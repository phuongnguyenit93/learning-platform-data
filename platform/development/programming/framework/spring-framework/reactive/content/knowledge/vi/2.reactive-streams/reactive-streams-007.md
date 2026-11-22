# Quan hệ với java.util.concurrent.Flow và các bộ chuyển đổi

## 1. Vấn đề: vì sao có hai bộ interface gần giống nhau?

Reactive Streams là đặc tả về trao đổi luồng dữ liệu bất đồng bộ có **backpressure**: bên nhận thông báo số phần tử mình sẵn sàng nhận, bên phát chỉ gửi trong phạm vi nhu cầu đã được cấp. Trên JVM, đặc tả ban đầu sử dụng các interface thuộc package **org.reactivestreams**. Từ **Java 9**, JDK đưa các interface tương ứng vào **java.util.concurrent.Flow**.

Điều quan trọng là **cùng mô hình và quy tắc cốt lõi, nhưng không cùng kiểu Java**. Một đối tượng khai báo là Flow.Publisher<T> không tự nhiên là org.reactivestreams.Publisher<T>, kể cả khi các tên và ý nghĩa phương thức giống nhau. Khi API A trả về Flow.Publisher còn thư viện B yêu cầu org.reactivestreams.Publisher, ta cần **adapter** để nối hai thế giới.

Sơ đồ:

~~~text
Java/JDK APIs                              Hệ sinh thái Reactive Streams
java.util.concurrent.Flow                  org.reactivestreams
  Flow.Publisher<T>     <-- adapter -->       Publisher<T>
  Flow.Subscriber<T>    <-- adapter -->       Subscriber<T>
  Flow.Subscription     <-- adapter -->       Subscription
  Flow.Processor<T,R>   <-- adapter -->       Processor<T,R>
                                                       |
                                                       v
                                                Project Reactor
                                                 Flux<T>/Mono<T>
                                                       |
                                                       v
                                                Spring WebFlux
                                           handler / controller / WebClient
~~~

**Adapter** chuyển đổi cách hai bên nhìn thấy cùng giao thức tín hiệu. Nó không tự biến stream thành nhanh hơn, không tạo backpressure mới và không biến thao tác blocking thành non-blocking.

## 2. Mapping một-một giữa các interface

| Reactive Streams (org.reactivestreams) | JDK Flow (java.util.concurrent) | Vai trò |
| --- | --- | --- |
| Publisher<T> | Flow.Publisher<T> | Cho phép Subscriber đăng ký bằng subscribe |
| Subscriber<T> | Flow.Subscriber<T> | Nhận onSubscribe, onNext, onError, onComplete |
| Subscription | Flow.Subscription | Điều phối request(n) và cancel() |
| Processor<T,R> | Flow.Processor<T,R> | Vừa tiêu thụ T vừa phát R |

Ví dụ các chữ ký cốt lõi có cùng ý nghĩa:

~~~java
// Trong org.reactivestreams.Publisher<T>:
void subscribe(org.reactivestreams.Subscriber<? super T> subscriber);

// Trong java.util.concurrent.Flow.Publisher<T>:
void subscribe(java.util.concurrent.Flow.Subscriber<? super T> subscriber);
~~~

Hai tham số Subscriber ở đây là **hai kiểu khác nhau**, nên một Publisher không thể được cast an toàn chỉ vì tên và hình dạng tương tự. Ép kiểu hoặc khai báo hai loại interface như đồng nhất có thể không biên dịch hoặc gây ClassCastException; dùng adapter rõ ràng.

Các tín hiệu và quy tắc quan trọng đối với **mỗi subscription**:

1. Publisher gọi onSubscribe, truyền Subscription cho Subscriber.
2. Subscriber gọi request(n) với n > 0 để cấp demand; tổng demand được cộng dồn, giới hạn bởi quy tắc của giao thức.
3. Publisher phát onNext(item) không vượt quá demand còn lại.
4. Publisher kết thúc bằng **một trong hai** onComplete() hoặc onError(error), sau đó không phát tín hiệu dữ liệu mới cho subscription đó.
5. Subscriber có thể hủy bằng cancel(); tác dụng ngừng phát và giải phóng tài nguyên phụ thuộc triển khai nguồn.
6. Tín hiệu phải được serialize theo quy tắc của giao thức, kể cả khi các thành phần xử lý dữ liệu trên nhiều thread.

**request(5)** có nghĩa yêu cầu tối đa năm **phần tử**, không phải năm byte, năm kết nối hay năm HTTP request. Gọi request(0) hoặc request âm là vi phạm giao thức và nguồn tuân thủ đặc tả phải báo lỗi theo quy tắc Subscription.

## 3. java.util.concurrent.Flow là gì và không phải là gì?

Flow thuộc module **java.base**, vì vậy Java 17 có sẵn các interface mà không cần cài Project Reactor, Spring hay dependency Reactive Streams bên ngoài. Flow là **hợp đồng** cho các thành phần phát/nhận dữ liệu; bản thân lớp Flow không cung cấp toán tử map, flatMap, zip như Flux.

JDK có **SubmissionPublisher<T>**, một triển khai Flow.Publisher dùng để phát dữ liệu đến các subscriber hiện đang đăng ký:

- Phân phối tín hiệu bất đồng bộ qua Executor.
- Có buffer riêng theo subscriber và cách xử lý khi phía nhận chậm.
- **submit(item)** có thể chặn khi buffer của subscriber đầy; **offer(...)** cung cấp lựa chọn xử lý khi không nhận được dữ liệu.
- Dữ liệu đã gửi trước khi một subscriber đăng ký không mặc nhiên được replay cho subscriber đó.
- Phải quản lý đóng publisher và vòng đời executor khi tạo tài nguyên riêng.

Điểm này dễ gây hiểu nhầm: **Flow có giao thức backpressure không có nghĩa mọi lời gọi của SubmissionPublisher đều không blocking**. Cần đọc hành vi từng API và kiểm thử tải.

### Ví dụ Java 17 thuần JDK: nhận từng phần tử theo demand

Lưu thành **FlowBasicsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowBasicsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> source =
                new SubmissionPublisher<>(executor, 16)) {

            source.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription value) {
                    subscription = value;
                    subscription.request(1);
                    subscribed.countDown();
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("item=" + value);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    error.printStackTrace();
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No subscription");
            }

            source.submit(10);
            source.submit(20);
            source.submit(30);
            source.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Stream did not complete");
            }
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy trong JDK 17+:

~~~bash
javac FlowBasicsDemo.java
java FlowBasicsDemo
~~~

Kết quả trong điều kiện thực thi bình thường:

~~~text
item=10
item=20
item=30
complete
~~~

Ở đây **onSubscribe** yêu cầu một phần tử; **onNext** yêu cầu thêm một phần tử. CountDownLatch bảo đảm ví dụ đợi tín hiệu đăng ký và kết thúc thay vì phụ thuộc tốc độ thread. Các callback chạy qua executor nên việc xử lý vẫn bất đồng bộ. Ví dụ có timeout để phát hiện trường hợp không nhận được tín hiệu; nếu xảy ra lỗi, stderr có thể chứa stack trace, không phải bốn dòng trên.

## 4. Adapter chuyển đổi những gì?

Adapter nối **kiểu interface** ở hai phía. Với Publisher:

~~~text
Flow.Publisher<T>
      |
      | subscribe(Flow.Subscriber)
      |          được chuyển thành
      v
org.reactivestreams.Publisher<T>
      |
      | subscribe(org.reactivestreams.Subscriber)
      v
Pipeline dùng Reactor / thư viện Reactive Streams
~~~

Ở biên chuyển đổi, adapter cung cấp các wrapper tương ứng cho Subscriber và Subscription. Khi downstream cấp request(n), adapter chuyển lời gọi yêu cầu về phía nguồn; khi nguồn gửi onNext, onError, onComplete, adapter chuyển tín hiệu qua bên nhận theo hợp đồng.

Bốn điểm cần phân biệt:

- **Chuyển đổi interface ≠ chuyển đổi từng giá trị**: adapter thường giữ nguyên loại phần tử T. Dùng map nếu muốn thay nội dung dữ liệu.
- **Adapter ≠ scheduler**: adapter không mặc nhiên tạo executor/thread riêng cho xử lý nghiệp vụ.
- **Adapter ≠ buffer không giới hạn**: giới hạn bộ nhớ vẫn do nguồn, toán tử, runtime và chiến lược backpressure quyết định.
- **Adapter ≠ sửa nguồn sai giao thức**: nếu một Publisher vi phạm demand hoặc phát tín hiệu sai thứ tự, bọc adapter không bảo đảm tự động khắc phục hành vi đó.

Adapter đặc biệt hữu ích **tại ranh giới tích hợp**: một JDK API trả Flow.Publisher nhưng tầng service sử dụng Flux; hoặc service Reactor cần xuất API chuẩn Flow cho thành phần Java không phụ thuộc Reactor.

## 5. Cách 1: JdkFlowAdapter tích hợp trong Project Reactor

Reactor cung cấp lớp **reactor.adapter.JdkFlowAdapter**, nằm trong thư viện reactor-core, với hai phương thức chính:

| Chuyển đổi | Phương thức | Kết quả |
| --- | --- | --- |
| Flow.Publisher<T> → Flux<T> | JdkFlowAdapter.flowPublisherToFlux(source) | Một Flux<T> có thể dùng các toán tử Reactor |
| org.reactivestreams.Publisher<T> → Flow.Publisher<T> | JdkFlowAdapter.publisherToFlowPublisher(source) | Publisher theo kiểu của JDK Flow |

Mono<T> và Flux<T> đều thuộc hệ Reactive Streams; do đó có thể truyền cho phương thức thứ hai. Nếu muốn giữ ngữ nghĩa 0 hoặc 1 phần tử của Mono khi nhận trở lại từ Flow.Publisher, cần bảo đảm contract nguồn và lựa chọn chuyển đổi thích hợp; **flowPublisherToFlux** trả về Flux, không tự cam kết đầu ra Mono.

### Ví dụ runnable: chuyển qua lại Reactor ↔ JDK Flow

Dùng **Java 17+, Maven 3.9+**. Cấu trúc:

~~~text
flow-reactor-bridge/
  pom.xml
  src/main/java/example/FlowReactorBridgeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>flow-reactor-bridge</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/FlowReactorBridgeDemo.java**:

~~~java
package example;

import java.util.concurrent.Flow;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

public class FlowReactorBridgeDemo {
    public static void main(String[] args) {
        // Hệ Reactive Streams -> kiểu Publisher chuẩn JDK.
        Flux<Integer> reactorSource = Flux.range(1, 3);
        Flow.Publisher<Integer> flowSource =
                JdkFlowAdapter.publisherToFlowPublisher(reactorSource);

        // Kiểu Publisher chuẩn JDK -> Flux để dùng toán tử Reactor.
        Flux<Integer> reactorAgain =
                JdkFlowAdapter.flowPublisherToFlux(flowSource);

        reactorAgain
                .map(number -> number * 10)
                .doOnNext(number -> System.out.println("value=" + number))
                .blockLast(); // Chỉ dùng ở ranh giới ứng dụng demo.
    }
}
~~~

Từ thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.FlowReactorBridgeDemo
~~~

Các dòng do chương trình in:

~~~text
value=10
value=20
value=30
~~~

Đây là pipeline có nguồn **Flux.range** hữu hạn; blockLast() được dùng trong **main** để đợi kết thúc cho ví dụ CLI. Trong controller WebFlux, không gọi blockLast()/block() để chờ Publisher: framework sẽ subscribe và quản lý phản hồi.

Ví dụ trên minh họa hai hướng của adapter bằng một nguồn Reactor, nên **không chứng minh hiệu năng của một Flow.Publisher bên ngoài Reactor**. Trong thực tế, Flow.Publisher có thể đến từ thành phần JDK, thư viện khác hoặc một Publisher tự xây dựng tuân thủ hợp đồng Flow.

## 6. Cách 2: org.reactivestreams.FlowAdapters

Reactive Streams cung cấp lớp **org.reactivestreams.FlowAdapters** để chuyển đổi các interface giữa hai hệ. Không nên nhầm lớp này với **reactor.adapter.JdkFlowAdapter**.

| Phương thức FlowAdapters | Tác dụng |
| --- | --- |
| toPublisher(Flow.Publisher) | Flow Publisher → Reactive Streams Publisher |
| toFlowPublisher(Publisher) | Reactive Streams Publisher → Flow Publisher |
| toSubscriber(Flow.Subscriber) | Flow Subscriber → Reactive Streams Subscriber |
| toFlowSubscriber(Subscriber) | Reactive Streams Subscriber → Flow Subscriber |
| toProcessor(Flow.Processor) | Flow Processor → Reactive Streams Processor |
| toFlowProcessor(Processor) | Reactive Streams Processor → Flow Processor |

Tùy dependency và phiên bản đang dùng, kiểm tra lớp FlowAdapters thuộc artifact nào thực sự có trên classpath. Ví dụ với **org.reactivestreams:reactive-streams:1.0.4**, API FlowAdapters được công bố trong Javadoc của artifact; với dự án cũ còn có artifact **reactive-streams-flow-adapters** riêng ở các phiên bản trước. Tránh đồng thời đưa nhiều bản khác nhau của cùng lớp vào classpath.

Ví dụ ngắn (giả định có reactor-core và Reactive Streams 1.0.4 trên classpath):

~~~java
import java.util.concurrent.Flow;
import org.reactivestreams.FlowAdapters;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Flux;

// Reactor Flux là Reactive Streams Publisher.
Publisher<Integer> rsPublisher = Flux.range(1, 3);

// Reactive Streams -> JDK Flow.
Flow.Publisher<Integer> flowPublisher =
        FlowAdapters.toFlowPublisher(rsPublisher);

// JDK Flow -> Reactive Streams.
Publisher<Integer> rsAgain =
        FlowAdapters.toPublisher(flowPublisher);

// Kết hợp với Reactor.
Flux.from(rsAgain)
    .map(n -> n + 100)
    .doOnNext(System.out::println)
    .blockLast();
~~~

Đoạn code trên **là ví dụ chèn vào một phương thức, không phải class Java độc lập**. Với nguồn Flux.range và thực thi bình thường, nó in 101, 102, 103 trên ba dòng. Các hàm toSubscriber/toFlowSubscriber và toProcessor/toFlowProcessor hữu ích khi **hợp đồng được tích hợp là subscriber hoặc processor**, không chỉ publisher.

Lựa chọn thực tế:

- Đã dùng Reactor và cần đổi giữa **Flux** với **Flow.Publisher**: chọn JdkFlowAdapter, gọn và trực tiếp.
- Đang viết thư viện muốn nối hai bộ **interface chuẩn** mà không dựa vào toán tử Reactor: chọn FlowAdapters, dùng đúng dependency được quản lý.
- Đang xây endpoint WebFlux: chuyển Flow.Publisher thành Flux ở biên service/controller rồi trả Publisher cho framework.

Không cần chuyển đổi nhiều vòng nếu cả hai phía vốn đã dùng cùng một loại Publisher.

## 7. Ứng dụng trong Spring WebFlux

**Spring WebFlux** dùng Reactor làm nền tảng lập trình reactive. Controller có thể trả Mono/Flux; Reactor biểu diễn contract Reactive Streams; web runtime xử lý HTTP. Khi một API của JDK hoặc thư viện bên ngoài cung cấp Flow.Publisher, ta thích nghi ở biên đó:

~~~text
Nguồn ngoài cung cấp Flow.Publisher<T>
                   |
      JdkFlowAdapter.flowPublisherToFlux(...)
                   |
                Flux<T>
                   |
          map / filter / timeout
                   |
           Spring WebFlux controller
                   |
             HTTP response
~~~

Ví dụ cấu trúc controller (đoạn minh họa, cần có bean ExternalFlowService và phương thức stream() do ứng dụng cung cấp):

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

@RestController
class FeedController {
    private final ExternalFlowService external;

    FeedController(ExternalFlowService external) {
        this.external = external;
    }

    @GetMapping("/feed")
    Flux<String> feed() {
        return JdkFlowAdapter
                .flowPublisherToFlux(external.stream())
                .map(String::trim);
    }
}
~~~

Giả định **external.stream()** trả **java.util.concurrent.Flow.Publisher<String>**. Không cần tự gọi subscribe() ở controller; WebFlux điều phối subscription theo vòng đời HTTP. Việc hủy do client ngắt kết nối có thể lan truyền qua adapter, nhưng chỉ dẫn đến dừng công việc thật sự nếu **nguồn và những tầng trung gian tôn trọng cancel()**.

**Spring WebFlux không tự đồng nghĩa với java.util.concurrent.Flow**: mặc dù hai bộ interface tương thích về mô hình, lập trình viên vẫn nên xác định API public cụ thể của thư viện mình tích hợp thay vì giả định mọi Flow.Publisher có thể truyền trực tiếp đến phương thức chỉ nhận org.reactivestreams.Publisher.

## 8. Backpressure đi qua adapter như thế nào?

Giả sử Subscriber nhận dữ liệu qua Flux được chuyển từ Flow.Publisher:

~~~text
Flow source                         Adapter                   Reactor subscriber
     |                                  |                              |
     | <------------ request(2) --------|<------ request(2) ---------|
     | --------- onNext(A) ------------>|------ onNext(A) ---------->|
     | --------- onNext(B) ------------>|------ onNext(B) ---------->|
     | <------------ request(1) --------|<------ request(1) ---------|
     | --------- onNext(C) ------------>|------ onNext(C) ---------->|
     | -------- onComplete() ---------->|----- onComplete() -------->|
~~~

Đây là **sơ đồ logic giản lược**. Các toán tử thực tế có thể prefetch, gom, chia nhỏ hoặc tăng demand, nên không thể khẳng định request từ consumer cuối luôn truyền nguyên xi qua từng operator. Điều quan trọng là bên phát phải bảo toàn giao thức và không gửi vượt quá demand cho mỗi subscription.

Phân biệt rõ các cơ chế thường bị gộp làm một:

- **Reactive Streams / Flow request(n)**: điều tiết **số phần tử** giữa Publisher và Subscriber.
- **SubmissionPublisher buffer**: giữ các phần tử đang chờ xử lý theo chính sách của implementation.
- **Network flow control**: TCP, HTTP/2, connection pool hoặc hàng đợi ở tầng network.
- **Reactor operators**: có thể prefetch, buffer, drop, limitRate hoặc đổi scheduler tùy ngữ nghĩa toán tử.

Một adapter không thay thế các tầng còn lại. Nếu upstream sinh dữ liệu không kiểm soát, cần đặt chính sách giới hạn, timeout, đo lượng buffer và xử lý lỗi tại nguồn hay tầng phù hợp.

## 9. Các lỗi phổ biến khi tích hợp

### Lỗi 1: nghĩ hai Publisher cùng tên nên có thể gán trực tiếp

~~~java
// Không biên dịch nếu method trả Flow.Publisher<String>:
org.reactivestreams.Publisher<String> value = externalFlowMethod();
~~~

Sửa bằng adapter:

~~~java
org.reactivestreams.Publisher<String> value =
        org.reactivestreams.FlowAdapters.toPublisher(
                externalFlowMethod());
~~~

### Lỗi 2: gọi subscribe() thủ công trong controller

Nếu controller tự subscribe() để xử lý dữ liệu rồi trả một kết quả khác, pipeline có nguy cơ mất liên kết với việc ghi response, hủy request và error propagation. Thông thường hãy **trả Flux/Mono** cho WebFlux.

### Lỗi 3: chuyển đổi kiểu rồi cho rằng blocking đã biến mất

~~~java
Flow.Publisher<String> source = obtainFlowPublisher();
Flux<String> result = JdkFlowAdapter.flowPublisherToFlux(source);
~~~

Adapter không đảm bảo tác vụ bên trong source là non-blocking; điều này phụ thuộc implementation. Nếu tạo Flow.Publisher bằng thread chặn hoặc SubmissionPublisher.submit() có lúc chặn vì buffer đầy, việc bọc thành Flux không loại bỏ blocking.

### Lỗi 4: nhầm kết thúc, lỗi và hủy

- **onComplete**: nguồn hoàn tất bình thường.
- **onError**: nguồn kết thúc với lỗi, không được phát thêm onComplete.
- **cancel**: Subscriber chủ động dừng subscription; không bắt buộc phải nhận onComplete sau cancel.

Khi xử lý lỗi qua onErrorResume hoặc retry trong Reactor, việc đăng ký mới và số lần thực thi có thể thay đổi; adapter không chịu trách nhiệm chính sách retry.

### Lỗi 5: bỏ qua lifecycle của nguồn hot

SubmissionPublisher thường phát cho **subscriber hiện đang có mặt**. Nếu đăng ký sau khi dữ liệu đã submit, không được giả định có replay. Nếu nguồn cần được đóng, quản lý close(), executor và tín hiệu hoàn tất đúng chỗ. Đừng giữ mãi SubmissionPublisher hoặc các đăng ký không còn được tiêu thụ.

### Lỗi 6: tưởng FlowAdapters là bộ chuyển dữ liệu đồng bộ sang bất đồng bộ

Chúng chỉ **bọc và chuyển tín hiệu giao thức**. Dùng scheduler, executor, asynchronous I/O hoặc thiết kế nguồn phù hợp khi thực sự cần thay đổi cách thực thi.

## 10. Hướng dẫn chọn cách tích hợp

| Đầu vào / yêu cầu | Giải pháp ưu tiên | Lý do |
| --- | --- | --- |
| JDK Flow.Publisher → Flux trong ứng dụng Reactor | JdkFlowAdapter.flowPublisherToFlux | Trực tiếp trả Flux để dùng toán tử |
| Flux hoặc Mono → API yêu cầu Flow.Publisher | JdkFlowAdapter.publisherToFlowPublisher | Giữ nguyên nguồn reactive, xuất interface JDK |
| Flow.Publisher → thư viện nhận Reactive Streams Publisher, không cần Reactor | FlowAdapters.toPublisher | Giữ biên API thuần Reactive Streams |
| Reactive Streams Publisher → JDK Flow.Publisher | FlowAdapters.toFlowPublisher | Không cần ép kiểu |
| Tích hợp Flow.Subscriber hoặc Flow.Processor | FlowAdapters.toSubscriber/toFlowSubscriber hoặc toProcessor/toFlowProcessor | Adapter hỗ trợ cả hai chiều cho Subscriber/Processor |
| Nguồn Flow đi vào Spring WebFlux | Chuyển thành Flux trong service hoặc controller | Trả Publisher phù hợp cho vòng đời HTTP của WebFlux |

Hãy kiểm tra dependency tree để tránh nhiều phiên bản Reactive Streams hoặc adapter không tương thích trong cùng ứng dụng. Trong Spring Boot, ưu tiên phiên bản Reactor và thư viện liên quan do dependency management quản lý trừ khi có yêu cầu tương thích cụ thể.

## 11. Tự kiểm tra

**Câu 1.** Tại sao không thể gán Flow.Publisher<Integer> cho org.reactivestreams.Publisher<Integer>?

Vì chúng là hai interface khác nhau, thuộc package khác nhau; API subscribe nhận các kiểu Subscriber khác nhau. Chúng cùng mô hình nhưng không có quan hệ kế thừa. Dùng adapter.

**Câu 2.** Có cần Reactor để sử dụng Flow.Publisher trong Java 17 không?

Không. Flow nằm trong JDK; có thể dùng Flow.Subscriber và SubmissionPublisher mà không thêm dependency bên ngoài.

**Câu 3.** Một adapter giúp client WebFlux không bị nghẽn nếu nguồn bên dưới gọi thao tác blocking chứ?

Không. Adapter chuyển hợp đồng Publisher; thao tác blocking vẫn blocking trên thread đang chạy. Cần lựa chọn nguồn hoặc cơ chế thực thi phù hợp.

**Câu 4.** Nếu muốn trả dữ liệu Flow.Publisher từ một service lên WebFlux, nên làm gì?

Chuyển Flow.Publisher thành Flux bằng JdkFlowAdapter.flowPublisherToFlux rồi trả Flux từ handler/controller, để WebFlux quản lý subscription, lỗi và hủy.

**Câu 5.** request(3) đảm bảo buffer hay TCP socket đọc đúng ba lần?

Không. Demand là số phần tử giao thức, còn buffering, I/O và prefetch có cơ chế riêng.

## 12. Tài liệu đối chiếu

- Java 17 API: [java.util.concurrent.Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html) và [Flow.Publisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html).
- Java 17 API: [SubmissionPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html).
- Reactor API: [reactor.adapter.JdkFlowAdapter (Reactor 3.6)](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.0/api/reactor/adapter/JdkFlowAdapter.html).
- Reactive Streams API: [org.reactivestreams.FlowAdapters (1.0.4)](https://javadoc.io/static/org.reactivestreams/reactive-streams/1.0.4/org/reactivestreams/FlowAdapters.html).
- Đặc tả Reactive Streams cho JVM: [reactive-streams-jvm](https://github.com/reactive-streams/reactive-streams-jvm).

**Ghi nhớ:** **java.util.concurrent.Flow** là cách JDK biểu diễn giao thức tương ứng Reactive Streams; **org.reactivestreams** là bộ interface độc lập đã được hệ sinh thái reactive sử dụng rộng rãi; **FlowAdapters** và **JdkFlowAdapter** nối hai phía; **Reactor** bổ sung Mono/Flux và toán tử; **Spring WebFlux** dùng những Publisher đó trong luồng xử lý web. Chuyển đổi đúng tại ranh giới API giúp mã dễ đọc và giữ rõ trách nhiệm về backpressure, threading và vòng đời dữ liệu.
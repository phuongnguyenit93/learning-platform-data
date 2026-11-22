# Lập trình phản ứng là gì và vì sao Spring hỗ trợ?

## 1. Bài toán mà lập trình phản ứng giải quyết

Trong một ứng dụng web, thời gian xử lý yêu cầu thường bao gồm cả thời gian **chờ I/O**: truy vấn cơ sở dữ liệu, gọi dịch vụ khác, nhận dữ liệu qua mạng hoặc gửi sự kiện cho trình duyệt. Với cách xử lý đồng bộ, mã có thể dừng ở lời gọi I/O cho đến khi có kết quả; luồng đang thực thi không thể tiếp tục công việc đó trong lúc chờ.

**Lập trình phản ứng (reactive programming)** là cách xây dựng chương trình quanh các luồng dữ liệu và sự kiện bất đồng bộ. Thay vì yêu cầu lấy ngay một giá trị, ta mô tả **chuỗi xử lý sẽ diễn ra khi dữ liệu xuất hiện**, cùng quy tắc hoàn tất và xử lý lỗi. Hệ thống nhận tín hiệu dữ liệu, biến đổi chúng, kết hợp các nguồn và chuyển tiếp kết quả cho bên tiêu thụ.

Ví dụ, thay vì tư duy “gọi dịch vụ A, đứng chờ; rồi gọi dịch vụ B, đứng chờ”, ta có thể mô tả các thao tác I/O không chặn, kết hợp kết quả khi sẵn sàng và trả phản hồi mà không giữ một luồng chỉ để chờ mạng. Đây là lợi ích khi **toàn bộ những đoạn I/O liên quan thực sự hỗ trợ non-blocking**.

Ba khái niệm cần phân biệt:

- **Bất đồng bộ (asynchronous):** công việc có thể hoàn tất sau, kết quả được báo qua tín hiệu/callback/future; không có nghĩa là luôn non-blocking ở mọi tầng.
- **Không chặn (non-blocking):** luồng thực thi không bị giữ lại chỉ để đợi thao tác I/O hoàn thành.
- **Phản ứng (reactive):** tổ chức dữ liệu và sự kiện thành pipeline có quy tắc phát, tiêu thụ, hoàn tất, lỗi và (trong mô hình Reactive Streams) điều tiết tốc độ nhận. Reactive không tự động có nghĩa là chạy song song hoặc chạy nhanh hơn.

“Reactive” trong **Reactive Streams** là một đặc tả giao tiếp giữa nguồn phát và bên nhận; “reactive system” trong kiến trúc phần mềm là khái niệm rộng hơn. Không nên đồng nhất hai thuật ngữ.

## 2. Cơ chế cốt lõi: luồng dữ liệu, tín hiệu và backpressure

Trong hệ sinh thái Spring reactive, thư viện **Project Reactor** triển khai mô hình Reactive Streams. Các thành phần quan trọng:

| Thành phần | Trách nhiệm |
| --- | --- |
| Publisher | Nguồn mô tả khả năng phát các phần tử theo thời gian. |
| Subscriber | Bên đăng ký để nhận dữ liệu, lỗi hoặc tín hiệu hoàn tất. |
| Subscription | Quan hệ đăng ký cho phép yêu cầu thêm phần tử và hủy luồng. |
| Operator | Phép biến đổi/kết hợp pipeline, chẳng hạn map, filter, flatMap, zip, timeout. |

Luồng tín hiệu điển hình là: Subscriber đăng ký với Publisher → nhận Subscription → gửi yêu cầu số phần tử có thể tiếp nhận (request(n)) → nhận các tín hiệu onNext → kết thúc bằng **onComplete** hoặc **onError**; Subscriber có thể **cancel**. Một stream có tối đa một tín hiệu kết thúc. Lỗi là một tín hiệu kết thúc, không phải một phần tử dữ liệu thông thường.

**Backpressure (điều tiết ngược)** giải quyết tình huống nguồn phát nhanh hơn khả năng xử lý của bên nhận. Theo hợp đồng Reactive Streams, Subscriber có thể yêu cầu từng lượng dữ liệu qua request(n) thay vì buộc phải nhận vô hạn. Tuy nhiên, backpressure chỉ hoạt động đầy đủ khi các thành phần trong đường truyền phối hợp hỗ trợ nó; không nên suy ra mọi driver, giao thức mạng hoặc nguồn dữ liệu bên ngoài đều có khả năng điều tiết tương đương.

Hai kiểu Publisher được Reactor dùng thường xuyên:

- **Mono<T>:** phát tối đa một phần tử, hoặc rỗng, hoặc báo lỗi. Phù hợp với thao tác lấy một bản ghi, kết quả gọi API, lệnh ghi hoặc một phản hồi HTTP.
- **Flux<T>:** phát từ 0 đến nhiều phần tử, rồi hoàn tất hoặc lỗi. Phù hợp với danh sách, sự kiện liên tục, stream dữ liệu và phản hồi nhiều phần.

Phần lớn pipeline Reactor là **lazy**: việc khai báo Flux/Mono với các operator chưa khiến công việc bắt đầu; nó được kích hoạt khi có **subscription**. Mặc định, nhiều nguồn là *cold* (mỗi lần đăng ký tạo một lượt xử lý); một số nguồn *hot* có thể phát tín hiệu độc lập với thời điểm đăng ký. Lựa chọn cold/hot ảnh hưởng đến việc chia sẻ dữ liệu, phát lại và số lần thực hiện I/O.

## 3. Vì sao Spring hỗ trợ mô hình reactive?

Spring phục vụ cả ứng dụng web truyền thống lẫn hệ thống có lượng kết nối đồng thời lớn, nhiều lời gọi I/O và dữ liệu cập nhật liên tục. Reactive là **một lựa chọn bổ sung** để giải quyết những nhu cầu này:

1. **Sử dụng luồng hiệu quả khi I/O chiếm nhiều thời gian.** Với stack non-blocking, một số lượng luồng nhỏ hơn có thể điều phối nhiều yêu cầu đang đợi mạng; ứng dụng không phải giữ riêng một luồng bị chặn cho mỗi thao tác I/O.
2. **Xử lý nhiều kết nối đồng thời và stream lâu dài.** Server-Sent Events (SSE), WebSocket và các nguồn phát dữ liệu tuần tự dễ biểu đạt qua Publisher.
3. **Kết hợp lời gọi bất đồng bộ.** Các operator cho phép phối hợp kết quả từ nhiều dịch vụ, xử lý timeout, fallback, hủy và lỗi theo một pipeline rõ ràng.
4. **Điều tiết dòng dữ liệu.** Reactive Streams cung cấp cơ chế demand/backpressure ở những ranh giới hỗ trợ, giúp thiết kế luồng tiêu thụ kiểm soát được.
5. **Đồng bộ hệ sinh thái lập trình.** Cùng mô hình Mono/Flux có thể đi qua HTTP, WebClient, truy cập dữ liệu reactive và xử lý nghiệp vụ, hạn chế các bước chuyển đổi rời rạc giữa nhiều kiểu callback.

Mục tiêu chính là **khả năng mở rộng tốt đối với tải nhiều I/O đồng thời và cách biểu diễn dòng dữ liệu**. Reactive **không bảo đảm độ trễ mỗi yêu cầu thấp hơn**, không tự làm CPU tính nhanh hơn và không thay thế nhu cầu đo lường hiệu năng.

### Các mảnh ghép trong Spring

| Công nghệ | Vai trò |
| --- | --- |
| **Project Reactor** | Thư viện nền cung cấp Mono, Flux và operator; triển khai Reactive Streams. |
| **Spring WebFlux** | Web stack reactive để xử lý HTTP, lập trình controller hoặc functional routing; hỗ trợ streaming. |
| **WebClient** | HTTP client có API reactive; thích hợp cho lời gọi mạng không chặn. |
| **Spring Data R2DBC** | Truy cập cơ sở dữ liệu quan hệ bằng API/driver reactive; khác với JDBC truyền thống vốn blocking. |
| **Spring Data reactive repositories** | Cung cấp các repository reactive khi kho dữ liệu và driver tương ứng thực sự hỗ trợ. |
| **Spring Boot** | Tự động cấu hình và vận hành ứng dụng WebFlux khi chọn starter phù hợp. |

**Spring MVC và Spring WebFlux cùng tồn tại.** MVC là lựa chọn rất tốt cho nhiều ứng dụng HTTP thông thường; WebFlux phù hợp khi cần pipeline non-blocking hoặc stream. WebFlux có thể vận hành trên runtime hỗ trợ phù hợp, thường dùng Reactor Netty với mô hình event loop. Spring không bắt buộc mọi ứng dụng phải chuyển sang reactive.

## 4. Một pipeline Reactor chạy được trên Java 17+

Ví dụ sau minh họa cách khai báo, biến đổi, lọc và tiêu thụ Mono/Flux. Đây là ví dụ **Reactor Core**, chưa phải một ứng dụng HTTP.

Tạo cấu trúc thư mục:

~~~text
reactive-intro/
├── pom.xml
└── src/main/java/ReactiveIntro.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-intro</artifactId>
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
                    <mainClass>ReactiveIntro</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/ReactiveIntro.java**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveIntro {
    public static void main(String[] args) {
        Flux.just("spring", "reactor", "webflux")
                .map(String::toUpperCase)
                .filter(word -> word.length() >= 7)
                .doOnNext(word -> System.out.println("Flux: " + word))
                .blockLast();

        Mono.just("reactive")
                .map(String::toUpperCase)
                .doOnNext(word -> System.out.println("Mono: " + word))
                .block();
    }
}
~~~

Với **JDK 17+** và Maven đã cài, chạy trong thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

Stdout của chương trình:

~~~text
Flux: REACTOR
Flux: WEBFLUX
Mono: REACTIVE
~~~

Giải thích từng bước:

- Flux.just tạo Publisher từ ba chuỗi; map đổi thành chữ hoa; filter bỏ “SPRING” vì có 6 ký tự; doOnNext in hai phần tử còn lại.
- Mono.just tạo Publisher tối đa một phần tử; map chuyển thành “REACTIVE”.
- blockLast()/block() tạo subscription rồi **chờ** kết thúc để chương trình console không thoát trước khi quan sát kết quả. Cách chờ này chỉ dùng ở **ranh giới chương trình demo/đồng bộ**; không nên chèn block() vào luồng xử lý request non-blocking của WebFlux.
- Vì nguồn trong ví dụ là dữ liệu nằm sẵn trong bộ nhớ, ví dụ chủ yếu minh họa **mô hình pipeline và subscription**; nó không chứng minh lợi thế non-blocking I/O. Lợi thế đó xuất hiện khi nối pipeline với các API mạng/cơ sở dữ liệu thực sự non-blocking.

## 5. Reactivity xuất hiện trong một API Spring như thế nào?

Trong dự án Spring Boot đã cấu hình **spring-boot-starter-webflux**, controller dưới đây phát ba giá trị dưới dạng **Server-Sent Events**. Đây là **đoạn mã controller cho một dự án WebFlux hiện có**; nó không phải một chương trình độc lập thiếu bootstrap.

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class TickController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(1)).take(3);
    }
}
~~~

Khi ứng dụng đang chạy, yêu cầu HTTP tới **GET /ticks** sẽ nhận lần lượt các giá trị 0, 1, 2 theo thời gian rồi kết thúc. Framework đăng ký với Publisher và ghi dữ liệu ra HTTP response theo cơ chế của WebFlux. Controller **trả Publisher** để framework quản lý vòng đời, thay vì tự gọi subscribe() rồi trả về trước khi xử lý xong.

**Mono/Flux không đồng nghĩa với non-blocking trong mọi trường hợp.** Ví dụ, đặt một truy vấn JDBC blocking hoặc Thread.sleep() bên trong map() vẫn giữ luồng đang chạy trong lúc đợi. Để khai thác WebFlux, đường đi I/O cần dùng những API tương thích như WebClient và driver cơ sở dữ liệu reactive khi có sẵn.

## 6. So sánh với cách xử lý truyền thống

| Tiêu chí | Mô hình thường gặp với Spring MVC và API blocking | Spring WebFlux với I/O non-blocking |
| --- | --- | --- |
| Tư duy xử lý | Gọi hàm, nhận kết quả hoặc chờ kết quả trước khi đi tiếp. | Khai báo Publisher và các phép biến đổi khi tín hiệu đến. |
| Trong lúc đợi I/O | Luồng gọi API blocking thường bị giữ để chờ. | Luồng có thể tiếp tục điều phối công việc khác nếu I/O thật sự không chặn. |
| Giao diện | Giá trị, collection, ResponseEntity, cùng các hỗ trợ async khác của MVC. | Mono/Flux hoặc các kiểu được WebFlux hỗ trợ. |
| Streaming | Có cơ chế streaming/async riêng của MVC. | Stream là mô hình trung tâm, phù hợp SSE và luồng liên tục. |
| Độ phức tạp | Dễ theo dõi bằng call stack đồng bộ. | Cần hiểu subscription, operator, scheduling, context và tín hiệu lỗi. |

Cần tránh hai suy luận sai:

- **Reactive không có nghĩa là mọi thao tác chạy trên thread riêng.** Pipeline có thể chạy ngay trên luồng gọi khi dùng nguồn đồng bộ; scheduler quyết định lúc nào chuyển luồng, còn event loop hỗ trợ I/O non-blocking.
- **Reactive không có nghĩa là parallel.** Muốn xử lý song song tác vụ CPU phải thiết kế và đo đạc riêng; sử dụng Flux/Mono đơn thuần không tự phân bổ tác vụ qua nhiều lõi.

## 7. Khi nào nên chọn, khi nào nên cân nhắc?

**WebFlux/reactive thường đáng cân nhắc** khi dịch vụ có rất nhiều kết nối đồng thời, phần lớn thời gian là chờ I/O; cần SSE/WebSocket/stream; gọi nhiều dịch vụ ngoài và muốn kết hợp các Publisher; hoặc hệ thống đã dùng driver và thư viện non-blocking xuyên suốt.

**Spring MVC thường đơn giản và hiệu quả hơn** với CRUD truyền thống, lưu lượng vừa phải, hệ thống phụ thuộc JDBC/thư viện blocking và đội ngũ quen với cách lập trình tuần tự. Với Java hiện đại, **virtual threads** cũng là một lựa chọn cần đo đạc cho workload I/O blocking, nhưng chúng không tự biến JDBC hay API blocking thành Reactive Streams.

Quyết định nên dựa trên **loại tải (I/O hay CPU), số yêu cầu/kết nối đồng thời, thư viện đang dùng, khả năng vận hành và số đo thực tế**, thay vì mặc định chọn reactive vì tên gọi hiện đại.

## 8. Những lỗi phổ biến khi bắt đầu

1. **Gọi block(), blockFirst() hoặc blockLast() trong đường xử lý HTTP WebFlux.** Việc này chặn luồng và có thể gây lỗi trên luồng event loop. Trả về Mono/Flux cho framework xử lý, dùng các operator để nối pipeline.
2. **Bọc thao tác blocking trong Mono.just() rồi tưởng là non-blocking.** Giá trị truyền vào Mono.just() được tính trước; nếu phép tính truy vấn DB/gọi mạng đang blocking thì sự chặn đã xảy ra. Khi buộc phải dùng API blocking, phải tách rõ ranh giới và cân nhắc scheduler phù hợp, chẳng hạn boundedElastic, như một giải pháp chuyển tiếp có giới hạn.
3. **Tự subscribe() trong controller/service để “chạy cho chắc”.** Dễ làm mất quản lý lỗi, hủy request và thời điểm phản hồi. Hãy ghép Publisher và trả về cho lớp chịu trách nhiệm subscribe.
4. **Bỏ qua onError, timeout và cancel.** Lỗi trong pipeline là tín hiệu kết thúc; cần xử lý bằng các operator phù hợp, đồng thời đặt giới hạn thời gian đối với lời gọi bên ngoài.
5. **Nhầm map với flatMap.** map dùng khi hàm trả giá trị thường; flatMap phù hợp khi hàm trả Publisher cần ghép vào chuỗi bất đồng bộ. flatMap có thể xen kẽ kết quả; nếu thứ tự là yêu cầu nghiệp vụ, cần chọn operator đúng.
6. **Giả định ThreadLocal luôn đi theo request.** Pipeline có thể đổi thread; dữ liệu ngữ cảnh trong ứng dụng reactive nên đi qua cơ chế hỗ trợ như Reactor Context/Spring tương ứng.
7. **Cho rằng backpressure luôn tự chống tràn bộ nhớ.** Cần hiểu giới hạn nguồn dữ liệu, buffering, tốc độ xử lý downstream và cơ chế của từng driver/giao thức.
8. **Tối ưu mà không đo.** Luồng reactive có thêm độ phức tạp về debug, tracing và test; so sánh throughput, latency, CPU, memory và độ ổn định với tải thực trước khi quyết định.

## 9. Ghi nhớ

Lập trình phản ứng mô tả **điều gì xảy ra khi dữ liệu/sự kiện đến** qua một pipeline Publisher → Subscriber, với các tín hiệu dữ liệu, kết thúc và lỗi; Reactive Streams bổ sung cơ chế demand/backpressure. Trong Spring, **Reactor** cung cấp Mono/Flux, **WebFlux** phục vụ HTTP reactive, **WebClient** hỗ trợ gọi HTTP bất đồng bộ và các thành phần dữ liệu reactive cho phép nối chuỗi non-blocking khi driver hỗ trợ.

**Lý do Spring hỗ trợ reactive là để có thêm mô hình xử lý I/O đồng thời, streaming và kết hợp bất đồng bộ**, song song với Spring MVC. Giá trị của nó phụ thuộc vào pipeline có thực sự non-blocking và bài toán có cần khả năng mở rộng theo hướng đó hay không.
# concatMap để xử lý tuần tự và giữ thứ tự trong Reactor

## 1. Bài toán và kết quả cần đạt

Trong **Spring WebFlux** và **Project Reactor**, ta thường có một **Flux<T>** gồm nhiều phần tử, rồi muốn biến đổi mỗi phần tử thành một tác vụ có thể phát sinh thêm dữ liệu hoặc chạy bất đồng bộ. Ví dụ:

- Nhận các mã đơn hàng theo đúng thứ tự rồi gọi dịch vụ để lấy thông tin từng đơn.
- Ghi lần lượt các thay đổi vào cùng một tài nguyên, cần hoàn thành bước trước mới chuyển sang bước sau.
- Biến đổi mỗi dòng đầu vào thành **Mono<R>** hoặc **Flux<R>**, nhưng không muốn các kết quả từ nhiều dòng xen kẽ.
- Xử lý một danh sách tác vụ mà thứ tự hoàn tất ảnh hưởng đến kết quả nghiệp vụ.

Toán tử **concatMap** giải quyết trường hợp này: **ánh xạ mỗi phần tử upstream thành một Publisher bên trong (inner Publisher), đăng ký và xử lý các inner Publisher theo thứ tự, đợi inner hiện tại kết thúc rồi mới chuyển sang inner tiếp theo**. Vì vậy kết quả downstream giữ thứ tự tương ứng với thứ tự phần tử upstream.

Đây là một toán tử **biến đổi và làm phẳng** (mapping + flattening). Nó không chỉ biến giá trị **T** thành **R** như **map**; nó biến **T** thành một **Publisher<R>** (thường là **Mono<R>** hoặc **Flux<R>**) rồi hợp nhất các phần tử của từng Publisher thành một **Flux<R>** duy nhất, theo thứ tự tuần tự.

Hình dung:

~~~text
Upstream:      A  ─── B ─── C
                │      │     │
concatMap:      f(A)   f(B)  f(C)
                │      │     │
Inner:        [a1 a2] [b1] [c1 c2]
                │      │     │
Downstream:    a1 a2  b1    c1 c2
               └──── chờ từng inner hoàn thành ────┘
~~~

**Điểm quan trọng:** thứ tự ở đây là **thứ tự tín hiệu onNext mà upstream thực tế phát ra**, không phải tự động sắp xếp theo khóa, thời gian tạo bản ghi hoặc thứ tự trong cơ sở dữ liệu.

## 2. Cú pháp và cách đọc pipeline

Với **Flux<T>**, dạng cơ bản:

~~~java
Flux<R> output = source.concatMap(item -> innerPublisher(item));
~~~

Trong đó:

- **source** là **Flux<T>** đầu vào.
- **item** là từng phần tử upstream.
- **innerPublisher(item)** trả về **Publisher<? extends R>**, chẳng hạn **Mono<R>** hoặc **Flux<R>**.
- **output** là **Flux<R>** chứa các giá trị do những inner Publisher phát ra, theo thứ tự của các item đầu vào.

Ví dụ biến từng số thành hai số:

~~~java
Flux.range(1, 3)
    .concatMap(n -> Flux.just(n * 10 + 1, n * 10 + 2))
    .subscribe(System.out::println);
~~~

Kết quả:

~~~text
11
12
21
22
31
32
~~~

Nguồn lần lượt phát **1, 2, 3**. Mỗi phần tử tạo một **Flux** gồm hai giá trị. **concatMap** phát trọn các giá trị từ Flux của **1** trước, rồi Flux của **2**, cuối cùng Flux của **3**. Nếu một inner Publisher rỗng (ví dụ **Mono.empty()**), nó không đóng góp phần tử nào, và concatMap tiếp tục đến item tiếp theo.

Với biến đổi **T → R** đơn giản, đồng bộ, hãy ưu tiên **map**:

~~~java
Flux<Integer> doubled = Flux.range(1, 3)
    .map(n -> n * 2);
~~~

Chỉ chọn **concatMap** khi hàm ánh xạ trả về **Publisher** hoặc khi cần tuần tự hóa việc thực thi các tác vụ reactive.

## 3. Cơ chế tuần tự: một inner Publisher tại một thời điểm

Một cách diễn giải luồng sự kiện:

~~~text
Nguồn phát:       item A          item B          item C
                      │               │               │
concatMap             ▼               │               │
                 subscribe A          │               │
                 onNext(a1)           │               │
                 onNext(a2)           │               │
                 onComplete A         │               │
                                      ▼               │
                                 subscribe B          │
                                 onNext(b1)           │
                                 onComplete B         │
                                                      ▼
                                                 subscribe C
                                                 onNext(c1)
                                                 onComplete C
                                                 onComplete toàn luồng
~~~

Trong thực tế, upstream có thể phát trước hoặc concatMap có thể yêu cầu và lưu tạm một số item trong hàng đợi. **Điều được bảo đảm là các inner Publisher không được đăng ký và phát ra downstream chồng lấn theo cách làm thay đổi thứ tự được concatMap quản lý**: inner sau chỉ bắt đầu sau khi inner trước đã kết thúc. Chi tiết yêu cầu trước (prefetch), hàng đợi và tối ưu scalar phụ thuộc phiên bản Reactor và cấu hình operator.

Đối với mỗi item đầu vào, concatMap:

1. Nhận item và gọi hàm mapper để có inner Publisher tương ứng.
2. Đăng ký vào inner Publisher được chọn.
3. Chuyển các phần tử của inner đó xuống downstream theo đúng thứ tự mà inner phát.
4. Khi inner hoàn thành, chuyển sang item kế tiếp.
5. Khi upstream đã kết thúc và không còn inner đang chạy/hàng đợi còn xử lý, phát **onComplete** cho downstream.

Nếu một inner **không bao giờ hoàn thành** (ví dụ **Flux.never()**), concatMap có thể chờ mãi tại inner đó; các item sau không có cơ hội được xử lý. Vì vậy, với I/O hoặc nguồn ngoài, cần nghĩ tới timeout, xử lý lỗi và cơ chế hủy.

### "Tuần tự" không có nghĩa "mọi mã đều chạy trên một thread"

Một inner có thể làm việc bất đồng bộ trên scheduler hoặc dùng dịch vụ mạng bên ngoài. **concatMap** tuần tự hóa **vòng đời đăng ký/hoàn tất của các inner Publisher mà nó quản lý**; nó không ép mọi callback chạy cùng thread và không biến các tác vụ đã khởi động độc lập thành tác vụ tuần tự. Không dùng lập luận "concatMap nên chắc chắn an toàn thread" để bỏ cơ chế đồng bộ cho tài nguyên được nhiều luồng khác cùng sử dụng.

## 4. So sánh map, flatMap, flatMapSequential và concatMap

| Toán tử | Hàm ánh xạ trả về | Có thể có nhiều inner hoạt động đồng thời? | Trật tự đầu ra | Dùng khi |
| --- | --- | --- | --- | --- |
| **map** | Giá trị **R** | Không có khái niệm inner Publisher | Theo thứ tự upstream | Biến đổi đồng bộ từng phần tử |
| **flatMap** | **Publisher<R>** | **Có**, tùy concurrency | Có thể xen kẽ và đảo thứ tự giữa các inner | Tác vụ độc lập, ưu tiên throughput |
| **flatMapSequential** | **Publisher<R>** | **Có**, đăng ký inner sớm | Giữ thứ tự xuất theo item upstream; có thể đệm kết quả | Muốn concurrency và vẫn giữ thứ tự kết quả |
| **concatMap** | **Publisher<R>** | **Không**, từng inner lần lượt | Giữ thứ tự và các giá trị của từng inner không xen kẽ | Cần thực thi/đăng ký tuần tự, tránh nhiều inner đồng thời |

Giả sử item 1 mất 300 ms, item 2 mất 50 ms và item 3 mất 100 ms:

~~~text
flatMap (các tác vụ được chạy gần đồng thời):
    start 1 ───────────────────── complete 1
    start 2 ──── complete 2
    start 3 ─────────── complete 3
    Thứ tự kết quả có thể là: 2, 3, 1

flatMapSequential (có thể chạy đồng thời, giữ thứ tự phát):
    start 1 ───────────────────── complete 1
    start 2 ──── complete 2 (kết quả được đệm)
    start 3 ─────────── complete 3 (kết quả được đệm)
    Kết quả downstream: 1, 2, 3

concatMap (chờ tác vụ trước kết thúc):
    start 1 ───────────────────── complete 1
                                  start 2 ──── complete 2
                                               start 3 ─────── complete 3
    Kết quả downstream: 1, 2, 3
~~~

Các mốc thời gian ở trên chỉ minh họa, không phải benchmark. **flatMap** không bắt buộc đảo thứ tự; nếu các inner kết thúc đúng thứ tự ban đầu, nó cũng có thể cho kết quả 1, 2, 3. Khác biệt là **không bảo đảm** thứ tự giữa các inner. **flatMapSequential** bảo đảm thứ tự phát ra nhưng **không** bảo đảm từng thao tác phụ được thực thi tuần tự. Nếu mục tiêu nghiệp vụ là “đơn 1 cập nhật xong rồi mới bắt đầu đơn 2”, **concatMap** thường diễn đạt đúng hơn.

**concat** hoặc **concatWith** ghép những Publisher đã được xác định; **concatMap** dùng mapper để tạo Publisher dựa trên từng item upstream. Chúng cùng mang ý tưởng nối tiếp nhưng có đầu vào API khác nhau.

## 5. Ví dụ có tác vụ bất đồng bộ: thứ tự không bị đảo

Ví dụ sau dùng **Mono.delay** để mô phỏng một công việc hoàn thành sau một khoảng thời gian; mặc dù công việc chạy qua scheduler, concatMap vẫn đợi từng inner hoàn thành:

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        Mono.delay(Duration.ofMillis(id == 1 ? 200 : 40))
            .map(tick -> "result-" + id)
    )
    .subscribe(System.out::println);
~~~

Đoạn trên minh họa trong môi trường đã có Reactor, cần import **Flux**, **Mono** và **Duration**. **subscribe** không giữ chương trình CLI chờ một nguồn async; trong ví dụ đầy đủ ở phần 8 sẽ dùng **blockLast()** tại ranh giới chương trình để quan sát đầy đủ output.

Dù item 1 mất nhiều thời gian hơn item 2, concatMap chỉ bắt đầu đăng ký inner của item 2 sau khi inner của item 1 kết thúc. Vì vậy kết quả sẽ theo thứ tự:

~~~text
result-1
result-2
result-3
~~~

Điều này đặc biệt hữu ích khi thứ tự là một yêu cầu nghiệp vụ. Đổi thành **flatMap** thì các inner có thể cùng được đăng ký, và phần tử hoàn thành sớm có thể xuất hiện trước.

## 6. "Giữ thứ tự" cần hiểu chính xác

concatMap giữ thứ tự của **những item mà nó nhận được**. Nó không tự giải quyết các vấn đề thứ tự ở ngoài phạm vi operator.

**Nguồn có thứ tự không xác định:** nếu dữ liệu đến từ truy vấn SQL không có **ORDER BY**, API stream nhiều partition hoặc các producer chạy song song, thứ tự onNext có thể khác nhau giữa các lần chạy. concatMap vẫn giữ *thứ tự thực tế đó*, không suy ra thứ tự theo id.

**Một item tạo nhiều giá trị:** nếu item A trả về **Flux(A1, A2)** và B trả về **Flux(B1, B2)**, đầu ra là **A1, A2, B1, B2**, không xen kẽ A1, B1, A2, B2.

**Một item trả về Mono.empty():** item đó tạo 0 giá trị nhưng không ngăn item tiếp theo. Do vậy, giữ thứ tự không có nghĩa đầu ra phải có cùng số lượng phần tử với đầu vào.

**Mapper trả về Mono.error/Flux.error:** mặc định lỗi từ inner kết thúc toàn bộ chuỗi qua **onError**; chưa chắc các item sau được xử lý. Phải có chiến lược phục hồi rõ ràng nếu muốn tiếp tục.

**Công việc đã khởi động ngoài chuỗi:** nếu trước khi gọi concatMap bạn đã khởi tạo và chạy nhiều **CompletableFuture**, HTTP request hay side effect, việc ghép các kết quả bằng concatMap không khiến các công việc đó bắt đầu tuần tự. Hãy tạo công việc lười (lazy) bên trong mapper/Mono.defer nếu thứ tự bắt đầu có ý nghĩa.

Ví dụ nguy cơ:

~~~java
// Các công việc được tạo và có thể đã bắt đầu trước khi concatMap.
List<CompletableFuture<Result>> started = startAllRequests();

Flux.fromIterable(started)
    .concatMap(future -> Mono.fromFuture(future));
~~~

Đoạn này là pseudocode có kiểu giả định **Result** và hàm **startAllRequests**. Nó chỉ tuần tự hóa việc lấy kết quả của những Future đã tồn tại, không tuần tự hóa quá trình gửi request. Nếu thực sự cần từng request chỉ bắt đầu sau khi request trước hoàn tất, hãy tổ chức **Flux** từ các item đầu vào và **tạo Mono cho request bên trong mapper**.

## 7. Lỗi, timeout và hủy

### 7.1. Hành vi mặc định: lỗi làm dừng pipeline

~~~java
Flux.just(1, 2, 3)
    .concatMap(id -> {
        if (id == 2) {
            return Mono.<String>error(
                new IllegalArgumentException("invalid id: 2")
            );
        }
        return Mono.just("ok-" + id);
    })
    .subscribe(
        System.out::println,
        error -> System.out.println("error: " + error.getMessage())
    );
~~~

Đầu ra:

~~~text
ok-1
error: invalid id: 2
~~~

Không có **ok-3**, vì lỗi tại inner của id 2 là **terminal signal** của cả pipeline. Như vậy, concatMap **giữ thứ tự các phần tử thực sự đã phát ra**, nhưng không có nghĩa nó luôn xử lý đủ mọi item đầu vào sau khi lỗi.

### 7.2. Muốn tiếp tục từng item: phục hồi bên trong mapper

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        callService(id)
            .onErrorResume(error -> {
                logFailure(id, error);
                return Mono.just(fallbackFor(id));
            })
    );
~~~

Đây là snippet giả định các hàm **callService**, **logFailure**, **fallbackFor** đã được định nghĩa; **callService(id)** trả về **Mono<Result>** và **fallbackFor(id)** trả về **Result**. Khi lỗi được đổi thành fallback **ngay trong inner**, inner vẫn hoàn thành bình thường và concatMap tiếp tục xử lý item kế tiếp. Nếu không muốn phát giá trị thay thế, có thể phục hồi bằng **Mono.empty()** (lúc này item lỗi không đóng góp dữ liệu).

Ngược lại:

~~~java
source.concatMap(this::callService)
    .onErrorResume(error -> Flux.just(fallbackValue));
~~~

Operator **onErrorResume** nằm *sau concatMap* chỉ thay thế phần còn lại của một pipeline đã lỗi; nó **không quay lại** để tiếp tục những item upstream chưa được xử lý. Vị trí xử lý lỗi quyết định hành vi.

Reactor cũng có các biến thể như **concatMapDelayError** để trì hoãn việc chuyển lỗi xuống downstream theo hợp đồng riêng. Đây là lựa chọn khác với việc phục hồi từng item; đừng mặc định rằng delay error sẽ biến một inner thất bại thành giá trị thành công hoặc luôn tiếp tục vô điều kiện. Hãy chọn cụ thể dựa trên yêu cầu nghiệp vụ về lỗi.

### 7.3. Tránh một inner treo vô hạn

~~~java
Flux.just(1, 2, 3)
    .concatMap(id ->
        callService(id)
            .timeout(Duration.ofSeconds(3))
            .onErrorResume(error -> fallbackMono(id, error))
    );
~~~

Snippet giả định **callService** và **fallbackMono** trả về **Mono<Result>**. Nếu inner bị timeout, nó chuyển sang đường lỗi để tạo fallback, nhờ đó item tiếp theo không bị chờ vô hạn. Thời hạn 3 giây ở đây chỉ là giá trị minh họa; phải dựa vào SLA, đặc tính nguồn và chính sách retry của ứng dụng.

Một inner **Flux.never()** hoặc một yêu cầu I/O không phản hồi sẽ khóa tiến trình của concatMap nếu không có cơ chế kết thúc. Dùng **timeout**, giới hạn tài nguyên và deadline khi phù hợp.

### 7.4. Cancellation không đồng nghĩa completion

Khi downstream hủy subscription (ví dụ client ngắt kết nối WebFlux, hoặc dùng **Disposable.dispose()**), concatMap sẽ yêu cầu hủy subscription upstream và inner đang hoạt động. Các item còn nằm trong hàng đợi có thể bị bỏ, còn công việc ngoài hệ thống đã khởi động chưa chắc được hoàn tác. **cancel** không tự phát **onComplete**.

Để quan sát lý do kết thúc và dọn dẹp tài nguyên:

~~~java
Flux<Result> flow = source
    .concatMap(this::callService)
    .doFinally(signalType -> log("terminated: " + signalType));
~~~

Đây là snippet có các hàm/kiểu ứng dụng giả định. **doFinally** quan sát các trường hợp như **ON_COMPLETE**, **ON_ERROR** hoặc **CANCEL**. Không tự gọi **subscribe()** trong controller WebFlux chỉ để ghi log; trả về pipeline để framework quản lý subscription.

## 8. Ví dụ Java 17+ chạy được với Maven và Reactor

Để có output nhất quán, chương trình dùng các nguồn **Flux.just/Flux.range** đồng bộ và **Mono.delay** bất đồng bộ nhưng chờ kết quả bằng **blockLast()** tại phương thức **main**. **blockLast()** trong ví dụ CLI có chủ đích; không dùng cách này trên event-loop của WebFlux.

Cấu trúc dự án:

~~~text
concatmap-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ConcatMapDemo.java
~~~

Tệp **pom.xml** (ví dụ sử dụng API ổn định của Reactor 3.6.6):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>concatmap-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tệp **src/main/java/ConcatMapDemo.java**:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ConcatMapDemo {

    public static void main(String[] args) {
        System.out.println("=== 1. Flatten in order ===");

        Flux.range(1, 3)
            .concatMap(id -> Flux.just(id * 10 + 1, id * 10 + 2))
            .doOnNext(System.out::println)
            .blockLast();

        System.out.println("=== 2. Async, one inner at a time ===");

        Flux.just(1, 2, 3)
            .concatMap(id ->
                Mono.delay(Duration.ofMillis(id == 1 ? 120 : 20))
                    .doOnSubscribe(s ->
                        System.out.println("start " + id)
                    )
                    .map(tick -> "item-" + id)
                    .doOnNext(item ->
                        System.out.println("finish " + id)
                    )
            )
            .doOnNext(item -> System.out.println("receive " + item))
            .blockLast();

        System.out.println("=== 3. Recover each inner ===");

        Flux.just(1, 2, 3)
            .concatMap(id -> {
                if (id == 2) {
                    return Mono.<String>error(
                            new IllegalArgumentException("invalid")
                        )
                        .onErrorResume(error ->
                            Mono.just("fallback-" + id)
                        );
                }
                return Mono.just("ok-" + id);
            })
            .doOnNext(System.out::println)
            .blockLast();
    }
}
~~~

Trong thư mục **concatmap-demo**, cần JDK 17+ và Maven. Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ConcatMapDemo
~~~

Stdout mong đợi:

~~~text
=== 1. Flatten in order ===
11
12
21
22
31
32
=== 2. Async, one inner at a time ===
start 1
finish 1
receive item-1
start 2
finish 2
receive item-2
start 3
finish 3
receive item-3
=== 3. Recover each inner ===
ok-1
fallback-2
ok-3
~~~

Giải thích:

- **Phần 1:** mỗi số tạo một Flux hai phần tử; concatMap xuất toàn bộ phần tử của inner 1, rồi inner 2, rồi inner 3.
- **Phần 2:** item 1 cần khoảng 120 ms, item 2 và 3 khoảng 20 ms. Mỗi dòng **start** xuất hiện sau khi inner trước có tín hiệu hoàn tất; callback **finish/receive** hiển thị thứ tự dữ liệu. Thời lượng thực tế tùy scheduler, nhưng thứ tự vẫn được bảo đảm.
- **Phần 3:** lỗi của id 2 được phục hồi ngay trong inner, tạo **fallback-2**, rồi tiếp tục đến **ok-3**. Nếu chuyển **onErrorResume** ra sau concatMap, hành vi không tương đương.
- **blockLast()** chỉ để giữ chương trình CLI chờ lần đăng ký và hoàn tất. Trong ứng dụng Spring WebFlux, nên trả về Mono/Flux cho framework, tránh gọi block trên event-loop.

Ví dụ không dựa vào thứ tự hoàn thành giữa các tác vụ chạy song song: chính concatMap quyết định chỉ xử lý lần lượt từng inner.

## 9. Ứng dụng Spring WebFlux: xử lý tác vụ theo thứ tự

Giả sử một ứng dụng nhận **Flux<OrderId>** đã được sắp theo thứ tự mong muốn. Mỗi mã cần gọi một dịch vụ qua **WebClient**:

~~~java
public Flux<OrderDetails> fetchInOrder(Flux<OrderId> orderedIds) {
    return orderedIds.concatMap(id ->
        webClient.get()
            .uri("/orders/{id}", id.value())
            .retrieve()
            .bodyToMono(OrderDetails.class)
    );
}
~~~

Đây là snippet trong một Spring bean có **webClient** được cấu hình, với các kiểu ứng dụng giả định **OrderId** và **OrderDetails**. **WebClient** trả về **Mono<OrderDetails>**. Khi dữ liệu được đăng ký, ứng dụng bắt đầu request tiếp theo sau khi inner request trước kết thúc và phát kết quả theo thứ tự đầu vào.

Không nhất thiết đây luôn là lựa chọn nhanh nhất: nếu mỗi request chờ mạng 200 ms và có 100 phần tử, thời gian chờ cộng dồn có thể lớn. Nếu yêu cầu chỉ là **kết quả ra đúng thứ tự** mà các request độc lập có thể chạy đồng thời, hãy xem xét **flatMapSequential** với giới hạn concurrency phù hợp; nếu không cần thứ tự, **flatMap** có thể cho throughput tốt hơn.

### 9.1. Quy tắc giữ thứ tự phải bắt đầu từ nguồn

Nếu **orderedIds** lấy từ cơ sở dữ liệu, mã nguồn phải yêu cầu thứ tự rõ ràng, chẳng hạn truy vấn có **ORDER BY position, id** nếu phù hợp nghiệp vụ. Reactor không tự sắp xếp các bản ghi từ query không xác định thứ tự. Nếu upstream nhận sự kiện từ nhiều producer, cần thiết kế cách đánh số thứ tự, tái sắp xếp hoặc phân vùng phù hợp trước khi concatMap.

### 9.2. Không subscribe lồng nhau

Sai về ý định quản lý chuỗi:

~~~java
// Sai: inner là một side effect được khởi động độc lập.
return orderedIds.concatMap(id -> {
    callService(id).subscribe(result -> save(result).subscribe());
    return Mono.just(id);
});
~~~

Đây là ví dụ minh họa lỗi kiến trúc với các phương thức giả định. **concatMap** ở ngoài chỉ chờ **Mono.just(id)**, **không chờ callService/save** đã được subscribe thủ công. Kết quả là thứ tự công việc thực không được bảo đảm, lỗi bị tách khỏi chuỗi và hủy subscription ngoài không nhất thiết hủy các tác vụ bên trong.

Cách ghép đúng:

~~~java
return orderedIds.concatMap(id ->
    callService(id)
        .flatMap(result -> save(result).thenReturn(id))
);
~~~

Ví dụ giả định **callService** trả về **Mono<Result>**, **save** trả về một Publisher hoàn thành khi lưu xong, và kết quả mong muốn là id. **concatMap** chỉ chuyển sang id mới khi cả **callService** lẫn **save** thuộc inner hiện tại đã hoàn tất. **flatMap** được dùng *bên trong một inner* để nối hai giai đoạn, không vi phạm nguyên tắc tuần tự hóa giữa các id của concatMap.

### 9.3. Thứ tự không thay thế transaction, tính idempotent hoặc kiểm soát đồng thời

Nếu nhiều HTTP request khác nhau cùng gọi một service, chúng có **những subscription độc lập**. concatMap trên một request chỉ tuần tự hóa các inner bên trong request đó; không tự áp đặt một hàng đợi toàn cục trên mọi request hoặc mọi instance ứng dụng. Khi cùng cập nhật dữ liệu chung, vẫn cần transaction, kiểm soát optimistic locking, idempotency key hoặc thiết kế hàng đợi phù hợp.

Tương tự, khi nhận sự kiện từ nguồn hot có tốc độ cao, yêu cầu tuần tự hóa có thể tạo **độ trễ tăng dần**. Cần đánh giá sức chứa, timeout, chính sách backpressure, tốc độ đầu vào và khả năng mở rộng; không coi concatMap là bộ lưu trữ bền vững.

## 10. Backpressure, bộ đệm và hiệu năng

**Reactive Streams** dùng **request(n)** để downstream điều khiển nhu cầu nhận dữ liệu. concatMap tham gia cơ chế này và có thể yêu cầu trước/đệm item upstream tùy cấu hình, nhưng vẫn phải tuân thủ demand downstream. Vì vậy:

- **Một inner hoạt động tại một thời điểm** không đồng nghĩa **bộ nhớ sử dụng luôn bằng O(1)**: upstream, inner, scheduler và các operator khác có thể có hàng đợi/bộ đệm.
- **Số item đã nhận từ upstream** có thể lớn hơn số item đã được chuyển xuống downstream tại một thời điểm. Đừng dùng số lượng log onNext ở một vị trí để suy ra toàn bộ demand pipeline.
- **Inner phát nhiều phần tử**: mọi phần tử của inner hiện tại phải tuân thủ demand downstream và được xử lý trước khi nội dung inner kế tiếp xuất hiện.
- **Inner xử lý chậm** làm những item phía sau phải đợi, dù các item sau có thể hoàn thành sớm nếu chạy song song.
- **Retry** là một chính sách độc lập. Nếu đặt **retryWhen** trong mapper, concatMap chờ các lần thử lại của inner hiện tại; nếu đặt ở ngoài, retry có thể đăng ký lại một phần pipeline và làm lặp những side effect trước đó.

Khi tối ưu, cần chọn theo điều kiện thực tế:

| Yêu cầu | Lựa chọn ban đầu |
| --- | --- |
| Biến đổi đồng bộ, không tạo Publisher | **map** |
| Các thao tác phải thực sự chờ nhau để tránh cập nhật sai thứ tự | **concatMap** |
| Có thể chạy đồng thời nhưng giao diện phải xuất kết quả đúng thứ tự | **flatMapSequential** với concurrency giới hạn |
| Không quan trọng thứ tự, muốn dùng I/O concurrency | **flatMap** với concurrency giới hạn |
| Ghép trực tiếp một số Publisher đã biết | **concat**, **concatWith** |

Để đo hiệu năng, quan sát **latency tổng**, **số tác vụ đồng thời**, **hàng đợi**, **độ trễ p95/p99** và **lỗi** dưới tải thực tế. Đừng dùng một ví dụ vài item với **Mono.delay** làm thước đo throughput của WebClient hoặc cơ sở dữ liệu.

## 11. Những lỗi tư duy thường gặp

| Nhận định sai hoặc triệu chứng | Cách hiểu và hướng xử lý |
| --- | --- |
| "concatMap luôn nhanh hơn flatMap vì không tranh chấp" | Chạy tuần tự thường **giảm concurrency**; hiệu quả phụ thuộc phụ tải và yêu cầu thứ tự. |
| "concatMap tự sort theo id" | Nó giữ thứ tự **onNext của upstream**, không tự sắp xếp theo khóa. |
| "flatMapSequential cũng xử lý tuần tự" | Nó có thể subscribe nhiều inner cùng lúc rồi **đệm kết quả** để phát đúng thứ tự. |
| "concatMap bảo đảm side effect ngoài Mono chạy tuần tự" | Chỉ công việc được mô hình hóa trong các inner Publisher và được subscribe đúng vòng đời mới chịu sự tuần tự hóa của operator. |
| "Một Mono lỗi thì concatMap vẫn tự xử lý item tiếp theo" | Mặc định lỗi dừng chuỗi; cần phục hồi per-inner hoặc chọn biến thể delay-error phù hợp. |
| "onErrorResume sau concatMap cho phép tiếp tục phần tử còn lại" | Nó thay phần tail của chuỗi đã lỗi; đặt recovery **bên trong mapper** để tiếp tục từng item. |
| "concatMap không cần timeout" | Một inner không bao giờ kết thúc có thể chặn mọi inner phía sau. |
| "Chỉ một inner có nghĩa không cần quan tâm bộ đệm" | Upstream/operator khác có thể prefetch, queue hoặc giữ dữ liệu. |
| "Dùng concatMap để sửa race condition giữa mọi user" | Các subscription/request khác vẫn có thể hoạt động đồng thời. Cần kiểm soát dữ liệu chung riêng. |
| "Có thể subscribe lồng rồi trả Mono.just" | concatMap chỉ chờ Publisher được **trả về từ mapper**, không chờ side effect đã subscribe ngoài chuỗi. |
| "Dùng blockLast trong controller để chờ kết quả" | WebFlux nên trả pipeline; blocking trên event-loop làm nghẽn xử lý I/O. |

## 12. Bài tập thực hành và tự kiểm tra

**Bài 1 – Dự đoán thứ tự.** Cho:

~~~java
Flux.just("A", "B")
    .concatMap(s -> Flux.just(s + "1", s + "2"))
    .subscribe(System.out::println);
~~~

Kết quả là **A1, A2, B1, B2**. Giải thích: mỗi inner phát hai phần tử, concatMap hoàn tất inner A trước khi bắt đầu inner B.

**Bài 2 – Nguồn rỗng.** Nếu mapper trả **Mono.empty()** cho B trong nguồn A, B, C, đầu ra sẽ như thế nào?  
**Đáp án:** không có phần tử cho B, nhưng concatMap tiếp tục sang C sau khi Mono.empty hoàn tất.

**Bài 3 – Lỗi tại B.** Nếu B trả **Mono.error**, liệu C có được xử lý không?  
**Đáp án:** theo mặc định, không. Muốn tiếp tục C, dùng recovery trong inner B hoặc một cơ chế xử lý lỗi được lựa chọn có chủ đích.

**Bài 4 – Thứ tự so với tốc độ.** Khi nhận danh sách 100 request GET độc lập, chỉ cần **trả kết quả đúng thứ tự**, có bắt buộc dùng concatMap không?  
**Đáp án:** không. **flatMapSequential** cho phép các request được chạy đồng thời nhưng kết quả được phát theo thứ tự, đổi lại có nguy cơ đệm kết quả chờ request chậm ở đầu.

**Bài 5 – Side effect ẩn.** Nguồn có ba CompletableFuture đã bắt đầu từ trước; đưa chúng vào concatMap có chắc các công việc bắt đầu tuần tự không?  
**Đáp án:** không. Cần tạo công việc lazily trong mapper hoặc Mono.defer để quản lý đúng thời điểm bắt đầu.

**Bài 6 – Thực nghiệm.** Sửa ví dụ Java ở phần 8: thay **concatMap** bằng **flatMap** tại phần 2 và tăng khác biệt thời gian delay; chạy nhiều lần và quan sát. Tiếp tục thay bằng **flatMapSequential**. Hãy ghi lại hai thứ riêng biệt: **thứ tự start/finish** của inner và **thứ tự receive** downstream. Từ đó giải thích vì sao "giữ thứ tự output" khác với "thực thi tuần tự".

## 13. Ghi nhớ khi thiết kế pipeline

Câu hỏi lựa chọn thực tế: **"Item tiếp theo có được phép bắt đầu công việc trước khi item hiện tại hoàn thành không?"** Nếu **không**, **concatMap** là toán tử phù hợp để biểu diễn chuỗi các inner Publisher. Nếu **có**, hãy cân nhắc **flatMapSequential** hoặc **flatMap** tùy yêu cầu thứ tự đầu ra.

Khi dùng concatMap, kiểm tra đủ bốn điểm: **nguồn upstream có thứ tự mong muốn**, **mọi side effect cần chờ đều nằm trong Publisher được trả từ mapper**, **lỗi/timeout/cancel được xử lý theo nghiệp vụ**, và **độ trễ/bộ đệm được quan sát dưới tải**. Tuân thủ các điểm này giúp giữ đúng cả thứ tự dữ liệu lẫn ranh giới vòng đời của tác vụ.

## 14. Tài liệu tham khảo

- Project Reactor — Transforming Sequences, API operator choices: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor — Flux.concatMap API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor — Backpressure and subscribe: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Spring Framework — Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
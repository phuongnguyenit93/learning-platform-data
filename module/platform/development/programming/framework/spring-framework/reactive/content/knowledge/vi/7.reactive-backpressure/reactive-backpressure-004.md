# limitRate và sự khác biệt với giới hạn yêu cầu theo thời gian

## 1. Một tên gọi, hai khái niệm khác nhau

Trong Project Reactor, **Flux.limitRate** là toán tử điều chỉnh tín hiệu **backpressure**: nó chia nhu cầu nhận phần tử (demand) từ downstream thành các **lô yêu cầu nhỏ hơn** khi chuyển ngược lên upstream. Đây là cơ chế điều phối số phần tử giữa Publisher và Subscriber.

Trong các hệ thống HTTP, **rate limiting theo thời gian** lại có nghĩa khác: ví dụ tối đa **10 HTTP requests/giây** hoặc **600 requests/phút** theo một API key. Cơ chế này phải theo dõi thời gian, xác định người/nhóm dùng quota và quyết định cho phép, đợi hay từ chối từng thao tác.

**Điểm chính: Flux.limitRate(10) không có nghĩa 10 phần tử/giây, không có nghĩa 10 HTTP requests/giây và không có nghĩa chỉ lấy tổng cộng 10 phần tử.**

Ba nhóm giới hạn dễ bị nhầm:

| Nhóm giới hạn | Đơn vị | Câu hỏi cần giải quyết | Ví dụ |
| --- | --- | --- | --- |
| **Backpressure / demand** | Phần tử trên mỗi lần request | Upstream được yêu cầu phát thêm tối đa bao nhiêu phần tử? | Flux.limitRate(10, 0) |
| **Concurrency** | Công việc đang hoạt động đồng thời | Có bao nhiêu HTTP call hoặc Publisher con được thực thi cùng lúc? | flatMap(mapper, 4) |
| **Rate limit theo thời gian** | Thao tác / giây, phút hoặc cửa sổ | Một API key được bắt đầu bao nhiêu request trong một khoảng thời gian? | Token bucket 20 calls/s |

Có thể cần cả ba nhóm trong cùng ứng dụng. Chúng có mục đích và ranh giới hoạt động khác nhau.

## 2. Nhắc lại hợp đồng Reactive Streams

Reactive Streams quy định các interface **Publisher**, **Subscriber**, **Subscription** và **Processor**. Một Subscriber sau khi nhận Subscription có thể gọi:

~~~java
subscription.request(5);
~~~

Lời gọi này cấp thêm **demand cho tối đa năm phần tử**, chứ không yêu cầu phát đúng năm phần tử ngay tức thì. Publisher có thể phát ít hơn nếu dữ liệu chưa sẵn sàng hoặc luồng đã hoàn tất.

~~~text
Subscriber                               Publisher
    |                                        |
    |----------- subscribe() -------------->|
    |<---------- onSubscribe(s) ------------|
    |----------- s.request(5) ------------->|
    |<---------- onNext(item1) -------------|
    |<---------- onNext(item2) -------------|
    |                  ...                   |
    |<---------- onNext(item5) -------------|
    |----------- s.request(5) ------------->|
    |                  ...                   |
~~~

Các nguyên tắc cần nhớ:

- **request(n)** đếm **phần tử** chứ không đếm byte, packet, lần truy vấn database hay HTTP request.
- Demand có thể được cộng dồn giữa các lời gọi; **Long.MAX_VALUE** biểu thị nhu cầu không giới hạn về số lượng phần tử.
- Source tuân thủ đặc tả không được gửi onNext vượt demand đã cấp cho subscription.
- Các toán tử ở giữa có quyền **biến đổi demand**. Ví dụ buffer(10) phải yêu cầu nhiều phần tử gốc hơn để hình thành một buffer.
- Cancellation, lỗi và hoàn tất kết thúc vòng đời subscription phù hợp với hợp đồng.
- Demand không chứa thông tin về **giây/phút** và cũng không tự tạo scheduler hay thread.

Khi downstream muốn nhận tất cả, nhiều kiểu tiêu thụ như subscribe() thông thường hoặc collectList().block() sẽ gửi **Long.MAX_VALUE**; vì thế việc điều tiết upstream demand có thể có ích với những nguồn không nên xử lý yêu cầu quá lớn một lần.

## 3. Flux.limitRate vận hành ở đâu?

Hai overload thường dùng:

~~~java
Flux<T> limitRate(int prefetchRate);
Flux<T> limitRate(int highTide, int lowTide);
~~~

Giả sử có nguồn phát 100 số nguyên và downstream muốn nhận toàn bộ:

~~~java
Flux<Integer> values = Flux.range(1, 100)
                           .limitRate(10);
~~~

**limitRate(10)** giới hạn kích thước các đợt request chuyển tới upstream; nó **không dừng ở phần tử thứ 10**. Nếu không có lỗi/hủy và downstream tiếp tục có nhu cầu, cả 100 số có thể được phát hết.

Vị trí trong pipeline:

~~~text
[Subscriber ở downstream]
    |
    | request(Long.MAX_VALUE)
    v
[limitRate(4, 0)]
    |
    | request(4) -> nhận một lô
    | request(4) -> nhận lô kế tiếp
    | request(4) -> tiếp tục nếu cần
    v
[Upstream Publisher]
~~~

Sơ đồ mô tả **demand**, không mô tả khoảng cách thời gian. Những đợt request có thể diễn ra cực nhanh nếu nguồn và consumer cùng nhanh. Không có bước “đợi một giây”.

Lợi ích thường gặp:

- Chia yêu cầu không giới hạn thành các đợt mà upstream quản lý dễ hơn.
- Tuning cơ chế prefetch và cấp bổ sung demand trong một pipeline.
- Hạn chế cách một nguồn bị yêu cầu kéo quá nhiều phần tử cùng một lúc nếu nguồn tôn trọng backpressure.
- Quan sát và tối ưu việc yêu cầu dữ liệu từ một adapter, kho dữ liệu hoặc nguồn xử lý theo lô.

Các giới hạn: **limitRate không tự tạo quota HTTP**, không quyết định latency, không cam kết tổng bộ nhớ dưới highTide và không bảo đảm một Publisher không tuân thủ backpressure sẽ trở nên compliant chỉ nhờ bọc toán tử này.

## 4. highTide, lowTide và replenishment

### highTide: mức request upstream theo đợt

Trong cách gọi **limitRate(highTide, lowTide)**, highTide là mức cao của một đợt demand truyền lên nguồn.

Ví dụ:

~~~java
Flux<Integer> source = Flux.range(1, 100)
                           .limitRate(8, 0);
~~~

Ở chế độ strict này, mỗi đợt có thể yêu cầu tám phần tử. Nguồn 100 phần tử không bị giới hạn tổng cộng tám phần tử; demand được bổ sung theo các đợt khi subscription còn cần thêm dữ liệu.

### lowTide: chiến lược cấp demand bổ sung

**limitRate(8)** một tham số dùng chiến lược **prefetch-and-replenish**: khi khoảng 75% của lượng yêu cầu ban đầu đã được tiêu thụ, operator chủ động yêu cầu bổ sung upstream. Mục tiêu là không phải đợi tới khi lô cũ hoàn toàn cạn rồi mới xin thêm.

**limitRate(highTide, lowTide)** cho phép điều chỉnh chiến lược bổ sung demand. Nếu **lowTide = 0**, Reactor dùng **strict batches** theo highTide, không dùng cách replenishment chủ động như overload mặc định.

~~~java
Flux<Integer> eagerReplenishment = Flux.range(1, 100)
                                      .limitRate(8);

Flux<Integer> strictBatches = Flux.range(1, 100)
                                 .limitRate(8, 0);
~~~

Hai stream đều có thể phát toàn bộ 100 phần tử. Khác biệt là **khi nào và bằng cách nào upstream nhận các tín hiệu request(n)**. Số lần gọi và độ lớn từng request khi có lowTide khác 0 còn phụ thuộc demand downstream, số phần tử được tiêu thụ và các operator khác.

Không diễn giải **limitRate(8, 2)** thành “8 phần tử mỗi 2 giây”. **lowTide không mang đơn vị thời gian.**

### Vì sao không luôn chọn highTide thật nhỏ?

Một lô quá nhỏ có thể làm tăng số lần request và chi phí điều phối, ảnh hưởng throughput. Một lô quá lớn có thể khiến nguồn tải hoặc chuẩn bị nhiều phần tử hơn cần thiết, tăng áp lực buffer/tài nguyên. Giá trị phù hợp được xác định qua **profiling**, không phải một quy tắc cố định.

## 5. Ví dụ với chín phần tử: không mất phần tử nào

Với nguồn đồng bộ gồm 9 phần tử và **limitRate(4, 0)**:

~~~text
Nguồn: [1, 2, 3, 4, 5, 6, 7, 8, 9]

Downstream yêu cầu toàn bộ
          |
          v
request(4): nguồn phát 1, 2, 3, 4
request(4): nguồn phát 5, 6, 7, 8
request(4): nguồn phát 9, hoàn tất

Downstream thu: [1, 2, 3, 4, 5, 6, 7, 8, 9]
~~~

Đợt cuối không nhất thiết có đủ bốn phần tử vì nguồn đã hết. **Tổng phần tử là chín, không phải bốn.** Và vì không hề định nghĩa thời gian, cả chín phần tử có thể được xử lý rất nhanh trên cùng một thread khi mọi thành phần đều đồng bộ.

Trong pipeline phức tạp, những operator như flatMap, buffer hoặc publishOn có thể tạo yêu cầu bổ sung và thay đổi trace. Sơ đồ này diễn tả trường hợp đơn giản có **strict batch** để người học nhìn thấy cơ chế.

## 6. Chương trình Java 17+ chạy được

Chương trình sau ghi lại các tín hiệu request ở hai phía của limitRate để thấy chúng khác nhau. Sau đó so sánh với take(4) và một stream có độ trễ theo thời gian.

Cần **JDK 17+** và **Maven 3.9+**.

Cấu trúc:

~~~text
reactor-demand-demo/
  pom.xml
  src/main/java/example/DemandVsTimeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-demand-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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

**src/main/java/example/DemandVsTimeDemo.java**:

~~~java
package example;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class DemandVsTimeDemo {
    public static void main(String[] args) {
        List<Long> upstreamRequests = new ArrayList<>();
        List<Long> downstreamRequests = new ArrayList<>();

        List<Integer> numbers = Flux.range(1, 9)
                .doOnRequest(upstreamRequests::add)
                .limitRate(4, 0)
                .doOnRequest(downstreamRequests::add)
                .collectList()
                .block();

        System.out.println("downstream=" + downstreamRequests);
        System.out.println("upstream=" + upstreamRequests);
        System.out.println("numbers=" + numbers);

        List<Integer> onlyFour = Flux.range(1, 9)
                .take(4)
                .collectList()
                .block();

        System.out.println("take(4)=" + onlyFour);

        List<Integer> delayed = Flux.range(1, 3)
                .concatMap(n -> Mono.delay(Duration.ofMillis(100))
                                    .thenReturn(n))
                .collectList()
                .block();

        System.out.println("delayed=" + delayed);
    }
}
~~~

Chạy trong thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.DemandVsTimeDemo
~~~

**Các dòng do chương trình in** với nguồn Flux.range đồng bộ:

~~~text
downstream=[9223372036854775807]
upstream=[4, 4, 4]
numbers=[1, 2, 3, 4, 5, 6, 7, 8, 9]
take(4)=[1, 2, 3, 4]
delayed=[1, 2, 3]
~~~

Giải thích:

1. **collectList()** thu toàn bộ nguồn, nên phía downstream của limitRate gửi demand **Long.MAX_VALUE** (9223372036854775807).
2. **limitRate(4, 0)** chia demand truyền lên nguồn thành các đợt bốn phần tử; với chín phần tử cần ba đợt.
3. **numbers** vẫn chứa **đủ chín** phần tử, chứng minh limitRate không giới hạn tổng lượng.
4. **take(4)** giới hạn tổng số phần tử còn bốn; đây là một operator khác.
5. **Mono.delay** tạo độ trễ thời gian ở từng Publisher con. **concatMap** đợi từng publisher con hoàn tất theo thứ tự, vì vậy phần delay vận hành tuần tự cho một subscription. Kết quả dữ liệu vẫn là 1, 2, 3.

Các khoảng delay có thể dao động do Scheduler và tải máy; output chỉ in giá trị, không khẳng định đúng tuyệt đối số millisecond. **block()** dùng tại ranh giới CLI để quan sát kết quả; tránh đặt block() trong xử lý request WebFlux hoặc thread event-loop.

Đối với pipeline có nguồn async, prefetch, hủy subscription hoặc operator phức tạp, trace request(n) có thể khác về thời điểm và số lượng. Không giả định mẫu [4,4,4] là một lời hứa cho mọi nguồn.

## 7. Khác biệt với giới hạn tổng phần tử: take(n)

~~~java
Flux<Integer> all = Flux.range(1, 100).limitRate(10);
Flux<Integer> firstTen = Flux.range(1, 100).take(10);
~~~

- **all** có thể phát cả 100 phần tử; limitRate chỉ đổi cách yêu cầu từng lô.
- **firstTen** phát tối đa 10 phần tử, rồi hoàn tất và thực hiện cancellation upstream khi phù hợp.

Một số tài liệu Reactor cũ đề cập **limitRequest(n)** cho giới hạn tổng demand; ở các phiên bản Reactor hiện đại, toán tử đó đã deprecated, và **take(n)** là lựa chọn thích hợp để giới hạn tổng phần tử.

Không nhầm:

~~~text
limitRate(10) : Điều tiết demand theo các lô, có thể nhận 100/100.
take(10)      : Dừng sau tối đa 10 phần tử, nhận 10/100.
~~~

Đây là hai nhu cầu hoàn toàn khác nhau. Tương tự, **take(Duration)** kết thúc luồng theo khoảng thời gian, nhưng không tự biến thành một quota số request/giây cho API.

## 8. Rate limiting theo thời gian hoạt động ra sao?

Giới hạn theo thời gian phải định nghĩa ít nhất bốn điều:

1. **Đối tượng được đếm**: HTTP request, lần gửi email, lần truy vấn, event hay thao tác khác.
2. **Phạm vi quota**: toàn ứng dụng, theo API key, user, tenant, IP hay route.
3. **Đơn vị thời gian và burst**: ví dụ 60/phút, 5/giây, có cho phép đột biến ngắn không.
4. **Chính sách khi hết quota**: chờ trong giới hạn, từ chối bằng HTTP 429, hoặc đưa công việc vào hàng đợi hữu hạn.

Một số thuật toán phổ biến:

| Cơ chế | Ý tưởng | Lưu ý |
| --- | --- | --- |
| **Fixed window counter** | Đếm thao tác trong từng cửa sổ cố định | Có thể burst ở ranh giới hai cửa sổ |
| **Sliding window** | Đếm hoặc ước tính trong cửa sổ trượt | Có thể công bằng hơn nhưng tốn state hơn |
| **Token bucket** | Mỗi thao tác dùng một token; token được bổ sung theo thời gian | Cho phép burst theo kích thước bucket |
| **Leaky bucket / pacing queue** | Các thao tác được phát theo tốc độ tương đối đều | Cần queue, timeout và chính sách tràn |
| **Semaphore** | Chỉ cho tối đa K thao tác đang chạy | Là concurrency limit, **không phải** rate limit theo thời gian |

Ví dụ token bucket có dung lượng **10 token**, bổ sung **5 token/giây**. Nếu bucket đầy, có thể chấp nhận một burst 10 request gần như ngay lập tức. Sau đó số token bổ sung phụ thuộc thời gian. Vì có burst, cơ chế này **không nhất thiết đáp ứng câu chữ “mọi cửa sổ một giây đều không quá năm request”**; chọn thuật toán theo yêu cầu SLA/quota cụ thể.

Các đơn vị của limiter là **request/giây**, **token/giây**, **request/phút** hoặc tương tự. Trong khi đó, highTide của limitRate chỉ có đơn vị **phần tử trong một lô demand**.

## 9. Tại sao delayElements không thay thế rate limiter production?

~~~java
Flux<Integer> paced = Flux.range(1, 4)
        .delayElements(Duration.ofMillis(250));
~~~

Đoạn trên là ví dụ đặt trong một phương thức đã import Flux và Duration. Nó tạo độ trễ theo thời gian giữa các phần tử của **một subscription**. Đây là công cụ hợp lý cho demo, test hoặc một luồng xử lý cần được làm chậm có kiểm soát.

Tuy nhiên:

- Mỗi subscriber có chuỗi delay riêng. Hai subscriber không tự chia sẻ quota chung.
- Nếu gọi HTTP API **trước** khi delay, limiter đang làm chậm **response** chứ không ngăn request được bắt đầu.
- Delay có dao động theo Scheduler, và không định nghĩa chính sách burst hoặc identity.
- Nhiều instance, nhiều thread, retry và công việc ngoài pipeline có thể tạo thêm request.
- Delay không tự phát HTTP 429 hoặc đặt giới hạn backlog trong gateway.

Với quota API nghiêm ngặt, cần một cơ chế cấp **permit trước lúc bắt đầu thao tác**, có state phù hợp với phạm vi quota. Delay chỉ có thể là một phần của chiến lược pacing ở trường hợp được kiểm soát.

## 10. Khác biệt với giới hạn concurrency

Ví dụ có một danh sách ID cần gọi API:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(id -> fetchProduct(id), 8);
~~~

Đây là đoạn minh họa, giả định ids đã được định nghĩa và fetchProduct(id) trả Mono<Product>. Tham số **8** giới hạn số **Publisher con** được xử lý đồng thời trong flatMap theo contract của operator. Điều đó **không có nghĩa 8 request/giây**.

Nếu mỗi HTTP call hoàn tất trong 10 ms, tám slot có thể được tái sử dụng rất nhiều lần trong một giây. Nếu mỗi call mất 5 giây, số call mới mỗi giây ít hơn nhiều. Concurrency đo số việc **đang hoạt động**, còn rate limiter đo số việc **bắt đầu/chấp nhận trong thời gian**.

~~~text
limitRate(8)
    -> upstream được xin demand theo lô phần tử.

flatMap(fetch, 8)
    -> tối đa 8 publisher con đang được subscribe đồng thời.

tokenBucket(5 calls/sec)
    -> cấp hoặc từ chối permit theo quota thời gian.

Ba con số 8, 8, 5 có ba ý nghĩa khác nhau.
~~~

Trong hệ thống có dịch vụ đối tác, có thể cần **cả concurrency limit lẫn time-based rate limiter**. Cơ chế thứ nhất bảo vệ số connection/công việc đồng thời; cơ chế thứ hai bảo vệ quota.

## 11. Spring WebFlux: giới hạn HTTP request đầu vào

Yêu cầu “mỗi API key tối đa 100 request/phút” là **chính sách HTTP ingress**, không phải chính sách về cách Flux trong controller yêu cầu phần tử.

Một kiến trúc tiêu biểu:

~~~text
HTTP client
    |
    v
[Gateway / WebFilter / edge]
    |-- xác định người dùng / API key / tenant
    |-- kiểm tra quota theo thời gian
    |-- đủ quota: cho request đi tiếp
    |-- hết quota: trả 429 hoặc chính sách được cấu hình
    v
[Spring WebFlux controller]
    |
    v
[Service trả Mono / Flux]
    |
    v
[Reactor Netty response]
~~~

Có thể triển khai bằng **Spring Cloud Gateway RequestRateLimiter**, WebFilter hoặc một API gateway bên ngoài. Nếu triển khai phân tán và quota phải được dùng chung toàn hệ thống, cần backend trạng thái phân tán/atomic phù hợp (ví dụ Redis), hoặc cơ chế phối hợp quota tương đương.

Các quyết định cần thống nhất:

- Quota theo API key, authenticated principal, tenant, route hay IP?
- Khi vượt quota trả HTTP **429 Too Many Requests**, chờ có giới hạn hay queue?
- Có gửi **Retry-After** khi tính được thời gian chờ hợp lệ hay không?
- Token bucket có cho burst không; nếu có thì tối đa bao nhiêu?
- Có nhiều pod không, mỗi pod có nhìn thấy cùng bộ đếm không?
- Logging/metric có phản ánh các request bị từ chối trước khi vào handler không?

**Gắn Flux.limitRate(100) vào response body không ngăn client gửi 1.000 HTTP request/giây.** Mỗi request HTTP có thể tạo một pipeline/subscription độc lập. Khi cần chống spam hoặc quota tài nguyên, thực hiện ở ranh giới ingress.

## 12. Spring WebFlux: giới hạn HTTP request đầu ra

Giả sử API bên ngoài quy định **5 calls/giây** cho cả tài khoản tích hợp. Mã gọi WebClient theo nhiều ID có thể là:

~~~java
Flux<PartnerResponse> result = Flux.fromIterable(ids)
    .flatMap(id ->
        webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(PartnerResponse.class),
        8
    );
~~~

Đây chỉ là đoạn minh họa; cần định nghĩa ids, webClient, PartnerResponse và cấu hình ứng dụng. Mức **8** ở flatMap là concurrency, không phải 8 calls/giây. Thêm **limitRate(5)** vào chuỗi cũng không biến nó thành quota 5 calls/giây.

Cần bảo đảm **mỗi HTTP attempt nhận permit** từ rate limiter trước khi bắt đầu:

~~~text
ID cần gọi
   |
   v
[Rate limiter: lấy permit theo khóa "partner"]
   |                       |
   | được phép             | hết quota
   v                       v
Bắt đầu WebClient      chờ hữu hạn / từ chối / lập lịch lại
   |
   v
HTTP response / timeout / retry
~~~

Một giao diện minh họa cho limiter bất đồng bộ:

~~~java
Mono<Void> awaitPermit(String quotaKey);
~~~

Giao diện này là **minh họa**, không phải implementation. Giả sử awaitPermit trả Mono hoàn tất khi có permit, có thể ghép:

~~~java
Flux<PartnerResponse> result = Flux.fromIterable(ids)
    .flatMap(id ->
        awaitPermit("partner")
            .then(Mono.defer(() ->
                webClient.get()
                    .uri("/items/{id}", id)
                    .retrieve()
                    .bodyToMono(PartnerResponse.class)
            )),
        8
    );
~~~

Đoạn trên **chưa phải chương trình chạy độc lập** vì thiếu các lớp và bean ứng dụng. Nó chỉ thể hiện **đúng điểm chèn limiter**: cấp phép trước khi Publisher đại diện HTTP call được subscribe.

Lưu ý quan trọng với **retryWhen**: mỗi attempt thực tế có thể là một HTTP request mới. Nếu quota của đối tác đếm từng attempt, **mỗi lần retry phải đi qua limiter**. Đặt permit ở ngoài toàn bộ chuỗi retry mà không tính lại có thể cho phép vượt quota. Đồng thời cần giới hạn số lần retry, backoff, timeout và kích thước queue chờ permit.

## 13. Các cơ chế cần phối hợp trong production

Ví dụ yêu cầu:

- Một job xử lý 10.000 bản ghi.
- Đối tác cho tối đa 10 HTTP requests/giây.
- Tối đa 4 HTTP call đồng thời.
- Mỗi call timeout sau 2 giây.
- Source bản ghi hưởng lợi khi nhận demand từng lô 32 phần tử.

Các cơ chế giải quyết những phần khác nhau:

~~~text
[Source 10.000 bản ghi]
       |
       | limitRate(32): chia upstream demand
       v
[Flux các bản ghi]
       |
       | flatMap(..., 4): giới hạn inner Publisher đồng thời
       v
[Rate limiter: 10 calls/s]
       |
       | permit cho mỗi HTTP attempt
       v
[WebClient / dịch vụ đối tác]
       |
       | timeout, retry, backoff và cancellation
       v
[Kết quả]
~~~

Một pipeline cần chọn **vị trí** từng cơ chế sao cho đúng công việc được bảo vệ. Ví dụ nếu rate limiter nằm sau việc tạo request có side effect ngay khi assembly, đã quá muộn; nếu giới hạn concurrency chỉ đặt ở một nhóm worker mà còn worker khác gọi cùng đối tác, quota tổng vẫn có thể vượt.

Không đặt niềm tin vào một thông số duy nhất để “giải quyết tất cả vấn đề backpressure, tốc độ và lỗi”.

## 14. Vị trí doOnRequest để quan sát demand

Có thể quan sát số phần tử được yêu cầu ở hai phía của operator:

~~~java
Flux<Integer> pipeline = Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(10, 0)
    .doOnRequest(n -> System.out.println("downstream request=" + n));
~~~

Ở đây **doOnRequest trước limitRate** gần nguồn, thấy các request đã bị chia. **doOnRequest sau limitRate** gần subscriber, thấy demand trước khi toán tử biến đổi.

~~~text
Source -- doOnRequest("upstream") -- limitRate -- doOnRequest("downstream") -- Subscriber
~~~

Một vài biến số ảnh hưởng trace:

- **buffer(N)** đổi demand từ số buffer sang số phần tử gốc.
- **flatMap** có concurrency và prefetch trên các Publisher con.
- **publishOn** có queue và prefetch để chuyển ngữ cảnh thực thi.
- **take**, cancellation và lỗi có thể khiến một request lớn không được sử dụng hết.
- Nguồn hot hoặc adapter có chính sách buffer/drop khác có thể không tôn trọng request theo cùng cách nguồn cold đơn giản.

Vì vậy, dùng trace để hiểu **đúng ranh giới cụ thể** thay vì suy ra mọi phần của pipeline đều nhận request giống nhau. Trên production tải lớn, tránh log từng item/request tràn lan; dùng metric/sampling phù hợp.

## 15. limitRate có bảo vệ bộ nhớ hay event loop không?

Chỉ một phần, và không có bảo đảm tổng quát. Có thể giảm cách upstream bị yêu cầu cung cấp dữ liệu, nhưng các nguồn khác vẫn làm hệ thống quá tải:

- Source vẫn giữ buffer lớn trước khi trả Flux.
- Một operator flatMap dùng nhiều Publisher con, mỗi Publisher có prefetch riêng.
- Nhiều Subscriber hoặc nhiều HTTP request độc lập cùng hoạt động.
- Bên ngoài Reactor có queue không giới hạn.
- Một callback dùng JDBC blocking hoặc Thread.sleep trên Netty event loop.
- Connection pool quá nhỏ hoặc quá nhiều retry cùng lúc.
- Các nguồn hot có hành vi drop/buffer khi downstream chậm.

**limitRate không tự chuyển blocking thành non-blocking**, không tự tạo scheduler, không bảo vệ request ingress và không tự quản lý toàn bộ RAM. Muốn bảo vệ event loop, dùng API non-blocking hoặc cô lập tác vụ blocking trên scheduler phù hợp khi không thể thay thế API cũ. Muốn bảo vệ bộ nhớ, phải xem tất cả buffer, queue và số công việc song song.

## 16. Đo chỉ số nào để biết đang giải đúng bài toán?

| Chỉ số | Ý nghĩa | Dùng để kiểm chứng |
| --- | --- | --- |
| Các giá trị request(n) gần source | Demand thực truyền lên upstream | limitRate có chia request đúng kỳ vọng không |
| Tổng phần tử emitted/consumed | Khối lượng dữ liệu cuối cùng | limitRate có đang bị nhầm với giới hạn tổng số không |
| HTTP requests started/second | Số call thực được khởi tạo theo thời gian | Quota outbound có được tuân thủ không |
| HTTP 429 và rejected-permit count | Tần suất chạm quota | Chính sách rate limiting |
| Active HTTP calls | Công việc HTTP đang in-flight | Concurrency limit, connection pool |
| Queue length và waiting time | Công việc chờ tài nguyên hoặc permit | Nguy cơ tràn hàng đợi/tăng latency |
| p50/p95/p99 latency, throughput | Hiệu năng/độ trễ ứng dụng | Tác động của batch/prefetch và limiter |
| Retry attempts, timeout, cancellations | Độ tin cậy/vòng đời thao tác | Có tính từng attempt trong quota không |

Đây là **loại chỉ số đề xuất**, không khẳng định mọi tên metric đều có sẵn trong Reactor hoặc Spring Boot.

Khi đo **rate limiter phân tán**, kiểm tra tốc độ tổng trên tất cả instance; thống kê mỗi pod riêng rẽ có thể che giấu việc vượt tổng quota.

## 17. Sai lầm phổ biến

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| limitRate(10) nghĩa 10 request/giây | Có thể vượt quota HTTP nghiêm trọng | Dùng limiter theo thời gian ở ingress/egress |
| limitRate(10) lấy đúng 10 phần tử | Stream vẫn phát đủ dữ liệu khi có demand | Dùng take(10) để cắt tổng phần tử |
| limitRate(10, 2) nghĩa 10 phần tử mỗi 2 giây | lowTide bị hiểu sai đơn vị | highTide/lowTide đều thuộc điều khiển demand |
| flatMap(..., 8) nghĩa 8 HTTP calls/giây | Call nhanh có thể khởi tạo rất nhiều lần | Kết hợp concurrency limit và rate limiter |
| delayElements(1 giây) bảo vệ toàn hệ thống | Nhiều subscription/pod cộng dồn tốc độ | Shared limiter theo đúng quota |
| limitRate là giới hạn RAM chính xác | Buffer và nguồn ngoài operator vẫn tồn tại | Tuning queue, prefetch, concurrency, backpressure |
| Một rate limiter in-memory/pod là quota global | Nhiều pod cộng dồn số permit | Đồng bộ quota toàn cụm khi cần |
| Retry không tính là request mới | Vượt quota của API đối tác | Cấp permit theo từng HTTP attempt |
| Source phải phát đủ n ngay sau request(n) | Hiểu sai contract của Publisher | Demand chỉ là quyền phát tối đa |
| Thêm limitRate ở response để chặn spam HTTP | Client vẫn tạo request mới | Thực hiện rate limiting tại Gateway/WebFilter/edge |

## 18. Câu hỏi tự kiểm tra

**1.** Flux.range(1, 1000).limitRate(20) có thể phát tối đa bao nhiêu phần tử nếu downstream muốn tất cả và không hủy?

**1.000.** 20 là mức request upstream theo lô, không phải giới hạn tổng số phần tử.

**2.** limitRate(20, 0) có bảo đảm 20 phần tử mỗi giây?

**Không.** Đây là strict batch demand, không có thông số thời gian.

**3.** Khi API yêu cầu 5 calls/s, flatMap(fetch, 5) đủ chưa?

**Chưa chắc.** Mức 5 giới hạn concurrency, không đếm số call bắt đầu trong một giây.

**4.** Khi nào take(10) thích hợp hơn limitRate(10)?

Khi mục tiêu là **chỉ xử lý tối đa 10 phần tử rồi hoàn tất**, thay vì tuning cách demand được truyền lên source.

**5.** Có ba instance, mỗi instance có limiter 100 requests/phút, vậy quota toàn hệ thống chắc chắn là 100 requests/phút không?

**Không.** Nếu state không dùng chung, các instance có thể cho tổng số request vượt 100/phút.

**6.** Để không vượt quota của dịch vụ bên ngoài, nên đặt permit ở đâu?

**Trước khi bắt đầu mỗi HTTP attempt** cần được đếm. Retry có thể tạo attempt mới, nên phải được tính theo chính sách quota.

**7.** Một downstream gọi request(Long.MAX_VALUE); limitRate(4, 0) còn ý nghĩa không?

**Có.** Nó chia demand lớn đó thành các đợt request upstream nhỏ theo highTide, dù upstream cuối cùng có thể phát toàn bộ dữ liệu.

**8.** Delay 250 ms trong một concatMap có bảo vệ được 4 requests/s cho mọi instance không?

**Không.** Nó chỉ điều tiết việc thực thi của pipeline/subscription đó. Cần rate limiter có state phù hợp để bảo đảm quota tổng.

## 19. Tài liệu tham khảo

- [Reactor Core Reference Guide — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): request(n), limitRate, highTide, lowTide và replenishment.
- [Reactor Core 3.6 — Flux API](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html): limitRate, take, flatMap, delayElements, doOnRequest.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm): hợp đồng Publisher–Subscriber–Subscription.
- [Spring Cloud Gateway RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): ví dụ về thực thi quota HTTP ở Gateway.
- [Java 17 Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): kiểu thời gian trong ví dụ pacing.

**Ghi nhớ:** **limitRate** là cơ chế **chia demand upstream thành các đợt phần tử**, không phải quota theo thời gian. **take(n)** giới hạn tổng phần tử, **flatMap(..., concurrency)** giới hạn số Publisher con chạy đồng thời, **delayElements** tạo độ trễ của một pipeline, còn **time-based rate limiter** cấp permit theo số thao tác trong thời gian và phạm vi quota. Chọn đúng tầng, đo đúng loại tín hiệu và đừng suy ra requests/second từ request(n).
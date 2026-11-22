# Prefetch và concurrency trong các toán tử kết hợp của Project Reactor

## 1. Mục tiêu bài học

Trong Spring WebFlux, một luồng thường biến mỗi đầu vào thành một tác vụ reactive rồi ghép tất cả kết quả lại. Ví dụ, một `Flux<OrderId>` được biến thành nhiều yêu cầu HTTP hoặc nhiều truy vấn R2DBC. Nếu bắt đầu quá nhiều tác vụ, hệ thống có thể làm cạn connection pool và bộ nhớ. Nếu xử lý lần lượt mọi tác vụ, một nguồn chậm có thể làm giảm thông lượng.

Hai tham số thường được dùng để điều chỉnh là:

- **`concurrency` / `maxConcurrency`**: số *inner Publisher* được phép có subscription đang hoạt động đồng thời tại một thời điểm, đối với toán tử hỗ trợ tham số này.
- **`prefetch`**: lượng phần tử toán tử yêu cầu trước ở một ranh giới upstream nhất định, để giữ cho pipeline có dữ liệu và hạn chế việc yêu cầu từng phần tử một.

Chúng liên quan đến **backpressure** nhưng giải quyết hai bài toán khác nhau. `concurrency` quản lý số nguồn con đang hoạt động; `prefetch` quản lý nhu cầu/đệm phần tử. Cùng một giá trị `prefetch` có thể áp vào **inner Publisher** ở `flatMap`, hoặc **outer Publisher** ở `concatMap` tùy API. Do đó, không thể hiểu hai tham số chỉ bằng tên gọi mà bỏ qua vị trí trong sơ đồ xử lý.

Sau bài học, bạn có thể:

1. Phân biệt `request(n)` downstream, `concurrency` và `prefetch`.
2. Đọc đúng các overload của `flatMap`, `flatMapSequential`, `concatMap`, `merge` và `mergeSequential`.
3. Giải thích vì sao tăng concurrency thường tăng số tác vụ in-flight nhưng không tương đương tăng số Java thread.
4. Giải thích vì sao tăng prefetch có thể giảm khoảng trống giữa các lần phát nhưng đồng thời làm tăng lượng dữ liệu được chuẩn bị/đệm.
5. Kiểm thử thứ tự, thời điểm subscribe và giới hạn số inner subscription bằng JUnit/StepVerifier.
6. Chọn cấu hình hợp lý cho API Spring WebFlux có nhiều nguồn dữ liệu độc lập.

## 2. Đặt nền tảng: backpressure và `request(n)`

Reactive Streams dùng `Subscription.request(long n)` để subscriber báo **nhu cầu nhận thêm phần tử** từ publisher. Một publisher tuân thủ giao thức không được gửi nhiều `onNext` hơn lượng demand hợp lệ chưa được đáp ứng. `onComplete` hoặc `onError` kết thúc subscription.

```text
Subscriber                   Operator                  Publisher
    | request(1)                |                          |
    |-------------------------->|                          |
    |                           | request(?), có thể khác 1 |
    |                           |------------------------->|
    |                           |<------------ onNext(...) |
    |<------------ onNext(...)  |                          |
    | request(1)                |                          |
    |-------------------------->|  ...                     |
```

Dấu `?` có chủ ý: demand không nhất thiết truyền lên **nguyên vẹn** qua các toán tử. Ví dụ:

- `map` thường có quan hệ một đầu vào → một đầu ra, nên tương đối trực tiếp.
- `buffer(10)` có thể cần 10 đầu vào mới tạo một buffer; request hai buffer ở downstream có thể biến thành request 20 phần tử upstream.
- `flatMap` tạo nhiều inner Publisher, nên phải xin dữ liệu ở **hai cấp**: outer để biết cần tạo inner nào, và mỗi inner để nhận kết quả của nó.
- `concatMap` có thể lấy trước các giá trị outer dù chỉ subscribe **một** inner tại một thời điểm.

Cách gọi `.subscribe(value -> ...)` và một số terminal operation thường yêu cầu dữ liệu không giới hạn (`Long.MAX_VALUE`) ở downstream. Không có nghĩa mọi upstream đều lập tức bị yêu cầu vô hạn: các toán tử trung gian có thể điều chỉnh demand, prefetch và cách phân phối.

### Quan sát demand có giới hạn

Đây là **snippet** dùng khi đã có dependency Reactor Core và import `Flux`, `BaseSubscriber`, `Subscription`:

```java
Flux.range(1, 3)
        .doOnRequest(n ->
                System.out.println("upstream request=" + n))
        .subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
                request(1);
            }
        });
```

Với `Flux.range` trực tiếp, các lần request có thể được quan sát là `1` liên tiếp, rồi nhận các giá trị `1`, `2`, `3`. Khi thêm các toán tử có queue, fusion hoặc prefetch vào giữa, các lần `doOnRequest` ở upstream **có thể có kích thước khác**. Không dùng một log đơn lẻ để kết luận toàn bộ pipeline tiêu thụ đúng từng phần tử một.

**Backpressure không phải rate limiting.** `request(16)` nói về số phần tử sẵn sàng nhận, không có nghĩa hệ thống cho phép 16 phần tử/giây. Cũng không có nghĩa dùng đúng 16 kết nối hoặc 16 thread.

## 3. `concurrency`: giới hạn số inner Publisher hoạt động

Xét một luồng gồm nhiều mã khách hàng:

```java
Flux<String> customerIds = Flux.just("A", "B", "C", "D");

Flux<Customer> customers = customerIds.flatMap(
        id -> fetchCustomer(id),
        2,
        8
);
```

Đây là **snippet thiết kế**, cần có `fetchCustomer(String)` trả `Publisher<Customer>` (thường `Mono<Customer>`) và kiểu `Customer` của ứng dụng. Hai tham số cuối là `concurrency=2` và `prefetch=8`.

Với các inner Publisher **cold, chưa hoàn tất ngay**:

```text
Outer:       A       B       C       D
                  |
maxConcurrency = 2
                  v
Ban đầu:     subscribe fetch(A), fetch(B)
Đang chờ:    C, D chưa được kích hoạt thành inner active
B xong:      giải phóng một slot -> subscribe fetch(C)
A xong:      giải phóng một slot -> subscribe fetch(D)
```

Ý nghĩa thực tế:

- `concurrency=2` giới hạn **tối đa hai inner subscription đang hoạt động** tại một thời điểm cho toán tử này.
- Khi một inner kết thúc, toán tử có thể lấy thêm một mục outer để tạo/subscribe inner tiếp theo.
- Các phần tử từ A và B vẫn có thể **xen kẽ** trong output của `flatMap`; concurrency không bảo đảm thứ tự xuất theo mã đầu vào.
- `concurrency` thường cũng ảnh hưởng lượng demand ban đầu gửi cho outer ở `flatMap`: cần có đủ phần tử outer để điền các slot đang mở.

**Concurrency không phải số thread.** Một `WebClient` hoặc driver reactive có thể dùng event loop để thực hiện nhiều I/O non-blocking cùng lúc mà không tạo một thread cho mỗi inner. Ngược lại, nếu mapper dùng API blocking, hai inner có thể giữ hai worker thread hoặc làm nghẽn event loop nếu chạy sai chỗ. Số kết nối thực tế còn phụ thuộc connection pool, HTTP protocol, retry, redirect và hành vi bên trong từng inner.

Không tự suy ra `maxConcurrency=8` là một giới hạn toàn ứng dụng. Nếu có 20 request HTTP đồng thời và **mỗi request** tạo pipeline `flatMap(..., 8, ...)`, tổng số tác vụ trên tất cả pipeline có thể lớn hơn 8 nhiều lần. Muốn áp quota toàn cục cần cơ chế chia sẻ giới hạn ở client, semaphore hoặc tầng điều phối phù hợp.

## 4. `prefetch`: chủ động yêu cầu dữ liệu trước

Giả sử một inner `Flux<LineItem>` có nhiều phần tử:

```java
Flux<LineItem> lines = fetchLines(orderId);
```

Nếu chờ downstream request từng phần tử rồi mới báo lên nguồn, có thể phát sinh nhiều lần trao đổi tín hiệu. Prefetch cho phép toán tử xin một số phần tử trước để sử dụng dần.

Với:

```java
Flux<LineItem> combined = orderIds.flatMap(
        orderId -> fetchLines(orderId),
        3,    // concurrency: tối đa 3 inner active
        4     // prefetch: lượng request ban đầu cho mỗi inner
);
```

Một mô hình trực quan:

```text
                flatMap(maxConcurrency=3, prefetch=4)
Outer IDs  ----------------------------------------------->
             |            |             |
             v            v             v
         inner #1      inner #2       inner #3
         request(4)    request(4)     request(4)
             |            |             |
             +------------+-------------+
                          |
                 Queue/drain theo demand
                          |
                      Downstream
```

Trong các operator hỗ trợ prefetch, Reactor thường **nạp lại demand theo từng đợt** khi đã tiêu thụ một phần đáng kể lượng yêu cầu trước đó. Tài liệu Reactor mô tả heuristic khoảng **75% prefetch** cho nhiều operator. Đây là hành vi tối ưu hóa, không phải hợp đồng rằng mọi operator, phiên bản và nguồn đều gọi `request()` với cùng dãy số; fusion, scalar optimization và thay đổi phiên bản có thể làm log khác đi.

**Không hiểu `prefetch=4` là “inner chỉ được phát tối đa bốn phần tử trong suốt vòng đời”.** Bốn phần tử là nhu cầu khởi đầu; khi các phần tử đã được tiêu thụ, toán tử sẽ request tiếp. Một inner hoàn toàn có thể phát 10.000 phần tử trong nhiều đợt.

### Prefetch đặt ở đâu mới đúng?

Điểm dễ nhầm nhất là vị trí **cấp demand**:

| Toán tử / overload | `concurrency` kiểm soát | `prefetch` chủ yếu áp vào |
|---|---|---|
| `flatMap(mapper, concurrency, prefetch)` | Số inner chạy cùng lúc | Request ban đầu **mỗi inner** |
| `flatMapSequential(mapper, maxConcurrency, prefetch)` | Số inner được subscribe sớm | Request **mỗi inner**, đồng thời có thể đệm kết quả để giữ thứ tự |
| `concatMap(mapper, prefetch)` | Không có tham số concurrency; subscribe từng inner tuần tự | Request giá trị từ **outer source** |
| `Flux.merge(sources, concurrency, prefetch)` khi `sources` là một `Publisher<Publisher<T>>` | Số nguồn con được merge cùng lúc | Request **mỗi nguồn con** |
| `Flux.mergeSequential(sources, maxConcurrency, prefetch)` ở overload tương ứng | Số nguồn con active được subscribe sớm | Request **mỗi nguồn con**, đệm để giữ thứ tự nhóm |
| `publishOn(scheduler, prefetch)` | Không có concurrency của inner | Request ở ranh giới **trước publishOn** khi chuyển scheduler |

Lưu ý quan trọng: các chữ ký trong bảng nói về những overload **có sẵn tham số tương ứng**. Ví dụ `Flux.merge(a, b)` là overload nhận các publisher cụ thể và không nhận thêm một `prefetch` theo cùng cách. Với `concatMap`, `prefetch` trên outer không làm tăng số inner đang subscribe vượt một.

Không đồng nhất `prefetch` với **kích thước response HTTP**, **số byte buffer**, **số request API/giây** hoặc **số kết nối pool**. Nó là tham số demand theo **đơn vị phần tử** của một publisher.

## 5. So sánh bốn kiểu ghép: thứ tự, subscription và tài nguyên

| Toán tử | Khi nào subscribe inner tiếp theo? | Output giữ thứ tự nhóm outer? | Có thể nhiều inner cùng chạy? |
|---|---|---|---|
| `concatMap(mapper, prefetch)` | Chỉ sau khi inner trước hoàn tất | Có | Không, về ngữ nghĩa concat |
| `flatMap(mapper, concurrency, prefetch)` | Sớm, đến giới hạn concurrency | Không bảo đảm | Có |
| `flatMapSequential(mapper, maxConcurrency, prefetch)` | Sớm, đến giới hạn concurrency | Có | Có |
| `Flux.concat(a,b)` | Chỉ sau `a` hoàn tất thành công | Có | Không trong phép concat |
| `Flux.merge(a,b)` | Subscribe các nguồn sớm | Không bảo đảm | Có |
| `Flux.mergeSequential(a,b)` | Subscribe sớm nhưng xuất theo nhóm | Có | Có |

Ví dụ A chậm, B nhanh:

```text
                 0 ms       40 ms       80 ms       200 ms
Nguồn A:         subscribe -------------------------- A1
Nguồn B:         subscribe -- B1 ------- B2

flatMap / merge:                  B1   B2            A1
flatMapSequential / mergeSequential:
                              (buffer B1, B2)        A1, B1, B2
concatMap / concat: (chỉ subscribe B sau khi A hoàn tất)
```

Với các nguồn bất đồng bộ khác nhau, tăng concurrency có thể làm B bắt đầu sớm và giảm thời gian tổng. Tuy nhiên, `flatMapSequential` phải **giữ kết quả của B trong bộ đệm** khi A chưa hoàn tất để bảo vệ thứ tự. Nếu A quá chậm và nhiều nguồn sau phát dữ liệu lớn, bộ đệm trở thành yếu tố cần cân nhắc.

Không gọi `flatMapSequential` là một phép `sort` theo thời gian phát. Nó giữ thứ tự **nhóm theo vị trí outer**, không sắp xếp các timestamp sự kiện.

### `concatMap` có thể prefetch outer mà vẫn giữ tính tuần tự

```java
Flux<String> ordered = ids.concatMap(
        id -> fetchText(id),
        8
);
```

`concatMap(..., 8)` có thể yêu cầu trước một số mã `id` từ nguồn ngoài, nhưng **không bắt đầu `fetchText(id)` cho mã kế tiếp** khi inner trước chưa hoàn tất. Điều này giúp vừa có nguồn outer sẵn dữ liệu vừa giữ các bước nghiệp vụ nối tiếp.

Trong Reactor 3.6.x, overload `concatMap(mapper, 0)` cho phép tắt prefetch outer; hãy kiểm tra tài liệu API của phiên bản đang chạy nếu muốn dựa vào khác biệt tinh tế giữa các overload. Prefetch lớn không nên được dùng để phá giới hạn tài nguyên hay kỳ vọng thay thế `concurrency`.

## 6. Một ví dụ tính toán nhu cầu và bộ đệm

Giả sử nguồn outer tạo danh sách 500 đơn hàng. Với mỗi đơn hàng, inner có thể trả một luồng tối đa 30 dòng sản phẩm:

```java
Flux<LineItem> allLines = orderIds.flatMap(
        id -> queryLines(id),
        4,
        8
);
```

Ở mức khái niệm:

1. `flatMap` có thể đăng ký tối đa **4** inner cùng thời điểm.
2. Mỗi inner có thể nhận nhu cầu khởi đầu khoảng **8** phần tử, nghĩa là tổng nhu cầu khởi đầu ở các inner đang hoạt động có thể vào khoảng `4 × 8 = 32` phần tử.
3. Khi downstream tiêu thụ phần tử và các inner còn dữ liệu, demand được bổ sung. Các inner mới có thể được subscribe khi slot trống.
4. Nếu downstream chậm hơn các inner, các phần tử đã được yêu cầu nhưng chưa phát ra downstream có thể được giữ trong queue/đệm nội bộ.
5. Sau khi một đơn hàng hoàn tất, một đơn hàng khác có thể lấp chỗ trống; toàn bộ 500 đơn hàng không cần cùng hoạt động.

**Con số 32 chỉ là mô hình minh họa cho lượng request khởi đầu**, không phải cận trên tuyệt đối cho mọi queue hay heap. Bởi vì:

- Demand được bổ sung theo thời gian; một inner có thể phát nhiều hơn `prefetch` trong suốt vòng đời.
- `flatMap` có thể có queue của outer/inner, dữ liệu đã xử lý đang chờ downstream, codec/network buffer và những tầng operator khác.
- Một phần tử có thể là chuỗi 10 byte hoặc một object/JSON nhiều megabyte: `prefetch=8` không giới hạn 8 KB hay bất kỳ kích thước byte cụ thể nào.
- Nguồn không tuân thủ backpressure hoặc nguồn hot có chiến lược overflow riêng có thể cần xử lý hoàn toàn khác.

Khi điều chỉnh thực tế, hãy theo dõi **số inner active**, số phần tử đang chờ, kích thước object trung bình, sử dụng heap/GC và sức chịu tải của downstream. Công thức `concurrency × prefetch` là điểm khởi đầu để hiểu áp lực, **không phải cam kết bộ nhớ**.

## 7. Chương trình Java 17+ chạy được: kiểm thử concurrency và thứ tự

Ví dụ sau dùng **Reactor Core 3.6.6**, JUnit Jupiter và `reactor-test`. Nó là dự án Java độc lập, không đòi hỏi khởi động Spring WebFlux. `Sinks.One` cho phép test chủ động kết thúc từng inner để thấy khi nào slot concurrency được giải phóng. `StepVerifier.withVirtualTime` kiểm thử thứ tự của các inner có độ trễ khác nhau mà không lệ thuộc clock thật.

Tạo cấu trúc:

```text
reactor-prefetch-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── PrefetchConcurrencyTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-prefetch-demo</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/test/java/edu/demo/PrefetchConcurrencyTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PrefetchConcurrencyTest {

    private static Mono<String> delayed(int id) {
        long delay = switch (id) {
            case 1 -> 100L;
            case 2 -> 20L;
            default -> 40L;
        };
        return Mono.delay(Duration.ofMillis(delay))
                .map(tick -> "R" + id);
    }

    @Test
    void flatMapInterleavesFasterInners() {
        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 3)
                        .flatMap(
                                id -> delayed(id),
                                3,
                                1
                        ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(150))
                .expectNext("R2", "R3", "R1")
                .verifyComplete();
    }

    @Test
    void flatMapSequentialPreservesSourceOrder() {
        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 3)
                        .flatMapSequential(
                                id -> delayed(id),
                                3,
                                1
                        ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(150))
                .expectNext("R1", "R2", "R3")
                .verifyComplete();
    }

    @Test
    void concatMapSubscribesToOneInnerAtATime() {
        List<Sinks.One<Integer>> gates = new ArrayList<>();
        for (int index = 0; index < 3; index++) {
            gates.add(Sinks.one());
        }

        List<Integer> started = new CopyOnWriteArrayList<>();

        Flux<Integer> ordered = Flux.range(1, 3)
                .concatMap(id ->
                        gates.get(id - 1).asMono()
                                .doOnSubscribe(s -> started.add(id)), 2);

        StepVerifier.create(ordered)
                .expectSubscription()
                .then(() -> assertEquals(List.of(1), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(0).tryEmitValue(1)))
                .expectNext(1)
                .then(() -> assertEquals(List.of(1, 2), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(1).tryEmitValue(2)))
                .expectNext(2)
                .then(() -> assertEquals(List.of(1, 2, 3), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(2).tryEmitValue(3)))
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void flatMapOpensOnlyTwoInitialSlotsAndRefillsThem() {
        List<Sinks.One<Integer>> gates = new ArrayList<>();
        for (int index = 0; index < 4; index++) {
            gates.add(Sinks.one());
        }

        List<Integer> started = new CopyOnWriteArrayList<>();

        Flux<Integer> merged = Flux.range(1, 4)
                .flatMap(id ->
                        gates.get(id - 1).asMono()
                                .doOnSubscribe(s -> started.add(id)),
                        2, 1);

        StepVerifier.create(merged)
                .expectSubscription()
                .then(() -> assertEquals(List.of(1, 2), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(1).tryEmitValue(2)))
                .expectNext(2)
                .then(() -> assertEquals(List.of(1, 2, 3), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(2).tryEmitValue(3)))
                .expectNext(3)
                .then(() -> assertEquals(List.of(1, 2, 3, 4), started))
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(0).tryEmitValue(1)))
                .expectNext(1)
                .then(() -> assertEquals(
                        Sinks.EmitResult.OK,
                        gates.get(3).tryEmitValue(4)))
                .expectNext(4)
                .verifyComplete();
    }
}
```

Chạy lệnh tại thư mục `reactor-prefetch-demo`:

```bash
mvn test
```

Khi môi trường tải dependency thành công, kết quả mong đợi là **bốn test PASS**. Tên bài test và assertion giải thích được điều gì đã kiểm tra:

- `flatMapInterleavesFasterInners`: ba inner được chạy sớm, kết quả theo thời điểm phát: `R2`, `R3`, `R1`.
- `flatMapSequentialPreservesSourceOrder`: có thể bắt đầu sớm, nhưng downstream nhận `R1`, `R2`, `R3`.
- `concatMapSubscribesToOneInnerAtATime`: dù `prefetch=2`, mỗi lần chỉ một inner được subscribe; `started` lần lượt có `[1]`, `[1,2]`, `[1,2,3]` sau các lần hoàn tất có kiểm soát.
- `flatMapOpensOnlyTwoInitialSlotsAndRefillsThem`: dù outer có 4 phần tử, ban đầu chỉ subscribe inner 1 và 2; khi inner 2 xong, subscribe 3; khi 3 xong, subscribe 4. Kết quả có thể nhận thứ tự `2, 3, 1, 4`, khác thứ tự outer.

**Lưu ý về phạm vi kiểm thử:** Ở hai test đầu, `prefetch=1` chỉ làm tham số cấu hình inner; mỗi `Mono` vốn phát tối đa một giá trị. Vì vậy hai test chủ yếu chứng minh **thứ tự kết hợp**, không chứng minh kích thước queue hoặc throughput khi thay đổi prefetch. Để đo tác động của prefetch, cần inner `Flux` nhiều giá trị và instrument demand/queue như mục sau.

## 8. Quan sát prefetch ở các inner nhiều phần tử

Ví dụ dưới đây giúp quan sát `request(n)` khi một nguồn outer tạo ra ba inner `Flux`. Đây là **snippet trong phương thức Java** có import `Flux`, `BaseSubscriber` và `Subscription`:

```java
Flux<Integer> result = Flux.range(1, 3)
        .flatMap(id ->
                Flux.range(id * 10, 5)
                        .hide()
                        .doOnSubscribe(s ->
                                System.out.println("inner " + id
                                        + " subscribed"))
                        .doOnRequest(n ->
                                System.out.println("inner " + id
                                        + " request=" + n)),
                2, 2);

result.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("received=" + value);
        request(1);
    }
});
```

Cách đọc log:

1. Dù outer có 3 ID, ban đầu tối đa 2 inner được subscribe vì `concurrency=2`.
2. `prefetch=2` khiến các inner được yêu cầu dữ liệu theo đợt thay vì mọi phần tử đều đợi một request mới từ downstream.
3. Khi một inner hoàn tất, ID thứ ba có thể trở thành inner active.
4. `BaseSubscriber` ở cuối chỉ gọi `request(1)` mỗi lần, nhưng operator trung gian vẫn có thể chủ động yêu cầu trước và giữ một ít dữ liệu.
5. `hide()` được dùng để giảm ảnh hưởng của một số tối ưu hóa *fusion* khi quan sát các tín hiệu; log chi tiết vẫn có thể đổi theo phiên bản Reactor và thứ tự luồng chạy.

**Không gắn nhãn một chuỗi log cụ thể là output duy nhất.** `flatMap` không bảo đảm thứ tự phần tử **giữa** các inner; thuật toán refill và queue có thể khác với suy luận ngây thơ `2,2,2` lặp lại. Muốn kiểm chứng yêu cầu quan trọng, hãy viết assertion trên hành vi cần thiết hoặc dùng `StepVerifier`, đồng thời đo bằng công cụ giám sát trong ứng dụng thực.

### Vì sao `Mono` và `Flux` cần tune prefetch khác nhau?

- Một inner `Mono<T>` phát nhiều nhất **một** giá trị. Tăng prefetch từ 1 lên 16 thường không tạo thêm 15 kết quả trong inner đó. Khi nhiều lời gọi WebClient `.bodyToMono(...)` cùng chạy, **concurrency, connection pool và timeout** thường quan trọng hơn prefetch.
- Một inner `Flux<T>` có thể phát hàng ngàn phần tử. Prefetch khi đó ảnh hưởng lượng nhu cầu đi trước và áp lực queue/bộ nhớ, đặc biệt khi downstream xử lý chậm.
- Nếu một inner trả về `Flux` từ decoder HTTP streaming hoặc R2DBC, khả năng backpressure đi xuyên toàn bộ network/database driver còn phụ thuộc implementation. Đừng đồng nhất `request(16)` với việc driver hoặc máy chủ từ xa chỉ thực hiện đúng 16 thao tác vật lý.

## 9. Tuning có chủ đích trong Spring WebFlux

Ví dụ một service gọi API non-blocking để lấy nhiều bản ghi mỗi mã khách hàng:

```java
@Service
public class CustomerQueryService {
    private final WebClient client;

    public CustomerQueryService(WebClient client) {
        this.client = client;
    }

    public Flux<CustomerRecord> loadRecords(Flux<String> customerIds) {
        int maxConcurrency = 8;
        int innerPrefetch = 16;

        return customerIds.flatMap(id ->
                        client.get()
                                .uri("/customers/{id}/records", id)
                                .retrieve()
                                .bodyToFlux(CustomerRecord.class),
                maxConcurrency,
                innerPrefetch);
    }
}
```

Đây là **snippet tích hợp**: cần `CustomerRecord` là kiểu dữ liệu của dự án, bean `WebClient`, import `org.springframework.stereotype.Service`, `org.springframework.web.reactive.function.client.WebClient` và `reactor.core.publisher.Flux`, cùng upstream API thực. Nó chưa phải dự án Spring Boot tự chạy độc lập.

Điều xảy ra trong một subscription:

- Có thể có đến 8 inner reactive HTTP stream đang hoạt động, tùy số mã khách hàng và khả năng cấp nguồn.
- Mỗi inner `Flux<CustomerRecord>` nhận demand theo cấu hình prefetch và thuật toán refill.
- Kết quả từ nhiều khách hàng có thể xen kẽ. Nếu API phải trả từng khách hàng theo thứ tự mã đầu vào, cân nhắc `flatMapSequential` với cùng các tham số; đổi lại có thể tăng buffering.
- Đây là **giới hạn ở toán tử trong một subscription**. Số request thực tế, kết nối và tải upstream còn bị chi phối bởi pool, retry, giới hạn HTTP client, nhiều subscriber cùng lúc và dịch vụ đích.
- Với `bodyToMono(CustomerRecord.class)`, mỗi inner tối đa một phần tử; chọn một `prefetch` nhỏ/để mặc định thường đủ, ưu tiên quản lý `maxConcurrency` và client pool.

Nếu nghiệp vụ bắt buộc xử lý xong khách hàng trước mới sang khách hàng kế tiếp:

```java
return customerIds.concatMap(id ->
        client.get()
                .uri("/customers/{id}/records", id)
                .retrieve()
                .bodyToFlux(CustomerRecord.class),
        8);
```

Ở đây `8` là **prefetch của outer IDs** trong overload `concatMap`, **không phải tám HTTP request chạy cùng lúc**. Nguồn trước phải hoàn tất mới chuyển sang nguồn sau.

### Không dùng tham số operator thay thế các giới hạn khác

`concurrency=8` **không** tương đương:

- Tối đa 8 request/giây (đó là rate limit theo thời gian).
- Toàn hệ thống có tối đa 8 request đang hoạt động (còn các subscription/request khác).
- Connection pool chỉ có 8 kết nối (pool cấu hình riêng).
- Mỗi request chắc chắn có timeout 8 giây (timeout cấu hình riêng).
- Có 8 thread riêng cho 8 inner (Reactor không mặc định tạo thread cho mỗi inner).

Muốn hạn chế số API call toàn hệ thống, dùng cơ chế có phạm vi chia sẻ đủ rộng như connector pool limit, concurrency control tại gateway/service hoặc quota của upstream. Muốn timeout, dùng timeouts ở WebClient/client và/hoặc `.timeout(...)` tại pipeline. Muốn retry, quyết định chính sách và vị trí `retryWhen` riêng; retry có thể làm tăng số lần truy cập thật.

## 10. `flatMapSequential`: concurrency cao có thể gây head-of-line blocking

Giả sử inner A mất 5 giây, B và C trả dữ liệu sau 50 ms:

```text
Outer order: A, B, C

A:  ────────────────────────────────────── A1, complete
B:  ─ B1, B2, complete
C:  ── C1, C2, complete

flatMap(A,B,C):
    B1, B2, C1, C2, A1  (một thứ tự khả dĩ)

flatMapSequential(A,B,C):
    [đệm B1,B2,C1,C2 trong lúc chờ A]
    A1, B1, B2, C1, C2
```

`flatMapSequential` cho phép B/C chạy sớm; **output vẫn bị chặn ở A** để giữ thứ tự. Điều này gọi là head-of-line blocking ở tầng phát kết quả, và có thể làm latency đến phần tử đầu tiên tăng dù nhiều tác vụ nền đã hoàn tất.

Với inner Flux trả nhiều dữ liệu, tăng `maxConcurrency` và `prefetch` đồng thời có thể khiến các nguồn sau tạo ra nhiều kết quả phải đệm:

- Nếu thứ tự toàn bộ nhóm là bắt buộc, đo kích thước và thời gian chờ của những buffer này.
- Nếu không bắt buộc thứ tự, `flatMap`/`merge` có thể chuyển phần tử đến downstream sớm hơn.
- Nếu mỗi inner có dữ liệu lớn, có thể dùng concurrency thấp hơn, prefetch thấp hơn hoặc thiết kế stream theo page/chunk.
- Nếu một inner không bao giờ hoàn tất, `flatMapSequential` có thể không phát các nhóm sau dù chúng đã sẵn sàng; cần timeout hoặc cancel rõ ràng.

Đây là lý do không thể mặc định “tăng concurrency luôn tốt”: càng nhiều nguồn chạy sớm, càng nhiều dữ liệu có thể phải chờ thứ tự xuất.

## 11. Prefetch đi qua những ranh giới nào khác?

Nhiều operator trong cùng pipeline có thể cùng biến đổi demand. Hãy đọc pipeline từ **downstream ngược lên upstream** để nhận ra ranh giới thực sự:

```java
Flux<LineItem> result = orderIds
        .flatMap(id -> queryLines(id), 4, 8)
        .publishOn(Schedulers.parallel(), 16)
        .limitRate(32);
```

Đây là snippet cần `orderIds`, `queryLines`, `LineItem`, import `Flux`, `Schedulers` và các dependency thích hợp.

- `flatMap(...,4,8)`: có tối đa 4 inner đang hoạt động; mỗi inner được prefetch 8 phần tử.
- `publishOn(...,16)`: chuyển downstream processing sang scheduler được chỉ định và dùng prefetch cho nhu cầu ở ranh giới trước `publishOn`.
- `limitRate(32)`: chia demand lớn từ downstream thành từng đợt upstream theo ngưỡng của toán tử; **không** giới hạn 32 phần tử/giây.
- Nhu cầu và queue của các operator này **tương tác**, không thể lấy `4 × 8 + 16 + 32` làm công thức chính xác cho heap.

`publishOn` còn thay đổi ngữ cảnh thực thi, **không** phải một cách mặc định để tự động chạy mọi inner song song. Các source I/O đã có lịch bất đồng bộ riêng; dùng thêm `publishOn` hoặc `subscribeOn` khi có mục đích rõ ràng. Nếu mapper chứa blocking JDBC, ưu tiên thiết kế lại driver/cách ly blocking đúng chỗ thay vì “chữa” bằng việc tăng prefetch.

### Prefetch và `limitRate` có quan hệ thế nào?

`limitRate(highTide)` là công cụ điều tiết demand upstream theo các lô; có overload `limitRate(highTide, lowTide)` để chỉnh điểm bổ sung. Prefetch là tham số **bên trong một operator cụ thể**, điều chỉnh nhu cầu đầu vào cho nó. Cả hai cùng dùng `request(n)` nhưng khác ranh giới và mục đích.

Ví dụ:

```java
Flux.range(1, 100)
        .limitRate(16)
        .doOnNext(System.out::println)
        .subscribe();
```

Đây là snippet, không đại diện giới hạn 16 phần tử/giây. `subscribe()` mặc định sẵn sàng nhận hết; `limitRate(16)` điều chỉnh cách nguồn upstream được yêu cầu thành các đợt để tránh một lời request vô hạn truyền thẳng qua.

## 12. Khi có lỗi, cancel, hot source và backpressure

### Lỗi và cancellation

Với `flatMap`, một inner phát `onError` thường làm kết quả tổng kết thúc lỗi theo kiểu fail-fast và các inner khác bị hủy. Khi hủy subscription từ downstream, operator cố hủy những inner đang hoạt động và bỏ các phần tử còn trong queue theo hỗ trợ discard của operator.

```java
Flux<LineItem> result = orderIds
        .flatMap(id -> queryLines(id), 4, 8)
        .timeout(Duration.ofSeconds(5));
```

Đây là snippet; cần import `Duration` và các nguồn thực. `.timeout(Duration)` ở đây giới hạn **khoảng thời gian chờ tín hiệu giữa các phần tử** hoặc từ subscribe đến phần tử đầu tiên, không mặc nhiên là deadline năm giây cho toàn bộ một request nhiều phần tử. Cần thiết kế timeout HTTP client và deadline nghiệp vụ phù hợp. Cancel không bảo đảm công việc bên ngoài Reactor luôn dừng tức thì nếu thư viện nguồn không tôn trọng cancellation.

Nếu muốn trì hoãn lỗi đến khi các inner khác có cơ hội kết thúc, Reactor có `flatMapDelayError(mapper, concurrency, prefetch)` và các biến thể merge delay error. Điều này **không sửa lỗi**, chỉ đổi thời điểm gửi terminal error; có thể làm queue, thời gian chờ và tài nguyên sử dụng tăng lên.

### Hot source và nguồn không tuân thủ demand

`prefetch` giả định upstream tuân thủ request/demand. Với một publisher hot, phần tử có thể đến từ bên ngoài mà không phụ thuộc tốc độ của subscriber; cần xem chính sách overflow: buffer có giới hạn, drop, latest, fail hoặc lưu vào hệ thống durable.

Không được coi `prefetch=8` là cơ chế tự động khiến Kafka broker, socket, database hoặc tất cả `Sinks.Many` chỉ sản xuất đúng tám phần tử. Hành vi của driver, broker và codec phải được xem xét riêng.

Nếu nguồn outer sử dụng `groupBy` tạo rất nhiều nhóm nhưng mỗi nhóm chưa được tiêu thụ, một `flatMap` có `maxConcurrency` quá thấp đôi khi khiến pipeline khó tiến triển hoặc kẹt do nhóm chưa được drain. Đây là một tình huống cần chọn concurrency dựa trên **số nhóm thực tế** và chiến lược tiêu thụ, thay vì dùng cố định một giá trị thấp cho mọi nguồn.

## 13. Quy trình điều chỉnh tham số theo số liệu

Một cách làm có thể lặp lại:

1. **Xác định yêu cầu thứ tự**: được phép xen kẽ (`flatMap`/`merge`), phải xuất theo thứ tự (`flatMapSequential`), hay phải hoàn tất từng nguồn (`concatMap`).
2. **Đếm inner thực sự**: mỗi mã đầu vào tạo một `Mono`, một `Flux` nhiều phần tử, hay nhiều lời gọi HTTP bên trong một inner? Đây là đơn vị cần giới hạn.
3. **Chọn concurrency ban đầu vừa phải** và tương thích với connection pool/quota upstream; không đặt quá cao vì muốn “chạy nhanh”.
4. **Chọn prefetch theo dữ liệu**: với `Mono` một giá trị, cần ít điều chỉnh; với `Flux` lớn, cân nhắc kích thước record, downstream speed và budget queue.
5. **Đặt timeout/cancellation/error policy** để không có inner treo vĩnh viễn và slot concurrency bị chiếm vô hạn.
6. **Đo tải tương đương thực tế**, theo dõi throughput, p50/p95/p99 latency, heap, GC, kết nối đang dùng/chờ, request lỗi và độ sâu hàng đợi.
7. **Điều chỉnh một biến mỗi lần** (ví dụ concurrency 4 → 8 trong khi giữ prefetch; rồi prefetch 8 → 16 ở cùng tải) để biết tác động nào thực sự có ích.
8. **Kiểm thử burst và downstream chậm**, vì bộ đệm thường chỉ tăng mạnh khi tốc độ nguồn lớn hơn tốc độ tiêu thụ.

Không có con số prefetch/concurrency “tối ưu” cho mọi dự án. Những con số minh họa `2`, `4`, `8`, `16` trong bài **không phải khuyến nghị mặc định cho production**.

### Mẫu triệu chứng và điều chỉnh

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Latency cao, pool còn dư, các API độc lập đang chạy tuần tự | Concat/concatMap không phù hợp yêu cầu | Cân nhắc flatMap có concurrency giới hạn nếu được phép xen kẽ |
| Nhiều timeout/429/503 từ upstream khi tăng concurrency | Vượt quota/pool hoặc gây quá tải remote | Giảm concurrency, kiểm soát retry và quota |
| Heap/GC tăng nhanh khi dùng flatMapSequential | Nguồn đầu chậm, nhiều nguồn sau có kết quả phải đệm | Giảm concurrency/prefetch, xem lại yêu cầu giữ thứ tự |
| Flux lớn tiến triển không đều nhưng CPU/network còn dư | Prefetch quá thấp hoặc downstream request gián đoạn | Quan sát `doOnRequest`, queue và thử tăng prefetch có kiểm soát |
| Downstream xử lý chậm, queue tăng | Tốc độ sinh vượt tốc độ tiêu thụ | Giảm prefetch/concurrency, xử lý demand/backpressure tận nguồn |
| Nhiều request HTTP dù concurrency mỗi pipeline nhỏ | Có nhiều subscription đồng thời hoặc inner tạo nhiều request | Giới hạn toàn cục/connection pool, quan sát metric cấp client |
| Mapper JDBC gây nghẽn event loop | Tác vụ blocking nằm sai scheduler | Dùng stack phù hợp hoặc cách ly nguồn blocking; tăng concurrency không giải quyết gốc |

## 14. Những nhầm lẫn phổ biến cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`concurrency=8` nghĩa là đúng tám thread” | Nó giới hạn số inner active ở operator; thread do runtime/scheduler quyết định. |
| “`prefetch=16` là tối đa 16 phần tử trong cả stream” | Đây là nhu cầu đầu vào ban đầu/từng đợt; tổng phát có thể rất lớn. |
| “`flatMap(...,8,16)` và `concatMap(...,16)` đều cho 16 inner chạy” | `flatMap` có nhiều inner; `concatMap` subscribe lần lượt một inner. |
| “`prefetch` chỉ có một nghĩa trên mọi operator” | Phải xác định nó áp vào outer, inner hay ranh giới scheduler. |
| “`flatMap` giữ thứ tự outer” | Kết quả có thể xen kẽ. Dùng `flatMapSequential` nếu cần thứ tự nhóm. |
| “`flatMapSequential` không tốn thêm bộ nhớ” | Kết quả inner đến sớm có thể bị đệm khi chờ inner trước. |
| “Tăng concurrency sẽ luôn tăng throughput” | Bị giới hạn bởi remote, CPU, pool, quota, queue và backpressure. |
| “`prefetch` là giới hạn byte” | Tham số đo theo **phần tử**, không xét kích thước object. |
| “`prefetch` là rate limit” | Không phải phần tử/giây hay request/giây. |
| “Một lệnh `request(1)` ở cuối luôn làm upstream nhận request 1” | Toán tử trung gian có thể reshaping request. |
| “Publisher trả `Mono` sẽ dùng hết prefetch 32 phần tử” | `Mono` phát tối đa một phần tử; tác động prefetch với inner Mono thường nhỏ. |
| “Chỉ cần set concurrency là có giới hạn toàn hệ thống” | Giới hạn thường là theo **mỗi subscription** và không bao quát logic bên trong inner. |
| “Đổi `merge` sang `concat` chỉ thay thứ tự output” | Nó còn thay thời điểm subscribe và mức hoạt động đồng thời. |
| “Dùng WebFlux thì mọi nguồn tự non-blocking” | Blocking I/O trong mapper vẫn có thể làm nghẽn event loop. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một `Flux.range(1, 100)` được ánh xạ thành 100 `Mono` truy cập API. Bạn dùng `.flatMap(mapper, 5, 20)`. Giá trị nào gần nhất với số inner cùng hoạt động?

**Đáp án:** Tối đa **5** inner active tại một thời điểm trong operator này. `20` là prefetch trên từng inner, nhưng mỗi `Mono` chỉ phát tối đa một kết quả; không phải 20 HTTP request/giây.

**Câu 2.** Với `.concatMap(mapper, 10)`, có mười inner cùng được subscribe không?

**Đáp án:** Không. `concatMap` xử lý inner **tuần tự**; `10` là prefetch của outer theo overload này.

**Câu 3.** `flatMapSequential(..., 8, 32)` có giữ nguyên thứ tự từng nhóm outer không? Có hệ quả gì khi nhóm đầu rất chậm?

**Đáp án:** Có; nhưng các nhóm sau có thể đã phát phần tử nội bộ và phải đệm cho đến khi nhóm đầu hoàn tất, gây tăng độ trễ và áp lực bộ nhớ.

**Câu 4.** Vì sao từ `concurrency=4` không thể suy ra cả ứng dụng chỉ có bốn kết nối HTTP?

**Đáp án:** Vì giới hạn thuộc một operator/subscription; ứng dụng có thể có nhiều subscription đồng thời, inner có thể tạo nhiều kết nối, và connection pool của HTTP client được quản lý riêng.

**Câu 5.** Bạn cần kiểm tra chính xác các request mà upstream nhận sau khi đặt prefetch. Nên dùng gì?

**Đáp án:** Gắn `doOnRequest` ở đúng phía của operator, dùng `StepVerifier`/`BaseSubscriber` để kiểm soát downstream demand, và chú ý các tối ưu hóa fusion, refill cùng phiên bản Reactor. Không đoán request thực chỉ từ một dòng code.

**Câu 6.** Nên ưu tiên tăng `concurrency` hay `prefetch` khi WebClient trả `Mono` một phần tử cho mỗi ID, kết quả chậm do nhiều lời gọi I/O độc lập chờ lâu?

**Đáp án:** Kiểm tra khả năng chạy đồng thời và giới hạn connection pool trước. Prefetch inner rất lớn thường không cải thiện nhiều vì Mono tối đa một phần tử; tăng concurrency có kiểm soát có thể hữu ích nếu upstream chịu được.

## 16. Ghi nhớ

Ba ý quan trọng nhất:

- **`concurrency` giới hạn số inner Publisher được subscribe đồng thời** ở những toán tử hỗ trợ. Nó thể hiện mức độ *overlap* của công việc, không trực tiếp chỉ thread hoặc request/giây.
- **`prefetch` là nhu cầu lấy trước tính theo phần tử tại một ranh giới cụ thể**. Với `flatMap`, nó thường điều chỉnh từng inner; với `concatMap`, điều chỉnh outer. Prefetch giúp pipeline có sẵn dữ liệu nhưng có thể tăng buffering.
- **Đừng tune tách rời nghiệp vụ**: yêu cầu giữ thứ tự, latency của nguồn chậm, số lượng phần tử trong mỗi inner, connection pool, cancellation, memory và backpressure quyết định cấu hình nào phù hợp.

Hãy bắt đầu từ hợp đồng `request(n)`, xác định **outer/inner** của toán tử, sau đó dùng kiểm thử thời gian và quan sát tài nguyên để chọn giá trị.

## Tài liệu tham khảo chính thức

- Project Reactor, **Flux API** (`flatMap`, `flatMapSequential`, `concatMap`, `merge`, `mergeSequential`): https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Reactor Core Reference – Backpressure and Ways to Reshape Requests**: https://projectreactor.io/docs/core/3.6.6/reference/
- Project Reactor, **StepVerifier và virtual time**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html
- Project Reactor, **Which Operator Do I Need?**: https://projectreactor.io/docs/core/3.6.6/reference/apdx-operatorChoice.html
- Reactive Streams, **JVM Specification**: https://www.reactive-streams.org/
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html
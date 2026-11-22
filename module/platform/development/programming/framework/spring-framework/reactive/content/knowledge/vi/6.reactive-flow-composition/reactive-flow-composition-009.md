# Nguy cơ giữ dữ liệu, nhóm không được tiêu thụ và bộ nhớ tăng trong Project Reactor

Trong Spring WebFlux, ta thường chia một luồng sự kiện thành **nhóm theo khóa** (`groupBy`), **cửa sổ** (`window`) hoặc **lô dữ liệu** (`buffer`). Những thao tác này giúp xử lý song song, tổng hợp và giới hạn kích thước công việc. Tuy nhiên, khi một nhóm không có subscriber, upstream tiếp tục tạo khóa mới, hoặc downstream gom dữ liệu cho tới lúc nguồn hoàn thành, pipeline có thể **giữ nhiều phần tử trong RAM, ngừng tiến triển do backpressure hoặc hết bộ nhớ**.

Bài học này tập trung vào nguyên nhân, dấu hiệu và cách xử lý các vấn đề đó trong nhóm chủ đề **Ghép và chia luồng** của Spring Reactive. Trọng tâm là `Flux.groupBy`, đồng thời liên hệ `window`, `buffer`, `collectList`, `flatMap` và vòng đời subscription.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt nhóm sống `GroupedFlux` với danh sách kết quả đã gom xong.
- Giải thích vì sao **mỗi nhóm cần được tiêu thụ** để `groupBy` tiếp tục xử lý ổn định.
- Nhận ra nguy cơ khi số khóa nhóm (cardinality) lớn và `flatMap` có `maxConcurrency` quá thấp.
- Phân biệt backpressure stall, backlog, giữ dữ liệu lâu và memory leak.
- Tránh `collectList` không giới hạn trên nguồn vô hạn; chọn cửa sổ/lô hữu hạn.
- Viết ví dụ Reactor Java 17+ chạy được, kiểm thử `StepVerifier` và áp dụng trong WebFlux.
- Chọn biện pháp quản lý bộ nhớ mà vẫn tôn trọng yêu cầu nghiệp vụ về đủ dữ liệu và đúng thứ tự.

## 2. Ba kiểu chia luồng tạo ra ba kiểu trạng thái

| Toán tử | Kết quả khái quát | Cách chia | Rủi ro chính |
| --- | --- | --- | --- |
| `groupBy(key)` | `Flux<GroupedFlux<K,T>>` | Theo khóa, phần tử cùng khóa không cần đứng cạnh nhau | Nhiều nhóm sống; nhóm không được tiêu thụ; backlog theo khóa |
| `window(n)` / `windowTimeout(...)` | `Flux<Flux<T>>` | Theo ranh giới kích thước, thời gian hoặc điều kiện | Publisher con chưa được drain; cửa sổ chờ; queue |
| `buffer(n)` / `bufferTimeout(...)` | `Flux<List<T>>` | Gom phần tử thành collection rồi phát collection | List giữ payload; nhiều batch chờ downstream |
| `collectList()` | `Mono<List<T>>` | Gom **toàn bộ nguồn** tới khi hoàn thành | Nguồn lớn/vô hạn làm List tăng hoặc không bao giờ phát kết quả |

Điểm khác biệt thiết yếu: `groupBy` và `window` phát ra **publisher con**. Việc outer `Flux` đã phát một nhóm không chứng minh các phần tử **bên trong nhóm** đã được lấy ra. Mỗi publisher con cần một nhánh downstream đăng ký và yêu cầu dữ liệu. `buffer` lại tạo một `List` thực nằm trong RAM; nó không có một inner publisher cần subscribe.

```text
Nguồn:  A1 → B1 → A2 → C1 → B2 → A3 → ...
             │ groupBy(Event::key)
             ▼
Outer:      group A      group B      group C
               │            │            │
               ▼            ▼            └─ không ai đọc?
          subscriber A  subscriber B            │
               │            │                  └─ dữ liệu/nhu cầu chờ
               ▼            ▼
          xử lý A       xử lý B
```

“Reactive không chặn thread” không đồng nghĩa “không giữ dữ liệu”. Các queue, collection, metadata nhóm, request đang hoạt động và socket buffer đều dùng bộ nhớ dù thread không `sleep` hay `block`.

## 3. groupBy tạo các nhóm sống, không tạo Map có sẵn

Giả sử luồng nguồn có:

```text
Nguồn:   A1  B1  A2  C1  B2  A3  C2  complete
Nhóm A:  A1      A2          A3       complete
Nhóm B:      B1      B2               complete
Nhóm C:              C1          C2   complete
```

`groupBy` tạo `GroupedFlux` khi gặp khóa mới. Một nhóm có thể nhận phần tử ở nhiều thời điểm không liên tục. Theo hợp đồng của Reactor, các nhóm là **unicast**, nghĩa là mỗi nhóm được dành cho một subscriber; không được giả định có thể đăng ký lặp nhiều lần như một cold publisher mới. Mỗi phần tử nguồn được phân vào một nhóm ứng với khóa của nó.

Nếu nguồn là stream sự kiện không kết thúc, một nhóm đang im lặng **không mặc nhiên complete**. Vì thế:

```java
// Chỉ là fragment: cần Event và liveEvents của ứng dụng.
Flux<GroupedFlux<String, Event>> groups =
    liveEvents.groupBy(Event::category);
```

Phát một đối tượng `GroupedFlux` chỉ thông báo “đã thấy khóa này”. Để thực sự xử lý dữ liệu, downstream phải consume inner, chẳng hạn:

```java
// Ví dụ tích hợp: cần Event và hàm handle(Event).
Flux<Result> handled = liveEvents
    .groupBy(Event::category)
    .flatMap(group -> group.map(this::handle), 4);
```

Ví dụ này chỉ hợp lý nếu số category đang sống đã được kiểm soát và giới hạn concurrency phù hợp; `Result` và `this::handle` do ứng dụng định nghĩa. Không tự dùng mẫu này cho hàng trăm nghìn khóa.

## 4. Tại sao một nhóm chưa đọc có thể giữ cả nguồn đứng?

Reactive Streams có cơ chế `Subscription.request(n)`: subscriber yêu cầu thêm phần tử, và các toán tử truyền/biến đổi nhu cầu này về upstream. `groupBy` đồng thời phải phân phối phần tử cho đúng nhóm. Điều gì xảy ra khi một số nhóm không được đọc?

1. Nguồn phát phần tử của khóa A, B, C, D... xen kẽ.
2. `groupBy` mở nhiều nhóm và chuyển item đến nhóm tương ứng.
3. Downstream chỉ có một vài subscription vào inner vì `flatMap(..., maxConcurrency)` đặt quá thấp, hoặc vì chỉ xử lý nhóm đầu.
4. Các nhóm chưa có subscriber có thể giữ dữ liệu trong hàng đệm và chưa giải phóng nhu cầu.
5. Khi khả năng chứa/yêu cầu đạt giới hạn, nguồn không thể tiếp tục phát như trước.
6. Một nhóm đang được đọc có thể chờ chính nguồn đó đi tiếp để nhận thêm dữ liệu hoặc hoàn thành. Nhưng tiến độ nguồn đang bị cản bởi những nhóm chưa được drain.

```text
    group A đang chờ completion / phần tử cuối
                   ▲
                   │ cần upstream đi tiếp
                   │
      upstream → groupBy → A (đã subscribe)
                   ├────→ B (chưa subscribe)
                   └────→ C (chưa subscribe)
                           │
                           ▼
                 dữ liệu B/C chưa drain
                           │
                           └─ backpressure làm nguồn không tiến
```

Kết quả có thể giống “treo”: không `onError`, không `onComplete`, throughput giảm về 0; thread dump thậm chí không có lock deadlock. Đây là **vòng phụ thuộc giữa consumption và backpressure**. Tài liệu Reactor cảnh báo điều kiện này khi cardinality cao mà concurrency của consumer quá thấp.

### Phản ví dụ: groupBy rồi concatMap gom cả nhóm

```java
// PHẢN VÍ DỤ: không chạy trong production hoặc test thiếu timeout.
Flux<List<Integer>> risky = Flux.range(1, 1000)
    .groupBy(n -> n % 10, 8)
    .concatMap(group -> group.collectList());
```

Nguồn có 10 khóa xen kẽ. `concatMap` chỉ subscribe từng nhóm một. `collectList` chờ nhóm đầu hoàn tất; trong lúc đó các nhóm khác có thể phát sinh dữ liệu nhưng chưa được drain, khiến `groupBy` bị cản bởi backpressure. Tùy kích thước prefetch, luồng và cách request, pipeline **có thể không hoàn thành**. Không khẳng định mọi đầu vào hữu hạn hoặc mọi phiên bản Reactor luôn treo, nhưng đây là cấu trúc cần tránh.

### Phản ví dụ: concurrency thấp hơn đáng kể số nhóm

```java
// PHẢN VÍ DỤ: mỗi category tạo một nhóm, chỉ 2 nhóm được xử lý cùng lúc.
Flux<Integer> risky = events
    .groupBy(Event::category)
    .flatMap(group -> group.map(Event::payloadSize), 2);
```

Đoạn này là fragment, `events` và `Event` phải có trong ứng dụng. Nếu có rất nhiều category xen kẽ, giới hạn hai nhóm hoạt động có thể gây stall. **Tăng concurrency vô hạn không phải cách sửa**: nó chỉ chuyển áp lực sang số nhóm đăng ký, tài nguyên khác và bộ nhớ.

## 5. Cardinality: số khóa mới có thể không ngừng tăng

| Khóa dùng để group | Đặc tính | Đánh giá |
| --- | --- | --- |
| `INFO` / `WARN` / `ERROR` | Ba giá trị định trước | Thường phù hợp |
| Enum trạng thái nghiệp vụ hữu hạn | Số giá trị có trần rõ ràng | Dễ lập ngân sách số nhóm |
| Khu vực trong danh mục nhỏ | Hữu hạn nếu validate input | Có thể phù hợp |
| `userId` | Có thể hàng trăm nghìn/hàng triệu | Cần cân nhắc kiến trúc khác |
| `sessionId`, `requestId`, UUID mới | Gần một nhóm mỗi item | Cardinality tăng rất nhanh |

Nếu nguồn vô hạn liên tục sinh key mới, nhiều nhóm có thể vẫn sống trong khi nguồn chưa kết thúc. Không có cơ sở để xem `groupBy` là cache có TTL hoặc cơ chế eviction nghiệp vụ tự động. Chi phí quản lý nhóm cộng với các item đang chờ có thể tạo áp lực heap đáng kể.

Cần phân biệt **giảm số nhóm có chủ đích** với **làm mất ngữ nghĩa**: nhóm `userId.hashCode() % 8` tạo tám bucket, nhưng nhiều người dùng bị trộn chung. Điều đó hợp lệ khi mục tiêu là chia thành tám phân vùng xử lý; không hợp lệ nếu cần thống kê riêng từng người dùng.

### Bộ nhớ không chỉ là kích thước payload

```text
Tổng bộ nhớ liên quan đến pipeline ≈
  trạng thái các nhóm đang sống
+ item trong queue nhóm chưa được drain
+ item mà inner operator đang gom (List, sort, join...)
+ queue phía downstream / transport
+ object và reference của ứng dụng
```

Đây là mô hình định tính, không phải công thức byte heap chính xác. Một payload 1 KB có thể cần nhiều object hoặc wrapper; các queue và collection cũng có overhead.

## 6. Backlog, heap tăng và memory leak là ba vấn đề khác nhau

**Backlog:** consumer xử lý chậm hơn nguồn tạo dữ liệu. Các item chờ trong queue; nếu tốc độ cân bằng trở lại và queue được drain, bộ nhớ có thể giảm.

**Giữ dữ liệu do thiết kế:** `collectList()` giữ item hợp lệ cho đến khi hoàn thành; `sort()` hoặc `groupBy` cũng có trạng thái trung gian. Nếu nguồn rất lớn hoặc không kết thúc, dữ liệu có thể được giữ quá lâu dù không có bug về tham chiếu.

**Memory leak:** object vẫn được tham chiếu dù không còn cần cho công việc. Ví dụ Map cache không eviction, subscription bị bỏ quên hoặc danh sách dùng toàn cục liên tục lưu thêm event.

Tất cả có thể gây `OutOfMemoryError` nhưng không được đánh đồng. Phân tích memory leak cần xem **live heap sau GC**, allocation rate, GC pressure và đường tham chiếu giữ object. Không kết luận chỉ vì RSS của tiến trình không giảm ngay sau khi hoàn thành một batch.

Với **nguồn nóng** ngoài hệ thống (broker/callback) không thể tự giảm tốc theo `request(n)`, backpressure trong pipeline không bảo đảm nguồn vật lý ngừng phát. Cần giới hạn queue và quyết định chính sách xử lý tràn: từ chối, chuyển sang lưu trữ, giảm tốc ở cổng vào hoặc bỏ dữ liệu khi nghiệp vụ thực sự cho phép. Bỏ sự kiện thanh toán không thể là default âm thầm.

## 7. Demo Reactor Java 17+ chạy được: ba nhóm được drain

Ví dụ dùng nguồn hữu hạn và đúng ba nhóm; `flatMap(..., 3)` đăng ký tối đa ba inner, đủ để cả ba được tiêu thụ. `collectList` ở đây an toàn về mặt phạm vi **do nguồn hữu hạn, chỉ có 12 phần tử**.

Tạo cấu trúc:

```text
reactor-group-memory/
├── pom.xml
├── src/main/java/GroupMemoryDemo.java
└── src/test/java/GroupMemoryTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-group-memory</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
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
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Nội dung `src/main/java/GroupMemoryDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import reactor.core.publisher.Flux;

public class GroupMemoryDemo {
    public static void main(String[] args) {
        Map<Integer, List<Integer>> groups = Flux.range(1, 12)
            .groupBy(n -> n % 3, 8)
            .flatMap(group ->
                group.collectList()
                    .map(items -> Map.entry(group.key(), items)),
                3)
            .collectMap(Map.Entry::getKey, Map.Entry::getValue)
            .block(Duration.ofSeconds(5));

        System.out.println("groups=" + new TreeMap<>(groups));

        List<List<Integer>> batches = Flux.range(1, 7)
            .buffer(3)
            .collectList()
            .block(Duration.ofSeconds(5));

        System.out.println("batches=" + batches);

        List<Integer> windowed = Flux.range(1, 7)
            .window(3)
            .concatMap(window -> window)
            .collectList()
            .block(Duration.ofSeconds(5));

        System.out.println("windowed=" + windowed);
    }
}
```

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=GroupMemoryDemo
```

Stdout:

```text
groups={0=[3, 6, 9, 12], 1=[1, 4, 7, 10], 2=[2, 5, 8, 11]}
batches=[[1, 2, 3], [4, 5, 6], [7]]
windowed=[1, 2, 3, 4, 5, 6, 7]
```

Giải thích kết quả:

1. `n % 3` tạo các nhóm 1, 2, 0 khi lần đầu xuất hiện; `flatMap(..., 3)` tiêu thụ cả ba nhóm.
2. `group.collectList()` đợi từng nhóm complete; vì nguồn `Flux.range(1, 12)` hữu hạn và cả ba nhóm được drain nên kết quả hoàn thành.
3. `collectMap` gom ba cặp key-value. `TreeMap` sắp xếp khóa để output có thứ tự chắc chắn 0, 1, 2.
4. `buffer(3)` tạo batch kích thước tối đa ba. Ví dụ chỉ có bảy phần tử nên batch cuối chứa một.
5. `window(3)` tạo publisher con. `concatMap(window -> window)` **subscribe và drain từng cửa sổ**, nên chuỗi kết quả bằng nguồn ban đầu.
6. `block(Duration...)` ở đây chỉ dành cho demo console, không dùng trong WebFlux event loop.

Ví dụ dùng Reactor 3.6.9 và JUnit 5 cho một project Maven độc lập. Trong Spring Boot nên để BOM quản lý phiên bản dependency phù hợp với ứng dụng.

## 8. Vì sao collectList trên nhóm không kết thúc nguy hiểm?

```java
// PHẢN VÍ DỤ: nguồn sự kiện sống lâu, mỗi nhóm thường không tự complete.
Flux<GroupSummary> summaries = liveEvents
    .groupBy(Event::category)
    .flatMap(group ->
        group.collectList()
            .map(items -> summarize(group.key(), items)));
```

Đoạn code chỉ là **fragment**, cần `liveEvents`, `Event`, `GroupSummary`, `summarize` trong ứng dụng. Nếu nguồn không bao giờ hoàn thành, các nhóm sống lâu. `collectList` trên một nhóm sẽ chờ completion và giữ các phần tử đã nhận, không phát summary định kỳ. Một nguồn sự kiện lớn có thể làm memory tăng trong khi UI không thấy kết quả.

Phương án đúng khi cần **thống kê theo các khoảng thời gian/lô** là đặt ranh giới hữu hạn bên trong nhóm:

```java
// Chỉ phù hợp khi Event::category có tối đa bốn giá trị đã kiểm soát.
Flux<GroupSummary> summaries = liveEvents
    .groupBy(Event::category)
    .flatMap(group ->
        group.windowTimeout(100, Duration.ofSeconds(2))
            .concatMap(window ->
                window.collectList()
                    .filter(batch -> !batch.isEmpty())
                    .map(batch -> summarize(group.key(), batch))),
        4);
```

Cơ chế: từng nhóm được drain qua `flatMap`, và `windowTimeout` tạo cửa sổ kết thúc khi có đủ phần tử hoặc hết khoảng thời gian. `collectList` chỉ gom item của **một cửa sổ**, rồi phát summary trong lúc upstream vẫn tiếp tục.

Điều cần nhớ: giới hạn **100 item mỗi cửa sổ** không tự giới hạn **tổng số cửa sổ đã hoàn thành nhưng chưa xử lý**, kích thước mỗi payload, số nhóm hay queue của các tầng khác. Nếu số khóa tăng vượt bốn, ví dụ này cũng phải thay đổi thiết kế.

Nếu không cần nhóm theo khóa, dùng `bufferTimeout(100, Duration.ofSeconds(2))` đơn giản hơn. Không dùng `groupBy` chỉ để chia sự kiện thành các batch theo kích thước.

## 9. window, buffer, collectList cũng có nguy cơ riêng

### window

`Flux.window(n)` tạo `Flux<Flux<T>>`. Một cửa sổ được phát từ outer không chứng tỏ inner đã được đọc. Nên có một nhánh xử lý rõ ràng:

```java
Flux<Long> counts = Flux.range(1, 250)
    .window(100)
    .concatMap(window -> window.count());
// Khi được subscribe: 100, 100, 50, rồi complete.
```

Cửa sổ theo **số lượng phần tử** thường có ranh giới hoàn thành ngay khi đạt n hoặc nguồn kết thúc. Đây là lý do `concatMap(window -> window.count())` trên nguồn hữu hạn có thể vận hành phù hợp, trong khi `concatMap(group -> group.collectList())` trên các nhóm xen kẽ có thể tạo vòng phụ thuộc: nhóm theo khóa không tự complete tại một ranh giới 100 phần tử.

### buffer

`buffer(100)` tạo `List` tối đa 100 phần tử mỗi batch, nhưng dữ liệu được giữ trong bộ nhớ trong lúc gom. Một trăm item lớn có thể là lô rất nặng; nếu downstream chậm, nhiều lô được giữ ở những hàng đệm tiếp theo vẫn có thể tăng RAM.

`bufferTimeout(maxSize, maxTime)` giúp lô không chờ vô hạn để đạt đủ số lượng khi nguồn thưa, nhưng không phải giới hạn tổng bộ nhớ cho mọi queue. Thiết kế thêm concurrency và capacity của các bước xử lý sau buffer.

### collectList

`collectList()` chỉ phát khi **upstream hoàn thành**. Trên stream vô hạn, nó có thể đợi mãi:

```java
// PHẢN VÍ DỤ: sẽ tích lũy đến khi bị cancel/error/OOM.
Mono<List<Long>> forever = Flux.interval(Duration.ofMillis(10))
    .collectList();
```

Nếu thực sự chỉ cần 50 phần tử đầu:

```java
Mono<List<Long>> first50 = Flux.interval(Duration.ofMillis(10))
    .take(50)
    .collectList();
```

`take(50)` hoàn thành downstream sau 50 item và cancel upstream. Điều này **cố ý bỏ qua các item về sau**; chỉ hợp lệ khi nghiệp vụ muốn “50 phần tử đầu”. Với một event stream phải xử lý mọi item, dùng batch lặp lại hoặc xử lý incremental, không cắt tùy tiện.

## 10. maxConcurrency và prefetch không phải trần RAM cứng

`flatMap(mapper, maxConcurrency)` giới hạn số inner được đăng ký đồng thời; `groupBy(keyMapper, prefetch)` có cơ chế yêu cầu trước dữ liệu nguồn. Các tham số này giúp điều chỉnh demand/backpressure nhưng:

- `maxConcurrency` quá **nhỏ** so với số nhóm sống có thể làm nhóm khác không được drain và gây stall.
- `maxConcurrency` quá **lớn** có thể tạo nhiều subscription, công việc song song và bộ đệm hơn.
- `prefetch` thay đổi số phần tử có thể được yêu cầu trước, nhưng **không giới hạn số khóa mới** và không đại diện cho số byte heap.
- Queue từ `flatMap`, `flatMapSequential`, HTTP client, scheduler, serialization hoặc các operator khác vẫn có chi phí riêng.

Ví dụ, `flatMapSequential` có thể đăng ký nhiều inner cùng lúc nhưng giữ kết quả của những inner hoàn thành sớm để downstream nhìn thấy **đúng thứ tự nguồn**. Một inner đầu tiên rất chậm có thể tạo **head-of-line blocking**; kết quả phía sau nằm trong queue. Đây là cơ chế giữ dữ liệu khác với `groupBy`, nhưng cần được xem xét khi ghép luồng.

Không thể viết một công thức đơn giản “bộ nhớ tối đa = concurrency × prefetch” cho toàn ứng dụng. Cần đo lượng payload, số nhóm sống, số item in-flight và các buffer thực tế.

## 11. Các chiến lược thiết kế an toàn hơn

| Nhu cầu nghiệp vụ | Giải pháp phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| Nhóm theo ba trạng thái cố định | `groupBy` + `flatMap` drain cả ba | Cardinality thực tế, concurrency và vòng đời nguồn |
| Tổng hợp trên luồng vô hạn | Cửa sổ theo số item/thời gian hoặc reducer incremental | Tránh `collectList` toàn stream |
| Chia 500 record thành batch | `buffer(500)` hoặc `bufferTimeout(...)` | Kích thước item và backlog |
| Xử lý từng userId với hàng triệu khóa | Keyed state có TTL/eviction, partitioning hoặc stream processor phù hợp | Lưu state, hồi phục và ngữ nghĩa khi eviction |
| Cần kết quả theo thứ tự gốc | `concatMap` / `flatMapSequential` khi phù hợp | Độ trễ inner chậm và queue chờ |
| Không cần sắp thứ tự kết quả | `flatMap` có giới hạn | Concurrency và throughput |
| Source nóng không giảm tốc | Bounded queue, chính sách overload rõ ràng | Không làm mất dữ liệu quan trọng mà không được phép |
| Chỉ cần đếm item cuối nguồn hữu hạn | `count()` | Tránh `collectList().map(List::size)` |
| Muốn bỏ một số khóa trước khi nhóm | Lọc item **trước §groupBy§** | Không để nhóm không được drain sau khi đã tạo |

**Lọc nhóm ở outer** mà bỏ qua inner có thể tạo nhóm không được tiêu thụ. Nếu nghiệp vụ cho phép loại sự kiện theo khóa, lọc item trước khi §groupBy§ thường rõ ràng hơn, vì các nhóm bị loại không được tạo ra từ đầu. Nếu bắt buộc tạo nhóm rồi quyết định bỏ, phải thiết kế rõ việc hủy/drain và tác động lên dữ liệu còn lại theo semantics Reactor.

## 12. Spring WebFlux: thống kê sự kiện theo từng cửa sổ

Ví dụ tích hợp controller sau giả định nguồn §service.events()§ là `Flux<Event>`, mỗi Event có category thuộc **tối đa bốn giá trị đã validate**, và DTO `CategoryCount(String category, long count)`.

```java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventStatsController {

    private final EventService service;

    public EventStatsController(EventService service) {
        this.service = service;
    }

    @GetMapping(value = "/stats",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<CategoryCount> stats() {
        return service.events()
            .groupBy(Event::category)
            .flatMap(group ->
                group.windowTimeout(100, Duration.ofSeconds(2))
                    .concatMap(window ->
                        window.count()
                            .filter(count -> count > 0)
                            .map(count ->
                                new CategoryCount(group.key(), count))),
                4);
    }
}
```

Đây là **mảnh ghép Spring WebFlux**, không có `main`, cần Spring WebFlux starter và khai báo `EventService`, `Event`, `CategoryCount`. Chỉ khi đã có các thành phần đó, code mới có thể biên dịch trong dự án thực tế.

Điểm có ích: `window.count()` chỉ giữ bộ đếm trong mỗi cửa sổ, không giữ cả batch payload. Các nhóm được subscribe qua `flatMap` và số nhóm dự kiến có trần. Nếu upstream không kết thúc, endpoint SSE có thể tiếp tục gửi từng kết quả thay vì chờ `collectList` toàn bộ nguồn.

Nhưng vẫn cần xác định:

1. Điều gì xảy ra khi service gửi một category thứ năm?
2. Có khi nào client disconnect mà subscription không được giải phóng?
3. Cách ứng dụng xử lý source hot khi downstream HTTP chậm là gì?
4. Timeout/heartbeat của client SSE và lỗi network được báo thế nào?
5. Batch/cửa sổ có thể được tạo nhanh hơn tốc độ encode response không?

Không tự gọi `subscribe()` trong controller; **trả publisher cho WebFlux** để framework quản lý subscription, lỗi và cancellation theo vòng đời HTTP. Không gọi `block()` hoặc `Thread.sleep` trong Netty event loop để “chờ nhóm”.

## 13. Xử lý lỗi và cancellation

Một lỗi trong một group hoặc inner có thể làm outer pipeline kết thúc và hủy các publisher khác, tùy toán tử. Nếu nghiệp vụ muốn mỗi item có kết quả thành công/thất bại riêng, chuyển lỗi **bên trong nhánh xử lý item** thành đối tượng kết quả có trạng thái, thay vì nuốt ngoại lệ không phân biệt.

```java
// Fragment tích hợp: cần Event, Outcome, handler và kiểu lỗi nghiệp vụ.
Flux<Outcome> outcomes = events
    .groupBy(Event::category)
    .flatMap(group ->
        group.flatMap(event ->
            handler.handle(event)
                .map(result -> Outcome.ok(group.key(), result))
                .onErrorResume(error ->
                    Mono.just(Outcome.failed(group.key(), event.id()))),
            8),
        4);
```

Đoạn này có hai mức concurrency: tối đa bốn nhóm bên ngoài, tám xử lý item trong từng nhóm. **Nếu số group không được kiểm soát, 4 vẫn có thể quá thấp; nếu nguồn rất nóng, 4 × 8 cũng có thể gây tải lớn.** Phải căn cứ năng lực hệ thống phụ trợ, không chọn tùy ý.

Với nguồn sống lâu, hãy quản lý khi client/người dùng hủy đăng ký. `doOnCancel` và `doFinally` giúp quan sát, nhưng **cancel không đồng nghĩa với `onComplete`** và không hoàn tác lời gọi API đã xảy ra.

`timeout` hữu ích để hạn chế một inner chờ vô hạn, nhưng cần đặt đúng **phạm vi**. Timeout trên cả stream vô hạn SSE có thể báo lỗi trong khoảng im lặng hợp lệ. Timeout trên mỗi request con thường rõ hơn. Không dùng retry vô hạn để che stall từ nhóm không được drain: retry có thể đăng ký lại và lặp side effect.

## 14. Kiểm thử bằng StepVerifier

Tạo §src/test/java/GroupMemoryTest.java§ trong project Maven ở phần 7:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class GroupMemoryTest {

    @Test
    void allThreeGroupsAreConsumed() {
        Flux<String> output = Flux.range(1, 12)
            .groupBy(n -> n % 3, 8)
            .flatMap(group ->
                group.count().map(n -> group.key() + ":" + n),
                3)
            .sort();

        StepVerifier.create(output)
            .expectNext("0:4", "1:4", "2:4")
            .verifyComplete();
    }

    @Test
    void bufferEmitsBoundedBatches() {
        StepVerifier.create(Flux.range(1, 7).buffer(3))
            .expectNext(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7))
            .verifyComplete();
    }

    @Test
    void takeCancelsUpstreamAfterLimit() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Integer> source = Flux.range(1, 10)
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source.take(3))
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertTrue(cancelled.get());
    }
}
```

Chạy:

```bash
mvn -q test
```

Maven thoát với mã 0 khi ba test thành công; tùy cấu hình `-q` mà có thể không in báo cáo chi tiết. Test thứ nhất chứng minh luồng hữu hạn có ba nhóm, cả ba được xử lý và kết thúc. Test thứ hai xác minh batch đúng kích thước. Test thứ ba xác minh toán tử `take(3)` chủ động hủy subscription nguồn khi đủ phần tử.

**Lưu ý khi kiểm tra các pipeline có nguy cơ stall:** không gọi `verifyComplete()` hay `block()` vô thời hạn trên phản ví dụ nguy hiểm. Đặt giới hạn thời gian cho bài test, ví dụ:

```java
// Fragment thay thế cho assertion của test đầu, import Duration.
StepVerifier.create(output)
    .expectNext("0:4", "1:4", "2:4")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Có thể dùng timeout của test runner và thử nghiệm cách ly để nghiên cứu stall, nhưng không để một ví dụ minh họa làm CI treo. Không nên chạy test có số nhóm vô hạn hoặc List tăng mãi để chứng minh OOM.

## 15. Chẩn đoán khi pipeline ngừng tiến triển

Khi số request đang hoạt động không giảm, heap tăng và không có lỗi, hãy kiểm tra theo thứ tự:

**Kiểm tra luồng:** có `groupBy`? Có bao nhiêu distinct key? Mọi `GroupedFlux` có subscriber không? `maxConcurrency` có thấp so với số nhóm mở? Có ai gọi `collectList` trên group vô hạn không? Có inner nào chưa nhận `request` hay bị giữ chờ downstream?

**Kiểm tra ranh giới:** nguồn hữu hạn hay vô hạn? Khi nào nhóm/window complete? Có `take`, `timeout`, cancellation hoặc cơ chế đóng nhóm rõ ràng không? Có nhánh xử lý lỗi nào chỉ log rồi bỏ subscription?

**Kiểm tra bộ nhớ:** heap live sau GC, allocation rate, các `List`/queue còn sống, số nhóm và độ lớn backlog. Với nguồn nóng, đo event được phát và event đã được tiêu thụ, không chỉ đo throughput API.

**Kiểm tra chi phí observability:** tránh log nguyên payload lớn hoặc dùng từng userId/UUID làm label metric; cardinality của metrics cũng có thể gây bộ nhớ tăng. Ưu tiên aggregate số nhóm, số item chờ, tốc độ xử lý, thời gian chờ và GC.

Một fragment quan sát trong ứng dụng:

```java
Flux<Result> observed = source
    .groupBy(Event::category)
    .flatMap(group ->
        group
            .doOnSubscribe(s -> metrics.groupSubscribed())
            .doOnCancel(() -> metrics.groupCancelled())
            .map(this::transform),
        4);
```

`source`, `Event`, `Result`, `metrics` và `transform` do ứng dụng định nghĩa. Đặt §doOnNext` sau xử lý để đếm item thực sự đi tiếp; không dựa vào mỗi dấu hiệu outer đã phát group để kết luận đã drain.

## 16. Những lỗi thường gặp

1. **Nhận nhóm nhưng không consume inner:** `groupBy` phát `GroupedFlux`, không phát toàn bộ danh sách của nhóm.
2. **Dùng requestId/UUID làm khóa nhóm:** cardinality gần bằng số sự kiện.
3. **Dùng `concatMap(group -> group.collectList())` với khóa xen kẽ:** nhóm đầu đợi nguồn hoàn thành, nhóm khác chưa drain.
4. **Giới hạn `flatMap` quá thấp:** nhóm chờ subscribe làm backpressure chặn tiến độ nguồn.
5. **Tăng concurrency vô hạn:** chuyển stall thành quá tải tài nguyên.
6. **`collectList` trên stream vô hạn:** không phát kết quả khi nguồn không complete, còn dữ liệu tiếp tục được giữ.
7. **Tin rằng `buffer(100)` luôn có tổng bộ nhớ nhỏ:** kích thước payload và queue của nhiều batch mới là yếu tố quyết định.
8. **Không subscribe vào window:** publisher con chưa chắc được drain dù outer đã phát.
9. **Nhầm stalled pipeline với Java thread deadlock:** backpressure có thể ngừng tiến triển mà không có thread bị khóa.
10. **Nhầm backlog với leak:** cần heap dump và đường tham chiếu trước khi kết luận.
11. **Bỏ nhóm ở outer mà không quyết định số phận dữ liệu:** lọc item trước khi nhóm nếu thật sự cho phép loại.
12. **Để nguồn nóng cấp dữ liệu vô hạn vào buffer không giới hạn:** nguy cơ OOM khi consumer chậm.
13. **Gọi `subscribe()` bên trong controller rồi bỏ disposable:** tách luồng khỏi cancellation của HTTP request.
14. **Cho rằng timeout sửa mọi vấn đề:** nếu nhóm không được drain, timeout chỉ có thể tạo lỗi khác.
15. **Bỏ qua thử tải và metrics:** lỗi chỉ xuất hiện khi cardinality, throughput hoặc độ trễ vượt điều kiện demo nhỏ.

## 17. Bài tập tự kiểm tra

**1.** Một nguồn 1.000.000 sự kiện có 3 giá trị category. Vì sao `groupBy(category)` có thể hợp lý hơn `groupBy(requestId)`?  
**Đáp án:** Category có cardinality thấp, có thể drain ba nhóm có kiểm soát. RequestId có thể tạo gần một triệu nhóm với nhiều state và nguy cơ queue.

**2.** Vì sao `groupBy(key).concatMap(g -> g.collectList())` có thể ngừng tiến triển?  
**Đáp án:** `concatMap` chờ nhóm đầu complete; nhưng upstream có thể cần nhóm khác được tiêu thụ để tiếp tục và hoàn thành. Các nhóm xen kẽ chưa drain tạo vòng phụ thuộc backpressure.

**3.** Một nhóm đã được phát từ outer `Flux<GroupedFlux>` nhưng chưa được subscribe. Có thể coi dữ liệu nhóm đã xử lý?  
**Đáp án:** Không. Phải có consumer của inner và nhu cầu phần tử phù hợp.

**4.** Nguồn vô hạn, cần số item mỗi phút. Có nên dùng `collectList()` rồi đếm toàn bộ List?  
**Đáp án:** Không. Dùng cửa sổ theo thời gian hoặc bộ đếm incremental có ranh giới, tránh giữ toàn bộ payload.

**5.** `buffer(100)` có bảo đảm app chỉ dùng RAM cho 100 item?  
**Đáp án:** Không. Có thể có nhiều batch và queue downstream, còn item có kích thước khác nhau.

**6.** Khi §flatMap(maxConcurrency=2)` xử lý 50 khóa đang sống, có nên tăng ngay lên 50.000?  
**Đáp án:** Không. Kiểm soát cardinality/vòng đời trước; chọn concurrency phù hợp, đo bộ nhớ và tải hệ thống phụ trợ.

**7.** Một SSE client đã đóng kết nối nhưng luồng nguồn vẫn tồn tại do được subscribe thủ công. Đây là rủi ro gì?  
**Đáp án:** Subscription mồ côi có thể tiếp tục giữ state/buffer và tài nguyên; trả publisher cho WebFlux quản lý lifecycle, theo dõi cancel.

**8.** `window(100).concatMap(w -> w.count())` và `groupBy(key).concatMap(g -> g.count())` khác nhau ở đâu?  
**Đáp án:** Window cố định thường complete theo số lượng phần tử. Group theo khóa có thể kéo dài đến khi upstream hoàn tất, nên nhánh `concatMap` có nguy cơ giữ các nhóm khác chờ.

**9.** Một biểu đồ heap đi lên rồi giảm sau GC có chắc memory leak?  
**Đáp án:** Không. Cần đánh giá live heap qua nhiều chu kỳ, retention path, queue và sự tiến triển dữ liệu.

**10.** Nếu hệ thống phải xử lý mọi giao dịch, có thể dùng `onBackpressureDrop()` để tránh OOM không?  
**Đáp án:** Không tùy tiện; drop làm mất event. Phải chọn chiến lược backpressure/bounded storage hoặc từ chối input đúng hợp đồng nghiệp vụ.

## 18. Checklist trước khi vận hành

- **Cardinality:** có trần rõ cho số khóa không, hay mỗi item có thể mở nhóm mới?
- **Consumption:** có subscriber/drain thực sự cho mọi nhóm và window cần xử lý không?
- **Completion:** nguồn và từng publisher con hoàn thành khi nào; có `collectList` đợi vô hạn không?
- **Concurrency:** `maxConcurrency` đủ để tránh nhóm bị bỏ chờ nhưng không quá lớn làm cạn tài nguyên?
- **Prefetch:** đã kiểm tra queue, throughput và demand thực tế chưa?
- **Memory:** kích thước payload, số batch đang chờ, heap live và GC có được đo không?
- **Cancellation:** client ngắt kết nối có hủy được công việc liên quan không?
- **Error/timeout:** có chính sách phục hồi, trả lỗi, retry và deadline phù hợp không?
- **Nguồn nóng:** có bounded queue hoặc điều tiết đầu vào, với chính sách overflow được duyệt không?
- **Kiểm thử:** test có deadline để không treo CI; phản ví dụ nguy hiểm chỉ chạy cách ly?
- **Tính đúng đắn:** mọi phương án lọc, bỏ, gom khóa hay thay đổi thứ tự đều có phù hợp nghiệp vụ không?

**Thông điệp quan trọng:** `groupBy` phát các nhóm sống và đòi hỏi downstream tiêu thụ chúng; nếu số khóa nhiều hoặc consumer nhóm không tiến triển, backpressure có thể làm nguồn đứng và giữ dữ liệu. `window`, `buffer` và `collectList` cũng có chi phí bộ nhớ khác nhau. Thiết kế bền vững phải đồng thời xác định **số nhóm, lượng dữ liệu tối đa cần giữ, vòng đời, tốc độ consumer và cách xử lý hủy/lỗi**.

### Tài liệu tham khảo

- Project Reactor, [Three Sorts of Batching — Grouping, Windowing, Buffering](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-three-sorts-batching.html).
- Project Reactor, [Flux Javadoc — groupBy và điều kiện drain các nhóm](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).

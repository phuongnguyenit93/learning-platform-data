# flatMapSequential: kết hợp xử lý đồng thời nhưng phát kết quả theo thứ tự trong Project Reactor

Trong Spring WebFlux và Project Reactor, ta thường phải xử lý nhiều phần tử đầu vào bằng các tác vụ bất đồng bộ: gọi HTTP, truy vấn cơ sở dữ liệu reactive, giải mã nội dung hoặc lấy thông tin bổ sung. Nếu chạy **từng tác vụ một**, thời gian chờ có thể cộng dồn. Nếu chạy **đồng thời** bằng `flatMap`, kết quả có thể đến không đúng thứ tự đầu vào. Toán tử **`Flux.flatMapSequential(...)`** giải quyết trường hợp cần cả hai đặc tính: **khởi động/đăng ký nhiều tác vụ con sớm, nhưng chỉ phát kết quả xuống subscriber theo thứ tự các phần tử nguồn**.

Đây là bài về **biến đổi dữ liệu với `flatMapSequential`**, không phải bảo đảm thứ tự của mọi tác dụng phụ hoặc của mọi hệ thống bên ngoài. Cần phân biệt rõ **thứ tự đầu vào**, **thứ tự tác vụ con hoàn thành**, **thứ tự phần tử downstream nhận** và **thứ tự tác dụng phụ xảy ra**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ba giai đoạn của `flatMapSequential`: **map phần tử thành publisher con → đăng ký đồng thời có giới hạn → phát kết quả theo thứ tự nguồn**.
- So sánh chính xác `flatMap`, `concatMap` và `flatMapSequential` theo **thời điểm subscription**, **mức đồng thời**, **thứ tự đầu ra**, **khả năng xen kẽ** và **bộ nhớ đệm**.
- Dùng `flatMapSequential(mapper, maxConcurrency, prefetch)` khi gọi I/O non-blocking và cần bảo toàn thứ tự hiển thị.
- Hiểu cách các publisher con phát **0, 1 hoặc nhiều phần tử**, và cách toán tử giữ nguyên **từng dải kết quả** tương ứng một đầu vào.
- Nhận ra trường hợp **head-of-line blocking**: tác vụ đầu chậm làm các kết quả phía sau bị giữ lại.
- Xử lý timeout, lỗi, kết quả rỗng, hủy đăng ký và backpressure để pipeline không bị kẹt hoặc dùng quá nhiều tài nguyên.
- Viết ví dụ Java 17+ chạy độc lập và dùng `StepVerifier` kiểm chứng thứ tự lẫn tính đăng ký sớm.

## 2. Vấn đề cốt lõi: đồng thời và thứ tự là hai trục khác nhau

Giả sử nguồn phát ba mã công việc theo đúng thứ tự:

```text
Nguồn:              [1] ── [2] ── [3]

Thời gian tác vụ:    1: ├───────────────────────────┤  chậm
                     2:    ├──────┤                   nhanh
                     3:       ├─────────┤             trung bình

Thứ tự hoàn tất:              2       3             1
Thứ tự cần hiển thị:          1       2             3
```

Nếu một yêu cầu “lấy thông tin cho mã 1” mất 300 ms, mã 2 mất 30 ms và mã 3 mất 80 ms thì mã 2 có thể hoàn thành trước. **Đồng thời** cho phép nhiều tác vụ đang chờ I/O cùng tồn tại; **thứ tự phát kết quả** quyết định subscriber nhìn thấy cái nào trước.

- `concatMap` giữ thứ tự bằng cách chờ publisher con trước hoàn thành rồi mới đăng ký publisher con sau: dễ suy luận, nhưng mất cơ hội chồng lấp thời gian I/O.
- `flatMap` đăng ký sớm nhiều publisher con và phát phần tử theo lúc chúng đến: tận dụng đồng thời, nhưng thứ tự có thể xen kẽ.
- `flatMapSequential` cũng đăng ký sớm các publisher con nhưng **giữ lại kết quả đến sớm từ những publisher đứng sau**, đợi các publisher trước phát xong mới chuyển sang dải kết quả tiếp theo.

**Bảo toàn thứ tự phát** không đồng nghĩa với **thực thi tuần tự**. Một HTTP request gửi sau vẫn có thể đến đích, ghi log hoặc làm thay đổi dữ liệu bên ngoài trước request gửi trước; `flatMapSequential` chỉ kiểm soát thứ tự **các phần tử được phát xuống downstream**.

## 3. Cơ chế ba bước của flatMapSequential

Hình dung nguồn `Flux.just(A, B, C)` được map thành ba publisher con:

```text
Upstream Flux
     A              B               C
     │              │               │
     ▼              ▼               ▼
mapper(A)       mapper(B)        mapper(C)
     │              │               │
     ▼              ▼               ▼
inner A          inner B           inner C
(đang chậm)      (xong sớm)       (xong sớm)
     │              │               │
     │          [đợi trong       [đợi trong
     │           hàng đệm]        hàng đệm]
     ▼              ▼               ▼
                flatMapSequential
                       │
                       ▼
Downstream:    [toàn bộ A] → [toàn bộ B] → [toàn bộ C]
```

Cơ chế theo thứ tự:

1. Nguồn phát phần tử `A`. Mapper tạo publisher con `inner A`; `flatMapSequential` đăng ký nguồn con đó khi có đủ nhu cầu/dung lượng.
2. Không bắt buộc đợi `inner A` kết thúc mới đăng ký `inner B` và `inner C`; số publisher con đang hoạt động bị giới hạn bằng `maxConcurrency` nếu cấu hình.
3. Nếu `inner B` trả kết quả trước `inner A`, toán tử giữ dữ liệu B trong vùng đệm để giữ đúng thứ tự.
4. Dữ liệu của `inner A` được phát xuống downstream khi có nhu cầu. Khi `inner A` hoàn thành, toán tử mới chuyển sang phát dải B, rồi dải C.
5. Khi các publisher con hoàn thành hoặc hủy, những chỗ trống trong giới hạn đồng thời có thể được dùng để đăng ký công việc tiếp theo.

**Thứ tự được bảo toàn là thứ tự phần tử nguồn đi vào toán tử**, sau những phép sắp xếp/lọc trước đó. Nếu nguồn thực tế đã đưa mã theo thứ tự C, A, B thì `flatMapSequential` sẽ giữ C, A, B; nó không suy ra thứ tự nghiệp vụ từ ID, timestamp hay thứ tự tạo request.

### Một publisher con có thể phát nhiều phần tử

Với nguồn A, B:

```text
inner A phát:       A1 --- A2 --- A3
inner B phát:           B1 - B2 (đến sớm)
downstream thấy:   A1 --- A2 --- A3 --- B1 - B2
```

Toán tử giữ **nguyên dải dữ liệu của từng publisher con** theo thứ tự nguồn và không trộn B1 vào giữa A1, A2, A3. Với `Mono<R>` con, mỗi dải có tối đa một phần tử; với `Flux<R>` con, có thể có rất nhiều phần tử. Nếu một publisher con hoàn thành rỗng, dải đó dài 0: downstream vẫn giữ thứ tự các dải còn lại, nhưng số phần tử đầu ra có thể ít hơn số phần tử đầu vào.

## 4. So sánh ba toán tử dễ nhầm

| Tiêu chí | `flatMap(mapper)` | `concatMap(mapper)` | `flatMapSequential(mapper)` |
| --- | --- | --- | --- |
| Đăng ký publisher con | Sớm, có thể nhiều nguồn con cùng lúc | Tuần tự: chờ nguồn con trước xong rồi mới tiến tới nguồn con sau | Sớm, có thể nhiều nguồn con cùng lúc |
| Phần tử từ các publisher con | Có thể xen kẽ | Từng dải, theo thứ tự nguồn | Từng dải, theo thứ tự nguồn |
| Thứ tự downstream | Phụ thuộc thời điểm phần tử đến | Theo thứ tự đầu vào | Theo thứ tự đầu vào |
| I/O độc lập có thể chồng lấp | Có | Không theo mô hình đăng ký tuần tự | Có |
| Cần giữ kết quả đến sớm để chờ lượt | Thường không vì merge theo lúc đến | Không cần đệm để sắp xếp theo thứ tự dải kiểu này | **Có**, nhất là khi publisher con đầu chậm |
| Rủi ro thường gặp | Mất thứ tự | Chờ lâu, thông lượng thấp | Bộ nhớ đệm và head-of-line blocking |
| Khi phù hợp | Xử lý độc lập, ưu tiên kết quả đến sớm | Bắt buộc làm xong tác vụ trước rồi mới bắt đầu tác vụ sau | Chạy I/O đồng thời, trả dữ liệu theo thứ tự đầu vào |

Ví dụ nếu ba tác vụ cùng được đăng ký và kết thúc theo thứ tự 2 → 3 → 1:

- `flatMap` có thể phát `2, 3, 1` (thứ tự còn phụ thuộc lịch thực thi).
- `flatMapSequential` phát `1, 2, 3`.
- `concatMap` cũng phát `1, 2, 3`, nhưng công việc 2 chỉ được đăng ký sau khi 1 đã hoàn thành; vì vậy ví dụ “2 hoàn tất trước 1” không thể xảy ra với các inner lạnh được đăng ký hoàn toàn tuần tự.

Không phải mọi chương trình dùng `flatMap` đều đảo thứ tự; nếu publisher con chạy đồng bộ nhanh hoặc hoàn tất đúng thứ tự, đầu ra vẫn có thể tình cờ giữ thứ tự. **Không dùng kết quả một lần chạy để suy ra bảo đảm hợp đồng API.**

### map có giống flatMapSequential không?

`map(fn)` biến **một phần tử thành một giá trị đồng bộ**; `flatMapSequential(fn)` biến phần tử thành **Publisher** và gộp dữ liệu từ những Publisher đó theo thứ tự. Ví dụ `map(id -> webClient.get()...)` chỉ tạo ra `Flux<Mono<User>>` nếu mapper trả `Mono<User>`, không tự thực thi/gộp HTTP. Chọn `flatMapSequential(id -> fetch(id))` nếu cần giải phóng các publisher con thành một `Flux<User>` theo thứ tự.

## 5. Các overload quan trọng và ý nghĩa tham số

API Reactor thường dùng:

```java
<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper);

<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper,
    int maxConcurrency);

<R> Flux<R> flatMapSequential(
    Function<? super T, ? extends Publisher<? extends R>> mapper,
    int maxConcurrency,
    int prefetch);
```

Đây là **chữ ký API khái quát** để giải thích; thông thường bạn gọi trực tiếp `flux.flatMapSequential(...)`, không tự khai báo những phương thức trên.

- **`mapper`**: nhận phần tử nguồn kiểu T, trả `Publisher<? extends R>`. Phổ biến là một `Mono<R>` từ WebClient, R2DBC hoặc một `Flux<R>` con.
- **`maxConcurrency`**: giới hạn số lượng **publisher con đồng thời được đăng ký/đang hoạt động**. Ví dụ `4` cho phép tối đa bốn inner in-flight trong một subscription của operator; giá trị phải dương. Không nên hiểu đây là “tạo chính xác bốn thread”.
- **`prefetch`**: mức yêu cầu phần tử từ **mỗi publisher con** trước khi downstream đã nhận hết. Dùng để điều chỉnh số lượng phần tử có thể đang bay và được đệm; giá trị phù hợp phụ thuộc kích thước phần tử và tốc độ downstream.

Ví dụ cấu hình cụ thể:

```java
Flux<Result> results = ids.flatMapSequential(
    id -> reactiveClient.fetch(id),
    8,  // tối đa 8 publisher con hoạt động
    1   // prefetch 1 phần tử từ mỗi inner
);
```

`ids`, `Result` và `reactiveClient` trong ví dụ này là **thành phần do ứng dụng cung cấp**, không phải chương trình độc lập. Nếu `fetch` trả `Mono<Result>`, mỗi inner chỉ có 0 hoặc 1 giá trị; cấu hình `prefetch = 1` thường dễ hiểu trong ví dụ. Nếu inner là `Flux` nhiều dữ liệu, điều chỉnh prefetch cần dựa trên lưu lượng thực tế.

**Lưu ý:** `maxConcurrency` giới hạn số subscription con, không bảo đảm đồng thời CPU hay giới hạn tổng kết nối toàn ứng dụng. Nhiều HTTP request riêng biệt đều có thể tạo pipeline mới với giới hạn riêng. Vẫn cần connection pool, rate limit, giới hạn tổng tải và đo lường tài nguyên ở cấp dịch vụ.

## 6. Demo Java 17+ chạy được: bất đồng bộ nhưng đầu ra đúng thứ tự

Ví dụ dùng `Mono.delay` để giả lập ba thao tác I/O hoàn thành với thời lượng khác nhau. Vì `Mono.delay` dùng scheduler, các khoảng chờ có thể chồng lấp **mà không chặn thread bằng `Thread.sleep`**. Phần hiển thị kết quả được gom bằng `collectList()` để stdout đơn giản và xác định.

Tạo cấu trúc:

```text
reactor-ordered-merge/
├── pom.xml
├── src/main/java/OrderedMergeDemo.java
└── src/test/java/OrderedMergeTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-ordered-merge</artifactId>
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

`src/main/java/OrderedMergeDemo.java`:

```java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class OrderedMergeDemo {

    private static Mono<String> fetch(int id) {
        long latencyMillis = switch (id) {
            case 1 -> 300;
            case 2 -> 30;
            case 3 -> 80;
            default -> 50;
        };

        return Mono.delay(Duration.ofMillis(latencyMillis))
            .map(tick -> "result-" + id);
    }

    public static void main(String[] args) {
        List<String> ordered = Flux.just(1, 2, 3)
            .flatMapSequential(OrderedMergeDemo::fetch, 3, 1)
            .collectList()
            .block();

        System.out.println(ordered);
    }
}
```

Chạy ở thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=OrderedMergeDemo
```

Stdout của `main`:

```text
[result-1, result-2, result-3]
```

Diễn giải:

1. `Flux.just(1, 2, 3)` phát ba mã theo thứ tự 1 → 2 → 3.
2. Mapper tạo ba `Mono` riêng. Vì `maxConcurrency = 3`, toán tử có thể đăng ký cả ba publisher con mà không đợi publisher đầu tiên hoàn tất.
3. Với độ trễ giả lập, publisher con 2 và 3 thường hoàn tất trước 1. **Các log quan sát nội bộ, nếu thêm vào, có thể đến theo thứ tự khác tùy lịch scheduler.**
4. `flatMapSequential` giữ kết quả của 2 và 3 đến khi dải dữ liệu của 1 hoàn thành. Vì mỗi inner chỉ phát một phần tử, đầu ra luôn có thứ tự `result-1`, `result-2`, `result-3` nếu pipeline hoàn thành bình thường.
5. `collectList()` tích lũy đầu ra thành một `List<String>`, chỉ dùng để in kết quả cuối. `block()` chỉ xuất hiện trong **demo dòng lệnh**; tuyệt đối tránh đặt `block()` trong luồng xử lý WebFlux event loop.

Thay toán tử bằng `flatMap(OrderedMergeDemo::fetch, 3)` thì **không còn bảo đảm** đầu ra theo thứ tự 1, 2, 3. Thay bằng `concatMap(OrderedMergeDemo::fetch)` sẽ giữ thứ tự nhưng khởi động từng publisher con tuần tự, nên ba khoảng chờ không còn chồng lấp tương tự.

**Không suy ra thông lượng cao hơn chỉ từ một phép đo vài trăm mili giây.** Tốc độ thật còn phụ thuộc việc thực hiện I/O có non-blocking hay không, giới hạn downstream, kích thước dữ liệu, connection pool, độ trễ dài đuôi và chính sách lỗi.

## 7. Khi một đầu vào tạo nhiều giá trị

Không phải mapper nào cũng trả `Mono`. Có thể một mã lớp học được mở rộng thành nhiều bài học, hoặc một nhóm hàng được chuyển thành nhiều item. Khi mapper trả `Flux`, `flatMapSequential` giữ dữ liệu của **toàn bộ inner trước** rồi mới phát dữ liệu của inner sau, ngay cả khi inner sau đã có phần tử sẵn.

Ví dụ Java độc lập khác có thể đặt trong `src/main/java/MultiValueDemo.java` cùng `pom.xml`:

```java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;

public class MultiValueDemo {
    public static void main(String[] args) {
        List<String> values = Flux.just("A", "B")
            .flatMapSequential(group -> {
                if (group.equals("A")) {
                    return Flux.just("A1", "A2")
                        .delayElements(Duration.ofMillis(60));
                }
                return Flux.just("B1", "B2");
            }, 2, 1)
            .collectList()
            .block();

        System.out.println(values);
    }
}
```

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultiValueDemo
```

Stdout:

```text
[A1, A2, B1, B2]
```

Dù inner B có thể sẵn sàng trước, nó không được xen giữa A1 và A2. Lưu ý `delayElements` là một publisher bất đồng bộ, còn `Flux.just("B1", "B2")` có thể phát đồng bộ khi được đăng ký. Operator vẫn giữ dải B đến đúng lượt. **Thứ tự bên trong mỗi publisher con** được giữ theo thứ tự chính publisher đó phát; nếu bản thân inner đã dùng `flatMap` làm xáo trộn thứ tự, `flatMapSequential` ở bên ngoài không tự sắp xếp lại các phần tử trong inner theo ID nghiệp vụ.

### Trường hợp publisher con rỗng

Nếu `fetch(id)` trả `Mono.empty()` cho ID 2 thì downstream của ví dụ một phần tử/inner có thể nhận `result-1`, `result-3`, rồi complete. Thứ tự vẫn đúng, nhưng **không còn quan hệ một-một với ID**. Nếu API yêu cầu đúng một kết quả (kể cả “not found”) cho mỗi ID, cần chuyển trường hợp rỗng thành một kết quả hợp lệ:

```java
Flux<LookupOutcome> outcomes = ids.flatMapSequential(
    id -> service.find(id)
        .map(value -> LookupOutcome.found(id, value))
        .switchIfEmpty(Mono.just(LookupOutcome.missing(id))),
    8, 1
);
```

`LookupOutcome`, `service` và `ids` là kiểu/đối tượng của ứng dụng thực tế; đoạn này minh họa thiết kế, không phải chương trình biên dịch độc lập. Chọn mô hình “missing” phù hợp để không mất ánh xạ giữa đầu vào và đầu ra. `Mono.just(null)` không phải cách biểu diễn thiếu kết quả trong Reactor.

## 8. Vì sao toán tử giữ thứ tự vẫn có thể gây nghẽn?

`flatMapSequential` tạo cơ hội đồng thời nhưng đánh đổi bằng việc **giữ kết quả của inner nhanh đang đứng sau inner chậm**. Điều này thường được gọi là *head-of-line blocking* ở phía phát kết quả.

Giả sử 20 request bắt đầu sớm, request đầu mất 10 giây, 19 request còn lại mất 100 ms. Với thứ tự bắt buộc, downstream có thể chưa nhận được kết quả của 19 request nhanh trong lúc chờ request 1. Những kết quả này cần được giữ lại trong bộ nhớ/hàng đệm; kích thước còn phụ thuộc số publisher đang hoạt động, lượng dữ liệu của từng inner và backpressure.

Dấu hiệu nhận biết:

- Độ trễ nhận kết quả ở client tăng, mặc dù phần lớn request nội bộ đã kết thúc.
- Heap/queue tăng do lưu kết quả đến sớm từ những inner chưa đến lượt.
- Thread không bị chặn vẫn có thể **bị nghẽn về tiến độ phát** vì yêu cầu giữ thứ tự.
- Một inner không bao giờ complete khiến các inner đứng sau **không được phát** dù có thể đã chạy xong.

Do đó, `flatMapSequential` là lựa chọn khi **thứ tự đầu ra thực sự là hợp đồng của API**. Nếu người dùng muốn thấy kết quả nào xong trước hiện trước, `flatMap` thường đáp ứng hợp lý hơn.

### Tối ưu có kiểm soát

- Giảm `maxConcurrency` để hạn chế publisher con in-flight và khối lượng kết quả chờ.
- Điều chỉnh `prefetch` dựa vào kích thước item, request từ downstream và tốc độ nguồn; không coi `prefetch` là “giới hạn byte bộ nhớ”.
- Đặt timeout cho từng tác vụ con để không có một phần tử đầu tiên chặn vô hạn các phần tử sau.
- Chia batch nhỏ, tối ưu endpoint chậm hoặc dùng một API bulk nếu hệ thống phụ trợ hỗ trợ.
- Nếu thứ tự không còn bắt buộc, chọn `flatMap` để chuyển sang phát theo thời điểm dữ liệu sẵn sàng.
- Với kết quả lớn, tránh tích lũy toàn bộ bằng `collectList()` trong production chỉ để “giữ thứ tự”: `flatMapSequential` đã bảo toàn thứ tự stream; không cần gom hết trừ khi thực sự phải trả về một danh sách.

## 9. Hiểu đúng maxConcurrency và prefetch

### maxConcurrency giới hạn publisher con, không phải số thread

`maxConcurrency = 8` cho phép tối đa tám inner đang đăng ký cùng lúc trong pipeline đó. Nếu mapper trả publisher xử lý I/O non-blocking, nhiều tác vụ có thể chờ mạng đồng thời. Nhưng nếu mapper gọi `Thread.sleep` hoặc repository JDBC đồng bộ **ngay khi tạo publisher**, phép gọi đồng bộ này có thể chặn thread gọi mapper:

```java
// SAI trong event loop: công việc chặn chạy ngay khi mapper được gọi.
.flatMapSequential(id -> Mono.just(legacyClient.fetchBlocking(id)), 8)
```

Đoạn trên là mảnh ghép minh họa (không biên dịch độc lập khi thiếu `legacyClient`). `Mono.just(...)` **đánh giá đối số ngay lập tức**, nên thao tác blocking đã xảy ra trước khi publisher được dựng xong. Tăng `maxConcurrency` sẽ không sửa được bản chất blocking.

Nếu bắt buộc dùng thư viện đồng bộ, cô lập lời gọi theo cách thích hợp:

```java
.flatMapSequential(
    id -> Mono.fromCallable(() -> legacyClient.fetchBlocking(id))
        .subscribeOn(Schedulers.boundedElastic()),
    8, 1
)
```

Trong ứng dụng thật, cần import `reactor.core.scheduler.Schedulers` và quản lý timeout, giới hạn thread/queue, connection pool, tải tổng và hủy tác vụ. `boundedElastic` giúp tách đoạn blocking khỏi event loop, **không biến I/O đó thành non-blocking**, cũng không bảo đảm tác vụ chặn có thể bị dừng tức thì khi cancel. Ưu tiên WebClient/R2DBC/driver reactive khi có thể.

### prefetch và backpressure

Reactive Streams cho phép downstream gọi `request(n)`; operator truyền/biến đổi nhu cầu sang upstream và inner. `prefetch` định hướng số lượng phần tử mỗi publisher con được yêu cầu sớm. Với inner phát nhiều bản ghi, request quá lớn có thể làm tăng dữ liệu chờ; request quá nhỏ có thể tạo nhiều đợt yêu cầu và làm giảm thông lượng. Buffer có thể chịu áp lực khi inner trước chậm và inner sau phát nhanh.

Không thể suy ra “tối đa `maxConcurrency × prefetch` phần tử trong toàn bộ ứng dụng” như một bảo đảm cứng: bản thân upstream, thư viện khách HTTP, bộ đệm mạng, từng publisher con và các toán tử khác có thể có hàng đệm riêng. Giới hạn hợp lý cần có thử tải và quan sát số subscription, byte buffered, throughput, độ trễ P95/P99 và cancellation.

## 10. Xử lý lỗi, timeout và cancellation

### Một inner lỗi thì sao?

Trong dạng `flatMapSequential` thông thường, lỗi từ publisher con được chuyển thành lỗi của pipeline; cần dự kiến khả năng các công việc khác bị hủy và dữ liệu đang đệm bị loại bỏ. Không nên hứa rằng mọi kết quả từ inner trước hoặc sau sẽ tiếp tục được phát khi một inner thất bại.

Nếu mỗi ID có thể thất bại nhưng API phải trả về một bản ghi kết quả cho **từng ID theo thứ tự**, xử lý lỗi **ở trong mapper**, chuyển chúng thành kết quả nghiệp vụ có kiểu rõ ràng:

```java
Flux<LookupOutcome> outcomes = ids.flatMapSequential(
    id -> service.find(id)
        .map(value -> LookupOutcome.found(id, value))
        .switchIfEmpty(Mono.just(LookupOutcome.missing(id)))
        .onErrorResume(ex ->
            Mono.just(LookupOutcome.failed(id, ex.getClass().getSimpleName()))),
    8, 1
);
```

Ví dụ ứng dụng (cần định nghĩa `LookupOutcome` và `service`) này không biến lỗi thành một giá trị `null`, mà tạo một đối tượng có trạng thái rõ ràng. Đừng vô điều kiện nuốt mọi exception ở production: cần phân biệt lỗi nghiệp vụ, lỗi hạ tầng, retry có điều kiện, log/metrics và yêu cầu bảo mật thông tin lỗi.

Reactor còn có overload `flatMapSequentialDelayError(mapper, maxConcurrency, prefetch)` để **trì hoãn báo lỗi** trong lúc xử lý backlog, nhưng kết quả cuối vẫn là một luồng lỗi nếu có inner thất bại; nó không mặc nhiên tạo một bản ghi lỗi tương ứng mỗi ID. Dùng sau khi đã xác định chính xác hợp đồng phát một phần, hoàn thành và ý nghĩa của lỗi.

### Một inner chờ mãi thì sao?

Ví dụ `Flux.just(1, 2).flatMapSequential(id -> id == 1 ? Mono.never() : Mono.just("two"), 2, 1)` có thể đã có dữ liệu từ ID 2, nhưng downstream **không nhận “two”** vì ID 1 chưa complete. Để giới hạn chờ một ID, gắn `timeout` bên trong mapper:

```java
.flatMapSequential(
    id -> service.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
            ex -> Mono.just(Result.timeout(id))),
    8, 1
)
```

Đây là fragment tích hợp, cần `Duration`, `TimeoutException`, `service`, `Result` và import trong ứng dụng thực. Với Java `java.util.concurrent.TimeoutException`, toán tử `timeout` của Reactor phát lỗi timeout khi điều kiện quá hạn của nó được thỏa. Fallback giúp downstream có một kết quả lỗi có cấu trúc để tiếp tục phát đúng thứ tự. **Không đặt một timeout toàn chuỗi rồi mặc định đó là timeout riêng từng ID.** Vị trí của `timeout` quyết định phạm vi áp dụng.

### Downstream hủy giữa chừng

Nếu subscriber hủy, các inner đang hoạt động thường được hủy theo khả năng của publisher. Trong WebFlux, client ngắt kết nối có thể làm subscription bị cancel. **Hủy không bảo đảm rollback tác dụng phụ đã phát sinh** như gọi API thanh toán, gửi tin nhắn hay ghi database. Với nghiệp vụ có tác dụng phụ, cần idempotency key hoặc mô hình transaction phù hợp; `flatMapSequential` chỉ sắp xếp dữ liệu phát, không tuần tự hóa các tác dụng phụ đó.

Đừng gọi `subscribe()` thủ công trong controller rồi trả về một `Flux` khác; điều đó tách quá trình xử lý khỏi lifecycle, cancellation và error handling của HTTP request. Trả trực tiếp publisher cho WebFlux.

## 11. Đưa flatMapSequential vào Spring WebFlux

Giả sử API nhận danh sách ID theo thứ tự người dùng lựa chọn và lấy thông tin từ một dịch vụ reactive bên ngoài. Handler muốn trả dữ liệu **theo thứ tự ID nhận được**, dù các HTTP call phụ trợ hoàn thành không cùng thứ tự.

Đoạn code dưới đây là **một phần controller Spring WebFlux**, không phải chương trình độc lập: cần một bean `ProfileService` có phương thức `Mono<ProfileDto> fetch(long id)` và DTO tương ứng.

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @GetMapping("/lookup")
    public Flux<ProfileDto> lookup(@RequestParam List<Long> ids) {
        return Flux.fromIterable(ids)
            .flatMapSequential(service::fetch, 8, 1);
    }
}
```

Ví dụ các ID yêu cầu là `[41, 7, 19]`. Dù `fetch(7)` hoàn thành trước `fetch(41)`, stream downstream vẫn phát kết quả của 41 trước 7, rồi 19, nếu cả ba publisher con đều phát một giá trị và hoàn thành bình thường. Nếu `fetch(41)` trả rỗng, kết quả 41 không xuất hiện; thứ tự **các kết quả thực sự phát** vẫn theo nguồn. Nếu cần một kết quả trên mỗi ID, thêm chiến lược `switchIfEmpty` tương ứng.

Với HTTP response, hãy phân biệt:

- `Flux<ProfileDto>` được WebFlux đăng ký và chuyển thành response theo cơ chế encoding và media type đã cấu hình.
- Nếu muốn stream từng item ngay khi có thể, cân nhắc `application/x-ndjson` hoặc SSE tùy hợp đồng API; JSON array thông thường có thể được encode/buffer theo cách khác.
- Vì `flatMapSequential` giữ thứ tự, item nhanh vẫn có thể bị hoãn phát cho tới khi item trước sẵn sàng.
- Nếu một inner lỗi sau khi HTTP response đã bắt đầu gửi, server có thể không còn đổi status code thành công sang mã lỗi theo cách thông thường. Cần thiết kế giao thức kết quả từng item và error mapping.
- Thứ tự HTTP response là thứ tự của pipeline, không phải cam kết rằng các lệnh gọi hệ thống ngoài hoặc lệnh ghi side effect đã chạy theo đúng trình tự ấy.

**Không dùng `collectList().block()` trong controller.** Nếu bắt buộc trả về một JSON array hoàn chỉnh, có thể dùng `collectList()` để nhận `Mono<List<ProfileDto>>` rồi để framework subscribe, nhưng phải chủ động đánh giá chi phí bộ nhớ và độ trễ.

## 12. Kiểm thử hợp đồng bằng StepVerifier và Sinks

Ví dụ thời gian thực có thể làm thứ tự tác vụ con hoàn tất khác nhau ở mỗi lần chạy. Muốn kiểm thử **bảo đảm thứ tự** một cách quyết định, dùng `Sinks.One` để tự điều khiển thời điểm mỗi inner phát dữ liệu. Thêm file `src/test/java/OrderedMergeTest.java` (dùng dependency test trong `pom.xml` đã nêu):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

public class OrderedMergeTest {

    @Test
    void emitsInInputOrderEvenWhenSecondFinishesFirst() {
        Sinks.One<String> first = Sinks.one();
        Sinks.One<String> second = Sinks.one();

        AtomicInteger subscriptions = new AtomicInteger();

        Flux<String> output = Flux.just(1, 2)
            .flatMapSequential(id -> {
                Mono<String> inner =
                    id == 1 ? first.asMono() : second.asMono();
                return inner.doOnSubscribe(s ->
                    subscriptions.incrementAndGet());
            }, 2, 1);

        StepVerifier.create(output)
            .expectSubscription()
            .then(() -> assertEquals(2, subscriptions.get()))
            .then(() -> assertEquals(
                Sinks.EmitResult.OK,
                second.tryEmitValue("second")))
            .expectNoEvent(Duration.ofMillis(20))
            .then(() -> assertEquals(
                Sinks.EmitResult.OK,
                first.tryEmitValue("first")))
            .expectNext("first", "second")
            .verifyComplete();
    }

    @Test
    void respectsMaxConcurrency() {
        AtomicInteger started = new AtomicInteger();

        Flux<Integer> output = Flux.range(1, 5)
            .flatMapSequential(
                id -> Mono.<Integer>never()
                    .doOnSubscribe(s -> started.incrementAndGet()),
                2, 1);

        StepVerifier.create(output)
            .expectSubscription()
            .then(() -> assertEquals(2, started.get()))
            .thenCancel()
            .verify();
    }

    @Test
    void preservesWholeInnerSequences() {
        Flux<String> output = Flux.just("A", "B")
            .flatMapSequential(group -> {
                if (group.equals("A")) {
                    return Flux.just("A1", "A2");
                }
                return Flux.just("B1", "B2");
            }, 2, 1);

        StepVerifier.create(output)
            .expectNext("A1", "A2", "B1", "B2")
            .verifyComplete();
    }
}
```

Chạy test:

```bash
mvn -q test
```

Nếu môi trường đã tải đủ dependency, Maven kết thúc thành công với exit code 0 khi cả ba test pass. Không có yêu cầu phải in một chuỗi stdout cụ thể từ test.

**Bài test thứ nhất quan trọng nhất:**

1. Sau subscribe, assert rằng cả **hai inner đã được đăng ký** (minh họa tính eager với `maxConcurrency = 2`).
2. Hoàn thành **second trước first**; assert không có sự kiện đầu ra trong khoảng quan sát ngắn, vì first chưa xong.
3. Hoàn thành first; downstream nhận `first` rồi `second` và complete.
4. Không dùng `Thread.sleep` để “đoán” thứ tự kết quả. Test điều khiển sự kiện bằng sink và chỉ dùng khoảng 20 ms để kiểm tra **không phát ra trước khi tới lượt**, thay vì khẳng định thời gian thực thi chính xác.

Bài test thứ hai giữ mọi inner ở trạng thái `never()`, vì vậy chỉ hai inner đầu được đăng ký theo `maxConcurrency=2`; sau đó chủ động cancel để test không treo. Bài test thứ ba chứng minh kết quả nhiều phần tử được giữ thành từng dải.

Để kiểm tra tải thực tế, ngoài unit test còn phải đánh giá tỷ lệ lỗi, độ trễ từng inner, kích thước kết quả, memory, cancellation và giới hạn connection pool. Một phép thử tuần tự đầu vào nhỏ không đại diện cho điều kiện mạng dao động trong production.

## 13. Lưu ý về tính đồng thời, scheduling và side effect

Ba thuật ngữ thường bị trộn lẫn:

- **Concurrency (nhiều tác vụ đang tiến triển):** các publisher con được đăng ký và có thể chờ kết quả độc lập cùng lúc.
- **Parallelism (chạy CPU cùng thời điểm):** công việc thực thi thực sự trên nhiều core/thread; không được `flatMapSequential` tự tạo ra nếu toàn bộ inner đồng bộ trên một thread.
- **Ordering (thứ tự downstream thấy):** operator gom dữ liệu và phát theo thứ tự publisher con; không tự khóa dữ liệu dùng chung hay tuần tự hóa các thao tác ghi bên ngoài.

Nếu mapper trả nguồn bất đồng bộ như WebClient, R2DBC hay `Mono.delay`, concurrency có ích rõ ràng. Nếu mapper trả `Mono.just(doBlockingWork())`, tác vụ đã chạy đồng bộ trước khi publisher được dựng, có thể chặn event loop; phải thiết kế lại nguồn hoặc cô lập blocking có kiểm soát.

**Không dùng `flatMapSequential` để đảm bảo nghiệp vụ như “chỉ cập nhật số dư theo đúng thứ tự ID”** khi inner đã bắt đầu thao tác ghi đồng thời. Nếu quy tắc nghiệp vụ yêu cầu tác vụ B chỉ bắt đầu sau khi A kết thúc, dùng `concatMap` hoặc cơ chế serialization/transaction phù hợp. Nếu chỉ yêu cầu kết quả hiển thị theo danh sách người dùng nhập, `flatMapSequential` có thể thích hợp.

Những quan sát sau giúp tránh hiểu nhầm:

- `doOnSubscribe` và `doOnNext` **bên trong mapper** phản ánh tiến độ inner và có thể xuất hiện khác thứ tự đầu vào.
- `doOnNext` đặt **sau `flatMapSequential`** quan sát thứ tự downstream, vốn được toán tử bảo toàn.
- Không có bảo đảm tất cả inner bắt đầu đúng cùng một thời điểm; mức request/backpressure, scheduler và `maxConcurrency` quyết định thời điểm đăng ký.
- Nếu upstream gửi phần tử theo thứ tự bất định từ nguồn nóng hoặc xử lý trước đó, `flatMapSequential` giữ chính thứ tự **nó nhận**.
- Sự hoàn thành bất thường hoặc cancellation có thể làm mất kết quả chưa phát; phải xem hợp đồng lỗi/hủy khi diễn giải “giữ thứ tự”.

## 14. Lỗi phổ biến và cách sửa

1. **Dùng `flatMap` rồi kỳ vọng thứ tự vì đầu vào là `Flux.just(1,2,3)`.** Nguồn có thứ tự không đồng nghĩa kết quả bất đồng bộ sẽ có thứ tự. Chọn `flatMapSequential` hoặc `concatMap` theo yêu cầu.
2. **Dùng `concatMap` cho mọi trường hợp cần thứ tự.** Nếu nhiều lời gọi I/O độc lập có thể cùng chờ, `flatMapSequential` có thể giúp chồng lấp thời gian chờ. Ngược lại, nếu **tác dụng phụ phải tuần tự**, `concatMap` mới là lựa chọn đúng.
3. **Tăng `maxConcurrency` vô hạn để “càng nhanh càng tốt”.** Có thể làm quá tải downstream, connection pool và bộ nhớ đệm. Chọn giới hạn theo phép đo.
4. **Nhầm `prefetch` với tổng số request API.** Nó liên quan đến nhu cầu phần tử của inner; tổng kết nối, hàng đệm và thread còn phụ thuộc các tầng khác.
5. **Không đặt timeout cho inner có thể treo.** Một inner đầu `never()` có thể giữ mọi kết quả sau mãi mãi. Đặt timeout đúng chỗ và có chiến lược lỗi.
6. **Hiểu “giữ thứ tự” là ghi database theo thứ tự.** Inner đang chạy đồng thời nên side effect vẫn có thể xảy ra khác thứ tự.
7. **Đặt `Thread.sleep`, `block()` hoặc lời gọi đồng bộ trong mapper trên event loop.** Điều này giảm khả năng phục vụ nhiều request và làm méo ý nghĩa concurrency. Dùng API non-blocking hoặc cô lập blocking.
8. **Gom mọi phần tử bằng `collectList()` chỉ để sắp thứ tự.** Operator đã phát theo thứ tự; gom toàn bộ có thể gây chậm first byte và tốn RAM.
9. **Giả định mỗi ID luôn phát đúng một kết quả.** Inner có thể empty, error hoặc nhiều giá trị. Cần thiết kế hợp đồng đầu ra và xử lý từng tình huống.
10. **Không xét hủy và retry.** Retry có thể đăng ký lại inner, lặp side effect; client disconnect có thể hủy pipeline. Phải dùng idempotency với các tác vụ nhạy cảm.
11. **So kết quả log nội bộ với kết quả downstream.** Log inner có thể xuất hiện theo thời gian hoàn thành khác thứ tự, còn đầu ra sau `flatMapSequential` được tuần tự hóa theo nguồn.
12. **Chọn toán tử chỉ theo tên gọi.** “Sequential” ở đây mô tả **thứ tự merge và phát**, không phải mọi thao tác bên trong đều tuần tự.

## 15. Bài tập vận dụng

**Bài 1.** Đầu vào là `[10, 20, 30]`; inner 10 mất 500 ms, inner 20 mất 50 ms, inner 30 mất 100 ms. Giới hạn đồng thời 3. Nếu mỗi inner trả đúng một giá trị, `flatMapSequential` phát thứ tự nào?  
**Đáp án:** `10, 20, 30`. Inner 20 và 30 có thể hoàn thành trước nhưng bị giữ lại tới lượt. Thời gian xuất hiện kết quả đầu tiên có thể lớn vì inner 10 chậm.

**Bài 2.** Nếu yêu cầu “phát kết quả nào sẵn sàng trước để giao diện hiển thị tức thì”, nên dùng toán tử nào?  
**Đáp án:** `flatMap` phù hợp hơn, vì không ràng buộc phát theo thứ tự nguồn. Cần lưu ID vào mỗi kết quả để giao diện gắn đúng đối tượng.

**Bài 3.** Nếu các thao tác là “trừ tiền rồi mới ghi hóa đơn” và bắt buộc việc thứ hai chỉ **bắt đầu** khi việc thứ nhất thành công, `flatMapSequential` có phù hợp không?  
**Đáp án:** Không. Hãy biểu diễn phụ thuộc bằng `then`/`flatMap` trong một chuỗi theo quan hệ phụ thuộc, hoặc `concatMap` đối với các nhiệm vụ tuần tự. Giữ thứ tự **đầu ra** không bảo đảm thứ tự **tác dụng phụ**.

**Bài 4.** Nguồn phát A, B; inner A phát A1 rồi A2, inner B phát B1 rất sớm. Thứ tự mà subscriber của `flatMapSequential` nhận là gì?  
**Đáp án:** A1, A2, B1, nếu tất cả thành công và hoàn thành. Không xen B1 giữa A1 và A2.

**Bài 5.** `maxConcurrency = 2`, nguồn có 100 ID và hai publisher con đầu không bao giờ hoàn thành. Các ID còn lại có chắc được subscribe không?  
**Đáp án:** Không. Hai slot bị chiếm; cần timeout/cancel hoặc thiết kế lại nguồn, và giám sát các tác vụ treo.

**Bài 6.** Inner của ID đầu trả `Mono.empty()`, inner thứ hai trả `Mono.just("B")`. Downstream thấy gì?  
**Đáp án:** Nhận `B` khi inner đầu hoàn thành rỗng rồi inner thứ hai đến lượt. Không có phần tử “null” đại diện cho ID đầu, trừ khi mapper chủ động tạo một kết quả hợp lệ như `Missing(id)`.

**Bài 7.** Nếu `prefetch=1` và `maxConcurrency=4`, có thể khẳng định chương trình chỉ dùng bộ nhớ cho đúng bốn phần tử không?  
**Đáp án:** Không. Đó là các tham số điều chỉnh nhu cầu/đăng ký trong toán tử; upstream, inner, network stack và các toán tử khác vẫn có thể có buffer riêng.

**Bài 8.** Có thể quan sát inner B complete trước inner A, trong khi downstream vẫn chỉ thấy A trước B không?  
**Đáp án:** Có. Đây chính là điểm khác biệt giữa **thứ tự hoàn thành công việc** và **thứ tự phát dữ liệu** của `flatMapSequential`.

## 16. Ghi nhớ và tiêu chí lựa chọn

`flatMapSequential` phù hợp khi **mỗi phần tử nguồn tạo một tác vụ độc lập có thể chạy đồng thời**, nhưng consumer cần nhận kết quả theo **thứ tự nguồn**. Nó đăng ký các publisher con sớm (trong giới hạn `maxConcurrency`), giữ những kết quả đến sớm ở hàng đệm và phát từng dải kết quả theo đúng thứ tự. Cần chấp nhận chi phí buffer và độ trễ do inner đầu chậm; thiết kế timeout, giới hạn đồng thời, xử lý lỗi, cancellation và non-blocking I/O là phần không thể thiếu.

Nếu **không cần thứ tự kết quả**, chọn `flatMap`. Nếu **phải xử lý xong công việc trước rồi mới bắt đầu công việc sau**, chọn `concatMap` hoặc chuỗi phụ thuộc phù hợp. Nếu **cần đồng thời nhưng đầu ra theo thứ tự**, chọn `flatMapSequential` và kiểm thử bằng việc cho inner đứng sau hoàn thành trước.

### Tài liệu tham khảo

- Project Reactor, [Flux Javadoc – flatMapSequential](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html): định nghĩa eager subscription, ordered merge, tham số `maxConcurrency` và `prefetch`.
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).

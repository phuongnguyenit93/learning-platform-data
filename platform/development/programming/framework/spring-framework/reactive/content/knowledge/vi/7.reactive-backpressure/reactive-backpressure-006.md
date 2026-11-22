# `buffer` và `window` làm thay đổi đơn vị nhu cầu trong Project Reactor

## 1. Vấn đề: `request(n)` đang đếm cái gì?

**Backpressure** trong Reactive Streams cho phép phía nhận chủ động yêu cầu số lượng tín hiệu dữ liệu qua `Subscription.request(n)`. Con số `n` đếm **phần tử `onNext` ở ngay giao diện Publisher–Subscriber đang xét**, không mặc định đếm bản ghi gốc, byte, phần tử trong danh sách, hay số lượt gọi I/O.

Trong Spring WebFlux/Project Reactor, toán tử **`buffer`** và **`window`** đều gom luồng thành các nhóm. Nhưng sau khi gom, kiểu phần tử mà downstream nhận đã đổi:

```text
                        mỗi onNext là một Integer
Flux<Integer> ──────────────────────────────────┐
                                               │
             buffer(3)                         window(3)
                 │                                 │
                 ▼                                 ▼
        Flux<List<Integer>>                Flux<Flux<Integer>>
        mỗi onNext là List                  mỗi onNext là một Flux con
        chứa tối đa 3 Integer               (một "cửa sổ")
                 │                                 │
                 ▼                                 ▼
        request(2) = yêu cầu                request(2) = yêu cầu
        tối đa 2 danh sách                  tối đa 2 Flux con
```

Vì thế, nói “downstream `request(2)`” **chưa đủ để kết luận** upstream được yêu cầu đúng hai phần tử ban đầu. Phải xác định toán tử nằm giữa hai phía đang biến đổi đơn vị như thế nào.

Đây là điểm học tập chính:

- Với `buffer(3)`, demand downstream tính theo **số `List<T>`**. Trong trường hợp đệm theo kích thước cố định, không chồng lấn, một yêu cầu cho hai danh sách thường được chuyển thành yêu cầu tối đa **sáu phần tử `T`** upstream.
- Với `window(3)`, demand **bên ngoài** tính theo **số `Flux<T>` con** được phát. Bên trong mỗi cửa sổ lại có **subscription và demand riêng** để tiêu thụ từng `T`. Không thể lấy số window được yêu cầu rồi suy ra toàn bộ nhu cầu dữ liệu bên trong mà bỏ qua các subscriber của window.

Cả hai vẫn phải tuân thủ hợp đồng Reactive Streams: không phát `onNext` vượt demand hợp lệ của từng subscriber; tôn trọng tín hiệu `onComplete`, `onError`, `cancel()` và việc tài nguyên có thể bị giải phóng.

## 2. Nhắc lại cơ chế demand trước khi gom nhóm

Một chuỗi đơn giản:

```java
Flux<Integer> numbers = Flux.range(1, 7);
```

`Flux.range` có thể phát `1..7`, nhưng nó tuân thủ yêu cầu nhận từ subscriber. Với subscriber ban đầu chỉ gọi `request(2)`, nguồn không được phát ba `onNext` trước khi được cấp thêm demand. Lời gọi `request` là **quyền nhận tối đa**, không bảo đảm rằng nguồn luôn có đủ phần tử để gửi.

Khi có toán tử trung gian, ta có ít nhất **hai ranh giới demand**:

```text
[Upstream Publisher<T>]
          │
          │ onNext(T), request(k) upstream
          ▼
[buffer(...) / window(...)]
          │
          │ onNext(R), request(m) downstream
          ▼
[Downstream Subscriber<R>]
```

`k` và `m` không bắt buộc bằng nhau. Toán tử phải **dịch yêu cầu** dựa trên kiểu kết quả và cách nó tiêu thụ dữ liệu; đó là lý do nhu cầu được gọi là đã “đổi đơn vị”.

Đồng thời, `request(n)` không phải thao tác “lấy n bản ghi tức thì”. Nó có thể dẫn đến công việc sau đó, có thể được cộng dồn, và có thể đi qua các toán tử có cơ chế prefetch hoặc hàng đợi.

## 3. `buffer(size)`: từ demand từng phần tử sang demand từng danh sách

### 3.1. Hợp đồng đầu ra

`Flux<T>.buffer(int maxSize)` phát các `List<T>` không chồng lấn, mỗi danh sách chứa tối đa `maxSize` phần tử. Với `maxSize = 3`:

```java
Flux<List<Integer>> batches =
        Flux.range(1, 7).buffer(3);
```

Khi toàn bộ nguồn được tiêu thụ, các giá trị downstream là:

```text
onNext([1, 2, 3])
onNext([4, 5, 6])
onNext([7])
onComplete()
```

**Đầu ra cuối có thể chưa đủ ba phần tử** vì nguồn hoàn tất. Với nguồn rỗng, `buffer(3)` không tự tạo một danh sách rỗng để phát; nó chỉ hoàn tất. Giá trị `size` phải dương.

Số phần tử kết quả trong trường hợp nguồn hữu hạn, không lỗi và `buffer(size)` đơn giản là \(\lceil N/\mathrm{size}\rceil\), với `N = 7`, `size = 3` thì bằng 3. Đây là số **danh sách**, không phải số phần tử gốc.

### 3.2. Cách diễn giải demand

Xét pipeline đơn giản, không có `filter`, `publishOn` hoặc toán tử khác thay đổi nhu cầu:

```text
Flux.range(1, 7)  ->  buffer(3)  ->  Subscriber<List<Integer>>
                                            |
                                         request(1)
```

Sau `request(1)` ở phía sau `buffer`:

1. Subscriber xin **một `List<Integer>`**.
2. `buffer(3)` cần tới **ba phần tử `Integer`** để đóng một danh sách đầy đủ, nên điều chỉnh yêu cầu upstream tương ứng.
3. Khi nhận các số 1, 2, 3, toán tử phát `onNext([1,2,3])`.
4. Nếu downstream chưa yêu cầu thêm, toán tử không được phát danh sách thứ hai cho subscriber ấy.
5. Khi downstream `request(1)` tiếp, nó có quyền nhận thêm một **danh sách**, chứ không phải chỉ một số.

Ví dụ chuyển đổi nhu cầu ở trường hợp cố định này:

| Downstream gọi | Đơn vị được yêu cầu | Số phần tử upstream cần cho nhóm đủ kích thước |
|---|---|---|
| `request(1)` | 1 `List<T>` | Tối đa 3 `T` cho `buffer(3)` |
| `request(2)` | 2 `List<T>` | Tối đa 6 `T` cho `buffer(3)` |
| `request(1)` sau hai danh sách đầy | 1 `List<T>` nữa | Có thể chỉ còn một `T` ở cuối nguồn |

**Giới hạn của bảng:** đây là mô hình đơn giản để lý giải `buffer(3)` không chồng lấn. Không dùng công thức `n × size` làm quy luật của *mọi* phiên bản buffer, mọi chain hay mọi tác vụ I/O. Nếu upstream hoàn tất sớm, toán tử có thể phát danh sách cuối chưa đầy; nếu nguồn chậm thì vẫn phải chờ dữ liệu.

Trong một pipeline nhiều tầng, các toán tử ở **mỗi tầng** có thể tiếp tục thay đổi lượng request: `filter` có thể bỏ phần tử, `publishOn` có thể prefetch, `flatMap` có nhiều inner publisher. Đo demand bằng tín hiệu/metric thực tế khi tối ưu hiệu năng.

### 3.3. `buffer` lưu dữ liệu ở đâu?

`buffer(3)` phải giữ các phần tử của **danh sách đang tạo** trong bộ nhớ cho đến khi đủ ba phần tử hoặc có điều kiện đóng buffer. Nếu có nhiều nhóm đang mở, hoặc biến thể buffer theo thời gian/biên, bộ nhớ có thể tăng theo số lượng và kích thước nhóm.

Gom theo batch có thể giảm số lần gọi xử lý nghiệp vụ, ví dụ một batch ghi xuống DB, nhưng không tự giảm dung lượng dữ liệu cần giữ; cũng không có nghĩa backend sẽ thực thi một transaction cho mỗi List nếu ứng dụng chưa thiết kế transaction.

## 4. `window(size)`: demand có hai tầng

### 4.1. Outer Flux và inner Flux

`Flux<T>.window(int maxSize)` phát một luồng **gồm các Publisher con**; mỗi Publisher con đại diện cho một nhóm phần tử:

```java
Flux<Flux<Integer>> windows =
        Flux.range(1, 7).window(3);
```

Hình dung kết quả:

```text
Outer Flux<Flux<Integer>>
      |
      +-- onNext(window 1) -> inner Flux: 1, 2, 3
      +-- onNext(window 2) -> inner Flux: 4, 5, 6
      +-- onNext(window 3) -> inner Flux: 7
      +-- onComplete()
```

Điểm khác `buffer`: outer không phát `[1,2,3]` dưới dạng `List<Integer>`; nó phát một **`Flux<Integer>` con**. Phần tử trong Flux con có thể được xử lý theo luồng, chẳng hạn `reduce`, `map`, `filter`, `take`, thay vì phải thu thập hết vào danh sách trước.

### 4.2. Hai quan hệ subscription/demand

```text
                                request(w) theo số WINDOW
Subscriber<Flux<T>> ────────────────────────────────────┐
       ▲                                                │
       │ onNext(innerFlux)                              ▼
       └─────────────────────── window(3) <──── Upstream<T>
                                      │
                                      └── innerFlux ──> Subscriber<T>
                                                        request(e) theo T
```

Ta cần tách bạch:

1. **Outer demand:** subscriber của `Flux<Flux<T>>` gọi `request(w)` để xin tối đa `w` **đối tượng window**.
2. **Inner demand:** khi một window được subscribe, subscriber của window ấy gọi `request(e)` để xin tối đa `e` **phần tử `T` của window**.
3. **Nhu cầu upstream thực tế** được toán tử window điều phối theo quá trình mở/đóng cửa sổ, nhu cầu outer, nhu cầu inner, buffering và các request đã có. Không được diễn giải `request(1)` outer là “chỉ một phần tử `T` sẽ được đọc”.

Ví dụ:

- Downstream outer `request(1)` cho phép phát **một `Flux<Integer>` con**.
- Nếu dùng `concatMap(window -> window.reduce(0, Integer::sum))`, operator đăng ký window, gom tổng từ các tín hiệu bên trong rồi phát **một tổng** cho mỗi window.
- Nếu tạo ra các window nhưng **không tiêu thụ chúng**, dữ liệu/queue có thể bị giữ lại hoặc pipeline có thể mắc kẹt do thiếu demand; việc phát window không thay thế việc tiêu thụ các phần tử bên trong.

Với `window(3)` đơn giản, không có nghĩa mọi phần tử phải vào một `List` được vật chất hóa trước khi window xuất hiện. Tuy nhiên, **không được kết luận window luôn dùng bộ nhớ O(1)**: kết quả phụ thuộc số window đang mở, hàng đợi, operator downstream và tốc độ consumer.

## 5. So sánh bản chất `buffer` và `window`

| Tiêu chí | `buffer(3)` | `window(3)` |
|---|---|---|
| Kiểu nguồn | `Flux<T>` | `Flux<T>` |
| Kiểu kết quả | `Flux<List<T>>` | `Flux<Flux<T>>` |
| Một `onNext` outer chứa | Một danh sách các phần tử | Một Publisher con |
| Đơn vị `request(1)` của outer subscriber | Một **List** | Một **window** |
| Demand bổ sung bên trong | Không có subscription Reactive Streams riêng cho từng List | Từng inner Flux được subscribe/tiêu thụ theo demand riêng |
| Khi nhóm kết thúc bình thường | Phát List đầy hoặc List cuối chưa đầy nếu nguồn complete | Inner Flux kết thúc; outer hoàn tất khi không còn window |
| Cách xử lý phổ biến | Gọi API batch, chuyển List sang DTO tổng hợp | `concatMap`/`flatMap` trên từng Flux con, xử lý dần dữ liệu bên trong |
| Bộ nhớ | Cần chứa nội dung các List đang tạo | Có thể xử lý dạng stream; vẫn có queue và nguy cơ tích lũy nếu inner chậm |
| Lỗi hay gặp | Nghĩ rằng `request(1)` nhận một `T` | Nghĩ rằng outer `request(1)` đã tiêu thụ tất cả `T` trong window |

Cả hai dùng để **chia nhóm dữ liệu**. Chúng không tự biến nguồn blocking thành non-blocking, không tự mở thread, và không thay thế cơ chế giới hạn tải khi upstream có thể tạo dữ liệu không giới hạn.

## 6. Ví dụ hoàn chỉnh Java 17+ với Project Reactor

Ví dụ dùng `Flux.range` (nguồn cold, đồng bộ, hữu hạn) để có stdout rõ ràng. Chương trình gồm ba phần:

1. `BaseSubscriber<List<Integer>>` tự gọi `request(1)` để minh họa demand theo **danh sách**.
2. `window(3)` được `concatMap` tiêu thụ từng window và thu thành List **chỉ để hiển thị rõ ranh giới cửa sổ**.
3. `window(3)` kết hợp `reduce` để tính tổng mỗi window, không cần tạo List ở bước này.

Tạo các file:

```text
reactor-demand-groups/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-demand-groups</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class Main {
    public static void main(String[] args) {
        // I. Sau buffer(3), mỗi request(1) xin MỘT DANH SÁCH.
        Flux.range(1, 7)
                .buffer(3)
                .subscribe(new BaseSubscriber<List<Integer>>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        System.out.println("request 1 batch");
                        request(1);
                    }

                    @Override
                    protected void hookOnNext(List<Integer> batch) {
                        System.out.println("buffer: " + batch);

                        // Tiếp tục cho đến khi nhận buffer cuối chưa đầy.
                        if (batch.size() == 3) {
                            request(1);
                        }
                    }

                    @Override
                    protected void hookOnComplete() {
                        System.out.println("buffer complete");
                    }
                });

        // II. Mỗi window là một inner Flux. collectList chỉ để xem nội dung.
        Flux.range(1, 7)
                .window(3)
                .concatMap(inner -> inner.collectList())
                .subscribe(
                        list -> System.out.println("window: " + list),
                        error -> System.out.println("window error: " + error),
                        () -> System.out.println("window complete")
                );

        // III. Xử lý stream bên trong từng window bằng reduce.
        Flux.range(1, 7)
                .window(3)
                .concatMap(inner -> inner.reduce(0, Integer::sum))
                .subscribe(
                        total -> System.out.println("sum: " + total),
                        error -> System.out.println("sum error: " + error)
                );
    }
}
```

Từ thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Stdout do chương trình in (không kể các log môi trường nếu Maven có cấu hình riêng):

```text
request 1 batch
buffer: [1, 2, 3]
buffer: [4, 5, 6]
buffer: [7]
buffer complete
window: [1, 2, 3]
window: [4, 5, 6]
window: [7]
window complete
sum: 6
sum: 15
sum: 7
```

**Đọc trace:**

- `BaseSubscriber` thay đổi mẫu mặc định bằng cách chỉ `request(1)` ngay khi subscribe. Đơn vị xin cấp lúc đó là **một `List<Integer>`**.
- Sau mỗi List đầy ba số, `hookOnNext` lại xin thêm **một List**. Cuối nguồn có List `[7]` và tín hiệu `onComplete`; không cần tự yêu cầu thêm khi đã kết thúc.
- `window(3)` tạo ba Flux con. `concatMap` đăng ký chúng theo thứ tự và `collectList()` chỉ gom nội dung **từng** window để hiển thị.
- Ở phép tính tổng, `reduce(0, Integer::sum)` tích lũy một số nguyên cho mỗi window, nhận các phần tử lần lượt. Cách dùng này thể hiện lợi ích của **xử lý inner Flux**; không cần tạo một danh sách cuối cùng của tất cả phần tử.

**Phân biệt rõ:** stdout cho thấy **giá trị** và **thứ tự** của nguồn đồng bộ này; nó không tự chứng minh số lần request upstream. Để xem số request thật trong một pipeline cụ thể, dùng `doOnRequest` tại từng vị trí quan sát hoặc kiểm thử với `StepVerifier` và publisher kiểm soát demand.

## 7. Quan sát sự thay đổi demand bằng `doOnRequest`

Một đoạn minh họa có chủ đích đặt log ở **hai phía của `buffer(3)`**:

```java
Flux<List<Integer>> batches = Flux.range(1, 7)
        .doOnRequest(n -> System.out.println("upstream asks: " + n))
        .buffer(3)
        .doOnRequest(n -> System.out.println("downstream asks: " + n));
```

Đây là **đoạn mã trong ngữ cảnh đã import `Flux` và `List`**, chưa là chương trình chạy độc lập cho đến khi thêm subscriber. Nếu subscriber gọi `request(1)` đối với `batches`, log đặt sau `buffer` cho biết yêu cầu **một danh sách**, còn log trước `buffer` quan sát yêu cầu theo **phần tử `Integer`** (trong cấu hình đơn giản này, một danh sách đầy cần ba số).

Chú ý thứ tự log của `doOnRequest` phụ thuộc vị trí các operator và chuỗi gọi request; không suy diễn rằng mọi phép `request` sẽ tạo chính xác một dòng log hay theo một thứ tự in cố định ở mọi scheduler. Đặc biệt, `doOnRequest` là **công cụ quan sát**, không phải phương pháp tính chính sách prefetch của toàn bộ ứng dụng từ một con số.

Thử đặt log ở đầu và cuối `window(3)`:

```java
Flux<Flux<Integer>> windows = Flux.range(1, 7)
        .doOnRequest(n -> System.out.println("source T request: " + n))
        .window(3)
        .doOnRequest(n -> System.out.println("outer window request: " + n));
```

Log outer đo **số inner Flux được yêu cầu**, trong khi log upstream đo **số Integer**. Nếu muốn biết số phần tử được tiêu thụ trong mỗi window, phải quan sát *inner publisher* khi nó được subscribe, ví dụ dùng `inner.doOnRequest(...)` trong hàm xử lý window. Đó là hai phạm vi demand khác nhau.

## 8. Các biến thể làm công thức demand phức tạp hơn

### 8.1. Kích thước và bước bắt đầu: `buffer(size, skip)`

Khi `skip == size`, các nhóm không chồng lấn và không có khoảng trống. Khi khác nhau:

- `skip < size`: **chồng lấn**. Một phần tử nguồn có thể thuộc **nhiều List**.
- `skip > size`: **có khoảng trống**. Một số phần tử nguồn không đi vào List kết quả.

Ví dụ `buffer(3, 2)` với nguồn `1..6` có các nhóm bắt đầu tại 1, 3, 5:

```text
[1, 2, 3]
[3, 4, 5]
[5, 6]       <- nhóm cuối chưa đầy khi nguồn kết thúc
```

Trong dạng chồng lấn, hai yêu cầu danh sách **không tương đương** với hai tập 3 phần tử hoàn toàn độc lập: có dữ liệu dùng chung. Trong dạng có khoảng trống, upstream còn phải đi qua các phần tử không xuất hiện trong đầu ra. Vì vậy, yêu cầu upstream được operator dịch theo **kích thước và khoảng bước**; không áp dụng máy móc `demand × size` cho mọi biến thể.

`window(size, skip)` cũng có thể mở các window chồng lấn hoặc bỏ khoảng trống; demand inner/outer khi ấy cần được xem cùng cấu hình cửa sổ và subscriber.

### 8.2. Buffer/window theo thời gian hoặc tín hiệu biên

- `bufferTimeout(maxSize, maxTime)` có thể đóng một List khi đủ kích thước **hoặc** hết thời gian; số phần tử của mỗi List không cố định.
- `windowTimeout(maxSize, maxTime)` có thể đóng inner Flux dựa trên kích thước **hoặc** thời gian.
- Các dạng theo boundary, predicate (`bufferUntil`, `windowUntil`, `bufferWhile`, `windowWhile`, ...) có chính sách mở/đóng nhóm dựa trên tín hiệu hoặc điều kiện, khác với `buffer(3)`/`window(3)`.

Thời gian và boundary làm số phần tử thực tế mỗi nhóm thay đổi; không thể dự báo nhu cầu upstream chỉ từ một kích thước nhóm cố định. Một số biến thể có tham số về chiến lược backpressure/buffering riêng, cần đọc chính xác API đang dùng.

## 9. Những lỗi triển khai điển hình

### Lỗi A: Nhầm demand danh sách với demand phần tử

Phản ví dụ về suy luận: “`buffer(100)` nhận `request(1)` thì chỉ được phép đọc một record ở upstream”. Đúng hơn: đó là yêu cầu **một danh sách**; để tạo danh sách đầy, toán tử phải xin/tiêu thụ tới **100 record** upstream trong trường hợp gom nhóm đơn giản. Nếu nhóm có 100 record lớn, một lần phát List cũng có thể chứa nhiều dữ liệu và tốn RAM.

### Lỗi B: Tạo inner window nhưng không tiêu thụ

```java
Flux<Flux<Integer>> windows = Flux.range(1, 100)
        .window(10);

// Đoạn minh họa về kiểu: outer nhận Flux<Integer>, chưa xử lý phần tử.
// Chỉ có subscriber outer không bảo đảm các window con được drain.
```

Nếu ứng dụng chỉ nhận đối tượng window rồi bỏ qua, các giá trị bên trong không được xử lý đúng. Khi demand inner không tiến triển, một số triển khai/toán tử có thể tích trữ dữ liệu, dừng tiến triển hoặc buộc hủy. Hãy xác định rõ mục đích của từng window và tiêu thụ chúng bằng các toán tử điều phối thích hợp.

Thường dùng:

```java
Flux<Integer> sums = Flux.range(1, 100)
        .window(10)
        .concatMap(inner -> inner.reduce(0, Integer::sum));
```

`concatMap` xử lý từng inner Publisher theo thứ tự. `flatMap` có thể xử lý đồng thời nhiều inner publisher, nhưng thứ tự và mức độ concurrency cần được cân nhắc.

### Lỗi C: Thu hết window thành List rồi tưởng không còn buffering

```java
Flux<List<Integer>> lists = Flux.range(1, 100)
        .window(10)
        .concatMap(inner -> inner.collectList());
```

Kết quả có hình dạng gần giống `buffer(10)`, bởi **`collectList()` lại thu phần tử của từng window thành List**. Dùng window không tự khiến pipeline ở trên trở thành streaming không giữ danh sách. Nên chọn `buffer(10)` nếu mục đích chỉ là batch đơn giản, còn chọn `window` khi cần phép xử lý reactive riêng trên mỗi nhóm.

### Lỗi D: Nhầm `buffer(n)` với `onBackpressureBuffer()`

Hai tên có chữ `buffer` nhưng **mục đích khác**:

- `buffer(100)` là **gom nhóm**: một tín hiệu downstream chứa `List<T>` gồm tối đa 100 phần tử.
- `onBackpressureBuffer(...)` là một **chiến lược xếp hàng các phần tử** khi nguồn và downstream có tốc độ không phù hợp. Nó không tự biến kiểu `T` thành `List<T>` và phải hiểu giới hạn hàng đợi/tràn bộ nhớ.

Không chọn `buffer(100)` chỉ vì muốn “chống tràn khi downstream chậm”; cần phân tích toàn bộ nguồn, tốc độ, bộ đệm, hủy và hành vi khi vượt giới hạn.

### Lỗi E: Công việc blocking bên trong từng nhóm

```java
// Phản ví dụ nếu saveBlocking thực hiện I/O đồng bộ chậm.
Flux.range(1, 100)
        .buffer(10)
        .map(batch -> repository.saveBlocking(batch));
```

Dù số lần gọi giảm nhờ batch, đây vẫn là I/O **blocking** nếu repository blocking. Trong WebFlux, việc đó có thể chặn thread xử lý sự kiện. Nên dùng repository non-blocking và operator như `concatMap(batch -> repository.saveBatch(batch))` nếu API trả Publisher; nếu bắt buộc dùng thư viện blocking, cần phân lịch thích hợp (ví dụ `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`) và giới hạn concurrency.

Đoạn này chỉ minh họa cấu trúc; `repository`/các method là thành phần giả định của dự án.

### Lỗi F: Xử lý nhu cầu không kiểm soát ở hai tầng

Nếu outer window được yêu cầu nhanh hơn khả năng subscriber xử lý inner, nhiều window hoặc phần tử chờ có thể tích tụ. Nếu inner bị giữ lại nhưng không subscribe, dữ liệu không được tiêu thụ. Cần chọn `concatMap`, `flatMap` kèm giới hạn concurrency, hoặc các toán tử khác theo yêu cầu thứ tự và tải; quan sát metric/bộ đệm khi dữ liệu lớn.

## 10. Liên hệ thực tế với Spring WebFlux

Giả sử hệ thống nhận các sự kiện dạng `Flux<Event>` từ một API reactive và cần gửi từng lô tới dịch vụ lưu trữ hỗ trợ non-blocking:

```java
// Mã minh họa trong service có sẵn; Event và storageClient là kiểu dự án.
// saveBatch(List<Event>) trả Mono<Void>.
Mono<Void> saveInBatches(Flux<Event> events) {
    return events
            .buffer(100)
            .concatMap(batch -> storageClient.saveBatch(batch))
            .then();
}
```

Khi downstream yêu cầu một lượt kết quả của `concatMap`, `buffer(100)` cấp **một List**; đó là nơi đơn vị nhu cầu đổi từ 100 `Event` thành một batch. `concatMap` chờ xử lý xong batch hiện tại rồi tiếp tục theo thứ tự, nhưng các chiến lược prefetch thực tế của chain vẫn cần được quan sát/điều chỉnh nếu tải cao.

Nếu cần **tính toán streaming trên từng nhóm**, `window` có thể hợp hơn:

```java
// Minh họa: mỗi Event có method amount() trả BigDecimal.
// sumWindow là hàm xử lý reactive do ứng dụng định nghĩa.
Flux<BigDecimal> totals = events
        .window(100)
        .concatMap(window -> window
                .map(Event::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add));
```

Trong ví dụ thứ hai, mỗi window được xử lý từng giá trị, cộng dồn một `BigDecimal`; không cần List 100 sự kiện như đầu vào của API batch. `Event`, `BigDecimal` và `events` thuộc ứng dụng, cần import `java.math.BigDecimal`; đây là **đoạn minh họa trong service**, không phải file biên dịch độc lập.

Việc dùng WebFlux không làm phép tính BigDecimal tự chạy song song. Tính đồng thời phụ thuộc upstream, scheduling và các toán tử. Các chính sách retry, transaction, timeout và hủy phải được thiết kế riêng theo yêu cầu nghiệp vụ.

## 11. Hướng kiểm tra và đo lường

Để chắc chắn không nhầm “đã gom nhóm” với “đã kiểm soát tải”, hãy quan sát ở các ranh giới:

1. **Loại phần tử tại mỗi chặng:** `T`, `List<T>` hay `Flux<T>`?
2. **Đơn vị demand:** `request(1)` xin một phần tử gốc, một List hay một window?
3. **Cách mỗi inner window được tiêu thụ:** có subscriber hay `concatMap`/`flatMap` không, demand có tiến triển không?
4. **Độ lớn thực tế của nhóm:** nhóm cuối có thể nhỏ; các biến thể timeout/boundary có thể đóng sớm.
5. **Bộ nhớ và độ trễ:** số nhóm đang mở, List lớn nhất, hàng đợi upstream/inner và thời gian chờ nguồn.
6. **Ngắt và lỗi:** khi downstream `cancel()` hoặc upstream `onError`, có tài nguyên nào cần cleanup, có phần tử đang đệm bị discard không?

Để kiểm thử demand theo cấu hình cụ thể, có thể sử dụng `reactor-test` và `StepVerifier` với `initialRequest(0)` rồi `thenRequest(...)`. Chọn publisher kiểm soát được nguồn và test cả hai tầng của window. `StepVerifier` thuộc dependency `io.projectreactor:reactor-test`, khác dependency `reactor-core` ở ví dụ chính; không mặc định dự án nào cũng đã có nó.

## 12. Bài tập tự kiểm tra

**Bài 1.** `Flux.range(1, 8).buffer(3)` phát bao nhiêu phần tử `onNext` ở downstream, và mỗi phần tử là gì?

**Đáp án:** Ba `onNext` tương ứng `[1,2,3]`, `[4,5,6]`, `[7,8]`. Mỗi `onNext` là một **List**, nên ba tín hiệu không có nghĩa nguồn chỉ chứa ba `Integer`.

**Bài 2.** Với nguồn trên, subscriber ngay sau `buffer(3)` chỉ `request(1)` thì được phép nhận tối đa bao nhiêu List ở thời điểm đó?

**Đáp án:** Một List. Danh sách đầy đầu tiên cần ba `Integer` ở upstream; muốn nhận List thứ hai phải yêu cầu thêm.

**Bài 3.** `Flux.range(1, 8).window(3)` phát kiểu phần tử nào ở outer? `request(2)` outer có nghĩa là gì?

**Đáp án:** Outer phát các phần tử kiểu `Flux<Integer>`. `request(2)` outer là yêu cầu tối đa **hai inner Flux**, không trực tiếp là yêu cầu hai `Integer`. Mỗi inner Flux còn phải được subscribe/tiêu thụ riêng.

**Bài 4.** Vì sao `window(100).concatMap(w -> w.collectList())` có thể giữ dữ liệu trong bộ nhớ?

**Đáp án:** `collectList()` tích lũy các phần tử của một window thành một List trước khi phát. Dù dùng window ở upstream, chặng này vẫn cần lưu dữ liệu cho mỗi List.

**Bài 5.** `buffer(5, 2)` có thể nhân demand downstream với 5 để tính chính xác request upstream không?

**Đáp án:** Không. Các nhóm có thể chồng lấn (bắt đầu cách hai phần tử nhưng kích thước năm), và các phần tử có thể được dùng cho nhiều nhóm. Request upstream phụ thuộc chính sách toán tử và cấu hình.

**Bài 6.** `buffer(100)` có thay thế hoàn toàn cơ chế bảo vệ một nguồn quá nhanh không?

**Đáp án:** Không. Nó tạo danh sách có kích thước tối đa 100 trong biến thể cơ bản, nhưng không tự kiểm soát mọi bộ đệm/tốc độ ở các tầng khác, không tự sửa I/O blocking và không thay thế giới hạn concurrency hoặc giám sát tài nguyên.

**Ghi nhớ:** `buffer` biến nhu cầu **phần tử → danh sách**; `window` biến nhu cầu outer **phần tử → Publisher con** rồi thêm **demand riêng bên trong từng Publisher**. Khi thiết kế backpressure, luôn xác định loại `onNext` ở từng đoạn pipeline trước khi kết luận `request(n)` đại diện cho bao nhiêu dữ liệu gốc.

# Điều khiển request bằng BaseSubscriber

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Backpressure

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu rõ quan hệ `Publisher` → `Subscriber` → `Subscription` và cơ chế backpressure bằng `request(n)`.
- Dùng `BaseSubscriber<T>` để yêu cầu phần tử theo từng đợt hoặc từng phần tử, thay cho mặc định không giới hạn.
- Phân biệt `request`, `cancel`, `onComplete` và `onError`; dự đoán tín hiệu cũng như thứ tự chương trình minh họa.
- Áp dụng các hook vòng đời như `hookOnSubscribe`, `hookOnNext`, `hookOnError`, `hookOnComplete`, `hookOnCancel` và `hookFinally`.
- Giải thích tại sao demand ở subscriber cuối có thể khác request quan sát ở upstream khi có `filter`, `buffer`, `flatMap` hoặc `publishOn`.
- Biết lúc nào tự quản lý subscriber là phù hợp và tại sao Spring WebFlux thường sở hữu subscription của HTTP response.

## 1. Vấn đề backpressure mà BaseSubscriber giải quyết

Khi nguồn phát nhanh hơn bên nhận xử lý, nếu không có điều phối, dữ liệu có thể dồn vào bộ nhớ hoặc hàng đợi. Reactive Streams dùng **backpressure** để bên nhận phát tín hiệu nhu cầu (demand) ngược về upstream: qua `Subscription.request(long n)`, subscriber thông báo mình sẵn sàng nhận thêm tối đa `n` phần tử.

```text
Subscriber                  Publisher
    |                           |
    |--- subscribe() ---------->|
    |<-- onSubscribe(s) --------|
    |                           |
    |--- s.request(2) --------->|
    |<-- onNext(value1) --------|
    |<-- onNext(value2) --------|
    |                           | (hết demand)
    |--- s.request(1) --------->|
    |<-- onNext(value3) --------|
    |<-- onComplete() ----------| (nguồn hữu hạn đã hết)
```

Sơ đồ là một trường hợp minh họa của nguồn có ba phần tử. Trong giao thức thực tế, subscriber nhận `onSubscribe` trước khi nhận `onNext`; nguồn không được gửi số lượng `onNext` nhiều hơn tổng demand được cấp. `onComplete` và `onError` là tín hiệu kết thúc, không cần một `request(1)` khác chỉ để cho phép báo kết thúc.

**Demand là quyền được phát, không phải lời hứa sẽ có đúng từng ấy giá trị.** `request(10)` có thể chỉ nhận ba giá trị rồi `onComplete` vì nguồn đã hết, hoặc không nhận giá trị nào vì nguồn rỗng. Nếu nguồn bị lỗi, tín hiệu `onError` có thể kết thúc chuỗi trước khi nhận đủ.

Các cách `subscribe()` tiện lợi của Reactor như `flux.subscribe(value -> ...)` thường yêu cầu `Long.MAX_VALUE`, nghĩa là **unbounded demand**. Cách này không tự gây lỗi và có thể phù hợp với nhiều tình huống, nhưng không cho ta nhịp “xử lý xong rồi mới xin thêm”. `BaseSubscriber` là công cụ để tự định lượng demand.

## 2. BaseSubscriber là gì?

`reactor.core.publisher.BaseSubscriber<T>` là lớp nền của Reactor cho một subscriber tùy biến. Nó giữ reference tới `Subscription` và cung cấp phương thức điều khiển trực tiếp:

| API | Mục đích |
| --- | --- |
| `request(long n)` | Yêu cầu thêm `n` phần tử; `n` phải dương. |
| `requestUnbounded()` | Yêu cầu `Long.MAX_VALUE`, chuyển sang nhu cầu không giới hạn. |
| `cancel()` | Yêu cầu hủy subscription đang quản lý. |
| `dispose()` | Dùng giao diện `Disposable` để hủy subscription. |
| `isDisposed()` | Kiểm tra trạng thái disposed; không thay thế toàn bộ quản lý vòng đời ứng dụng. |

Một chi tiết rất dễ bỏ qua: **nếu không ghi đè `hookOnSubscribe`, `BaseSubscriber` mặc định yêu cầu không giới hạn**. Để thực sự kiểm soát demand, phải override hook này và cấp số dương ban đầu thích hợp, chẳng hạn `request(1)`.

`BaseSubscriber` được thiết kế để gắn với **một subscription**. Không tái sử dụng cùng instance cho các lần đăng ký khác nhau; hãy tạo một đối tượng subscriber mới cho mỗi lần `subscribe`.

### 2.1. Các hook vòng đời

| Hook | Khi được kích hoạt | Ví dụ công việc |
| --- | --- | --- |
| `hookOnSubscribe(Subscription subscription)` | Nguồn chấp nhận subscription | Khởi tạo state và phát `request(1)` hay `request(n)` đầu tiên. |
| `hookOnNext(T value)` | Có phần tử nguồn được gửi xuống | Xử lý phần tử; khi sẵn sàng có thể xin phần tử tiếp. |
| `hookOnComplete()` | Publisher hoàn tất thành công | Ghi nhận hoàn tất, đóng tài nguyên liên quan. |
| `hookOnError(Throwable error)` | Publisher kết thúc bằng lỗi | Ghi nhận và xử lý lỗi; không có `onComplete` sau đó. |
| `hookOnCancel()` | `BaseSubscriber.cancel()` được gọi | Xử lý nhánh hủy do subscriber chủ động phát động. |
| `hookFinally(SignalType signal)` | Sau completion, error hoặc cancel | Dọn tài nguyên ở một nơi dùng chung; biết kết thúc kiểu `ON_COMPLETE`, `ON_ERROR` hay `CANCEL`. |

`hookFinally` được gọi thêm, sau hook terminal tương ứng. Với ứng dụng thực tế, nên override `hookOnError` vì hành vi mặc định báo lỗi chưa xử lý không thay bạn thực hiện chính sách lỗi nghiệp vụ.

**Vòng đời subscription khác vòng đời đối tượng Java mang cấu hình nguồn.** Một `Flux.range(1, 5)` có thể được dùng làm nguồn cho A và B, nhưng A và B phải có subscription và demand riêng. Hủy A không mặc nhiên hủy B nếu B đang dùng một cold subscription độc lập.

### 2.2. Quy tắc request(n) cần nhớ

- `request(1)` cấp quyền phát tối đa **một `onNext` mới** tương ứng với phần demand đó; sau khi nhận xong, demand được tiêu thụ.
- `request(3)` và sau đó `request(2)` có thể cộng dồn thành tổng demand 5 nếu chưa nhận phần tử nào. Demand bão hòa tại `Long.MAX_VALUE` thay vì tràn âm.
- `requestUnbounded()` tương đương yêu cầu không giới hạn. Nó không cấp phát một mảng có `Long.MAX_VALUE` phần tử, nhưng bỏ giới hạn số tín hiệu mà subscriber chấp nhận.
- `request(0)` và `request(-1)` **không phải nút pause**: yêu cầu không dương vi phạm Reactive Streams và phải được báo lỗi theo hợp đồng. Muốn tạm dừng, không gửi request mới sau khi demand còn lại đã hết.
- `cancel()` là hủy quan hệ đăng ký, **không phát `onComplete` chỉ vì bị hủy**. Cancellation bất đồng bộ có thể có độ trễ và không hoàn tác các tác dụng phụ đã hoàn thành.
- Khi subscription đã kết thúc do complete/error/cancel, không thể “khởi động lại” nó bằng cách gọi `request(n)`; muốn tiêu thụ lại cold publisher, tạo một subscriber mới.

## 3. Dòng thời gian cụ thể: A và B yêu cầu khác nhau

Với cold publisher `Flux.range(1, 5)`, ta có thể chủ động điều khiển hai subscriber:

```text
Flux.range(1, 5)
  │
  ├── subscribe(A)
  │       ├── hookOnSubscribe -> request(1)
  │       ├── onNext(1)     [còn 0 demand]
  │       ├── main gọi A.request(2)
  │       ├── onNext(2), onNext(3) [còn 0 demand]
  │       └── main gọi A.cancel() -> hookOnCancel
  │
  └── subscribe(B)  (BaseSubscriber mới)
          ├── hookOnSubscribe -> request(1)
          ├── onNext(1)
          ├── main gọi B.request(4)
          └── onNext(2), onNext(3), onNext(4), onNext(5)
              -> hookOnComplete
```

Ở đây, A và B có **tiến độ riêng**: A dừng ở 3, còn B bắt đầu từ 1 và đọc hết 5. Không có một con trỏ phát chung làm B bắt đầu từ 4. Điều đó đúng với nguồn `Flux.range` cold, không được suy rộng máy móc sang một nguồn hot phát sự kiện liên tục.

Nếu A chỉ xin `request(1)` thì việc chưa thấy `onComplete` không đồng nghĩa hệ thống treo. Nguồn còn phần tử nhưng chưa được cấp demand tiếp. Khi A `cancel()`, việc không xuất hiện `hookOnComplete` là hành vi đúng.

## 4. Chương trình Java 17+ chạy được: điều khiển request và cancel

Ví dụ dùng **Java 17+**, **Maven** và **Project Reactor Core 3.8.8**. Tạo hai tệp sau; Maven cần tải dependency khi chạy lần đầu.

```text
base-subscriber-demo/
├── pom.xml
└── src/main/java/demo/
    └── BaseSubscriberDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>base-subscriber-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/BaseSubscriberDemo.java

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class BaseSubscriberDemo {
    static final class ManualSubscriber extends BaseSubscriber<Integer> {
        private final String label;

        ManualSubscriber(String label) {
            this.label = label;
        }

        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            System.out.println(label + ": subscribed");
            // Ghi đè mặc định unbounded: chỉ xin 1 giá trị trước.
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(label + ": next " + value);
            // Chưa request tiếp: bên ngoài quyết định khi nào nhận thêm.
        }

        @Override
        protected void hookOnComplete() {
            System.out.println(label + ": complete");
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.out.println(label + ": error " +
                    error.getClass().getSimpleName());
        }

        @Override
        protected void hookOnCancel() {
            System.out.println(label + ": cancelled");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5);

        ManualSubscriber a = new ManualSubscriber("A");
        source.subscribe(a);
        System.out.println("main: request A +2");
        a.request(2);
        System.out.println("main: cancel A");
        a.cancel();

        ManualSubscriber b = new ManualSubscriber("B");
        source.subscribe(b);
        System.out.println("main: request B +4");
        b.request(4);
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BaseSubscriberDemo
```

**Stdout của chương trình** (không tính thông báo riêng của Maven):

```text
A: subscribed
A: next 1
main: request A +2
A: next 2
A: next 3
main: cancel A
A: cancelled
B: subscribed
B: next 1
main: request B +4
B: next 2
B: next 3
B: next 4
B: next 5
B: complete
```

**Diễn giải theo từng thời điểm:**

1. `source.subscribe(a)` gọi `hookOnSubscribe` của A. A in dòng `subscribed` rồi gọi `request(1)`. Vì nguồn `Flux.range` đồng bộ, A nhận `next 1` **trước khi** `subscribe(a)` trả về.
2. `a.request(2)` cấp thêm đúng hai phần tử; nguồn phát 2 và 3. A vẫn chưa nhận 4 và 5 vì không còn demand.
3. `a.cancel()` yêu cầu hủy và gọi `hookOnCancel`. Sau đó không có dòng `A: complete`; cancel không đồng nghĩa complete.
4. B là một `ManualSubscriber` **mới**, tự xin một phần tử, nên nhận 1. Sau `b.request(4)`, B nhận 2, 3, 4, 5 và `hookOnComplete`.

Ví dụ có đầu ra xác định vì `range` là nguồn đồng bộ, không dùng scheduler, timer hoặc network. Với publisher bất đồng bộ, thứ tự giữa log từ thread điều khiển và log từ publisher có thể thay đổi; đừng áp máy móc stdout này cho mọi nguồn.

## 5. Xin từng phần tử sau khi xử lý: mẫu one-by-one

Ta có thể gửi `request(1)` ban đầu trong `hookOnSubscribe`, rồi chỉ xin phần tử kế tiếp từ `hookOnNext` sau khi phần tử vừa nhận đã được xử lý xong.

Thêm tệp `src/main/java/demo/OneByOneDemo.java` vào cùng dự án:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class OneByOneDemo {
    public static void main(String[] args) {
        Flux.range(10, 6).subscribe(new BaseSubscriber<Integer>() {
            private int received;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("handled " + value);
                received++;
                if (received == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }

            @Override
            protected void hookOnCancel() {
                System.out.println("stopped after " + received);
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("error: " + error.getMessage());
            }
        });
    }
}
```

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OneByOneDemo
```

Stdout:

```text
handled 10
handled 11
handled 12
stopped after 3
```

`Flux.range(10, 6)` có các phần tử `10, 11, 12, 13, 14, 15`. Subscriber chỉ cho phép nhận ba phần tử đầu rồi hủy. Nó **không** tự động complete vì nguồn vẫn còn dữ liệu tại thời điểm cancel.

Ở đây, “xử lý xong” nghĩa là thao tác đồng bộ ngắn đã hoàn thành trước khi `request(1)` được gọi. Nếu `hookOnNext` chỉ khởi động một tác vụ async và lập tức xin thêm, thì có thể còn nhiều tác vụ đang chạy dù bạn nghĩ đã xử lý từng phần tử. Trường hợp đó cần quản lý completion và error của tác vụ hoặc dùng pipeline có concurrency xác định, ví dụ `concatMap` hay `flatMap` có giới hạn; tránh tạo các nhánh `subscribe()` lồng nhau không được quản lý.

## 6. Cách cấp demand tùy mục tiêu

| Cách request | Mục đích | Lưu ý |
| --- | --- | --- |
| `request(1)`, sau xử lý lại `request(1)` | Điều khiển từng giá trị | Phù hợp khi xử lý đồng bộ có thể quyết định ngay. |
| `request(10)` mỗi đợt | Giảm số lần điều khiển demand | Cần biết khi nào đã tiêu thụ đủ đợt để cấp tiếp. |
| `request(1)` rồi chờ tín hiệu người dùng | Pause/resume một consumer | Không cấp thêm demand khi muốn tạm dừng; không gọi `request(0)`. |
| `requestUnbounded()` | Chấp nhận tất cả phần tử nguồn có thể phát | Làm mất giới hạn demand ở subscriber. |
| `cancel()` | Ngừng quan hệ đăng ký | Không tự hoàn tác I/O hoặc transaction đã hoàn thành. |

Không có `n` tối ưu cho mọi hệ thống. Một phần tử một lượt có thể dễ kiểm soát nhưng tăng overhead trong pipeline phức tạp; batch lớn hơn có thể tốt cho throughput nhưng cần bộ nhớ và năng lực xử lý đủ để hấp thụ dữ liệu.

### 6.1. Cẩn thận với state và thread

`BaseSubscriber` là một đối tượng Java, các hook có thể chạy trên thread đang phát tín hiệu; với `Flux.range`, điều đó thường là thread gọi `subscribe` hoặc `request`. Với nguồn bất đồng bộ, hook có thể chạy trên scheduler/thread khác. Reactor yêu cầu signal tới một subscriber được serial hóa, nhưng biến state ứng dụng dùng chung với UI hoặc nhiều thread điều khiển **không tự thread-safe**. Khi cập nhật counter, trạng thái dừng hoặc queue từ nhiều thread, phải dùng cơ chế đồng bộ hóa hoặc mô hình single-owner phù hợp.

## 7. Demand ở subscriber không nhất thiết giống request ở nguồn

Các operator có thể đổi đơn vị hoặc kích thước request. Vì vậy, `request(1)` ở subscriber cuối **không chứng minh** upstream chỉ phát/giữ đúng một đối tượng ở mọi tầng.

### 7.1. Lọc phần tử

Với `Flux.range(1, 10).filter(n -> n % 2 == 0)`, subscriber yêu cầu hai số chẵn. Để có hai phần tử được giữ, upstream có thể phải cung cấp 1, 2, 3, 4. Operator xử lý các phần tử bị loại trong khi duy trì demand downstream. Đọc log upstream có thể thấy số lượng request lớn hơn số phần tử output.

### 7.2. Đổi đơn vị bằng buffer

`buffer(5)` biến năm giá trị nguồn thành **một danh sách** ở downstream. Một `request(1)` tới luồng `Flux<List<T>>` có thể cần năm giá trị input. Tương tự, `flatMap` có thể tạo nhiều inner publisher với demand và prefetch riêng.

### 7.3. Prefetch và scheduler

`publishOn` thường có hàng đợi và cơ chế prefetch nhằm giảm số lần điều phối request. Bạn có thể thấy log upstream của một batch trước khi subscriber cuối gọi thêm request tương ứng. Điều này không tự động chứng minh publisher vi phạm backpressure; cần biết bạn đang quan sát demand **ở đoạn nào**.

### 7.4. Đặt doOnRequest đúng vị trí

```java
Flux<Integer> source = Flux.range(1, 5)
        .doOnRequest(n ->
                System.out.println("observed upstream request: " + n));
```

Đây là **đoạn minh họa**. Khi nguồn này được subscribe bằng `BaseSubscriber` không có operator thay đổi demand ở giữa, lời gọi `request(1)`/`request(2)` có thể được ghi nhận tương ứng. Di chuyển `doOnRequest` sang phía khác của `publishOn`, `buffer` hoặc `limitRate` sẽ làm bạn quan sát một đoạn demand khác. `doOnRequest` chỉ quan sát request, nó không phải toán tử tự bổ sung demand.

### 7.5. limitRate khác request thủ công

```java
Flux<Integer> shaped = Flux.range(1, 100)
        .limitRate(16);
```

Đây là **đoạn minh họa**. `limitRate(16)` giúp chia demand lớn từ downstream thành các đợt request với kích thước được điều phối; không có nghĩa “chỉ nhận 16 phần tử tổng cộng”. Nếu muốn giới hạn **số phần tử output**, dùng `take(16)`. Nếu muốn giới hạn **số tác vụ inner chạy đồng thời**, xem tham số concurrency của `flatMap` và đặc tính dịch vụ. Các toán tử `onBackpressureBuffer`/`onBackpressureDrop`/`onBackpressureLatest` là chính sách xử lý nguồn nhanh; không tương đương `BaseSubscriber.request(1)`.

## 8. Với nguồn hot, request(1) có dừng thế giới bên ngoài không?

Không nhất thiết. Với `Flux.range` cold, tiến độ dãy số được tính theo từng subscription. Với hot publisher, cảm biến, message broker hoặc stream sự kiện có thể tiếp tục có dữ liệu dù một subscriber đang dừng ở demand 0. Tùy nguồn và operator, dữ liệu có thể được giữ trong buffer, bỏ qua, phát lỗi overflow hoặc được xử lý theo chính sách khác.

`Flux.interval` là nguồn tạo tick theo thời gian. Nếu đã đến tick mà không còn demand, Reactor có thể báo lỗi overflow thay vì lưu mọi tick chờ `request` sau. Không dùng `request(1)` như một lời cam kết rằng một hot source vô hạn sẽ có thể replay chính xác mọi sự kiện về sau.

Với nguồn hot có nhiều subscriber, A chậm và B nhanh còn phụ thuộc cơ chế multicast, buffer và replay. Mỗi subscriber có quan hệ `Subscription` riêng, nhưng upstream chung có thể áp chính sách ảnh hưởng tới cả hệ thống. Nên chọn rõ nguồn, dung lượng buffer, overflow handling và yêu cầu mất dữ liệu trước khi triển khai.

## 9. Cancellation và quản lý tài nguyên

`cancel()` thể hiện rằng subscriber không cần thêm phần tử. Nó không đồng nghĩa `onComplete`; đối với `BaseSubscriber`, `hookOnCancel` giúp quan sát nhánh hủy chủ động. `hookFinally(SignalType type)` có thể làm cleanup chung cho complete/error/cancel.

```java
@Override
protected void hookFinally(SignalType type) {
    System.out.println("subscriber terminated with: " + type);
    // Đóng tài nguyên mà subscriber thực sự sở hữu nếu cần.
}
```

Đây là **đoạn minh họa đặt trong một lớp con `BaseSubscriber`**, cần import `reactor.core.publisher.SignalType`. Nếu callback này chạy, `type` là `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Cần lưu ý hủy của một downstream không bảo đảm dừng ngay I/O đang thực hiện hoặc đảo ngược side effect đã commit; cancellation có thể đến trễ trong pipeline bất đồng bộ.

Dùng `using`/`usingWhen` hoặc `doFinally` khi **publisher** mới là nơi sở hữu tài nguyên. Không chỉ phụ thuộc vào hook của subscriber để dọn các resource mà pipeline mở bên trong, vì resource scope và vòng đời của subscriber không nhất thiết trùng một-một.

## 10. Dùng BaseSubscriber ở đâu trong ứng dụng?

### 10.1. Consumer do ứng dụng sở hữu

`BaseSubscriber` hữu ích khi bạn xây dựng consumer riêng của một publisher (CLI, công cụ quan sát, thành phần desktop, bộ xử lý dữ liệu có giao thức “Next” hoặc một background consumer được quản lý). Thành phần sở hữu consumer cần:

- Tạo subscriber mới cho mỗi lần `subscribe`.
- Cấp demand ban đầu có chủ đích; xin thêm sau khi có năng lực tiếp nhận.
- Xử lý `onError`, `onComplete`, `cancel` và đóng tài nguyên khi shutdown.
- Theo dõi throughput, latency, buffer và downstream processing, không chỉ số request.
- Nếu consumer phải phục hồi sau crash, có phương án checkpoint/acknowledgment riêng: `BaseSubscriber` tự nó không cung cấp xử lý bền vững.

Ví dụ minh họa với các lớp ở mục 4:

```java
ManualSubscriber console = new ManualSubscriber("console");
source.subscribe(console);
// Khi người dùng bấm Next:
console.request(1);
// Khi công cụ đóng:
console.dispose();
```

Đây là **đoạn minh họa**, không phải ứng dụng console hoàn chỉnh có UI. Dữ liệu chỉ tiếp tục nếu nguồn còn sống và demand được cấp thêm; sau `dispose` cần tạo subscriber mới cho lượt mới.

### 10.2. Spring WebFlux HTTP đã có subscriber từ hạ tầng

Trong WebFlux controller, thường **trả publisher** cho hạ tầng HTTP tiêu thụ:

```java
@GetMapping("/items")
public Flux<ItemDto> items() {
    return itemService.findAll()
            .filter(ItemDto::isVisible)
            .limitRate(32);
}
```

Đây là **đoạn minh họa trong controller**, cần định nghĩa `ItemDto`, `itemService` và import `GetMapping`. WebFlux cùng reactive HTTP server sở hữu pipeline response, bao gồm subscribe/consume, backpressure, ghi body, error và cancellation. Khi muốn định hình request upstream, cân nhắc `limitRate`, phân trang, giới hạn prefetch/concurrency và khả năng thực tế của nguồn; không cần nhét `BaseSubscriber` vào controller chỉ để “chạy” response.

Anti-pattern:

```java
@GetMapping("/wrong")
public Flux<ItemDto> wrong() {
    itemService.findAll().subscribe(value -> saveSomewhere(value));
    return Flux.empty();
}
```

Đây là **đoạn minh họa cách sai**. Nhánh tự `subscribe` không gắn vào body đã trả: response có thể kết thúc trước khi công việc lưu hoàn tất, lỗi của việc lưu không tự trở thành HTTP error, cancellation của client không nhất thiết dừng nhánh độc lập. Muốn hai công việc thuộc cùng HTTP lifecycle, compose các publisher bằng `flatMap`/`then` rồi trả chuỗi cuối cùng. Muốn chạy background có chủ ý thì dùng một consumer do ứng dụng quản lý đầy đủ, với lifecycle và chính sách lỗi riêng.

### 10.3. BaseSubscriber không phải rate limiter hay queue

`request(n)` quản lý nhu cầu cho **một subscription**. Nó không giới hạn số HTTP request đồng thời của toàn server, không cấp phép gọi API liên request, không tự retry message đã lỗi, không xác nhận xử lý durable và không đảm bảo fairness tuyệt đối giữa các subscriber khác nhau. Các yêu cầu đó thuộc về throttling, rate limiting, queue, scheduler, dịch vụ hoặc giao thức nguồn.

## 11. Kiểm thử backpressure bằng StepVerifier

`reactor-test` cung cấp `StepVerifier` để xác minh demand theo kịch bản và terminal signal. Bạn không nhất thiết viết một `BaseSubscriber` mới trong mỗi test.

Thêm dependency sau vào `pom.xml` nếu cần dùng `StepVerifier` trong test:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

Ví dụ **đoạn mã trong một phương thức test** (cần import `reactor.test.StepVerifier` và `reactor.core.publisher.Flux`):

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .thenCancel()
        .verify();
```

`StepVerifier.create(..., 0)` khởi động với demand 0. `thenRequest(1)` mở đường cho giá trị 1, `thenRequest(2)` cho 2 và 3. Test sau đó chủ động `thenCancel`, nên không mong `onComplete`. Để kiểm thử completion, yêu cầu đủ dữ liệu rồi `expectNext(...)`/`verifyComplete()`. Nếu cần kiểm thử lỗi, dùng `expectError...` và `verify()`.

## 12. Lỗi thường gặp và cách xử lý

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Không override `hookOnSubscribe` | `BaseSubscriber` yêu cầu không giới hạn | Override, khởi tạo state cần thiết và gọi `request(n > 0)`. |
| Chỉ gọi `request(1)` một lần | Chuỗi có thể dừng ở phần tử đầu do demand bằng 0 | Xin tiếp khi sẵn sàng, hoặc chủ động cancel. |
| Dùng `request(0)` để pause | Vi phạm giao thức, có thể gây lỗi | Không gửi demand mới khi muốn dừng tạm; `cancel` khi dừng hẳn. |
| Tái sử dụng một instance BaseSubscriber | Vòng đời subscription sai, có thể hủy không như mong đợi | Tạo một subscriber mới cho mỗi lần subscribe. |
| Cho rằng `request(5)` đảm bảo đủ năm phần tử | Nguồn có thể empty, complete hoặc error sớm | Hiểu request là khả năng nhận tối đa, không phải số phần tử bắt buộc. |
| Gọi `requestUnbounded()` sau khi đã kiểm soát từng phần tử | Bỏ cơ chế giới hạn demand mong muốn | Chỉ dùng unbounded khi consumer chủ đích chấp nhận. |
| Nghĩ subscriber `request(1)` thì mọi operator chỉ giữ một đối tượng | Prefetch/buffer/flatMap có thể thay đổi demand upstream | Quan sát đúng chỗ và cấu hình buffer/concurrency riêng. |
| Gọi `cancel()` rồi chờ `onComplete` | Cancel không phải complete | Dùng hook cancel/finally để ghi nhận và cleanup. |
| Khởi động async task trong `hookOnNext` rồi xin ngay phần tử khác | Có nhiều tác vụ chưa hoàn tất ngoài ý muốn | Phối hợp completion hoặc compose bằng `concatMap`/`flatMap` giới hạn. |
| `block()` hoặc blocking I/O trong hook chạy trên event-loop | Chặn thread và hại throughput | Dùng API reactive, chuyển công việc blocking theo cấu hình thích hợp. |
| Tạo `BaseSubscriber` ngay trong WebFlux controller | Công việc tách khỏi HTTP lifecycle, lỗi và hủy khó kiểm soát | Trả publisher, để WebFlux subscribe; dùng operator nếu cần. |
| Cho rằng nguồn hot tự giữ vô hạn dữ liệu khi demand = 0 | Có thể drop, buffer hoặc báo overflow | Xác định rõ backpressure strategy và chính sách replay. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Flux.range(1, 5)` được subscribe bởi một `BaseSubscriber` chỉ gọi `request(2)` trong `hookOnSubscribe`. Không có request thêm. Kết quả?  
**Đáp án:** Nhận 1 và 2, sau đó chờ. Nguồn còn 3, 4, 5 nhưng chưa được cấp demand.

**Câu 2.** Nếu sau đó gọi `request(1)` rồi `request(2)`, nguồn cold này sẽ làm gì?  
**Đáp án:** Phát 3, sau đó 4 và 5 rồi hoàn tất, giả sử không bị hủy và không lỗi.

**Câu 3.** Vì sao tạo `BaseSubscriber` nhưng không override `hookOnSubscribe` chưa phải backpressure tùy biến?  
**Đáp án:** Vì hook mặc định yêu cầu `Long.MAX_VALUE`. Muốn cấp nhu cầu hữu hạn, phải override để gọi `request(n)` thích hợp.

**Câu 4.** `cancel()` có kích hoạt `onComplete` không?  
**Đáp án:** Không. Nó kích hoạt đường hủy; `hookOnCancel` và `hookFinally(SignalType.CANCEL)` phù hợp để quan sát kết thúc do cancel.

**Câu 5.** Hai subscriber A và B đăng ký độc lập vào `Flux.range(1, 5)`. A đã nhận 1, 2, 3; B sẽ bắt đầu từ giá trị nào?  
**Đáp án:** B bắt đầu từ 1 vì `range` là cold publisher với tiến độ riêng theo subscription.

**Câu 6.** Vì sao khi subscriber xin `request(1)` lại có thể thấy upstream log yêu cầu 32 hoặc 256?  
**Đáp án:** Một operator giữa hai vị trí có thể yêu cầu trước theo lô, hoặc đổi đơn vị demand (ví dụ buffer/prefetch). Cần xác định vị trí `doOnRequest` trước khi kết luận pipeline sai.

**Câu 7.** Có nên gọi `subscribe(new BaseSubscriber...)` bên trong mỗi WebFlux controller để điều khiển HTTP response?  
**Đáp án:** Thông thường không. Controller nên trả `Mono`/`Flux`; hạ tầng WebFlux quản lý subscription, lỗi, body và cancellation. Điều chỉnh pipeline bằng operator và chính sách nguồn khi cần.

## Ghi nhớ

**`BaseSubscriber` giúp một consumer chủ động cấp thêm demand qua `request(n)`**. Muốn thật sự điều khiển nhịp, phải override `hookOnSubscribe` vì mặc định subscriber yêu cầu không giới hạn. Khi demand hết, nguồn tôn trọng backpressure dừng phát thêm `onNext` tới subscriber đó; khi muốn tiếp tục, gọi request dương. `cancel()` dừng subscription chứ không tạo `onComplete`. Demand còn có thể bị thay đổi bởi operator và chính sách nguồn hot. Với HTTP WebFlux, thường để framework sở hữu subscriber và trả lại publisher đã compose từ controller.

### Tài liệu tham khảo

1. [Project Reactor – BaseSubscriber API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html) – lifecycle hooks, `request`, `cancel`, `requestUnbounded`.
2. [Project Reactor – Creating and Subscribing to a Flux or Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) – `BaseSubscriber` và custom request.
3. [Project Reactor – Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand, `limitRate`, prefetch.
4. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – hợp đồng `Publisher`, `Subscriber` và `Subscription`.
5. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – HTTP pipeline và reactive response.

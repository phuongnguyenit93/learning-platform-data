# Vai trò của Publisher, Subscriber, Subscription và Processor

## 1. Bối cảnh: Reactive Streams giải quyết vấn đề gì?

**Reactive Streams** là một đặc tả về cách các thành phần trao đổi chuỗi dữ liệu **bất đồng bộ** theo cơ chế **backpressure** (bên nhận kiểm soát số phần tử được phép gửi). Đây là *hợp đồng giao tiếp* giữa các thành phần, không phải một thư viện xử lý luồng hay cơ chế tự động tạo luồng chạy song song.

Trong hệ sinh thái Java/Spring WebFlux, các giao diện cốt lõi nằm trong gói `org.reactivestreams`: `Publisher<T>`, `Subscriber<T>`, `Subscription` và `Processor<T, R>`. Project Reactor hiện thực mô hình này qua `Flux` (0..N phần tử) và `Mono` (0..1 phần tử). Java cũng có các giao diện tương tự trong `java.util.concurrent.Flow`; tên giống nhau nhưng **khác kiểu Java/package**, không được hoán đổi trực tiếp nếu không có bộ chuyển đổi thích hợp.

Mục tiêu của hợp đồng: một nguồn có khả năng phát nhanh không được áp đảo bên nhận chậm bằng cách gửi `onNext` nhiều hơn lượng bên nhận đã yêu cầu. Backpressure là điều phối **nhu cầu nhận dữ liệu**, không có nghĩa mọi thao tác trong toàn hệ thống đều không chặn hoặc tự động tiết kiệm bộ nhớ.

## 2. Trách nhiệm của bốn giao diện

| Thành phần | Vai trò | Phương thức cốt lõi | Điều cần nhớ |
|---|---|---|---|
| `Publisher<T>` | **Nguồn/đầu phát** tạo luồng phần tử kiểu `T`; chấp nhận người đăng ký. | `subscribe(Subscriber<? super T> s)` | Cam kết phát tín hiệu đúng hợp đồng; từng lượt đăng ký có vòng đời và yêu cầu riêng. |
| `Subscriber<T>` | **Bên nhận** xử lý phần tử, lỗi và tín hiệu kết thúc. | `onSubscribe`, `onNext`, `onError`, `onComplete` | Nhận `Subscription` trước, rồi quyết định khi nào yêu cầu dữ liệu. |
| `Subscription` | **Kênh điều khiển** gắn với một quan hệ Publisher–Subscriber. | `request(long n)`, `cancel()` | Đại diện cho quyền yêu cầu thêm `n` phần tử hoặc hủy; không phải bản thân dữ liệu. |
| `Processor<T,R>` | **Trung gian hai chiều**: nhận `T` từ upstream và phát `R` cho downstream. | Kế thừa `Subscriber<T>` và `Publisher<R>` | Vừa tuân thủ hợp đồng nhận, vừa tuân thủ hợp đồng phát; có thể đổi kiểu, lọc hoặc phối hợp luồng. |

Chữ ký rút gọn để thấy mối quan hệ kiểu (đây là **minh họa API**, không phải một file độc lập để biên dịch):

```java
interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable error);
    void onComplete();
}

interface Subscription {
    void request(long n);
    void cancel();
}

interface Processor<T, R> extends Subscriber<T>, Publisher<R> {}
```

**Phân biệt trách nhiệm:** `Publisher` quyết định *dữ liệu nào được phát* và tuân thủ số lượng được yêu cầu; `Subscriber` quyết định *nhận và xử lý thế nào*; `Subscription` quyết định *khi nào/còn bao nhiêu phần tử được phép chuyển*; `Processor` đóng vai trò trung gian nên phải quản lý cả hai phía.

## 3. Vòng đời đăng ký và các tín hiệu

Một luồng hợp lệ có dạng tín hiệu:

```text
onSubscribe(subscription)
    ├─ onNext(item)  [0 hoặc nhiều lần, trong giới hạn demand]
    ├─ onNext(item)
    └─ onComplete()  HOẶC  onError(throwable)
```

Trình tự ví dụ khi nguồn có ba phần tử:

```text
Subscriber ── subscribe(subscriber) ──> Publisher
Subscriber <── onSubscribe(s) ──────── Publisher
Subscriber ── s.request(2) ──────────> Subscription
Subscriber <── onNext(1) ──────────── Publisher
Subscriber <── onNext(2) ──────────── Publisher
Subscriber ── s.request(1) ──────────> Subscription
Subscriber <── onNext(3) ──────────── Publisher
Subscriber <── onComplete() ───────── Publisher
```

Các mũi tên mô tả **quan hệ logic**; không khẳng định mỗi tín hiệu chạy trên một thread riêng hay xảy ra không đồng bộ. Chẳng hạn `Flux.range(...)` của Reactor có thể phát đồng bộ ngay trong lời gọi `request`.

Những bất biến quan trọng:

1. `onSubscribe` cung cấp đúng một `Subscription` cho mỗi lượt đăng ký và phải đến trước `onNext`, `onError`, `onComplete`.
2. `onNext` truyền từng phần tử **không null**; số lượng `onNext` chưa có tín hiệu kết thúc không được vượt tổng demand còn hiệu lực.
3. `onComplete` báo nguồn kết thúc bình thường; `onError` báo thất bại. **Chỉ một loại terminal signal** được gửi cho một lượt đăng ký, và không còn `onNext` sau đó.
4. Các tín hiệu đến **cùng một Subscriber** phải được tuần tự hóa theo hợp đồng; không tùy tiện gọi `onNext` đồng thời từ nhiều thread.
5. `onComplete`/`onError` là tín hiệu kết thúc, **không tiêu thụ demand** như `onNext`; `onError` có thể đến ngay cả khi chưa yêu cầu phần tử.
6. Sau `cancel()`, nguồn phải dừng gửi sớm nhất có thể; do bất đồng bộ, một số tín hiệu đang trên đường truyền vẫn có thể xuất hiện. Hủy **không đồng nghĩa** với phát `onComplete`.

Một `Publisher` có thể là nguồn **cold** (mỗi subscriber kích hoạt luồng riêng) hoặc **hot** (chia sẻ một nguồn đang hoạt động); interface `Publisher` tự nó không bảo đảm cold/hot, tính toán lười, thread nào chạy, hay khả năng phát lại dữ liệu.

## 4. Subscription và cơ chế backpressure

- Trong `onSubscribe(s)`, Subscriber thường lưu `s` rồi gọi `s.request(n)` với **`n > 0`**. `request(0)` và `request(n < 0)` là yêu cầu không hợp lệ, theo đặc tả sẽ dẫn tới tín hiệu `onError`.
- Demand có tính **cộng dồn**: `request(2)` rồi `request(3)` cấp tổng cộng năm quyền nhận `onNext` (trừ phần đã nhận); một `onNext` làm giảm demand còn lại một đơn vị.
- `request(Long.MAX_VALUE)` thường được dùng như yêu cầu **không giới hạn**. Đặc tả yêu cầu xử lý cộng demand an toàn khi tràn số, tương đương bão hòa ở mức không giới hạn.
- `cancel()` dùng khi không còn quan tâm kết quả, ví dụ người dùng ngắt kết nối hoặc nghiệp vụ dừng xử lý. Gọi hủy nhiều lần phải an toàn.
- Backpressure kiểm soát **phần tử bàn giao cho Subscriber**. Một chuỗi có `filter`, `buffer`, `flatMap`, prefetch hoặc nguồn hot có thể quản lý, gom hoặc yêu cầu lượng phần tử upstream khác với demand downstream. Vì thế không suy luận `request(1)` luôn bằng đúng một lần đọc I/O hay đúng một phần tử sinh ra ở mọi tầng.

Ví dụ nguồn có 100 phần tử và Subscriber chỉ `request(2)`: nếu chưa có yêu cầu bổ sung, nguồn tuân thủ đặc tả không được gửi phần tử thứ ba qua `onNext` cho Subscriber đó. Dữ liệu upstream có thể được giữ lại, đệm có giới hạn, hoặc xử lý theo chiến lược riêng của operator/nguồn; không được hiểu là tự động có bộ đệm vô hạn.

## 5. Ví dụ Java 17+ chạy được với Project Reactor

Ví dụ sau dùng **chính các interface `org.reactivestreams`**. `Flux` là Publisher thực tế; một `Subscriber` tự quản lý `Subscription`, nhận một phần tử rồi mới yêu cầu phần tiếp theo. Không cần khởi động Spring Boot.

Tạo cấu trúc:

```text
reactive-roles/
├── pom.xml
└── src/main/java/demo/Main.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-roles</artifactId>
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

Nội dung `src/main/java/demo/Main.java`:

```java
package demo;

import org.reactivestreams.Publisher;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import reactor.core.publisher.Flux;

public class Main {
    public static void main(String[] args) {
        Publisher<Integer> publisher =
                Flux.range(1, 3).map(n -> n * 10);

        publisher.subscribe(new Subscriber<Integer>() {
            private Subscription subscription;

            @Override
            public void onSubscribe(Subscription s) {
                this.subscription = s;
                System.out.println("onSubscribe -> request(1)");
                s.request(1);
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("onNext: " + item);
                subscription.request(1);
            }

            @Override
            public void onError(Throwable error) {
                System.out.println("onError: " + error.getMessage());
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
            }
        });
    }
}
```

Từ thư mục chứa `pom.xml`, chạy bằng **JDK 17+** và Maven:

```bash
mvn -q compile exec:java
```

Đầu ra stdout của chương trình:

```text
onSubscribe -> request(1)
onNext: 10
onNext: 20
onNext: 30
onComplete
```

Giải thích theo từng vai trò:

1. `Flux.range(1, 3).map(n -> n * 10)` là một pipeline **Publisher<Integer>** phát lần lượt `10`, `20`, `30` khi có yêu cầu; `map` biến đổi từng phần tử.
2. `publisher.subscribe(...)` kết nối Subscriber với Publisher. Trước khi phát dữ liệu, nguồn gọi `onSubscribe(s)`.
3. Subscriber giữ `s` và gọi `request(1)`: chỉ cho phép chuyển **một** `onNext` lúc đó. Sau mỗi phần tử, `onNext` gọi `request(1)` để tiếp tục.
4. Khi ba phần tử đã phát hết, Publisher gọi `onComplete`; không gọi `onError`. Trong ví dụ nguồn đồng bộ và hữu hạn nên thứ tự stdout ổn định.

**Thử hủy:** trong `onNext`, sau khi in `item`, thay `subscription.request(1)` bằng:

```java
if (item == 20) {
    subscription.cancel();
    System.out.println("cancel");
} else {
    subscription.request(1);
}
```

Với nguồn đồng bộ này, stdout sẽ dừng sau `onNext: 20` và dòng `cancel`, không có `onNext: 30` hoặc `onComplete`. Đây là thay đổi **bên trong phương thức `onNext` của ví dụ**, không phải chương trình độc lập thứ hai. Với nguồn bất đồng bộ, `cancel()` có thể không thu hồi được mọi tín hiệu đã được gửi trước đó.

## 6. Processor: khi nào cần và khi nào không?

`Processor<T, R>` đồng thời là **Subscriber<T>** nhận đầu vào từ upstream và **Publisher<R>** cấp luồng đầu ra cho downstream:

```text
Publisher<Order>
    ──(Subscription upstream / Order)──>
Processor<Order, Receipt>
    ──(Subscription downstream / Receipt)──>
Subscriber<Receipt>
```

Processor phải ứng xử đúng ở **cả hai phía**: nhận `onSubscribe` từ upstream; quyết định `request` upstream; quản lý nhu cầu của downstream; chuyển đổi dữ liệu; chuyển tiếp hoàn thành/lỗi và xử lý hủy một cách phù hợp. Quan hệ demand không nhất thiết 1:1 (ví dụ lọc bỏ một số đầu vào). Tự viết Processor tuân thủ mọi quy tắc về đồng thời, backpressure và hủy là công việc khó.

**Không phải mọi toán tử Reactor đều là một đối tượng `Processor`.** Trong ứng dụng, thông thường biểu diễn phép biến đổi bằng toán tử:

```java
Flux<Integer> result = Flux.range(1, 5)
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10); // logic: 10, 30, 50
```

Đoạn trên tạo một pipeline Publisher, chưa phát tới Subscriber nào nếu chưa subscribe. Các toán tử đảm nhận việc phối hợp demand/biến đổi trong implementation của Reactor; không có lý do phải tự tạo `Processor<Integer,Integer>` chỉ để làm phép lọc hay map.

Khi cần đưa sự kiện chủ động từ bên ngoài vào luồng Reactor, nên tìm hiểu **`Sinks.Many<T>`** và chiến lược phát/buffer phù hợp thay vì mặc định xây một Processor thủ công. `Sinks.Many` là API nguồn sự kiện của Reactor, **không phải** chính giao diện `org.reactivestreams.Processor`. Không mặc định giả định mọi lần `tryEmitNext` đều thành công: cần kiểm tra `EmitResult` và hiểu quy tắc subscriber/demand của sink được chọn.

## 7. Liên hệ thực tế với Spring WebFlux

Trong Spring WebFlux, method controller có thể **trả về `Flux`/`Mono`**. Framework và hạ tầng HTTP tham gia đăng ký, tiêu thụ, điều tiết và hủy theo vòng đời request/response.

Ví dụ **đoạn mã minh họa trong một ứng dụng Spring WebFlux có sẵn** (không phải file chạy độc lập):

```java
@RestController
class NumberController {
    @GetMapping(value = "/numbers",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

Cần import `org.springframework.web.bind.annotation.GetMapping`, `RestController`, `org.springframework.http.MediaType` và `reactor.core.publisher.Flux`. Khi client truy cập `/numbers`, server có thể phát các số dưới dạng Server-Sent Events. Không gọi `.subscribe()` bên trong controller chỉ để “khởi động” chuỗi rồi trả `void`: trả Publisher cho framework giúp giữ kết nối với xử lý lỗi, hủy khi client ngắt và cơ chế điều tiết của runtime. Điều tiết thực tế còn phụ thuộc mạng, codec, buffering và loại nguồn; không thể khẳng định một lần `request(1)` ở tầng HTTP tương ứng chính xác một lần đọc database.

## 8. Lỗi hiểu sai thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Publisher luôn đẩy dữ liệu ngay khi tạo ra.” | Việc phát phụ thuộc loại nguồn và nhu cầu; nguồn cold thường chỉ bắt đầu khi được đăng ký. |
| “`subscribe()` đồng nghĩa chạy song song/tạo thread.” | Reactive Streams không quy định thread; scheduler và nguồn/operator mới quyết định execution context. |
| “Subscriber chỉ cần `onNext`.” | Phải nhận `onSubscribe`, nắm vòng đời `Subscription`, xử lý lỗi và hoàn thành. |
| “`request(1)` luôn có một phần tử ngay lập tức.” | Request là **quyền nhận tối đa**; nguồn có thể chậm, chưa có phần tử hoặc kết thúc mà không phát gì. |
| “Có thể gọi `onNext(null)`.” | Phần tử null vi phạm hợp đồng; dùng kiểu biểu diễn sự vắng mặt phù hợp, ví dụ `Mono.empty()`. |
| “`cancel()` sẽ phát `onComplete()`.” | Hủy là chấm dứt quan tâm/tiêu thụ; không phải một terminal signal thông thường. |
| “Mọi phép `map`/`filter` cần một Processor.” | Dùng toán tử `Flux`/`Mono`; chỉ cân nhắc Processor khi thực sự cần vai trò trung gian Publisher + Subscriber. |
| “Backpressure bảo đảm không có buffer hay blocking.” | Nó chỉ định giao thức demand; chiến lược xử lý upstream, bộ đệm và I/O là trách nhiệm implementation. |

## 9. Tự kiểm tra nhanh

**Tình huống:** Publisher có sẵn năm phần tử; Subscriber gọi `request(2)`, nhận hai `onNext`, rồi không gọi `request` nữa. Hỏi: có được gửi phần tử thứ ba qua `onNext` không? Nếu sau đó Subscriber gọi `request(3)` thì sao? Và ai cung cấp phương thức `cancel()`?

**Đáp án:** Chưa được gửi phần tử thứ ba khi demand đã hết. `request(3)` bổ sung quyền nhận tối đa ba `onNext` tiếp theo, nên nguồn có thể gửi hết ba phần tử còn lại rồi `onComplete()`. `cancel()` thuộc `Subscription` mà Publisher đưa cho Subscriber thông qua `onSubscribe`.

**Ghi nhớ:** `Publisher` **phát**, `Subscriber` **nhận**, `Subscription` **điều khiển demand/hủy**, còn `Processor` **nhận rồi phát tiếp** theo cả hai hợp đồng. Nắm rõ ranh giới này giúp đọc đúng các pipeline `Flux`/`Mono` và lý giải backpressure trong Spring WebFlux.

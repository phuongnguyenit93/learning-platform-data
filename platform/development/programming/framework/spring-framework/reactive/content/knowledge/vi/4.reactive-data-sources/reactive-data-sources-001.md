# Tạo dữ liệu có sẵn bằng `just`, `fromIterable` và `range` trong Project Reactor

## 1. Mục tiêu và bối cảnh

Trong Spring Framework Reactive, đặc biệt là Spring WebFlux, `Mono<T>` và `Flux<T>` của Project Reactor biểu diễn các nguồn dữ liệu tuân theo Reactive Streams. Khi đã **có sẵn dữ liệu trong bộ nhớ**, ba factory method thường gặp để biến dữ liệu đó thành Publisher là `just`, `fromIterable` và `range`.

Học xong bài, bạn cần chọn đúng phương thức từ loại dữ liệu đầu vào, dự đoán thứ tự các tín hiệu phát ra, hiểu sự khác biệt giữa thời điểm tạo Publisher và thời điểm đăng ký, xử lý luồng rỗng hoặc giá trị `null`, và tránh nhầm lẫn tham số `count` của `range` với cận trên.

Một chương trình sau đây tạo **nguồn** nhưng chưa yêu cầu nhận dữ liệu:

~~~java
Flux<String> colors = Flux.just("đỏ", "xanh", "vàng");
~~~

Thông thường khi có subscriber đăng ký (ví dụ gọi `subscribe`), nguồn mới bắt đầu gửi `onNext` theo nhu cầu `request(n)`, rồi `onComplete` nếu phát xong; nếu gặp lỗi thì gửi `onError`. Ba nguồn trong bài đều là nguồn **hữu hạn**, thường xử lý **đồng bộ** khi chưa gắn toán tử thay đổi scheduler. Chỉ đổi `List` thành `Flux` không tự làm I/O trở thành bất đồng bộ, không tự mở thread và không làm chương trình nhanh hơn.

## 2. So sánh nhanh ba factory method

| Phương thức | Dữ liệu đầu vào | Kiểu trả về | Số phần tử phát ra | Trường hợp phù hợp |
| --- | --- | --- | --- | --- |
| `Mono.just(value)` | Một đối tượng không-null | `Mono<T>` | Đúng 1 | Một giá trị đã có, như một cấu hình, một ID, một object |
| `Flux.just(a, b, c)` | Các đối tượng được liệt kê | `Flux<T>` | Bằng số đối tượng được đưa vào | Vài giá trị cố định để minh họa hoặc khởi tạo |
| `Flux.fromIterable(iterable)` | `Iterable<? extends T>` như `List`, `Set`, `Collection` | `Flux<T>` | Bằng số phần tử iterator cung cấp | Đã có một tập dữ liệu trong bộ nhớ |
| `Flux.range(start, count)` | Hai số `int` | `Flux<Integer>` | `count` số nguyên liên tiếp, nếu `count > 0` | Sinh số thứ tự, test, chạy một phép biến đổi N lần |

Ví dụ ngắn:

~~~java
Mono<String> single = Mono.just("Spring");                 // Spring
Flux<String> fixed = Flux.just("A", "B", "C");              // A, B, C
Flux<String> fromList = Flux.fromIterable(List.of("X", "Y")); // X, Y
Flux<Integer> numbers = Flux.range(5, 3);                 // 5, 6, 7
~~~

Các chú thích cuối dòng biểu diễn **giá trị sẽ được phát khi có đăng ký và demand**, không phải kết quả trả về lập tức của lệnh tạo Publisher.

## 3. `just`: tạo nguồn từ một hoặc vài giá trị đã biết

### 3.1. `Mono.just(T)` cho đúng một giá trị

`Mono.just("hello")` tạo `Mono<String>` có một `onNext("hello")` rồi `onComplete()`. Khi đã có một object cụ thể, chẳng hạn một bản ghi đọc sẵn từ cache hoặc một hằng cấu hình, đây là lựa chọn đơn giản.

~~~java
Mono<String> greeting = Mono.just("Xin chào");

greeting.subscribe(
    value -> System.out.println("value=" + value),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Stdout:

~~~text
value=Xin chào
complete
~~~

`Mono.just` không nhận `null`. Nếu giá trị có thể vắng mặt, sử dụng `Mono.justOrEmpty(nullableValue)` hoặc `Mono.empty()`; không phát `null` qua `onNext` vì Reactive Streams cấm dữ liệu null. Trường hợp **không có dữ liệu** khác với trường hợp **có một phần tử có nội dung chuỗi rỗng** (`Mono.just("")` vẫn phát một phần tử).

### 3.2. `Flux.just(T...)` cho một danh sách giá trị liệt kê trực tiếp

~~~java
Flux<String> statuses = Flux.just("NEW", "PAID", "SHIPPED");
Flux<Integer> primes = Flux.just(2, 3, 5, 7);
~~~

`Flux.just` phát các phần tử theo thứ tự được truyền vào rồi hoàn tất. Lựa chọn này tốt cho nguồn nhỏ, cố định; với một `List` sẵn có, dùng `fromIterable` rõ nghĩa hơn. Chú ý:

- `Flux.just(list)` có kiểu `Flux<List<T>>`: nó phát **một phần tử là cả danh sách**. `Flux.fromIterable(list)` có kiểu `Flux<T>`: nó phát **từng phần tử** của danh sách. Đừng nhầm hai trường hợp.
- Không truyền `null` làm phần tử; với 0 phần tử, dùng `Flux.empty()`.
- Với giá trị là object mutable, `just` giữ tham chiếu đến object; không tự deep-copy trạng thái của object.
- Hai subscriber độc lập có thể đăng ký cùng một nguồn `Flux.just` và mỗi subscriber nhận lại toàn bộ chuỗi từ đầu, trừ khi đã thêm toán tử chia sẻ/cache làm thay đổi ngữ nghĩa.

### 3.3. "Có sẵn" nghĩa là biểu thức đầu vào được tính ngay

Phân biệt **việc đánh giá biểu thức Java** với **việc Publisher phát tín hiệu**:

~~~java
String title = loadTitleFromMemory();   // hàm chạy ngay trên dòng này
Mono<String> value = Mono.just(title);  // giữ giá trị đã tính
// Chưa có subscriber, nhưng loadTitleFromMemory() đã chạy.
~~~

Tương tự, `Mono.just(loadTitleFromMemory())` **gọi hàm ngay khi xây dựng nguồn**, trước `subscribe`. Nếu cần thực hiện hàm *mỗi lần đăng ký*, dùng `Mono.fromSupplier(() -> loadTitleFromMemory())` hoặc `Mono.defer(() -> Mono.just(loadTitleFromMemory()))`. Đây là các factory method khác để giải quyết bài toán tạo dữ liệu trì hoãn; không nên ép `just` đảm nhận hành vi này.

### 3.4. Có nên dùng `Mono.just` hay `Flux.just` cho một object?

Cả hai đều có thể phát một phần tử, nhưng kiểu trả về truyền đạt hợp đồng:

- Một kết quả hoặc không có kết quả: ưu tiên `Mono<T>` (ví dụ tra cứu bằng ID).
- Tập kết quả 0..N: ưu tiên `Flux<T>` (ví dụ trả nhiều trạng thái hoặc nhiều hàng).
- `Mono<T>` không phải là `Flux<T>`; có thể chuyển `mono.flux()` nếu cần API trả về `Flux`.

## 4. `Flux.fromIterable`: phát lần lượt các phần tử của tập có sẵn

### 4.1. Từ `List` và `Set`

`Flux.fromIterable(Iterable<? extends T>)` lấy các phần tử thông qua cơ chế duyệt `Iterable`, giữ thứ tự mà iterator cung cấp. Với `List`, thứ tự phát thường trùng thứ tự phần tử trong danh sách:

~~~java
List<String> cities = List.of("Hà Nội", "Đà Nẵng", "Cần Thơ");
Flux<String> cityFlux = Flux.fromIterable(cities);

cityFlux.subscribe(System.out::println);
~~~

Stdout:

~~~text
Hà Nội
Đà Nẵng
Cần Thơ
~~~

Với `Set`, thứ tự phụ thuộc implementation: `HashSet` không bảo đảm thứ tự logic, còn `LinkedHashSet` giữ thứ tự chèn. Nếu nghiệp vụ cần thứ tự xác định, hãy chọn `List` hoặc một collection có hợp đồng thứ tự phù hợp.

`List.of()` rỗng cho một `Flux` **không phát `onNext` nào** mà chỉ `onComplete`:

~~~java
Flux.fromIterable(List.<String>of())
    .subscribe(
        value -> System.out.println("onNext=" + value),
        error -> System.out.println("onError=" + error),
        () -> System.out.println("onComplete")
    );
// Chỉ in: onComplete
~~~

### 4.2. Mỗi lần đăng ký duyệt lại Iterable

`fromIterable` nắm giữ đối tượng `Iterable` và lấy dữ liệu để phát khi có đăng ký. Vì vậy với một `List` có thể thay đổi, nội dung được nhìn thấy khi subscribe sau có thể khác subscribe trước:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));
Flux<String> namesFlux = Flux.fromIterable(names);

namesFlux.subscribe(name -> System.out.println("Lần 1: " + name));
names.add("Chi");
namesFlux.subscribe(name -> System.out.println("Lần 2: " + name));
~~~

Stdout:

~~~text
Lần 1: An
Lần 1: Bình
Lần 2: An
Lần 2: Bình
Lần 2: Chi
~~~

Điều này **không** có nghĩa `Flux` quan sát và push sự thay đổi của `List` theo thời gian: sửa danh sách **không tự phát một event** đến subscriber đã hoàn tất. Ví dụ trên có **hai lần đăng ký riêng biệt**. Việc sửa collection **đồng thời trong lúc đang duyệt** có thể gây lỗi hoặc kết quả không xác định theo implementation, nên dùng nguồn dữ liệu ổn định trong thời gian phát.

Nếu muốn snapshot độc lập khỏi các thay đổi ở cấp danh sách, có thể sao chép dữ liệu trước:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(source); // bản sao bất biến ở cấp danh sách
Flux<String> frozen = Flux.fromIterable(snapshot);

source.add("C"); // frozen vẫn chỉ phát A, B
~~~

`List.copyOf` từ chối phần tử null; và với object bên trong mutable, snapshot chỉ sao chép cấu trúc danh sách, không sao chép sâu các object.

### 4.3. Yêu cầu của một Iterable có thể đăng ký lại

Theo Javadoc Reactor, `fromIterable` có thể gọi `Iterable.iterator()` **một hoặc hai lần cho mỗi subscriber**, do cần kiểm tra đặc tính hữu hạn phục vụ việc hủy/bỏ phần tử còn lại. Vì vậy, custom `Iterable` nên trả iterator hợp lệ mỗi lần, không giả định phương thức `iterator()` luôn được gọi đúng một lần hoặc có thể tiêu thụ cùng một iterator duy nhất mãi mãi.

Không nhầm `Iterable` với `Iterator`: một `Iterator` là con trỏ duyệt có trạng thái, còn `Iterable` là khả năng cung cấp iterator. Cần nhiều lần subscribe thì nguồn phải có khả năng được duyệt lại. Nếu đầu vào là mảng, cách trực tiếp là `Flux.fromArray(array)`; nếu là `Stream` chỉ dùng được một lần, cân nhắc `Flux.fromStream(() -> createStream())` để tạo stream mới cho mỗi lần đăng ký. Hai API này chỉ là phương án tương ứng với dạng đầu vào, trọng tâm của bài vẫn là `fromIterable`.

### 4.4. Null, exception và tài nguyên

- `Iterable` và phần tử truyền qua `onNext` không được `null`. Một phần tử `null` từ collection sẽ dẫn đến lỗi, chứ không biểu diễn "bỏ qua phần tử".
- Nếu iterator ném exception khi duyệt, chuỗi sẽ đi vào đường `onError`; cần xác định cách xử lý lỗi ở downstream.
- `fromIterable` dành cho dữ liệu đã có khả năng duyệt. Nếu iterator thực hiện I/O chặn thread (đọc DB, file, HTTP), việc dùng `Flux.fromIterable` **không biến I/O đó thành non-blocking**; cần tích hợp API phản ứng hoặc scheduling đúng.

## 5. `Flux.range(start, count)`: tạo các số nguyên liên tiếp

Chữ ký:

~~~java
static Flux<Integer> range(int start, int count)
~~~

`start` là **giá trị đầu tiên** (bao gồm), còn `count` là **số lượng phần tử cần phát**. Khi `count > 0`, dãy là:

~~~text
start, start + 1, ..., start + count - 1
~~~

Ví dụ:

| Biểu thức | Dữ liệu phát ra | Giải thích |
| --- | --- | --- |
| `Flux.range(5, 3)` | `5, 6, 7` | Bắt đầu 5 và phát 3 số |
| `Flux.range(1, 5)` | `1, 2, 3, 4, 5` | Bắt đầu 1 và phát 5 số |
| `Flux.range(0, 4)` | `0, 1, 2, 3` | Có thể bắt đầu bằng 0 |
| `Flux.range(-2, 3)` | `-2, -1, 0` | Có thể bắt đầu bằng số âm |
| `Flux.range(9, 1)` | `9` | Chỉ một phần tử |
| `Flux.range(9, 0)` | Không có `onNext` | Luồng rỗng, hoàn tất ngay |

**Sai lầm thường gặp:** `Flux.range(5, 10)` tạo **mười** số từ 5 đến 14, không phải các số từ 5 đến 10. Nếu muốn số từ `a` đến `b`, với `a <= b` và phép tính không tràn `int`, dùng `Flux.range(a, b - a + 1)`; kiểm tra biên trước khi tính cho input người dùng.

`count < 0` là tham số không hợp lệ; khoảng vượt quá miền biểu diễn `Integer` cũng không hợp lệ. Đừng cố biểu diễn dãy vượt quá `Integer.MAX_VALUE` bằng `range`; dùng kiểu và cách tạo nguồn khác nếu bài toán yêu cầu số lớn.

`range` không cần tạo trước một `List<Integer>` gồm tất cả phần tử. Khi subscriber yêu cầu dữ liệu, nó có thể tính phần tử kế tiếp, tôn trọng số lượng đã yêu cầu (`request(n)`). Điều này đặc biệt hữu ích cho dữ liệu kiểm thử hoặc sinh số thứ tự mà không chiếm bộ nhớ tuyến tính theo số lượng phần tử.

## 6. Thời điểm phát dữ liệu, backpressure và tính chất của nguồn

Ba factory method tạo `Publisher`; phương thức `subscribe` gắn `Subscriber` vào luồng:

~~~text
Tạo nguồn (assembly):
Flux.range(3, 3)           -> object Flux, chưa có onNext

Đăng ký (subscription):
subscribe(subscriber)      -> onSubscribe(subscription)
subscriber.request(2)      -> onNext(3), onNext(4)
subscriber.request(1)      -> onNext(5), onComplete()
~~~

Đây là luồng tín hiệu khái niệm với một subscriber điều khiển demand. Các overload `subscribe(Consumer)` thường yêu cầu lượng dữ liệu không giới hạn, nên mọi phần tử của nguồn hữu hạn được phát ngay trong cùng luồng gọi nếu không dùng scheduler khác. Với API callback cần kiểm soát demand, có thể dùng `BaseSubscriber` và `request(n)`.

Các đặc điểm cần ghi nhớ:

1. **Nguồn cold mặc định:** Mỗi lần đăng ký sẽ có một vòng phát riêng. `Flux.just` phát lại các phần tử đã giữ; `fromIterable` có thể thấy tình trạng mới của Iterable; `range` tính lại cùng dãy số.
2. **Backpressure:** `just`, `fromIterable` và `range` có thể tôn trọng `request(n)`. Demand là số phần tử tối đa bên nhận cho phép nguồn gửi tại thời điểm đó, không phải yêu cầu nguồn phải phát đủ nếu nó đã hết dữ liệu.
3. **Kết thúc hữu hạn:** Sau khi phát hết dữ liệu, nguồn gửi `onComplete`. Một nguồn rỗng vẫn có thể hoàn tất mà không cần phát phần tử.
4. **Hủy:** `Subscription.cancel()` yêu cầu upstream dừng. Với nguồn có sẵn cực ngắn và `subscribe(Consumer)` chạy đồng bộ, dữ liệu có thể đã phát xong trước lúc bạn có cơ hội hủy từ bên ngoài.
5. **Không tự bất đồng bộ:** Không có thread mới chỉ nhờ gọi `just`, `fromIterable` hoặc `range`. Toán tử `publishOn`/`subscribeOn` và runtime WebFlux có vai trò riêng; chỉ thêm scheduler khi thực sự cần và hiểu giới hạn thread.

## 7. Chương trình Java 17+ hoàn chỉnh, chạy được

Ví dụ dùng Project Reactor Core 3.8.8 (bản phát hành ổn định) và Maven. Tạo hai tệp theo đúng cấu trúc:

~~~text
reactor-ready-data/
├── pom.xml
└── src/main/java/example/ReadyDataSources.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-ready-data</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ReadyDataSources</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/ReadyDataSources.java`**

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReadyDataSources {
    public static void main(String[] args) {
        System.out.println("1. just");

        Mono.just("user-7").subscribe(
            value -> System.out.println("mono=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("mono complete")
        );

        Flux.just("red", "blue").subscribe(
            value -> System.out.println("fixed=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("fixed complete")
        );

        System.out.println("2. fromIterable");

        List<String> colors = new ArrayList<>(List.of("red", "blue"));
        Flux<String> fromList = Flux.fromIterable(colors);
        fromList.subscribe(value -> System.out.println("first=" + value));

        colors.add("green");
        fromList.subscribe(value -> System.out.println("second=" + value));

        System.out.println("3. range");

        Flux.range(5, 3).subscribe(
            value -> System.out.println("number=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("range complete")
        );

        System.out.println("4. backpressure");

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("subscribed");
                // Chưa request: nguồn chưa được phép phát onNext.
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("done");
            }
        };

        Flux.range(10, 4).subscribe(subscriber);
        subscriber.request(2);
        subscriber.request(2);

        System.out.println("5. empty");

        Flux.fromIterable(List.<String>of()).subscribe(
            value -> System.out.println("unexpected=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("empty list complete")
        );

        Flux.range(42, 0).subscribe(
            value -> System.out.println("unexpected=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("zero range complete")
        );
    }
}
~~~

Chạy từ thư mục `reactor-ready-data` (đã cài JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
1. just
mono=user-7
mono complete
fixed=red
fixed=blue
fixed complete
2. fromIterable
first=red
first=blue
second=red
second=blue
second=green
3. range
number=5
number=6
number=7
range complete
4. backpressure
subscribed
received=10
received=11
received=12
received=13
done
5. empty
empty list complete
zero range complete
~~~

Ý nghĩa kết quả:

- `just` phát đúng các giá trị đã liệt kê; `Mono` có một giá trị, `Flux` có hai giá trị.
- `fromIterable` sử dụng cùng một đối tượng `List` nhưng duyệt lại khi có subscription thứ hai, nên subscription sau thấy phần tử `green` được thêm trước đó.
- `range(5, 3)` phát ba số 5–7.
- Subscriber kiểm soát `request(2)` hai lần, nhận lần lượt bốn số rồi mới `onComplete`.
- `List` rỗng và `range` với `count=0` chỉ phát tín hiệu hoàn tất.

## 8. Áp dụng trong Spring WebFlux

Trong controller của Spring WebFlux, bạn có thể **trả Publisher** cho framework quản lý subscription khi xử lý HTTP. Ví dụ sau là minh họa một lớp controller trong dự án **đã có dependency Spring WebFlux** (không phải phần của chương trình Maven Reactor Core độc lập ở mục 7):

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping("/version")
    public Mono<String> version() {
        return Mono.just("v1");
    }

    @GetMapping("/categories")
    public Flux<String> categories() {
        List<String> items = List.of("books", "games", "tools");
        return Flux.fromIterable(items);
    }

    @GetMapping("/positions")
    public Flux<Integer> positions() {
        return Flux.range(1, 4);
    }
}
~~~

Các endpoint theo thứ tự biểu diễn một chuỗi, một tập chuỗi và bốn số nguyên. **Không tự gọi `subscribe()` trong handler** vì framework đảm nhận việc đăng ký, truyền lỗi và hủy khi xử lý response. Những nguồn trong ví dụ hữu ích cho demo, dữ liệu cấu hình hoặc fixture nhỏ; với dữ liệu thực sự từ database, nên dùng repository/driver reactive nếu có.

Trả về `Flux<T>` **không bảo đảm mỗi phần tử được đẩy ngay lập tức đến trình duyệt**. Cách kết xuất HTTP còn phụ thuộc `produces`, codec, buffering và kiểu media. Để yêu cầu truyền từng phần tử theo thời gian, cần hợp đồng response thích hợp như SSE hoặc NDJSON; việc đó tách biệt với cách tạo `Flux`.

## 9. Chọn phương thức đúng trong tình huống thực tế

| Tình huống | Nên dùng | Vì sao |
| --- | --- | --- |
| Đã có một object `Product` không-null | `Mono.just(product)` | Hợp đồng một kết quả |
| Ba trạng thái cố định trong mã | `Flux.just("NEW", "PAID", "DONE")` | Dễ đọc, không cần tạo collection |
| Có sẵn `List<Order>` | `Flux.fromIterable(orders)` | Phát từng `Order` và giữ thứ tự List |
| Muốn 100 số thứ tự từ 1 | `Flux.range(1, 100)` | Không tạo List 100 phần tử |
| API cũ trả một object có thể `null` | `Mono.justOrEmpty(value)` | Biểu diễn kết quả vắng mặt đúng quy tắc |
| Collection rỗng | `Flux.fromIterable(List.of())` hoặc `Flux.empty()` | Có `onComplete` mà không có `onNext` |
| Dữ liệu được tính tốn kém mỗi lần subscribe | `Mono.fromSupplier` / `Mono.defer` | Không đánh giá hàm ngay khi lắp ráp |
| Muốn 0..N kết quả từ DB reactive | Publisher từ driver/repository | Không cố dùng collection vốn chưa được nạp |

## 10. Lỗi phổ biến và cách kiểm tra

**Lỗi 1 — Hiểu `count` là giá trị kết thúc.** `Flux.range(4, 3)` phát `4, 5, 6`, không phải `4, 5, 6, 7` hay `3, 4`. Luôn tự kiểm tra bằng quy tắc `start + count - 1`.

**Lỗi 2 — Bọc cả `List` bằng `Flux.just(list)`.** Một subscriber nhận đúng **một** object `List`. Nếu mong các phần tử của List, dùng `fromIterable(list)`.

**Lỗi 3 — Truyền `null` cho `just` hoặc collection chứa `null`.** Reactive Streams cấm `onNext(null)`. Dùng `Mono.empty()`, `Mono.justOrEmpty`, `filter`/`handle` hoặc loại giá trị null ở biên đầu vào tùy nghiệp vụ.

**Lỗi 4 — Cho rằng mọi nguồn đều chạy ngầm hoặc tạo thread mới.** Những nguồn có sẵn này thường chạy đồng bộ theo nhu cầu; tự đưa tác vụ blocking vào `map` hay iterator vẫn có thể chặn event loop.

**Lỗi 5 — Cho rằng `fromIterable` là snapshot.** Nó giữ tham chiếu Iterable, nên nội dung List có thể đổi giữa các lần subscribe. Nếu cần dữ liệu ổn định, tạo bản sao ở thời điểm phù hợp.

**Lỗi 6 — Tạo custom Iterable chỉ dùng được một lần.** `iterator()` có thể được gọi đến hai lần cho mỗi subscriber. Nguồn phải tuân thủ ngữ nghĩa Iterable, nhất là nếu cho phép đăng ký lại.

**Lỗi 7 — Dùng `Flux.range` cho khoảng quá lớn hoặc tham số không hợp lệ.** Kiểm tra `count >= 0`, giới hạn `int` và nguy cơ tràn số khi tính count từ hai cận.

**Lỗi 8 — Đánh giá hàm tốn kém trong `Mono.just(service.load())` rồi mong khi subscribe mới chạy.** Java đánh giá biểu thức trước; với xử lý lazy chọn `fromSupplier`/`defer` đúng ngữ nghĩa.

**Lỗi 9 — Bỏ qua lỗi khi thử `subscribe`.** Với ví dụ học tập, truyền error consumer và callback hoàn tất để quan sát ba loại tín hiệu. Trong WebFlux hãy trả Publisher cho framework thay vì tự đăng ký.

**Lỗi 10 — Giả định các collection đều có thứ tự phát giống nhau.** `fromIterable` tôn trọng thứ tự iterator; `HashSet` không có thứ tự cố định theo hợp đồng, khác với `List`.

## 11. Bài tập tự kiểm tra

1. Cho `Flux.range(8, 4)`, hãy liệt kê giá trị phát ra. **Đáp án:** 8, 9, 10, 11.
2. Cho `List<String> fruits = List.of("cam", "táo");`. `Flux.just(fruits)` phát bao nhiêu phần tử? `Flux.fromIterable(fruits)` phát bao nhiêu phần tử? **Đáp án:** Lần lượt 1 phần tử kiểu `List<String>` và 2 phần tử kiểu `String`.
3. `Flux.range(1, 0)` có phát số 1 không? **Không**. Luồng rỗng và hoàn tất.
4. Tạo `Flux<String> p = Flux.fromIterable(list)` rồi sửa `list` trước khi `subscribe`. Nội dung có thể thay đổi không? **Có**, vì `Iterable` được duyệt cho lần đăng ký; điều này không tạo push update tự động.
5. Vì sao `Mono.just(fetch())` có thể thực thi `fetch()` dù chưa ai đăng ký? **Vì Java đánh giá đối số lúc gọi method**; muốn trì hoãn, dùng `Mono.fromSupplier(fetch::call)` hoặc `defer` với hàm phù hợp.
6. `Flux.range(1, 1_000_000)` có cần tạo `List` một triệu số trước khi phát không? **Không**. Nguồn sinh dãy theo subscription/demand.

## 12. Tài liệu tham khảo

- [Project Reactor Reference – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).
- [Project Reactor API – Flux.just, Flux.fromIterable, Flux.range](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor API – Mono.just và Mono.justOrEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm#specification): khái niệm Subscriber, Subscription, `request`, tín hiệu và yêu cầu không phát null.
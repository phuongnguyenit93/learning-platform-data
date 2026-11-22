# handle cho logic phát có điều kiện trong Project Reactor

## 1. Khi nào cần \`handle\`?

Khi xử lý dữ liệu reactive, đôi khi một phần tử đầu vào cần được **biến đổi nếu đạt điều kiện**, **bỏ qua nếu không hợp lệ**, hoặc **chấm dứt luồng nếu gặp tín hiệu nghiệp vụ đặc biệt**. Chuỗi \`filter(...).map(...)\` có thể đáp ứng nhiều trường hợp, nhưng đôi khi việc lọc và tính kết quả dùng chung một phép tính, hoặc hàm chuyển đổi có thể trả \`null\`, hoặc cần phát lỗi tại đúng nhánh xử lý.

Trong Project Reactor, toán tử **\`handle\`** cung cấp một \`SynchronousSink\` cho **mỗi phần tử mà nguồn upstream phát ra**. Callback quyết định có phát phần tử kết quả hay không:

- Gọi \`sink.next(output)\` **tối đa một lần** cho một lần callback để phát kết quả.
- Không gọi \`sink.next\` nếu muốn **bỏ qua phần tử đầu vào**.
- Gọi \`sink.error(exception)\` khi muốn **kết thúc bằng lỗi**.
- Gọi \`sink.complete()\` khi muốn **kết thúc bình thường ngay tại đây**.

Toán tử này có trong cả **\`Flux\` lẫn \`Mono\`**. Với \`Flux\`, số phần tử đầu ra có thể ít hơn số phần tử đầu vào; với \`Mono\`, kết quả vẫn là **0 hoặc 1 phần tử**. \`handle\` không tạo dòng dữ liệu độc lập từ đầu và không phải API phát bất đồng bộ cho callback chạy sau.

Ví dụ cốt lõi:

~~~java
Flux<Integer> positive =
        Flux.just(-3, 2, 0, 5)
            .<Integer>handle((number, sink) -> {
                if (number > 0) {
                    sink.next(number * 10);
                }
            });
// Khi subscribe: phát 20, 50 rồi hoàn tất.
~~~

Đoạn code này minh họa một biểu thức trong phương thức Java đã import \`reactor.core.publisher.Flux\`, chưa phải class độc lập. Phần tử âm và \`0\` không có tín hiệu \`onNext\` đầu ra vì callback không gọi \`sink.next\`.

## 2. Vị trí của \`handle\` trong pipeline

~~~text
Flux<T> upstream
    |
    | onNext(input)
    v
handle((input, sink) -> ...)
    |
    +-- sink.next(result) --> downstream nhận onNext(result)
    |
    +-- không next() ------> bỏ qua input, chờ input kế tiếp
    |
    +-- sink.error(err) ---> downstream nhận onError(err), kết thúc
    |
    +-- sink.complete() ---> downstream nhận onComplete(), kết thúc
~~~

Với nguồn upstream hoàn tất bình thường sau khi phát hết dữ liệu, downstream cũng sẽ hoàn tất ngay cả khi callback \`handle\` không gọi \`complete()\`. \`handle\` chỉ được gọi với **phần tử \`onNext\` của upstream**: nếu upstream là \`Flux.empty()\`, \`Mono.empty()\` hoặc lỗi trước khi phát bất kỳ phần tử nào, callback \`handle\` không được gọi để tự sinh dữ liệu.

Các chữ ký khái niệm:

~~~java
// Project Reactor Flux<T>:
<R> Flux<R> handle(BiConsumer<? super T, SynchronousSink<R>> handler);

// Project Reactor Mono<T>:
<R> Mono<R> handle(BiConsumer<? super T, SynchronousSink<R>> handler);
~~~

\`BiConsumer\` nhận hai tham số: **đầu vào \`T\`** và **sink cho kết quả \`R\`**. Nếu type inference chưa suy ra kiểu đầu ra rõ ràng, khai báo tường minh \`.<Integer>handle(...)\` hoặc \`.<String>handle(...)\`.

Đặc tả \`SynchronousSink\` cho phép **tối đa một \`next\` và tối đa một tín hiệu kết thúc** (\`complete\` hoặc \`error\`) trong mỗi invocation. Có thể gọi \`next\` rồi \`complete\` để phát phần tử cuối cùng và kết thúc, nhưng **không gọi nhiều lần \`next\`**, cũng không phát cả \`complete\` lẫn \`error\`. Trình tự đơn giản, dễ hiểu là chọn **một nhánh xử lý rõ ràng** rồi \`return\` sau tín hiệu kết thúc.

## 3. Kết quả của mỗi nhánh xử lý

| Trong callback \`handle\` | Tín hiệu đầu ra | Ý nghĩa |
| --- | --- | --- |
| \`sink.next(value)\` | Phát một phần tử \`value\` khác null | Biến đổi hoặc giữ lại đầu vào |
| Không gọi hàm phát | Không có \`onNext\` cho đầu vào này | Lọc bỏ phần tử |
| \`sink.error(e)\` | Phát \`onError(e)\` và kết thúc luồng | Dữ liệu không hợp lệ đến mức phải dừng |
| \`sink.complete()\` | Phát \`onComplete()\` và kết thúc luồng | Đạt điều kiện dừng sớm |
| \`sink.next(v)\` rồi \`sink.complete()\` | Phát phần tử cuối và hoàn tất | Có thể dùng nhưng cần tuân thủ giới hạn tín hiệu |

**Không được \`sink.next(null)\`.** Reactive Streams/Reactor không cho phép \`null\` là một phần tử \`onNext\`; nếu dữ liệu không tồn tại, bỏ qua \`next\` hoặc biểu diễn trạng thái tùy chọn bằng một object khác (ví dụ \`Optional\`, nếu bài toán yêu cầu).

**Không dùng \`sink.error\` để loại một bản ghi xấu rồi tiếp tục xử lý phần tử kế tiếp.** \`error\` là sự kiện terminal cho subscription đó. Nếu mục tiêu là “bỏ qua bản ghi sai nhưng vẫn xử lý các bản ghi sau”, không gọi \`next\` cho bản ghi sai; nếu mục tiêu là “fail fast”, gọi \`error\`.

## 4. \`handle\` khác \`map\`, \`filter\`, \`flatMap\` và \`generate\` thế nào?

| Operator | Số phần tử phát theo một input | Cách hoạt động | Khi nên chọn |
| --- | --- | --- | --- |
| \`map\` | Đúng một phần tử hợp lệ | Từ \`T\` tính ra \`R\` | Phép biến đổi thuần, luôn tạo giá trị khác null |
| \`filter\` | 0 hoặc 1, giữ nguyên kiểu \`T\` | Kiểm tra predicate và giữ/bỏ đầu vào | Chỉ cần điều kiện và không đổi kiểu |
| \`filter(...).map(...)\` | 0 hoặc 1 | Lọc rồi biến đổi qua hai operator | Dễ đọc khi điều kiện tách biệt khỏi phép biến đổi |
| **\`handle\`** | **0 hoặc 1** | Callback đồng bộ quyết định phát, bỏ qua, lỗi hoặc dừng | Lọc và map trong một bước; dùng kết quả chuyển đổi một lần; quy tắc có nhánh |
| \`flatMap\` | Có thể 0, 1 hoặc nhiều | Mỗi input trở thành một Publisher con | Công việc bất đồng bộ hoặc một input có nhiều output |
| \`concatMap\` | Có thể 0, 1 hoặc nhiều | Subscribe Publisher con theo thứ tự | Cần giữ thứ tự và xử lý Publisher con |
| \`Flux.generate\` | Tối đa một \`next\` mỗi vòng tạo | Tạo sequence từ generator, không cần Flux upstream | Sinh dữ liệu từng bước từ state/generator |
| \`Flux.create\` / \`Mono.create\` | Phụ thuộc sink và API | Nối nguồn callback tùy ý, có thể bất đồng bộ | Tích hợp API callback/event bên ngoài |

Đặc điểm dễ nhớ: **\`handle\` là phép biến đổi một input có thể cho không có output**. \`generate\` là cách **tạo nguồn** (source generator); \`handle\` là cách **xử lý luồng đã tồn tại**.

Nếu chỉ cần \`filter(n -> n > 0).map(n -> n * 10)\`, hai operator quen thuộc thường sáng sủa hơn \`handle\`. Lợi ích của \`handle\` nổi bật khi điều kiện cần thông tin từ kết quả chuyển đổi, ví dụ hàm parse trả \`null\` hoặc không muốn parse cùng chuỗi hai lần.

## 5. Tình huống 1 — parse dữ liệu và bỏ qua giá trị không hợp lệ

Giả sử nhận nhiều chuỗi đầu vào; chỉ phát **số nguyên dương**. Ta cần xử lý các trường hợp chuỗi không phải số, \`0\`, số âm, và vẫn tiếp tục xử lý những chuỗi còn lại.

~~~java
Flux<Integer> parsed = Flux.just(" 12 ", "bad", "3", "0", "-5", " 7 ")
    .<Integer>handle((raw, sink) -> {
        try {
            int number = Integer.parseInt(raw.trim());
            if (number > 0) {
                sink.next(number);
            }
        } catch (NumberFormatException ignored) {
            // Chính sách của ví dụ: bỏ qua bản ghi không parse được.
        }
    });

// Khi subscribe: 12, 3, 7.
~~~

Đây là ví dụ thích hợp cho \`handle\` vì việc **chuyển chuỗi sang số** và **kiểm tra số dương** gắn với nhau; parse đúng một lần. Trong ứng dụng thật, quyết định bỏ qua đầu vào có lỗi cần dựa trên yêu cầu nghiệp vụ; nên đo số bản ghi bị loại hoặc ghi thông tin lỗi ở mức phù hợp. Không mặc định im lặng bỏ dữ liệu quan trọng.

Nếu chỉ muốn giải mã có điều kiện theo phương thức trả \`null\`, có thể làm:

~~~java
String parsedOrNull = legacyLookup(input);
if (parsedOrNull != null) {
    sink.next(parsedOrNull);
}
~~~

Đoạn trong callback này là **mã minh họa**, giả định có \`input\`, \`sink\` và hàm \`legacyLookup\`. Không được viết \`map(this::legacyLookup)\` nếu hàm có thể trả \`null\`, vì \`map\` không chấp nhận giá trị \`null\` được phát. Ở các phiên bản Reactor hỗ trợ \`mapNotNull\`, toán tử đó cũng là lựa chọn ngắn gọn riêng cho trường hợp “map rồi bỏ kết quả null”; \`handle\` hữu ích khi logic có nhiều nhánh hơn.

## 6. Tình huống 2 — phân biệt “bỏ qua” và “lỗi”

Cùng là chuỗi sai định dạng, có ít nhất hai **chính sách nghiệp vụ**:

**Chính sách khoan dung:** bỏ qua input lỗi, tiếp tục đọc các input khác.

~~~java
Flux<Integer> tolerant = Flux.just("1", "oops", "2")
    .<Integer>handle((text, sink) -> {
        try {
            sink.next(Integer.parseInt(text));
        } catch (NumberFormatException ignored) {
            // Không phát output cho "oops".
        }
    });
// Đầu ra: 1, 2, rồi complete.
~~~

**Chính sách nghiêm ngặt:** dừng cả luồng tại input lỗi.

~~~java
Flux<Integer> strict = Flux.just("1", "oops", "2")
    .<Integer>handle((text, sink) -> {
        try {
            sink.next(Integer.parseInt(text));
        } catch (NumberFormatException error) {
            sink.error(new IllegalArgumentException(
                    "Invalid number: " + text, error));
        }
    });
// Đầu ra: 1, rồi onError(IllegalArgumentException).
// "2" không được xử lý tiếp bởi subscription này.
~~~

Các đoạn trên là biểu thức trong phương thức Java đã import \`Flux\`. Cả hai đều đúng về mặt cú pháp nhưng mang **ý nghĩa nghiệp vụ khác nhau**. Nếu downstream đặt \`onErrorResume\`, có thể thay thế luồng bằng fallback **sau lỗi**, nhưng không nên hiểu rằng điều đó khôi phục việc xử lý những phần tử nguồn bị ngắt sau lỗi; nguồn đã kết thúc/cancel theo terminal semantics.

Ví dụ:

~~~java
List<Integer> values = strict
        .onErrorResume(IllegalArgumentException.class, e -> Flux.just(-1))
        .collectList()
        .block();
// Với nguồn strict ở trên: [1, -1].
// Input "2" không được tự động xử lý lại.
~~~

## 7. Tình huống 3 — dừng sớm theo nội dung dữ liệu

Khi luồng chứa một giá trị đánh dấu điểm kết thúc, \`sink.complete()\` có thể kết thúc mà không chờ upstream phát hết:

~~~java
Flux<Integer> untilStop = Flux.just(10, 20, -1, 30)
    .<Integer>handle((number, sink) -> {
        if (number == -1) {
            sink.complete();
            return;
        }
        sink.next(number);
    });
// Đầu ra: 10, 20, rồi complete.
// 30 không được chuyển đến handler trong subscription này.
~~~

\`sink.complete()\` là tín hiệu kết thúc của **toàn bộ subscription downstream**, không phải “bỏ qua input -1 rồi chờ input kế tiếp”. Nếu muốn chỉ bỏ qua giá trị đánh dấu mà vẫn xử lý số 30, không gọi \`complete()\`:

~~~java
Flux<Integer> withoutMarker = Flux.just(10, 20, -1, 30)
    .<Integer>handle((number, sink) -> {
        if (number != -1) {
            sink.next(number);
        }
    });
// Đầu ra: 10, 20, 30, rồi complete.
~~~

Có thể phát phần tử cuối rồi complete trong cùng callback khi bài toán đòi hỏi. Ví dụ “đọc tới và bao gồm số 3”:

~~~java
Flux<Integer> throughThree = Flux.range(1, 5)
    .<Integer>handle((n, sink) -> {
        sink.next(n);
        if (n == 3) {
            sink.complete();
        }
    });
// Đầu ra: 1, 2, 3, rồi complete.
~~~

Cả ba ví dụ là những đoạn biểu thức độc lập ở mức operator, không phải chương trình Java hoàn chỉnh. Trong thực tế, những nguồn có side effect hoặc đọc trước theo buffer/prefetch có thể thực hiện một phần công việc upstream trước khi cancellation lan truyền; \`complete\` không phải cam kết “không có bất kỳ byte/tác vụ upstream nào đã được xử lý trước”.

## 8. Tình huống 4 — \`Mono.handle\` cho kết quả có hoặc không

Một \`Mono<T>\` phát tối đa một phần tử thành công. \`Mono.handle\` có thể biến phần tử đó sang kiểu \`R\`, hoặc **không phát gì** nếu điều kiện không thỏa.

~~~java
Mono<String> source = Mono.just("  hello ");
Mono<String> normalized = source.<String>handle((raw, sink) -> {
    String value = raw.trim();
    if (!value.isBlank()) {
        sink.next(value.toUpperCase());
    }
});
// normalized: Mono phát "HELLO".
~~~

Nếu input là chuỗi toàn khoảng trắng, \`handle\` không gọi \`next\`, kết quả là **\`Mono.empty()\` về mặt tín hiệu**:

~~~java
Mono<String> empty = Mono.just("   ")
    .<String>handle((raw, sink) -> {
        String value = raw.trim();
        if (!value.isEmpty()) {
            sink.next(value);
        }
    });

Boolean hasValue = empty.hasElement().block(); // false
~~~

Nếu **upstream đã rỗng**, ví dụ \`Mono.<String>empty().handle(...)\`, callback cũng không được gọi. \`handle\` không tự biến một \`Mono.empty()\` thành một giá trị mặc định; với tình huống đó, dùng \`defaultIfEmpty\`, \`switchIfEmpty\` hoặc \`onErrorResume\` theo loại tín hiệu và yêu cầu.

Ví dụ xác định rõ nghiệp vụ:

~~~java
Mono<String> answer = Mono.just(" ")
    .<String>handle((raw, sink) -> {
        String trimmed = raw.trim();
        if (!trimmed.isEmpty()) sink.next(trimmed);
    })
    .defaultIfEmpty("UNKNOWN");
// Khi subscribe, answer phát "UNKNOWN".
~~~

Dùng \`handle\` khi “giá trị hiện diện nhưng không hợp lệ” có thể được mô hình thành “không có kết quả”. Nếu việc không hợp lệ phải là **lỗi**, phát \`sink.error\` thay vì bỏ qua.

## 9. Chương trình Java 17+ hoàn chỉnh, có kết quả kiểm chứng được

Chương trình sau gom các tình huống thành một ví dụ có thể biên dịch và chạy. Nó cho thấy:

1. Phát có điều kiện với \`Flux.handle\`.
2. \`Mono.handle\` trả 1 hoặc 0 phần tử.
3. \`sink.error\` làm kết thúc luồng và \`onErrorResume\` thay lỗi bằng fallback.
4. \`sink.complete\` dừng luồng tại phần tử đánh dấu.

Yêu cầu: **JDK 17+** và **Maven 3.9+**. Tạo cấu trúc:

~~~text
reactor-handle-demo/
├── pom.xml
└── src/main/java/example/HandleDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-handle-demo</artifactId>
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

**src/main/java/example/HandleDemo.java**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class HandleDemo {
    public static void main(String[] args) {
        Flux<Integer> accepted = Flux.just(
                " 12 ", "skip", "3", "0", "-5", " 7 ")
            .<Integer>handle((raw, sink) -> {
                try {
                    int number = Integer.parseInt(raw.trim());
                    if (number > 0) {
                        sink.next(number);
                    }
                } catch (NumberFormatException ignored) {
                    // Demo: các chuỗi không hợp lệ bị bỏ qua.
                }
            });

        System.out.println("accepted=" + accepted.collectList().block());

        Mono<Integer> one = Mono.just(" 42 ")
            .<Integer>handle((raw, sink) ->
                    sink.next(Integer.parseInt(raw.trim())));

        Mono<String> none = Mono.just("  ")
            .<String>handle((raw, sink) -> {
                if (!raw.isBlank()) {
                    sink.next(raw.trim());
                }
            });

        System.out.println("one=" + one.block());
        System.out.println("none.hasValue=" + none.hasElement().block());

        Flux<Integer> strict = Flux.just("2", "bad", "4")
            .<Integer>handle((raw, sink) -> {
                try {
                    sink.next(Integer.parseInt(raw));
                } catch (NumberFormatException cause) {
                    sink.error(new IllegalArgumentException(
                            "bad number: " + raw, cause));
                }
            });

        System.out.println("strictRecovered=" +
                strict.onErrorResume(IllegalArgumentException.class,
                        error -> Flux.just(-1))
                      .collectList().block());

        Flux<Integer> untilMarker = Flux.range(1, 5)
            .<Integer>handle((number, sink) -> {
                if (number == 4) {
                    sink.complete();
                    return;
                }
                sink.next(number);
            });

        System.out.println("untilMarker=" +
                untilMarker.collectList().block());
    }
}
~~~

Từ thư mục \`reactor-handle-demo\`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.HandleDemo
~~~

**Các dòng do chương trình in:**

~~~text
accepted=[12, 3, 7]
one=42
none.hasValue=false
strictRecovered=[2, -1]
untilMarker=[1, 2, 3]
~~~

Giải thích từng dòng:

- \`accepted\`: chuỗi \`skip\` không parse được, \`0\` và \`-5\` không dương, nên chỉ phát \`12, 3, 7\`.
- \`one\`: \`Mono.handle\` chuyển \`" 42 "\` sang số \`42\`.
- \`none.hasValue\`: vì input toàn khoảng trắng không gọi \`next\`, \`Mono\` hoàn tất rỗng.
- \`strictRecovered\`: phát \`2\`, gặp \`bad\` thì phát lỗi; \`onErrorResume\` thay lỗi bằng \`-1\`. Chuỗi \`"4"\` phía sau **không được tự động phát tiếp**.
- \`untilMarker\`: khi input bằng \`4\`, callback gọi \`complete\`; \`5\` không trở thành output.

Các thao tác \`block()\` trong ví dụ chỉ ở **ranh giới chương trình console** để thu kết quả dễ quan sát. Trong WebFlux hoặc trên event-loop, thông thường cần **trả Publisher cho framework xử lý**, tránh \`block()\` trong luồng request.

## 10. Giới hạn đồng bộ của \`SynchronousSink\`

Tên **SynchronousSink** là một ràng buộc thật sự. Phải gọi \`next\`, \`error\` hoặc \`complete\` **trong thời gian callback \`handle\` đang chạy**. Không lưu \`sink\` vào biến toàn cục, hàng đợi hoặc callback sẽ được kích hoạt sau:

~~~java
// SAI về hợp đồng SynchronousSink:
Flux<String> invalid = Flux.just("a")
    .<String>handle((value, sink) -> {
        someAsyncClient.fetch(value, result -> {
            sink.next(result); // Callback chạy sau khi handle đã trả về.
        });
    });
~~~

Đây chỉ là **đoạn minh họa phản ví dụ**: \`someAsyncClient\` chưa được khai báo và không phải source runnable. Sai ở việc sử dụng \`sink\` bất đồng bộ, dù cú pháp callback có thể trông hợp lý. \`SynchronousSink\` không được thiết kế để lưu rồi phát từ sự kiện đến sau.

Nếu công việc trả **\`Mono<R>\` hoặc \`Flux<R>\`**, chọn operator xử lý Publisher con:

~~~java
Flux<Result> results = requests.flatMap(
        request -> asyncService.fetch(request)
);
~~~

Đây cũng là đoạn **minh họa**, giả định \`requests\` là \`Flux<Request>\` và \`asyncService.fetch(request)\` trả \`Mono<Result>\`. \`flatMap\` có thể cho nhiều inner publisher chạy đồng thời và không bảo đảm thứ tự đầu ra tương ứng thứ tự input. Nếu cần giữ thứ tự theo chính sách cụ thể, xem \`concatMap\` hoặc \`flatMapSequential\`.

Nếu cần **chuyển một API callback thành nguồn reactive**, xem \`Mono.create\`, \`Flux.create\`, các API \`Sinks\` và chính sách cancellation/backpressure thích hợp. Sau khi có \`Mono\`/\`Flux\` hợp lệ, dùng \`flatMap\`/\`concatMap\` để ghép vào luồng. Đừng dùng \`handle\` như một “cổng phát sự kiện bất đồng bộ” vì hợp đồng nó là đồng bộ.

## 11. \`handle\` có tự tạo thread, non-blocking hoặc backpressure mới không?

**Không.** \`handle\` là operator xử lý tín hiệu của một Publisher hiện có. Callback thường chạy trên thread đang đưa \`onNext\` qua pipeline, trừ khi các phần khác thay đổi ngữ cảnh thực thi (chẳng hạn \`publishOn\`).

~~~java
Flux<String> source = Flux.just("a", "b")
    .<String>handle((value, sink) -> {
        // Đây là xử lý đồng bộ trên thread được dùng cho pipeline.
        sink.next(value.toUpperCase());
    });
~~~

Nếu callback gọi \`Thread.sleep\`, JDBC synchronous hoặc một HTTP client blocking, nó vẫn **chặn thread hiện tại**. Trong ứng dụng WebFlux, việc blocking trên Netty event-loop có thể làm chậm các request khác. Không nên thêm \`handle\` với kỳ vọng tự xử lý vấn đề threading; chọn API thực sự non-blocking hoặc cô lập công việc blocking bằng scheduler phù hợp như \`boundedElastic\` khi bắt buộc dùng hệ thống cũ.

**Backpressure** vẫn theo hợp đồng Reactive Streams. \`handle\` có thể bỏ qua một số input và vì vậy downstream muốn \`N\` kết quả có thể khiến upstream cần xử lý hơn \`N\` phần tử đầu vào. Đừng suy diễn \`request(1)\` downstream luôn tương ứng đúng một \`onNext\` upstream; operator, fusion, prefetch, nguồn và cancellation ảnh hưởng chi tiết thực thi.

Đặc biệt, \`handle\` không phải một cơ chế điều tiết bộ nhớ tổng thể. Nếu upstream nhanh hơn khả năng xử lý, hãy xem xét toàn bộ nguồn, buffer, tốc độ downstream và chính sách quản lý tài nguyên. Bỏ qua phần tử đầu vào không bảo đảm upstream không có tác dụng phụ trước đó.

## 12. Ngữ nghĩa error, completion và cancellation

Một pipeline có thể kết thúc theo ba hướng:

| Tình huống | Đến downstream | Có xử lý tiếp input sau đó không? |
| --- | --- | --- |
| Callback không gọi \`next\` | Không có onNext cho input này | **Có**, nếu upstream vẫn phát |
| Callback gọi \`error\` | onError terminal | **Không**, trên subscription này |
| Callback gọi \`complete\` | onComplete terminal | **Không**, trên subscription này |
| Upstream tự hoàn tất | onComplete terminal khi các tín hiệu đã xử lý xong | Không |
| Downstream cancel | Subscription bị hủy | Không còn quyền tiếp tục phát theo subscription; việc dừng tài nguyên upstream tùy implementation |

Trong một nhánh nghiệp vụ, dùng \`sink.error\` khi **thực sự muốn đóng luồng bằng lỗi**. Nếu chỉ cần tiếp tục nhưng không phát dữ liệu, để callback kết thúc bình thường mà không \`next\`.

Khi callback ném \`RuntimeException\`, Reactor có thể truyền lỗi thành \`onError\`; dùng \`onErrorResume\` hoặc \`onErrorMap\` downstream khi cần. Nên xử lý lỗi rõ ràng theo chính sách ứng dụng. **Tránh dùng \`onErrorContinue\` như cách mặc định để cứu toàn bộ luồng**, bởi hành vi còn phụ thuộc operator và có thể khiến ý nghĩa lỗi, phần tử bị bỏ và phạm vi xử lý khó dự đoán.

\`handle\` có thể mang side effect như log, tăng metric hoặc gọi dịch vụ. Nếu pipeline bị **retry/resubscribe**, callback có thể chạy lại cho những input được nguồn phát lại. Các side effect phải được thiết kế phù hợp; \`handle\` không cung cấp bảo đảm “chỉ chạy đúng một lần” qua nhiều subscription.

## 13. Dùng \`handle\` trong Spring WebFlux

Trong WebFlux, controller có thể trả \`Flux<R>\` đã được lọc/biến đổi với \`handle\`; framework chịu trách nhiệm subscribe và biến dữ liệu thành HTTP response.

Ví dụ controller, giả định đây là một ứng dụng Spring Boot WebFlux đã có dependencies phù hợp:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class NumberController {

    @GetMapping("/positive-numbers")
    public Flux<Integer> positiveNumbers() {
        return Flux.just("10", "bad", "-1", "4")
            .<Integer>handle((raw, sink) -> {
                try {
                    int value = Integer.parseInt(raw);
                    if (value > 0) {
                        sink.next(value);
                    }
                } catch (NumberFormatException ignored) {
                    // Ví dụ: loại đầu vào sai định dạng.
                }
            });
    }
}
~~~

Đoạn trên là một controller Java đầy đủ nhưng **cần đặt trong project Spring Boot WebFlux và cấu hình/entry point để chạy server**; không thể chạy độc lập bằng \`java NumberController\`. Khi truy cập endpoint với HTTP JSON mặc định, phần dữ liệu tương ứng là \`[10,4]\`.

Cần phân biệt **“lược bỏ phần tử”** với **“từ chối HTTP request”**. Nếu payload người dùng sai và hợp đồng API yêu cầu lỗi 400, không nên âm thầm loại toàn bộ dữ liệu bằng \`handle\`. Khi cần từ chối request, dùng validation và error mapping phù hợp (ví dụ \`ResponseStatusException\`, \`@Valid\`, hoặc luồng xử lý lỗi của WebFlux), tránh khiến client hiểu rằng đầu vào đã được chấp nhận đầy đủ.

Đối với dữ liệu rất lớn hoặc streaming, hãy kiểm tra media type, khả năng viết response, cancellation và tính chính xác của lựa chọn bỏ dữ liệu. \`handle\` chỉ xử lý các phần tử khi Publisher được đăng ký; nó không thay thế kiểm soát tài nguyên network/server.

## 14. Mẫu dùng an toàn: một callback, một quyết định

Một callback \`handle\` dễ đọc thường tuân theo thứ tự:

~~~java
Flux<Output> result = source.<Output>handle((input, sink) -> {
    // 1. Kiểm tra điều kiện cần dừng toàn luồng.
    if (shouldStop(input)) {
        sink.complete();
        return;
    }

    // 2. Kiểm tra trường hợp đầu vào không cần phát.
    if (shouldSkip(input)) {
        return;
    }

    // 3. Tính output (có thể ném lỗi nếu policy yêu cầu).
    Output output = transform(input);

    // 4. Quyết định phát hay bỏ output.
    if (output != null) {
        sink.next(output);
    }
});
~~~

Đây là **pseudocode Java có kiểu gợi ý**, không phải chương trình độc lập; \`source\`, \`Output\`, \`shouldStop\`, \`shouldSkip\`, \`transform\` cần được định nghĩa theo ứng dụng. Không nhất thiết mọi callback phải có đủ bốn bước. Mục tiêu là để reviewer nhìn thấy rõ **nhánh bỏ qua**, **nhánh lỗi/dừng** và **nhánh phát dữ liệu**.

Với lỗi validate, có thể phát:

~~~java
if (isInvalid(input)) {
    sink.error(new IllegalArgumentException("invalid input"));
    return;
}
~~~

Nếu đầu ra là một **Publisher bất đồng bộ**, dùng \`flatMap\`:

~~~java
Flux<Output> result = source.flatMap(input -> transformAsync(input));
~~~

Nếu chỉ cần điều kiện giữ/bỏ đơn giản, dùng \`filter\`:

~~~java
Flux<Integer> result = Flux.range(1, 10).filter(n -> n % 2 == 0);
~~~

Nếu chỉ cần biến đổi mọi phần tử thành một giá trị hợp lệ, dùng \`map\`:

~~~java
Flux<Integer> result = Flux.range(1, 10).map(n -> n * 2);
~~~

Cả ba minh họa cuối cần nằm trong method hoặc class Java có khai báo nguồn/hàm tương ứng.

## 15. Những lỗi thường gặp và cách nhận ra

| Sai lầm | Biểu hiện / hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| Gọi \`sink.next\` nhiều lần trong một callback | Vi phạm hợp đồng SynchronousSink; có thể phát lỗi khi thực thi | Chỉ tối đa một \`next\` mỗi input; một input → nhiều output thì dùng \`flatMap\` hoặc operator thích hợp |
| Gọi \`sink.next(null)\` | Không có phần tử null hợp lệ trong Reactor | Bỏ qua \`next\` hoặc chuyển null sang giá trị hợp lệ |
| Không gọi \`next\` nhưng mong phần tử vẫn đi qua | Đầu ra bị mất cho input đó | \`handle\` **không tự forward** input; phải gọi \`sink.next(input)\` |
| Lưu \`SynchronousSink\` để gọi từ callback async | Vi phạm ranh giới đồng bộ của sink | Dùng Mono.create/Flux.create/Sinks và ghép bằng flatMap |
| Dùng \`sink.error\` để “skip” bản ghi xấu | Luồng kết thúc, các phần tử sau không được xử lý | Nếu muốn tiếp tục, không gọi \`next\` |
| Dùng \`sink.complete\` để “bỏ qua một phần tử” | Toàn luồng kết thúc sớm | Chỉ bỏ qua bằng cách không phát dữ liệu |
| Tưởng \`handle\` tự giúp code blocking an toàn | Thread đang xử lý tín hiệu vẫn bị chặn | Dùng API non-blocking hoặc xử lý blocking ở scheduler phù hợp |
| Gắn \`block()\` trong \`handle\` để chờ Mono khác | Có thể chặn event-loop, dễ bế tắc hoặc ném lỗi trong thread không cho phép blocking | Dùng \`flatMap\` để kết hợp Publisher |
| Không phân biệt nullable result với lỗi nghiệp vụ | Có thể âm thầm mất dữ liệu hoặc gây lỗi không mong muốn | Thiết kế rõ chính sách skip/error/default |
| Khẳng định thứ tự thread cố định | Sai khi pipeline có scheduler hoặc nguồn bất đồng bộ | Dựa vào contract operator; dùng \`publishOn\`/\`subscribeOn\` khi cần |

Một vấn đề nâng cao là **discard**: khi một phần tử bị loại trong pipeline, tài nguyên nằm trong phần tử đó (nếu có) vẫn cần được quản lý đúng theo loại dữ liệu. Đối với object có vòng đời đặc biệt như buffer reference-counted, không giả định việc “không gọi next” đã tự đóng mọi tài nguyên. Kiểm tra hợp đồng của nguồn, các hook discard được hỗ trợ và quy tắc giải phóng tài nguyên của thư viện tương ứng.

## 16. Gợi ý kiểm thử các nhánh quan trọng

Với một \`handle\` có nhiều nhánh, nên kiểm tra riêng:

1. **Đầu vào hợp lệ**: phát đúng giá trị và đúng thứ tự kỳ vọng.
2. **Đầu vào bị bỏ**: không phát phần tử nhưng subscription vẫn xử lý input tiếp theo.
3. **Đầu vào lỗi**: phát đúng kiểu lỗi và ngừng phát các phần tử tiếp theo.
4. **Điều kiện complete**: kết thúc ở vị trí mong muốn.
5. **Nguồn rỗng**: callback không được gọi, downstream nhận complete.
6. **Mono.handle**: đầu ra chỉ 0 hoặc 1 phần tử.
7. **Hủy subscription/backpressure**: nếu nguồn có tác dụng phụ hoặc tài nguyên, xác nhận hành vi hủy và giới hạn tải bằng kiểm thử tích hợp phù hợp.

Trong ứng dụng Reactor, thư viện **reactor-test** cung cấp \`StepVerifier\` để mô tả các tín hiệu mong đợi:

~~~java
StepVerifier.create(
        Flux.just(-2, 3, 0, 5)
            .<Integer>handle((n, sink) -> {
                if (n > 0) sink.next(n * 2);
            })
)
    .expectNext(6, 10)
    .verifyComplete();
~~~

Đây là đoạn test minh họa, cần dependency \`io.projectreactor:reactor-test\` với phiên bản tương ứng \`reactor-core\`, import \`reactor.test.StepVerifier\` và chạy trong test method phù hợp. Nó kiểm tra **giá trị và tín hiệu complete**, không chỉ kết quả của thao tác \`collectList\`.

## 17. Tự kiểm tra kiến thức

**Câu 1.** \`Flux.just("1", "bad", "2")\` đi qua \`handle\` chỉ gọi \`next\` với các chuỗi parse được. Kết quả?

Phát \`1\`, \`2\`, rồi complete. Input \`bad\` bị bỏ qua **nếu callback đã bắt NumberFormatException và không phát error**.

**Câu 2.** Nếu callback \`handle\` không gọi bất kỳ phương thức nào trên sink, đầu vào sẽ đi tiếp chứ?

Không. \`handle\` không tự truyền input xuống downstream; input đó được bỏ qua. Callback tiếp tục được gọi với các input tiếp theo khi nguồn phát và subscription còn hoạt động.

**Câu 3.** Sự khác nhau giữa \`sink.complete()\` và không gọi \`sink.next\`?

Không gọi \`next\` chỉ loại **một input**. Gọi \`complete\` kết thúc **cả luồng** trên subscription đó.

**Câu 4.** Có thể gọi \`sink.next(a)\` và \`sink.next(b)\` cho cùng một input để phát hai kết quả không?

Không. \`SynchronousSink\` giới hạn tối đa một \`next\` mỗi lần callback. Nếu một input sinh nhiều phần tử, ánh xạ thành \`Flux\` qua \`flatMap\`/\`concatMap\` hoặc xây nguồn thích hợp.

**Câu 5.** Có thể dùng \`handle\` để phát sau khi nhận HTTP response từ callback bất đồng bộ không?

Không an toàn. \`SynchronousSink\` phải được dùng trong callback hiện tại. Dùng một API reactive hoặc bridge callback sang Mono/Flux rồi kết hợp qua \`flatMap\`.

**Câu 6.** \`Mono.handle\` được gọi với \`Mono.empty()\` chứ?

Không. Không có \`onNext\` upstream nên callback không được gọi; downstream nhận complete rỗng.

**Câu 7.** Khi nào \`filter().map()\` dễ hiểu hơn \`handle\`?

Khi điều kiện giữ/bỏ và phép biến đổi tách biệt rõ ràng, không cần tính chung hoặc điều khiển terminal signal. Chọn operator đơn giản nhất mô tả đúng ý định.

**Câu 8.** Nếu callback \`handle\` thực hiện JDBC blocking, nó có tự chạy sang thread khác không?

Không. \`handle\` là callback đồng bộ; phải chọn nơi thực thi phù hợp hoặc đổi sang driver non-blocking. Trong WebFlux tránh chặn event-loop.

## 18. Tài liệu tham khảo

- **Project Reactor Reference Guide — Handle**: [Programmatically creating a sequence, phần Handle](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- **Reactor API — Flux.handle(...)**: [Flux JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html).
- **Reactor API — Mono.handle(...)**: [Mono JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html).
- **Reactor API — SynchronousSink**: [SynchronousSink JavaDoc](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/SynchronousSink.html).
- **Reactor testing**: [StepVerifier documentation](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).

**Ghi nhớ:** **\`handle\` xử lý từng phần tử từ upstream một cách đồng bộ và quyết định phát \`0\` hoặc \`1\` phần tử, hoàn tất hoặc báo lỗi**. Một callback chỉ được gọi \`sink.next\` tối đa một lần; **không \`next\` là bỏ qua input**, **\`complete\` là kết thúc luồng**, **\`error\` là kết thúc lỗi**. Chọn \`handle\` khi việc lọc và biến đổi gắn với nhau hoặc khi cần điều khiển tín hiệu theo từng phần tử; dùng \`flatMap\` cho công việc bất đồng bộ hay một input sinh nhiều kết quả.
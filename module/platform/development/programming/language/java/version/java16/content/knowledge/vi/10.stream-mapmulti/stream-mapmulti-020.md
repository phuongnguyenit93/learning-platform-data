# Tương tác với `limit()` và `findFirst()` khi mapper phát nhiều phần tử

`Stream.mapMulti()` cho phép một phần tử đầu vào tạo ra không, một hoặc nhiều phần tử đầu ra thông qua `Consumer`. Khi kết hợp với `limit()` hoặc `findFirst()`, cần phân biệt số phần tử mà pipeline giữ lại với lượng công việc mapper đã thực hiện.

`limit()` và `findFirst()` có thể yêu cầu pipeline dừng việc lấy thêm phần tử từ nguồn khi đã đủ kết quả. Tuy nhiên, callback của `mapMulti()` không nhận tín hiệu hủy hay số lượng phần tử downstream còn cần. Nếu mapper đang chạy một vòng lặp để phát nhiều phần tử cho cùng một input, vòng lặp đó vẫn có thể chạy đến hết dù downstream đã nhận đủ kết quả. Vì vậy, hãy giữ lượng công việc trong mỗi lần gọi mapper có giới hạn rõ ràng.

## 1. `mapMulti()` phát không hoặc nhiều phần tử cho mỗi input

Chữ ký generic của phương thức:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Với mỗi phần tử kiểu `T` của stream nguồn, mapper được gọi một lần và nhận:

- Phần tử đầu vào hiện tại.
- Một `Consumer<R>` để phát các phần tử đầu ra.

Mapper có thể gọi `accept()` không lần nào, một lần hoặc nhiều lần. Các giá trị được phát sẽ trở thành phần tử của stream kiểu `R`.

Ví dụ tách mỗi chuỗi thành các token:

```java
import java.util.List;
import java.util.stream.Stream;

class TokenExample {
    static List<String> tokens() {
        return Stream.of("red,blue", "green")
            .<String>mapMulti((text, output) -> {
                for (String token : text.split(",")) {
                    if (!token.isBlank()) {
                        output.accept(token.trim());
                    }
                }
            })
            .toList();
    }
}
```

Kết quả là `[red, blue, green]`. Input thứ nhất phát hai phần tử, input thứ hai phát một phần tử. `mapMulti()` phù hợp khi số phần tử phát ra từ mỗi input nhỏ và có giới hạn tự nhiên.

## 2. Vị trí của `limit()` quyết định giới hạn input hay output

`limit(n)` chỉ giới hạn số phần tử đi qua vị trí mà nó xuất hiện trong pipeline.

**Đặt `limit()` sau `mapMulti()`:** giới hạn số phần tử đầu ra của mapper.

```java
import java.util.List;
import java.util.stream.Stream;

class LimitAfterMapMulti {
    static List<Integer> firstFourOutputs() {
        return Stream.of(1, 2, 3)
            .<Integer>mapMulti((number, output) -> {
                output.accept(number * 10 + 1);
                output.accept(number * 10 + 2);
            })
            .limit(4)
            .toList();
    }
}
```

Kết quả là `[11, 12, 21, 22]`: pipeline giữ tối đa bốn phần tử sau khi mapper phát ra.

**Đặt `limit()` trước `mapMulti()`:** giới hạn số input được đưa vào mapper. Mỗi input vẫn có thể phát nhiều output.

```java
import java.util.List;
import java.util.stream.Stream;

class LimitBeforeMapMulti {
    static List<Integer> outputsFromFirstTwoInputs() {
        return Stream.of(1, 2, 3, 4)
            .limit(2)
            .<Integer>mapMulti((number, output) -> {
                output.accept(number * 10 + 1);
                output.accept(number * 10 + 2);
            })
            .toList();
    }
}
```

Kết quả là `[11, 12, 21, 22]`. Chỉ hai input đầu được xử lý, nhưng chúng phát tổng cộng bốn output. Do đó, `limit(2)` trước `mapMulti()` không có nghĩa danh sách kết quả tối đa hai phần tử.

| Pipeline | `limit(n)` giới hạn | Kết quả có thể có |
| --- | --- | --- |
| `source.mapMulti(mapper).limit(n)` | Số output sau mapper | Tối đa `n` phần tử đầu ra |
| `source.limit(n).mapMulti(mapper)` | Số input đi vào mapper | Có thể nhiều hơn `n` output |

## 3. `limit()` dừng nhận output nhưng không ngắt callback đang chạy

`limit()` là short-circuiting intermediate operation. Khi đã nhận đủ số phần tử yêu cầu, pipeline có thể ngừng yêu cầu input tiếp theo. Nhưng callback `mapMulti()` hiện tại vẫn có thể tiếp tục gọi `Consumer.accept()` cho đến khi mapper trả về.

Ví dụ sau dùng bộ đếm để quan sát số lần mapper cố phát output:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

class LimitWorkExample {
    public static void main(String[] args) {
        AtomicInteger emissionAttempts = new AtomicInteger();

        List<Integer> result = Stream.of(1, 2, 3)
            .<Integer>mapMulti((number, output) -> {
                for (int offset = 1; offset <= 2; offset++) {
                    emissionAttempts.incrementAndGet();
                    output.accept(number * 10 + offset);
                }
            })
            .limit(3)
            .toList();

        System.out.println(result); // [11, 12, 21]
        System.out.println(emissionAttempts.get()); // 4
    }
}
```

Giải thích:

1. Với input `1`, mapper gọi `accept()` hai lần: phát `11` và `12`.
2. Với input `2`, mapper gọi `accept()` thêm hai lần: phát `21` và thử phát `22`.
3. `limit(3)` chỉ chuyển ba output đầu xuống terminal operation; `22` không được đưa vào danh sách.
4. Dù downstream đã đủ ba phần tử sau `21`, callback của input `2` vẫn chạy hết vòng lặp và thực hiện lần gọi `accept()` thứ tư.
5. Sau khi callback trả về, pipeline không cần yêu cầu input `3` nữa.

Bộ đếm trong ví dụ chỉ dùng để quan sát hành vi. Không nên dựa vào side effect như vậy trong mapper nghiệp vụ; mapper nên không can thiệp trạng thái dùng chung và cho kết quả xác định từ input.

Điểm cần nhớ: `limit(3)` giới hạn kích thước danh sách đầu ra, nhưng không nhất thiết giới hạn số lần mapper gọi `accept()` hoặc lượng công việc trong callback cuối cùng.

## 4. `findFirst()` lấy output đầu tiên, không cắt ngang mapper

`findFirst()` là short-circuiting terminal operation và trả về `Optional<T>`. Trên stream có encounter order, nó tìm phần tử đầu tiên theo thứ tự đó. Khi phần tử đầu tiên được phát xuống downstream, pipeline có thể dừng yêu cầu input tiếp theo.

Tuy vậy, nếu mapper của input hiện tại đang phát nhiều output trong một vòng lặp, callback đó vẫn có thể hoàn tất trước khi quyền điều khiển quay lại pipeline:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

class FindFirstWorkExample {
    public static void main(String[] args) {
        AtomicInteger mapperCalls = new AtomicInteger();
        AtomicInteger emissionAttempts = new AtomicInteger();

        Optional<Integer> first = Stream.of(1, 2, 3)
            .<Integer>mapMulti((number, output) -> {
                mapperCalls.incrementAndGet();

                for (int offset = 1; offset <= 3; offset++) {
                    emissionAttempts.incrementAndGet();
                    output.accept(number * 10 + offset);
                }
            })
            .findFirst();

        System.out.println(first); // Optional[11]
        System.out.println(mapperCalls.get()); // 1
        System.out.println(emissionAttempts.get()); // 3
    }
}
```

`findFirst()` chỉ cần `11`, nên không yêu cầu mapper xử lý input `2` và `3`. Nhưng callback cho input `1` đã chạy đủ ba lần gọi `accept()` trước khi trả về. Hai output `12` và `13` không được dùng làm kết quả.

Nếu input đầu tiên phát ra zero phần tử, `findFirst()` tiếp tục yêu cầu input kế tiếp cho đến khi tìm được output đầu tiên hoặc nguồn kết thúc.

## 5. Tránh mapper phát vô hạn trong một lần gọi

Không dùng `limit()` hoặc `findFirst()` để hy vọng ngắt một vòng lặp vô hạn bên trong mapper:

```java
import java.util.stream.Stream;

class UnboundedMapMultiExample {
    static void run() {
        Stream.of(1)
            .<Integer>mapMulti((number, output) -> {
                int value = 0;
                while (true) {
                    output.accept(value++);
                }
            })
            .findFirst(); // Không thể kết thúc vì callback mapMulti không trả về.
    }
}
```

`Consumer.accept()` không trả về trạng thái cho biết downstream còn cần output hay không. Callback cũng không nhận một cancellation token. Vì vậy, mapper không có cách trực tiếp biết `findFirst()` hoặc `limit()` đã đủ kết quả.

Đây là lý do mỗi lần gọi mapper cần có công việc hữu hạn. Nếu nguồn dữ liệu con có thể vô hạn hoặc rất lớn, hãy thiết kế lại cách duyệt để có thể giới hạn ngay tại nơi sinh dữ liệu, phân trang hoặc xử lý từng phần.

## 6. Giới hạn ngay trong mapper khi có quy tắc nghiệp vụ rõ ràng

Nếu nghiệp vụ quy định mỗi input chỉ được phát tối đa một số lượng phần tử, hãy thể hiện giới hạn đó trong mapper. Ví dụ mỗi đơn hàng chỉ cần tối đa hai dòng đầu tiên đủ điều kiện:

```java
import java.util.List;

record Order(List<String> lines) {}

class OrderLineExample {
    static List<String> firstTwoLinesPerOrder(List<Order> orders) {
        return orders.stream()
            .<String>mapMulti((order, output) -> {
                int emitted = 0;

                for (String line : order.lines()) {
                    if (!line.isBlank()) {
                        output.accept(line);
                        emitted++;

                        if (emitted == 2) {
                            break;
                        }
                    }
                }
            })
            .toList();
    }
}
```

Ở đây vòng lặp có giới hạn tối đa hai output cho mỗi đơn hàng. Đây là giới hạn theo nghiệp vụ, độc lập với downstream `limit()`.

Nếu yêu cầu là lấy tối đa hai dòng trên toàn bộ danh sách đơn hàng, không phải hai dòng mỗi đơn, hãy đặt giới hạn ở pipeline sau khi đã làm phẳng dữ liệu hoặc dùng một chiến lược phân trang phù hợp. Không sao chép một giới hạn toàn cục vào từng mapper, vì điều đó có thể tạo ra số output lớn hơn mong muốn.

## 7. Kết hợp `mapMulti()`, `limit()` và `findFirst()` trong parallel stream

Với ordered parallel stream, các operation vẫn phải tôn trọng encounter order khi hợp đồng yêu cầu. `limit(n)` phải chọn prefix đầu tiên theo encounter order; `findFirst()` phải tìm phần tử đầu tiên theo encounter order. Việc phối hợp thứ tự có thể làm giảm lợi ích song song so với trường hợp không cần thứ tự.

```java
import java.util.List;
import java.util.Optional;

class ParallelExpansion {
    static List<Integer> firstFive(List<Integer> source) {
        return source.parallelStream()
            .<Integer>mapMulti((number, output) -> {
                output.accept(number * 10 + 1);
                output.accept(number * 10 + 2);
            })
            .limit(5)
            .toList();
    }

    static Optional<Integer> firstOutput(List<Integer> source) {
        return source.parallelStream()
            .<Integer>mapMulti((number, output) -> {
                output.accept(number * 10 + 1);
                output.accept(number * 10 + 2);
            })
            .findFirst();
    }
}
```

Với nguồn có thứ tự, danh sách từ `firstFive()` giữ năm output đầu theo thứ tự gặp; `firstOutput()` trả output đầu tiên theo thứ tự gặp. Không suy ra thứ tự thực thi mapper từ thứ tự danh sách: các callback có thể được thực hiện đồng thời và trên các thread khác nhau.

Không dùng side effect hoặc biến đếm không đồng bộ trong mapper của parallel stream. Nếu không cần encounter order và nghiệp vụ chấp nhận bất kỳ phần tử nào, có thể cân nhắc `unordered()` hoặc `findAny()`, nhưng hai lựa chọn đó thay đổi hợp đồng kết quả và cần được quyết định theo nghiệp vụ.

## 8. Chọn `mapMulti()` hay một cách biến đổi khác

`mapMulti()` phù hợp khi mapper có thể phát một số lượng nhỏ, hữu hạn phần tử bằng logic imperative. Nếu mapper thường phát ra rất nhiều phần tử, cần duyệt nguồn con lớn hoặc cần giới hạn việc đọc nguồn con theo nhu cầu downstream, hãy cân nhắc cấu trúc pipeline khác.

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Mỗi input phát 0–vài output có giới hạn | Dùng `mapMulti()`. |
| Mỗi input chuyển thành đúng một giá trị | Dùng `map()`. |
| Cần giới hạn tổng output | Đặt `limit(n)` sau `mapMulti()`, đồng thời giữ callback hữu hạn. |
| Chỉ cần output đầu tiên | Dùng `findFirst()`; không để callback đầu tiên làm việc vô hạn. |
| Cần giới hạn số input được xử lý | Đặt `limit(n)` trước `mapMulti()`. |
| Nguồn con rất lớn hoặc cần duyệt theo nhu cầu | Thiết kế pipeline có thể duyệt từng phần, phân trang hoặc dùng stream con phù hợp. |

`mapMulti()` không thay thế mọi trường hợp của `flatMap()`. Khi phép biến đổi tự nhiên tạo ra một stream con, `flatMap()` thường diễn đạt đúng mô hình hơn. Khi phép biến đổi phát vài giá trị trực tiếp bằng vòng lặp ngắn, `mapMulti()` có thể gọn và tránh tạo stream con cho từng input. Chọn theo mô hình dữ liệu và đo hiệu năng với workload thực tế.

## 9. Các lưu ý khi viết mapper

- Mapper nên stateless và non-interfering; không sửa nguồn stream trong lúc xử lý.
- Mỗi callback nên kết thúc trong thời gian hữu hạn và có giới hạn số output rõ ràng.
- Không lưu `Consumer` nhận được vào field hoặc dùng sau khi callback kết thúc; consumer chỉ dành cho lần gọi mapper hiện tại.
- Không giả định downstream `limit()` sẽ ngắt vòng lặp đang chạy trong mapper.
- `findFirst()` trả `Optional<T>`; nếu phần tử đầu tiên được phát là `null`, terminal operation ném `NullPointerException`. Nếu null không hợp lệ, lọc hoặc xác thực trước `findFirst()`.
- Trên parallel stream, không dựa vào thứ tự callback hoặc side effect; chỉ dựa vào encounter order được API bảo đảm cho kết quả.

## 10. Những điểm cần nhớ

- `mapMulti()` có thể phát zero, one hoặc many output cho mỗi input.
- `limit()` sau `mapMulti()` giới hạn output; `limit()` trước `mapMulti()` giới hạn input.
- `limit()` và `findFirst()` có thể ngừng yêu cầu input tiếp theo sau khi đủ kết quả.
- Callback hiện tại của `mapMulti()` vẫn có thể chạy hết vòng lặp vì `Consumer` không cung cấp tín hiệu cancellation.
- Không phát vô hạn hoặc thực hiện công việc không giới hạn trong một callback.
- Dùng giới hạn bên trong mapper khi đó là quy tắc nghiệp vụ cụ thể; dùng phân trang hoặc pipeline khác khi cần kiểm soát việc duyệt nguồn con.
- Với ordered parallel stream, kết quả vẫn tuân theo encounter order, dù callback có thể chạy đồng thời.

Hãy xem `limit()` và `findFirst()` là cơ chế giới hạn những gì pipeline cần nhận, không phải cơ chế ngắt tùy ý code đang chạy bên trong mapper. Khi `mapMulti()` phát nhiều phần tử, hãy bảo đảm mỗi lần gọi mapper có khối lượng công việc hữu hạn và có thể dự đoán.

## Tài liệu tham khảo

- [Stream.mapMulti() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer))
- [Stream.limit() và Stream.findFirst() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [Stream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [java.util.stream package – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)

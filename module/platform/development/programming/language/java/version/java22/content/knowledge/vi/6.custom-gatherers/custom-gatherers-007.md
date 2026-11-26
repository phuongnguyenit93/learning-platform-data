# Ghép nhiều gatherer bằng `andThen` và phân định trách nhiệm từng bước

`Gatherer.andThen(...)` cho phép nối nhiều gatherer thành một phép biến đổi trung gian duy nhất. Kết quả của gatherer đứng trước trở thành đầu vào của gatherer đứng sau. Nhờ đó, ta có thể chia một quy trình xử lý dữ liệu thành các bước nhỏ, mỗi bước đảm nhiệm một việc như chuẩn hóa, lọc, phân tích, kiểm tra hoặc định dạng.

Stream Gatherers xuất hiện dưới dạng preview trong Java 22 theo JEP 461, tiếp tục ở vòng preview thứ hai trong Java 23 theo JEP 473, và trở thành tính năng chính thức từ Java 24 theo JEP 485. `andThen` vẫn có trong Java SE 27. Vì vậy, khi áp dụng vào dự án hiện đại, hãy dùng API `java.util.stream` đã được chuẩn hóa từ JDK 24 trở lên; phần nói về Java 22 trong bài giải thích mốc lịch sử và cách chạy mã ở phiên bản preview.

Sau bài học, bạn có thể:

- Hiểu cách `andThen` kết nối kiểu đầu ra của gatherer trước với kiểu đầu vào của gatherer sau.
- Chia một pipeline tùy biến thành các bước nhỏ có trách nhiệm rõ ràng.
- Phân biệt composition bằng `andThen` với việc gọi liên tiếp `Stream.gather(...)`.
- Hiểu cách state, finisher, short-circuit và combiner ảnh hưởng đến pipeline đã ghép.
- Chọn cách tổ chức pipeline dễ kiểm thử, bảo trì và phù hợp với xử lý tuần tự hoặc song song.

## 1. `andThen` kết nối hai gatherer như thế nào?

Một gatherer có ba tham số kiểu:

```java
Gatherer<T, A, R>
```

Trong đó:

- `T` là kiểu phần tử đầu vào.
- `A` là kiểu state trung gian mà gatherer dùng để theo dõi dữ liệu trong quá trình xử lý.
- `R` là kiểu phần tử đầu ra được đẩy tới downstream.

Phương thức `andThen` có dạng:

```java
default <RR> Gatherer<T, ?, RR> andThen(
        Gatherer<? super R, ?, ? extends RR> that)
```

Gọi `a.andThen(b)` có nghĩa là đầu vào đi vào `a` trước; mỗi phần tử mà `a` phát ra sẽ được chuyển tới `b`; kết quả cuối cùng là đầu ra của `b`.

```text
Input stream
    |
    v
Gatherer A: T -> R
    |
    | output R
    v
Gatherer B: R -> RR
    |
    | output RR
    v
Downstream stream
```

Kiểu đầu ra `R` của gatherer bên trái phải tương thích với kiểu đầu vào của gatherer bên phải. Kiểu trả về `Gatherer<T, ?, RR>` giữ kiểu đầu vào ban đầu `T`, kiểu đầu ra cuối `RR`, còn dấu `?` che giấu state nội bộ của gatherer ghép. State của hai gatherer vẫn thuộc trách nhiệm riêng của từng bước; `andThen` không yêu cầu chúng dùng chung một đối tượng state.

Thứ tự có ý nghĩa. `normalize.andThen(parse)` là chuẩn hóa chuỗi rồi phân tích thành đối tượng. Đảo thành `parse.andThen(normalize)` sẽ không tương thích kiểu nếu `parse` đã chuyển chuỗi thành một đối tượng khác.

## 2. Vì sao nên tách trách nhiệm thành các gatherer nhỏ?

Một gatherer lớn có thể vừa chuẩn hóa dữ liệu, vừa kiểm tra hợp lệ, vừa chuyển kiểu, vừa gom nhóm. Khi một kết quả sai, khó xác định bước nào gây ra lỗi. Nếu tách thành các gatherer nhỏ, mỗi bước có một hợp đồng dễ diễn đạt:

| Bước | Trách nhiệm | Kiểu dữ liệu minh họa |
|---|---|---|
| Chuẩn hóa | Loại khoảng trắng thừa ở đầu và cuối | `String -> String` |
| Lọc | Loại dòng trống | `String -> String` |
| Phân tích | Chuyển dòng thành đối tượng miền nghiệp vụ | `String -> Product` |
| Kiểm tra | Chỉ giữ sản phẩm có giá lớn hơn 0 | `Product -> Product` |
| Trình bày | Tạo nội dung hiển thị | `Product -> String` |

Cách tách này giúp bạn có thể kiểm tra từng bước riêng, tái sử dụng gatherer ở pipeline khác và thay đổi một bước mà không phải viết lại toàn bộ quy trình. `andThen` ghép các bước lại để nơi sử dụng nhìn thấy một phép biến đổi có tên và có ý nghĩa nghiệp vụ.

Không phải mọi phép toán đơn giản đều cần một gatherer riêng. Với phép biến đổi một-một thông thường, `map` có sẵn thường rõ ràng hơn. Hãy tạo gatherer tùy biến khi cần xử lý theo nhóm, giữ state, phát ra không hoặc nhiều phần tử, dừng sớm, hoặc khi muốn đóng gói một quy trình trung gian có thể tái sử dụng.

## 3. Tạo gatherer nhỏ cho `map` và `filter`

Ví dụ sau tạo hai factory method dùng lại được. Cả hai gatherer đều không cần state riêng:

```java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Gatherer;

static <T, R> Gatherer<T, ?, R> map(
        Function<? super T, ? extends R> mapper) {
    return Gatherer.of((unused, element, downstream) ->
            downstream.push(mapper.apply(element)));
}

static <T> Gatherer<T, ?, T> filter(
        Predicate<? super T> predicate) {
    return Gatherer.of((unused, element, downstream) ->
            !predicate.test(element) || downstream.push(element));
}
```

Trong `map`, mỗi phần tử đầu vào được chuyển qua `mapper` và đẩy xuống bước tiếp theo. Giá trị boolean từ `downstream.push(...)` được trả về trực tiếp để gatherer biết downstream còn muốn nhận dữ liệu hay không.

Trong `filter`, nếu phần tử không thỏa predicate thì integrator trả `true` để tiếp tục đọc phần tử kế tiếp. Nếu phần tử thỏa điều kiện, nó được đẩy xuống downstream và kết quả boolean từ `push` được truyền lại. Cách viết này bảo toàn tín hiệu short-circuit.

`Gatherer.of(Integrator)` tạo gatherer không state và có thể chạy song song. Điều đó không có nghĩa mọi mapper hoặc predicate đều tự động an toàn khi chạy song song: hàm được truyền vào vẫn nên không có tác dụng phụ gây tranh chấp, không can thiệp nguồn dữ liệu và không phụ thuộc thứ tự gọi.

## 4. Ví dụ thực tế: xử lý dòng dữ liệu đơn hàng

Giả sử đầu vào là các dòng có dạng `SKU:PRICE`. Pipeline cần chuẩn hóa khoảng trắng, bỏ dòng trống, phân tích dữ liệu thành `Product`, loại giá không dương và tạo chuỗi hiển thị.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;
import java.util.function.Function;
import java.util.function.Predicate;

public class OrderImport {
    record Product(String sku, BigDecimal price) {}

    static <T, R> Gatherer<T, ?, R> map(
            Function<? super T, ? extends R> mapper) {
        return Gatherer.of((unused, element, downstream) ->
                downstream.push(mapper.apply(element)));
    }

    static <T> Gatherer<T, ?, T> filter(
            Predicate<? super T> predicate) {
        return Gatherer.of((unused, element, downstream) ->
                !predicate.test(element) || downstream.push(element));
    }

    static Product parseProduct(String line) {
        int separator = line.indexOf(':');
        if (separator <= 0 || separator == line.length() - 1) {
            throw new IllegalArgumentException(
                    "Expected SKU:PRICE but got: " + line);
        }

        String sku = line.substring(0, separator).strip();
        String rawPrice = line.substring(separator + 1).strip();
        if (sku.isEmpty() || rawPrice.isEmpty()) {
            throw new IllegalArgumentException(
                    "SKU and price must not be blank: " + line);
        }

        try {
            return new Product(sku, new BigDecimal(rawPrice));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Invalid price in row: " + line, ex);
        }
    }

    public static void main(String[] args) {
        Gatherer<String, ?, String> normalize = map(String::strip);
        Gatherer<String, ?, String> skipBlank = filter(line -> !line.isEmpty());
        Gatherer<String, ?, Product> parse = map(OrderImport::parseProduct);
        Gatherer<Product, ?, Product> positivePrice =
                filter(product -> product.price().signum() > 0);
        Gatherer<Product, ?, String> format = map(product ->
                product.sku() + " -> " + product.price().toPlainString());

        Gatherer<String, ?, String> importPipeline = normalize
                .andThen(skipBlank)
                .andThen(parse)
                .andThen(positivePrice)
                .andThen(format);

        List<String> summaries = Stream.of(
                        " SKU-101 : 120.00 ",
                        " ",
                        "SKU-102:0.00",
                        "SKU-103:80.50")
                .gather(importPipeline)
                .toList();

        System.out.println(summaries);
    }
}
```

Kết quả:

```text
[SKU-101 -> 120.00, SKU-103 -> 80.50]
```

Mỗi gatherer có một trách nhiệm: `normalize` chỉ chuẩn hóa, `skipBlank` chỉ lọc, `parse` chỉ chuyển chuỗi thành `Product`, `positivePrice` chỉ kiểm tra quy tắc giá, và `format` chỉ định dạng kết quả. Nếu định dạng đầu ra thay đổi, chỉ cần thay `format`; nếu quy tắc giá thay đổi, chỉ cần thay `positivePrice`.

Trong ví dụ này, dòng sai định dạng làm `parseProduct` ném `IllegalArgumentException` và kết thúc pipeline. Đây là chính sách *fail fast*. Nếu yêu cầu nghiệp vụ là tiếp tục nhập các dòng hợp lệ, hãy biểu diễn kết quả phân tích bằng một kiểu như `ParseResult<Product>` chứa cả dữ liệu thành công hoặc thông tin lỗi, rồi quyết định rõ bước nào thu thập lỗi, ghi log hoặc loại bản ghi. Không nên bắt `RuntimeException` chung rồi âm thầm bỏ dòng, vì như vậy lỗi lập trình cũng có thể bị che giấu.

## 5. `andThen` tương đương với nhiều lần gọi `gather`

Giả sử `source` có kiểu `Stream<T>`, `a` có kiểu `Gatherer<T, ?, R>` và `b` có kiểu `Gatherer<R, ?, RR>`. Hai cách viết dưới đây tương đương về ngữ nghĩa:

```java
Stream<RR> first = source
        .gather(a)
        .gather(b);

Stream<RR> second = source
        .gather(a.andThen(b));
```

Khác biệt nằm ở cách tổ chức API:

- Gọi `.gather(a).gather(b)` phù hợp khi pipeline tại chỗ cần thể hiện từng bước rõ ràng.
- Dùng `a.andThen(b)` phù hợp khi muốn đóng gói chuỗi bước thành một gatherer có tên, truyền nó qua nhiều tầng hoặc tái sử dụng ở nhiều pipeline.

Có thể nối nhiều bước theo thứ tự:

```java
Gatherer<T, ?, D> pipeline = first
        .andThen(second)
        .andThen(third)
        .andThen(fourth);
```

Mỗi lần nối, kiểu đầu ra của gatherer hiện tại phải tương thích với kiểu đầu vào của bước tiếp theo. Nếu hai kiểu không khớp, hãy thêm một bước chuyển đổi tường minh thay vì ép kiểu không an toàn.

Không nên xem `andThen` là một cam kết tăng hiệu năng. Nó cung cấp composition ở mức API. Tài liệu `Stream` cho phép triển khai nhận diện các lần gọi `gather` liên tiếp và hợp nhất chúng thành một thao tác, nhưng không bắt buộc phải làm vậy. Hãy đo hiệu năng trên dữ liệu và JDK thực tế nếu hiệu năng là lý do để thay đổi cấu trúc pipeline.

## 6. Composition với gatherer có state và finisher

Không phải gatherer nào cũng xử lý từng phần tử độc lập. Một gatherer có thể giữ state, đợi nhiều đầu vào rồi mới phát kết quả, hoặc phát thêm kết quả khi upstream kết thúc.

Ví dụ, `Gatherers.scan` tạo ra dãy tổng tích lũy. `Gatherers.fold` gom các giá trị nhận được thành một kết quả cuối:

```java
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> runningTotals =
        Gatherers.scan(() -> 100, Integer::sum);

Gatherer<Integer, ?, String> joinTotals =
        Gatherers.fold(
                () -> "",
                (result, element) -> result.isEmpty()
                        ? element.toString()
                        : result + ";" + element);

String summary = Stream.of(1, 2, 3, 4, 5, 6, 7, 8, 9)
        .gather(runningTotals.andThen(joinTotals))
        .findFirst()
        .orElse("");

System.out.println(summary);
```

Kết quả:

```text
101;103;106;110;115;121;128;136;145
```

Ở đây, `runningTotals` sở hữu state của phép cộng tích lũy và phát từng tổng trung gian. `joinTotals` sở hữu state chuỗi và chỉ phát chuỗi hoàn chỉnh trong finisher khi upstream kết thúc. `andThen` chuyển các giá trị mà bước scan phát ra sang bước fold. Ví dụ này minh họa rằng composition kết nối cả luồng dữ liệu giữa các bước, kể cả dữ liệu do finisher phát ra.

Mỗi gatherer vẫn quản lý vòng đời state của chính nó. Khi thiết kế một bước có finisher, hãy xác định rõ nó phát thêm phần tử nào, phát khi nào và bước tiếp theo sẽ diễn giải chúng ra sao. Đặc biệt, gatherer như `fold` có thể chỉ phát một kết quả cuối; đừng giả định mọi gatherer đều phát một phần tử cho mỗi phần tử đầu vào.

## 7. Short-circuit và tín hiệu từ downstream

`Gatherer.Integrator` trả về `boolean`:

- `true`: gatherer có thể tiếp tục nhận phần tử đầu vào.
- `false`: gatherer báo rằng không cần nhận thêm đầu vào.

`Gatherer.Downstream.push(...)` cũng trả về `boolean` để cho biết downstream còn sẵn sàng nhận thêm phần tử hay không. Vì vậy, khi một gatherer chỉ chuyển tiếp hoặc biến đổi phần tử, hãy trả lại kết quả `push` như trong factory `map` ở trên.

Với filter, khi phần tử không phù hợp, integrator trả `true` vì nó chỉ bỏ phần tử hiện tại. Khi phần tử phù hợp, nó trả kết quả `push` để tôn trọng yêu cầu dừng từ downstream.

Trong chuỗi `a.andThen(b)`, tín hiệu dừng từ downstream có thể truyền ngược qua các bước trung gian. Một gatherer không được bỏ qua tín hiệu này rồi tiếp tục tạo đầu ra không cần thiết. Nếu một bước tự short-circuit, các phần tử đầu vào tiếp theo sẽ không còn được chuyển qua gatherer đó.

Các terminal operation như `findFirst()` cũng có thể không cần toàn bộ dữ liệu. Khi viết gatherer, hãy kiểm tra `downstream.isRejecting()` nếu thuật toán cần biết downstream đã từ chối thêm đầu ra, đặc biệt trong finisher hoặc khi một phần tử có thể tạo ra nhiều kết quả.

## 8. Ghép gatherer và xử lý song song

Một gatherer chỉ có thể được xử lý song song nếu có combiner hợp lệ để kết hợp state của các phân vùng. Nếu dùng `Gatherer.defaultCombiner()` (mặc định), gatherer đó chỉ được đánh giá tuần tự; gọi `.parallel()` trên stream không tự tạo ra combiner.

Khi ghép nhiều gatherer:

- Gatherer không state tạo bằng `Gatherer.of(Integrator)` có thể song song nếu logic mapper/predicate an toàn cho việc đó.
- Gatherer có state cần combiner kết hợp hai state sao cho kết quả tương đương với xử lý tuần tự theo encounter order mà hợp đồng yêu cầu.
- Một gatherer phụ thuộc thứ tự, chẳng hạn giữ cửa sổ trượt hoặc phát kết quả dựa trên phần tử trước đó, có thể cần xử lý tuần tự nếu không có cách kết hợp state đúng.
- Hãy kiểm tra khả năng song song của từng bước trước khi dùng `parallel()`. Composition không tự làm một thuật toán phụ thuộc thứ tự trở thành song song an toàn.

Không dùng chung một mutable state bên ngoài giữa các gatherer hoặc giữa các lần thực thi pipeline. State cần được tạo từ initializer cho mỗi lần đánh giá/phân vùng theo hợp đồng; không lưu giữ tham chiếu tới state hoặc `Downstream` ngoài thời gian gọi mà API cho phép. Nếu các bước có side effect như ghi file, cập nhật database hoặc tăng biến đếm dùng chung, cần thiết kế đồng bộ và chính sách lỗi riêng thay vì giả định Stream sẽ tự bảo vệ chúng.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Nối hai gatherer không tương thích kiểu | Không biên dịch hoặc phải ép kiểu khó kiểm soát | Kiểm tra `R` của bước trước và `T` của bước sau; thêm mapper rõ ràng nếu cần. |
| Một gatherer làm quá nhiều việc | Khó kiểm thử và khó xác định bước gây sai dữ liệu | Tách theo trách nhiệm, giữ mỗi bước có hợp đồng đơn giản. |
| Dùng `andThen` chỉ để thay `map` hoặc `filter` đơn giản | Tăng độ phức tạp mà không tăng khả năng diễn đạt | Ưu tiên intermediate operation có sẵn khi chúng đáp ứng yêu cầu. |
| Bỏ qua kết quả `downstream.push` | Tiếp tục xử lý khi downstream đã yêu cầu dừng | Trả lại boolean từ `push` hoặc xử lý nó rõ ràng. |
| Giả định finisher không phát dữ liệu | Bỏ mất phần kết quả chỉ được tạo ở cuối stream | Xác định vai trò finisher ở mỗi bước và bước sau nhận dữ liệu đó như thế nào. |
| Gọi `.parallel()` dù gatherer không có combiner đúng | Không đạt song song hoặc tạo kết quả sai nếu tự chia state không đúng | Cung cấp combiner hợp lệ hoặc giữ pipeline tuần tự. |
| Dùng mapper/predicate có side effect | Kết quả phụ thuộc số lần gọi hoặc thứ tự thực thi | Ưu tiên hàm thuần, không can thiệp nguồn và không phụ thuộc thứ tự. |
| Nuốt lỗi phân tích dữ liệu | Bản ghi sai bị mất mà không có dấu vết | Chọn chính sách fail-fast hoặc mô hình kết quả chứa lỗi một cách tường minh. |

## 10. Phiên bản Java và cách biên dịch

`Gatherer`, `Gatherers` và `Stream.gather` đã có trong Java 22 nhưng còn là preview. Chúng trải qua hai vòng preview trước khi ổn định:

| JDK | JEP | Trạng thái |
|---|---|---|
| Java 22 | JEP 461 | Preview lần đầu; phải bật preview khi biên dịch và chạy. |
| Java 23 | JEP 473 | Preview lần thứ hai. |
| Java 24 trở lên | JEP 485 | API chính thức; không cần `--enable-preview`. |

Nếu cần chạy ví dụ bằng đúng JDK 22, biên dịch và chạy với preview flag:

```bash
javac --enable-preview --release 22 OrderImport.java
java --enable-preview OrderImport
```

Với JDK 24 trở lên, mã dùng API đã chuẩn hóa:

```bash
javac OrderImport.java
java OrderImport
```

Trong dự án mới, ưu tiên JDK có Gatherers đã final. Không giữ cấu hình preview chỉ vì mã từng được viết trong Java 22; preview flag chỉ cần khi chủ động biên dịch/chạy một bản preview của đúng release tương ứng.

## 11. Kết luận

`andThen` kết nối đầu ra của một gatherer với đầu vào của gatherer tiếp theo và trả về một gatherer tổng hợp. Nó giúp chia pipeline thành những bước có trách nhiệm rõ ràng, dễ kiểm tra và tái sử dụng. Mỗi bước vẫn giữ state, integrator, combiner và finisher riêng theo hợp đồng của nó.

Khi thiết kế, hãy kiểm tra tính tương thích kiểu giữa các bước, bảo toàn tín hiệu short-circuit, hiểu rõ dữ liệu do finisher phát ra và chỉ dùng song song khi mọi gatherer có combiner đúng. Stream Gatherers đã chính thức từ Java 24, nên `andThen` là API ổn định có thể tiếp tục sử dụng trên JDK hiện đại.

## Tài liệu tham khảo

- [JEP 461: Stream Gatherers (Preview)](https://openjdk.org/jeps/461)
- [JEP 473: Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473)
- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)
- [Java SE 22 API: `Gatherer`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 22 API: `Stream.gather`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 24 Guide: Stream Gatherers and Composing Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
- [Java SE 27 API: `Gatherer`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html)

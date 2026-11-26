# Stream.gather và khác biệt giữa Gatherer, Collector cùng các phép map hoặc flatMap

## 1. Stream Gatherers giải quyết vấn đề gì?

Stream API có sẵn nhiều phép biến đổi hữu ích như `map`, `filter`, `flatMap`, `distinct`, `sorted` và `limit`. Tuy nhiên, có những thao tác cần nhớ trạng thái giữa nhiều phần tử, gom một nhóm phần tử thành một kết quả, phát ra kết quả trung gian sau mỗi bước tích lũy, hoặc dừng xử lý khi đã đủ dữ liệu. Ghép các phép Stream cơ bản đôi khi khiến mã nguồn dài, phải tự quản lý trạng thái bên ngoài pipeline hoặc phải kết thúc Stream rồi tạo một pipeline mới.

`Gatherer` bổ sung một loại *intermediate operation* có thể tùy biến. Nó nhận các phần tử từ Stream đầu vào, có thể giữ trạng thái nội bộ, phát ra không, một hoặc nhiều phần tử xuống bước tiếp theo và có thể thực hiện công việc cuối khi upstream kết thúc. `Stream.gather(Gatherer)` nối thao tác này vào pipeline và trả về một Stream mới.

Gatherer phù hợp khi logic biến đổi phụ thuộc vào nhiều phần tử hoặc cần điều khiển quá trình phát kết quả. Với phép biến đổi đơn giản một phần tử thành một phần tử hoặc một phần tử thành một Stream con, `map` và `flatMap` vẫn là lựa chọn dễ đọc hơn.

## 2. Trạng thái của API: dùng bản chính thức từ Java 24 trở lên

Stream Gatherers được giới thiệu dưới dạng preview trong Java 22 qua JEP 461, tiếp tục ở preview thứ hai trong Java 23 qua JEP 473 và trở thành API chính thức trong Java 24 qua JEP 485. Từ Java 24, `Stream.gather`, `Gatherer` và `Gatherers` không còn yêu cầu bật preview.

Bài học này tập trung vào API ổn định hiện nay. Các ví dụ có thể biên dịch với JDK 24 trở lên mà không cần `--enable-preview`. Việc Java 22 từng giới thiệu tính năng này ở dạng preview chỉ là bối cảnh lịch sử; không dùng cú pháp hoặc hướng dẫn preview cũ làm cách triển khai hiện tại.

## 3. Cách gọi `Stream.gather`

`Stream.gather` là một intermediate operation. Nó nhận một `Gatherer` và trả về một Stream chứa các phần tử do Gatherer phát ra:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherExample {
    public static void main(String[] args) {
        List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
                .gather(Gatherers.windowFixed(3))
                .toList();

        System.out.println(batches);
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
```

`windowFixed(3)` gom các phần tử theo từng nhóm có tối đa ba phần tử. Nhóm cuối vẫn được phát ra dù chưa đủ kích thước. Kết quả của `gather` vẫn là Stream, do đó có thể tiếp tục gọi `map`, `filter`, `flatMap`, `toList` hoặc một terminal operation khác.

Pipeline Stream vẫn được đánh giá lazy: thao tác gatherer chỉ chạy khi có terminal operation kích hoạt pipeline. Giống các intermediate operation khác, một Stream không được tiêu thụ nhiều lần.

## 4. Gatherer được cấu thành từ bốn hàm

Một `Gatherer<T, A, R>` có ba tham số kiểu:

- `T`: kiểu phần tử đầu vào.
- `A`: kiểu trạng thái trung gian mà Gatherer quản lý.
- `R`: kiểu phần tử được phát ra downstream.

Gatherer được mô tả bởi bốn hàm phối hợp với nhau:

| Hàm | Vai trò | Câu hỏi cần trả lời |
|---|---|---|
| `initializer()` | Tạo trạng thái ban đầu cho một lần xử lý hoặc một partition. | Cần lưu trạng thái gì? |
| `integrator()` | Nhận từng phần tử đầu vào, cập nhật trạng thái và có thể phát kết quả qua `Downstream`. | Khi nhận phần tử này thì cập nhật gì và phát ra gì? |
| `combiner()` | Kết hợp hai trạng thái trung gian khi Gatherer hỗ trợ xử lý song song. | Có thể ghép hai phần xử lý độc lập thành một trạng thái đúng không? |
| `finisher()` | Chạy khi upstream kết thúc; có thể phát nốt dữ liệu còn đệm. | Còn kết quả nào chỉ có thể tạo ra ở cuối không? |

`initializer`, `combiner` và `finisher` có triển khai mặc định. Nếu dùng `defaultCombiner()`, Gatherer chỉ được đánh giá tuần tự. Muốn Gatherer có thể được xử lý song song, cần cung cấp combiner có ý nghĩa đúng với cách chia partition và ghép trạng thái.

`Gatherer.Downstream` là nơi gửi kết quả sang bước kế tiếp. `downstream.push(value)` trả về `boolean`: `false` báo downstream không muốn nhận thêm kết quả, cho phép integrator dừng sớm bằng cách trả về `false`. Đây là một phần cơ chế short-circuit của Gatherer.

## 5. Tạo một Gatherer có trạng thái

Ví dụ sau loại bỏ các chuỗi trùng nhau liên tiếp. Nếu một giá trị xuất hiện lại sau một giá trị khác, nó vẫn được giữ lại. Để quyết định có phát phần tử hiện tại hay không, Gatherer phải nhớ phần tử trước đó.

```java
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class ConsecutiveDistinctExample {
    static Gatherer<String, ?, String> distinctConsecutive() {
        class State {
            String previous;
            boolean hasPrevious;
        }

        return Gatherer.ofSequential(
                State::new,
                (state, element, downstream) -> {
                    if (state.hasPrevious && Objects.equals(state.previous, element)) {
                        return true;
                    }

                    state.previous = element;
                    state.hasPrevious = true;
                    return downstream.push(element);
                });
    }

    public static void main(String[] args) {
        var result = Stream.of("A", "A", "B", "B", "A", "C", "C")
                .gather(distinctConsecutive())
                .toList();

        System.out.println(result); // [A, B, A, C]
    }
}
```

Ở đây:

1. `State::new` tạo trạng thái riêng cho lần đánh giá Gatherer.
2. Integrator so sánh phần tử hiện tại với phần tử trước đó.
3. Nếu hai giá trị bằng nhau, integrator không phát phần tử và tiếp tục đọc upstream bằng cách trả về `true`.
4. Nếu khác nhau, integrator cập nhật trạng thái và gọi `downstream.push(element)`.

Ví dụ dùng `Gatherer.ofSequential` vì logic chỉ được thiết kế cho một chuỗi phần tử theo thứ tự. Nó không khai báo combiner nên không được chạy song song, kể cả khi Stream đầu vào gọi `parallel()`. Không nên thêm combiner giả chỉ để bật parallel; việc chia dữ liệu thành các partition có thể làm mất thông tin phần tử cuối của partition trước và khiến kết quả sai.

## 6. Các Gatherer dựng sẵn trong `Gatherers`

Java cung cấp lớp tiện ích `Gatherers` với một số thao tác thường gặp. Chúng phù hợp khi hành vi mong muốn đã có sẵn và không cần tự cài đặt Gatherer.

### 6.1. `windowFixed`: gom nhóm có kích thước cố định

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
        .gather(Gatherers.windowFixed(3))
        .toList();

// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Các nhóm không chồng lấn. Nếu Stream rỗng thì không có nhóm nào. Nhóm cuối có thể ngắn hơn `windowSize`. Danh sách từng nhóm là unmodifiable; không sửa trực tiếp các phần tử của window sau khi nhận.

### 6.2. `windowSliding`: gom nhóm có phần tử chồng lấn

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Mỗi window tiếp theo giữ lại các phần tử cũ trừ phần tử lâu đời nhất, sau đó thêm phần tử tiếp theo. Nếu toàn bộ Stream ngắn hơn kích thước window, chỉ có một window chứa tất cả phần tử đầu vào. Chọn kích thước window hợp lý vì việc lưu các window có thể tiêu thụ bộ nhớ đáng kể.

### 6.3. `scan`: phát ra kết quả tích lũy sau mỗi phần tử

`scan` là prefix scan: bắt đầu từ giá trị ban đầu, áp dụng hàm tích lũy với từng phần tử rồi phát ra giá trị mới sau mỗi bước.

```java
List<Integer> runningTotals = Stream.of(2, 3, 4, 5)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(runningTotals); // [2, 5, 9, 14]
```

Khác với `reduce`, `scan` giữ lại toàn bộ các tổng trung gian dưới dạng một Stream. Có thể tiếp tục lọc hoặc biến đổi từng tổng trước khi kết thúc pipeline.

### 6.4. `fold`: gộp toàn bộ đầu vào thành kết quả cuối

`fold` thực hiện một phép gộp có thứ tự và phát ra một kết quả sau khi xử lý đầu vào. Nó hữu ích cho phép tính phụ thuộc thứ tự hoặc không có combiner phù hợp:

```java
var folded = Stream.of("Java", " ", "Gatherers")
        .gather(Gatherers.fold(StringBuilder::new,
                StringBuilder::append))
        .findFirst()
        .map(StringBuilder::toString);

System.out.println(folded.orElse("")); // Java Gatherers
```

`fold` là thao tác có thứ tự, không thay thế `collect` trong mọi tình huống. Khi mục tiêu là tạo một collection hoặc map kết quả, `Collector` thường diễn đạt đúng ý định hơn.

### 6.5. `mapConcurrent`: thực hiện ánh xạ đồng thời có giới hạn

`mapConcurrent(maxConcurrency, mapper)` chạy mapper đồng thời bằng virtual threads với số tác vụ đồng thời tối đa được chỉ định. Kết quả vẫn giữ encounter order của Stream:

```java
List<String> pages = urls.stream()
        .gather(Gatherers.mapConcurrent(8, this::downloadPage))
        .toList();
```

Ví dụ này giả sử `downloadPage` là phương thức thực hiện I/O và trả về nội dung trang. `maxConcurrency` phải lớn hơn 0. Đây là một Gatherer có sẵn cho trường hợp cần giới hạn mức đồng thời; không đồng nghĩa với việc mọi Gatherer tự động chạy song song.

## 7. Phân biệt Gatherer và Collector

Hai API đều có thể quản lý trạng thái, dùng combiner và hỗ trợ xử lý song song, nhưng chúng nằm ở hai vị trí khác nhau trong Stream pipeline.

| Tiêu chí | `Gatherer` | `Collector` |
|---|---|---|
| Vai trò | Intermediate operation | Mô tả chiến lược terminal reduction |
| Phương thức Stream | `stream.gather(gatherer)` | `stream.collect(collector)` |
| Kết quả | Một Stream mới để pipeline tiếp tục xử lý | Một giá trị kết quả cuối như `List`, `Map`, số liệu hoặc đối tượng tổng hợp |
| Hàm xử lý từng phần tử | `integrator()` có thể phát nhiều kết quả qua `Downstream` | `accumulator()` cập nhật result container |
| Trạng thái cuối | `finisher()` có thể phát thêm phần tử vào downstream | `finisher()` chuyển container tích lũy thành kết quả cuối |
| Dừng sớm | Integrator có thể trả về `false` | Collector không phải cơ chế short-circuit trung gian |
| Kết hợp | `combiner()` cho phép chia và ghép trạng thái Gatherer khi có triển khai phù hợp | `combiner()` ghép các result container của reduction |

Ví dụ dùng Collector để gom các đơn hàng thành danh sách:

```java
List<String> names = orders.stream()
        .map(Order::customerName)
        .collect(Collectors.toList());
```

Sau `collect`, pipeline đã kết thúc và biến `names` là kết quả cuối. Ngược lại, `gather` trả về Stream:

```java
List<List<Order>> batches = orders.stream()
        .gather(Gatherers.windowFixed(100))
        .filter(batch -> !batch.isEmpty())
        .toList();
```

Ở đây Gatherer biến một Stream đơn hàng thành Stream các nhóm đơn hàng; `filter` và `toList` vẫn có thể được nối tiếp sau đó.

`Collector` có bốn thành phần `supplier`, `accumulator`, `combiner`, `finisher`. Chúng khá giống `Gatherer` ở việc tạo và kết hợp trạng thái, nhưng accumulator chỉ cập nhật container. Gatherer integrator còn có khả năng phát không, một hoặc nhiều kết quả xuống downstream trong khi pipeline vẫn đang chạy.

## 8. Phân biệt Gatherer với `map`, `flatMap` và `mapMulti`

Các phép `map` và `flatMap` cũng là intermediate operation. Chúng thường đơn giản hơn và nên được ưu tiên nếu không cần trạng thái qua nhiều phần tử.

| Phép toán | Quan hệ đầu vào và đầu ra | Có trạng thái giữa nhiều phần tử? | Trường hợp phù hợp |
|---|---|---|---|
| `map` | Một phần tử đầu vào tạo đúng một phần tử đầu ra | Không | Chuyển đổi một đối tượng sang kiểu hoặc biểu diễn khác |
| `flatMap` | Một phần tử đầu vào tạo một Stream con; các Stream con được làm phẳng | Không cần trạng thái dùng chung giữa các phần tử | Mở rộng một phần tử thành 0..n phần tử |
| `mapMulti` | Một phần tử đầu vào phát 0..n phần tử qua consumer | Không cần trạng thái dùng chung giữa các phần tử | Mở rộng phần tử theo cách imperative mà không cần tạo Stream con |
| `gather` | Một hoặc nhiều phần tử đầu vào có thể tạo 0..n phần tử đầu ra | Có thể có | Gom nhóm, scan, bỏ trùng liên tiếp, buffer, dừng sớm hoặc logic stateful khác |

### 8.1. `map`: một đầu vào, một đầu ra

```java
List<String> upperNames = names.stream()
        .map(String::toUpperCase)
        .toList();
```

Mỗi tên được chuyển thành một chuỗi viết hoa. Không cần nhớ các phần tử trước đó.

### 8.2. `flatMap`: một đầu vào, nhiều phần tử đầu ra

```java
List<String> words = sentences.stream()
        .flatMap(sentence -> Arrays.stream(sentence.split("\\s+")))
        .toList();
```

Mỗi câu tạo một Stream từ các từ; `flatMap` làm phẳng các Stream con thành một Stream duy nhất. Nếu mapper trả về Stream rỗng thì phần tử đầu vào không tạo phần tử đầu ra.

### 8.3. `mapMulti`: phát nhiều phần tử mà không tạo Stream con

```java
List<String> words = sentences.stream()
        .<String>mapMulti((sentence, downstream) -> {
            for (String word : sentence.split("\\s+")) {
                downstream.accept(word);
            }
        })
        .toList();
```

`mapMulti` hữu ích khi muốn phát 0..n kết quả cho mỗi phần tử bằng vòng lặp hoặc điều kiện. Nó tránh phải tạo một Stream con cho mỗi phần tử đầu vào. Nếu logic cần nhớ phần tử của những lần gọi trước, phát phần tử khi kết thúc upstream hoặc có combiner cho trạng thái, hãy cân nhắc Gatherer.

## 9. Chọn công cụ theo mục đích

- **Chuyển đổi từng phần tử độc lập:** dùng `map`.
- **Mở rộng từng phần tử thành một Stream con:** dùng `flatMap`; nếu muốn phát kết quả bằng vòng lặp mà không tạo Stream con, cân nhắc `mapMulti`.
- **Gom các phần tử thành kết quả cuối như List, Set, Map hoặc số liệu:** dùng `collect` với `Collector`.
- **Tạo một Stream trung gian mới dựa trên trạng thái của nhiều phần tử:** dùng `gather` với `Gatherer`.
- **Cần gom cửa sổ, prefix scan hoặc ánh xạ đồng thời có giới hạn:** kiểm tra các factory method của `Gatherers` trước khi tự viết.

Gatherer không làm cho pipeline tự động nhanh hơn. Nếu thao tác có thể diễn đạt rõ bằng `map`, `filter` hoặc `flatMap`, hãy dùng phép toán có sẵn. Khi tự viết Gatherer stateful, cần giữ state riêng cho mỗi lần đánh giá/partition, không chia sẻ state mutable ra ngoài, và chỉ khai báo combiner khi có thể kết hợp kết quả các partition một cách đúng đắn.

## 10. Những điểm cần nhớ khi tự triển khai

1. Không lưu tham chiếu tới đối tượng state hoặc `Gatherer.Downstream` lâu hơn thời gian gọi integrator/finisher tương ứng.
2. Tạo state mới trong `initializer()`; không dùng một biến mutable static để chia sẻ trạng thái giữa các lần chạy Stream.
3. Nếu integrator trả về `false`, upstream được xem như không còn phần tử để chuyển tiếp. Dùng điều này cho short-circuit có chủ đích.
4. `downstream.push` có thể trả về `false`; cần truyền tín hiệu dừng này về integrator thay vì tiếp tục phát dữ liệu.
5. Nếu Gatherer đệm phần tử nhưng chưa phát, `finisher()` phải quyết định cách xử lý phần còn lại khi upstream kết thúc.
6. Nếu không có combiner phù hợp, dùng `Gatherer.ofSequential` và chấp nhận xử lý tuần tự. Đừng dùng `.parallel()` với kỳ vọng biến một Gatherer tuần tự thành song song.
7. Nếu có combiner, bảo đảm cách ghép hai state tương thích với kết quả xử lý tuần tự và với encounter order cần giữ.
8. Không sửa trực tiếp các window list do `windowFixed` hoặc `windowSliding` phát ra; API quy định chúng là unmodifiable.

## 11. Tài liệu tham khảo

- [JEP 461: Stream Gatherers (Java 22 Preview)](https://openjdk.org/jeps/461) — lịch sử giới thiệu tính năng.
- [JEP 473: Stream Gatherers (Second Preview, Java 23)](https://openjdk.org/jeps/473) — vòng preview thứ hai.
- [JEP 485: Stream Gatherers (Java 24)](https://openjdk.org/jeps/485) — phiên bản hoàn thiện và chính thức.
- [Java SE 26 API: Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html) — hợp đồng của `Stream.gather`.
- [Java SE 26 API: Gatherer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html) — bốn hàm của Gatherer, factory methods và quy tắc xử lý song song.
- [Java SE 26 API: Gatherers](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherers.html) — các Gatherer dựng sẵn.
- [Java SE 26 API: Collector](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html) — hợp đồng của terminal reduction.

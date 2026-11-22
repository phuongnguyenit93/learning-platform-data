# Dùng reduce ba tham số để thay đổi kiểu kết quả

Trong chương **Phép rút gọn với reduce** của **Java Stream API**, ta đã quen với các pipeline khai báo: lấy phần tử từ nguồn, biến đổi bằng `map` hoặc lọc bằng `filter`, rồi dùng một terminal operation để tính kết quả. `reduce` là thao tác dùng để gộp nhiều phần tử thành một giá trị theo một phép kết hợp.

Khi kiểu phần tử đầu vào và kiểu kết quả **khác nhau**, overload `reduce` có **ba tham số** đặc biệt hữu ích. Ta có thể chuyển một `Stream<String>` thành tổng độ dài kiểu `Integer`, hoặc chuyển một `Stream<Sale>` thành bản thống kê `InvoiceStats` chứa số dòng hàng, số lượng và tổng tiền. Để kết quả đúng cả khi chạy tuần tự lẫn song song, ba tham số `identity`, `accumulator` và `combiner` phải tuân thủ một hợp đồng chặt chẽ.

Bài này giải thích hợp đồng đó, triển khai ví dụ hoàn chỉnh, nhận diện các lỗi thường gặp và xác định khi nào dùng `reduce` hay `collect`.

## 1. Ba overload của reduce và ý nghĩa của kiểu kết quả

Trong `java.util.stream.Stream<T>`, ba overload của `reduce` có thể đọc như sau:

~~~java
// 1. Không có identity: kết quả vẫn thuộc kiểu T, có thể không tồn tại.
Optional<T> reduce(BinaryOperator<T> accumulator);

// 2. Có identity: kết quả vẫn thuộc kiểu T.
T reduce(T identity, BinaryOperator<T> accumulator);

// 3. Có identity và combiner: kết quả có thể thuộc kiểu U khác T.
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

`T` là **kiểu phần tử đang chảy trong Stream**, còn `U` là **kiểu kết quả tích lũy**. Với overload ba tham số, `T` và `U` có thể khác nhau; nếu bằng nhau vẫn dùng được, nhưng lợi ích chính là hỗ trợ phép tổng hợp thay đổi kiểu.

| Thành phần | Kiểu hàm / giá trị | Trách nhiệm |
| --- | --- | --- |
| `identity` | `U` | Giá trị trung hòa, cũng là kết quả khi nguồn rỗng. |
| `accumulator` | `(U, T) -> U` | Nhận tổng một phần và một phần tử mới của Stream, trả tổng một phần mới. |
| `combiner` | `(U, U) -> U` | Gộp hai tổng một phần thành một tổng theo cùng ý nghĩa nghiệp vụ. |
| Giá trị cuối | `U` | Kết quả của terminal operation sau khi hoàn tất duyệt và kết hợp. |

So sánh:

~~~java
Stream<Integer> numbers = Stream.of(1, 2, 3);

// T = Integer, kết quả cũng là Integer:
int total = numbers.reduce(0, Integer::sum);
~~~

Với Stream chuỗi, phép tính độ dài cần thay đổi kiểu:

~~~java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");

// T = String, U = Integer.
int totalChars = names.stream()
        .reduce(
                0,
                (sum, name) -> sum + name.length(),
                Integer::sum
        );

System.out.println(totalChars); // 9
~~~

Trong đoạn này `identity = 0`; `accumulator` biến `Integer + String` thành một `Integer`; `combiner` cộng hai số nguyên. Không thể dùng overload hai tham số `reduce(0, ...)` trực tiếp trên `Stream<String>` vì khi đó identity phải là `String`, phù hợp với kiểu phần tử `T`.

> **Điểm cốt lõi:** Overload ba tham số dùng **hai phép kết hợp có vai trò khác nhau**: nhận thêm một `T` vào `U` và gộp hai `U`. Dù khi chạy tuần tự có thể chỉ thấy accumulator được gọi, combiner vẫn là một phần bắt buộc của hợp đồng.

## 2. Hiểu luồng xử lý trong chế độ tuần tự và song song

Với dữ liệu:

~~~text
["An", "Binh", "Chi"]  -- String (T)
           |
           v
      accumulate
           |
           v
     Tổng độ dài       -- Integer (U)
~~~

Khi chạy tuần tự, ta có thể hình dung:

~~~text
identity = 0
accumulate(0, "An")   = 2
accumulate(2, "Binh") = 6
accumulate(6, "Chi")  = 9
Kết quả: 9
~~~

Khi chạy song song, Stream có thể chia nguồn thành nhiều phần. Mỗi phần được tích lũy riêng từ identity, rồi các kết quả được ghép bằng combiner:

~~~text
Nhánh A: ["An", "Binh"] -> 0 + 2 + 4 = 6
Nhánh B: ["Chi"]        -> 0 + 3     = 3

combine(6, 3) -> 9
~~~

Đó chỉ là **một cách chia minh họa**, không phải cách chia cố định của JDK. Số phần, thứ tự lời gọi và cách ghép có thể khác. Chương trình đúng phải cho cùng **kết quả theo hợp đồng** dù cách chia thay đổi.

Ví dụ chạy song song:

~~~java
int totalChars = names.parallelStream()
        .reduce(
                0,
                (sum, name) -> sum + name.length(),
                Integer::sum
        );
~~~

Chuyển sang `parallelStream()` không làm thay đổi ý nghĩa của kết quả. Tuy nhiên, không nên coi xử lý song song là tối ưu mặc định; công việc quá nhỏ có thể chậm hơn do chi phí chia và ghép tác vụ.

## 3. Hợp đồng bắt buộc của identity, accumulator và combiner

Để reduction có thể gộp các phần con an toàn, Java Stream API yêu cầu các hàm **không can thiệp vào nguồn**, **không phụ thuộc trạng thái thay đổi bên ngoài** và tuân theo các quan hệ toán học thích hợp.

### 3.1. Identity phải là phần tử trung hòa của combiner

Với mọi tổng một phần `u`:

~~~text
combiner(identity, u) = u
~~~

Ví dụ, khi kết quả là tổng số nguyên:

~~~java
identity  = 0;
combiner  = Integer::sum;
~~~

Vì `0 + u = u` nên `0` là identity phù hợp. Nếu dùng `10` làm identity chỉ để “cộng sẵn 10” thì mỗi nhánh song song có thể cộng thêm 10, khiến kết quả thay đổi theo cách phân chia.

~~~java
import java.util.List;

List<String> words = List.of("a", "bb");

// Sai: 10 không phải identity của phép cộng.
int broken = words.parallelStream()
        .reduce(10, (sum, word) -> sum + word.length(), Integer::sum);
~~~

Trên tuần tự, đoạn trên cho `13`; nếu tách thành hai nhánh, mỗi nhánh khởi tạo bằng `10` nên có thể thu `(10 + 1) + (10 + 2) = 23`. Đoạn mã **vi phạm hợp đồng reduce**, vì vậy kết quả không được bảo đảm.

Nếu muốn cộng phí cố định 10 vào tổng, cách đúng là:

~~~java
int base = 10;
int total = base + words.parallelStream()
        .reduce(0, (sum, word) -> sum + word.length(), Integer::sum);

System.out.println(total); // 13
~~~

### 3.2. Combiner phải có tính kết hợp

Với mọi tổng một phần `a`, `b`, `c`, ta cần:

~~~text
combine(combine(a, b), c) = combine(a, combine(b, c))
~~~

Phép cộng số nguyên trong điều kiện số học đang xét và phép cộng `BigDecimal` chính xác đáp ứng điều kiện này. Một phép cộng rồi **làm tròn trung gian** có thể không còn kết hợp; vì thế không nên nhét bước làm tròn vào combiner nếu muốn tổng chính xác và kết quả song song ổn định.

Tính kết hợp **không đồng nghĩa** với tính giao hoán. Chẳng hạn, phép nối chuỗi có tính kết hợp nhưng không giao hoán: `"ab" + "c"` bằng `"a" + "bc"`, còn `"a" + "b"` khác `"b" + "a"`. Nếu phép toán nhạy với thứ tự, phải tôn trọng *encounter order* của Stream; không được tự ý gọi `unordered()` khi bài toán yêu cầu thứ tự.

### 3.3. Accumulator và combiner phải tương thích

Với tổng một phần `u` và phần tử mới `t`, hợp đồng yêu cầu:

~~~text
combine(u, accumulate(identity, t)) = accumulate(u, t)
~~~

Hiểu đơn giản: kết quả khi tích lũy phần tử `t` vào `u` phải khớp với việc **tính riêng phần tử đó từ identity** rồi ghép vào `u` bằng combiner.

Trong ví dụ tổng độ dài chuỗi:

~~~text
combine(5, accumulate(0, "An"))
= combine(5, 2)
= 7

accumulate(5, "An") = 7
~~~

Nếu accumulator tính tổng độ dài nhưng combiner lại lấy hiệu hoặc nhân hai tổng, các nhánh song song sẽ ghép ra kết quả sai:

~~~java
// Sai: combiner không cùng ngữ nghĩa với accumulator.
int broken = words.parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left - right
        );
~~~

Trong pipeline tuần tự, lỗi này có thể bị che khuất vì combiner không nhất thiết được gọi. Do đó, **chạy đúng ở chế độ tuần tự chưa đủ chứng minh reduction ba tham số là đúng**.

### 3.4. Không chia sẻ trạng thái thay đổi giữa các hàm

`accumulator` và `combiner` nên hoạt động trên những giá trị độc lập, lý tưởng là bất biến (*immutable*). Tránh ghi vào danh sách hay bộ đếm bên ngoài để lưu tổng, vì nhiều nhánh có thể chạy đồng thời.

Các nguyên tắc này cũng áp dụng khi kết hợp Stream với `filter`, `map`, Spliterator tùy chỉnh, pipeline song song hoặc những thao tác trung gian mới. Cách chia công việc có thể thay đổi, nên ý nghĩa reduction không được phụ thuộc vào thứ tự gọi hàm tùy ý hoặc trạng thái chia sẻ.

## 4. Ví dụ thực tế: từ Sale sang InvoiceStats

Một hóa đơn gồm nhiều dòng hàng, mỗi dòng có mã sản phẩm, số lượng và đơn giá. Ta muốn **một kết quả có kiểu khác nguồn**, chứa ba chỉ số:

- `lineCount`: số dòng hàng.
- `totalUnits`: tổng đơn vị sản phẩm.
- `exactAmount`: tổng tiền trước làm tròn.

Dùng một `record` bất biến làm kiểu tích lũy `U`.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class InvoiceStatsDemo {

    record Sale(String sku, long quantity, BigDecimal unitPrice) {}

    record InvoiceStats(
            long lineCount,
            long totalUnits,
            BigDecimal exactAmount) {

        static InvoiceStats zero() {
            return new InvoiceStats(0, 0, BigDecimal.ZERO);
        }

        InvoiceStats addSale(Sale sale) {
            BigDecimal lineAmount = sale.unitPrice()
                    .multiply(BigDecimal.valueOf(sale.quantity()));

            return new InvoiceStats(
                    lineCount + 1,
                    totalUnits + sale.quantity(),
                    exactAmount.add(lineAmount)
            );
        }

        InvoiceStats merge(InvoiceStats other) {
            return new InvoiceStats(
                    lineCount + other.lineCount(),
                    totalUnits + other.totalUnits(),
                    exactAmount.add(other.exactAmount())
            );
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("PEN", 2, new BigDecimal("12.50")),
                new Sale("BOOK", 1, new BigDecimal("8.75")),
                new Sale("PAD", 3, new BigDecimal("2.40"))
        );

        InvoiceStats stats = sales.stream()
                .reduce(
                        InvoiceStats.zero(),  // U: giá trị trung hòa
                        InvoiceStats::addSale, // (U, Sale) -> U
                        InvoiceStats::merge    // (U, U) -> U
                );

        System.out.println(stats.lineCount());  // 3
        System.out.println(stats.totalUnits()); // 6
        System.out.println(stats.exactAmount()); // 40.95
    }
}
~~~

Đọc đoạn mã theo kiểu dữ liệu:

~~~text
Stream<Sale>       T = Sale
identity           U = InvoiceStats
accumulator        (InvoiceStats, Sale) -> InvoiceStats
combiner           (InvoiceStats, InvoiceStats) -> InvoiceStats
kết quả reduce     U = InvoiceStats
~~~

Ba khoản tiền là `2 × 12.50 = 25.00`, `1 × 8.75 = 8.75` và `3 × 2.40 = 7.20`. Tổng chính xác bằng `40.95`. Mỗi lần `addSale` tạo **một đối tượng mới**, không sửa đối tượng tích lũy nhận vào. `merge` cũng tạo đối tượng mới, cộng những chỉ số tương ứng.

Nếu dữ liệu không có dòng hàng:

~~~java
InvoiceStats emptyStats = List.<Sale>of().stream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );

System.out.println(emptyStats.lineCount());  // 0
System.out.println(emptyStats.exactAmount()); // 0
~~~

Mẫu này hoàn toàn có thể chạy song song:

~~~java
InvoiceStats parallelStats = sales.parallelStream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );
~~~

Với dữ liệu ví dụ và các phép cộng chính xác, các chỉ số đều phải có cùng giá trị số học giữa chạy tuần tự và song song.

> **Phiên bản Java:** `record` chính thức có từ Java 16; nếu dùng Java 8–15, thay bằng lớp immutable có constructor, getter và phương thức tạo giá trị mới. Overload `reduce` ba tham số đã có từ Java 8.

## 5. Kiểm tra hợp đồng bằng ví dụ InvoiceStats

Với `InvoiceStats.zero()`:

~~~text
zero = (lineCount=0, totalUnits=0, exactAmount=0)
~~~

Nếu `u` là một tổng phần bất kỳ, `zero.merge(u)` có cùng các chỉ số với `u`. Đây là quan hệ identity.

Với ba tổng phần `a`, `b`, `c`, phép `merge` cộng từng thành phần. Vì cộng chính xác các giá trị tiền và cộng số đếm, việc nhóm `(a.merge(b)).merge(c)` hay `a.merge(b.merge(c))` cho cùng kết quả theo số học (giả sử số đếm `long` không vượt giới hạn và dữ liệu hợp lệ). Đây là tính kết hợp.

Cuối cùng, với một dòng `sale` bất kỳ:

~~~text
u.merge(zero.addSale(sale)) == u.addSale(sale)
~~~

Ở đây ký hiệu `==` diễn tả **bằng nhau về nội dung các chỉ số**, không phải so sánh tham chiếu Java bằng toán tử `==`. Hai phép tạo `InvoiceStats` có thể trả về hai đối tượng khác nhau nhưng cùng giá trị.

Trong chương trình thật, cần thống nhất thêm chính sách với `null`, số lượng âm, đơn giá âm, tràn số đếm và scale của `BigDecimal`. Những chính sách đó thuộc mô hình nghiệp vụ; `reduce` chỉ kết hợp các kết quả theo định nghĩa mà ta đưa vào.

## 6. Dùng phương thức lambda trực tiếp thay cho record trung gian

Không nhất thiết phải tạo record thống kê nếu kết quả chỉ là một số. Ví dụ, đếm tổng số ký tự trong chuỗi:

~~~java
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

long totalCharacters = words.stream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(totalCharacters); // 13
~~~

`T = String` còn `U = Long`; dạng ba tham số biểu đạt việc chuyển từ chuỗi sang tổng độ dài. Dùng `long` giúp giới hạn tràn lớn hơn so với `int`, dù bản thân `long` vẫn có thể tràn với dữ liệu cực lớn.

Với phép tổng này, một pipeline ngắn hơn và thường hiệu quả hơn là:

~~~java
long sameTotal = words.stream()
        .mapToLong(String::length)
        .sum();
~~~

Hai cách phù hợp khi chỉ cần một con số; dạng primitive stream tránh việc tạo các đối tượng `Long` trung gian. Khi cần **nhiều phép tổng hợp khác nhau trong một kiểu kết quả**, ví dụ `InvoiceStats`, overload ba tham số thể hiện rõ mô hình `T -> U` hơn.

### Khi có điều kiện lọc

Có thể đặt `filter` phía trước `reduce`:

~~~java
long lengthOfLongWords = words.stream()
        .filter(word -> word.length() >= 5)
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(lengthOfLongWords); // 6 ("Stream")
~~~

`filter` giữ lại những phần tử được đưa đến accumulator. Dù `filter` và `map` thường là thao tác trung gian *lazy*, `reduce` là **terminal operation** nên kích hoạt quá trình duyệt và kết thúc pipeline. Đối tượng Stream đó không thể dùng lại cho một terminal operation khác.

## 7. Sai lầm phổ biến: reduce với danh sách hoặc Map mutable

Đây là cách **không nên** dùng để dựng một danh sách từ Stream:

~~~java
import java.util.ArrayList;
import java.util.List;

// Ví dụ sai, không dùng trong ứng dụng:
List<String> result = words.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, word) -> {
                    list.add(word);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Tại sao sai?

1. `identity` là **một đối tượng danh sách mutable**, được dùng làm giá trị khởi tạo cho các phép giảm. Khi các hàm sửa trực tiếp đối tượng này, các nhánh có thể chia sẻ cùng trạng thái và gây race condition.
2. `accumulator` thay đổi trực tiếp input thay vì trả về một tổng phần độc lập; việc áp dụng hoặc ghép các phần con có thể làm lặp phần tử hoặc cho kết quả phụ thuộc cách chạy.
3. `combiner` tiếp tục sửa một danh sách có thể trùng với danh sách khác hoặc với identity. Hợp đồng identity và tính tương thích không còn được đảm bảo.

Để tích lũy vào **container có thể thay đổi**, Java Stream API có terminal operation `collect` chuyên biệt:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> result = words.parallelStream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Hoặc dùng overload ba tham số của `collect`, vốn nhận `supplier` tạo container riêng, `accumulator` kiểu `BiConsumer` và `combiner` kiểu `BiConsumer`:

~~~java
List<String> result = words.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
~~~

So sánh quan trọng:

| `reduce(identity, accumulator, combiner)` | `collect(supplier, accumulator, combiner)` |
| --- | --- |
| `identity` là một **giá trị `U`**. | `supplier` là hàm tạo **container mới**. |
| Accumulator trả lại `U`. | Accumulator thường thay đổi container và trả `void`. |
| Combiner trả về một `U`. | Combiner nhận hai container và trả `void` trong overload ba tham số của `Stream.collect`. |
| Phù hợp với kết quả bất biến, phép kết hợp thuần. | Phù hợp với danh sách, map, builder và các cấu trúc mutable. |

Cần phân biệt với `Collector` dùng bởi `collect(Collector)`: loại này có đặc tả riêng về supplier, accumulator, combiner, finisher và characteristics. Đối với nhóm dữ liệu, `Collectors.groupingBy`, `partitioningBy` hoặc collector tùy chỉnh thường phù hợp hơn việc dựng Map mutable bằng `reduce`.

Nếu tự viết collector cho xử lý song song, vẫn cần tuân thủ hợp đồng về kết hợp, container và thứ tự.

## 8. Những lỗi làm kết quả tuần tự và song song khác nhau

| Biểu hiện | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Kết quả có “phí ban đầu” bị cộng nhiều lần | `identity` khác phần tử trung hòa | Dùng identity trung hòa, cộng khoản cố định vào **sau** reduction. |
| Tuần tự đúng, song song sai | `combiner` khác nghĩa với `accumulator` | Bảo đảm `combine(u, accumulate(identity, t)) = accumulate(u, t)`. |
| Kết quả phụ thuộc cách chia nhóm | Combiner không kết hợp, ví dụ có làm tròn trung gian | Chỉ gộp chính xác; thực hiện làm tròn tại bước nghiệp vụ đã xác định. |
| Dữ liệu bị lặp hoặc mất khi chạy song song | Biến tích lũy mutable bị chia sẻ | Dùng giá trị `U` bất biến hoặc chuyển sang `collect`. |
| Không xử lý đúng Stream rỗng | Identity không diễn tả kết quả rỗng | Xác định phần tử trung hòa đúng: 0 cho tổng, 1 cho tích, record rỗng cho thống kê. |
| Có lỗi `NullPointerException` trong accumulator | Phần tử `null` hoặc field được phép rỗng | Xác nhận đầu vào; đặt quy tắc loại bỏ, mặc định hoặc từ chối rõ ràng. |
| Kết quả nối chuỗi đổi thứ tự | Pipeline unordered nhưng phép kết hợp nhạy thứ tự | Bảo đảm encounter order hoặc đổi mô hình phép toán phù hợp. |
| Tổng quá lớn hoặc tính chậm | Boxing, cấp phát nhiều `U`, chạy song song quá nhỏ | Cân nhắc primitive stream hoặc collector được tối ưu, đo hiệu năng thực tế. |

### Không làm tròn ngay trong mỗi lần cộng BigDecimal

Ví dụ sau có nguy cơ vi phạm tính kết hợp:

~~~java
// Không nên khi mục tiêu là tổng tiền chính xác:
BigDecimal total = sales.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (subtotal, sale) -> subtotal
                        .add(sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())))
                        .setScale(2, RoundingMode.HALF_UP),
                (left, right) -> left.add(right)
                        .setScale(2, RoundingMode.HALF_UP)
        );
~~~

Làm tròn ở từng nhánh hoặc từng bước ghép có thể khiến kết quả thay đổi. Nếu quy tắc nghiệp vụ là **cộng chính xác rồi làm tròn một lần**, hãy thực hiện:

~~~java
BigDecimal exactTotal = sales.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (sum, sale) -> sum.add(
                        sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity()))),
                BigDecimal::add
        );

BigDecimal payable = exactTotal.setScale(
        2, RoundingMode.HALF_UP);
~~~

Đoạn mã này giả sử đã import `java.math.BigDecimal` và `java.math.RoundingMode`, các bản ghi `Sale` có accessor `unitPrice()` và `quantity()`, đồng thời chính sách làm tròn một lần ở cấp hóa đơn được nghiệp vụ cho phép.

## 9. Khi nào không nên dùng reduce ba tham số?

Dù linh hoạt, overload ba tham số không phải lúc nào cũng là lựa chọn tối ưu.

### 9.1. Tổng số nguyên hoặc số thực nguyên thủy

Với `Stream<String>`, nếu chỉ cộng độ dài chuỗi:

~~~java
long length = words.stream()
        .mapToLong(String::length)
        .sum();
~~~

Cách này ngắn, tránh boxing trong phần tổng hợp và thể hiện rõ ý nghĩa. Tương tự, dùng `mapToInt`, `mapToDouble` và các phép `sum`, `average`, `summaryStatistics` khi phù hợp.

### 9.2. Cần collector thống kê sẵn có

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.Collectors;

IntSummaryStatistics stats = words.stream()
        .collect(Collectors.summarizingInt(String::length));

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 13
~~~

Collector này đã cung cấp số lượng, tổng, min, max và trung bình độ dài. Nếu các thống kê cần có đã được thư viện cung cấp và khớp yêu cầu, dùng collector có sẵn giúp giảm mã tùy chỉnh.

### 9.3. Cần nhóm dữ liệu hoặc kết quả mutable

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));
~~~

`groupingBy` tạo Map chứa danh sách chuỗi được nhóm theo độ dài, không cần tự dựng một `Map` mutable bằng `reduce`. Với danh sách, `toList()` hoặc `Collectors.toList()` cũng phù hợp hơn.

### 9.4. Chỉ cần đổi kiểu một lần rồi dùng overload hai tham số

Nếu phần tử có thể chuyển thành kiểu kết quả bằng `map`, có thể tách bước chuyển kiểu:

~~~java
BigDecimal total = sales.stream()
        .map(sale -> sale.unitPrice()
                .multiply(BigDecimal.valueOf(sale.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Đây là `Stream<Sale> -> Stream<BigDecimal> -> BigDecimal`. Nó rất dễ đọc và cho phép dùng overload hai tham số vì tại thời điểm reduce, kiểu phần tử đã là `BigDecimal`.

Ngược lại, nếu muốn trực tiếp tạo một kết quả có nhiều trường từ mỗi phần tử và kết hợp các kết quả trung gian, `reduce` ba tham số cùng một kiểu `U` bất biến như `InvoiceStats` là lựa chọn hợp lý.

## 10. Vòng đời Stream, tài nguyên và giới hạn hiệu năng

`reduce` là **terminal operation**: dù pipeline phía trước gồm `filter`, `map` và các bước *lazy*, việc gọi `reduce` bắt đầu duyệt nguồn để tính kết quả. Sau đó, không thể gọi thêm một terminal operation khác trên cùng đối tượng Stream.

Để tổng hợp toàn bộ dữ liệu, reduction thông thường phải tiêu thụ tất cả phần tử đầu ra. Với Stream vô hạn không có điểm dừng, `reduce` không tự biết lúc nào đủ dữ liệu; cần một giới hạn hữu hạn như `limit` hoặc một thiết kế nguồn kết thúc rõ ràng.

~~~java
long sumFirstTen = java.util.stream.LongStream.iterate(1, n -> n + 1)
        .limit(10)
        .sum();

System.out.println(sumFirstTen); // 55
~~~

`reduce` có thể tránh việc giữ tất cả phần tử vào một `List`, nhưng một `U` lớn hoặc phép ghép tốn kém vẫn có thể dùng nhiều CPU và bộ nhớ. Với `InvoiceStats`, mỗi lần accumulator tạo một record mới và có thể tạo `BigDecimal` mới; đây là đánh đổi giữa tính bất biến, dễ chứng minh đúng và chi phí cấp phát. Trên dữ liệu rất lớn, nên đo hiệu năng trước khi quyết định dùng reduction tùy chỉnh hay collector tối ưu.

Nếu nguồn là tệp hoặc tài nguyên I/O, chẳng hạn Stream từ `Files.lines`, dùng `try-with-resources` để đóng nguồn. `reduce` kết thúc phép tính nhưng không thay thế hợp đồng đóng tài nguyên.

Khi chạy song song, hãy nhớ `reduce` không tự tạo ra an toàn luồng cho lambda có side effect, không khắc phục các hạn chế của nguồn/Spliterator và không bảo đảm cải thiện tốc độ trong mọi trường hợp.

## 11. Tự kiểm tra

**Bài 1 — Kiểu T và U**

~~~java
List<String> words = List.of("A", "BC", "DEF");

long result = words.stream()
        .reduce(0L, (total, s) -> total + s.length(), Long::sum);
~~~

Hỏi kiểu `T`, `U` và giá trị kết quả là gì?

**Đáp án:** `T = String`, `U = Long`, kết quả là `1 + 2 + 3 = 6`.

**Bài 2 — Tìm lỗi với identity**

~~~java
long result = words.parallelStream()
        .reduce(100L, (total, s) -> total + s.length(), Long::sum);
~~~

Hỏi tại sao kết quả có thể sai?

**Đáp án:** `100L` không trung hòa với `Long::sum`. Mỗi nhánh có thể bắt đầu từ 100; muốn cộng thêm khoản cố định 100, hãy giảm từ `0L` rồi cộng 100 sau khi nhận kết quả.

**Bài 3 — Chọn reduce hay collect**

Yêu cầu tạo `List<String>` chứa các phần tử viết hoa từ `Stream<String>`. Nên dùng `reduce(new ArrayList<>(), ...)` rồi sửa danh sách trong accumulator không?

**Đáp án:** Không. Dùng:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Nếu cần danh sách mutable, có thể dùng `collect(Collectors.toCollection(ArrayList::new))`.

**Bài 4 — Kiểm tra combiner**

~~~java
int total = words.parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left * right
        );
~~~

Hỏi vì sao combiner sai?

**Đáp án:** Accumulator tính tổng độ dài, nhưng combiner lại nhân các tổng một phần, không đáp ứng tính tương thích. Ngoài ra, `0` là phần tử trung hòa của phép cộng chứ không phải phép nhân. Combiner đúng với ngữ nghĩa tổng là `Integer::sum`.

**Bài 5 — Kết quả cho Stream rỗng**

~~~java
InvoiceStats stats = List.<Sale>of().stream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );
~~~

Hỏi kết quả là gì?

**Đáp án:** `InvoiceStats.zero()`: 0 dòng, 0 đơn vị, tổng chính xác bằng 0. Vì không có phần tử để tích lũy, reduction trả identity đúng hợp đồng.

## 12. Ghi nhớ

- `reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` cho phép tổng hợp từ `Stream<T>` thành kết quả kiểu `U`.
- **Identity** phải trung hòa với combiner; **combiner** phải có tính kết hợp; **accumulator** phải tương thích với combiner.
- Việc chạy tuần tự có thể che giấu lỗi combiner; khi xử lý song song, các tổng một phần cần ghép ra cùng kết quả nghiệp vụ.
- Dùng **kiểu `U` bất biến** khi muốn một reduction thuần, đặc biệt với bản thống kê gồm nhiều trường.
- Không dùng `reduce` để sửa chung `ArrayList`, `HashMap` hoặc builder; dùng `collect` khi cần mutable reduction.
- Với bài toán đơn giản, cân nhắc `mapToInt`/`mapToLong` và `sum`, các collector thống kê, `groupingBy` hoặc `map` rồi `reduce` hai tham số.

**Ý chính:** Overload `reduce` ba tham số là công cụ để **đổi kiểu kết quả trong quá trình rút gọn**. Sự đúng đắn không chỉ nằm ở cách tính accumulator trên từng phần tử mà còn ở khả năng **ghép các kết quả trung gian bằng combiner** theo cùng một quy tắc, độc lập với cách Stream chia công việc.

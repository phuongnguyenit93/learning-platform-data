# Phép rút gọn kết hợp nhiều phần tử thành một kết quả trong Java Stream

## 1. Reduction là gì?

**Reduction** (rút gọn) là thao tác kết hợp nhiều phần tử thành **một kết quả tổng hợp**. Thay vì giữ một danh sách kết quả như `map` hay chọn bớt các phần tử như `filter`, `reduce` nhận một phép kết hợp và áp dụng nó để tính ra tổng, tích, giá trị lớn nhất hoặc một đối tượng thống kê.

Ví dụ, với nguồn có thứ tự:

~~~text
Nguồn: [2, 3, 4]
Tổng: 0 + 2 + 3 + 4 = 9
Tích: 1 × 2 × 3 × 4 = 24
Max: max(max(2, 3), 4) = 4
~~~

Đặt trong một phương thức Java:

~~~java
List<Integer> values = List.of(2, 3, 4);
int sum = values.stream().reduce(0, Integer::sum);
int product = values.stream().reduce(1, (a, b) -> a * b);
~~~

Đoạn này cần `import java.util.List;`. `reduce` là **terminal operation** của Stream: lời gọi yêu cầu framework tính một kết quả, tiêu thụ Stream tương ứng. Hai phép cộng/nhân trong ví dụ trả lần lượt `9` và `24`.

Java 17 cung cấp ba overload quan trọng:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)

Optional<T> reduce(BinaryOperator<T> accumulator)

<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Đây là **chữ ký API để giải thích**, không phải đoạn code hoàn chỉnh đặt trong class. Chúng lần lượt phục vụ: (1) phép kết hợp có giá trị trung tính và kết quả T, (2) phép kết hợp không có giá trị trung tính nên cần biểu diễn trường hợp nguồn rỗng, (3) phép tổng hợp có kiểu kết quả U khác kiểu phần tử nguồn T.

**Nguyên tắc học bài:** `reduce` không chỉ là một vòng lặp viết ngắn. Một phép reduce đúng phải đáp ứng các yêu cầu về **identity**, **tính kết hợp**, **không can thiệp nguồn** và khả năng xử lý **Stream rỗng**.

## 2. reduce(identity, accumulator) — dùng khi có phần tử trung tính

Phép cộng:

~~~java
int total = List.of(2, 3, 4).stream()
        .reduce(0, Integer::sum);
// 9
~~~

- `identity = 0`: giá trị bắt đầu và cũng là phần tử **trung tính** của phép cộng.
- `accumulator = Integer::sum`: hàm nhận hai giá trị `Integer`, trả tổng của chúng.
- Kiểu kết quả là `Integer` (được unbox về `int` trong dòng trên).

Có thể hiểu phép tính tuần tự về mặt logic:

| Bước | Đã tích lũy | Phần tử | Kết quả mới |
| --- | ---: | ---: | ---: |
| Khởi đầu | 0 | — | 0 |
| 1 | 0 | 2 | 2 |
| 2 | 2 | 3 | 5 |
| 3 | 5 | 4 | 9 |

Tuy nhiên, đây là sơ đồ mô tả dễ hiểu khi **tuần tự**, không phải lời hứa rằng mọi lần reduce chạy đúng một lịch xử lý duy nhất. Framework có thể chia và gộp các nhóm khi thực thi song song nếu accumulator đáp ứng hợp đồng.

### 2.1. Chọn đúng identity

Với toán tử `op`, identity `e` cần thỏa:

~~~text
op(e, x) == x
op(x, e) == x
~~~

cho các giá trị thuộc miền được xét (trong phạm vi ngữ nghĩa phép tính). Ví dụ:

| Phép kết hợp | Identity hợp lệ | Tại sao |
| --- | --- | --- |
| Cộng số | `0` | `0+x=x` |
| Nhân số | `1` | `1*x=x` |
| Ghép chuỗi | `""` | `"".concat(s)=s` |
| Hợp nhất hai thống kê (count,total) | `Stats(0,0)` | Không tăng số lượng và tổng |

Không được dùng identity tùy tiện. Nếu viết `reduce(10, Integer::sum)`, kết quả của `[2,3,4]` là 19, không phải 9. Nếu viết `reduce(0, (a,b)->a*b)`, mọi tích sẽ bị ép thành 0.

Đặc biệt với parallel reduction, một identity không trung tính có thể được áp dụng ở nhiều phần xử lý, khiến kết quả sai theo cách khó nhận ra trong bài test tuần tự.

### 2.2. Stream rỗng khi có identity

~~~java
int emptySum = List.<Integer>of().stream()
        .reduce(0, Integer::sum);
// 0
~~~

Vì không có phần tử nguồn để tích lũy, overload này trả **identity**. Đây là giá trị có nghĩa đối với phép cộng; không phải exception và không phải `null`.

## 3. reduce(BinaryOperator) không có identity — trả Optional<T>

Một số bài toán không có một giá trị trung tính tự nhiên. Ví dụ tìm **phần tử lớn nhất** trong tập có thể rỗng:

~~~java
Optional<Integer> largest = List.of(2, 3, 4).stream()
        .reduce(Integer::max);
// Optional[4]
~~~

Đoạn minh họa cần `import java.util.Optional;`. Trên nguồn có phần tử, hàm `Integer::max` kết hợp các giá trị thành giá trị lớn nhất. Trên nguồn rỗng:

~~~java
Optional<Integer> emptyMax = List.<Integer>of().stream()
        .reduce(Integer::max);
// Optional.empty()
~~~

Nếu không có phần tử, không thể khẳng định “max bằng 0”: một nguồn toàn số âm vẫn có max âm, còn nguồn rỗng **không có max**. Vì vậy, thay vì đặt identity giả, Java trả `Optional<T>` để caller quyết định chính sách:

~~~java
int max = largest.orElseThrow();
int fallback = emptyMax.orElse(-1);
~~~

Chọn giá trị mặc định `-1` chỉ khi nó hợp lệ trong ngữ nghĩa nghiệp vụ. Nếu nguồn rỗng là một lỗi, có thể dùng `orElseThrow(...)`; nếu nguồn rỗng là tình huống bình thường, giữ `Optional` và xử lý rõ tại ranh giới.

**Lưu ý về null:** phép giảm kết quả thành `null` không phải cách mô hình hóa một kết quả Optional hợp lệ. Một reduction trả `null` có thể dẫn đến `NullPointerException`; nên thiết kế toán tử và kiểu dữ liệu tránh null hoặc có cách biểu diễn thiếu dữ liệu riêng.

## 4. Associativity — điều kiện quan trọng nhất để gộp các nhóm

Phép kết hợp `op` là **associative** nếu:

~~~text
(a op b) op c == a op (b op c)
~~~

Tại sao cần? Với parallel Stream, framework có thể chia nguồn:

~~~text
[2, 3, 4]
 /   |   \
2    3    4       (các nhóm được rút gọn độc lập)
 \   |   /
(2 + 3) + 4 = 9  (kết hợp các kết quả nhóm)
~~~

Đây là mô hình khái niệm, không mô tả chính xác việc chia thread trong mọi JDK.

### 4.1. Phép cộng số nguyên và identity 0

`Integer::sum` kết hợp với identity 0 theo ngữ nghĩa phép cộng int của Java, vì vậy kết quả giảm là 9 cho dữ liệu nhỏ trên dù có thể phân nhóm.

Tuy nhiên, **tính kết hợp của phép cộng theo kiểu int không bảo đảm không overflow**. Kết quả số nguyên Java có thể tràn miền biểu diễn. Với số lượng lớn hoặc tiền, cần chọn kiểu dữ liệu và chính sách overflow phù hợp, có thể dùng `Math.addExact`, `long` hoặc `BigDecimal` tùy bài toán.

### 4.2. Phép trừ không associative

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Đây là hai kết quả khác nhau. Vì thế không nên viết:

~~~java
// Phản ví dụ về hợp đồng rút gọn song song:
int difference = List.of(10, 3, 2).parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Dòng này có cú pháp hợp lệ nhưng không đáp ứng yêu cầu toán tử kết hợp của reduction. Khi framework chia nhóm, kết quả có thể lệch khỏi phép trừ từ trái sang phải mà người lập trình hình dung.

Nếu nghiệp vụ thực sự yêu cầu lần lượt trừ một dãy số theo thứ tự, hãy thiết kế một phép toán tường minh có thứ tự hoặc chuyển biểu thức sang một reduction associative khi toán học cho phép.

### 4.3. Số thực cần thận trọng

Với `double`, phép cộng có thể khác kết quả khi đổi cách nhóm vì sai số làm tròn:

~~~text
(1.0e16 + (-1.0e16)) + 1.0 = 1.0
1.0e16 + ((-1.0e16) + 1.0) = 0.0
~~~

Trong bài toán cần tính toán số thực chặt chẽ, không tự cho rằng mọi dạng reduce song song cho kết quả bit-for-bit giống lặp tuần tự. Có thể cần một thuật toán tổng hợp số ổn định hơn hoặc kiểu số chính xác theo domain.

## 5. Stateless và non-interfering: không biến reduce thành kênh tác dụng phụ

Accumulator nên nhận các đối số và trả kết quả mới dựa vào chúng, không phụ thuộc trạng thái mutable chia sẻ. Cần tránh:

~~~java
// Phản ví dụ: dùng accumulator để sửa trạng thái bên ngoài.
// int[] sum = {0};
// numbers.stream().reduce(0, (a,b) -> {
//     sum[0] += b;
//     return a + b;
// });
~~~

Biến `sum[0]` không phải phần của kết quả return từ reduce; khi chạy parallel, side effect như vậy dễ gây race và không có hợp đồng số lần thực thi đúng theo mong muốn.

Nên lấy **giá trị trả về từ reduce** làm kết quả:

~~~java
int sum = numbers.stream().reduce(0, Integer::sum);
~~~

Với các phần tử mutable, không được thay đổi Collection nguồn trong callback đang duyệt. Điều này không đồng nghĩa không thể xử lý object mutable, nhưng nếu muốn cập nhật trạng thái bên ngoài, cần thiết kế API/action riêng có hợp đồng rõ về threading, lỗi và thứ tự.

## 6. Overload ba đối số: reduce(identity, accumulator, combiner)

Khi nguồn có kiểu `T` nhưng kết quả có kiểu `U`, dùng:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Ba thành phần có vai trò khác nhau:

| Thành phần | Tham số | Giá trị trả về | Vai trò |
| --- | --- | --- | --- |
| Identity | Không | U | Tổng hợp rỗng/trung tính |
| Accumulator | U, T | U | Gộp một phần tử nguồn vào kết quả đang có |
| Combiner | U, U | U | Gộp hai kết quả từng phần |

Khi chạy parallel, framework có thể tích lũy độc lập từng phần rồi dùng combiner để hợp nhất các tổng hợp U.

### 6.1. Ví dụ cộng độ dài các chuỗi

~~~java
List<String> names = List.of("An", "Binh", "Chi");

int letterCount = names.parallelStream().reduce(
        0,
        (subtotal, name) -> subtotal + name.length(),
        Integer::sum);
// 9
~~~

Đoạn này cần `java.util.List`. Ở đây `T=String`, `U=Integer`, identity là 0, accumulator cộng chiều dài một tên, combiner cộng hai subtotal. Tổng là 2 + 4 + 3 = 9.

Cách viết gần hơn với ý định nếu chỉ cần tổng độ dài:

~~~java
int letterCount = names.parallelStream()
        .mapToInt(String::length)
        .sum();
~~~

Việc học overload ba đối số cần thiết khi giá trị tổng hợp là kiểu khác với phần tử nguồn và không có terminal operation đơn giản tương đương.

### 6.2. Combiner phải tương thích với accumulator

Không đủ nếu `accumulator` cho kết quả đúng trong pipeline tuần tự nhưng `combiner` bỏ đi một phần tổng hợp. Javadoc đưa ra điều kiện tương thích:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

với kết quả tổng hợp U và phần tử T phù hợp.

Bên cạnh đó, combiner phải **associative**, identity phải trung tính với combiner và các hàm phải stateless/non-interfering. Nếu combiner chỉ trả tham số trái, phần xử lý phải có thể bị mất khi framework kết hợp các nhóm.

**Đừng dùng một combiner giả chỉ để vượt qua lỗi biên dịch** với dự định “mình chỉ chạy tuần tự”. API của bạn có thể được gọi trên parallel Stream sau này; thiết kế đúng từ đầu an toàn hơn.

## 7. Rút gọn thành một record thống kê bất biến

Reduction có thể trả về một object chứa **nhiều chỉ số**, không chỉ một số đơn.

Ví dụ record Java 17:

~~~java
record Stats(long orderCount, long totalAmount) {
    Stats combine(Stats other) {
        return new Stats(
                orderCount + other.orderCount,
                totalAmount + other.totalAmount);
    }
}
~~~

Đây là khai báo **kiểu**, cần đặt trong một class hoặc ở phạm vi top-level hợp lệ. Nếu mỗi đơn hàng có phương thức `long amount()`, ta có thể tạo một `Stats` cho từng đơn:

~~~java
Stats stats = orders.parallelStream()
        .map(order -> new Stats(1, order.amount()))
        .reduce(new Stats(0, 0), Stats::combine);
~~~

- `Stats(0,0)` là identity của phép cộng hai thống kê.
- `Stats::combine` là phép gộp, cộng số đơn và tổng tiền.
- Record bất biến ở cấp các thành phần primitive trong ví dụ. `combine` tạo record **mới**, không sửa một object `Stats` được dùng chung.
- Cả map và reduce đều không sửa Collection nguồn.
- Với các dữ liệu mẫu ở phần 9, kết quả là `Stats[orderCount=3, totalAmount=85000]`.

Đây là một ví dụ **value-based reduction** hợp lý cho parallel Stream. Đừng dùng một object `ArrayList` hoặc `HashMap` mutable làm identity chung rồi sửa nó trong accumulator: kiểu giảm ấy dễ vi phạm điều kiện hợp đồng của reduce khi chia nhóm.

## 8. reduce khác collect ở điểm nào?

**reduce**: phép tổng hợp giá trị, kết quả mới được hình thành bằng toán tử associative.

**collect**: phép rút gọn có tính mutable được thiết kế để tạo container, cho phép tích lũy có kiểm soát (với supplier/accumulator/combiner hoặc một Collector).

Phản ví dụ nên tránh:

~~~java
// KHÔNG NÊN dùng parallel reduce như thế:
// List<String> unsafe = words.parallelStream().reduce(
//     new ArrayList<String>(),
//     (list, word) -> { list.add(word); return list; },
//     (left, right) -> { left.addAll(right); return left; });
~~~

Ở đây mutable identity có thể được dùng làm đầu vào nhiều phần giảm; accumulator sửa tại chỗ và mất tính an toàn trong ngữ cảnh parallel. Có combiner không biến việc sửa identity dùng chung thành một reduction hợp lệ.

Nếu muốn danh sách mới:

~~~java
List<String> upper = words.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

Nếu cần một danh sách mutable hoặc Map được gộp theo khóa, thường dùng `collect(Collectors.toList())`, `collect(Collectors.groupingBy(...))` hoặc Collector phù hợp hơn.

Khi chỉ cần **đếm/tính tổng/tìm min/max**, cũng nên cân nhắc `count()`, `sum()`, `min()`, `max()`; sử dụng reduce tổng quát không phải mục tiêu tự thân.

## 9. Chương trình Java 17 hoàn chỉnh và stdout đã kiểm chứng

Tạo file **StreamReduceDemo.java**. Chương trình độc lập minh họa cả ba overload với dữ liệu cụ thể, trường hợp rỗng, tổng tiền và object thống kê:

~~~java
import java.util.List;
import java.util.Optional;

public class StreamReduceDemo {
    record Order(String code, int quantity, long unitPrice) {
        long amount() { return quantity * unitPrice; }
    }

    record Stats(long orderCount, long totalAmount) {
        Stats combine(Stats other) {
            return new Stats(
                    orderCount + other.orderCount,
                    totalAmount + other.totalAmount);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 4);
        int sum = numbers.stream().reduce(0, Integer::sum);
        int product = numbers.stream().reduce(1, (a, b) -> a * b);
        Optional<Integer> largest = numbers.stream().reduce(Integer::max);
        int emptySum = List.<Integer>of().stream().reduce(0, Integer::sum);
        Optional<Integer> emptyMax = List.<Integer>of().stream().reduce(Integer::max);

        System.out.println("sum=" + sum);
        System.out.println("product=" + product);
        System.out.println("largest=" + largest.orElseThrow());
        System.out.println("empty sum=" + emptySum);
        System.out.println("empty max present=" + emptyMax.isPresent());

        List<Order> orders = List.of(
                new Order("A", 2, 15_000),
                new Order("B", 1, 25_000),
                new Order("C", 3, 10_000)
        );

        long total = orders.stream()
                .map(Order::amount)
                .reduce(0L, Long::sum);

        Stats stats = orders.parallelStream()
                .map(order -> new Stats(1, order.amount()))
                .reduce(new Stats(0, 0), Stats::combine);

        List<String> names = List.of("An", "Binh", "Chi");
        int letterCount = names.parallelStream().reduce(
                0,
                (subtotal, name) -> subtotal + name.length(),
                Integer::sum);

        System.out.println("total=" + total);
        System.out.println("stats=" + stats);
        System.out.println("letters=" + letterCount);
        System.out.println("parallel sum=" +
                numbers.parallelStream().reduce(0, Integer::sum));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 StreamReduceDemo.java
java StreamReduceDemo
~~~

**Stdout đã được kiểm chứng qua biên dịch và thực thi:**

~~~text
sum=9
product=24
largest=4
empty sum=0
empty max present=false
total=85000
stats=Stats[orderCount=3, totalAmount=85000]
letters=9
parallel sum=9
~~~

Diễn giải:

1. `sum=9` là 2+3+4, identity bằng 0.
2. `product=24` là 2×3×4, identity bằng 1.
3. `largest=4` cho biết phép reduce không identity trả Optional có giá trị.
4. `empty sum=0` và `empty max present=false` cho thấy sự khác nhau của overload có identity và overload không identity trên Stream rỗng.
5. `total=85000` vì ba đơn có thành tiền lần lượt 30.000, 25.000, 30.000.
6. `stats=Stats[orderCount=3, totalAmount=85000]` thể hiện hai số liệu được tổng hợp trong một record mới.
7. `letters=9` vì độ dài của An, Binh, Chi là 2, 4, 3.
8. `parallel sum=9` minh họa phép cộng với identity đúng và phép gộp associative.

Record được hỗ trợ đầy đủ trong Java 17; các đoạn đã ghi chú là **minh họa riêng** không phải file chạy độc lập, trong khi file `StreamReduceDemo.java` là chương trình đầy đủ.

## 10. Những lỗi reduce thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng identity 0 với phép nhân | Tích trở thành 0 | Identity phải là 1 |
| Dùng identity không trung tính | Kết quả sai, đặc biệt khi chia nhóm | Chứng minh hai đẳng thức identity |
| Dùng phép trừ làm accumulator parallel | Kết quả phụ thuộc cách nhóm | Chọn phép kết hợp associative |
| Bỏ qua Optional rỗng của reduce không identity | Dễ giả định luôn có giá trị | Dùng `orElse...`/`orElseThrow...` đúng nghĩa |
| Dùng null làm kết quả rút gọn | Có thể gây lỗi NullPointerException | Thiết kế kiểu giá trị phù hợp |
| Sửa object identity mutable | Dễ sai với parallel, race hoặc mất phần tử | Dùng collect hoặc value-based reduce |
| Combiner trả một phía, bỏ phía kia | Mất tổng hợp từ một số nhóm | Gộp hai kết quả U đúng |
| Phép cộng double được coi chính xác mọi cách nhóm | Sai số làm tròn | Chọn thuật toán và kiểu số phù hợp |
| Cộng long/int có thể tràn nhưng không kiểm tra | Kết quả sai domain | Chọn kiểu lớn hơn/kiểm tra overflow |
| Dùng reduce thay mọi terminal operation | Code khó đọc, có thể boxing | Dùng sum, count, max, min khi phù hợp |
| Tái sử dụng cùng Stream sau reduce | IllegalStateException hoặc vi phạm hợp đồng | Tạo Stream mới từ nguồn |

### 10.1. Không phải phép nối nào cũng nên tự reduce

Ví dụ ghép chuỗi:

~~~java
String text = List.of("A", "B", "C").stream()
        .reduce("", String::concat);
// "ABC"
~~~

Nối chuỗi là một phép associative theo thứ tự các chuỗi, nhưng lặp lại String::concat có thể tạo nhiều chuỗi trung gian. Với danh sách lớn hoặc dấu phân cách, thường dùng `Collectors.joining(",")` thay vì tự viết reduce.

### 10.2. Reduce là terminal operation

Sau khi gọi `reduce`, instance Stream đã tiêu thụ, không dùng tiếp để gọi `count()` hoặc `toList()`. Nếu nguồn là Collection, tạo Stream mới khi cần tính toán khác.

### 10.3. Parallel không bảo đảm nhanh hơn

Việc chia source, tích lũy và kết hợp nhiều tổng phụ có chi phí. Với dữ liệu nhỏ, `parallelStream().reduce(...)` có thể chậm hơn `stream().reduce(...)`. Trước khi tối ưu, bảo đảm toán tử đáp ứng hợp đồng và đo bằng benchmark đại diện, không chỉ dựa vào cảm giác.

## 11. Checklist khi thiết kế một phép reduction

Hãy kiểm tra tuần tự:

1. Kết quả cần là **một giá trị** hay một container mutable?
2. Có terminal operation chuyên dụng `sum`, `count`, `max`, `min` rõ nghĩa hơn không?
3. Có **identity** thực sự trung tính không? Nếu không, dùng overload trả Optional.
4. Accumulator có **associative**, **stateless** và **non-interfering** không?
5. Nếu dùng overload ba đối số, combiner có nhận và gộp đúng **hai kết quả U** không?
6. `combiner(u, accumulator(identity,t))` có tương thích `accumulator(u,t)` không?
7. Có chia sẻ một object mutable giữa các nhóm tính không? Nếu có, xem lại hoặc đổi sang Collector.
8. Nguồn rỗng, một phần tử, nhiều phần tử và dữ liệu biên cho kết quả gì?
9. Tính toán có nguy cơ tràn số hoặc sai số làm tròn không?
10. Pipeline có thể chạy parallel không, và liệu hiệu năng thực tế có chứng minh việc dùng parallel là cần thiết?

## 12. Bài tập tự kiểm tra

**Bài 1.** `List.of(5,6,7).stream().reduce(0,Integer::sum)` trả gì? **Đáp án:** 18, vì 0 là identity phép cộng.

**Bài 2.** `List.<Integer>of().stream().reduce(Integer::max)` trả gì? **Đáp án:** `Optional.empty()`, vì không có phần tử lớn nhất.

**Bài 3.** Vì sao `reduce(0,(a,b)->a*b)` không hợp lệ để tính tích? **Đáp án:** 0 không phải identity của phép nhân; cần 1.

**Bài 4.** Trong `Stream<String>` được reduce về `Integer`, combiner nhận hai kiểu gì? **Đáp án:** hai Integer tổng hợp, không phải hai String.

**Bài 5.** Một phép trừ `(a,b)->a-b` chạy đúng theo mong đợi trên một nguồn tuần tự có đủ an toàn để bật parallel không? **Đáp án:** không, vì không associative.

**Bài 6.** Có thể dùng reduce với record `Stats(orderCount,totalAmount)` không? **Đáp án:** có, nếu identity và combine thực hiện phép gộp hai trường một cách associative, không sửa trạng thái chia sẻ.

**Bài 7.** Vì sao nên dùng collect khi tạo một danh sách mutable? **Đáp án:** collector được thiết kế cho mutable reduction; dùng reduce với identity mutable sửa tại chỗ dễ vi phạm hợp đồng.

**Bài 8.** Với ba chuỗi độ dài 2, 4, 3, `reduce(0,(sum,s)->sum+s.length(),Integer::sum)` trả gì? **Đáp án:** 9.

## 13. Tài liệu chính thức

- [Java SE 17 — Stream.reduce và các hợp đồng identity/associativity/combiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html).
- [Java SE 17 — BiFunction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiFunction.html).
- [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

**Kết luận:** `reduce` kết hợp nhiều phần tử thành **một kết quả** theo toán tử có hợp đồng rõ ràng. Overload có identity trả kết quả khởi đầu nếu Stream rỗng; overload không identity trả `Optional<T>`; overload ba đối số hỗ trợ kiểu kết quả U khác kiểu nguồn T và dùng combiner để hợp nhất các kết quả từng phần. Thiết kế reduction đúng cần **identity trung tính, phép gộp associative, hàm stateless/non-interfering và xử lý nguồn rỗng minh bạch**, đặc biệt khi dùng parallel Stream.

# Parallel Streams: Combiner, identity và lỗi reduction khi chạy song song

## 1. Bài toán: vì sao cùng một `reduce` lại có thể cho kết quả khác khi chạy song song?

Một phép **reduction** (rút gọn/tổng hợp) chuyển nhiều phần tử của stream thành một kết quả: tổng, giá trị lớn nhất, thống kê, hay cấu trúc dữ liệu tổng hợp. Với stream tuần tự, ta dễ hình dung một biến tích lũy chạy từ trái sang phải:

~~~text
Stream:      [2, 4, 6, 8]
identity:     0
tích lũy:    0 → 2 → 6 → 12 → 20
kết quả:    20
~~~

Nhưng `parallelStream()` có thể chia dữ liệu thành nhiều phần, xử lý từng phần riêng, rồi **ghép các kết quả trung gian**. Khái niệm ghép đó là **combiner**. Mọi phần có thể được khởi tạo với **identity** (phần tử trung hòa).

~~~text
Stream:           [2, 4]             [6, 8]
                     │                  │
identity = 0      0+2+4 = 6        0+6+8 = 14
                     └───── combiner ────┘
                                6+14
                                 │
                                20
~~~

Hình trên là **một cách phân hoạch để giải thích**, không cam kết số nhóm, thứ tự thread, kích thước nhóm hay cách phân hoạch thực tế. Java có quyền thay đổi các quyết định triển khai này. Nếu phép tính đáp ứng đúng hợp đồng của `reduce`, kết quả không phụ thuộc cách chia và ghép; nếu vi phạm, parallel có thể bộc lộ lỗi mà chạy tuần tự chưa thấy.

**Ba câu hỏi quyết định correctness:**

1. **Identity có thực sự trung hòa không?** Khi ghép với một kết quả bất kỳ, nó phải giữ nguyên kết quả đó.
2. **Combiner có kết hợp được theo các nhóm khác nhau không?** Việc đổi cách đặt ngoặc không được đổi kết quả toán học mong muốn.
3. **Accumulator và combiner có tương thích không?** Kết quả gom một phần tử vào kết quả trung gian phải phù hợp với cách tạo phần trung gian rồi ghép.

Đây là bài về **Java Stream API và Java concurrency nói chung**. Các quy tắc áp dụng cả khi stream chạy trong nhiều thread, không phụ thuộc framework.

## 2. Ba biến thể `Stream.reduce` và vai trò của combiner

### 2.1. `reduce(BinaryOperator<T>)` — không khai báo identity

~~~java
Optional<Integer> max = Stream.of(2, 4, 6, 8)
        .parallel()
        .reduce(Integer::max);
~~~

Mỗi phần tử có thể đóng vai trò kết quả khởi đầu của một nhóm. Vì stream có thể rỗng và không có identity do caller cung cấp, kết quả trả về `Optional<T>`: rỗng nếu stream rỗng. Toán tử nhị phân vẫn phải **associative** và stateless/non-interfering để được phép regroup đúng. Với `Integer::max`, `max(max(a,b),c) == max(a,max(b,c))` nên có thể ghép nhóm an toàn.

Không gọi `Optional.get()` một cách vô điều kiện nếu stream có thể rỗng; dùng `orElseThrow()` khi dữ liệu bắt buộc phải có, hoặc `orElse(...)` cho fallback hợp lệ.

### 2.2. `reduce(identity, BinaryOperator<T>)` — một toán tử cho tích lũy và ghép

~~~java
int sum = Stream.of(2, 4, 6, 8)
        .parallel()
        .reduce(0, Integer::sum);
~~~

`0` là identity của phép cộng; `Integer::sum` vừa tích lũy trong từng nhóm, vừa ghép các nhóm. Kiểu kết quả là `T` (không phải `Optional<T>`). Nếu stream rỗng, nó trả identity `0`.

Điều kiện của overload này:

- `accumulator` là hàm hai đối số cùng kiểu `T`, trả `T`, ví dụ phép cộng.
- Phải **associative**, không phụ thuộc thứ tự đặt ngoặc: `op(op(a,b),c) == op(a,op(b,c))`.
- `identity` phải là phần tử trung hòa **hai phía**: `op(identity,x) == x` và `op(x,identity) == x`.
- Hàm phải **non-interfering**, **stateless**: không thay đổi nguồn stream và không dựa vào trạng thái mutable thay đổi giữa các lượt gọi.

Đừng hiểu identity như “giá trị khởi động **một lần duy nhất cho toàn bộ phép giảm**”. Khi xử lý song song, các phần khác nhau đều có thể bắt đầu từ identity. Chọn `10` cho phép cộng vì muốn “cộng thêm 10 một lần” là lỗi contract.

### 2.3. `reduce(identity, accumulator, combiner)` — đầu vào và kết quả khác kiểu

Chữ ký tổng quát:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Trong đó:

- `T` là kiểu của **phần tử stream**.
- `U` là kiểu của **kết quả tích lũy**; có thể khác `T`.
- `identity` là giá trị kết quả rỗng ban đầu, kiểu `U`.
- `accumulator` nhận một `U` và một phần tử `T`, trả `U` sau khi gộp phần tử.
- `combiner` ghép **hai kết quả `U`** đến từ những nhánh khác nhau.

Ví dụ đếm tổng số ký tự của các chuỗi:

~~~java
int length = Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(
                0,                                // U = Integer, identity
                (total, text) -> total + text.length(),  // (U, T) -> U
                Integer::sum);                    // (U, U) -> U
~~~

Kết quả là `6`. Combiner rất cần khi `T = String` nhưng `U = Integer`; không thể dùng một `BinaryOperator` cùng kiểu để thực hiện cả hai vai trò.

**Điều kiện đặc biệt của overload ba đối số** được Java Stream API yêu cầu:

- Combiner phải associative.
- Identity phải trung hòa cho combiner: `combiner(identity, u) == u` (và trong thực tế cần phép ghép trung hòa đúng phía cho mọi kết quả).
- **Compatibility law:**  
  `combiner(u, accumulator(identity, t)) == accumulator(u, t)`  
  với mọi kết quả trung gian hợp lệ `u` và phần tử `t`.
- Accumulator/combiner phải non-interfering và stateless. Một hàm trả đối tượng mutable nhưng chỉnh sửa chung object từ nhiều nhánh sẽ vi phạm ý nghĩa của reduction.

Compatibility law nói rằng: “thêm `t` vào kết quả hiện có” phải tương đương với “tự tích lũy `t` từ identity rồi ghép kết quả đó”. Đây là điều kiện thường bị quên khi lập trình viên viết đúng accumulator nhưng combiner khác nghĩa.

## 3. Identity không phải giá trị khởi đầu tùy ý

Identity là **phần tử trung hòa** của phép ghép, không phải một tham số điều chỉnh tổng.

| Phép toán | Identity hợp lệ | Giải thích |
|---|---|---|
| Cộng số nguyên (không xét tràn) | `0` | `0 + x = x = x + 0` |
| Nhân số nguyên (không xét tràn) | `1` | `1 × x = x = x × 1` |
| Ghép chuỗi với `String::concat` | `""` | Chuỗi rỗng không thêm ký tự |
| Ghép tập hợp bằng phép hợp | Tập rỗng | Hợp với tập rỗng không đổi tập |
| Giá trị lớn nhất của mọi `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Giá trị nhỏ nhất của mọi `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

Khi biết dữ liệu không rỗng, `reduce(Integer::max)` trả `Optional` thường diễn đạt ý định rõ hơn identity nhân tạo cho `max`. Với kiểu `double` và NaN, ±0.0, hoặc một miền đặc biệt, cần kiểm tra semantics cụ thể của toán tử thay vì áp bảng trên một cách máy móc.

### Ví dụ sai: `reduce(10, Integer::sum)` để cộng “phụ phí 10”

Nếu dữ liệu là `[1, 2, 3, 4]` thì chạy tuần tự:

~~~text
10 + 1 + 2 + 3 + 4 = 20
~~~

Giả sử **chỉ để minh họa** stream song song được tách thành hai nhóm, mỗi nhóm bắt đầu từ identity `10`:

~~~text
Nhóm A: 10 + 1 + 2 = 13
Nhóm B: 10 + 3 + 4 = 17
Ghép:  13 + 17 = 30
~~~

`10` không phải identity của phép cộng, nên kết quả phụ thuộc số phần được phân hoạch. Số nhóm và kết quả số cụ thể trong runtime **không được API bảo đảm**. Không viết unit test “parallel luôn ra 30” cho ví dụ này; con số 30 chỉ là giả định của phép chia nhóm bên trên.

Cách đúng để cộng phụ phí **một lần**:

~~~java
int total = 10 + numbers.parallelStream().reduce(0, Integer::sum);
~~~

`numbers` là `Collection<Integer>` đã định nghĩa trong ứng dụng. Sau `reduce(0, sum)`, phép cộng `10` xảy ra ngoài phép giảm đúng một lần. Với stream số nguyên có thể dùng `mapToInt(Integer::intValue).sum()` rồi cộng phụ phí.

### Identity là một object mutable: bẫy nguy hiểm hơn

Code **sai, chỉ để phân tích, không chạy**:

~~~java
List<String> identity = new ArrayList<>();

List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                identity,
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

Vấn đề: `identity` là **cùng một object `ArrayList`** được truyền cho các nhánh; `accumulator` thay đổi object đó bằng `add`, còn combiner tiếp tục thay đổi bằng `addAll`. Identity không còn bất biến/trung hòa theo yêu cầu; các nhánh có thể sửa chung danh sách gây data race, lặp phần tử, sai số lượng hoặc lỗi runtime. **Không sửa bằng cách thay `ArrayList` thành danh sách synchronized** rồi coi reduction đã đúng: khóa có thể tránh một phần race nhưng không giải quyết việc một object được dùng làm identity cho nhiều nhánh và bị ghép với chính nó.

Để gom danh sách, dùng **mutable reduction `collect`** (phần 7), vì nó có `supplier` tạo container riêng cho các nhánh.

## 4. Combiner là phép ghép kết quả từng phần, không phải hàm “cho có”

Trong phép giảm ba tham số sau, accumulator và combiner đúng cùng một ngữ nghĩa:

~~~java
record Stats(long count, long total) {
    Stats add(int value) {
        return new Stats(count + 1, total + value);
    }
    Stats merge(Stats other) {
        return new Stats(count + other.count, total + other.total);
    }
}

Stats stats = values.parallelStream().reduce(
        new Stats(0, 0), // identity
        Stats::add,      // accumulator (Stats, Integer) -> Stats
        Stats::merge);   // combiner    (Stats, Stats) -> Stats
~~~

Đây là **đoạn trích trong class**, `values` phải là `Collection<Integer>`; chương trình độc lập ở phần 6 có đầy đủ khai báo và code chạy được. `Stats` là record **immutable**: mỗi lần `add` và `merge` tạo một đối tượng mới, nên không chia sẻ mutable accumulator. Combiner cộng số lượng và tổng, giữ đúng cấu trúc kết quả.

Ví dụ dữ liệu `[2,4,6,8]`, hai nhóm có thể tổng hợp thành:

~~~text
Nhóm A: Stats(count=2, total=6)
Nhóm B: Stats(count=2, total=14)

merge(A, B) = Stats(count=4, total=20)
average = 20.0 / 4 = 5.0
~~~

Để tính average đúng, cần gộp **count và total** trước rồi mới chia. Trung bình của hai trung bình không luôn bằng trung bình của toàn bộ dữ liệu, vì kích thước nhóm có thể khác nhau:

~~~text
Nhóm A: [1]          average = 1, size = 1
Nhóm B: [5, 9, 13]   average = 9, size = 3
Sai: (1 + 9) / 2 = 5
Đúng: (1 + 5 + 9 + 13) / 4 = 7
~~~

Thay vì chứa average của mỗi nhóm rồi ghép bằng trung bình cộng, hãy mang theo `sum` và `count`, cuối cùng mới tính average.

### Combiner sai: “chỉ trả nhánh trái”

~~~java
// SAI — loại bỏ toàn bộ kết quả ở nhánh phải
(left, right) -> left
~~~

Code này có thể tình cờ cho kết quả đúng ở một trường hợp tuần tự đơn giản nếu combiner ít hoặc không được gọi. Trong parallel, dữ liệu của các nhánh có thể bị mất; vi phạm compatibility law.

### Combiner sai: dùng phép trừ để ghép

~~~java
// SAI — phép trừ không associative
(left, right) -> left - right
~~~

Vì `(8 - 3) - 1 = 4` nhưng `8 - (3 - 1) = 6`, đổi nhóm có thể đổi kết quả. Chỉ “giữ thứ tự phần tử” không cứu được phép giảm có grouping khác nhau. `Stream` có encounter order vẫn được phép regroup khi reduction song song.

### Combiner đúng nhưng accumulator sai nghĩa

Ngay cả khi `combiner = Integer::sum` là associative, `accumulator` phải cho kết quả có thể ghép với nó. Ví dụ sau **không tương thích**:

~~~java
// SAI: accumulator nhân 2 ở mỗi lượt, combiner lại cộng.
.reduce(0, (total, n) -> total * 2 + n, Integer::sum)
~~~

Nếu thêm `n` vào một phần tổng `u`, kết quả là `2u+n`; nhưng tính `accumulator(0,n)=n` rồi ghép vào `u` bằng `sum` cho `u+n`. Hai vế khác nhau khi `u != 0`. Code có thể chạy tuần tự nhưng không phải reduction ba tham số hợp lệ cho parallel.

## 5. Associativity khác với commutativity và encounter order

**Associative (kết hợp)** là thay đổi cách đặt ngoặc vẫn giữ kết quả:

~~~text
(a ◦ b) ◦ c = a ◦ (b ◦ c)
~~~

**Commutative (giao hoán)** là đổi chỗ phần tử vẫn giữ kết quả:

~~~text
a ◦ b = b ◦ a
~~~

Phép nối chuỗi **associative nhưng không commutative**: `("a"+"b")+"c" == "a"+("b"+"c") == "abc"`, nhưng `"a"+"b" != "b"+"a"`. Phép toán phù hợp với reduction của stream có thứ tự không bắt buộc giao hoán trong mọi trường hợp; kết quả đúng còn phụ thuộc contract bảo toàn encounter order của phép reduction và nguồn stream. Đừng dùng `unordered()` hoặc một concurrent collector có `UNORDERED` nếu thứ tự là một phần ý nghĩa kết quả.

Ví dụ `[a,b,c]` nối chuỗi đúng thành `"abc"` trong các cách ghép hợp lệ giữ thứ tự. Nhưng một parallel `forEach` ghi vào `StringBuilder` chung không có đảm bảo giữ thứ tự và không an toàn thread; đó không phải reduction đúng.

**Số thực dấu phẩy động:** toán học coi phép cộng là associative, nhưng IEEE 754 với giới hạn độ chính xác có thể làm hai cách đặt ngoặc cho kết quả khác nhau:

~~~text
(1e16 + (-1e16)) + 1.0 = 1.0
1e16 + ((-1e16) + 1.0) = 0.0
~~~

Vì thế tổng `double` tính song song và tuần tự có thể khác vài bit, kể cả dùng phép cộng, và không được kiểm tra bằng `==` nếu hợp đồng cho phép sai số. Với nghiệp vụ cần độ chính xác thập phân, hãy cân nhắc `BigDecimal` và lựa chọn rounding/scale có định nghĩa; hoặc thiết kế phép tổng hợp ổn định số học theo yêu cầu chuyên môn. `BigDecimal` cũng cần chú ý `MathContext` và việc làm tròn có thể phá tính kết hợp.

**Tràn số nguyên:** `int`/`long` dùng cộng wraparound theo bề rộng bit; nếu nghiệp vụ cần tổng chính xác trong miền số lớn, `Integer::sum` có thể không phù hợp dù thuộc tính kết hợp modulo vẫn đúng. Dùng kiểu đủ rộng, `BigInteger`, hoặc phép kiểm tra overflow tùy yêu cầu. Không đánh đồng “cùng kết quả modulo” với “đúng giá trị nghiệp vụ”.

## 6. Ví dụ Java 17+ chạy độc lập, kết quả xác định

Tạo file **`ReductionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class ReductionDemo {
    record Stats(long count, long total) {
        Stats add(int n) {
            return new Stats(count + 1, total + n);
        }
        Stats merge(Stats other) {
            return new Stats(count + other.count, total + other.total);
        }
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 6, 8);

        int sum = values.parallelStream().reduce(0, Integer::sum);
        System.out.println("sum=" + sum);

        Stats stats = values.parallelStream().reduce(
                new Stats(0, 0),
                Stats::add,
                Stats::merge);
        System.out.println("stats=" + stats.count() + "/" + stats.total());

        int length = Stream.of("a", "bb", "ccc")
                .parallel()
                .reduce(0, (n, s) -> n + s.length(), Integer::sum);
        System.out.println("length=" + length);

        int max = values.parallelStream().reduce(Integer::max).orElseThrow();
        System.out.println("max=" + max);

        List<Integer> collected = values.parallelStream().collect(
                ArrayList::new, ArrayList::add, ArrayList::addAll);
        System.out.println("collected=" + collected.size());

        boolean identityTen = 10 + 5 == 5 && 5 + 10 == 5;
        System.out.println("identityTen=" + identityTen);

        boolean subtractionAssociative = (8 - 3) - 1 == 8 - (3 - 1);
        System.out.println("subtractionAssociative=" + subtractionAssociative);

        double left = (1e16 + -1e16) + 1.0;
        double right = 1e16 + (-1e16 + 1.0);
        System.out.println("floatingGroupingEqual=" + (left == right));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ReductionDemo.java
java ReductionDemo
~~~

**stdout:**

~~~text
sum=20
stats=4/20
length=6
max=8
collected=4
identityTen=false
subtractionAssociative=false
floatingGroupingEqual=false
~~~

Giải thích:

1. `reduce(0, Integer::sum)`: identity `0` đúng, phép cộng số nguyên hợp lệ về tính kết hợp trong miền biểu diễn modulo, kết quả `20`.
2. `Stats::add` chuyển `Integer` thành cấu trúc gồm số lượng và tổng; `Stats::merge` là combiner associative. Kết quả `count=4`, `total=20`; trung bình là `20/4 = 5`.
3. `length` dùng overload ba đối số, phân biệt `T=String` và `U=Integer`; kết quả `1+2+3 = 6`.
4. `reduce(Integer::max)` không cần identity, trả `Optional`, rồi lấy giá trị tối đa `8`.
5. `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` cấp các container mutable riêng, sau đó ghép; có đúng bốn phần tử. Chương trình chỉ in kích thước, không phụ thuộc cách chia việc nội bộ.
6. Ba dòng cuối kiểm tra luật: `10` không trung hòa cho phép cộng; phép trừ không kết hợp; phép cộng `double` có thể bị ảnh hưởng bởi cách đặt ngoặc.

Ví dụ **không cố in kết quả thực tế của một reduction sai trên parallel stream** vì kết quả đó có thể thay đổi theo triển khai và phân hoạch. Thay vào đó nó kiểm tra chính các quy tắc bắt buộc — một kiểu kiểm thử đáng tin cậy hơn khi dạy correctness.

## 7. Khi nào dùng `collect` thay vì `reduce`?

**Reduce** tự nhiên với tổng hợp bằng giá trị **immutable**: số nguyên, `BigInteger`, record `Stats` mới cho mỗi bước, hoặc một giá trị có phép kết hợp rõ ràng. **Collect** sinh ra để gom vào **container mutable** được tạo độc lập cho mỗi nhánh.

Với overload ba hàm:

~~~java
List<String> result = names.parallelStream().collect(
        ArrayList::new,  // supplier: tạo container mới khi cần
        ArrayList::add,  // accumulator: thêm một tên vào container của nhánh
        ArrayList::addAll // combiner: ghép container nhánh khác
);
~~~

`names` là `Collection<String>` của ứng dụng; đây là đoạn minh họa không độc lập. Cấu trúc:

- **Supplier:** cấp phát collection mới, để các task có accumulator riêng.
- **Accumulator:** cập nhật container cục bộ.
- **Combiner:** ghép container khi join những nhánh.
- **Không cần mutate chung một `ArrayList` từ nhiều thread:** phép thu gom đúng giữ ranh giới các container trung gian.

Đây không phải lời hứa rằng mọi `Collector` tự viết đều thread-safe; một collector `CONCURRENT` có thể cho phép nhiều thread đóng góp vào một container chung, lúc đó accumulator và container phải thực sự hỗ trợ truy cập đồng thời. `Collector.Characteristics.UNORDERED` cho biết thứ tự kết quả không quan trọng đối với collector; `CONCURRENT` là tính chất riêng, không được tự gắn vào collector chưa đáp ứng.

Khi không cần thuật toán custom, ưu tiên terminal operation hoặc collector có sẵn:

~~~java
// Những đoạn code minh họa khi numbers là Stream<Integer>.
long count = numbers.count();

// Khi source là Collection<Integer>, tạo stream mới cho mỗi terminal operation:
int sum = source.parallelStream().mapToInt(Integer::intValue).sum();

IntSummaryStatistics summary = source.parallelStream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

List<Integer> list = source.parallelStream().toList();
~~~

`source` là `Collection<Integer>` đã có, cần `import java.util.IntSummaryStatistics;`. `Stream.toList()` (Java 16+) trả danh sách **unmodifiable**, khác với việc tự tạo `ArrayList` bằng `collect`. Một stream chỉ dùng được cho **một terminal operation**: không gọi `count()` rồi lại `sum()` trên chính stream đã tiêu thụ.

Nếu việc kết hợp dữ liệu tốn nhiều phép cấp phát, primitive streams (`IntStream`, `LongStream`, `DoubleStream`) và collector tối ưu có thể hiệu quả hơn record immutable tạo mới ở mỗi phần tử. Chọn theo profiling, không chỉ theo cú pháp ngắn.

### Tránh vừa giảm vừa mutate biến ngoài

~~~java
// SAI: ghi vào biến mutable ngoài stream, race condition khi chạy song song.
int[] sum = {0};
values.parallelStream().forEach(n -> sum[0] += n);
~~~

Kể cả `values` là danh sách immutable, `sum[0]` vẫn là shared mutable state. Phép `+=` không atomic, một số cập nhật có thể bị mất. Giải pháp chuẩn:

~~~java
int sum = values.parallelStream().mapToInt(Integer::intValue).sum();
~~~

Không dùng side effect chỉ để “có kết quả”; reduction biểu diễn ý định tổng hợp rõ ràng hơn và để runtime tự điều phối.

## 8. Lỗi reduction song song: nhận diện và xử lý theo nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Kết quả khác giữa sequential/parallel | Identity sai hoặc phép tính không associative/không tương thích | Kiểm tra ba luật identity, associativity, compatibility |
| Dữ liệu bị lặp, mất hoặc `ArrayList` lỗi | Mutate một object identity chung khi reduce | Dùng `collect` có supplier tạo container riêng |
| Kết quả thiếu dữ liệu từ các nhánh | Combiner bỏ qua một nhánh, ví dụ `(a,b)->a` | Viết combiner gộp đầy đủ và đúng nghĩa |
| Count/tổng đúng nhưng average sai | Trung bình của trung bình, không cân theo số lượng | Gộp `(sum,count)` rồi mới tính average |
| Kết quả float khác một ít | Rounding và grouping thay đổi | Dùng phép so sánh có tolerance hoặc thuật toán số thích hợp |
| Kết quả có dấu hiệu ngẫu nhiên | Callback dùng mutable state bên ngoài, random/time/I/O side effect | Dùng hàm stateless, thuần dữ liệu; tách side effect |
| Kết quả tuần tự đúng nhưng parallel rất chậm | Tác vụ quá nhỏ, splitting/combining tốn kém, boxing, contention | Benchmark với dữ liệu thật, dùng primitive streams và giảm allocation |
| Lỗi bất ngờ từ mapper/accumulator | Hàm ném exception trong task; lỗi nổi lên ở terminal operation | Theo dõi nguyên nhân, không coi reduction là hệ thống nuốt lỗi |
| Stream rỗng trả giá trị lạ | Identity được trả về theo hợp đồng, hoặc `Optional.empty` | Quy định semantics cho đầu vào rỗng |
| Không thể tái sử dụng stream | Terminal operation đã tiêu thụ pipeline | Tạo stream mới từ nguồn trước mỗi lần reduce |

### Exception khi thực thi parallel

Nếu lambda của accumulator/combiner ném exception, terminal operation có thể hoàn thành bằng exception đó (hoặc exception được bọc theo đường truyền nội bộ). Các task khác có thể đã được bắt đầu; không dựa vào “tất cả dừng tức thì” hoặc thứ tự ném lỗi khi nhiều task cùng thất bại.

Đặc biệt, parallel reduction **không có transaction**: nếu trong lambda có gọi API ngoài, ghi file hoặc thay đổi database, việc một nhánh lỗi không rollback side effect ở nhánh khác. Vì thế lambda reduction nên là phép biến đổi dữ liệu thuần, và việc ghi side effect nên được xử lý ở tầng có hợp đồng rõ ràng.

### Kết quả `null` và nguồn dữ liệu có `null`

`Stream.reduce(BinaryOperator)` trả `Optional` và không chấp nhận kết quả cuối `null` như một phần tử hợp lệ của `Optional`; các phép toán hoặc mapper phụ thuộc non-null có thể gây `NullPointerException`. Với stream chứa `null`, trước tiên phải xác định nghiệp vụ: lọc `Objects::nonNull`, chuyển sang giá trị sentinel hợp lệ, hoặc báo lỗi sớm. Không dùng identity `null` rồi suy đoán nó trung hòa với mọi toán tử.

## 9. Kiểm chứng luật trước khi bật parallel

Hãy thử một mô hình **phân hoạch độc lập với runtime**. Với tập `[a,b,c,d]`, viết kiểm tra:

~~~text
Reduce tuần tự:    fold(identity, [a,b,c,d])
Chia 2 nhóm:       combine(fold(identity,[a,b]), fold(identity,[c,d]))
Chia 3 nhóm:       combine(combine(fold(identity,[a]), fold(identity,[b,c])), fold(identity,[d]))
Dữ liệu rỗng:      identity
~~~

Nếu kết quả khác nhau, phải sửa luật trước khi chạy benchmark. Với phép nối chuỗi có thứ tự, kiểm tra cả thứ tự ghép nhóm; với số thực, xác định sai số chấp nhận được.

Ví dụ kiểm tra law ở dạng pseudocode Java:

~~~java
// Không phải chương trình độc lập; op là BinaryOperator<T>,
// identity và a,b,c là các giá trị mẫu của cùng kiểu T.
boolean leftIdentity = op.apply(identity, a).equals(a);
boolean rightIdentity = op.apply(a, identity).equals(a);
boolean associative = op.apply(op.apply(a, b), c)
        .equals(op.apply(a, op.apply(b, c)));
~~~

Với kết quả có thể `null`, dùng `Objects.equals(...)` để tránh NPE khi kiểm thử. Phép test vài bộ dữ liệu chỉ tìm ra phản ví dụ, **không chứng minh** luật đúng trên mọi giá trị. Kiểm thử property-based/randomized inputs, các kích thước nhóm khác nhau và edge cases (rỗng, một phần tử, số cực trị, dữ liệu trùng, null nếu được phép) có giá trị hơn một lần chạy `parallelStream()` thấy “đúng”.

Đối với overload ba tham số, kiểm tra thêm:

~~~java
// Pseudocode, không tự chạy nếu thiếu u, t, identity,
// accumulator và combiner.
U left = combiner.apply(u, accumulator.apply(identity, t));
U right = accumulator.apply(u, t);
boolean compatible = Objects.equals(left, right);
~~~

Một số giá trị `U` có semantics về tương đương khác `equals`; khi kiểm thử phải định nghĩa đúng tiêu chí tương đương của kết quả nghiệp vụ.

### Quy trình điều tra một lỗi parallel thực tế

1. Tạo input nhỏ, cố định; chạy sequential để hiểu kết quả mong muốn.
2. Viết rõ identity, accumulator và combiner trong ba hàm/biểu thức riêng.
3. Kiểm tra identity hai phía, associativity, compatibility, tính stateless và dữ liệu shared.
4. Tính tay vài cách partition khác nhau; xác minh kết quả không đổi.
5. Chạy parallel nhiều lần, thử input rỗng, có phần tử lặp, và kích thước thay đổi; chỉ dùng các kết quả như bằng chứng bổ sung.
6. Nếu có mutable accumulation, chuyển sang `collect` hoặc thiết kế kết quả immutable.
7. Đo hiệu năng với dữ liệu đại diện, bao gồm thời gian tách nhóm, boxing, combine và tương tranh tài nguyên.

### Parallel không mặc nhiên nhanh hơn

`parallelStream()` thường tận dụng cơ chế Fork/Join của JVM; cách sử dụng pool và scheduling còn tùy ngữ cảnh thực thi. Với stream nhỏ, chi phí phân việc, tạo task và ghép kết quả có thể lớn hơn phép tính. Với `reduce` tạo nhiều object immutable, allocation/GC cũng đáng kể. Khi nguồn không tách được tốt, xử lý song song có thể kém hiệu quả.

Không dùng `parallel()` để “chữa” một vòng lặp chậm trước khi đo. Phép reduction trước hết phải **đúng về đại số**, sau đó mới đánh giá lợi ích song song.

## 10. Chọn công cụ cho từng yêu cầu

| Yêu cầu | Cách Java thường phù hợp |
|---|---|
| Tính tổng `int`/`long` đơn giản | Primitive stream `sum()` hoặc `reduce(0, sum)` đúng identity |
| Tìm max/min có thể không có phần tử | `reduce(Integer::max)` hoặc primitive `max()` trả Optional |
| Tổng hợp nhiều thống kê | `summaryStatistics()` hoặc record immutable `(count,sum,...)` với combiner |
| Đếm ký tự từ `Stream<String>` thành `Integer` | `reduce(0, accumulator, Integer::sum)` |
| Gom danh sách/set/map mutable | `collect(...)` hoặc `Collectors.toList()/toSet()/toMap()` |
| Gộp chuỗi lớn | `Collectors.joining()` thường phù hợp hơn lặp `String::concat` |
| Kết quả yêu cầu thứ tự cụ thể | Giữ ordered stream và collector có hợp đồng phù hợp |
| Cần làm side effect cho từng phần tử | Xác định cơ chế đồng bộ và vòng đời riêng; không dùng shared mutation trong `reduce` |

**Câu hỏi tự kiểm tra:**

- Tại sao `reduce(10, Integer::sum)` sai khi muốn thêm 10 đúng một lần? Vì `10` có thể làm identity cho **nhiều** nhánh; identity của cộng phải là `0`.
- Vì sao `(a,b)->a-b` không phù hợp parallel reduction? Vì phép trừ không associative; grouping khác nhau tạo kết quả khác.
- Nếu accumulator gom dữ liệu thành một `ArrayList` và mutate nó, có nên dùng object identity chung trong `reduce`? Không. Dùng `collect` với supplier tạo container riêng.
- `combiner` có thể bỏ qua vì dữ liệu thử chỉ có một phần tử? Không. Phải đúng với mọi cách phân hoạch hợp lệ.
- Tại sao average không thể ghép bằng average của average? Vì kích thước nhóm khác nhau; cần gộp tổng và số lượng.
- `String::concat` không commutative, vậy có dùng được khi giảm stream có thứ tự? Có nếu phép ghép giữ đúng encounter order; phép nối là associative, thứ tự phải được bảo toàn theo contract.
- Tại sao parallel sum của `double` có thể khác sequential sum? Bởi giới hạn độ chính xác và rounding khiến phép cộng thực tế không associative tuyệt đối.

## 11. Tài liệu Java chuẩn để tra cứu

- [Java 21 Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html) — hợp đồng `reduce` ba overload, associativity, identity, compatibility, yêu cầu stateless/non-interfering.
- [Java 21 package java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html) — nguyên lý reduction, mutable reduction, parallelization, side effects.
- [Java 21 Collector API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html) — supplier, accumulator, combiner và characteristics.
- [Java 21 Collectors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html) — các collector chuẩn, joining, grouping, thống kê.

Một parallel reduction đúng không được dựa vào việc JVM tình cờ chạy theo thứ tự đã quan sát ở một lần test. **Identity trung hòa + phép ghép associative + accumulator/combiner tương thích + không chia sẻ mutable state sai cách** là nền tảng để cùng một phép tính có ý nghĩa như nhau ở sequential và parallel.

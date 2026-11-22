# Reduction trong Java Streams: phép tổng hợp và yêu cầu associativity

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích reduction (phép tổng hợp) biến nhiều phần tử của Stream thành một kết quả như tổng, tích, giá trị lớn nhất hoặc thống kê.
2. Phân biệt identity, accumulator và combiner trong các overload của Stream.reduce(...).
3. Chứng minh vì sao phép kết hợp phải có tính **associative** để reduction có thể chia nhỏ và tính song song đúng.
4. Nhận ra sai lầm khi dùng phép trừ, identity sai, trạng thái dùng chung, phép làm tròn hoặc cấu trúc mutable.
5. Chọn reduce, collect hay các terminal operation chuyên biệt phù hợp với yêu cầu thực tế.

Bài tập trung vào API Stream được giới thiệu ở Java 8 và **vẫn là API hiện hành trong các phiên bản Java hiện đại**. Ví dụ độc lập sử dụng Java 17 trở lên; không dựa vào API đã lỗi thời.

## 1. Reduction là gì?

Reduction (còn gọi là *fold*) là quá trình kết hợp các phần tử thành một kết quả tổng hợp:

- Danh sách số → tổng, tích, min, max.
- Danh sách chuỗi → chuỗi được ghép.
- Danh sách đối tượng → một thống kê bất biến, chẳng hạn số lượng và tổng giá trị.

Ví dụ, với các số [2, 3, 5] và phép cộng:

~~~text
         2    3    5
         \    |    /
          cộng dồn
              |
             10
~~~

Một vòng lặp có thể giữ biến tổng và cập nhật tuần tự. Stream.reduce diễn đạt phép toán tổng hợp ở mức cao hơn và cho phép thư viện thực hiện theo nhiều cách, bao gồm chia thành các phần rồi ghép kết quả. Tính đúng đắn của phép chia và ghép đó phụ thuộc vào các quy tắc đại số bên dưới.

Các thao tác reduction là terminal operation: chúng kích hoạt pipeline Stream và tạo ra kết quả. Một Stream đã được tiêu thụ không được tái sử dụng để chạy terminal operation lần nữa; hãy tạo Stream mới từ nguồn khi cần.

## 2. Associativity: điều kiện cốt lõi

Một phép nhị phân op là **associative (có tính kết hợp)** nếu với mọi a, b, c thuộc miền giá trị hợp lệ:

~~~text
op(op(a, b), c) = op(a, op(b, c))

Viết ngắn: (a op b) op c = a op (b op c)
~~~

Điều kiện này nói rằng **được đổi cách đặt ngoặc**, tức cách gom nhóm phép tính, mà vẫn giữ cùng kết quả. Nó không cho phép tự ý đổi thứ tự phần tử.

Ví dụ với phép cộng số nguyên (xét theo ngữ nghĩa số nguyên Java):

~~~text
(2 + 3) + 5 = 10
2 + (3 + 5) = 10
~~~

Ngược lại, phép trừ không associative:

~~~text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
~~~

Khi reduction chạy song song, hệ thống có thể chia [a, b, c, d] thành các nhóm rồi tổng hợp:

~~~text
Tuần tự:  (((a op b) op c) op d)
Chia đôi: (a op b) op (c op d)
~~~

Nếu op associative, hai cách nhóm tương đương về mặt phép toán. Nếu không, kết quả có thể phụ thuộc vào cách Stream được phân hoạch và ghép lại. Đừng coi kết quả của một lần chạy thử parallelStream() là bảo đảm cho những lần chạy khác.

### Associative khác commutative

- **Associative:** (a op b) op c = a op (b op c), chỉ đổi cách nhóm.
- **Commutative (giao hoán):** a op b = b op a, đổi vị trí hai toán hạng.

Ghép chuỗi có tính associative, vì ("A" + "B") + "C" bằng "A" + ("B" + "C"), nhưng không giao hoán: "AB" khác "BA". Vì vậy **không bắt buộc commutative để dùng reduce**. Tuy nhiên, nếu kết quả nhạy với thứ tự, nguồn Stream và encounter order phải được xem xét: Stream từ List có thứ tự xác định, còn nguồn như HashSet không bảo đảm thứ tự duyệt cố định.

Cũng cần tách biệt **tính kết hợp toán học** khỏi **tính chính xác của biểu diễn máy tính**: phép cộng double có thể không associative do làm tròn; xem mục 8.

## 3. Ba thành phần: identity, accumulator, combiner

| Thành phần | Vai trò | Ví dụ tính tổng |
|---|---|---|
| **identity** | Giá trị trung hòa; khởi tạo một kết quả bộ phận và đại diện kết quả khi Stream rỗng ở overload có identity | 0 |
| **accumulator** | Gộp kết quả đã có với một phần tử mới | (sum, x) → sum + x |
| **combiner** | Gộp hai kết quả bộ phận, đặc biệt khi xử lý song song | (left, right) → left + right |

### Identity phải thực sự trung hòa

Với phép nhị phân op, giá trị e là identity khi ghép e với một giá trị không làm thay đổi giá trị ấy (theo phía ghép mà hợp đồng yêu cầu). Những ví dụ quen thuộc:

| Phép tổng hợp | Identity đúng | Lý do |
|---|---|---|
| Cộng số nguyên | 0 | 0 + x = x |
| Nhân số nguyên | 1 | 1 × x = x |
| Ghép chuỗi | Chuỗi rỗng "" | "" + s = s |
| OR boolean | false | false OR b = b |
| AND boolean | true | true AND b = b |

**Identity không phải “giá trị bắt đầu tùy ý”.** Nếu muốn cộng thêm một hằng số sau khi tính tổng, hãy tổng hợp bằng identity = 0 rồi cộng hằng số vào kết quả cuối cùng.

Ví dụ sai: numbers.parallelStream().reduce(10, Integer::sum). Trong một reduction song song, 10 có thể được dùng làm giá trị đầu của **nhiều** kết quả bộ phận, nên phép cộng này không thực hiện ý nghĩa “tổng phần tử + 10” một cách ổn định. Với [1, 2, 3], luồng tuần tự trả 16; số lần cộng thêm 10 ở luồng song song phụ thuộc cách phân nhóm. Cách đúng:

~~~java
int sumPlusTen = numbers.parallelStream()
        .reduce(0, Integer::sum) + 10;
~~~

Đây là một mảnh mã minh họa, với biến numbers là List<Integer> đã được khai báo.

### Những quy tắc bổ sung

Hàm accumulation và combination phải:

- Có tính associative theo yêu cầu của overload.
- **Stateless:** không phụ thuộc vào biến đếm hoặc kết quả mutable bên ngoài thay đổi giữa các lần gọi.
- **Non-interfering:** không sửa nguồn dữ liệu của Stream trong lúc pipeline chạy.
- Cung cấp kết quả có ý nghĩa độc lập với chiến lược phân hoạch; các phép toán được yêu cầu phải tương thích với nhau.

Các hàm có side effect dễ tạo race condition, kết quả thiếu ổn định và lỗi khó tái hiện. Nên sử dụng các phép toán thuần (pure function), đặc biệt khi parallelStream() xuất hiện.

## 4. Ba overload của Stream.reduce

### 4.1. reduce(BinaryOperator<T>) — không có identity

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Thư viện lấy phần tử đầu tiên làm giá trị tích lũy ban đầu. Stream rỗng trả Optional.empty(); Stream có phần tử trả Optional chứa kết quả. Accumulator phải associative.

~~~java
Optional<Integer> maximum = numbers.stream()
        .reduce(Integer::max);
~~~

Dạng này hữu ích khi **không có giá trị trung hòa tự nhiên phù hợp với miền dữ liệu**, như tìm max mà không muốn tự chọn một giá trị giả làm max của Stream rỗng. Dùng orElse, orElseThrow hoặc xử lý Optional một cách chủ động; không gọi get() khi chưa kiểm tra có giá trị.

Hàm reduction không được trả null để đại diện “không tìm thấy”: overload này có thể ném NullPointerException nếu kết quả reduce là null.

### 4.2. reduce(T identity, BinaryOperator<T>) — cùng kiểu đầu vào/đầu ra

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Identity phải trung hòa đối với accumulator; accumulator phải associative, stateless và non-interfering.

~~~java
int total = numbers.stream().reduce(0, Integer::sum);
int product = numbers.stream().reduce(1, (a, b) -> a * b);
~~~

Dạng này trả trực tiếp T, kể cả khi Stream rỗng (khi đó kết quả là identity). Không dùng identity sai chỉ để tránh xử lý trường hợp rỗng.

### 4.3. reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)

Ký hiệu khái quát (bỏ các wildcard để dễ đọc):

~~~java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
~~~

Kiểu phần tử T có thể khác kiểu kết quả U. Accumulator thêm một phần tử T vào kết quả trung gian U; combiner gộp hai kết quả U.

Với mọi kết quả trung gian u và phần tử t, các điều kiện cần giữ là:

~~~text
combine(identity, u) = u
combine(combine(a, b), c) = combine(a, combine(b, c))
combine(u, accumulate(identity, t)) = accumulate(u, t)
~~~

Điều kiện thứ ba gọi là **tính tương thích giữa combiner và accumulator**. Nó bảo đảm rằng “tự tích lũy phần tử t vào u” tương đương “tính phần đóng góp của t rồi kết hợp vào u”. Chỉ kiểm tra combiner associative mà bỏ điều kiện tương thích vẫn có thể cho kết quả sai.

Ví dụ tính tổng độ dài chuỗi:

~~~java
List<String> names = List.of("An", "Binh", "Chi");

int totalLength = names.parallelStream().reduce(
        0,
        (length, name) -> length + name.length(),
        Integer::sum
);
~~~

Ở đây T = String và U = Integer. Identity là 0; accumulator biến chuỗi thành phần đóng góp số lượng ký tự; combiner cộng hai tổng trung gian. Với u = 5 và t = "An":

~~~text
combine(5, accumulate(0, "An")) = 5 + 2 = 7
accumulate(5, "An")             = 5 + 2 = 7
~~~

Trong trường hợp chỉ cần chuyển kiểu rồi cộng, cách dưới thường sáng sủa và chuyên biệt hơn:

~~~java
int totalLength = names.parallelStream()
        .mapToInt(String::length)
        .sum();
~~~

Không phải lúc nào overload ba tham số cũng cần thiết; ưu tiên API dễ đọc khi khả năng diễn đạt và hiệu năng phù hợp.

## 5. Chương trình thực hành: phép tổng hợp đúng

Lưu thành tệp ReductionBasics.java rồi chạy bằng JDK 17 trở lên:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class ReductionBasics {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 3, 5);
        List<String> names = List.of("An", "Binh", "Chi");

        int sequentialSum = values.stream()
                .reduce(0, Integer::sum);

        int parallelSum = values.parallelStream()
                .reduce(0, Integer::sum);

        int product = values.stream()
                .reduce(1, (a, b) -> a * b);

        Optional<Integer> maximum = values.stream()
                .reduce(Integer::max);

        Optional<Integer> emptyMaximum = Stream.<Integer>empty()
                .reduce(Integer::max);

        int totalLength = names.parallelStream().reduce(
                0,
                (length, name) -> length + name.length(),
                Integer::sum
        );

        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("product=" + product);
        System.out.println("maximum=" + maximum.orElseThrow());
        System.out.println("emptyMaximum=" +
                (emptyMaximum.isEmpty() ? "none" : emptyMaximum.get()));
        System.out.println("totalLength=" + totalLength);
    }
}
~~~

~~~text
javac ReductionBasics.java
java ReductionBasics

sequentialSum=10
parallelSum=10
product=30
maximum=5
emptyMaximum=none
totalLength=9
~~~

Tổng và tích dùng identity phù hợp. Integer::sum và phép nhân số nguyên có tính kết hợp theo phép toán của kiểu int trong Java. Nếu mục tiêu là tổng **toán học chính xác vượt phạm vi int**, dùng kiểu dữ liệu thích hợp (chẳng hạn BigInteger) thay vì mặc nhiên chấp nhận tràn số.

## 6. Thiết kế reduction cho kết quả tổng hợp riêng

Có trường hợp cần đồng thời số lượng và tổng để tính trung bình. **Trung bình của hai nhóm không được tự động lấy trung bình cộng của hai giá trị trung bình**, vì số phần tử mỗi nhóm có thể khác nhau.

Ví dụ hai nhóm {10} và {20, 30, 40}: trung bình nhóm lần lượt 10 và 30; trung bình đúng của toàn bộ bốn số là 25, không phải (10 + 30) / 2 = 20.

Thay vào đó, giữ trạng thái tổng hợp **bất biến** gồm (count, sum). Ghép hai nhóm bằng cách cộng count và sum tương ứng. Phép này associative và có identity (0, 0).

Tệp StatsReduction.java, chạy được trên Java 17 trở lên:

~~~java
import java.util.stream.Stream;

public class StatsReduction {
    record Stats(long count, long sum) {
        Stats add(int value) {
            return new Stats(count + 1, sum + value);
        }

        Stats combine(Stats other) {
            return new Stats(count + other.count, sum + other.sum);
        }
    }

    public static void main(String[] args) {
        Stats result = Stream.of(4, 6, 8)
                .parallel()
                .reduce(
                        new Stats(0, 0),
                        Stats::add,
                        Stats::combine
                );

        System.out.println("count=" + result.count()
                + ", sum=" + result.sum());
        System.out.println("average="
                + (double) result.sum() / result.count());
    }
}
~~~

~~~text
javac StatsReduction.java
java StatsReduction

count=3, sum=18
average=6.0
~~~

**Giải thích:**

1. **Stats(0, 0)** là identity: kết hợp với bất kỳ Stats hợp lệ nào cũng giữ nguyên count và sum.
2. **add(int value)** tạo một Stats mới, tăng count và cộng giá trị vào sum; không thay đổi đối tượng cũ.
3. **combine(Stats other)** gộp hai kết quả trung gian với phép cộng ở cả hai thành phần.
4. Tính tương thích: combine(u, add(identity, t)) tạo đúng kết quả như add(u, t).
5. Chia Stream thành các nhóm bất kỳ rồi combine vẫn cho cùng cặp (count, sum), miễn không xảy ra tràn số. Không chia khi count = 0; dùng OptionalDouble hoặc xử lý trạng thái rỗng riêng.

Trong công việc thực tế, với nhu cầu thống kê số nguyên thông thường, có thể dùng IntStream.summaryStatistics() (hoặc DoubleStream.summaryStatistics()) thay vì viết lại kiểu Stats. Mẫu tự thiết kế ở trên giúp hiểu chính xác các hợp đồng cần đáp ứng khi tổng hợp dữ liệu tùy biến.

## 7. Khi nào dùng reduce, khi nào dùng collect?

Cả hai đều thuộc nhóm reduction nhưng có cơ chế phù hợp với những kiểu kết quả khác nhau:

| Nhu cầu | Gợi ý | Vì sao |
|---|---|---|
| Tổng số nguyên | mapToInt(...).sum() hoặc IntStream.sum() | API chuyên biệt, rõ ý định |
| Min/max không muốn tự đặt identity | min(...), max(...) hoặc reduce(... ) trả Optional | Xử lý Stream rỗng rõ ràng |
| Tạo giá trị bất biến từ nhiều phần tử | reduce với toán tử pure | Kết quả trung gian có thể ghép an toàn |
| Thu thập thành List/Set/Map | collect(...) hoặc Stream.toList() khi phù hợp | Cơ chế mutable reduction được thiết kế riêng |
| Ghép nhiều chuỗi | Collectors.joining(delimiter) | Tránh tạo chuỗi tạm lặp lại không cần thiết |
| Đếm/tổng/thống kê nhiều trường | summaryStatistics(), collectingAndThen(), teeing() hoặc Collector phù hợp | Diễn đạt cấu trúc kết quả rõ ràng |

**Lỗi nguy hiểm:** dùng một ArrayList mutable làm identity rồi add trực tiếp vào nó trong reduce ba tham số.

~~~java
// PHẢN VÍ DỤ: không dùng cho production.
List<String> unsafe = names.parallelStream().reduce(
        new java.util.ArrayList<String>(),
        (list, name) -> {
            list.add(name);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

Đây là mảnh mã minh họa với names là List<String> đã khai báo. Nó vi phạm tinh thần identity trung hòa và reduction không dùng chung trạng thái: cùng một object ArrayList ban đầu có thể tham gia nhiều tác vụ, dẫn đến race, lặp kết quả hoặc lỗi. **Đổi parallelStream() thành stream() không biến mẫu này thành một thiết kế reduction đúng hợp đồng.**

Cách đúng:

~~~java
List<String> safe = names.parallelStream()
        .toList();
~~~

Từ Java 16, Stream.toList() trả một List không sửa được. Nếu thật sự cần một ArrayList mutable, dùng:

~~~java
List<String> mutable = names.parallelStream()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
~~~

collect cung cấp container mới cho các phần tổng hợp, accumulator để thêm phần tử và combiner để gộp container; không dùng chung identity mutable theo cách của reduce.

## 8. Những bẫy quan trọng về associativity

### 8.1. Phép trừ và phép chia

Các phép này không associative nói chung. Không dùng (a, b) -> a - b hoặc (a, b) -> a / b làm toán tử reduce với kỳ vọng kết quả bất biến khi xử lý song song.

~~~text
(10 - 5) - 2 = 3, nhưng 10 - (5 - 2) = 7
(24 / 6) / 2 = 2, nhưng 24 / (6 / 2) = 8
~~~

Nếu bài toán thực sự yêu cầu phép trừ từ trái sang phải, hãy dùng vòng lặp tuần tự rõ ràng hoặc thiết kế lại phép tổng hợp thành một cấu trúc có phép ghép associative; đừng dựa vào một chiến lược gom nhóm ngầm định.

### 8.2. Số thực dấu chấm động

Vì IEEE 754 làm tròn sau phép tính, cộng double có thể cho kết quả khác nhau khi đổi ngoặc:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Do đó, không bảo đảm tính nhất quán bit-for-bit giữa mọi cách phân hoạch và thứ tự tính của một reduction dùng double. Với các tổng lớn, cần đánh giá sai số và độ ổn định số; DoubleStream.sum() dùng thuật toán cải thiện độ chính xác nhưng **không hứa kết quả luôn giống nhau cho mọi thứ tự cộng**. Với tiền tệ hoặc phép cộng thập phân đòi hỏi chính xác, có thể dùng BigDecimal khởi tạo từ chuỗi thập phân và phép cộng không đặt MathContext làm tròn mỗi bước. Làm tròn một lần ở cuối theo quy tắc nghiệp vụ.

### 8.3. Sai identity hoặc combiner

Những lỗi thường gặp:

- Cộng nhưng identity = 1 hoặc 10, làm lệch kết quả giữa các phân hoạch.
- Accumulator tính tổng nhưng combiner lại lấy max: hai phép không tương thích.
- Combiner bỏ mất một nhánh, ví dụ (left, right) -> left.
- Combiner có side effect cập nhật chung một Map, List hoặc biến đếm bên ngoài.

Kiểm tra không chỉ kết quả cuối cùng của vài input; hãy viết rõ phương trình identity, associativity và compatibility.

### 8.4. Trạng thái ngoài, nguồn bị sửa và null

Không cập nhật biến mutable bên ngoài từ lambda của reduce, không thay đổi collection nguồn khi pipeline đang chạy và không dựa vào thứ tự gọi accumulator. Tránh trả null từ các toán tử reduction; với overload trả Optional, null là lỗi được Java chỉ rõ.

### 8.5. Tràn số nguyên

Phép cộng int Java có thể tràn số và tạo kết quả wraparound. Dù tính kết hợp vẫn giữ dưới ngữ nghĩa số nguyên modulo 2^32 của phép cộng int, **giá trị đó có thể sai so với tổng toán học nghiệp vụ cần có**. Dùng long nếu đủ miền, BigInteger nếu cần số nguyên chính xác không giới hạn kích thước; cân nhắc Math.addExact khi muốn phát hiện tràn thay vì nhận kết quả âm/dương bất ngờ.

### 8.6. Parallel không tự động nhanh hơn

parallelStream() có chi phí phân hoạch, lập lịch và ghép kết quả. Với dữ liệu nhỏ, công việc rất nhẹ, thao tác chặn I/O hoặc combiner tốn kém, nó có thể chậm hơn Stream tuần tự. Chỉ bật sau khi có phép toán đúng hợp đồng và đo hiệu năng trên workload thật. Associativity là điều kiện **đúng đắn**, không phải lời hứa **tăng tốc**.

## 9. Kiểm tra tính associative một cách chủ động

Với một phép op, hãy tự đối chiếu hai cách nhóm trên nhiều bộ (a, b, c). Ví dụ sau kiểm tra miền nhỏ [-2, 2] và cho thấy phép trừ thất bại ngay trong tập mẫu:

Tệp AssociativityCheck.java:

~~~java
import java.util.function.IntBinaryOperator;

public class AssociativityCheck {
    static boolean associativeOnSample(IntBinaryOperator op) {
        for (int a = -2; a <= 2; a++) {
            for (int b = -2; b <= 2; b++) {
                for (int c = -2; c <= 2; c++) {
                    int left = op.applyAsInt(
                            op.applyAsInt(a, b), c);
                    int right = op.applyAsInt(
                            a, op.applyAsInt(b, c));
                    if (left != right) {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        System.out.println("add=" +
                associativeOnSample(Integer::sum));
        System.out.println("subtract=" +
                associativeOnSample((a, b) -> a - b));
    }
}
~~~

~~~text
javac AssociativityCheck.java
java AssociativityCheck

add=true
subtract=false
~~~

**Giới hạn:** kiểm tra trên tập hữu hạn chỉ giúp phát hiện phản ví dụ, không chứng minh cho mọi phần tử. Với phép tổng hợp tùy biến, cần lập luận đại số hoặc kiểm định tính chất (property-based tests), kiểm tra Stream rỗng, một phần tử, nhiều phần tử và so sánh kết quả tuần tự/song song trên các tập dữ liệu có ý nghĩa. Cần kiểm tra thêm phương trình identity và compatibility của overload ba tham số.

## 10. Checklist trước khi viết reduction

1. Kết quả cần là một giá trị bất biến hay một container mutable? Container thường nên dùng collect.
2. Toán tử của bạn associative trong **miền dữ liệu và kiểu biểu diễn đang dùng** hay chưa? Có thể viết chứng minh/phản ví dụ?
3. Identity có đúng là giá trị trung hòa, kể cả lúc phân hoạch song song và lúc Stream rỗng?
4. Với reduce ba tham số: combiner có associative và tương thích với accumulator không?
5. Lambda có stateless, non-interfering, không side effect và không chia sẻ object mutable không?
6. Thứ tự phần tử có ý nghĩa không? Nguồn có encounter order xác định không? Có đang nhầm associative với commutative?
7. Có nguy cơ overflow, sai số floating point hoặc phép làm tròn làm thay đổi kết quả?
8. Có terminal operation chuyên biệt rõ ràng hơn, chẳng hạn sum, max, summaryStatistics, joining hoặc toList không?
9. Có kiểm tra trường hợp rỗng, một phần tử, nhiều phần tử và so sánh sequential với parallel? Đã đo hiệu năng trước khi dùng parallel?

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao reduce(0, Integer::sum) phù hợp để tính tổng các số nguyên, còn reduce(10, Integer::sum) không phù hợp để tính “tổng + 10”?

*Gợi ý đáp án:* 0 là identity của phép cộng; 10 không trung hòa và có thể được đưa vào nhiều lần ở các nhánh reduction song song. Hãy cộng 10 sau reduce với identity 0.

**Câu 2.** Ghép chuỗi có associative không? Có cần commutative để dùng reduce không?

*Gợi ý đáp án:* Ghép chuỗi associative nhưng không commutative. Reduce không bắt buộc giao hoán; nếu kết quả phụ thuộc thứ tự, phải giữ đúng encounter order từ nguồn.

**Câu 3.** Trong reduce(identity, accumulator, combiner), vì sao chỉ kiểm tra combiner associative là chưa đủ?

*Gợi ý đáp án:* Accumulator và combiner còn phải thỏa combine(u, accumulate(identity, t)) = accumulate(u, t); nếu không, gộp các phần sẽ khác tích lũy trực tiếp.

**Câu 4.** Muốn chuyển một Stream<String> thành List<String>, nên dùng reduce với ArrayList hay collect/toList?

*Gợi ý đáp án:* Dùng collect hoặc toList; reduce có identity mutable chia sẻ là thiết kế sai, đặc biệt nguy hiểm khi song song.

**Câu 5.** Hai kết quả double được cộng theo hai cách đặt ngoặc khác nhau có thể khác nhau không?

*Gợi ý đáp án:* Có, vì làm tròn floating point; hãy chọn chiến lược số học phù hợp với độ chính xác nghiệp vụ yêu cầu.

## Tài liệu tham khảo hiện hành

- Oracle Java SE 25 (LTS), Stream API: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 25 (LTS), Stream package — Reduction operations & Associativity: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 25 (LTS), Collectors API: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html

Các hợp đồng về associativity, identity, combiner và reduction nêu trên vẫn là nền tảng để dùng Stream đúng trong Java hiện đại.
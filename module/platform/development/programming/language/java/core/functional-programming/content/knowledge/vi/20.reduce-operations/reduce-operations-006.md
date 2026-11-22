# Yêu cầu tương thích giữa accumulator và combiner trong Stream.reduce()

Trong Java Stream API, **reduce** kết hợp nhiều phần tử thành **một kết quả tổng hợp** theo quy tắc do lập trình viên cung cấp. Dạng reduce có ba đối số đặc biệt hữu ích khi **kiểu phần tử đầu vào T khác kiểu kết quả U**. Nhưng để giảm dữ liệu đúng trong cả stream tuần tự và song song, không thể chỉ chọn accumulator và combiner sao cho mã biên dịch: hai hàm phải **tương thích về mặt đại số**, còn combiner phải có phần tử trung hòa và tính kết hợp.

Nếu accumulator xử lý một phần tử theo một nghĩa nhưng combiner ghép kết quả của các nhóm theo nghĩa khác, phép reduce có thể chạy tuần tự ra số đúng nhưng **parallel stream cho kết quả sai hoặc phụ thuộc cách chia nhóm**. Đây là lỗi logic không được hệ thống generic của Java tự phát hiện.

Bài học giải thích chữ ký API, phương trình tương thích chính thức, vai trò identity, associativity, phương pháp kiểm thử bằng phân vùng giả lập, các phản ví dụ, immutable reduction và khi nào nên chuyển sang collect. Ví dụ hoàn chỉnh dùng Java 17+ và có stdout được kiểm chứng bằng thực thi thực tế.

## 1. Dạng reduce ba đối số

Chữ ký trong Stream<T>:

~~~java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
~~~

Trong đó:

| Thành phần | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **identity** | U | Giá trị ban đầu/trung hòa cho các phần rút gọn |
| **accumulator** | BiFunction<U, ? super T, U> | Tích lũy một phần tử T vào kết quả U |
| **combiner** | BinaryOperator<U> | Ghép hai kết quả U của các phần đã được rút gọn |
| **kết quả** | U | Giá trị tổng hợp cuối cùng |

Ví dụ tính tổng độ dài chuỗi:

~~~java
List<String> words = List.of("Java", "Go", "Lambda", "API");

int totalLength = words.stream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
System.out.println(totalLength); // 15
~~~

Ở đây T = String, U = Integer.

- **0** là identity cho phép cộng Integer.
- **(total, word) -> total + word.length()** là accumulator; nó nhận Integer và String, trả Integer.
- **Integer::sum** là combiner; nó nhận hai Integer và trả Integer.

Ba giá trị có chữ ký tương thích, nhưng điều quan trọng hơn là **chúng cùng diễn đạt một phép tính**: tổng độ dài của mọi phần tử, dù phần tử được xử lý trong một nhóm duy nhất hay nhiều nhóm.

Các đoạn minh họa lẻ trong bài cần import và đặt vào một lớp/phương thức hợp lệ; mục chương trình hoàn chỉnh có đầy đủ import và phương thức main.

## 2. Ba luật đại số cần tuân thủ

Với reduce ba đối số, hãy kiểm tra:

1. **Identity trung hòa đối với combiner.**
2. **Combiner có tính kết hợp (associative).**
3. **Accumulator tương thích với combiner.**

Bên cạnh đó, các callback được cung cấp cho Stream cần **stateless** và **non-interfering** theo hợp đồng xử lý Stream: không sửa nguồn, không phụ thuộc vào dữ liệu mutable dùng chung theo cách làm kết quả khác nhau giữa các lần gọi.

### 2.1. Identity trung hòa

Đối với một kết quả tích lũy u bất kỳ, identity phù hợp phải không thay đổi giá trị khi được ghép với u. Có thể hình dung bằng:

~~~text
combiner(identity, u) = u
combiner(u, identity) = u
~~~

Phép cộng số nguyên có identity là 0. Phép nhân có identity là 1. Phép nối String có identity là chuỗi rỗng.

~~~java
BinaryOperator<Integer> combine = Integer::sum;
int identity = 0;

System.out.println(combine.apply(identity, 7)); // 7
System.out.println(combine.apply(7, identity)); // 7
~~~

Chọn identity theo **combiner**, không chọn một giá trị tùy ý chỉ vì muốn cộng thêm một số cố định vào tổng.

### 2.2. Combiner có tính kết hợp

Tính kết hợp có nghĩa đổi cách đặt ngoặc khi ghép ba kết quả không đổi nghĩa kết quả:

~~~text
combiner(combiner(a, b), c)
    =
combiner(a, combiner(b, c))
~~~

Với phép cộng:

~~~text
(2 + 3) + 4 = 2 + (3 + 4) = 9
~~~

Với phép nối chuỗi:

~~~text
("A" + "B") + "C"
    =
"A" + ("B" + "C")
~~~

Nhưng phép trừ không có tính kết hợp:

~~~text
(9 - 4) - 2 = 3
9 - (4 - 2) = 7
~~~

Vì vậy, dùng phép trừ làm combiner của một phép tổng hợp thường không phù hợp. Java cho phép bạn viết lambda trả Integer, nhưng **không tự chứng minh luật kết hợp**.

### 2.3. Phương trình compatibility: yêu cầu quan trọng nhất

Điều kiện tương thích của accumulator và combiner được diễn đạt:

~~~text
combiner(u, accumulator(identity, t))
    =
accumulator(u, t)
~~~

Với u là một giá trị U và t là một phần tử T.

**Giải thích từng vế:**

- **accumulator(identity, t)**: xử lý riêng phần tử t trong một phần rút gọn bắt đầu từ identity.
- **combiner(u, accumulator(identity, t))**: ghép phần kết quả vừa tính với phần kết quả u đã có.
- **accumulator(u, t)**: xử lý t trực tiếp vào kết quả u mà không tạo phần riêng.

Hai cách làm phải cho cùng một giá trị theo hợp đồng của phép tính.

Ví dụ tổng độ dài: u = 10, t = "Go", identity = 0.

~~~text
accumulator(0, "Go") = 2
combiner(10, 2) = 12
accumulator(10, "Go") = 12
~~~

Hai vế đều bằng 12. Điều này có nghĩa việc ghép một phân vùng chỉ chứa "Go" cho đúng kết quả như thêm "Go" trực tiếp vào tổng hiện tại.

## 3. Vì sao sequential và parallel có thể dùng hai cách ghép?

Để dễ hình dung, khi giảm tuần tự bốn từ Java, Go, Lambda, API, ta có thể mô tả:

~~~text
0 + length("Java")   = 4
4 + length("Go")     = 6
6 + length("Lambda") = 12
12 + length("API")   = 15
~~~

Ở parallel stream, nguồn **có thể** được chia và xử lý cục bộ:

~~~text
Phần A: ["Java", "Go"]     -> 6
Phần B: ["Lambda", "API"]  -> 9

Ghép: combiner(6, 9)      -> 15
~~~

Đây chỉ là mô hình minh họa; JVM không cam kết cách chia chính xác hay thứ tự gọi combiner như sơ đồ trên. Nếu các luật đại số đúng, việc thay đổi cách chia nhóm hợp lệ không thay đổi kết quả.

**Không nên hiểu parallel stream chỉ là nhiều thread đồng thời sửa một biến tổng duy nhất.** Nó có thể tạo kết quả của từng phần rồi kết hợp các phần bằng combiner. Vì vậy một phép reduce có vẻ hoạt động tốt khi tuần tự vẫn có thể bị lỗi nếu combiner không nhất quán.

## 4. Phản ví dụ: accumulator cộng nhưng combiner trừ

Giả sử:

~~~java
List<String> words = List.of("Java", "Go");

int result = words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    (left, right) -> left - right
);
~~~

Accumulator cộng tổng độ dài, nhưng combiner lại trừ hai tổng cục bộ. Chữ ký cả hai hàm hợp lệ, song **ngữ nghĩa sai**.

Nếu toàn bộ dữ liệu được xử lý bởi một phần rút gọn:

~~~text
0 + 4 + 2 = 6
~~~

Nếu tách thành hai phần:

~~~text
partA = 0 + 4 = 4
partB = 0 + 2 = 2

wrongCombiner(partA, partB) = 4 - 2 = 2
~~~

Kết quả 2 khác 6. Không nên chạy parallel nhiều lần rồi chờ “tình cờ” có kết quả 2; việc **tự mô phỏng phân vùng** đã chứng minh sự không tương thích.

Thử phương trình với u = 4, t = "Go":

~~~text
combiner(4, accumulator(0, "Go")) = 4 - 2 = 2
accumulator(4, "Go")              = 4 + 2 = 6
~~~

Vì hai vế không bằng nhau, bộ ba bị lỗi.

**Sửa bằng combiner đúng nghĩa:**

~~~java
int correct = words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

Khi dùng tổng cộng ở cả accumulator và combiner, kết quả của hai phân vùng là 4 + 2 = 6.

## 5. Phản ví dụ: identity không trung hòa

Đoạn này có vẻ cộng thêm 10 vào tổng độ dài:

~~~java
int value = List.of("Java", "Go").stream().reduce(
    10,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

Với lượt rút gọn tuần tự trong ví dụ, giá trị là:

~~~text
10 + 4 + 2 = 16
~~~

Nhưng khi nguồn được chia thành hai phần riêng, mỗi phần có thể bắt đầu từ identity = 10:

~~~text
partA = 10 + 4 = 14
partB = 10 + 2 = 12
combined = 14 + 12 = 26
~~~

**Identity 10 không trung hòa phép cộng**, vì combiner(10, u) = 10 + u, không bằng u. Sự chênh lệch 16 và 26 không phải bug của Java mà do bộ đối số reduce sai luật.

Muốn cộng thêm một khoản cơ sở 10 đúng **một lần**, hãy dùng identity 0 để giảm rồi cộng 10 sau:

~~~java
int result = 10 + words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

Khi dữ liệu được chia nhiều phần, mỗi phần sử dụng identity hợp lệ 0, rồi giá trị cơ sở chỉ được cộng vào tổng cuối cùng.

## 6. T và U khác nhau vẫn có thể tương thích

Điều kiện compatibility **không yêu cầu accumulator và combiner có cùng chữ ký**, bởi chúng có nhiệm vụ khác nhau.

Đối với Stream<String> giảm thành Integer:

~~~java
int total = words.stream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
);
~~~

Accumulator nhận Integer và String; combiner nhận hai Integer. Chúng khác phép tính trên đối số nhưng tương thích về kết quả “tổng độ dài”.

Một ví dụ khác: Stream<Integer> giảm thành Long:

~~~java
long total = numbers.parallelStream().reduce(
    0L,
    (sum, number) -> sum + number.longValue(),
    Long::sum
);
~~~

T ở đây là Integer, U là Long. Dùng Long để giảm nguy cơ tràn int cho tổng lớn, nhưng long vẫn có giới hạn. Nếu giá trị ngoài phạm vi long có thể xuất hiện, cần thiết kế một kiểu số/kiểm tra overflow khác phù hợp.

### 6.1. Nối chuỗi có định dạng

~~~java
String labels = words.parallelStream().reduce(
    "",
    (result, word) -> result + "[" + word + "]",
    String::concat
);
~~~

Đầu ra là chuỗi các nhãn "[Java][Go]..." theo encounter order phù hợp. Identity là chuỗi rỗng. Accumulator biến word thành đoạn đã định dạng rồi nối; combiner nối hai đoạn đã hoàn tất.

Điểm cần chú ý: **tính tương thích không phải “phép toán trông giống nhau”**. Nó có nghĩa rằng kết quả của việc thêm phần tử và kết quả của việc ghép phân vùng diễn đạt **chính cùng một phép tổng hợp**.

## 7. Tính kết hợp khác tính giao hoán

Một phép toán có thể kết hợp mà không giao hoán.

Nối String có tính kết hợp:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C")
~~~

Nhưng không giao hoán:

~~~text
"A" + "B" = "AB"
"B" + "A" = "BA"
~~~

Parallel reduction không bắt buộc mọi combiner đều giao hoán. Tuy nhiên, nếu kết quả phụ thuộc thứ tự phần tử, **encounter order của nguồn và các thao tác** phải phù hợp với yêu cầu nghiệp vụ.

Với ordered stream, phép nối String tương thích có thể cho kết quả theo thứ tự nguồn. Với nguồn unordered, không nên mặc định chuỗi kết quả có đúng một thứ tự cố định.

### 7.1. Phép trừ và chia không thích hợp khi đổi nhóm

~~~text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
~~~

Nếu yêu cầu là lấy số ban đầu rồi trừ **tổng** các phần tử, hãy tính tổng bằng phép cộng kết hợp rồi trừ một lần:

~~~java
int result = initial - numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Nếu yêu cầu là một thuật toán **phụ thuộc chặt vào thứ tự từng bước**, vòng lặp tuần tự với trạng thái được kiểm soát có thể dễ hiểu và đúng hợp đồng hơn việc ép nó vào parallel reduce.

### 7.2. Floating-point không kết hợp tuyệt đối

Phép cộng double/float có sai số làm tròn. Theo tính toán dấu chấm động, hai cách đặt ngoặc có thể tạo số khác nhau đôi chút:

~~~text
(a + b) + c
a + (b + c)
~~~

Các nhóm khác nhau trong parallel reduction có thể làm thay đổi thứ tự cộng và sai số quan sát được. Đừng viết test tổng double yêu cầu bit-for-bit bằng nhau trong mọi cách thực thi nếu dữ liệu nhạy với thứ tự. Với nghiệp vụ tiền tệ, cân nhắc BigDecimal và chính sách precision/rounding hoặc số nguyên đơn vị nhỏ nhất phù hợp.

Với phép cộng int/long, overflow có thể làm giá trị không còn đúng theo toán học; cần kiểm tra giới hạn và dùng Math.addExact khi không được phép tràn.

## 8. Không để accumulator hoặc combiner sửa nguồn hay global state

Hợp đồng Stream yêu cầu các behavioral parameters phù hợp với xử lý không can thiệp nguồn và stateless. Đừng sửa Collection đang được duyệt từ callback:

~~~java
// SAI: source là một collection mutable đang được Stream duyệt.
source.parallelStream().reduce(
    0,
    (sum, value) -> {
        source.add(value);
        return sum + 1;
    },
    Integer::sum
);
~~~

Đây là mã minh họa lỗi có chủ ý, cần nguồn source được khai báo trong ngữ cảnh thật. Hậu quả có thể là thay đổi bất ngờ, ConcurrentModificationException hoặc kết quả không tin cậy.

Tương tự, một bộ đếm ngoài không tạo ra tính thuần chỉ vì là AtomicInteger:

~~~java
AtomicInteger counter = new AtomicInteger();

int result = values.parallelStream().reduce(
    0,
    (sum, value) -> sum + value + counter.incrementAndGet(),
    Integer::sum
);
~~~

Số lần gọi, thứ tự và lịch thread có thể làm kết quả thay đổi. AtomicInteger chỉ giải quyết thao tác tăng nguyên tử, không giải quyết tính tương thích đại số.

Hãy để giá trị U chứa **trạng thái kết quả cần tính**, thay vì phụ thuộc vào biến toàn cục mutable.

## 9. Không dùng mutable identity với reduce

Một lỗi nổi tiếng là dùng StringBuilder làm identity rồi sửa nó tại chỗ:

~~~java
// SAI: identity mutable, accumulator/combiner mutate object.
StringBuilder text = words.parallelStream().reduce(
    new StringBuilder(),
    (builder, word) -> builder.append(word),
    (left, right) -> left.append(right)
);
~~~

Mặc dù Java cho phép biên dịch, đoạn này không phải reduction theo giá trị bất biến: nó dùng cùng object identity mutable và sửa object từ các nhánh. Với parallel stream, điều này có thể gây race, nhân đôi dữ liệu hoặc thứ tự không đúng.

**Không khắc phục đúng bằng cách chỉ thêm synchronized.** Vấn đề còn nằm ở hợp đồng reduction, aliasing và cùng một container mutable có thể bị ghép với chính nó.

### 9.1. Cách 1: reduce giá trị immutable

~~~java
String joined = words.stream().reduce(
    "",
    (result, word) -> result + word,
    String::concat
);
~~~

String immutable, mỗi phép nối trả một String giá trị mới, phù hợp hơn về mặt đại số. Tuy nhiên, nối nhiều String liên tục có thể tạo chi phí sao chép đáng kể với dữ liệu dài.

### 9.2. Cách 2: collect với container mutable

~~~java
String joined = words.parallelStream().collect(
    StringBuilder::new,
    (builder, word) -> builder.append(word),
    StringBuilder::append
).toString();
~~~

Stream.collect(supplier, accumulator, combiner) dành cho **mutable reduction**. Supplier tạo container cho từng phần, accumulator thêm phần tử vào container, combiner ghép các container. Không đưa cùng một StringBuilder static từ supplier cho mọi nhánh.

Khác biệt về kiểu:

| Thao tác | Accumulator | Combiner | Cách dùng |
| --- | --- | --- | --- |
| reduce ba đối số | BiFunction<U,T,U> | BinaryOperator<U> | Tạo giá trị U từ kết quả và phần tử |
| collect ba đối số | BiConsumer<R,T> | BiConsumer<R,R> | Thay đổi container R được supplier tạo |
| reduce hai đối số | BinaryOperator<T> | Cùng operator được dùng trong reduction | Tích lũy các phần tử cùng kiểu T |

Với collect, cần tuân thủ chính hợp đồng supplier/accumulator/combiner và bảo đảm không can thiệp nguồn. Mutable container **riêng từng nhóm** là ý tưởng khác với mutable identity chung trong reduce.

## 10. Kiểm tra ba luật bằng code nhỏ

### 10.1. Identity

~~~java
int identity = 0;
BinaryOperator<Integer> combiner = Integer::sum;
int u = 7;

System.out.println(combiner.apply(identity, u) == u); // true
System.out.println(combiner.apply(u, identity) == u); // true
~~~

### 10.2. Associativity

~~~java
int a = 3, b = 4, c = 5;
int left = combiner.apply(combiner.apply(a, b), c);
int right = combiner.apply(a, combiner.apply(b, c));
System.out.println(left == right); // true
~~~

### 10.3. Compatibility

~~~java
BiFunction<Integer, String, Integer> accumulator =
    (sum, word) -> sum + word.length();

int u = 10;
String t = "Go";

int left = combiner.apply(
    u, accumulator.apply(identity, t));
int right = accumulator.apply(u, t);

System.out.println(left == right); // true
~~~

Kiểm tra vài giá trị giúp đọc rõ quy tắc nhưng **không chứng minh luật đúng với mọi input**. Với mã quan trọng, dùng property-based testing để kiểm tra nhiều giá trị, empty input, giá trị biên, sự thay đổi thứ tự có liên quan và các phân vùng khác nhau.

### 10.4. Kiểm thử phân vùng giả lập

~~~java
int partA = List.of("Java").stream()
    .reduce(0, accumulator, combiner);
int partB = List.of("Go").stream()
    .reduce(0, accumulator, combiner);

int combined = combiner.apply(partA, partB);
System.out.println(combined); // 6
~~~

Nếu dùng phép trừ để ghép partA và partB, combined = 2, khác với giảm tuần tự 6. Cách test này tái hiện lỗi **không phụ thuộc số thread**, giúp phát hiện mismatch ngay cả khi máy hiện tại chạy parallel theo lịch khác.

## 11. Chương trình Java 17+ hoàn chỉnh

Bài tập sau thực hiện cả các phép đúng và phản ví dụ sai **một cách có kết quả xác định**. Đoạn code dùng hai phần giả lập để chứng minh lỗi combiner/identity, không yêu cầu Java parallel stream phải tình cờ chia theo một cách nhất định.

Tạo tệp **ReduceCompatibilityDemo.java**:

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.IntStream;

public class ReduceCompatibilityDemo {
    static int totalLength(List<String> words, boolean parallel) {
        var source = parallel ? words.parallelStream() : words.stream();
        return source.reduce(
            0,
            (total, word) -> total + word.length(),
            Integer::sum
        );
    }

    public static void main(String[] args) {
        List<String> words = List.of("Java", "Go", "Lambda", "API");
        BiFunction<Integer, String, Integer> accumulator =
            (total, word) -> total + word.length();
        BinaryOperator<Integer> combiner = Integer::sum;
        int identity = 0;

        int u = 10;
        String t = "Go";
        int left = combiner.apply(u, accumulator.apply(identity, t));
        int right = accumulator.apply(u, t);
        System.out.println("compatibility=" + (left == right));
        System.out.println("sequential=" + totalLength(words, false));
        System.out.println("parallel=" + totalLength(words, true));

        int partA = List.of("Java").stream()
            .reduce(0, accumulator, combiner);
        int partB = List.of("Go").stream()
            .reduce(0, accumulator, combiner);
        System.out.println("correct-merge=" + combiner.apply(partA, partB));
        System.out.println("wrong-merge=" + (partA - partB));

        int wrongIdentitySequential = List.of("Java", "Go").stream()
            .reduce(10, accumulator, combiner);
        int wrongIdentitySplit =
            (10 + "Java".length()) + (10 + "Go".length());
        System.out.println("wrong-identity-sequential=" +
            wrongIdentitySequential);
        System.out.println("wrong-identity-split=" + wrongIdentitySplit);

        String labels = words.parallelStream().reduce(
            "",
            (text, word) -> text + "[" + word + "]",
            String::concat
        );
        System.out.println("labels=" + labels);

        long sum = IntStream.rangeClosed(1, 1_000)
            .boxed().parallel()
            .reduce(0L, (total, number) -> total + number, Long::sum);
        System.out.println("sum1000=" + sum);

        String joined = words.parallelStream().collect(
            StringBuilder::new,
            (builder, word) -> builder.append(word),
            StringBuilder::append
        ).toString();
        System.out.println("collected=" + joined);
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ReduceCompatibilityDemo.java
java ReduceCompatibilityDemo
~~~

**Stdout chính xác:**

~~~text
compatibility=true
sequential=15
parallel=15
correct-merge=6
wrong-merge=2
wrong-identity-sequential=16
wrong-identity-split=26
labels=[Java][Go][Lambda][API]
sum1000=500500
collected=JavaGoLambdaAPI
~~~

Giải thích:

- **compatibility=true:** hai vế của phương trình với u=10, t="Go" đều bằng 12.
- **sequential=15** và **parallel=15:** tổng bốn độ dài 4+2+6+3 đúng trong cả hai cách xử lý.
- **correct-merge=6:** ghép hai phân vùng độc lập bằng cộng.
- **wrong-merge=2:** ghép cùng hai phân vùng bằng trừ; đây là kết quả sai được cố ý minh họa.
- **wrong-identity-sequential=16:** một lượt cộng bắt đầu từ 10, rồi thêm 4 và 2.
- **wrong-identity-split=26:** mỗi phân vùng bắt đầu từ 10, sau đó kết quả 14 và 12 bị cộng lại.
- **labels:** String immutable với identity rỗng và combiner concat phù hợp cho nối nhãn của ordered stream.
- **sum1000=500500:** giảm 1000 Integer thành Long, cho tổng 1+2+...+1000.
- **collected:** dùng collect và StringBuilder để tích lũy chuỗi qua container thay vì mutate identity của reduce.

Trong ví dụ, những đường sai được mô phỏng tường minh, **không dùng một phép reduce song song sai rồi khẳng định stdout luôn phải là 2 hoặc 26**. Đây là cách trình bày có thể kiểm thử ổn định trên JDK 17.

## 12. Reduce một và hai toán tử có liên quan gì?

Stream còn có overload:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);
Optional<T> reduce(BinaryOperator<T> accumulator);
~~~

Dạng hai đối số làm việc với **T là cả phần tử nguồn lẫn kết quả tích lũy**, dùng một BinaryOperator để giảm. Dạng không có identity trả Optional<T> vì có thể không có phần tử.

~~~java
int sum = Stream.of(2, 3, 4)
    .reduce(0, Integer::sum);
~~~

Với ba đối số, khi T và U khác nhau, ta tách chức năng thêm phần tử T vào U khỏi chức năng ghép hai kết quả U. Hai chức năng phải thống nhất với nhau thông qua phương trình compatibility. Các overload khác vẫn phải tuân thủ identity/associativity tương ứng để dùng đúng.

## 13. Chọn kiểu U phù hợp và cân nhắc API khác

### 13.1. Chỉ đếm phần tử

~~~java
long count = words.parallelStream().reduce(
    0L,
    (total, word) -> total + 1L,
    Long::sum
);
~~~

Cách này có thể đúng về đại số, nhưng **Stream.count()** mô tả ý định gọn hơn, và đôi khi được tối ưu tốt hơn.

### 13.2. Chỉ tính tổng độ dài

~~~java
long total = words.stream()
    .mapToLong(String::length)
    .sum();
~~~

Cách này thường đơn giản hơn reduce ba đối số nếu mục tiêu chỉ là tổng số học, đồng thời tránh một phần boxing của kết quả trung gian.

### 13.3. Nhiều thống kê trong một kết quả U

Có thể dùng record immutable:

~~~java
record Summary(long count, long length) {}

Summary result = words.parallelStream().reduce(
    new Summary(0, 0),
    (summary, word) -> new Summary(
        summary.count() + 1,
        summary.length() + word.length()
    ),
    (left, right) -> new Summary(
        left.count() + right.count(),
        left.length() + right.length()
    )
);
~~~

Identity là (0,0). Accumulator thêm một phần tử: count+1, length+word.length. Combiner cộng các trường tương ứng giữa hai Summary. Phương trình tương thích đúng trên từng component nếu không có lỗi số học.

Tuy nhiên, tạo record mới cho mỗi phần tử có thể phát sinh allocation đáng kể với dữ liệu rất lớn. Nếu cần hiệu năng, có thể dùng collector mutable được thiết kế đúng hoặc công cụ thống kê tiêu chuẩn thích hợp, sau khi đo đạc.

## 14. Những lỗi phổ biến

**Lỗi 1 — combiner khác ý nghĩa accumulator:** accumulator cộng nhưng combiner trừ có thể biên dịch và chạy tuần tự ổn, nhưng sai khi chia nhóm.

**Lỗi 2 — identity không trung hòa:** mỗi phân vùng có thể áp dụng lại identity, làm offset được tính nhiều lần.

**Lỗi 3 — toán tử không kết hợp:** phép trừ, phép chia và các bước phụ thuộc thứ tự không thích hợp để đổi cách đặt ngoặc tùy ý.

**Lỗi 4 — nhầm T với U:** ở Stream<String> giảm thành Integer, combiner phải ghép hai Integer chứ không phải hai String.

**Lỗi 5 — chỉ test tuần tự:** combiner có thể ít hoặc không được dùng trong tuần tự; phải test nhiều cách chia và ghép.

**Lỗi 6 — dùng mutable identity trong reduce:** chia sẻ cùng StringBuilder/ArrayList làm sai mô hình reduction. Dùng immutable U hoặc collect.

**Lỗi 7 — side effect trong accumulator:** không sửa Collection nguồn, global variable hoặc database từ callback khi số lần gọi không được bảo đảm.

**Lỗi 8 — nghĩ associative đồng nghĩa commutative:** nối String associative nhưng không commutative; vẫn phải quan tâm encounter order.

**Lỗi 9 — quên tính toán số thực:** thứ tự cộng double có thể gây chênh lệch do làm tròn, cần kiểm thử sai số theo yêu cầu.

**Lỗi 10 — dùng String concatenation lớn mà không xem xét hiệu năng:** đúng luật không có nghĩa chạy tối ưu; có thể dùng Collectors.joining hoặc StringBuilder trong collect.

**Lỗi 11 — dùng reduce cho mọi phép tổng hợp:** count, mapToLong().sum(), min/max và collect có thể rõ hơn.

**Lỗi 12 — giả định lịch parallel cố định:** không dựa vào số thread hoặc số lần combiner chạy để chứng minh kết quả.

**Lỗi 13 — bỏ qua overflow và giá trị null:** giá trị vượt phạm vi, null element hoặc exception làm pipeline không đạt hợp đồng nghiệp vụ.

**Lỗi 14 — coi type-check là proof của phép giảm:** compiler kiểm tra chữ ký, không chứng minh identity, associativity hay compatibility.

## 15. Checklist review reduce ba đối số

| Câu hỏi | Kiểm tra |
| --- | --- |
| T và U là gì? | T là phần tử đầu vào; U là giá trị tổng hợp |
| Identity đúng? | Ghép identity không làm đổi U |
| Combiner associative? | Ghép theo hai cách đặt ngoặc cho cùng nghĩa |
| Accumulator compatible? | combiner(u, accumulator(identity,t)) = accumulator(u,t) |
| Có mutation identity? | Không mutate cùng object U chia sẻ; dùng collect nếu cần |
| Có sửa nguồn hoặc global state? | Callback stateless và non-interfering |
| Kết quả phụ thuộc thứ tự? | Xem encounter order và phép toán |
| Có sai số hoặc overflow? | Xác định kiểu số, precision, giới hạn |
| Test nhiều phân vùng? | So sequential, parallel và ghép nhóm giả lập |
| Có API phù hợp hơn? | count, sum, collect hoặc collector khác |

## 16. Câu hỏi tự kiểm tra

1. Vì sao accumulator nhận U và T nhưng combiner nhận U và U?
2. Hãy diễn giải hai vế của phương trình compatibility bằng tổng độ dài chuỗi.
3. Vì sao phép cộng độ dài tương thích với Integer::sum?
4. Tại sao identity=10 sai khi combiner là phép cộng?
5. Vì sao accumulator cộng nhưng combiner trừ có thể biên dịch mà vẫn sai?
6. Làm sao mô phỏng hai phân vùng để kiểm thử mà không phụ thuộc lịch parallel stream?
7. Tính kết hợp và tính giao hoán khác nhau thế nào?
8. Vì sao StringBuilder mutable phù hợp với collect hơn reduce?
9. Khi nào nên dùng mapToLong(...).sum() thay reduce ba đối số?
10. Một record Summary(count,length) có thể có identity, accumulator và combiner nào?
11. Vì sao synchronized không tự sửa được bài toán mutable identity?
12. Vì sao tổng double có thể đổi chút ít khi chia nhóm?
13. Vì sao callback không được sửa Collection đang xử lý?
14. Nếu chuyển một stream tuần tự sang song song, bạn sẽ kiểm tra những hợp đồng nào?

**Kết luận:** Với Stream.reduce(identity, accumulator, combiner), **xử lý phần tử trực tiếp bằng accumulator phải tương đương xử lý phần tử ở một phân vùng riêng rồi ghép qua combiner**. Để bảo đảm điều đó, cần identity trung hòa, combiner kết hợp được và phương trình compatibility đúng, đồng thời callback không can thiệp nguồn hoặc dựa vào trạng thái dùng chung. Khi cần xây dựng container mutable, sử dụng collect hoặc Collector có hợp đồng phù hợp.
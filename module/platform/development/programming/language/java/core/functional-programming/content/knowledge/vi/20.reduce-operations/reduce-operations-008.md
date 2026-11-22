# Không dùng đối tượng tích lũy có thể thay đổi chung trong reduce() — Java Stream

## 1. Mục tiêu

**Stream.reduce()** là thao tác rút gọn (reduction) nhiều phần tử thành một kết quả. Nó rất thích hợp để tính tổng, tích, giá trị lớn nhất, hoặc tổng hợp bằng phép kết hợp có **tính kết hợp (associative)** và có **phần tử đơn vị (identity)**.

Một lỗi nguy hiểm là truyền một **đối tượng mutable**, chẳng hạn **ArrayList**, **StringBuilder**, **HashMap** hoặc một đối tượng chứa bộ đếm, làm identity cho reduce rồi **sửa trực tiếp nó trong accumulator**. Trong parallel stream, identity có thể bị nhiều nhánh xử lý chia sẻ; combiner còn có thể nhận các tham chiếu trùng nhau. Hậu quả có thể là race condition, phần tử bị nhân bản, mất dữ liệu hoặc kết quả phụ thuộc chiến lược thực thi. Dùng một container thread-safe cũng không tự sửa được hợp đồng reduce.

Bài học giúp bạn:

- Hiểu ba overload **reduce()** và sự khác biệt giữa identity, accumulator và combiner.
- Biết tại sao các hàm của reduce cần **stateless**, **non-interfering**, cùng các quy tắc identity, associativity và compatibility.
- Phân tích chính xác vì sao **reduce(new ArrayList<>(), ...)** hoặc **reduce(new StringBuilder(), ...)** với lambda mutate là sai.
- Dùng **reduce** cho giá trị bất biến hoặc phép rút gọn thích hợp; dùng **collect** khi muốn tạo/mutate một container tích lũy.
- Phân biệt trạng thái có thể thay đổi **nội bộ một container do collector tạo riêng** với **trạng thái mutable chung ngoài pipeline**.
- Kiểm thử sequential và parallel, hiểu các giới hạn khi tổng hợp dữ liệu tiền tệ, phép cộng overflow, string concatenation và hiệu ứng phụ.

## 2. Reduce là rút gọn, không phải vòng lặp mutate tùy ý

Một ví dụ đơn giản:

~~~java
int total = java.util.stream.IntStream.of(2, 4, 6)
        .reduce(0, Integer::sum);

System.out.println(total); // 12
~~~

**0** là identity của phép cộng; **Integer::sum** là phép kết hợp hai số nguyên. Tính chất quan trọng:

- **Identity:** 0 + x = x và x + 0 = x.
- **Associativity:** (a + b) + c = a + (b + c), xét trong miền giá trị/semantics phù hợp.
- **Không cần một đối tượng dùng chung bị sửa:** mỗi kết quả số được tính từ các đối số và trả về như giá trị.

Trong Java int, phép cộng thông thường có quy tắc overflow modulo 2^32; với chính quy tắc đó, phép cộng int vẫn có tính kết hợp. Nhưng nó có thể tạo giá trị âm hoặc sai ý nghĩa kinh doanh khi số vượt miền int. Nếu cần tổng lớn chính xác, chọn **long**, **BigInteger** hoặc kiểu tiền tệ phù hợp, thay vì hiểu identity/associativity là đủ để loại bỏ vấn đề overflow.

### 2.1. Cấu trúc pipeline

~~~text
Stream<T>
    |
    v
map / filter / ...
    |
    v
reduce(identity, accumulator, combiner)
    |
    +-- gộp phần tử thành các kết quả từng phần
    |
    +-- kết hợp các kết quả từng phần
    |
    v
kết quả U
~~~

Trong sequential stream, reduce có thể trông giống một vòng lặp cập nhật biến. Tuy nhiên, API còn phải hỗ trợ chia công việc thành nhiều phần và **gộp kết quả** khi parallel. Vì vậy các đối số của reduce có hợp đồng mạnh hơn “code của tôi chạy đúng khi duyệt một lượt”.

## 3. Ba overload reduce() quan trọng

### 3.1. reduce(BinaryOperator<T>): không cần identity

Chữ ký:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Dùng khi kết quả có thể không tồn tại, chẳng hạn tìm cực đại trên stream rỗng:

~~~java
Optional<Integer> maximum = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(maximum.orElse(-1)); // 9

Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::max);
System.out.println(none.isEmpty()); // true
~~~

Đoạn minh họa cần import **List**, **Optional**, **Stream**. Với nguồn rỗng, kết quả là **Optional.empty()**, vì không có phần tử đầu để làm giá trị ban đầu. Hàm được truyền cần phù hợp với phép kết hợp các kết quả từng phần.

### 3.2. reduce(identity, BinaryOperator<T>): có identity cùng kiểu

Chữ ký:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Ví dụ:

~~~java
long total = LongStream.of(100, 200, 300)
        .reduce(0L, Long::sum);

System.out.println(total); // 600
~~~

**identity phải là phần tử đơn vị của phép rút gọn**, không phải “giá trị khởi tạo bất kỳ” được cộng vào đúng một lần theo cảm tính.

Ví dụ sai khi muốn tính **10 + tổng các số**:

~~~java
// Không dùng 10 làm identity của phép cộng:
// int wrong = Stream.of(1, 2, 3).parallel()
//         .reduce(10, Integer::sum);
~~~

Trong sequential pipeline nó có thể cho 16, nhưng khi chia nguồn thành nhiều nhánh, identity 10 có thể được áp dụng ở mỗi nhánh; kết quả không được bảo đảm là 16. Cách đúng:

~~~java
int result = 10 + IntStream.of(1, 2, 3).parallel().sum();
System.out.println(result); // 16
~~~

Nếu giá trị ban đầu có ý nghĩa nghiệp vụ ngoài phép rút gọn, hãy **cộng/ghép nó sau khi tổng hợp** hoặc thiết kế một monoid hợp lệ thay vì giả làm identity.

### 3.3. reduce(identity, accumulator, combiner): kết quả khác kiểu phần tử

Chữ ký rút gọn:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

- **T:** kiểu phần tử nguồn.
- **U:** kiểu kết quả tích lũy.
- **identity:** một giá trị đơn vị kiểu U.
- **accumulator:** nhận kết quả U hiện tại và phần tử T, **trả một U**.
- **combiner:** kết hợp hai kết quả U thành một U.

Ví dụ biến danh sách String thành tổng độ dài **mà không mutate một đối tượng kết quả chung**:

~~~java
int length = List.of("Java", "Go", "C").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                Integer::sum
        );

System.out.println(length); // 7
~~~

Đây là ví dụ mảnh ghép đặt trong ngữ cảnh đã import List. **subtotal + text.length()** tạo kết quả int mới, thay vì sửa một container dùng chung. **Integer::sum** kết hợp hai subtotal hợp lệ.

## 4. Hợp đồng đại số của reduce

Để kết quả có ý nghĩa nhất quán khi Stream thay đổi cách chia và ghép công việc, người viết phải đáp ứng các điều kiện phù hợp.

### 4.1. Identity đúng

Với phép kết hợp **⊕**, một identity e phải thỏa:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

Ví dụ:

| Phép rút gọn | Identity | Phép kết hợp |
| --- | --- | --- |
| Tổng số nguyên | 0 | cộng |
| Tích số nguyên | 1 | nhân |
| Nối chuỗi | chuỗi rỗng | nối chuỗi |
| Tập hợp hợp nhất không thay đổi đối số | tập rỗng theo mô hình immutable | union tạo tập mới |
| Cực đại có giới hạn miền rõ ràng | phần tử nhỏ nhất thích hợp, hoặc reduce không identity | max |

Nếu không xác định được identity tự nhiên, dùng **reduce(BinaryOperator)** trả **Optional** có thể diễn đạt chính xác hơn so với tự đặt một sentinel không phù hợp.

### 4.2. Tính kết hợp — associativity

Một phép kết hợp phải thỏa:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

**Phép cộng thông thường** là ví dụ tiêu biểu; **phép trừ** không có tính kết hợp:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Nếu dùng phép trừ trong reduce trên parallel stream, việc thay đổi cách chia/ghép có thể làm kết quả thay đổi. Không dùng reduce như một bộ máy thực thi “phần tử thứ nhất trừ phần tử thứ hai rồi trừ phần tử thứ ba” khi bạn cần thứ tự đó mà vẫn mong parallel tương đương.

Với số thực **double**, phép cộng trong toán học có tính kết hợp nhưng tính toán IEEE 754 có **làm tròn ở các bước trung gian**; vì vậy tổng theo những cách ghép khác nhau có thể chênh lệch do sai số floating-point. Nếu kết quả tài chính cần tính chính xác, cần kiểu và quy tắc làm tròn phù hợp, chẳng hạn **BigDecimal**.

### 4.3. Compatibility của accumulator và combiner

Với overload ba đối số, Java còn yêu cầu accumulator và combiner **tương thích**. Trực giác: thêm một phần tử T vào subtotal U phải tương đương với việc gom phần tử ấy vào một subtotal mới tạo từ identity, rồi kết hợp lại.

Có thể viết điều kiện:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

Với **U là int**, **T là String**, accumulator là **subtotal + length**, identity là **0**, combiner là **Integer::sum**:

~~~text
u + (0 + length(t)) = u + length(t)
~~~

Hợp đồng này giúp các nhánh parallel có thể tổng hợp một phần rồi ghép về kết quả chung.

### 4.4. Stateless và non-interfering

Các behavioral parameter của Stream nói chung cần:

- **Non-interfering:** không sửa nguồn Stream đang duyệt.
- **Stateless:** kết quả của lambda không phụ thuộc vào một trạng thái mutable bên ngoài thay đổi theo lượt gọi.
- Với reduce, phải tôn trọng thêm identity, associativity và compatibility.

**Không dùng một biến bên ngoài như tổng toàn cục để thay cho kết quả trả về từ accumulator.** Cách này làm phép rút gọn phụ thuộc vào số lượt và thứ tự callback, đặc biệt dễ sai với parallel.

## 5. Phản ví dụ: reduce(new ArrayList<>(), ...)

Một lỗi phổ biến:

~~~java
List<String> source = List.of("A", "B", "C");

List<String> result = source.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);  // Sai: mutate identity/subtotal.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right); // Sai: giả định hai list độc lập.
                    return left;
                }
        );
~~~

**Đây là phản ví dụ có chủ đích; không chạy trong ứng dụng.** Nó có thể biên dịch nếu import List, ArrayList, nhưng **vi phạm hợp đồng giảm**, không có kết quả đáng tin khi chạy song song.

Tại sao sai?

1. **Identity là một đối tượng ArrayList mutable** được tạo một lần rồi chuyển cho reduce.
2. Lambda accumulator nhận tham chiếu list và **sửa chính đối tượng đó**. Việc trả list không biến nó thành một giá trị U độc lập.
3. Khi xử lý song song, các nhánh có thể sử dụng chung hoặc nhìn thấy cùng identity. **ArrayList không thread-safe**, nên các lệnh add có thể race, làm mất dữ liệu hoặc khiến cấu trúc sai.
4. Combiner giả định **left** và **right** là hai kết quả riêng. Nhưng chúng có thể tham chiếu **cùng đối tượng**. Khi gọi **left.addAll(right)** với cùng tham chiếu, dữ liệu có thể bị nhân bản hoặc phát sinh lỗi.
5. Kể cả chạy tuần tự và có vẻ cho kết quả đúng, identity đã bị thay đổi, vi phạm kỳ vọng của phép rút gọn. Ví dụ chạy đúng tình cờ không biến cách viết thành hợp lệ cho parallel.

Cần phân biệt: vấn đề không chỉ là ArrayList “không có khóa”. **Một mutable identity chia sẻ là sai mô hình** ngay cả khi bạn bao nó bằng một collection synchronized.

### 5.1. Tại sao synchronizedList không giải quyết hoàn toàn?

Có thể nghĩ đến:

~~~java
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());
~~~

Ngay cả nếu sử dụng **shared** làm identity và mọi add riêng lẻ được bảo vệ, combiner vẫn có thể gặp **left == right** rồi ghép chính list đó vào nó; phép rút gọn không còn tương đương phép kết hợp hợp lệ. Thêm khóa chỉ xử lý một phần vấn đề race, **không tạo ra identity độc lập và không sửa luật đại số**.

Một implementation “may mắn chạy ra đúng trong ba phần tử” vẫn không có bảo đảm khi dữ liệu lớn, máy khác, mức parallelism khác hoặc optimizer thay đổi.

## 6. Phản ví dụ: StringBuilder trong reduce

**StringBuilder** có thể nối chuỗi hiệu quả khi làm việc cục bộ, nhưng không thích hợp làm **identity mutable chung** cho reduce như sau:

~~~java
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                (builder, item) -> builder.append(item),
                (left, right) -> left.append(right)
        );
~~~

Đoạn này cũng có thể biên dịch, nhưng **không phải phép rút gọn hợp lệ**:

- **append** sửa đối tượng receiver.
- Nhiều nhánh có thể cùng thấy một identity.
- **StringBuilder không thread-safe**.
- Combiner có thể nối một builder với chính nó, gây dữ liệu trùng/không mong đợi.
- Ngay cả khi không chạy song song, kết quả dựa vào mutation và aliasing chứ không tuân thủ kiểu kết hợp value-oriented mà reduce mong đợi.

**StringBuffer** có phương thức synchronized cũng không biến công thức reduce trên thành thiết kế đúng. Đừng sửa bằng đổi class mutable; hãy đổi **abstraction** sang collect hoặc dùng một phép rút gọn không mutation.

## 7. Cách đúng thứ nhất: reduce với kết quả bất biến

Dùng **reduce** khi mỗi lần kết hợp tạo một kết quả mới hoặc dùng một giá trị có semantics bất biến.

### 7.1. Tổng số

~~~java
long total = List.of(10L, 20L, 30L).parallelStream()
        .reduce(0L, Long::sum);

System.out.println(total); // 60
~~~

**Long** là immutable wrapper; accumulator trả Long mới theo semantics giá trị. Không có object accumulator mutable chung.

Nếu làm việc với số nguyên thủy lớn, có thể dùng **mapToLong(...).sum()** để biểu đạt phép cộng trực tiếp hơn và tránh boxing của Stream<Long> khi không cần.

### 7.2. Nối String immutable

~~~java
String joined = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", String::concat);

System.out.println(joined); // ABC
~~~

String là immutable. **""** là identity của phép nối, và phép nối chuỗi có tính kết hợp về nội dung. Với ordered stream, kết quả theo thứ tự gặp là ABC.

Nhưng cách này có thể tạo nhiều String trung gian khi nguồn lớn. Nếu mục tiêu là xây chuỗi dài hiệu quả, **Collectors.joining** hoặc **collect(StringBuilder::new,...)** thường phù hợp hơn về chi phí sao chép.

### 7.3. BigDecimal cho phép cộng chính xác

~~~java
BigDecimal total = Stream.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).parallel().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
~~~

**BigDecimal** là immutable. Ở đây không truyền MathContext làm tròn tại mỗi phép cộng; các giá trị được cộng chính xác. Nếu áp dụng làm tròn theo từng bước, tính kết hợp theo kết quả làm tròn có thể không còn như mong muốn; chính sách làm tròn phải được thiết kế ở ranh giới phù hợp.

## 8. Cách đúng thứ hai: collect cho mutable reduction

Nếu mục tiêu là **tạo một container và thêm từng phần tử**, dùng **collect**, không dùng reduce với một identity mutable.

### 8.1. collect(Supplier, BiConsumer, BiConsumer)

Chữ ký rút gọn:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner)
~~~

Ba phần khác hẳn reduce:

- **supplier:** tạo **một container kết quả mới** khi cần. Trong parallel reduction, nhiều container riêng có thể được tạo cho các phần công việc.
- **accumulator:** cập nhật container của phần công việc bằng một phần tử T; đây là **mutable reduction có chủ đích**.
- **combiner:** trộn **nội dung của container thứ hai vào container thứ nhất** khi các phần công việc được gộp.
- **Kết quả:** một container R được trả về cho caller.

Ví dụ:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(result); // [A, B, C]
~~~

Với ordered Stream từ **Stream.of**, collect bảo toàn encounter order theo ngữ nghĩa kết quả; nhiều ArrayList nội bộ có thể được tạo riêng và hợp nhất, không phải dùng một identity ArrayList chung cho mọi nhánh. Bản thân ArrayList vẫn **không thread-safe nếu bạn dùng chung nó ở bên ngoài** sau collect; collect không trao quyền truy cập đồng thời an toàn cho mọi thao tác về sau.

### 8.2. StringBuilder qua collect

~~~java
String result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();

System.out.println(result); // ABC
~~~

Ở đây **supplier** tạo StringBuilder riêng cho các phần tổng hợp; accumulator thêm ký tự vào builder của phần đó; combiner nối hai builder để tạo kết quả hợp nhất. Đây là đúng kiểu API dành cho **mutable accumulation**.

**Phân biệt then chốt:** collect cho phép mutate **container do supplier tạo để phục vụ phép gom**, không đồng nghĩa bạn được mutate **một container global** được tất cả lambda capture.

### 8.3. Collector có sẵn thường dễ đọc hơn

Trong ứng dụng, thường chọn một collector tiêu chuẩn:

~~~java
List<String> names = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toList());

String csv = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining(","));

System.out.println(names); // [A, B, C]
System.out.println(csv);   // A,B,C
~~~

**Collectors.toList()** không cam kết loại implementation hay tính mutable của List kết quả. Nếu cần bảo đảm một ArrayList mutable, dùng collector cung cấp collection factory, ví dụ **Collectors.toCollection(ArrayList::new)**. Nếu cần danh sách unmodifiable, với Java 17 có thể dùng **Stream.toList()** hoặc collector thích hợp theo semantics mong muốn.

### 8.4. Collect không tự bảo đảm thread safety cho side effect khác

Sai lầm khác:

~~~java
List<String> shared = new ArrayList<>();

List<String> result = source.parallelStream()
        .collect(
                ArrayList::new,
                (local, item) -> {
                    shared.add(item); // Sai: sửa một list ngoài dùng chung.
                    local.add(item);
                },
                ArrayList::addAll
        );
~~~

Đây là phản ví dụ. Dù container **local** do supplier tạo được quản lý như mutable reduction, việc ghi vào **shared** từ nhiều task vẫn là side effect chia sẻ, có nguy cơ race và không thuộc hợp đồng gom dữ liệu an toàn của collector. Chỉ sửa container được cung cấp cho accumulator, tuân thủ thiết kế của Collector và các ràng buộc bổ sung nếu dùng collector concurrent.

## 9. Chương trình Java 17 hoàn chỉnh: tổng doanh thu và danh sách ID

Chương trình này cố ý **không chạy ví dụ reduce mutable sai**. Thay vào đó, nó kiểm chứng những mẫu đúng: reduce cho long và BigDecimal, reduce trả Optional, collect vào ArrayList/StringBuilder và Collectors.joining.

Tạo file **SafeReductionDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SafeReductionDemo {
    record Sale(String id, int quantity, long unitPriceVnd) {
        long amount() {
            return Math.multiplyExact((long) quantity, unitPriceVnd);
        }
    }

    static long revenue(List<Sale> sales, boolean parallel) {
        Stream<Sale> pipeline = parallel
                ? sales.parallelStream()
                : sales.stream();

        return pipeline
                .mapToLong(Sale::amount)
                .reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2, 1_500),
                new Sale("B", 1, 700),
                new Sale("C", 3, 400)
        );

        long sequential = revenue(sales, false);
        long parallel = revenue(sales, true);

        System.out.println("sequential revenue: " + sequential);
        System.out.println("parallel revenue: " + parallel);

        List<String> ids = sales.parallelStream()
                .map(Sale::id)
                .collect(ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll);
        System.out.println("collected ids: " + ids);

        StringBuilder builder = sales.parallelStream()
                .map(Sale::id)
                .collect(StringBuilder::new,
                        StringBuilder::append,
                        StringBuilder::append);
        System.out.println("builder: " + builder);

        String joined = sales.parallelStream()
                .map(Sale::id)
                .collect(Collectors.joining(","));
        System.out.println("joined: " + joined);

        Optional<Long> biggest = sales.stream()
                .map(Sale::amount)
                .reduce(Long::max);
        Optional<Long> emptyBiggest = Stream.<Long>empty()
                .reduce(Long::max);

        System.out.println("max amount: " + biggest.orElse(-1L));
        System.out.println("empty max present: "
                + emptyBiggest.isPresent());

        BigDecimal decimal = Stream.of(
                new BigDecimal("0.10"),
                new BigDecimal("0.20")
        ).parallel().reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("decimal sum: " + decimal);

        System.out.println("source quantities: "
                + sales.stream().map(Sale::quantity).toList());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SafeReductionDemo.java
java SafeReductionDemo
~~~

**Đầu ra của chương trình:**

~~~text
sequential revenue: 4900
parallel revenue: 4900
collected ids: [A, B, C]
builder: ABC
joined: A,B,C
max amount: 3000
empty max present: false
decimal sum: 0.30
source quantities: [2, 1, 3]
~~~

### 9.1. Tại sao cả hai phép tính doanh thu đều ra 4900?

- A: 2 × 1.500 = 3.000.
- B: 1 × 700 = 700.
- C: 3 × 400 = 1.200.
- Tổng: 3.000 + 700 + 1.200 = **4.900**.

**mapToLong(Sale::amount)** sinh giá trị long cho mỗi Sale; **reduce(0L, Long::sum)** rút gọn bằng phép cộng với identity hợp lệ. Vì không dùng một subtotal mutable chung, cùng nguồn dữ liệu ổn định cho cùng kết quả số trong chương trình tuần tự lẫn song song.

**Math.multiplyExact** phát hiện overflow của phép nhân mỗi mặt hàng. Đoạn ví dụ dùng **Long::sum** cho phép cộng tổng; với dữ liệu production có thể vượt phạm vi long, cần kiểm tra overflow của tổng hoặc chọn BigInteger/BigDecimal theo yêu cầu. Không nên suy luận vì từng phép nhân an toàn thì tổng nhiều phần tử cũng chắc chắn nằm trong long.

### 9.2. Tại sao collected ids và builder vẫn đúng khi parallel?

**collect** dành cho mutable reduction:

- Tạo các container nội bộ qua **ArrayList::new** hoặc **StringBuilder::new**.
- Từng phần công việc đưa phần tử vào container của nó.
- Gộp các container theo combiner phù hợp.

Với **List** nguồn có encounter order, kết quả hiển thị **[A,B,C]** và **ABC** theo thứ tự nguồn. Không nên dựa vào thứ tự **lời gọi** accumulator/combiner ở các thread, mà dựa vào **semantics của kết quả có thứ tự**.

**Collectors.joining(",")** giúp tạo một String có dấu phẩy một cách thuận tiện, tránh tự viết logic separator.

### 9.3. Optional từ reduce không identity

**reduce(Long::max)** không có identity nên trả **Optional<Long>**. Trong dữ liệu có giá trị, max=3000. Với Stream.empty, Optional rỗng và isPresent=false. Điều này tốt hơn việc chọn một sentinel bất kỳ nếu cả miền long có thể là dữ liệu hợp lệ.

### 9.4. BigDecimal không mutate

**BigDecimal.ZERO** và **BigDecimal::add** không làm thay đổi BigDecimal cũ; phép cộng tạo kết quả mới. Dãy 0.10 và 0.20 cho **0.30**. Nếu dùng quy tắc rounding ở mỗi bước hoặc dữ liệu số thực double, cần phân tích thêm độ chính xác và tính kết hợp.

## 10. Vậy collect có được mutate không?

**Có, nhưng phải đúng phạm vi.** Mục đích của collect là mutable reduction. Phân biệt hai dạng:

**Đúng:**

~~~java
List<String> out = values.parallelStream()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
~~~

Ở đây accumulator nhận container do supplier tạo cho quá trình gom; code không tự đưa một ArrayList chung vào cho mọi nhánh.

**Sai:**

~~~java
List<String> shared = new ArrayList<>();
List<String> out = values.parallelStream()
        .collect(
                () -> shared,    // Sai: mọi lời supplier trả cùng object.
                List::add,
                List::addAll
        );
~~~

Đây là phản ví dụ. Supplier của collect **phải cung cấp container mới phù hợp**, không trả một đối tượng shared duy nhất. Nếu mọi nhánh nhận cùng tham chiếu, lại xuất hiện race/aliasing và combiner có thể hợp nhất một đối tượng với chính nó.

**Quy tắc thực hành:** nếu lambda phải tham chiếu biến **shared** bên ngoài để thêm/cộng trong khi giảm dữ liệu, hãy đặt câu hỏi liệu bạn đang né hợp đồng của collect/reduce hay không.

## 11. Ba mức an toàn phải tách riêng

Một thiết kế reduction đúng có ít nhất ba câu hỏi độc lập:

1. **An toàn kiểu (type safety):** compiler chấp nhận kiểu trả về, accumulator và combiner hay không?
2. **Đúng đại số và phân hoạch:** identity/associativity/compatibility có cho phép chia và gộp công việc thành cùng một kết quả không?
3. **An toàn đồng thời và ownership:** có một object mutable bị nhiều nhánh sửa hoặc combiner nhận alias mà code không xử lý được không?

Biên dịch thành công chỉ trả lời câu hỏi thứ nhất. **Collections.synchronizedList**, **AtomicInteger**, synchronized block hoặc lock có thể xử lý một số race, nhưng không tự tạo identity đúng hoặc compatibility đúng. Không nên coi “đã khóa rồi nên reduce sẽ đúng”.

### 11.1. AtomicInteger trong reduce có phải giải pháp?

Nếu dùng **AtomicInteger** làm một identity mutable:

~~~java
// Không dùng như identity mutable trong reduce:
// AtomicInteger shared = new AtomicInteger();
// stream.parallel().reduce(
//     shared,
//     (counter, n) -> { counter.addAndGet(n); return counter; },
//     (a, b) -> { a.addAndGet(b.get()); return a; }
// );
~~~

Dù phép tăng atomic, combiner có thể nhận cùng đối tượng a==b, rồi cộng lại giá trị của chính nó; semantic rút gọn không còn đúng. Dùng **mapToInt(...).sum()** hoặc **reduce(0, Integer::sum)** cho tổng, hay **collect** khi thực sự cần cấu trúc mutable kết quả.

### 11.2. Stateful callback cũng là rủi ro

Một reducer có thể tạo giá trị mới nhưng vẫn sai nếu gọi random/time hoặc đọc một biến global mutable:

~~~java
// Phản ví dụ về phụ thuộc trạng thái ngoài:
// int extra = externalCounter.incrementAndGet();
// return subtotal + item + extra;
~~~

Kết quả phụ thuộc số lần gọi reducer và lịch chạy, không phải chỉ dữ liệu đầu vào. Predicate/mapper trước reduce cũng nên non-interfering và stateless để toàn pipeline ổn định.

## 12. Một ví dụ khó: nối chuỗi bằng reduce

Đoạn sau **đúng về giá trị**:

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", (left, right) -> left + right);

System.out.println(text); // ABC
~~~

Vì String immutable và nối chuỗi có phần tử đơn vị chuỗi rỗng, không có identity mutable chung.

Nhưng có thể kém hiệu quả khi nối rất nhiều phần tử, do String mới phải được tạo và sao chép nội dung ở nhiều bước. **Collectors.joining** hoặc **collect(StringBuilder::new, StringBuilder::append, StringBuilder::append)** thường mô tả đúng ý định và giảm việc tạo String trung gian.

Một API không trở nên “đúng hơn” chỉ vì dùng functional style. Hãy chọn **công cụ khớp cấu trúc kết quả**.

## 13. Không dùng reduce để sửa nguồn hoặc ghi transaction

Ngoài việc mutate identity, còn một sai lầm khác: để accumulator sửa **chính các phần tử của nguồn**:

~~~java
// Phản ví dụ:
// stream.reduce(identity, (acc, item) -> {
//     item.markProcessed(); // Side effect trên nguồn.
//     ...
// }, combiner);
~~~

Các behavioral parameter của Stream cần non-interfering; nếu nguồn chứa object mutable thì Stream không tự deep-copy chúng. Việc gọi **markProcessed** có thể làm dữ liệu nguồn thay đổi, gây race hoặc khiến những pipeline khác thấy trạng thái khác.

Tương tự, không đặt **gửi email**, **ghi thanh toán**, **ghi audit bắt buộc** trong accumulator, vì chiến lược chia/gộp và các tối ưu không được thiết kế để bảo đảm một giao dịch nghiệp vụ trên từng phần tử.

Nếu cần xử lý mọi bản ghi và cập nhật hệ thống, hãy thiết kế một **quy trình điều phối với hợp đồng lỗi, idempotency, transaction và kiểm toán rõ ràng**; các hàm reduction chỉ nên tính toán kết quả, không thay thế quy trình ghi dữ liệu.

## 14. Parallel stream và collector không tự bảo đảm mọi thứ

Việc collect hoạt động trên parallel stream **không có nghĩa** mọi collector hoặc mọi callback tùy ý đều an toàn:

- Accumulator/combiner phải tuân thủ luật của Collector.
- Supplier cần tạo container mới phù hợp, không trả cùng shared object.
- Collector đồng thời (CONCURRENT) có đặc tính riêng, và một số collector unordered có thể không bảo đảm thứ tự mà nghiệp vụ mong muốn.
- Nếu lambda ghi vào cấu trúc mutable **ngoài** collector, bạn vẫn có thể gặp race.
- Nếu kết quả là một ArrayList, sau khi collect trả về, **nhiều thread tự ý sửa cùng ArrayList** vẫn không an toàn.
- Nếu thứ tự là yêu cầu nghiệp vụ, cần hiểu encounter order của nguồn, đặc tính collector và cách thực thi.

Chỉ bật **parallelStream()** khi phép rút gọn hợp lệ cho parallel và có lợi ích hiệu năng đã được đo. Với dữ liệu nhỏ, chi phí chia/gộp có thể lớn hơn lợi ích.

### 14.1. Collectors.toConcurrentMap

Một số collector được thiết kế cho concurrency, ví dụ **Collectors.toConcurrentMap** và **groupingByConcurrent**. Nhưng chúng vẫn yêu cầu các mapper, key classifier và merge function phù hợp, và có thể trả kết quả với đặc tính thứ tự khác collector thông thường. Không dùng chữ “Concurrent” như dấu bảo đảm toàn bộ business logic hay các đối tượng được lưu trữ trong map đều thread-safe.

## 15. Overflow, số thực và độ chính xác

### 15.1. int/long

Với Java int/long, phép cộng thường có thể overflow theo semantics số nguyên. Nếu nghiệp vụ không chấp nhận điều này, hãy:

- Sử dụng kiểu lớn hơn khi đủ: long thay int.
- Dùng **BigInteger/BigDecimal** khi miền số vượt khả năng biểu diễn của long hoặc yêu cầu tiền tệ.
- Áp dụng validation và kiểm tra giới hạn trước/sau reduction.
- Cẩn thận với **Math.addExact**: nếu chạy trên những nhóm phần tử khác nhau, một tổ hợp có thể có **tổng trung gian vượt miền long** dù tổng cuối sẽ nằm trong miền. Vì vậy, hành vi ném exception trong các phân hoạch có thể khác nhau. Nếu cần phép tính chính xác không phụ thuộc phân hoạch, dùng kiểu số có miền đủ rộng.

### 15.2. double

Với số thực nhị phân, tổng tính theo các nhóm khác nhau có thể cho sai khác làm tròn:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Do đó khi parallel reduction với double, đừng đòi kết quả luôn khớp từng bit với một phép cộng tuần tự theo thứ tự cố định. Cần kiểm thử theo sai số cho phép, hoặc chọn mô hình số phù hợp nếu nghiệp vụ yêu cầu chính xác tuyệt đối.

## 16. Unit test và kiểm tra tính chất

### 16.1. Test kết quả sequential và parallel

Đối với reducer hợp lệ:

1. Rút gọn nguồn rỗng: identity phải được trả về nếu overload có identity.
2. Một phần tử: kết quả phải đúng với chính phần tử.
3. Nhiều phần tử: kết quả phù hợp kỳ vọng.
4. So sánh sequential/parallel trên nguồn ổn định.
5. Trộn thứ tự phần tử nếu phép toán được kỳ vọng giao hoán; nếu không giao hoán như nối chuỗi, kiểm tra encounter order và collector đúng.
6. Nguồn lớn: kiểm tra độ chính xác, overflow và memory.
7. Không có state mutable bị thay đổi ngoài dự kiến.

Ví dụ với phép cộng:

~~~java
int sequential = IntStream.rangeClosed(1, 1000)
        .reduce(0, Integer::sum);

int parallel = IntStream.rangeClosed(1, 1000)
        .parallel()
        .reduce(0, Integer::sum);

if (sequential != 500_500 || parallel != 500_500) {
    throw new AssertionError("Unexpected sum");
}
~~~

Đây là mảnh ghép cần import IntStream và đặt trong phương thức. Dãy 1..1000 có tổng 500.500 nằm trong miền int, nên cùng kết quả là điều kỳ vọng.

### 16.2. Test luật identity/associativity

Nếu tự định nghĩa **BinaryOperator<T> combine**, hãy kiểm tra:

~~~text
combine(identity, x) == x
combine(x, identity) == x

combine(combine(a, b), c)
    == combine(a, combine(b, c))
~~~

Với kiểu đối tượng, nên so **giá trị/đặc tính nghiệp vụ** chứ không chỉ so tham chiếu. Đối với số floating-point hoặc phép toán có overflow/rounding, xác định rõ khái niệm tương đương phù hợp; đừng viết property test sai tiền đề.

### 16.3. Test nguy cơ aliasing bằng cách đọc code

Không cần tạo một stress test race dễ qua ngẫu nhiên để biết sai. Chỉ cần thấy:

~~~java
U identity = new MutableU();
return stream.parallel().reduce(
        identity,
        (u, t) -> { u.mutate(t); return u; },
        (left, right) -> { left.merge(right); return left; }
);
~~~

là đã thấy **đối tượng identity có thể bị mutate** và combiner giả định sai quyền sở hữu. Phản ví dụ cần được sửa thành **collect** hoặc dùng một U immutable phù hợp. Cố chạy nhiều lần rồi thấy “đa số đúng” không phải bằng chứng an toàn.

### 16.4. Test Collector

Với collect(ArrayList::new, ArrayList::add, ArrayList::addAll):

- Kiểm tra đúng phần tử, đủ phần tử và không trùng ngoài dữ liệu nguồn.
- Với nguồn ordered, kiểm tra thứ tự tương ứng.
- Kiểm tra nguồn vẫn không đổi.
- Đối với object mutable, kiểm tra rõ phần tử có được chia sẻ tham chiếu với nguồn không (collect không deep-copy).
- Nếu muốn collector không gặp null, xác định chính sách của từng thành phần.

## 17. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| **reduce(new ArrayList<>(), (list,x)->{list.add(x);return list;},...)** | Identity mutable, alias, race/ghép sai | **collect(ArrayList::new, ArrayList::add, ArrayList::addAll)** |
| **reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)** | Mutation của identity và combiner, dễ nhân bản dữ liệu | **collect(StringBuilder::new, StringBuilder::append, StringBuilder::append)** |
| Dùng synchronizedList làm identity của reduce | Vẫn sai luật identity và khả năng alias | Đổi sang collect, không chỉ thêm khóa |
| Dùng AtomicInteger làm identity rồi mutate | Atomic không sửa hợp đồng rút gọn | reduce số nguyên bất biến hoặc IntStream.sum |
| Dùng identity=10 cho phép cộng | Có thể bị áp dụng trên nhiều nhánh | identity=0; cộng 10 sau reduction |
| Dùng phép trừ với parallel reduce | Phép trừ không associative | Thiết kế thuật toán tuần tự hoặc phép kết hợp đúng |
| Supplier của collect trả cùng shared list | Nhiều nhánh dùng cùng object | Supplier tạo object mới |
| Dùng mutable global counter trong accumulator | Kết quả phụ thuộc lần gọi/thread | Tính từ tham số, trả kết quả |
| Dùng side effect để ghi audit trong reduce | Không có transaction đúng cho mọi phần tử | Tách bước xử lý nghiệp vụ |
| Dùng Collectors.toList mà đòi chắc chắn ArrayList mutable | Không có cam kết implementation/mutability | toCollection(ArrayList::new) |
| Dùng Double::sum và đòi tính kết hợp số học tuyệt đối | Floating-point rounding khác nhau | Dùng sai số chấp nhận hoặc kiểu số chính xác |
| Dùng Math.addExact mà không xét kết quả từng partition | Có thể khác về ngoại lệ do intermediate overflow | Chọn kiểu có miền đủ rộng, định nghĩa quy tắc |
| Bật parallel vì nghĩ nhanh hơn | Overhead và khó kiểm soát state | Benchmark sau khi bảo đảm đúng |

## 18. Bài tập tự luyện

### Bài 1 — Phát hiện lỗi mutable identity

Xét:

~~~java
List<String> result = Stream.of("A", "B")
        .parallel()
        .reduce(
                new ArrayList<>(),
                (list, item) -> { list.add(item); return list; },
                (left, right) -> { left.addAll(right); return left; }
        );
~~~

**Hỏi:** Vì sao không được dựa vào kết quả? **Đáp án:** identity ArrayList mutable có thể bị dùng chung ở nhiều nhánh; accumulator mutate identity; combiner có thể nhận alias và ghép sai. Hãy dùng collect với supplier tạo ArrayList mới. Mảnh ghép cần import List, Stream, ArrayList.

### Bài 2 — Chọn reduce hay collect

Chọn API phù hợp:

1. Tính tổng số lượng từ IntStream.
2. Tạo ArrayList chứa những ID của mỗi đơn.
3. Nối chuỗi lớn có dấu phẩy.
4. Tìm max khi stream có thể rỗng.
5. Cộng BigDecimal chính xác.

**Đáp án gợi ý:** (1) IntStream.sum hoặc reduce(0,Integer::sum); (2) collect(toCollection(ArrayList::new)) hoặc collect ba đối số; (3) Collectors.joining(","); (4) reduce(max) hoặc max tương ứng trả Optional; (5) reduce(BigDecimal.ZERO, BigDecimal::add) nếu quy tắc cộng phù hợp.

### Bài 3 — Sửa identity không đúng

~~~java
int result = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

**Yêu cầu:** tính 10 + tổng các phần tử mà vẫn đúng khi parallel.

**Đáp án:**

~~~java
int result = 10 + IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);
~~~

Kết quả **16**. Identity phải là 0 cho phép cộng; số 10 là dữ liệu bổ sung ngoài reduction.

### Bài 4 — Sửa StringBuilder

Mã cũ dùng reduce(new StringBuilder(), ...). Hãy thay bằng:

~~~java
String text = words.parallelStream()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();
~~~

**words** giả định là List<String> có encounter order. Hãy giải thích vì sao supplier của collect làm việc đúng với các partial containers và vì sao dùng một StringBuilder mutable identity trong reduce là sai.

### Bài 5 — Vì sao AtomicInteger chưa đủ?

Một đồng nghiệp thay ArrayList bằng AtomicInteger để các phép ghi trở nên nguyên tử, nhưng vẫn dùng identity AtomicInteger và mutate/merge trong reduce.

**Đáp án:** AtomicInteger chỉ giải quyết tính nguyên tử của các thao tác đơn lẻ lên bộ đếm; không đảm bảo identity đúng, combiner không gặp cùng tham chiếu hoặc kết quả không bị cộng lặp. Hãy chọn phép rút gọn số thuần hoặc collect với quyền sở hữu kết quả rõ.

### Bài 6 — Viết test luật kết hợp

Hãy thiết kế test cho một phép combine tùy chọn trên các bộ ba a,b,c, kiểm tra identity và associativity. Bổ sung thử nghiệm sequential/parallel với tập dữ liệu nhiều kích thước. Test nhiều lần có thể tìm lỗi, nhưng không thay cho việc chứng minh hợp đồng, đặc biệt khi có shared mutable state.

## 19. Ghi nhớ

**Không dùng một đối tượng tích lũy có thể thay đổi chung trong reduce().** Reduce cần một **identity hợp lệ**, các phép kết hợp có **tính kết hợp**, và accumulator/combiner **stateless, non-interfering, tương thích** để việc chia/gộp kết quả không làm đổi ngữ nghĩa.

- **reduce**: phù hợp để tạo **giá trị rút gọn** như tổng số, max, BigDecimal sum, hoặc một kết quả immutable theo phép kết hợp đúng.
- **collect**: dành cho **mutable reduction** cần ArrayList, StringBuilder, Map hoặc cấu trúc kết quả được supplier tạo riêng rồi kết hợp.
- **Đừng mutate identity** của reduce, kể cả sequential; kết quả “đúng khi chạy thử” không đủ chứng minh tính đúng.
- **Thêm synchronized/AtomicInteger không sửa được identity và aliasing.**
- **Không dùng supplier trả cùng một container shared** trong collect.
- **Tránh side effect trên nguồn/global state** trong các hàm rút gọn, nhất là parallel.
- **Xem xét overflow, tính kết hợp và sai số floating-point** để không đổi tính đúng đắn lấy tốc độ.

Câu hỏi tự kiểm tra trước khi viết: **“Đây là phép kết hợp các giá trị độc lập, hay tôi cần tạo và sửa một container?”** Nếu là phép kết hợp giá trị, cân nhắc reduce. Nếu là tích lũy mutable, hãy dùng collect với supplier/accumulator/combiner đúng hợp đồng.

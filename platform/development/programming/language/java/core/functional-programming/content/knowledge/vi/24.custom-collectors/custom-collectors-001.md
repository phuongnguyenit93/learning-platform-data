# Collector<T,A,R> và vai trò của ba kiểu dữ liệu trong Java Stream

Trong Java Stream API, `Collector<T,A,R>` là hợp đồng mô tả cách **thu thập nhiều phần tử đầu vào thành một kết quả**. Các collector có sẵn như `Collectors.toList()`, `joining()`, `groupingBy()` giúp xử lý nhiều trường hợp. Nhưng khi muốn quy tắc tổng hợp đặc thù, bạn có thể tạo **collector tùy chỉnh** bằng `Collector.of(...)` hoặc tự triển khai interface `Collector`.

Điểm quan trọng nhất để đọc và thiết kế collector đúng là hiểu rõ **ba tham số kiểu `T`, `A`, `R`**:

- **`T` — input element type:** kiểu của **từng phần tử** đi vào collector.
- **`A` — mutable accumulation type:** kiểu của **trạng thái tích lũy trung gian** mà collector tạo và cập nhật khi duyệt Stream.
- **`R` — result type:** kiểu của **kết quả cuối** được trả về bởi `stream.collect(collector)`.

**`T`, `A`, `R` có thể giống nhau, nhưng không bắt buộc.** Ví dụ, thu thập Stream chuỗi thành một chuỗi nối với dấu phẩy có thể có `T=String`, `A=StringJoiner`, `R=String`. Khi tích lũy vào một ArrayList rồi trả chính ArrayList đó, có thể có `A=R=ArrayList<String>`. Khi tích lũy thống kê qua một class mutable và trả record bất biến, `A` và `R` cũng khác nhau.

Bài học đi từ mô hình dữ liệu và các chức năng thành phần của Collector, đến mã Java 17 chạy được, ý nghĩa `IDENTITY_FINISH`/`CONCURRENT`/`UNORDERED`, xử lý song song và những lỗi dễ mắc.

## 1. Ba kiểu: đọc như ba vai trò khác nhau

Xét bài toán nối những tên người đã chuẩn hóa:

```java
List<String> names = List.of("Lan", "Mai", "Minh");
String display = names.stream()
        .collect(Collectors.joining(" | "));
```

Đây là mảnh mã trong một phương thức, cần import `java.util.List` và `java.util.stream.Collectors`. `joining` là collector có sẵn; kết quả là `"Lan | Mai | Minh"`.

Để hiểu một collector tùy chỉnh làm công việc tương tự, có thể hình dung:

| Vai trò | Ví dụ kiểu | Tại sao |
| --- | --- | --- |
| `T` | `String` | Stream đưa vào từng tên `"Lan"`, `"Mai"`, `"Minh"`. |
| `A` | `StringJoiner` | Một bộ chứa có thể thêm tên và gộp hai bộ chứa. |
| `R` | `String` | Ứng dụng cần một chuỗi để hiển thị, không cần `StringJoiner`. |

Có thể viết kiểu kết quả collector:

```java
Collector<String, StringJoiner, String>
```

Đây là **kiểu tham số hóa minh họa**, chưa phải một khai báo biến hay chương trình độc lập.

Lưu ý: **`A` không phải là kiểu của từng phần tử mới được thêm**, cũng không phải luôn là kiểu trả về cho caller. `A` là trạng thái mà các hàm `supplier`, `accumulator`, `combiner` sử dụng **trong lúc thu thập**. Sau khi thu thập xong, `finisher` có thể đổi `A` sang `R`.

## 2. Bốn thành phần cơ bản của Collector

Về bản chất, một Collector xác định bốn chức năng:

1. **Supplier** tạo bộ chứa/trạng thái tích lũy mới kiểu `A`.
2. **Accumulator** thêm một phần tử `T` vào trạng thái `A`.
3. **Combiner** kết hợp hai trạng thái `A` thành một `A`.
4. **Finisher** chuyển trạng thái cuối `A` thành kết quả kiểu `R`.

Các dạng hàm liên quan:

```java
Supplier<A> supplier()
BiConsumer<A, T> accumulator()
BinaryOperator<A> combiner()
Function<A, R> finisher()
```

Đây là **các chữ ký mang tính khái niệm**, không phải code Java hoàn chỉnh. Trong `Collector<T,A,R>`, những phương thức có dạng generic rộng hơn ở API thực; cách viết trên giúp nhìn rõ loại giá trị đi vào/đi ra.

<escape>**Sơ đồ dòng dữ liệu:**</escape>

```text
       Stream<T> — các phần tử T
                    |
              supplier() -> A
                    |
          accumulator(A, T) -> void
                    |
          nhiều A trong parallel?
                    |
             combiner(A, A) -> A
                    |
               finisher(A) -> R
                    |
          stream.collect(...) -> R
```

Với Stream tuần tự, framework có thể không cần gọi combiner. Với Stream song song, nó có thể tạo nhiều trạng thái `A` riêng, rồi gọi combiner để gộp. Vì vậy **không được viết combiner giả hoặc để ném `UnsupportedOperationException` chỉ vì thử tuần tự chưa thấy nó chạy**.

### Điều quan trọng về chữ ký

- `accumulator` là `BiConsumer<A,T>`: nó nhận state và phần tử, **không trả giá trị**. Nó được thiết kế để cập nhật state.
- `combiner` là `BinaryOperator<A>`: nhận hai state, **trả về một state**. Thường gộp dữ liệu từ state thứ hai vào state thứ nhất rồi trả state thứ nhất.
- `finisher` là `Function<A,R>`: chỉ cần chuyển đổi khi `A` và `R` không dùng cùng một kết quả identity.
- `supplier` phải tạo state thích hợp mỗi lần được yêu cầu; không trả lại một object mutable singleton được chia sẻ ngoài ý muốn.

## 3. Hai overload quan trọng của Collector.of

Java cung cấp những factory overload thường dùng:

```java
static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)

static <T, A, R> Collector<T, A, R> of(
    Supplier<A> supplier,
    BiConsumer<A, T> accumulator,
    BinaryOperator<A> combiner,
    Function<A, R> finisher,
    Collector.Characteristics... characteristics
)
```

Đây là **chữ ký API được trình bày để học**, không phải code chạy độc lập.

**Dạng ba hàm chính** (supplier, accumulator, combiner) phù hợp khi **state tích lũy chính là kết quả**: `A=R`. Overload này có đặc tính `IDENTITY_FINISH`; không cần cung cấp finisher chuyển đổi kiểu.

**Dạng bốn hàm chính** (có finisher) phù hợp khi **state tích lũy cần chuyển đổi trước khi trả**: `A` có thể khác `R`. Ví dụ, sau khi đếm và tính tổng trong một state mutable, finisher tạo `record` bất biến có các giá trị count/sum/average.

Cả hai overload còn có danh sách `Characteristics...` tùy chọn, nhưng **đừng tự gắn `CONCURRENT` hoặc `UNORDERED` nếu logic không đáp ứng hợp đồng**.

## 4. Ví dụ Java 17: T=String, A=StringJoiner, R=String

Tạo tệp **`JoiningCollectorDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.stream.Collector;

public class JoiningCollectorDemo {

    static Collector<String, StringJoiner, String> upperNames() {
        return Collector.of(
                () -> new StringJoiner(" | "),
                (joiner, name) -> joiner.add(
                        name.toUpperCase(Locale.ROOT)),
                StringJoiner::merge,
                StringJoiner::toString
        );
    }

    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai", "Minh");

        String sequential = names.stream().collect(upperNames());
        String parallel = names.parallelStream().collect(upperNames());
        String empty = List.<String>of().stream().collect(upperNames());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=[" + empty + "]");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 JoiningCollectorDemo.java
java JoiningCollectorDemo
```

**Stdout chính xác:**

```text
sequential=LAN | MAI | MINH
parallel=LAN | MAI | MINH
empty=[]
```

Đọc các kiểu theo luồng dữ liệu:

1. `T=String`: từng `name` là String từ danh sách.
2. `A=StringJoiner`: `supplier` tạo `new StringJoiner(" | ")`; `accumulator` gọi `add` sau khi chuyển tên sang chữ hoa.
3. `combiner` dùng `StringJoiner.merge` để gộp các phần đã tích lũy.
4. `R=String`: `finisher` dùng `StringJoiner.toString` trả chuỗi kết quả, thay vì để caller nhận một object `StringJoiner`.

Nguồn `List` có encounter order, collector này không khai báo `UNORDERED`, nên kết quả nối chuỗi duy trì thứ tự gặp khi thu thập tuần tự hoặc song song phù hợp hợp đồng. `StringJoiner` rỗng cho chuỗi `""`, vì vậy khi in cặp ngoặc vuông, kết quả là `empty=[]`.

**Tránh hiểu nhầm:** Stream song song có thể thực hiện bước accumulator ở nhiều thread, nhưng nó không có nghĩa `StringJoiner` trong ví dụ này được chia sẻ để nhiều thread sửa cùng lúc. Đây là collector **không concurrent**; framework có thể sử dụng các state độc lập rồi kết hợp chúng.

## 5. Khi T, A và R đều khác nhau

Một ứng dụng có Stream các bản ghi giao dịch `Sale`, muốn tổng hợp thành báo cáo `Report` bất biến. State tích lũy có thể là một class mutable `Summary` với count và sum.

| Vai trò | Kiểu | Công việc |
| --- | --- | --- |
| `T` | `Sale` | Bản ghi đơn lẻ có `amount`. |
| `A` | `Summary` | Ghi nhớ count và total trong quá trình thu thập. |
| `R` | `Report` | Record kết quả cuối, đã tính mean, không có setter. |

**Chọn `A` không nhất thiết phải giống object cuối cùng.** Bạn có thể giữ một state tối thiểu đủ để xây dựng kết quả, tránh cấp phát một object Report mới mỗi khi thêm một bản ghi.

### Ví dụ Java 17 hoàn chỉnh: custom statistics collector

Lưu thành **`SaleSummaryCollectorDemo.java`**:

```java
import java.util.List;
import java.util.stream.Collector;

public class SaleSummaryCollectorDemo {
    record Sale(String code, int amount) {}
    record Report(long count, long total, double average) {}

    static final class Summary {
        private long count;
        private long total;

        void add(Sale sale) {
            count++;
            total += sale.amount();
        }

        Summary merge(Summary other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Report finish() {
            double average = count == 0 ? 0.0 : (double) total / count;
            return new Report(count, total, average);
        }
    }

    static Collector<Sale, Summary, Report> summarizingSales() {
        return Collector.of(
                Summary::new,
                Summary::add,
                Summary::merge,
                Summary::finish
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 10),
                new Sale("B", 20),
                new Sale("C", 30)
        );

        Report sequential = sales.stream().collect(summarizingSales());
        Report parallel = sales.parallelStream().collect(summarizingSales());
        Report empty = List.<Sale>of().stream().collect(summarizingSales());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SaleSummaryCollectorDemo.java
java SaleSummaryCollectorDemo
```

**Stdout chính xác:**

```text
sequential=Report[count=3, total=60, average=20.0]
parallel=Report[count=3, total=60, average=20.0]
empty=Report[count=0, total=0, average=0.0]
```

Giải thích kỹ:

- `Summary::new` tạo **một accumulator mới**. Giá trị mặc định của hai trường `long` là 0.
- `Summary::add` nhận `Sale` và cập nhật count/total; không trả `Summary` vì dùng chữ ký `BiConsumer<Summary,Sale>`.
- `Summary::merge` nhận state thứ hai, cộng vào state thứ nhất và trả state thứ nhất. Đây là `BinaryOperator<Summary>`.
- `Summary::finish` tạo `Report` mới. `Report` là record Java 17 với accessor và biểu diễn chuỗi ổn định.
- `average=0.0` khi rỗng là **quy ước riêng của ví dụ**, không phải mọi bộ thống kê đều phải chọn giá trị ấy. Nếu nghiệp vụ cần phân biệt không có dữ liệu với trung bình bằng 0, hãy trả `OptionalDouble` hoặc một trạng thái riêng.

Collector này không gắn `CONCURRENT`; các state riêng của từng nhánh song song được gộp bằng `merge`. Phép cộng count và total của bộ dữ liệu nhỏ phù hợp với yêu cầu kết hợp. Với dữ liệu lớn, **`long` vẫn có thể tràn**; code sản xuất cần chính sách số học thích hợp.

## 6. A=R và IDENTITY_FINISH: khi không cần đổi kiểu kết quả

Một collector khác có thể gom các chuỗi vào `ArrayList<String>` và trả **chính danh sách tích lũy**. Khi đó:

```text
T = String
A = ArrayList<String>
R = ArrayList<String>
```

Có thể tạo collector bằng overload không có finisher riêng. Với overload này, `Collector.of` cung cấp đặc tính **`IDENTITY_FINISH`**. Điều đó có nghĩa kết quả kiểu `R` thực chất là state kiểu `A`, không cần biến đổi một cách có ý nghĩa.

Ngược lại, nếu bạn cần **`List<String>` không sửa được** sau quá trình tích lũy, `A` có thể vẫn là `ArrayList<String>` nhưng `R` là `List<String>` được tạo bằng `List.copyOf`. Collector đó **không** có `IDENTITY_FINISH`, vì finisher phải thật sự chạy để tạo kết quả mới.

### Chương trình Java 17: so sánh hai kết quả

Lưu thành **`CollectorFinishDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class CollectorFinishDemo {

    static Collector<String, ArrayList<String>, ArrayList<String>>
    mutableListCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
    }

    static Collector<String, ArrayList<String>, List<String>>
    readOnlyListCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                list -> List.copyOf(list)
        );
    }

    public static void main(String[] args) {
        List<String> source = List.of("A", "B");

        var mutableCollector = mutableListCollector();
        var readOnlyCollector = readOnlyListCollector();

        ArrayList<String> mutable =
                source.parallelStream().collect(mutableCollector);
        List<String> readOnly =
                source.parallelStream().collect(readOnlyCollector);

        mutable.add("C");

        System.out.println("mutable=" + mutable);
        System.out.println("readOnly=" + readOnly);
        System.out.println("mutableIdentityFinish="
                + mutableCollector.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("readOnlyIdentityFinish="
                + readOnlyCollector.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));

        try {
            readOnly.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("readOnlyAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CollectorFinishDemo.java
java CollectorFinishDemo
```

**Stdout chính xác:**

```text
mutable=[A, B, C]
readOnly=[A, B]
mutableIdentityFinish=true
readOnlyIdentityFinish=false
readOnlyAdd=UnsupportedOperationException
```

Ở factory `mutableListCollector`, accumulator giữ một `ArrayList` và kết quả cuối chính là danh sách ấy. Với `readOnlyListCollector`, finisher gọi `List.copyOf`, tạo một List không cho phép các phép sửa như `add`. Các phần tử trong ví dụ là chuỗi không null; `List.copyOf` từ chối phần tử null.

**Hai lưu ý về kiểu:**

1. `List<String>` trong `R` chỉ là **kiểu tĩnh** của kết quả. Khả năng sửa phụ thuộc hợp đồng của object thực tế. `List.copyOf` cung cấp một kết quả không sửa được; `Collectors.toList()` thì **không bảo đảm** luôn trả ArrayList mutable.
2. **Không tự thêm `IDENTITY_FINISH` cho collector có finisher chuyển đổi `A` thành một object khác.** Khi đặc tính này được công bố, Stream framework được phép bỏ qua việc gọi finisher trong những hoàn cảnh hợp lệ. Khai báo sai sẽ phá hợp đồng và có thể dẫn đến lỗi kiểu hoặc kết quả không như mong muốn.

## 7. Quy tắc supplier, accumulator và combiner khi chạy song song

Parallel Stream có thể phân chia phần tử thành nhiều nhóm công việc. Một collector không concurrent thường hoạt động theo mô hình:

```text
                   Stream<T>
                  /         \
       supplier() -> A1    supplier() -> A2
       accumulate T        accumulate T
                  \         /
                 combine(A1,A2) -> A
                          |
                    finisher(A) -> R
```

Đây là **sơ đồ khái niệm**, không cam kết Stream chỉ chia thành đúng hai task hay gọi các phương thức theo đúng số lần vẽ.

### Những yêu cầu quan trọng

**Supplier:** mỗi lần tạo state mới phải cho một container ban đầu hợp lệ (identity của phép kết hợp). Tránh:

```java
// CỐ Ý SAI VỀ THIẾT KẾ:
ArrayList<String> shared = new ArrayList<>();
Collector<String, ?, ?> broken = Collector.of(
        () -> shared,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

Đây là mảnh cảnh báo cần import các lớp liên quan; ý nghĩa sai là **supplier trả về cùng object shared** cho nhiều phần việc. Khi gộp, có nguy cơ tự thêm danh sách vào chính nó, nhân đôi dữ liệu, hoặc tranh chấp cập nhật giữa các thread. Mẫu này không phải collector hợp lệ để dùng cho aggregation tổng quát.

**Accumulator:** cập nhật state đã được supplier tạo; không sửa nguồn Stream, không dựa vào global mutable counter và không ghi side effect cần chính xác theo thứ tự luồng.

**Combiner:** phải đúng cho mọi cách chia hợp lệ. Ví dụ với `ArrayList`:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Mẫu này kết hợp nội dung của hai state thành một state để trả. Với chuỗi cần bảo toàn encounter order, combiner phải nối trái trước phải. Không đổi thứ tự chỉ vì “parallel chạy không có thứ tự” — **execution order** và **encounter order** là hai khái niệm khác nhau.

**Finisher:** chuyển state cuối sang kết quả, không giả định sẽ được gọi riêng cho từng phần tử hay mỗi phần việc. Nếu cần chuyển thành dữ liệu bất biến, làm ở finisher và không công bố `IDENTITY_FINISH`.

## 8. Hai điều kiện về tính kết hợp và identity

Một Collector đúng phải có các thành phần tương thích nhau để phép thu thập không phụ thuộc vào cách Stream framework chia và gộp phần việc.

- **Identity:** khi kết hợp một kết quả tích lũy với một container rỗng mới từ supplier, kết quả phải có ý nghĩa tương đương với kết quả ban đầu.
- **Associativity:** các cách nhóm và kết hợp state phải cho kết quả tương đương về mặt ngữ nghĩa, chứ không phụ thuộc trình tự ghép nhóm.

Ví dụ cho việc nối chuỗi:

```text
merge(merge(A, B), C) == merge(A, merge(B, C))
```

Ký hiệu `==` ở đây biểu thị **tương đương về nội dung kết quả** trong sơ đồ, **không phải yêu cầu hai object Java có cùng reference**.

Với `Summary` đếm/tính tổng, phép gộp:

```java
count += other.count;
total += other.total;
```

là kết hợp được theo ý nghĩa cộng của dữ liệu ví dụ và có state rỗng `count=0,total=0`. Với phép xử lý đòi thứ tự (như nối chuỗi), combiner còn phải tôn trọng order phù hợp nếu collector không `UNORDERED`.

**Đừng dùng phép trung bình trực tiếp bằng cách lấy trung bình hai trung bình con** mà bỏ qua số lượng mẫu: ví dụ một nhóm có 1 phần tử 100, nhóm còn lại có 9 phần tử 0; trung bình tổng đúng là 10, không phải `(100+0)/2 = 50`. Hãy lưu count/sum trong `A`, rồi tính trung bình ở `finisher`.

## 9. Ba Characteristics phổ biến

`Collector.Characteristics` mô tả một số cam kết mà Stream framework có thể dùng để tối ưu hóa.

| Characteristic | Ý nghĩa | Khi nào cần thận trọng |
| --- | --- | --- |
| `IDENTITY_FINISH` | State tích lũy có thể dùng trực tiếp làm kết quả cuối | Không khai báo nếu `finisher` thực sự đổi A sang R |
| `UNORDERED` | Kết quả không phụ thuộc encounter order | Không đánh dấu nếu nối chuỗi hoặc giữ “bản đầu tiên” |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên **cùng** state A | State phải thật sự hỗ trợ cập nhật thread-safe |

Không có một flag chung tên `PARALLEL`: **Collector không concurrent vẫn có thể dùng an toàn với parallel stream** nhờ mỗi phần việc có state riêng và combiner gộp chúng.

### CONCURRENT không đồng nghĩa mọi Collector đều nên có

Nếu `A=ArrayList` và accumulator gọi `add`, không nên khai báo `CONCURRENT` chỉ vì pipeline chạy song song; `ArrayList` không an toàn cho nhiều cập nhật đồng thời. Nếu `A` có các thao tác cập nhật an toàn khi gọi đồng thời và logic không lệ thuộc thứ tự, `CONCURRENT` và `UNORDERED` có thể phù hợp tùy trường hợp.

### Khi đặc tính và nguồn kết hợp

Với collector concurrent, Stream framework có thể dùng một state chung để tích lũy đồng thời trong những hoàn cảnh phù hợp; việc đó phụ thuộc cả đặc tính `UNORDERED` hoặc tình trạng không có encounter order của Stream. Nếu không đáp ứng điều kiện để dùng concurrent reduction trên một container chung, framework có thể chia state như thông thường.

**Các đặc tính là hợp đồng, không phải gợi ý tùy ý về hiệu năng.** Đánh dấu sai có thể gây race condition, sai thứ tự hoặc bỏ qua finisher.

## 10. Ví dụ Java 17: Collector concurrent đếm phần tử

Có thể tạo một collector đơn giản đếm số phần tử bằng state `LongAdder` (trong `java.util.concurrent.atomic`), vốn hỗ trợ cập nhật nguyên tử phân tán giữa các thread. Ví dụ này cố ý không quan tâm encounter order nên có thể công bố `CONCURRENT` và `UNORDERED`.

Tạo file **`ConcurrentCountCollectorDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCountCollectorDemo {
    static Collector<String, LongAdder, Long> counter() {
        return Collector.of(
                LongAdder::new,
                (adder, value) -> adder.increment(),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
    }

    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D", "E");

        long sequential = letters.stream().collect(counter());
        long parallel = letters.parallelStream().collect(counter());
        long empty = List.<String>of().stream().collect(counter());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
        System.out.println("identityFinish=" + counter().characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConcurrentCountCollectorDemo.java
java ConcurrentCountCollectorDemo
```

**Stdout chính xác:**

```text
sequential=5
parallel=5
empty=0
identityFinish=false
```

Ở đây `T=String`, `A=LongAdder`, `R=Long`. Accumulator chỉ cần tăng bộ đếm, không đọc giá trị `String`; đó là lựa chọn có chủ đích vì bài toán chỉ đếm số phần tử.

`CONCURRENT` phù hợp do `LongAdder.increment()` hỗ trợ gọi từ nhiều thread, `UNORDERED` phù hợp vì đếm không phụ thuộc thứ tự, và không có `IDENTITY_FINISH` vì `finisher` trả `Long` từ state `LongAdder`. Trong code ứng dụng, `Collectors.counting()` là lựa chọn đơn giản hơn nếu chỉ cần đếm; mục tiêu ở đây là học chính xác ba kiểu `T,A,R` và đặc tính collector.

`LongAdder.sum()` không phải một snapshot nguyên tử tuyệt đối khi đồng thời có cập nhật chưa kết thúc. Nhưng framework chỉ gọi finisher sau khi việc tích lũy cho kết quả đã hoàn tất, nên trong collector này việc đọc tổng cuối phù hợp. Không tự chia sẻ state ra bên ngoài rồi gọi `sum()` giữa các lần cập nhật nếu cần một snapshot tuyến tính hóa.

## 11. So sánh Collector<T,A,R> với Stream.collect ba đối số

Bên cạnh `collect(Collector)`, object Stream có overload:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R,R> combiner
)
```

Đây là chữ ký API khái niệm. Chú ý khác biệt:

- Dạng **`Stream.collect(supplier, accumulator, combiner)`** không nhận finisher riêng. Container thu thập chính là kết quả: suy nghĩ theo `A=R`.
- Dạng **`Stream.collect(Collector<T,A,R>)`** có thể dùng bất kỳ collector phù hợp, bao gồm collector mà `A` khác `R` nhờ finisher và collector có `Characteristics`.
- Combiner ở `Stream.collect` ba đối số là `BiConsumer<R,R>` có thể cập nhật container đích nhưng **không trả giá trị**. Combiner trong `Collector` là `BinaryOperator<A>`, cần **trả lại state gộp**.

Ví dụ với mảnh mã có import `List`, `ArrayList`:

```java
ArrayList<String> names = List.of("A", "B", "C")
        .stream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

Ở đây ba đối số được truyền **trực tiếp vào `Stream.collect`**, không phải `Collector.of`. Cách này dùng được khi mục tiêu là xây một container trực tiếp. Nếu bạn muốn chuẩn hóa tên, tạo báo cáo thống kê bất biến hoặc tái sử dụng cùng logic tại nhiều pipeline, `Collector<T,A,R>` với finisher rõ ràng thường phù hợp hơn.

Đừng nhầm `reduce` với `collect`:
- `reduce` mô tả phép kết hợp giá trị, identity và toán tử thường phải stateless, associative.
- `collect` được thiết kế cho **mutable reduction**, trong đó accumulator cập nhật state riêng do supplier tạo.

Một `reduce` sử dụng `new ArrayList<>()` làm identity và sửa nó trong accumulator có thể vi phạm hợp đồng, đặc biệt khi chạy song song. Cách đó không trở thành một collector hợp lệ chỉ vì cả hai API đều “gộp phần tử”.

## 12. Những tình huống chọn kiểu T, A và R

| Bài toán | T | A | R | Ghi chú |
| --- | --- | --- | --- | --- |
| Thu thập thành ArrayList và trả chính List | `String` | `ArrayList<String>` | `ArrayList<String>` | Có thể `IDENTITY_FINISH` |
| Nối chuỗi bằng delimiter | `String` | `StringJoiner` | `String` | Finisher gọi `toString` |
| Tổng hợp bán hàng thành báo cáo | `Sale` | `Summary` | `Report` | Finisher tính average |
| Đếm thành số long | `String` | `LongAdder` | `Long` | Có thể concurrent nếu hợp đồng đúng |
| Phân nhóm theo khu vực | `Order` | Container map/nhóm | `Map<String,List<Order>>` | Collector chuẩn thường thích hợp |
| Thu thập rồi trả List không sửa được | `String` | `ArrayList<String>` | `List<String>` | Finisher `List.copyOf` |

Trong generic type `Collector<T,A,R>`, **chọn `T` từ phần tử của Stream trước**. Sau đó hỏi “phải giữ trạng thái gì để xây kết quả?” để chọn `A`, và “caller cuối cùng muốn nhận gì?” để chọn `R`. Không bắt đầu bằng việc ép cả ba kiểu thành nhau cho ngắn.

Ví dụ nếu mục tiêu cuối là trung bình, `T` có thể là một `Purchase` với amount, `A` cần **count và sum**, còn `R` là một `double` hoặc `OptionalDouble` theo hợp đồng của ứng dụng. Không chọn `A=Double` một cách vội vàng rồi cố gộp trung bình con không tính trọng số.

## 13. Cách thiết kế collector tùy chỉnh theo từng bước

1. **Định nghĩa kết quả nghiệp vụ `R`.** Ví dụ một `Report` có count, total, average, hoặc một `String` đã chuẩn hóa.
2. **Xác định phần tử vào `T`.** Đây là phần tử **sau** những phép `filter`/`map` của pipeline, không nhất thiết là object ban đầu của nguồn.
3. **Thiết kế trạng thái `A`.** Chỉ giữ những dữ liệu đủ để tổng hợp; ưu tiên state có cấu trúc đơn giản, các field rõ nghĩa.
4. **Viết supplier tạo identity state hợp lệ.** Mỗi lần gọi cần có thể tạo state sạch, độc lập nếu collector không concurrent.
5. **Viết accumulator cập nhật state và kiểm tra null.** Một phần tử đi qua collector phải góp vào state đúng một lần khi được tích lũy.
6. **Viết combiner và kiểm tra tính kết hợp.** Tự thử gộp các state theo những cách chia khác nhau.
7. **Viết finisher để đổi `A` sang `R` nếu cần.** Ví dụ `List.copyOf`, `StringJoiner.toString`, hoặc tạo record bất biến.
8. **Chọn Characteristics thật thận trọng.** Không dùng `IDENTITY_FINISH` khi có chuyển đổi, không dùng `CONCURRENT` với state không thread-safe, không dùng `UNORDERED` nếu thứ tự cần thiết.
9. **Kiểm tra ba nguồn:** Stream nhiều phần tử, Stream chỉ một phần tử, Stream rỗng.
10. **Chạy cả sequential và parallel** trên cùng dataset để đối chiếu nội dung kết quả nếu ứng dụng có dùng song song.
11. **Đo hiệu năng khi cần**, không mặc định custom collector nhanh hơn collector có sẵn. Nếu yêu cầu có thể viết gọn bằng `toList`, `joining`, `groupingBy`, `summarizingInt`, hãy cân nhắc dùng collector chuẩn.

Đặc biệt, **không khai báo `CONCURRENT` chỉ để kỳ vọng tăng tốc**. Nếu state có khóa hoặc yêu cầu duy trì order, hiệu năng có thể không như mong đợi.

## 14. Những lỗi thường gặp

1. **Nhầm `A` và `R`:** `A` là trạng thái tích lũy nội bộ, `R` là kết quả caller nhận.
2. **Tưởng `T` luôn bằng kiểu phần tử collection gốc:** sau `map`, collector nhận kiểu phần tử của Stream đã biến đổi.
3. **Dùng supplier trả singleton mutable:** nhiều tác vụ có thể chia sẻ state và gộp sai.
4. **Bỏ trống combiner bằng exception:** pipeline tuần tự có thể chạy nhưng parallel có thể lỗi.
5. **Combiner không associative hoặc đổi thứ tự:** kết quả phụ thuộc cách Stream chia task.
6. **Trộn `Collector.of` và `Stream.collect` ba đối số:** combiner của chúng có kiểu và hợp đồng trả về khác nhau.
7. **Quên finisher khi `A` khác `R`:** caller nhận sai kiểu hoặc không compile.
8. **Gắn `IDENTITY_FINISH` sai:** có thể khiến framework bỏ qua finisher bắt buộc.
9. **Gắn `CONCURRENT` cho ArrayList/StringJoiner:** cập nhật đồng thời trên cùng state không an toàn.
10. **Gắn `UNORDERED` cho thuật toán giữ bản đầu tiên hoặc nối chuỗi theo thứ tự:** có thể làm mất cam kết thứ tự đầu ra.
11. **Tính trung bình bằng cách lấy trung bình các trung bình con không trọng số:** sai khi các nhóm có kích thước khác nhau.
12. **Trả state mutable rồi tiếp tục dùng nó làm shared global:** mất kiểm soát vòng đời và an toàn luồng.
13. **Cho rằng finisher luôn chạy:** với `IDENTITY_FINISH`, framework có thể bỏ qua.
14. **Cho rằng collector concurrent chắc chắn nhanh:** còn phụ thuộc workload, contention, dữ liệu và số core.
15. **Không kiểm tra Stream rỗng:** supplier/finisher phải tạo kết quả rỗng có ý nghĩa.
16. **Không quản lý tràn số:** count/sum kiểu long vẫn có giới hạn.
17. **Tự viết custom collector khi collector chuẩn đã phù hợp:** tăng độ phức tạp và rủi ro bug.
18. **Dựa vào thread hoặc iteration order để in stdout trong demo parallel:** không có bảo đảm cho lịch trình thread.

## 15. Tự kiểm tra

**Câu 1.** Trong `Collector<String,StringJoiner,String>`, kiểu nào đại diện cho phần tử, state và kết quả?

**Đáp án:** `T=String`, `A=StringJoiner`, `R=String`. Finisher thường gọi `toString()` để chuyển A sang R.

**Câu 2.** Vì sao `Collector<Sale,Summary,Report>` phải có finisher khi Summary là class mutable còn Report là record bất biến?

Vì `A=Summary` khác `R=Report`. Finisher tạo `Report` từ state đã tổng hợp, ví dụ tính average từ count và total.

**Câu 3.** Combiner của custom Collector trả gì?

**Đáp án:** Một state `A`, theo kiểu `BinaryOperator<A>`. Nó không giống combiner `BiConsumer<R,R>` không trả giá trị của overload `Stream.collect` ba đối số.

**Câu 4.** Khi nào có thể khai báo `IDENTITY_FINISH`?

Khi kết quả tích lũy có thể trực tiếp trở thành kết quả cuối theo hợp đồng; không cần một bước chuyển đổi thật sự từ A sang R. Không khai báo nếu cần `List.copyOf`, tạo record hay `StringJoiner.toString`.

**Câu 5.** Một collector dùng `ArrayList` là A có nên gắn `CONCURRENT`?

**Không**, nếu accumulator gọi trực tiếp `add` vào cùng một ArrayList. ArrayList không an toàn cho nhiều thread cùng cập nhật. Collector không concurrent vẫn có thể thu thập parallel bằng state riêng và combiner.

**Câu 6.** Vì sao một collector tính trung bình thường dùng state chứa `count` và `sum` thay vì chỉ có trường average?

Vì combiner phải gộp dữ liệu đúng trọng số. Chỉ biết average của hai nhóm không đủ để suy ra average chung nếu kích thước nhóm khác nhau.

**Câu 7.** Khi nào nên chọn `Collectors.summarizingInt` hoặc `Collectors.joining` thay vì tự tạo Collector mới?

Khi API có sẵn đã biểu diễn đúng hợp đồng nghiệp vụ và xử lý các ca rỗng, kết hợp, finisher phù hợp; dùng chuẩn giúp giảm code và lỗi tự triển khai.

**Câu 8.** Nếu một List gốc chứa `Sale`, sau `.map(Sale::amount)` thì Collector nhận kiểu `T` nào?

Sau `map`, Stream chứa `Integer` nếu `amount()` trả `int` và dùng object `map`. Vì vậy một collector trên Stream đó có `T=Integer`, không phải `Sale`. Nếu dùng `mapToInt`, ta có `IntStream` với các API collect chuyên biệt, không còn object `Stream<Integer>` theo cùng cách.

**Ghi nhớ:** Trong `Collector<T,A,R>`, **T là dữ liệu đầu vào**, **A là trạng thái tích lũy**, **R là kết quả cuối**. Supplier tạo A, accumulator thêm T vào A, combiner gộp các A, và finisher chuyển A thành R nếu cần. Thiết kế đúng ba vai trò này — cùng identity, associativity và Characteristics — là nền tảng để custom collector vừa dễ hiểu vừa đúng khi chạy tuần tự hoặc song song.

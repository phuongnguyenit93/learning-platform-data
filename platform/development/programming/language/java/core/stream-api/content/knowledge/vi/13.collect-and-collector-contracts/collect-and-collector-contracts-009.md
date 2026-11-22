# Kiểm tra Collector khi ghép nhiều kết quả trung gian

> **Chương:** Cơ chế collect và Collector  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Xác minh một `Collector` giữ đúng kết quả khi Java Stream API chia dữ liệu thành nhiều phần, tạo các trạng thái tích lũy trung gian rồi dùng `combiner` ghép chúng lại. Đây là điều kiện quan trọng trước khi sử dụng `parallelStream()`, `parallel()`, collector tùy chỉnh hoặc các phép nhóm dữ liệu phức tạp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vai trò của `supplier`, `accumulator`, `combiner`, `finisher` và `characteristics` trong `Collector<T, A, R>`.
2. Phân biệt tính đúng của một Collector khi chạy tuần tự và khi các trạng thái trung gian được gộp theo nhiều cách.
3. Kiểm tra hai quy tắc cốt lõi: **identity** và **associativity**, đồng thời xét tính tương đương của kết quả qua `finisher`.
4. Viết Collector dùng accumulator mutable nhưng không chia sẻ nhầm container giữa các phần xử lý.
5. Phát hiện combiner làm mất bản ghi, nhân đôi dữ liệu, gộp ngược thứ tự hoặc làm tròn sai.
6. Thiết kế phép kiểm thử chủ động chia nguồn thành 2–3 phân vùng, đổi cây ghép, kiểm tra nguồn rỗng và dùng oracle độc lập.
7. Hiểu ảnh hưởng của `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` đến cách Stream có thể tích lũy và ghép trạng thái.

Ví dụ sử dụng Java 17 trở lên. `Collector`, `collect` và cơ chế Stream song song đã có từ Java 8; các ví dụ dùng `record` yêu cầu Java 16+. Nội dung liên hệ các kỹ thuật `filter`, `map`, `reduce`, `groupingBy`, tính đúng của tổng số và nguồn dữ liệu `Spliterator` trong module Java Stream API.

## 1. Vì sao chạy tuần tự đúng chưa đủ?

Một pipeline thu thập dữ liệu có thể vận hành như sau:

~~~text
Nguồn có 6 phần tử: [a, b, c, d, e, f]

Thu thập tuần tự:
  supplier() -> A0
  accumulator(A0, a)
  accumulator(A0, b)
  ...
  accumulator(A0, f)
  finisher(A0) -> R

Một khả năng khi chạy song song:
       [a, b]          [c, d]          [e, f]
         |               |               |
   supplier()       supplier()      supplier()
         |               |               |
       A1              A2              A3
         \               /               |
          combiner(A1,A2)                |
                  \                       /
                     combiner(...)
                           |
                       finisher()
                           |
                           R
~~~

Trong trường hợp tuần tự đơn giản, có thể chỉ dùng một container tích lũy và **không cần gọi combiner**. Khi Stream phân chia dữ liệu để xử lý song song, `combiner` có thể được gọi nhiều lần để ghép những container do các nhánh tạo ra.

Vì vậy, một Collector có `accumulator` đúng nhưng `combiner` sai thường vượt qua bài kiểm tra tuần tự rồi thất bại khi chuyển sang `parallelStream()`.

~~~java
import java.util.List;
import java.util.stream.Collector;

List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

// Sai: combiner bỏ hoàn toàn trạng thái bên phải.
Collector<Integer, int[], Integer> broken = Collector.of(
        () -> new int[] {0},
        (acc, value) -> acc[0] += value,
        (left, right) -> left,
        acc -> acc[0]
);

System.out.println(numbers.stream().collect(broken)); // 21 trong ví dụ tuần tự
// Kết quả parallel KHÔNG ĐƯỢC BẢO ĐẢM bằng 21.
System.out.println(numbers.parallelStream().collect(broken));
~~~

Điều sai nằm ngay trong hợp đồng: `(left, right) -> left` làm mất toàn bộ kết quả từ `right`. Không nên dựa vào một con số cụ thể của lần chạy song song; môi trường và cách chia nguồn có thể ảnh hưởng số lần combiner được gọi.

**Mục tiêu kiểm tra Collector là kiểm chứng phép ghép trung gian**, chứ không chỉ kiểm chứng một lần chạy tuần tự và một lần chạy song song tình cờ cho kết quả giống nhau.

## 2. Đọc đúng hợp đồng Collector<T, A, R>

Một Collector có ba kiểu:

~~~java
Collector<T, A, R>
~~~

- `T`: kiểu phần tử đầu vào của Stream.
- `A`: kiểu container/trạng thái tích lũy **trung gian**.
- `R`: kiểu kết quả **cuối cùng** của phép thu thập.

Collector có năm thành phần:

| Thành phần | Chữ ký khái niệm | Nhiệm vụ |
|---|---|---|
| `supplier()` | `() -> A` | Tạo trạng thái `A` mới, ban đầu rỗng |
| `accumulator()` | `(A, T) -> void` | Đưa một phần tử `T` vào trạng thái `A` |
| `combiner()` | `(A, A) -> A` | Ghép hai trạng thái tích lũy thành một |
| `finisher()` | `A -> R` | Chuyển trạng thái cuối sang kết quả công khai |
| `characteristics()` | `Set<Characteristics>` | Cho framework biết đặc điểm của Collector |

Ví dụ một danh sách:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

Collector<String, List<String>, List<String>> toMutableList =
        Collector.of(
                ArrayList::new,                   // supplier
                List::add,                       // accumulator
                (left, right) -> {                // combiner
                    left.addAll(right);
                    return left;
                }
                // Collector.of 3 tham số có identity finisher.
        );

List<String> result = List.of("a", "b", "c")
        .parallelStream()
        .collect(toMutableList);

System.out.println(result); // [a, b, c]
~~~

Container `A` ở đây cũng là kết quả `R`. Trong ví dụ khác, `A` có thể là một đối tượng mutable chứa tổng và số lượng, còn `R` là một `record` bất biến mô tả thống kê.

### 2.1. collect không phải reduce đơn giản trên một biến chung

`Stream.collect(Collector)` là **terminal operation**. Nó tiêu thụ Stream và thu thập kết quả theo hợp đồng Collector. Việc tạo container riêng cho mỗi phần việc rồi ghép với `combiner` là cơ chế quan trọng hỗ trợ song song.

Không nên tự thay bằng:

~~~java
// Không đúng thiết kế thu thập song song:
// List<String> shared = new ArrayList<>();
// input.parallelStream().forEach(shared::add);
~~~

`ArrayList` không an toàn nếu nhiều thread thêm dữ liệu đồng thời. Một Collector chuẩn sẽ điều phối container và phép ghép theo hợp đồng phù hợp.

`Collector` có thể chứa container mutable. Điều quan trọng là **container nào được sửa, ở giai đoạn nào, và có bị chia sẻ giữa các thread hay không**.

## 3. Hai quy tắc nền tảng: identity và associativity

Tài liệu hợp đồng `Collector` mô tả các ràng buộc trên kết quả thu thập. Hãy dùng ký hiệu:

- `empty()` = `supplier.get()`: container mới ở trạng thái rỗng.
- `accumulate(a, t)`: thêm phần tử `t` vào trạng thái `a`.
- `combine(a, b)`: ghép hai trạng thái.
- `finish(a)` = `finisher.apply(a)`: tạo kết quả cuối.

Khi kiểm tra, **tính tương đương** là tương đương theo hợp đồng kết quả. Không đòi hỏi hai object `A` có cùng địa chỉ hay `equals` trả `true`; nhiều container mutable không định nghĩa `equals` theo nội dung.

### 3.1. Identity: ghép với container rỗng không đổi ý nghĩa

Với một trạng thái `a` đã tích lũy, hợp đồng yêu cầu:

~~~text
finish(combine(a, empty()))  ≈  finish(a)

≈ : tương đương về kết quả được Collector công khai
~~~

Ví dụ một accumulator đếm số lượng:

~~~java
final class CountAcc {
    long count;

    void accept(String value) {
        count++;
    }

    CountAcc combine(CountAcc other) {
        count += other.count;  // ghép số đếm
        return this;
    }
}
~~~

Một container mới có `count == 0`. Ghép nó vào trạng thái đã có không đổi số lượng.

Sai thường gặp: `supplier` khởi tạo bộ đếm bằng `1`, hoặc `combiner` cộng thêm “chi phí phân vùng” ngoài nghiệp vụ. Trong Stream song song, container có thể được tạo nhiều lần; giá trị dư bị nhân lên theo số phần.

**Đặc biệt:** muốn tính trung bình, `supplier` phải khởi tạo **sum = 0, count = 0**. Không nên khởi tạo `count = 1` để “tránh chia cho 0”; xử lý nguồn rỗng ở `finisher`.

### 3.2. Associativity: ghép nhiều phân vùng theo cây nào cũng đúng

Nếu ba phần nguồn cho ra trạng thái `a`, `b`, `c`, cần có:

~~~text
finish(combine(combine(a, b), c))
    ≈
finish(combine(a, combine(b, c)))
~~~

Đây là tính **kết hợp** của việc ghép kết quả trung gian. Với Collector hỗ trợ thứ tự, các cách ghép ở trên đều duy trì trật tự phần nguồn `a -> b -> c`; chúng chỉ **đổi cách đặt ngoặc**, không đảo nguồn.

Ví dụ ghép danh sách đúng:

~~~text
a = [A, B]
b = [C]
c = [D, E]

(left + right) theo thứ tự:
  ((a + b) + c) = [A, B, C, D, E]
  (a + (b + c)) = [A, B, C, D, E]
~~~

`addAll` theo thứ tự trái rồi phải phù hợp, với giả định các container độc lập. Ngược lại, nếu combiner luôn nối `right + left`, kết quả bị đảo ở một số cách chia, vi phạm yêu cầu giữ encounter order.

### 3.3. Identity/associativity được đánh giá ở cấp kết quả

Đối với Collector có `finisher`, hai trạng thái khác object vẫn có thể cho kết quả tương đương. Ví dụ các accumulator lưu số lượng có thể khác `identityHashCode` nhưng trả cùng `long`.

Khi thử thủ công trên accumulator mutable, hãy **tạo các container mới cho từng cách ghép**. Không dùng lại container đã bị `combine` sửa để so sánh cây ghép khác, vì thử nghiệm sẽ tự làm thay đổi dữ liệu đầu vào.

## 4. Ví dụ Collector đúng: gộp số lượng và tổng tiền chính xác

Giả sử xử lý các giao dịch, mỗi giao dịch ghi số tiền ở đơn vị **cent**, có thể dương hoặc âm (hoàn tiền). Cần kết quả gồm số giao dịch và tổng cent, không tràn khi cộng `long`.

Đoạn dưới đây là chương trình Java 17 độc lập:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;

public class CollectorMergeDemo {
    record Sale(String id, long cents) {}
    record Summary(long count, BigInteger totalCents) {}

    static final class Acc {
        private long count;
        private BigInteger total = BigInteger.ZERO;

        void add(Sale sale) {
            count = Math.addExact(count, 1L);
            total = total.add(BigInteger.valueOf(sale.cents()));
        }

        Acc merge(Acc other) {
            count = Math.addExact(count, other.count);
            total = total.add(other.total);
            return this;
        }

        Summary finish() {
            return new Summary(count, total);
        }
    }

    static Collector<Sale, Acc, Summary> collector() {
        return Collector.of(
                Acc::new,       // supplier
                Acc::add,       // accumulator
                Acc::merge,     // combiner
                Acc::finish     // finisher
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 1_200),
                new Sale("B", -200),
                new Sale("C", 500),
                new Sale("D", 700)
        );

        Summary sequential = sales.stream().collect(collector());
        Summary parallel = sales.parallelStream().collect(collector());

        System.out.println(sequential); // Summary[count=4, totalCents=2200]
        System.out.println(parallel);   // Summary[count=4, totalCents=2200]
    }
}
~~~

Vì sao Collector này phù hợp để ghép phân vùng?

- `Acc::new` cung cấp container riêng có **count = 0**, **total = 0**.
- `Acc::add` cộng một giao dịch vào đúng trạng thái của container.
- `Acc::merge` ghép **cả count lẫn total** của hai container, không bỏ trường nào.
- `Acc::finish` trả `Summary` bất biến; kết quả có thể so sánh bằng `equals`.
- `BigInteger::add` thực hiện phép cộng số nguyên chính xác; việc nhóm phép cộng không làm thay đổi giá trị.
- `Math.addExact` giúp phát hiện tràn bộ đếm `long`. Nếu yêu cầu đếm hơn giới hạn `long`, cần chọn kiểu đếm khác.

Trong Collector này, `merge` **có thay đổi `this`** và trả về `this`. Đó là một mô hình hợp lệ: combiner được phép gộp vào một container rồi trả container đó. Không nhất thiết phải tạo object `Acc` mới cho mỗi lần ghép.

**Phạm vi an toàn:** `Acc` không thread-safe nếu cùng một instance được cập nhật đồng thời. Tuy nhiên Collector ở đây **không khai báo `CONCURRENT`**; Stream có thể dùng các container riêng rồi gộp chúng khi chạy song song. Không giữ `Acc` ở field static để tái sử dụng giữa các lần `collect`.

## 5. Kiểm tra trực tiếp hai container trung gian

Một cách kiểm tra tốt là tạo những container độc lập, tích lũy mỗi phần nguồn rồi gọi combiner, thay vì chỉ chạy `parallelStream()` và hy vọng framework chọn cấu trúc chia mong muốn.

Các phương thức sau có thể đặt **bên trong lớp `CollectorMergeDemo`** ở mục 4:

~~~java
static Acc fold(List<Sale> partition) {
    Acc acc = new Acc();
    for (Sale sale : partition) {
        acc.add(sale);
    }
    return acc;
}

static void requireEquals(Object expected, Object actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected " + expected + ", got " + actual
        );
    }
}

static void verifyTwoPartitions(List<Sale> sales) {
    int middle = sales.size() / 2;

    Acc left = fold(sales.subList(0, middle));
    Acc right = fold(sales.subList(middle, sales.size()));

    Summary merged = left.merge(right).finish();

    Summary whole = fold(sales).finish();
    requireEquals(whole, merged);
}
~~~

Với danh sách bốn giao dịch `A, B, C, D`:

~~~text
Phần 1: [A, B] -> count=2, total=1000
Phần 2: [C, D] -> count=2, total=1200

Ghép đúng:
  count = 2 + 2 = 4
  total = 1000 + 1200 = 2200
~~~

Khi kiểm thử Collector thật, có thể lấy `supplier()`, `accumulator()` và `combiner()` từ chính Collector để tránh viết lại logic. Mục 7 cung cấp cách làm đó.

### 5.1. Phải kiểm tra cả hai trường của kết quả

Nếu combiner chỉ cộng tổng cent nhưng quên cộng `count`:

~~~java
// SAI, chỉ minh họa:
// Acc merge(Acc other) {
//     total = total.add(other.total);
//     return this;  // count của other bị bỏ quên
// }
~~~

Kiểm tra mỗi tổng tiền có thể vẫn PASS, nhưng số lượng giao dịch lại sai. Tương tự, collector gồm nhiều trường như `sum`, `count`, `min`, `max` hoặc `Map` theo nhóm cần kiểm tra **từng trường** và sự nhất quán giữa chúng.

## 6. Kiểm tra ba phân vùng: hai cách đặt ngoặc

Chia dữ liệu thành ba phần có tính phân biệt:

~~~text
A = [1, 2]
B = [3]
C = [4, 5]

Cây trái:  combine(combine(A, B), C)
Cây phải: combine(A, combine(B, C))
~~~

Với accumulator mutable, mỗi cây ghép cần được tạo từ những container riêng. Thêm các phương thức này vào `CollectorMergeDemo`:

~~~java
static void verifyAssociativity(
        List<Sale> first,
        List<Sale> second,
        List<Sale> third) {

    Summary leftGrouping = fold(first)
            .merge(fold(second))
            .merge(fold(third))
            .finish();

    Summary rightGrouping = fold(first)
            .merge(fold(second).merge(fold(third)))
            .finish();

    requireEquals(leftGrouping, rightGrouping);

    // Kiểm tra cả kết quả chuẩn của tập đầu vào.
    java.util.ArrayList<Sale> all = new java.util.ArrayList<>();
    all.addAll(first);
    all.addAll(second);
    all.addAll(third);
    Summary whole = fold(all).finish();

    requireEquals(whole, leftGrouping);
}
~~~

Có thể gọi:

~~~java
verifyAssociativity(
        sales.subList(0, 2),
        sales.subList(2, 3),
        sales.subList(3, 4)
);
~~~

Bài kiểm tra này gọi thẳng `merge` của ví dụ. Nó bắt được combiner phụ thuộc **cách phân nhóm** và loại bỏ sự may rủi của lịch chạy song song.

**Không đổi thứ tự A, B, C** khi kiểm tra associativity của Collector có thứ tự. Đẳng thức `combine(a, b) == combine(b, a)` là **commutativity**, yêu cầu mạnh hơn và không áp dụng cho mọi Collector hợp lệ. Collector nối danh sách đúng là associative nhưng thường **không commutative**.

## 7. Hàm kiểm tra dùng trực tiếp giao diện Collector

Để áp dụng với nhiều Collector, có thể viết tiện ích thao tác theo đúng các thành phần do Collector cung cấp.

~~~java
import java.util.List;
import java.util.stream.Collector;

final class CollectorChecks {
    private CollectorChecks() {}

    static <T, A, R> A fold(
            Collector<T, A, R> collector,
            List<T> source) {
        A container = collector.supplier().get();

        for (T element : source) {
            collector.accumulator().accept(container, element);
        }
        return container;
    }

    static <T, A, R> R finish(
            Collector<T, A, R> collector,
            A container) {
        return collector.finisher().apply(container);
    }

    static <T, A, R> R mergeInOrder(
            Collector<T, A, R> collector,
            List<T> first,
            List<T> second) {
        A a = fold(collector, first);
        A b = fold(collector, second);

        A merged = collector.combiner().apply(a, b);
        return finish(collector, merged);
    }

    static <T, A, R> void verifyTwoPartitions(
            Collector<T, A, R> collector,
            List<T> source) {
        int middle = source.size() / 2;

        R expected = source.stream().collect(collector);
        R actual = mergeInOrder(
                collector,
                source.subList(0, middle),
                source.subList(middle, source.size())
        );

        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Merge mismatch: " + expected + " vs " + actual
            );
        }
    }
}
~~~

Chẳng hạn, trong `CollectorMergeDemo.main`:

~~~java
CollectorChecks.verifyTwoPartitions(collector(), sales);
~~~

Hàm này:

1. Tạo **hai** container `A` bằng `supplier`.
2. Gọi `accumulator` cho từng phần.
3. Buộc gọi `combiner` ít nhất một lần.
4. Dùng `finisher` để kiểm tra kết quả kiểu `R`.
5. So với phép thu thập trên toàn nguồn.

**Giới hạn của phép so sánh:** Nếu phép thu thập tuần tự cũng sai, bài thử trên có thể cho PASS giả. Cần thêm **oracle độc lập** dựa trên logic nghiệp vụ, như một vòng lặp tính tổng bằng `BigInteger` hoặc bộ dữ liệu nhỏ đã tính tay. Bài thử cũng dùng `Objects.equals`, chỉ phù hợp nếu `R` có ngữ nghĩa `equals` đúng; với mảng, dùng `Arrays.equals` hoặc `Arrays.deepEquals` theo kiểu dữ liệu.

### 7.1. Kiểm tra identity bằng container rỗng

Với Collector tùy chỉnh có kết quả bất biến, có thể viết:

~~~java
Collector<Sale, Acc, Summary> c = collector();

Acc accumulated = CollectorChecks.fold(c, sales);
Summary before = c.finisher().apply(accumulated);

Acc empty = c.supplier().get();
Acc merged = c.combiner().apply(accumulated, empty);
Summary after = c.finisher().apply(merged);

requireEquals(before, after);
~~~

Ở đây `before` là `record Summary` bất biến, nên việc `merged` có thể sửa `accumulated` không thay đổi giá trị đã chụp ở `before`. Nếu `R` chính là container mutable, cần **snapshot nội dung** trước khi merge; so sánh hai tham chiếu tới cùng một object sau khi đã sửa có thể cho PASS giả.

### 7.2. Với collector hợp lệ trên Stream rỗng

~~~java
import java.util.List;

List<Sale> empty = List.of();

Summary s1 = empty.stream().collect(collector());
Summary s2 = empty.parallelStream().collect(collector());

System.out.println(s1); // Summary[count=0, totalCents=0]
System.out.println(s2); // Summary[count=0, totalCents=0]
~~~

Nguồn rỗng kiểm tra `supplier` và `finisher` có diễn đạt đúng trạng thái rỗng không. **Đừng** khởi tạo `count = 1` chỉ để tránh lỗi khi tính trung bình; phải quy định kết quả với nguồn rỗng riêng.

## 8. Những lỗi combiner cần phát hiện

### 8.1. Bỏ mất kết quả bên phải

~~~java
// Sai:
(left, right) -> left
~~~

Nếu có hai phần kết quả, một phần bị mất. Các bài test chia hai phân vùng không rỗng thường phát hiện ngay.

### 8.2. Gộp sai phép toán

~~~java
// Sai khi đang tổng hợp tiền:
// (left, right) -> {
//     left.total = left.total.subtract(right.total);
//     return left;
// }
~~~

Combiner phải có **cùng ý nghĩa** tổng hợp với accumulator. Nếu accumulator đang cộng số tiền, combiner lại trừ, kết quả phụ thuộc cách phân vùng.

### 8.3. Quên ghép một trường

~~~java
// Sai nếu thống kê gồm sum và count:
// left.sum += right.sum;
// return left; // Quên left.count += right.count
~~~

Một phép kiểm chỉ xem `sum` sẽ bỏ sót. Kiểm tra đồng thời `sum`, `count`, `min`, `max` và mọi thuộc tính nghiệp vụ.

### 8.4. Ghép làm nhân đôi dữ liệu

~~~java
// Sai với danh sách:
// left.addAll(right);
// left.addAll(right); // nhân đôi toàn bộ phần bên phải
// return left;
~~~

Danh sách có nhiều phần tử giống nhau làm lỗi khó phát hiện nếu chỉ so sánh tập giá trị. Cần so cả **số lần xuất hiện (multiplicity)** và thứ tự nếu hợp đồng yêu cầu.

### 8.5. Đảo thứ tự của phần kết quả

~~~java
// Sai nếu Collector phải giữ encounter order:
// right.addAll(left);
// return right; // [B, C] + [A] có thể thành [B, C, A]
~~~

Với Collector gom `List` từ nguồn có encounter order, combiner phải nối theo thứ tự được giao. `Collectors.toList()` thích hợp hơn nếu chỉ cần danh sách mà không có yêu cầu container tùy chỉnh.

### 8.6. Mỗi phần bị tính phí khởi tạo

~~~java
// Sai về ngữ nghĩa của supplier:
// () -> new long[] {100L}
~~~

Nếu `100` là “phí cố định cho toàn bộ batch”, việc tạo nhiều container có thể cộng phí nhiều lần. Hãy tách phí cố định khỏi phép gom từng bản ghi rồi áp dụng **một lần sau khi tổng hợp**, nếu đó là đúng quy tắc nghiệp vụ.

### 8.7. Làm tròn trung gian

~~~java
// Nguy cơ sai khi BigDecimal được gộp theo nhóm khác nhau:
// left.sum = left.sum.add(right.sum, mathContext);
~~~

Khi `MathContext` làm tròn ở từng bước, phép cộng có thể mất tính kết hợp theo giá trị thập phân chính xác. Nếu quy tắc cho phép, tích lũy `BigDecimal::add` **không truyền MathContext**, rồi làm tròn một lần ở finisher. Nếu mỗi giao dịch bắt buộc làm tròn trước, hãy chuẩn hóa **mỗi giao dịch** rồi cộng các giá trị đã chuẩn hóa.

## 9. Supplier phải tạo container độc lập

Một lỗi kín đáo là tái sử dụng **cùng một instance** cho tất cả lần gọi supplier:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> shared = new ArrayList<>();

// SAI: mỗi lần supplier được gọi đều trả về cùng một List.
Collector<String, List<String>, List<String>> broken = Collector.of(
        () -> shared,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

Khi ghép hai “container” thực ra là **một đối tượng**, việc `left.addAll(right)` có thể thành `list.addAll(list)`, gây nhân đôi phần tử. Với chạy song song, nhiều thread còn có thể ghi vào cùng `ArrayList` mà không có đồng bộ.

Cách đúng:

~~~java
Collector<String, List<String>, List<String>> correct = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

`ArrayList::new` tạo một list mới cho **mỗi lần supplier được gọi**.

**Quy tắc thực hành:** Không đặt accumulator trong static field, singleton hoặc closure chung rồi trả lại từ `supplier`. Các container của mỗi lượt thu thập phải độc lập để framework quản lý tích lũy và ghép đúng.

## 10. Finisher, kiểu kết quả và IDENTITY_FINISH

Kết quả cuối `R` có thể khác kiểu tích lũy `A`. Trong ví dụ thống kê, `A = Acc` còn `R = Summary`; `finisher` chuyển dữ liệu mutable thành `record` bất biến.

Một ví dụ ngắn thu thập chuỗi rồi tạo list không thể thay đổi cấu trúc:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

Collector<String, List<String>, List<String>> immutableList =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf
        );

List<String> values = List.of("a", "b", "c")
        .parallelStream()
        .collect(immutableList);

System.out.println(values); // [a, b, c]
// values.add("d"); // UnsupportedOperationException
~~~

Ở đây `finisher` quan trọng: nó chuyển một `ArrayList` mutable thành list không thể thay đổi cấu trúc. **Không khai báo `IDENTITY_FINISH`** cho collector này.

### 10.1. Ý nghĩa của IDENTITY_FINISH

`Collector.Characteristics.IDENTITY_FINISH` cho phép framework coi bước kết thúc là phép chuyển kiểu đồng nhất, bỏ qua việc gọi một finisher khác. Đặc tính này phải **đúng theo hợp đồng kiểu và hành vi**, không đơn thuần vì “finisher thường trả nội dung giống accumulator”.

Sai lầm:

~~~java
// ĐỪNG tự thêm Characteristics.IDENTITY_FINISH vào Collector
// có finisher List::copyOf; framework có thể không gọi finisher,
// khiến kết quả không còn bảo đảm là list bất biến.
~~~

Với `Collector.of(supplier, accumulator, combiner)` ba tham số, kết quả chính là container và Collector có `IDENTITY_FINISH`. Với overload có finisher thực sự chuyển đổi dữ liệu, để đặc tính này vắng mặt trừ khi việc chuyển kiểu đồng nhất là hợp đồng đúng.

### 10.2. Không so sánh reference identity thay cho nội dung

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> first = new ArrayList<>(List.of("a", "b"));
List<String> second = new ArrayList<>(List.of("a", "b"));

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Hai Collector hợp lệ có thể trả hai instance khác nhau nhưng cùng nội dung. Dùng tiêu chí tương đương theo kết quả nghiệp vụ, không so địa chỉ bộ nhớ.

## 11. Collector có thứ tự và Collector UNORDERED

`Characteristics.UNORDERED` nói rằng phép thu thập **không cam kết bảo toàn encounter order**. Đây là đặc tính của Collector, không phải câu lệnh “hãy đảo thứ tự”.

Ví dụ:

- Gom phần tử vào `List` thường quan tâm thứ tự nếu nguồn có thứ tự.
- Gom vào `Set` hoặc `Map` để tra cứu theo khóa thường không quan tâm thứ tự duyệt, trừ khi bài toán yêu cầu thứ tự cụ thể.
- Một Collector tính tổng có thể không cần quan tâm thứ tự nếu phép toán tổng hợp đúng và không phụ thuộc thứ tự.

Bảng kiểm chứng:

| Kết quả | Kiểm tra tương đương phù hợp |
|---|---|
| `List<T>` có thứ tự | `List.equals`, so đúng vị trí và số lần xuất hiện |
| `Set<T>` không yêu cầu thứ tự | `Set.equals` |
| `Map<K,V>` không yêu cầu thứ tự | `Map.equals` và kiểm tra từng giá trị |
| Tổng nguyên chính xác | So giá trị số chính xác |
| Tổng `double` | Theo chính sách sai số/tính tái lập đã xác định |
| Kết quả của Collector khai báo `UNORDERED` | So nội dung theo hợp đồng; không tự đòi thứ tự |

**Thứ tự khi gộp:** Với Collector có thứ tự, kiểm tra các cách đặt ngoặc nhưng giữ nguyên thứ tự các phân vùng. Với Collector thực sự không quan tâm thứ tự, có thể thêm phép thử đổi thứ tự phân vùng để tìm sự phụ thuộc không mong muốn.

Không thêm `UNORDERED` vào một Collector nối `StringBuilder` hoặc `List` mà yêu cầu nghiệp vụ là giữ nguyên thứ tự đầu vào.

## 12. CONCURRENT không có nghĩa chỉ cần dùng parallelStream()

Một Collector khai báo `Characteristics.CONCURRENT` cho biết các container có thể được phép **tích lũy đồng thời** từ nhiều thread. Để đặc tính này đúng, cấu trúc dữ liệu và accumulator phải hỗ trợ việc đó.

Một Collector **không khai báo `CONCURRENT`** vẫn có thể dùng hợp lệ với `parallelStream()`: framework có thể tích lũy vào nhiều container riêng rồi gọi `combiner`.

Phân biệt:

| Tình huống | Framework có thể làm gì? | Điều cần bảo đảm |
|---|---|---|
| `parallelStream()` + Collector thông thường | Tạo nhiều container, tích lũy riêng, ghép lại | Combiner đúng identity/associativity |
| Collector có `CONCURRENT` trên Stream không có encounter order cần giữ | Có thể gọi accumulator đồng thời trên **cùng container** | Container và accumulator thread-safe |
| Collector có `CONCURRENT` nhưng không `UNORDERED` trên Stream có thứ tự | Framework có thể chọn cách không tích lũy chung đồng thời để giữ thứ tự | Đừng giả định mọi lần chạy đều dùng cùng container |
| Collector có `UNORDERED` nhưng không `CONCURRENT` | Không đòi thứ tự nhưng vẫn có thể dùng nhiều container riêng | Không vì `UNORDERED` mà chia sẻ container bừa bãi |

Theo cơ chế thu thập Stream, phép tích lũy đồng thời trong cùng một container đặc biệt có thể được sử dụng nếu Collector có `CONCURRENT` và nguồn **không có thứ tự** hoặc Collector đồng thời có `UNORDERED`. Dù đủ điều kiện, framework không có nghĩa vụ phải chọn một lịch chạy cố định.

### 12.1. Ví dụ chọn API concurrent có sẵn

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

record Payment(String category, long cents) {}

List<Payment> payments = List.of(
        new Payment("BOOK", 100),
        new Payment("PEN", 50),
        new Payment("BOOK", 300)
);

ConcurrentMap<String, BigInteger> sums = payments.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Payment::category,
                p -> BigInteger.valueOf(p.cents()),
                BigInteger::add
        ));

System.out.println(sums.get("BOOK")); // 400
System.out.println(sums.get("PEN"));  // 50
~~~

`Collectors.toConcurrentMap` quản lý container và cơ chế gộp đồng thời theo hợp đồng API. Phép `BigInteger::add` phù hợp vì cho kết quả nguyên chính xác. Đây thường là lựa chọn rõ ràng hơn việc tự viết `HashMap` chia sẻ rồi khai báo Collector là `CONCURRENT`.

**Không làm:**

~~~java
// Sai nếu accumulator có thể chạy đồng thời trên cùng container:
// Collector.Characteristics.CONCURRENT
// kết hợp HashMap::new và HashMap.merge(...) không có đồng bộ.
~~~

`HashMap` không thread-safe. Tự gắn `CONCURRENT` không tự làm container an toàn.

## 13. Thử với groupingBy, mapping và reducing

Một downstream Collector cũng phải ghép đúng khi kết quả nhóm được chia ra thành nhiều phần.

Ví dụ gom tổng cent theo danh mục:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Payment(String category, long cents) {}

List<Payment> payments = List.of(
        new Payment("BOOK", 100),
        new Payment("PEN", 50),
        new Payment("BOOK", -30),
        new Payment("PEN", 70)
);

Map<String, BigInteger> totals = payments.parallelStream()
        .collect(Collectors.groupingBy(
                Payment::category,
                Collectors.mapping(
                        p -> BigInteger.valueOf(p.cents()),
                        Collectors.reducing(BigInteger.ZERO, BigInteger::add)
                )
        ));

System.out.println(totals.get("BOOK")); // 70
System.out.println(totals.get("PEN"));  // 120
~~~

Có hai cấp ghép:

1. **Cấp nhóm:** kết quả cho cùng khóa từ nhiều phân vùng phải được gộp vào đúng khóa.
2. **Cấp giá trị:** các tổng `BigInteger` của cùng khóa được cộng bằng phép toán kết hợp chính xác.

Kiểm thử nên xác nhận:

- Tập khóa đúng, không mất hoặc xuất hiện khóa ngoài mong đợi.
- Giá trị **từng khóa** đúng.
- Tổng các nhóm bằng tổng toàn nguồn nếu mỗi bản ghi thuộc đúng một nhóm.
- Không dựa vào thứ tự duyệt của `HashMap`/`ConcurrentHashMap` nếu không có hợp đồng thứ tự.

### 13.1. Khi dùng toMap phải có merge function cho khóa trùng

~~~java
Map<String, BigInteger> totals = payments.parallelStream()
        .collect(Collectors.toMap(
                Payment::category,
                p -> BigInteger.valueOf(p.cents()),
                BigInteger::add
        ));
~~~

Nếu hai phần dữ liệu có cùng khóa, `toMap` cần cách ghép giá trị; `BigInteger::add` là merge function hợp lệ. Bỏ merge function trong bài toán có khóa trùng sẽ gây `IllegalStateException`, không phụ thuộc việc chạy tuần tự hay song song.

Đừng dùng merge function không kết hợp như phép trừ hoặc phép chia nếu muốn kết quả không phụ thuộc cách phân vùng.

## 14. Kiểm tra dữ liệu số: tránh một combiner “đúng kiểu” nhưng sai số học

Một Collector có thể biên dịch và trả đúng kiểu `R` nhưng vẫn sai yêu cầu tính toán.

### 14.1. Trung bình phải gộp tổng và số đếm

Hai phân vùng:

~~~text
A = [10, 20]  -> average = 15, count = 2
B = [100]     -> average = 100, count = 1

Sai: (15 + 100) / 2 = 57.5
Đúng: (10 + 20 + 100) / 3 = 43.333...
~~~

Combiner không thể chỉ tính trung bình của hai trung bình, trừ khi thiết kế có thêm trọng số đúng. Thay vào đó, accumulator nên giữ cặp **(sum, count)**, combiner cộng từng trường, finisher mới chia.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

record Stats(BigInteger sum, long count) {
    BigDecimal average(int scale) {
        if (count == 0) {
            throw new IllegalStateException("Không có dữ liệu");
        }
        return new BigDecimal(sum).divide(
                BigDecimal.valueOf(count),
                scale,
                RoundingMode.HALF_UP
        );
    }
}
~~~

Record này là **kết quả cuối** có thể dùng sau khi đã thu thập `sum` và `count` bằng Collector đúng. Quyết định scale và rounding mode phải xuất phát từ yêu cầu nghiệp vụ.

### 14.2. Số nguyên có thể tràn

~~~java
import java.util.List;

List<Integer> amounts = List.of(1_500_000_000, 1_500_000_000);

int wrong = amounts.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

long correctInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(wrong);         // -1294967296
System.out.println(correctInLong); // 3000000000
~~~

Dù combiner của phép cộng `int` có tính kết hợp **modulo** \(2^{32}\), kết quả có thể sai nghiệp vụ nếu muốn tổng số nguyên toán học. Chọn `long` hoặc `BigInteger` theo miền giá trị; đừng coi “sequential == parallel” là chứng cứ duy nhất của độ đúng.

### 14.3. double không kết hợp tuyệt đối

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Nếu combiner dùng phép cộng `double` hoặc làm tròn `BigDecimal` ở từng bước, kết quả có thể thay đổi theo cây gộp. Cần đặt ra sai số cho phép, thuật toán tích lũy, quy tắc làm tròn hoặc chọn phép toán chính xác nếu nghiệp vụ đòi hỏi.

## 15. Bộ ca kiểm thử đủ để bắt lỗi ghép trung gian

Một ma trận cơ bản:

| Ca | Vì sao cần kiểm tra? | Kỳ vọng |
|---|---|---|
| Nguồn rỗng | Supplier/finisher đúng trạng thái khởi đầu | Kết quả rỗng/0 đúng nghiệp vụ |
| Một phần tử | Không tạo giá trị phụ | Kết quả bằng phần tử |
| Hai phân vùng đều không rỗng | Buộc dùng combiner | Không mất/nhân đôi dữ liệu |
| Một phân vùng rỗng | Identity | Ghép với rỗng không đổi kết quả |
| Ba phân vùng | Associativity | Hai cách đặt ngoặc cho kết quả tương đương |
| Phân vùng có kích thước rất lệch | Lộ lỗi chỉ tính trung bình các trung bình | Tổng/đếm đúng |
| Dữ liệu lặp, khóa trùng | Lộ lỗi merge hoặc multiplicity | Giữ đủ số lần xuất hiện |
| Nhiều giá trị dương và âm | Lộ overflow/triệt tiêu | Đúng theo miền số nghiệp vụ |
| Hoán vị nguồn | Kiểm tra trường hợp kết quả không phụ thuộc thứ tự | Chỉ áp dụng nếu hợp đồng cho phép |
| Nguồn lớn và nhiều lần chạy parallel | Phát hiện race hoặc lỗi hiếm | Đúng oracle, không có trạng thái chia sẻ |
| Collector có `CONCURRENT` | Có thể dùng accumulator cùng lúc | Thread-safe và ổn định |
| Kết quả có thứ tự | Lộ combiner đảo phần | Giữ encounter order khi phải giữ |

Đừng dừng ở `assertEquals(sequential, parallel)`. Nếu combiner không được gọi trong một lần chạy hoặc cả hai đường thực thi đều có lỗi số học, phép so sánh có thể PASS giả.

### 15.1. Oracle độc lập

Với dữ liệu `Sale` ở mục 4, hãy xây một vòng lặp tính toán độc lập:

~~~java
static Summary oracle(List<Sale> sales) {
    long count = 0;
    java.math.BigInteger total = java.math.BigInteger.ZERO;

    for (Sale sale : sales) {
        count = Math.addExact(count, 1L);
        total = total.add(java.math.BigInteger.valueOf(sale.cents()));
    }

    return new Summary(count, total);
}
~~~

Thêm phương thức này **trong lớp `CollectorMergeDemo`**. Sau đó kiểm tra:

~~~java
Summary expected = oracle(sales);
Summary seq = sales.stream().collect(collector());
Summary par = sales.parallelStream().collect(collector());

requireEquals(expected, seq);
requireEquals(expected, par);
~~~

Oracle này dùng vòng lặp, không gọi Collector đang được kiểm tra. Nhờ vậy, nếu `accumulator` và `combiner` cùng sai theo một cách, phép so sánh với oracle có cơ hội phát hiện.

### 15.2. Thử nhiều cách chia, không chỉ chia đôi

Ví dụ với danh sách sáu phần tử:

~~~text
[A, B, C, D, E, F]

[A] | [B, C, D, E, F]
[A, B] | [C, D, E, F]
[A, B, C] | [D, E, F]
[A, B, C, D] | [E, F]
[A, B, C, D, E] | [F]

[A] | [B, C] | [D, E, F]
[A, B] | [C] | [D, E, F]
...
~~~

Dùng một helper như `CollectorChecks.mergeInOrder` để thử từng cách chia đôi. Với ba phân vùng, so sánh cả `(A + B) + C` và `A + (B + C)` bằng các container mới.

Nếu Collector được thiết kế **UNORDERED** và có phép ghép thực sự không quan tâm thứ tự, có thể thử đảo các phân vùng. Với Collector có thứ tự, chỉ thay vị trí ranh giới và cây ghép; không đảo encounter order.

### 15.3. Dùng seed cố định khi tạo dữ liệu

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

List<Integer> original = List.of(2, 5, 1, 2, 9, 5, 4);

for (int trial = 0; trial < 20; trial++) {
    List<Integer> candidate = new ArrayList<>(original);
    Collections.shuffle(candidate, new Random(20261118L + trial));

    long expected = 0;
    for (int n : candidate) {
        expected += n;
    }

    long actual = candidate.parallelStream()
            .mapToLong(Integer::longValue)
            .sum();

    if (expected != actual) {
        throw new AssertionError("Mismatch at trial " + trial);
    }
}
~~~

Seed cố định cho phép tái hiện đầu vào khi phát hiện lỗi. Dẫu vậy, kiểm thử shuffle **không thay thế** phép kiểm tra hợp đồng identity và associativity, và việc lặp nhiều lần chưa chứng minh không có data race trong mọi điều kiện.

## 16. Cách viết kiểm thử với JUnit 5

Nếu dự án có JUnit 5, các kiểm tra nên so sánh với oracle, thử nhiều dạng chia và đưa đầu vào biên vào test. Ví dụ dưới đây dựa trên lớp `CollectorMergeDemo` ở mục 4 (đặt mã test trong cùng phạm vi package hoặc điều chỉnh visibility):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigInteger;
import java.util.List;
import org.junit.jupiter.api.Test;

class CollectorMergeDemoTest {
    @Test
    void bothExecutionModesMatchIndependentOracle() {
        List<CollectorMergeDemo.Sale> sales = List.of(
                new CollectorMergeDemo.Sale("A", 1_200),
                new CollectorMergeDemo.Sale("B", -200),
                new CollectorMergeDemo.Sale("C", 500),
                new CollectorMergeDemo.Sale("D", 700)
        );

        CollectorMergeDemo.Summary expected =
                new CollectorMergeDemo.Summary(
                        4, BigInteger.valueOf(2_200)
                );

        assertEquals(expected,
                sales.stream().collect(CollectorMergeDemo.collector()));
        assertEquals(expected,
                sales.parallelStream().collect(CollectorMergeDemo.collector()));
    }

    @Test
    void twoPartitionMergeMatchesWholeInput() {
        List<CollectorMergeDemo.Sale> sales = List.of(
                new CollectorMergeDemo.Sale("A", 1_200),
                new CollectorMergeDemo.Sale("B", -200),
                new CollectorMergeDemo.Sale("C", 500)
        );

        CollectorChecks.verifyTwoPartitions(
                CollectorMergeDemo.collector(), sales);
    }

    @Test
    void emptyInputProducesZeroCountAndTotal() {
        List<CollectorMergeDemo.Sale> empty = List.of();
        var result = empty.parallelStream()
                .collect(CollectorMergeDemo.collector());

        assertEquals(0L, result.count());
        assertEquals(BigInteger.ZERO, result.totalCents());
    }
}
~~~

Bài test đầu xác nhận giá trị mong đợi tính được từ ví dụ; bài test thứ hai ép ghép hai trạng thái; bài test thứ ba xác minh identity trên đầu vào rỗng.

Để biến thành một bộ kiểm tra mạnh hơn, bổ sung bài test cho 3 phân vùng và các cây ghép, lỗi trùng khóa, lần chạy song song lặp lại và các giá trị biên lớn. **Không nên viết test chỉ tái sử dụng cùng một phép tính sai ở cả expected và actual.**

## 17. Quy trình phân tích khi kết quả song song không khớp

Khi `parallelStream().collect(customCollector)` trả kết quả bất thường, dùng trình tự kiểm tra:

1. **Bắt đầu với dữ liệu nhỏ có oracle rõ ràng.** Ghi lại các phần tử, thứ tự và kết quả mong đợi.
2. **Kiểm tra supplier.** Mỗi lần gọi có tạo trạng thái độc lập đúng giá trị rỗng không?
3. **Kiểm tra accumulator.** Một container nhận lần lượt mọi phần tử có cho kết quả đúng không?
4. **Kiểm tra combiner trực tiếp.** Ép tạo hai container không rỗng, ghép chúng rồi đối chiếu oracle.
5. **Kiểm tra identity và ba phân vùng.** Ghép với container rỗng; so hai cây ghép khác nhau.
6. **Kiểm tra finisher.** Có làm tròn, đổi kiểu, bỏ trạng thái, trả tham chiếu mutable bị sửa sau đó hoặc nhầm `IDENTITY_FINISH` không?
7. **Kiểm tra characteristics.** `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH` có phản ánh đúng hành vi không?
8. **Kiểm tra trạng thái chia sẻ và độ chính xác số.** Loại bỏ các biến dùng chung và lỗi overflow/rounding.
9. **Thử nguồn lớn, nhiều phân vùng, nhiều lần chạy.** Khi đã đúng mới xét benchmark hiệu năng.

~~~text
Kết quả parallel sai?
       |
       v
Sequential có đúng oracle?
   |-- Không --> kiểm tra supplier / accumulator / finisher
   |
   v
Ghép thủ công hai container có đúng?
   |-- Không --> kiểm tra combiner, dữ liệu bị mất / nhân đôi
   |
   v
Ghép với empty và đổi cây 3 phân vùng có đúng?
   |-- Không --> identity / associativity / rounding
   |
   v
Có dùng chung một container hoặc khai báo CONCURRENT sai?
   |-- Có --> sửa cấu trúc và hợp đồng đồng thời
   |
   v
So sánh theo hợp đồng kết quả (thứ tự, số học, ngưỡng sai số)
       |
       v
Chạy lại các ca biên và oracle; sau đó mới đo hiệu năng
~~~

## 18. Bài tập tự kiểm tra (kèm đáp án)

### Bài 1. Supplier dùng chung

**Đề:** Vì sao `() -> sharedList` là supplier sai cho Collector thông thường nếu `sharedList` là một `ArrayList` mutable dùng lại?

**Đáp án:** Mỗi container đáng lẽ phải độc lập. Khi hai nhánh dùng cùng list, các lần `accumulator` có thể ghi đồng thời và `combiner` có thể nối một list với chính nó. Dùng `ArrayList::new` để mỗi lời gọi supplier tạo list riêng.

### Bài 2. Combiner làm mất dữ liệu

~~~java
Collector<Integer, int[], Integer> c = Collector.of(
        () -> new int[1],
        (a, n) -> a[0] += n,
        (left, right) -> left,
        a -> a[0]
);
~~~

**Đề:** Với hai phần `[1, 2]` và `[3, 4]`, kết quả ghép thủ công ra sao?

**Đáp án:** `left = 3`, `right = 7`. Combiner chỉ trả `left` nên kết quả là `3`, không phải tổng `10`. Sửa thành `left[0] += right[0]; return left;`.

### Bài 3. Associativity và thứ tự

**Đề:** Collector nối danh sách bằng `left.addAll(right)` có cần thỏa `combine(left, right) == combine(right, left)` không?

**Đáp án:** Không. Nó cần giữ đúng thứ tự khi đặt ngoặc lại: `(A+B)+C` và `A+(B+C)` đều bằng `A+B+C`. Nối `B+A` có thể đổi encounter order. Commutativity không phải điều kiện chung cho mọi Collector.

### Bài 4. Finisher và IDENTITY_FINISH

**Đề:** Collector gom `ArrayList` rồi dùng `List.copyOf` để trả list không thể thay đổi cấu trúc. Có nên khai báo `IDENTITY_FINISH`?

**Đáp án:** Không. Finisher thật sự thay đổi loại/hợp đồng của kết quả, từ list mutable thành list không thể thay đổi cấu trúc. `IDENTITY_FINISH` có thể khiến finisher bị bỏ qua.

### Bài 5. Trung bình của hai nhóm

**Đề:** Nhóm `A = [10, 20]` và `B = [100]`. Nếu combiner lấy trung bình của hai trung bình nhóm, kết quả sai như thế nào?

**Đáp án:** Cho `57.5`, nhưng trung bình toàn bộ là `130/3 ≈ 43.3333`. Gộp **sum** và **count**, sau đó chia ở finisher.

### Bài 6. Collector và tràn số

**Đề:** Collector cộng `int` có combiner đúng `Integer::sum`, nhưng tổng thật vượt `Integer.MAX_VALUE`. Test chỉ so sequential và parallel bằng nhau có đủ không?

**Đáp án:** Không. Cả hai có thể cùng tràn theo số học `int`. Cần oracle `long`/`BigInteger` và kiểm tra miền số trước khi khẳng định kết quả nghiệp vụ đúng.

### Bài 7. Concurrent collector

**Đề:** Có thể dùng `HashMap` và `HashMap::merge` thiếu đồng bộ rồi tự khai báo `CONCURRENT` không?

**Đáp án:** Không. Nếu nhiều thread cùng gọi accumulator trên một container, `HashMap` không bảo đảm an toàn. Dùng collector concurrent chuẩn như `toConcurrentMap` hoặc xây cấu trúc thread-safe thực sự với hợp đồng thích hợp.

### Bài 8. Kiểm tra trường hợp rỗng

**Đề:** Tại sao nguồn rỗng cần một bài test riêng?

**Đáp án:** Nguồn rỗng kiểm tra supplier khởi tạo chính xác và finisher xử lý trạng thái chưa tích lũy. Nó bắt được lỗi như `count = 1`, `min` mặc định không hợp lệ hoặc phép chia cho 0 khi tính trung bình.

### Bài 9. Nguồn có thứ tự

**Đề:** Dữ liệu `[A, B, C, D]` cần kết quả List theo thứ tự. Một combiner trả `right.addAll(left)` có nguy cơ gì?

**Đáp án:** Khi chia phần, nó có thể đặt nhóm sau trước nhóm trước. Kết quả có thể là `[C, D, A, B]`, vi phạm yêu cầu encounter order. Dùng `left.addAll(right)` theo thứ tự combiner nhận các phần.

### Bài 10. Chọn phép kiểm chứng phù hợp

**Đề:** Collector gom tổng cent theo từng khóa `BOOK` và `PEN`. Cần so kết quả ra sao?

**Đáp án:** So cùng tập khóa, tổng của **từng khóa**, tổng cộng các nhóm và tổng số bản ghi nếu có thống kê số lượng. Không dựa vào thứ tự in ra của `Map`. Với dữ liệu tiền lớn, dùng kiểu số có miền đủ rộng hoặc `BigInteger`.

---

**Ghi nhớ:** Một `Collector` chỉ đáng tin cậy khi **supplier tạo trạng thái rỗng độc lập, accumulator đưa dữ liệu vào đúng container, combiner giữ identity và associativity, finisher trả kết quả đúng hợp đồng, và characteristics phản ánh đúng hành vi**. Hãy chủ động ghép **hai và ba** trạng thái trung gian, so với oracle độc lập và thử cả nguồn rỗng, thứ tự, tràn số, dữ liệu trùng lặp. Kết quả tuần tự đúng hoặc một lần chạy song song thành công chưa đủ chứng minh Collector sẽ luôn đúng khi Stream phân chia công việc theo cách khác.


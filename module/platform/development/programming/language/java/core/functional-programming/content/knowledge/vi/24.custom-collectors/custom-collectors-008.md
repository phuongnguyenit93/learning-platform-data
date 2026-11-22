# Luật phần tử đơn vị, tính kết hợp và tính tương đương kết quả của custom Collector

Trong Java Stream, một **custom collector** cho phép chuyển nhiều phần tử nguồn thành một kết quả tổng hợp: thống kê, gom danh sách, xây dựng đối tượng báo cáo hoặc kết hợp các bản ghi. Nhưng viết đúng `supplier`, `accumulator`, `combiner` và `finisher` chưa đủ: các hàm đó phải thỏa những **luật tương thích** để cùng một phép `collect` cho kết quả đúng khi chạy tuần tự hoặc song song.

Ba trọng tâm của bài là **phần tử đơn vị** (*identity*), **tính kết hợp** (*associativity*) và **tính tương đương kết quả** (*equivalence*). Nếu vi phạm, một collector có thể vượt qua bài kiểm thử tuần tự nhưng sai khi Java chia stream thành nhiều nhánh rồi gộp các kết quả trung gian.

## 1. Hợp đồng `Collector<T, A, R>`

`java.util.stream.Collector<T,A,R>` có ba kiểu:

- `T`: kiểu phần tử từ stream nguồn.
- `A`: kiểu **container tích lũy trung gian** (*accumulation type*).
- `R`: kiểu **kết quả cuối** sau khi hoàn tất.

Một collector thường có bốn thành phần:

| Thành phần | Chức năng | Dạng điển hình |
| --- | --- | --- |
| `supplier` | Tạo container `A` mới, ban đầu rỗng/trung hòa | `Supplier<A>` |
| `accumulator` | Đưa một phần tử `T` vào container `A` | `BiConsumer<A,T>` |
| `combiner` | Gộp hai container `A` thành một container `A` | `BinaryOperator<A>` |
| `finisher` | Chuyển `A` thành `R` nếu cần | `Function<A,R>` |

```text
Nguồn:                  t1   t2   t3   t4
                         |    |    |    |
Nhánh 1: supplier() -> A1 --accumulate(t1,t2)
Nhánh 2: supplier() -> A2 --accumulate(t3,t4)
                                |
                      combiner(A1, A2) -> A
                                |
                         finisher(A) -> R
```

Sơ đồ là **một cách phân chia có thể xảy ra**. Java được quyền chia thành các nhóm khác nhau khi thực thi parallel stream, không cam kết đúng hai nhánh, không cam kết thứ tự thời gian thực thi callback. Tuy nhiên kết quả quan sát được phải đáp ứng hợp đồng collector.

API `Collector.of(...)` dùng để tạo collector từ các hàm thành phần. Với `Collector.of(supplier, accumulator, combiner, finisher, characteristics...)`, không nên tự gắn cờ `CONCURRENT`, `UNORDERED` hay `IDENTITY_FINISH` nếu chưa chứng minh các thuộc tính đó thực sự đúng.

## 2. Luật phần tử đơn vị: gộp với container rỗng không được làm đổi kết quả

Theo hợp đồng collector, container `a` được hình thành bằng một chuỗi lời gọi accumulator và container rỗng `e = supplier.get()` mới tạo phải thỏa:

```text
combiner(a, e)  ≡  a
```

Dấu `≡` ở đây là **tương đương về kết quả quan sát được**, không nhất thiết hai object phải cùng reference. Đặc biệt, `combiner` có thể sửa chính `a` rồi trả `a`.

Ví dụ accumulator lưu tổng và số lượng:

```java
static final class Acc {
    long sum;
    int count;

    void add(int n) {
        sum += n;
        count++;
    }

    Acc merge(Acc other) {
        sum += other.sum;
        count += other.count;
        return this;
    }
}
```

Đây là đoạn khai báo class minh họa, cần đặt trong một class Java bên ngoài. Một `new Acc()` có `sum = 0` và `count = 0`, nên gộp nó vào một accumulator khác **không thay đổi** tổng và số lượng.

Giả sử `a` đã xử lý hai giá trị `3` và `5`:

```text
a = (sum=8, count=2)
e = (sum=0, count=0)

combine(a,e) = (sum=8, count=2) = a
```

**Phần tử đơn vị ở đây không nhất thiết là một số duy nhất.** Với custom collector, nó thường là **trạng thái trống của container `A`** được tạo bởi supplier.

### Sai lầm 1: supplier đưa vào phí cố định hoặc số lượng mặc định

```java
// SAI: mỗi container mới đã tự tính là có một bản ghi.
Acc wrong = new Acc();
wrong.count = 1;
```

Nếu supplier trả về kiểu `Acc` có `count = 1`, một kết quả từ `n` phần tử dễ bị đếm thừa. Trong parallel stream, mỗi nhánh có thể tạo container riêng, nên phần đếm thừa có thể được nhân lên theo số container.

Khi nghiệp vụ cần cộng khoản cố định **đúng một lần**, hãy cộng khoản đó **sau khi hoàn tất collect**, không lén đưa vào từng container do supplier sinh ra.

### Sai lầm 2: combiner tự cộng thêm dữ liệu

```java
// SAI: thêm 1 bản ghi tưởng tượng mỗi lần gộp.
Acc mergeWrong(Acc other) {
    this.sum += other.sum;
    this.count += other.count + 1;
    return this;
}
```

Dù `other` là container rỗng, `count` vẫn tăng 1. Điều này vi phạm ngay luật identity. Với stream tuần tự, `combiner` có thể không được gọi và lỗi bị che; khi chạy song song, combiner có thể chạy nhiều lần nên sai lệch xuất hiện.

Các snippet sai được đánh dấu rõ để **không dùng trong ứng dụng**.

## 3. Luật tính kết hợp: đổi cách chia và gộp không làm đổi ý nghĩa

Với ba kết quả trung gian `a`, `b`, `c`, tính kết hợp có nghĩa:

```text
combine(combine(a, b), c)  ≡  combine(a, combine(b, c))
```

Đây là luật về **kết quả**, không đòi hỏi lần gọi hay object reference giống nhau. Vì accumulator/combiner của collector thường **mutate container**, trong kiểm thử phải tạo **những container độc lập** cho hai vế; không tái sử dụng các object đã bị gộp.

Với cặp `(sum, count)`, việc ghép tương ứng cộng từng trường:

```text
a = (sum=3, count=1)
b = (sum=5, count=1)
c = (sum=7, count=1)

(a ⊕ b) ⊕ c = (sum=15, count=3)
a ⊕ (b ⊕ c) = (sum=15, count=3)
```

Như vậy hai cách nhóm đều có cùng kết quả.

**Ví dụ phép gộp sai** là lấy trung bình hai nhóm một cách không trọng số:

```text
Nhóm X có các giá trị [1]        -> average = 1
Nhóm Y có các giá trị [9,9,9]    -> average = 9

Trung bình của hai average = (1 + 9) / 2 = 5   (SAI)
Trung bình của bốn phần tử = (1 + 9 + 9 + 9) / 4 = 7  (ĐÚNG)
```

Muốn tính trung bình, collector nên giữ **`sum` và `count`** trong `A`, khi gộp thì cộng hai tổng và hai số đếm. Chỉ ở `finisher` mới tính `sum / count`. Nếu `count == 0`, cần chính sách xác định (ví dụ trả `OptionalDouble.empty()` hoặc trường kết quả tường minh) thay vì chia cho 0 ngoài ý muốn.

### Luật không chỉ dành cho số học

Với collector tích lũy `List<T>`, combiner có thể dùng `left.addAll(right); return left;`. Nối danh sách theo chiều trái–phải có tính kết hợp về **thứ tự phần tử**:

```text
([A] ++ [B]) ++ [C] = [A,B,C]
[A] ++ ([B] ++ [C]) = [A,B,C]
```

Nhưng đổi chiều thành `right.addAll(left)` hoặc đảo danh sách ở mỗi lần merge có thể làm hỏng encounter order của một collector phải giữ thứ tự. Việc Java chạy song song không có nghĩa được phép tự ý đảo thứ tự kết quả.

## 4. Luật tương đương: các cách thu thập hợp lệ phải trả cùng kết quả quan sát được

Với cùng các phần tử đầu vào, một collector đúng phải làm cho:

1. Tích lũy tuần tự vào một container rồi gọi finisher.
2. Chia nguồn thành các phần, tích lũy mỗi phần vào **container mới**, gộp các phần theo những cách được phép, rồi gọi finisher.

cho ra kết quả **tương đương** theo đặc tính collector đã khai báo.

```text
supplier -> accumulate(t1,t2,t3,t4) -> finish = R1

supplier -> accumulate(t1,t2) --+
                                 combine -> finish = R2
supplier -> accumulate(t3,t4) --+

Yêu cầu: R1 ≡ R2
```

Không đồng nhất “tương đương” với việc **cùng một đối tượng**. Với một immutable `record`, `equals()` theo giá trị thường là phép kiểm tra phù hợp.

Cũng cần phân biệt kết quả **có yêu cầu thứ tự** và **không có yêu cầu thứ tự**:

- Với collector giữ encounter order, hai kết quả `List` phải có cùng các phần tử **theo đúng thứ tự**; `[A,B]` và `[B,A]` không tương đương.
- Với collector khai báo `UNORDERED`, những khác biệt chỉ về thứ tự quan sát có thể được coi là tương đương. Chẳng hạn nếu thực sự cần một tập giá trị, thứ tự iteration của `Set` không có ý nghĩa nghiệp vụ.
- Không được tự gắn `UNORDERED` lên collector trả `List` nếu thứ tự phần tử có ý nghĩa; nó có thể khiến kết quả chạy song song khác yêu cầu.
- Khi finisher tạo đối tượng tổng hợp, hãy so sánh những **trường mang ý nghĩa nghiệp vụ** của kết quả.

Luật tương đương không đòi hỏi callback phải chạy trên cùng luồng hoặc theo cùng lịch thời gian. Nó chỉ ràng buộc **kết quả được phép quan sát**.

## 5. Ví dụ Java 17+ hoàn chỉnh: collector có đủ ba luật

Bài toán: danh sách giao dịch `Sale` có số lượng sản phẩm. Ta cần kết quả `Summary(count, totalUnits)`. Container tích lũy là `Acc` có hai trường `count` và `units`. Khi xử lý một Sale thì tăng count và cộng số lượng; khi gộp hai phần thì cộng từng trường; finisher trả một record bất biến.

Lưu thành tệp `CollectorLawsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class CollectorLawsDemo {
    record Sale(String sku, int units) {}
    record Summary(int count, long totalUnits) {}

    static final class Acc {
        int count;
        long totalUnits;

        void add(Sale sale) {
            count++;
            totalUnits += sale.units();
        }

        Acc merge(Acc other) {
            count += other.count;
            totalUnits += other.totalUnits;
            return this;
        }

        Summary finish() {
            return new Summary(count, totalUnits);
        }
    }

    static Collector<Sale, Acc, Summary> summaryCollector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish
        );
    }

    static Collector<String, List<String>, List<String>> listCollector() {
        return Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2),
                new Sale("B", 3),
                new Sale("C", 4),
                new Sale("D", 1)
        );

        Summary sequential = sales.stream()
                .collect(summaryCollector());
        Summary parallel = sales.parallelStream()
                .collect(summaryCollector());

        Acc left = new Acc();
        left.add(sales.get(0));
        left.add(sales.get(1));
        Acc right = new Acc();
        right.add(sales.get(2));
        right.add(sales.get(3));
        Summary split = left.merge(right).finish();

        Acc one = new Acc();
        one.add(sales.get(0));
        Summary identity = one.merge(new Acc()).finish();

        Summary empty = List.<Sale>of().stream()
                .collect(summaryCollector());

        List<String> ordered = List.of("A", "B", "C")
                .parallelStream()
                .collect(listCollector());

        System.out.println("sequential = " + sequential);
        System.out.println("parallel = " + parallel);
        System.out.println("split = " + split);
        System.out.println("identity = " + identity);
        System.out.println("empty = " + empty);
        System.out.println("ordered = " + ordered);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CollectorLawsDemo.java
java CollectorLawsDemo
```

Kết quả stdout:

```text
sequential = Summary[count=4, totalUnits=10]
parallel = Summary[count=4, totalUnits=10]
split = Summary[count=4, totalUnits=10]
identity = Summary[count=1, totalUnits=2]
empty = Summary[count=0, totalUnits=0]
ordered = [A, B, C]
```

**Phân tích:**

- `Acc::new` tạo một container riêng mỗi lần `supplier` được gọi; mặc định `count=0`, `totalUnits=0` là trạng thái rỗng trung hòa.
- `Acc::add` chỉ cập nhật container do framework cấp, không thay đổi `Sale` hoặc một biến toàn cục.
- `Acc::merge` có thể sửa container bên trái rồi trả lại nó; đây là cách dùng được phép. Hai trường được cộng theo phép kết hợp phù hợp.
- `Acc::finish` trả record `Summary` mới, giúp kết quả cuối **không lộ container tích lũy mutable**.
- `identity` chứng minh gộp một kết quả một phần tử với `Acc` mới rỗng không làm đổi kết quả.
- `empty` thể hiện chính sách của collector này: trên stream rỗng, kết quả là `Summary[count=0, totalUnits=0]`. Đó là hợp đồng được lựa chọn có chủ đích.
- `listCollector()` không khai báo `UNORDERED`. Với nguồn `List` ordered và cách ghép `left.addAll(right)`, danh sách `[A,B,C]` được bảo toàn dù collector chạy từ parallel stream.

Lưu ý: trong thử nghiệm thủ công, `left.merge(right)` **thay đổi `left`**; sau khi gộp, không dùng `left` và `right` để kiểm thử một nhánh ghép khác. Hãy tạo bộ container mới cho mỗi kịch bản.

## 6. Vì sao bug của combiner thường chỉ lộ khi parallel?

Một collector tuần tự thường sử dụng supplier, accumulator rồi finisher mà **không cần combiner**. Khi chạy parallel stream, framework có thể tạo nhiều accumulator và cần combiner để ghép kết quả.

Ví dụ combiner sai:

```java
Acc mergeWrong(Acc other) {
    totalUnits += other.totalUnits;
    count += other.count + 1; // Cộng 1 vô cớ mỗi lần ghép.
    return this;
}
```

Nếu danh sách có bốn Sale, accumulator tuần tự tính `count=4`. Nhưng với hai container có `count=2` và `count=2`, combiner sai cho `2 + 2 + 1 = 5`. Nếu Java chia thành nhiều nhánh hơn, số lần cộng thừa có thể tăng thêm.

Cũng vậy, supplier sai:

```java
// SAI: trả cùng một instance mutable cho mọi lần được gọi.
Acc shared = new Acc();
java.util.function.Supplier<Acc> badSupplier = () -> shared;
```

Khi các nhánh dùng chung `shared`, việc đồng thời gọi `add` có thể gây race condition, và `merge` có thể gộp một object với chính nó. Supplier phải trả một container mới phù hợp với mỗi lần gọi (trừ những trường hợp bất biến/không chia sẻ trạng thái được thiết kế đặc biệt đúng hợp đồng).

**Bài kiểm thử đúng** không phải chạy parallel một lần thấy “đúng” rồi kết luận ổn. Cần kiểm thử trực tiếp luật identity, associativity và so sánh nhiều cách chia/ghép.

## 7. `Collector.of` hai dạng thường gặp

Nếu kiểu tích lũy `A` khác kiểu kết quả `R`, dùng dạng có finisher:

```java
Collector.of(supplier, accumulator, combiner, finisher)
```

Trong chương trình, `A = Acc`, `R = Summary`, nên `Acc::finish` là bắt buộc.

Nếu `A` cũng là `R` và muốn trả chính container tích lũy, có thể dùng dạng ba đối số:

```java
Collector.of(supplier, accumulator, combiner)
```

Dạng ba đối số tạo collector với đặc tính `IDENTITY_FINISH`: finisher về bản chất là phép đồng nhất. Ví dụ `listCollector()` trả chính `List<String>` đã tích lũy.

**Không khai báo `IDENTITY_FINISH` cho `summaryCollector()`**, bởi `Acc` và `Summary` là hai kiểu khác nhau và kết quả phải qua `Acc::finish`. Nếu đánh dấu sai, framework có thể bỏ qua finisher và gây lỗi kiểu hoặc trả kết quả sai.

## 8. Ba `Collector.Characteristics` và mối liên hệ với luật tương đương

`Collector.Characteristics` mô tả những thuộc tính có ý nghĩa khi framework thực thi:

| Characteristic | Ý nghĩa | Thận trọng |
| --- | --- | --- |
| `IDENTITY_FINISH` | Có thể coi kết quả tích lũy là kết quả cuối | Chỉ đúng khi `A` và `R` thực sự tương thích để không cần chuyển đổi |
| `UNORDERED` | Collector không yêu cầu giữ encounter order | Không phù hợp nếu nghiệp vụ đòi danh sách theo thứ tự nguồn |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên **cùng một container** | Container, accumulator và các cấu trúc phụ phải thread-safe theo hợp đồng |

`Acc` dùng các trường `int`/`long` mutable và phép tăng thông thường, nên **không thread-safe cho nhiều luồng cùng cập nhật một instance**. Vì vậy `summaryCollector()` không khai báo `CONCURRENT`, dù nó vẫn dùng được trên `parallelStream()`: framework có thể giữ các accumulator riêng cho các nhánh, sau đó gộp qua combiner.

Đây là một điểm dễ nhầm:

> **Một collector dùng được trên parallel stream không nhất thiết là collector có characteristic `CONCURRENT`.**

`CONCURRENT` là lời cam kết mạnh hơn về việc tích lũy đồng thời trên cùng container. Chỉ đánh dấu khi đã thực sự thiết kế và kiểm thử được thao tác đồng thời an toàn.

`UNORDERED` không có nghĩa Java sẽ đảo/xáo trộn phần tử; nó nới lỏng yêu cầu giữ encounter order. Nếu kết quả là một tập giá trị không quan trọng thứ tự, có thể cân nhắc collector unordered; nếu trả về `List` dùng để hiển thị, hãy giữ ngữ nghĩa ordered.

## 9. Phân biệt luật của `Collector` và `reduce()`

Phép `reduce(identity, accumulator)` thường dùng **identity là một giá trị kiểu kết quả** và accumulator là phép kết hợp không làm thay đổi trạng thái bên ngoài. Trong custom collector, supplier tạo **container tích lũy** và accumulator thường sửa container đó.

So sánh:

| `reduce` | Custom `Collector` |
| --- | --- |
| Identity thường là giá trị `0`, `1`, `""`... | Identity là container rỗng do `supplier` tạo |
| Accumulator thường trả về giá trị mới | Accumulator có thể mutate container `A` |
| Combiner (nếu dùng dạng ba đối số) phải phù hợp accumulator | Combiner gộp hai container `A` |
| Kết quả thường là một giá trị giảm từ các phần tử | Finisher có thể chuyển container thành kiểu báo cáo `R` |

**Ví dụ sai:** dùng cùng một `StringBuilder` mutable làm identity cho `Stream.reduce` rồi `append` trong nhiều nhánh. Điều đó vi phạm hợp đồng reduce. Với `Collector`, thiết kế đúng hơn là mỗi nhánh có builder riêng do supplier cấp và combiner gộp các builder.

Tuy nhiên, không có nghĩa mọi kiểu mutable đều nên tự viết collector. Các collector chuẩn như `toList()`, `joining()`, `groupingBy()`, `summarizingInt()` đã được thư viện triển khai theo hợp đồng. Ưu tiên chúng nếu đáp ứng bài toán; dùng custom collector khi cần trạng thái tích lũy hoặc kết quả đặc thù.

## 10. Kiểm tra luật bằng các nhóm nhỏ

Giả sử có tập Sale với `units` là `[2, 3, 4, 1]`. Ta có thể tính:

```text
Tích lũy tuyến tính:
  empty + 2 + 3 + 4 + 1 -> (count=4, units=10)

Chia hai nhóm:
  empty + 2 + 3 -> (count=2, units=5)
  empty + 4 + 1 -> (count=2, units=5)
  combine        -> (count=4, units=10)

Chia ba nhóm:
  empty + 2     -> (count=1, units=2)
  empty + 3,4   -> (count=2, units=7)
  empty + 1     -> (count=1, units=1)
  combine       -> (count=4, units=10)
```

Để tự kiểm thử nghiêm túc hơn, tạo nhiều cách chia và ghép, rồi so sánh kết quả **sau finisher**. Đặc biệt nên bao gồm:

1. **Nguồn rỗng:** `supplier.get()` rồi `finish()` phải cho kết quả được chính sách cho phép.
2. **Một phần tử:** kiểm tra accumulator tạo đúng một đóng góp.
3. **Identity:** gộp accumulator đã có dữ liệu với một container rỗng mới, kết quả tương đương trạng thái ban đầu.
4. **Associativity:** ghép ba nhóm theo hai cách bằng những bộ container độc lập, so sánh kết quả cuối.
5. **Sequential versus parallel:** so sánh kết quả trên một tập dữ liệu đủ lớn và có các phân bố khác nhau.
6. **Thứ tự:** nếu là collector ordered, thêm dữ liệu có thứ tự rõ ràng để phát hiện combiner đảo danh sách.
7. **Thread-safety:** nếu dự định đánh dấu `CONCURRENT`, phải kiểm tra tranh chấp dữ liệu, đặc biệt các phép `count++` và cập nhật map/list.

Kiểm thử vài trường hợp không chứng minh toàn bộ định luật cho mọi dữ liệu, nên còn cần **lập luận từ cấu trúc toán học** của phép kết hợp.

## 11. Những lỗi thường gặp

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Supplier khởi tạo `count = 1` | Container rỗng đã chứa đóng góp giả; identity không trung hòa | Khởi tạo trạng thái `count=0` |
| Combiner cộng thêm phí cố định mỗi lần merge | Số lần merge phụ thuộc cách chia stream | Cộng khoản cố định một lần **sau collect** |
| Combiner chỉ gộp `sum`, quên `count` | Trạng thái từng nhánh không được kết hợp đầy đủ | Gộp tất cả trường trạng thái liên quan |
| Gộp `average` bằng trung bình hai average | Nhóm có kích thước khác nhau bị cho trọng số bằng nhau | Gộp `sum` và `count`, tính average ở finisher |
| Supplier trả một instance mutable dùng chung | Race hoặc combiner tự gộp với chính đối tượng đó | Tạo container mới cho mỗi lần gọi |
| Combiner đảo thứ tự `List` | Vi phạm tính tương đương khi encounter order quan trọng | Nối trái–phải theo đúng thứ tự |
| Đánh dấu `CONCURRENT` cho container không thread-safe | Accumulator có thể bị gọi đồng thời trên cùng container | Chỉ đánh dấu khi có bảo đảm concurrency thực sự |
| Đánh dấu `IDENTITY_FINISH` khi `A != R` | Có thể bỏ qua bước chuyển đổi | Dùng finisher thật và không đánh dấu sai |
| Gắn `UNORDERED` để hy vọng nhanh hơn | Có thể mất yêu cầu thứ tự của kết quả | Chỉ bỏ ràng buộc khi nghiệp vụ không cần order |
| Chỉ kiểm thử tuần tự | Combiner có thể chưa chạy nên lỗi bị ẩn | Kiểm thử split/merge thủ công và parallel |
| Coi hai container phải `==` mới tương đương | Mutable collector có thể tạo nhiều instance khác nhau | So sánh kết quả sau finisher theo hợp đồng |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với collector đếm phần tử, vì sao `supplier` phải tạo `count=0`?

**Đáp án:** Vì 0 là trạng thái không đóng góp bản ghi nào; gộp container rỗng phải giữ nguyên count của container còn lại.

**Câu 2.** Một custom collector có `accumulator` đúng nhưng `combiner` cộng thêm 1 mỗi lần gộp. Tại sao vẫn có thể qua kiểm thử tuần tự?

**Đáp án:** Thực thi tuần tự có thể không cần gọi combiner; lỗi chỉ xuất hiện khi kết hợp các nhóm, đặc biệt trong parallel stream.

**Câu 3.** Tại sao không lấy trung bình của các giá trị trung bình nhóm bằng cách chia đều số nhóm?

**Đáp án:** Vì nhóm có kích thước khác nhau; cần tính tổng có trọng số. Giữ `sum` và `count`, rồi tính average sau khi gộp.

**Câu 4.** Custom collector không khai báo `CONCURRENT` có được dùng trên parallel stream không?

**Đáp án:** Có, nếu các luật collector đúng. Framework có thể dùng accumulator riêng cho các nhánh, rồi gộp bằng combiner.

**Câu 5.** Với collector trả `List` ordered, `[A,B]` và `[B,A]` có tương đương không?

**Đáp án:** Không. Chúng khác encounter order, nên sai nếu collector cần giữ thứ tự nguồn.

**Câu 6.** `IDENTITY_FINISH` có đúng khi `A` là container mutable `Acc` còn `R` là record `Summary` không?

**Đáp án:** Không. Finisher phải chuyển `Acc` thành `Summary`; đánh dấu identity finisher là sai.

## Ghi nhớ

- **Identity:** `combiner(a, supplier.get()) ≡ a` đối với accumulator `a` hợp lệ.
- **Associativity:** các cách chia/ghép accumulator phải tạo kết quả tương đương, bất kể tổ chức nhóm thế nào.
- **Equivalence:** thu thập tuần tự và song song phải cho kết quả quan sát được tương đương theo bảo đảm order của collector.
- Supplier phải tạo container mới đúng trạng thái rỗng; accumulator cập nhật đủ dữ liệu; combiner gộp đủ trạng thái; finisher chuyển sang kiểu kết quả cuối.
- Không gắn `CONCURRENT`, `UNORDERED` hoặc `IDENTITY_FINISH` nếu không đáp ứng hợp đồng.
- Khi nghi ngờ, kiểm thử **empty, identity, nhiều cách split/merge và sequential vs parallel** trước khi đưa custom collector vào mã sản xuất.

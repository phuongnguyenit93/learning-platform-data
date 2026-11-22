# Supplier tạo vùng tích lũy mới trong Collector tùy chỉnh (Java Stream)

Trong `Stream.collect(...)`, một **Collector** gom nhiều phần tử đầu vào thành kết quả tổng hợp: danh sách, tập hợp, bảng thống kê hoặc cấu trúc nghiệp vụ. Khi tự xây dựng `Collector<T,A,R>`, thành phần đầu tiên cần hiểu là **`Supplier<A>` — hàm tạo một vùng tích lũy (*accumulation container*) mới, độc lập, ở trạng thái ban đầu đúng**.

`Supplier` không lấy phần tử từ stream và không biến một `T` thành `R`. Công việc của nó là **cấp một đối tượng `A` có thể được accumulator cập nhật**. Trong chế độ song song, Stream có thể cần nhiều vùng tích lũy và kết hợp chúng; vì thế viết supplier sai có thể gây mất dữ liệu, nhân đôi, race condition hoặc kết quả lệ thuộc cách phân chia công việc.

Bài học tập trung vào việc *supplier tạo vùng tích lũy mới*, sau đó đặt nó trong mối quan hệ với `accumulator`, `combiner`, `finisher`, và các ràng buộc quan trọng khi xử lý song song. Ví dụ dùng **Java 17+**.

## 1. Bốn thành phần của một `Collector<T,A,R>`

Một collector tổng quát có ba tham số kiểu:

- **`T`**: kiểu phần tử đầu vào của stream.
- **`A`**: kiểu **vùng tích lũy trung gian**. Đây là nơi lưu trạng thái khi nhận từng phần tử.
- **`R`**: kiểu kết quả cuối cùng, có thể bằng hoặc khác `A`.

Các thành phần chính:

| Thành phần | Kiểu hàm | Vai trò |
| --- | --- | --- |
| `supplier()` | `Supplier<A>`, `() -> A` | Tạo vùng `A` **mới** ở trạng thái ban đầu, dùng khi cần tích lũy. |
| `accumulator()` | `BiConsumer<A,T>`, `(A,T) -> void` | Cập nhật một vùng `A` khi nhận phần tử `T`. |
| `combiner()` | `BinaryOperator<A>`, `(A,A) -> A` | Gộp kết quả của hai vùng tích lũy, trả một vùng `A` chứa trạng thái kết hợp. |
| `finisher()` | `Function<A,R>`, `A -> R` | Chuyển vùng `A` thành kết quả cuối `R`. |

Ví dụ `Stream<String>` thu thành danh sách:

~~~text
T = String
A = ArrayList<String>        (vùng tích lũy mutable)
R = List<String>             (kết quả công bố)

supplier        () -> new ArrayList<String>()
accumulator     (list, element) -> list.add(element)
combiner        (left, right) -> { left.addAll(right); return left; }
finisher        list -> List.copyOf(list)
~~~

Những dòng trên là **sơ đồ kiểu và hành vi**, không phải lời gọi thực thi độc lập. `List.copyOf` tạo danh sách kết quả không hỗ trợ thao tác sửa và không chấp nhận phần tử null; mô hình này dành cho dữ liệu đầu vào khác null.

`A` là vùng tạm, `R` là hợp đồng đầu ra. **Supplier chỉ tạo `A`, không cần và không nên tự tạo `R`**, trừ trường hợp `A = R` và collector dùng identity finish.

## 2. `Supplier<A>` có nghĩa gì trong code?

`java.util.function.Supplier<T>` là functional interface có một phương thức:

~~~java
T get();
~~~

Không có tham số đầu vào. Một số supplier thường gặp:

~~~java
// Đoạn minh họa trong một phương thức Java.
java.util.function.Supplier<java.util.ArrayList<String>> lists =
        java.util.ArrayList::new;

java.util.function.Supplier<java.util.HashMap<String, Integer>> maps =
        java.util.HashMap::new;
~~~

Dạng method reference `ArrayList::new` là **constructor reference**: mỗi lần gọi `lists.get()` tạo một `ArrayList` mới. Tương đương `() -> new ArrayList<String>()` về ý nghĩa.

Supplier **không nên trả về `null`**. Nếu collector không có vùng chứa hợp lệ, accumulator và combiner không thể làm đúng hợp đồng. Trạng thái ban đầu của `A` cũng phải biểu diễn “chưa thu thập phần tử nào”, không chứa sẵn dữ liệu nghiệp vụ gây nhân đôi khi có nhiều vùng.

### Ví dụ kiểm tra hai lần gọi tạo hai vùng riêng

Tạo file `FreshSupplierDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class FreshSupplierDemo {
    public static void main(String[] args) {
        Supplier<List<String>> supplier = ArrayList::new;

        List<String> first = supplier.get();
        List<String> second = supplier.get();

        first.add("An");
        second.add("Bình");

        System.out.println("same object=" + (first == second));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
~~~

~~~bash
javac --release 17 FreshSupplierDemo.java
java FreshSupplierDemo
~~~

Stdout:

~~~text
same object=false
first=[An]
second=[Bình]
~~~

`first` và `second` có cùng **kiểu**, nhưng là **hai đối tượng khác nhau**. Việc thêm `"An"` vào danh sách đầu không ảnh hưởng danh sách thứ hai. Tính độc lập này là một phần thiết yếu của collector tùy chỉnh: các vùng do supplier tạo ra phải có trạng thái riêng, có thể được tích lũy và gộp mà không vô tình tham chiếu chung bộ đệm mutable.

## 3. Tạo một Collector đầy đủ bằng `Collector.of(...)`

Đây là factory chính khi bạn tự viết collector. Overload có finisher có dạng:

~~~java
// Chữ ký khái quát để học, không phải lớp Java độc lập.
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
~~~

Giả sử muốn thu một `Stream<String>` thành danh sách, nhưng đầu ra là bản sao không chỉnh sửa được:

~~~java
Collector<String, List<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

Đoạn này cần import `Collector`, `ArrayList` và `List`, được dùng trong chương trình hoàn chỉnh tiếp theo.

Tạo file `CustomListCollectorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CustomListCollectorDemo {
    public static void main(String[] args) {
        Collector<String, List<String>, List<String>> collector =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf);

        List<String> names = Stream.of("An", "Bình", "Chi")
                .collect(collector);

        System.out.println(names);
        System.out.println(names.getClass().getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CustomListCollectorDemo.java
java CustomListCollectorDemo
~~~

Kết quả đầu tiên luôn là:

~~~text
[An, Bình, Chi]
~~~

**Lưu ý về dòng `getClass().getSimpleName()`:** tên lớp triển khai cụ thể của danh sách trả về từ `List.copyOf` không phải hợp đồng API, có thể khác tùy JDK. Vì vậy **không dựa vào tên lớp đó trong kiểm thử hoặc nghiệp vụ**. Ví dụ trên chỉ yêu cầu kiểm tra dòng danh sách là kết quả xác định; nếu muốn stdout hoàn toàn độc lập implementation, bỏ câu lệnh `System.out.println(names.getClass().getSimpleName());`.

Để kiểm tra tính không sửa được, có thể chủ động thử `names.add("Dũng")` trong `try/catch(UnsupportedOperationException)`; không cần làm vậy trong logic sản xuất.

Ở collector này:

1. `ArrayList::new` tạo vùng chứa `List<String>` rỗng.
2. `List::add` đưa từng chuỗi vào vùng đó.
3. `combiner` ghép các phần từ vùng bên phải vào bên trái và **trả về** bên trái.
4. `List::copyOf` tạo danh sách kết quả `R` từ vùng `A`.

Không đánh dấu `IDENTITY_FINISH` cho collector có `finisher = List::copyOf`: finisher **không phải phép đồng nhất**, dù `A` và `R` cùng được khai báo là `List<String>`.

## 4. Tại sao supplier phải tạo vùng mới, nhất là khi parallel?

Với stream tuần tự, người học thường hình dung một collector chỉ cần một `ArrayList` hoặc một bộ đếm. Nhưng một phép thu thập **song song** có thể phân chia dữ liệu và tạo nhiều vùng tích lũy:

~~~text
Nguồn: [A, B, C, D]

Supplier.get() ──→ vùng L (rỗng) ── accumulator(A), accumulator(B)
Supplier.get() ──→ vùng R (rỗng) ── accumulator(C), accumulator(D)

combiner(L, R) ──→ vùng gộp [A, B, C, D]
finisher(vùng gộp) ──→ kết quả
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết JDK tạo đúng hai vùng hoặc chia nguồn theo cách minh họa. Số lần supplier được gọi có thể khác theo nguồn, triển khai, chế độ parallel và cách collector được dùng. Một pipeline tuần tự thường cần một vùng, nhưng không nên viết logic phụ thuộc vào số lần gọi như một hợp đồng API.

**Supplier phải bảo đảm mỗi lần tạo một vùng độc lập.** Việc Stream tạo các vùng riêng và gộp chúng bằng combiner cho phép các collector không concurrent xử lý song song mà không cho nhiều worker cùng sửa một `ArrayList` đơn lẻ.

Đừng nghĩ đặt `.parallel()` tự làm mọi accumulator thread-safe. Chính sách đúng phải dựa trên contract của collector và các `Characteristics`.

## 5. Sai lầm nghiêm trọng: trả lại cùng một đối tượng dùng chung

Đây là mẫu **sai**:

~~~java
// Minh họa sai: mỗi lần supplier được gọi đều trả SAME list.
List<String> shared = new ArrayList<>();

Collector<String, List<String>, List<String>> broken =
        Collector.of(
                () -> shared,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

Đoạn này nằm trong phương thức có import và không nên thực thi để dự đoán kết quả. Nó vi phạm hợp đồng “vùng trống, độc lập khi cần”:

- Lần tạo thứ hai vẫn thấy phần tử từ vùng thứ nhất.
- Với parallel stream, hai tác vụ có thể cùng gọi `add` lên một `ArrayList` không thread-safe.
- Trường hợp `left == right`, `left.addAll(right)` tự ghép danh sách vào chính nó, có thể nhân đôi dữ liệu và làm hỏng ý nghĩa giảm/gộp.
- Nếu tái sử dụng collector ở nhiều lần `collect`, trạng thái từ lần trước còn tồn tại, khiến kết quả **rò rỉ dữ liệu giữa các lần thu thập**.

**Sửa đúng** là đưa việc tạo đối tượng vào thân supplier:

~~~java
// Đúng: mỗi lời gọi get tạo một vùng mới.
() -> new ArrayList<String>()
// Tương đương:
ArrayList::new
~~~

Một nhầm lẫn tinh vi khác:

~~~java
// Sai: object đã tạo một lần trước khi supplier được gọi.
ArrayList<String> existing = new ArrayList<>();
Supplier<ArrayList<String>> supplier = () -> existing;
~~~

Việc dùng cú pháp lambda không làm kết quả trở thành “mới”. Hãy hỏi **mỗi lần gọi `get()` có thực sự tạo đối tượng mới không?**, chứ không chỉ thấy có `() ->`.

## 6. Vùng tích lũy phải bắt đầu ở trạng thái trung lập

Chỉ tạo đối tượng khác nhau chưa đủ. Supplier cần cung cấp **trạng thái rỗng/trung lập đúng đối với phép tích lũy và kết hợp**:

- Thu danh sách: danh sách mới, chưa có phần tử.
- Đếm: bộ đếm mới bắt đầu bằng `0`.
- Tổng: giá trị tổng ban đầu bằng `0` (và kiểu đủ sức chứa nếu cần).
- Tích: giá trị tích ban đầu bằng `1`.
- Tìm min/max: cần trạng thái *chưa có dữ liệu* hoặc sentinel đúng, không áp đặt một giá trị có thể làm sai kết quả.
- Thống kê nhiều chỉ số: bộ đếm `0`, tổng `0`, min/max ở trạng thái chưa quan sát hoặc giá trị khởi tạo phù hợp.

Nếu supplier trả vùng có sẵn một bản ghi mặc định, mỗi vùng song song đều có thêm bản ghi đó; khi combiner ghép chúng lại, bản ghi mặc định bị lặp lại nhiều lần. Do đó supplier không nên đọc/ghi dữ liệu phụ thuộc số lượng worker hay thời điểm thực thi.

### Ví dụ vùng chứa thống kê tùy chỉnh

Tạo file `StatsCollectorDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class StatsCollectorDemo {
    record Sale(int amount) {}
    record Result(long count, long sum, double average) {}

    static final class Acc {
        long count;
        long sum;

        void add(Sale sale) {
            count++;
            sum += sale.amount();
        }

        Acc merge(Acc other) {
            count += other.count;
            sum += other.sum;
            return this;
        }

        Result finish() {
            return new Result(
                    count,
                    sum,
                    count == 0 ? 0.0 : (double) sum / count);
        }
    }

    static Collector<Sale, Acc, Result> collector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale(10), new Sale(20), new Sale(30));

        Result normal = sales.stream().collect(collector());
        Result parallel = sales.parallelStream().collect(collector());
        Result empty = List.<Sale>of().stream().collect(collector());

        System.out.println("normal=" + normal);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
~~~

~~~bash
javac --release 17 StatsCollectorDemo.java
java StatsCollectorDemo
~~~

Stdout:

~~~text
normal=Result[count=3, sum=60, average=20.0]
parallel=Result[count=3, sum=60, average=20.0]
empty=Result[count=0, sum=0, average=0.0]
~~~

Phân tích kỹ vai trò của supplier:

1. `Acc::new` tạo **đối tượng `Acc` mới**. Hai trường `long` được Java khởi tạo thành `0` nên trạng thái ban đầu trung lập đối với tổng và đếm.
2. `Acc::add` nhận một `Sale` và cập nhật vùng chứa: tăng count, cộng amount vào sum.
3. `Acc::merge` gộp hai vùng `Acc` bằng cách cộng count và sum, rồi trả vùng bên trái.
4. `Acc::finish` chuyển `A = Acc` thành `R = Result`. Record `Result` biểu diễn snapshot rõ ràng, không đưa vùng mutable ra ngoài.
5. Trên stream rỗng, vẫn tạo một trạng thái tích lũy ban đầu thích hợp và finisher tạo `Result[count=0, sum=0, average=0.0]`. Nếu nghiệp vụ muốn “không có trung bình” thay vì 0.0, đổi **hợp đồng kết quả**, ví dụ `OptionalDouble`, không giả sử 0.0 có nghĩa như một quan sát thật.

Collector này cho cùng kết quả khi xử lý tuần tự hoặc song song vì phép cộng đếm và tổng có tính kết hợp theo ngữ nghĩa số nguyên Java, các vùng độc lập và không có trạng thái mutable ngoài. Tuy nhiên, `long` vẫn có thể tràn nếu dữ liệu vượt miền biểu diễn; muốn kiểm tra overflow, phải thiết kế phương án riêng.

## 7. Đọc hợp đồng `Collector.of` hai overload

Trong Java có hai factory phổ biến:

~~~java
// Có finisher riêng: A có thể khác R.
Collector.of(supplier, accumulator, combiner, finisher, characteristics...)

// Không có finisher riêng: vùng A được dùng làm kết quả R (identity finish).
Collector.of(supplier, accumulator, combiner, characteristics...)
~~~

Đây là **ký hiệu API minh họa**, không phải các lời gọi Java đầy đủ.

Trong overload không có finisher, `A` và `R` là cùng kiểu và collector mang đặc tính `IDENTITY_FINISH`. Ví dụ `Collector.of(ArrayList::new, List::add, combiner)` trả vùng danh sách đã được tích lũy làm kết quả. Không cần sao chép nếu hợp đồng cho phép trả danh sách mutable.

Trong overload có finisher, **không tự gắn `IDENTITY_FINISH`** nếu finisher biến đổi dữ liệu, dù kiểu khai báo đầu/cuối trùng nhau. Gắn sai characteristic có thể khiến framework bỏ qua finisher hoặc dùng phép ép kiểu không hợp lệ.

### Ví dụ không có finisher: trả trực tiếp vùng tích lũy

Tạo file `IdentityFinishDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class IdentityFinishDemo {
    public static void main(String[] args) {
        Collector<String, ArrayList<String>, ArrayList<String>> collector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        ArrayList<String> result =
                Stream.of("A", "B", "C").collect(collector);

        System.out.println(result);
        System.out.println(collector.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH));
    }
}
~~~

~~~bash
javac --release 17 IdentityFinishDemo.java
java IdentityFinishDemo
~~~

Stdout:

~~~text
[A, B, C]
true
~~~

Đây là trường hợp `A = R = ArrayList<String>`. Supplier vẫn phải tạo vùng **mới** cho mỗi lần được gọi; identity finish chỉ nói kết quả cuối chính là vùng đã tích lũy chứ **không** cho phép supplier trả cùng một instance dùng chung giữa các lần.

## 8. Đừng nhầm với overload `Stream.collect(supplier, accumulator, combiner)`

Java Stream còn có một **terminal operation** nhận ba hàm trực tiếp:

~~~java
// Chữ ký khái quát của Stream<T>.
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

Dễ nhầm `Collector.of` và `Stream.collect` vì cả hai có từ “supplier, accumulator, combiner”, nhưng chữ ký **combiner khác nhau**:

- Trong `Collector.of(...)`, combiner là `BinaryOperator<A>`: **trả một vùng `A`** sau khi kết hợp.
- Trong `stream.collect(supplier, accumulator, combiner)`, combiner là `BiConsumer<R,R>`: **trả `void`**, cập nhật vùng đích bằng nội dung của vùng nguồn.

Tạo file `DirectCollectDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class DirectCollectDemo {
    public static void main(String[] args) {
        ArrayList<String> result = Stream.of("An", "Bình", "Chi")
                .collect(
                        ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll);

        System.out.println(result);
    }
}
~~~

~~~bash
javac --release 17 DirectCollectDemo.java
java DirectCollectDemo
~~~

Stdout:

~~~text
[An, Bình, Chi]
~~~

Ở đây `ArrayList::new` vẫn bảo đảm vùng tích lũy mới, `ArrayList::add` thêm phần tử và `ArrayList::addAll` gộp vùng. Method reference `ArrayList::addAll` trỏ đến phương thức Java trả `boolean`, nhưng vẫn có thể dùng làm `BiConsumer` vì kết quả gọi được bỏ qua theo quy tắc tương thích của method reference/statement expression. Nếu cách viết làm nhóm khó hiểu, dùng lambda `(left, right) -> left.addAll(right)` cho combiner `void`.

API trực tiếp hữu ích cho các phép mutable reduction đơn giản không cần finisher riêng. `Collector.of` hữu ích nếu muốn định nghĩa một collector dùng lại nhiều lần, công bố characteristics, và có `finisher` độc lập.

## 9. Supplier trong xử lý tuần tự, song song và grouping

Một nhầm lẫn là cho rằng supplier **luôn được gọi đúng một lần**. Điều đó không phải điều nên dựa vào:

- Trong pipeline **tuần tự thông thường**, framework có thể dùng một container cho toàn bộ dữ liệu.
- Trong pipeline **song song**, framework có thể tạo nhiều container để các phần xử lý tích lũy độc lập và sau đó kết hợp.
- Với `groupingBy(classifier, downstreamCollector)`, downstream supplier có thể tạo vùng tích lũy riêng cho mỗi nhóm cần xử lý.
- Với các đặc tính như `CONCURRENT`, cách thực thi có thể khác; không suy ra số lần supplier hoặc số thread dùng cùng một vùng từ một ví dụ đơn giản.

Ví dụ dữ liệu nhóm:

~~~java
// Đoạn minh họa, giả sử employees: List<Employee>.
Map<String, List<Employee>> byDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.toList()));
~~~

Trong `groupingBy` này, downstream collector cần các vùng chứa danh sách cho từng nhóm; chúng không phải **một danh sách chung** cho tất cả phòng ban. Trường hợp cần custom downstream, supplier của collector tùy chỉnh phải tạo đúng vùng mới mà mỗi nhóm và mỗi phân đoạn có thể sử dụng.

Nếu bạn muốn cung cấp **loại Map** cho `groupingBy` hoặc `toMap`, tham số `mapSupplier` trong các overload tương ứng cũng phải cấp **Map mới**. Nó giống về nguyên tắc nhưng là supplier của **container Map** (không phải lúc nào cũng là cùng loại `A` của một custom collector trực tiếp).

## 10. `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH` liên quan thế nào?

Các `Collector.Characteristics` ảnh hưởng cách Stream được phép sử dụng collector:

| Characteristic | Ý nghĩa quan trọng | Liên quan tới supplier |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher là phép đồng nhất, có thể bỏ qua việc chạy finisher. | Container `A` cũng là kết quả `R`; supplier vẫn cần container mới. |
| `UNORDERED` | Kết quả không phụ thuộc encounter order của phần tử. | Không được khai báo nếu thứ tự tích lũy quan trọng đối với kết quả. |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng vùng tích lũy. | Container và cập nhật phải an toàn với concurrent accumulation; không tự gắn nếu chỉ dùng `ArrayList`/bộ đếm `long` thường. |

**Tạo vùng mới không đồng nghĩa vùng đó thread-safe.** Một `ArrayList` độc lập phù hợp với mô hình tích lũy phân vùng rồi kết hợp của collector không concurrent, nhưng không an toàn khi nhiều thread thực sự cùng gọi `add` trên một instance. Đánh dấu `CONCURRENT` sai cho collector dùng `ArrayList` không đồng bộ sẽ tạo rủi ro dữ liệu.

Ngược lại, `CONCURRENT` **không bắt buộc** để một collector chạy được với `parallelStream()`. Nhiều collector không concurrent vẫn hoạt động song song bằng cách tích lũy ở các vùng riêng rồi dùng combiner.

Cẩn trọng với `UNORDERED`: collector ghép danh sách theo thứ tự gặp đầu vào thường **quan tâm encounter order**, nên không được đánh dấu unordered chỉ để thử tối ưu. `CONCURRENT` cũng không tự quyết định việc xử lý có bỏ qua encounter order: framework còn xét nguồn có ordered hay unordered và những characteristics khác.

## 11. Những ràng buộc hợp đồng cần giữ đúng

Một supplier hợp lệ phải tương thích với accumulator và combiner. Hãy kiểm tra:

**A. Vùng mới:** các lời gọi `supplier.get()` khác nhau tạo các vùng tích lũy có trạng thái **độc lập**, không dùng chung cấu trúc mutable nội bộ. Đối với immutable shared constants trong vùng là có thể chấp nhận, miễn không gây shared mutable state.

**B. Vùng trung lập:** nếu không đưa phần tử nào vào vùng, kết quả sau finisher tương ứng với kết quả của **stream rỗng**. Khi gộp với vùng đã tích lũy, vùng rỗng không làm sai kết quả.

**C. Tương thích với combiner:** kết hợp hai vùng phải tương đương việc đưa tất cả phần tử tương ứng vào một vùng, theo các quy tắc encounter order/collector. Cần có **associativity** phù hợp để cách chia nhóm không làm thay đổi ý nghĩa.

**D. Không can thiệp nguồn và stateless:** hàm tích lũy không thay đổi collection đang được duyệt hoặc dựa vào state mutable bên ngoài. Supplier cũng không nên đọc trạng thái dùng chung đang thay đổi làm mất tính độc lập giữa các vùng.

**E. Không trả về null:** supplier phải trả đối tượng `A` hợp lệ. Nếu kết quả trống cần biểu diễn bằng `Optional.empty()`, cờ `hasValue`, hoặc count 0, hãy ghi nhận bằng **trạng thái bên trong container**, không dùng tham chiếu container null.

**F. Kết thúc rõ ràng:** nếu `A` là cấu trúc mutable còn `R` cần bất biến, dùng finisher tạo snapshot hoặc bản sao phù hợp; không tuyên bố `IDENTITY_FINISH` sai để bỏ qua bước chuyển.

## 12. Ví dụ kiểm tra supplier đúng với nhiều lần `collect`

Một collector được thiết kế đúng có thể sử dụng lại **định nghĩa collector** qua nhiều lần thu thập trên những stream khác nhau mà không rò rỉ dữ liệu. Tạo file `ReusableCollectorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class ReusableCollectorDemo {
    public static void main(String[] args) {
        Collector<String, ArrayList<String>, ArrayList<String>> collector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        List<String> first = Stream.of("A", "B")
                .collect(collector);
        List<String> second = Stream.of("C")
                .collect(collector);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("shared=" + (first == second));
    }
}
~~~

~~~bash
javac --release 17 ReusableCollectorDemo.java
java ReusableCollectorDemo
~~~

Stdout:

~~~text
first=[A, B]
second=[C]
shared=false
~~~

Trong hai lần `collect`, supplier tạo vùng mới; kết quả lần thứ hai không chứa A/B từ lần thứ nhất. **Tái sử dụng một `Collector` hợp lệ khác với tái sử dụng một `Stream`**: stream đã có terminal operation không thể dùng lại, nhưng định nghĩa collector stateless có thể được dùng cho nhiều stream độc lập.

Ví dụ `ReusableCollectorDemo` dùng đầu ra mutable và identity finish; trong API đòi tính bất biến, nên có finisher tạo bản sao độc lập.

## 13. Tránh nhầm tạo container với tạo một phần tử

Các phương thức có chữ ký dễ gây nhầm:

~~~text
Supplier<A>                   : ()  -> A       (tạo vùng tích lũy)
BiConsumer<A,T>               : (A,T) -> void (đưa phần tử vào vùng)
Function<T,R>                 : T   -> R       (biến đổi một phần tử)
BinaryOperator<A>             : (A,A) -> A     (gộp hai vùng)
Function<A,R>                 : A   -> R       (kết thúc vùng)
~~~

Ví dụ `ArrayList::new` có thể là supplier của vùng. Nhưng `User::new` chỉ phù hợp khi **vùng `A` thực sự là User** và trạng thái/hành vi của nó có ý nghĩa tích lũy. Đừng dùng constructor reference chỉ vì thấy có chữ `new`; phải hiểu **cái được tạo là trạng thái tổng hợp**, không phải đối tượng kết quả của từng phần tử.

Nếu mục tiêu là ánh xạ từng `String` sang `User`, dùng `map(User::new)` trong stream và chọn collector sau đó. Trong `Collector.of`, supplier không nhận `String` đang đi qua pipeline; **accumulator** mới nhận từng phần tử.

## 14. So sánh collector tùy chỉnh với collector có sẵn

Java có nhiều collector đã giải quyết đúng vấn đề vùng tích lũy:

| Mục tiêu | Cách thường nên dùng | Lý do |
| --- | --- | --- |
| Thu các phần tử vào danh sách | `Collectors.toList()` hoặc `Stream.toList()` | Không phải tự viết supplier/combiner/finisher. |
| Cần danh sách mutable cụ thể | `Collectors.toCollection(ArrayList::new)` | Supplier được truyền trực tiếp, loại collection rõ ràng. |
| Thu vào set | `Collectors.toSet()` hoặc `toCollection(HashSet::new)` | Xử lý container theo API có sẵn. |
| Tạo `Map<K,V>` | `Collectors.toMap(...)` | Có hỗ trợ merge function và map supplier. |
| Phân nhóm | `Collectors.groupingBy(...)` | Tạo các vùng tích lũy phù hợp từng nhóm. |
| Thống kê số liệu | `Collectors.summarizingInt(...)` | Cung cấp vùng thống kê và cách gộp được kiểm chứng. |
| Có thuật toán tổng hợp hoặc kết quả đặc thù | `Collector.of(...)` | Tự quyết định `A`, supplier, accumulator, combiner và finisher. |

Ví dụ chọn loại collection bằng supplier trong API có sẵn:

~~~java
// Trong phương thức đã import List, ArrayList và Collectors.
ArrayList<String> names = source.stream()
        .collect(java.util.stream.Collectors.toCollection(
                ArrayList::new));
~~~

Ở đây `source` là `Collection<String>` minh họa. `toCollection(ArrayList::new)` đã xử lý việc dùng supplier để tạo container; không cần tự viết collector chỉ để bảo đảm kết quả là `ArrayList`.

Custom collector có giá trị khi cần trạng thái phong phú (chẳng hạn count/sum/min/max kết hợp điều kiện nghiệp vụ, một cấu trúc đồ thị, hoặc snapshot DTO). Nếu chỉ cần tính tổng số nguyên, các API như `mapToInt(...).sum()` hoặc `summingInt(...)` thường rõ hơn.

## 15. Những lỗi thường gặp với `Supplier<A>`

1. **Trả cùng một instance đã tạo sẵn:** `() -> sharedList` khiến vùng không độc lập.
2. **Khởi tạo trạng thái không trung lập:** thêm sẵn phần tử hoặc count khác 0, dẫn đến nhân đôi sau combiner.
3. **Trả `null`:** accumulator không có vùng `A` để thao tác, gây lỗi.
4. **Nghĩ supplier nhận từng `T`:** supplier không nhận đối số, accumulator mới nhận `(A,T)`.
5. **Nghĩ supplier chỉ gọi một lần:** parallel và downstream collector có thể cần nhiều vùng.
6. **Cho rằng `ArrayList::new` tự làm collector concurrent:** vùng mới không tương đương thread-safety của một vùng được truy cập đồng thời.
7. **Đánh dấu `CONCURRENT` cho bộ đếm thường hoặc `ArrayList`:** dễ tạo race condition khi Stream dùng chung container.
8. **Đánh dấu `IDENTITY_FINISH` khi có bước copy/transform:** có thể khiến finisher không được dùng.
9. **Viết combiner sai kiểu:** `Collector.of` cần `BinaryOperator<A>` trả `A`; `Stream.collect` ba đối số cần `BiConsumer<R,R>` cập nhật vùng.
10. **Không gộp trạng thái trong combiner:** chạy tuần tự có vẻ đúng nhưng kết quả parallel bị thiếu dữ liệu.
11. **Sửa container bên ngoài sau khi lấy kết quả immutable theo kỳ vọng:** phải phân biệt có/không có finisher và loại `R`.
12. **Dùng state mutable bên ngoài trong supplier/accumulator:** có thể tạo phụ thuộc giữa các lần chạy và kết quả không tái lập.
13. **Tái sử dụng stream đã tiêu thụ:** collector có thể dùng lại; stream không thể dùng lại.
14. **Dựa vào số lần gọi supplier để tính số lô dữ liệu:** số vùng không phải một chỉ số nghiệp vụ ổn định.
15. **Không kiểm thử nguồn rỗng:** với nguồn rỗng, tính trung lập của supplier và finisher mới biểu lộ rõ nhất.

## 16. Checklist trước khi viết supplier

- `T`, `A`, `R` là những kiểu gì? Chúng có cần khác nhau không?
- Supplier có thật sự **tạo vùng mới mỗi lần gọi** không?
- Vùng mới có ở **trạng thái trung lập** và không chia sẻ mutable buffer với vùng khác không?
- Với stream rỗng, kết quả sau finisher có đúng quy tắc nghiệp vụ không?
- Accumulator có thay đổi vùng `A` chính xác cho mỗi `T` không?
- Combiner có kết hợp đầy đủ hai vùng, có tính kết hợp và trả đúng `A` không?
- Nếu `A` mutable và `R` cần immutable, finisher đã tạo snapshot phù hợp chưa?
- Có vô tình khai báo `CONCURRENT`, `UNORDERED` hoặc `IDENTITY_FINISH` không đúng không?
- Kết quả tuần tự và song song có cùng ý nghĩa? Hai lần collect độc lập có bị rò rỉ state không?
- Có collector có sẵn nào (`toCollection`, `groupingBy`, `summarizingInt`) làm rõ mục tiêu hơn không?

**Ghi nhớ:** `Supplier<A>` của một collector tùy chỉnh **tạo vùng tích lũy mới, độc lập, trung lập**. Nó không xử lý phần tử đầu vào, không quyết định chính sách gộp và không được trả cùng một container dùng chung. Khi kết hợp đúng với accumulator, combiner và finisher, supplier giúp collector hoạt động hợp lệ cả trên stream rỗng, tuần tự lẫn song song.

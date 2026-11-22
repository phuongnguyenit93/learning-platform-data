# Finisher chuyển vùng tích lũy thành kết quả trong Java Collector tùy chỉnh

## 1. Bài toán: không phải lúc nào đối tượng tích lũy cũng là kết quả cuối

Trong Java Stream API, khi gọi `stream.collect(collector)`, dữ liệu đi qua một quy trình **thu thập** (*mutable reduction*). Một collector có thể dùng một cấu trúc tạm **có thể thay đổi** để gom các phần tử, nhưng trả về kết quả cuối ở **một kiểu khác**, gọn hơn, an toàn hơn hoặc đúng hợp đồng nghiệp vụ hơn.

Ví dụ: cần tính báo cáo doanh thu từ các đơn hàng. Trong lúc duyệt, ta lưu bộ đếm và tổng tiền vào một accumulator mutable. Sau khi duyệt xong, API chỉ nên trả một record `RevenueReport` chứa các số liệu cuối cùng, không để caller có quyền thay đổi accumulator.

Đây chính là vai trò của **finisher**:

~~~text
Stream<T>
   |
   v
supplier() --> A ban đầu
                 |
                 v
          accumulator(A,T) -- nhận các phần tử
                 |
                 v
          combiner(A,A)    -- gộp kết quả từng nhánh khi cần
                 |
                 v
          finisher(A) --> R kết quả cuối
~~~

Trong đó:

- **T**: kiểu phần tử đầu vào của Stream.
- **A**: kiểu **vùng tích lũy** (accumulation type), thường là object mutable nội bộ.
- **R**: kiểu **kết quả trả ra** sau khi hoàn tất thu gom.
- **finisher**: một `Function<A,R>` chuyển cấu trúc tạm A thành kết quả R.

Ví dụ minh họa ngắn, **không phải chương trình độc lập**:

~~~java
Collector<Order, ReportAccumulator, RevenueReport> collector =
        Collector.of(
                ReportAccumulator::new,   // supplier: () -> A
                ReportAccumulator::add,   // accumulator: (A,T) -> void
                ReportAccumulator::merge, // combiner: (A,A) -> A
                ReportAccumulator::finish // finisher: A -> R
        );
~~~

Nếu `ReportAccumulator` khác `RevenueReport`, việc dùng finisher **không phải bước phụ tùy ý**: đó là bước tạo kiểu kết quả đã hứa với caller. Collector có thể tích lũy thuận tiện bằng A nhưng **không lộ A** ra public API.

## 2. Collector<T,A,R> và bốn hàm thành phần

Interface `java.util.stream.Collector<T,A,R>` mô hình hóa phép giảm mutable. Khi tự tạo collector, thường cần bốn thành phần:

| Thành phần | Kiểu hàm | Mục đích |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Tạo container tích lũy mới |
| `accumulator()` | `BiConsumer<A,T>` | Đưa một T vào A bằng cách cập nhật A |
| `combiner()` | `BinaryOperator<A>` | Gộp hai container A thành một container A |
| `finisher()` | `Function<A,R>` | Chuyển A cuối thành R |

**Thứ tự hiểu ở mức ngữ nghĩa:** các phần tử được tích lũy vào một hay nhiều A; các A có thể được kết hợp; cuối cùng một A hoàn chỉnh được chuyển sang kết quả R. Chi tiết cách phân chia nhánh và thực thi trong parallel stream thuộc quyền triển khai Stream, không được coi là lịch thực thi cố định.

Collector còn có **characteristics** (đặc tính) như `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT` để mô tả những cam kết cụ thể. Chúng không phải nhãn trang trí: khai báo sai có thể dẫn đến kết quả không đúng.

### 2.1. Finisher là `Function<A,R>`, không phải `Consumer<A>`

Một sai lầm phổ biến là viết finisher chỉ in log rồi nghĩ rằng nó đã tạo kết quả. **Finisher phải trả R**, vì `Collector.finisher()` có kiểu `Function<A,R>`. Hình dung:

~~~java
Function<Accumulator, Report> finish = acc ->
        new Report(acc.count, acc.sum);
~~~

Đây là đoạn minh họa, giả định đã có kiểu `Accumulator`, `Report`. Nếu chỉ muốn log, đó là side effect chứ không phải kết quả của collector; tránh dựa vào log làm nghĩa chính của finisher.

### 2.2. R có thể khác A hoặc cùng A

Hai khả năng:

1. **Finisher không đồng nhất:** A là `ArrayList<T>`, R là `List<T>` bất biến; hoặc A là `MutableStats`, R là `Report`.
2. **Finisher đồng nhất (identity finish):** kết quả chính là accumulator A. Những collector kiểu này có thể được mô tả bởi đặc tính `IDENTITY_FINISH` nếu đáp ứng đầy đủ các yêu cầu của đặc tính đó.

Không phải lúc nào A và R cùng kiểu thì finisher cũng là identity. Ví dụ A là `List<String>`, R cũng là `List<String>`, nhưng finisher trả **một bản sao bất biến**. Đó vẫn là phép chuyển đổi thực sự, vì **object và khả năng sửa đổi đã thay đổi**.

## 3. Collector.of() và hai overload dễ nhầm

Java cung cấp hai hình thức quan trọng của `Collector.of`:

~~~java
// Overload identity-finish: không truyền finisher tường minh.
Collector.of(supplier, accumulator, combiner, characteristics...);

// Overload có finisher: A có thể khác R.
Collector.of(supplier, accumulator, combiner, finisher,
        characteristics...);
~~~

Hai dòng trên là **mô tả cú pháp**, không phải Java source hoàn chỉnh vì các biến chưa được khai báo.

**Khi nào dùng overload có finisher?**

- Cần trả record báo cáo thay vì class tích lũy mutable.
- Cần biến `StringBuilder` thành `String`.
- Cần tính trường dẫn xuất như trung bình, tỷ lệ phần trăm, trạng thái.
- Cần tạo một snapshot bất biến của danh sách hoặc map đã tích lũy.
- Cần xác thực các bất biến cuối cùng trước khi công bố kết quả.

**Khi nào không nhất thiết cần finisher?** Nếu muốn trả luôn collection mutable do Supplier tạo, ví dụ `ArrayList<T>`, có thể dùng collector có identity finish hoặc `Collectors.toCollection(ArrayList::new)`.

### 3.1. Không đánh dấu IDENTITY_FINISH nếu finisher thật sự chuyển đổi

`Collector.Characteristics.IDENTITY_FINISH` nói rằng finisher có thể được **bỏ qua**, vì một phép cast không kiểm tra từ A sang R đã đủ trả kết quả. Điều này chỉ đúng nếu A thực sự có thể đóng vai trò kết quả R theo hợp đồng collector.

Vì vậy, đoạn sau là **phản mẫu**:

~~~java
// SAI VỀ CONTRACT: A là StringBuilder, R là String,
// nhưng lại khai báo IDENTITY_FINISH.
Collector.of(
        StringBuilder::new,
        StringBuilder::append,
        (left, right) -> left.append(right),
        StringBuilder::toString,
        Collector.Characteristics.IDENTITY_FINISH);
~~~

Đây là ví dụ cố ý sai, không nên chạy. Nếu runtime bỏ qua finisher và cố trả A như R, code có thể gặp lỗi kiểu như `ClassCastException` hoặc hành vi vi phạm hợp đồng.

**Quan trọng:** Ngay cả khi A và R đều là `List<String>`, nếu finisher trả **List.copyOf(accumulator)** để bảo vệ kết quả, **không được** khai báo IDENTITY_FINISH. Nếu framework bỏ finisher, caller có thể nhận danh sách tích lũy mutable thay vì snapshot bất biến như API đã hứa.

## 4. Ví dụ Java 17 hoàn chỉnh: Mutable accumulator → immutable report

Tạo tệp **FinisherReportDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

record Order(String id, long amountCents, boolean paid) {}

record RevenueReport(long count, long totalCents,
                     double averageCents, List<String> ids) {}

public class FinisherReportDemo {
    static final class Accumulator {
        private long count;
        private long total;
        private final ArrayList<String> ids = new ArrayList<>();

        void add(Order order) {
            count++;
            total = Math.addExact(total, order.amountCents());
            ids.add(order.id());
        }

        Accumulator combine(Accumulator other) {
            count = Math.addExact(count, other.count);
            total = Math.addExact(total, other.total);
            ids.addAll(other.ids);
            return this;
        }

        RevenueReport finish() {
            double average = count == 0 ? 0.0
                    : (double) total / count;
            return new RevenueReport(
                    count, total, average, List.copyOf(ids));
        }
    }

    static Collector<Order, Accumulator, RevenueReport> reportCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 100, true),
                new Order("B", 150, false),
                new Order("C", 200, true)
        );

        RevenueReport report = orders.stream()
                .filter(Order::paid)
                .collect(reportCollector());

        RevenueReport empty = List.<Order>of()
                .stream().collect(reportCollector());

        System.out.println("Count: " + report.count());
        System.out.println("Total: " + report.totalCents());
        System.out.println("Average: " + report.averageCents());
        System.out.println("IDs: " + report.ids());

        System.out.println("Empty count: " + empty.count());
        System.out.println("Empty total: " + empty.totalCents());
        System.out.println("Empty average: " + empty.averageCents());
        System.out.println("Empty IDs: " + empty.ids());
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 FinisherReportDemo.java
java FinisherReportDemo
~~~

Stdout:

~~~text
Count: 2
Total: 300
Average: 150.0
IDs: [A, C]
Empty count: 0
Empty total: 0
Empty average: 0.0
Empty IDs: []
~~~

**Giải thích từng thành phần:**

1. **Supplier** là `Accumulator::new`. Mỗi container có count=0, total=0 và danh sách IDs rỗng.
2. **Accumulator** là `Accumulator::add`, được gọi với từng Order sau bước `filter(Order::paid)`. Chỉ A và C được thu thập.
3. **Combiner** là `Accumulator::combine`, gộp count, total và nối IDs giữa hai vùng tích lũy. Khi chạy tuần tự, combiner có thể không cần được gọi.
4. **Finisher** là `Accumulator::finish`, tính trung bình rồi tạo `RevenueReport`. Nó trả **List.copyOf(ids)** để giữ snapshot danh sách ID có cấu trúc không sửa được.
5. Phương thức `Math.addExact` bắt overflow của phép cộng long bằng `ArithmeticException`, thay vì âm thầm tràn số. Đây là chính sách của ví dụ, không phải mọi collector đều cần cùng chính sách.
6. Khi không có phần tử, finisher vẫn tạo RevenueReport với count=0, total=0, average=0.0 và danh sách rỗng. **0.0 ở đây là quy tắc fallback của chương trình**, không phải trung bình toán học xác định cho tập rỗng.

**Chọn đúng API:** Nếu caller cần phân biệt “không có dữ liệu” với “dữ liệu có trung bình đúng 0”, record nên dùng **OptionalDouble average** hoặc một trạng thái riêng, thay vì mặc định 0.0. Chọn cấu trúc R theo ý nghĩa nghiệp vụ, không chỉ theo tiện lợi khi in.

### 4.1. Tại sao A thường là mutable còn R nên bất biến?

Trong quá trình duyệt, mỗi phần tử cần cập nhật count, sum, danh sách... nên một accumulator mutable giúp thao tác đơn giản. Nhưng sau khi collect xong, caller thường chỉ nên thấy báo cáo cuối, không được vô tình thay đổi bộ đếm hay các invariant.

Trong ví dụ, `Accumulator` là private implementation detail của lớp, còn `RevenueReport` là record. Danh sách IDs được sao chép bằng `List.copyOf`, nên caller không thêm/bớt ID được.

**Cẩn trọng:** Record không tự tạo deep copy cho mọi trường chứa object. `List.copyOf` tạo danh sách không sửa được về mặt cấu trúc, nhưng nếu phần tử ID là một object mutable thay vì String, đối tượng phần tử đó vẫn có thể thay đổi nội dung. Với dữ liệu có ownership nghiêm ngặt, cần xác định phép sao chép sâu phù hợp.

## 5. Finisher phải chờ accumulator và combiner hoàn thành

Một cách suy nghĩ hữu ích:

~~~text
Nguồn tuần tự:
  supplier → A
  A = add(T1), add(T2), add(T3) ...
  finisher(A) → R

Nguồn song song (mô hình khái niệm):
  supplier → A1; add một tập con
  supplier → A2; add tập con khác
  supplier → A3; add tập con khác
  combine(A1,A2) → A12
  combine(A12,A3) → A
  finisher(A) → R
~~~

Đây là **mô hình ngữ nghĩa**, không phải lịch task cố định. Stream có quyền quyết định số container, chiến lược chia và thời điểm kết hợp phù hợp với collector characteristics.

**Combiner phải trả A**, không phải R. Nếu combiner lỡ gọi finisher và biến container thành record kết quả, các bước tiếp theo không còn container đúng kiểu để tích lũy hoặc kết hợp, đặc biệt trong parallel stream.

Phản mẫu ý tưởng:

~~~java
// SAI: combiner không được trả Report khi A là Accumulator.
// (left, right) -> new Report(...)
~~~

Đây là đoạn minh họa cố ý sai; combiner phải có chữ ký `BinaryOperator<A>`, tương ứng **(A,A) -> A**.

### 5.1. Luật đúng đắn: kết hợp từng phần không được thay đổi kết quả

Nếu một tập phần tử được chia thành nhiều nhóm, thu gom riêng rồi kết hợp, kết quả sau finisher phải tương đương với việc thu gom tuần tự toàn bộ tập theo hợp đồng collector.

Hình dung:

~~~text
finish(merge(accumulate(S1), accumulate(S2)))
    tương đương
finish(accumulate(S1 nối S2))
~~~

Với collector có thứ tự, cần giữ tương ứng encounter order khi kết hợp. Trong ví dụ RevenueReport, `ids.addAll(other.ids)` bảo toàn thứ tự nếu left và right đại diện hai đoạn dữ liệu theo encounter order; count và total cũng được gộp.

**Nguyên tắc thực hành:** Khi thiết kế custom collector, luôn kiểm thử cả stream tuần tự và song song với cùng dữ liệu, đặc biệt nếu finisher tạo danh sách có thứ tự hoặc tính toán phụ thuộc vào cách gộp.

## 6. Ví dụ Java 17: finisher với StringBuilder → String

StringBuilder là vùng tích lũy mutable hiệu quả để xây chuỗi, còn kiểu kết quả cuối cần một **String** bất biến.

Tạo tệp **StringFinisherDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class StringFinisherDemo {
    static Collector<String, StringBuilder, String> pipeJoiner() {
        return Collector.of(
                StringBuilder::new,
                (builder, value) -> {
                    if (builder.length() > 0) {
                        builder.append("|");
                    }
                    builder.append(value);
                },
                (left, right) -> {
                    if (right.length() == 0) {
                        return left;
                    }
                    if (left.length() > 0) {
                        left.append("|");
                    }
                    left.append(right);
                    return left;
                },
                StringBuilder::toString
        );
    }

    public static void main(String[] args) {
        List<String> values = List.of("a", "b", "c", "d");

        String joined = values.stream().collect(pipeJoiner());
        String parallel = values.parallelStream().collect(pipeJoiner());
        String empty = List.<String>of().stream().collect(pipeJoiner());

        System.out.println("Sequential: " + joined);
        System.out.println("Parallel: " + parallel);
        System.out.println("Empty: [" + empty + "]");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringFinisherDemo.java
java StringFinisherDemo
~~~

Stdout:

~~~text
Sequential: a|b|c|d
Parallel: a|b|c|d
Empty: []
~~~

**Vì sao ví dụ hợp lệ?**

- Supplier tạo một StringBuilder rỗng cho mỗi vùng tích lũy.
- Accumulator thêm delimiter khi cần rồi thêm String mới.
- Combiner nối hai StringBuilder, chèn delimiter giữa chúng **nếu cả hai có nội dung**; bỏ qua container rỗng một cách đúng đắn.
- Finisher biến StringBuilder cuối thành String.
- Collector này **không có đặc tính UNORDERED**, nên kết quả của stream có encounter order được yêu cầu bảo toàn thứ tự, kể cả khi collect song song.
- Dữ liệu ví dụ không chứa null và không chứa String rỗng. Với dữ liệu mà phần tử có thể rỗng, `builder.length() == 0` không phân biệt "chưa có phần tử" với "đã thêm một phần tử là chuỗi rỗng"; do đó **đây là ví dụ cho các token không rỗng**. Nếu cần hỗ trợ token rỗng, hãy lưu thêm `count` hoặc cờ `hasElement` trong accumulator, thay vì dựa vào độ dài StringBuilder.

**Lưu ý quan trọng:** Một Collector dùng StringBuilder có thể hợp lệ cho parallel stream khi mỗi vùng tích lũy được quản lý riêng và combiner gộp đúng cách. Điều đó không đồng nghĩa StringBuilder tự **thread-safe** để chia sẻ một instance duy nhất cho nhiều thread. Không khai báo CONCURRENT cho collector này.

Trong thực tế, với nhu cầu nối chuỗi đơn giản, **Collectors.joining("|")** đã có sẵn và thường dễ dùng hơn. Custom finisher hữu ích để hiểu cơ chế và khi kết quả R có hợp đồng đặc biệt không được collector chuẩn thể hiện thuận tiện.

## 7. Finisher tạo snapshot: List tích lũy thành List bất biến

Một use case phổ biến là cho phép accumulator thay đổi trong lúc thu thập, nhưng kết quả trả về không cho phép chỉnh sửa cấu trúc.

~~~java
Collector<String, ArrayList<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

Đây là **đoạn minh họa** cần import Collector, ArrayList, List. A là ArrayList<String>; R là List<String> **unmodifiable** do `List.copyOf` tạo.

Với input **["A","B"]**, kết quả R là List chứa A, B nhưng `result.add("C")` sẽ ném UnsupportedOperationException.

### 7.1. Phân biệt ba lựa chọn

- `Collectors.toCollection(ArrayList::new)`: trả ArrayList mutable.
- `stream.toList()` (Java 16+): trả List không sửa được; không cần viết custom collector khi chỉ cần danh sách đầu ra.
- `collect(Collector.of(..., List::copyOf))`: diễn đạt **chủ đích finisher** và có thể kết hợp logic tích lũy chuyên biệt nếu cần.

**Đừng viết custom collector nếu API chuẩn đáp ứng toàn bộ hợp đồng**. Mục tiêu học finisher không phải khuyến khích thay mọi `toList()` bằng bốn hàm custom.

### 7.2. Null có thể gây lỗi ở finisher

`ArrayList` cho phép lưu `null`, nhưng **List.copyOf(collection)** không chấp nhận phần tử null. Vì vậy, một stream có null có thể được tích lũy thành công vào A và **chỉ ném NullPointerException khi finisher chạy**.

Nếu nullable là hợp lệ, chọn kết quả R phù hợp hoặc lọc/biến đổi có chủ đích. Nếu nullable là lỗi dữ liệu, xác thực sớm với thông báo phù hợp. Đừng đoán từ việc accumulator nhận null rằng finisher cũng nhận được dữ liệu ấy.

### 7.3. Cảnh báo về aliasing

Finisher chỉ trả chính accumulator mutable:

~~~java
acc -> acc
~~~

là identity finish về giá trị object (khi A/R tương thích), nhưng **không tạo snapshot**. Nếu caller có thể giữ A và sửa nó, tính bất biến mong muốn bị phá vỡ.

Tương tự:

~~~java
acc -> Collections.unmodifiableList(acc)
~~~

là một **view không cho sửa qua view**, nhưng vẫn phản ánh thay đổi nếu có một tham chiếu khác tới `acc` sửa danh sách nền. Nếu muốn snapshot tách biệt rõ ràng, có thể dùng `List.copyOf(acc)` (khi không chứa null) hoặc `Collections.unmodifiableList(new ArrayList<>(acc))`. Chọn theo yêu cầu ownership và null policy.

## 8. Khi chỉ cần finisher bổ sung: Collectors.collectingAndThen()

Không phải lúc nào cần viết toàn bộ custom Collector. **Collectors.collectingAndThen(downstream, finisher)** bọc một collector có sẵn, rồi áp dụng một finisher lên kết quả của downstream.

Ví dụ:

~~~java
List<String> result = Stream.of("B", "A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(TreeSet::new),
                List::copyOf));
~~~

Đây là đoạn minh họa với import List, TreeSet, Stream, Collectors. Downstream thu vào **TreeSet<String>**, nên loại trùng và sắp xếp A, B. Finisher **List.copyOf** biến TreeSet thành **List<String> không sửa được** với thứ tự duyệt từ TreeSet. Kết quả là **[A, B]**.

**Đặc điểm thiết kế:**

- `collectingAndThen` tận dụng supplier, accumulator, combiner của downstream.
- Finisher bổ sung tạo kết quả mới hoặc kiểm tra cuối.
- Nó tạo collector mới **không mang IDENTITY_FINISH**, vì bước finish bổ sung không được bỏ qua.
- Có thể dùng làm downstream trong `groupingBy`: mỗi nhóm được gom rồi finish thành báo cáo/collection theo yêu cầu.
- Không cần tự triển khai combiner nếu downstream đã làm đúng công việc thu gom.

### 8.1. Ví dụ Java 17 hoàn chỉnh: collectingAndThen

Tạo tệp **CollectingAndThenDemo.java**:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectingAndThenDemo {
    public static void main(String[] args) {
        List<String> ordered = Stream.of(
                "pear", "apple", "pear", "banana")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(TreeSet::new),
                        List::copyOf));

        System.out.println("Values: " + ordered);

        try {
            ordered.add("kiwi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot add");
        }

        List<String> empty = Stream.<String>empty()
                .collect(Collectors.collectingAndThen(
                        Collectors.toList(), List::copyOf));
        System.out.println("Empty: " + empty);
    }
}
~~~

Chạy:

~~~bash
javac CollectingAndThenDemo.java
java CollectingAndThenDemo
~~~

Stdout:

~~~text
Values: [apple, banana, pear]
Cannot add
Empty: []
~~~

**Giải thích:**

1. `TreeSet` loại bản sao "pear" và sắp xếp theo String natural ordering.
2. `List.copyOf` tạo List không thể thêm/bớt phần tử; gọi add ném UnsupportedOperationException, được catch chỉ để minh họa hợp đồng.
3. Với nguồn rỗng, downstream toList tạo List rỗng, finisher copyOf trả List rỗng unmodifiable.
4. **Đừng dùng test sửa collection ở production** nếu chỉ để kiểm tra mutability; trong ví dụ, catch được sử dụng để chứng minh hành vi API.

**Vì sao cách này khác `stream.sorted().distinct().toList()`?** Với Stream<String> không null và yêu cầu output unmodifiable, cách thứ hai có thể ngắn gọn hơn. `collectingAndThen` đặc biệt hữu ích khi có một downstream collector phức tạp cần thêm bước finish chung, không phải cách bắt buộc cho mọi phép đổi kiểu.

## 9. Finisher và groupingBy(): chuyển accumulator riêng từng nhóm

Một collector có thể được đặt làm **downstream** của `Collectors.groupingBy`. Khi đó mỗi nhóm có vùng tích lũy A riêng; finisher của downstream chuyển từng A thành R.

Ví dụ: muốn thống kê số lượng và tổng điểm của nhân viên theo phòng ban, với R là record chuyên biệt.

Tạo tệp **GroupedFinisherDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Employee(String department, int score) {}
record DepartmentStats(long count, long total, double average) {}

public class GroupedFinisherDemo {
    static final class StatsAcc {
        long count;
        long total;

        void add(Employee employee) {
            count++;
            total += employee.score();
        }

        StatsAcc merge(StatsAcc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        DepartmentStats finish() {
            return new DepartmentStats(
                    count, total, count == 0 ? 0.0
                            : (double) total / count);
        }
    }

    static Collector<Employee, StatsAcc, DepartmentStats> collector() {
        return Collector.of(
                StatsAcc::new,
                StatsAcc::add,
                StatsAcc::merge,
                StatsAcc::finish);
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("IT", 10),
                new Employee("HR", 30),
                new Employee("IT", 20),
                new Employee("HR", 50),
                new Employee("Ops", 40)
        );

        Map<String, DepartmentStats> reports =
                employees.stream().collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        collector()));

        reports.forEach((department, stats) ->
                System.out.println(department
                        + ": count=" + stats.count()
                        + ", total=" + stats.total()
                        + ", average=" + stats.average()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GroupedFinisherDemo.java
java GroupedFinisherDemo
~~~

Stdout:

~~~text
HR: count=2, total=80, average=40.0
IT: count=2, total=30, average=15.0
Ops: count=1, total=40, average=40.0
~~~

**Phân tích:**

- groupingBy dùng `Employee::department` để quyết định khóa trước khi đưa Employee vào downstream.
- Mỗi nhóm có StatsAcc riêng: HR nhận điểm 30,50; IT nhận 10,20; Ops nhận 40.
- Khi xử lý từng nhóm, downstream finisher chuyển StatsAcc thành DepartmentStats.
- `TreeMap::new` xác định thứ tự duyệt khóa HR, IT, Ops để stdout ổn định.
- Nhóm không có Employee cha sẽ **không tự xuất hiện** trong kết quả groupingBy. Một accumulator rỗng chỉ được finish cho nhóm thực sự tồn tại; muốn hiển thị phòng ban có count=0 dù không có Employee thì phải bổ sung danh sách phòng ban chuẩn.
- Mẫu này khác với việc tạo `Map<String, List<Employee>>` rồi duyệt lại mỗi List để tính thống kê; downstream custom Collector xử lý ngay các phần tử từng nhóm.

**Cân nhắc overflow:** `StatsAcc` ở ví dụ dùng `long total += score`. Với dữ liệu rất lớn có thể tràn long; ví dụ tập nhỏ chỉ tập trung vào finisher. Khi cần tính chính xác và phát hiện tràn, dùng `Math.addExact` hoặc kiểu số đúng miền.

## 10. Finisher có thể xác thực kết quả cuối

Một finisher không nhất thiết chỉ là đổi kiểu. Nó cũng có thể **kiểm tra điều kiện cuối** của accumulator trước khi xuất báo cáo, ví dụ:

~~~java
Report finish() {
    if (count == 0) {
        throw new IllegalStateException("Cannot report empty data");
    }
    if (total < 0) {
        throw new IllegalStateException("Invalid total");
    }
    return new Report(count, total);
}
~~~

Đây là đoạn minh họa, giả định có kiểu `Report` và các trường `count`, `total` trong accumulator. Cách này hợp lệ về mặt ý định nếu **bất biến chỉ có thể đánh giá sau khi toàn bộ dữ liệu được gộp**.

Nhưng cần phân biệt:

- **Validation từng bản ghi** (null, giá trị âm, ID sai) nên được làm khi đọc/nhận dữ liệu hoặc trong accumulator theo hợp đồng. Không đợi cuối nếu lỗi cần phản hồi chính xác vị trí.
- **Validation của toàn bộ tập** (tổng phải khớp một ngưỡng, cần ít nhất một phần tử, số lượng đủ) có thể đặt ở finisher.
- Nếu finisher ném exception, `collect(...)` thất bại và không có R hợp lệ được trả về.
- Nếu finisher có side effect bắt buộc (ghi DB, gửi mail), cần thiết kế ranh giới transaction/lỗi rõ ràng; **không xem collector là nền tảng đảm bảo side effect nghiệp vụ**.

**Nguyên tắc:** Finisher nên có hành vi đơn giản, xác định và không can thiệp nguồn dữ liệu; lý tưởng là chuyển accumulator thành **kết quả hợp lệ**.

## 11. Identity finish: hiểu chính xác để không khai báo sai

Đặc tính `IDENTITY_FINISH` là một phần hợp đồng của `Collector`, không phải mẹo tối ưu tùy tiện.

Nếu collector tích lũy trực tiếp trong `ArrayList<T>` rồi trả chính ArrayList đó, có thể dùng overload ba hàm:

~~~java
Collector<String, ArrayList<String>, ArrayList<String>> listCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

Đây là đoạn minh họa cần import ArrayList và Collector. Loại collector này có identity finish; R là chính A.

Nếu thêm finisher biến `ArrayList<String>` thành `List.copyOf(acc)`:

~~~java
Collector<String, ArrayList<String>, List<String>> snapshot =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

thì không được khai báo IDENTITY_FINISH vì **R phải là snapshot** chứ không được trả trực tiếp A.

**Lỗi tinh vi:** Nếu chỉ nhìn kiểu tĩnh `A` và `R` đều implement List rồi gắn IDENTITY_FINISH, bạn có thể làm mất hợp đồng **immutable, sorted, validated** mà finisher thực sự mang lại.

### 11.1. Có được phép bỏ qua finisher không?

Khi collector **có IDENTITY_FINISH**, implementation có thể bỏ qua finisher vì accumulator chính là kết quả. Khi collector **không có đặc tính này**, finisher đóng vai trò chuyển đổi bắt buộc trong phép thu thập theo hợp đồng. Không nên viết test giả định finisher luôn được gọi chính xác bao nhiêu lần trong mọi ngữ cảnh (đặc biệt khi collector dùng làm downstream của collector kết hợp), mà nên kiểm tra **R cuối cùng** và các invariant.

## 12. UNORDERED và CONCURRENT không liên quan trực tiếp đến finisher

Collector characteristics khác cũng rất dễ bị dùng sai:

### 12.1. UNORDERED

`UNORDERED` nói rằng kết quả **không phụ thuộc thứ tự gặp** của phần tử. Nếu finisher tạo một List giữ thứ tự ban đầu hoặc chuỗi nối theo thứ tự, **không** khai báo UNORDERED.

Trong ví dụ `StringFinisherDemo`, kết quả `a|b|c|d` khác `d|c|b|a`, nên không được khẳng định thứ tự là không quan trọng.

Nếu chỉ tính tổng số nguyên không có ràng buộc thứ tự và phép kết hợp hợp lệ, collector có thể có đặc tính unordered tùy thiết kế. Tuy nhiên, với floating-point hoặc các side effect, việc thay đổi thứ tự có thể ảnh hưởng kết quả; cần đánh giá cẩn thận.

### 12.2. CONCURRENT

`CONCURRENT` cho phép nhiều thread tích lũy đồng thời vào **cùng một container** theo hợp đồng của collector trong những trường hợp thích hợp. Muốn gắn đặc tính này, accumulator phải bảo đảm thread safety, và ý nghĩa kết hợp/thứ tự phải phù hợp.

Một collector dùng `ArrayList`, `StringBuilder` hoặc các trường long thường **không có an toàn đồng thời** nếu chia sẻ container để cập nhật; không gắn CONCURRENT chỉ vì code được gọi từ `parallelStream()`.

**Phân biệt:** Parallel stream có thể dùng nhiều container riêng + combiner; đó không đồng nghĩa collector có đặc tính CONCURRENT.

### 12.3. Không cố “tối ưu” bằng cách khai báo mọi đặc tính

Các characteristics là **cam kết của collector**. Nếu không chắc collector có đáp ứng một đặc tính, bỏ nó đi thường an toàn hơn là tuyên bố sai. Tập trung trước vào ba luật: supplier trả container mới, accumulator thêm đúng dữ liệu và combiner tạo kết quả tương đương xử lý tuần tự; finisher trả R chính xác.

## 13. Tránh side effect trong finisher

Finisher là bước chuyển đổi kết quả, nhưng có thể phát sinh exception hoặc side effect như mọi hàm Java khác. Không nên đặt những hành động mà hệ thống cần bảo đảm chính xác một lần vào đây, chẳng hạn:

~~~java
// Phản mẫu thiết kế: finisher vừa trả kết quả
// vừa gửi một thông báo nghiệp vụ.
acc -> {
    mailService.sendReport(acc); // Side effect ngoài hệ thống.
    return acc.toReport();
}
~~~

Đây là đoạn minh họa cần các loại và biến phù hợp. Tại sao rủi ro?

- Khi dùng collector như một downstream của collector khác, cách triển khai finish phụ thuộc cấu trúc collector kết hợp; không nên xem nó là hệ thống điều phối gửi mail.
- Nếu finisher lỗi sau khi đã thực hiện một phần side effect, caller phải xử lý transaction/retry, nếu không dễ gửi trùng hoặc thiếu thông báo.
- Unit test hoặc phép thu thập thử có thể vô tình kích hoạt side effect.
- Khi API hứa **R là giá trị**, việc thêm I/O bắt buộc khiến ranh giới trách nhiệm khó quan sát.

Tốt hơn:

~~~java
Report report = records.stream().collect(reportCollector());
mailService.sendReport(report);
~~~

Đây là đoạn minh họa. Việc gửi thông báo nằm **sau khi kết quả R đã được tạo**, nên ứng dụng có thể thiết kế retry, logging, idempotency và xử lý lỗi riêng. Cách tách này không tự tạo giao dịch, nhưng giúp đặt đúng trách nhiệm.

## 14. Aliasing, dữ liệu mutable và ranh giới ownership

Giả sử finisher trả một record chứa List do accumulator đã xây:

~~~java
record Report(List<String> ids) {}
~~~

Finisher:

~~~java
acc -> new Report(acc.ids)
~~~

Đây là đoạn minh họa. Nếu một tham chiếu khác vẫn có thể sửa `acc.ids`, Report có thể thay đổi nội dung sau khi được công bố. Dù accumulator là private, vẫn nên xác định rõ ownership và liệu có lộ container mutable qua API hay không.

Một cách bảo vệ:

~~~java
acc -> new Report(List.copyOf(acc.ids))
~~~

`List.copyOf` tạo một danh sách không sửa được về cấu trúc, và với dữ liệu String bất biến của ví dụ thì kết quả báo cáo ổn định. Nếu cần cho phép null, `List.copyOf` sẽ không phù hợp nếu các phần tử có thể null.

**Đừng khẳng định finisher trả immutable object chỉ vì R là record.** Record không ngăn một List mutable được giữ bên trong. Không khẳng định **Collections.unmodifiableList(acc.ids)** là deep immutable snapshot: nó là view không sửa qua view, nhưng có thể phản ánh thay đổi của underlying list.

**Một collector tốt** không làm lộ vùng tích lũy mutable nếu public API hứa kết quả bất biến. Khi cần snapshot, hãy tạo bản sao đúng độ sâu và đúng chính sách null.

## 15. Null và exception trong từng giai đoạn

Một custom collector có thể lỗi ở nhiều giai đoạn:

| Giai đoạn | Lỗi thường gặp | Hướng xử lý |
| --- | --- | --- |
| Supplier | Trả null hoặc shared container không hợp lệ | Trả A mới hợp lệ |
| Accumulator | Dereference phần tử null, chuyển đổi không hợp lệ | Kiểm tra input và hợp đồng null |
| Combiner | Gộp sai, thiếu phần tử, mất thứ tự, overflow | Thiết kế phép merge đúng và kiểm thử parallel |
| Finisher | Vi phạm invariant, List.copyOf gặp null, phép chia cho 0 | Kiểm tra/định nghĩa trạng thái empty, xử lý lỗi rõ ràng |
| Sau collect | Caller sửa R dù hợp đồng không cho phép | Công bố loại R và mutability chính xác |

Nếu A chứa số đếm và tổng, nên xác định **overflow policy**. Nếu tính average, không nên chia `0/0` vô ý; có thể dùng `OptionalDouble` trong R để diễn đạt kết quả không tồn tại trên tập rỗng.

Nếu A chứa đối tượng có trạng thái mutable, tạo snapshot sau cùng không nhất thiết giải quyết mọi vấn đề thread safety khi **đang tích lũy**. Accumulator và combiner vẫn phải tuân thủ contract trong parallel stream.

## 16. Kiểm thử custom collector có finisher

Một bộ kiểm thử hữu ích nên bao phủ:

1. **Nguồn rỗng:** supplier tạo A hợp lệ; finisher trả R theo chính sách.
2. **Một phần tử:** kết quả chính xác.
3. **Nhiều phần tử:** count/sum/list đúng.
4. **Stream tuần tự và song song:** cùng kết quả theo contract; với kết quả thứ tự, kiểm tra encounter order.
5. **Combiner gộp nhánh rỗng:** không thêm dấu phân tách thừa, không mất phần tử.
6. **Null input:** hợp đồng cho phép hay từ chối rõ ràng.
7. **Overflow:** nếu domain cần phát hiện, dùng phép cộng có kiểm tra và test cận miền.
8. **Bất biến của R:** caller không sửa được collection nếu API hứa unmodifiable.
9. **Characteristics:** không khai báo IDENTITY_FINISH khi finisher tạo kiểu mới hoặc snapshot.
10. **Tính độc lập:** hai lần collect từ hai stream mới không chia sẻ accumulator vô tình.

### 16.1. Test bất biến sau khi finish

Với ví dụ RevenueReport:

~~~java
RevenueReport report = orders.stream()
        .collect(reportCollector());

// Hợp đồng: không thể sửa cấu trúc danh sách ID
// report.ids().add("X"); -> UnsupportedOperationException.
~~~

Đây là đoạn minh họa cần các lớp/method từ `FinisherReportDemo`. Một unit test có thể dùng `assertThrows(UnsupportedOperationException.class, () -> report.ids().add("X"))` với JUnit được khai báo phù hợp. JUnit không nằm trong Java SE và cần dependency riêng, nên bài này không dùng assertion JUnit làm ví dụ Java 17 tự chạy độc lập.

### 16.2. So sánh kết quả, đừng đoán lịch gọi

Trong parallel stream, không nên kiểm tra rằng Supplier được gọi đúng 4 lần hay Combiner đúng 3 lần. Lịch thực thi và mức phân chia công việc có thể thay đổi theo JVM, kích thước dữ liệu và cấu hình.

Hãy kiểm tra **R cuối cùng**, ví dụ tổng và danh sách, so với phương án tuần tự. Nếu thấy R khác nhau, điều tra các luật kết hợp, thứ tự và trạng thái mutable, không vội gắn CONCURRENT để “sửa” hiệu năng.

## 17. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Hiểu finisher là Consumer chỉ để log | Không tạo R, sai vai trò | Finisher có kiểu Function<A,R> |
| Cho rằng combiner được trả R | Sai kiểu, không còn A để kết hợp | Combiner phải trả A |
| Gắn IDENTITY_FINISH khi A là StringBuilder, R là String | Finisher có thể bị bỏ, gây lỗi kiểu | Không khai báo đặc tính sai |
| Gắn IDENTITY_FINISH khi finisher trả snapshot | R có thể không đạt bất biến mong muốn | Đánh dấu đúng contract |
| Supplier trả một accumulator dùng chung | Sai kết quả/race khi thu thập, nhất là parallel | Tạo A mới cho mỗi lần gọi |
| Combiner không gộp đủ trường count/sum/list | Mất dữ liệu trong parallel | Kiểm thử phép kết hợp đầy đủ |
| Trả List mutable trong record rồi tưởng immutable | Caller hoặc alias có thể thay đổi nội dung | Copy phù hợp vào R |
| Dùng List.copyOf với danh sách có null | NPE khi finish | Xác định null policy |
| Chia cho count=0 trong finisher | Lỗi hoặc kết quả không đúng nghĩa | Xử lý empty rõ ràng |
| Dùng StringBuilder.length() để biết đã có token, nhưng token rỗng hợp lệ | Dấu phân cách sai | Có flag/count riêng |
| Gắn UNORDERED cho collector nối String theo thứ tự | Cho phép đổi encounter order trái ý định | Không khai báo UNORDERED |
| Gắn CONCURRENT chỉ vì có parallelStream | Accumulator mutable không thread-safe | Dùng contract parallel với container riêng + combiner |
| Đặt I/O bắt buộc trong finisher | Khó retry/transaction, side effect phụ | Tách side effect ra sau collect |
| Dùng custom collector cho việc toList đơn giản | Tăng độ phức tạp không cần thiết | Dùng collector/API chuẩn |
| Mong nhóm không có phần tử tự xuất hiện khi groupingBy | Không có khóa để tạo nhóm | Bổ sung tập khóa chuẩn khi cần |
| Tính tổng không kiểm tra overflow trong miền nhạy cảm | Báo cáo sai mà không có lỗi | Dùng kiểu số hoặc phép cộng phù hợp |

## 18. Checklist thiết kế finisher

Trước khi tạo `Collector<T,A,R>`, tự hỏi:

1. **T là gì?** Kiểu phần tử đầu vào.
2. **A là gì?** Container phù hợp để update và merge.
3. **R là gì?** Kết quả public API thật sự cần.
4. **Có cần R khác A không?** Nếu không, collector sẵn có hoặc identity finish có thể đủ.
5. **Finisher phải tạo gì?** Record, String, Map bất biến, danh sách đã chuẩn hóa, báo cáo đã tính tỷ lệ?
6. **Empty input cần R thế nào?** Giá trị 0, Optional, hay exception?
7. **Supplier có tạo A mới không?** Không chia sẻ mutable container.
8. **Accumulator có xử lý T null và overflow đúng không?**
9. **Combiner có trả đúng A, gộp đủ trạng thái và bảo toàn thứ tự theo contract không?**
10. **R có lộ mutable alias từ A không?** Chọn snapshot đúng.
11. **Có vô tình khai báo IDENTITY_FINISH khi finisher không phải identity không?**
12. **Có cần UNORDERED hoặc CONCURRENT thật không?** Không gắn characteristic để “tối ưu” khi chưa có guarantee.
13. **Có nên dùng collectingAndThen thay vì custom toàn bộ không?**
14. **Đã kiểm thử cả tuần tự, song song, rỗng và lỗi chưa?**

## 19. Bài tập

### Bài 1: Nhận biết A và R

Một collector dùng `StringBuilder` tích lũy tên người dùng, nhưng trả `String` hoàn chỉnh. Hãy xác định T, A, R; viết chữ ký supplier, accumulator, combiner, finisher.

### Bài 2: Sửa combiner thiếu trường

Một `StatsAcc` có `count`, `sum` và `ids`, nhưng combiner chỉ cộng `sum`. Hãy giải thích vì sao kết quả có thể đúng trên Stream tuần tự mà sai trên parallel stream. Viết merge đúng cả ba trường.

### Bài 3: Bảo vệ snapshot

Một collector thu String vào ArrayList. Viết finisher trả danh sách không sửa được bằng `List.copyOf`. So sánh với `Collections.unmodifiableList(acc)` trong trường hợp underlying list còn bị alias sửa.

### Bài 4: IDENTITY_FINISH

Đoạn sau có hợp đồng hợp lệ không?

~~~java
Collector.of(
        StringBuilder::new,
        StringBuilder::append,
        (a,b) -> a.append(b),
        StringBuilder::toString,
        Collector.Characteristics.IDENTITY_FINISH);
~~~

Đây là đoạn phản mẫu cố ý. Giải thích vì sao A = StringBuilder và R = String không cho phép bỏ qua finisher.

### Bài 5: Báo cáo nhóm

Cho List<Employee> có department và score. Viết downstream collector dùng StatsAcc rồi finish thành DepartmentStats(count,total,average). Đặt collector đó vào `groupingBy(Employee::department, TreeMap::new, collector)`. Tự tính expected output cho hai phòng ban và một phòng ban không có nhân viên.

### Bài 6: Empty input

Nếu một collector tính average mà count bằng 0, hãy thiết kế hai chính sách:
- Trả record có `OptionalDouble.empty()`.
- Ném `IllegalStateException` nếu domain bắt buộc ít nhất một bản ghi.

Chính sách nào đúng khi “không có dữ liệu” là một trạng thái bình thường?

### Bài 7: So sánh collectingAndThen

Thu các từ `["b","a","b"]` thành TreeSet rồi đổi sang List unmodifiable bằng `collectingAndThen(toCollection(TreeSet::new), List::copyOf)`. Vì sao không cần viết lại supplier/accumulator/combiner?

### Bài 8: Đảm bảo hành vi parallel

Viết custom collector nối các token không rỗng bằng dấu `|`. Chạy trên nguồn List có encounter order với `stream()` và `parallelStream()`. Kiểm tra kết quả cuối thay vì đếm số lần supplier/combiner được gọi.

## 20. Ghi nhớ

**Finisher là phép chuyển đổi `A → R` của Collector**: sau khi các phần tử T đã được thu gom và các container A đã được kết hợp theo yêu cầu, finisher biến vùng tích lũy thành giá trị kết quả. Nó có thể tạo record báo cáo, String từ StringBuilder, snapshot không sửa được hoặc trạng thái đã được xác thực.

Để custom collector đúng, **supplier phải tạo A mới**, **accumulator cập nhật A**, **combiner gộp A với A và trả A**, **finisher trả R**. Nếu R khác A hoặc finisher tạo snapshot thực sự, **không đánh dấu IDENTITY_FINISH**.

Ưu tiên **Collectors.collectingAndThen** khi đã có downstream collector phù hợp và chỉ cần thêm bước chuyển đổi cuối. Khi nghiệp vụ cần A chuyên biệt và R có hợp đồng riêng, dùng **Collector.of(supplier, accumulator, combiner, finisher)** cùng kiểm thử cho input rỗng, nguồn có thứ tự và parallel.

Câu hỏi quyết định thiết kế: **“Tôi cần giữ cái gì trong lúc tích lũy, nhưng cuối cùng muốn công bố một kết quả có kiểu và bất biến nào?”** Đó chính là lý do tồn tại của finisher trong Java Collector.
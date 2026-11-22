# boxed() và mapToObj() trong Primitive Stream (Java 8+)

## 1. Mục tiêu: chuyển từ luồng giá trị nguyên thủy sang luồng đối tượng

Java cung cấp ba loại **primitive stream** chính: **IntStream**, **LongStream** và **DoubleStream**. Chúng xử lý trực tiếp các giá trị **int**, **long**, **double** và có những phép toán như **sum()**, **average()**, **min()**, **max()** mà không cần biến từng giá trị thành đối tượng wrapper.

Tuy nhiên, khi cần tạo **List<Integer>**, phân nhóm bằng **Collectors.groupingBy(...)**, tạo mã hiển thị **String**, hoặc tạo một đối tượng nghiệp vụ từ số nguyên, ta cần chuyển sang **Stream<T>** của các đối tượng. Hai phương thức trung tâm là:

- **boxed()**: chuyển mỗi giá trị nguyên thủy sang đúng kiểu wrapper của nó, ví dụ **int -> Integer**. Mục đích là giữ nguyên ý nghĩa giá trị số và đổi sang **Stream<Integer>**.
- **mapToObj(mapper)**: áp dụng hàm chuyển đổi do bạn định nghĩa cho mỗi giá trị nguyên thủy và nhận một **Stream<U>**; U có thể là **String**, **Integer**, **Long**, một record/class nghiệp vụ hoặc kiểu tham chiếu khác.

Sau bài này, bạn sẽ phân biệt chính xác hai API; theo dõi kiểu của từng bước pipeline; biết cách chuyển sang List/Map/mảng; hiểu boxing/unboxing, null, thứ tự, hiệu suất và các lỗi thường gặp.

Các phương thức **boxed()** và **mapToObj()** đã có từ Java 8 và vẫn là API hợp lệ, được duy trì trong Java hiện đại. Các ví dụ chính được viết tương thích Java 8 và chạy được trên JDK 17+.

## 2. Primitive Stream và object Stream khác nhau ở đâu?

| Loại luồng | Kiểu phần tử mà API xử lý | Ví dụ tạo | Phép toán có ích |
| --- | --- | --- | --- |
| IntStream | int | IntStream.rangeClosed(1, 3) | sum(), average(), map(IntUnaryOperator) |
| LongStream | long | LongStream.of(2L, 4L) | sum(), average(), map(LongUnaryOperator) |
| DoubleStream | double | DoubleStream.of(1.5, 2.5) | sum(), average(), map(DoubleUnaryOperator) |
| Stream<T> | đối tượng tham chiếu T | Stream.of("A", "B") | collect(Collector), map(Function), groupingBy qua collect |

Với **IntStream.of(1, 2, 3)**, phần tử đi qua lambda kiểu **int**. Với **Stream<Integer>**, phần tử là một đối tượng **Integer**, có thể làm việc với các API generic yêu cầu kiểu tham chiếu.

**Java không có Stream<int> hoặc List<int>.** Generic của Java dùng kiểu tham chiếu, nên khi cần **Stream<Integer>** ta dùng **boxed()** hoặc **mapToObj(...)**. Java cũng không có các chuyên biệt Stream chuẩn tương ứng riêng cho boolean, byte, short, char, float; ba primitive stream của package này là int, long và double.

Sơ đồ biến đổi:

~~~text
IntStream        -- boxed() ------------------> Stream<Integer>
        \ 
         \------ mapToObj(int -> U) ----------> Stream<U>

LongStream       -- boxed() ------------------> Stream<Long>
                 -- mapToObj(long -> U) ------> Stream<U>

DoubleStream     -- boxed() ------------------> Stream<Double>
                 -- mapToObj(double -> U) ----> Stream<U>
~~~

Hai phép biến đổi đều là **intermediate operation**: chúng tạo pipeline mới, chưa thu thập kết quả và chưa tự chạy mọi phần tử. Terminal operation như **collect**, **toArray**, **forEach** hoặc **count** mới kích hoạt việc xử lý khi cần.

## 3. Chữ ký API và kiểu kết quả

Trong API Java Stream hiện hành, các phương thức có các chữ ký cốt lõi sau:

| Nguồn | Phương thức | Kiểu trả về |
| --- | --- | --- |
| IntStream | boxed() | Stream<Integer> |
| LongStream | boxed() | Stream<Long> |
| DoubleStream | boxed() | Stream<Double> |
| IntStream | <U> mapToObj(IntFunction<? extends U>) | Stream<U> |
| LongStream | <U> mapToObj(LongFunction<? extends U>) | Stream<U> |
| DoubleStream | <U> mapToObj(DoubleFunction<? extends U>) | Stream<U> |

Các kiểu hàm mapper nhận primitive tương ứng: **IntFunction** nhận int, **LongFunction** nhận long, **DoubleFunction** nhận double; chúng trả một đối tượng thuộc kiểu U. Không phải đóng hộp đầu vào thành Integer/Long/Double chỉ để gọi mapper.

Ví dụ độc lập ở mức biểu thức:

~~~java
Stream<Integer> a = IntStream.of(1, 2, 3).boxed();
Stream<Long> b = LongStream.of(4L, 5L).boxed();
Stream<Double> c = DoubleStream.of(1.5, 2.5).boxed();

Stream<String> labels = IntStream.of(1, 2, 3)
        .mapToObj(n -> "ID-" + n);

Stream<Integer> alsoBoxed = IntStream.of(1, 2, 3)
        .mapToObj(Integer::valueOf);
~~~

Ở đoạn minh họa này, các lớp **Stream**, **IntStream**, **LongStream**, **DoubleStream** cần import từ **java.util.stream**.

**boxed()** biểu diễn trực tiếp ý định "chuyển sang wrapper". **mapToObj(Integer::valueOf)** tạo giá trị Integer tương ứng và có cùng kiểu kết quả, nhưng diễn đạt bằng ánh xạ do người viết cung cấp. Khi chỉ cần wrapper tương ứng, thường chọn **boxed()** vì rõ ràng hơn.

**mapToObj(n -> n)** cũng có thể tạo **Stream<Integer>** nhờ boxing tự động của Java khi suy luận kiểu trả về. Tuy nhiên, đây vẫn là phép ánh xạ; nếu mục đích chỉ là boxing, **boxed()** thể hiện ý định tốt hơn.

## 4. Hiểu đúng boxed(): không phải chuyển thành List hoặc mảng

**IntStream.boxed()** tạo **Stream<Integer>**, chưa tạo **List<Integer>**, **Integer[]**, hay một collection sẵn có.

~~~java
// Dòng này chỉ tạo pipeline object Stream.
Stream<Integer> stream = IntStream.rangeClosed(1, 4).boxed();

// Collect mới tạo danh sách.
List<Integer> numbers = stream.collect(Collectors.toList());
// [1, 2, 3, 4]
~~~

**Không tái sử dụng stream** sau khi terminal operation đã chạy. Nếu muốn tạo nhiều kết quả từ cùng một nguồn, hãy tạo pipeline mới từ nguồn.

Các cách kết thúc pipeline sau boxing:

~~~java
List<Integer> numbers = IntStream.rangeClosed(1, 4)
        .boxed()
        .collect(Collectors.toList());

Set<Integer> unique = IntStream.of(2, 2, 3)
        .boxed()
        .collect(Collectors.toSet());

Integer[] array = IntStream.rangeClosed(1, 4)
        .boxed()
        .toArray(Integer[]::new);
~~~

Giải thích:

- **toList** thông qua **Collectors.toList()** thu các Integer vào List, nhưng API Collector này **không hứa kiểu List cụ thể hay khả năng sửa đổi** của kết quả. Nếu nhất thiết cần List có thể sửa, dùng **Collectors.toCollection(ArrayList::new)**.
- **toSet()** loại các giá trị Integer trùng theo equals/hashCode; thứ tự duyệt Set không được bảo đảm.
- **toArray(Integer[]::new)** tạo mảng runtime kiểu Integer[].

Trên Java 16+, bạn cũng có thể viết:

~~~java
List<Integer> numbers = IntStream.rangeClosed(1, 4)
        .boxed()
        .toList(); // Java 16+; List kết quả không hỗ trợ thay đổi phần tử
~~~

**Stream.toList()** không phải API Java 8, dù hiện nay vẫn hoàn toàn áp dụng. Nếu dự án cần tương thích Java 8, giữ cách **collect(Collectors.toList())** hoặc **toCollection(...)**.

## 5. mapToObj(): biến mỗi primitive thành đối tượng theo quy tắc riêng

Điểm mạnh của **mapToObj** là tạo ra một kiểu đối tượng **khác** với wrapper thông thường.

### 5.1. Tạo chuỗi để hiển thị

~~~java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "Order-" + n)
        .collect(Collectors.toList());
// [Order-1, Order-2, Order-3]
~~~

Ở đây **n** là primitive int; lambda tạo String, và kiểu sau map là **Stream<String>**. Không có bước **boxed()** riêng trước đó.

### 5.2. Tạo đối tượng nghiệp vụ

Giả sử hệ thống có class **Ticket** với constructor **Ticket(int id, String status)**:

~~~java
List<Ticket> tickets = IntStream.rangeClosed(1, 3)
        .mapToObj(id -> new Ticket(id, "open"))
        .collect(Collectors.toList());
~~~

Mỗi số nguyên được ánh xạ thành một Ticket. Ví dụ đầy đủ có class Ticket thực sự nằm ở phần 8, nên có thể biên dịch toàn bộ mà không cần tạo class giả.

### 5.3. LongStream và DoubleStream cũng dùng mapToObj

~~~java
List<String> longIds = LongStream.of(1000L, 2000L)
        .mapToObj(value -> "L-" + value)
        .collect(Collectors.toList());
// [L-1000, L-2000]

List<String> formatted = DoubleStream.of(1.25, 2.5)
        .mapToObj(value ->
                String.format(Locale.ROOT, "%.2f", value))
        .collect(Collectors.toList());
// [1.25, 2.50]
~~~

**Locale.ROOT** giúp ví dụ định dạng thập phân dự đoán được, không thay đổi dấu phân cách theo locale hệ thống. Đây là ví dụ hiển thị số; nếu bài toán là tiền tệ hoặc tài chính, cần một mô hình làm tròn và chính xác riêng thay vì dựa đơn thuần vào double.

### 5.4. mapToObj có thể vẫn trả wrapper

~~~java
Stream<Integer> viaMapper = IntStream.rangeClosed(1, 3)
        .mapToObj(Integer::valueOf);

Stream<Integer> viaBoxed = IntStream.rangeClosed(1, 3)
        .boxed();
~~~

Hai pipeline tương đương về **giá trị từng phần tử** (1, 2, 3) và kiểu **Stream<Integer>**. Không dựa vào danh tính đối tượng wrapper để so sánh chúng; quy tắc caching của wrapper có thể khiến một số tham chiếu được dùng lại.

## 6. boxed(), mapToObj(), map() và mapToInt(): chọn đúng hướng

Bốn phương thức thường bị nhầm vì tên tương tự nhau:

| Lời gọi | Trước -> sau | Mục đích |
| --- | --- | --- |
| IntStream.map(IntUnaryOperator) | int -> int | Biến đổi số nhưng giữ primitive stream |
| IntStream.boxed() | int -> Integer | Chuyển sang wrapper tương ứng |
| IntStream.mapToObj(IntFunction<U>) | int -> U | Biến đổi primitive thành đối tượng bất kỳ |
| Stream<T>.map(Function<T,R>) | T -> R | Biến đổi đối tượng thành đối tượng |
| Stream<T>.mapToInt(ToIntFunction<T>) | T -> int | Chuyển object stream về IntStream |

Ví dụ tính bình phương:

~~~java
int sum = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .sum(); // 1 + 4 + 9 + 16 = 30
~~~

Pipeline trên **không cần boxing** vì toàn bộ công việc vẫn là phép toán trên int.

Nếu yêu cầu là danh sách chuỗi bình phương:

~~~java
List<String> squares = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .mapToObj(String::valueOf)
        .collect(Collectors.toList());
// [1, 4, 9, 16] dưới dạng List<String>
~~~

Ở đây đặt **map** trước **mapToObj** giúp biến đổi số bằng primitive rồi mới chuyển thành String.

Nếu viết **boxed().map(n -> n * n)**, biểu thức vẫn hoạt động nhưng các phần tử bên trong **Stream<Integer>** phải qua unboxing và boxing khi tính toán. Nếu chỉ cần tổng hay phép xử lý số học, nên ở lại IntStream đến khi thật sự cần đối tượng.

Để chuyển ngược từ **Stream<Integer>** sang **IntStream**:

~~~java
int sum = IntStream.rangeClosed(1, 4)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum(); // 10
~~~

Việc chuyển qua lại ở đây chỉ để minh họa; ứng dụng thực tế nên tính trực tiếp bằng **IntStream.rangeClosed(1, 4).sum()** nếu không cần dữ liệu trung gian dạng wrapper.

## 7. Sơ đồ quyết định kiểu kết quả và terminal operation

~~~text
Bắt đầu: IntStream / LongStream / DoubleStream
   |
   | Cần chỉ xử lý số nguyên thủy?
   +-- Có -> filter / map / sum / average / min / max / toArray()
   |
   | Cần Stream<Integer>/Stream<Long>/Stream<Double>?
   +-- Có -> boxed()
   |           +-- collect(toList/toSet/groupingBy...)
   |           +-- toArray(Wrapper[]::new)
   |
   | Cần String, DTO, label hoặc đối tượng khác?
   +-- Có -> mapToObj(primitive -> object)
               +-- map/filter/groupingBy/collect...
               +-- toArray(Target[]::new)
~~~

**Tại thời điểm gọi boxed/mapToObj, bạn mới có một Stream của object, chưa có List, Set hay array.** Bộ sưu tập xuất hiện sau một terminal operation phù hợp.

Nếu cần **int[]**, không đi vòng qua boxing:

~~~java
int[] primitive = IntStream.rangeClosed(1, 3).toArray();
~~~

Nếu cần **Integer[]**, phải tạo mảng wrapper từ object stream:

~~~java
Integer[] wrappers = IntStream.rangeClosed(1, 3)
        .boxed()
        .toArray(Integer[]::new);
~~~

Nếu cần **String[]**, có thể map trực tiếp:

~~~java
String[] labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "ID-" + n)
        .toArray(String[]::new);
~~~

## 8. Chương trình chạy được: cả boxing, mapping, grouping và kiểu mảng

Tạo tệp **PrimitiveObjectBridgeDemo.java**:

~~~java
import java.util.*;
import java.util.stream.*;

public class PrimitiveObjectBridgeDemo {
    static final class Ticket {
        final int id;
        final String status;

        Ticket(int id, String status) {
            this.id = id;
            this.status = status;
        }

        @Override
        public String toString() {
            return id + ":" + status;
        }
    }

    public static void main(String[] args) {
        List<Integer> boxedIds = IntStream.rangeClosed(1, 4)
                .boxed().collect(Collectors.toList());

        List<String> labels = IntStream.rangeClosed(1, 4)
                .mapToObj(n -> "T-" + n).collect(Collectors.toList());

        List<Ticket> tickets = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> new Ticket(n, "open"))
                .collect(Collectors.toList());

        List<Long> longs = LongStream.of(5L, 8L)
                .boxed().collect(Collectors.toList());

        List<String> prices = DoubleStream.of(1.25, 2.5)
                .mapToObj(n ->
                        String.format(Locale.ROOT, "%.2f", n))
                .collect(Collectors.toList());

        Map<String, List<Integer>> byParity = IntStream.rangeClosed(1, 6)
                .boxed().collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd",
                        TreeMap::new, Collectors.toList()));

        int primitiveSum = IntStream.rangeClosed(1, 4).sum();

        int unboxedSum = boxedIds.stream()
                .mapToInt(Integer::intValue).sum();

        int[] raw = IntStream.rangeClosed(1, 4).toArray();

        Integer[] typed = IntStream.rangeClosed(1, 4)
                .boxed().toArray(Integer[]::new);

        String[] typedLabels = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "T-" + n).toArray(String[]::new);

        List<String> nonNull = IntStream.of(-1, 0, 1)
                .mapToObj(n -> n < 0 ? null : "N" + n)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());

        System.out.println("boxed: " + boxedIds);
        System.out.println("labels: " + labels);
        System.out.println("tickets: " + tickets);
        System.out.println("longs: " + longs);
        System.out.println("prices: " + prices);
        System.out.println("groups: " + byParity);
        System.out.println("sum: " + primitiveSum + " / " + unboxedSum);
        System.out.println("raw array: " + Arrays.toString(raw));
        System.out.println("boxed array: " + Arrays.toString(typed));
        System.out.println("label array: " + Arrays.toString(typedLabels));
        System.out.println("non-null: " + nonNull);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrimitiveObjectBridgeDemo.java
java PrimitiveObjectBridgeDemo
~~~

Đầu ra:

~~~text
boxed: [1, 2, 3, 4]
labels: [T-1, T-2, T-3, T-4]
tickets: [1:open, 2:open, 3:open]
longs: [5, 8]
prices: [1.25, 2.50]
groups: {even=[2, 4, 6], odd=[1, 3, 5]}
sum: 10 / 10
raw array: [1, 2, 3, 4]
boxed array: [1, 2, 3, 4]
label array: [T-1, T-2, T-3]
non-null: [N0, N1]
~~~

Chương trình được viết bằng tính năng có sẵn trong Java 8 và có thể chạy trên Java 17+. Phần **TreeMap::new** trong **groupingBy** cố định thứ tự duyệt khóa **even** rồi **odd**, giúp stdout xác định. **Collectors.toList()** giữ thứ tự phần tử trong các nhóm của nguồn ordered dùng trong ví dụ này.

Phân tích đầu ra:

1. **boxedIds**: giá trị int được chuyển sang Integer. Kết quả in trong List vẫn giống số nguyên nhưng kiểu các phần tử là wrapper.
2. **labels**: mapToObj chuyển số thành chuỗi **T-n** và không cần bước boxing trung gian.
3. **tickets**: mỗi số là id để xây một **Ticket**. **Ticket.toString()** chỉ được định nghĩa để minh họa đầu ra ổn định.
4. **longs**: LongStream.boxed tạo Stream<Long>, sau collect là List<Long>.
5. **prices**: DoubleStream.mapToObj tạo String đã định dạng, không trả Stream<Double>.
6. **byParity**: groupingBy là Collector dùng trên **Stream<Integer>** sau boxing. Mỗi khóa có List<Integer> tương ứng.
7. **primitiveSum** và **unboxedSum** đều là 10; việc boxing rồi unboxing không cần thiết trong bài toán chỉ tính tổng.
8. **raw** là int[], **typed** là Integer[], **typedLabels** là String[]. Cách in Arrays.toString giống nhau với số, nhưng kiểu mảng thực tế khác nhau.
9. **nonNull** cho thấy mapper có thể trả null và object stream có thể lọc bỏ null trước khi thu thập.

## 9. Khi nào boxed() là lựa chọn thích hợp?

### 9.1. Cần Collector chỉ áp dụng trực tiếp với Stream<T>

Các **Collectors** như **groupingBy**, **partitioningBy**, **toMap**, **toSet** là công cụ dành cho object stream. Nếu nguồn là IntStream và yêu cầu Map nhóm các số, boxed cung cấp chiếc cầu trực tiếp:

~~~java
Map<String, List<Integer>> groups =
        IntStream.rangeClosed(1, 6)
                .boxed()
                .collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd"));
~~~

Các phần tử Integer trong mỗi nhóm vẫn phản ánh giá trị nguồn. Nếu cần thứ tự Map nhất định, dùng overload **groupingBy(classifier, mapFactory, downstream)**, như chương trình ở phần 8.

Lưu ý **IntStream** cũng có một overload **collect(supplier, accumulator, combiner)** riêng sử dụng primitive int. Tuy nhiên, nó **không phải** phương thức **collect(Collector)** của Stream<T>. Nếu cần trực tiếp **Collectors.groupingBy**, cách đơn giản là chuyển sang Stream<Integer> bằng boxed.

### 9.2. Cần List<Integer> cho API có generic

~~~java
List<Integer> indices = IntStream.range(0, 4)
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
// [0, 1, 2, 3]
~~~

Kết quả là ArrayList<Integer> có thể sửa đổi nhờ collector **toCollection(ArrayList::new)**. Đây là lựa chọn phù hợp nếu API cần danh sách các chỉ số và người gọi phải có thể thêm/xóa phần tử.

### 9.3. Cần gọi phương thức yêu cầu Stream<Integer>

Nếu một hàm nhận **Stream<Integer>**, không thể đưa **IntStream** vào chỉ vì cả hai biểu diễn số nguyên. Chúng là **hai kiểu API khác nhau**. Boxing làm rõ bước chuyển:

~~~java
Stream<Integer> values = IntStream.of(3, 5, 8).boxed();
~~~

Khi dùng xong Stream này trong một terminal operation, phải tạo stream mới nếu cần tính toán tiếp từ nguồn.

## 10. Khi nào mapToObj() là lựa chọn thích hợp?

### 10.1. Tạo nhãn UI và mã định danh

~~~java
List<String> rowIds = IntStream.rangeClosed(1, 3)
        .mapToObj(index -> "row-" + index)
        .collect(Collectors.toList());
// [row-1, row-2, row-3]
~~~

Thứ tự từ IntStream.rangeClosed được giữ ở List sau collect với nguồn ordered. Tuy nhiên, nếu dùng parallel stream, không được giả định mapper được gọi theo thứ tự thời gian tăng dần; chỉ kết quả có hợp đồng về encounter order mới được sử dụng làm căn cứ.

### 10.2. Tạo hàng dữ liệu có chỉ số đi kèm

Giả sử bạn có danh sách tên và cần kết quả chứa **vị trí** cùng **giá trị**. Với Java 17+ có thể dùng **record** để khai báo dữ liệu gọn:

~~~java
record IndexedName(int index, String name) {}

List<String> names = Arrays.asList("An", "Binh", "Chi");
List<IndexedName> rows = IntStream.range(0, names.size())
        .mapToObj(i -> new IndexedName(i, names.get(i)))
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa bổ sung yêu cầu Java 17+** do sử dụng record. Phương thức mapToObj vẫn là API Java 8; nếu dự án yêu cầu Java 8, thay record bằng một class có constructor tương ứng. Nguồn List trong ví dụ không bị sửa trong khi pipeline chạy.

### 10.3. Tạo ngày theo offset

~~~java
java.time.LocalDate start = java.time.LocalDate.of(2026, 1, 1);

List<java.time.LocalDate> days = IntStream.range(0, 3)
        .mapToObj(start::plusDays)
        .collect(Collectors.toList());
// [2026-01-01, 2026-01-02, 2026-01-03]
~~~

Đây là ví dụ hay dùng cho lịch: mapper nhận số ngày offset và trả **LocalDate**. **LocalDate.plusDays(long)** chấp nhận int nhờ mở rộng sang long, nên method reference có thể phù hợp với IntFunction<LocalDate>. Nguồn vẫn chỉ là các int, còn Stream mới chứa các đối tượng ngày bất biến.

### 10.4. Cần tính toán số trước, rồi tạo đối tượng cuối

~~~java
List<String> labels = IntStream.rangeClosed(1, 3)
        .map(n -> n * 10)
        .mapToObj(n -> "Score " + n)
        .collect(Collectors.toList());
// [Score 10, Score 20, Score 30]
~~~

**map** giữ phần primitive, **mapToObj** tạo String ở bước cuối trước khi collect. Cách này thường rõ và gọn hơn **boxed().map(...)** cho cùng mục tiêu, đồng thời tránh bước wrapper trung gian không cần thiết.

## 11. Kiểu của kết quả: List, mảng, Optional và toán tử terminal

### 11.1. Sự khác biệt giữa int[], Integer[] và Object[]

~~~java
int[] primitive = IntStream.of(1, 2).toArray();

Integer[] integerArray = IntStream.of(1, 2)
        .boxed()
        .toArray(Integer[]::new);

Object[] objectArray = IntStream.of(1, 2)
        .boxed()
        .toArray();
~~~

- PrimitiveStream.toArray() tạo mảng nguyên thủy tương ứng (**int[]**, **long[]**, **double[]**).
- Với **Stream<Integer>**, phương thức **toArray()** không tham số trả **Object[]**; muốn **Integer[]** phải truyền **Integer[]::new**.
- **Integer[] không thể ép kiểu trực tiếp thành int[]**. Muốn int[] từ List<Integer>, dùng **list.stream().mapToInt(Integer::intValue).toArray()**.

### 11.2. Boxing thay đổi các terminal operation có sẵn

~~~java
OptionalInt primitiveMax = IntStream.of(3, 8, 5).max();

Optional<Integer> boxedMax = IntStream.of(3, 8, 5)
        .boxed()
        .max(Integer::compareTo);
~~~

Với primitive stream, **max()** trả **OptionalInt** (tương tự OptionalLong/OptionalDouble). Với Stream<Integer>, **max** nhận comparator và trả **Optional<Integer>**. Khi không cần object, phiên bản primitive ngắn hơn và tránh bước wrapper.

Nếu nguồn là **Stream<Integer>**, muốn sum hãy viết:

~~~java
int sum = IntStream.of(1, 2, 3)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();
~~~

**Stream<Integer> không có phương thức sum()**; đó là phép toán chuyên biệt của primitive stream.

### 11.3. Không nhầm Stream với collection đã materialize

Một câu lệnh như **IntStream.range(1, 5).boxed()** chưa tạo List. Bản thân Stream cũng không phải nơi lưu trữ phần tử để truy cập ngẫu nhiên theo chỉ số. Nếu cần dùng lại toàn bộ giá trị, hãy thu thập thành dữ liệu vật hóa (List/mảng) và mở stream mới từ dữ liệu đó khi cần.

## 12. Null, autoboxing và wrapper identity

**boxed()** của IntStream/LongStream/DoubleStream chuyển giá trị nguyên thủy sang wrapper tương ứng. Vì primitive không có null, luồng được boxed từ các primitive hợp lệ **không tạo null**.

**mapToObj()** có thể trả null nếu mapper được viết như vậy:

~~~java
List<String> kept = IntStream.of(-1, 0, 1)
        .mapToObj(n -> n < 0 ? null : "N" + n)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
// [N0, N1]
~~~

Đây là ví dụ có chủ ý. Khi thiết kế ứng dụng, thường nên tránh tạo null nếu có thể biểu diễn trực tiếp bằng **filter** hoặc một giá trị có ý nghĩa; nếu mapper có thể trả null, mọi bước downstream phải xử lý khả năng đó.

**Unboxing null gây NullPointerException**:

~~~java
List<Integer> input = Arrays.asList(1, null, 3);

// Sẽ ném NullPointerException khi gặp null:
int sum = input.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Nếu dữ liệu cho phép null, hãy chọn một quy tắc rõ ràng trước khi unbox:

~~~java
int sum = input.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
~~~

**Integer/Long/Double là đối tượng, không phải primitive.** Với wrapper, toán tử **==** trên hai tham chiếu có thể so sánh danh tính đối tượng, không phải giá trị. Muốn so sánh ý nghĩa số, dùng phép so sánh giá trị phù hợp hoặc **equals(...)** khi cả hai đối tượng không null. Không dựa vào việc **Integer.valueOf** có cache một số giá trị để suy ra kết quả == cho mọi số.

Về hiệu suất, một lần boxing **không nhất thiết luôn cấp phát đối tượng mới**: wrapper có thể được cache, JIT có thể tối ưu một số trường hợp. Tuy vậy, khi mã cần lưu một lượng lớn wrapper trong List/Map/mảng đối tượng, chi phí bộ nhớ và truy cập vẫn phải được cân nhắc.

## 13. Encounter order, parallelStream và tính thuần của mapper

Với nguồn có encounter order như **IntStream.range**, **IntStream.of**, **LongStream.of**, **DoubleStream.of**, **boxed()** và **mapToObj()** là các bước biến đổi theo từng phần tử; chúng không tự sắp xếp lại các phần tử.

~~~java
List<String> labels = IntStream.rangeClosed(1, 4)
        .parallel()
        .mapToObj(n -> "ID-" + n)
        .collect(Collectors.toList());
// [ID-1, ID-2, ID-3, ID-4]
~~~

Với ordered stream và collector phù hợp, thứ tự phần tử trong List được giữ trong kết quả. Nhưng thứ tự **thực thi lambda** trên các thread có thể khác. Không dùng biến đếm chung, in log hay ghi vào List ngoài pipeline để suy ra "phần tử nào chạy trước" trong parallel mode.

Hàm mapper nên:

- **Non-interfering**: không sửa nguồn dữ liệu đang được stream duyệt.
- **Stateless**: kết quả không phụ thuộc vào trạng thái mutable thay đổi trong lúc chạy.
- **Đơn giản và xác định**: cùng đầu vào nên cho cùng ý nghĩa đầu ra; xử lý exception/null có chủ đích.

Ví dụ sai khi dùng trạng thái dùng chung:

~~~java
List<String> shared = new ArrayList<>();

IntStream.rangeClosed(1, 100)
        .parallel()
        .mapToObj(n -> {
            String text = "ID-" + n;
            shared.add(text); // Sai: ghi vào ArrayList dùng chung
            return text;
        })
        .collect(Collectors.toList());
~~~

Đoạn này là **phản ví dụ cố ý**, có nguy cơ data race và hỏng kết quả; mapper nên trả String và để collector tạo List, không thao tác với shared mutable state.

Ngoài ra, **không được dựa vào số lần mapper được gọi** chỉ để tạo side effect. Stream có lazy evaluation, một số terminal operation có thể kết thúc sớm hoặc được tối ưu dựa trên thông tin của nguồn. Nếu muốn thực hiện một công việc có hiệu ứng bên ngoài, cần thiết kế tách riêng khỏi việc dùng mapToObj để biến đổi dữ liệu.

## 14. Boxing, chi phí cấp phát và cách tối ưu có ý nghĩa

Primitive stream thường có lợi khi thao tác chủ yếu với số vì không đòi hỏi wrapper **Integer/Long/Double** cho từng giá trị trung gian. Khi chuyển sang Stream<T> bằng **boxed()**, chương trình mở ra khả năng dùng generic collector và object API, nhưng cũng có thể phát sinh:

- Boxing/unboxing bổ sung khi đi qua các hàm dùng wrapper rồi quay lại primitive.
- Chi phí lưu đối tượng/metadata nếu vật hóa thành List<Integer> hoặc Integer[] lớn.
- Chi phí bộ nhớ, cache locality và thu gom rác khác với int[]/long[]/double[].
- Chi phí cấp phát nếu mapToObj tự tạo String, DTO hoặc đối tượng khác cho từng phần tử.

**Không kết luận rằng mapToObj luôn nhanh hơn boxed().map(...) trong mọi tình huống.** Lựa chọn mapToObj trực tiếp tránh nhu cầu tạo *một bước wrapper trung gian rõ ràng* theo thiết kế API, nhưng JVM có thể tối ưu nhiều đối tượng tạm; hiệu năng thật còn phụ thuộc mapper, dữ liệu, JIT, collector và số lượng phần tử.

Hai pipeline cùng mục tiêu tạo String:

~~~java
List<String> direct = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "N" + n)
        .collect(Collectors.toList());

List<String> indirect = IntStream.rangeClosed(1, 3)
        .boxed()
        .map(n -> "N" + n)
        .collect(Collectors.toList());
~~~

Chúng cho cùng nội dung **[N1, N2, N3]**; **direct** diễn đạt trực tiếp việc chuyển int thành String. Khi hiệu năng quan trọng, đo bằng công cụ benchmark đáng tin (ví dụ JMH) với dữ liệu thực tế, chứ không suy ra chỉ từ một đoạn code ngắn.

Nếu mục tiêu chỉ là tổng, min/max hoặc average trên số, giữ primitive stream đến cuối. Nếu mục tiêu cần danh sách wrapper, khóa nhóm hay DTO, boxing hoặc mapToObj là cần thiết và hợp lý.

## 15. Những sai lầm phổ biến

### 15.1. Gọi mapToObj rồi vẫn dùng sum() của primitive stream

~~~java
// Sai kiểu: sau mapToObj đã là Stream<String>.
// IntStream.of(1, 2, 3).mapToObj(String::valueOf).sum();
~~~

Muốn sum, thực hiện trên IntStream trước. Muốn đếm String, object Stream có **count()**.

### 15.2. Đòi kết quả Integer[] từ toArray() không tham số

~~~java
// Sai kiểu biên dịch:
// Integer[] numbers = IntStream.of(1, 2).boxed().toArray();
~~~

Đúng là **toArray(Integer[]::new)**. Phiên bản không tham số của Stream<T>.toArray() có kiểu **Object[]**.

### 15.3. Nhầm Stream.of(int[]) với Arrays.stream(int[])

~~~java
int[] values = {10, 20, 30};

long groups = Stream.of(values).count();       // 1
long numbers = Arrays.stream(values).count();  // 3
~~~

**Stream.of(values)** ở đây tạo **Stream<int[]>** với một phần tử là cả mảng. **Arrays.stream(values)** tạo **IntStream** lần lượt có ba giá trị 10, 20, 30. Nếu cần List<Integer> từ int[], dùng **Arrays.stream(values).boxed().collect(Collectors.toList())**.

### 15.4. Mong boxed() tự tạo kiểu DTO

**boxed()** chỉ chuyển sang **Integer/Long/Double** tương ứng. Muốn String, ngày, DTO hoặc record, hãy dùng **mapToObj** với mapper phù hợp.

### 15.5. Tạo wrapper chỉ để tính toán số

~~~java
// Hợp lệ nhưng có bước boxing không cần thiết:
int sum = IntStream.rangeClosed(1, 100)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();

// Phù hợp hơn khi chỉ cần tổng:
int directSum = IntStream.rangeClosed(1, 100).sum();
~~~

### 15.6. Thay đổi dữ liệu nguồn hoặc dùng biến mutable trong mapper

Không sửa collection nguồn trong mapToObj; không thêm phần tử vào List dùng chung giữa các thread. Đặt việc thu thập vào **collect** và giữ mapper thuần.

### 15.7. Không quản lý đúng số phần tử khi vật hóa

**rangeClosed(1, 3)** có ba giá trị: 1, 2, 3; **range(1, 3)** chỉ có 1, 2 vì cận trên loại trừ. Boxing không làm thay đổi việc này, và mapToObj mặc định tạo một giá trị kết quả cho mỗi phần tử nguồn. Nếu nguồn vô hạn, không gọi collect(toList()) mà không có giới hạn hữu hiệu.

## 16. Luyện tập có đáp án

### Bài 1 — Chọn boxed hay mapToObj?

Yêu cầu: từ **IntStream.of(2, 4, 6)** tạo **List<Integer>** để truyền cho API nhận List.

~~~java
List<Integer> values = IntStream.of(2, 4, 6)
        .boxed()
        .collect(Collectors.toList());
// [2, 4, 6]
~~~

**Lý do:** chỉ cần wrapper của cùng giá trị số; **boxed()** diễn đạt đúng ý định.

### Bài 2 — Chuyển chỉ số thành nhãn

Yêu cầu: từ các số 0, 1, 2 tạo **List<String>** lần lượt là **item-0**, **item-1**, **item-2**.

~~~java
List<String> items = IntStream.range(0, 3)
        .mapToObj(i -> "item-" + i)
        .collect(Collectors.toList());
// [item-0, item-1, item-2]
~~~

**Lý do:** mỗi int được ánh xạ thành String mới, không cần Integer trung gian.

### Bài 3 — Tạo Set<Integer> không trùng

~~~java
Set<Integer> unique = IntStream.of(3, 1, 3, 2)
        .boxed()
        .collect(Collectors.toSet());
~~~

**Đáp án:** tập hợp chứa đúng các giá trị 1, 2, 3; **không giả định thứ tự duyệt** Set.

### Bài 4 — Tại sao không dùng boxed để tạo String[]?

Yêu cầu kết quả là String[] chứa các mã **N1, N2, N3**.

~~~java
String[] labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "N" + n)
        .toArray(String[]::new);
~~~

**Giải thích:** boxed() chỉ tạo Stream<Integer>. mapToObj tạo Stream<String> tương ứng; overload toArray có generator tạo mảng kiểu String[].

### Bài 5 — Nguồn có thể chứa null sau bước nào?

- **IntStream.of(1, 2).boxed()**: không sinh null từ các giá trị primitive.
- **IntStream.of(1, 2).mapToObj(n -> n == 1 ? null : "N2")**: có thể có null.
- Nếu gọi phương thức instance trên kết quả null, dễ gặp NullPointerException. Muốn loại null, dùng **filter(Objects::nonNull)** trước downstream xử lý không chấp nhận null.

### Bài 6 — Giữ thao tác số ở primitive stream

Yêu cầu: bình phương các số từ 1 đến 4 rồi lấy tổng.

~~~java
int sumSquares = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .sum(); // 30
~~~

**Đáp án:** không cần boxed hay mapToObj vì không chuyển sang object.

## 17. Ghi nhớ

1. **IntStream/LongStream/DoubleStream.boxed()** trả tương ứng **Stream<Integer>/Stream<Long>/Stream<Double>**; bản thân boxed() chưa tạo collection.
2. **mapToObj(mapper)** trả **Stream<U>** do mapper quyết định: có thể là String, DTO, LocalDate hoặc wrapper; mapper nhận trực tiếp primitive tương ứng.
3. **map** trên primitive stream giữ primitive; **mapToObj** chuyển sang object; **mapToInt/mapToLong/mapToDouble** là chiều từ object stream về primitive stream.
4. Nếu chỉ làm toán số, giữ primitive đến cuối. Nếu cần Collectors, generic List hoặc kiểu object cụ thể, dùng boxed hoặc mapToObj đúng ý định.
5. **toArray() trên primitive stream** tạo mảng nguyên thủy; **toArray() trên Stream<T>** trả Object[] nếu không truyền generator. Dùng **Integer[]::new**, **String[]::new** khi cần mảng có kiểu.
6. **boxed** không tạo null từ primitive, còn **mapToObj** có thể tạo null. Unboxing wrapper null gây NullPointerException.
7. Mapper nên thuần và không sửa nguồn; parallel stream không bảo đảm thứ tự thực thi lambda. Không dùng cache wrapper hay phép so sánh tham chiếu để suy luận giá trị số.
8. Khi so sánh hiệu suất, cân nhắc chi phí boxing, cấu trúc kết quả cần lưu và đo đạc thực tế.

### Tài liệu Java chính thức còn áp dụng

- **IntStream**: boxed, mapToObj, map, toArray, sum và primitive terminal operations — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html
- **LongStream**: boxed, mapToObj với LongFunction — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/LongStream.html
- **DoubleStream**: boxed, mapToObj với DoubleFunction — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/DoubleStream.html
- **Stream**: map, mapToInt, collect, typed toArray và toList — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **Package java.util.stream**: intermediate operation, laziness, stateless/non-interfering behavior và parallelism — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html

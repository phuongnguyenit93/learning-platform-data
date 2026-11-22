# Collector.of và tạo bộ thu thập tùy biến trong Java Stream

**Chủ đề:** Java 8 → Collector tùy biến → Collector.of và tạo bộ thu thập.

Khi dùng Stream, nhiều nhu cầu có thể giải quyết ngay bằng **Collectors.toList()**, **groupingBy()**, **joining()**, **counting()** hoặc **summarizingInt()**. Nhưng đôi khi kết quả cần một cấu trúc riêng, quy tắc cộng dồn đặc thù, kiểm tra lỗi trong lúc thu thập, hoặc bước chuyển từ trạng thái tích lũy sang kết quả bất biến. **Collector.of(...)** cho phép định nghĩa một **Collector** bằng các hàm có trách nhiệm rõ ràng, rồi dùng với **Stream.collect(collector)**.

Đây là API được giới thiệu từ Java 8 và vẫn áp dụng với Java hiện đại. Bài sử dụng Java 17+ cho ví dụ chạy độc lập; những cú pháp mới hơn như **List.of(...)** (Java 9+) và **record** (Java 16+) được phân biệt với API Collector.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Collector<T, A, R>** và vai trò của ba kiểu **T**, **A**, **R**.
2. Tạo collector với **Collector.of(supplier, accumulator, combiner)** hoặc overload có thêm **finisher**.
3. Hiểu vì sao **combiner** phải đúng ngay cả khi code thường chạy tuần tự.
4. Phân biệt **IDENTITY_FINISH**, **UNORDERED** và **CONCURRENT**; chỉ khai báo characteristic khi thực sự đáp ứng hợp đồng.
5. Viết collector có kết quả bất biến, kiểm soát nguồn rỗng và có thể dùng làm downstream của **groupingBy(...)**.
6. Kiểm tra tính đúng đắn ở chế độ tuần tự, song song và khi tập dữ liệu được chia thành nhiều phần.

**Phạm vi:** Bài tập trung vào **collector tự tạo và hợp đồng của Collector**. Những kỹ thuật gom nhóm, reduction và xử lý kiểu số chỉ xuất hiện nơi cần để giải thích cách tạo collector, không biến bài thành hướng dẫn chung về toàn bộ Stream API.

## 2. Collector<T, A, R> là gì?

**Collector<T, A, R>** mô tả cách thực hiện một phép **mutable reduction**: tạo ra một vùng chứa trung gian, đưa từng phần tử nguồn vào vùng chứa đó, kết hợp các vùng chứa khi thực thi song song, rồi tùy chọn chuyển sang kiểu kết quả cuối cùng.

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| **T** | Kiểu một phần tử đầu vào của Stream | **String**, **Order**, **Product** |
| **A** | Kiểu trạng thái tích lũy trung gian, thường mutable | **ArrayList<String>**, **StringJoiner**, **OrderBuffer** |
| **R** | Kiểu kết quả cuối cùng trả cho **collect(...)** | **List<String>**, **String**, **OrderReport** |

Ví dụ: **Collector<String, StringJoiner, String>** nhận từng **String** đầu vào (**T**), tích lũy bằng **StringJoiner** (**A**) và trả về một **String** (**R**). Một collector khác có thể dùng **ArrayList<String>** làm cả A lẫn R.

Mô hình ý niệm:

~~~text
Stream<T>
   │
   ├─ supplier()       ─→ tạo A mới
   ├─ accumulator(A,T) ─→ cập nhật A cho từng phần tử
   ├─ combiner(A,A)    ─→ gộp các A từng phần (nếu cần)
   └─ finisher(A)      ─→ R cuối cùng

Stream<T>.collect(Collector<T,A,R>) ─→ R
~~~

Trong luồng tuần tự, quá trình thu thập có thể tương đương với:

~~~java
A state = supplier.get();
for (T item : source) {
    accumulator.accept(state, item);
}
R result = finisher.apply(state);
~~~

Đây là **mã giả dùng kiểu generic**, không phải chương trình có thể biên dịch độc lập. Stream API có quyền chia dữ liệu và phối hợp các kết quả trung gian khác với vòng lặp trên. Vì vậy, collector phải được thiết kế cho cả **supplier**, **accumulator**, **combiner** và **finisher**, kể cả khi thường dùng stream tuần tự.

Một **Collector** là **mô tả cách thu thập**. Nó không đồng nghĩa với một vùng chứa đang có sẵn dữ liệu. Mỗi lượt gọi **collect(...)** phải tạo các vùng chứa theo yêu cầu bằng **supplier**.

## 3. Hai overload của Collector.of(...)

Java cung cấp hai factory method chính:

~~~java
// Khi A và R cùng một kiểu:
static <T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);

// Khi A và R có thể khác kiểu:
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
~~~

Đây là **chữ ký API được trình bày để đọc**, không phải hai phương thức cần tự khai báo trong lớp ứng dụng.

**Overload ba hàm:** Kết quả trung gian chính là kết quả cuối (**A = R**). Overload này tự gắn **Collector.Characteristics.IDENTITY_FINISH**. Ví dụ: một collector gom các phần tử vào **ArrayList** và trả lại chính ArrayList đó.

**Overload bốn hàm:** Có thêm **finisher** chuyển **A → R**, ví dụ **StringJoiner → String** hoặc **ArrayList → List bất biến**. Với trường hợp này, **không** tự khai báo **IDENTITY_FINISH** khi finisher có biến đổi thực sự.

Đối số **characteristics...** là một varargs tùy chọn, nghĩa là có thể không truyền gì. Để học đúng cơ chế, các ví dụ chính trong bài **không khai báo UNORDERED hay CONCURRENT**: chúng có quy tắc thứ tự rõ ràng và accumulator dùng trạng thái mutable không hỗ trợ truy cập đồng thời vào cùng container.

### Bốn thành phần và trách nhiệm

| Thành phần | Kiểu hàm | Trách nhiệm |
|---|---|---|
| **supplier** | **Supplier<A>** | Tạo **container mới, độc lập** cho mỗi lần được gọi |
| **accumulator** | **BiConsumer<A,T>** | Thêm một phần tử T vào container A bằng cách cập nhật trạng thái |
| **combiner** | **BinaryOperator<A>** | Gộp hai container trung gian thành một A và **trả container kết quả** |
| **finisher** | **Function<A,R>** | Chuyển trạng thái cuối A sang kết quả R |
| **characteristics** | Tập thuộc tính | Công bố các bảo đảm mà collector thực sự thỏa mãn |

**Lưu ý về kiểu trả về:** **accumulator** là **BiConsumer** nên không trả gì; **combiner** là **BinaryOperator** nên **bắt buộc trả một A**. Phương thức **add(...)** của ArrayList trả **boolean**, nhưng method reference **ArrayList::add** có thể dùng làm **BiConsumer** vì kết quả đó được bỏ qua theo ngữ cảnh void.

## 4. Ví dụ 1 — Collector.of có finisher để ghép chuỗi

Yêu cầu: ghép danh sách tên thành chuỗi theo encounter order, phân tách bằng **" | "**, trả về **String**. Ta dùng **StringJoiner** để quản lý dấu phân cách. Collector này **giữ thứ tự phần tử của stream có encounter order**, ví dụ nguồn **List**.

Lưu thành **JoinNamesCollectorDemo.java**:

~~~java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class JoinNamesCollectorDemo {
    static Collector<String, StringJoiner, String> joinNames() {
        return Collector.of(
                () -> new StringJoiner(" | "),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
        );
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        String sequential = names.stream().collect(joinNames());
        String parallel = names.parallelStream().collect(joinNames());
        String empty = Stream.<String>empty().collect(joinNames());

        System.out.println("seq=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty='" + empty + "'");

        System.out.println("identityFinish="
                + joinNames().characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 JoinNamesCollectorDemo.java
java JoinNamesCollectorDemo
~~~

**Stdout:**

~~~text
seq=An | Binh | Chi
parallel=An | Binh | Chi
empty=''
identityFinish=false
~~~

**Phân tích từng hàm:**

1. **supplier:** Mỗi khi cần một bộ chứa, **new StringJoiner(" | ")** tạo vùng chứa mới, rỗng.
2. **accumulator:** **StringJoiner::add** thêm một tên vào bộ chứa; StringJoiner quản lý dấu phân cách để không tạo ký tự thừa ở đầu/cuối.
3. **combiner:** **StringJoiner::merge** ghép hai bộ chứa và trả về bộ chứa sau khi gộp. Khi nguồn có thứ tự, collector không khai báo **UNORDERED**, vì vậy kết quả thu thập cần giữ thứ tự nguồn.
4. **finisher:** **StringJoiner::toString** tạo **String** cuối cùng. Vì A là StringJoiner còn R là String, đây **không** phải identity finish.
5. **nguồn rỗng:** supplier tạo StringJoiner rỗng; finisher trả chuỗi rỗng. Không có lỗi chỉ vì Stream không chứa phần tử.

**Vì sao không viết StringBuilder cho mọi trường hợp?** Có thể viết, nhưng cần tự giải quyết dấu phân cách khi gộp hai phần. **StringJoiner** có **merge(...)**, nên giảm lỗi dấu phân cách trong parallel collection.

Trong ứng dụng thông thường, chính nhu cầu này đã có **Collectors.joining(" | ")**. Ví dụ ở đây nhằm giải thích cơ chế tạo collector; không nên tự viết collector nếu API chuẩn đã thể hiện đầy đủ ý định.

### Suy nghĩ về combiner

Nếu việc chia dữ liệu tạo hai vùng chứa:

~~~text
A1 = "An | Binh"
A2 = "Chi"

combiner(A1,A2) → "An | Binh | Chi"
~~~

Nếu **combiner** chỉ trả A1 và bỏ A2, kết quả tuần tự có thể đúng tình cờ, nhưng kết quả song song sẽ mất phần tử. Nếu ghép theo thứ tự ngược, thứ tự đầu ra cũng sai đối với stream có thứ tự.

Không giả định **combiner chỉ là một tham số kỹ thuật ít quan trọng**: nó là một phần của tính đúng đắn.

## 5. Ví dụ 2 — Collector.of ba hàm và IDENTITY_FINISH

Khi trạng thái thu thập chính là đối tượng được trả về, dùng overload ba hàm. Ví dụ tạo một **ArrayList<String>** mới:

Lưu thành **ListCollectorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class ListCollectorDemo {
    static Collector<String, ArrayList<String>, ArrayList<String>>
            mutableCollector() {
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
            immutableCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf
        );
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        Collector<String, ArrayList<String>, ArrayList<String>> mutable =
                mutableCollector();
        Collector<String, ArrayList<String>, List<String>> immutable =
                immutableCollector();

        ArrayList<String> editable = names.stream().collect(mutable);
        List<String> readOnly = names.stream().collect(immutable);

        System.out.println("mutable=" + editable);
        System.out.println("identity="
                + mutable.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("immutable=" + readOnly);
        System.out.println("immutableIdentity="
                + immutable.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListCollectorDemo.java
java ListCollectorDemo
~~~

**Stdout:**

~~~text
mutable=[An, Binh, Chi]
identity=true
immutable=[An, Binh, Chi]
immutableIdentity=false
~~~

**Phân biệt hai kết quả:**

- **mutableCollector():** supplier tạo ArrayList mới; accumulator thêm phần tử; combiner **left.addAll(right); return left;**. Vì không có finisher tách biệt nên **A = R = ArrayList<String>** và **IDENTITY_FINISH=true**.
- **immutableCollector():** vẫn tích lũy trong ArrayList, nhưng finisher **List.copyOf** tạo một danh sách **không cho phép sửa**. Vì A khác R về hợp đồng kết quả, **IDENTITY_FINISH=false**.
- **List.copyOf** không chấp nhận phần tử **null**; ví dụ dùng **List.of** nên không có null. Với đầu vào có null phải xác định chính sách rõ ràng.
- Kết quả bất biến thích hợp khi muốn công bố dữ liệu sau khi thu thập mà không để người gọi vô tình chỉnh sửa trạng thái.

Đây là ví dụ giáo khoa. Đối với nhu cầu thông thường, dùng **Collectors.toCollection(ArrayList::new)** nếu cần ArrayList cụ thể có thể sửa, **Collectors.toUnmodifiableList()** nếu muốn list không cho phép sửa, hoặc **Stream.toList()** (Java 16+) nếu cần list không cho phép sửa và không yêu cầu loại triển khai cụ thể. **Collectors.toList()** không cam kết loại List hoặc khả năng sửa; đừng dựa vào một implementation tình cờ.

**Không tự đặt IDENTITY_FINISH cho overload có List::copyOf:** nếu runtime được quyền bỏ qua finisher, kết quả có thể sai loại hoặc sai đặc tính bất biến. Tính chất này chỉ hợp lệ khi kết quả có thể dùng trực tiếp trạng thái tích lũy với phép cast A sang R an toàn.

## 6. Ví dụ 3 — Collector thật sự cần tùy biến: báo cáo bất biến có kiểm tra tràn

Một hệ thống cần thống kê **số đơn, tổng tiền theo cent, giá trị đơn nhỏ nhất/lớn nhất**. Vì tổng tiền phải được kiểm tra **tràn số** tại từng phép tính, và min/max của tập rỗng phải được biểu diễn tường minh, ta tạo một collector riêng:

- **T:** **Order** — đơn hàng đầu vào.
- **A:** **OrderBuffer** — trạng thái mutable gồm count, tổng, min, max.
- **R:** **OrderReport** — record kết quả bất biến; min/max được biểu diễn bằng **OptionalLong** để phân biệt dữ liệu rỗng.

Đây là tình huống có lý do tạo collector thay vì chỉ sao chép hành vi **summarizingLong(...)**: ta muốn kiểm tra **Math.multiplyExact/Math.addExact**, định nghĩa kết quả công bố và thống kê nhiều chỉ số gắn với **giá trị tính từ một đơn hàng**.

Lưu mã đầy đủ thành **OrderReportCollectorDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.OptionalLong;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class OrderReportCollectorDemo {
    record Order(String category, long unitPriceCents, int quantity) {}

    record OrderReport(
            long count,
            long totalCents,
            OptionalLong minOrderCents,
            OptionalLong maxOrderCents) {}

    static final class OrderBuffer {
        long count;
        long totalCents;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;

        void add(Order order) {
            long value = Math.multiplyExact(
                    order.unitPriceCents(), (long) order.quantity());

            count = Math.addExact(count, 1L);
            totalCents = Math.addExact(totalCents, value);
            min = Math.min(min, value);
            max = Math.max(max, value);
        }

        OrderBuffer merge(OrderBuffer other) {
            count = Math.addExact(count, other.count);
            totalCents = Math.addExact(totalCents, other.totalCents);

            if (other.count > 0) {
                min = Math.min(min, other.min);
                max = Math.max(max, other.max);
            }
            return this;
        }

        OrderReport finish() {
            return new OrderReport(
                    count,
                    totalCents,
                    count == 0 ? OptionalLong.empty() : OptionalLong.of(min),
                    count == 0 ? OptionalLong.empty() : OptionalLong.of(max)
            );
        }
    }

    static Collector<Order, OrderBuffer, OrderReport> reportCollector() {
        return Collector.of(
                OrderBuffer::new,
                OrderBuffer::add,
                OrderBuffer::merge,
                OrderBuffer::finish
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("books", 1500, 2),
                new Order("books", 800, 1),
                new Order("tools", 2000, 3)
        );

        OrderReport all = orders.stream().collect(reportCollector());
        OrderReport parallel =
                orders.parallelStream().collect(reportCollector());

        System.out.println("all count=" + all.count()
                + ", total=" + all.totalCents()
                + ", min=" + all.minOrderCents().orElseThrow()
                + ", max=" + all.maxOrderCents().orElseThrow());

        System.out.println("parallel equals=" + all.equals(parallel));

        Map<String, OrderReport> byCategory = orders.stream().collect(
                Collectors.groupingBy(
                        Order::category,
                        reportCollector()
                )
        );

        System.out.println("books total="
                + byCategory.get("books").totalCents());
        System.out.println("tools total="
                + byCategory.get("tools").totalCents());

        OrderReport empty =
                Stream.<Order>empty().collect(reportCollector());

        System.out.println("empty count=" + empty.count()
                + ", minPresent=" + empty.minOrderCents().isPresent());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderReportCollectorDemo.java
java OrderReportCollectorDemo
~~~

**Stdout:**

~~~text
all count=3, total=9800, min=800, max=6000
parallel equals=true
books total=3800
tools total=6000
empty count=0, minPresent=false
~~~

### 6.1. Giải thích cách tính

Có ba đơn hàng:

| Nhóm | Đơn giá cent | Số lượng | Thành tiền cent |
|---|---:|---:|---:|
| books | 1500 | 2 | 3000 |
| books | 800 | 1 | 800 |
| tools | 2000 | 3 | 6000 |

Tổng là **9800 cent**, nhỏ nhất **800 cent**, lớn nhất **6000 cent**, và có **3 đơn**. **Map<String, OrderReport>** sau **groupingBy** chứa thống kê của từng nhóm; không giả định thứ tự duyệt các khóa trong Map.

**OrderBuffer.add(...)** tính thành tiền trước, sau đó cập nhật count, total, min, max. Với giá trị vượt phạm vi **long**, **Math.multiplyExact** hoặc **Math.addExact** ném **ArithmeticException**; ứng dụng cần xử lý lỗi dữ liệu phù hợp. **Math.addExact** phát hiện tràn ở phép cộng trung gian, nên có thể ném dù một tổng toán học cuối cùng (sau các số bù trừ) nằm trong phạm vi — đó là chính sách kiểm tra phép toán từng bước, không phải số học chính xác không giới hạn.

**OrderBuffer.merge(other)** kết hợp hai báo cáo trung gian. Nếu **other** rỗng, min/max hiện tại không bị thay đổi. Nếu bản thân **left** rỗng, giá trị khởi tạo **Long.MAX_VALUE**/**Long.MIN_VALUE** vẫn kết hợp đúng với min/max thực từ **other**. Sau phép merge, trả về chính **left**.

**OrderBuffer.finish()** tạo **record** và OptionalLong độc lập với buffer. Đối với nguồn rỗng: count/tổng là 0 và min/max là **OptionalLong.empty()**; không diễn giải sentinel kỹ thuật thành một giá trị kinh doanh.

Mã ví dụ không định nghĩa các quy tắc nghiệp vụ như cấm giá/số lượng âm. Trong hệ thống thực tế, cần kiểm tra đầu vào, đơn vị tiền tệ, giới hạn số tiền và chính sách hoàn tiền trước khi tính.

### 6.2. Vì sao kết quả có thể dùng trong groupingBy?

**reportCollector()** trả một **Collector<Order, OrderBuffer, OrderReport>**, nên có thể truyền làm downstream:

~~~java
// Đoạn minh họa, giả sử Order và reportCollector() đã khai báo.
Map<String, OrderReport> grouped = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                reportCollector()
        ));
~~~

Mỗi nhóm sẽ có trạng thái tích lũy riêng và được hoàn thiện thành một **OrderReport**. Cách này tận dụng khả năng **kết hợp Collector**, không phải tự viết một **Map<String, OrderBuffer>** dùng chung ngoài stream.

**Điều kiện quan trọng:** hàm phân nhóm cần trả về khóa hợp lệ (với groupingBy thông thường không nên là null), và buffer không bị chia sẻ qua biến static hoặc một biến mutable bên ngoài.

## 7. Các luật cần thỏa để Collector.of đúng

Một collector hợp lệ phải tuân thủ **identity** và **associativity/compatibility** theo đặc tả **Collector**. Việc "chạy đúng trên một danh sách nhỏ ở chế độ tuần tự" chưa đủ.

### 7.1. Luật identity — gộp với trạng thái rỗng không làm đổi kết quả

Gọi **supplier.get()** để tạo một container rỗng mới. Với bất kỳ trạng thái tích lũy hợp lệ **a**, việc kết hợp **a** với container rỗng phải cho kết quả **tương đương** a:

~~~text
combiner(a, supplier()) ≃ a
~~~

Dấu **≃** biểu thị **tương đương về kết quả**, không đòi hai biến tham chiếu cùng một đối tượng Java. Nếu collector giữ thứ tự, kết quả cuối phải giữ cùng các phần tử theo thứ tự; nếu collector thật sự **UNORDERED**, tiêu chí tương đương có thể không xét thứ tự.

Ví dụ đúng cho list:

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

Với **right** rỗng, **left** không đổi về nội dung.

### 7.2. Luật kết hợp — chia rồi gộp phải tương đương gom liền

Ví dụ với dãy phần tử **[A, B, C]**, hai cách phải cho kết quả tương đương:

~~~text
gom tất cả:                  accumulate(A,B,C)
chia thành [A,B] và [C]:     combine(accumulate(A,B), accumulate(C))
chia thành [A] và [B,C]:     combine(accumulate(A), accumulate(B,C))
~~~

Khi thứ tự đầu vào có nghĩa, **combiner** không được tự đảo nhóm hoặc làm mất phần tử.

Đặc tả Collector trình bày luật này theo kết quả sau **finisher**, vì trạng thái trung gian A có thể khác đối tượng cuối R. Trên stream song song, việc chia thành phần nhỏ và gộp cây có thể thay đổi; collector không được chỉ đúng khi combiner được gọi theo một thứ tự tình cờ.

**Ví dụ lỗi:**

~~~java
// SAI: làm mất toàn bộ dữ liệu trong right.
(left, right) -> left
~~~

Một lỗi khác là nối nội dung ở thứ tự đảo ngược khi kết quả cần bảo toàn encounter order:

~~~java
// SAI nếu kết quả cần thứ tự input như List:
(left, right) -> {
    right.addAll(left);
    return right;
}
~~~

### 7.3. Accumulator và combiner phải tương thích

**accumulator** nạp từng phần tử nguồn T; **combiner** gộp hai A. Hai hàm phải thể hiện cùng một phép tổng hợp.

Chẳng hạn, nếu accumulator cộng **giá trị thành tiền** nhưng combiner lại cộng **đơn giá** chưa nhân số lượng, chạy tuần tự có thể đúng nhưng chạy song song sẽ sai. Nếu accumulator dùng quy tắc chuẩn hóa chuỗi còn combiner không áp dụng quy tắc đó, các nhánh cho ra kết quả không tương đương.

Với các phép toán **double**, thứ tự cộng làm tròn có thể thay đổi bit kết quả dù ý định toán học là tổng. Nếu ứng dụng đòi tổng decimal chính xác, cần thiết kế miền dữ liệu và thuật toán khác, thay vì khẳng định collector double cho kết quả tuyệt đối chính xác.

### 7.4. Các hàm không phụ thuộc tác dụng phụ bên ngoài

**supplier**, **accumulator**, **combiner** và **finisher** nên tuân thủ hợp đồng Stream: không sửa nguồn đang duyệt, không phụ thuộc vào trạng thái dùng chung bên ngoài và tránh những tác dụng phụ làm kết quả phụ thuộc lịch chạy. **Trạng thái mutable nằm trong A** là bình thường, nhưng **biến mutable global dùng chung** là một rủi ro khác.

Ví dụ không nên làm:

~~~java
// SAI: tất cả lượt tạo container cùng trả về một ArrayList có sẵn.
List<String> shared = new ArrayList<>();
Collector<String, ?, List<String>> broken = Collector.of(
        () -> shared,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

Đây chỉ là **đoạn minh họa lỗi**, cần import **java.util.List/ArrayList** và **java.util.stream.Collector** nếu thử riêng. Supplier như vậy vi phạm yêu cầu tạo **container mới độc lập**. Trong parallel stream, nhiều nhánh có thể ghi chung vào một danh sách không an toàn; thậm chí kết quả có thể bị nhân đôi hoặc thay đổi qua các lần collect.

**Đúng:** dùng **ArrayList::new** hoặc lambda trả về **new ArrayList<>()** trong mỗi lần gọi.

## 8. Characteristics: khai báo đúng hợp đồng

**Collector.Characteristics** có ba giá trị:

| Characteristic | Ý nghĩa | Khi nào phù hợp? |
|---|---|---|
| **IDENTITY_FINISH** | Finisher có thể bị bỏ qua; A có thể dùng trực tiếp làm R với cast hợp lệ | A và R thật sự tương thích, finisher là identity |
| **UNORDERED** | Kết quả không cam kết giữ encounter order | Ví dụ tập hợp mà thứ tự phần tử không có ý nghĩa |
| **CONCURRENT** | Accumulator hỗ trợ nhiều thread cùng cập nhật **cùng một container** an toàn | Chỉ khi container và logic cập nhật thực sự an toàn đồng thời |

### 8.1. IDENTITY_FINISH

Overload **Collector.of(supplier, accumulator, combiner)** tự thêm **IDENTITY_FINISH**. Dùng overload có **finisher biến đổi kết quả** thì không gắn characteristic này.

Nếu khai báo sai **IDENTITY_FINISH** cho một collector có **finisher chuyển ArrayList thành String hoặc danh sách bất biến**, runtime có thể bỏ qua finisher và đưa trạng thái trung gian ra ngoài như kết quả cuối; dẫn tới sai kiểu hoặc sai bảo đảm.

**Không dùng IDENTITY_FINISH để biểu đạt "finisher chạy rất nhanh"**. Nó là hợp đồng về **tính đồng nhất giữa A và R**, không phải mẹo hiệu năng tùy tiện.

### 8.2. UNORDERED

**UNORDERED** có nghĩa là kết quả thu thập **không cam kết** bảo toàn thứ tự gặp phần tử. Nó không có nghĩa "hãy trộn ngẫu nhiên" hay "tự động nhanh hơn".

Nếu cần xuất **"An | Binh | Chi"** theo thứ tự List, không khai báo **UNORDERED**. Nếu đang gom vào một **Set** và thực sự chỉ quan tâm thành viên, một collector phù hợp có thể được thiết kế là unordered. Phải cân nhắc cả kiểu kết quả và ngữ nghĩa nghiệp vụ.

### 8.3. CONCURRENT

**CONCURRENT** cho phép accumulator của collector được gọi đồng thời trên **cùng một container**. **ArrayList**, **StringJoiner** và **OrderBuffer** trong các ví dụ trên **không tự an toàn cho tình huống đó**, nên không được gắn CONCURRENT.

**Parallel stream vẫn có thể dùng collector không CONCURRENT**: hệ thống tạo các container **riêng biệt** cho các nhánh, sau đó gọi combiner để gộp. Đây là cơ chế **parallel reduction bằng phân chia trạng thái**, không phải nhiều thread ghi vào chung một container.

Một concurrent reduction theo hợp đồng Stream có thể xảy ra khi **Stream song song**, collector có **CONCURRENT** và **nguồn unordered hoặc collector UNORDERED**. Ngay cả khi đáp ứng điều kiện, không được dựa vào việc combiner chắc chắn không được gọi; phải cung cấp combiner hợp lệ.

**Khai báo CONCURRENT không tự biến ArrayList thành thread-safe.** Chỉ khai báo sau khi đã chứng minh accumulator và mọi trạng thái dùng chung chịu được cập nhật đồng thời và các bảo đảm về thứ tự phù hợp với yêu cầu.

## 9. Phân biệt Collector.of với các phương án gần giống

### 9.1. Stream.collect(supplier, accumulator, combiner)

Ngoài **Stream.collect(Collector)**, Java còn overload ba hàm trực tiếp:

~~~java
// Đoạn minh họa hoàn chỉnh về biểu thức, với List/ArrayList đã import:
ArrayList<String> values = Stream.of("An", "Binh")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
~~~

Chú ý đây là **Stream.collect(...)**, không phải **Collector.of(...)**:

| Khía cạnh | **Stream.collect(supplier, accumulator, combiner)** | **Collector.of(...)** |
|---|---|---|
| Vị trí sử dụng | Gọi trực tiếp trên một Stream | Tạo đối tượng Collector có thể tái sử dụng |
| Kiểu combiner | **BiConsumer<R,R>** — gộp vào container đích, không trả về | **BinaryOperator<A>** — gộp và **trả A** |
| Finisher | Không truyền finisher riêng | Có overload với **Function<A,R>** |
| Characteristics | Không khai báo trong lời gọi này | Có thể khai báo theo hợp đồng |
| Dùng làm downstream groupingBy | Không thể truyền ba hàm trực tiếp | Có thể truyền **Collector** đã tạo |

**Đừng nhầm chữ ký combiner**: trong **Stream.collect** ba hàm, **ArrayList::addAll** có thể dùng như **BiConsumer**; trong **Collector.of**, cần viết lambda **left.addAll(right); return left;**.

Đoạn minh họa trên dùng **Stream.of(...)** và yêu cầu import **java.util.stream.Stream**, **java.util.ArrayList**.

### 9.2. reduce(...) khác collect(...)

**reduce(...)** thường diễn tả tổng hợp bằng một giá trị theo phép kết hợp; **collect(...)** diễn tả việc cập nhật một **mutable result container**. Không nên truyền một **ArrayList mutable** làm identity cho **reduce(...)** rồi sửa nó trong accumulator, đặc biệt khi chạy song song. Collector cung cấp cơ chế **supplier tạo trạng thái độc lập**, accumulator thêm phần tử và combiner gộp trạng thái.

Nếu chỉ cần cộng số **int** hoặc lấy **max**, các operation chuyên dụng như **sum()**, **max()** hoặc **reduce(...)** có thể rõ ràng hơn. Không tạo Collector.of cho mọi terminal operation theo thói quen.

### 9.3. Ưu tiên Collector có sẵn khi đúng yêu cầu

| Yêu cầu | Thường nên dùng |
|---|---|
| Gom phần tử vào một danh sách | **toList()**, **Collectors.toList()**, **Collectors.toCollection(...)** |
| Gom vào một tập hợp | **Collectors.toSet()**, **Collectors.toCollection(...)** |
| Nối chuỗi có delimiter | **Collectors.joining(delimiter)** |
| Gom theo khóa | **Collectors.groupingBy(...)** |
| Tạo Map từ key/value | **Collectors.toMap(...)** với merge policy nếu khóa trùng |
| Chuyển kết quả của collector có sẵn | **Collectors.collectingAndThen(...)** |
| Tính tổng, đếm, min/max, thống kê cơ bản | Các collector tương ứng trong **Collectors** |
| Tạo trạng thái/qui tắc cộng dồn/finisher riêng | **Collector.of(...)** |

**Ví dụ thay cho custom collector bất biến:**

~~~java
// Đoạn minh họa cần import List, ArrayList và Collectors:
List<String> result = names.stream().collect(
        Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf
        )
);
~~~

Hoặc với Java 17+ khi phù hợp, **names.stream().toList()** đã trả danh sách không cho phép sửa. Việc dùng Collector.of có lợi khi muốn tái sử dụng **logic thu thập mới**, chứ không phải viết lại một API chuẩn sẵn có.

## 10. Cách kiểm thử collector tùy biến

Với collector mới, chỉ test một ví dụ "chạy ra đúng" là chưa đủ. Cần xác minh các trường hợp:

1. **Nguồn rỗng:** supplier và finisher cho kết quả hợp lệ theo quy định bài toán.
2. **Một phần tử:** accumulator nạp đúng giá trị.
3. **Nhiều phần tử có thứ tự:** kết quả đúng encounter order khi cần.
4. **Chia thành hai hoặc ba nhóm:** dùng các buffer khác nhau, gộp lại và so sánh với cách gom liền.
5. **Parallel stream:** kết quả tương đương với tuần tự theo ngữ nghĩa collector, không chỉ một lần chạy tình cờ.
6. **Dữ liệu bất thường:** null, số âm, giới hạn int/long, chuỗi rỗng, khóa nhóm thiếu, tùy hợp đồng nghiệp vụ.
7. **Đặc tính kết quả:** danh sách có được sửa không, kết quả có độc lập với container tích lũy không.
8. **Characteristics:** chỉ công bố những thuộc tính được kiểm chứng.

### Kiểm thử combiner trực tiếp

Có thể gọi các thành phần từ Collector để kiểm tra hợp đồng mà không cần phụ thuộc vào cách runtime phân chia parallel stream:

~~~java
// Đoạn minh họa cần import java.util.StringJoiner,
// java.util.stream.Collector; giả sử joinNames() đã được khai báo.
Collector<String, StringJoiner, String> c = joinNames();

StringJoiner left = c.supplier().get();
StringJoiner right = c.supplier().get();

c.accumulator().accept(left, "An");
c.accumulator().accept(left, "Binh");
c.accumulator().accept(right, "Chi");

StringJoiner combined = c.combiner().apply(left, right);
String result = c.finisher().apply(combined);

// result.equals("An | Binh | Chi") == true
~~~

Hai container được tạo bằng **hai lượt supplier.get() độc lập**, sau đó được gộp. Có thể thêm kiểm thử gộp với container rỗng và gộp ba phần theo các cách nhóm khác nhau.

**Không gọi lại accumulator trên một container đã đưa vào finisher** để suy luận hành vi Stream: theo hợp đồng Collector, sau khi kết quả trung gian được chuyển cho finisher hoặc kết hợp theo cách kết thúc sử dụng, runtime có thể coi trạng thái trước đó không còn được dùng nữa. Ví dụ kiểm tra manual cũng nên tuân thủ lối dùng này.

### Tính tương đương thay vì dựa vào danh tính đối tượng

Có collector trả **A** sau khi sửa chính container **left**; có collector tạo một container **A** mới khi merge. Kiểm thử dựa vào **nội dung kết quả** theo hợp đồng, thay vì khẳng định mọi lần combiner đều trả đúng cùng tham chiếu **left**.

Nếu collector khai báo **UNORDERED**, kiểm thử có thể so sánh tập phần tử và số lần xuất hiện thay cho thứ tự danh sách. Nếu collector giữ thứ tự, so sánh danh sách/chữ ký đã hoàn thiện theo đúng thứ tự nguồn.

## 11. Các lỗi thường gặp khi tự viết Collector

### Lỗi 1 — supplier tái sử dụng một container

~~~java
// Không dùng cùng một instance chia sẻ cho mọi lượt collect.
() -> sharedAccumulator
~~~

Supplier phải tạo container mới, độc lập. Việc dùng một biến **static ArrayList** hoặc một instance dùng chung sẽ gây rò trạng thái giữa các lần collect và có nguy cơ race condition khi parallel.

### Lỗi 2 — combiner bỏ dữ liệu hoặc không trả container

~~~java
// SAI: bỏ qua right
(left, right) -> left
~~~

**Collector.of** đòi **BinaryOperator<A>** trả A. Ngay cả nếu đã thêm tất cả phần tử từ right vào left, cũng cần **return left**; khác với combiner kiểu **BiConsumer** của **Stream.collect(...)**.

### Lỗi 3 — gắn IDENTITY_FINISH sai

~~~java
// Về ý tưởng là SAI: finisher đang chuyển A sang String,
// nên không được khai báo IDENTITY_FINISH.
Collector.of(
    StringBuilder::new,
    (builder, value) -> builder.append(value),
    (left, right) -> left.append(right),
    StringBuilder::toString,
    Collector.Characteristics.IDENTITY_FINISH
);
~~~

Đây là **đoạn minh họa lỗi**, không dùng trong sản phẩm. Finisher có thể bị bỏ qua theo characteristic, làm sai kiểu kết quả. Đối với finisher chuyển kiểu, hãy bỏ **IDENTITY_FINISH**.

### Lỗi 4 — gắn CONCURRENT cho accumulator không thread-safe

~~~java
// SAI nếu A là ArrayList hoặc StringBuilder mutable không bảo vệ:
// Collector.Characteristics.CONCURRENT
~~~

**parallelStream()** với collector bình thường không đòi accumulator tự an toàn để nhiều thread ghi cùng một A; runtime có thể giữ trạng thái từng nhánh riêng. **CONCURRENT** mới là cam kết cho phép ghi đồng thời vào cùng A, nên không được khai báo chỉ với mục đích "bật song song".

### Lỗi 5 — lấy thứ tự làm mục tiêu nhưng khai báo UNORDERED

Nếu muốn nối tên theo đúng thứ tự List, hãy giữ collector **ordered**. **UNORDERED** cho runtime quyền bỏ cam kết về encounter order của kết quả; tính đúng nghiệp vụ cần phù hợp trước khi chọn đặc tính này.

### Lỗi 6 — dùng average của các nhóm như phép gộp

Giả sử nhóm đầu có một giá trị **10**, nhóm thứ hai có chín giá trị **0**. Trung bình toàn bộ là **1**, còn trung bình của hai trung bình nhóm là **5**. Combiner chỉ lấy **(averageLeft + averageRight) / 2** là sai nếu số phần tử hai nhóm khác nhau. Hãy lưu **sum và count** (hoặc trạng thái phù hợp) trong A, rồi tính average ở finisher. Nếu dùng số thực, còn cần xét sai số làm tròn.

### Lỗi 7 — không xử lý nguồn rỗng

Các collector như **min**, **max**, **average**, **tính tỉ lệ** cần quy định khi count bằng 0. **Optional**, kết quả rỗng có cấu trúc, hoặc ngoại lệ nghiệp vụ có ý nghĩa có thể phù hợp hơn một sentinel giả. Ví dụ báo cáo đơn hàng dùng **OptionalLong** cho min/max.

### Lỗi 8 — mapper/accumulator có tác dụng phụ ngoài collector

Không tăng biến toàn cục, gọi API ghi dữ liệu, thay đổi nguồn đang duyệt hoặc ghi chung vào một map mutable trong accumulator chỉ để "tiết kiệm" tạo buffer. Với parallel stream, tần suất và thứ tự gọi không phải là giao kèo dành cho tác dụng phụ bên ngoài.

### Lỗi 9 — giả định collector luôn chạy nhanh hơn vòng lặp

Một collector có thể tăng số lượng đối tượng tạm, chi phí merge và cấp phát vùng nhớ. Quyết định dùng **Collector.of** nên dựa trên **ý nghĩa, khả năng tái sử dụng và tính đúng đắn**. Nếu hiệu năng quan trọng, hãy benchmark với kích thước và loại dữ liệu thực; không giả định parallel sẽ nhanh hơn sequential.

### Lỗi 10 — đánh đồng tính bất biến của kết quả với tính bất biến của A

Dùng **List.copyOf** ở finisher tạo kết quả không cho phép sửa. Nhưng A vẫn là **ArrayList** mutable trong lúc tích lũy. Không công bố hay lưu tham chiếu A ở nơi khác rồi tiếp tục thay đổi; nếu R chứa tham chiếu trực tiếp tới A mutable, phải hiểu đó có thể là một dạng lộ trạng thái dù R có kiểu interface đọc.

## 12. Checklist thiết kế collector trước khi viết

Một cách tiếp cận thực tế:

- **Kết quả R là gì?** Hãy định nghĩa chính xác hình dạng, đơn vị, quy tắc rỗng và khả năng sửa được hay không.
- **Cần tích lũy những gì trong A?** Thường nên có đủ thông tin để merge đúng: sum/count, min/max, danh sách theo thứ tự, v.v.
- **Supplier có luôn tạo A mới?** Không dùng chung biến mutable qua các lần gọi.
- **Accumulator xử lý từng T như thế nào?** Có xác nhận null, giới hạn số và quy tắc dữ liệu không?
- **Combiner hợp nhất hai A như thế nào?** Dữ liệu của cả hai nhánh có được giữ đầy đủ không? Có phụ thuộc thứ tự không?
- **A và R có giống nhau không?** Nếu không, chọn overload có **finisher**.
- **Có bảo đảm characteristic nào?** Mặc định không khai báo thêm là lựa chọn an toàn khi chưa chứng minh.
- **Có collector chuẩn đáp ứng yêu cầu không?** Nếu có, ưu tiên tái sử dụng.
- **Đã so kết quả tuần tự, parallel, rỗng và chia nhóm chưa?** Điều này giúp phát hiện lỗi combiner khó thấy khi chỉ chạy tuần tự.

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong **Collector<String, StringJoiner, String>**, ba kiểu T, A, R là gì?

**Câu 2.** Với collector gom vào **ArrayList** và trả đúng ArrayList đó, nên dùng overload **Collector.of** nào? Characteristic nào được tự thêm?

**Câu 3.** Trong **Collector.of**, combiner có kiểu **BiConsumer<A,A>** hay **BinaryOperator<A>**? Điều đó ảnh hưởng code như thế nào?

**Câu 4.** Một collector nối chuỗi cho kết quả đúng ở chế độ tuần tự nhưng mất một nửa dữ liệu khi chạy song song. Thành phần nào cần kiểm tra trước?

**Câu 5.** Nếu finisher tạo **List.copyOf(accumulator)**, có được khai báo **IDENTITY_FINISH** không?

**Câu 6.** **parallelStream().collect(collector)** có nhất thiết cần collector mang **CONCURRENT** không?

**Câu 7.** Một collector tính trung bình chỉ giữ số trung bình hiện tại, sau đó combiner lấy trung bình của hai kết quả. Vì sao có thể sai?

**Đáp án:**

1. **T = String**, **A = StringJoiner**, **R = String**.
2. Dùng overload **ba hàm**: supplier, accumulator, combiner. Nó tự có **IDENTITY_FINISH**.
3. **BinaryOperator<A>**; phải trả một **A** đã gộp. **BiConsumer** là kiểu combiner của overload **Stream.collect(supplier, accumulator, combiner)**.
4. Kiểm tra **combiner**: có gộp mọi phần tử của nhánh phải vào nhánh trái và trả kết quả đúng không; kiểm tra tiếp luật identity/associativity.
5. **Không.** Finisher chuyển A thành một List không cho phép sửa, cần thực thi bước này.
6. **Không.** Collector bình thường có thể chạy song song bằng các container riêng và combiner; **CONCURRENT** là cam kết hỗ trợ cùng một container được cập nhật đồng thời.
7. Các nhóm có thể có số lượng phần tử khác nhau. Phải lưu ít nhất **sum và count** hoặc trạng thái tương đương để tính trung bình chính xác theo số lượng.

## 14. Ghi nhớ

**Collector.of(...)** cho phép đóng gói cách tạo bộ chứa, nạp phần tử, gộp các kết quả từng phần và hoàn thiện kết quả. Hãy nhìn nó theo bốn trách nhiệm **supplier → accumulator → combiner → finisher**, cùng các luật **identity, associativity và compatibility**.

Dùng overload ba hàm khi **A = R** và kết quả không cần biến đổi; dùng overload có **finisher** khi cần tạo đối tượng khác, chuẩn hóa hoặc khóa kết quả để tránh sửa đổi. Không gắn **IDENTITY_FINISH**, **UNORDERED**, **CONCURRENT** nếu chưa đáp ứng đúng hợp đồng. **Combiner đúng** là yêu cầu bắt buộc ngay cả khi phần lớn lần chạy là tuần tự.

### Tài liệu chính thức

- [Collector<T,A,R> và Collector.of — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html): chữ ký factory, hợp đồng identity/associativity và các ràng buộc thu thập.
- [Collector.Characteristics — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.Characteristics.html): **IDENTITY_FINISH**, **UNORDERED**, **CONCURRENT**.
- [Stream.collect — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): hai overload **collect(...)** và cách thực hiện mutable reduction.
- [Collectors — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): **toCollection**, **groupingBy**, **collectingAndThen** và các collector có sẵn.

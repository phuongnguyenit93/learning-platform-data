# Dùng breakpoint và peek để quan sát với giới hạn tối ưu hóa

Trong chương **Gỡ lỗi và kiểm thử pipeline** của **Java Stream API**, một khó khăn rất thường gặp là đoạn code nhìn như sẽ thực thi từng bước từ trên xuống dưới, nhưng thực tế chỉ chạy khi có **terminal operation**, có thể dừng sớm, chạy đồng thời hoặc được JVM/Stream implementation **lược bỏ những bước không ảnh hưởng kết quả**.

Điều này đặc biệt dễ gây nhầm lẫn khi lập trình viên đặt breakpoint bên trong lambda của `filter`, `map`, `peek`, hoặc thêm `System.out.println` để "xem từng phần tử". Một breakpoint không được kích hoạt **không tự chứng minh có lỗi**; một dòng log không xuất hiện **không tự chứng minh phần tử chưa tồn tại**. Trước khi sửa thuật toán, cần hiểu hợp đồng của pipeline.

Bài này hướng dẫn:

- Dùng **breakpoint** để theo dõi giá trị và ngoại lệ ở đúng giai đoạn.
- Dùng `Stream.peek` như một phép quan sát **phục vụ chẩn đoán**, không làm thay đổi dữ liệu.
- Hiểu sự khác nhau giữa **lazy evaluation**, **short-circuit**, **encounter order**, **tối ưu hóa Stream** và tác động của **JIT/debugger**.
- Nhận diện trường hợp `count()` trên nguồn có kích thước biết trước có thể **không chạy lambda** ở các bước trung gian.
- Chọn phương pháp đúng hơn khi cần xác minh **kết quả nghiệp vụ**, **số phần tử được xử lý** hay **hiệu năng**.
- Tránh biến `peek` thành nơi sửa dữ liệu, ghi audit, gọi API hoặc cập nhật trạng thái chia sẻ.

> **Phiên bản ví dụ:** Java 17 trở lên. `Stream.peek` có từ Java 8. Hợp đồng tối ưu hóa cho phép bỏ qua việc duyệt khi tính `count()` được nêu rõ trong tài liệu từ Java 9; hành vi cụ thể có thể khác giữa JDK, loại nguồn và pipeline. Không dùng số dòng log như một bảo đảm kiểm thử.

## 1. Bản đồ luồng thực thi: mô tả pipeline không phải thực thi pipeline

Một pipeline thường có ba phần:

~~~text
Nguồn                    Intermediate operations           Terminal
-----                    -----------------------           --------
orders.stream()   --->   filter -> map -> peek      --->   toList()
                           |        |        |
                        thường lazy, chưa chạy khi được khai báo
~~~

Ví dụ:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .peek(n -> System.out.println("peek=" + n));

// Chưa có terminal operation: không nên trông đợi log peek.
System.out.println("Pipeline prepared");

List<Integer> result = pipeline.toList();

System.out.println(result); // [20, 40]
~~~

Tại thời điểm gán `pipeline`, Java chỉ tạo **mô tả các bước xử lý**. Các lambda của `filter`, `map`, `peek` nhìn chung chưa xử lý phần tử.

Khi gọi `toList()`, terminal operation yêu cầu kết quả và pipeline mới được thực thi. Trên một nguồn `List` có thứ tự, pipeline tuần tự như ví dụ thường quan sát các giá trị `20`, `40` ở `peek`; **nhưng không nên biến các lần gọi peek thành điều kiện của chương trình**.

Đừng nhầm với `List.stream().forEach(...)`: `forEach` là terminal operation, còn `peek` là intermediate operation.

## 2. peek làm gì, và không làm gì?

Chữ ký cơ bản:

~~~java
Stream<T> peek(Consumer<? super T> action)
~~~

`peek` trả một Stream chứa **cùng các phần tử** về mặt ngữ nghĩa, đồng thời cung cấp một action để quan sát phần tử khi chúng đi qua điểm đó **nếu bước xử lý được thực thi**.

~~~java
List<String> values = List.of("a", "bb", "ccc");

List<Integer> lengths = values.stream()
        .map(String::length)
        .peek(length -> System.out.println(
                "Length observed: " + length))
        .toList();
~~~

`peek` không thay thế `map`: giá trị trả về từ action không được dùng vì `Consumer.accept` có kiểu `void`. `peek` cũng không thay thế `filter`: nó không quyết định phần tử nào được giữ.

| Phương thức | Vai trò được đặc tả | Đầu ra |
| --- | --- | --- |
| `map(f)` | Biến đổi từng phần tử theo hàm `f` | Stream kiểu kết quả mới |
| `filter(p)` | Chỉ giữ phần tử thỏa predicate | Có thể ít phần tử hơn |
| `peek(action)` | Cho phép action quan sát phần tử khi được thực thi | Giữ nguyên phần tử trong pipeline |
| `forEach(action)` | Terminal operation thực hiện action trên kết quả | Không trả Stream |
| `forEachOrdered(action)` | Terminal operation thực hiện action theo encounter order nếu có | Không trả Stream |
| `count()` | Terminal operation tính số phần tử kết quả | `long` |

**Cảnh báo quan trọng:** Java API cho phép implementation **bỏ qua việc thực thi một số thao tác hoặc không duyệt các phần tử nguồn** nếu có thể tính đúng kết quả. Vì vậy, **không được dùng `peek` làm cơ chế bắt buộc chạy audit, ghi DB, thay đổi trạng thái, đếm lượt callback hoặc thu thập sự kiện giao dịch**.

## 3. Vì sao breakpoint trong peek có thể không dừng: tối ưu count()

Đây là tình huống kinh điển:

~~~java
import java.util.List;

long count = List.of("A", "B", "C").stream()
        .peek(value -> System.out.println("Seen: " + value))
        .count();

System.out.println("count=" + count); // 3
~~~

Người mới học có thể chờ ba dòng `Seen: ...`. Nhưng trên các phiên bản JDK hiện đại, **không được bảo đảm** có bất kỳ dòng nào xuất hiện.

Vì sao?

1. Nguồn là một `List` biết chính xác số phần tử.
2. `peek` không thay đổi số phần tử trong Stream.
3. `count()` chỉ cần trả số lượng phần tử kết quả.
4. Nếu runtime có thể xác định con số từ nguồn và các thuộc tính pipeline, nó có thể **không duyệt** ba phần tử và **không gọi action của peek**.

Tài liệu API của `Stream.count()` nêu rõ khả năng tối ưu này: với nguồn biết kích thước và các intermediate operation không làm thay đổi số lượng, việc lược bỏ thực thi vẫn cho **kết quả count đúng**.

Một ví dụ tương tự:

~~~java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println("Map called with: " + n);
            return n * 10;
        })
        .count();

System.out.println(count); // 3
~~~

`map` không làm thay đổi cardinality; các lời gọi mapper có thể bị lược bỏ nếu không cần thiết cho kết quả `count()`.

### Điều phải và không phải kết luận

**Được kết luận:**

- `count()` trả đúng `3` cho ví dụ.
- Action trong `peek`/`map` không phải điểm chốt để đo số phần tử đã được duyệt.
- Breakpoint trong những lambda đó **có thể không được kích hoạt**.

**Không được kết luận:**

- "IDE hoặc debugger bị lỗi".
- "JVM bỏ sót dữ liệu".
- "Cứ gọi terminal operation là mọi lambda được chạy".
- "Mọi pipeline `count()` đều không duyệt dữ liệu".

Nếu có `filter` mà việc quyết định giữ/loại phụ thuộc dữ liệu, implementation thông thường phải đánh giá predicate để đếm đúng, trừ khi có đủ thông tin khác để tính kết quả. **Đừng lấy số lần gọi `peek` đi kèm làm điều kiện bắt buộc**, bởi hợp đồng vẫn cho phép tối ưu trong những trường hợp phù hợp.

## 4. SIZED, đặc tính nguồn và giới hạn suy luận

Các nguồn Stream có thể mang thông tin từ `Spliterator`. Hai đặc tính liên quan:

- `SIZED`: biết kích thước chính xác của những phần tử còn lại theo hợp đồng nguồn.
- `SUBSIZED`: các Spliterator thu được sau khi tách cũng có kích thước chính xác, hữu ích khi chia công việc.

Một `ArrayList`, mảng hoặc những nguồn có kích thước cố định thường cho runtime thông tin kích thước rõ ràng; nhiều nguồn I/O hoặc nguồn vô hạn không có cùng loại thông tin.

Nhưng việc biết nguồn có 1.000 phần tử **không đồng nghĩa mọi pipeline cho ra 1.000 phần tử**:

~~~java
long count = numbers.stream()
        .filter(n -> n > 0)
        .count();
~~~

`filter` có thể loại phần tử; chỉ biết kích thước nguồn chưa đủ để xác định số phần tử thỏa predicate.

Bảng định hướng:

| Bước trung gian | Có thể làm thay đổi số lượng kết quả? | Hệ quả đối với suy luận count |
| --- | --- | --- |
| `map` | Không, một phần tử tạo một phần tử | Thường không cần chạy mapper chỉ để biết số lượng |
| `peek` | Không | Action có thể không chạy khi count tối ưu |
| `filter` | Có | Thường phải kiểm tra predicate |
| `flatMap` | Có, 0..N phần tử từ một input | Không suy ra chỉ từ kích thước nguồn |
| `mapMulti` | Có, 0..N phần tử từ một input | Tương tự, cần biết số đầu ra thực |
| `distinct` | Có thể loại trùng | Cần xét dữ liệu/đặc tính nguồn |
| `limit(n)` | Có thể rút ngắn | Có thể tính số kết quả bằng metadata trong một số trường hợp |
| `skip(n)` | Có thể bỏ phần tử đầu | Một số nguồn có thể suy ra kích thước kết quả |

**Bảng chỉ là gợi ý về khả năng tối ưu**, không phải danh sách cứng phương thức nào "luôn gọi" hoặc "không bao giờ gọi" lambda. JDK và nguồn cụ thể có thể thay đổi.

### Không sửa characteristic của Spliterator để ép debugger

Tự viết Spliterator rồi cố tình khai báo sai `SIZED`/`SUBSIZED` để khiến `count` có hành vi mong muốn là **vi phạm hợp đồng nguồn**. Các characteristic ảnh hưởng tới cách runtime tính toán, phân chia và tối ưu; khai báo sai có thể phá tính đúng.

Khi cần quan sát dữ liệu thật, chọn một **đường chạy phù hợp với mục tiêu debug**, không phá metadata của nguồn.

## 5. Đặt peek trước và sau filter/map để khoanh vùng

Một cách hữu ích để chẩn đoán pipeline là quan sát dữ liệu tại những **ranh giới được đặt tên rõ**:

~~~java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6).stream()
        .peek(n -> System.out.println("SOURCE: " + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("AFTER_FILTER: " + n))
        .map(n -> n * 10)
        .peek(n -> System.out.println("AFTER_MAP: " + n))
        .toList();

System.out.println(result); // [20, 40, 60]
~~~

Với nguồn có thứ tự, pipeline **tuần tự**, terminal cần toàn bộ giá trị, ví dụ trên thường cho thấy đường đi của từng phần tử qua các giai đoạn.

Cách đọc:

- `SOURCE`: giá trị đến trước bộ lọc.
- `AFTER_FILTER`: những giá trị bộ lọc giữ lại.
- `AFTER_MAP`: giá trị sau biến đổi.
- `result`: đầu ra thực tế cần kiểm chứng.

**Điểm quan trọng:** `peek` được đặt **sau** `filter` chỉ quan sát những phần tử mà filter cho qua ở bước đó. Nếu cần tìm vì sao một phần tử bị loại, breakpoint hoặc log phải nằm **trong predicate** hay **trước filter**.

### Nhãn quan sát giúp tránh nhầm lẫn

Đừng chỉ in `System.out.println(n)` nhiều lần, vì không biết số đó đến từ giai đoạn nào. Khi cần chẩn đoán:

~~~java
.peek(n -> System.out.printf(
        "[stage=after-map] n=%d%n", n))
~~~

Nếu có id nghiệp vụ, in id thay vì toàn bộ object:

~~~java
.peek(order -> System.out.printf(
        "[stage=filtered] orderId=%s%n", order.id()))
~~~

Không in token, email, bí mật hoặc nội dung nhạy cảm nếu log có thể được lưu/chuyển tiếp. Debug log là một đầu ra có rủi ro dữ liệu, không phải vùng an toàn mặc định.

## 6. Breakpoint trong lambda: nên đặt ở đâu?

Một debugger Java trong IDE thường cho phép đặt breakpoint ngay ở dòng lambda. Nhưng một lambda dạng một dòng có thể khó theo dõi khi có nhiều thao tác và cùng dòng source.

Ví dụ:

~~~java
List<Integer> result = values.stream()
        .filter(n -> n > 0)
        .map(n -> n * 2)
        .toList();
~~~

Để gỡ lỗi predicate hoặc mapper, tách lambda thành block:

~~~java
List<Integer> result = values.stream()
        .filter(n -> {
            boolean accepted = n > 0; // đặt breakpoint tại đây
            return accepted;
        })
        .map(n -> {
            int mapped = n * 2;       // đặt breakpoint tại đây
            return mapped;
        })
        .toList();
~~~

Hoặc tách thành **phương thức được đặt tên**:

~~~java
static boolean isPositive(int n) {
    return n > 0;                    // breakpoint riêng
}

static int twice(int n) {
    return Math.multiplyExact(n, 2); // breakpoint riêng
}
~~~

Dùng:

~~~java
List<Integer> result = values.stream()
        .filter(PipelineDebugDemo::isPositive)
        .map(PipelineDebugDemo::twice)
        .toList();
~~~

Ưu điểm:

- Breakpoint có vị trí rõ hơn.
- Có thể đặt **conditional breakpoint** như `n == 42`.
- Dễ xem biến local, tham số và call stack.
- Tách logic để viết unit test không cần chạy toàn bộ Stream.
- Phân biệt lỗi xử lý dữ liệu với việc quan sát pipeline.

### Quy trình debug một phần tử cụ thể

1. Tạo **dữ liệu hữu hạn và có thể tái lập**.
2. Nếu cần thứ tự dự đoán, bắt đầu bằng `stream()` tuần tự.
3. Đặt breakpoint ở predicate/mapper nghi ngờ, không đặt tràn lan.
4. Dùng điều kiện phù hợp như `order.id().equals("O-42")`.
5. Gọi terminal operation thực sự cần kết quả, ví dụ `toList()`.
6. Kiểm tra **giá trị vào**, **kết quả predicate/mapper**, **đầu ra cuối cùng**.
7. Khi không hit breakpoint, kiểm tra **lazy, short-circuit, metadata nguồn và tối ưu hóa** trước khi nghi ngờ IDE.

**Đừng sử dụng số lần breakpoint dừng làm bộ đếm nghiệp vụ.** Bước debugger có thể làm chậm đáng kể runtime, và số lần lambda chạy không phải lúc nào cũng được Stream API bảo đảm.

## 7. Chương trình Java 17 hoàn chỉnh: quan sát và kiểm tra kết quả

Chương trình sau tập trung vào một tình huống thực tế: từ đơn hàng, chỉ giữ những đơn đã thanh toán và có số tiền dương, rồi tạo bản ghi tổng hợp. Nó có ba chế độ quan sát:

- Pipeline `toList` để kiểm tra kết quả.
- `count()` trên nguồn biết kích thước để minh họa **peek có thể không chạy**.
- Một terminal operation `forEachOrdered` khi muốn thực hiện action trên **mỗi kết quả của Stream có thứ tự**.

Lưu thành `PipelineDebugDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class PipelineDebugDemo {

    record Order(
            String id,
            long amountCents,
            boolean paid
    ) {}

    record Summary(String orderId, long amountCents) {}

    static boolean eligible(Order order) {
        // Breakpoint: xem order.id(), paid, amountCents.
        return order.paid() && order.amountCents() > 0L;
    }

    static Summary summarize(Order order) {
        // Breakpoint: xem giá trị sau lọc, trước khi tạo Summary.
        return new Summary(order.id(), order.amountCents());
    }

    static List<Summary> buildSummaries(List<Order> orders) {
        return orders.stream()
                .peek(order -> System.out.println(
                        "[input] " + order.id()))
                .filter(PipelineDebugDemo::eligible)
                .peek(order -> System.out.println(
                        "[eligible] " + order.id()))
                .map(PipelineDebugDemo::summarize)
                .peek(summary -> System.out.println(
                        "[summary] " + summary.orderId()))
                .toList();
    }

    static void inspectCountElision() {
        long count = List.of(10, 20, 30).stream()
                .peek(n -> System.out.println(
                        "[count-peek] " + n))
                .count();

        // Luôn là 3; các log count-peek không được bảo đảm.
        System.out.println("count=" + count);
    }

    static void visitOrderedResults(List<Order> orders) {
        // Terminal action được dùng để xử lý từng kết quả,
        // không dùng peek làm cơ chế bắt buộc.
        orders.stream()
                .filter(PipelineDebugDemo::eligible)
                .map(PipelineDebugDemo::summarize)
                .forEachOrdered(summary ->
                        System.out.println(
                                "[terminal] " + summary.orderId()));
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-01", 10000L, true),
                new Order("O-02", 2500L, false),
                new Order("O-03", 0L, true),
                new Order("O-04", 7100L, true)
        );

        List<Summary> summaries = buildSummaries(orders);

        List<Summary> expected = List.of(
                new Summary("O-01", 10000L),
                new Summary("O-04", 7100L)
        );

        if (!expected.equals(summaries)) {
            throw new AssertionError(
                    "Unexpected summaries: " + summaries);
        }

        System.out.println("result=" + summaries);
        inspectCountElision();
        visitOrderedResults(orders);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 PipelineDebugDemo.java
java PipelineDebugDemo
~~~

Phần kết quả được **bảo đảm theo hợp đồng** của pipeline trên nguồn `List` có thứ tự:

~~~text
result=[Summary[orderId=O-01, amountCents=10000], Summary[orderId=O-04, amountCents=7100]]
count=3
[terminal] O-01
[terminal] O-04
~~~

Trong một lần chạy, các dòng `[input]`, `[eligible]` và `[summary]` có thể xuất hiện xen giữa theo cách pipeline xử lý. **Không coi thứ tự dòng peek hoặc số lượng dòng peek là kết quả kiểm thử cần khẳng định**; chỉ dùng chúng làm dấu vết hỗ trợ chẩn đoán. Ở `inspectCountElision`, JDK có thể không in bất kỳ dòng `[count-peek]` nào.

Sự khác biệt quan trọng: chương trình kiểm tra nội dung `summaries` bằng `equals`. Đây mới là **bằng chứng tính đúng** của yêu cầu nghiệp vụ; những dòng peek chỉ giúp người học nhìn vào quá trình thực thi khi runtime có thực hiện action đó.

## 8. Vì sao không nên bắt debugger "bắt buộc hit" mọi phần tử?

Ba điều khác nhau cần phân biệt:

1. **Logic của pipeline:** những phần tử nào phải có trong kết quả.
2. **Lịch thực thi:** thread nào chạy lambda, khi nào gọi, có chia nguồn không.
3. **Quan sát của debugger:** breakpoint có được phát hiện/hit theo code đang được thực thi hay không.

Stream API đặc tả chủ yếu **kết quả và ràng buộc hành vi**, không bảo đảm gọi mọi lambda theo đúng thứ tự viết code.

Ngoài tối ưu của Stream implementation, JIT có thể inline hoặc thay đổi cách mã được thực thi; debugger và JVM thường phối hợp để hỗ trợ breakpoint nhưng việc debug có thể yêu cầu deoptimization và làm thay đổi timing. **Đừng diễn giải khác biệt tốc độ giữa Debug và Run là kết quả benchmark**.

Một workflow hiệu quả:

- Dùng breakpoint khi cần kiểm tra **một giá trị, một nhánh điều kiện hoặc một exception**.
- Dùng test với input cố định khi cần kiểm tra **đầu ra**.
- Dùng profiler/JFR khi cần kiểm tra **nút thắt thực thi**.
- Dùng JMH hoặc load test khi cần đo **hiệu năng**.

Không buộc người đọc tin rằng debugger luôn hiển thị một call stack theo đúng bố cục pipeline trong mã nguồn; một số bước có thể được inline, kết hợp hoặc không thực thi.

## 9. Short-circuit: chỉ một phần đầu vào có thể được quan sát

Các terminal operation như `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` và intermediate operation `limit` có khả năng **dừng sớm** khi đã có đủ thông tin.

Ví dụ:

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

int firstEven = numbers.stream()
        .peek(n -> System.out.println("Checked: " + n))
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 2
~~~

Trên pipeline **tuần tự** có encounter order và input ở ví dụ, runtime thường chỉ cần xem `1` và `2`. Nhưng không nên viết test yêu cầu `peek` chính xác hai lần. Với pipeline song song, việc đánh giá và phối hợp kết quả có thể khiến nhiều phần tử được kiểm tra trước khi có kết quả.

Tương tự:

~~~java
List<Integer> limited = numbers.stream()
        .peek(n -> System.out.println("Before limit: " + n))
        .limit(2)
        .toList();

System.out.println(limited); // [1, 2]
~~~

`limited` có đúng hai phần tử; **không được suy ra** rằng mọi action chẩn đoán trước `limit` đều chạy đúng hai lần trong mọi cấu hình nguồn, JDK và mức song song.

### findFirst khác findAny

- `findFirst` bảo toàn ý nghĩa phần tử đầu theo encounter order nếu nguồn có thứ tự.
- `findAny` cho phép chọn **một phần tử bất kỳ** phù hợp, đặc biệt hữu ích khi không cần duy trì thứ tự trong xử lý song song.
- Nếu nguồn unordered, không thể dùng log peek để suy ra một thứ tự nghiệp vụ không hề được đặc tả.

**Điểm cần kiểm thử là tính đúng của kết quả được API cho phép**, không phải những phần tử tình cờ đã được action log chạm tới.

## 10. peek trước/ sau sorted, distinct và thao tác có trạng thái

Những thao tác có trạng thái (*stateful intermediate operations*) như `distinct`, `sorted`, `limit`, `skip` và các phép lấy tiền tố có thể ảnh hưởng thứ tự đánh giá hoặc số phần tử quan sát được.

### distinct

~~~java
List<Integer> input = List.of(3, 1, 3, 2, 1);

List<Integer> unique = input.stream()
        .peek(n -> System.out.println("Before distinct: " + n))
        .distinct()
        .peek(n -> System.out.println("After distinct: " + n))
        .toList();

System.out.println(unique); // [3, 1, 2]
~~~

Điều được đặc tả: `distinct` giữ giá trị duy nhất; với ordered Stream, tính ổn định giữ lần xuất hiện đầu tiên của từng giá trị. Nếu quan sát được log, `peek` sau `distinct` cho thấy các phần tử **đã qua bước loại trùng**. Không dùng số dòng log để chứng minh có bao nhiêu phép so sánh/hash thực sự đã xảy ra.

### sorted

~~~java
List<Integer> sorted = input.stream()
        .peek(n -> System.out.println("Before sorted: " + n))
        .sorted()
        .peek(n -> System.out.println("After sorted: " + n))
        .toList();

System.out.println(sorted); // [1, 1, 2, 3, 3]
~~~

`sorted` có thể cần thu thập dữ liệu trước khi phát kết quả đã sắp xếp. Vì vậy dấu vết trước/sau `sorted` có thể trông khác pipeline chỉ gồm các bước không trạng thái. **Không suy ra cách cấp phát buffer hay thuật toán sắp xếp nội bộ chỉ từ thứ tự log**.

### Giới hạn của việc chèn peek để quan sát

Khi thêm `peek`, bạn đã **thay đổi pipeline** (thêm action chẩn đoán); việc in console còn tạo I/O và có thể tác động scheduling/hiệu năng. Đây là một công cụ khoanh vùng lỗi, không phải phép đo đặc tính chuẩn của pipeline sản xuất.

## 11. Parallel stream: encounter order không phải thứ tự chạy lambda

Ví dụ:

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

List<Integer> result = numbers.parallelStream()
        .peek(n -> System.out.println(
                "peek " + n + " on "
                + Thread.currentThread().getName()))
        .map(n -> n * 10)
        .toList();

System.out.println(result);
// [10, 20, 30, 40, 50, 60]
~~~

Với nguồn `List` ordered, `toList()` duy trì encounter order của kết quả. Nhưng những dòng `peek` có thể xuất hiện **không theo thứ tự 1,2,3,4,5,6** và có thể chạy trên nhiều thread.

Phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Encounter order** | Thứ tự logic được nguồn/pipeline công bố |
| **Execution order** | Lịch thực thi mapper, filter, peek do runtime quyết định |
| **Output order** | Thứ tự phần tử đầu ra do terminal operation cam kết |
| **Print order** | Thứ tự các dòng log đến console khi nhiều thread in |

Không đồng nhất bốn khái niệm này.

### forEach và forEachOrdered

~~~java
numbers.parallelStream()
        .forEach(n -> System.out.println("any: " + n));

numbers.parallelStream()
        .forEachOrdered(n -> System.out.println("ordered: " + n));
~~~

- `forEach` không bảo đảm hành động thực hiện theo encounter order.
- `forEachOrdered` thực hiện action trên các phần tử kết quả theo encounter order của nguồn có thứ tự.
- Nhưng **`forEachOrdered` không ép mọi mapper/peek phía trước chạy tuần tự hoặc đúng thứ tự**; nó điều phối việc thực hiện terminal action.

Nếu đầu ra nghiệp vụ yêu cầu kết quả có thứ tự, kiểm tra `toList`/`forEachOrdered` và nguồn ordered, không kiểm tra chuỗi log bên trong `peek`.

### Breakpoint trong parallel pipeline

Khi nhiều worker cùng hit một breakpoint:

- IDE có thể tạm dừng một thread hoặc tất cả thread tùy chế độ suspend.
- Việc tạm dừng thay đổi lịch thực thi và có thể che/bộc lộ race condition.
- Giá trị trong biến local của một task không đại diện cho toàn bộ pipeline.
- Shared mutable state có thể thay đổi trước khi bạn xem nó.

Để tìm lỗi logic đơn giản, bắt đầu **tuần tự**. Để tìm lỗi concurrency, dùng test phù hợp cho trạng thái đồng thời, thu thập thread dump/profiler và tránh suy luận kết quả từ một lần debug.

## 12. Không biến peek thành bộ đếm hoặc audit có side effect

Một anti-pattern:

~~~java
int[] countSeen = {0};

long count = numbers.stream()
        .peek(n -> countSeen[0]++)
        .count();

System.out.println(countSeen[0]);
// Không được khẳng định luôn bằng numbers.size().
~~~

Vấn đề chính: `peek` không cam kết action được thực hiện cho mọi phần tử. Với parallel Stream, cập nhật `int[]` dùng chung còn **không an toàn đồng thời**.

Ngay cả khi chuyển sang `AtomicInteger`:

~~~java
java.util.concurrent.atomic.AtomicInteger seen =
        new java.util.concurrent.atomic.AtomicInteger();

long count = numbers.stream()
        .peek(n -> seen.incrementAndGet())
        .count();
~~~

Bạn có thể tránh được race của phép tăng, nhưng **vẫn không sửa được ngữ nghĩa**: implementation có thể không gọi `peek` nếu không cần để tính kết quả.

### Làm gì khi cần đếm thật?

Nếu cần số phần tử kết quả, dùng `count()`:

~~~java
long matched = numbers.stream()
        .filter(n -> n > 0)
        .count();
~~~

Nếu cần số phần tử từng nhóm, dùng `groupingBy(..., counting())`. Nếu cần tính nhiều chỉ số cùng lúc, dùng collector thích hợp. Nếu cần audit bắt buộc, thiết kế **giao thức xử lý sự kiện riêng** có hợp đồng về giao dịch, retry và lỗi; không phụ thuộc `peek` của Stream.

**Không sử dụng `peek` để:**

- Ghi bản ghi tài chính bắt buộc.
- Xóa hoặc sửa dữ liệu nguồn.
- Gọi HTTP endpoint cần đúng một lần cho mỗi phần tử.
- Cập nhật Map dùng chung từ parallel Stream.
- Thay thế kiểm thử nội dung kết quả.

## 13. Dùng debugger để điều tra ngoại lệ trong mapper/filter

Trong dữ liệu thực tế, nhiều lỗi xuất hiện ở một phần tử bất thường:

~~~java
List<String> raw = List.of("10", "20", "oops", "30");

List<Integer> values = raw.stream()
        .map(Integer::parseInt)
        .toList();
// NumberFormatException khi gặp "oops".
~~~

Có hai cách debug chính.

### 13.1. Exception breakpoint

Thiết lập breakpoint cho `NumberFormatException` trong debugger. Khi exception được ném, xem call stack và đối số đang parse. Cách này hữu ích khi không biết trước giá trị nào làm hỏng pipeline.

### 13.2. Phương thức có tên và điều kiện

~~~java
static int parseStrict(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid integer input: " + raw, ex);
    }
}
~~~

Dùng:

~~~java
List<Integer> values = raw.stream()
        .map(PipelineDebugDemo::parseStrict)
        .toList();
~~~

Đây là **mẫu phương thức bổ sung** cho lớp `PipelineDebugDemo` ở phần 7; để chạy độc lập cần đặt phương thức trong đúng lớp và bảo đảm biến `raw` nằm trong scope.

### Đừng nuốt lỗi bằng peek

Không nên đặt `try/catch` trong `peek` để "sửa" dữ liệu rồi tiếp tục pipeline không có chính sách rõ. Nếu parser cho phép dữ liệu lỗi, hãy có một bước parse tạo `ParseResult` biểu diễn thành công/thất bại, rồi tính số bản ghi lỗi và báo cáo rõ.

Nếu pipeline xử lý một nguồn I/O, lỗi đọc tệp không được chuyển thành "0 bản ghi" chỉ để terminal operation trả kết quả thành công. Kỹ thuật debug không được thay đổi hợp đồng phát hiện lỗi.

## 14. Dữ liệu null và khó khăn khi đặt breakpoint sau filter

Giả sử danh sách có thể chứa `null`:

~~~java
List<String> raw = new java.util.ArrayList<>();
raw.add(" A ");
raw.add(null);
raw.add(" B ");

List<String> cleaned = raw.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::trim)
        .toList();

System.out.println(cleaned); // [A, B]
~~~

Nếu đặt breakpoint **trong `String::trim`** hoặc `peek` sau filter, sẽ không thấy phần tử `null` đã bị loại. Đó là hành vi đúng, không phải dữ liệu biến mất bí ẩn.

Khi mục tiêu là tìm vì sao null có mặt trong đầu vào, cần xem dữ liệu **trước filter** hoặc kiểm tra nguồn dữ liệu ở điểm sinh record. Nếu `null` là dữ liệu không hợp lệ theo nghiệp vụ, đừng âm thầm loại chỉ để hết `NullPointerException`; hãy xác thực và báo lỗi theo yêu cầu.

**Không dùng `List.of("A", null, "B")` làm fixture** vì `List.of` không chấp nhận phần tử `null`; trong ví dụ này ta dùng `ArrayList` có thể chứa null.

## 15. Tài nguyên I/O và peek: short-circuit không tự đóng nguồn

Một nguồn như `Files.lines` sở hữu file handle. Việc thêm `peek` để in log hoặc `limit` để dừng sớm **không thay thế `close()`**.

Ví dụ đúng:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> firstWarnings(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("WARN"))
                .peek(line -> System.out.println(
                        "[diagnostic] " + line))
                .limit(3)
                .toList();
    }
}
~~~

`try-with-resources` đóng Stream khi rời khối, kể cả khi `limit(3)` đã có đủ kết quả hoặc terminal operation ném exception.

Hai điểm cần phân biệt:

- `peek` chỉ là phép quan sát và **có thể bị bỏ qua** trong một số đường thực thi.
- `Files.lines` có thể ném lỗi I/O trong **lúc duyệt lazy**, không chỉ khi mở tệp. Không được nuốt những lỗi đó để trả báo cáo hoàn chỉnh giả.

Nếu cần kiểm tra chương trình **thực sự đóng nguồn**, có thể thêm một `onClose` trong test mô phỏng để xem callback được chạy khi đóng:

~~~java
java.util.concurrent.atomic.AtomicBoolean closed =
        new java.util.concurrent.atomic.AtomicBoolean(false);

try (Stream<Integer> stream = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true))) {
    stream.findFirst();
}

if (!closed.get()) {
    throw new AssertionError("Expected Stream.close()");
}
~~~

Đây là test về cơ chế close của Stream giả lập, **không thay thế** test tích hợp theo dõi tài nguyên tệp thực tế.

## 16. Khi nào dùng forEachOrdered thay vì peek?

Nếu mục tiêu là thực hiện một action **cho từng phần tử kết quả** khi pipeline hoàn tất bình thường, có thể dùng terminal operation.

~~~java
List<String> names = List.of("Lan", "An", "Minh");

names.stream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
~~~

Với nguồn ordered, hành động terminal xuất ra các giá trị theo encounter order. Nhưng trước khi dùng nó cho một hệ thống audit, nhớ rằng:

1. **I/O/DB có thể thất bại** giữa chừng.
2. Một transaction hoặc message broker có thể yêu cầu retry/idempotency và xử lý kết quả một phần.
3. Chạy lại pipeline có thể lặp action.
4. Một exception có thể làm pipeline chưa xử lý hết mọi phần tử.
5. `forEachOrdered` không tự tạo giao thức *exactly-once*.

Vì vậy `forEachOrdered` phù hợp khi action trên mỗi phần tử là **mục tiêu của terminal operation**, nhưng một quy trình giao dịch đúng cần thêm thiết kế ở tầng ứng dụng.

Nếu mục tiêu chỉ là debug, `peek` thường tiện khi muốn **giữ pipeline còn một terminal kết quả**; đừng dùng terminal `forEach` giữa pipeline rồi cố tiếp tục Stream cũ.

## 17. Test kết quả: bằng chứng mạnh hơn log và breakpoint

Một test không nên kết luận thành công chỉ vì "đã thấy ba dòng log". Thay vào đó, so kết quả với **oracle** dễ hiểu.

Ví dụ:

~~~java
List<Integer> input = List.of(-1, 0, 1, 2, 3, 4);

List<Integer> actual = input.stream()
        .filter(n -> n > 0)
        .map(n -> n * 2)
        .toList();

List<Integer> expected = List.of(2, 4, 6, 8);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected=" + expected + ", actual=" + actual);
}
~~~

Đây là cách kiểm tra tính đúng của `filter` và `map` về **giá trị và thứ tự**. Không cần biết `peek` có chạy bao nhiêu lần.

Có thể dùng một vòng lặp độc lập làm oracle:

~~~java
List<Integer> expected = new java.util.ArrayList<>();

for (int value : input) {
    if (value > 0) {
        expected.add(value * 2);
    }
}
~~~

Khi cần kiểm tra tính chất chung, tạo nhiều input hữu hạn bằng seed cố định; ghi seed và input nếu test thất bại. Đừng tạo ngẫu nhiên ngay trong lambda của một pipeline song song rồi mong debugger sẽ tái hiện cùng thứ tự thực thi.

### Kiểm tra bằng bất biến

Với `filter(p)` trên List có thứ tự:

- Mọi kết quả đều thỏa `p`.
- Kết quả giữ thứ tự tương đối của những phần tử được chọn.
- Kết quả không chứa phần tử không xuất hiện ở nguồn, trừ khi pipeline có phép biến đổi tạo giá trị mới.
- Số phần tử kết quả không vượt quá số phần tử đầu vào.

Các bất biến này mạnh hơn việc đếm những lần action log trong `peek` được gọi.

## 18. Debugger không phải profiler và log không phải benchmark

Đặt breakpoint làm chương trình dừng, có thể khiến JIT deoptimize hoặc đổi lịch thread. In console trong `peek` thường là I/O chậm và có thể gây tranh chấp khi nhiều thread cùng ghi.

Vì vậy, những cách dưới đây **không dùng để kết luận hiệu năng**:

~~~java
// Không nên benchmark bằng output của peek:
long start = System.nanoTime();

numbers.stream()
        .peek(System.out::println)
        .mapToLong(Integer::longValue)
        .sum();

long elapsed = System.nanoTime() - start;
~~~

Phép đo này trộn chi phí tính toán với chi phí in console và trạng thái JIT/GC. Một lần chạy còn dễ bị nhiễu bởi warm-up, scheduler và allocation.

Chọn công cụ theo câu hỏi:

| Câu hỏi | Công cụ phù hợp |
| --- | --- |
| Tại sao bản ghi O-42 bị loại? | Conditional breakpoint ở predicate; fixture cụ thể |
| Trường nào có giá trị null? | Breakpoint trước filter hoặc ở parser |
| Kết quả của nhóm có đúng không? | Unit test/oracle, assertion trên Map/List |
| Action peek có bị lược bỏ vì count không? | Đọc hợp đồng Stream, ví dụ kiểm chứng nhỏ |
| Thứ tự song song có thay đổi giá trị không? | Test tuần tự/song song theo contract |
| CPU đang nóng ở đâu? | CPU profiler hoặc Java Flight Recorder (JFR) |
| Allocation/GC có làm chậm không? | JFR, GC log, benchmark có profiler |
| Thay map bằng mapToInt có lợi không? | JMH với cùng workload và terminal operation |

**Điều cần nhớ:** Logging có thể hỗ trợ nhìn thấy dữ liệu, nhưng kết quả log hiếm khi là phép đo đủ chuẩn cho latency/throughput hoặc số lần gọi lambda.

## 19. Logging có kiểm soát khi không thể dừng bằng debugger

Trong môi trường production, không phải lúc nào cũng được phép tạm dừng tiến trình bằng breakpoint. Có thể cần log có cấu trúc nhưng phải giới hạn:

- Chỉ bật diagnostic cho **một request/batch** hoặc một tỷ lệ mẫu nhỏ.
- Gắn `correlationId` hoặc id nghiệp vụ thay vì in toàn bộ đối tượng.
- Giới hạn số lượng bản ghi log, độ dài trường và thời gian bật.
- Tránh thông tin nhạy cảm, mật khẩu, token hoặc dữ liệu cá nhân.
- Nêu rõ log là **best-effort observation**, không phải audit đầy đủ.
- Tắt diagnostic sau điều tra và đo lại hiệu năng không có logging.

Một predicate chẩn đoán có thể kiểm tra một ID trước khi trả giá trị:

~~~java
static boolean eligible(Order order) {
    if ("O-42".equals(order.id())) {
        // Đặt conditional breakpoint tại đây thay vì log mọi order.
        System.out.println(
                "Investigating amount=" + order.amountCents());
    }
    return order.paid() && order.amountCents() > 0;
}
~~~

Đây là **mã tạm phục vụ debug**. Không để lại `println` trong hot path của production nếu không có chính sách observability phù hợp.

Khi cần bảo đảm đầu vào được ghi nhận, hãy thực hiện ở **ranh giới nhận dữ liệu của hệ thống** với cơ chế log/audit có hợp đồng riêng, không dùng `peek` trong pipeline vốn có thể bỏ qua callback.

## 20. Một số tình huống dễ diễn giải sai

| Hiện tượng | Khả năng nguyên nhân | Cách kiểm tra đúng |
| --- | --- | --- |
| `peek` không in gì khi gọi `count()` | Count suy ra từ kích thước nguồn, không cần duyệt | Kiểm tra kết quả count, đặc tính nguồn và API contract |
| Breakpoint trong `map` không hit | Pipeline chưa có terminal hoặc mapper bị tối ưu bỏ | Kiểm tra đường chạy, terminal, và nếu cần dùng `toList` để xem dữ liệu |
| `peek` sau `filter` không thấy bản ghi X | X bị filter loại trước đó | Breakpoint trong predicate hoặc quan sát trước filter |
| `peek` chỉ thấy vài phần tử | Short-circuit `findFirst`/`limit`/`anyMatch` | Kiểm tra loại terminal, không yêu cầu log đủ nguồn |
| `peek` in lộn xộn | Pipeline song song, print order khác encounter order | Test output với `toList`/`forEachOrdered` |
| `sorted` làm thứ tự log lạ | Có state và có thể buffer dữ liệu | Xem thứ tự đầu ra, không suy internals từ log |
| Debug mode chạy chậm | Breakpoint, deoptimization, console I/O | Đo bằng profiler/benchmark không dừng debugger |
| `AtomicInteger` trong peek vẫn bằng 0 | Action có thể không thực thi | Đếm kết quả bằng terminal, không dựa side effect |
| Có log nhưng dữ liệu cuối sai | Log không phải oracle, có thể chỉ quan sát một giai đoạn | So với fixture/loop tham chiếu |
| Nguồn file đã dừng sớm mà còn mở | `limit/findFirst` không tự đóng I/O | Bao `Files.lines` trong `try-with-resources` |
| Parallel có lỗi thất thường | Shared mutable state hoặc giả định thứ tự | Giảm thành test xác định, kiểm tra races và collector |
| Exception xuất hiện ở terminal | Pipeline lazy; lỗi mapper xảy ra khi tiêu thụ | Exception breakpoint và call stack |

Đừng sửa một hiện tượng "không có log" bằng cách thêm side effect để ép lambda chạy. Điều đó có thể biến một pipeline đúng thành mã phụ thuộc vào hành vi không được đặc tả.

## 21. Quy trình gỡ lỗi an toàn trong một dự án thật

Một quy trình thực dụng:

### Bước 1 — Viết kết quả kỳ vọng

Ví dụ: "Từ bốn đơn trong fixture, chỉ O-01 và O-04 có `paid=true` và `amountCents>0`."

### Bước 2 — Tạo fixture nhỏ, ổn định

Dùng `List.of(...)` với vài bản ghi để loại nhiễu từ DB/network. Nếu lỗi xuất hiện trên dữ liệu ngẫu nhiên, ghi lại seed và input.

### Bước 3 — Kiểm tra có terminal operation

Một Stream mới khai báo sẽ không tự duyệt. Chọn `toList`, `collect`, `sum` hoặc terminal khác theo đúng mục tiêu.

### Bước 4 — Debug tuần tự trước

Nếu logic không phụ thuộc song song, dùng `stream()` để theo dõi một phần tử qua các bước dễ hơn. Nếu lỗi chỉ có trong parallel, giữ một bài test parallel riêng.

### Bước 5 — Đặt một breakpoint có điều kiện

Đặt trong phương thức predicate/mapper có tên, dựa vào id bản ghi cụ thể; tránh đặt tại mọi phần tử và làm chậm toàn bộ ứng dụng.

### Bước 6 — Dùng peek có nhãn nếu cần

Quan sát trước/sau bước nghi ngờ, nhưng không dùng số lần log làm kết quả bảo đảm.

### Bước 7 — Kiểm tra kết quả với oracle

So List/Map/Optional theo hợp đồng, không so log/Thread name.

### Bước 8 — Bỏ diagnostic và chạy regression test

Loại bỏ hoặc tắt `peek` chẩn đoán; đảm bảo sửa lỗi không phụ thuộc side effect. Kiểm tra nguồn rỗng, dữ liệu lỗi, giá trị biên và nguồn có thứ tự/không thứ tự.

### Bước 9 — Đo hiệu năng nếu cần

Dùng profiler/JFR/JMH hoặc load test trên workload đại diện, không đo thời gian trong lúc breakpoint/console logging đang bật.

## 22. Bài tập thực hành

### Bài 1 — Vì sao peek không in đủ ba dòng?

~~~java
long n = List.of(10, 20, 30).stream()
        .peek(System.out::println)
        .count();
~~~

**Câu hỏi:** `n` là bao nhiêu? Có bắt buộc console phải in ba số không?

**Đáp án:** `n == 3`. Không có bảo đảm phải in ba dòng: implementation có thể dùng kích thước đã biết của nguồn để trả `count` mà không gọi action `peek`.

### Bài 2 — Breakpoint không hit

~~~java
Stream<String> pipeline = List.of("a", "b").stream()
        .map(String::toUpperCase);
~~~

**Câu hỏi:** Vì sao breakpoint trong mapper không dừng?

**Đáp án:** Chưa có terminal operation. Pipeline chưa yêu cầu xử lý phần tử. Thêm một terminal cần kết quả như `toList()` để kiểm tra đầu ra; cũng không nên dựa vào mọi mapper sẽ được gọi nếu dùng terminal có thể tối ưu dựa trên metadata.

### Bài 3 — Peek trước và sau filter

~~~java
List<Integer> data = List.of(1, 2, 3, 4);

List<Integer> out = data.stream()
        .peek(n -> System.out.println("A=" + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("B=" + n))
        .toList();
~~~

**Câu hỏi:** Kết quả `out` là gì? Ở bước B, có quan sát số lẻ không?

**Đáp án:** `out = [2,4]`. Bước `peek` sau filter chỉ nằm trên luồng các phần tử được giữ lại; nó không thấy các số lẻ bị loại trước đó. Không viết test assert số lần log chính xác.

### Bài 4 — findFirst và số lần gọi

~~~java
int first = List.of(5, 7, 8, 10).stream()
        .peek(n -> System.out.println(n))
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();
~~~

**Đáp án:** `first == 8`. Trên một ordered, sequential pipeline, thường chỉ cần quan sát đến 8; song song và tối ưu có thể thay đổi số callback được quan sát. Chỉ assert kết quả 8.

### Bài 5 — count và filter khác map thế nào?

**Câu hỏi:** Vì sao `map(...).count()` có thể không chạy mapper, còn `filter(...).count()` thường phải đọc giá trị đầu vào?

**Đáp án:** `map` không đổi số phần tử, còn `filter` có thể bỏ phần tử. Nếu nguồn có kích thước biết trước và các bước không đổi cardinality, `count` có thể tính từ metadata. Với `filter` phụ thuộc nội dung, thường phải đánh giá predicate để biết số phần tử còn lại.

### Bài 6 — Thứ tự log trong parallel

~~~java
List<Integer> out = List.of(1, 2, 3, 4)
        .parallelStream()
        .peek(System.out::println)
        .toList();
~~~

**Đáp án:** `out` giữ thứ tự `[1,2,3,4]` của nguồn `List`; thứ tự in trong `peek` không được bảo đảm là 1,2,3,4. Không dùng log làm oracle cho encounter order.

### Bài 7 — Đếm bằng AtomicInteger trong peek?

**Câu hỏi:** Có thể dùng `AtomicInteger` tăng trong `peek` để audit đúng một lần cho từng phần tử không?

**Đáp án:** Không. Atomicity chỉ xử lý vấn đề cập nhật đồng thời; nó không buộc Stream thực hiện action `peek`. Audit bắt buộc cần thiết kế quy trình riêng và quản lý lỗi, retry, idempotency nếu cần.

### Bài 8 — sorted và breakpoint

**Câu hỏi:** Khi đặt breakpoint trong `peek` trước và sau `sorted`, vì sao thứ tự các lần dừng có thể không tương ứng với vòng lặp đọc từng phần tử rồi in ngay?

**Đáp án:** `sorted` có trạng thái, có thể thu thập dữ liệu trước khi phát phần tử đã sắp xếp. Breakpoint chỉ cho thấy những invocation được runtime thực hiện ở thời điểm đó, không cho phép suy chính xác nội bộ buffering.

### Bài 9 — Debug pipeline đọc file

~~~java
List<String> first = Files.lines(path)
        .peek(System.out::println)
        .limit(5)
        .toList();
~~~

**Đáp án:** Nguồn I/O cần được đóng. Đặt tạo và tiêu thụ `Files.lines` trong `try-with-resources`, kể cả khi `limit` dừng sớm. Đừng dựa vào `peek` để xác nhận tài nguyên đã được đóng.

### Bài 10 — Mục đích nào thuộc test, mục đích nào thuộc debugger?

**Câu hỏi:** Cần chứng minh mọi đơn thanh toán có tiền dương được giữ trong kết quả; nên đếm log `peek` hay so List với oracle?

**Đáp án:** So List/Map với fixture hoặc oracle độc lập. Breakpoint và peek giúp tìm lỗi ở đâu, nhưng không phải cơ chế kiểm chứng đầy đủ của kết quả.

## 23. Ghi nhớ

- **Stream lazy:** khai báo pipeline không nhất thiết chạy lambda; cần terminal operation.
- **`peek` là công cụ quan sát, không phải cam kết callback.** Implementation có thể bỏ qua các stage nếu kết quả vẫn đúng theo hợp đồng.
- **`count()` trên nguồn `SIZED`** có thể tính trực tiếp mà không duyệt phần tử, vì vậy breakpoint trong `peek`/`map` có thể không hit.
- **Short-circuit** như `findFirst`, `anyMatch`, `limit` có thể dừng trước khi duyệt hết nguồn; không suy số phần tử đã xử lý từ log.
- **Encounter order khác execution order.** `toList` hoặc `forEachOrdered` có thể giữ thứ tự kết quả dù log ở `peek` trong parallel Stream xuất hiện không có thứ tự.
- **Breakpoint hiệu quả nhất** là breakpoint có điều kiện trong predicate/mapper được đặt tên, trên dữ liệu nhỏ và có thể tái lập.
- **Tác dụng phụ trong peek là rủi ro:** không dùng để audit, cập nhật Map chung, phát sự kiện bắt buộc hoặc đo số lần callback.
- **Log/debugger không phải benchmark.** Dùng JFR, profiler, JMH hoặc đo end-to-end để kết luận hiệu năng.
- **Nguồn I/O cần được đóng**, dù pipeline dừng sớm: `Files.lines` phải nằm trong `try-with-resources`.
- **Chứng minh tính đúng bằng dữ liệu và kết quả**: assertion, oracle, bất biến và regression test; xem `peek` như dấu vết chẩn đoán tạm thời.

**Ý chính:** Trong Java Stream API, **breakpoint và `peek` chỉ cho thấy những lời gọi mà runtime thực sự thực hiện**, chứ không phải một hợp đồng rằng mọi phần tử phải đi qua tất cả dòng code. Khi hiểu rõ lazy evaluation, tối ưu của `count`, short-circuit và thực thi song song, bạn sẽ biết **lúc nào dấu vết log hữu ích, lúc nào nó có thể vắng mặt hợp lệ, và lúc nào cần chuyển sang kiểm thử kết quả hoặc profiler** để đưa ra kết luận chính xác.

# Dùng JFR so sánh cấp phát của mapMulti, flatMap và mô hình record

Java 16 bổ sung **Stream.mapMulti()**, một phép biến đổi cho phép mỗi phần tử đầu vào phát ra không, một hoặc nhiều phần tử đầu ra thông qua một **Consumer**. Phép này có thể là lựa chọn phù hợp thay cho **flatMap()** khi mỗi phần tử chỉ tạo ra một số lượng nhỏ kết quả. Tuy nhiên, lợi ích về cấp phát phụ thuộc vào cách triển khai, dữ liệu và workload thực tế.

Record cũng thường xuất hiện trong pipeline Stream để biểu diễn dữ liệu đầu vào hoặc kết quả trung gian. Record giúp khai báo data carrier ngắn gọn và có equality theo component, nhưng không tự động loại bỏ object allocation hoặc bảo đảm object nhỏ hơn class thông thường.

Bài học này trình bày cách dùng Java Flight Recorder (JFR) để tìm allocation hot spot trong pipeline, thiết kế phép so sánh công bằng giữa **flatMap()** và **mapMulti()**, sau đó so sánh record với một class bất biến tương đương. JFR giúp tìm đường code tạo object; JMH với GC profiler giúp đo lượng cấp phát chuẩn hóa trên mỗi thao tác.

## 1. Vì sao cần đo allocation của Stream pipeline?

Một pipeline Stream có thể tạo nhiều loại object trong quá trình xử lý:

- Các đối tượng biểu diễn pipeline và stage trung gian.
- Stream con được tạo bên trong mapper của **flatMap()**.
- Kết quả dữ liệu như DTO, record hoặc wrapper.
- Collection và mảng dùng để chứa kết quả sau terminal operation.
- Object phụ trợ do thư viện hoặc ứng dụng tạo trong mapper.

Không phải tất cả object được tạo trong mã nguồn đều chắc chắn trở thành allocation thực tế trên heap. JIT compiler có thể inline phương thức và loại bỏ một số allocation thông qua escape analysis hoặc scalar replacement nếu object không cần tồn tại như một object độc lập. Vì vậy, cần quan sát ứng dụng đã được JIT tối ưu trong điều kiện chạy đại diện.

Khi pipeline chậm hoặc gây áp lực GC, hãy đặt các câu hỏi cụ thể:

1. Allocation đến từ stage Stream hay từ object kết quả?
2. **flatMap()** có tạo overhead đáng kể so với **mapMulti()** trong workload này không?
3. Record kết quả có phải nguồn allocation lớn hay số lượng record tạo ra vốn là yêu cầu nghiệp vụ?
4. Allocation có làm tăng GC hoặc latency không?
5. Thay đổi có giảm byte cấp phát trên mỗi request hoặc mỗi thao tác không?

JFR và JMH trả lời các câu hỏi khác nhau. JFR giúp tìm nguồn allocation trong ứng dụng đang chạy; JMH giúp so sánh định lượng những đoạn code nhỏ trong môi trường benchmark được kiểm soát.

## 2. mapMulti() và flatMap() khác nhau thế nào?

Cả hai đều hỗ trợ phép biến đổi một phần tử thành nhiều phần tử và làm phẳng kết quả.

### flatMap()

**flatMap()** nhận một mapper trả về Stream. Các phần tử của Stream con được nối vào Stream kết quả:

~~~java
import java.util.Arrays;

List<String> words = List.of("java stream", "record api");

List<String> tokens = words.stream()
    .flatMap(text -> Arrays.stream(text.split(" ")))
    .toList();
~~~

Với mỗi phần tử đầu vào, mapper tạo ra một Stream con. Pipeline sau đó tiêu thụ các phần tử của Stream con đó.

### mapMulti()

**mapMulti()** nhận một mapper cùng một Consumer để phát ra các phần tử kết quả. Mapper có thể gọi Consumer không lần nào, một lần hoặc nhiều lần:

~~~java
List<String> words = List.of("java stream", "record api");

List<String> tokens = words.stream()
    .<String>mapMulti((text, out) -> {
        for (String token : text.split(" ")) {
            out.accept(token);
        }
    })
    .toList();
~~~

Cách viết này không yêu cầu mapper trả về một Stream con cho từng phần tử đầu vào. API Java SE ghi rõ **mapMulti()** có thể phù hợp hơn **flatMap()** khi mỗi phần tử đầu vào được thay bằng một số lượng nhỏ phần tử đầu ra, có thể bằng không.

Mapper cần là hàm stateless và non-interfering. Không lưu Consumer để gọi sau khi mapper kết thúc; API quy định kết quả không xác định nếu Consumer được dùng bên ngoài phạm vi lời gọi mapper.

### Không mặc định rằng mapMulti luôn nhanh hơn

Cần đọc cả hợp đồng API và implementation:

- **flatMap()** diễn đạt trực tiếp phép biến đổi từ một phần tử sang một Stream con.
- **mapMulti()** phát kết quả trực tiếp qua Consumer, thuận tiện khi dùng vòng lặp hoặc điều kiện để phát ra một số lượng nhỏ kết quả.
- Implementation cụ thể có thể tối ưu các stage khác nhau. JIT cũng có thể inline hoặc loại bỏ một số allocation.
- Default implementation được mô tả trong API của **mapMulti()** có thể triển khai thông qua **flatMap()** và một buffer nội bộ; implementation của Stream cụ thể có thể override cách này.
- Kết quả hiệu năng phụ thuộc JDK, kích thước dữ liệu, số kết quả trên mỗi phần tử, terminal operation và mức tối ưu của JIT.

Vì vậy, **mapMulti()** là một lựa chọn cần đo trong trường hợp phù hợp, không phải quy tắc thay thế mọi **flatMap()**.

## 3. Record có làm giảm allocation không?

Record là loại class dùng làm data carrier, được chuẩn hóa trong Java 16. Compiler tự sinh canonical constructor, accessor và các implementation mặc định của **equals()**, **hashCode()**, **toString()** dựa trên component.

Ví dụ:

~~~java
public record LineAmount(String sku, long amount) {}
~~~

Mỗi lần gọi:

~~~java
LineAmount result = new LineAmount("SKU-01", 120_000L);
~~~

chương trình tạo một instance record theo ngữ nghĩa Java hiện hành. Record vẫn là object có identity; nó không phải value type và không tự động biến thành dữ liệu nằm trực tiếp trong object chứa nó.

Record cũng chỉ bất biến ở mức nông. Nếu component tham chiếu tới một object mutable, object được tham chiếu vẫn có thể thay đổi.

Khi so sánh allocation của record với class thông thường, cần nhớ:

- Cả record và class đều có thể tạo object trên heap.
- Record không bảo đảm ít byte hơn class tương đương.
- Các phương thức được compiler sinh ra không nhất thiết được gọi trong đường xử lý đang benchmark.
- JIT có thể loại bỏ allocation của cả record lẫn class nếu object không thoát khỏi phạm vi tối ưu.
- Nếu pipeline phát ra một kết quả record cho mỗi dòng dữ liệu, số lượng kết quả vẫn phụ thuộc vào nghiệp vụ.

Do đó, cần đo record trong cùng một phép biến đổi, cùng số lượng kết quả và cùng cách sử dụng output.

## 4. Chuẩn bị mô hình dữ liệu dùng chung

Ví dụ dưới đây dùng một đơn hàng chứa nhiều dòng hàng. Input được biểu diễn bằng record và được chuẩn bị trước khi benchmark để không tính chi phí tạo dữ liệu đầu vào vào kết quả so sánh pipeline.

~~~java
import java.util.List;

record OrderLine(String sku, int quantity, long unitPrice) {}

record Order(List<OrderLine> lines) {
    Order {
        lines = List.copyOf(lines);
    }
}

record LineAmount(String sku, long amount) {}
~~~

Để so sánh record kết quả với class thông thường, khai báo một class bất biến có cùng hai field và accessor tương đương:

~~~java
final class LineAmountClass {
    private final String sku;
    private final long amount;

    LineAmountClass(String sku, long amount) {
        this.sku = sku;
        this.amount = amount;
    }

    String sku() {
        return sku;
    }

    long amount() {
        return amount;
    }
}
~~~

Trong phép so sánh allocation, hai kiểu kết quả đều có hai field và cùng được tạo một lần cho mỗi dòng hàng hợp lệ. Class ví dụ chưa cài đặt **equals()** và **hashCode()** vì benchmark bên dưới không gọi hai phương thức đó. Nếu ứng dụng thực tế dùng equality hoặc hash-based collection, cần triển khai semantics tương đương và đo thêm đúng thao tác đó.

Input được tạo trước:

~~~java
static List<Order> createOrders(int orderCount, int linesPerOrder) {
    return java.util.stream.IntStream.range(0, orderCount)
        .mapToObj(orderIndex -> {
            List<OrderLine> lines =
                java.util.stream.IntStream.range(0, linesPerOrder)
                    .mapToObj(lineIndex -> new OrderLine(
                        "SKU-" + lineIndex,
                        1 + lineIndex % 3,
                        1_000L + lineIndex
                    ))
                    .toList();

            return new Order(lines);
        })
        .toList();
}
~~~

Constructor của **Order** dùng **List.copyOf()** để tách cấu trúc danh sách khỏi list mutable truyền vào. Các phần tử **OrderLine** là record có component primitive và String; String là immutable. Phần tạo input này thuộc setup, không thuộc phép đo pipeline.

## 5. So sánh flatMap và mapMulti với cùng record kết quả

Để cô lập tác động của hai phép biến đổi, hãy dùng cùng input, cùng điều kiện lọc, cùng phép tính và cùng kiểu output **LineAmount**.

### Phiên bản flatMap

~~~java
static List<LineAmount> calculateWithFlatMap(List<Order> orders) {
    return orders.stream()
        .flatMap(order -> order.lines().stream()
            .filter(line -> line.quantity() > 0)
            .map(line -> new LineAmount(
                line.sku(),
                line.quantity() * line.unitPrice()
            )))
        .toList();
}
~~~

Mỗi Order tạo một Stream con từ danh sách dòng hàng. Pipeline con lọc dòng hợp lệ, tạo **LineAmount** và được làm phẳng vào Stream kết quả.

### Phiên bản mapMulti

~~~java
static List<LineAmount> calculateWithMapMulti(List<Order> orders) {
    return orders.stream()
        .<LineAmount>mapMulti((order, out) -> {
            for (OrderLine line : order.lines()) {
                if (line.quantity() > 0) {
                    out.accept(new LineAmount(
                        line.sku(),
                        line.quantity() * line.unitPrice()
                    ));
                }
            }
        })
        .toList();
}
~~~

Mapper duyệt trực tiếp các dòng hàng và gửi từng kết quả qua Consumer. Không tạo Stream con trong mã mapper. Mỗi dòng hợp lệ vẫn tạo một **LineAmount** vì đó là object kết quả mà ứng dụng yêu cầu.

### Những thứ phải giữ giống nhau

| Yếu tố | flatMap | mapMulti |
| --- | --- | --- |
| Input | Cùng danh sách Order | Cùng danh sách Order |
| Điều kiện lọc | quantity > 0 | quantity > 0 |
| Phép tính | quantity × unitPrice | quantity × unitPrice |
| Kiểu kết quả | LineAmount record | LineAmount record |
| Số kết quả | Một kết quả cho mỗi dòng hợp lệ | Một kết quả cho mỗi dòng hợp lệ |
| Terminal operation | toList() | toList() |

Nếu một phiên bản tạo ít kết quả hơn, dùng collection khác hoặc bỏ qua điều kiện nghiệp vụ, phép so sánh không còn công bằng.

## 6. So sánh record với class trong cùng pipeline

Sau khi đã so sánh **flatMap()** và **mapMulti()** trên cùng record, có thể kiểm tra riêng chi phí của mô hình kết quả. Giữ nguyên **mapMulti()**, input và phép tính; chỉ thay kiểu object đầu ra.

~~~java
static List<LineAmountClass> calculateWithClass(List<Order> orders) {
    return orders.stream()
        .<LineAmountClass>mapMulti((order, out) -> {
            for (OrderLine line : order.lines()) {
                if (line.quantity() > 0) {
                    out.accept(new LineAmountClass(
                        line.sku(),
                        line.quantity() * line.unitPrice()
                    ));
                }
            }
        })
        .toList();
}
~~~

Có thể so sánh hai phương thức:

- **calculateWithMapMulti()** tạo một record **LineAmount** cho mỗi dòng hợp lệ.
- **calculateWithClass()** tạo một instance **LineAmountClass** cho mỗi dòng hợp lệ.

Hai phương thức dùng cùng số field, cùng giá trị, cùng điều kiện và cùng kiểu collection kết quả. Kết quả benchmark cho biết sự khác biệt trên JDK và workload được thử nghiệm; nó không tạo ra quy tắc chung rằng record luôn ít hoặc nhiều allocation hơn class.

Để đo đúng tác động của các phương thức **equals()**, **hashCode()** hoặc **toString()**, hãy tạo một nhóm benchmark riêng có gọi chúng theo cùng tần suất. Không trộn chi phí đó vào phép đo chỉ tạo và lưu kết quả.

## 7. Dùng JFR để tìm nguồn allocation trong pipeline

JFR phù hợp để quan sát ứng dụng đang chạy và xác định allocation đến từ đâu. Với workload đại diện, tạo recording ngắn bằng cấu hình **profile**:

~~~bash
java -XX:StartFlightRecording=filename=stream-allocation.jfr,settings=profile,duration=3m -jar app.jar
~~~

Chạy các request hoặc tác vụ sử dụng pipeline trong thời gian recording. Sau khi recording kết thúc, kiểm tra tổng quan:

~~~bash
jfr summary stream-allocation.jfr
~~~

Lọc allocation sample và stack trace:

~~~bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 32 stream-allocation.jfr
~~~

Khi đọc event, tập trung vào:

| Field | Cách dùng |
| --- | --- |
| **objectClass** | Xác định object được lấy mẫu, ví dụ LineAmount, LineAmountClass, byte[] hoặc class nội bộ của Stream |
| **weight** | Ước lượng lượng cấp phát được đại diện bởi mẫu |
| **eventThread** | Xác định request thread, worker hoặc scheduler thực hiện pipeline |
| **stackTrace** | Truy ngược tới mapper, method ứng dụng và đường gọi nghiệp vụ |
| **startTime** | Đối chiếu với thời điểm workload được chạy |

Weight là trọng số thống kê, không phải kích thước chính xác của object trong event. Không lấy số event làm số object đã tạo và không dùng một recording ngắn để kết luận chênh lệch nhỏ là có ý nghĩa.

### Nhận diện allocation từ pipeline

Trong stack trace, có thể thấy:

- Frame ứng dụng ở mapper tạo **LineAmount** hoặc **LineAmountClass**.
- Các frame của thư viện Stream liên quan tới stage trung gian.
- Các frame tạo collection hoặc array cho kết quả terminal operation.
- Các frame xử lý dữ liệu khác như format chuỗi hoặc sao chép buffer.

Tên class nội bộ của Stream là chi tiết implementation, có thể thay đổi giữa các JDK. Hãy dùng chúng để hiểu recording cụ thể, không gắn logic ứng dụng vào tên class nội bộ.

Nếu JFR cho thấy **LineAmount** có weight lớn, điều đó có thể phản ánh số lượng kết quả record được tạo theo yêu cầu. Chuyển từ **flatMap()** sang **mapMulti()** không loại bỏ các record đầu ra này. Lợi ích tiềm năng nằm ở các object phụ trợ của pipeline, không phải ở số kết quả nghiệp vụ.

## 8. Dùng JDK Mission Control để phân tích stack allocation

Mở file **stream-allocation.jfr** bằng JDK Mission Control (JMC). Tùy phiên bản JMC, tên trang và bố cục có thể khác nhau. Hãy tập trung vào các góc nhìn allocation và method profiling:

1. Xem allocation theo class để tìm nhóm object có weight lớn.
2. Mở stack trace hoặc allocation profile để xác định method tạo object.
3. Tách kết quả theo thread nếu nhiều workload chạy đồng thời.
4. Chọn khoảng thời gian tương ứng với request hoặc tác vụ đang so sánh.
5. Đối chiếu với GC và latency trong cùng recording.

Nếu JMC hiển thị sample count và allocation weight ở các góc nhìn khác nhau, hãy xác định rõ đang xem chỉ số nào. Số mẫu không phải số byte. Khi cần kiểm tra field **weight** của event, dùng event details hoặc **jfr print** trên file recording.

Một recording chứa cả hai phiên chạy chỉ hữu ích nếu có thể xác định rõ khoảng thời gian từng phiên và workload tương ứng. Để so sánh rõ ràng, nên ghi riêng từng biến thể hoặc gắn mốc thời gian và workload có thể phân biệt.

## 9. Dùng JMH để đo allocation trên mỗi thao tác

JFR sampling phù hợp để tìm nguồn allocation trong ứng dụng thực tế. Khi muốn so sánh ba phương án nhỏ như **flatMap()**, **mapMulti()** và record/class, dùng JMH với GC profiler để đo lượng allocation chuẩn hóa trên mỗi operation.

JMH có profiler **gc**. Chỉ số **gc.alloc.rate.norm** biểu diễn lượng cấp phát được chuẩn hóa theo operation, thường hiển thị bằng B/op. Đây là phép đo phù hợp hơn để so sánh allocation trên mỗi lần chạy benchmark so với việc lấy số event JFR chia thủ công.

Ví dụ lệnh chạy benchmark:

~~~bash
java -jar target/benchmarks.jar ".*AllocationBenchmark.*" -prof gc -f 3 -wi 5 -i 8
~~~

Trong đó:

- **-prof gc** bật GC profiler.
- **-f 3** chạy ba fork JVM độc lập.
- **-wi 5** chạy năm vòng warmup.
- **-i 8** chạy tám vòng đo.

Hãy so sánh cột **gc.alloc.rate.norm** giữa các benchmark. Thời gian chạy và throughput cũng cần được xem cùng nhau; một phương án giảm allocation nhưng làm chậm xử lý có thể không phù hợp.

### Nguyên tắc thiết kế benchmark

- Chuẩn bị input trong **@Setup(Level.Trial)** để không tính chi phí tạo fixture vào phép đo.
- Dùng cùng dữ liệu, số đơn hàng, số dòng và phân bố quantity cho mọi benchmark.
- Đưa mỗi phương án vào một method có **@Benchmark** riêng.
- Trả về kết quả hoặc dùng **Blackhole** để JMH không loại bỏ công việc không được quan sát.
- Dùng warmup và nhiều fork để giảm ảnh hưởng của khởi động JVM.
- Không tạo recording JFR cùng một file cho nhiều fork benchmark; mỗi fork có thể ghi đè file hoặc làm lẫn dữ liệu. Dùng JMH GC profiler cho phép đo B/op và chạy JFR riêng khi cần stack trace trong workload.
- Không dùng **System.nanoTime()** tự viết vòng lặp làm benchmark thay thế JMH.

Một skeleton benchmark có thể tổ chức như sau:

~~~java
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
@State(Scope.Thread)
public class AllocationBenchmark {
    private List<Order> orders;

    @Param({"100", "1000"})
    public int orderCount;

    @Param({"4", "16"})
    public int linesPerOrder;

    @Setup(Level.Trial)
    public void setup() {
        orders = createOrders(orderCount, linesPerOrder);
    }

    @Benchmark
    public List<LineAmount> flatMapRecord() {
        return calculateWithFlatMap(orders);
    }

    @Benchmark
    public List<LineAmount> mapMultiRecord() {
        return calculateWithMapMulti(orders);
    }

    @Benchmark
    public List<LineAmountClass> mapMultiClass() {
        return calculateWithClass(orders);
    }
}
~~~

Các record, class và hàm **createOrders()**, **calculateWithFlatMap()**, **calculateWithMapMulti()**, **calculateWithClass()** được đặt trong cùng project benchmark; các hàm helper có thể là static method trong **AllocationBenchmark** hoặc một utility class cùng package. Cần thêm dependency và cấu hình build JMH theo hướng dẫn của dự án JMH.

**@State(Scope.Thread)** tạo state riêng cho mỗi benchmark thread. Input được dựng ở setup và không thay đổi trong phép đo. Mỗi benchmark trả về List để kết quả được JMH tiêu thụ.

Nếu ứng dụng chạy song song trong production, hãy tạo benchmark riêng cho workload song song sau khi đã đo được baseline tuần tự. Không gộp khác biệt về parallelism vào phép so sánh ban đầu giữa hai phép biến đổi.

## 10. Đọc kết quả và tránh kết luận sai

Giả sử JMH cho kết quả minh họa:

| Benchmark | gc.alloc.rate.norm |
| --- | ---: |
| flatMapRecord | 18.4 KB/op |
| mapMultiRecord | 15.7 KB/op |
| mapMultiClass | 15.8 KB/op |

Đây là số giả định để minh họa cách đọc, không phải kết quả đo thực tế. Có thể nhận xét:

- Trong workload này, **mapMultiRecord** có allocation/op thấp hơn **flatMapRecord**.
- **mapMultiClass** gần với **mapMultiRecord**, nên mô hình record không tạo ra khác biệt allocation đáng kể trong phép đo này.
- Chênh lệch giữa record và class cần được kiểm tra qua nhiều fork và khoảng tin cậy trước khi đưa ra quyết định.
- Nếu kết quả thay đổi theo số dòng mỗi đơn hàng, số lượng đầu ra trên mỗi input có thể ảnh hưởng tới hiệu quả của mapMulti.

Khi kết hợp JFR và JMH:

| Công cụ | Câu hỏi trả lời tốt |
| --- | --- |
| JFR **ObjectAllocationSample** | Allocation trong ứng dụng đến từ class, thread và stack trace nào? |
| JMC | Hot spot phân bố theo class, method và thời gian ra sao? |
| JMH **-prof gc** | Mỗi operation của từng phương án cấp phát bao nhiêu byte theo benchmark? |
| JMH timing/throughput | Phương án nào xử lý nhanh hơn trong cấu hình benchmark? |

Không dùng JFR sample count làm số byte/op. Không dùng JMH microbenchmark đơn lẻ để kết luận toàn bộ ứng dụng production sẽ nhanh hơn. Cần đo lại trên workload gần với thực tế.

## 11. Quy trình so sánh trong dự án

Có thể áp dụng quy trình sau khi tối ưu một pipeline:

1. Xác định pipeline đang xử lý một-nhiều và số kết quả trung bình trên mỗi phần tử đầu vào.
2. Ghi JFR với workload đại diện để tìm class và stack trace allocation nổi bật.
3. Tạo hai implementation **flatMap()** và **mapMulti()** với cùng input, filter, phép tính và output.
4. Dùng cùng kiểu record kết quả để cô lập khác biệt của phép biến đổi.
5. Chạy JMH với GC profiler để đo B/op và thời gian xử lý.
6. Tạo benchmark riêng để so sánh record với class bất biến có cùng field và cách sử dụng.
7. Đối chiếu JFR để biết allocation đến từ Stream stage, record kết quả hay collection đầu ra.
8. Kiểm tra tính đúng đắn của kết quả, thứ tự, số phần tử và các trường hợp đầu vào rỗng.
9. Chạy lại với workload đại diện và so sánh allocation, GC, throughput cùng latency.
10. Chỉ giữ thay đổi khi lợi ích đo được phù hợp với độ rõ ràng và khả năng bảo trì của code.

Nếu mỗi order thường tạo hàng nghìn kết quả, **flatMap()** có thể vẫn là cách biểu đạt dễ đọc hơn. Nếu mỗi order chỉ phát ra vài kết quả hoặc không phát ra kết quả, **mapMulti()** đáng để thử. Kết quả đo trên workload thật mới quyết định lựa chọn.

## 12. Kết luận

**mapMulti()** và **flatMap()** đều hỗ trợ biến đổi một phần tử thành nhiều phần tử. **mapMulti()** có thể phù hợp khi mỗi phần tử đầu vào phát ra số lượng nhỏ kết quả, nhưng hiệu quả allocation phụ thuộc implementation và workload. Record giúp mô hình hóa dữ liệu đầu ra gọn gàng, nhưng không tự động loại bỏ allocation hoặc bảo đảm ít bộ nhớ hơn class tương đương.

Dùng JFR để tìm class và stack trace tạo allocation trong ứng dụng. Dùng JMH **-prof gc** để đo B/op trên từng operation trong benchmark có warmup, nhiều fork và input được chuẩn bị công bằng. So sánh riêng phép biến đổi Stream và mô hình dữ liệu, sau đó xác nhận bằng workload đại diện cùng các chỉ số GC, throughput và latency.

## Tài liệu tham khảo

- [Stream.mapMulti() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer))
- [Stream — Java SE 16 API Specification](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [JEP 395: Records](https://openjdk.org/jeps/395)
- [Record — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html)
- [JLS 27 — Record Classes (Section 8.10)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10)
- [JFR Diagnostic Tools — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [OpenJDK JMH — Profilers Sample 35](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java)


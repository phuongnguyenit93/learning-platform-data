# Phân biệt tối ưu JIT với cam kết ngữ nghĩa của ngôn ngữ và API

JIT compiler có thể biến đổi mã Java để chương trình chạy nhanh hơn: inline phương thức, tính trước biểu thức, loại bỏ allocation không cần thiết hoặc tối ưu khóa đồng bộ. Những biến đổi này là chi tiết triển khai của JVM. Chúng phải giữ nguyên hành vi mà chương trình được phép quan sát theo đặc tả ngôn ngữ Java, Java Memory Model và hợp đồng của API.

Điểm cần nhớ là **hiệu năng có thể thay đổi giữa các JVM, phiên bản JDK và workload; ngữ nghĩa mà chương trình dựa vào phải ổn định theo hợp đồng**. Một object có thể được JIT loại bỏ allocation vật lý nếu identity của nó không thể quan sát, nhưng chương trình không được dựa vào việc allocation luôn bị loại bỏ. Một phương thức có thể được inline trong một lần chạy, nhưng code không được giả định nó luôn inline.

Bài học này phân biệt những gì Java bảo đảm với những gì HotSpot có thể tối ưu, giải thích cách các tối ưu hóa phổ biến hoạt động và hướng dẫn kiểm chứng hiệu năng mà không biến chi tiết JIT thành yêu cầu correctness.

## 1. Ba lớp hợp đồng cần phân biệt

Khi phân tích một hành vi runtime, hãy xác định nó thuộc lớp nào:

| Lớp | Nội dung | Ví dụ |
| --- | --- | --- |
| Ngữ nghĩa ngôn ngữ Java | Quy tắc được đặc tả bởi JLS và Java Memory Model | Kiểu dữ liệu, overflow số nguyên, toán tử ==, synchronized, volatile |
| Hợp đồng Java API | Hành vi mà thư viện công bố qua API specification | Thứ tự của List, tính bất biến của String, semantics của Stream |
| Chi tiết triển khai JVM | Cách một JVM hiện thực và tối ưu chương trình | Inlining, escape analysis, scalar replacement, deoptimization |

Hai lớp đầu xác định chương trình được phép dựa vào điều gì. Lớp thứ ba có thể thay đổi theo JVM, JDK, kiến trúc CPU, profile thực thi và cấu hình.

HotSpot là một implementation phổ biến, nhưng đặc tả Java không yêu cầu mọi JVM phải dùng cùng thuật toán JIT hoặc thực hiện cùng một tối ưu hóa. Khi chuyển JVM hoặc nâng cấp JDK, code đúng theo JLS và API vẫn phải giữ hành vi; hiệu năng có thể khác và cần được đo lại.

## 2. Nguyên tắc cốt lõi: tối ưu phải giữ hành vi có thể quan sát

Compiler và JVM được phép thay đổi cách thực hiện nếu kết quả quan sát được vẫn phù hợp với đặc tả. Điều này thường được mô tả bằng nguyên tắc *as-if*: implementation có thể sắp xếp lại, gộp hoặc loại bỏ công việc khi những thay đổi đó không làm sai hành vi mà chương trình được phép quan sát.

Trong một luồng đơn, điều này có nghĩa phép tính và side effect có thể quan sát phải giữ đúng ngữ nghĩa Java. Trong chương trình đa luồng, còn phải tuân theo Java Memory Model: các quy tắc về data race, synchronization order và happens-before quyết định những quan sát nào được bảo đảm.

JIT không phải bộ dịch từng dòng Java thành một chỉ thị máy cố định. Nó có thể:

- Gộp các phép tính tương đương.
- Loại bỏ code không ảnh hưởng kết quả.
- Inline lời gọi phương thức.
- Đưa một số giá trị vào register thay vì giữ object trên heap.
- Loại bỏ khóa không thể được thread khác quan sát.
- Tối ưu dựa trên profile rồi hủy tối ưu khi giả định không còn đúng.

Những việc này chỉ hợp lệ nếu các bảo đảm ngôn ngữ và API vẫn được giữ.

## 3. Các tối ưu hóa JIT phổ biến và giới hạn của chúng

### Constant folding và dead-code elimination

Nếu giá trị của một biểu thức được xác định an toàn, compiler có thể tính trước kết quả. Nếu kết quả của một phép tính không được sử dụng và phép tính không có side effect có thể quan sát, JIT có thể loại bỏ nó.

~~~java
static int calculate() {
    int taxRate = 10;
    int total = 100 * taxRate;
    return total;
}
~~~

JIT có thể thay biểu thức bằng kết quả tương đương. Code không được dựa vào việc một phép tính vô ích vẫn tiêu tốn CPU.

Tuy nhiên, một biểu thức có side effect hoặc có thể ném exception không thể bị loại bỏ tùy tiện nếu điều đó làm thay đổi hành vi được bảo đảm.

Ví dụ, phép chia cho 0 có thể ném **ArithmeticException**; compiler không thể đơn giản xóa phép chia đó nếu việc ném exception là hành vi quan sát được của chương trình.

### Method inlining

Inlining thay lời gọi phương thức bằng phần thân phương thức tại call site. Nó có thể giảm chi phí gọi hàm và mở đường cho các tối ưu hóa tiếp theo như constant folding hoặc dead-code elimination.

~~~java
final class Price {
    int withTax(int amount) {
        return amount * 110 / 100;
    }
}

static int total(Price price, int amount) {
    return price.withTax(amount);
}
~~~

HotSpot có thể inline **withTax()** nếu phương thức và call site phù hợp với heuristic của compiler. Nhưng không có cam kết rằng một phương thức cụ thể luôn được inline. Kích thước method, profile, mức độ nóng, kiểu lời gọi và giới hạn compiler đều có thể ảnh hưởng quyết định.

Không viết code chỉ để ép inline bằng cách tách hoặc gộp method dựa trên giả định cố định. Hãy đo trên runtime và workload mục tiêu.

### Escape analysis và scalar replacement

Escape analysis phân tích object có thoát khỏi phạm vi mà compiler đang xét hay không. Nếu object không thoát và identity của nó không thể được quan sát, JIT có thể thay object bằng các giá trị thành phần, thường được gọi là *scalar replacement*.

~~~java
record Point(int x, int y) {}

static int sum(int x, int y) {
    Point point = new Point(x, y);
    return point.x() + point.y();
}
~~~

Trong ví dụ này, **Point** chỉ được dùng để đọc hai component và không được trả ra ngoài. Nếu JIT inline accessor và chứng minh object không escape, nó có thể giữ **x** và **y** như các giá trị riêng, không cần tạo object trên heap.

Điều đó không có nghĩa record luôn miễn phí. Nếu object được lưu vào collection, trả về caller hoặc được chia sẻ qua một đường code mà compiler không thể phân tích, allocation có thể vẫn cần thiết. Kết quả còn phụ thuộc vào JIT, mức độ inline và cấu trúc chương trình.

Không dựa vào việc allocation sẽ bị loại bỏ để thiết kế correctness hoặc kiểm soát bộ nhớ. Nếu chương trình cần object tồn tại như một giá trị có identity quan sát được, nó phải hoạt động đúng ngay cả khi JVM thực hiện allocation thực tế.

### Lock elimination và lock coarsening

Nếu JIT chứng minh object khóa không thể được thread khác truy cập, nó có thể loại bỏ một số thao tác monitor vì đồng bộ hóa đó không thể tạo ra tương tác liên luồng có thể quan sát.

~~~java
static int calculate() {
    Object lock = new Object();

    synchronized (lock) {
        return 42;
    }
}
~~~

Object khóa được tạo và dùng cục bộ; nếu nó không escape, thread khác không thể lấy cùng monitor. Trong trường hợp compiler chứng minh được điều này, HotSpot có thể loại bỏ allocation và thao tác khóa.

JIT cũng có thể gộp các vùng khóa liền kề trên cùng monitor khi việc gộp không làm thay đổi hành vi đồng bộ được quan sát.

Điều này không cho phép bỏ **synchronized** khỏi giao thức bảo vệ trạng thái dùng chung. Nếu thread khác có thể lấy cùng khóa, monitor và quan hệ happens-before vẫn là một phần ngữ nghĩa chương trình phải giữ.

### Speculative optimization và deoptimization

JIT có thể dùng profile runtime để tối ưu một call site. Ví dụ, nếu một lời gọi interface trong thời gian dài chỉ nhận một implementation, compiler có thể giả định call site đang có một kiểu đích phổ biến và inline implementation đó kèm guard.

Nếu về sau một implementation khác xuất hiện, guard có thể thất bại. JVM có thể deoptimize mã đã biên dịch và quay lại mức thực thi khác để tiếp tục với ngữ nghĩa đúng.

Do đó:

- Một tối ưu hóa có thể xuất hiện trong workload này nhưng không xuất hiện trong workload khác.
- Mã đã tối ưu có thể bị hủy tối ưu khi profile thay đổi.
- Thời điểm compilation và deoptimization không phải hợp đồng của Java.
- Không suy ra correctness từ việc một call site hiện tại chỉ có một implementation.

## 4. JIT phải giữ ngữ nghĩa của kiểu dữ liệu và phép toán Java

Tối ưu hóa không được thay quy tắc kiểu dữ liệu Java bằng giả định toán học hoặc quy tắc của CPU.

Ví dụ, phép cộng **int** có overflow theo biểu diễn số nguyên 32-bit của Java:

~~~java
int value = Integer.MAX_VALUE;
int next = value + 1;

System.out.println(next); // -2147483648
~~~

JIT phải giữ kết quả theo ngữ nghĩa Java. Không được giả định rằng **value + 1** luôn lớn hơn **value** như số nguyên toán học không giới hạn.

Nếu ứng dụng cần phát hiện overflow, dùng API có hợp đồng rõ ràng:

~~~java
int next = Math.addExact(value, 1);
~~~

Phương thức này ném **ArithmeticException** khi phép cộng overflow.

Tương tự, cần giữ đúng khác biệt giữa equality và identity:

~~~java
record Point(int x, int y) {}

Point first = new Point(2, 3);
Point second = new Point(2, 3);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

Record có equality mặc định dựa trên component, nhưng hai lần **new** vẫn tạo hai object có identity riêng theo ngữ nghĩa Java. JIT có thể loại bỏ allocation nội bộ nếu identity không thể được quan sát; nó không được làm **==** trả về **true** trong tình huống trên.

Đây là lý do không nên suy luận rằng record là value type hoặc mọi record có thể được JVM gộp thành cùng một object.

## 5. Java Memory Model vẫn là giới hạn của tối ưu hóa đa luồng

JIT có quyền tối ưu nhưng phải tuân theo Java Memory Model (JMM). Đặc biệt, các thao tác **volatile** và **synchronized** tạo ra những bảo đảm về visibility và ordering.

### volatile và happens-before

~~~java
class Signal {
    private int data;
    private volatile boolean ready;

    void publish() {
        data = 42;
        ready = true;
    }

    int read() {
        if (ready) {
            return data;
        }
        return -1;
    }
}
~~~

Nếu một thread ghi **ready = true** và thread khác đọc được giá trị **true** đó, volatile write happens-before volatile read tương ứng. Vì vậy, thread đọc sẽ thấy cập nhật **data = 42** được thực hiện trước volatile write.

Ví dụ này giả định dữ liệu được publish một lần: writer ghi **data** rồi ghi **ready**, reader chỉ đọc dữ liệu sau khi thấy **ready == true** từ lần publish đó. Nếu có nhiều lần cập nhật hoặc nhiều writer, cần thiết kế giao thức đồng bộ phù hợp thay vì chỉ thêm một cờ volatile.

JIT không được sắp xếp lại các thao tác theo cách phá vỡ bảo đảm happens-before này.

### synchronized và monitor

~~~java
class Counter {
    private final Object lock = new Object();
    private int value;

    void increment() {
        synchronized (lock) {
            value++;
        }
    }

    int value() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Cả đọc và ghi dùng cùng monitor. Một lần unlock monitor happens-before một lần lock tiếp theo trên cùng monitor. JIT có thể tối ưu cách thực thi vùng synchronized khi chứng minh được an toàn, nhưng không thể phá vỡ hành vi đồng bộ mà chương trình dựa vào.

Không kiểm thử visibility bằng cách chèn **Thread.sleep()** hoặc giả định scheduler sẽ chạy thread theo một thứ tự nhất định. Hãy dùng concurrency test có đồng bộ rõ ràng và thiết kế theo JMM.

## 6. Hợp đồng API cũng giới hạn điều chương trình được phép giả định

Không phải mọi hành vi mà ta quan sát được trong một lần chạy đều là cam kết của API. Thư viện có thể tối ưu nội bộ miễn vẫn tuân thủ hợp đồng được công bố.

### Ví dụ Stream: peek không phải nơi thực hiện side effect bắt buộc

~~~java
long count = List.of("A", "B", "C").stream()
    .peek(System.out::println)
    .count();
~~~

Không được dựa vào việc đoạn code này luôn in đủ ba phần tử. API Stream cho phép implementation bỏ qua một số stage hoặc behavioral parameter nếu có thể tính kết quả mà không cần thực thi chúng và việc đó không ảnh hưởng kết quả cuối. Với nguồn có kích thước đã biết và pipeline không đổi số lượng phần tử, **count()** có thể được tính trực tiếp mà không duyệt từng phần tử; khi đó action trong **peek()** có thể không chạy.

Nếu cần thực hiện side effect cho từng phần tử, dùng terminal operation có hợp đồng phù hợp, chẳng hạn:

~~~java
List.of("A", "B", "C").stream()
    .forEach(System.out::println);
~~~

Với parallel stream, **forEach()** không bảo đảm thứ tự. Nếu cần giữ encounter order của stream, dùng **forEachOrdered()** và cân nhắc chi phí của việc duy trì thứ tự.

Điểm quan trọng: đây là quyền tối ưu được ghi trong hợp đồng Stream API, không nhất thiết là một tối ưu JIT. Phải đọc cả API specification lẫn hành vi compiler.

### Thứ tự collection phải dựa vào interface và implementation contract

**List** là sequence có encounter order; **HashSet** và **HashMap** không cam kết thứ tự iteration ổn định. Nếu ứng dụng cần thứ tự, hãy chọn collection có hợp đồng phù hợp hoặc sắp xếp rõ ràng.

Không dựa vào thứ tự tình cờ quan sát được từ một lần chạy HashMap. Nó có thể thay đổi khi kích thước map, hash, JDK hoặc implementation thay đổi.

### API timing không cam kết lịch thực thi chính xác

**Thread.sleep()** yêu cầu thread tạm ngừng trong khoảng thời gian chỉ định, nhưng thời điểm thread thực sự tiếp tục phụ thuộc độ chính xác của timer và scheduler; nó không bảo đảm thread chạy lại đúng thời điểm đó. **System.gc()** chỉ là yêu cầu JVM cố gắng thực hiện garbage collection, không bảo đảm một đợt GC cụ thể sẽ diễn ra ngay.

Nếu cần đo thời gian đã trôi qua, dùng **System.nanoTime()** để đo khoảng thời gian đơn điệu thay vì dựa vào thời gian lịch. Nếu cần đồng bộ, dùng các API concurrency có hợp đồng phù hợp thay vì dựa vào timing.

## 7. Phân biệt cam kết với quan sát implementation

Bảng sau giúp tránh biến chi tiết quan sát được thành giả định của ứng dụng:

| Quan sát trong một lần chạy | Điều được bảo đảm? | Cách viết code đúng |
| --- | --- | --- |
| Method được inline | Không | Viết method rõ ràng; đo nếu call overhead thực sự quan trọng |
| Record allocation bị loại bỏ | Không | Code vẫn phải đúng khi object được tạo thực tế |
| Một object local được scalar-replace | Không | Không phụ thuộc allocation elimination |
| Khóa local bị loại bỏ | Không | Bảo vệ trạng thái chia sẻ bằng giao thức khóa đúng |
| Stream **peek()** được gọi cho mọi phần tử trước **count()** | Không | Không đặt side effect bắt buộc trong intermediate operation |
| HashMap lặp theo cùng thứ tự trong test | Không | Dùng collection có thứ tự nếu thứ tự là yêu cầu |
| **volatile** write được nhìn thấy theo happens-before | Có, theo JMM khi điều kiện đọc/ghi tương ứng thỏa mãn | Dùng volatile đúng mục đích |
| **synchronized** bảo vệ vùng tới hạn và visibility | Có, theo JMM nếu các thread dùng cùng monitor | Đồng bộ nhất quán mọi đường truy cập |
| **int** overflow theo quy tắc Java | Có | Dùng **Math.addExact** nếu cần phát hiện overflow |
| **List** duy trì encounter order | Có theo hợp đồng List | Dùng List khi thứ tự là một phần yêu cầu |

## 8. Không dùng CompileCommand để thay đổi correctness

CompileCommand có thể yêu cầu HotSpot inline, không inline hoặc loại một phương thức khỏi compilation. Những lệnh đó phục vụ chẩn đoán và thử nghiệm compiler; chúng không phải cách sửa lỗi logic hoặc thay thế đồng bộ đúng.

Ví dụ:

~~~bash
java -XX:CompileCommand=dontinline,com/example/OrderService.calculate -jar app.jar
~~~

Lệnh này có thể thay đổi profile hiệu năng. Nếu lỗi dữ liệu biến mất khi bật **dontinline**, điều đó không chứng minh lỗi đã được sửa. Nó có thể làm thay đổi timing và che một race condition hoặc lỗi phụ thuộc thứ tự thực thi.

Khi một lỗi chỉ xuất hiện ở chế độ JIT hoặc biến mất khi thay đổi compilation, hãy:

1. Xác minh code có data race hoặc phụ thuộc vào timing không.
2. Kiểm tra JMM và các đường truy cập shared state.
3. Tạo test tái hiện có synchronization rõ ràng.
4. Thu thập JFR, compilation log hoặc thread dump nếu cần.
5. So sánh interpreter/JIT chỉ như công cụ khoanh vùng, không làm chuẩn correctness.
6. Báo lỗi JVM/compiler nếu có reproducer tối thiểu và bằng chứng đặc tả bị vi phạm.

Không giữ CompileCommand chẩn đoán trong production chỉ để che một lỗi chưa hiểu nguyên nhân.

## 9. Đo hiệu năng mà không nhầm với hợp đồng

JIT tối ưu dựa trên runtime profile. Một benchmark quá ngắn có thể kết thúc trước khi code đạt trạng thái steady state. Benchmark tự viết bằng vòng lặp và **System.nanoTime()** cũng dễ bị dead-code elimination, constant folding, warm-up và nhiễu từ hệ thống làm sai lệch kết quả.

Dùng JMH cho microbenchmark:

- Có warm-up để JVM đạt trạng thái tối ưu phù hợp.
- Có nhiều fork để giảm ảnh hưởng trạng thái JVM trước đó.
- Dùng input đủ đa dạng, tránh benchmark chỉ đo một hằng số.
- Trả về kết quả hoặc dùng **Blackhole** để công việc không bị loại bỏ ngoài ý muốn.
- Dùng profiler phù hợp như **-prof gc** khi cần đo allocation.
- Không suy rộng một microbenchmark thành kết luận hiệu năng của toàn ứng dụng.

Dùng JFR để quan sát ứng dụng hoặc workload tích hợp:

- **jdk.ExecutionSample** hỗ trợ tìm method tiêu thụ CPU.
- **jdk.ObjectAllocationSample** hỗ trợ tìm allocation hot spot theo class và stack trace.
- GC events giúp xem hoạt động thu gom.
- Compilation events và compilation log hỗ trợ xem hoạt động JIT.

JFR cũng có overhead và sampling limits; cần chọn cấu hình phù hợp và đo lại trên workload đại diện.

## 10. Quy trình phân tích một tối ưu JIT

Khi muốn biết JIT có cải thiện một đường code hay không, hãy đi theo trình tự:

1. Xác định yêu cầu ngữ nghĩa từ JLS, JMM và API specification.
2. Viết test kiểm tra kết quả, exception, equality, thứ tự và concurrency behavior cần bảo đảm.
3. Tạo baseline benchmark bằng JMH hoặc workload tích hợp.
4. Thu JFR để xác định method, allocation và GC có liên quan.
5. Kiểm tra compilation bằng JFR, **PrintCompilation**, compilation log hoặc công cụ phù hợp.
6. Nếu thử CompileCommand, ghi rõ đó là cấu hình chẩn đoán và chỉ thay đổi một yếu tố mỗi lần.
7. Chạy lại benchmark với cùng JDK, CPU, heap, input và warm-up.
8. Kiểm tra kết quả correctness độc lập với kết quả hiệu năng.
9. Đánh giá trên JDK mục tiêu và lặp lại nếu kết quả dao động.
10. Loại bỏ cấu hình chẩn đoán nếu không còn lý do vận hành cụ thể để giữ lại.

Một tối ưu chỉ đáng giữ khi có lợi ích đo được, không phá hợp đồng và không làm code khó bảo trì hơn mức cần thiết.

## 11. Những giả định nên tránh

- Không giả định một method luôn được inline.
- Không giả định object local luôn được scalar-replace hoặc không chiếm heap.
- Không giả định JIT sẽ sửa một data race hoặc làm code thiếu synchronization trở nên an toàn.
- Không dựa vào thứ tự iteration không được API bảo đảm.
- Không đặt side effect bắt buộc trong **peek()** hoặc intermediate Stream operation có thể bị elide.
- Không coi số sample JFR là số lần thực thi hoặc allocation chính xác.
- Không dùng CompileCommand để che lỗi correctness.
- Không suy ra hiệu năng production chỉ từ một microbenchmark.
- Không phụ thuộc tên class nội bộ, assembly hoặc heuristic của một phiên bản HotSpot như một phần hợp đồng ứng dụng.

## 12. Kết luận

JIT có quyền thay đổi cách thực thi để tăng hiệu năng, nhưng phải giữ hành vi được bảo đảm bởi ngôn ngữ Java, Java Memory Model và hợp đồng API. Inlining, escape analysis, scalar replacement, lock elimination và speculative optimization là các cơ chế implementation; chúng có thể xuất hiện hoặc biến mất theo JDK, JVM và workload.

Hãy viết code dựa trên hợp đồng: kiểu dữ liệu, identity, overflow, happens-before, thứ tự collection và semantics của API. Dùng JFR, JMH và compilation log để quan sát, đo lường và giải thích hiệu năng. Không biến một tối ưu JIT đã quan sát trong một lần chạy thành giả định correctness của chương trình.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html)
- [Java Language Specification, Java SE 27 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html)
- [Java Language Specification, Java SE 27 — Integer Operations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html)
- [Stream Package Specification — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html)
- [Stream.count() — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html#count())
- [Stream.peek() — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer))
- [JEP 165: Compiler Control](https://openjdk.org/jeps/165)
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)
- [JDK Mission Control — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)


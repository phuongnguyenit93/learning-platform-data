# Phân biệt biến đổi của javac với tối ưu hóa của JVM

Khi biên dịch Java, chúng ta thường thấy một chuỗi xử lý tưởng như đơn giản: `.java` → `javac` → `.class` → `java`. Tuy nhiên, có **hai thời điểm biến đổi chương trình rất khác nhau**. `javac` xử lý mã nguồn và tạo bytecode trước khi chạy. JVM tiếp nhận bytecode rồi có thể diễn giải hoặc biên dịch một số phần thành **mã máy được tối ưu theo dữ liệu chạy thực tế**, thường thông qua trình biên dịch JIT (Just-In-Time).

Sự khác biệt này giải thích vì sao cấu trúc Java cấp cao không còn hiện nguyên dạng trong `javap`, vì sao chạy chương trình lâu có thể nhanh hơn giai đoạn đầu, vì sao JVM có thể tối ưu khác nhau trên hai máy dù dùng cùng tệp `.class`, và vì sao không nên kết luận có JIT optimization chỉ từ việc quan sát bytecode.

Bài học thuộc nhóm **Biến đổi mã** của `Java Advance - compilation`. Mục tiêu là phân định trách nhiệm, đầu vào, đầu ra, khả năng quan sát và giới hạn của `javac` so với JVM/JIT. Ví dụ dùng Java 17+; chi tiết về tiered compilation, C1/C2 và một số cờ chẩn đoán nói đến **HotSpot** trong OpenJDK/JDK phổ biến, không mặc định áp dụng cho mọi JVM.

## 1. Một chương trình, hai lớp xử lý

~~~text
           THỜI ĐIỂM BIÊN DỊCH
 Mã nguồn .java + classpath/module path + options
                       │
                       ▼
      javac: parse / kiểm tra ngữ nghĩa
                       │
                       ▼
    javac: desugar / lower / sinh bytecode
                       │
                       ▼
                   .class
                       │
         ──────────────┼──────────────
                       │
           THỜI ĐIỂM CHẠY
                       ▼
       JVM: nạp, kiểm tra, liên kết class
                       │
                       ▼
             Interpreter / JIT
                       │
            profiling / hot code
                       │
                       ▼
            machine code tối ưu
                       │
                       ▼
       CPU thực thi hành vi chương trình
~~~

Đây là sơ đồ khái niệm. JVM có thể bắt đầu diễn giải rồi biên dịch thành mã máy; các quyết định được lặp lại, nâng cấp hoặc thu hồi khi chạy. Một số JVM có chiến lược khác HotSpot, còn các bước như garbage collection hoạt động song song với thực thi. Không có một đường thẳng cố định buộc mọi method đều phải qua đúng từng khối trong sơ đồ.

So sánh nhanh:

| Câu hỏi | `javac` | JVM / JIT |
| --- | --- | --- |
| **Khi nào?** | Trước khi chạy, ở quá trình biên dịch nguồn | Khi nạp và thực thi class, tùy JVM |
| **Đầu vào chính?** | Java source, dependency, option compiler | Bytecode, runtime classes, dữ liệu profiling và môi trường CPU |
| **Đầu ra chính?** | Các tệp `.class` (bytecode + metadata) | Thực thi chương trình; có thể tạo machine code trong bộ nhớ |
| **Mục tiêu?** | Đúng ngữ nghĩa Java, dạng class file tương thích | Chạy bytecode đúng ngữ nghĩa và nâng hiệu năng runtime |
| **Biết trước dữ liệu chạy thật?** | Thông thường không | Có thể quan sát call counts, branch frequencies, type profiles... |
| **Công cụ quan sát?** | `javap`, `javac -verbose`, kiểm tra class file | JFR, JIT logs, JITWatch, profiler, tùy chọn JVM |
| **Tệp `.class` có đổi khi JIT chạy?** | Được tạo hoặc thay đổi khi biên dịch lại | Thông thường không; JIT code nằm trong bộ nhớ của JVM |

**Điểm cốt lõi:** không đồng nhất **“javac đã hạ cấu trúc nguồn”** với **“JVM đã tối ưu tốc độ chạy”**. Một chuyển đổi của compiler có thể giúp runtime tối ưu về sau, nhưng đó vẫn là hai trách nhiệm khác nhau.

## 2. Những gì javac làm trước khi chương trình chạy

`javac` phải tạo ra biểu diễn có thể thực thi theo quy tắc Java. Ở mức tổng quan, công việc gồm:

1. Đọc source, token hóa và parse thành cây cú pháp.
2. Ghi nhận khai báo, phân giải tên, kiểm tra kiểu, access, overload, definite assignment và các ràng buộc khác.
3. Chạy annotation processors khi được cấu hình; processor có thể sinh thêm nguồn hoặc metadata, không đồng nghĩa với JIT.
4. Chuyển các cấu trúc ngôn ngữ cấp cao sang biểu diễn phù hợp cho JVM.
5. Phát sinh class file chứa bytecode, constant pool và metadata cần thiết.

Bước 4 thường gọi **desugaring/lowering**. Một cấu trúc ngôn ngữ không nhất thiết có instruction JVM tương ứng trực tiếp; compiler phải biểu diễn hành vi đó bằng tổ hợp instruction, method, class hoặc metadata. Ví dụ:

| Cấu trúc Java nguồn | Kết quả thường thấy ở bytecode hoặc class file |
| --- | --- |
| Enhanced `for` trên array | Chỉ số và vòng lặp tương đương |
| Enhanced `for` trên `Iterable` | Lời gọi `iterator()`, `hasNext()`, `next()` |
| `try`-with-resources | Luồng đóng resource và xử lý suppressed exception theo JLS |
| Generic `List<String>` | Erasure trong descriptor và thông tin signature khi cần |
| Lambda / method reference | Thường có `invokedynamic` và bootstrap metadata ở OpenJDK `javac` |
| Nối chuỗi động bằng `+` | Thường dùng `invokedynamic`/`StringConcatFactory` ở Java 17 |
| `record` | Class với field, accessor, constructor và các thành viên theo quy tắc record |
| `switch` expression | Điều khiển luồng và trả giá trị phù hợp, có thể kết hợp `tableswitch`/`lookupswitch` hoặc cấu trúc khác |

Đây là **hình dạng thực thi phù hợp ngôn ngữ**, không phải lời bảo đảm rằng compiler đã đạt tối ưu tốc độ cao nhất. Compiler vẫn có thể áp dụng các phép xử lý đơn giản như **constant folding** và các phép biến đổi được đặc tả cho constant expression; nhưng không nên trông chờ `javac` thực hiện toàn bộ inlining, escape analysis hay profile-guided optimization kiểu HotSpot JIT.

**Lưu ý về “tối ưu hóa của javac”:** không cần phủ nhận mọi tối ưu hóa compile time. Một số phép tính hằng được tính trước thật; điểm khác là `javac` thường không có dữ liệu nóng/lạnh, nhánh phổ biến hoặc class thực tế của object trong lần chạy tương lai, nên không thể đưa ra cùng loại quyết định như runtime compiler.

## 3. Ví dụ thứ nhất: mã nguồn cao cấp được hạ thành bytecode

Tạo tệp **`SourceTransformDemo.java`**:

~~~java
public class SourceTransformDemo {
    static int sum(int[] numbers) {
        int total = 0;
        for (int number : numbers) {
            total += number;
        }
        return total;
    }

    static String greet(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println(sum(new int[] {1, 2, 3}));
        System.out.println(greet("Java"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SourceTransformDemo.java
java SourceTransformDemo
~~~

Stdout chính xác:

~~~text
6
Hello, Java
~~~

Quan sát class file:

~~~bash
javap -c -p SourceTransformDemo
~~~

Ở mã nguồn có `for (int number : numbers)`, nhưng trong bytecode sẽ thấy các bước tương ứng để đi qua mảng, lấy từng phần tử, cộng và kiểm tra điều kiện vòng lặp. Đây là **lowering** từ cú pháp ngôn ngữ sang bytecode, không chứng minh rằng vòng lặp đang được tối ưu theo profile runtime.

Với `"Hello, " + name`, OpenJDK `javac` hiện đại cho target Java 17 thường phát ra một call site `invokedynamic` dựa trên `StringConcatFactory`. `javap -c` có thể hiển thị lệnh `invokedynamic` và `javap -v` cho thấy bootstrap metadata. Cơ chế này từ JEP 280 cho phép runtime chọn phương thức nối chuỗi thích hợp; **không đồng nghĩa javac đã nối trước một `name` chỉ biết khi chạy**.

Lệnh `javap` đọc nội dung class file đã biên dịch. Nó cho biết **compiler đã phát ra gì**, chứ không cung cấp ảnh chụp machine code sau khi JVM dùng JIT để tối ưu.

### Khi nào cần so bytecode?

- Khi muốn hiểu một cú pháp được hạ ra sao.
- Khi kiểm tra `--release`, thông tin debug, method synthetic/bridge hoặc descriptor generic.
- Khi một công cụ bytecode, coverage, instrumentation hay reflection hoạt động khác với dự đoán từ Java source.

Không nên lấy số lượng instruction được `javap -c` in ra làm thước đo trực tiếp cho tốc độ chạy: một instruction có thể được JIT gộp với nhiều instruction khác; chi phí runtime còn phụ thuộc cache, dữ liệu, nhánh và môi trường.

## 4. Constant folding của javac khác runtime optimization

Xét tệp **`CompileTimeConstantDemo.java`**:

~~~java
public class CompileTimeConstantDemo {
    static final int LIMIT = 40 + 2;

    public static void main(String[] args) {
        System.out.println(LIMIT);
        System.out.println("Ja" + "va");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CompileTimeConstantDemo.java
java CompileTimeConstantDemo
~~~

Stdout:

~~~text
42
Java
~~~

`40 + 2` và `"Ja" + "va"` là những **constant expressions** theo luật Java. Compiler có thể đưa giá trị `42` và `"Java"` trực tiếp vào class file; khi quan sát `javap -c`, thường không thấy instruction cộng hai số 40 và 2 ở runtime hay gọi trình nối chuỗi cho hai hằng đó.

Đây là công việc **compile time** vì toán hạng đã xác định được từ source. Nó khác hoàn toàn với việc JIT nhận thấy một method lặp lại rất nhiều lần, suy đoán nhánh nóng và tạo native code tối ưu khi ứng dụng đang chạy.

Phân biệt thêm:

~~~java
int x = 40;
int y = 2;
int answer = x + y;
~~~

Không nên kết luận rằng mọi chương trình dùng biến local đều có cùng bộ instruction với hằng trong ví dụ trước. `javac` có thể giữ các thao tác nạp/cộng trong bytecode; JIT về sau có thể tối ưu tùy thông tin khả dụng. Với nhiều giá trị runtime khác nhau, không thể thay một phép cộng bằng hằng cố định mà vẫn đúng hành vi.

### Hệ quả quan trọng: hằng được inline qua tệp class

Tạo hai tệp:

**`ConstantConfig.java`**

~~~java
public final class ConstantConfig {
    private ConstantConfig() {}

    public static final int LIMIT = 40 + 2;
}
~~~

**`ConstantConsumer.java`**

~~~java
public class ConstantConsumer {
    public static void main(String[] args) {
        System.out.println(ConstantConfig.LIMIT);
    }
}
~~~

Lần đầu:

~~~bash
javac --release 17 ConstantConfig.java ConstantConsumer.java
java ConstantConsumer
~~~

Stdout:

~~~text
42
~~~

Bây giờ sửa `ConstantConfig.LIMIT` thành `99`, rồi chỉ biên dịch lại:

~~~bash
javac --release 17 ConstantConfig.java
java ConstantConsumer
~~~

`ConstantConsumer.class` cũ **vẫn có thể in `42`** vì `LIMIT` là một *constant variable* có giá trị được nhúng khi consumer biên dịch. Để đồng bộ, biên dịch lại consumer hoặc build lại toàn bộ tập phụ thuộc. Đây là đặc tính **separate compilation và binary compatibility** của compile-time constants, không phải do JIT “cache sai” giá trị.

Với `static final` tham chiếu đến object mới được tính lúc khởi tạo class, hoặc biểu thức không phải constant expression, cơ chế truy cập field và khả năng tối ưu khác. Đừng coi **mọi** field `static final` đều được javac nhúng như một primitive/String compile-time constant.

## 5. JVM thực thi bytecode như thế nào?

Khi chạy:

~~~bash
java SourceTransformDemo
~~~

JVM thực hiện các hoạt động như nạp class, xác minh bytecode, liên kết và khởi tạo theo thời điểm cần thiết. Sau đó, method có thể được thực thi bằng **interpreter** hoặc bằng machine code do runtime compiler sinh. Trên HotSpot, các method thường bắt đầu ở interpreter hoặc tầng code tương ứng; runtime thu thập thông tin và có thể chuyển một số đoạn nóng sang compiled code.

Dữ liệu profiling có thể gồm:

- Tần suất gọi method và số lần lặp của loop.
- Tần suất nhánh đúng/sai ở những vị trí có đo lường.
- Kiểu runtime thường gặp ở call site đa hình.
- Đặc tính được compiler runtime suy ra từ luồng dữ liệu và lịch sử thực thi.

JIT sử dụng thông tin này để đưa ra quyết định mà `javac` không thể biết từ source đơn thuần. Kết quả machine code phụ thuộc CPU architecture, phiên bản JVM, flag, profile và điều kiện thực tế; **tệp `.class` không cần thay đổi**.

### Tiered compilation trên HotSpot

HotSpot thông dụng dùng **tiered compilation** để cân bằng thời gian khởi động, chi phí biên dịch và throughput dài hạn. Có thể nhìn khái quát:

~~~text
Bytecode
   │
   ├── Interpreter (và thu thập dữ liệu)
   │
   ├── C1: biên dịch tương đối nhanh, có thể hỗ trợ profiling
   │
   └── C2: tối ưu sâu hơn khi đủ điều kiện
            │
            ▼
     Native machine code cho method hoặc loop
~~~

Các mức tier 0–4 và đường đi chi tiết của HotSpot tùy cấu hình và phiên bản; ví dụ level 0 gắn interpreter, các level 1–3 thường liên quan C1, level 4 thường liên quan C2. Đây không phải “bốn vòng javac” hay quy tắc mọi method phải chạm từng level. Một method ngắn ít dùng có thể không được biên dịch JIT; một loop nóng có thể kích hoạt **on-stack replacement (OSR)** khi thực thi.

### Warm-up

Một workload có thể chạy chậm hơn khi mới khởi động vì còn class loading, initialization, profiling, JIT compilation và nhiều chi phí khác. Sau thời gian chạy, hot code có thể được tối ưu hơn. Tuy nhiên, **không thể suy ra một tốc độ warm-up cố định**: workload nhỏ, I/O-bound, JVM khác hoặc profile thay đổi có thể cho xu hướng khác; GC, cache và CPU cũng ảnh hưởng.

## 6. Ví dụ thứ hai: cùng class file, các chế độ chạy JVM

Tạo **`HotLoopDemo.java`**:

~~~java
public class HotLoopDemo {
    static int step(int value) {
        return value * 2 + 1;
    }

    static long calculate() {
        long total = 0;
        for (int i = 0; i < 1_000_000; i++) {
            total += step(i % 10);
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(calculate());
    }
}
~~~

Biên dịch đúng một lần:

~~~bash
javac --release 17 HotLoopDemo.java
~~~

Chạy bình thường:

~~~bash
java HotLoopDemo
~~~

Stdout:

~~~text
10000000
~~~

Vì `i % 10` lặp các số 0–9 đúng 100.000 lần, mỗi nhóm 10 lượt góp `1 + 3 + ... + 19 = 100`; tổng bằng 10.000.000.

Nếu dùng HotSpot, có thể thử hai lệnh chẩn đoán:

~~~bash
java -Xint HotLoopDemo
java -XX:+PrintCompilation HotLoopDemo
~~~

- `-Xint` yêu cầu HotSpot chạy theo chế độ chỉ interpreter, hữu ích để **đối chiếu**, nhưng không biến source thành “Java khác”.
- `-XX:+PrintCompilation` in log những phương thức được biên dịch JIT trong quá trình chạy; log có thể gồm rất nhiều method của JDK, thay đổi theo phiên bản/môi trường và không buộc phải chứa mọi method của chương trình.
- Kết quả nghiệp vụ của chương trình vẫn phải là `10000000` nếu chạy thành công, mặc dù log JIT có thể được in thêm ra console và vị trí dòng output không cố định.

So sánh file `HotLoopDemo.class` trước và sau hai lần `java` (nếu không có công cụ khác can thiệp) sẽ cho cùng nội dung: JVM không viết đè class file để lưu code đã JIT. Machine code tối ưu được quản lý bên trong tiến trình JVM, thường trong code cache, và chấm dứt khi tiến trình dừng.

Không dùng thời gian của một lượt chạy đơn lẻ làm bằng chứng JIT nhanh/chậm hơn. Với microbenchmark, cần warm-up, nhiều fork/lần đo, đầu vào đủ đại diện và ngăn tối ưu làm mất workload; JMH phù hợp hơn cách tự tính `System.nanoTime()` tùy tiện.

## 7. Các tối ưu hóa JIT thường được nhắc đến

**Inlining:** thay một lời gọi method bằng biểu diễn phần thân method tại call site khi chi phí/độ phức tạp hợp lý. Ví dụ `step(i % 10)` trong `HotLoopDemo` có thể được inline sau khi JIT có đủ thông tin. `javap -c HotLoopDemo` vẫn thường cho thấy lời gọi method vì nó in class file, không phải code sau inlining.

**Dead code elimination:** loại bỏ tính toán không ảnh hưởng kết quả quan sát được trong phạm vi chứng minh an toàn. Trên JVM tối ưu, một biến trung gian không dùng có thể không tồn tại như một slot machine code. Không được loại bỏ thao tác có side effect hoặc exception quan sát được một cách làm thay đổi hành vi chương trình.

**Constant propagation / folding runtime:** JIT có thể biết một giá trị là hằng trong vùng mã đang tối ưu sau khi inline và phân tích luồng dữ liệu, dù `javac` chưa thể biết hằng ở cấu trúc source. Điều này khác việc Java source chứa constant expression được compiler xử lý theo JLS.

**Loop optimizations:** hoán đổi vị trí công việc an toàn ra ngoài loop, cải thiện loop control hoặc loại bớt kiểm tra dư thừa tùy trường hợp. Không có lời hứa rằng mọi loop Java đều được vectorize hoặc loại bỏ mọi bounds check.

**Range-check elimination:** nếu JIT chứng minh một lần truy cập array luôn nằm trong miền hợp lệ trong vùng code tối ưu, có thể tránh một số kiểm tra biên lặp đi lặp lại. Nhưng mọi truy cập vẫn phải tuân theo ngữ nghĩa ném `ArrayIndexOutOfBoundsException` khi thực sự ngoài miền.

**Escape analysis và scalar replacement:** nếu một object tạm không “thoát” khỏi phạm vi phân tích và không cần giữ object identity quan sát được, JIT có thể thay việc truy cập object bằng các giá trị scalar. Đây là **khả năng tối ưu**, không phải bảo đảm “viết `new` thì JVM không cấp phát”.

**Branch prediction / profile-guided optimization:** ưu tiên bố cục và đường đi được dùng nhiều theo thông tin runtime; có thể áp dụng speculative assumptions rồi kiểm tra điều kiện bảo vệ.

**Devirtualization:** khi runtime profile cho thấy kiểu receiver thường là một kiểu cụ thể, JIT có thể tối ưu lời gọi interface/virtual thành lời gọi chuyên biệt hoặc inline với guard thích hợp. Không làm thay đổi quy tắc polymorphism Java; nếu giả định không còn đúng, runtime phải xử lý an toàn.

Các thuật ngữ mô tả *khả năng* của một runtime compiler; muốn biết một biến đổi có xảy ra ở một method cụ thể phải có bằng chứng từ runtime/profiler, chứ không dựa vào tính “có vẻ tối ưu” của Java source.

## 8. Ví dụ escape analysis: vì sao không nên đoán từ câu lệnh new

Xét đoạn độc lập sau — tệp **`PointWorkDemo.java`**:

~~~java
public class PointWorkDemo {
    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    static int result(int value) {
        Point point = new Point(value, value + 1);
        return point.x + point.y;
    }

    public static void main(String[] args) {
        System.out.println(result(10));
    }
}
~~~

~~~bash
javac --release 17 PointWorkDemo.java
java PointWorkDemo
~~~

Stdout:

~~~text
21
~~~

`javac` phát bytecode có thể biểu diễn việc tạo `Point` và đọc hai field. Sau khi JIT inline đủ các method và chứng minh object không escape, HotSpot **có thể** scalar-replace những giá trị này, giảm hoặc tránh allocation trong mã máy tối ưu.

Điều này **không bảo đảm** allocation bị xóa trên mọi lần gọi. Escape analysis phụ thuộc đồ thị lời gọi, phiên bản JVM, các lựa chọn tối ưu, khả năng quan sát đối tượng và trạng thái runtime. Nếu `Point` được trả về, lưu vào field toàn cục hoặc dùng trong ngữ cảnh làm identity cần quan sát, bài toán khác.

Không sử dụng kết quả `javap` để kết luận “JIT không tối ưu allocation”: `javap` chỉ nhìn thấy bytecode trước runtime. Cũng đừng viết code phụ thuộc vào việc JIT *phải* loại bỏ object; chương trình phải chạy đúng cả khi interpreter thực thi đúng các thao tác tương đương.

## 9. Speculative optimization và deoptimization

Một JVM runtime compiler có thể đưa ra giả định dựa trên dữ liệu thực tế, ví dụ “hầu hết receiver ở call site này có class `FastWorker`”. Khi giả định đó hợp lý, nó có thể tạo code nhanh hơn với **guard** xác nhận điều kiện. Nếu trong tương lai điều kiện không còn đúng, runtime có thể **deoptimize**: chuyển về cách thực thi bảo toàn ngữ nghĩa, có thể phục hồi trạng thái phù hợp để tiếp tục, hoặc biên dịch lại bằng profile mới.

~~~text
Dữ liệu runtime → profile: call site thường nhận FastWorker
                           │
                           ▼
JIT tạo machine code chuyên biệt + guard
                           │
            ┌──────────────┴─────────────┐
            ▼                            ▼
     Guard đúng                     Guard sai / giả định mất hiệu lực
     Đường nhanh                    Deoptimization / đường tổng quát
            │                            │
            └──────────► Cùng ngữ nghĩa Java ◄─────────┘
~~~

Không nhầm **deoptimization** với “compiler javac đã sửa tệp source” hay “JVM đổi bytecode trên ổ đĩa”. Thông thường đây là sự thay đổi cách thực thi của code đã nạp trong bộ nhớ, dù những công cụ như Java agents có thể thực hiện class redefinition theo một cơ chế khác.

HotSpot có thể biên dịch lại method, vô hiệu hóa compiled code hoặc chuyển frame sang interpreter tùy tình huống. Các thay đổi này giải thích vì sao tốc độ chương trình có thể biến thiên theo dữ liệu chạy, ngay cả khi tệp `.class` được giữ nguyên.

## 10. JIT không được phép làm gì?

Tối ưu runtime phải bảo toàn **ngữ nghĩa có thể quan sát** theo Java Language Specification và Java Memory Model. Ví dụ:

- Không được tự ý đảo thứ tự những thao tác gây side effect nếu việc đảo làm khác kết quả quan sát được theo ngữ nghĩa Java.
- Không được loại bỏ một exception bắt buộc xuất hiện trong đường thực thi cụ thể nếu việc loại bỏ thay đổi hành vi chương trình.
- Không được coi phép toán `int` tràn như số nguyên toán học vô hạn; Java định nghĩa hành vi tràn số nguyên, nên tối ưu phải giữ kết quả tương ứng.
- Không được tự xem `volatile` hay ràng buộc đồng bộ/thread-safety là dữ liệu bình thường rồi tối ưu sai quy tắc happens-before.
- Không được tạo ra kết quả phụ thuộc sai vào một type profile cũ khi chương trình hợp lệ chạy với một receiver mới; đó là lý do cần guard và deoptimization.

Phát biểu chính xác hơn “JIT không thay đổi kết quả” là **JIT phải duy trì các hành vi được đặc tả trong phạm vi chương trình Java hợp lệ**. Thứ tự vật lý của các instruction máy có thể khác source, miễn các ràng buộc quan sát và mô hình bộ nhớ vẫn được đáp ứng. Một số thứ bên ngoài hợp đồng ngữ nghĩa, chẳng hạn thời gian chạy hay thời điểm GC, có thể thay đổi.

Nếu một benchmark thay đổi output khi bật/tắt JIT, cần kiểm tra race condition, phụ thuộc ngoài đặc tả, hành vi native hoặc bug trong chương trình/runtime trước khi gọi đó là “tối ưu bình thường”.

## 11. String concatenation: một trường hợp làm rõ hai lớp biến đổi

Xét:

~~~java
static String label(String name, int number) {
    return "item=" + name + ":" + number;
}
~~~

Đây chỉ là *đoạn method để giải thích*, cần đặt vào một class Java để biên dịch. Java đảm bảo hành vi nối chuỗi và thứ tự đánh giá toán hạng theo ngữ nghĩa của ngôn ngữ.

Trên OpenJDK `javac` đời Java 8, nhiều trường hợp nối chuỗi được hạ thành chuỗi thao tác trên `StringBuilder`. Từ JDK 9 (JEP 280), code động thường được phát qua `invokedynamic` với bootstrap `StringConcatFactory`. Điều này có hai tầng:

1. **javac quyết định dạng bytecode** dùng `invokedynamic` thay vì hardcode một chiến lược builder nhất định.
2. **JVM/JDK runtime** liên kết call site và chọn cách thực hiện nối chuỗi, sau đó JIT còn có thể tối ưu code thực thi.

Không nên mô tả `invokedynamic` là “mọi concatenation đều được JIT tối ưu”. Đó là **một cơ chế liên kết động**, còn lợi ích hiệu năng phải được đo ở workload và JVM cụ thể. Với biểu thức nối các hằng như `"Ja" + "va"`, javac có thể gộp thành hằng `"Java"` mà không cần runtime concat.

Để quan sát trên máy, đặt đoạn method vào class và dùng `javac --release 17`, sau đó `javap -c -v`. Nội dung `BootstrapMethods` thường cho thấy metadata phục vụ `StringConcatFactory`. Hình dạng này phụ thuộc trình biên dịch và tùy chọn, nên phân biệt **quy định ngữ nghĩa Java** với **chi tiết implementation của OpenJDK**.

## 12. Lambda: compiler sinh call site, runtime hiện thực cách gọi

Ví dụ đầy đủ **`LambdaTransformDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class LambdaTransformDemo {
    public static void main(String[] args) {
        IntUnaryOperator doubleIt = x -> x * 2;
        System.out.println(doubleIt.applyAsInt(21));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LambdaTransformDemo.java
java LambdaTransformDemo
~~~

Stdout:

~~~text
42
~~~

`javap -c -p LambdaTransformDemo` trên `javac` thông dụng sẽ thấy một call site `invokedynamic` liên quan khởi tạo functional object, cùng một phương thức hỗ trợ lambda khi cần. Runtime liên kết call site theo cơ chế được mô tả cho lambda. Việc một JVM có tạo thêm lớp ẩn, cấp phát object hay inline lời gọi `applyAsInt` ra sao là chuyện **runtime implementation và tối ưu**, không phải kết luận bắt buộc từ câu `x -> x * 2`.

Tránh khẳng định lambda chắc chắn “nhanh hơn anonymous class” hoặc “không có cấp phát”. Cần benchmark đúng workload và xem runtime cụ thể để kết luận hiệu năng.

## 13. Inlining: bytecode còn lời gọi nhưng machine code có thể không còn

Giả sử source có:

~~~java
static int square(int value) {
    return value * value;
}

static int work(int x) {
    return square(x) + 1;
}
~~~

Ở bytecode của `work`, `javac` thường phát lệnh gọi `square`; đây là phương thức độc lập theo mô hình class file. Nếu `work` trở thành code nóng, JIT có thể inline `square` vào bản native của `work`, rồi loại bỏ overhead call hoặc tiếp tục tối ưu biểu thức.

**Hai câu sau có thể cùng đúng:**

- `javap -c` cho thấy lời gọi `square` trong `work`.
- JIT machine code của một phiên bản `work` đang thực thi **không còn lời gọi thật đến `square`** vì thân method đã được inline.

Không có mâu thuẫn; công cụ nhìn **hai tầng khác nhau**. Để xác nhận inlining cần log/quan sát JIT (ví dụ tùy chọn diagnostic phù hợp trên HotSpot, profiler hoặc công cụ phân tích JIT); `javap` không đủ.

Inlining cũng phụ thuộc code size, số lần gọi, tính đa hình, recursion, escape, cách profiling và giới hạn budget của JIT. Không nên cố đoán rằng method vài dòng **luôn** được inline.

## 14. Tại sao javac không “tối ưu hết” ngay từ đầu?

Một compiler nguồn chạy trước ứng dụng thường không biết:

- Các giá trị method sẽ nhận trong phần lớn lượt gọi.
- Những nhánh nào xuất hiện nhiều nhất theo dữ liệu nghiệp vụ thật.
- Kiểu đối tượng thực tế tại call site đa hình khi đã chạy lâu.
- Bộ xử lý, cache, tập lệnh máy và hoàn cảnh scheduling sẽ dùng trong runtime.
- Những class bổ sung có thể được nạp, làm thay đổi các giả định của speculative optimization.

`javac` chủ yếu cần **tạo class file đúng chuẩn và có thể chạy trên nhiều môi trường JVM tương thích**. JIT có thể trì hoãn lựa chọn đến lúc có profile/CPU thật, chấp nhận thêm chi phí đo lường và biên dịch để cải thiện đoạn code nóng.

Tuy vậy, thuật ngữ “javac không tối ưu” chỉ nên hiểu là **javac không đóng vai trò một optimizing native runtime compiler tổng quát như HotSpot JIT**. Nó vẫn có constant folding, các chuyển đổi bắt buộc của language, và lựa chọn bytecode ảnh hưởng hiệu năng. Câu “tất cả tối ưu đều xảy ra ở JVM” là quá cực đoan.

## 15. Phân biệt JVM/JIT với các thành phần runtime khác

**Interpreter:** trực tiếp xử lý bytecode theo cơ chế diễn giải; đây là một cách thực thi bytecode, không phải trình chuyển Java source thành class file.

**JIT compiler:** tạo machine code cho code được lựa chọn trong một JVM runtime. Không phải mọi JVM đều có cùng JIT hoặc cùng heuristics.

**Class loader và verifier:** nạp và kiểm tra class file; không đồng nghĩa với JIT tối ưu method. Class không tìm thấy khi chạy là vấn đề loading/linking/runtime dependency, không chứng minh javac đã tối ưu sai.

**Garbage collector:** quản lý vùng nhớ và thu hồi object không còn truy cập được. Escape analysis có thể ảnh hưởng allocation pressure, nhưng GC không phải là “pass tối ưu bytecode của javac”.

**AOT/native-image compiler:** có thể biên dịch một phần hoặc toàn bộ chương trình sang mã máy trước khi chạy theo cơ chế riêng của từng công cụ. Đó là một pipeline khác với ví dụ tiêu chuẩn `javac .java → .class → HotSpot JIT`; không nên ép mọi Java application vào cùng một mô hình.

**Build tool:** Gradle/Maven quyết định classpath, task và biên dịch tăng dần, có thể cache kết quả. Việc một task build được bỏ qua không phải là JIT optimization; dù chẳng gọi lại `javac`, JVM vẫn có thể JIT khi thực thi chương trình.

## 16. Quan sát đúng tầng bằng công cụ đúng

| Muốn trả lời | Nên dùng | Không suy ra |
| --- | --- | --- |
| Compiler phát class file ra sao? | `javac` và `javap -c -p -v` | JIT đã inline các method |
| Một biểu thức constant đã được gộp chưa? | Xem bytecode/constant pool và JLS | Mọi tính toán đều fold trước runtime |
| Lỗi compile-time xuất hiện đâu? | Diagnostics từ `javac` | Runtime sẽ không còn exception |
| Method nào được JIT compile? | Log `-XX:+PrintCompilation` trên HotSpot | Tất cả method đều được tối ưu cùng mức |
| JIT có inline/escape analysis thật không? | JIT diagnostic, disassembly hoặc profiler phù hợp | Chỉ nhìn source hoặc `javap` là đủ |
| Tốc độ ổn định và độ trễ có cải thiện? | JMH/JFR/profiler, đo có kiểm soát | Một lần đo bằng `nanoTime` đã kết luận |
| Hành vi có đúng dưới concurrency? | Tests và quy tắc JMM/happens-before | JIT tự sửa race condition |

### Các lệnh kiểm tra tham khảo

Trong thư mục có `HotLoopDemo.java`:

~~~bash
javac -version
java -version
javac --release 17 HotLoopDemo.java
javap -c -p HotLoopDemo
java -Xint HotLoopDemo
java -XX:+PrintCompilation HotLoopDemo
~~~

Nếu là HotSpot, dùng thêm Java Flight Recorder (JFR) hoặc profiler khi cần tìm hot method, allocation và độ trễ. Cú pháp, tính khả dụng và lượng log phụ thuộc JDK/JVM. Ví dụ `-XX:+PrintCompilation` thêm nhiều dòng chẩn đoán ngoài stdout nghiệp vụ, nên không thể mong toàn bộ màn hình chỉ có dòng `10000000`.

Có thể so sánh `javap` của cùng class trước và sau một lượt chạy dài. Nếu không biên dịch lại hay dùng công cụ sửa bytecode, nội dung class file vẫn nguyên; JIT không persist machine code bằng cách ghi đè `.class`.

### Không biến flag debug thành một “tối ưu hóa mới”

Các flag như `-Xint`, `-XX:+PrintCompilation` hoặc tùy chọn thông tin inlining chủ yếu thay đổi chế độ thực thi/chẩn đoán. Chúng không phải các annotation cho `javac`, không sửa Java source và không cung cấp kết quả tối ưu ổn định giữa mọi nhà cung cấp JVM. Cần ghi nhận chính xác phiên bản VM và các flag trước khi so số liệu.

## 17. Tình huống thực tế: phát hiện nhầm nguyên nhân

### Tình huống A — “javap thấy invokevirtual nên method không được inline”

**Nhận định này sai.** `javap` thấy lời gọi ở bytecode do `javac` phát. JIT có thể inline method trong machine code. Cần thông tin runtime mới biết có xảy ra hay không.

### Tình huống B — “JIT đổi kết quả hằng 42 sau khi sửa ConstantConfig”

Nếu chỉ biên dịch lại class chứa `static final int LIMIT = ...` mà không biên dịch consumer, consumer có thể giữ giá trị đã được inline lúc compile time. Trước hết kiểm tra **binary hiện có và dependency rebuild**, không quy ngay cho JIT.

### Tình huống C — “Có new trong Java source nên chắc chắn phân bổ trên heap”

Không luôn đúng. JIT có thể loại một số allocation qua escape analysis/scalar replacement. Nhưng cũng không được khẳng định compiler bắt buộc làm vậy; phải đo/quan sát runtime.

### Tình huống D — “Lần chạy thứ hai nhanh hơn là do javac”

Nếu class file không thay đổi, `javac` không chạy lại. Khác biệt có thể liên quan JVM warm-up, JIT, cache, hệ điều hành, GC hoặc nhiễu đo đạc. Cần thí nghiệm có nhiều lần đo để phân định.

### Tình huống E — “Dùng --release 17 thì JIT chỉ được dùng chiến lược Java 17”

`--release 17` điều khiển **ngôn ngữ/API/định dạng class file khi biên dịch**. JVM phiên bản mới hơn vẫn có thể chạy class file Java 17 với JIT và thuật toán tối ưu của chính nó. Không nên đồng nhất bytecode target với phiên bản hoặc cấu hình máy thực thi.

### Tình huống F — “Chuỗi + được javac tối ưu thành StringBuilder mọi lúc”

Từ JDK 9, cách biên dịch nối chuỗi động trên OpenJDK thường dùng `invokedynamic`; constant concatenation có thể fold hoàn toàn. Cần xem bytecode tạo bởi phiên bản compiler thực tế thay vì áp một mô hình cũ cho mọi JDK.

## 18. Checklist phân tích hiệu năng có trách nhiệm

1. **Xác định tầng:** lỗi cú pháp/ngữ nghĩa, hình dạng bytecode, class loading, JIT, allocation, GC hay I/O? Mỗi tầng có công cụ khác nhau.
2. **Chốt thông tin môi trường:** `javac -version`, `java -version`, `--release`, OS, CPU và flags.
3. **Kiểm tra hành vi trước:** input, output, exception, concurrency semantics đúng thì mới bàn đến tối ưu.
4. **Quan sát bytecode nếu câu hỏi thuộc compiler:** `javap -c -p -v`, kiểm tra signature, call site, constant và control flow.
5. **Quan sát runtime nếu câu hỏi thuộc JIT:** warm-up, compilation logs, JFR/JMH và profiling trên JVM thật.
6. **Phân biệt khả năng và bằng chứng:** “JIT có thể inline” khác “method này đã được inline trong lần chạy này”.
7. **Đo trước rồi sửa:** tránh tự viết lại Java source chỉ vì hình dung rằng càng ít object hoặc càng ít method call thì chắc chắn càng nhanh.
8. **Đảm bảo tái lập:** dùng cùng class file, input, flags và quy trình đo nếu muốn so các cấu hình runtime.

## 19. Tự kiểm tra

**Câu 1.** `javap -c` thấy `invokestatic SomeClass.helper`. Có thể kết luận HotSpot chưa inline method đó?  
**Đáp án:** Không. `javap` xem bytecode; JIT có thể inline lời gọi trong compiled machine code.

**Câu 2.** `System.out.println(40 + 2);` có thể in `42` mà runtime không cộng không?  
**Đáp án:** Có. Đây là constant expression mà `javac` có thể gộp trước khi sinh bytecode.

**Câu 3.** Khi `Point point = new Point(...)` tạo object tạm, JIT có bắt buộc phân bổ object không?  
**Đáp án:** Không nhất thiết; escape analysis/scalar replacement có thể làm giảm allocation. Nhưng không được bảo đảm loại bỏ trong mọi điều kiện.

**Câu 4.** Một class file chạy trên hai máy cho tốc độ khác nhau. Có bắt buộc là do `javac` biên dịch khác không?  
**Đáp án:** Không. JVM, JIT, CPU, workload, GC và môi trường khác nhau dù bytecode giống nhau.

**Câu 5.** Tại sao Java 17 `javac` thường sinh `invokedynamic` cho nối chuỗi động?  
**Đáp án:** Đó là cơ chế từ JEP 280 để tách phần lựa chọn thực hiện nối chuỗi khỏi một mẫu bytecode builder cố định, cho phép runtime liên kết và tối ưu linh hoạt.

**Câu 6.** Vì sao JIT được phép làm speculative inlining mà không phá polymorphism?  
**Đáp án:** Runtime dùng guard/điều kiện phù hợp và có thể deoptimize hoặc quay về cách thực thi tổng quát khi giả định hết đúng.

**Câu 7.** `java -Xint` và `java -XX:+PrintCompilation` có thay tệp `.class` trên đĩa không?  
**Đáp án:** Thông thường không; đây là lựa chọn runtime/diagnostic của HotSpot. Chúng không phải một lệnh biên dịch lại nguồn.

## 20. Ghi nhớ

- `javac` **kiểm tra ngôn ngữ và sinh bytecode**, bao gồm desugaring/lowering và một số xử lý compile-time như constant folding. Output của nó là class file.
- JVM **nạp và thực thi bytecode**. Trên HotSpot, JIT có thể biên dịch những vùng code nóng thành machine code, dựa trên profiling và thông tin runtime.
- **Inlining, escape analysis, loop optimization, tiered compilation và deoptimization** là các khái niệm runtime quan trọng. Không thể xác nhận chúng đã xảy ra chỉ từ `javap`.
- Cùng một tệp `.class` có thể được chạy bằng interpreter hoặc các bản machine code khác nhau mà vẫn bảo toàn ngữ nghĩa Java.
- Hãy dùng `javap` để trả lời câu hỏi **compiler đã sinh gì**, và runtime profiling/JIT diagnostics để trả lời **JVM đã thực thi và tối ưu như thế nào**.

### Tài liệu tham khảo

- [Javac command — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Javap command — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280).
- [Java SE 17 JLS: Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).
- [Java SE 17 JVM Specification](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html).
- [HotSpot Tiered Compilation — Microsoft Java Engineering](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/).

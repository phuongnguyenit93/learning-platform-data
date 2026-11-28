# Interpreter, JIT, tiered compilation và deoptimization trong Java 27

Trong chương **JVM, bộ nhớ và thu gom rác**, hiệu năng Java không chỉ phụ thuộc vào dung lượng heap hoặc lựa chọn garbage collector (GC). **Cách JVM thực thi bytecode và tối ưu mã trong lúc chương trình chạy** cũng ảnh hưởng trực tiếp đến thời gian khởi động, thông lượng, độ trễ và mức tiêu thụ CPU/bộ nhớ.

Trên **HotSpot JVM của Java 27**, chương trình có thể bắt đầu bằng **bytecode interpreter**, sau đó những phương thức hoặc vòng lặp thường xuyên thực thi được **Just-In-Time compiler (JIT)** biên dịch thành mã máy. **Tiered compilation** kết hợp interpreter, bộ biên dịch nhanh **C1** và bộ biên dịch tối ưu mạnh **C2**. Khi giả định mà JIT dựa vào không còn đúng, JVM có thể **deoptimize**: quay về một hình thức thực thi an toàn hơn, rồi tiếp tục thu thập profile và tối ưu lại.

Đó không phải lỗi lập trình, cũng không phải bằng chứng JVM thực thi sai: **deoptimization là cơ chế giúp tối ưu mang tính suy đoán vẫn bảo toàn ngữ nghĩa Java**.

> **Phạm vi:** bài mô tả chủ yếu **HotSpot/OpenJDK Java 27**; các level C1/C2, JIT flags và code cache là chi tiết triển khai, **không phải cam kết chung của Java Language Specification/JVM Specification cho mọi JVM**. Các ví dụ dùng API và công cụ hiện hành; không khuyến khích những tuning recipe từ JDK cũ hoặc tự đặt ngưỡng compile tùy tiện.

## 1. Từ Java source đến thực thi trên CPU

Khi viết:

```java
public class SumDemo {
    static int sum(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(sum(20, 22));
    }
}
```

quy trình đơn giản là:

```text
SumDemo.java
   |
   | javac SumDemo.java
   v
SumDemo.class (bytecode của JVM)
   |
   | class loading + verification + linking
   v
HotSpot JVM
   +-------------------------+
   | Interpreter             |  Thực thi bytecode, thu profile
   +-------------------------+
               |
               | Phương thức/vòng lặp đủ "hot",
               | theo heuristic của runtime
               v
   +-------------------------+
   | JIT C1 / C2             |  Tạo native machine code
   +-------------------------+
               |
               v
      CPU chạy mã máy
```

`javac` **không** phải JIT: `javac` là compiler chạy trước ứng dụng, chuyển Java source thành `.class` bytecode. JIT là **compiler trong runtime**, dùng thông tin thu thập trong khi ứng dụng chạy để tạo mã phù hợp với hành vi thật.

**Không phải mọi method đều được JIT-compile.** Một method gọi vài lần có thể chạy qua interpreter đến hết đời process. Bản thân quá trình compile cũng tốn CPU và bộ nhớ; JVM chỉ ưu tiên compile khi nó kỳ vọng chi phí đó được bù đắp.

### 1.1. JVM Specification không bắt buộc một JIT cụ thể

Bytecode xác định hành vi cần được thực thi nhưng không ép implementation phải có đúng C1, C2 hay năm level. Một JVM khác có thể có chiến lược biên dịch khác. Ngay trong HotSpot, heuristics, thresholds và cách quản lý compiled code có thể đổi giữa JDK/platform/bản dựng.

Vì thế, khi nói “tier 3” hoặc “C2”, hãy hiểu là **mô hình HotSpot**, không phải một đặc điểm bắt buộc của ngôn ngữ Java.

## 2. Interpreter thực sự làm gì?

**Bytecode interpreter** đọc và thực thi các instruction JVM, quản lý operand stack, local variables và các bước gọi method/return theo mô hình của JVM. Nó giúp chương trình bắt đầu mà không phải đợi compile toàn bộ ứng dụng sang machine code.

Ví dụ nhìn bytecode bằng công cụ JDK:

```text
javac SumDemo.java
javap -c -p SumDemo
```

Kết quả của method `sum(int,int)` có thể giống:

```text
static int sum(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Ý nghĩa:

- `iload_0`, `iload_1`: đưa giá trị `int` từ local variables vào operand stack.
- `iadd`: cộng hai giá trị `int`.
- `ireturn`: trả kết quả.

Đây là **bytecode**, không phải mã máy x86/ARM, và một bản JDK/compiler khác có thể tạo instruction sequence khác nhưng vẫn cùng ý nghĩa.

### 2.1. Vì sao không compile ngay mọi method?

JIT-compile mọi class trong lúc start có thể tăng:

- Thời gian trước khi ứng dụng sẵn sàng.
- CPU dành cho compiler threads.
- Số lượng mã máy phải lưu trong code cache.
- Bộ nhớ cần cho profiling và dữ liệu biên dịch.

Trong ứng dụng rất lớn, nhiều method **không bao giờ được gọi** ở workload cụ thể. Interpreter giúp chạy phần ít phổ biến mà không phải trả trước chi phí tối ưu mạnh.

### 2.2. Interpreter không đồng nghĩa “không được tối ưu bất kỳ điều gì”

Ngay cả khi một method đang chạy dạng interpreted, runtime vẫn có thể dùng metadata, resolution/caching và các cơ chế HotSpot hỗ trợ để thực thi hiệu quả hơn so với cách diễn giải “đọc file bytecode từ đĩa cho từng instruction”. Tuy nhiên mức hiệu năng của interpreter thường thấp hơn compiled code cho vòng lặp CPU-bound đủ nóng.

## 3. JIT là gì và tại sao runtime profile quan trọng?

JIT theo dõi những **phần mã được chạy thường xuyên** (*hot spots*) để quyết định nơi nên đầu tư compile. Thông tin runtime có thể gồm:

- Số lần gọi method.
- Số lần quay lại đầu vòng lặp (*backedges*).
- Loại class thực tế xuất hiện ở một call site.
- Nhánh nào thường được chọn.
- Thông tin về receiver hoặc tình huống runtime hữu ích cho tối ưu.
- Những thống kê khác do implementation thu thập.

Giả sử:

```java
interface PriceRule {
    int apply(int price);
}

final class StandardRule implements PriceRule {
    public int apply(int price) {
        return price - 5;
    }
}
```

Nếu tại một điểm gọi `rule.apply(price)` gần như luôn gặp `StandardRule`, HotSpot có thể tạo mã máy chuyên biệt cho trường hợp phổ biến đó, thay vì xử lý đầy đủ mọi triển khai interface ở mọi lần gọi.

**Điều này chỉ an toàn khi có cách kiểm tra hoặc xử lý tình huống giả định không đúng**. Khi về sau có một `PriceRule` khác, chương trình vẫn phải trả kết quả đúng.

### 3.1. Hot không có nghĩa “gọi đúng 10.000 lần”

Không nên học thuộc một ngưỡng kiểu “sau 10.000 lần, method chắc chắn được C2 compile”. Chính sách của HotSpot phụ thuộc tiered compilation, số vòng lặp, tốc độ phát sinh event, hàng đợi compiler, kích thước method, cấu hình JVM và nhiều yếu tố.

Một method có thể được compile nhiều phiên bản; một loop có thể được biên dịch theo **OSR** trước khi method entry được tối ưu hoàn chỉnh.

## 4. Tiered compilation: kết hợp interpreter, C1 và C2

**Tiered compilation được bật mặc định trong cấu hình HotSpot Java 27 thông thường**, sử dụng cả C1 (client compiler) và C2 (server compiler), theo Java SE 27 GC Ergonomics Guide.

- **Interpreter**: khởi chạy bytecode và có thể thu thông tin cơ bản.
- **C1**: biên dịch nhanh để sớm chuyển method sang machine code; có các mức thu thập profile khác nhau.
- **C2**: dùng nhiều thông tin runtime để tối ưu sâu; có thể mất nhiều thời gian/CPU hơn cho một compilation.

Mục tiêu không chỉ tối đa hóa throughput dài hạn mà còn cân bằng **startup, warm-up, footprint và peak performance**.

### 4.1. Năm execution levels trong HotSpot

| Level | Hình thức thực thi | Mục đích điển hình |
| --- | --- | --- |
| **0** | Interpreter | Thực thi bytecode, bắt đầu profiling |
| **1** | C1 không profiling | Mã máy nhanh với chi phí profile thấp |
| **2** | C1 profiling giới hạn | Mã máy và một số bộ đếm invocation/backedge |
| **3** | C1 profiling đầy đủ hơn | Thu profile phong phú cho compilation tiếp theo |
| **4** | C2 tối ưu mạnh | Machine code tối ưu theo profile, hướng tới hiệu năng ổn định |

Đây là các **level của HotSpot**, không phải năm “thế hệ JIT” hoặc năm giai đoạn mà **mọi method bắt buộc phải đi qua**.

Một đường chuyển đổi thường gặp:

```text
Level 0 (Interpreter)
       |
       v
Level 3 (C1 + profiling)
       |
       v
Level 4 (C2 optimized)
```

Nhưng còn những đường đi khác:

```text
Level 0 --> Level 2 --> Level 3 --> Level 4
       \--> Level 1
       \--> Level 4 (trong điều kiện nhất định)
```

Heuristics có thể tránh các level không cần thiết, thay đổi kế hoạch compile do độ dài compiler queue hoặc giữ một method ở level thấp nếu không đáng đầu tư thêm.

### 4.2. Tại sao C1 và C2 cần cùng tồn tại?

C1 thường cho **machine code sớm** với chi phí compile thấp; C2 thường cung cấp **tối ưu sâu hơn** khi có đủ profile. Một phương thức thường chạy lâu có thể hưởng lợi từ C2. Một method rất ngắn, ít dùng hoặc nằm trong đường khởi động có thể không cần phải đạt level 4.

Không nên kết luận “level 4 là chuẩn đúng, các level khác là lỗi hiệu năng”. Mỗi mức phục vụ một trade-off khác nhau.

### 4.3. Compiler threads và compilation queue

C1/C2 thường chạy trên **compiler threads** của HotSpot; khi một version mới đang được compile, code cũ/interpreter vẫn có thể tiếp tục phục vụ ứng dụng.

Nếu compiler queue dài hoặc compiler CPU cao, warm-up có thể chậm hơn. Cũng cần hiểu rằng việc tăng số compiler threads không bảo đảm ứng dụng nhanh hơn: chúng dùng CPU/bộ nhớ và có thể cạnh tranh với worker threads/GC.

## 5. Compilation không đồng nghĩa tất cả code thành mã máy một lần

Có ít nhất ba trạng thái đáng phân biệt:

1. Method chưa có compiled entry, đang thực thi qua interpreter.
2. Method có compiled version C1 và vẫn tiếp tục thu profile.
3. Method có version được tối ưu bằng C2, nhưng một số đường đi hoặc guard vẫn có thể đưa execution về runtime/interpreter.

Compiled code có thể được **thay thế, đánh dấu không còn được dùng, quét khỏi code cache hoặc deoptimize** khi điều kiện thay đổi. Việc nhìn thấy “method đã compile” trong log không đảm bảo mọi invocation tương lai luôn chạy cùng một bản machine code.

### 5.1. Code cache là gì?

**Code cache** chứa native code mà JIT tạo và các phần code runtime khác. Nó **không phải Java heap chứa object nghiệp vụ**.

```text
JVM Process Memory (sơ lược)
+----------------------------------------+
| Java Heap                              |
|  Objects, arrays, application data     |
+----------------------------------------+
| Metaspace / class metadata             |
+----------------------------------------+
| Code cache                             |
|  JIT compiled machine code             |
|  Interpreter/runtime stubs             |
+----------------------------------------+
| Thread stacks, GC/JIT native memory... |
+----------------------------------------+
```

Sơ đồ chỉ để định hướng. Layout chi tiết phụ thuộc JVM, OS và chính sách cấp phát.

**Không suy ra `-Xmx` giới hạn toàn bộ bộ nhớ của process.** Heap chỉ là một phần; code cache, metaspace, thread stacks, direct buffers và native allocations có footprint riêng.

## 6. Các tối ưu JIT thường dùng

HotSpot có thể áp dụng nhiều tối ưu theo ngữ nghĩa chương trình và profile. Mức độ thực tế phụ thuộc compiler và target platform.

| Tối ưu | Ý tưởng | Điều kiện/giới hạn |
| --- | --- | --- |
| Method inlining | Đưa code callee vào caller | Heuristics kích thước, profile, call-site shape |
| Devirtualization | Chuyên biệt lời gọi ảo theo kiểu mục tiêu thực tế | Có guard/đường dự phòng khi profile đổi |
| Constant folding | Tính trước biểu thức có giá trị xác định | Không được đổi hiệu ứng quan sát được |
| Dead-code elimination | Bỏ công việc không ảnh hưởng kết quả | Không bỏ side effect hợp lệ |
| Loop optimization | Tối ưu các phép lặp, hoisting hoặc unrolling có điều kiện | Phải bảo toàn thứ tự hiệu ứng và kiểm tra |
| Escape analysis | Xem object có thoát khỏi phạm vi phân tích không | Hỗ trợ scalar replacement/lock elimination |
| Range-check elimination | Tránh kiểm tra trùng lặp khi chứng minh an toàn | Phải giữ hành vi exceptions khi vi phạm |
| Intrinsics | Thay một số thao tác thành mã chuyên biệt | Phụ thuộc JDK, CPU, flags và API |

Những tên gọi này mô tả **khả năng**, không phải đảm bảo “mỗi lần viết vòng lặp JIT sẽ vectorize”.

### 6.1. Inlining và devirtualization

Ví dụ:

```java
interface FeeRule {
    int apply(int cents);
}

static int calculate(FeeRule rule, int cents) {
    return rule.apply(cents);
}
```

Nếu call site chủ yếu nhận một type, JIT có thể lập kế hoạch kiểm tra receiver type rồi inline nhánh phổ biến. Nếu sau đó một type khác xuất hiện, guard có thể đưa tới nhánh phù hợp hoặc kích hoạt deoptimization.

Điểm quan trọng: **Java vẫn phải hỗ trợ mọi implementation hợp lệ của `FeeRule`**. Profile chỉ tạo cơ hội tối ưu, không được thay đổi contract của interface.

### 6.2. Escape analysis và object allocation

```java
record Point(int x, int y) { }

static int distanceLike(Point point) {
    return point.x() * point.x() + point.y() * point.y();
}

static int compute(int x, int y) {
    return distanceLike(new Point(x, y));
}
```

Nếu C2 chứng minh object `Point` không cần tồn tại như một object heap quan sát được, nó **có thể** loại allocation qua **scalar replacement**. Nhưng:

- Không có cam kết rằng code trên luôn được tối ưu thành không allocation.
- `record` không tự đồng nghĩa “object nằm trên stack”.
- Không nên thay thiết kế API rõ ràng bằng một lượng lớn manual object reuse chỉ dựa trên suy đoán của lập trình viên.

**Tài liệu HotSpot Java 27 giải thích escape analysis có thể loại allocation và lock, không khẳng định thay mọi heap allocation bằng stack allocation.**

## 7. OSR: tối ưu một vòng lặp đang chạy

**On-Stack Replacement (OSR)** cho phép HotSpot chuyển **ngay trong khi đang chạy** một đoạn vòng lặp từ interpreted/C1 code sang một compiled version phù hợp, thường tại *backedge*.

```java
static long longLoop(int iterations) {
    long sum = 0L;
    for (int i = 0; i < iterations; i++) {
        sum += (i * 31L) ^ (i >>> 3);
    }
    return sum;
}
```

Ngay cả khi method `longLoop` chỉ được gọi **một lần**, vòng lặp chạy rất nhiều iteration có thể được xem là hot. JVM không bắt buộc đợi method kết thúc rồi gọi lại hàng nghìn lần mới có thể compile.

```text
longLoop() enter
      |
      v
Interpreter chạy vòng lặp, đếm backedges
      |
      +---- OSR compile request ----> compiled OSR entry
      |                                 |
      +----------- chuyển tại điểm phù hợp
                                        |
                                        v
                            chạy phần còn lại bằng mã máy
```

**OSR không phải deoptimization.** OSR là quá trình *đưa execution vào compiled code* của đoạn đang chạy; deoptimization là quá trình *rời compiled code đã tối ưu* khi cần để bảo toàn hành vi.

### 7.1. Nhận biết OSR trong compile log

Với `-XX:+PrintCompilation`, một số dòng có ký hiệu `%` để cho biết compilation là **OSR**. Dòng log và tier level thực tế có thể khác theo version/runtime/workload; không khẳng định mọi vòng lặp đủ số iteration nhất định sẽ sinh dấu `%`.

## 8. Speculative optimization: tối ưu dựa trên giả định có kiểm soát

JIT không chỉ tối ưu những điều có thể suy ra hoàn toàn từ bytecode. Nó còn có thể dùng profile để “đặt cược” vào trường hợp phổ biến, nhưng vẫn phải giữ **đường xử lý đúng** nếu điều kiện đổi.

Ví dụ:

```java
interface Parser {
    int parse(String input);
}

static int useParser(Parser parser, String input) {
    return parser.parse(input);
}
```

Nếu tại `useParser` chỉ thấy một implementation trong phần warm-up, JIT có thể:
1. Dựa vào dữ liệu type profile hoặc class hierarchy để tối ưu lời gọi ảo.
2. Inline code của implementation phổ biến.
3. Giữ guard hoặc dependency cần thiết để nhận ra khi giả định không còn hợp lệ.

Sau đó một implementation mới xuất hiện, HotSpot có thể **deoptimize** hoặc chọn một đường khác.

### 8.1. Profile là dữ liệu quan sát, không phải luật tương lai

Giả sử 100.000 request đầu đều có cùng loại payload, nhưng 100.001 request kế tiếp đến từ một tenant có kiểu dữ liệu khác. JVM phải vẫn xử lý đúng, dù profile trước đó thiên về kiểu đầu tiên.

Đây là lý do C2 có thể tối ưu mạnh mà không biến các điều kiện runtime thành giả định vô điều kiện.

## 9. Deoptimization là gì?

**Deoptimization** là cơ chế HotSpot **từ bỏ một phiên bản mã đã tối ưu** khi giả định của phiên bản đó không còn hợp lệ hoặc cần chuyển sang trạng thái thực thi khác, rồi khôi phục trạng thái chương trình để tiếp tục đúng ngữ nghĩa.

```text
Compiled C2 code
      |
      | Guard/uncommon trap hoặc compiled-code dependency bị vô hiệu
      v
Deoptimization
      |
      | Tái tạo trạng thái Java-level tương ứng
      | (locals, operand stacks, frames inlined nếu cần)
      v
Interpreter / đường code an toàn
      |
      | Profile mới, heuristics quyết định
      v
Có thể compile lại
```

Deoptimization thường gắn với **speculation**, nhưng không nên khẳng định nó chỉ có một nguyên nhân.

Các nhóm lý do minh họa:

- Type profile thay đổi ở call site.
- Class hierarchy thay đổi do class mới được load, làm invalid một số giả định.
- Đường đi “hiếm” mà compiled code không tối ưu sẵn nay được thực thi.
- Một điều kiện runtime hoặc dependency khiến phiên bản code hiện tại không còn phù hợp.

**Deoptimization không có nghĩa JVM bỏ qua các tác dụng phụ đã xảy ra** hoặc thực thi lại toàn bộ request từ đầu. Runtime phải dựng lại execution state phù hợp để tiếp tục có ngữ nghĩa đúng.

### 9.1. “Uncommon trap” có nghĩa gì?

JIT có thể tối ưu nhánh thường gặp và đặt một **uncommon trap** cho trường hợp nó dự đoán là hiếm. Khi nhánh hiếm thực sự xảy ra, trap chuyển điều khiển về runtime, có thể dẫn tới deoptimization.

Ví dụ khái niệm:

```java
static int score(Object value) {
    if (value instanceof String s) {
        return s.length();
    }
    return 0;
}
```

Nếu hầu hết lần chạy có `String`, JIT có thể tối ưu cho nhánh đó. Khi bỗng xuất hiện `Integer`, chương trình vẫn phải trả `0`, có thể qua guard hoặc đường ít phổ biến. **Không được khẳng định một invocation `Integer` chắc chắn tạo uncommon trap**; C2 có thể đã sinh đầy đủ nhánh dự phòng hoặc dùng một chiến lược khác.

### 9.2. Deopt không phải exception của ứng dụng

| Hiện tượng | Ý nghĩa |
| --- | --- |
| `NullPointerException` | Exception theo ngữ nghĩa Java, ứng dụng cần xử lý/sửa nếu không mong muốn |
| Deoptimization | JVM đổi cách thực thi compiled code để bảo toàn ngữ nghĩa |
| Compilation failure | Runtime không tạo được một compiled version cụ thể, có thể tiếp tục bằng code khác |
| Code cache full | Áp lực dung lượng vùng native code, có thể hạn chế compilation mới |
| `OutOfMemoryError` | Lỗi cấp phát hoặc giới hạn một loại tài nguyên; không đồng nhất với deopt |

Ứng dụng không nên bắt hoặc xử lý deoptimization như một exception thông thường; nó là cơ chế nội bộ của runtime.

## 10. Vì sao deoptimization cần khôi phục frame?

C2 có thể inline nhiều method vào nhau, loại bỏ allocation hoặc tối ưu giá trị trung gian. Vì vậy stack frame vật lý ở compiled code có thể **không giống từng Java method frame** như interpreter.

Khi deopt, JVM dùng metadata/debug information đi kèm compiled code để phục dựng trạng thái tương ứng với execution bytecode, gồm các frame đã được inline, local values và điểm tiếp tục.

**Khả năng dựng lại trạng thái là điều kiện để speculative optimization an toàn.** Nếu JVM không thể khôi phục trạng thái đúng ở một điểm cần deopt, loại tối ưu đó không được áp dụng theo cách ấy.

### 10.1. Escape analysis và deopt cùng tồn tại như thế nào?

Nếu JIT đã scalar-replace một object và sau đó cần chuyển về interpreter ở điểm đòi object reference thật, runtime có thể phải **materialize object** tương ứng trong quá trình khôi phục state.

Đừng hiểu “không thấy allocation trong benchmark hot path” nghĩa JVM đã thay đổi Java object identity hoặc xóa các semantics mà chương trình được phép quan sát.

### 10.2. Deoptimization có tác động hiệu năng không?

Có thể có. Việc chuyển state, hủy compiled version hoặc compile lại tiêu tốn CPU và có thể gây biến thiên latency. Nhưng:
- Một vài deopt trong warm-up là hiện tượng bình thường.
- Không phải mọi deopt đều gây ảnh hưởng đáng kể đến p99.
- Chỉ khi xảy ra nhiều lần trên hot path hoặc kéo theo compile churn mới đáng điều tra sâu.

## 11. Ví dụ thực hành: quan sát compile, warm-up và thay đổi type profile

Chương trình dưới đây cố ý gọi một interface method rất nhiều lần, sau đó thay implementation. Nó **không bảo đảm** tạo deopt trên mọi máy/JDK — đây là ví dụ quan sát JIT và tính đúng đắn khi profile thay đổi.

```java
public final class TieredCompilationDemo {
    interface FeeRule {
        int apply(int amount);
    }

    static final class StandardRule implements FeeRule {
        @Override
        public int apply(int amount) {
            return amount - 5;
        }
    }

    static final class PremiumRule implements FeeRule {
        @Override
        public int apply(int amount) {
            return amount - 7;
        }
    }

    private static volatile long sink;

    static long calculate(FeeRule rule, int rounds) {
        long total = 0;

        for (int i = 0; i < rounds; i++) {
            total += rule.apply(i & 1_023);
        }

        return total;
    }

    public static void main(String[] args) {
        FeeRule standard = new StandardRule();

        // Giai đoạn warm-up: call site chủ yếu thấy StandardRule.
        for (int i = 0; i < 40_000; i++) {
            sink = calculate(standard, 1_024);
        }

        FeeRule premium = new PremiumRule();

        // Bây giờ call site của calculate nhận thêm một kiểu.
        long afterChange = calculate(premium, 1_024);
        sink = afterChange;

        System.out.println("Result: " + sink);
        // Kết quả phải đúng, bất kể HotSpot chọn interpreter/C1/C2.
    }
}
```

Biên dịch:

```text
javac TieredCompilationDemo.java
```

Thực thi bình thường và in hoạt động biên dịch:

```text
java -XX:+PrintCompilation TieredCompilationDemo
```

Các dòng log sẽ đan xen với output ứng dụng. Có thể thấy level và một số phương thức được compile/đánh dấu không dùng nữa, nhưng **không nên đoán số dòng, thời điểm hay một sự kiện deopt cụ thể** vì khác biệt giữa các lần chạy và cấu hình.

Ví dụ này có lượng lặp đủ lớn để dễ quan sát JIT trên nhiều môi trường nhưng vẫn cần hạn chế chạy trên hệ thống chia sẻ/tải cao; không đưa benchmark mẫu làm tải không kiểm soát lên production.

### 11.1. So sánh với interpreter-only

```text
java -Xint TieredCompilationDemo
```

`-Xint` yêu cầu HotSpot chạy bytecode bằng interpreter, tắt JIT compilation. Lệnh này có thể **chậm hơn nhiều** với ví dụ CPU-bound ở trên.

Chạy lại mặc định:

```text
java TieredCompilationDemo
```

Khác biệt về thời gian phản ánh **rất nhiều yếu tố** gồm interpreter, warm-up, compilation, CPU scheduling, JVM setup. Không lấy hai lần đo thô làm benchmark công bố số liệu.

### 11.2. Chú ý những gì cần ghi nhận

- Kết quả phải giống nhau giữa `-Xint` và chế độ bình thường.
- Mức CPU compiler và application khác nhau theo giai đoạn.
- Code được compile không nhất thiết chỉ sau khi method được gọi nhiều lần; OSR có thể xảy ra.
- Một type mới không bắt buộc luôn kích hoạt deopt.
- Kết quả hiệu năng giữa hai lần chạy có thể khác do JIT background scheduling và môi trường.

## 12. Các flag Java 27 để quan sát JIT

Những tùy chọn dưới đây vẫn có trong **Java 27 HotSpot**. Chúng dùng cho **học tập/chẩn đoán có kiểm soát**, không phải cấu hình mặc định khuyến nghị cho production.

| Flag / command | Mục đích |
| --- | --- |
| `-Xint` | Chạy interpreter-only; tắt JIT |
| `-Xmixed` | Trộn interpreter và compiled hot methods (mặc định) |
| `-Xcomp` | Chế độ kiểm thử để ép nhiều compilation; **không dùng cho production** |
| `-XX:+PrintCompilation` | In các hoạt động compile lên console |
| `-XX:-TieredCompilation` | Tắt tiered compilation; **không** đồng nghĩa tắt JIT |
| `-XX:ReservedCodeCacheSize=<size>` | Thay giới hạn code cache (khi có lý do đo đạc) |
| `-XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation` | Ghi XML compilation log chuyên sâu |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | In quyết định inlining |
| `-XX:CompileCommand=...` | Chỉ dẫn trình biên dịch cho method cụ thể; dùng thận trọng |

Ví dụ:

```text
java -XX:+PrintCompilation TieredCompilationDemo

java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation TieredCompilationDemo

java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining TieredCompilationDemo
```

`LogCompilation` mặc định có thể ghi tệp `hotspot.log` trong thư mục chạy (hoặc đường dẫn do `-XX:LogFile` định nghĩa). Log có thể lớn, gây overhead và chứa metadata lớp/phương thức; không bật lâu dài trên production một cách tùy tiện.

### 12.1. Mẫu output của `PrintCompilation`

Một dòng được giản lược có thể có dạng:

```text
  100  123       3       TieredCompilationDemo::calculate (40 bytes)
```

Đây chỉ là **minh họa định dạng**, không phải output bảo đảm từ chương trình. Trong nhiều bản HotSpot, số level như `3` hoặc `4` thể hiện compilation tier; ký hiệu `%` cho OSR, `!` cho method có exception handler trong một số format, và các dấu trạng thái có thể khác giữa các phiên bản.

Không gán nhãn “đã deopt” chỉ vì nhìn thấy một số hiệu đặc biệt mà chưa xác định format của bản HotSpot thực tế. Dùng tài liệu công cụ và log chi tiết khi cần chứng minh nguyên nhân.

### 12.2. Vì sao không bật `-Xcomp` để ứng dụng “chạy nhanh”?

Tài liệu `java` của Java 27 mô tả `-Xcomp` là chế độ **kiểm thử JIT compilers**, không khuyến nghị production. Ép compilation có thể tăng startup cost, compilation pressure và làm thiếu runtime profile hữu ích.

Để ứng dụng tự chọn khi nào compile thường phù hợp hơn. Cần tối ưu startup hãy đo bằng workload và cân nhắc những cơ chế startup/runtime hiện đại được JDK hỗ trợ thay vì ép JIT compile tất cả.

## 13. `jcmd`: quan sát trạng thái compiler và code cache

`jcmd` là công cụ chẩn đoán JDK; câu lệnh chi tiết phụ thuộc JVM và những diagnostic commands đang được hỗ trợ.

Đầu tiên liệt kê JVM có thể attach:

```text
jcmd -l
```

Xem lệnh mà JVM đích hỗ trợ:

```text
jcmd <pid> help
```

Những lệnh HotSpot thường hữu ích:

```text
jcmd <pid> Compiler.codecache
jcmd <pid> Compiler.queue
jcmd <pid> Compiler.codelist
```

Ý nghĩa:

- `Compiler.codecache`: trạng thái/bố trí vùng code cache.
- `Compiler.queue`: các method đang chờ compilation.
- `Compiler.codelist`: danh sách compiled methods đang có trong code cache (có thể lớn).

**Đừng coi queue rỗng tại một snapshot nghĩa JIT không hoạt động.** Có thể công việc compile đã hoàn tất, hàng đợi tạm thời rỗng hoặc ứng dụng ít hot methods.

### 13.1. Khi nào code cache cần điều tra?

- Log/metrics cho thấy code cache gần đầy.
- JVM cảnh báo về JIT/code cache hoặc compilation bị hạn chế.
- Throughput/latency thay đổi sau khi tải hoặc triển khai thêm nhiều code paths.
- Lượng compiled code tăng theo hoạt động nạp class/hot-reload.

Bộ nhớ code cache **không** tăng giống heap của object Java. Với tiered compilation, HotSpot có thể dùng **segmented code cache** gồm vùng non-method, profiled và non-profiled code; tỷ lệ sử dụng của từng vùng cũng đáng quan sát.

Tránh tăng ngay `ReservedCodeCacheSize` chỉ vì thấy số liệu lớn: trước hết xác định nguyên nhân compilation, phạm vi code và áp lực native memory của process.

## 14. Java Flight Recorder: xem JIT trên timeline

**Java Flight Recorder (JFR)** có thể ghi những sự kiện liên quan compilation và runtime performance, tùy profile/cấu hình sự kiện. Đây là cách phù hợp để đối chiếu:

- CPU compiler threads.
- Compile events và thời lượng compilation.
- Code cache pressure.
- Thời gian khởi động/warm-up.
- GC pauses và allocation.
- Latency request trong cùng khoảng thời gian.

Bắt đầu một recording ngắn khi được phép:

```text
jcmd <pid> JFR.start name=JitStudy settings=profile duration=60s filename=jit-study.jfr
```

Xem trạng thái:

```text
jcmd <pid> JFR.check
```

Mở tệp `.jfr` bằng Java Mission Control hoặc công cụ JFR được hỗ trợ. **Không giả định `settings=profile` mặc định bật tất cả sự kiện deoptimization hoặc compiler phases với mức chi tiết cần thiết.** Hãy kiểm tra event configuration trên JDK thật trước khi kết luận “không có sự kiện = không có deopt”.

### 14.1. Mẫu phân tích timeline

```text
Ứng dụng khởi động
    |
    +-- compiler CPU tăng, nhiều methods được compile
    |
    +-- request latency giảm dần sau warm-up
    |
    +-- tải thay đổi, xuất hiện type profiles khác
    |
    +-- JIT/deopt activity tăng nếu có assumptions bị phá
    |
    +-- latency/throughput đạt trạng thái mới
```

Đây là giả thuyết điều tra, **không phải quy luật**. CPU có thể bận vì GC, JSON parsing, network TLS, class loading hoặc một tác vụ khác; cần đối chiếu các sự kiện, không đổ mọi thay đổi latency cho JIT.

## 15. Tiered compilation và GC: liên quan nhưng không đồng nhất

Bài này thuộc chương JVM, bộ nhớ và GC vì JIT ảnh hưởng đến việc tạo object và phân bổ CPU; nhưng **GC và JIT có vai trò khác nhau**:

- **JIT:** tối ưu cách thực thi bytecode và tạo compiled machine code.
- **GC:** xác định object còn sống và thu hồi vùng heap có thể tái sử dụng.
- **Runtime memory manager:** quản lý nhiều vùng nhớ khác nhau, không chỉ heap.

Ví dụ nếu escape analysis loại một allocation, GC có thể phải xử lý ít object hơn. Nếu JIT compile một method tốn nhiều CPU, thread biên dịch có thể cạnh tranh tài nguyên với GC và application threads. Nhưng **không có quan hệ trực tiếp “GC chạy thì JIT deopt” trong mọi trường hợp**.

### 15.1. Code cache không nằm trong heap do GC quản lý

Không xử lý cảnh báo code cache bằng cách tùy tiện tăng `-Xmx` và mong heap size giải quyết mọi vấn đề. Cần đo riêng:

| Triệu chứng | Nơi cần xem |
| --- | --- |
| Heap used sau GC tăng liên tục | Object retention, allocation, GC |
| Compiler CPU cao lúc warm-up | Compilation events, code hotness, compiler queues |
| Code cache gần đầy | `Compiler.codecache`, `ReservedCodeCacheSize` và profile compiled code |
| RSS tăng nhưng heap ổn định | Metaspace, code cache, threads, direct/native memory |
| Latency tăng khi classpath/traffic thay đổi | Class loading, JIT activity, GC và workload đồng thời |

Native Memory Tracking (NMT) có thể hỗ trợ xem một số vùng native memory của JVM, nhưng phải bật theo hướng dẫn JVM và không bảo đảm đo mọi cấp phát từ native libraries ngoài JVM.

### 15.2. Đừng tối ưu GC khi vấn đề là cold code

Nếu benchmark chỉ chạy vài giây và đa số thời gian dành cho class loading/JIT compilation, việc đổi GC có thể không giải quyết mục tiêu. Ngược lại, một dịch vụ đã warm-up ổn định mà có GC pauses cao cần phân tích heap/liveness, không mặc định “thiếu JIT”.

## 16. Warm-up: startup latency khác steady-state throughput

Hai mục tiêu thường xung đột:

- **Time to first response / startup:** có thể quan trọng với CLI, serverless, batch jobs ngắn.
- **Steady-state throughput:** quan trọng với service chạy lâu.
- **Tail latency:** quan trọng với p95/p99/p99.9 response times.
- **Memory footprint:** quan trọng trong container hoặc thiết bị giới hạn RAM.

JIT có thể cải thiện throughput sau khi warm-up nhưng tiêu thụ tài nguyên trong giai đoạn compile. Vì vậy một phương án tốt cho server chạy nhiều ngày chưa chắc phù hợp với một lệnh CLI chạy dưới một giây.

### 16.1. Tiered compilation đã tối ưu cân bằng mặc định

Theo Java 27 docs, mặc định HotSpot bật tiered compilation. Trước khi thay:
- Đo workload đại diện.
- Xác định metric cần cải thiện.
- So sánh bản JDK/heap/container/cgroup và CPU budget.
- Quan sát compiler threads, code cache và GC.
- Chỉ thay flag trong thử nghiệm có thể rollback.

Không áp dụng những hướng dẫn bắt buộc `-server`, chỉnh `CompileThreshold` cố định hoặc tắt tiered compilation từ một bài viết nhiều năm trước mà không xác minh tài liệu Java 27.

### 16.2. AOT cache không đồng nghĩa vô hiệu JIT

Các bản JDK hiện đại có cơ chế **ahead-of-time cache** cho một số dữ liệu/hoạt động chuẩn bị runtime nhằm cải thiện startup. Những cơ chế này có thể **bổ trợ** việc biên dịch lúc chạy; không nên nói “có AOT thì toàn bộ JVM không cần JIT nữa”.

Nếu một dự án dùng AOT cache/CDS, hãy kiểm thử startup, chất lượng profile và môi trường deploy bằng cùng một JDK và cấu hình có hỗ trợ. Trọng tâm bài này vẫn là interpreter, JIT và deoptimization.

## 17. Benchmark đúng cách: không “benchmark JIT” bằng một vòng lặp tùy ý

Ví dụ không đáng tin:

```java
long start = System.nanoTime();

for (int i = 0; i < 10_000; i++) {
    Math.abs(i);
}

System.out.println(System.nanoTime() - start);
```

Compiler có thể loại công việc không có kết quả quan sát được; thời gian đo còn trộn class loading, compilation, OS scheduling và nhiệt độ CPU. Con số thấp không chứng minh `Math.abs` chạy nhanh với mọi workload.

### 17.1. Thực hành benchmark tốt hơn

Đối với microbenchmark cần số liệu đáng tin, dùng **JMH (Java Microbenchmark Harness)** và thiết kế workload phù hợp, bao gồm:

1. Có warm-up hợp lý, theo dõi khi nào đến steady state.
2. Lặp lại nhiều phép đo, nhiều fork process khi cần.
3. Dùng dữ liệu đầu vào thay đổi có kiểm soát, không tạo tình huống compiler bỏ toàn bộ phép tính.
4. Không đặt allocation, logging, I/O ở vị trí không thuộc bài toán cần đo.
5. Báo JVM version, CPU, OS, flags, container limits và GC.
6. Tách throughput, latency, allocation rate và compilation effort.
7. Không áp dụng microbenchmark cho toàn bộ kiến trúc mà không đo workload thực.

**Một benchmark Java tốt đo tác vụ, không cố ép “có deopt” bằng cách phá ngữ nghĩa chương trình**. Muốn nghiên cứu sự kiện nội bộ cần công cụ JVM và test có kiểm soát.

### 17.2. Tại sao “warm-up 10 giây” không phải quy tắc chung?

Ứng dụng ít class, nhiều CPU loops có thể warm-up nhanh; hệ thống nhiều dependency, nhiều endpoint hiếm và nhiều dynamic type có thể warm-up theo **lưu lượng thật** lâu hơn đáng kể. Tốt nhất là theo dõi compilation rate và kết quả thực tế, không lấy một số giây cố định làm bảo đảm.

## 18. Khi nào nên can thiệp compilation policy?

Trong nhiều ứng dụng, nên **giữ mặc định**. Chỉ cân nhắc flags khi có bằng chứng cụ thể:

| Bối cảnh | Hướng xử lý trước khi đổi flags |
| --- | --- |
| Startup quá lâu | Phân tích class loading, dependency initialization, JFR startup và JIT CPU |
| CPU compile chiếm nhiều khi warm-up | Kiểm tra hot methods, số core, compiler queues |
| Steady-state throughput thấp | Profile application hot path, allocation, locking, I/O |
| Code cache pressure | Xem `Compiler.codecache`, class loading/code churn |
| Deoptimization lặp nhiều | Xem type profiles, dynamic class changes, uncommon traps và hot spots |
| Kết quả benchmark không ổn định | Thiết kế lại measurement/warm-up và nhiều forks |

Không dùng `-Xint` hoặc `-XX:-TieredCompilation` làm giải pháp tối ưu sản xuất chỉ vì một thử nghiệm ngắn thấy startup nhanh hơn. Mỗi thay đổi ảnh hưởng những mục tiêu khác nhau và có thể làm throughput dài hạn tệ đi.

### 18.1. Compiler directives và `CompileCommand`

HotSpot có hệ thống compiler directives/`-XX:CompileCommand` cho trường hợp chẩn đoán chuyên sâu, như giới hạn compilation hoặc quan sát một method.

Đây là công cụ **can thiệp compiler**, không phải public API bảo đảm kết quả ứng dụng nhanh hơn. Ví dụ loại một method khỏi compilation có thể hữu ích khi cô lập một lỗi HotSpot cụ thể, nhưng cũng có thể làm dịch vụ chậm đi đáng kể. Không đổi compiler policy trong production chỉ để “thử vận may”.

## 19. Các hiểu nhầm và lỗi thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`javac` chính là JIT” | `javac` tạo bytecode trước khi chạy; JIT tạo native code trong runtime |
| “Java luôn được interpreter chạy mọi dòng” | HotSpot có thể compile hot methods/loops thành mã máy |
| “Mọi method đều qua level 0 → 1 → 2 → 3 → 4” | Tier policy chọn nhiều đường và có thể bỏ qua level |
| “C1 là JIT cũ không còn dùng” | C1 vẫn tham gia tiered compilation mặc định của HotSpot Java 27 |
| “C2 luôn compile ngay từ startup” | Compiler dựa vào heuristics/profile và queue |
| “Sau đúng N lần gọi sẽ compile” | Thresholds động, tính cả backedges, kích thước và trạng thái runtime |
| “OSR và deoptimization là một” | OSR đưa loop đang chạy vào compiled code; deopt rời code không còn phù hợp |
| “Deopt = application bug” | Deopt thường là fallback hợp lệ của speculative optimization |
| “JVM chạy lại request từ đầu khi deopt” | Runtime phục dựng execution state tại điểm tiếp tục phù hợp |
| “C2 đã inline method thì type khác sẽ bị xử lý sai” | Guards/deoptimization giữ ngữ nghĩa Java |
| “Record được JIT đảm bảo allocate trên stack” | Escape analysis có thể loại allocation; không có cam kết mọi trường hợp |
| “Đổi GC sẽ xóa mọi JIT latency” | GC/JIT khác trách nhiệm; phải đo nguồn gốc |
| “Tăng `-Xmx` giải quyết code cache full” | Code cache là vùng bộ nhớ khác với Java heap |
| “`-Xcomp` là production performance flag” | Là chế độ kiểm thử JIT, không khuyến nghị production |
| “`-Xint` nhanh thì tắt JIT vĩnh viễn là tốt” | Startup và steady-state throughput khác nhau |
| “Một lần `PrintCompilation` phản ánh toàn bộ deopt” | Output phụ thuộc cấu hình và không phải trace đầy đủ mọi runtime event |
| “Có JIT rồi benchmark vòng lặp một lần là đủ” | Warm-up, compiler optimization và môi trường làm số liệu sai lệch |
| “Java 27 bắt buộc mọi JVM dùng C1/C2” | C1/C2 là chi tiết HotSpot, không phải yêu cầu JVM Specification |

## 20. Checklist điều tra JIT trong Java 27

Trước khi kết luận hiệu năng bị ảnh hưởng bởi JIT, hãy trả lời:

1. JVM đang dùng có thật là **HotSpot/OpenJDK Java 27** không?
2. Workload là CLI ngắn hay service chạy lâu? Mục tiêu là startup, throughput hay p99?
3. Tiered compilation có đang bật như mặc định không?
4. Có evidence từ JFR, compiler log hoặc `jcmd` về compile queue/code cache không?
5. Hot methods và số lần gọi/backedges đã đủ để xét JIT chưa?
6. Sự kiện xảy ra trong giai đoạn warm-up hay sau khi ổn định?
7. Type profile có biến đổi theo endpoint, tenant hoặc data distribution không?
8. Có sự kiện deopt thực sự, hay chỉ là suy đoán từ latency?
9. Code cache, heap, metaspace và native memory có được đo riêng không?
10. Có tương quan JIT activity với GC, class loading, threads và I/O không?
11. Benchmark có warm-up/fork/đa lần đo phù hợp và chống dead-code elimination không?
12. Tuning nào được phép rollback và được kiểm tra bằng tải thật?
13. Có dùng flag không còn phù hợp từ hướng dẫn JDK cũ hay không?
14. Sau mọi tối ưu, ứng dụng vẫn cho kết quả đúng và thread-safe chứ?

**Ghi nhớ:** Interpreter giúp Java chạy ngay; C1 tạo compiled code sớm và có thể thu profile; C2 dùng profile để tối ưu sâu; OSR tăng tốc vòng lặp đang chạy; deoptimization giúp HotSpot rời giả định không còn đúng **mà vẫn giữ nguyên ngữ nghĩa Java**. Việc tối ưu đáng tin cậy bắt đầu bằng profile và đo lường, không phải đổi một JVM flag ngẫu nhiên.

## Tài liệu tham khảo chính thức

- [Java SE 27 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/27/vm/index.html): tổng quan HotSpot JVM và compilation.
- [Java SE 27 — HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/27/vm/java-hotspot-virtual-machine-performance-enhancements.html): tiered compilation, segmented code cache và escape analysis.
- [Java SE 27 — Garbage Collection Ergonomics](https://docs.oracle.com/en/java/javase/27/gctuning/ergonomics.html): trạng thái mặc định tiered compilation C1/C2 và các nguyên tắc tuning.
- [Java SE 27 — The `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-Xint`, `-Xcomp`, `-Xmixed`, JIT/compiler flags, code cache và diagnostic options.
- [Java SE 27 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): compiler commands, code cache và JFR.
- [Java SE 27 — The `javap` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): xem bytecode qua `-c`.
- [Java SE 27 — Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/jvms/se27/html/index.html): mô hình bytecode, frame, runtime data areas và ngữ nghĩa thực thi.
- [OpenJDK — HotSpot Tiered Compilation Policy](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): mô tả các level interpreter/C1/C2 trong mã nguồn HotSpot (chi tiết implementation, có thể thay đổi).
- [OpenJDK — Deoptimization Implementation](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/deoptimization.cpp): cơ chế phục dựng interpreter state từ compiled frames (chi tiết implementation).
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): công cụ microbenchmark Java.

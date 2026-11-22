# Phân biệt tối ưu mã do trình biên dịch với bảo đảm của đặc tả Java

*Chủ đề cha: Biên dịch và kiểm chứng — Java 10. Bài Knowledge độc lập giải thích ranh giới giữa **ngữ nghĩa được Java Language Specification (JLS), Java Virtual Machine Specification (JVMS), Java Memory Model (JMM) và Java SE API bảo đảm** với **tối ưu mà `javac` hoặc HotSpot/JIT có thể chọn**. Ví dụ Java biên dịch bằng `--release 17` và chạy trên JDK 17+, sử dụng kiến thức còn áp dụng hiện nay. Các thực nghiệm `javap` và binary compatibility đã được kiểm thử trên OpenJDK 21.*

## 1. Quy tắc ngắn gọn

**Đặc tả quyết định điều gì hợp lệ; implementation quyết định thực hiện nó bằng cách nào.**

Cần tách ba câu hỏi:

1. **Source Java có ý nghĩa gì?** Ví dụ `Integer.MAX_VALUE + 1` có kết quả `-2147483648` theo quy tắc `int`; toán hạng có side effects được đánh giá theo thứ tự JLS yêu cầu.
2. **`javac` tạo bytecode gì?** Nó có thể fold hằng, nhúng `static final` constants, sinh `invokedynamic` để nối chuỗi hoặc chọn những JVM instructions cụ thể. Đây là output của compiler/version đã chọn.
3. **JVM chạy ra sao?** HotSpot có thể dùng interpreter, tiered JIT, inlining, speculative optimizations, escape analysis và deoptimization. Các quyết định thực thi không trở thành ngôn ngữ Java SE contract.

Một nhận định kiểu “Tôi thấy `javap` in `ldc` nên mọi Java compiler đều phải in `ldc`” là **sai phạm vi**. Một nhận định kiểu “Chương trình phải giữ side effects và exception phù hợp JLS dù được tối ưu” mới là cách suy luận đúng.

### 1.1. Ví dụ mở đầu

```java
int answer = 40 + 2;
System.out.println(answer);
```

Kết quả là 42. Trong một bản `javac`, biểu thức có thể trở thành constant trong class file. Compiler khác có thể chọn biểu diễn bytecode khác trong giới hạn class-file semantics. Một HotSpot JIT có thể biến bytecode thành machine code khác. **Hợp đồng quan trọng là `answer` có giá trị đúng**, không phải có đúng một lệnh cộng vật lý trên CPU.

Tuy nhiên, **compile-time constant expression** không đơn thuần là tên của một optimization tùy ý: JLS định nghĩa tập biểu thức này và trao cho nó những ngữ nghĩa đặc biệt, kể cả string interning, narrowing conversion, class initialization và binary compatibility.

## 2. Mục tiêu bài học

Hoàn thành bài, bạn sẽ:

1. Phân biệt JLS, JVMS, JMM và API contract với chi tiết `javac`/HotSpot.
2. Hiểu source → compiler → class file → verifier/linker → interpreter/JIT → native execution.
3. Dùng `javap -c -p`, `javap -verbose` đúng phạm vi quan sát.
4. Hiểu constant expression, `static final` constant variable và hệ quả nhúng hằng vào client binary.
5. Chạy thử thay thư viện mà không rebuild client để thấy kết quả cũ của compile-time constant.
6. Phân biệt `String` concatenation semantics với `invokedynamic` code generation hiện đại.
7. Giải thích thứ tự đánh giá, exceptions, integer overflow, null checks và short-circuit.
8. Biết `final` không phải “chỉ thị bắt JIT inline”.
9. Hiểu JIT có thể inline, devirtualize, khử allocation không quan sát được hoặc deoptimize, nhưng không có cam kết luôn thực hiện.
10. Hiểu JMM giới hạn reordering và vai trò của `volatile`/happens-before.
11. Hiểu FP always-strict từ Java 17 theo JEP 306, không tự thay đổi thứ tự cộng số thực.
12. Phân biệt `var` Java 10 là static type inference, không phải runtime optimization.
13. Dùng `javac --release 17` đúng ý nghĩa; không nhầm class file version với performance.
14. Thiết kế unit tests và microbenchmarks theo observable behavior thay vì instruction count.
15. Tránh những kiến thức legacy hoặc cờ tuning cũ không còn cần thiết trong JDK hiện đại.

## 3. Các cấp hợp đồng

| Cấp | Điều quy định hoặc mô tả | Ví dụ |
| --- | --- | --- |
| **JLS** | Nghĩa source code, đánh giá biểu thức, kiểu, exception, class initialization | `int` overflow, thứ tự operands, constant expressions |
| **JVMS** | Class-file format, bytecode instruction behavior, verification, loading/linking | Class file major version, JVM operand stack |
| **JMM — JLS `17** | Những executions đa luồng hợp lệ, visibility/order, synchronization | `volatile` synchronizes-with, monitor unlock/lock |
| **Java SE API** | Hợp đồng methods/classes cụ thể | `Math.addExact`, `String.equals`, `Thread.join` |
| **`javac` implementation** | Cách compiler chuyển source thành bytecode | Fold literal, dùng `invokedynamic`, đặt local variables |
| **HotSpot/JIT implementation** | Cách runtime thực thi bytecode để tối ưu | Inlining, escape analysis, register allocation, deoptimization |

**JLS/JVMS/API không đặt ra chỉ tiêu thời gian chạy cố định.** Ngược lại, JIT được tự do thay mã máy nhưng không được thay các behavior quan sát được trái luật.

### 3.1. Cách đọc phát biểu cho đúng

- “`100 / divisor` ném `ArithmeticException` khi `divisor==0`”: **hợp đồng ngữ nghĩa**.
- “`javac` đã đặt `constant=42` vào constant pool”: **quan sát compiler output**.
- “HotSpot inline `sum` khi nó trở nên hot”: **phỏng đoán hoặc phát hiện từ profile**; không hứa mọi lần chạy.
- “`volatile` bảo đảm visibility trong một happens-before chain hợp lệ”: **hợp đồng JMM**.
- “Mọi dấu `+` String tạo `StringBuilder`”: **không đúng** với compiler hiện đại.
- “Mọi `new` tạo một heap allocation vật lý mà profiler nhất định nhìn thấy”: **không bảo đảm** do optimization.

## 4. Pipeline và ranh giới của từng công cụ

```text
  Java source (.java)
         |
         v
  javac / source compiler
  - parse, name/type checking, overload resolution
  - constant-expression semantics và definite assignment
  - lựa chọn cách sinh bytecode
         |
         v
  Class file (.class)
  - constant pool, methods, fields, attributes
         |
         v
  JVM load / link / verify / initialize
         |
         v
  Interpreter và/hoặc JIT runtime
  - profiling, inlining, speculative optimizations
  - deoptimization khi assumptions không còn phù hợp
         |
         v
  CPU/native execution
         |
         v
  Hành vi phải tuân thủ Java language/VM/API contracts
```

`javac` tạo class file **trước khi** chạy ứng dụng. `javap` đọc cấu trúc và bytecode của class file. HotSpot có thể **dịch và tối ưu lại** trong thời gian thực thi. Đừng đọc `javap -c` rồi nói đó là CPU instructions đang được thực hiện sau JIT.

**JVM có thể thực thi Java đúng mà không có JIT**. Ví dụ HotSpot `-Xint` dùng interpreter cho mục đích chẩn đoán. Các tối ưu runtime là implementation choices, không phải điều kiện để code có ngữ nghĩa Java hợp lệ.

### 4.1. Từ khóa “observable” quan trọng

Optimizer có thể thay đổi thứ tự instructions hoặc khử tính toán **nếu mọi hành vi có thể quan sát cần thiết vẫn phù hợp**. Những thứ phải xem xét gồm kết quả, exception, side effects I/O, identity khi quan sát được, synchronization, class initialization, API contracts và những execution rules của JMM.

Không nên diễn đạt “optimizer có thể làm bất cứ điều gì miễn stdout giống một lần chạy”. Cùng stdout của một input **không đủ**, vì input khác, exception path và concurrency behavior cũng thuộc ngữ nghĩa.

## 5. Điều được bảo đảm: `int` overflow

Java `int` có độ rộng 32 bit và ngữ nghĩa số nguyên xác định. Khi cộng vượt giới hạn, kết quả quay vòng theo biểu diễn 32 bit:

```java
System.out.println(Integer.MAX_VALUE + 1);
```

Stdout:

```text
-2147483648
```

Đây là **hợp đồng của Java**, không phải “trình biên dịch đã xử lý tình cờ”. `javac` có thể fold biểu thức vì `Integer.MAX_VALUE` là constant variable, và JIT cũng có thể fold nếu phù hợp, nhưng cả hai phải giữ kết quả.

Nếu nghiệp vụ cần **phát hiện** overflow thay vì chấp nhận quay vòng, dùng API `Math.addExact`:

```java
try {
    int result = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(result);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
```

Đây là snippet đặt trong method. `Math.addExact` có hợp đồng ném `ArithmeticException` khi phép cộng vượt miền; việc JIT có thể inline method này **không cho phép nó bỏ kiểm tra overflow**.

### 5.1. Phép chia số nguyên cho zero

`int divisor=0; int result=100/divisor;` ném `ArithmeticException`. Dù CPU hardware có lệnh chia hay JVM dùng một đường kiểm tra khác, code đúng phải giữ exception behavior theo JLS.

Không coi `100 / 0` là một constant expression tạo ra giá trị hợp lệ; phép chia zero không hoàn thành bình thường. Trong ví dụ runnable phía dưới, phép chia dùng biến để quan sát rõ exception runtime.

## 6. Điều được bảo đảm: thứ tự đánh giá và side effects

JLS `15.7 quy định thứ tự đánh giá toán hạng/đối số trong những trường hợp tương ứng, gồm quy tắc **trái sang phải**.

```java
static int calls;

static int step(String name) {
    System.out.print(name);
    return ++calls;
}

// Ở bên trong main hoặc method khác:
int result = step("L") + step("R");
System.out.println(":result=" + result);
```

Output:

```text
LR:result=3
```

`step("L")` chạy trước, in L, tăng counter thành 1; `step("R")` chạy sau, in R, counter thành 2; tổng 3. JIT không được đảo thành `RL` nếu làm khác observable side effects.

### 6.1. Short-circuit có ngữ nghĩa riêng

```java
boolean x = false && expensiveOrSideEffecting();
boolean y = true || expensiveOrSideEffecting();
```

Đoạn này chỉ là snippet; cần khai báo method `expensiveOrSideEffecting()` trả boolean để biên dịch. Trong cả hai biểu thức, toán hạng phải **không được đánh giá** theo quy tắc `&&`/`||`. Compiler có thể sinh branch hay fold thành constant, nhưng không được gây side effects từ method lẽ ra không được gọi.

**Không nhầm** với toán tử boolean `&` và `|`: chúng không có cùng short-circuit semantics với `&&`/`||`.

### 6.2. Exception order cũng quan trọng

Nếu đánh giá vế trái ném exception, vế phải có thể không được đánh giá theo JLS. Optimizer không được di chuyển những side effects từ vế phải lên trước exception vế trái rồi nói ngữ nghĩa không đổi.

Để code dễ bảo trì, thường nên tránh dồn quá nhiều thao tác có side effects vào cùng một expression, dù JLS đã định nghĩa thứ tự.

## 7. Constant expression do JLS định nghĩa, không chỉ là mẹo compiler

JLS **`15.29 trong Java 17** (số mục ở các bản JLS cũ có thể khác) định nghĩa **constant expressions** gồm một tập expression có kiểu primitive hoặc String, được xây từ literals, những operators hợp lệ và constant variables.

```java
final int answer = 40 + 2;
String word = "Ja" + "va";
boolean same = word == "Java";
```

Ở ví dụ này `"Ja"+"va"` là compile-time constant String expression và được intern; vì vậy `same` là true. **Không** suy mọi String concat runtime đều là cùng object với một literal. Trong code thông thường, dùng `equals` để so nội dung.

### 7.1. Constant variable là gì?

Một `constant variable` là biến `final` có **kiểu primitive hoặc String** và được khởi tạo bằng constant expression (JLS `4.12.4`):

```java
public static final int VERSION = 7;
public static final String LABEL = "v" + "1";
```

Còn:

```java
public static final int RUNTIME =
        Integer.parseInt("7");
```

**không** là constant variable, dù có `final`. Lý do: initializer gọi method, không thuộc tập compile-time constant expressions được JLS định nghĩa.

Phải phân biệt:

- **Bảo đảm của spec:** constant variable có quy tắc riêng về initialization, nhúng hằng và binary compatibility.
- **Lựa chọn optimization:** JIT có thể tối ưu những method calls hoặc biểu thức khác tại runtime khi an toàn, nhưng việc đó không biến `Integer.parseInt("7")` thành JLS compile-time constant expression.

## 8. Bài thử binary compatibility: client cũ vẫn thấy hằng 7

Tạo file **`BuildConstants.java`**, bản đầu:

```java
public final class BuildConstants {
    public static final int VERSION = 7;

    public static final int RUNTIME =
            Integer.parseInt("7");

    static {
        System.out.println("apiInitialized");
    }
}
```

Tạo file **`UseConstants.java`**:

```java
public final class UseConstants {
    public static void main(String[] args) {
        System.out.println(
                "constant=" + BuildConstants.VERSION);
        System.out.println(
                "runtime=" + BuildConstants.RUNTIME);
    }
}
```

Trong thư mục thử nghiệm chứa hai source files:

```bash
mkdir api app
javac --release 17 -d api BuildConstants.java
javac --release 17 -cp api -d app UseConstants.java
java -cp "app:api" UseConstants
```

Trên Windows, classpath separator là `;`, do đó thay đoạn `"app:api"` bằng `"app;api"`.

Output đã kiểm thử:

```text
constant=7
apiInitialized
runtime=7
```

**Giải thích:** chỉ tham chiếu `BuildConstants.VERSION` không bắt buộc khởi tạo class `BuildConstants`, vì đó là static constant variable. `UseConstants` đã được compile với giá trị hằng. Truy cập `BuildConstants.RUNTIME` không phải constant variable sẽ kích hoạt initialization; static initializer in `apiInitialized`.

### 8.1. Chỉ sửa/recompile thư viện, không rebuild client

Sửa **`BuildConstants.java`** thành:

```java
public final class BuildConstants {
    public static final int VERSION = 9;

    public static final int RUNTIME =
            Integer.parseInt("9");

    static {
        System.out.println("apiInitialized");
    }
}
```

Chạy **chỉ**:

```bash
javac --release 17 -d api BuildConstants.java
java -cp "app:api" UseConstants
```

Output thực tế:

```text
constant=7
apiInitialized
runtime=9
```

Client cũ vẫn in `7` ở phần constant dù dependency `BuildConstants.class` mới đã khai báo `VERSION=9`. Đây là hệ quả **JLS `13.4.9**: compile-time constant variable có thể được nhúng vào pre-existing binaries. Chỉ thay JAR dependency không làm một client đã compile tự tải lại giá trị constant đó.

`RUNTIME` là một field được đọc ở runtime nên thấy giá trị 9 trong lớp mới. Tuy nhiên, `RUNTIME` **không phải biến cấu hình hot reload**; nó vẫn là final field khởi tạo lúc class được initialized.

**Bài học thiết kế API:** không công bố một primitive/String public `static final` constant nếu giá trị cần đổi giữa các releases mà consumer binaries không đồng loạt biên dịch lại. Dùng method/config accessor có versioning, lifecycle rõ hoặc buộc rebuild các clients.

### 8.2. Class initialization khác với class loading

JLS `12.4.1 quy định điều kiện class/interface initialization. Tham chiếu static **constant variable** không tự gây class initialization, nhưng không nên suy từ một dòng source rằng runtime sẽ không bao giờ load/link class do còn có những lý do khác. Tránh nhầm “không chạy static initializer” với “không có class metadata nào trong JVM”.

## 9. `javap` cho thấy gì trong ví dụ hằng?

Lệnh:

```bash
javap -c -classpath "app:api" UseConstants
```

Trên bản compiler đã kiểm thử có các đoạn đại diện:

```text
ldc           // String constant=7
getstatic     // Field BuildConstants.RUNTIME:I
invokedynamic // nối chuỗi với giá trị field runtime
```

Đây là **bản rút gọn giải thích**, không phải toàn bộ offset và constant-pool index nguyên văn. Ý chính là `constant=7` đã nằm trong client binary, còn `RUNTIME` dùng field access. Việc thấy `invokedynamic` ở chỗ nối String là một lựa chọn codegen của `javac` hiện đại.

Nếu compiler khác chọn những instructions hợp lệ khác, điều đó không có nghĩa JLS binary compatibility bị thay. **JLS `13.4.9** mới là nguồn ngữ nghĩa cần đọc.

## 10. Chương trình Java 17+ runnable tổng hợp

Tạo file **`SpecVsOptimizerDemo.java`**:

```java
public final class SpecVsOptimizerDemo {
    static int calls;
    static volatile boolean ready;
    static int publishedData;

    static int step(String name) {
        System.out.print(name);
        return ++calls;
    }

    static String greeting(String name, int index) {
        return "Hello " + name + " #" + index;
    }

    static int arithmetic(int value) {
        return value * 2 + 1;
    }

    public static void main(String[] args)
            throws InterruptedException {
        final int constant = 40 + 2;
        System.out.println("constant=" + constant);
        System.out.println("sameString="
                + ("Ja" + "va" == "Java"));
        System.out.println("overflow="
                + (Integer.MAX_VALUE + 1));

        int result = step("L") + step("R");
        System.out.println(":result=" + result);

        int divisor = 0;
        try {
            int ignored = 100 / divisor;
            System.out.println("not-reached=" + ignored);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "divByZero=ArithmeticException");
        }

        System.out.println(
                "greeting=" + greeting("Lan", 3));
        System.out.println(
                "arithmetic=" + arithmetic(20));

        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println(
                    "volatilePublished=" + publishedData);
        });

        reader.start();
        publishedData = 42;
        ready = true;
        reader.join();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SpecVsOptimizerDemo.java
java SpecVsOptimizerDemo
```

Output đã kiểm thử trên OpenJDK 21:

```text
constant=42
sameString=true
overflow=-2147483648
LR:result=3
divByZero=ArithmeticException
greeting=Hello Lan #3
arithmetic=41
volatilePublished=42
```

### 10.1. Giải thích từng dòng

| Dòng | Cơ sở ngữ nghĩa |
| --- | --- |
| `constant=42` | Constant expression `40+2` có giá trị 42 |
| `sameString=true` | Constant `String` expressions được intern |
| `overflow=-2147483648` | Quy tắc overflow của `int` |
| `LR:result=3` | Left-to-right evaluation và side effects |
| `divByZero=ArithmeticException` | `int` division với divisor zero |
| `greeting=Hello Lan #3` | String conversion/concatenation đúng thứ tự |
| `arithmetic=41` | `20*2+1` theo số nguyên |
| `volatilePublished=42` | `volatile` read/write + program order cho happens-before |

**Lưu ý liveness:** `Thread.onSpinWait()` không tạo deadline cho scheduler; demo chỉ nhằm minh họa visibility/order và đã chạy thành công. Trong ứng dụng thực, nên dùng `CountDownLatch`, `CompletableFuture` hoặc primitives có cancellation/timeout phù hợp thay vì busy-loop vô hạn.

### 10.2. Không nói chương trình này luôn dùng một chiến lược JIT

Đoạn `arithmetic` có thể được inlined hoặc không; code đúng ở cả hai tình huống. Thứ tự side effects, kết quả số học, exception và visibility là các điều kiện không được tùy ý phá vỡ, dù runtime chọn machine instructions khác.

## 11. Xem class file của chương trình bằng `javap`

```bash
javap -c -p SpecVsOptimizerDemo
javap -verbose SpecVsOptimizerDemo
```

Ý nghĩa:

- `-c`: disassemble methods thành JVM bytecode.
- `-p`: gồm private members.
- `-verbose`: thông tin class-file version, constant pool, methods và attributes.

Khi biên dịch `javac --release 17` bằng JDK 21, `javap -verbose` đã báo **major version 61**, tương ứng target Java 17.

Kết quả kiểm thử còn cho thấy:

- Các chuỗi có constant expressions có thể được gộp thành `ldc` chứa cả nội dung như `"constant=42"`.
- `greeting` dùng `invokedynamic` cho string concatenation động.
- `arithmetic(int)` có `imul` và `iadd` trong class file.
- Phép chia số nguyên còn có `idiv`.
- Hai lời gọi `step` được biểu diễn theo thứ tự phù hợp.

Các điểm trên chỉ là **quan sát bytecode của một phiên bản compiler**, không nói JIT sẽ thực thi native code theo đúng thứ tự/cùng số instruction. Đổi compiler hoặc JVM build có thể thay codegen hợp lệ.

### 11.1. `javap` không làm được gì?

Nó không chứng minh:

1. Một method chắc chắn được inline ở runtime.
2. JVM cấp phát đúng một heap object cho mỗi bytecode `new`.
3. CPU dùng một instruction native cho từng bytecode `iadd`.
4. Có một số nanoseconds cố định cần để chạy `invokedynamic`.
5. JIT đã hoặc chưa deoptimize trong một workload cụ thể.
6. Mọi Java compiler sinh class files giống hệt nhau.

Muốn phân tích optimization runtime, dùng profiler/JFR/JIT diagnostics phù hợp JDK/version, nhưng những kết quả ấy vẫn **không biến thành JLS contract**.

## 12. Nối chuỗi: ngữ nghĩa cố định, implementation linh hoạt

Trong Java source:

```java
static String greeting(String name, int index) {
    return "Hello " + name + " #" + index;
}
```

JLS định nghĩa String concatenation và thứ tự các phần; không bắt `javac` phải dùng `StringBuilder`. Từ **JDK 9**, JEP 280 (*Indify String Concatenation*) đưa hướng codegen `invokedynamic` cho nhiều biểu thức nối chuỗi. Java 10 và các JDK hiện đại tiếp tục sử dụng kỹ thuật này.

Trên class file thử nghiệm, đoạn liên quan có dạng:

```text
invokedynamic // makeConcatWithConstants:(String,int)String
```

Đây là minh họa rút gọn của một instruction, không phải output `javap` nguyên văn có offsets/constant pool indices.

### 12.1. Ngữ nghĩa phải giữ

- Các operands có side effects được đánh giá theo thứ tự JLS.
- Kết quả chứa đúng ký tự của các phần đã nối.
- `null` khi string conversion phù hợp được biểu diễn bằng `"null"`.
- `String` constant expression được intern.
- Những trường hợp nối runtime không phải constant expression phải giữ những quan sát hợp lệ về String result, kể cả identity nếu thực sự được quan sát; JVM có thể tránh vật hóa một object khi tối ưu không đổi observable behavior.

### 12.2. Đừng hứa sai

- “Mỗi dấu cộng chắc chắn tạo `StringBuilder` trong bytecode.”
- “Mỗi phép nối chuỗi cấp phát đúng hai objects.”
- “`invokedynamic` luôn nhanh hơn viết `StringBuilder` bằng tay.”
- “String concatenation đã được javac tối ưu xong nên JIT không thể tối ưu nữa.”
- “Nội dung đúng là đủ để bỏ qua mọi side effects ở operands.”

Trong loop nối chuỗi lớn, có thể chủ động dùng `StringBuilder` hoặc các API khác phù hợp, nhưng hãy **benchmark/profile ứng dụng thật**. Không chọn kỹ thuật chỉ vì thấy một instruction tên `invokedynamic`.

## 13. JIT inlining, devirtualization và deoptimization

Ví dụ:

```java
static int square(int value) {
    return value * value;
}
```

Đoạn trên cần nằm trong class; JVM có thể inline method này tại call site nếu điều kiện runtime cho phép. JIT có thể dùng profile call types để devirtualize, inline, constant propagate hoặc compile lại method ở tier khác. Nhưng **không có quy tắc Java SE rằng mọi method ngắn hơn N bytecodes phải inline**.

### 13.1. `final` có bắt buộc inline không?

Không. `final` trên method chủ yếu ngăn overriding theo hợp đồng Java; không hứa method sẽ inline hay chạy nhanh hơn. `static` cũng không phải một lệnh ép JIT. JLS `13.4.22 còn nhấn mạnh binary-compatibility constraints của việc đưa method body vào client ở compile-time.

### 13.2. Speculation không được thay ngữ nghĩa

HotSpot có thể tối ưu khi profile cho thấy call site thường chỉ gặp một class. Nếu một class khác xuất hiện, runtime có thể **deoptimize** và quay về đường thực thi an toàn. Điều phải được giữ là kết quả/exception/side effects theo contract.

Không hợp lệ khi nói “JIT thấy đầu vào thường khác 0 nên được trả giá trị ngẫu nhiên lúc divisor=0”. Optimization chỉ được thực hiện nếu đảm bảo semantics cho những trường hợp cần quan sát.

### 13.3. JIT không phải tùy chọn compile-time của `javac`

`javac --release 17` không bật hoặc tắt C1/C2/Graal bằng một hợp đồng Java source-level. JIT runtime phụ thuộc JVM implementation, flags và workload. Cùng class file chạy trên Java 17/21/25 có thể có profile/optimization khác nhưng behavior vẫn phải phù hợp đặc tả.

## 14. Escape analysis: `new` không nhất thiết là một allocation vật lý luôn thấy

Xét snippet Java 17+:

```java
record Point(int x, int y) {}

static int addCoordinates(int a, int b) {
    Point point = new Point(a, b);
    return point.x() + point.y();
}
```

Đây là đoạn code cần đặt trong class, không phải file runnable độc lập. Khi JVM chứng minh `point` không escape khỏi phạm vi và không có quan sát identity cần bảo vệ, HotSpot có thể dùng **escape analysis và scalar replacement** thay một phần truy cập object bằng scalars hoặc tránh allocation vật lý.

**Cần phân biệt:**

- Source `new` quy định ngữ nghĩa tạo object và constructor invocation.
- Một VM có thể tối ưu việc vật hóa object khi không đổi hành vi quan sát hợp lệ.
- Constructor có side effects hoặc object identity/locks được quan sát phải được bảo toàn theo contract.
- `new` không có nghĩa cứ một lần gọi method là profiler chắc chắn nhìn thấy một heap allocation.
- Không có cam kết HotSpot bắt buộc thực hiện escape analysis trong mọi lần chạy.
- GC allocation profiles của các bản JDK khác nhau có thể khác mà source semantics vẫn như cũ.

### 14.1. Dead-code elimination cũng có ranh giới

Đoạn:

```java
for (int i = 0; i < 1_000_000; i++) {
    int result = i * 2;
}
```

là snippet; `result` không được dùng và computation không có observable side effects. Một optimizer có thể bỏ/rút gọn đáng kể. **Không** suy “phép nhân mất 0 ns trong ứng dụng thật” từ benchmark đo loop này.

Trái lại, không được tự xóa những I/O, exception, synchronization, mutation hoặc other side effects mà ngữ nghĩa thực tế buộc phải quan sát. Tối ưu không phải quyền tùy ý thay kết quả.

## 15. JMM: compiler/CPU có thể reordering nhưng không vượt happens-before

Trong chương trình đa luồng, không đủ suy luận theo thứ tự source của một thread và giả định các thread khác ngay lập tức thấy mọi write. **Java Memory Model**, JLS `17, mô tả những executions nào hợp lệ.

### 15.1. Ví dụ publication bằng `volatile`

Trong chương trình ở mục 10:

```java
static volatile boolean ready;
static int publishedData;

// Writer, theo thứ tự:
publishedData = 42;
ready = true;

// Reader:
while (!ready) {
    Thread.onSpinWait();
}
System.out.println(publishedData);
```

Đây là **hai đoạn chạy ở hai threads khác nhau**, không phải một method nối tuần tự. Khi reader quan sát giá trị `true` do writer publish qua volatile, write và read đó tạo quan hệ **synchronizes-with**, dẫn tới happens-before. Writer ghi `publishedData=42` trước `ready=true`, nên reader sau khi thấy `ready==true` trong demo (không có writer khác) phải thấy `publishedData==42`.

Vì vậy dòng `volatilePublished=42` không phải một “lợi ích bất ngờ của HotSpot JIT”; nó có cơ sở **JMM**.

### 15.2. `volatile` không làm compound operation atomic

Nếu hai threads cùng chạy `count++` trên `volatile int count`, có thể xảy ra lost updates vì increment gồm read/compute/write. Dùng `AtomicInteger.incrementAndGet` hoặc synchronization đúng nếu cần increment atomic.

Không được hiểu “volatile nghĩa là JIT không tối ưu” — JVM vẫn có thể tối ưu các phần hợp lệ, miễn không vi phạm volatile ordering/visibility.

### 15.3. Data race không được chữa bằng `-Xint`

Nếu `ready` không volatile và không có synchronization khác, reader spin có thể không thấy write theo cách lập trình viên kỳ vọng; chương trình không properly synchronized. Chạy với interpreter và thấy đúng một lần **không chứng minh** đồng bộ đã đúng.

Đừng dùng `Thread.sleep` để tạo visibility guarantee. Dùng `volatile`, `synchronized`, `java.util.concurrent` hoặc mechanism có happens-before contract rõ.

### 15.4. `final` và publication

Java `final` fields có những initialization semantics đặc biệt (JLS `17.5), nhưng `final` không biến mọi object graph mutable thành thread-safe. Nếu một final reference trỏ tới một mutable collection, collection vẫn cần thread safety/synchronization khi được chia sẻ và thay đổi giữa threads.

### 15.5. Không có deadline scheduling tuyệt đối

JMM mô tả visibility và allowed executions; nó không bảo đảm một thread được OS schedule trong 1 ms hay spin loop luôn kết thúc theo deadline. Ví dụ `Thread.onSpinWait` chỉ là hint. Với production cần timeout/cancellation hoặc blocking primitives phù hợp.

## 16. Floating point: Java 17+ always-strict và không được tùy ý reassociate

Từ **JDK 17**, JEP 306 khôi phục ngữ nghĩa **always-strict floating-point**, nên không cần đưa `strictfp` như một yêu cầu mới để “bật tính đúng” trong Java 17+.

Một phép biến đổi đại số đúng trên số thực vô hạn có thể **sai cho floating-point** vì rounding:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c);
System.out.println(a + (b + c));
```

Output đã kiểm thử:

```text
1.0
0.0
```

Do đó, optimizer không được tùy ý thay `(a+b)+c` thành `a+(b+c)` nếu việc đổi làm kết quả quan sát được khác hợp đồng Java. Các giá trị `NaN`, Infinity, signed zero và rounding cũng phải được xét đúng.

### 16.1. Fused multiply-add không tự giống phép toán tách

`Math.fma(a,b,c)` có hợp đồng fused multiply-add; `a*b+c` có thể có cách rounding khác. Một JIT không thể tự dùng instruction fused theo cách thay đổi kết quả được đặc tả trong những đầu vào cần phân biệt.

**Không** áp dụng giả định “toán số thực luôn kết hợp” từ toán học lý tưởng vào benchmark Java FP. Nếu đổi thứ tự phép tính có thể thay output, đó là một vấn đề ngữ nghĩa, không chỉ performance.

## 17. `var` Java 10 là suy luận kiểu compile-time, không phải runtime optimizer

Java 10 giới thiệu **local-variable type inference**:

```java
var name = "Lan"; // kiểu String
var count = 10;   // kiểu int
int next = count + 1;
```

`var` không làm biến trở thành dynamic typed. `count = "text";` sẽ lỗi biên dịch vì `count` có kiểu `int`. Không có performance contract “dùng `var` chạy nhanh hơn” so với viết kiểu tường minh cùng nghĩa.

Tối ưu runtime có thể phụ thuộc class type/profile thực tế, nhưng việc dùng `var` không phải cờ của JIT. **Đừng nhầm** suy luận kiểu của compiler với escape analysis, method inlining hoặc dynamic typing.

## 18. `javac --release 17`: target semantics/API, không quyết định JIT

Để biên dịch example:

```bash
javac --release 17 SpecVsOptimizerDemo.java
java SpecVsOptimizerDemo
javap -verbose SpecVsOptimizerDemo
```

`--release 17` chọn source/target và **nền API công khai của release 17** mà compiler hỗ trợ. Nó thường an toàn hơn chỉ dùng `-target 17` nếu compiler mới có APIs không tồn tại trong Java 17.

- Class file của ví dụ có **major version 61**.
- Điều đó **không** có nghĩa class file Java 17 sẽ chạy trên Java 10 (class file max version khác).
- Điều đó **không** chứng minh mọi dependency bên thứ ba hoặc native library đã tương thích với JDK 17.
- Điều đó **không** buộc HotSpot JIT chạy một optimization cụ thể.
- Source code có thể giữ kết quả như nhau trên nhiều JDK dù bytecode/JIT optimizations khác.

### 18.1. Tránh mô hình “javac -O3 = nhanh hơn” như compiler C++

Không có hợp đồng portable “`javac -O3` làm chương trình chạy nhanh hơn đúng N%” theo Java SE. Compiler `javac` chủ yếu xử lý Java source và tạo class files; nhiều tối ưu hiệu năng diễn ra ở JVM runtime.

Các compiler/JVM-specific flags có thể hữu ích khi debug nhưng không phải **yêu cầu của JLS**. Đừng sao chép các cờ compiler/JVM legacy từ hướng dẫn Java 10 mà không đối chiếu JDK hiện dùng.

## 19. Cách kiểm thử đúng ranh giới

### 19.1. Test observable semantics

Nên kiểm:

- Giá trị `int` overflow và behavior `Math.addExact`.
- Thứ tự side effects với operands/arguments.
- `ArithmeticException` khi int division cho divisor zero trong đường chạy.
- `String` content, constant String interning khi JLS yêu cầu.
- Kết quả class initialization đối với constant và non-constant static fields.
- Kết quả binary compatibility khi thay constant trong library.
- Happens-before, visibility và atomicity bằng đồng bộ đúng.
- Những boundary cases, exceptions và object identity mà ứng dụng thật cần.

**Không** chỉ kiểm một lối chạy “đang dùng C2/JIT” rồi khẳng định semantics luôn đúng. Dựa vào spec cho bảo đảm, và dùng tests để kiểm regressions của implementation hoặc code.

### 19.2. So interpreter với mode mặc định khi điều tra

Trong HotSpot hỗ trợ `-Xint`:

```bash
java -Xint SpecVsOptimizerDemo
java SpecVsOptimizerDemo
```

So kết quả và exception; đừng lấy elapsed time của hai mode làm benchmark tối ưu production. `-Xint` làm VM dùng interpreter, **không** bỏ constant inlining đã được `javac` đưa vào class file. Nếu kết quả khác, kiểm JMM/data races/native code và runtime bug trước khi kết luận một optimization “được phép” thay đổi nghiệp vụ.

### 19.3. Không viết tests theo bytecode shape

Những assertion sai phạm vi:

- “`javac` luôn sinh đúng một `invokedynamic` cho mỗi phép String concat.”
- “Tất cả methods ≤ 35 bytecodes sẽ được JIT inline.”
- “`-Xint` tự thay giá trị constant đã inline từ dependency.”
- “Đếm `new` trong `javap` bằng số allocations trên heap.”
- “Có `var` thì program phải giảm 20% memory.”
- “`Thread.sleep(10)` làm mọi thread khác nhìn thấy shared field.”
- “`Math.fma` và `a*b+c` luôn cho cùng bit pattern.”

Test đúng **hành vi có nghĩa**, để compiler/runtime được quyền đổi implementation trong giới hạn spec.

### 19.4. Microbenchmark tránh dead-code elimination

Một ví dụ benchmark kém:

```java
for (int i = 0; i < 1_000_000; i++) {
    int result = i * 2; // result không được dùng
}
```

Một optimizer có thể xóa nhiều hoặc toàn bộ computation vì không ảnh hưởng observable result. Thời gian cực nhỏ **không có nghĩa phép nhân Java “miễn phí” trong mọi chương trình**.

Khi đánh giá optimization, dùng **JMH** với warm-up, fork, state/input đại diện và consumption của output (ví dụ `Blackhole`). Đối với ứng dụng server, cần benchmark end-to-end và profiler; ghi JDK vendor/build, CPU, GC, JVM flags và tải để tái hiện.

### 19.5. Concurrency tests không thay JMM

Test chạy thành công một triệu lần có ích để phát hiện bug nhưng không chứng minh mọi execution hợp lệ, vì scheduler/timing chưa bao phủ hết. Nếu có data race, việc bật/tắt JIT có thể đổi khả năng tái hiện. Giải pháp là thiết kế đúng happens-before, không trông đợi scheduler luôn cho cùng một interleaving.

## 20. Các nhầm lẫn hay gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Java spec yêu cầu đúng những bytecode tôi thấy trong `javap`.” | Spec quy định ngữ nghĩa/JVMS; compiler có thể chọn codegen khác |
| “`javap` cho biết CPU instructions của JIT.” | Nó đọc class files, không phải native compiled code |
| “`int` overflow phụ thuộc CPU.” | Java có ngữ nghĩa số nguyên xác định |
| “JIT có thể đảo side effects trái/phải.” | Không được làm khác observable evaluation order |
| “`final` luôn có nghĩa compile-time constant.” | Phải là primitive/String và constant-expression initializer |
| “Đổi public constant trong JAR thì client binary cũ tự thấy bản mới.” | Có thể còn giá trị inline cũ; xem JLS `13.4.9 |
| “Dùng static constant luôn kích hoạt class initializer.” | Không; constant variable có quy tắc khác |
| “Nối String `+` luôn biên dịch thành `StringBuilder`.” | `javac` JDK9+ có thể dùng `invokedynamic` |
| “Method `final` bắt buộc JIT inline.” | `final` là hạn chế overriding, không phải optimizer directive |
| “`new` luôn tương đương một `malloc`.” | Escape analysis/scalar replacement có thể bỏ materialization |
| “JIT được bỏ mọi exception để chạy nhanh.” | Cần giữ exception behavior theo semantics |
| “Mọi FP addition có tính kết hợp.” | Rounding làm `(a+b)+c` khác `a+(b+c)` |
| “Java 17 cần `strictfp` để có FP strict.” | JDK17+ always-strict theo JEP 306 |
| “Compiler/JIT không được reorder bất kỳ memory operations nào.” | JMM cho phép một số biến đổi trong phạm vi allowed executions |
| “JIT được trả giá trị shared memory tùy ý.” | JMM có happens-before và causality constraints |
| “`volatile count++` là atomic.” | Không; cần atomic/synchronization |
| “`Thread.sleep` tạo visibility guarantee.” | Không phải publication mechanism |
| “`var` tăng hiệu năng Java 10.” | `var` chỉ suy luận static type |
| “`--release 17` làm class chạy được trên Java 10.” | Target Java 17 không tương thích ngược tới JVM 10 |
| “`-Xint` tắt luôn javac constant folding.” | Class file đã biên dịch giữ nguyên |
| “Benchmark unused result cho tốc độ thật.” | Có thể bị dead-code elimination |
| “Không thấy inline trong log nghĩa là không tuân spec.” | Inlining là implementation choice |
| “Một test pass trên một JDK = mọi JVM luôn cùng tốc độ.” | Correctness contract khác performance observation |

## 21. Bài tập có đáp án

### Bài 1 — Phép cộng overflow

`Integer.MAX_VALUE+1` trả bao nhiêu? Có phụ thuộc HotSpot dùng JIT không?

**Đáp án:** `-2147483648`; không phụ thuộc implementation optimization nếu JVM tuân Java semantics.

### Bài 2 — Hằng và bytecode

`javap` cho thấy literal `42` thay vì `40+2`. Có được assert mọi compiler bắt buộc dùng đúng `ldc`?

**Đáp án:** không; output shape của compiler là lựa chọn, còn giá trị/hành vi là điều được đặc tả.

### Bài 3 — Side effects

`step("L")+step("R")` có thể hợp lệ nếu runtime in `RL` thay vì `LR`?

**Đáp án:** không, khi làm thay observable order của source.

### Bài 4 — String constant

`"Ja"+"va" == "Java"` có kết quả gì?

**Đáp án:** true, vì compile-time `String` constant expression được intern; không khái quát sang mọi runtime concatenation.

### Bài 5 — Final nhưng không constant

`static final int R = Integer.parseInt("7")` có phải constant variable JLS không?

**Đáp án:** không; initializer có method call.

### Bài 6 — Dependency update

Client biên dịch với `VERSION=7`, thư viện được rebuild thành `VERSION=9` nhưng client không rebuild. Trong demo client in gì?

**Đáp án:** `constant=7`; đây là hệ quả binary compatibility của constant variables, không phải bug JIT.

### Bài 7 — Class initializer

Chỉ đọc static constant variable của class có static initializer có bắt buộc initializer chạy không?

**Đáp án:** không. Đọc field runtime không là constant variable có thể kích hoạt initialization.

### Bài 8 — StringBuilder

JLS có bắt compiler luôn sinh `new StringBuilder` cho nối String không?

**Đáp án:** không. `javac` hiện đại thường dùng `invokedynamic`.

### Bài 9 — Method final

`final` method có buộc HotSpot inline không?

**Đáp án:** không; `final` ngăn override, inlining là quyết định runtime.

### Bài 10 — Object allocation

Mỗi `new Point(...)` trong method trả về tổng hai fields có bắt buộc là một allocation vật lý mà profiler nhìn thấy không?

**Đáp án:** không. Có thể dùng escape analysis/scalar replacement khi giữ đúng observable behavior.

### Bài 11 — Division exception

JIT có thể cho `int x=100/0` chạy thành kết quả 0 mà không ném exception nếu muốn tăng tốc không?

**Đáp án:** không. Phải giữ exception behavior khi phép chia zero được thực hiện theo semantics.

### Bài 12 — Volatile publication

Writer ghi `data=42` rồi `ready=true` với ready volatile; reader quan sát true rồi đọc data. Cơ sở visibility?

**Đáp án:** `volatile` synchronizes-with/happens-before theo JMM.

### Bài 13 — Atomicity

`volatile int count` cùng `count++` bảo đảm không mất cập nhật?

**Đáp án:** không. Increment compound không atomic; dùng `AtomicInteger` hoặc locking.

### Bài 14 — Floating point

Vì sao `(1e16 + -1e16) + 1.0` là 1.0, còn `1e16 + (-1e16 + 1.0)` là 0.0?

**Đáp án:** rounding của floating-point; re-association có thể đổi kết quả và không mặc định hợp lệ.

### Bài 15 — `var` Java 10

`var n=10; n="text";` có hợp lệ do dynamic typing?

**Đáp án:** không. `n` có static type `int` đã được compiler suy luận.

### Bài 16 — Class file version

`javac --release 17` tạo major version bao nhiêu? Có chạy Java 10 không?

**Đáp án:** major 61; không thể mặc định chạy trên Java 10.

### Bài 17 — Interpreter

`-Xint` có làm giá trị `static final VERSION` đã inline trong client tự đổi theo JAR mới?

**Đáp án:** không. `-Xint` chỉ đổi execution mode của JVM.

### Bài 18 — Benchmark

Tại sao vòng lặp chỉ gán `int result=i*2;` rồi không dùng result có thể cho benchmark vô nghĩa?

**Đáp án:** optimizer có thể bỏ computation không quan sát được. Dùng JMH/return value/Blackhole thích hợp.

### Bài 19 — Exceptions and JIT

Nếu method bị inline, JVM có quyền bỏ qua `ArithmeticException` trên đường code chia zero không?

**Đáp án:** không. JIT phải giữ error/exception behavior theo contract.

### Bài 20 — Test pass

Một chương trình chạy đúng trên HotSpot JDK 21 có bảo đảm mọi JVM Java 17 đều nhanh như nhau không?

**Đáp án:** không. Đặc tả bảo đảm ngữ nghĩa, không đặt một chiến lược JIT/hiệu năng cố định.

## 22. Checklist khi biên dịch, review và tối ưu

1. **Đang nói source semantics, bytecode hay native runtime code?**
2. Có trích đúng JLS/JVMS/JMM/API contract cho phát biểu “bắt buộc”?
3. Có phân biệt `javac` compile-time và JIT runtime?
4. Có dùng `javap` đúng mục đích, không nhầm với disassembly JIT?
5. Có kiểm JLS `15.29 cho constant expressions?
6. Có phân biệt `final` với constant variable?
7. Có xét public constant inlining khi nâng cấp dependency?
8. Có hiểu class initialization không bị kích hoạt chỉ vì static constant access?
9. Có kiểm integer overflow/Math.addExact theo contract?
10. Có giữ side effects và evaluation order?
11. Có kiểm short-circuit/exception path?
12. Có dùng `String.equals` khi so nội dung thay vì lạm dụng `==`?
13. Có tránh khẳng định String concat luôn dùng `StringBuilder`?
14. Có hiểu `invokedynamic` là codegen implementation detail?
15. Có tránh assert JIT method inlining?
16. Có xem escape analysis/allocation elimination là tùy chọn?
17. Có giữ identity, constructor side effects và observable exceptions?
18. Có thiết kế đồng bộ đúng JMM/happens-before?
19. Có tránh lạm dụng `volatile` cho read-modify-write atomic?
20. Có tránh dùng `sleep` để tạo visibility?
21. Có biết FP always-strict từ Java 17+ không?
22. Có tránh phép re-association FP làm đổi rounding?
23. Có dùng `--release 17` theo target thật?
24. Có kiểm third-party API/binary compatibility riêng không?
25. Có hiểu `var` không phải optimizer runtime?
26. Có tách functional tests khỏi benchmarking?
27. Có tiêu thụ benchmark result để tránh DCE?
28. Có warm-up/forks và ghi JDK/CPU/flags khi đo?
29. Có tránh dùng cờ legacy/undocumented optimizer làm Java SE contract?
30. Có kiểm đúng nguồn tài liệu JLS/JVMS và JDK version khi quyết định?

## 23. Tổng kết

**JLS/JVMS/JMM/Java SE API là nguồn của bảo đảm ngữ nghĩa; `javac` và JIT chỉ chọn cách thực hiện hợp lệ.** Phép cộng `int` overflow, thứ tự đánh giá, exception và happens-before không phải mẹo tối ưu; ngược lại `ldc`, `invokedynamic`, inlining, escape analysis và deoptimization không là cam kết bắt buộc của mọi Java implementation.

Trường hợp **`static final` constant variable** đặc biệt quan trọng: JLS quy định hệ quả của compile-time constants, nên một client đã build có thể tiếp tục thấy giá trị cũ dù thư viện được thay mới. Test đã kiểm chứng `VERSION=7 → 9` ở thư viện nhưng client cũ vẫn in 7; field không phải constant lại in 9. Đó là vấn đề thiết kế API/binary compatibility, không phải do HotSpot làm sai.

Với Java hiện đại, hãy dùng `javac --release 17`, `javap`, kiểm tra JLS/JMM, unit tests theo observable behavior và profiler/JMH nếu nghiên cứu hiệu năng. **Đừng biến một bytecode shape, một log JIT hay một benchmark run thành “bảo đảm của đặc tả”.**

### Tài liệu chính thức

- [Java Language Specification SE 17 — `15 Expressions, `15.7 evaluation order, `15.29 constant expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html)
- [Java Language Specification SE 17 — `17 Threads and Locks / JMM](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [Java Language Specification SE 17 — `13 Binary Compatibility, `13.4.9 constants](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [Java Language Specification SE 17 — `12 Execution and Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [Java Language Specification SE 17 — `4 Variables and Constant Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html)
- [Java Virtual Machine Specification SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [Oracle Java SE 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280)
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286)
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
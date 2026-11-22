# Hằng số lúc biên dịch, gấp hằng và nguy cơ dùng giá trị cũ

Trong Java, không phải mọi giá trị khai báo `final` đều là **hằng số tại thời điểm biên dịch** (*compile-time constant*). Một số biểu thức có thể được `javac` xác định hoàn toàn từ mã nguồn, và giá trị của các trường `static final` thỏa điều kiện có thể được **ghi trực tiếp vào class file của mã gọi**. Điều đó giúp việc sử dụng hằng hiệu quả nhưng tạo ra bẫy: **thư viện thay giá trị hằng, còn class đã biên dịch từ phiên bản cũ có thể tiếp tục dùng giá trị cũ cho đến khi được biên dịch lại**.

Bài học này làm rõ ba khái niệm có liên quan nhưng không đồng nhất: **constant expression** theo Java Language Specification (JLS), **constant variable** và **constant folding/inlining** trong quá trình biên dịch. Sau đó ta tự tái hiện lỗi dùng giá trị cũ, quan sát bytecode và áp dụng cách quản lý cấu hình, build/dependency phù hợp.

## 1. Ba khái niệm phải phân biệt

| Khái niệm | Nghĩa chính xác | Ví dụ |
| --- | --- | --- |
| Constant expression | Biểu thức thuộc kiểu primitive hoặc `String`, đáp ứng tập biểu thức/toán tử/tên hằng được JLS `15.29 cho phép và có thể xác định ở compile time | `2 * 3 + 1`, `"Ja" + "va"` |
| Constant variable | Biến có kiểu primitive hoặc `String`, khai báo `final` và khởi tạo bằng **constant expression** (JLS `4.12.4) | `static final int LIMIT = 3;` |
| Constant folding | Việc đánh giá/rút gọn biểu thức có kết quả đã xác định, từ đó có thể ghi hằng trực tiếp vào bytecode thay cho chuỗi phép toán | `2 + 3` có thể thành giá trị `5` |
| Inlining giá trị hằng | Mã sử dụng trường hằng mang **giá trị đã được nhúng khi biên dịch**, thay vì phải đọc trường của lớp khai báo lúc chạy | Client dùng `Config.LIMIT` đã biên dịch với `LIMIT = 3` có thể giữ `3` |
| Runtime evaluation | Giá trị được tính khi chương trình chạy hoặc khi một lớp được khởi tạo | `Integer.parseInt("3")`, `System.getenv(...)` |

**Constant folding** là cách nói phổ biến về phép biến đổi mã; **constant expression** và **constant variable** là khái niệm có quy tắc cụ thể trong JLS. Không nên kết luận “trình biên dịch có thể đoán ra giá trị” là đủ để một biểu thức trở thành constant expression theo ngôn ngữ Java.

Ví dụ `final int x = Integer.parseInt("3");` là giá trị không đổi sau khi gán, nhưng phép gọi `Integer.parseInt` không thuộc các hình thức constant expression của JLS. Giá trị của `x` chỉ được tạo khi đường thực thi chạy biểu thức khởi tạo.

## 2. Constant expression là gì theo JLS?

JLS `15.29 định nghĩa compile-time constant expression là một biểu thức thuộc kiểu nguyên thủy hoặc `String` và chỉ sử dụng các cấu trúc được cho phép. Các nhóm thường gặp:

- Literal: số nguyên, số thực, ký tự, boolean, string literal và text block.
- Toán tử số học `+`, `-`, `*`, `/`, `%`; unary `+`/`-`.
- Dịch bit `<<`, `>>`, `>>>` và toán tử bit `&`, `|`, `^`, `~`.
- So sánh `<`, `<=`, `>`, `>=`, `==`, `!=`; logic `&&`, `||`, `!`.
- Toán tử điều kiện `? :`, dấu ngoặc và các cast cho primitive/`String` được JLS cho phép.
- Tên biến `final` đủ điều kiện là **constant variable**, có thể tham gia biểu thức hằng khác.

Ví dụ hợp lệ:

```java
static final int TWO = 2;
static final int RESULT = (TWO + 3) * 4;       // 20
static final boolean ENABLED = TWO < 5 && true; // true
static final String LABEL = "Java" + " " + 17;  // "Java 17"
static final long SHIFTED = 1L << 8;           // 256
```

Đây là các khai báo minh họa bên trong một lớp, **không phải chương trình độc lập**. Trong mọi khai báo này, kiểu trường là primitive hoặc `String`, có `final`, và initializer là constant expression.

Những trường hợp không phải constant expression:

```java
static final int PARSED = Integer.parseInt("20");
static final String ENV = System.getenv("APP_MODE");
static final String BUILT = new String("Java");
static final Integer BOXED = Integer.valueOf(20);
static final long TIME = System.nanoTime();
static final int[] TABLE = {1, 2, 3};
```

- Có lời gọi phương thức (`parseInt`, `getenv`, `nanoTime`, `valueOf`), toán tử `new` hoặc initializer mảng: không đủ điều kiện.
- `Integer` không phải primitive hoặc `String`, nên `static final Integer BOXED` không thể là constant variable theo định nghĩa trên, dù đối tượng tham chiếu qua field là `final`.
- `final int[] TABLE` chỉ ngăn **gán lại biến tham chiếu** sau khi khởi tạo; không biến phần tử của mảng thành bất biến.

Cũng cần phân biệt: **`final` không tự làm đối tượng trở thành immutable**. Mức bất biến của các đối tượng phụ thuộc vào API, thiết kế lớp và khả năng thay đổi trạng thái.

### Một biến local final có thể là constant variable

```java
final int base = 4;
final int squared = base * base;  // 16, constant expression
```

Biến `base` có kiểu primitive, `final` và initializer là constant expression; vì vậy nó là constant variable dù nằm trong phương thức. Ngược lại:

```java
int argument = 4;
final int squared = argument * argument;
```

`squared` vẫn chỉ được gán một lần, nhưng **không phải compile-time constant variable**, vì `argument` là biến thường và initializer không phải constant expression.

**Lưu ý:** đối với hiện tượng client giữ hằng cũ khi thay JAR, phần quan trọng đặc biệt là **trường `static` là constant variable** được biên dịch tham chiếu từ class khác (JLS `13.4.9); không đồng nhất mọi biến local `final` với trường public trong API.

## 3. Ví dụ chạy được: folding, String và thứ tự phép cộng

Tạo file `FoldingDemo.java`:

```java
public class FoldingDemo {
    static final int BASE = 2 + 3;
    static final int SQUARE = BASE * BASE;
    static final String GREETING = "Xin" + " chào";
    static final String WORD = "Ja" + "va";

    public static void main(String[] args) {
        System.out.println(BASE);
        System.out.println(SQUARE);
        System.out.println(GREETING);
        System.out.println("Java" == WORD);
        System.out.println(1 + 2 + "x");
        System.out.println("x" + 1 + 2);
        System.out.println(Integer.MAX_VALUE + 1);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out FoldingDemo.java
java -cp out FoldingDemo
```

Stdout:

```text
5
25
Xin chào
true
3x
x12
-2147483648
```

Giải thích từng phần:

1. `BASE = 2 + 3` là biểu thức hằng và có giá trị `5`. Vì `BASE` là constant variable, `SQUARE = BASE * BASE` cũng được xác định khi biên dịch thành `25`.
2. `GREETING` và `WORD` đều là `String` constant variables; nối những thành phần hằng đủ điều kiện cho ra `"Xin chào"` và `"Java"`.
3. Kết quả `"Java" == WORD` là `true` theo quy tắc **interning của String constant expressions** trong JLS `15.29. Đây là một hiện tượng ngôn ngữ được quy định; trong code ứng dụng nói chung, so sánh **nội dung** chuỗi bằng `equals`, không dùng `==`.
4. `1 + 2 + "x"` được đánh giá từ trái sang phải: phép cộng số nguyên `1 + 2` tạo `3` trước, rồi nối thành `"3x"`. `"x" + 1 + 2` bắt đầu là nối chuỗi nên tạo `"x12"`.
5. `Integer.MAX_VALUE + 1` dùng toán học `int` 32 bit: overflow theo quy tắc Java và cho `-2147483648`, **không tự ném ngoại lệ vì overflow int**.

Đây là kết quả ngôn ngữ Java 17+, không phải lời khẳng định mọi compiler luôn phải tạo cùng một chuỗi bytecode. Compiler có thể biểu diễn hằng bằng instruction `iconst`, `bipush`, `ldc` hoặc cách tương đương được JVM cho phép; lựa chọn cụ thể tùy class file và toolchain.

### Gấp hằng không được thay đổi thứ tự và kiểu biểu thức

Nối chuỗi `1 + 2 + "x"` và `"x" + 1 + 2` khác nhau vì phép cộng và phép nối chuỗi có quy tắc kiểu, tính kết hợp và thứ tự toán hạng. Không được lấy một phép biến đổi toán học áp dụng cho số để tùy tiện thay đổi kết quả của chương trình đã chuyển sang kiểu `String`.

Tương tự, số học primitive có quy tắc overflow và đặc điểm số thực; trình biên dịch không được tùy ý thay đổi hành vi quan sát được của một biểu thức chỉ vì thấy nó có thể “tối ưu”.

## 4. Tại sao public static final đôi khi bị nhúng vào client?

Xem lớp thư viện:

```java
public class Config {
    public static final int LIMIT = 3;
    public static final String MODE = "safe";
}
```

Hai trường này là **static constant variables**. Khi một class khác biên dịch lời gọi:

```java
System.out.println(Config.LIMIT);
System.out.println(Config.MODE);
```

Compiler sử dụng **giá trị tại thời điểm biên dịch client** theo quy tắc dành cho constant variables. Class file của client có thể chứa trực tiếp `3` và `"safe"`, không cần thao tác đọc trường `Config.LIMIT` hay `Config.MODE` ở runtime.

Điều đó dẫn tới hệ quả quan trọng:

> Nếu thay `Config.LIMIT` từ `3` thành `7`, chỉ biên dịch lại `Config.class` và phân phối JAR mới, **mã client đã biên dịch từ giá trị cũ có thể tiếp tục sử dụng `3`** cho đến khi chính client được biên dịch lại.

JLS `13.4.9 mô tả chính xác tình huống này: đổi giá trị trường `static` thuộc loại constant variable **không nhất thiết làm binary cũ ngừng chạy**, nhưng binary cũ không tự thấy giá trị mới. Đây là **binary compatibility về khả năng liên kết/chạy**, không đồng nghĩa **đồng bộ giá trị**.

Không nhầm cơ chế này với cache dữ liệu, thread-local, classloader “đọc nhầm” hoặc JIT giữ code quá lâu. Trong ví dụ đơn giản, **giá trị cũ vốn đã nằm trong `Consumer.class`** khi compiler xử lý mã client.

## 5. Thực hành tái hiện nguy cơ giá trị cũ: hai lượt biên dịch

Phần này là một thí nghiệm hoàn chỉnh có **hai file nguồn độc lập** và hai thư mục class output. Mục đích là chứng kiến **thư viện đổi giá trị, client chưa build lại**, chứ không chỉ đọc mô tả lý thuyết.

### 5.1. Cấu trúc ban đầu

Tạo thư mục làm việc gồm:

```text
constant-lab/
  libsrc/
    Config.java
  clientsrc/
    Consumer.java
  out/
    lib/          (sẽ do javac tạo)
    client/       (sẽ do javac tạo)
```

Trong `libsrc/Config.java` (phiên bản V1):

```java
public class Config {
    public static final int LIMIT = 3;
    public static final String MODE = "safe";
    public static final Integer BOXED = Integer.valueOf(3);

    public static int currentLimit() {
        return LIMIT;
    }
}
```

Trong `clientsrc/Consumer.java`:

```java
public class Consumer {
    public static void main(String[] args) {
        System.out.println("direct-limit=" + Config.LIMIT);
        System.out.println("direct-mode=" + Config.MODE);
        System.out.println("method-limit=" + Config.currentLimit());
        System.out.println("boxed=" + Config.BOXED);
    }
}
```

Vì sao dùng cả bốn biểu thức?

| Biểu thức | Compile-time constant? | Runtime đọc theo cách nào? |
| --- | --- | --- |
| `Config.LIMIT` | Có, trường `static final int` khởi tạo bằng literal `3` | Giá trị có thể được nhúng trong client |
| `Config.MODE` | Có, trường `static final String` khởi tạo bằng literal `"safe"` | Giá trị có thể được nhúng trong client |
| `Config.currentLimit()` | **Không**: lời gọi phương thức | Runtime gọi phương thức của phiên bản `Config.class` đang nạp |
| `Config.BOXED` | **Không**: `Integer` không thuộc kiểu constant variable | Runtime truy cập trường của lớp `Config` đã nạp |

**Chú ý:** `BOXED` là một đối tượng `Integer`, không phải `int` primitive; trường chỉ `final` về tham chiếu, và initializer `Integer.valueOf(3)` là lời gọi method. Việc JIT có thể tối ưu truy cập/boxing không thay đổi quy tắc constant variable giữa các binary riêng biệt.

### 5.2. Biên dịch thư viện V1 và client V1

Đứng trong thư mục `constant-lab` rồi chạy:

```bash
javac --release 17 -encoding UTF-8 -d out/lib libsrc/Config.java
javac --release 17 -encoding UTF-8 -cp out/lib -d out/client clientsrc/Consumer.java
java -cp "out/client:out/lib" Consumer
```

Lệnh `java` ở trên dùng **dấu `:` dành cho Linux/macOS**. Với Windows PowerShell hoặc cmd, chạy:

```powershell
java -cp "out/client;out/lib" Consumer
```

Stdout của V1:

```text
direct-limit=3
direct-mode=safe
method-limit=3
boxed=3
```

Có hai ý quan trọng ở câu lệnh biên dịch thứ hai:

1. `-cp out/lib` giúp `javac` tìm được khai báo lớp `Config` và giá trị hằng khi **biên dịch Consumer**.
2. Sau khi `Consumer.class` đã tạo, compile-time constant đã được sử dụng để sinh bytecode; lúc chạy, `Consumer` không nhất thiết tra lại trường hằng của `Config`.

### 5.3. Sửa duy nhất thư viện thành V2

Thay nội dung `libsrc/Config.java` bằng **đúng**:

```java
public class Config {
    public static final int LIMIT = 7;
    public static final String MODE = "fast";
    public static final Integer BOXED = Integer.valueOf(7);

    public static int currentLimit() {
        return LIMIT;
    }
}
```

**Chỉ** biên dịch lại thư viện:

```bash
javac --release 17 -encoding UTF-8 -d out/lib libsrc/Config.java
```

**Không** chạy lại lệnh `javac ... clientsrc/Consumer.java` ở bước này. Giữ nguyên `out/client/Consumer.class` là điều kiện quan trọng để tái hiện vấn đề.

Bây giờ chạy V2 của thư viện với binary client cũ:

Linux/macOS:

```bash
java -cp "out/client:out/lib" Consumer
```

Windows:

```powershell
java -cp "out/client;out/lib" Consumer
```

Stdout **được mong đợi và đã được kiểm tra bằng JDK 21 với `--release 17`**:

```text
direct-limit=3
direct-mode=safe
method-limit=7
boxed=7
```

Giải thích chính xác:

- `direct-limit=3` và `direct-mode=safe`: binary `Consumer.class` **cũ** đang mang giá trị compile-time của V1. Việc thay class file bên phía thư viện không sửa binary client.
- `method-limit=7`: JVM gọi `Config.currentLimit()` **của V2** đã nạp, phương thức V2 trả về `7`.
- `boxed=7`: khi chạy, truy cập `Config.BOXED` đọc trường từ lớp runtime V2; vì trường này không thuộc dạng static constant variable, client không nhúng literal `3` theo cơ chế constant variable.

Đây là ví dụ thực tế của một thay đổi thư viện **không phá vỡ khả năng liên kết binary** nhưng khiến giá trị mà mỗi client nhìn thấy **khác nhau** tùy thời điểm biên dịch.

### 5.4. Biên dịch lại client để nhận giá trị V2

Sau khi thư viện V2 đã được biên dịch, chạy lại lệnh build client:

```bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/client clientsrc/Consumer.java
```

Sau đó chạy `Consumer` bằng classpath phù hợp hệ điều hành như trên. Stdout:

```text
direct-limit=7
direct-mode=fast
method-limit=7
boxed=7
```

Đến đây cả compiler đầu vào client lẫn runtime đều nhìn thấy V2, nên các giá trị thống nhất. Nếu build nhiều module, chỉ thay JAR thư viện **không bảo đảm** tất cả consumer module được biên dịch lại. Hãy kiểm tra build graph, incremental build, cache và artifact thực được deploy.

## 6. Dùng javap chứng minh giá trị đã nằm trong class file

Sau khi tạo `Consumer.class` bằng V1, **trước khi build lại client**, thử:

```bash
javap -classpath out/client -c Consumer
```

Trên JDK hiện đại, output thường cho thấy các dòng ý nghĩa như sau (đây là trích dẫn **minh họa cấu trúc**, các bytecode offset/constant-pool index có thể khác):

```text
ldc           // String direct-limit=3
...
ldc           // String direct-mode=safe
...
invokestatic  // Method Config.currentLimit:()I
...
getstatic     // Field Config.BOXED:Ljava/lang/Integer;
```

Do cách biên dịch phép nối chuỗi, compiler có thể gộp literal `"direct-limit=" + Config.LIMIT` thành một hằng duy nhất `"direct-limit=3"`. Vì vậy không nhất thiết thấy một instruction riêng tải số nguyên `3`; có thể thấy **nguyên chuỗi sau folding**.

Điểm cần tìm khi đọc bytecode:

1. Với hai dòng `direct-...`, có thể thấy **literal** đã mang giá trị V1 và **không có `getstatic Config.LIMIT`/`getstatic Config.MODE`** cho các cách dùng ấy.
2. Với `Config.currentLimit()`, sẽ có lời gọi method phù hợp như `invokestatic`.
3. Với `Config.BOXED`, sẽ có truy cập field phù hợp như `getstatic`.
4. Sau khi chỉ thay thư viện thành V2, chạy lại `javap ... Consumer` vẫn cho hình ảnh V1: class file của client chưa đổi.
5. Sau khi biên dịch lại client, giá trị trong literal thay thành V2.

Lệnh `javap -v Config` có thể cho thấy thuộc tính `ConstantValue` của một số trường hằng trong class file. `ConstantValue` là một chi tiết quan trọng ở class file khi compiler phát sinh constant fields, nhưng **không tự bảo đảm mọi consumer sẽ đọc trường ở runtime**. Cần quan sát **bytecode của consumer** để biết nó đang dùng literal hay field access.

Bytecode chính xác có thể khác theo phiên bản `javac`, đặc biệt ở phần nối chuỗi (`invokedynamic` là một cách triển khai thường gặp). Hãy đọc ý nghĩa instruction, tránh bắt buộc khớp mọi offset và index.

## 7. final không đồng nghĩa với constant variable

Một trường có `final` nhưng **không thỏa kiểu và initializer** sẽ không là compile-time constant variable.

Ví dụ hoàn chỉnh `FinalKinds.java`:

```java
public class FinalKinds {
    static final int COMPILE_TIME = 2 * 3;
    static final int RUN_TIME = Integer.parseInt("7");
    static final Integer WRAPPER = Integer.valueOf(8);

    public static void main(String[] args) {
        System.out.println(COMPILE_TIME);
        System.out.println(RUN_TIME);
        System.out.println(WRAPPER);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 -d out FinalKinds.java
java -cp out FinalKinds
```

Stdout:

```text
6
7
8
```

Ba giá trị đều không được gán lại sau khởi tạo, nhưng:

- `COMPILE_TIME` là `static final int` với initializer constant expression, đủ điều kiện constant variable.
- `RUN_TIME` là `static final int` nhưng có lời gọi `Integer.parseInt`, nên được tính khi lớp khởi tạo, không phải constant variable.
- `WRAPPER` là `static final Integer`; `Integer` là kiểu reference và không phải `String`, nên không thuộc constant variable.

**Phân biệt trạng thái:** `final` áp dụng quy tắc gán; **constant variable** áp dụng một điều kiện ngôn ngữ chặt hơn. `final` cũng không bảo đảm một config value an toàn được đổi giữa các phiên bản thư viện đã phân phối.

## 8. Hằng compile-time và khởi tạo lớp

Đọc một trường `static` là constant variable không buộc JVM phải khởi tạo lớp khai báo chỉ vì hành vi đọc hằng ấy (theo quy tắc khởi tạo lớp của JLS `12.4.1). Trong khi đó, truy cập trường `static` **không phải** constant variable có thể là một hành động kích hoạt khởi tạo lớp.

Tạo file `InitializationDemo.java`:

```java
class Settings {
    static {
        System.out.println("Settings initialized");
    }

    static final int CONSTANT = 2 * 3;
    static final int RUNTIME_VALUE = Integer.parseInt("7");
}

public class InitializationDemo {
    public static void main(String[] args) {
        System.out.println(Settings.CONSTANT);
        System.out.println(Settings.RUNTIME_VALUE);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 -d out InitializationDemo.java
java -cp out InitializationDemo
```

Stdout:

```text
6
Settings initialized
7
```

Tại sao thứ tự này đúng?

1. Lời gọi `System.out.println(Settings.CONSTANT)` sử dụng giá trị `6` đã được compiler xác định; việc dùng constant variable ấy **không kích hoạt khởi tạo `Settings`**.
2. Lời gọi sau truy cập `Settings.RUNTIME_VALUE` là trường static không phải constant variable, nên JVM phải khởi tạo lớp `Settings` trước khi đọc giá trị. Khối `static` in `Settings initialized`.
3. Sau khởi tạo, `RUNTIME_VALUE` có giá trị `7`, nên chương trình in dòng `7`.

Nếu có mã khác đã chủ động khởi tạo `Settings` từ trước, bạn có thể thấy thứ tự khác. Ví dụ trên là một chương trình độc lập không khởi tạo lớp ấy trước lời gọi vào `RUNTIME_VALUE`.

**Bẫy chẩn đoán:** Một đoạn mã chỉ tham chiếu `Settings.CONSTANT` có thể không thực thi static initializer, dù người đọc tưởng mọi truy cập `Settings.SOMETHING` luôn khởi tạo lớp.

## 9. Ranh giới của constant folding: JVM, JIT và kết quả runtime

Có ba mức dễ bị gộp nhầm:

| Mức | Thực hiện khi nào? | Điều kiện / ví dụ | Cơ hội quan sát |
| --- | --- | --- | --- |
| Constant expression theo JLS | Kiểu và giá trị xác định khi compiler xử lý nguồn | `2 + 3`, `"A" + "B"` | `javap -c` trên binary |
| Biến đổi của `javac` | Trong quá trình tạo class file | Gấp biểu thức hằng, sinh literal trong code client | So sánh `.class` và constant pool |
| Tối ưu của JVM/JIT | Trong lúc chạy, có thể dựa vào profile và trạng thái đã quan sát | Inlining lời gọi method, loại bỏ code dư, constant propagation runtime | Công cụ profiling/JIT logging theo JVM |

**Không đồng nhất JIT inline với compile-time constant inlining.** Dù HotSpot có thể tối ưu một lệnh đọc field hoặc lời gọi method khi chạy, kết quả phải tuân thủ ngữ nghĩa của chương trình và điều kiện tối ưu, khác với tình huống literal đã được đặt trong `Consumer.class` do `javac`.

Cũng đừng suy luận “bất kỳ biểu thức nào có kết quả luôn giống nhau đều bị javac gấp”:

```java
static final int A = 2 + 3;                 // constant variable
static final int B = Math.abs(-5);          // không phải constant variable
static final String C = "A" + "B";           // constant variable
static final String D = new String("AB");   // không phải constant variable
```

Một compiler hoặc JIT có thể tối ưu một số đoạn mã khác theo quy định và implementation, nhưng **không biến `Math.abs(-5)` thành constant expression theo JLS `15.29**. Quan hệ binary client–library cần phân tích bằng điều kiện constant variable, không bằng dự đoán optimizer “chắc đã thông minh”.

## 10. Các ràng buộc của compile-time constant trong ngôn ngữ

### Case label của switch

Một `case` truyền thống dùng giá trị constant expression thích hợp với selector. Ví dụ (minh họa bên trong lớp):

```java
static final int CODE_OK = 2 + 3;

static String describe(int code) {
    return switch (code) {
        case CODE_OK -> "ok";
        default -> "other";
    };
}
```

`CODE_OK` có giá trị `5` được xác định khi biên dịch, nên có thể làm nhãn `case`. Nếu thay bằng:

```java
static final int CODE_OK = Integer.parseInt("5");
```

thì `CODE_OK` không còn là constant variable; dùng nó làm nhãn `case CODE_OK` kiểu trên sẽ không đáp ứng yêu cầu constant expression. Những ví dụ trên minh họa sự khác nhau của điều kiện biên dịch, không phải chương trình độc lập có `main`.

### Narrowing trong constant assignment

Java cho phép một số phép gán hằng số nguyên cho kiểu nhỏ hơn nếu giá trị biểu diễn được:

```java
byte small = 10 + 20;   // Hợp lệ vì constant expression int = 30.
char letter = 65;       // Hợp lệ vì 65 nằm trong miền char.
// byte fail = 200;     // LỖI: vượt miền byte.
```

Nhưng không áp dụng bừa quy tắc này cho mọi ngữ cảnh gọi phương thức. Với `static void f(byte x) {}`, lời gọi `f(30)` (literal có kiểu `int`) **không tự narrowing** thành `byte` để overload; cần `f((byte) 30)` hoặc một biến `byte` phù hợp.

### Chia số nguyên cho 0 trong biểu thức hằng

```java
// static final int BROKEN = 1 / 0; // LỖI BIÊN DỊCH: chia cho 0 trong constant expression.
```

Với phép chia số nguyên được thực hiện ở runtime:

```java
int divisor = 0;
// int result = 1 / divisor; // Biên dịch hợp lệ nhưng nếu chạy sẽ ném ArithmeticException.
```

Nhận xét “compiler phát hiện mọi phép chia cho 0” là sai: nó chỉ có thể áp dụng những quy tắc kiểm tra liên quan từ thông tin tĩnh; lỗi của phép toán với dữ liệu runtime có thể xuất hiện lúc chạy.

### Integer overflow không báo lỗi runtime

Như ví dụ `FoldingDemo`, `Integer.MAX_VALUE + 1` cho `-2147483648` ở `int` 32 bit. Không được giả định `javac` từ chối mọi biểu thức vượt miền hoặc Java ném ngoại lệ khi integer overflow thông thường. Nếu cần kiểm soát overflow khi tính toán runtime, xem các API như `Math.addExact` (nhưng lời gọi `Math.addExact` không là constant expression theo JLS).

## 11. Nguy cơ trong API thư viện, cache và hệ thống triển khai

Các ứng dụng nhiều module thường có quan hệ:

```text
module-shared
    |
    | public static final int TIMEOUT = 30;
    v
service-A (đã compile lúc TIMEOUT=30)
service-B (đã compile lúc TIMEOUT=30)
    |
    | shared JAR được thay bằng TIMEOUT=45
    v
service-A (chưa compile lại)  -> có thể tiếp tục dùng 30
service-B (compile lại)      -> dùng 45
```

Đây là **vấn đề phiên bản binary**, không chỉ là chuyện classpath chứa JAR cũ. Ngay cả khi `service-A` đang sử dụng bản `shared.jar` mới, `service-A.class` có thể mang literal `30` từ lần biên dịch cũ.

Tác động có thể nghiêm trọng nếu giá trị liên quan đến giao thức, mã sự kiện, giới hạn, tính năng hoặc chính sách: hai client khác thời điểm build có thể ra quyết định khác nhau, dù cùng nhìn một phiên bản thư viện runtime.

### Đặc biệt nguy hiểm với cờ bật/tắt

```java
public static final boolean FEATURE_ENABLED = false;
```

Nếu mã client compile với giá trị `false` rồi sau này thư viện đổi thành `true`, client cũ vẫn có thể giữ giá trị `false`. Trình biên dịch còn có thể loại bỏ/biến đổi nhánh dựa trên constant expression. Vì vậy **không dùng public static final compile-time constant làm cờ cấu hình cần thay đổi sau khi deploy**.

Đối với `if (Config.FEATURE_ENABLED)`, không nên mặc nhiên kết luận chương trình sẽ đọc trường bên phía thư viện ngay khi chạy. Trong bytecode client đã biên dịch, điều kiện có thể đã được xác định và không còn việc đọc field.

### Nguy cơ tương tự với chuỗi constant

```java
public static final String API_VERSION = "v1";
```

Nếu client compile với `"v1"`, sau đó thư viện đổi thành `"v2"`, client cũ vẫn có thể dùng literal `"v1"`. `String` nằm trong tập kiểu có thể là constant variable; không chỉ số nguyên mới gặp vấn đề.

## 12. Thiết kế API nào phù hợp với từng loại giá trị?

| Nhu cầu | Thiết kế gợi ý | Lý do |
| --- | --- | --- |
| Hằng toán học hoặc giá trị thực sự không đổi qua các phiên bản | `public static final int/long/String` với constant expression | Có thể dùng tiện lợi khi compile, giá trị ổn định là chủ đích |
| Giá trị có thể thay đổi giữa các phiên bản thư viện | Method accessor như `public static int limit()` | Client gọi implementation ở runtime thay vì nhúng literal qua constant variable |
| Cấu hình môi trường/deploy | Config từ file, environment, property hoặc service cấu hình | Phân tách việc chọn cấu hình khỏi biên dịch |
| Giá trị bất biến sau khởi tạo nhưng không nên inline | `private static final` khởi tạo runtime, công khai qua accessor | Điều khiển cách đọc và đóng gói API |
| Enum trạng thái mang ngữ nghĩa ổn định | `enum` khi phù hợp hợp đồng API | Tránh hard-code số/chuỗi thiếu kiểu trong code sử dụng |
| Cờ bật/tắt cần thay đổi sau deploy | Feature/config service hoặc runtime configuration | Không phụ thuộc bytecode client chứa boolean cố định |

Ví dụ accessor:

```java
public class RuntimeLimits {
    private static final int LIMIT = 7;

    public static int limit() {
        return LIMIT;
    }
}
```

Tại nơi gọi, dùng `RuntimeLimits.limit()` thay vì công khai `RuntimeLimits.LIMIT`. `LIMIT` trong lớp trên vẫn là constant variable *bên trong thư viện*, nhưng **client chỉ gọi method**, nên sau khi thay library class và không đổi chữ ký method, client cũ có thể nhận giá trị mới.

**Giới hạn của cách làm:** JVM/classloader phải thực sự nạp bản library mới. Một ứng dụng đang chạy từ trước sẽ không tự thay thế class đã nạp chỉ vì bạn chép JAR mới vào ổ đĩa. Cơ chế hot reload/redefinition, classloader và restart là các vấn đề runtime riêng. Ví dụ stale constant ở trên luôn chạy một tiến trình `java` mới với class file thư viện đã thay.

Một lựa chọn khác là `public static final int VALUE = computeValue();` để tránh constant variable, nhưng nếu việc công khai field làm client phụ thuộc trực tiếp vào ABI và semantics, accessor vẫn thường dễ kiểm soát thay đổi hơn.

## 13. Cách sửa khi phát hiện giá trị cũ

Đi theo thứ tự để không chẩn đoán sai:

1. **Xác định trường bị thay:** kiểu có phải primitive/`String`, có `final` và initializer là constant expression không? Nếu đúng, nghi ngờ client đã inline.
2. **Xem chính bytecode của client:** chạy `javap -c` trên class file được deploy và tìm literal cũ so với `getstatic`/`invokestatic`.
3. **Xác minh đúng artifact:** đọc version/checksum của JAR thư viện và class file client đang chạy; chú ý dependency copy, shaded/fat JAR hoặc image/container.
4. **Biên dịch lại toàn bộ consumer phụ thuộc:** khi thay giá trị compile-time constant, build lại những module đã sử dụng nó. Chạy lại test và đóng gói lại artifact deploy.
5. **Triển khai artifact thực sự mới:** restart/rollout theo cách vận hành dự án để process mới nạp binary mới; phân biệt deploy library mới với deploy client mới.
6. **Sửa thiết kế API** nếu giá trị được kỳ vọng sẽ đổi nhiều lần: không tiếp tục công khai nó như hằng compile-time cho consumer cần thấy giá trị mới.
7. **Kiểm tra CI/cache:** nếu build system phục hồi class file cũ, phải xác định dependency input và điều kiện invalidation, tránh chỉ xóa dữ liệu ngẫu nhiên.

Đối với ứng dụng Java nhiều module, việc sửa một file nguồn constant trong `module-shared` và build riêng module đó **không đủ bằng chứng** rằng các module phụ thuộc đã biên dịch lại. Kiểm tra output của build và binary hiện diện trong bản phát hành.

### Đừng nhầm với các lỗi khác

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần tìm |
| --- | --- | --- |
| Đã thay `LIMIT` nhưng client vẫn in `3` | Constant variable đã nhúng giá trị V1 | Literal cũ trong bytecode client |
| Client đọc trường runtime nhưng vẫn nhận giá trị cũ | Chưa nạp JAR mới, classloader, nhiều bản thư viện | `getstatic` trong client, đường dẫn class thực tế |
| Client thấy method cũ | Chưa thay/restart implementation, sai classpath | `invokestatic`/`invokevirtual` và class runtime |
| Một thread thấy giá trị khác thread khác | Đồng bộ bộ nhớ/visibility hoặc logic runtime | Truy cập runtime, volatile/synchronization |
| Chạy trên máy khác ra khác | Artifact/JDK/config khác | Hash/version JAR, build metadata, cấu hình |
| Build thành công nhưng class cũ vẫn được deploy | Cache/artifact pipeline | Timestamp, hash và output của đúng tác vụ |

Không đổ mọi hiện tượng “giá trị cũ” cho constant folding. **Nếu field không phải constant variable, phải kiểm tra runtime classloading, cập nhật cấu hình và phân phối artifact trước**.

## 14. Kiểm tra lại bằng ba lệnh và một thay đổi

Thí nghiệm trong mục 5 có thể được tóm theo thứ tự để tự thực hành:

```text
(1) Biên dịch Config V1 -> out/lib/Config.class
(2) Biên dịch Consumer V1 với -cp out/lib -> out/client/Consumer.class
(3) Chạy Consumer -> 3 / safe / 3 / 3
(4) Thay nội dung Config bằng V2
(5) Chỉ biên dịch lại Config -> out/lib/Config.class
(6) Chạy Consumer cũ -> 3 / safe / 7 / 7
(7) Biên dịch lại Consumer với Config V2
(8) Chạy Consumer mới -> 7 / fast / 7 / 7
```

Khi kết quả khác bảng trên, kiểm tra:

- Có vô tình biên dịch lại `Consumer` ở bước (5) không?
- Lệnh `javac` của client dùng đúng `-cp out/lib` không?
- Lệnh `java` dùng đúng cả `out/client` và `out/lib`, theo đúng dấu phân cách từng hệ điều hành không?
- Bạn có chạy trong đúng thư mục `constant-lab` chứa những đường dẫn tương đối không?
- Có nhiều bản `Config.class` khác trên classpath không?
- Phiên JDK có đáp ứng `--release 17` không?

**Quan sát chính:** chỉ thay thư viện và chạy lại không xóa được literal đã có trong binary client; biên dịch lại client mới cập nhật những giá trị hằng được nhúng.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao `final int v = Integer.parseInt("3");` không phải constant variable?**

Vì initializer dùng method invocation, không thuộc tập constant expression của JLS `15.29, dù biến là `final` và kiểu `int`.

**2. `static final String S = "A" + "B";` có thể bị inline không?**

Có. Biểu thức nối hai string literal là constant expression và trường thuộc kiểu `String`, khai báo `final`. Consumer compile với giá trị `"AB"` có thể giữ giá trị đó.

**3. `static final Integer N = 3;` có phải constant variable không?**

Không. `Integer` không phải primitive hoặc `String`. Autoboxing không làm thay đổi định nghĩa constant variable.

**4. Nếu client đã compile với `TIMEOUT=30` nhưng thư viện mới là `45`, chỉ thay library JAR là đủ chưa?**

Chưa. Client có thể đã nhúng `30` trong class file. Cần build lại client, kiểm tra artifact và triển khai đúng binary mới hoặc đổi cách truy cập giá trị.

**5. Vì sao `Config.currentLimit()` trả `7` trong khi `Config.LIMIT` vẫn là `3` ở cùng client cũ?**

Client đã lưu trực tiếp giá trị constant variable từ thời điểm compile, còn lời gọi method chạy code từ `Config.class` V2 được nạp ở runtime.

**6. Tại sao `Settings.CONSTANT` có thể không chạy static initializer?**

Vì tham chiếu tới trường static là constant variable có thể được giải quyết từ compile-time value và không phải active use bắt buộc khởi tạo lớp theo JLS `12.4.1.

**7. Có thể xem `Math.abs(-5)` là constant expression vì kết quả hiển nhiên không?**

Không. Java Language Specification giới hạn những cấu trúc được phép xuất hiện trong compile-time constant expression. Tối ưu JIT, nếu có, là một cơ chế khác.

**8. Tại sao không nên dùng `public static final boolean ENABLED = false` làm feature flag cần đổi trong production?**

Vì consumer compile với `false` có thể giữ giá trị/nhánh logic cũ, không tự đọc `true` từ phiên bản thư viện mới.

## 16. Tài liệu chuẩn

- [Java Language Specification, Java SE 21 — `15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29): phạm vi constant expressions, phép toán được chấp nhận và quy tắc string interning.
- [Java Language Specification, Java SE 21 — `4.12.4 final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): định nghĩa constant variable.
- [Java Language Specification, Java SE 21 — `13.4.9 final Fields and static Constant Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9): ảnh hưởng của việc đổi giá trị hằng tới pre-existing binaries.
- [Java Language Specification, Java SE 21 — `12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): truy cập trường static và khởi tạo lớp.
- [Java SE 21 — javap command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): cách quan sát bytecode, field/method references và constant pool.

**Ghi nhớ:** `final` chỉ là một phần điều kiện của constant variable; **constant expression** chịu quy tắc chặt của ngôn ngữ; **folding/inlining** có thể đặt giá trị trực tiếp vào binary consumer. Khi giá trị `public static final` cần thay đổi giữa các phiên bản, hãy kiểm tra **cả binary client** và thiết kế API, vì **binary compatibility không bảo đảm client cũ nhìn thấy giá trị mới**.
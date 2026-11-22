# `return` và các biến thể khi lời gọi hoàn thành bình thường

## 1. Mục tiêu: “trở về” ở cấp Java và ở cấp JVM là gì?

Trong Java source, từ khóa `return` làm kết thúc việc thực thi phương thức hiện tại theo nhánh bình thường, với một giá trị hoặc không có giá trị. Ở cấp JVM, **một lời gọi phương thức hoàn tất bình thường (normal method invocation completion)** khi phương thức đã được gọi đi đến một trong **sáu bytecode return phù hợp với kiểu trả về** của nó và không có exception làm thất bại quá trình hoàn tất.

Theo **JVMS `2.6.4`**, khi callee hoàn tất bình thường, JVM:

1. Hoàn tất các công việc bắt buộc trước khi thực sự kết thúc lời gọi, chẳng hạn chạy `finally` tương ứng và xử lý monitor của `synchronized method` theo ngữ nghĩa liên quan.
2. Nếu có giá trị trả về, chuyển đúng giá trị đó từ **operand stack của frame callee** sang **operand stack của frame caller**.
3. Kết thúc frame callee, khôi phục frame caller thành **current frame**.
4. Tiếp tục thực thi caller tại vị trí logic **ngay sau instruction gọi phương thức**.

Với phương thức trả `void`, không có giá trị được đẩy lên operand stack của caller.

~~~text
frame(caller)                          frame(callee)
  locals: ...                            locals: parameters ...
  operand stack trước invoke: [args]      operand stack khởi đầu: []
          |                                     |
          +------- invoke method ------------> |
                                                | thực thi code
                                                | ... -> [result]
          <----------- ireturn <----------------+
  operand stack sau invoke: [result]      frame callee kết thúc
  caller tiếp tục sau invoke
~~~

Sơ đồ biểu diễn **ngữ nghĩa frame theo đặc tả JVM**. JIT compiler có thể tối ưu hoặc inline method; không bắt buộc mỗi lời gọi phải có một native memory block tách rời nếu hành vi Java/JVMS được bảo toàn.

Phân biệt ngay ba khái niệm:

- **`return` ở source Java:** phát biểu điều khiển luồng, có thể trả biểu thức hoặc kết thúc `void` method.
- **Các opcode `return` trong bytecode:** những lệnh máy ảo thực sự kết thúc method theo đường bình thường, chọn theo **return descriptor**.
- **`ret` trong bytecode lịch sử:** nhảy về điểm sau `jsr` bên **trong cùng method**; **không phải** opcode trả giá trị cho method caller, không nên gộp vào sáu opcode của bài này.

## 2. Bảng sáu opcode: nhìn tên để biết giá trị nào trở về

JVMS `2.11.8` và `6.5` định nghĩa các lệnh return:

| Opcode JVM | Byte opcode (hex) | Kiểu trả về method hợp lệ | Giá trị phải có ở đỉnh operand stack |
| --- | --- | --- | --- |
| **`return`** | `0xb1` | `void`; constructor `<init>`, class initializer `<clinit>` | Không có giá trị cần trả |
| **`ireturn`** | `0xac` | `int`, **`boolean`, `byte`, `short`, `char`** | Một giá trị **kiểu `int`** |
| **`lreturn`** | `0xad` | `long` | Một giá trị `long` |
| **`freturn`** | `0xae` | `float` | Một giá trị `float` |
| **`dreturn`** | `0xaf` | `double` | Một giá trị `double` |
| **`areturn`** | `0xb0` | Các **reference types**: class, interface, array | Một giá trị `reference` tương thích descriptor |

Tại sao có **sáu** chứ không phải một opcode riêng cho từng kiểu Java?

- JVM dùng `int` làm kiểu tính toán chung cho `boolean`, `byte`, `char`, `short` trong nhiều ngữ cảnh bytecode. Vì vậy cả năm loại đó cùng dùng **`ireturn`**.
- `long`, `float`, `double` cần các opcode riêng phù hợp kiểu operand và cấu trúc thực thi.
- Object, array và interface values là **reference**; chúng cùng dùng **`areturn`**.
- `void` không có giá trị, nên dùng **`return`**, không dùng một giá trị giả như `null` hay `0`.

**Quy tắc verifier:** `ireturn` không hợp lệ nếu method descriptor yêu cầu `long`; `areturn` không hợp lệ nếu descriptor yêu cầu `int`; `return` không được dùng để kết thúc bình thường method khai báo trả về `String`. Các quy tắc ràng buộc này thuộc **JVMS `4.9.2`**.

### Kiểu `boolean`, `byte`, `short`, `char` đi qua `ireturn` như thế nào?

Trong frame callee, giá trị dùng bởi `ireturn` được biểu diễn là `int`. Trước khi chuyển kết quả sang caller, JVM có các chuyển đổi cần thiết theo return type đã khai báo:

- `byte`: chuyển tương đương `i2b` (thu hẹp có dấu).
- `short`: tương đương `i2s`.
- `char`: tương đương `i2c` (thu hẹp không dấu).
- `boolean`: chỉ lấy bit thấp, tức phép `AND 1` đối với giá trị `int` trong ngữ nghĩa `ireturn`.
- `int`: giữ kiểu `int`.

Compiler Java bình thường đã thực hiện các chuyển đổi cần thiết theo quy tắc ngôn ngữ, nhưng bộ kiểm tra bytecode và đường return của JVM vẫn phải tuân thủ kiểu khai báo. **Không có `breturn`, `creturn`, `sreturn`, `zreturn`** trong tập opcode JVM.

Các giá trị `long`/`double` chiếm **hai slot** trong mô hình operand stack; chúng vẫn là **một giá trị logic** được chuyển qua `lreturn`/`dreturn`. `float` và `reference` thuộc category 1.

## 3. Cấu trúc frame trước và sau return

Một lần gọi Java method có frame với **local variables array**, **operand stack** và thông tin liên kết động qua run-time constant pool. Trước khi callee thực thi, arguments được đưa vào locals của callee; operand stack của frame mới bắt đầu rỗng.

Ví dụ:

~~~java
static int add(int x, int y) {
    int result = x + y;
    return result;
}
~~~

Đây là method minh họa, cần đặt **bên trong một class** để biên dịch. Một dạng bytecode phù hợp do `javac` sinh:

~~~text
static int add(int, int);
  descriptor: (II)I
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: ireturn
~~~

Nếu caller gọi `add(4, 5)`:

~~~text
Caller frame trước invoke:
  operand stack: [4, 5]
  instruction: invokestatic add:(II)I

Callee frame lúc vào add:
  locals: slot0=x=4; slot1=y=5; slot2=result(chưa gán)
  operand stack: []

Sau iload_0:  [4]
Sau iload_1:  [4, 5]
Sau iadd:     [9]
Sau istore_2: []; local result=9
Sau iload_2:  [9]
Sau ireturn:  callee hoàn tất, result=9 về caller

Caller frame sau invoke:
  operand stack: [9]
  instruction tiếp: có thể là istore, iadd, ireturn,...
~~~

**Giá trị trả về được chuyển về operand stack của caller, không tự động gán vào một biến source.** Nếu caller viết `int answer = add(4,5);`, bytecode caller thường dùng thêm `istore` để ghi giá trị đó vào local slot. Nếu caller chỉ viết `add(4,5);` và bỏ kết quả, compiler vẫn thực hiện lời gọi rồi có thể dùng `pop` để bỏ giá trị không dùng.

Đối với `void` method, operand stack caller sau invoke **không có thêm result**, vì `return` không đưa một giá trị nào trở về. Caller cũng không thể dùng kết quả `void` trong phép cộng như một `int`.

### Quy tắc “đường sau invoke”

Khi method trả về bình thường, **PC của caller** tiếp tục sau bytecode instruction dùng để gọi method: `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial` hoặc `invokedynamic`. Địa chỉ trong mô tả này là vị trí instruction của **caller**; không nên hiểu JVM nhảy theo số dòng Java hay theo constant-pool index.

Ví dụ:

~~~text
Caller:
  0: iconst_4
  1: iconst_5
  2: invokestatic #N   // add:(II)I
  5: istore_1
  6: ...
~~~

`#N` là constant-pool index để xác định lời gọi; `5` là **BCI** ngay sau instruction invoke trong đoạn mã minh họa; `1` trong `istore_1` là **local slot index**. Chúng là ba không gian chỉ số khác nhau.

## 4. Mã Java 17+ chạy được: sáu nhóm kết quả

Tạo file **`ReturnOpcodes.java`** (một chương trình Java 17+ độc lập):

~~~java
public class ReturnOpcodes {
    static void noValue() {
        System.out.println("inside void");
    }

    static int anInt() {
        return 7;
    }

    static boolean aBoolean() {
        return true;
    }

    static byte aByte() {
        return 12;
    }

    static short aShort() {
        return 300;
    }

    static char aChar() {
        return 'A';
    }

    static long aLong() {
        return 4_000_000_000L;
    }

    static float aFloat() {
        return 1.5f;
    }

    static double aDouble() {
        return 2.25;
    }

    static String aReference() {
        return "JVM";
    }

    static int[] anArray() {
        return new int[] {2, 3};
    }

    static String aNullReference() {
        return null;
    }

    public static void main(String[] args) {
        noValue();
        System.out.println("int=" + anInt());
        System.out.println("boolean=" + aBoolean());
        System.out.println("byte=" + aByte());
        System.out.println("short=" + aShort());
        System.out.println("char=" + aChar());
        System.out.println("long=" + aLong());
        System.out.println("float=" + aFloat());
        System.out.println("double=" + aDouble());
        System.out.println("reference=" + aReference());
        System.out.println("array=" + java.util.Arrays.toString(anArray()));
        System.out.println("null reference=" + aNullReference());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -g ReturnOpcodes.java
java ReturnOpcodes
~~~

**Stdout chính xác:**

~~~text
inside void
int=7
boolean=true
byte=12
short=300
char=A
long=4000000000
float=1.5
double=2.25
reference=JVM
array=[2, 3]
null reference=null
~~~

Tại sao output giúp phân biệt bytecode?

- `noValue()`: in thông điệp, sau đó dùng opcode `return` cuối method (dù trong source không viết `return;` tường minh).
- `anInt()`, `aBoolean()`, `aByte()`, `aShort()`, `aChar()`: cả năm đều kết thúc bằng **`ireturn`** trên class file hợp lệ.
- `aLong()`, `aFloat()`, `aDouble()`: lần lượt **`lreturn`**, **`freturn`**, **`dreturn`**.
- `aReference()`, `anArray()` và `aNullReference()`: đều là **`areturn`** dù kết quả có thể là String reference, array reference hoặc `null`. `null` là một giá trị reference hợp lệ, **không có opcode `nullreturn`**.

Trong Java source, `boolean` là kiểu riêng; ở JVM, `ireturn` sử dụng `int` representation theo rules. Chương trình trên **không** kiểm tra hành vi abnormal bytecode; nó là bằng chứng phổ thông cho cách compiler hạ type return trong class file.

### Dùng `javap` để kiểm chứng opcode thực tế

~~~bash
javap -c -p ReturnOpcodes
javap -s -p ReturnOpcodes
javap -v -p ReturnOpcodes
~~~

Cách đọc:

1. Với `-s`, nhìn descriptor `()V`, `()I`, `()Z`, `()B`, `()S`, `()C`, `()J`, `()F`, `()D`, `()Ljava/lang/String;`, `()[I`.
2. Với `-c`, tìm opcode cuối các method tương ứng: `return`, `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`.
3. Với `-v`, đọc `Code: stack=..., locals=...` cùng line numbers/constant pool. `javac -g` giúp thấy debug information để liên hệ source.
4. Tránh dùng duy nhất số bytecode offset và constant-pool index được mô tả trong bài làm “giá trị chuẩn”: chúng có thể khác theo JDK/compiler hoặc target release.

Ví dụ phần disassembly **minh họa cấu trúc, không cam kết BCI/constant-pool index cố định**:

~~~text
static int anInt();
  descriptor: ()I
  Code:
     0: bipush        7
     2: ireturn

static long aLong();
  descriptor: ()J
  Code:
     0: ldc2_w        #...   // long 4000000000l
     3: lreturn

static java.lang.String aReference();
  descriptor: ()Ljava/lang/String;
  Code:
     0: ldc           #...   // String JVM
     2: areturn

static void noValue();
  descriptor: ()V
  Code:
     ... invokevirtual #... // PrintStream.println
     ... return
~~~

Ở ví dụ source trên, một compiler có thể chọn instruction khác để nạp hằng, nhưng lệnh **return phù hợp descriptor** phải giữ quy tắc của JVM.

## 5. Descriptor quyết định opcode return hợp lệ

**Method descriptor** trong class file cho biết dạng `(parameter types)return type`, ví dụ:

| Method Java | JVM descriptor | Opcode return |
| --- | --- | --- |
| `void write()` | `()V` | `return` |
| `int sum(int,int)` | `(II)I` | `ireturn` |
| `boolean valid()` | `()Z` | `ireturn` |
| `byte code()` | `()B` | `ireturn` |
| `short id()` | `()S` | `ireturn` |
| `char initial()` | `()C` | `ireturn` |
| `long count()` | `()J` | `lreturn` |
| `float ratio()` | `()F` | `freturn` |
| `double average()` | `()D` | `dreturn` |
| `String label()` | `()Ljava/lang/String;` | `areturn` |
| `int[] numbers()` | `()[I` | `areturn` |
| `Object[][] matrix()` | `()[[Ljava/lang/Object;` | `areturn` |

Những ký hiệu như `I`, `J`, `V`, `L...;` và `[` thuộc **JVMS `4.3`**. Khi phân tích bytecode, **kiểu trả về được ghi trong descriptor** là nguồn để xác định opcode nào hợp lệ; kiểu của một local variable tình cờ nằm trên stack trước đó không tự cho phép dùng một opcode return khác.

Ví dụ `return 42;` trong method khai báo `long` được compiler xử lý thành giá trị `long`, có thể qua `i2l` hoặc nạp trực tiếp constant long, rồi kết thúc bằng **`lreturn`**; không thể chỉ dùng `ireturn` để trả về `long` vì source expression vốn bắt đầu là số nguyên 42.

### Vì sao method reference khác method return?

Một lời gọi `foo()` trong bytecode caller có một **symbolic method reference** (owner/name/descriptor) hoặc call site tương ứng; lệnh return chạy **ở callee** khi phương thức thực thi xong. `return` không cần chứa constant-pool index của caller, và nó cũng không chọn lại phương thức đích. Method invocation và method completion là hai bước khác nhau.

## 6. `void` method, constructor và `<clinit>`

### Java source không viết `return;` vẫn có opcode return

~~~java
static void show() {
    System.out.println("done");
}
~~~

Method `show` kết thúc khi đến hết block. Compiler phát sinh opcode `return` tương ứng để VM biết phương thức `void` đã hoàn tất.

Bạn cũng có thể viết:

~~~java
static void choose(boolean stop) {
    if (stop) {
        return;
    }
    System.out.println("continue");
}
~~~

Trong `void` method, `return;` **không có expression**. Bytecode có thể có nhiều lối dẫn tới opcode `return`, hoặc branch/goto dẫn đến một điểm return chung. **Không** có `return void;` hay `return null;` hợp lệ trong `void` method.

### Constructor: bytecode `<init>` kết thúc bằng `return`

Constructor Java không khai báo kiểu trả về:

~~~java
class Ticket {
    final int number;

    Ticket(int number) {
        this.number = number;
    }
}
~~~

Đây là class minh họa, không có `main` để chạy độc lập. Trong class file, constructor là **instance initialization method** tên `<init>` và descriptor `(I)V`. Lệnh `return` kết thúc việc thực thi **constructor**, nhưng biểu thức `new Ticket(5)` có giá trị reference do cơ chế cấp phát/invocation ở caller cung cấp.

Điểm hay nhầm: **constructor có descriptor trả `V` không có nghĩa opcode `<init>` trả về chính object**. Khi source viết `new Ticket(5)`, kết quả expression là object reference, nhưng constructor được gọi qua `invokespecial` và hoàn tất bằng `return`, không bằng `areturn`.

### Class initializer: `<clinit>` cũng dùng `return`

Compiler có thể sinh method đặc biệt `<clinit>` cho các biểu thức khởi tạo `static` và `static` blocks. Nó có descriptor `()V`, kết thúc bình thường bằng opcode `return`. Không thể khai báo hay gọi `<clinit>` trực tiếp bằng cú pháp Java thường.

Nếu một static initializer ném exception và làm class initialization thất bại, đó **không phải** một lần hoàn tất bình thường bằng `return`. Runtime áp dụng các quy tắc class initialization error riêng của JVMS/JLS.

## 7. `return` kết thúc lời gọi, còn `ret` legacy thì không

Trong bytecode lịch sử, `jsr`/`ret` từng được dùng cho **subroutine trong cùng một method**, thường liên quan cách biên dịch `finally` cũ.

~~~text
Một method:
  jsr Lcleanup     ; đẩy returnAddress đến instruction kế tiếp
  ireturn          ; SAU KHI cleanup xong, mới trả int cho method caller

Lcleanup:
  astore_2         ; lưu returnAddress vào local slot 2
  ... cleanup ...
  ret 2            ; nhảy về instruction sau jsr, trong cùng method
~~~

Đây là **sơ đồ bytecode lịch sử, không phải chương trình hoàn chỉnh để nạp vào JVM**. `ret` dùng giá trị `returnAddress` trong local slot để chuyển PC bên trong method. `ireturn` dùng một `int` trên operand stack để hoàn tất method và chuyển giá trị về caller. **Hai lệnh không cùng chức năng**, mặc dù tên đều chứa “ret/return”.

Theo **JVMS `4.9.1`**, class files với **major version ≥ 51 (Java 7+)** không được chứa `jsr`, `jsr_w` và `ret` trong `Code`. Do đó, với bytecode tạo bằng `javac` hiện đại, hãy tìm **sáu opcode return** nêu ở mục 2, không tạo ví dụ mới bằng `ret`.

## 8. `finally`: source return có thể chưa phải opcode return ngay

Một lỗi thường gặp là cho rằng cứ gặp `return expression;` trong source thì JVM lập tức thực thi `ireturn`/`areturn` ở đúng vị trí đó. Với `try/finally`, Java phải hoàn tất công việc của `finally` trước khi phương thức thực sự trở về bình thường.

Tạo file **`FinallyReturns.java`**:

~~~java
public class FinallyReturns {
    static int normal(int input) {
        try {
            System.out.println("try=" + input);
            return input * 2;
        } finally {
            System.out.println("finally=" + input);
        }
    }

    static int overrideReturn() {
        try {
            return 10;
        } finally {
            return 20; // ví dụ cảnh báo: tránh viết return trong finally
        }
    }

    static int fail() {
        try {
            System.out.println("start");
            throw new IllegalStateException("boom");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println("normal=" + normal(4));
        System.out.println("overridden=" + overrideReturn());

        try {
            fail();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -g FinallyReturns.java
java FinallyReturns
~~~

**Stdout chính xác:**

~~~text
try=4
finally=4
normal=8
overridden=20
start
cleanup
caught=boom
~~~

### Diễn giải ba nhánh

**`normal(4)`**: biểu thức `input * 2` tính ra 8; `finally` in thông điệp; cuối cùng lời gọi trả về giá trị 8. Trong bytecode, compiler có thể lưu tạm 8 vào local slot, thực thi code `finally` rồi mới dùng `ireturn`. Một câu lệnh source `return input * 2;` do đó có thể triển khai qua **nhiều opcode và nhiều BCI**.

**`overrideReturn()`**: `finally` có `return 20;`, nên kết quả `10` dự định trả từ `try` **bị thay thế** bằng 20. Trong Java, nếu `finally` hoàn tất bất thường bằng một `return` khác hoặc ném exception, lý do hoàn tất trước đó của `try` có thể bị thay thế. Đây là lý do **không nên dùng `return` trong `finally` trong code thực tế**: nó khiến kết quả hoặc exception trước đó bị che khuất. Ví dụ đưa ra để hiểu ngữ nghĩa, không khuyến nghị phong cách viết này.

**`fail()`**: ném `IllegalStateException`, chạy `finally` để in `cleanup` rồi exception truyền ra caller. Method `fail` **không hoàn tất bình thường**, không đưa `int` result nào về `main`. `main` bắt exception rồi tiếp tục chạy bình thường.

### Vì sao `javap` có thể hiển thị nhiều opcode return?

~~~bash
javap -c -p FinallyReturns
javap -v -p FinallyReturns
~~~

Trong `normal` có thể thấy nhiều nhánh và các đoạn code in `finally` ở những đường thoát khác nhau. Compiler có thể duplicate phần code `finally` hay tổ chức handler phù hợp; **không yêu cầu chỉ có một opcode `ireturn` cho mỗi method**. Trong method `overrideReturn`, compiler có thể không phát sinh một đường `ireturn` thực sự trả 10 vì `finally` luôn thay thế kết quả.

Điều quyết định liệu method **đã hoàn tất bình thường** là **opcode return cuối cùng thực thi theo đường đi cụ thể và các ràng buộc khác**, không phải số lượng từ khóa `return` bạn đếm trong Java source.

## 9. `return` khác `throw` và việc hoàn tất bất thường

Đường bình thường (normal completion) khác với **abrupt completion**:

| Tình huống | Frame callee | Caller nhận gì? |
| --- | --- | --- |
| `return;` trong method `void` | Kết thúc bình thường | Không có giá trị trả về |
| `return 5;` từ method `int` | Kết thúc bình thường | Một `int` giá trị 5 |
| `return obj;` từ method `Object` | Kết thúc bình thường | Một reference (có thể `null`) |
| Exception bị bắt và xử lý **bên trong** callee, sau đó `return` | Cuối cùng hoàn tất bình thường | Result thích hợp nếu có |
| Exception **không được xử lý** trong callee | Kết thúc bất thường | **Không có result**; exception tiếp tục tìm handler bên ngoài |
| `finally` tự ném exception | Có thể làm kết thúc bất thường dù try đã tính result | Không có result bình thường nếu exception đi ra caller |

Theo **JVMS `2.6.5`**, invocation hoàn tất bất thường **không bao giờ trả một giá trị bình thường cho caller**. Đây là điểm rất quan trọng khi đọc opcode `athrow`: nó xử lý exception, **không phải** một kiểu `return` nữa.

Một phương thức Java khai báo `int` có thể ném exception mà không thực hiện `ireturn` trên đường đó. Quy tắc compiler kiểm tra tính đầy đủ đường `return` trong source cần tính đến các đường luôn `throw`; JVM verifier kiểm tra đường bytecode riêng.

### Ví dụ Java 17+ ngắn về exception được bắt trước return

~~~java
static int parseOrDefault(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    }
}
~~~

Đây là method minh họa nằm trong một class. Nếu parse thành công, trả `int` đã parse; nếu parse ném `NumberFormatException` và được bắt ngay trong method, method vẫn hoàn tất bình thường bằng `ireturn` với giá trị -1. Không được nói rằng “cứ gặp exception thì invocation chắc chắn abnormal”: **chỉ exception thoát ra không được xử lý trong callee** mới làm invocation đó hoàn tất bất thường.

## 10. `synchronized method`: monitor được xử lý khi return

Khi một method có modifier `synchronized`, JVM phải có ngữ nghĩa vào/ra monitor của object tương ứng:

- **Instance synchronized method** khóa monitor của receiver, tức `this`.
- **Static synchronized method** khóa monitor gắn với `Class` object đại diện class đó.
- Khi method hoàn tất bình thường, JVM xử lý việc rời monitor (hoặc cập nhật số lần tái nhập) như thể `monitorexit` thích hợp đã được thực hiện.
- Trên đường exception không được xử lý, JVM cũng phải xử lý monitor release theo quy tắc phù hợp.

Điểm kỹ thuật: **`javac` thường không tạo `monitorenter`/`monitorexit` tường minh bao quanh body của `synchronized method`**. Method được đánh dấu **`ACC_SYNCHRONIZED`**, và cơ chế invocation/return của VM xử lý monitor. Ngược lại, **`synchronized (lock) { ... }` block** trong source thường được compiler chuyển thành `monitorenter`/`monitorexit` và exception handler cần thiết trong `Code`.

Tạo file **`SynchronizedReturn.java`**:

~~~java
public class SynchronizedReturn {
    private int counter;

    public synchronized int increment() {
        counter++;
        return counter;
    }

    public static void main(String[] args) {
        SynchronizedReturn sample = new SynchronizedReturn();
        System.out.println("first=" + sample.increment());
        System.out.println("second=" + sample.increment());
    }
}
~~~

~~~bash
javac -g SynchronizedReturn.java
java SynchronizedReturn
javap -v -p SynchronizedReturn
~~~

**Stdout của chương trình:**

~~~text
first=1
second=2
~~~

Trong `javap -v -p`, hãy tìm method `increment` với **`ACC_PUBLIC, ACC_SYNCHRONIZED`**, descriptor `()I` và opcode `ireturn`. JVM đảm bảo monitor tương ứng được xử lý khi method hoàn tất; việc trả về 1/2 không khiến khóa tiếp tục bị giữ vĩnh viễn. Lệnh `javap` chạy tiếp sau chương trình sẽ in **metadata/disassembly bổ sung**, không thuộc stdout của hai lời in từ chương trình.

**Lưu ý:** Java `synchronized` là cơ chế đồng bộ thread; ví dụ chạy một thread chứng minh output dự đoán được, **không** chứng minh tính đúng trong mọi tình huống cạnh tranh. Để phân tích concurrency, cần xem Java Memory Model, quy tắc lock và tình huống nhiều thread.

## 11. Opcode, slot và descriptor: tránh nhầm ba tầng

### `max_stack`/`max_locals` không phải số result

Một `Code` attribute trong class file chứa `max_stack` và `max_locals`:

- `max_stack` cho biết operand stack có thể sâu tối đa bao nhiêu **slots** trong lúc method chạy.
- `max_locals` cho biết dung lượng local slots cho method.
- Method return có thể đẩy **một kết quả logic** sang caller nhưng kết quả ấy có thể chiếm 1 hoặc 2 operand-stack slots.

Ví dụ:

~~~text
callee: long produce()
  descriptor: ()J
  operand stack ngay trước lreturn: [long 4000000000]
  logical values: 1
  stack slots occupied by long: 2

caller: long n = produce()
  sau invoke, caller operand stack: [long 4000000000]
  rồi lstore_<n> ghi vào 2 local slots liên tiếp
~~~

Sơ đồ trên mô tả mô hình JVMS; trong `javap`, `lstore` có local slot index, còn `#N` ở `invokestatic #N` là constant-pool index. Không có liên hệ rằng lệnh `lreturn` phải trỏ tới constant pool để biết slot chứa giá trị.

### Boolean và array không cần opcode return riêng

`boolean ok()` trong source tạo descriptor `()Z` nhưng kết thúc bằng `ireturn`; `int[] data()` tạo descriptor `()[I` nhưng kết thúc bằng `areturn`. Đây là **quy tắc cấp máy ảo**; ký hiệu descriptor và loại opcode không phải tên giống hệt Java keyword.

### Return statement trong vòng lặp

~~~java
static int firstPositive(int[] values) {
    for (int value : values) {
        if (value > 0) {
            return value;
        }
    }
    return -1;
}
~~~

Đây là method minh họa, cần đặt trong class. Vòng lặp **không tạo frame mới** mỗi vòng; chỉ có một lần gọi method và một frame. Có thể có nhiều opcode `ireturn`, mỗi đường chạy đến một trong chúng. Những nhánh không kết thúc thì tiếp tục method; opcode return thực thi nào quyết định lần gọi kết thúc ở đâu.

## 12. Lỗi phổ biến khi học và đọc bytecode return

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Java có 8 kiểu primitive nên phải có 8 return opcodes.” | `boolean`, `byte`, `char`, `short` dùng cùng `ireturn` với `int`; `void`, reference và số lớn có các opcode riêng. |
| “`ireturn` luôn yêu cầu method khai báo `int`.” | Nó cũng đúng với method `boolean`, `byte`, `short`, `char`. |
| “`return` là bytecode trả `null`.” | `return` cho `void`; `null` reference được đẩy rồi trả bằng `areturn`. |
| “`areturn` chỉ trả Java Object, không trả array.” | Mảng cũng là JVM reference type, nên dùng `areturn`. |
| “`lreturn`/`dreturn` trả hai giá trị.” | Chúng trả một giá trị category 2, chiếm hai operand-stack slots. |
| “`return 5;` của Java luôn là `ireturn`.” | Tùy **method descriptor**: method `long` phải trả bằng `lreturn`. |
| “Caller luôn nhận value ở local variables ngay khi invoke xong.” | Return result được đưa lên **operand stack của caller**; caller có thể lưu vào local. |
| “Mỗi source `return` tương ứng đúng một opcode return tại cùng BCI.” | Compiler có thể sắp xếp control flow và `finally` trước khi thực sự return. |
| “`ret` là cách rút gọn của `return`.” | `ret` là legacy subroutine branch, không phải method return. |
| “Nếu callee ném exception thì cũng trả một object exception qua `areturn`.” | Uncaught exception gây **abrupt completion**, không trả value bình thường. |
| “`finally` chạy sau khi callee đã trả value cho caller.” | `finally` cần hoàn tất trước khi caller nhận normal result; bản thân `finally` có thể thay đổi kết quả/exception. |
| “`synchronized method` luôn phải có opcode `monitorexit` in trong Code.” | Monitor vào/ra cho method được quản lý theo `ACC_SYNCHRONIZED` và invocation/return semantics. |
| “Constructor `new C()` dùng `areturn` để trả object.” | `<init>` có descriptor `()V` và dùng `return`; value của biểu thức `new` do caller-side object construction logic tạo ra. |
| “Phương thức `void` kết thúc source block không có instruction return nào.” | Compiler phải tạo đường kết thúc bytecode hợp lệ bằng `return` theo ngữ nghĩa JVM. |
| “JIT inline method nghĩa là JVM bỏ qua quy tắc return.” | Tối ưu implementation có thể thay hình dạng native code nhưng phải giữ ngữ nghĩa return quan sát được. |

## 13. Bài tập tự kiểm tra

**Câu 1.** `boolean valid()` và `int answer()` có cùng opcode hoàn tất bình thường không?  
**Đáp án:** Có, đều dùng **`ireturn`** theo descriptor tương ứng.

**Câu 2.** Phương thức `long count()` có `return 2;` trong source. Opcode kết thúc là gì?  
**Đáp án:** **`lreturn`**, vì method khai báo `long`. Compiler phải tạo một giá trị long phù hợp trước khi return.

**Câu 3.** `String[] names()` và `int[] numbers()` dùng opcode gì?  
**Đáp án:** Cả hai dùng **`areturn`**, vì array là reference type.

**Câu 4.** Khi `callee()` trả `int 9` bình thường, frame caller tiếp tục với result ở đâu?  
**Đáp án:** Trên **operand stack của caller**; caller có thể dùng ngay trong phép toán hoặc ghi vào local.

**Câu 5.** `return;` trong một method `void` có đẩy `null` lên caller không?  
**Đáp án:** Không. Opcode `return` không chuyển giá trị.

**Câu 6.** Constructor `Ticket(int)` có JVM descriptor nào, và opcode cuối bình thường?  
**Đáp án:** `(I)V`, dùng **`return`**. Constructor không trả object reference bằng `areturn`.

**Câu 7.** `try { return 10; } finally { return 20; }` nhận giá trị gì ở caller?  
**Đáp án:** **20**, vì `finally` thay thế lý do hoàn tất trước đó. Không nên dùng kiểu code này trong thực tế.

**Câu 8.** Một method `int` ném exception không được bắt trong chính method. Có `ireturn` nào đưa value về caller không?  
**Đáp án:** Không, invocation hoàn tất **bất thường** và không có return value bình thường.

**Câu 9.** `ret 2` trong file Java 6 cũ có tương đương `ireturn` không?  
**Đáp án:** Không. `ret` dùng returnAddress để nhảy trong cùng method sau `jsr`. `ireturn` kết thúc method và trả một `int` cho caller.

**Câu 10.** Method `synchronized int increment()` có cần compiler chèn cặp `monitorenter`/`monitorexit` tường minh ở thân Code không?  
**Đáp án:** Không cho việc khóa ở cấp synchronized method; JVM xử lý monitor implicit nhờ `ACC_SYNCHRONIZED`, và `ireturn` tham gia đường kết thúc bình thường.

## 14. Tài liệu chính thức

- [JVMS Java SE 25 — `2.6` Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): frame, local variables, operand stack và việc caller/callee chuyển quyền điều khiển.
- [JVMS Java SE 25 — `2.6.4` Normal Method Invocation Completion](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.4): kết thúc bình thường, khôi phục caller, trả giá trị.
- [JVMS Java SE 25 — `2.6.5` Abrupt Method Invocation Completion](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.5): kết thúc bất thường không có normal result.
- [JVMS Java SE 25 — `2.11.8` Method Invocation and Return Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.11.8): ánh xạ kiểu dữ liệu sang các opcode return.
- [JVMS Java SE 25 — `6.5` JVM Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): mục `return`, `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn` và ràng buộc synchronized monitor.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): các ký hiệu `V`, `I`, `J`, `F`, `D`, `L...;`, `[` và dạng method descriptor.
- [JVMS Java SE 25 — `4.9.2` Structural Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.9.2): opcode return phải đúng kiểu trả về đã khai báo.
- [JLS Java SE 25 — `14.17` The return Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.17): `return` ở Java source, kể cả khi có `try/finally`.
- [JLS Java SE 25 — `14.20.2` Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.2): cách `finally` ảnh hưởng normal/abrupt completion.
- [Oracle JDK 25 — `javap`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): dùng `javap -c -s -v -p` để xem opcode return, descriptor và metadata.

**Ghi nhớ khi đọc bytecode:** nhìn **return descriptor** của method trước, sau đó xem **opcode return** trên từng nhánh. Một lời gọi chỉ hoàn tất bình thường khi thực thi đúng lệnh return và các xử lý cần thiết hoàn tất; **value đi về operand stack caller**, còn exception không được xử lý làm invocation hoàn tất bất thường và **không tạo result bình thường**.
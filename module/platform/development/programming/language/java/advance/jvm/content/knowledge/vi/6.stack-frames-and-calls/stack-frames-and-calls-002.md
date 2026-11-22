# JVM Frame và lời gọi phương thức: truyền đối số, vị trí `this` và giá trị trả về

Khi một phương thức Java gọi phương thức khác, JVM phải chuyển các giá trị đối số từ ngữ cảnh **bên gọi** sang ngữ cảnh **bên được gọi**, xác định đối tượng nhận lời gọi `this` nếu có, sau đó đưa giá trị trả về về đúng nơi. Cơ chế được mô tả bằng **operand stack**, **local-variable array**, **frame** và các bytecode `invoke*` / `*return`.

Một sự phân biệt quan trọng:

- **Ở phía bên gọi (caller):** bytecode chuẩn bị `objectref` (nếu là instance call) và các giá trị đối số **trên operand stack của frame hiện tại**.
- **Khi lệnh gọi thực thi:** JVM xử lý lời gọi, lập frame mới cho phương thức Java đích theo mô hình đặc tả, gán receiver/đối số vào **local variables của frame mới**.
- **Trong bên được gọi (callee):** local slot `0` là `this` với instance method, nhưng là đối số đầu tiên với static method.
- **Khi trả về bình thường:** lệnh `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn` hoặc `return` kết thúc frame callee; nếu có giá trị, giá trị được chuyển về **operand stack của caller**.

Đây là **mô hình JVM ở cấp bytecode**. HotSpot có thể inline method, dùng thanh ghi CPU, loại bỏ cấp phát và tối ưu cách bố trí frame vật lý. Không nên lấy sơ đồ logic dưới đây làm cam kết mỗi lời gọi luôn tạo một native stack frame hữu hình.

## 1. Bức tranh tổng quát: hai frame riêng biệt

Giả sử source Java:

```java
static int add(int x, int y) {
    return x + y;
}

static int calculate() {
    int result = add(2, 3);
    return result * 10;
}
```

Đây là **các phương thức minh họa**, chưa phải class chạy độc lập. Ở mức bytecode, trình tự tư duy:

```text
Caller frame: calculate()                      Callee frame: add(int,int)
┌───────────────────────────────────┐         ┌──────────────────────────────┐
│ Local variables                   │         │ Local variables             │
│  slot 0: result (sau khi store)   │         │  slot 0: x = 2              │
│                                   │         │  slot 1: y = 3              │
│ Operand stack (ngay trước invoke) │         │ Operand stack: lúc bắt đầu   │
│  ... , int 2 , int 3              │──invoke►│  rỗng                       │
└───────────────────────────────────┘         └──────────────────────────────┘
                                                         │
                                                 iload_0, iload_1
                                                         │
                                                     iadd → 5
                                                         │
                                                     ireturn
                                                         ▼
Caller được tiếp tục:
  operand stack có int 5
  istore_0 → lưu result = 5
  iload_0, bipush 10, imul, ireturn → trả 50
```

**Hai operand stacks khác nhau:** khi `add()` bắt đầu, operand stack của frame mới **rỗng**; tham số đã trở thành **local variables** của frame `add`, không phải tiếp tục nằm nguyên trên stack operand của callee. Ngược lại, trước lệnh `invokestatic add`, caller phải đẩy đủ đối số theo đúng thứ tự.

Mỗi frame gắn với **một lời gọi phương thức cụ thể**. Nếu `add` gọi tiếp phương thức khác, một frame khác trở thành frame hiện tại; frame `add` tạm không còn là current frame cho đến khi lời gọi bên trong kết thúc.

## 2. Cấu trúc một frame trong JVM

Trong mô hình Java Virtual Machine Specification (JVMS), mỗi invocation của phương thức Java tạo một frame chứa:

| Thành phần frame | Nhiệm vụ |
| --- | --- |
| **Local-variable array** | Chứa receiver `this` nếu có, các tham số và biến cục bộ/tạm thời; truy cập qua index 0,1,2,... |
| **Operand stack** | Đưa toán hạng cho các lệnh bytecode, chuẩn bị đối số gọi method và nhận kết quả trả về |
| **Dynamic-linking information** | Hỗ trợ resolve các tham chiếu ký hiệu đến field/method/type trong runtime constant pool |
| **Thông tin trả về** | Phục vụ khôi phục luồng thực thi và chuyển kết quả về caller theo ngữ nghĩa VM |

Frame nằm trong ngữ cảnh **Java Virtual Machine stack của thread** gọi nó. Mỗi JVM thread có stack/frame logic riêng, nên biến cục bộ trong lời gọi của thread A không tự động là cùng local-variable array với lời gọi của thread B.

Thông số được ghi trong `Code` attribute của class file:

- `max_locals`: số **local slots** tối đa cần cho một frame của phương thức, bao gồm receiver, parameters và temporaries.
- `max_stack`: độ sâu tối đa tính theo đơn vị của **operand stack**.
- `code_length` và `code[]`: các bytes chứa chỉ thị bytecode của phương thức.

Hai vùng này độc lập; không thể dùng `max_stack` để suy số biến Java hay dùng `max_locals` để suy số object còn sống trên heap.

### 2.1. Khi tạo frame mới, operand stack ban đầu rỗng

Ở thời điểm phương thức Java mới bắt đầu, JVM đã đưa receiver/các giá trị đối số vào **local variables của callee**. Việc tính toán trong callee tiếp tục qua lệnh `iload`, `aload`, `dload`, `lload`,... để đưa local values lên operand stack của chính nó.

Ví dụ `add(int,int)` có bytecode minh họa:

```text
0: iload_0
1: iload_1
2: iadd
3: ireturn
```

Trong phương thức `static` đó:

- `iload_0` lấy local `0 = x` lên operand stack.
- `iload_1` lấy local `1 = y`.
- `iadd` pop hai `int` và push kết quả.
- `ireturn` pop một `int` từ operand stack callee, trả nó về caller.

Đừng nhầm local slot `0` của `add` với local slot `0` của `calculate`: đó là **hai frame khác nhau** dù có cùng chỉ số.

## 3. Truyền đối số: bên gọi dùng operand stack, bên nhận dùng local variables

### 3.1. Bước chuẩn bị ở caller

Với lời gọi `add(2, 3)` trong Java source, compiler tạo logic tương tự:

```text
iconst_2              // push argument 2
iconst_3              // push argument 3
invokestatic #...     // gọi add:(II)I
                      // kết quả int được push về operand stack caller
```

Operand stack là last-in-first-out, nhưng điều đó **không đảo thứ tự tham số**: compiler đặt các giá trị theo **thứ tự phù hợp với method descriptor**, và lệnh invoke biết cách lấy chúng. Với static call `add(int x, int y)`, `2` tương ứng `x`, `3` tương ứng `y`.

Khi các biểu thức đối số có side effects, Java Language Specification còn quy định thứ tự đánh giá expression. Trước khi gọi được thực hiện, biểu thức argument phải được đánh giá hợp lệ theo thứ tự ngôn ngữ Java, trừ những trường hợp lời gọi fail sớm theo quy tắc của biểu thức gọi (ví dụ ngoại lệ khi đánh giá receiver). Không được tự giả định đánh giá từ phải qua trái chỉ vì operand stack là LIFO.

### 3.2. Local variables của callee

Một phương thức **static** nhận tham số bắt đầu tại local index **0**:

```java
static int sum(int left, int right) {
    return left + right;
}
```

```text
Callee local variables
index 0 = left
index 1 = right
```

Một phương thức **instance** dành local index **0** cho receiver:

```java
int sum(int left, int right) {
    return left + right;
}
```

```text
Callee local variables
index 0 = this
index 1 = left
index 2 = right
```

**`this` không được viết tường minh trong method descriptor**. Đối với instance method, `this` là receiver được JVM truyền bằng một tham chiếu object. Một method có ba tham số source vẫn có thể dùng bốn local slots chỉ cho receiver và các tham số nếu cả ba đều category 1.

### 3.3. `long` và `double` chiếm hai local-variable slots

Quy tắc category 2 của JVM:

- `long` và `double`: mỗi giá trị dùng **hai local-variable slots liên tiếp**.
- `int`, `float`, tham chiếu object: thường dùng **một slot** theo mô hình JVM.
- `boolean`, `byte`, `short`, `char` thường được xử lý qua int-family bytecodes trong những thao tác được quy định.
- Một giá trị `long`/`double` chỉ được tải từ **index thấp hơn** của cặp slot. Index cao hơn không phải nửa giá trị có thể đọc riêng bằng `iload`.

Xét:

```java
static long staticWork(long base, double rate, int extra) {
    return base + (long) (rate * extra);
}

long instanceWork(long base, double rate, int extra) {
    return base + (long) (rate * extra);
}
```

Bảng:

| Phương thức | Slot 0 | Slot 1 | Slot 2 | Slot 3 | Slot 4 | Slot 5 |
| --- | --- | --- | --- | --- | --- | --- |
| `staticWork(JDI)J` | `base` (long) | phần 2 của `base` | `rate` (double) | phần 2 của `rate` | `extra` (int) | — |
| `instanceWork(JDI)J` | `this` | `base` (long) | phần 2 của `base` | `rate` (double) | phần 2 của `rate` | `extra` (int) |

Vậy:

- `staticWork` cần **ít nhất 5 local slots** cho parameters; `lload_0` tải `base` và `dload_2` tải `rate`.
- `instanceWork` cần **ít nhất 6 local slots** cho receiver và parameters; `lload_1` tải `base` và `dload_3` tải `rate`.
- Cả hai có **ba tham số Java**, dù số parameter slots khác nhau. `long` và `double` không được tính thành hai đối số nguồn.

Descriptor JVM của cả hai là **`(JDI)J`**, vì chúng nhận `long` (`J`), `double` (`D`), `int` (`I`) và trả `long` (`J`). Receiver `this` không nằm trong descriptor.

## 4. Receiver `this`: xuất hiện ở đâu và khi nào?

Một instance method cần object target. Trong Java source, receiver có thể hiện rõ hoặc ngầm định:

```java
item.process(5);    // receiver là item
process(5);         // trong instance method: receiver ngầm là this
this.process(5);    // receiver viết tường minh
```

Trong class file, khi method được gọi bằng cơ chế instance invocation thích hợp, **operand stack của caller có object reference**, và callee nhận reference đó ở **local slot 0**.

Ví dụ lời gọi `item.process(5)`:

```text
Caller operand stack trước lời gọi (đáy → đỉnh):
    ..., objectref(item), int(5)
                           ▲ đỉnh

invokevirtual process:(I)V
    │
    ▼
Callee frame của item.process:
    local 0 = objectref(item) → this
    local 1 = 5              → tham số
    operand stack = rỗng khi bắt đầu
```

Đặc biệt:

- **Static method không có receiver `this`.** Không thể dùng `this` trong thân static method như instance method.
- **Instance method có receiver ở local 0** theo quy tắc parameter passing, kể cả khi source không hề dùng từ khóa `this`.
- **Static nested class** vẫn có instance methods và `this` của **chính** nested class đó; “static” trong `static class Nested` không làm mọi method của nó trở thành static.
- **Constructor `<init>`** là một trường hợp instance initialization: receiver ở local 0 trong frame constructor. Trước khi object initialization hoàn thành, verifier áp dụng thêm ràng buộc về reference chưa được khởi tạo.
- **Instance synchronized method** cũng có receiver ở local 0; cơ chế monitor được JVM quản lý theo lời gọi, không cần tự viết `monitorenter` như với block `synchronized`.

### 4.1. `this` không phải là một object được copy nguyên khối

Java truyền **giá trị của reference**. Khi callee nhận receiver, nó không tạo một object mới giống hệt receiver. Caller và callee đều có reference tới **cùng object**; thao tác trên field của object đó có thể quan sát được bên ngoài khi được phép.

Vì thế:

```java
void setValue(int next) {
    this.value = next;
}
```

Thay field `this.value` tác động tới cùng object mà caller đang giữ. Điều đó **không phải** “Java truyền object theo tham chiếu” theo nghĩa có thể gán lại biến reference gốc ở bên gọi.

### 4.2. Có thể có `NullPointerException` trước khi callee bắt đầu

Với `obj.method()` và `obj == null`, một instance invocation không thể có receiver hợp lệ để bắt đầu method tương ứng; JVM có thể ném `NullPointerException` theo quy tắc opcode. **Không có frame callee chạy thân phương thức `method()` bình thường** rồi mới kiểm tra null.

Nếu lời gọi còn đối số là các biểu thức có side effects, cần hiểu thứ tự đánh giá của **Java source** và thời điểm kiểm tra null theo ngữ nghĩa gọi cụ thể. Không mặc định “không có gì bên trong biểu thức lời gọi được đánh giá” chỉ vì receiver null.

## 5. Năm bytecode dành cho method invocation

| Opcode | Dạng lời gọi chủ yếu | Có receiver `this` truyền trực tiếp? |
| --- | --- | --- |
| `invokestatic` | Static method của class/interface | **Không** |
| `invokevirtual` | Instance method với cơ chế lựa chọn mục tiêu phù hợp runtime class | **Có** |
| `invokeinterface` | Gọi interface method trên một object, với resolution/dispatch phù hợp | **Có** |
| `invokespecial` | Constructor `<init>`, private instance method, lời gọi `super`/một số lời gọi đặc biệt | **Có** |
| `invokedynamic` | Call site được liên kết qua bootstrap method; thường liên quan lambda, string concatenation, dynamic language support | **Không có receiver ngầm cố định**; tất cả argument types có trong call-site descriptor |

Đây là phân nhóm giúp đọc bytecode, không phải định nghĩa đầy đủ mọi trường hợp đặc biệt như signature-polymorphic methods hoặc thay đổi lựa chọn method qua version JVM.

### 5.1. `invokestatic`

```java
int answer = Math.abs(-7);
```

Nếu gọi static method, caller chuẩn bị các arguments trên operand stack, sau đó `invokestatic` thực hiện gọi. Callee nhận tham số đầu ở local 0. Không có `this` hay objectref cho class `Math`.

**Không phải** vì `Math.abs` không dùng object nên nó “không cần frame” theo mô hình JVM: lời gọi static Java method vẫn có ngữ nghĩa invocation; runtime/JIT có thể tối ưu hoặc dùng intrinsic.

### 5.2. `invokevirtual`

```java
String text = "hello";
int size = text.length();
```

Caller đặt objectref `text` lên operand stack rồi gọi method. JVM dựa vào loại đối tượng/phân giải method để chọn implementation theo quy tắc virtual dispatch. Ở callee, slot 0 là `this`.

Một lời gọi Java source có thể liên hệ với phương thức override; điều này không thay đổi vị trí receiver/arguments ở callee.

### 5.3. `invokeinterface`

```java
Runnable job = () -> System.out.println("run");
job.run();
```

Về ngữ nghĩa, `job.run()` gọi interface method trên receiver object. Operand stack có objectref `job` trước `invokeinterface`; receiver trở thành local 0 của method được chọn.

Tính trừu tượng interface không có nghĩa JVM không có đối tượng nhận lời gọi.

### 5.4. `invokespecial` và constructor

```java
Object item = new Object();
```

Bytecode điển hình ở caller:

```text
new java/lang/Object
dup
invokespecial java/lang/Object.<init>:()V
astore_1  // nếu compiler chọn local 1 cho item
```

**`new`** tạo reference đến object chưa khởi tạo theo ngữ nghĩa JVM; **`dup`** giữ một reference trên operand stack để dùng sau khi constructor hoàn tất. **`invokespecial <init>`** gọi instance initialization method có receiver, nhưng constructor có descriptor **trả `void`**, nên lệnh gọi constructor **không trả objectref như kết quả method**. Reference dùng cho `astore_1` là reference được giữ bằng `dup`.

Đoạn bytecode trên là **minh họa**; index lưu biến sẽ phụ thuộc chỗ đoạn code xuất hiện, và JVM verifier kiểm tra việc object reference chưa khởi tạo được sử dụng đúng quy tắc.

### 5.5. `invokedynamic` khác ở cách liên kết call site

`invokedynamic` được liên kết theo bootstrap method; call-site descriptor khai báo arguments và kiểu trả về. Không phải mọi dynamic call đều có một `this` ngầm ở slot 0 như instance invocation.

Nếu một argument là object reference, nó chỉ là **một đối số tường minh theo descriptor** của call site. Khi bootstrap dẫn tới thực thi Java methods khác, những phương thức đó vẫn tuân theo ngữ nghĩa frame và receiver phù hợp với kiểu gọi thực tế.

## 6. Kiểu trả về quyết định opcode và tác động lên caller stack

Java source `return expression;` được compiler chuyển thành lệnh return có loại phù hợp với descriptor.

| Kiểu trả về | Opcode JVM | Giá trị chuyển về caller |
| --- | --- | --- |
| `int` và các kiểu `boolean`, `byte`, `short`, `char` theo dạng phù hợp | `ireturn` | Một giá trị int-family, category 1 |
| `long` | `lreturn` | Một giá trị `long`, category 2 |
| `float` | `freturn` | Một giá trị `float`, category 1 |
| `double` | `dreturn` | Một giá trị `double`, category 2 |
| Reference type, array | `areturn` | Một object/array reference, category 1 |
| `void`, constructor `<init>` | `return` | **Không có giá trị trả về** |

Điều đáng nhớ là opcode `return` **không có chữ cái đứng trước** chỉ dùng khi method trả `void`. `ireturn` và `areturn` không phải hai cách tùy ý để trả cùng một loại; verifier và method descriptor ràng buộc kiểu phù hợp.

### 6.1. Trả về không đồng nghĩa ghi trực tiếp vào biến của caller

Giả sử:

```java
int result = add(2, 3);
```

Callee dùng `ireturn` để đưa `5` về **operand stack của caller**. Sau đó caller mới quyết định làm gì với kết quả:

```text
caller: iconst_2, iconst_3, invokestatic add:(II)I
                                    │
callee: iload_0, iload_1, iadd, ireturn
                                    │
                                    ▼
caller operand stack: [..., int 5]
caller: istore_0            // lưu vào biến local result
```

Nếu caller viết `System.out.println(add(2, 3))`, kết quả có thể được dùng trực tiếp để tạo arguments cho lệnh gọi tiếp theo mà **không cần `istore` vào một local variable**.

Đối với `long` hoặc `double`, giá trị trả về vẫn là **một giá trị category 2**, chiếm **hai đơn vị độ sâu** trên operand stack caller. Không có hai lệnh return cho hai nửa của nó.

### 6.2. Sau khi return, frame nào hiện hành?

Khi một phương thức hoàn tất bình thường:

1. Method trả giá trị (nếu có) bằng typed return opcode.
2. Frame callee bị loại khỏi ngữ cảnh frame hiện hành theo mô hình JVM.
3. Frame caller trở lại là frame hiện hành.
4. JVM khôi phục luồng thực thi ở vị trí **tiếp sau invocation instruction** của caller.
5. Giá trị trả về (nếu có) trở thành một giá trị trên operand stack của caller.

Đó là lý do caller có thể tiếp tục tính toán với kết quả của callee mà không cần truy cập trực tiếp local variables riêng của callee.

Các chi tiết runtime như machine registers, return address vật lý hoặc optimizations không làm thay đổi kết quả ngữ nghĩa này.

### 6.3. `void` và trường hợp ngoại lệ

Với phương thức:

```java
static void log(String message) {
    System.out.println(message);
}
```

Khi `log` kết thúc bằng `return`, caller **không được push bất kỳ giá trị method return nào**. Thân method có thể đã tạo side effects (in stdout), nhưng không có kết quả biểu thức để sử dụng.

Ngược lại, nếu callee ném exception và không xử lý ở trong nó, phương thức kết thúc **abruptly**, không có giá trị return bình thường. JVM tìm exception handler phù hợp, có thể unwind qua các frames cho tới khi gặp handler thích hợp hoặc thread kết thúc.

**Không được nói “exception được trả về như một object ở operand stack qua `areturn`”.** Exception propagation là cơ chế điều khiển riêng; khi handler được chọn, JVM thiết lập trạng thái operand stack cho handler theo đặc tả.

## 7. Ví dụ Java 17 chạy được: static call, instance call, `this` và long return

Tạo file **`FrameCallDemo.java`**:

```java
public class FrameCallDemo {
    private final int factor;

    public FrameCallDemo(int factor) {
        this.factor = factor;
    }

    static long mix(long base, double ratio, int extra) {
        return base + (long) (ratio * extra);
    }

    long adjust(long base, double ratio, int extra) {
        return mix(base, ratio, extra) + factor;
    }

    static void display(long value) {
        System.out.println("display=" + value);
    }

    public static void main(String[] args) {
        FrameCallDemo demo = new FrameCallDemo(3);
        long result = demo.adjust(10L, 2.5, 4);

        System.out.println("result=" + result);
        display(result);
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac --release 17 FrameCallDemo.java
java FrameCallDemo
```

**Stdout chính xác:**

```text
result=23
display=23
```

Tại `mix`: `(long) (2.5 * 4) = (long) 10.0 = 10L` nên `base + 10 = 20L`. `adjust` cộng thêm field `factor = 3` và trả `23L`. `display` chỉ in kết quả, không trả value.

### 7.1. Sơ đồ lời gọi trong chương trình

```text
main(String[] args)
  local 0 = args
  local 1 = demo (tham chiếu, trong bytecode thông thường)
  local 2–3 = result (long)

  new FrameCallDemo
    └─ invokespecial <init>(I)V
         local 0 = this (demo)
         local 1 = factor = 3
         return (void)

  gọi demo.adjust(10L, 2.5, 4)
    caller operand stack:
      [..., demo ref, long 10, double 2.5, int 4]
    invokevirtual adjust:(JDI)J
         │
         ▼
         frame adjust:
           local 0 = this
           local 1–2 = base (long)
           local 3–4 = ratio (double)
           local 5   = extra (int)
           │
           └─ invokestatic mix:(JDI)J
                 frame mix:
                   local 0–1 = base
                   local 2–3 = ratio
                   local 4   = extra
                   lreturn 20L
           │
           <long 20L> trở về operand stack của adjust
           đọc this.factor và cộng → lreturn 23L
         │
         ▼
    main nhận long 23L trên operand stack
    lstore ...  → result = 23L

  gọi static display(result)
    invokestatic display:(J)V
    callee local 0–1 = result (long)
    return (void), không có giá trị
```

Sơ đồ local của `main` là **một cách cấp phát thường thấy** từ `javac` cho mã này; compiler khác có thể tái sử dụng index khác. Local index cho **receiver và tham số tại đầu `adjust`, `mix`, `display`** lại được quy định bởi thứ tự/type của method descriptor, bất kể có bao nhiêu temporaries ở thân method.

### 7.2. Tại thời điểm `invokevirtual adjust`, stack caller chứa gì?

Method descriptor: **`(JDI)J`**.

| Thứ tự từ đáy lên đỉnh của các giá trị cho lời gọi | Kiểu | Độ sâu operand stack tăng |
| --- | --- | ---: |
| Object reference `demo` | Reference | 1 |
| `10L` | Long (category 2) | 2 |
| `2.5` | Double (category 2) | 2 |
| `4` | Int | 1 |
| **Tổng** | Receiver + ba đối số | **6 đơn vị** |

Caller phải có đủ operand stack capacity tại điểm này. Lệnh gọi tiêu thụ các giá trị trên. Frame `adjust` có receiver ở slot 0, các giá trị tham số ở slot 1–5. Khi `adjust` kết thúc bằng `lreturn`, caller nhận **một giá trị long** có độ sâu 2 trên operand stack.

**Lưu ý:** con số 6 là độ sâu **của chính các giá trị dùng cho lời gọi**. `max_stack` thực tế của cả phương thức `main` có thể cao hơn tùy những phép tính và instruction khác.

### 7.3. Quan sát bytecode bằng `javap`

```bash
javap -c -p FrameCallDemo
javap -v -p FrameCallDemo
```

Các vùng cần tìm:

- `FrameCallDemo(int)`: `aload_0` lấy `this`, `iload_1` lấy tham số `factor`, `putfield` ghi field, cuối cùng `return`.
- `static long mix(long, double, int)`: `lload_0` lấy `base`, `dload_2` lấy `ratio`, `iload 4` lấy `extra`; các lệnh nhân/chuyển kiểu/cộng sẽ dẫn tới `lreturn`.
- `long adjust(long, double, int)`: `lload_1`, `dload_3`, `iload 5` chuẩn bị arguments cho `invokestatic mix`. Sau đó lấy `this.factor` và dùng `lreturn`.
- `static void display(long)`: nhận `long` ở local slots 0–1; cuối phương thức có `return`.
- `main`: `new`, `dup`, `invokespecial <init>` khi tạo instance; `invokevirtual adjust` với descriptor `(JDI)J`; `lstore` lưu kết quả và `invokestatic display` khi in.

Các lệnh exact offsets có thể khác giữa các compiler, cấu hình compiler và version JDK. Bảng chỉ nêu **những quan hệ bytecode cốt lõi** cần đối chiếu, không giả định mọi compiler đặt cùng instruction index.

### 7.4. `max_locals` không phải số tham số nguồn

Với `adjust(long, double, int)`, ngay khi vào method:

```text
Slot 0     : this
Slot 1,2   : long base
Slot 3,4   : double ratio
Slot 5     : int extra
Cần ít nhất 6 local slots
```

Với `mix(long, double, int)`:

```text
Slot 0,1   : long base
Slot 2,3   : double ratio
Slot 4     : int extra
Cần ít nhất 5 local slots
```

Không có cặp `long` hoặc `double` nào bắt buộc phải bắt đầu ở index chẵn. `adjust` có `long` ở `1–2` và `double` ở `3–4` hoàn toàn hợp lệ.

## 8. Java truyền tham số theo giá trị, kể cả reference

Một hiểu nhầm xuất hiện khi nghe “truyền đối số object”: Java **luôn truyền các giá trị** của primitive hoặc reference. Caller đặt một **bản sao giá trị** vào lời gọi; callee nhận giá trị ấy trong local variable của frame riêng.

Với primitive:

```java
static void change(int value) {
    value = 99;
}
```

Gán lại `value` của callee không làm biến `int` của caller đổi theo.

Với reference:

```java
static void mutateBox(Box box) {
    box.value = 99; // Thay đổi trạng thái object được chia sẻ qua reference.
}

static void replaceBox(Box box) {
    box = new Box(); // Chỉ gán lại local reference của callee.
}
```

Đoạn trên là **minh họa** và yêu cầu khai báo `Box` khi đưa vào chương trình. Ví dụ độc lập có ngay dưới đây.

### 8.1. Ví dụ chạy được: thay object khác với gán lại reference

Tạo file **`ReferenceValueDemo.java`**:

```java
public class ReferenceValueDemo {
    static class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 99;
    }

    static void replace(Box box) {
        box = new Box(123);
        System.out.println("inside replace=" + box.value);
    }

    public static void main(String[] args) {
        Box shared = new Box(10);

        mutate(shared);
        System.out.println("after mutate=" + shared.value);

        replace(shared);
        System.out.println("after replace=" + shared.value);
    }
}
```

Chạy:

```bash
javac ReferenceValueDemo.java
java ReferenceValueDemo
```

Stdout:

```text
after mutate=99
inside replace=123
after replace=99
```

Lý do:

- `shared` trong `main` chứa một **reference value** tới object `Box`.
- Khi gọi `mutate(shared)`, reference value được sao chép thành parameter `box` tại **local slot 0** của static callee. Cả hai references cùng chỉ một object, nên đổi field thấy từ caller.
- Khi gọi `replace(shared)`, phép `box = new Box(123)` chỉ đổi **local slot của callee** sang object mới; `shared` ở frame caller vẫn chỉ tới object cũ có `value = 99`.
- Không có phép “truyền biến `shared` theo tham chiếu” để callee trực tiếp thay ô local của caller.

Điều này cũng áp dụng khi truyền receiver `this`: reference đến object được dùng để chọn/khởi chạy instance method, chứ bản thân object không bị sao chép sang frame mới.

## 9. Đánh giá đối số, boxing và varargs trước method invocation

Mã Java có thể trông như chỉ “đưa một biến” vào lời gọi, nhưng compiler có thể phát sinh những phép toán chuẩn bị giá trị.

### 9.1. Thứ tự đánh giá arguments

```java
static int first() {
    System.out.print("A");
    return 1;
}

static int second() {
    System.out.print("B");
    return 2;
}

static int add(int a, int b) {
    return a + b;
}
```

Khi caller gọi `add(first(), second())`, Java đánh giá các biểu thức đối số theo thứ tự phù hợp với ngôn ngữ (với trường hợp đơn giản trên: `first()` rồi `second()`), chuẩn bị chúng cho `invokestatic add`. Side effects in `A` trước `B`. LIFO stack **không** có nghĩa `second()` thực thi trước `first()`.

### 9.2. Boxing và unboxing

Với lời gọi `accept(Integer.valueOf(7))` hoặc `accept(7)` khi chữ ký nhận `Integer`, compiler có thể phát sinh boxing method call trước method invocation chính.

Với parameter primitive `int` mà caller có `Integer`, compiler có thể gọi `intValue()` để unbox, và có thể ném `NullPointerException` nếu reference null. Những lời gọi/chuyển đổi này là công việc chuẩn bị arguments; callee cuối cùng vẫn nhận **kiểu đã được khai báo trong descriptor**.

### 9.3. Varargs thực chất là array parameter

```java
static int count(String... items) {
    return items.length;
}
```

Chữ ký runtime có parameter là `String[]` (descriptor `([Ljava/lang/String;)I`). Với `count("a", "b")`, compiler thường tạo một `String[]` gồm hai phần tử rồi truyền **một array reference** vào callee. Không có opcode đặc biệt tên `invokevarargs` và không có hai local parameters tách rời cho `"a"`, `"b"`.

Tuy nhiên Java source có thể truyền trực tiếp một mảng phù hợp trong một varargs invocation. Khi kiểm tra bytecode, đừng suy số lượng slot chỉ từ số phần tử varargs ở vị trí gọi.

## 10. Method descriptor: bản đồ loại đối số và loại trả về

Method descriptor của JVM ghi **loại và thứ tự** parameters, rồi loại return. Ví dụ:

```text
(I)I                         int → int
(II)I                        (int,int) → int
(JDI)J                       (long,double,int) → long
(Ljava/lang/String;)V        (String) → void
([Ljava/lang/String;)V       (String[]) → void
()D                          () → double
()Ljava/lang/Object;         () → Object
```

Quy tắc nhận diện:

| Ký tự descriptor | Kiểu |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `V` | `void` (chỉ cho return type) |
| `Lpkg/Type;` | Class/interface reference |
| `[` theo sau một kiểu | Một chiều array; nhiều `[` cho nhiều chiều |

Descriptor **không ghi `this`** cho instance methods. Điều này thường gây nhầm lẫn khi so sánh với local slots:

```text
instance method: adjust:(JDI)J

descriptor parameter types: 3
receiver objectref:        1 (ngầm khi gọi instance)
parameter local slots:     2 + 2 + 1 = 5
total local slots đầu vào: 1 + 5 = 6

static method: mix:(JDI)J

descriptor parameter types: 3
receiver objectref:        0
parameter local slots:     2 + 2 + 1 = 5
total local slots đầu vào: 5
```

**Không nên lấy số dấu phẩy hay độ dài chuỗi descriptor** để suy `max_locals`. Với reference `Ljava/lang/String;` dù chuỗi descriptor dài, nó vẫn là **một reference category 1** ở JVM.

## 11. Sự khác biệt giữa hoàn tất bình thường và exception propagation

Giả sử:

```java
static int parse(String text) {
    return Integer.parseInt(text);
}
```

Nếu `text` hợp lệ, callee trả một `int`, bên gọi tiếp tục và có thể dùng kết quả.

Nếu `Integer.parseInt` ném `NumberFormatException`:

1. Lời gọi sâu hơn không hoàn tất bình thường.
2. JVM tìm handler `catch` phù hợp trong các frames theo quy tắc exception dispatch.
3. Nếu không có handler trong một frame, frame đó bị unwound, các ngữ cảnh gọi được rời bỏ.
4. Tại handler được chọn, exception object được đưa vào trạng thái operand stack phù hợp để handler sử dụng (thường là phần tử duy nhất của stack tại điểm handler).
5. Không có typed return value bình thường cho lời gọi `parse` nếu exception chưa được bắt và xử lý để quay lại đường thực thi thường.

Một phương thức có thể dùng `try/finally` hoặc `try-with-resources`; Java compiler phải đảm bảo side effects phù hợp trong quá trình return/exception. Điều đó có thể bổ sung handler/branch bytecode, nhưng không biến exception thành `ireturn` hay `areturn`.

### 11.1. Điều gì xảy ra khi callee là native method?

Với `native` method, JVM có thể chuyển sang code native thông qua cơ chế triển khai phụ thuộc platform (ví dụ JNI), nên cách passing arguments ở mức ABI/native stack có thể khác. Tuy nhiên từ góc nhìn bytecode Java caller, lời gọi vẫn tuân theo descriptor, objectref/argument values và kiểu kết quả mà JVM quy định.

Do đó không được suy “nếu Java method nhận `long` ở hai slots thì C function JNI nhận đúng hai thanh ghi 32-bit” mà không hiểu ABI riêng.

## 12. Frame recursion, stack overflow và vòng đời dữ liệu

Nếu phương thức tự gọi lại, **mỗi invocation có frame riêng**:

```java
static int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
```

Với `factorial(3)`, các frames logic tồn tại trong lúc gọi sâu:

```text
factorial(3) ─ đang đợi factorial(2)
    factorial(2) ─ đang đợi factorial(1)
        factorial(1) ─ ireturn 1
    factorial(2) ─ nhân 2 * 1, ireturn 2
factorial(3) ─ nhân 3 * 2, ireturn 6
```

Mỗi callee có local slot `0` chứa `n` **riêng của lời gọi đó**. Caller đang đợi không bị overwrite local `n` khi một frame mới cũng dùng slot 0.

Đệ quy sâu có thể dẫn tới `StackOverflowError` khi JVM stack không đủ chỗ cho những frame cần thiết. Nó khác với `OutOfMemoryError: Java heap space`. Tăng heap `-Xmx` không phải giải pháp mặc định cho stack overflow; cần xem thuật toán, recursion depth và giới hạn stack phù hợp.

**Đời sống dữ liệu:** local primitive hoặc reference trong frame không phải mãi tồn tại sau khi method kết thúc. Nếu local giữ reference tới object được caller/trường static/container khác giữ lại, object có thể vẫn reachable trên heap sau return. Frame hết hoạt động không chứng minh GC sẽ thu hồi object ngay.

## 13. JVM có thực sự tạo frame vật lý cho mọi lời gọi?

JVMS mô tả **ngữ nghĩa** dưới dạng frames và operand stacks. Một JVM tối ưu như HotSpot có thể:

- **Inlining:** thay lời gọi bằng mã của callee trong compiled caller, trong khi vẫn giữ hành vi Java.
- **Scalar replacement:** loại bỏ allocation không cần thiết hoặc biểu diễn dữ liệu ở các thanh ghi/giá trị nội bộ.
- **Register allocation:** đặt arguments/temporaries trong CPU registers thay vì layout y hệt biểu đồ local slots.
- **Deoptimization:** phục hồi trạng thái Java-level phù hợp khi những giả định tối ưu không còn đúng.
- **Native/intrinsic calls:** thực hiện một số thao tác theo cơ chế đặc thù, không hiện ra như một chuỗi bytecode thông dịch đầy đủ ở runtime.

Không được suy rằng “method nhỏ có `invokestatic` chắc chắn làm chậm do phải tạo OS thread hoặc native frame mới”. Gọi một phương thức bình thường **không tạo thread mới**, và JIT có thể tối ưu chi phí invocation.

Khi phân tích kết quả profiler/thread dump, một số frame logic có thể được tái dựng hoặc biểu diễn theo quy ước của công cụ; đừng đồng nhất mọi khung logic Java với một vùng cố định trong machine stack.

## 14. Thực hành xem `max_locals`, `max_stack` và call stack

### 14.1. Kiểm tra `FrameCallDemo` với `javap`

```bash
javac --release 17 FrameCallDemo.java
javap -c -p FrameCallDemo
javap -v -p FrameCallDemo
```

Tìm phần phương thức `adjust`. Đặc biệt xem:

1. **Method descriptor `(JDI)J`.** Nó mô tả ba tham số và kết quả `long`.
2. **Không có `this` trong descriptor**, nhưng lệnh `aload_0` trong instance method tham chiếu receiver.
3. **`lload_1` và `dload_3`:** cho thấy `long`/`double` bắt đầu ở slots 1/3.
4. **`invokestatic`:** gọi `mix` không có objectref.
5. **`lreturn`:** trả `long` bằng typed return instruction.
6. **`Code: stack=..., locals=..., args_size=...`:** chỉ số do `javap` in để giúp hiểu, nhưng nhớ `max_locals` và stack depth là khái niệm khác nhau.

Dùng `javac -g` nếu cần thông tin debug như `LocalVariableTable`. Không có debug local-variable names thì bạn vẫn đọc được index qua lệnh bytecode và method descriptor.

### 14.2. Hiểu ví dụ stack trace

Khi Java exception được in, thường thấy:

```text
Exception in thread "main" java.lang.IllegalArgumentException: invalid
    at Example.callee(Example.java:20)
    at Example.caller(Example.java:12)
    at Example.main(Example.java:5)
```

Đây là **mẫu minh họa**, không phải output của các chương trình ở trên. Stack trace thể hiện chuỗi lời gọi Java gần thời điểm exception: callee ở trên, caller ở dưới. Nó không in nguyên local-variable array hay operand stack theo chỉ số.

Muốn xem chi tiết method signature và instruction, dùng `javap`; muốn quan sát các lời gọi/runtime frames, dùng debugger/profiler/thread dump theo phạm vi thích hợp. Tránh dự đoán chính xác physical frame layout từ stack trace.

### 14.3. Phân biệt phương thức và thread

Một lời gọi `demo.adjust(...)` **thêm frame logic** trên JVM stack của thread hiện tại; nó không tự tạo thread mới. Chỉ khi chương trình sử dụng Thread/Executor/virtual thread mechanism phù hợp thì có một ngữ cảnh thread mới cho task. Trong mỗi thread, nhiều frame method có thể xuất hiện trong call chain; các thread không chia sẻ local slots của nhau.

## 15. Các nhầm lẫn thường gặp

1. **“Method arguments được truyền trực tiếp vào local slots của caller.”** Sai. Caller chuẩn bị arguments trên **operand stack caller**; callee nhận chúng trong **local-variable array riêng**.
2. **“Instance method có tham số đầu ở slot 0.”** Sai. Slot 0 là `this`; tham số đầu bắt đầu ở 1.
3. **“Static method vẫn có `this` ở slot 0 nhưng không dùng.”** Sai. Static method không nhận receiver, tham số đầu bắt đầu ở 0.
4. **“Có ba tham số thì cần đúng ba slots.”** Sai khi có `long` hoặc `double` chiếm hai slots, và instance receiver thêm một slot.
5. **“Constructor trả object bằng `areturn`.”** Sai. `<init>` có return descriptor `V`; reference object để gán được giữ từ `new`/`dup` ở caller.
6. **“`ireturn` lưu kết quả thẳng vào biến Java `result`.”** Sai. Nó trả về operand stack caller; caller có thể `istore` sau đó, hoặc dùng trực tiếp.
7. **“`return` trả một giá trị null.”** Sai. `return` dành cho method `void`, không push kết quả nào.
8. **“Java truyền object theo tham chiếu nên callee đổi được biến caller.”** Sai. Java truyền **giá trị reference**; gán lại local parameter không thay local variable caller.
9. **“Object được copy mỗi khi dùng `this`.”** Sai. Reference được truyền, nhiều frames có thể tham chiếu cùng object heap.
10. **“`invokedynamic` luôn có `this` như `invokevirtual`.”** Sai. Argument list đến từ call-site descriptor, không có receiver ngầm bất biến.
11. **“Phương thức `throw` exception vẫn sử dụng `areturn`.”** Sai. Exception propagation là abrupt completion, không có typed normal return.
12. **“Mỗi lời gọi bytecode luôn tạo thêm native stack frame vật lý ở HotSpot.”** Không phải cam kết. JIT có thể inline và tối ưu layout nhưng phải giữ ngữ nghĩa Java.
13. **“`max_stack` là số lượng method invocation đang mở.”** Sai. Nó là độ sâu tối đa operand stack của **một** frame, không phải độ sâu call stack.
14. **“Frame của hai thread dùng chung local slot 0.”** Sai. Chỉ số có nghĩa trong từng frame cụ thể, không phải tên biến chia sẻ toàn JVM.
15. **“`lreturn` trả hai giá trị `int`.”** Sai. Nó trả **một giá trị `long` category 2**.

## 16. Tự kiểm tra (có đáp án)

**Câu 1.** Method `static double avg(long sum, int count)` có parameter slots nào?

**Đáp án:** `sum` ở slots **0–1**, `count` ở slot **2**. Method cần ít nhất **3 slots** cho tham số, descriptor `(JI)D`.

**Câu 2.** Nếu `avg(long,int)` trở thành instance method, các index thay đổi thế nào?

**Đáp án:** Slot **0** là `this`, `sum` ở **1–2**, `count` ở **3**. Descriptor **vẫn `(JI)D`**, vì receiver không ghi trong descriptor.

**Câu 3.** Một instance method nhận `long, double, int`, caller cần chuẩn bị những gì trên operand stack ngay trước `invokevirtual`?

**Đáp án:** Từ đáy lên đỉnh: **objectref**, **long**, **double**, **int**, theo descriptor. Tổng độ sâu dành cho chúng là **1+2+2+1 = 6** đơn vị.

**Câu 4.** Method `static long parse(...)` kết thúc bằng `lreturn`. Giá trị đi đâu?

**Đáp án:** Một `long` category 2 được đưa về **operand stack của caller**; caller có thể dùng tiếp hoặc `lstore` vào local variable riêng.

**Câu 5.** Tại sao `new SomeType()` không có nghĩa constructor `<init>` trả về reference bằng `areturn`?

**Đáp án:** Constructor descriptor trả **`void`**. Bytecode `new` tạo uninitialized object reference; caller có thể giữ một bản bằng `dup` trong khi `invokespecial <init>` thực hiện initialization, rồi dùng reference đã giữ.

**Câu 6.** Vì sao `replace(Box box)` gán `box = new Box()` không thay giá trị biến `shared` của caller?

**Đáp án:** `box` là local parameter trong frame callee, chứa bản sao của **giá trị reference**. Gán lại nó không ghi vào local slot chứa `shared` trong frame caller.

**Câu 7.** Nếu `callee` ném exception chưa được bắt, caller có nhận normal return trên operand stack không?

**Đáp án:** Không. JVM xử lý **abrupt completion** và stack unwinding; không có normal return value nếu đường exception không được xử lý để đi tiếp theo một lời gọi thành công.

**Câu 8.** Vì sao một phương thức Java rất nhỏ có nhiều lần gọi không nhất thiết tạo chi phí frame vật lý tương ứng?

**Đáp án:** JIT có thể inline/tối ưu lời gọi, dùng thanh ghi và những biểu diễn nội bộ khác; JVM chỉ phải bảo toàn **ngữ nghĩa** invocation và return theo Java/JVMS.

## 17. Tổng hợp bằng một sơ đồ

```text
                 Frame của caller (current)
                 ┌───────────────────────────────┐
                 │ Local variables: dữ liệu riêng│
                 │ Operand stack:               │
                 │ [..., receiver?, arg1, arg2] │
                 └───────────────┬───────────────┘
                                 │ invoke*
                                 │ lấy receiver/args đúng descriptor
                                 ▼
                 Frame của callee (new current)
                 ┌───────────────────────────────┐
                 │ Instance: slot 0 = this        │
                 │ Static:   slot 0 = param đầu  │
                 │ long/double = hai local slots │
                 │ Operand stack: ban đầu rỗng   │
                 │ Thực thi lệnh của callee      │
                 └───────────────┬───────────────┘
                                 │
                     ┌───────────┴───────────┐
                     │                       │
                  *return                 athrow /
               normal completion          exception
                     │                       │
                     ▼                       ▼
        Kết quả → caller operand       Tìm handler /
        stack (nếu non-void)           unwind frames
                     │
                     ▼
            Caller tiếp tục sau invoke
```

**Điểm cốt lõi:** Caller chuẩn bị đối số **trên operand stack của chính mình**; callee nhận giá trị đó trong **local-variable array của frame mới**. **`this` chiếm local slot 0 ở instance methods**, còn static methods bắt đầu tham số ở slot 0. Typed return opcodes đưa **một giá trị có kiểu** về operand stack caller; `void` và exception không có normal return value. Mô hình này giúp đọc bytecode, descriptor, frame, đệ quy và stack trace đúng mà không đánh đồng các khái niệm với stack native hay vị trí bộ nhớ vật lý.

### Tài liệu tham khảo chuẩn

- [JVMS Java SE 17 — Frames (`2.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 17 — Local Variables (`2.6.1`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1): quy tắc `this`, static parameters và category-2 slots.
- [JVMS Java SE 17 — Operand Stacks (`2.6.2`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): argument preparation và method results.
- [JVMS Java SE 17 — Normal/Abrupt Method Invocation Completion (`2.6.4–2.6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.4).
- [JVMS Java SE 17 — Method Descriptors (`4.3.3`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3).
- [JVMS Java SE 17 — Method invocation opcodes (`6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- [JVMS Java SE 17 — Compiling examples: Passing/Receiving Arguments (`3.5–3.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-3.html#jvms-3.6).
- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).

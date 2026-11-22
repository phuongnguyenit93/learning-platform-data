# Mỗi lời gọi tạo frame: biến cục bộ, operand stack và liên kết động

## 1. Hiểu frame là gì và tại sao mỗi lời gọi cần một frame riêng

Khi mã Java gọi một phương thức, JVM cần nhớ **các tham số và biến cục bộ của lần gọi đó**, nơi đặt các giá trị trung gian trong lúc tính toán, cách tra cứu những tham chiếu đến class/field/method và nơi tiếp tục khi phương thức kết thúc. Theo **Java Virtual Machine Specification (JVMS) `2.6`**, mỗi lần gọi phương thức tạo một **frame** mới theo mô hình JVM, và frame đó tồn tại cho đến khi lần gọi hoàn tất bình thường hoặc hoàn tất bất thường do exception.

Một frame chứa ba thành phần cốt lõi:

1. **Local variables array**: các ô đánh số từ 0 để lưu `this` (với phương thức instance), tham số và giá trị cục bộ/tạm.
2. **Operand stack**: ngăn xếp LIFO để nạp giá trị, tính toán, chuẩn bị đối số, nhận kết quả của lời gọi phương thức.
3. **Tham chiếu tới run-time constant pool** của class/interface định nghĩa phương thức hiện tại: hỗ trợ **dynamic linking** từ symbolic references trong class file tới các thành phần runtime.

Frame còn tham gia chuyển **giá trị trả về**, tiếp tục điểm thực thi của caller và xử lý **exception**. JVM có thể lưu thêm thông tin riêng của triển khai; **ba thành phần trên là mô hình đặc tả**, không buộc HotSpot hoặc một JVM khác phải đặt từng frame thành một khối native memory riêng với layout giống sơ đồ sách.

### Minh họa một chuỗi lời gọi

~~~text
Một Java thread, theo thứ tự thời gian:

main() bắt đầu
  Thread's JVM stack:
  ┌─────────────────────────────────────┐
  │ frame(main)    <-- current frame    │
  └─────────────────────────────────────┘

main() gọi calculate(4)
  ┌─────────────────────────────────────┐
  │ frame(calculate) <-- current frame  │
  ├─────────────────────────────────────┤
  │ frame(main)                         │
  └─────────────────────────────────────┘

calculate(4) gọi add(4, 4)
  ┌─────────────────────────────────────┐
  │ frame(add)   <-- current frame      │
  ├─────────────────────────────────────┤
  │ frame(calculate)                    │
  ├─────────────────────────────────────┤
  │ frame(main)                         │
  └─────────────────────────────────────┘

add() trả 8 -> frame(add) kết thúc.
calculate() nhận 8, cộng 1, trả 9 -> frame(calculate) kết thúc.
main() tiếp tục với giá trị 9.
~~~

**Mỗi lần gọi là một frame khác nhau**, kể cả khi gọi lại cùng một phương thức. Trong một thread, chỉ frame của phương thức **đang thực thi** là current frame theo mô hình JVMS; khi gọi phương thức khác, frame của caller tạm ngừng và frame của callee trở thành current.

**Không nhầm** JVM stack (chứa các frame của một thread) với **operand stack** (nằm **bên trong từng frame**). Cũng không nhầm với **heap**, nơi các object/array thường được cấp phát theo mô hình JVM. Một local variable chứa `reference` có thể tham chiếu object trên heap; nó **không phải** bản sao toàn bộ object.

## 2. JVM stack và vòng đời của frame

Theo **JVMS `2.5.2`**, mỗi JVM thread có **JVM stack riêng**, được tạo khi thread hình thành. Các frame của một thread không được thread khác trực tiếp tham chiếu hay chia sẻ. Các thread có thể dùng chung object trên heap, nhưng **local variables và operand stack của từng frame** thuộc lần thực thi cụ thể của thread đó.

Quy trình trừu tượng khi một Java method gọi một Java method khác:

1. Caller tính các đối số trên operand stack của **frame caller**.
2. Lệnh invoke được thực hiện; JVM xác định method cần gọi theo ngữ nghĩa bytecode và tạo **frame cho lần gọi mới**.
3. Đối số (và receiver `this` nếu là instance method) được đưa vào **local variables của frame callee**. Operand stack của frame mới ban đầu **rỗng**.
4. Callee thực thi các bytecode, thao tác trên locals/operand stack của **chính frame callee**.
5. Nếu callee `return`/`ireturn`/`areturn`… bình thường, frame callee kết thúc; kết quả nếu có được chuyển về operand stack của caller và caller tiếp tục tại lệnh sau invoke.
6. Nếu exception không được xử lý trong callee, callee kết thúc **bất thường**; JVM tìm handler thích hợp bằng cơ chế exception dispatch và có thể tiếp tục tháo các frame trước đó.

Một frame được giải phóng theo **kết thúc lần gọi**, không theo phạm vi ngoặc nhọn của một khối `if`/`for`. Vòng lặp trong **một** phương thức thường dùng lại **một frame**, còn mỗi lời gọi đệ quy tạo thêm một frame trừu tượng.

### Mô hình tuần tự, không phải layout vật lý tuyệt đối

JVMS cho phép triển khai tối ưu hóa cách cấp phát và quản lý frame. Chẳng hạn JIT có thể **inline** một phương thức, tránh tạo một frame native độc lập tương ứng ở thời điểm thực thi mã máy, miễn giữ ngữ nghĩa chương trình và bảo đảm quan sát thích hợp. Stack trace, debug và deoptimization chịu ảnh hưởng của các cơ chế runtime. Khi nói “mỗi lời gọi tạo frame”, ta đang mô tả **hợp đồng máy ảo trừu tượng**.

JVM stack theo JVMS có thể có kích cỡ cố định hoặc khả năng mở rộng. Một chuỗi lời gọi quá sâu có thể gây `StackOverflowError`; nếu triển khai không thể cấp phát/mở rộng stack theo nhu cầu, có tình huống gây `OutOfMemoryError`. Những cơ chế native stack, `-Xss`, layout frame và tối ưu JIT là chi tiết của runtime cụ thể, không phải các local slots được Java source điều khiển trực tiếp.

## 3. Local variables array: slot 0, tham số và biến cục bộ

Mỗi frame có mảng **local variables** dài `max_locals` slots theo code của method. Slot được đánh số từ **0**; các bytecode `iload_0`, `iload_1`, `istore_2`, `aload_0`… tham chiếu chỉ số trong **frame hiện tại**.

### Static method và instance method

| Loại method | Slot đầu | Các slot tiếp theo |
| --- | --- | --- |
| `static int sum(int a, int b)` | `slot 0 = a` | `slot 1 = b`; các biến cục bộ bắt đầu sau tham số |
| `int sum(int a, int b)` (instance) | `slot 0 = this` | `slot 1 = a`, `slot 2 = b`; rồi biến cục bộ |
| Constructor `MyClass(int n)` | `slot 0 = this` | `slot 1 = n`; sau đó local/tạm |

**`this` không phải một biến riêng bắt buộc ở slot 0 của mọi method.** Static method không có receiver instance; slot 0 của nó thường chứa tham số đầu tiên. Constructor là một loại instance initialization method, có receiver ở slot 0 nhưng đối tượng đang qua quá trình khởi tạo cần tuân thủ các quy tắc đặc biệt của verifier.

Khi method có nhiều tham số, JVM chuyển chúng vào các slot liên tiếp theo **độ rộng kiểu**, không theo số lượng tên biến:

- `int`, `float`, `reference` (và các giá trị thuộc nhóm một slot) dùng **1 slot**.
- `long` và `double` dùng **2 slot liên tiếp**. Bytecode truy cập giá trị này từ **chỉ số thấp hơn**; không được `lload` từ slot thứ hai.
- Một giá trị `long` ở local slot 1 chiếm slot **1 và 2**; tham số tiếp theo bắt đầu tại **slot 3**.
- Slot thứ hai của `long`/`double` không phải một biến Java độc lập của cùng giá trị; việc ghi đè một slot có thể làm mất hiệu lực nội dung giá trị hai-slot.

Sơ đồ hai phương thức:

~~~java
static int add(int a, int b) {
    int sum = a + b;
    return sum;
}

long blend(long base, double factor, int delta) {
    long total = base + delta;
    return total + (long) factor;
}
~~~

Đây là **các method minh họa phải nằm bên trong một class**, không phải file Java hoàn chỉnh chạy độc lập.

~~~text
add(int a, int b) — static:
  slot 0: a             int
  slot 1: b             int
  slot 2: sum           int             (compiler thường dùng)

blend(long base, double factor, int delta) — instance:
  slot 0: this          reference
  slot 1: base          long (slot 1 + slot 2)
  slot 2: phần thứ hai của base
  slot 3: factor        double (slot 3 + slot 4)
  slot 4: phần thứ hai của factor
  slot 5: delta         int
  slot 6: total         long (slot 6 + slot 7)
  slot 7: phần thứ hai của total
~~~

**Không nhất thiết slot nào cũng mang đúng một tên biến Java suốt cả method.** Compiler có thể dùng slot cho giá trị tạm, tái sử dụng slot khi phạm vi sống khác nhau và tối ưu code. `max_locals` đo **dung lượng slot cần cấp cho frame**, không đếm số biến được khai báo trong source. Compiler có thể chọn layout khác trong những trường hợp phức tạp.

### LocalVariableTable khác local variables runtime

Mảng locals là thành phần runtime theo JVMS. `LocalVariableTable` là **debug attribute tùy chọn** trong class file, giúp ánh xạ slot sang tên biến và phạm vi BCI. Nếu biên dịch bằng `javac -g:none`, tên local có thể không xuất hiện trong `javap -l` nhưng JVM vẫn có locals và vẫn thực thi `iload`/`istore` bình thường.

Không nhầm:

- **`max_locals`**: thông tin dung lượng locals bắt buộc khi method có `Code`.
- **`LocalVariableTable`**: metadata debug tùy chọn.
- **StackMapTable**: metadata **verification type frames**, không phải bảng chứa tất cả frame runtime đang gọi nhau.

## 4. Operand stack: nơi bytecode xử lý các giá trị trung gian

Operand stack của **mỗi frame** là ngăn xếp LIFO (**last in, first out**). Khi frame mới được tạo, operand stack bắt đầu **trống**. Các bytecode sau đó:

- Đẩy hằng: `iconst_1`, `bipush 10`, `ldc`…
- Nạp locals: `iload_n`, `aload_n`, `lload_n`…
- Đọc field: `getstatic`, `getfield`…
- Lấy các toán hạng khỏi đỉnh stack, tính toán rồi đẩy kết quả: `iadd`, `imul`, `dadd`…
- Cất kết quả vào locals: `istore_n`, `astore_n`…
- Chuẩn bị receiver/arguments cho invoke; nhận giá trị trả về nếu callee trả một giá trị.
- Dùng một giá trị để branch (`ifeq`, `if_icmpgt`…), lưu field, trả về (`ireturn`) hoặc ném exception (`athrow`).

### Theo dõi phép cộng

Với `add(int a, int b)`, một compiler như `javac` có thể sinh chuỗi bytecode tương đương:

~~~text
0: iload_0
1: iload_1
2: iadd
3: istore_2
4: iload_2
5: ireturn
~~~

Đây là **disassembly minh họa hợp lý**. Bytecode offsets/biến thể có thể khác theo compiler, nhưng ngữ nghĩa các lệnh là cố định. Nếu `a=4`, `b=4`:

| Opcode | Locals liên quan | Operand stack sau lệnh (trái: đáy; phải: đỉnh) |
| --- | --- | --- |
| Vào method | `slot0=4, slot1=4` | `[]` |
| `iload_0` | Đọc `a` | `[4]` |
| `iload_1` | Đọc `b` | `[4, 4]` |
| `iadd` | Không đổi locals | `[8]` |
| `istore_2` | Ghi `sum=8` | `[]` |
| `iload_2` | Đọc `sum` | `[8]` |
| `ireturn` | Trả 8, frame kết thúc | Giá trị 8 chuyển về **operand stack của caller** |

Khi `iadd` chạy, nó **pop hai giá trị kiểu `int`** rồi push một giá trị `int`. Không nên tưởng tượng operand stack là một `java.util.Stack` do ứng dụng tạo ra; đó là cơ chế máy ảo phục vụ thực thi bytecode.

### Chiều sâu stack không đồng nghĩa số phần tử

`max_stack` đo độ sâu tối đa bằng **đơn vị slot**. `long` và `double` mỗi giá trị đóng góp **hai đơn vị** độ sâu; các loại category 1 đóng góp một.

Ví dụ khi bytecode đang giữ trên stack:

~~~text
[reference, long, int]

Số giá trị logic: 3
Độ sâu tính theo slot: 1 + 2 + 1 = 4
~~~

Vì vậy `max_stack=4` không có nghĩa method gọi bốn method khác hay JVM có bốn frame. Đó là độ sâu tối đa của **operand stack bên trong một frame** theo thông tin `Code`.

### Quy tắc kiểu và thao tác stack

Các lệnh bytecode có ràng buộc kiểu:

- `iadd` cần hai giá trị `int` tương thích.
- `ladd` cần hai giá trị `long` tương thích.
- `swap` chỉ hoán đổi các giá trị **category 1** thích hợp; không được chia đôi giá trị `long`/`double`.
- `dup`/`dup2` có các dạng sử dụng tùy category của các giá trị phía trên.
- `checkcast`, `aastore`, lời gọi method và các lệnh khác có ràng buộc riêng.

Verifier kiểm tra cấu trúc và tính hợp lệ của luồng kiểu theo JVMS. Không được lấy một `long` từ hai `int` tùy tiện chỉ vì tổng dung lượng chiếm hai slot.

## 5. Liên kết động: frame dùng run-time constant pool ra sao?

Khái niệm thứ ba thường ít rõ ràng hơn locals và operand stack là **dynamic linking**. Theo **JVMS `2.6.3`**, mỗi frame giữ một tham chiếu tới **run-time constant pool của class/interface chứa method hiện tại**. Code trong class file có thể chứa các **symbolic references** tới class, field và method khác.

Ví dụ Java:

~~~java
static int twice(int value) {
    return add(value, value);
}
~~~

Một disassembly có thể thể hiện:

~~~text
0: iload_0
1: iload_0
2: invokestatic #NN  // Method add:(II)I
5: ireturn
~~~

`#NN` là chỉ số constant pool **của class chứa `twice`**; nó không phải địa chỉ máy, số dòng source hay slot locals. Constant-pool entry dẫn tới **tên owner, tên method và descriptor**. Khi cần, VM dùng cơ chế resolution để chuyển symbolic reference này sang thông tin runtime cụ thể.

~~~text
twice() bytecode:
   invokestatic #NN
          |
          v
run-time constant pool (của class định nghĩa twice)
   #NN -> Methodref Example.add:(II)I
          |
          | method resolution (khi cần)
          v
resolved runtime method / thông tin liên kết
          |
          v
invoke add(...) -> tạo frame(add)
~~~

Đây là mô hình khái niệm. **Resolution có thể được thực hiện sớm hoặc muộn** theo luật JVMS, và VM có thể cache kết quả; không có yêu cầu rằng mỗi lần `invokestatic` chạy lại phải tìm tên symbol từ đầu. Ngoài ra:

- **Resolution** trả lời tham chiếu biểu tượng tương ứng thành phần runtime nào; nó có thể cần load/link class liên quan và kiểm tra truy cập.
- **Dynamic dispatch** trả lời implementation nào được chọn khi gọi một method có thể override, chẳng hạn `invokevirtual`/`invokeinterface`. Nó liên quan nhưng **không đồng nhất** với việc resolve symbolic reference.
- **`invokedynamic`** là một opcode với cơ chế call site/bootstrap riêng; nó **không phải** tên khác của “dynamic linking có trong mọi frame”.

Vì vậy câu “frame chứa **tham chiếu tới run-time constant pool** để hỗ trợ liên kết động” chính xác hơn câu “mỗi frame chứa bản sao toàn bộ constant pool” hoặc “mỗi lời gọi đều phải tra bảng phương thức từ đầu”.

### Phân biệt runtime constant pool với operand stack

| Cơ chế | Chứa gì? | Dùng khi nào? |
| --- | --- | --- |
| **Constant pool / run-time constant pool** | Symbolic information, constants, resolved references phù hợp triển khai | Liên kết tới field/method/class và nạp hằng |
| **Local variables** | `this`, tham số, giá trị local/tạm của lần gọi | `iload`, `istore`, `aload`, `lstore`… |
| **Operand stack** | Các giá trị trung gian và đối số chờ thao tác | Arithmetic, branch, invoke, return |
| **JVM stack** | Chuỗi **frames** của thread | Quản lý những lần gọi đang hoạt động |

Đặt các khái niệm này đúng chỗ rất quan trọng khi đọc output `javap -c -v` và khi giải thích một lỗi linking/verification.

## 6. Chương trình chạy được Java 17+: quan sát lời gọi lồng nhau

Tạo file **`FrameTrace.java`**:

~~~java
public class FrameTrace {
    static int add(int left, int right) {
        int sum = left + right;
        return sum;
    }

    static int calculate(int value) {
        int doubled = add(value, value);
        return doubled + 1;
    }

    public static void main(String[] args) {
        int answer = calculate(4);
        System.out.println("result=" + answer);
    }
}
~~~

Dùng Java 17+:

~~~bash
javac -g FrameTrace.java
java FrameTrace
~~~

**Stdout chính xác:**

~~~text
result=9
~~~

Ta có `add(4, 4) = 8`, rồi `calculate(4) = 8 + 1 = 9`.

### Theo dõi từng frame

**Thời điểm A — vào `main`:**

~~~text
frame(main)
  locals: slot0 = args (String[])
  operand stack: []
  link: run-time constant pool của FrameTrace
~~~

**Thời điểm B — `main` gọi `calculate(4)`:**

~~~text
current frame = frame(calculate)
  locals: slot0 = value = 4
  operand stack: []
  link: run-time constant pool của FrameTrace

suspended caller frame(main)
  locals: slot0 = args
  program execution will continue after invokestatic calculate
~~~

**Thời điểm C — `calculate` chuẩn bị `add(value, value)`:**

~~~text
frame(calculate) trước invoke:
  iload_0  -> operand stack = [4]
  iload_0  -> operand stack = [4, 4]
  invokestatic add:(II)I

new frame(add):
  locals: slot0 = left = 4
          slot1 = right = 4
  operand stack: []       <-- mới tạo, không mang sang nguyên stack caller
  link: run-time constant pool của FrameTrace
~~~

**Thời điểm D — `add` trả về 8:**

~~~text
frame(add):
  tính sum = 8
  ireturn 8
  -> frame(add) kết thúc

frame(calculate) tiếp tục:
  operand stack sau invoke = [8]
  istore_1  -> local slot1 = doubled = 8; stack = []
  iload_1, iconst_1, iadd -> [9]
  ireturn 9
  -> frame(calculate) kết thúc
~~~

**Thời điểm E — `main` tiếp tục:**

~~~text
frame(main) sau calculate(4):
  operand stack = [9]
  istore_1 -> slot1 = answer = 9
  ...
  System.out.println("result=" + answer)
~~~

Dòng cuối in `result=9`. Cùng một **run-time constant pool** của class `FrameTrace` có thể được các frame khác nhau **tham chiếu**, nhưng **locals và operand stack của mỗi frame là riêng**. Không có chuyện `add` vô tình ghi trực tiếp vào local `answer` của `main` chỉ vì cả hai cùng nằm trên JVM stack.

### Đọc bytecode thực tế để kiểm chứng

~~~bash
javap -c -p FrameTrace
javap -v -p FrameTrace
javap -l -p FrameTrace
~~~

Hãy tìm:

- `add`: `iload_0`, `iload_1`, `iadd`, `istore_2`, `iload_2`, `ireturn` (theo `javac` thông dụng).
- `calculate`: hai lệnh nạp `value`, `invokestatic` tới `add:(II)I`, lưu `doubled`, thêm 1, `ireturn`.
- `main`: `iconst_4` hoặc cách nạp hằng tương đương, `invokestatic` tới `calculate:(I)I`, lưu `answer` và code in `System.out`.
- Trong output `-v`, mỗi `Code` có `stack=...`, `locals=...` (tương ứng `max_stack` và `max_locals`), cùng constant-pool entries cho những lời gọi tham chiếu.
- `javac -g` cung cấp debug line/local information thường hiển thị bằng `LineNumberTable` và `LocalVariableTable`.

**Không giả định index `#N` hay offset BCI giống nhau trên mọi JDK.** Hãy đọc bytecode do chính compiler bạn vừa chạy tạo ra, rồi ghép `invokestatic #N` với entry `#N` trong constant pool của **cùng class file**.

## 7. `long` và `double`: vì sao local slot index nhảy cóc?

Ví dụ trên sử dụng `int` nên mỗi tham số chỉ chiếm một slot. Để thấy loại **category 2**, tạo file **`WideSlots.java`**:

~~~java
public class WideSlots {
    static long mix(long base, double adjustment, int extra) {
        long total = base + extra;
        return total + (long) adjustment;
    }

    public static void main(String[] args) {
        System.out.println("mixed=" + mix(10L, 2.9, 3));
    }
}
~~~

~~~bash
javac -g WideSlots.java
java WideSlots
javap -c -v -p WideSlots
~~~

**Stdout chính xác:**

~~~text
mixed=15
~~~

Phép tính: `10L + 3 = 13L`, `(long) 2.9 = 2L` vì phép ép Java cắt phần thập phân hướng về 0; tổng cuối là `15L`.

Đối với **static `mix(long,double,int)`**, các slot ban đầu:

| Slot | Nội dung | Ghi chú |
| --- | --- | --- |
| 0–1 | `base: long` | Hai slots, truy cập bằng chỉ số 0 |
| 2–3 | `adjustment: double` | Hai slots, truy cập bằng chỉ số 2 |
| 4 | `extra: int` | Một slot |
| 5–6 | `total: long` | Hai slots, dùng khi biến được lưu |

`max_locals` của method này theo bytecode compiler thông thường là ít nhất **7**; mọi phương án compiler phải đủ để phục vụ các slot được sử dụng. Các opcode dễ nhận ra gồm `lload_0`, `dload_2`, `iload` với index 4, `i2l`, `d2l`, `ladd`, `lstore` và `lreturn` (thứ tự tùy compiler). `lreturn` đưa một **giá trị long** về caller; không biến hai slots vật lý thành hai giá trị trả về độc lập.

Độ rộng slot chỉ là **mô hình lưu trữ JVM**, không phải lời hứa về căn chỉnh địa chỉ 64-bit. JVMS không bắt buộc `long`/`double` bắt đầu tại slot chẵn.

## 8. Đệ quy: mỗi lần gọi cùng một method vẫn có frame riêng

Đệ quy giúp nhìn rõ hơn tại sao JVM không thể dùng một bộ locals duy nhất cho mọi invocation.

Tạo file **`RecursiveFrames.java`**:

~~~java
public class RecursiveFrames {
    static int factorial(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    public static void main(String[] args) {
        System.out.println("factorial(4)=" + factorial(4));
    }
}
~~~

~~~bash
javac RecursiveFrames.java
java RecursiveFrames
~~~

**Stdout chính xác:**

~~~text
factorial(4)=24
~~~

Theo mô hình JVM:

~~~text
main()
  factorial(4): local n = 4, chờ kết quả factorial(3)
    factorial(3): local n = 3, chờ kết quả factorial(2)
      factorial(2): local n = 2, chờ kết quả factorial(1)
        factorial(1): local n = 1 -> ireturn 1
      factorial(2): 2 * 1 -> ireturn 2
    factorial(3): 3 * 2 -> ireturn 6
  factorial(4): 4 * 6 -> ireturn 24
main(): in 24
~~~

Mỗi frame `factorial` có **giá trị `n` của lần gọi riêng**. Khi gọi sâu hơn, các frame trước giữ trạng thái chờ cho tới khi nhận giá trị trả về, sau đó tiếp tục. Nếu chỉ có một biến `n` toàn cục cho mọi lời gọi, tính toán trên sẽ không thể hoạt động đúng.

**Đệ quy không giới hạn có thể làm tràn stack.** Ví dụ `factorial(-1)` trong chương trình này trả 1 ngay do điều kiện `n <= 1`; vì vậy nó **không** phải ví dụ tràn stack. Một method gọi chính nó mãi không có điều kiện dừng sẽ tiêu tốn khả năng gọi lồng nhau và có thể ném `StackOverflowError`. Đừng cố tình tạo tràn stack trong môi trường production để đo giới hạn vì giới hạn thực tế phụ thuộc runtime và cấu hình.

### Tail call, inlining và frame vật lý

Không suy rằng “có n lời gọi source thì máy luôn cấp phát n khối native stack giống hệt nhau”. HotSpot/JIT có thể inline một số lời gọi. Java/JVMS không đưa ra bảo đảm chung rằng mọi tail-recursive method được chuyển thành vòng lặp và sẽ không tràn stack. Hãy dùng thuật toán lặp hoặc cấu trúc dữ liệu phù hợp khi cần kiểm soát độ sâu.

## 9. Hoàn tất lời gọi bình thường: đưa kết quả về caller

Theo **JVMS `2.6.4`**, method kết thúc bình thường khi bytecode chạy lệnh return thích hợp:

| Opcode | Kiểu kết quả |
| --- | --- |
| `return` | `void`, không đưa giá trị kết quả lên operand stack của caller |
| `ireturn` | `int` (gồm cách biểu diễn kết quả cho `boolean`, `byte`, `char`, `short` ở cấp JVM) |
| `lreturn` | `long` |
| `freturn` | `float` |
| `dreturn` | `double` |
| `areturn` | `reference` |

Khi callee hoàn tất bình thường:

1. Kết quả (nếu có) được **chuyển vào operand stack của caller**.
2. Callee frame được loại bỏ khỏi JVM stack trừ khi triển khai dùng cách biểu diễn tối ưu khác nhưng giữ ngữ nghĩa.
3. Caller trở lại current frame, tiếp tục sau lệnh invoke với trạng thái locals/operand stack của **caller**.

Ví dụ `int x = add(2, 3);`:

~~~text
caller trước invokestatic:
  operand stack = [2, 3]

callee add khi vừa vào:
  locals = [2, 3]
  operand stack = []

callee ireturn 5

caller sau invoke:
  operand stack = [5]

caller istore_<n>:
  local x = 5
  operand stack = []
~~~

Tuy nhiên khi lời gọi hoàn tất do **uncaught exception**, **không có kết quả method bình thường** được đẩy về caller. Cách kết thúc bất thường được xử lý riêng.

## 10. Exception: tìm handler và tháo frame

Theo **JVMS `2.6.5`**, nếu một instruction ném exception mà method hiện tại không xử lý, lần gọi kết thúc **abruptly**. JVM không chạy “nhánh `ireturn` giả định” rồi đưa một kết quả tùy ý cho caller. Exception có thể truyền qua nhiều frame cho đến khi tìm được handler phù hợp, nếu không được bắt thì ảnh hưởng thread và cơ chế xử lý uncaught exception.

Tạo file **`ExceptionalFrames.java`**:

~~~java
public class ExceptionalFrames {
    static void bottom() {
        throw new IllegalStateException("boom");
    }

    static void middle() {
        bottom();
    }

    static void top() {
        try {
            middle();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        top();
        System.out.println("continued");
    }
}
~~~

~~~bash
javac -g ExceptionalFrames.java
java ExceptionalFrames
~~~

**Stdout chính xác:**

~~~text
caught=boom
continued
~~~

Luồng frame:

~~~text
main()
  top()
    middle()
      bottom()
        athrow IllegalStateException("boom")
      bottom frame kết thúc bất thường
    middle không có handler -> middle frame kết thúc bất thường
  top có handler IllegalStateException -> thực thi catch
  top kết thúc bình thường
main() tiếp tục in "continued"
~~~

Điều cần hiểu:

- `bottom()` không trả về một giá trị cho `middle()`; `middle()` cũng không hoàn tất theo đường bình thường.
- **Exception table** trong `Code` của `top` xác định vùng code được bảo vệ và handler; nó không phải chỉ là một bảng “tên exception” tĩnh của cả JVM.
- Khi VM chuyển vào handler, operand stack có trạng thái theo quy tắc exception handler (chứa exception object để bytecode xử lý), không phải giữ nguyên các giá trị trung gian ngẫu nhiên trước khi exception ném ra.
- `finally`, nếu có, vẫn tuân theo ngữ nghĩa Java riêng; đừng nhầm exception-unwinding với việc “bỏ qua tất cả finally”.

Bạn có thể xem:

~~~bash
javap -c -v -p ExceptionalFrames
~~~

Trong `top`, tìm `Exception table`, `astore` để cất exception vào local và các lời gọi `getMessage`/`println`. Hình dạng bytecode và chỉ số constant pool khác nhau theo compiler nhưng thứ tự xử lý trong ví dụ là xác định.

## 11. `max_stack` và `max_locals` nằm ở đâu trong class file?

Theo **JVMS `4.7.3`**, mỗi method có thân bytecode (không phải `abstract` hoặc `native`) có `Code` attribute:

~~~text
Code_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 max_stack;
    u2 max_locals;
    u4 code_length;
    u1 code[code_length];
    u2 exception_table_length;
    ...
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Hai trường quan trọng:

- **`max_stack`**: độ sâu tối đa của **operand stack** tính theo slot tại **bất kỳ điểm nào** trong quá trình thực thi method.
- **`max_locals`**: số slot của **local variables array**, bao gồm cả receiver, các tham số và locals/tạm.

**Các con số này xác định theo code method**, không phải đo được chính xác số frame đang hoạt động trong lúc JVM chạy. Chẳng hạn `stack=2, locals=3` trong output `javap -v` là hai kích thước **bên trong một frame** cho method đang xem.

Giá trị `max_stack` có thể khác số lệnh trong method và khác số tham số. Một method dài hàng trăm instruction nhưng chỉ cần stack depth 2 vẫn hợp lệ; một lời gọi có nhiều đối số có thể cần depth lớn hơn.

Bộ kiểm tra bytecode của JVM sử dụng các ràng buộc kiểu và dữ liệu class file để đảm bảo việc thao tác stack/locals hợp lệ. `StackMapTable` hỗ trợ xác minh ở các điểm control flow, nhưng không phải snapshot runtime của tất cả lời gọi đang chạy.

### `Code` cho method abstract/native?

`abstract` method không có thân `Code` để JVM thực thi. `native` method có phần thân ở ngôn ngữ/bộ phận native thông qua cơ chế triển khai, không được mô tả bằng `Code` attribute của Java bytecode. Vì vậy cách giải thích “mỗi lời gọi tạo frame với `Code.max_stack/max_locals`” áp dụng trực tiếp cho **những Java bytecode methods có Code**, còn native method invocation liên quan thêm native method stacks/ABI và chi tiết runtime. Điều này không làm mất ý nghĩa của mô hình method invocation trong JVMS.

## 12. So sánh frame, heap, static state và method area

| Thành phần | Phạm vi | Dữ liệu điển hình | Ví dụ trong bài |
| --- | --- | --- | --- |
| **JVM stack** | Riêng từng thread | Những frame của các lời gọi đang hoạt động | `main → calculate → add` |
| **Frame local variables** | Riêng mỗi lần gọi | `this`, tham số, local values và references | `left=4, right=4, sum=8` |
| **Frame operand stack** | Riêng mỗi lần gọi | Giá trị tính toán, đối số, kết quả chờ dùng | `[4,4] → [8]` |
| **Heap** | Chia sẻ trong JVM theo mô hình | Object và array instances | `new IllegalStateException(...)` |
| **Run-time constant pool** | Gắn với class/interface, nằm trong vùng lưu dữ liệu runtime tương ứng | Symbolic references, constants, link info | `Methodref FrameTrace.add:(II)I` |
| **Static fields** | Gắn với class theo runtime identity | Trạng thái class, phụ thuộc class loader | `static int counter` nếu chương trình khai báo |
| **PC register** | Riêng mỗi thread | Vị trí instruction hiện hành khi chạy Java method | BCI đang thực thi trong `add` |

Sơ đồ object/reference:

~~~text
frame(main).local[1] = reference ──────────┐
                                           v
                                        Heap object
                                           ^
frame(otherMethod).local[0] = reference ────┘
~~~

Hai frame có thể trỏ đến **cùng một object**, vì vậy sửa object qua reference từ thread này có thể ảnh hưởng thread kia nếu phối hợp thread-safety không đúng. Nhưng hai frame không tự chia sẻ **mảng locals** hay **operand stack** chỉ vì chúng tham chiếu cùng object.

Khi một frame hết vòng đời, các local references của frame đó không còn là references sống từ frame ấy. Điều này **không chứng minh** object liên quan được GC thu ngay lập tức: object vẫn có thể được tham chiếu ở nơi khác, GC diễn ra theo chính sách runtime, và JIT/liveness có thể ảnh hưởng thời gian object thực sự được coi là reachable. Đừng suy “frame pop = heap object bị giải phóng ngay”.

## 13. Đọc StackTrace mà không đồng nhất nó với operand stack

Một stack trace Java thường thể hiện **chuỗi lời gọi method**:

~~~text
java.lang.IllegalStateException: boom
    at ExceptionalFrames.bottom(ExceptionalFrames.java:3)
    at ExceptionalFrames.middle(ExceptionalFrames.java:7)
    at ExceptionalFrames.top(ExceptionalFrames.java:12)
    at ExceptionalFrames.main(ExceptionalFrames.java:19)
~~~

Đây là **sơ đồ minh họa call chain**, **số dòng không cam kết** nếu bạn thêm/bớt dòng trong file. Chương trình `ExceptionalFrames` ở mục 10 bắt exception và **không tự in stack trace**; muốn xem stack trace bạn có thể gọi `ex.printStackTrace()` trong catch, khi đó output có thêm thông tin và thường đi tới stderr.

Stack trace hiển thị những **frames quan sát được của lời gọi**, không in toàn bộ operand stack hoặc giá trị từng local slot. Một dòng như `at ...middle(...java:7)` giúp định vị lời gọi nhưng không có nghĩa “operand stack ở dòng 7 chứa 7 phần tử”.

Các công cụ như debugger, JFR hoặc `jcmd Thread.print` có thể hỗ trợ phân tích thread/call stack trên runtime cụ thể. Chúng không thay thế bản đặc tả về locals, operand stack và constant-pool linking. Để nhìn cấp bytecode và slot, `javap -c -v -l -p` là lựa chọn rõ hơn.

## 14. Lỗi thường gặp và cách sửa cách hiểu

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “Mỗi Java method chỉ có một frame cho toàn bộ ứng dụng.” | **Mỗi lần gọi** method tạo frame trừu tượng; đệ quy có nhiều frame của cùng method. |
| “Một vòng lặp chạy 100 lần tức 100 frame.” | Không, vòng lặp trong cùng lần gọi thường tiếp tục trong **một frame**. |
| “JVM stack và operand stack là một.” | JVM stack chứa **frames**; mỗi frame chứa **operand stack** của riêng nó. |
| “Slot 0 luôn là `this`.” | Chỉ với instance method; static method dùng slot 0 cho tham số đầu nếu có. |
| “Một tham số = một local slot.” | `long`/`double` chiếm **hai** slot liên tiếp. |
| “`max_stack` là số method đang gọi lồng nhau.” | Đó là độ sâu **operand stack** của một method, không phải số frames. |
| “Callee dùng chính operand stack của caller.” | Callee bắt đầu với operand stack **riêng, rỗng**; arguments được chuyển vào locals callee. |
| “`ireturn` giữ lại frame callee để caller đọc local bên trong.” | Nó trả một **giá trị** về stack caller; frame callee hoàn tất. |
| “Exception cũng trả một giá trị qua `ireturn`.” | Exception không được xử lý trong callee gây **abrupt completion**, không return bình thường. |
| “Dynamic linking nghĩa mọi lời gọi đều quét toàn bộ constant pool.” | Resolution có thể lazy/cached; frame giữ **tham chiếu** tới run-time constant pool. |
| “Dynamic linking = dynamic dispatch = `invokedynamic`.” | Đây là các khái niệm liên quan nhưng **khác chức năng**. |
| “LocalVariableTable thiếu thì JVM không có locals.” | Runtime locals vẫn tồn tại; bảng debug chỉ chứa tên/phạm vi nếu compiler ghi. |
| “Frame biến mất thì mọi object từ frame bị xóa khỏi heap.” | Object có thể còn reachable qua references khác; GC không đồng nghĩa pop frame. |
| “JIT bắt buộc luôn cấp phát một native stack frame vật lý cho từng lời gọi.” | JVMS mô tả **frame trừu tượng**; triển khai có thể tối ưu hóa và inline. |

## 15. Bài tập tự kiểm tra

**Câu 1.** Trong `static int add(int x, int y)`, các tham số nằm ở slot nào?  
**Đáp án:** Thông thường `x` ở slot 0 và `y` ở slot 1; không có receiver `this`.

**Câu 2.** Trong `long instanceMethod(int a, long b, double c)`, local slot đầu của `b` và `c` là gì?  
**Đáp án:** `slot0=this`, `slot1=a`; `b` bắt đầu slot2 và chiếm slot2–3; `c` bắt đầu slot4 và chiếm slot4–5.

**Câu 3.** Nếu `main` gọi `calculate` và `calculate` gọi `add`, current frame khi đang tính `iadd` bên trong `add` là frame nào?  
**Đáp án:** `frame(add)`. Frames của `calculate` và `main` đang tạm ngừng chờ callee.

**Câu 4.** Sau `add(4,4)` kết thúc bằng `ireturn`, giá trị 8 xuất hiện ở đâu?  
**Đáp án:** Trên **operand stack của frame caller `calculate`**, rồi caller có thể lưu vào local `doubled`.

**Câu 5.** Vì sao `max_stack=4` không có nghĩa method có bốn frames?  
**Đáp án:** `max_stack` là độ sâu tối đa **theo slot của operand stack của một frame**.

**Câu 6.** `invokestatic #N` tham chiếu gì và có nhất thiết tìm lại symbol ở mỗi lần gọi không?  
**Đáp án:** `#N` là constant-pool index dẫn tới symbolic method reference; VM có thể resolve/cache theo luật, không cần tìm lại mỗi lần.

**Câu 7.** Hai lời gọi đệ quy `factorial(4)` và `factorial(3)` có chia sẻ local `n` không?  
**Đáp án:** Không. Mỗi invocation có frame/locals riêng với `n=4` hoặc `n=3`.

**Câu 8.** Nếu `bottom` ném exception mà không có handler, caller `middle` có nhận “kết quả method” gì không?  
**Đáp án:** Không. Lần gọi `bottom` kết thúc bất thường, exception tiếp tục tìm handler thay vì trả một giá trị qua `return`.

**Câu 9.** Vì sao thiếu `LocalVariableTable` không làm class file không chạy được?  
**Đáp án:** Vì đó là metadata debug tùy chọn; `Code.max_locals` cùng bytecode vẫn chỉ định đầy đủ slots cần cho thực thi.

**Câu 10.** Nêu ranh giới giữa method frame và object trên heap.  
**Đáp án:** Frame lưu locals/operand stack của **lần gọi**; reference trong frame có thể trỏ đến object trên heap. Hết frame không đồng nghĩa object bị thu hồi ngay.

## 16. Tài liệu chính thức và cách tự học tiếp

- [JVMS Java SE 25 — `2.5.2` Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.2): JVM stack riêng của từng thread, chứa frames.
- [JVMS Java SE 25 — `2.6` Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): mỗi lần invoke tạo frame, current frame, vòng đời và return.
- [JVMS Java SE 25 — `2.6.1` Local Variables](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.1): slot, receiver, tham số, `long`/`double`.
- [JVMS Java SE 25 — `2.6.2` Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.2): LIFO, loại giá trị, max depth và category.
- [JVMS Java SE 25 — `2.6.3` Dynamic Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.3): liên kết symbolic references qua run-time constant pool.
- [JVMS Java SE 25 — `2.6.4 và `2.6.5](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.4): hoàn tất bình thường, bất thường và vận chuyển kết quả/exception.
- [JVMS Java SE 25 — `4.7.3` Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, bytecode và exception table.
- [JVMS Java SE 25 — `5` Linking, Loading, and Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): resolution và invocation liên quan symbolic references.
- [JDK 25 `javap` manual](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): cách dùng `-c`, `-v`, `-l` để đối chiếu locals, operand stack và Code metadata.

**Cách ghi nhớ:** Một **thread** có **JVM stack**; một lần **invoke** có một **frame**; frame có **local variables**, **operand stack** và tham chiếu tới **run-time constant pool**; khi callee hoàn tất, caller tiếp tục với giá trị trả về hoặc theo đường exception. Từ mô hình này, bạn có thể đọc `javap` mà không nhầm local slots, operand-stack depth, constant-pool index và chuỗi lời gọi method.
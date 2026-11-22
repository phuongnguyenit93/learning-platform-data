# Code attribute, local variables, operand stack và các lệnh trả về

Bài này thuộc **Java Advance – instrumentation / Nền tảng class file**. Mục tiêu là đọc được bytecode của một phương thức và hiểu chính xác ba thứ thường bị nhầm: **vùng biến cục bộ (local variables)**, **ngăn xếp toán hạng (operand stack)** và **lệnh kết thúc phương thức (return instructions)**. Đây cũng là kiến thức cần có trước khi chèn, xóa hoặc thay đổi bytecode bằng một công cụ instrumentation.

## 1. Từ phương thức Java đến `Code` attribute

Một tệp `.class` gồm các cấu trúc như constant pool, khai báo trường và danh sách `method_info`. Với phương thức có thân Java thông thường, trong danh sách attributes của `method_info` có **đúng một `Code` attribute**. Phương thức `abstract` hoặc `native` không có `Code` attribute. Constructor `<init>` và class initializer `<clinit>` cũng chứa bytecode trong `Code` khi có thân thực thi.

```text
ClassFile
└── methods[]
    └── method_info (name + descriptor + access_flags + attributes[])
        └── Code
            ├── max_stack / max_locals
            ├── code[]                 ← các byte lệnh JVM
            ├── exception_table[]      ← vùng bảo vệ và exception handler
            └── attributes[]           ← metadata của Code
                ├── LineNumberTable
                ├── LocalVariableTable
                └── StackMapTable      (nếu được phát sinh/ghi)
```

Cấu trúc giản lược theo JVM Specification `4.7.3:

```text
Code_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 max_stack;
    u2 max_locals;
    u4 code_length;
    u1 code[code_length];
    u2 exception_table_length;
    { u2 start_pc; u2 end_pc; u2 handler_pc; u2 catch_type; }
        exception_table[exception_table_length];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

- `u1`, `u2`, `u4` lần lượt là số nguyên không dấu dài 1, 2, 4 byte trong định dạng class file. `attribute_name_index` tham chiếu chuỗi `Code` trong constant pool; `attribute_length` là số byte dữ liệu của attribute, **không** gồm 6 byte header của attribute.
- `max_stack` là độ sâu tối đa của operand stack, tính theo **đơn vị stack**; giá trị `long`/`double` (category 2) chiếm hai đơn vị, các giá trị category 1 chiếm một. Đây không phải số lệnh `push` và cũng không phải giới hạn của toàn JVM.
- `max_locals` là số **slot** biến cục bộ mà frame dành cho phương thức, bao gồm cả tham số và `this` khi có. Một `long`/`double` chiếm hai slot liên tiếp.
- `code_length` là số byte thực tế của `code[]`, bắt buộc từ 1 đến 65.535 byte. Những con số `0:`, `1:`, `2:` mà `javap` hiển thị là **bytecode offset** (vị trí tính theo byte), không mặc định là số thứ tự lệnh; có lệnh dài hơn một byte.
- `exception_table` mô tả các handler. Khoảng được bảo vệ là `[start_pc, end_pc)` (bao gồm đầu, loại trừ cuối), `handler_pc` là nơi bắt đầu handler, `catch_type` tham chiếu kiểu ngoại lệ; `catch_type = 0` có nghĩa handler bắt mọi ngoại lệ.
- `attributes[]` lồng trong `Code` chứa metadata bổ sung. `LineNumberTable` ánh xạ bytecode offset sang dòng nguồn; `LocalVariableTable` ghi tên/kiểu/phạm vi sống của biến cho debugger; `StackMapTable` cung cấp trạng thái kiểu dùng khi verifier kiểm tra các luồng điều khiển. Những metadata này **không phải** operand stack hoặc local variables đang chạy trong bộ nhớ. Một phương thức hợp lệ có thể không chứa `LocalVariableTable`.

**Phân biệt:** `Code` attribute là dữ liệu trong **class file**; khi JVM gọi phương thức, JVM tạo một **frame thời gian chạy** với local variable array và operand stack cho lần gọi đó. Cùng một `Code` có thể được thực thi bởi nhiều frame khác nhau, kể cả khi đệ quy hoặc chạy đồng thời.

## 2. Frame của JVM: local variables và operand stack

Có thể hình dung mỗi lần gọi phương thức như sau:

```text
                         FRAME của một lần gọi
   ┌──────────────────────────────┬──────────────────────────────┐
   │ Local variable array         │ Operand stack                │
   │ slot 0, slot 1, slot 2, ...  │  đáy → ... → đỉnh (LIFO)     │
   │ giữ tham số, this, biến tạm  │  giữ toán hạng/kết quả trung gian │
   └──────────────────────────────┴──────────────────────────────┘
          ↑ iload/istore/...              ↑ iconst, iadd, invoke, ...
```

### 2.1. Local variables: địa chỉ bằng chỉ số slot

- Với **instance method**, slot `0` chứa reference `this` lúc vào phương thức; tham số tường minh bắt đầu ở slot `1`. Với **static method**, không có `this`, tham số đầu bắt đầu ở slot `0`.
- `int`, `float` và reference chiếm một slot; `long`, `double` chiếm hai slot. Các giá trị `boolean`, `byte`, `char`, `short` được biểu diễn bằng kiểu `int` khi xử lý bằng những lệnh số nguyên tương ứng.
- `iload_0`, `iload_1` hoặc `iload n` **đọc** slot số nguyên và **đẩy** giá trị lên operand stack; `istore_2` hay `istore n` **lấy** giá trị ở đỉnh stack rồi **ghi** vào slot. Các họ `aload/astore` dùng cho reference, `lload/lstore` cho `long`, `dload/dstore` cho `double`, `fload/fstore` cho `float`.
- `iinc index, const` thay đổi trực tiếp một biến `int` trong local variable array mà không cần đặt toán hạng lên stack. `wide` mở rộng chỉ số/độ rộng toán hạng cho một số lệnh truy cập local khi chỉ số lớn.
- Slot có thể được **tái sử dụng** bởi các biến có phạm vi sống không trùng nhau. Số slot trong `max_locals` không nhất thiết bằng số tên biến trong mã nguồn; tên biến còn có thể vắng mặt do thiếu debug metadata. Đọc slot chưa được khởi tạo theo luồng điều khiển không được verifier chấp nhận.

Ví dụ phương thức `public long echo(long value)` của một đối tượng: slot `0` chứa `this`, giá trị tham số `value` dùng slot `1` và `2`; do đó `max_locals` phải đủ **ít nhất 3**. Lệnh `lload_1` nạp một giá trị `long` từ hai slot, rồi `lreturn` trả giá trị đó về phương thức gọi. Với `static long echo(long value)`, tham số sẽ bắt đầu ở slot `0` và dùng slots `0–1`.

### 2.2. Operand stack: tính toán theo LIFO

Operand stack không chứa tên biến; các lệnh tiêu thụ và tạo **giá trị** theo quy tắc ngăn xếp last-in-first-out. Ví dụ:

```text
iconst_2    []       -> [2]
iconst_3    [2]      -> [2, 3]
iadd        [2, 3]   -> [5]
istore_0    [5]      -> []        (ghi 5 vào local slot 0)
iload_0     []       -> [5]
ireturn     [5]      -> kết thúc frame, chuyển 5 cho caller
```

Trong ký hiệu `[2, 3]`, **bên phải là đỉnh stack**. `iadd` lấy hai giá trị `int` (lấy `3` trước, rồi `2`), cộng và đẩy một `int` mới. `istore_0` lấy giá trị khỏi stack; `iload_0` tạo giá trị stack từ slot. Một lời gọi `invoke*` lấy đối tượng nhận (nếu cần) và đối số theo descriptor, rồi đặt giá trị trả về lên stack của caller **nếu** kết quả khác `void`.

Một số thao tác stack hữu ích khi đọc hoặc instrument bytecode: `dup` sao chép một giá trị category 1 ở đỉnh, `dup2` sao chép một giá trị category 2 hoặc hai giá trị category 1 phù hợp, `pop` bỏ một giá trị category 1, `pop2` bỏ một giá trị category 2 hoặc hai giá trị category 1. Không được dùng `dup`/`pop` như thể `long` và `double` chỉ chiếm một đơn vị. `swap` chỉ hợp lệ với hai giá trị category 1.

**Điểm mấu chốt:** local array lưu dữ liệu để có thể đọc theo chỉ số, còn operand stack là nơi nhiều phép tính và lệnh gọi nhận/nhả toán hạng. `max_stack` và `max_locals` cùng nằm trong `Code` nhưng kiểm soát **hai tài nguyên khác nhau**.

## 3. Thực nghiệm Java 17+: theo dõi từng bytecode

Lưu đúng tệp **`FrameDemo.java`** sau. Đây là chương trình đầy đủ có thể biên dịch và chạy:

```java
public final class FrameDemo {
    public static int sumPlusOne(int a, int b) {
        int sum = a + b;
        return sum + 1;
    }

    public long echo(long value) {
        return value;
    }

    public static void main(String[] args) {
        System.out.println(sumPlusOne(3, 4));
        System.out.println(new FrameDemo().echo(12L));
    }
}
```

Trong thư mục chứa tệp, dùng JDK 17 hoặc mới hơn:

```bash
javac -g FrameDemo.java
java FrameDemo
javap -c -l -p FrameDemo
javap -v -p FrameDemo
```

Hai dòng stdout từ lệnh `java FrameDemo` là:

```text
8
12
```

`javap -c` giải mã lệnh bytecode; `-l` hiện bảng dòng nguồn và biến cục bộ **nếu có**; `-p` hiện cả thành viên không public; `-v` hiện thông tin chi tiết, gồm header `Code` với `stack`, `locals`, `args_size`, constant pool và attributes. `javac -g` yêu cầu phát sinh debug info (ví dụ `LocalVariableTable`). Những phần như constant-pool index, số dòng nguồn và bố cục bổ sung có thể khác theo compiler/JDK, nên xem các dòng dưới là **trích đoạn mô tả lệnh chính của phương thức `sumPlusOne`**, không phải toàn bộ output của `javap`:

```text
public static int sumPlusOne(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: iconst_1
     6: iadd
     7: ireturn
```

Phương thức này cần `max_locals = 3` (hai tham số `a`, `b` và biến `sum`), `max_stack = 2` (tại `iadd`, stack có hai số nguyên). Với descriptor `(II)I`, hai `I` trong ngoặc là hai tham số `int` và `I` cuối là kiểu trả về `int`.

Theo vết khi `a = 3`, `b = 4`:

| Offset | Lệnh | Local slots sau lệnh (a, b, sum) | Operand stack sau lệnh |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `(3, 4, —)` | `[3]` |
| 1 | `iload_1` | `(3, 4, —)` | `[3, 4]` |
| 2 | `iadd` | `(3, 4, —)` | `[7]` |
| 3 | `istore_2` | `(3, 4, 7)` | `[]` |
| 4 | `iload_2` | `(3, 4, 7)` | `[7]` |
| 5 | `iconst_1` | `(3, 4, 7)` | `[7, 1]` |
| 6 | `iadd` | `(3, 4, 7)` | `[8]` |
| 7 | `ireturn` | frame kết thúc | trả `8` về caller |

Dấu `—` nghĩa là biến `sum` chưa được khởi tạo. Bảng mô tả trạng thái logic của frame, không khẳng định JVM bắt buộc cài đặt từng slot/stack bằng một vùng bộ nhớ vật lý riêng; JIT có thể tối ưu cách thực thi.

Với `echo(long value)`, kết quả thường có chuỗi `lload_1` → `lreturn`. Chú ý `lload_1` đọc giá trị category 2 và `lreturn` trả lại một `long`; chúng không phải hai lần đọc/trả một `int`.

## 4. Sáu lệnh `return` theo kiểu dữ liệu

Trong bytecode, một lệnh trả về phải tương thích với **descriptor của phương thức**. `return` trong Java source có thể sinh một trong sáu opcode sau:

| Opcode | Kiểu giá trị trên đỉnh operand stack | Kiểu trả về của phương thức | Tác động |
| --- | --- | --- | --- |
| `ireturn` | `int` (category 1) | `int`, `boolean`, `byte`, `char`, `short` | Lấy một giá trị kiểu int và trả về |
| `lreturn` | `long` (category 2) | `long` | Trả về long |
| `freturn` | `float` (category 1) | `float` | Trả về float |
| `dreturn` | `double` (category 2) | `double` | Trả về double |
| `areturn` | reference (category 1) | object, interface hoặc array reference | Trả về reference, kể cả `null` hợp lệ |
| `return` | không yêu cầu giá trị trả về | `void`, constructor/class initializer | Kết thúc bình thường, không chuyển kết quả |

Với các lệnh trả về có giá trị, JVM lấy kết quả từ **operand stack của callee**, kết thúc frame đó và đặt kết quả vào operand stack của caller (khi caller tồn tại). Nó không trực tiếp đọc biến Java theo tên: ví dụ `return sum;` thường cần `iload_2` rồi `ireturn`. Sau `return` bình thường, dòng lệnh tiếp theo trong cùng frame không được thực thi.

`athrow` **không phải** một trong sáu lệnh trả về: nó ném một reference ngoại lệ, chuyển điều khiển tới handler phù hợp hoặc làm unwinding qua các frame. `ret` trong bytecode lịch sử (đi với `jsr`/`jsr_w`) cũng **không** phải lệnh trả kết quả phương thức; không dùng nó để thay cho `ireturn` hay `return`.

### Chương trình quan sát đủ sáu kiểu

Lưu vào **`ReturnDemo.java`**:

```java
public class ReturnDemo {
    static int intValue(int x) { return x + 1; }
    static long longValue(long x) { return x * 2; }
    static float floatValue(float x) { return x / 2; }
    static double doubleValue(double x) { return x + 0.5; }
    static String referenceValue() { return "OK"; }
    static void voidValue() { System.out.println("done"); }

    public static void main(String[] args) {
        System.out.println(intValue(7));
        System.out.println(longValue(10L));
        System.out.println(floatValue(4.0f));
        System.out.println(doubleValue(2.0));
        System.out.println(referenceValue());
        voidValue();
    }
}
```

```bash
javac ReturnDemo.java
java ReturnDemo
javap -c -p ReturnDemo
```

Stdout của `java ReturnDemo`:

```text
8
20
2.0
2.5
OK
done
```

Quan sát cuối `intValue` là `ireturn`, `longValue` là `lreturn`, `floatValue` là `freturn`, `doubleValue` là `dreturn`, `referenceValue` là `areturn`, còn `voidValue` kết thúc bằng `return`. Phương thức `main` là `void` nên cũng kết thúc bình thường bằng `return`. Dù source dùng chung từ khóa `return`, JVM dùng opcode phụ thuộc kiểu.

## 5. Điều khiển luồng, exception handlers và kiểm tra kiểu

Tại một điểm rẽ nhánh, vòng lặp, lời gọi phương thức hay exception handler, ta không thể đoán stack chỉ từ dòng source hiện tại:

1. Các đường đi hợp lệ hội tụ tại cùng bytecode offset phải có trạng thái local variables và operand stack **tương thích theo luật xác minh kiểu**. JVM verifier kiểm tra bytecode, bao gồm descriptor, kiểu operand, khả năng truy cập local và sự nhất quán của frame; dữ liệu `StackMapTable` trợ giúp kiểm tra này.
2. Nếu một handler nhận quyền điều khiển do ngoại lệ, operand stack của frame tại đầu handler có **một exception reference** tương ứng, thay vì giữ nguyên các giá trị đang dang dở trên stack tại lệnh gây lỗi. Bytecode handler thường lưu exception bằng `astore` trước khi xử lý.
3. Các offset trong nhánh (`if*`, `goto`, `tableswitch`, `lookupswitch`) và `exception_table` phụ thuộc bố cục bytecode. Thêm byte mới làm thay đổi vị trí và có thể đòi hỏi cập nhật offset/range và các attributes liên quan.
4. `LineNumberTable` và `LocalVariableTable` phục vụ debug, có thể khác nhau hoặc vắng mặt giữa các lần biên dịch mà chương trình vẫn chạy đúng. `StackMapTable` thuộc bài toán verification; nó không phải bảng tên biến cho debugger và không đồng nghĩa với `max_stack`.

Ví dụ `try/catch` có thể phát sinh thêm handler entry trong `exception_table`; `finally` hoặc try-with-resources có thể tạo bytecode sao chép đường kết thúc và xử lý ngoại lệ. **Không nên** suy ra rằng một `return` trong source luôn tương ứng đúng một lệnh `return` trong class file.

## 6. Vì sao kiến thức này quan trọng khi instrumentation?

Giả sử muốn ghi nhận giá trị trả về của phương thức `int` trước khi nó kết thúc. Ở ngay trước `ireturn`, kết quả đã nằm trên operand stack. Nếu gọi logger trực tiếp, logger có thể **tiêu thụ** kết quả, khiến `ireturn` không còn toán hạng cần lấy. Về mặt **minh họa bytecode** (không phải chương trình Java độc lập), mô hình đúng với một phương thức logger `Trace.logInt(int) : void` có thể là:

```text
...                                 ; stack = [result:int]
dup                                 ; stack = [result:int, result:int]
invokestatic Trace.logInt:(I)V     ; stack = [result:int]
ireturn                             ; trả result về caller
```

Điểm cần kiểm tra khi chèn lệnh:

- **Đúng opcode:** `ireturn`/`freturn`/`areturn` dùng category 1, còn `lreturn`/`dreturn` dùng category 2. Với một giá trị category 2, thao tác copy phù hợp có thể là `dup2`. Với `return` kiểu `void`, **không có** giá trị để `dup`; nếu ghi nhận thoát bất thường phải xét riêng đường `athrow`/handler.
- **Đúng descriptor và stack effect:** Lệnh gọi `invokestatic` ở ví dụ phải tiêu thụ một `int` và có kết quả `void`; một descriptor khác làm thay đổi operand stack hoặc gây lỗi xác minh kiểu. Cần xử lý đúng đường có nhiều `return`.
- **Đúng frame metadata:** Có thể phải tăng `max_stack`, tính lại stack map frames, cập nhật các bytecode branch targets, exception handler ranges, offsets của debug attributes và những cấu trúc phụ thuộc code. `max_locals` cần tăng nếu tạo thêm slot tạm.
- **Đúng ngữ nghĩa chương trình:** Lời gọi logger có thể ném ngoại lệ, tạo side effect, gây đệ quy instrumentation hoặc thay đổi thời gian/khóa đồng bộ. Cần có chủ đích rõ về cách xử lý các trường hợp này, không chỉ cố làm class qua verifier.
- **Dùng thư viện bytecode phù hợp:** Với ASM chẳng hạn, có cơ chế hỗ trợ tính lại maxs/frames trong tình huống phù hợp, nhưng vẫn phải hiểu class hierarchy, loader, điểm chèn và descriptor. Sửa mảng byte bằng phép cộng offset thủ công rất dễ làm class không hợp lệ.

**Nguyên tắc kiểm tra:** Với mỗi điểm chèn, hãy viết trạng thái operand stack *trước* và *sau* từng lệnh; đảm bảo lệnh trả về cuối vẫn nhận đúng giá trị, các đường nhánh/handler hợp lệ và verifier chấp nhận class đã biến đổi.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `max_stack` là số lượng biến cục bộ | Nó giới hạn độ sâu operand stack; `max_locals` mới là số slot locals. |
| `long`/`double` chiếm một slot như `int` | Chúng chiếm hai slot locals và hai đơn vị độ sâu operand stack. |
| Slot 0 luôn là `this` | Chỉ đúng khi vào instance method; static method bắt đầu bằng tham số đầu ở slot 0. |
| `javap` in offset 7 nghĩa là lệnh thứ 8 | Offset là số byte kể từ đầu `code[]`; độ dài lệnh thay đổi. |
| Tên biến bắt buộc có trong class file | Tên local thường ở `LocalVariableTable` tùy chọn; bytecode làm việc với index. |
| `return` luôn là opcode `return` | Giá trị trả về dùng `ireturn`, `lreturn`, `freturn`, `dreturn` hoặc `areturn`. |
| Có thể gọi logger rồi `ireturn` mà không để lại giá trị | `ireturn` phải lấy được một `int` trên operand stack; nhiều khi cần `dup` trước lệnh gọi. |
| Bytecode kết thúc chỉ có `return` hoặc `ireturn` | Còn các kiểu trả về khác và đường kết thúc bất thường bằng exception. |
| `StackMapTable` là hình ảnh runtime stack | Nó là metadata về trạng thái kiểu cho việc kiểm tra bytecode. |
| Tăng `max_stack` là đủ để mọi đoạn code chèn chạy được | Còn phải giữ kiểu, điều khiển luồng, handler, frames và các attribute liên quan nhất quán. |

## 8. Tự kiểm tra

1. Với `static long add(long x, int y) { return x + y; }`, khi vào phương thức, các tham số dùng ít nhất mấy slot locals? Lệnh trả về thuộc họ nào? **Đáp án:** `x` dùng slots `0–1`, `y` dùng slot `2`, nên ít nhất **3 slots**; kết quả `long` trả bằng `lreturn` (compiler phải mở rộng `y` từ `int` sang `long` khi cộng).
2. Trong `sumPlusOne`, vì sao `max_stack = 2` trong khi phương thức có ba biến `a`, `b`, `sum`? **Đáp án:** ba biến ở local array; operand stack chỉ cần giữ tối đa hai giá trị `int` tại một thời điểm.
3. Phương thức trả `String[]` sử dụng opcode gì? **Đáp án:** `areturn`, vì mảng cũng là reference.
4. Chèn một lời gọi `void` ngay trước `lreturn`, sau khi logger tiêu thụ giá trị `long`, có thể tiếp tục `lreturn` không? **Đáp án:** không; phải bảo toàn/đưa lại giá trị category 2 lên operand stack và xác minh stack effect.
5. Không thấy tên `sum` trong output của `javap -c` thì biến `sum` có nhất thiết biến mất khỏi bytecode không? **Đáp án:** không; slot `2` vẫn được dùng qua `istore_2`/`iload_2`; tên hiển thị phụ thuộc debug metadata như `LocalVariableTable`.

## Tài liệu gốc để đối chiếu

- Java Virtual Machine Specification, **`2.6 Frames**: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6
- Java Virtual Machine Specification, **`4.7.3 Code Attribute; `4.7.4 StackMapTable; `4.7.13 LocalVariableTable**: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3
- Java Virtual Machine Specification, **`6.5 Instructions** (nhóm `*load`, `*store`, `iadd`, `ireturn`, `lreturn`, `return`, `athrow`): https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html

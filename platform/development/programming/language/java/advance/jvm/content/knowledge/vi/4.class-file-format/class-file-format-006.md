# Thuộc tính Code trong tệp class: `max_stack`, `max_locals`, bytecode và bảng xử lý ngoại lệ

Một phương thức Java đã biên dịch thường không còn lưu source code trong tệp `.class`. Thay vào đó, phương thức có một **`Code` attribute** mô tả mã lệnh JVM, số slot tối đa của operand stack, số slot biến cục bộ cần cấp cho frame, các vùng bắt ngoại lệ và một số metadata phụ trợ. Đọc đúng cấu trúc này giúp giải thích vì sao một lời gọi Java hoạt động, vì sao cast/branch/`try-catch` xuất hiện thành nhiều bytecode instructions, và vì sao một tệp `.class` có thể bị từ chối khi verification.

Bài này dùng **Java SE 17 (class-file major version 61)** làm mốc. Các quy tắc cấu trúc lấy từ Java Virtual Machine Specification (JVMS), chủ yếu `4.7.3, `2.6, `4.10, `6.5. Các bản JDK khác có thể tạo chuỗi bytecode khác nhau mà vẫn đúng ngữ nghĩa; đừng mặc định ảnh chụp từ `javap` là cấu trúc duy nhất một compiler được phép tạo.

## 1. Thuộc tính `Code` nằm ở đâu?

Một tệp `.class` gồm phần đầu, constant pool, thông tin class, fields, methods và attributes. Trong bảng `methods[]`, mỗi `method_info` có một bảng `attributes[]`. Với phương thức có phần thân mà JVM thực thi, một phần tử của bảng ấy là **`Code`**.

```text
ClassFile
├── magic, minor_version, major_version
├── constant_pool
├── access_flags, this_class, super_class, interfaces
├── fields[]
├── methods[]
│   └── method_info của một phương thức cụ thể
│       ├── access_flags, name_index, descriptor_index
│       └── attributes[]
│           └── Code_attribute
│               ├── max_stack
│               ├── max_locals
│               ├── code_length + code[] (bytecode)
│               ├── exception_table[]
│               └── attributes[] của chính Code
└── attributes[] của class
```

Điểm cần phân biệt:

- **`method_info`** mô tả một phương thức bằng tên, descriptor (kiểu tham số/kiểu trả về theo định dạng JVM), flags và attributes.
- **`Code_attribute`** mô tả code và thông tin hỗ trợ thực thi **cho một phương thức**, không phải cho toàn class, một lời gọi riêng lẻ hay toàn bộ JVM.
- **Một lần gọi phương thức** có một JVM frame riêng với operand stack và local variables; mỗi frame dùng giới hạn từ `max_stack` và `max_locals` của method tương ứng. Nhiều lời gọi đệ quy cùng một method tạo nhiều frame, cùng khuôn metadata nhưng giá trị locals khác nhau.
- Phương thức **`abstract` hoặc `native`** không có `Code` attribute trong `method_info`. Phương thức bình thường có code phải có **đúng một** `Code` attribute theo quy tắc class file.
- Constructor là method `<init>`; class/interface initializer là `<clinit>` nếu compiler phát sinh. Chúng cũng có thể chứa `Code`. Một method `default` của interface có thân cũng thuộc nhóm có code.
- `Code` không đồng nghĩa `SourceFile` hoặc `SourceDebugExtension`: các metadata ấy có vai trò khác.

Nếu class có mười method có body, thông thường bạn sẽ thấy nhiều mục `Code:`, mỗi mục gắn với một method. Đọc một mục không thể áp dụng `max_stack` hay `exception_table` của nó cho method khác.

## 2. Cấu trúc nhị phân chuẩn của `Code_attribute`

JVMS `4.7.3` định nghĩa cấu trúc sau. Đây là **pseudocode đặc tả định dạng class file**, không phải chương trình Java độc lập:

```text
Code_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 max_stack;
    u2 max_locals;
    u4 code_length;
    u1 code[code_length];
    u2 exception_table_length;
    {
        u2 start_pc;
        u2 end_pc;
        u2 handler_pc;
        u2 catch_type;
    } exception_table[exception_table_length];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

`u1`, `u2`, `u4` lần lượt là **số nguyên không dấu** mã hóa trên 1, 2, 4 byte trong class file; các giá trị nhiều byte trong định dạng class file dùng thứ tự byte big-endian.

| Trường | Kích thước/ý nghĩa | Cách đọc |
| --- | --- | --- |
| `attribute_name_index` | `u2`, chỉ số constant pool | Trỏ tới `CONSTANT_Utf8_info` có giá trị `Code` |
| `attribute_length` | `u4` | Số byte của nội dung attribute, **không tính 6 byte đầu** dành cho name index và length |
| `max_stack` | `u2` | Độ sâu operand stack **tối đa** mà method cần, tính theo đơn vị slot |
| `max_locals` | `u2` | Số slot trong local-variable array của mỗi frame method |
| `code_length` | `u4` | Số **byte** trong mảng mã lệnh, không phải số lệnh và không phải số dòng Java |
| `code[]` | `u1[code_length]` | Opcode cùng byte operand, branch offsets, dữ liệu switch, v.v. |
| `exception_table_length` | `u2` | Số entry xử lý ngoại lệ |
| `exception_table[]` | Mỗi entry gồm 4 trường `u2` | Dải bytecode được bảo vệ, đích handler và kiểu exception |
| `attributes_count` | `u2` | Số attribute **lồng trong Code**, ví dụ `StackMapTable` hoặc `LineNumberTable` |
| `attributes[]` | Độ dài thay đổi | Metadata verification và debug gắn với mã của method |

Giới hạn quan trọng: `code_length` **lớn hơn 0 và nhỏ hơn 65536**, nghĩa là một `Code` chỉ chứa tối đa **65535 byte** bytecode. Một lệnh nhiều byte vẫn tính theo từng byte. `javap -c` cho thấy **bytecode offset**, không cho số thứ tự của lệnh theo hàng source.

Đừng nhầm tên `Code` attribute với constant pool entry chứa literal chuỗi `Code`: `attribute_name_index` chỉ **định danh loại attribute**; mã thực nằm trong `code[]`.

## 3. `max_stack`: số slot tối đa của operand stack trong một frame

Mỗi JVM frame có **operand stack** riêng. Bytecode thường đưa giá trị lên stack bằng `iload`/`lload`/`iconst_*`, lấy toán hạng ra bằng phép cộng hoặc phép gọi, rồi đẩy kết quả lên. `max_stack` cho biết độ sâu **tối đa tính theo đơn vị stack slot** cần cho method này.

Ví dụ phép cộng hai `int` trong một method:

```text
Trạng thái operand stack (đáy → đỉnh):
ban đầu             []
iload_0             [a]        // 1 slot
iload_1             [a, b]     // 2 slot
iadd                [a+b]      // 1 slot
ireturn             []         // trả giá trị về caller
```

Độ sâu tối đa của đoạn này là **2 slot**, nên một method chỉ thực hiện chuỗi ấy có thể có `max_stack = 2`. `max_stack` **không** phải số opcode, số lượng biến Java, số byte của tệp class, dung lượng RAM dành cho mọi stack của tiến trình, hoặc giá trị thực tế tại mọi thời điểm.

### Giá trị loại category 1 và category 2

Trong mô hình JVMS:

- `int`, `float`, reference và các giá trị tính toán thuộc **category 1** chiếm **1 slot** của operand stack.
- `long` và `double` thuộc **category 2** chiếm **2 slot**.
- Các giá trị Java `byte`, `short`, `char` thường được biểu diễn/tính bằng `int` trên operand stack; không có tập opcode cộng `byte` hoàn toàn độc lập.

Ví dụ method `sumLong(long a, long b)` có thể có dãy:

```text
lload_0             [a(long)]              // 2 slot
lload_2             [a(long), b(long)]     // 4 slot
ladd                [a+b(long)]           // 2 slot
lreturn             []                    // kết thúc frame
```

Vì cần cùng lúc hai `long`, độ sâu tối đa ở đây là **4 slot**. Đếm “có hai số nên max_stack bằng 2” là sai. Một giá trị `long` vẫn là **một giá trị logic**, nhưng đóng góp **hai đơn vị** vào độ sâu stack.

### `max_stack` là mức tối đa tĩnh, không phải stack trace runtime

- Nó là metadata của **method** do compiler/class-file generator điền để phục vụ tổ chức thực thi và kiểm chứng hợp lệ.
- `max_stack = 4` không hứa luôn luôn có bốn slot dữ liệu trên stack; một số nhánh có thể dùng ít hơn.
- Không được lấy `max_stack` để suy ra độ sâu **call stack**, số lần đệ quy có thể thực hiện hay giá trị `-Xss`. Mỗi lần gọi method lại tạo frame riêng.
- Nếu bytecode cố đẩy nhiều slot hơn mức đã khai báo trên một đường thực thi hợp lệ, class file không thỏa yêu cầu verification; JVM có thể từ chối bằng `VerifyError` hoặc lỗi định dạng/liên kết thích hợp tùy vi phạm.

## 4. `max_locals`: số slot dành cho tham số và biến cục bộ

Mỗi frame chứa mảng **local variables** được đánh chỉ số `0, 1, 2, ...`. `max_locals` xác định tổng số **slot** cấp cho mảng này. Nó bao gồm slot cho tham số truyền vào method và các biến tạm do compiler sinh ra khi cần.

Bảng quy tắc:

| Tình huống | Vị trí local variables |
| --- | --- |
| Method instance | Slot `0` thường chứa `this`, sau đó là tham số |
| Method `static` | Không có `this` ẩn; tham số đầu tiên bắt đầu ở slot `0` |
| Tham số `int`/`float`/reference | Chiếm một slot |
| Tham số `long`/`double` | Chiếm **hai slot liên tiếp** |
| Biến trong các scope không giao nhau | Compiler có thể tái sử dụng một slot |
| Exception local ở `catch` | Compiler thường dùng thêm slot để chứa `Throwable` được handler nhận |

Với method `public static long sumLong(long left, long right)`, `left` chiếm slot **0–1**, `right` chiếm slot **2–3**; method chỉ cần hai tham số này nên có thể có **`max_locals = 4`**.

Với method `public int increment(int value)`, slot **0** chứa `this`, slot **1** chứa `value`; có thể có **`max_locals = 2`**.

Một method `static void run()` không nhận tham số và không dùng biến cục bộ có thể có `max_locals = 0`. Đừng cho rằng mọi method đều có `this`.

### Hai lưu ý về index và tên biến

1. Chỉ số local variable là **slot trong frame**, không phải số thứ tự khai báo trong source. Tham số `double` hoặc `long` tạo khoảng cách hai slot; compiler còn có thể thêm slot cho giá trị trung gian hoặc exception.
2. `max_locals` không lưu tên biến `left` hay `right`. Tên biến/ranh giới scope có thể xuất hiện trong attribute tùy chọn `LocalVariableTable` khi biên dịch với debug info, nhưng khi không có bảng đó, JVM vẫn hiểu và thực thi bytecode qua **index** và **kiểu**.

Trong `javap`, trường `locals=4` là thông tin từ `max_locals`; phần `LocalVariableTable` (nếu xuất hiện) cho biết một số tên biến và khoảng sống gắn với các slot, **không phải** kích thước thay thế cho `max_locals`.

## 5. `code_length` và `code[]`: nơi đặt bytecode thực sự

`code[]` là dãy **byte** của các JVM instructions. Một số opcode không có operand; một số opcode đọc thêm một hoặc nhiều byte. Lệnh có độ dài biến thiên như `tableswitch` và `lookupswitch` còn có yêu cầu căn chỉnh và các phần dữ liệu bổ sung. Vì thế:

- `code_length` đo **số byte**; từ độ dài không suy ra ngay số instruction.
- **Bytecode index/offset (BCI)** của `javap -c` là **vị trí byte bắt đầu opcode** trong `code[]`. Nó không phải số dòng Java.
- `goto`/`if_*`/`tableswitch` nhảy đến bytecode index hợp lệ; mục tiêu nhảy cần rơi vào **đầu một instruction**, không được nhảy vào giữa phần operand của lệnh.
- `ireturn`, `lreturn`, `areturn`, `return` kết thúc bình thường phần thực thi method tương ứng với kiểu kết quả.
- `athrow` ném reference kiểu `Throwable`, có thể làm JVM tìm exception handler trong cùng method hoặc các frame gọi bên ngoài.

Ví dụ đọc output:

```text
  0: iload_0
  1: iload_1
  2: idiv
  3: ireturn
  4: astore_2
  5: iconst_m1
  6: ireturn
```

Các số `0, 1, 2, 3, 4, 5, 6` ở đây là **offset theo byte**. Chúng liên tục vì từng opcode trong ví dụ chiếm đúng một byte; trong method khác, bytecode index có thể tăng 2, 3 hoặc nhiều hơn giữa hai instruction được in.

### Bytecode thường gặp trong nội dung bài

| Nhóm | Ví dụ opcode | Vai trò |
| --- | --- | --- |
| Nạp local lên stack | `iload_0`, `iload_1`, `lload_0`, `aload_0` | Đọc slot local với loại phù hợp |
| Ghi stack xuống local | `istore`, `astore_2`, `lstore` | Lưu giá trị vào slot local |
| Hằng đơn giản | `iconst_m1`, `iconst_1`, `bipush` | Đẩy giá trị số nguyên |
| Tính toán | `iadd`, `idiv`, `ladd` | Lấy operands từ stack, trả kết quả lên stack |
| Chuyển kiểu | `i2l`, `l2i`, `i2b` | Thay cách biểu diễn/độ rộng theo ngữ nghĩa JVM |
| Điều khiển | `ifeq`, `if_icmpge`, `goto` | Thay BCI thực thi |
| Gọi/return | `invokestatic`, `invokevirtual`, `ireturn`, `lreturn` | Tương tác giữa các frame |
| Exception | `athrow` | Ném exception, có thể đi tới handler |

Trường `code[]` chứa tất cả opcode và các operand bytes tương ứng, chứ không lưu tên ký hiệu `iload_0` dưới dạng text. `javap` là công cụ **disassembler** chuyển mã nhị phân thành mnemonic đọc được.

## 6. `exception_table[]`: xác định handler cho các vùng bytecode

Một entry trong exception table gồm bốn trường:

```text
start_pc  end_pc  handler_pc  catch_type
```

| Trường | Ý nghĩa |
| --- | --- |
| `start_pc` | BCI bắt đầu **bao gồm** trong vùng code được bảo vệ |
| `end_pc` | BCI kết thúc **không bao gồm**; có thể bằng `code_length` |
| `handler_pc` | BCI của instruction đầu tiên trong handler |
| `catch_type` | Index của `CONSTANT_Class_info` mô tả kiểu exception được bắt, hoặc `0` nếu handler bắt tất cả |

Một handler áp dụng khi exception xảy ra ở instruction có offset `pc` thỏa **`start_pc <= pc < end_pc`**. `start_pc` phải là offset instruction hợp lệ; `end_pc` phải là offset instruction hợp lệ hoặc bằng `code_length`, đồng thời `start_pc < end_pc`. `handler_pc` phải chỉ tới đầu instruction hợp lệ trong `code[]`.

Quan trọng: **`end_pc` là exclusive**. Nếu bảng ghi `from 0 to 3 target 4`, những instruction bắt đầu ở BCI `0, 1, 2` thuộc vùng được bảo vệ; instruction ở BCI `3` không thuộc vùng đó.

### JVM làm gì khi có exception?

1. Khi một instruction ném exception (ví dụ `idiv` chia cho 0) hoặc khi code thực hiện `athrow`, JVM xác định method và instruction nơi exception được ném.
2. JVM xét các entry **theo thứ tự trong `exception_table[]`**, tìm entry có BCI nằm trong vùng bảo vệ và kiểu exception phù hợp.
3. Nếu tìm thấy handler, luồng điều khiển chuyển đến `handler_pc`. **Operand stack của frame được dọn** và chỉ còn exception object ở đỉnh để handler xử lý, thường bắt đầu bằng `astore` đưa exception vào local variable.
4. Nếu không có handler phù hợp ở method hiện tại, exception lan ra caller; quá trình tìm handler tiếp tục trong các frame ngoài, với hiệu ứng unwinding thích hợp. Exception không được xử lý có thể kết thúc thread theo cơ chế xử lý uncaught exception.

Tại một entry có `catch_type != 0`, JVM kiểm tra loại của exception có tương thích với lớp chỉ ra bởi constant pool hay không. Nếu `catch_type == 0`, handler áp dụng cho mọi exception (catch-all). Compiler dùng catch-all trong những cơ chế xử lý tương tự `finally` hoặc code cleanup; đừng suy ra mọi handler catch-all đều được người lập trình viết bằng cú pháp `catch (Throwable ...)`.

### Vì sao thứ tự handler quan trọng?

Các vùng `try` và các kiểu catch có thể chồng lấn hoặc cùng áp dụng; **entry phù hợp đầu tiên** trong table quyết định handler. Java compiler tạo thứ tự phù hợp với các quy tắc source; các công cụ sửa class file không được tùy tiện đảo thứ tự vì có thể thay đổi ngữ nghĩa.

Đừng nhầm **exception table** của `Code` với:

- **`Exceptions` attribute** tại cấp `method_info`: mô tả những **checked exception types được khai báo** trong `throws`, không phải danh sách handler cho `try/catch`.
- **`LineNumberTable`**: ánh xạ BCI sang số dòng source, không xử lý ngoại lệ.
- **`StackMapTable`**: hỗ trợ verifier kiểm tra các loại giá trị trên stack/locals ở những điểm trong control flow; không thay thế exception handler table.
- **Exception stack trace** được in ra runtime: mô tả chuỗi lời gọi khi lỗi xảy ra, không phải bảng `exception_table[]` lưu trong class.

## 7. Ví dụ chạy được Java 17: từ `try/catch` đến `Code`

Tạo file **`CodeAttributeDemo.java`** đúng tên class:

```java
public class CodeAttributeDemo {

    public static int divideOrMinusOne(int dividend, int divisor) {
        try {
            return dividend / divisor;
        } catch (ArithmeticException error) {
            return -1;
        }
    }

    public static long sumLong(long left, long right) {
        return left + right;
    }

    public int increment(int value) {
        return value + 1;
    }

    public static void main(String[] args) {
        System.out.println("normal=" + divideOrMinusOne(12, 3));
        System.out.println("fallback=" + divideOrMinusOne(12, 0));
        System.out.println("sum=" + sumLong(20L, 22L));
        System.out.println("increment=" + new CodeAttributeDemo().increment(4));
    }
}
```

Biên dịch bằng compiler JDK 17+ có hỗ trợ `--release 17` và yêu cầu đầy đủ debug metadata:

```bash
javac --release 17 -g CodeAttributeDemo.java
java CodeAttributeDemo
javap -c -v -p CodeAttributeDemo
```

**Stdout của riêng lệnh `java CodeAttributeDemo`** (không bao gồm output dài của `javap`):

```text
normal=4
fallback=-1
sum=42
increment=5
```

Ở `divideOrMinusOne(12, 3)`, instruction `idiv` thành công. Khi `divisor == 0`, `idiv` ném `ArithmeticException`, handler trả về `-1`. Hai lời gọi thực thi **cùng một Code attribute** nhưng đi theo hai đường control flow khác nhau.

### Đọc `javap -c -v -p` theo từng phần

Trong output của method `divideOrMinusOne(int,int)` do `javac` phiên bản 17 thông thường sinh ra, phần liên quan có dạng:

```text
Code:
  stack=2, locals=3, args_size=2
     0: iload_0
     1: iload_1
     2: idiv
     3: ireturn
     4: astore_2
     5: iconst_m1
     6: ireturn
  Exception table:
     from    to  target type
        0     3     4   Class java/lang/ArithmeticException
```

**Chú ý:** đây là đoạn disassembly tiêu biểu của `javac`, không phải cam kết mọi compiler/version sẽ chọn cùng offsets hoặc bố trí handler. Các phần `LineNumberTable`, `LocalVariableTable`, `StackMapTable` và constant pool có thể xuất hiện xen kẽ hoặc phía dưới trong output `javap -v`.

Giải thích từng trường:

- **`stack=2`:** khi chuẩn bị `idiv`, stack cùng lúc chứa `dividend` và `divisor`, mỗi số `int` chiếm một slot. Trong handler chỉ cần một slot để nhận exception; độ sâu tối đa vẫn là **2**.
- **`locals=3`:** `dividend` ở slot 0, `divisor` ở slot 1, biến `error` trong `catch` ở slot 2. Chương trình có hai tham số nhưng cần ba local slots.
- **`args_size=2`:** `javap` tóm tắt hai tham số được khai báo; đây **không phải** trường độc lập có tên `args_size` trong `Code_attribute`.
- **`0–3`:** handler bảo vệ instruction bắt đầu tại BCI 0, 1, 2; `idiv` ở BCI 2 được bảo vệ. `ireturn` ở BCI 3 nằm **ngoài** khoảng vì `to` exclusive.
- **`target 4`:** khi chia cho 0, JVM chuyển tới `astore_2` để lưu exception object vào slot 2, sau đó đẩy `-1` và trả về qua `ireturn`.
- **`type Class java/lang/ArithmeticException`:** `catch_type` trỏ tới constant pool class entry; chỉ bắt exception phù hợp với loại này.

Đừng hiểu `stack=2` là “method có hai câu lệnh” hoặc `locals=3` là “có ba biến được khai báo trong source”; chúng là những **slot** dùng trong frame.

### Đọc `long` và method instance

Với `sumLong(long,long)`, output tiêu biểu:

```text
Code:
  stack=4, locals=4, args_size=2
     0: lload_0
     1: lload_2
     2: ladd
     3: lreturn
```

Đây là method `static`: `left` chiếm local slots 0 và 1, `right` chiếm 2 và 3. Đặt hai `long` lên operand stack sử dụng **4 slot** trước khi `ladd`. Giá trị `args_size=2` đếm **hai đối số logic**, không có nghĩa chỉ cần hai local slots.

Với `increment(int)` là method **instance**, output tiêu biểu:

```text
Code:
  stack=2, locals=2, args_size=2
     0: iload_1
     1: iconst_1
     2: iadd
     3: ireturn
```

`this` chiếm slot 0 dù body không sử dụng nó; `value` nằm slot 1. `args_size=2` trong cách in của `javap` đếm receiver `this` và một tham số truyền vào method invocation.

### Tự kiểm tra các giả thiết

Nếu bạn dùng một compiler khác và thấy mã lệnh hoặc offset khác, hãy tự kiểm tra giá trị do nó in rồi áp dụng **quy tắc JVMS** tương ứng. Không nên ghi test yêu cầu bytecode giống nguyên văn một ví dụ, trừ khi dự án đang kiểm thử chính công cụ/compiler được cố định phiên bản.

## 8. StackMapTable và các attribute lồng bên trong Code

Sau `exception_table[]`, `Code` còn có bảng `attributes[]` của riêng nó. Một số thuộc tính hay gặp:

| Thuộc tính | Mục đích | Có phải danh sách opcode hoặc handler không? |
| --- | --- | --- |
| `StackMapTable` | Lưu các stack map frames giúp kiểm tra kiểu locals/operand stack tại các điểm trong control flow | Không; phục vụ verification |
| `LineNumberTable` | Ánh xạ bytecode offsets sang số dòng source (hỗ trợ debug/stack trace) | Không |
| `LocalVariableTable` | Tên, descriptor, index và khoảng sống của một số local variables | Không |
| `LocalVariableTypeTable` | Thông tin generic signatures bổ sung cho locals khi có | Không |
| Attribute khác được định nghĩa phù hợp | Metadata khác theo chuẩn và mở rộng được phép | Không được tùy ý thay đổi ngữ nghĩa core của code |

**`StackMapTable` không phải operand stack đang chạy.** Nó mô tả **trạng thái kiểu kỳ vọng** ở một số BCI để verifier xác nhận đường đi control flow hợp lệ. Ví dụ một exception handler cần nhận reference tương thích với `Throwable`, không thể được tùy tiện xem như `int` rồi đưa vào `iadd`.

Ở class-file major 50 trở lên, nếu không xuất hiện `StackMapTable` tường minh thì đặc tả có cơ chế **implicit stack map** tương đương một bảng không chứa entry; điều này không đồng nghĩa JVM bỏ qua verification. Một class file có branch/handler phức tạp phải có thông tin verification hợp lệ theo các quy tắc áp dụng cho phiên bản class file ấy.

Khi bật `javac -g`, `LineNumberTable` và `LocalVariableTable` thường đầy đủ hơn; khi biên dịch không kèm debug info, tên biến có thể không có dù code vẫn chạy. Không dựa vào việc tồn tại `LocalVariableTable` để xác định xem class file có hợp lệ hay không.

### Đọc và sửa class file có thể bị `VerifyError` vì sao?

Nếu tự viết bytecode bằng thư viện hoặc sửa tệp `.class`, bạn cần bảo đảm:

- Các đường control flow dùng operand stack **đúng loại và đúng số slot**; nhánh merge hợp lệ.
- `max_stack` và `max_locals` đủ cho tất cả đường thực thi hợp lệ.
- BCI trong branch, exception-table bounds, target handler, stack map frames đều hợp lệ.
- Các instruction nhận đúng kiểu operand/local; không đọc slot chưa có kiểu hợp lệ.
- `StackMapTable` (nếu cần) khớp với frame state ở các mục tiêu điều khiển.

Lỗi verification thường xảy ra trước khi JVM chạy method tương ứng; nó khác lỗi runtime `ArithmeticException` được ví dụ tạo ra rồi bắt bằng `catch`. Khi debug, đọc **thông báo lỗi và BCI**, dùng `javap -v`, đối chiếu descriptor, locals, exception table và stack map frames.

## 9. Xử lý exception đi qua nhiều method

`exception_table[]` chỉ chứa handler **của method đang xét**. Khi method A gọi B:

```text
A gọi B
  └── B thực thi một instruction ném exception
      ├── B có handler phù hợp trong phạm vi BCI? → chạy handler của B
      └── Nếu không:
          └── exception lan ra A tại call site
              ├── A có handler phù hợp? → chạy handler của A
              └── Không → tiếp tục ra caller cao hơn
```

Vì vậy, một `try/catch` trong A có thể bắt exception phát sinh sâu trong B dù exception table của A chỉ bảo vệ BCI chứa invocation và **không** liệt kê tất cả instruction bên trong B.

Về mặt bytecode, các phần `try-with-resources`, `finally`, synchronized code và synthetic paths do compiler sinh có thể làm exception table nhiều entry hơn source thể hiện. Đừng suy rằng “một `catch` trong source luôn đúng một entry”, hay thấy `catch_type=0` rồi mặc định người viết source cố ý bắt mọi `Throwable`.

Khi exception được chuyển tới handler, operand stack của frame được đặt để chứa exception object. Code của handler thường lưu nó vào local bằng `astore`; nếu exception handler tái ném, bạn có thể thấy `aload` rồi `athrow`. Các lệnh `astore` và `athrow` nằm trong **`code[]`**, còn exception table chỉ mô tả **vùng và điểm chuyển điều khiển**.

## 10. Các giới hạn và nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`max_stack` là kích thước JVM thread stack” | Nó chỉ là độ sâu **operand stack** tối đa của **một method frame**; `-Xss` là khái niệm khác |
| “`max_stack` = số biến đang sống” | Nó đếm slot tạm trên operand stack; locals có giới hạn riêng `max_locals` |
| “`max_locals` = số biến đặt tên trong source” | Đếm local **slots**, gồm tham số, `this`, biến compiler tạo/tái dùng; `long/double` cần hai slot |
| “Mọi method có `this` ở slot 0” | Chỉ method instance; method `static` không có receiver slot |
| “Hai tham số `long` nên `locals=2`” | Hai `long` chiếm tổng cộng **4 slot** |
| “`code_length` = số lệnh trong method” | Đó là **số byte**; lệnh JVM dài ngắn khác nhau |
| “`Exception table` giống `throws`” | Exception table là handler trong Code; `Exceptions` attribute mô tả checked exceptions khai báo |
| “`end_pc` vẫn thuộc phạm vi `try`” | `end_pc` là **exclusive**, chỉ bảo vệ BCI trong `[start_pc,end_pc)` |
| “Handler nào cũng có `catch_type` khác 0” | Giá trị **0** là catch-all handler |
| “JVM tìm handler không theo thứ tự” | **Entry phù hợp đầu tiên** trong exception table quyết định xử lý |
| “`StackMapTable` là ảnh chụp operand stack runtime” | Đó là thông tin **verification types** ở các BCI |
| “Bỏ debug info thì JVM mất logic xử lý exception” | Logic nằm trong bytecode và exception table; debug metadata có chức năng khác |
| “`javap` in ra bytecode source Java nguyên văn” | `javap` phân rã `code[]` thành mnemonic; source đã qua compiler transform/optimization |
| “Method abstract có `Code` trống” | Phương thức `abstract`/`native` không có Code attribute |
| “Chỉ cần tăng `max_stack` là bytecode sai sẽ chạy” | Còn cần kiểm tra kiểu, control flow, stack map frames, locals và mọi ràng buộc khác |

## 11. Quy trình kiểm tra `Code` khi debug class file

1. **Chốt JDK và class-file version**: dùng `java -version`, `javac -version`; `javap -v MyClass` in `major version` của file. Java 17 thường là major 61.
2. **Chọn đúng method**: phân biệt tên, descriptor, static/instance, constructor, overload. Một class có nhiều `Code` attributes.
3. **Đọc `stack=..., locals=..., args_size=...`**: tính số slot cần dùng, nhớ `long/double` chiếm hai; receiver ở slot 0 chỉ khi method instance.
4. **Theo dõi `code[]` theo BCI**: ghi input operand stack/local cho mỗi instruction trên những nhánh quan trọng.
5. **Đọc exception table**: đánh dấu mỗi đoạn `[from,to)` và `target` trên disassembly. Tại `target`, stack nhận exception object.
6. **Đọc `StackMapTable` và metadata debug khi cần**: xem verification states, line numbers, local variable lifetimes; tránh coi chúng là source business logic.
7. **Phân biệt lỗi**: `VerifyError`/`ClassFormatError` là vấn đề hợp lệ class file/linking; exception do code chạy như `ArithmeticException` là vấn đề runtime logic.
8. **Đối chiếu với đặc tả đúng edition**: đừng suy ra một thứ là bắt buộc chỉ vì `javac` của một release in đúng chuỗi đó.

## 12. Câu hỏi ôn tập

**Câu 1:** `max_stack=4` trong `sumLong(long,long)` có nghĩa có bốn biến Java?

Không. Có hai đối số `long`, mỗi giá trị chiếm hai slot trên operand stack; khi hai toán hạng cùng hiện diện thì độ sâu là bốn **slot**.

**Câu 2:** Method instance `increment(int value)` có một biến tham số, vậy `max_locals` tối thiểu có phải 1?

Không. Local slot 0 chứa `this`, slot 1 chứa tham số `value`; cần tối thiểu hai slot.

**Câu 3:** Handler `from=0,to=3,target=4` có bắt exception xảy ra tại BCI 3?

Không. BCI 3 nằm ngoài khoảng vì `to` exclusive; nó bắt các instruction có BCI trong `[0,3)`.

**Câu 4:** `catch_type=0` có nghĩa không có exception nào được bắt?

Không. Ngược lại, đó là **catch-all handler**, có thể được compiler dùng cho cleanup/`finally`.

**Câu 5:** Nếu không thấy `LocalVariableTable` thì method không có biến cục bộ?

Không. `max_locals` và instructions load/store đủ để thực thi. `LocalVariableTable` chỉ là metadata tên/kiểu/khoảng sống tùy chọn.

**Câu 6:** Khi `idiv` ném exception, có bắt buộc phải có `athrow` ngay sau `idiv` mới dùng được exception table?

Không. JVM tự ném `ArithmeticException` cho phép chia nguyên cho 0; exception table được xét theo vị trí instruction phát sinh exception.

## Tài liệu gốc để tra cứu

- [JVMS Java SE 17 `4.7.3` — The Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): cấu trúc và ràng buộc của `max_stack`, `max_locals`, `code_length`, exception table.
- [JVMS Java SE 17 `2.6` — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): local variables, operand stack và frame.
- [JVMS Java SE 17 `2.10` — Throwing Exceptions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.10): exception propagation và handler.
- [JVMS Java SE 17 `4.7.4 — StackMapTable](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.4) và [`4.10 — Verification](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10): kiểm tra kiểu/flow của class file.
- [JVMS Java SE 17 `6.5` — Instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `iload`, `idiv`, `astore`, `ladd`, `athrow` và các opcode khác.
- [Java SE 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): sử dụng `-c`, `-v`, `-p` để xem bytecode và các thuộc tính class file.

**Điểm ghi nhớ:** `Code_attribute` là bản mô tả **một method** gồm giới hạn frame (`max_stack`, `max_locals`), bytecode (`code[]`), handler (`exception_table[]`) và metadata lồng bên trong. Đọc đúng số **slot**, đúng **BCI**, đúng phạm vi **[start_pc,end_pc)** và đúng thứ tự handler sẽ nối được source Java, JVM execution và lỗi verification một cách có căn cứ.

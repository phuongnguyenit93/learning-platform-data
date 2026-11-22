# StackMapTable và thông tin kiểu phục vụ xác minh bytecode

## 1. Bài toán: JVM kiểm tra một phương thức bytecode bằng cách nào?

Mã nguồn Java được trình biên dịch kiểm tra kiểu, nhưng tệp `.class` có thể đến từ nhiều nguồn: `javac`, Kotlin/Scala, công cụ sinh mã, trình biến đổi bytecode, hoặc tệp được tải từ một nguồn không đáng tin cậy. JVM **không thể chỉ dựa vào lời hứa rằng tệp đã được biên dịch đúng**. Trước khi chạy, nó phải áp dụng những quy tắc về cấu trúc và kiểu của class file, giúp phát hiện bytecode không hợp lệ.

Xem một tình huống giả định:

```text
Vị trí A: operand stack có int
       |
       | nhảy đến B
       v
Vị trí B: lệnh invokevirtual của một phương thức instance
```

`invokevirtual` cần một **tham chiếu đối tượng** phù hợp, không thể lấy một `int` làm receiver. Dù bytecode được mã hóa theo cú pháp đúng, luồng kiểu như vậy phải bị từ chối khi xác minh.

Với lệnh rẽ nhánh, tình huống còn khó hơn: **nhiều đường chạy có thể hội tụ ở cùng một bytecode offset**. JVM cần biết những đường đó mang cùng một trạng thái kiểu hợp lệ hay không. `StackMapTable` cung cấp các **mốc trạng thái kiểu đã được mã hóa trong class file** để việc xác minh có thể kiểm tra các bước chuyển của bytecode hiệu quả và có cơ sở rõ ràng.

```text
Mã nguồn Java
   |
   v
javac / compiler / bytecode generator
   |
   v
.class
  ├── constant pool
  ├── method_info
  └── Code
       ├── max_stack, max_locals
       ├── code[] (bytecode)
       ├── exception_table
       └── attributes[]
            └── StackMapTable (nếu có)
                  ├── frame tại điểm điều khiển 1
                  ├── frame tại điểm điều khiển 2
                  └── ...
   |
   v
JVM: nạp lớp → xác minh cấu trúc và kiểu → thực thi khi hợp lệ
```

**Ý chính:** `StackMapTable` không chứa mã nguồn, không thay thế bytecode, và không “chạy” thay JVM. Nó mô tả **kiểu xác minh được kỳ vọng** của **các biến cục bộ** (*local variables*) và **ngăn xếp toán hạng** (*operand stack*) ở những vị trí quan trọng của một phương thức.

## 2. Phân biệt ba lớp thông tin

Để đọc `StackMapTable` không nhầm, cần tách ba khái niệm:

| Khái niệm | Nội dung | Dùng để làm gì |
| --- | --- | --- |
| **Kiểu trong ngôn ngữ Java** | `boolean`, `byte`, `char`, `int`, `String`, generic type… | Compiler kiểm tra tính hợp lệ của mã nguồn |
| **Kiểu của giá trị và câu lệnh JVM** | `int`, `long`, `float`, `double`, `reference`, category 1/2; opcode như `iload`, `aload` | JVM thực thi và tuân theo hợp đồng của opcode |
| **Verification type** | Các kiểu trừu tượng dùng để kiểm tra an toàn của luồng bytecode: `Integer`, `Object`, `Null`, `Uninitialized`… | Bytecode verifier kiểm tra các trạng thái kiểu và phép chuyển giữa chúng |

Ví dụ, ở mức bytecode, `boolean`, `byte`, `char` và `short` được thao tác thông qua các kiểu và lệnh liên quan `int` trong nhiều ngữ cảnh; `StackMapTable` không có một tag riêng cho từng primitive nhỏ đó. Một `String` reference trong frame được mô tả bằng `Object_variable_info` trỏ đến class thích hợp trong constant pool; còn một null reference có tag xác minh riêng.

**Verification type không phải đối tượng kiểu Java có thể khai báo trong code.** `UninitializedThis` là một trạng thái của bộ xác minh trong constructor; nó không phải một kiểu khai báo của ngôn ngữ Java. Tương tự, `Top` là một kiểu xác minh đặc biệt, không phải class `java.lang.Object` và không phải nguyên lý “mọi giá trị đều phù hợp”.

## 3. Stack map frame là gì?

Một **stack map frame** mô tả trạng thái kiểu tại **một offset của bytecode** bên trong **một phương thức**. Trạng thái gồm:

- **Local variables:** kiểu của các slot biến cục bộ trong frame thực thi phương thức.
- **Operand stack:** kiểu của những giá trị đang nằm trên ngăn xếp toán hạng tại offset đó.

Ví dụ trừu tượng:

```text
Phương thức: static String pick(boolean flag)

Tại vị trí đầu (initial frame):
  locals       = [Integer]       // flag: boolean được biểu diễn kiểu verifier Integer
  operandStack = []

Sau khi đi qua hai nhánh và hội tụ:
  locals       = [Integer, Object(java/lang/String)]
  operandStack = []              // trước khi nạp value để return

Lệnh aload_1:
  locals       = [Integer, Object(java/lang/String)]
  operandStack = [Object(java/lang/String)]

Lệnh areturn:
  lấy reference tương thích từ operand stack để trả về
```

Sơ đồ này chỉ minh họa **kiểu kỳ vọng**, không phải dump bytecode chính xác của mọi compiler. Compiler có thể chọn cách bố trí slot, nhánh và frame khác nhưng phải tạo class file hợp lệ.

### 3.1. Vì sao cần nhìn cả locals lẫn operand stack?

JVM là một **máy ngăn xếp** (*stack-based virtual machine*). Lệnh `iadd` lấy hai giá trị tương thích kiểu `int` từ operand stack; `aload_1` lấy một giá trị reference từ local slot 1 và đẩy lên operand stack. `invokestatic`, `invokevirtual`, `ireturn`, `areturn` đều đặt yêu cầu về số lượng và kiểu của các giá trị này.

Một trạng thái có thể hợp lệ với lệnh `ireturn` nhưng không hợp lệ với `areturn`. Kiểm tra từng opcode cần theo dõi loại giá trị trước và sau khi thực thi trừu tượng (*type transition*).

### 3.2. Không phải mỗi instruction đều có một stack map frame được lưu

`StackMapTable` thường cung cấp frame ở **đầu các basic block**, nhất là **đích của lệnh nhảy** và **đầu exception handler**, theo các ràng buộc xác minh cụ thể. Các lệnh nằm giữa những điểm này được verifier kiểm tra bằng cách áp dụng quy tắc chuyển trạng thái kiểu của từng opcode.

Vì vậy:

- `max_stack` là giới hạn độ sâu operand stack, **không** phải danh sách trạng thái kiểu.
- `max_locals` là giới hạn slot biến cục bộ, **không** phải nội dung `StackMapTable`.
- Một frame có thể có operand stack rỗng.
- Một phương thức có thể không có entry `StackMapTable` tường minh, nếu trạng thái kiểu mặc định và luồng bytecode đủ để xác minh theo quy tắc class file tương ứng.

## 4. Vị trí và cấu trúc của `StackMapTable` trong tệp `.class`

Theo **JVMS `4.7.4`**, `StackMapTable` là một **attribute có độ dài biến thiên** nằm **bên trong bảng attributes của `Code` attribute** của một phương thức có mã bytecode. Trong một `Code` attribute có tối đa **một** `StackMapTable`.

Dạng nhị phân trừu tượng:

```text
StackMapTable_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 number_of_entries;
    stack_map_frame entries[number_of_entries];
}
```

Ý nghĩa:

| Trường | Ý nghĩa |
| --- | --- |
| `attribute_name_index` | Chỉ số tới `CONSTANT_Utf8_info` chứa chuỗi `StackMapTable` trong constant pool |
| `attribute_length` | Độ dài phần thân attribute, không bao gồm 6 byte đầu của attribute header |
| `number_of_entries` | Số frame **tường minh** trong `entries` |
| `entries[]` | Các frame có thứ tự theo vị trí bytecode; có thể được mã hóa dạng delta và kế thừa thông tin từ frame trước |

Một số nhầm lẫn quan trọng:

1. **Không đặt `StackMapTable` ngang cấp toàn bộ class một cách tùy tiện.** Nó là attribute của một `Code` attribute cụ thể, tức gắn với việc xác minh **một phương thức**.
2. **Không phải frame đầu tiên của phương thức được ghi trong `entries[0]`.** Trạng thái đầu tiên là một **initial frame ngầm định**, tính từ mô tả phương thức và các quy tắc liên quan; `entries[0]` biểu diễn frame tường minh tiếp theo.
3. **Thiếu attribute không nhất thiết nghĩa là class hỏng.** Với class file phiên bản **50.0 trở lên**, nếu `Code` không có `StackMapTable` thì theo đặc tả tồn tại một **stack map attribute ngầm định có `number_of_entries = 0`**. Class chỉ qua xác minh nếu luồng mã của phương thức phù hợp với những gì được phép trong trường hợp này.
4. **Frame không nói về giá trị cụ thể.** Ví dụ ghi `Integer` có nghĩa slot phải chứa giá trị kiểu verifier Integer; nó không ghi số 10 hay 20 đang lưu tại runtime.

### 4.1. Kiểu xác minh và tag trong `verification_type_info`

Mỗi slot được mô tả bằng một cấu trúc `verification_type_info`. Các tag theo JVMS:

| Tag | Tên cấu trúc | Vai trò |
| ---: | --- | --- |
| 0 | `Top_variable_info` | Trạng thái `Top` dùng trong kiểm tra slot và kiểu trừu tượng; không là một đối tượng Java |
| 1 | `Integer_variable_info` | Giá trị `int` theo mô hình xác minh (bao gồm các giá trị primitive nhỏ khi được biểu diễn tương ứng) |
| 2 | `Float_variable_info` | Giá trị `float` |
| 3 | `Double_variable_info` | Giá trị `double` |
| 4 | `Long_variable_info` | Giá trị `long` |
| 5 | `Null_variable_info` | Null reference |
| 6 | `UninitializedThis_variable_info` | `this` chưa khởi tạo hoàn chỉnh trong constructor |
| 7 | `Object_variable_info` | Reference có kiểu class, interface hoặc array được chỉ định qua constant pool |
| 8 | `Uninitialized_variable_info` | Tham chiếu tới object vừa được tạo bằng `new` nhưng chưa gọi xong constructor tương ứng; gắn với offset lệnh `new` |

**Tag 7:** cấu trúc `Object_variable_info` chứa `cpool_index` tới `CONSTANT_Class_info` hợp lệ. Đối tượng có thể là class, interface hoặc array type tùy thông tin tương ứng; không hiểu chữ “Object” ở tên cấu trúc là lúc nào cũng `java/lang/Object`.

**Tag 8:** cấu trúc `Uninitialized_variable_info` chứa `offset` tham chiếu đến một **instruction `new`** có liên quan. Điều này cho phép verifier phân biệt các object chưa khởi tạo ở những lệnh `new` khác nhau.

**`long` và `double`:** mỗi giá trị chiếm **hai đơn vị slot** trong mô hình local variables/operand stack; bảng frame mã hóa theo quy tắc riêng để khớp slot. Không suy luận `number_of_locals` luôn bằng đúng số slot của `max_locals` vì các entry biểu diễn `long` hoặc `double` có thể chiếm hai slot.

### 4.2. Bảy dạng `stack_map_frame`

Vì trạng thái kiểu giữa các basic block thường gần giống nhau, class file có các dạng nén:

| Kiểu frame | Mã `frame_type` | Nội dung |
| --- | --- | --- |
| `same_frame` | 0–63 | Locals như frame trước; operand stack rỗng; offset delta nằm trong tag |
| `same_locals_1_stack_item_frame` | 64–127 | Locals giữ nguyên; operand stack có một item; delta nằm trong tag |
| `same_locals_1_stack_item_frame_extended` | 247 | Giống dạng có 1 stack item nhưng `offset_delta` được ghi bằng `u2` |
| `chop_frame` | 248–250 | Operand stack rỗng; bỏ 1–3 mục locals ở cuối so với frame trước |
| `same_frame_extended` | 251 | Locals giữ nguyên, stack rỗng; delta viết riêng bằng `u2` |
| `append_frame` | 252–254 | Operand stack rỗng; thêm 1–3 mục locals so với frame trước |
| `full_frame` | 255 | Mã hóa tường minh tập locals và operand stack cho frame mới |

Dải tag **128–246** được dành riêng trong định dạng, không phải một kiểu frame người đọc có thể dùng tùy ý.

**Nén frame không làm mất thông tin cần thiết cho verifier.** Ví dụ nếu locals không thay đổi và stack rỗng, `same_frame` chỉ cần ghi tag; muốn hiểu đầy đủ thì tái tạo từ trạng thái frame trước.

### 4.3. `offset_delta` là khoảng cách giữa frame, không phải offset tuyệt đối trong mọi trường hợp

Các frame tường minh được mã hóa theo **thứ tự tăng của offset bytecode**. Công thức xác định vị trí:

- **Frame tường minh đầu tiên:** `offset = offset_delta` (so với initial frame ngầm định).
- **Các frame tường minh tiếp theo:** `offset = previous_offset + offset_delta + 1`.

Ví dụ mô hình:

```text
Initial frame : offset = 0 (ngầm định)
Explicit #1   : offset_delta = 8   → offset 8
Explicit #2   : offset_delta = 4   → offset 8 + 4 + 1 = 13
Explicit #3   : offset_delta = 5   → offset 13 + 5 + 1 = 19
```

Các offset trên là **ví dụ toán học giả định**, không phải output compiler. Phải đảm bảo frame áp dụng tại offset hợp lệ của **instruction** và đáp ứng các quy tắc target/control flow. Cộng `+1` ở những frame sau giúp phân biệt offset và ngăn tạo frame tường minh trùng vị trí do nhầm delta.

## 5. JVM tạo trạng thái đầu tiên (initial frame) như thế nào?

Verifier cần một điểm xuất phát trước khi xét các frame tường minh. **Initial frame** được suy ra từ **method descriptor**, việc phương thức là `static` hay instance, tên `<init>` trong constructor và những quy tắc có liên quan.

Ví dụ:

```java
static String describe(int id, Object value) {
    return id + ":" + value;
}
```

Đây là **đoạn minh họa phương thức** cần đặt trong một lớp, không phải chương trình độc lập. Với phương thức `static`, các tham số ở đầu locals theo thứ tự:

```text
locals[0] = Integer
locals[1] = Object(java/lang/Object)
stack     = []
```

Trong phương thức **instance thông thường**, local slot 0 chứa receiver `this`, các tham số bắt đầu sau đó. Với phương thức `static`, **không có `this` ở slot 0**.

Trong **constructor `<init>`** của một lớp, receiver có trạng thái `UninitializedThis` trước khi việc khởi tạo hợp lệ hoàn thành. Đó là lý do Java không thể tùy tiện dùng một `this` chưa khởi tạo như một đối tượng hoàn chỉnh trong mọi tình huống.

### 5.1. `long`/`double` và slot đôi

```java
static void consume(long id, double ratio, Object object) {
    System.out.println(object);
}
```

Ví dụ khái niệm về local slot index:

```text
slot 0–1 : long id
slot 2–3 : double ratio
slot 4   : Object object
```

Đừng lấy số **giá trị khai báo** làm số **slot**. Ngay cả khi frame dùng một entry cho `Long` hoặc `Double`, thông tin vị trí local tiếp theo vẫn phải tính theo quy tắc hai slot.

### 5.2. Kiểu sau rẽ nhánh và merge

Giả sử hai nhánh cùng ghi một giá trị `String` vào local 1:

```java
static String pick(boolean flag) {
    String value;
    if (flag) {
        value = "left";
    } else {
        value = "right";
    }
    return value;
}
```

Nếu compiler tạo các nhánh và một điểm hội tụ, verifier cần thấy rằng ở các đường đến điểm này, local chứa kiểu tham chiếu tương thích `java/lang/String`. Nếu một nhánh mang `int` còn nhánh kia yêu cầu tham chiếu `String` rồi dùng `aload` tại điểm hội tụ, class file có thể **không qua xác minh**.

Khi gặp các kiểu tham chiếu khác nhau mà mã hợp lệ, trạng thái kiểu được phép tại điểm hội tụ phải đáp ứng quan hệ gán được chấp nhận bởi quy tắc verifier. Có thể xuất hiện một kiểu chung thích hợp, nhưng không nên dùng trực giác “mọi thứ đổi thành `Object`” để bỏ qua các quy tắc thực tế về interface, mảng, khả năng khởi tạo và opcode.

## 6. Verifier sử dụng `StackMapTable` như thế nào?

### 6.1. Kiểm tra luồng điều khiển và chuyển trạng thái kiểu

Với mô hình **verification by type checking** (JVMS `4.10.1`):

1. JVM có cấu trúc phương thức: code array, giới hạn locals/stack, exception table, method descriptor.
2. Verifier xác định **expected type state** tại những vị trí được mô tả bởi stack map frame, bao gồm initial frame.
3. Ở mỗi instruction, nó áp dụng quy tắc của opcode đối với locals và operand stack: đọc kiểu nào, tạo kiểu nào, pop/push bao nhiêu phần tử.
4. Khi một instruction chuyển điều khiển sang offset khác (ví dụ `if`, `goto`, exception handler), trạng thái được suy ra ở đường chuyển phải tương thích với trạng thái mà frame đích yêu cầu.
5. Những thao tác không thỏa quy tắc kiểu, stack height, tính hợp lệ của target hay ràng buộc đối tượng chưa khởi tạo dẫn tới **verification failure**.

Không coi đây là lời khẳng định JVM “chạy thử” toàn bộ chương trình với dữ liệu thật. Verifier hoạt động trên **kiểu trừu tượng**, không thực thi nghiệp vụ, không biết các giá trị người dùng nhập và không chứng minh chương trình không ném exception hợp lệ khi chạy.

### 6.2. Rẽ nhánh: điểm hội tụ cần một hợp đồng kiểu

Sơ đồ giả định:

```text
                  [đầu phương thức]
                         |
                  iload_0, ifeq
                    /          \
                nhánh A       nhánh B
                  |              |
             astore_1       astore_1
                    \          /
                     \        /
                    [join @ offset J]
                    locals[1] = String
                    operandStack = []
                           |
                        aload_1
                           |
                        areturn
```

Frame ở `J` cho biết **kiểu được kỳ vọng khi mọi đường hợp lệ đi tới**. Bytecode gây ra stack height khác nhau ở hai nhánh hoặc kiểu locals không phù hợp có thể bị từ chối.

**Không có StackMapTable “giải quyết giúp” bytecode sai.** Nếu dòng nhảy dẫn vào giữa một instruction, các stack không khớp, hoặc một giá trị primitive bị dùng như object reference, việc thêm frame tùy tiện không làm chương trình thành hợp lệ.

### 6.3. Exception handler cũng là đích luồng điều khiển

Giả sử bytecode có một `try/catch`. Khi exception được chuyển đến handler, operand stack lúc bắt đầu handler phải chứa **tham chiếu ngoại lệ** tương ứng theo hợp đồng; không phải giữ nguyên toàn bộ operand stack của instruction đang lỗi.

Ví dụ Java:

```java
static int safeLength(String value) {
    try {
        return value.length();
    } catch (NullPointerException ex) {
        return -1;
    }
}
```

Exception handler cần trạng thái kiểu phù hợp với nhánh exception. Đặc tả yêu cầu xác minh đúng entry state của handler; compiler sinh `StackMapTable` tương ứng khi target class format yêu cầu.

### 6.4. `new`, `Uninitialized` và gọi constructor

Bytecode tạo một object thường theo chuỗi khái niệm:

```text
new SomeClass
dup
invokespecial SomeClass.<init>:()V
... dùng tham chiếu đã khởi tạo ...
```

Sau `new` nhưng trước lời gọi constructor hợp lệ, reference ở trạng thái **uninitialized**. Việc gán/gọi phương thức hoặc để nó thoát khỏi nơi cho phép bị giới hạn chặt; verifier cần biết **lệnh `new` nào** sinh ra giá trị đó.

Hai trạng thái đáng phân biệt:

- **`UninitializedThis`:** receiver đặc biệt của `<init>` trước khi khởi tạo theo hợp đồng.
- **`Uninitialized(offset)`:** tham chiếu tới object mới tạo tại offset `new` cụ thể.

Mã bytecode do compiler tạo phải bảo đảm transition từ uninitialized sang initialized theo đúng quy tắc constructor. Điều này liên quan đến **an toàn về cấu trúc đối tượng**, khác với việc kiểm tra biến Java có bằng `null` hay không.

## 7. Thí nghiệm chạy được với Java 17+: xem `StackMapTable` bằng `javap -v`

Tạo tệp **`FrameDemo.java`** ở một thư mục riêng:

```java
public class FrameDemo {
    static String pick(boolean flag) {
        String selected;
        if (flag) {
            selected = "left";
        } else {
            selected = "right";
        }
        return selected;
    }

    static int safeLength(String text) {
        try {
            return text.length();
        } catch (NullPointerException exception) {
            return -1;
        }
    }

    static String create() {
        return new String("created");
    }

    public static void main(String[] args) {
        System.out.println(pick(true));
        System.out.println(pick(false));
        System.out.println(safeLength("abc"));
        System.out.println(safeLength(null));
        System.out.println(create());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FrameDemo.java
java FrameDemo
```

**Stdout chính xác**:

```text
left
right
3
-1
created
```

Giải thích đầu ra:

- Hai lời gọi `pick` đi qua hai nhánh khác nhau nhưng trả cùng **kiểu `String`**.
- `safeLength("abc")` trả độ dài 3; `safeLength(null)` kích hoạt `NullPointerException`, được handler chuyển thành `-1`.
- `create()` tạo một object `String` mới; bytecode của nó thể hiện quá trình cấp phát và gọi constructor.

Để quan sát phần metadata class file:

```bash
javap -v -p FrameDemo
```

`-v` in thông tin chi tiết, trong đó có `Code` attribute và `StackMapTable` của các phương thức phù hợp; `-p` cho phép hiển thị cả thành viên không public. Tìm các dòng như:

```text
Code:
  stack=..., locals=..., args_size=...
  ...
  StackMapTable: number_of_entries = ...
    frame_type = ... /* ... */
```

**Đây là sơ đồ minh họa định dạng hiển thị, không phải stdout nguyên văn của `javap`**. Các dấu `...` đại diện cho dữ liệu phụ thuộc compiler và phương thức. Hãy dựa vào output thực tế trên máy để xem `frame_type` và offset đúng của build đang dùng.

### 7.1. Phân tích `pick`

Có thể nhìn thấy các instruction thuộc nhóm:

- `iload_0` để đọc giá trị cờ (boolean được xử lý theo dạng integer ở bytecode).
- `ifeq` hoặc một dạng nhánh phù hợp.
- `ldc` để nạp hằng chuỗi.
- `astore_1` để lưu reference vào local.
- `goto` để đi qua nhánh không được chọn.
- `aload_1` và `areturn` để trả reference.

Compiler có thể sắp xếp nhánh hoặc thực hiện tối ưu khác. Điều cần tìm là **điểm đích nhảy** và **frame mô tả trạng thái ở điểm đó**. Nếu các nhánh cập nhật `selected`, frame ở vị trí hội tụ phải tương thích với các đường đi.

Ví dụ trạng thái kiểu **sơ đồ, không cố định theo offset**:

```text
locals = [Integer(flag), Object(java/lang/String)]
stack  = []
```

Ở trạng thái này, `aload_1` được phép lấy reference tại local 1 để return. Cách mã hóa thật có thể dùng `append_frame`, `same_frame`, `full_frame` hay dạng phù hợp khác.

### 7.2. Phân tích `safeLength`

Trong output `javap -v`, xem cả:

- **Exception table:** vùng bytecode được bảo vệ và đích handler.
- **StackMapTable:** trạng thái tại handler, thường bao gồm một stack item kiểu ngoại lệ phù hợp.
- **Bytecode:** lệnh `invokevirtual` để gọi `String.length()`, rồi các lệnh chuyển sang nhánh return `-1`.

Ở đầu handler, operand stack được khôi phục theo cơ chế exception dispatch, có exception reference để mã handler xử lý. Vì vậy frame handler không cần mang toàn bộ nội dung stack của phép gọi `length()` trước đó.

### 7.3. Phân tích `create`

Với `new String("created")`, compiler thông thường sinh chuỗi opcode thể hiện `new`, `dup`, nạp tham số constructor và `invokespecial`. Kiểm tra `new` và `invokespecial` sẽ giúp liên hệ tag `Uninitialized` với quy tắc xác minh constructor.

**Không nhất thiết `create` phải có StackMapTable tường minh nhiều entries.** Vì phương thức có luồng điều khiển thẳng, initial frame ngầm định có thể đủ; không thấy dòng `StackMapTable` ở phương thức này **không phải** bằng chứng JVM bỏ qua verification.

### 7.4. Thử thay đổi cờ debug mà không thay đổi bản chất verification

`javac -g FrameDemo.java` bổ sung thông tin debug như line/local variable tables khi phù hợp. `javac -g:none FrameDemo.java` giảm các bảng debug tùy chọn. `StackMapTable` là **metadata phục vụ verifier**, không đơn thuần là bảng ánh xạ dòng mã nguồn như `LineNumberTable`.

Lệnh `javap -c -p FrameDemo` đủ để đọc instruction; dùng `-v` khi muốn xem các attribute và frame. Không lẫn **`LocalVariableTable`** (tên và phạm vi biến phục vụ debug) với **`StackMapTable`** (verification types theo bytecode offsets). Hai bảng phục vụ mục đích khác nhau.

## 8. Tại sao phải có frame ở những điểm điều khiển quan trọng?

Bất kỳ công cụ nào đọc bytecode cũng có thể xây dựng **control-flow graph**: các node là basic block, các cạnh là nhánh điều khiển hoặc exception. Nếu không có trạng thái kiểu ràng buộc ở mỗi điểm cần thiết, verifier có thể phải lặp suy luận trạng thái đi qua các cạnh cho tới khi đạt kết quả ổn định.

Stack map frames giúp bản class file cung cấp những **trạng thái được công bố** từ trước. Verifier vẫn cần kiểm tra chúng **đúng** và **tương thích với opcode/luồng**; không tin mù quáng. Đó là điểm khác biệt giữa:

- **Thông tin được khai báo trong class file:** trạng thái kiểu kỳ vọng tại offset.
- **Kết quả xác minh của JVM:** khẳng định rằng các lệnh và mọi cạnh luồng điều khiển thỏa các quy tắc bắt buộc.

Về mặt vận hành, cơ chế này hỗ trợ xác minh bằng kiểm tra kiểu, đặc biệt hữu ích cho các công cụ sinh/biến đổi class file đúng chuẩn. Nhưng **mục đích an toàn** mới là trọng tâm; `StackMapTable` không được coi là “một bộ tối ưu tốc độ ứng dụng” cho JIT và không trực tiếp bảo đảm mã chạy nhanh hơn.

### 8.1. Basic block không đồng nghĩa với mỗi dòng Java

Một dòng Java có thể tạo nhiều instruction bytecode; ngược lại, compiler có thể tối ưu và tái cấu trúc dòng nguồn. `StackMapTable` dùng **bytecode offsets**, không dùng số dòng nguồn. Vì vậy khi `javap` in:

```text
17: goto          26
20: ...
26: aload_1
```

Các số 17, 20, 26 trong ví dụ này chỉ là **offset minh họa**. Frame áp dụng cho offset theo code array thực tế, không nhất thiết trùng số dòng của `FrameDemo.java`.

### 8.2. Vì sao exception handler phải được kiểm tra?

Một exception có thể xuất hiện tại nhiều instruction trong vùng `try`. Khi JVM chuyển sang handler, stack đầu vào có dạng đặc biệt chứa exception reference. Nếu handler mong đợi sai kiểu hoặc cấu trúc stack, bytecode đó không hợp lệ. Frame tại handler là một điểm kiểm soát kiểu rõ ràng.

### 8.3. Vì sao không thể suy luận an toàn từ một đường chạy thử?

Chương trình có thể chạy ổn với đầu vào `true` nhưng đi vào nhánh khác với `false`. Bytecode verifier không chỉ quan sát một input mẫu; nó kiểm tra những ràng buộc cấu trúc/kiểu cần thỏa trên các đường điều khiển được phép. Tuy nhiên, nó không chứng minh lỗi logic, race condition hoặc ngoại lệ hợp lệ là không tồn tại.

## 9. Phiên bản class file và quy tắc verification

Phạm vi quan trọng theo **JVMS `4.10.1`**:

- Class file phiên bản **50.0 trở lên** (bắt đầu từ Java 6) được xác minh theo cơ chế **type checking** như đặc tả mô tả.
- Có một quy định tương thích đặc biệt: **chỉ với version 50.0**, khi type checking thất bại, một bản triển khai JVM có thể lựa chọn fallback sang **verification by type inference** theo quy tắc đặc tả. Đây không phải hành vi mà ứng dụng được quyền yêu cầu cho mọi phiên bản.
- Với class file thuộc định dạng cũ hơn, việc xác minh có quy định cho cơ chế **type inference**, trong những JVM thuộc phạm vi áp dụng tương ứng.
- Đối với **class file version mới hơn** (ví dụ class Java 17 biên dịch mặc định, major 61), không nên dựa vào fallback riêng của version 50.0 để chạy class thiếu frame bắt buộc ở các đích rẽ nhánh.

Ví dụ trong `javap -v` sau khi chạy:

```bash
javac --release 17 FrameDemo.java
javap -v FrameDemo
```

Phần đầu mô tả class file có **major version: 61** đối với target Java 17. Đây là **phiên bản định dạng class file**, không phải số frame trong phương thức. Phần `StackMapTable` nằm trong từng `Code` attribute phù hợp.

**Không suy diễn “không có `StackMapTable` là luôn sai”.** Nếu phương thức đủ đơn giản và initial frame ngầm định đáp ứng mọi yêu cầu, số entry tường minh có thể bằng 0. Ngược lại, với nhánh điều khiển/handler cần frame, thiếu hoặc sai frame có thể khiến verifier từ chối class.

## 10. `VerifyError` xảy ra khi nào?

`java.lang.VerifyError` là một loại `LinkageError`. Nó có thể được ném khi JVM cố xác minh và phát hiện class file có bytecode vi phạm ràng buộc cần thiết. Thời điểm quan sát lỗi có thể là khi nạp/liên kết/sử dụng lớp tùy hoạt động của runtime và cách tổ chức kiểm tra.

Một số dạng thông báo thường gặp từ triển khai JVM:

```text
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Inconsistent stackmap frames at branch target ...
```

**Các dòng này là mẫu thông báo minh họa**, không phải stdout tất yếu của `FrameDemo`, cũng không phải văn bản ổn định bắt buộc trong mọi JVM.

### 10.1. Những nguyên nhân thực tế

1. **Chỉnh opcode nhưng giữ frame cũ.** Chèn một instruction làm bytecode offsets đổi; frame trước đó còn trỏ vị trí không đúng.
2. **Thay cấu trúc nhánh nhưng không cập nhật trạng thái.** Thêm nhánh mới dẫn vào điểm hội tụ mà stack hoặc locals không tương thích.
3. **Thay kiểu của giá trị trên stack.** Một instruction dùng opcode reference trong khi đường đi cung cấp primitive.
4. **Sinh mã constructor sai.** Dùng reference `Uninitialized` trước bước khởi tạo hợp lệ.
5. **Cập nhật exception table nhưng quên handler frame.** Handler mới cần trạng thái kiểu phù hợp.
6. **Sinh class file không phù hợp major version.** Công cụ tạo bytecode dùng luật frame lỗi thời hoặc đặt metadata không hợp lệ.
7. **Class instrumented sai.** Agent/transformer thay đổi code hoặc control flow, nhưng không tái tính các stack map frame và giới hạn locals/stack khi cần.

**Không phải mọi lỗi class file là `VerifyError`.** Sai cấu trúc class file nghiêm trọng có thể gây `ClassFormatError`; class biên dịch cho runtime quá cũ có thể gây `UnsupportedClassVersionError`; lỗi tìm class có thể là `ClassNotFoundException` hoặc `NoClassDefFoundError` tùy ngữ cảnh. Cần đọc **loại lỗi và thông điệp thật** trước khi sửa.

### 10.2. Quy trình debug an toàn

1. Xác định **class chính xác** bị từ chối (đừng vội sửa source khác chỉ vì stack trace có nhiều lớp).
2. Kiểm tra runtime và target bytecode: `java -version`, compiler target, `javap -v` để xem major version.
3. Nếu class bị transformer/agent chỉnh sửa, so sánh **class gốc** và **class đã biến đổi** trong môi trường phát triển; xác định các instruction/branch/handler mới.
4. Dùng `javap -v -p <ClassName>` hoặc công cụ kiểm tra class file tương thích để đối chiếu bytecode offsets, `StackMapTable` và exception table.
5. Tại offset lỗi, mô phỏng **kiểu** mà instruction trước đó tạo ra; so với trạng thái mà frame đích công bố.
6. Sửa logic biến đổi để cập nhật **control-flow targets, frame states, max stack, max locals** theo API thư viện sinh bytecode đang dùng.
7. Build và chạy lại bằng **JDK mục tiêu** để JVM xác minh output cuối.

Tránh chữa triệu chứng bằng cách tìm cách **tắt bytecode verification** trong môi trường thật. Điều đó che giấu lỗi class file và có thể không khả dụng trên các runtime mới. Mục tiêu đúng là tạo bytecode cùng metadata hợp lệ.

## 11. StackMapTable khi chỉnh bytecode bằng ASM, Byte Buddy hoặc agent

Bài này không hướng dẫn triển khai một transformer cụ thể, nhưng cần hiểu hậu quả của việc thay mã:

```text
Original method:
  Code instructions
  Branch targets
  Exception handlers
  StackMapTable states

Transformer:
  insert logging / guards / branches / try-catch
           |
           v
New control-flow graph
           |
           v
Recompute or carefully update:
  instruction offsets
  branch and handler targets
  frame states
  max_stack / max_locals
           |
           v
Valid transformed .class
```

Một phép thay đổi **không đổi luồng điều khiển** vẫn có thể thay đổi trạng thái stack/local ở những điểm cụ thể. Khi transformer thay đổi bytecode, đừng cho rằng “chỉ thêm một println” luôn giữ nguyên StackMapTable hợp lệ.

Các thư viện như **ASM** cung cấp cơ chế tính toán frame/maxs trong những cấu hình thích hợp (ví dụ hướng tiếp cận với `ClassWriter.COMPUTE_FRAMES` trong ASM). Tuy vậy, việc tính toán này cần biết các **kiểu lớp chung**, hierarchy và classpath phù hợp. Nếu resolver không tìm được lớp cần thiết hoặc class loader khác với runtime đích, quá trình tính frame có thể thất bại hoặc không diễn đạt đúng quan hệ kiểu cần thiết.

Điểm quan trọng hơn tên API: **output cuối phải được JVM verifier chấp nhận**. Khi nâng cấp JDK, thay target class version, tạo branch mới hoặc đổi cấu trúc constructor, nên kiểm chứng lại class đã sinh.

### Phân biệt metadata verifier với metadata debug, GC và JIT

| Dữ liệu | Mục đích |
| --- | --- |
| `StackMapTable` trong class file | Khai báo trạng thái **verification type** tại bytecode offsets của phương thức |
| `LineNumberTable` | Ánh xạ bytecode offsets tới số dòng nguồn để debug/stack trace |
| `LocalVariableTable` | Tên, phạm vi và descriptor của biến cục bộ phục vụ debug |
| `max_stack` và `max_locals` | Giới hạn tài nguyên cho operand stack/local variable slots của một frame phương thức |
| **GC stack maps / oop maps** của một JVM | Dữ liệu nội bộ về vị trí reference tại các điểm runtime phù hợp để hỗ trợ GC |
| **JIT compiler metadata** | Thông tin phục vụ tối ưu và thực thi mã máy đã biên dịch |

Hai thuật ngữ cùng có chữ **stack map** không nhất thiết chỉ cùng một cấu trúc. Đặc biệt, **`StackMapTable` trong `.class` không phải trực tiếp bản đồ GC roots ở safe point** và không mô tả trạng thái thực tế của từng thread tại thời điểm chạy.

## 12. Ví dụ tư duy: phân biệt lỗi verification và exception hợp lệ

Xét hai tình huống:

**Tình huống A — mã Java hợp lệ nhưng có thể ném ngoại lệ:**

```java
static int divide(int a, int b) {
    return a / b;
}
```

Nếu `b == 0`, chương trình có thể ném `ArithmeticException` ở runtime. Đây **không** phải bằng chứng bytecode có kiểu sai. Verification bảo đảm phép `idiv` được dùng trên kiểu phù hợp, chứ không bảo đảm số chia luôn khác 0.

**Tình huống B — bytecode sai kiểu:**

```text
Giả định bytecode:
  iconst_1       // đẩy int lên operand stack
  invokevirtual  // giả định lời gọi yêu cầu receiver reference ở vị trí này
```

Nếu không có receiver reference thích hợp và chữ ký/stack operand hợp lệ, bytecode vi phạm quy tắc kiểu/stack. Đây là **lỗi cấu trúc hoặc xác minh**, khác với `ArithmeticException` hợp lệ ở A.

Tương tự, `String s = null; s.length();` là mã Java có thể biên dịch và có thể ném `NullPointerException` khi chạy. `StackMapTable` có thể xác nhận slot `s` thuộc nhóm **reference type**, nhưng **không chứng minh runtime reference đó khác null**. Verifier xử lý an toàn kiểu, không chứng minh tất cả điều kiện nghiệp vụ.

## 13. Những nhầm lẫn phổ biến

1. **“StackMapTable là call stack của JVM.”** Sai: nó là attribute trong class file, mô tả trạng thái kiểu theo bytecode offsets, không lưu lịch sử lời gọi lúc chạy.
2. **“Mỗi dòng Java tương ứng một frame.”** Sai: frame gắn với các vị trí bytecode phục vụ verifier; không phải cứ mỗi source line có một entry.
3. **“Frame ghi giá trị thật của biến.”** Sai: frame ghi verification type, không lưu giá trị như 42, `"hello"` hay PID.
4. **“StackMapTable kiểm tra runtime null-safety.”** Sai: reference có thể mang `null`; verifier không ngăn mọi `NullPointerException`.
5. **“Một phương thức thiếu StackMapTable là chắc chắn invalid.”** Sai: có initial frame ngầm định và quy tắc cho attribute ngầm định có 0 entry ở class version phù hợp.
6. **“Một frame có thể chèn vào bất kỳ byte offset nào.”** Sai: frame phải đáp ứng quy tắc offset/instruction/control-flow của verifier.
7. **“`Top` đồng nghĩa với `Object`.”** Sai: `Top` là verification type đặc biệt; `Object(java/lang/Object)` là một reference verification type cụ thể.
8. **“`Uninitialized` chính là null.”** Sai: uninitialized reference liên quan object đang trong quá trình tạo; `Null` là null reference đặc biệt.
9. **“`max_stack` lớn là đủ sửa mọi `VerifyError`.”** Sai: kích thước đủ không tự sửa kiểu stack, local, branch target hoặc initialization state.
10. **“Thêm bytecode không đổi line number nên không cần cập nhật frame.”** Sai: frame dựa trên **offset và luồng bytecode**, không dựa vào line number.
11. **“StackMapTable là dữ liệu GC/JIT runtime.”** Sai: nó thuộc giai đoạn class file verification; GC/JIT có metadata nội bộ khác.
12. **“`javap -c` và `javap -v` cho cùng mức thông tin.”** `-c` tập trung vào instruction; `-v` cung cấp chi tiết attribute, trong đó có `StackMapTable` khi được ghi.

## 14. Bài tập tự kiểm tra (kèm đáp án)

**Câu 1.** `StackMapTable` được gắn ở đâu?

**Đáp án:** Trong bảng attributes của **`Code` attribute** thuộc một phương thức có bytecode, tối đa một `StackMapTable` cho mỗi `Code`.

**Câu 2.** Vì sao `entries[0]` không phải frame ở offset đầu tiên của phương thức?

**Đáp án:** Vì **initial frame** được verifier tính ngầm định từ method descriptor và các quy tắc phương thức; entry đầu là frame tường minh kế tiếp.

**Câu 3.** Phương thức `static void f(long x, Object y)` cần bao nhiêu local slots tối thiểu cho tham số?

**Đáp án:** Ít nhất **3 slots**: `long` chiếm slot 0–1, `Object` ở slot 2. Với phương thức `static` không có receiver `this`.

**Câu 4.** Tag nào dùng cho reference null? Tag nào cho `this` chưa khởi tạo trong constructor?

**Đáp án:** `Null_variable_info` tag **5**; `UninitializedThis_variable_info` tag **6**.

**Câu 5.** Frame `same_frame` có thể biểu diễn operand stack chứa hai `int` được không?

**Đáp án:** Không. `same_frame` kế thừa locals nhưng yêu cầu operand stack **rỗng**. Nếu trạng thái cần stack chứa hai giá trị, phải mã hóa bằng dạng phù hợp.

**Câu 6.** Tại sao sau khi thêm một `if` vào phương thức bằng transformer, class có thể bị `VerifyError`?

**Đáp án:** Vì có target luồng điều khiển mới và các trạng thái locals/operand stack tại target cần khớp; frame hoặc offsets cũ có thể không còn hợp lệ.

**Câu 7.** `StackMapTable` có ngăn `NullPointerException` trong `text.length()` khi `text == null` không?

**Đáp án:** Không. Reference null vẫn có thể được lưu trong một slot reference; dereference ở runtime mới ném `NullPointerException`.

**Câu 8.** Có phải cả ba offset của những frame tường minh đều bằng tổng các `offset_delta` tương ứng?

**Đáp án:** Không. Frame tường minh đầu tiên ở `offset_delta`; mỗi frame tiếp theo ở `previous_offset + offset_delta + 1`.

**Câu 9.** Dùng công cụ JDK nào xem `StackMapTable`?

**Đáp án:** `javap -v -p TenClass` sau khi đã biên dịch; có thể đọc cả bytecode, exception table và các thuộc tính của phương thức.

**Câu 10.** Vì sao output `javap -v` chỉ có một số frame dù phương thức có hàng chục bytecode instructions?

**Đáp án:** Frame được lưu tại những offset cần thiết, thường là đầu basic block; các instruction khác được verifier kiểm tra bằng các quy tắc type transition.

## 15. Tổng kết và tài liệu chuẩn

**StackMapTable là hợp đồng trạng thái kiểu của phương thức ở cấp bytecode.** Nó xuất hiện bên trong `Code` attribute, lưu các frame tường minh được nén, mỗi frame mô tả kiểu của locals và operand stack ở một offset. Verifier kết hợp initial frame ngầm định, frame ở các điểm rẽ nhánh/exception và quy tắc của từng opcode để bảo đảm class file không vi phạm các ràng buộc cấu trúc/kiểu mà JVM yêu cầu.

Nếu chỉ ghi nhớ một quy trình khi sửa bytecode:

```text
Đổi instructions / branches / handlers
             ↓
Kiểm tra lại control-flow graph
             ↓
Tính lại trạng thái locals + operand stack ở các điểm cần thiết
             ↓
Sinh/cập nhật frame và giới hạn stack/locals hợp lệ
             ↓
Đọc output bằng javap -v
             ↓
Kiểm chứng class trên JVM mục tiêu
```

Tài liệu đặc tả chính thức:

- [JVMS `4.7.3` — The Code Attribute (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): nơi chứa bytecode, exception table và attributes của phương thức.
- [JVMS `4.7.4` — The StackMapTable Attribute (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.4): cấu trúc frame, verification_type_info, kiểu frame và cách tính offset.
- [JVMS `4.10.1` — Verification by Type Checking (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.10.1): quy tắc xác minh bằng kiểm tra kiểu và initial frame.
- [JVMS `2.6` — Frames (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): local variables và operand stacks của JVM.
- [`javap` tool documentation (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): các cờ `-c`, `-v`, `-p` để đọc class file.

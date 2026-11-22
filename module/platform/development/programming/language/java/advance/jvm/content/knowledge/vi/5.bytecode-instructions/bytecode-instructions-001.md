# Máy dựa trên ngăn xếp: opcode, toán hạng và bộ đếm lệnh

## 1. Từ một dòng Java tới các bước thực thi trong JVM

Khi đọc Java, chúng ta thường thấy một biểu thức như:

```java
int result = (a + b) * 2;
```

Trong chương trình được biên dịch thông thường, JVM thực thi một chuỗi **lệnh bytecode** mô tả các bước nhỏ: lấy giá trị từ biến, đưa lên **operand stack**, cộng hai số, đẩy hằng số 2, nhân, rồi lưu kết quả về biến. JVM vì thế được gọi là **máy ảo dựa trên ngăn xếp** (*stack-based virtual machine*).

Một ví dụ bytecode mô hình hóa biểu thức trên:

```text
iload_0      ; đưa giá trị biến cục bộ a lên operand stack
iload_1      ; đưa giá trị biến cục bộ b lên operand stack
iadd         ; lấy hai int trên đỉnh stack, cộng, đẩy kết quả
iconst_2     ; đẩy hằng số int 2
imul         ; lấy hai int trên đỉnh stack, nhân, đẩy kết quả
istore_2     ; lấy kết quả khỏi stack, ghi vào biến cục bộ result
```

Ba ý niệm xuyên suốt bài:

- **Opcode** (*operation code*) cho biết JVM phải làm thao tác gì: `iadd`, `iload_0`, `goto`, `invokevirtual`…
- **Toán hạng** (*operand*) là dữ liệu mà thao tác sử dụng: có thể là các giá trị đã có trên **operand stack**, hoặc các byte **đi kèm opcode** như chỉ số biến cục bộ, số hằng, chỉ số constant pool, độ lệch nhảy.
- **Program counter (PC)** giúp luồng thực thi xác định **instruction bytecode hiện tại**. Nhảy nhánh thay đổi nơi thực thi tiếp theo; lời gọi phương thức tạo frame mới cho phương thức được gọi.

Đây là mô hình máy ảo ở cấp **bytecode**, không có nghĩa CPU thật của máy tính phải chạy bằng ngăn xếp. Một JVM như HotSpot có thể thông dịch bytecode hoặc biên dịch JIT thành mã máy sử dụng thanh ghi CPU. Ngữ nghĩa cần giữ đúng là ngữ nghĩa do đặc tả JVM quy định.

## 2. Các bộ phận phải phân biệt: frame, locals, operand stack và PC

Một JVM thread có **JVM stack** riêng; mỗi lời gọi phương thức tạo một **frame** mới. Frame chứa thông tin liên quan đến một lần gọi, trong đó có **mảng biến cục bộ** và **operand stack**. Theo JVMS, mỗi thread cũng có **PC register** riêng.

```text
Thread đang chạy
├── PC register: địa chỉ instruction JVM đang thực thi
└── JVM stack (ngăn xếp các lời gọi phương thức)
    ├── Frame của method hiện tại (trên cùng)
    │   ├── Local variables: slot 0, 1, 2, ...
    │   ├── Operand stack: [..., phần tử đỉnh]
    │   └── Tham chiếu tới runtime constant pool của lớp
    ├── Frame của method gọi nó
    └── Frame cũ hơn
```

### 2.1. JVM stack khác operand stack

Hai khái niệm có cùng chữ “stack” nhưng khác trách nhiệm:

| Thành phần | Chứa gì? | Thời điểm thay đổi |
| --- | --- | --- |
| **JVM stack** của một thread | Các **frame** của những lời gọi phương thức đang hoạt động | Gọi phương thức → tạo/đẩy frame; return → frame tương ứng kết thúc |
| **Operand stack** bên trong một frame | Các giá trị trung gian mà các instruction đang thao tác | `iload` đẩy giá trị, `iadd` lấy toán hạng, `istore` lấy kết quả |
| **Local variables** bên trong frame | Các slot chứa tham số và giá trị cục bộ của phương thức | `iload` đọc, `istore` ghi, `iinc` cập nhật slot |
| **PC register** của thread | Vị trí instruction JVM đang được thực thi trong ngữ cảnh hiện tại | Tiến tới instruction kế tiếp, nhảy nhánh, thực thi lời gọi… |

Đừng đồng nhất **operand stack** với cấu trúc dữ liệu `java.util.Stack` hoặc với **call stack** hiển thị trong stack trace. `java.util.Stack` là một lớp thư viện; hai cấu trúc thực thi là những phần của mô hình JVM.

### 2.2. Local variables là các slot có chỉ số

Phương thức `static int sum(int a, int b)` thường đặt `a` ở local slot 0 và `b` ở slot 1. Một phương thức instance thường có `this` ở slot 0; các tham số bắt đầu từ các slot tiếp theo. Các giá trị `long` và `double` chiếm **hai local variable slots**, trong khi phần lớn kiểu khác chiếm một slot.

Ví dụ khái niệm:

```text
static int sum(int a, int b)
locals:
  [0] a = 3
  [1] b = 4
  [2] result (được ghi sau)

int Person.compute(int n)
locals:
  [0] this   (reference)
  [1] n      (int)
```

Chỉ số slot không phải tên biến nguồn. Compiler có thể sử dụng lại slot tại các phạm vi khác nhau. Khi `javap -c` hiển thị `iload_0`, con số `0` là **local index**, không phải giá trị của biến.

### 2.3. Operand stack là vùng làm việc tạm thời

Các instruction lấy/đẩy giá trị theo quy tắc **LIFO (last in, first out)**. Dùng ký hiệu sau để mô phỏng:

```text
[]            = stack rỗng
[3]           = giá trị 3 ở đỉnh
[3, 4]        = 4 ở đỉnh, 3 ngay dưới
[7]           = kết quả sau khi iadd lấy 3 và 4
```

Mỗi phương thức có `max_stack` trong `Code` attribute để giới hạn độ sâu operand stack cần thiết; `max_locals` giới hạn số slot local. Đây là **giới hạn của phương thức**, không phải số lượng luôn tồn tại ở mọi thời điểm.

Một `int` hoặc tham chiếu thường chiếm một đơn vị stack; `long` và `double` thuộc **category 2** và chiếm hai đơn vị. Các instruction `dup`, `pop`, `swap` có quy tắc chặt về category nên không thể tùy tiện đảo những giá trị hai đơn vị như giá trị một đơn vị.

## 3. Một instruction JVM được mã hóa như thế nào?

Mô hình lệnh:

```text
+-----------+-------------------------------+
| opcode    | operand bytes nếu lệnh cần    |
| 1 byte    | 0, 1, 2 hoặc nhiều byte       |
+-----------+-------------------------------+
```

Opcode được mã hóa bằng **một byte** và cho biết loại thao tác. Nhiều instruction có các **operand bytes** đi ngay sau opcode; độ dài instruction không cố định. Những byte này có thể biểu diễn số tức thời, chỉ số local, chỉ số vào constant pool hoặc độ lệch nhảy.

Ví dụ:

| Mnemonic | Ý nghĩa | Operand mã hóa sau opcode? |
| --- | --- | --- |
| `iconst_2` | Đẩy hằng int 2 | Không |
| `iload_0` | Đọc local slot 0 kiểu int và đẩy lên stack | Không: chỉ số 0 nằm trong tên opcode |
| `iload 5` | Đọc local slot 5 kiểu int | Có: chỉ số local |
| `bipush 100` | Đẩy số nguyên 100 từ immediate dạng signed byte | Có: một byte |
| `sipush 1000` | Đẩy immediate dạng signed short | Có: hai byte |
| `ldc #k` | Nạp hằng phù hợp từ runtime constant pool | Có: index tới constant pool |
| `iinc 2, 1` | Tăng local int slot 2 thêm 1 | Có: local index và signed increment |
| `if_icmpge target` | So sánh hai int rồi nhảy khi điều kiện thỏa | Có: nhánh tương đối (signed offset) |
| `invokestatic #k` | Gọi phương thức static qua symbolic reference | Có: index vào constant pool |

**Hai nghĩa của “toán hạng” phải được tách rõ:**

1. **Toán hạng của phép tính ở runtime:** chẳng hạn `iadd` lấy **hai giá trị int đã có trên operand stack**. Bytecode của `iadd` không chứa trực tiếp hai số đó.
2. **Toán hạng được mã hóa trong instruction:** chẳng hạn `bipush 100` có byte chứa 100, `iload 5` chứa local index, `goto` chứa branch displacement.

Do vậy câu “`iadd` không có operands” chỉ đúng khi nói về **operand bytes sau opcode**. Về **ngữ nghĩa tính toán**, `iadd` vẫn cần hai toán hạng trên stack.

### 3.1. Mnemonic không phải bytecode thô

`iload_0`, `iadd` và `invokevirtual` là **tên dễ đọc** của opcode trong bản disassembly. Công cụ `javap` biến opcode bytes thành mnemonic và in thêm operand dưới dạng số, tên lớp/phương thức hoặc comment đã giải quyết từ constant pool.

Với `javap -c`:

```text
  0: iload_0
  1: iload_1
  2: iadd
```

Các số **0, 1, 2** ở đầu dòng là **bytecode offsets**, không phải opcode và cũng không phải số dòng Java. Việc offset đi từ 0 → 1 → 2 trong ví dụ là do cả ba instruction đều dài một byte.

### 3.2. Các cách nạp hằng số khác nhau

- `iconst_m1`, `iconst_0` … `iconst_5`: nạp các hằng int rất nhỏ, không cần operand bytes.
- `bipush`, `sipush`: immediate signed 8-bit / 16-bit, kết quả được đẩy như `int`.
- `ldc`: nạp một hằng được hỗ trợ từ constant pool, ví dụ chuỗi hoặc số.
- `ldc_w`: dạng index constant pool lớn hơn `ldc`.
- `ldc2_w`: dùng với hằng category-2 như `long` và `double` theo quy tắc instruction.

Compiler chọn dạng thích hợp; không nên suy luận một câu lệnh `int n = 100;` bắt buộc phải sinh `bipush` trên mọi compiler hay mọi cách tối ưu.

### 3.3. Không phải instruction nào cũng có độ dài cố định

Các instruction như `tableswitch` và `lookupswitch` có **padding** để căn chỉnh dữ liệu nhảy và mang nhiều cặp/offset. `wide` sửa cách giải mã operand của một số instruction liên quan local variables hoặc `iinc` để hỗ trợ index/counter lớn. `goto_w` có branch offset rộng hơn `goto`.

Hệ quả: **PC không tăng một số cố định sau mọi opcode**. Nếu một instruction dài 3 byte và luồng đi tuần tự, offset kế tiếp thường cách 3 byte; nếu có nhánh, PC hướng tới một vị trí khác hoàn toàn.

## 4. Các nhóm opcode cốt lõi của một máy dựa trên ngăn xếp

| Nhóm | Opcode tiêu biểu | Điều thay đổi |
| --- | --- | --- |
| Nạp hằng | `iconst_0`, `bipush`, `ldc`, `aconst_null` | Đẩy giá trị lên operand stack |
| Nạp local | `iload`, `aload`, `lload`, `iload_0` | Đọc local slot → đẩy lên stack |
| Lưu local | `istore`, `astore`, `lstore`, `istore_1` | Lấy giá trị từ stack → ghi local slot |
| Số học | `iadd`, `isub`, `imul`, `idiv`, `ladd` | Lấy toán hạng, tính, đẩy kết quả |
| Chuyển kiểu | `i2l`, `l2i`, `d2i` | Lấy giá trị, chuyển theo quy tắc JVM, đẩy kết quả |
| Quản lý stack | `pop`, `dup`, `swap`, `dup2` | Sắp xếp/nhân bản/hủy giá trị stack theo category |
| So sánh/nhánh | `ifeq`, `if_icmpgt`, `ifnull`, `goto` | Đọc điều kiện từ stack, có thể đổi vị trí thực thi |
| Lời gọi/return | `invokestatic`, `invokevirtual`, `invokeinterface`, `ireturn`, `return` | Truyền tham số, tạo/hoàn tất lời gọi phương thức |
| Trường | `getstatic`, `putstatic`, `getfield`, `putfield` | Đọc/ghi field, tiêu thụ/đẩy reference và giá trị |
| Đối tượng/mảng | `new`, `newarray`, `anewarray`, `iaload`, `iastore`, `arraylength` | Tạo đối tượng, truy cập mảng, dùng reference |
| Kiểm tra/ngoại lệ | `checkcast`, `instanceof`, `athrow` | Kiểm tra kiểu reference hoặc ném ngoại lệ |
| Đồng bộ | `monitorenter`, `monitorexit` | Thao tác monitor theo quy tắc JVM |

Các tiền tố thường gặp thể hiện loại giá trị theo JVM: `i` cho `int`, `l` cho `long`, `f` cho `float`, `d` cho `double`, `a` cho **reference** trong các instruction như `aload`/`astore`. Nhưng **không phải mọi instruction có tiền tố `a` đều cùng mẫu**; hãy đọc định nghĩa opcode cụ thể.

Đừng hiểu bảng như danh sách **toàn bộ** bytecode JVM. Mục đích là nhận ra cách các instruction thao tác trên locals, operand stack và control flow; các lệnh chuyên biệt có thêm điều kiện về kiểu, cấu trúc và ngoại lệ.

## 5. Mô phỏng chính xác `iload`, `iadd`, `imul` và `istore`

Giả sử phương thức static có hai tham số:

```java
static int combine(int a, int b) {
    int result = (a + b) * 2;
    return result;
}
```

Với bytecode điển hình từ `javac` trên Java 17:

```text
0: iload_0
1: iload_1
2: iadd
3: iconst_2
4: imul
5: istore_2
6: iload_2
7: ireturn
```

Giả sử gọi `combine(3, 4)`. Trước instruction đầu tiên, locals chứa `a = 3` và `b = 4`, operand stack rỗng.

| PC offset | Instruction | Stack trước → sau (đỉnh bên phải) | Locals liên quan |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `[] → [3]` | `slot0=3` |
| 1 | `iload_1` | `[3] → [3,4]` | `slot1=4` |
| 2 | `iadd` | `[3,4] → [7]` | Không đổi |
| 3 | `iconst_2` | `[7] → [7,2]` | Không đổi |
| 4 | `imul` | `[7,2] → [14]` | Không đổi |
| 5 | `istore_2` | `[14] → []` | `slot2=14` |
| 6 | `iload_2` | `[] → [14]` | `slot2=14` |
| 7 | `ireturn` | `[14] → []` trong callee | Trả `14` cho caller |

Tại **offset 2**, `iadd` lấy hai số theo thứ tự trên operand stack và đẩy tổng. Tại **offset 4**, `imul` lấy `7` và `2` rồi đẩy `14`. Tại **offset 5**, `istore_2` làm operand stack rỗng bằng cách lưu `14` vào local slot 2.

Với lệnh `ireturn`, giá trị được chuyển thành kết quả của lời gọi phương thức: caller nhận `14` tại vị trí tương ứng trên **operand stack của caller**, còn frame callee kết thúc. Không có một operand stack dùng chung cho tất cả phương thức.

### 5.1. Vì sao `max_stack = 2` ở phương thức này?

Trong bảng, độ sâu lớn nhất của operand stack là **2 đơn vị**: `[3, 4]` hoặc `[7, 2]`. `max_locals` cần **3 slots** để chứa `a`, `b` và `result`. `javap -v` thường hiển thị cho `combine` metadata tương ứng:

```text
stack=2, locals=3, args_size=2
```

Dòng trên thuộc kiểu output của `javap` cho phiên bản `javac` thông thường; nếu xem output thực tế, nên đối chiếu cả đoạn code thay vì dựa vào một bản in từ môi trường khác.

**Không tính `max_stack` bằng số biến của chương trình.** Nó là mức stack tối đa dùng khi thực thi bytecode trong frame, không phải số lượng biến khai báo hoặc số frame của call stack.

### 5.2. Thử biểu thức có toán tử không giao hoán

`isub` và `idiv` cần chú ý thứ tự giá trị. Nếu stack là `[a, b]` (b ở đỉnh), thì `isub` tính `a - b` và `idiv` tính `a / b` theo quy tắc chia số nguyên JVM.

Ví dụ:

```text
iconst_5     → [5]
iconst_2     → [5, 2]
isub         → [3]       // 5 - 2, không phải 2 - 5
```

Không mô tả stack như “lấy đỉnh làm toán hạng trái” một cách tổng quát; thứ tự operand của từng instruction được đặc tả rõ.

## 6. PC register và bytecode offset: điều gì đang được đếm?

**Program Counter (PC) register** là trạng thái riêng của **mỗi JVM thread**. Trong mô hình của JVMS, khi thread đang thực thi phương thức **không phải native**, PC chứa địa chỉ của instruction JVM đang được thực thi. Nếu phương thức hiện tại là **native**, giá trị PC register **không được đặc tả**.

Điều này không phải lời cam kết rằng PC là một biến Java đọc trực tiếp được, cũng không có nghĩa ứng dụng nên suy đoán số PC từ stack trace. PC là một thành phần của **mô hình thực thi JVM**, không phải API truy xuất thông thường như `Thread.currentThread()`.

### 6.1. Đọc ba cột trong output `javap`

```text
  0: iload_0
  1: iload_1
  2: iadd
  3: iconst_2
  4: imul
  5: istore_2
  6: iload_2
  7: ireturn
```

- **Bên trái dấu `:`:** bytecode offset, tính bằng byte kể từ đầu `code[]` của phương thức.
- **Bên phải:** opcode mnemonic (và operand nếu có).
- **PC:** về mặt logic chỉ tới instruction JVM đang thực thi của thread, nên có thể liên hệ với những offset này khi phân tích bytecode.

Không nhầm **bytecode offset** với **chỉ số instruction**. Nếu instruction tại offset 1 dài 3 byte, instruction kế tiếp có thể bắt đầu tại offset 4. Các offset không nhất thiết tăng đều một đơn vị.

### 6.2. Chạy tuần tự, nhảy và lời gọi phương thức

Trong một đường chạy không có nhánh, JVM tiến tới instruction kế tiếp. Nhưng có ba tình huống cơ bản khác:

1. **Rẽ nhánh:** `if…` hoặc `goto` chuyển điều khiển tới target instruction; PC tương ứng với đích đã chọn.
2. **Gọi phương thức:** `invoke…` thiết lập lời gọi mới, một frame của phương thức được gọi được kích hoạt; khi nó return, caller tiếp tục tại điểm sau lời gọi theo ngữ nghĩa thực thi.
3. **Ngoại lệ:** khi lỗi/`athrow` xảy ra, điều khiển có thể chuyển tới exception handler hợp lệ; nếu không có handler trong frame thì frame có thể kết thúc bất thường và việc tìm handler tiếp tục ở caller.

PC không “cộng đều cho đến khi chạm cuối tệp class”. Mỗi phương thức có `code[]` riêng, và JVM có quy tắc cụ thể để giải mã instruction, giải quyết branch target và chuyển control flow.

### 6.3. JVM đa luồng có một PC hay nhiều PC?

Mỗi JVM thread có **PC register riêng**, vì các thread có thể đang thực thi những instruction ở các phương thức khác nhau hoặc các vị trí khác nhau của cùng một phương thức. JVM stack và operand stack trong các frame cũng gắn với thread tương ứng.

```text
Thread A                             Thread B
PC → methodA, offset 12             PC → methodB, offset 5
JVM stack A                         JVM stack B
  frame methodA                       frame methodB
    locals / operand stack              locals / operand stack
```

Hai thread có thể chia sẻ heap và đối tượng, nhưng **không chia sẻ PC register hay frame đang thực thi**. Bộ lập lịch có thể tạm dừng/chạy lại một thread; hành vi scheduling của hệ điều hành và triển khai runtime không thay đổi quy tắc PC trong mô hình JVM.

## 7. Branch operands: chuyển PC bằng độ lệch tương đối

Nhiều lệnh nhánh như `ifeq`, `if_icmpge` hoặc `goto` dùng **branch offset tương đối**, được tính từ **địa chỉ của opcode đang nhảy**, không phải từ địa chỉ instruction kế tiếp.

Ví dụ sơ đồ có offset giả định:

```text
 0: iconst_0
 1: istore_1
 2: iload_0
 3: ifle       12
 6: iconst_1
 7: istore_1
 8: goto       12
11: nop
12: iload_1
13: ireturn
```

**Đây là sơ đồ minh họa, không khẳng định `javac` thực tế phải sinh đúng chuỗi trên.** Ví dụ nhánh tại offset 3 sang offset 12 có độ lệch logic **12 - 3 = +9** byte. Nếu một `goto` ở offset 8 chuyển tới 12, độ lệch tương ứng là **+4** byte.

`javap` thường in luôn **target offset tuyệt đối** như `ifle 12`, giúp người đọc không cần tự giải mã giá trị signed branch displacement nằm trong class file. Trong bytecode thô, operand branch của `ifle` là một số có dấu **16 bit** (hai byte); `goto_w` dùng offset có dấu 32 bit.

Tại một nhánh có điều kiện, verifier và runtime cần bảo đảm target là điểm hợp lệ của instruction, không rơi vào giữa phần operand bytes của instruction khác. Luồng thực thi phải tuân thủ các quy tắc về kiểu và operand stack tại điểm hội tụ.

### 7.1. `if…` tiêu thụ giá trị trên stack

Ví dụ biểu thức `if (n == 0)` có thể biên dịch thành:

```text
iload_0          ; stack [] → [n]
ifeq target      ; lấy n; nếu n == 0 thì nhảy
```

Sau khi `ifeq` kiểm tra, giá trị `n` đã được **lấy khỏi operand stack** trên cả hai đường; nó không tự nằm lại đó. Một số opcode dùng so sánh **một** giá trị với 0/null (`ifeq`, `ifnull`), trong khi `if_icmp…` so sánh **hai** giá trị int từ stack.

### 7.2. Vòng lặp cần nhảy ngược

Một vòng `for` có thể tạo nhánh về offset thấp hơn để kiểm tra điều kiện lặp. Trong trường hợp này, PC đi đến một instruction **trước đó** chứ không tăng mãi.

```text
[Khởi tạo] → [Kiểm tra điều kiện] → sai → [Thoát vòng]
                  |
                đúng
                  v
              [Thân vòng]
                  |
              [Cập nhật]
                  |
                  +--------→ [Kiểm tra điều kiện]
```

Tùy compiler, `for` có thể sinh `goto` về đầu vòng, hoặc dùng một instruction nhánh có điều kiện để quay lại. Cấu trúc chính vẫn là **control flow graph** có cạnh quay ngược; không phải lệnh “lặp” đặc biệt theo nghĩa mọi vòng đều dùng đúng một opcode.

### 7.3. `tableswitch` và `lookupswitch`

Hai instruction này dùng cho những dạng `switch` thích hợp:

- `tableswitch` mô tả nhiều target qua dải giá trị nguyên tương đối liên tục.
- `lookupswitch` biểu diễn những cặp giá trị khóa/target; thích hợp với những trường hợp khóa thưa theo chiến lược compiler.

Cả hai có padding và branch operands nhiều byte; độ dài phụ thuộc số trường hợp. Không khẳng định mọi `switch` trong Java dùng `tableswitch`; compiler lựa chọn dựa trên ngữ nghĩa, mật độ khóa và chiến lược sinh mã.

## 8. Lời gọi phương thức: truyền argument qua stack và chuyển frame

Xét:

```java
static int twice(int x) {
    return x * 2;
}

static int caller() {
    return twice(4);
}
```

Trong caller, compiler có thể đặt giá trị 4 lên operand stack rồi dùng `invokestatic` để gọi `twice`. Caller cung cấp arguments theo phương thức được mô tả trong **method descriptor**. Khi gọi:

```text
Caller frame:
  ... operand stack [4]
             |
             | invokestatic twice:(I)I
             v
Callee frame twice:
  local slot 0 = 4
  operand stack = []
  ... thực thi iload_0, iconst_2, imul, ireturn ...
             |
             | kết quả 8
             v
Caller frame:
  ... operand stack [8]
```

Những điểm then chốt:

- `invokestatic` lấy các tham số phù hợp từ operand stack của caller.
- Phương thức được gọi chạy với **frame mới**, có locals và operand stack riêng.
- Nếu callee return giá trị `int` bằng `ireturn`, caller nhận giá trị đó vào operand stack của mình.
- Nếu phương thức có kiểu trả về `void`, instruction `return` không đưa giá trị trả về cho caller.
- Với `invokevirtual` hoặc `invokeinterface`, thông thường còn có **receiver reference** cùng arguments trên operand stack; việc liên kết và dispatch phải tuân theo các quy tắc JVM.

Khi gặp `invokevirtual`, tên opcode chưa đủ để biết phương thức cụ thể được dispatch tới implementation nào. Runtime có thể xác định đích theo lớp thực tế của đối tượng và quy tắc gọi phương thức. Một receiver null có thể dẫn tới `NullPointerException`; đó là lỗi runtime hợp lệ, không đồng nghĩa class file có opcode sai.

### 8.1. Descriptor gắn operand stack với chữ ký phương thức

Ví dụ descriptor:

```text
(II)I                    // hai tham số int, trả int
(Ljava/lang/String;)V    // một String reference, trả void
([I)J                   // một int[] reference, trả long
```

`I` biểu diễn `int`, `J` biểu diễn `long`, `V` dùng cho `void` ở kiểu trả về, `L...;` cho class/interface, và `[` cho array.

Verifier dùng các quy tắc này để biết instruction gọi phương thức phải tiêu thụ bao nhiêu giá trị và thuộc loại gì, cũng như giá trị trả về nào sẽ xuất hiện trên stack của caller. Phải tính đúng **category-2 slots** với `long`/`double`.

### 8.2. `invoke…` liên quan constant pool

Đa số lệnh gọi phương thức dùng một **chỉ số tới runtime constant pool** của lớp hiện tại, nơi chứa symbolic reference hay thông tin lời gọi phù hợp. Khi liên kết, JVM giải quyết các tham chiếu theo những quy tắc riêng, có thể dẫn đến các lỗi linkage nếu class/phương thức không hợp lệ hoặc không truy cập được.

Không diễn giải operand của `invokevirtual #k` là “địa chỉ hàm native cố định”. Nó là một tham chiếu theo định dạng class file để JVM có thể liên kết đúng ngữ nghĩa.

## 9. Reference, object và array trong mô hình stack

Máy dựa trên stack không chỉ làm số học. Với object và array, **giá trị tham chiếu** cũng được lưu trong locals và operand stack.

Ví dụ:

```java
String word = "Java";
int size = word.length();
```

Một chuỗi opcode thường liên quan:

```text
ldc #k                   ; tham chiếu String constant
astore_0                 ; lưu reference vào local slot 0
aload_0                  ; đẩy reference lên operand stack
invokevirtual #method    ; gọi String.length() trên receiver
istore_1                 ; lưu int kết quả
```

Dấu `#k` và `#method` biểu thị **constant-pool index** mang tính minh họa. Compiler có thể bố trí local slot khác theo cách biên dịch.

Đối với mảng:

```java
int[] values = new int[2];
values[0] = 9;
int first = values[0];
```

Một phép ghi phần tử `iastore` cần trên operand stack theo thứ tự thích hợp: **array reference**, **index**, **giá trị int**. Phép đọc `iaload` cần **array reference** và **index**, rồi đẩy giá trị đã đọc. Runtime còn kiểm tra null reference, chỉ số mảng và các ràng buộc liên quan; một số thao tác có thể ném `NullPointerException` hoặc `ArrayIndexOutOfBoundsException`.

`aconst_null` đẩy một null reference lên operand stack. Nó là một giá trị có ý nghĩa trong mô hình kiểu reference; opcode không tạo ra một “đối tượng null”. Không được dùng null để gọi instance method mà không gặp kiểm tra runtime tương ứng.

### `new` và trạng thái chưa khởi tạo

Để tạo object, mã bytecode điển hình có chuỗi dạng:

```text
new MyClass
dup
invokespecial MyClass.<init>:()V
```

Lệnh `new` cấp phát đối tượng và đẩy một reference **chưa khởi tạo hoàn chỉnh** theo quy tắc verifier; `dup` thường nhân bản giá trị trên stack để giữ một reference cho phần sử dụng sau constructor; `invokespecial` gọi constructor tương ứng. Việc dùng reference chưa khởi tạo bị ràng buộc chặt; không thể sửa bytecode để bỏ qua các bước khởi tạo hợp lệ rồi mong verifier chấp nhận.

## 10. Ví dụ Java 17+ hoàn chỉnh: xem operand stack và PC bằng `javap`

Tạo tệp **`StackMachineDemo.java`**:

```java
public final class StackMachineDemo {
    static int combine(int a, int b) {
        int result = (a + b) * 2;
        return result;
    }

    static int sumTo(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) {
            total += i;
        }
        return total;
    }

    static String describe(int value) {
        return value >= 0 ? "nonnegative" : "negative";
    }

    public static void main(String[] args) {
        System.out.println("combine(3, 4) = " + combine(3, 4));
        System.out.println("sumTo(4) = " + sumTo(4));
        System.out.println("describe(-1) = " + describe(-1));
    }
}
```

Từ thư mục chứa tệp, chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 StackMachineDemo.java
java StackMachineDemo
```

**Stdout chính xác**:

```text
combine(3, 4) = 14
sumTo(4) = 10
describe(-1) = negative
```

Ba phương thức biểu diễn những hành vi khác nhau:

1. **`combine`:** nạp local, đẩy stack, tính số học, lưu local và return.
2. **`sumTo`:** dùng local `total` và `i`, phép tăng, so sánh, nhảy điều kiện và quay lại vòng lặp; PC không đi thẳng từ offset 0 tới cuối một lần duy nhất.
3. **`describe`:** kiểm tra điều kiện và chọn một trong hai constant String; nhánh quyết định instruction kế tiếp.

Lệnh xem disassembly:

```bash
javap -c -p StackMachineDemo
```

Cờ `-c` in code của phương thức, `-p` hiện cả thành viên không public. Để xem cấu trúc rộng hơn, dùng:

```bash
javap -v -p StackMachineDemo
```

`-v` giúp thấy constant pool, method descriptors, `Code` attribute, `stack`/`locals`, các bảng frame khi có, và các thông tin class file khác.

### 10.1. Kết quả disassembly để đối chiếu với `combine`

Với `javac` của JDK 17 và đúng mã `combine` ở trên, phần method về mặt opcode là:

```text
static int combine(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: iconst_2
     4: imul
     5: istore_2
     6: iload_2
     7: ireturn
```

Phần offset là **độ lệch byte trong `code[]`**; đây không phải thứ tự dòng nguồn. Theo bảng mô phỏng ở mục 5:

```text
PC   instruction     operand stack (sau instruction)
0    iload_0          [3]
1    iload_1          [3,4]
2    iadd             [7]
3    iconst_2         [7,2]
4    imul             [14]
5    istore_2         []
6    iload_2          [14]
7    ireturn          kết thúc frame và trả 14
```

Kiểm tra bản của bạn khi dùng compiler khác: JVM chỉ yêu cầu code hợp lệ và đúng ngữ nghĩa, không bắt mọi compiler sinh **cùng chuỗi instruction** cho một mã nguồn. Việc tối ưu hóa JIT sau đó cũng không thay đổi văn bản bytecode mà `javap` đọc từ tệp `.class`.

### 10.2. Vì sao `sumTo` chứng minh PC có thể quay lại?

`sumTo(4)` thực hiện:

```text
total = 0
i = 1 → total = 1
i = 2 → total = 3
i = 3 → total = 6
i = 4 → total = 10
i = 5 → điều kiện i <= n sai → return 10
```

Khi disassemble, tìm opcode nhóm `if_icmp…`/`if…`, `goto` và `iinc` (chi tiết phụ thuộc compiler). Một số target nhảy sẽ trở lại bytecode offset đã đi qua để tiếp tục vòng; cuối cùng nhánh điều kiện chuyển PC tới vùng return. Đây là cách một **control-flow graph** biểu diễn vòng lặp bằng các instruction cơ bản.

### 10.3. Vì sao `describe` không bắt buộc có “opcode ternary”?

Toán tử `?:` thuộc cú pháp Java. Compiler có thể chuyển nó thành nhánh điều kiện, nạp một hằng String từ constant pool rồi `areturn`. Trong bytecode, không có yêu cầu phải tồn tại một opcode chung tên `ternary`. Mô hình JVM thực thi các bước **so sánh → nhảy → nạp reference → return**.

### 10.4. Tự kiểm tra constant pool

Ở `javap -v`, các operand có dạng `#k` thường tham chiếu tới constant pool. Với lời gọi trong `main`, bạn sẽ thấy các constant-pool entries hoặc thông tin liên quan đến in ra stdout và string concatenation. Trên Java 17, trình biên dịch có thể dùng **`invokedynamic`** cho nối chuỗi; không có gì mâu thuẫn với mô hình stack: arguments vẫn được chuẩn bị và tiêu thụ theo descriptor của lời gọi.

`invokedynamic` là một opcode có quy tắc liên kết riêng; không cần giải thích toàn bộ bootstrap method ở bài này để hiểu rằng nó **đọc operands qua runtime constant pool và tiêu thụ giá trị từ operand stack**.

## 11. Branch offset và kích thước instruction: bài mô phỏng nhỏ

Giả sử có các bytecode offsets sau trong một ví dụ **giả định**:

```text
0:  iconst_1
1:  istore_0
2:  iload_0
3:  ifeq          11
6:  bipush        10
8:  istore_0
9:  goto          13
12: nop
13: iload_0
14: ireturn
```

Sơ đồ này chỉ để hình dung kích thước instruction và đường nhảy; nếu dùng như class file thật, mọi target (kể cả offset 11 được minh họa phía trên) **phải trỏ tới opcode boundary hợp lệ**. Trong chuỗi minh họa này offset 11 rơi vào operand bytes của `goto`, nên **đây là ví dụ về một branch target sai và sẽ không là bytecode hợp lệ**.

Hãy sửa target của `ifeq` thành offset **12**:

```text
3: ifeq 12  // displacement = 12 - 3 = +9
```

Rồi để branch target và stack states đều hợp lệ, cần bảo đảm mọi đường đi hội tụ không vi phạm quy tắc stack/locals. Ví dụ sửa một displacement chỉ khắc phục **vị trí target**, không tự đảm bảo toàn bộ frame/StackMapTable đã đúng.

Cách học an toàn là:

1. Trước hết xác định **bytecode instruction boundary** theo độ dài từng opcode.
2. Tính branch displacement từ **offset opcode nhảy** đến **offset opcode đích**.
3. Kiểm tra **stack height và verification types** tại target trên mọi đường đi.
4. Nếu lớp thuộc định dạng yêu cầu stack map frames, đối chiếu/cập nhật `StackMapTable` phù hợp.

Kỹ thuật này đặc biệt quan trọng khi đọc bytecode do công cụ instrument/transform tạo ra.

## 12. Kiểu dữ liệu ảnh hưởng đến thao tác stack ra sao?

Không thể thay một opcode bằng opcode khác chỉ vì cả hai “đều cộng hai số”:

| Lệnh | Operand trên stack | Kết quả |
| --- | --- | --- |
| `iadd` | Hai `int` | `int` |
| `ladd` | Hai `long` | `long` |
| `fadd` | Hai `float` | `float` |
| `dadd` | Hai `double` | `double` |
| `i2l` | Một `int` | `long` |
| `l2i` | Một `long` | `int` |
| `aload` | Một local có kiểu reference phù hợp | Đẩy reference |
| `astore` | Một reference trên stack | Ghi reference vào local |

Vì category-2 values chiếm hai đơn vị stack, `long`/`double` cần được phân biệt khi tính `max_stack` và xử lý các instruction như `dup2`. Một kiểu như `byte` hay `boolean` thường được biểu diễn và thao tác dưới dạng kiểu `int` trong nhiều instruction JVM, nhưng điều đó không xóa các quy tắc kiểm tra/chuyển đổi riêng ở biên như array stores hoặc descriptors.

### Ví dụ category-2

```java
static long add(long a, long b) {
    return a + b;
}
```

Một dạng bytecode hợp lệ:

```text
lload_0
lload_2
ladd
lreturn
```

Vì mỗi tham số `long` dùng **hai local slots**, `a` bắt đầu tại slot 0 và `b` tại slot 2. Không viết `lload_1` cho tham số `b` trong bố cục này. Khi cả hai `long` nằm trên operand stack, chúng chiếm tổng cộng **bốn đơn vị** stack; phép `ladd` tạo một `long` chiếm hai đơn vị.

Với phương thức instance, slot 0 còn dành cho `this`, nên các chỉ số có thể dịch đi. Hãy xác định chữ ký và modifier của phương thức trước khi suy ra bố cục locals.

## 13. Bộ xác minh bytecode kiểm tra những gì?

JVM verifier kiểm tra các ràng buộc **cấu trúc và kiểu** để không có một luồng instruction hợp lệ nào dùng stack/locals theo cách vi phạm yêu cầu của opcode. Các kiểm tra liên quan:

- `iadd` nhận hai giá trị kiểu verifier phù hợp, không nhận reference như `String`.
- `aload` đọc local slot có giá trị reference hợp lệ; `iload` yêu cầu kiểu số nguyên thích hợp.
- Mọi branch target hợp lệ và các đường đi đến target có trạng thái kiểu tương thích.
- Operand stack không vượt quá `max_stack` theo quy tắc của phương thức.
- Return opcode phù hợp return type trong method descriptor, ví dụ `ireturn` khi trả `int`.
- Receiver/arguments của lời gọi phù hợp quy tắc method invocation.
- Các reference chưa khởi tạo trong constructor được quản lý theo quy tắc verifier.

`StackMapTable` trong class file giúp khai báo **verification type state** tại các offset quan trọng để verifier đối chiếu với luồng bytecode. Nó không phải stack đang chứa các giá trị thực tế tại một thời điểm chạy cụ thể. Phần metadata này hỗ trợ xác minh kiểu, không phải “bộ đếm lệnh”.

**Verifier không chứng minh chương trình không có lỗi nghiệp vụ.** Một phương thức `idiv` được kiểm tra kiểu thành công vẫn có thể ném `ArithmeticException` khi mẫu số bằng 0. Tương tự, reference null hợp lệ về kiểu vẫn có thể ném `NullPointerException` khi dereference.

Nếu bytecode bị biến đổi sai sau biên dịch, JVM có thể từ chối class bằng `VerifyError` hoặc lỗi định dạng/liên kết khác tùy bản chất sai. Hãy điều tra opcode, stack states, offsets, class version và `StackMapTable` trước khi kết luận.

## 14. PC, exception và `athrow`

Các bước thực thi không phải lúc nào cũng tiếp tục từ instruction ngay sau instruction hiện tại. Xét:

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (ArithmeticException ex) {
        return -1;
    }
}
```

Với `b = 0`, phép chia số nguyên tạo `ArithmeticException`. JVM tìm một handler thích hợp theo **exception table** của `Code` attribute. Nếu handler được tìm thấy trong phương thức, điều khiển chuyển tới bytecode offset của handler và operand stack ở handler nhận exception reference theo quy tắc xử lý ngoại lệ.

Khung mô hình:

```text
... iload_0, iload_1, idiv ...
               |
           b == 0
               |
               v
       ArithmeticException
               |
               v
  exception table → handler PC
               |
               v
  handler nhận reference ngoại lệ
               |
               v
  trả về -1
```

Đừng hiểu rằng PC luôn chuyển sang instruction kế tiếp sau `idiv`. Khi exception được ném và có handler, control flow **nhảy tới handler**. Nếu không có handler phù hợp trong frame, việc tìm kiếm tiếp tục qua stack frames của caller; stack trace ghi nhận call frames liên quan chứ không phải một bản log toàn bộ PC offsets đã đi qua.

`athrow` là instruction ném một object reference kiểu ngoại lệ phù hợp. Nó thay đổi control flow tương tự: không chỉ là một thao tác “pop rồi next PC” thông thường.

## 15. JVM dựa trên stack có luôn chậm hơn máy dựa trên thanh ghi không?

**Không thể kết luận chỉ từ mô hình bytecode.** Stack-based ISA của JVM dùng nhiều lệnh ngắn như `iload_0`, `iadd`, `istore_1` và biểu diễn toán hạng ngầm định qua operand stack. Điều đó có thể giúp định dạng bytecode gọn và tạo ra một hợp đồng thực thi tương đối độc lập CPU.

Tuy nhiên, JVM có thể:

- **Thông dịch:** đọc opcode và thực hiện các thao tác tương ứng.
- **Biên dịch JIT:** chuyển vùng bytecode thường chạy thành mã máy phù hợp CPU, tối ưu qua các biểu diễn trung gian, phân bổ thanh ghi, inline, v.v.
- **Tối ưu hóa runtime:** thay đổi chiến lược tùy profile và môi trường triển khai.

Vì vậy **operand stack là mô hình ngữ nghĩa bytecode**; không có yêu cầu mỗi `iadd` luôn biến thành một cặp push/pop thật trên stack phần cứng. Một compiler JIT có thể giữ các giá trị trung gian ở thanh ghi CPU trong mã máy cuối.

Mọi nhận định về hiệu năng cần benchmark workload cụ thể, có warm-up phù hợp, xem cả thời gian khởi động và cách đo. Đếm số instruction bytecode **không đủ** để dự đoán tốc độ thực thi.

## 16. Những sai lầm thường gặp khi đọc `javap`

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`0:` là số dòng Java” | Đây là bytecode offset trong `code[]` của method |
| “Mỗi opcode dài một byte nên instruction luôn dài một byte” | Opcode một byte; operands có thể kéo dài instruction, switch có độ dài biến thiên |
| “`iadd` không có toán hạng” | Không có operand bytes, nhưng **lấy hai giá trị** từ operand stack |
| “`iload_0` nạp hằng 0” | Nó **đọc local slot 0**; `iconst_0` mới đẩy hằng số 0 |
| “`istore_2` lưu vào heap object thứ hai” | Nó ghi **local slot 2** của frame phương thức |
| “Operand stack là call stack” | Operand stack thuộc **mỗi frame**; call stack chứa nhiều frame |
| “`max_stack` là số lần gọi hàm tối đa” | Là độ sâu operand stack tối đa của một method theo đơn vị stack |
| “PC là biến toàn cục của JVM” | Mỗi JVM thread có PC riêng |
| “PC luôn tăng 1” | Instruction có độ dài khác nhau; nhánh, method call, exception đổi control flow |
| “`goto 15` là offset delta +15” | `javap` hiển thị target offset; class file mã hóa branch displacement tương đối |
| “`long` chiếm một local slot như `int`” | `long`/`double` dùng **hai local slots** |
| “Mã JIT thực thi operand stack bằng RAM stack thật ở từng opcode” | JIT có thể ánh xạ ngữ nghĩa bytecode sang thanh ghi/mã máy |
| “Verifier chứng minh mọi input chạy thành công” | Nó kiểm tra an toàn cấu trúc/kiểu, không chứng minh không có exception hợp lệ |

Một lỗi khác là lấy một đoạn `javap` từ phương thức khác rồi suy ngược vị trí local không có chữ ký method. Ví dụ `iload_1` trong instance method có thể là tham số đầu tiên, còn trong static method có thể là tham số thứ hai. Phải xét **có `this` ở slot 0 hay không**, và lưu ý kiểu category-2.

## 17. Tự luyện đọc bytecode

### Bài 1. Đọc operand stack

Cho đoạn bytecode giả định hợp lệ:

```text
0: iconst_3
1: iconst_4
2: iadd
3: iconst_2
4: imul
5: ireturn
```

Hãy viết stack sau từng instruction và kết quả return.

**Đáp án:**

```text
0 → [3]
1 → [3, 4]
2 → [7]
3 → [7, 2]
4 → [14]
5 → return 14
```

### Bài 2. Phân biệt immediate và runtime operand

Cho `bipush 100` và `iadd`. Lệnh nào có operand byte đi kèm? Lệnh nào lấy giá trị từ operand stack?

**Đáp án:** `bipush` có operand byte biểu diễn 100 và đẩy 100. `iadd` không có operand bytes nhưng tiêu thụ hai giá trị `int` từ operand stack rồi đẩy tổng.

### Bài 3. PC và branch displacement

Một opcode `goto` nằm tại offset 20, đích nằm tại offset 7. Độ lệch signed được mã hóa theo khái niệm là bao nhiêu?

**Đáp án:** `7 - 20 = -13`, tính từ offset opcode `goto`, **không** từ offset ngay sau `goto`.

### Bài 4. Local slots

Một static method nhận `(long first, double second, int third)`. Những tham số bắt đầu ở slot nào?

**Đáp án:** `first` ở slot 0–1; `second` ở slot 2–3; `third` ở slot 4. Nếu là instance method thì còn receiver `this` ở slot 0 và các tham số dịch tương ứng.

### Bài 5. `iload_0` và `iconst_0` khác nhau ra sao?

**Đáp án:** `iload_0` lấy giá trị `int` từ local slot 0; `iconst_0` đẩy giá trị hằng số `0`, không cần đọc local.

### Bài 6. Vì sao một method với `max_stack=2` vẫn gọi được method khác?

**Đáp án:** `max_stack` giới hạn operand stack **trong frame hiện tại**. Lời gọi tạo/kích hoạt frame khác với locals và operand stack của callee; không dùng giới hạn 2 đó làm số frame tối đa cho JVM stack.

### Bài 7. Một đoạn code Java chạy êm với dữ liệu đầu vào A. Điều đó đủ kết luận bytecode luôn hợp lệ không?

**Đáp án:** Không. Verifier phải kiểm tra các ràng buộc kiểu/luồng ở cấp class file; một thử nghiệm cụ thể không khám phá mọi nhánh. Ngược lại, qua verification cũng **không** bảo đảm không có lỗi runtime nghiệp vụ.

### Bài 8. Tại sao không thể suy ra CPU đang dùng những thanh ghi nào từ `javap -c`?

**Đáp án:** `javap` hiển thị **bytecode JVM**, không phải mã máy sau khi JIT tối ưu. Cách JVM ánh xạ operand stack sang thanh ghi CPU là chi tiết của runtime và phiên bản thực thi.

## 18. Tóm tắt và tài liệu chính thức

Chuỗi tư duy đúng khi đọc bytecode:

```text
instruction offset / PC
          |
          v
Đọc opcode và operand bytes nếu có
          |
          v
Kiểm tra kiểu và trạng thái operand stack / locals trước lệnh
          |
          v
Áp dụng hiệu ứng pop, push, load, store hoặc branch
          |
          v
Xác định instruction tiếp theo (tuần tự, nhảy, gọi/return, exception)
          |
          v
Lặp lại cho đến khi phương thức kết thúc
```

**Opcode** quy định thao tác, **operand bytes** mang những tham số mã hóa của một số instruction, **operand stack** mang nhiều toán hạng runtime, **local variables** chứa tham số/giá trị cục bộ, và **PC register** xác định vị trí instruction hiện tại của mỗi thread. Bốn thành phần này liên kết để tạo mô hình thực thi stack-based của JVM.

Đọc thêm:

- [JVM Specification 2.5 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5): PC register, JVM stacks và những vùng dữ liệu runtime.
- [JVM Specification 2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.6): local variables, operand stacks, frame và cách truyền giá trị khi gọi/return.
- [JVM Specification 4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, mảng bytecode `code[]` và exception table.
- [JVM Specification 6 — The JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html): semantics, operands, cấu trúc và ngoại lệ của từng opcode.
- [`javap` Tool Documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): `-c`, `-p` và `-v` để đọc code/attribute.

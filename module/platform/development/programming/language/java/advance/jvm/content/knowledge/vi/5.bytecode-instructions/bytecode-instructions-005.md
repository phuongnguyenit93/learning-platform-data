# Nhánh điều kiện, `goto`, vòng lặp và địa chỉ đích trong JVM bytecode

## 1. Mã nguồn điều khiển luồng được chuyển thành bytecode như thế nào?

Trong Java, chúng ta dùng `if`, `else`, `for`, `while`, `do-while`, `switch`, `break` và `continue` để diễn tả thứ tự thực hiện. Ở mức JVM, phần lớn luồng điều khiển thông thường được biểu diễn bằng **instruction so sánh/kiểm tra điều kiện**, **instruction nhảy vô điều kiện**, **instruction lựa chọn nhiều nhánh**, cùng với những instruction thực hiện công việc và trả kết quả.

~~~text
Source Java                      Mô hình bytecode thường gặp

if (condition) { ... }       →   kiểm tra; nhảy qua block nếu sai
while (condition) { ... }    →   kiểm tra; chạy body; nhảy ngược về điều kiện
for (init; test; update)     →   init; test; body; update; nhảy để lặp
break                        →   nhảy tới điểm sau vòng lặp/switch
continue                     →   nhảy tới điểm cập nhật/kiểm tra của vòng lặp
switch                       →   tableswitch / lookupswitch / chuỗi so sánh
return                       →   ireturn, areturn, return, ... theo loại giá trị
~~~

Đây là cách hình dung, **không phải quy tắc một-một** giữa cú pháp nguồn và một lệnh bytecode cụ thể. Compiler có thể đảo chiều điều kiện, bỏ nhánh dư, constant-fold, đổi vị trí kiểm tra hoặc sinh các cấu trúc khác mà vẫn bảo toàn ngữ nghĩa của chương trình.

Một phương thức có bytecode nằm trong thuộc tính `Code` của class file. Mảng `code[]` này là một dãy byte instruction có địa chỉ tính **từ đầu code của chính phương thức đó**. Trong đầu ra `javap -c`, số ở đầu dòng như `0:`, `4:`, `12:` chính là **bytecode offset**, không phải số dòng source, index trong constant pool hay địa chỉ RAM.

## 2. Program counter (PC), fall-through và branch target

Theo mô hình JVM, mỗi JVM thread có **program counter (PC) register** để biểu thị vị trí instruction đang được thực thi trong phương thức hiện tại; phần chi tiết native method có quy tắc riêng. Khi chạy các instruction bytecode:

- **Fall-through**: nếu instruction không thay đổi luồng điều khiển, vị trí tiếp theo thường là instruction kế tiếp theo thứ tự `code[]`.
- **Conditional branch**: JVM kiểm tra điều kiện sau khi lấy operand cần thiết từ operand stack. Nếu đúng, chuyển sang **branch target**; nếu sai, tiếp tục ở instruction tiếp theo.
- **Unconditional branch**: `goto` chuyển thẳng tới target, không kiểm tra điều kiện.
- **Return/throw**: `ireturn`, `areturn`, `return`, `athrow` chuyển điều khiển ra khỏi luồng instruction bình thường của phương thức, theo các quy tắc gọi và xử lý exception.

Mỗi instruction có độ dài byte tùy opcode và operand. Vì vậy bytecode offset thường **không tăng đều từng 1**: ví dụ một lệnh `iload_0` có thể chiếm 1 byte, còn `ifeq` dạng thông thường chiếm 3 byte (opcode và hai byte offset). Không suy ra một lệnh ở offset 4 có “số thứ tự instruction = 4”.

### Địa chỉ đích của `if` và `goto` được tính từ đâu?

Đối với các branch instruction dạng offset 16 bit như `ifeq`, `if_icmpge`, `ifnull`, `goto`, operand branch offset là một số **có dấu 16 bit**, mã hóa từ hai byte theo thứ tự high byte rồi low byte. Giá trị offset được cộng với **địa chỉ của chính opcode nhảy**, không phải địa chỉ instruction ngay sau lệnh nhảy.

~~~text
target_pc = branch_opcode_pc + signed_branch_offset
~~~

Ví dụ:

~~~text
  1: ifge          7
  4: iload_0
  5: ineg
  6: ireturn
  7: iload_0
~~~

Nếu opcode `ifge` nằm ở PC = 1 và target in bởi `javap` là 7 thì độ dời (branch offset) là **7 - 1 = +6**, không phải 7 - 4. Nếu branch target nhỏ hơn PC hiện tại thì độ dời là số âm, rất thường gặp ở vòng lặp.

`javap -c` **in target PC đã tính thành số offset đích** để dễ đọc; nó không nhất thiết in trực tiếp hai byte operand đã mã hóa. Khi cần kiểm tra bytes thực tế, dùng `javap -v` để xem cấu trúc và một công cụ đọc class file dạng hex nếu cần, đồng thời nhớ rằng phần trình bày `javap` là disassembly.

**Quan trọng:** target phải chỉ đến một instruction hợp lệ trong `code[]`, không được nhảy vào giữa byte operand của instruction khác; lớp phải thỏa các quy tắc cấu trúc và verification của JVM. Đây cũng không phải “nhảy tới dòng 7 của file Java”.

## 3. Những nhóm branch instruction phổ biến

| Nhóm | Instruction thường gặp | Operand được kiểm tra |
| --- | --- | --- |
| So với 0 | `ifeq`, `ifne`, `iflt`, `ifle`, `ifgt`, `ifge` | Lấy **một giá trị int** trên operand stack để so với 0 |
| So hai int | `if_icmpeq`, `if_icmpne`, `if_icmplt`, `if_icmple`, `if_icmpgt`, `if_icmpge` | Lấy **hai giá trị int**, so sánh theo quan hệ |
| So hai reference | `if_acmpeq`, `if_acmpne` | Kiểm tra hai reference có cùng object hoặc cùng null hay không |
| So với null | `ifnull`, `ifnonnull` | Lấy một reference và kiểm tra null |
| Nhảy vô điều kiện | `goto`, `goto_w` | Không dùng điều kiện trên stack |
| Chọn nhiều nhánh | `tableswitch`, `lookupswitch` | Lấy một khóa int, chọn target phù hợp |

Các instruction `if*` **lấy operand ra khỏi operand stack** để kiểm tra, nên trạng thái stack sau kiểm tra đã thay đổi. Compiler thường phải đặt lệnh nạp giá trị như `iload`, `aload`, `iconst` hoặc phép tính tương ứng trước lệnh branch.

Chú ý các nhầm lẫn:

- `ifeq` nghĩa là **nhảy khi int bằng 0**, chứ không phải “if của source đúng”. Nếu source viết `if (flag)`, compiler có thể dùng `ifeq` để **bỏ qua thân if khi flag false**.
- `if_icmp*` so hai số `int`, không phải mọi kiểu số. Với `long`, JVM thường dùng `lcmp` trước một branch so với 0; với `float`/`double` có `fcmpl`, `fcmpg`, `dcmpl`, `dcmpg` cùng những quy tắc riêng cho NaN.
- `if_acmp*` so **reference identity**, không gọi `equals()`. Hai `String` khác object nhưng cùng nội dung có thể là `false` khi so `==`.
- `ifnull`/`ifnonnull` làm việc với reference value; `null` không phải một object có thể dereference.
- `goto` của bytecode là công cụ triển khai control flow JVM, **không chứng minh source Java có câu lệnh goto**. Java không có statement `goto`; từ khóa `goto` được dành riêng nhưng không sử dụng.

## 4. Ví dụ tối thiểu: một if chuyển thành nhánh thế nào?

Nguồn Java:

~~~java
static int absoluteLike(int number) {
    if (number < 0) {
        return -number;
    }
    return number;
}
~~~

Một chuỗi bytecode điển hình do `javac` sinh ra là:

~~~text
0: iload_0
1: ifge          7
4: iload_0
5: ineg
6: ireturn
7: iload_0
8: ireturn
~~~

Đây là **một cách biên dịch minh họa**; hãy dùng `javap` trên class thật để biết offset và instruction của compiler bạn đang chạy.

Phân tích từng bước:

1. `iload_0` đưa `number` vào operand stack.
2. `ifge 7` lấy `number` khỏi stack và nhảy tới offset 7 **nếu number ≥ 0**, tức là **đảo điều kiện** để bỏ qua nhánh xử lý số âm.
3. Nếu `number < 0`, JVM tiếp tục ở offset 4, nạp lại `number`, thực hiện `ineg` rồi `ireturn`.
4. Nếu `number ≥ 0`, JVM tới offset 7, nạp `number` và `ireturn`.

Điều kiện source `number < 0` không bắt buộc xuất hiện thành instruction `iflt`. Compiler dùng `ifge` vì đây là điều kiện để **nhảy ra khỏi nhánh true**.

Một ghi chú về toán học: giá trị `Integer.MIN_VALUE` không có số đối dương biểu diễn được bằng `int`; phép `-number` trên `int` cho lại giá trị đó do overflow theo quy tắc Java. Ví dụ tập trung vào bytecode branching, không triển khai hàm trị tuyệt đối an toàn cho mọi `int`.

## 5. Vòng lặp = nhánh tiến, nhánh lùi và điểm kiểm tra

Một **backward branch** là branch có target offset **nhỏ hơn** offset opcode nhảy: đó là kiểu liên kết thường xuất hiện ở vòng lặp. Nhưng bản chất một vòng lặp là **chu trình trong control-flow graph (CFG)**, không nhất thiết luôn có đúng một instruction `goto` lùi.

### 5.1. While

Source:

~~~java
int i = 0;
while (i < 3) {
    i++;
}
~~~

Mô hình CFG:

~~~text
      [khởi tạo i = 0]
              |
              v
       [kiểm tra i < 3] ------ sai -----> [sau vòng lặp]
              |
             đúng
              v
          [i tăng]
              |
              +----------- nhảy về kiểm tra
~~~

Một dạng bytecode giản lược, các offset chỉ mang tính mô tả:

~~~text
0: iconst_0
1: istore_1
2: iload_1
3: iconst_3
4: if_icmpge     13
7: iinc          1, 1
10: goto         2
13: ...          ; lệnh sau vòng lặp
~~~

Lệnh `if_icmpge` nhảy **tiến** qua body khi điều kiện `i < 3` sai. `goto 2` nhảy **lùi** về vị trí kiểm tra, tạo chu trình.

**Không ghi nhớ những offset trên như output thật**: compiler có thể thay đổi cách sinh code tùy ngữ cảnh, version, phần code sau vòng lặp và tối ưu. Khi phân tích một class thực tế, offset phải lấy trực tiếp từ `javap -c`.

### 5.2. Do-while

Trong `do { body } while (condition);`, body phải chạy **ít nhất một lần**. Compiler thường đặt **body trước kiểm tra**, rồi dùng conditional branch lùi nếu điều kiện còn đúng. Điều này giải thích vì sao đôi khi chỉ có một branch có điều kiện lùi, không cần một `goto` lùi riêng.

### 5.3. For

Với `for (initialization; condition; update) { body }`, luồng logic là:

~~~text
initialization
      |
      v
  condition ----- false -----> exit
      |
     true
      v
     body
      |
      v
    update
      |
      +----------------------> condition
~~~

Phần initialization diễn ra một lần, condition trước mỗi lượt (nếu có), update sau mỗi lượt kết thúc bình thường hoặc khi `continue` chuyển tới update. Compiler có thể dùng `iinc` cho `i++`, nhưng đây chỉ là lựa chọn tối ưu cho một số biến `int` cục bộ.

Một `for (;;)` không có điều kiện có thể trở thành chu trình backedge không có nhánh thoát trực tiếp, trừ khi thân chứa `break`, `return`, `throw` hay sự kiện điều khiển khác.

### 5.4. `break` và `continue` tương ứng đích khác nhau

Trong vòng lặp Java:

- `break` thường chuyển điều khiển tới **điểm sau vòng lặp**.
- `continue` chuyển điều khiển tới **điểm thực hiện update** trong `for`, hoặc **điểm kiểm tra điều kiện** của `while`/`do-while`.
- Với **labeled break/continue**, target phải tương ứng với statement/vòng lặp được gắn nhãn theo ngữ nghĩa Java. Không phải luôn nhảy tới vòng lặp bên trong cùng.
- Nếu `break`/`continue` đi ra khỏi vùng `try/finally`, compiler phải thực hiện ngữ nghĩa `finally` phù hợp; không thể mô hình hóa bằng một `goto` duy nhất mà bỏ cleanup.

Không đồng nhất `break` trong `switch` statement với `break` thoát vòng lặp; chúng điều khiển các statement khác nhau. `switch` expression với arrow/yield cũng có quy tắc nguồn riêng.

## 6. `tableswitch` và `lookupswitch`: chọn nhiều địa chỉ đích

Với nhiều lựa chọn trên một khóa `int` phù hợp, compiler có thể dùng một trong hai switch instruction JVM.

### 6.1. `tableswitch`

`tableswitch` biểu diễn các target ứng với một **dải khóa liên tục** từ `low` đến `high`, cùng target mặc định. Từng khóa trong dải có một offset (nếu source không khai báo case tương ứng, compiler vẫn có thể cho entry đó nhảy tới default).

Cấu trúc về mặt ý nghĩa:

~~~text
tableswitch
    default_offset
    low
    high
    jump_offsets[high - low + 1]
~~~

Nó phù hợp với những giá trị `case` tương đối dày đặc; một khoảng quá rộng và thưa có thể làm bảng lãng phí bytecode.

### 6.2. `lookupswitch`

`lookupswitch` lưu danh sách **match-offset pair** cho các khóa cụ thể, cùng default:

~~~text
lookupswitch
    default_offset
    npairs
    (match_1, offset_1)
    (match_2, offset_2)
    ...
~~~

Danh sách `match` được sắp tăng theo quy tắc class-file format. Đây có thể là lựa chọn gọn hơn khi case rời rạc (ví dụ 1, 1000, 1000000).

### 6.3. Điều mà hai instruction có chung

- Chúng lấy khóa `int` từ operand stack rồi chọn một nhánh.
- Offset đích của switch được lưu dưới dạng **signed 32-bit**, tính **tương đối từ offset của opcode `tableswitch`/`lookupswitch`**, không phải từ vị trí entry trong bảng.
- Các phần dữ liệu của switch cần **padding để trường dữ liệu bắt đầu ở ranh giới 4 byte** tính từ đầu mảng `code[]`. Do đó một `tableswitch` hoặc `lookupswitch` có độ dài byte thay đổi theo vị trí opcode.
- Đầu ra `javap -c` in các target cuối cùng dưới dạng PC và thường hiển thị `default:` / `case:`, không bắt người đọc cộng offset bằng tay.
- Compiler **không bắt buộc** dùng `tableswitch` cho mọi switch dày đặc hay `lookupswitch` cho mọi switch thưa. Chính sách lựa chọn là chi tiết compiler; switch với `String` hoặc một số cấu trúc nguồn có thể dùng hash/equals hoặc chuỗi so sánh kết hợp các instruction khác.

Ví dụ Java:

~~~java
static String classify(int value) {
    return switch (value) {
        case 0 -> "ZERO";
        case 1, 2 -> "SMALL";
        default -> "OTHER";
    };
}
~~~

Khi xem `javap -c`, chú ý các target dùng chung của case 1 và 2, nhánh default và vị trí trả String. Đây là ví dụ có nhiều lựa chọn, nhưng cách compiler hạ `switch` **không được cam kết** là một opcode switch cụ thể.

## 7. Bài thực hành Java 17+: nhiều cấu trúc điều khiển trong một file

Tạo tệp **`BranchFlowDemo.java`**:

~~~java
public final class BranchFlowDemo {
    static int absoluteLike(int number) {
        if (number < 0) {
            return -number;
        }
        return number;
    }

    static String grade(int score) {
        if (score < 0) {
            return "INVALID";
        }
        if (score >= 80) {
            return "HIGH";
        }
        return "NORMAL";
    }

    static int sumEvenUntilSeven(int limit) {
        int sum = 0;
        for (int i = 0; i < limit; i++) {
            if ((i & 1) != 0) {
                continue;
            }
            if (i > 6) {
                break;
            }
            sum += i;
        }
        return sum;
    }

    static int countDown(int start) {
        int remaining = start;
        while (remaining > 0) {
            remaining--;
        }
        return remaining;
    }

    static String classify(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> "SMALL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("abs=" + absoluteLike(-3));
        System.out.println("grade=" + grade(85));
        System.out.println("sum=" + sumEvenUntilSeven(10));
        System.out.println("remaining=" + countDown(3));
        System.out.println("kind0=" + classify(0));
        System.out.println("kind2=" + classify(2));
        System.out.println("kind9=" + classify(9));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa file:

~~~bash
javac --release 17 BranchFlowDemo.java
java BranchFlowDemo
~~~

**Stdout được xác định bởi chương trình:**

~~~text
abs=3
grade=HIGH
sum=12
remaining=0
kind0=ZERO
kind2=SMALL
kind9=OTHER
~~~

Kiểm tra nhanh:

- `absoluteLike(-3)` trả 3 qua nhánh xử lý số âm.
- `grade(85)` rơi vào nhánh `score >= 80`, trả `HIGH`.
- Trong `sumEvenUntilSeven(10)`, số lẻ bị `continue` bỏ qua; cộng 0 + 2 + 4 + 6 = **12**; tại i = 8, `break` thoát vòng lặp.
- `countDown(3)` giảm còn 0 rồi thoát do `remaining > 0` sai.
- `classify` trả đúng string cho case 0, case 1/2 và default.

### Dùng javap để quan sát nhánh thật

~~~bash
javap -classpath . -c -p BranchFlowDemo
javap -classpath . -v -p BranchFlowDemo
~~~

Hãy đọc từng method theo cách sau:

1. Xác định block `Code:` của `absoluteLike`; tìm `ifge` hoặc một nhánh điều kiện tương đương rồi các lệnh `ireturn`.
2. Trong `grade`, chú ý nhiều điều kiện và các instruction return của kiểu reference như `areturn`.
3. Trong `sumEvenUntilSeven`, tìm điều kiện của `for`, nhánh bỏ qua số lẻ, nhánh thoát khi `i > 6` và backedge. Liên hệ `continue` với đường tới update/kiểm tra tiếp theo.
4. Trong `countDown`, tìm phần kiểm tra dừng và backedge, đồng thời xem liệu compiler có đặt điều kiện ở đầu hay dùng bố trí khác.
5. Trong `classify`, quan sát xem compiler chọn `tableswitch` hay `lookupswitch` hoặc một chuỗi nhánh; đừng suy diễn lựa chọn từ source mà không kiểm tra.
6. Với `-v`, xem thêm `StackMapTable` (nếu có), `LineNumberTable` và dữ liệu class-file version. Class biên dịch bằng `--release 17` có **major version 61**.

Một bài tập bổ sung là biên dịch riêng với `-g:none` và so đầu ra `javap -c` với `javap -l`: bỏ debug line/local metadata **không xóa những nhánh điều khiển cần thiết để chương trình chạy**.

## 8. Đọc control-flow graph (CFG) từ bytecode

**Basic block** là dãy instruction có một điểm bắt đầu và không có nhánh rẽ nội bộ, kết thúc bằng một instruction chuyển luồng hoặc tại vị trí trước một target của nhánh. Có thể dựng CFG từ `javap`:

1. Lấy **entry PC = 0** cho method có code.
2. Tìm các target của `if*`, `goto`, `tableswitch`, `lookupswitch` và các điểm tiếp tục sau conditional branch.
3. Tách basic block ở đầu method, tại target, và tại instruction tiếp sau những nơi luồng điều khiển có thể phân nhánh.
4. Nối các cạnh **conditional true**, **fall-through**, **unconditional goto**, và cạnh lựa chọn switch/default. `return` kết thúc nhánh thực thi bình thường.
5. Tìm đường quay lại các block đã có để nhận diện vòng lặp; tìm block sau nhiều nhánh hội tụ để hiểu phần tiếp tục chung.
6. Khi phân tích chương trình thực, bổ sung **exceptional control flow** từ `exception_table`; code ném exception có thể chuyển tới handler mà không qua lệnh `goto` thông thường.

Ví dụ CFG tối giản:

~~~text
PC 0: [load x; test x]
          |
          +-- true ---> PC 8: [return A]
          |
          +-- false --> PC 4: [return B]
~~~

Con số PC chỉ là nhãn offset của ví dụ. Nếu nhìn thấy đường đi `PC 20 -> PC 4`, bạn nhận ra **backedge** nhưng chưa thể khẳng định nguồn dùng `for`, `while` hay `do-while`; nhiều cấu trúc khác nhau có thể sinh CFG tương tự.

### Điều kiện rẽ nhánh không phải “kết quả boolean trên stack” trong mọi trường hợp

Một câu source như `a < b` có thể được compiler thực hiện bằng `iload` hai biến và `if_icmpge` đảo chiều để bỏ qua body, **không nhất thiết phải đẩy ra một đối tượng Boolean** hoặc một giá trị boolean tạm rồi mới kiểm tra. Điều đó giúp bạn đọc code hiệu quả hơn: quan sát **chuỗi instruction lấy operand và nhảy**, thay vì cố tìm một `Boolean` object cho mọi biểu thức điều kiện.

## 9. `&&`, `||` và short-circuit

Ngôn ngữ Java có short-circuit:

- `a && b`: nếu `a` false, **không đánh giá `b`**.
- `a || b`: nếu `a` true, **không đánh giá `b`**.

Trình biên dịch có thể sử dụng nhiều branch liên tiếp để thực thi đúng thứ tự và tránh side effect không cần thiết. Ví dụ:

~~~java
static boolean allowed(String value) {
    return value != null && !value.isEmpty();
}
~~~

Điều kiện `value != null` phải được xử lý trước, và khi `value == null`, lời gọi `value.isEmpty()` **không được thực hiện**. Ở bytecode, bạn có thể thấy `ifnull` hoặc branch tương đương chuyển sang đường trả false trước instruction `invokevirtual` của `isEmpty`.

Do đó, nếu bạn muốn phân tích hành vi của một expression phức tạp, hãy xác định các đường nhánh thực tế và thứ tự lời gọi, không chỉ đếm số instruction `if`.

## 10. Giới hạn branch offset và `goto_w`

Hầu hết conditional branch thông thường và `goto` sử dụng **signed 16-bit relative offset**, với khoảng biểu diễn từ -32768 đến +32767 tính từ bytecode PC của opcode. Khi target ở ngoài khoảng này:

- `goto_w` sử dụng **signed 32-bit branch offset** để nhảy vô điều kiện tới target xa hơn.
- Không có một cặp opcode `if_w` chung cho mọi điều kiện. Compiler có thể **đảo điều kiện** để nhảy qua một `goto_w`, nhờ đó vẫn biểu diễn được một nhánh điều kiện dài.
- Cách compiler triển khai phụ thuộc kích thước method và công cụ; đừng suy ra lệnh `goto_w` xuất hiện vì nguồn Java có cấu trúc đặc biệt.
- Một method có giới hạn độ dài `code[]` theo class-file format (tối đa **65535 byte** ở các phiên bản class file liên quan), nên không thể có code bytecode dài vô hạn trong một method. Compiler có thể báo lỗi khi phương thức quá lớn; việc dùng `goto_w` không loại bỏ giới hạn kích thước method.

Ví dụ minh họa biến đổi để nhảy xa:

~~~text
Điều kiện dự định: nếu x == 0 thì nhảy tới TARGET_FAR

Dạng có thể được compiler chuyển thành:
    ifne AFTER
    goto_w TARGET_FAR
AFTER:
    ...           ; tiếp tục khi x != 0
~~~

Đây là **pseudocode điều khiển**, không phải output `javap` cố định; các nhãn `AFTER`, `TARGET_FAR` chỉ giúp người học hiểu cách đảo điều kiện.

### Các instruction lịch sử

JVM còn có `jsr`, `jsr_w` và `ret`, từng được dùng với subroutine bytecode cho `finally` trong các compiler cũ. Chúng **không phải** cách biểu diễn vòng lặp Java thông thường; đối với class-file version hiện đại, các ràng buộc verifier đã khiến compiler Java hiện nay không dùng mô hình subroutine lịch sử này. Khi thấy tài liệu cũ có `jsr`/`ret`, hãy phân biệt với `goto` và compiler Java hiện đại.

## 11. Verification, `StackMapTable` và branch target an toàn

JVM verifier không chỉ kiểm tra opcode có được hỗ trợ. Nó phải xác minh điều kiện để các instruction dùng operand stack/local variables nhất quán ở những điểm điều khiển có thể tới.

Ví dụ: một block nhận điều khiển từ hai nhánh phải có trạng thái kiểu operand stack/local variables **hợp lệ và tương thích** theo quy tắc verification. Nếu một nhánh để trên stack giá trị int trong khi đường khác đưa reference tới cùng điểm mà code đòi đọc int, class file có thể không qua verification.

**`StackMapTable`** (với các class-file version hiện đại khi thích hợp) chứa các frame hỗ trợ type checking ở các vị trí liên quan. Đây là metadata dành cho **verification**, khác với `LineNumberTable` hỗ trợ ánh xạ dòng source:

- Không thể chỉ sửa hai byte branch offset rồi tin rằng class sẽ chạy; target, stack frame, instruction length và control-flow metadata phải nhất quán.
- Nhảy vào giữa instruction/operand không hợp lệ.
- Target thuộc phạm vi `Code` của **cùng method**; muốn gọi method khác phải dùng instruction invoke, không dùng `goto` để “nhảy” thẳng sang một method khác.
- `StackMapTable` không mô tả thứ tự nguyên văn của các câu `if`/loop source. Nó hỗ trợ kiểm tra tính nhất quán kiểu của bytecode đã sinh.

Bên cạnh các branch instruction còn có **exception table** trong `Code`, với những giá trị `start_pc`, `end_pc`, `handler_pc` và kiểu catch. Các trường này là **PC index trong mảng code**, không phải tất cả đều là signed relative offset giống operand `goto`. Exception có thể chuyển điều khiển tới handler dù trong bytecode không có một `goto` minh thị tới đó.

## 12. Địa chỉ đích trong javap không phải địa chỉ máy hay dòng source

Có ít nhất bốn dạng số thường xuất hiện khi phân tích class file:

| Giá trị | Nó đánh số gì? | Công dụng |
| --- | --- | --- |
| Bytecode offset/PC | Vị trí instruction trong `code[]` của **method** | `javap -c` hiển thị lệnh và target |
| Branch offset | Số byte đích lệch tương đối so với PC opcode nhảy | Operand của `if*`, `goto`, `switch` |
| Source line number | Dòng văn bản `.java` do compiler ghi trong `LineNumberTable` | Breakpoint, stack trace, debug |
| Địa chỉ native/virtual memory | Vị trí trong không gian địa chỉ của tiến trình hoặc code do JIT sinh | Chi tiết implementation/runtime, không phải nhãn `javap -c` |

Ví dụ một dòng disassembly `10: goto 2` nói rằng **instruction ở bytecode PC 10 chuyển tới bytecode PC 2** trong cùng method. Nó **không** có nghĩa “nhảy tới dòng source 2”, “truy cập địa chỉ RAM 0x2”, hoặc “tới instruction thứ 2”. Nếu bytecode đang được JIT tối ưu thành native machine code, vị trí instruction native hoàn toàn khác hệ tọa độ PC bytecode này.

Một chương trình có thể chạy với class file đã bị strip debug metadata nên không có `LineNumberTable`, nhưng nhánh `goto` và các bytecode offset vẫn hiện diện vì JVM cần chúng để thực thi. Điều này là bằng chứng trực tiếp cho thấy **bytecode control flow** và **source-line mapping** là hai lớp thông tin khác nhau.

## 13. Những nhầm lẫn phổ biến

1. **“`ifeq` nghĩa là source if đúng.”** Sai. Nó nhảy khi operand int bằng 0; compiler thường dùng để bỏ qua body khi điều kiện nguồn false.
2. **“`goto 12` là nhảy tới dòng 12 trong Java.”** Sai. Đây là bytecode PC 12 của cùng method.
3. **“Branch offset tính từ sau instruction `goto`.”** Sai. JVM branch offset được tính từ **PC của chính opcode**.
4. **“Vòng lặp luôn phải có một `goto` lùi.”** Sai. CFG có thể có conditional backedge, hoặc compiler bố trí điều kiện và jump khác.
5. **“`break` chỉ cần xóa instruction tiếp theo.”** Sai. Nó chuyển điều khiển đúng target và vẫn phải tôn trọng ngữ nghĩa `finally` khi có.
6. **“`continue` trong for luôn quay về đầu body.”** Sai. Nó đi tới update/kiểm tra như cấu trúc `for` quy định.
7. **“`if_acmpeq` gọi `equals()`.”** Sai. Nó so reference identity.
8. **“`tableswitch` có offset tính từ đầu bảng case.”** Sai. Offset relative được tính từ **PC opcode switch**.
9. **“Mọi switch Java là `tableswitch`.”** Sai. Compiler có thể chọn `lookupswitch` hoặc cơ chế khác.
10. **“Nhảy tới bất kỳ byte nào trong `code[]` đều được.”** Sai. Target và stack state phải hợp lệ theo verification.
11. **“Dòng 20 trong `LineNumberTable` là PC 20.”** Sai. Line number và bytecode offset là hai đại lượng khác nhau.
12. **“Source Java có từ khóa `goto` để gọi JVM goto.”** Sai. Java dành riêng từ `goto` nhưng không có statement `goto` hợp lệ.

## 14. Câu hỏi và bài tập tự kiểm tra

1. `ifge` ở PC 4 nhảy tới PC 16. Operand relative offset bằng bao nhiêu? **+12**, vì tính từ PC opcode = 4.
2. `goto` ở PC 20 nhảy về PC 5. Offset bằng bao nhiêu? **-15**; đây là một backward branch.
3. `ifeq` nhìn thấy int 0 sẽ làm gì? **Nhảy tới target**; nếu khác 0, fall-through.
4. Một `if (x > 0)` có thể biên dịch thành `ifle` không? **Có**, nếu `ifle` được dùng để bỏ qua body khi điều kiện nguồn sai.
5. `if_acmpeq` so `String.equals()` hay so reference identity? **So identity**.
6. Tại sao `continue` trong `for (init; test; update)` thường dẫn về `update`? Vì đó là bước tiếp theo theo ngữ nghĩa của `for`, trước lần test tiếp theo.
7. Tại sao `tableswitch` thường hiệu quả với dải khóa dày và `lookupswitch` hợp hơn với khóa thưa? Bởi **bảng target liên tục** khác với **danh sách cặp match/offset**.
8. `StackMapTable` có phải tên khác của `LineNumberTable` không? **Không**; một bảng phục vụ verification kiểu, một bảng phục vụ ánh xạ dòng nguồn.
9. Nếu `javap -c` hiển thị `0: iload_0`, `1: ifge 7`, `4: iload_0`, tại sao PC kế tiếp là 4? Vì `ifge` dài 3 byte, không phải 1 byte.
10. Tại sao một decompiler không thể chắc source dùng `for` hay `while` chỉ từ backedge? Vì nhiều cấu trúc nguồn có thể tạo **CFG/bytecode tương đương**.

## 15. Nguồn tham khảo đặc tả

- JVM Specification Java SE 17, chương **Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- JVMS, chương **The Class File Format**, cấu trúc `Code` và `StackMapTable`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS, chương **Verification**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10
- Tài liệu JDK 17 `javap`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Java Language Specification Java SE 17, phần **Statements**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html

**Kết luận kỹ thuật:** `if*`, `goto`, `goto_w`, `tableswitch` và `lookupswitch` mô tả **các cạnh luồng điều khiển giữa những vị trí bytecode trong cùng phương thức**. Conditional branch kiểm tra operand stack, `goto` nhảy không điều kiện và vòng lặp tạo chu trình trong CFG. Các địa chỉ đích được tính theo **bytecode PC và signed relative offset**, không phải số dòng Java hay địa chỉ bộ nhớ vật lý. Khi đọc disassembly, luôn lần theo operand, target và trạng thái stack để hiểu chính xác JVM thực thi đường đi nào.

# Nhóm lệnh bytecode JVM: số học, bit, so sánh và chuyển kiểu

## Mục tiêu

Bytecode của Java Virtual Machine (JVM) là tập lệnh được định nghĩa trong *Java Virtual Machine Specification (JVMS)*. Người lập trình thường viết toán tử Java như `+`, `&`, `<` hay ép kiểu `(int) x`; compiler có thể chuyển chúng thành các lệnh JVM tương ứng để thao tác trên **operand stack** và **local variables**. Một toán tử nguồn không luôn tương đương đúng một opcode vì còn có nâng kiểu, nạp/lưu dữ liệu, rẽ nhánh, lời gọi thư viện và tối ưu.

Sau bài học, bạn có thể:

- Đọc tên và quy tắc kiểu của opcode số học, phép bit, phép dịch, so sánh và chuyển đổi nguyên thủy trên JVM.
- Giải thích cách opcode lấy toán hạng từ operand stack, đẩy kết quả và dùng local variables.
- Phân biệt tràn số nguyên với số thực, dịch phải có dấu với không dấu, toán tử so sánh với instruction rẽ nhánh và cách xử lý NaN.
- Hiểu mở rộng/thu hẹp kiểu, mất độ chính xác, truncation và các trường hợp NaN/vô cực khi ép kiểu.
- Tự biên dịch Java 17+, xem bytecode qua `javap -c -p`, so sánh kết quả thực thi với quy tắc JVM.

## 1. Đọc quy tắc đặt tên lệnh và mô hình stack

Nhiều opcode có **tiền tố kiểu dữ liệu** và phần **hậu tố phép toán**:

| Tiền tố | Kiểu giá trị trên operand stack | Ví dụ |
| --- | --- | --- |
| `i` | `int` (cũng dùng làm representation cho `boolean`, `byte`, `short`, `char` trong nhiều thao tác) | `iadd`, `iand`, `ishl`, `i2d` |
| `l` | `long` | `ladd`, `lcmp`, `lushr` |
| `f` | `float` | `fadd`, `fcmpl`, `f2i` |
| `d` | `double` | `ddiv`, `dcmpg`, `d2l` |

Ngoài các tiền tố đó còn có opcode như `iinc`, `if_icmplt` hoặc `if_acmpeq` với vai trò đặc thù. JVM **không có nguyên một bộ opcode số học riêng cho `byte`/`short`/`char`/`boolean`**; khi cần, compiler thực hiện các phép toán theo **numeric promotion** của ngôn ngữ Java và dùng `int` hoặc opcode chuyển đổi để bảo toàn ý nghĩa.

### Operand stack hoạt động theo nguyên tắc LIFO

Ví dụ giả định operand stack đang có hai số nguyên:

~~~text
Trước iadd:      ..., value1, value2  (value2 ở đỉnh)
Thực thi iadd:   pop value2, pop value1; tính value1 + value2
Sau iadd:        ..., result
~~~

Với phép không giao hoán, thứ tự rất quan trọng: `isub` tính **value1 − value2**, `idiv` tính **value1 / value2**, không đảo chiều hai toán hạng.

Trong phần mô tả opcode của JVMS, mẫu `..., value1, value2 → ..., result` là **mô hình stack**, không phải cú pháp Java có thể biên dịch. Các kiểu `long` và `double` thuộc **category 2** (chiếm hai đơn vị độ sâu stack), còn `int` và `float` thuộc **category 1**. Bytecode verifier kiểm tra kiểu và hình dạng stack trên những đường điều khiển hợp lệ.

### Local variables và bytecode số học

Ví dụ Java đầy đủ về phương thức:

~~~java
public static int add(int left, int right) {
    return left + right;
}
~~~

Đây là **một phương thức**, chưa phải class chạy độc lập. Với `javac` thông thường, đoạn bytecode tương ứng có dạng:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

Hai lệnh `iload` nạp biến cục bộ vào stack, `iadd` tính tổng, `ireturn` trả giá trị về caller. Đừng nhầm `iadd` với thao tác trực tiếp trên hai ô local variables; phép cộng lấy hai giá trị **trên operand stack**. Compiler khác có thể sinh chuỗi tương đương, và các chỉ số/offset bytecode không phải phần của ngữ nghĩa chương trình Java.

## 2. Nhóm số học: `add`, `sub`, `mul`, `div`, `rem` và `neg`

Mỗi hàng có các biến thể tương ứng với `int`, `long`, `float`, `double`:

| Phép toán | `int` | `long` | `float` | `double` |
| --- | --- | --- | --- | --- |
| Cộng | `iadd` | `ladd` | `fadd` | `dadd` |
| Trừ | `isub` | `lsub` | `fsub` | `dsub` |
| Nhân | `imul` | `lmul` | `fmul` | `dmul` |
| Chia | `idiv` | `ldiv` | `fdiv` | `ddiv` |
| Lấy dư | `irem` | `lrem` | `frem` | `drem` |
| Đổi dấu | `ineg` | `lneg` | `fneg` | `dneg` |

Các lệnh nhị phân pop hai toán hạng theo kiểu tương ứng rồi push một kết quả. Các opcode đổi dấu là đơn toán hạng: `..., value → ..., result`. Không có opcode cộng hoặc nhân trực tiếp cho hai đối tượng `BigInteger` hay `BigDecimal`; phép đó thực hiện qua lời gọi phương thức thư viện.

### Tràn số nguyên: modulo theo độ rộng bit

`int` có 32 bit có dấu và `long` có 64 bit có dấu. Các lệnh cộng/trừ/nhân số nguyên dùng hai bit-width cố định; nếu kết quả toán học vượt giới hạn biểu diễn, các bit cao bị loại bỏ. Kết quả tương ứng biểu diễn hai's complement; **không tự ném `ArithmeticException` vì overflow**.

~~~java
int a = Integer.MAX_VALUE;
System.out.println(a + 1); // -2147483648
System.out.println(-Integer.MIN_VALUE); // -2147483648
~~~

Đây là snippet trong phương thức Java. Ví dụ thứ hai cho thấy đổi dấu số nguyên nhỏ nhất vẫn ra chính nó do không thể biểu diễn đối số dương tương ứng trong 32 bit.

Nếu nghiệp vụ đòi **phát hiện overflow**, dùng các API như `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact` hoặc thiết kế kiểu số lớn. Trong bytecode, chúng thường là **lời gọi phương thức** (ví dụ `invokestatic`), không phải một biến thể “`iaddExact`” của JVMS.

### Chia nguyên và phép dư

- `idiv`/`ldiv` chia số nguyên có dấu; phần thương được làm tròn **về 0**.
- `irem`/`lrem` là phần dư cùng quy tắc chia; khi phần dư khác 0, **dấu của phần dư theo số bị chia**.
- Nếu **số chia bằng 0**, `idiv`, `ldiv`, `irem`, `lrem` ném `ArithmeticException`.
- Trường hợp đặc biệt `Integer.MIN_VALUE / -1` trả `Integer.MIN_VALUE` do overflow; `Integer.MIN_VALUE % -1` trả `0`. Bản `long` tương tự.

~~~java
System.out.println(-7 / 3); // -2
System.out.println(-7 % 3); // -1
System.out.println(7 % -3); // 1
~~~

Nếu muốn phép chia hướng về âm vô cực hoặc modulo toán học dùng trong một số thuật toán, xem `Math.floorDiv` và `Math.floorMod`, vì dấu của kết quả có thể khác với toán tử `/` và `%`.

### Số thực khác số nguyên

Với `float`/`double`, JVM thực thi theo semantics dấu phẩy động IEEE 754 được Java quy định:

- `1.0 / 0.0` cho `+Infinity`; `-1.0 / 0.0` cho `-Infinity`.
- `0.0 / 0.0` cho `NaN`, không ném `ArithmeticException` chỉ vì mẫu số bằng 0.
- Phép toán vượt miền hữu hạn có thể sinh vô cực; phép toán quá nhỏ có thể sinh subnormal rồi tiến về `±0.0`.
- `frem`/`drem` làm phép dư dấu phẩy động theo **quy tắc remainder của Java, không phải định nghĩa IEEE remainder lấy thương nguyên gần nhất**. Khi muốn phép IEEE remainder, dùng `Math.IEEEremainder`.
- `fneg`/`dneg` đảo dấu giá trị dấu phẩy động; với `+0.0` và `-0.0` bit dấu là khác nhau.

Từ **Java 17**, JEP 306 khôi phục **always-strict floating-point semantics**: các phép dấu phẩy động của Java có quy tắc strict, không còn khác biệt ngữ nghĩa do lựa chọn tính intermediate exponent mở rộng như trước. Dù vậy, cộng số thực vẫn có làm tròn và không nhất thiết có tính kết hợp; thứ tự phép tính khác có thể tạo kết quả cuối khác.

## 3. Lệnh tăng biến cục bộ `iinc`

`iinc` là opcode đặc biệt: nó **tăng một biến cục bộ kiểu `int` bằng một hằng số có dấu mã hóa trong instruction**, thay vì pop hai toán hạng từ operand stack.

~~~text
iinc <local_index>, <signed_constant>
~~~

Ví dụ compiler có thể dùng `iinc 1, 1` cho `i++` hoặc `++i` khi `i` là một biến local kiểu `int` và kết quả biểu thức không cần giữ trên stack. Hành vi tăng cũng tuân theo overflow 32-bit như phép cộng nguyên thông thường.

- `iinc` không dùng để tăng trực tiếp local `long` hoặc field của đối tượng.
- Compiler không bị buộc phải sinh `iinc` cho mọi cú pháp `i++`. Nếu cần giá trị trước/sau increment, compiler có thể dùng thêm các lệnh load/store hoặc chọn chuỗi khác.
- `iinc` dạng thường chứa operand local index và hằng 8-bit có dấu; tiền tố `wide` cho phép các operand lớn hơn.

Đừng gọi `iinc` là instruction tính trên operand stack: nó tác động **trực tiếp vào một local variable** trong frame hiện hành.

## 4. Nhóm phép bit: AND, OR, XOR

JVM hỗ trợ các phép bit trên **`int` và `long`**:

| Toán tử nguồn | Opcode trên `int` | Opcode trên `long` | Ý nghĩa từng bit |
| --- | --- | --- | --- |
| `&` | `iand` | `land` | Bit kết quả là 1 khi cả hai bit tương ứng đều 1. |
| `|` | `ior` | `lor` | Bit kết quả là 1 khi ít nhất một bit bằng 1. |
| `^` | `ixor` | `lxor` | Bit kết quả là 1 khi hai bit tương ứng khác nhau. |

Ví dụ số nhỏ 4 bit:

~~~text
a = 10  = 1010
b = 12  = 1100

a & b  = 1000 = 8
a | b  = 1110 = 14
a ^ b  = 0110 = 6
~~~

Đây là minh họa ở bốn bit thấp, không phải giới hạn kích thước `int`. Với `int` thực tế mọi phép đều thao tác đủ 32 bit; với `long` là 64 bit.

**Không có `fand`, `dand` hay opcode `inot`.** Toán tử nguồn `~x` đảo từng bit trên `int`/`long`, có thể được compiler triển khai bằng XOR với mẫu bit toàn 1 (`-1`), ví dụ `iconst_m1` rồi `ixor`. Không có instruction JVM riêng mang tên `inot` cho phép đảo bit nguyên.

### Bitwise với boolean khác short-circuit

Trong ngôn ngữ Java, `&`, `|` và `^` cũng có thể áp dụng cho `boolean`, nhưng biểu thức boolean đó thường được compiler chuyển thành các thao tác int/branch thích hợp. Phân biệt:

- `a && b` và `a || b`: **short-circuit**, vế phải có thể không được đánh giá.
- `a & b` và `a | b` với boolean: **luôn đánh giá cả hai vế**.
- `^` boolean: true khi hai toán hạng khác nhau.

Hệ thống bytecode không có tập opcode arithmetic riêng cho boolean; chi tiết compiler có thể dùng các lệnh int, nhánh hoặc tổ hợp tùy ngữ cảnh.

### Kiểm tra bit flag

~~~java
int permissions = 0b1010;
int writeFlag = 0b0010;

boolean canWrite = (permissions & writeFlag) != 0;
System.out.println(canWrite); // true
~~~

Đây là đoạn minh họa bên trong một phương thức. Với bit mask, hãy chú ý signedness khi dịch bit và khi serialize sang kiểu có độ rộng khác.

## 5. Nhóm phép dịch: `shl`, `shr` và `ushr`

Chỉ `int` và `long` hỗ trợ dịch bit trực tiếp; shift count trên operand stack là **`int`** trong cả hai trường hợp:

| Java | `int` | `long` | Mô tả |
| --- | --- | --- | --- |
| `value << distance` | `ishl` | `lshl` | Dịch trái, lấp bit thấp bằng 0; bỏ bit cao tràn khỏi độ rộng. |
| `value >> distance` | `ishr` | `lshr` | Dịch phải **số học**, lấp bit cao bằng bit dấu cũ. |
| `value >>> distance` | `iushr` | `lushr` | Dịch phải **logic**, lấp bit cao bằng 0. |

Với toán hạng âm, `>>` và `>>>` khác nhau rõ rệt:

~~~java
int x = -8;
System.out.println(x >> 1);  // -4
System.out.println(x >>> 1); // 2147483644
~~~

Trong biểu diễn bù hai, `-8` là một chuỗi 32 bit bắt đầu bằng nhiều bit 1. Dịch phải số học giữ bit dấu 1 nên vẫn âm; dịch phải logic lấp bằng 0 nên trở thành một giá trị dương lớn.

### Shift count được mask

JVM sử dụng **5 bit thấp nhất** của khoảng dịch cho `int`, tức khoảng cách thực tế là `distance & 0x1F` (modulo 32). Với `long`, JVM sử dụng **6 bit thấp nhất**, tức `distance & 0x3F` (modulo 64).

~~~java
System.out.println(1 << 32);  // 1, vì 32 & 31 = 0
System.out.println(1L << 64); // 1, vì 64 & 63 = 0
System.out.println(1 << -1);  // -2147483648, vì -1 & 31 = 31
~~~

Khoảng dịch âm **không tự gây exception**; quy tắc bit mask vẫn áp dụng. Đây là nguồn lỗi phổ biến nếu giả định rằng dịch nhiều hơn độ rộng bit luôn trả về 0.

Chú ý: dịch trái tràn bit không tự gây exception; `x << n` chỉ tương đương nhân với lũy thừa của 2 trong miền không overflow và với các điều kiện giá trị thích hợp. Khi dùng shift để tính kích thước buffer, bit mask hoặc mã hóa, nên xác định rõ độ rộng dữ liệu và xử lý overflow.

## 6. Nhóm so sánh: instruction tạo kết quả và instruction rẽ nhánh

Ở bytecode có **hai cơ chế thường bị nhập làm một**:

1. Lệnh so sánh các giá trị lớn/float và **push một `int` kết quả** lên stack.
2. Lệnh nhánh điều kiện (**`if...`**) kiểm tra một hoặc hai giá trị trên stack và quyết định chuyển điểm thực thi đến offset khác.

Ví dụ mã Java §a < b§ không nhất thiết phải sinh một instruction tên §icmp§ rồi trả boolean; với hai §int§, JVM có instruction nhánh trực tiếp §if_icmplt§.

### So sánh hai `int` rồi rẽ nhánh

| Opcode | Nhánh khi |
| --- | --- |
| `if_icmpeq` | value1 == value2 |
| `if_icmpne` | value1 != value2 |
| `if_icmplt` | value1 < value2 |
| `if_icmple` | value1 <= value2 |
| `if_icmpgt` | value1 > value2 |
| `if_icmpge` | value1 >= value2 |

Những lệnh này **pop hai giá trị int**; nếu điều kiện đúng, control flow nhảy đến nhãn/offset đích, không tự push một giá trị Java §boolean§ 1 hoặc 0. Để trả boolean từ một biểu thức so sánh, compiler có thể tạo code nhánh và đưa §iconst_0§/§iconst_1§ lên stack, sau đó dùng §ireturn§.

Nhóm `ifeq`, `ifne`, `iflt`, `ifle`, `ifgt`, `ifge` lại kiểm tra **một giá trị int đối chiếu với 0**. Chúng thường dùng sau `lcmp`, `fcmp*`, `dcmp*` hoặc cho điều kiện đã mã hóa thành int.

Ngoài so sánh số, có `if_acmpeq`/`if_acmpne` để so sánh **hai tham chiếu đối tượng** theo identity và `ifnull`/`ifnonnull` để kiểm tra null; những instruction này không thực hiện `Object.equals`.

### So sánh hai `long`: `lcmp`

`lcmp` lấy hai giá trị `long` trên stack, thực hiện so sánh **có dấu**, rồi push kết quả kiểu `int`:

~~~text
value1 > value2  →  1
value1 = value2  →  0
value1 < value2  → -1
~~~

Ví dụ phương thức minh họa:

~~~java
static boolean isEarlier(long a, long b) {
    return a < b;
}
~~~

Một compiler Java thông thường có thể dùng `lcmp` rồi `ifge` (hoặc dạng nhánh tương đương) để xây dựng boolean. **Không có chuỗi sáu opcode `if_lcmpeq`...** tương ứng với `if_icmp*` của int.

### So sánh `float`/`double` và NaN

Các opcode:

- `fcmpl`, `fcmpg` cho `float`.
- `dcmpl`, `dcmpg` cho `double`.

Cả bốn lệnh đều lấy hai giá trị số thực và push một `int`:

| Điều kiện so sánh | `fcmpl/dcmpl` | `fcmpg/dcmpg` |
| --- | --- | --- |
| value1 < value2 | -1 | -1 |
| value1 == value2 | 0 | 0 |
| value1 > value2 | 1 | 1 |
| Ít nhất một operand là **NaN** | **-1** | **1** |

Sự khác nhau giữa hậu tố `l` (*less*) và `g` (*greater*) chỉ xuất hiện khi có **NaN**. Điều này quan trọng vì toán tử so sánh số học của Java yêu cầu mọi điều kiện `<`, `<=`, `>`, `>=` đều false nếu một operand là NaN.

Ví dụ compiler muốn triển khai **`a < b`** thường chọn `dcmpg` rồi dùng `ifge`: nếu gặp NaN, `dcmpg` trả 1 và §ifge§ sẽ chuyển sang nhánh false. Với **`a > b`**, có thể dùng `dcmpl` rồi `ifle` để NaN đi về nhánh false. Compiler có thể chọn chuỗi khác nhưng phải bảo toàn semantics.

**Hai số không dấu khác nhau:** `+0.0 == -0.0` là true trong so sánh số học; các opcode `fcmp*`/`dcmp*` coi hai dạng số không là bằng nhau. Nhưng `Double.compare(-0.0, +0.0) < 0` là true, do phương thức thư viện áp dụng **thứ tự toàn phần** khác ngữ nghĩa toán tử/JVM compare instruction. Không dùng `Double.compare` để đoán trực tiếp kết quả của `dcmpl` hoặc `dcmpg` khi có NaN hoặc signed zero.

### Vì sao không có opcode trả kết quả “boolean trên stack”?

Ở mức JVM, kết quả điều kiện thường được biểu diễn bằng đường điều khiển và các hằng int. Một kiểu Java §boolean§ trong biểu thức nguồn có thể tương ứng với giá trị int 0/1 trong nhiều thao tác bytecode. Đây là lý do không nên suy diễn “§if_icmplt§ push true/false” — instruction này chỉ **rẽ nhánh**.

## 7. Nhóm chuyển kiểu số: mã lệnh `x2y`

Tên opcode `i2l` có nghĩa **chuyển int thành long**, `d2i` là **double thành int**. Tập instruction chuyển đổi được thiết kế cho kiểu JVM, nên khác cách viết cast đầy đủ trong mã Java.

### Mở rộng (widening) kiểu nguyên thủy

| Opcode | Chuyển đổi | Ghi chú |
| --- | --- | --- |
| `i2l` | int → long | Bảo toàn chính xác mọi int. |
| `i2f` | int → float | Có thể làm tròn, mất độ chính xác vì chỉ 24 bit significand. |
| `i2d` | int → double | Bảo toàn chính xác mọi int 32-bit. |
| `l2f` | long → float | Có thể làm tròn nhiều bit thấp. |
| `l2d` | long → double | Có thể mất độ chính xác với long lớn. |
| `f2d` | float → double | Bảo toàn chính xác giá trị số hữu hạn của float trong double (không biến số thập phân ban đầu thành “chính xác”). |

Không có opcode `b2i`, `s2i`, `c2i` trong JVM cho việc đổi `byte`/`short`/`char` sang int: các kiểu đó thường được JVM biểu diễn dưới dạng int trong các thao tác liên quan.

**Widening không đồng nghĩa không mất dữ liệu ở mọi trường hợp.** Ví dụ một `long` lớn hơn 2^53 có thể mất bit thấp khi chuyển thành `double`; một `int` không nhất thiết được biểu diễn chính xác khi chuyển thành `float`.

### Thu hẹp (narrowing)

| Opcode | Chuyển đổi | Điểm cần nhớ |
| --- | --- | --- |
| `i2b` | int → byte | Giữ 8 bit thấp rồi mở rộng dấu thành int trên stack. |
| `i2c` | int → char | Giữ 16 bit thấp, không mang dấu rồi biểu diễn dạng int trên stack. |
| `i2s` | int → short | Giữ 16 bit thấp rồi mở rộng dấu thành int trên stack. |
| `l2i` | long → int | Giữ 32 bit thấp, có thể đổi dấu. |
| `f2i`, `f2l` | float → int/long | Bỏ phần lẻ theo hướng 0; xử lý NaN/vô cực theo quy tắc riêng. |
| `d2i`, `d2l` | double → int/long | Tương tự với double; có thể làm tròn/cắt thông tin. |
| `d2f` | double → float | Làm tròn về binary32; có thể thành vô cực, số không hoặc subnormal. |

Ví dụ ép kiểu nguyên:

~~~java
System.out.println((byte) 130);  // -126
System.out.println((short) 65535); // -1
System.out.println((char) 65535 == '\uFFFF'); // true
System.out.println((int) 3.9); // 3
System.out.println((int) -3.9); // -3
~~~

Với `i2b`, 130 ở nhị phân giữ 8 bit thấp là `10000010`, diễn giải có dấu thành -126. Với `i2c`, 16 bit được xem không dấu trong miền mã unit `char` 0..65535. Không có “exception tràn kiểu” tự động khi cast primitive theo các quy tắc này.

### Float/double sang int/long: NaN, vô cực và giới hạn

Đối với các opcode như `d2i`:

1. Nếu đầu vào là **NaN**, kết quả là `0`.
2. Nếu là số hữu hạn trong miền sau khi bỏ phần lẻ hướng 0, kết quả là số nguyên đó.
3. Nếu giá trị vượt miền int dương hoặc là `+Infinity`, kết quả là `Integer.MAX_VALUE`.
4. Nếu thấp hơn miền int âm hoặc là `-Infinity`, kết quả là `Integer.MIN_VALUE`.

Đối với `d2l`/`f2l`, áp dụng tương tự với miền `long` và `Long.MAX_VALUE/MIN_VALUE`.

~~~java
System.out.println((int) Double.NaN);               // 0
System.out.println((int) Double.POSITIVE_INFINITY); // 2147483647
System.out.println((int) Double.NEGATIVE_INFINITY); // -2147483648
System.out.println((int) 3.99);                     // 3
System.out.println((int) -3.99);                    // -3
~~~

Đừng cho rằng ép kiểu số thực sang số nguyên sẽ **ném ngoại lệ** khi đầu vào NaN hoặc vô cực. Nếu nghiệp vụ cần từ chối những giá trị này, hãy kiểm tra `Double.isFinite(x)` hoặc `Float.isFinite(x)` trước cast, và chủ động kiểm tra miền giá trị hợp lệ.

### Phân biệt ép primitive và cast tham chiếu

- `i2d`, `d2i` và tương tự: **chuyển giá trị primitive**.
- `checkcast`: **kiểm tra/ép kiểu tham chiếu** và có thể ném `ClassCastException`.
- `instanceof`: kiểm tra quan hệ kiểu runtime của tham chiếu.

Ba việc này có tên “cast” trong cách diễn đạt thông thường nhưng sử dụng cơ chế bytecode khác nhau. `int` sang `Integer` còn có thể biên dịch thành **boxing** qua lời gọi thư viện như `Integer.valueOf`, không phải `checkcast`.

## 8. Chương trình Java 17+ chạy được: đối chiếu từng nhóm

Tạo tệp **`BytecodeOpsDemo.java`** có tên trùng `public class`:

~~~java
public class BytecodeOpsDemo {
    static int add(int a, int b) {
        return a + b;
    }

    static int bits(int a, int b) {
        return (a & b) ^ (a << 1);
    }

    static int unsignedShift(int value) {
        return value >>> 1;
    }

    static boolean lessThanLong(long a, long b) {
        return a < b;
    }

    static boolean lessThanDouble(double a, double b) {
        return a < b;
    }

    static int toInt(double value) {
        return (int) value;
    }

    static byte toByte(int value) {
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(7, 5));
        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("remainder=" + (-7 % 3));
        System.out.println("and=" + (10 & 12));
        System.out.println("or=" + (10 | 12));
        System.out.println("xor=" + (10 ^ 12));
        System.out.println("not=" + (~10));
        System.out.println("bitMethod=" + bits(10, 12));
        System.out.println("signedShift=" + (-8 >> 1));
        System.out.println("unsignedShift=" + unsignedShift(-8));
        System.out.println("longLess=" + lessThanLong(4L, 9L));
        System.out.println("nanLess=" + lessThanDouble(Double.NaN, 1.0));
        System.out.println("cast=" + toInt(3.9));
        System.out.println("nanCast=" + toInt(Double.NaN));
        System.out.println("infinityCast=" + toInt(Double.POSITIVE_INFINITY));
        System.out.println("byteCast=" + toByte(130));
        System.out.println("floatDivide=" + (1.0 / 0.0));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 BytecodeOpsDemo.java
java BytecodeOpsDemo
~~~

**Stdout chính xác:**

~~~text
add=12
overflow=-2147483648
remainder=-1
and=8
or=14
xor=6
not=-11
bitMethod=28
signedShift=-4
unsignedShift=2147483644
longLess=true
nanLess=false
cast=3
nanCast=0
infinityCast=2147483647
byteCast=-126
floatDivide=Infinity
~~~

Kiểm tra kỹ `bitMethod=28`: `(10 & 12) = 8`, còn `(10 << 1) = 20`; `8 ^ 20 = 28`. Không cộng số học hai kết quả này; `^` là XOR từng bit.

### Xem bytecode bằng javap

~~~bash
javap -c -p BytecodeOpsDemo
~~~

Bạn có thể tìm các dấu hiệu trong phương thức đã tách riêng:

| Phương thức | Instruction chính dự kiến khi biên dịch bằng `javac` thông thường |
| --- | --- |
| `add` | `iload_0`, `iload_1`, `iadd`, `ireturn` |
| `bits` | `iand`, `ishl`, `ixor` |
| `unsignedShift` | `iushr` |
| `lessThanLong` | `lcmp` và một opcode `if...` |
| `lessThanDouble` | `dcmpg` và một opcode nhánh để bảo đảm NaN cho false |
| `toInt` | `d2i`, `ireturn` |
| `toByte` | `i2b`, `ireturn` |

Đây là **kỳ vọng theo compiler Java thông thường**, không phải bản dump exact có số offset/chỉ mục constant pool bắt buộc. Compiler được phép sinh những chuỗi bytecode khác nhưng phải giữ ngữ nghĩa Java. Trong `main`, thao tác nối chuỗi khi in có thể liên quan §invokedynamic§ hoặc các lời gọi thư viện; không nên nhầm những lệnh tạo chuỗi ấy với opcode số học đang khảo sát.

### Minh họa quá trình stack cho `add(7, 5)`

~~~text
Local variables: [0]=7, [1]=5
Stack ban đầu: []

iload_0  → Stack [7]
iload_1  → Stack [7, 5]
iadd     → Stack [12]
ireturn  → Trả 12 về caller
~~~

Với `lessThanLong(4L, 9L)`, `lcmp` có thể đẩy kết quả int `-1` rồi nhánh điều kiện biến nó thành boolean đúng. Với `lessThanDouble(Double.NaN, 1.0)`, `dcmpg` có thể đẩy `1`, vì vậy điều kiện `<` được coi false như yêu cầu Java.

## 9. Những khác biệt quan trọng giữa toán tử Java và opcode JVM

### Compiler có thể gấp hằng (constant folding)

Đối với biểu thức thuần hằng như `2 + 3` hoặc `10 & 12`, compiler có thể tính sẵn giá trị và phát instruction nạp hằng, thay vì tạo `iadd` hoặc `iand`. Muốn **quan sát opcode** cụ thể, nên dùng phương thức nhận tham số động như `add(int,int)`, `bits(int,int)` trong ví dụ.

### Chuỗi cộng không phải phép cộng số

Trong mã nguồn, `"total=" + value` là **string concatenation**, không phải `iadd` hay `dadd`. Với JDK 17, `javac` thường dùng cơ chế `invokedynamic` phục vụ ghép chuỗi. Đừng tìm một opcode kiểu `sadd`: JVM không có lệnh cộng chuỗi primitive riêng.

### Numeric promotion trước khi thực hiện phép toán

Cú pháp:

~~~java
byte a = 100;
byte b = 20;
// byte result = a + b; // Không biên dịch: a + b có kiểu int.
int result = a + b;
~~~

Dù hai toán hạng là §byte§, Java thực hiện **binary numeric promotion** và biểu thức có kiểu §int§. JVM thường sử dụng `iadd`. Muốn lưu trở lại §byte§, cần cast rõ hoặc compound assignment theo ngữ nghĩa Java:

~~~java
byte resultByte = (byte) (a + b); // 120
~~~

Đây là đoạn minh họa phương thức; cast còn có thể phát `i2b`. Việc dùng `byte`/`short`/`char` không làm bytecode chuyển sang một bộ instruction arithmetic 8/16-bit riêng.

### Phương thức thư viện không phải opcode chuyên dụng

`Math.abs`, `Math.addExact`, `Integer.compareUnsigned`, `BigDecimal.add`, `Double.compare` không phải tên instruction trong JVMS. Compiler có thể phát lời gọi phương thức; JVM/JIT có thể tối ưu hoặc sử dụng intrinsic trong runtime cụ thể, nhưng **định dạng bytecode của phương thức gọi** vẫn tuân thủ instruction set JVM chứ không mặc nhiên có opcode cùng tên API.

### Tính tràn của `int` khác `float` và `double`

- Với `iadd`, kết quả là giá trị bit-width cố định modulo 2^32 (diễn giải có dấu), không tự sinh Infinity hoặc NaN.
- Với `fadd`/`dadd`, kết quả có thể được làm tròn, tràn về vô cực hoặc mang NaN.
- Với `idiv`, số chia 0 ném `ArithmeticException`; với `ddiv`, `1.0 / 0.0` là Infinity, còn `0.0 / 0.0` là NaN.

Không thể dùng một quy tắc “phép toán / luôn ném khi chia cho 0” cho cả hai họ kiểu.

## 10. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân | Hướng điều tra/xử lý |
| --- | --- | --- |
| `int` cộng số lớn biến thành âm | Overflow 32-bit không có exception | Dùng `Math.addExact` khi cần phát hiện; `long`/`BigInteger` khi cần miền lớn. |
| `Integer.MIN_VALUE / -1` không thành số dương | Thương toán học không biểu diễn được trong int | Kiểm tra riêng trường hợp biên, chọn kiểu lớn hơn nếu cần. |
| §byte + byte§ không gán trực tiếp lại §byte§ | Binary numeric promotion thành int | Dùng biến int hoặc cast có kiểm tra miền. |
| `-7 % 3` ra `-1` | Java remainder có dấu theo số bị chia | Dùng `Math.floorMod` nếu cần modulo theo quy ước khác. |
| `>>>` trên số âm cho kết quả dương lớn | Bit cao lấp 0, không giữ sign bit | Phân biệt `ishr` với `iushr` và độ rộng 32/64. |
| `1 << 32` ra 1 | Shift count int chỉ dùng 5 bit thấp | Mask khoảng dịch và validate số bit mong đợi. |
| So sánh NaN bằng `<` hoặc `>` đều false | NaN unordered; compiler dùng `fcmpg/fcmpl` hoặc `dcmpg/dcmpl` đúng ngữ nghĩa | Kiểm tra `Double.isNaN`/`Double.isFinite` khi cần. |
| Cast `Double.NaN` thành `int` ra 0 | Quy tắc narrowing floating-point → integer | Validate dữ liệu trước ép kiểu. |
| Cast vô cực thành `int` không ném exception | Narrowing bị giới hạn tại biên miền int/long | Kiểm tra hữu hạn và khoảng giá trị. |
| Không thấy `iadd` trong `2 + 3` | Compiler đã constant fold | Quan sát phương thức nhận tham số động. |
| `javap -c` không giống “mỗi toán tử một opcode” | Nạp/lưu stack, branch, calls và tối ưu | Đọc toàn bộ stack flow, không so từng ký hiệu máy móc. |
| Bytecode lỗi type/stack không chạy | Không thỏa điều kiện verifier | Xem `VerifyError`, định dạng class và stack map; không tự phát bytecode sai. |

### Cách đọc §javap§ có hệ thống

1. Xác định chữ ký phương thức (tham số, kiểu trả về), chú ý một tham số `long`/`double` dùng hai slot trong local variable array theo quy tắc JVM.
2. Theo dõi local variables được nạp bằng `iload`, `lload`, `fload`, `dload`.
3. Vẽ operand stack sau mỗi instruction. Với lệnh binary, operand ở đỉnh là giá trị thứ hai.
4. Nhận diện opcode tính toán, chuyển kiểu, so sánh và nhánh; tách chúng khỏi lời gọi `invoke*`.
5. Quan sát đường đi khi nhánh đúng/sai; bảo đảm stack shape hợp lệ tại điểm hội tụ.
6. Với thông tin phụ, dùng `javap -v -p TênLớp` để xem thêm constant pool, descriptor, StackMapTable và các thuộc tính khác.

**Đừng cố suy ra toàn bộ source Java ban đầu chỉ từ vài instruction**: nhiều cách viết nguồn có thể biên dịch thành bytecode tương đương, đặc biệt khi có constant folding hoặc compiler tối ưu.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `iadd` lấy hai số từ đâu? `iinc` có giống không?

**Đáp án:** `iadd` pop hai giá trị int từ operand stack rồi push tổng. `iinc` tăng một local variable kiểu int bằng hằng đã mã hóa, không lấy hai toán hạng từ stack.

**Câu 2.** `idiv` và `ddiv` khác nhau thế nào khi số chia bằng 0?

**Đáp án:** `idiv` ném `ArithmeticException`, còn `ddiv` tuân thủ IEEE 754: tùy tử số và dấu, có thể ra vô cực hoặc NaN.

**Câu 3.** Hai toán hạng là `byte`, tại sao thường thấy `iadd`?

**Đáp án:** Java binary numeric promotion biến biểu thức cộng thành int; JVM không có opcode `badd` riêng.

**Câu 4.** Với `int x = -8`, `x >> 1` và `x >>> 1` khác gì?

**Đáp án:** `>>` giữ dấu nên ra -4; `>>>` đưa 0 vào bit cao nên ra 2147483644.

**Câu 5.** `1 << 32` bằng bao nhiêu và vì sao?

**Đáp án:** Bằng 1, vì shift count với int chỉ sử dụng 5 bit thấp: 32 trở thành khoảng dịch 0.

**Câu 6.** `lcmp` trả gì khi value1 nhỏ hơn value2? Nó trực tiếp trả `boolean` chứ?

**Đáp án:** Push số nguyên -1 lên stack, không trực tiếp trả một boolean Java. Compiler dùng thêm nhánh để xây dựng kết quả boolean nếu cần.

**Câu 7.** Vì sao `dcmpg` và `dcmpl` khác nhau khi gặp NaN?

**Đáp án:** NaN unordered; `dcmpg` chọn kết quả int +1 và `dcmpl` chọn -1. Hai loại cho phép compiler tạo nhánh đúng ngữ nghĩa mọi phép so sánh của Java.

**Câu 8.** `(int) Double.NaN`, `(int) Double.POSITIVE_INFINITY` và `(int) -3.9` cho kết quả gì?

**Đáp án:** Lần lượt 0, 2147483647 và -3. Trường hợp NaN và Infinity do quy tắc narrowing đặc biệt, số hữu hạn bị bỏ phần lẻ hướng 0.

**Câu 9.** `i2d` có mất chính xác với bất kỳ `int` nào không? `l2d` thì sao?

**Đáp án:** `i2d` bảo toàn chính xác mọi giá trị int 32-bit; `l2d` có thể mất bit thấp của long quá lớn vì double chỉ có 53 bit phần trị hiệu dụng.

**Câu 10.** Tại sao có khi mã Java `2 + 3` không có `iadd` trong disassembly?

**Đáp án:** Compiler có thể tính hằng tại compile time thành 5 và sinh instruction nạp 5; không phải JVM bỏ phép cộng sai.

## 12. Sơ đồ ghi nhớ

~~~text
Toán tử Java                     Opcode JVM điển hình
--------------------------------------------------------
int a+b, a-b, a*b                iadd / isub / imul
long a/b, a%b                    ldiv / lrem
float/double arithmetic          fadd..frem / dadd..drem
int/long bitwise &, |, ^         iand/ior/ixor, land/lor/lxor
int/long <<, >>, >>>             ishl/ishr/iushr, lshl/lshr/lushr
int local++                      có thể dùng iinc
int a < b                        thường if_icmplt
long a < b                       lcmp rồi branch
float/double a < b               fcmpg/dcmpg rồi branch
(int) someDouble                 d2i
(byte) someInt                   i2b

Operand stack: ... value1, value2 → ... result
Instruction branch: pop operand, thay đổi control flow, không push boolean
~~~

**Điểm cốt lõi:** học bytecode theo **kiểu operand, quy tắc stack và semantics của instruction**, không theo suy đoán “mỗi toán tử Java bằng đúng một lệnh”. Với số nguyên, quan sát độ rộng bit, overflow và dịch bit; với số thực, quan sát NaN/vô cực và làm tròn; với so sánh, phân biệt opcode tạo kết quả với nhánh; với chuyển kiểu, xác định chỗ mất dữ liệu.

## Tài liệu chuẩn

- [JVMS Java SE 21 — §2.11 Instruction Set Summary](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.11).
- [JVMS Java SE 21 — §6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JLS Java SE 21 — §5 Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html).
- [JLS Java SE 21 — §15 Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html).
- [JDK 21 — javap documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).

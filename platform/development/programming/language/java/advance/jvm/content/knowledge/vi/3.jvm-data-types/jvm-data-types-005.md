# Số nguyên tràn, phép chuyển kiểu và ngữ nghĩa phép toán bytecode

Trong Java, một phép cộng `int` có thể cho ra số âm dù hai toán hạng đều dương; ép `int` về `byte` có thể đổi cả dấu lẫn giá trị; và ép sang `long` **sau** khi phép tính đã tràn không lấy lại được phần thông tin mất đi. Đây là **ngữ nghĩa được quy định** bởi Java Language Specification (JLS) và Java Virtual Machine Specification (JVMS), không phải lỗi ngẫu nhiên của CPU hay HotSpot.

Mục tiêu của bài: hiểu chính xác số nguyên JVM được biểu diễn và xử lý như thế nào; theo dõi **kiểu của từng toán hạng → phép toán → kết quả → phép chuyển kiểu**; đọc các lệnh bytecode tương ứng; và chọn cách phát hiện tràn khi dữ liệu không được phép mất.

## 1. Bức tranh số nguyên ở Java và ở JVM

### Kiểu dữ liệu, độ rộng và miền giá trị

| Kiểu Java | Số bit | Miền giá trị | Đặc điểm |
| --- | ---: | --- | --- |
| `byte` | 8 | -128 đến 127 | Số nguyên có dấu |
| `short` | 16 | -32.768 đến 32.767 | Số nguyên có dấu |
| `char` | 16 | 0 đến 65.535 | Giá trị nguyên *không dấu*, thường đại diện một UTF-16 code unit |
| `int` | 32 | -2.147.483.648 đến 2.147.483.647 | Kiểu nguyên thông dụng trong phép toán JVM |
| `long` | 64 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Kiểu nguyên 64 bit có dấu |

`boolean` là kiểu riêng, không phải số nguyên và không thể cộng, ép số bằng numeric cast. `float`/`double` là kiểu dấu phẩy động với ngữ nghĩa IEEE 754, không sử dụng cùng phép tràn dạng modulo của `int`/`long`.

Giá trị nguyên có dấu được diễn giải theo **two's complement (bù hai)**. Ví dụ, mẫu 32 bit `0xFFFF_FFFF` biểu thị `-1` khi xem là `int` có dấu; cùng mẫu bit có thể được API unsigned đọc thành `4.294.967.295`. Đổi cách diễn giải **không đổi** số bit lưu trữ.

Trong **operand stack** của JVM, nhiều thao tác trên `byte`, `short`, `char` và `boolean` sử dụng loại tính toán `int`; kiểu khai báo nhỏ vẫn tồn tại trong mô tả field, array, method signature và các bước thu hẹp/chuyển về kiểu đích. JVM không có đầy đủ một họ lệnh cộng riêng `badd`, `sadd`, `cadd` cho ba kiểu nhỏ. `long` có họ lệnh riêng `ladd`, `lsub`, `lmul`, v.v.

Ví dụ suy luận đúng phải hỏi: “Tại **thời điểm thực hiện phép cộng**, toán hạng đang là `int` hay `long`?”, thay vì chỉ xem kiểu của biến nhận kết quả.

## 2. Tràn `int` và `long` là quy tắc xác định

Với toán tử nguyên như `+`, `-`, `*`, phép đổi dấu `-x`, Java giữ lại **32 bit thấp** của kết quả toán học nếu phép tính có kiểu `int`, hoặc **64 bit thấp** nếu có kiểu `long`. Sau đó các bit này được diễn giải bằng two's complement.

Có thể hình dung:

- Tính tổng/tích toán học đủ độ rộng.
- Lấy kết quả theo modulo `2^32` cho `int` hoặc `2^64` cho `long`.
- Diễn giải mẫu bit kết quả là số **có dấu** của kiểu tương ứng.

Ví dụ:

```java
int largest = Integer.MAX_VALUE;  // 2_147_483_647
int wrapped = largest + 1;        // -2_147_483_648
long wide = Long.MAX_VALUE + 1;    // -9_223_372_036_854_775_808
```

Ba dòng trên là **trích đoạn minh họa**, không phải file độc lập. Phép `largest + 1` có kiểu `int`, kết quả toán học `2_147_483_648` vượt `int`, mẫu 32 bit thấp là `0x8000_0000`, được diễn giải thành `Integer.MIN_VALUE`.

| Phép toán số nguyên | Hành vi tràn | Exception do *tràn*? |
| --- | --- | --- |
| `iadd`/`ladd`; `isub`/`lsub`; `imul`/`lmul` | Cắt còn 32/64 bit thấp | Không |
| `ineg`/`lneg`, ví dụ `-Integer.MIN_VALUE` | Vẫn là `Integer.MIN_VALUE` / `Long.MIN_VALUE` | Không |
| `iinc` với biến cục bộ `int` | Cộng hằng số và giữ 32 bit thấp | Không |
| Chia nguyên `idiv`/`ldiv` với số chia `-1` và số bị chia nhỏ nhất | Kết quả vẫn bằng `MIN_VALUE` | Không |
| Chia hoặc lấy dư nguyên với số chia `0` | Không có kết quả nguyên hợp lệ | **`ArithmeticException`** |
| Chuyển kiểu thu hẹp `i2b`, `i2s`, `i2c`, `l2i` | Mất các bit cao | Không, kể cả mất giá trị |
| `Math.addExact`, `Math.multiplyExact`, v.v. | Kiểm tra tràn theo hợp đồng API | **`ArithmeticException`** khi tràn |

Không có chế độ mặc định như “checked arithmetic” buộc mọi lệnh `iadd` phải ném lỗi khi tràn. Compiler hoặc JVM có thể tối ưu cách thực thi, nhưng **kết quả quan sát được** của biểu thức nguyên vẫn phải tuân theo ngữ nghĩa Java.

### Điểm dễ nhầm: tràn không phải phép cộng dấu phẩy động

`double x = Double.MAX_VALUE * 2;` có thể thành `Infinity` thay vì quấn về một số âm. `double a = 1.0 / 0.0;` trả `Infinity`, trong khi `int a = 1 / 0;` có thể bị phát hiện ngay ở biểu thức hằng hoặc gây `ArithmeticException` khi thực hiện ở runtime; để quan sát hành vi runtime, dùng biến số chia. Không áp dụng quy tắc `iadd` cho `fadd`, `dadd` hoặc `ddiv`.

## 3. Khi chuyển sang `long`: thời điểm chuyển kiểu quyết định đúng/sai

Xét phép nhân hai giá trị:

```java
int amount = 1_500_000_000;
long wrong = amount * 2;
long correct = (long) amount * 2;
```

- `amount * 2` được tính dưới kiểu `int`, tràn thành **`-1_294_967_296`**; gán vào `long` chỉ sign-extend giá trị âm *đã sai*.
- `(long) amount * 2` chuyển toán hạng đầu sang `long` **trước khi nhân**, nên phép nhân là `long` và cho **`3_000_000_000`**.

Cùng vấn đề với dấu ngoặc:

```java
int max = Integer.MAX_VALUE;
long tooLate = (long) (max + 1); // -2147483648
long inTime = (long) max + 1;    //  2147483648
```

**Quy tắc:** kiểu của **phép tính đang diễn ra** quyết định độ rộng; kiểu của biến bên trái dấu `=` không có khả năng sửa một phép tính đã tràn.

Đổi sớm sang `long` giúp giảm nguy cơ nhưng `long` cũng có giới hạn 64 bit và vẫn tràn nếu vượt miền giá trị. Với số tiền lớn, bộ đếm an toàn, kích thước dữ liệu, hoặc phép nhân nhiều bước, cần xác định rõ miền đầu vào và có thể dùng `Math.*Exact` hay `BigInteger`.

### Promotion cho kiểu nhỏ

Với các phép số học hai toán hạng thường gặp (`+`, `-`, `*`, `/`, `%`), `byte`, `short`, `char` được **binary numeric promotion** về ít nhất `int` trước khi tính. Ví dụ:

```java
byte a = 100;
byte b = 20;
// byte c = a + b; // LỖI biên dịch: a+b có kiểu int
int sum = a + b;   // đúng, sum = 120
byte c = (byte) (a + b); // đúng cú pháp, nhưng có thể mất dữ liệu
```

Ngoại lệ đáng nhớ ở ngữ cảnh gán:

- `byte b = 127;` biên dịch được: hằng `int` biểu diễn vừa `byte` được phép thu hẹp theo quy tắc constant assignment.
- `byte b = 128;` lỗi biên dịch: hằng ngoài miền `byte`.
- `byte b = 127; b++;` hợp lệ; phép tăng có bước chuyển về kiểu `byte` và kết quả thành `-128`.
- `byte b = 127; b += 1;` cũng hợp lệ; phép gán kết hợp có phép cast ngầm về kiểu bên trái. Còn `b = b + 1;` cần cast tường minh vì kết quả phép cộng là `int`.

Việc hằng được compiler chấp nhận không làm mất quy tắc tràn runtime. Tương tự, một biểu thức hằng nguyên có thể được compiler tính trước nhưng vẫn phải giữ quy tắc overflow của kiểu nguyên.

## 4. Chuyển kiểu nguyên: giữ bit thấp, sau đó xác định có dấu hay không

Phép **widening** từ kiểu nguyên hẹp sang kiểu nguyên rộng hơn:

- `byte`/`short`/`int` là số có dấu; mở rộng sang kiểu có nhiều bit hơn bằng **sign extension**.
- `char` không dấu; mở rộng sang `int`/`long` bằng **zero extension**.
- Widening từ số nguyên sang số nguyên rộng hơn bảo toàn **giá trị**; ngược lại, widening `int → float` hoặc `long → double` có thể mất **độ chính xác**, vì dấu phẩy động có số bit phần trị hữu hạn.

Phép **narrowing** từ kiểu nguyên rộng sang kiểu hẹp:

- `int → byte` giữ 8 bit thấp; `int → short`/`char` giữ 16 bit thấp.
- `long → int` giữ 32 bit thấp; chuyển `long` sang `byte`/`short`/`char` có thể tương ứng hai bước thu hẹp trong bytecode.
- Kiểu đích `byte` và `short` đọc bit dấu theo two's complement; `char` xem 16 bit kết quả là một số **không dấu**.
- Chuyển kiểu nguyên **không tự kiểm tra** giá trị có vừa đích không. `(byte) 130` là `-126`, không ném exception.

Các ví dụ từng bit:

| Biểu thức | Phần bit còn giữ | Giá trị |
| --- | --- | ---: |
| `(byte) 130` | `0x82` (8 bit) | -126 |
| `(byte) 255` | `0xFF` (8 bit) | -1 |
| `(short) 65535` | `0xFFFF` (16 bit) | -1 |
| `(char) (-1)` | `0xFFFF` (16 bit) | 65535 |
| `(int) 0x1_0000_0001L` | `0x0000_0001` (32 bit) | 1 |
| `(long) (byte) 255` | `0xFFFF_FFFF_FFFF_FFFF` | -1 |

Điều cuối cùng thể hiện **thu hẹp rồi mới mở rộng**: cast sang `byte` biến `255` thành `-1`, mở sang `long` chỉ bảo toàn `-1`, không lấy lại `255`. Nếu nhận byte thô của giao thức cần hiểu theo khoảng 0–255, thường dùng `value & 0xFF` khi `value` có kiểu `byte` đã được promote sang `int`, hoặc `Byte.toUnsignedInt(value)`.

### Ví dụ Java 17: chuyển kiểu và mất bit

Tạo **`NarrowingConversions.java`**:

```java
public class NarrowingConversions {
    public static void main(String[] args) {
        System.out.println("byte130=" + (byte) 130);
        System.out.println("byte255=" + (byte) 255);
        System.out.println("short65535=" + (short) 65535);
        System.out.println("charMinus1=" + (int) (char) -1);
        System.out.println("longToInt=" + (int) 0x1_0000_0001L);

        byte counter = 127;
        counter++;
        System.out.println("counter=" + counter);

        byte raw = (byte) 255;
        System.out.println("unsignedByte=" + Byte.toUnsignedInt(raw));
    }
}
```

Biên dịch, chạy:

```bash
javac --release 17 NarrowingConversions.java
java NarrowingConversions
```

**Stdout chính xác**:

```text
byte130=-126
byte255=-1
short65535=-1
charMinus1=65535
longToInt=1
counter=-128
unsignedByte=255
```

Điểm chính: `byte`, `short` và `char` có cùng khả năng mất bit cao khi narrowing, nhưng diễn giải bit dấu **khác nhau**. `Byte.toUnsignedInt` chỉ đổi cách biểu diễn giá trị sang `int` dương, không thay đổi byte gốc.

## 5. Chuyển `float`/`double` sang số nguyên không chỉ đơn giản là “giữ bit thấp”

Java có quy tắc hai giai đoạn với narrowing từ dấu phẩy động sang kiểu nguyên:

1. Chuyển về `int` hoặc `long` bằng cách **làm tròn về 0** nếu là số hữu hạn và nằm trong miền biểu diễn. Giá trị NaN cho **0**; quá lớn/+∞ cho `MAX_VALUE`; quá nhỏ/−∞ cho `MIN_VALUE` tương ứng.
2. Nếu kiểu đích là `byte`, `short` hay `char`, tiếp tục **narrowing** từ `int` theo quy tắc giữ bit thấp.

Điều này khác việc “ép `double` thẳng về `byte` bằng cách chỉ lấy 8 bit của phần thập phân”. Ví dụ `(byte) 130.5`: trước hết `(int) 130.5 = 130`, rồi `(byte) 130 = -126`.

Tạo file **`FloatingToInteger.java`**:

```java
public class FloatingToInteger {
    public static void main(String[] args) {
        System.out.println("positive=" + (int) 3.9);
        System.out.println("negative=" + (int) -3.9);
        System.out.println("NaN=" + (int) Double.NaN);
        System.out.println("plusInfinity=" + (int) Double.POSITIVE_INFINITY);
        System.out.println("minusInfinity=" + (int) Double.NEGATIVE_INFINITY);
        System.out.println("doubleToByte=" + (byte) 130.5);
    }
}
```

```bash
javac --release 17 FloatingToInteger.java
java FloatingToInteger
```

**Stdout**:

```text
positive=3
negative=-3
NaN=0
plusInfinity=2147483647
minusInfinity=-2147483648
doubleToByte=-126
```

Cần hiểu kỹ: ép `double` sang `int` **không ném `ArithmeticException`** vì giá trị vượt miền; đó là lý do rất nguy hiểm nếu dữ liệu đầu vào phải chính xác. Nếu ứng dụng cần phát hiện giá trị NaN/vô hạn, ngoài miền hoặc có phần lẻ, hãy kiểm tra tường minh *trước khi cast*.

Ngược chiều `int → float` cũng có thể làm tròn mất chính xác, dù nó được gọi là **widening primitive conversion** theo hệ thống kiểu. Ví dụ `(float) 16_777_217` thành `16_777_216.0` do số bit phần trị của `float`; “widening” không luôn có nghĩa “mọi bit giá trị được giữ nguyên” khi đổi từ nguyên sang dấu phẩy động.

## 6. Phép chia nguyên, dấu của số dư và trường hợp cực trị

Java chia hai số nguyên với thương **làm tròn về 0** (truncation toward zero), không phải làm tròn xuống âm vô cùng:

| Biểu thức | Giá trị |
| --- | ---: |
| `7 / 3` | 2 |
| `-7 / 3` | -2 |
| `7 / -3` | -2 |
| `-7 % 3` | -1 |
| `7 % -3` | 1 |
| `Integer.MIN_VALUE / -1` | -2.147.483.648 |
| `Integer.MIN_VALUE % -1` | 0 |

Số dư khác 0 có cùng dấu với **số bị chia**. Vì thế `-7 % 3` là `-1`, không phải `2`. Nếu cần phép chia theo hướng floor (ví dụ phép tính ngày tháng hoặc chia nhóm với số âm), xem `Math.floorDiv` và `Math.floorMod`; đừng thay đổi quy tắc của toán tử `/`, `%` bằng suy luận toán học thiếu phần làm tròn.

**Trường hợp đặc biệt**: `Integer.MIN_VALUE / -1` có thương toán học `2147483648` không thể biểu diễn bởi `int`. Theo JLS/JVMS, kết quả là **`Integer.MIN_VALUE`**, không ném overflow exception. Tương tự với `Long.MIN_VALUE / -1L`.

Chia nguyên cho **0** làm phát sinh `ArithmeticException`; ví dụ runtime hợp lệ:

```java
int divisor = 0;
try {
    System.out.println(42 / divisor);
} catch (ArithmeticException ex) {
    System.out.println("division by zero");
}
```

Đây là **đoạn minh họa trong một method**, không phải chương trình độc lập. Output của `catch` là `division by zero`. Với `double`, `42.0 / 0.0` cho `Infinity`, khác quy tắc chia số nguyên. Lệnh bytecode tương ứng là `idiv`/`ldiv` so với `ddiv`/`fdiv`.

## 7. Phép dịch bit không phải phép nhân/chia vô hạn độ rộng

Các toán tử dịch làm việc trên mẫu bit có kích thước cố định:

- `<<` dịch trái, đưa số 0 vào phần bit thấp. Bit cao bị loại bỏ, nên có thể đổi dấu hoặc mất dữ liệu.
- `>>` dịch phải **có dấu**: đưa bản sao bit dấu vào bên trái (sign extension).
- `>>>` dịch phải **không dấu**: đưa bit 0 vào bên trái (zero fill); nó không đổi kiểu Java thành unsigned.
- Với toán hạng trái kiểu `int`, khoảng dịch chỉ dùng **5 bit thấp** của khoảng dịch: hiệu dụng là `distance & 0x1F` (modulo 32).
- Với toán hạng trái kiểu `long`, chỉ dùng **6 bit thấp**: `distance & 0x3F` (modulo 64).
- Các `byte`/`short`/`char` ở vế trái được **unary numeric promotion** lên `int` trước khi dịch; kiểu vế phải không khiến kết quả của `int << 1L` trở thành `long`.

Ví dụ:

```java
System.out.println(1 << 32);   // 1: 32 & 31 = 0
System.out.println(1L << 64);  // 1: 64 & 63 = 0
System.out.println(-1 >> 1);   // -1
System.out.println(-1 >>> 1);  // 2147483647
```

Có thể nhìn thấy lệnh bytecode tương ứng: `ishl`/`lshl`, `ishr`/`lshr`, `iushr`/`lushr`. Khi giải mã một trường nhị phân, checksum hoặc màu ARGB, luôn quy định **độ rộng kiểu** và thao tác mask cụ thể; một shift vượt 31 cho `int` không có nghĩa tất cả bit đều biến mất.

### Unsigned là cách diễn giải, không phải kiểu Java mới

`int` vẫn là kiểu có dấu 32 bit; Java cung cấp các API như `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedLong`, `Integer.toUnsignedString`. Ví dụ `Integer.toUnsignedLong(-1)` là `4294967295L`. Dịch `>>>` cũng chỉ thao tác trên 32/64 bit hiện có; nó không làm một biến `int` có thêm miền lưu trữ.

## 8. Từ Java source đến lệnh JVM: nhìn chính xác chuỗi tính và cast

JVM thường thực thi logic theo **operand stack**: nạp giá trị, đặt toán hạng lên stack, một opcode lấy toán hạng rồi đẩy kết quả, sau đó có thể cast hoặc return. Với `int`, một giá trị trên stack có loại `int`; với `long`, dùng loại `long`.

Bảng một số opcode cốt lõi trong JVMS 17:

| Opcode | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| `iadd`, `isub`, `imul`; `ladd`, `lsub`, `lmul` | Cộng, trừ, nhân `int`/`long` | Wrap 32/64 bit; không exception do tràn |
| `ineg`/`lneg` | Đổi dấu số nguyên | `-MIN_VALUE == MIN_VALUE` |
| `iinc` | Tăng biến cục bộ `int` một hằng có dấu | Wrap; opcode này làm việc với local variable, không phải mọi biến/đối tượng |
| `idiv`/`ldiv`; `irem`/`lrem` | Chia, lấy dư `int`/`long` | Số chia 0 ném `ArithmeticException` |
| `i2l` | `int → long` | Sign extension; bản thân phép mở rộng là chính xác |
| `l2i` | `long → int` | Giữ 32 bit thấp |
| `i2b`, `i2s` | `int → byte/short` | Giữ 8/16 bit rồi **sign-extend trở lại int trên stack** |
| `i2c` | `int → char` | Giữ 16 bit rồi **zero-extend trở lại int trên stack** |
| `f2i`, `d2i`, `f2l`, `d2l` | Floating-point → integral | Làm tròn về 0; NaN về 0; giá trị ngoài miền bị clamp |
| `ishl`, `ishr`, `iushr` | Dịch `int` | Chỉ dùng 5 bit thấp của khoảng dịch |
| `lshl`, `lshr`, `lushr` | Dịch `long` | Chỉ dùng 6 bit thấp của khoảng dịch |

Cần đặc biệt phân biệt **kiểu giá trị bytecode operand stack** với **kiểu Java của kết quả biểu thức/biến**. Ví dụ `i2b` không tạo ra kiểu operand stack riêng “byte”: theo mô tả instruction, nó thu hẹp về 8 bit rồi sign-extend thành **int** trên stack; code sinh ra vẫn đảm bảo giá trị đáp ứng phạm vi `byte`.

### Chương trình độc lập có thể dịch ngược bằng `javap`

Tạo file **`IntegerBytecode.java`**:

```java
public class IntegerBytecode {
    public static int add(int a, int b) {
        return a + b;
    }

    public static byte narrow(int value) {
        return (byte) value;
    }

    public static long tooLate(int a, int b) {
        return (long) (a + b);
    }

    public static long inTime(int a, int b) {
        return (long) a + b;
    }

    public static int unsignedShift(int value, int bits) {
        return value >>> bits;
    }

    public static int divide(int a, int b) {
        return a / b;
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("add=" + add(max, 1));
        System.out.println("narrow=" + narrow(130));
        System.out.println("tooLate=" + tooLate(max, 1));
        System.out.println("inTime=" + inTime(max, 1));
        System.out.println("unsignedShift=" + unsignedShift(-1, 1));
        System.out.println("divide=" + divide(-7, 3));
    }
}
```

Lệnh với **JDK 17+ có hỗ trợ `--release 17`**:

```bash
javac --release 17 IntegerBytecode.java
java IntegerBytecode
javap -c -p IntegerBytecode
```

**Stdout của lệnh `java IntegerBytecode`**:

```text
add=-2147483648
narrow=-126
tooLate=-2147483648
inTime=2147483648
unsignedShift=2147483647
divide=-2
```

Với lệnh `javap -c -p IntegerBytecode`, bỏ qua địa chỉ offset và lệnh tải/trả về cần thiết, chuỗi opcode chính trong các method có dạng:

```text
add:           iload_0, iload_1, iadd, ireturn
narrow:        iload_0, i2b, ireturn
tooLate:       iload_0, iload_1, iadd, i2l, lreturn
inTime:        iload_0, i2l, iload_1, i2l, ladd, lreturn
unsignedShift: iload_0, iload_1, iushr, ireturn
divide:        iload_0, iload_1, idiv, ireturn
```

Đây là **lược đồ các opcode đáng chú ý**, không phải nguyên văn toàn bộ output `javap`. Compiler có thể chọn sequence khác mà vẫn tuân thủ Java; đầu ra `javap` sẽ chứa offsets và cả method `main`.

Điểm mấu chốt: ở `tooLate`, opcode `iadd` thực hiện **trước** `i2l`; khi `i2l` chạy, phép cộng đã wrap. Ở `inTime`, mỗi toán hạng được mở rộng bằng `i2l`, sau đó `ladd` mới cộng hai `long`, nên `2147483648` không vượt miền 64 bit.

### Theo dõi `iadd` trên operand stack

Ví dụ gọi `add(2147483647, 1)` (dưới đây chỉ là phần liên quan của frame method `add`):

| Thời điểm | Operand stack, từ đáy đến đỉnh | Giải thích |
| --- | --- | --- |
| Trước lệnh đầu | `[]` | `a` và `b` nằm trong local variables |
| Sau `iload_0` | `[2147483647]` | Nạp `a` loại `int` |
| Sau `iload_1` | `[2147483647, 1]` | Nạp `b` loại `int` |
| Sau `iadd` | `[-2147483648]` | Cộng 32 bit, giữ bit thấp theo two's complement |
| Sau `ireturn` | Stack của frame kết thúc | Trả kết quả `int` về caller |

Nếu đọc bytecode và nhìn thấy `i2l` *sau* `iadd`, không được tự suy luận đó là phép cộng `long` chỉ vì method trả `long`.

### `javap` giúp thấy cơ chế, nhưng không phải cam kết source-to-opcode một đối một

- Một phép `a++` có thể được compiler thể hiện bằng `iinc` khi là biến cục bộ `int` phù hợp; tăng field/array có thể cần các opcode load, add, store khác.
- Compiler được phép constant-fold biểu thức hằng, nên không phải dòng source nào chứa `+` cũng sẽ sinh ra `iadd`.
- JIT có thể thay đổi lệnh CPU thực thi, nhưng kết quả quan sát được của phép toán phải giữ đúng contract JVM/Java.

Hãy coi `javap -c` là cách soi **bytecode cụ thể** được compiler tạo ra, còn JLS/JVMS là nguồn xác định **ngữ nghĩa bắt buộc**.

## 9. Khi tràn là lỗi: kiểm tra bằng API và kiểm tra miền

Nếu yêu cầu nghiệp vụ không chấp nhận wrap, hãy phát hiện trước/sau theo API thay vì hy vọng JVM tự báo lỗi:

- `Math.addExact(a, b)`, `subtractExact`, `multiplyExact`: thực hiện phép tính nguyên có kiểm tra tràn, ném `ArithmeticException` nếu kết quả vượt miền.
- `Math.incrementExact`, `decrementExact`, `negateExact`: kiểm tra tràn các phép tương ứng; ví dụ `Math.negateExact(Integer.MIN_VALUE)` sẽ ném lỗi.
- `Math.toIntExact(longValue)`: thu hẹp `long → int` có kiểm tra phạm vi thay cho cast âm thầm loại 32 bit cao.
- Với kết quả có thể vượt `long`, xem `BigInteger` hoặc mô hình dữ liệu thích hợp; với giá trị tiền có phần thập phân, cần xem xét thêm `BigDecimal`/quy ước số đơn vị nhỏ nhất.

Tạo **`CheckedArithmetic.java`**:

```java
public class CheckedArithmetic {
    public static void main(String[] args) {
        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("add overflow detected");
        }

        try {
            System.out.println(Math.toIntExact(3_000_000_000L));
        } catch (ArithmeticException ex) {
            System.out.println("narrowing overflow detected");
        }

        System.out.println("valid=" + Math.multiplyExact(6, 7));
    }
}
```

```bash
javac --release 17 CheckedArithmetic.java
java CheckedArithmetic
```

**Stdout**:

```text
add overflow detected
narrowing overflow detected
valid=42
```

Hai lỗi trên được báo vì ta **gọi API checked**, không phải JVM phát hiện overflow mặc định của `iadd` hay `l2i`.

### Kiểm tra giới hạn không tạo overflow ngay trong biểu thức kiểm tra

Cảnh báo phổ biến khi kiểm tra lát cắt mảng, offset hoặc bộ đệm:

```java
// Có thể sai nếu offset + length bị tràn int:
if (offset + length > capacity) {
    throw new IllegalArgumentException("out of bounds");
}
```

Đây là đoạn trích chưa đủ điều kiện an toàn nếu các giá trị không được kiểm soát. Với các giá trị `int` đại diện offset/length/capacity không âm, kiểm tra an toàn hơn bằng cách loại đầu vào âm và giữ phép trừ trong miền:

```java
if (capacity < 0 || offset < 0 || length < 0
        || offset > capacity || length > capacity - offset) {
    throw new IllegalArgumentException("out of bounds");
}
```

Do `offset <= capacity` được kiểm tra trước vế trừ, `capacity - offset` không âm và không tràn trong miền `int` không âm. Điều kiện `||` short-circuit từ trái sang phải nên phép trừ chỉ được đánh giá khi điều kiện phía trước cho phép.

Vấn đề tương tự xảy ra với `count * elementSize`, `end = start + duration`, tính chỉ số hash, số thứ tự tăng liên tục hoặc chuyển timestamp sang đơn vị nhỏ: **phép kiểm tra cũng phải an toàn với tràn**.

## 10. Sai lầm thường gặp khi đọc source hoặc bytecode

| Nhận định sai | Điều đúng |
| --- | --- |
| “`int` tràn thì JVM ném `ArithmeticException`” | `iadd`/`isub`/`imul` wrap; riêng chia/lấy dư nguyên cho 0 ném lỗi, hoặc dùng các API checked |
| “Gán kết quả vào `long` sẽ chống tràn” | Nếu phép tính `int` đã xong rồi mới widen, phần bị mất không thể phục hồi |
| “`byte + byte` có kiểu `byte`” | Binary numeric promotion cho phép cộng thông thường tạo `int` |
| “`(byte)255` thành 255 nhưng lưu ít bit hơn” | Kết quả là `-1` do bit thấp `0xFF` được diễn giải có dấu |
| “`char` là số nguyên 16 bit có dấu” | `char` biểu diễn giá trị nguyên **không dấu** 0–65535 |
| “`i2b` đẩy giá trị byte 8 bit độc lập lên stack” | Nó thu hẹp, rồi sign-extend trở lại giá trị **int** trên operand stack |
| “`(int) Double.NaN` gây lỗi” | Kết quả là `0`; vô hạn/ngoài miền bị clamp, không gây overflow exception |
| “`>>>` biến `int` thành kiểu unsigned” | Nó chỉ dịch bit với zero-fill; kiểu kết quả vẫn là `int` |
| “Dịch `int` trái 32 vị trí đưa về 0” | Khoảng dịch bị mask 5 bit, `1 << 32` bằng `1` |
| “`-7 / 3` là `-3` như floor division” | Phép chia nguyên Java làm tròn về 0, kết quả `-2` |
| “Nếu source có phép cộng thì `javap` luôn có `iadd`” | Compiler có thể constant-fold, dùng opcode khác hoặc tối ưu với ngữ nghĩa tương đương |

## 11. Quy trình phân tích một phép toán số nguyên

Khi một phép toán cho kết quả lạ, đi từ trên xuống:

1. **Xác định version và kiểu source:** giá trị là `byte`/`short`/`char`/`int`/`long` hay floating-point? `--release` và API tương ứng?
2. **Đặt dấu ngoặc đúng thứ tự đánh giá:** xác định phép cộng/nhân thực hiện trước hay sau cast.
3. **Áp dụng promotion:** phép toán tạo `int`, `long` hay floating-point? Có unboxing hoặc constant expression hay không?
4. **Tính kết quả toán học:** nếu là `int`/`long`, giữ 32/64 bit thấp khi phép cộng/nhân/trừ có thể tràn.
5. **Áp dụng các cast sau đó:** narrowing giữ bit thấp; widening signed sign-extends, `char` zero-extends.
6. **Nếu chia hoặc shift:** nhớ chia nguyên truncation về 0; shift mask 5/6 bit khoảng dịch; phân biệt `>>` với `>>>`.
7. **Đối chiếu bytecode:** `javac --release 17` + `javap -c -p`; theo dõi `iadd`, `i2l`, `ladd`, `i2b`... đúng thứ tự.
8. **Quyết định rủi ro:** wrap có phải thiết kế cố ý (ví dụ hash/bit flags) hay lỗi (ví dụ kích thước, tiền, kiểm tra giới hạn)? Nếu là lỗi, dùng API checked, miền đủ rộng hoặc kiểu số lớn.

### Bài tự kiểm tra nhanh

| Biểu thức Java 17 | Kết quả | Lý do |
| --- | --- | --- |
| `Integer.MAX_VALUE + 1` | `-2147483648` | `int` wrap 32 bit |
| `(long) (Integer.MAX_VALUE + 1)` | `-2147483648L` | Cộng `int` rồi mới `i2l` |
| `(long) Integer.MAX_VALUE + 1` | `2147483648L` | Widen trước, cộng `long` |
| `(byte) 0xFF` | `-1` | Giữ 8 bit rồi diễn giải có dấu |
| `(char) -1` | `65535` | Giữ 16 bit và diễn giải không dấu |
| `(int) Double.NaN` | `0` | Quy tắc float/double → integer |
| `-7 % 3` | `-1` | Dư có dấu của số bị chia |
| `1 << 32` | `1` | 5 bit thấp của khoảng dịch là `0` |
| `-1 >>> 1` | `2147483647` | Dịch phải zero-fill |
| `Math.addExact(Integer.MAX_VALUE, 1)` | Ném `ArithmeticException` | API chủ động kiểm tra tràn |

## 12. Tài liệu gốc (đối chiếu Java SE 17)

- [JLS §4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): phạm vi `byte`, `short`, `int`, `long`, `char`.
- [JLS `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2) và [`5.1.3 — Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3): mở rộng có dấu/không dấu, mất bit, floating-point → integer.
- [JLS `5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6) và [`15.26.2 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26.2): promotion, phép gán kết hợp.
- [JLS `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17) và [`15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): chia nguyên, số dư, wrap khi cộng/nhân.
- [JLS §15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): masking shift distance và các kiểu dịch.
- [JVMS §2.11.3–§2.11.4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.3): tổng quan lệnh arithmetic và conversion; [JVMS §6.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5) mô tả chính xác từng opcode `iadd`, `i2b`, `l2i`, `idiv`, `iushr`.
- [Java SE 17 `Math` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) và [`Integer` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): checked arithmetic, floor division, unsigned interpretation.
- [`javap` tool guide Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): cách đọc bytecode thật được biên dịch.

**Quy tắc cốt lõi:** xác định **kiểu và độ rộng ngay lúc phép toán được thực hiện**, rồi mới xét các bước chuyển kiểu. Khi đọc bytecode, thứ tự `iadd`/`i2l`/`ladd` giải thích vì sao hai biểu thức trông giống nhau ở source có thể cho kết quả khác nhau. Không có kiểm tra overflow tự động cho phép toán nguyên thông thường; hãy lựa chọn chủ động nếu không được phép mất giá trị.

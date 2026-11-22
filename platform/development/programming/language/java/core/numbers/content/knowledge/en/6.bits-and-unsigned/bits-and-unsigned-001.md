# Các toán tử `&`, `|`, `^` và `~` trong Java — Bit và số không dấu

## 1. Mục tiêu của bài học

Trong Java, **toán tử thao tác bit (bitwise operators)** tác động lên từng bit của giá trị số nguyên. Chúng rất hữu ích khi làm việc với cờ trạng thái, quyền được mã hóa thành bit, giao thức nhị phân, dữ liệu thiết bị, trường màu RGB và các phép biến đổi ở mức bit.

Bài này tập trung vào bốn toán tử:

- `&` — AND theo từng bit;
- `|` — OR theo từng bit;
- `^` — XOR theo từng bit;
- `~` — NOT (đảo tất cả các bit).

Sau bài học, bạn cần tự tính được kết quả nhị phân, hiểu vì sao `~12` cho ra `-13`, biết kiểu `byte`/`short`/`char` được nâng lên `int`, sử dụng mặt nạ bit (bitmask), và nhận biết điểm khác biệt giữa thao tác bit với diễn giải số nguyên **có dấu/không dấu**.

**Điều kiện:** đã biết `int`, `long`, literal nhị phân `0b...`, literal hex `0x...` và các toán tử cơ bản. Ví dụ chạy độc lập với JDK 17 trở lên. Java không có kiểu nguyên thủy `unsigned int` hay `unsigned long`; chủ đề “không dấu” ở đây chủ yếu nói về **cách diễn giải bit** và các API hỗ trợ unsigned.

## 2. Bit và biểu diễn số nguyên Java

Mỗi bit chỉ có thể là `0` hoặc `1`. Java sử dụng các kiểu số nguyên có độ rộng xác định:

| Kiểu | Độ rộng | Có dấu? | Lưu ý |
| --- | ---: | --- | --- |
| `byte` | 8 bit | Có dấu | −128 đến 127 |
| `short` | 16 bit | Có dấu | −32.768 đến 32.767 |
| `char` | 16 bit | Không dấu | Đơn vị mã UTF-16, không phải kiểu số lượng thông thường |
| `int` | 32 bit | Có dấu | −2³¹ đến 2³¹ − 1 |
| `long` | 64 bit | Có dấu | −2⁶³ đến 2⁶³ − 1 |

Các giá trị `byte`, `short`, `int` và `long` được diễn giải theo biểu diễn **bù hai (two's complement)**. Bit cao nhất của `int` hoặc `long` có ý nghĩa dấu khi diễn giải như số nguyên có dấu.

Ta có thể dùng tám hoặc bốn bit để **minh họa trên giấy**, nhưng cần nhớ: phép toán Java trên một biến `int` thực tế làm việc với **32 bit**; biến `long` là **64 bit**. Đó là điểm đặc biệt quan trọng với `~`.

Ví dụ lấy bốn bit thấp:

```text
x = 12 = 1100
y = 10 = 1010
```

`12` ở dạng nhị phân là `1100`, `10` là `1010`. Khi biểu diễn hai giá trị `int`, các bit cao hơn trong ví dụ này là `0`.

## 3. Bảng chân trị: cách bốn toán tử xử lý một bit

Ba toán tử `&`, `|`, `^` so sánh **hai bit tương ứng**:

| Bit A | Bit B | A `&` B | A `|` B | A `^` B |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 0 | 1 | 1 |
| 1 | 0 | 0 | 1 | 1 |
| 1 | 1 | 1 | 1 | 0 |

Với NOT `~`, chỉ có **một toán hạng**:

| Bit A | `~`A |
| ---: | ---: |
| 0 | 1 |
| 1 | 0 |

Có thể ghi nhớ:

- AND chỉ bật bit khi **cả hai** bit đều bật.
- OR bật bit khi **ít nhất một** bit bật.
- XOR bật bit khi **hai** bit khác nhau.
- NOT đảo từng bit, `0` thành `1` và ngược lại.

Không nên áp dụng bảng chân trị trên một vị trí duy nhất rồi quên các bit còn lại. Toán tử bitwise xử lý toàn bộ các bit của toán hạng sau khi Java thực hiện quy tắc chuyển kiểu.

## 4. Toán tử `&`: AND theo từng bit

Xét `12` và `10`:

```text
     1100    (12)
   & 1010    (10)
   ------
     1000     (8)
```

Kết quả là `8` vì chỉ bit tương ứng ở vị trí `2³` cùng bằng `1`.

Ví dụ Java:

```java
int x = 0b1100;
int y = 0b1010;
int both = x & y;      // 0b1000 = 8
```

### 4.1. Ứng dụng phổ biến: kiểm tra một bit

Mỗi bit có thể đại diện cho một khả năng hoặc cờ. Giả sử bit `2` biểu thị quyền thực thi:

```java
int flags = 0b0101;
int execute = 0b0100;

boolean enabled = (flags & execute) != 0; // true
```

`flags & execute` sẽ giữ lại đúng các bit có `1` ở **cả** `flags` và `execute`. Nếu chỉ cần kiểm tra **một cờ được biểu diễn bằng một bit**, điều kiện `!= 0` là đủ.

Với mặt nạ có **nhiều bit**, hai câu hỏi khác nhau:

```java
int state = 0b0101;
int mask = 0b0110;

boolean any = (state & mask) != 0;    // true: ít nhất một bit trong mask bật
boolean all = (state & mask) == mask; // false: chưa đủ tất cả bit trong mask
```

Đặc biệt, khi `mask == 0`, biểu thức `(state & mask) == mask` luôn đúng. Nếu mã nghiệp vụ yêu cầu mask phải chứa ít nhất một bit, cần xác thực `mask != 0` riêng.

### 4.2. Ứng dụng: giữ lại một phần bit

`value & 0xFF` giữ **8 bit thấp** và xóa tất cả bit cao hơn. Nó thường được dùng khi cần diễn giải một `byte` thành số từ `0` đến `255`:

```java
byte signed = (byte) 0xF0; // bit pattern 11110000, byte có dấu = -16
int unsigned = signed & 0xFF; // 240
```

Đây là phép bitwise AND và quy tắc promotion của Java, không phải việc biến `byte` thành một kiểu primitive unsigned mới. Xem phần về số không dấu bên dưới.

## 5. Toán tử `|`: OR theo từng bit

```text
     1100    (12)
   | 1010    (10)
   ------
     1110    (14)
```

Ví dụ:

```java
int x = 0b1100;
int y = 0b1010;
int either = x | y;    // 0b1110 = 14
```

`|` thường dùng để **bật bit** hoặc **kết hợp các cờ độc lập**:

```java
int flags = 0b0001;
int writeFlag = 0b0010;

flags = flags | writeFlag; // 0b0011
// Cách viết gọn:
flags |= writeFlag;        // vẫn là 0b0011
```

Nếu bit đã bật, OR với `1` vẫn giữ bit đó bằng `1`. Vì vậy thao tác `flags |= mask` có tính **idempotent theo giá trị bit**: lặp nhiều lần sẽ không tự tắt cờ. Nhưng phép OR không bảo đảm việc cập nhật biến dùng chung giữa các luồng là nguyên tử.

**Không cộng số học thay cho OR để bật cờ.** Nếu bit đã bật, `flags + mask` có thể gây nhớ sang bit khác; `flags | mask` diễn đạt rõ thao tác bật bit.

## 6. Toán tử `^`: XOR theo từng bit

```text
     1100    (12)
   ^ 1010    (10)
   ------
     0110     (6)
```

Ví dụ:

```java
int x = 0b1100;
int y = 0b1010;
int different = x ^ y; // 0b0110 = 6
```

XOR hữu ích khi cần **đảo trạng thái các bit được chọn**:

```java
int flags = 0b0101;
int mask = 0b0100;

flags ^= mask; // 0b0001: tắt bit 2
flags ^= mask; // 0b0101: bật lại bit 2
```

Các tính chất quan trọng với bit nguyên:

- `x ^ 0 == x`.
- `x ^ x == 0`.
- `(x ^ mask) ^ mask == x`: áp dụng cùng XOR hai lần sẽ phục hồi bit ban đầu.
- `a ^ b == b ^ a` với toán hạng nguyên cùng kiểu.

**XOR không phải phép lũy thừa.** Trong Java, `2 ^ 3` bằng `1` vì `010 ^ 011 = 001`, **không** phải `8`. Muốn tính lũy thừa, cân nhắc `Math.pow` cho số thực hoặc thuật toán nhân nguyên có kiểm tra tràn tùy yêu cầu.

Một ứng dụng khác là phát hiện bit khác nhau giữa hai trạng thái: `changed = oldState ^ newState` tạo mask với bit `1` đúng tại những vị trí có khác biệt.

## 7. Toán tử `~`: NOT trên *toàn bộ* bit của toán hạng

`~` là toán tử **một ngôi**:

```java
int x = 12;
int flipped = ~x; // -13
```

Tại sao `~12` là `-13` mà không phải `3`?

Nếu chỉ **vẽ bốn bit**, phép NOT cho:

```text
x = 1100
~   ----
    0011   (3, nếu chỉ đảo trong một mặt nạ rộng 4 bit)
```

Nhưng `x` là `int` 32 bit. Java đảo cả **32 bit**:

```text
x:  00000000 00000000 00000000 00001100
~x: 11111111 11111111 11111111 11110011
```

Bit cao nhất trở thành `1`, nên khi diễn giải theo bù hai, giá trị là `-13`. Với `int`/`long`, đồng nhất thức đúng theo số học Java là:

```text
~x == -x - 1
```

Ví dụ `~0 == -1`, `~(-1) == 0` và `~12 == -13`.

### 7.1. Muốn đảo trong phạm vi N bit, phải dùng mặt nạ

Giả sử chỉ quan tâm bốn bit thấp:

```java
int x = 0b1100;            // 12
int lowFourInverted = ~x & 0b1111;
System.out.println(lowFourInverted); // 3
```

Mặt nạ `0b1111` xóa các bit cao sau khi NOT, giữ lại `0011`. Tương tự, `~x & 0xFF` giữ tám bit thấp của giá trị sau đảo.

### 7.2. `~` không giống `!`

- `~` làm việc trên **kiểu nguyên** (sau unary numeric promotion), đảo tất cả bit.
- `!` làm việc trên **`boolean`** (hoặc `Boolean` được unbox), đảo giá trị logic.

`~true` không hợp lệ; `!12` cũng không hợp lệ. Cách dùng đúng:

```java
int invertedBits = ~12;       // -13
boolean invertedFlag = !true; // false
```

## 8. Kiểu dữ liệu, binary numeric promotion và kết quả trung gian

Các toán tử `&`, `|`, `^` với **toán hạng nguyên** dùng quy tắc **binary numeric promotion**. Toán tử `~` dùng **unary numeric promotion**.

- `byte`, `short` và `char` được nâng lên `int` trước phép toán.
- `int` với `int` cho kết quả `int`.
- `long` kết hợp với kiểu nguyên nhỏ hơn dẫn đến kết quả `long`.
- `~byteValue`, `~shortValue` hoặc `~charValue` cho kết quả `int`, không tự trở về kiểu nhỏ.
- Không có bitwise `&`/`|`/`^`/`~` trực tiếp trên `float` hay `double`.

Ví dụ:

```java
byte a = 0b0101;
byte b = 0b0011;
int andResult = a & b;     // 1, kiểu int
int notResult = ~a;        // -6, kiểu int

// byte invalid = a & b;  // lỗi: biểu thức là int, không tự thu hẹp thành byte
byte narrowed = (byte) (a & b); // cast tường minh, giá trị 1 ở ví dụ này
```

**Lưu ý với compound assignment:** `a &= b` có thể biên dịch khi `a` là `byte`, vì phép gán ghép có chuyển kiểu ngầm về kiểu biến đích. Nhưng `a = a & b` thường lỗi kiểu do vế phải là `int`. Chuyển hẹp có thể mất các bit cao nên cần chủ động xác định miền dữ liệu.

### 8.1. Sign extension khi nâng một `byte` âm

Xem giá trị có tám bit `1111_0000`:

```java
byte raw = (byte) 0xF0;  // raw == -16
int promoted = raw;      // 0xFFFFFFF0, sign-extended
int unsigned = raw & 0xFF; // 0x000000F0 = 240
int inverse = ~raw;      // 0x0000000F = 15
```

Bởi `raw` là số có dấu, khi chuyển lên `int`, các bit cao được **mở rộng dấu**. Trong `raw & 0xFF`, mask xóa 24 bit cao và giữ nguyên tám bit thấp.

Java cũng có `Byte.toUnsignedInt(raw)` để nhận `240` rõ ý định hơn. Đối với `short`, có `Short.toUnsignedInt`. Không nên viết `Math.abs(raw)` thay cho việc diễn giải 8 bit không dấu; giá trị âm của kiểu signed và unsigned representation là hai vấn đề khác nhau.

### 8.2. `char` không mở rộng dấu

`char` là giá trị 16 bit không dấu. Khi promoted thành `int`, các bit cao là `0`. Ví dụ `char ch = 0xFF00; int n = ch;` cho `n = 65280`, không phải một số âm. Tuy vậy `~ch` vẫn có kiểu `int` và có thể âm vì đảo đủ 32 bit.

Trong xử lý text, `char` đại diện cho **đơn vị mã UTF-16**, không tương đương một Unicode code point trong mọi trường hợp; không dùng toán tử bit chỉ vì muốn thao tác chuỗi ký tự.

## 9. Phân biệt bitwise integer và các phép boolean `&`, `|`, `^`

Java còn định nghĩa `&`, `|` và `^` cho hai toán hạng **boolean`. Khi đó chúng trả `boolean`:

| Toán tử boolean | Quy tắc |
| --- | --- |
| `a & b` | `true` khi cả `a` và `b` đều `true` |
| `a | b` | `true` khi ít nhất một bên `true` |
| `a ^ b` | `true` khi hai bên khác nhau |

Điểm khác biệt quan trọng so với `&&` và `||` là **`&`/`|` trên boolean đánh giá cả hai toán hạng**, còn `&&`/`||` có **short circuit**:

- `false && method()` không gọi `method()`.
- `true || method()` không gọi `method()`.
- `false & method()` vẫn gọi `method()`.
- `true | method()` vẫn gọi `method()`.
- `a ^ b` cũng đánh giá cả hai bên.

Không thể áp dụng `&` giữa một `int` và một `boolean`; biểu thức `flags & true` lỗi biên dịch. Java không tự coi số nguyên `0` là `false` hoặc số nguyên khác `0` là `true`.

### Ví dụ chạy được: so sánh short circuit

Lưu tệp **`BooleanBitwise.java`**:

```java
public class BooleanBitwise {
    static boolean check(String name) {
        System.out.println(name);
        return true;
    }

    public static void main(String[] args) {
        System.out.println(false & check("AND evaluated"));
        System.out.println(true | check("OR evaluated"));
        System.out.println(false && check("AND skipped"));
        System.out.println(true || check("OR skipped"));
        System.out.println(true ^ true);
    }
}
```

Chạy:

```bash
javac --release 17 BooleanBitwise.java
java BooleanBitwise
```

Stdout:

```text
AND evaluated
false
OR evaluated
true
false
true
false
```

Hai nhãn “AND skipped” và “OR skipped” **không xuất hiện**, vì hai phương thức tương ứng không được gọi. Trong biểu thức boolean thông thường, nên ưu tiên `&&`/`||` khi muốn short circuit; dùng `&`/`|` khi thực sự cần cả hai biểu thức được đánh giá và điều đó rõ ràng trong yêu cầu.

## 10. Độ ưu tiên: `~`, `&`, `^`, `|`

Trong các toán tử đang học, thứ tự ưu tiên là:

1. `~` (unary bitwise complement).
2. `&`.
3. `^`.
4. `|`.

Ví dụ:

```java
int a = 0b1100;
int b = 0b1010;
int c = 0b0011;

int first = a | b & c;       // a | (b & c)
int second = (a | b) & c;    // (a | b) & c
```

Tính thủ công:

- `b & c = 0010`; `a | 0010 = 1110` nên `first == 14`.
- `a | b = 1110`; `1110 & 0011 = 0010` nên `second == 2`.

Với XOR:

```java
int ungrouped = a ^ b & c;   // a ^ (b & c) => 1100 ^ 0010 = 1110
int grouped = (a ^ b) & c;   // 0110 & 0011 = 0010
```

Hai biểu thức lần lượt cho `14` và `2`.

**Bẫy thường gặp với phép so sánh:** Trong Java, `==` có độ ưu tiên **cao hơn** bitwise `&`. Vì thế:

```java
// boolean invalid = flags & MASK == MASK;
// Java nhóm như flags & (MASK == MASK): int & boolean -> lỗi biên dịch.

boolean correct = (flags & MASK) == MASK;
```

Đoạn trên chỉ là **minh họa cú pháp**, cần khai báo `flags` và `MASK` nếu đưa vào class chạy. Luôn đặt ngoặc quanh phần bitwise trong điều kiện, chẳng hạn `(flags & mask) != 0`, để vừa tránh lỗi vừa bộc lộ ý định.

Các toán tử shift `<<`, `>>`, `>>>` có độ ưu tiên cao hơn `&`/`^`/`|`. Chúng dùng để định vị bit, nhưng là một nhóm toán tử khác; bài này chỉ dùng shift khi cần tạo mask và tách dữ liệu.

## 11. Một chương trình đầy đủ cho bốn toán tử

Lưu thành **`BitwiseBasics.java`**:

```java
public class BitwiseBasics {
    public static void main(String[] args) {
        int x = 0b1100;
        int y = 0b1010;

        System.out.println(x & y);
        System.out.println(x | y);
        System.out.println(x ^ y);
        System.out.println(~x);
        System.out.println(~x & 0b1111);

        System.out.println(~0);
        System.out.println(~(-1));
    }
}
```

Chạy:

```bash
javac --release 17 BitwiseBasics.java
java BitwiseBasics
```

**Stdout chính xác:**

```text
8
14
6
-13
3
-1
0
```

Giải thích: ba dòng đầu tương ứng bảng bit `1100`/`1010`; `~x` đảo 32 bit của `int` và thành `-13`; `& 0b1111` giữ bốn bit thấp nên nhận `3`. Đảo toàn bộ bit của `0` cho `-1`, và đảo `-1` cho `0`.

**Đừng dùng `Integer.toBinaryString(~x)` rồi mong chỉ có bốn ký tự**, vì kết quả `int` âm được thể hiện đầy đủ bằng chuỗi 32 bit theo two's complement. Muốn xem phần bit thấp, dùng mask trước khi chuyển sang chuỗi.

## 12. Dùng bitmask để bật, tắt, kiểm tra và đảo cờ

Một cờ một bit có thể tạo bằng `1 << vị_trí_bit`. Từ đây có bốn công thức quan trọng:

| Mục đích | Công thức | Ý nghĩa |
| --- | --- | --- |
| Kiểm tra **một** cờ | `(flags & FLAG) != 0` | Bit đại diện cờ đang bật |
| Bật cờ | `flags |= FLAG` | Đặt bit thành 1 |
| Tắt cờ | `flags &= ~FLAG` | Xóa bit về 0 |
| Đảo cờ | `flags ^= FLAG` | Đổi 0↔1 |
| Kiểm tra đủ **nhiều** cờ | `(flags & MASK) == MASK` | Tất cả bit trong mask đều bật |

### Ví dụ chạy được: trạng thái quyền bằng bit

Lưu thành **`FlagDemo.java`**:

```java
public class FlagDemo {
    private static final int READ = 1 << 0;    // 001
    private static final int WRITE = 1 << 1;   // 010
    private static final int EXECUTE = 1 << 2; // 100

    public static void main(String[] args) {
        int permissions = READ | EXECUTE; // 101
        System.out.println(permissions);
        System.out.println((permissions & WRITE) != 0);

        permissions |= WRITE;   // 111
        System.out.println(permissions);

        permissions ^= EXECUTE; // 011
        System.out.println(permissions);

        permissions &= ~READ;   // 010
        System.out.println(permissions);
    }
}
```

Chạy:

```bash
javac --release 17 FlagDemo.java
java FlagDemo
```

**Stdout:**

```text
5
false
7
3
2
```

Trình tự:

- `READ | EXECUTE` bật bit `0` và bit `2`, giá trị là `101₂ = 5`.
- Chưa có `WRITE` nên kiểm tra trả `false`.
- `|= WRITE` bật thêm bit `1` → `111₂ = 7`.
- `^= EXECUTE` đảo bit `2` từ `1` về `0` → `011₂ = 3`.
- `&= ~READ` xóa bit `0` → `010₂ = 2`.

**Chọn đúng thao tác:** muốn **bảo đảm bật** thì dùng `|`; muốn **bảo đảm tắt** thì dùng `& ~`; chỉ dùng `^` khi thật sự muốn **đảo** trạng thái. Việc dùng mask tự nó không thay thế quy tắc phân quyền của ứng dụng hay kiểm tra quyền theo người dùng/tài nguyên.

### 12.1. Khi bit vượt phạm vi 31

`int` có 32 bit; `1 << 31` vẫn hợp lệ nhưng cho giá trị `Integer.MIN_VALUE` âm vì bật bit dấu. Nếu cần cờ ở vị trí `40`, phải dùng `long`:

```java
long flag40 = 1L << 40;
```

Viết `1 << 40` **không** tạo bit 40 của `int`: Java chỉ dùng 5 bit thấp của shift distance với `int`, nên hiệu ứng tương đương dịch `1 << 8`. Với `long`, số bước dịch chỉ xét 6 bit thấp. Luôn chọn độ rộng trước khi tạo mask và kiểm tra phạm vi chỉ số bit.

## 13. `&` với số không dấu: cùng bit, cách diễn giải khác

Java không có kiểu nguyên thủy `unsigned int` hoặc `unsigned long`. `int` và `long` vẫn dùng các bit tương ứng cho phép AND/OR/XOR/NOT dù chúng được diễn giải như số âm. Sự khác biệt giữa có dấu và không dấu nằm ở **cách diễn giải giá trị và một số phép toán khác** (so sánh, chia, dịch phải), không phải bảng chân trị của bốn toán tử bitwise.

### 13.1. Đọc một `byte` thành 0..255

Lưu thành **`UnsignedBits.java`**:

```java
public class UnsignedBits {
    public static void main(String[] args) {
        byte raw = (byte) 0xF0;

        System.out.println(raw);
        System.out.println(raw & 0xFF);
        System.out.println(Byte.toUnsignedInt(raw));
        System.out.println(~raw);
        System.out.println((byte) ~raw);
        System.out.println(Integer.toUnsignedString(-1));
    }
}
```

Chạy:

```bash
javac --release 17 UnsignedBits.java
java UnsignedBits
```

**Stdout:**

```text
-16
240
240
15
15
4294967295
```

Giải thích:

1. `0xF0` có 8 bit thấp `11110000`; khi ép về `byte` có dấu, đó là `-16`.
2. `raw & 0xFF` xóa bit cao đã được mở rộng dấu → `240`.
3. `Byte.toUnsignedInt(raw)` trả cùng giá trị `240` với ý nghĩa unsigned tường minh.
4. `~raw` được tính ở kiểu `int` sau unary promotion: `~(-16) = 15`.
5. Cast `(byte) ~raw` trong ví dụ vẫn là `15` vì vừa trong miền `byte`; với dữ liệu khác, cast hẹp có thể cắt bit.
6. `Integer.toUnsignedString(-1)` diễn giải 32 bit toàn `1` thành `4294967295`. Biểu diễn bit không đổi; chỉ thay cách đọc giá trị.

Để so sánh/chia số nguyên theo hướng unsigned, Java còn có `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.remainderUnsigned` cùng các API `Long` tương ứng. `char` là trường hợp primitive không dấu 16 bit, nhưng chủ yếu phục vụ UTF-16.

### 13.2. Cách tách nhiều trường từ một số

Một tình huống thực tế là tách ba kênh màu RGB được đóng gói vào 24 bit:

```java
int rgb = 0x12AB34;
int red   = (rgb >>> 16) & 0xFF;
int green = (rgb >>> 8)  & 0xFF;
int blue  = rgb & 0xFF;
```

Trong đó `>>>` là **dịch phải điền 0**, đưa nhóm bit cần đọc xuống vị trí thấp; `& 0xFF` chỉ giữ tám bit tương ứng. Ba giá trị nhận được: `red = 18`, `green = 171`, `blue = 52`. Dùng `&` để mask là điều cốt lõi; cần học riêng `>>`, `>>>`, `<<` để hiểu toàn bộ thuật toán đóng gói bit.

## 14. Các tính chất đại số hữu ích và giới hạn áp dụng

Với các toán hạng nguyên cùng kiểu và phép bitwise thuần, những luật sau đúng trên toàn bộ bit của kiểu:

| Tính chất | Biểu thức |
| --- | --- |
| AND với 0 | `x & 0 == 0` |
| AND với toàn bit 1 | `x & -1 == x` |
| OR với 0 | `x | 0 == x` |
| OR với toàn bit 1 | `x | -1 == -1` |
| XOR với 0 | `x ^ 0 == x` |
| XOR với chính nó | `x ^ x == 0` |
| Đảo hai lần | `~~x == x` (khi `x` đã là `int`/`long`) |
| De Morgan | `~(x & y) == (~x | ~y)` |
| De Morgan | `~(x | y) == (~x & ~y)` |

Các luật này rất hữu ích khi đơn giản hóa mặt nạ. Tuy nhiên cần giữ **cùng độ rộng**, xét promotion, và không tự ý biến phép toán có lời gọi hàm/side effect thành biểu thức khác.

### 14.1. XOR không bảo đảm hoán đổi biến an toàn

Mẹo `a ^= b; b ^= a; a ^= b;` thường được dùng để swap hai số. Nó khó đọc, có thể sai khi hai tham chiếu/vị trí thực chất trỏ vào cùng phần tử, và không mang lợi ích mặc định trong Java hiện đại. Hãy dùng biến tạm tường minh để swap giá trị. Mục tiêu học XOR là hiểu bit, không phải thay thế mọi thao tác dữ liệu bằng “mẹo”.

### 14.2. Thao tác bit không đồng nghĩa phép cập nhật nguyên tử

`flags |= mask` là phép đọc, OR và ghi lại theo ngữ nghĩa bình thường. Nếu nhiều luồng cùng thay đổi một biến, có thể mất cập nhật nếu không đồng bộ. Với yêu cầu đồng thời, dùng cơ chế đồng bộ hoặc các phương thức cập nhật nguyên tử phù hợp; phạm vi của toán tử `|` không tự cung cấp thread safety.

## 15. Lỗi phổ biến và cách phát hiện

1. **Nhầm `^` với mũ:** `2 ^ 3` = `1`, không phải 8.
2. **Nghĩ `~12` là 3:** đó chỉ là kết quả NOT ở **bốn bit thấp**; `~12` với `int` 32 bit bằng `-13`. Muốn 3 dùng `(~12) & 0xF`.
3. **Quên promotion của `byte`:** `~byteValue` cho `int`, không cho `byte`; `byteA & byteB` cũng cho `int`.
4. **Không mask sau sign extension:** `byte raw = (byte) 0xF0` là `-16`; `raw & 0xFF` hoặc `Byte.toUnsignedInt(raw)` trả 240.
5. **Dùng `^` để “bật cờ”:** XOR sẽ tắt một cờ đang bật. Dùng `|` khi yêu cầu chắc chắn bật.
6. **Dùng `|` để “tắt cờ”:** muốn tắt một bit phải dùng `flags &= ~FLAG`.
7. **Sai mức ưu tiên:** `flags & MASK == MASK` không có nhóm mong muốn; đặt `(flags & MASK) == MASK`.
8. **Nhầm `&` với `&&`:** với `boolean`, `&` luôn đánh giá cả hai bên, nên lời gọi hàm thứ hai vẫn chạy.
9. **Quên rằng `~` là NOT cho toàn độ rộng:** mask hẹp chỉ được áp dụng khi ghi rõ `& mask` sau đó.
10. **Tạo mask dùng `int` cho bit cao:** `1 << 40` không phải cờ vị trí 40; dùng `1L << 40`.
11. **Nhầm unsigned bit pattern với giá trị signed:** cùng `0xFFFFFFFF` là bit toàn 1; đọc kiểu `int` là `-1`, đọc unsigned 32 bit là `4294967295`.
12. **Trộn số thực/boolean với integer bitwise:** `1.5 & 2`, `~1.0` hoặc `3 & true` không có kiểu toán hạng hợp lệ trong Java.

## 16. Bài luyện tập kèm giải thích

### Bài 1 — Tính tay bảng bit

Với `a = 0b1100` và `b = 0b1010`, hãy tính `a & b`, `a | b` và `a ^ b`.

**Đáp án:** `1000₂ = 8`, `1110₂ = 14`, `0110₂ = 6`. AND giữ bit cùng 1, OR giữ bit có ít nhất một 1, XOR chỉ giữ bit khác nhau.

### Bài 2 — Vì sao NOT ra số âm?

Tính `~0`, `~12` và `~(-1)` với toán hạng `int`.

**Đáp án:** `-1`, `-13` và `0`. `~` đảo đủ 32 bit; công thức `~x = -x - 1` có thể giúp kiểm tra.

### Bài 3 — Bật, tắt, đảo

Ban đầu `flags = 0b0101`; cần (a) bật bit `1`, (b) tắt bit `2`, (c) đảo bit `0`.

**Đáp án:** (a) `flags |= 0b0010` → `0111`; (b) `flags &= ~0b0100` → `0011`; (c) `flags ^= 0b0001` → `0010`. Ba bước thực hiện **liên tiếp**.

### Bài 4 — Một bit và nhiều bit

`flags = 0b0101`, `mask = 0b0110`. Kết quả `(flags & mask) != 0` và `(flags & mask) == mask` là gì?

**Đáp án:** `true` và `false`. Mask yêu cầu bit 1 và 2, nhưng flags chỉ chứa bit 2 trong hai bit đó.

### Bài 5 — Promotion và unsigned byte

`byte raw = (byte) 0xF0;`. Hãy tính `raw`, `raw & 0xFF` và `~raw`.

**Đáp án:** `-16`, `240`, `15`. `raw` sign-extends lên `int` trong hai phép bitwise, còn mask `0xFF` giữ tám bit thấp.

### Bài 6 — Chọn toán tử theo ý định

Tại sao `flags ^= FLAG` không phải lựa chọn mặc định để đảm bảo một cờ bật?

**Đáp án:** XOR **đảo** bit. Nếu cờ đã bật, XOR tắt nó. OR với `FLAG` bảo đảm bit bật, tức `flags |= FLAG`.

### Bài 7 — Boolean có side effect

Giả sử `probe()` in thông báo rồi trả `true`. So sánh `false & probe()` với `false && probe()`.

**Đáp án:** biểu thức thứ nhất vẫn gọi `probe()` và trả `false`; biểu thức thứ hai bỏ qua `probe()` do short circuit và cũng trả `false`.

### Bài 8 — Mask ở bit 40

Tại sao `1 << 40` sai nếu mục tiêu là tạo một cờ tại vị trí bit 40? Viết lại đúng.

**Đáp án:** `1` là `int` 32 bit; khoảng dịch hiệu dụng chỉ xét năm bit thấp nên `40` được xử lý như `8`. Viết `1L << 40` để dùng `long` và dịch đúng vị trí.

### Bài 9 — Tách màu RGB

Cho `rgb = 0x12AB34`. Dùng `& 0xFF` và dịch phải để lấy red, green, blue.

**Đáp án:**

```java
int red   = (rgb >>> 16) & 0xFF; // 18
int green = (rgb >>> 8)  & 0xFF; // 171
int blue  = rgb & 0xFF;          // 52
```

Đoạn này là **mảnh mã**; đặt trong phương thức với `int rgb = 0x12AB34;` trước khi chạy.

## 17. Checklist thành thạo

- [ ] Tôi tự dựng được bảng chân trị của AND, OR, XOR và NOT.
- [ ] Tôi lý giải được `12 & 10 = 8`, `12 | 10 = 14`, `12 ^ 10 = 6`.
- [ ] Tôi không nhầm `~12` với việc đảo chỉ bốn bit.
- [ ] Tôi biết `&`/`|`/`^` và `~` áp dụng lên kiểu nguyên sau promotion; `~byte` cho `int`.
- [ ] Tôi phân biệt `&`/`|` trên `boolean` với `&&`/`||` và cơ chế short circuit.
- [ ] Tôi chọn được mask để bật, tắt, kiểm tra hoặc đảo cờ.
- [ ] Tôi biết phải đặt ngoặc với biểu thức kiểm tra `(flags & mask) != 0` và `(flags & mask) == mask`.
- [ ] Tôi hiểu ý nghĩa dấu khi đọc `byte`/`int` và cách mask ra phần thấp không dấu.
- [ ] Tôi biết cờ ở bit cao cần `long` và literal `1L` trước phép dịch.
- [ ] Tôi đã chạy ví dụ Java 17+ và kiểm tra các trường hợp số âm, bit cao và mask nhiều bit.

**Tài liệu tham khảo chính thức:**

- [JLS 17 §15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.22): quy tắc `&`, `^`, `|` với integer/boolean.
- [JLS 17 §15.15.5 — Bitwise Complement Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.15.5): quy tắc toán tử `~`.
- [JLS 17 §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): unary/binary numeric promotion.
- [JLS 17 §15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): dịch bit và số bước dịch hiệu dụng.
- [Java SE 17 Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `toBinaryString`, `toUnsignedString` và các phương thức unsigned.
- [Java SE 17 Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `toUnsignedInt`.

Hãy luôn đọc biểu thức bitwise theo **bit width, kiểu sau promotion, mask và mục đích thao tác**. Bốn toán tử đơn giản về bảng chân trị, nhưng hiệu quả và độ đúng phụ thuộc vào cách bạn diễn giải các bit thành giá trị trong Java.
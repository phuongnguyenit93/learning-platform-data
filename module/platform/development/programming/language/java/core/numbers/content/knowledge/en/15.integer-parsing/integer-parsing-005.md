# decode và các tiền tố cơ số trong Java

## 1. Khi chuỗi số có tiền tố, Java đọc theo cơ số nào?

Java cho phép viết số nguyên theo hệ thập phân, nhị phân, bát phân và thập lục phân. Nhưng có sự khác biệt quan trọng giữa **literal viết trong mã Java** và **chuỗi ký tự được phân tích khi chương trình đang chạy**.

Ví dụ, trong mã nguồn:

```java
int decimal = 42;
int binary = 0b101010;
int octal = 052;
int hex = 0x2A;
// Cả bốn biến đều có giá trị int 42.
```

Để đọc một chuỗi như `"0x2A"` hoặc `"052"` tại runtime, Java có phương thức `Integer.decode(String)`. Nó nhận diện **một số tiền tố cơ số** và chuyển thành số nguyên có dấu.

```java
int a = Integer.decode("42");   // 42, thập phân
int b = Integer.decode("052");  // 42, bát phân: 5*8+2
int c = Integer.decode("0x2A"); // 42, thập lục phân
int d = Integer.decode("#2A");  // 42, cú pháp hex khác
```

**Cảnh báo đầu tiên:** `Integer.decode("010")` cho **8**, không phải 10, vì chuỗi bắt đầu bằng `0` nên được hiểu là bát phân. Trong khi đó, `Integer.parseInt("010")` cho **10** vì `parseInt(String)` mặc định là thập phân.

**Cảnh báo thứ hai:** mặc dù literal `0b101010` hợp lệ trong mã Java, `Integer.decode("0b101010")` **không hỗ trợ** tiền tố nhị phân `0b`. Muốn đọc chuỗi nhị phân, cần dùng `Integer.parseInt("101010", 2)` hoặc một hàm riêng có xử lý tiền tố.

Bài học tập trung vào **cơ chế `decode`, tiền tố hợp lệ, sự khác biệt với `parseInt`, giới hạn kiểu số và cách xử lý đầu vào an toàn**.

## 2. Những phương thức `decode` sẵn có

Các wrapper số nguyên có phương thức tĩnh `decode(String)`:

| Phương thức | Trả về | Miền giá trị có dấu |
|---|---|---|
| `Byte.decode(text)` | `Byte` | -128 đến 127 |
| `Short.decode(text)` | `Short` | -32_768 đến 32_767 |
| `Integer.decode(text)` | `Integer` | -2_147_483_648 đến 2_147_483_647 |
| `Long.decode(text)` | `Long` | -9_223_372_036_854_775_808 đến 9_223_372_036_854_775_807 |

Đây là **các phương thức `static`**: gọi bằng tên lớp như `Integer.decode("0xFF")`, không cần tạo một đối tượng `Integer` trước.

Giá trị trả về là **wrapper**, không phải primitive; tuy nhiên Java có thể tự **unbox** khi bạn gán kết quả vào biến primitive:

```java
Integer wrapper = Integer.decode("0x2A"); // Integer, giá trị 42
int primitive = Integer.decode("0x2A");   // unboxing -> int 42
long large = Long.decode("0x100000000"); // 4294967296L
```

`decode` **không hỗ trợ `Float` hoặc `Double`** theo cùng ý nghĩa phân tích chuỗi nguyên với tiền tố cơ số. Nếu cần đọc số thực, dùng API số thực phù hợp như `Double.parseDouble`; nếu cần phân tích một chuỗi giá trị số nguyên có tiền tố rồi chuyển thành `double`, hai bước ấy có ngữ nghĩa khác nhau và phải được quyết định rõ.

## 3. Bảng tiền tố được `decode` hỗ trợ

`Integer.decode` và `Long.decode` tuân theo các hình thức thông dụng:

| Dạng chuỗi | Cơ số | Ví dụ | Kết quả thập phân |
|---|---:|---|---:|
| Không có tiền tố (và không bắt đầu bằng số 0 theo quy tắc bát phân) | 10 | `"42"` | 42 |
| `0x` | 16 | `"0x2A"` | 42 |
| `0X` | 16 | `"0X2a"` | 42 |
| `#` | 16 | `"#2A"` | 42 |
| Bắt đầu bằng `0`, sau đó là chữ số | 8 | `"052"` | 42 |
| Tiền tố nhị phân `0b`, `0B` | Không được hỗ trợ | `"0b101010"` | `NumberFormatException` |

Tại sao `"052"` là 42?

\[
5\times 8^1 + 2\times 8^0 = 40+2=42
\]

Tại sao `"0x2A"` là 42?

\[
2\times 16^1 + 10\times 16^0 = 32+10=42
\]

Chữ cái `A` đến `F` (hoặc chữ thường `a` đến `f`) biểu thị các chữ số hex 10 đến 15. Ký tự `#` trong `"#2A"` cũng là **tiền tố hex**, không phải một toán tử số học mới.

**Số 0 đứng đầu có ý nghĩa cú pháp.** Ví dụ:

- `Integer.decode("0")` → 0.
- `Integer.decode("00")` → 0.
- `Integer.decode("010")` → 8.
- `Integer.decode("077")` → 63.
- `Integer.decode("08")` → lỗi, vì chữ số 8 không hợp lệ trong hệ bát phân.
- `Integer.decode("09")` → lỗi tương tự.

Vì thế, nếu một đầu vào thực sự là **số thập phân** và có thể có số 0 đứng đầu (ví dụ `"008"`), đừng dùng `decode` một cách mặc định.

## 4. Dấu cộng, dấu trừ và vị trí hợp lệ của chúng

`decode` hỗ trợ **dấu `+` hoặc `-` đứng trước tiền tố**, nếu có:

```java
int a = Integer.decode("-42");      // -42
int b = Integer.decode("+42");      // 42
int c = Integer.decode("-052");     // -42 (bát phân)
int d = Integer.decode("-0x2A");    // -42
int e = Integer.decode("+#2A");     // 42
int f = Integer.decode("-0X2a");    // -42
```

Quy tắc cốt lõi: **dấu đứng đầu toàn bộ chuỗi**, rồi mới tới phần `0x`, `0X`, `#` hoặc `0`.

Các chuỗi sau không hợp lệ:

```java
// Integer.decode("0x-2A"); // sai: dấu ở sau tiền tố
// Integer.decode("#-2A");  // sai
// Integer.decode("--42");  // sai
// Integer.decode("++42");  // sai
```

Dấu chỉ được xuất hiện một lần và phải đứng ở vị trí đầu. Việc tách dấu và tiền tố theo đúng thứ tự giúp các chuỗi âm dạng hex/bát phân có nghĩa nhất quán với các giá trị âm ở hệ thập phân.

### Giá trị âm thấp nhất của `int` vẫn đọc được

`Integer.MIN_VALUE` bằng -2_147_483_648. Trong hex, độ lớn tương ứng là `0x80000000`. Chuỗi có dấu âm:

```java
int min = Integer.decode("-0x80000000");
// -2147483648
```

là hợp lệ. Nhưng:

```java
// Integer.decode("0x80000000"); // NumberFormatException
```

không hợp lệ vì nó biểu thị **giá trị dương** 2_147_483_648, vượt `Integer.MAX_VALUE`. `decode` đọc **số nguyên có dấu**, không tự coi mọi mẫu 32 bit là một giá trị unsigned.

## 5. So sánh `decode`, `parseInt` và `parseUnsignedInt`

Đây là phần quan trọng nhất khi chọn API.

| Mục đích | API phù hợp | Cách hiểu đầu vào |
|---|---|---|
| Đọc chuỗi có tiền tố `0x`, `0X`, `#` hoặc `0` bát phân | `Integer.decode(text)` | Tự quyết định 10/8/16 từ tiền tố |
| Đọc số thập phân, kể cả số 0 đầu | `Integer.parseInt(text)` | Cố định cơ số 10 |
| Đọc một chuỗi chữ số theo cơ số chỉ định | `Integer.parseInt(digits, radix)` | Cơ số do tham số `radix` quyết định |
| Đọc mẫu bit `int` như số không dấu | `Integer.parseUnsignedInt(digits, radix)` | Cơ số chỉ định và miền 0..2³²−1 |
| Đọc số nguyên signed 64 bit theo tiền tố | `Long.decode(text)` | 10/8/16 có dấu |
| Đọc số nguyên không dấu 64 bit | `Long.parseUnsignedLong(digits, radix)` | Miền 0..2⁶⁴−1, lưu trong mẫu bit `long` |

Ví dụ cùng một chuỗi:

```java
int a = Integer.decode("010"); // 8, bát phân
int b = Integer.parseInt("010"); // 10, thập phân
int c = Integer.parseInt("010", 8); // 8, cơ số chỉ định
int d = Integer.parseInt("1010", 2); // 10, nhị phân
```

Ví dụ chuỗi hex:

```java
int a = Integer.decode("0xFF"); // 255
int b = Integer.parseInt("FF", 16); // 255
// Integer.parseInt("0xFF", 16); // lỗi: parseInt không tự bỏ "0x"
```

**Nguyên tắc chọn API:** Nếu giao thức quy định input là **decimal**, dùng `parseInt` hoặc `parseLong`. Nếu giao thức quy định input **có tiền tố đa cơ số theo quy tắc `decode`**, dùng `decode`. Nếu cơ số được quy định bên ngoài, dùng overload `parseInt(text, radix)` thay vì suy luận từ số 0 đứng đầu.

## 6. Ví dụ Java 17+ đầu tiên: giải mã tất cả dạng cơ số

Tạo tệp `DecodePrefixesDemo.java`:

```java
public class DecodePrefixesDemo {
    public static void main(String[] args) {
        System.out.println("42 -> " + Integer.decode("42"));
        System.out.println("052 -> " + Integer.decode("052"));
        System.out.println("0x2A -> " + Integer.decode("0x2A"));
        System.out.println("0X2a -> " + Integer.decode("0X2a"));
        System.out.println("#2A -> " + Integer.decode("#2A"));
        System.out.println("-052 -> " + Integer.decode("-052"));
        System.out.println("-0x2A -> " + Integer.decode("-0x2A"));
        System.out.println("+0X2a -> " + Integer.decode("+0X2a"));
        System.out.println("010 via decode -> "
                + Integer.decode("010"));
        System.out.println("010 via parseInt -> "
                + Integer.parseInt("010"));
        System.out.println("binary via radix -> "
                + Integer.parseInt("101010", 2));
        System.out.println("long hex -> "
                + Long.decode("0x100000000"));
        System.out.println("short hex -> "
                + Short.decode("0x7FFF"));
        System.out.println("byte octal -> "
                + Byte.decode("0177"));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac DecodePrefixesDemo.java
java DecodePrefixesDemo
```

Kết quả chính xác:

```text
42 -> 42
052 -> 42
0x2A -> 42
0X2a -> 42
#2A -> 42
-052 -> -42
-0x2A -> -42
+0X2a -> 42
010 via decode -> 8
010 via parseInt -> 10
binary via radix -> 42
long hex -> 4294967296
short hex -> 32767
byte octal -> 127
```

Ở ba dòng cuối, kết quả vẫn phải nằm trong miền kiểu trả về. Ví dụ `Byte.decode("0177")` đọc bát phân 177 và nhận 127 trong miền `byte` có dấu; `Byte.decode("0200")` sẽ không thành -128 bằng wraparound mà báo lỗi vì giá trị dương 128 **ngoài miền `byte`**.

## 7. `decode` không hiểu mọi cú pháp literal Java

Các literal trong **mã nguồn Java** do compiler xử lý. Chuỗi dữ liệu đưa vào `decode` được kiểm tra bằng ngữ pháp riêng của phương thức; nó không phải trình biên dịch Java thu nhỏ.

Bảng đối chiếu:

| Trong mã nguồn Java | Có hợp lệ? | Chuỗi tương ứng đưa cho `Integer.decode` |
|---|---|---|
| `0b1010` | Có: nhị phân | `"0b1010"` → lỗi |
| `0xFF` | Có: hex | `"0xFF"` → 255 |
| `077` | Có: bát phân | `"077"` → 63 |
| `1_000` | Có: dấu gạch dưới phân nhóm chữ số | `"1_000"` → lỗi |
| `123L` | Có: literal `long` | `"123L"` → lỗi |
| `0xFFL` | Có: literal `long` hex | `"0xFFL"` → lỗi |
| `10` | Có: thập phân | `"10"` → 10 |

Dấu gạch dưới `_` **được compiler cho phép trong literal theo quy tắc nhất định**, nhưng không được chấp nhận trong chuỗi phân tích bằng `Integer.decode`, `Integer.parseInt` hoặc `Long.parseLong`.

Tương tự, hậu tố `L`/`l` là cú pháp literal Java, **không phải chữ số hợp lệ** trong chuỗi cho `Long.decode`. Nên viết `Long.decode("123")` thay vì `Long.decode("123L")`.

### Cú pháp nhị phân phải xử lý riêng

Nếu đầu vào được quy định là một dãy chữ số nhị phân:

```java
int value = Integer.parseInt("101010", 2); // 42
```

Nếu đầu vào được quy định là `"0b101010"`, bạn cần kiểm tra và bỏ tiền tố trước khi parse:

```java
String text = "0b101010";
if (text.startsWith("0b") || text.startsWith("0B")) {
    int value = Integer.parseInt(text.substring(2), 2); // 42
}
```

Đây là **đoạn mã minh họa**, không phải chương trình đầy đủ. Nó chỉ chấp nhận tiền tố nhị phân ở đầu chuỗi dương; với dữ liệu có dấu như `"-0b1010"`, phải xác định quy ước dấu và thiết kế bộ phân tích tương ứng.

Đừng coi `decode` tự hỗ trợ nhị phân chỉ vì các literal Java có `0b`.

## 8. Giới hạn miền: `decode` kiểm tra số signed, không wraparound

Các phương thức `Byte.decode`, `Short.decode`, `Integer.decode` và `Long.decode` trả wrapper số nguyên **có dấu**. Giá trị ngoài miền gây `NumberFormatException`.

```java
int max = Integer.decode("2147483647");
int min = Integer.decode("-2147483648");

// Integer.decode("2147483648");  // quá lớn
// Integer.decode("-2147483649"); // quá nhỏ
// Integer.decode("0xFFFFFFFF"); // dương 4294967295, ngoài miền int
```

Với `Long`:

```java
long max = Long.decode("9223372036854775807");
long min = Long.decode("-9223372036854775808");

// Long.decode("9223372036854775808");  // ngoài miền long
```

Với `Byte` và `Short`:

```java
byte maxByte = Byte.decode("127");
byte minByte = Byte.decode("-0x80");
short maxShort = Short.decode("0x7FFF");

// Byte.decode("128");       // ngoài miền byte
// Short.decode("0x8000");   // dương 32768, ngoài miền short
```

Nếu mục tiêu là chuyển một **bit pattern** 32 bit thành `int` có thể âm, đừng dùng `Integer.decode("0xFFFFFFFF")`. Nó không nhận 4_294_967_295 như số signed hợp lệ. Thay vào đó, dùng parse không dấu theo đúng cơ số (và bỏ tiền tố `0x` trước khi parse), rồi làm việc với các bit ở kết quả.

## 9. Đọc số nguyên không dấu và giữ mẫu bit

Java `int` và `long` là các kiểu primitive có dấu, nhưng thư viện có API **đọc và hiển thị giá trị không dấu** bằng chính các mẫu bit 32/64 bit:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(bits); // -1 khi in kiểu int có dấu
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
```

Bit pattern `0xFFFFFFFF` có thể được biểu diễn bằng `int` -1, nhưng khi diễn giải như số không dấu, nó bằng 4_294_967_295. **Giá trị trả về vẫn có kiểu `int`**, không tạo kiểu `unsigned int`.

Tương tự:

```java
long bits = Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);
System.out.println(bits); // -1 khi in kiểu long có dấu
System.out.println(Long.toUnsignedString(bits)); // 18446744073709551615
```

### Chương trình hoàn chỉnh: đọc mẫu hex không dấu

Tạo tệp `UnsignedDecodeDemo.java`:

```java
public class UnsignedDecodeDemo {
    public static void main(String[] args) {
        int signedMin = Integer.decode("-0x80000000");
        System.out.println("signed min: " + signedMin);

        int unsignedBits =
                Integer.parseUnsignedInt("80000000", 16);
        System.out.println("signed view: " + unsignedBits);
        System.out.println("unsigned view: "
                + Integer.toUnsignedString(unsignedBits));
        System.out.println("as unsigned long: "
                + Integer.toUnsignedLong(unsignedBits));

        int allOnes =
                Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("all bits signed: " + allOnes);
        System.out.println("all bits unsigned: "
                + Integer.toUnsignedString(allOnes));

        long longBits =
                Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);
        System.out.println("long signed: " + longBits);
        System.out.println("long unsigned: "
                + Long.toUnsignedString(longBits));
    }
}
```

Chạy:

```bash
javac UnsignedDecodeDemo.java
java UnsignedDecodeDemo
```

Kết quả:

```text
signed min: -2147483648
signed view: -2147483648
unsigned view: 2147483648
as unsigned long: 2147483648
all bits signed: -1
all bits unsigned: 4294967295
long signed: -1
long unsigned: 18446744073709551615
```

**Bẫy quan trọng:** `Integer.parseUnsignedInt("0xFFFFFFFF", 16)` vẫn không hợp lệ, vì `parseUnsignedInt` nhận các **chữ số theo cơ số** đã được chỉ định chứ không tự bóc tiền tố. Hãy xác minh định dạng input, bỏ `0x` khi cần, rồi parse.

## 10. `NumberFormatException` và dữ liệu không hợp lệ

`decode` có thể ném `NumberFormatException` khi gặp đầu vào sai cú pháp hoặc ngoài miền. Những ví dụ dưới đây không hợp lệ với `Integer.decode`:

| Chuỗi | Lý do |
|---|---|
| `"08"` | Bắt đầu bằng 0 nên đọc bát phân; chữ số 8 không hợp lệ |
| `"09"` | Lỗi bát phân tương tự |
| `"0b1010"` | Không hỗ trợ tiền tố `0b` |
| `"0x"` | Thiếu chữ số hex |
| `"#"` | Thiếu chữ số hex |
| `"0x-10"` | Dấu âm sai vị trí |
| `"1_000"` | Dấu `_` không hợp lệ trong chuỗi parse |
| `"42L"` | Hậu tố literal `L` không được hỗ trợ |
| `" 42"` | Có khoảng trắng ở đầu; `decode` không tự trim |
| `"42 "` | Có khoảng trắng ở cuối |
| `""` | Không có chữ số |
| `"2147483648"` | Ngoài miền `int` có dấu |

Khi nhận input không đáng tin, nên **bắt ngoại lệ tại ranh giới nhập liệu**, thay vì để lỗi propagate không kiểm soát hoặc tự ép một giá trị giả định.

### Ví dụ Java 17+: phân loại các chuỗi hợp lệ và không hợp lệ

Tạo tệp `DecodeValidationDemo.java`:

```java
public class DecodeValidationDemo {
    private static void check(String text) {
        try {
            int value = Integer.decode(text);
            System.out.println(text + " -> " + value);
        } catch (NumberFormatException e) {
            System.out.println(text + " -> invalid");
        }
    }

    public static void main(String[] args) {
        check("0x10");
        check("010");
        check("08");
        check("0b1010");
        check("0x");
        check("42L");
        check("1_000");
        check(" 42");
        check("-0x80000000");
        check("0x80000000");
    }
}
```

Biên dịch và chạy:

```bash
javac DecodeValidationDemo.java
java DecodeValidationDemo
```

Kết quả:

```text
0x10 -> 16
010 -> 8
08 -> invalid
0b1010 -> invalid
0x -> invalid
42L -> invalid
1_000 -> invalid
 42 -> invalid
-0x80000000 -> -2147483648
0x80000000 -> invalid
```

Lưu ý dòng `" 42"` chứa một **dấu cách ngay đầu chuỗi**. Vì phương thức `check` in nguyên chuỗi đó trước dấu `->`, trong output có **một dấu cách đầu dòng**. Đây là hành vi in chuỗi thực tế; nó không được tự cắt bỏ khi kiểm tra output.

## 11. Dùng `decode` an toàn theo hợp đồng đầu vào

Để tránh nhầm lẫn và hành vi khó đoán, trước khi chọn `decode` hãy xác định:

1. **Có được phép tiền tố cơ số hay không?** Nếu có, những tiền tố nào là hợp lệ?
2. **Số 0 đứng đầu là mã định danh hay giá trị số?** Ví dụ `"008"` có thể là một mã có ý nghĩa văn bản; parse thành số sẽ mất các số 0 đầu.
3. **Giá trị có dấu hay không dấu?** `decode` chỉ dành cho kiểu số signed; nếu đọc bit pattern nguyên vẹn, cần API unsigned phù hợp.
4. **Kiểu đích có đủ miền?** `Byte/Short/Integer/Long.decode` kiểm tra miền khác nhau.
5. **Có cần chấp nhận khoảng trắng hoặc format từ người dùng?** `decode` không tự trim; nếu chính sách cho phép, hãy chuẩn hóa có kiểm tra trước.
6. **Có cho phép tiền tố nhị phân?** `decode` không chấp nhận `0b`; nếu cần, viết parser riêng.
7. **Cần báo lỗi ra sao?** Bắt `NumberFormatException` tại lớp nhập liệu và trả thông báo rõ, không coi dữ liệu sai là 0 theo mặc định.

Ví dụ với đầu vào **có chủ đích cho phép khoảng trắng đầu/cuối**:

```java
static int decodeTrimmed(String input) {
    if (input == null) {
        throw new IllegalArgumentException("value is required");
    }
    String text = input.trim();
    if (text.isEmpty()) {
        throw new IllegalArgumentException("value is empty");
    }
    return Integer.decode(text);
}
```

Đây là **một phương thức minh họa**, cần đặt trong class Java. Việc dùng `trim()` là **quyết định chính sách nhập liệu**, không phải hành vi có sẵn của `decode`. Với giao thức máy đọc các chuỗi có định dạng chặt chẽ, có thể muốn từ chối khoảng trắng thay vì tự sửa.

Nếu dữ liệu là số decimal do người dùng nhập vào, một API cụ thể hơn có thể là:

```java
static int parseDecimal(String input) {
    if (input == null) {
        throw new IllegalArgumentException("value is required");
    }
    return Integer.parseInt(input.trim());
}
```

Dùng `parseInt` ở đây vì đầu vào **được định nghĩa là decimal**, không phải chuỗi tiền tố tùy ý.

## 12. Phân biệt giá trị số với mã định danh

Không phải mọi chuỗi toàn chữ số đều nên parse thành số. Các mã sau có thể **phải được giữ dưới dạng `String`**:

- Mã khách hàng: `"000123"`.
- Mã sản phẩm: `"008"`.
- Mã bưu chính hoặc mã vùng tùy quốc gia: có thể bắt đầu bằng 0.
- Mã cấu hình có độ dài cố định, ví dụ `"0016"`.
- Một chuỗi nhị phân được yêu cầu đủ 16 bit với những số 0 đứng đầu.

Nếu bạn gọi `Integer.decode("000123")`, Java **diễn giải chuỗi là số bát phân**, hoàn toàn không giữ lại mã gốc. Thậm chí `"008"` gây lỗi. Nếu trường dữ liệu là định danh, **giữ `String`** và kiểm tra độ dài/ký tự hợp lệ, không dùng `decode`.

Đây là nguyên tắc mô hình hóa dữ liệu: **dữ liệu trông giống số chưa chắc có ngữ nghĩa số học**.

## 13. `Integer.getInteger` khác `Integer.decode`

Một cặp API tên giống nhau dễ gây nhầm:

- `Integer.decode("0x10")`: **phân tích chính chuỗi đã đưa vào**, nhận 16.
- `Integer.getInteger("name")`: đọc **Java system property** có tên `name`, rồi phân tích giá trị property đó theo quy tắc cơ số thích hợp. Nó **không** có nghĩa đọc một chuỗi số nguyên trực tiếp.

Ví dụ minh họa:

```java
System.setProperty("app.port", "0x1F90");
Integer port = Integer.getInteger("app.port"); // 8080
Integer fromText = Integer.decode("0x1F90");   // 8080
```

Đoạn code này đặt trong phương thức. `Integer.getInteger` có thể trả `null` khi property không tồn tại hoặc không phân tích hợp lệ; `decode` không phải lời gọi đọc system property.

Tương tự `Long.getLong` dành cho system property, không phải một biến thể thay thế `Long.decode` để parse các chuỗi số bất kỳ.

**An toàn khi dùng property:** system property có thể do môi trường thực thi cấu hình; luôn xác định giá trị mặc định và chính sách xử lý lỗi. Không nhầm giữa **tên thuộc tính** và **chuỗi số** khi gọi API.

## 14. `BigInteger` và dữ liệu vượt giới hạn `long`

Nếu giá trị thực sự có thể lớn hơn miền `long`, `Long.decode` không phù hợp. Java có `java.math.BigInteger` để xử lý số nguyên độ lớn tùy ý.

```java
import java.math.BigInteger;

BigInteger decimal = new BigInteger("18446744073709551615");
BigInteger hex = new BigInteger("FFFFFFFFFFFFFFFF", 16);
```

Đây là **đoạn mã minh họa**, cần đặt trong class/phương thức và khai báo import thích hợp. Cả hai đối tượng có cùng giá trị toán học là 18_446_744_073_709_551_615.

Khác với `decode`, constructor `BigInteger(String, radix)` nhận **dãy chữ số ứng với cơ số đã cho** chứ không tự chấp nhận `0x`:

```java
BigInteger value = new BigInteger("FF", 16); // 255
// new BigInteger("0xFF", 16); // NumberFormatException
```

Nếu protocol quy định các chuỗi có `0x` hay `0b` và số lượng chữ số không cố định, bạn có thể xây dựng một parser **chỉ chấp nhận đúng các tiền tố đã được liệt kê** rồi gọi constructor với `radix` phù hợp. Không nên tùy tiện chấp nhận mọi ký tự giống literal Java vì nó làm tăng độ phức tạp xác thực.

Lưu ý: `BigInteger` không có các phép cộng toán tử `+` giữa hai đối tượng; sử dụng `add`, `subtract` và `multiply`.

## 15. Xây dựng parser tùy biến khi cần cả `0b`

Giả sử yêu cầu dữ liệu là:

- Chuỗi thập phân không tiền tố.
- Hex với `0x` hoặc `0X`.
- Nhị phân với `0b` hoặc `0B`.
- Không hỗ trợ bát phân bằng 0 đứng đầu.
- Cho phép dấu `+` hoặc `-` đứng trước.
- Số ngoài miền `int` là lỗi.

Đây là **một hợp đồng khác `Integer.decode`**, nên hãy xây dựng parser riêng.

Tạo file `ExplicitRadixParserDemo.java`:

```java
public class ExplicitRadixParserDemo {
    static int parseFlexibleInt(String input) {
        if (input == null || input.isEmpty()) {
            throw new NumberFormatException("empty input");
        }

        int position = 0;
        boolean negative = false;

        char first = input.charAt(0);
        if (first == '-' || first == '+') {
            negative = first == '-';
            position = 1;
        }
        if (position == input.length()) {
            throw new NumberFormatException("missing digits");
        }

        int radix = 10;
        if (input.startsWith("0b", position)
                || input.startsWith("0B", position)) {
            radix = 2;
            position += 2;
        } else if (input.startsWith("0x", position)
                || input.startsWith("0X", position)) {
            radix = 16;
            position += 2;
        }
        if (position == input.length()) {
            throw new NumberFormatException("missing digits");
        }

        // Để parseInt kiểm tra chữ số và giới hạn signed int.
        String digits = input.substring(position);
        return Integer.parseInt((negative ? "-" : "") + digits, radix);
    }

    public static void main(String[] args) {
        System.out.println(parseFlexibleInt("42"));
        System.out.println(parseFlexibleInt("010"));
        System.out.println(parseFlexibleInt("0b101010"));
        System.out.println(parseFlexibleInt("-0B101010"));
        System.out.println(parseFlexibleInt("+0x2A"));
        System.out.println(parseFlexibleInt("-0x80000000"));
    }
}
```

Chạy:

```bash
javac ExplicitRadixParserDemo.java
java ExplicitRadixParserDemo
```

Kết quả:

```text
42
10
42
-42
42
-2147483648
```

Parser trên có hành vi **cố ý khác `decode`**: `"010"` được đọc theo decimal thành 10, thay vì bát phân thành 8. Nó không tự trim, không chấp nhận dấu gạch dưới hoặc hậu tố `L`, và luôn kiểm tra miền `int` bằng `Integer.parseInt`.

### Những điểm cần mở rộng nếu dùng trong production

- Hạn chế chiều dài input để tránh tài nguyên bị tiêu tốn quá mức.
- Ràng buộc loại prefix phù hợp giao thức; nếu cần `#`, bổ sung nhánh rõ ràng.
- Quy định có cho phép dấu `+` hay số `0` đứng đầu hay không.
- Chọn kiểu `long`/`BigInteger` nếu phạm vi cần lớn hơn.
- Báo lỗi phân biệt “ký tự sai”, “thiếu chữ số” và “ngoài miền” khi API yêu cầu.
- Kiểm thử chuỗi rỗng, `null`, tiền tố không có chữ số, giá trị MIN/MAX và số dài.

Không cần viết parser tùy biến nếu `parseInt` hoặc `decode` sẵn có đã **phù hợp chính xác hợp đồng đầu vào**.

## 16. Những lỗi thường gặp và cách sửa

| Lỗi hoặc nhầm lẫn | Nguyên nhân | Cách sửa |
|---|---|---|
| `decode("010")` ra 8 thay vì 10 | Số 0 đầu kích hoạt bát phân | Dùng `parseInt("010")` khi input là decimal |
| `decode("08")` ném lỗi | 8 không hợp lệ trong hệ bát phân | Dùng `parseInt("08")` nếu muốn decimal |
| `decode("0b1010")` không hoạt động | `decode` không hỗ trợ tiền tố nhị phân | `parseInt("1010", 2)` hoặc parser riêng |
| `parseInt("0xFF",16)` lỗi | `parseInt` nhận chữ số, không bóc tiền tố | Dùng `parseInt("FF",16)` hoặc `decode("0xFF")` |
| `decode("1_000")` lỗi | `_` là cú pháp literal, không phải cú pháp chuỗi parse | Dùng chuỗi chữ số hợp lệ |
| `decode("42L")` lỗi | Hậu tố `L` chỉ dùng ở literal Java | `Long.decode("42")` |
| `decode(" 42")` lỗi | Không tự bỏ khoảng trắng | Trim sau khi kiểm tra chính sách |
| `decode("0x-1")` lỗi | Dấu phải trước prefix | Viết `"-0x1"` |
| `decode("0xFFFFFFFF")` lỗi | Vượt miền `int` có dấu | Dùng unsigned parser sau khi bỏ `0x` |
| `Byte.decode("0200")` lỗi | Bát phân 200 bằng 128, ngoài miền `byte` | Chọn kiểu rộng hoặc xác định signed/unsigned |
| `getInteger("123")` không trả 123 như mong đợi | Tìm system property tên `123` | Dùng `parseInt`/`decode` |
| Parse mã `"000123"` và mất số 0 đầu | Đối xử mã định danh như số học | Giữ `String` |
| Chấp nhận mọi dạng prefix theo suy luận | Giao thức chưa định nghĩa radix | Thiết kế hợp đồng parser rõ ràng |

## 17. Bài tập tự kiểm tra

**Câu 1.** `Integer.decode("010")` và `Integer.parseInt("010")` lần lượt bằng bao nhiêu?  
**Đáp án:** 8 và 10; `decode` thấy bát phân còn `parseInt(String)` dùng decimal.

**Câu 2.** `Integer.decode("0x2A")` và `Integer.decode("#2A")` có giống nhau không?  
**Đáp án:** Có, đều bằng 42 vì đều dùng cơ số 16.

**Câu 3.** `Integer.decode("0b101010")` có cho 42 không?  
**Đáp án:** Không, nó ném `NumberFormatException`. Dùng `Integer.parseInt("101010", 2)`.

**Câu 4.** Vì sao `Integer.decode("08")` lỗi trong khi `Integer.parseInt("08")` trả 8?  
**Đáp án:** Dấu 0 đầu khiến `decode` hiểu là bát phân, nơi chữ số 8 không hợp lệ; `parseInt` mặc định decimal.

**Câu 5.** Dấu âm trong chuỗi hex nên viết ở đâu?  
**Đáp án:** Trước tiền tố: `"-0x2A"`, không phải `"0x-2A"`.

**Câu 6.** Có thể đọc `Integer.MIN_VALUE` bằng dạng hex không?  
**Đáp án:** Có: `Integer.decode("-0x80000000")` trả -2_147_483_648.

**Câu 7.** `Integer.decode("0xFFFFFFFF")` có trả -1 không?  
**Đáp án:** Không, chuỗi biểu thị số dương hex ngoài miền `int` có dấu. Dùng `Integer.parseUnsignedInt("FFFFFFFF",16)` để lấy mẫu bit, rồi đọc không dấu bằng `toUnsignedString`.

**Câu 8.** Vì sao `Integer.parseInt("FF",16)` được còn `Integer.parseInt("0xFF",16)` không được?  
**Đáp án:** Overload `parseInt(text, radix)` nhận **các chữ số** theo cơ số, không tự xử lý tiền tố.

**Câu 9.** Nếu cột dữ liệu chứa mã `"008"`, có nên dùng `decode` để lưu vào hệ thống không?  
**Đáp án:** Thường không. Đây có thể là mã định danh cần giữ nguyên số 0 đầu; dùng `String`.

**Câu 10.** `Long.decode("0x100000000")` bằng bao nhiêu?  
**Đáp án:** 4_294_967_296, nằm trong miền `long` có dấu.

**Câu 11.** Muốn đọc số nguyên quá lớn cho `long` từ chuỗi hex `"FFFFFFFFFFFFFFFF"` như **giá trị toán học dương**, dùng gì?  
**Đáp án:** `new BigInteger("FFFFFFFFFFFFFFFF", 16)`. Nếu chỉ cần mẫu bit không dấu 64 bit, dùng `Long.parseUnsignedLong("FFFFFFFFFFFFFFFF",16)` kèm API hiển thị/so sánh không dấu thích hợp.

**Câu 12.** `Integer.getInteger("app.port")` khác `Integer.decode("0x1F90")` ở đâu?  
**Đáp án:** Phương thức đầu đọc **giá trị system property** có tên `app.port` rồi parse; phương thức sau parse trực tiếp **chuỗi đối số**.

## 18. Checklist lựa chọn API và nguồn tham khảo

Trước khi triển khai parser cho chuỗi số nguyên:

1. Xác định trường dữ liệu là **số** hay **mã định danh**.
2. Định nghĩa **cơ số** và tiền tố hợp lệ ở API/giao thức.
3. Xác định cách xử lý **dấu**, số 0 đầu và khoảng trắng.
4. Chọn kiểu đích `byte`, `short`, `int`, `long`, `BigInteger` và giới hạn miền.
5. Quyết định đầu vào là **signed value** hay **unsigned bit pattern**.
6. Sử dụng `decode` chỉ khi quy tắc `0x`/`0X`/`#`/`0` bát phân thực sự được chấp nhận.
7. Dùng `parseInt(text)` hoặc `parseLong(text)` cho decimal; dùng `parseInt(text, radix)` khi cơ số được chỉ định.
8. Bắt `NumberFormatException` và chuyển thành lỗi phù hợp ở ranh giới dữ liệu.
9. Kiểm thử số MIN/MAX, các prefix hợp lệ/sai, input dài, dấu sai vị trí và khoảng trắng.
10. Không dùng khả năng parse được một chuỗi để suy ra dữ liệu phù hợp nghiệp vụ nếu còn ràng buộc khác.

**Ghi nhớ:** `Integer.decode` và `Long.decode` hỗ trợ **decimal**, **octal khi chuỗi bắt đầu bằng 0**, và **hex với `0x`, `0X`, `#`**; dấu `+/-` đứng **trước tiền tố**. Chúng **không** hiểu tiền tố `0b`, dấu `_` hay hậu tố `L` trong chuỗi runtime. Nếu yêu cầu là decimal, ưu tiên `parseInt`; nếu là bit pattern unsigned hoặc phạm vi số rất lớn, dùng API phù hợp hơn.

Tài liệu chuẩn:
- [Java SE 17 — Integer.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#decode(java.lang.String))
- [Java SE 17 — Long.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html#decode(java.lang.String))
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int))
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)

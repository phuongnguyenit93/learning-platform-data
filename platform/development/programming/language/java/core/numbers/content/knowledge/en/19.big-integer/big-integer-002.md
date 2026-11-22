# BigInteger: Tạo từ String, radix, long hoặc mảng byte

> **Java core – numbers · BigInteger**  
> **Mục tiêu:** Chọn đúng cách khởi tạo `java.math.BigInteger` từ văn bản thập phân, văn bản có cơ số, primitive `long`, dữ liệu nhị phân `byte[]` có dấu và dữ liệu nhị phân không dấu; đọc đúng big-endian/bù hai, xử lý dấu, đầu vào lỗi, độ rộng byte và kiểm tra chuyển đổi ngược.

## 1. BigInteger giải quyết vấn đề gì?

Các kiểu nguyên primitive trong Java có độ rộng cố định:

| Kiểu | Độ rộng | Miền giá trị |
| --- | ---: | --- |
| `byte` | 8 bit | −128 đến 127 |
| `short` | 16 bit | −32.768 đến 32.767 |
| `int` | 32 bit | −2³¹ đến 2³¹−1 |
| `long` | 64 bit | −2⁶³ đến 2⁶³−1 |

`BigInteger` là lớp **số nguyên độ chính xác tùy ý** (*arbitrary-precision integer*) trong `java.math`. Nó không giới hạn cố định ở 32 hoặc 64 bit như `int`/`long`; các giá trị rất lớn được xử lý bằng nhiều bit nội bộ, trong phạm vi tài nguyên và giới hạn triển khai của JVM.

```java
import java.math.BigInteger;

BigInteger x = new BigInteger("123456789012345678901234567890");
BigInteger y = BigInteger.valueOf(10L);
BigInteger sum = x.add(y);

System.out.println(sum);
// 123456789012345678901234567900
```

**Không có toán tử `+` cho hai đối tượng `BigInteger`.** Sử dụng `add`, `subtract`, `multiply`, `divide` và các phương thức khác. `BigInteger` là **immutable**: phép `add` trả một giá trị mới thay vì sửa x.

Một BigInteger có thể được xây dựng bằng nhiều con đường. Việc chọn API phải dựa vào **kiểu và cách mã hóa dữ liệu nguồn**, không chỉ giá trị muốn nhận:

| Dữ liệu hiện có | API nên dùng | Điểm cần hiểu |
| --- | --- | --- |
| Chuỗi số thập phân | `new BigInteger(text)` | Cho phép dấu `+`/`-` đầu chuỗi |
| Chuỗi số cơ số 2–36 | `new BigInteger(text, radix)` | Cần chỉ rõ cơ số, không tự hiểu `0x` |
| Primitive `long` | `BigInteger.valueOf(number)` | Giữ nguyên giá trị có dấu của long |
| `byte[]` đã mã hóa signed two's complement | `new BigInteger(bytes)` | Big-endian, bit dấu của byte đầu có ý nghĩa |
| `byte[]` chứa độ lớn **unsigned** | `new BigInteger(1, bytes)` | Signum dương, không coi bit cao là dấu |
| Độ lớn và dấu được truyền riêng | `new BigInteger(signum, magnitude)` | Signum −1, 0, +1; magnitude là big-endian unsigned |
| Chỉ một lát cắt trong `byte[]` | Constructor có `off,len` (Java 9+) | Không cần tự tạo mảng con để gọi constructor |

**Câu hỏi quyết định cho byte array:** “Đây là số nguyên signed theo bù hai, hay một chuỗi byte unsigned biểu diễn độ lớn?” Hai cách hiểu này có thể cho kết quả **trái dấu** từ chính các byte giống nhau.

## 2. Tạo từ String thập phân

Constructor thông dụng nhất:

```java
BigInteger decimal = new BigInteger("123456789012345678901234567890");
BigInteger negative = new BigInteger("-255");
BigInteger positive = new BigInteger("+255");

System.out.println(decimal);  // 123456789012345678901234567890
System.out.println(negative); // -255
System.out.println(positive); // 255
```

`new BigInteger(String)` đọc chuỗi **decimal radix 10** theo mặc định. Chuỗi gồm một dấu đầu `+` hoặc `-` tùy chọn, theo sau bởi ít nhất một chữ số hợp lệ. Không truyền chuỗi rỗng hoặc chỉ có dấu.

Các chuỗi sau là các trường hợp cần phân biệt:

| Đầu vào | Kết quả |
| --- | --- |
| `"123"` | 123 |
| `"+123"` | 123 |
| `"-123"` | −123 |
| `"000123"` | 123, bỏ các số 0 đầu |
| `"-0"` | 0, không có trạng thái “âm zero” như float |
| `""` | `NumberFormatException` |
| `"+"` | `NumberFormatException` |
| `"12.0"` | `NumberFormatException` |
| `" 123 "` | `NumberFormatException` vì có ký tự thừa |
| `"1_000"` | `NumberFormatException` với quy tắc parser chuẩn |

**BigInteger chỉ biểu diễn số nguyên.** Nó không âm thầm cắt phần lẻ của chuỗi decimal hay chấp nhận dấu chấm như `BigDecimal`. Nếu nguồn là `"12.5"` và nghiệp vụ thực sự cho phép phần lẻ, hãy dùng kiểu/luồng chuyển đổi được thiết kế cho decimal có scale, không ép dữ liệu thành BigInteger bằng cách tự bỏ ký tự.

### Chữ số Unicode

Quy tắc ánh xạ ký tự thành chữ số dùng `Character.digit(char, radix)`, có thể chấp nhận một số ký tự chữ số Unicode. Nếu giao thức chỉ cho phép **ASCII `0..9`**, cần **validate riêng** trước hoặc cùng lúc với parse. Thành công của `new BigInteger(text)` không tự chứng minh token chứa toàn ASCII.

## 3. Tạo từ String theo radix (cơ số)

Dùng constructor:

```java
BigInteger binary = new BigInteger("101101", 2); // 45
BigInteger octal = new BigInteger("77", 8);      // 63
BigInteger hex = new BigInteger("FF", 16);       // 255
BigInteger base36 = new BigInteger("ZZ", 36);    // 1295
```

`radix` phải nằm trong khoảng **2 đến 36**. Các chữ số thập phân và chữ cái hợp lệ được quy đổi theo `Character.digit`. Chữ `A`/`a` là 10 trong cơ số 16, `F`/`f` là 15, `Z`/`z` là 35 trong cơ số 36.

Ví dụ có dấu:

```java
System.out.println(new BigInteger("-FF", 16));  // -255
System.out.println(new BigInteger("+100", 2));  // 4
System.out.println(new BigInteger("000101", 2)); // 5
```

**Sai lầm dễ gặp: tiền tố không tự được loại bỏ.**

```java
// new BigInteger("0xFF", 16); // NumberFormatException
// new BigInteger("0b101", 2); // NumberFormatException
```

Đây là **dữ liệu chuỗi runtime**, không phải literal Java trong mã nguồn. Với radix 16, hãy đưa chuỗi chữ số `"FF"` (và dấu nếu có), **không đưa `"0x"`**. Nếu giao thức cho phép tiền tố, tách và validate prefix trước khi truyền chuỗi chữ số cho constructor.

Ví dụ parse định dạng có tiền tố cố định:

```java
static BigInteger parsePrefixedHex(String text) {
    if (text == null || !text.startsWith("0x")) {
        throw new IllegalArgumentException("Expected 0x prefix");
    }
    return new BigInteger(text.substring(2), 16);
}
```

Đây là **phương thức minh họa**, cần đặt trong một class. Nó cố ý chỉ chấp nhận `0x` chữ thường ở đầu và số **không có dấu** sau prefix; nếu cần nhận `-0xFF` hoặc `0XFF`, phải định nghĩa cú pháp ấy và kiểm tra riêng. Đừng dùng một thao tác `replace` xóa `0x` ở mọi vị trí vì có thể chấp nhận chuỗi sai.

### toString(radix) là hướng chuyển đổi ngược

```java
BigInteger n = new BigInteger("255");
System.out.println(n.toString(2));  // 11111111
System.out.println(n.toString(16)); // ff
System.out.println(n.toString(10)); // 255
```

`toString(radix)` thường dùng chữ cái **thường** cho cơ số lớn hơn 10 và không thêm `0x`/`0b`. Với radix hợp lệ, có thể dùng hai đầu của một cặp round-trip:

```java
BigInteger original = new BigInteger("-12345678901234567890");
String encoded = original.toString(16);
BigInteger restored = new BigInteger(encoded, 16);

System.out.println(original.equals(restored)); // true
```

Dùng `equals` để so sánh **giá trị** đối tượng, không dùng `==` để kiểm tra hai biến có cùng số hay không.

## 4. Tạo từ long: dùng BigInteger.valueOf(long)

Nếu đầu vào đã là primitive `long`, dùng static factory:

```java
long id = 9_000_000_000L;
BigInteger bigId = BigInteger.valueOf(id);

System.out.println(bigId); // 9000000000
```

Không có constructor public `BigInteger(long)` tương ứng:

```java
// BigInteger wrong = new BigInteger(123L); // Không biên dịch
BigInteger correct = BigInteger.valueOf(123L);
```

Phương thức `valueOf` bảo toàn **giá trị có dấu** của `long`, bao gồm biên âm và dương:

```java
BigInteger low = BigInteger.valueOf(Long.MIN_VALUE);
BigInteger high = BigInteger.valueOf(Long.MAX_VALUE);

System.out.println(low); // -9223372036854775808
System.out.println(high); // 9223372036854775807
```

Nếu đầu vào là `int`, Java tự mở rộng int sang long khi gọi `BigInteger.valueOf`:

```java
int count = 12;
BigInteger n = BigInteger.valueOf(count);
```

Phương thức không “đoán” giá trị ban đầu đã nằm ngoài miền long: nếu một phép toán `long` bị tràn **trước** khi gọi, `valueOf` chỉ nhận giá trị sau tràn.

```java
long a = Long.MAX_VALUE;
long wrong = a + 1; // overflow thành Long.MIN_VALUE

BigInteger alreadyLost = BigInteger.valueOf(wrong);
BigInteger exact = BigInteger.valueOf(a).add(BigInteger.ONE);

System.out.println(alreadyLost); // -9223372036854775808
System.out.println(exact);       // 9223372036854775808
```

**Giữ dữ liệu chính xác ngay từ đầu:** với số nguyên literal ngoài miền `long`, tạo từ **chuỗi decimal** chứ không ép literal vào `long` rồi mới chuyển. Đối với phép tính có thể tràn, chuyển các toán hạng sang BigInteger **trước khi thực hiện phép cộng/nhân**.

### valueOf không phải parser chuỗi

`BigInteger.valueOf("123")` **không tồn tại**. Dùng:

```java
BigInteger fromText = new BigInteger("123");
BigInteger fromPrimitive = BigInteger.valueOf(123L);
```

Khác với `Integer.valueOf(String)` hoặc `Long.valueOf(String)`, BigInteger dùng constructor từ `String` để parse.

## 5. Tạo từ byte[]: Java mặc định hiểu signed two's complement

Constructor:

```java
BigInteger n = new BigInteger(byteArray);
```

giả định mảng biểu diễn **số nguyên theo bù hai có dấu** (*two's complement*) theo thứ tự **big-endian**: phần tử ở chỉ số 0 là byte có trọng số lớn nhất.

Ví dụ một byte:

```text
Byte hex    8 bit             BigInteger(byte[])
---------------------------------------------------
0x00        00000000                0
0x01        00000001                1
0x7F        01111111              127
0x80        10000000             -128
0xFF        11111111               -1
```

Trong Java:

```java
byte[] bytes = {(byte) 0xFF};
BigInteger signed = new BigInteger(bytes);
System.out.println(signed); // -1
```

**Tại sao `0xFF` lại thành −1 chứ không phải 255?** Bit cao nhất của byte đầu là bit dấu trong biểu diễn hai's complement dài 8 bit. Mẫu toàn bit 1 mô tả −1.

Nhiều byte có cùng quy tắc:

```java
BigInteger positive128 = new BigInteger(
        new byte[] {0x00, (byte) 0x80});
BigInteger negative256 = new BigInteger(
        new byte[] {(byte) 0xFF, 0x00});

System.out.println(positive128); // 128
System.out.println(negative256); // -256
```

Với `[00,80]`, byte `00` đầu tiên giữ bit dấu bằng 0; giá trị là 128. Với `[FF,00]`, mẫu 16 bit `11111111 00000000` là −256 theo bù hai.

**Đừng bỏ byte `00` đầu trong bản mã signed nếu byte kế tiếp có bit cao là 1.** Bỏ `00` khỏi `[00,FF]` biến số 255 thành −1.

## 6. Byte array không dấu: constructor (signum, magnitude)

Nhiều giao thức gửi **độ lớn unsigned** dưới dạng mảng byte: một octet `0xFF` có nghĩa 255 chứ không phải −1. Khi đó dùng:

```java
byte[] unsignedMagnitude = {(byte) 0xFF};
BigInteger n = new BigInteger(1, unsignedMagnitude);
System.out.println(n); // 255
```

Constructor `BigInteger(int signum, byte[] magnitude)` nhận:

- `signum = 1`: giá trị không âm/dương với độ lớn mảng byte;
- `signum = -1`: giá trị âm với độ lớn mảng byte;
- `signum = 0`: chỉ hợp lệ khi toàn bộ magnitude biểu diễn **0**.

Mảng `magnitude` chứa **độ lớn nguyên không dấu** big-endian. Các giá trị `byte` trong Java có thể âm khi cast hoặc in trực tiếp, nhưng constructor đọc **mẫu 8 bit** của từng byte như octet thuộc phần độ lớn.

Ví dụ:

```java
byte[] mag = {(byte) 0xFF};

System.out.println(new BigInteger(mag));    // -1: signed two's complement
System.out.println(new BigInteger(1, mag)); // 255: positive magnitude
System.out.println(new BigInteger(-1, mag));// -255: negative magnitude
```

Đây là **ba cách đọc khác nhau** từ cùng byte `FF`. Hãy đọc contract của định dạng nguồn trước khi chọn constructor.

### Signum sai gây lỗi

```java
// new BigInteger(0, new byte[] {1});
// NumberFormatException: signum 0 nhưng magnitude khác 0

// new BigInteger(2, new byte[] {1});
// NumberFormatException: signum không thuộc -1,0,1
```

Mảng độ lớn rỗng hoặc toàn số 0 biểu diễn giá trị **0** kể cả khi signum truyền vào là +1 hoặc −1:

```java
BigInteger zero = new BigInteger(1, new byte[0]);
System.out.println(zero);        // 0
System.out.println(zero.signum());// 0
```

BigInteger không có âm zero hay dương zero dưới dạng giá trị nguyên riêng biệt.

### Không nhầm signum với byte dấu

Tham số đầu tiên trong `new BigInteger(1, bytes)` là **chính dấu** do caller cung cấp; nó không lấy từ bit cao của dữ liệu byte. Nếu giao thức của bạn đã mã hóa dấu trong mảng byte bù hai, **đừng** thêm signum=1 tùy tiện vì sẽ làm số âm thành số dương.

## 7. Cấu trúc big-endian: byte có trọng số cao nhất nằm trước

Big-endian với byte unsigned `{0x01,0x00}`:

\[
1\times256 + 0=256
\]

```java
byte[] bytes = {0x01, 0x00};
System.out.println(new BigInteger(1, bytes)); // 256
```

Nếu nguồn của bạn là **little-endian**, byte thấp nhất nằm trước. Không được truyền thẳng mảng little-endian vào các constructor BigInteger rồi kỳ vọng đúng trị số.

Ví dụ số `0x0102 = 258`:

```java
byte[] bigEndian = {0x01, 0x02};
byte[] littleEndian = {0x02, 0x01};

System.out.println(new BigInteger(1, bigEndian));     // 258
System.out.println(new BigInteger(1, littleEndian)); // 513
```

Nếu giao thức little-endian, chuyển thứ tự byte **theo đúng đặc tả** hoặc dùng một bộ đọc byte theo endianness đã chọn rồi chuyển sang BigInteger. Không nên làm lật byte vô điều kiện: một số trường đã là big-endian, một số trường chỉ có một byte, một số trường dùng signed two's complement.

### ByteBuffer và toByteArray

`ByteBuffer` có cấu hình thứ tự byte riêng cho các phép đọc primitive đa byte. Nhưng `BigInteger(byte[])` **không nhận ByteBuffer và không tự đọc `ByteOrder`** của buffer. Chỉ khi đã có `byte[]` đúng thứ tự mong muốn mới truyền vào constructor thích hợp.

Khi đọc từ buffer với vị trí/giới hạn, kiểm tra byte nào thuộc token, không vô tình đưa header/checksum vào số.

## 8. Java 9+: constructor đọc một đoạn của byte[]

Java 9 bổ sung hai constructor có offset/length, đều có trong Java 17:

```java
new BigInteger(byte[] val, int off, int len);
new BigInteger(int signum, byte[] magnitude, int off, int len);
```

- `off`: chỉ số phần tử bắt đầu trong mảng (zero-based).
- `len`: **số byte cần đọc**, **không phải chỉ số kết thúc**.
- Hai phiên bản đều coi các byte được chọn theo **big-endian**.
- Phiên bản không signum đọc **two's complement signed**.
- Phiên bản có signum đọc **unsigned magnitude** có dấu ngoài mảng.

Ví dụ một buffer có byte header/trailer:

```java
byte[] packet = {0x55, 0x00, (byte) 0x80, 0x66};

// Lấy 2 byte ở [1,3): 00 80, signed = 128
BigInteger value = new BigInteger(packet, 1, 2);

// Lấy đúng 1 byte ở [2,3): 80, unsigned magnitude = 128
BigInteger positive = new BigInteger(1, packet, 2, 1);

System.out.println(value);    // 128
System.out.println(positive); // 128
```

Nếu dùng signed constructor với `off=2,len=1`, chỉ có byte `80` và kết quả là **−128**:

```java
System.out.println(new BigInteger(packet, 2, 1)); // -128
```

Đây là sai lầm **rất khó phát hiện nếu chỉ thử dữ liệu có bit đầu bằng 0**.

Chỉ số vượt miền gây `IndexOutOfBoundsException`. Với dữ liệu bù hai, khoảng rỗng không mô tả một số hợp lệ và có thể gây `NumberFormatException`; với constructor signum/magnitude, độ lớn rỗng là số 0 hợp lệ.

Một constructor đọc subarray giúp tránh việc **người gọi phải tạo mảng con** chỉ để parse. Nó **không cam kết zero-allocation nội bộ**, và không bảo đảm an toàn nếu mảng bị sửa đồng thời trong quá trình constructor đọc: yêu cầu caller giữ dữ liệu ổn định trong cuộc gọi.

## 9. toByteArray(): mã hóa ngược bằng bù hai, không phải magnitude unsigned

Phương thức `value.toByteArray()` trả byte **big-endian signed two's complement tối thiểu**. `BigInteger.valueOf(255).toByteArray()` là `00 FF`, còn `BigInteger.valueOf(-1).toByteArray()` là `FF`. Byte `00` bảo vệ dấu của số dương có bit cao bật; mảng này không phải magnitude unsigned. Vòng `new BigInteger(value.toByteArray())` khôi phục **giá trị số** chính xác, nhưng không cam kết khôi phục độ dài input gốc.

## 10. Dữ liệu unsigned có chiều rộng cố định: cần hợp đồng rõ ràng

Với một trường hai byte unsigned `FF FF`, `new BigInteger(bytes)` cho -1, còn `new BigInteger(1,bytes)` cho 65535. Khi **xuất** unsigned N byte, phải kiểm tra số không âm và vừa `0..2^(8N)-1`, loại đúng byte dấu `00` khi có, sau đó đệm `00` ở bên trái đến N byte. Không được cắt dữ liệu mang giá trị hoặc quên trường hợp zero; các codec signed/unsigned fixed-width và round trip chi tiết được thực hành ở bài chuyên về `toByteArray`.

## 11. Cảnh giác dữ liệu ASCII/UTF-8: byte chuỗi KHÔNG phải giá trị số

Nếu có văn bản số `"123"`, có thể nghĩ:

```java
byte[] textBytes = "123".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
BigInteger wrong = new BigInteger(textBytes);
```

Nhưng byte UTF-8 của ba ký tự `'1','2','3'` là `0x31,0x32,0x33`. `new BigInteger(textBytes)` sẽ diễn giải **ba byte này như số nguyên nhị phân big-endian**, không thực hiện phân tích decimal từ chuỗi.

Cách đúng:

```java
BigInteger fromDecimal = new BigInteger("123");
```

Ngược lại, nếu byte array đến từ một protocol truyền **giá trị số nhị phân**, không biến nó thành `new String(bytes, UTF_8)` rồi parse decimal: byte `0xFF` hoặc nhiều byte điều khiển không phải chữ số văn bản hợp lệ.

**Quy tắc lựa chọn:** xác định đầu vào là **văn bản biểu diễn số** hay **mẫu bit biểu diễn số**. Không thể thay lẫn hai cách này chỉ vì cả hai cuối cùng đều nằm trong `byte[]` ở tầng mạng.

## 12. Xử lý lỗi khi tạo BigInteger

Các lỗi cần phân biệt theo loại nguồn:

| Nguồn và tình huống | Lỗi / cách xử lý |
| --- | --- |
| `new BigInteger("12X")` radix 10 | `NumberFormatException` |
| `new BigInteger("FF", 1)` radix ngoài 2..36 | `NumberFormatException` |
| `new BigInteger("")` | `NumberFormatException` |
| `new BigInteger("0xFF",16)` | `NumberFormatException` |
| `new BigInteger(new byte[0])` | `NumberFormatException` |
| `new BigInteger(0,new byte[]{1})` | `NumberFormatException` |
| `new BigInteger(2,new byte[]{1})` | `NumberFormatException` |
| Constructor byte[] với off/len vượt phạm vi | `IndexOutOfBoundsException` |
| Tham số đối tượng `null` | `NullPointerException` |
| Giá trị quá lớn vượt khả năng triển khai/tài nguyên | Có thể lỗi giới hạn/`ArithmeticException` hoặc lỗi tài nguyên; không coi là vô hạn |

Ví dụ:

```java
try {
    BigInteger n = new BigInteger("0xFF", 16);
} catch (NumberFormatException ex) {
    System.out.println("Invalid numeric token");
}
```

Đừng bắt tất cả `RuntimeException` và trả `BigInteger.ZERO`. Giá trị 0 hoàn toàn hợp lệ, nên **không được** dùng như mã thay thế chung cho token sai nếu nghiệp vụ cần phân biệt dữ liệu trống/sai với số 0 thật.

Nếu đầu vào đến từ người dùng hoặc mạng, cân nhắc giới hạn số chữ số/byte trước khi parse để bảo vệ CPU/bộ nhớ, xác nhận radix, sign, endianness và độ dài của trường.

## 13. BigInteger không biến mọi phép chuyển đổi ngược thành an toàn

Tạo BigInteger từ `long` giữ đúng giá trị; nhưng đọc ngược về `long` có thể mất dữ liệu nếu số BigInteger vượt miền long:

```java
BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

System.out.println(huge);             // 9223372036854775808
System.out.println(huge.longValue()); // -9223372036854775808
```

`longValue()` giữ các bit thấp phù hợp theo quy tắc chuyển đổi, **không tự ném lỗi**. Nếu cần bảo toàn giá trị hoặc báo lỗi, dùng:

```java
try {
    long checked = huge.longValueExact();
} catch (ArithmeticException ex) {
    System.out.println("Value outside long range");
}
```

Tương tự có `intValueExact()`, `shortValueExact()`, `byteValueExact()`. Khi đầu vào BigInteger được tạo từ String rất dài hoặc unsigned field vượt phạm vi signed, **đừng** tự đổi về `int`/`long` chỉ vì kiểu nghiệp vụ trước đây dùng primitive.

Một BigInteger có thể chứa giá trị unsigned 64-bit từ mảng 8 byte `FF FF FF FF FF FF FF FF`, tương đương `18446744073709551615`, nhưng `longValue()` của nó là −1. Đây là **cùng bit thấp diễn giải signed**, không phải lỗi parser.

## 14. Immutable, equals và các hằng thường dùng

Các BigInteger bất biến. Ví dụ:

```java
BigInteger a = new BigInteger("123");
BigInteger b = a.add(BigInteger.ONE);

System.out.println(a); // 123
System.out.println(b); // 124
```

Các hằng có sẵn: `BigInteger.ZERO`, `BigInteger.ONE`, `BigInteger.TWO` (có từ Java 9) và `BigInteger.TEN`. Chúng phù hợp để thể hiện giá trị cố định mà không phải parse chuỗi nhiều lần:

```java
BigInteger zero = BigInteger.ZERO;
BigInteger power = BigInteger.TWO.pow(16);
System.out.println(power); // 65536
```

Dùng `equals` để kiểm tra giá trị:

```java
BigInteger x = new BigInteger("255");
BigInteger y = new BigInteger(1, new byte[]{(byte) 0xFF});

System.out.println(x.equals(y)); // true
```

Toán tử `==` so sánh **tham chiếu đối tượng**, không phải nội dung số. `BigInteger.valueOf` có thể tái sử dụng đối tượng cho một số giá trị; **không dựa vào identity/cache** để kiểm tra hai số bằng nhau.

## 15. Demo Java 17+ đầy đủ, đã kiểm chứng stdout

Tạo tệp **`BigIntegerConstructionDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerConstructionDemo {
    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte value : bytes) {
            out.append(String.format("%02x", value & 0xff));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        BigInteger decimal =
                new BigInteger("123456789012345678901234567890");
        BigInteger negative = new BigInteger("-255");
        BigInteger hexNumber = new BigInteger("FF", 16);
        BigInteger binary = new BigInteger("101101", 2);
        BigInteger base36 = new BigInteger("ZZ", 36);
        BigInteger fromLong = BigInteger.valueOf(Long.MIN_VALUE);

        System.out.println("decimal = " + decimal);
        System.out.println("negative = " + negative);
        System.out.println("hex = " + hexNumber);
        System.out.println("binary = " + binary);
        System.out.println("base36 = " + base36);
        System.out.println("long minimum = " + fromLong);
        System.out.println("255 to hex = "
                + hexNumber.toString(16));

        byte[] oneByte = {(byte) 0xff};
        BigInteger signed = new BigInteger(oneByte);
        BigInteger unsigned = new BigInteger(1, oneByte);
        BigInteger prefixed = new BigInteger(
                new byte[] {0x00, (byte) 0xff});
        BigInteger negativeBytes = new BigInteger(
                new byte[] {(byte) 0xff, 0x00});

        System.out.println("0xff signed = " + signed);
        System.out.println("0xff magnitude = " + unsigned);
        System.out.println("00ff signed = " + prefixed);
        System.out.println("ff00 signed = " + negativeBytes);
        System.out.println("255 encoded = "
                + hex(unsigned.toByteArray()));
        System.out.println("-1 encoded = "
                + hex(signed.toByteArray()));
        System.out.println("0 encoded = "
                + hex(BigInteger.ZERO.toByteArray()));

        byte[] packet = {0x55, 0x00, (byte) 0x80, 0x66};
        BigInteger rangeSigned =
                new BigInteger(packet, 1, 2);
        BigInteger rangeMagnitude =
                new BigInteger(1, packet, 2, 1);
        System.out.println("range signed = " + rangeSigned);
        System.out.println("range magnitude = " + rangeMagnitude);
        System.out.println("bytes round-trip = "
                + unsigned.equals(
                        new BigInteger(unsigned.toByteArray())));
        System.out.println("empty magnitude = "
                + new BigInteger(1, new byte[0]));

        try {
            new BigInteger("0xFF", 16);
        } catch (NumberFormatException ex) {
            System.out.println("prefix: rejected");
        }
        try {
            new BigInteger("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("underscore: rejected");
        }
        try {
            new BigInteger("FF", 1);
        } catch (NumberFormatException ex) {
            System.out.println("radix: rejected");
        }
        try {
            new BigInteger(new byte[0]);
        } catch (NumberFormatException ex) {
            System.out.println("empty signed bytes: rejected");
        }
        try {
            new BigInteger(0, new byte[] {1});
        } catch (NumberFormatException ex) {
            System.out.println("signum mismatch: rejected");
        }
        try {
            new BigInteger(packet, 3, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("range: rejected");
        }
        try {
            BigInteger.valueOf(Long.MAX_VALUE)
                    .add(BigInteger.ONE).longValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("long exact: rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 BigIntegerConstructionDemo.java
java BigIntegerConstructionDemo
```

**Stdout đã đối chiếu bằng một chương trình biên dịch với `javac --release 17`:**

```text
decimal = 123456789012345678901234567890
negative = -255
hex = 255
binary = 45
base36 = 1295
long minimum = -9223372036854775808
255 to hex = ff
0xff signed = -1
0xff magnitude = 255
00ff signed = 255
ff00 signed = -256
255 encoded = 00ff
-1 encoded = ff
0 encoded = 00
range signed = 128
range magnitude = 128
bytes round-trip = true
empty magnitude = 0
prefix: rejected
underscore: rejected
radix: rejected
empty signed bytes: rejected
signum mismatch: rejected
range: rejected
long exact: rejected
```

### Cách đọc kết quả

1. `new BigInteger("...")` giữ số nguyên decimal dài, `new BigInteger("FF",16)` nhận 255, `valueOf(Long.MIN_VALUE)` giữ đúng biên âm long.
2. Cùng byte `FF` được đọc **−1** khi dùng signed constructor, nhưng **255** khi dùng signum +1.
3. `00 FF` là bản mã signed dương của 255; `FF 00` biểu diễn signed −256.
4. `toByteArray()` không hứa một byte cho 255; nó cần thêm `00` đầu để giữ dấu dương.
5. Các constructor có `off,len` cho phép đọc một vùng byte mà không cần `Arrays.copyOfRange` ở phía caller.
6. Những chuỗi chứa prefix/underscore, radix sai, mảng signed rỗng, signum sai, phạm vi sai và chuyển đổi long không an toàn đều có cách báo lỗi riêng.

## 16. Lỗi phổ biến cần tránh

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “BigInteger có constructor nhận long” | Dùng `BigInteger.valueOf(long)` |
| “valueOf nhận chuỗi như Integer.valueOf” | BigInteger parse chuỗi bằng `new BigInteger(String)` |
| “BigInteger(String) tự nhận `0xFF`” | Constructor mặc định radix 10; với hex truyền `"FF",16` |
| “`new BigInteger("1_000")` giống literal Java `1_000`” | Parser runtime không hiểu dấu gạch dưới như cú pháp mã nguồn |
| “Tạo từ String thì không thể vượt giới hạn long” | Chuỗi decimal có thể dài hơn miền long nhiều lần |
| “Giá trị byte 0xFF luôn là 255” | `BigInteger(byte[])` diễn giải signed `FF` thành −1 |
| “Mảng byte theo little-endian truyền trực tiếp là đúng” | Constructor BigInteger dùng big-endian |
| “`new BigInteger(1,bytes)` vẫn suy dấu từ bit cao” | Signum=1 buộc cách đọc **độ lớn dương** |
| “`toByteArray` trả unsigned magnitude cố định N byte” | Nó trả signed two's complement, độ dài biến thiên |
| “Byte `00` đầu luôn thừa” | Có thể là byte cần thiết giữ sign dương khi byte kế có bit cao 1 |
| “Mảng signed rỗng và magnitude rỗng có cùng hành vi” | Signed rỗng bị từ chối; magnitude rỗng có thể cho zero |
| “Offset,length nghĩa là hai vị trí đầu/cuối” | `len` là số byte, không phải endIndex |
| “BigInteger có nghĩa là tài nguyên vô hạn” | Vẫn chịu giới hạn bộ nhớ, CPU và hỗ trợ JVM |
| “big.longValue() luôn an toàn” | Có thể cắt bit; dùng `longValueExact()` nếu cần toàn vẹn |
| “So sánh BigInteger bằng ==” | Dùng `equals` hoặc `compareTo` theo giá trị |
| “Có thể tạo BigInteger từ byte UTF-8 của chuỗi số” | Byte mã hóa ký tự không đồng nghĩa byte biểu diễn số |
| “Đổi số sang BigInteger sau khi tràn sẽ sửa tràn” | Phải chuyển toán hạng **trước** phép tính có thể tràn |

## 17. Bài tập có lời giải

**Bài 1.** Tạo BigInteger từ số decimal `"987654321098765432109876543210"` mà không đi qua long.  
**Lời giải:** `new BigInteger("987654321098765432109876543210")`; không có bước chuyển sang primitive.

**Bài 2.** Giá trị của `new BigInteger("101101",2)`?  
**Lời giải:** `32+8+4+1=45`. Chuỗi nhị phân không cần tiền tố `0b`.

**Bài 3.** Giá trị của `new BigInteger("FF",16)`? Vì sao `"0xFF"` khác?  
**Lời giải:** 255. Constructor radix 16 không tự bỏ prefix `0x`; `new BigInteger("0xFF",16)` ném `NumberFormatException`.

**Bài 4.** Tạo từ `Long.MIN_VALUE` thế nào?  
**Lời giải:** `BigInteger.valueOf(Long.MIN_VALUE)`. Không cần dựng chuỗi, không có constructor `BigInteger(long)`.

**Bài 5.** Hai biểu thức `new BigInteger(new byte[]{(byte)0x80})` và `new BigInteger(1,new byte[]{(byte)0x80})` bằng bao nhiêu?  
**Lời giải:** −128 và +128. Mẫu bit `80` là signed two's complement âm nhưng magnitude unsigned là 128.

**Bài 6.** Vì sao `new BigInteger(new byte[]{0x00,(byte)0xFF})` là 255?  
**Lời giải:** Byte 00 đầu có bit dấu 0, mẫu 16 bit `00FF` là +255. Bỏ 00 còn `FF` sẽ bị hiểu là −1 dưới signed constructor.

**Bài 7.** Byte mảng `{0x01,0x00}` big-endian unsigned biểu diễn giá trị nào?  
**Lời giải:** `0x0100 = 256`. Dùng `new BigInteger(1,bytes)` nếu contract dữ liệu là unsigned magnitude.

**Bài 8.** `new BigInteger(0,new byte[]{1})` có giá trị là 0 không?  
**Lời giải:** Không; ném `NumberFormatException` vì signum=0 không khớp với magnitude khác 0.

**Bài 9.** Với `byte[] packet={0x55,0x00,(byte)0x80,0x66}`, `new BigInteger(packet,1,2)` lấy những byte nào?  
**Lời giải:** Byte ở chỉ số 1 và 2 (`00 80`), kết quả 128; `len=2` là chiều dài, không phải chỉ số kết thúc.

**Bài 10.** `BigInteger.valueOf(255).toByteArray()` có chắc chỉ chứa một byte `FF` không?  
**Lời giải:** Không; nó trả `00 FF` ở dạng signed, vì `FF` đơn lẻ biểu diễn −1.

**Bài 11.** Một trường mạng hai byte có `FF FF` và được định nghĩa là unsigned. Dùng constructor nào và giá trị nào?  
**Lời giải:** `new BigInteger(1,new byte[]{(byte)0xFF,(byte)0xFF})`, cho 65535. Signed constructor sẽ cho −1.

**Bài 12.** `new BigInteger("-0")` và `new BigInteger(1,new byte[0])` có giá trị khác nhau không?  
**Lời giải:** Không. Cả hai là số nguyên zero; BigInteger không có ±0 như floating-point.

**Bài 13.** Muốn chuyển BigInteger rất lớn về long mà **không mất dữ liệu** thì làm gì?  
**Lời giải:** Dùng `longValueExact()`. Nếu không biểu diễn được trong long, phương thức ném `ArithmeticException` thay vì âm thầm bỏ bit.

**Bài 14.** Vì sao `new BigInteger("123".getBytes(UTF_8))` không tương đương `new BigInteger("123")`?  
**Lời giải:** Cái đầu đọc mẫu byte `31 32 33` như số nhị phân; cái sau parse ba chữ số decimal thành 123.

**Bài 15.** Chương trình lấy `BigInteger.valueOf(a+b)` với a,b là long lớn. Khi nào có thể sai?  
**Lời giải:** Nếu `a+b` tràn **trước khi được chuyển sang BigInteger**; sửa thành `BigInteger.valueOf(a).add(BigInteger.valueOf(b))`.

## 18. Checklist chọn cách tạo BigInteger

1. **Nhận diện định dạng nguồn:** text decimal, text radix khác, primitive long, byte array signed hay unsigned?
2. **Với String:** quyết định radix 2–36, chính sách dấu, khoảng trắng, prefix, ASCII/Unicode digits và giới hạn độ dài.
3. **Với long:** dùng `valueOf(long)`, nhưng bảo đảm phép toán trước đó chưa overflow.
4. **Với byte[] signed:** dùng `new BigInteger(bytes)` và hiểu big-endian two's complement.
5. **Với byte[] unsigned:** dùng `new BigInteger(1,bytes)` hoặc signum theo hợp đồng, không suy dấu từ byte đầu.
6. **Với byte subarray:** constructor `(off,len)` từ Java 9+, chú ý `len` là chiều dài và input phải ổn định khi được đọc.
7. **Khi lưu ngược ra byte[]:** `toByteArray()` là signed, độ dài biến thiên; cần quy tắc riêng nếu protocol unsigned/fixed-width.
8. **Không trộn ASCII bytes và binary bytes**: byte mã hóa ký tự `'1'` không phải số nguyên 1.
9. **Kiểm tra lỗi riêng:** parse/radix/signed byte rỗng, signum sai, index sai, null, vượt giới hạn tài nguyên.
10. **Khi chuyển về primitive:** dùng các phương thức `*ValueExact` nếu nghiệp vụ không được mất thông tin.
11. **So sánh bằng `equals`**, không dùng `==` cho hai BigInteger.
12. **Dùng bài test biên:** 0, −1, 127, 128, 255, 256, long min/max, mảng trống, byte đầu `80`/`FF`, little-/big-endian và số vượt chiều rộng trường.

### Tài liệu tham khảo

- [BigInteger — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [Character.digit — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#digit(char,int))
- [ByteBuffer và ByteOrder — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)

**Ghi nhớ:** `BigInteger` có thể khởi tạo từ số lớn thập phân, văn bản ở cơ số 2–36, `long` hoặc `byte[]`. Với mảng byte, phải phân biệt **signed two's complement** với **unsigned sign-magnitude**, giữ đúng **big-endian** và xác định byte dấu. Đây là yếu tố quyết định chương trình hiểu đúng giá trị, không chỉ là khác biệt cú pháp constructor.

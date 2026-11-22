# Chuyển `char` với `byte` hoặc `short` trong Java

## 1. Vì sao chuyển đổi giữa các kiểu 8 và 16 bit lại dễ nhầm?

Trong Java, `char`, `byte` và `short` đều là **kiểu số nguyên nguyên thủy** (*integral primitive types*), nhưng chúng không biểu diễn cùng miền giá trị.

| Kiểu | Kích thước | Có dấu? | Miền số nguyên | Vai trò chính |
|---|---:|---|---|---|
| `byte` | 8 bit | Có | `-128` đến `127` | Dữ liệu byte, số nguyên 8 bit |
| `short` | 16 bit | Có | `-32768` đến `32767` | Số nguyên có dấu 16 bit |
| `char` | 16 bit | **Không** | `0` đến `65535` | **Một đơn vị mã UTF-16** |

Điểm quan trọng nhất là **`char` và `short` đều rộng 16 bit nhưng khác cách diễn giải bit cao nhất**. Với `short`, bit cao nhất tham gia biểu diễn dấu; với `char`, toàn bộ 16 bit tạo thành một giá trị từ 0 đến 65535. Còn `byte` chỉ có 8 bit và cũng là kiểu có dấu.

Do đó, các chuyển đổi giữa `char` với `byte` hoặc `short` là **narrowing primitive conversion** (chuyển đổi thu hẹp) về mặt phân loại quy tắc Java, kể cả `short` và `char` cùng 16 bit. Không có chuyển đổi mở rộng (*widening primitive conversion*) trực tiếp giữa các cặp kiểu này.

Lưu ý: “thu hẹp” trong đặc tả không chỉ nói số bit giảm. Nó còn có thể nói **miền giá trị đích không chứa tất cả giá trị của miền nguồn**. Ví dụ, `char` nhận `40000` nhưng `short` không nhận được số nguyên dương `40000`, dù cả hai cùng 16 bit.

## 2. Chuyển đổi ngầm định và chuyển đổi tường minh

Với **biến thông thường**, Java không cho gán trực tiếp từ `byte` hoặc `short` sang `char`, hay từ `char` sang `byte`/`short`:

~~~java
byte b = 65;
short s = 65;
char c = 'A';

// Không biên dịch:
// char fromByte = b;
// char fromShort = s;
// byte fromChar = c;
// short otherFromChar = c;
~~~

Đây là **đoạn minh họa** cố ý chứa các dòng lỗi được comment. Phép gán giữa các kiểu trên cần **ép kiểu tường minh** (*explicit cast*):

~~~java
char fromByte = (char) b;
char fromShort = (char) s;
byte fromChar = (byte) c;
short otherFromChar = (short) c;
~~~

Hai đoạn cùng ngữ cảnh biến; chúng không phải chương trình độc lập.

Ép kiểu chỉ nói “hãy thực hiện phép chuyển đổi theo quy tắc của Java”. Nó **không bảo đảm giá trị số học được giữ nguyên**, không kiểm tra dữ liệu có ý nghĩa là ký tự hợp lệ, và không phải thao tác giải mã văn bản.

### Ngoại lệ quan trọng: biểu thức hằng

Java cho phép **thu hẹp biểu thức hằng tại phép gán** trong một số trường hợp: biểu thức hằng có kiểu `byte`, `short`, `char` hoặc `int` và giá trị nằm trong miền kiểu đích có thể được gán không cần cast:

~~~java
char letter = 65;   // hằng int 65 vừa char
byte small = 65;    // hằng int 65 vừa byte
short number = 'A'; // hằng char 65 vừa short
~~~

Ngược lại:

~~~java
int variable = 65;
// char invalid = variable; // không biên dịch: biến int không được thu hẹp ngầm
~~~

Điều này giải thích vì sao `char c = 65;` hợp lệ nhưng `int n = 65; char c = n;` không hợp lệ. Không nên kết luận từ cú pháp hằng số rằng Java hỗ trợ chuyển đổi ngầm giữa các biến `byte`, `short` và `char`.

## 3. Từ `byte` sang `char`: số âm biến thành giá trị lớn

Một `byte` có dấu nhận giá trị âm từ `-128` đến `-1`. Khi ép sang `char`, Java thực hiện chuyển đổi theo quy tắc **mở rộng từ `byte` lên `int` rồi thu hẹp xuống `char`**, tương đương về kết quả với việc giữ 16 bit thấp sau khi mở rộng có dấu.

Ví dụ:

~~~java
byte b = -1;
char c = (char) b;
// (int) c == 65535; mã hex của c là FFFF
~~~

Vì `b` bằng `-1`, khi được mở rộng có dấu sang `int`, mẫu bit hai mươi bốn bit cao cũng là 1. Thu hẹp xuống 16 bit tạo `0xFFFF`. `char` diễn giải `0xFFFF` thành **65535**, không phải `-1`.

| `byte` nguồn | Dạng hex của 8 bit | Giá trị `(int) (char) b` | Hex `char` |
|---:|---|---:|---|
| `0` | `00` | `0` | `0000` |
| `65` | `41` | `65` | `0041` |
| `127` | `7F` | `127` | `007F` |
| `-1` | `FF` | `65535` | `FFFF` |
| `-128` | `80` | `65408` | `FF80` |

**Cảnh báo:** Chuyển `byte` âm trực tiếp thành `char` sẽ **không** cho bạn cách hiểu byte ấy là số không dấu từ 0 đến 255. Nếu đang xử lý dữ liệu nhị phân mà muốn lấy giá trị **unsigned byte**, hãy dùng:

~~~java
byte b = (byte) 0xFF;
int unsigned = Byte.toUnsignedInt(b); // 255
int masked = b & 0xFF;               // 255
char unit = (char) unsigned;         // U+00FF nếu thực sự muốn code unit đó
~~~

Đây là đoạn minh họa. `Byte.toUnsignedInt(b)` và `b & 0xFF` cho giá trị `int` từ 0 đến 255. Việc tiếp tục cast sang `char` chỉ hợp lý khi bạn **thực sự đang ánh xạ giá trị số ấy vào một đơn vị mã UTF-16**, không phải đang giải mã UTF-8 hay xác định ký tự của một charset bất kỳ.

## 4. Từ `short` sang `char`: cùng bit, khác ý nghĩa dấu

`short` và `char` cùng 16 bit. Khi chuyển `short` sang `char`, Java giữ 16 bit thấp, nhưng `char` luôn diễn giải chúng là giá trị **không dấu**.

Ví dụ:

~~~java
short s = -1;
char c = (char) s;
// (int) c == 65535 (0xFFFF)
~~~

Một số giá trị minh họa:

| `short` nguồn | Hex 16 bit | Giá trị `char` sau cast |
|---:|---|---:|
| `0` | `0000` | `0` |
| `65` | `0041` | `65` |
| `32767` | `7FFF` | `32767` |
| `-32768` | `8000` | `32768` |
| `-1` | `FFFF` | `65535` |

Một `short` âm không trở thành ký tự “số âm”. Nó trở thành code unit có cùng mẫu 16 bit nhưng giá trị số không dấu. Java cung cấp `Short.toUnsignedInt(shortValue)` để diễn giải mẫu 16 bit của một `short` thành giá trị `int` từ 0 đến 65535.

Ví dụ `Short.toUnsignedInt((short) -1)` bằng 65535, trùng với `(int) (char) ((short) -1)` về **giá trị số**. Tuy nhiên, khi mục tiêu là xử lý số nhị phân unsigned 16 bit, `int` thường diễn đạt ý nghĩa rõ hơn `char`; nên giữ `char` cho các API xử lý code unit UTF-16.

## 5. Từ `char` sang `byte`: mất 8 bit cao và có thể đổi dấu

Khi cast `char` xuống `byte`, Java giữ **8 bit thấp nhất**. Kết quả được diễn giải theo số nguyên **có dấu 8 bit**:

~~~java
char c1 = '\u0041'; // 'A' = 65
char c2 = '\u00FF'; // 255
char c3 = '\u0100'; // 256

byte b1 = (byte) c1; // 65
byte b2 = (byte) c2; // -1 (0xFF)
byte b3 = (byte) c3; // 0  (0x0100 -> 0x00)
~~~

Bảng ví dụ:

| `char` nguồn | Hex 16 bit | `(byte) c` | Giải thích |
|---:|---|---:|---|
| `65` | `0041` | `65` | Trong miền `byte` có dấu |
| `127` | `007F` | `127` | Giá trị dương lớn nhất của `byte` |
| `128` | `0080` | `-128` | Bit dấu của byte đích bằng 1 |
| `255` | `00FF` | `-1` | Giữ `FF`, diễn giải có dấu |
| `256` | `0100` | `0` | 8 bit cao bị loại |
| `65535` | `FFFF` | `-1` | 8 bit thấp đều là 1 |

Đây là **chuyển đổi dữ liệu số**. Nếu `char` biểu diễn ký tự Unicode, cast sang `byte` **không có nghĩa là chuyển ký tự thành UTF-8**. UTF-8 sử dụng thuật toán mã hóa và có thể cần nhiều byte cho một code point. Bài học về mã hóa ở phần sau cho ví dụ cụ thể.

## 6. Từ `char` sang `short`: giá trị trên 32767 trở thành âm

Từ `char` (0..65535) sang `short` (-32768..32767), Java giữ 16 bit và diễn giải theo kiểu số nguyên có dấu:

~~~java
char a = (char) 32767;
char b = (char) 32768;
char c = (char) 65535;

short s1 = (short) a; // 32767
short s2 = (short) b; // -32768
short s3 = (short) c; // -1
~~~

Không có bit nào bị bỏ khi chuyển `char` sang `short`, vì độ rộng đều là 16 bit. Tuy nhiên, **giá trị toán học có thể đổi dấu** do cách diễn giải bit đầu cao nhất. Có thể hiểu công thức tương đương:

- Với `c <= 32767`: `(short) c` giữ giá trị số.
- Với `c >= 32768`: `(short) c` bằng `(int) c - 65536`.

Tại sao lại cần cast dù không giảm số bit? Vì giá trị như `65535` nằm trong miền `char` nhưng ngoài miền `short`. Java yêu cầu thể hiện rõ thao tác đổi cách hiểu dấu.

## 7. Bốn phép chuyển trong một chương trình Java 17+ hoàn chỉnh

Tạo tệp `CharByteShortDemo.java`:

~~~java
public class CharByteShortDemo {
    public static void main(String[] args) {
        byte b = 65;
        short s = 65;
        char a = 'A';

        System.out.println("byteToChar=" + (int) (char) b);
        System.out.println("shortToChar=" + (int) (char) s);
        System.out.println("charToByte=" + (byte) a);
        System.out.println("charToShort=" + (short) a);

        byte negativeByte = -1;
        short negativeShort = -1;
        System.out.printf("negativeByteToChar=U+%04X%n",
                (int) (char) negativeByte);
        System.out.printf("negativeShortToChar=U+%04X%n",
                (int) (char) negativeShort);

        char ff = (char) 0x00FF;
        char highBit = (char) 0x8000;
        System.out.println("FFToByte=" + (byte) ff);
        System.out.println("FFToShort=" + (short) ff);
        System.out.println("8000ToShort=" + (short) highBit);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac CharByteShortDemo.java
java CharByteShortDemo
~~~

Đầu ra chính xác:

~~~text
byteToChar=65
shortToChar=65
charToByte=65
charToShort=65
negativeByteToChar=U+FFFF
negativeShortToChar=U+FFFF
FFToByte=-1
FFToShort=255
8000ToShort=-32768
~~~

Từ `65`, bốn hướng chuyển đổi đều giữ giá trị vì nó nằm trong miền chung của ba kiểu. Nhưng `-1` chuyển sang `char` thành 65535; `char` 255 khi thu về `byte` thành -1; `char` 32768 chuyển sang `short` thành -32768. Những kết quả này không phụ thuộc vào cách màn hình hiển thị ký tự, mà đến từ quy tắc số nguyên.

## 8. Khi byte từ mạng hoặc file được dùng như số không dấu

Nhiều định dạng nhị phân định nghĩa một trường 8 bit hoặc 16 bit **không dấu**. Vì Java không có primitive `unsigned byte` hay `unsigned short` riêng, người lập trình thường lưu raw bit bằng `byte`/`short` và diễn giải bằng kiểu `int`:

- `Byte.toUnsignedInt(byteValue)` trả giá trị 0..255.
- `Short.toUnsignedInt(shortValue)` trả giá trị 0..65535.
- `byteValue & 0xFF` tương đương về giá trị với cách đọc unsigned byte.
- `shortValue & 0xFFFF` tương đương về giá trị với cách đọc unsigned short.

Tạo tệp `UnsignedNumbersDemo.java`:

~~~java
public class UnsignedNumbersDemo {
    public static void main(String[] args) {
        byte rawByte = (byte) 0xFF;
        short rawShort = (short) 0xFFFF;

        int unsignedByte = Byte.toUnsignedInt(rawByte);
        int unsignedShort = Short.toUnsignedInt(rawShort);

        char directByteCast = (char) rawByte;
        char unsignedByteAsChar = (char) unsignedByte;

        System.out.println("signedByte=" + rawByte);
        System.out.println("unsignedByte=" + unsignedByte);
        System.out.println("maskedByte=" + (rawByte & 0xFF));
        System.out.printf("directByteCast=U+%04X%n",
                (int) directByteCast);
        System.out.printf("unsignedByteAsChar=U+%04X%n",
                (int) unsignedByteAsChar);

        System.out.println("signedShort=" + rawShort);
        System.out.println("unsignedShort=" + unsignedShort);
        System.out.println("maskedShort=" + (rawShort & 0xFFFF));
        System.out.printf("directShortCast=U+%04X%n",
                (int) (char) rawShort);
    }
}
~~~

~~~bash
javac UnsignedNumbersDemo.java
java UnsignedNumbersDemo
~~~

Đầu ra:

~~~text
signedByte=-1
unsignedByte=255
maskedByte=255
directByteCast=U+FFFF
unsignedByteAsChar=U+00FF
signedShort=-1
unsignedShort=65535
maskedShort=65535
directShortCast=U+FFFF
~~~

**Khác biệt quan trọng:** cast trực tiếp `(char) rawByte` khi raw byte là `-1` tạo `U+FFFF`; chuyển qua `Byte.toUnsignedInt` trước rồi cast cho `U+00FF`. Hai kết quả khác nhau dù cùng bắt đầu từ mẫu bit `FF` của byte.

Đối với raw `short`, cast sang `char` và diễn giải unsigned 16 bit có cùng con số 0..65535, nhưng **ý nghĩa dữ liệu** vẫn khác: một số đo/giao thức unsigned 16 bit không tự biến thành một ký tự Unicode.

## 9. Chuyển đổi số không phải là mã hóa hay giải mã văn bản

`char` là **một đơn vị mã UTF-16**, còn `byte` là **một đơn vị dữ liệu 8 bit**. Cast giữa chúng chỉ thực hiện các quy tắc chuyển đổi primitive ở những phần trước. Cast **không biết charset** và không thực hiện thuật toán UTF-8/UTF-16.

Ví dụ chữ `é` là code point `U+00E9`. Khi mã hóa bằng UTF-8, nó dùng **hai byte `C3 A9`**, không phải chỉ một byte `E9`. Mỗi byte UTF-8 đó khi đọc vào primitive `byte` có giá trị có dấu (theo thứ tự) `-61` và `-87`.

Nếu cast từng byte sang `char`, Java chỉ mở rộng/thu hẹp bit: `(char) (byte) 0xC3` cho `U+FFC3`, và `(char) (byte) 0xA9` cho `U+FFA9`. Kết quả **không phải** văn bản `é`.

Muốn giải mã đúng, dùng API charset:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8DecodeDemo {
    public static void main(String[] args) {
        byte[] encoded = {(byte) 0xC3, (byte) 0xA9};
        String decoded = new String(encoded, StandardCharsets.UTF_8);

        System.out.println("decoded=" + decoded);
        System.out.println("units=" + decoded.length());
        System.out.printf("unit=U+%04X%n", (int) decoded.charAt(0));
        System.out.printf("wrongFirst=U+%04X%n",
                (int) (char) encoded[0]);
        System.out.printf("wrongSecond=U+%04X%n",
                (int) (char) encoded[1]);
    }
}
~~~

~~~bash
javac Utf8DecodeDemo.java
java Utf8DecodeDemo
~~~

Đầu ra:

~~~text
decoded=é
units=1
unit=U+00E9
wrongFirst=U+FFC3
wrongSecond=U+FFA9
~~~

Dữ liệu `byte[]` đã được giải mã theo `StandardCharsets.UTF_8` mới trở thành `String` đúng. Khi cần biến chuỗi thành byte theo charset, dùng `text.getBytes(StandardCharsets.UTF_8)`. Đây là quy tắc quan trọng cho file, JSON, HTTP và dữ liệu từ mạng.

Lưu ý rằng `char` chỉ biểu diễn **một code unit UTF-16**, nên ngay cả khi đã giải mã đúng, một Unicode code point ngoài BMP (chẳng hạn emoji) có thể chiếm **hai** giá trị `char` trong `String`. Không coi một byte hay một char bất kỳ là “một ký tự người dùng nhìn thấy”.

## 10. Phép toán với `char`, `byte` và `short` được nâng kiểu

Trong đa số biểu thức số học, `byte`, `short` và `char` được **nâng lên `int`**. Vì thế:

~~~java
byte b = 1;
short s = 2;
char c = 'A';

int sum = b + s + c;     // int: 1 + 2 + 65 = 68
int nextCode = c + 1;    // int: 66

// Không biên dịch:
// char next = c + 1;
// byte smallSum = b + 1;
~~~

Đây là đoạn minh họa (các câu không hợp lệ đã comment). Mặc dù `char` là kiểu số nguyên không dấu, kết quả `c + 1` có kiểu `int`. Nếu ép về `char`, có thể gây cuốn vòng về 16 bit thấp:

~~~java
char max = Character.MAX_VALUE;     // 65535
char wrapped = (char) (max + 1);    // 0
~~~

Cast rõ ràng không kiểm tra tràn. Với số học thông thường, giữ kết quả ở `int`, kiểm tra miền trước khi cast về kiểu hẹp; các phép toán `Math.toIntExact` chỉ kiểm tra chuyển `long` sang `int`, **không** tự kiểm tra chuyển `int` sang `char`/`byte`/`short`.

### Làm sao kiểm tra miền thay vì cắt bit?

Giả sử API nhận `int codeUnit` và yêu cầu trả về `char` giữ nguyên giá trị:

~~~java
if (codeUnit < Character.MIN_VALUE || codeUnit > Character.MAX_VALUE) {
    throw new IllegalArgumentException("out of char range");
}
char unit = (char) codeUnit;
~~~

Đoạn minh họa này bảo đảm giá trị số nằm trong 0..65535 trước khi cast. Nhưng “nằm trong miền `char`” **chưa chắc có nghĩa là Unicode scalar value hoàn chỉnh**: vùng `U+D800`–`U+DFFF` là các code unit surrogate, vốn cần phối hợp trong cặp nếu biểu diễn code point ngoài BMP.

Đối với `byte` và `short` có dấu, kiểm tra `Byte.MIN_VALUE`/`Byte.MAX_VALUE` hoặc `Short.MIN_VALUE`/`Short.MAX_VALUE` tương tự. Nếu muốn diễn giải một unsigned byte, hãy kiểm tra 0..255 hoặc dùng `Byte.toUnsignedInt` với raw byte.

## 11. Ví dụ mất dữ liệu và tính chất round-trip

Một *round-trip* là chuyển từ kiểu A sang kiểu B rồi quay trở lại A. Không phải round-trip nào cũng giữ nguyên giá trị.

Tạo tệp `NarrowingRoundTripDemo.java`:

~~~java
public class NarrowingRoundTripDemo {
    public static void main(String[] args) {
        char original = '\u0100'; // 256
        byte narrowed = (byte) original; // 0
        char restored = (char) narrowed; // 0

        char small = 'A';
        byte smallByte = (byte) small;
        char smallRestored = (char) smallByte;

        short negativeShort = -1;
        char unsignedUnit = (char) negativeShort;
        short sameBits = (short) unsignedUnit;

        System.out.println("original=" + (int) original);
        System.out.println("narrowed=" + narrowed);
        System.out.println("restored=" + (int) restored);
        System.out.println("smallRoundTrip=" + (small == smallRestored));
        System.out.println("shortBitsRoundTrip=" + (negativeShort == sameBits));
        System.out.println("charUnsignedValue=" + (int) unsignedUnit);
    }
}
~~~

~~~bash
javac NarrowingRoundTripDemo.java
java NarrowingRoundTripDemo
~~~

Đầu ra:

~~~text
original=256
narrowed=0
restored=0
smallRoundTrip=true
shortBitsRoundTrip=true
charUnsignedValue=65535
~~~

Ở ví dụ thứ nhất, `char` có giá trị 256 mất bit cao khi chuyển qua `byte` rồi không thể khôi phục thông tin gốc. Ở ví dụ thứ hai, `'A'` bằng 65 nằm trong khoảng an toàn của `byte` nên giữ nguyên. Ở ví dụ thứ ba, đi từ `short -1` sang `char 65535` rồi quay về `short -1` giữ nguyên **mẫu bit**, nhưng giá trị số trung gian khác nhau.

Cần phân biệt rõ:

- **Bảo toàn mẫu bit:** giữ các bit trong một độ rộng nhất định.
- **Bảo toàn giá trị số:** kết quả số học giống ban đầu.
- **Bảo toàn văn bản:** các code point/ký tự vẫn mang cùng ý nghĩa sau khi mã hóa/giải mã.

Một chuyển đổi có thể giữ mẫu bit nhưng đổi giá trị số, hoặc làm mất dữ liệu mà không có exception.

## 12. Những lỗi phổ biến và cách tránh

| Nhầm lẫn | Thực tế |
|---|---|
| “`char` và `short` đều 16 bit nên gán trực tiếp được.” | Không: miền số khác nhau; cần cast khi làm việc với biến. |
| “`byte` sang `char` là widening vì `char` có 16 bit.” | Không có widening trực tiếp `byte → char`; cast là bắt buộc. |
| “`(char) (byte) -1` bằng 255.” | Sai: nó bằng 65535 (`U+FFFF`); muốn unsigned byte 255, dùng `Byte.toUnsignedInt` trước. |
| “`(short) (char) 65535` bằng 65535.” | Sai: kết quả `short` là -1. |
| “`(byte) '\u0100'` báo lỗi overflow.” | Sai: cast primitive cho 0 sau khi bỏ 8 bit cao. |
| “Ép byte sang char sẽ đọc đúng UTF-8.” | Sai: cần decoder, ví dụ `new String(bytes, StandardCharsets.UTF_8)`. |
| “Kết quả `char + 1` vẫn là `char`.” | Sai: biểu thức được nâng lên `int`. |
| “`Math.toIntExact` kiểm tra được việc cast `int` sang `byte`.” | Sai: API này chỉ chuyển `long → int`. |
| “Một `char` bằng một ký tự Unicode hiển thị.” | Sai: `char` là một code unit UTF-16; một code point có thể cần hai code unit. |

## 13. Checklist khi cần chuyển `char` với `byte`/`short`

1. **Xác định dữ liệu:** đang tính số, đọc trường nhị phân, xử lý đơn vị mã UTF-16 hay giải mã văn bản?
2. **Xác định cách hiểu dấu:** `byte`/`short` có dấu, `char` không dấu. Dữ liệu đầu vào có thể âm không?
3. **Kiểm tra miền hợp lệ:** đầu vào có chắc nằm trong khoảng biểu diễn của kiểu đích khi cần giữ giá trị không?
4. **Kiểm tra mục tiêu:** muốn giữ **giá trị số**, giữ **mẫu bit**, hay khôi phục **văn bản**? Ba mục tiêu đòi cách làm khác nhau.
5. **Chọn API đúng:** `Byte.toUnsignedInt`/`Short.toUnsignedInt` để đọc unsigned; charset decoder để đọc byte thành chuỗi; cast chỉ khi thực sự muốn phép chuyển đổi số Java.
6. **Test các biên:** `-128`, `-1`, `0`, `127`, `128`, `255`, `256`, `32767`, `32768`, `65535` và dữ liệu Unicode nhiều byte/cặp surrogate khi có xử lý văn bản.

## 14. Tự kiểm tra

1. Vì sao không thể gán trực tiếp biến `short` vào `char` dù chúng đều 16 bit?
2. Kết quả `(int) (char) ((byte) -1)` là 255 hay 65535? Giải thích.
3. `(byte) ((char) 256)` bằng bao nhiêu? Thông tin nào bị mất?
4. `(short) ((char) 0x8000)` bằng bao nhiêu, và tại sao?
5. Nếu giao thức truyền byte `0xFF` đại diện cho số unsigned 255, nên dùng `(char) rawByte` hay `Byte.toUnsignedInt(rawByte)` để tính toán?
6. Vì sao một chuỗi UTF-8 gồm hai byte `C3 A9` không thể khôi phục chữ `é` bằng hai phép cast `(char)`?
7. `char c = 65;` có biên dịch không? Còn `int x = 65; char c = x;` thì sao?
8. `char max = Character.MAX_VALUE; char next = (char) (max + 1);` cho giá trị số bao nhiêu?

**Gợi ý đáp án:** (1) Khác miền và cách diễn giải dấu nên không có widening giữa `short` với `char`. (2) 65535 do sign extension của `byte -1` trước khi thu hẹp xuống 16 bit. (3) 0, mất tám bit cao. (4) -32768, giữ mẫu bit `8000` nhưng `short` có dấu. (5) `Byte.toUnsignedInt`. (6) UTF-8 là mã hóa nhiều byte, phải giải mã bằng charset. (7) Câu đầu hợp lệ do hằng số 65 nằm trong miền `char`; câu sau không biên dịch nếu không cast. (8) 0 vì cast giữ 16 bit thấp.

**Ghi nhớ:** Giữa `char` với `byte` hoặc `short`, Java yêu cầu **ép kiểu tường minh** đối với biến vì miền giá trị và cách diễn giải dấu khác nhau. Cast có thể giữ bit, đổi dấu hoặc bỏ bit; khi xử lý binary unsigned hãy dùng các API đọc số không dấu, còn khi xử lý văn bản hãy dùng charset decoder phù hợp.
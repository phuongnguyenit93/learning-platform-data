# Phân biệt mô hình UTF-16 của API với biểu diễn nội bộ của Java String

Khi làm việc với `String`, lập trình viên Java thường nghe hai mệnh đề có vẻ trái ngược nhau:

- API của `String` dùng **chỉ số đơn vị mã UTF-16** (*UTF-16 code units*). Vì thế `length()`, `charAt()`, `substring()` và nhiều vị trí trả về đều tuân theo cách đánh chỉ số này.
- Trên những bản **OpenJDK/HotSpot hiện đại**, `String` thường dùng cơ chế **Compact Strings**: một mảng `byte[]` bên trong và thông tin cho biết dữ liệu đang được lưu ở dạng Latin-1 hay UTF-16. Một chuỗi ASCII có thể chỉ cần một byte cho mỗi đơn vị mã trong vùng dữ liệu của nó.

Hai mệnh đề **không mâu thuẫn**: **mô hình mà API cam kết** khác với **cách JVM được quyền tối ưu hóa biểu diễn trong bộ nhớ**. Chương trình cần dựa vào hợp đồng API; chi tiết lưu trữ nội bộ chỉ nên dùng để hiểu hiệu năng/bộ nhớ và luôn gắn với phiên bản, nhà triển khai JVM.

## 1. Ba khái niệm phải phân biệt

| Khái niệm | Đơn vị | Vai trò |
| --- | --- | --- |
| **UTF-16 code unit** | Một giá trị 16 bit; Java biểu diễn bằng `char` | Đơn vị chỉ số của `String.length()`, `charAt()`, `substring()` |
| **Unicode code point** | Một giá trị Unicode như U+0041 hoặc U+1F600 | Đơn vị thường dùng khi xử lý ký tự Unicode, tra cứu `codePointAt()`, duyệt `codePoints()` |
| **Byte lưu trữ hoặc truyền đi** | 8 bit | Có thể là byte nội bộ do JVM chọn, hoặc byte bên ngoài tạo bởi `getBytes(charset)`; hai trường hợp là khác nhau |

**Không được đồng nhất ba đơn vị này.** Trong UTF-16:

- Code point thuộc **BMP** (Basic Multilingual Plane), chẳng hạn `A` (U+0041) hoặc `Đ` (U+0110), thường chiếm **một** code unit UTF-16.
- Code point **ngoài BMP**, chẳng hạn emoji `😀` (U+1F600), cần **hai** code unit UTF-16 liên tiếp: **high surrogate** `U+D83D` và **low surrogate** `U+DE00`.
- Một **ký tự người dùng nhìn thấy** (*grapheme cluster*) còn có thể gồm **nhiều code point**; ví dụ chữ `e` đi với dấu sắc kết hợp `U+0301` thường trông giống `é`.

`String` là chuỗi các `char` UTF-16 theo mô hình API. Nó thậm chí có thể chứa một surrogate đứng một mình, mặc dù surrogate đơn lẻ **không phải Unicode scalar value hợp lệ** để chuyển trực tiếp thành UTF-8 chuẩn.

## 2. Các API dựa trên chỉ số UTF-16, không dựa trên số byte

Xét giá trị Java:

~~~java
String text = "A\uD83D\uDE00B"; // A😀B, viết bằng Unicode escapes
~~~

Mảng code unit được quan sát qua API:

~~~text
Chỉ số UTF-16:   0       1          2       3
charAt(index): U+0041  U+D83D     U+DE00   U+0042
Code point:    U+0041  <--- U+1F600 --->   U+0042
Hình hiển thị:   A            😀               B
~~~

Vì vậy:

- `text.length()` là **4**: tổng số code unit UTF-16.
- `text.codePointCount(0, text.length())` là **3**: `A`, `😀`, `B`.
- `text.charAt(1)` là **high surrogate** `\uD83D`, **không phải** toàn bộ emoji.
- `text.codePointAt(1)` kết hợp cặp surrogate bắt đầu tại vị trí 1 và trả về `0x1F600`.
- `text.indexOf("B")` là **3**, vì kết quả dùng chỉ số UTF-16.
- `text.substring(1, 3)` lấy cả cặp surrogate nên tạo đúng `😀`.
- `text.substring(1, 2)` chỉ lấy nửa đầu cặp surrogate, tạo một `String` dài 1 code unit nhưng không chứa code point emoji hoàn chỉnh.

### Chương trình Java 17 chạy độc lập

~~~java
// Utf16ApiDemo.java
public class Utf16ApiDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("length = " + text.length());
        System.out.println("codePointCount = "
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("charAt(%d) = U+%04X%n",
                    i, (int) text.charAt(i));
        }

        System.out.printf("codePointAt(1) = U+%04X%n",
                text.codePointAt(1));
        System.out.println("indexOf(B) = " + text.indexOf("B"));
        System.out.println("offsetByCodePoints(1, 1) = "
                + text.offsetByCodePoints(1, 1));

        String emoji = text.substring(1, 3);
        System.out.println("emoji slice equals original = "
                + emoji.equals("\uD83D\uDE00"));

        String half = text.substring(1, 2);
        System.out.println("half.length = " + half.length());
        System.out.println("half is high surrogate = "
                + Character.isHighSurrogate(half.charAt(0)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 Utf16ApiDemo.java
java Utf16ApiDemo
~~~

Stdout chính xác:

~~~text
length = 4
codePointCount = 3
charAt(0) = U+0041
charAt(1) = U+D83D
charAt(2) = U+DE00
charAt(3) = U+0042
codePointAt(1) = U+1F600
indexOf(B) = 3
offsetByCodePoints(1, 1) = 3
emoji slice equals original = true
half.length = 1
half is high surrogate = true
~~~

Ở đây `offsetByCodePoints(1, 1)` tìm chỉ số UTF-16 sau **một code point** bắt đầu tại chỉ số 1: bỏ qua cả hai code unit của emoji và trả về 3. Phương thức này hữu ích khi cần xử lý Unicode theo code point mà vẫn tương tác với các API nhận chỉ số UTF-16.

## 3. `char`, `chars()`, `codePoints()`: tên gần nhau nhưng khác ý nghĩa

`char` là kiểu nguyên thủy **16 bit không dấu** trong Java. `String.charAt(i)` trả về **một** `char`; vì vậy nó có thể trả về một surrogate, thay vì một ký tự hiển thị hoàn chỉnh.

Hai phương thức stream quan trọng:

~~~java
String text = "A\uD83D\uDE00B";

text.chars();      // IntStream của các đơn vị UTF-16: 0x0041, 0xD83D, 0xDE00, 0x0042
text.codePoints(); // IntStream của code point:       0x0041, 0x1F600,       0x0042
~~~

Đây là đoạn minh họa gọi API, không phải một chương trình độc lập. `chars()` nâng từng `char` thành một giá trị `int`; `codePoints()` gộp hai surrogate hợp lệ thành một code point. Nếu một surrogate không có cặp hợp lệ, `codePoints()` vẫn có thể phát ra giá trị surrogate chưa ghép đó theo quy tắc API; đừng hiểu rằng thao tác này tự “sửa” chuỗi lỗi thành Unicode hợp lệ.

Khi cần chuyển một code point sang các code unit UTF-16 của Java, dùng `Character.toChars(codePoint)`; khi cần tính số `char` mà code point chiếm, dùng `Character.charCount(codePoint)` (1 hoặc 2 cho code point hợp lệ). Các phép tính này phục vụ **mô hình UTF-16 của API**, không mô tả số byte bên trong đối tượng `String`.

## 4. Biểu diễn nội bộ: lịch sử và Compact Strings

Ở nhiều phiên bản OpenJDK trước Java 9, nội dung `String` được giữ bằng mảng `char[]`. Từ Java 9, **JEP 254 — Compact Strings** chuyển sang mảng `byte[]` kèm thông tin mã hóa nội bộ (`coder`). Nếu mọi code unit nằm trong U+0000–U+00FF, biểu diễn **LATIN1** có thể dùng một byte/code unit; nếu có đơn vị ngoài vùng đó, biểu diễn **UTF16** cần hai byte/code unit trong mảng dữ liệu.

Ví dụ, `"café"` gồm 4 code unit đều thuộc Latin-1, còn `"Đ"` chứa U+0110 ngoài Latin-1. Trên HotSpot có bật Compact Strings, phần dữ liệu của hai chuỗi **có thể** dùng hai dạng lưu trữ khác nhau; `length()`, `charAt()` và các phép cắt theo chỉ số vẫn có ngữ nghĩa UTF-16.

| Mức quan sát | Điều được cam kết |
| --- | --- |
| **Public API** | `length()` đếm UTF-16 code units; `charAt()`, `substring()`, `codePointAt()` tuân theo API |
| **Chi tiết OpenJDK** | `byte[]`, `coder`, LATIN1/UTF16, tối ưu JIT và cách chia sẻ bộ nhớ có thể thay đổi |
| **Số byte trao đổi** | Được xác định bởi charset chỉ định cho `getBytes(charset)`, không bởi `coder` |

Không dùng reflection vào các trường `private` của `String` để giải quyết bài toán Unicode, và đừng suy ra kích thước heap từ `length()`. Bài **Compact Strings và các dạng LATIN1, UTF16** đi sâu vào quy tắc chọn coder, layout, tùy chọn VM và phép thử tương ứng.

## 5. Vì sao đổi biểu diễn nội bộ không làm đổi `String.length()`?

Một ví dụ then chốt:

~~~java
String latin = "café";  // 4 code unit
String wide = "Đ";      // 1 code unit
~~~

Trên OpenJDK/HotSpot có Compact Strings, `latin` thường có dữ liệu nội bộ dạng một byte/code unit, còn `wide` có thể cần hai byte/code unit. **Nhưng**:

~~~java
System.out.println(latin.length()); // 4
System.out.println(wide.length());  // 1
~~~

Kết quả `4` và `1` luôn dựa trên **số code unit UTF-16 theo API**. Tương tự, dù có tối ưu bộ nhớ, `charAt()` vẫn trả về một đơn vị UTF-16: runtime tự giải mã giá trị từ biểu diễn nội bộ trước khi đưa ra API.

Đừng hình dung rằng chương trình Java nhìn được trực tiếp từng byte đã nén thông qua `charAt()`. Nó nhìn **giá trị logic**; cách đọc dữ liệu vật lý là công việc của thư viện và JVM.

## 6. Byte tạo từ `getBytes(charset)` là một chuyện khác

`String.getBytes(StandardCharsets.UTF_8)` sinh dữ liệu để **xuất ra ngoài** theo UTF-8. `String.getBytes(StandardCharsets.UTF_16BE)` sinh byte theo UTF-16 big-endian. Đây là **hai phép encode**, không phải cửa sổ nhìn vào `byte[]` nội bộ.

Với `"A😀B"`:

| Cách nhìn | Kết quả |
| --- | --- |
| `String.length()` | 4 đơn vị UTF-16 |
| `codePointCount(...)` | 3 code point |
| `getBytes(UTF_8)` | 6 byte: `41 F0 9F 98 80 42` |
| `getBytes(UTF_16BE)` | 8 byte: `00 41 D8 3D DE 00 00 42` |
| `getBytes(UTF_16)` của Java | 10 byte: `FE FF` (BOM) + 8 byte UTF-16BE |
| Bộ nhớ `String` bên trong HotSpot | Không xác định chỉ từ các API trên; phụ thuộc cơ chế cài đặt và đối tượng |

### Chương trình Java 17 chạy độc lập

~~~java
// StringBytesDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class StringBytesDemo {
    static void show(String name, byte[] bytes) {
        System.out.println(name + " = "
                + HexFormat.of().withUpperCase().formatHex(bytes)
                + " (" + bytes.length + " bytes)");
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("UTF-16 code units = " + text.length());
        show("UTF-8", text.getBytes(StandardCharsets.UTF_8));
        show("UTF-16BE", text.getBytes(StandardCharsets.UTF_16BE));
        show("UTF-16", text.getBytes(StandardCharsets.UTF_16));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 StringBytesDemo.java
java StringBytesDemo
~~~

Stdout:

~~~text
UTF-16 code units = 4
UTF-8 = 41F09F988042 (6 bytes)
UTF-16BE = 0041D83DDE000042 (8 bytes)
UTF-16 = FEFF0041D83DDE000042 (10 bytes)
~~~

Byte `FE FF` trong ví dụ cuối là **Byte Order Mark (BOM)** do `StandardCharsets.UTF_16` của Java tạo ra theo quy tắc encoder này. `UTF_16BE` không tự thêm BOM như ví dụ. Bộ byte **được xuất ra** thay đổi theo charset; ta không từ đó suy ra HotSpot đang lưu các byte vật lý của `String` với cùng thứ tự hoặc có BOM trong bộ nhớ.

Nếu phải gửi văn bản qua mạng hay ghi file, **luôn chỉ định charset theo giao ước**, ví dụ `StandardCharsets.UTF_8`. Đừng sử dụng trường nội bộ của `String` như định dạng trao đổi dữ liệu.

## 7. Code point cũng chưa chắc là một ký tự nhìn thấy

Ngoài khác biệt code unit/code point, Unicode còn có **grapheme cluster**: một cụm mà người đọc thường coi là một ký tự. Ví dụ:

- `"\u00E9"`: `é` ở dạng **một code point** U+00E9; `length() == 1`.
- `"e\u0301"`: chữ `e` + dấu sắc kết hợp U+0301, **hai code point** và **hai code unit**; hình hiển thị có thể giống `é`.
- Emoji gồm các thành phần nối bằng **zero-width joiner (ZWJ)** hoặc modifier màu da có thể là **nhiều code point**, nhưng một biểu tượng hiển thị.

Hai `String` nhìn giống nhau chưa chắc `equals()` trả về `true`. Java không tự chuẩn hóa Unicode trong `String.equals()`. Nếu bài toán yêu cầu so sánh văn bản đã chuẩn hóa, thực hiện bước riêng theo `java.text.Normalizer`, rồi xác định thêm quy tắc ngôn ngữ/locale khi cần. Việc chuẩn hóa **không** thuộc cơ chế Compact Strings.

### Ví dụ Java 17

~~~java
// UnicodeNormalizationDemo.java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";   // é, một code point
        String decomposed = "e\u0301"; // e + dấu sắc kết hợp

        System.out.println("composed length = " + composed.length());
        System.out.println("decomposed length = " + decomposed.length());
        System.out.println("raw equals = " + composed.equals(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals = " + composed.equals(normalized));
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Kết quả:

~~~text
composed length = 1
decomposed length = 2
raw equals = false
NFC equals = true
~~~

`Normalizer.Form.NFC` đưa tổ hợp kết hợp thích hợp về dạng tiền tổ hợp chuẩn. Nó **không** giải quyết mọi vấn đề đếm ký tự hiển thị, chia cụm emoji hay xử lý ngôn ngữ tự nhiên.

## 8. Những ảnh hưởng thực tế khi lập trình

### Cắt chuỗi không làm vỡ cặp surrogate

Nếu vòng lặp đi qua `charAt(i)`, có thể bạn đang xử lý **nửa code point**. Khi cần duyệt code point, nên dùng `text.codePoints()` hoặc bộ đôi `codePointAt(i)` và `Character.charCount(cp)`:

~~~java
// Duyệt từng code point, không cắt đôi surrogate pair.
// Đoạn minh họa, đặt trong một phương thức Java có biến String text.
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    // Xử lý code point cp tại đây.
    i += Character.charCount(cp);
}
~~~

Nếu muốn xử lý **grapheme cluster**, code point vẫn chưa đủ; cần giải pháp phân đoạn Unicode phù hợp phiên bản và mục tiêu, cùng các bài kiểm thử cho dấu kết hợp/emoji. Không cắt bằng `substring(0, n)` với `n` suy ra từ “số ký tự nhìn thấy” mà chưa chuyển đổi thành chỉ số UTF-16 an toàn.

### Tính kích thước lưu trữ hoặc giới hạn đầu vào

`String.length()` **không đo byte** của dữ liệu gửi qua HTTP hoặc file. Để kiểm tra giới hạn byte với charset cụ thể:

~~~java
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
~~~

Đây là đoạn minh họa (cần import `StandardCharsets` và có biến `String text`). Với dữ liệu lớn, có thể dùng encoder/stream thay vì tạo cả mảng chỉ để đếm. Nếu hệ thống đặt giới hạn theo **code point** hoặc **grapheme**, phải triển khai đúng đơn vị mà yêu cầu quy định.

### Hiệu năng và bộ nhớ

Compact Strings có thể giảm phần dữ liệu trong bộ nhớ đối với nhiều chuỗi Latin-1. Nhưng phép tính đơn giản `length * 1` hoặc `length * 2` chỉ là **ước lượng phần backing storage** trong một cài đặt cụ thể, **không phải kích thước object thực**. Ngoài vùng chứa byte còn có object header, tham chiếu, thông tin phụ, căn chỉnh, cơ chế GC/JIT và chi phí tạm thời.

Nếu tối ưu hóa bộ nhớ trên một JVM cụ thể, hãy đo thực tế bằng **profiler/JOL** hoặc công cụ phân tích heap phù hợp; không cố dự đoán byte chính xác từ `String.length()` hay thông qua truy cập trường private. Với HotSpot hỗ trợ cờ này, `-XX:-CompactStrings` có thể dùng trong thí nghiệm để tắt Compact Strings, nhưng đây là **tùy chọn cài đặt**, không phải yêu cầu của Java SE.

Ví dụ thử trên HotSpot tương thích:

~~~bash
java Utf16ApiDemo
java -XX:-CompactStrings Utf16ApiDemo
~~~

**Output API phải giống nhau**, dù cách lưu trữ nội bộ và mức sử dụng bộ nhớ có thể khác. Không cần và không nên thay đổi cờ JVM để sửa logic xử lý Unicode của ứng dụng.

### Phân biệt với `char[]` hoặc `StringBuilder`

Gọi `text.toCharArray()` trả về một **mảng `char[]` công khai** chứa các code unit UTF-16, tức mỗi phần tử mảng là một `char` 16 bit. Điều đó **không chứng minh** `String` ban đầu đã lưu dữ liệu trong `char[]`. `StringBuilder` cũng cung cấp API dựa trên chỉ số `char`, nhưng cách nó cấp phát và lưu dữ liệu bên trong là chuyện triển khai; đừng suy ra biểu diễn của `String` từ một API có cùng kiểu trả về.

## 9. Lỗi thường gặp và cách nhận diện

1. **“Java `String` luôn lưu hai byte mỗi ký tự.”** Sai vì câu này trộn API UTF-16 với cài đặt. Java 9+ trên các HotSpot/OpenJDK thông dụng có thể lưu Latin-1 với một byte/code unit. Và một code point ngoài BMP còn cần hai code unit.
2. **“`String.length()` là số ký tự mắt nhìn thấy.”** Sai với surrogate pair, dấu kết hợp, cụm ZWJ và nhiều trường hợp Unicode khác.
3. **“`charAt(i)` luôn trả về một Unicode code point hoàn chỉnh.”** Sai: `char` chỉ có 16 bit và có thể là một high/low surrogate.
4. **“`getBytes()` cho biết byte trong heap.”** Sai: đây là thao tác **encode** ra charset được chỉ định hoặc mặc định; byte đầu ra không phải ảnh chụp cách JVM cất `String`.
5. **“UTF-16BE và `StandardCharsets.UTF_16` luôn tạo byte giống nhau.”** Sai: `UTF_16` có thể tạo BOM như ví dụ `FE FF`; phải phân biệt charset cụ thể.
6. **“Có chữ Unicode ngoài ASCII thì chắc chắn cần hai byte nội bộ cho mỗi code unit.”** Không hẳn: `é` thuộc Latin-1; `Đ` thì không. Phải xét **tập code unit của toàn chuỗi** và cài đặt đang dùng.
7. **“Cắt chuỗi theo chỉ số bất kỳ luôn an toàn.”** `substring` có thể cắt đôi surrogate pair. Nếu cần đơn vị code point hoặc grapheme, phải chuyển đổi/chia đoạn có chủ đích.
8. **“Hai chuỗi hiển thị như nhau thì `equals()` trả về true.”** Sai nếu chúng dùng các chuỗi code unit khác nhau, chẳng hạn NFC so với dạng có dấu kết hợp.
9. **“Có thể dựa vào private fields của `String` cho thuật toán.”** Những trường này không thuộc hợp đồng Java SE và có thể bị JVM thay đổi hoặc cơ chế module hạn chế.
10. **“Tắt Compact Strings sẽ đổi `length()` hoặc `charAt()`.”** Sai đối với triển khai tuân thủ Java SE: tối ưu hóa biểu diễn nội bộ phải bảo toàn hành vi API.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Với `String s = "A\uD83D\uDE00B";`, `s.length()`, `s.codePointCount(0, s.length())` và số byte UTF-8 lần lượt là bao nhiêu?

**Đáp án:** `4` code unit, `3` code point, `6` byte. Emoji U+1F600 chiếm hai code unit UTF-16 nhưng bốn byte UTF-8.

**Câu 2.** Vì sao `"café"` có thể dùng đường Latin-1 Compact Strings, còn `"Đ"` lại cần biểu diễn UTF-16 trong cài đặt HotSpot điển hình?

**Đáp án:** Tất cả code unit của `"café"` nằm ở U+0000–U+00FF, kể cả `é` U+00E9; `Đ` U+0110 nằm ngoài miền ấy. Đây là điều kiện lựa chọn **biểu diễn bộ nhớ**, không đổi semantics của API.

**Câu 3.** `text.substring(1, 2)` với `text = "A\uD83D\uDE00B"` chứa gì?

**Đáp án:** Chỉ high surrogate `U+D83D`, không phải emoji hoàn chỉnh. Muốn lấy emoji, dùng `substring(1, 3)`.

**Câu 4.** Nếu mã hóa `"A😀B"` bằng `UTF_16BE`, tại sao có 8 byte? Nếu bằng `UTF_8` tại sao có 6 byte?

**Đáp án:** Mô hình UTF-16 có 4 code unit × 2 byte = 8 byte ở dạng UTF-16BE. UTF-8 dùng 1 byte cho `A`, 4 byte cho `😀` và 1 byte cho `B` nên tổng là 6. Đây là số byte **encode để trao đổi**, không phải kích thước object trên heap.

**Câu 5.** Có thể kết luận một `String` dùng bao nhiêu byte trong JVM chỉ nhờ `length()` hoặc `getBytes(UTF_8).length` không?

**Đáp án:** Không. Hai giá trị có ý nghĩa API/charset; kích thước thực tế còn phụ thuộc cài đặt, lựa chọn Compact Strings, header và các cơ chế quản lý bộ nhớ.

## Ghi nhớ

**Mô hình UTF-16 của API là hợp đồng ổn định; biểu diễn nội bộ là chi tiết JVM có thể tối ưu.** Hãy đọc `length()` và các chỉ số `String` theo **UTF-16 code units**; dùng `codePoints()`, `codePointAt()` và `offsetByCodePoints()` khi cần code point; dùng giải pháp phân đoạn Unicode riêng khi cần **ký tự người dùng nhìn thấy**; dùng `getBytes(charset)` để đo byte **truyền/lưu**, không để đo byte nội bộ của `String`.

Tài liệu tra cứu: [Java 17 `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [JEP 254 — Compact Strings](https://openjdk.org/jeps/254) và [Java 17 `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).

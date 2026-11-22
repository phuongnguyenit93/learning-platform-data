# `String.codePoints()` kết hợp surrogate pair thành code point trong Java

## 1. Vấn đề: một ký tự Unicode có thể chiếm hai `char`

Trong Java, kiểu nguyên thủy `char` có **16 bit** và một `String` được lưu theo các **UTF-16 code unit**. Với ký tự thuộc Basic Multilingual Plane (BMP), ví dụ `A` (U+0041), một UTF-16 code unit thường đủ biểu diễn ký tự. Nhưng các code point ngoài BMP, như emoji `😃` (U+1F603), cần **hai UTF-16 code unit** liên tiếp, gọi là **surrogate pair**.

Ví dụ:

~~~java
String text = "A😃B";
System.out.println(text.length());             // 4 code unit UTF-16
System.out.println(text.codePoints().count()); // 3 code point
~~~

Ta **nhìn thấy ba ký hiệu** `A`, `😃`, `B`, nhưng `length()` trả về `4` vì `😃` chiếm **hai `char`**. Đây là lý do không thể mặc định `charAt(i)` trả về trọn vẹn một code point Unicode.

**Điểm chính:** `String.codePoints()` tạo `IntStream` gồm các Unicode code point được đọc từ chuỗi. Nếu nó gặp một **high surrogate** ngay trước một **low surrogate**, nó kết hợp hai code unit ấy thành **một giá trị `int`** trong stream. Các code unit không tạo thành cặp hợp lệ được đưa ra riêng lẻ.

## 2. Ba khái niệm dễ nhầm

| Khái niệm | Trong Java | Ví dụ với `A😃B` |
| --- | --- | --- |
| UTF-16 **code unit** | `char` 16 bit, được `length()`, `charAt()`, `chars()` quan sát | 4 đơn vị: U+0041, U+D83D, U+DE03, U+0042 |
| Unicode **code point** | Số nguyên biểu thị một mã Unicode, thường xử lý bằng `int` | 3 mã: U+0041, U+1F603, U+0042 |
| **Grapheme cluster** (cụm ký tự người dùng nhìn thấy) | Khái niệm phân đoạn văn bản Unicode, không tương đương `char` hay code point | Có thể chứa nhiều code point dù hiển thị như một ký tự |

Không phải mọi code point đều là một ký tự hiển thị độc lập. Ví dụ `e` + dấu sắc kết hợp `\u0301` là **hai code point** có thể cùng tạo nên một chữ `é` trên màn hình. Emoji có biến thể màu da, variation selector hoặc chuỗi Zero Width Joiner (ZWJ) cũng có thể gồm nhiều code point nhưng hiển thị thành một biểu tượng.

`codePoints()` giúp đọc **code point**, **không** tự ghép các code point thành grapheme cluster và không tự chuẩn hóa Unicode.

## 3. Surrogate pair là gì?

Trong UTF-16, các code point từ U+10000 đến U+10FFFF được mã hóa bằng **hai `char`**:

- **High surrogate**: giá trị trong khoảng U+D800–U+DBFF.
- **Low surrogate**: giá trị trong khoảng U+DC00–U+DFFF.

Hai giá trị phải xuất hiện **theo thứ tự high rồi low và nằm cạnh nhau** mới tạo nên surrogate pair hợp lệ. Công thức ghép:

~~~text
codePoint = 0x10000
          + ((high - 0xD800) << 10)
          +  (low  - 0xDC00)
~~~

Với `😃` (U+1F603), UTF-16 chứa:

~~~text
High surrogate: U+D83D
Low surrogate : U+DE03
Kết hợp       : U+1F603
~~~

Java cung cấp sẵn các hàm `Character.isHighSurrogate(char)`, `Character.isLowSurrogate(char)`, `Character.isSurrogatePair(char, char)`, `Character.toCodePoint(high, low)` và `Character.toChars(int)`. Nên dùng API chuẩn thay vì tự viết công thức ghép trong code ứng dụng.

Ví dụ minh họa riêng (các lệnh đặt trong phương thức `main`):

~~~java
String emoji = "😃";
char high = emoji.charAt(0);
char low = emoji.charAt(1);

System.out.println(Character.isHighSurrogate(high));   // true
System.out.println(Character.isLowSurrogate(low));     // true
System.out.println(Character.isSurrogatePair(high, low)); // true
System.out.println(Character.toCodePoint(high, low) == 0x1F603); // true
~~~

**Lưu ý:** một code point trong BMP (ví dụ chữ `A`) được biểu diễn bởi một code unit; riêng vùng U+D800–U+DFFF được dành cho surrogate nên không phải các Unicode scalar value hợp lệ khi đứng lẻ.

## 4. So sánh `chars()` và `codePoints()`

Cả hai trả về `IntStream`, nhưng **ý nghĩa mỗi `int`** khác nhau.

### `String.chars()`

`chars()` xuất ra từng UTF-16 code unit dưới dạng `int` bằng cách mở rộng giá trị `char` thành số nguyên không dấu. Nó **không ghép** surrogate pair.

~~~java
"A😃B".chars()
       .mapToObj(cp -> String.format("U+%04X", cp))
       .forEach(System.out::println);
~~~

Kết quả:

~~~text
U+0041
U+D83D
U+DE03
U+0042
~~~

### `String.codePoints()`

`codePoints()` xét các phần tử `char` liên tiếp. Nếu gặp high surrogate và low surrogate liền nhau, nó phát ra **một `int` code point bổ sung**; còn lại phát ra giá trị code unit riêng lẻ.

~~~java
"A😃B".codePoints()
       .mapToObj(cp -> String.format("U+%04X", cp))
       .forEach(System.out::println);
~~~

Kết quả:

~~~text
U+0041
U+1F603
U+0042
~~~

| Phương thức | Số phần tử với `A😃B` | Đơn vị được duyệt |
| --- | ---: | --- |
| `text.length()` | 4 | Độ dài theo UTF-16 code unit |
| `text.chars().count()` | 4 | Mỗi `int` là một code unit |
| `text.codePoints().count()` | 3 | Mỗi `int` là một code point được giải mã |
| `text.codePointCount(0, text.length())` | 3 | Đếm code point trong một vùng chỉ số UTF-16 |

`String.codePoints()` có từ Java 9, còn nội dung ở đây dùng Java 17+ để thống nhất ví dụ. `IntStream` xử lý code point theo thứ tự của chuỗi khi duyệt tuần tự.

## 5. Ví dụ Java 17+ đầy đủ, chạy được

Lưu tệp thành `CodePointsDemo.java` (mã nguồn UTF-8):

~~~java
import java.util.stream.Collectors;

public class CodePointsDemo {
    private static String hex(int value) {
        return String.format("U+%04X", value);
    }

    public static void main(String[] args) {
        String text = "A😃B";

        System.out.println("length=" + text.length());
        System.out.println("chars=" + text.chars().count());
        System.out.println("codePoints=" + text.codePoints().count());

        System.out.println("units=" +
                text.chars()
                    .mapToObj(CodePointsDemo::hex)
                    .collect(Collectors.joining(", ")));

        System.out.println("points=" +
                text.codePoints()
                    .mapToObj(CodePointsDemo::hex)
                    .collect(Collectors.joining(", ")));

        System.out.println("charAt1=" + hex(text.charAt(1)));
        System.out.println("pointAt1=" + hex(text.codePointAt(1)));
        System.out.println("before3=" + hex(text.codePointBefore(3)));
        System.out.println("offsetAfter2=" +
                text.offsetByCodePoints(0, 2));

        System.out.println("supplementary=" +
                text.codePoints()
                    .filter(Character::isSupplementaryCodePoint)
                    .count());

        String unpaired = new String(new char[] {
                '\uD83D', 'X', '\uDE03'
        });
        System.out.println("unpaired=" +
                unpaired.codePoints()
                        .mapToObj(CodePointsDemo::hex)
                        .collect(Collectors.joining(", ")));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CodePointsDemo.java
java CodePointsDemo
~~~

Kết quả chuẩn:

~~~text
length=4
chars=4
codePoints=3
units=U+0041, U+D83D, U+DE03, U+0042
points=U+0041, U+1F603, U+0042
charAt1=U+D83D
pointAt1=U+1F603
before3=U+1F603
offsetAfter2=3
supplementary=1
unpaired=U+D83D, U+0058, U+DE03
~~~

Diễn giải:

1. `charAt(1)` trả về **high surrogate** U+D83D, chỉ là **một nửa** của emoji.
2. `codePointAt(1)` nhìn thêm low surrogate ở vị trí 2, trả về code point U+1F603.
3. `codePointBefore(3)` đọc về phía trước chỉ số 3, kết hợp hai code unit ở vị trí 1 và 2 thành U+1F603.
4. `offsetByCodePoints(0, 2)` đi qua **hai code point** kể từ chỉ số UTF-16 0 nên trả về chỉ số UTF-16 `3`, tức vị trí chữ `B`.
5. `filter(Character::isSupplementaryCodePoint)` đếm được một code point ngoài BMP.
6. Ví dụ `unpaired` cố ý đặt high surrogate, chữ `X`, low surrogate **không kề nhau**. `codePoints()` không ghép chúng thành một code point; nó xuất lần lượt U+D83D, U+0058, U+DE03.

Các dòng hiển thị code point theo hệ thập lục phân để phân biệt rõ mã Unicode với ký tự xuất hiện trên terminal.

## 6. Cách duyệt và xử lý code point đúng

### 6.1. Duyệt bằng stream

Nếu chỉ quan tâm các code point thực tế, dùng `codePoints()`:

~~~java
String s = "A😃B";
s.codePoints().forEachOrdered(cp -> {
    System.out.println(String.format("U+%04X", cp));
});
~~~

Kết quả:

~~~text
U+0041
U+1F603
U+0042
~~~

Phương thức `codePoints()` là **nguồn dữ liệu** cho pipeline `IntStream`. Có thể dùng `filter`, `map`, `distinct`, `count` hoặc `toArray` như với các primitive stream khác. Stream không tự biến thành danh sách `String` một ký tự.

Ví dụ lọc các code point ngoài BMP:

~~~java
long count = "A😃B".codePoints()
        .filter(Character::isSupplementaryCodePoint)
        .count();
System.out.println(count); // 1
~~~

Lưu ý các phương thức `Character.isLetter(int)`, `Character.isDigit(int)`, `Character.getType(int)` nhận `int codePoint`, phù hợp khi kiểm tra đặc tính Unicode của từng code point.

### 6.2. Khôi phục `String` từ các code point

Không chuyển code point bổ sung thành một `char` duy nhất bằng ép kiểu, vì sẽ làm mất thông tin:

~~~java
int smile = 0x1F603;
// char broken = (char) smile; // Ép kiểu làm mất các bit cao: không phải 😃.
String restored = new String(Character.toChars(smile));
System.out.println(restored.codePointAt(0) == smile); // true
~~~

`Character.toChars(int)` chuyển code point ngoài BMP thành cặp surrogate. Khi ghép nhiều code point vào chuỗi, dùng `StringBuilder.appendCodePoint(int)`:

~~~java
int[] points = "A😃B".codePoints().toArray();
StringBuilder builder = new StringBuilder();

for (int point : points) {
    builder.appendCodePoint(point);
}

System.out.println(builder.toString().equals("A😃B")); // true
~~~

Phân biệt `append((char) point)` và `appendCodePoint(point)`: cách thứ nhất chỉ thêm **một code unit**, còn cách thứ hai thêm đúng một hoặc hai UTF-16 code unit tùy code point.

### 6.3. Chỉ số UTF-16 và chỉ số code point không giống nhau

Các API `charAt`, `substring`, `indexOf`, `codePointAt` đều nhận/chia sẻ **chỉ số UTF-16** của `String`, không tự hiểu đó là vị trí code point thứ mấy.

~~~java
String s = "A😃B";

// Bắt đầu từ UTF-16 index 1, bỏ qua đúng một code point (emoji).
int afterEmoji = s.offsetByCodePoints(1, 1);
System.out.println(afterEmoji);        // 3
System.out.println(s.charAt(afterEmoji)); // B
~~~

Nếu cần lấy phần tử Unicode thứ `k` (đếm từ 0), dùng `offsetByCodePoints(0, k)` để tìm vị trí UTF-16, rồi `codePointAt(index)` để lấy code point. Bảo đảm `k` nằm trong phạm vi trước khi truy cập; các phương thức này có thể ném `IndexOutOfBoundsException` khi chỉ số không hợp lệ.

Ví dụ lấy **đúng một code point** dưới dạng `String`:

~~~java
String text = "A😃B";
int start = text.offsetByCodePoints(0, 1);
int end = text.offsetByCodePoints(start, 1);
String emoji = text.substring(start, end);

System.out.println(emoji.codePoints().count()); // 1
~~~

`substring(1, 2)` sẽ chỉ lấy high surrogate, còn `substring(1, 3)` lấy đủ hai code unit cho emoji trong ví dụ này.

## 7. Surrogate lẻ: giới hạn quan trọng của `codePoints()`

Một `String` Java có thể chứa dữ liệu UTF-16 **không ghép cặp hợp lệ**, chẳng hạn một high surrogate không có low surrogate ngay sau hoặc một low surrogate đứng lẻ.

~~~java
String invalid = new String(new char[]{'\uD83D', 'X'});
System.out.println(invalid.length());            // 2
System.out.println(invalid.codePoints().count()); // 2
~~~

Java **không âm thầm xóa**, ghép sai vị trí hoặc tự sửa các surrogate đứng lẻ khi chạy `codePoints()`. Theo hợp đồng của `String.codePoints()`, một surrogate **không ghép cặp** được xuất ra như một giá trị `int` bằng cách mở rộng chính code unit của nó (ví dụ U+D83D).

Điều cần phân biệt:

- Một surrogate lẻ có thể trở thành một phần tử trong `IntStream` do `codePoints()` trả về.
- Giá trị từ U+D800 đến U+DFFF **không phải Unicode scalar value hợp lệ** khi đứng riêng, dù Java vẫn cho phép `String` chứa chúng.
- Vì thế không nên xem việc dùng `codePoints()` là bước **xác thực UTF-16** hoặc sửa dữ liệu Unicode không hợp lệ.
- Nếu đầu vào có thể lỗi, cần quyết định rõ chính sách: phát hiện/từ chối, thay thế bằng ký tự thay thế U+FFFD hoặc áp dụng chính sách giải mã của thư viện phù hợp. Việc chuyển sang byte UTF-8 còn có thể áp dụng chính sách thay thế ký tự không hợp lệ riêng.

Có thể kiểm tra surrogate lẻ khi duyệt `codePoints()`:

~~~java
String invalid = new String(new char[]{'\uD83D'});
boolean hasUnpairedSurrogate = invalid.codePoints()
        .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);
System.out.println(hasUnpairedSurrogate); // true
~~~

Khi chỉ gặp cặp high–low hợp lệ, `codePoints()` trả về mã ngoài BMP của chúng, không xuất riêng hai giá trị surrogate.

## 8. Code point khác với một ký tự người dùng nhìn thấy

`codePoints()` giải quyết vấn đề **surrogate pair của UTF-16**, nhưng không giải quyết mọi vấn đề về việc đếm “ký tự”.

Ví dụ:

~~~java
String composed = "é";       // U+00E9
String decomposed = "e\u0301"; // U+0065 rồi U+0301

System.out.println(composed.codePoints().count());   // 1
System.out.println(decomposed.codePoints().count()); // 2
~~~

Hai chuỗi có thể trông giống nhau, nhưng biểu diễn Unicode khác nhau. Nếu ứng dụng cần chuẩn hóa tương đương, có thể cân nhắc `java.text.Normalizer` (ví dụ NFC) trước khi so sánh theo quy tắc nghiệp vụ; `codePoints()` **không tự chuẩn hóa**.

Một emoji gồm nhiều thành phần hoặc một lá cờ tạo bởi các regional indicator cũng có thể có **nhiều code point** nhưng hiển thị như một biểu tượng. Với tác vụ di chuyển con trỏ, xóa một ký tự người dùng nhìn thấy, hoặc giới hạn độ dài theo **grapheme cluster**, cần công cụ phân đoạn Unicode phù hợp, ví dụ thư viện hỗ trợ Unicode grapheme boundaries. Đừng lấy `codePoints().count()` làm số grapheme cluster.

## 9. Lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `length()` là số code point | `length()` đếm UTF-16 code unit | `codePointCount(0, length())` hoặc `codePoints().count()` |
| `charAt(i)` luôn lấy trọn ký tự Unicode | Có thể trả về nửa surrogate pair | `codePointAt(i)` khi `i` là UTF-16 index hợp lệ |
| `chars()` và `codePoints()` giống nhau | `chars()` tách từng code unit | `codePoints()` ghép surrogate pair hợp lệ |
| Ép `(char) cp` để dựng lại emoji | `char` không đủ chứa code point ngoài BMP | `Character.toChars(cp)` hoặc `appendCodePoint(cp)` |
| Dùng code point index với `substring` | `substring` nhận UTF-16 index | Quy đổi bằng `offsetByCodePoints` |
| `codePoints()` sửa mọi surrogate lỗi | Nó vẫn phát ra surrogate đứng lẻ | Xác thực hoặc xử lý lỗi riêng |
| Mỗi code point là một grapheme | Ký tự kết hợp và emoji phức hợp có nhiều code point | Phân đoạn grapheme phù hợp nhu cầu |

### Checklist tự kiểm tra

- Với `A😃B`: `length() == 4` và `codePoints().count() == 3`.
- `chars()` xuất U+D83D, U+DE03 riêng; `codePoints()` xuất U+1F603.
- `codePointAt(1)` trả về U+1F603; `charAt(1)` chỉ trả về U+D83D.
- `offsetByCodePoints(0, 2)` trả về UTF-16 index `3`.
- High và low surrogate bị ngăn bởi ký tự khác **không ghép**; stream vẫn mang surrogate đứng lẻ.
- `codePoints()` đếm code point, **không tự đếm grapheme cluster** hoặc chuẩn hóa Unicode.

**Kết luận:** `String.codePoints()` cho phép xử lý chuỗi Java theo từng code point Unicode thay vì từng `char` UTF-16. Nó ghép **high surrogate + low surrogate liền kề** thành một `int`, giúp duyệt emoji và ký tự ngoài BMP chính xác hơn. Tuy nhiên, chỉ số của `String` vẫn theo UTF-16, surrogate lỗi vẫn cần xử lý riêng, và việc nhận diện “một ký tự nhìn thấy” đòi hỏi mức phân tích grapheme cluster.

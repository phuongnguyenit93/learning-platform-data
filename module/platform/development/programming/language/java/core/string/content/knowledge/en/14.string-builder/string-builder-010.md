# `StringBuilder.repeat()` với code point hoặc `CharSequence` từ Java 21

## 1. Tổng quan và mục tiêu

Từ **Java 21**, `java.lang.StringBuilder` có thêm hai phương thức `repeat` giúp **nối lặp lại** một Unicode code point hoặc một `CharSequence` vào **cuối bộ đệm đang có**:

```java
StringBuilder repeat(int codePoint, int count)
StringBuilder repeat(CharSequence cs, int count)
```

Cả hai phương thức **thay đổi chính đối tượng `StringBuilder`**, trả về cùng tham chiếu `this` để có thể gọi nối tiếp và **không tự xóa** dữ liệu đang có. Chúng khác với `String.repeat(int)`, vốn trả về một `String` mới và đã có từ Java 11.

Ví dụ:

```java
StringBuilder builder = new StringBuilder(">");
builder.repeat('*', 3).repeat("ab", 2);
System.out.println(builder); // >***abab
```

Sau bài học, bạn có thể:
- Phân biệt chính xác hai overload `repeat(int, int)` và `repeat(CharSequence, int)`.
- Lặp một ký tự/emoji Unicode bằng **code point**, thay vì vô tình chia surrogate pair.
- Lặp một chuỗi hay đoạn văn bản chứa nhiều ký tự bằng `CharSequence`.
- Giải thích `count`, giá trị trả về, `length()` và các trường hợp `null`/đếm âm.
- Biết phiên bản Java cần dùng, khác biệt với `String.repeat()` và giải pháp thay thế trước Java 21.

## 2. Hai overload và ý nghĩa tham số

| Phương thức | Tham số đầu | `count` | Tác động |
| --- | --- | --- | --- |
| `repeat(int codePoint, int count)` | Giá trị nguyên của **một Unicode code point** | Số bản sao cần nối thêm | Nối biểu diễn UTF-16 của code point đó `count` lần. |
| `repeat(CharSequence cs, int count)` | Một dãy ký tự, ví dụ `String`, `StringBuilder` hoặc `StringBuffer` | Số bản sao cần nối thêm | Nối toàn bộ dãy `cs` `count` lần. |

Cả hai:
- Là phương thức **instance** của `StringBuilder`, không phải phương thức `static`.
- Có kiểu trả về `StringBuilder`, thực tế là **cùng builder đang nhận lệnh**.
- Nối vào **cuối**, không chèn tại một vị trí tùy ý.
- Đòi `count >= 0`; nếu `count == 0`, không nối thêm nội dung nào.
- Chỉ có từ **Java 21**. Nếu chương trình phải biên dịch ở Java 17 thì chưa dùng trực tiếp hai overload này được.

Ví dụ:

```java
StringBuilder b = new StringBuilder("Hi");

StringBuilder same = b.repeat('!', 2);

System.out.println(b);           // Hi!!
System.out.println(same == b);   // true
```

**Giải thích:** `repeat` không sinh ra builder riêng; nó nối hai dấu `!` vào `b`. Việc so sánh `same == b` cho kết quả `true` vì cả hai biến tham chiếu đến cùng đối tượng.

## 3. `repeat(int codePoint, int count)` — lặp một code point

Trong Java, `int codePoint` là giá trị số biểu diễn một code point Unicode. Với các ký tự trong BMP (Basic Multilingual Plane), biểu diễn UTF-16 thông thường dài **một** `char`. Với code point ngoài BMP như `🚀` (`U+1F680`), biểu diễn UTF-16 cần **hai** `char` (surrogate pair).

### 3.1. Ví dụ với code point trong BMP

```java
StringBuilder stars = new StringBuilder();
stars.repeat('*', 5);

System.out.println(stars);          // *****
System.out.println(stars.length()); // 5
```

Literal `'*'` có kiểu `char`, được mở rộng thành `int` khi gọi `repeat(int, int)`. Do đó mỗi lần lặp nối thêm ký tự dấu sao.

Có thể truyền trực tiếp giá trị code point:

```java
StringBuilder letters = new StringBuilder();
letters.repeat(65, 2);

System.out.println(letters); // AA
```

**Rất quan trọng:** `65` được hiểu là code point `U+0041` (chữ `A`), **không** được biến thành chuỗi chữ số `"65"`. Muốn lặp văn bản `"65"`, dùng overload `CharSequence`:

```java
System.out.println(
        new StringBuilder().repeat("65", 2)); // 6565
```

### 3.2. Ví dụ với emoji ngoài BMP

```java
StringBuilder emoji = new StringBuilder();
emoji.repeat(0x1F680, 2); // U+1F680: 🚀

System.out.println(emoji);                  // 🚀🚀
System.out.println(emoji.length());         // 4
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 2
```

`0x1F680` là **một code point**, nhưng khi mã hóa thành UTF-16 nó cần hai code unit: high surrogate `U+D83D` và low surrogate `U+DE80`. Lặp hai lần cho **4 code unit** nhưng chỉ **2 code point**.

Cách biểu diễn theo chỉ số:

| Chỉ số UTF-16 trong `"🚀🚀"` | Giá trị code unit | Thuộc code point |
| ---: | --- | --- |
| 0 | `U+D83D` | `🚀` thứ nhất |
| 1 | `U+DE80` | `🚀` thứ nhất |
| 2 | `U+D83D` | `🚀` thứ hai |
| 3 | `U+DE80` | `🚀` thứ hai |

Nếu `codePoint` có biểu diễn UTF-16 một code unit thì độ dài tăng thêm `count`; nếu có hai code unit thì tăng thêm `2 * count` (khi dữ liệu đủ dung lượng bộ nhớ). Vì vậy, **số lần lặp không luôn bằng mức tăng `StringBuilder.length()`**.

### 3.3. Code point hợp lệ, surrogate và đầu vào không tin cậy

Phương thức `repeat(int codePoint, int count)` báo `IllegalArgumentException` nếu code point **không phải giá trị Unicode code point hợp lệ** (ngoài phạm vi `U+0000..U+10FFFF`) hoặc `count` âm.

Một chi tiết Unicode: các giá trị surrogate `U+D800..U+DFFF` có thể được xem là **giá trị code point hợp lệ về mặt miền số** bởi `Character.isValidCodePoint`, nhưng **không phải Unicode scalar value** độc lập. Không nên dùng chúng làm một “ký tự hoàn chỉnh” khi sinh văn bản chuẩn cho bên ngoài. Nếu dữ liệu đến từ người dùng và yêu cầu là một Unicode scalar value, hãy chủ động loại trừ dải surrogate:

```java
static boolean isUnicodeScalar(int cp) {
    return cp >= 0 && cp <= 0x10FFFF
            && !(cp >= 0xD800 && cp <= 0xDFFF);
}
```

Đoạn trên là một **phương thức hỗ trợ**, cần đặt trong một lớp Java; nó không phải chương trình độc lập. Việc kiểm tra scalar value bổ sung là **chính sách đầu vào của ứng dụng**, không nên nhầm với toàn bộ hợp đồng xác thực của API `repeat`.

## 4. `repeat(CharSequence cs, int count)` — lặp cả một dãy ký tự

`CharSequence` là một interface chung cho các dãy ký tự; `String` và `StringBuilder` đều triển khai interface này. Overload `repeat(CharSequence, int)` lấy **toàn bộ dãy được truyền vào**, không chỉ một ký tự.

```java
StringBuilder b = new StringBuilder("List: ");
b.repeat("ab", 3);

System.out.println(b);          // List: ababab
System.out.println(b.length()); // 12
```

Phần đầu `"List: "` dài 6 code unit; `"ab"` dài 2, lặp 3 lần thêm 6, tổng `length() == 12`.

Có thể truyền một `CharSequence` khác `String`:

```java
CharSequence unit = new StringBuilder("XY");
StringBuilder output = new StringBuilder(">");
output.repeat(unit, 2);

System.out.println(output); // >XYXY
```

Ở đây `unit` được đọc như một dãy ký tự và `output` là nơi nhận bản lặp.

### 4.1. Dãy ký tự có emoji

```java
StringBuilder b = new StringBuilder();
b.repeat("🚀", 2);

System.out.println(b);          // 🚀🚀
System.out.println(b.length()); // 4
```

Dù truyền một `CharSequence` dài 2 code unit hay một code point `0x1F680`, kết quả văn bản ở ví dụ này giống nhau. Khác biệt là **ý nghĩa tham số**: overload `int` nhận **một code point**, còn overload `CharSequence` nhận **một dãy UTF-16 code unit**, có thể có nhiều code point.

Overload `CharSequence` không phân đoạn thành “ký tự nhìn thấy được”, không chuẩn hóa Unicode và không tự sửa surrogate đơn lẻ đã tồn tại trong dữ liệu nguồn.

### 4.2. `null` có hành vi riêng

Theo hợp đồng Java 21, khi `cs == null`, phương thức nối lặp lại **chuỗi bốn chữ `"null"`**:

```java
StringBuilder b = new StringBuilder();
b.repeat((CharSequence) null, 2);

System.out.println(b);          // nullnull
System.out.println(b.length()); // 8
```

Đây là **nội dung văn bản `"null"`**, không phải ngoại lệ `NullPointerException` và cũng không phải bỏ qua đầu vào. Hãy dùng kiểm tra `null` riêng nếu ứng dụng muốn chính sách khác:

```java
CharSequence input = null;
StringBuilder b = new StringBuilder();

if (input != null) {
    b.repeat(input, 2);
}
System.out.println(b.length()); // 0
```

Không thể truyền `null` cho tham số nguyên thủy `int codePoint`; trường hợp `null` trên chỉ liên quan đến overload `CharSequence`.

### 4.3. Tham số `CharSequence` có thể thay đổi

`String` là bất biến, nhưng `StringBuilder` hoặc một `CharSequence` tự định nghĩa có thể thay đổi trong quá trình thực thi. Nếu dãy nguồn bị sửa đồng thời trong khi gọi `repeat`, không nên giả định kết quả là bản sao nhất quán theo ý muốn. Với dãy nguồn có thể bị sửa, hãy tạo **snapshot `String` ổn định** trước:

```java
StringBuilder source = new StringBuilder("OK");
String snapshot = source.toString();

StringBuilder dest = new StringBuilder();
dest.repeat(snapshot, 3);

System.out.println(dest); // OKOKOK
```

Điều này làm rõ phần được lặp. Nếu bản thân việc **đọc `source` để tạo snapshot** cũng cạnh tranh với một luồng sửa `source`, ứng dụng vẫn cần cơ chế đồng bộ phù hợp. `StringBuilder` nói chung **không bảo đảm thread-safe**.

## 5. `count` bằng 0, âm và vùng rỗng

### Trường hợp `count == 0`

Lặp `0` lần không làm thay đổi nội dung:

```java
StringBuilder b = new StringBuilder("seed");

b.repeat("XY", 0);
b.repeat('*', 0);

System.out.println(b); // seed
```

Dãy rỗng cũng không tạo thêm ký tự:

```java
StringBuilder b = new StringBuilder("X");
b.repeat("", 100);

System.out.println(b); // X
```

### Trường hợp `count < 0`

Số lần lặp âm không hợp lệ. Cả hai overload đều ném `IllegalArgumentException`:

```java
try {
    new StringBuilder().repeat("ab", -1);
} catch (IllegalArgumentException ex) {
    System.out.println("Negative count rejected"); // In ra dòng này.
}
```

Tương tự, `repeat('A', -1)` không hợp lệ.

### Trường hợp code point vượt miền hợp lệ

```java
try {
    new StringBuilder().repeat(0x110000, 1);
} catch (IllegalArgumentException ex) {
    System.out.println("Invalid code point rejected");
}
```

`U+110000` lớn hơn giới hạn Unicode `U+10FFFF` nên không hợp lệ. Đừng dựa vào **thông báo lỗi** cụ thể của JVM; kiểm tra lớp ngoại lệ và điều kiện nghiệp vụ.

### Số lần lặp quá lớn

Với `count` rất lớn và đầu vào dài, nội dung kết quả có thể cần quá nhiều bộ nhớ hoặc vượt giới hạn kích thước mảng nội bộ. Cần đặt giới hạn đầu vào trước khi tạo dữ liệu:

```java
static void validateRepeatCount(int count, int max) {
    if (count < 0 || count > max) {
        throw new IllegalArgumentException(
                "count must be in [0, " + max + "]");
    }
}
```

Giới hạn `max` tùy nghiệp vụ; không có một con số cố định phù hợp mọi ứng dụng. Với hệ thống xử lý dữ liệu đầu vào không tin cậy, hãy kiểm soát cả **số lần lặp** lẫn **kích thước đoạn bị lặp**.

## 6. Chương trình Java 21+ chạy độc lập

Lưu mã sau vào file `StringBuilderRepeatDemo.java`. **Yêu cầu JDK 21 trở lên** để biên dịch:

```java
public class StringBuilderRepeatDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(">");
        builder.repeat('*', 3).repeat("ab", 2);
        System.out.println("combined = " + builder);

        StringBuilder rocket = new StringBuilder();
        rocket.repeat(0x1F680, 2);
        System.out.println("rocket = " + rocket);
        System.out.println("UTF-16 units = " + rocket.length());
        System.out.println("code points = "
                + rocket.codePointCount(0, rocket.length()));

        System.out.println("int code point = "
                + new StringBuilder().repeat(65, 2));
        System.out.println("text sequence = "
                + new StringBuilder().repeat("65", 2));

        StringBuilder nulls = new StringBuilder();
        nulls.repeat((CharSequence) null, 2);
        System.out.println("null sequence = " + nulls);

        StringBuilder unchanged = new StringBuilder("seed");
        unchanged.repeat("XY", 0);
        System.out.println("zero count = " + unchanged);

        StringBuilder same = new StringBuilder("x");
        boolean sameReference = same.repeat('!', 2) == same;
        System.out.println("same reference = " + sameReference);
        System.out.println("mutable result = " + same);

        try {
            new StringBuilder().repeat("A", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative count rejected");
        }

        try {
            new StringBuilder().repeat(0x110000, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid code point rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StringBuilderRepeatDemo.java
java StringBuilderRepeatDemo
```

Đầu ra mong đợi (terminal hỗ trợ Unicode):

```text
combined = >***abab
rocket = 🚀🚀
UTF-16 units = 4
code points = 2
int code point = AA
text sequence = 6565
null sequence = nullnull
zero count = seed
same reference = true
mutable result = x!!
negative count rejected
invalid code point rejected
```

**Giải thích:** Hai overload hoạt động ngay trên builder được gọi. `repeat(0x1F680, 2)` ghi hai surrogate pair nên `length()` là 4, nhưng số code point là 2. `repeat(65, 2)` xem `65` là code point của `A`, trong khi `repeat("65", 2)` nhân đôi chuỗi số. `null` trở thành văn bản `"nullnull"`; `count == 0` giữ nguyên trạng thái; lần gọi `repeat` trả về chính builder để gọi nối tiếp.

Chương trình này **không** dành cho JDK 17: khi biên dịch với Java 17, hai overload `StringBuilder.repeat` sẽ không được tìm thấy trong API.

## 7. So sánh `StringBuilder.repeat` và `String.repeat`

| Thuộc tính | `StringBuilder.repeat` | `String.repeat` |
| --- | --- | --- |
| Có từ | Java **21** | Java **11** |
| Phương thức điển hình | `builder.repeat("ab", 3)` hoặc `builder.repeat('*', 3)` | `"ab".repeat(3)` |
| Đối tượng nhận lệnh | `StringBuilder` mutable | `String` immutable |
| Kết quả | Trả **cùng `StringBuilder`** đã được nối thêm | Trả `String` kết quả |
| Nội dung trước đó | **Giữ lại**, rồi nối phần lặp ở cuối | Lặp nội dung của chính chuỗi nhận lệnh |
| Loại đầu vào bổ sung | Code point `int` hoặc `CharSequence` | Không có tham số code point/CharSequence |
| Hỗ trợ chuỗi có emoji | Có, biểu diễn theo UTF-16 | Có, lặp chuỗi như văn bản |

Ví dụ đối chiếu:

```java
String text = "ab";
String repeatedText = text.repeat(3);

StringBuilder builder = new StringBuilder(">");
builder.repeat("ab", 3);

System.out.println(text);         // ab
System.out.println(repeatedText); // ababab
System.out.println(builder);      // >ababab
```

Nếu bạn cần một **`String` bất biến** với mẫu lặp cố định và không cần tích lũy phần khác, `"ab".repeat(3)` thường rất trực tiếp. Nếu bạn đang xây dựng một thông điệp nhiều phần trong một `StringBuilder`, `builder.repeat("ab", 3)` làm rõ ý định nối thêm mà không cần tạo riêng chuỗi trung gian chỉ để append.

Không có lời khẳng định chung rằng cách này luôn nhanh hơn cách kia. Hiệu năng phụ thuộc kích thước dữ liệu, phiên bản JVM, bộ nhớ và bối cảnh sử dụng.

## 8. Trước Java 21: làm thế nào?

Nếu ứng dụng phải hỗ trợ Java 17, **không thể dùng trực tiếp** `builder.repeat(codePoint, count)` hoặc `builder.repeat(cs, count)`.

### Cách A — `String.repeat` rồi `append` (Java 11+)

```java
StringBuilder builder = new StringBuilder(">");
builder.append("ab".repeat(3));

System.out.println(builder); // >ababab
```

Nếu cần lặp một code point ngoài BMP trên Java 17, chuyển nó thành chuỗi trước:

```java
int codePoint = 0x1F680;
String unit = new String(Character.toChars(codePoint));

StringBuilder builder = new StringBuilder();
builder.append(unit.repeat(2));

System.out.println(builder); // 🚀🚀
```

`Character.toChars(int)` đưa một code point hợp lệ thành `char[]` UTF-16 tương ứng; với `🚀`, mảng dài 2. Đây là phương án rõ nghĩa khi cần chuyển giá trị code point thành chuỗi lặp.

### Cách B — Lặp `append` từng lần

```java
StringBuilder builder = new StringBuilder(">");
CharSequence unit = "ab";

for (int i = 0; i < 3; i++) {
    builder.append(unit);
}

System.out.println(builder); // >ababab
```

Với code point:

```java
StringBuilder builder = new StringBuilder();
int cp = 0x1F680;

for (int i = 0; i < 2; i++) {
    builder.appendCodePoint(cp);
}

System.out.println(builder); // 🚀🚀
```

Cả hai ví dụ có thể dùng từ trước Java 21. Lời gọi `appendCodePoint` thích hợp cho code point Unicode, thay vì chuyển một code point ngoài BMP thành một `char` đơn lẻ.

Nếu bạn phải chạy cả trên Java 17 và Java 21, dùng phương án chung `append` / `appendCodePoint` hoặc định nghĩa một phương thức hỗ trợ tương thích Java 17; không nên thêm phương thức Java 21 vào mã rồi giả định nó sẽ tự được thay thế ở runtime cũ.

## 9. Dung lượng bộ đệm và độ dài sau lặp

`StringBuilder.length()` trả về số **UTF-16 code unit thực sự đang chứa**, khác với `capacity()` là dung lượng bộ đệm dành sẵn. `repeat` có thể làm `length()` tăng và có thể khiến builder mở rộng dung lượng lưu trữ.

Nếu trước khi lặp `builder.length() == L` và đoạn `CharSequence` có `cs.length() == M`, thì với lần lặp thành công:

```text
newLength = L + M * count
```

Với overload code point có độ dài biểu diễn UTF-16 là `U` (thường `1` hoặc `2`):

```text
newLength = L + U * count
```

Đó là độ dài theo `char` UTF-16, không phải số ký tự được cảm nhận bằng mắt.

Ví dụ:

```java
StringBuilder b = new StringBuilder("x");
b.repeat("🚀", 3);

System.out.println(b.length()); // 7 (1 + 3*2)
```

Có thể gọi `ensureCapacity(int)` trước khi xây dựng một chuỗi lớn để dự phòng chỗ chứa, nhưng chỉ nên làm khi đã tính kích thước cẩn thận, kiểm soát tràn số và có lý do thực tế. `ensureCapacity` **không** thay đổi độ dài nội dung, không giúp lặp dữ liệu quá giới hạn bộ nhớ thành công, và không là yêu cầu bắt buộc khi dùng `repeat`.

Ví dụ về kiểm tra dung lượng dự kiến bằng `long`:

```java
long requested = (long) unit.length() * count;
long newLength = requested + builder.length();

if (newLength > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Result too large");
}
```

Đây là phần minh họa cần đặt trong phương thức có các biến `unit`, `count`, `builder` đã khai báo. Dùng `long` tránh tràn âm khi nhân/chia dự kiến với số lượng lớn, nhưng **kết quả không vượt giới hạn `int` vẫn có thể quá lớn so với tài nguyên thực tế**, nên ứng dụng cần giới hạn nhỏ hơn nếu phù hợp.

## 10. Lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `repeat` trên `StringBuilder` nhưng biên dịch bằng JDK 17. | Không tìm thấy phương thức tương ứng. | Dùng **JDK 21+** hoặc phương án `append`/`appendCodePoint` trước Java 21. |
| Nghĩ `repeat(65, 2)` tạo `"6565"`. | Thực tế tạo `"AA"`. | Truyền `"65"` kiểu `CharSequence` nếu muốn nhân chuỗi chữ số. |
| Nghĩ `repeat(int, count)` chỉ lặp một `char` 16 bit. | Dễ xử lý sai emoji ngoài BMP. | Giá trị `int` được hiểu là **code point**; kiểm tra `length()` theo UTF-16. |
| Nghĩ `repeat` trả một builder mới và giữ builder cũ nguyên. | Làm thay đổi nội dung đối tượng đang dùng chung. | Nhớ phương thức **mutates receiver** và trả chính `this`. |
| Nghĩ `count = 0` tạo một bản sao. | Thực tế không nối thêm gì. | Dùng `count > 0` khi muốn có phần lặp. |
| Truyền số lần lặp âm. | `IllegalArgumentException`. | Xác thực số lần lặp. |
| Truyền `CharSequence null` và mong bỏ qua. | Nối văn bản `"null"` theo số lần lặp. | Định nghĩa chính sách `null` và kiểm tra tường minh nếu cần. |
| Lặp dãy mutable đang được sửa đồng thời. | Kết quả không còn có thể dự đoán theo một snapshot ổn định. | Dùng snapshot ổn định và cơ chế đồng bộ khi cần. |
| Nhầm `length` với `capacity`. | Tính sai kích thước dữ liệu thực hoặc khả năng cấp phát. | Dùng `length()` cho nội dung, `capacity()` cho vùng đệm. |
| Không giới hạn `count` hoặc kích thước `cs`. | Có thể vượt tài nguyên hoặc giới hạn kích thước nội bộ. | Xác thực kích thước theo yêu cầu nghiệp vụ. |

## 11. Bài tập tự kiểm tra

### Bài 1 — code point hay văn bản số?

```java
System.out.println(new StringBuilder().repeat(65, 3));
System.out.println(new StringBuilder().repeat("65", 3));
```

**Đáp án:**

```text
AAA
656565
```

`65` là code point U+0041; `"65"` là hai ký tự chữ số lặp ba lần.

### Bài 2 — Emoji và độ dài

```java
StringBuilder b = new StringBuilder();
b.repeat(0x1F680, 3);
System.out.println(b.length());
System.out.println(b.codePointCount(0, b.length()));
```

**Đáp án:** `6` rồi `3`. Mỗi emoji `🚀` chiếm hai code unit UTF-16.

### Bài 3 — Có ghi đè phần trước không?

```java
StringBuilder b = new StringBuilder("ABC");
b.repeat("-", 2);
System.out.println(b);
```

**Đáp án:** `ABC--`. `repeat` **nối vào cuối**, không xóa `ABC`.

### Bài 4 — `null` và số lần lặp

```java
StringBuilder b = new StringBuilder("X");
b.repeat((CharSequence) null, 2);
System.out.println(b);
```

**Đáp án:** `Xnullnull`. Overload nhận `CharSequence` chuyển `null` thành chuỗi `"null"` rồi lặp hai lần.

### Bài 5 — Phân biệt Java 17 và 21

Bạn cần lặp một chuỗi `"ab"` bốn lần trong `StringBuilder` nhưng dự án bắt buộc Java 17. Có thể gọi `builder.repeat("ab", 4)` không?

**Đáp án:** Không. Overload này có từ **Java 21**. Trên Java 17 có thể viết `builder.append("ab".repeat(4))` hoặc một vòng lặp `append("ab")`.

### Bài 6 — Xử lý đầu vào rủi ro

Ứng dụng nhận `count` từ API công khai để sinh báo cáo văn bản. Nên làm gì trước khi gọi `repeat`?

**Đáp án:** Kiểm tra `count >= 0`, giới hạn tối đa theo tài nguyên/nghiệp vụ, giới hạn độ dài phần bị lặp và tránh tràn số khi dự tính dung lượng. Nếu dùng code point từ người dùng, xác thực miền Unicode theo yêu cầu và cân nhắc loại trừ surrogate khi cần Unicode scalar value.

## 12. Tóm tắt

- Từ **Java 21**, `StringBuilder` có `repeat(int codePoint, int count)` và `repeat(CharSequence cs, int count)`.
- Overload `int` lặp **một code point Unicode**; overload `CharSequence` lặp **cả một dãy ký tự**.
- Cả hai **nối thêm vào cuối builder hiện tại**, trả về chính builder và hỗ trợ chaining.
- `count == 0` không làm thay đổi nội dung; `count < 0` ném `IllegalArgumentException`. Code point ngoài miền hợp lệ cũng bị từ chối.
- `CharSequence null` được lặp như văn bản `"null"`.
- `StringBuilder.length()` tính theo **UTF-16 code unit**; code point ngoài BMP có thể chiếm hai `char` mỗi lần lặp.
- `String.repeat(int)` có từ Java 11, nhưng **khác** vì trả `String` thay vì sửa `StringBuilder`.
- Với Java 17, dùng `String.repeat` + `append` hoặc vòng lặp `append`/`appendCodePoint`.

## Tài liệu tham khảo

- [Oracle Java SE 21 — `StringBuilder`: `repeat(int,int)` và `repeat(CharSequence,int)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html)
- [Oracle Java SE 21 — `String.repeat(int)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#repeat(int))
- [Oracle Java SE 21 — `Character` và Unicode code points](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Java Language Specification 21 — Unicode escapes và ký tự](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html)

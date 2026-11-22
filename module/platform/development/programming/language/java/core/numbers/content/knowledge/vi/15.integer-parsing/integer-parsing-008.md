# Phân tích đoạn CharSequence mà không tạo String con khi API hỗ trợ

> **Java core – numbers · Phân tích số nguyên**  
> **Mục tiêu:** Parse trực tiếp một đoạn ký tự trong `String`, `StringBuilder`, `StringBuffer` hay `CharBuffer` khi cần đọc `int`/`long` có dấu hoặc không dấu; xác định đúng chỉ số đầu/cuối và radix; tránh tạo `substring` không cần thiết; xử lý ngoại lệ, overflow và giới hạn hiệu năng một cách chính xác trong Java 17+.

## 1. Tình huống thực tế: chỉ cần một con số nằm giữa chuỗi dài

Giả sử bộ xử lý nhận một dòng:

```text
id=12345;delta=-42;flags=7F
```

Mục tiêu là đọc `12345` thành `int`, `-42` thành `int` và `7F` thành số nguyên hệ 16.

Cách nhiều người viết:

```java
String line = "id=12345;delta=-42;flags=7F";
int idStart = line.indexOf("id=") + 3;
int idEnd = line.indexOf(';', idStart);

int id = Integer.parseInt(line.substring(idStart, idEnd));
```

Cách này đúng với đầu vào đã được kiểm soát. Nhưng `substring(idStart, idEnd)` tạo một đối tượng `String` biểu diễn đoạn con, trong khi việc parse thực chất chỉ cần **đọc ký tự từ vị trí đầu đến vị trí cuối**.

Nếu API được gọi hỗ trợ trực tiếp một vùng `CharSequence`, có thể viết:

```java
int id = Integer.parseInt(line, idStart, idEnd, 10);
```

Cú pháp sau đọc ngay khoảng `[idStart, idEnd)` của chuỗi ban đầu và không yêu cầu chương trình tạo `String` con bằng `substring`. Đây là lợi thế đáng cân nhắc trong parser phải xử lý nhiều trường số hoặc lượng bản ghi lớn.

**Phân biệt quan trọng:** “Không tự tạo `String` con” **không đồng nghĩa** “toàn bộ thao tác được bảo đảm không cấp phát bộ nhớ” hay “chắc chắn nhanh hơn trong mọi trường hợp”. Mục tiêu là tránh một bước chuyển đổi trung gian **không cần thiết**; hiệu năng thực tế còn phụ thuộc vào đầu vào, JVM, JIT, xử lý lỗi và cách xác định các chỉ số.

## 2. CharSequence là gì và vì sao có thể parse trực tiếp?

`CharSequence` là interface đại diện cho một **dãy ký tự có thể truy cập bằng chỉ số**. Một số kiểu quen thuộc triển khai interface này:

| Kiểu | Đặc điểm thường gặp | Ý nghĩa khi parse |
| --- | --- | --- |
| `String` | Chuỗi bất biến | Có thể parse một vùng trực tiếp, không gọi `substring` |
| `StringBuilder` | Bộ đệm ký tự có thể thay đổi | Parse trực tiếp dữ liệu đang tích lũy, không cần `toString()` |
| `StringBuffer` | Bộ đệm ký tự có thể thay đổi với cơ chế đồng bộ của lớp | Cũng truyền được như `CharSequence`; phải xét việc sửa dữ liệu đồng thời |
| `CharBuffer` | Vùng truy cập ký tự dạng buffer | Có thể parse từ view của buffer nếu chỉ số phù hợp |
| Implement custom `CharSequence` | Quy tắc truy cập do lớp tự định nghĩa | Cần đảm bảo `length()`, `charAt()` và dữ liệu nhất quán |

Các phương thức cơ bản của interface gồm `length()`, `charAt(index)` và `subSequence(start,end)`. Overload parse theo vùng có thể truy cập ký tự trực tiếp qua interface mà người gọi **không phải** lấy một `String` con để chuyển vào API chỉ nhận `String`.

Tuy nhiên, `CharSequence` có thể là **mutable**. Tài liệu JDK nêu rõ các overload parse theo vùng **không có biện pháp tự bảo vệ** khi dãy ký tự bị sửa trong lúc đang parse. Vì vậy, các bộ đệm chia sẻ giữa nhiều luồng cần kiểm soát việc thay đổi dữ liệu theo hợp đồng đồng bộ thích hợp; không giả định API parser sẽ tự tạo bản sao an toàn.

## 3. Bốn overload phù hợp trong Integer và Long

Java 9 bổ sung các overload parse một khoảng `CharSequence`; tất cả đều có trong Java 17+:

| Phương thức | Loại số | Kiểu trả về |
| --- | --- | --- |
| `Integer.parseInt(CharSequence, int, int, int)` | `int` có dấu | `int` |
| `Integer.parseUnsignedInt(CharSequence, int, int, int)` | 32 bit diễn giải không dấu | `int` (cùng 32 bit) |
| `Long.parseLong(CharSequence, int, int, int)` | `long` có dấu | `long` |
| `Long.parseUnsignedLong(CharSequence, int, int, int)` | 64 bit diễn giải không dấu | `long` (cùng 64 bit) |

Bốn tham số cùng một thứ tự:

```java
Integer.parseInt(sequence, beginIndex, endIndex, radix);
Long.parseLong(sequence, beginIndex, endIndex, radix);
Integer.parseUnsignedInt(sequence, beginIndex, endIndex, radix);
Long.parseUnsignedLong(sequence, beginIndex, endIndex, radix);
```

- `sequence`: dãy ký tự gốc; có thể là `StringBuilder` chứ không nhất thiết là `String`.
- `beginIndex`: chỉ số **bắt đầu, có tính vào đoạn** (*inclusive*).
- `endIndex`: chỉ số **kết thúc, không tính vào đoạn** (*exclusive*).
- `radix`: cơ số dùng để diễn giải chữ số; Java hỗ trợ từ `Character.MIN_RADIX = 2` đến `Character.MAX_RADIX = 36`.

Không có overload ba tham số `(CharSequence, begin, end)` tự mặc định radix 10 trong nhóm trên. Khi parse theo vùng, hãy truyền **đủ bốn tham số** và viết `10` cho số thập phân.

**Lưu ý loại API:** Các phương thức `Byte.parseByte`, `Short.parseShort`, `Integer.valueOf`, `Long.valueOf` hoặc constructor `BigInteger` **không tự có cùng overload bốn tham số** chỉ vì `Integer.parseInt` có. Phải kiểm tra chữ ký chính xác của lớp/phương thức trước khi chuyển đổi code.

## 4. Chỉ số [beginIndex, endIndex): ví dụ từng vị trí

Ví dụ:

```text
Chuỗi:  id=12345;delta=-42
Index:  0123456789...
        ^  ^    ^
        |  |    |
        |  3    8
        0

id=       ở [0,3)
12345     ở [3,8)
;         ở index 8
```

Mã Java:

```java
StringBuilder line = new StringBuilder("id=12345;delta=-42");
int from = 3;
int to = 8;

int id = Integer.parseInt(line, from, to, 10);
System.out.println(id); // 12345
```

Với `endIndex` loại trừ, dấu chấm phẩy tại vị trí 8 **không** bị đưa vào parser. Nếu vô tình gọi `Integer.parseInt(line, 3, 9, 10)`, đoạn sẽ bao gồm `"12345;"` và việc parse thất bại vì `;` không phải chữ số thập phân.

### Quy tắc xác định chỉ số

Một khoảng hợp lệ có:

\[
0 \le beginIndex \le endIndex \le sequence.length()
\]

- `beginIndex == endIndex`: khoảng rỗng; chỉ số **hợp lệ**, nhưng không có chữ số để parse nên `NumberFormatException`.
- `beginIndex < 0`: phạm vi không hợp lệ, `IndexOutOfBoundsException`.
- `beginIndex > endIndex`: phạm vi không hợp lệ, `IndexOutOfBoundsException`.
- `endIndex > sequence.length()`: phạm vi không hợp lệ, `IndexOutOfBoundsException`.

Đừng trộn chỉ số từ **mảng byte UTF-8**, offset của token hay số lượng **Unicode code point** với chỉ số được dùng bởi `CharSequence.charAt`. Trong các chuỗi Java thông dụng, các chỉ số này tính theo **đơn vị mã UTF-16**; ký tự ngoài BMP có thể chiếm hai đơn vị `char`. Với token số ASCII, mỗi chữ số chiếm một `char`, nhưng vị trí đầu của token vẫn phải lấy từ đúng nguồn `CharSequence` đang parse.

## 5. Parse trực tiếp từ StringBuilder: không cần toString hoặc substring

Khi một dòng đang được xây bằng `StringBuilder`, cách cũ có thể là:

```java
StringBuilder buffer = new StringBuilder("count=12345;");
int start = 6;
int end = 11;

// Tạo chuỗi từ đoạn rồi parse:
// int count = Integer.parseInt(buffer.substring(start, end));
```

Cách trực tiếp:

```java
int count = Integer.parseInt(buffer, start, end, 10);
System.out.println(count); // 12345
```

**Không cần viết** `buffer.toString().substring(start,end)`. Cách đó tạo một `String` toàn bộ rồi lại tạo chuỗi đoạn con — không đạt mục tiêu tận dụng overload theo vùng.

Không cần gọi `subSequence(start,end)` chỉ để đưa cho parser; overload đã nhận trực tiếp các chỉ số và `CharSequence`. Với kiểu `CharSequence` custom hoặc view đặc biệt, việc gọi `subSequence` có thể có đặc tính cấp phát riêng; hãy dựa vào contract triển khai thay vì đoán.

## 6. Signed int và long: dấu thuộc chính khoảng được parse

Các chuỗi số thập phân có thể có dấu ASCII `+` hoặc `-` **ở đầu đoạn được parse**:

```java
StringBuilder text = new StringBuilder("delta=-42;next=+17");

int delta = Integer.parseInt(text, 6, 9, 10); // -42
int next = Integer.parseInt(text, 15, 18, 10); // +17
```

Tại sao phải chú ý khoảng? Ví dụ nếu `beginIndex` bỏ qua dấu `-` thì parse ra giá trị **42**, sai ý nghĩa bản ghi, dù Java không ném ngoại lệ:

```java
int wrongMeaning = Integer.parseInt(text, 7, 9, 10); // 42
```

Nếu chỉ có `+` hoặc `-` mà không có chữ số, parse thất bại với `NumberFormatException`. Dấu ở **giữa** các chữ số cũng không hợp lệ.

Giới hạn miền:

```java
StringBuilder minimum = new StringBuilder("value=-2147483648");
int min = Integer.parseInt(minimum, 6, minimum.length(), 10);
System.out.println(min == Integer.MIN_VALUE); // true
```

Đây là giá trị biên âm của `int`. Nếu chuỗi số vượt miền từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE` thì parser **từ chối**, không làm tràn âm thầm như phép ép kiểu nguyên thu hẹp.

Với `long`:

```java
StringBuilder text = new StringBuilder("n=-9223372036854775808");
long min = Long.parseLong(text, 2, text.length(), 10);
System.out.println(min == Long.MIN_VALUE); // true
```

Nếu cần parse số nguyên lớn hơn miền `long`, sử dụng chiến lược số nguyên độ chính xác tùy ý thích hợp như `BigInteger`, nhưng **không có cùng overload phạm vi** trong `BigInteger` tương ứng với bốn phương thức này.

## 7. Cơ số khác 10: hexadecimal, binary và dấu

Truyền `radix` rõ ràng:

```java
StringBuilder line = new StringBuilder("hex=7F;bits=101011");

int hex = Integer.parseInt(line, 4, 6, 16);  // 127
int bits = Integer.parseInt(line, 12, 18, 2); // 43
```

Các ký tự được chấp nhận phải là chữ số hợp lệ theo `Character.digit(char, radix)`, ngoài dấu ASCII đầu đoạn trong signed parser. Điều này có nghĩa parser được JDK hỗ trợ cho nhiều radix và có thể chấp nhận một số chữ số Unicode, chứ **không tự giới hạn toàn bộ token về ASCII**.

Nếu giao thức của bạn yêu cầu **chỉ ký tự ASCII**, hãy validate quy tắc đó riêng. Không dùng việc `parseInt` thành công làm bằng chứng token hoàn toàn tuân thủ bộ ký tự ASCII của một giao thức.

### Không tự nhận tiền tố 0x

Với radix 16, đoạn được parse phải là các chữ số theo cơ số 16 (có thể có dấu đầu hợp lệ), ví dụ `"FF"` hoặc `"-FF"`, không tự cho phép chuỗi có tiền tố `"0x"`:

```java
StringBuilder s = new StringBuilder("value=0xFF");
// Integer.parseInt(s, 6, 10, 16); // NumberFormatException
int value = Integer.parseInt(s, 8, 10, 16); // 255
```

Ở đây `[8,10)` bỏ qua tiền tố `0x`. Khi một chuẩn giao thức cho phép nhiều prefix, bạn cần xác định/loại prefix ở bước phân tích token.

`Integer.decode(String)` hỗ trợ quy tắc prefix riêng, nhưng **không cung cấp overload `(CharSequence,begin,end,radix)`**. Nếu chọn cách parse vùng, người viết parser tự quyết định radix và phạm vi chữ số.

### Dấu gạch dưới và hậu tố L không phải cú pháp chuỗi số

`1_000` và `123L` có thể có ý nghĩa trong *numeric literal của mã nguồn Java* (tùy vị trí), nhưng không có nghĩa `Integer.parseInt`/`Long.parseLong` chấp nhận dấu `_` hoặc hậu tố `L` trong chuỗi decimal thông thường:

```java
// Integer.parseInt(new StringBuilder("1_000"), 0, 5, 10); // NFE
// Long.parseLong(new StringBuilder("123L"), 0, 4, 10);     // NFE
```

Hãy định nghĩa rõ cú pháp **dữ liệu runtime** thay vì lấy nguyên quy tắc numeric literal của mã nguồn Java.

## 8. Unsigned parse: số lớn hơn MAX_VALUE có thể hợp lệ theo 32/64 bit

Hai overload không dấu:

```java
Integer.parseUnsignedInt(seq, from, to, radix);
Long.parseUnsignedLong(seq, from, to, radix);
```

cho phép đọc các giá trị từ `0` đến `2^32−1` hoặc `0` đến `2^64−1`. Nhưng Java vẫn dùng kiểu kết quả là **`int` 32 bit** hoặc **`long` 64 bit**, không có primitive unsigned riêng.

Ví dụ giá trị lớn nhất:

```java
StringBuilder u32Text = new StringBuilder("u=4294967295");
int bits32 = Integer.parseUnsignedInt(
        u32Text, 2, u32Text.length(), 10);

System.out.println(bits32);                      // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
```

Lưu ý `System.out.println(bits32)` đọc các bit theo signed `int` nên in `-1`; điều đó **không chứng tỏ parser không dấu bị lỗi**. Cùng mẫu `0xFFFFFFFF` có nghĩa `4294967295` theo unsigned và `-1` theo signed.

Với 64 bit:

```java
StringBuilder u64Text =
        new StringBuilder("u=18446744073709551615");

long bits64 = Long.parseUnsignedLong(
        u64Text, 2, u64Text.length(), 10);

System.out.println(bits64);                    // -1
System.out.println(Long.toUnsignedString(bits64));
// 18446744073709551615
```

Unsigned parser không nhận số âm như một signed integer âm: dấu `-` ở đầu đoạn không phải giá trị unsigned hợp lệ. Dấu cộng ASCII đầu đoạn có thể được chấp nhận, nhưng đừng coi token `"-1"` là cách viết thay thế cho unsigned max.

Khi xử lý bit-pattern unsigned, các API `Integer.compareUnsigned`, `Long.compareUnsigned`, `Integer.divideUnsigned` và tương đương có thể cần thiết. **Đừng dùng so sánh signed `bits32 < 0` để kết luận giá trị unsigned là âm.**

## 9. Cơ chế xử lý lỗi: ba loại ngoại lệ cần tách biệt

Với overload `parseInt(CharSequence,int,int,int)` và các overload tương ứng của `Long`:

| Trường hợp | Ngoại lệ thường được xác định bởi API | Ví dụ |
| --- | --- | --- |
| `CharSequence` bằng `null` | `NullPointerException` | `Integer.parseInt(null,0,1,10)` |
| Chỉ số ngoài phạm vi hoặc đảo thứ tự | `IndexOutOfBoundsException` | `beginIndex=-1` |
| Khoảng rỗng, ký tự sai, radix sai, giá trị vượt miền | `NumberFormatException` | `[0,0)`; `"12x"`; radix 1; `"2147483648"` khi đọc signed int |

**Đặc biệt:** overloaded method dùng `String` khác overload dùng `CharSequence` về cách tài liệu quy định trường hợp `null`. Không đồng nhất chúng nếu API của bạn cần chuyển exception thành lỗi có mã riêng.

Một ví dụ minh họa:

```java
StringBuilder buffer = new StringBuilder("x=12A");

try {
    Integer.parseInt(buffer, 2, 5, 10);
} catch (NumberFormatException ex) {
    System.out.println("Invalid decimal token");
}
```

Nếu cả biên token lẫn dữ liệu có thể sai, hãy cân nhắc:

- Kiểm tra `beginIndex` và `endIndex` riêng để phát hiện parser nội bộ xác định sai token.
- Xử lý `NumberFormatException` như **dữ liệu số không hợp lệ** hoặc **ngoài miền**.
- Xử lý `NullPointerException` như thiếu dãy ký tự đầu vào nếu nghiệp vụ cho phép nguồn null.
- Không bắt mọi `RuntimeException` rồi trả 0: lỗi parser và số 0 thực là hai tình huống không nên trộn làm một.

Tránh in toàn bộ chuỗi chứa dữ liệu nhạy cảm vào log lỗi. Có thể ghi tên trường, chỉ số hoặc thông điệp khái quát thay vì log nguyên bản ghi.

## 10. Có cần trim khoảng trắng không?

Parser số nguyên không tự cắt khoảng trắng bao quanh token:

```java
StringBuilder data = new StringBuilder("n= 42 ");
 // Integer.parseInt(data, 2, data.length(), 10); // NFE
```

Nếu định dạng dữ liệu cho phép khoảng trắng ở hai đầu, ta có thể **dịch hai biên** trước khi parse mà không tạo `String` con.

Ví dụ cho khoảng trắng ASCII đơn giản:

```java
static int parseTrimmedAscii(CharSequence text, int from, int to) {
    while (from < to && text.charAt(from) == ' ') {
        from++;
    }
    while (to > from && text.charAt(to - 1) == ' ') {
        to--;
    }
    return Integer.parseInt(text, from, to, 10);
}
```

Đây là **phương thức minh họa**, chưa tự validate tất cả chỉ số; giả định caller truyền `0 <= from <= to <= text.length()`. Nó chỉ loại khoảng trắng ASCII `' '` theo quy ước cụ thể, không tự xử lý mọi Unicode whitespace. Nếu hợp đồng cho phép tab, CR/LF hoặc khoảng trắng Unicode khác, hãy bổ sung chính sách tường minh, ví dụ kiểm tra code point hoặc hàm phù hợp.

**Không tự ý trim** nếu giao thức yêu cầu token không có khoảng trắng; trong parser chính xác, việc nhận token sai có thể nghiêm trọng hơn tiết kiệm một lần cấp phát.

## 11. Không thay Parse API bằng một bộ parser thủ công nếu chưa cần

Một vòng lặp tính số trực tiếp qua `charAt` có vẻ đơn giản:

```java
int result = 0;
for (int i = from; i < to; i++) {
    result = result * 10 + (text.charAt(i) - '0');
}
```

Nhưng đoạn code minh họa này **không an toàn để đưa vào production**:

- không kiểm tra mọi ký tự có nằm trong `'0'..'9'` hay không;
- không hỗ trợ dấu `+`/`-`;
- không kiểm tra overflow khi nhân 10 và cộng chữ số;
- không kiểm tra trường hợp rỗng hoặc radix khác;
- không thực hiện quy tắc về `Character.digit` theo API Java;
- có thể chấp nhận đầu vào sai rồi âm thầm trả số không đáng tin.

Bốn overload có sẵn xử lý đúng ngữ nghĩa của parser chuẩn. Chỉ tự viết parser tối ưu chuyên biệt khi có **hợp đồng dữ liệu rõ ràng**, test overflow và đo benchmark trên workload cụ thể.

Nếu dữ liệu nằm trong `byte[]` UTF-8 thay vì `CharSequence`, các overload này **không parse trực tiếp byte array**. Khi đó cần decode sang ký tự hoặc dùng parser byte chuyên dụng đã kiểm định; không ép kiểu giả để truyền `byte[]` vào `CharSequence`.

## 12. Hiệu năng: giảm String trung gian nhưng không hứa zero allocation

So sánh về ý tưởng:

```java
StringBuilder builder = new StringBuilder("qty=12345;");
int from = 4, to = 9;

// Cách có chuỗi trung gian:
int a = Integer.parseInt(builder.substring(from, to));

// Cách dùng đoạn của CharSequence:
int b = Integer.parseInt(builder, from, to, 10);
```

Cả hai trả `12345`. Cách thứ hai **không yêu cầu gọi `substring`**; phương thức nhận trực tiếp dãy ký tự và biên. Điều này có thể tránh tạo đối tượng chuỗi con từ code gọi và hỗ trợ xử lý lặp trong parser.

Tuy vậy:

1. API không cam kết một số lượng cấp phát cụ thể dưới mọi implementation hoặc nhánh lỗi.
2. JIT có thể tối ưu các đối tượng trung gian trong một số workload; bản cũ chưa chắc luôn chậm hơn.
3. Việc tìm delimiter bằng `indexOf`/scan vẫn có chi phí và thuật toán có thể dominate thời gian parse.
4. Parser chạy trên `StringBuilder` mutable chia sẻ giữa threads cần bảo đảm tính nhất quán; “ít copy” không đồng nghĩa “thread-safe”.
5. Việc tạo `String` con đôi khi lại hợp lý khi cần giữ token lâu dài sau khi buffer gốc bị ghi đè hoặc tái sử dụng.

Muốn biết cải thiện bao nhiêu, dùng **JMH** hoặc benchmark Java được thiết kế đúng, kiểm tra allocation rate và throughput với dữ liệu thực. Tránh tự đo một vòng lặp nhỏ bằng `System.nanoTime()` rồi kết luận tuyệt đối vì dead-code elimination, warming, GC và JIT có thể làm kết quả sai lệch.

## 13. Xác định đúng phạm vi token: nội dung ngoài đoạn vẫn còn nguyên

Parser theo vùng chỉ đọc phạm vi bạn truyền. Ví dụ:

```java
StringBuilder line = new StringBuilder("A=123;B=oops;");
int n = Integer.parseInt(line, 2, 5, 10);
System.out.println(n); // 123
```

Chuỗi `"oops"` ở bên ngoài đoạn **không cần là số hợp lệ** vì parser không đọc tới đó. Đây là tính chất hữu ích khi có nhiều trường khác loại trong cùng bản ghi.

Ngược lại, nếu vị trí biên được tính sai, parser có thể:

- lấy cả dấu phân cách và ném `NumberFormatException`;
- bỏ dấu âm và đọc thành số dương sai về ngữ nghĩa;
- lấy sang ký tự trường kế tiếp;
- parse một đoạn chữ số **hợp lệ nhưng không phải token intended**, nguy hiểm hơn lỗi parse rõ ràng.

Vì vậy phần **tokenization** (tìm vị trí bắt đầu/kết thúc trường) phải được thiết kế và kiểm thử độc lập với phần **numeric conversion** (đổi token hợp lệ thành số). Một overload parse tốt không thay thế được parser của cả giao thức.

## 14. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`CharSequenceRangeParsingDemo.java`**:

```java
public class CharSequenceRangeParsingDemo {

    private static int beginAfter(StringBuilder source, String field) {
        int keyIndex = source.indexOf(field);
        if (keyIndex < 0) {
            throw new IllegalArgumentException("Missing field: " + field);
        }
        return keyIndex + field.length();
    }

    private static int endOfField(StringBuilder source, int begin) {
        int separator = source.indexOf(";", begin);
        return separator >= 0 ? separator : source.length();
    }

    public static void main(String[] args) {
        StringBuilder record = new StringBuilder(
                "id=12345;delta=-42;hex=7F;u32=4294967295;"
              + "u64=18446744073709551615");

        int start = beginAfter(record, "id=");
        int end = endOfField(record, start);
        int id = Integer.parseInt(record, start, end, 10);
        System.out.println("id = " + id);

        start = beginAfter(record, "delta=");
        end = endOfField(record, start);
        int delta = Integer.parseInt(record, start, end, 10);
        System.out.println("delta = " + delta);

        start = beginAfter(record, "hex=");
        end = endOfField(record, start);
        int hex = Integer.parseInt(record, start, end, 16);
        System.out.println("hex = " + hex);

        start = beginAfter(record, "u32=");
        end = endOfField(record, start);
        int u32 = Integer.parseUnsignedInt(record, start, end, 10);
        System.out.println("u32 signed view = " + u32);
        System.out.println("u32 unsigned view = "
                + Integer.toUnsignedString(u32));

        start = beginAfter(record, "u64=");
        end = endOfField(record, start);
        long u64 = Long.parseUnsignedLong(record, start, end, 10);
        System.out.println("u64 signed view = " + u64);
        System.out.println("u64 unsigned view = "
                + Long.toUnsignedString(u64));

        StringBuilder signedLong =
                new StringBuilder("n=-9223372036854775808");
        long min = Long.parseLong(
                signedLong, 2, signedLong.length(), 10);
        System.out.println("long minimum = " + min);

        try {
            Integer.parseInt(new StringBuilder("x=12A"), 2, 5, 10);
        } catch (NumberFormatException ex) {
            System.out.println("bad digits: rejected");
        }

        try {
            Integer.parseInt(new StringBuilder("x=1"), -1, 3, 10);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("bad range: rejected");
        }

        try {
            Integer.parseInt(
                    new StringBuilder("n=2147483648"), 2, 12, 10);
        } catch (NumberFormatException ex) {
            System.out.println("signed int overflow: rejected");
        }

        StringBuilder extra = new StringBuilder("A=123;B=oops;");
        int first = Integer.parseInt(extra, 2, 5, 10);
        System.out.println("first field = " + first);
    }
}
```

Lưu tệp bằng đúng tên lớp, sau đó biên dịch và chạy:

```bash
javac CharSequenceRangeParsingDemo.java
java CharSequenceRangeParsingDemo
```

**Kết quả chuẩn:**

```text
id = 12345
delta = -42
hex = 127
u32 signed view = -1
u32 unsigned view = 4294967295
u64 signed view = -1
u64 unsigned view = 18446744073709551615
long minimum = -9223372036854775808
bad digits: rejected
bad range: rejected
signed int overflow: rejected
first field = 123
```

**Phân tích:**

- `id`, `delta`, `hex` được parse từ các vùng trong một `StringBuilder` mà không tạo `String` con cho từng trường số.
- `u32`, `u64` minh họa cùng bit pattern có thể in ra `-1` khi đọc signed, nhưng có giá trị unsigned max khi dùng `toUnsignedString`.
- `Long.parseLong` chấp nhận `Long.MIN_VALUE` chính xác, không yêu cầu đổi qua `double` hay `BigInteger`.
- Ký tự không hợp lệ gây `NumberFormatException`; biên chỉ số sai gây `IndexOutOfBoundsException`; signed overflow cũng gây `NumberFormatException`.
- Trường `B=oops` nằm ngoài phạm vi parse của trường `A` nên không ảnh hưởng đến kết quả `123`.

**Phạm vi minh họa:** Hàm `beginAfter` ở ví dụ dùng `StringBuilder.indexOf` để đơn giản hóa. Nó **không phải parser key/value production hoàn chỉnh**: nếu tên trường bị lặp, trùng một phần hoặc xuất hiện bên trong giá trị khác, cách tìm đơn thuần có thể chọn sai. Ứng dụng thực tế phải token hóa theo delimiter và kiểm tra tên trường đầy đủ.

## 15. Lỗi phổ biến khi tối ưu parse số nguyên

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`parseInt` chỉ nhận String” | Java 9+ có overload nhận `CharSequence` và phạm vi |
| “Chỉ cần truyền `sequence, from, to`” | Overload này yêu cầu thêm `radix` |
| “`endIndex` là vị trí ký tự cuối cùng” | `endIndex` là **exclusive**, không bao gồm ký tự đó |
| “`beginIndex == endIndex` là chỉ số sai” | Phạm vi rỗng có thể hợp lệ về chỉ số nhưng không parse được số |
| “Parser tự bỏ khoảng trắng” | Phải loại bỏ hoặc từ chối theo đặc tả của dữ liệu |
| “`radix=16` tự hiểu tiền tố 0x” | Không; phải xác định prefix và phạm vi chữ số riêng |
| “Chuỗi numeric runtime hiểu dấu gạch dưới như Java literal” | `"1_000"` thường không được parse bằng overload này |
| “Unsigned parse sẽ trả số dương với kiểu int/long” | Vẫn trả bit pattern của `int`/`long`, có thể in ra giá trị signed âm |
| “StringBuilder truyền vào sẽ được parser snapshot an toàn” | JDK không tự bảo vệ khi CharSequence bị sửa trong lúc parse |
| “Không gọi substring là zero allocation” | Chỉ tránh bước tạo chuỗi con ở phía caller; không bảo đảm cấp phát bằng 0 |
| “Bắt NumberFormatException đủ cho mọi lỗi” | Null và chỉ số sai là các loại ngoại lệ riêng |
| “Tính đúng token tự đến từ parser số” | Vẫn phải xác định begin/end đúng với giao thức |
| “Nhận thành công nghĩa là token chỉ gồm ASCII” | JDK có quy tắc `Character.digit`, có thể chấp nhận một số chữ số ngoài ASCII |
| “Mọi lớp wrapper parse đều có overload giống nhau” | Chữ ký của từng API khác nhau; kiểm tra Javadoc |

## 16. Bài tập tự kiểm tra

**Bài 1.** Với `StringBuilder s = new StringBuilder("x=987;y=1");`, viết lệnh parse `987` không tạo `String` con.

**Bài 2.** `Integer.parseInt(s, 2, 5, 10)` đọc những chỉ số nào?

**Bài 3.** Với `StringBuilder s = new StringBuilder("n=-42;");`, kết quả của `Integer.parseInt(s, 2, 5, 10)` và `Integer.parseInt(s, 3, 5, 10)` lần lượt là gì?

**Bài 4.** Vì sao `Integer.parseInt(new StringBuilder("h=0xFF"), 2, 6, 16)` thất bại? Cách sửa không tạo `String` con?

**Bài 5.** Với `StringBuilder s = new StringBuilder("u=4294967295");`, `Integer.parseUnsignedInt(s, 2, s.length(), 10)` trả kiểu gì, và in ra thế nào để được `4294967295`?

**Bài 6.** Một token có dấu cách đầu/cuối. Có thể gọi trực tiếp `parseInt` trên toàn phạm vi rồi mong parser tự trim không?

**Bài 7.** Trường hợp nào là `IndexOutOfBoundsException`: `begin=-1` hay đoạn hợp lệ nhưng chứa chữ `A` khi radix 10? Trường hợp còn lại là lỗi gì?

**Bài 8.** Vì sao dùng `Integer.parseInt(builder,from,to,10)` chưa tự chứng minh chương trình chạy nhanh hơn phiên bản dùng `substring`?

**Bài 9.** `Long.parseUnsignedLong` đọc `18446744073709551615` thành `long` có mẫu bit nào? Khi in thông thường và khi dùng `Long.toUnsignedString` khác thế nào?

**Bài 10.** Có an toàn nếu thread A sửa `StringBuilder` trong lúc thread B gọi `Integer.parseInt(builder,...)` không?

### Đáp án và giải thích

1. `Integer.parseInt(s, 2, 5, 10)`. Phạm vi `[2,5)` là `987`.
2. Đọc chỉ số `2, 3, 4`; không đọc ký tự tại chỉ số 5.
3. Lần lượt `-42` và `42`; phiên bản bắt đầu ở chỉ số 3 đã bỏ dấu `-`, gây sai ý nghĩa.
4. Token `"0xFF"` chứa `x` không phải digit radix 16; sửa bằng `Integer.parseInt(s, 4, 6, 16)` để đọc `FF`.
5. Trả primitive `int` với 32 bit đều bằng 1, khi in signed là `-1`; dùng `Integer.toUnsignedString(result)` để in `4294967295`.
6. Không. Cần xác định chính sách có chấp nhận whitespace không; nếu có thì điều chỉnh biên trước khi parse.
7. `begin=-1` gây `IndexOutOfBoundsException`; ký tự `A` không hợp radix 10 gây `NumberFormatException`.
8. JIT, cách xác định token, xử lý lỗi và đặc tính dữ liệu đều ảnh hưởng. Phương pháp theo vùng giảm yêu cầu tạo `String` con tại caller, nhưng muốn kết luận hiệu năng phải benchmark phù hợp.
9. Mẫu 64 bit đều là 1, giá trị signed `long=-1`; `Long.toUnsignedString(result)` in `18446744073709551615`.
10. Không có bảo đảm snapshot/nhất quán do parser tự cung cấp. Cần đồng bộ, không sửa trong quá trình parse hoặc chuyển quyền sở hữu bộ đệm theo giao thức phù hợp.

## 17. Checklist trước khi dùng overload CharSequence

1. **Xác định đầu vào thực tế**: `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` hay một implementation custom?
2. **Chọn đúng API**: `Integer` hay `Long`, signed hay unsigned? Có đúng overload `(CharSequence,begin,end,radix)` không?
3. **Giữ đúng biên**: `0 <= begin <= end <= length`, `end` exclusive, dấu âm/dương đầu token không bị bỏ.
4. **Chỉ số tính theo ký tự của nguồn**: đừng truyền byte offset của UTF-8 vào `CharSequence`.
5. **Chọn radix và chính sách prefix** rõ ràng; không mặc định parser radix 16 chấp nhận `0x`.
6. **Định nghĩa whitespace và ký tự hợp lệ**: cần ASCII-only hay chấp nhận các digit Unicode theo `Character.digit`?
7. **Rà soát miền số**: `int`, `long` có dấu/không dấu; giá trị ngoài miền là lỗi parse, không âm thầm wrap khi parse signed.
8. **Xử lý exception**: null, chỉ số sai, dữ liệu/radix/overflow sai là các loại lỗi khác nhau.
9. **Bảo đảm tính nhất quán**: tránh sửa mutable `CharSequence` đồng thời khi parse.
10. **Kiểm chứng hiệu năng** bằng benchmark nếu đây là tối ưu hot path; không hứa zero allocation hoặc lợi ích tuyệt đối.
11. **Giữ token khi cần**: nếu logic phải lưu lại giá trị văn bản sau khi buffer tái sử dụng, copy token theo yêu cầu vòng đời dữ liệu là hợp lý.
12. **Kiểm thử dữ liệu biên**: chuỗi rỗng, dấu không chữ số, ±MAX/MIN, unsigned max, token có dấu phân cách, prefix, khoảng trắng, radix lỗi và chỉ số ngoài phạm vi.

## Tài liệu API

- [Java 17 – Integer: parseInt và parseUnsignedInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [Java 17 – Long: parseLong và parseUnsignedLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html)

**Ghi nhớ:** Khi đã có `CharSequence` và biết `beginIndex/endIndex` của một trường số, hãy ưu tiên overload parse trực tiếp trên **đoạn ký tự** nếu API hỗ trợ. Cách này giúp tránh tạo `String` con không cần thiết, nhưng vẫn phải đảm bảo **đúng chỉ số, radix, miền giá trị, signedness, tính nhất quán của dữ liệu và ngữ nghĩa lỗi**. Tiết kiệm cấp phát chỉ có ích khi giá trị được phân tích **đúng**.

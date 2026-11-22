# String.chars(): các đơn vị char UTF-16 được mở rộng thành int

## 1. String.chars() là gì?

Trong Java, `String.chars()` tạo ra một `IntStream` lần lượt chứa **giá trị của từng đơn vị mã UTF-16 (`char`)** trong chuỗi. Mỗi giá trị `char` được **mở rộng thành `int` bằng zero-extension**: các bit phía trên được điền bằng 0, nên giá trị số giữ nguyên và nằm trong khoảng 0–65.535.

Chữ ký có thể nhìn từ `CharSequence` (Java 9+):

~~~java
IntStream chars()
~~~

Ví dụ đơn giản:

~~~java
String s = "ABC";
int[] units = s.chars().toArray();
// [65, 66, 67]
~~~

Kết quả là `int[]` bởi vì `chars()` trả về `IntStream`, dù từng giá trị đại diện cho một đơn vị `char`. Với chuỗi `"ABC"`, mã UTF-16 của `'A'`, `'B'` và `'C'` lần lượt là 65, 66, 67 nên ta thấy ba số nguyên đó.

**Điểm phải nhớ:** `chars()` không hứa trả về từng ký tự Unicode hoàn chỉnh (*Unicode code point*) và không tự giải mã cặp surrogate. Nó lần lượt lấy đúng từng đơn vị UTF-16 có trong chuỗi, chuyển giá trị của đơn vị đó từ `char` (16 bit không dấu) sang `int` (32 bit có dấu nhưng giá trị vẫn không âm).

## 2. Vì sao một char và một ký tự Unicode có thể khác nhau?

Java biểu diễn `String` bằng một dãy đơn vị mã UTF-16. Một `char` có độ rộng 16 bit, nhưng tập mã Unicode có các code point lớn hơn phạm vi 16 bit.

- Các code point thuộc **BMP** (Basic Multilingual Plane), ngoại trừ vùng dành riêng cho surrogate, được biểu diễn bằng một đơn vị UTF-16. Ví dụ chữ `A` (`U+0041`) và chữ `á` (`U+00E1`).
- Các code point **ngoài BMP**, từ `U+10000` đến `U+10FFFF`, cần **hai đơn vị UTF-16**: một *high surrogate* thuộc `U+D800..U+DBFF` và một *low surrogate* thuộc `U+DC00..U+DFFF`.
- Một đơn vị surrogate riêng lẻ **không phải** Unicode scalar value hoàn chỉnh. Trong `String` vẫn có thể tồn tại surrogate lẻ; `chars()` sẽ phát ra nguyên giá trị đơn vị đó.

Ví dụ chuỗi hiển thị `A😀B`, trong đó emoji `😀` có code point `U+1F600`:

| Vị trí `char` (chỉ số UTF-16) | Giá trị hex của đơn vị UTF-16 | Giá trị thập phân `int` | Ý nghĩa |
|---|---|---|---|
| 0 | `0041` | 65 | `A` |
| 1 | `D83D` | 55.357 | High surrogate của `😀` |
| 2 | `DE00` | 56.832 | Low surrogate của `😀` |
| 3 | `0042` | 66 | `B` |

Do đó:

~~~java
String s = "A\uD83D\uDE00B"; // A😀B
System.out.println(s.length());        // 4 đơn vị UTF-16
System.out.println(s.chars().count()); // 4 phần tử int
System.out.println(s.codePoints().count()); // 3 code point
~~~

Số phần tử của `chars()` bằng số đơn vị UTF-16 trong `String`, tức bằng `s.length()`. Đừng suy ra “4 ký tự người đọc nhìn thấy” từ kết quả đó: cách đếm đơn vị UTF-16, Unicode code point và ký tự hiển thị trên giao diện có thể cho các kết quả khác nhau.

## 3. Cơ chế mở rộng char thành int

`char` là kiểu nguyên thủy 16 bit **không dấu**. Khi mở rộng `char` thành `int`, Java giữ 16 bit thấp và đặt các bit còn lại bằng 0 (*zero-extension*); đây không phải chuyển đổi có dấu (*sign-extension*).

~~~java
char ch = '\u00E1';           // á, mã U+00E1
int asInt = ch;               // 225
int viaStream = "á".chars().findFirst().orElseThrow();
// viaStream == 225
~~~

Với `'A'`, phép chuyển đổi có thể hình dung như:

~~~text
char: 0000 0000 0100 0001   (0x0041, 65)
int : 0000 0000 0000 0000 0000 0000 0100 0001   (0x00000041, 65)
~~~

Với một đơn vị surrogate có bit cao bật, `int` sau khi mở rộng **vẫn là số dương**, ví dụ `0xD83D` thành `55357`; không trở thành một số nguyên âm.

Vì đây là mở rộng giá trị của một đơn vị `char`, **nó không biến hai `char` của emoji thành một code point**. Muốn kết hợp đúng một cặp surrogate hợp lệ thành code point, cần cơ chế đọc code point như `codePoints()` hoặc API `Character`.

## 4. So sánh chars(), codePoints(), charAt() và length()

| API | Kết quả | Đơn vị xử lý | Trường hợp phù hợp |
|---|---|---|---|
| `s.chars()` | `IntStream` | Từng đơn vị UTF-16, mở rộng thành `int` | Kiểm tra/xử lý trực tiếp các code unit; thao tác luồng với text ASCII/BMP theo yêu cầu đã rõ |
| `s.codePoints()` | `IntStream` | Mỗi cặp surrogate hợp lệ được kết hợp thành một code point | Xử lý Unicode code point, đặc biệt khi có chữ hoặc emoji ngoài BMP |
| `s.charAt(i)` | `char` | Một đơn vị UTF-16 ở chỉ số `i` | Truy cập trực tiếp code unit theo chỉ số |
| `s.length()` | `int` | Số đơn vị UTF-16 | Kiểm tra độ dài lưu trữ logic của chuỗi theo `char` |
| `s.codePointCount(0, s.length())` | `int` | Số code point trong đoạn UTF-16 chỉ định | Đếm code point, tính cặp surrogate hợp lệ là một |

Đối với `"A\uD83D\uDE00B"`:

~~~text
UTF-16 code units:  0041 | D83D | DE00 | 0042   → 4 phần tử
Unicode code points: U+0041 | U+1F600 | U+0042  → 3 phần tử
~~~

`chars()` và `codePoints()` cùng trả `IntStream` nhưng giá trị của các phần tử có **ngữ nghĩa khác nhau**. Kiểu `int` tự nó không nói rõ đang chứa code unit hay code point; tên biến và API nguồn giúp tránh nhầm lẫn.

Lưu ý đặc biệt: `codePoints()` chỉ kết hợp **cặp high/low surrogate hợp lệ**. Nếu chuỗi chứa một surrogate không ghép cặp, phương thức có thể phát ra giá trị surrogate đó dưới dạng một `int` riêng; nó không tự làm sạch dữ liệu lỗi hay thay bằng ký tự thay thế `U+FFFD`.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Tạo tệp **`StringCharsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

public class StringCharsDemo {
    public static void main(String[] args) {
        // A + 😀 + B. Emoji U+1F600 được mã hóa bằng hai char UTF-16.
        String text = "A\uD83D\uDE00B";

        System.out.println("length = " + text.length());
        System.out.println("chars count = " + text.chars().count());
        System.out.println("chars decimal = "
                + Arrays.toString(text.chars().toArray()));

        String unitsHex = text.chars()
                .mapToObj(unit -> String.format(Locale.ROOT, "%04X", unit))
                .collect(Collectors.joining(" "));
        System.out.println("chars hex = " + unitsHex);

        String pointsHex = text.codePoints()
                .mapToObj(point -> String.format(Locale.ROOT, "U+%04X", point))
                .collect(Collectors.joining(" "));
        System.out.println("code points hex = " + pointsHex);

        System.out.println("code point count = "
                + text.codePoints().count());

        System.out.println("high surrogate = "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("low surrogate = "
                + Character.isLowSurrogate(text.charAt(2)));

        long countA = "banana".chars()
                .filter(unit -> unit == 'a')
                .count();
        System.out.println("count a = " + countA);

        String reconstructed = text.codePoints()
                .collect(
                        StringBuilder::new,
                        StringBuilder::appendCodePoint,
                        StringBuilder::append
                )
                .toString();
        System.out.println("round trip = " + text.equals(reconstructed));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringCharsDemo.java
java StringCharsDemo
~~~

Kết quả:

~~~text
length = 4
chars count = 4
chars decimal = [65, 55357, 56832, 66]
chars hex = 0041 D83D DE00 0042
code points hex = U+0041 U+1F600 U+0042
code point count = 3
high surrogate = true
low surrogate = true
count a = 3
round trip = true
~~~

Giải thích:

1. `length()` và `chars().count()` đều là **4** vì emoji chiếm hai code unit.
2. `chars().toArray()` tạo **`int[]`**: `[65, 55357, 56832, 66]`. Hai số giữa biểu diễn hai nửa UTF-16 của emoji.
3. `mapToObj(...)` chuyển từng số thành chuỗi hex; `Collectors.joining(" ")` ghép các phần thành một dòng dễ đọc.
4. `codePoints()` kết hợp hai surrogate hợp lệ thành `U+1F600`, nên chỉ có **3** code point.
5. `Character.isHighSurrogate` và `Character.isLowSurrogate` xác minh hai đơn vị ở chỉ số 1 và 2.
6. Bộ lọc `unit == 'a'` có kết quả 3 với `banana`, vì chữ `a` thuộc BMP và được biểu diễn bằng đúng một đơn vị UTF-16.
7. `StringBuilder.appendCodePoint` bổ sung code point trở lại chuỗi UTF-16 hợp lệ; vì dữ liệu đầu vào có cặp surrogate hợp lệ, phép tạo lại cho chuỗi đúng bằng ban đầu.

Trong code, `StringBuilder::appendCodePoint` được dùng với `IntStream.collect` để cộng dồn code point, còn `StringBuilder::append` dùng để kết hợp các bộ đệm khi cần.

## 6. Những thao tác trực tiếp với IntStream

### 6.1. Duyệt các đơn vị char

~~~java
String s = "ABC";
s.chars().forEachOrdered(unit -> System.out.println(unit));
// 65
// 66
// 67
~~~

Vì nguồn có thứ tự, `forEachOrdered` bảo toàn thứ tự duyệt, kể cả khi chuyển stream sang chế độ song song. `forEach` trên stream song song không bảo đảm thứ tự thực hiện giữa các phần tử.

### 6.2. Lọc và đếm

~~~java
long digits = "a1b23".chars()
        .filter(unit -> unit >= '0' && unit <= '9')
        .count();
// digits == 3
~~~

Mẫu này chủ động kiểm tra **chữ số ASCII** `'0'` đến `'9'`. Nếu cần hỗ trợ chữ số thuộc nhiều hệ chữ Unicode, hãy cân nhắc `codePoints().filter(Character::isDigit)` theo quy tắc nghiệp vụ; không đồng nhất “ASCII digit” với “mọi ký tự được Unicode xem là chữ số”.

### 6.3. Tạo danh sách giá trị nguyên hoặc tổng hợp

~~~java
int[] values = "ABC".chars().toArray();
// [65, 66, 67]

int total = "ABC".chars().sum();
// 198
~~~

`sum()` chỉ cộng giá trị số của các đơn vị UTF-16; nó **không tạo một số đo ý nghĩa văn bản**. Các phép tính số học trên code unit nên được sử dụng khi bài toán thực sự yêu cầu những giá trị đó, ví dụ kiểm tra mã ký tự trong phạm vi ASCII.

### 6.4. Chuyển giá trị code unit thành chuỗi để hiển thị

~~~java
String hex = "Az".chars()
        .mapToObj(unit -> String.format(Locale.ROOT, "%04X", unit))
        .collect(Collectors.joining(", "));
// "0041, 007A"
~~~

`mapToObj` chuyển `IntStream` thành `Stream<String>`; sau đó `Collectors.joining` ghép các chuỗi. Cách này phù hợp để hiển thị **giá trị code unit**. Nếu muốn hiện từng code point Unicode thành ký tự tương ứng, hãy dùng `codePoints()` và chuyển code point thành chuỗi bằng `Character.toChars(cp)`.

Các stream là **một lần sử dụng**: sau khi đã gọi terminal operation như `count()`, `toArray()` hoặc `forEachOrdered()`, không dùng lại cùng đối tượng stream. Nếu muốn chạy phép tính khác, gọi `s.chars()` lần nữa.

## 7. Vì sao không nên ép mọi int từ chars() thành “một ký tự Unicode”?

Đối với ASCII/BMP thông thường, đoạn sau có vẻ hoạt động:

~~~java
String value = "ABC";
value.chars().forEachOrdered(unit -> {
    char c = (char) unit;
    System.out.print(c);
});
// ABC
~~~

Nhưng với dữ liệu chứa emoji ngoài BMP, mỗi lần ép `(char) unit` vẫn chỉ tạo **một nửa surrogate**. Việc xử lý, kiểm tra, xóa hoặc phát từng nửa như một ký tự độc lập có thể làm hỏng cặp surrogate:

~~~java
String emoji = "\uD83D\uDE00"; // 😀
int[] units = emoji.chars().toArray();
// [55357, 56832]

// units[0] là high surrogate; nó không phải emoji hoàn chỉnh.
boolean high = Character.isHighSurrogate((char) units[0]); // true
~~~

Nếu cần đi qua từng Unicode code point và chuyển trở lại chuỗi, hãy dùng:

~~~java
String source = "A\uD83D\uDE00B";
String joined = source.codePoints()
        .mapToObj(cp -> new String(Character.toChars(cp)))
        .collect(Collectors.joining());
// joined.equals(source) == true, với nguồn có code point hợp lệ
~~~

`Character.toChars(cp)` chuyển một code point hợp lệ thành một hoặc hai `char` UTF-16 đúng quy tắc. Với surrogate lẻ do `codePoints()` phát ra, `Character.toChars(cp)` vẫn có thể trả về chính một đơn vị surrogate vì giá trị này nằm trong phạm vi code point mà API chấp nhận; nó **không** xác thực hay sửa Unicode lỗi. Nếu đầu ra phải gồm các Unicode scalar value hợp lệ, hãy phát hiện rồi từ chối hoặc thay thế surrogate lẻ theo hợp đồng ứng dụng.

Nếu ứng dụng cần cắt chuỗi theo vị trí code point thay vì vị trí UTF-16, đừng tự tăng chỉ số `char` đúng 1 sau mọi phần tử. Có thể sử dụng `offsetByCodePoints(...)` để chuyển chỉ số code point thành chỉ số UTF-16:

~~~java
String s = "A\uD83D\uDE00B";
int from = s.offsetByCodePoints(0, 1); // chỉ số UTF-16: 1
int to = s.offsetByCodePoints(0, 2);   // chỉ số UTF-16: 3
String secondCodePoint = s.substring(from, to); // 😀
~~~

Trong ví dụ trên, `s.substring(1, 2)` chỉ lấy high surrogate và tạo chuỗi có surrogate lẻ; muốn lấy trọn emoji phải lấy đoạn UTF-16 `[1,3)`.

## 8. Đếm code unit, code point và ký tự người dùng thấy

Ba cách đếm thường bị lẫn:

| Khái niệm | Đếm gì? | Công cụ liên quan |
|---|---|---|
| Đơn vị UTF-16 (code unit) | Từng `char` 16 bit | `length()`, `chars().count()` |
| Unicode code point | Mỗi mã điểm; cặp surrogate hợp lệ tính là một | `codePoints().count()`, `codePointCount(...)` |
| Grapheme cluster (*ký tự cảm nhận*) | Nhóm code point hiển thị như một đơn vị người dùng nhận thấy | Bộ phân đoạn văn bản Unicode phù hợp, ví dụ API phân tách theo grapheme cluster |

Một chữ có dấu có thể được mã hóa bằng **một code point dựng sẵn** hoặc **chữ nền cộng dấu kết hợp**; hai cách có thể nhìn gần giống nhau nhưng đếm số code point khác nhau. Emoji có modifier, dấu nối zero-width joiner hoặc cờ quốc gia cũng có thể gồm nhiều code point nhưng hiển thị như một hình.

Vì vậy:

- `chars().count()` **không** phải luôn là số ký tự Unicode.
- `codePoints().count()` cũng **không** chắc bằng số ký tự người dùng nhìn thấy.
- Khi xây dựng giao diện (giới hạn số ký tự người dùng nhập, cắt tên hiển thị, chọn vị trí con trỏ), phải định nghĩa rõ đơn vị cần đếm và chọn bộ phân đoạn tương ứng.

Đây là hệ quả trực tiếp của cách Java dùng UTF-16 trong `String`, chứ không phải lỗi riêng của `chars()`.

## 9. Một số lưu ý về API và hiệu năng

**`IntStream` là primitive stream.** Từ `chars()` nhận được `IntStream`, không phải `Stream<Character>`. Nếu cần `int[]`, gọi `toArray()`; nếu cần stream của đối tượng, dùng `mapToObj` hoặc `boxed()` khi thực sự cần. Việc boxing thành `Integer` có thể tạo thêm chi phí so với duy trì kiểu nguyên thủy.

**`chars()` không thay đổi `String`.** `String` là bất biến; `filter`, `map`, `count` chỉ tạo pipeline hoặc tính kết quả. Các phép trung gian như `filter()` có tính lười (*lazy*), thường chỉ được thực thi khi gọi terminal operation như `count()`.

**Tránh tạo stream nếu mục tiêu là đọc một đơn vị ở chỉ số cố định.** `s.charAt(i)` rõ ràng hơn cho phép đọc một code unit. Với các tác vụ duyệt đơn giản hoặc cần phối hợp chỉ số UTF-16, vòng lặp `for (int i = 0; i < s.length(); i++)` có thể dễ kiểm soát hơn; lựa chọn nào nhanh hơn phải đo trong ngữ cảnh thực tế.

**Không giả định mỗi int chứa một “ký tự đầy đủ”.** Đây là vấn đề đúng/sai của Unicode, không chỉ hiệu năng. Việc dùng `codePoints()` từ đầu giúp tránh vô tình tách đôi ký tự ngoài BMP.

**Không dùng stream đã kết thúc.** Ví dụ:

~~~java
var stream = "ABC".chars();
long size = stream.count();  // 3
// stream.sum(); // Sai: stream đã được tiêu thụ
int sum = "ABC".chars().sum(); // Tạo stream mới, kết quả 198
~~~

**Lưu ý chuỗi rỗng và null.** `"".chars()` là stream rỗng, nên `count()` trả 0 và `toArray()` trả mảng rỗng. Gọi `chars()` trên tham chiếu `String` bằng `null` sẽ gây `NullPointerException`; nếu đầu vào có thể null, hãy quyết định cách xử lý trước khi tạo stream.

## 10. Sai lầm phổ biến và cách sửa

1. **Đọc `chars()` là “stream các code point”.** Không đúng: đầu ra là các code unit UTF-16 đã nâng kiểu lên `int`. Với ký tự ngoài BMP, số phần tử sẽ lớn hơn số code point. **Sửa:** dùng `codePoints()` nếu yêu cầu là Unicode code point.
2. **Nghĩ `toArray()` sẽ tạo `char[]`.** `IntStream.toArray()` trả `int[]`. Nếu cần mảng `char[]` chứa các code unit, dùng `s.toCharArray()`.
3. **Ép `(char)` cho một int rồi giả định đó là một ký tự người dùng nhìn thấy.** Một surrogate có thể chỉ là nửa của code point. **Sửa:** xử lý theo cặp hoặc dùng `codePoints()` và `Character.toChars()`.
4. **Sử dụng `length()` để giới hạn “số ký tự nhìn thấy”.** `length()` đếm các code unit UTF-16. **Sửa:** xác định yêu cầu là code unit, code point hay grapheme cluster trước.
5. **Cắt chuỗi theo chỉ số UTF-16 ngay giữa cặp surrogate.** Điều này tạo chuỗi chứa surrogate lẻ. **Sửa:** xác định ranh giới code point với `offsetByCodePoints()` hoặc API phù hợp.
6. **Tái sử dụng `IntStream` sau terminal operation.** Stream chỉ được tiêu thụ một lần. **Sửa:** gọi lại `s.chars()` hoặc lưu kết quả cần tái sử dụng.
7. **Dùng một phép kiểm tra ASCII để xử lý mọi hệ chữ.** Ví dụ so sánh `'0' <= unit && unit <= '9'` chỉ nhận chữ số ASCII. **Sửa:** dùng thuật toán theo code point và quy tắc Unicode khi thực sự muốn hỗ trợ nhiều hệ chữ.
8. **Cho rằng `codePoints()` tự sửa surrogate lẻ hoặc tính luôn grapheme cluster.** Cả hai đều sai. **Sửa:** kiểm tra dữ liệu Unicode không hợp lệ và chọn bộ phân đoạn grapheme khi yêu cầu liên quan ký tự hiển thị.

## 11. Tự kiểm tra nhanh

**Câu 1.** `"Java".chars().count()` trả bao nhiêu? — **4**, vì mỗi chữ Latin ở đây chiếm một đơn vị UTF-16.

**Câu 2.** Với `String s = "\uD83D\uDE00";`, `s.chars().count()` và `s.codePoints().count()` trả bao nhiêu? — Lần lượt **2** và **1**: emoji dùng một cặp surrogate nhưng là một code point.

**Câu 3.** `"A".chars().toArray()` cho kiểu dữ liệu nào? — **`int[]`**, chứa giá trị `65`, bởi nguồn là `IntStream`.

**Câu 4.** Nếu cần in mã điểm Unicode `U+1F600` của emoji, nên bắt đầu từ API nào? — **`codePoints()`**; `chars()` phát ra riêng `D83D` và `DE00`.

**Câu 5.** `String.chars()` có tự đổi chuỗi gốc hay trả từng `Character` object không? — **Không** ở cả hai ý: chuỗi là bất biến và luồng chứa giá trị `int` nguyên thủy.

## 12. Ghi nhớ

`String.chars()` là công cụ duyệt **đơn vị `char` UTF-16**, sau khi **zero-extend** từng giá trị thành `int` trong `IntStream`. Phương thức phù hợp khi bài toán muốn thao tác ở mức code unit, hoặc trên dữ liệu ASCII/BMP với giả định được làm rõ. Khi bài toán cần xử lý **code point Unicode**, nhất là văn bản có emoji hay ký tự ngoài BMP, hãy chọn `String.codePoints()`. Khi bài toán cần “một ký tự mà người dùng nhìn thấy”, cả hai cách đếm trên có thể chưa đủ và cần xử lý grapheme cluster.

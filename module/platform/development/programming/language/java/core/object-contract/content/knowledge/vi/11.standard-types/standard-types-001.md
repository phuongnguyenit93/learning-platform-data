# `String.equals()` so sánh nội dung và không phụ thuộc danh tính

## 1. Phân biệt giá trị văn bản và danh tính tham chiếu

Trong Java, biến `String` chứa **tham chiếu** đến một đối tượng chuỗi. Vì thế, hai phép kiểm tra sau trả lời hai câu hỏi khác nhau:

- **`a == b`** với hai tham chiếu: hai biến có trỏ tới **cùng một đối tượng** không? Đây là kiểm tra danh tính tham chiếu (*reference identity*), không phải phép so sánh nội dung.
- **`a.equals(b)`**: hai đối tượng có cùng **nội dung `String`** không, bất kể chúng nằm ở hai đối tượng riêng?

Hai `String` khác đối tượng vẫn có thể `a == b` là `false` và `a.equals(b)` là `true`. Ngược lại, nếu `a == b` và `a` không `null`, `a.equals(b)` tất nhiên đúng vì đó là cùng đối tượng.

`String` là một lớp `final` với giá trị bất biến (*immutable*). Mã khác không thể kế thừa `String` để thay đổi cách `equals` hoạt động, và nội dung của một đối tượng `String` không thay đổi sau khi tạo. Đây là lý do nó thích hợp làm khóa của `HashMap` hoặc phần tử trong `HashSet`.

**Phạm vi của `equals`:** hai đối tượng có cùng nội dung chuỗi không đồng nghĩa chúng biểu thị cùng người, cùng tài khoản, cùng bản ghi hay cùng đối tượng trong mô hình nghiệp vụ. `equals` chỉ xác nhận sự bằng nhau theo định nghĩa giá trị của lớp.

## 2. Hợp đồng và cơ chế của `String.equals(Object)`

Phương thức `String` ghi đè phương thức từ `Object`:

```java
public boolean equals(Object anObject)
```

Đây là **chữ ký API**, không phải một chương trình chạy độc lập.

Về mặt ngữ nghĩa, `String.equals` trả `true` khi đối số là một `String` có **cùng dãy đơn vị mã UTF-16** theo đúng thứ tự. Điều này tương đương với cùng chiều dài `length()` và cùng giá trị `charAt(i)` tại mọi chỉ số hợp lệ. Với đối số `null` hoặc đối tượng không phải `String`, kết quả là `false`.

JDK được phép tối ưu cách kiểm tra, ví dụ xử lý cùng tham chiếu, kiểm tra chiều dài, so sánh dữ liệu trong bộ nhớ hoặc dùng biểu diễn compact; **không nên giả định một thuật toán vòng lặp duy nhất** từ mô tả hợp đồng.

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `"java".equals("java")` | `true` | Cùng nội dung |
| `"java".equals("Java")` | `false` | Phân biệt chữ hoa/thường |
| `"java".equals("java ")` | `false` | Có dấu cách ở cuối |
| `"".equals("")` | `true` | Cùng chuỗi rỗng |
| `"java".equals(null)` | `false` | `null` không phải `String` |
| `"java".equals(new StringBuilder("java"))` | `false` | Khác kiểu đối tượng, dù ký tự hiển thị giống |

`String.equals` không tự động xóa khoảng trắng, bỏ phân biệt chữ hoa, áp dụng bộ quy tắc ngôn ngữ theo locale hoặc chuẩn hóa Unicode. Nếu cần cách so sánh khác, ứng dụng phải định nghĩa rõ quy tắc đó.

## 3. String Pool và lý do `==` đôi lúc có vẻ hoạt động

Các literal chuỗi Java dùng cơ chế *interning*. Những literal cùng giá trị như `"hello"` thường trỏ đến đối tượng canonical từ String Pool. Vì vậy, kiểm tra `==` giữa hai literal giống nhau có thể trả `true` và gây hiểu lầm rằng `==` dùng để so nội dung.

```java
String a = "hello";
String b = "hello";
String c = new String("hello");

System.out.println(a == b);       // true
System.out.println(a == c);       // false
System.out.println(a.equals(c));  // true
```

Đây là **mảnh mã minh họa**. `a` và `b` nhận cùng đối tượng chuỗi được intern; `new String("hello")` tạo đối tượng mới có nội dung giống nhau, nên `a == c` sai còn `a.equals(c)` đúng.

Các tình huống quan trọng:

1. Hai literal hằng cùng nội dung được intern theo quy tắc chuỗi literal; `"he" + "llo"` cũng là biểu thức hằng có thể được trình biên dịch xử lý thành literal `"hello"`.
2. Phép nối dữ liệu từ biến tại **runtime** có thể tạo đối tượng chuỗi khác. Không dùng kết quả `==` với literal để suy ra quy tắc cho dữ liệu từ file, mạng hay người dùng.
3. `String.intern()` cung cấp tham chiếu canonical nhưng **không cần gọi nó để `equals` đúng**. Interning là cơ chế chia sẻ tham chiếu, không phải điều kiện bắt buộc cho equality nội dung.
4. `==` vẫn có chỗ dùng: kiểm tra tham chiếu giống nhau hoặc kiểm tra với `null`. Khi câu hỏi là “hai chuỗi có cùng chữ không?”, chọn `equals`.

## 4. Ví dụ Java 17+ chạy hoàn chỉnh

Tạo tệp `StringEqualityDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringEqualityDemo {
    public static void main(String[] args) {
        String literalA = "java";
        String literalB = "java";
        String separate = new String("java");
        String alias = literalA;

        System.out.println("literal identity: " + (literalA == literalB));
        System.out.println("separate identity: " + (literalA == separate));
        System.out.println("alias identity: " + (literalA == alias));
        System.out.println("content equal: " + literalA.equals(separate));
        System.out.println("case sensitive: " + "Java".equals(separate));
        System.out.println("ignore case: " + "Java".equalsIgnoreCase(separate));

        Set<String> set = new HashSet<>();
        set.add(literalA);
        set.add(separate);
        System.out.println("set size: " + set.size());

        Map<String, Integer> values = new HashMap<>();
        values.put(new String("ticket-17"), 42);
        System.out.println("map lookup: " + values.get(new String("ticket-17")));

        StringBuilder builder = new StringBuilder("java");
        System.out.println("builder equals: " + literalA.equals(builder));
        System.out.println("builder content: " + literalA.contentEquals(builder));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicode equals: " + composed.equals(decomposed));
        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("normalized equals: " + composed.equals(normalized));

        System.out.println("same hash: "
                + ("FB".hashCode() == "Ea".hashCode()));
        System.out.println("same content: " + "FB".equals("Ea"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StringEqualityDemo.java
java StringEqualityDemo
```

Stdout:

```text
literal identity: true
separate identity: false
alias identity: true
content equal: true
case sensitive: false
ignore case: true
set size: 1
map lookup: 42
builder equals: false
builder content: true
unicode equals: false
normalized equals: true
same hash: true
same content: false
```

Giải thích:

- **Ba dòng đầu:** hai literal dùng chung đối tượng interned; `new String` tạo đối tượng riêng; `alias` chỉ là tham chiếu tới đối tượng cũ.
- **`content equal`:** hai đối tượng `String` khác nhau vẫn bằng nhau về nội dung. `equals` phân biệt chữ hoa trong khi `equalsIgnoreCase` dùng quy tắc bỏ qua hoa/thường của Java.
- **`set size` và `map lookup`:** `HashSet` loại trùng và `HashMap` tra cứu khóa dựa trên equality nội dung, không yêu cầu đầu vào có cùng tham chiếu.
- **`builder equals` và `builder content`:** `StringBuilder` không phải `String`. `String.equals(builder)` trả `false`; `String.contentEquals(builder)` lại có thể so nội dung một `CharSequence`.
- **Unicode:** `é` dạng tổ hợp sẵn và dạng `e` cộng dấu kết hợp có thể trông giống nhau nhưng chứa dãy UTF-16 khác nhau; chuẩn hóa NFC trước khi so sánh giúp chúng tương đương.
- **Hash:** `"FB"` và `"Ea"` có cùng mã hash theo thuật toán `String.hashCode` nhưng `equals` vẫn `false`. Không suy diễn nội dung chỉ từ hash code.

## 5. `String.equals` và `hashCode` trong collection

`String` cài cả `equals` và `hashCode`. Hợp đồng chung của Java yêu cầu: khi `a.equals(b)` trả `true` thì **`a.hashCode() == b.hashCode()`**. Vì đối tượng `String` bất biến, thông tin dùng tính hash không thay đổi. Đây là một nền tảng khiến chuỗi hoạt động ổn định như khóa hash.

Khi `HashMap` có khóa `new String("A-001")`, lệnh `get(new String("A-001"))` vẫn lấy được giá trị đã lưu vì hai khóa có cùng nội dung và cùng hash. `HashSet` cũng loại trùng theo quan hệ bằng nhau, dù hai giá trị được tạo qua hai lệnh `new` khác nhau.

Nhưng **cùng hash không chứng minh bằng nhau**. Va chạm là điều có thể xảy ra, như ví dụ `"FB"` và `"Ea"`. Hash giúp định vị vị trí tra cứu; equality giúp phân biệt những khóa cụ thể. Không thay `a.equals(b)` bằng phép so sánh `hashCode` vì kết quả có thể sai.

Ngược lại, dùng `==` để tìm mã đơn hàng, khóa cache hoặc dữ liệu API có thể thất bại do một giá trị bằng nội dung nhưng đến từ đối tượng mới. Câu hỏi nghiệp vụ thường là **cùng mã**, không phải **cùng địa chỉ tham chiếu**.

## 6. `null`, các phương thức liên quan và cách chọn

### Tránh `NullPointerException`

Nếu `input` có thể bằng `null` thì `input.equals("ok")` sẽ ném `NullPointerException`, bởi phương thức không thể được gọi trên tham chiếu `null`. Hai cách thông dụng:

```java
String input = null;
boolean a = "ok".equals(input);                   // false
boolean b = java.util.Objects.equals(input, "ok"); // false
boolean c = java.util.Objects.equals(null, null);  // true
```

Đây là **mảnh mã minh họa**. `"ok".equals(input)` an toàn vì đối tượng gọi luôn tồn tại. `Objects.equals(a,b)` xử lý cả hai toán hạng có thể null và trả `true` nếu cả hai đều null. Vì vậy cần xem yêu cầu nghiệp vụ có coi “hai giá trị chưa biết” là bằng nhau không.

### Các phép so sánh khác

| API | Đặc điểm | Khi dùng |
| --- | --- | --- |
| `a == b` | So cùng tham chiếu | Kiểm tra identity hoặc null |
| `a.equals(b)` | So chính xác nội dung hai `String` | So giá trị chuỗi theo mặc định |
| `Objects.equals(a,b)` | So bằng nhau an toàn với null; dùng `equals` khi có giá trị | Hai phía có thể null |
| `a.equalsIgnoreCase(b)` | Bỏ qua khác biệt hoa/thường theo quy tắc của Java, không phụ thuộc locale | Khi yêu cầu chỉ cần so tương đương theo quy tắc đó |
| `a.contentEquals(cs)` | So nội dung `String` với một `CharSequence` | So với `StringBuilder`, `StringBuffer`... khi phù hợp |
| `a.compareTo(b)` | So thứ tự từ điển theo đơn vị mã UTF-16; trả 0 nếu chuỗi cùng nội dung | Sắp xếp thứ tự tự nhiên của `String` |
| `Collator` | So sánh theo quy tắc của một locale và mức độ phân biệt | Sắp xếp văn bản theo ngôn ngữ |

**`equalsIgnoreCase` không phải chuẩn hóa văn bản phổ quát.** Nó không tự cắt khoảng trắng, chuẩn hóa Unicode hoặc đảm bảo quy tắc so sánh của từng ngôn ngữ. Nếu muốn so tên người theo thứ tự/sự tương đương theo locale, nên cân nhắc `Collator` và các quy tắc dữ liệu riêng. Với mật khẩu, token hoặc chữ ký, không tự bỏ qua khác biệt ký tự khi giao thức không yêu cầu.

Một điểm dễ nhầm: `StringBuilder` kế thừa `Object.equals` theo ngữ nghĩa danh tính, do vậy hai `StringBuilder` chứa cùng ký tự không mặc nhiên bằng nhau. Muốn so nội dung với `String`, dùng `contentEquals` hoặc chuyển builder thành `String` rồi dùng `equals`.

## 7. Unicode: nhìn giống nhau không đảm bảo `equals`

Một văn bản có thể có nhiều cách biểu diễn Unicode. Chữ `é` chẳng hạn có thể là ký tự ghép sẵn U+00E9 hoặc chữ `e` U+0065 theo sau bởi dấu kết hợp U+0301. Hai cách có thể hiển thị gần như giống nhau, nhưng `String.equals` so từng **đơn vị mã UTF-16**, nên vẫn thấy khác biệt.

`String.length()` đếm đơn vị mã UTF-16, không nhất thiết đếm số ký tự mà người đọc nhìn thấy hay số Unicode code point. Ký tự ngoài BMP có thể gồm một cặp surrogate, còn chữ có dấu kết hợp có thể có nhiều code point. Do đó, so chính xác nội dung không đồng nghĩa so cách hiển thị.

Khi nghiệp vụ muốn coi hai biểu diễn Unicode tương đương, có thể chuẩn hóa cùng một dạng, chẳng hạn NFC:

```java
import java.text.Normalizer;

String normalizedA = Normalizer.normalize(inputA, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(inputB, Normalizer.Form.NFC);
boolean same = normalizedA.equals(normalizedB);
```

Đây là **mảnh mã minh họa**, giả định `inputA` và `inputB` đã có giá trị. Chuẩn hóa NFC xử lý tương đương chuẩn tắc Unicode; nó **không tự xử lý mọi khác biệt** về chữ hoa, khoảng trắng, ký tự giống hình từ các bảng chữ cái khác nhau, hay các yêu cầu so sánh theo tiếng Việt.

Đối với khóa dữ liệu và định danh, hãy xác định chính sách chuẩn hóa **trước khi ghi và truy vấn**, để mọi phía dùng cùng cách diễn giải. Đối với mật khẩu hoặc mã bảo mật, tuân thủ chính sách giao thức; không tự áp dụng chuẩn hóa hoặc bỏ phân biệt chữ hoa nếu điều đó làm thay đổi bí mật được kỳ vọng.

## 8. Những lỗi phổ biến trong thực tế

**Lỗi: dùng `==` cho văn bản nhận từ bên ngoài.** Hai tham chiếu khác nhau có thể có nội dung giống nhau; so bằng `equals` hoặc một quy tắc chuẩn hóa được định nghĩa rõ.

**Lỗi: gọi `equals` trên biến có thể null.** Nếu cần so với chuỗi hằng, dùng `"constant".equals(value)`; nếu cả hai biến có thể null, dùng `Objects.equals` khi cách xử lý hai null phù hợp nghiệp vụ.

**Lỗi: nhầm kết quả String Pool với quy tắc chung.** Hai literal bằng nhau có thể cùng đối tượng, nhưng dữ liệu nối lúc chạy hoặc đọc từ API không nhất thiết như vậy. Kiểm thử nên bao gồm hai `new String("same")` để quan sát `== false` và `equals true`.

**Lỗi: cho rằng `equals` không phân biệt hoa/thường hoặc khoảng trắng.** `"Java".equals("java")` và `"x".equals("x ")` đều `false`. Nếu cần bỏ khoảng trắng hoặc biến đổi chữ, áp dụng `strip()` hay biến đổi có kiểm soát theo `Locale.ROOT`/locale thích hợp; nhớ rằng quy tắc chữ hoa có thể phức tạp với Unicode.

**Lỗi: cho rằng cùng cách hiển thị thì cùng chuỗi.** Dấu kết hợp và các dạng chuẩn hóa khác nhau có thể khiến `equals` sai. Cần kiểm thử bằng ký tự Unicode thực tế của miền dữ liệu, nhất là tên, văn bản đa ngữ và chuỗi sao chép từ nhiều nguồn.

**Lỗi: kiểm tra bằng hash thay vì equality.** Hai hash trùng không có nghĩa hai chuỗi có cùng nội dung. `HashMap`/`HashSet` xử lý va chạm bằng hợp đồng equals/hashCode; mã nghiệp vụ cũng cần kiểm tra giá trị đúng nghĩa.

## 9. Checklist để ghi nhớ và tự kiểm thử

1. Xác định đang hỏi **cùng đối tượng** (`==`) hay **cùng nội dung `String`** (`equals`).
2. Tạo hai chuỗi cùng nội dung bằng `new String` để chứng minh identity có thể khác.
3. So chuỗi literal, chuỗi rỗng, chữ hoa/thường, dấu cách, giá trị `null` và văn bản Unicode.
4. Kiểm tra `HashSet` gộp hai chuỗi bằng nhau; `HashMap` tra cứu được bằng khóa `String` khác tham chiếu.
5. Ghi nhớ `String.equals` chỉ trả true với đối số kiểu `String` có cùng nội dung UTF-16.
6. Với giá trị có thể null, chọn `"literal".equals(variable)` hoặc `Objects.equals` theo yêu cầu.
7. Không dùng `StringBuilder.equals` hay so mã hash để thay thế kiểm tra nội dung.
8. Nếu cần không phân biệt hoa, chuẩn hóa Unicode, bỏ khoảng trắng hoặc so theo locale, định nghĩa và áp dụng quy tắc tường minh.
9. Xác nhận phép so sánh có phục vụ đúng khái niệm **danh tính nghiệp vụ**: hai chuỗi giống nhau không nhất thiết là cùng thực thể.

**Điểm cốt lõi:** `String.equals(Object)` so sánh chính xác nội dung văn bản theo ngữ nghĩa của Java `String`, độc lập với việc hai biến có cùng tham chiếu hay không. `==` dùng để kiểm tra identity; String Pool chỉ giải thích vì sao `==` đôi lúc cũng trả `true` với hai literal giống nhau. Khi cần quy tắc tương đương rộng hơn, hãy xác định rõ việc chuẩn hóa và so sánh ngoài `String.equals`.

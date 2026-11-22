# Giá trị `String` không đổi sau khi đối tượng được tạo (tính bất biến trong Java)

## 1. Tính bất biến (*immutability*) là gì?

Trong Java, một đối tượng `String` là **bất biến**: sau khi được tạo, nội dung chuỗi của chính đối tượng đó không thể thay đổi. Mọi thao tác muốn biểu diễn nội dung khác phải trả về/tham chiếu đến một giá trị `String` khác; nó không sửa các ký tự đã có trong đối tượng gốc.

Điều này khác với một **biến tham chiếu**. Biến kiểu `String` (nếu không khai báo `final`) vẫn có thể được gán để trỏ sang đối tượng khác. Chẳng hạn:

```java
String text = "Java";
text = text + " 17";
```

Sau phép gán, biến `text` chứa `"Java 17"`. Đối tượng chuỗi `"Java"` trước đó **không bị biến đổi**. Đó là điểm quan trọng nhất của bài: **đổi giá trị biến** không có nghĩa là **sửa nội dung đối tượng**.

Có thể hình dung như sau:

```text
Ban đầu:       text ───────> String "Java"

Tạo giá trị mới:              String "Java 17"
                String "Java" (vẫn nguyên vẹn)

Gán lại:       text ───────> String "Java 17"
                            (đối tượng "Java" không bị sửa)
```

Sơ đồ mô tả ý nghĩa tham chiếu, không khẳng định cách JVM cấp phát/thu hồi từng đối tượng cụ thể.

## 2. Đối tượng không đổi, nhưng biến có thể trỏ nơi khác

Một biến khác có thể cùng tham chiếu đến chuỗi ban đầu:

```java
String original = "Hello";
String alias = original;

original = original.concat(" Java");

// original -> "Hello Java"
// alias    -> "Hello"
```

`concat(" Java")` trả về chuỗi có nội dung mới. Phép gán lại chỉ thay đổi tham chiếu của `original`; `alias` vẫn tham chiếu chuỗi `"Hello"`. Nếu phương thức thực sự sửa đối tượng gốc, `alias` cũng sẽ nhìn thấy sự thay đổi; với `String`, điều đó không xảy ra.

Câu nói “`String` không thể đổi” cần được hiểu chính xác là **nội dung của một đối tượng `String` cụ thể không thể đổi**, không có nghĩa biến `String` phải giữ mãi một giá trị.

### `final String` khác với tính bất biến của `String`

```java
final String language = "Java";
// language = "Kotlin"; // LỖI BIÊN DỊCH: không thể gán lại biến final
```

`final` ngăn biến `language` bị gán lại sau khi đã khởi tạo; còn tính bất biến của `String` ngăn chính đối tượng bị sửa nội dung. Kể cả khi bỏ `final`, bản thân `String` vẫn bất biến. Ngược lại, khai báo `final StringBuilder builder` chỉ cố định **tham chiếu** `builder`, không ngăn `builder.append(...)` sửa nội dung của `StringBuilder`.

## 3. Những phương thức trông như “sửa” chuỗi thực ra làm gì?

Nhiều phương thức của `String` trả về giá trị để sử dụng, nhưng không thay đổi đối tượng gọi phương thức.

| Phép gọi | Kết quả biểu diễn | Đối tượng chuỗi ban đầu |
| --- | --- | --- |
| `"cat".concat("s")` | `"cats"` | Vẫn là `"cat"` |
| `"cat".replace('c', 'b')` | `"bat"` | Vẫn là `"cat"` |
| `"java".toUpperCase(java.util.Locale.ROOT)` | `"JAVA"` | Vẫn là `"java"` |
| `"  abc  ".strip()` | `"abc"` | Vẫn là `"  abc  "` |
| `"hello".substring(1, 4)` | `"ell"` | Vẫn là `"hello"` |

**Phải giữ kết quả nếu muốn sử dụng nội dung mới:**

```java
String name = "java";
name.toUpperCase(java.util.Locale.ROOT);
System.out.println(name); // java

name = name.toUpperCase(java.util.Locale.ROOT);
System.out.println(name); // JAVA
```

Lệnh đầu chỉ gọi hàm mà không dùng giá trị trả về; không có tác dụng sửa `name`. Lệnh sau gán lại biến.

**Đừng hiểu nhầm rằng mỗi lần gọi phương thức đều bắt buộc tạo một đối tượng mới.** Một số phương thức có thể trả lại chính đối tượng hiện tại khi kết quả không đổi, ví dụ `"abc".concat("")`. Điều được đảm bảo là **không làm thay đổi nội dung của đối tượng `String` gốc**; việc có cấp phát đối tượng mới hay tái sử dụng đối tượng hiện hữu là vấn đề khác. Trong lập trình ứng dụng, đừng dùng phép so sánh tham chiếu `==` để suy luận nội dung từ các thao tác này.

## 4. Ví dụ đầy đủ chạy bằng Java 17

Lưu chương trình sau vào tệp `StringImmutabilityDemo.java`:

```java
import java.util.Locale;

public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String extended = original.concat(" 17");

        System.out.println("original = " + original);
        System.out.println("alias = " + alias);
        System.out.println("extended = " + extended);

        String upper = original.toUpperCase(Locale.ROOT);
        System.out.println("upper = " + upper);
        System.out.println("original after method = " + original);

        original = extended;
        System.out.println("original after assignment = " + original);
        System.out.println("alias after assignment = " + alias);

        char[] source = {'J', 'a', 'v', 'a'};
        String fromArray = new String(source);
        source[0] = 'K';
        System.out.println("source array = " + new String(source));
        System.out.println("string from array = " + fromArray);

        char[] exported = fromArray.toCharArray();
        exported[0] = 'Z';
        System.out.println("exported array = " + new String(exported));
        System.out.println("string after export = " + fromArray);

        StringBuilder builder = new StringBuilder("Go");
        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("builder = " + builder);
        System.out.println("snapshot = " + snapshot);

        String literal = "same";
        String created = new String("same");
        System.out.println("same content = " + literal.equals(created));
        System.out.println("same reference = " + (literal == created));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

Kết quả in ra:

```text
original = Java
alias = Java
extended = Java 17
upper = JAVA
original after method = Java
original after assignment = Java 17
alias after assignment = Java
source array = Kava
string from array = Java
exported array = Zava
string after export = Java
builder = Go!
snapshot = Go
same content = true
same reference = false
```

Ví dụ minh họa bốn điểm: thay đổi tham chiếu không sửa chuỗi cũ; phương thức `String` trả về kết quả; mảng ký tự bên ngoài không thể sửa nội dung `String` đã tạo; `StringBuilder` thay đổi được nhưng `String` lấy từ `toString()` vẫn là một giá trị bất biến.

## 5. Vì sao mảng `char[]` không thể sửa một `String`?

Mảng ký tự là cấu trúc **mutable**: có thể gán `chars[0] = 'X'`. Nhưng khi tạo `String` từ mảng `char[]`, Java lấy nội dung của mảng để tạo chuỗi và **không để các thay đổi về sau của mảng ảnh hưởng đến chuỗi**.

```java
char[] chars = {'a', 'b', 'c'};
String s = new String(chars);
chars[0] = 'X';

System.out.println(new String(chars)); // Xbc
System.out.println(s);                 // abc
```

Tương tự, `s.toCharArray()` tạo mảng riêng để bạn sửa nếu cần. Việc sửa mảng trả về sẽ không làm `s` đổi nội dung. `String` cũng không cung cấp API công khai để người dùng gán trực tiếp ký tự tại một vị trí như `s.setCharAt(...)`; phương thức kiểu này thuộc các đối tượng mutable như `StringBuilder`.

Chi tiết triển khai bên trong `String` thay đổi giữa các phiên bản JDK (chẳng hạn `String` hiện đại có thể lưu dữ liệu theo dạng compact strings). Người học nên dựa vào **hợp đồng bất biến của API**, không dựa vào trường nội bộ hay giả định `String` luôn lưu bằng một mảng `char[]`. Không dùng reflection/`Unsafe` để can thiệp vào biểu diễn nội bộ: điều đó phá vỡ giả định của chương trình và không phải cách sử dụng `String` được hỗ trợ.

## 6. Tính bất biến và string pool

Java có cơ chế *string pool* để chia sẻ các chuỗi có cùng nội dung trong những trường hợp phù hợp. Đặc biệt, chuỗi literal và các biểu thức hằng kiểu chuỗi được intern:

```java
String a = "Java";
String b = "Ja" + "va"; // biểu thức hằng được gộp khi biên dịch
System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Ở đây `a == b` là `true` vì hai tham chiếu đến cùng literal đã được intern. **Không suy rộng** kết quả này cho mọi chuỗi có cùng nội dung. Ví dụ:

```java
String a = "Java";
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
System.out.println(a == b.intern()); // true
```

`new String("Java")` được dùng ở đây **chỉ để minh họa** sự khác nhau giữa tham chiếu và giá trị; trong ứng dụng thông thường không cần tạo đối tượng thừa như vậy.

String pool có thể chia sẻ an toàn một đối tượng `String` vì không ai có thể sửa nội dung của nó: các nơi dùng chung sẽ luôn thấy cùng dãy ký tự. Muốn so sánh **nội dung**, dùng `equals()`; `==` chỉ phù hợp khi bạn thực sự cần so sánh **cùng đối tượng** (hoặc kiểm tra với `null`).

## 7. Khi cần sửa nhiều lần: dùng `StringBuilder`

`StringBuilder` là đối tượng **có thể thay đổi**. Các thao tác như `append()`, `insert()`, `delete()`, `replace()` và `setCharAt()` cập nhật trạng thái của builder, thay vì tạo một đối tượng `String` bất biến sau mỗi bước.

Ví dụ chương trình độc lập `BuildMessage.java`:

```java
public class BuildMessage {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        String before = builder.toString();

        builder.append(" 17");
        builder.setCharAt(0, 'j');

        String after = builder.toString();
        System.out.println("before = " + before);
        System.out.println("builder = " + builder);
        System.out.println("after = " + after);
    }
}
```

Chạy:

```bash
javac BuildMessage.java
java BuildMessage
```

Kết quả:

```text
before = Java
builder = java 17
after = java 17
```

`before` không thay đổi sau khi builder được sửa. `toString()` cung cấp một giá trị `String` bất biến tại thời điểm gọi; sửa builder sau đó không làm các chuỗi đã trả về đổi nội dung.

### So sánh lựa chọn khi ghép chuỗi

| Trường hợp | Cách phù hợp | Lý do |
| --- | --- | --- |
| Ghép vài đoạn đơn giản | `first + " " + last` | Dễ đọc; compiler/JVM có thể tối ưu |
| Ghép nhiều đoạn trong vòng lặp | `StringBuilder` rồi `toString()` | Tránh lặp lại việc hình thành các giá trị chuỗi trung gian không cần thiết |
| Cần chuỗi ổn định để lưu/chia sẻ | `String` | Nội dung đối tượng không đổi |
| Một đối tượng builder dùng từ nhiều thread | Thiết kế đồng bộ thích hợp hoặc tách mỗi thread một builder | `StringBuilder` không bảo đảm thread-safe khi cùng bị sửa từ nhiều thread |

Không nên tuyên bố mọi phép `+` đều “chậm”; Java có tối ưu ghép chuỗi. Điều cần nhận biết là `String` không cung cấp cơ chế sửa tại chỗ, nên khi tích lũy dữ liệu qua nhiều bước, builder có thể phù hợp hơn.

## 8. Tác dụng của tính bất biến

### 8.1. Chia sẻ nội dung an toàn

Nhiều đoạn code hoặc nhiều thread có thể giữ tham chiếu đến **cùng một** `String` mà không lo một nơi sửa nội dung khiến nơi khác quan sát thấy ký tự mới. Tính chất này hữu ích khi truyền tham số, trả kết quả, lưu cấu hình và chia sẻ hằng số.

Điều đó **không tự động làm mọi chương trình chứa `String` trở nên thread-safe**. Nếu nhiều thread cùng đọc/ghi một **biến tham chiếu** kiểu `String`, vẫn phải xử lý đúng vấn đề chia sẻ trạng thái, khả năng nhìn thấy giá trị và đồng bộ khi cần. Sự an toàn về **nội dung đối tượng** và sự an toàn khi **cập nhật biến** là hai vấn đề khác nhau.

### 8.2. Làm khóa cho `HashMap` hoặc phần tử `HashSet`

`String.equals()` và `String.hashCode()` phụ thuộc vào nội dung chuỗi. Vì nội dung không thể đổi, một `String` đã dùng làm khóa không tự thay đổi cách so sánh/hash của nó trong khi đang nằm trong cấu trúc dữ liệu.

```java
java.util.Map<String, Integer> scores = new java.util.HashMap<>();
String key = "Java";
scores.put(key, 10);

key = key + " 17";

System.out.println(scores.get("Java"));    // 10
System.out.println(scores.get("Java 17")); // null
```

Gán lại `key` không đổi khóa `"Java"` đã được đưa vào map. Tính bất biến giúp ngăn lỗi thường gặp khi đối tượng khóa mutable bị thay đổi nội dung sau khi chèn.

### 8.3. Dễ hiểu luồng dữ liệu hơn

Một phương thức nhận `String` có thể tin rằng mã bên ngoài không sửa các ký tự của chính đối tượng được truyền vào trong lúc phương thức xử lý. Nếu cần văn bản khác, code trả về hoặc nhận một giá trị mới, làm hành vi rõ ràng và dễ kiểm thử.

Tuy nhiên, bất biến **không đồng nghĩa với bí mật hay an toàn tuyệt đối**: ví dụ, dữ liệu nhạy cảm trong `String` không thể chủ động ghi đè ký tự theo cách ghi đè một mảng có thể sửa; thời điểm đối tượng được thu gom là do JVM quyết định. Với dữ liệu nhạy cảm cần chính sách xóa khỏi bộ nhớ, cân nhắc thiết kế và API phù hợp, thay vì dựa vào khả năng “xóa nội dung String”.

## 9. Những nhầm lẫn thường gặp

1. **“`s += "x"` đã sửa đối tượng `s`.”** Sai: biểu thức tạo ra giá trị chuỗi với nội dung mới và gán lại biến `s`. Alias tham chiếu chuỗi cũ vẫn nhìn thấy nội dung cũ.
2. **“Gọi `s.replace(...)` là đủ.”** Sai nếu bạn cần kết quả. `replace` trả về chuỗi kết quả; phải gán vào biến hoặc truyền giá trị trả về cho bước tiếp theo.
3. **“`String` immutable vì tôi khai báo `final`.”** Không đúng: `String` vốn bất biến dù tham chiếu không `final`. `final` chỉ cấm gán lại biến.
4. **“`==` và `equals` đều so sánh chữ.”** `==` so sánh tham chiếu; `equals` so sánh nội dung. Pool có thể làm một số cặp `==` trả về true, nhưng không phải quy tắc so sánh chuỗi.
5. **“Tất cả phương thức `String` luôn cấp phát một đối tượng mới.”** Không chắc. Nếu không thay đổi kết quả, API hoặc JVM có thể trả về cùng tham chiếu hoặc dùng lại đối tượng đã có; bất biến chỉ đòi hỏi không sửa chuỗi gốc.
6. **“Có thể sửa `String` bằng cách thay đổi mảng truyền vào constructor.”** Không: thay đổi mảng bên ngoài sau khi tạo `String` không thay đổi nội dung chuỗi.
7. **“Builder và String giống nhau.”** Không: `StringBuilder` mutable, có thể bị sửa qua cùng một tham chiếu; `String` immutable, các giá trị lấy từ builder vẫn giữ nguyên.
8. **“Vì nội dung String thread-safe nên gán lại biến chung cũng thread-safe.”** Sai: tính bất biến không thay cho các quy tắc về đồng bộ và visibility của Java Memory Model.

## 10. Tự kiểm tra kiến thức

Xét đoạn mã sau trong thân một phương thức Java:

```java
String a = "cat";
String b = a;

a.replace('c', 'b');
a = a + "s";

System.out.println(a);
System.out.println(b);
```

Kết quả là:

```text
cats
cat
```

Giải thích: `replace` không thay đổi `a` vì kết quả trả về bị bỏ qua. Phép `a + "s"` tạo giá trị `"cats"` và `a` được gán lại. `b` vẫn tham chiếu giá trị `"cat"` ban đầu.

Thử sửa dòng thứ ba thành `a = a.replace('c', 'b');`. Khi đó `a` cuối cùng là `"bats"`, còn `b` vẫn là `"cat"`.

**Ghi nhớ:** Tính bất biến nói về **nội dung của một đối tượng `String` sau khi được tạo**. Mỗi khi thấy chuỗi “thay đổi”, hãy hỏi: *đã sửa đối tượng ban đầu, hay chỉ tạo/nhận giá trị khác rồi gán lại biến?* Với `String` trong Java, đó là trường hợp thứ hai.

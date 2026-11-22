# `StringBuilder.append` với `String`, primitive, `Object`, `char[]` và `CharSequence`

Trong Java, `StringBuilder` xây dựng văn bản bằng cách **bổ sung dữ liệu vào chính đối tượng hiện tại**. Họ phương thức `append(...)` có nhiều overload để nhận trực tiếp `String`, các kiểu nguyên thủy (*primitive*), `Object`, mảng `char[]` và `CharSequence`. Nhìn bên ngoài, mọi lời gọi đều «nối thêm», nhưng **kiểu của đối số quyết định overload được chọn**, và overload đó quyết định cách dữ liệu được chuyển thành các ký tự.

Ví dụ nhanh:

```java
StringBuilder out = new StringBuilder();
out.append("id=").append(42).append(", active=").append(true);
System.out.println(out); // id=42, active=true
```

Không cần tạo liên tiếp những `String` trung gian cho từng thao tác nối. Tuy vậy, để dùng đúng `append`, cần hiểu sự khác nhau giữa **thêm nội dung văn bản**, **chuyển giá trị sang văn bản** và **thêm các phần tử của một mảng ký tự**.

## 1. `append` thay đổi chính builder và trả về `this`

Với `String`, phép nối như `text = text + suffix` cho ra một giá trị `String` rồi gán lại biến `text`, vì `String` bất biến. Còn `StringBuilder.append(...)` ghi bổ sung vào nội dung của builder hiện có.

```java
StringBuilder builder = new StringBuilder("A");
StringBuilder sameReference = builder;

StringBuilder returned = builder.append("B");

System.out.println(builder);                  // AB
System.out.println(sameReference);            // AB
System.out.println(returned == builder);      // true
```

`append` trả về **chính builder** nên có thể nối chuỗi nhiều lời gọi:

```java
new StringBuilder().append("x=").append(10).append(", y=").append(20)
```

Đây là biểu thức minh họa: nếu muốn lấy `String` kết quả, gọi `toString()` ở cuối. Không cần gán lại `builder = builder.append(...)` vì builder đã thay đổi tại chỗ, dù phép gán đó vẫn hợp lệ.

**Phân biệt `length` và `capacity`:** `length()` là số UTF-16 code unit hiện có; `capacity()` là dung lượng bộ đệm dành cho các code unit trước khi cần mở rộng. Nhiều lần `append` có thể tăng `length` và làm tăng `capacity` khi cần. `capacity` không phải giới hạn số ký tự cố định của builder.

### Ví dụ 1: nối nhiều kiểu trong một chương trình

Tạo tệp `AppendOverviewDemo.java`:

```java
public class AppendOverviewDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("User ");
        StringBuilder alias = builder;

        builder.append("An")
               .append(" | age=")
               .append(21)
               .append(" | active=")
               .append(true)
               .append(" | grade=")
               .append('A');

        System.out.println(builder);
        System.out.println(alias);
        System.out.println(builder == alias);
        System.out.println(builder.length());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AppendOverviewDemo.java
java AppendOverviewDemo
```

Kết quả:

```text
User An | age=21 | active=true | grade=A
User An | age=21 | active=true | grade=A
true
40
```

Hai biến vẫn trỏ đến **một đối tượng mutable** sau khi `append`. Dữ liệu được thêm theo đúng thứ tự gọi, không tự chèn dấu cách hay dấu phân cách trừ khi bạn tự cung cấp.

## 2. `append(String)`: thêm các ký tự của chuỗi

Overload `append(String str)` nối các ký tự của `str` vào cuối builder. Nếu đối số là một `String`, overload này thường là lựa chọn trực tiếp nhất.

```java
String prefix = "Hello";
StringBuilder sb = new StringBuilder();
sb.append(prefix);
sb.append(", Java");
```

Kết quả là `"Hello, Java"`. Hai đối tượng `String` nguồn không bị sửa; builder sao chép nội dung cần thêm vào vùng dữ liệu riêng của nó.

### `null` ở overload `String`

Theo hợp đồng `StringBuilder.append(String)`, một tham chiếu `String` bằng `null` được thêm dưới dạng bốn ký tự `"null"`. Nó **không bỏ qua** giá trị và cũng không tự động ném lỗi:

```java
String missing = null;
StringBuilder sb = new StringBuilder("value=");
sb.append(missing);
// Nội dung: "value=null"
```

Nếu yêu cầu nghiệp vụ coi `null` là chuỗi rỗng hoặc không muốn thêm gì, bạn phải **xử lý rõ trước khi gọi**. Chẳng hạn:

```java
if (missing != null) {
    sb.append(missing);
}
```

Hai đoạn trên là mã minh họa, có thể đặt trong một phương thức. Không nên dựa vào hành vi `"null"` để xây dựng giao thức dữ liệu nếu đây không phải quy ước đã định nghĩa.

## 3. `append` với primitive: giá trị được biểu diễn thành chữ

`StringBuilder` có overload cho các primitive thông dụng:

| Kiểu đối số | Overload tiêu biểu | Ví dụ thêm vào builder |
| --- | --- | --- |
| `boolean` | `append(boolean)` | `true` → `"true"`; `false` → `"false"` |
| `char` | `append(char)` | `'A'` → `"A"` |
| `int` | `append(int)` | `42` → `"42"` |
| `long` | `append(long)` | `42L` → `"42"` |
| `float` | `append(float)` | `1.5f` → `"1.5"` |
| `double` | `append(double)` | `2.25` → `"2.25"` |

`byte` và `short` không có overload riêng; chúng có thể được **nâng kiểu số** sang `int`, nên giá trị thường được thêm theo cách biểu diễn số thập phân.

Điều đặc biệt cần nhớ: `char` biểu diễn **đơn vị ký tự**, còn `int` biểu diễn **số nguyên**. `append('A')` khác `append(65)`:

```java
new StringBuilder().append('A') // "A"
new StringBuilder().append(65)  // "65"
```

Dù `'A'` có giá trị số Unicode là 65, overload được chọn theo **kiểu tại thời điểm biên dịch**, không theo ý định ngầm của người viết.

### Ví dụ 2: primitive, kiểu và phép tính

Tạo tệp `PrimitiveAppendDemo.java`:

```java
public class PrimitiveAppendDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder();
        first.append(65).append('|')
             .append('A').append('|')
             .append(true).append('|')
             .append(12L).append('|')
             .append(1.5f).append('|')
             .append(2.25d);

        System.out.println(first);

        StringBuilder second = new StringBuilder();
        second.append(1 + 2).append('|');
        second.append(1).append(2);

        System.out.println(second);

        byte small = 7;
        short another = 8;
        System.out.println(new StringBuilder().append(small).append(',').append(another));
    }
}
```

```bash
javac -encoding UTF-8 PrimitiveAppendDemo.java
java PrimitiveAppendDemo
```

Kết quả:

```text
65|A|true|12|1.5|2.25
3|12
7,8
```

Ở `append(1 + 2)`, phép tính `1 + 2` được thực hiện **trước khi gọi**, rồi `append(int)` thêm `3`. Ngược lại, `append(1).append(2)` là hai lần gọi liên tiếp, thêm `"1"` và `"2"` thành `"12"`. Các overload không tự hiểu bạn muốn cộng số hay ghép văn bản.

Định dạng số mặc định phù hợp để biểu diễn giá trị, nhưng không phải lúc nào cũng đáp ứng yêu cầu báo cáo: ví dụ hiển thị đúng hai chữ số thập phân hoặc dấu phân cách theo locale cần xử lý định dạng riêng, chẳng hạn `Formatter` hay `String.format(Locale, ...)`. Khi nối trực tiếp, không giả định `append(double)` tạo định dạng tiền tệ hay định dạng số địa phương.

## 4. `append(Object)`: chuyển đối tượng thành chuỗi qua `String.valueOf`

Overload `append(Object obj)` lấy biểu diễn chuỗi tương ứng với `String.valueOf(obj)`:

- Nếu `obj == null`, phần được thêm là `"null"`.
- Nếu `obj != null`, `String.valueOf(obj)` dựa vào `obj.toString()`.
- Nếu lớp của đối tượng tự ghi đè `toString()`, văn bản thêm vào builder là biểu diễn do lớp cung cấp.
- Nếu không ghi đè, `Object.toString()` thường cho dạng tên lớp cùng thông tin danh tính; đó **không** phải biểu diễn có cấu trúc thích hợp cho mọi nghiệp vụ.

Khi muốn chèn đối tượng tùy biến vào câu log hoặc chuỗi mô tả, nên có `toString()` dễ hiểu nếu đây thực sự là công dụng mong đợi. Tuy nhiên, `toString()` không phải API tuần tự hóa (serialization) chuẩn cho dữ liệu cần round-trip.

### Ví dụ 3: đối tượng có `toString()` riêng

Tạo tệp `ObjectAppendDemo.java`:

```java
public class ObjectAppendDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public String toString() {
            return "(" + x + "," + y + ")";
        }
    }

    public static void main(String[] args) {
        Point point = new Point(3, 4);
        Object asObject = point;

        StringBuilder builder = new StringBuilder("position=");
        builder.append(asObject).append("; missing=");
        builder.append((Object) null);

        System.out.println(builder);
        System.out.println(new StringBuilder().append((Object) "hello"));
    }
}
```

```bash
javac -encoding UTF-8 ObjectAppendDemo.java
java ObjectAppendDemo
```

Kết quả:

```text
position=(3,4); missing=null
hello
```

Biến `asObject` được khai báo kiểu `Object`, nên overload `append(Object)` được chọn; phương thức `Point.toString()` thực sự được gọi lúc chạy nhờ đa hình. Dòng cuối ép kiểu `String` thành `Object` nhưng kết quả vẫn là `hello` vì `String.toString()` thể hiện đúng nội dung của chuỗi.

**Chú ý:** `append(Object)` **không tự duyệt và nối phần tử của mọi loại mảng**. Đặc biệt, mảng ký tự có overload riêng (`append(char[])`), còn một biến đã ép thành `Object` sẽ đi qua đường xử lý `Object`. Đây là lý do phải hiểu sự khác nhau giữa **kiểu khai báo** và **giá trị runtime**.

## 5. `append(char[])`: nối nội dung mảng ký tự, không phải tên mảng

`char[]` là kiểu đối số quan trọng vì `StringBuilder` có overload chuyên dụng:

```java
append(char[] str)
append(char[] str, int offset, int len)
```

- `append(char[])` nối **từng code unit** trong mảng vào builder theo thứ tự.
- `append(char[], offset, len)` nối **`len` phần tử** bắt đầu từ `offset`.
- `offset` là vị trí đầu **được tính vào đoạn**; `len` là **số lượng phần tử**, **không phải chỉ số kết thúc**.
- Nếu mảng bằng `null`, overload `char[]` ném `NullPointerException`.
- Nếu khoảng mảng không hợp lệ, overload phạm vi ném `IndexOutOfBoundsException` hoặc loại ngoại lệ con phù hợp.

Đây là khác biệt với `append(String)` hoặc `append(Object)` nhận null và thêm chữ `"null"`. Vì vậy `append(null)` **không có một hành vi duy nhất**: biểu thức null không có kiểu cụ thể và bị **mơ hồ overload** ở thời điểm biên dịch. Muốn chọn một overload, cần biến có kiểu khai báo hoặc ép kiểu tường minh.

### Ví dụ 4: toàn bộ mảng và một lát cắt

Tạo `CharArrayAppendDemo.java`:

```java
public class CharArrayAppendDemo {
    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a', '!'};
        StringBuilder builder = new StringBuilder();

        builder.append(letters);
        builder.append(" | ");
        builder.append(letters, 1, 3);

        System.out.println(builder);

        letters[0] = 'X';
        System.out.println(builder);

        StringBuilder nullText = new StringBuilder();
        nullText.append((String) null).append('|')
                .append((Object) null).append('|')
                .append((CharSequence) null);
        System.out.println(nullText);

        try {
            new StringBuilder().append((char[]) null);
        } catch (NullPointerException exception) {
            System.out.println("char[] is null");
        }
    }
}
```

```bash
javac -encoding UTF-8 CharArrayAppendDemo.java
java CharArrayAppendDemo
```

Kết quả:

```text
Java! | ava
Java! | ava
null|null|null
char[] is null
```

`append(letters, 1, 3)` lấy các phần tử ở chỉ số 1, 2, 3, tương ứng `"ava"`. Sau đó thay `letters[0]` thành `'X'` **không thay đổi văn bản đã append** vào builder: các code unit cần thêm đã được sao chép vào nội dung builder.

Nếu muốn thêm chỉ một phần của mảng, không nhầm chữ ký `(offset, len)` với `substring(start, end)` hay `CharSequence.subSequence(start, end)`: các API sau dùng vị trí cuối **loại trừ**, còn ở `char[]` tham số cuối là **độ dài đoạn**.

### Mảng ký tự đi qua overload `Object` thì sao?

Xét:

```java
char[] letters = {'O', 'K'};
StringBuilder first = new StringBuilder().append(letters);
StringBuilder second = new StringBuilder().append((Object) letters);
```

`first` có nội dung `"OK"`. `second` **không** có nội dung `"OK"`; nó dùng `Object.toString()` của mảng ký tự, thường có dạng như `[C@...` với phần định danh không cố định. Không ghi output cụ thể của `second` vì phần định danh phụ thuộc đối tượng/runtime.

Đây là một trường hợp overload cho thấy cùng **đối tượng runtime `char[]`** nhưng kiểu đối số ở lời gọi khác nhau dẫn tới hành vi khác. Mảng `int[]` hay `Object[]` cũng không được `append(Object)` tự động duyệt phần tử; nếu cần ghép phần tử mảng, hãy lựa chọn cách định dạng rõ ràng, chẳng hạn `Arrays.toString(...)` khi phù hợp.

## 6. `append(CharSequence)`: lập trình theo giao diện đọc dãy ký tự

`CharSequence` biểu diễn dãy ký tự có thể đọc bằng `length()` và `charAt(...)`. `String`, `StringBuilder`, `StringBuffer` và `CharBuffer` là các triển khai thường gặp.

`StringBuilder` có overload:

```java
append(CharSequence s)
append(CharSequence s, int start, int end)
```

Ý nghĩa:

- `append(CharSequence s)` nối toàn bộ các ký tự hiện tại của dãy `s`.
- `append(s, start, end)` nối đoạn theo khoảng chỉ số **nửa mở `[start, end)`**. Tham số `end` là vị trí **loại trừ**, khác với tham số `len` của `append(char[], offset, len)`.
- Khoảng hợp lệ là `0 <= start <= end <= s.length()` đối với `s` khác null.
- Với `s == null`, hợp đồng overload `CharSequence` quy định xem nguồn như dãy ký tự `"null"`. Để tránh nhập nhằng, hãy định nghĩa chính sách null của ứng dụng thay vì dựa vào giá trị mặc định.
- `CharSequence` không bảo đảm đối tượng nguồn bất biến; các implementation mutable có thể thay đổi nội dung giữa những thời điểm đọc khác nhau.

Hợp đồng giao diện cho phép bạn viết code nhận nhiều kiểu đầu vào. Tuy nhiên, **khi append đã hoàn thành**, nội dung được thêm là phần dữ liệu của builder đích; builder đích **không trở thành một view liên kết** để thay đổi nguồn sau đó tự động cập nhật văn bản cũ.

### Ví dụ 5: `String`, `StringBuilder` và `CharBuffer`

Tạo `CharSequenceAppendDemo.java`:

```java
import java.nio.CharBuffer;

public class CharSequenceAppendDemo {
    public static void main(String[] args) {
        CharSequence word = "abcdef";
        CharSequence mutable = new StringBuilder("XYZ123");
        CharSequence buffer = CharBuffer.wrap("hello");

        StringBuilder result = new StringBuilder();
        result.append(word, 1, 4).append('|')
              .append(mutable, 0, 3).append('|')
              .append(buffer, 1, 4);

        System.out.println(result);

        StringBuilder source = new StringBuilder("cat");
        StringBuilder target = new StringBuilder().append((CharSequence) source);
        source.setCharAt(0, 'B');

        System.out.println(source);
        System.out.println(target);

        CharSequence missing = null;
        System.out.println(new StringBuilder().append(missing));
    }
}
```

```bash
javac -encoding UTF-8 CharSequenceAppendDemo.java
java CharSequenceAppendDemo
```

Kết quả:

```text
bcd|XYZ|ell
Bat
cat
null
```

Lời gọi `result.append(word, 1, 4)` lấy chỉ số 1, 2, 3 nên cho `"bcd"`. Với `mutable`, `[0,3)` cho `"XYZ"`; với `buffer`, `[1,4)` cho `"ell"`.

`target` giữ `"cat"` mặc dù `source` đã thành `"Bat"` vì append đã ghi nội dung vào builder đích. Nếu nguồn có thể bị sửa **đồng thời** bởi luồng khác, phải dùng cách đồng bộ thích hợp để bảo đảm snapshot nhất quán: `StringBuilder` không tự bảo đảm thread-safety.

### Trường hợp null với đoạn `CharSequence`

Theo hợp đồng `append(CharSequence, int, int)`, một nguồn `null` được xử lý như dãy `"null"` trước khi lấy đoạn. Do vậy `append((CharSequence) null, 1, 3)` có thể thêm `"ul"`. Dù hợp lệ, viết code dựa vào cách xử lý null ngầm này thường kém rõ ràng hơn việc tự chọn giá trị mặc định hoặc kiểm tra `null` trước.

## 7. Overload resolution: kiểu **biểu thức** quyết định phương thức

Java chọn overload có thể áp dụng và cụ thể nhất tại **thời điểm biên dịch**, dựa vào kiểu biểu thức ở lời gọi. Không phải cứ giá trị runtime là một `String` thì luôn gọi `append(String)`.

```java
String text = "hello";
Object object = text;
CharSequence sequence = text;

new StringBuilder().append(text);      // append(String)
new StringBuilder().append(object);    // append(Object)
new StringBuilder().append(sequence);  // append(CharSequence)
```

Cả ba cho chữ `hello` trong ví dụ này, nhưng **con đường chuyển đổi** và lựa chọn overload khác nhau. Sự khác biệt lộ rõ hơn với `char[]`, với `null`, và với những lớp có `toString()` tùy chỉnh.

| Biểu thức đối số | Overload liên quan | Kết quả hoặc lưu ý |
| --- | --- | --- |
| `"abc"` | `String` | Thêm `abc` |
| `(String) null` | `String` | Thêm `null` |
| `42` | `int` | Thêm `42` |
| `'A'` | `char` | Thêm `A` |
| `(Object) null` | `Object` | Thêm `null` |
| `new char[] {'O', 'K'}` | `char[]` | Thêm `OK` |
| `(Object) new char[] {'O', 'K'}` | `Object` | Không tự thêm `OK`; dùng `toString()` của mảng |
| `(CharSequence) "abc"` | `CharSequence` | Thêm `abc` |
| `(CharSequence) null` | `CharSequence` | Thêm `null` |
| `null` (không ép kiểu) | Mơ hồ giữa nhiều overload tham chiếu | **Lỗi biên dịch** |

Lý do `append(null)` gây mơ hồ là các overload như `append(String)` và `append(char[])` không có quan hệ kiểu cha–con giúp trình biên dịch chọn một overload duy nhất cụ thể nhất. Không viết ví dụ này trong file Java cần biên dịch; hãy xem nó như một dòng **cố ý sai** để minh họa:

```java
// new StringBuilder().append(null); // Lỗi biên dịch: reference to append is ambiguous
```

Chỉ thêm một cast là thay đổi ý nghĩa lời gọi:

```java
new StringBuilder().append((String) null); // Hợp lệ, "null"
new StringBuilder().append((char[]) null); // Ném NullPointerException
```

Do đó, trong mã review, cần để ý **kiểu khai báo** và cast của các biến dùng làm đối số. Đừng chỉ nhìn giá trị khi chạy.

## 8. Tương tác với `char`, Unicode và code point

`append(char)` thêm **một UTF-16 code unit**. Một code point Unicode ngoài Basic Multilingual Plane (BMP), ví dụ U+1F600, cần **hai code unit** (một cặp surrogate). Nếu chỉ thêm một `char` surrogate, bạn chưa thêm trọn code point.

Khi cần bổ sung một Unicode code point được lưu trong biến `int`, `StringBuilder.appendCodePoint(int)` là API phù hợp hơn `append(int)`:

```java
StringBuilder a = new StringBuilder().append(0x1F600);         // "128512"
StringBuilder b = new StringBuilder().appendCodePoint(0x1F600); // U+1F600
```

`append(int)` chuyển **giá trị số** sang chữ số thập phân; `appendCodePoint(int)` chuyển **mã điểm Unicode** thành đơn vị UTF-16 tương ứng. Hai phương thức có mục đích khác nhau, và không nên hoán đổi.

### Ví dụ 6: số code point khác số code unit

Tạo `UnicodeAppendDemo.java`:

```java
public class UnicodeAppendDemo {
    public static void main(String[] args) {
        int smile = 0x1F600;
        StringBuilder numeric = new StringBuilder().append(smile);
        StringBuilder actual = new StringBuilder().appendCodePoint(smile);

        System.out.println(numeric);
        System.out.println(numeric.length());
        System.out.println(actual.length());
        System.out.println(actual.codePointCount(0, actual.length()));
        System.out.println(actual.toString().codePointAt(0) == smile);
    }
}
```

```bash
javac -encoding UTF-8 UnicodeAppendDemo.java
java UnicodeAppendDemo
```

Kết quả:

```text
128512
6
2
1
true
```

Nếu bạn có một `String` chứa emoji và gọi `append(String)` hoặc `append(CharSequence)`, API sẽ thêm các code unit của chuỗi đó. Với `char[]`, bạn cũng cần đảm bảo mảng chứa đầy đủ cặp surrogate nếu muốn biểu diễn code point ngoài BMP. `StringBuilder` không tự biến mọi đơn vị `char` đơn lẻ thành ký tự Unicode hoàn chỉnh.

## 9. Chọn overload phù hợp trong thiết kế API

Một quy tắc thực hành hữu ích:

- **Đã có `String`:** dùng `append(String)` trực tiếp.
- **Đang nối dữ liệu số hoặc boolean:** dùng overload primitive để thể hiện rõ giá trị và tránh các phép chuyển kiểu không cần thiết.
- **Đã có mảng `char[]`:** dùng overload `char[]` nếu muốn thêm **nội dung ký tự của mảng**; dùng `offset` và `len` khi chỉ cần một đoạn.
- **Dữ liệu được mô tả bằng `CharSequence`:** dùng overload `CharSequence`; đoạn `[start,end)` thuận tiện cho cắt dãy ký tự chung.
- **Có đối tượng nghiệp vụ:** dùng `append(Object)` khi thật sự muốn biểu diễn `toString()` của nó. Nếu đây là dữ liệu trao đổi hoặc định dạng phải ổn định, hãy tạo formatter chuyên dụng.
- **Mỗi lần thêm một code point từ biến `int`:** xem xét `appendCodePoint`, vì `append(int)` sẽ viết số.
- **Có `null`:** xác định chính sách rõ ràng để không vô tình tạo chữ `"null"` hoặc ném lỗi mảng.

Khi xây dựng chuỗi nhiều bước, cú pháp `append` giúp người đọc thấy thứ tự nối và tránh viết nhiều biểu thức `String` trung gian. Tuy nhiên không phải mọi đoạn ghép đều cần builder: với những phép nối ngắn, `+` thường dễ đọc và trình biên dịch/JVM hiện đại có thể tối ưu. Chọn theo tính rõ ràng và nhu cầu thực tế, không theo một quy tắc tuyệt đối.

### Ví dụ 7: xây dựng dòng mô tả đầy đủ

Tạo tệp `AppendRecordDemo.java`:

```java
public class AppendRecordDemo {
    static String render(String id, int quantity, boolean active, char[] token) {
        StringBuilder builder = new StringBuilder();
        builder.append("id=").append(id)
               .append("; qty=").append(quantity)
               .append("; active=").append(active)
               .append("; token=").append(token, 0, token.length);
        return builder.toString();
    }

    public static void main(String[] args) {
        char[] token = {'A', 'B', 'C'};
        String rendered = render("p-1", 3, true, token);

        System.out.println(rendered);
        token[0] = 'Z';
        System.out.println(rendered);
    }
}
```

```bash
javac -encoding UTF-8 AppendRecordDemo.java
java AppendRecordDemo
```

Kết quả:

```text
id=p-1; qty=3; active=true; token=ABC
id=p-1; qty=3; active=true; token=ABC
```

Dữ liệu `char[]` được nối vào builder rồi `toString()` trả về một `String` bất biến. Thay đổi mảng gốc sau đó không làm đổi chuỗi `rendered`.

**Giới hạn của ví dụ:** phương thức giả định `token` khác `null`. Trong ứng dụng thực tế, nếu có thể nhận null, phải đặt điều kiện kiểm tra hoặc định nghĩa giá trị thay thế trước khi dùng `token.length`.

## 10. Những nhầm lẫn thường gặp

**Nhầm 1 — tưởng tất cả các overload giống nhau.** Với `String`, `Object`, `char[]` và `CharSequence`, kết quả có thể giống nhau trong trường hợp bình thường nhưng rất khác khi gặp mảng, null hoặc kiểu đối số tổng quát.

**Nhầm 2 — tưởng `append(Object)` nối phần tử của mọi mảng.** Nó dùng `String.valueOf(Object)` và có thể gọi `Object.toString()` của mảng. Với `char[]`, chỉ overload chuyên dụng mới thêm nội dung các phần tử theo mong muốn.

**Nhầm 3 — viết `append(null)` và đoán là thêm `"null"`.** Lời gọi bị mơ hồ overload; cần cast hoặc tham chiếu có kiểu khai báo. Sau khi chọn kiểu, `String`/`Object`/`CharSequence` null thêm `"null"`, còn `char[]` null ném `NullPointerException`.

**Nhầm 4 — dùng `append(65)` để thêm `'A'`.** Số nguyên 65 được biểu diễn thành `"65"`. Muốn chữ `A`, dùng `append('A')` hoặc API Unicode phù hợp.

**Nhầm 5 — tưởng `append(char[], offset, len)` lấy chỉ số kết thúc.** `len` là số phần tử; ví dụ `offset=1, len=3` lấy các vị trí 1, 2, 3.

**Nhầm 6 — áp quy tắc mảng sang `CharSequence`.** `append(sequence, start, end)` dùng khoảng **[start, end)**, tức `end` là vị trí loại trừ, không phải số phần tử.

**Nhầm 7 — nghĩ builder chỉ tạo một chuỗi mới và không sửa đối tượng cũ.** `append` làm thay đổi chính `StringBuilder` và trả lại builder đó. Mọi tham chiếu đang giữ builder đều nhìn thấy nội dung mới.

**Nhầm 8 — nghĩ builder vẫn liên kết tới mảng hoặc nguồn `CharSequence`.** Sau khi đã append thành công, văn bản được ghi vào builder đích; việc thay đổi nguồn về sau không tự cập nhật ký tự đã thêm.

**Nhầm 9 — dùng `append(Object)` như chuẩn serialize.** `toString()` có thể thay đổi theo implementation, không cung cấp schema hay escaping. Định dạng lưu trữ/trao đổi cần một hợp đồng riêng.

**Nhầm 10 — bỏ qua Unicode.** `char` là code unit UTF-16, không phải mọi Unicode code point; `append(int)` là thêm số, khác `appendCodePoint(int)`.

**Nhầm 11 — mặc định builder thread-safe.** `StringBuilder` không đồng bộ hóa mọi thao tác để dùng chung an toàn qua nhiều luồng; nếu cần chia sẻ và sửa đồng thời, phải thiết kế cơ chế đồng bộ phù hợp. Dùng `StringBuffer` có đồng bộ hóa cho các thao tác riêng lẻ nhưng cũng cần xem lại toàn bộ workflow nhiều bước.

## 11. Tự luyện tập

### Câu 1: kiểu primitive

```java
StringBuilder b = new StringBuilder();
b.append(7).append('7').append(true);
System.out.println(b);
```

Kết quả:

```text
77true
```

Lần đầu thêm chữ số `7` từ `int`, lần hai thêm ký tự `'7'`, lần ba thêm chữ `true`. Không có dấu phân cách tự động.

### Câu 2: khác nhau giữa `char[]` và `Object`

Với `char[] data = {'H', 'i'};`, lời gọi `append(data)` có nội dung gì? **`Hi`** vì chọn overload `char[]`.

Còn `append((Object) data)`? **Không bảo đảm là `Hi`**, vì dùng biểu diễn `toString()` của đối tượng mảng; phần hậu tố định danh không nên đoán trong kiểm thử.

### Câu 3: `offset, len` so với `start, end`

```java
char[] a = {'a', 'b', 'c', 'd', 'e'};
CharSequence s = "abcde";

System.out.println(new StringBuilder().append(a, 1, 3));
System.out.println(new StringBuilder().append(s, 1, 3));
```

Kết quả:

```text
bcd
bc
```

Với mảng: lấy **3 phần tử** từ vị trí 1. Với `CharSequence`: lấy các vị trí từ 1 đến trước 3, nên chỉ có **2 ký tự**.

### Câu 4: null

Dự đoán:

```java
System.out.println(new StringBuilder().append((String) null));
System.out.println(new StringBuilder().append((CharSequence) null));
```

Kết quả:

```text
null
null
```

Nhưng nếu đổi thành `append((char[]) null)`, chương trình ném `NullPointerException`; nếu bỏ cast và viết `append(null)` thì lỗi nằm ở **biên dịch** do mơ hồ overload.

### Câu 5: đối tượng mutable khác với nội dung đã được append

```java
StringBuilder source = new StringBuilder("one");
StringBuilder target = new StringBuilder();
target.append((CharSequence) source);
source.append(" two");
System.out.println(target);
System.out.println(source);
```

Kết quả:

```text
one
one two
```

Đối tượng `source` mutable, nhưng `target` không phải view của `source`. Nó giữ những ký tự đã append vào thời điểm lời gọi hoàn thành.

## Kết luận

**`StringBuilder.append(...)` có một mục tiêu chung — thêm dữ liệu vào cuối builder — nhưng lựa chọn overload quyết định ý nghĩa của đối số.** `String` và `CharSequence` cung cấp nội dung văn bản; primitive được biểu diễn dưới dạng ký tự; `Object` dựa vào `String.valueOf`/`toString()`; `char[]` được nối theo từng code unit và có overload cắt theo `offset, len`. Hãy chú ý kiểu biểu thức tại thời điểm biên dịch, xử lý `null` tường minh, phân biệt khoảng `[start,end)` với `offset,len`, và nhớ rằng `append` **làm thay đổi chính `StringBuilder`, không làm thay đổi nguồn đã được nối**.
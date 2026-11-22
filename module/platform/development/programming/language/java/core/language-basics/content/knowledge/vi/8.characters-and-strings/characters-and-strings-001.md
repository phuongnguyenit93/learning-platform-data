# Phân biệt `char`, `String` và mảng `char` trong Java 17+

## 1. Ba cách biểu diễn ký tự: không thể dùng thay thế tùy ý

Java có ba dạng thường gặp khi làm việc với văn bản:

- **`char`**: một giá trị nguyên thủy 16 bit, biểu diễn **một đơn vị mã UTF-16**. Viết literal bằng dấu nháy đơn, ví dụ `'A'`.
- **`String`**: một đối tượng chuỗi ký tự **bất biến** (*immutable*), biểu diễn một dãy đơn vị mã UTF-16. Viết literal bằng dấu nháy kép, ví dụ `"Java"`.
- **`char[]`**: một **mảng có độ dài cố định** gồm các phần tử `char`, có thể thay đổi phần tử bằng phép gán.

~~~java
char initial = 'J';
String word = "Java";
char[] letters = {'J', 'a', 'v', 'a'};
~~~

Ba biến trên khác nhau về **kiểu**, **cách truy cập**, **khả năng sửa dữ liệu** và **cách sao chép**.

| Thuộc tính | `char` | `String` | `char[]` |
|---|---|---|---|
| Phân loại | Primitive | Class `java.lang.String` | Array object |
| Nội dung | Một UTF-16 code unit | Dãy UTF-16 code units | Các phần tử `char` |
| Cách khởi tạo ví dụ | `'J'` | `"Java"` | `{'J','a','v','a'}` |
| Lấy độ dài | Không có thuộc tính độ dài | `word.length()` | `letters.length` |
| Truy cập vị trí | Không có chỉ số | `word.charAt(i)` | `letters[i]` |
| Sửa nội dung tại vị trí | Không áp dụng | **Không thể** sửa tại chỗ | `letters[i] = 'K'` |
| Giá trị `null` | Không nhận được | Có thể là `null` | Có thể là `null` |

**Cần nhớ:** `String` **không phải** là cách viết khác của `char[]`; chúng là hai loại đối tượng khác nhau với API và tính bất biến khác nhau.

## 2. `char`: một đơn vị mã UTF-16, không nhất thiết là một ký tự người nhìn thấy

`char` dùng nháy đơn:

~~~java
char letter = 'A';
char digit = '5';
char newline = '\n';
char backslash = '\\';

System.out.println(letter);           // A
System.out.println((int) digit);      // 53: mã UTF-16 của '5'
System.out.println((int) newline);    // 10: LF
~~~

`'5'` là **ký tự chữ số**, không phải số nguyên `5`. Ép `char` sang `int` cho giá trị số của code unit đó:

~~~java
char value = 'A';
int codeUnit = value;
System.out.println(codeUnit); // 65
~~~

Java `char` có miền giá trị từ 0 đến 65535 (`Character.MIN_VALUE` đến `Character.MAX_VALUE`). Đó là **giá trị UTF-16 code unit**, không phải toàn bộ miền Unicode code point.

Các ký tự Unicode ngoài **Basic Multilingual Plane** (BMP) như emoji thường được biểu diễn bằng **cặp surrogate** gồm hai `char`. Vì thế:

- Một Unicode code point có thể cần **hai `char`**.
- Một ký tự hiển thị như cụm chữ có dấu hoặc emoji có thể gồm **nhiều code point**.
- Không nên mặc định `char` = một chữ người dùng nhìn thấy.

### Cú pháp sai dễ gặp

~~~java
// char empty = '';    // Sai: char literal rỗng
// char two = 'AB';    // Sai: có hai ký tự thông thường
// char text = "A";    // Sai kiểu: String không tự thành char
// char missing = null; // Sai: null không gán được cho primitive char
~~~

Khi cần một chữ cái từ chuỗi, dùng `charAt(index)` và kiểm tra rằng chuỗi không rỗng và index hợp lệ.

## 3. `String`: chuỗi bất biến với API xử lý văn bản

`String` là **kiểu tham chiếu** trong `java.lang`:

~~~java
String label = "Java";
System.out.println(label.length());  // 4
System.out.println(label.charAt(0)); // J
System.out.println(label.substring(1, 3)); // av
~~~

Các phương thức như `replace`, `toUpperCase`, `concat` hoặc `substring` **không sửa nội dung của đối tượng String cũ**. Chúng trả kết quả chuỗi phù hợp, có thể là cùng instance hoặc instance khác theo hợp đồng API; điểm cần quan tâm là **giá trị chuỗi ban đầu không đổi**.

~~~java
String title = "Java";
String modified = title.replace('J', 'L');

System.out.println(title);    // Java
System.out.println(modified); // Lava
~~~

Muốn biến `title` giữ kết quả mới, bạn **gán lại biến**:

~~~java
title = title.replace('J', 'L');
System.out.println(title); // Lava
~~~

Ở đây biến tham chiếu được gán một giá trị tham chiếu khác; đối tượng `String` ban đầu không bị sửa.

Một `String` có thể chứa `null` nếu chưa có dữ liệu (khi bạn gán `null` cho biến); nhưng `null` không phải chuỗi rỗng `""`. Cần phân biệt:

~~~java
String missing = null;
String empty = "";
System.out.println(empty.length()); // 0
// missing.length(); // Nếu chạy: NullPointerException
~~~

## 4. `char[]`: mảng có thể sửa từng phần tử

Mảng `char` có kích thước được xác định lúc tạo và **không thể đổi chiều dài ngay trên cùng một array object**. Nhưng có thể sửa phần tử:

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
letters[0] = 'K';

System.out.println(new String(letters)); // Kava
System.out.println(letters.length);      // 4
~~~

Với mảng rỗng hoặc mảng khởi tạo bằng kích thước:

~~~java
char[] buffer = new char[3];
System.out.println(buffer.length); // 3
System.out.println((int) buffer[0]); // 0: giá trị mặc định '\u0000'
~~~

Mảng là **đối tượng tham chiếu**; một biến mảng có thể được gán sang mảng khác:

~~~java
char[] data = {'A'};
data = new char[] {'B', 'C'};
System.out.println(data.length); // 2
~~~

Câu lệnh trên **không kéo dài mảng cũ**; nó thay giá trị tham chiếu trong biến `data` để trỏ đến một mảng khác.

### `length()` khác `length`

~~~java
String word = "cat";
char[] chars = {'c', 'a', 't'};

System.out.println(word.length()); // 3
System.out.println(chars.length);  // 3
~~~

`String.length()` là lời gọi method; `char[].length` là **field độ dài** của array. Viết `chars.length()` hoặc `word.length` sẽ không biên dịch.

## 5. Chuyển đổi qua lại: `String` và `char[]`

Hai API thực dụng nhất:

~~~java
String word = "Java";
char[] chars = word.toCharArray(); // String -> char[]
String restored = new String(chars); // char[] -> String
~~~

Các phép chuyển đổi này hữu ích vì tạo dữ liệu riêng để xử lý:

~~~java
String original = "Java";
char[] copy = original.toCharArray();
copy[0] = 'K';

System.out.println(new String(copy)); // Kava
System.out.println(original);         // Java
~~~

`toCharArray()` cung cấp **một mảng mới** chứa các code unit của chuỗi; sửa mảng đó không làm biến đổi `String` nguồn.

Ở chiều ngược lại, `new String(chars)` lấy **bản sao nội dung** mảng tại thời điểm tạo chuỗi:

~~~java
char[] buffer = {'A', 'B'};
String snapshot = new String(buffer);
buffer[0] = 'Z';

System.out.println(snapshot);          // AB
System.out.println(new String(buffer)); // ZB
~~~

**Không có liên kết đồng bộ tự động giữa mảng và String.** Sau khi chuyển đổi, mỗi bên giữ nội dung theo quy tắc của loại đối tượng đó.

Các lựa chọn khác:

- `String.valueOf(chars)` tạo `String` từ mảng ký tự.
- `String.valueOf(oneChar)` tạo chuỗi một phần tử từ `char`.
- `String.valueOf(chars, offset, count)` chọn một đoạn của mảng, nhưng phải kiểm tra phạm vi hợp lệ.
- `Character.toString(ch)` chuyển một `char` thành `String`.

~~~java
char initial = 'J';
String oneLetter = String.valueOf(initial);
System.out.println(oneLetter); // J
~~~

## 6. So sánh: nội dung chuỗi và nội dung mảng

Với `String`, thường dùng **`equals`** để so sánh nội dung:

~~~java
String first = new String(new char[] {'o', 'k'});
String second = new String(new char[] {'o', 'k'});

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

`==` ở ví dụ kiểm tra **hai tham chiếu có trỏ cùng object không**, không phải hai chuỗi có cùng ký tự không.

Với `char[]`, **mảng không tự so sánh phần tử bằng `equals`**. Sử dụng `java.util.Arrays.equals`:

~~~java
char[] a = {'o', 'k'};
char[] b = {'o', 'k'};

System.out.println(a == b);                 // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Để so sánh một mảng với một chuỗi, có thể chuyển đổi và gọi `equals`, hoặc thiết kế API nhận cùng một biểu diễn ngay từ đầu:

~~~java
String expected = "ok";
char[] actual = {'o', 'k'};
System.out.println(expected.equals(new String(actual))); // true
~~~

**Lưu ý với dữ liệu nhạy cảm:** chuyển `char[]` chứa thông tin bí mật thành `String` có thể để lại bản sao bất biến khó xóa khỏi bộ nhớ. Khi bảo mật là yêu cầu, tránh tạo những bản sao không cần thiết; việc xóa mảng chỉ làm sạch chính mảng đó và **không đảm bảo xóa mọi bản sao dữ liệu**.

## 7. Cách in `char[]` và bẫy overload

`PrintStream` có overload `println(char[])` nên ví dụ:

~~~java
char[] data = {'J', 'a', 'v', 'a'};
System.out.println(data);
~~~

sẽ in:

~~~text
Java
~~~

Điều này **không** có nghĩa bản thân array tự biến thành String. Đối với một mảng tham chiếu được xem là `Object`, cách chọn overload và biểu diễn mặc định có thể khác; không nên dựa vào `toString()` của mảng để lấy nội dung văn bản.

Khi mục tiêu là rõ ràng, viết:

~~~java
System.out.println(new String(data));          // Java
System.out.println(java.util.Arrays.toString(data)); // [J, a, v, a]
~~~

`Arrays.toString(char[])` là biểu diễn danh sách các phần tử để **debug**, trong khi `new String(data)` là **nội dung văn bản**.

## 8. Ranh giới Unicode khi chuyển giữa String và char[]

Cả `String.length()` lẫn `char[].length` đều tính **đơn vị mã UTF-16**, nên một Unicode code point ngoài BMP có thể chiếm hai `char`. Việc chuyển `String` sang `char[]` **không tự tách thành các Unicode code point**:

~~~java
int emoji = 0x1F600; // U+1F600.
char[] twoUnits = Character.toChars(emoji);
String symbol = new String(twoUnits);

System.out.println(twoUnits.length); // 2
System.out.println(symbol.length()); // 2
System.out.println(symbol.codePointCount(0, symbol.length())); // 1
~~~

Nếu sửa riêng một phần tử của `twoUnits`, có thể phá **surrogate pair**. Khi mục tiêu là xử lý code point, dùng `codePoints()` hoặc `codePointAt` ở biên UTF-16 hợp lệ; nếu mục tiêu là ký tự người dùng nhìn thấy, một **grapheme cluster** đôi khi còn gồm nhiều code point. Bài này tập trung lựa chọn `char`, `String`, `char[]` và quy tắc copy/mutability; các vị trí surrogate, công thức ghép và cách cắt an toàn được kiểm chứng chi tiết trong bài về UTF-16.


## 9. Chương trình Java 17 chạy độc lập và expected output

Tạo tệp **`CharStringArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class CharStringArrayDemo {
    private CharStringArrayDemo() {}

    public static void main(String[] args) {
        char initial = 'J';
        String word = "Java";
        char[] letters = {'J', 'a', 'v', 'a'};

        System.out.println("char: " + initial);
        System.out.println("string: " + word);
        System.out.println("array: " + new String(letters));
        System.out.println("lengths: " + word.length()
                + " / " + letters.length);
        System.out.println("index 1: " + word.charAt(1)
                + " / " + letters[1]);

        String snapshot = new String(letters);
        letters[0] = 'K';
        System.out.println("edited array: " + new String(letters));
        System.out.println("snapshot: " + snapshot);
        System.out.println("original String: " + word);

        char[] copied = word.toCharArray();
        copied[1] = 'o';
        System.out.println("toCharArray copy: " + new String(copied));
        System.out.println("String remains: " + word);

        String updated = word.replace('J', 'L');
        System.out.println("replace result: " + updated);
        System.out.println("replace source: " + word);

        System.out.println("equal text: " + word.equals(
                new String(new char[] {'J', 'a', 'v', 'a'})));
        System.out.println("equal arrays: " + Arrays.equals(
                word.toCharArray(), new char[] {'J', 'a', 'v', 'a'}));

        System.out.println("char arithmetic: " + ('A' + 'B'));
        System.out.println("char appended: " + ("A" + 'B'));

        int codePoint = 0x1F600;
        char[] twoUnits = Character.toChars(codePoint);
        String symbol = new String(twoUnits);
        System.out.println("supplementary units: " + twoUnits.length);
        System.out.println("supplementary String.length: "
                + symbol.length());
        System.out.println("supplementary codepoints: "
                + symbol.codePointCount(0, symbol.length()));
        System.out.println("high surrogate: "
                + Character.isHighSurrogate(twoUnits[0]));
    }
}
~~~

Yêu cầu **JDK 17+**; mở terminal tại thư mục chứa source.

**Bash (Linux/macOS):**

~~~bash
java -version
javac --release 17 -encoding UTF-8 CharStringArrayDemo.java
java -cp . CharStringArrayDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac --release 17 -encoding UTF-8 .\CharStringArrayDemo.java
java -cp . CharStringArrayDemo
~~~

**Expected output:**

~~~text
char: J
string: Java
array: Java
lengths: 4 / 4
index 1: a / a
edited array: Kava
snapshot: Java
original String: Java
toCharArray copy: Jova
String remains: Java
replace result: Lava
replace source: Java
equal text: true
equal arrays: true
char arithmetic: 131
char appended: AB
supplementary units: 2
supplementary String.length: 2
supplementary codepoints: 1
high surrogate: true
~~~

**Kiểm chứng cốt lõi:**

- Sửa `letters[0]` chỉ thay đổi **mảng**, không thay đổi `snapshot` hoặc `word`.
- Sửa mảng do `toCharArray()` trả về cũng **không tác động** đến `word`.
- `replace` tạo giá trị chuỗi mới, không sửa `word` ban đầu.
- `'A' + 'B'` là phép cộng số với các giá trị `char`, tạo `int` **131**; biểu thức `"A" + 'B'` nối chuỗi thành **AB**.
- Code point U+1F600 có hai UTF-16 code units nhưng chỉ là một Unicode code point.

## 10. Lỗi thường gặp và cách khắc phục

| Trường hợp | Sai ở đâu? | Cách đúng |
|---|---|---|
| `char ch = "A";` | Literal `"A"` là `String` | `char ch = 'A';` |
| `String s = 'A';` | Không gán trực tiếp `char` cho `String` | `String s = String.valueOf('A');` |
| `word[0]` | String không có toán tử lập chỉ số `[]` | `word.charAt(0)` |
| `letters.charAt(0)` | Mảng không có method `charAt` | `letters[0]` |
| `word.length` | String không có field public `length` | `word.length()` |
| `letters.length()` | Mảng dùng field `length` | `letters.length` |
| `word.charAt(0) = 'K';` | Không thể gán cho kết quả method; String bất biến | Tạo String mới hoặc sửa mảng rồi chuyển lại |
| `a.equals(b)` với hai `char[]` khác nhau | Mảng không so sánh từng phần tử | `Arrays.equals(a, b)` |
| `str1 == str2` để so nội dung | So sánh tham chiếu | `str1.equals(str2)` khi không null |
| Một emoji có `length() == 2` | `length` tính UTF-16 units | Dùng API code point theo mục đích |
| `chars.toString()` | Không chuyển mảng thành văn bản như mong đợi | `new String(chars)` |
| `String s = null; s.length()` | Gọi method trên null | Kiểm tra null trước khi truy cập |

### Lỗi vượt chỉ số

Cả hai cách truy cập đều cần chỉ số không âm và **nhỏ hơn độ dài**:

~~~java
String text = "ABC";
char[] array = {'A', 'B', 'C'};

// text.charAt(3); // StringIndexOutOfBoundsException nếu chạy
// char c = array[3]; // ArrayIndexOutOfBoundsException nếu chạy
~~~

Với đoạn code trên, chỉ số hợp lệ là 0, 1, 2. Java **không** tự trả `'\0'` khi đọc vượt cuối.

## 11. Chọn biểu diễn phù hợp với công việc

| Nhiệm vụ | Nên cân nhắc |
|---|---|
| Lưu nhãn, tên, thông báo, đoạn văn bản thông thường | `String` |
| So sánh/chuyển đổi/chia đoạn văn bản bằng các API chuẩn | `String` |
| Xử lý một code unit UTF-16 đơn lẻ | `char` |
| Cần buffer có thể sửa từng code unit tại chỉ số | `char[]` |
| Xây dựng chuỗi bằng nhiều lần thêm/nối/sửa | `StringBuilder` thường tiện hơn thao tác mảng |
| Duyệt ký tự Unicode ngoài BMP đúng code point | `String.codePoints()` và API `Character` |
| Xử lý dữ liệu bí mật cần chủ động xóa buffer sau dùng | Có thể dùng `char[]` cùng quy trình hạn chế bản sao; không phải bảo đảm tuyệt đối |

Một lựa chọn tốt không chỉ dựa vào kích thước bộ nhớ: hãy cân nhắc **tính bất biến**, API mà thư viện yêu cầu, khả năng sửa dữ liệu và đúng đơn vị Unicode mà nghiệp vụ quan tâm.

### Về `StringBuilder` khi cần sửa nhiều lần

~~~java
StringBuilder builder = new StringBuilder();
builder.append('J').append("ava");
builder.setCharAt(0, 'K');
String result = builder.toString();

System.out.println(result); // Kava
~~~

`StringBuilder` là đối tượng mutable chuyên hỗ trợ xây dựng và chỉnh sửa chuỗi hiệu quả; **nó không phải kiểu `String` và cũng không phải `char[]`**. Sau khi gọi `toString()`, giá trị chuỗi trả về có tính bất biến như các `String` khác.

## 12. Bài tập kèm đáp án

### Bài A — phân loại kiểu

~~~java
char a = 'X';
String b = "X";
char[] c = {'X'};
~~~

**Đáp án:** `a` là primitive char; `b` là String object; `c` là mảng object một phần tử char. Dù cùng thể hiện chữ X, chúng không phải cùng kiểu.

### Bài B — chuỗi có đổi theo mảng không?

~~~java
char[] data = {'a', 'b'};
String s = new String(data);
data[0] = 'z';
System.out.println(s);
System.out.println(new String(data));
~~~

**Đáp án:**

~~~text
ab
zb
~~~

`new String(data)` lấy bản sao nội dung tại thời điểm tạo.

### Bài C — khác biệt `length()` và `length`

~~~java
String word = "cat";
char[] data = word.toCharArray();
System.out.println(word.length());
System.out.println(data.length);
~~~

**Đáp án:** lần lượt `3` và `3`. Cú pháp khác nhau vì String dùng method, array dùng field.

### Bài D — so sánh hai mảng

~~~java
char[] first = {'o', 'k'};
char[] second = {'o', 'k'};
System.out.println(first == second);
System.out.println(java.util.Arrays.equals(first, second));
~~~

**Đáp án:**

~~~text
false
true
~~~

### Bài E — một code point ngoài BMP chiếm bao nhiêu char?

~~~java
String s = new String(Character.toChars(0x1F600));
System.out.println(s.length());
System.out.println(s.codePointCount(0, s.length()));
~~~

**Đáp án:**

~~~text
2
1
~~~

Java String được lập chỉ số theo UTF-16 code units. Một code point ngoài BMP thường cần surrogate pair gồm hai `char`.

## 13. Checklist trước khi áp dụng

- [ ] Phân biệt `char` primitive, `String` immutable và `char[]` mutable.
- [ ] Dùng nháy đơn cho `char`, nháy kép cho `String`.
- [ ] Nhớ `String.length()` và `char[].length` khác cú pháp.
- [ ] Dùng `charAt(i)` cho String, `[i]` cho mảng.
- [ ] Biết `new String(chars)` và `toCharArray()` tạo dữ liệu không bị sửa theo bên còn lại.
- [ ] Dùng `String.equals` cho chuỗi và `Arrays.equals` cho mảng.
- [ ] Hiểu `char` là UTF-16 code unit, không phải mọi Unicode code point.
- [ ] Phân biệt phép cộng số `'A' + 'B'` với nối chuỗi `"A" + 'B'`.
- [ ] Kiểm tra null và chỉ số trước các phép truy cập.
- [ ] Biên dịch và chạy `CharStringArrayDemo.java` trên JDK 17+ rồi đối chiếu output.

**Kết luận:** `char` giữ một đơn vị mã UTF-16; `String` giữ dãy ký tự **bất biến**; `char[]` giữ dãy `char` **có thể sửa tại từng chỉ số**. Lựa chọn đúng kiểu và hiểu rõ quy tắc copy/chuyển đổi giúp tránh lỗi vô tình thay dữ liệu, so sánh sai và xử lý Unicode không chính xác.
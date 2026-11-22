# Toán tử `+` và phép chuyển giá trị thành chuỗi trong Java

## 1. Khi nào `+` là phép nối chuỗi?

Trong Java, ký hiệu `+` được dùng cho hai mục đích: **cộng số** và **nối chuỗi** (*string concatenation*). Khi một toán hạng của phép `+` có kiểu `String`, phép toán đó tạo giá trị `String` bằng cách nối biểu diễn văn bản của hai toán hạng theo thứ tự từ trái sang phải.

```java
String language = "Java";
int version = 17;

String message = language + " " + version;
System.out.println(message); // Java 17
```

Ở ví dụ này, `version` là một số nguyên `int` nhưng được chuyển thành văn bản `"17"` khi tham gia phép nối với `String`. Kết quả cuối cùng là một chuỗi, không phải phép cộng số học.

Cần phân biệt ba khái niệm:

- **Đối tượng `String`:** đại diện cho văn bản trong Java; nội dung không thể sửa tại chỗ.
- **Toán tử `+`:** tạo biểu thức nối chuỗi khi có toán hạng kiểu `String`; cũng có thể cộng số nếu các toán hạng phù hợp là kiểu số.
- **Chuyển thành chuỗi:** tạo biểu diễn văn bản của giá trị `int`, `double`, `boolean`, `char`, đối tượng hoặc `null` để tham gia phép nối.

Các đoạn mã ngắn trong bài được hiểu là viết **trong một phương thức Java**, trừ chương trình hoàn chỉnh có `class` và `main` ở phần sau.

## 2. Quy tắc phân biệt cộng số với nối chuỗi

### Trường hợp 1: cả hai toán hạng là số

```java
int result = 2 + 3;          // 5
double total = 2.5 + 1.5;   // 4.0
```

Đây là cộng số học. Các kiểu số nguyên thủy có thể trải qua **numeric promotion** theo quy tắc Java. Chưa xuất hiện `String`, nên chưa có nối chuỗi.

### Trường hợp 2: có một toán hạng là `String`

```java
String one = "Java" + 17;     // "Java17"
String two = 17 + "Java";     // "17Java"
String three = "score=" + 5; // "score=5"
```

Java thực hiện **string conversion** đối với toán hạng còn lại. Phép nối giữ nguyên thứ tự: `"Java" + 17` khác `17 + "Java"`.

Một giá trị số đặt trong dấu nháy kép đã là chuỗi:

```java
String digits = "17"; // String
int number = 17;      // int
```

`"17" + 3` trả `"173"`, trong khi `17 + 3` trả số `20`.

### Trường hợp 3: không phải mọi kiểu đều dùng được với `+`

Ví dụ hai đối tượng tùy ý không thể cộng với nhau chỉ vì chúng có phương thức `toString()`:

```java
Object a = new Object();
Object b = new Object();

// Object invalid = a + b; // Không biên dịch
String valid = "objects: " + a + ", " + b;
```

Ở dòng hợp lệ, các phép nối đều có toán hạng `String`. Java sẽ chuyển đối tượng thành biểu diễn văn bản; biểu diễn mặc định của `Object` thường là tên lớp kèm mã hash ở dạng hex, không phải mô tả có ý nghĩa của dữ liệu nghiệp vụ.

## 3. Thứ tự kết hợp từ trái sang phải: bẫy `"1" + 2 + 3`

Các phép `+` cùng độ ưu tiên kết hợp trái: `1 + 2 + "3"` tạo `"33"`, còn `"1" + 2 + 3` tạo `"123"`. Dấu ngoặc cho biết rõ phép cộng số nào phải làm trước:

```java
System.out.println("sum=" + 2 + 3);   // sum=23
System.out.println("sum=" + (2 + 3)); // sum=5
```

Phép nhân vẫn có độ ưu tiên cao hơn `+`. Bài **Thứ tự kết hợp trái–phải của + với số và chuỗi** triển khai bảng phân tích biểu thức, ví dụ có tác dụng phụ và bẫy tràn số; ở đây chỉ cần biết lúc nào phép `+` đang trả về số hay `String`.

## 4. Java chuyển các giá trị thành chuỗi như thế nào?

Đối với phép nối `String`, Java chuyển các toán hạng còn lại theo **quy tắc string conversion của ngôn ngữ**. Bảng dưới đây nêu các trường hợp thường gặp.

| Giá trị tham gia phép nối | Biểu diễn văn bản điển hình | Ví dụ |
|---|---|---|
| `int` | Chữ số thập phân có thể kèm dấu âm | `"n=" + 42` → `"n=42"` |
| `long` | Chữ số của số nguyên dài | `"n=" + 42L` → `"n=42"` |
| `double` | Biểu diễn thập phân của số dấu phẩy động | `"x=" + 2.5` → `"x=2.5"` |
| `boolean` | `"true"` hoặc `"false"` | `"ok=" + true` → `"ok=true"` |
| `char` | Ký tự được biểu diễn bởi giá trị `char` | `"c=" + 'A'` → `"c=A"` |
| `String` | Nội dung chuỗi hiện có | `"A" + "B"` → `"AB"` |
| Tham chiếu `null` | Văn bản `"null"` | `"x=" + (String) null` → `"x=null"` |
| Đối tượng thông thường | Dựa trên biểu diễn `toString()` | Có thể được tùy biến trong lớp |

Với các giá trị số nguyên, việc nối chuỗi **không làm phép cộng số** một lần nữa. Java chỉ lấy biểu diễn văn bản của giá trị ở thời điểm cần nối.

Đối với `float`/`double`, biểu diễn mặc định của toán tử nối không phải công cụ định dạng số dành cho người dùng theo vùng miền. Nếu cần dấu phân cách hàng nghìn, làm tròn theo số chữ số cố định hoặc quy tắc locale, hãy sử dụng API định dạng như `String.format(...)`, `NumberFormat` hoặc `DecimalFormat` theo yêu cầu cụ thể.

### Đối tượng: vai trò của `toString()`

Với một đối tượng không phải `null`, quy tắc string conversion có thể dựa trên phương thức `toString()` của đối tượng đó. Một lớp thường ghi đè `toString()` để cung cấp biểu diễn có ý nghĩa:

```java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book(" + title + ")";
    }
}
```

Khi dùng trong phương thức của lớp khác:

```java
Book book = new Book("Java");
System.out.println("item=" + book);
// item=Book(Java)
```

`toString()` là mô tả văn bản của đối tượng, không nhất thiết là dữ liệu đã được chuẩn hóa, không phải định dạng trao đổi JSON, và không nên mặc nhiên bao gồm thông tin nhạy cảm. Trong hệ thống thực tế, thiết kế `toString()` theo mục đích gỡ lỗi hoặc hiển thị phù hợp.

## 5. `null` trong phép nối chuỗi: không giống gọi phương thức trên `null`

Một tham chiếu `String` có thể mang giá trị `null`:

```java
String name = null;

System.out.println("name=" + name); // name=null
```

Phép nối biến `name` đang là `null` thành văn bản `"null"`. Kết quả là chuỗi thông thường `"name=null"`; đây **không phải** đối tượng `null`.

Tuy nhiên, điều đó không có nghĩa có thể gọi phương thức lên tham chiếu `null`:

```java
String name = null;

// name.concat("!"); // NullPointerException
// name.length();     // NullPointerException

System.out.println("name=" + name); // Hợp lệ
```

Cần phân biệt:

- **String conversion trong phép `+`:** có quy tắc riêng để biểu diễn tham chiếu `null` thành `"null"`.
- **Lời gọi phương thức `name.concat(...)`:** yêu cầu `name` tham chiếu đến đối tượng `String`; nếu `null`, ném `NullPointerException`.

Nếu `"null"` là đầu ra không mong muốn, phải xác định cách xử lý thiếu dữ liệu:

```java
String name = null;
String display = name == null ? "(chưa có)" : name;
System.out.println("Tên: " + display);
// Tên: (chưa có)
```

Đây là chính sách hiển thị do chương trình quyết định. Đừng nhầm chuỗi bốn ký tự `"null"` với tham chiếu `null` thật.

## 6. `char` có thể là ký tự hoặc tham gia phép cộng số

`char` là đơn vị mã UTF-16 có thể tham gia cộng số sau numeric promotion; khi nằm cạnh một `String`, nó được nối như văn bản:

```java
System.out.println('A' + 1);       // 66 (int)
System.out.println("A" + 1);       // A1
System.out.println("" + 'A' + 1);  // A1
```

Phép cộng mã của `char` không phải cách xử lý mọi Unicode code point. Bài **Phân biệt ký tự cộng số với nối chuỗi** phân tích chuyển kiểu, ký tự chữ số, dấu ngoặc và surrogate pair.

## 7. Các mảng không tự được nối theo từng phần tử

Giả sử có mảng số:

```java
int[] numbers = {1, 2, 3};
```

Biểu thức `"numbers=" + numbers` không cho ra `"numbers=[1, 2, 3]"` theo quy tắc chung. Mảng là một đối tượng; nếu không được chuyển thành mô tả riêng, biểu diễn mặc định thường chứa thông tin kiểu mảng và mã hash, nên không thích hợp làm đầu ra mong muốn. Phần mã hash có thể khác giữa các lượt chạy.

Hãy chọn API phù hợp với ý định:

```java
int[] numbers = {1, 2, 3};
String readable = "numbers=" + java.util.Arrays.toString(numbers);

System.out.println(readable); // numbers=[1, 2, 3]
```

Với mảng đa chiều, có thể cần `Arrays.deepToString(...)` để biểu diễn các mảng lồng nhau.

### Trường hợp `char[]` cũng cần chú ý

```java
char[] letters = {'J', 'a', 'v', 'a'};

String actualText = new String(letters);
System.out.println("letters=" + actualText); // letters=Java
```

Không nên giả định toán tử `+` sẽ tự ghép các phần tử của `char[]` theo cách `new String(letters)` làm. Có các overload của `String.valueOf` dành riêng cho `char[]`, nhưng phép nối qua tham chiếu mảng không phải một lời gọi tùy ý tới overload ấy.

## 8. Ví dụ Java 17+ hoàn chỉnh và stdout

Lưu vào tệp **`StringPlusConversionDemo.java`**:

```java
import java.util.Arrays;

public class StringPlusConversionDemo {
    public static void main(String[] args) {
        String language = "Java";
        int release = 17;
        double rating = 4.5;
        boolean supported = true;

        String summary = "summary=" + language + " " + release
                + ", rating=" + rating + ", supported=" + supported;
        System.out.println(summary);

        System.out.println("left=" + 2 + 3);
        System.out.println("right=" + (2 + 3));
        System.out.println(2 + 3 + " points");
        System.out.println("value=" + 2 + 3 * 4);

        char letter = 'A';
        System.out.println("letter=" + letter + 1);
        System.out.println("code=" + (letter + 1));
        System.out.println("next=" + (char) (letter + 1));

        String missing = null;
        System.out.println("missing=" + missing);
        System.out.println("valueOfMissing=" + String.valueOf(missing));

        int[] numbers = {1, 2, 3};
        System.out.println("numbers=" + Arrays.toString(numbers));

        char[] letters = {'J', 'a', 'v', 'a'};
        System.out.println("letters=" + new String(letters));

        System.out.println("joined=" + String.join(" | ", "A", "B", "C"));

        String source = "Hi";
        String modified = source + "!";
        System.out.println("source=" + source + ", modified=" + modified);

        String folded = "Ja" + "va";
        System.out.println("foldedSameLiteral=" + (folded == "Java"));
    }
}
```

Chạy bằng **JDK 17 trở lên** trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 StringPlusConversionDemo.java
java StringPlusConversionDemo
```

**Stdout chính xác:**

```text
summary=Java 17, rating=4.5, supported=true
left=23
right=5
5 points
value=212
letter=A1
code=66
next=B
missing=null
valueOfMissing=null
numbers=[1, 2, 3]
letters=Java
joined=A | B | C
source=Hi, modified=Hi!
foldedSameLiteral=true
```

Lý giải các kết quả trọng tâm:

1. `summary` chuyển `int`, `double`, `boolean` sang văn bản và nối theo thứ tự.
2. `"left=" + 2 + 3` nối lần lượt thành `"left=23"`, còn `"right=" + (2 + 3)` cộng số trong ngoặc trước, được `"right=5"`.
3. `2 + 3 + " points"` cộng hai số đầu thành `5` rồi nối `" points"`.
4. Phép nhân trong `"value=" + 2 + 3 * 4` có độ ưu tiên cao hơn `+`, nên `3 * 4 = 12`, cuối cùng tạo `"value=212"`.
5. Ký tự `'A'` cộng `1` cho giá trị số `66`, nhưng tham gia nối từ trái sang phải sau một chuỗi cho văn bản `"A1"`.
6. Tham chiếu `missing` là `null`; phép nối và `String.valueOf(missing)` đều có biểu diễn `"null"` trong trường hợp này.
7. `Arrays.toString` biểu diễn giá trị các phần tử mảng; `new String(letters)` tạo văn bản từ mảng `char`.
8. `source + "!"` tạo kết quả được lưu ở `modified`, không sửa nội dung của `source`.
9. `"Ja" + "va"` là **biểu thức hằng chuỗi** được xác định tại thời điểm biên dịch; giá trị chuỗi hằng được intern nên có cùng tham chiếu với literal `"Java"`.

## 9. `String.valueOf(...)`: chuyển giá trị thành chuỗi một cách tường minh

Khi cần tự chuyển một giá trị sang `String` trước khi xử lý tiếp, hãy dùng các overload `String.valueOf(...)` thích hợp.

```java
String number = String.valueOf(42);       // "42"
String yes = String.valueOf(true);        // "true"
String letter = String.valueOf('A');      // "A"
String pi = String.valueOf(3.5);          // "3.5"

Object missing = null;
String absent = String.valueOf(missing);  // "null"
```

Điểm đáng chú ý: `String.valueOf` có nhiều overload như `int`, `long`, `double`, `boolean`, `char`, `char[]` và `Object`. Trình biên dịch lựa chọn overload dựa trên **kiểu biểu thức đối số**.

Ví dụ khác biệt quan trọng với mảng ký tự:

```java
char[] chars = {'J', 'a', 'v', 'a'};

String a = String.valueOf(chars);          // "Java" (overload char[])
String b = String.valueOf((Object) chars); // Biểu diễn đối tượng mảng
```

`b` không được đảm bảo là `"Java"`; nó đi theo overload `Object` và có thể chứa kiểu `[C` cùng mã hash.

**Cẩn thận với `String.valueOf(null)` không có kiểu tường minh.** Vì có nhiều overload nhận kiểu tham chiếu, truyền literal `null` trần có thể chọn overload khác với ý định, đặc biệt là overload `char[]`. Khi cần biểu diễn tham chiếu đối tượng `null` thành `"null"`, hãy dùng đối số có kiểu rõ ràng:

```java
String value = String.valueOf((Object) null); // "null"
```

Nếu đối số thực sự là mảng `char[]` bằng `null`, gọi overload `valueOf(char[])` có thể ném `NullPointerException`. Vì thế kiểu tĩnh của đối số ảnh hưởng đáng kể đến lời gọi `String.valueOf`, dù toán tử `+` thường được dùng thuận tiện cho việc nối văn bản.

### Vì sao đôi khi dùng `String.valueOf` thay cho `+`?

Hai mục đích khác nhau:

- **Tạo một câu văn mới:** `"Số lượng: " + count` diễn đạt trực tiếp và dễ đọc.
- **Chuyển một giá trị thành chuỗi riêng biệt:** `String.valueOf(count)` làm rõ bạn cần một `String` để truyền cho API khác hoặc lưu trước.

Không cần chủ động viết `String.valueOf` cho **mọi** toán hạng khi đã dùng phép nối: Java vốn có quy tắc string conversion cho toán tử `+`.

## 10. Chuyển chuỗi thành số là hướng ngược lại

Khi `String` chứa chữ số, dùng toán tử `+` với số **không** tự phân tích chuỗi thành số:

```java
String text = "20";
System.out.println(text + 3); // 203
```

Muốn thực hiện phép cộng số học, phải chuyển văn bản bằng API phân tích dữ liệu:

```java
String text = "20";
int number = Integer.parseInt(text);

System.out.println(number + 3); // 23
```

Nếu văn bản không có định dạng số hợp lệ, `Integer.parseInt(...)` có thể ném `NumberFormatException`:

```java
// Integer.parseInt("twenty"); // NumberFormatException
```

Phân biệt rõ hai hướng:

| Hướng | API / thao tác | Ví dụ |
|---|---|---|
| **Giá trị → chuỗi** | Toán tử `+` với `String`, `String.valueOf(...)` | `42` → `"42"` |
| **Chuỗi → số** | `Integer.parseInt`, `Double.parseDouble`, ... | `"42"` → `42` |

Tự thêm `""` bằng `number + ""` có thể chuyển số thành chuỗi, nhưng `String.valueOf(number)` thể hiện rõ ý định hơn khi chỉ cần chuyển đổi. Đừng dùng `Integer.parseInt` chỉ để nối số với chữ.

## 11. `+=` và tính bất biến của `String`

`+=` trên biến `String` tạo giá trị nối rồi gán lại biến; chuỗi nguồn không bị sửa:

```java
String first = "Hi";
String alias = first;
first += "!";
System.out.println(alias); // Hi
```

Biến `final String` không thể dùng `+=` vì không được gán lại. Xem bài **+= là tạo kết quả rồi gán lại tham chiếu** để phân tích vế trái phức tạp và sự khác nhau giữa `s += 1 + 2` với `s = s + 1 + 2`.

## 12. Biểu thức hằng và phép nối lúc chạy

Biểu thức `"Ja" + "va"` là một **constant expression**, được xác định lúc biên dịch và có giá trị hằng đã intern. Ngược lại, khi kết quả phụ thuộc biến không phải constant variable, phép nối diễn ra lúc chạy. Dùng `equals()` để so nội dung; không dựa vào `==` dù một số kết quả hằng có cùng tham chiếu. Chi tiết bytecode thuộc bài **Chi tiết biên dịch phép nối có thể thay đổi theo JDK**.

## 13. Hiệu năng: khi nào dùng `+`, khi nào dùng `StringBuilder`?

Với một biểu thức ngắn như `"Hello, " + name`, `+` dễ đọc và Java hiện đại có thể tối ưu. Khi tích lũy liên tục qua vòng lặp, `StringBuilder.append(...)` thường phù hợp hơn vì tránh tạo lại tiền tố đã tích lũy ở mỗi lượt. Để nối danh sách có dấu phân cách, ưu tiên `String.join()` nếu thích hợp. Bài **Nối trong một biểu thức so với tích lũy qua vòng lặp** hướng dẫn chi tiết cách chọn API và kiểm chứng chi phí.

## 14. Thứ tự đánh giá và tác dụng phụ

Các toán hạng Java được đánh giá theo thứ tự từ trái sang phải, kể cả khi phép nối được tối ưu. Ví dụ:

```java
int n = 1;
String text = "n=" + n++ + ", after=" + n;
System.out.println(text); // n=1, after=2
```

Hạn chế tác dụng phụ trong biểu thức dài. Bài về **Thứ tự kết hợp trái–phải** phân biệt tính kết hợp, độ ưu tiên và thứ tự đánh giá.

## 15. Những lỗi thường gặp

| Ngộ nhận | Cách kiểm tra đúng |
|---|---|
| `"2" + 3` là phép cộng số | Kết quả là `"23"`; dùng `Integer.parseInt` khi muốn cộng số |
| `'A' + 1` tạo `"A1"` | Kết quả `int` là `66` |
| Mảng tự liệt kê phần tử khi nối | Dùng `Arrays.toString(...)` |
| `s + "B";` là statement hợp lệ | Phải sử dụng/gán kết quả; biểu thức `+` riêng lẻ không phải statement expression |
| Nối `null` và gọi method trên `null` giống nhau | `"x=" + ref` có thể in `"null"`; `ref.concat(...)` có thể ném NPE |

Điểm chung: cần xác định **kiểu của phép toán đang xét**, cách chuyển đổi và hợp đồng của API.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `"n=" + 2 + 3` và `"n=" + (2 + 3)` khác nhau thế nào? **Đáp án:** `"n=23"` so với `"n=5"`.

**Câu 2.** `"values=" + numbers` (với `numbers` là `int[]`) có liệt kê các phần tử không? **Đáp án:** Không; dùng `Arrays.toString(numbers)`.

**Câu 3.** `String.valueOf((Object) null)` cho gì? **Đáp án:** `"null"`; không tự áp dụng điều này cho overload `char[]` với đối số null.

**Câu 4.** Vì sao `"Hi" + name` thường đủ tốt cho lời chào ngắn? **Đáp án:** diễn đạt rõ ý định; chỉ cân nhắc builder cho quá trình tích lũy qua nhiều lượt.

## 17. Ghi nhớ

Toán tử `+` trong Java chỉ là **nối chuỗi** khi có toán hạng kiểu `String` ở phép toán đang xét; nếu cả hai là các toán hạng số phù hợp, đó là **cộng số**. Khi nối chuỗi, Java chuyển các giá trị thành văn bản theo quy tắc string conversion: số thành chữ số, `boolean` thành `"true"`/`"false"`, `char` thành ký tự tương ứng, tham chiếu `null` thành `"null"`, và đối tượng thông thường dựa vào biểu diễn văn bản của nó.

Chú ý **kết hợp trái**, **độ ưu tiên toán tử** và dấu ngoặc: `"sum=" + 2 + 3` ra `"sum=23"`, còn `"sum=" + (2 + 3)` ra `"sum=5"`. Sử dụng `String.valueOf` khi cần chuyển đổi tường minh, `Arrays.toString` cho mảng, `String.join` cho dữ liệu có dấu phân cách và `StringBuilder` khi xây dựng chuỗi nhiều bước. Bởi vì `String` bất biến, mỗi phép nối tạo giá trị kết quả để lưu hoặc sử dụng, không chỉnh sửa nội dung đối tượng chuỗi ban đầu.

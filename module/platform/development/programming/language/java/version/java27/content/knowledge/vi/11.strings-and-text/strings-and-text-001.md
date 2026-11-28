# String bất biến, so sánh nội dung và string pool

Trong Java 27, **String** là kiểu tham chiếu đại diện cho một chuỗi ký tự. Nó xuất hiện ở gần như mọi ứng dụng: tên người dùng, thông điệp, mã định danh, dữ liệu từ tệp, nội dung HTTP và giá trị hiển thị. Để sử dụng String đúng, cần phân biệt ba vấn đề:

1. **String bất biến (immutable):** sau khi đối tượng String được tạo, nội dung của đối tượng đó không thay đổi.
2. **So sánh nội dung:** dùng **equals()** để xác định hai chuỗi có cùng nội dung; toán tử **==** trên tham chiếu lại kiểm tra xem chúng có cùng một đối tượng không.
3. **String pool:** Java duy trì cơ chế dùng chung các đối tượng String đã được intern, trong đó có các string literal và biểu thức hằng chuỗi.

Ba đặc tính này liên hệ với nhau nhưng **không đồng nghĩa**. String bất biến không có nghĩa mọi biến giữ chuỗi đều là final. Hai String bằng nội dung không nhất thiết là cùng một đối tượng. Và string pool không làm cho mọi String có cùng nội dung tự động dùng chung một tham chiếu.

Bài học sử dụng cú pháp và API vẫn còn phù hợp với Java 27, không dựa vào các chi tiết triển khai JVM cũ hoặc API đã lỗi thời.

## 1. String là gì?

**java.lang.String** là một lớp **final** dùng để biểu diễn văn bản dưới dạng chuỗi các đơn vị mã UTF-16 (UTF-16 code units). Vì lớp này final, không thể tạo lớp con của String bằng **extends String**.

String không phải kiểu nguyên thủy như **int** hoặc **boolean**. Một biến String lưu **tham chiếu tới đối tượng**, hoặc có thể chứa **null** nếu chưa tham chiếu tới đối tượng nào.

~~~java
String greeting = "Xin chào";
String empty = "";
String nothing = null;
~~~

Ở đây:

- **greeting** tham chiếu tới một String có nội dung **"Xin chào"**.
- **empty** tham chiếu tới chuỗi rỗng, tức một chuỗi hợp lệ với độ dài bằng 0.
- **nothing** có giá trị **null**, tức không tham chiếu tới String nào.

**Chuỗi rỗng không phải null.** Ví dụ:

~~~java
String empty = "";

System.out.println(empty.isEmpty()); // true
System.out.println(empty.length());  // 0
System.out.println(empty == null);   // false
~~~

Việc gọi method trên một tham chiếu null như **nothing.length()** sẽ gây **NullPointerException**. Vì vậy, quy tắc xử lý null phải được xác định rõ ở ranh giới API.

### Những cách tạo String thường gặp

~~~java
String literal = "Java";
String combined = "Ja" + "va";
String fromNumber = String.valueOf(27);
String repeated = "Hi".repeat(3);
~~~

**String.valueOf(27)** tạo biểu diễn văn bản của một giá trị **int**. Phương thức **repeat(3)** cho ra nội dung **"HiHiHi"**, nhưng không sửa String gốc.

Có thể tạo String bằng constructor, chẳng hạn:

~~~java
String explicit = new String("Java");
~~~

Tuy nhiên, cách này thường **không cần thiết** khi chỉ muốn có chuỗi **"Java"**. Literal đơn giản, dễ đọc và tận dụng cơ chế interning. Constructor **new String(...)** chỉ đáng cân nhắc khi có yêu cầu riêng về đối tượng hoặc API; không nên dùng nó như cách mặc định để viết chuỗi.

## 2. Bất biến nghĩa là gì?

Một đối tượng **String** không cho phép thay đổi trực tiếp nội dung của nó sau khi được tạo. Các method có vẻ như “sửa” chuỗi thực chất trả về một kết quả String khác về mặt giá trị khi cần thay đổi.

~~~java
String name = "java";

name.toUpperCase();

System.out.println(name); // java
~~~

Lời gọi **toUpperCase()** không thay đổi nội dung của đối tượng mà **name** đang tham chiếu. Vì không lưu kết quả trả về, giá trị mà chương trình dùng sau đó vẫn là **"java"**.

Muốn sử dụng kết quả biến đổi, hãy gán lại tham chiếu hoặc lưu vào biến khác:

~~~java
String name = "java";
String upperName = name.toUpperCase(java.util.Locale.ROOT);

System.out.println(name);      // java
System.out.println(upperName); // JAVA
~~~

Biến **name** vẫn trỏ tới chuỗi có nội dung **"java"**. Biến **upperName** trỏ tới một kết quả String chứa **"JAVA"**.

### Thay đổi biến tham chiếu không phải thay đổi đối tượng

~~~java
String title = "Draft";

title = "Published";

System.out.println(title); // Published
~~~

Phép gán **title = "Published"** làm biến **title** tham chiếu tới chuỗi khác. Nó **không** biến đổi nội dung của đối tượng String chứa **"Draft"**.

Có thể hình dung:

~~~text
Trước phép gán:  title ──> "Draft"
Sau phép gán:    title ──> "Published"
~~~

Đối tượng String cũ có thể vẫn được tham chiếu từ nơi khác. Việc nó còn tồn tại trong bộ nhớ bao lâu phụ thuộc vào khả năng tiếp cận đối tượng và quản lý bộ nhớ của JVM, không phải vào phép gán biến.

### String immutable khác final String

**final** là ràng buộc đối với việc gán lại biến hoặc field; **immutable** là đặc tính không đổi của nội dung đối tượng.

~~~java
String first = "A";
first = "B"; // Hợp lệ: biến không final.

final String second = "A";
// second = "B"; // Lỗi biên dịch: không được gán lại biến final.
~~~

Cả hai đối tượng String có nội dung **"A"** và **"B"** đều bất biến. Khác biệt là biến **first** được gán lại, còn biến **second** thì không.

Một **final String** không làm cho string pool hoạt động khác theo ý nghĩa “mọi biến final đều được intern”. Khả năng gộp thành biểu thức hằng lúc biên dịch còn phụ thuộc vào quy tắc **constant variable** của Java, được trình bày ở phần sau.

### Không phải mọi thao tác đều tạo một đối tượng mới

Một phương thức String có thể trả lại chính đối tượng nhận lời gọi nếu kết quả không cần thay đổi, hoặc trả về đối tượng khác. Ví dụ, một thao tác **replace()** không tìm được ký tự cần thay có thể trả lại chuỗi ban đầu.

Do đó, **không nên dựa vào toán tử == để suy đoán một thao tác xử lý chuỗi đã chạy hay chưa**, cũng không nên khẳng định mọi lời gọi String method luôn cấp phát một đối tượng mới. Điều quan trọng là **giá trị nội dung** và hợp đồng của method.

## 3. Vì sao String được thiết kế bất biến?

Bất biến là một lựa chọn thiết kế quan trọng, đặc biệt khi String được dùng làm tên lớp, đường dẫn, khóa dữ liệu, tham số hệ thống hoặc nội dung dùng chung.

Các lợi ích chính:

- **Dễ chia sẻ:** nhiều biến có thể tham chiếu cùng một String mà không sợ một bên sửa nội dung làm thay đổi giá trị bên kia.
- **Phù hợp làm khóa trong Map và phần tử trong Set:** nội dung dùng để tính **equals()** và **hashCode()** không thay đổi trong suốt vòng đời đối tượng.
- **Hỗ trợ string pool:** việc dùng chung một đối tượng String đã intern là an toàn về mặt nội dung vì không ai có thể sửa đối tượng đó.
- **Đơn giản hóa suy luận:** sau khi có một String, mã khác không thể thay đổi nội dung String thông qua tham chiếu đang chia sẻ.
- **Thuận lợi khi dùng đồng thời:** bản thân giá trị String bất biến, dù thao tác trên biến, collection hoặc đối tượng chứa String vẫn có thể cần đồng bộ tùy thiết kế.

Bất biến **không** có nghĩa mọi thao tác sử dụng String đều tự động thread-safe. Ví dụ, nhiều thread cùng cập nhật một biến tham chiếu String hoặc cùng sửa một **HashMap<String, ...>** vẫn cần được thiết kế đồng bộ phù hợp.

## 4. == và equals(): so sánh hai điều khác nhau

Đây là nhầm lẫn phổ biến nhất khi làm việc với String.

| Cách so sánh | Ý nghĩa khi dùng với String | Khi nào sử dụng |
|---|---|---|
| **a == b** | Hai tham chiếu có trỏ tới **cùng một đối tượng** không? | Kiểm tra danh tính đối tượng hoặc so sánh với null |
| **a.equals(b)** | Hai String có **cùng chuỗi đơn vị mã UTF-16** không? | Kiểm tra nội dung có giống hệt nhau |
| **a.equalsIgnoreCase(b)** | Nội dung có tương đương theo quy tắc so sánh bỏ qua phân biệt hoa/thường của Java không? | Trường hợp thực sự muốn so sánh không phân biệt hoa/thường theo hợp đồng method |
| **a.compareTo(b)** | So sánh thứ tự từ điển theo các đơn vị mã UTF-16 của Java | Sắp xếp theo thứ tự tự nhiên của String, **không** phải quy tắc ngôn ngữ địa phương |

Ví dụ:

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Hai biểu thức **new** tạo hai đối tượng riêng biệt. Do đó, **a == b** là false. Nhưng cả hai chứa cùng nội dung, nên **a.equals(b)** là true.

### String.equals() là phép so sánh theo giá trị chính xác

~~~java
String expected = "Java";

System.out.println(expected.equals("Java")); // true
System.out.println(expected.equals("java")); // false
System.out.println(expected.equals("Java ")); // false
System.out.println(expected.equals("JAVA")); // false
~~~

**equals()** phân biệt chữ hoa/chữ thường, khoảng trắng và từng đơn vị mã trong chuỗi. Nó không tự cắt khoảng trắng, chuyển chữ hoa/chữ thường hoặc chuẩn hóa Unicode trước khi so sánh.

### Không dùng == để so sánh nội dung nhập từ bên ngoài

~~~java
String userInput = new String("admin");

if (userInput.equals("admin")) {
    System.out.println("Same content");
}
~~~

Nếu viết **userInput == "admin"**, chương trình có thể trả false dù nội dung là **"admin"**. Nguồn của chuỗi (literal, dữ liệu đọc từ tệp, HTTP, database, kết quả nối chuỗi hoặc biến đổi văn bản) ảnh hưởng tới danh tính đối tượng; nội dung mới là thứ phần lớn logic nghiệp vụ cần so sánh.

**Quy tắc thực hành:** khi muốn kiểm tra hai String có cùng nội dung hay không, hãy dùng **equals()**, không dùng **==**.

## 5. So sánh an toàn khi có null

Lời gọi **a.equals(b)** yêu cầu **a** không phải null. Nếu **a** là null, Java ném **NullPointerException**.

~~~java
String input = null;

// System.out.println(input.equals("ready")); // NullPointerException.
~~~

Có ba cách thường gặp tùy hợp đồng:

### Đặt hằng chuỗi ở bên trái

~~~java
String input = null;

boolean ready = "ready".equals(input);

System.out.println(ready); // false
~~~

Literal **"ready"** không phải null, nên cách gọi này an toàn với **input** null.

### Dùng Objects.equals()

~~~java
import java.util.Objects;

String first = null;
String second = null;

System.out.println(Objects.equals(first, second)); // true
System.out.println(Objects.equals(first, "Java")); // false
~~~

**Objects.equals(a, b)** kiểm tra an toàn khi một hoặc cả hai tham chiếu là null. Khi cả hai cùng null, kết quả là true; khi một bên null và bên còn lại không null, kết quả là false; khi cả hai không null, phương thức dùng phép so sánh nội dung qua **equals()**.

### Từ chối null ngay tại ranh giới API

Nếu đầu vào bắt buộc phải có String, nên kiểm tra rõ:

~~~java
import java.util.Objects;

static void process(String name) {
    Objects.requireNonNull(name, "name");
    System.out.println(name);
}
~~~

Khi null là giá trị không hợp lệ, việc từ chối sớm giúp phát hiện lỗi gần nơi phát sinh. Nếu null là một trạng thái hợp lệ của bài toán, hãy mô tả rõ điều đó trong hợp đồng và xử lý nhất quán.

## 6. equals(), hashCode() và khóa trong Map

**String** ghi đè **equals()** và **hashCode()** theo nội dung. Nếu hai String **equals()** bằng nhau, chúng phải có cùng **hashCode()**. Tuy nhiên, **hashCode()** không phải định danh duy nhất: hai String khác nhau vẫn có thể trùng hash code.

~~~java
String a = new String("order-001");
String b = "order-001";

System.out.println(a.equals(b));                  // true
System.out.println(a.hashCode() == b.hashCode()); // true
~~~

Điều này cho phép sử dụng String làm khóa trong những cấu trúc dữ liệu như **HashMap** hoặc phần tử trong **HashSet**:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> stock = new HashMap<>();

stock.put(new String("SKU-01"), 12);

System.out.println(stock.get("SKU-01")); // 12
~~~

Mặc dù khóa được tạo bằng **new String(...)** và việc tra cứu dùng literal, **HashMap** vẫn tìm đúng mục vì so sánh khóa theo hợp đồng hash/equality, không yêu cầu cùng tham chiếu.

**Không** nên tự xây logic tra cứu String bằng cách chỉ so sánh hash code, vì có thể xảy ra va chạm hash.

## 7. String pool là gì?

**String pool** là cơ chế quản lý các String đã được **intern** để những chuỗi bằng nội dung dùng chung một tham chiếu chuẩn (canonical reference) khi thích hợp.

Java bảo đảm string literal có cùng nội dung được intern. Các chuỗi là biểu thức hằng tại thời điểm biên dịch cũng được intern theo quy tắc ngôn ngữ.

~~~java
String first = "Java";
String second = "Java";

System.out.println(first == second); // true
~~~

Cả hai biến tham chiếu tới cùng một String đã được intern cho literal **"Java"**. Vì vậy, **==** trả true trong ví dụ này.

Tuy nhiên, **đây không phải lý do để thay equals() bằng ==**. Một String có cùng nội dung được tạo từ nguồn khác có thể là đối tượng khác và không cùng tham chiếu.

### String literal và new String khác nhau

~~~java
String literal = "Java";
String created = new String("Java");

System.out.println(literal == created);      // false
System.out.println(literal.equals(created)); // true
~~~

Biểu thức **new String("Java")** tạo một đối tượng String riêng. Literal **"Java"** được intern, còn đối tượng được tạo tường minh bằng **new** không tự trở thành chính đối tượng của literal.

Không nên diễn giải ví dụ này thành một con số cố định về **bao nhiêu đối tượng đã được cấp phát trong toàn JVM**. Literal có thể đã tồn tại trong pool từ trước, JVM có thể tối ưu hóa và quản lý bộ nhớ theo triển khai. Hợp đồng cần ghi nhớ ở đây là danh tính của đối tượng tạo bằng **new** và đối tượng literal khác nhau, trong khi **equals()** vẫn đúng.

### Các literal giống nhau ở nhiều vị trí

~~~java
class First {
    static final String LABEL = "ready";
}

class Second {
    static final String LABEL = "ready";
}

System.out.println(First.LABEL == Second.LABEL); // true
~~~

Trong ví dụ, cả hai biểu thức hằng dùng cùng nội dung đã được intern. Dù chương trình tổ chức literal ở nhiều lớp, quy tắc interning giúp các hằng chuỗi có cùng nội dung chia sẻ tham chiếu chuẩn.

Không cần gọi **intern()** thủ công đối với literal thông thường.

## 8. Biểu thức hằng được gộp khi biên dịch

Java có khái niệm **constant expression**. Khi một phép nối chuỗi chỉ gồm các thành phần là hằng phù hợp, kết quả có thể được xác định ngay lúc biên dịch và được intern.

~~~java
String left = "Java";
String right = "Ja" + "va";

System.out.println(left == right); // true
~~~

Biểu thức **"Ja" + "va"** là biểu thức hằng; Java xử lý nó như một chuỗi hằng có nội dung **"Java"**.

### final với giá trị hằng

~~~java
final String part = "Ja";

String combined = part + "va";

System.out.println(combined == "Java"); // true
~~~

Ở đây, **part** là một **constant variable**: biến final kiểu String, được khởi tạo bằng biểu thức hằng. Vì vậy, phép nối có thể là biểu thức hằng.

Điều này **không** có nghĩa mọi biến final đều tạo ra biểu thức hằng:

~~~java
final String part = new String("Ja");
String combined = part + "va";

System.out.println(combined.equals("Java")); // true
~~~

Giá trị của **part** được tạo bằng **new**, không phải biểu thức hằng theo định nghĩa Java. Do đó, không nên suy diễn việc nối chuỗi này sẽ được intern chỉ vì biến được khai báo final.

### Phép nối chuỗi tại thời điểm chạy

~~~java
String prefix = "Ja";
String result = prefix + "va";

System.out.println(result.equals("Java")); // true
System.out.println(result == "Java");      // false
~~~

Biến **prefix** không phải constant variable, nên biểu thức nối này không phải constant expression. Kết quả nối tại thời điểm chạy có thể bằng literal về **nội dung**, nhưng không phải cùng đối tượng literal đã intern.

Ngay cả khi JVM sử dụng những kỹ thuật tối ưu hóa khác nhau cho phép nối chuỗi, chương trình không được dựa vào danh tính của một String kết quả để suy ra nội dung hay độ tối ưu của thao tác.

### Bảng ghi nhớ

| Tình huống | **equals("Java")** | **== "Java"** |
|---|---|---|
| **"Java"** | true | true |
| **"Ja" + "va"** (hằng) | true | true |
| **new String("Java")** | true | false |
| **prefix + "va"**, với **prefix** là biến thường chứa **"Ja"** | true | false |
| **part + "va"**, với **final String part = "Ja"** | true | true |

Bảng này minh họa các quy tắc trong mã được nêu cụ thể; đừng mở rộng nó thành quy tắc “cứ nối chuỗi là tạo mới” hoặc “cứ final là được intern”.

## 9. String.intern(): lấy chuỗi chuẩn trong pool

Phương thức **intern()** trả về tham chiếu chuẩn tới String có cùng nội dung trong pool. Nếu pool đã có một String tương đương, kết quả là đối tượng đó; nếu chưa, cơ chế interning sẽ thiết lập một tham chiếu chuẩn cho nội dung tương ứng.

~~~java
String literal = "Java";
String generated = new String("Java");

System.out.println(generated == literal);          // false
System.out.println(generated.intern() == literal); // true
~~~

Lời gọi **generated.intern()** không biến đổi nội dung của **generated**. Nó trả về tham chiếu canonical cho nội dung **"Java"**.

### Có nên intern mọi String?

Không. **intern()** là cơ chế chuyên biệt, không phải cách mặc định để bảo đảm so sánh chuỗi đúng.

Nên ưu tiên:

~~~java
if (actual.equals(expected)) {
    // Nội dung bằng nhau.
}
~~~

Thay vì:

~~~java
if (actual.intern() == expected.intern()) {
    // Có thể cho ra cùng kết quả nội dung, nhưng không cần thiết.
}
~~~

Việc intern số lượng lớn chuỗi động, đặc biệt chuỗi từ dữ liệu không kiểm soát, có thể tạo thêm chi phí quản lý pool và bộ nhớ. Chỉ cân nhắc khi có một mô hình dữ liệu lặp lại rõ ràng, đã đo đạc hiệu năng và hiểu chi phí của thiết kế.

**String pool khác với những kỹ thuật tối ưu hóa bộ nhớ bên trong JVM**, chẳng hạn cơ chế giảm trùng lặp dữ liệu lưu trữ String ở một số cấu hình. Cách JVM tổ chức mảng byte, bố trí bộ nhớ hay thực hiện tối ưu hóa không phải hợp đồng API dùng để so sánh chuỗi.

## 10. Chuỗi trong text block và những cách tạo nội dung mới

**Text block** cho phép viết văn bản nhiều dòng dễ đọc bằng ba dấu nháy kép. Đây là một dạng string literal trong Java hiện đại:

~~~java
String message = """
        Hello,
        Java!
        """;

System.out.println(message);
~~~

Kết quả:

~~~text
Hello,
Java!
~~~

Text block giúp biểu diễn JSON, SQL hoặc nội dung nhiều dòng mà không phải liên tục nối các literal. Nó **vẫn là String bất biến**.

Lưu ý về ký tự xuống dòng, khoảng trắng đầu dòng và quy tắc loại bỏ thụt lề ngẫu nhiên của text block khi cần so sánh nội dung chính xác. Ví dụ, một ký tự xuống dòng ở cuối có thể làm **equals()** trả false so với chuỗi trông tương tự nhưng không có xuống dòng.

### Biến đổi bằng method

~~~java
String input = "  Java  ";
String cleaned = input.strip();
String lower = cleaned.toLowerCase(java.util.Locale.ROOT);

System.out.println(input.equals("  Java  ")); // true
System.out.println(cleaned);                  // Java
System.out.println(lower);                    // java
~~~

**strip()** loại bỏ các ký tự khoảng trắng ở hai đầu theo quy tắc Unicode-aware của **Character.isWhitespace()**, khác với **trim()** vốn dùng tiêu chí ký tự có giá trị mã không vượt quá U+0020. Khi xử lý văn bản Unicode hiện đại, **strip()** thường diễn đạt đúng ý định hơn, nhưng không phải mọi ký tự người đọc cảm nhận là khoảng trắng đều được loại bỏ.

Các method phổ biến như **replace()**, **substring()**, **toLowerCase()**, **toUpperCase()** và **repeat()** không sửa nội dung String gốc. Chúng trả về kết quả theo hợp đồng tương ứng.

### Nối chuỗi trong vòng lặp

~~~java
StringBuilder builder = new StringBuilder();

for (int number = 1; number <= 3; number++) {
    if (number > 1) {
        builder.append(", ");
    }
    builder.append(number);
}

String result = builder.toString();

System.out.println(result); // 1, 2, 3
~~~

**StringBuilder** là đối tượng **có thể thay đổi trạng thái**, phù hợp khi muốn xây dựng một chuỗi qua nhiều bước trong cùng luồng xử lý. Khi cần giá trị String, dùng **toString()** để thu được String bất biến.

Không phải mọi phép nối bằng toán tử **+** đều kém hiệu quả. Với vài phần cố định, phép nối thường ngắn gọn và JVM có thể tối ưu hiệu quả. Ưu tiên **StringBuilder** khi lặp ghép nhiều phần hoặc cần kiểm soát quá trình xây dựng chuỗi.

### String.join() cho cấu trúc đơn giản

~~~java
String csv = String.join(",", "red", "green", "blue");

System.out.println(csv); // red,green,blue
~~~

Với trường hợp chỉ nối các phần tử bằng dấu phân cách, **String.join()** diễn đạt trực tiếp hơn việc tự viết vòng lặp.

## 11. UTF-16: length() không luôn là số ký tự người dùng nhìn thấy

String trong Java được biểu diễn ở cấp API bằng chuỗi **UTF-16 code units**. Mỗi giá trị **char** là một đơn vị mã 16-bit, **không nhất thiết** tương ứng với một ký tự Unicode hoàn chỉnh mà người dùng nhìn thấy.

### ASCII và ký tự phổ biến

~~~java
String word = "Java";

System.out.println(word.length()); // 4
System.out.println(word.charAt(0)); // J
~~~

Với chữ cái ASCII, một ký tự tương ứng một đơn vị mã UTF-16 nên **length()** và số ký tự nhìn thấy thường trùng nhau.

### Code point ngoài Basic Multilingual Plane

Một số ký tự Unicode được biểu diễn bằng **surrogate pair** gồm hai đơn vị mã UTF-16.

~~~java
String rocket = "🚀";

System.out.println(rocket.length()); // 2
System.out.println(rocket.codePointCount(0, rocket.length())); // 1
~~~

Dù mắt người nhìn thấy một biểu tượng tên lửa, **length()** bằng 2 vì nó chiếm hai đơn vị mã UTF-16. **codePointCount()** cho biết một code point trong chuỗi này.

Có thể duyệt theo code point:

~~~java
"🚀A".codePoints().forEach(codePoint -> {
    System.out.println("U+" + Integer.toHexString(codePoint));
});
~~~

**codePoints()** trả về một **IntStream** của các giá trị code point được giải mã từ chuỗi UTF-16; cách này phù hợp hơn việc giả định mỗi **char** là một ký tự Unicode hoàn chỉnh.

### Code point vẫn có thể khác ký tự hiển thị

Một ký tự người dùng cảm nhận có thể được tạo từ nhiều code point, chẳng hạn chữ **e** cùng dấu sắc kết hợp. Vì vậy:

- **length()** đo số đơn vị mã UTF-16.
- **codePointCount()** đo số code point theo chuỗi UTF-16.
- Số ký tự người dùng cảm nhận (*grapheme clusters*) có thể khác cả hai.

Khi cắt chuỗi cho giao diện, đếm ký tự nhập hoặc giới hạn nội dung hiển thị, cần xác định chính xác đơn vị cần đếm; không mặc định **substring()** theo chỉ số **char** luôn cắt đúng biên ký tự người dùng nhìn thấy.

## 12. Hai chuỗi nhìn giống nhau có thể không equals()

Unicode có thể biểu diễn cùng một ký tự hiển thị bằng các dãy code point khác nhau. **String.equals()** chỉ kiểm tra chính xác nội dung các đơn vị mã UTF-16, không tự chuẩn hóa hai chuỗi theo quy tắc Unicode.

Ví dụ về chữ **é**:

~~~java
String composed = "\u00E9";   // é: một code point.
String decomposed = "e\u0301"; // e + dấu sắc kết hợp.

System.out.println(composed.equals(decomposed)); // false
~~~

Hai chuỗi có thể hiển thị giống nhau, nhưng cách mã hóa nội dung khác nhau nên **equals()** trả false.

Nếu miền nghiệp vụ yêu cầu xem các biểu diễn Unicode tương đương về mặt chuẩn hóa là cùng giá trị, có thể chuẩn hóa trước khi so sánh:

~~~java
import java.text.Normalizer;

String left = Normalizer.normalize(composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(left.equals(right)); // true
~~~

**NFC** là một dạng Unicode normalization phổ biến. Quy tắc chuẩn hóa nào phù hợp còn tùy hệ thống: tên hiển thị, mã định danh, khóa tìm kiếm và dữ liệu ký điện tử có thể có yêu cầu khác nhau.

**Không tự ý chuẩn hóa mọi dữ liệu.** Nếu dữ liệu có ý nghĩa ở mức byte hoặc yêu cầu so khớp chính xác chuỗi gốc, thao tác biến đổi trước khi so sánh có thể phá vỡ ý nghĩa của dữ liệu. Hãy xác định hợp đồng từ đầu và dùng nhất quán tại nơi tạo, lưu và tra cứu.

## 13. So sánh không phân biệt hoa/thường và theo ngôn ngữ

Phương thức **equalsIgnoreCase()** có thể phù hợp cho một số quy tắc so sánh văn bản không phân biệt chữ hoa/chữ thường:

~~~java
String first = "JAVA";
String second = "java";

System.out.println(first.equalsIgnoreCase(second)); // true
~~~

Nhưng đây **không phải phép so sánh theo ngôn ngữ hoặc vùng miền (locale-aware)**, và không nên giả định nó đáp ứng mọi quy tắc chuyển đổi chữ hoa/chữ thường trên toàn Unicode.

Ví dụ, chữ thường/chữ hoa của một số ngôn ngữ có quy tắc đặc biệt. Với văn bản hiển thị cho người dùng, việc so sánh hoặc sắp xếp thường cần ngữ cảnh **Locale**.

### Chuyển chữ hoa/thường có Locale rõ ràng

~~~java
import java.util.Locale;

String input = "Java";

System.out.println(input.toLowerCase(Locale.ROOT)); // java
System.out.println(input.toUpperCase(Locale.ROOT)); // JAVA
~~~

**Locale.ROOT** phù hợp khi muốn phép biến đổi nhất quán, không phụ thuộc locale mặc định của máy, trong các quy tắc xử lý văn bản trung tính với ngôn ngữ. Nó không tự thay thế việc thiết kế phép so sánh Unicode hoàn chỉnh cho mọi ngôn ngữ hoặc mã định danh.

Nếu ngữ nghĩa là văn bản của một ngôn ngữ cụ thể, hãy truyền **Locale** thích hợp thay vì mặc định rằng mọi hệ thống đều dùng cùng một quy tắc.

### compareTo() không phải sắp xếp ngôn ngữ

~~~java
System.out.println("apple".compareTo("banana") < 0); // true
~~~

**compareTo()** của String áp dụng thứ tự từ điển dựa trên giá trị các đơn vị mã UTF-16, phân biệt hoa/thường. Nó phù hợp khi cần một thứ tự tự nhiên xác định theo String, nhưng không phải thuật toán sắp xếp ngôn ngữ cho người dùng.

Khi cần sắp xếp văn bản theo locale, có thể dùng **Collator**:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));

int comparison = collator.compare("An", "Bình");
System.out.println(comparison);
~~~

**Collator** hỗ trợ so sánh có xét đến quy tắc collation của locale. Cách cấu hình mức độ phân biệt dấu và chữ hoa/thường cần dựa trên mục tiêu của ứng dụng; không nên dùng kết quả collation để thay thế trực tiếp định danh chính xác trong mọi hệ thống.

## 14. So sánh nội dung trong switch và collection

### switch trên String

Trong Java, **switch** có thể dùng String làm selector. Các nhánh **case** so khớp theo **giá trị String**, không bắt buộc cùng danh tính đối tượng.

~~~java
String command = new String("start");

switch (command) {
    case "start" -> System.out.println("Started");
    case "stop" -> System.out.println("Stopped");
    default -> System.out.println("Unknown");
}
~~~

Kết quả:

~~~text
Started
~~~

Dù **command** được tạo bằng **new String(...)**, nội dung của nó khớp với case **"start"**. Không nên hiểu switch String như phép so sánh tham chiếu bằng **==**.

Lưu ý về null: một switch thông thường không có nhánh xử lý null phù hợp có thể ném **NullPointerException** nếu selector null. Nếu đầu vào có thể null, cần thiết kế xử lý rõ ràng thay vì ngầm mặc định rằng null tương đương chuỗi rỗng.

### contains(), startsWith(), endsWith() là kiểm tra nội dung

~~~java
String path = "reports/summary.csv";

System.out.println(path.startsWith("reports/")); // true
System.out.println(path.endsWith(".csv"));       // true
System.out.println(path.contains("summary"));    // true
~~~

Những method này kiểm tra nội dung theo hợp đồng từng method; chúng không kiểm tra danh tính đối tượng.

Nếu bài toán là so khớp cấu trúc đường dẫn, định dạng hoặc quy tắc bảo mật, nên dùng API chuyên dụng cho miền đó thay vì tự suy diễn quá nhiều chỉ từ phép kiểm tra chuỗi.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai String cùng nội dung nhưng **==** trả false | Hai tham chiếu trỏ tới đối tượng khác nhau | Dùng **equals()** để so sánh nội dung |
| Đổi hoa/thường nhưng chuỗi gốc không đổi | String bất biến; method trả về kết quả | Lưu kết quả của **toUpperCase()**, **replace()**, **strip()**... |
| **NullPointerException** khi gọi **equals()** | Biến nhận lời gọi có giá trị null | Dùng **Objects.equals()**, literal bên trái hoặc từ chối null sớm |
| Hai literal **==** trả true nên tưởng mọi String bằng nhau đều cùng đối tượng | Literal được intern | Không dùng kết quả của pool làm quy tắc so sánh nghiệp vụ |
| **final String** không được gán lại | **final** ràng buộc biến chứ không chỉ nội dung | Phân biệt biến final với đối tượng String bất biến |
| Nối String trong vòng lặp gây nhiều kết quả tạm | Dùng **+** lặp lại để tích lũy nhiều phần | Cân nhắc **StringBuilder** khi xây chuỗi từng bước |
| Một emoji có **length()** bằng 2 | UTF-16 dùng surrogate pair | Dùng API code point hoặc xử lý grapheme theo nhu cầu |
| Hai đoạn văn nhìn như nhau nhưng **equals()** false | Khác dạng chuẩn hóa Unicode hoặc ký tự khoảng trắng | Xác định quy tắc chuẩn hóa/so sánh của miền nghiệp vụ |
| **equalsIgnoreCase()** không cho kết quả mong đợi theo tiếng người dùng | Không phải collation locale-aware | Dùng quy tắc case mapping/collation theo **Locale** phù hợp |
| Dùng **hashCode()** như định danh duy nhất | Hash có thể va chạm | Dùng **equals()** và cấu trúc dữ liệu tuân hợp đồng equality |
| Gọi **intern()** trên mọi chuỗi đầu vào | Nhầm interning với so sánh nội dung | Ưu tiên **equals()**, chỉ intern khi có lý do và đã đo đạc |

## 16. Ví dụ tổng hợp có thể chạy trực tiếp

Ví dụ sau kết hợp bất biến, so sánh nội dung, string pool, hằng lúc biên dịch, **intern()**, xử lý khoảng trắng, Unicode và **HashSet**. Lưu vào tệp **StringSemanticsDemo.java**:

~~~java
import java.text.Normalizer;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public class StringSemanticsDemo {
    public static void main(String[] args) {
        // 1. String literal và biểu thức hằng chia sẻ tham chiếu interned.
        String literal = "Java";
        String folded = "Ja" + "va";

        System.out.println(literal == folded); // true

        // 2. Đối tượng tạo bằng new khác tham chiếu, nhưng cùng nội dung.
        String explicit = new String("Java");

        System.out.println(literal == explicit);      // false
        System.out.println(literal.equals(explicit)); // true

        // 3. Phép nối runtime không phải biểu thức hằng.
        String prefix = "Ja";
        String dynamic = prefix + "va";

        System.out.println(literal == dynamic);          // false
        System.out.println(literal.equals(dynamic));     // true
        System.out.println(literal == dynamic.intern()); // true

        // 4. Mỗi phép biến đổi trả về kết quả; không sửa chuỗi gốc.
        String original = "  java  ";
        String normalized = original.strip().toUpperCase(Locale.ROOT);

        System.out.println(original.equals("  java  ")); // true
        System.out.println(normalized);                  // JAVA

        // 5. Một emoji có thể chiếm hai đơn vị mã UTF-16.
        String rocket = "🚀";

        System.out.println(rocket.length()); // 2
        System.out.println(
                rocket.codePointCount(0, rocket.length())); // 1

        // 6. Hai dạng Unicode nhìn giống nhau không tự equals().
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.equals(decomposed)); // false
        System.out.println(composed.equals(
                Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC))); // true

        // 7. Set dùng equality theo nội dung, không theo tham chiếu.
        Set<String> identifiers = new HashSet<>();
        identifiers.add(new String("ticket-01"));

        System.out.println(identifiers.contains("ticket-01")); // true
    }
}
~~~

Kết quả:

~~~text
true
false
true
false
true
true
true
JAVA
2
1
false
true
true
~~~

Những kết luận có thể rút ra từ ví dụ:

1. Literal và biểu thức hằng chuỗi có thể trỏ cùng đối tượng interned.
2. **new String(...)** tạo đối tượng khác dù nội dung vẫn bằng literal.
3. **equals()** so sánh nội dung; **==** so sánh danh tính.
4. **intern()** trả về tham chiếu chuẩn cho nội dung.
5. **strip()** và **toUpperCase()** không biến đổi String gốc.
6. **length()** đo đơn vị mã UTF-16, không mặc định là số ký tự nhìn thấy.
7. Chuẩn hóa Unicode phải được thực hiện tường minh khi hợp đồng yêu cầu.
8. **HashSet<String>** dùng quy tắc equality của String khi tra cứu phần tử.

## 17. Checklist khi dùng String trong Java 27

Trước khi hoàn tất một đoạn mã xử lý chuỗi, hãy kiểm tra:

- Khi so sánh **nội dung**, đã dùng **equals()** hoặc một chiến lược so sánh có hợp đồng rõ ràng chưa?
- Đã tách bạch **null**, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng chưa?
- Nếu gọi **replace()**, **strip()** hoặc phương thức biến đổi khác, đã dùng kết quả trả về chưa?
- Có đang dùng **==** chỉ vì kết quả thử nghiệm với hai literal đều là true không?
- Có đang hiểu sai **final String** thành cơ chế sửa đổi đối tượng hoặc interning không?
- Có đang tự gọi **intern()** khi chỉ cần so sánh bằng **equals()** không?
- Nếu thao tác với Unicode, chỉ số **char** và độ dài **length()** có đúng đơn vị yêu cầu không?
- Nếu muốn coi các dạng biểu diễn Unicode hoặc chữ hoa/thường là tương đương, đã xác định rõ normalization và locale chưa?
- Nếu xây dựng chuỗi qua nhiều lần nối trong vòng lặp, **StringBuilder** hoặc **String.join()** có phù hợp hơn không?
- Nếu dùng String làm khóa dữ liệu, đã dựa vào hợp đồng **equals()**/**hashCode()**, thay vì tham chiếu hoặc hash đơn lẻ, chưa?

## Kết luận

**String bất biến**, vì vậy thao tác biến đổi không sửa nội dung đối tượng đã tồn tại. **equals()** kiểm tra nội dung, còn **==** kiểm tra xem hai tham chiếu có cùng đối tượng hay không. **String pool** là cơ chế interning cho các chuỗi hằng và những chuỗi được intern tường minh; cơ chế này giúp chia sẻ tham chiếu trong những trường hợp xác định nhưng không thay thế phép so sánh nội dung.

Trong Java 27, hãy chọn phép so sánh dựa trên **ngữ nghĩa của bài toán**, không dựa trên tình cờ hai biến cùng tham chiếu. Khi xử lý văn bản thực tế, cần quan tâm thêm tới null, các đơn vị mã UTF-16, Unicode normalization và locale để có kết quả chính xác, dễ đọc và dễ bảo trì.

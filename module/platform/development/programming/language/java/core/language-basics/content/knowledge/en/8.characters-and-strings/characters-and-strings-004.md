# Nối chuỗi bằng `+` và chuyển giá trị thành văn bản trong Java 17+

## 1. Mục tiêu và quy tắc cơ bản

Trong Java, toán tử `+` có **hai vai trò khác nhau**:

- **Cộng số** khi các toán hạng là kiểu số và không có ngữ cảnh nối chuỗi.
- **Nối chuỗi** (*string concatenation*) khi **ít nhất một toán hạng của phép `+` đang xét là `String`**. Toán hạng còn lại được chuyển thành dạng văn bản rồi ghép vào chuỗi.

~~~java
int quantity = 3;
int price = 40;

System.out.println(quantity + price);       // 43
System.out.println("quantity=" + quantity);  // quantity=3
System.out.println("total=" + quantity * price); // total=120
~~~

Nối chuỗi trả về một **`String`**, không thay đổi kiểu dữ liệu của biến gốc. Ví dụ `quantity` vẫn là `int` sau khi tham gia biểu thức `"quantity=" + quantity`.

**Lưu ý:** quy tắc `+` áp dụng khi biểu thức đã được phân tích theo **thứ tự toán tử và dấu ngoặc**; không phải cứ trong cùng một dòng có `String` thì toàn bộ các phép `+` đều trở thành nối chuỗi.

## 2. Khi một biểu thức có cả số và chuỗi

`"sum=" + a + b` nối lần lượt hai giá trị số vào nhãn, còn `"sum=" + (a + b)` cộng hai số trước rồi mới chuyển tổng thành văn bản. Nếu có nhiều bước tính toán, tách thành `int sum = a + b;` giúp cả phép tính lẫn thông báo dễ kiểm tra hơn.

Quy tắc có `String` áp dụng cho **từng phép `+` sau khi nhóm biểu thức**, không tự biến mọi phép cộng số trên cùng một dòng thành phép nối. Bài tiếp theo phân tích sâu tính kết hợp trái, độ ưu tiên, thứ tự đánh giá có tác dụng phụ và sự khác biệt giữa `+=` với phép gán thông thường.

## 3. Chuyển primitive thành văn bản

Khi nối với `String`, Java thực hiện **string conversion** để biểu diễn giá trị còn lại:

~~~java
int count = 7;
long size = 12L;
double ratio = 1.5;
boolean enabled = true;
char grade = 'A';

System.out.println("count=" + count);   // count=7
System.out.println("size=" + size);     // size=12
System.out.println("ratio=" + ratio);   // ratio=1.5
System.out.println("enabled=" + enabled); // enabled=true
System.out.println("grade=" + grade);   // grade=A
~~~

Với kiểu nguyên thủy, các method `String.valueOf(...)` tương ứng là cách chuyển **tường minh** và dễ dùng lại:

~~~java
String countText = String.valueOf(7);
String flagText = String.valueOf(false);
String gradeText = String.valueOf('A');

System.out.println(countText); // 7
System.out.println(flagText);  // false
System.out.println(gradeText); // A
~~~

**Phân biệt giá trị và định dạng:** `String.valueOf(1.5)` cho `"1.5"`, không tự thêm đơn vị, phần trăm hay làm tròn thành hai chữ số sau dấu phẩy. Cách hiển thị theo quy tắc nghiệp vụ là một công việc riêng.

Đối với `char`, phép `+` **không phải lúc nào cũng nối ký tự**:

~~~java
System.out.println('A' + 'B');         // 131
System.out.println("chars=" + 'A' + 'B'); // chars=AB
~~~

Biểu thức `'A' + 'B'` là phép **cộng số** trên hai giá trị `char` (được nâng thành `int`): 65 + 66 = 131. Ở dòng sau, mỗi `char` tham gia phép `+` có toán hạng `String` nên được nối thành văn bản.

## 4. `null`, đối tượng và phương thức `toString()`

Khi một giá trị tham chiếu được nối vào chuỗi:

- Nếu tham chiếu là `null`, văn bản nhận được là `"null"`.
- Nếu không phải `null`, Java chuyển giá trị thành dạng chuỗi phù hợp với ngữ nghĩa string conversion, thường dựa vào `toString()` của object.

~~~java
String missing = null;
Object item = null;

System.out.println("missing=" + missing); // missing=null
System.out.println("item=" + item);       // item=null
~~~

Với kiểu đối tượng do bạn tự định nghĩa, **ghi đè `toString()`** nếu muốn một mô tả rõ nghĩa:

~~~java
final class Product {
    private final int id;

    Product(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Product#" + id;
    }
}

// Trong method:
Product product = new Product(7);
System.out.println("product=" + product); // product=Product#7
~~~

Không nên dựa vào `Object.toString()` mặc định để tạo văn bản hướng tới người dùng: kết quả thường có tên class và mã hash dạng hex, không phải nội dung nghiệp vụ ổn định.

**`null` không trở thành chuỗi bằng chính nó.** `String missing = null;` là một tham chiếu null; chỉ khi nối/convert, chuỗi `"null"` mới xuất hiện. Vì vậy cần quyết định theo yêu cầu liệu nên hiển thị `"null"`, chuỗi rỗng, dấu gạch ngang hay thông báo “chưa có dữ liệu”.

Một ví dụ chuyển tường minh an toàn:

~~~java
Object value = null;
System.out.println(String.valueOf(value)); // null
~~~

Ở đây chọn overload `String.valueOf(Object)`. Không nên viết `String.valueOf(null)` thiếu kiểu trong code ví dụ: overload `String.valueOf(char[])` là một chi tiết dễ gây nhầm và có thể dẫn tới ngoại lệ khi truyền mảng null.

## 5. Nối mảng: cần hiển thị nội dung, không phải tham chiếu

Một lỗi thường gặp là ghép mảng trực tiếp vào `String` rồi mong nhìn thấy các phần tử:

~~~java
int[] numbers = {2, 4, 6};
System.out.println("numbers=" + numbers); // Không phải "numbers=[2, 4, 6]"
~~~

Mảng là object; biểu diễn `toString()` mặc định của mảng thường có dạng ký hiệu kiểu mảng và hash, ví dụ `[I@...`. Phần hash phụ thuộc lần chạy; **không** đưa nó vào expected output cố định.

Để hiển thị nội dung mảng một chiều, dùng `java.util.Arrays.toString`:

~~~java
int[] numbers = {2, 4, 6};
System.out.println("numbers=" + java.util.Arrays.toString(numbers));
// numbers=[2, 4, 6]
~~~

Với mảng nhiều chiều, có thể cần `Arrays.deepToString` khi phần tử là các mảng object tương ứng.

**Trường hợp đặc biệt `char[]`:**

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
System.out.println(String.valueOf(letters)); // Java
System.out.println(java.util.Arrays.toString(letters)); // [J, a, v, a]
~~~

`String.valueOf(char[])` có overload riêng tạo văn bản từ **nội dung các phần tử**. Trong khi đó, phép `"text=" + letters` là string concatenation trên mảng tham chiếu và **không nên được dùng** nếu mục tiêu là chuyển cả mảng thành văn bản `Java`.

Đáng chú ý, `System.out.println(letters)` cũng có overload nhận `char[]` nên có thể in `Java`; điều này **không** có nghĩa mọi cách nối với mảng đều có hành vi giống nhau. Hãy gọi API chuyển đổi có chủ đích.

## 6. Nối chuỗi không thay đổi đối tượng String cũ

`String` là immutable. Biểu thức `message + "!"` tạo giá trị văn bản mới; `message += "!"` còn **gán lại biến** `message` để giữ kết quả đó:

~~~java
String original = "Hi";
String updated = original + "!";
System.out.println(original); // Hi
System.out.println(updated);  // Hi!
~~~

Với `final String name = "Lan";`, `name += "!";` là lỗi biên dịch vì cố gán lại biến `final`. Compiler/JVM có thể tối ưu ghép trong một biểu thức, nên không quy định rằng mỗi dấu `+` bắt buộc tạo một số đối tượng cụ thể. Bài về tính bất biến phân biệt chi tiết nội dung đối tượng với phép gán lại tham chiếu.


## 7. Khi cần xây văn bản qua nhiều bước

Một phép ghép ngắn bằng `+` dễ đọc. Khi nội dung tăng qua nhiều vòng lặp hoặc điều kiện, có thể dùng `StringBuilder` rồi kết thúc bằng `toString()`:

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append("|");
    }
    builder.append("item").append(i);
}
System.out.println(builder.toString()); // item1|item2|item3
~~~

`append` thay đổi builder mà không phải gán lại một `String` sau mỗi lần nối. Builder thích hợp khi cần xây văn bản nhiều bước, nhưng không phải lựa chọn bắt buộc cho mọi biểu thức `+`. Phần API sửa chuỗi, so sánh chi phí và `String.join` là trọng tâm riêng của bài `StringBuilder`.


## 8. Định dạng có quy tắc: String.format và Locale

`String.valueOf` và `+` làm nhiệm vụ chuyển/ghép giá trị, **không phải công cụ điều khiển chính xác định dạng báo cáo**. Nếu cần số chữ số thập phân, căn lề hoặc quy tắc hiển thị, có thể dùng `String.format`:

~~~java
String twoDecimals = String.format(
        java.util.Locale.ROOT, "%.2f", 12.5);
System.out.println(twoDecimals); // 12.50
~~~

Ở đây `%.2f` yêu cầu hiển thị **hai chữ số sau dấu thập phân**. `Locale.ROOT` giúp chọn quy tắc định dạng ổn định cho ví dụ; nếu là giao diện người dùng, hãy chọn `Locale` theo đối tượng sử dụng thay vì mặc định bỏ qua bản địa hóa.

| Cách viết | Ví dụ | Ý nghĩa |
|---|---|---|
| `"count=" + count` | `count=7` | Nối chuỗi đơn giản |
| `String.valueOf(count)` | `7` | Chuyển giá trị thành chuỗi |
| `String.format(Locale.ROOT, "%.2f", 12.5)` | `12.50` | Chỉ định số chữ số hiển thị |
| `Arrays.toString(numbers)` | `[2, 4, 6]` | Hiển thị phần tử mảng một chiều |
| `builder.append(...).toString()` | Văn bản được xây từng bước | Ghép nhiều lần |

Định dạng hiển thị **không biến số thực dấu phẩy động thành số thập phân chính xác tuyệt đối**. Ví dụ `0.1 + 0.2` vẫn có sai số nhị phân dù bạn định dạng kết quả thành `0.30`. Nếu cần tính tiền tệ chính xác theo decimal, nên xem xét `BigDecimal` hoặc kiểu số nguyên đại diện đơn vị nhỏ nhất, kèm quy tắc làm tròn.

## 9. Chuyển dữ liệu thành văn bản khác với parse văn bản

Hai chiều chuyển đổi không giống nhau:

~~~java
int number = 42;
String text = String.valueOf(number);   // int -> String
int restored = Integer.parseInt(text); // String -> int

System.out.println(text);              // 42
System.out.println(restored + 1);      // 43
~~~

`Integer.parseInt("42")` có thể chuyển dữ liệu hợp lệ thành số, nhưng `Integer.parseInt("forty-two")` ném `NumberFormatException`. Khi đọc input từ người dùng, cần validation/exception handling riêng.

Điều này quan trọng khi biểu thức `+` bị hiểu nhầm:

~~~java
String x = "10";
String y = "20";

System.out.println(x + y); // 1020
System.out.println(Integer.parseInt(x) + Integer.parseInt(y)); // 30
~~~

Nối hai chuỗi chứa chữ số không làm chúng tự trở thành số. Java không có quy tắc “tự parse số” chỉ vì văn bản trông giống một con số.

## 10. Ví dụ Java 17 đầy đủ, chạy độc lập

Lưu nội dung dưới đây vào tệp **`StringConcatDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class StringConcatDemo {
    private StringConcatDemo() {}

    static final class Product {
        private final int id;

        Product(int id) {
            this.id = id;
        }

        @Override
        public String toString() {
            return "Product#" + id;
        }
    }

    public static void main(String[] args) {
        int a = 3;
        int b = 40;

        System.out.println("numeric=" + (a + b));
        System.out.println("left associative=" + a + b);
        System.out.println("number first=" + (a + b) + " units");
        System.out.println("mixed=" + 1 + 2 + 3);
        System.out.println("grouped=" + (1 + 2 + 3));

        System.out.println("char math=" + ('A' + 'B'));
        System.out.println("char text=" + 'A' + 'B');
        System.out.println("primitive=" + a + "," + true + "," + 'X');

        Object missing = null;
        System.out.println("null=" + missing);
        System.out.println("valueOf(null)="
                + String.valueOf((Object) null));

        char[] letters = {'J', 'a', 'v', 'a'};
        int[] numbers = {2, 4, 6};
        System.out.println("char array=" + String.valueOf(letters));
        System.out.println("int array=" + Arrays.toString(numbers));

        Product product = new Product(7);
        System.out.println("object=" + product);

        String original = "A";
        String updated = original + "B";
        System.out.println("immutable=" + original + "/" + updated);

        StringBuilder builder = new StringBuilder();
        for (int i = 1; i <= 3; i++) {
            if (i > 1) {
                builder.append("|");
            }
            builder.append("item").append(i);
        }
        System.out.println("builder=" + builder);

        System.out.println("format="
                + String.format(Locale.ROOT, "%.2f", 12.5));
        System.out.println("floating sum=" + (0.1 + 0.2));
    }
}
~~~

Dùng **JDK 17 trở lên** và mở terminal trong thư mục có tệp.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StringConcatDemo.java
java -cp . StringConcatDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StringConcatDemo.java
java -cp . StringConcatDemo
~~~

**Expected output:**

~~~text
numeric=43
left associative=340
number first=43 units
mixed=123
grouped=6
char math=131
char text=AB
primitive=3,true,X
null=null
valueOf(null)=null
char array=Java
int array=[2, 4, 6]
object=Product#7
immutable=A/AB
builder=item1|item2|item3
format=12.50
floating sum=0.30000000000000004
~~~

Chương trình chỉ dùng JDK; kết quả trên là đầu ra dự kiến có thể đối chiếu khi chạy trên Java 17+. Nó không phụ thuộc hash object ngẫu nhiên, đầu vào bàn phím hoặc locale mặc định của hệ thống.

## 11. Lỗi thường gặp và cách sửa

| Đoạn mã / hiện tượng | Vấn đề | Cách đúng |
|---|---|---|
| `"sum=" + a + b` cho `sum=340` | `+` nối từ trái sang phải sau `String` | `"sum=" + (a + b)` |
| `"value=" + 1 + 2` cho `value=12` | `1` và `2` đã được ghép vào chuỗi | `"value=" + (1 + 2)` nếu muốn phép cộng |
| `'A' + 'B'` cho 131 | Cộng code unit `char`, không nối văn bản | `"" + 'A' + 'B'` hoặc dùng String |
| `"items=" + intArray` | Biểu diễn tham chiếu mảng, không phải phần tử | `Arrays.toString(intArray)` |
| `"word=" + charArray` | Nối mảng tham chiếu không phải overload `valueOf(char[])` | `String.valueOf(charArray)` |
| `String.valueOf(null)` không như mong đợi | Overload với `char[]` dễ gây bất ngờ | Chỉ rõ `(Object) null` nếu muốn `"null"` |
| `name += "!"` với biến `final` | `+=` gán lại biến | Tạo biến kết quả khác |
| Nối trong vòng lặp hàng nghìn lần | Nhiều kết quả trung gian, khó kiểm soát chi phí | `StringBuilder` |
| `"10" + "20"` cho `1020` | Chuỗi không tự parse số | Parse input rồi cộng `int` |
| Dùng `+` để bắt hiển thị đúng 2 chữ số thập phân | Nối chuỗi không kiểm soát định dạng | `String.format(Locale, "%.2f", value)` |
| `String.valueOf(someObject)` không có thông tin hữu ích | Object không ghi đè `toString()` thích hợp | Định nghĩa văn bản rõ nghĩa bằng method/API |
| `"value=" + nullable` hiển thị `null` cho người dùng | Cơ chế chuyển chuỗi khác mong đợi UI | Xử lý null thành placeholder theo nghiệp vụ |

**Đừng che lỗi dữ liệu bằng biểu diễn văn bản:** nếu `int` đã tràn trước khi nối, `"total=" + overflowed` chỉ in ra **kết quả đã sai**. Hãy kiểm tra miền/kiểu toán hạng trước khi tính và định dạng sau cùng.

## 12. Bài tập kèm đáp án

### Bài A — ưu tiên và kết hợp của `+`

~~~java
System.out.println("x=" + 10 + 20);
System.out.println("x=" + (10 + 20));
System.out.println(10 + 20 + " items");
~~~

**Đáp án:**

~~~text
x=1020
x=30
30 items
~~~

### Bài B — `char` cộng số hay nối chữ?

~~~java
System.out.println('A' + 1);
System.out.println("A" + 1);
~~~

**Đáp án:**

~~~text
66
A1
~~~

Ký tự `'A'` là `char` có giá trị số 65 nên cộng `1` ra 66; `"A"` là `String` nên nối số thành `A1`.

### Bài C — in danh sách số nguyên

~~~java
int[] scores = {7, 8};
System.out.println("scores=" + java.util.Arrays.toString(scores));
~~~

**Đáp án:** `scores=[7, 8]`. Dùng `Arrays.toString` chứ không nối trực tiếp mảng.

### Bài D — `null` và hiển thị

~~~java
Object value = null;
System.out.println("value=" + value);
System.out.println(String.valueOf(value));
~~~

**Đáp án:**

~~~text
value=null
null
~~~

Nếu ứng dụng không muốn chữ `null`, hãy xử lý trường hợp thiếu dữ liệu trước khi hiển thị, thay vì trông chờ phép `+` tự chọn placeholder.

### Bài E — nhiều lần ghép

Hãy tạo chuỗi `A-B-C` từ các giá trị `"A"`, `"B"`, `"C"`.

**Đáp án đơn giản:** `String joined = "A" + "-" + "B" + "-" + "C";`.

**Đáp án khi cần lặp:**

~~~java
String[] parts = {"A", "B", "C"};
StringBuilder sb = new StringBuilder();
for (String part : parts) {
    if (sb.length() > 0) {
        sb.append("-");
    }
    sb.append(part);
}
System.out.println(sb); // A-B-C
~~~

## 13. Checklist tự đánh giá

- [ ] Biết khi nào `+` là cộng số, khi nào là nối `String`.
- [ ] Hiểu `+` kết hợp trái và dùng ngoặc để cộng trước khi nối.
- [ ] Biết cách chuyển `int`, `double`, `boolean`, `char` thành văn bản.
- [ ] Phân biệt nối chuỗi với `String.valueOf(...)`.
- [ ] Biết `null` thành văn bản `"null"` nhưng không tự là `String`.
- [ ] Biết object nên có `toString()` phù hợp khi cần mô tả.
- [ ] Dùng `Arrays.toString` cho mảng và `String.valueOf(char[])` cho mảng ký tự.
- [ ] Hiểu `String` bất biến và `+=` là gán lại biến.
- [ ] Chọn `StringBuilder` cho nhiều lần ghép, không tối ưu sớm mọi phép `+`.
- [ ] Dùng `String.format` với `Locale` phù hợp khi cần định dạng rõ.
- [ ] Phân biệt chuyển số sang chuỗi với parse chuỗi thành số.
- [ ] Biên dịch/chạy `StringConcatDemo.java` bằng `javac`/`java`, đối chiếu toàn bộ đầu ra.

**Kết luận:** Toán tử `+` rất tiện để ghép giá trị thành `String`, nhưng phải đọc đúng **thứ tự tính toán** để không nhầm cộng số với nối văn bản. Dùng `String.valueOf`, `Arrays.toString`, `toString()`, `StringBuilder` và `String.format` khi chúng làm mục đích chuyển đổi, xây dựng hoặc định dạng trở nên rõ ràng và có thể kiểm chứng.
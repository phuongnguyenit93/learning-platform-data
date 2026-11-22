# Chuyển Object qua toString khi tham gia nối chuỗi trong Java

Trong Java, toán tử `+` không chỉ cộng các số. Khi **ít nhất một toán hạng là `String`**, nó thực hiện **nối chuỗi** (*string concatenation*). Nếu toán hạng còn lại là một đối tượng, Java áp dụng **string conversion** để lấy biểu diễn văn bản của giá trị đó; với đối tượng không phải `null`, hành vi thông thường được xác định thông qua phương thức `toString()`.

Ví dụ:

```java
Object value = Integer.valueOf(42);
String message = "Giá trị: " + value;
System.out.println(message); // Giá trị: 42
```

Ở đây `Integer` cung cấp `toString()`, nên phần được nối là văn bản `42`. Tuy nhiên, **không được hiểu rằng mọi `Object` tự động có biểu diễn dễ đọc**: nếu lớp không ghi đè `toString()`, kết quả thường có dạng `TenLop@maHex`; và với `null`, Java nối chuỗi văn bản `"null"` thay vì gọi phương thức trên tham chiếu rỗng.

Bài này tập trung vào **cách giá trị Object được chuyển thành văn bản khi tham gia phép nối**, không chỉ cách sử dụng toán tử `+`.

## 1. String conversion khi dùng toán tử +

Với biểu thức:

```java
String result = "Item: " + someObject;
```

nếu `someObject` có kiểu tham chiếu như `Book`, `Object`, `List<?>` hoặc một kiểu tự định nghĩa, Java cần một biểu diễn `String` của giá trị ở phía phải. Về mặt **mô hình ngữ nghĩa**:

1. Đánh giá các toán hạng của phép `+` theo quy tắc đánh giá biểu thức Java.
2. Nếu một toán hạng thuộc kiểu `String`, phép `+` là nối chuỗi; toán hạng còn lại được chuyển sang biểu diễn chuỗi thích hợp.
3. Với một **tham chiếu đối tượng khác `null`**, hành vi biểu diễn văn bản gắn với `toString()` của kiểu thực tế.
4. Với một **tham chiếu `null`**, kết quả string conversion là bốn chữ cái `"null"`.
5. Kết hợp các phần văn bản để tạo giá trị `String` của biểu thức nối.

**Lưu ý kỹ thuật:** Đây là quy tắc **quan sát được ở cấp ngôn ngữ**, không phải cam kết rằng bytecode phải gọi tường minh `String.valueOf(Object)` hay tạo `StringBuilder`. Trình biên dịch/JVM được phép sử dụng chiến lược tối ưu khác, miễn giữ đúng ngữ nghĩa Java.

Khi đọc:

```java
String line = "User=" + user;
```

có thể hình dung rằng Java cần biểu diễn `user` theo ý nghĩa của `String.valueOf(user)` nếu `user` là tham chiếu đối tượng. Nhưng đừng kết luận “Java nhất định biên dịch thành lời gọi `user.toString()` ở vị trí đó”: cơ chế thực thi cụ thể còn phụ thuộc compiler và JDK.

### Những giá trị nào được chuyển thành văn bản?

| Loại toán hạng | Ví dụ | Biểu diễn khi nối |
|---|---|---|
| `String` | `"abc"` | Nội dung chuỗi đó |
| Số nguyên primitive | `42` | Văn bản `"42"` |
| `boolean` | `true` | Văn bản `"true"` |
| `char` | `'A'` | Văn bản `"A"` |
| Đối tượng có `toString()` hữu ích | `new Book("Java")` | Giá trị do `Book.toString()` tạo |
| Đối tượng không ghi đè `toString()` | `new Object()` | Mẫu mặc định `TenLop@hexHash`, không phải nội dung nghiệp vụ |
| Tham chiếu `null` | `(Object) null` | `"null"` |
| Array như `int[]` | `new int[]{1,2}` | Thường là biểu diễn identity mặc định, **không** phải `"[1, 2]"` |

Quy tắc với primitive liên quan đến **chuyển đổi dữ liệu nguyên thủy thành văn bản**; primitive **không có** phương thức instance `toString()`. Chỉ giá trị kiểu tham chiếu có thể gọi `toString()`.

## 2. Vai trò của Object.toString()

Mọi lớp Java đều kế thừa hoặc có thể ghi đè `toString()` từ `java.lang.Object`. Chữ ký:

```java
public String toString()
```

Phiên bản mặc định của `Object` tạo một chuỗi đại khái theo dạng:

```text
Tên_lớp@giá_trị_hash_hệ_16
```

Ví dụ dạng `com.example.User@5e2de80c`. **Giá trị hash, tên lớp đầy đủ và số lần tạo đối tượng không nên được dùng làm output cố định trong bài kiểm thử.** Đây không phải định dạng dành cho người dùng cuối hoặc dữ liệu có tính ổn định.

Một lớp nên ghi đè `toString()` nếu ứng dụng cần biểu diễn văn bản có ý nghĩa trong log hoặc khi ghép vào thông báo.

```java
final class Book {
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

Đây là **định nghĩa lớp minh họa**. Với `new Book("Java")`:

```java
Book book = new Book("Java");
System.out.println("Item: " + book); // Item: Book(Java)
```

Phần văn bản `Book(Java)` do **`Book.toString()` quyết định**. Toán tử `+` không biết `title` là trường gì và không tự đọc các trường của đối tượng.

### Tính đa hình

Khi biến được khai báo kiểu cha `Object` nhưng thực sự trỏ đến một `Book`, `Book.toString()` vẫn được dùng:

```java
Object item = new Book("Java");
String line = "Item: " + item; // Item: Book(Java)
```

Chính **kiểu đối tượng lúc chạy** quyết định phương thức ghi đè nào được thực thi, không phải chỉ kiểu tĩnh `Object` của biến.

Nếu lớp không ghi đè `toString()`, Java sử dụng triển khai được kế thừa. Điều này giải thích vì sao đôi khi log chỉ hiện dạng `Book@...` thay vì trường `title` mong muốn.

## 3. Null: không giống gọi toString() trực tiếp

Đây là sự khác biệt dễ gây nhầm nhất:

```java
Object missing = null;

String a = "Value: " + missing;
String b = String.valueOf(missing);

System.out.println(a); // Value: null
System.out.println(b); // null
```

Hai biểu thức trên **không ném `NullPointerException`**. Với toán tử nối chuỗi, tham chiếu `null` được chuyển thành văn bản `"null"`; `String.valueOf(Object)` cũng xử lý `null` tương ứng.

Ngược lại:

```java
Object missing = null;
// missing.toString(); // Nếu thực thi: NullPointerException
```

**Không có object nào để gọi phương thức** khi receiver là `null`. Java không lén gọi `toString()` trên `null` lúc nối chuỗi.

Một bảng phân biệt:

| Biểu thức | Kết quả |
|---|---|
| `"x=" + (Object) null` | `"x=null"` |
| `String.valueOf((Object) null)` | `"null"` |
| `Objects.toString(null)` | `"null"` |
| `Objects.toString(null, "N/A")` | `"N/A"` |
| `((Object) null).toString()` | Ném `NullPointerException` |

Các ví dụ với `Objects` cần `import java.util.Objects;`. Lưu ý phương thức `Objects.toString(obj, nullDefault)` cho phép chọn chuỗi thay thế khi đối tượng `null` — phù hợp khi muốn hiển thị `"(chưa có)"` hoặc `"N/A"` thay vì chuỗi `"null"`.

### Cẩn thận với String.valueOf(null) không ép kiểu

Java có nhiều overload `String.valueOf(...)`, trong đó có `valueOf(Object)` và `valueOf(char[])`. Khi viết:

```java
// String.valueOf(null); // Có thể chọn overload char[] rồi ném NullPointerException
String result = String.valueOf((Object) null); // "null"
```

Dòng được chú thích chỉ để giải thích **overload resolution**. Việc ép kiểu `(Object) null` giúp chọn đúng overload xử lý tham chiếu đối tượng. Trong mã thông thường khi biến đã có kiểu tĩnh `Object`, `String.valueOf(variable)` sẽ chọn overload `Object`.

## 4. String.valueOf(Object) có giống toString() không?

`String.valueOf(Object obj)` cung cấp một điểm gọi dễ dùng để biến tham chiếu thành `String`. Với một object không null, hàm sử dụng biểu diễn do `obj.toString()` trả về; với `null`, hàm trả chuỗi `"null"`.

```java
Book book = new Book("Java");

String a = book.toString();
String b = String.valueOf(book);
String c = "" + book;

System.out.println(a.equals(b)); // true
System.out.println(b.equals(c)); // true
```

Ví dụ trên giả định định nghĩa `Book` ở mục 2. Tất cả có cùng **nội dung**, không nên dùng `==` để suy luận rằng các biến nhất thiết tham chiếu cùng một object `String`.

Cần phân biệt ba câu hỏi:

- **`toString()` trả văn bản gì?** Phụ thuộc cách lớp cài đặt.
- **`String.valueOf(...)` xử lý null và overload ra sao?** Phụ thuộc kiểu đối số đã được trình biên dịch chọn.
- **Toán tử `+` nối chuỗi tạo kết quả gì?** Theo quy tắc *string conversion* và *string concatenation* của Java.

Một `toString()` được thiết kế kém cũng có thể ném exception hoặc sinh văn bản không ổn định. `String.valueOf` và toán tử `+` **không tự xác thực** hay bảo đảm nội dung do `toString()` cung cấp phù hợp với nghiệp vụ.

## 5. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây tránh in giá trị identity-hash không dự đoán được của mảng, thay vào đó **so sánh hành vi** và dùng `Arrays.toString` để in dữ liệu mảng theo định dạng rõ ràng.

Lưu thành **`ObjectConcatDemo.java`**:

```java
import java.util.Arrays;

public class ObjectConcatDemo {
    static final class Book {
        private final String title;

        Book(String title) {
            this.title = title;
        }

        @Override
        public String toString() {
            return "Book(" + title + ")";
        }
    }

    static final class Tracked {
        static int calls;

        @Override
        public String toString() {
            calls++;
            return "tracked";
        }
    }

    public static void main(String[] args) {
        Object book = new Book("Java");
        Object missing = null;

        System.out.println("item: " + book);
        System.out.println("missing: " + missing);
        System.out.println("valueOf null: " + String.valueOf(missing));
        System.out.println("valueOf matches: "
                + String.valueOf(book).equals("Book(Java)"));
        System.out.println("book content equals: "
                + book.equals("Book(Java)"));

        int[] numbers = {1, 2, 3};
        System.out.println("array readable: "
                + Arrays.toString(numbers));
        System.out.println("array concat is readable: "
                + ("Array: " + numbers).equals("Array: [1, 2, 3]"));

        Tracked tracked = new Tracked();
        System.out.println("tracked: " + tracked);
        System.out.println("toString calls: " + Tracked.calls);

        System.out.println("math1: " + ("sum=" + 7 + 3));
        System.out.println("math2: " + ("sum=" + (7 + 3)));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ObjectConcatDemo.java
java ObjectConcatDemo
```

Kết quả:

```text
item: Book(Java)
missing: null
valueOf null: null
valueOf matches: true
book content equals: false
array readable: [1, 2, 3]
array concat is readable: false
tracked: tracked
toString calls: 1
math1: sum=73
math2: sum=10
```

**Phân tích:**

1. `book` được khai báo là `Object` nhưng trỏ đến `Book`; phương thức `Book.toString()` trả `"Book(Java)"`.
2. `missing` là `null`, nên tham gia `"missing: " + missing` thành văn bản `"null"` và không ném exception.
3. `String.valueOf(missing)` trả `"null"`. Với `book`, `String.valueOf(book)` có nội dung bằng `"Book(Java)"`.
4. `book.equals("Book(Java)")` là `false` vì `Book` trong ví dụ không ghi đè `equals`; kế thừa cách so sánh identity của `Object`. **Biểu diễn text giống nhau không làm hai giá trị thuộc hai kiểu trở thành bằng nhau**.
5. Mảng `int[]` không tự chuyển thành `"[1, 2, 3]"` khi nối. `Arrays.toString(numbers)` mới là phương pháp tường minh để hiển thị nội dung mảng một chiều.
6. `Tracked.toString()` tăng biến đếm `calls` mỗi lần được gọi. Phép nối đơn giản `"tracked: " + tracked` tạo `tracked: tracked` và có **một lần gọi** trên đối tượng này trong chương trình.
7. `+` là toán tử **kết hợp trái** (*left-associative*). `"sum=" + 7 + 3` được hiểu như `("sum=" + 7) + 3` nên ra `sum=73`, còn `"sum=" + (7 + 3)` cộng số trước rồi thành `sum=10`.

Ví dụ cho thấy Java quyết định **khi nào `+` là phép cộng số và khi nào là nối chuỗi**, còn cách chuyển một `Object` thành văn bản là vấn đề riêng.

## 6. Mảng là trường hợp rất hay bị hiểu sai

Mảng Java cũng là đối tượng, nhưng `int[]`, `String[]` và mảng nhiều chiều **không mặc nhiên override `toString()` để hiển thị từng phần tử**. Vì thế:

```java
int[] scores = {7, 8, 9};
String message = "Scores: " + scores;
```

`message` **không** có dạng `"Scores: [7, 8, 9]"`. Nó sẽ chứa chuỗi biểu diễn đối tượng mảng, thường gồm tên kiểu JVM của mảng và mã hex liên quan identity; giá trị cụ thể không ổn định để kiểm thử bằng cách so sánh toàn bộ.

Nếu cần trình bày dữ liệu, dùng:

```java
import java.util.Arrays;

int[] scores = {7, 8, 9};
String formatted = "Scores: " + Arrays.toString(scores);
System.out.println(formatted); // Scores: [7, 8, 9]
```

Với mảng nhiều chiều:

```java
int[][] matrix = {{1, 2}, {3, 4}};
System.out.println("matrix: " + Arrays.deepToString(matrix));
// matrix: [[1, 2], [3, 4]]
```

Hai đoạn trên là **đoạn mã minh họa**: cần đặt trong method phù hợp và có import `java.util.Arrays`. Nếu giá trị là mảng đối tượng có cấu trúc lồng nhau, cân nhắc `Arrays.deepToString(...)`. Nó hữu ích cho debug, nhưng khi xuất định dạng trao đổi dữ liệu chính thức (JSON, CSV, v.v.) nên dùng thư viện/serializer có hợp đồng rõ ràng.

### Trường hợp đặc biệt: char[]

Có sự khác biệt dễ gây bất ngờ giữa **nối chuỗi** và **chọn overload của println/valueOf**:

```java
char[] letters = {'J', 'a', 'v', 'a'};

System.out.println(letters);               // Java
System.out.println(String.valueOf(letters)); // Java
System.out.println("prefix: " + letters);   // Thường là prefix: [C@...
```

`System.out.println(char[])` có overload riêng để in **các ký tự trong mảng**, và `String.valueOf(char[])` cũng có overload chuyên biệt. Nhưng trong `"prefix: " + letters`, array được tham gia **string conversion** theo quy tắc nối, không phải tự động gọi overload in `char[]`. Không nên trông chờ kết quả giống hai dòng đầu.

Đây là lý do việc chỉ nhìn kết quả `println(someValue)` có thể gây hiểu nhầm về **hành vi riêng của phép `"prefix: " + someValue`**: `println` có nhiều overload, còn toán tử `+` tuân theo quy tắc của ngôn ngữ.

## 7. toString() mặc định, equals() và hashCode() không phải một

Ba khái niệm cần tách biệt:

- **`toString()`**: trả biểu diễn văn bản của đối tượng.
- **`equals(Object)`**: định nghĩa tính bằng nhau của đối tượng (nếu lớp ghi đè).
- **`hashCode()`**: dùng trong các cấu trúc dựa trên hash và phải tuân theo hợp đồng với `equals`.

Việc ghi đè `toString()` **không tự làm thay đổi** `equals` hoặc `hashCode`. Nếu hai đối tượng có cùng `toString()`, không có nghĩa chúng bằng nhau, cũng không có nghĩa chúng là cùng tham chiếu.

Ví dụ:

```java
Book one = new Book("Java");
Book two = new Book("Java");

System.out.println(one.toString().equals(two.toString())); // true
System.out.println(one == two);                             // false
System.out.println(one.equals(two));                        // false
```

Đoạn ví dụ dùng lớp `Book` đã khai báo ở trên, **không** override `equals`. Nếu một domain entity cần so sánh giá trị, hãy tự thiết kế `equals`/`hashCode` hoặc dùng một kiểu có ngữ nghĩa giá trị rõ ràng như `record` khi phù hợp. Không dùng `toString()` để thay thế phép so sánh giá trị.

Tương tự, `Object.toString()` mặc định thường liên quan `hashCode()` trong phần văn bản sau dấu `@`, nhưng biểu diễn hex **không phải** ID duy nhất, không ổn định giữa các lần chạy và không nên dùng làm khóa nghiệp vụ.

## 8. Lúc nào toString() được gọi và có tác dụng phụ gì?

Một phương thức `toString()` có thể thực hiện công việc tùy ý: tính toán, đọc field, truy cập trạng thái hoặc thậm chí ném exception. Khi object tham gia nối chuỗi, **cách biểu diễn của nó được đánh giá trong quá trình thực thi phép nối**. Đây không phải việc Java “lưu sẵn” bản in của object khi tạo đối tượng.

Ví dụ, nếu một đối tượng thay đổi nội dung, các lần nối chuỗi diễn ra ở thời điểm khác nhau có thể sinh text khác nhau:

```java
final class Counter {
    int value;

    @Override
    public String toString() {
        return "Counter(" + value + ")";
    }
}
```

Trong một method:

```java
Counter counter = new Counter();
String before = "State: " + counter;
counter.value = 2;
String after = "State: " + counter;

System.out.println(before); // State: Counter(0)
System.out.println(after);  // State: Counter(2)
```

Việc dùng `toString()` chỉ để định dạng **không làm cho đối tượng bất biến**. Nếu `toString()` ném unchecked exception, thao tác tạo chuỗi cũng có thể thất bại. Điều này quan trọng khi ghi log hoặc thông báo lỗi: một `toString()` có side effect hay phụ thuộc dịch vụ ngoài có thể khiến chẩn đoán khó khăn.

**Khuyến nghị thiết kế:** `toString()` nên dễ hiểu, có chi phí hợp lý, không phụ thuộc dịch vụ ngoài khi có thể, và không vô tình tiết lộ password, access token, thông tin tài chính hay dữ liệu nhạy cảm. Ghi log bằng `"user=" + user` sẽ đưa kết quả `toString()` vào log; cần chủ động kiểm soát trường nào được xuất.

### Những vòng gọi đệ quy cần tránh

Nếu trong `toString()` lại nối chính `this`:

```java
@Override
public String toString() {
    return "Self: " + this; // Sai: liên tục gọi lại toString()
}
```

có thể xảy ra đệ quy vô hạn cho tới `StackOverflowError`. Thay vào đó, xây dựng text từ các field cụ thể hoặc kiểu dữ liệu đơn giản. Khi object graph có chu trình, một số cách ghép `toString()` qua các đối tượng liên kết cũng có thể gây đệ quy; cần cách in có nhận diện vòng lặp nếu dữ liệu có cấu trúc như vậy.

## 9. Thứ tự đánh giá, cộng số và nối chuỗi

Với `String` ở bên trái, `"sum=" + 7 + 3` cho `"sum=73"`; ngoặc trong `"sum=" + (7 + 3)` cho `"sum=10"`. Quy tắc này giống các phép nối khác và không làm `Object` nguồn biến thành `String`. Bài **Thứ tự kết hợp trái–phải** dành riêng cho phân tích cú pháp, còn ở đây chú ý **hàm `toString()` của đối tượng được gọi lúc nào và có tác dụng phụ gì**.

## 10. StringBuilder.append(Object) và các cách định dạng khác

Khi xây dựng text từ nhiều phần trong vòng lặp, thường sử dụng `StringBuilder`:

```java
Object book = new Book("Java");

String message = new StringBuilder()
        .append("Item: ")
        .append(book)
        .toString();
```

`StringBuilder.append(Object)` dùng biểu diễn chuỗi của đối tượng (theo hợp đồng `String.valueOf(Object)`), do đó ví dụ cũng sinh `"Item: Book(Java)"`. Với `null`, nó đưa văn bản `"null"` vào builder.

**Tuy nhiên `StringBuilder` có nhiều overload** như `append(char[])` và `append(int)`. Nếu truyền mảng `char[]` trực tiếp, overload `append(char[])` có thể được chọn và nối các ký tự; còn `append((Object) letters)` dùng hướng xử lý đối tượng. Vì thế, so sánh behavior luôn phải xét **kiểu tĩnh của biểu thức và overload nào được chọn**.

### Có phải nối chuỗi bằng + luôn tạo StringBuilder?

Không. Nhiều ví dụ và tài liệu JVM cũ mô tả compiler “dịch phép nối thành `StringBuilder`”, nhưng đó không phải quy tắc bất biến của ngôn ngữ. Trên các JDK hiện đại, compiler thường dùng cơ chế **`invokedynamic` với string-concat recipes** (JEP 280) và JVM có thể tối ưu thêm. Hợp đồng mà mã ứng dụng dựa vào là **giá trị và ngữ nghĩa của biểu thức nối**, không phải một bytecode hay cấu trúc builder cụ thể.

Có thể khảo sát bằng:

```bash
javac ObjectConcatDemo.java
javap -c -p ObjectConcatDemo
```

Trong bytecode của compiler/JDK phù hợp có thể thấy `invokedynamic` cho string concatenation. Đừng suy luận hiệu năng chỉ từ số lần nhìn thấy `new StringBuilder` trong một output: JVM có thể áp dụng nhiều tối ưu, và chi phí `toString()` do lớp tự định nghĩa đôi khi đáng kể hơn thao tác nối.

Nếu cần đo đạc, dùng benchmark nghiêm túc với JMH; không kết luận `+` luôn chậm hơn `StringBuilder` trong mọi ngữ cảnh.

### Khi nào nên định dạng rõ ràng thay vì nối Object?

- **Mảng:** `Arrays.toString` hoặc `Arrays.deepToString`.
- **Ngày/giờ:** dùng `java.time.format.DateTimeFormatter` khi cần format xác định.
- **Số tiền:** dùng `NumberFormat`/`DecimalFormat` cùng locale và quy tắc làm tròn phù hợp.
- **Dữ liệu JSON/XML:** sử dụng serializer đúng chuẩn, **không** coi `toString()` là JSON.
- **Thông báo cho người dùng:** dùng template/formatter rõ ràng và tránh đưa toàn bộ object nội bộ ra giao diện.
- **Log:** `toString()` có thể hữu ích khi dữ liệu không nhạy cảm, nhưng cần kiểm soát nội dung, chi phí và exception.

## 11. Các nhầm lẫn và lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu/khắc phục |
|---|---|---|
| “Nối Object thì Java gọi `toString()` trên cả null.” | `null` không có instance để gọi method; phép nối tạo `"null"` theo string conversion | Phân biệt `"x=" + nullReference` với `nullReference.toString()` |
| “Mọi object tự động nối thành các giá trị field.” | `Object.toString()` mặc định thường chỉ in tên lớp và hash | Override `toString()` khi cần, hoặc định dạng trường tường minh |
| “`"Array: " + array` liệt kê phần tử.” | Mảng không có `toString()` hiển thị nội dung | Dùng `Arrays.toString`/`deepToString` |
| “`System.out.println(charArray)` và `"x=" + charArray` hoạt động giống nhau.” | `println` có overload `char[]`; toán tử nối dùng string conversion | Xác định API và kiểu tĩnh của đối số |
| “`String.valueOf(null)` luôn trả `"null"`.” | Overload `char[]` có thể được chọn cho literal `null` | Chỉ rõ `String.valueOf((Object) null)` hoặc dùng biến `Object` |
| “`toString()` cùng text thì `equals` phải true.” | Text representation không định nghĩa equality | Thiết kế `equals/hashCode` riêng |
| “Object được đổi thành String vĩnh viễn sau phép nối.” | `+` chỉ tạo giá trị chuỗi kết quả | Biến nguồn giữ nguyên kiểu và tham chiếu |
| “Kết quả `Object.toString()` mặc định là ID ổn định.” | Dạng `Class@hex` không phải khóa nghiệp vụ | Dùng ID do hệ thống quản lý |
| “`toString()` không thể gây lỗi.” | Override có thể throw hoặc đệ quy | Giữ `toString()` đơn giản và an toàn |
| “Java bắt buộc biên dịch nối chuỗi thành `new StringBuilder`.” | Chi tiết compiler/JDK có thể thay đổi | Dựa vào ngữ nghĩa JLS, không hardcode chiến lược bytecode |

## 12. Bài tập tự kiểm tra

### Bài 1: null và override

Cho:

```java
final class User {
    final String name;
    User(String name) { this.name = name; }

    @Override
    public String toString() {
        return "User(" + name + ")";
    }
}

Object a = new User("Lan");
Object b = null;

System.out.println("a=" + a);
System.out.println("b=" + b);
```

**Đáp án:**

```text
a=User(Lan)
b=null
```

Dòng thứ nhất dùng `User.toString()` qua đa hình; dòng thứ hai dùng string conversion của tham chiếu null.

### Bài 2: khác biệt phép cộng và phép nối

Dự đoán:

```java
Object number = Integer.valueOf(8);
System.out.println("n=" + number + 2);
System.out.println("n=" + (8 + 2));
```

**Đáp án:**

```text
n=82
n=10
```

Sau khi xuất hiện `String` phía trái, các phép `+` còn lại là nối văn bản. Biểu thức trong ngoặc trước hết thực hiện cộng hai số.

### Bài 3: mảng

Cho:

```java
String[] names = {"Lan", "Minh"};
String a = "names=" + names;
String b = "names=" + java.util.Arrays.toString(names);
```

Hỏi biểu thức nào hiển thị `names=[Lan, Minh]`? **Đáp án:** chỉ `b`; `a` biểu diễn đối tượng mảng chứ không tự nối các phần tử.

### Bài 4: giá trị đối tượng và giá trị String

Một lớp `Customer` override `toString()` trả `"VIP"`. Hai đối tượng khác nhau đều có `toString()` bằng `"VIP"`. Điều đó có làm `customer1 == customer2` đúng không? **Không.** Hai tham chiếu khác nhau vẫn khác identity. Việc hai `String` có nội dung giống nhau không thay đổi equality của hai đối tượng nguồn.

## 13. Tài liệu chính thức

- [Java Language Specification `15.18.1 — String Concatenation Operator +`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): quy tắc nối chuỗi của toán tử `+`.
- [Java Language Specification `5.1.11 — String Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.11): xử lý giá trị primitive, tham chiếu đối tượng và null khi chuyển sang chuỗi.
- [Java SE 17 — `Object.toString()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()): hành vi và mục đích của method.
- [Java SE 17 — `String.valueOf(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)): chuyển object hoặc null thành text.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): minh họa lý do không nên đồng nhất phép nối Java với một chiến lược bytecode cụ thể.

**Ghi nhớ:** Khi một `Object` tham gia nối với `String` bằng `+`, Java thực hiện *string conversion*: với object khác null, biểu diễn phụ thuộc `toString()` của kiểu thực lúc chạy; với null, văn bản là `"null"`. **`toString()` chỉ là biểu diễn văn bản, không phải identity, equality hay serializer**, và với mảng hoặc dữ liệu nghiệp vụ nên định dạng tường minh khi cần đầu ra ổn định, dễ hiểu.

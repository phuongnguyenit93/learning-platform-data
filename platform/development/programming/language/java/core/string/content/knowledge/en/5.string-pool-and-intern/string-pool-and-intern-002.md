# Biểu thức hằng chuỗi được tính khi biên dịch trong Java

## 1. Hiện tượng cần hiểu

Hai cách viết sau tạo ra **cùng một giá trị chuỗi** `"Java"`:

```java
String a = "Java";
String b = "Ja" + "va";
```

Điểm thú vị: biểu thức `"Ja" + "va"` **không cần ghép hai chuỗi trong lúc chương trình chạy**. Vì cả hai toán hạng đều là hằng, trình biên dịch Java có thể và theo ngữ nghĩa ngôn ngữ sẽ xử lý chúng như một **biểu thức hằng chuỗi** (*constant string expression*), có giá trị `"Java"` ngay từ lúc biên dịch.

```java
System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Ở ví dụ này, `a == b` là `true` vì các chuỗi có giá trị là biểu thức hằng được **intern**: chuỗi có cùng nội dung dùng chung một tham chiếu chuẩn hóa trong *string pool*. Tuy nhiên, trong ứng dụng thực tế, muốn kiểm tra **nội dung văn bản**, luôn ưu tiên `.equals(...)` thay vì dựa vào `==`.

Bài học này giải thích điều kiện để phép nối chuỗi được tính khi biên dịch, mối liên hệ với pool và `intern()`, cách phân biệt với nối chuỗi lúc chạy, cùng các nhầm lẫn khi đọc hoặc tối ưu mã Java.

## 2. Biểu thức hằng (*constant expression*) là gì?

**Constant expression** là biểu thức có giá trị được xác định từ những thành phần và phép toán được Java cho phép tại thời điểm biên dịch. Quy tắc ngôn ngữ được mô tả trong *Java Language Specification*, mục **15.29 – Constant Expressions**.

Với chuỗi, các ví dụ đơn giản là:

```java
String first = "Java";                   // Literal chuỗi
String second = "Ja" + "va";             // Nối hai literal
String version = "Java " + 17;           // Chuỗi cộng với hằng số nguyên
String calculated = "Kết quả: " + (1 + 2); // Hằng số học + chuỗi
```

Giá trị tương ứng là `"Java"`, `"Java"`, `"Java 17"` và `"Kết quả: 3"`.

Toán tử `+` có hai ý nghĩa liên quan ở đây:

- Nếu hai toán hạng là số, `+` có thể là phép cộng số học.
- Nếu một toán hạng là `String`, `+` dùng để **nối chuỗi**, chuyển toán hạng còn lại sang biểu diễn văn bản theo quy tắc của Java.

Khi các thành phần của phép nối thỏa điều kiện *constant expression*, nội dung kết quả được tính trước, không cần thực hiện một phép nối động tại thời điểm chạy.

**Phân biệt hai thời điểm:** *Tính nội dung chuỗi lúc biên dịch* không có nghĩa trình biên dịch đã tạo một đối tượng `String` Java nằm trong heap của tiến trình tương lai. Trình biên dịch biểu diễn hằng trong dữ liệu của class file; khi class được sử dụng, JVM giải quyết literal/hằng chuỗi theo cơ chế runtime và pool.

## 3. Khi nào một biến được coi là hằng tại thời điểm biên dịch?

Đặt từ khóa `final` lên biến **chưa đủ** để mọi cách sử dụng biến trở thành constant expression.

Java dùng thuật ngữ **constant variable** cho biến:

1. Có kiểu nguyên thủy (*primitive*) hoặc `String`.
2. Được khai báo `final`.
3. Được khởi tạo **bằng một constant expression** ngay trong phần khai báo.

Ví dụ về các biến hằng hợp lệ (đặt trong phương thức):

```java
final String PREFIX = "Ja";
final String WORD = PREFIX + "va";
final int MAJOR = 17;

String a = WORD;              // "Java"
String b = "Java " + MAJOR;    // "Java 17"
```

Vì `PREFIX`, `WORD` và `MAJOR` thỏa ba điều kiện, trình biên dịch có thể thay các tham chiếu của chúng bằng giá trị hằng khi xác định biểu thức.

Các trường `static final` cũng có thể là constant variable:

```java
class Constants {
    static final String PREFIX = "Ja";
    static final String WORD = PREFIX + "va";
}
```

Nhưng hãy xem những ví dụ **không** phải constant variable:

```java
String prefix = "Ja";                  // Không final
final String fromMethod = getPrefix(); // Gọi phương thức lúc chạy
final String boxed = new String("Ja"); // Khởi tạo bằng new
```

Trong đó `getPrefix()` giả sử là phương thức được định nghĩa ở nơi khác, trả về `String`; ba dòng này chỉ minh họa cú pháp trong ngữ cảnh có khai báo phương thức phù hợp.

Cả khi `getPrefix()` luôn trả về `"Ja"`, hoặc `new String("Ja")` luôn chứa cùng ký tự, các biểu thức ấy vẫn **không** trở thành constant expression chỉ vì ta dự đoán được kết quả.

Một biến `final` được **gán trong khối khởi tạo** thay vì có initializer ngay trong khai báo cũng không thỏa định nghĩa constant variable:

```java
class Config {
    static final String PREFIX;
    static {
        PREFIX = "Ja";
    }
}
```

Sau đó `Config.PREFIX + "va"` là phép nối phụ thuộc giá trị của biến tại runtime, không phải constant expression theo quy tắc đã nêu.

### So sánh nhanh

| Biểu thức | Hằng khi biên dịch? | Giải thích |
|---|---|---|
| `"Ja" + "va"` | Có | Hai toán hạng là literal |
| `"Java " + 17` | Có | Literal chuỗi và hằng số nguyên |
| `final String x = "Ja";` rồi `x + "va"` | Có | `x` là constant variable |
| `String x = "Ja";` rồi `x + "va"` | Không | `x` không `final` |
| `final String x = method();` rồi `x + "va"` | Không | Initializer là lời gọi phương thức |
| `final String x = new String("Ja");` rồi `x + "va"` | Không | Initializer không phải constant expression |
| `String.valueOf(17) + "!"` | Không | Có lời gọi phương thức |

Ở bảng này, các dòng chứa khai báo biến và biểu thức nối mô tả những đoạn mã riêng biệt, không phải một chương trình đầy đủ. Đừng đồng nhất “có giá trị luôn giống nhau khi chạy” với “được JLS công nhận là constant expression”.

## 4. Mối liên hệ giữa constant expression, string pool và `intern()`

### String pool hoạt động thế nào?

*String pool* là cơ chế JVM duy trì tham chiếu chuẩn hóa cho các chuỗi có cùng nội dung. String literal và các `String` là **giá trị của constant expression** được intern để các giá trị hằng tương đương tham chiếu đến cùng một đối tượng chuỗi chuẩn hóa.

Vì vậy:

```java
String literal = "Java";
String folded = "Ja" + "va";

System.out.println(literal == folded); // true
```

Nội dung `"Ja" + "va"` được coi là hằng `"Java"`, và hai biểu thức hằng nội dung tương đương dùng chung tham chiếu chuẩn hóa.

### Nối chuỗi lúc chạy là tình huống khác

```java
String prefix = "Ja";
String joined = prefix + "va";

System.out.println("Java".equals(joined)); // true
System.out.println("Java" == joined);       // false
```

`prefix` không phải constant variable. Biểu thức `prefix + "va"` cần đọc giá trị của biến khi chạy; nó là phép nối động, cho một đối tượng kết quả khác với đối tượng interned được literal `"Java"` tham chiếu. Nội dung bằng nhau vẫn không đồng nghĩa tham chiếu bằng nhau.

### `intern()` đóng vai trò gì?

`String.intern()` trả về tham chiếu chuẩn hóa trong pool cho chuỗi có cùng nội dung. Nếu chưa có chuỗi tương ứng trong pool, cơ chế intern sẽ thiết lập tham chiếu chuẩn hóa đó theo hợp đồng API.

```java
String prefix = "Ja";
String joined = prefix + "va";

System.out.println(joined == "Java");          // false
System.out.println(joined.intern() == "Java"); // true
```

Lời gọi `intern()` **không biến phép cộng lúc chạy thành phép cộng lúc biên dịch**. Đây là một hành động lúc chương trình chạy để lấy tham chiếu chuẩn hóa. Nó cũng không thay nội dung của `joined`: `String` bất biến.

Một lưu ý về thuật ngữ: **constant pool trong class file** là cấu trúc dữ liệu lưu nhiều loại hằng và tham chiếu biểu tượng của mã biên dịch; **string pool** là cơ chế chia sẻ đối tượng `String` khi thực thi. Hai khái niệm có liên hệ, nhưng không phải một nơi chứa duy nhất và cũng không nên coi là đồng nghĩa.

## 5. Ví dụ Java 17+ hoàn chỉnh và kết quả kiểm chứng

Tạo tệp **`StringConstantExpressionDemo.java`**:

```java
public class StringConstantExpressionDemo {
    private static final String STATIC_PREFIX = "Ja";

    private static final String LATE_PREFIX;
    static {
        LATE_PREFIX = "Ja";
    }

    private static String getPrefix() {
        return "Ja";
    }

    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        final String localPrefix = "Ja";
        String fromLocalConstant = localPrefix + "va";
        String fromStaticConstant = STATIC_PREFIX + "va";

        String mutablePrefix = "Ja";
        String runtimeConcat = mutablePrefix + "va";

        final String methodPrefix = getPrefix();
        String fromMethod = methodPrefix + "va";
        String fromLateFinal = LATE_PREFIX + "va";

        String explicitNew = new String("Java");

        System.out.println("literal == folded: "
                + (literal == folded));
        System.out.println("literal == local constant: "
                + (literal == fromLocalConstant));
        System.out.println("literal == static constant: "
                + (literal == fromStaticConstant));
        System.out.println("literal == runtime concat: "
                + (literal == runtimeConcat));
        System.out.println("literal == method result: "
                + (literal == fromMethod));
        System.out.println("literal == late final: "
                + (literal == fromLateFinal));
        System.out.println("literal == new String: "
                + (literal == explicitNew));
        System.out.println("literal == interned runtime: "
                + (literal == runtimeConcat.intern()));
        System.out.println("literal.equals(runtime): "
                + literal.equals(runtimeConcat));
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 StringConstantExpressionDemo.java
java StringConstantExpressionDemo
```

**Stdout:**

```text
literal == folded: true
literal == local constant: true
literal == static constant: true
literal == runtime concat: false
literal == method result: false
literal == late final: false
literal == new String: false
literal == interned runtime: true
literal.equals(runtime): true
```

**Đọc kết quả:**

1. `folded`, `fromLocalConstant` và `fromStaticConstant` có nội dung được xác định bởi constant expression. Chúng cùng tham chiếu đến giá trị interned `"Java"` như literal.
2. `runtimeConcat`, `fromMethod` và `fromLateFinal` tham gia phép nối lúc chạy, nên nội dung vẫn là `"Java"` nhưng đối tượng kết quả không phải đối tượng được literal `"Java"` tham chiếu.
3. `new String("Java")` yêu cầu tạo một đối tượng `String` riêng; vì thế tham chiếu khác literal ngay cả khi nội dung giống nhau.
4. `runtimeConcat.intern()` lấy tham chiếu chuẩn hóa của `"Java"` và so sánh bằng `==` với literal sẽ là `true`.
5. `literal.equals(runtimeConcat)` là `true`, xác nhận so sánh nội dung không phụ thuộc hai biến có trỏ đến cùng đối tượng hay không.

Ví dụ kiểm soát rõ nguồn của từng chuỗi để minh họa quy tắc. Trong chương trình thông thường, **không dùng kết quả `==` giữa `String` để suy đoán dữ liệu đã được tính lúc nào**; nếu mục tiêu là so sánh văn bản, dùng `equals`.

## 6. Nhận diện phép ghép hằng qua bytecode

Với đoạn nguồn:

```java
String result = "Ja" + "va";
```

Compiler có thể đưa thẳng nội dung `"Java"` vào class file thay vì mã nối hai toán hạng riêng. Đây là *constant folding*: rút gọn biểu thức hằng trước khi chương trình thực thi.

Có thể quan sát class file được tạo ở mục 5 bằng:

```bash
javap -c -p StringConstantExpressionDemo
```

Kết quả `javap` phụ thuộc compiler và phiên bản JDK, nhưng bạn có thể tìm các lệnh tải hằng chuỗi như `ldc ... // String Java` ở những chỗ dùng constant expression. Với phép nối runtime, bytecode của `javac` trên JDK hiện đại thường sử dụng `invokedynamic` và cơ chế nối chuỗi của JVM; cách sinh bytecode có thể thay đổi qua các bản JDK.

**Không cần dựa vào một opcode cụ thể để hiểu quy tắc**. Điều cốt lõi là: phép nối của constant expression có giá trị xác định trước theo JLS; phép nối phụ thuộc biến không phải constant variable phải sử dụng dữ liệu runtime.

Cũng cần tránh hiểu sai rằng một biểu thức được tối ưu nhờ JIT lúc chạy sẽ tự động trở thành **constant expression của ngôn ngữ Java**. Đây là hai tầng khác nhau: tính hằng theo JLS được xác định từ mã nguồn/biên dịch, còn JIT là tối ưu thực thi.

## 7. Những lỗi hiểu sai thường gặp

### Lỗi 1: “Có chữ `final` là trình biên dịch tính hết”

Không đúng. Hãy so sánh:

```java
final String a = "Ja";             // Constant variable
final String b = "J".concat("a");  // Không phải constant variable
```

`b` là `final`, nhưng lời gọi `concat(...)` không phải constant expression theo định nghĩa JLS. `b + "va"` vẫn không phải phép nối hằng tại thời điểm biên dịch.

### Lỗi 2: “Dùng `==` để so sánh hai chuỗi sẽ nhanh hơn nên an toàn”

`==` so sánh **đồng nhất đối tượng**. Những chuỗi hằng được intern có thể tình cờ làm phép so sánh `==` cho kết quả đúng như nội dung, nhưng chuỗi nhập từ người dùng, đọc file, API hoặc ghép động thường không có bảo đảm ấy.

Dùng:

```java
"Java".equals(candidate)
```

Khi `candidate` có thể là `null`, cách viết này tránh `NullPointerException` ở phía nhận phương thức. Hoặc dùng `java.util.Objects.equals(a, b)` khi cả hai biến đều có thể `null`.

### Lỗi 3: “Nối hai giá trị luôn giống nhau thì chắc chắn là nối hằng”

Ví dụ `getPrefix() + "va"` vẫn là nối runtime, dù phương thức `getPrefix()` luôn trả `"Ja"`. Quy tắc xét **cấu trúc biểu thức** và những thành phần được JLS cho phép, không dựa vào việc con người biết trước kết quả.

### Lỗi 4: “Compiler đã tính chuỗi thì chương trình hoàn toàn không dùng bộ nhớ cho `String`”

Sai. Compiler xác định **nội dung hằng**, còn JVM vẫn có đối tượng `String` được sử dụng ở runtime. Việc intern giúp tái sử dụng tham chiếu của các hằng có cùng nội dung, chứ không xóa khái niệm đối tượng chuỗi.

### Lỗi 5: “Gọi `intern()` sẽ làm toàn bộ việc xử lý chuỗi nhanh hơn”

Không có quy tắc chung như vậy. `intern()` mang thêm hoạt động quản lý tham chiếu chuẩn hóa; chỉ nên sử dụng khi thực sự hiểu yêu cầu chia sẻ/chuẩn hóa tham chiếu và đặc điểm dữ liệu. Cách so sánh nội dung bình thường vẫn là `.equals(...)`; không cần intern mọi chuỗi để so sánh.

## 8. Khi nào kiến thức này hữu ích?

- **Đọc kết quả `==` bất ngờ:** giải thích vì sao `"a" + "b" == "ab"` có thể đúng trong biểu thức hằng, còn nối bằng biến có cùng nội dung thì khác.
- **Hiểu compiler:** nhận diện ranh giới giữa tính hằng tại biên dịch và nối chuỗi tại runtime.
- **Đọc bytecode:** hiểu tại sao source dùng toán tử `+` mà class file chỉ cần tải một hằng chuỗi.
- **Thiết kế hằng dùng chung:** `static final String` được khởi tạo bởi constant expression có thể được nội tuyến giá trị vào mã của lớp sử dụng khi biên dịch. Vì thế nếu thay giá trị hằng công khai trong thư viện, các lớp đã biên dịch trước đó có thể vẫn giữ giá trị cũ cho tới khi được biên dịch lại. Không nên dựa vào field hằng biên dịch để cung cấp cấu hình cần thay đổi mà không biên dịch lại client.
- **Tránh tối ưu hóa sai:** lựa chọn giữa `==`, `.equals(...)` và `intern()` dựa vào **ngữ nghĩa** cần thiết, không chỉ vào việc thấy hai chuỗi có nội dung giống nhau.

## 9. Tự kiểm tra

**Câu 1.** Đoạn sau in gì?

```java
String x = "ab";
String y = "a" + "b";
System.out.println(x == y);
```

**Đáp án:** `true`, vì `"a" + "b"` là constant expression có giá trị interned `"ab"`.

**Câu 2.** Thêm `final` vào biến có thay đổi kết quả không?

```java
String a = "a";
String x = a + "b";
System.out.println(x == "ab");
```

**Đáp án:** Mã như trên in `false`. Nếu thay khai báo bằng `final String a = "a";`, `a` trở thành constant variable; phép nối `a + "b"` là constant expression và kết quả so sánh được in là `true`.

**Câu 3.** Vì sao ví dụ này vẫn nối lúc chạy?

```java
final String a = new String("a");
String x = a + "b";
```

**Đáp án:** `a` không phải constant variable vì initializer dùng `new`, vốn không là constant expression.

**Câu 4.** `String t = dynamic + "ab";` có nên dùng `t.intern() == "someValue"` để kiểm tra nội dung không?

**Đáp án:** Không cần. Khi muốn kiểm tra văn bản, dùng `"someValue".equals(t)`. `intern()` phục vụ chuẩn hóa tham chiếu, không phải công cụ so sánh nội dung thông thường.

**Câu 5.** “Tính khi biên dịch” và “intern lúc chạy” có mâu thuẫn không?

**Đáp án:** Không. Compiler xác định **giá trị hằng của biểu thức**, còn JVM sử dụng cơ chế **chuỗi chuẩn hóa trong runtime** để biểu diễn và chia sẻ đối tượng `String` tương ứng.

## 10. Điểm cần nhớ

Một biểu thức nối chuỗi chỉ được xem là **constant expression** khi các thành phần tuân theo đúng quy tắc ngôn ngữ Java; literal và **constant variable** là những trường hợp thường gặp. Giá trị `String` của constant expression được intern, nên các chuỗi hằng có cùng nội dung dùng chung tham chiếu chuẩn hóa. Phép nối sử dụng biến không hằng hay lời gọi phương thức là nối runtime, dù nội dung cuối cùng trông giống hệt. Hãy dùng kiến thức về string pool để hiểu Java, và dùng `.equals(...)` khi cần kiểm tra nội dung văn bản.

# Phân biệt nối chuỗi hằng và nối giá trị lúc chạy trong Java

Phép toán `+` có thể nối các `String` thành một chuỗi mới, nhưng **không phải mọi biểu thức nối chuỗi đều được tính ở cùng thời điểm**. Java phân biệt:

- **Nối chuỗi bằng biểu thức hằng tại thời điểm biên dịch** (*compile-time constant expression*): trình biên dịch có thể tính trước toàn bộ kết quả. `"Java" + "Core"` được xem như chuỗi literal `"JavaCore"` và kết quả hằng được **intern**.
- **Nối chuỗi lúc chương trình chạy** (*runtime concatenation*): có ít nhất một toán hạng không tạo thành biểu thức hằng theo quy tắc ngôn ngữ. Giá trị chuỗi được ghép khi thực thi, ngay cả khi tại thời điểm đó nó có nội dung giống một literal có sẵn.

Sự khác biệt quan trọng khi học **String Pool, `intern()`, tính chất `final`, so sánh `==` và `equals()`**, cũng như khi đọc bytecode và đánh giá chi phí nối chuỗi.

## 1. Ranh giới giữa nối hằng và nối runtime

**Nối hằng** chỉ xảy ra khi toàn bộ biểu thức thỏa định nghĩa *constant expression* của Java: compiler xác định giá trị trước khi chương trình chạy. **Nối runtime** cần đọc giá trị không phải constant expression lúc thực thi; kết quả có thể cùng nội dung literal nhưng không tự động được intern.

~~~java
String literal = "Java";
String folded = "Ja" + "va";       // Hằng tại biên dịch
final String constant = "Ja";
String foldedFinal = constant + "va";
String variable = "Ja";
String runtime = variable + "va";   // Nối lúc chạy
~~~

`folded == literal` và `foldedFinal == literal` là `true`, còn `runtime == literal` là `false`; `runtime.equals(literal)` vẫn `true`. `final String` chỉ trở thành **constant variable** khi được khai báo kèm initializer là constant expression; `final String s = new String("Ja")` không thỏa. Bài về biểu thức hằng đã đi sâu vào các ngoại lệ, cách compiler nội tuyến hằng và ảnh hưởng đến API.

Trọng tâm tiếp theo là phép nối **khi runtime thực thi**, thứ tự dấu `+`, bytecode và kỹ thuật nối nhiều phần.

## 2. Liên hệ với String Pool và phép so sánh

**String Pool** là cơ chế Java duy trì một phiên bản chuẩn (*canonical representation*) cho các chuỗi đã được intern. Chuỗi literal và chuỗi kết quả của constant expression kiểu `String` được intern theo ngữ nghĩa ngôn ngữ. Hai biểu thức hằng có cùng nội dung vì vậy có thể tham chiếu cùng đối tượng `String`.

Với nối lúc chạy, nội dung có thể giống hệt chuỗi trong pool, nhưng **không vì thế mà phép nối tự động sử dụng tham chiếu trong pool**.

Hãy biên dịch cả class sau bằng Java 17+.

Lưu tệp `ConcatIdentityDemo.java`:

```java
public class ConcatIdentityDemo {
    public static void main(String[] args) {
        String pooled = "JavaCore";

        // Hai cách tạo constant expression
        String folded = "Java" + "Core";
        final String constantPrefix = "Java";
        final String constantSuffix = "Core";
        String foldedFinals = constantPrefix + constantSuffix;

        // Hai cách nối lúc chạy
        String variablePrefix = "Java";
        String runtime = variablePrefix + "Core";

        final String notConstantPrefix = new String("Java");
        String runtimeFinal = notConstantPrefix + "Core";

        System.out.println(folded == pooled);
        System.out.println(foldedFinals == pooled);
        System.out.println(runtime == pooled);
        System.out.println(runtime.equals(pooled));
        System.out.println(runtimeFinal == pooled);
        System.out.println(runtimeFinal.intern() == pooled);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConcatIdentityDemo.java
java ConcatIdentityDemo
```

Kết quả:

```text
true
true
false
true
false
true
```

Giải thích theo từng dòng:

1. `folded == pooled` là `true` vì `"Java" + "Core"` được gộp thành chuỗi hằng `"JavaCore"` và dùng tham chiếu interned.
2. `foldedFinals == pooled` là `true` vì hai biến `final` nhận initializer là literal, nên là constant variables; `constantPrefix + constantSuffix` cũng là biểu thức hằng.
3. `runtime == pooled` là `false`: `variablePrefix` không phải constant variable, phép nối diễn ra lúc chạy và kết quả không tự động là đối tượng interned `"JavaCore"`.
4. `runtime.equals(pooled)` là `true`: hai chuỗi chứa **cùng nội dung**.
5. `runtimeFinal == pooled` là `false`: `new String("Java")` được đánh giá khi chạy; có `final` cũng không làm biểu thức nối thành hằng biên dịch.
6. `runtimeFinal.intern() == pooled` là `true`: `intern()` trả về tham chiếu canonical trong pool ứng với nội dung `"JavaCore"`.

**Không dùng `==` để so sánh nội dung chuỗi.** `==` so tham chiếu đến đối tượng, nên hai `String` cùng chữ có thể cho kết quả khác nhau tùy đường tạo chuỗi. `equals()` so nội dung; với hai giá trị có thể chứa `null`, dùng `Objects.equals(a, b)` nếu muốn kết quả boolean an toàn.

## 3. Phép cộng số và thứ tự đánh giá khi nối chuỗi

`+` có thể là **cộng số học** hoặc **nối chuỗi** tùy kiểu toán hạng. Java đánh giá biểu thức theo thứ tự, và dấu ngoặc có thể làm thay đổi kết quả.

Ví dụ độc lập ở `ConcatOrderDemo.java`:

```java
public class ConcatOrderDemo {
    public static void main(String[] args) {
        System.out.println("A" + 1 + 2);
        System.out.println(1 + 2 + "A");
        System.out.println("A" + (1 + 2));

        final int constantNumber = 2;
        int variableNumber = 2;

        System.out.println(("v" + constantNumber) == "v2");
        System.out.println(("v" + variableNumber) == "v2");
        System.out.println(("v" + variableNumber).equals("v2"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ConcatOrderDemo.java
java ConcatOrderDemo
```

Kết quả:

```text
A12
3A
A3
true
false
true
```

- `"A" + 1 + 2` thực hiện nối từ trái sang phải, thành `"A1"` rồi `"A12"`.
- `1 + 2 + "A"` cộng hai số thành `3` trước, rồi nối `"A"`, được `"3A"`.
- `"A" + (1 + 2)` buộc cộng trong ngoặc, nên được `"A3"`.
- `constantNumber` là constant variable (kiểu `int`, `final`, khởi tạo bằng literal), nên `"v" + constantNumber` là constant expression và đã được intern.
- `variableNumber` không phải constant variable, nên `"v" + variableNumber` được thực hiện lúc chạy; so nội dung vẫn bằng `true` với `equals()`.

Một phép tính có thể tạo ra kết quả đúng về nội dung nhưng diễn ra lúc chạy. **“Biểu thức tạo chuỗi cố định ở lần chạy này”** không đồng nghĩa với **“constant expression theo JLS”**.

## 4. Nhìn từ lúc biên dịch và bytecode

Ở cấp ngôn ngữ Java, điểm cần phân biệt là **khi nào kết quả là constant expression**; cách compiler/JVM thực hiện phép nối lúc chạy là chi tiết triển khai.

Với `javac` hiện đại trên Java 17+, lệnh:

```bash
javap -c -p ConcatIdentityDemo
```

cho phép xem bytecode của class đã biên dịch. Những dấu hiệu thường gặp:

- Với `"Java" + "Core"`, có thể thấy mã nạp literal đã gộp `"JavaCore"`, chẳng hạn instruction `ldc`; không cần một phép nối runtime để hình thành kết quả này.
- Với `variablePrefix + "Core"`, `javac` hiện đại thường tạo `invokedynamic`, bootstrap qua `java.lang.invoke.StringConcatFactory`. Thông tin nối chuỗi/đối số được dùng khi chương trình chạy.
- Các trình biên dịch hoặc phiên bản Java cũ có thể sinh `StringBuilder.append(...)` để nối lúc chạy. Java 9+ đã đưa ra chiến lược dựa trên `invokedynamic` qua JEP 280; vì vậy **không nên khẳng định mọi phép nối runtime đều được biên dịch thành `new StringBuilder()` trong bytecode**.
- JIT/JVM có thể tối ưu phân bổ và ghép chuỗi trong lúc chạy mà không làm thay đổi ngữ nghĩa chương trình. Không suy ra số lần cấp phát thực tế chỉ từ một đoạn mã nguồn hoặc một phép đo `==`.

Mô hình tư duy:

```text
"Java" + "Core"
    -> toàn constant expression
    -> compiler tính "JavaCore"
    -> tham chiếu tới kết quả hằng được intern

variablePrefix + "Core"
    -> có toán hạng không phải compile-time constant
    -> phép nối runtime
    -> tạo nội dung mới theo giá trị hiện tại
    -> KHÔNG mặc nhiên nhận tham chiếu String Pool
```

Hai đường đi có thể cho **chuỗi ký tự giống nhau**, nhưng cách xác định thời điểm nối và quan hệ tham chiếu với pool là khác nhau.

## 5. Tương tác với toán tử `+=`, vòng lặp và StringBuilder

`+=` trên `String` có ý nghĩa tương đương về mặt nối chuỗi với việc lấy giá trị hiện tại rồi nối thêm phần mới, sau đó gán lại biến.

```java
String value = "a";
value += "b"; // giá trị hiện tại + "b", được đánh giá lúc chạy
```

`value` là biến thông thường, không phải constant variable. Kể cả sau câu lệnh, `value` có nội dung `"ab"`, **không nên dựa trên tham chiếu của nó** khi so với literal `"ab"`.

Với các đoạn nối cố định và ngắn, toán tử `+` đọc dễ và `javac`/JVM có cơ chế tối ưu. Nhưng khi nối lặp lại nhiều phần bằng một biến tích lũy, nên cân nhắc `StringBuilder` để tránh tạo các chuỗi trung gian lặp đi lặp lại:

```java
import java.util.List;

public class JoinPartsDemo {
    public static void main(String[] args) {
        List<String> parts = List.of("Java", " ", "Core");

        StringBuilder builder = new StringBuilder();
        for (String part : parts) {
            builder.append(part);
        }

        String result = builder.toString();
        System.out.println(result);
        System.out.println(result.equals("Java Core"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 JoinPartsDemo.java
java JoinPartsDemo
```

Kết quả:

```text
Java Core
true
```

`StringBuilder` gom các phần có thể thay đổi vào vùng đệm, phù hợp với vòng lặp nhiều lần; `toString()` trả về `String` kết quả. Với các trường hợp kết hợp chuỗi bằng dấu phân tách, `String.join(...)` hoặc `Collectors.joining(...)` có thể diễn đạt ý định rõ hơn. Không dùng benchmark đơn lẻ hoặc suy đoán từ `+` để kết luận chắc chắn mức hiệu năng; cần đo với khối lượng thực tế khi tối ưu là yêu cầu.

## 6. Quy trình kiểm tra trong bài tập và thực tế

Khi bắt gặp một phép nối chuỗi, hãy tự hỏi theo thứ tự:

1. **Tất cả toán hạng có tham gia constant expression không?** Phân biệt literal, phép toán hằng được phép và constant variable với dữ liệu từ biến/phương thức.
2. **Kết quả có được tính lúc biên dịch hay phải chờ chạy?** Nếu toàn bộ là constant expression kiểu `String` thì được gộp và intern theo quy tắc Java; nếu không thì là nối runtime.
3. **Đang kiểm tra nội dung hay tham chiếu?** Dùng `equals()` cho nội dung; chỉ dùng `==` nếu mục tiêu thực sự là danh tính đối tượng hoặc tìm hiểu intern.
4. **Đang ghép một biểu thức ngắn hay một vòng lặp dài?** Viết `+` cho mã đơn giản, `StringBuilder`/công cụ join khi có nhiều phần hoặc tích lũy liên tục.
5. **Cần khẳng định chiến lược compiler/JVM không?** Xem bytecode bằng `javap` và kiểm thử trên JDK mục tiêu; đừng biến dấu hiệu của một phiên bản thành quy tắc áp dụng cho mọi bản Java.

### Tự kiểm tra

| Biểu thức | Constant expression? | Lý do |
| --- | --- | --- |
| `"a" + "b"` | Có | Chỉ gồm literal |
| `"n=" + (2 * 3)` | Có | Phép toán số học là hằng |
| `final String a = "a"; a + "b"` | Có | `a` là constant variable |
| `String a = "a"; a + "b"` | Không | `a` không có `final` |
| `final String a = new String("a"); a + "b"` | Không | Initializer của `a` được tính lúc chạy |
| `"a" + args.length` | Không | `args.length` chỉ biết lúc chạy |
| `String.valueOf(1) + "a"` | Không | Có lời gọi phương thức |
| `"v" + 1` | Có | Literal `String` + literal nguyên thủy |

Các dòng có khai báo biến trong bảng là **đoạn mã minh họa đặt trong cùng scope**; đây không phải các biểu thức Java độc lập có thể copy nguyên bảng vào một file `.java`.

**Ghi nhớ:** Nối hằng là trường hợp compiler xác định toàn bộ nội dung từ *constant expression* và kết quả được intern. Nối lúc chạy sử dụng giá trị thật khi thực thi, không mặc nhiên chia sẻ đối tượng trong String Pool. Việc so sánh hai `String` nên dựa vào **`equals()`**, không dựa vào sự tình cờ của `==`.
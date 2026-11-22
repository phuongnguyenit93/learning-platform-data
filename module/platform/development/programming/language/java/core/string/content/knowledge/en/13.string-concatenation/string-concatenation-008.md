# Chi tiết biên dịch phép nối chuỗi có thể thay đổi theo JDK

## 1. Ý tưởng cốt lõi: cùng phép `+`, cách triển khai có thể khác

Trong Java, toán tử `+` được dùng để **nối chuỗi** khi ít nhất một toán hạng có kiểu `String`. Ví dụ:

```java
String name = "Lan";
int score = 9;
String message = "Name: " + name + ", score: " + score;
```

Kết quả `message` là `"Name: Lan, score: 9"`. Ý nghĩa của phép nối này do **ngôn ngữ Java** quy định; ứng dụng phải quan sát được nội dung đúng bất kể trình biên dịch hoặc JVM dùng chiến lược nội bộ nào.

Tuy nhiên, mã nguồn không chỉ rõ JVM phải ghép ký tự bằng lớp nào, tạo các buffer trung gian nào hoặc dùng lệnh bytecode nào. Các JDK và trình biên dịch có thể sinh bytecode khác nhau, và JVM có thể chọn cách thực thi/tối ưu khác nhau, miễn giữ đúng hành vi của Java. Vì vậy, câu nói **“`+` luôn được compiler biến thành `new StringBuilder().append(...).toString()`”** không đúng cho mọi phiên bản.

Phân biệt ba lớp:

1. **Mã nguồn Java:** phép `+`, thứ tự biểu thức, cách chuyển giá trị sang văn bản.
2. **Bytecode của file `.class`:** ví dụ chuỗi lệnh với `StringBuilder` hoặc lời gọi `invokedynamic`.
3. **Cách chạy thực tế trong JVM/JIT:** có thể tiếp tục tối ưu cấp phát, inlining hoặc kỹ thuật khác mà bytecode không mô tả trực tiếp.

Không nên lấy bytecode của một JDK làm “định nghĩa” của toán tử nối chuỗi trong ngôn ngữ.

## 2. Những quy tắc ngôn ngữ phải giữ nguyên

**Hợp đồng cố định:** các phép `+` cùng mức ưu tiên kết hợp trái; khi có toán hạng kiểu `String`, Java thực hiện string conversion (bao gồm tham chiếu `null` thành chữ `"null"`). Compiler và JVM phải giữ nguyên thứ tự đánh giá cùng những tác dụng phụ/ngoại lệ có thể quan sát được.

Với phép nối **không phải biểu thức hằng**, kết quả là một `String` theo ngữ nghĩa runtime mà chuỗi đầu vào không bị sửa; trình biên dịch và JIT được quyền tối ưu các đối tượng trung gian khi không đổi hành vi. Ví dụ:

```java
String original = "Java";
String alias = original;
original = original + " 17";
System.out.println(alias); // Java
```

Đây là nền tảng để so sánh bytecode Java 8 với cơ chế `invokedynamic` Java 9+, không cần dạy lại toàn bộ quy tắc cộng số/chuỗi.

## 3. Nối hằng ở thời điểm biên dịch: constant folding

Trước khi bàn về khác biệt Java 8 và Java 9+, cần nhận ra có những phép nối **không cần ghép tại runtime**.

```java
String direct = "Hello World";
String folded = "Hello" + " " + "World";

System.out.println(direct.equals(folded)); // true
System.out.println(direct == folded);      // true
```

`"Hello" + " " + "World"` là **biểu thức hằng** theo Java Language Specification. Compiler có thể biểu diễn kết quả trong constant pool của `.class`; các giá trị chuỗi hằng được intern nên tham chiếu của `direct` và `folded` bằng nhau.

Một biến `final` có thể tham gia biểu thức hằng nếu bản thân biến là **constant variable** (kiểu primitive hoặc `String`, `final`, khởi tạo bằng biểu thức hằng):

```java
final String prefix = "Hello";
String folded = prefix + " World";

System.out.println(folded == "Hello World"); // true
```

Nhưng `final` đơn thuần không đủ:

```java
final String prefix = new String("Hello");
String result = prefix + " World";

System.out.println(result.equals("Hello World")); // true
System.out.println(result == "Hello World");       // false
```

`new String(...)` không phải biểu thức hằng. Phép nối ở đây thực hiện lúc chạy và không tự intern thành literal. **Không suy ra mọi lệnh có dấu `+` đều sinh `invokedynamic` hoặc `StringBuilder`:** compiler có thể gộp biểu thức hằng từ trước.

## 4. Java 8: ví dụ điển hình dùng `StringBuilder`

Ở `javac` của JDK 8, phép nối chuỗi **không phải hằng** thường được hạ xuống (*lowering*) chuỗi lời gọi `StringBuilder`: tạo builder, `append` các phần rồi `toString`.

Mã nguồn minh họa:

```java
static String label(String name, int age) {
    return "Name=" + name + ", age=" + age;
}
```

Một dạng bytecode rút gọn thường thấy ở Java 8 (minh họa cấu trúc, không phải bản chép nguyên văn `javap`):

```text
new           java/lang/StringBuilder
dup
invokespecial java/lang/StringBuilder.<init>
ldc           "Name="
invokevirtual java/lang/StringBuilder.append
aload         ...
invokevirtual java/lang/StringBuilder.append
ldc           ", age="
invokevirtual java/lang/StringBuilder.append
iload         ...
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.toString
areturn
```

Mô hình này **hữu ích để hiểu lịch sử**, nhưng không phải cam kết mỗi dấu `+` luôn là một `append()`, mỗi lần chạy luôn có đúng một builder hay JIT không được khử cấp phát. Trình biên dịch và runtime có các cơ hội tối ưu riêng; chuỗi nhiều toán hạng trong một biểu thức có thể được compiler xử lý tập hợp.

Từ đó phát sinh lối giải thích quen thuộc: “nối `String` bằng `+` dùng `StringBuilder` ngầm”. Với Java hiện đại, cần cập nhật mô hình này.

## 5. Từ Java 9: `invokedynamic` và `StringConcatFactory`

Java 9 đưa vào **JEP 280 — Indify String Concatenation**, chuyển cơ chế mặc định của `javac` hiện đại cho nhiều phép nối không phải hằng sang việc phát sinh bytecode `invokedynamic`. Bytecode mô tả **điểm nối** (*call site*) và có thể liên kết qua bootstrap method của `java.lang.invoke.StringConcatFactory`, thay vì hard-code chuỗi lệnh `new StringBuilder` vào mã người dùng.

Với ví dụ `"Name=" + name + ", age=" + age`, bytecode do `javac` hiện đại sinh thường có một `invokedynamic` dành cho thao tác nối:

```text
aload         ...
iload         ...
invokedynamic ... // makeConcatWithConstants hoặc chiến lược tương đương
areturn
```

Đây là sơ đồ **minh họa**; thứ tự chỉ dẫn, method descriptor, recipe và tên bootstrap trong bản `javap -v` cụ thể tùy compiler, tùy mục tiêu biên dịch và các tối ưu của JDK đang dùng.

### Bootstrap method và cách thực thi

`StringConcatFactory` là API hỗ trợ liên kết `invokedynamic` cho thao tác nối chuỗi. Hai bootstrap method đáng biết là:

- `StringConcatFactory.makeConcat(...)`: nhận các đối số động để nối.
- `StringConcatFactory.makeConcatWithConstants(...)`: có thể mang theo **recipe** và các thành phần hằng, giúp mô tả cách kết hợp đối số động với văn bản hằng.

Khi call site được liên kết, một `CallSite` cung cấp `MethodHandle` thích hợp để thực hiện phép nối khi được gọi. JVM có thể chọn, tối ưu hoặc thay đổi triển khai bên dưới mà không đòi hỏi tất cả bytecode gọi phép nối phải đổi theo cùng một cách.

Ví dụ, recipe của `makeConcatWithConstants` có thể dùng ký hiệu đặc biệt cho đối số động và hằng. **Recipe là chi tiết liên kết**, không phải cú pháp phải viết tay khi sử dụng dấu `+` bình thường.

Điều quan trọng: **`invokedynamic` là cơ chế bytecode**, còn `StringConcatFactory` là một cơ chế trong thư viện nền hỗ trợ runtime. Việc mã Java dùng `+` không có nghĩa người lập trình bắt buộc tự gọi factory.

### Mục tiêu của JEP 280

Cơ chế mới cho phép cải tiến chiến lược nối chuỗi ở thư viện/runtime mà không cần mã ứng dụng liên tục đổi mã nguồn chỉ để nhận các cải tiến đó. Tuy nhiên, việc có `invokedynamic` **không bảo đảm một benchmark cụ thể sẽ nhanh hơn**, cũng không có nghĩa phép nối không tạo đối tượng nào.

Tham khảo chính thức: [JEP 280](https://openjdk.org/jeps/280) và [Java SE 21 — StringConcatFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html).

## 6. Một mã nguồn, nhiều bytecode: cách tự kiểm chứng

Lưu tệp `ConcatVersionDemo.java` dưới đây. Chương trình tương thích Java 8+, và tất nhiên có thể chạy bằng JDK 17+.

```java
public class ConcatVersionDemo {
    static String label(String name, int age) {
        return "Name=" + name + ", age=" + age;
    }

    public static void main(String[] args) {
        String name = "Lan";
        int age = 20;

        System.out.println(label(name, age));

        String literal = "Java";
        String folded = "Ja" + "va";
        final String constantPrefix = "Ja";
        String foldedWithFinal = constantPrefix + "va";

        String dynamicPrefix = "Ja";
        String runtime = dynamicPrefix + "va";

        System.out.println("folded == literal: " + (folded == literal));
        System.out.println("final folded == literal: "
                + (foldedWithFinal == literal));
        System.out.println("runtime equals literal: "
                + runtime.equals(literal));
        System.out.println("runtime == literal: " + (runtime == literal));

        System.out.println(1 + 2 + " apples");
        System.out.println("apples: " + 1 + 2);
        System.out.println("name=" + (String) null);
    }
}
```

Dùng đúng tên tệp `ConcatVersionDemo.java`. Chạy bằng JDK 17+:

```bash
javac ConcatVersionDemo.java
java ConcatVersionDemo
```

Kết quả chuẩn:

```text
Name=Lan, age=20
folded == literal: true
final folded == literal: true
runtime equals literal: true
runtime == literal: false
3 apples
apples: 12
name=null
```

Đây là kết quả theo ngữ nghĩa Java, độc lập với việc phiên bản JDK đang sinh `StringBuilder` hay `invokedynamic` cho phép nối runtime.

### Xem bytecode bằng `javap`

`javap` là công cụ đi kèm JDK để xem cấu trúc và bytecode của file `.class`:

```bash
javac -version
java -version
javac --release 8 ConcatVersionDemo.java
javap -c -p ConcatVersionDemo
javap -v ConcatVersionDemo
```

Nhìn vào bytecode của phương thức `label` và `main`. Với `javac` hiện đại khi xuất `--release 8`, ta thường thấy chuỗi lệnh `new StringBuilder`, `append` và `toString` cho nối chuỗi runtime. Tùy ví dụ, **biểu thức hằng** đã được compiler gộp và chỉ còn tải chuỗi hằng.

Bây giờ biên dịch lại cùng tệp nguồn sang mục tiêu Java 17:

```bash
javac --release 17 ConcatVersionDemo.java
javap -c -p ConcatVersionDemo
javap -v ConcatVersionDemo
```

Với `javac` JDK hiện đại, các phép nối runtime thường xuất hiện dạng `invokedynamic`, và ở phần `BootstrapMethods` của `javap -v` có thể thấy `StringConcatFactory.makeConcatWithConstants`. Hãy **kiểm tra output thực tế** thay vì tin vào một đoạn bytecode cố định trong tài liệu.

**Điều kiện thực hiện:** Các lệnh `--release 8` và `--release 17` ở trên dành cho JDK hỗ trợ cả hai mục tiêu, chẳng hạn JDK 17 hoặc JDK 21/24. Trên JDK 8 không có tùy chọn `--release`; khi đó cần công cụ biên dịch và cờ tương ứng với JDK 8. Nếu dự án dùng Maven/Gradle hoặc compiler khác, cần xác nhận cài đặt toolchain/target thực sự trước khi so sánh.

**Chú ý:** Hai lần `javac` liên tiếp sẽ ghi đè file `ConcatVersionDemo.class` trong cùng thư mục. Vì vậy, **quan sát `javap` ngay sau từng lần biên dịch**, hoặc biên dịch ra hai thư mục riêng khi cần so sánh song song. Lệnh `java ConcatVersionDemo` chạy class file hiện có tại thời điểm gọi, không tự chạy lại compiler.

### Phân biệt ba phiên bản

| Thuộc tính | Bạn đang kiểm tra điều gì? |
| --- | --- |
| `javac -version` | Phiên bản **trình biên dịch** đang chạy |
| `javac --release N` | Mục tiêu API, cú pháp và class-file mà compiler được yêu cầu xuất |
| `java -version` | Phiên bản **runtime/JVM** dùng để chạy |
| `javap -c -v ...` | Bytecode **thực sự được tạo** trong file `.class` |
| Hiệu năng khi chạy | Kết quả tương tác giữa chương trình, dữ liệu, JVM/JIT, GC và hệ thống |

Ví dụ, sử dụng `javac` từ JDK 24 để biên dịch `--release 8` **không biến compiler thành `javac` của JDK 8**. Nó yêu cầu xuất mã tương thích mức Java 8; chi tiết triển khai nội bộ vẫn tùy compiler đang dùng. Đồng thời, một class file nhắm Java 17 thông thường không chạy được trên runtime Java 8 vì class-file version và thư viện nền tương ứng.

## 7. Điều gì thay đổi và điều gì không?

| Khía cạnh | Bảo đảm / nhận định phù hợp |
| --- | --- |
| Nội dung kết quả `"A" + "B"` | Bằng `"AB"` |
| Thứ tự và kết quả các phép toán như `1 + 2 + "x"` | Theo ngữ nghĩa Java, không phụ thuộc công thức nối nội bộ |
| `String` đầu vào có bị sửa không? | Không; `String` bất biến |
| Biểu thức hằng có thể gộp khi biên dịch? | Có, theo quy tắc constant expression |
| Mọi phép nối phải dùng `StringBuilder`? | Không |
| Mọi phép nối phải dùng `invokedynamic`? | Không |
| `javac` Java 8 và Java 17 có thể sinh bytecode khác? | Có |
| Hai JVM chạy cùng bytecode có thể tối ưu khác? | Có, nếu vẫn giữ đúng ngữ nghĩa |
| `javap` có phản ánh mọi bước tối ưu JIT lúc chạy? | Không; nó hiển thị bytecode trong class file |
| Có thể đoán chính xác số object chỉ từ dấu `+`? | Không đáng tin nếu bỏ qua folding, các đối tượng trung gian và tối ưu runtime |

**Không nhầm constant pool của class file với String pool.** Constant pool trong `.class` là bảng mục dùng để biểu diễn hằng, tên, tham chiếu và các dữ liệu liên kết cần thiết cho bytecode. String pool là cơ chế quản lý các chuỗi đã intern ở runtime. Chúng có liên hệ với literal, nhưng không phải hai tên cho cùng một cấu trúc.

## 8. Khi nào nên dùng `+`, `StringBuilder`, hoặc API khác?

Sự khác nhau về bytecode **không** thay đổi hướng dẫn chọn API: `+` đủ rõ cho một biểu thức ngắn; `StringBuilder` thường phù hợp khi tích lũy qua nhiều vòng; `String.join`/ `StringJoiner` thuận tiện cho dấu phân cách. Xem bài **Nối trong một biểu thức so với tích lũy qua vòng lặp** để phân tích đầy đủ các tình huống đó.

## 9. Đo hiệu năng đúng và tránh phụ thuộc vào chi tiết JDK

Bytecode `invokedynamic` không trực tiếp chứng minh phép nối nhanh hơn hoặc không cấp phát: JIT, warm-up, escape analysis, GC, độ dài chuỗi và dữ liệu đầu vào đều ảnh hưởng kết quả. Nếu cần so sánh JDK/compiler, hãy kiểm tra `javac -version`, `java -version`, `--release` và `javap` trước, rồi dùng benchmark đại diện như JMH.

Không xây logic ứng dụng dựa vào hình dạng recipe, số object suy đoán từ `javap` hoặc cờ compiler nội bộ.

## 10. Các lỗi thường gặp

1. **Khẳng định compiler luôn chuyển `+` thành `StringBuilder`.** Điều này mô tả phổ biến `javac` Java 8 nhưng không bao quát Java 9+ và các biến thể compiler.
2. **Khẳng định mọi dấu `+` ở Java 17 đều dùng `invokedynamic`.** Biểu thức hằng có thể đã được gộp khi biên dịch; các phần còn lại phụ thuộc compiler và target.
3. **Lấy phiên bản `java -version` để suy ra phiên bản compiler.** Runtime và công cụ biên dịch có thể khác nhau; kiểm tra cả `javac -version` và `--release`.
4. **Cho rằng `--release 8` là chạy một compiler JDK 8 thật.** Không: đó là yêu cầu mục tiêu phát sinh mã/ API tương thích, khi compiler hỗ trợ.
5. **Đọc output `javap` như danh sách object thực sự được cấp phát.** JIT có thể tối ưu khi thực thi; `javap` chỉ nhìn bytecode đã ghi trong class file.
6. **Cho rằng `invokedynamic` nghĩa là hành vi nối chuỗi khác `+` cũ.** Bất kể cơ chế, chương trình hợp lệ phải tuân theo ngữ nghĩa Java.
7. **Tự viết `a + b + c` rồi nghĩ tất cả đều là cộng số.** Khi có `String`, các toán hạng tiếp theo nối thành văn bản; dùng ngoặc để làm rõ ý định.
8. **Viết `StringBuilder` trong mỗi vòng lặp nhưng vẫn tạo builder mới mỗi lượt.** Khi cần tích lũy, tạo và tái sử dụng builder ở phạm vi thích hợp.
9. **Benchmark `+` và builder không khống chế JDK, dữ liệu và warm-up.** Kết luận hiệu năng có thể sai; dùng công cụ đo phù hợp.
10. **Trộn lẫn class-file constant pool với runtime String pool.** Hai khái niệm phục vụ mục đích khác nhau.

## 11. Tự kiểm tra

Cho mã sau:

```java
final String a = "he";
String b = "he";
String x = a + "llo";
String y = b + "llo";

System.out.println(x == "hello");
System.out.println(y.equals("hello"));
System.out.println(y == "hello");
```

Kết quả theo ngữ nghĩa Java:

```text
true
true
false
```

`a` là constant variable nên `a + "llo"` là biểu thức hằng được intern. `b` không phải constant variable nên `b + "llo"` được nối lúc chạy và có nội dung bằng `"hello"` nhưng không cùng đối tượng literal. Thay JDK hoặc cách biên dịch có thể làm **bytecode nối `y` khác đi**, nhưng không được làm kết quả ba phép kiểm tra thay đổi trái với đặc tả.

**Ghi nhớ:** Ngữ nghĩa của `String` và toán tử `+` thuộc **ngôn ngữ Java**; cách compiler hạ phép nối thành `StringBuilder`, `invokedynamic` và cách runtime tối ưu chúng thuộc **triển khai JDK/JVM**. Hãy viết mã dựa vào ngữ nghĩa, quan sát thực tế bằng `javap` khi cần tìm hiểu, và đo hiệu năng trên môi trường mục tiêu.

### Tài liệu tham khảo

- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280)
- [Java SE 21 — StringConcatFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [Java Language Specification — `15.18.1`, String Concatenation Operator `+`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18.1)

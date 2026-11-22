# Toán tử += trong Java String: tạo kết quả rồi gán lại tham chiếu

## 1. Hiểu đúng mục tiêu

Khi viết:

~~~java
String name = "Java";
name += " Core";
~~~

giá trị của biến `name` trở thành `"Java Core"`. Nhưng **đối tượng chuỗi `"Java"` không bị sửa**. Java tính phép nối chuỗi, cho ra kết quả, rồi **gán kết quả trở lại biến tham chiếu `name`**.

Đây là điểm khác biệt quan trọng giữa việc *thay đổi giá trị của biến* và việc *thay đổi nội dung đối tượng*. `String` là **immutable**: nội dung của một đối tượng `String` không thay đổi sau khi tạo. Cú pháp `+=` chỉ làm phép nối và phép gán ngắn gọn hơn; nó **không phá vỡ tính bất biến**.

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của `s += part` trong trường hợp `s` là `String`.
2. Phân biệt `s += x`, `s = s + x`, `s.concat(x)` và `StringBuilder.append(x)`.
3. Dự đoán giá trị của các biến khác đang giữ **tham chiếu cũ** sau khi `s += ...`.
4. Hiểu cách `+=` chuyển các toán hạng thành văn bản, kể cả số, đối tượng và `null`.
5. Phân biệt thứ tự tính toán, dấu ngoặc và kết quả khi nối số.
6. Nhận biết lỗi dùng `+=` với biến `final` và cân nhắc `StringBuilder` khi nối nhiều lần.
7. Đọc và kiểm chứng kết quả bằng các chương trình Java 17+ chạy độc lập.

Kiến thức nền cần có: biến, tham chiếu đối tượng, dấu `=`, `+`, `String`, kiểu nguyên thủy và `final`.

## 2. += vừa nối chuỗi vừa gán kết quả

`+=` là **toán tử gán kết hợp** (*compound assignment operator*). Với biến `String` đơn giản, có thể hiểu:

~~~java
String s = "Hello";

s += " World";    // Viết gọn
// Tương đương về kết quả với:
// s = s + " World";
~~~

Kết quả cuối của `s` là `"Hello World"`. Thao tác có thể hình dung theo ba bước:

1. Đọc giá trị hiện tại mà biến `s` tham chiếu, ở đây là `"Hello"`.
2. Tính phép `s + " World"`, tạo giá trị nội dung `"Hello World"`.
3. Gán kết quả phép nối trở lại biến `s`.

Chú ý câu **“tương đương về kết quả”**: đối với biểu thức ở vế trái phức tạp có tác dụng phụ như `array[index++]`, Java đánh giá vế trái của phép gán kết hợp **một lần**. Vì vậy không thể máy móc thay mọi `left += value` bằng văn bản `left = left + value` nếu việc tính `left` có tác dụng phụ.

Sơ đồ tham chiếu đơn giản:

~~~text
Ban đầu:
s ─────────► String "Hello"

Sau s += " World":
s ─────────► String "Hello World"

Đối tượng mang nội dung "Hello" không bị sửa.
Nếu còn biến khác trỏ đến đối tượng cũ, biến ấy vẫn đọc "Hello".
~~~

Trong Java, `String` bất biến, dù trình biên dịch và JVM có thể tối ưu việc hình thành giá trị kết quả theo nhiều cách. Không nên suy đoán **mỗi phép nối luôn cấp phát chính xác bao nhiêu đối tượng trung gian**.

## 3. Ví dụ then chốt: biến khác không bị thay đổi

~~~java
String first = "Java";
String second = first;

first += " Core";

System.out.println(first);  // Java Core
System.out.println(second); // Java
~~~

Trước `+=`, cả `first` và `second` tham chiếu tới cùng giá trị `"Java"`. Sau phép gán, **chỉ `first` được gán lại**; `second` vẫn giữ tham chiếu ban đầu, nên in `"Java"`.

~~~text
Trước:
first  ───┐
          ├──► "Java"
second ───┘

Sau:
first  ──────► "Java Core"
second ──────► "Java"
~~~

Một cách kiểm tra ý nghĩa (ưu tiên kiểm tra bằng `equals()`):

~~~java
String original = "A";
String copyOfReference = original;
original += "B";

System.out.println("A".equals(copyOfReference)); // true
System.out.println("AB".equals(original));       // true
~~~

Đây chính là ý nghĩa **“tạo kết quả rồi gán lại tham chiếu”**. Phép gán không truyền ngược thay đổi sang các biến tham chiếu khác.

### Phân biệt với StringBuilder

~~~java
StringBuilder builder = new StringBuilder("A");
StringBuilder alias = builder;

builder.append("B");

System.out.println(builder); // AB
System.out.println(alias);   // AB
~~~

Hai biến `builder` và `alias` tham chiếu **cùng một đối tượng `StringBuilder` mutable**, nên thay đổi do `append()` đều quan sát được qua cả hai biến. `StringBuilder.append()` thay đổi builder; `String += ...` thay giá trị mà biến `String` giữ.

## 4. Cơ chế của String + và chuyển đổi sang văn bản

`s += value` dùng quy tắc nối `String`: số, `boolean`, `char` và đối tượng được chuyển thành văn bản. Giá trị `null` có thể trở thành chữ `"null"`:

```java
String label = "count=";
label += 42;
System.out.println(label); // count=42

String missing = null;
missing += "!";
System.out.println(missing); // null!
```

`+=` không định dạng số theo locale hoặc tự giải quyết dữ liệu thiếu. Đây là **chuyển đổi trong phép nối**; xem bài về `+` và `String.valueOf` để học bảng chuyển kiểu đầy đủ.

## 5. Số học, thứ tự toán tử và dấu ngoặc

`+` vừa có nghĩa **cộng số** vừa có nghĩa **nối chuỗi**, nên thứ tự tính toán có thể cho kết quả khác nhau.

~~~java
String first = "N";
first += 1 + 2;
System.out.println(first); // N3

String second = "N";
second += 1;
second += 2;
System.out.println(second); // N12
~~~

Ở ví dụ đầu, biểu thức ở bên phải `1 + 2` thực hiện cộng số trước, ra `3`, rồi mới được nối với `"N"`. Ví dụ thứ hai nối lần lượt từng số.

Tương tự:

~~~java
String a = "Result=";
a += (10 + 5);
System.out.println(a); // Result=15

String b = "Result=";
b = b + 10 + 5;
System.out.println(b); // Result=105
~~~

Biểu thức `b + 10 + 5` liên kết từ trái sang phải: bắt đầu bằng `String`, nên phép `+` tiếp theo thực hiện nối văn bản.

**Cách đọc an toàn:** Khi muốn cộng trước rồi chuyển sang văn bản, đặt phép số học trong dấu ngoặc. Khi muốn nối từng giá trị, thể hiện rõ dấu phân cách hoặc sử dụng formatter.

### += không nhất thiết giống gọi concat()

~~~java
String a = "ID";
a += 17;                // Hợp lệ: ID17

String b = "ID";
// b = b.concat(17);     // Không biên dịch: concat nhận String
b = b.concat("17");      // Hợp lệ: ID17
~~~

`concat(String)` yêu cầu đối số kiểu `String`; toán tử `+` với `String` có quy tắc chuyển đổi toán hạng linh hoạt hơn.

## 6. Sự khác biệt giữa += và các toán tử gán thường gặp

| Biểu thức | Cơ chế | Đối tượng String nguồn bị sửa? |
| --- | --- | --- |
| `s = "Hello"` | Gán tham chiếu tới chuỗi | Không |
| `s = s + "!"` | Tạo giá trị nối, gán kết quả | Không |
| `s += "!"` | Gán kết hợp: nối rồi gán lại | Không |
| `s.concat("!")` | Trả kết quả nối, **bỏ kết quả** | Không; `s` giữ nguyên |
| `s = s.concat("!")` | Nhận kết quả từ `concat()` | Không |
| `builder.append("!")` | Thay đổi nội dung `StringBuilder` | Không áp dụng cho `String`; builder mutable |

Ví dụ lỗi thường gặp:

~~~java
String s = "Hello";

s.concat("!");
System.out.println(s); // Hello

s += "!";
System.out.println(s); // Hello!
~~~

Điểm khác nằm ở việc **có gán kết quả hay không**. Khi gọi `concat()` mà bỏ kết quả, biến không đổi. `+=` bao gồm phép gán trong cú pháp của chính nó.

### Biến final không dùng được +=

~~~java
final String title = "Java";
// title += " Core"; // Lỗi biên dịch: không thể gán lại biến final
~~~

`final` ngăn việc gán lại biến. Dù bản thân `String` là immutable, `+=` vẫn là một phép **gán lại**, nên bị cấm trên biến `final`.

Ngược lại:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core"); // Hợp lệ: không gán lại biến builder
~~~

`final` không biến một đối tượng mutable thành immutable; nó chỉ cố định **tham chiếu** của biến.

## 7. String Pool và vấn đề dùng ==

`String` literal và biểu thức hằng có thể chia sẻ giá trị đã intern, nhưng `+=` thường tạo kết quả lúc chạy. `==` so tham chiếu; `equals()` so nội dung:

```java
String name = "Ja";
name += "va";
System.out.println(name.equals("Java")); // true
```

Danh tính kết quả không phải cơ sở để kiểm tra nội dung. Cơ chế intern/constant expression được giải thích riêng ở các bài về String pool và compiler.

## 8. Vế trái phức tạp: chỉ được đánh giá một lần

Đối với biến đơn giản, có thể đọc `s += x` như `s = s + x`. Tuy nhiên **quy tắc ngôn ngữ** của phép gán kết hợp là vế trái được đánh giá một lần.

~~~java
String[] values = {"A", "B"};
int index = 0;

values[index++] += "!";

System.out.println(index);     // 1
System.out.println(values[0]); // A!
System.out.println(values[1]); // B
~~~

`index++` chỉ thực hiện một lần, rồi Java nối vào phần tử `values[0]` và gán kết quả về đúng phần tử đó.

Không máy móc thay câu lệnh này thành:

~~~java
// KHÔNG tương đương, vì index++ có thể chạy hai lần:
// values[index++] = values[index++] + "!";
~~~

Ở dạng thay thế sai, biểu thức chỉ số có thể bị đánh giá hai lần và các phần tử khác nhau có thể bị đọc/ghi. Với field access, array access hoặc phương thức có tác dụng phụ trong vế trái, cần tuân theo quy tắc đánh giá cụ thể của Java.

### += với phần tử mảng String

~~~java
String[] labels = {"A", "B"};
String old = labels[0];

labels[0] += "1";

System.out.println(labels[0]); // A1
System.out.println(old);       // A
~~~

Phần tử mảng được **gán lại tham chiếu mới**. Đối tượng chuỗi cũ `"A"` vẫn bất biến; biến `old` tiếp tục giữ giá trị cũ.

## 9. Chi phí của nối lặp nhiều lần

Nối `result += part` lặp nhiều lần phải xây giá trị kết quả mới qua mỗi lượt; với dữ liệu tăng, `StringBuilder.append(part)` thường phù hợp hơn. Điều này không có nghĩa mọi `+=` ngắn đều đáng thay đổi:

```java
String greeting = "Hello";
greeting += ", Java"; // Rõ ý, hợp lệ
```

Bài **Nối trong một biểu thức so với tích lũy qua vòng lặp** phân tích mô hình chi phí và cách benchmark; ở bài này trọng tâm vẫn là **phép gán lại tham chiếu**.

## 10. Một chương trình hoàn chỉnh kiểm chứng Java 17+

Tạo file **`StringPlusEqualsDemo.java`**:

~~~java
public class StringPlusEqualsDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;
        first += " Core";
        System.out.println("first=" + first);
        System.out.println("alias=" + alias);

        String missing = null;
        missing += "!";
        System.out.println("missing=" + missing);

        String number = "N";
        number += 1 + 2;
        System.out.println("number=" + number);

        String pieces = "N";
        pieces += 1;
        pieces += 2;
        System.out.println("pieces=" + pieces);

        String[] values = {"A", "B"};
        int index = 0;
        values[index++] += "!";
        System.out.println("index=" + index);
        System.out.println("values[0]=" + values[0]);
        System.out.println("values[1]=" + values[1]);

        StringBuilder builder = new StringBuilder("A");
        StringBuilder builderAlias = builder;
        builder.append("B");
        System.out.println("builder=" + builder);
        System.out.println("builderAlias=" + builderAlias);

        String text = "Ja";
        text += "va";
        System.out.println("equals=" + text.equals("Java"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringPlusEqualsDemo.java
java StringPlusEqualsDemo
~~~

**Stdout chính xác:**

~~~text
first=Java Core
alias=Java
missing=null!
number=N3
pieces=N12
index=1
values[0]=A!
values[1]=B
builder=AB
builderAlias=AB
equals=true
~~~

**Giải thích:**

1. `first` được gán kết quả nối, còn `alias` giữ chuỗi `"Java"`.
2. `missing` ban đầu `null` được chuyển thành đoạn văn bản `"null"`, nên có kết quả `"null!"`.
3. `number += 1 + 2` cộng số trước rồi nối `3`; `pieces` nối hai số riêng nên có `"N12"`.
4. `values[index++] += "!"` chỉ tăng `index` một lần và gán kết quả tại phần tử đầu tiên.
5. `StringBuilder.append()` sửa builder mutable nên `builderAlias` cũng đọc `"AB"`.
6. `equals()` xác nhận nội dung sau `+=` đúng, không phụ thuộc so sánh danh tính đối tượng.

Chương trình độc lập có một lớp public trùng tên file, chạy với Java 17 trở lên, không cần thư viện ngoài JDK.

## 11. Những ngộ nhận cần sửa

| Ngộ nhận | Sự thật |
| --- | --- |
| `s += x` sửa nội dung đối tượng `String` nguồn | Nó tạo giá trị kết quả rồi **gán lại biến** |
| Mọi biến cùng tham chiếu `String` đều thấy giá trị mới sau `+=` | Chỉ vế trái được gán lại; tham chiếu khác giữ giá trị cũ |
| `+=` luôn an toàn khi `s == null` | Có thể tạo văn bản `"null..."` ngoài ý muốn |
| `s += 1 + 2` luôn ra `"...12"` | `1 + 2` thực hiện cộng số trước, ra `3` |
| `s += value` luôn giống thay chữ bằng `s = s + value` | Với vế trái có tác dụng phụ, quy tắc đánh giá một lần rất quan trọng |
| Biến `final String` dùng `+=` được vì String bất biến | `+=` là gán lại, nên **bị lỗi biên dịch** |
| Gọi `s.concat(x)` rồi bỏ kết quả vẫn đổi `s` | Không: String bất biến, phải nhận kết quả |
| `==` đủ để so nội dung sau phép nối | Dùng `String.equals()` |
| Dùng `+=` trong vòng lặp lớn luôn tối ưu | Cân nhắc `StringBuilder`, đo hiệu năng khi cần |
| `StringBuilder.append()` giống `String +=` | `append()` sửa builder; `+=` trên String gán lại tham chiếu |
| `String` mới nào cũng chứa cùng tham chiếu như literal bằng nội dung | Không dựa vào pooling để suy luận danh tính kết quả runtime |

## 12. Bài tập tự luyện

### Bài 1 — Dự đoán hai biến

~~~java
String a = "Hello";
String b = a;
a += "!";
System.out.println(a);
System.out.println(b);
~~~

Dự đoán và giải thích vì sao một biến cho `"Hello!"`, biến còn lại cho `"Hello"`.

### Bài 2 — null khác lỗi phương thức

Chạy `String s = null; s += "X";`. So với `s.concat("X")` khi `s` còn `null`. Giải thích chuỗi văn bản `"nullX"` khác trạng thái thiếu dữ liệu và vì sao không nên chấp nhận nó tự động.

### Bài 3 — Dấu ngoặc số học

Viết ba biểu thức nối từ `"N"` với `1` và `2`: một biểu thức trả `"N3"`, một trả `"N12"`, một trả `"N1,2"`. Dùng dấu ngoặc hoặc dấu phân cách để thể hiện ý định.

### Bài 4 — final

Thử biên dịch:

~~~java
final String code = "A";
// code += "B";
~~~

Bỏ dấu chú thích của dòng thứ hai để quan sát lỗi compiler. Sau đó thử `final StringBuilder builder = new StringBuilder("A"); builder.append("B");` và giải thích sự khác biệt.

### Bài 5 — Mảng và tác dụng phụ

Cho `String[] a = {"X", "Y"}; int i = 0;`, thực hiện `a[i++] += "?";`. Dự đoán `i` và từng phần tử, sau đó giải thích vì sao một phép khai triển dùng hai lần `i++` sẽ làm sai ngữ nghĩa.

### Bài 6 — Nối số trong vòng lặp

Tạo chuỗi số từ `0` đến `9999` theo hai cách: nối `+=` trong vòng lặp và `StringBuilder.append()`. Xác minh **nội dung kết quả giống nhau** và so sánh thiết kế/độ phức tạp. Nếu benchmark, làm nóng JVM, lặp nhiều lần, tránh dùng một phép đo thời gian duy nhất làm kết luận.

### Bài 7 — Không bỏ kết quả

Cho:

~~~java
String title = "Java";
title.concat(" Core");
~~~

Sửa đoạn code để `title` có nội dung `"Java Core"` bằng hai cách: `title = title.concat(" Core");` và `title += " Core";`. Giải thích điểm chung của hai cách.

### Bài 8 — Giữ bản gốc

Tạo `String raw = "  Java  "; String display = raw;`. Cho `display += " Core";`. Kiểm tra `raw` giữ nguyên. Nếu muốn loại khoảng trắng ở `display`, cần áp dụng `strip()` cho kết quả rồi nhận lại giá trị trả về.

## 13. Checklist hoàn thành bài học

Trước khi dùng `+=` với `String`, tự hỏi:

- Biến vế trái có phải `String` và có thể **gán lại** không?
- Mình đang nối văn bản hay muốn làm phép số học trước? Có cần dấu ngoặc?
- Dữ liệu vế trái/đối số có thể là `null`? Có muốn xuất hiện chữ `"null"` không?
- Có biến nào khác đang giữ tham chiếu đến chuỗi gốc không?
- Có đang lặp nối rất nhiều lần? `StringBuilder` có rõ ràng/hiệu quả hơn không?
- Mình đang so kết quả bằng `equals()` thay vì dựa vào `==`?
- Nếu vế trái là một phần tử mảng hoặc field, việc đánh giá biểu thức có tác dụng phụ không?

**Điểm nhớ lâu:** với `String`, `s += part` nghĩa là **tính kết quả ghép văn bản rồi gán kết quả cho `s`**. Nội dung của đối tượng `String` cũ không đổi; các tham chiếu khác tới nó cũng không đổi. Đây là cơ chế bình thường của Java, không có thao tác sửa `String` tại chỗ.

## 14. Tài liệu chuẩn

- [Java Language Specification 17 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26.2): quy tắc `+=`, đánh giá vế trái một lần và phép gán.
- [Java Language Specification 17 — String Concatenation Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): phép `+` trên `String`, string conversion và biểu thức hằng.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): tính bất biến, `concat()`, `equals()` và API chuỗi.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `append()`, mutable builder và `toString()`.

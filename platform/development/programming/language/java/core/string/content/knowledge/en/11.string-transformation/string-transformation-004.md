# `String.repeat(int)`: số lần lặp, chuỗi rỗng và giá trị âm trong Java

## 1. `repeat()` dùng để làm gì?

Khi cần lặp lại **nguyên vẹn một chuỗi** nhiều lần và ghép các bản sao liền nhau, lớp `java.lang.String` cung cấp phương thức:

```java
public String repeat(int count)
```

Phương thức `String.repeat(int)` có từ **Java 11** và dùng được trên Java 17 trở lên. Nó tạo ra **giá trị chuỗi kết quả** bằng cách lặp toàn bộ nội dung của chuỗi nhận lời gọi đúng `count` lần. Không có dấu phân cách nào được tự thêm vào giữa các lần lặp.

Ví dụ, trong phần thân một phương thức Java:

```java
String word = "ha";
String result = word.repeat(3);

System.out.println(result); // hahaha
```

Cách hiểu trực quan:

```text
"ha".repeat(3)
    = "ha" + "ha" + "ha"
    = "hahaha"
```

`repeat` đặc biệt tiện để tạo các dấu phân cách, ký tự đệm, đường kẻ minh họa, hoặc chuỗi mẫu với số lần lặp đã biết. Nó **không sửa nội dung của chuỗi gốc** vì `String` là bất biến (*immutable*).

**Quy tắc quan trọng nhất:** tham số `count` phải **không âm**. Giá trị `0` là hợp lệ và cho chuỗi rỗng; số âm khiến phương thức ném `IllegalArgumentException`.

## 2. Bảng hành vi theo số lần lặp

Giả sử chuỗi nhận lời gọi là `"ab"`:

| Biểu thức | Kết quả hoặc hành vi | Ý nghĩa |
|---|---|---|
| `"ab".repeat(0)` | `""` | Lặp không lần nào |
| `"ab".repeat(1)` | `"ab"` | Giữ cùng nội dung, một lần |
| `"ab".repeat(2)` | `"abab"` | Nối hai bản sao |
| `"ab".repeat(3)` | `"ababab"` | Nối ba bản sao |
| `"ab".repeat(-1)` | `IllegalArgumentException` | Số lần lặp âm là không hợp lệ |

Điều này khác cách một số người mới học có thể phỏng đoán:

- `repeat(0)` **không** trả về chuỗi gốc và cũng **không** trả `null`. Nó trả về chuỗi rỗng `""`.
- `repeat(1)` cho **nội dung giống chuỗi gốc**. Không nên dựa vào phép so sánh tham chiếu `==` để kiểm tra kết quả, dù triển khai JDK có thể tái sử dụng đối tượng trong trường hợp này.
- `repeat(2)` trở lên nối các bản sao **không chèn khoảng trắng, dấu phẩy hay xuống dòng** giữa chúng.
- `repeat(-1)` không có nghĩa là “bỏ một phần tử” hoặc “lặp ngược”. Đó là đối số sai, nên Java ném ngoại lệ.

Một chuỗi nhiều ký tự luôn được lặp **cả cụm**:

```java
System.out.println("Java ".repeat(3)); // Java Java Java 
System.out.println("ab".repeat(3));    // ababab
System.out.println("-=".repeat(3));    // -=-=-=
```

Trong ví dụ đầu, khoảng trắng nằm **sẵn trong** chuỗi `"Java "`. Do đó kết quả có cả dấu cách cuối cùng. Nếu gọi `"Java".repeat(3)`, kết quả sẽ là `"JavaJavaJava"`.

## 3. Trường hợp chuỗi nhận lời gọi rỗng

Một **chuỗi rỗng** được biểu diễn bằng `""` và có độ dài bằng `0`. Khi nội dung gốc rỗng, lặp bao nhiêu lần **không âm** thì kết quả vẫn rỗng:

```java
"".repeat(0) // ""
"".repeat(1) // ""
"".repeat(5) // ""
```

Bởi vì nối các chuỗi rỗng không tạo thêm ký tự nào:

```text
"" + "" + "" = ""
```

Dù chuỗi nhận lời gọi có nội dung hay không, quy tắc đối với **số âm** vẫn giữ nguyên:

```java
"".repeat(-2); // Ném IllegalArgumentException
```

Đây là điểm cần nhớ: **chuỗi rỗng không làm cho số lần lặp âm trở nên hợp lệ**.

### Chuỗi rỗng khác với `null`

```java
String empty = "";
System.out.println(empty.repeat(3).isEmpty()); // true

String missing = null;
// missing.repeat(3); // NullPointerException
```

`empty` tham chiếu đến một đối tượng `String` hợp lệ có `length() == 0`; vì vậy `repeat` gọi được. `missing` là tham chiếu `null`, nên không có đối tượng nào để nhận lời gọi phương thức. Lỗi này khác với `IllegalArgumentException` khi truyền `count` âm cho một chuỗi hợp lệ.

## 4. Số âm và ngoại lệ `IllegalArgumentException`

`repeat(int count)` yêu cầu `count >= 0`. Khi `count < 0`, Java ném một ngoại lệ kiểu `IllegalArgumentException`.

```java
String line = "-";
line.repeat(-1); // IllegalArgumentException
```

Để bắt ngoại lệ trong tình huống thử nghiệm:

```java
try {
    String result = "ab".repeat(-3);
    System.out.println(result);
} catch (IllegalArgumentException ex) {
    System.out.println("count phải không âm");
}
```

**Stdout:**

```text
count phải không âm
```

Không nên dùng `catch (Exception ignored) {}` để âm thầm bỏ lỗi nếu giá trị `count` đến từ công thức hay đầu vào người dùng. Thường tốt hơn là làm rõ quy tắc nghiệp vụ trước khi gọi:

```java
static String repeatSafely(String text, int count) {
    if (count < 0) {
        throw new IllegalArgumentException("count phải >= 0");
    }
    return text.repeat(count);
}
```

Đây là một phương thức minh họa đặt bên trong một lớp. Phép kiểm tra giúp thông báo lỗi dễ hiểu hơn trong mã ứng dụng, nhưng bản thân `repeat` đã kiểm tra số lần lặp âm.

### Khi `count` được tính bằng biểu thức

Một tình huống thực tế là tính số dấu cách cần thêm để đạt độ rộng mong muốn:

```java
String label = "Java";
int width = 3;
int padding = width - label.length(); // -1
// String result = label + " ".repeat(padding); // Lỗi vì count = -1
```

Nếu ý định là **không thêm đệm khi nội dung đã dài**, có thể chặn về `0`:

```java
int padding = Math.max(0, width - label.length());
String result = label + " ".repeat(padding);
```

Ở đây `Math.max(0, ...)` phản ánh **quy tắc nghiệp vụ của việc đệm chuỗi**. Không nên tự động biến mọi `count` âm thành `0` trong mọi tình huống: đôi khi số âm là lỗi dữ liệu cần được thông báo rõ ràng.

## 5. Ví dụ Java 17+ hoàn chỉnh

Lưu nội dung sau vào tệp **`StringRepeatDemo.java`**:

```java
public class StringRepeatDemo {

    static void show(String label, String value) {
        System.out.println(label + "=[" + value + "], length=" + value.length());
    }

    public static void main(String[] args) {
        String unit = "ab";

        show("zero", unit.repeat(0));
        show("once", unit.repeat(1));
        show("twice", unit.repeat(2));
        show("three", unit.repeat(3));

        show("emptyFive", "".repeat(5));
        show("emptyZero", "".repeat(0));
        show("emojiTwice", "😀".repeat(2));

        System.out.println("original=" + unit);
        unit.repeat(3); // Giá trị trả về bị bỏ qua
        System.out.println("discarded=" + unit);

        String saved = unit.repeat(3);
        System.out.println("saved=" + saved);

        try {
            "".repeat(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative=" + ex.getClass().getSimpleName());
        }

        show("dashes", "-".repeat(6));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 StringRepeatDemo.java
java StringRepeatDemo
```

**Stdout:**

```text
zero=[], length=0
once=[ab], length=2
twice=[abab], length=4
three=[ababab], length=6
emptyFive=[], length=0
emptyZero=[], length=0
emojiTwice=[😀😀], length=4
original=ab
discarded=ab
saved=ababab
negative=IllegalArgumentException
dashes=[------], length=6
```

### Phân tích kết quả

1. `repeat(0)` trả `""` nên phần nội dung trong dấu `[]` trống và `length()` là `0`.
2. `repeat(1)`, `repeat(2)` và `repeat(3)` tạo nội dung tương ứng `"ab"`, `"abab"` và `"ababab"`.
3. `""` lặp `5` lần hoặc `0` lần vẫn là chuỗi rỗng.
4. `"😀"` là **một Unicode code point** nhưng được biểu diễn bằng **hai UTF-16 code unit**; hai emoji có `String.length() == 4`.
5. `unit.repeat(3);` tính kết quả rồi bỏ qua, nên biến `unit` vẫn giữ `"ab"`. Khi lưu kết quả vào `saved`, giá trị `"ababab"` được giữ lại.
6. `"" .repeat(-1)` (trong code viết không có dấu cách giữa `""` và `.repeat`) vẫn ném `IllegalArgumentException`, cho thấy đối số âm bị từ chối ngay cả khi chuỗi rỗng.
7. `"-".repeat(6)` tạo đúng sáu dấu gạch nối, không có dấu phân cách bổ sung.

Ví dụ dùng `show` để kẹp nội dung trong `[]`: nhờ vậy chuỗi rỗng dễ nhận biết hơn khi in ra màn hình.

## 6. `repeat()` và tính bất biến của `String`

Giống `trim()`, `replace()`, `substring()` hay `toUpperCase()`, `repeat()` là phương thức tạo **giá trị trả về** và không sửa nội dung đối tượng `String` nhận lời gọi.

**Sai nếu mục đích là cập nhật biến:**

```java
String marker = "*";
marker.repeat(4);
System.out.println(marker); // *
```

Lời gọi `marker.repeat(4)` đã trả về `"****"`, nhưng kết quả bị bỏ qua. Để giữ kết quả, có thể:

**Gán lại biến:**

```java
marker = marker.repeat(4);
System.out.println(marker); // ****
```

**Hoặc lưu vào biến khác:**

```java
String original = "*";
String repeated = original.repeat(4);

System.out.println(original); // *
System.out.println(repeated); // ****
```

**Hoặc dùng ngay làm đối số:**

```java
System.out.println("*".repeat(4)); // ****
```

Không có lý do gì để giả định `repeat()` làm tăng độ dài của chính đối tượng `String` cũ. Java chỉ cho phép thay đổi **giá trị của biến tham chiếu** bằng phép gán lại; đối tượng `String` vốn bất biến.

### Không dựa vào `==` để nhận diện kết quả

Khi `count == 1`, nội dung kết quả giống nội dung gốc. Triển khai JDK có thể trả về cùng một đối tượng `String`, nhưng đây không phải điều kiện cần để sử dụng phương thức.

```java
String source = new String("xy");
String once = source.repeat(1);

System.out.println(source.equals(once)); // true
```

Dùng `.equals(...)` để kiểm tra nội dung; dùng `==` trên hai `String` là so **tham chiếu đối tượng**, không phải so văn bản.

## 7. Độ dài kết quả và lưu ý về bộ nhớ

Nếu chuỗi ban đầu có `m = source.length()` (đo bằng **UTF-16 code unit**) và `count = n` là số nguyên không âm, độ dài của chuỗi kết quả về mặt toán học là:

\[
L = m \times n
\]

Ví dụ:

```java
String a = "abc";
String b = a.repeat(4);

System.out.println(b);          // abcabcabcabc
System.out.println(b.length()); // 12 = 3 * 4
```

Với chuỗi rỗng, `m == 0`, kết quả luôn có độ dài `0` cho mọi `n >= 0`. Với `n == 0`, kết quả cũng có độ dài `0` bất kể chuỗi gốc.

### Không nên tạo chuỗi khổng lồ

`repeat` có thể yêu cầu cấp phát bộ nhớ tương ứng với kích thước kết quả. Một `count` dương rất lớn kết hợp với chuỗi dài có thể gây vấn đề về bộ nhớ hoặc làm chương trình chậm. Nếu yêu cầu kích thước vượt khả năng biểu diễn hoặc cấp phát của JVM, thao tác có thể thất bại, chẳng hạn bằng **`OutOfMemoryError`**.

Không chạy thử ví dụ nguy hiểm như sau trong một ứng dụng bình thường:

```java
// Minh họa không nên thực thi: có nguy cơ tiêu thụ bộ nhớ rất lớn.
String huge = "abcdefghij".repeat(Integer.MAX_VALUE);
```

Đây là vấn đề **kích thước/bộ nhớ**, khác với lỗi `IllegalArgumentException` do `count` âm. Đừng dựa vào một thông báo lỗi cụ thể hoặc vào việc JVM luôn cấp phát được chuỗi chỉ vì `count >= 0`.

Khi dữ liệu từ người dùng quyết định số lần lặp, hãy đặt giới hạn phù hợp. Ví dụ, phương thức dưới đây giới hạn tổng độ dài kết quả bằng một mức do ứng dụng đặt ra:

```java
static String boundedRepeat(String text, int count, int maxUnits) {
    if (text == null) {
        throw new IllegalArgumentException("text không được null");
    }
    if (count < 0 || maxUnits < 0) {
        throw new IllegalArgumentException("count và maxUnits phải không âm");
    }

    long expectedUnits = (long) text.length() * count;
    if (expectedUnits > maxUnits) {
        throw new IllegalArgumentException("Kết quả vượt giới hạn");
    }

    return text.repeat(count);
}
```

Phép ép `(long)` trước phép nhân giúp tránh **tràn số nguyên `int`** khi kiểm tra kích thước. Kiểm tra này giới hạn số UTF-16 code unit theo chính sách ứng dụng, chứ không bảo đảm mọi hoạt động cấp phát bộ nhớ luôn thành công.

## 8. Unicode và ký tự nhiều đơn vị UTF-16

`repeat` không thao tác riêng từng ký tự để chọn hoặc cắt. Nó lặp **toàn bộ chuỗi gốc**, nên những cặp surrogate hợp lệ ở bên trong một bản sao vẫn được sao chép cùng nhau.

Ví dụ:

```java
String emoji = "😀";
String repeated = emoji.repeat(3);

System.out.println(repeated); // 😀😀😀
System.out.println(repeated.length()); // 6
System.out.println(
        repeated.codePointCount(0, repeated.length())
); // 3
```

`String.length()` tính UTF-16 code unit; mỗi emoji ở đây gồm hai code unit, nên ba emoji có độ dài `6` nhưng chỉ có `3` Unicode code point.

Tương tự, với ký tự tiếng Việt được biểu diễn bằng nhiều code point (ví dụ chữ cái cộng dấu kết hợp), `repeat` vẫn sao chép **đúng chuỗi mã đầu vào**. Phương thức **không chuẩn hóa Unicode**, không đổi chữ hoa/thường và không tự gộp các ký tự kết hợp.

Nếu chuỗi nguồn vốn chứa một surrogate không ghép cặp hợp lệ, `repeat` cũng không tự sửa hoặc kiểm tra tính hợp lệ của dữ liệu Unicode ấy. Nó chỉ lặp chuỗi theo nội dung đã có.

## 9. Khi nào nên và không nên sử dụng `repeat()`?

### Tạo đường kẻ hoặc dấu nhấn văn bản

```java
String line = "-".repeat(12);
System.out.println(line); // ------------
```

Đơn giản và dễ hiểu hơn việc tự viết vòng lặp để nối một ký tự cố định.

### Tạo phần đệm có số lượng xác định

```java
String label = "OK";
int width = 6;

String padded = label + " ".repeat(Math.max(0, width - label.length()));
System.out.println("[" + padded + "]"); // [OK    ]
```

Ví dụ tính độ rộng theo `String.length()` (UTF-16 code unit). Nếu cần canh cột chính xác theo **độ rộng hiển thị của terminal**, `length()` không đủ cho mọi emoji, ký tự kết hợp hoặc chữ có độ rộng khác nhau.

### Tạo nhiều dòng trống hoặc ký tự xuống dòng

```java
String twoNewlines = "\n".repeat(2);
```

Kết quả chứa hai ký tự xuống dòng. Khi in chuỗi này trực tiếp, các dòng trống có thể khó nhận diện bằng mắt; đây là lý do các ví dụ QA thường in thêm nhãn hoặc độ dài.

### Phân biệt với việc nối có dấu phân cách

```java
String result = "Java".repeat(3);
// "JavaJavaJava"
```

Nếu muốn `"Java,Java,Java"`, cần tự xây dựng logic về **dấu phân cách**. Một cách đơn giản là dùng `String.join` với danh sách các phần tử:

```java
String joined = String.join(",", java.util.Collections.nCopies(3, "Java"));
System.out.println(joined); // Java,Java,Java
```

`repeat` tự nó **không** có đối số cho dấu phân cách; `String.join` thực hiện một bài toán khác là nối các phần tử bằng ký tự phân tách.

### Trường hợp vòng lặp hoặc `StringBuilder` phù hợp hơn

`repeat` phù hợp khi muốn lặp **cùng một mẫu** đúng số lần. Nếu nội dung ở mỗi bước khác nhau, chẳng hạn `"1, 2, 3"` hay mỗi dòng chứa một số thứ tự mới, hãy dùng vòng lặp và `StringBuilder` hoặc những API tập hợp thích hợp.

```java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append(", ");
    }
    builder.append(i);
}
System.out.println(builder); // 1, 2, 3
```

Phương thức `String.repeat` không nhận một callback để sinh nội dung mới ở từng lượt. Nó luôn lặp chính chuỗi nhận lời gọi.

## 10. Những lỗi phổ biến

| Cách hiểu hoặc mã | Vấn đề | Cách sửa / nguyên tắc |
|---|---|---|
| `"ab".repeat(0)` sẽ trả `"ab"` | Sai: số lần lặp `0` tạo chuỗi rỗng | Dự đoán kết quả `""` |
| `"".repeat(5)` sẽ báo lỗi | Sai: chuỗi rỗng là đầu vào hợp lệ | Kết quả vẫn `""` |
| `"".repeat(-1)` sẽ trả `""` | Sai: `count < 0` bị từ chối | Xử lý hoặc báo lỗi `IllegalArgumentException` |
| `text.repeat(3);` tự sửa `text` | `String` bất biến | Gán lại hoặc sử dụng giá trị trả về |
| `"ha".repeat(3)` tự thêm dấu cách | Không có dấu phân cách mặc định | Đặt dấu cách vào mẫu nếu cần |
| `String value = null; value.repeat(2);` | Gọi phương thức trên `null` | Kiểm tra đầu vào, tránh `NullPointerException` |
| `repeat` chấp nhận số thực `2.5` | Tham số phải là `int` | Chọn số nguyên theo quy tắc nghiệp vụ |
| `repeat` luôn an toàn với `Integer.MAX_VALUE` | Chuỗi đầu ra có thể quá lớn | Giới hạn `count` và kích thước dự kiến |
| `"😀".repeat(2).length()` bằng `2` | `length()` đếm UTF-16 code unit | Kết quả ví dụ là `4`, tương ứng 2 code point |

### Chú ý khi kiểm tra ngoại lệ

Đừng kiểm tra thông báo (`ex.getMessage()`) như một chuỗi cố định. Thông điệp có thể khác tùy JDK hoặc đường đi thực thi. Khi dạy khái niệm, điều cần xác nhận ở trường hợp số âm là **kiểu ngoại lệ `IllegalArgumentException`** và nguyên nhân `count < 0`.

## 11. Kiểm thử các trường hợp biên

Bạn có thể tạo một phương thức tự kiểm tra, đặt bên trong lớp Java:

```java
static void testRepeat() {
    if (!"".equals("abc".repeat(0))) {
        throw new AssertionError("repeat(0) phải trả chuỗi rỗng");
    }
    if (!"abc".equals("abc".repeat(1))) {
        throw new AssertionError("repeat(1) phải giữ nội dung");
    }
    if (!"abcabc".equals("abc".repeat(2))) {
        throw new AssertionError("repeat(2) phải ghép hai bản sao");
    }
    if (!"".equals("".repeat(100))) {
        throw new AssertionError("Chuỗi rỗng lặp vẫn rỗng");
    }

    boolean negativeRejected = false;
    try {
        "".repeat(-1);
    } catch (IllegalArgumentException ex) {
        negativeRejected = true;
    }
    if (!negativeRejected) {
        throw new AssertionError("count âm phải bị từ chối");
    }
}
```

Có thể gọi `testRepeat();` từ `main`. Nếu đúng hết, phương thức kết thúc bình thường mà không in gì. Các khẳng định này dùng `AssertionError` được ném trực tiếp nên không phụ thuộc cờ chạy `-ea`.

Bộ kiểm thử tập trung vào **đặc tả của phương thức**: `0`, `1`, số dương, chuỗi rỗng và số âm. Đây là những ca cần có khi bạn viết hàm tiện ích dựa trên `repeat()`.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `"xy".repeat(3)` tạo chuỗi gì và độ dài bằng bao nhiêu?

**Đáp án:** `"xyxyxy"`, độ dài `6` UTF-16 code unit.

**Câu 2.** `"-".repeat(0)` và `"".repeat(10)` có trả cùng nội dung không?

**Đáp án:** Có. Cả hai đều trả chuỗi rỗng `""`.

**Câu 3.** Vì sao `String x = "a"; x.repeat(4);` rồi in `x` vẫn ra `"a"`?

**Đáp án:** `String` bất biến; kết quả `"aaaa"` đã bị bỏ qua. Muốn giữ kết quả cần `x = x.repeat(4);` hoặc lưu vào biến khác.

**Câu 4.** `String.repeat(-5)` và `null.repeat(5)` có gây cùng lỗi không?

**Đáp án:** Không. Gọi trên một `String` hợp lệ với `count = -5` gây `IllegalArgumentException`; cố gọi phương thức trên tham chiếu `null` gây `NullPointerException`.

**Câu 5.** Tại sao không nên thực hiện `"abc".repeat(count)` khi `count` do người dùng nhập mà không giới hạn?

**Đáp án:** `count` quá lớn có thể yêu cầu lượng bộ nhớ rất lớn. Nên kiểm tra tính hợp lệ, giới hạn số lần lặp hoặc tổng độ dài dự kiến theo yêu cầu ứng dụng.

**Câu 6.** `"ab".repeat(3)` và `String.join("-", Collections.nCopies(3, "ab"))` khác nhau thế nào?

**Đáp án:** `repeat` tạo `"ababab"`; `String.join` với danh sách ba phần tử và dấu nối `"-"` tạo `"ab-ab-ab"`. `repeat` không tự chèn dấu phân cách.

## 13. Ghi nhớ

`String.repeat(int count)` lặp **toàn bộ nội dung chuỗi** đúng `count` lần, liền nhau và không thêm dấu phân cách. Với `count = 0`, kết quả là `""`; với `count = 1`, nội dung không đổi; với `count > 1`, các bản sao được nối liên tục. Chuỗi rỗng lặp một số lần **không âm** vẫn rỗng, nhưng **mọi `count` âm đều gây `IllegalArgumentException`**, kể cả với chuỗi rỗng.

Vì `String` bất biến, bạn phải **sử dụng giá trị trả về** của `repeat` nếu muốn giữ kết quả. Khi số lần lặp đến từ dữ liệu ngoài hoặc phép tính, hãy xác thực số âm và giới hạn tổng độ dài trước khi cấp phát chuỗi lớn.

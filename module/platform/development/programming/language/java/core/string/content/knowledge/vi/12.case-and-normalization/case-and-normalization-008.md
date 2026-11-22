# `Collator` trong Java: so sánh chuỗi theo quy tắc ngôn ngữ

Khi người dùng xem danh sách tên người, từ ngữ hoặc nhãn sản phẩm, họ thường mong **thứ tự bảng chữ cái theo ngôn ngữ**. Thứ tự này có thể khác thứ tự UTF-16 mà `String.compareTo()` sử dụng. Java cung cấp **`java.text.Collator`** để so sánh và sắp xếp chuỗi theo những quy tắc *collation* phụ thuộc `Locale`, như tiếng Việt, tiếng Đức hay tiếng Thụy Điển.

**Ý chính:** `String.equals()` kiểm tra cùng nội dung; `String.compareTo()` so theo thứ tự code unit của chuỗi; còn **`Collator.compare(a, b)`** xác định thứ tự (và mức độ tương đương khi so sánh) theo ngôn ngữ và cấu hình. `Collator` rất hữu ích cho giao diện hoặc danh sách hướng tới người đọc, nhưng không tự động là công cụ phù hợp để kiểm tra token, mã định danh hoặc quyền truy cập.

## 1. Vì sao cần `Collator`?

Các bảng chữ cái không luôn xử lý chữ có dấu theo cùng một cách. Ví dụ, trong cách sắp xếp phổ biến của tiếng Đức, `ä` thường được xếp gần `a`; còn trong tiếng Thụy Điển, `ä` đứng sau `z`. Vì vậy một thứ tự dựa trên giá trị UTF-16 không thể đại diện cho mọi ngôn ngữ.

Java có ba cách quen thuộc:

| API | Quy tắc cơ bản | Nhu cầu phù hợp |
| --- | --- | --- |
| `a.equals(b)` | So sánh **toàn bộ nội dung `String`**; phân biệt hoa/thường và code unit | Kiểm tra mã, chuỗi chính xác |
| `a.compareTo(b)` | So thứ tự từ điển dựa trên **UTF-16 code unit**, không phụ thuộc `Locale` | Quy ước sắp xếp kỹ thuật cố định |
| `collator.compare(a, b)` | So theo **quy tắc collation của `Locale` và cấu hình** | Sắp xếp tên, từ và nhãn hiển thị |
| `a.compareToIgnoreCase(b)` | So không phân biệt hoa/thường theo cách của `String`, **không phải collation theo `Locale`** | So sánh đơn giản khi không cần quy tắc ngôn ngữ |

Ví dụ sử dụng `Collator`:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
int result = collator.compare("An", "Bình");
```

Đây là **đoạn mã minh họa đặt trong phương thức**. `Locale.forLanguageTag("vi-VN")` mô tả ngôn ngữ và vùng mong muốn. Nhà cung cấp dữ liệu locale của JDK quyết định những quy tắc thực tế được áp dụng; khi thiếu dữ liệu chuyên biệt, môi trường có thể sử dụng quy tắc dự phòng. Vì vậy nên thử trên JDK và locale đang triển khai, đặc biệt với tên có dấu.

## 2. Lấy `Collator` theo `Locale` và đọc kết quả so sánh

`Collator` là lớp trừu tượng. Thông thường không gọi `new Collator()` mà tạo đối tượng qua:

```java
Collator collator = Collator.getInstance(Locale.US);
```

Một số cách tạo `Locale`:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale swedish = Locale.forLanguageTag("sv-SE");
Locale german = Locale.GERMAN;
```

Ví dụ trên là các khai báo dùng trong phạm vi có `import java.util.Locale;`.

Kết quả `collator.compare(a, b)` là một số nguyên:

- **Âm**: `a` đứng trước `b` theo collator.
- **Bằng 0**: `a` và `b` được xem là **tương đương ở mức so sánh đang cấu hình**.
- **Dương**: `a` đứng sau `b`.

Không dựa vào giá trị cụ thể như `-1` hay `1` trong mọi trường hợp. Dùng `< 0`, `== 0` và `> 0`; với phần minh họa muốn in dấu so sánh, có thể dùng `Integer.signum(...)` để chuyển kết quả về `-1`, `0` hoặc `1`.

### Ví dụ: cùng ký tự, thứ tự khác nhau giữa các locale

Lưu tệp `LocaleOrderDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class LocaleOrderDemo {
    public static void main(String[] args) {
        Collator german = Collator.getInstance(Locale.GERMAN);
        Collator swedish = Collator.getInstance(
                Locale.forLanguageTag("sv-SE"));

        String aUmlaut = "\u00E4"; // ä

        System.out.println(Integer.signum(
                german.compare(aUmlaut, "z")));
        System.out.println(Integer.signum(
                swedish.compare(aUmlaut, "z")));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 LocaleOrderDemo.java
java LocaleOrderDemo
```

Với dữ liệu locale của OpenJDK sử dụng trong ví dụ, kết quả:

```text
-1
1
```

`-1` ở dòng đầu cho biết `ä` được xếp trước `z` trong ví dụ tiếng Đức; `1` ở dòng sau cho biết `ä` được xếp sau `z` trong ví dụ tiếng Thụy Điển. **Bộ quy tắc có thể biến đổi theo phiên bản JDK, cấu hình locale provider và dữ liệu ngôn ngữ**, do đó không nên dùng một danh sách ví dụ làm bảng xếp hạng bất biến cho mọi môi trường. Khi cần tái lập dữ liệu giữa hệ thống, cố định môi trường/phiên bản collation.

## 3. Điều chỉnh mức độ phân biệt bằng `setStrength()`

`Collator` cho phép xác định **độ mạnh (strength)** khi so sánh. Mức càng cao càng xét thêm những khác biệt nhỏ giữa các chuỗi.

| Strength | Ý tưởng chính | Khác biệt thường có tác dụng |
| --- | --- | --- |
| `Collator.PRIMARY` | So những khác biệt cơ bản của chữ | Trong nhiều locale, có thể coi chữ có/không dấu và hoa/thường là tương đương |
| `Collator.SECONDARY` | Xét thêm khác biệt thứ cấp | Thường thêm sự khác biệt dấu hoặc biến thể chữ |
| `Collator.TERTIARY` | Xét thêm khác biệt thứ ba | Thường thêm khác biệt hoa/thường và các biến thể khác |
| `Collator.IDENTICAL` | Mức nhận biết khác biệt tinh hơn | Hữu ích khi cần phân biệt ở mức gần với dạng biểu diễn, chịu ảnh hưởng chế độ decomposition |

**Lưu ý:** Đây là mô tả định hướng; cách một dấu, biến thể chữ hoặc quy tắc chữ ghép được xét cụ thể còn phụ thuộc **`Locale` và dữ liệu collation**. Chẳng hạn không nên khẳng định mọi locale đều bỏ qua mọi dấu tại `PRIMARY`. Nếu cần lọc “không dấu” hoặc tìm kiếm tiếng Việt theo quy tắc đặc biệt, phải kiểm thử đúng tập dữ liệu.

### Ví dụ: chữ hoa/thường và dấu

Lưu tệp `CollatorStrengthDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);

        collator.setStrength(Collator.PRIMARY);
        System.out.println(collator.compare(
                "resume", "r\u00E9sum\u00E9") == 0);
        System.out.println(collator.compare(
                "Java", "java") == 0);

        collator.setStrength(Collator.SECONDARY);
        System.out.println(collator.compare(
                "resume", "r\u00E9sum\u00E9") == 0);
        System.out.println(collator.compare(
                "Java", "java") == 0);

        collator.setStrength(Collator.TERTIARY);
        System.out.println(collator.compare(
                "Java", "java") == 0);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
```

Kết quả với dữ liệu locale đã kiểm tra:

```text
true
true
false
true
false
```

Giải thích:

1. Ở `PRIMARY` với `Locale.US`, `resume` và `résumé` được xem là tương đương; `Java` và `java` cũng tương đương.
2. Ở `SECONDARY`, sự khác biệt dấu sắc khiến `resume` và `résumé` không còn tương đương; khác biệt chữ hoa/thường giữa `Java` và `java` vẫn được bỏ qua trong ví dụ.
3. Ở `TERTIARY`, `Java` và `java` không còn tương đương trong ví dụ.

Vì `setStrength()` thay đổi chính sách so sánh, **không thay đổi cấu hình collator trong lúc một bộ sưu tập đã được sắp xếp hoặc đánh chỉ mục bằng collator đó đang hoạt động**; thứ tự so sánh phải nhất quán trong suốt thao tác.

### `compare(a, b) == 0` khác `a.equals(b)`

`String.equals()` chỉ trả `true` khi nội dung chuỗi giống nhau theo quy tắc của `String`. `Collator.compare(a, b) == 0` chỉ cho biết hai chuỗi không khác nhau **theo strength/locale/decomposition hiện tại**. Với strength thấp, các chuỗi khác nhau có thể được coi là tương đương.

Điều này còn ảnh hưởng tới `TreeSet` hoặc `TreeMap`: nếu dùng collator làm comparator, hai khóa có `compare() == 0` được bộ sưu tập xem như cùng một khóa về thứ tự, dù `String.equals()` trả `false`. Không dùng collator strength thấp để lưu tập khóa cần phân biệt chính xác từng ký tự.

## 4. `setDecomposition()`: chữ dựng sẵn và dấu kết hợp

Unicode cho phép một số văn bản được biểu diễn bằng nhiều dãy code point khác nhau nhưng **tương đương chuẩn (canonical equivalence)**:

- `"\u00E9"`: chữ `é` dựng sẵn (U+00E9).
- `"e\u0301"`: chữ `e` và dấu sắc kết hợp U+0301.

`String.equals()` so nội dung code unit nên thường trả `false` cho hai biểu diễn trên. Trong khi đó, bài toán so sánh ngôn ngữ có thể muốn coi chúng tương đương.

`Collator` có chế độ decomposition:

- `Collator.NO_DECOMPOSITION`: không yêu cầu bước decomposition chuẩn trước khi so sánh; thường tiết kiệm xử lý hơn nhưng cần thận trọng với các dạng Unicode tương đương.
- `Collator.CANONICAL_DECOMPOSITION`: xét sự phân rã tương đương chuẩn; thích hợp khi cần xử lý các chuỗi chữ dựng sẵn và tổ hợp dấu một cách nhất quán.
- `Collator.FULL_DECOMPOSITION`: phân rã tương thích rộng hơn, có thể coi thêm những biểu diễn khác là tương đương theo collation; **không tự chọn mức này nếu nghiệp vụ yêu cầu phân biệt các ký tự tương thích**.

### Ví dụ hoàn chỉnh về dạng Unicode

Lưu tệp `CanonicalDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CanonicalDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println(composed.equals(decomposed));
        System.out.println(
                collator.compare(composed, decomposed) == 0);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CanonicalDemo.java
java CanonicalDemo
```

Kết quả:

```text
false
true
```

Cả hai chuỗi hiển thị tương tự `Café`. Tuy nhiên, `equals()` so dãy mã khác nhau; `Collator` với decomposition chuẩn xem chúng tương đương trong cấu hình ví dụ.

**Phân biệt:** `Normalizer.normalize(text, Normalizer.Form.NFC)` là thao tác *biến đổi nội dung* về dạng chuẩn. Ngược lại, `collator.compare(...)` là thao tác *so sánh* theo quy tắc; nó không thay thế hoặc chỉnh sửa hai `String` đầu vào.

## 5. Dùng `Collator` để sắp xếp danh sách

`Collator` triển khai `Comparator`, có thể truyền trực tiếp cho `List.sort(...)` hoặc `Collections.sort(...)`. Ví dụ độc lập `CollatorSortDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class CollatorSortDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);

        List<String> names = new ArrayList<>(
                List.of("Zoe", "Alice", "Bob"));
        names.sort(collator);
        System.out.println(names);

        List<String> fromKeys = names.stream()
                .map(collator::getCollationKey)
                .sorted()
                .map(CollationKey::getSourceString)
                .toList();
        System.out.println(fromKeys);

        collator.setStrength(Collator.PRIMARY);
        TreeSet<String> unique = new TreeSet<>(collator);
        unique.add("resume");
        unique.add("r\u00E9sum\u00E9");
        System.out.println(unique.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CollatorSortDemo.java
java CollatorSortDemo
```

Kết quả với cấu hình `Locale.US` đã kiểm tra:

```text
[Alice, Bob, Zoe]
[Alice, Bob, Zoe]
1
```

Hai dòng đầu minh họa sắp xếp trực tiếp bằng `Collator` và dùng khóa `CollationKey`. Dòng cuối cho thấy `TreeSet` tại `PRIMARY` chỉ giữ **một khóa theo quan hệ so sánh**, vì `resume` và `résumé` được xem là tương đương theo collator. Nó **không** chứng minh hai `String` có nội dung như nhau theo `equals()`.

### Khi nào dùng `CollationKey`?

`CollationKey` lưu khóa so sánh rút ra từ `Collator`. Với một tập chuỗi phải so sánh nhiều lần (chẳng hạn sắp xếp lặp lại cùng dữ liệu), tạo khóa một lần có thể giảm công việc phân tích từng chuỗi mỗi lần so sánh.

Quy tắc sử dụng:

1. Tạo các khóa bằng **cùng collator với cùng cấu hình `Locale`, strength và decomposition**.
2. So sánh/sắp xếp các khóa bằng `CollationKey.compareTo(...)`.
3. Dùng `getSourceString()` để lấy lại chuỗi ban đầu nếu cần.
4. Cân nhắc chi phí tạo/lưu khóa so với việc chỉ so sánh vài chuỗi; không mặc định dùng `CollationKey` cho mọi trường hợp.

Không so sánh khóa được tạo bằng các collator có quy tắc khác nhau, vì thứ tự của chúng có thể không tương thích. Khi thay đổi strength/decomposition, hãy **tạo lại khóa** nếu cần tiếp tục so sánh nhất quán.

## 6. Các quy tắc an toàn và giới hạn thực tế

### 6.1. Locale cố định hay locale của người dùng?

- **Sắp xếp dữ liệu để hiển thị:** chọn `Locale` ứng với ngôn ngữ/môi trường mà người dùng muốn xem. Ví dụ `Locale.forLanguageTag("vi-VN")` khi yêu cầu sắp xếp tên tiếng Việt.
- **Cần kết quả đồng nhất giữa máy chủ:** cố định locale, phiên bản JDK, dữ liệu collation và cấu hình; ghi nhận thay đổi khi nâng cấp runtime. Ngay cả cùng thẻ locale, dữ liệu collation của các hệ thống khác nhau có thể khác.
- **Không dùng mặc định một cách vô thức:** `Collator.getInstance()` dùng locale mặc định của máy chạy, nên kết quả có thể phụ thuộc môi trường. Khi quy tắc nghiệp vụ đã xác định, truyền `Locale` tường minh.

### 6.2. Không dùng collation ngôn ngữ để xác minh danh tính hoặc bảo mật

Các mức strength có thể xem hai chuỗi khác nhau là tương đương; điều này hữu ích cho **sắp xếp hiển thị** nhưng có thể không phù hợp cho:

- Token, API key, mã phiên, mật khẩu.
- Mã định danh phân biệt hoa/thường.
- Khóa phải so chính xác theo byte/code unit.
- Quy tắc phân quyền hoặc chữ ký dữ liệu.

Với những trường hợp trên, áp dụng phép so sánh đúng theo đặc tả của dữ liệu. `String.equals()` so nội dung chính xác của `String`, nhưng với bí mật nhạy cảm có thể cần cơ chế so sánh thời gian ổn định và bảo vệ dữ liệu chuyên biệt theo giao thức.

### 6.3. `Collator` có trạng thái cấu hình

`setStrength()` và `setDecomposition()` thay đổi cách đối tượng so sánh. Nếu nhiều luồng dùng chung và một luồng thay đổi cấu hình trong khi luồng khác đang so sánh, kết quả có thể không nhất quán. Cách đơn giản là tạo/cấu hình collator riêng cho mỗi công việc hoặc mỗi luồng, hoặc quản lý đồng bộ hóa phù hợp.

`Collator` hỗ trợ `clone()` để tạo bản sao có thể cấu hình độc lập trong những trường hợp cần tránh sửa trực tiếp một đối tượng dùng chung. Đừng thay đổi cấu hình comparator trong lúc đang sắp xếp hoặc lưu phần tử trong bộ sưu tập dựa trên comparator đó.

### 6.4. Chỉ so sánh chuỗi có dữ liệu hợp lệ

Ví dụ API `compare(String, String)` thông thường yêu cầu cả hai chuỗi không `null`. Nếu muốn sắp xếp danh sách có thể chứa null, quyết định quy tắc rõ ràng như `Comparator.nullsFirst(collator)` hoặc `Comparator.nullsLast(collator)`. Đây là chính sách của ứng dụng; bản thân collation không định nghĩa null là một từ hoặc ký tự.

Với Unicode, việc dùng decomposition/strength phù hợp giúp so sánh chữ có dấu, nhưng **không tự thay thế** mọi bài toán tách từ, tìm kiếm gần đúng, bỏ dấu, phiên âm hoặc hỗ trợ quy tắc riêng của sản phẩm.

## 7. Lỗi phổ biến cần tránh

1. **Dùng `String.compareTo()` cho danh sách tên người rồi xem đó là thứ tự bảng chữ cái chuẩn mọi ngôn ngữ.** Nó so theo UTF-16 code unit, không dùng quy tắc collation địa phương.
2. **Gọi `Collator.getInstance()` mà không chủ động chọn `Locale`.** Dùng locale mặc định chỉ khi đó là yêu cầu thực tế.
3. **Tin rằng `compare()` luôn trả chính xác `-1`, `0` hoặc `1`.** Chỉ kiểm tra dấu âm/0/dương; `Integer.signum` khi cần chuẩn hóa.
4. **Cho rằng `compare(a, b) == 0` đồng nghĩa `a.equals(b)`.** Sự tương đương theo strength có thể rộng hơn sự bằng nhau về nội dung.
5. **Dùng `PRIMARY` cho `TreeSet` khóa định danh** mà không lường trước việc khóa khác nội dung có thể bị gộp thành một phần tử.
6. **Hiểu `PRIMARY`/`SECONDARY`/`TERTIARY` như quy tắc bỏ dấu giống nhau ở mọi locale.** Quy tắc phụ thuộc ngôn ngữ và provider.
7. **Quên normalization/decomposition** khi dữ liệu có cả chữ dựng sẵn lẫn chữ + dấu kết hợp.
8. **Thay đổi strength sau khi đã tạo `CollationKey` hoặc đưa comparator vào cấu trúc sắp xếp** mà không tái lập các khóa/cấu trúc tương ứng.
9. **Dùng khóa collation khác cấu hình để so sánh.** Các khóa chỉ có nghĩa nhất quán khi xuất phát từ cùng bộ quy tắc.
10. **Dùng thứ tự collation để thay cho phân tích Unicode, tìm từ, search ranking hoặc phân quyền.** `Collator` giải quyết bài toán so sánh/sắp xếp theo ngôn ngữ, không bao trùm những chức năng khác.

## 8. Tự kiểm tra hiểu biết

- **Câu 1:** Muốn hiển thị danh sách tên tiếng Việt theo quy tắc ngôn ngữ, nên dùng gì?  
  **Đáp án:** `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` rồi dùng làm comparator; kiểm tra quy tắc và dữ liệu JDK của môi trường triển khai.
- **Câu 2:** `collator.compare(a, b) < 0` nghĩa là gì?  
  **Đáp án:** `a` đứng trước `b` theo cấu hình collator hiện tại.
- **Câu 3:** `PRIMARY` có bảo đảm mọi dấu ở mọi ngôn ngữ đều bị bỏ qua?  
  **Đáp án:** Không. Hiệu lực từng dấu phụ thuộc locale và dữ liệu collation.
- **Câu 4:** Hai chuỗi khác `String.equals()` có thể bằng nhau theo `Collator.compare()` không?  
  **Đáp án:** Có, nếu quy tắc strength/decomposition coi chúng tương đương.
- **Câu 5:** Khi nào nên tạo `CollationKey`?  
  **Đáp án:** Khi so sánh lặp lại cùng tập chuỗi và lợi ích lớn hơn chi phí lưu/tạo khóa; các khóa cần chung cấu hình.
- **Câu 6:** Nên dùng `Collator` để xác minh API key không?  
  **Đáp án:** Không. Hãy dùng quy tắc so khớp chính xác và cơ chế bảo mật phù hợp với giao thức.

**Ghi nhớ:** `Collator` phục vụ **so sánh và sắp xếp theo `Locale`**. Chọn strength/decomposition dựa trên cách ứng dụng muốn xem những khác biệt chữ, dấu và biểu diễn Unicode; kiểm tra `compare` theo dấu âm/0/dương; và tách biệt **tương đương ngôn ngữ** khỏi **bằng nhau chính xác** của chuỗi hoặc khóa nghiệp vụ.

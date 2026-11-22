# `String.compareTo()` và thứ tự từ điển theo giá trị `char` trong Java

## 1. `compareTo()` giải quyết vấn đề gì?

Khi cần biết hai chuỗi có **bằng nhau về nội dung** hay không, Java có `String.equals(...)`. Nhưng nhiều bài toán còn cần biết chuỗi nào **đứng trước hoặc đứng sau** chuỗi khác để sắp xếp tên, từ khóa, mã định danh hay danh sách.

Lớp `java.lang.String` cung cấp:

```java
public int compareTo(String anotherString)
```

Đây là phép **so sánh thứ tự từ điển** (*lexicographical comparison*) của hai chuỗi theo các giá trị `char` (đơn vị mã UTF-16) của Java. Phương thức xét từ trái sang phải, tìm vị trí đầu tiên mà hai chuỗi khác nhau. Nếu mọi vị trí chung đều giống nhau, chuỗi ngắn hơn đứng trước.

Ví dụ:

```java
System.out.println("apple".compareTo("banana")); // Số âm
System.out.println("java".compareTo("java"));     // 0
System.out.println("zebra".compareTo("apple"));   // Số dương
```

Các đoạn mã ngắn trong bài chỉ là **mã minh họa bên trong một phương thức**, trừ ví dụ có lớp `public class` và phương thức `main` được trình bày đầy đủ ở phần sau.

Điều quan trọng nhất khi đọc giá trị trả về là **dấu** của số nguyên:

| Giá trị `left.compareTo(right)` | Kết luận |
|---|---|
| Nhỏ hơn `0` | `left` đứng **trước** `right` theo thứ tự của `String` |
| Bằng `0` | Hai chuỗi có cùng dãy giá trị `char` |
| Lớn hơn `0` | `left` đứng **sau** `right` theo thứ tự của `String` |

**Không nên chỉ kiểm tra `compareTo(...) == -1` hoặc `== 1`.** Phương thức có thể trả `-32`, `2`, `5` hoặc một giá trị âm/dương khác. Khi chỉ cần xác định thứ tự, hãy so sánh với **`0`**.

## 2. Cú pháp và hợp đồng API

Cú pháp cơ bản:

```java
String left = "cat";
String right = "car";

int result = left.compareTo(right);
System.out.println(result); // 2
```

- `left` là đối tượng `String` **nhận lời gọi**.
- `right` là đối số `String` **được so sánh với** `left`.
- Kết quả là một `int`; giá trị mang ý nghĩa **thứ tự**, không phải vị trí ký tự trong chuỗi.
- `compareTo` **không sửa** hai chuỗi vì `String` bất biến.
- Đối số phải là một `String` khác `null`. Nếu truyền `null`, lời gọi ném `NullPointerException`. Nếu biến nhận lời gọi là `null`, việc gọi phương thức cũng ném `NullPointerException`.

`String` triển khai giao diện `Comparable<String>`. Vì thế Java có thể dùng `compareTo` làm **thứ tự tự nhiên** (*natural ordering*) của `String`, chẳng hạn khi gọi `Arrays.sort` hoặc `Collections.sort` mà không cung cấp `Comparator` riêng.

### So với `equals(...)` và `==`

```java
String first = new String("Java");
String second = "Java";

System.out.println(first.equals(second));    // true: cùng nội dung
System.out.println(first.compareTo(second)); // 0: cùng nội dung, bằng thứ tự
System.out.println(first == second);         // false: khác tham chiếu
```

Với hai đối tượng `String` khác `null`, điều kiện `a.compareTo(b) == 0` tương đương với `a.equals(b)` về **nội dung chuỗi**. Tuy nhiên:

- Dùng **`equals`** để trả lời “Nội dung có bằng nhau không?”.
- Dùng **`compareTo`** để trả lời “Chuỗi nào đứng trước/sau?”.
- **`==`** trên hai biến `String` kiểm tra cùng tham chiếu đối tượng, không phải thứ tự và cũng không phù hợp để so nội dung.

## 3. Thuật toán so sánh từng `char` từ trái sang phải

Giả sử hai chuỗi lần lượt là `left` và `right`.

**Quy tắc 1 – Tìm vị trí đầu tiên khác nhau.** Java xét từng giá trị `char` theo chỉ số `0`, `1`, `2`, ... đến hết phần chung. Nếu gặp vị trí `k` mà:

```java
left.charAt(k) != right.charAt(k)
```

thì kết quả mang giá trị:

```java
left.charAt(k) - right.charAt(k)
```

Việc trừ ở đây sử dụng giá trị số của hai `char`. Phần **dấu** quyết định thứ tự. Những ký tự nằm sau vị trí khác nhau đầu tiên **không còn ảnh hưởng** đến phép so sánh.

**Quy tắc 2 – Nếu toàn bộ phần chung giống nhau.** Nếu một chuỗi là tiền tố của chuỗi kia (hoặc cả hai giống hệt), kết quả là:

```java
left.length() - right.length()
```

Vì vậy chuỗi ngắn hơn đứng trước, còn chuỗi có cùng độ dài và cùng dãy `char` thì trả `0`.

### Ví dụ: ký tự khác nhau đầu tiên

```java
"cat".compareTo("car")
```

```text
Chỉ số:  0   1   2
Chuỗi 1: c   a   t
Chuỗi 2: c   a   r
                 ^
              Khác đầu tiên

't' = 116, 'r' = 114
Kết quả: 116 - 114 = 2
```

Do đó `"cat".compareTo("car")` trả `2`. Đảo chiều lời gọi:

```java
"car".compareTo("cat") // -2
```

Kết quả âm vì tại vị trí khác nhau đầu tiên, `'r'` nhỏ hơn `'t'`.

### Ví dụ: một chuỗi là tiền tố của chuỗi còn lại

```java
"app".compareTo("apple") // -2
"apple".compareTo("app") // 2
"same".compareTo("same") // 0
```

`"app"` là tiền tố của `"apple"`. Toàn bộ 3 vị trí chung đều giống nhau, nên kết quả là `3 - 5 = -2`, **không phải vị trí chữ cái `l`**.

Với chuỗi rỗng:

```java
"".compareTo("")      // 0
"".compareTo("Java")  // -4
"Java".compareTo("")  // 4
```

Chuỗi rỗng đứng trước mọi chuỗi không rỗng vì độ dài `0` nhỏ hơn độ dài của chúng.

## 4. Thứ tự này dựa trên giá trị `char`, không phải từ điển tiếng Việt

Trong Java, kiểu `char` biểu diễn **một UTF-16 code unit** có giá trị nguyên không dấu từ `0` đến `65535` (`U+0000` đến `U+FFFF` ở mức giá trị đơn vị mã). Thứ tự tự nhiên của `String` được xác định từ dãy giá trị `char` này.

Một số giá trị dễ nhớ:

| Ký tự | Giá trị thập phân của `char` | Ghi chú |
|---|---:|---|
| `'0'` | 48 | Chữ số dạng ký tự |
| `'9'` | 57 | Vẫn là ký tự, không phải số nguyên 9 |
| `'A'` | 65 | Chữ Latin hoa |
| `'Z'` | 90 | Chữ Latin hoa |
| `'a'` | 97 | Chữ Latin thường |
| `'z'` | 122 | Chữ Latin thường |

Vì vậy:

```java
"A".compareTo("a")     // -32: 65 - 97
"a".compareTo("A")     // 32: 97 - 65
"9".compareTo("A")     // -8: 57 - 65
"Z".compareTo("a")     // -7: 90 - 97
```

Không thể kết luận `"apple"` luôn đứng trước `"Banana"` theo cảm nhận của một ngôn ngữ tự nhiên. Theo `String.compareTo`, `"Banana"` đứng trước `"apple"` vì ký tự đầu tiên `'B'` (66) nhỏ hơn `'a'` (97).

### Phân biệt so sánh số và so sánh chuỗi chứa chữ số

```java
System.out.println("10".compareTo("2")); // -1
System.out.println(Integer.compare(10, 2)); // 1
```

Chuỗi `"10"` đứng **trước** `"2"` vì ký tự đầu tiên `'1'` (49) nhỏ hơn `'2'` (50). Ngược lại, số nguyên `10` lớn hơn `2`.

Khi cần sắp xếp các **số**, hãy chuyển đổi sang kiểu số thích hợp và so sánh số; khi cần sắp xếp “tự nhiên” các mã như `file2`, `file10`, cần một `Comparator` có quy tắc tách phần số. `String.compareTo` không tự nhận biết các đoạn số nằm trong văn bản.

## 5. Ví dụ Java 17+ hoàn chỉnh và stdout

Tạo tệp **`StringCompareToDemo.java`** với nội dung:

```java
import java.util.Arrays;

public class StringCompareToDemo {
    public static void main(String[] args) {
        System.out.println("cat/car = " + "cat".compareTo("car"));
        System.out.println("car/cat = " + "car".compareTo("cat"));
        System.out.println("app/apple = " + "app".compareTo("apple"));
        System.out.println("apple/app = " + "apple".compareTo("app"));
        System.out.println("java/java = " + "java".compareTo("java"));
        System.out.println("A/a = " + "A".compareTo("a"));
        System.out.println("10/2 = " + "10".compareTo("2"));

        String[] words = {"banana", "Apple", "apple", "Banana", "app"};
        Arrays.sort(words);
        System.out.println("sorted = " + Arrays.toString(words));

        String supplementary = "😀";
        String bmpPrivateUse = "\uE000";
        System.out.println("UTF16 order sign = "
                + Integer.signum(supplementary.compareTo(bmpPrivateUse)));
        System.out.println("Code point order sign = "
                + Integer.signum(Integer.compare(
                        supplementary.codePointAt(0),
                        bmpPrivateUse.codePointAt(0))));
    }
}
```

Chạy trên JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 StringCompareToDemo.java
java StringCompareToDemo
```

**Stdout:**

```text
cat/car = 2
car/cat = -2
app/apple = -2
apple/app = 2
java/java = 0
A/a = -32
10/2 = -1
sorted = [Apple, Banana, app, apple, banana]
UTF16 order sign = -1
Code point order sign = 1
```

**Giải thích kết quả:**

1. `"cat"` và `"car"` khác nhau đầu tiên ở `'t'` và `'r'`, nên trả `2` và `-2` nếu đảo chiều.
2. `"app"` là tiền tố của `"apple"`, kết quả là chênh lệch độ dài `3 - 5 = -2`.
3. Hai literal `"java"` giống hệt nên trả `0`.
4. `'A'` (65) so với `'a'` (97) cho `-32`; `"10"` so với `"2"` so chữ số đầu `'1'` và `'2'` nên `-1`.
5. `Arrays.sort(words)` sử dụng thứ tự tự nhiên của `String`: các mục bắt đầu bằng chữ hoa được đặt trước các mục bắt đầu bằng chữ thường trong tập dữ liệu này.
6. Hai dòng cuối cho thấy một đặc điểm của UTF-16: so sánh theo đơn vị `char` đôi khi có **thứ tự khác** so với so sánh giá trị Unicode code point. Phần 7 giải thích chi tiết.

## 6. Dùng `compareTo` để sắp xếp và rẽ nhánh

### Kiểm tra thứ tự với `if`

```java
String left = "alpha";
String right = "beta";

int order = left.compareTo(right);

if (order < 0) {
    System.out.println("left đứng trước right");
} else if (order > 0) {
    System.out.println("left đứng sau right");
} else {
    System.out.println("hai chuỗi bằng nhau");
}
```

Phép so sánh với `0` là cách đúng. Nếu chỉ cần biết dấu, có thể dùng `Integer.signum(order)` để quy về `-1`, `0` hoặc `1`.

### Sắp xếp tự nhiên bằng `Arrays.sort`

```java
String[] labels = {"zebra", "Apple", "banana"};
java.util.Arrays.sort(labels);
System.out.println(java.util.Arrays.toString(labels));
// [Apple, banana, zebra]
```

`Arrays.sort` sử dụng `compareTo` của các phần tử nếu mảng có kiểu `String[]` và không chỉ định `Comparator`. Tương tự, `java.util.Collections.sort(list)` sắp xếp một `List<String>` có thể thay đổi được theo thứ tự tự nhiên; `list.sort(null)` cũng dùng thứ tự tự nhiên.

Nếu muốn **đảo ngược** thứ tự:

```java
java.util.Arrays.sort(
        labels,
        java.util.Comparator.reverseOrder()
);
```

Lưu ý `Comparator.reverseOrder()` trên chuỗi cũng đảo thứ tự tự nhiên theo UTF-16; nó không biến phép sắp xếp thành từ điển theo ngôn ngữ người dùng.

### Dùng với collection có thứ tự

`TreeSet<String>` hoặc `TreeMap<String, ...>` có thể sử dụng thứ tự tự nhiên của `String` khi không cung cấp comparator. Quy tắc thứ tự ảnh hưởng cả **cách tìm kiếm và xác định khóa tương đương** trong các cấu trúc ấy.

```java
java.util.Set<String> set = new java.util.TreeSet<>();
set.add("apple");
set.add("Apple");

System.out.println(set); // [Apple, apple]
```

Hai chuỗi này khác nhau theo `compareTo`, nên được giữ thành hai phần tử riêng trong `TreeSet` mặc định.

## 7. Chi tiết Unicode: `char` không luôn tương đương một ký tự nhìn thấy

Đây là điểm quan trọng nhất trong cụm từ **“thứ tự từ điển theo giá trị `char`”**.

`String` của Java dùng các đơn vị mã UTF-16. Một Unicode code point trong vùng BMP thường biểu diễn bằng một `char`; nhưng những code point lớn hơn `U+FFFF` (ví dụ nhiều emoji) dùng **một cặp surrogate** gồm hai `char`.

Ví dụ:

```java
String smile = "😀";

System.out.println(smile.length()); // 2
System.out.println(smile.codePointCount(0, smile.length())); // 1
```

Vì thế `compareTo` so sánh **các code unit UTF-16**, không phải luôn so trực tiếp giá trị nguyên của Unicode code point.

### Ví dụ có thể gây bất ngờ

- Emoji `"😀"` có Unicode code point `U+1F600`, được biểu diễn trong UTF-16 bởi cặp `U+D83D U+DE00`.
- Ký tự ở vị trí `U+E000` là một code point vùng BMP, biểu diễn bởi `char` có giá trị `U+E000`.
- Nếu so code point dưới dạng số nguyên, `U+1F600` **lớn hơn** `U+E000`.
- Nhưng `String.compareTo` xét `char` **đầu tiên**: `U+D83D` **nhỏ hơn** `U+E000`, nên `"😀".compareTo("\uE000")` trả một số **âm**.

Đó là lý do hai dòng cuối ví dụ chạy ở phần 5 cho dấu lần lượt là `-1` và `1`.

**Kết luận về Unicode:** thứ tự của `String.compareTo` là thứ tự xác định, ổn định theo chuỗi đơn vị mã UTF-16, nhưng không nên diễn giải nó là “thứ tự tất cả ký tự Unicode theo code point”, càng không phải thứ tự từ điển theo tiếng Việt hoặc một ngôn ngữ khác.

### Ký tự ghép dấu và chuẩn hóa

Hai chuỗi có thể trông giống nhau nhưng chứa các dãy code point khác nhau. Ví dụ chữ `é` có thể được biểu diễn bằng một code point `U+00E9` hoặc bằng chữ `e` (`U+0065`) cộng dấu sắc kết hợp (`U+0301`).

```java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed));    // false
System.out.println(composed.compareTo(decomposed)); // Số dương
```

Ngay ở đơn vị mã đầu tiên, `U+00E9` (233) lớn hơn `U+0065` (101), nên `compareTo` trả số dương. Nếu nghiệp vụ xem hai cách biểu diễn là cùng văn bản, có thể **chuẩn hóa Unicode** bằng `java.text.Normalizer` trước khi so sánh. Chọn hình thức NFC/NFD tùy yêu cầu và thực hiện nhất quán cho các bên.

## 8. So sánh không phân biệt hoa/thường và so sánh theo ngôn ngữ

### `compareToIgnoreCase` giải quyết bài toán khác

Khi muốn so sánh chuỗi mà **bỏ qua khác biệt chữ hoa/chữ thường** theo quy tắc không phân biệt chữ của Java, có thể dùng:

```java
System.out.println("JAVA".compareToIgnoreCase("java")); // 0
```

Tuy nhiên, `compareToIgnoreCase` **không phải** bộ sắp xếp theo ngôn ngữ tự nhiên. Các phép chuyển đổi hoa/thường phức tạp của Unicode, quy tắc theo ngôn ngữ và dấu có thể cần xử lý riêng. Đừng giả định rằng bỏ qua hoa/thường cũng tự động bỏ dấu tiếng Việt, đồng nhất mọi kiểu chữ hoặc tạo thứ tự chữ cái theo ngôn ngữ.

Để không phân biệt hoa/thường khi sắp xếp:

```java
String[] words = {"b", "A", "a"};
java.util.Arrays.sort(words, String.CASE_INSENSITIVE_ORDER);
```

Comparator này sử dụng quy tắc so sánh không phân biệt hoa/thường của Java. Với những chuỗi khác nhau nhưng được comparator coi là bằng nhau, cần hiểu quy tắc bảo toàn thứ tự hoặc thêm tiêu chí phụ nếu nghiệp vụ yêu cầu kết quả quyết định duy nhất.

### `Collator` dành cho thứ tự theo ngôn ngữ

Đối với tên người, từ tiếng Việt, nhãn giao diện hoặc nội dung cần so đúng quy tắc của một ngôn ngữ, hãy cân nhắc `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

class VietnameseSortingExample {
    public static void main(String[] args) {
        String[] names = {"Đào", "An", "Ân", "Ánh"};
        Collator vi = Collator.getInstance(Locale.forLanguageTag("vi-VN"));

        Arrays.sort(names, vi);
        System.out.println(Arrays.toString(names));
    }
}
```

Đây là chương trình minh họa **độc lập** (lớp không `public` vẫn có thể chạy khi biên dịch vào `VietnameseSortingExample.java`), nhưng bài không khẳng định một dòng stdout cố định: thứ tự chi tiết có thể phụ thuộc dữ liệu đối chiếu ngôn ngữ và cấu hình phiên bản Java. `Collator` có các thiết lập như độ nhạy với dấu, hoa/thường và các cấp so sánh (*strength*) cần chọn theo yêu cầu.

`compareTo` phù hợp khi bạn muốn **thứ tự tự nhiên theo `char` của Java**; `Collator` phù hợp khi yêu cầu là thứ tự **theo ngôn ngữ**. Đây là hai hợp đồng khác nhau.

## 9. `null`, `Comparator` và tính nhất quán

Với biến tham chiếu có thể `null`, gọi `compareTo` trực tiếp không an toàn:

```java
String value = null;
// value.compareTo("Java");  // NullPointerException
// "Java".compareTo(null);   // NullPointerException
```

Nếu bài toán muốn cho phép `null` xuất hiện trong danh sách, hãy định nghĩa quy tắc thứ tự rõ ràng bằng `Comparator`:

```java
java.util.Comparator<String> order =
        java.util.Comparator.nullsFirst(
                java.util.Comparator.naturalOrder()
        );

System.out.println(order.compare(null, "Java")); // Số âm
System.out.println(order.compare("Java", null)); // Số dương
System.out.println(order.compare(null, null));   // 0
```

`naturalOrder()` dùng `String.compareTo`; `nullsFirst(...)` bổ sung quy tắc đặt `null` trước các chuỗi hợp lệ.

Khi viết comparator riêng cho cấu trúc có thứ tự như `TreeSet` hoặc `TreeMap`, hãy chú ý khái niệm **tương đương theo comparator**: hai giá trị mà comparator trả `0` có thể bị xem là một phần tử/khóa tương đương dù `equals` của chúng là `false`. Ví dụ `String.CASE_INSENSITIVE_ORDER.compare("A","a") == 0`, trong khi `"A".equals("a")` là `false`. Với `TreeSet` sử dụng comparator đó, chỉ một trong hai giá trị có thể được lưu làm phần tử đại diện cho nhóm tương đương.

`String.compareTo` tự nhiên **nhất quán với `equals`**, nên không có bất đồng này khi so các `String` bằng comparator tự nhiên mặc định.

## 10. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| `if (a.compareTo(b) == 1)` | Số dương không bắt buộc là `1` | `if (a.compareTo(b) > 0)` |
| Xem `compareTo` là `equals` | `compareTo` trả `int` để xác định thứ tự | Dùng `equals` khi chỉ kiểm tra bằng nhau |
| Nghĩ `"10"` đứng sau `"2"` | Chuỗi được so theo `char` từ trái sang phải | Chuyển sang số hoặc comparator có hiểu số |
| Nghĩ chữ thường luôn đứng trước chữ hoa | `'A'` có giá trị nhỏ hơn `'a'` | Hiểu thứ tự theo UTF-16; hoặc chọn comparator khác |
| Nghĩ so theo `char` luôn là so theo code point | Emoji có thể gồm hai UTF-16 code unit | Hiểu rõ đơn vị mã và quy tắc cần dùng |
| Nghĩ thứ tự theo `compareTo` là thứ tự tiếng Việt | API không dùng quy tắc ngôn ngữ | Dùng `Collator` phù hợp khi cần sắp tên/từ |
| Gọi `text.compareTo(null)` | Đối số `null` gây ngoại lệ | Kiểm tra đầu vào hoặc dùng comparator có xử lý `null` |
| Dùng `==` để kiểm tra từ bằng nhau | `==` so tham chiếu, không so văn bản | Dùng `equals` hoặc `compareTo(...) == 0` |

## 11. Bài tập tự kiểm tra

**Câu 1.** `"dog".compareTo("dot")` trả giá trị gì?

**Đáp án:** `'g'` (103) trừ `'t'` (116) bằng `-13`. Hai ký tự đầu giống nhau, nên xét ký tự thứ ba.

**Câu 2.** `"car".compareTo("carpet")` là âm, bằng không hay dương?

**Đáp án:** **Âm**, cụ thể là `3 - 6 = -3`, vì `"car"` là tiền tố của `"carpet"` và ngắn hơn.

**Câu 3.** Tại sao `"20".compareTo("100")` trả số dương dù số `20` nhỏ hơn số `100`?

**Đáp án:** So sánh ký tự đầu `'2'` (50) với `'1'` (49) cho `+1`; đây là thứ tự chuỗi, không phải so sánh số.

**Câu 4.** Sửa điều kiện sau để kiểm tra `a` đứng trước `b`:

```java
if (a.compareTo(b) == -1) {
    System.out.println("a đứng trước b");
}
```

**Đáp án:** Thay `== -1` bằng `< 0`. Mọi giá trị âm đều có cùng ý nghĩa thứ tự.

**Câu 5.** Hai chuỗi có cùng nội dung nhưng tạo thành hai đối tượng `String` khác nhau thì `compareTo` trả gì?

**Đáp án:** `0`, vì `compareTo` xét dãy `char` của **nội dung**, không xét danh tính đối tượng.

**Câu 6.** Khi sắp xếp tên tiếng Việt hiển thị cho người dùng, có nên mặc định dùng `compareTo` không?

**Đáp án:** Không nên nếu nghiệp vụ đòi thứ tự theo tiếng Việt. `compareTo` chỉ cung cấp thứ tự theo giá trị `char` UTF-16; cần cân nhắc `Collator` và thiết lập ngôn ngữ phù hợp.

## 12. Tổng kết kiến thức

`String.compareTo(other)` duyệt hai chuỗi từ trái sang phải theo **đơn vị mã UTF-16 `char`**. Nếu có vị trí khác nhau đầu tiên, kết quả mang dấu của hiệu hai giá trị `char` tại vị trí ấy; nếu toàn bộ phần chung bằng nhau, kết quả là hiệu độ dài. **Âm / 0 / dương** lần lượt có nghĩa là trước / bằng / sau theo thứ tự tự nhiên của `String`.

Quy tắc này giúp Java sắp xếp chuỗi một cách xác định, nhưng **không tự hiểu số, không tự bỏ qua hoa/thường, không tuân theo thứ tự tiếng Việt**, và có khác biệt đáng chú ý với thứ tự Unicode code point khi gặp ký tự bổ trợ. Hãy chọn `equals` để kiểm tra nội dung, `compareTo` hoặc comparator tự nhiên để sắp theo UTF-16, và `Collator` khi cần thứ tự từ điển của ngôn ngữ con người.

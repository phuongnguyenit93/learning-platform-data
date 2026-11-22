# Kiểm thử split giữ phần rỗng và splitWithDelimiters trong Java

## 1. Bài toán và mục tiêu kiểm thử

Trong Java, `String.split(regex)` và `String.split(regex, limit)` dùng **biểu thức chính quy** để phân tách chuỗi. Kết quả là `String[]` gồm các phần văn bản nằm giữa những lần regex khớp. Một nguồn lỗi phổ biến là tưởng rằng kết quả luôn giữ mọi trường rỗng hoặc mọi dấu phân cách.

Ví dụ dữ liệu giống CSV đơn giản:

```text
name,age,city,
```

Dấu phẩy cuối có thể biểu thị một trường cuối **rỗng**. Nếu viết:

```java
String[] fields = "name,age,city,".split(",");
```

thì mặc định `split` **bỏ phần tử rỗng ở cuối**, khiến kết quả chỉ còn `["name", "age", "city"]`. Nếu cần xác nhận chính xác số trường, phải chọn `limit` phù hợp.

Từ **Java 21**, Java còn cung cấp `String.splitWithDelimiters(regex, limit)` và `Pattern.splitWithDelimiters(input, limit)` để giữ **cả chuỗi khớp với delimiter** xen giữa các trường. Đây là một API khác với `split`: có ích khi cần phân tích, kiểm thử hoặc tái dựng dữ liệu có dấu phân cách. **Java 17 không có `splitWithDelimiters`**; các ví dụ sử dụng API này yêu cầu JDK 21 trở lên.

Sau bài này, bạn sẽ biết kiểm thử: các phần rỗng **ở đầu, giữa và cuối**; các giá trị `limit` bằng 0, âm và dương; delimiter lặp; ký tự đặc biệt của regex; delimiter khớp độ dài 0; và sự khác nhau giữa `split` với `splitWithDelimiters`.

## 2. Cơ chế split(regex, limit)

Hai overload của `String`:

```java
String[] split(String regex)
String[] split(String regex, int limit)
```

`split(regex)` tương đương `split(regex, 0)`. Giá trị `limit` quyết định **số lần áp dụng delimiter và việc giữ các chuỗi rỗng cuối mảng**.

| `limit` | Số lần phân tách | Phần tử rỗng ở cuối |
| --- | --- | --- |
| `0` (mặc định) | Áp dụng regex nhiều lần nhất có thể | **Bỏ** những phần tử `""` liên tiếp ở cuối |
| Số âm, ví dụ `-1` | Áp dụng regex nhiều lần nhất có thể | **Giữ** các phần tử `""` ở cuối |
| Số dương `n` | Áp dụng regex tối đa `n - 1` lần, tối đa `n` phần tử | Giữ phần cuối còn lại, kể cả `""` khi có |

Đối số `limit` **không** phải số ký tự và **không** phải số dấu phân cách xuất hiện trong chuỗi. `limit = 2` nghĩa là chỉ chia tại tối đa **một** lần khớp delimiter; phần còn lại trở thành phần tử cuối.

```java
String text = "a,b,,";

System.out.println(java.util.Arrays.toString(text.split(",")));      // [a, b]
System.out.println(java.util.Arrays.toString(text.split(",", -1)));  // [a, b, , ]
System.out.println(java.util.Arrays.toString(text.split(",", 2)));   // [a, b,,]
```

`Arrays.toString` không đặt dấu nháy quanh từng giá trị, vì vậy các chuỗi rỗng nhìn dễ nhầm. Khi viết test, hãy dùng `Arrays.equals` với mảng kỳ vọng hoặc hàm hiển thị có dấu nháy như ở phần chương trình đầy đủ.

### Phân biệt ba loại trường rỗng

- **Ở đầu:** `",a"` có một delimiter khớp độ dài dương ngay tại vị trí 0 → trường rỗng `""` ở đầu **được giữ**, kể cả `limit = 0`.
- **Ở giữa:** `"a,,b"` có hai dấu phẩy kề nhau → trường rỗng `""` nằm giữa hai delimiter **được giữ**.
- **Ở cuối:** `"a,b,"` có dấu phẩy cuối → `limit = 0` bỏ phần tử rỗng cuối; `limit = -1` giữ.

Bảng ví dụ cụ thể:

| Dữ liệu | Lệnh | Kết quả chính xác |
| --- | --- | --- |
| `"a,b,,"` | `split(",")` | `["a", "b"]` |
| `"a,b,,"` | `split(",", 0)` | `["a", "b"]` |
| `"a,b,,"` | `split(",", -1)` | `["a", "b", "", ""]` |
| `"a,b,,"` | `split(",", 2)` | `["a", "b,,"]` |
| `",a,"` | `split(",")` | `["", "a"]` |
| `",a,"` | `split(",", -1)` | `["", "a", ""]` |
| `"a,,b,"` | `split(",", -1)` | `["a", "", "b", ""]` |
| `""` | `split(",", -1)` | `[""]` |

**Cẩn thận với chuỗi rỗng:** Khi input hoàn toàn rỗng và regex như `","` không khớp, kết quả chứa **một phần tử chuỗi rỗng** `[""]` chứ không phải mảng độ dài 0. Vì thế nên khẳng định cả độ dài và nội dung phần tử trong những test này.

## 3. splitWithDelimiters hoạt động thế nào?

Từ Java 21:

```java
String[] splitWithDelimiters(String regex, int limit)
```

Phương thức này cũng dùng regex làm dấu phân cách, nhưng thay vì bỏ delimiter như `split`, nó trả cả **các đoạn văn bản và các delimiter khớp regex**, đúng thứ tự xuất hiện.

Ví dụ:

```java
String input = "boo:::and::foo";
String[] parts = input.splitWithDelimiters(":+", -1);

// ["boo", ":::", "and", "::", "foo"]
```

`":+"` là regex khớp **một hoặc nhiều** dấu hai chấm liền kề, vì vậy `":::"` và `"::"` được giữ như hai delimiter nguyên vẹn. Chúng không bị phân tách thành từng dấu `":"`.

Kết quả thường có dạng:

```text
[phần văn bản, delimiter, phần văn bản, delimiter, phần văn bản]
```

Dấu phân cách cuối được giữ nếu có, và `limit = -1` giữ cả phần văn bản rỗng ở cuối. Ví dụ:

```java
String[] parts = "a,,b,".splitWithDelimiters(",", -1);

// ["a", ",", "", ",", "b", ",", ""]
```

Kết quả phản ánh chính xác cả dấu phẩy liên tiếp và dấu phẩy cuối.

### Bảng so sánh split và splitWithDelimiters

Với chuỗi `"a,,b,"` và regex `","`:

| Phương thức | `limit` | Kết quả |
| --- | --- | --- |
| `split` | `0` | `["a", "", "b"]` |
| `split` | `-1` | `["a", "", "b", ""]` |
| `splitWithDelimiters` | `0` | `["a", ",", "", ",", "b", ","]` |
| `splitWithDelimiters` | `-1` | `["a", ",", "", ",", "b", ",", ""]` |
| `splitWithDelimiters` | `2` | `["a", ",", ",b,"]` |
| `splitWithDelimiters` | `1` | `["a,,b,"]` |

Với `limit = 0`, `splitWithDelimiters` **loại các chuỗi rỗng ở cuối mảng**, dù đó là trường hay delimiter rỗng. Các dấu phân cách có nội dung (ví dụ `","`) vẫn xuất hiện trong mảng.

### limit dương của splitWithDelimiters

Giả sử `limit = n > 0`: regex được dùng để chia tối đa `n - 1` lần, vì vậy kết quả có **không quá `2n - 1` phần tử**. Phần cuối được giữ nguyên sau delimiter cuối đã dùng để chia.

```java
System.out.println(
    java.util.Arrays.toString("boo:::and::foo".splitWithDelimiters(":+", 2))
);
// [boo, :::, and::foo]
```

Ở ví dụ này, chỉ delimiter `":::"` đầu tiên được sử dụng; `"and::foo"` là phần chưa chia. Không suy ra rằng `limit = 2` sẽ giữ đúng 2 phần tử: mảng có thể dài 3 vì nó chứa cả delimiter.

Có một API tương đương trên `java.util.regex.Pattern`:

```java
java.util.regex.Pattern pattern =
        java.util.regex.Pattern.compile(":+");

String[] parts = pattern.splitWithDelimiters("boo:::and::foo", -1);
```

Cách dùng `Pattern` phù hợp khi cùng một regex được sử dụng nhiều lần hoặc cần các flags như `CASE_INSENSITIVE`. Cả `Pattern.splitWithDelimiters` và `String.splitWithDelimiters` đều được giới thiệu từ Java 21.

## 4. Trường hợp delimiter ở đầu, ở cuối và liên tiếp

Delimiter **khớp độ dài dương ở đầu input** tạo phần tử `""` đầu tiên:

```java
String[] result = ",a,".splitWithDelimiters(",", -1);

// ["", ",", "a", ",", ""]
```

Với `split(",", -1)`, kết quả tương ứng chỉ còn `["", "a", ""]` vì các delimiter không được đưa vào mảng.

Nếu có nhiều delimiter liền nhau, vẫn phải xem regex khớp như thế nào:

```java
String a = "a:::b";

System.out.println(java.util.Arrays.toString(
        a.splitWithDelimiters(":", -1)));
// [a, :, , :, , :, b]

System.out.println(java.util.Arrays.toString(
        a.splitWithDelimiters(":+", -1)));
// [a, :::, b]
```

Với regex `":"`, có các đoạn rỗng giữa những delimiter kề nhau. Với regex `":+"`, cả chuỗi `":::"` là một delimiter duy nhất và **không còn các đoạn rỗng ở giữa các lần khớp** đó.

Nếu yêu cầu nghiệp vụ là phân tách chính xác mỗi dấu phẩy, đừng vô tình dùng regex `",+"` vì nó gộp các dấu phẩy kề nhau và sẽ che mất các cột rỗng. Hãy khẳng định trong test rằng số lượng trường và vị trí trường rỗng đúng như định dạng quy định.

## 5. Regex có ý nghĩa đặc biệt và zero-width matches

`split` và `splitWithDelimiters` đều nhận **regex**, không phải ký tự phân cách literal. Dấu chấm `.` trong regex nghĩa là “một ký tự bất kỳ” (theo quy tắc của regex), không phải dấu chấm thật.

Ví dụ muốn chia theo dấu chấm literal:

```java
String input = "a.b.";
String[] items = input.split("\\.", -1);

// ["a", "b", ""]
```

`"\\."` là cách escape regex `\.` trong **Java string literal**. Nếu dấu phân cách đến từ người dùng và cần hiểu hoàn toàn như văn bản literal, có thể dùng:

```java
String delimiter = ".";
String regex = java.util.regex.Pattern.quote(delimiter);
String[] items = "a.b.".split(regex, -1);
```

Khi regex là `"\\s+"`, mỗi chuỗi gồm một hay nhiều ký tự whitespace được xem là **một delimiter**. Với `splitWithDelimiters`, toàn bộ chuỗi whitespace đã khớp sẽ nằm trong phần tử delimiter; điều này hữu ích khi cần bảo toàn khoảng trắng để phân tích lại dữ liệu gốc.

### Regex khớp độ dài bằng 0

Các regex như lookahead `(?=b)` hay word boundary `\\b` có thể khớp tại một vị trí **không tiêu thụ ký tự**. Quy tắc Java có một ngoại lệ quan trọng:

- Khi delimiter có **độ dài dương** và khớp ở đầu input, Java thêm trường rỗng `""` ở đầu.
- Khi delimiter khớp **độ dài 0 ở đầu input**, Java **không thêm** trường rỗng đầu, và `splitWithDelimiters` cũng không thêm delimiter rỗng đầu tương ứng.

Ví dụ trên Java 21+:

```java
String[] positive = "abc".splitWithDelimiters("a", -1);
// ["", "a", "bc"]

String[] zeroWidthAtStart =
        "abc".splitWithDelimiters("(?=a)", -1);
// ["abc"]
```

`(?=a)` là positive lookahead khớp vị trí trước chữ `a` mà không tiêu thụ chữ `a`. Do đó nó không tạo delimiter có nội dung ở vị trí 0.

Ở cuối chuỗi, regex `$` cũng có thể tạo match độ dài 0:

```java
String[] keep = "abc".splitWithDelimiters("$", -1);
// ["abc", "", ""]

String[] dropTrailing = "abc".splitWithDelimiters("$", 0);
// ["abc"]
```

Hai phần tử cuối của `keep` lần lượt là delimiter rỗng và phần văn bản rỗng cuối. Với `limit = 0`, các phần tử rỗng cuối bị loại. Regex khớp độ dài 0 khá tinh tế: hãy kiểm thử với đầu/cuối chuỗi và input rỗng, tránh giả định rằng mọi match đều lấy mất một ký tự.

## 6. Chương trình Java 21+ kiểm thử chính xác phần tử rỗng

Để kết quả dễ kiểm chứng, ví dụ sau in **dấu nháy kép** quanh từng phần tử, thay vì dùng `Arrays.toString` vốn khiến chuỗi rỗng khó phân biệt.

Lưu thành tệp `SplitEmptyAndDelimitersDemo.java` bằng UTF-8:

```java
import java.util.StringJoiner;
import java.util.regex.Pattern;

public class SplitEmptyAndDelimitersDemo {
    private static String show(String[] items) {
        StringJoiner output = new StringJoiner(", ", "[", "]");
        for (String item : items) {
            String visible = item.replace("\\", "\\\\")
                                 .replace("\n", "\\n");
            output.add("\"" + visible + "\"");
        }
        return output.toString();
    }

    private static void print(String label, String[] items) {
        System.out.println(label + " = " + show(items));
    }

    public static void main(String[] args) {
        String csv = "a,b,,";
        print("split default", csv.split(","));
        print("split zero", csv.split(",", 0));
        print("split minus", csv.split(",", -1));
        print("split two", csv.split(",", 2));

        print("initial default", ",a,".split(","));
        print("initial minus", ",a,".split(",", -1));
        print("middle empty", "a,,b,".split(",", -1));
        print("empty input", "".split(",", -1));
        print("literal dot", "a.b.".split("\\.", -1));

        String repeated = "a,,b,";
        print("with -1", repeated.splitWithDelimiters(",", -1));
        print("with 0", repeated.splitWithDelimiters(",", 0));
        print("with 2", repeated.splitWithDelimiters(",", 2));
        print("with 1", repeated.splitWithDelimiters(",", 1));

        print("positive start",
                "abc".splitWithDelimiters("a", -1));
        print("zero width start",
                "abc".splitWithDelimiters("(?=a)", -1));

        Pattern runsOfColon = Pattern.compile(":+");
        print("colon all",
                runsOfColon.splitWithDelimiters("boo:::and::foo", -1));
        print("colon limit 2",
                runsOfColon.splitWithDelimiters("boo:::and::foo", 2));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac -encoding UTF-8 SplitEmptyAndDelimitersDemo.java
java SplitEmptyAndDelimitersDemo
```

Kết quả chuẩn, trong đó `""` biểu thị một phần tử chuỗi rỗng:

```text
split default = ["a", "b"]
split zero = ["a", "b"]
split minus = ["a", "b", "", ""]
split two = ["a", "b,,"]
initial default = ["", "a"]
initial minus = ["", "a", ""]
middle empty = ["a", "", "b", ""]
empty input = [""]
literal dot = ["a", "b", ""]
with -1 = ["a", ",", "", ",", "b", ",", ""]
with 0 = ["a", ",", "", ",", "b", ","]
with 2 = ["a", ",", ",b,"]
with 1 = ["a,,b,"]
positive start = ["", "a", "bc"]
zero width start = ["abc"]
colon all = ["boo", ":::", "and", "::", "foo"]
colon limit 2 = ["boo", ":::", "and::foo"]
```

Chương trình xác nhận đồng thời bốn điểm: `split(regex)` bằng `split(regex, 0)`; limit âm giữ phần rỗng cuối; `splitWithDelimiters` giữ cả các delimiter đã khớp; và các match zero-width ở đầu không tạo phần tử rỗng mở đầu.

## 7. Viết assertion thay vì chỉ nhìn output

Khi kiểm thử tự động, nên so sánh **mảng theo giá trị và đúng thứ tự**, gồm cả chuỗi rỗng. Nếu dùng JUnit 5, có thể sử dụng `assertArrayEquals(expected, actual)`. Với Java thuần, `Arrays.equals` cũng đủ để minh họa:

```java
import java.util.Arrays;

public class SplitAssertions {
    private static void check(String name, String[] expected, String[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(name + ": expected "
                    + Arrays.toString(expected)
                    + " but got " + Arrays.toString(actual));
        }
        System.out.println(name + " = PASS");
    }

    public static void main(String[] args) {
        check("trailing fields",
                new String[] {"a", "b", "", ""},
                "a,b,,".split(",", -1));

        check("default removes trailing",
                new String[] {"a", "b"},
                "a,b,,".split(","));

        check("middle empty",
                new String[] {"a", "", "b"},
                "a,,b,".split(","));

        check("retain delimiters",
                new String[] {"a", ",", "", ",", "b", ",", ""},
                "a,,b,".splitWithDelimiters(",", -1));

        check("limit two",
                new String[] {"a", ",", ",b,"},
                "a,,b,".splitWithDelimiters(",", 2));

        check("empty source",
                new String[] {""},
                "".split(",", -1));
    }
}
```

Chạy bằng JDK 21+:

```bash
javac -encoding UTF-8 SplitAssertions.java
java SplitAssertions
```

Output:

```text
trailing fields = PASS
default removes trailing = PASS
middle empty = PASS
retain delimiters = PASS
limit two = PASS
empty source = PASS
```

Đây là một chương trình kiểm thử độc lập, không cần cài JUnit. Điểm cần giữ khi chuyển sang JUnit là **assert cả toàn bộ mảng**, không chỉ kiểm tra `array.length`. Hai mảng có cùng số phần tử nhưng vị trí phần tử rỗng khác nhau vẫn là dữ liệu khác nhau.

Nếu ứng dụng phải hỗ trợ Java 17, có thể giữ các assertion về `split` trên Java 17; nhưng phải bỏ hoặc thay cách kiểm thử `splitWithDelimiters` vì API này chưa tồn tại ở bản JDK đó.

## 8. Bộ test biên nên có trong dự án

Đối với code dùng `split` để parse một định dạng đơn giản, nên có các nhóm kiểm thử song song:

| Trường hợp | Input và regex điển hình | Điều cần assert |
| --- | --- | --- |
| Không có delimiter | `"abc"`, `","` | Chỉ một phần tử `"abc"` |
| Input rỗng | `""`, `","` | `[""]` nếu regex không khớp |
| Delimiter đầu | `",abc"`, `","` | Phần rỗng đầu được giữ nếu match có độ dài dương |
| Delimiter cuối | `"abc,"`, `","` | So sánh khác biệt `limit = 0` và `-1` |
| Hai delimiter liên tiếp | `"a,,b"`, `","` | Có trường rỗng giữa |
| Nhiều delimiter cuối | `"a,b,,"`, `","` | `limit = -1` giữ đủ các trường rỗng cuối |
| Limit dương | `"a,b,c"`, `","`, `2` | Phần cuối `"b,c"` không bị chia tiếp |
| Regex có metacharacter | `"a.b"`, dấu chấm literal | Dùng `"\\."` hoặc `Pattern.quote(".")` |
| Regex gộp delimiter | `"a:::b"`, `":+"` | Delimiter `":::"` giữ nguyên thành một phần tử khi dùng `splitWithDelimiters` |
| Lookahead đầu | `"abc"`, `"(?=a)"` | Không tạo phần rỗng đầu |
| Regex cuối chuỗi | `"abc"`, `"$"` | Kiểm tra chuỗi rỗng cuối theo `limit` |
| Unicode | Chuỗi chứa ký tự đa đơn vị UTF-16 | Regex và kỳ vọng không vô tình tách surrogate pair |
| Delimiter không hợp lệ | `"a[b"` với regex `"["` | Xác minh `PatternSyntaxException` được xử lý tại ranh giới nhập liệu |

Khi kiểm thử dữ liệu có tính nghiệp vụ, hãy xác định rõ liệu “một dấu phân cách cuối” biểu thị **một trường rỗng hợp lệ**, một dòng không hợp lệ hay chỉ là dấu kết thúc bản ghi. Java `split` không thể tự quyết định chính sách đó.

**Đặc biệt với CSV thật:** `split(",")` hoặc `split(",", -1)` **không phải CSV parser hoàn chỉnh**. CSV có thể cho phép dấu phẩy bên trong trường được đặt dấu nháy, dấu nháy escape và newline trong trường. Khi dữ liệu có các quy tắc đó, hãy dùng parser CSV tương thích định dạng, sau đó kiểm thử các trường rỗng theo hợp đồng parser. `split` chỉ phù hợp khi delimiter là đơn giản và không cần ngữ cảnh trích dẫn.

## 9. Tái dựng chuỗi và kiểm tra delimiter

Với `splitWithDelimiters(regex, -1)`, kết quả giữ mọi chuỗi văn bản và delimiter theo thứ tự, nên với những regex và input phù hợp, ghép chúng lại có thể tái dựng nguyên văn input:

```java
String original = "left==right;next";
String[] tokens = original.splitWithDelimiters("==|;", -1);

String restored = String.join("", tokens);

System.out.println(original.equals(restored)); // true
```

Kiểu kiểm tra này hữu ích khi viết tokenizer nhẹ có yêu cầu không mất thông tin. Nó kiểm tra **khả năng bảo toàn văn bản**, nhưng chưa chứng minh việc phân loại token phù hợp ngữ nghĩa nghiệp vụ: vẫn cần assert các phần tử tương ứng và delimiter cụ thể.

Một test tốt có thể kiểm tra cả hai điều:

```java
String original = "a,,b,";
String[] tokens = original.splitWithDelimiters(",", -1);

boolean sameContent = String.join("", tokens).equals(original);
boolean sameStructure = java.util.Arrays.equals(tokens,
        new String[] {"a", ",", "", ",", "b", ",", ""});

System.out.println(sameContent);   // true
System.out.println(sameStructure); // true
```

Nếu cần tách **token có loại** (text, delimiter, vị trí bắt đầu/kết thúc, whitespace), `splitWithDelimiters` chỉ cung cấp chuỗi kết quả, không cung cấp offset; khi cần vị trí match, dùng `Matcher.find()` và `start()/end()` để thu thập vị trí một cách tường minh.

## 10. Lỗi phổ biến

1. **Dùng `split(",")` để đếm số cột có thể rỗng ở cuối.** Overload mặc định loại bỏ rỗng cuối. Dùng `split(",", -1)` khi định dạng coi chúng là cột.
2. **Tin vào `Arrays.toString` để đếm dấu rỗng bằng mắt.** Hãy in có dấu nháy hoặc dùng `assertArrayEquals`.
3. **Dùng `limit = 1` rồi mong có hai phần.** Limit dương `1` cho tối đa một phần, thường là nguyên input.
4. **Nghĩ `limit` của `splitWithDelimiters` cũng là số phần tử tối đa.** Với limit dương `n`, mảng có thể dài tới `2n - 1` do giữ delimiter.
5. **Nhầm regex với literal.** Dấu `.` hoặc `|` có ý nghĩa regex; dùng escape đúng hoặc `Pattern.quote`.
6. **Nhầm delimiter lặp thành nhiều trường rỗng dù regex là `,+`.** Regex có thể gộp cả đoạn delimiter thành một match.
7. **Nhầm `splitWithDelimiters` với capturing group của `split`.** Java `split` không tự đưa nhóm capture vào kết quả; muốn giữ delimiter dùng API mới từ Java 21 hoặc tự quét `Matcher`.
8. **Quên match zero-width ở đầu.** Quy tắc này không sinh phần rỗng dẫn đầu như match có độ dài dương.
9. **Bỏ qua `PatternSyntaxException`.** Nếu regex được nhập động, cần có chính sách validate/parse rõ ràng.
10. **Viết `splitWithDelimiters` rồi chạy JDK 17.** Phương thức không tồn tại ở Java 17; cần Java 21+ hoặc giải pháp tương thích phiên bản cũ.
11. **Dùng split cho CSV/định dạng có quote phức tạp.** Những trường chứa delimiter hoặc xuống dòng được quote phải được parser tương thích xử lý.

## 11. Câu hỏi và bài tập tự luyện

**Bài 1.** Với `"x,y,,"`, hai lệnh dưới đây khác nhau thế nào?

```java
"x,y,,".split(",");
"x,y,,".split(",", -1);
```

**Đáp án:** Lệnh đầu trả `["x", "y"]`; lệnh sau trả `["x", "y", "", ""]`. Hai phần cuối biểu thị hai trường rỗng do hai dấu phẩy cuối.

**Bài 2.** Với `"a,,b,".splitWithDelimiters(",", 2)`, có bao nhiêu phần tử?

**Đáp án:** Ba phần tử: `["a", ",", ",b,"]`. `limit = 2` chỉ cho áp dụng delimiter tối đa một lần rồi giữ nguyên phần còn lại.

**Bài 3.** `"a::b".splitWithDelimiters(":+", -1)` cho gì?

**Đáp án:** `["a", "::", "b"]` vì regex `:+` khớp hai dấu hai chấm như **một** delimiter.

**Bài 4.** Vì sao `"abc".splitWithDelimiters("(?=a)", -1)` không bắt đầu bằng `""`?

**Đáp án:** `(?=a)` là match độ dài 0 ở vị trí đầu; API không thêm phần rỗng đầu hay delimiter rỗng đầu cho trường hợp đó.

**Bài 5.** Java 17 có gọi trực tiếp `String.splitWithDelimiters` được không?

**Đáp án:** Không. Phương thức được giới thiệu từ Java 21. Trên Java 17, dùng `split` khi không cần delimiter hoặc tự quét bằng `Pattern`/`Matcher` nếu cần vừa giữ văn bản vừa giữ delimiter.

## Tài liệu tham khảo

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): hai overload `split` và `splitWithDelimiters`, định nghĩa `limit`, quy tắc match zero-width.
- [Java SE 21 — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html): `split(input, limit)`, `splitWithDelimiters(input, limit)` và các ví dụ regex.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): hợp đồng `split` trên bản Java trước khi `splitWithDelimiters` xuất hiện.

**Ghi nhớ:** Nếu cần bảo toàn các **trường rỗng cuối**, dùng `split(regex, -1)`. Nếu cần bảo toàn cả **delimiter** và có JDK 21+, dùng `splitWithDelimiters(regex, -1)`; khi kiểm thử phải xác nhận cả nội dung, độ dài và thứ tự từng phần tử của mảng.
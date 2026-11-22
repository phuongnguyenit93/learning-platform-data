# Pattern.splitAsStream() và xử lý kết quả lười trong Java

## 1. Mục tiêu và ý tưởng cốt lõi

Khi cần tách một chuỗi bằng **biểu thức chính quy (regex)** rồi lọc, chuyển đổi hoặc lấy một vài phần tử đầu tiên, Java cung cấp `Pattern.splitAsStream(CharSequence input)` trong `java.util.regex.Pattern` (từ Java 8). Phương thức trả về `Stream<String>` chứa các đoạn nằm giữa những lần khớp của regex.

Thay vì tạo trước một mảng toàn bộ token như `String.split(regex)`, API này cho phép kết nối ngay với các thao tác Stream:

- **Intermediate operations** như `map`, `filter`, `distinct`, `limit`, `skip` thường xử lý lười: xây dựng pipeline chưa khiến các token được duyệt.
- **Terminal operations** như `toList` (Java 16+), `collect`, `findFirst`, `anyMatch`, `forEach` mới kích hoạt việc duyệt.
- Với terminal operation có thể **dừng sớm** (ví dụ `findFirst` hoặc `limit(2).toList()`), pipeline có thể tránh xử lý những phần tử còn lại. Đây là lợi ích chính của sự lười (laziness); không nên hiểu rằng mọi trường hợp đều tiết kiệm bộ nhớ hoặc thời gian.

Cú pháp cơ bản:

```java
Pattern delimiter = Pattern.compile("\\s*,\\s*"); // Dấu phẩy, cho phép khoảng trắng hai bên
Stream<String> tokens = delimiter.splitAsStream("java, spring, kafka");
// Đến đây ta mới có pipeline; terminal operation bên dưới bắt đầu tiêu thụ stream.
List<String> result = tokens.filter(s -> !s.isBlank()).toList();
```

Regex `\\s*,\\s*` khớp dấu phẩy cùng khoảng trắng xung quanh. Kết quả là `[java, spring, kafka]`. Regex là **dấu phân tách**, không phải regex mô tả nội dung token; những phần khớp với dấu phân tách không xuất hiện trong stream.

## 2. Cách splitAsStream hoạt động

Với `Pattern.compile(",").splitAsStream("a,b,c")`, biểu thức `,` tìm hai vị trí phân tách và stream phát ra lần lượt `"a"`, `"b"`, `"c"`. Thứ tự các token là thứ tự trong input.

| Input | Regex | Các token theo thứ tự | Ý nghĩa |
| --- | --- | --- | --- |
| `"a,b,c"` | `","` | `["a", "b", "c"]` | Tách thông thường. |
| `"a,,b"` | `","` | `["a", "", "b"]` | Giữ token rỗng **ở giữa**. |
| `"a,b,,"` | `","` | `["a", "b"]` | Bỏ các token rỗng **ở cuối**. |
| `",a,b"` | `","` | `["", "a", "b"]` | Dấu phân tách có độ dài dương ở đầu tạo token rỗng đầu tiên. |
| `"abc"` | `","` | `["abc"]` | Không tìm thấy dấu phân tách: một token là toàn bộ input. |
| `"abc"` | `"(?=a)"` | `["abc"]` | Khớp độ dài 0 ngay đầu chuỗi **không** tạo token rỗng đầu tiên. |

**Quy tắc quan trọng:** `splitAsStream` loại bỏ các chuỗi rỗng ở cuối, tương tự cách tách với `limit = 0` của `Pattern.split(input, 0)`. Không được lẫn token rỗng ở giữa với token rỗng cuối. Nếu dữ liệu cần bảo toàn số cột trống ở cuối (chẳng hạn record phân cách bằng dấu `|`), hãy dùng `pattern.split(input, -1)`.

Các regex có độ dài khớp bằng 0 (zero-width match), ví dụ lookahead `(?=a)`, cần được kiểm tra cẩn thận khi dùng làm dấu phân tách. Khớp rỗng ở đầu khác khớp ký tự thật ở đầu; đặc điểm này ảnh hưởng số token.

**Không có tham số `limit` trong `splitAsStream`.** `stream.limit(n)` là giới hạn **số token được tiêu thụ**, còn `Pattern.split(input, n)` giới hạn **số lần áp dụng dấu phân tách** và để phần dư trong phần tử cuối. Ví dụ:

```java
Pattern p = Pattern.compile(",");
System.out.println(p.splitAsStream("a,b,c,d").limit(2).toList());
// [a, b]
System.out.println(Arrays.toString(p.split("a,b,c,d", 2)));
// [a, b,c,d]
```

Hai kết quả khác nhau; khi muốn giữ toàn bộ phần còn lại vào cột cuối, hãy chọn `split(input, n)`.

## 3. Ví dụ Java 17+ chạy độc lập

Tạo file **`SplitAsStreamDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class SplitAsStreamDemo {
    private static final Pattern COMMA = Pattern.compile("\\s*,\\s*");

    public static void main(String[] args) {
        String input = "java, spring,, kafka, ";

        // toList() tiêu thụ toàn bộ stream và tạo danh sách kết quả.
        List<String> raw = COMMA.splitAsStream(input).toList();
        System.out.println("So token: " + raw.size());
        System.out.println("Token: " + raw.stream()
                .map(s -> "[" + s + "]")
                .collect(Collectors.joining(" ")));

        // Bỏ token rỗng, viết hoa, rồi mới gom thành List.
        List<String> normalized = COMMA.splitAsStream(input)
                .filter(s -> !s.isBlank())
                .map(String::toUpperCase)
                .toList();
        System.out.println("Da loc: " + normalized);

        // Chỉ lấy tối đa hai token đầu tiên.
        List<String> firstTwo = COMMA.splitAsStream(input).limit(2).toList();
        System.out.println("Hai token dau: " + firstTwo);

        // findFirst() có thể dừng ngay khi gặp token phù hợp.
        String firstLong = COMMA.splitAsStream(input)
                .filter(s -> s.length() >= 5)
                .findFirst()
                .orElse("<khong co>");
        System.out.println("Token dai dau tien: " + firstLong);

        // Token "NaN" nằm sau hai giá trị cần lấy, không bị parse.
        List<Integer> numbers = Pattern.compile(",")
                .splitAsStream("10,20,NaN")
                .map(Integer::parseInt)
                .limit(2)
                .toList();
        System.out.println("Chi lay hai so: " + numbers);

        // Cần giữ các trường trống ở cuối? Dùng split(input, -1).
        System.out.println("split(..., -1): "
                + Arrays.toString(COMMA.split(input, -1)));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 SplitAsStreamDemo.java
java SplitAsStreamDemo
```

Kết quả stdout (đã kiểm tra bằng Java với chế độ biên dịch Java 17):

```text
So token: 4
Token: [java] [spring] [] [kafka]
Da loc: [JAVA, SPRING, KAFKA]
Hai token dau: [java, spring]
Token dai dau tien: spring
Chi lay hai so: [10, 20]
split(..., -1): [java, spring, , kafka, ]
```

Giải thích:

1. Input có hai dấu phẩy liên tiếp nên có một token rỗng **ở giữa**. Dấu phẩy cuối tạo phần rỗng **ở cuối** và phần này bị `splitAsStream` bỏ đi: còn bốn token.
2. `filter(s -> !s.isBlank())` bỏ chuỗi rỗng hoặc toàn khoảng trắng. `map(String::toUpperCase)` biến đổi token còn lại. Thứ tự `filter` trước `map` cũng giúp không biến đổi các token sẽ bị loại.
3. `limit(2)` chỉ cần hai phần tử đầu; `findFirst()` dừng sau khi tìm thấy `spring` có độ dài từ năm ký tự.
4. `map(Integer::parseInt).limit(2)` chỉ chuyển `10` và `20` thành số; vì chưa yêu cầu phần tử thứ ba nên chuỗi `NaN` không gây `NumberFormatException`. Nếu đổi terminal operation thành `toList()` mà bỏ `limit(2)` thì việc parse đến `NaN` sẽ ném ngoại lệ.
5. `split(input, -1)` giữ thêm một trường trống cuối, nên output kết thúc bằng dấu phẩy trước dấu `]`.

## 4. Pipeline lười: khi nào thực sự làm việc?

Một pipeline có ba thành phần:

```text
Pattern + CharSequence
        |
        v
splitAsStream(input)  -->  filter(...)  -->  map(...)  -->  limit(...)
                                                        |
                                                        v
                                                     toList()
```

Việc gọi `splitAsStream` và xâu chuỗi các intermediate operation chưa yêu cầu Stream trả toàn bộ kết quả. Java bắt đầu duyệt khi gặp terminal operation. Các phần tử thường đi qua nhiều bước xử lý theo nhu cầu của terminal operation, thay vì tạo sẵn một mảng token rồi mới lọc.

Ví dụ:

```java
Pattern p = Pattern.compile(";");
List<String> firstValid = p.splitAsStream(" ;  alice ; ; bob ; carol ")
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .limit(2)
        .toList();
System.out.println(firstValid); // [alice, bob]
```

Dù input chứa nhiều đoạn, kết quả chỉ cần hai token hợp lệ. Pipeline có thể phải xem **nhiều hơn hai token nguồn** vì các token rỗng không vượt qua `filter`; `limit(2)` đếm phần tử **sau khi lọc**. Đảo thứ tự hai bước sẽ đổi ý nghĩa:

- `filter(...).limit(2)`: lấy tối đa hai token **hợp lệ**.
- `limit(2).filter(...)`: chỉ xem hai token **đầu vào** rồi bỏ phần tử không hợp lệ; có thể thu được ít hơn hai token.

Dừng sớm là **khả năng của pipeline**, không bảo đảm rằng toàn bộ regex engine hay mỗi bước nội bộ chỉ làm đúng một lượng công việc cố định. Với `toList()`, `count()`, `collect(...)` hoặc `forEach(...)` thông thường, việc duyệt cần đến hết stream; riêng một số tối ưu của Stream có thể khiến callback không được gọi như người viết mong đợi. Không dựa vào side effect trong `map`, `filter` hoặc `peek` để thực hiện công việc bắt buộc.

**Stream là một lần sử dụng:** sau terminal operation, không tái dùng stream cũ. Khi cần hai cách xử lý khác nhau, gọi lại `pattern.splitAsStream(input)` để tạo hai stream; `Pattern` có thể tái sử dụng.

```java
Pattern p = Pattern.compile(",");
String input = "a,b,c";
long total = p.splitAsStream(input).count();
List<String> first = p.splitAsStream(input).limit(1).toList();
System.out.println(total + " " + first); // 3 [a]
```

## 5. Áp dụng trong chương trình

### 5.1. Chuẩn hóa danh sách nhãn

Giả sử người dùng nhập danh sách tag ngăn cách bởi dấu chấm phẩy, có khoảng trắng, ô rỗng và nhãn lặp:

```java
Pattern separator = Pattern.compile(";");
List<String> tags = separator.splitAsStream(" java ; spring ; ; java ; sql ; ")
        .map(String::strip)
        .filter(s -> !s.isBlank())
        .distinct()
        .toList();
System.out.println(tags); // [java, spring, sql]
```

`strip()` (Java 11+) loại bỏ khoảng trắng Unicode ở hai đầu theo `Character.isWhitespace`; khác `trim()` ở một số trường hợp Unicode. `distinct()` giữ lần xuất hiện đầu tiên theo thứ tự gặp đối với stream có thứ tự. Việc lọc token rỗng là lựa chọn của bài toán, **không tự động xảy ra cho token rỗng ở giữa**.

### 5.2. Lấy một phần dữ liệu và kiểm tra hợp lệ

```java
Pattern comma = Pattern.compile(",");
boolean hasAdmin = comma.splitAsStream("guest,editor,admin,viewer")
        .map(String::strip)
        .anyMatch("admin"::equals);
System.out.println(hasAdmin); // true
```

`anyMatch` trả về ngay khi đã biết kết quả là `true`; với dữ liệu đủ lớn và dấu phân tách phù hợp, điều này có thể tránh xử lý phần tử không cần thiết. Nếu không có token khớp, thao tác phải duyệt cho đến hết.

### 5.3. Regex và delimiter đúng ý nghĩa

`Pattern.compile(regex)` diễn giải ký tự đặc biệt như `.`, `|`, `*`, `+`, dấu ngoặc. Ví dụ dấu `.` trong regex đại diện cho một ký tự bất kỳ; để tách theo **dấu chấm thật**, dùng `"\\."` hoặc `Pattern.quote(".")`:

```java
Pattern dot = Pattern.compile(Pattern.quote("."));
System.out.println(dot.splitAsStream("api.example.com").toList());
// [api, example, com]
```

Khi delimiter do người dùng nhập như **văn bản thuần**, `Pattern.quote(userDelimiter)` thường an toàn hơn việc ghép trực tiếp delimiter vào regex. Khi muốn tách theo nhiều khoảng trắng, dùng regex `"\\s+"` và cân nhắc token rỗng đầu chuỗi nếu input bắt đầu bằng khoảng trắng.

## 6. So sánh cách tách chuỗi

| API | Kết quả | Đặc điểm và tình huống phù hợp |
| --- | --- | --- |
| `String.split(regex)` | `String[]` | Tiện cho thao tác đơn giản; tương ứng với `limit = 0`, bỏ trường rỗng ở cuối. |
| `Pattern.split(input, limit)` | `String[]` | Chủ động điều khiển `limit`. `limit < 0` giữ cả trường rỗng cuối; `limit > 0` giới hạn số lần tách. |
| `Pattern.splitAsStream(input)` | `Stream<String>` | Xâu chuỗi `filter/map/limit/findFirst`, hỗ trợ xử lý theo nhu cầu; không có tham số `limit` kiểu `split`. |
| `String.lines()` | `Stream<String>` | Thích hợp khi mục tiêu là lấy các dòng phân cách bằng LF/CR/CRLF (Java 11+), không cần tự viết regex dòng. |

Không mặc định rằng dùng stream luôn nhanh hơn mảng. Nếu cuối cùng vẫn `toList()` toàn bộ token thì chương trình phải duyệt toàn bộ dữ liệu và tạo List. Hãy chọn dựa trên việc cần dừng sớm, logic pipeline, yêu cầu giữ token rỗng và chi phí thực tế đã đo được.

## 7. Những lỗi thường gặp

1. **Nhầm regex với chuỗi ký tự thường.** `Pattern.compile(".")` sẽ khớp từng ký tự thay vì tách theo dấu chấm. Dùng `Pattern.quote(".")` hoặc `"\\."`.
2. **Cho rằng mọi token rỗng đều bị bỏ.** `splitAsStream("a,,b")` với dấu phẩy vẫn có token `""` ở giữa. Nếu muốn loại bỏ, dùng `filter(s -> !s.isEmpty())` hoặc `!s.isBlank()` tùy yêu cầu.
3. **Muốn giữ cột trống cuối nhưng dùng `splitAsStream`.** Vì API loại bỏ phần tử rỗng ở cuối, hãy chuyển sang `split(input, -1)` trước khi áp dụng quy tắc nghiệp vụ đòi bảo toàn vị trí cột.
4. **Lẫn `limit(n)` với `split(input, n)`.** Thao tác Stream giới hạn số token xuất ra; tham số của `split` còn gộp phần dữ liệu chưa tách vào token cuối.
5. **Cố sử dụng stream hai lần.** Stream đã chạy terminal operation không dùng lại được; tạo stream mới từ cùng `Pattern`.
6. **Sửa input dạng mutable trong khi stream đang thực thi.** API nhận `CharSequence`, có thể là `StringBuilder`. Nếu input thay đổi trong quá trình terminal operation, kết quả là **không được xác định** theo hợp đồng API. Có thể chụp `builder.toString()` trước rồi xử lý trên chuỗi bất biến.
7. **Nhầm dữ liệu CSV thực sự với tách dấu phẩy.** Dòng `"Nguyen, Van",25` có dấu phẩy bên trong trường được trích dẫn; `splitAsStream` với `,` không hiểu cú pháp CSV, dấu nháy hoặc escape. Dùng parser CSV đúng chuẩn khi cần.
8. **Dùng `peek`/`map` cho side effect thiết yếu.** Pipeline có thể dừng sớm hoặc được tối ưu; xử lý side effect một cách tường minh ở nơi được bảo đảm, đặc biệt khi mã có tác động ngoài chương trình.
9. **Biên dịch regex liên tục trong vòng lặp.** Nếu delimiter cố định và dùng nhiều lần, tạo một `Pattern` tái sử dụng. `Pattern` là bất biến và dùng lại được giữa nhiều lời gọi; `Matcher` riêng lẻ thì không nên dùng chung giữa các thread.
10. **Bỏ qua chi phí regex.** Pattern phức tạp có thể tốn CPU trên input dài. Với dữ liệu đến từ bên ngoài, kiểm tra regex, kích thước input và hiệu năng, nhất là khi sử dụng biểu thức có nguy cơ backtracking quá mức.

## 8. Bài tập tự kiểm tra

**Bài 1.** Dự đoán kết quả của hai dòng:

```java
Pattern p = Pattern.compile(",");
System.out.println(p.splitAsStream(",x,,y,").toList());
System.out.println(Arrays.toString(p.split(",x,,y,", -1)));
```

Đáp án: stream có các token `["", "x", "", "y"]`; mảng với `-1` có thêm `""` ở cuối. Khi in trực tiếp `List`/mảng, biểu diễn token trống bằng mắt thường dễ gây nhầm, nên có thể bọc từng phần bằng dấu ngoặc vuông khi debug.

**Bài 2.** Với `"  ;a; ;b;c"` và delimiter `";"`, hãy lấy hai token **không rỗng** đầu tiên sau khi `strip`. Đáp án:

```java
List<String> answer = Pattern.compile(";")
        .splitAsStream("  ;a; ;b;c")
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .limit(2)
        .toList();
System.out.println(answer); // [a, b]
```

**Bài 3.** Cần giữ chính xác ba cột của chuỗi `"a|b|"`, gồm cột cuối rỗng. Chọn `Pattern.compile(Pattern.quote("|")).split(input, -1)` để có `["a", "b", ""]`; dùng `splitAsStream` sẽ bỏ trường rỗng cuối.

## 9. Ghi nhớ

`Pattern.splitAsStream` phù hợp nhất khi **tách bằng regex rồi nối trực tiếp thao tác Stream**, đặc biệt khi chỉ cần một vài kết quả đầu. Nó duy trì thứ tự token, giữ phần rỗng ở giữa nhưng bỏ phần rỗng ở cuối. Kết hợp `filter/map/limit/findFirst` theo đúng thứ tự nghiệp vụ và chọn `Pattern.split(input, limit)` khi cần bảo toàn mọi cột hoặc gộp phần dữ liệu còn lại. Luôn phân biệt **tạo pipeline** với **terminal operation bắt đầu tiêu thụ**, và đừng suy diễn “lazy” thành cam kết hiệu năng trong mọi trường hợp.

**Tài liệu tham khảo:** [Java SE 17 — Pattern.splitAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html#splitAsStream(java.lang.CharSequence)), [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [Java SE 17 — String.split](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#split(java.lang.String,int)).
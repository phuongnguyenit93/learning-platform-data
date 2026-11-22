# Tìm và trích xuất trường từ chuỗi có cấu trúc đơn giản trong Java

## 1. Mục tiêu và phạm vi

Rất nhiều dữ liệu thực tế có cấu trúc nhẹ nhưng được truyền dưới dạng một `String`: `id=42;name=Lan;active=true`, `INFO|user_1|125ms`, `2026-10-23 | INFO | Started` hoặc `code:200;message:OK`. Bài này hướng dẫn cách xác định ranh giới trường, trích xuất giá trị, kiểm tra lỗi và chuyển dữ liệu thành kiểu Java thích hợp mà vẫn bảo toàn ý nghĩa của từng trường.

Sau khi học, bạn có thể:
- Chọn `indexOf`, `substring`, `split` hay `Pattern`/`Matcher` theo cấu trúc đầu vào.
- Phân biệt dấu phân cách giữa **các trường** và dấu nối giữa **khóa và giá trị**; giữ nguyên các dấu phân cách hợp lệ nằm trong giá trị.
- Phát hiện trường bắt buộc bị thiếu, khóa trùng, đầu vào thừa, sai kiểu và giá trị rỗng.
- Xây dựng ví dụ Java 17+ chạy độc lập, có kết quả có thể kiểm chứng; thiết kế kiểm thử cho đầu vào chuẩn và đầu vào lỗi.
- Nhận ra giới hạn của cách tách thủ công: JSON, CSV có dấu nháy, URL query, log tùy ý cần parser theo đúng đặc tả.

**Phạm vi quan trọng:** ví dụ sử dụng chuỗi có **hợp đồng định dạng rõ ràng**. Dữ liệu đầu vào là văn bản đã được giải mã thành Java `String`. Bài này không tìm cách tự nhận diện bảng mã byte và không xây parser tổng quát cho mọi định dạng.

## 2. Đọc cấu trúc trước khi viết mã

Xét bản ghi:

```text
orderId=42;item=book;quantity=3;note=a=b
```

Ta định nghĩa hợp đồng đơn giản:

| Thành phần | Quy tắc |
| --- | --- |
| Phân cách các trường | Dấu chấm phẩy `;` |
| Phân cách khóa và giá trị | Dấu bằng `=` **đầu tiên** trong mỗi trường |
| Khóa | Ký tự ASCII A–Z/a–z ở đầu; sau đó được dùng chữ, chữ số hoặc `_` |
| Giá trị | Chuỗi bất kỳ không chứa `;`; có thể chứa thêm `=` |
| Khoảng trắng | Bỏ ở hai đầu khóa và giá trị bằng `strip()` |
| Trường bắt buộc | `orderId`, `item`, `quantity` |
| Trường tùy chọn | `note` |
| Khóa trùng | Từ chối để không âm thầm lấy nhầm giá trị |
| Giá trị số | `orderId` và `quantity` là số nguyên dương |

Với hợp đồng đó, `note=a=b` có nghĩa **khóa `note` với giá trị `a=b`**, không phải ba phần bằng nhau. Ta cần tách trường theo `;` và chỉ tìm dấu `=` đầu tiên trong từng trường.

Trước khi viết parser, trả lời năm câu hỏi:
1. Dấu nào là ký hiệu cấu trúc? Nó có được xuất hiện trong giá trị không?
2. Trường có thứ tự cố định hay xác định bằng tên khóa?
3. Khoảng trắng nào có ý nghĩa? Giá trị rỗng có hợp lệ không?
4. Khi trường bị thiếu, trùng hoặc sai kiểu, cần báo lỗi hay dùng giá trị mặc định?
5. Đầu vào có trích dẫn/escape/lồng nhau không? Nếu có, `split` đơn giản có thể không đủ.

Một parser tốt đưa các quy tắc trên thành điều kiện kiểm tra tường minh. Nếu định dạng nguồn chưa được thống nhất, việc chọn thuật toán trước thường dẫn tới giả định sai.

## 3. `indexOf` và `substring`: tìm chính xác ranh giới

`String.indexOf(char)` tìm vị trí đầu tiên của ký tự hoặc trả về `-1` nếu không thấy. `String.indexOf(String)` tìm chuỗi con; overload có `fromIndex` tìm từ một vị trí. `lastIndexOf` tìm lần xuất hiện cuối. `substring(beginIndex, endIndex)` trích phần [beginIndex, endIndex), tức là có đầu nhưng không có vị trí cuối.

Ví dụ Java 17+ chạy độc lập, lưu thành `IndexExtractDemo.java`:

```java
public class IndexExtractDemo {
    public static void main(String[] args) {
        String input = "status=OK;detail=a=b";
        int delimiter = input.indexOf(';');
        if (delimiter < 0) {
            throw new IllegalArgumentException("Thiếu dấu ;");
        }

        String left = input.substring(0, delimiter);
        String right = input.substring(delimiter + 1);

        int leftEquals = left.indexOf('=');
        int rightEquals = right.indexOf('=');
        if (leftEquals < 1 || rightEquals < 1) {
            throw new IllegalArgumentException("Trường thiếu khóa hoặc dấu =");
        }

        String status = left.substring(leftEquals + 1);
        String detail = right.substring(rightEquals + 1);
        System.out.println("status=" + status);
        System.out.println("detail=" + detail);
    }
}
```

```bash
javac -encoding UTF-8 IndexExtractDemo.java
java IndexExtractDemo
```

```text
status=OK
detail=a=b
```

Trong trường hợp `detail=a=b`, tìm dấu `=` **đầu** rồi lấy phần bên phải giữ nguyên `a=b`. Nếu dùng `lastIndexOf('=')` để phân cách khóa và giá trị, kết quả sẽ không đúng hợp đồng.

**Kiểm tra trước khi cắt:** `indexOf` có thể trả về `-1`; không được dùng chỉ số đó trực tiếp cho `substring` hoặc `charAt`. Các ngoại lệ như `StringIndexOutOfBoundsException` là dấu hiệu lỗi xử lý ranh giới, không phải chính sách xác thực dữ liệu mong muốn.

Các chỉ số trên `String` tính theo **đơn vị mã UTF-16**. `indexOf(String)` và `substring` vẫn hợp lệ với dữ liệu Unicode, nhưng không nên tự giả định rằng mỗi `char` tương ứng một ký tự người dùng nhìn thấy.

## 4. Dùng `split` khi ranh giới trường đơn giản

`String.split(regex)` nhận **regex**; khi delimiter do ứng dụng cung cấp là ký tự nguyên văn như `|` hoặc `.`, dùng `Pattern.quote(delimiter)` để tránh diễn giải nhầm dấu đặc biệt. Nếu cần giữ trường rỗng cuối, chọn `split(regex, -1)`, bởi `split(regex)` tương đương `split(regex, 0)` và bỏ các trường rỗng ở đuôi.

Với một cặp `key=value`, chỉ được cắt tại dấu `=` đầu tiên nếu nội dung value có thể chứa thêm `=`:

```java
String[] pair = "note=a=b".split("=", 2);
System.out.println(pair[0]); // note
System.out.println(pair[1]); // a=b
```

Cần kiểm tra `pair.length == 2`, khóa không rỗng và hợp đồng xử lý whitespace. Trong parser ở mục tiếp theo, `indexOf('=')` làm bước kiểm tra rõ hơn; `split(";", -1)` lại bảo toàn trường cuối rỗng để phát hiện dấu `;` thừa. Khi cần giữ chính xác từng dấu phân cách và tái tạo chuỗi gốc, xem bài **“Tách dữ liệu có phần tử rỗng và giữ đúng dấu phân cách”**, nơi giải thích đầy đủ `limit`, delimiter dạng regex và `Matcher`.

## 5. Ví dụ tổng hợp: parse các trường `key=value`

Ví dụ sau trích trường, kiểm tra khóa và kiểu dữ liệu, phát hiện khóa trùng, bảo toàn dấu `=` trong giá trị, sau đó in kết quả. Lưu thành `SimpleRecordParser.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class SimpleRecordParser {
    private static Map<String, String> parse(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Bản ghi trống");
        }

        Map<String, String> fields = new LinkedHashMap<>();

        for (String rawEntry : input.split(";", -1)) {
            String entry = rawEntry.strip();
            int equalsIndex = entry.indexOf('=');
            if (equalsIndex <= 0) {
                throw new IllegalArgumentException(
                        "Trường thiếu khóa hoặc dấu =: " + entry);
            }

            String key = entry.substring(0, equalsIndex).strip();
            String value = entry.substring(equalsIndex + 1).strip();

            if (!key.matches("[A-Za-z][A-Za-z0-9_]*")) {
                throw new IllegalArgumentException("Khóa không hợp lệ: " + key);
            }
            if (fields.containsKey(key)) {
                throw new IllegalArgumentException("Khóa trùng: " + key);
            }
            fields.put(key, value);
        }
        return fields;
    }

    private static String required(Map<String, String> fields, String key) {
        String value = fields.get(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Thiếu giá trị: " + key);
        }
        return value;
    }

    private static int positiveInt(Map<String, String> fields, String key) {
        String raw = required(fields, key);
        final int value;
        try {
            value = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    key + " phải là số nguyên", ex);
        }
        if (value <= 0) {
            throw new IllegalArgumentException(key + " phải > 0");
        }
        return value;
    }

    public static void main(String[] args) {
        String input = "orderId=42;item=book;quantity=3;note=a=b";
        Map<String, String> fields = parse(input);

        int orderId = positiveInt(fields, "orderId");
        String item = required(fields, "item");
        int quantity = positiveInt(fields, "quantity");
        String note = fields.getOrDefault("note", "");

        System.out.println("orderId=" + orderId);
        System.out.println("item=" + item);
        System.out.println("quantity=" + quantity);
        System.out.println("note=" + note);
        System.out.println("fieldCount=" + fields.size());
    }
}
```

```bash
javac -encoding UTF-8 SimpleRecordParser.java
java SimpleRecordParser
```

```text
orderId=42
item=book
quantity=3
note=a=b
fieldCount=4
```

### Phân tích cách hoạt động

1. `split(";", -1)` giữ cả đoạn rỗng cuối để đầu vào `a=1;` không bị coi là hợp lệ một cách âm thầm: đoạn cuối rỗng sẽ vi phạm điều kiện `equalsIndex <= 0`.
2. `indexOf('=')` chỉ chọn dấu phân cách đầu tiên. Phần còn lại, kể cả `=`, thuộc giá trị.
3. `strip()` loại bỏ khoảng trắng Unicode ở hai đầu theo tiêu chí `Character.isWhitespace`; nếu khoảng trắng đầu/cuối là dữ liệu có ý nghĩa, **không nên strip giá trị**.
4. Biểu thức `[A-Za-z][A-Za-z0-9_]*` định nghĩa **khóa ASCII** theo hợp đồng ví dụ. Nó không ngầm đại diện mọi định danh Unicode hợp lệ.
5. `containsKey` phát hiện trùng khóa. Nếu dùng `Map.put` trực tiếp, trường xuất hiện sau có thể âm thầm ghi đè trường trước.
6. `required(...)` phân biệt tên khóa phải có nội dung với khóa tùy chọn. `positiveInt(...)` kiểm tra được cả sai cú pháp số, tràn phạm vi `int` và số không dương.
7. `LinkedHashMap` giữ thứ tự chèn khi cần xem lại trường theo thứ tự nguồn. Nếu không cần thứ tự, có thể chọn `HashMap`; không nên dựa vào thứ tự duyệt của `HashMap`.

**Giới hạn tường minh:** parser này không cấm khóa lạ ngoài `orderId`, `item`, `quantity` và `note`; không xử lý escape cho `;`; không kiểm tra giới hạn kích thước chuỗi/giá trị; và chỉ minh họa một schema nhỏ. Ứng dụng thật nên bổ sung giới hạn theo hợp đồng dữ liệu, whitelist khóa nếu cần, kiểm tra độ dài, chính sách logging an toàn và kiểm thử lỗi tương ứng.

### Trường hợp đầu vào lỗi

| Đầu vào | Hành vi của parser trên |
| --- | --- |
| `orderId=42;quantity=3;item=book` | Hợp lệ, `note` tùy chọn rỗng |
| `orderId=42;item=book;quantity=3;` | Báo lỗi vì có một trường rỗng cuối |
| `orderId=42;orderId=99;item=book;quantity=3` | Báo lỗi khóa `orderId` trùng |
| `=42;item=book;quantity=3` | Báo lỗi trường thiếu khóa |
| `orderId=42;item=book;quantity=zero` | Lỗi khi gọi `positiveInt` cho `quantity` |
| `orderId=42;item=book` | Lỗi thiếu giá trị `quantity` khi được yêu cầu |
| `orderId=42;item=;quantity=3` | Lỗi khi gọi `required` cho `item` |
| `orderId=42;item=book;quantity=3;note=a=b` | Hợp lệ, `note` giữ nguyên `a=b` |

Lưu ý: `parse(...)` tách và xác thực **cú pháp các trường**, còn `required(...)`/`positiveInt(...)` xác thực **schema và kiểu** sau khi tách. Thiết kế tách hai trách nhiệm này giúp kiểm thử rõ ràng và tái sử dụng logic phù hợp hơn.

## 6. Trích xuất trường theo vị trí từ bản ghi có delimiter cố định

Không phải chuỗi có cấu trúc nào cũng có khóa. Ví dụ một log đơn giản được định nghĩa gồm **ba trường** ngăn bởi ` | `:

```text
2026-10-23 | INFO | Started successfully
```

Có thể tìm hai dấu phân cách đầu tiên rồi cắt từng phần. Cách này giữ nguyên delimiter ` | ` nếu vô tình xuất hiện trong thông điệp phía cuối, vì thông điệp là toàn bộ phần còn lại.

Lưu thành `FixedFieldsDemo.java`:

```java
public class FixedFieldsDemo {
    private static final String SEPARATOR = " | ";

    public static void main(String[] args) {
        String line = "2026-10-23 | INFO | Started | background task";

        int first = line.indexOf(SEPARATOR);
        int second = first < 0
                ? -1 : line.indexOf(SEPARATOR, first + SEPARATOR.length());

        if (first < 0 || second < 0) {
            throw new IllegalArgumentException("Thiếu trường log");
        }

        String date = line.substring(0, first);
        String level = line.substring(
                first + SEPARATOR.length(), second);
        String message = line.substring(second + SEPARATOR.length());

        if (date.isBlank() || level.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Trường bắt buộc trống");
        }

        System.out.println("date=" + date);
        System.out.println("level=" + level);
        System.out.println("message=" + message);
    }
}
```

```bash
javac -encoding UTF-8 FixedFieldsDemo.java
java FixedFieldsDemo
```

```text
date=2026-10-23
level=INFO
message=Started | background task
```

Cách này phù hợp khi **hai trường đầu cố định, phần cuối được phép chứa delimiter**. Nếu ngược lại phần đầu được phép chứa delimiter và phần cuối có cấu trúc cố định, cần xác định ranh giới khác hoặc tìm từ cuối bằng `lastIndexOf` theo hợp đồng.

`String.split(" \\| ", 3)` cũng có thể tách tối đa ba phần, nhưng `indexOf` làm rõ ranh giới và điều kiện thiếu delimiter. Nếu ngày, level hay message có quy tắc riêng, hãy xác thực sau khi lấy được trường, ví dụ `LocalDate.parse(date)` cho định dạng ngày ISO hoặc tập giá trị level được cho phép.

## 7. Dùng regex khi cần kiểm tra mẫu và trích nhiều trường cùng lúc

Khi cấu trúc có phần chữ cố định, số, dấu cách tùy chọn hoặc tập giá trị hợp lệ, regex có thể vừa xác nhận toàn chuỗi vừa trích nhóm. `Pattern` biểu diễn regex đã biên dịch; `Matcher` là đối tượng so khớp cho một chuỗi đầu vào.

Ví dụ định dạng theo hợp đồng: `LEVEL|userName|durationMs`, trong đó:
- `LEVEL` thuộc `INFO`, `WARN` hoặc `ERROR`.
- `userName` chỉ gồm chữ ASCII ở đầu rồi chữ, số, dấu gạch dưới.
- Thời lượng là một hoặc nhiều chữ số thập phân, theo sau bởi chữ `ms`.
- Cả dòng phải khớp; không chấp nhận tiền tố/hậu tố tùy ý.

Lưu thành `RegexFieldsDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexFieldsDemo {
    private static final Pattern LINE = Pattern.compile(
            "(?<level>INFO|WARN|ERROR)\\|"
            + "(?<user>[A-Za-z][A-Za-z0-9_]*)\\|"
            + "(?<duration>\\d+)ms");

    public static void main(String[] args) {
        String input = "INFO|linh_2|125ms";
        Matcher matcher = LINE.matcher(input);

        if (!matcher.matches()) {
            throw new IllegalArgumentException("Sai định dạng dòng log");
        }

        String level = matcher.group("level");
        String user = matcher.group("user");
        int duration = Integer.parseInt(matcher.group("duration"));

        System.out.println("level=" + level);
        System.out.println("user=" + user);
        System.out.println("durationMs=" + duration);
    }
}
```

```bash
javac -encoding UTF-8 RegexFieldsDemo.java
java RegexFieldsDemo
```

```text
level=INFO
user=linh_2
durationMs=125
```

Dấu `\\|` trong literal Java tạo regex `\|` để khớp dấu gạch đứng. `\\d+` tạo regex cho một hoặc nhiều chữ số. `(?<level>...)` khai báo **named capturing group**; `group("level")` trích phần tương ứng sau khi `matches()` thành công.

### `matches()` và `find()` khác nhau

- `matcher.matches()` yêu cầu **toàn bộ chuỗi đầu vào** phù hợp với mẫu. Nên dùng khi xác thực một bản ghi hoàn chỉnh.
- `matcher.find()` tìm **một đoạn con phù hợp** bắt đầu từ vị trí quét hiện tại. Phù hợp khi lấy nhiều lần xuất hiện trong văn bản dài; gọi lại `find()` sẽ tiếp tục tìm.
- `matcher.group(...)` chỉ hợp lệ sau khi so khớp thành công. Nếu lấy group khi chưa `matches()`/`find()` thành công, sẽ phát sinh trạng thái lỗi của `Matcher`.

Ví dụ chỉ để minh họa cú pháp gọi `find()` (đoạn code đặt trong phương thức Java):

```java
Matcher m = Pattern.compile("id=(\\d+)").matcher("id=10; id=20");
while (m.find()) {
    System.out.println(m.group(1));
}
```

```text
10
20
```

Đối với dữ liệu phức tạp hoặc input không tin cậy, tránh regex lồng nhiều lượng tử tham lam có thể gây chi phí backtracking lớn. `Pattern` bất biến và có thể tái sử dụng; `Matcher` có trạng thái riêng, không nên dùng chung một thể hiện giữa nhiều luồng.

## 8. Chọn `indexOf`, `split` hay regex?

| Cấu trúc đầu vào | Lựa chọn gợi ý | Ví dụ |
| --- | --- | --- |
| Lấy nội dung sau dấu `=` đầu tiên | `indexOf` + `substring` | `message=a=b=c` |
| Tách vài phần theo dấu phân cách cố định | `split` với regex đã escape; hoặc `indexOf` | `red;green;blue` |
| Cần giữ trường trống cuối | `split(regex, -1)` | `A|B|` |
| Chỉ tách thành đúng hai phần | `split(regex, 2)` hoặc `indexOf` | `key=value=extra` |
| Bản ghi có trường theo vị trí, phần cuối chứa delimiter | Hai lần `indexOf` hoặc `split(regex, 3)` | `date | level | long message` |
| Mẫu gồm tên, số, tập enum đơn giản | `Pattern` + `Matcher.matches` | `INFO|user_1|23ms` |
| Quét nhiều kết quả nằm giữa văn bản | `Matcher.find` | `id=10; id=20` |
| CSV có trường đặt trong dấu nháy / JSON / URL query | Parser tương ứng | `"Lan, Nguyễn",21`, JSON hoặc query có percent-encoding |

Không có phương pháp nào mặc định đúng cho mọi chuỗi. Chọn cách đơn giản nhất vẫn đáp ứng đầy đủ hợp đồng đầu vào, điều kiện lỗi và trường hợp delimiter bên trong giá trị.

## 9. Kiểm tra dữ liệu sau khi trích xuất

**Tách chuỗi không đồng nghĩa với dữ liệu hợp lệ.** Sau khi lấy giá trị, xác minh theo kiểu mong đợi:

- **Số nguyên:** `Integer.parseInt(...)` ném `NumberFormatException` nếu không phải số nguyên thập phân hợp lệ hoặc vượt miền `int`. Nếu cần số lớn, cân nhắc `Long.parseLong` hoặc `BigInteger`.
- **Boolean:** `Boolean.parseBoolean(...)` trả về `true` duy nhất cho chuỗi tương đương `"true"` khi bỏ qua hoa/thường; phần còn lại, kể cả chuỗi sai như `"tru"`, trả về `false`. Nếu input phải là `true/false` hợp lệ, hãy xác minh **trước** khi chuyển.
- **Ngày ISO:** `LocalDate.parse(...)` xác thực cú pháp/ngày hợp lệ và ném `DateTimeParseException` khi sai. Không chỉ kiểm tra ngày bằng regex `\d{4}-\d{2}-\d{2}` rồi giả định lịch đúng.
- **Trường tùy chọn:** quyết định rõ giữa *khóa không có*, *khóa có giá trị rỗng*, và *khóa có giá trị mặc định*. Ví dụ `Map.getOrDefault` chỉ trả về mặc định khi khóa không tồn tại; nếu có khóa với giá trị rỗng, kết quả vẫn là chuỗi rỗng.
- **Mã định danh:** đặt giới hạn ký tự và chiều dài theo yêu cầu nghiệp vụ; đừng cho rằng `trim` hay `strip` có thể thay cho kiểm tra định dạng.

Ví dụ boolean nghiêm ngặt (đoạn phương thức độc lập có thể đặt trong một class):

```java
static boolean parseStrictBoolean(String raw) {
    if ("true".equalsIgnoreCase(raw)) {
        return true;
    }
    if ("false".equalsIgnoreCase(raw)) {
        return false;
    }
    throw new IllegalArgumentException("Giá trị boolean không hợp lệ: " + raw);
}
```

Tương tự, nếu `quantity` phải lớn hơn 0, `parseInt` thành công chưa đủ: vẫn phải kiểm tra miền giá trị sau chuyển đổi.

## 10. Lỗi thường gặp và cách tránh

### 10.1. Nhầm delimiter với regex

`"A|B|C".split("|")` không tách theo dấu gạch đứng theo nghĩa literal vì `|` có ý nghĩa đặc biệt trong regex. Dùng `split("\\|")` hoặc `split(Pattern.quote("|"))`.

Tương tự, `split(".")` không tách đúng dấu chấm; sử dụng `split("\\.")` hoặc `Pattern.quote(".")`. Lỗi có thể âm thầm tạo các phần tử không mong muốn hoặc một mảng rỗng.

### 10.2. Dùng `split("=")` cho giá trị có dấu `=`

`note=a=b` phải tách tại dấu `=` đầu tiên. Dùng `indexOf('=')` và `substring`, hoặc `split("=", 2)`. Nếu định dạng có escaping phức tạp, cả hai cách đơn giản có thể không đủ.

### 10.3. Truy cập phần tử mảng mà không kiểm tra

Mã `input.split(";")[1]` sẽ có thể ném `ArrayIndexOutOfBoundsException` khi thiếu dấu phân cách. Luôn kiểm tra số trường và chính sách trường trống trước khi truy cập.

### 10.4. Đánh rơi trường trống cuối

`"A;B;".split(";")` mặc định bỏ đoạn trống cuối. Nếu dữ liệu bắt buộc có ba cột và cột thứ ba rỗng là thông tin có ý nghĩa, dùng `split(";", -1)`.

### 10.5. Lấy giá trị mà không kiểm tra khóa

Với `"name=Lan;role=admin"`, nếu yêu cầu trường `role`, không nên coi “phần tử thứ hai” chắc chắn là `role` trừ khi thứ tự cố định là một phần của hợp đồng. Dữ liệu hoán đổi thứ tự vẫn nên đọc đúng theo tên khóa nếu nguồn khai báo cấu trúc theo tên.

### 10.6. Ghi đè khóa trùng

`id=1;id=2` đặt ra câu hỏi: lấy giá trị đầu, giá trị cuối hay từ chối? Nếu không có chính sách rõ, `Map.put` có thể che dấu dữ liệu bất thường. Ví dụ tổng hợp chọn từ chối khóa trùng.

### 10.7. Coi mọi chuỗi có dấu phẩy là CSV đơn giản

Dòng CSV `"Nguyen, Lan",21` có dấu phẩy **bên trong giá trị được quote**. `split(",")` sẽ tách sai; CSV còn có escaping dấu nháy và xuống dòng trong trường. Dùng thư viện/parser CSV tuân thủ đúng dialect thay vì một regex nhanh.

### 10.8. Tự parse query string hoặc JSON

Query string URL có thể có percent-encoding, dấu `=`/`&` trong dữ liệu đã escape, key trùng và quy tắc encoding. JSON có string escape, dấu ngoặc lồng nhau và kiểu dữ liệu. Dùng API hoặc parser dành riêng cho định dạng đó. Bài này áp dụng cho cấu trúc đơn giản **do ứng dụng kiểm soát**.

### 10.9. Không giới hạn đầu vào

Nếu nhận chuỗi rất lớn hoặc hàng triệu trường, `split` và regex có thể tiêu tốn thời gian/bộ nhớ đáng kể. Giới hạn chiều dài đầu vào, số trường và độ dài giá trị theo hợp đồng; chỉ ghi log thông tin cần thiết, tránh lộ dữ liệu riêng tư. Với luồng dữ liệu lớn, cân nhắc parser streaming.

### 10.10. Tách trường thành công nhưng bỏ qua dữ liệu thừa

Regex với `find()` có thể nhận một đoạn hợp lệ bên trong một dòng không hợp lệ. Khi một bản ghi **phải khớp toàn phần**, dùng `matches()`, kiểm tra đúng số trường hoặc các điều kiện kết thúc rõ ràng.

## 11. Thiết kế kiểm thử cho parser đơn giản

Kiểm thử ít nhất những nhóm sau. Việc parser trả về kết quả đúng với một ví dụ đẹp chưa đủ chứng minh sự vững chắc.

| Nhóm | Đầu vào ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Bình thường | `id=12;name=Lan` | Đúng hai trường và giá trị |
| Đổi thứ tự khóa | `name=Lan;id=12` | Lookup theo khóa không phụ thuộc thứ tự |
| Rỗng toàn chuỗi | `""` | Bị từ chối hoặc xử lý theo hợp đồng |
| Thiếu dấu phân cách cặp | `id12` | Báo lỗi có nguyên nhân rõ |
| Khóa rỗng | `=12` | Bị từ chối |
| Giá trị rỗng | `name=` | Xử lý khác với khóa không có, theo schema |
| Giá trị chứa `=` | `note=a=b` | Không làm mất đoạn `=b` |
| Trường rỗng cuối | `id=12;` | Không bị bỏ qua âm thầm |
| Khóa trùng | `id=12;id=13` | Phát hiện theo chính sách |
| Sai kiểu | `quantity=three` | Lỗi chuyển kiểu được xử lý |
| Số ngoài phạm vi | `quantity=99999999999999` | Không tràn mà không báo |
| Ký tự Unicode | `name=Hà Nội` | Đúng chuỗi Unicode và chính sách whitespace |
| Chuỗi rất dài | Nhiều trường/giá trị dài | Có giới hạn tài nguyên |
| Delimiter trong dữ liệu | `note=a;b` | Bị từ chối theo định dạng đơn giản hoặc chuyển sang cú pháp có escape |

Nên chia kiểm thử thành ba cấp: kiểm thử **tách cú pháp**, kiểm thử **xác thực schema/kiểu**, và kiểm thử **hành vi ứng dụng** khi một bản ghi không hợp lệ. Đặc biệt, tránh nuốt ngoại lệ bằng cách trả về chuỗi rỗng hoặc giá trị `0` khi đó có thể bị hiểu là dữ liệu thật.

## 12. Bài tập thực hành

**Bài tập 1 — key/value:** viết hàm `extractValue(String record, String wantedKey)` cho định dạng `a=1;b=2;c=3`. Hàm trả về `Optional<String>` hoặc giá trị có chính sách “không tìm thấy” rõ ràng. Xử lý đúng `note=a=b` và khóa `a` so với `aa`. Không dùng phép kiểm tra `contains("a=")` đơn giản vì có thể khớp nhầm.

**Bài tập 2 — bản ghi cố định:** phân tích `"2026-10-23|WARN|Disk nearly full"` thành ngày, level và thông điệp. Kiểm tra hai dấu phân cách đầu tiên, xác thực ngày bằng `LocalDate.parse` và level thuộc một tập giá trị được cho phép.

**Bài tập 3 — kiểm tra giá trị số:** từ `"user=linh;age=21;active=true"`, trích các trường và chuyển kiểu. Từ chối `age=-3`, `age=abc` và `active=maybe` nếu nghiệp vụ yêu cầu tuổi không âm và boolean tường minh.

**Bài tập 4 — Regex:** viết `Pattern` để khớp toàn chuỗi `"HTTP 200 /health"`, trích mã trạng thái ba chữ số và đường dẫn bắt đầu bằng `/`. So sánh hành vi `matches()` và `find()` khi thêm văn bản không hợp lệ ở đầu dòng.

**Bài tập 5 — giới hạn của `split`:** thử `"id=1;note=red;blue"`. Vì `;` trong giá trị không được escape, parser đơn giản sẽ không biết chính xác phần nào là ranh giới. Hãy đề xuất một **hợp đồng dữ liệu mới** (ví dụ escape, độ dài trường hoặc định dạng chuẩn như JSON) và giải thích vì sao cần parser riêng cho hợp đồng đó.

## 13. Ghi nhớ khi áp dụng

Hãy bắt đầu bằng **hợp đồng đầu vào**: delimiter là gì, giá trị có được chứa delimiter hay không, trường nào bắt buộc và khi nào báo lỗi. Với cấu trúc cố định nhỏ, `indexOf` và `substring` là cách rõ ràng. Với danh sách phân cách đều, `split` tiện lợi nhưng phải nhớ regex và tham số `limit`. Với mẫu có nhiều điều kiện và nhóm cần lấy, `Pattern`/`Matcher` hữu ích; `matches()` xác thực toàn bộ bản ghi còn `find()` dò đoạn con.

Luôn kiểm tra vị trí trước khi cắt, kiểm tra số lượng trường trước khi truy cập, không ghi đè khóa trùng ngoài ý muốn và xác thực kiểu sau khi tách. Khi dữ liệu đã có đặc tả phức tạp như CSV, URL query hoặc JSON, chọn parser đúng đặc tả thay vì kéo dài một chuỗi các phép `split`.
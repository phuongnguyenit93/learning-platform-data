# Giới hạn của tách dòng và `split()` khi đọc định dạng có escape phức tạp

Khi đọc dữ liệu văn bản, hai thao tác thường gặp là **tách thành dòng** (`BufferedReader.readLine()`, `Files.lines()`) và **tách thành token** (`String.split(regex)`, `Scanner`). Cách này rất phù hợp với dữ liệu đơn giản: một dòng là một bản ghi, dấu phân cách không bao giờ xuất hiện trong giá trị, không có trích dẫn (quoting) hay escape.

Với các định dạng có escape phức tạp, hai giả định trên có thể sai:

- Một bản ghi logic có thể **trải qua nhiều dòng vật lý**, chẳng hạn trường CSV được bao trong dấu nháy chứa `\n`.
- Dấu phân cách có thể xuất hiện như **dữ liệu thật**, chẳng hạn dấu phẩy trong `"Hà Nội, Việt Nam"` hoặc `\|` trong định dạng phân cách bằng `|`.
- Dấu nháy và dấu gạch chéo ngược có thể có **quy tắc escape riêng**; ký tự phân cách chỉ có ý nghĩa sau khi xét trạng thái parser.
- Những định dạng lồng nhau như JSON cần hiểu dấu ngoặc, chuỗi và escape; chia theo `,`, `:` hoặc dấu xuống dòng không đủ để hiểu cấu trúc.

**Ý chính:** Tách chuỗi chỉ dựa trên dấu phân cách là thao tác từ vựng đơn giản. Khi dấu phân cách có thể bị escape, nằm trong chuỗi được trích dẫn hoặc trong cấu trúc lồng nhau, cần **parser hiểu quy tắc của định dạng**. Không tồn tại một công thức `split()` chung có thể đọc đúng mọi định dạng phức tạp.

## 1. Dòng vật lý, bản ghi logic và trường dữ liệu khác nhau

Giả sử tệp CSV chứa:

```csv
id,note
1,"Thành phố Hồ Chí Minh, Việt Nam"
2,"Dòng thứ nhất
Dòng thứ hai"
3,"Anh ấy nói ""Xin chào"""
```

Ta cần phân biệt:

| Khái niệm | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| Dòng vật lý | Phần văn bản ngăn bởi dấu kết thúc dòng trong file | Bản ghi `id=2` trải qua **hai** dòng vật lý. |
| Bản ghi logic | Một đơn vị dữ liệu hoàn chỉnh theo cú pháp định dạng | CSV ở đây có một bản ghi header và ba bản ghi dữ liệu. |
| Trường (field) | Một giá trị nằm trong bản ghi | `Thành phố Hồ Chí Minh, Việt Nam` là một trường dù chứa dấu phẩy. |
| Dấu phân cách | Ký tự có ý nghĩa cấu trúc trong ngữ cảnh hợp lệ | Dấu phẩy **ngoài** cặp nháy phân cách trường; dấu phẩy **trong** cặp nháy là dữ liệu. |
| Escape | Cú pháp biểu diễn ký tự đặc biệt mà không làm thay đổi cấu trúc | CSV thường dùng `""` để biểu diễn một ký tự `"` trong trường có nháy. |

`BufferedReader.readLine()` trả một **dòng vật lý** và loại bỏ delimiter kết thúc dòng; nó **không biết** dấu xuống dòng có đang nằm trong trường CSV được trích dẫn hay không. Tương tự, `String.split(",")` không biết dấu phẩy đang nằm trong cặp nháy. Dùng cả hai liên tiếp vẫn không tự tạo ra parser CSV.

### Ví dụ 1 — minh họa lỗi bằng chương trình Java 17+

```java
// NaiveSplitDemo.java
public class NaiveSplitDemo {
    public static void main(String[] args) {
        String csv =
                "id,note\n"
                + "1,\"Hello, world\"\n"
                + "2,\"Dòng thứ nhất\nDòng thứ hai\"\n";

        String[] physicalLines = csv.split("\\R");
        String[] wrongFields = "1,\"Hello, world\"".split(",", -1);

        System.out.println("physicalLines=" + physicalLines.length);
        System.out.println("naiveFields=" + wrongFields.length);
        System.out.println("logicalRecordsExpected=3");
        System.out.println("fieldsPerRecordExpected=2");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NaiveSplitDemo.java
java NaiveSplitDemo
```

Kết quả:

```text
physicalLines=4
naiveFields=3
logicalRecordsExpected=3
fieldsPerRecordExpected=2
```

Dữ liệu thực có **ba bản ghi logic**, nhưng `split("\\R")` tạo bốn phần vì bản ghi thứ ba chứa newline trong dấu nháy. Dòng thứ hai có **hai trường**, nhưng `split(",")` tạo ba phần do dấu phẩy nằm trong `"Hello, world"`. `split()` vẫn hoạt động đúng theo quy tắc regex của nó; điều **không đúng** là giả định regex dấu phẩy/dấu xuống dòng biểu diễn toàn bộ cú pháp CSV.

## 2. Những giới hạn riêng của `String.split()`

`String.split(String regex)` dùng **biểu thức chính quy**, không phải chuỗi delimiter thuần túy. Kết quả dựa trên vị trí match của regex và tham số `limit`, chứ không suy diễn trích dẫn hoặc escape của định dạng đầu vào.

### 2.1. Dấu phân cách có ký tự đặc biệt trong regex

Các ký tự như `.`, `|`, `*`, `+`, `?`, `[`, `]`, `(`, `)` có ý nghĩa trong regex. Vì vậy:

```java
String[] parts = "a|b|c".split("|");  // Sai mục đích: | là toán tử alternation của regex
```

Đây là đoạn minh họa lỗi về **mục đích tách delimiter**, không phải cú pháp Java không biên dịch được. Để tách theo ký tự `|` theo nghĩa đen, dùng `"\\|"` hoặc `Pattern.quote("|")`.

### 2.2. Mặc định bỏ các trường rỗng ở cuối

`split(regex)` tương đương `split(regex, 0)`: bỏ các chuỗi rỗng **cuối kết quả**. Khi các cột cuối rỗng vẫn có ý nghĩa, phải chỉ định `limit` âm:

```java
// SplitSemanticsDemo.java
import java.util.Arrays;
import java.util.regex.Pattern;

public class SplitSemanticsDemo {
    public static void main(String[] args) {
        String line = "one|two||";

        System.out.println(Arrays.toString(line.split("\\|")));
        System.out.println(Arrays.toString(line.split("\\|", -1)));
        System.out.println(line.split(Pattern.quote("|"), -1).length);
    }
}
```

```bash
javac SplitSemanticsDemo.java
java SplitSemanticsDemo
```

Kết quả:

```text
[one, two]
[one, two, , ]
4
```

`Pattern.quote()` giúp escape delimiter cho **regex**, nhưng không giải quyết escape/trích dẫn **trong dữ liệu**. Ví dụ `one\|two|three` vẫn không thể tách đúng theo quy tắc “`\|` là dấu `|` thuộc nội dung” bằng cách chỉ dùng `split("\\|")`.

### 2.3. Regex có thể phù hợp với định dạng đơn giản, nhưng không tự hiểu grammar

Regex hữu ích khi quy tắc rõ ràng, không có nesting và delimiter chắc chắn không xuất hiện trong trường; ví dụ tách các dấu cách liên tiếp bằng `split("\\s+")`. Regex có thể biểu diễn nhiều điều kiện phức tạp, nhưng một regex tách đơn giản:

- Không tự duy trì trạng thái trường CSV đang ở trong hay ngoài dấu nháy qua nhiều dòng.
- Không tự kiểm tra số dấu escape, cách nhân đôi dấu nháy, record kết thúc ở đâu.
- Không tự phát hiện toàn bộ các trường hợp sai cú pháp như chuỗi quote chưa đóng hoặc escape không hợp lệ.
- Không phân tích đầy đủ cấu trúc JSON/XML/YAML vốn có quy tắc riêng về chuỗi, lồng nhau và biểu diễn ký tự.

Một regex được thiết kế rất kỹ có thể xử lý **một tập con** của một format; cần có quy tắc kiểm tra và test rõ ràng. Không coi một mẫu `split()` vài ký tự là CSV/JSON parser tổng quát.

## 3. Escape không chỉ là “có dấu `\` đứng trước”

Từ “escape” không có một nghĩa duy nhất cho mọi định dạng:

| Định dạng / quy ước | Ví dụ dữ liệu | Quy tắc cần hiểu |
| --- | --- | --- |
| CSV kiểu trích dẫn kép | `"He said ""Hi"""` | Hai dấu `""` ở bên trong trường trích dẫn biểu diễn một dấu `"` thật. |
| Chuỗi kiểu backslash | `a\|b|c` | Giả sử `\|` biểu diễn `|` thuộc nội dung; chỉ `|` không escape mới phân cách. |
| JSON | `{"message":"a,\"b\""}` | Trong văn bản JSON thực, `\"` nằm trong chuỗi; dấu phẩy trong chuỗi không chia thuộc tính. |
| JSON có escape Unicode | `"\u0041"` | Trình phân tích JSON phải xử lý escape theo grammar JSON; không dùng `split()` để tự giải mã. |
| URL-encoded form | `name=An%20Nguyen` | `%20` có nghĩa theo quy tắc percent-encoding; thứ tự split/decode rất quan trọng. |
| Log có dấu nháy hoặc metadata | `"GET /a,b HTTP/1.1" 200` | Tách theo dấu cách sẽ phá vỡ request nằm trong dấu nháy. |

**Ví dụ JSON trong bảng là cú pháp minh họa**, không phải Java string literal. Khi viết những nội dung này trực tiếp trong source Java, phải xét **hai lớp escape**: Java string literal và định dạng dữ liệu mà chuỗi Java chứa. Chẳng hạn Java `"\\n"` có hai ký tự backslash + `n` ở runtime, trong khi Java `"\n"` là ký tự xuống dòng thật. Sự nhầm lẫn hai lớp này dẫn tới các bài test parser sai ngay từ dữ liệu đầu vào.

### 3.1. Số lượng backslash liên tiếp có thể làm thay đổi ý nghĩa

Trong một grammar dùng backslash để escape, cần biết chính xác **backslash nào escape ký tự nào**. Ví dụ nếu quy ước cho phép `\|` là dấu `|` dữ liệu và `\\` là một backslash dữ liệu:

- Dữ liệu `a\|b|c` phải có hai token: `a|b` và `c`.
- Dữ liệu `a\\|b` có một backslash dữ liệu rồi một delimiter thực, nên thành `a\` và `b`.

Quy tắc đơn giản “hễ dấu `|` có backslash đứng ngay trước thì bỏ qua” sẽ sai khi có hai hoặc nhiều backslash liên tiếp. Thao tác `replace("\\|", "|")` **trước khi tách** còn có thể làm mất thông tin delimiter nào vốn đã bị escape. Cách an toàn là parser đọc tuần tự và giữ trạng thái escape, hoặc dùng thư viện hiểu chính xác grammar.

### Ví dụ 2 — parser nhỏ cho định dạng tự định nghĩa có `\|` và `\\`

Đây là **một định dạng minh họa do ta quy định**, không phải CSV: delimiter là `|`; chỉ hai escape hợp lệ là `\|` và `\\`; mọi escape khác phải báo lỗi. Nó cho thấy vì sao cần nhìn từng ký tự trong bối cảnh.

```java
// BackslashDelimitedDemo.java
import java.util.ArrayList;
import java.util.List;

public class BackslashDelimitedDemo {
    static List<String> parse(String input) {
        List<String> fields = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        boolean escaped = false;

        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);

            if (escaped) {
                if (c != '|' && c != '\\') {
                    throw new IllegalArgumentException(
                            "Unsupported escape: \\" + c);
                }
                field.append(c);
                escaped = false;
            } else if (c == '\\') {
                escaped = true;
            } else if (c == '|') {
                fields.add(field.toString());
                field.setLength(0);
            } else {
                field.append(c);
            }
        }

        if (escaped) {
            throw new IllegalArgumentException("Trailing backslash");
        }

        fields.add(field.toString());
        return fields;
    }

    public static void main(String[] args) {
        List<String> fields = parse("alpha\\|beta|gamma\\\\delta||");
        System.out.println("count=" + fields.size());
        System.out.println("first=" + fields.get(0));
        System.out.println("second=" + fields.get(1));
        System.out.println("emptyThird=" + fields.get(2).isEmpty());
        System.out.println("emptyFourth=" + fields.get(3).isEmpty());
    }
}
```

```bash
javac BackslashDelimitedDemo.java
java BackslashDelimitedDemo
```

Kết quả:

```text
count=4
first=alpha|beta
second=gamma\delta
emptyThird=true
emptyFourth=true
```

Bộ parser giữ trạng thái `escaped`; khi gặp backslash thì ký tự sau đó được xử lý như dữ liệu theo hai escape được cho phép. Nó cũng giữ nguyên trường rỗng ở cuối và báo lỗi nếu input kết thúc giữa một escape. Đây mới chỉ là **grammar một tầng rất nhỏ**: để hỗ trợ escape Unicode, dấu nháy, nesting, giới hạn kích thước, dòng và cột lỗi..., phải mở rộng parser có chủ đích, không âm thầm chấp nhận cú pháp ngoài hợp đồng.

## 4. CSV: dấu nháy quyết định dấu phẩy và newline có phải delimiter không

Với kiểu CSV dùng dấu `"` cho quoted field và `""` để escape quote:

1. Ngoài quoted field, dấu phẩy phân cách các trường; CR/LF hoặc CRLF kết thúc bản ghi.
2. Bên trong quoted field, dấu phẩy và newline là **dữ liệu của field**.
3. `""` bên trong quoted field biểu diễn một dấu nháy `"` trong giá trị.
4. Dấu nháy mở/đóng hợp lệ phụ thuộc vị trí; một dấu nháy sai chỗ là lỗi cú pháp.
5. Một bản ghi chỉ kết thúc ở newline khi parser **không ở trong quoted field**.

Quy tắc này giải thích vì sao `BufferedReader.readLine()` là công cụ đọc dòng vật lý nhưng **không thể tự quyết định ranh giới bản ghi CSV**. Parser phải giữ trạng thái khi đọc qua newline.

### 4.1. Mô hình trạng thái

Một parser CSV strict có thể sử dụng bốn trạng thái:

| Trạng thái | Ý nghĩa | Chuyển trạng thái điển hình |
| --- | --- | --- |
| `START` | Đang ở đầu một trường | `"` → `QUOTED`; ký tự thường → `PLAIN`; `,` → kết thúc trường rỗng. |
| `PLAIN` | Đang trong trường không có trích dẫn | `,` → kết thúc trường; newline → kết thúc bản ghi; `"` → lỗi. |
| `QUOTED` | Đang ở trong trường có dấu nháy | Delimiter/newline thành dữ liệu; `""` thêm một dấu nháy; dấu nháy đóng → `AFTER_QUOTE`. |
| `AFTER_QUOTE` | Vừa đóng trường trích dẫn | Chỉ chấp nhận dấu phẩy, newline hoặc EOF; ký tự khác → lỗi ở chế độ strict. |

Parser có thể đọc bằng `Reader` theo từng ký tự. `PushbackReader` giúp nhìn thêm một ký tự khi gặp dấu `"` mà không đánh mất ký tự kế tiếp.

### Ví dụ 3 — parser CSV minh họa có quoted newline và `""`

Ví dụ sau hỗ trợ **tập con CSV được xác định rõ**: delimiter `,`, quote `"`, quote escape bằng `""`, newline ngoài quote ngăn bản ghi, CRLF được nhận là một dấu kết thúc bản ghi, newline trong quote được giữ nguyên. Bộ parser **không** tự bỏ khoảng trắng quanh quote và không hỗ trợ những dialect CSV khác; mục tiêu là làm rõ state machine.

```java
// QuotedCsvDemo.java
import java.io.IOException;
import java.io.PushbackReader;
import java.io.Reader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

public class QuotedCsvDemo {
    enum State { START, PLAIN, QUOTED, AFTER_QUOTE }

    static List<List<String>> parse(Reader source) throws IOException {
        PushbackReader input = new PushbackReader(source, 1);
        List<List<String>> records = new ArrayList<>();
        List<String> record = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        State state = State.START;
        boolean recordStarted = false;
        int value;

        while ((value = input.read()) != -1) {
            char c = (char) value;

            if (state == State.QUOTED) {
                if (c == '"') {
                    int next = input.read();
                    if (next == '"') {
                        field.append('"');
                    } else {
                        state = State.AFTER_QUOTE;
                        if (next != -1) {
                            input.unread(next);
                        }
                    }
                } else {
                    field.append(c);
                }
                continue;
            }

            if (state == State.AFTER_QUOTE
                    && c != ',' && c != '\r' && c != '\n') {
                throw new IOException("Unexpected char after closing quote");
            }

            if (c == ',') {
                record.add(field.toString());
                field.setLength(0);
                state = State.START;
                recordStarted = true;
            } else if (c == '\r' || c == '\n') {
                if (c == '\r') {
                    int next = input.read();
                    if (next != '\n' && next != -1) {
                        input.unread(next);
                    }
                }

                record.add(field.toString());
                records.add(record);
                record = new ArrayList<>();
                field.setLength(0);
                state = State.START;
                recordStarted = false;
            } else if (c == '"' && state == State.START) {
                state = State.QUOTED;
                recordStarted = true;
            } else if (c == '"') {
                throw new IOException("Quote inside unquoted field");
            } else {
                field.append(c);
                state = State.PLAIN;
                recordStarted = true;
            }
        }

        if (state == State.QUOTED) {
            throw new IOException("Unterminated quoted field");
        }

        if (recordStarted || !record.isEmpty()) {
            record.add(field.toString());
            records.add(record);
        }

        return records;
    }

    public static void main(String[] args) throws Exception {
        String csv =
                "id,note\n"
                + "1,\"Hello, world\"\n"
                + "2,\"line one\nline two\"\n"
                + "3,\"He said \"\"Hi\"\"\"\n";

        try (Reader source = new StringReader(csv)) {
            List<List<String>> records = parse(source);
            System.out.println("records=" + records.size());

            for (List<String> row : records) {
                System.out.println(row.get(0) + " | "
                        + row.get(1).replace("\n", "\\n"));
            }
        }
    }
}
```

```bash
javac QuotedCsvDemo.java
java QuotedCsvDemo
```

Kết quả:

```text
records=4
id | note
1 | Hello, world
2 | line one\nline two
3 | He said "Hi"
```

Ở trường thứ ba, ký tự `\n` thực nằm **bên trong quoted field**, được giữ trong field và chỉ đổi thành hai ký tự hiển thị `\` + `n` ở lúc `println` để đầu ra dễ quan sát. Kết quả có bốn bản ghi (một header, ba data), dù dữ liệu thô chứa năm dòng vật lý.

Parser minh họa này không gọi `input.close()` trong `parse` vì `Reader` được **caller truyền vào**; caller giữ quyền đóng nguồn bằng `try-with-resources`. `PushbackReader` được dùng trong phạm vi hàm và không được giữ lại; khi caller đóng nguồn thì tài nguyên bên dưới được giải phóng. Đây là cách làm rõ ranh giới sở hữu tài nguyên khi chuyển từ xử lý từng dòng sang parser tuần tự.

**Giới hạn của ví dụ:** Nó giữ nguyên newline nằm trong quote (bao gồm `\r\n` nếu có), không có tùy chọn escape bằng backslash, không chấp nhận ký tự khoảng trắng sau quote đóng, không tự kiểm tra số trường cố định và chưa có chính sách giới hạn kích thước hay báo vị trí dòng/cột. Một parser CSV cho dữ liệu production còn phải quyết định các dialect và yêu cầu này. Nếu định dạng được định nghĩa là CSV thực tế với nguồn dữ liệu khác nhau, thư viện CSV chuyên dụng thường an toàn, dễ bảo trì hơn việc tự viết.

## 5. Không phải CSV: JSON, XML, log và dữ liệu lồng nhau

### JSON

Trong JSON, dấu phẩy ngăn phần tử mảng/thuộc tính object **chỉ khi nằm đúng mức cấu trúc**. Các dấu phẩy bên trong chuỗi hoặc đối tượng/mảng lồng nhau không có cùng ý nghĩa.

Ví dụ JSON:

```json
{
  "name": "Lan, An",
  "tags": ["java", "io"],
  "meta": {"message": "Có dấu phẩy, và escape \""}
}
```

Chuỗi chứa `\"` (một dấu quote được escape theo cú pháp JSON), các mảng/object có nesting, và các giá trị có thể chứa escape Unicode. `text.split(",")`, `text.split(":")` hoặc `replace("\\\"", "\"")` áp dụng mù quáng sẽ phá cấu trúc hoặc thay đổi giá trị. Dùng **JSON parser** (ví dụ Jackson hoặc một API JSON phù hợp với dự án) để parse thành cây hoặc đọc streaming theo token. Không dùng `String.split()` để mô phỏng JSON parser.

Đối với **JSON Lines/NDJSON**, hợp đồng thường yêu cầu *mỗi dòng vật lý chứa đúng một JSON value hoàn chỉnh*; khi đúng hợp đồng này, đọc từng dòng rồi truyền từng dòng cho **JSON parser** là hợp lý. Nhưng đó là ràng buộc của format NDJSON, không phải bằng chứng rằng có thể chia JSON tùy ý theo newline.

### XML/HTML

Dấu `>` có thể xuất hiện trong thuộc tính được trích dẫn; entity như `&amp;` và các cấu trúc CDATA có ngữ nghĩa riêng. `split("<")` / `split(">")` không hiểu DOM, namespace hoặc encoding. Với XML, dùng XML parser (`SAX`, `StAX` hoặc `DOM`) phù hợp mục đích; đặc biệt khi nhận dữ liệu không tin cậy, cấu hình parser để kiểm soát external entities và tài nguyên.

### Log có quote

Một log định dạng kiểu:

```text
127.0.0.1 "GET /search?q=a,b HTTP/1.1" 200
```

Nếu dùng `split(" ")`, request sẽ bị chia thành các token lẻ. Nếu format quy định quoted string và escape, phải parse theo đúng quote grammar, hoặc dùng log parser tương ứng. Không tự suy quy tắc CSV cho log chỉ vì chúng cùng có dấu nháy.

### URL/form encoding

Các ký tự `%2C`, `%26` hoặc `%3D` được mã hóa theo quy tắc percent-encoding, không phải cú pháp backslash/CSV. Thứ tự tách **cặp key/value** và giải mã có thể ảnh hưởng ý nghĩa khi dấu `&` hoặc `=` cũng nằm trong dữ liệu mã hóa. Hãy dùng parser của giao thức URL/form được chuẩn hóa, thay vì `split("&")` và tự decode tùy ý trên đầu vào bất kỳ.

## 6. Nên dùng công cụ nào trong Java?

| Dạng dữ liệu | Cách làm phù hợp | Khi nào `split()` là đủ? |
| --- | --- | --- |
| Mỗi dòng thực sự là một record và delimiter không thể nằm trong field | `BufferedReader.readLine()` rồi `split(Pattern.quote(delimiter), -1)` | Có, nếu quy tắc tách thật sự đơn giản. |
| File CSV có quoted fields, dấu phẩy hoặc newline bên trong field | CSV parser theo dialect; có thể dùng Apache Commons CSV hoặc parser CSV tương đương | Chỉ với một tập con CSV đã kiểm soát chặt, không có quoting/escape. |
| TSV có escape, quote, hoặc multiline | Parser theo đặc tả TSV thực tế; TSV không có một grammar escape duy nhất | Chỉ khi delimiter và newline được bảo đảm không nằm trong dữ liệu. |
| JSON / NDJSON | JSON parser (chẳng hạn Jackson). Với NDJSON, có thể đọc từng dòng rồi parse từng value. | Không dùng split để parse cấu trúc JSON. |
| XML | SAX/StAX/DOM với cấu hình phù hợp | Không dùng split để parse XML. |
| Protocol dạng record có length prefix | Đọc số byte/char theo framing, sau đó parse payload | Không dựa vào dấu xuống dòng làm boundary nếu protocol không quy định như vậy. |
| Định dạng tự tạo với `\` escape | Parser trạng thái nhỏ, có hợp đồng và test | Có thể chỉ với delimiter không escape; khi đã có escape cần trạng thái. |

`Scanner` cũng dựa vào delimiter regex trong các thao tác phân tách. `Scanner.useDelimiter(...)` giúp thay delimiter, nhưng **không biến `Scanner` thành CSV hoặc JSON parser**. `Files.lines()` cung cấp stream các **dòng vật lý** chứ không tự gom lại trường CSV multiline. Nếu cần parse streaming, hãy tổ chức parser đọc dần từ `Reader`/`InputStream` và phát ra bản ghi logic đúng ranh giới.

Không có thư viện CSV bắt buộc nào trong Java SE chuyên giải mọi dialect; nếu chọn dependency bên ngoài, phải thống nhất phiên bản/dialect, charset, dấu nháy, escape, header, khoảng trắng, cách xử lý dòng rỗng và lỗi dữ liệu theo yêu cầu dự án.

## 7. Những khác biệt cú pháp cần xác định trước khi parse

Đối với format có escape, parser phải có **hợp đồng rõ ràng**, thay vì tự phỏng đoán:

1. **Charset:** byte đầu vào là UTF-8 hay encoding khác? BOM có hợp lệ không? Decoder xử lý chuỗi byte lỗi ra sao?
2. **Record boundary:** newline vật lý có luôn kết thúc bản ghi không? Có `\n`, `\r\n`, hoặc `\r` không? Newline trong quoted field được giữ hay chuẩn hóa?
3. **Delimiter:** dấu phẩy, tab, `|`, dấu chấm phẩy hay chuỗi nhiều ký tự? Delimiter có nghĩa khi nào?
4. **Quote:** quote mở/đóng bằng ký tự nào? Có cho quote bên trong unquoted field không? Khoảng trắng trước/sau quote có hợp lệ không?
5. **Escape:** dùng `""`, `\"`, `\\`, `%xx`, hay cơ chế khác? Escape sai cú pháp được báo lỗi hay giữ nguyên?
6. **Trường rỗng:** `a,,` biểu diễn bao nhiêu trường? Record trống có một field rỗng, hay nên bỏ qua? Chuỗi `""` và field không quoted có cùng ý nghĩa không?
7. **Giới hạn:** tối đa bao nhiêu byte, số ký tự, độ sâu lồng nhau, trường và bản ghi? Parser phải chặn input khổng lồ khi đọc từ nguồn không tin cậy.
8. **Schema:** số field mỗi record có cố định không? Header có bắt buộc không? Có kiểu số/ngày tháng cần kiểm tra sau khi tách field không?
9. **Lỗi:** thiếu quote đóng, ký tự escape cuối file, ký tự dư sau quote đóng cần báo ở đâu? Có phục hồi một bản ghi lỗi và đọc tiếp hay phải dừng?
10. **Ownership:** caller hay parser sẽ đóng `Reader`/`InputStream`? Nên ghi rõ để tránh parser đóng luồng dùng chung ngoài dự kiến.

Đừng unescape toàn bộ chuỗi **trước** khi xác định cấu trúc: bước đó có thể biến delimiter vốn là dữ liệu thành delimiter thật. Trình tự đúng tùy định dạng, nhưng thường là **nhận diện cấu trúc theo trạng thái rồi giải mã nội dung field** khi grammar đã rõ.

## 8. Xử lý streaming, lỗi và ranh giới ký tự

Một parser dữ liệu lớn thường cần đọc theo từng phần thay vì `Files.readString()` toàn bộ file:

- **Giữ trạng thái qua các lần đọc:** một dấu nháy mở ở cuối chunk chỉ có thể đóng ở chunk sau; tương tự một escape `\` có thể nằm đúng mép buffer.
- **Không giả định một lần `Reader.read(buffer)` là một record:** `read` trả bao nhiêu `char` còn phụ thuộc bộ đệm; ranh giới chunk không quyết định ranh giới logic.
- **Đếm đơn vị đúng:** `Reader` trả các đơn vị UTF-16; payload protocol đôi khi quy định độ dài bằng byte, nên phải decode/parse đúng thứ tự.
- **Giữ vị trí lỗi:** số dòng, cột, record và field giúp phát hiện input hỏng. Với quoted multiline, số dòng vật lý không trùng số record.
- **Dùng giới hạn tài nguyên:** giới hạn độ dài quoted field, số phần tử/nesting và timeout cho nguồn mạng theo nhu cầu. Một field chưa đóng quote có thể khiến parser giữ dữ liệu rất lâu.
- **Quản lý nguồn:** đóng reader trong `try-with-resources` ở tầng sở hữu, xử lý `IOException` đúng chỗ. Nếu phương thức parser chỉ được truyền reader mượn, không tự đóng nguồn trừ khi hợp đồng nói vậy.

### Kiểm thử để tránh parser có vẻ chạy đúng nhưng vẫn sai

Với CSV, tối thiểu kiểm thử các chuỗi: `a,b`, `a,,b`, `a,b,`, `"a,b",c`, `"a\nb",c`, `"He said ""Hi""",x`, file rỗng, dấu `\r\n`, dấu nháy chưa đóng và ký tự dư sau nháy đóng. Với backslash escape, kiểm thử dấu delimiter đã escape, một và hai backslash, escape cuối input, escape không hợp lệ và hai delimiter liên tiếp. Với JSON, kiểm thử dấu phẩy/dấu hai chấm trong string, escaped quote, mảng/object lồng nhau và input JSON thiếu dấu đóng.

Không chỉ so khớp **số lượng token**; cần so khớp chính xác **giá trị sau giải escape**, phân biệt field rỗng với record rỗng, và bảo đảm dữ liệu hỏng tạo lỗi thay vì bị âm thầm diễn giải sai.

## 9. Các lỗi phổ biến và hậu quả

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đọc CSV bằng `readLine()` rồi `split(",")` | Phá record multiline và field chứa dấu phẩy | Dùng CSV parser biết quote và record boundary. |
| Tưởng `split()` nhận delimiter literal | `|` hoặc `.` bị hiểu theo regex | Dùng `Pattern.quote(delimiter)` khi grammar đơn giản. |
| Không truyền `limit=-1` khi trường cuối có thể rỗng | Mất field rỗng ở cuối | Dùng `split(regex, -1)` cho dữ liệu phù hợp với split. |
| Unescape trước khi tách | Delimiter thuộc dữ liệu bị biến thành delimiter thật | Parse cấu trúc trước, decode field theo grammar. |
| Chỉ nhìn một ký tự trước delimiter | Sai với nhiều backslash liên tiếp | Theo dõi trạng thái escape và số lượng ký tự. |
| Tự dùng regex cho JSON/XML tổng quát | Sai với quote, nesting, entity và escape | Dùng parser chuyên dụng. |
| Xem mỗi chunk từ `Reader` là một dòng/record | Cắt đôi quote, escape hoặc Unicode | Duy trì trạng thái qua các lần đọc. |
| Im lặng chấp nhận dấu nháy không đóng | Dữ liệu hỏng được hiểu như dữ liệu hợp lệ | Báo lỗi cú pháp với vị trí nếu có thể. |
| Không giới hạn field khi đọc nguồn ngoài | Có thể tiêu thụ rất nhiều RAM/CPU | Đặt giới hạn dung lượng, độ sâu, số record và chính sách lỗi. |

## 10. Tự kiểm tra

**Câu 1.** Vì sao `readLine()` có thể sai khi lấy từng bản ghi CSV?

**Đáp án:** Một trường CSV quoted có thể chứa newline; một bản ghi logic có thể gồm nhiều dòng vật lý.

**Câu 2.** `"a,b",c` được `split(",")` thành bao nhiêu phần, còn CSV parser đúng thành bao nhiêu trường?

**Đáp án:** `split(",")` tạo ba phần do dấu phẩy nằm trong quote; CSV parser đúng tạo hai trường: `a,b` và `c`.

**Câu 3.** `"x|y||".split("\\|")` có giữ hai trường rỗng cuối không?

**Đáp án:** Không; dùng `split("\\|", -1)` khi hai trường rỗng cuối phải được giữ.

**Câu 4.** `Pattern.quote("|")` có làm `String.split()` hiểu được `a\|b|c` theo quy tắc escape backslash không?

**Đáp án:** Không. Nó chỉ xử lý cách biểu diễn dấu `|` **trong regex**, không thêm grammar escape cho nội dung đầu vào.

**Câu 5.** Vì sao gặp `\|` và `\\|` cần theo dõi trạng thái, không chỉ nhìn ký tự ngay trước `|`?

**Đáp án:** Trong quy ước ví dụ, `\|` biểu diễn delimiter thuộc dữ liệu; `\\|` biểu diễn một backslash thuộc dữ liệu rồi đến delimiter thật.

**Câu 6.** Muốn đọc JSON có object lồng nhau và escaped quote, dùng phương án nào?

**Đáp án:** Dùng JSON parser hiểu cấu trúc và escape. Nếu đầu vào là NDJSON hợp lệ, có thể lấy từng dòng vật lý rồi parse **từng JSON value**.

**Câu 7.** Nếu đang đọc bằng `Reader` mà quote mở nằm ở cuối buffer, parser có được kết thúc record không?

**Đáp án:** Không; phải giữ trạng thái quote sang lần đọc kế tiếp và chỉ kết thúc record khi grammar cho phép.

**Nguyên tắc cần nhớ:** `readLine()` chia theo newline vật lý, `split()` chia theo regex; **không phương thức nào tự hiểu ranh giới bản ghi, escape, quote hay nesting**. Dùng chúng cho dữ liệu có grammar đơn giản đã kiểm soát; dùng parser có trạng thái hoặc thư viện đúng định dạng khi cấu trúc và escape phức tạp.

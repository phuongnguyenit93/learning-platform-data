# StreamTokenizer và lựa chọn công cụ phân tích phù hợp trong Java I/O

## 1. Mục tiêu và vị trí của `StreamTokenizer`

Khi đọc văn bản, chương trình thường cần đi xa hơn thao tác đọc từng ký tự hoặc từng dòng: phải nhận biết **từ**, **số**, **dấu phân cách** và đôi khi là **chuỗi nằm trong dấu nháy**. Công việc tách văn bản thành các phần tử có ý nghĩa này gọi là *tokenization* (phân tách token). Java cung cấp lớp lâu đời `java.io.StreamTokenizer` để đọc từng token từ luồng ký tự và cho phép tùy chỉnh một số quy tắc nhận diện.

Bài học thuộc chủ đề **Dòng và token** của Java Core I/O. Sau khi học, bạn cần:

- Biết khi nào dùng `StreamTokenizer`, hiểu vòng lặp `nextToken()`, các hằng `TT_WORD`, `TT_NUMBER`, `TT_EOL`, `TT_EOF` và các trường `ttype`, `sval`, `nval`.
- Hiểu cách định nghĩa ký tự cấu thành từ, khoảng trắng, dấu nháy, comment, số, ký tự thường và dấu xuống dòng.
- Viết chương trình Java 17+ xử lý token, phân biệt EOF và EOL, lấy thông tin dòng, quản lý `Reader` và xử lý lỗi.
- Biết giới hạn của tokenizer: **tách token chưa phải phân tích cú pháp (parsing)**, không tự hiểu CSV/JSON, không tự xác thực quy tắc ngữ nghĩa.
- Chọn đúng công cụ giữa `StreamTokenizer`, `Scanner`, `BufferedReader` + xử lý chuỗi/regex, parser CSV/JSON và lexer/parser chuyên dụng.

**Thông điệp chính:** `StreamTokenizer` phù hợp khi đầu vào là một ngôn ngữ văn bản **đơn giản, có quy tắc token rõ và cần đọc lần lượt từ `Reader`**. Với định dạng chuẩn hoặc ngữ pháp phức tạp, hãy chọn parser dành riêng cho định dạng đó.

## 2. Phân biệt ký tự, dòng, token và cấu trúc

Giả sử đầu vào:

```text
total = 12.5
name = "Ada Lovelace"
```

Có nhiều cấp độ xử lý:

1. **Đọc ký tự:** `Reader.read()` cung cấp các đơn vị `char` và thông báo EOF bằng `-1`.
2. **Đọc dòng:** `BufferedReader.readLine()` trả về chuỗi một dòng, không giữ ký tự kết thúc dòng; kết quả là `null` khi hết dòng.
3. **Tách token:** tokenizer nhận biết `total` là word, `=` là dấu riêng, `12.5` là number; ở dòng sau, `"Ada Lovelace"` được nhận diện như một quoted token theo cú pháp được cấu hình.
4. **Parsing:** bộ phân tích hiểu rằng cấu trúc phải là `name = value`, kiểm tra tên khóa hợp lệ, giá trị đúng kiểu, thứ tự hay dấu bắt buộc.
5. **Validation/ngữ nghĩa:** ứng dụng kiểm tra `total` không âm, `name` không rỗng hoặc giá trị nằm trong miền cho phép.

Tokenization **không tự đảm nhận** bước 4 và bước 5. Một dãy token hợp lệ ở mức lexical vẫn có thể là cấu hình hoặc biểu thức sai.

| Mục tiêu | Thao tác/công cụ |
| --- | --- |
| Chỉ cần giữ nguyên từng dòng văn bản | `BufferedReader.readLine()` |
| Đọc chuỗi/từ/số từ input đơn giản | `Scanner` hoặc `StreamTokenizer` |
| Điều khiển phân loại ký tự và các token riêng | `StreamTokenizer` |
| Tách log theo quy tắc rõ, ít phức tạp | Đọc từng dòng + phương thức chuỗi/`Pattern` |
| Đọc CSV theo RFC hoặc yêu cầu có quote, dấu phẩy trong trường, xuống dòng trong trường | Thư viện CSV chuyên dụng |
| Đọc JSON có nested object/array, escape, Unicode | Thư viện JSON có parser chuẩn |
| Ngôn ngữ riêng với grammar, precedence, vị trí token, thông báo lỗi chi tiết | Lexer/parser chuyên dụng hoặc generator như ANTLR |

## 3. Cơ chế của `java.io.StreamTokenizer`

Tạo tokenizer từ một `Reader`:

```java
java.io.StreamTokenizer tokenizer =
        new java.io.StreamTokenizer(reader);
```

`reader` là một `Reader` đã được mở. `nextToken()` đọc tiếp một token và trả về mã loại token (`int`); đồng thời cập nhật trạng thái tokenizer:

| Thành phần | Ý nghĩa | Cách lấy |
| --- | --- | --- |
| `StreamTokenizer.TT_WORD` | Token được phân loại là từ | Khi trả về loại này, lấy nội dung ở `tokenizer.sval` |
| `StreamTokenizer.TT_NUMBER` | Token được phân loại là số | Khi trả về loại này, lấy giá trị kiểu `double` ở `tokenizer.nval` |
| `StreamTokenizer.TT_EOL` | Ký hiệu kết thúc dòng (nếu bật `eolIsSignificant(true)`) | Không coi là nội dung chuỗi |
| `StreamTokenizer.TT_EOF` | Hết luồng đầu vào | Dừng vòng lặp, không đọc tiếp |
| Mã của một ký tự thông thường hoặc ký tự quote | Ví dụ `'='`, `'+'`, `'"'` | Với dấu thông thường: xử lý ký tự; với quoted token: `sval` chứa nội dung bên trong |
| `tokenizer.ttype` | Loại của token cuối cùng | Có thể dùng thay cho mã `int` do `nextToken()` trả về |
| `tokenizer.sval` | Nội dung của token dạng word hoặc quoted string | Chỉ diễn giải theo loại token tương ứng |
| `tokenizer.nval` | Giá trị số dưới dạng `double` | Chỉ diễn giải khi loại là `TT_NUMBER` |
| `tokenizer.lineno()` | Dòng hiện tại theo bộ đếm tokenizer | Dùng bổ sung ngữ cảnh lỗi, không phải cột/khoảng ký tự |

Có thể xử lý token bằng vòng lặp:

```java
int type;
while ((type = tokenizer.nextToken()) != StreamTokenizer.TT_EOF) {
    if (type == StreamTokenizer.TT_WORD) {
        // Dùng tokenizer.sval
    } else if (type == StreamTokenizer.TT_NUMBER) {
        // Dùng tokenizer.nval
    } else {
        // Xử lý dấu, chuỗi quoted hoặc EOL tùy cấu hình
    }
}
```

Đoạn trên **chỉ minh họa cấu trúc**, chưa phải chương trình độc lập: biến `tokenizer` phải được tạo từ một `Reader` và quản lý vòng đời nguồn đúng cách.

### 3.1. EOF khác EOL

- **EOF** (`TT_EOF`): nguồn không còn token nào; phải kết thúc vòng lặp đọc token.
- **EOL** (`TT_EOL`): ranh giới dòng *khi được bật*; người dùng có thể tiếp tục đọc token ở dòng kế tiếp.
- Theo cấu hình mặc định, kết thúc dòng thường được bỏ qua như whitespace. Gọi `eolIsSignificant(true)` nếu grammar coi dòng là ranh giới bản ghi.
- `lineno()` hữu ích để đưa số dòng vào thông báo lỗi, nhưng tokenizer không tự lưu vị trí cột hoặc vị trí byte của từng token.

Nếu ứng dụng cần phân biệt **dòng trống**, **kết thúc record**, hoặc các trường theo từng dòng, EOL có thể quan trọng. Nếu ngữ pháp cho phép record trải trên nhiều dòng, việc dừng ở EOL có thể làm hỏng quá trình phân tích.

### 3.2. Số được lưu dạng `double`

Khi `TT_NUMBER` xuất hiện, `nval` là `double`. Với số nguyên lớn hơn miền chính xác của binary floating-point, số thập phân cần độ chính xác tài chính hoặc số có định dạng đặc biệt, không được xem đây là parser số “không mất thông tin”.

Ví dụ nguyên 64-bit lớn có thể bị làm tròn khi đi qua `double`; số tiền `0.1` không có biểu diễn nhị phân hữu hạn chính xác. Nếu dữ liệu cần giữ nguyên các chữ số, hãy đọc token **dạng chuỗi** theo grammar phù hợp rồi dùng `Long.parseLong`, `BigInteger` hoặc `BigDecimal` cùng validation; đừng chuyển qua `nval` trước.

## 4. Java 17+: ví dụ đầy đủ nhận dạng word, number, ký hiệu, quoted string và EOL

Ví dụ cố định đầu vào trong `StringReader` để kết quả kiểm thử ổn định. Khi áp dụng thực tế, có thể dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` thay `StringReader`. `StringReader` là nguồn ở bộ nhớ, thích hợp cho dữ liệu mẫu ngắn.

Lưu mã vào **`StreamTokenizerDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StreamTokenizer;
import java.io.StringReader;

public class StreamTokenizerDemo {
    public static void main(String[] args) throws IOException {
        String input = "total = 12.5\nname = \"Ada Lovelace\"\n";

        try (Reader reader = new StringReader(input)) {
            StreamTokenizer tokenizer = new StreamTokenizer(reader);
            tokenizer.eolIsSignificant(true);

            while (true) {
                int type = tokenizer.nextToken();

                if (type == StreamTokenizer.TT_EOF) {
                    System.out.println("EOF");
                    break;
                }
                if (type == StreamTokenizer.TT_EOL) {
                    System.out.println("EOL");
                } else if (type == StreamTokenizer.TT_WORD) {
                    System.out.println("WORD " + tokenizer.sval);
                } else if (type == StreamTokenizer.TT_NUMBER) {
                    System.out.println("NUMBER " + tokenizer.nval);
                } else if (type == '"') {
                    System.out.println("QUOTED " + tokenizer.sval);
                } else {
                    System.out.println("CHAR " + (char) type);
                }
            }
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 StreamTokenizerDemo.java
java StreamTokenizerDemo
```

**stdout của ví dụ:**

```text
WORD total
CHAR =
NUMBER 12.5
EOL
WORD name
CHAR =
QUOTED Ada Lovelace
EOL
EOF
```

**Giải thích:**

- `total` và `name` là `TT_WORD`; nội dung nằm ở `sval`.
- `12.5` là `TT_NUMBER`; `nval` hiển thị `12.5`.
- Dấu `=` là ký tự riêng, nên nhánh cuối in `CHAR =`.
- Dấu `"` báo một quoted token; `sval` chứa `Ada Lovelace`, gồm cả khoảng trắng ở giữa nhưng không gồm dấu quote bao quanh.
- Do đã gọi `eolIsSignificant(true)` và input có ký tự `\n` ở cuối **cả hai dòng**, ta nhận hai token `EOL` trước `EOF`.
- `try-with-resources` đóng `Reader`. Bản thân `StreamTokenizer` không phải tài nguyên cần đóng riêng, nhưng reader nguồn thường cần được đóng, nhất là khi mở file/socket.

Đây là ví dụ về **phân loại token**, chưa hề xác minh rằng dấu `=` phải nằm giữa tên và giá trị. Muốn thực thi grammar, hãy thêm các bước “chờ tên khóa → đòi dấu bằng → đòi giá trị” và báo lỗi nếu gặp loại token không mong đợi.

## 5. Tùy chỉnh cú pháp: sử dụng đúng các phương thức cấu hình

Một ưu thế chính của `StreamTokenizer` là có thể định nghĩa ký tự nào được xem là word, whitespace, comment, quote và ký tự đơn.

| Phương thức | Tác dụng | Điều cần lưu ý |
| --- | --- | --- |
| `wordChars(low, high)` | Đặt dải ký tự thành thành phần của word | Dải cấu hình chỉ là một phần của grammar; không tự hiểu identifier Java đầy đủ |
| `whitespaceChars(low, high)` | Đặt dải ký tự làm whitespace | Dễ vô tình bỏ dấu phân cách nếu cấu hình quá rộng |
| `ordinaryChar(ch)` / `ordinaryChars(low, high)` | Phân loại ký tự thành token riêng | Có thể ghi đè vai trò word/whitespace/comment/quote trước đó |
| `quoteChar(ch)` | Đặt ký tự làm dấu mở/đóng chuỗi quoted | Không đồng nghĩa parser chuỗi JSON hay CSV chuẩn |
| `commentChar(ch)` | Đặt ký tự bắt đầu comment đến hết dòng | Chỉ có ý nghĩa nếu grammar định nghĩa đúng comment |
| `slashSlashComments(true)` | Nhận dạng comment dạng `//` | Cần cân nhắc khi văn bản có URL/đường dẫn chứa `//` |
| `slashStarComments(true)` | Nhận dạng comment dạng `/* ... */` | Không mặc nhiên xử lý mọi trường hợp ngữ pháp comment lồng nhau |
| `parseNumbers()` | Bật cách nhận diện số của tokenizer | Số trả về kiểu `double`; không thay parser số chính xác |
| `eolIsSignificant(true)` | Đưa EOL vào dãy token | Không đồng nghĩa với đọc dòng hoàn chỉnh |
| `lowerCaseMode(true)` | Chuyển token word thành chữ thường | Có thể làm mất phân biệt hoa/thường quan trọng |
| `resetSyntax()` | Đặt lại phân loại ký tự | Phải cấu hình lại word/whitespace/quote/number/comment theo nhu cầu |
| `pushBack()` | Đưa token vừa đọc trở lại để `nextToken()` trả lại một lần | Chỉ hỗ trợ nhìn trước rất hạn chế, không phải bộ đệm token tùy ý |

### 5.1. Đặt identifier có dấu gạch dưới và comment dấu `#`

Mặc định, không nên giả định identifier như `user_name` sẽ được nhận dạng theo đúng grammar mong muốn. Với file cấu hình đơn giản, ta có thể bổ sung ký tự `_` vào word và xem `#` là comment.

Lưu thành **`ConfiguredTokenizerDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StreamTokenizer;
import java.io.StringReader;

public class ConfiguredTokenizerDemo {
    public static void main(String[] args) throws IOException {
        String source =
                "user_name = \"Ada Lovelace\" # annotation\n"
                + "attempts = 3";

        try (Reader reader = new StringReader(source)) {
            StreamTokenizer tokenizer = new StreamTokenizer(reader);
            tokenizer.wordChars('_', '_');
            tokenizer.commentChar('#');

            int type;
            while ((type = tokenizer.nextToken())
                    != StreamTokenizer.TT_EOF) {
                if (type == StreamTokenizer.TT_WORD) {
                    System.out.println("WORD " + tokenizer.sval);
                } else if (type == StreamTokenizer.TT_NUMBER) {
                    System.out.println("NUMBER " + tokenizer.nval);
                } else if (type == '"') {
                    System.out.println("QUOTED " + tokenizer.sval);
                } else {
                    System.out.println("CHAR " + (char) type);
                }
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConfiguredTokenizerDemo.java
java ConfiguredTokenizerDemo
```

**stdout:**

```text
WORD user_name
CHAR =
QUOTED Ada Lovelace
WORD attempts
CHAR =
NUMBER 3.0
```

**Giải thích:** `wordChars('_', '_')` giúp `user_name` là một token word. `commentChar('#')` bỏ phần sau `#` đến hết dòng. Vì không bật EOL như ví dụ trước, chương trình không in `EOL`. `attempts = 3` vẫn được phân loại thành word, dấu, number. Giá trị `3` thể hiện thành `3.0` vì `nval` có kiểu `double`.

Hai chương trình trên cho thấy cú pháp của `StreamTokenizer` đủ tiện lợi cho một tập token nhỏ. Tuy nhiên, mã mới **chỉ in token**; parser thực tế vẫn phải bắt lỗi trường thiếu, trùng khóa, giá trị sai kiểu, comment không được phép và thứ tự không hợp lệ.

### 5.2. Cẩn trọng với `resetSyntax()` và thay đổi ưu tiên ký tự

Gọi `resetSyntax()` làm mất các quy tắc có sẵn; nếu tiếp đó chỉ gọi `wordChars('a', 'z')` mà quên whitespace, số và quote, tokenizer sẽ không còn xử lý giống mặc định. Hãy lập một bảng grammar mong muốn trước khi viết các lệnh cấu hình và dùng test cho:

- Ký tự đầu/cuối của word.
- Dấu âm, dấu chấm trong số và độ chính xác.
- Dấu bằng/dấu phẩy/dấu chấm phẩy hoặc ngoặc.
- Dấu nháy đơn và nháy kép; chuỗi chưa đóng; ký tự escape.
- Whitespace, CRLF và LF.
- Comment trong và ngoài quoted text.
- Ký tự Unicode ngoài ASCII.

Không thể chỉ gọi một phương thức rồi cho rằng tokenizer trở thành lexer của Java, CSV hay JSON đầy đủ. Đặc biệt, việc nhận diện dấu trong một định dạng chuẩn có thể cần xử lý escape và trạng thái mà cách cấu hình ký tự đơn giản không mô tả được.

## 6. Khi nào `StreamTokenizer` phù hợp?

Dùng `StreamTokenizer` khi:

1. Đầu vào là luồng ký tự có thể đọc dần và ngữ pháp lexical nhỏ, ví dụ các lệnh nội bộ dạng `name = value`, danh sách tên và số, tập câu lệnh học tập.
2. Muốn tùy chỉnh word/number/quote/comment/EOL ở mức ký tự mà không tự viết scanner từ đầu.
3. Cần token tuần tự và grammar phía sau rất đơn giản; có thể viết state machine nhỏ để kiểm tra thứ tự token.
4. Chấp nhận giới hạn của `double` cho số hoặc có chiến lược riêng để parse những số cần độ chính xác.
5. Không cần vị trí token chính xác theo cột, vị trí byte, cây cú pháp phức tạp hay parser lỗi chuyên sâu.

Ví dụ bài toán phù hợp: một mini language dùng để luyện phân biệt token `name`, `=`, `number` và `;`, với tập từ khóa và cú pháp được định nghĩa rõ. Điều đó khác với việc nhận toàn bộ file SQL, JSON hoặc mã nguồn Java rồi mong `StreamTokenizer` xử lý grammar hoàn chỉnh.

## 7. So sánh với các công cụ phân tích khác

### 7.1. `Scanner`: đọc dữ liệu theo delimiter và pattern

`java.util.Scanner` thường thuận tiện cho nhập liệu dạng token phân cách bởi whitespace, phân tích số theo locale và xử lý regex delimiter:

```java
// Minh họa: scanner chỉ xử lý chuỗi ví dụ, không phải parser CSV.
try (java.util.Scanner scanner =
        new java.util.Scanner("red blue 42")) {
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
```

Với ví dụ trên, stdout là ba dòng `red`, `blue` và `42`. `Scanner` có `hasNextInt()`, `nextInt()`, `useDelimiter(...)` và cơ chế locale; khi parse số, cần lưu ý định dạng và `InputMismatchException`. Khi đọc từ file, phải đóng scanner (vì nó quản lý nguồn được bọc).

**Ưu:** API dễ đọc cho input nhỏ hoặc dạng whitespace/regex delimiter. **Nhược:** regex/locale/khối lượng lời gọi có thể gây chi phí đáng kể so với xử lý đơn giản theo khối; `Scanner` cũng không tự trở thành parser CSV/JSON hay lexer của ngôn ngữ phức tạp.

Chọn `StreamTokenizer` nếu quy tắc phân loại ký tự và dấu quote/comment phù hợp thiết kế của nó; chọn `Scanner` nếu input chủ yếu là các trường theo delimiter/pattern và muốn API chuyển kiểu tiện lợi.

### 7.2. `BufferedReader` + `String` / `Pattern`: kiểm soát theo dòng

Với log chỉ có “một record mỗi dòng”, thường dễ đọc bằng `readLine()` rồi áp dụng `indexOf`, `split` hoặc `Pattern` theo grammar cụ thể:

```java
// Minh họa một dòng đơn giản, không phải parser CSV.
String record = "ERROR|42|disk full";
String[] fields = record.split("\\|", -1);
System.out.println(fields[0]); // ERROR
System.out.println(fields[1]); // 42
```

Lưu ý `String.split` nhận **regular expression**, nên ký tự `|` phải escape dưới dạng `"\\|"` trong Java. Tham số `-1` giữ các trường rỗng ở cuối; không có tham số đó, các trường rỗng cuối có thể bị bỏ.

**Ưu:** tiện khi đơn vị nghiệp vụ là một dòng và thông báo lỗi cần số dòng. **Nhược:** dễ sai với quote/escape, multiline record hoặc dòng dài bất thường; `readLine()` đọc cả một dòng thành `String` nên không tự giới hạn độ dài dòng. Với log từ nguồn không tin cậy, cần quota dòng và kiểm tra input.

### 7.3. `StringTokenizer`: lớp cũ để chia chuỗi đơn giản

`java.util.StringTokenizer` tách **một `String` đã có sẵn**, chủ yếu dựa trên delimiter. Nó không đọc trực tiếp từ `Reader` theo token và không hiểu trọn vẹn quoted fields hay định dạng cấu trúc. Với code mới, `String.split`/`Pattern` hoặc parser đúng định dạng thường dễ kiểm soát hơn; không nên dùng `StringTokenizer` như giải pháp parser tổng quát.

### 7.4. CSV, JSON và định dạng chuẩn: parser chuyên dụng

Ví dụ CSV:

```text
id,name,description
1,"Ada, A.","first, second"
```

Nếu chỉ tách theo dấu phẩy, dữ liệu `"Ada, A."` bị chia sai. CSV còn có dấu nháy kép escaped, dòng mới bên trong trường, header, encoding và các biến thể dialect. Dùng thư viện CSV có hỗ trợ chuẩn/dialect cần thiết (ví dụ Apache Commons CSV hoặc OpenCSV, tùy dependency dự án). Khi parse dữ liệu quan trọng, định nghĩa rõ dialect và cách báo lỗi.

Ví dụ JSON:

```json
{"user":{"name":"Ada","roles":["reader","writer"]},"active":true}
```

JSON cần parser hiểu object, array, escape, kiểu số, boolean, null và cấu trúc lồng nhau. `StreamTokenizer` không tự tạo cây JSON hay xác thực grammar JSON. Dùng thư viện parser JSON phù hợp như Jackson hoặc Gson nếu chúng có sẵn trong dự án; kiểm tra giới hạn kích thước và độ sâu nếu input không đáng tin cậy.

### 7.5. Lexer/parser chuyên dụng

Nếu viết biểu thức có toán tử, ưu tiên, ngoặc lồng nhau, biến, keyword, string literal phức tạp hoặc ngôn ngữ riêng nhiều quy tắc, cần phân biệt rõ:

- **Lexer:** biến ký tự thành token mang loại, text, vị trí.
- **Parser:** kiểm tra grammar và tạo cấu trúc cú pháp như AST.
- **Semantic validation:** kiểm tra kiểu, tên biến, phép toán, miền giá trị.

`StreamTokenizer` chỉ hỗ trợ một phần lexical. Với nhu cầu mạnh hơn, cân nhắc lexer riêng rõ ràng, `Pattern` có ràng buộc tốt hoặc generator như ANTLR, tùy quy mô grammar và yêu cầu bảo trì.

## 8. Bảng quyết định nhanh

| Đầu vào thực tế | Lựa chọn bắt đầu | Vì sao |
| --- | --- | --- |
| Danh sách từ/số đơn giản phân cách whitespace | `Scanner` | Dễ đọc, có `nextInt`/`nextDouble` |
| Mini language với word, number, punctuation, quote/comment cơ bản | `StreamTokenizer` | Có cấu hình loại ký tự, trả token lần lượt từ `Reader` |
| Log “một record một dòng”, delimiter rõ, ít trường | `BufferedReader` + code dòng/`Pattern` | Kiểm soát record và thông báo lỗi dễ |
| File CSV có quote, delimiter trong trường hoặc multiline | Parser CSV chuyên dụng | Đúng cấu trúc và escape của CSV |
| JSON lồng nhau | Parser JSON chuyên dụng | Xử lý grammar, escape và kiểu dữ liệu |
| Dữ liệu cố định theo byte, giao thức nhị phân | `InputStream`/`DataInputStream`/`ByteBuffer` | Dữ liệu không phải văn bản để tách token |
| Ngôn ngữ có expression grammar, source positions, lỗi phục hồi | Lexer/parser chuyên dụng | `StreamTokenizer` không đủ cho grammar |
| Dữ liệu quá lớn nhưng chỉ cần đếm/phân lọc token | Đọc streaming với giới hạn tài nguyên | Tránh giữ toàn bộ tài liệu; đặt quota cho token/dòng |

**Không có công cụ “tốt nhất” tách khỏi yêu cầu.** Chọn theo định dạng thực, mức đúng cần đạt, kích thước input, báo lỗi, hiệu năng, bảo trì và thư viện đã có.

## 9. Tổ chức parser nhỏ dựa trên token

Giả sử grammar của một lệnh là:

```text
assignment := identifier "=" value
identifier := một word hợp lệ
value      := quoted-string | number | word
```

Một parser đúng phải lần lượt:

1. Gọi `nextToken()` và đòi loại `TT_WORD` cho tên khóa; nếu không, báo lỗi cùng `lineno()`.
2. Gọi `nextToken()` và đòi dấu `'='`. Nếu thiếu, không âm thầm nhận token tiếp theo làm giá trị.
3. Gọi `nextToken()` và chỉ chấp nhận những loại token hợp lệ cho value.
4. Kiểm tra bản ghi đã kết thúc: EOL, dấu `;` hoặc EOF, theo đúng grammar đã chọn.
5. Validate tên khóa, giá trị, số lớn/độ chính xác và trường trùng; trả lỗi có ngữ cảnh.
6. Nếu muốn lookahead một token, `pushBack()` có thể đưa token vừa đọc trở lại cho lần đọc kế; đừng dựa vào nó như bộ đệm bất kỳ độ dài.

Nếu grammar đặt ý nghĩa lên ranh giới dòng, bật `eolIsSignificant(true)`, nhưng kiểm tra kỹ trường hợp kết thúc nguồn ngay sau token cuối mà không có newline. Nếu grammar yêu cầu dấu `;`, phải cấu hình và kiểm tra dấu đó tường minh.

### 9.1. Vì sao không chỉ ghép chuỗi token?

Với đầu vào `x == 4`, tokenizer có thể trả lần lượt `x`, `=`, `=`, `4`. Nếu ứng dụng chỉ lấy những word/number và bỏ qua dấu, nó có thể vô tình chấp nhận biểu thức sai thành “x = 4”. Parser có nhiệm vụ kiểm tra thứ tự và số lượng token một cách chính xác.

Với đầu vào `total = 99999999999999999999`, việc lấy `nval` thành `double` rồi ép về `long` có thể mất dữ liệu hoặc làm thay đổi giá trị. Tách lexing và parsing rõ ràng: số cần chính xác nên được phân tích theo chuỗi chữ số gốc bởi bộ parser số phù hợp.

## 10. Quản lý nguồn, Unicode, bảo mật và tài nguyên

### 10.1. Charset và nguồn tệp

Với file văn bản, nên mở bằng charset xác định:

```java
// Minh họa API: path là một Path có sẵn.
try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    java.io.StreamTokenizer tokenizer =
            new java.io.StreamTokenizer(reader);
    // Đọc và xử lý token theo grammar của ứng dụng.
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập vì `path` chưa được khai báo. `try-with-resources` đóng reader ngay cả khi `nextToken()` ném `IOException`.

`StreamTokenizer` làm việc ở tầng `char` của Java, không ở tầng byte. Nếu dữ liệu được giải mã sai charset, token có thể sai ngay từ đầu. Với Unicode, không tự giả định cấu hình dải ký tự tương ứng hoàn toàn với grammar nhận diện mọi identifier Unicode hợp lệ; nếu có yêu cầu cụ thể về Unicode code point/normalization, hãy xác định và kiểm thử grammar riêng.

### 10.2. Giới hạn dữ liệu đầu vào không đáng tin cậy

Đọc streaming không có nghĩa an toàn vô điều kiện. Một token quoted cực dài, một dòng vô hạn, nhiều token liên tục hoặc nguồn block có thể làm ứng dụng tiêu tốn bộ nhớ, CPU, thời gian hoặc kết nối.

Khi phân tích input từ mạng/người dùng, cần chính sách:

- Giới hạn **tổng số byte** đọc (ở tầng byte) và/hoặc số ký tự nếu nghiệp vụ yêu cầu.
- Giới hạn **số token, kích thước token, số dòng, độ sâu cấu trúc** nếu grammar có cấu trúc lồng nhau.
- Đặt **timeout/cancellation** ở tầng nguồn nếu là socket/pipe có thể block.
- Kiểm soát lỗi định dạng: dấu quote không đóng, trường thiếu, number ngoài miền hợp lệ, ký tự ngoài grammar.
- Không đánh giá lệnh sinh ra từ token như code hoặc query nếu chưa validate và escape/parameterize theo bối cảnh.
- Với chuẩn có parser chuyên dụng, ưu tiên các giới hạn tài nguyên mà thư viện hỗ trợ thay vì tự giả định tokenizer an toàn.

`StreamTokenizer` không cung cấp sẵn quota token hay quota ký tự cho mọi trường hợp. Khi cần giới hạn chặt, đặt wrapper đầu vào có đo/giới hạn hoặc dùng parser hỗ trợ giới hạn được kiểm chứng.

### 10.3. Ngoại lệ và xử lý lỗi

`nextToken()` có thể ném `IOException` khi reader gặp vấn đề I/O. Điều đó khác lỗi grammar: ví dụ token không đúng chỗ là lỗi **phân tích cú pháp** mà code ứng dụng cần tự báo. Nên phân biệt ba nhóm:

- **I/O:** không đọc được file, lỗi mạng, hết quyền truy cập.
- **Lexical/syntax:** ký tự không hợp lệ, quote/grammar sai, thiếu dấu.
- **Semantic:** khóa không được phép, giá trị vượt giới hạn, trường trùng.

Không bỏ qua token bất ngờ chỉ để “đọc tiếp được”; điều đó làm sai dữ liệu và che khuất lỗi đầu vào.

## 11. Sai lầm phổ biến

- Nhầm `StreamTokenizer` là parser JSON/CSV hoặc một parser ngôn ngữ lập trình hoàn chỉnh.
- Nhầm `StreamTokenizer.TT_EOF` và `TT_EOL`; quên bật EOL nếu ngữ pháp cần phân biệt các dòng.
- Đọc `sval` khi token không phải word/quoted hoặc đọc `nval` khi token không phải number.
- Tin `nval` là số nguyên hoặc số thập phân chính xác cho mọi giá trị.
- Không kiểm tra dấu `=`, dấu ngoặc hoặc thứ tự token; chỉ thu thập word/number rồi bỏ dấu.
- Quên quản lý vòng đời `Reader`; tokenizer không tự đóng nguồn.
- Gọi `resetSyntax()` rồi quên khai báo lại whitespace/quote/number.
- Bật cú pháp comment mà không xét chuỗi chứa ký tự giống comment.
- Dùng `String.split(",")` để xử lý CSV có quoted comma.
- Dùng regex đơn giản để parse JSON lồng nhau.
- Coi API streaming là an toàn cho input vô hạn: token lớn hoặc thời gian đọc dài vẫn cần giới hạn.
- Không chỉ định charset khi đọc file và không kiểm thử Unicode/CRLF/LF.

## 12. Bài tập và tiêu chí tự đánh giá

1. **Phân loại token:** dự đoán stdout của `StreamTokenizerDemo` nếu bỏ `eolIsSignificant(true)`. Token `EOF` có biến mất không? (Không.)
2. **Quy tắc dấu:** thêm dấu `;` vào input, sửa parser để chấp nhận chính xác một dấu `=` và tùy chọn kết thúc bằng `;`. Kiểm thử `x == 4` bị từ chối.
3. **Tùy chỉnh word:** thêm tên `first_name` vào `ConfiguredTokenizerDemo`. Giải thích vì sao cần `wordChars('_', '_')`.
4. **Số chính xác:** thử một mã định danh 20 chữ số. Vì sao không lưu nó bằng `nval` rồi ép sang `long`? Thiết kế hướng xử lý token nguyên gốc dạng chuỗi.
5. **So sánh công cụ:** với `a,b,"c,d"`, giải thích vì sao `split(",")` sai và chọn parser CSV.
6. **Dữ liệu nhiều dòng:** tạo input hai lệnh, dòng trống, dấu xuống dòng CRLF và EOF không có newline cuối. Xác định cách parser phát hiện kết thúc record.
7. **Lỗi nguồn:** mô phỏng `IOException` từ reader và phân biệt thông điệp lỗi I/O với lỗi “thiếu dấu =”.
8. **Unicode:** kiểm thử tên và giá trị có dấu tiếng Việt, emoji; xác định grammar identifier mong muốn và charset khi đọc file.
9. **Tài nguyên:** nêu nơi đóng `Reader`, nơi đặt quota/timeout và vì sao `StreamTokenizer` không tự làm việc này.

**Kiểm tra kết quả cuối cùng:** bạn cần phân biệt được **tokenization, parsing, validation**, viết được vòng lặp `nextToken()` dừng chính xác ở EOF, hiểu cách lấy `sval`/`nval` đúng loại token, và chọn parser chuyên dụng khi định dạng có quy tắc vượt quá khả năng lexer đơn giản.
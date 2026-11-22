# Tạo bảng tần suất từ và thống kê văn bản Unicode

## 1. Bài toán: đếm từ trong văn bản không chỉ là split theo dấu cách

Trong các ứng dụng tìm kiếm, phân tích phản hồi, xử lý nhật ký hoặc đánh giá tài liệu, ta thường cần biết **một từ xuất hiện bao nhiêu lần**, từ nào phổ biến nhất, có bao nhiêu từ khác nhau và độ dài văn bản ra sao. Với **Java Stream API**, pipeline có thể biểu diễn nhiệm vụ này theo chuỗi bước khai báo:

```text
Văn bản đầu vào
       |
       v
Chuẩn hóa Unicode + chữ hoa/chữ thường
       |
       v
Tách các token dạng từ
       |
       v
flatMap: nhiều dòng -> một luồng token
       |
       v
groupingBy(token, counting())
       |
       v
Map<String, Long> tần suất
       |
       v
Sắp theo tần suất giảm dần, token tăng dần
       |
       v
Bảng báo cáo ổn định
```

Giả sử hai đoạn văn nhìn giống nhau:

```text
Văn bản A: CÀ phê, cà PHÊ!
Văn bản B: café, café
```

Văn bản A khác nhau về chữ hoa/thường. Trong văn bản B, chữ `é` thứ hai có thể được biểu diễn bằng **hai Unicode code point**: chữ `e` và dấu sắc kết hợp `U+0301`. Nếu chỉ dùng `String.split(" ")` rồi so sánh chuỗi, chương trình có thể tính ra nhiều mục riêng dù người dùng thấy cùng một chữ.

Bài này thuộc chương **Mẫu xử lý dữ liệu thực tế** của module `JAVA_STREAM_API`. Ta sẽ sử dụng `map`, `flatMap`, `filter`, `collect`, `Collectors.groupingBy`, `Collectors.counting` và `sorted`, đồng thời nhận diện giới hạn của xử lý Unicode bằng API chuẩn.

**Sau bài học, bạn có thể:**

1. Phân biệt `char` UTF-16, Unicode code point và ký tự hiển thị (*grapheme cluster*).
2. Chuẩn hóa dạng Unicode bằng `Normalizer`, rồi xử lý chữ hoa/thường theo một chính sách rõ ràng.
3. Tách token có chữ và dấu kết hợp bằng biểu thức chính quy Unicode.
4. Tạo bảng tần suất từ, sắp kết quả có tie-break xác định và tính thống kê văn bản.
5. Đọc tập tin UTF-8 bằng `Files.lines` với `try-with-resources`.
6. Nhận diện trường hợp regex không đủ cho tiếng Việt đa âm tiết, văn bản đa ngôn ngữ, emoji, từ có số và dấu câu.

Các ví dụ độc lập dùng **Java 17+**. Phần lớn API như `Stream`, `Normalizer`, `Pattern` và `Collectors.groupingBy` đã có từ Java 8.

## 2. Định nghĩa "từ" trước khi viết chương trình

Để bài toán có thể kiểm thử được, ta cần nói rõ **token nào được đếm**. Một quy tắc thực hành ban đầu:

- Chỉ lấy chuỗi ký tự bắt đầu bằng **chữ Unicode** (nhóm `\p{L}`).
- Sau chữ đầu, chấp nhận thêm chữ hoặc **dấu kết hợp** (nhóm `\p{M}`).
- Dấu cách, dấu câu, chữ số và emoji được xem là dấu phân cách hoặc bị bỏ qua theo chính sách này.
- Chuyển chữ về chữ thường và chuẩn hóa **NFC** trước khi đếm.
- Đếm theo **token**: mỗi lần xuất hiện đóng góp một đơn vị, kể cả khi token lặp lại trong cùng dòng.

Ví dụ:

| Văn bản đầu vào | Token theo chính sách bài học | Lưu ý |
| --- | --- | --- |
| `"CÀ phê"` | `cà`, `phê` | Hai âm tiết là hai token; không tự hiểu cụm `cà phê` là một từ ghép. |
| `"café"` | `café` | Chữ có dấu được giữ. |
| `"cafe" + dấu sắc kết hợp` | `café` sau NFC | Hai cách mã hóa được đưa về cùng dạng chuẩn. |
| `"Java-Stream"` | `java`, `stream` | Dấu nối là dấu phân cách. |
| `"A12 B34"` | `a`, `b` | Chữ số không nằm trong token theo quy tắc đang chọn. |
| `"🙂 Java"` | `java` | Emoji không phải token dạng chữ. |

**Đây là một quy tắc token hóa có chủ đích, không phải định nghĩa ngôn ngữ học phổ quát về "từ".** Trong tiếng Việt, `"học sinh"` hoặc `"cà phê"` có thể là đơn vị từ vựng gồm nhiều âm tiết; regex dưới đây sẽ tách theo từng chuỗi chữ. Để đếm từ ghép đúng nghĩa, cần một bộ **word segmentation** phù hợp ngôn ngữ và mô hình dữ liệu.

## 3. Unicode: char, code point và ký tự hiển thị khác nhau

Java `String` được biểu diễn bằng các **đơn vị mã UTF-16**. Một `char` chứa một đơn vị mã 16 bit, nhưng không phải lúc nào cũng tương ứng với một ký tự Unicode hoàn chỉnh.

Ví dụ:

```java
String greeting = "A🙂";

System.out.println(greeting.length());        // 3 đơn vị UTF-16
System.out.println(greeting.codePointCount(
        0, greeting.length()));               // 2 code point
```

Chữ `A` sử dụng một đơn vị UTF-16; emoji `🙂` là code point ngoài Basic Multilingual Plane nên được mã hóa bằng **cặp surrogate**, chiếm hai đơn vị UTF-16.

Một chữ có dấu kết hợp cũng có thể làm số code point khác số ký tự người đọc thấy:

```java
String composed = "é";
String decomposed = "e" + "\u0301"; // e + COMBINING ACUTE ACCENT

System.out.println(composed.length());   // 1
System.out.println(decomposed.length()); // 2
System.out.println(composed.equals(decomposed)); // false trước chuẩn hóa
```

Ba khái niệm:

| Đơn vị | API Java thường dùng | Ý nghĩa |
| --- | --- | --- |
| UTF-16 code unit | `String.length()`, `charAt()` | Đơn vị lưu trữ của chuỗi Java. |
| Unicode code point | `codePoints()`, `codePointCount()` | Giá trị ký tự trừu tượng của Unicode, có thể chiếm 1 hoặc 2 `char`. |
| Grapheme cluster | Phân đoạn văn bản theo quy tắc hiển thị | Có thể gồm nhiều code point, ví dụ chữ với dấu kết hợp hoặc emoji ghép. |

Nếu báo cáo muốn đếm **code point**, sử dụng `codePointCount` hoặc `codePoints`. Nếu muốn đếm **số ký tự mà người dùng nhìn thấy**, không thể coi `String.length()` hay số code point luôn chính xác; cần thuật toán phân đoạn grapheme thích hợp với phiên bản Unicode và ngữ cảnh hiển thị.

### Duyệt code point bằng Stream nguyên thủy

```java
String sample = "A🙂é";

long codePoints = sample.codePoints().count();
long unicodeLetters = sample.codePoints()
        .filter(Character::isLetter)
        .count();

System.out.println(codePoints);     // 3
System.out.println(unicodeLetters); // 2
```

`String.codePoints()` trả `IntStream` gồm các code point. `Character.isLetter` xét từng code point; khác với việc xử lý từng `char` bằng một vòng lặp có nguy cơ tách cặp surrogate.

## 4. Chuẩn hóa Unicode bằng Normalizer và Locale

Unicode có thể biểu diễn một số chữ với dấu theo nhiều chuỗi code point tương đương **về mặt chuẩn tắc**. Dạng chuẩn `NFC` thực hiện phép phân rã và hợp thành chuẩn tắc, giúp nhiều cách biểu diễn trở về một dạng thống nhất.

```java
import java.text.Normalizer;

String composed = "café";
String decomposed = "cafe" + "\u0301";

System.out.println(composed.equals(decomposed)); // false

String a = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String b = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(a.equals(b)); // true
```

`Normalizer.Form.NFC` là lựa chọn thường phù hợp khi **muốn giữ nguyên sự khác biệt chữ có dấu và không dấu**, đồng thời làm đồng nhất biểu diễn tổ hợp dấu.

### Xử lý chữ hoa/thường

`String.toLowerCase()` không truyền locale sử dụng locale mặc định của môi trường, có thể làm kết quả khác nhau giữa các máy. Trong một hệ thống đếm token có quy ước ngôn ngữ trung lập, dùng `Locale.ROOT`:

```java
import java.util.Locale;

String lower = "CÀ PHÊ".toLowerCase(Locale.ROOT);
System.out.println(lower); // cà phê
```

Quy trình chuẩn hóa minh họa:

```java
static String normalizeForCounting(String input) {
    String nfc = Normalizer.normalize(
            input, Normalizer.Form.NFC);
    String lower = nfc.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
```

Lý do chuẩn hóa NFC **sau** bước chuyển chữ thường: một số phép chuyển hoa/thường có thể tạo hoặc giữ dấu kết hợp; chuẩn hóa lần cuối giúp khóa thống nhất.

**Giới hạn quan trọng:** chuyển chữ thường bằng `Locale.ROOT` không tương đương đầy đủ với **Unicode case folding** trong mọi ngôn ngữ. Nếu cần so khớp ngôn ngữ chuyên biệt (ví dụ quy tắc chữ `I` ở tiếng Thổ Nhĩ Kỳ) hoặc so khớp tìm kiếm quốc tế nghiêm ngặt, phải chọn locale và cơ chế so khớp theo sản phẩm. Đừng âm thầm dùng một quy tắc chung cho toàn bộ hệ thống.

### NFC khác NFKC như thế nào?

`NFKC` còn chuẩn hóa các ký tự **tương thích**, có thể gộp những hình thức viết mang ý nghĩa hiển thị khác nhau (ví dụ một số dạng ký tự toàn chiều rộng hoặc ký hiệu tương thích). Điều đó có ích cho một số hệ thống tìm kiếm nhưng cũng có thể làm mất phân biệt mà nghiệp vụ muốn giữ.

| Mục tiêu | Hướng lựa chọn |
| --- | --- |
| Gộp các cách mã hóa có dấu tương đương chuẩn tắc | Thường bắt đầu với `NFC`. |
| Gộp thêm dạng ký tự tương thích | Cân nhắc `NFKC` sau khi xác định hệ quả. |
| Bỏ dấu tiếng Việt để tìm kiếm không dấu | Là một chính sách riêng, **không phải tác dụng mặc định của NFC**. |
| Giữ phân biệt chữ `ma`, `má`, `mà` | Không xóa các dấu kết hợp khi chuẩn hóa. |

Đừng bỏ dấu chỉ vì muốn đếm tần suất: các từ tiếng Việt khác dấu có thể mang nghĩa khác nhau.

## 5. Token hóa bằng Pattern Unicode

Một biểu thức chính quy phù hợp với chính sách ở mục 2 là:

```regex
\p{L}[\p{L}\p{M}]*
```

Giải thích:

- `\p{L}`: một ký tự thuộc nhóm **Letter** của Unicode, dùng ở vị trí đầu token.
- `[\p{L}\p{M}]*`: tiếp theo là không hoặc nhiều **Letter**/**Mark**.
- Biểu thức không nhận chữ số, ký hiệu nối hoặc dấu câu làm một phần của token.
- Vì bắt đầu bằng `\p{L}`, một dấu kết hợp **đứng lẻ không có chữ trước nó** sẽ không tạo thành token.

Trong chuỗi Java, dấu gạch chéo ngược của regex phải được **escape thêm một lần**:

```java
import java.util.regex.Pattern;

Pattern WORD = Pattern.compile(
        "\\p{L}[\\p{L}\\p{M}]*"
);
```

`Pattern` có thể dùng lại giữa nhiều lần phân tích. Đối tượng `Pattern` là bất biến về cấu hình, có thể được chia sẻ; còn mỗi `Matcher` là đối tượng có trạng thái và **không được chia sẻ đồng thời giữa các thread**.

### Tạo danh sách token từ một chuỗi

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;

static List<String> tokenize(String input) {
    String normalized = normalizeForCounting(input);
    Matcher matcher = WORD.matcher(normalized);

    List<String> words = new ArrayList<>();
    while (matcher.find()) {
        words.add(matcher.group());
    }
    return words;
}
```

Khi đặt `WORD`, `normalizeForCounting` và `tokenize` trong cùng một class:

```java
System.out.println(tokenize("CÀ phê, cà PHÊ!"));
// [cà, phê, cà, phê]

System.out.println(tokenize("café cafe\u0301"));
// [café, café]

System.out.println(tokenize("Java-Stream 2026 🙂"));
// [java, stream]
```

**Lưu ý về tính lazy:** hàm `tokenize` minh họa ở đây sử dụng `Matcher.find()` để **tạo một List trung gian cho mỗi chuỗi** trước khi trả về. Đây là chủ ý đơn giản hóa bài học; nó không phải một tokenizer hoàn toàn lazy. Với văn bản cực lớn hoặc cần streaming từng token, có thể viết `Spliterator` cho `Matcher` hoặc dùng thư viện token hóa chuyên dụng, nhưng phải tuân thủ hợp đồng tài nguyên và trạng thái.

## 6. Vì sao split theo khoảng trắng chưa đủ?

Phương án thường thấy:

```java
String[] pieces = "CÀ phê, cà PHÊ!".split("\\s+");
```

Kết quả là các mảnh như `"phê,"` và `"PHÊ!"` vẫn mang dấu câu; nếu đem làm khóa Map trực tiếp, `"phê"` khác `"phê,"`. Chỉ dùng `split(" ")` còn bỏ sót tab hoặc dấu ngắt dòng.

Ngay cả `split("\\W+")` cũng cần thận trọng: ý nghĩa các lớp ký tự như `\w` và `\W` chịu ảnh hưởng bởi cờ và quy tắc của `Pattern`. Khi cần Unicode, việc viết rõ `\p{L}`/`\p{M}` diễn đạt tốt hơn **loại token mà bài toán muốn đếm**.

| Đầu vào | Hậu quả của cách tách sơ sài |
| --- | --- |
| `"phê, phê!"` | Dấu câu có thể trở thành một phần khóa. |
| `"café cafe" + dấu kết hợp` | Hai biểu diễn có thể không bằng nhau nếu thiếu NFC. |
| `"CÀ cà"` | Đếm thành hai mục nếu chưa chuyển chữ thường. |
| `"Java\\tStream"` | Split theo một dấu cách thường không xử lý tab. |
| `"🙂 code"` | Kiểu đếm theo `char` có thể tách surrogate của emoji. |

Không có một regex nào giải quyết toàn bộ phân đoạn văn bản của mọi ngôn ngữ. Hãy chọn một **hợp đồng token hóa cụ thể và có test**.

## 7. Xây bảng tần suất bằng flatMap, groupingBy và counting

Giả sử văn bản được lưu dưới dạng nhiều dòng:

```java
List<String> lines = List.of(
        "CÀ phê, cà PHÊ!",
        "Trà trà, café cafe\u0301.",
        "Java Stream — JAVA stream JAVA."
);
```

Ý nghĩa của `flatMap`: mỗi dòng được biến thành **nhiều token**, rồi nối các Stream token thành một Stream chung.

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Long> frequencies = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));
```

Đọc pipeline từ trái sang phải:

1. `lines.stream()` tạo `Stream<String>` gồm các dòng.
2. `flatMap(line -> tokenize(line).stream())` tạo Stream các token đã được chuẩn hóa, **giữ cả lần xuất hiện lặp**.
3. `Function.identity()` lấy chính token làm khóa nhóm.
4. `Collectors.counting()` đếm số lần token được đưa vào nhóm.
5. Kết quả là `Map<String, Long>`.

Kiểm tra bằng các giá trị cụ thể:

```java
System.out.println(frequencies.get("java"));   // 3
System.out.println(frequencies.get("cà"));     // 2
System.out.println(frequencies.get("phê"));    // 2
System.out.println(frequencies.get("trà"));    // 2
System.out.println(frequencies.get("café"));   // 2
System.out.println(frequencies.get("stream")); // 2
System.out.println(frequencies.size());        // 6 từ khác nhau
```

Tổng số token là **13**: `java` xuất hiện ba lần, năm token còn lại xuất hiện hai lần mỗi token. Đây là một ví dụ có cả dấu tiếng Việt, chuẩn hóa NFC và chữ hoa/thường.

### Có thể dùng toMap thay cho groupingBy không?

Có, nếu xác định merge function đúng:

```java
Map<String, Long> withMerge = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.toMap(
                Function.identity(),
                token -> 1L,
                Long::sum
        ));

System.out.println(withMerge.equals(frequencies)); // true
```

`Collectors.toMap` **hai đối số** sẽ ném `IllegalStateException` khi token trùng; overload ba đối số với `Long::sum` mới diễn đạt đúng phép đếm. Với bài toán tần suất, `groupingBy(identity, counting())` thường gần ngữ nghĩa thống kê hơn.

## 8. Xuất bảng tần suất theo thứ tự xác định

`Collectors.groupingBy` mặc định không cam kết thứ tự duyệt của Map kết quả. Với một bảng báo cáo, ta thường muốn:

1. Tần suất **giảm dần**.
2. Nếu bằng tần suất, token **tăng dần** để kết quả ổn định.

```java
record WordCount(String word, long count) {}

List<WordCount> ranking = frequencies.entrySet().stream()
        .sorted(
                Comparator.<Map.Entry<String, Long>>comparingLong(
                        entry -> entry.getValue()
                ).reversed().thenComparing(Map.Entry::getKey)
        )
        .map(entry -> new WordCount(
                entry.getKey(), entry.getValue()
        ))
        .toList();

ranking.forEach(System.out::println);
```

Kết quả của ví dụ ở mục 7:

```text
WordCount[word=java, count=3]
WordCount[word=café, count=2]
WordCount[word=cà, count=2]
WordCount[word=phê, count=2]
WordCount[word=stream, count=2]
WordCount[word=trà, count=2]
```

**Thứ tự ở đây xác định theo `String.compareTo`** (thứ tự từ vựng theo đơn vị UTF-16), **không phải thứ tự từ điển tiếng Việt**. Ví dụ, so sánh chữ có dấu theo cách người Việt mong đợi cần một `Collator` và chính sách locale thích hợp. Nếu kết quả phải hoàn toàn ổn định xuyên môi trường, cần thống nhất phiên bản/rules của collator hoặc dùng comparator đã xác định rõ trong ứng dụng.

### Chỉ lấy top N

```java
int topN = 3;

List<WordCount> top = ranking.stream()
        .limit(topN)
        .toList();

System.out.println(top.size()); // 3
```

`limit` lấy tiền tố của danh sách **đã được sắp**. Đừng dùng `frequencies.entrySet().stream().limit(3)` rồi kỳ vọng đó là ba từ nhiều nhất.

### Chỉ in từ có tần suất lớn hơn ngưỡng

```java
List<WordCount> frequent = ranking.stream()
        .filter(item -> item.count() >= 3)
        .toList();

System.out.println(frequent); // [WordCount[word=java, count=3]]
```

Nếu chỉ cần báo cáo chứ không cần Map giữ thứ tự, có thể giữ Map ban đầu rồi chỉ tạo `List<WordCount>` đã sắp khi xuất dữ liệu.

## 9. Thống kê văn bản: dòng, token, từ khác nhau, code point

Bảng tần suất còn có thể cung cấp các số liệu tổng quan:

| Đại lượng | Định nghĩa trong bài này | Cách tính |
| --- | --- | --- |
| **Số dòng đầu vào** | Số phần tử `String` trong danh sách dòng | `lines.size()` |
| **Tổng số token** | Mọi lần xuất hiện, kể cả lặp | Tổng các value của bảng tần suất |
| **Số token khác nhau** | Số khóa duy nhất sau chuẩn hóa | `frequencies.size()` |
| **Số code point** | Code point Unicode trong văn bản gốc | `String.codePoints().count()` |
| **Số code point dạng chữ** | Các code point thỏa `Character.isLetter` | `codePoints().filter(Character::isLetter).count()` |
| **Độ dài token trung bình** | Trung bình **số code point** trên token đã chuẩn hóa | `mapToInt(...).average()` |

Ví dụ:

```java
long lineCount = lines.size();
long tokenCount = frequencies.values().stream()
        .mapToLong(Long::longValue)
        .sum();
long uniqueCount = frequencies.size();

long sourceCodePoints = lines.stream()
        .mapToLong(line -> line.codePointCount(0, line.length()))
        .sum();

long sourceLetters = lines.stream()
        .mapToLong(line -> line.codePoints()
                .filter(Character::isLetter)
                .count())
        .sum();

double averageTokenCodePoints = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .mapToInt(word -> word.codePointCount(0, word.length()))
        .average()
        .orElse(0.0);

System.out.println(lineCount);               // 3
System.out.println(tokenCount);              // 13
System.out.println(uniqueCount);             // 6
System.out.println(averageTokenCodePoints); // khoảng 3.69
```

Trong ví dụ này, tổng độ dài các token sau NFC là **48 code point**, trên 13 token nên trung bình xấp xỉ **3,69**. `sourceCodePoints` và `sourceLetters` đo trên **dòng đầu vào gốc**, vì vậy có thể bao gồm dấu câu, chữ số và các code point khác theo từng định nghĩa.

`IntStream.average()` trả `OptionalDouble` vì Stream có thể rỗng. `orElse(0.0)` là **chính sách báo cáo** chứ không phải phép toán toán học: nếu không có token nào, giá trị trung bình thực sự **không xác định**; trong hệ thống cần phân biệt hai trạng thái, hãy giữ `OptionalDouble` hoặc dùng một trường nullable/flag theo thiết kế.

### Tổng tần suất không được lẫn với số khóa

`frequencies.size()` là **số từ khác nhau**, không phải tổng số lần xuất hiện. Đó là lỗi thường gặp khi chuyển từ `List<String>` sang `Map<String, Long>`. Để lấy tổng token mà không phải duyệt lại văn bản, cộng các value của Map.

## 10. Cắt bỏ stop words mà không làm sai bảng thống kê

*Stop words* là những token thường gặp có thể được loại theo mục đích phân tích, chẳng hạn một số từ chức năng trong ngôn ngữ. Danh sách này **phụ thuộc lĩnh vực**; đừng tự loại `"không"`, `"có"` hoặc các từ quan trọng đối với phân tích cảm xúc/chủ đề.

Trong ví dụ đơn giản, ta có một tập từ cần bỏ:

```java
Set<String> stopWords = Set.of("và", "là", "của");

Map<String, Long> withoutStopWords = lines.stream()
        .flatMap(line -> tokenize(line).stream())
        .filter(word -> !stopWords.contains(word))
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));
```

Nên chuẩn hóa stop words **bằng cùng chính sách** với token đầu vào. Nếu danh sách stop words đến từ file hoặc người dùng, hãy chạy `normalizeForCounting` (và quy tắc token hóa phù hợp) trên dữ liệu này, thay vì giả định chúng đã ở cùng dạng NFC/chữ thường.

**Cần xác định thứ tự xử lý:** nếu lọc stop words trước `groupingBy`, số token khác nhau và tổng token của báo cáo sẽ **thay đổi**. Muốn đồng thời báo cáo số token tổng và số token sau lọc, nên tính hai chỉ số riêng hoặc xây một phép tổng hợp được thiết kế cho cả hai.

## 11. Unicode thực tế: dấu câu, chữ số, emoji và từ ghép

Regex `\p{L}[\p{L}\p{M}]*` tạo một bộ tách token **có giới hạn rõ ràng**. Nó không giải quyết hoàn chỉnh mọi dạng văn bản:

### Từ có số, hashtag và địa chỉ email

```text
Đầu vào      Chính sách regex trong bài
Java17       -> java
#Java        -> java
user@mail.io -> user, mail, io
don't        -> don, t
AI-based     -> ai, based
```

Điều này không nhất thiết sai nếu chỉ đếm chuỗi chữ; nhưng nếu sản phẩm cần giữ mã `Java17`, hashtag `#Java` hoặc email thành một token, phải **đổi hợp đồng token hóa**, không chỉ bổ sung `filter` sau đó. Có thể sử dụng một `Pattern` riêng cho mã sản phẩm, hashtag hoặc email và kiểm thử từng trường hợp.

### Tiếng Việt và từ ghép nhiều âm tiết

Với `"học sinh"`, regex này tạo hai token `học` và `sinh`. Trong nhiều bài toán NLP tiếng Việt, cả cụm có thể là một đơn vị từ vựng. `Collectors.groupingBy` chỉ đếm những token được đưa vào, **không tự biết ranh giới từ theo ngôn ngữ**.

Nếu cần **tần suất từ tiếng Việt theo nghĩa từ vựng**, hãy dùng bộ tách từ chuyên dụng và đánh giá trên dữ liệu có nhãn. Pipeline Stream từ bước token hóa trở đi (lọc, nhóm, đếm, sắp) vẫn có thể tái sử dụng.

### Chữ viết không dùng dấu cách

Một số hệ chữ như Hán văn không chia từ bằng khoảng trắng theo cùng cách. Regex ở đây có thể gộp một dãy chữ dài thành một token. Java có `BreakIterator.getWordInstance(locale)` để phân đoạn theo quy tắc ngôn ngữ/locale, nhưng chất lượng tách từ và bộ quy tắc phụ thuộc implementation cùng phiên bản JDK; với yêu cầu NLP chuyên sâu, cần đánh giá thư viện hoặc mô hình phù hợp.

### Emoji và grapheme clusters

Emoji như `🙂` hoặc emoji ghép qua `U+200D` không nằm trong token `\p{L}`. Nếu yêu cầu đếm emoji hay "ký tự người nhìn thấy", đó là **một bài toán khác**, cần xử lý grapheme clusters hoặc emoji sequences; không thể lấy `String.length()` làm số emoji.

## 12. Đọc văn bản UTF-8 với Files.lines và đóng tài nguyên

Trong ứng dụng thực tế, dữ liệu thường đến từ một tệp. `Files.lines` tạo một `Stream<String>` các dòng, phù hợp với pipeline sau:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countWordsFromFile(Path path)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }
}
```

Những nguyên tắc quan trọng:

1. **Chỉ định UTF-8 rõ ràng**: không dựa vào charset mặc định của hệ điều hành.
2. **Dùng `try-with-resources`**: Stream từ `Files.lines` gắn với tài nguyên I/O và cần đóng khi dùng xong.
3. **Terminal operation nằm bên trong khối `try`**: nếu đóng Stream rồi mới gọi `collect`, nguồn đã hết vòng đời.
4. **Không tái sử dụng Stream đã tiêu thụ**: muốn chạy báo cáo khác trên cùng file, mở lại nguồn hoặc thiết kế bộ tổng hợp nhiều chỉ số trong một lần duyệt.
5. **Xử lý lỗi đúng ranh giới**: mở file có thể ném `IOException`; lỗi đọc trong khi duyệt lazy có thể xuất hiện dưới dạng `UncheckedIOException`. Đừng tự nuốt lỗi rồi báo một bảng tần suất thiếu dữ liệu là thành công.

Với file lớn, `Files.lines` giúp tránh phải đọc **toàn bộ file thành một String**. Tuy nhiên, implementation `tokenize` ở đây vẫn tạo List token **cho từng dòng**, và `groupingBy` giữ Map gồm mọi token khác nhau; bộ nhớ vẫn có thể tăng theo số lượng token duy nhất hoặc độ dài một dòng.

Không nên dùng `parallel()` trên nguồn file tùy tiện: hiệu quả còn phụ thuộc Spliterator, cách chia dữ liệu, chi phí regex, I/O và thứ tự. Luôn kiểm tra tính đúng đắn trước khi đo hiệu năng.

## 13. Thống kê theo dòng và theo toàn tài liệu

Tùy sản phẩm, **tần suất toàn văn** khác với **số dòng có chứa token**:

```text
Dòng 1: java java
Dòng 2: java stream

Tần suất token:
  java   = 3
  stream = 1

Số dòng chứa token:
  java   = 2
  stream = 1
```

Để đếm **số dòng chứa** một token, chỉ cần loại trùng **trong từng dòng**, không loại trùng cả văn bản:

```java
List<String> sampleLines = List.of(
        "java java",
        "java stream"
);

Map<String, Long> linePresence = sampleLines.stream()
        .flatMap(line -> tokenize(line).stream().distinct())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(linePresence.get("java"));   // 2
System.out.println(linePresence.get("stream")); // 1
```

`distinct()` nằm **bên trong Stream của mỗi dòng**, nên mỗi token đóng góp tối đa một lần cho một dòng. Nếu đặt `distinct()` sau `flatMap` của toàn văn, mọi token chỉ còn một lần xuất hiện và kết quả đếm dòng sẽ sai.

Một chỉ số khác là **tần suất tương đối**:

```java
long total = frequencies.values().stream()
        .mapToLong(Long::longValue)
        .sum();

double javaShare = total == 0
        ? 0.0
        : (double) frequencies.getOrDefault("java", 0L) / total;

System.out.println(javaShare); // khoảng 0.23077 = 3/13
```

Khi trình bày phần trăm, cần nêu rõ mẫu số là **toàn bộ token** hay **token sau stop-word filtering**. Với văn bản không có token, không nên âm thầm gọi `0%` nếu báo cáo đòi phân biệt "không có dữ liệu".

## 14. Pipeline song song: an toàn với trạng thái và thứ tự

Về nguyên tắc, `groupingBy`/`counting` có thể được dùng trên nguồn song song:

```java
Map<String, Long> parallelFrequencies = lines.parallelStream()
        .flatMap(line -> tokenize(line).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(parallelFrequencies.equals(frequencies)); // true
```

Ví dụ này có các tính chất thuận lợi:

- `lines` là List ổn định, không bị sửa trong khi xử lý.
- `normalizeForCounting` là phép biến đổi theo giá trị đầu vào, không sửa biến global.
- Mỗi lần `tokenize` tạo `Matcher` và danh sách token **riêng cho lời gọi đó**.
- `Pattern` được dùng chung an toàn vì pattern không mang trạng thái tìm kiếm của `Matcher`.
- `Collectors.groupingBy(..., counting())` quản lý các kết quả tích lũy và kết hợp.

**Không dùng** một `HashMap` dùng chung để tăng số đếm:

```java
Map<String, Long> shared = new HashMap<>();

// SAI: ghi vào HashMap chung từ các tác vụ song song.
lines.parallelStream()
        .flatMap(line -> tokenize(line).stream())
        .forEach(word -> shared.merge(word, 1L, Long::sum));
```

`HashMap.merge` không khiến Map trở nên thread-safe. Việc cập nhật này có thể làm mất dữ liệu hoặc gây lỗi. Dùng collector như trên là lựa chọn rõ ràng hơn.

Nếu không cần thứ tự và dữ liệu rất lớn, có thể **đo thử** `Collectors.groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentFrequencies =
        lines.parallelStream()
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(),
                        Collectors.counting()
                ));
```

`groupingByConcurrent` là collector concurrent, unordered; **không tự cam kết nhanh hơn**. Để có bảng kết quả theo thứ tự ổn định, hãy **sắp các entry sau khi đếm**, bất kể Map do collector nào tạo.

Đặc biệt, **không chia sẻ một `Matcher` cho nhiều thread**. `Matcher` có con trỏ và các nhóm bắt được thay đổi theo `find()`; sử dụng chung có thể làm hỏng cả token và tần suất.

## 15. Ví dụ Java 17+ hoàn chỉnh: phân tích Unicode và in bảng xếp hạng

Chương trình bên dưới chạy độc lập: chuẩn hóa NFC và chữ thường, tách token Unicode, tạo tần suất, sắp giảm dần theo số lần xuất hiện, tính thống kê và kiểm tra kết quả mong đợi.

```java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class UnicodeWordFrequencyDemo {
    private static final Pattern WORD =
            Pattern.compile("\\p{L}[\\p{L}\\p{M}]*");

    record WordCount(String word, long count) {}
    record Summary(
            long lines,
            long tokens,
            long distinctTokens,
            long sourceCodePoints,
            double avgTokenCodePoints
    ) {}

    static String normalize(String input) {
        String nfc = Normalizer.normalize(
                input, Normalizer.Form.NFC);
        String lower = nfc.toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lower, Normalizer.Form.NFC);
    }

    static List<String> tokenize(String text) {
        Matcher matcher = WORD.matcher(normalize(text));
        List<String> tokens = new ArrayList<>();
        while (matcher.find()) {
            tokens.add(matcher.group());
        }
        return tokens;
    }

    static Map<String, Long> frequencies(List<String> lines) {
        return lines.stream()
                .flatMap(line -> tokenize(line).stream())
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }

    static List<WordCount> rank(Map<String, Long> frequencies) {
        return frequencies.entrySet().stream()
                .sorted(
                        Comparator.<Map.Entry<String, Long>>comparingLong(
                                entry -> entry.getValue()
                        ).reversed().thenComparing(Map.Entry::getKey)
                )
                .map(entry -> new WordCount(
                        entry.getKey(), entry.getValue()
                ))
                .toList();
    }

    static Summary summarize(
            List<String> lines, Map<String, Long> frequencies) {
        long totalTokens = frequencies.values().stream()
                .mapToLong(Long::longValue)
                .sum();

        long sourceCodePoints = lines.stream()
                .mapToLong(line -> line.codePointCount(
                        0, line.length()
                ))
                .sum();

        double averageLength = lines.stream()
                .flatMap(line -> tokenize(line).stream())
                .mapToInt(token -> token.codePointCount(
                        0, token.length()
                ))
                .average()
                .orElse(0.0);

        return new Summary(
                lines.size(),
                totalTokens,
                frequencies.size(),
                sourceCodePoints,
                averageLength
        );
    }

    public static void main(String[] args) {
        List<String> text = List.of(
                "CÀ phê, cà PHÊ!",
                "Trà trà, café cafe\u0301.",
                "Java Stream — JAVA stream JAVA."
        );

        Map<String, Long> frequencies = frequencies(text);
        List<WordCount> ranking = rank(frequencies);
        Summary summary = summarize(text, frequencies);

        if (summary.tokens() != 13
                || summary.distinctTokens() != 6
                || frequencies.get("java") != 3L
                || frequencies.get("café") != 2L
                || frequencies.get("cà") != 2L) {
            throw new AssertionError("Kết quả đếm token sai");
        }

        List<WordCount> expected = List.of(
                new WordCount("java", 3),
                new WordCount("café", 2),
                new WordCount("cà", 2),
                new WordCount("phê", 2),
                new WordCount("stream", 2),
                new WordCount("trà", 2)
        );
        if (!ranking.equals(expected)) {
            throw new AssertionError("Sai thứ tự bảng tần suất");
        }

        System.out.println("Từ       | Số lần");
        System.out.println("---------+-------");
        ranking.forEach(item -> System.out.printf(
                "%-8s | %d%n", item.word(), item.count()
        ));
        System.out.printf(
                "Dòng=%d, token=%d, khác nhau=%d%n",
                summary.lines(), summary.tokens(),
                summary.distinctTokens()
        );
        System.out.printf(
                "Độ dài token trung bình (code point)=%.2f%n",
                summary.avgTokenCodePoints()
        );
        System.out.println("PASS");
    }
}
```

**Kết quả tần suất mong đợi:**

```text
java   -> 3
café   -> 2
cà     -> 2
phê    -> 2
stream -> 2
trà    -> 2
Tổng token: 13
Số token khác nhau: 6
Độ dài token trung bình: khoảng 3.69 code point
```

### Giải thích thiết kế

1. `WORD` là `Pattern` chia sẻ, còn mỗi lượt `tokenize` tạo `Matcher` riêng.
2. `Normalizer.Form.NFC` và `Locale.ROOT` làm rõ chính sách hợp nhất khóa khi đếm.
3. `flatMap` ghép token từ nhiều dòng thành một luồng dữ liệu.
4. `groupingBy(identity, counting())` tạo Map tần suất mà không cần tự cập nhật HashMap ngoài pipeline.
5. `rank` sắp theo **count giảm dần**, sau đó **token theo thứ tự `String.compareTo` tăng dần**, có tie-break cụ thể.
6. `summarize` giữ riêng tổng token, số từ khác nhau và số code point của nguồn. Các chỉ số không bị nhầm với nhau.
7. `assert` bằng điều kiện `if`/`throw` làm ví dụ thất bại nếu kết quả sai; không phụ thuộc vào việc JVM có bật `-ea`.

**Giới hạn của ví dụ:** đây là báo cáo **tần suất token dạng chữ**, chưa phải bộ tách từ tiếng Việt đa âm tiết hay hệ thống hỗ trợ mọi trường hợp Unicode. Với dữ liệu lớn, cách token hóa trả List sẽ tạo nhiều allocation; với quy tắc ngôn ngữ phức tạp, cần tokenizer chuyên dụng và bộ test phù hợp.

## 16. Bài tập thực hành

### Bài 1 — Chuẩn hóa và kiểm chứng NFC

Cho:

```java
List<String> data = List.of(
        "Café",
        "cafe" + "\u0301",
        "CAFÉ"
);
```

**Yêu cầu:** dùng chính sách NFC/chữ thường ở bài này để đếm ba lần xuất hiện thành một khóa. Giải thích vì sao không đủ nếu chỉ gọi `toLowerCase(Locale.ROOT)` mà bỏ `Normalizer`.

**Gợi ý lời giải:**

```java
Map<String, Long> counts = data.stream()
        .flatMap(item -> tokenize(item).stream())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("café")); // 3
System.out.println(counts.size());      // 1
```

### Bài 2 — Bảng top N có tie-break

Cho các dòng:

```java
List<String> logs = List.of(
        "Java Java Stream",
        "Stream API",
        "Java API"
);
```

**Yêu cầu:** tạo bảng tần suất, lấy hai token có số lần xuất hiện lớn nhất. Nếu bằng tần suất, sắp token tăng dần theo `String.compareTo`.

**Lời giải:**

```java
Map<String, Long> logCounts = frequencies(logs);

List<WordCount> topTwo = rank(logCounts).stream()
        .limit(2)
        .toList();

System.out.println(topTwo);
// [WordCount[word=java, count=3],
//  WordCount[word=api, count=2]]
```

`stream` cũng xuất hiện hai lần, nhưng `api` đứng trước `stream` ở bước tie-break.

### Bài 3 — Đếm số dòng chứa token

Cho:

```java
List<String> comments = List.of(
        "java java",
        "stream java",
        "stream stream"
);
```

**Yêu cầu:** tính cả tần suất token toàn văn và số dòng có chứa mỗi token. Phân biệt hai chỉ số.

**Lời giải:**

```java
Map<String, Long> occurrences = frequencies(comments);

Map<String, Long> documentFrequency = comments.stream()
        .flatMap(line -> tokenize(line).stream().distinct())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(occurrences.get("java"));       // 3
System.out.println(documentFrequency.get("java")); // 2
System.out.println(occurrences.get("stream"));      // 3
System.out.println(documentFrequency.get("stream")); // 2
```

### Bài 4 — Xử lý emoji và Unicode bổ sung

Cho:

```java
String sample = "A🙂é";
```

**Yêu cầu:** giải thích vì sao `sample.length() == 4` nhưng `sample.codePointCount(0, sample.length()) == 3`; phân biệt số code point, số token dạng chữ và số ký tự hiển thị.

**Đáp án:** `A` và `é` chiếm mỗi chữ một đơn vị UTF-16 trong dạng composed, emoji `🙂` chiếm hai đơn vị; tổng `length = 4`. Có ba Unicode code point. Với chính sách regex của bài, có hai token chữ là `a` và `é` sau chuẩn hóa; emoji không được tính thành token. Đếm grapheme cluster là một tiêu chí khác.

### Bài 5 — Đọc tệp thật và kiểm tra tài nguyên

**Yêu cầu:** viết phương thức nhận `Path`, đọc UTF-8, đếm token, đóng Stream kể cả khi phát sinh ngoại lệ. Giải thích vì sao không gọi `Files.lines` rồi bỏ mặc Stream không đóng.

**Lời giải:** tham khảo `countWordsFromFile` ở mục 12. Đặt toàn bộ terminal operation trong khối `try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8))`. Không làm mất thông tin về `IOException` hoặc `UncheckedIOException`.

### Bài 6 — Điều chỉnh chính sách token hóa

**Yêu cầu mở rộng:** sản phẩm muốn giữ `"Java17"` làm một token và xem dấu `#` trong hashtag là thành phần riêng của một loại token. Hãy định nghĩa lại quy tắc, ví dụ biểu thức có chữ số ở sau chữ đầu, rồi kiểm thử `Java17`, `Java-17`, `#Java`, email và dữ liệu có dấu Unicode.

**Gợi ý:** có thể bắt đầu từ `\p{L}[\p{L}\p{M}\p{N}]*` nếu muốn cho phép chữ số Unicode sau chữ đầu; hashtag cần quy tắc khác. Mọi thay đổi định nghĩa token sẽ **thay đổi kết quả thống kê**, vì vậy cần cập nhật bộ test và tài liệu giải thích.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `"CÀ"` và `"cà"` thành hai khóa | Không chuẩn hóa chữ hoa/thường | Dùng quy tắc locale rõ ràng, ví dụ `toLowerCase(Locale.ROOT)`. |
| `"café"` và `"cafe" + dấu kết hợp` thành hai khóa | Khác biểu diễn Unicode | Chuẩn hóa `Normalizer.Form.NFC` trước khi nhóm. |
| `"phê,"` và `"phê"` bị đếm khác nhau | Dấu câu bị giữ trong token | Token hóa theo chính sách Unicode đã định nghĩa. |
| Kết quả sai với emoji hoặc ký tự ngoài BMP | Duyệt từng `char` như ký tự hoàn chỉnh | Dùng `codePoints()` hoặc cơ chế grapheme phù hợp. |
| Số từ bằng `frequencies.size()` nhưng thấp bất ngờ | Nhầm số token khác nhau với tổng lần xuất hiện | Cộng các value bằng `mapToLong(...).sum()`. |
| Bảng tần suất in thứ tự khác nhau | `groupingBy` không cam kết thứ tự Map | Sắp entry theo count và token có tie-break. |
| Dùng `toMap(key, value)` thì ném lỗi | Token trùng khóa | Dùng `groupingBy(..., counting())` hoặc `toMap(..., Long::sum)`. |
| Một matcher cho nhiều thread làm mất token | `Matcher` mutable, không thread-safe | Tạo `Matcher` riêng cho mỗi lời gọi tokenizer. |
| Bộ lọc stop words bỏ mất dữ liệu quan trọng | Danh sách và thứ tự lọc thiếu chính sách | Định nghĩa mục đích thống kê, giữ số liệu trước/sau lọc. |
| `Files.lines` bị bỏ quên không đóng | Stream gắn với tài nguyên tệp | Dùng `try-with-resources` và terminal operation trong khối `try`. |
| Unicode tiếng Việt bị tách sai từ ghép | Regex chỉ lấy token dạng chữ, không phải phân đoạn từ vựng | Dùng tokenizer có nhận biết ngôn ngữ nếu cần. |
| File rất lớn làm hết bộ nhớ | Quá nhiều từ duy nhất, List token trung gian | Tính toán giới hạn, streaming tokenizer, chia lô hoặc thiết kế lưu trữ ngoài bộ nhớ. |
| `parallelStream()` không nhanh hơn | Chi phí chia tác vụ, tạo Matcher/List và gộp Map | Đo thực tế; giữ biến đổi không có trạng thái dùng chung. |

## 18. Checklist bàn giao pipeline phân tích văn bản

1. **Định nghĩa token:** có chữ số, hashtag, dấu nối, dấu nháy, emoji hoặc từ ghép nhiều âm tiết hay không?
2. **Unicode:** chính sách NFC/NFKC, chữ thường và locale có được ghi rõ không?
3. **Độ dài:** thống kê theo UTF-16 code unit, code point hay grapheme cluster?
4. **Tách token:** `Pattern` có chấp nhận `\p{M}` và xử lý dấu kết hợp như mong muốn không?
5. **Null:** dòng đầu vào có thể null không? Nếu có, lọc hoặc báo lỗi trước khi gọi `Normalizer`.
6. **Stop words:** danh sách đã được chuẩn hóa theo cùng quy tắc với token chưa?
7. **Đếm:** tổng số token và số token duy nhất có được tách thành hai chỉ số khác nhau không?
8. **Bảng xếp hạng:** có thứ tự chính theo tần suất và tie-break xác định không?
9. **Văn bản rỗng:** có xử lý Map rỗng và `OptionalDouble.empty()` đúng chính sách không?
10. **Tệp:** có chỉ định UTF-8, đóng `Files.lines` và không nuốt lỗi đọc giữa pipeline không?
11. **Song song:** matcher riêng cho mỗi tác vụ, không chia sẻ Map mutable và đã kiểm tra nội dung tuần tự/song song chưa?
12. **Giới hạn ngôn ngữ:** với tiếng Việt, có phân biệt đếm âm tiết và đếm từ ghép không?
13. **Hiệu năng:** đã đo số token, số token khác nhau, kích thước dòng cực đại và bộ nhớ chưa?
14. **Kiểm thử:** có dữ liệu tiếng Việt NFC/NFD, tiếng Anh, emoji, chữ số, dấu câu, văn bản rỗng và stop words không?

## Ghi nhớ

Tạo **bảng tần suất từ** là một mẫu xử lý dữ liệu hữu ích để kết hợp nhiều kỹ thuật của **Java Stream API**: chuẩn hóa đầu vào, `flatMap` để làm phẳng token từ nhiều dòng, `groupingBy(Function.identity(), counting())` để đếm, rồi `sorted` để tạo bảng xếp hạng ổn định.

Với văn bản Unicode, **định nghĩa token và chính sách chuẩn hóa quyết định kết quả**. `String.length()` đếm đơn vị UTF-16 chứ không phải luôn là số ký tự hiển thị; `Normalizer.Form.NFC` giúp thống nhất các biểu diễn dấu tương đương; `\p{L}` và `\p{M}` giúp biểu thức chính quy xử lý chữ và dấu kết hợp. Regex minh họa vẫn chỉ tách **token dạng chữ**, không tự hiểu từ ghép tiếng Việt hay mọi ngôn ngữ.

Hãy phân biệt tổng token với số token khác nhau, sắp bảng tần suất có tie-break, đóng nguồn I/O bằng `try-with-resources` và tránh cập nhật một Map/Matcher dùng chung trong pipeline song song. Sau khi chứng minh tính đúng đắn trên dữ liệu Unicode có chủ đích, mới đo và tối ưu hiệu năng.

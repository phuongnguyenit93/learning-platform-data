# Pattern.splitAsStream, BitSet.stream và JarFile.stream — ba nguồn Stream chuyên biệt trong Java

## 1. Mục tiêu bài học

Trong Java, `Stream` không chỉ được tạo bằng `Collection.stream()` hoặc `Stream.of(...)`. Nhiều API thuộc các lĩnh vực khác nhau có thể tạo một stream trực tiếp từ **dữ liệu có cấu trúc chuyên biệt**. Ba ví dụ quan trọng là:

- **`Pattern.splitAsStream(CharSequence)`** tạo `Stream<String>` từ việc tách văn bản theo **biểu thức chính quy**.
- **`BitSet.stream()`** tạo `IntStream` chứa **chỉ số những bit đang bật** trong một `BitSet`.
- **`JarFile.stream()`** tạo `Stream<JarEntry>` để duyệt **các entry của tệp JAR**.

Ba API đều có từ **Java 8** và vẫn được hỗ trợ trong Java hiện đại. Chúng minh họa một ý tưởng chung: nguồn Stream không nhất thiết là danh sách có sẵn; nguồn có thể là thao tác tách chuỗi, cấu trúc bit nén hay mục lục của một archive.

Sau bài này, bạn sẽ:

1. Chọn đúng API cho dữ liệu đầu vào thay vì chuyển toàn bộ dữ liệu sang collection trung gian một cách không cần thiết.
2. Đọc đúng **kiểu phần tử**, **thứ tự**, **điều kiện dừng**, **đặc tính lazy** và **hợp đồng sử dụng** của từng nguồn.
3. Nắm rõ `Pattern.splitAsStream` loại bỏ các phần tử rỗng **ở cuối**, xử lý khác nhau giữa dấu phân cách có độ rộng dương và zero-width.
4. Hiểu `BitSet.stream()` trả về **index** chứ không phải một luồng giá trị boolean, đồng thời biết rủi ro sửa `BitSet` khi stream đang chạy.
5. Duyệt `JarFile` an toàn với `try-with-resources`, phân biệt **metadata entry** và **nội dung entry**, biết khi nào nên dùng `versionedStream()`.
6. Viết chương trình Java 17+ độc lập, tạo JAR thử nghiệm, chạy và kiểm tra kết quả đầu ra chính xác.
7. Tránh các lỗi regex, thay đổi nguồn đang được traverse, resource leak và dùng side effects bên trong intermediate operations.

## 2. Bức tranh tổng quan: giống ở pipeline, khác ở nguồn

| Phương thức | Thuộc class | Kết quả | Mỗi phần tử đại diện cho gì? |
| --- | --- | --- | --- |
| `splitAsStream(input)` | `java.util.regex.Pattern` | `Stream<String>` | Một đoạn văn bản giữa các lần khớp regex |
| `stream()` | `java.util.BitSet` | `IntStream` | Chỉ số của bit đang có giá trị `true` |
| `stream()` | `java.util.jar.JarFile` | `Stream<JarEntry>` | Một entry trong central directory của JAR |

Ví dụ ngắn:

~~~java
Pattern comma = Pattern.compile(",");
Stream<String> tokens = comma.splitAsStream("red,green,blue");

BitSet flags = new BitSet();
flags.set(2);
flags.set(5);
IntStream selectedPositions = flags.stream();

try (JarFile jar = new JarFile("application.jar")) {
    Stream<JarEntry> entries = jar.stream();
    // Dùng một terminal operation khi JarFile còn mở.
}
~~~

Đây là **ba đoạn minh họa**, không phải một chương trình độc lập: cần import các kiểu tương ứng, có file `application.jar` thật, và caller xử lý `IOException`. Chương trình hoàn chỉnh được trình bày ở phần sau.

Cả ba nguồn đều có thể nối với các intermediate/terminal operations quen thuộc như `filter`, `map`, `mapToInt`, `sorted`, `count`, `toList` và `forEach`. Tuy nhiên, **không được suy rằng chúng có cùng chính sách về resource hoặc thay đổi nguồn**. Cụ thể:

- Nguồn `String` thường là dữ liệu bất biến; nhưng `splitAsStream` cũng nhận `CharSequence` mutable, và tài liệu đặt ràng buộc tính ổn định của đầu vào.
- Nguồn `BitSet` mutable và stream có đặc tính **late-binding**; sửa BitSet trong lúc terminal operation chạy làm kết quả không được xác định.
- `JarFile` nắm tài nguyên file/archive; cần đóng `JarFile` và xử lý stream trước khi chủ sở hữu tài nguyên bị đóng.

**Mục tiêu là dùng chung mô hình Stream nhưng vẫn tôn trọng hợp đồng của từng loại nguồn.**

## 3. Pattern.splitAsStream: tách chuỗi bằng regex thành Stream

### 3.1 Chữ ký và chức năng

~~~java
public Stream<String> splitAsStream(CharSequence input)
~~~

`Pattern` là **regex đã biên dịch**. `splitAsStream` trả về một stream các chuỗi con của `input`, được phân cách bởi các đoạn khớp với regex. Các chuỗi con xuất hiện theo **thứ tự trong văn bản gốc**.

Ví dụ:

~~~java
Pattern comma = Pattern.compile(",");

List<String> names = comma
        .splitAsStream("Lan,Mai,Hoa")
        .toList();

// [Lan, Mai, Hoa]
~~~

Ở đây `,` là delimiter được diễn giải như regex. Dữ liệu nguồn không phải một `List<String>`; các tokens được tạo ra khi Stream được tiêu thụ.

Điểm cần nhớ: **`splitAsStream` tách quanh những chỗ regex khớp**, không trả các đoạn khớp regex đó. Nếu muốn lấy **các match** chứ không phải các vùng giữa match, cân nhắc `Matcher.results()` (Java 9+) hoặc các API `Matcher` tương ứng.

### 3.2 Regex không phải delimiter literal mặc định

`Pattern.compile(regex)` nhận một **regular expression**, không phải chuỗi ký tự delimiter nguyên văn trong mọi trường hợp.

~~~java
Pattern dotRegex = Pattern.compile(".");
Pattern literalDot = Pattern.compile(Pattern.quote("."));
~~~

- Regex `"."` khớp gần như mọi ký tự, **không chỉ dấu chấm**.
- `Pattern.quote(".")` tạo regex khớp đúng **dấu chấm literal**.
- `Pattern.compile("\\.")` cũng có thể dùng để khớp dấu chấm nếu bạn hiểu cách escape trong cả Java string literal và regex.

Ví dụ:

~~~java
List<String> segments = Pattern.compile(Pattern.quote("."))
        .splitAsStream("user.profile.name")
        .toList();

// [user, profile, name]
~~~

Khi delimiter đến từ cấu hình/người dùng và phải được xem là **chuỗi literal**, `Pattern.quote(delimiter)` thường rõ ràng hơn tự nối regex.

### 3.3 Regex tiền xử lý khoảng trắng

Muốn tách CSV rất đơn giản có các dấu phẩy và khoảng trắng xung quanh:

~~~java
Pattern delimiter = Pattern.compile("\\s*,\\s*");

List<String> colors = delimiter
        .splitAsStream("red, green,blue, ")
        .map(String::trim)
        .toList();

// [red, green, blue]
~~~

`\\s*` là zero-or-more whitespace trong **regex**, còn Java source phải viết `"\\s*,\\s*"` để đưa hai dấu backslash thực vào regex engine.

**Giới hạn:** Đây chỉ là ví dụ **chuỗi phân cách bằng dấu phẩy đơn giản**, không phải parser CSV đầy đủ. CSV có quy tắc về quoted fields, dấu phẩy bên trong dấu ngoặc kép, xuống dòng trong field, escape và chuẩn encoding. Nếu nghiệp vụ dùng CSV thật, cần parser hiểu định dạng, không dùng regex đơn giản rồi cho rằng đã xử lý mọi trường hợp.

## 4. Trailing empty strings: chuỗi rỗng ở cuối sẽ bị bỏ

Đây là quy tắc dễ sai nhất khi dùng `Pattern.splitAsStream`:

**Các chuỗi rỗng ở cuối kết quả được loại bỏ.** Các chuỗi rỗng **ở giữa** vẫn có thể xuất hiện.

~~~java
List<String> pieces = Pattern.compile(",")
        .splitAsStream("a,,b,")
        .map(s -> "[" + s + "]")
        .toList();

System.out.println(pieces);
~~~

Kết quả:

~~~text
[[a], [], [b]]
~~~

Giải thích:

- `a` là token đầu tiên.
- Hai dấu phẩy liền nhau tạo **một token rỗng ở giữa**.
- `b` là token tiếp theo.
- Dấu phẩy cuối dẫn đến token rỗng cuối nhưng token này **bị bỏ**.

Dùng cặp dấu ngoặc `[...]` trong ví dụ giúp phân biệt chuỗi rỗng với khoảng trắng khi in.

### Khi nghiệp vụ cần giữ cả phần tử rỗng ở cuối

`splitAsStream` không nhận tham số `limit` như `Pattern.split(input, limit)`. Nếu định dạng dữ liệu cần phân biệt `"a,b,"` với `"a,b"` theo **số lượng cột**, một cách tương thích là:

~~~java
Pattern comma = Pattern.compile(",");

String[] fields = comma.split("a,b,", -1);
System.out.println(Arrays.toString(fields));

// [a, b, ]
~~~

Ở đây `limit = -1` trong `Pattern.split` giữ các trailing empty strings. Đó là một API khác với `splitAsStream`.

**Không thay thế bằng `splitAsStream(...).limit(n)` rồi coi hai tham số `limit` cùng nghĩa.** `Stream.limit(n)` cắt Stream sau nhiều nhất `n` phần tử được tạo, còn `Pattern.split(input, limit)` kiểm soát số lần regex được áp dụng và cách xử lý phần cuối chuỗi. Hai cơ chế không tương đương.

Nếu format yêu cầu lưu mọi trường rỗng (ví dụ CSV có số cột cố định), hãy chọn parser/cơ chế split phù hợp; không mặc định `splitAsStream` đáp ứng nhu cầu này.

## 5. Leading empty: delimiter ở đầu có thể tạo chuỗi rỗng

Java `Pattern.splitAsStream` phân biệt một match **có độ rộng dương** và một match **zero-width** ở đầu input.

- Nếu regex có **positive-width match tại đầu**, một token rỗng ở đầu **được đưa vào** kết quả.
- Nếu regex có **zero-width match tại đầu**, nó **không** tạo token rỗng đầu tiên.

Ví dụ positive-width:

~~~java
List<String> tokens = Pattern.compile(",")
        .splitAsStream(",alpha,beta")
        .map(s -> "[" + s + "]")
        .toList();

// [[], [alpha], [beta]]
~~~

Dấu phẩy khớp một ký tự tại vị trí đầu. Vì có text rỗng trước dấu phẩy, kết quả có token rỗng đầu.

Ví dụ regex zero-width:

~~~java
Pattern lookAhead = Pattern.compile("(?=a)");

List<String> tokens = lookAhead
        .splitAsStream("abc")
        .toList();

// [abc]
~~~

`(?=a)` là một **lookahead** có match độ rộng 0 tại đầu chuỗi `abc`. Không có token rỗng đầu được sinh ra chỉ vì zero-width match này.

### Vì sao regex zero-width cần thận trọng?

Các regex như lookahead/lookbehind, ranh giới từ hoặc pattern có thể khớp chuỗi rỗng có semantics khác delimiter thông thường. Nếu bạn cần phân tích field boundaries chính xác, hãy kiểm thử:

- Delimiter ở đầu.
- Delimiter ở cuối.
- Hai delimiter liên tiếp.
- Input rỗng.
- Delimiter không xuất hiện.
- Match zero-width ở đầu hoặc nhiều vị trí khác.

**Không tự suy từ ví dụ dấu phẩy** rằng mọi regex đều chia chuỗi theo cùng số lượng token.

## 6. Không có match và trường hợp chuỗi rỗng

Nếu regex **không khớp bất cứ đoạn nào** trong input, stream chứa một phần tử là **toàn bộ input** dưới dạng String.

~~~java
List<String> tokens = Pattern.compile(",")
        .splitAsStream("single")
        .toList();

// [single]
~~~

Điều này khác với logic `filter`: Pattern không tìm thấy delimiter không có nghĩa stream rỗng. Nó có nghĩa **không cần tách**.

Nếu muốn loại bỏ tokens trống hoặc chỉ gồm whitespace do nghiệp vụ quy định, hãy đặt filter rõ:

~~~java
List<String> nonBlank = Pattern.compile(",")
        .splitAsStream("A, ,B")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();

// [A, B]
~~~

Nhưng việc loại bỏ tokens rỗng là một **quy tắc nghiệp vụ riêng**. Với dữ liệu bảng, token rỗng ở giữa có thể biểu diễn một cột rỗng quan trọng; lọc bỏ nó có thể làm thay đổi vị trí các cột.

## 7. Input CharSequence mutable: phải giữ ổn định trong terminal operation

Chữ ký nhận `CharSequence`, không chỉ `String`. Các đối tượng như `StringBuilder` có thể bị sửa.

~~~java
StringBuilder text = new StringBuilder("A,B,C");

Stream<String> tokens = Pattern.compile(",")
        .splitAsStream(text);
~~~

**Theo tài liệu Pattern:** nếu đầu vào có thể thay đổi, nó **phải không bị sửa trong quá trình terminal stream operation thực thi**; nếu không, kết quả terminal operation là **không xác định**.

Không nên làm:

~~~java
StringBuilder text = new StringBuilder("A,B,C");

Pattern.compile(",")
        .splitAsStream(text)
        .peek(x -> text.append(",D"))
        .forEach(System.out::println);
~~~

Đây là **mã minh họa một cách dùng sai**. Nó thay đổi chính input trong lúc tách, làm semantics không được bảo đảm. Không dựa vào số lần `peek` chạy, việc code có ném exception hay không, hoặc output trông có vẻ hợp lệ để kết luận thiết kế đúng.

Nếu cần snapshot ổn định:

~~~java
String snapshot = text.toString();

List<String> tokens = Pattern.compile(",")
        .splitAsStream(snapshot)
        .toList();
~~~

`String` là bất biến nên không có rủi ro nội dung đầu vào bị sửa từ chính chuỗi này trong khi tách.

### Thực hành tốt

- Dùng `Pattern` được biên dịch trước nếu regex được tái sử dụng nhiều lần.
- Tránh regex không rõ semantics với input lớn/không đáng tin cậy; cân nhắc rủi ro hiệu năng của backtracking.
- Nếu chỉ cần một delimiter literal đơn giản và quy tắc định dạng khác, cân nhắc API split thích hợp.
- Đừng giả định `Pattern.splitAsStream` tự diễn giải CSV, TSV có quoting, JSON hay một grammar bất kỳ.

## 8. BitSet.stream(): Stream của vị trí bit TRUE

### 8.1 BitSet là gì?

`java.util.BitSet` là cấu trúc lưu các bit được đánh chỉ số từ **0 trở lên**. Có thể dùng nó để biểu diễn:

- Các ID dạng số không âm đã được đánh dấu (trong phạm vi index hợp lý).
- Những feature flags đang bật tại các vị trí bit.
- Vị trí đã được chọn trong một tập dữ liệu lớn.
- Tập chỉ số thỏa điều kiện nào đó với mật độ phù hợp.

Đặt bit:

~~~java
BitSet selected = new BitSet();

selected.set(1);
selected.set(4);
selected.set(9);
~~~

Các bit có chỉ số `1`, `4`, `9` đang có giá trị true. Những chỉ số không được set mặc định là false.

### 8.2 Chữ ký

~~~java
public IntStream stream()
~~~

**Mỗi phần tử của stream là chỉ số của bit đang set**, không phải giá trị `true/false` tại mọi vị trí.

~~~java
int[] indexes = selected.stream().toArray();

System.out.println(Arrays.toString(indexes));
~~~

Kết quả:

~~~text
[1, 4, 9]
~~~

Java không tạo stream `[false, true, false, false, true, ...]`. `BitSet.stream()` chỉ liệt kê những vị trí có bit true.

### 8.3 Thứ tự kết quả

Javadoc xác định các chỉ số được trả **từ thấp đến cao**.

~~~java
BitSet bits = new BitSet();

bits.set(9);
bits.set(1);
bits.set(4);

System.out.println(Arrays.toString(bits.stream().toArray()));
~~~

Kết quả vẫn là:

~~~text
[1, 4, 9]
~~~

**Thứ tự gọi `set` không phải thứ tự stream.** Dù bạn set chỉ số 9 trước, kết quả vẫn được duyệt theo index tăng dần.

### 8.4 cardinality(), length() và size() khác nhau

Với các bit `1`, `4`, `9`:

- `cardinality()` trả `3`: số bit true.
- `length()` trả `10`: vị trí cao nhất đang set cộng một.
- `size()` nói về **số bit theo dung lượng lưu trữ hiện tại** của cấu trúc, không phải số bit true. Nó thường liên quan số word lưu trữ và không nên dùng như cardinality.

Đặc biệt:

~~~java
long count = bits.stream().count();
int setCount = bits.cardinality();
~~~

Với `BitSet` không bị thay đổi trong lúc terminal operation, số phần tử của `bits.stream()` bằng `bits.cardinality()` theo Javadoc.

**Không so sánh `stream().count()` với `bits.length()` để đo “số bit true”**: hai giá trị mô tả hai đại lượng khác nhau.

## 9. IntStream thay vì Stream<Integer>

`BitSet.stream()` trả **`IntStream` nguyên thủy**, không phải `Stream<Integer>`.

Điều này đem lại các terminal operations xử lý số nguyên trực tiếp:

~~~java
int[] indexes = bits.stream().toArray();

long selectedCount = bits.stream().count();

int sumOfIndexes = bits.stream().sum();

OptionalInt maxIndex = bits.stream().max();
~~~

Mỗi lời gọi `bits.stream()` ở trên tạo **một stream mới** từ BitSet hiện có. Không dùng lại cùng một `IntStream` đã bị terminal operation tiêu thụ.

### Chuyển sang boxed stream khi cần List<Integer>

~~~java
List<Integer> indexes = bits.stream()
        .boxed()
        .toList();
~~~

`boxed()` chuyển `IntStream` thành `Stream<Integer>`. Đây là bước boxing có thể tạo chi phí bộ nhớ/đối tượng. Nếu chỉ cần tính `sum`, `count`, `max`, dùng primitive stream thường hợp lý hơn.

### Lọc hoặc ánh xạ chỉ số

~~~java
int[] oddIndexes = bits.stream()
        .filter(index -> index % 2 != 0)
        .toArray();

// Với bit 1, 4, 9: [1, 9]
~~~

Bạn cũng có thể dùng index để truy cập dữ liệu có cùng hệ tọa độ:

~~~java
List<String> names = List.of("zero", "one", "two", "three", "four");

BitSet chosen = new BitSet();
chosen.set(1);
chosen.set(4);

List<String> result = chosen.stream()
        .mapToObj(names::get)
        .toList();

// [one, four]
~~~

**Cảnh báo:** Khi dùng `index -> names.get(index)`, phải bảo đảm mọi set-bit index nằm trong `0 .. names.size()-1` và nguồn `names` không bị thay đổi làm mất tính hợp lệ. `BitSet` không tự biết kích thước của collection mà bạn đang muốn ánh xạ nó vào.

## 10. Late-binding và quy tắc không sửa BitSet đang được traverse

Javadoc nói spliterator của `BitSet.stream()` là **late-binding**: nó gắn vào BitSet khi terminal operation bắt đầu.

~~~java
BitSet bits = new BitSet();
bits.set(2);

IntStream stream = bits.stream();

// Stream chưa được tiêu thụ.
bits.set(5);

// Việc quan sát lúc terminal diễn ra theo late-binding contract.
int[] indexes = stream.toArray();
~~~

Điểm trọng tâm: việc tạo stream **không đồng nghĩa tạo snapshot bất biến**.

**Ràng buộc quan trọng hơn:** Nếu `BitSet` bị sửa **trong lúc terminal stream operation đang thực thi**, Javadoc quy định kết quả là **undefined**. Không được suy từ thử nghiệm trên một JDK rằng đây là một nguồn weakly-consistent hay tự động thread-safe.

### Cách dùng sai: sửa BitSet trong callback

~~~java
BitSet bits = new BitSet();
bits.set(1);
bits.set(4);

bits.stream().forEach(index -> {
    bits.set(index + 1); // Không nên: sửa nguồn lúc traverse.
});
~~~

Mã trên là **ví dụ tránh làm**. Có thể thấy kết quả không như mong muốn, bỏ qua phần tử hoặc tình cờ trông đúng trong một lần chạy; **không có cam kết API** về kết quả.

### Nếu cần snapshot ổn định

~~~java
BitSet snapshot = (BitSet) bits.clone();

int[] selectedIndices = snapshot.stream().toArray();
~~~

`clone()` tạo bản sao bằng giá trị tại thời điểm copy theo điều kiện thread-safety của chương trình. Nếu đối tượng `bits` đang bị thread khác sửa không đồng bộ **trong chính lúc clone**, bạn cũng không có một snapshot nhất quán được bảo đảm.

Với dữ liệu được chia sẻ giữa threads, đồng bộ việc tạo snapshot hoặc dùng một cơ chế publish/copy nhất quán. Sau đó không sửa bản `snapshot` cho tới khi stream tiêu thụ xong.

## 11. BitSet.stream và khả năng biểu diễn tập ID

`BitSet` có thế mạnh khi ID là **số nguyên không âm** và không gian chỉ số tương đối phù hợp. Tuy nhiên, đừng tự động chọn nó cho mọi bộ ID:

- Nếu các ID cực kỳ thưa và có giá trị rất lớn, dung lượng của BitSet có thể không hợp lý so với `Set<Integer>`.
- `BitSet` không lưu dữ liệu object gắn với từng ID; nó chỉ lưu trạng thái bit.
- `BitSet.stream()` không trả về thứ tự thêm vào; nó trả index tăng dần.
- Nếu nghiệp vụ cần lưu duplicate occurrences, BitSet chỉ biểu diễn trạng thái set/unset, không biểu diễn tần suất.
- `BitSet.stream()` trả `int` indices theo hợp đồng Java BitSet; không thể dùng type argument `Long` như generic stream.

**Ví dụ lựa chọn:** Đánh dấu “những hàng đã được xử lý” theo index trong một bảng vài trăm nghìn dòng có thể dùng BitSet tốt. Lưu một tập user IDs thưa, âm hoặc không có miền hữu hạn hợp lý thường nên dùng collection/hash-based structure khác.

## 12. JarFile.stream(): duyệt mục lục archive JAR

### 12.1 JarFile và JarEntry

`java.util.jar.JarFile` đọc một JAR, dựa trên định dạng ZIP và hỗ trợ các đặc tính JAR như manifest và multi-release entries.

~~~java
public Stream<JarEntry> stream()
~~~

**Mỗi phần tử là `JarEntry`**, mô tả một entry của archive, chẳng hạn:

- `docs/readme.txt`
- `com/example/App.class`
- `META-INF/MANIFEST.MF`
- Các entries thư mục như `docs/`

`JarFile.stream()` là **Stream có encounter order**. Javadoc quy định entries xuất hiện theo **thứ tự trong central directory của archive**.

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    List<String> names = jar.stream()
            .map(JarEntry::getName)
            .toList();

    System.out.println(names);
}
~~~

Đây là **mã minh họa** với `jarPath` là `Path` và nơi gọi xử lý `IOException`. Danh sách tên phụ thuộc nội dung JAR đang mở; không có một stdout chung cho mọi file.

### 12.2 Thứ tự central directory khác thứ tự chữ cái

Dù `JarFile.stream()` có order, Javadoc **không bảo đảm order đó là alphabetic hoặc theo package depth**.

Nếu cần hiển thị tên file theo thứ tự từ điển:

~~~java
List<String> sorted = jar.stream()
        .filter(entry -> !entry.isDirectory())
        .map(JarEntry::getName)
        .sorted()
        .toList();
~~~

`sorted()` định nghĩa thứ tự mới theo tên String, độc lập với thứ tự entries được ghi vào archive.

**Không dùng `parallel().forEach(System.out::println)` rồi mong các dòng xuất hiện theo central-directory order.** Terminal `forEach` song song không bảo đảm encounter order của side effects. Nếu cần output theo thứ tự, xử lý sequential hoặc dùng `forEachOrdered` với ý thức về chi phí và terminal ordering.

### 12.3 Entries thư mục và entries file

`JarEntry.isDirectory()` giúp phân biệt entry thư mục với file:

~~~java
long files = jar.stream()
        .filter(entry -> !entry.isDirectory())
        .count();
~~~

Nhưng **không bảo đảm** JAR nào cũng chứa entry thư mục cho mọi path prefix; một archive có thể có `docs/readme.txt` mà không có entry `docs/`. Vì vậy `JarFile.stream()` phản ánh **entries được lưu trong archive**, không phải một filesystem directory tree đã được bổ sung ngầm.

Một class-file inventory:

~~~java
List<String> classes = jar.stream()
        .filter(entry -> !entry.isDirectory())
        .map(JarEntry::getName)
        .filter(name -> name.endsWith(".class"))
        .sorted()
        .toList();
~~~

Cách lọc trên chỉ liệt kê entries có tên kết thúc `.class`. Nó **không tự load classes, kiểm tra bytecode, xác minh signatures hoặc tìm Java source files**.

## 13. JarFile.stream không đọc byte[] nội dung của mọi entry

Đây là hiểu nhầm quan trọng nhất của nguồn JAR:

~~~java
jar.stream().map(JarEntry::getName)
~~~

chỉ lấy **metadata tên entry**. Nó không tự động đọc toàn bộ nội dung nén/giải nén của mỗi file.

Để đọc bytes, cần truy cập đúng entry:

~~~java
JarEntry entry = jar.getJarEntry("docs/readme.txt");

if (entry != null && !entry.isDirectory()) {
    try (InputStream in = jar.getInputStream(entry)) {
        byte[] bytes = in.readAllBytes();
        // Giải mã bytes theo charset/hợp đồng của định dạng file.
    }
}
~~~

Đoạn này cần `JarFile` còn mở, imports và xử lý `IOException`. `InputStream.readAllBytes()` có từ Java 9, nên ví dụ yêu cầu Java 9+.

**Lưu ý hiệu năng và an toàn:**

- Đừng `readAllBytes()` vô điều kiện cho entries lớn hoặc không tin cậy; có thể tốn nhiều bộ nhớ.
- Nếu chỉ cần index tên/metadata, tránh giải nén nội dung.
- Nếu cần extract entries ra disk, chuẩn hóa và kiểm tra destination path để chống **path traversal/Zip Slip**.
- Giới hạn tổng dung lượng giải nén, số entries và kích thước file khi xử lý archive không đáng tin.
- JAR có thể có entries ký số; đọc `JarEntry` trong stream **không tương đương xác nhận nội dung/chuỗi chứng chỉ là đáng tin cậy**.

Không dùng `JarFile.stream()` như một scanner bảo mật đầy đủ; nó là API duyệt entries, còn chính sách xác minh/bảo mật phải được thiết kế ở tầng riêng.

## 14. Quản lý vòng đời JarFile: try-with-resources

`JarFile` triển khai `Closeable/AutoCloseable`, nên có thể và nên dùng:

~~~java
try (JarFile jar = new JarFile(file)) {
    long count = jar.stream()
            .filter(e -> !e.isDirectory())
            .count();

    System.out.println(count);
}
~~~

Khi ra khỏi `try`, `jar.close()` được gọi, kể cả nếu code trong block ném exception theo cơ chế try-with-resources.

### Không đóng JAR trước khi tiêu thụ stream

~~~java
Stream<JarEntry> entries;

try (JarFile jar = new JarFile(file)) {
    entries = jar.stream();
}

// Sai: JarFile đã bị đóng; không nên tiêu thụ stream lúc này.
// entries.forEach(System.out::println);
~~~

Tạo stream trong block không tự giữ cho `JarFile` sống mãi. `JarFile.stream()` có thể ném `IllegalStateException` nếu JarFile đã đóng; các thao tác lazy tiêu thụ stream sau khi resource bị đóng cũng không có cơ sở an toàn.

**Nguyên tắc:** tiêu thụ stream **trong thời gian JarFile còn mở**. Nếu cần kết quả sau khi đóng archive, materialize thành List/Map/DTO không phụ thuộc handle mở:

~~~java
List<String> names;

try (JarFile jar = new JarFile(file)) {
    names = jar.stream()
            .map(JarEntry::getName)
            .toList();
}

// names hiện chứa String độc lập với JarFile.
~~~

Không đưa `JarEntry` hay `InputStream` ra ngoài một API mà caller không biết lifetime của chủ sở hữu; nếu cần, tài liệu hóa ownership rõ ràng.

### Stream.close khác JarFile.close

`Stream` có phương thức `close()`, nhưng **không nên mặc định** `jar.stream().close()` sẽ đóng `JarFile` đã tạo nó. `JarFile` là resource chủ sở hữu cần được đóng bằng `jar.close()` (thường nhờ try-with-resources).

Nếu một thư viện trả Stream phụ thuộc vào tài nguyên, thiết kế API phải làm rõ **ai đóng cái gì**. Với `JarFile` trực tiếp, giữ handle trong scope là cách đơn giản và rõ ràng nhất.

## 15. Multi-release JAR: khi stream() khác versionedStream()

Java hiện đại hỗ trợ **multi-release JAR**, có thể chứa các bản class/resource dưới `META-INF/versions/{N}/...` để cung cấp phiên bản thích hợp theo runtime.

Hai API khác nhau:

| API | Có từ | Ngữ nghĩa |
| --- | --- | --- |
| `JarFile.stream()` | Java 8 | Duyệt các entries vật lý theo central directory |
| `JarFile.versionedStream()` | Java 10 | Duyệt entries sau khi xét phiên bản phù hợp với cách JarFile được cấu hình |

`versionedStream()` có thể chọn entry versioned mới nhất thích hợp theo cấu hình multi-release của `JarFile`. Nếu JAR không là multi-release hoặc không được cấu hình để xử lý multi-release, theo Javadoc nó trả cùng nội dung stream như `stream()`.

Điểm dễ nhầm:

- `JarFile.stream()` **không** tự thay mọi `com/example/A.class` bằng phiên bản dành cho runtime khi liệt kê entries vật lý.
- `JarFile.versionedStream()` chỉ có ý nghĩa khác khi JarFile và archive được cấu hình cho multi-release processing thích hợp.
- Đừng chỉ thấy tên thư mục `META-INF/versions/17` rồi tự suy rằng runtime đang dùng bản đó; hãy xác định **phiên bản JAR/JDK và cấu hình JarFile**.
- Nếu mục đích là kiểm kê tất cả entries vật lý trong archive, `stream()` thường hợp lý.
- Nếu mục đích là nhìn logical/versioned view trên runtime được cấu hình phù hợp, cân nhắc `versionedStream()`.

Ví dụ chữ ký (Java 10+):

~~~java
try (JarFile jar = new JarFile(file)) {
    List<String> names = jar.versionedStream()
            .map(JarEntry::getName)
            .toList();
}
~~~

Đây là mã minh họa; không nên khẳng định dữ liệu đã “tự động chọn đúng version cho JVM” nếu không kiểm tra cách `JarFile` được khởi tạo. Hãy đọc Javadoc về constructor nhận `Runtime.Version` khi làm việc nghiêm túc với multi-release archives.

## 16. Một chương trình Java 17+ chạy độc lập: cả ba nguồn và JAR tạm

Chương trình dưới đây **không cần tải thư viện bên ngoài hay chuẩn bị một JAR trước**. Nó tự:

1. Tách một chuỗi bằng regex đã biên dịch.
2. Minh họa token rỗng ở giữa và token rỗng cuối bị bỏ.
3. Đọc các chỉ số bit đang bật.
4. Tạo tệp JAR thử nghiệm trong thư mục tạm.
5. Duyệt entry names và đọc bytes của một entry.
6. Đóng `JarOutputStream`, `JarFile` và `InputStream`; xóa file tạm trong `finally`.

Tạo file **`StreamSourcesDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.BitSet;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;
import java.util.regex.Pattern;

public class StreamSourcesDemo {

    private static void add(
            JarOutputStream out, String name, String content)
            throws IOException {

        JarEntry entry = new JarEntry(name);
        out.putNextEntry(entry);

        if (!name.endsWith("/")) {
            out.write(content.getBytes(StandardCharsets.UTF_8));
        }

        out.closeEntry();
    }

    public static void main(String[] args) throws IOException {
        Pattern csv = Pattern.compile("\\s*,\\s*");

        List<String> colors = csv
                .splitAsStream("red, green,blue, ")
                .map(String::trim)
                .toList();

        System.out.println("tokens=" + colors);

        List<String> gaps = Pattern.compile(",")
                .splitAsStream("a,,b,")
                .map(s -> "[" + s + "]")
                .toList();

        System.out.println("gaps=" + gaps);

        BitSet bits = new BitSet();
        bits.set(1);
        bits.set(4);
        bits.set(9);

        System.out.println("indices=" +
                Arrays.toString(bits.stream().toArray()));

        System.out.println("cardinality=" + bits.cardinality());

        System.out.println("odd=" +
                Arrays.toString(bits.stream()
                        .filter(i -> i % 2 != 0)
                        .toArray()));

        Path jarPath = Files.createTempFile(
                "stream-sources-", ".jar");

        try {
            try (JarOutputStream out = new JarOutputStream(
                    Files.newOutputStream(jarPath))) {

                add(out, "docs/", "");
                add(out, "docs/readme.txt", "hello");
                add(out, "config/", "");
                add(out, "config/app.properties", "mode=demo");
            }

            try (JarFile jar = new JarFile(jarPath.toFile())) {
                List<String> files = jar.stream()
                        .filter(e -> !e.isDirectory())
                        .map(JarEntry::getName)
                        .sorted()
                        .toList();

                System.out.println("jar-files=" + files);
                System.out.println("jar-file-count=" +
                        files.size());

                JarEntry readme =
                        jar.getJarEntry("docs/readme.txt");

                try (InputStream in = jar.getInputStream(readme)) {
                    System.out.println("readme=" +
                            new String(in.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }
            }

        } finally {
            Files.deleteIfExists(jarPath);
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 StreamSourcesDemo.java
java StreamSourcesDemo
~~~

**Stdout đã được kiểm chứng bằng biên dịch/chạy thực tế:**

~~~text
tokens=[red, green, blue]
gaps=[[a], [], [b]]
indices=[1, 4, 9]
cardinality=3
odd=[1, 9]
jar-files=[config/app.properties, docs/readme.txt]
jar-file-count=2
readme=hello
~~~

### Giải thích cụ thể

1. Regex `"\\s*,\\s*"` nhận dấu phẩy kèm whitespace xung quanh. Sau khi tách, khoảng trắng cuối bị loại theo delimiter hoặc `trim`, trailing empty cũng được bỏ nên chỉ còn ba colors.
2. Với `"a,,b,"`, dấu phẩy liên tiếp tạo token rỗng **ở giữa**, còn dấu phẩy cuối không làm xuất hiện token rỗng cuối.
3. `bits.stream()` xuất `1`, `4`, `9` theo thứ tự tăng dần, không phụ thuộc thứ tự gọi `set`.
4. `cardinality()` là `3` vì có đúng ba bit true.
5. Bộ lọc số lẻ trên **chỉ số** trả `1` và `9`. Nó không kiểm tra “giá trị boolean của bit lẻ” — mọi phần tử trong stream vốn đại diện một bit true.
6. Tệp JAR tạm có hai directory entries và hai file entries. `filter(!isDirectory())` giữ hai file, sau đó `sorted()` sắp tên theo thứ tự chữ cái.
7. `JarFile.stream()` mới chỉ đưa ra entries; `jar.getInputStream(readme)` là bước **riêng** để đọc nội dung `"hello"`.
8. `main` khai báo `throws IOException` nên xử lý hợp lệ các checked exceptions có thể phát sinh từ file I/O và JarFile.
9. Các resource handles được đóng trong `try-with-resources`; `finally` xóa tệp thử nghiệm kể cả khi xử lý có exception. Trong ứng dụng thực tế, nếu cleanup cũng có thể thất bại, cần xác định chính sách báo lỗi thích hợp.

Ví dụ dùng `List.toList()` từ `Stream.toList()` (Java 16+) và `InputStream.readAllBytes()` (Java 9+), nên lấy **Java 17+** làm baseline. Ba phương thức nguồn `Pattern.splitAsStream`, `BitSet.stream` và `JarFile.stream` đã có từ Java 8 và vẫn còn hoạt động.

## 17. Khi nào dùng nguồn nào? Ba tình huống thực tế

### 17.1 Tách văn bản thành token

Ví dụ dịch vụ phân tích một chuỗi tùy chọn có nhiều delimiter:

~~~java
Pattern separators = Pattern.compile("[,;|]");

List<String> options = separators
        .splitAsStream("fast;safe|portable,small")
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .toList();
~~~

Kết quả là `[fast, safe, portable, small]`. `String.strip` có từ Java 11. Đoạn này phù hợp khi delimiter có regex rõ, token rỗng không mang nghĩa riêng và không có quoting phức tạp.

**Không dùng nó cho mọi ngôn ngữ có grammar**. Một parser chuyên biệt thích hợp hơn nếu dữ liệu có escape, nested structures hoặc quy tắc tokenization phức tạp.

### 17.2 Lấy các index đang bật từ bitmap

Ví dụ có các vị trí cần xử lý:

~~~java
BitSet dirtyIndexes = new BitSet();
dirtyIndexes.set(3);
dirtyIndexes.set(8);

int[] pending = dirtyIndexes.stream().toArray();

// [3, 8]
~~~

Sau đó code có thể ánh xạ index sang bảng dữ liệu **đã được kiểm tra bounds**. Ưu điểm là không duyệt các vị trí bit false theo cách tạo một phần tử stream cho từng vị trí.

**Không đồng nhất `dirtyIndexes.length()` với số lượng công việc đang chờ**. Sử dụng `cardinality()` hoặc `stream().count()` khi muốn đếm set bits.

### 17.3 Kiểm kê classes/resources bên trong JAR

~~~java
try (JarFile jar = new JarFile(path.toFile())) {
    List<String> classEntries = jar.stream()
            .map(JarEntry::getName)
            .filter(name -> name.endsWith(".class"))
            .sorted()
            .toList();
}
~~~

Kết quả phục vụ inventory, audit build artifacts hoặc kiểm tra có entry tên nhất định. Nhưng nó không chứng minh class đó hợp lệ, class có thể load được trong module hiện tại, hay chữ ký số hợp lệ.

**Đặc biệt với multi-release JAR**, physical entry inventory và logical runtime-selected entries có thể khác nhau. Hãy xác định đúng mục tiêu trước khi chọn `stream()` hay `versionedStream()`.

## 18. Sự khác nhau về lazy evaluation và resource ownership

Cả ba API trả về Stream và cùng tuân theo quy tắc **single-use** của pipeline: một Stream sau terminal operation không thể tùy ý tiêu thụ lần thứ hai. Nhưng tài nguyên gốc của chúng khác nhau:

| Nguồn | Đặc tính cần bảo vệ | Cách bảo vệ |
| --- | --- | --- |
| `Pattern.splitAsStream` | `CharSequence` mutable không được đổi trong terminal | Dùng `String` snapshot hoặc giữ input ổn định |
| `BitSet.stream` | `BitSet` không được sửa trong terminal | Snapshot/synchronization khi cần |
| `JarFile.stream` | `JarFile` phải còn mở khi duyệt; file handle cần đóng | `try-with-resources` và terminal trong scope |

Ví dụ sai:

~~~java
Stream<JarEntry> stream;

try (JarFile jar = new JarFile(file)) {
    stream = jar.stream();
}

// Jar đã bị đóng: không tiêu thụ stream bên ngoài scope.
long count = stream.count();
~~~

Đoạn trên là **mã minh họa lỗi**, không phải chương trình nên chạy. Việc pipeline lazy khiến lifecycle đặc biệt quan trọng: chỉ có object `Stream` không chứng minh nguồn dữ liệu vẫn khả dụng.

### Không dùng lại Stream đã tiêu thụ

~~~java
IntStream indices = bits.stream();

long count = indices.count();

// Sai: cùng stream đã bị consume.
// int sum = indices.sum();
~~~

Nếu cần hai kết quả từ cùng BitSet ổn định, gọi `bits.stream()` **hai lần** hoặc thu thập dữ liệu một lần rồi tính tiếp; nếu nguồn mutable, tính nhất quán giữa hai lần duyệt còn phụ thuộc có ai sửa nguồn ở giữa không.

## 19. Stream operations và ảnh hưởng đến thứ tự

Không được lẫn **thứ tự nguồn** với **thứ tự callback chạy trong parallel pipeline**.

- `Pattern.splitAsStream` sinh các đoạn theo thứ tự văn bản.
- `BitSet.stream` sinh indices từ nhỏ đến lớn.
- `JarFile.stream` là ordered stream theo thứ tự central directory.

Khi dùng:

~~~java
List<String> out = pattern
        .splitAsStream(text)
        .map(String::toUpperCase)
        .toList();
~~~

ordered stream và transformations phù hợp tạo kết quả theo encounter order. Nhưng nếu chuyển sang `parallel()` rồi dùng `forEach(System.out::println)`, **thứ tự những dòng in không được bảo đảm**.

Với JarFile, không nên dùng parallel processing để thực hiện I/O đọc từng entry qua **cùng một resource đang sở hữu file handle** nếu chưa đánh giá kỹ thread-safety, hiệu năng, memory usage và failure semantics. Đặc biệt không dựa vào `parallel()` như một cách “tự động đọc nhanh hơn” archive nén.

### Short-circuit ảnh hưởng phần dữ liệu được đọc

Ví dụ:

~~~java
Optional<String> firstClass = jar.stream()
        .map(JarEntry::getName)
        .filter(name -> name.endsWith(".class"))
        .findFirst();
~~~

Stream có thể dừng khi tìm được class entry đầu tiên theo encounter order. Nếu cần **mọi** class entries, đừng dùng `findFirst()`. Nếu chỉ muốn kiểm tra có ít nhất một entry, dùng `anyMatch(...)` sẽ thể hiện ý định rõ.

Không đặt side effects bắt buộc vào `peek` rồi chờ `count` hoặc `findFirst` luôn thực hiện chúng. Stream API cho phép tối ưu hóa và short-circuiting trong phạm vi hợp đồng.

## 20. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `Pattern.compile(".")` để tách dấu chấm literal | Regex `.` khớp ký tự bất kỳ | `Pattern.quote(".")` hoặc escape đúng |
| Coi `splitAsStream` là parser CSV hoàn chỉnh | Sai với quoted fields, newline/escape | Dùng CSV parser phù hợp |
| Mong trailing empty strings được giữ | Mất cột trống cuối | Chọn `Pattern.split(input, -1)` hoặc parser chuyên biệt |
| Xóa mọi empty token bằng `filter` mà không xét nghiệp vụ | Mất vị trí cột trống ở giữa | Giữ token rỗng nếu có nghĩa |
| Sửa `StringBuilder` trong khi terminal split đang chạy | Kết quả không xác định | Snapshot thành String |
| Coi `BitSet.stream()` là `Stream<Boolean>` | Nhầm nghĩa phần tử | Nhớ đây là `IntStream` của set-bit indices |
| Dùng `length()` để đếm bit true | Sai số lượng | `cardinality()` |
| Dùng `size()` làm số set bits | Nhầm capacity | `cardinality()` |
| Sửa BitSet trong callback/trong khi terminal đang chạy | Kết quả undefined | Bất biến/snapshot trong lúc duyệt |
| Dùng index của BitSet truy cập List không kiểm tra bounds | Có thể `IndexOutOfBoundsException` | Đồng bộ miền chỉ số với collection |
| Quên `isDirectory()` khi đếm file JAR | Đếm cả directory entries | Lọc trước khi count |
| Coi `JarFile.stream()` là Stream byte arrays | Không đọc nội dung như kỳ vọng | Dùng `getInputStream(entry)` |
| Đóng JarFile rồi mới dùng stream | Resource đã đóng | Tiêu thụ stream bên trong `try` |
| Chỉ close Stream, không close JarFile | Có thể rò file handle | Đóng JarFile bằng try-with-resources |
| Coi JarFile stream order là alphabetical | Listing không theo ý muốn | `sorted()` nếu cần |
| Coi `stream()` và `versionedStream()` giống nhau trên mọi multi-release JAR | Nhầm physical/logical view | Kiểm tra cấu hình và phiên bản JDK |
| `readAllBytes()` mọi entry của untrusted JAR | Rủi ro memory/zip bomb | Giới hạn kích thước, stream bytes có kiểm soát |
| Extract entry trực tiếp theo tên không kiểm tra path | Path traversal | Normalize/validate destination path |
| Dùng stream đã có terminal operation lần hai | `IllegalStateException` hoặc lạm dụng stream | Tạo stream mới khi nguồn còn hợp lệ |

## 21. Hỏi đáp nhanh

**Hỏi:** `Pattern.splitAsStream("a,b")` trả array hay Stream?

**Đáp:** `Stream<String>`. Muốn array, dùng `toArray(String[]::new)`. Muốn List, dùng `toList()` ở Java 16+.

**Hỏi:** Vì sao `splitAsStream("a,b,")` không có token rỗng cuối?

**Đáp:** Javadoc quy định loại bỏ trailing empty strings; khác với `Pattern.split(input, -1)`.

**Hỏi:** Có thể dùng regex `,` để tách đúng mọi dữ liệu CSV không?

**Đáp:** Không nếu dữ liệu có trường đặt trong dấu ngoặc kép và dấu phẩy bên trong field; dùng parser định dạng CSV.

**Hỏi:** `BitSet.stream()` trả `true` và `false`?

**Đáp:** Không. Nó trả **các chỉ số có bit true** dưới dạng `IntStream`.

**Hỏi:** `bits.stream().count()` có bằng `bits.length()`?

**Đáp:** Không nói chung. `count` bằng số set bits, tức `cardinality()`, khi nguồn ổn định.

**Hỏi:** BitSet thay đổi giữa lúc tạo Stream và lúc terminal có được không?

**Đáp:** Nó dùng late-binding; không nên coi stream là snapshot. Điều đặc biệt cần tránh là **thay đổi BitSet trong khi terminal operation đang chạy**, vì kết quả undefined.

**Hỏi:** JarFile.stream trả Java classes đã load?

**Đáp:** Không. Nó trả `JarEntry` trong archive, có thể gồm tệp `.class`, resources và directory entries. Nó không tự load class.

**Hỏi:** Stream JarFile có tự đóng JAR?

**Đáp:** Không nên giả định như vậy. Đóng resource chủ sở hữu `JarFile` bằng `try-with-resources`.

**Hỏi:** Muốn liệt kê classes cho runtime từ multi-release JAR thì luôn dùng `stream()`?

**Đáp:** Không. `stream()` liệt kê physical entries; `versionedStream()` có thể phù hợp với logical versioned view nếu JarFile được cấu hình multi-release đúng.

## 22. Bài tập thực hành

**Bài 1 — Tách đúng delimiter.** Tách `"api.example.com"` theo dấu chấm literal bằng `Pattern.quote(".")`. Kết quả mong đợi: `[api, example, com]`.

**Bài 2 — Token rỗng.** Với `"x,,y,"`, dùng `Pattern.compile(",").splitAsStream(...)`. Dự đoán các token và giải thích vì sao token cuối không xuất hiện.

**Bài 3 — Giữ cột rỗng.** Hãy dùng `Pattern.split(text, -1)` để giữ cả trailing empty fields của `"x,y,"`. So sánh với `splitAsStream`.

**Bài 4 — Regex zero-width.** Với `Pattern.compile("(?=a)")` và input `"abc"`, giải thích vì sao không có empty token đứng đầu.

**Bài 5 — Input mutable.** Viết một ví dụ sử dụng `StringBuilder` làm `CharSequence` cho `splitAsStream`. Vì sao không được sửa nó trong terminal? Viết lại bằng `toString()` snapshot.

**Bài 6 — Bit indices.** Tạo `BitSet` và set chỉ số `0`, `3`, `8`. In `bits.stream().toArray()` và `bits.cardinality()`. Giải thích khác nhau giữa số phần tử và `length()`.

**Bài 7 — Ánh xạ từ index sang object.** Có `List<String> students` và `BitSet selected`. Viết `selected.stream().mapToObj(students::get).toList()`, đồng thời bảo đảm tất cả indices nằm trong phạm vi hợp lệ.

**Bài 8 — Không sửa nguồn.** Viết đoạn cố ý sai thay đổi `BitSet` trong `forEach`, rồi sửa bằng clone/snapshot và tách rõ bước cập nhật sau traversal.

**Bài 9 — Kiểm kê JAR.** Dùng `JarFile.stream` để lấy List các tên entry kết thúc `.class` theo thứ tự từ điển; không đọc bytes nếu chỉ cần tên.

**Bài 10 — Resource scope.** Tạo JAR tạm, dùng `try-with-resources` cho cả `JarOutputStream` lẫn `JarFile`. Vì sao phải tiêu thụ `jar.stream()` trong khi JarFile còn mở?

**Bài 11 — Multi-release.** Nêu tình huống `JarFile.stream()` và `JarFile.versionedStream()` có thể khác. Vì sao cấu hình versioned processing quan trọng?

**Bài 12 — Thiết kế an toàn.** Một dịch vụ tải JAR do người dùng cung cấp và trích xuất resources. Xác định ít nhất bốn kiểm tra ngoài việc gọi `JarFile.stream()`: giới hạn dung lượng, kiểm tra entry paths, đóng resource và xác thực định dạng/chính sách tin cậy.

## 23. Tổng kết trọng tâm

- **`Pattern.splitAsStream`** tách `CharSequence` theo regex thành `Stream<String>`. Nó giữ thứ tự token, loại bỏ trailing empty strings, phân biệt positive-width và zero-width match ở đầu, và không tự thực hiện CSV parsing phức tạp.
- **`BitSet.stream`** trả `IntStream` các **chỉ số set bits theo thứ tự tăng dần**. Số phần tử bằng `cardinality()` khi nguồn ổn định; stream late-binding và không được sửa BitSet trong terminal operation.
- **`JarFile.stream`** trả ordered `Stream<JarEntry>` theo **central-directory order**, không phải nội dung bytes hay Java classes đã load. Lọc `isDirectory` nếu chỉ cần file entries.
- **`JarFile` sở hữu tài nguyên**; dùng `try-with-resources` và tiêu thụ Stream khi archive còn mở. Muốn đọc nội dung dùng `getInputStream` riêng và đóng stream ấy.
- **`JarFile.versionedStream` (Java 10+)** dành cho view versioned khi multi-release JAR được cấu hình phù hợp; không đồng nhất với physical stream trong mọi trường hợp.
- Cả ba phương thức nguồn đã có từ Java 8 và **vẫn là API hợp lệ trong Java hiện đại**; chương trình chính chọn Java 17+ để tận dụng `Stream.toList()` và `InputStream.readAllBytes()`.

## 24. Tài liệu chính thức

1. Java SE 26 Javadoc — `Pattern.splitAsStream(CharSequence)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html#splitAsStream(java.lang.CharSequence)
2. Java SE 26 Javadoc — `BitSet.stream()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html#stream()
3. Java SE 26 Javadoc — `JarFile.stream()`, `JarFile.versionedStream()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html
4. Java SE 17 Javadoc — `Pattern`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
5. Java SE 17 Javadoc — `BitSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html
6. Java SE 17 Javadoc — `JarFile` và `JarEntry`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
7. Java SE 17 Javadoc — `IntStream` và `Stream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
8. Java SE 25 JAR File Specification — phần multi-release JAR: https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html
9. Java SE 17 Javadoc — `JarOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html

Khi chọn một Stream source, đừng chỉ xem tên phương thức `stream()`. Hãy luôn hỏi: **mỗi phần tử biểu diễn điều gì, nguồn có thể thay đổi hay không, encounter order là gì, và ai chịu trách nhiệm đóng tài nguyên?** Ba câu hỏi đó quyết định cách dùng `Pattern.splitAsStream`, `BitSet.stream` và `JarFile.stream` đúng, an toàn và dễ bảo trì.
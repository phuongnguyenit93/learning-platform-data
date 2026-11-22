# Đối chiếu `Since`: phân biệt nguồn gốc API với cải tiến mới (Java 11 và JDK hiện hành)

## 1. Mục tiêu: biết chính xác **API nào** có từ phiên bản **nào**

Khi đọc tài liệu Java, một câu như “`String` là class từ ngày đầu”, “Java 11 có cải tiến về String” và “JDK 26 vẫn hỗ trợ `String.strip()`” đều có thể đúng, nhưng **không đồng nghĩa với nhau**. Điểm quan trọng là **xác định chính xác declaration đang dùng** và thời điểm declaration đó trở thành API được công bố.

Ví dụ:

```java
String value = "  Hello  ";
System.out.println(value.trim());       // API cũ, vẫn dùng được
System.out.println(value.strip());      // Method được thêm ở Java 11
System.out.println(value.repeat(2));    // Method được thêm ở Java 11
// System.out.println(value.indent(2));  // Method chỉ có từ Java 12
```

Trong Javadoc, các method `strip()`, `repeat(int)` của `java.lang.String` có thông tin **`Since: 11`**, còn `indent(int)` có **`Since: 12`**. Điều đó **không** biến bản thân class `String` thành một “class mới của Java 11”, và cũng **không** làm `String.indent` thành API Java 11 chỉ vì JDK 26/27 còn cung cấp nó.

**Câu hỏi chuẩn** không phải “class này có mới không?”, mà là:

> Với Java API chính xác gồm **fully qualified class**, **method/constructor**, **tham số và return type**, declaration này được bổ sung từ release nào; và runtime/build target của dự án có cung cấp declaration đó không?

Bài này thuộc nhóm **Kiểm chứng API** cho module **Java 11**. Nó trình bày cách đọc `Since` ở tài liệu chính thức, nhận diện API Java 11 thật, tách biệt API thêm ở JDK mới hơn, kiểm chứng bằng `javac --release 11`, và tránh nhầm lịch sử của class với thời điểm xuất hiện của method mới.

**Giới hạn kiến thức:** chỉ sử dụng các API hiện vẫn được hỗ trợ; các ví dụ kiểu `@since 1.7` hoặc flags biên dịch cũ được nhắc đến để **giải thích cách đọc và tránh sai**, không khuyến nghị quay về cơ chế lỗi thời.

## 2. `Since` trong Javadoc là gì?

Javadoc dùng tag **`@since`** trong mã nguồn documentation comment để biểu thị release đầu tiên giới thiệu **một API element**. Khi sinh tài liệu HTML, thông tin này thường hiện thành nhãn **`Since: 11`**, **`Since: 16`** hay **`Since: 1.8`** ở phần mô tả class/method/constructor.

Ví dụ ý tưởng:

```java
/**
 * A helper class published in release 11 of a library.
 *
 * @since 11
 */
public class TextHelper {
    /**
     * A method added when the class first shipped.
     * @since 11
     */
    public String normalize(String s) {
        return s.strip();
    }
}
```

Trong thư viện do bạn quản lý, `@since` là **cam kết tài liệu** do người viết API gắn vào element. Khi biên dịch, `javac` **không có cơ chế đặc biệt tự động từ chối source dựa vào nội dung `@since` của Javadoc**. Trình biên dịch kiểm tra những declarations thật sự có trong **API surface của platform release** đã chọn.

### Một số release labels hay gặp

| Dạng `Since` | Đọc như | Tránh hiểu sai |
| --- | --- | --- |
| `Since: 1.2` | JDK 1.2 | Không phải Java 12 |
| `Since: 1.5` | Java 5 | Không phải Java 15 |
| `Since: 1.7` | Java 7 | Không phải Java 17 |
| `Since: 1.8` | Java 8 | Không phải Java 18 |
| `Since: 9` | Java 9 | Không cần thêm tiền tố `1.` |
| `Since: 11` | Java 11 | Có mặt từ Java 11, không chỉ Java 11 |
| `Since: 16` | Java 16 | Không nằm trong public API baseline Java 11 |
| `Since: 21` | Java 21 | Không biên dịch bằng `--release 11` nếu gọi trực tiếp API mới |

**`Since: 11` không phải dòng "đã cũ" hay "deprecated".** Một method có `Since: 11` vẫn có thể là cách sử dụng khuyến nghị trên JDK 27. Người đọc phải kiểm tra thêm trạng thái deprecation, Javadoc notes và các thay đổi hành vi nếu có.

### `@since` không phải Java annotation runtime

`@since` là **Javadoc block tag** trong comment:

```java
/**
 * @since 11
 */
public void execute() { }
```

Nó không tương đương một annotation kiểu `@Since(11)` mà có thể gọi `Class.getAnnotation(...)` để đọc ở runtime. Những API reflection như `getDeclaredMethods()` thường **không cung cấp năm giới thiệu của method**. Để truy xuất thông tin lịch sử, dùng Javadoc/nguồn release và kiểm chứng API availability khi compile.

## 3. Các cấp độ phải đối chiếu riêng

Giả sử tài liệu Javadoc có đường dẫn:

```text
java.base/java/lang/String.html
```

Có nhiều cấp khác nhau:

1. **Module:** `java.base` tồn tại từ thời hệ thống module Java 9 (tên module không phải bằng chứng mọi class trong nó ra đời ở Java 9).
2. **Package:** `java.lang` có lịch sử riêng.
3. **Class/interface:** `java.lang.String` đã có từ những release rất sớm.
4. **Constructor:** mỗi overload có thể được giới thiệu tại các release khác nhau.
5. **Method:** `String.strip()` và `String.indent(int)` có `Since` khác nhau.
6. **Field/constant:** static field có thể được thêm mới sau khi class tồn tại.
7. **Method overload:** cùng tên nhưng parameters khác có thể có `Since` khác nhau.
8. **Inherited/default method:** method nhìn thấy ở class có thể được **khai báo trong supertype/interface**, với lịch sử gốc khác class đang xem.

Vì vậy, **không lấy `Since` ở đầu class rồi gán cho mọi method phía dưới**.

Ví dụ:

```text
java.lang.String
  ├─ trim()          -> API rất cũ
  ├─ isEmpty()       -> API có trước Java 11
  ├─ strip()         -> Since: 11
  ├─ isBlank()       -> Since: 11
  ├─ lines()         -> Since: 11
  ├─ repeat(int)     -> Since: 11
  ├─ indent(int)     -> Since: 12
  ├─ transform(...)  -> Since: 12
  └─ formatted(...)  -> Since: 15
```

Đây là cách đọc **theo member**, không phải timeline của toàn package `java.lang`.

### Overload là một nguồn lỗi rất phổ biến

Ví dụ giả định một thư viện:

```java
void send(String text);                  // @since 1.0
void send(String text, Duration timeout); // @since 2.3
```

Cùng tên `send` không có nghĩa cả hai overload cùng một thời điểm xuất hiện. Muốn xác định phiên bản tối thiểu phải so **cả danh sách tham số**. Kiểm tra Javadoc **Method Detail** của overload thực sự được trình biên dịch chọn, không chỉ một dòng ở **Method Summary**.

Với methods có generic types, varargs, bridge methods hoặc type erasure, phải xác định đúng declaration public API thay vì kết luận chỉ từ tên method trong bytecode.

## 4. Phân biệt bốn câu hỏi về phiên bản

| Câu hỏi | Nguồn kiểm chứng chính | Ví dụ |
| --- | --- | --- |
| **API được giới thiệu khi nào?** | Javadoc `Since` ở declaration, docs release tương ứng | `String.strip()` — 11 |
| **Bản JDK hiện hành còn có API không?** | Javadoc version hiện hành + build thực tế | `String.strip()` vẫn có |
| **API có sẵn trong target Java 11 không?** | `javac --release 11` + tài liệu Java SE 11 | `Stream.toList()` — không |
| **API có phù hợp/khuyến nghị ở hiện tại không?** | Javadoc notes, deprecated/forRemoval, security/correctness guidance | `String.trim()` vẫn có nhưng khác ngữ nghĩa với `strip()` |

**Không dùng một nguồn để trả lời cả bốn câu.** Ví dụ đọc Javadoc JDK 27 chỉ chứng minh API hiện tồn tại ở JDK 27, không tự chứng minh nó đã có ở JDK 11. Ngược lại, `Since: 11` nói thời điểm đưa vào API, không đủ chứng minh phương pháp sử dụng vẫn được khuyến nghị trong mọi use case hoặc không có behavior changes sau đó.

### Cần phân biệt với những sự kiện khác

- **API introduction:** method/class được thêm vào public documented API.
- **Behavioral improvement:** implementation, performance, Unicode data, default behavior hoặc correctness thay đổi mà method đã tồn tại từ trước.
- **Language feature:** cú pháp Java như `var` hoặc switch expression — cần tra JLS/release/`javac --release`, không đọc `Since` của một class để suy ra.
- **JVM/GC feature:** ZGC, class-file attributes, VM options — phải kiểm tra JVM specification/tuning docs/JEP và runtime support, không thể tìm một `@since` duy nhất.
- **Preview/incubator:** một feature hoặc module được thử nghiệm ở release này rồi chuẩn hóa/thay đổi API ở release khác. Không lấy release thử nghiệm làm mốc **stable API** của package sau cùng.
- **Backport/vendor-specific API:** runtime/vendor có thể backport sửa lỗi hoặc thêm chức năng riêng; `Since` của Java SE không tự chứng minh một vendor build tùy chỉnh có cùng API.

## 5. Bảng mốc API Java 11 thật (và vẫn được dùng)

Dưới đây là những **public Java APIs thực sự có từ Java 11**, không phải toàn bộ API của class tương ứng.

| API declaration | `Since` | Phân biệt nguồn gốc với cải tiến | Dùng để |
| --- | --- | --- | --- |
| `String.strip()` | 11 | `String` tồn tại lâu, `trim()` đã có từ trước | Loại bỏ Unicode white space ở hai đầu theo `Character.isWhitespace` |
| `String.stripLeading()` | 11 | Method mới trên class cũ | Loại bỏ leading white space |
| `String.stripTrailing()` | 11 | Method mới trên class cũ | Loại bỏ trailing white space |
| `String.isBlank()` | 11 | Khác `isEmpty()` có từ trước | Kiểm tra rỗng hoặc chỉ chứa white space codepoints |
| `String.lines()` | 11 | Khác `split(...)` có trước | Stream các dòng, xử lý lười khi tiêu thụ |
| `String.repeat(int)` | 11 | Method tiện ích mới | Lặp nội dung một số lần |
| `Optional.isEmpty()` | 11 | `Optional` có từ Java 8, `isPresent()` cũ | Kiểm tra không có giá trị |
| `Predicate.not(Predicate)` | 11 | `Predicate` có từ Java 8, `negate()` cũ | Lật predicate phù hợp method reference |
| `Path.of(String, String...)` | 11 | `Path`/`Paths` có từ Java 7 | Tạo `Path` từ các thành phần |
| `Path.of(URI)` | 11 | Overload tạo `Path` từ `URI` | Tạo `Path` từ URI |
| `Files.readString(Path)` | 11 | `Files` có từ Java 7 | Đọc file text UTF-8 vào `String` |
| `Files.readString(Path, Charset)` | 11 | Overload có charset | Đọc text dùng charset chỉ định |
| `Files.writeString(Path, CharSequence, ...)` | 11 | Method mới trên `Files` | Ghi chuỗi ra file UTF-8 |
| `Files.writeString(Path, CharSequence, Charset, ...)` | 11 | Overload có charset | Ghi text với charset chỉ định |
| `java.net.http.HttpClient` | 11 | Public **standard API/module** `java.net.http` | HTTP Client/WebSocket hiện đại |
| `java.net.http.HttpRequest` | 11 | Cùng module | Tạo yêu cầu HTTP |
| `java.net.http.HttpResponse` | 11 | Cùng module | Xử lý response |
| `Collection.toArray(IntFunction<T[]>)` | 11 | Interface `Collection` lâu đời; overload thêm | Tạo typed array bằng generator |

**Ghi chú về phạm vi bảng:**

- `Files.readString` và `writeString` phù hợp cho file text **không quá lớn**; không nên đọc file hàng GB vào một `String` chỉ vì API có sẵn.
- `Path.of(...)` là lựa chọn hiện hành được khuyến nghị trong API note so với một số cách dùng `Paths.get(...)`; **`Paths.get` không phải tự động đã deprecated**.
- `java.net.http` được chuẩn hóa ở Java 11. Những incubator HTTP client modules của release trước là lịch sử phát triển, **không dùng làm chuẩn API tương thích Java 11**.
- Mỗi member cụ thể có thể có Javadoc notes/overloads riêng; luôn mở phần detail để xác nhận signature.

## 6. So sánh với các API mới xuất hiện **sau Java 11**

| API | `Since` | Có thể dùng trực tiếp với `--release 11`? | Hướng xử lý khi phải giữ Java 11 |
| --- | --- | --- | --- |
| `String.indent(int)` | **12** | Không | Tự xử lý indentation/line endings theo yêu cầu, tránh giả định tương đương hoàn toàn |
| `String.transform(Function)` | **12** | Không | Gọi function trực tiếp, ví dụ `fn.apply(text)` |
| `Files.mismatch(Path, Path)` | **12** | Không | So sánh bytes bằng cách streaming hoặc giải pháp có sẵn phù hợp |
| `String.formatted(Object...)` | **15** | Không | `String.format(format, args)` (đã có từ lâu) |
| `Stream.toList()` | **16** | Không | `stream.collect(Collectors.toList())` nếu semantics phù hợp |
| `java.util.HexFormat` | **17** | Không | Dùng encoder/decoder khác phù hợp hoặc implementation kiểm thử được |
| `java.util.SequencedCollection` | **21** | Không | Dùng `List`, `Deque` hoặc collection contract phù hợp của Java 11 |
| `List.reversed()` | **21** | Không | Dùng view/copy/sắp xếp phù hợp; không giả định mọi List đều có reversed-view API |
| `RecordedThread.isVirtual()` trong JFR | **21** | Không | Đối với Java 11 không có virtual-thread API tương ứng |

**Lưu ý quan trọng:** Cột Java 11 ở trên nói về **compile-time availability** của platform public APIs. Nó không khẳng định mọi API tương lai có thể thay bằng một dòng code với **cùng ngữ nghĩa**. Ví dụ `Stream.toList()` trả một danh sách **unmodifiable**; `Collectors.toList()` không hứa cụ thể kiểu hay khả năng sửa đổi trong API contract. Hai phương thức khác nhau ở semantics dù kết quả in ra có thể giống.

### Trường hợp `String.indent`

```java
// Java 12+:
String text = "a\nb";
String indented = text.indent(2);
```

`indent(int)` còn **chuẩn hóa line endings** và thêm LF cuối các dòng theo contract, không chỉ thêm khoảng trắng. Không nên ghi “Java 11 có `String.indent`” vì class `String` hoặc method `lines` có từ Java 11.

### Trường hợp `Stream.toList`

```java
// Java 16+:
List<String> names = Stream.of("a", "b").toList();

// Java 11, nếu contract collector phù hợp:
List<String> names11 =
        Stream.of("a", "b").collect(Collectors.toList());
```

**Đoạn code là ví dụ hai cách khác nhau trong cùng ngữ cảnh**, không phải cam kết list có đầy đủ cùng behavior. Khi yêu cầu unmodifiable list ở Java 11, có thể cân nhắc `Collectors.toUnmodifiableList()` (có từ Java 10), nhưng nó **từ chối `null`**, trong khi `Stream.toList()` có thể chứa null; xác nhận yêu cầu dữ liệu trước khi đổi.

`List.of(...)` là API Java 9; `List.copyOf(...)` từ Java 10. Đừng nói mọi “immutable list conveniences” mới đến ở Java 16 chỉ vì `Stream.toList` xuất hiện khi ấy.

### Trường hợp `String.formatted`

```java
// Java 15+:
String text = "User: %s".formatted("Ana");

// Java 11:
String text11 = String.format("User: %s", "Ana");
```

Cả hai dựa trên formatting rules liên quan, nhưng điều đó không khiến `String.formatted` có ở Java 11. Tra method detail sẽ thấy `Since: 15`; method `String.format` đã có từ lâu hơn.

## 7. Cách tìm và xác nhận `Since` trên trang Javadoc chính thức

### Bước 1 — Xác định **fully qualified name**

Từ code:

```java
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(Path.of("input.txt"));
```

Có **hai API cần kiểm tra riêng**:

1. `java.nio.file.Files.readString(Path)`.
2. `java.nio.file.Path.of(String, String...)`.

Nếu chỉ kiểm tra class `Files` có từ Java 7 rồi kết luận `readString` dùng được trên Java 7, bạn sẽ sai.

### Bước 2 — Mở đúng Javadoc **theo version target**

Ví dụ baseline Java 11:

- `java.lang.String`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html
- `java.nio.file.Files`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html
- `java.nio.file.Path`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Path.html
- `java.util.stream.Stream`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/stream/Stream.html

**Nếu method không xuất hiện trong Javadoc của target version, chưa thể tự cho rằng nó thuộc public API version ấy.** Hãy so với version sau và kiểm tra compile để phân biệt tên/overload hoặc tài liệu khác.

### Bước 3 — Vào **Method Detail** / **Constructor Detail**

Bảng tóm tắt liệt kê overloads thuận tiện để tìm kiếm, nhưng phần detail mới giúp đọc:

- signature chính xác, type parameters, return type;
- `Since`;
- `Deprecated`, `API Note`, `Implementation Note`;
- behavior, exceptions, default charset hay mutability;
- links `Specified by` / `Overrides` / `See Also` khi method kế thừa hoặc implement từ supertype.

Đừng chỉ tìm chuỗi “Since: 11” xuất hiện ở bất kỳ vị trí nào của trang: trong một trang có thể có hàng chục `Since` của **những members khác nhau**.

### Bước 4 — Đối chiếu Javadoc hiện hành

Mở cùng class ở JDK hiện hành, ví dụ JDK 26/27, và kiểm tra API cụ thể:

- `String.strip()` vẫn có `Since: 11`.
- `String.indent(int)` vẫn có `Since: 12`.
- `Stream.toList()` có `Since: 16`.
- `Files.mismatch(Path, Path)` có `Since: 12`.

**Một method xuất hiện ở cả Javadoc 11 và 26 không đồng nghĩa implementation byte-for-byte giống nhau**. `Since` nói thời điểm public API được giới thiệu, không chứng minh behavior, performance và security fixes không thay đổi.

### Bước 5 — Thử bằng compiler đúng mục tiêu

```bash
javac --release 11 Example.java
```

Trên JDK mới hỗ trợ `--release 11`, compiler kiểm tra **Java 11 language rules**, **class-file target** và **public documented Java 11 API surface**. Đây là bước chống nhầm quan trọng nhất khi người học nhìn tài liệu JDK 26/27 trong IDE đang cấu hình JDK mới.

### Bước 6 — Test trên runtime target thực

Ngay cả khi compile đúng, vẫn nên chạy integration tests trên **Java 11 runtime** nếu dự án thực sự deploy Java 11: external dependencies, reflection, service loading, native libraries, multi-release JARs và môi trường triển khai có thể tạo incompatibilities không được một compilation đơn lẻ phát hiện.

**Ngược lại**, nếu dự án có source target Java 11 nhưng deployment chỉ dùng JDK 21/25/27, cần tách biệt **policy compile target** với **minimum deployed runtime**. Không tự tuyên bố dự án hỗ trợ chạy Java 11 nếu build đã dùng API chỉ có ở Java 16.

## 8. Vì sao `--release` cần thiết hơn chỉ dùng `-source` và `-target`

Trên một JDK mới, có ba khái niệm:

| Option | Kiểm soát | Điều **không** đủ bảo đảm |
| --- | --- | --- |
| `--source 11` | Cú pháp/quy tắc ngôn ngữ Java 11 | Không hạn chế public JDK APIs mới nếu không khóa API platform |
| `--target 11` | Class-file version tương ứng Java 11 | Không chứng minh mọi method references có trên Java 11 runtime |
| **`--release 11`** | **Ngôn ngữ, class-file target và API surface Java 11** | Không thay thế runtime test hoặc kiểm tra dependencies ngoài JDK |

Trình biên dịch JDK 24 đã **trực tiếp in cảnh báo** khi thử `-source 11 -target 11` mà không đặt platform APIs:

```text
warning: [options] location of system modules is not set
in conjunction with -source 11
...
--release 11 is recommended instead of -source 11 -target 11
```

Đây là cảnh báo **đã được quan sát trong lần thử**, không phải lời gợi ý chung do bài viết tự bịa. Nó giải thích một bẫy: code viết cú pháp Java 11, bytecode version 55, nhưng có thể tham chiếu method chỉ có từ Java 12/15/16.

### Class-file version không phải “minimum JDK API version”

Một file `.class` có:

```text
major version: 55
```

chỉ chứng minh compiler đã tạo **class file theo định dạng Java 11**. Nó không chứng minh mọi symbolic method/class references được dùng trong file đều tồn tại trong public Java 11 APIs. Khi code như vậy chạy trên JDK 11, có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError` khi JVM cần resolve reference đến API mới.

**`UnsupportedClassVersionError` là một vấn đề khác**: runtime không hiểu **class-file major version** của class đang load. Không gộp lỗi “class file quá mới” với lỗi “method không có ở runtime” thành cùng một nguyên nhân.

## 9. Demo 1 — Mười thao tác có `Since: 11` biên dịch được bằng `--release 11`

Chương trình độc lập dưới đây kiểm tra nhiều public APIs của Java 11 mà **không** cần thư viện ngoài. Nó chứng minh các method mới trên những class đã tồn tại từ các Java release trước.

**Tên file:** `ApiSince11Demo.java`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Optional;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class ApiSince11Demo {
    public static void main(String[] args) throws Exception {
        String value = "\u2003 Hello \u2003";

        System.out.println(
                "stripEqualsHello=" + value.strip().equals("Hello"));
        System.out.println(
                "trimKeepsEmSpace=" +
                value.trim().startsWith("\u2003"));
        System.out.println(
                "isBlank=" + "\t\u2003".isBlank());

        System.out.println(
                "repeat=" + "na".repeat(3));

        System.out.println(
                "lines=" + "one\r\ntwo\n"
                        .lines()
                        .collect(Collectors.joining("|")));

        System.out.println(
                "optionalEmpty=" +
                Optional.<String>empty().isEmpty());

        String nonBlank = Stream.of("", " Java ", "\t", "11")
                .filter(Predicate.not(String::isBlank))
                .map(String::strip)
                .collect(Collectors.joining(","));

        System.out.println("nonBlank=" + nonBlank);

        Path path =
                Files.createTempFile("java-api-since-", ".txt");
        try {
            Files.writeString(
                    path, "Hello Java 11\n", StandardCharsets.UTF_8);

            System.out.println(
                    "fileContent=" +
                    Files.readString(
                            path, StandardCharsets.UTF_8).strip());
        } finally {
            Files.deleteIfExists(path);
        }

        System.out.println(
                "pathOfMatchesPathsGet=" +
                Path.of("guide", "intro.txt").equals(
                        Paths.get("guide", "intro.txt")));
    }
}
```

### Biên dịch/chạy

```bash
javac --release 11 ApiSince11Demo.java
java ApiSince11Demo
```

Với một JDK mới vẫn hỗ trợ `--release 11`, chương trình trên đã được **biên dịch thành công bằng javac 24.0.2** và chạy trên cùng runtime. Nó chỉ dùng public Java 11 methods; mặc dù được kiểm tra chạy bằng JDK 24, **mục tiêu Java 11 đã được compiler kiểm chứng**.

### Stdout đã kiểm chứng

```text
stripEqualsHello=true
trimKeepsEmSpace=true
isBlank=true
repeat=nanana
lines=one|two
optionalEmpty=true
nonBlank=Java,11
fileContent=Hello Java 11
pathOfMatchesPathsGet=true
```

### Đối chiếu từng dòng với `Since`

1. **`stripEqualsHello=true`**: `String.strip()` có `Since: 11`, loại bỏ Unicode white space ở hai đầu.
2. **`trimKeepsEmSpace=true`**: `String.trim()` dùng quy tắc cũ, không đồng nghĩa `strip()`. Ở ví dụ, U+2003 EM SPACE còn lại khi dùng `trim`.
3. **`isBlank=true`**: `String.isBlank()` có `Since: 11`; khác `isEmpty()` vì chuỗi có ký tự white space nhưng không có non-whitespace code point.
4. **`repeat=nanana`**: `String.repeat(int)` có `Since: 11`; `count=3` lặp `"na"` ba lần. Count âm gây `IllegalArgumentException` theo contract.
5. **`lines=one|two`**: `String.lines()` có `Since: 11`; `\r\n` và `\n` được coi là line terminators, không sinh dòng rỗng phụ sau terminator cuối.
6. **`optionalEmpty=true`**: `Optional.isEmpty()` có `Since: 11`; bản thân `Optional` đã có từ Java 8.
7. **`nonBlank=Java,11`**: `Predicate.not(...)` có `Since: 11`; `Predicate` và `negate()` có từ Java 8. `String.isBlank` và `strip` cũng là methods Java 11.
8. **`fileContent=Hello Java 11`**: `Files.writeString` và `readString` có `Since: 11`; `Files` và `Path` đã tồn tại ở Java 7.
9. **`pathOfMatchesPathsGet=true`**: `Path.of(...)` có `Since: 11`; `Paths.get(...)` có trước. Cả hai tạo đường dẫn tương đương trong default filesystem ở ví dụ.

**Không có thư viện third-party** hoặc server bên ngoài; file tạm được tạo, đọc, xóa trong `try/finally`. Việc đặt charset UTF-8 tường minh giữ ngữ nghĩa rõ, dù overload `Files.readString(Path)` đã mặc định UTF-8.

## 10. Demo 2 — API thêm sau Java 11 bị `--release 11` từ chối

Dùng một file khác để minh họa **negative compilation test**.

**Tên file:** `NewerApisDemo.java`

```java
import java.util.stream.Stream;

public final class NewerApisDemo {
    public static void main(String[] args) {
        System.out.println(
                "a\nb".indent(2).replace("\n", "|"));
        System.out.println(
                Stream.of("x", "y").toList().size());
        System.out.println(
                "%s-%d".formatted("x", 2));
    }
}
```

Ba API trên có thời điểm giới thiệu **khác nhau**:

| Dòng | API thật | `Since` |
| --- | --- | --- |
| `"a\nb".indent(2)` | `String.indent(int)` | 12 |
| `Stream.of(...).toList()` | `Stream.toList()` | 16 |
| `"%s-%d".formatted(...)` | `String.formatted(Object...)` | 15 |

### Lệnh kiểm tra Java 11

```bash
javac --release 11 NewerApisDemo.java
```

**Kết quả đã kiểm chứng bằng javac 24.0.2:** biên dịch **thất bại** với ba lỗi `cannot find symbol`, lần lượt:

```text
symbol:   method indent(int)
location: class String

symbol:   method toList()
location: interface Stream<String>

symbol:   method formatted(String,int)
location: class String

3 errors
```

Các dòng trên là **trích các thông tin lỗi chính** (file path, line numbers và dấu `^` trong diagnostic thực đã lược đi). Failure ở bước compile là **kết quả đúng và mong đợi** của kiểm chứng Java 11, không phải một bug compiler.

### Dùng `-source 11 -target 11` lại biên dịch được — đây là bẫy

Trên **JDK 24**:

```bash
javac -source 11 -target 11 NewerApisDemo.java
javap -verbose NewerApisDemo.class
java NewerApisDemo
```

**Kết quả thử:**

- `javac` **thành công nhưng phát cảnh báo** vì không khóa API platform Java 11.
- `javap` báo **`major version: 55`** — định dạng class file Java 11.
- Chương trình chạy **trên JDK 24** và in:

```text
  a|  b|
2
x-2
```

Dòng đầu có **hai dấu cách** trước `a` và `b` do `indent(2)` thêm indentation; dấu `|` thay newline. Đây là output trên JDK mới, **không** khẳng định chương trình chạy được trên JDK 11.

**Vì sao nguy hiểm?** JVM Java 11 có thể load `major 55` nhưng **không có** `String.indent(int)`, `String.formatted(...)` hay `Stream.toList()`. Khi bytecode thực thi tới một reference thiếu, việc liên kết method có thể thất bại bằng **`NoSuchMethodError`**. Đây là lý do `--release 11` là bước kiểm chứng mạnh hơn `-source 11 -target 11` đơn thuần.

### Nếu đã chạy chương trình trên JDK mới thành công thì sao?

Thành công ở JDK 24 chỉ chứng minh:

```text
Current runtime has the referenced APIs
```

Không chứng minh:

```text
Minimum runtime Java 11 has the referenced APIs
```

Muốn thật sự hỗ trợ Java 11, giữ `--release 11` trong build, kiểm tra dependencies và chạy tests ít nhất trên một JDK 11 runtime được hỗ trợ bởi policy của dự án.

## 11. Demo 3 — Javadoc `@since` không thay thế compiler checks

Ví dụ độc lập:

**Tên file:** `SinceDocDemo.java`

```java
/**
 * Demo documentation tag; this class deliberately uses only Java 11 APIs.
 *
 * @since 21
 */
public final class SinceDocDemo {
    /**
     * Returns a fixed greeting.
     *
     * @since 21
     */
    public static String sayHello() {
        return "Runs using Java 11 APIs";
    }

    public static void main(String[] args) {
        System.out.println(sayHello());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 SinceDocDemo.java
java SinceDocDemo
```

Stdout đã kiểm chứng:

```text
Runs using Java 11 APIs
```

Dù Javadoc comments chứa `@since 21`, chương trình vẫn compile bằng `--release 11` vì code chỉ cần Java 11 public API. Lý do: `@since 21` là **metadata tài liệu do tác giả khai báo**, không phải bộ luật ràng buộc `javac` trên method source của thư viện tùy ý.

**Không suy ra `@since 21` ở một thư viện bên thứ ba tự chứng minh binary target là Java 21**. Phiên bản class-file/API dependencies phải kiểm riêng. Và cũng đừng dùng Javadoc tag giả để hứa library hỗ trợ release mà chưa kiểm thử.

Nếu tạo docs bằng `javadoc`, tag `@since` có thể hiện trong generated HTML, nhưng `Class.getDeclaredMethod(...)` không tự cung cấp lịch sử `@since` từ comment.

## 12. `@since` và `@Deprecated(since=...)` khác nhau

Hai metadata trông giống nhau nhưng trả lời **hai câu hỏi khác nhau**.

```java
/**
 * This API was introduced in version 11.
 *
 * @since 11
 */
@Deprecated(since = "21", forRemoval = false)
public static void oldPath() {
    // Code của thư viện.
}
```

Đây là một **method declaration minh họa**, không phải full Java class chạy độc lập.

- **`@since 11`**: tác giả tài liệu nói API được **giới thiệu** trong release 11.
- **`@Deprecated(since = "21")`**: API **bị đánh dấu deprecated** kể từ release 21.
- **`forRemoval = false`**: API hiện **không được đánh dấu** dự kiến remove theo annotation này.
- **`Deprecated` không tự chứng minh method đã bị remove.**
- **`@since` không tự chứng minh method đã deprecated.**

Trong Javadoc, các phần `Deprecated`, `Since`, `API Note` và `@since` của member phải được đọc riêng. Một method có thể có `Since: 8` rồi `Deprecated, since: 17`: **không** được viết “method mới ở Java 17”.

### Vì sao đặc biệt quan trọng với module Java 11?

Một tutorial có thể mô tả method **được thêm ở Java 11** nhưng hiện đã có guidance thay thế; ngược lại một API rất cũ có thể vẫn hoàn toàn hợp lệ và đang được khuyến nghị. Với yêu cầu “chỉ kiến thức còn áp dụng”, phải:

1. Xác định API member.
2. Kiểm tra `Since`.
3. Kiểm tra deprecation/removal warning.
4. Đọc hiện hành `API Note/Implementation Note` và contract.
5. Chỉ giữ ví dụ còn được hỗ trợ, không tái sử dụng các lệnh legacy/incubator đã hết hiệu lực.

## 13. Một phương thức mới trên interface cũ: case `Stream.toList()`

`java.util.stream.Stream` là interface xuất hiện từ Java 8. Nhiều người nghĩ mọi method trong `Stream` cũng là API Java 8. Điều đó sai vì interface có thể được bổ sung **default methods** sau này.

```java
// Java 8+:
Stream.of("a", "b").collect(Collectors.toList());

// Java 16+:
Stream.of("a", "b").toList();
```

Cách đọc Javadoc:

1. Mở `Stream` ở Java 11: có `collect(...)`; **không** có `toList()`.
2. Mở `Stream` ở Java 16/26: có `toList()`.
3. Vào `toList()` Method Detail: **`Since: 16`**.
4. Kiểm tra contract: danh sách trả về **unmodifiable**.
5. Nếu source bắt buộc Java 11, không gọi method ấy.
6. Nếu di chuyển sang giải pháp dùng `Collectors.toList()`, kiểm tra semantics và mutability dự kiến thay vì mặc định hai kết quả giống tuyệt đối.

Một sự khác biệt có thể quan sát:

```java
// Java 16+:
List<String> items = Stream.of("a", "b").toList();
items.add("c"); // UnsupportedOperationException
```

Tương phản:

```java
// Java 11:
// API contract của Collectors.toList() không hứa implementation
// cụ thể, mutability, serializability hoặc thread-safety.
List<String> items =
        Stream.of("a", "b").collect(Collectors.toList());
```

Nếu cần chắc chắn một `ArrayList` có thể sửa trên Java 11, dùng:

```java
List<String> items = Stream.of("a", "b")
        .collect(Collectors.toCollection(ArrayList::new));
```

Đây là snippets, cần imports và ngữ cảnh sử dụng. **Khả năng biên dịch** và **behavioral equivalence** là hai vấn đề khác nhau.

## 14. Class mới, constructor mới, overload mới: phương pháp đối chiếu

### 14.1. Class mới: `HexFormat`

`java.util.HexFormat` được giới thiệu từ **Java 17**. Nếu code cần xử lý hex và dự án target Java 11, không thể chỉ import `HexFormat` vì trong Java 11 không có class public API này.

Một số code xử lý hex có thể sử dụng cách viết thay thế ở Java 11, nhưng phải kiểm tra performance, handling bytes, uppercase/lowercase, delimiter và error semantics. Không ghi rằng `HexFormat` là “Java 11 API” chỉ vì nó thuộc `java.util` vốn là package lâu đời.

### 14.2. Interface mới: `SequencedCollection`

`java.util.SequencedCollection` xuất hiện từ **Java 21**. Nó đưa vào hợp đồng collection có thứ tự truy cập đầu/cuối và reversed view. Điều này không biến `List` hoặc `Deque` thành class lần đầu xuất hiện ở Java 21.

Khi đọc một dự án dùng `list.getFirst()` hay `list.reversed()`, phải kiểm tra **method declaration chính xác trên API version**. Một `List` được khai báo trong Java 11 không đảm bảo có mọi tiện ích mới bổ sung vào `List` ở Java 21.

### 14.3. Overload mới

Nếu một class có `foo(String)` từ Java 8 và thêm `foo(String, Charset)` ở Java 11, thì:

- Code gọi overload một tham số có thể hỗ trợ Java 8 (nếu các phụ thuộc khác cho phép).
- Code gọi overload hai tham số cần Java 11.
- Tên `foo` không đủ để quyết định minimum Java version.

Đây là **ví dụ giả định** minh họa overload; không đại diện cho một class cụ thể của JDK. Trường hợp thật có nhiều overload như `Files.readString(Path)` và `Files.readString(Path, Charset)`, cả hai đều có `Since: 11`; phải đọc signature và `Since` ở từng overload.

## 15. API giống nhau về kết quả nhưng không cùng ngữ nghĩa

Không chỉ kiểm tra “method được thêm khi nào”. Khi nâng cấp hoặc thay API, kiểm tra hành vi.

### 15.1. `String.strip` vs `trim`

```java
String s = "\u2003hi\u2003";

System.out.println(s.strip().equals("hi")); // true
System.out.println(s.trim().equals("hi"));  // false
```

`strip` dựa trên Unicode white-space semantics (`Character.isWhitespace`), `trim` xử lý theo quy tắc lịch sử khác. `strip` mới ở Java 11, nhưng không có nghĩa `trim` “lỗi thời” trong mọi tình huống. Khi cần giữ nguyên một protocol definition dựa vào ASCII control chars, **thay `trim` bằng `strip` có thể thay đổi behavior**.

### 15.2. `String.lines` vs `split`

`String.lines()` được thêm ở Java 11 và được thiết kế để stream các dòng. Một cách làm cũ là `split(...)`, nhưng handling trailing empty fields/line terminators và mức tạo mảng khác. Không viết rằng chúng **luôn tương đương**; phải kiểm tra input có `\r\n`, `\n`, `\r` và dấu kết thúc.

### 15.3. `Path.of` vs `Paths.get`

`Path.of(String, String...)` có `Since: 11`; `Paths.get(...)` có từ Java 7. Javadoc `Paths` hiện có **API Note** khuyến nghị `Path.of`, nhưng không phải mọi use case/library code cần từ bỏ `Paths.get` bằng mọi giá.

Đặc biệt, `Path.of` dùng default filesystem. Một library cần hỗ trợ arbitrary filesystem providers nên cân nhắc `existingPath.resolve(...)` hoặc `FileSystem.getPath(...)` thay vì giả định default FS. “Tiện ích mới” không thay thế việc xác định filesystem semantics.

### 15.4. `Files.readString` vs streaming I/O

`Files.readString` mới ở Java 11, phù hợp file text vừa/nhỏ. Nó không có nghĩa `BufferedReader`, `Files.lines` hay streaming APIs trở nên obsolete. Với file lớn, streaming giúp kiểm soát memory và xử lý từng dòng; `readString` đưa nội dung thành một `String`.

### 15.5. `Optional.isEmpty` vs `isPresent`

`Optional.isEmpty` từ Java 11 cho cách đọc trực tiếp điều kiện không có value. `!optional.isPresent()` vẫn biểu diễn cùng boolean condition nhưng API cũ hơn. Quyết định viết code dựa trên clarity và target release, không gọi cái cũ “sai” chỉ vì mới có cú pháp thuận tiện.

## 16. `Since` ở JDK hiện hành: đừng đồng nhất “được bổ sung” với “được cải tiến”

Ví dụ, `Files.readString(Path)` có `Since: 11` ở Javadoc hiện hành. Nhưng:

- JVM implementation có thể được tối ưu I/O, memory hoặc exception handling trong các JDK updates;
- bug fixes có thể đổi một tình huống edge case;
- security policy/module access và locale/Unicode data có thể tác động đến chương trình;
- một overload khác có thể được bổ sung sau này.

**`Since` không phải changelog đầy đủ**. Khi cần xác nhận hành vi đã thay đổi giữa hai phiên bản, dùng release notes, CSR/JEP nếu liên quan, JDK issue tracker và tests cùng platform versions.

Một câu chính xác hơn:

> “`String.strip()` được giới thiệu trong Java 11; API đó vẫn có mặt trong JDK hiện hành, nhưng cần tham khảo Javadoc phiên bản đang chạy để xem contract và các lưu ý cụ thể.”

Tránh:

> “`String` mới ở Java 11”, hoặc “`String.strip` mới ở JDK 27 chỉ vì trang Javadoc JDK 27 có method đó”.

## 17. Hạn chế của `javap`, reflection, `jdeps` và IDE khi kiểm chứng Since

### 17.1. `javap -verbose`

`javap` xem bytecode/class-file structure, có thể in:

```text
major version: 55
```

Nó xác nhận format của **class file**, không tự biết mốc `@since` của method trong Javadoc. Với class file tạo bằng `-source 11 -target 11` trên JDK mới, metadata major 55 vẫn có thể chứa reference đến `String.indent` mà Java 11 runtime không cung cấp.

### 17.2. Reflection

`String.class.getMethods()` trên **JDK 27** liệt kê methods runtime JDK 27, không cho biết tất cả methods ấy đã có từ JDK 11. Reflection không đọc Javadoc `@since`, vì nó không phải runtime annotation.

Một ví dụ quan sát:

```java
for (java.lang.reflect.Method m :
        String.class.getDeclaredMethods()) {
    if ("indent".equals(m.getName())) {
        System.out.println(m);
    }
}
```

Chương trình này có thể in method trên JDK mới. **Không dùng kết quả ấy làm bằng chứng nó đã có từ Java 11.**

### 17.3. `jdeps`

`jdeps` rất hữu ích phân tích module/package/class dependencies, kể cả phát hiện JDK internal API usage bằng các tùy chọn phù hợp. Nhưng **việc không có lỗi từ `jdeps` không tự chứng minh every referenced method existed in Java 11**. Method-level compatibility của JDK APIs nên được xác nhận bằng `--release 11` và tests.

### 17.4. `jdeprscan`

`jdeprscan` hỗ trợ xem những uses of deprecated Java SE APIs. Nhưng **deprecated since** khác **introduced since**; nó không phải công cụ lấy minimum Java version của toàn bộ API usage.

### 17.5. IDE auto-completion

IDE đang dùng SDK **JDK 27** có thể gợi ý `Stream.toList()` dù project runtime policy là Java 11 nếu project language level/API baseline chưa khóa đúng. Không coi auto-completion là nguồn lịch sử API.

Khuyến nghị thiết lập project SDK/toolchain và compile task **thật sự dùng `--release 11`** khi Java 11 là baseline. Kiểm tra build logs và CI, không chỉ biểu tượng JDK trong IDE.

## 18. Một quy trình kiểm chứng version cho pull request

Giả sử PR thêm dòng:

```java
return stream.toList();
```

Trong khi project vẫn yêu cầu Java 11.

**Quy trình:**

1. **Đọc source:** tìm fully qualified type `java.util.stream.Stream`, method `toList()`, parameter list trống.
2. **Tra Javadoc target 11:** method **không** có.
3. **Tra Javadoc mới:** `toList()` có `Since: 16`.
4. **Kiểm tra contract:** trả unmodifiable list, không phải chỉ “collect nhanh hơn”.
5. **Chạy `javac --release 11` hoặc CI build:** báo lỗi không tìm thấy method.
6. **Chọn giải pháp:** nếu cần giữ Java 11, dùng collector có contract phù hợp hoặc cơ chế khác; nếu nâng baseline, cập nhật runtime matrix và deployment.
7. **Viết test semantics:** mutability, null elements, encounter order, performance nếu liên quan.
8. **Đưa quyết định vào PR description:** “Giữ baseline Java 11, thay `Stream.toList()` (Since 16) bằng phương án tương thích và bổ sung test.”
9. **Kiểm tra dependency graph:** library ngoài có thể target/newer APIs, dù source project của bạn pass.

Không cần “đổi toàn bộ Streams thành arrays” để xử lý một method mới; ta chỉ cần chọn một thao tác **cùng contract mong muốn** được hỗ trợ trong target release.

## 19. Kiểm tra ở cấp dự án: phần API check chưa bao phủ

### 19.1. Libraries bên ngoài

`javac --release 11` khóa **public JDK API surface** cho Java 11, nhưng không tự bảo đảm thư viện third-party không gọi Java 17 APIs ở runtime.

Ví dụ:

- Application source chỉ dùng Java 11 APIs.
- Dependency JAR biên dịch class-file major 55 nhưng tác giả dùng `-source/-target` không khóa APIs.
- Dependency method gọi `String.formatted` chỉ có từ Java 15.
- Application compile xong, chạy trên Java 11 tới code của dependency có thể ném `NoSuchMethodError`.

Cần kết hợp:

- dependency version matrix và minimum required Java;
- compile/release compatibility tests;
- test integration trên oldest supported JDK;
- static/binary linkage analysis khi cần.

### 19.2. Multi-release JAR

Một multi-release JAR có thể chứa implementation cho Java 11 và implementation khác cho JDK mới. Một dependency “support Java 11” có thể có nhiều class versions trong archive. Khi phân tích, phải xét **thực tế class variant nào được JVM chọn**.

Đừng đọc một file trong `META-INF/versions/21` rồi suy ra code đó chạy trên Java 11. Ngược lại, đừng chỉ kiểm tra base variant rồi bỏ qua code chạy trên JDK mới.

### 19.3. Reflection, method handles và dynamic invocation

`--release 11` chỉ kiểm tra những references mà compiler thấy. Code như:

```java
Class.forName("java.util.HexFormat");
```

chứa một **chuỗi tên class**, không phải compile-time reference tới `HexFormat.class`. Nó có thể **biên dịch bằng `--release 11`**, rồi khi chạy trên Java 11 ném `ClassNotFoundException` do class không tồn tại.

Tương tự, reflective `getMethod("toList")` hoặc method handles được resolve động có thể phụ thuộc APIs mới hơn mà compile không bắt được. Phải test runtime paths và có fallback hợp lệ nếu chủ đích hỗ trợ nhiều JDK versions.

### 19.4. Native, agents, JNI, serialization, services

Ngay cả khi JDK public API surface phù hợp, ứng dụng còn có:

- JNI/native library ABI và OS compatibility;
- Java agents/instrumentation;
- service provider loading;
- serialized data/schema compatibility;
- bytecode transformation và classfile version;
- behavior differences khi đổi JDK.

Vì vậy, `Since` cùng `--release` là hai lớp kiểm chứng rất quan trọng nhưng **không phải toàn bộ kế hoạch migration**.

## 20. Ghi chú đặc biệt: Java 11 là “origin” hay “minimum target”?

Cụm “API Java 11” có thể được sử dụng theo ba nghĩa, cần nêu rõ khi viết tài liệu:

| Cụm nói | Ý nghĩa đúng cần nói rõ |
| --- | --- |
| **“Mới ở Java 11”** | Declaration có `Since: 11`, hoặc feature được tiêu chuẩn hóa ở Java 11 |
| **“Có thể dùng trên Java 11”** | Declaration có sẵn trong API target Java 11; `Since` có thể là 1.8, 9, 10 hoặc 11 |
| **“Đang dùng JDK 11”** | JVM runtime hiện chạy JDK 11, không nói feature được giới thiệu khi nào |

Ví dụ:

- `Optional.isPresent()`: có thể dùng trên Java 11, **không phải mới ở Java 11**.
- `Optional.isEmpty()`: có thể dùng trên Java 11 **và** mới ở Java 11.
- `Stream.toList()`: có thể chạy trên JDK 17/21/27 nhưng **không thể dùng với API baseline Java 11**.
- `String.strip()`: có `Since: 11`; vẫn hoàn toàn hữu ích ở JDK 27.
- `Path.of`: tiện ích Java 11 trên interface Java 7.
- `HttpClient` chuẩn `java.net.http`: được chuẩn hóa ở Java 11; trước đó có giai đoạn incubator nhưng **không nên ghi stable API xuất hiện Java 9**.

**Đừng lấy version của JDK đang mở Javadoc làm version phát minh API.** Javadoc JDK 27 có thể chứa APIs `Since: 1.8`, `Since: 11`, `Since: 16` và `Since: 27` trên cùng một package.

## 21. Các tình huống dễ gây nhầm

### Tình huống A — Đọc `String` trên trang Javadoc JDK 26

Có methods cũ và mới cùng trang. Cách đúng là tìm **mỗi method detail**, đọc `Since` của method và xem lại Java 11 docs nếu target Java 11. Không nói “tất cả là Java 26 APIs”.

### Tình huống B — `Files` có `Since: 1.7` nhưng `readString` có `Since: 11`

Class ra đời ở Java 7, nhưng **member** thêm ở Java 11. Code dùng `Files.readString` cần target ít nhất 11, dù cả hai thuộc `java.nio.file`.

### Tình huống C — Một method không in `Since` ở detail

Không tự gán “nó có từ release 1.0” hoặc “nó có cùng Since với class”. Kiểm tra Javadoc cũ/nguồn định nghĩa/inherited method hoặc API index; **thiếu tag là thiếu một metadata assertion rõ ràng**, không phải phép suy luận thời gian tuyệt đối.

### Tình huống D — Một method được đánh dấu `Deprecated(since="21")`

Nó bắt đầu bị khuyến cáo hạn chế ở Java 21; có thể đã tồn tại từ Java 8. Đọc thêm `@since`, replacement guidance và `forRemoval`.

### Tình huống E — Class mới tồn tại ở JDK 27 nhưng import compile `--release 11` lỗi

Class được giới thiệu sau Java 11 (hoặc package/module không có trong documented APIs Java 11). Chọn cách khác tương thích hoặc nâng baseline. Không thêm `--add-exports` để “cứu” một public API **chưa tồn tại**.

### Tình huống F — Source code target Java 11 nhưng runtime JDK 27

Nếu build dùng `--release 11` và không có dynamic/libraries incompatible, Java 11 API references có thể chạy tốt trên JDK 27. Ngược lại, việc runtime mới không thay đổi thông tin origin: `String.strip` vẫn `Since: 11`.

### Tình huống G — Java API được backport bằng thư viện

Một backport library có thể cung cấp **tính năng tương tự** một API JDK mới dưới package/class khác. Điều đó **không biến public JDK API gốc** thành member của Java 11. Cần mô tả cụ thể dependency và semantic differences thay vì thay nhãn `Since`.

### Tình huống H — APIs chuyển từ incubator sang standard

Phải xác định exact **module/package/type** trong stable JDK API. Một prototype ở JDK trước có thể có namespace hoặc contract khác hẳn. Không lấy một JEP prototype year làm `Since` của final API.

## 22. Checklist nhanh cho reviewer

Dùng checklist này khi bài học hoặc PR nhắc một API “được thêm ở Java 11”:

- [ ] Xác định đúng **module, package, class/interface, method/constructor, overload**.
- [ ] Đọc `Since` của **member**, không chỉ `Since` của class.
- [ ] Đối chiếu Javadoc **Java 11** với Javadoc **JDK hiện hành**.
- [ ] Kiểm tra API có **Deprecated/forRemoval** hoặc notes mới không.
- [ ] Phân biệt Java 11 **new API** với API cũ **cũng có thể dùng trên Java 11**.
- [ ] Phân biệt new method với behavioral/performance changes của method cũ.
- [ ] Không suy ra JDK API availability từ class-file major 55.
- [ ] Biên dịch bằng **`javac --release 11`** nếu baseline là Java 11.
- [ ] Không chỉ dựa vào `-source 11 -target 11` trên JDK mới.
- [ ] Chạy ít nhất test quan trọng trên oldest supported runtime.
- [ ] Kiểm tra direct/indirect third-party dependencies và reflection.
- [ ] Nếu phải dùng API mới, công khai quyết định **nâng minimum JDK**.
- [ ] Kiểm tra compatibility không phá semantics (null, mutability, charset, I/O, exceptions).
- [ ] Ghi link Oracle Javadoc **đúng version và member** cho kết luận.
- [ ] Không gắn nhãn “legacy” cho API cũ chỉ vì có API mới hơn nếu nó vẫn hợp lệ.

## 23. Câu hỏi tự luyện tập có đáp án

**1. `Since: 11` ở `String.strip()` nghĩa là gì?**

`strip()` được đưa vào public Java API từ Java 11. Class `String` đã có trước đó; ở JDK mới method vẫn có thể được hỗ trợ.

**2. Nếu class `Files` có `Since: 1.7`, `Files.readString` có thể dùng trên Java 7 không?**

Không. `readString` là member được bổ sung ở Java 11, phải đọc `Since` của method.

**3. `Path.of(...)` mới từ Java nào? `Paths.get(...)` có phải API mới cùng đợt không?**

`Path.of` mới ở Java 11; `Paths.get` đã có từ Java 7. Javadoc hiện hành có hướng dẫn ưu tiên `Path.of` trong ngữ cảnh phù hợp, nhưng `Paths.get` không tự động thành deprecated.

**4. `Optional.isPresent()` và `Optional.isEmpty()` có cùng Since không?**

Không. `Optional` và `isPresent` có từ Java 8, `isEmpty()` được bổ sung ở Java 11.

**5. `Stream.toList()` có từ Java nào?**

Java 16. Interface `Stream` có từ Java 8.

**6. Nếu dùng `Stream.toList()`, đổi thành `Collectors.toList()` có chắc giữ mutability contract không?**

Không. `Stream.toList()` trả unmodifiable list; `Collectors.toList()` không cam kết cụ thể mutability. Chọn collector theo contract.

**7. `String.indent(int)` được thêm ở Java nào?**

Java 12. `String.lines()` là Java 11 nhưng không làm `indent` cũng thuộc Java 11.

**8. `String.formatted(...)` có thể gọi khi build `--release 11` không?**

Không. Method này xuất hiện ở Java 15. Có thể dùng `String.format(...)` khi semantics phù hợp.

**9. `java.util.HexFormat` có từ Java 11 không?**

Không. Class thuộc Java 17.

**10. `java.util.SequencedCollection` có từ Java nào?**

Java 21; không thuộc Java 11 API baseline.

**11. `@since` là annotation runtime để reflection đọc phải không?**

Không. Đó là Javadoc documentation tag, không phải metadata runtime annotation.

**12. `@Deprecated(since="21")` nghĩa method được giới thiệu ở Java 21?**

Không. Nó nói được đánh dấu deprecated từ release 21, không phải original `@since`.

**13. Vì sao `javap` hiện `major version: 55` chưa đủ bảo đảm API Java 11?**

Vì major 55 chỉ biểu thị định dạng bytecode Java 11; class file có thể chứa references tới methods chỉ tồn tại ở JDK mới, nếu compile không khóa API platform.

**14. Lệnh nào ưu tiên để kiểm chứng public Java 11 APIs bằng JDK mới?**

`javac --release 11 SourceFile.java`.

**15. `-source 11 -target 11` có tự hạn chế JDK APIs theo Java 11 không?**

Không. Nếu compiler vẫn nhìn public APIs của host JDK mới, code có thể reference APIs thêm sau Java 11. Cần `--release`.

**16. Với demo thứ hai, `--release 11` báo lỗi ở những methods nào?**

`String.indent(int)`, `Stream.toList()` và `String.formatted(...)`. Chúng lần lượt có `Since 12`, `16`, `15`.

**17. Cùng demo compile bằng `-source 11 -target 11` trên JDK 24 tạo major mấy?**

Major **55**. Nhưng class file version đúng không chứng minh Java 11 runtime có những methods được tham chiếu.

**18. Nếu class file major 55 mà gọi `String.indent` trên runtime Java 11, loại lỗi nào có thể xảy ra?**

`NoSuchMethodError` khi JVM cần resolve method ấy. Đây khác `UnsupportedClassVersionError` của class-file format mới hơn runtime.

**19. Javadoc JDK 27 vẫn liệt kê `String.strip()`, vậy nó được giới thiệu năm 2026?**

Không. `Since: 11` xác nhận API được giới thiệu ở Java 11; trang JDK hiện hành chỉ là tài liệu phiên bản đang được hỗ trợ.

**20. Khi cần biết method có được khuyến nghị ở hiện tại không, chỉ đọc Since đủ không?**

Không. Kiểm tra thêm deprecation, forRemoval, API notes, security/correctness guidance, release notes và contract.

**21. Nếu method không có `Since` rõ ràng, nên làm gì?**

So Javadoc lịch sử, nơi khai báo method/inherited/default implementation và kiểm tra API release bằng compiler. Không tự gán năm.

**22. Java 11 có `java.net.http.HttpClient` standard API không?**

Có. Module `java.net.http` được chuẩn hóa ở Java 11. Lịch sử HTTP client incubator trước đó không có nghĩa stable API `java.net.http` được công bố từ Java 9.

**23. Một project dùng `javac --release 11` và có dependency mới thì đã chắc chắn chạy trên Java 11 chưa?**

Chưa. Compiler kiểm soát public platform APIs cho source được compile, không bảo đảm mọi thư viện/reflective call/native component đều tương thích runtime target.

**24. Có thể dùng `String.class.getMethods()` trên JDK 27 để xác định API nào “mới ở Java 11” không?**

Không. Reflection hiển thị API hiện có của runtime, không xuất lịch sử `@since`.

**25. Mục tiêu của việc đối chiếu `Since` là gì?**

Ghi chính xác **nguồn gốc public API**, phân biệt class cũ với member mới và API mới hơn baseline, rồi kết hợp compiler/runtime tests để bảo đảm tính tương thích và tránh truyền đạt lịch sử Java sai.

## 24. Nguồn chính thức để tự đối chiếu

**Javadoc baseline Java 11**

- [Oracle Java SE 11 — String](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): `strip`, `isBlank`, `lines`, `repeat` và các APIs cũ.
- [Oracle Java SE 11 — Optional](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html): `isEmpty()` có `Since: 11`.
- [Oracle Java SE 11 — Predicate](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/function/Predicate.html): `not(Predicate)` có `Since: 11`.
- [Oracle Java SE 11 — Path](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Path.html): `of(String, String...)` và `of(URI)`.
- [Oracle Java SE 11 — Paths](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Paths.html): API đã có từ Java 7, `Paths.get` vẫn tồn tại.
- [Oracle Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `readString` và `writeString`.
- [Oracle Java SE 11 — Stream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/stream/Stream.html): không có `Stream.toList()`.
- [Oracle Java SE 11 — Collection](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Collection.html): `toArray(IntFunction)` có `Since: 11`.
- [Oracle Java SE 11 — java.net.http module](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/module-summary.html): standard HTTP Client/WebSocket APIs có `Since: 11`.

**Javadoc các phiên bản mới hơn**

- [Oracle Java SE 12 — String](https://docs.oracle.com/en/java/javase/12/docs/api/java.base/java/lang/String.html): `indent(int)` và `transform(Function)` có `Since: 12`.
- [Oracle Java SE 12 — Files](https://docs.oracle.com/en/java/javase/12/docs/api/java.base/java/nio/file/Files.html): `mismatch(Path, Path)` có `Since: 12`.
- [Oracle Java SE 15 — String](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html): `formatted(Object...)` có `Since: 15`.
- [Oracle Java SE 16 — Stream](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html): `toList()` có `Since: 16`.
- [Oracle Java SE 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): class có `Since: 17`.
- [Oracle Java SE 21 — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): interface có `Since: 21`.
- [Oracle Java SE 26 — Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): tài liệu hiện hành vẫn giữ `Since: 16` cho `toList()`.
- [Oracle Java SE 26 — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): một trang class chứa các methods `Since 11/12/15` khác nhau.

**Công cụ để kiểm chứng**

- [Oracle JDK 26 — javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--release`, `--source`, `--target` và compiling for earlier releases.
- [Oracle Java SE 11 — javap tool](https://docs.oracle.com/en/java/javase/11/tools/javap.html): inspect class-file major version/bytecode, nhưng không thay thế `Since`.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): cơ sở cho `javac --release`.
- [OpenJDK JEP 321 — HTTP Client](https://openjdk.org/jeps/321): chuẩn hóa HTTP Client trong Java 11.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): một ví dụ về công cụ/tiện ích ở release trước Java 11 để tránh nhầm “mọi collections convenience API đều mới ở Java 11”.

## 25. Tổng kết

**Nguyên tắc thực hành:**

1. Đọc **`Since` ở đúng API element** — class, method, constructor hay overload — không gán version của class cho mọi method.
2. Phân biệt **API introduction**, **implementation improvements**, **deprecation**, **language features** và **runtime/JVM features**.
3. Muốn dạy “Java 11 có gì mới”, xác định `Since: 11` ở member hoặc nguồn release chính thức; API ra đời trước nhưng vẫn dùng trên Java 11 phải ghi đúng là **đã tồn tại**.
4. Muốn biết API **đang được hỗ trợ**, xem Javadoc phiên bản hiện hành cùng notes/deprecation.
5. Muốn bảo đảm source dùng được với Java 11, compile bằng **`javac --release 11`**, không chỉ `-source/-target` và `javap major 55`.
6. Muốn bảo đảm deploy chạy được trên Java 11, còn phải test runtime thực và kiểm tra dependencies/dynamic calls.
7. **`Since: 11` không phải dấu hiệu obsolete**: một API có nguồn gốc ở Java 11 vẫn có thể là lựa chọn hợp lệ, an toàn, được duy trì ở JDK hiện hành.

Câu hỏi cốt lõi khi review là: **“Declaration nào, được thêm ở release nào, có contract gì, và build/runtime mục tiêu có thực sự hỗ trợ nó không?”**
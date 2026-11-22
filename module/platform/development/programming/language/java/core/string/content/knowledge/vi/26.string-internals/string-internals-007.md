# Chi tiết substring, intern và tối ưu String có thể khác giữa các phiên bản JDK

## 1. Phân biệt hợp đồng API và chi tiết cài đặt

`String` là một lớp cốt lõi của Java: bất biến (immutable), biểu diễn một dãy đơn vị mã UTF-16 và cung cấp các thao tác như `substring()`, `equals()` và `intern()`. Tuy vậy, cách JVM bố trí bộ nhớ, tái sử dụng vùng dữ liệu ký tự, lưu bảng chuỗi intern hay loại bỏ bản sao trùng lặp đã thay đổi nhiều lần qua các phiên bản JDK.

Khi học hoặc tối ưu hóa `String`, phải tách **hai tầng**:

- **Hợp đồng ngôn ngữ/API:** `substring(begin, end)` lấy đúng đoạn ký tự; `equals` so sánh nội dung; `intern` trả về đại diện chuẩn (canonical) của nội dung trong pool. Chương trình phải dựa vào các quy tắc này.
- **Cơ chế cài đặt:** `String` dùng `char[]` hay `byte[]`, một substring có chia sẻ backing array không, pool lưu ở vùng bộ nhớ nào, JIT/GC có loại bỏ bản sao hay không. Đây là các lựa chọn của phiên bản JDK, nhà cung cấp JVM và cấu hình runtime; không nên coi là API bất biến.

Một tối ưu hợp lý trên JDK cũ có thể đã lỗi thời trên JDK mới; ngược lại, kết quả đúng của chương trình không được phụ thuộc vào đoán định về backing array, kích thước đối tượng hoặc số lần cấp phát nội bộ.

| Vấn đề | Bảo đảm ổn định để viết chương trình | Chi tiết phụ thuộc JDK/JVM |
| --- | --- | --- |
| `substring` | Trả về nội dung từ chỉ số đầu (bao gồm) tới cuối (không bao gồm) | Có copy dữ liệu hay chia sẻ vùng lưu trữ; chi phí cấp phát |
| `String.intern` | Với chuỗi bằng nhau theo `equals`, kết quả `intern()` là cùng tham chiếu chuẩn | Cấu trúc bảng pool, vị trí lưu trữ, GC, thời gian tìm kiếm |
| `String` immutable | Nội dung chuỗi không thể bị sửa sau khi tạo | Các đối tượng có dùng chung mảng dữ liệu nội bộ không |
| `length` và `charAt` | Hoạt động theo đơn vị mã UTF-16 `char` | Chuỗi có lưu bằng mảng byte compact hay mảng char |
| Tối ưu String | Nội dung và hành vi API không đổi | Deduplication, compact storage, JIT, GC, chiến lược nối chuỗi |

## 2. substring: cùng một kết quả, nhiều chiến lược lưu trữ

Hai overload thường dùng:

```java
String substring(int beginIndex)
String substring(int beginIndex, int endIndex)
```

`beginIndex` được tính vào kết quả; `endIndex` **không** được tính vào. Các chỉ số được đo bằng đơn vị `char` UTF-16, không phải Unicode code point.

```java
String source = "abcdef";
String part = source.substring(2, 5);

System.out.println(part);                    // cde
System.out.println(part.length());           // 3
System.out.println(part.equals("cde"));      // true
```

Phạm vi bất hợp lệ như `beginIndex < 0`, `endIndex > source.length()` hoặc `beginIndex > endIndex` gây `IndexOutOfBoundsException`. API quy định **nội dung đoạn chuỗi**; nó không hứa mỗi lần gọi phải tạo một đối tượng `String` và mảng backing độc lập.

### Lịch sử: chia sẻ mảng ở JDK cũ

Trong các cài đặt OpenJDK/HotSpot đời cũ **trước JDK 7u6**, `String` từng sử dụng một mảng `char[]` cùng thông tin `offset`/`count`. Một `substring` nhỏ có thể tạo đối tượng String mới nhưng **chia sẻ cùng mảng ký tự lớn** với chuỗi gốc. Lợi thế là tránh copy dữ liệu; đánh đổi là nguy cơ giữ sống mảng lớn chỉ vì còn một substring ngắn.

Ví dụ tình huống lịch sử:

```text
Chuỗi gốc rất dài:     [........ hàng triệu ký tự ........]
                                |
Substring chỉ lấy:             "id"

Cài đặt chia sẻ mảng đời cũ:
" id " nhỏ vẫn tham chiếu backing char[] lớn.
Khi chuỗi gốc không còn dùng, backing array lớn có thể vẫn
chưa được giải phóng vì substring còn sống.
```

Điểm dễ nhầm: đây thường gọi là **khả năng giữ bộ nhớ ngoài ý muốn (memory retention)**, không có nghĩa `String` bị thay đổi nội dung hay JVM vi phạm tính immutable.

Từ **JDK 7u6**, cách cài đặt phổ biến đã thay đổi: substring có thể tạo vùng lưu trữ ký tự phù hợp với đoạn cần giữ, thay cho việc luôn chia sẻ cả mảng lớn theo `offset`/`count`. Vì thế, mẹo cũ `new String(large.substring(...))` để buộc copy/thoát tham chiếu tới backing array **không nên được áp dụng máy móc trên JDK hiện đại**. Constructor `String(String original)` hiện không bảo đảm một backing copy mới tách biệt; String bất biến cho phép chia sẻ dữ liệu khi có lợi.

**Kết luận về thiết kế:** dùng `substring` để lấy đoạn theo nhu cầu. Khi thực sự lo về memory retention hoặc throughput, kiểm tra **đúng JDK/JVM đang chạy** bằng heap profiler và benchmark thay vì áp dụng quy tắc “substring luôn O(1)” hay “substring luôn copy” cho mọi phiên bản. Với tác vụ cắt rất nhiều chuỗi, chi phí cấp phát vẫn cần được đo.

### UTF-16 và nguy cơ cắt giữa surrogate pair

Cho dù cài đặt bên trong dùng compact bytes, API `substring` vẫn dùng **chỉ số UTF-16**. Ví dụ emoji `🚀` là một Unicode code point nhưng cần hai `char`:

```java
String value = "A🚀B";
System.out.println(value.length());                    // 4
System.out.println(value.codePointCount(0, value.length())); // 3
System.out.println(value.substring(1, 3));             // 🚀
```

Cắt `substring(1, 2)` sẽ chỉ lấy một nửa cặp surrogate; giá trị Java String vẫn có thể chứa đơn vị mã lẻ, nhưng có thể không hiển thị như ký tự mong muốn. Khi xử lý theo code point, tính chỉ số bằng `offsetByCodePoints` hoặc xử lý bằng `codePoints()`; đừng nhầm một `char` là một ký tự người dùng nhìn thấy.

## 3. intern(): hợp đồng ổn định, nơi giữ pool thay đổi

`String.intern()` trả một đối tượng canonical theo nội dung; với hai String `a.equals(b)` là `true`, `a.intern() == b.intern()` cũng là `true`. Literal và biểu thức String hằng lúc biên dịch được intern. Cách JVM lưu và quản lý các đối tượng canonical có thể đổi mà vẫn phải giữ hợp đồng đó.

```java
String literal = "java";
String created = new String("java");
System.out.println(created == literal);          // false
System.out.println(created.equals(literal));      // true
System.out.println(created.intern() == literal);  // true
```

Trong lịch sử **HotSpot**, vùng lưu String interned từng gắn với **PermGen** trên JDK 6 trở về trước. **Từ JDK 7**, các đối tượng String được intern nằm trên **Java heap thông thường**; JDK 8 loại bỏ PermGen và dùng **Metaspace** cho metadata, chứ không chuyển các `String` ứng dụng vào Metaspace. Các bản JDK/GC khác nhau có thể đổi cấu trúc bảng tra pool, thời gian sống hoặc chính sách thu gom.

Điều đó **không** có nghĩa intern miễn phí hay các đối tượng được intern sẽ sống mãi. Với tập giá trị ít lặp, như UUID, session ID hay URL ngẫu nhiên, đưa mọi đầu vào vào pool có thể làm tăng chi phí quản lý. Hãy kiểm tra độ trùng, vòng đời dữ liệu và profile heap trước khi dùng làm tối ưu.

Bài **Constant pool và vai trò của Constable/ConstantDesc** giải thích chi tiết khác biệt giữa String pool, constant pool trong class file và API mô tả hằng. Phần này tập trung vào **sự dịch chuyển cài đặt và hệ quả khi nâng JDK**.

## 4. String layout thay đổi qua các đời JDK

| Giai đoạn triển khai OpenJDK/HotSpot | Cách lưu nội dung điển hình | Hệ quả cần kiểm tra khi nâng cấp |
| --- | --- | --- |
| Nhiều bản trước Java 9 | `char[]` theo đơn vị UTF-16 | Không mặc định áp dụng footprint của JDK hiện đại |
| Java 9+ có Compact Strings (JEP 254) | `byte[]` với dạng LATIN1 hoặc UTF16 | Chuỗi có toàn code unit thuộc U+0000–U+00FF có thể tiết kiệm byte dữ liệu |

Ví dụ `"Xin chào"` gồm ký tự `à` thuộc Latin-1, nên **có thể** đủ điều kiện compact dù là tiếng Việt. Một ký tự ngoài U+00FF làm cả String dùng dạng UTF16 trong chiến lược này. Tuy nhiên `length()` vẫn đếm UTF-16 code units, còn `getBytes(StandardCharsets.UTF_8)` vẫn cho byte UTF-8 của dữ liệu trao đổi.

Đây là chuyện triển khai, không phải yêu cầu Java SE cho mọi JVM. Không truy cập trường `value`/`coder` bằng reflection để suy đoán tính đúng của ứng dụng. Nếu cần phân tích cụ thể cách chọn coder, tác động của `-XX:-CompactStrings` và chi phí bộ nhớ, xem bài **Compact Strings** và bài **Chi phí đối tượng, mảng lưu dữ liệu và chuỗi tạm**.

## 5. String Deduplication: chia sẻ dữ liệu, không trộn đối tượng

**JEP 192 — String Deduplication in G1**, có từ JDK 8u20 ở HotSpot với GC G1, nhằm giảm bộ nhớ khi nhiều đối tượng String khác nhau chứa cùng nội dung. Dưới điều kiện thích hợp, GC có thể giúp các String **chia sẻ cùng vùng dữ liệu backing** mà vẫn giữ **hai đối tượng `String` riêng**.

```text
Đối tượng String A ----\
                        > dữ liệu "AB" được chia sẻ (khi GC dedup)
Đối tượng String B ----/

A và B vẫn là hai tham chiếu đối tượng khác nhau.
```

Đây **không** phải `intern()`:

| Cơ chế | Chuẩn hóa chính đối tượng String? | Mục đích chính | Điều Java code quan sát được |
| --- | --- | --- | --- |
| `intern()` | Có: trả về một đối tượng canonical cho nội dung | Chuẩn hóa identity khi gọi rõ ràng | Hai kết quả `intern` của chuỗi bằng nhau so sánh `==` ra `true` |
| String Deduplication của GC | Không: có thể chia sẻ **mảng nội dung** nhưng giữ các String riêng | Giảm số vùng dữ liệu trùng lặp | `equals` vẫn đúng; `==` giữa hai đối tượng riêng vẫn `false` |

Trong HotSpot/JDK có hỗ trợ, có thể thử tùy chọn sau tại **môi trường đo đạc**:

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication YourApp
```

Hiệu quả phụ thuộc số lượng nội dung lặp lại, vòng đời đối tượng, GC, áp lực bộ nhớ và thời gian xử lý. Không có bảo đảm rằng một String cụ thể chắc chắn được dedup ngay hoặc rằng ứng dụng luôn nhanh hơn khi bật tùy chọn. Một số cờ và GC được hỗ trợ có thể thay đổi theo JDK; hãy kiểm tra tài liệu `java`/`-XX` của phiên bản runtime đích trước khi dùng trong môi trường thật.

**Không dùng `a == b` để đo deduplication.** Trường hợp hai `String` được tạo riêng, identity vẫn khác nhau kể cả khi GC đã chia sẻ backing data. Kiểm tra bằng chỉ số heap/GC hoặc profiler, không dựa vào Java reference equality.

## 6. Những tối ưu khác cũng phụ thuộc phiên bản JVM

Ngoài `substring`, `intern`, compact storage và deduplication, hành vi cấp phát/hiệu năng còn chịu ảnh hưởng của:

- **JIT và escape analysis:** trình biên dịch runtime có thể thay đổi, tối ưu hoặc loại bớt các cấp phát không quan sát được, nhưng không bảo đảm mọi lời gọi `new String` hay phép nối đều được loại bỏ.
- **Ghép chuỗi bằng `+`:** bộ biên dịch/JVM có thể dùng chiến lược khác nhau; từ Java 9, JEP 280 đưa cơ chế dựa trên `invokedynamic` cho bytecode nối chuỗi của `javac`. Không suy ra mã nguồn `a + b` luôn có cùng số `StringBuilder` hay số cấp phát trên mọi JDK.
- **GC và kích thước heap:** thuật toán quản lý/di chuyển đối tượng, kiểu collector và hành vi thu hồi tạo ra thời gian chạy/footprint khác nhau ngay cả khi source code giống hệt.
- **Phiên bản Unicode và quy tắc xử lý chữ:** việc nâng JDK có thể cập nhật dữ liệu Unicode trong các API liên quan; nếu logic phụ thuộc thuộc tính ký tự hay quy tắc case mapping, kiểm thử lại với bộ dữ liệu thực.

Từng thay đổi có thể tối ưu nhiều workload nhưng không có “một cờ tốt nhất” áp dụng mọi ứng dụng. Tránh đánh giá chỉ từ một lần chạy trên máy phát triển.

## 7. Ví dụ Java 17+ có kết quả ổn định giữa các cài đặt

Lưu vào tệp `StringVersionDemo.java`:

```java
public class StringVersionDemo {

    public static void main(String[] args) {
        String parent = "abcdef";
        String piece = parent.substring(2, 5);

        System.out.println("substring = " + piece);
        System.out.println("substring length = " + piece.length());
        System.out.println("substring content = " + piece.equals("cde"));

        String literal = "java";
        String created = new String("java");
        System.out.println("new equals literal = " + created.equals(literal));
        System.out.println("new == literal = " + (created == literal));
        System.out.println("intern == literal = " + (created.intern() == literal));

        String folded = "ja" + "va";
        System.out.println("constant == literal = " + (folded == literal));

        String runtime = new StringBuilder()
                .append("ja")
                .append("va")
                .toString();
        System.out.println("runtime equals literal = " + runtime.equals(literal));
        System.out.println("runtime intern == literal = " + (runtime.intern() == literal));

        String first = new String(new char[] {'A', 'B'});
        String second = new String(new char[] {'A', 'B'});
        System.out.println("equal objects = " + first.equals(second));
        System.out.println("different references = " + (first != second));
        System.out.println("interned references = " + (first.intern() == second.intern()));

        String rocket = "\uD83D\uDE80";
        System.out.println("rocket UTF16 units = " + rocket.length());
        System.out.println("rocket code points = "
                + rocket.codePointCount(0, rocket.length()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StringVersionDemo.java
java StringVersionDemo
```

Kết quả:

```text
substring = cde
substring length = 3
substring content = true
new equals literal = true
new == literal = false
intern == literal = true
constant == literal = true
runtime equals literal = true
runtime intern == literal = true
equal objects = true
different references = true
interned references = true
rocket UTF16 units = 2
rocket code points = 1
```

Chương trình kiểm tra **hợp đồng quan sát được** thay vì kích thước backing array:

- `substring` trả đúng nội dung, không khẳng định mảng dữ liệu có được copy hay không.
- `new String("java")` tạo tham chiếu khác literal nhưng cùng nội dung.
- `intern` trả về một đại diện canonical; cả hai lần gọi `intern` trên các String cùng nội dung cho cùng tham chiếu.
- Hai `String` khác nhau từ hai mảng ký tự riêng có nội dung `"AB"` vẫn là hai đối tượng; dedup của GC không thay đổi phép kiểm tra identity của chúng.
- `length()` vẫn tính theo UTF-16 bất kể có dùng Compact Strings bên trong hay không.

Không nên tạo bài kiểm tra unit test có assertion về địa chỉ, trường `value` nội bộ, số byte chiếm dụng hoặc tốc độ của `substring`. Các đặc điểm này cần benchmark/profiler và có thể thay đổi qua patch version.

## 8. Cách kiểm tra tối ưu trên đúng JDK đang chạy

### Bước 1: ghi rõ môi trường

Kiểm tra JDK và JVM hiện dùng:

```bash
java -version
javac -version
```

Ghi lại nhà cung cấp, bản cập nhật, hệ điều hành, kiến trúc CPU, heap size, collector và các cờ JVM liên quan. Nói “Java 17” thôi chưa đủ để chứng minh hai tiến trình có cùng footprint và chiến lược tối ưu.

### Bước 2: đo vấn đề thật

Trước khi tối ưu, xác định thước đo:

- Nếu quan tâm **heap footprint**, dùng heap dump/profiler để thấy số lượng `String`, kích thước dữ liệu và những đối tượng còn tham chiếu.
- Nếu quan tâm **allocation rate/GC**, dùng Java Flight Recorder (JFR), công cụ giám sát GC hoặc heap/allocation profiler phù hợp.
- Nếu quan tâm **throughput/latency** của việc cắt và ghép chuỗi, dùng benchmark có warm-up và dữ liệu đại diện; [JMH](https://github.com/openjdk/jmh) là công cụ chuyên dụng của OpenJDK. Đừng dựa vào `System.nanoTime()` quanh một phép `substring` đơn lẻ để đưa kết luận.
- Nếu quan tâm **intern/dedup**, đo số giá trị lặp lại, thời gian sống và chi phí pool/GC. Không suy ra lượng bộ nhớ tiết kiệm từ `==`.

### Bước 3: so sánh một yếu tố mỗi lần

Chạy cùng workload với phiên bản JDK/cờ JVM dự kiến, cố định dữ liệu và tài nguyên, đo nhiều lần; cân nhắc chi phí GC và tác dụng phụ. Ví dụ, chỉ thử bật `-XX:+UseStringDeduplication` khi runtime hỗ trợ và đo được khối lượng chuỗi trùng lặp đáng kể. Đừng tự ý dùng cờ cũ như `-XX:MaxPermSize` trên JDK đã loại bỏ PermGen.

### Bước 4: ưu tiên tính đúng trước micro-optimization

Khi code rõ ràng và đúng phạm vi dữ liệu, thường nên giữ `substring`, `equals` và cách tạo chuỗi phổ biến. Chỉ thêm cache, intern hay cấu hình JVM sau khi có bằng chứng về bottleneck và kiểm thử hồi quy. Hiệu năng cũng có thể thay đổi khi nâng patch JDK, thay collector hoặc thay số lượng dữ liệu thực tế.

## 9. Các nhận định dễ sai

| Khẳng định | Đánh giá và cách hiểu đúng |
| --- | --- |
| “`substring` luôn tạo view dùng chung mảng gốc.” | Sai với nhiều JDK hiện đại; đó là hành vi của một số triển khai cũ trước JDK 7u6. |
| “`substring` luôn phải copy và tốn O(n) trên mọi JVM.” | Không phải bảo đảm API; hiệu năng, trường hợp biên và tối ưu JIT phụ thuộc cài đặt. |
| “`new String(s)` luôn tạo backing array mới, nên phải gọi sau `substring`.” | Không đúng cho JDK hiện đại; tránh dùng mẹo lịch sử không còn phù hợp. |
| “Mọi String intern đều ở PermGen.” | Sai từ JDK 7 trong HotSpot; đối tượng intern nằm trên heap thông thường. |
| “JDK 8 Metaspace là nơi lưu String pool.” | Sai; Metaspace thay một phần vai trò metadata của PermGen, không có nghĩa chuỗi Java nằm trong Metaspace. |
| “`intern` làm `equals` nhanh hơn cho mọi chuỗi.” | Không đúng; có chi phí duy trì pool và không thay thế quy tắc so sánh nội dung. |
| “String Deduplication làm `a == b` thành true.” | Sai; nó có thể chia sẻ dữ liệu nội bộ nhưng không hợp nhất các đối tượng String. |
| “JDK 9+ luôn dùng UTF-8 cho String vì có Compact Strings.” | Sai; cơ chế compact sử dụng Latin-1 hoặc UTF-16 trong triển khai tương ứng, không phải mã hóa UTF-8 của API. |
| “Mọi ký tự có dấu phải dùng hai byte ở Compact Strings.” | Sai; ký tự thuộc Latin-1 như `é` có thể dùng một byte trong dạng compact. |
| “Đổi JDK không ảnh hưởng tối ưu bộ nhớ.” | Sai; layout, JIT, GC và flags thay đổi. Cần đo lại nếu việc tối ưu quan trọng. |

## 10. Bài tập tự kiểm tra

**Bài 1.** Có thể viết code dựa vào giả định `big.substring(0, 3)` luôn giữ tham chiếu tới toàn bộ mảng dữ liệu của `big` không?

**Đáp án:** Không. Đó là chi tiết của một số JDK cũ. Hợp đồng API chỉ bảo đảm nội dung đoạn con và xử lý chỉ số hợp lệ.

**Bài 2.** Vì sao đoạn sau in `true` rồi `false`?

```java
String literal = "abc";
String copy = new String("abc");

System.out.println(literal.equals(copy));
System.out.println(literal == copy);
```

**Đáp án:** `equals` so sánh nội dung còn `==` so sánh identity; `new String(...)` tạo đối tượng String mới.

**Bài 3.** `a.intern() == b.intern()` cho biết điều gì nếu `a.equals(b)` là `true`?

**Đáp án:** Hai chuỗi cùng nội dung được đưa về cùng đại diện canonical trong pool. Điều đó không chứng minh chúng vốn là một đối tượng trước khi gọi `intern`.

**Bài 4.** Hai String `a` và `b` khác đối tượng nhưng có nội dung giống nhau. Sau String Deduplication của GC, `a == b` có chuyển thành `true` không?

**Đáp án:** Không. Deduplication có thể dùng chung dữ liệu nội bộ, còn đối tượng String vẫn giữ identity riêng.

**Bài 5.** Vì sao `"café"` có thể được lưu gọn ở JVM hỗ trợ Compact Strings, còn `"漢字"` cần dạng khác?

**Đáp án:** Các ký tự trong `"café"` nằm trong Latin-1; `"漢字"` có ký tự ngoài Latin-1. Đây là chiến lược lưu dữ liệu của JEP 254, không đổi ý nghĩa Unicode/UTF-16 mà API `String` cung cấp.

## Tài liệu tham khảo

- [Java SE 17 — API `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): hợp đồng `substring`, `intern`, tính immutable và mô hình UTF-16.
- [Oracle — Java Virtual Machine Enhancements in JDK 7](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/enhancements-7.html): sự thay đổi vị trí interned strings trong HotSpot từ JDK 7.
- [Oracle — JDK 9 Enhancements, JEP 254 Compact Strings](https://www.oracle.com/java/technologies/javase/9-enhancements.html): bố trí `byte[]` + coder Latin-1/UTF-16 và tùy chọn `CompactStrings`.
- [OpenJDK — JEP 192 String Deduplication in G1](https://openjdk.org/jeps/192): chia sẻ dữ liệu String trùng lặp và mục tiêu giảm sử dụng heap từ JDK 8u20.
- [OpenJDK — JEP 280 Indify String Concatenation](https://openjdk.org/jeps/280): cài đặt nối chuỗi thay đổi từ Java 9.
- [Aleksey Shipilëv — java.lang.String Catechism (2014)](https://2014.jokerconf.com/presentations/shipilev-string.pdf): phân tích trực quan lịch sử `substring` và chi phí bộ nhớ của cách chia sẻ mảng trước JDK 7u6.

**Nguyên tắc áp dụng:** viết Java dựa vào ngữ nghĩa chuẩn của `String`; đo `substring`, `intern` và các tối ưu bộ nhớ bằng **JDK/JVM thực sự triển khai ứng dụng**. Các mẹo về backing array, pool, cấp phát hoặc GC luôn cần được đặt trong ngữ cảnh phiên bản cụ thể.
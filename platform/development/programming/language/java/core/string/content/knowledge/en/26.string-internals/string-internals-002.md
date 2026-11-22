# Compact Strings và hai dạng LATIN1, UTF16 trong OpenJDK

Từ Java 9, các phiên bản OpenJDK dùng cơ chế **Compact Strings** (JEP 254) để giảm bộ nhớ lưu trữ nội dung của nhiều đối tượng `String`. Một chuỗi chỉ chứa các đơn vị mã nằm trong phạm vi Latin-1 có thể lưu bằng **1 byte cho mỗi đơn vị mã**; chuỗi chứa đơn vị mã ngoài phạm vi đó dùng dạng **UTF16, 2 byte cho mỗi đơn vị mã**. Đây là **chi tiết triển khai nội bộ** của OpenJDK/HotSpot, không thay đổi ý nghĩa của API `String`.

Bài này giải thích lý do ra đời, cách OpenJDK chọn dạng `LATIN1` hoặc `UTF16`, tác động đến bộ nhớ và tốc độ, cách tự kiểm tra ví dụ Java 17+, cũng như những nhầm lẫn khi so sánh Compact Strings với UTF-8 hoặc `String.length()`.

## 1. Bối cảnh: từ `char[]` tới `byte[]`

Trước Java 9, các bản OpenJDK phổ biến biểu diễn nội dung `String` bằng một mảng `char[]`. Mỗi `char` là một **đơn vị mã UTF-16** dài 16 bit (2 byte), kể cả khi chuỗi chỉ chứa ASCII như `"Hello"`. Với trường hợp ASCII hoặc Latin-1 chiếm tỷ trọng cao, phần lớn dung lượng 16 bit mỗi đơn vị mã không cần đến.

JEP 254 (triển khai trong JDK 9) chuyển nội dung sang một mảng `byte[]` kèm **một trường nhận diện cách mã hóa nội bộ**, thường được gọi là `coder`:

~~~text
                    String trong OpenJDK từ Java 9
                  ┌───────────────────────────────┐
                  │ value: byte[]                 │
                  │ coder: LATIN1 hoặc UTF16      │
                  │ các metadata nội bộ khác      │
                  └───────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              coder = LATIN1            coder = UTF16
             1 byte/code unit          2 byte/code unit
             (nội dung phù hợp)        (nội dung ngoài Latin-1)
~~~

Đây là **sơ đồ ý tưởng**. Mảng `byte[]` là đối tượng riêng trên heap, ngoài dữ liệu nội dung còn có chi phí header, căn chỉnh bộ nhớ và tham chiếu. Sơ đồ không thể dùng để tính chính xác kích thước toàn bộ đối tượng.

**Lưu ý về phiên bản:** đây là cơ chế triển khai của OpenJDK từ Java 9, không phải quy định bắt buộc của Java Language Specification. Một JVM khác hoặc một bản Java tương lai có thể triển khai khác mà vẫn tuân thủ cùng API `String`.

## 2. Quy tắc chọn `LATIN1` hay `UTF16`

Trong OpenJDK khi Compact Strings được bật:

- **`LATIN1`:** mọi đơn vị mã UTF-16 của chuỗi đều nằm trong khoảng `U+0000`–`U+00FF`. Mỗi đơn vị mã có thể biểu diễn bằng một byte. Đây là tập giá trị tương ứng ISO-8859-1/Latin-1, bao gồm ASCII và các ký tự như `é` (`U+00E9`), `ñ` (`U+00F1`).
- **`UTF16`:** có ít nhất một đơn vị mã nằm ngoài `U+00FF`; toàn bộ nội dung của chuỗi được lưu theo biểu diễn UTF-16 nội bộ, hai byte trên mỗi đơn vị mã. Ví dụ `€` (`U+20AC`), `ệ` (`U+1EC7`), chữ Hán, ký tự emoji.
- Với ký tự ngoài BMP như `😀` (`U+1F600`), một Unicode code point cần một **cặp surrogate** gồm hai đơn vị mã UTF-16; dạng nội bộ `UTF16` dùng tổng cộng bốn byte cho cặp đó.

Điều kiện thuộc về **toàn chuỗi**. `"ABCé"` vẫn đủ điều kiện `LATIN1`, trong khi `"ABC€"` buộc sử dụng `UTF16` cho cả chuỗi, không phải ba ký tự đầu dùng Latin-1 và ký tự cuối dùng UTF-16 trong cùng một `String`.

### Bảng so sánh dễ nhớ

| Nội dung | `String.length()` | Có thể dùng `LATIN1` khi bật Compact Strings? | Số byte của riêng mảng nội dung theo dạng tương ứng |
| --- | ---: | --- | ---: |
| `"Hello"` | 5 | Có | 5 |
| `"café"` | 4 | Có | 4 |
| `"Euro €"` | 6 | Không, vì `€` lớn hơn `U+00FF` | 12 |
| `"Việt"` | 4 | Không, vì `ệ` là `U+1EC7` | 8 |
| `"A😀B"` | 4 | Không, vì emoji là cặp surrogate | 8 |

Cột cuối **chỉ biểu thị số byte nội dung lý thuyết trong mảng `value`**, giả sử chuỗi được tạo theo dạng nêu trong bảng. Nó không bao gồm kích thước đối tượng `String`, mảng `byte[]`, header, alignment, khả năng dùng chung dữ liệu hay kỹ thuật tối ưu khác của JVM.

**Hai nhầm lẫn quan trọng:**

1. `LATIN1` không đồng nghĩa chỉ có ASCII: `é` vẫn đủ điều kiện, dù UTF-8 của `é` dùng 2 byte.
2. `LATIN1` là phạm vi Unicode `U+0000`–`U+00FF`, **không phải Windows-1252**. Dấu nháy cong `’` là `U+2019`; dù Windows-1252 mã hóa được ký tự đó bằng một byte, OpenJDK Compact Strings vẫn không thể lưu nó trong dạng `LATIN1`.

## 3. `byte[] value` và `coder` hoạt động ra sao?

Trong mã nguồn `java.lang.String` của các phiên bản OpenJDK có Compact Strings, bạn có thể thấy các thành phần nội bộ tương đương:

~~~java
private final byte[] value;
private final byte coder;
static final boolean COMPACT_STRINGS;
~~~

Đây là **trích đoạn minh họa khai báo trường nội bộ**, không phải đoạn chương trình Java có thể biên dịch độc lập và cũng không phải public API.

- `value` chứa byte biểu diễn nội dung chuỗi.
- `coder` cho biết phải diễn giải `value` theo dạng `LATIN1` hay `UTF16`. Trong các bản OpenJDK được đề cập, giá trị nội bộ điển hình là `LATIN1 = 0` và `UTF16 = 1`; lập trình ứng dụng không nên phụ thuộc những hằng số nội bộ này.
- `COMPACT_STRINGS` là cờ nội bộ mà JIT có thể dùng để tối ưu nhánh thực thi. Khi chế độ nén bị tắt ở mức VM, đường thực thi UTF16 được sử dụng.

OpenJDK có các lớp trợ giúp nội bộ như `StringLatin1` và `StringUTF16` để cài đặt những thao tác trên từng dạng lưu trữ. Nhiều phép toán của `String` có đường xử lý riêng hoặc đường tối ưu tương ứng với `coder`. Những lớp này thuộc `java.lang` nhưng **không phải API công khai để ứng dụng phụ thuộc**.

Bạn có thể quan sát tên trường của JDK đang sử dụng bằng lệnh:

~~~bash
javap -private java.lang.String
~~~

Trong các phiên bản OpenJDK có cách tổ chức này, phần khai báo có thể thấy `byte[] value`, `byte coder` và `COMPACT_STRINGS`. Lệnh `javap` là công cụ xem cấu trúc class; nó **không xác định `coder` của một đối tượng `String` cụ thể**.

Không nên viết logic nghiệp vụ bằng reflection vào `String.value`/`String.coder`: các trường `private` có thể thay đổi theo JDK, Java Module System giới hạn quyền truy cập sâu, và thao tác sửa nội dung bên trong còn phá vỡ bất biến `String`.

## 4. Thí nghiệm chạy được trên Java 17+: tính điều kiện dùng Latin-1

Public API không cho biết trực tiếp `coder`, nhưng ta có thể tự kiểm tra **nội dung có đủ điều kiện** lưu bằng Latin-1 hay không. Điều này khác với việc đo trạng thái thực tế của bộ nhớ JVM.

Tạo tệp `CompactStringsDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class CompactStringsDemo {
    public static void main(String[] args) {
        inspect("ASCII", "Cafe");
        inspect("Latin1", "caf\u00E9");
        inspect("Vietnamese", "Vi\u1EC7t");
        inspect("Euro", "Euro \u20AC");
        inspect("Emoji", "A\uD83D\uDE00B");
    }

    private static void inspect(String label, String text) {
        int utf16Units = text.length();
        int codePoints = text.codePointCount(0, text.length());
        int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

        // chars() duyệt từng đơn vị mã UTF-16, không phải code point.
        boolean latin1Eligible = text.chars()
                .allMatch(codeUnit -> codeUnit <= 0xFF);

        System.out.printf(
                "%s: units=%d, codePoints=%d, utf8Bytes=%d, latin1Eligible=%s%n",
                label, utf16Units, codePoints, utf8Bytes, latin1Eligible
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CompactStringsDemo.java
java CompactStringsDemo
~~~

Đầu ra:

~~~text
ASCII: units=4, codePoints=4, utf8Bytes=4, latin1Eligible=true
Latin1: units=4, codePoints=4, utf8Bytes=5, latin1Eligible=true
Vietnamese: units=4, codePoints=4, utf8Bytes=6, latin1Eligible=false
Euro: units=6, codePoints=6, utf8Bytes=8, latin1Eligible=false
Emoji: units=4, codePoints=3, utf8Bytes=6, latin1Eligible=false
~~~

Giải thích:

- `"Cafe"` gồm 4 ký tự ASCII: đủ điều kiện Latin-1 và cũng cần đúng 4 byte UTF-8.
- `"café"` gồm 4 đơn vị mã UTF-16, tất cả không vượt `U+00FF`, nên đủ điều kiện Latin-1; tuy nhiên UTF-8 của `é` chiếm **2 byte**, vì vậy toàn chuỗi có 5 byte UTF-8.
- `"Việt"` có `ệ` (`U+1EC7`), nằm ngoài Latin-1. `length()` là 4 nhưng khi mã hóa UTF-8 cần 6 byte.
- `"Euro €"` chứa ký hiệu euro `U+20AC`, nên không đủ điều kiện Latin-1 dù các ký tự đầu là ASCII.
- `"A😀B"` chứa 3 code point nhưng 4 đơn vị mã UTF-16: emoji chiếm 2 đơn vị mã và 4 byte UTF-8.

`text.chars()` trả về một `IntStream` của **đơn vị mã UTF-16**, nên ở đây kiểm tra `<= 0xFF` là phù hợp để diễn tả điều kiện nén Latin-1. Nếu dùng `codePoints()`, bạn đang duyệt theo code point; trong trường hợp này vẫn có thể suy luận điều kiện với chuỗi hợp lệ, nhưng cần hiểu sự khác nhau khi làm việc với surrogate đơn lẻ.

Biến `latin1Eligible` chỉ trả lời “nội dung có vừa Latin-1 không?”. Nếu chạy với Compact Strings **đã tắt**, biểu thức vẫn là `true` cho `"café"`, trong khi VM sẽ sử dụng dạng nội bộ `UTF16`. Không gọi đây là cách kiểm tra chính xác `String.coder`.

## 5. Thử tùy chọn JVM `-XX:-CompactStrings`

Với HotSpot/OpenJDK hỗ trợ cờ này, Compact Strings được bật mặc định từ Java 9. Có thể chạy chương trình trên ở hai chế độ:

~~~bash
java CompactStringsDemo
java -XX:-CompactStrings CompactStringsDemo
~~~

Ở chế độ thứ hai, HotSpot tắt cơ chế nén và sử dụng dạng nội bộ `UTF16` cho chuỗi. **Hai lần chạy vẫn phải in ra cùng nội dung** như ví dụ trên: cả `String.length()`, `codePointCount()`, byte UTF-8 và `latin1Eligible` đều xuất phát từ ký tự/Unicode, không phải trạng thái `coder` nội bộ.

Điều này cho thấy Compact Strings được thiết kế để **bảo toàn hành vi của public API**. Bạn có thể dùng cờ tắt để nghiên cứu hiệu ứng bộ nhớ/hiệu năng, nhưng không nên tắt nó mặc định nếu không có benchmark hoặc bằng chứng hồi quy trên workload thực tế.

Lưu ý cú pháp cờ VM: `-XX:-CompactStrings` phải đứng **trước tên class** khi gọi `java`, vì nó là tùy chọn của JVM, không phải đối số truyền vào `main(String[] args)`.

## 6. Phân biệt ba khái niệm: nội bộ, UTF-16 và UTF-8

Đây là điểm rất dễ gây hiểu nhầm khi học về Compact Strings.

| Câu hỏi | Cơ chế/API thích hợp |
| --- | --- |
| Có bao nhiêu đơn vị mã trong `String`? | `text.length()`: luôn đếm UTF-16 code units theo hợp đồng API |
| Có bao nhiêu Unicode code point? | `text.codePointCount(0, text.length())` |
| Có bao nhiêu byte UTF-8 khi xuất chuỗi? | `text.getBytes(StandardCharsets.UTF_8).length` |
| OpenJDK có thể lưu phần nội dung của chuỗi này ở dạng Latin-1? | Mọi đơn vị mã UTF-16 đều `<= U+00FF`, với Compact Strings được bật |
| Kích thước heap thật sự là bao nhiêu? | Đo trên VM cụ thể bằng heap profiler/công cụ layout, bao gồm overhead và tương tác với GC |

**Nội bộ `LATIN1` không đồng nghĩa dây truyền dùng ISO-8859-1.** Chẳng hạn một `String` Java chứa `"café"` có thể chiếm 4 byte ở mảng `value` nội bộ, nhưng:

~~~java
String text = "caf\u00E9";
int utf8Size = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8
).length; // 5
~~~

Đoạn mã trên minh họa một biểu thức Java trong phương thức; đầu ra ở giao thức UTF-8 vẫn là **5 byte**. Ngược lại, gọi `getBytes(StandardCharsets.ISO_8859_1)` là **yêu cầu mã hóa dữ liệu bên ngoài** sang ISO-8859-1, không phải hành động “lấy mảng `value` nội bộ” của `String`.

**Nội bộ `UTF16` không đồng nghĩa dữ liệu bên ngoài buộc phải dùng UTF-16.** `"A😀B"` có thể ở dạng `UTF16` trong heap, nhưng khi truyền HTTP body/ghi file qua UTF-8, kết quả vẫn là mã UTF-8 theo charset chỉ định. Không bao giờ suy ra kích thước UTF-8 trực tiếp từ `coder` hoặc `length()`.

## 7. Tác động đến bộ nhớ thực tế

### Tiết kiệm ở đâu?

Khi một chuỗi có `n` đơn vị mã UTF-16 và phù hợp Latin-1:

- Dạng `LATIN1` cần xấp xỉ `n` byte cho **phần dữ liệu ký tự**.
- Dạng `UTF16` cần xấp xỉ `2n` byte cho **phần dữ liệu ký tự**.
- Về riêng phần nội dung, dữ liệu dạng Latin-1 dùng khoảng **một nửa** dung lượng so với biểu diễn UTF-16 hai byte trên mỗi đơn vị mã.

Ví dụ một chuỗi 1.000 ký tự ASCII có thể dùng khoảng 1.000 byte cho nội dung thay vì khoảng 2.000 byte. Đây **không phải** tuyên bố rằng toàn đối tượng `String` hay tổng heap của ứng dụng sẽ giảm 50%. Tổng bộ nhớ còn phụ thuộc header, alignment, mảng, trường `coder`, tham chiếu, String pool, GC, deduplication và các thành phần khác.

### Khi nào lợi ích giảm?

Một chuỗi có một ký tự ngoài Latin-1, như `"report-2026-€"`, cần dùng dạng `UTF16` cho toàn bộ chuỗi trong mô hình Compact Strings này. Tỷ lệ các chuỗi như vậy, độ dài chuỗi, vòng đời đối tượng và lượng string được tái sử dụng sẽ ảnh hưởng lợi ích tổng thể.

Đối với ứng dụng đa ngôn ngữ, **không kết luận “tiếng Việt luôn dùng 2 byte mỗi ký tự”**. Một số ký tự tiếng Việt như `ê` (`U+00EA`) thuộc Latin-1, nhưng nhiều ký tự như `ệ` (`U+1EC7`) nằm ngoài. Coder được chọn trên cơ sở toàn chuỗi, và emoji còn có surrogate pair. Vì vậy cần phân tích dữ liệu thực tế.

### Tốc độ xử lý có luôn tăng không?

Không có bảo đảm mọi thao tác luôn nhanh hơn. Compact Strings có thể giảm băng thông bộ nhớ, giảm áp lực cache/GC khi phần lớn chuỗi phù hợp Latin-1. Đồng thời có thêm những đường xử lý/phân nhánh hoặc chuyển đổi giữa biểu diễn; HotSpot dùng nội tại (intrinsics) và tối ưu JIT để giảm overhead cho nhiều thao tác. Kết quả phụ thuộc thao tác và workload.

Để đánh giá:

1. Giữ nguyên ứng dụng/dữ liệu thử nghiệm; so sánh mặc định với `-XX:-CompactStrings` trên **cùng phiên bản JDK và cấu hình máy**.
2. Đo lượng cấp phát, live heap, GC, throughput và latency đại diện cho thực tế.
3. Warm-up, dùng công cụ benchmark đúng mục đích (ví dụ JMH cho microbenchmark) và tránh đo duy nhất thời gian của một vòng lặp thiếu kiểm soát.
4. Không suy ra lợi ích hiệu năng chỉ từ công thức `n` và `2n`, hoặc từ một ví dụ vài chuỗi ngắn.

## 8. Vì sao `String.length()` không đổi?

Theo API Java, `length()` luôn trả về số **đơn vị mã UTF-16** trong chuỗi. Nội bộ OpenJDK có thể lưu Latin-1 một byte trên mỗi đơn vị mã, nhưng Java vẫn phải trả về `length()` như trước JDK 9.

Ví dụ:

~~~java
String latin1 = "caf\u00E9";
String emoji = "A\uD83D\uDE00B";

System.out.println(latin1.length()); // 4
System.out.println(emoji.length());  // 4
System.out.println(emoji.codePointCount(0, emoji.length())); // 3
~~~

Đây là đoạn mã minh họa trong một phương thức, không phải class độc lập; các giá trị là `4`, `4` và `3`. Chế độ Compact Strings không đổi kết quả đó.

Với ký tự ngoài BMP, Java vẫn biểu diễn một code point bằng một **cặp surrogate ở lớp API UTF-16**. Dù cơ chế lưu trữ bên dưới thay đổi, các phương thức `charAt`, `substring`, `codePointAt`, `codePointCount` phải giữ đúng hợp đồng API. Lưu ý `substring` và chỉ số `charAt` dùng vị trí của **đơn vị mã UTF-16**; có thể cắt giữa surrogate pair nếu lập trình viên chọn chỉ số không phù hợp.

## 9. Hoạt động khi tạo và biến đổi chuỗi

Những thao tác như tạo chuỗi từ literal, ghép chuỗi, chuyển từ `StringBuilder`, đổi chữ hoa/thường hay trích chuỗi con có thể dẫn đến **một đối tượng `String` khác**. Biểu diễn nội bộ của đối tượng kết quả có thể được chọn theo **nội dung của kết quả**, độc lập với dạng của đối tượng đầu vào.

Ví dụ ở góc độ nội dung:

~~~java
String original = "ABC\u20AC";
String onlyAscii = original.substring(0, 3);

System.out.println(original); // ABC€
System.out.println(onlyAscii); // ABC
~~~

Đây là đoạn minh họa có thể đặt trong phương thức. Khi Compact Strings bật, một `String` mới chỉ chứa `"ABC"` đủ điều kiện Latin-1 dù `original` có ký tự `€`. Tuy nhiên, **không nên dựa vào chi tiết đối tượng có dùng chung/copy mảng nào hoặc đúng thời điểm chọn coder**: đó là quyết định của phiên bản triển khai. Mục tiêu quan trọng là các API trả về văn bản đúng.

`StringBuilder` và `StringBuffer` trong các bản OpenJDK hỗ trợ JEP 254 cũng có những tối ưu biểu diễn nội dung liên quan, nhưng chiến lược quản lý dung lượng/capacity của builder không đồng nhất với `String` bất biến. Tránh suy ra rằng phép `append` hay `toString()` luôn sao chép, luôn dùng chung mảng hoặc luôn có chi phí cố định.

## 10. Những nhầm lẫn thường gặp

**Nhầm 1 — “Java từ Java 9 đã đổi String sang UTF-8”.** Sai. Compact Strings sử dụng **LATIN1 hoặc UTF16** để lưu trữ nội bộ, không dùng UTF-8 làm hai dạng coder chính.

**Nhầm 2 — “Vì mảng là `byte[]` nên `String.length()` đếm byte”.** Sai. `length()` vẫn đếm UTF-16 code units, bất kể Java sử dụng dạng lưu trữ nội bộ nào.

**Nhầm 3 — “Mọi ký tự không phải ASCII đều dùng UTF16”.** Sai. `é`, `ñ` hoặc `ÿ` đều nằm trong phạm vi Latin-1. Trong khi đó, `€` và phần lớn các dấu Unicode ngoài `U+00FF` buộc dùng UTF16.

**Nhầm 4 — “Chỉ ký tự vượt Latin-1 mới chiếm 2 byte”.** Sai ở cấp **một đối tượng `String`**: khi một đơn vị mã không vừa Latin-1, cả chuỗi chuyển sang dạng UTF16.

**Nhầm 5 — “Có thể đọc `coder` để tối ưu logic ứng dụng”.** Trường này là nội bộ và có thể thay đổi. Không dùng reflection/`Unsafe` để viết logic phụ thuộc `coder`; xử lý chuỗi bằng public API.

**Nhầm 6 — “Tắt Compact Strings thì chương trình trả ra văn bản khác”.** Sai đối với hành vi hợp lệ của public API. Cờ tác động biểu diễn và có thể ảnh hưởng bộ nhớ/hiệu năng, không thay đổi nội dung hay cách đếm `length()`.

**Nhầm 7 — “String đủ điều kiện Latin-1 thì dữ liệu UTF-8 cũng chỉ có một byte/ký tự”.** Sai: `"café"` có 4 đơn vị mã và đủ điều kiện Latin-1, nhưng cần 5 byte khi mã hóa UTF-8.

**Nhầm 8 — “Tiết kiệm 50% dữ liệu ký tự tức tiết kiệm 50% toàn bộ heap”.** Sai. Tổng heap gồm nhiều đối tượng và overhead; cần đo thực tế.

## 11. Kiểm tra kiến thức

**Câu 1.** `"ABC\u00E9"` có dùng dạng `LATIN1` được không? Tại sao?

**Đáp án:** Có, vì cả bốn đơn vị mã UTF-16 đều nằm trong `U+0000`–`U+00FF`. Trong môi trường bật Compact Strings, nội dung đủ điều kiện nén còn 4 byte.

**Câu 2.** `"ABC\u20AC"` có thể lưu 3 ký tự đầu ở LATIN1 và ký tự cuối ở UTF16 trong cùng đối tượng `String` không?

**Đáp án:** Không theo mô hình JEP 254 của OpenJDK: `coder` chọn một dạng cho nội dung của toàn đối tượng. Có ký tự `€` ngoài Latin-1 nên cần dạng UTF16.

**Câu 3.** Chạy cùng chương trình Java với `-XX:-CompactStrings`. Giá trị `"A😀B".length()` có thay đổi không?

**Đáp án:** Không. Giá trị vẫn là `4`, gồm `A` (1), emoji (2 đơn vị mã UTF-16) và `B` (1).

**Câu 4.** Một dịch vụ gửi UTF-8 qua mạng. Có nên lấy số byte mảng nội bộ `String.value` làm `Content-Length`?

**Đáp án:** Không. Phải dùng số byte của **payload cuối cùng** được gửi. Compact Strings là chi tiết lưu trữ nội bộ; khi xuất UTF-8, chuỗi được mã hóa sang UTF-8 độc lập với coder bên trong.

**Câu 5.** Tại sao nên đánh giá bằng heap profiling thay vì dùng `text.length() * 1` hay `* 2` để báo lượng RAM mà `String` chiếm?

**Đáp án:** Các công thức đó chỉ mô tả gần đúng **phần dữ liệu** trong mảng lưu trữ, bỏ qua object header, array header, alignment, tham chiếu, khả năng tái sử dụng và nhiều tối ưu khác. Kích thước thực còn phụ thuộc cấu hình JVM.

## 12. Kết luận và cách áp dụng

Compact Strings là tối ưu lưu trữ của OpenJDK từ Java 9: `String` sử dụng `byte[] value` cùng `coder` để chọn **LATIN1 khi mọi đơn vị mã nằm trong `U+0000`–`U+00FF`**, hoặc **UTF16 khi có đơn vị mã ngoài phạm vi đó**. Trên nhiều workload chứa lượng lớn chuỗi Latin-1, phần dữ liệu ký tự có thể giảm gần một nửa so với cách lưu UTF-16 cố định. Nhưng đây là tối ưu phía dưới API; trong ứng dụng, hãy tiếp tục dùng `String.length()`, các API code point và mã hóa byte bằng `StandardCharsets.UTF_8` theo đúng ngữ nghĩa từng nhu cầu.

Khi tối ưu heap, nên đo dữ liệu/ứng dụng thực tế và chỉ cân nhắc `-XX:-CompactStrings` nếu phép đo cho thấy lý do cụ thể; khi triển khai định dạng file, HTTP hay cơ sở dữ liệu, hãy căn cứ **charset và định dạng đầu ra**, không căn cứ coder nội bộ.

Tài liệu tham khảo:

- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254).
- [Oracle JDK 21 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).
- [OpenJDK: mã nguồn `java.lang.String`](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/String.java) và [`StringUTF16`](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/StringUTF16.java).
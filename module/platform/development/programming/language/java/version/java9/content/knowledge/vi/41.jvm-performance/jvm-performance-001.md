# Compact Strings và biểu diễn Latin-1 hoặc UTF-16 bên trong HotSpot

Compact Strings là tối ưu bộ nhớ được HotSpot đưa vào từ Java 9. Thay vì lưu mọi ký tự của String bằng hai byte như cách biểu diễn char array trước đó, HotSpot có thể lưu nội dung String bằng một byte cho mỗi đơn vị Latin-1 khi toàn bộ nội dung nằm trong phạm vi đó. Nếu String chứa ký tự ngoài Latin-1, HotSpot dùng biểu diễn UTF-16.

Tối ưu này thay đổi cách triển khai bên trong JVM, không thay đổi hợp đồng công khai của lớp `String`. Code vẫn dùng `length()`, `charAt()`, `codePointAt()`, `equals()` và các API String như trước. Để hiểu đúng Compact Strings, cần phân biệt ba khái niệm: biểu diễn nội bộ trong HotSpot, đơn vị mã UTF-16 mà API String sử dụng, và encoding dùng khi chuyển dữ liệu ra byte bên ngoài JVM.

## 1. Compact Strings giải quyết vấn đề gì?

Phần lớn chuỗi trong nhiều ứng dụng chứa chủ yếu ký tự ASCII hoặc Latin-1: tên, mã định danh, URL, email, log, dữ liệu giao thức và văn bản tiếng Tây Âu. Nếu mỗi đơn vị ký tự luôn chiếm hai byte, các chuỗi này dùng nhiều vùng nhớ hơn mức cần thiết để biểu diễn nội dung.

JEP 254 giới thiệu Compact Strings trong JDK 9. Trong HotSpot, String lưu nội dung trong một mảng byte và một coder cho biết cách diễn giải các byte đó:

- Coder Latin-1: mỗi ký tự nằm trong phạm vi U+0000 đến U+00FF được lưu bằng một byte.
- Coder UTF-16: nội dung cần biểu diễn ngoài phạm vi Latin-1 được lưu theo các đơn vị mã UTF-16, mỗi đơn vị mã dùng hai byte.

Vì vậy, chuỗi chỉ chứa ký tự Latin-1 có thể dùng gần một nửa vùng nhớ payload so với cách lưu hai byte cho mỗi đơn vị mã. Mức tiết kiệm thực tế của toàn bộ object nhỏ hơn hoặc bằng mức tiết kiệm payload, vì String và mảng byte vẫn có object header, alignment và các chi phí quản lý bộ nhớ khác.

## 2. HotSpot chọn Latin-1 hay UTF-16 như thế nào?

HotSpot dùng một coder để xác định cách diễn giải mảng byte của String. Trong implementation OpenJDK HotSpot hiện hành, các thao tác xử lý được tách theo hai dạng nội bộ tương ứng với `StringLatin1` và `StringUTF16`.

| Nội dung String | Biểu diễn nội bộ Compact Strings |
|---|---|
| Chỉ chứa U+0000 đến U+00FF | Latin-1, một byte cho mỗi đơn vị ký tự |
| Có ít nhất một ký tự lớn hơn U+00FF | UTF-16, hai byte cho mỗi đơn vị mã UTF-16 |
| Có ký tự supplementary như emoji | UTF-16, thường dùng một cặp surrogate |

Ví dụ:

- `"Hello"` chỉ chứa ASCII nên có thể dùng coder Latin-1.
- `"café"` chứa `é` (U+00E9), vẫn nằm trong Latin-1 nên có thể dùng coder Latin-1.
- `"漢字"` chứa ký tự ngoài Latin-1 nên cần coder UTF-16.
- `"A😀B"` chứa emoji U+1F600. Code point này lớn hơn U+FFFF và được biểu diễn trong UTF-16 bằng một cặp surrogate.

Quyết định này áp dụng cho toàn bộ String. Nếu chỉ một ký tự nằm ngoài Latin-1, String đó cần dạng UTF-16; HotSpot không lưu phần lớn chuỗi bằng Latin-1 rồi chỉ đổi riêng ký tự ngoại lệ sang UTF-16.

## 3. Latin-1 không đồng nghĩa với ASCII

ASCII chỉ bao phủ U+0000 đến U+007F. Latin-1 mở rộng đến U+00FF, do đó bao gồm thêm các ký tự như `é`, `ñ`, `ü` và các ký tự thuộc Latin-1 Supplement.

Điều này có nghĩa một chuỗi có dấu tiếng Tây Âu vẫn có thể được lưu theo dạng Latin-1. Ngược lại, các ký tự như chữ Hán, chữ Nhật, nhiều ký tự tiếng Việt có dấu tổ hợp riêng biệt và nhiều ký hiệu khác không nằm trong phạm vi Latin-1 sẽ khiến String dùng dạng UTF-16.

Không nên kết luận rằng mọi văn bản có dấu đều bắt buộc dùng UTF-16. Cần xét chính xác từng code point: các ký tự như `é` (U+00E9) nằm trong Latin-1, trong khi `ế` (U+1EBF) nằm ngoài phạm vi này. String chứa `ế` do đó cần biểu diễn UTF-16 trong Compact Strings.

## 4. Coder nội bộ không thay đổi cách String hoạt động

Java String có ngữ nghĩa dựa trên chuỗi đơn vị mã UTF-16. Compact Strings không biến String thành một chuỗi byte công khai và cũng không thay đổi cách các API xử lý chỉ số.

Các API quan trọng:

| API | Ý nghĩa |
|---|---|
| `length()` | Số đơn vị mã UTF-16, không phải số code point hay số byte |
| `charAt(index)` | Trả về một đơn vị mã UTF-16 kiểu char |
| `codePointAt(index)` | Trả về code point tại vị trí chỉ định |
| `codePointCount(begin, end)` | Đếm code point trong khoảng đơn vị mã |
| `codePoints()` | Tạo IntStream các code point |
| `getBytes(charset)` | Mã hóa nội dung String thành byte theo charset bên ngoài |

Với ký tự BMP thông thường, một code point thường tương ứng một đơn vị mã UTF-16. Với ký tự supplementary, một code point cần hai đơn vị mã: high surrogate và low surrogate. Vì vậy `"A😀B".length()` bằng 4, trong khi số code point là 3.

Compact Strings có thể lưu chuỗi Latin-1 bằng một byte cho mỗi ký tự, nhưng `length()` vẫn trả về số đơn vị mã UTF-16 theo hợp đồng String. Đây là điểm quan trọng: không dùng `length()` để suy ra số byte nội bộ hoặc số code point.

## 5. Ví dụ Java 17: Latin-1, BMP và supplementary character

Chương trình sau so sánh số đơn vị mã UTF-16, số code point và số byte khi mã hóa UTF-8. Ba con số này mô tả ba khía cạnh khác nhau của cùng một String.

**Main.java**

```java
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class Main {
    private static void describe(String label, String value) {
        int codePoints = value.codePointCount(0, value.length());
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;

        System.out.println(label + " text=" + value);
        System.out.println("length=" + value.length()
                + ", codePoints=" + codePoints
                + ", utf8Bytes=" + utf8Bytes);
    }

    public static void main(String[] args) {
        String latin1 = "café";
        String bmp = "漢字";
        String supplementary = "A😀B";

        describe("latin-1", latin1);
        describe("bmp", bmp);
        describe("supplementary", supplementary);

        int emoji = supplementary.codePointAt(1);
        System.out.println("index1IsHighSurrogate="
                + Character.isHighSurrogate(supplementary.charAt(1)));
        System.out.println("codePointAt1="
                + String.format(Locale.ROOT, "U+%X", emoji));
        System.out.println("sameLogicalValue="
                + latin1.equals(new String(latin1)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả stdout:

```text
latin-1 text=café
length=4, codePoints=4, utf8Bytes=5
bmp text=漢字
length=2, codePoints=2, utf8Bytes=6
supplementary text=A😀B
length=4, codePoints=3, utf8Bytes=6
index1IsHighSurrogate=true
codePointAt1=U+1F600
sameLogicalValue=true
```

Diễn giải:

- `café` có bốn đơn vị mã UTF-16 và bốn code point. Khi mã hóa UTF-8, nội dung chiếm năm byte. Trong HotSpot Compact Strings, chuỗi này có thể dùng Latin-1 vì mọi code point đều không vượt U+00FF.
- `漢字` có hai đơn vị mã UTF-16 và hai code point. Hai ký tự nằm ngoài Latin-1 nên String dùng coder UTF-16.
- `A😀B` có bốn đơn vị mã UTF-16 nhưng chỉ ba code point. `charAt(1)` trả về high surrogate; `codePointAt(1)` kết hợp cặp surrogate và trả U+1F600.

Số byte UTF-8 trong ví dụ là kết quả của một lần mã hóa ra ngoài JVM. Nó không phải số byte mà HotSpot đang dùng để lưu String. Không thể dùng `getBytes(UTF_8)` để suy ra coder nội bộ.

## 6. Compact Strings có thể bật hoặc tắt trong HotSpot

Trên HotSpot, Compact Strings được bật mặc định. Có thể truyền tùy chọn JVM để tắt tối ưu này:

```bash
java -XX:-CompactStrings -cp out Main
```

Hoặc chỉ định bật tường minh:

```bash
java -XX:+CompactStrings -cp out Main
```

Khi tắt Compact Strings, HotSpot dùng biểu diễn UTF-16 cho String thay vì chọn Latin-1 cho chuỗi phù hợp. Giá trị trả về từ `length()`, `codePointCount()`, `charAt()`, `equals()` và kết quả UTF-8 trong ví dụ vẫn không đổi. Khác biệt nằm ở cách lưu trữ và chi phí bộ nhớ/CPU bên trong JVM.

Tùy chọn `-XX` là tùy chọn của HotSpot/OpenJDK, không phải một phần của Java language specification. Các JVM khác có thể có implementation hoặc tùy chọn riêng. Chỉ sử dụng cờ này khi runtime thực tế hỗ trợ và khi đã đo được tác động trên workload đại diện.

## 7. Lợi ích và chi phí hiệu năng

Compact Strings chủ yếu nhắm đến giảm footprint của dữ liệu chuỗi phổ biến:

- Chuỗi Latin-1 cần một byte payload cho mỗi đơn vị ký tự thay vì hai byte.
- Heap nhỏ hơn có thể cải thiện mật độ dữ liệu và cache locality.
- Ít payload hơn có thể giảm lượng dữ liệu GC phải quét hoặc di chuyển trong các tình huống phù hợp.
- Chuỗi chứa ký tự ngoài Latin-1 vẫn cần dạng UTF-16 và không nhận được mức tiết kiệm payload tương tự.

Đổi lại, các thao tác String phải biết coder của nội dung và thực hiện đường xử lý tương ứng. HotSpot có các implementation chuyên biệt cho Latin-1 và UTF-16 để tối ưu các thao tác phổ biến. Không nên mặc định rằng mọi thao tác với Latin-1 luôn nhanh hơn hoặc mọi workload đều cải thiện cùng một tỷ lệ.

Tác động phụ thuộc vào phân bố nội dung, số lượng String, thao tác được thực hiện, GC, heap sizing và phiên bản JVM. Nếu cần so sánh hiệu năng, hãy dùng JMH với dữ liệu đại diện cho production, warm-up phù hợp và đo cả throughput lẫn allocation/memory footprint.

## 8. Điều Compact Strings không làm

| Hiểu nhầm | Thực tế |
|---|---|
| String chỉ còn là byte[] mà API trả về byte | Mảng byte là chi tiết triển khai; API String vẫn giữ ngữ nghĩa UTF-16 |
| Latin-1 chỉ có ASCII | Latin-1 bao phủ U+0000 đến U+00FF |
| Mọi ký tự Unicode chiếm một byte | Chỉ nội dung nằm trọn trong Latin-1 mới dùng coder Latin-1 |
| length() trả số byte | length() đếm đơn vị mã UTF-16 |
| Một char luôn là một code point | Supplementary code point cần một cặp surrogate |
| UTF-8 byte count cho biết coder nội bộ | UTF-8 là encoding bên ngoài; coder nội bộ là quyết định riêng của HotSpot |
| Tắt Compact Strings làm thay đổi nội dung String | Tắt cờ chỉ thay đổi representation và có thể ảnh hưởng hiệu năng/bộ nhớ |
| Latin-1 giúp toàn bộ object giảm đúng 50% | Payload có thể gần một nửa; object header, array header và alignment vẫn tồn tại |

## 9. Lưu ý khi làm việc với Unicode

Khi xử lý văn bản, chọn API theo đơn vị dữ liệu mà nghiệp vụ cần:

- Dùng `length()` khi cần số đơn vị mã UTF-16 theo hợp đồng Java.
- Dùng `codePointCount()` hoặc `codePoints()` khi cần đếm/duyệt Unicode code point.
- Dùng `BreakIterator` hoặc thư viện xử lý Unicode phù hợp khi cần tách ký tự hiển thị (grapheme cluster). Một grapheme có thể gồm nhiều code point, ví dụ chữ cái kết hợp dấu hoặc emoji có modifier.
- Chọn charset rõ ràng như `StandardCharsets.UTF_8` khi đọc/ghi byte. Không dựa vào representation nội bộ của String để quyết định charset của file, network protocol hoặc database.
- Không dùng reflection, `Unsafe` hoặc giả định về field private của String trong ứng dụng. Cấu trúc byte array và coder là chi tiết triển khai có thể thay đổi giữa các JVM hoặc phiên bản.

## 10. Checklist kiểm tra

- Nội dung có nằm hoàn toàn trong U+0000 đến U+00FF không?
- Nếu có ký tự ngoài Latin-1, đã hiểu rằng cả String chuyển sang coder UTF-16 chưa?
- Code có phân biệt UTF-16 code unit, Unicode code point và UTF-8 byte không?
- Có đang dùng `length()` như thể nó đếm code point hoặc byte không?
- Có xử lý surrogate pair đúng khi duyệt ký tự supplementary không?
- Charset bên ngoài có được chỉ định rõ ràng khi chuyển String thành byte không?
- Có đang phụ thuộc vào field private hoặc layout nội bộ của một phiên bản HotSpot không?
- Nếu cân nhắc tắt Compact Strings, đã benchmark trên workload thực tế chưa?

Compact Strings trong HotSpot giảm bộ nhớ payload cho các String chỉ chứa ký tự Latin-1 bằng cách dùng một byte cho mỗi đơn vị ký tự; String có ký tự ngoài phạm vi này dùng biểu diễn UTF-16. Đây là tối ưu triển khai được giới thiệu trong Java 9, không làm thay đổi API hay ngữ nghĩa String. Hãy tiếp tục phân biệt đơn vị mã UTF-16, code point và byte encoding bên ngoài để xử lý Unicode chính xác, bất kể Compact Strings đang bật hay tắt.

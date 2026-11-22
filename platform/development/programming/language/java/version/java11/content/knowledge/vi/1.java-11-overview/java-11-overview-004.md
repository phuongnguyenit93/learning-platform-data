# Đọc Javadoc hiện hành và thông tin `Since` (Java 11)

## Mục tiêu học tập

Sau bài này, bạn có thể tra cứu API Java từ nguồn chính thức, đọc chữ ký và hợp đồng sử dụng của phương thức, hiểu nhãn `Since`, phân biệt thời điểm API xuất hiện với thời điểm bị deprecated và xác nhận liệu API đang xem có dùng được trên Java 11 hay không.

## 1. Chọn đúng tài liệu Javadoc

**Javadoc** là công cụ sinh tài liệu từ chú thích mã Java và cũng là cách gọi tài liệu tham chiếu API. Tài liệu Java SE/JDK mô tả những gì người dùng API có thể dựa vào: chức năng, chữ ký, kiểu tham số và kết quả, ngoại lệ, điều kiện đặc biệt, tình trạng deprecated và phiên bản xuất hiện.

Luôn xác định **hai phiên bản**:

- **Bản JDK mới nhất để cập nhật kiến thức:** [Java SE/JDK 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/) là bản hiện hành tại thời điểm 07/11/2026. Ở thời điểm khác, kiểm tra phiên bản phát hành mới nhất thay vì mặc định mãi là 27.
- **Bản Java phải hỗ trợ:** [Java SE/JDK 11 API Specification](https://docs.oracle.com/en/java/javase/11/docs/api/) khi dự án có baseline Java 11. Đây là nguồn để đối chiếu tập API đã có ở Java 11.

Hai trang có mục đích khác nhau: tài liệu hiện hành cho biết API, cảnh báo và thay đổi mới; tài liệu Java 11 giúp kết luận API có mặt trong baseline Java 11. Một API tìm thấy trên Java 27 **chưa chắc** có thể biên dịch và chạy trên Java 11.

Kiểm tra môi trường bằng:

~~~bash
java -version
javac -version
~~~

Cũng cần xem phiên bản Java được cấu hình trong Maven/Gradle và JDK chạy thật ở môi trường triển khai. JDK dùng để biên dịch, mức tương thích của chương trình và JDK chạy ứng dụng có thể khác nhau.

## 2. Cách đọc một trang API chính thức

Ví dụ cần hiểu `String.isBlank()`:

1. Tại trang API của phiên bản cần tra, sử dụng ô **Search** để tìm `java.lang.String`; hoặc đi theo **module `java.base` → package `java.lang` → class `String`**. Tên đầy đủ gồm package giúp tránh nhầm các lớp trùng tên.
2. Ở đầu trang lớp, đọc mô tả, quan hệ kế thừa, các interface liên quan và mục `Since` của **lớp**.
3. Tại **Method Summary**, tìm `isBlank()` rồi mở **Method Details**. Nếu có overload, xác định đúng **danh sách tham số**: `Files.readString(Path)` và `Files.readString(Path, Charset)` là hai chữ ký khác nhau.
4. Xem chữ ký chính xác: phạm vi truy cập, `static` hay phương thức instance, kiểu trả về, generic, tham số và `throws`.
5. Đọc mô tả hành vi, điều kiện biên, `Parameters`, `Returns`, `Throws`, `Since`, `See Also`; để ý **Deprecated**, **For Removal**, **Preview** hoặc **Incubating** nếu có.
6. Đối chiếu với Javadoc Java 11 nếu sản phẩm phải hỗ trợ Java 11; xác nhận bằng chương trình nhỏ và trình biên dịch.

| Phần trong Javadoc | Câu hỏi phải trả lời |
| --- | --- |
| **Description / Method Details** | API làm gì, xử lý đầu vào và các trường hợp đặc biệt như thế nào? |
| **Parameters / Returns** | Tham số, kết quả có kiểu gì? `null` có được cho phép không? |
| **Throws** | Ngoại lệ nào có thể xuất hiện, ngoại lệ checked nào phải xử lý/khai báo? |
| **Since** | Phần tử được đưa vào đặc tả API từ bản nào? |
| **Deprecated / For Removal** | Còn nên dùng API này không? Có API thay thế hoặc kế hoạch loại bỏ không? |
| **API Note** | Ghi chú dành cho người dùng, cách áp dụng hợp lý. |
| **Implementation Requirements / Notes** | Các yêu cầu hoặc ghi chú riêng về triển khai, không thay thế mô tả hợp đồng API. |
| **See Also** | Các API và hướng dẫn liên quan cần tìm tiếp. |

**Một ví dụ đọc ngữ nghĩa:** `String.isBlank()` trả `true` nếu chuỗi rỗng hoặc chỉ gồm các ký tự khoảng trắng theo `Character.isWhitespace`. Trong khi đó `String.isEmpty()` chỉ trả `true` khi độ dài chuỗi bằng 0. Vì vậy `" ".isBlank()` là `true` còn `" ".isEmpty()` là `false`. Đọc `Returns` sẽ tránh suy đoán sai từ tên phương thức.

## 3. Hiểu đúng `Since` và `@since`

Trong mã nguồn Java, chú thích tài liệu `@since` được công cụ Javadoc hiển thị thành **Since**. Với API nền tảng Java, nhãn này chỉ **phiên bản đặc tả Java lần đầu có phần tử API đó**; nó không nhất thiết là thời điểm một bản triển khai thử nghiệm nội bộ được tạo ra.

Ví dụ cú pháp trong một thư viện tự viết:

~~~java
/**
 * Chuẩn hóa chuỗi đầu vào.
 *
 * @since 2.1
 */
public static String normalize(String text) {
    return text.strip();
}
~~~

Đây chỉ là **đoạn minh họa phương thức**, chưa phải chương trình độc lập. `2.1` ở ví dụ chỉ phiên bản của thư viện giả định, không phải Java 2.1. Với các thư viện ngoài JDK, phải xem tài liệu đúng **phiên bản dependency** để hiểu quy ước `@since`.

Năm quy tắc đọc `Since`:

1. **`Since: 11` nghĩa là API được giới thiệu từ Java 11**, không phải API chỉ hoạt động trên Java 11. Ở các bản sau, API có thể tiếp tục được duy trì, deprecated hoặc trong trường hợp đặc biệt bị loại bỏ; hãy xem tài liệu mới.
2. **Đọc nhãn của chính thành viên đang gọi.** Lớp có thể rất cũ nhưng phương thức mới được bổ sung. Không dùng `Since` ở đầu lớp để kết luận mọi phương thức đều có từ cùng phiên bản.
3. **Không thấy nhãn `Since` không đủ chứng minh API ra mắt từ rất sớm.** Thành viên được thêm cùng lúc với lớp thường không có nhãn riêng; mặt khác tài liệu cũng có thể thiếu thẻ hoặc được tạo với tùy chọn ẩn. Khi quan trọng, đối chiếu trực tiếp trang của bản Java đích.
4. **`@since` khác `@Deprecated(since = "...")`:** thẻ Javadoc `@since` ghi phiên bản được thêm vào API; tham số `since` của annotation `@Deprecated` ghi phiên bản bắt đầu bị deprecated. `forRemoval = true` là ý định loại bỏ trong tương lai, không nói rõ chính xác bản nào sẽ xóa.
5. **`Since` không bảo đảm tính phù hợp với bài toán.** Cần xem thêm ngoại lệ, ngữ nghĩa, trạng thái deprecated, yêu cầu module, khả năng hỗ trợ của nền tảng và API đang được khuyến nghị.

### Các ví dụ có thể tự kiểm tra

| API/thành viên | `Since` | Có trong Java 11? |
| --- | --- | --- |
| `String.isBlank()` | 11 | Có; kiểm tra chuỗi trắng theo `Character.isWhitespace`. |
| `String.strip()` và `String.repeat(int)` | 11 | Có. |
| `Optional.isEmpty()` | 11 | Có; `Optional` là lớp được giới thiệu trước Java 11. |
| `Files.readString(Path)` | 11 | Có; đọc toàn bộ tệp với UTF-8, có thể ném `IOException`. |
| `java.net.http.HttpClient` | 11 | Có; HTTP Client chuẩn được giới thiệu ở Java 11. |
| `String.stripIndent()` | 15 | **Không** có trong Java 11. |
| `List.getFirst()` | 21 | **Không** có trong Java 11. |

Các trường hợp đặc biệt đáng chú ý: lớp `Files` có từ Java 7, còn phương thức `Files.readString(Path)` chỉ được thêm ở Java 11; `String` đã có từ lâu, nhưng `String.isBlank()` mới có từ Java 11. Đó là lý do phải tìm **đúng thành viên và overload**.

Tài liệu kiểm chứng: [String Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html), [Optional Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html), [Files Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html), [HttpClient Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html), [List Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html).

## 4. Thực hành với ví dụ Java 11 biên dịch được

Tạo tệp **ApiSinceDemo.java**:

~~~java
import java.util.Optional;

public class ApiSinceDemo {
    public static void main(String[] args) {
        System.out.println(" \t ".isBlank());
        System.out.println("Java 11".repeat(2));
        System.out.println("  Javadoc  ".strip());
        System.out.println(Optional.<String>empty().isEmpty());
    }
}
~~~

Đây là **chương trình Java hoàn chỉnh**, không cần thư viện ngoài, tệp dữ liệu hoặc mạng. Cả bốn phương thức đều được ghi `Since: 11` trong Javadoc.

Biên dịch và chạy trên JDK 11 hoặc JDK mới hơn có hỗ trợ target Java 11:

~~~bash
javac --release 11 ApiSinceDemo.java
java ApiSinceDemo
~~~

Kết quả chuẩn:

~~~text
true
Java 11Java 11
Javadoc
true
~~~

Lý do: chuỗi chỉ chứa dấu cách và tab nên `isBlank()` là `true`; `repeat(2)` ghép hai bản sao không tự chèn dấu cách; `strip()` bỏ khoảng trắng ở hai đầu; `Optional.empty()` không chứa giá trị nên `isEmpty()` trả `true`.

**Tại sao cần `--release 11`?** Trên JDK mới, `javac --release 11` kiểm tra nguồn và tập API công khai của bản Java 11, đồng thời tạo mã đích tương ứng. Chỉ đặt `-source 11` hoặc `-target 11` không bảo đảm rằng bạn không vô tình gọi phương thức được thêm sau Java 11. Xác nhận thêm bằng chạy thử trên runtime Java 11 nếu đó là môi trường phải hỗ trợ.

Thử một ví dụ **không tương thích Java 11**:

~~~java
public class TooNewFor11 {
    public static void main(String[] args) {
        System.out.println("  hello  ".stripIndent());
    }
}
~~~

`String.stripIndent()` có `Since: 15`. Chạy `javac --release 11 TooNewFor11.java` trên JDK hỗ trợ `--release 11` sẽ báo không tìm được phương thức `stripIndent()` theo bộ API Java 11. Đây là lỗi **tương thích API**, không đơn thuần là cú pháp. Khi cần Java 11, tìm phương án thay thế thực sự đáp ứng cùng **ngữ nghĩa**, không hoán đổi hai phương thức có tên giống nhau một cách máy móc.

## 5. Quy trình ra quyết định thực tế: `Files.readString(Path)`

Bài toán: ứng dụng Java 11 cần đọc toàn bộ một tệp cấu hình nhỏ thành chuỗi. Mở trang `java.nio.file.Files` của Javadoc Java 11, tìm đúng overload `readString(Path)` và ghi lại:

- **Chữ ký:** `public static String readString(Path path) throws IOException`. Đầu vào là `Path`; kết quả là `String`; mã gọi phải xử lý hoặc khai báo `IOException`.
- **Hành vi:** đọc toàn bộ tệp, giải mã UTF-8 khi dùng overload một tham số; có overload `readString(Path, Charset)` khi cần chỉ định charset.
- **Giới hạn:** tài liệu khuyến cáo dùng với tệp có kích thước phù hợp để đọc toàn bộ vào bộ nhớ; đối với tệp lớn, cân nhắc API đọc dòng/stream và đóng tài nguyên đúng cách.
- **Phiên bản:** `Since: 11` ở **phương thức**, dù lớp `Files` đã tồn tại trước đó.
- **Kết luận:** dùng được nếu baseline là Java 11+, tệp phù hợp về kích thước và có xử lý lỗi I/O. Nếu phải chạy Java 8, API này không tồn tại: cần thiết kế lại cách đọc bằng API có trong Java 8.

Đây là cách biến Javadoc thành quyết định kỹ thuật: phải kiểm tra **chữ ký + ngữ nghĩa + ngoại lệ + giới hạn + phiên bản**, không chỉ nhìn tên phương thức hay một dòng `Since`.

## 6. Cập nhật kiến thức mà không lệ thuộc API lỗi thời

- Mở **Javadoc hiện hành** để kiểm tra API có còn được hỗ trợ, bị đánh dấu **Deprecated/For Removal** hay không; đọc gợi ý thay thế và **Release Notes/Migration Guide** khi chuẩn bị nâng JDK. Không mặc định rằng API từng tồn tại sẽ mãi tồn tại.
- Với ứng dụng Java 11, luôn tra Javadoc **Java 11** và thử `javac --release 11`. API mới xuất hiện trong bản hiện hành nhưng có `Since` lớn hơn 11 không đáp ứng mục tiêu tương thích.
- Phân biệt API Java SE công khai như `java.base` và `java.net.http` với API triển khai riêng hoặc package nội bộ như `jdk.internal.*`. Tránh phụ thuộc vào API nội bộ; các tính năng đánh dấu **Preview/Incubating** có điều kiện khác API ổn định.
- `Since: 11` chỉ phiên bản nền tảng, không phải số bản vá `11.0.x`. Thông tin về sửa lỗi, bảo mật và thay đổi của từng bản cập nhật nằm trong release notes tương ứng.
- Với thư viện ngoài JDK, tra **đúng phiên bản thư viện** đang khai báo trong dự án. `@since` ở tài liệu thư viện nói về phiên bản của thư viện theo quy ước tác giả, không tự động nói về Java.
- Một trang tài liệu không hiển thị `Since` hoặc ghi mô tả thiếu rõ ràng không nên trở thành cơ sở để đoán. Hãy tra Javadoc của bản mục tiêu và kiểm chứng bằng mã tối thiểu trước khi đưa vào hệ thống.

## 7. Bài tự kiểm tra kèm đáp án

**Câu 1.** Dự án chạy Java 11 nhưng một ví dụ ở tài liệu JDK 27 sử dụng `List.getFirst()`. Có dùng ngay được không?

**Đáp án:** Không. `List.getFirst()` có `Since: 21`, nên không nằm trong API Java 11. Chọn thao tác tương thích Java 11 và xem kỹ cách xử lý danh sách rỗng; chạy kiểm tra `javac --release 11`.

**Câu 2.** Lớp `Files` có `Since: 1.7`. Có suy ra `Files.readString(Path)` chạy trên Java 8 không?

**Đáp án:** Không. Thành viên `Files.readString(Path)` có `Since: 11`. Cần so sánh phiên bản ở **phương thức**, không chỉ lớp.

**Câu 3.** Nếu một API có `@since 11` và `@Deprecated(since = "25", forRemoval = true)` thì có mâu thuẫn không?

**Đáp án:** Không. Đây là tình huống **giả định**: API được thêm ở Java 11, bắt đầu deprecated ở Java 25, đồng thời có ý định loại bỏ sau đó. Phải đọc lý do và phương án thay thế; `forRemoval` không cam kết bản loại bỏ chính xác.

**Tiêu chí hoàn thành bài:** Với một phương thức chưa biết, bạn tìm được tên đầy đủ, đúng overload, chữ ký, `Parameters/Returns/Throws`, `Since` ở cấp phù hợp, tình trạng deprecated/preview, phiên bản Java cần hỗ trợ, và kiểm chứng được qua `javac --release 11`.

## Tài liệu chính thức

- [Java SE/JDK 27 API Specification (hiện hành ngày 07/11/2026)](https://docs.oracle.com/en/java/javase/27/docs/api/)
- [Java SE/JDK 11 API Specification](https://docs.oracle.com/en/java/javase/11/docs/api/)
- [Đặc tả tài liệu `@since` trong Javadoc](https://docs.oracle.com/en/java/javase/22/docs/specs/javadoc/doc-comment-spec.html)
- [`javac` và tùy chọn `--release`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [`@Deprecated`, `since` và `forRemoval`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Deprecated.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

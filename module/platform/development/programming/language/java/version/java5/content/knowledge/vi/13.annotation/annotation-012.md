# @Deprecated và thông báo vòng đời API

## 1. Vì sao một API cần thông báo ngừng khuyến nghị sử dụng?

Một thư viện có thể đã cung cấp phương thức cho nhiều chương trình khác. Khi có thiết kế tốt hơn, xóa phương thức ngay lập tức làm bên sử dụng khó nâng cấp. Giữ phương thức mà không thông báo lại khiến mã mới tiếp tục phụ thuộc vào lựa chọn cần thay thế.

`@Deprecated` đánh dấu phần tử API **không còn được khuyến nghị sử dụng**. Công cụ biên dịch và IDE có thể cảnh báo khi mã gọi, tham chiếu hoặc ghi đè phần tử đó. API thường vẫn tồn tại và thực thi được trong phiên bản hiện tại; annotation tự nó không thay đổi thân phương thức hay cấm gọi ở lúc chạy. [API Deprecated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html)

Một quy trình thiết kế hợp lý là: cung cấp lựa chọn thay thế → đánh dấu API cần chuyển đổi → giải thích cách chuyển đổi → dành thời gian cho bên sử dụng nâng cấp → cân nhắc xóa theo chính sách phiên bản. Đây là quy trình của thư viện; Java không tự thực hiện các bước phát hành này.

Bài dùng API tự tạo và lệnh dành cho Java 17 trở lên. Không cần gọi một API JDK đã lỗi thời để học cơ chế `@Deprecated`.

## 2. Đọc đúng since và forRemoval

Ví dụ khai báo:

```java
@Deprecated(since = "2.0", forRemoval = false)
public static String greet(String name) {
    return compose(name);
}
```

Đây là phần thân phương thức trong một lớp; chương trình đầy đủ có ở phần sau.

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Deprecated` | Không khuyến nghị tiếp tục sử dụng phần tử |
| `since = "2.0"` | Phiên bản bắt đầu đánh dấu deprecated |
| `forRemoval = false` | Tại thời điểm đánh dấu chưa có ý định cụ thể sẽ xóa |
| `forRemoval = true` | Có ý định xóa trong một phiên bản tương lai |

`since` mặc định là chuỗi rỗng; `forRemoval` mặc định là `false`. Chuỗi `"2.0"` thuộc hệ phiên bản **thư viện đang định nghĩa API**, không mặc nhiên là phiên bản Java. `forRemoval=true` không ấn định ngày hay số phiên bản xóa, còn `false` không phải lời hứa giữ API mãi mãi. [Thuộc tính Deprecated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html)

Phân biệt thêm hai mốc:

- Javadoc `@since 1.0`: API được giới thiệu từ phiên bản 1.0.
- Annotation `@Deprecated(since = "2.0")`: bắt đầu không khuyến nghị dùng từ phiên bản 2.0.

Hai thông tin không mâu thuẫn và có thể cùng xuất hiện trên một phương thức.

## 3. Annotation và Javadoc bổ sung cho nhau

`@Deprecated` là thông tin có cấu trúc cho công cụ. Thẻ Javadoc `@deprecated` là lời giải thích cho người dùng API: từ phiên bản nào nên chuyển đổi, dùng gì thay thế, lý do và khác biệt hành vi cần lưu ý. Nên viết cả hai, đồng thời dùng `{@link ...}` dẫn tới API thay thế khi có. [Đặc tả Javadoc: deprecated](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html#deprecated)

Phần giải thích tốt phải đủ để người đọc hành động. Ví dụ, nếu thay thế phương thức tính tiền làm đổi cách làm tròn, cần nói rõ thay đổi đó; chỉ viết “dùng phương thức mới” là chưa đủ. Không phải API deprecated nào cũng có một thay thế trực tiếp; khi không có, hãy nói rõ giới hạn và hướng xử lý.

Không dựa vào việc thêm một thẻ Javadoc đơn lẻ thay cho annotation. Cặp `@Deprecated` và `@deprecated` thể hiện ý định rõ ràng cho cả người đọc lẫn công cụ.

## 4. Ví dụ đầy đủ: hai mức thông báo

Tạo ba tệp sau trong cùng một thư mục.

### Tệp Greetings.java

```java
/**
 * Creates greeting messages.
 */
public final class Greetings {
    private Greetings() {
    }

    /**
     * Creates a greeting message.
     *
     * @param name recipient name
     * @return a greeting message
     * @since 2.0
     */
    public static String compose(String name) {
        return "Hello, " + name + "!";
    }

    /**
     * Creates a greeting message.
     *
     * @param name recipient name
     * @return a greeting message
     * @since 1.0
     * @deprecated Since 2.0, use {@link #compose(String)}.
     *             The returned message is unchanged.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public static String greet(String name) {
        return compose(name);
    }

    /**
     * Creates a greeting message.
     *
     * @param name recipient name
     * @return a greeting message
     * @since 1.0
     * @deprecated Since 2.1, use {@link #compose(String)}.
     *             This method is intended for removal in a future release.
     *             The returned message is unchanged.
     */
    @Deprecated(since = "2.1", forRemoval = true)
    public static String salutation(String name) {
        return compose(name);
    }
}
```

### Tệp App.java

```java
public class App {
    public static void main(String[] args) {
        System.out.println(Greetings.greet("Lan"));
        System.out.println(Greetings.salutation("Minh"));
    }
}
```

### Tệp AppMigrated.java

```java
public class AppMigrated {
    public static void main(String[] args) {
        System.out.println(Greetings.compose("Lan"));
        System.out.println(Greetings.compose("Minh"));
    }
}
```

Biên dịch để xem cảnh báo chi tiết:

```shell
javac --release 17 -encoding UTF-8 -Xlint:deprecation,removal Greetings.java App.java AppMigrated.java
java App
java AppMigrated
```

`javac` báo cảnh báo nhóm `[deprecation]` cho lời gọi `greet`, nhóm `[removal]` cho lời gọi `salutation`. Tên đường dẫn, số dòng và ngôn ngữ thông báo có thể khác theo môi trường; không cần coi toàn bộ câu chẩn đoán là stdout cố định. Hai lớp gọi được tách khỏi lớp cung cấp API để quan sát cảnh báo trong ngữ cảnh sử dụng thông thường.

Mỗi lần chạy `App` hoặc `AppMigrated` đều in đúng:

```text
Hello, Lan!
Hello, Minh!
```

Trong ví dụ này, các phương thức cũ ủy quyền cho `compose`, nên đầu ra trước và sau chuyển đổi giống nhau. Việc dùng API deprecated vẫn biên dịch thành công vì lệnh chưa yêu cầu coi cảnh báo là lỗi. Cảnh báo xuất hiện khi **biên dịch**; chạy `java App` không tự in lại cảnh báo đó.

### Quan sát tài liệu sinh ra

Sinh tài liệu cho lớp cung cấp API:

```shell
javadoc -quiet -encoding UTF-8 -d docs Greetings.java
```

Mở `docs/Greetings.html`. Kiểm tra phần `greet` và `salutation`: phải thấy nội dung deprecated, liên kết tới `compose(String)` và trạng thái dự kiến xóa của `salutation`. Các tệp HTML do `javadoc` sinh là đầu ra tài liệu; annotation không tự cung cấp lời giải thích nếu người tác giả không viết.

## 5. Cảnh báo, lỗi biên dịch và chính sách kiểm tra

Hai nhóm cảnh báo có mức ý định khác nhau:

| Nhóm | Nguồn thường gặp | Cách hiểu |
| --- | --- | --- |
| `deprecation` | Dùng API deprecated thông thường | Cần xem và lập kế hoạch chuyển đổi |
| `removal` | Dùng API có `forRemoval=true` | Có ý định xóa; cần ưu tiên xử lý phụ thuộc |

Có thể cấu hình kiểm tra nghiêm hơn:

```shell
javac --release 17 -encoding UTF-8 -Xlint:deprecation,removal -Werror Greetings.java App.java
```

Lệnh này kết thúc với lỗi vì `App` gây cảnh báo và `-Werror` làm biên dịch thất bại khi có cảnh báo. Không dùng các tệp `.class` đã có từ lần trước làm bằng chứng lần biên dịch này thành công.

Ngược lại:

```shell
javac --release 17 -encoding UTF-8 -Xlint:deprecation,removal -Werror Greetings.java AppMigrated.java
```

Lệnh biên dịch phiên bản đã chuyển đổi thành công, không in stdout. `-Werror` là chính sách của công cụ/build; nó không biến `@Deprecated` thành lệnh cấm ở JVM. [Tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)

### Không phải mọi nơi dùng đều có cảnh báo giống nhau

Ngôn ngữ có những ngoại lệ, chẳng hạn sử dụng trong cùng lớp ngoài cùng. Cảnh báo deprecation thông thường cũng có thể không xuất hiện khi chỗ sử dụng vốn đã deprecated. Với API dự kiến xóa, việc bản thân chỗ sử dụng cũng deprecated không tự loại cảnh báo removal. Vì vậy “không thấy cảnh báo” không đủ để kết luận một API chưa deprecated. [JLS §9.6.4.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.6)

## 6. Nếu tạm thời chưa chuyển đổi được

Ưu tiên đọc tài liệu và chuyển đổi thật sự. Khi có lý do cụ thể phải giữ một phụ thuộc tạm thời, có thể tắt cảnh báo trong phạm vi nhỏ:

```java
public class TemporaryBridge {
    // Kept temporarily while the integration moves to compose.
    @SuppressWarnings({"deprecation", "removal"})
    public static String message() {
        return Greetings.greet("Lan")
                + " / " + Greetings.salutation("Minh");
    }
}
```

Đây là toàn bộ tệp **TemporaryBridge.java**, phụ thuộc `Greetings.java` ở trên. Có thể kiểm tra:

```shell
javac --release 17 -encoding UTF-8 -Xlint:deprecation,removal -Werror Greetings.java TemporaryBridge.java
```

Lệnh thành công. Annotation chỉ tắt hai nhóm cảnh báo trong phương thức này; không sửa trạng thái của API được gọi. Riêng `@SuppressWarnings("deprecation")` không đồng nghĩa với việc tắt nhóm `removal`. Giữ lời giải thích và kế hoạch chuyển đổi trong quy trình dự án; tránh tắt toàn bộ cảnh báo trên cả mã nguồn chỉ để qua build. [Nhóm cảnh báo javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)

## 7. Đọc metadata khi chạy

`@Deprecated` có retention `RUNTIME`, nên reflection có thể đọc thuộc tính của annotation đã được lưu trên phương thức. Tạo **DeprecationMetadata.java** cạnh `Greetings.java`:

```java
import java.lang.reflect.Method;

public class DeprecationMetadata {
    public static void main(String[] args) throws Exception {
        inspect("greet");
        inspect("salutation");
        inspect("compose");
    }

    private static void inspect(String name) throws Exception {
        Method method =
                Greetings.class.getDeclaredMethod(name, String.class);
        Deprecated marker = method.getAnnotation(Deprecated.class);

        if (marker == null) {
            System.out.println(name + ": active");
            return;
        }

        System.out.println(name
                + ": since=" + marker.since()
                + ", forRemoval=" + marker.forRemoval());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 Greetings.java DeprecationMetadata.java
java DeprecationMetadata
```

Kết quả:

```text
greet: since=2.0, forRemoval=false
salutation: since=2.1, forRemoval=true
compose: active
```

Chương trình đọc annotation trên phương thức được tra cứu, không lấy lời giải thích trong Javadoc. Từ `active` là quy ước in của ví dụ, chỉ nghĩa là không tìm thấy annotation `@Deprecated`; nó không chứng minh API không có vấn đề nào khác. [Metadata Deprecated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html)

## 8. Dùng thông báo vòng đời API để chuyển đổi an toàn

Khi gặp cảnh báo, cần xác định **API nào**, **từ phiên bản nào**, **có dự kiến xóa không**, rồi đọc hướng dẫn thay thế. So sánh hợp đồng hành vi trước khi đổi: tham số, giá trị trả về, xử lý `null`, ngoại lệ, tài nguyên và ảnh hưởng bên ngoài. Sau đó kiểm chứng lại hành vi mà ứng dụng phụ thuộc.

Ví dụ, nếu thư viện đổi API trả một chuỗi ngày tháng thành API trả đối tượng ngày tháng, sửa tên phương thức chưa đủ: bên sử dụng còn phải chọn định dạng. Một thông báo vòng đời hữu ích giúp người dùng nhận ra việc này trước khi nâng cấp.

Những nhầm lẫn cần tránh:

- `since` của `@Deprecated` không phải phiên bản đầu tiên tồn tại của API.
- `forRemoval=true` không tự xóa hay vô hiệu hóa phương thức trong bản hiện tại.
- Tắt cảnh báo không phải là hoàn tất chuyển đổi.
- Không nên suy luận rằng API thay thế luôn cho cùng kết quả; ví dụ trong bài ghi rõ cùng kết quả vì thiết kế đã bảo đảm điều đó.
- Đánh dấu deprecated lên biến cục bộ hoặc tham số không tạo cơ chế cảnh báo dùng API giống phương thức/lớp; không dùng nó làm công cụ kiểm soát việc sử dụng biến. [Phạm vi cảnh báo Deprecated](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html)

### Tự kiểm tra

1. Đổi `greet` thành `forRemoval=true`, biên dịch lại với hai nhóm `-Xlint`. Cảnh báo tại lời gọi đó chuyển sang nhóm nào?
2. Chỉ giữ `@SuppressWarnings("deprecation")` trong `TemporaryBridge`. Lời gọi nào vẫn gây cảnh báo và khiến `-Werror` thất bại?
3. Đổi `since = "2.0"` thành `"2.2"` rồi chạy `DeprecationMetadata`. Vì sao hành vi tạo lời chào không đổi?
4. Viết hướng dẫn chuyển đổi nếu `compose` có hành vi xử lý `null` khác hai phương thức cũ. Thông tin nào phải bổ sung vào Javadoc trước khi khuyến nghị thay thế?

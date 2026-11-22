# Chuyển đổi UUID bằng fromString và toString

## 1. Một định danh, hai cách sử dụng

Khi nhận mã đơn hàng từ đường dẫn HTTP, đọc một trường JSON hoặc nạp dữ liệu cấu hình, chương trình thường nhận **chuỗi văn bản**. Trong phần xử lý Java, ta có thể muốn giữ mã đó dưới dạng `java.util.UUID` để thể hiện rõ đây là định danh UUID.

Hai phương thức nối hai phía:

| Chiều chuyển đổi | Cách gọi | Kết quả |
|---|---|---|
| Chuỗi → UUID | `UUID.fromString(text)` | Một đối tượng chứa giá trị UUID đã được phân tích |
| UUID → chuỗi | `id.toString()` | Biểu diễn văn bản của chính UUID đó |

Đây là chuyển đổi biểu diễn, không phải tạo định danh ngẫu nhiên mới. Gọi `fromString` hai lần với cùng nội dung biểu diễn sẽ thu được hai giá trị UUID bằng nhau; không cần dựa vào việc chúng có cùng tham chiếu đối tượng hay không.

Luồng điển hình là:

```text
Dữ liệu văn bản từ bên ngoài
        → kiểm tra chính sách đầu vào
        → UUID.fromString(...)
        → xử lý bằng kiểu UUID
        → toString()
        → dữ liệu văn bản đưa ra ngoài
```

Bài này dùng các API vẫn được hỗ trợ trên Java hiện hành; chương trình minh họa chạy với Java 17 trở lên.

## 2. Chuỗi UUID chuẩn trông như thế nào?

Ví dụ:

```text
550e8400-e29b-41d4-a716-446655440000
```

Biểu diễn thông dụng có 32 chữ số hệ thập lục phân và 4 dấu gạch nối, tổng cộng 36 ký tự. Năm nhóm có độ dài **8-4-4-4-12**. Mỗi chữ số hệ thập lục phân biểu diễn 4 bit, nên 32 chữ số biểu diễn giá trị 128 bit; dấu gạch nối giúp đọc chứ không thêm bit dữ liệu.

Các chữ `a`–`f` có thể viết hoa hoặc viết thường trong văn bản UUID chuẩn. `UUID.toString()` trong JDK tạo dạng chữ thường. Vì vậy, hai chuỗi khác nhau về chữ hoa/thường có thể cùng biểu diễn một UUID. Định dạng văn bản hiện hành được mô tả trong [RFC 9562, mục 4](https://www.rfc-editor.org/rfc/rfc9562.html#section-4).

Không tự bỏ các số 0 ở đầu từng nhóm. Định danh có nhiều số 0 vẫn cần giữ đầy đủ độ dài khi trao đổi theo dạng chuẩn.

## 3. Dùng fromString để phân tích chuỗi

Đoạn minh họa sau đặt bên trong một phương thức Java và cần import `java.util.UUID`:

```java
String text = "550E8400-E29B-41D4-A716-446655440000";
UUID id = UUID.fromString(text);
```

`fromString` là phương thức `static`: gọi qua tên lớp `UUID`. Nó đọc giá trị đã có trong chuỗi; không hỏi cơ sở dữ liệu, không xác nhận định danh đang thuộc về một bản ghi nào.

Theo hợp đồng API, chuỗi không phù hợp định dạng sẽ gây `IllegalArgumentException`. Tuy nhiên, khi ứng dụng yêu cầu **đúng hình thức 36 ký tự**, nên kiểm tra hình thức đó một cách tường minh. Không đồng nhất “trình phân tích đã chấp nhận” với “đầu vào đã đáp ứng mọi quy định của giao thức”. Một số triển khai OpenJDK có nhánh phân tích cho nhóm ngắn hơn; không dùng sự nới lỏng đó làm định dạng trao đổi của ứng dụng. Xem [API UUID](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html#fromString(java.lang.String)) và [mã nguồn UUID của OpenJDK](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/UUID.java).

Khi bắt lỗi ở ranh giới nhận dữ liệu, hãy xử lý đúng lỗi đầu vào. Đừng bắt mọi `Exception` rồi âm thầm thay bằng UUID mới: như vậy một mã bị gõ sai có thể biến thành một định danh khác, làm mất khả năng tìm lại dữ liệu đúng.

## 4. Dùng toString để xuất một dạng thống nhất

Với `id` ở trên:

```java
String canonical = id.toString();
```

Giá trị của `canonical` là:

```text
550e8400-e29b-41d4-a716-446655440000
```

Có hai phép so sánh khác nhau:

- `UUID.fromString(canonical).equals(id)` kiểm tra **giá trị định danh** có được giữ nguyên hay không.
- `text.equals(canonical)` kiểm tra **chuỗi ký tự** có giữ nguyên từng ký tự hay không.

Trong ví dụ, phép thứ nhất đúng, phép thứ hai sai vì đầu vào dùng chữ hoa. Do đó, chuyển đi rồi chuyển lại bảo toàn UUID, nhưng không nhất thiết bảo toàn cách viết ban đầu.

Một quy tắc hữu ích là giữ kiểu `UUID` trong phần xử lý, rồi dùng `toString()` tại chỗ cần văn bản. Nếu có yêu cầu kiểm toán phải lưu nguyên chuỗi người dùng nhập, giữ chuỗi gốc trong trường riêng; không coi dạng đã chuẩn hóa là bản sao nguyên văn đầu vào.

Không dùng `id1 == id2` để so sánh giá trị UUID. Dùng `id1.equals(id2)` khi đã biết `id1` khác `null`; nếu cả hai có thể vắng, dùng cách so sánh có xử lý `null` phù hợp.

## 5. Đặt chính sách cho đầu vào trước khi chuyển đổi

Một bộ kiểm tra nên trả lời rõ những trường hợp sau:

| Đầu vào | Chính sách trong ví dụ của bài |
|---|---|
| Dạng 8-4-4-4-12, chữ thường | Chấp nhận |
| Dạng 8-4-4-4-12, chữ hoa hoặc pha trộn | Chấp nhận, khi xuất sẽ chuẩn hóa |
| `null`, chuỗi rỗng, chỉ có khoảng trắng | Từ chối |
| Khoảng trắng đầu hoặc cuối | Từ chối |
| Thiếu dấu gạch nối hoặc nhóm quá ngắn | Từ chối |
| Có ký tự ngoài hệ thập lục phân | Từ chối |
| Có ngoặc nhọn hoặc tiền tố `urn:uuid:` | Từ chối vì không thuộc hình thức đầu vào đã chọn |

Một URN UUID là hình thức khác với chuỗi UUID trần. Nếu giao thức của bạn cho phép URN hoặc cho phép bỏ khoảng trắng ở biên, hãy thiết kế bước xử lý riêng và kiểm thử nó. Không tự động xóa mọi ký tự “có vẻ thừa”, vì việc đó khiến dữ liệu sai hình thức bị che khuất.

Có hai chính sách thường gặp cần phân biệt:

1. **Chấp nhận chuẩn, xuất thống nhất:** nhận cả chữ hoa và thường, sau đó xuất qua `toString()`.
2. **Chỉ nhận đúng dạng chữ thường đã chuẩn hóa:** sau khi phân tích hợp lệ, yêu cầu thêm `text.equals(id.toString())`.

Chính sách thứ hai chặt hơn, nên chuỗi chữ hoa có thể bị từ chối dù nó biểu diễn được cùng định danh. Hãy lựa chọn theo hợp đồng giao tiếp thay vì vô tình áp dụng khác nhau ở từng nơi.

## 6. Chương trình đầy đủ: chuyển đổi, chuẩn hóa và kiểm tra hình thức

Lưu vào tệp `UuidTextDemo.java`. Hàm `parseStandard` dưới đây cố ý xử lý cả `null` như lỗi đầu vào bằng `IllegalArgumentException`, để người gọi có một hợp đồng rõ ràng. Đây là chính sách của hàm bao, không phải khẳng định rằng gọi trực tiếp mọi phương thức Java với `null` đều gây loại ngoại lệ này.

```java
import java.util.UUID;
import java.util.regex.Pattern;

public class UuidTextDemo {
    private static final Pattern STANDARD_UUID = Pattern.compile(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    + "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    static UUID parseStandard(String text) {
        if (text == null || !STANDARD_UUID.matcher(text).matches()) {
            throw new IllegalArgumentException(
                    "Expected UUID text in 8-4-4-4-12 form");
        }
        return UUID.fromString(text);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectRejected(String text) {
        try {
            parseStandard(text);
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Invalid text was accepted");
    }

    public static void main(String[] args) {
        String input = "550E8400-E29B-41D4-A716-446655440000";
        UUID id = UUID.fromString(input);
        String canonical = id.toString();
        UUID restored = UUID.fromString(canonical);

        check(id.equals(restored), "UUID round trip failed");
        check(canonical.length() == 36, "Wrong text length");
        check(parseStandard(input).equals(id), "Uppercase rejected");
        check(parseStandard(canonical).equals(id), "Lowercase rejected");

        String[] invalid = {
                null, "", " ",
                "1-1-1-1-1",
                "550e8400e29b41d4a716446655440000",
                "550e8400-e29b-41d4-a716-44665544000g",
                " 550e8400-e29b-41d4-a716-446655440000",
                "550e8400-e29b-41d4-a716-446655440000 ",
                "{550e8400-e29b-41d4-a716-446655440000}",
                "urn:uuid:550e8400-e29b-41d4-a716-446655440000"
        };
        for (String text : invalid) {
            expectRejected(text);
        }

        System.out.println("canonical=" + canonical);
        System.out.println("same UUID=" + id.equals(restored));
        System.out.println("same input text=" + input.equals(canonical));
        System.out.println("strict parse=" + parseStandard(input));
        System.out.println("rejected inputs=" + invalid.length);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 UuidTextDemo.java
java UuidTextDemo
```

Stdout:

```text
canonical=550e8400-e29b-41d4-a716-446655440000
same UUID=true
same input text=false
strict parse=550e8400-e29b-41d4-a716-446655440000
rejected inputs=10
```

### Vì sao biểu thức chính quy viết như vậy?

`[0-9a-fA-F]` giới hạn rõ chữ số ASCII của hệ thập lục phân. Các lượng `{8}`, `{4}`, `{12}` kiểm tra độ dài nhóm, còn bốn dấu `-` kiểm tra vị trí phân cách.

`matcher(text).matches()` yêu cầu **toàn bộ chuỗi** khớp mẫu. Dùng `find()` ở đây sẽ đổi ý nghĩa thành “tìm một đoạn con có hình thức UUID”, có thể chấp nhận một câu có UUID nằm giữa.

Mẫu được biên dịch một lần vào biến `static final`. Sau khi hình thức hợp lệ, `UUID.fromString` thực hiện chuyển đổi giá trị; không tự ghép các nhóm thành số bằng những phép dịch bit khó kiểm tra.

### Các phép kiểm tra chứng minh điều gì?

- UUID sau khi xuất rồi phân tích lại bằng giá trị ban đầu.
- Đầu vào chữ hoa và chữ thường đều được chấp nhận theo chính sách đã chọn.
- Chuỗi sau chuẩn hóa có 36 ký tự.
- Cả 10 đầu vào sai đều bị hàm bao từ chối.
- Một bài kiểm tra không thể đạt chỉ vì một lỗi bất kỳ xảy ra: `expectRejected` chỉ nhận đúng `IllegalArgumentException`.

Các phép kiểm tra dùng `AssertionError` tường minh, nên không cần chạy với `-ea`. Chương trình dùng định danh cố định để stdout có thể đối chiếu chính xác; không có yếu tố ngẫu nhiên.

## 7. Giới hạn của kiểm tra hình thức

Hàm `parseStandard` chỉ kiểm tra hình thức và chuyển sang giá trị UUID. Nó không áp đặt một phiên bản UUID cụ thể, không xác minh nguồn sinh, không chứng minh bản ghi tồn tại và không quyết định người gọi có quyền truy cập bản ghi.

Nếu một trường chỉ cho phép một loại UUID do hệ thống quy định, kiểm tra yêu cầu đó sau khi phân tích và trả lỗi rõ ràng khi không đáp ứng. Không sửa các bit để làm đầu vào “trông như” đúng loại: sửa bit là đổi định danh.

Ví dụ mã đơn hàng được phân tích thành công vẫn có thể không có trong kho dữ liệu. Cần phân biệt lỗi **hình thức mã không hợp lệ** với kết quả **không tìm thấy đơn hàng**, vì cách xử lý và thông báo cho người dùng khác nhau.

## 8. Lỗi thường gặp và cách tự kiểm tra

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi `randomUUID()` thay `fromString(text)` | Tạo định danh mới, mất liên hệ với đầu vào | Chuyển đổi bằng `fromString` |
| So sánh UUID bằng `==` | So tham chiếu đối tượng | Dùng `equals` cho giá trị |
| So chuỗi trước chuẩn hóa | Hai cách viết cùng UUID bị xem là khác | Phân tích thành UUID hoặc chuẩn hóa theo hợp đồng |
| Chỉ kiểm tra `length() == 36` | Chuỗi đủ dài vẫn có ký tự hoặc dấu gạch nối sai | Kiểm tra đầy đủ hình thức |
| Dùng `find()` với mẫu kiểm tra | Chấp nhận UUID nằm trong văn bản khác | Dùng `matches()` |
| Tự động thêm dấu, cắt nhóm hoặc thay ký tự sai | Che lỗi dữ liệu, có thể đổi ý nghĩa định danh | Từ chối đầu vào sai theo chính sách |
| Gọi `toString()` khi biến UUID là `null` | Lỗi do thiếu giá trị | Xử lý trường hợp vắng riêng trước khi xuất |

### Bài thực hành

1. Bổ sung một đầu vào pha trộn chữ hoa/thường và xác nhận kết quả xuất vẫn có cùng dạng chữ thường.
2. Viết hàm chỉ chấp nhận chuỗi đã chuẩn hóa chữ thường; kiểm thử rằng chuỗi chữ hoa bị từ chối, còn chuỗi do `toString()` tạo ra được chấp nhận.
3. Thêm một ký tự xuống dòng vào cuối mã hợp lệ và xác nhận chính sách nghiêm ngặt vẫn từ chối.
4. Mô tả luồng xử lý hai trường hợp: mã sai hình thức và mã đúng hình thức nhưng không có bản ghi. Xác định bước nào là chuyển đổi UUID, bước nào là tra cứu nghiệp vụ.

Điều cần kiểm chứng sau mỗi thay đổi là: giá trị UUID được giữ nguyên khi chuyển hai chiều, còn việc chấp nhận cách viết đầu vào phải tuân theo một chính sách rõ ràng.

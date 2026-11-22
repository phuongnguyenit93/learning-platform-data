# Lựa chọn biểu diễn UUID trong dữ liệu và giao tiếp

Một UUID là một giá trị 128 bit. Cùng giá trị đó có thể xuất hiện dưới dạng đối tượng Java, chuỗi có dấu gạch ngang, 16 byte hoặc một chuỗi mã hóa ngắn hơn. Đổi biểu diễn đúng cách **không tạo UUID mới** và không thay đổi định danh.

Vấn đề cần giải quyết là chọn biểu diễn phù hợp với từng ranh giới: mã Java cần kiểu dữ liệu rõ ràng; JSON và URL cần văn bản; lưu trữ hoặc giao thức nhị phân có thể ưu tiên 16 byte. Bài này giải thích cách lựa chọn và chuyển đổi qua lại mà không mất bit.

Các API UUID cốt lõi xuất hiện từ Java 5 vẫn áp dụng trong Java hiện đại. Chương trình minh họa dùng Java 17 trở lên, có thêm các tiện ích chuẩn hiện đại để mã hóa và in byte.

## 1. Tách giá trị khỏi cách trình bày

Xét UUID:

```text
00112233-4455-4677-8899-aabbccddeeff
```

Bỏ các dấu gạch ngang để nhìn các chữ số hệ 16:

```text
00112233445546778899aabbccddeeff
```

Mỗi cặp chữ số hệ 16 biểu diễn một byte, nên toàn bộ giá trị tương ứng với:

```text
00 11 22 33 44 55 46 77 88 99 AA BB CC DD EE FF
```

Ba cách trình bày trên giữ cùng 128 bit. Chuỗi bỏ gạch ngang là một quy ước riêng cần được hai bên thống nhất; không mặc nhiên coi mọi phương thức phân tích UUID đều chấp nhận nó.

Quy cách UUID dạng văn bản và nhị phân được mô tả trong [RFC 9562, mục 4](https://www.rfc-editor.org/rfc/rfc9562.html#section-4).

### So sánh các lựa chọn

| Biểu diễn | Kích thước phần giá trị | Ưu điểm | Điều phải thống nhất |
| --- | --- | --- | --- |
| `UUID` trong Java | 128 bit có ý nghĩa; bộ nhớ đối tượng còn có chi phí khác | Rõ kiểu, so sánh giá trị thuận tiện | Chuyển đổi ở ranh giới |
| Chuỗi `8-4-4-4-12` | 36 ký tự | Dễ đọc, phổ biến trong API và nhật ký | Dạng chữ, dấu gạch, xử lý đầu vào |
| Nhị phân | 16 byte | Gọn, phù hợp giao thức nhị phân và lưu trữ | Thứ tự byte và độ dài |
| Base64 URL không đệm từ 16 byte | 22 ký tự | Ngắn hơn dạng hệ 16 | Bảng chữ, bỏ đệm, thứ tự byte |
| Hai số `long` | Hai phần 64 bit | Thuận tiện bên trong mã Java | Thứ tự hai phần và cách truyền số |

Kích thước trên không phải kích thước toàn bộ một bản ghi hay đối tượng. Ví dụ, chuỗi UUID chuẩn chứa các ký tự ASCII nên phần nội dung mã hóa UTF-8 là 36 byte, nhưng một đối tượng `String` trong JVM và một trường trong cơ sở dữ liệu còn có chi phí quản lý.

## 2. Giữ kiểu UUID trong mô hình Java

Bên trong ứng dụng, ưu tiên dùng `UUID` cho một trường thực sự là UUID:

```java
// Đoạn khai báo; cần import java.util.UUID.
record Document(UUID id, String title) {
}
```

So với dùng `String` cho mọi thứ, kiểu này giúp phân biệt định danh với tên tệp, tiêu đề và chuỗi đầu vào chưa kiểm tra.

Khi đi ra ranh giới văn bản, dùng `toString()`. Khi nhận văn bản, phân tích thành `UUID` một lần rồi truyền giá trị đã kiểm tra vào logic nghiệp vụ. Constructor hai `long` và các phương thức lấy hai nửa 64 bit cũng cho phép chuyển đổi nhị phân mà không sinh giá trị mới. Xem [UUID API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html).

Đừng dùng `UUID.randomUUID()` để “chuyển đổi” một UUID đã có. Đó là thao tác cấp định danh mới.

## 3. JSON, URL và thông điệp văn bản

Trong JSON, một cách biểu diễn thông dụng là chuỗi:

```json
{
  "documentId": "00112233-4455-4677-8899-aabbccddeeff"
}
```

JSON không có kiểu UUID riêng. Hợp đồng API cần nói trường này là chuỗi biểu diễn UUID, có bắt buộc không và chấp nhận dạng nào.

Không truyền toàn bộ UUID dưới dạng một số JSON. Dù một bên có kiểu số nguyên lớn, bên nhận có thể xử lý số bằng dạng dấu phẩy động với độ chính xác không đủ để giữ nguyên 128 bit. Tách thành hai số 64 bit cũng có thể gặp vấn đề nếu bên nhận không giữ chính xác từng số.

Với URL hoặc nhật ký, dạng có gạch ngang dễ nhận biết và có thể sao chép trực tiếp giữa các công cụ. Các chữ số hệ 16 và dấu gạch ngang không đòi hỏi một bảng mã riêng như biểu diễn nhị phân.

### Chuẩn hóa đầu vào phải là một chính sách rõ ràng

Có thể chọn chính sách:

- Chấp nhận đúng mẫu `8-4-4-4-12`.
- Chấp nhận chữ hệ 16 hoa hoặc thường.
- Sau khi phân tích, xuất lại dạng chuẩn bằng `toString()`.
- Từ chối chuỗi rỗng, khoảng trắng dư, ngoặc nhọn hoặc tiền tố nếu hợp đồng không cho phép.

Nếu muốn tự động bỏ khoảng trắng hoặc chấp nhận nhiều dạng, phải quyết định rõ và kiểm tra nhất quán. Đừng để mỗi tầng tự sửa một kiểu, khiến cùng dữ liệu có nhiều khóa văn bản khác nhau.

Kiểm tra biểu diễn khác với kiểm tra nghiệp vụ. Một UUID đúng cú pháp vẫn có thể không tồn tại, sai loại tài nguyên hoặc không thuộc quyền truy cập của người gọi. Ngược lại, không ép mọi UUID thành phiên bản 4 nếu hợp đồng chấp nhận nhiều phiên bản.

## 4. Nhị phân 16 byte: gọn nhưng phải đúng thứ tự

Chọn quy ước sau cho ví dụ:

1. Ghi nửa 64 bit cao trước.
2. Ghi nửa 64 bit thấp sau.
3. Trong mỗi nửa, ghi byte có trọng số cao trước: big-endian.

Đây là cách xếp byte theo dạng nhị phân UUID chuẩn khi không có giao thức khác quy định. Không dùng thứ tự bản địa của CPU làm hợp đồng dữ liệu trao đổi.

`ByteBuffer` hỗ trợ đọc/ghi số nhiều byte theo thứ tự được cấu hình bằng `order`; ví dụ khai báo `ByteOrder.BIG_ENDIAN` rõ ràng ở cả hai chiều. Xem [ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html#order(java.nio.ByteOrder)).

Một UUID khi ghi theo quy ước này:

```text
UUID: 00112233-4455-4677-8899-aabbccddeeff
Byte: 00 11 22 33 44 55 46 77 88 99 AA BB CC DD EE FF
```

Lưu ý hai lỗi khác nhau:

- `uuid.toString().getBytes(UTF_8)` tạo byte của **văn bản 36 ký tự**, không phải 16 byte giá trị UUID.
- Đọc 16 byte đúng bằng thứ tự byte khác có thể tạo UUID khác dù không mất byte nào.

Dữ liệu GUID từ một số hệ thống có quy ước xếp byte khác. Đặc biệt không suy luận rằng mọi hàm tên “GUID to bytes” đều trả cùng thứ tự như ví dụ. Cần đối chiếu đặc tả của bên gửi, dùng một mẫu có byte bất đối xứng và kiểm tra chuyển đổi ngược.

## 5. Base64 URL: ngắn hơn nhưng là hợp đồng khác

Từ đúng 16 byte UUID, mã hóa Base64 URL không đệm tạo chuỗi 22 ký tự:

```text
ABEiM0RVRneImaq7zN3u_w
```

Đây vẫn là cùng giá trị mẫu; độ ngắn đến từ cách mã hóa, không phải bỏ bớt bit.

Phải mã hóa **16 byte giá trị**, không mã hóa chuỗi UUID 36 ký tự rồi kỳ vọng nhận 22 ký tự. Hai thao tác đó có đầu vào khác nhau.

Trong Java, dùng `Base64.getUrlEncoder().withoutPadding()` và `Base64.getUrlDecoder()` cho quy ước này. Bảng chữ URL dùng `-` và `_` thay cho `+` và `/` của Base64 cơ bản; không dùng bộ giải mã MIME để chấp nhận tùy tiện ký tự dư. Xem [Base64](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.html).

Base64 URL không phải chuỗi UUID dạng chuẩn có gạch ngang. Bên nhận không thể đưa thẳng nó vào `UUID.fromString`; phải giải mã về byte rồi dựng UUID.

Nếu không có nhu cầu rõ ràng về độ dài, dạng chuẩn 36 ký tự thường dễ tích hợp và kiểm tra thủ công hơn. Nếu chọn Base64 URL, ghi chính xác quy ước trong schema hoặc tài liệu giao tiếp.

## 6. Chương trình chuyển đổi đầy đủ

Lưu thành **UuidRepresentationDemo.java**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

public class UuidRepresentationDemo {
    private static final Pattern TEXT = Pattern.compile(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
            + "-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    private static final Pattern COMPACT = Pattern.compile(
            "[A-Za-z0-9_-]{22}");

    static UUID parseText(String text) {
        if (text == null || !TEXT.matcher(text).matches()) {
            throw new IllegalArgumentException("Expected UUID text");
        }
        return UUID.fromString(text);
    }

    static byte[] toBytes(UUID id) {
        Objects.requireNonNull(id, "id");
        return ByteBuffer.allocate(16)
                .order(ByteOrder.BIG_ENDIAN)
                .putLong(id.getMostSignificantBits())
                .putLong(id.getLeastSignificantBits())
                .array();
    }

    static UUID fromBytes(byte[] bytes) {
        if (bytes == null || bytes.length != 16) {
            throw new IllegalArgumentException("Expected exactly 16 bytes");
        }
        ByteBuffer buffer = ByteBuffer.wrap(bytes)
                .order(ByteOrder.BIG_ENDIAN);
        return new UUID(buffer.getLong(), buffer.getLong());
    }

    static String toCompact(UUID id) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(toBytes(id));
    }

    static UUID fromCompact(String text) {
        if (text == null || !COMPACT.matcher(text).matches()) {
            throw new IllegalArgumentException("Expected 22 URL-safe characters");
        }
        UUID id = fromBytes(Base64.getUrlDecoder().decode(text));
        if (!toCompact(id).equals(text)) {
            throw new IllegalArgumentException("Noncanonical encoding");
        }
        return id;
    }

    public static void main(String[] args) {
        UUID id = parseText("00112233-4455-4677-8899-AABBCCDDEEFF");
        byte[] bytes = toBytes(id);
        String compact = toCompact(id);

        System.out.println("text = " + id);
        System.out.println("bytes = " + HexFormat.of().formatHex(bytes));
        System.out.println("byte count = " + bytes.length);
        System.out.println("binary round trip = " + id.equals(fromBytes(bytes)));
        System.out.println("compact = " + compact);
        System.out.println("compact length = " + compact.length());
        System.out.println("compact round trip = "
                + id.equals(fromCompact(compact)));

        try {
            fromBytes(new byte[15]);
        } catch (IllegalArgumentException ex) {
            System.out.println("15-byte input rejected");
        }

        try {
            parseText("00112233445546778899aabbccddeeff");
        } catch (IllegalArgumentException ex) {
            System.out.println("text without hyphens rejected");
        }

        try {
            fromCompact(compact + "==");
        } catch (IllegalArgumentException ex) {
            System.out.println("padded compact input rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidRepresentationDemo.java
java UuidRepresentationDemo
```

Stdout:

```text
text = 00112233-4455-4677-8899-aabbccddeeff
bytes = 00112233445546778899aabbccddeeff
byte count = 16
binary round trip = true
compact = ABEiM0RVRneImaq7zN3u_w
compact length = 22
compact round trip = true
15-byte input rejected
text without hyphens rejected
padded compact input rejected
```

Các kiểm tra từ chối thuộc **chính sách của ví dụ**, không phải tuyên bố rằng mọi giao thức UUID đều cấm dạng khác. Ở đây hợp đồng văn bản yêu cầu dấu gạch ngang và hợp đồng compact không nhận ký tự đệm.

Việc mã hóa lại trong `fromCompact` bảo đảm chỉ chấp nhận đúng một cách viết theo encoder đã chọn. Độ dài và bảng chữ hợp lệ chưa thay thế được yêu cầu biểu diễn chuẩn duy nhất nếu ứng dụng dùng văn bản làm khóa, đường dẫn hoặc đầu vào ký.

## 7. Lựa chọn lưu trữ trong cơ sở dữ liệu

Không quyết định kiểu cột chỉ từ việc Java in UUID thành chuỗi.

### Kiểu UUID bản địa khi hệ quản trị hỗ trợ

Ví dụ PostgreSQL có kiểu `uuid` chuyên biệt để lưu giá trị UUID. Nó có thể nhận UUID được tạo ngoài cơ sở dữ liệu, không bắt buộc UUID phải do cơ sở dữ liệu sinh. Xem [PostgreSQL UUID Type](https://www.postgresql.org/docs/current/datatype-uuid.html).

Một khai báo bảng minh họa riêng cho PostgreSQL:

```sql
CREATE TABLE document (
    id uuid PRIMARY KEY,
    title text NOT NULL
);
```

Kiểu `uuid` của SQL không phải cú pháp dùng nguyên xi cho mọi hệ quản trị. Cách ánh xạ qua JDBC hoặc ORM phụ thuộc driver, dialect và cấu hình; cần kiểm tra chuyển đổi hai chiều với môi trường thật.

### Cột nhị phân 16 byte

Khi dùng cột nhị phân, cần thống nhất codec với tất cả chương trình đọc/ghi. Độ dài đúng là cần thiết nhưng chưa đủ: một bên đảo nhóm byte sẽ lưu giá trị khác với bên còn lại.

Chẳng hạn MySQL có `UUID_TO_BIN` và `BIN_TO_UUID`; tham số hoán đổi của chúng làm thay đổi bố trí byte và phải được dùng tương ứng khi chuyển ngược. Không bật hoán đổi vì nghĩ đó là tùy chọn “UUID nhanh hơn” cho mọi phiên bản. Xem [MySQL UUID_TO_BIN](https://dev.mysql.com/doc/refman/8.4/en/miscellaneous-functions.html#function_uuid-to-bin).

Nếu dùng codec Java ở bài này, kiểm tra rằng thao tác SQL và lớp truy cập dữ liệu giữ đúng cùng thứ tự 16 byte.

### Cột văn bản

Chuỗi 36 ký tự thuận tiện khi xem và xuất dữ liệu thủ công. Đổi lại, phần giá trị dài hơn 16 byte nhị phân và phải thống nhất cách viết.

Nếu chọn văn bản, quy định dạng chuẩn tại nơi ghi, xử lý hoa/thường nhất quán và giữ ràng buộc duy nhất. Việc cơ sở dữ liệu so văn bản theo một collation nào đó không nên trở thành cơ chế duy nhất để sửa dữ liệu đầu vào không thống nhất.

### Biểu diễn và đặc tính chỉ mục là hai quyết định liên quan nhưng khác nhau

Đổi UUID ngẫu nhiên từ chuỗi sang 16 byte không biến nó thành dãy tăng dần theo thời gian. Kiểu cột có thể giảm dung lượng nhưng không thay đổi thuật toán tạo UUID.

Khi tối ưu chỉ mục, cần đo với dữ liệu và truy vấn thật. Tránh tuyên bố một biểu diễn luôn nhanh hơn trong mọi trường hợp. Kích thước khóa, cách chèn, chỉ mục, driver và khối lượng dữ liệu đều ảnh hưởng.

## 8. Hợp đồng chuyển đổi nên ghi những gì?

Một mô tả đủ cụ thể cho giao tiếp nhị phân có thể là:

```text
documentId:
  value: UUID 128 bit
  wire representation: exactly 16 bytes
  order: most-significant 64 bits, then least-significant 64 bits
  byte order inside each part: big-endian
  missing value: not allowed
```

Với dạng compact, bổ sung:

```text
text encoding: Base64 URL-safe of those exact 16 bytes
padding: omitted
length: 22 characters
case: significant
```

Không chuyển chữ hoa thành chữ thường cho Base64 URL: khác với chữ số hệ 16, hoa/thường trong bảng chữ Base64 mang giá trị khác nhau.

Khi đổi biểu diễn của một API đã được sử dụng, phải coi đó là thay đổi hợp đồng. Đừng đổi từ chuỗi 36 ký tự sang 22 ký tự trong cùng trường mà không phối hợp với bên nhận, kiểm thử dữ liệu cũ và có chiến lược tương thích.

## 9. Lỗi phổ biến

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Gọi `randomUUID` khi chuyển đổi | Đổi định danh | Bảo toàn đủ 128 bit |
| Dùng byte của chuỗi làm nhị phân UUID | 36 byte văn bản thay vì 16 byte giá trị | Mã hóa đúng hai nửa 64 bit |
| Chỉ giữ một `long` | Mất 64 bit | Giữ cả hai phần hoặc đủ 16 byte |
| Dùng `hashCode` làm biểu diễn ngắn | Mất thông tin và có va chạm | Dùng codec bảo toàn giá trị |
| Mã hóa Base64 từ văn bản UUID | Độ dài và dữ liệu khác hợp đồng | Mã hóa từ 16 byte |
| Đọc/ghi khác thứ tự byte | Định danh biến thành giá trị khác | Thống nhất codec và mẫu kiểm thử |
| Viết thường chuỗi Base64 | Thay đổi giá trị mã hóa | Giữ nguyên hoa/thường |
| Coi UUID toàn 0 là null | Lẫn giá trị có mặt với dữ liệu vắng | Quy định null riêng |
| Đổi định dạng mà không đổi hợp đồng | Bên nhận không phân tích được | Quản lý tương thích tại ranh giới |

## 10. Thực hành

1. Dùng mẫu UUID của chương trình và xác nhận chuỗi hệ 16 32 ký tự khớp đúng 16 byte theo thứ tự.
2. Đổi một chiều sang little-endian để quan sát kiểm tra chuyển đổi ngược thất bại; sau đó khôi phục cùng quy ước hai chiều.
3. Thiết kế trường JSON cho UUID có thể thiếu: phân biệt trường không có, giá trị null và UUID toàn 0.
4. Chọn biểu diễn cho một API công khai cần dễ đọc và một giao thức nội bộ đã có schema nhị phân. Giải thích lựa chọn theo nhu cầu.
5. Nếu dữ liệu nằm trong cơ sở dữ liệu, kiểm tra một lần Java -> lưu -> đọc -> Java bằng UUID có các byte khác nhau, không chỉ mẫu toàn 0.

Một biểu diễn tốt giữ nguyên định danh, có quy tắc chuyển đổi rõ ràng và phù hợp công cụ ở hai phía của ranh giới dữ liệu.

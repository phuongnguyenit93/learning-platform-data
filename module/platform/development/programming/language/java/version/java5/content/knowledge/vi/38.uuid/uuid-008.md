# Phân biệt định danh UUID với bí mật xác thực

## 1. UUID trả lời “đối tượng nào?”, xác thực trả lời “ai đang gọi?”

Giả sử một API nhận yêu cầu:

```http
GET /documents/9a111111-1111-4111-8111-111111111111
```

UUID trong đường dẫn giúp máy chủ tìm tài liệu. Nó không tự cho biết người gửi yêu cầu là ai, tài liệu có thuộc về người đó không hoặc người đó được phép thực hiện thao tác gì.

Ba trách nhiệm cần tách rõ:

| Trách nhiệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Định danh | Đang nói đến đối tượng nào? | UUID của tài liệu |
| Xác thực (authentication) | Danh tính người gọi đã được kiểm chứng chưa? | Phiên đăng nhập được máy chủ xác minh |
| Phân quyền (authorization) | Danh tính đó được làm gì với đối tượng này? | Chỉ chủ sở hữu được đọc tài liệu |

Một bí mật xác thực hoặc mã truy cập có thể được dùng làm bằng chứng theo một giao thức đã định. UUID của tài nguyên thường là thông tin tham chiếu có thể xuất hiện ở giao diện, URL hoặc dữ liệu trao đổi. Tự lấy mã tài nguyên làm bằng chứng truy cập sẽ trộn các trách nhiệm này.

Ví dụ dễ hiểu: số hồ sơ giúp nhân viên tìm đúng hồ sơ; việc biết số hồ sơ không chứng minh người hỏi là chủ hồ sơ.

## 2. Tính ít trùng và tính khó đoán không đồng nghĩa với được cấp quyền

Có ba tính chất khác nhau:

- Ít trùng: giảm khả năng hai đối tượng vô tình nhận cùng mã.
- Khó đoán: người chưa biết mã khó dự đoán được một giá trị hợp lệ.
- Được cấp quyền: máy chủ cho phép một chủ thể thực hiện một hành động theo chính sách.

UUID ngẫu nhiên có thể giúp hạn chế việc dò tuần tự mã tài nguyên. Tuy nhiên, nếu một mã bị lộ qua ảnh chụp, dữ liệu xuất, thông báo hoặc URL được chuyển tiếp, người biết mã vẫn phải bị chặn khi không có quyền.

Đó là lý do thay khóa số tăng dần bằng UUID không tự khắc phục lỗi truy cập trực tiếp đối tượng thiếu kiểm quyền, thường gọi là IDOR. [OWASP IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) yêu cầu kiểm quyền truy cập ngay cả khi định danh khó đoán.

Không cần đoán hoặc phá thuật toán UUID để khai thác lỗi này: chỉ cần có sẵn một mã của người khác rồi gửi yêu cầu tới API thiếu kiểm quyền.

## 3. Vì sao “UUID 128 bit” chưa mô tả một bí mật xác thực?

`UUID.randomUUID()` trong Java tạo UUIDv4 bằng nguồn giả ngẫu nhiên mạnh về mật mã. Vì thế nói “mọi UUID đều dễ đoán” cũng sai. Xem [Java UUID API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html#randomUUID()).

Tuy nhiên, UUIDv4 có các bit version/variant cố định, nên phần ngẫu nhiên là 122 bit chứ không phải toàn bộ 128 bit. Các version khác có thể chứa thành phần khác, chẳng hạn thời gian trong UUIDv7. Không được nhìn kích thước chuỗi rồi mặc định mọi UUID có cùng lượng ngẫu nhiên hoặc cùng mục đích. Bố cục hiện hành được mô tả trong [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html).

Quan trọng hơn, kiểu `UUID` tự nó không cung cấp:

- Thời điểm hết hạn.
- Phạm vi hành động được phép.
- Liên kết với tài khoản hoặc phiên cụ thể.
- Thu hồi, xoay vòng hoặc vô hiệu hóa sau khi dùng.
- Quy tắc lưu và xử lý khi giá trị bị lộ.

Một chuỗi được tạo ngẫu nhiên tốt vẫn cần đầy đủ hợp đồng sử dụng nếu nó mang quyền truy cập. Độ khó đoán là một phần của thiết kế, không thay thế thiết kế đó.

Đổi UUID tài nguyên sang Base64, bỏ dấu gạch nối hoặc băm UUID đã công khai không tạo ra một bí mật mới. Các phép biến đổi định dạng hoặc tính toán từ đầu vào công khai không làm cho thông tin đó chỉ còn người hợp lệ biết được.

## 4. Một token dạng bearer cần được đối xử như quyền đang mang theo

Với token dạng bearer, bên giữ giá trị token có thể sử dụng quyền gắn với nó trong phạm vi giao thức. Vì vậy nếu hệ thống cố ý cho phép “ai có đường dẫn này thì được đọc”, phần khó đoán trong đường dẫn thực chất là bí mật mang quyền truy cập, dù người lập trình đặt tên biến là `id`.

Ví dụ hợp lệ về mặt mô hình là liên kết chia sẻ có giới hạn hoặc liên kết đặt lại mật khẩu. Chúng cần thiết kế riêng: bí mật độc lập với mã tài nguyên, mục đích rõ ràng, thời hạn, khả năng thu hồi và giới hạn sử dụng phù hợp. Đừng dùng lại UUID tài nguyên đang được hiển thị công khai cho chức năng này.

Cũng không kết luận một giá trị không thể làm bí mật chỉ vì nhìn giống UUID. Vai trò do giao thức quyết định. Nếu một hệ thống dùng giá trị đó như token mang quyền, phải đánh giá nó như token và bảo vệ nó tương ứng; hình dạng chuỗi không tự tạo hoặc xóa quyền.

Đối với đặt lại mật khẩu, token cần được sinh bằng nguồn ngẫu nhiên phù hợp, đủ dài, liên kết đúng tài khoản, hết hạn và vô hiệu sau khi sử dụng. Xem [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 5. Cách xử lý đúng một yêu cầu dùng UUID tài nguyên

Với tài liệu riêng tư, luồng khái niệm là:

```text
Nhận UUID tài liệu
    ↓
Xác minh phiên hoặc thông tin xác thực của người gọi
    ↓
Lấy danh tính từ ngữ cảnh xác thực đáng tin cậy
    ↓
Tìm tài liệu trong phạm vi người gọi được phép truy cập
    ↓
Thực hiện hành động đã được cho phép
```

Không lấy `ownerId` do trình duyệt gửi rồi coi đó là danh tính đã xác thực. Một người có thể sửa cả `documentId` lẫn `ownerId` trong yêu cầu. Thông tin về tài khoản đang gọi phải đến từ kết quả xác thực phía máy chủ.

Trong hệ thống nhiều đơn vị dùng chung, còn cần ranh giới đơn vị (tenant). Hai tài khoản có cùng tên hiển thị hoặc cùng mã cục bộ ở hai tenant không được tự động truy cập dữ liệu của nhau.

Chính sách cụ thể tùy nghiệp vụ: chủ sở hữu, người cùng nhóm, vai trò quản trị hoặc quyền được chia sẻ. Điều quan trọng là thực thi chính sách trên tài nguyên và hành động, không suy quyền từ việc parser đã đọc thành công UUID.

## 6. Minh chứng bằng Java 17+: mã tài nguyên và quyền là hai dữ liệu riêng

Chương trình sau dùng bộ nhớ để minh họa quy tắc “chỉ chủ sở hữu trong cùng tenant được đọc”. Nó không triển khai đăng nhập hay một hệ thống token hoàn chỉnh.

`VerifiedUser` đóng vai trò kết quả đã xác thực. Trong ứng dụng thật, không tạo nó trực tiếp từ các trường tài khoản mà người gọi tự khai báo. Phần sinh token ở cuối độc lập với UUID tài liệu, chỉ minh họa cách tạo dữ liệu bí mật ngẫu nhiên.

Lưu thành `UuidAndSecretDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

public class UuidAndSecretDemo {
    record VerifiedUser(String tenant, String userId) {}
    record Document(UUID id, String tenant, String ownerId) {}

    private static final SecureRandom RANDOM = new SecureRandom();

    public static void main(String[] args) {
        UUID ownId = UUID.fromString("9a111111-1111-4111-8111-111111111111");
        UUID otherOwnerId = UUID.fromString("9a222222-2222-4222-8222-222222222222");
        UUID otherTenantId = UUID.fromString("9a333333-3333-4333-8333-333333333333");

        Map<UUID, Document> documents = Map.of(
                ownId, new Document(ownId, "north", "alice"),
                otherOwnerId, new Document(otherOwnerId, "north", "bob"),
                otherTenantId, new Document(otherTenantId, "south", "alice"));

        // In this demo, this stands for an already authenticated identity.
        VerifiedUser alice = new VerifiedUser("north", "alice");
        System.out.println("own=" + findVisible(documents, ownId, alice).isPresent());
        System.out.println("otherOwner="
                + findVisible(documents, otherOwnerId, alice).isPresent());
        System.out.println("otherTenant="
                + findVisible(documents, otherTenantId, alice).isPresent());
        System.out.println("anonymous="
                + findVisible(documents, ownId, null).isPresent());

        byte[] tokenBytes = new byte[32];
        RANDOM.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tokenBytes);
        System.out.println("tokenChars=" + token.length());
        System.out.println("decodedBytes=" + Base64.getUrlDecoder().decode(token).length);
    }

    private static Optional<Document> findVisible(
            Map<UUID, Document> documents, UUID id, VerifiedUser user) {
        if (user == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(documents.get(id))
                .filter(document -> document.tenant().equals(user.tenant()))
                .filter(document -> document.ownerId().equals(user.userId()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidAndSecretDemo.java
java UuidAndSecretDemo
```

Stdout:

```text
own=true
otherOwner=false
otherTenant=false
anonymous=false
tokenChars=43
decodedBytes=32
```

Kết quả cho thấy:

1. Alice đọc được tài liệu của mình trong tenant `north`.
2. Biết đúng UUID của tài liệu thuộc Bob không làm Alice có quyền đọc.
3. Tài liệu cùng `ownerId = alice` nhưng thuộc tenant `south` cũng bị loại.
4. Không có danh tính đã xác thực thì hàm không trả tài liệu.
5. Token lấy 32 byte ngẫu nhiên độc lập, mã hóa Base64 URL-safe không padding thành 43 ký tự; giải mã lại có 32 byte.

Token thật không được in ra stdout. Hai dòng cuối chỉ in độ dài nên kết quả vẫn ổn định giữa các lần chạy, dù giá trị token thay đổi. Việc độ dài đúng không phải phép kiểm chứng toàn bộ độ an toàn của một giao thức token.

`SecureRandom.nextBytes()` cung cấp dữ liệu từ nguồn ngẫu nhiên mạnh về mật mã; không tự đặt seed dự đoán được như thời gian hệ thống để tạo “tính ngẫu nhiên”. Xem [Java SecureRandom API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html).

Với cơ sở dữ liệu thực tế, có thể đưa phạm vi quyền vào truy vấn hoặc một tầng phân quyền tập trung. Ví dụ trong bài chỉ lọc ba bản ghi để làm rõ nguyên tắc. Cần áp dụng kiểm quyền cho cả sửa, xóa và xuất dữ liệu, không chỉ thao tác đọc.

## 7. Những phần còn thiếu để token trở thành một chức năng thực tế

Hàm sinh token chỉ tạo giá trị. Chức năng đặt lại mật khẩu hoặc chia sẻ tệp còn cần xử lý vòng đời:

| Thành phần | Vai trò |
| --- | --- |
| Bản ghi liên kết | Gắn token với đối tượng, người dùng và mục đích cụ thể |
| Hết hạn | Giới hạn thời gian sử dụng |
| Phạm vi quyền | Không cho token của một hành động dùng sang hành động khác |
| Trạng thái dùng/thu hồi | Chặn sử dụng lại khi chính sách yêu cầu |
| Kiểm tra nguyên tử | Hai yêu cầu đồng thời không cùng tiêu thụ thành công token dùng một lần |
| Giới hạn thử | Giảm lạm dụng và việc thử hàng loạt |
| Truyền và lưu an toàn | Giảm khả năng bí mật bị lộ |

Đây là phần việc của thiết kế dịch vụ, không thể hoàn thành chỉ bằng cách đổi `UUID.randomUUID()` sang `SecureRandom`.

Với token ngẫu nhiên đủ mạnh và chỉ cần kiểm chứng, có thể lưu giá trị dẫn xuất để đối chiếu thay vì lưu token thô; phải chọn cách làm phù hợp với hệ thống và mô hình đe dọa. Không sao chép cách lưu token ngẫu nhiên sang mật khẩu do người dùng tự chọn: mật khẩu có tính chất khác và cần cơ chế lưu mật khẩu chuyên dụng.

Dùng thư viện hoặc nền tảng xác thực được duy trì cho đăng nhập, phiên và giao thức chuẩn. Ví dụ trong bài chỉ tách hai vai trò để tránh dùng định danh tài nguyên như quyền truy cập.

## 8. Hậu quả của việc coi nhầm định danh là bí mật

Nếu mã tài nguyên vô tình trở thành khóa mở dữ liệu, những nơi đang xử lý nó như thông tin bình thường có thể làm lộ quyền:

- URL được sao chép vào hội thoại hỗ trợ.
- Access log, công cụ phân tích hoặc bản chụp màn hình.
- Dữ liệu tài nguyên xuất cho đối tác.
- Liên kết bị chuyển tiếp ra ngoài nhóm được phép.

Ngược lại, mã tài nguyên bình thường không nhất thiết phải giữ kín bằng mọi giá. Có thể cho người dùng biết mã để đối chiếu hoặc tìm kiếm, rồi kiểm quyền đầy đủ ở máy chủ. Đối với dữ liệu nhạy cảm, định danh và siêu dữ liệu vẫn có thể cần hạn chế công khai theo yêu cầu riêng; “không phải mật khẩu” không có nghĩa là được ghi mọi nơi.

Khi một giá trị mang vai trò bí mật, tránh ghi toàn bộ nó vào log; truyền qua kênh bảo vệ và xử lý rò rỉ bằng thu hồi hoặc vô hiệu hóa theo vòng đời. Nếu một đường dẫn chứa token bắt buộc phải được gửi cho người dùng, cần xem cả log, lịch sử trình duyệt và các điểm có thể truyền tiếp URL trong thiết kế tính năng.

## 9. Tự kiểm tra

1. Nếu đổi khóa số tăng dần sang UUID nhưng vẫn trả bất kỳ tài liệu nào tìm được theo mã, lỗi truy cập trái phép đã được giải quyết chưa?
2. Một UUID có đúng version 4 và variant IETF có chứng minh người gửi là chủ tài liệu không?
3. Có được tin `ownerId` do người gọi gửi để xác định tài khoản đang đăng nhập không?
4. Một token ngẫu nhiên 32 byte có tự biết khi nào phải hết hạn không?
5. Nếu ai có một liên kết đều được đọc tệp, phần bí mật của liên kết đang đóng vai trò gì?

Đáp án: (1) chưa, còn thiếu kiểm quyền; (2) không, đó chỉ là thông tin cấu trúc định danh; (3) không, cần ngữ cảnh xác thực phía máy chủ; (4) không, dịch vụ phải áp dụng vòng đời; (5) token mang quyền truy cập, cần được bảo vệ theo vai trò đó.

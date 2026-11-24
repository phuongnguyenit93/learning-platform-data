# Sinh mã dự phòng cho khôi phục tài khoản

Chủ đề **Backup code generation** thuộc chương **Backup Code Recovery**.

Mã dự phòng là bí mật được cấp trước để người dùng có thể thực hiện một bước xác thực hoặc khôi phục khi không còn dùng được phương tiện thông thường. Chúng có thể giúp xử lý việc mất ứng dụng MFA, passkey hoặc thiết bị xác thực, tùy chính sách của sản phẩm. Người giữ một mã hợp lệ có thể nhận được quyền nhạy cảm, nên việc sinh mã phải được xem là phát hành thông tin xác thực.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, sinh mã dự phòng cần kết hợp độ khó đoán, cấp quyền phát hành, lưu trữ an toàn, vòng đời dùng một lần và ràng buộc với luồng khôi phục. Một chuỗi trông ngẫu nhiên chưa đủ nếu ai có session cũ cũng được cấp bộ mã mới hoặc bộ cũ vẫn được chấp nhận sau khi đã thay thế.

## 1. Xác định quyền mà mã dự phòng đại diện

Trước khi chọn độ dài hay cách định dạng, cần trả lời: mã dùng để làm gì?

| Cách sử dụng | Ý nghĩa | Điều cần quy định |
| --- | --- | --- |
| Thay một bước MFA trong lần đăng nhập | Mã đóng vai trò bằng chứng dự phòng | Các điều kiện đăng nhập khác vẫn phải được kiểm tra theo chính sách |
| Bắt đầu luồng thay yếu tố đã mất | Mã cho phép chuyển sang một tiến trình khôi phục | Cần giới hạn quyền, thời hạn luồng và hành động được phép |
| Khôi phục tài khoản không dùng mật khẩu | Mã có thể là một bằng chứng quan trọng của quyền khôi phục | Không tự giả định còn một mật khẩu để làm lớp bảo vệ khác |
| Phát hành lại bộ mã dự phòng | Đây là thao tác tạo thêm bí mật cho tương lai | Không mặc nhiên cho phép chỉ vì một mã cũ vừa được chấp nhận |

Một mã dự phòng không tự đủ cho mọi hành động. Sản phẩm phải quy định rõ mã có thể thay yếu tố nào, có cần bằng chứng khác hay không và khi nào cần đánh giá rủi ro bổ sung.

Mã là bí mật mang quyền: người có mã có thể là chủ tài khoản, người được chủ tài khoản chia sẻ nhầm hoặc kẻ đã đánh cắp bản lưu. Mã đúng chứng minh bên yêu cầu biết bí mật đã được cấp, không tự chứng minh danh tính pháp lý. Mã cũng có thể bị lừa lấy theo thời gian thực, nên không được coi là cơ chế chống phishing chỉ vì nó chỉ dùng một lần.

## 2. Đặc tính của một bộ mã được sinh đúng

Một thiết kế cần giữ được những thuộc tính sau:

1. Mỗi mã có đủ độ khó đoán cho mức quyền được cấp và tổng số lần thử có thể xảy ra.
2. Mã được sinh bằng nguồn ngẫu nhiên phù hợp cho mật mã, không từ dữ liệu dễ đoán của tài khoản.
3. Các mã trong một bộ không trùng nhau và không suy ra được từ mã khác đã biết.
4. Mã được gắn với tài khoản, bộ phát hành và trạng thái phía máy chủ.
5. Mỗi mã chỉ được tiêu thụ một lần theo cơ chế nguyên tử.
6. Người dùng nhận mã qua một luồng được bảo vệ; log và hệ thống phân tích không nhận bản rõ.
7. Phát hành thay thế làm rõ bộ nào đang hoạt động và bộ nào đã bị thu hồi.

Một mã dự phòng thường sống lâu hơn OTP gửi qua SMS hoặc email. Điều này giúp người dùng lưu để dùng khi cần, nhưng cũng khiến bản sao bị lộ có giá trị trong thời gian dài. Thời hạn hết hiệu lực và điều kiện thu hồi phải là quyết định rõ ràng của sản phẩm.

## 3. Chọn entropy, độ dài và số lượng mã

Nếu mỗi ký tự được chọn đều, độc lập theo giả định mật mã, từ một bảng có `A` ký tự và mã có `L` ký tự, số giá trị có thể có là:

```text
N = A^L
H = log2(N) = L * log2(A)
```

`H` là số bit entropy của phần bí mật. Bảng minh họa:

| Dạng phần bí mật | Không gian giá trị | Entropy xấp xỉ |
| --- | --- | --- |
| 6 chữ số thập phân | 10^6 | 19,9 bit |
| 8 chữ số thập phân | 10^8 | 26,6 bit |
| 12 ký tự chọn đều từ 32 ký tự | 32^12 | 60 bit |
| 20 ký tự chọn đều từ 32 ký tự | 32^20 | 100 bit |
| 16 byte ngẫu nhiên đều | 2^128 | 128 bit |

Đây là so sánh để thiết kế, không phải một mức tối thiểu chung cho mọi sản phẩm. Không thể chỉ đếm ký tự hiển thị: dấu gạch nối, tiền tố, số thứ tự và checksum không tạo thêm entropy bí mật nếu chúng được suy ra công khai.

### Có nhiều mã hợp lệ thì rủi ro thay đổi thế nào?

Giả sử một tài khoản còn `m` mã hợp lệ khác nhau, mỗi mã được chọn đều trong không gian `N`, và kẻ tấn công có tối đa `q` phép đoán. Một cận trên đơn giản là:

```text
P(đoán trúng ít nhất một mã) <= min(1, q * m / N)
```

Với thiết kế minh họa có 10 mã, mỗi mã 100 bit và một triệu phép đoán:

```text
P <= 1.000.000 * 10 / 2^100
  xấp xỉ 7,9 * 10^-24
```

Công thức chỉ xét đoán mã dưới các giả định trên. Nó không bao phủ việc đánh cắp mã, lỗi cấp quyền, lộ trình duyệt hoặc bỏ qua kiểm tra trạng thái. Dịch vụ vẫn phải giới hạn thử để chống lạm dụng và bảo vệ tài nguyên.

Mười mã 100 bit không có nghĩa một lần khôi phục được bảo vệ bằng 1.000 bit: kẻ tấn công thường chỉ cần trúng một mã. Càng nhiều mã hoạt động, càng nhiều bí mật có thể bị lộ và càng nhiều giá trị được chấp nhận.

## 4. Định dạng dễ đọc mà giữ nguyên độ khó đoán

Một lựa chọn minh họa là bảng 32 ký tự:

```text
0123456789ABCDEFGHJKMNPQRSTVWXYZ
```

Bảng này bỏ một số chữ dễ gây nhầm khi đọc. Sinh 20 ký tự rồi chia thành năm nhóm bốn ký tự:

```text
9G2M-7Q4R-D6NX-3V8T-K5WP
```

Chuỗi trên chỉ là ví dụ trong tài liệu, không được dùng làm mã thật. Sau khi bỏ dấu phân nhóm, phần bí mật có 20 ký tự, tương ứng 100 bit nếu được sinh đúng.

Quy tắc chuẩn hóa cần được định nghĩa trước và áp dụng giống nhau khi sinh verifier và khi xác minh. Ví dụ:

- Chấp nhận chữ cái ASCII hoa hoặc thường và chuyển về dạng hoa theo quy tắc ổn định.
- Bỏ dấu gạch nối ASCII và khoảng trắng ASCII nếu giao diện có chủ đích hỗ trợ.
- Sau chuẩn hóa, yêu cầu đúng 20 ký tự thuộc bảng đã chọn.
- Không tự thay mọi ký tự Unicode có hình dạng giống nhau thành một ký tự hợp lệ.
- Không cắt bớt một chuỗi quá dài để làm nó khớp độ dài cần thiết.

Có thể chọn ánh xạ các ký tự dễ nhầm nếu sản phẩm cần, nhưng phải thiết kế và kiểm thử quy tắc đó rõ ràng. Không âm thầm thêm nhiều cách diễn giải khác nhau ở các endpoint.

Nếu thêm checksum để phát hiện lỗi nhập, cần tách phần checksum khỏi phần bí mật trong phép tính entropy. Checksum giúp phát hiện sai sót; nó không chứng minh người nhập có quyền sở hữu tài khoản.

## 5. Nguồn ngẫu nhiên và ví dụ Java

Không sinh mã bằng thời gian hiện tại, số điện thoại, ID tài khoản, bộ đếm hoặc hàm băm của các giá trị đó. Không dùng bộ sinh dành cho mô phỏng như `java.util.Random` hay `Math.random()` để phát hành bí mật khôi phục.

Ví dụ sau dùng `SecureRandom` để sinh từng ký tự đều trong bảng 32 ký tự. Nó chỉ minh họa phần sinh và định dạng trong bộ nhớ; chưa bao gồm cấp quyền, lưu trữ, kích hoạt hoặc xác minh mã.

```java
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class BackupCodeGenerator {
    private static final char[] ALPHABET =
            "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();
    private static final int SECRET_LENGTH = 20;
    private static final int MAX_BATCH_SIZE = 20;

    private final SecureRandom random = new SecureRandom();

    public List<String> generate(int count) {
        if (count < 1 || count > MAX_BATCH_SIZE) {
            throw new IllegalArgumentException("Invalid batch size");
        }

        Set<String> canonicalCodes = new LinkedHashSet<>();
        while (canonicalCodes.size() < count) {
            char[] value = new char[SECRET_LENGTH];
            for (int i = 0; i < value.length; i++) {
                value[i] = ALPHABET[random.nextInt(ALPHABET.length)];
            }
            canonicalCodes.add(new String(value));
        }

        List<String> displayCodes = new ArrayList<>(count);
        for (String canonical : canonicalCodes) {
            StringBuilder formatted = new StringBuilder();
            for (int i = 0; i < canonical.length(); i++) {
                if (i > 0 && i % 4 == 0) {
                    formatted.append('-');
                }
                formatted.append(canonical.charAt(i));
            }
            displayCodes.add(formatted.toString());
        }
        return displayCodes;
    }
}
```

`nextInt(bound)` cung cấp cách chọn chỉ số phù hợp cho bảng ký tự. Với những cách tự ánh xạ số ngẫu nhiên sang bảng có kích thước khác, cần tránh modulo bias: một số ký tự có thể được chọn thường xuyên hơn nếu phép ánh xạ không đều.

Không tự đặt seed của bộ sinh bằng một giá trị dễ đoán. Không dùng một seed cố định trong môi trường thật để tiện kiểm thử. Cũng không rút ngắn tùy ý UUID hoặc một chuỗi có cấu trúc rồi mặc định phần còn lại có đủ entropy.

`LinkedHashSet` loại mã trùng trong bộ đang sinh. Nếu trùng, vòng lặp sinh thêm một mã mới. Với 10 mã trong không gian `2^100`, xác suất trùng ngẫu nhiên đã rất nhỏ, nhưng việc giữ ràng buộc không trùng vẫn giúp mô hình dữ liệu rõ ràng.

Giới hạn 20 mã trong ví dụ chỉ là giới hạn của thành phần minh họa. Nó không thay thế giới hạn số bộ đang hoạt động hoặc tốc độ phát hành theo tài khoản. Các chuỗi Java được tạo ra cũng không có bảo đảm xóa sạch khỏi bộ nhớ chỉ bằng cách bỏ tham chiếu; cần giảm thời gian tồn tại và tránh sao chép chúng sang log hoặc công cụ chẩn đoán.

## 6. Lưu verifier thay cho bản rõ

Sau khi chuyển mã cho người dùng, hệ thống thường chỉ cần kiểm tra mã được nhập có khớp một mã hợp lệ hay không. Không cần lưu bản rõ lâu dài để hiển thị lại.

Với mã được sinh ngẫu nhiên có entropy cao, một digest mật mã thích hợp có thể dùng làm verifier. Cần ràng buộc tài khoản và bộ mã để tránh dùng lẫn ngữ cảnh. Một lựa chọn có khóa là:

```text
verifier = HMAC(
  serverKey,
  encode("backup-code:v1", tenantId, accountId, batchId, canonicalCode)
)
```

`encode` phải không mơ hồ, chẳng hạn mã hóa có độ dài từng trường. Khóa HMAC cần được quản lý tách khỏi dữ liệu verifier, có phân quyền và định danh phiên bản. Nếu không dùng HMAC, cần chọn thiết kế digest phù hợp với entropy thực tế và mô hình đe dọa; một hash nhanh không biến mã ngắn, dễ đoán thành bí mật mạnh.

Khi dữ liệu chỉ có verifier, kẻ đọc cơ sở dữ liệu không nhận ngay danh sách mã rõ. Tuy vậy, vẫn phải bảo vệ cơ sở dữ liệu, trạng thái tiêu thụ và khóa của hệ thống. Kẻ có quyền sửa trạng thái hoặc bỏ qua xác minh có thể gây hậu quả mà việc băm mã không giải quyết được.

Nếu dùng HMAC, việc luân chuyển khóa cần được lập kế hoạch. Không thể tính lại toàn bộ verifier dưới khóa mới chỉ từ verifier cũ khi không còn mã rõ. Có thể cần giữ khóa cũ cho những bộ còn hiệu lực trong thời gian được phép hoặc yêu cầu phát hành bộ thay thế theo quy trình. Không hạ toàn bộ bộ mã xuống trạng thái lỗi để rồi bỏ qua kiểm tra.

Với bộ nhỏ, ứng dụng có thể kiểm tra các verifier trong phạm vi tài khoản bằng primitive so sánh phù hợp. Nếu dùng chỉ mục để tra cứu, vẫn cần kiểm soát phạm vi và phản hồi để tránh lộ thông tin không cần thiết. Không cung cấp API công khai cho biết một mã có thuộc tài khoản nào hay không.

## 7. Mô hình dữ liệu của bộ mã

Một mô hình khái niệm có thể gồm:

```text
BackupCodeBatch
  batchId
  accountId
  formatVersion
  verifierKeyId
  status
  createdAt
  expiresAt
  activatedAt
  revokedAt
  authorizedByRef
  baseActiveBatchVersion

BackupCode
  codeId
  batchId
  verifier
  status
  usedAt
  consumedByFlowId

BackupCodeIssuance
  issuanceId
  accountId
  browserBindingRef
  requestId
  requestFingerprint
  pendingBatchId
  expiresAt
  state
```

Trạng thái bộ mã có thể là `PENDING`, `ACTIVE`, `REVOKED` hoặc `EXPIRED`. Trạng thái từng mã có thể là `UNUSED` hoặc `USED`; một mã chưa dùng trong bộ đã thu hồi vẫn không hợp lệ.

Hệ thống phải kiểm tra đồng thời trạng thái bộ và trạng thái mã. Chỉ kiểm tra `usedAt` trống sẽ vô tình chấp nhận lại mã chưa dùng từ một bộ cũ.

`codeId`, `batchId` hoặc số thứ tự của mã là định danh quản lý, không phải phần entropy bí mật nếu chúng công khai. Không dùng ID bản ghi làm chính mã dự phòng.

## 8. Cấp quyền phát hành mã

Endpoint sinh hoặc thay bộ mã là một endpoint nhạy cảm. Một session có thể đủ để đọc nội dung thông thường nhưng chưa chắc đủ để phát hành bí mật cho những lần khôi phục sau.

Trước khi sinh, máy chủ cần kiểm tra quyền hiện tại, độ mới của lần xác thực, mức bảo đảm phù hợp, chống giả mạo request và tín hiệu rủi ro. Có thể yêu cầu xác thực lại bằng yếu tố còn hoạt động hoặc một quyền khôi phục được cấp rõ cho thao tác phát hành mã.

Không để client tự chọn tài khoản đích hoặc khai rằng MFA đã hoàn tất. Máy chủ lấy tài khoản và thông tin xác thực từ ngữ cảnh đáng tin cậy. Không cho một token chỉ được đặt lại mật khẩu tự sinh bộ mã dự phòng nếu phạm vi đó chưa được phép.

Đặc biệt, một mã dự phòng dùng để vượt qua một lần đăng nhập không nên mặc nhiên cho phép phát ngay vô hạn mã mới. Nếu sản phẩm cho phép phát lại sau khôi phục, cần quy định rõ điều kiện, bằng chứng còn lại và kiểm soát session cho nhánh đó.

Giới hạn phát hành theo tài khoản, luồng và nguồn yêu cầu giúp chống lạm dụng. Nhưng không được thu hồi bộ mã đang hoạt động chỉ vì có một yêu cầu phát hành chưa được cấp quyền; người lạ có thể lợi dụng điều đó để làm mất đường dự phòng của nạn nhân.

## 9. Phát hành, trình bày và kích hoạt nhất quán

Có hai cách phổ biến cần phân biệt:

| Cách phát hành | Thời điểm bộ mới có hiệu lực | Vấn đề cần xử lý |
| --- | --- | --- |
| Kích hoạt ngay khi tạo | Trong transaction phát hành | Nếu phản hồi bị mất, người dùng có thể không nhận được bộ vừa thay thế |
| Tạo bộ chờ rồi xác nhận kích hoạt | Sau thao tác xác nhận có cấp quyền | Phải bảo vệ bộ chờ, thời hạn và thao tác chuyển đổi |

Thiết kế minh họa trong bài dùng cách thứ hai: tối đa một bộ `ACTIVE` và một bộ `PENDING` cho mỗi tài khoản, với quy tắc thay thế rõ ràng.

### Giai đoạn tạo bộ chờ

1. Xác minh quyền phát hành và tạo ngữ cảnh có thời hạn.
2. Sinh các mã trong bộ nhớ, tạo verifier và lưu bộ `PENDING` cùng các bản ghi mã.
3. Gắn bộ chờ với tài khoản, trình duyệt, quyền phát hành và phiên bản bộ đang hoạt động.
4. Chỉ sau khi lưu thành công, trả mã rõ qua phản hồi được bảo vệ cho đúng ngữ cảnh.
5. Không chấp nhận các mã trong bộ chờ ở endpoint khôi phục.

Chỉ lưu verifier lâu dài. Nếu mô hình chỉ lưu verifier và phản hồi chứa mã bị mất, máy chủ không thể hiển thị lại chính bộ mã đó. Cần hướng dẫn tạo lại bộ chờ qua một thao tác còn được cấp quyền, rồi thu hồi bộ chờ cũ. Không sinh một bộ khác âm thầm dưới cùng một khóa idempotency và giả vờ đó là phản hồi cũ.

Nếu sản phẩm cần gửi lại đúng nội dung trong một khoảng retry, phải thiết kế riêng việc lưu tạm bản rõ đã mã hóa, ràng buộc truy cập và xóa sau hạn ngắn. Khi đó không còn đúng nếu nói hệ thống tuyệt đối chỉ giữ verifier trong mọi thời điểm. Cần diễn đạt đúng mô hình đang dùng.

### Giai đoạn kích hoạt

Sau khi người dùng chủ động xác nhận đã lưu bộ mã, máy chủ thực hiện một cập nhật nhất quán:

```text
Trong cùng ranh giới cập nhật của tài khoản:
  kiểm tra lại quyền, thời hạn và ràng buộc
  kiểm tra đúng bộ PENDING hiện hành
  kiểm tra phiên bản bộ ACTIVE và trạng thái an ninh liên quan
  thu hồi bộ ACTIVE cũ nếu có
  chuyển bộ PENDING thành ACTIVE
  tăng phiên bản quản lý bộ mã
  kết thúc quyền phát hành theo chính sách
  lưu sự kiện thông báo và kết quả idempotent
  commit
```

Nút “đã lưu” thể hiện ý định người dùng; nó không chứng minh chắc chắn họ đã lưu ở một nơi an toàn. Giao diện cần hướng dẫn rõ rằng bộ cũ sẽ hết hiệu lực sau khi kích hoạt bộ mới.

Nếu hai tab cùng thao tác, chỉ bộ chờ hiện hành và đúng phiên bản được kích hoạt. Nếu transaction thất bại, không để cả hai bộ cùng hoạt động ngoài chính sách hoặc khiến dữ liệu ở trạng thái nửa chuyển đổi.

Giữ bộ cũ trong thời gian chờ phù hợp với trường hợp thay thế thông thường. Nếu bộ cũ đã bị lộ, việc thu hồi có thể cần thực hiện sớm bằng một hành động đã được cấp quyền riêng; không mặc định kéo dài hiệu lực của bộ bị lộ đến lúc người dùng xác nhận bộ mới.

## 10. Hiển thị và lưu mã ở phía người dùng

Trang trình bày mã là nơi có toàn bộ bí mật của bộ phát hành. Cần bảo vệ đường truyền, hạn chế cache, tránh script hoặc công cụ theo dõi không cần thiết và không đưa mã vào URL, lịch sử truy cập hoặc sự kiện phân tích.

Có thể cho sao chép, in hoặc tải xuống trong ngữ cảnh được cấp quyền. Nội dung nên ghi tên dịch vụ, tài khoản ở mức phù hợp, ngày phát hành, nhãn bộ và hướng dẫn mỗi mã dùng một lần. Phần ghi chú không được tạo cảm giác mã là một mật khẩu dùng lại lâu dài.

Hướng dẫn người dùng lưu ở nơi vẫn truy cập được khi phương tiện chính bị mất, ví dụ một bản in được cất an toàn hoặc kho bí mật có đường truy cập phù hợp. Không chỉ lưu trên chính điện thoại duy nhất mà mã đang dùng để dự phòng. Cũng cần xét nguy cơ chung nếu cùng một kho chứa mật khẩu, mã dự phòng và phương tiện để khôi phục kho đó.

Không yêu cầu gửi ảnh bộ mã cho hỗ trợ. Không tự động gửi toàn bộ mã qua email như một bước hoàn tất mặc định. Nếu cung cấp nút sao chép, nên làm rõ clipboard có thể bị ứng dụng hoặc thiết bị khác tiếp cận tùy môi trường.

Khi người dùng quay lại trang quản lý sau này, hiển thị số mã còn lại và tùy chọn phát lại theo quyền phù hợp thay vì danh sách mã cũ. Có thể hiển thị metadata không chứa bí mật; không cần tiết lộ một phần mã đủ gây rủi ro chỉ để người dùng nhận diện bộ.

## 11. Dùng một lần là thuộc tính của máy chủ

Bản thân chuỗi được sinh không tự biết rằng nó đã dùng. Thuộc tính dùng một lần phải được thực thi bằng trạng thái phía máy chủ.

Một luồng tiêu thụ cần kiểm tra tài khoản, bộ mã đang hoạt động, thời hạn, trạng thái chưa dùng, ngân sách thử và mục đích được phép. Sau khi khớp, việc đánh dấu mã đã dùng và cấp kết quả có phạm vi phải được phối hợp nguyên tử.

```text
UNUSED trong bộ ACTIVE
    -> xác minh thành công và tiêu thụ nguyên tử
    -> USED, gắn với luồng đã nhận quyền
```

Không làm theo mẫu “đọc thấy chưa dùng, cấp session, rồi cập nhật đã dùng” bằng các thao tác rời rạc. Hai request đồng thời có thể cùng vượt qua bước đọc.

Retry của cùng một thao tác có thể trả lại kết quả ràng buộc với cùng luồng mà không tiêu thụ thêm mã. Cùng khóa idempotency nhưng thay nội dung phải bị từ chối. Một mã đã dùng không được phục hồi thành chưa dùng chỉ vì luồng sau đó bị gián đoạn; cần thiết kế khả năng tiếp tục luồng hoặc dùng phương án khác theo chính sách.

Mã dự phòng nên dẫn tới mức quyền đã xác định ở đầu bài. Nếu chỉ cho phép đăng ký lại MFA, không tạo ngay session có đầy đủ quyền quản trị. Sau khi thực sự thay thông tin xác thực, áp dụng chính sách thu hồi session và các quyền khôi phục còn lại theo rủi ro.

## 12. Thu hồi, hết hạn và quan sát vận hành

Một bộ mã cần bị thu hồi khi được thay thế hoặc khi có quyết định bảo vệ do nghi lộ. Việc hết hạn có thể theo chính sách sản phẩm; phải cân bằng nguy cơ bí mật tồn tại lâu với khả năng người dùng cần mã vào lúc khẩn cấp.

Khi người dùng báo mất bản lưu nhưng chưa chứng minh quyền, hệ thống không nên tự làm mọi mã vô hiệu. Khi báo cáo đã được xử lý bằng quyền phù hợp, cần hướng dẫn tạo bộ mới và kiểm tra những thông tin xác thực khác có thể cùng bị lộ.

Các sự kiện hữu ích gồm bộ được tạo, bộ chờ bị hủy, bộ được kích hoạt, bộ cũ bị thu hồi, mã được tiêu thụ và yêu cầu bị từ chối. Không ghi nội dung mã, response chứa mã hoặc dữ liệu đủ dùng làm quyền khôi phục vào log.

Metric tổng hợp có thể dùng nhãn hữu hạn như kết quả và loại thao tác. Không đặt mã, email hoặc ID tài khoản vào nhãn metric. Khi cần điều tra theo tài khoản, dùng sự kiện được phân quyền và thời hạn lưu giữ thích hợp.

Thông báo thay bộ mã qua kênh đã đăng ký giúp phát hiện phát hành trái phép. Thông báo cần mô tả hành động và thời điểm, không chứa chính bộ mã. Một yêu cầu nhập sai mã chưa được xác minh không nên tự làm mọi session của nạn nhân bị thu hồi.

## 13. Ví dụ xuyên suốt

Hà có MFA đang hoạt động và muốn chuẩn bị đường dự phòng trước khi đổi điện thoại. Giả sử chính sách cho phép phát một bộ 10 mã, mỗi mã có 20 ký tự bí mật từ bảng 32 ký tự ở trên.

1. Hà mở trang quản lý an ninh và thực hiện xác thực lại theo chính sách. Máy chủ cấp quyền chỉ cho phát hành bộ mã dự phòng.
2. Thành phần sinh mã dùng `SecureRandom`, tạo 10 giá trị không trùng nhau và định dạng thành các nhóm dễ đọc.
3. Máy chủ tạo bộ `B2` ở trạng thái `PENDING`, lưu verifier và ngữ cảnh phát hành. Bộ đang hoạt động `B1` vẫn giữ hiệu lực trong quá trình thay thế thông thường.
4. Hà nhận mã qua trang được bảo vệ và lưu ngoài chiếc điện thoại sắp thay. Không có mã rõ trong log hoặc email thông báo.
5. Hà xác nhận kích hoạt. Máy chủ kiểm tra quyền, bộ chờ và phiên bản, rồi chuyển `B2` thành `ACTIVE` đồng thời thu hồi `B1`.
6. Vài tháng sau, Hà mất ứng dụng MFA. Một mã chưa dùng của `B2` được kiểm tra cùng những điều kiện khác của luồng và bị tiêu thụ một lần.
7. Retry hợp lệ tiếp tục cùng kết quả khôi phục. Việc phát lại bộ mã sau đó vẫn phải qua quyền thích hợp, không tự được phép chỉ vì đã nhập một mã đúng.

Nếu Hà không nhận được phản hồi ở bước 4 trong thiết kế chỉ lưu verifier, hệ thống không thể đọc lại 10 mã của `B2`. Hà cần một thao tác được cấp quyền để tạo bộ chờ mới; `B1` chưa bị thu hồi chỉ vì phản hồi trình bày bộ chờ bị mất.

Nếu bộ `B1` đã bị nghi lộ, chính sách thu hồi khẩn cấp phải được xử lý rõ ràng bằng quyền phù hợp, thay vì mặc định giữ nó hoạt động theo quy trình thay thế thông thường.

## 14. Những tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Thành phần sinh nhận số lượng ngoài giới hạn | Từ chối, không cấp bộ mã ngoài chính sách |
| Hai giá trị ngẫu nhiên trùng trong cùng bộ | Sinh lại để bộ không có mã trùng |
| Người dùng nhập chữ thường hoặc dấu phân nhóm được hỗ trợ | Chuẩn hóa nhất quán với lúc tạo verifier |
| Chuỗi có ký tự không được phép hoặc quá dài | Từ chối, không cắt hoặc diễn giải tùy tiện |
| Session không đáp ứng quyền phát hành | Không sinh hoặc hiển thị bí mật mới |
| Response chứa bộ chờ bị mất | Có cách tạo lại có cấp quyền; không giả vờ đọc được mã từ verifier |
| Bộ còn PENDING được dùng ở endpoint khôi phục | Không được chấp nhận |
| Hai tab kích hoạt các bộ khác nhau | Chỉ chuyển đổi theo bộ hiện hành và đúng phiên bản |
| Kích hoạt bộ mới thất bại giữa chừng | Không để các bộ ở trạng thái nửa chuyển đổi |
| Mã chưa dùng thuộc bộ đã thu hồi | Không được chấp nhận |
| Hai request cùng tiêu thụ một mã | Chỉ một kết quả tiêu thụ hợp lệ theo thiết kế |
| Mã đúng được dùng cho hành động ngoài phạm vi | Không cấp quyền ngoài chính sách |
| Luân chuyển khóa HMAC | Các bộ còn hiệu lực được xử lý theo kế hoạch, không bỏ qua xác minh |
| Log, telemetry hoặc email nhận kết quả phát hành | Không chứa danh sách mã rõ |

Sinh mã dự phòng cần được nối với toàn bộ quá trình phát hành thông tin xác thực: nguồn ngẫu nhiên, định dạng, verifier, quyền tạo bộ, chuyển trạng thái và tiêu thụ dùng một lần. Các phần này cùng quyết định liệu bộ mã có giúp người dùng khôi phục tài khoản mà vẫn giới hạn được nguy cơ chiếm đoạt hay không.

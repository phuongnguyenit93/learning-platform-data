# Digital signature

## 1. Chữ ký số xác minh điều gì?

Digital signature, hay chữ ký số, sử dụng một cặp khóa: private key để ký và public key tương ứng để kiểm tra chữ ký. Ở mức cơ chế, người xác minh đưa đúng dữ liệu, chữ ký và public key vào thuật toán để kiểm tra mối liên hệ mật mã giữa chúng.

```text
Private key + dữ liệu cần ký → chữ ký
Public key + dữ liệu + chữ ký → kết quả kiểm tra mật mã
```

Chữ ký giúp phát hiện thay đổi dữ liệu và hỗ trợ xác thực nguồn khi public key đã được gắn với một bên phát hành theo mô hình tin cậy phù hợp. NIST Digital Signature Standard mô tả các mục tiêu liên quan đến phát hiện sửa đổi và xác thực bên ký. [NIST: FIPS 186-5](https://csrc.nist.gov/pubs/fips/186-5/final).

Trong thiết kế yêu cầu bảo mật, một kết quả `verify=true` chưa đủ để chấp nhận một tài liệu. Hệ thống còn phải biết public key có thuộc bên được tin không, dữ liệu có đúng mục đích không, có hết hiệu lực hoặc bị thu hồi không và đối tượng nhận có được phép dùng kết quả đó cho thao tác hiện tại không.

Ví dụ trong nền tảng học tập, một chứng chỉ có chữ ký hợp lệ bằng khóa do người gửi tự tạo không chứng minh nó được trường học phát hành. Ngay cả chứng chỉ thật của khóa học A cũng không tự cho phép đổi nó thành bằng chứng hoàn thành khóa học B.

Bài học tập trung vào những yêu cầu biến chữ ký số thành một cơ chế có ý nghĩa trong hệ thống: dữ liệu được ký, nguồn tin cậy của khóa, quy trình xác minh, vòng đời và bằng chứng nghiệm thu.

## 2. Phân biệt chữ ký, mã hóa, hash và MAC

| Cơ chế | Thuộc tính chính cần xét | Khác chữ ký số ở điểm nào? |
| --- | --- | --- |
| Hash mật mã | Digest của dữ liệu theo thuật toán | Ai cũng có thể tính lại; digest không được bảo vệ không xác thực nguồn |
| MAC/HMAC | Toàn vẹn và xác thực giữa các bên giữ khóa chung | Bên được quyền kiểm tra bằng khóa chung cũng có thể tạo MAC |
| Chữ ký số | Kiểm tra dữ liệu bằng public key tương ứng với private key đã ký | Có thể phân phối quyền xác minh mà không phân phối quyền ký |
| Mã hóa | Giữ bí mật theo mô hình khóa và cơ chế được chọn | Không tự có cùng hợp đồng xác thực chữ ký |
| Base64/hex | Biểu diễn byte dưới dạng text | Không giữ bí mật và không tạo bằng chứng nguồn |

Một tài liệu chỉ được ký vẫn có thể đọc nội dung. Nếu chứng chỉ hoặc báo cáo chứa thông tin riêng, cần quyết định riêng về công bố dữ liệu, quyền truy cập hoặc lớp mã hóa phù hợp. Chữ ký không phải phương pháp che nội dung.

Không mô tả ký số như “mã hóa bằng private key” rồi dùng API mã hóa tổng quát để tự thực hiện. Chữ ký là một scheme có quy tắc và tham số riêng; phải sử dụng implementation của scheme đã được duyệt.

Chữ ký cũng không tự chứng minh một cá nhân đã hiểu hoặc chấp thuận nội dung. Kết luận về ý nghĩa người ký cần dựa vào việc kiểm soát khóa, nhận diện chủ thể, quyền ký và flow xác nhận của ứng dụng. Không biến một kết quả mật mã thành bảo đảm tuyệt đối ngoài ranh giới đó.

## 3. Tình huống: chứng chỉ hoàn thành khóa học

Một nền tảng muốn cấp chứng chỉ mà nhà tuyển dụng hoặc đối tác có thể kiểm tra. Tài liệu dữ liệu của tình huống có thể gồm:

```json
{
  "schemaVersion": 1,
  "purpose": "learning-certificate",
  "issuer": "https://issuer.learning.example",
  "certificateId": "certificate-8f12",
  "learnerRef": "learner-73a4",
  "courseId": "course-java-foundation",
  "issuedAt": "2026-11-27T00:00:00Z",
  "validUntil": "2027-11-27T00:00:00Z"
}
```

Các định danh và thời điểm trên chỉ minh họa contract của bài học. Chúng không mô tả chứng chỉ đã được hệ thống thật phát hành.

### 3.1. Tài sản và rủi ro cần đặc tả

| Rủi ro | Yêu cầu cần hình thành |
| --- | --- |
| Sửa người học hoặc khóa học trên chứng chỉ | Các trường có ý nghĩa nghiệp vụ phải nằm trong phần được xác thực |
| Tự tạo key rồi gửi cùng một chứng chỉ giả | Public key phải có nguồn tin cậy độc lập với tài liệu chưa được xác minh |
| Dùng dữ liệu có chữ ký ở một mục đích khác | Kiểm tra type/purpose/profile và domain nghiệp vụ |
| Đưa lại chứng chỉ đã bị thu hồi | Kiểm tra trạng thái theo policy, không chỉ kiểm tra chữ ký |
| Chiếm được dịch vụ ký | Giới hạn quyền ký, scope khóa, audit và kế hoạch compromise |
| Kết quả hiển thị khác đối tượng đã kiểm tra | Renderer/consumer dùng đúng dữ liệu đã được xác minh |
| Public verification làm lộ dữ liệu học viên | Tập trường công bố và quyền tra cứu có policy riêng |

Một mã QR trên PDF có thể dẫn tới trang tra cứu, nhưng không tự ký các byte PDF. Ngược lại, ký payload dữ liệu không tự bảo đảm mọi dòng trên một PDF được trình bày tương ứng với payload đó. Phải chốt chính xác artifact nào được xác minh và người dùng được hướng dẫn hiểu kết quả nào.

## 4. Thiết kế signing contract trước khi gọi API ký

Một signing profile cần mô tả ít nhất:

```text
Loại tài liệu và mục đích sử dụng
Format/version và giới hạn kích thước
Những field hoặc byte nằm trong phạm vi chữ ký
Quy tắc serialize/canonicalize
Thuật toán, tham số và provider được duyệt
Nguồn chọn signing key và verification key
Issuer, audience/context nếu use case cần
Thời điểm, hiệu lực, trạng thái và chống replay nếu cần
Hành vi lỗi và tập kết quả được công bố
```

Không cung cấp một endpoint có đặc quyền ký mọi byte do client gửi rồi coi đó là dịch vụ cấp chứng chỉ. Quyền dùng private key phải đi sau command nghiệp vụ: người học đủ điều kiện, khóa học đúng, bên phát hành đúng và actor được phép cấp.

Với chứng chỉ mẫu, service nên tạo dữ liệu đã kiểm tra từ nguồn có thẩm quyền rồi serialize theo profile. Client có thể yêu cầu cấp chứng chỉ của một trường hợp được phép; nó không được tự chọn nội dung `issuer`, key hoặc điều kiện hoàn thành rồi đưa cho signer đóng dấu.

Một use case ký dữ liệu tùy ý có thể hợp lệ trong sản phẩm khác, nhưng có mô hình quyền và mục tiêu khác. Không tái sử dụng khóa cấp chứng chỉ làm khóa ký tổng quát để tiện tích hợp.

## 5. Ký byte nào và xác minh byte nào?

Thuật toán chữ ký xử lý dữ liệu theo đầu vào đã định. Nếu hai bên dựng byte khác nhau từ một object tưởng là giống nhau, kết quả kiểm tra có thể thất bại hoặc lớp ứng dụng có thể hiểu nội dung khác nhau.

### 5.1. Hai lựa chọn contract cần phân biệt

| Lựa chọn | Hợp đồng | Điểm cần kiểm soát |
| --- | --- | --- |
| Ký đúng byte payload | Giữ và xác minh nguyên payload đã ký | Không parse rồi serialize lại trước verify nếu cách đó đổi byte |
| Ký biểu diễn canonical | Hai bên tạo cùng biểu diễn chuẩn trước thao tác mật mã | Quy tắc canonicalization, parser và miền dữ liệu phải thống nhất |

JSON có thể khác thứ tự property, khoảng trắng hoặc biểu diễn số mà trông vẫn tương đương ở một tầng ứng dụng. RFC 8785 định nghĩa JSON Canonicalization Scheme cho một biểu diễn JSON ổn định theo các ràng buộc cụ thể. Nó không phải chỉ là thao tác “sort key rồi stringify” tùy runtime. [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html).

Nếu chọn JCS, dùng implementation phù hợp và test vector, đồng thời tuân miền dữ liệu của scheme. Không tự chuẩn hóa Unicode, ngày giờ hoặc số theo một quy tắc riêng mà phía kia không biết. Canonicalization xác định biểu diễn; nó không thay validation nghiệp vụ của field.

### 5.2. Metadata quan trọng phải được xác thực

Format chữ ký có thể có phần metadata được bảo vệ và phần không được bảo vệ. Signing profile phải chỉ rõ nơi đặt thông tin như algorithm/profile và key identifier; không mặc định mọi field trong envelope đều nằm trong chữ ký.

JWS là một ví dụ định dạng biểu diễn nội dung được bảo vệ bằng chữ ký hoặc MAC, với các quy tắc về protected header và signing input. Nếu mục tiêu là chữ ký bất đối xứng, phải chọn đúng nhóm thuật toán và thư viện theo profile, không cho client đổi sang MAC hoặc bỏ chữ ký. [RFC 7515: JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html).

Không tự ghép byte JWS bằng một helper ký tổng quát rồi công bố đã triển khai chuẩn. Tương tự, PDF, XML hoặc container khác có quy tắc riêng cần thư viện và validation tương ứng.

### 5.3. Dữ liệu được sử dụng phải là dữ liệu đã được kiểm tra

Sau khi verify, không lấy một bản object khác do request gửi để hiển thị hoặc cấp quyền. Với detached signature, cần ràng buộc đúng payload và chữ ký của cùng artifact, không cho một trường `displayPayload` chưa được bảo vệ quyết định nội dung trên màn hình.

Với format có cấu trúc, tránh parser hiểu khác nhau về field lặp, alias, kiểu số hoặc vị trí tham chiếu. Một chữ ký đúng trên một phần tài liệu chưa chắc bảo vệ được phần mà business code thực sự đọc.

## 6. Public key cần nguồn tin cậy độc lập

Một bước verify bằng public key lấy nguyên từ file người gửi chỉ cho biết chữ ký khớp key đó. Nó chưa gắn key với tổ chức phát hành mà hệ thống tin.

Ba mô hình thường cần cân nhắc:

| Mô hình | Nguồn tin cậy | Yêu cầu vận hành |
| --- | --- | --- |
| Registry public key được cấu hình | Mapping issuer–purpose–key đã được duyệt | Phân phối, rotation, thu hồi và bảo vệ quyền sửa registry |
| PKI/X.509 | Trust anchor và quy trình kiểm tra certificate path | Issuer/key usage/hiệu lực, policy và trạng thái thu hồi thích hợp |
| Cơ chế discovery của một giao thức đã chọn | Issuer/endpoint gốc đã được thiết lập tin cậy | HTTPS, allowlist, cache, rotation và giới hạn việc tìm key |

RFC 5280 mô tả profile X.509 và quy trình xác minh certificate path. Một certificate tự ký hoặc một chuỗi gửi kèm tài liệu không mặc định trở thành trust anchor. [RFC 5280: PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html).

### 6.1. `keyId` chỉ là bộ chọn trong một namespace được phép

Nếu envelope có `keyId`, verifier dùng nó để tìm trong tập key đã được chốt theo issuer và mục đích. Không biến `keyId` thành đường dẫn filesystem, câu query tùy ý hoặc URL mạng không giới hạn.

Với header chứa tham chiếu key/certificate bên ngoài, không tự tải từ mọi địa chỉ client gửi. Phải theo cơ chế discovery và network policy đã được duyệt; certificate material được gửi kèm vẫn chỉ là ứng viên cần xác minh trust.

Một key hợp lệ của tenant A không tự có thẩm quyền ký cho tenant B. Registry và payload phải ràng buộc được key với issuer/purpose tương ứng, không chỉ có một danh sách public key dùng được cho mọi tài liệu.

## 7. Ví dụ Java: ký và verify đúng byte bằng Ed25519

Java cung cấp API `Signature` với các bước khởi tạo bằng private/public key, đưa dữ liệu vào `update`, rồi `sign` hoặc `verify`. [Oracle Java 17: Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html).

Ví dụ sau dùng profile minh họa Ed25519 và giới hạn payload 64 KiB. Tên thuật toán là hằng do ứng dụng chọn, không nhận từ envelope. Java có tên chuẩn Ed25519; khả năng và chế độ của provider triển khai vẫn phải được xác nhận theo môi trường. [Oracle: Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html#signature-algorithms), [RFC 8032: EdDSA](https://www.rfc-editor.org/rfc/rfc8032.html).

```java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Objects;

public final class Ed25519SignatureExample {
    private static final String ALGORITHM = "Ed25519";
    private static final int MAX_MESSAGE_BYTES = 65_536;
    private static final int SIGNATURE_BYTES = 64;

    public static byte[] signBytes(byte[] message, PrivateKey signingKey)
            throws GeneralSecurityException {
        byte[] exactMessage = boundedCopy(message);
        Objects.requireNonNull(signingKey, "Signing key required");

        Signature signer = Signature.getInstance(ALGORITHM);
        signer.initSign(signingKey);
        signer.update(exactMessage);
        return signer.sign();
    }

    public static boolean verifyBytes(
            byte[] message,
            byte[] signatureBytes,
            PublicKey trustedVerificationKey
    ) throws GeneralSecurityException {
        byte[] exactMessage = boundedCopy(message);
        Objects.requireNonNull(signatureBytes, "Signature required");
        Objects.requireNonNull(trustedVerificationKey, "Trusted key required");
        if (signatureBytes.length != SIGNATURE_BYTES) {
            return false;
        }
        byte[] exactSignature = signatureBytes.clone();

        Signature verifier = Signature.getInstance(ALGORITHM);
        verifier.initVerify(trustedVerificationKey);
        verifier.update(exactMessage);
        return verifier.verify(exactSignature);
    }

    private static byte[] boundedCopy(byte[] message) {
        Objects.requireNonNull(message, "Message required");
        if (message.length == 0 || message.length > MAX_MESSAGE_BYTES) {
            throw new IllegalArgumentException("Message outside example limits");
        }
        return message.clone();
    }

    private Ed25519SignatureExample() {}
}
```

Đoạn mã chỉ minh họa primitive trên đúng byte đầu vào, không triển khai JWS, PDF signature hay một dịch vụ cấp chứng chỉ hoàn chỉnh. Không tự hash payload bằng một thuật toán tùy chọn rồi đưa digest vào helper này nếu signing profile không quy định cách đó; khi đó thông điệp được ký đã thay đổi.

`trustedVerificationKey` phải do lớp trust resolution đã kiểm tra cung cấp. Hàm Java không thể biết một public key caller đưa vào có thực sự thuộc trường học hay không. Tương tự, quyền gọi `signBytes` phải được bảo vệ bởi service nghiệp vụ và quyền private key.

Giới hạn 64 KiB là chính sách ví dụ cho payload chứng chỉ nhỏ, không phải giới hạn của mọi chữ ký số. Signature object được tạo cho từng thao tác trong ví dụ; không chia sẻ một instance có trạng thái giữa các request đồng thời.

Khi `verify` trả false hoặc phát sinh lỗi, lớp tích hợp phải xử lý như không chấp nhận artifact theo contract. Không catch exception rồi coi nội dung là hợp lệ để giữ khả năng đọc tài liệu.

## 8. Quy trình xác minh phải đi tới quyết định nghiệp vụ

Một pipeline mẫu cho tài liệu từ nguồn ngoài:

```text
Giới hạn kích thước request/artifact
→ parse envelope tối thiểu bằng parser có giới hạn
→ kiểm tra format/profile và metadata cần thiết
→ resolve verification key trong trust registry được phép
→ verify đúng signing input của format
→ parse/validate payload theo schema của profile
→ kiểm tra issuer, purpose, thời gian và trạng thái
→ kiểm tra quyền/điều kiện của use case
→ sử dụng đúng dữ liệu đã được xác minh
```

Một số format cần parse hoặc canonicalize payload trước bước mật mã; khi đó parser và canonicalization phải có giới hạn và đúng profile. Không diễn giải bước parse như đã tin nội dung, và không thực thi extension tùy ý từ dữ liệu chưa được xác minh.

### 8.1. Tách kết quả mật mã và kết quả chấp nhận

| Kết quả riêng | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| Chữ ký khớp public key | Dữ liệu đáp ứng phép verify với key được đưa vào | Key thuộc một issuer được tin hoặc artifact còn hiệu lực |
| Key được trust registry chấp nhận | Key thuộc phạm vi/mục đích được phép | Payload có đúng khóa học hay người học không |
| Payload đúng schema và context | Field đáp ứng contract đã chốt | Chứng chỉ chưa bị thu hồi tại thời điểm sử dụng |
| Tài liệu còn hiệu lực theo policy | Các kiểm tra thời gian/trạng thái đạt | Actor hiện tại có quyền thực hiện mọi hành động dựa vào tài liệu |
| Use case chấp nhận | Tất cả điều kiện của thao tác cụ thể đạt | Tài liệu được dùng cho một mục đích khác trong tương lai |

Một trang tra cứu có thể cần hiển thị kết luận dễ hiểu, nhưng bên trong vẫn nên phân biệt các lớp kiểm tra để điều tra đúng nguyên nhân. Không chỉ có một boolean `valid` được mọi service diễn giải theo ý riêng.

### 8.2. Không cho metadata chưa được kiểm tra mở rộng thuật toán

Algorithm identifier trong artifact chỉ được so với allowlist của profile và loại key tương ứng. Không gọi `Signature.getInstance` theo một chuỗi tùy ý do client gửi. Nếu cần hỗ trợ nhiều profile, mapping profile–algorithm–key type phải do cấu hình tin cậy quản lý.

Với format cho cả chữ ký và MAC, tránh nhầm public key thành secret của MAC hoặc chấp nhận mode không có chữ ký cho một use case yêu cầu ký bất đối xứng. Thư viện protocol được chọn vẫn cần cấu hình chính sách thuật toán và key đúng mục đích.

Format hay key không được hỗ trợ phải có kết quả từ chối rõ. Không thử một danh sách mode yếu hơn hoặc bỏ verify sau khi một cách xác minh thất bại.

## 9. Hiệu lực, thu hồi và tính mới là các yêu cầu riêng

### 9.1. Chữ ký không tự hết hạn

Một phép verify có thể vẫn trả true sau thời điểm nghiệp vụ muốn ngừng chấp nhận tài liệu. Các field `issuedAt`, `validUntil`, audience hoặc purpose chỉ có hiệu lực nếu được bảo vệ trong signing contract và được bên nhận kiểm tra đúng.

Nguồn thời gian, độ lệch cho phép, cách xử lý múi giờ và điều kiện tại đúng mốc hết hạn phải được chốt. Không để client tự gửi thời gian hiện tại cho server để quyết định một chứng chỉ còn hạn.

Với payload thời gian dạng string, parser phải hiểu định dạng mà profile công bố, không tự đoán nhiều cách ghi gây khác nhau giữa consumer. Giới hạn khoảng hiệu lực cũng cần gắn với loại tài liệu và quyền của issuer.

### 9.2. Ba loại trạng thái dễ bị gọi chung là certificate

Trong tình huống này cần phân biệt:

- Chứng chỉ hoàn thành khóa học là đối tượng nghiệp vụ có thể bị thu hồi vì kết quả bị hủy hoặc phát hành sai.
- Certificate X.509, nếu dùng, là cấu trúc gắn public key với thông tin và policy của PKI.
- Signing key có vòng đời sử dụng riêng, bao gồm rotation, ngừng ký hoặc compromise.

Một chứng chỉ học tập có thể bị thu hồi dù signing key vẫn tốt. Một signing key bị thay thế không tự làm mọi chứng chỉ cũ mất giá trị. Chính sách chấp nhận phải mô tả những quan hệ này thay vì gộp thành một cờ `revoked` không rõ nghĩa.

### 9.3. Xác minh offline có giới hạn về trạng thái hiện tại

Offline verification có thể xác minh chữ ký và những dữ liệu đã mang theo theo mô hình trust được phân phối trước. Nó không tự biết sự kiện thu hồi vừa xảy ra mà không có dữ liệu trạng thái đủ mới.

Nếu cần kiểm tra trạng thái online, phải chốt nguồn trạng thái có thẩm quyền, xác thực kênh, timeout, cache TTL và hành vi khi không liên hệ được. `STATUS_UNKNOWN` không được tự đổi thành “đã xác nhận chưa thu hồi” chỉ để màn hình luôn hiển thị màu xanh.

Use case có thể cho phép xem nội dung nhưng không chấp nhận nó làm bằng chứng cho một hành động nhạy cảm khi trạng thái chưa rõ. Quyết định phải được ghi trong policy thay vì ẩn bên trong một fallback thư viện.

### 9.4. Replay phụ thuộc loại tài liệu

Một chứng chỉ công khai có thể được xác minh nhiều lần; đó thường là chức năng mong muốn. Ngược lại, một thông điệp phê duyệt một lần hoặc lệnh từ đối tác có thể cần event ID, nonce/challenge, TTL và trạng thái đã xử lý ở server.

Chữ ký xác thực thông điệp không tự ngăn việc phát lại thông điệp hợp lệ. Nếu cần one-time use, việc đánh dấu đã dùng phải có tính nhất quán phù hợp với đồng thời và retry, đồng thời ràng buộc đúng thao tác/đối tượng.

Không thêm nonce một cách hình thức rồi bỏ qua kiểm tra phía nhận. Tương tự, đặt một `certificateId` duy nhất không tự biến một chứng chỉ nhiều lần xác minh thành chứng từ chỉ dùng được một lần.

## 10. Vòng đời signing key và khả năng kiểm tra lâu dài

### 10.1. Giới hạn quyền ký trước khi bảo vệ key material

Private key không được hard-code, đưa vào source repository, log hoặc phân phối cho các bên chỉ cần verify. Có thể dùng KMS/HSM hoặc cơ chế bảo vệ key phù hợp với môi trường; identity sử dụng cần được giới hạn đúng key và đúng thao tác.

Tuy nhiên một HSM không tự ngăn service có quyền ký phát hành chứng chỉ sai. Nếu service bị chiếm hoặc nhận command không được phân quyền, kẻ tấn công có thể sử dụng chính API ký hợp lệ. Cần kiểm soát command nghiệp vụ, tách mục đích khóa, quota và audit.

Không dùng cùng private key cho môi trường dev và production hoặc cho nhiều mục đích không có cùng trust boundary. Verifier phải phân biệt được issuer và purpose, thay vì chấp nhận mọi artifact có key từng xuất hiện trong hệ thống.

### 10.2. Rotation cần kế hoạch cho cả signer và verifier

Khi chuyển sang key mới, dữ liệu phát hành mới dùng key version đã active. Public key cũ có thể cần tiếp tục có trong trust registry cho tài liệu còn được chấp nhận theo policy.

Không xóa public key cũ khỏi mọi consumer chỉ vì đã ngừng dùng private key đó để ký. Cũng không giữ key ở trạng thái ký mới vô hạn chỉ vì còn tài liệu lịch sử cần verify. Hai quyền có vòng đời khác nhau.

Registry cần liên kết key ID với issuer, purpose, algorithm/profile, thời điểm và trạng thái sử dụng. Phân phối thay đổi tới consumer phải có revision và khả năng đối soát, đặc biệt với verifier offline hoặc đối tác có cache.

### 10.3. Compromise khác rotation theo lịch

Khi private key bị lộ, đối thủ có thể tạo chữ ký hợp lệ dưới key đó. Chỉ đổi key cho tài liệu mới chưa trả lời những artifact nào đã được phát hành trái phép hoặc phải ngừng chấp nhận.

Cần kế hoạch giới hạn ảnh hưởng, ngừng quyền ký, cập nhật trust/status, xác định tài liệu liên quan và phát hành lại theo nghiệp vụ nếu cần. Log của signer giúp điều tra nhưng không mặc định chứng minh mọi chữ ký ngoài log đều giả nếu log không đầy đủ.

Field `issuedAt` do bên ký đưa vào không phải bằng chứng độc lập về thời điểm chữ ký được tạo. Một người đã có private key bị compromise có thể đặt thời điểm quá khứ trong payload mới.

Nếu yêu cầu xác minh lâu dài cần bằng chứng dữ liệu đã tồn tại trước một mốc, có thể sử dụng cơ chế trusted timestamp theo profile phù hợp. RFC 3161 mô tả Time-Stamp Protocol và dịch vụ TSA cho loại bằng chứng đó; timestamp vẫn phải được xác minh với mô hình trust riêng. [RFC 3161: Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161.html).

Timestamp không tự chứng minh người ký đã có quyền nghiệp vụ hoặc nội dung chứng chỉ là sự thật. Nó bổ sung một loại bằng chứng thời gian, không thay toàn bộ chuỗi kiểm tra.

## 11. Vận hành, lỗi và audit

### 11.1. Chặn lỗi mà không bỏ xác minh

| Lỗi | Hành vi cần đặc tả |
| --- | --- |
| Chữ ký không khớp hoặc malformed | Không chấp nhận artifact; không dùng payload như đã xác thực |
| Key ID không biết hoặc issuer ngoài trust | Không tự tin key được gửi kèm; không discovery ngoài policy |
| Algorithm/profile không hỗ trợ | Từ chối, không downgrade hoặc chuyển sang mode không ký |
| Signer/KMS không sẵn có | Không cấp chứng chỉ unsigned rồi báo phát hành thành công |
| Nguồn trạng thái không truy cập được | Kết quả theo policy unknown, không giả kết luận còn hiệu lực |
| Parser/canonicalization lỗi | Không verify một representation khác rồi dùng nội dung chưa được kiểm tra |

Lớp HTTP có thể gom thông báo để hạn chế lộ thông tin nội bộ. Lớp quan sát vẫn cần reason code phân biệt integrity, trust, expiry, revocation và availability để xử lý đúng.

### 11.2. Giới hạn tài nguyên trước những thao tác đắt

Verifier nhận input không tin cậy cần giới hạn kích thước artifact, độ sâu cấu trúc, số chữ ký/certificate, độ dài key ID và chi phí discovery. Không để một file nhỏ trỏ tới vô hạn tài nguyên mạng hoặc một tập candidate key không giới hạn.

Signer cần rate limit/quota theo tác vụ và actor được cấp quyền. Điều này bảo vệ năng lực dịch vụ và hỗ trợ phát hiện lạm dụng khóa, nhưng không thay điều kiện học viên đã hoàn thành khóa học.

### 11.3. Audit ghi được ý nghĩa thao tác

Một sự kiện phát hành có thể liên kết certificate ID, actor/workload, issuer, profile, key version, payload digest và kết quả nghiệp vụ. Không ghi private key, password hoặc toàn bộ dữ liệu học viên chỉ để chẩn đoán chữ ký.

Payload digest trong audit giúp đối soát nội dung theo thiết kế, nhưng quyền sửa và tính toàn vẹn của audit cũng phải được bảo vệ. Một digest lưu trong log mà đối thủ cùng có thể thay không tự tạo bằng chứng độc lập.

Public verification cũng cần giới hạn dữ liệu trả về. Chữ ký của một chứng chỉ không tự cấp quyền tra cứu toàn bộ hồ sơ học tập hoặc dùng một endpoint để dò thông tin người học hàng loạt.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-SIG-01 | Mỗi loại tài liệu ký có purpose, format/profile, scope dữ liệu và bên phát hành được chốt | Signing contract và ma trận trust/use case |
| SR-SIG-02 | Signer chỉ ký dữ liệu đã qua command nghiệp vụ được phân quyền; không là oracle ký byte tùy ý | Ca actor/đối tượng sai và kiểm tra đường gọi key service |
| SR-SIG-03 | Mọi field có ý nghĩa chấp nhận tài liệu và metadata cần thiết nằm trong signing input theo profile | Đối chiếu protected data với quyết định nghiệp vụ |
| SR-SIG-04 | Hai bên thống nhất byte/canonicalization; không dùng object đã parse lại khác representation ngoài contract | Test vector và ca serialize khác biệt |
| SR-SIG-05 | Verification key lấy từ trust model được duyệt, gắn với issuer/purpose; không tin key tự gửi kèm | Ca key tự tạo, issuer lạ và key khác tenant |
| SR-SIG-06 | Algorithm và key type được allowlist; không chấp nhận mode ngoài profile hoặc bỏ chữ ký | Ca algorithm lạ, mode không ký và loại key không phù hợp |
| SR-SIG-07 | Consumer chỉ dùng đúng dữ liệu đã được verify và validate | Ca detached payload, object hiển thị khác và field không được bảo vệ |
| SR-SIG-08 | Hiệu lực, trạng thái thu hồi và trường hợp unknown được xử lý theo policy | Ca hết hạn, revoked, nguồn trạng thái lỗi và boundary thời gian |
| SR-SIG-09 | Thông điệp cần one-time use có ràng buộc freshness và xử lý replay nhất quán | Ca phát lại, retry và đồng thời |
| SR-SIG-10 | Private key được bảo vệ và tách mục đích/môi trường; quyền ký tối thiểu có audit | Ma trận key identity và ca workload bị từ chối |
| SR-SIG-11 | Rotation/compromise có kế hoạch cho phát hành mới và kiểm tra tài liệu lịch sử | Diễn tập đổi key, cập nhật registry và đối soát artifact |
| SR-SIG-12 | Lỗi parser, verify hoặc signer không dẫn tới chấp nhận/cấp unsigned artifact | Fault injection có kiểm soát và đọc lại trạng thái |
| SR-SIG-13 | Verifier/signer giới hạn tài nguyên, discovery và dữ liệu log | Ca quá kích thước, nhiều candidate key và kiểm tra telemetry |

SR-SIG-09 chỉ áp dụng với thông điệp cần dùng một lần; chứng chỉ nhiều lần xác minh không cần bị vô tình tiêu thụ sau lần tra cứu đầu tiên. Yêu cầu phải theo mục tiêu của từng use case, không sao chép một cơ chế replay cho mọi loại artifact.

Nếu dự án yêu cầu chứng nhận provider, một định dạng chữ ký cụ thể hoặc khả năng kiểm tra dài hạn, cần bổ sung gate đúng môi trường đó. Việc tên thuật toán xuất hiện trong tiêu chuẩn không tự chứng minh mọi library build và cấu hình của ứng dụng đáp ứng yêu cầu triển khai.

## 13. Thiết kế bằng chứng kiểm chứng

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được thực thi trong bài học.

### 13.1. Ma trận ca kiểm thử

| Ca | Dữ liệu/hành động | Kỳ vọng |
| --- | --- | --- |
| S1 | Artifact hợp lệ từ issuer/key được tin | Đạt các lớp kiểm tra và được chấp nhận đúng use case |
| S2 | Đổi learnerRef/courseId trong phần được ký | Verify thất bại hoặc artifact bị từ chối theo format |
| S3 | Đổi một byte chữ ký hoặc cắt ngắn chữ ký | Không chấp nhận, không có fallback unsigned |
| S4 | Tạo key riêng và gửi public key kèm tài liệu | Không thành issuer được tin chỉ vì chữ ký khớp key tự gửi |
| S5 | Key có thật nhưng thuộc issuer/tenant/purpose khác | Từ chối theo trust/context |
| S6 | Đổi algorithm hoặc yêu cầu mode không ký | Từ chối theo profile trước khi chấp nhận dữ liệu |
| S7 | Thay whitespace/order của JSON | Kết quả đúng contract raw-byte hoặc canonical đã chọn, không đoán linh hoạt |
| S8 | Payload có duplicate field, kiểu sai hoặc vượt giới hạn | Bị chặn theo parser/schema, không có hai cách hiểu nghiệp vụ |
| S9 | Chữ ký đúng nhưng purpose hoặc audience không phù hợp | Không dùng cho thao tác hiện tại |
| S10 | Artifact hết hạn, bị thu hồi hoặc trạng thái chưa rõ | Kết quả đúng policy, không gộp thành valid chỉ vì verify=true |
| S11 | Signer/KMS lỗi trong lúc phát hành | Không tạo trạng thái đã cấp kèm artifact thiếu chữ ký |
| S12 | Rotate key, giữ chứng chỉ cũ còn được chấp nhận | Signer dùng key mới; verifier xử lý lịch sử theo policy |
| S13 | Phát lại thông điệp chỉ được dùng một lần | Không lặp tác dụng phụ; retry theo contract |
| S14 | Nội dung hiển thị khác payload đã verify | Không công bố kết luận hợp lệ cho phần chưa được bảo vệ |

S7 phải có kỳ vọng riêng theo lựa chọn format. Với helper Java ký đúng byte trong bài, thay byte làm đầu vào khác. Với một JCS profile đúng, các biểu diễn được scheme chuẩn hóa tương đương có thể cùng được xác minh sau canonicalization; không trộn hai contract trong cùng một phép thử.

### 13.2. Phải thử trust sai dù phép verify có thể thành công

Một bài test tạo key pair, ký rồi verify bằng public key cùng pair là kiểm tra happy path của primitive. Ca S4 cần chứng minh ứng dụng không chấp nhận một key pair mới do bên gửi tự tạo như một issuer có thẩm quyền.

Tương tự, ca S5 chứng minh giới hạn issuer/purpose. Nếu verifier chỉ thử tất cả public key đã từng biết tới rồi nhận bất kỳ key nào verify được, có thể bỏ mất ranh giới giữa bên phát hành, tenant và mục đích.

### 13.3. Kiểm tra đúng thời điểm và trạng thái

Sử dụng nguồn thời gian có thể kiểm soát trong môi trường kiểm thử để thử trước, đúng và sau mốc hiệu lực. Không sửa đồng hồ production để chạy ca expiry.

Với trạng thái online, thử cache cũ, dịch vụ trạng thái timeout và sự kiện thu hồi sau khi chữ ký đã được phát hành. Kết quả phải thể hiện đúng cửa sổ hiệu lực/cập nhật mà policy cam kết, không hứa immediate revocation nếu consumer offline hoặc cache còn sống.

Nếu có trusted timestamp, cần ca timestamp đúng/không đúng, trust TSA sai và dữ liệu timestamp không khớp. Một field thời gian trong payload không thay ca kiểm tra bằng chứng thời gian độc lập.

### 13.4. Quan sát tác dụng phụ và dữ liệu thực sự được dùng

Đọc lại trạng thái phát hành sau một lỗi signer để chắc không có chứng chỉ đã được đánh dấu thành công mà thiếu artifact hợp lệ. Với thông điệp one-time, kiểm tra tác dụng phụ chỉ xảy ra theo semantics retry đã chốt.

Đối với màn hình xác minh, đối chiếu learner/course/issuer hiển thị với đúng phần đã được verify. Một badge “signature valid” nằm cạnh nội dung lấy từ một object chưa được bảo vệ là một lỗi thiết kế dù phép kiểm tra mật mã tự nó đúng.

## 14. Những giả định cần loại bỏ

**“Public key có trong file nên đã có đủ thông tin tin cậy.”** File chỉ cung cấp một ứng viên key. Cần nguồn trust độc lập và phạm vi issuer/purpose.

**“Đã ký thì dữ liệu là bí mật.”** Chữ ký không tự mã hóa nội dung. Public verification phải có quyết định riêng về dữ liệu được công bố.

**“Verify=true là giấy phép thực hiện mọi hành động.”** Phải kiểm tra context, thời gian, trạng thái và quyền nghiệp vụ của thao tác cụ thể.

**“Signer trong HSM không thể phát hành sai.”** HSM bảo vệ key material và thao tác theo cơ chế của nó; service có quyền gọi ký vẫn cần authorization và dữ liệu có thẩm quyền.

**“Một field issuedAt chứng minh chữ ký được tạo lúc đó.”** Field do người giữ khóa đặt không phải timestamp độc lập, đặc biệt sau compromise.

**“Đổi tên một field JSON không ảnh hưởng chữ ký.”** Điều đó phụ thuộc signing contract. Phải xác định đúng byte hoặc canonical representation được ký.

**“Rotation nghĩa là bỏ mọi public key cũ.”** Quyền ký mới và khả năng xác minh tài liệu lịch sử là hai vòng đời cần quản lý riêng.

**“Đếm số lần verify thành công là đủ audit.”** Audit cần liên kết issuer, profile, artifact và quyết định chấp nhận của use case, trong giới hạn dữ liệu cho phép.

## 15. Bài tập vận dụng

Một nền tảng phát chứng chỉ PDF kèm một JSON payload có chữ ký. Trang tra cứu nhận cả payload, public key và một field `displayName` riêng từ client, rồi hiển thị “hợp lệ” nếu phép verify trả true. Signing key sắp được rotate và một đối tác muốn xác minh offline trong nhiều năm.

Hãy đề xuất một thiết kế thay thế:

1. Chọn artifact và những field thực sự được bảo vệ; mô tả quan hệ giữa PDF, payload và kết quả tra cứu.
2. Định nghĩa trust model cho issuer/key và cách từ chối public key tự gửi không có thẩm quyền.
3. Chọn raw-byte hoặc canonical/protocol profile, cùng yêu cầu parser và metadata được bảo vệ.
4. Tách kết quả verify mật mã khỏi kiểm tra expiry, thu hồi, purpose và quyết định chấp nhận.
5. Lập kế hoạch rotation/compromise và mô tả giới hạn của verifier offline đối với trạng thái hiện tại.
6. Viết ba yêu cầu và các ca nghiệm thu chứng minh không thể hiển thị dữ liệu khác phần đã được xác minh.

Kết quả cần cho thấy dữ liệu nào được ký, ai có thẩm quyền ký nó và vì sao bên nhận chấp nhận nó trong một tình huống cụ thể. Chữ ký số trở thành kiểm soát có ý nghĩa khi phép xác minh mật mã được gắn với trust, context, vòng đời khóa và quyết định nghiệp vụ rõ ràng.

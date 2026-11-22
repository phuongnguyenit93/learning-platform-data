# Quản lý lỗi mà không bỏ qua xác minh chữ ký trong Java 15+

## 1. Mục tiêu: thất bại an toàn (*fail closed*) khi tích hợp chữ ký

Trong một ứng dụng nhận thông điệp, tài liệu hoặc yêu cầu API có chữ ký số, việc “không xảy ra ngoại lệ” **không đủ để tin tưởng dữ liệu**. Ứng dụng chỉ được chấp nhận tính xác thực mật mã sau khi thực sự gọi bộ xác minh, dùng **public key được tin cậy**, kiểm tra **đúng byte thông điệp**, và nhận được kết quả `Signature.verify(...) == true`.

Từ Java 15, JCA có hỗ trợ chính thức EdDSA với `Ed25519` và `Ed448`. Bài này dùng **Ed25519** làm ví dụ cụ thể trên Java 17+ nhưng quy tắc *fail closed* áp dụng rộng hơn cho chữ ký số nói chung:

- **Đúng chữ ký:** bộ xác minh trả `true` và các điều kiện nghiệp vụ khác vẫn phải được kiểm tra.
- **Sai chữ ký:** `verify` trả `false` → **từ chối**.
- **Dữ liệu chữ ký/đầu vào không hợp lệ:** không tiếp tục như đã xác minh → **từ chối**.
- **Thiếu public key được tin cậy hoặc cấu hình sai:** **từ chối**, đồng thời xử lý như sự cố cấu hình.
- **Lỗi thuật toán, provider, khóa hoặc xử lý chữ ký:** **từ chối**, đồng thời báo lỗi kỹ thuật để điều tra.

Nguyên tắc quan trọng nhất: **mọi đường đi không chứng minh được chữ ký hợp lệ đều không được cấp quyền**. Không thay `verify=false` bằng `true` khi gặp ngoại lệ, không cho qua khi thiếu khóa và không bật “chế độ bỏ qua xác minh” ở production.

## 2. Mô hình các bước xử lý an toàn

Một luồng xử lý chữ ký tích hợp trong Java nên được tách thành các bước rõ ràng:

```text
Yêu cầu bên ngoài:
  - payload (byte[] hoặc biểu diễn byte chính xác)
  - signature (thí dụ Base64)
  - keyId / thông tin giao thức nếu có
                |
                v
[1] Giới hạn kích thước, kiểm tra dữ liệu bắt buộc
                |-- lỗi ----------> REJECT: INVALID_INPUT
                v
[2] Chọn public key từ kho TIN CẬY, theo chính sách
                |-- thiếu/lỗi ----> REJECT: CONFIG_ERROR
                v
[3] Decode chữ ký đúng encoding và cấu trúc
                |-- lỗi ----------> REJECT: INVALID_INPUT
                v
[4] Signature.initVerify + update + verify
                |-- false --------> REJECT: INVALID_SIGNATURE
                |-- exception ----> REJECT: VERIFICATION_ERROR
                v
          VALID (về chữ ký)
                |
                v
[5] Kiểm tra thời hạn, keyId, nonce, quyền, audience,
    chống replay và chính sách nghiệp vụ nếu có
                |-- không đạt ----> REJECT: POLICY_FAILURE
                v
       Cho phép xử lý nghiệp vụ
```

**Quan trọng:** `VALID` ở bước 4 có nghĩa là chữ ký phù hợp với **public key được chọn** và **những byte đã đưa vào verifier**, không có nghĩa người gửi có mọi quyền. Chỉ sau khi bước 5 đạt yêu cầu mới nên thực hiện giao dịch, thay đổi trạng thái hoặc cấp quyền truy cập.

### 2.1. Ba nhóm nguyên nhân phải tách riêng

| Nhóm | Ví dụ | Kết quả an ninh | Hướng xử lý vận hành |
| --- | --- | --- | --- |
| **Dữ liệu hoặc chữ ký không hợp lệ** | Base64 sai, độ dài sai, `verify=false` | Từ chối | Trả phản hồi đầu vào/chữ ký không hợp lệ theo API contract |
| **Không có cấu hình đáng tin cậy** | Key ID không có trong registry tin cậy, trusted key chưa nạp, key hết hiệu lực | Từ chối | Kiểm tra cấu hình, key lifecycle, rotation, deployment |
| **Lỗi xác minh kỹ thuật** | Provider không có thuật toán, `InvalidKeyException`, `SignatureException` | Từ chối | Ghi log nội bộ có kiểm soát, cảnh báo/điều tra, không được bỏ qua |

Trạng thái báo lỗi cho client có thể được thiết kế theo giao thức, nhưng **không làm thay đổi kết quả quyết định bảo mật**: trừ khi xác minh thành công và các điều kiện nghiệp vụ đạt yêu cầu, request không được chấp thuận.

## 3. Hiểu đúng hợp đồng của `java.security.Signature`

Lớp `Signature` có các bước cơ bản:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedPublicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Đây là **snippet đặt trong một method** với import, biến và xử lý `GeneralSecurityException` phù hợp. Nó có ba kiểu kết quả cần phân biệt:

1. `valid == true`: chữ ký xác minh thành công với thuật toán, khóa và message bytes đã dùng.
2. `valid == false`: chữ ký không xác minh thành công (một kết quả nghiệp vụ mật mã, **không phải ngoại lệ**).
3. Một ngoại lệ bảo mật, chẳng hạn `NoSuchAlgorithmException`, `InvalidKeyException` hoặc `SignatureException`: **quá trình xác minh chưa cho kết quả thành công**, cần từ chối và phân loại lỗi.

Theo tài liệu Java API, `Signature.verify(byte[])` trả `boolean` và **có thể ném `SignatureException`** nếu chữ ký được mã hóa sai kiểu, engine chưa được khởi tạo đúng hoặc provider không xử lý được dữ liệu. Do đó câu “chữ ký sai thì luôn trả `false`” là **không chính xác**. Một đầu vào hỏng có thể trả `false` hoặc gây exception tùy lỗi và provider; **cả hai đều không được chấp nhận**.

`Signature` là đối tượng có trạng thái. Khi dùng lại một instance, phải tuân thủ thứ tự `initVerify`, `update`, `verify`; để dễ kiểm toán, ví dụ tạo instance riêng cho mỗi lần xác minh. Không chia sẻ cùng một `Signature` instance để xác minh đồng thời từ nhiều luồng mà không có thiết kế đồng bộ phù hợp.

## 4. Thiết kế trạng thái kết quả rõ ràng

Thay vì chỉ trả về `boolean` cho mọi lỗi, nhiều dịch vụ nên tách trạng thái như sau:

| Trạng thái | Ý nghĩa | Được phép chấp nhận? |
| --- | --- | --- |
| `VALID` | Bộ xác minh đã trả về `true` | **Có**, nhưng vẫn phải qua chính sách nghiệp vụ |
| `INVALID_SIGNATURE` | `verify` đã trả về `false` | **Không** |
| `INVALID_INPUT` | Thiếu/không đọc được payload hoặc chữ ký, encoding sai, giới hạn bị vượt | **Không** |
| `CONFIG_ERROR` | Không có public key tin cậy hoặc chưa có policy/key mapping phù hợp | **Không** |
| `VERIFICATION_ERROR` | JCA không thể hoàn thành xác minh do lỗi thuật toán/khóa/provider/engine | **Không** |

Những trạng thái này hỗ trợ thống kê, cảnh báo và quy trình xử lý. **Không biến lỗi nội bộ thành `VALID` chỉ vì cần hệ thống “chịu lỗi tốt hơn”.** Độ sẵn sàng và tính đúng của xác thực là hai vấn đề khác nhau; với hệ thống bảo mật, *fail closed* được ưu tiên hơn việc cho qua request không chứng minh được chữ ký.

Một quy tắc đơn giản, dễ test:

```java
boolean accepted() {
    return status == Status.VALID;
}
```

Mã trên là phương thức minh họa thuộc một lớp giữ trạng thái; ví dụ đầy đủ ở phần 6 thể hiện rõ `enum Status` và `record Result`.

## 5. Phải kiểm soát những đầu vào nào?

### 5.1. Payload phải là đúng dãy byte đã ký

Chữ ký số xác minh **byte**, không xác minh “ý nghĩa gần giống” của một đối tượng Java. Ví dụ, hai chuỗi:

```text
payment:100:v1
payment:100:v1\n
```

khác nhau ở byte xuống dòng; nếu bên ký ký chuỗi đầu và bên nhận xác minh chuỗi sau, chữ ký không còn khớp.

Với JSON, sự khác biệt về thứ tự trường, khoảng trắng, escaping, chuẩn hóa Unicode hoặc chuyển số có thể làm byte khác nhau. Nếu giao thức ký **raw HTTP body**, cần giữ đúng bytes trước mọi thao tác serialize/deserialize biến đổi nội dung. Nếu giao thức ký **canonical JSON**, hai bên phải thống nhất và thực hiện chính xác quy trình canonicalization đã định nghĩa. Không tự lấy `object.toString()` để thay thế bytes đã ký.

### 5.2. Chữ ký Base64 phải được decode đúng

Nhiều giao thức gửi chữ ký ở dạng Base64 hoặc Base64URL. Trong Java:

```java
byte[] signatureBytes = Base64.getDecoder().decode(signatureBase64);
```

`Base64.getDecoder()` sử dụng bảng ký tự Base64 cơ bản; `Base64.getUrlDecoder()` dùng cho biến thể URL-safe. **Không thử lần lượt mọi decoder rồi nhận phiên bản nào thành công** nếu giao thức đã quy định duy nhất một định dạng.

Khi input không phải Base64 hợp lệ, decoder ném `IllegalArgumentException`. Đây là lỗi **dữ liệu đầu vào**, không phải bằng chứng chữ ký đã hợp lệ. Không nên bỏ qua exception và truyền một mảng rỗng hoặc `null` vào verifier.

### 5.3. Giới hạn kích thước trước khi decode

Ứng dụng phục vụ request từ mạng nên đặt **giới hạn kích thước payload và chữ ký ở ranh giới API**, trước khi cấp phát bộ nhớ lớn hoặc parse. Ví dụ minh họa ở phần 6 dùng 1 MiB payload và tối đa 128 ký tự cho Base64 chữ ký. Các con số này chỉ là **chính sách ví dụ**, không phải giới hạn chung do JCA quy định: khi triển khai cần chọn theo đặc tả giao thức, giới hạn upload và khả năng hệ thống.

Đối với **Ed25519 RFC 8032**, chữ ký chuẩn có **64 byte**; ví dụ kiểm tra độ dài sau Base64 decode. Với **Ed448**, chữ ký chuẩn có **114 byte**. Không sao chép phép kiểm tra `== 64` sang Ed448, ECDSA hoặc RSA: cách mã hóa và độ dài chữ ký của chúng khác nhau.

### 5.4. Khóa công khai phải đến từ nguồn tin cậy

Đừng lấy `PublicKey` do chính request tùy ý gửi lên rồi tuyên bố request “đã xác thực”: một kẻ gửi có thể tự tạo cặp khóa, tự ký và gửi kèm public key của mình để qua kiểm tra mật mã. Việc đó chỉ chứng minh **người gửi nắm khóa riêng tương ứng**, chưa chứng minh khóa đó thuộc danh tính được chấp thuận.

Chương trình demo tạo key pair tại chỗ để dễ kiểm thử. **Trong production**, hãy chọn public key từ registry/keystore/chứng chỉ đã kiểm tra, ánh xạ `keyId` tới khóa tin cậy, kiểm tra trạng thái key rotation và các ràng buộc theo giao thức. Một `keyId` do client gửi chỉ nên dùng làm **gợi ý tra cứu trong kho khóa tin cậy**, không phải quyền cho phép nhập bất kỳ public key nào.

## 6. Chương trình Java 17+ hoàn chỉnh: fail closed cho Ed25519

Chương trình này cố ý tách **năm trạng thái** và chứng minh rằng chỉ trường hợp `VALID` được chấp nhận. Nó tạo một chữ ký thử nghiệm Ed25519, sau đó chạy các ca chữ ký sai, thông điệp bị đổi, sai encoding, thiếu khóa, sai loại khóa và quá giới hạn.

Tạo file **`SignatureFailClosedDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Arrays;
import java.util.Base64;

public class SignatureFailClosedDemo {
    private static final int MAX_MESSAGE_BYTES = 1_048_576;
    private static final int MAX_SIGNATURE_TEXT_CHARS = 128;

    enum Status {
        VALID, INVALID_SIGNATURE, INVALID_INPUT, CONFIG_ERROR, VERIFICATION_ERROR
    }

    record Result(Status status) {
        boolean accepted() {
            return status == Status.VALID;
        }
    }

    static Result verify(byte[] message, String signatureBase64, PublicKey trustedKey) {
        if (trustedKey == null) {
            return new Result(Status.CONFIG_ERROR);
        }
        if (message == null || signatureBase64 == null || signatureBase64.isBlank()) {
            return new Result(Status.INVALID_INPUT);
        }
        if (message.length > MAX_MESSAGE_BYTES
                || signatureBase64.length() > MAX_SIGNATURE_TEXT_CHARS) {
            return new Result(Status.INVALID_INPUT);
        }

        byte[] signatureBytes;
        try {
            signatureBytes = Base64.getDecoder().decode(signatureBase64);
        } catch (IllegalArgumentException ex) {
            return new Result(Status.INVALID_INPUT);
        }
        if (signatureBytes.length != 64) {
            return new Result(Status.INVALID_INPUT);
        }

        try {
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(trustedKey);
            verifier.update(message);
            return new Result(verifier.verify(signatureBytes)
                    ? Status.VALID : Status.INVALID_SIGNATURE);
        } catch (GeneralSecurityException ex) {
            return new Result(Status.VERIFICATION_ERROR);
        }
    }

    static void show(String label, Result result) {
        System.out.println(label + "=" + result.status()
                + " accepted=" + result.accepted());
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyPair keys = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        KeyPair otherKeys = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        KeyPair wrongCurve = KeyPairGenerator.getInstance("Ed448").generateKeyPair();

        byte[] message = "payment:100:v1".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();
        String base64Signature = Base64.getEncoder().encodeToString(signature);

        show("valid", verify(message, base64Signature, keys.getPublic()));
        show("changedMessage", verify("payment:999:v1".getBytes(StandardCharsets.UTF_8),
                base64Signature, keys.getPublic()));
        show("wrongPublicKey", verify(message, base64Signature, otherKeys.getPublic()));
        show("malformedBase64", verify(message, "***bad***", keys.getPublic()));
        show("shortSignature", verify(message,
                Base64.getEncoder().encodeToString(Arrays.copyOf(signature, 10)),
                keys.getPublic()));
        show("missingMessage", verify(null, base64Signature, keys.getPublic()));
        show("missingTrustedKey", verify(message, base64Signature, null));
        show("wrongKeyType", verify(message, base64Signature, wrongCurve.getPublic()));
        show("oversizedMessage", verify(new byte[MAX_MESSAGE_BYTES + 1],
                base64Signature, keys.getPublic()));
        show("oversizedSignatureText", verify(message,
                "A".repeat(MAX_SIGNATURE_TEXT_CHARS + 1), keys.getPublic()));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 SignatureFailClosedDemo.java
java SignatureFailClosedDemo
```

**Stdout chính xác**, đã biên dịch bằng `--release 17` và chạy kiểm chứng trên JDK 24:

```text
valid=VALID accepted=true
changedMessage=INVALID_SIGNATURE accepted=false
wrongPublicKey=INVALID_SIGNATURE accepted=false
malformedBase64=INVALID_INPUT accepted=false
shortSignature=INVALID_INPUT accepted=false
missingMessage=INVALID_INPUT accepted=false
missingTrustedKey=CONFIG_ERROR accepted=false
wrongKeyType=VERIFICATION_ERROR accepted=false
oversizedMessage=INVALID_INPUT accepted=false
oversizedSignatureText=INVALID_INPUT accepted=false
```

### 6.1. Giải thích kết quả

1. **`valid=VALID`**: chữ ký được tạo bằng private key tương ứng với public key tin cậy trong bài demo, và verifier nhận đúng bytes thông điệp.
2. **`changedMessage=INVALID_SIGNATURE`**: một ký tự trong nội dung thanh toán thay đổi làm chữ ký không còn phù hợp.
3. **`wrongPublicKey=INVALID_SIGNATURE`**: dùng một public key Ed25519 khác, chữ ký không xác minh thành công.
4. **`malformedBase64=INVALID_INPUT`**: decoder không chấp nhận chuỗi `***bad***`.
5. **`shortSignature=INVALID_INPUT`**: bytes sau decode chỉ dài 10 thay vì 64 byte Ed25519.
6. **`missingMessage=INVALID_INPUT`**: `null` là thiếu đầu vào, khác một thông điệp rỗng hợp lệ nếu giao thức cho phép.
7. **`missingTrustedKey=CONFIG_ERROR`**: không có key đáng tin cậy, nên hệ thống tuyệt đối không cho qua.
8. **`wrongKeyType=VERIFICATION_ERROR`**: thử dùng khóa Ed448 cho verifier Ed25519 dẫn tới lỗi JCA về khóa, được phân loại và từ chối.
9. **`oversizedMessage`** và **`oversizedSignatureText`**: ứng dụng từ chối dữ liệu vượt ngưỡng trước khi decode/verify, phù hợp với giới hạn ví dụ.

**Điều cần kiểm chứng lại trong code:** `accepted()` chỉ trả `true` cho `VALID`. Tất cả các nhánh lỗi đều trả một status **khác** `VALID`. Không có fallback ẩn nào trả `true` khi lỗi xảy ra.

Trong môi trường production, hãy thiết kế thêm **log/metrics nội bộ** cho `CONFIG_ERROR` và `VERIFICATION_ERROR`: demo chỉ thể hiện phân loại bằng status, không in stack trace hoặc dữ liệu nhạy cảm. Nếu provider thực tế phân loại một chữ ký hỏng thành `SignatureException` thay vì `false`, chương trình vẫn **từ chối**; chi tiết loại status có thể thay đổi nhưng nguyên tắc bảo mật không đổi.

## 7. Phân biệt `verify(false)`, đầu vào sai và ngoại lệ JCA

| Tình huống | Phản ứng tại API Java | Xử lý an toàn |
| --- | --- | --- |
| Chữ ký đúng | `Signature.verify(bytes)` trả `true` | Đánh dấu chữ ký hợp lệ; tiếp tục kiểm tra chính sách |
| Chữ ký không đúng | `verify` trả `false` | Từ chối; không thử cho qua |
| Base64 lỗi | `Base64.Decoder.decode` ném `IllegalArgumentException` | Từ chối đầu vào |
| Signature bytes sai định dạng | `verify` có thể `false` hoặc ném `SignatureException` | Từ chối trong cả hai trường hợp |
| Public key không phù hợp | `initVerify` có thể ném `InvalidKeyException` | Từ chối và kiểm tra cấu hình |
| Thuật toán không được provider hỗ trợ | `getInstance` ném `NoSuchAlgorithmException` | Từ chối và báo lỗi triển khai |
| Engine không xử lý được | `SignatureException` | Từ chối; log/alert nội bộ |
| Trusted key không tồn tại | Không nên gọi xác minh với `null` | Từ chối và xác định vấn đề key registry |

Đối với ứng dụng cần ánh xạ lỗi chính xác hơn, có thể bắt riêng `InvalidKeyException`, `NoSuchAlgorithmException` và `SignatureException` để tạo mã lỗi nội bộ có ý nghĩa. Nhưng **kể cả khi có nhiều `catch` hơn, không được biến bất kỳ nhánh exception nào thành xác minh thành công**.

`GeneralSecurityException` là lớp gốc cho nhiều lỗi có thể thu hồi/ghi nhận ở ranh giới thao tác JCA. Ví dụ dùng nó để tổng hợp thành `VERIFICATION_ERROR` mà không bỏ qua quyết định bảo mật. Nó **không** bắt mọi `RuntimeException` hoặc mọi `Error`; code sản xuất nên có xử lý lỗi request và sự cố hạ tầng riêng, không dùng một `catch (Throwable)` để mặc định chấp nhận.

## 8. Những phản mẫu nguy hiểm: tuyệt đối tránh

### 8.1. “Catch rồi cho qua”

```java
// SAI: Không áp dụng.
try {
    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(key);
    verifier.update(message);
    return verifier.verify(signature);
} catch (GeneralSecurityException ex) {
    return true; // LỖ HỔNG: mọi lỗi xác minh biến thành chấp nhận.
}
```

Đây là **phản ví dụ**: các biến được giả định có sẵn và khối này phải được đặt trong method thích hợp. Sai lầm cốt lõi nằm ở `return true` trong nhánh lỗi, làm mất toàn bộ ý nghĩa của chữ ký số.

### 8.2. “Thiếu khóa thì không cần verify”

```java
// SAI: Không áp dụng.
if (trustedKey == null) {
    return true;
}
```

Thiếu khóa đáng tin cậy là **lỗi cấu hình hoặc chính sách**, không phải tín hiệu cho phép không xác minh. Nếu đang trong đợt key rotation, hệ thống phải chọn một khóa **vẫn được chính sách cho phép** từ registry, hoặc từ chối khi không có khóa hợp lệ.

### 8.3. “Verify sai thì thử tắt kiểm tra”

```text
verify=false -> thử key bất kỳ do request gửi -> cho qua
verify throws -> chỉ ghi warning -> thực hiện giao dịch
signature missing -> xem như authenticated=true
unknown algorithm -> tự động dùng chế độ không ký
```

Mọi quy tắc trên đều là **fail open** và không được có mặt trong đường xử lý yêu cầu có chữ ký bắt buộc.

Nếu giao thức cho phép nhiều thuật toán hoặc nhiều key đang trong thời gian chuyển đổi, phải thiết kế **allowlist và policy** rõ ràng. Tránh việc verifier tự thử thuật toán/khoá yếu hơn chỉ để tìm được một cách xác minh “thành công”.

## 9. Quản lý thuật toán, keyId và các biến thể EdDSA

### 9.1. Cố định thuật toán theo chính sách

Trong demo, ứng dụng chọn tường minh:

```java
Signature verifier = Signature.getInstance("Ed25519");
```

Đây là lựa chọn phù hợp khi giao thức quy định Ed25519. Không nên lấy một chuỗi `algorithm` tự do từ request để đưa ngay vào `Signature.getInstance(algorithm)` mà không có allowlist; điều đó có thể tạo *algorithm confusion* hoặc làm đường kiểm tra phụ thuộc dữ liệu không đáng tin.

Nếu hệ thống thực sự cần hỗ trợ cả Ed25519 và Ed448, hãy khai báo **một allowlist thuật toán**, ánh xạ từng key đã đăng ký với thuật toán của chính nó và chọn trình xác minh theo chính sách. Ed25519 chuẩn có chữ ký dài 64 byte; Ed448 chuẩn dài 114 byte; không được dùng một kiểm tra độ dài cho mọi thuật toán.

### 9.2. Context và prehash phải khớp giao thức

EdDSA có các biến thể như **Ed25519 pure**, **Ed25519ctx**, **Ed25519ph**, **Ed448** và **Ed448ph**. Java cung cấp `EdDSAParameterSpec` để cấu hình `prehash` và `context` khi giao thức yêu cầu:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedKey);
verifier.setParameter(
        new java.security.spec.EdDSAParameterSpec(false, contextBytes));
verifier.update(messageBytes);
boolean verified = verifier.verify(signatureBytes);
```

Đây là đoạn minh họa **có context** (cần biến/import/ngoại lệ thích hợp), không phải cấu hình mặc định cho mọi chữ ký Ed25519. `contextBytes` phải được xác định bởi **giao thức tin cậy**; không được “thử mọi context” hoặc bật/tắt prehash khi xác minh thất bại. Nếu giao thức dùng Ed25519 pure, không tự bật ctx hay ph để “chữa lỗi”.

**Chú ý:** Nếu giao thức đã định nghĩa đúng mode, cả bên ký lẫn bên xác minh cần thực hiện cùng quy tắc. Không tự băm message bên ngoài rồi coi đó là Ed25519ph; prehash theo RFC 8032 phải được thực hiện đúng qua tham số và implementation tương ứng.

### 9.3. Key rotation không được biến thành bypass

Trong quá trình đổi khóa, một `keyId` có thể tham chiếu tới khóa cũ nhưng còn trong cửa sổ chấp nhận, hoặc khóa mới. Policy cần quy định rõ:

- Trạng thái và thời hạn sử dụng của mỗi public key đáng tin cậy.
- Thuật toán gắn với key và phạm vi cho phép (tenant, service, audience, loại giao dịch).
- Cách xử lý khi `keyId` không tồn tại: **từ chối**, không lấy khóa bất kỳ do client cung cấp.
- Những metadata nào phải nằm trong **nội dung được ký** để tránh việc một chữ ký hợp lệ bị chuyển sang ngữ cảnh không đúng.

Không đánh đồng “đã từng tin cậy” với “đang được phép dùng để xác minh request này”.

## 10. Phân loại lỗi ở tầng API và vận hành

Một dịch vụ có thể phản hồi khác nhau với người gọi mà vẫn đảm bảo fail closed:

| Trạng thái nội bộ | Hành vi ra ngoài (tham khảo) | Hành vi nội bộ |
| --- | --- | --- |
| `INVALID_INPUT` | Phản hồi lỗi dữ liệu/chữ ký theo giao thức, thường nhóm 4xx | Đếm lỗi input, áp dụng giới hạn request |
| `INVALID_SIGNATURE` | Phản hồi xác thực thất bại, thường nhóm 4xx | Có thể ghi metric về thất bại chữ ký |
| `CONFIG_ERROR` | Không thực hiện thao tác; thông báo dịch vụ không thể xác minh nếu phù hợp | Cảnh báo cấu hình, key registry và on-call |
| `VERIFICATION_ERROR` | Không thực hiện thao tác; thông báo lỗi xác minh tổng quát | Ghi nhận lỗi JCA/provider và điều tra |
| `VALID` | Tiếp tục kiểm tra quyền, thời hạn, replay và nghiệp vụ | Ghi nhận kết quả xác minh với dữ liệu audit an toàn |

Mã HTTP cụ thể tùy API contract và mô hình threat; bảng trên **không** quy định mọi `INVALID_SIGNATURE` đều phải là 401 hoặc 403. Không gửi chi tiết provider, stack trace hoặc thông tin private key về client. Đồng thời tránh trả về nội dung quá chi tiết giúp đối tượng tấn công đoán thông tin nhạy cảm về key registry.

**Logging an toàn:**

- Nên có event code, timestamp, correlation ID, key identifier đã kiểm soát, thuật toán đã chọn, trạng thái và thời gian xử lý.
- Không log private key, seed, chữ ký nguyên văn hoặc nội dung mật của payload chỉ để debug.
- Với `CONFIG_ERROR` và `VERIFICATION_ERROR`, ghi thông tin ngoại lệ vào log nội bộ được phân quyền và thiết lập cảnh báo, nhưng request vẫn bị từ chối.
- Ghi nhận số liệu thất bại có thể giúp phát hiện sự cố provider sau nâng cấp JDK, cấu hình sai, dữ liệu bị đổi và lạm dụng API.

**Retry có kiểm soát:** Lỗi hạ tầng có thể được xử lý bằng retry ở tầng vận hành nếu policy cho phép, nhưng **không thực hiện nghiệp vụ bảo vệ bởi chữ ký trong lúc chờ retry**. Một retry thành công phải chạy xác minh thực sự và đạt `VALID`, không được mặc định chấp nhận vì lần trước đã lỗi.

## 11. Chữ ký hợp lệ chưa đủ: chống replay và ràng buộc nghiệp vụ

Chữ ký có thể đúng nhưng **yêu cầu không còn được phép thực hiện**. Ví dụ kẻ tấn công ghi lại một yêu cầu thanh toán hợp lệ và gửi lại sau đó. Nếu hệ thống chỉ kiểm tra chữ ký mà không kiểm tra uniqueness/freshness, một thông điệp đã ký hợp lệ vẫn có thể bị phát lại.

Với giao thức cần chống replay, cân nhắc kiểm tra:

- **Thời hạn:** `issuedAt`, `expiresAt` hoặc timestamp phù hợp (được đưa vào dữ liệu ký).
- **Nonce hoặc event ID:** định danh duy nhất được ghi nhận để từ chối lặp lại.
- **Audience, tenant, resource, operation:** đảm bảo thông điệp được ký cho đúng dịch vụ và mục đích sử dụng.
- **Authorization:** chủ thể gắn với public key hiện có được phép thực hiện hành động đó không?
- **Tính toàn vẹn của metadata:** thông tin ảnh hưởng quyết định bảo mật phải nằm trong nội dung ký hoặc được ràng buộc mật mã theo giao thức.

**Thứ tự triển khai:** đọc và kiểm tra giới hạn dữ liệu → xác định khóa tin cậy → xác minh chữ ký → kiểm tra chính sách chống replay/ủy quyền → thực hiện nghiệp vụ. Các dữ liệu đầu vào chưa được xác minh không được sử dụng để thực hiện side effect nhạy cảm.

Một endpoint có thể trả `VALID` về mặt mật mã nhưng trả lỗi ở tầng **authorization** do request quá hạn, đã xử lý hoặc sai quyền. Đây không phải lỗi `Signature.verify`; không nên trộn hai tầng thành một kết quả mơ hồ.

## 12. Kiểm thử tự động những nhánh bắt buộc phải từ chối

Một bộ test tối thiểu cho middleware xác minh chữ ký nên có:

| Test case | Mong đợi |
| --- | --- |
| Đúng payload, signature, trusted key | Xác minh `VALID` |
| Sửa 1 byte payload | Không được accepted |
| Dùng public key khác | Không được accepted |
| Dữ liệu Base64 không hợp lệ | `INVALID_INPUT`, không được accepted |
| Chữ ký bị cắt ngắn | `INVALID_INPUT` hoặc từ chối tương ứng |
| Signature đủ độ dài nhưng sai | `INVALID_SIGNATURE` hoặc lỗi verify, không được accepted |
| Payload chữ ký bị thiếu | `INVALID_INPUT`, không được accepted |
| Không có trusted public key | `CONFIG_ERROR`, không được accepted |
| Key sai thuật toán/curve | `VERIFICATION_ERROR` hoặc lỗi khóa tương ứng, không được accepted |
| Thuật toán không được runtime hỗ trợ | Từ chối và cảnh báo nội bộ |
| Giao thức không thống nhất context/prehash | Xác minh thất bại, không được fallback |
| Dữ liệu vượt giới hạn | Từ chối trước khi tiêu tốn tài nguyên lớn |
| Dữ liệu hợp lệ về chữ ký nhưng đã hết hạn/replay | Từ chối bởi policy/authorization |

**Đặc biệt quan trọng:** Các test âm tính phải assert rằng **không thực hiện side effect** (không cập nhật số dư, không ghi đơn hàng, không cấp quyền) khi kết quả xác minh không đạt. Chỉ assert “có exception” là chưa đủ nếu code phía sau vẫn tiếp tục thực hiện giao dịch.

Nên có test tích hợp dùng key/tài liệu từ hệ thống khác và test vectors chính thức của RFC 8032 để xác nhận tương thích encoding, khóa, chữ ký và biến thể EdDSA. Tránh chỉ dùng key pair được sinh trong cùng một process nếu mục tiêu là kiểm tra liên thông nhiều implementation.

## 13. Những lỗi lập trình hay gặp

1. **`catch (Exception) { return true; }`:** biến sự cố thành chấp nhận; tuyệt đối tránh.
2. **Không gọi `verify(...)` khi request thiếu signature:** dữ liệu chưa được chứng minh hợp lệ, phải từ chối.
3. **Nhận public key tùy ý trong request:** có thể xác minh chữ ký tự ký của kẻ gửi; phải có registry/chain tin cậy.
4. **Dùng thuật toán từ request không qua allowlist:** tạo nguy cơ algorithm confusion và downgrade.
5. **Kiểm tra độ dài cố định 64 cho mọi thuật toán:** sai với Ed448 (114 byte) và nhiều họ chữ ký khác.
6. **Băm hoặc serialize lại payload không theo giao thức:** verifier nhận bytes khác so với bên ký.
7. **Thử lần lượt nhiều decoder, nhiều key hoặc mode khi chữ ký sai:** che giấu lỗi giao thức; cần lựa chọn theo policy tin cậy.
8. **Bỏ qua `SignatureException` và chạy tiếp:** exception có nghĩa xác minh không hoàn tất thành công.
9. **Nhầm `VALID` với “được phép giao dịch”:** còn phải kiểm tra quyền, hạn dùng, nonce/replay.
10. **Đưa stack trace hoặc private-key bytes ra response/log:** rò rỉ thông tin kỹ thuật và bí mật; dùng logging an toàn.
11. **Dựa vào một khóa đã hết hiệu lực vì muốn duy trì tương thích:** policy rotation phải xác định thời gian và phạm vi được phép.
12. **Coi thiếu khóa hoặc provider là lỗi “tạm chấp nhận”:** phải fail closed và cảnh báo, không thay thế xác minh bằng cờ cấu hình dễ lạm dụng.

## 14. Checklist trước khi đưa vào production

- [ ] Public key chỉ đến từ registry/keystore/chứng chỉ tin cậy, đã kiểm tra policy.
- [ ] Thuật toán và biến thể chữ ký được chọn từ allowlist/giao thức, không tự do từ request.
- [ ] Message bytes đúng theo nội dung đã ký; thống nhất UTF-8/canonicalization khi cần.
- [ ] Chữ ký được decode theo định dạng protocol đã quy định, không bỏ qua lỗi Base64.
- [ ] Áp dụng giới hạn kích thước request và chữ ký trước các phép xử lý nặng.
- [ ] Xử lý **cả** `verify=false` và ngoại lệ JCA bằng quyết định từ chối.
- [ ] Trạng thái không phải `VALID` không được thực hiện side effect.
- [ ] Khóa thiếu/hết hiệu lực hoặc provider lỗi đều không tạo đường bypass.
- [ ] Nếu dùng Ed25519ctx/ph hoặc Ed448, cấu hình mode/context và độ dài tương ứng đúng giao thức.
- [ ] Có kiểm tra thời hạn, nonce/replay, audience, scope và authorization sau khi xác minh.
- [ ] Log/alert nội bộ đủ điều tra nhưng không lộ private key, payload bí mật hoặc chi tiết kỹ thuật ra client.
- [ ] Có automated negative tests và kiểm tra trên JDK/provider production tương ứng.

**Kết luận:** Tích hợp chữ ký an toàn không chỉ là gọi `Signature.verify`. Nó cần một luồng **fail closed** có phân loại lỗi, khóa tin cậy, dữ liệu nguyên vẹn và chính sách kiểm soát quyền. Chỉ `Signature.verify(...) == true` với đầu vào, thuật toán và public key đáng tin cậy mới cho phép **tiếp tục** tới bước kiểm tra nghiệp vụ — tuyệt đối không dùng exception hoặc lỗi cấu hình như lý do để bỏ qua xác minh.

## Tài liệu chính thức và chuẩn hiện hành

- [Oracle Java SE 27 — Signature](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/Signature.html): `initVerify`, `update`, `verify`, giá trị boolean và `SignatureException`.
- [Oracle Java SE 27 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/KeyPairGenerator.html): tạo cặp khóa public/private phục vụ ký số.
- [Oracle Java SE 27 — Base64.Decoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Base64.Decoder.html): decode Base64 và `IllegalArgumentException` với dữ liệu không hợp lệ.
- [Oracle Java SE 27 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): cấu trúc JCA, providers, `Signature`, `KeyStore` và keys.
- [OpenJDK JEP 339 — EdDSA in Java 15](https://openjdk.org/jeps/339): Ed25519/Ed448 được hỗ trợ chính thức từ Java 15.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): quy tắc Ed25519, Ed448, chữ ký 64/114 byte và test vectors.

Bài học chỉ sử dụng những API và nguyên tắc bảo mật vẫn còn áp dụng trong Java hiện đại, không sử dụng kỹ thuật legacy hay preview đã hết hiệu lực.
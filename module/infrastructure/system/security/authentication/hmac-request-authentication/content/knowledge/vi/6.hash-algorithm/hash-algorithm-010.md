# Kiểm thử algorithm trong xác thực HMAC request

> **Chương:** Hash algorithm  
> **Đề bài:** Kiểm thử algorithm  
> **Bối cảnh:** Hệ thống xác thực HTTP request bằng HMAC với shared secret và canonical request chứa phương thức, URI, header hoặc body theo hợp đồng ký. Nội dung hướng dẫn kiểm thử thuật toán hash/HMAC ở mức byte và ở ranh giới ứng dụng, kể cả key rotation, timestamp/nonce chống replay, proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Tại sao cần kiểm thử thuật toán?

Trong xác thực HTTP bằng HMAC, sender tính chữ ký cho một thông điệp canonical, sau đó receiver tính lại chữ ký bằng shared secret tương ứng:

\[
T = \operatorname{HMAC\text{-}SHA256}(K,\operatorname{Canonical}(R)).
\]

Trong đó `K` là khóa bí mật, `R` là request, `T` là tag xác thực. Với một cấu hình thường dùng, `HMAC-SHA-256` tạo **32 byte tag**. Tag có thể được mã hóa Base64URL không padding để truyền trên HTTP (32 byte thường thành **43 ký tự**). Bên nhận cần đối chiếu **byte tag sau giải mã**.

Một tính toán sai có thể đến từ nhiều lớp khác nhau:

- **Sai algorithm**: dùng `SHA-256` thông thường thay vì `HmacSHA256`, chọn tên thuật toán sai hoặc dùng nhầm provider.
- **Sai byte đầu vào**: sender ký raw body, receiver ký JSON đã serialize lại; URI hoặc header bị proxy thay đổi.
- **Sai key**: key ID trỏ nhầm secret, dùng key phiên bản cũ, secret lấy từ cấu hình sai môi trường.
- **Sai cách so sánh**: chấp nhận tag cắt ngắn ngoài hợp đồng, giải mã Base64 mơ hồ hoặc so sánh không thích hợp.
- **Thiếu bước xác thực**: chỉ kiểm tra MAC nhưng không kiểm tra timestamp, nonce, key status hoặc audience.
- **Thiếu phân quyền**: MAC hợp lệ nhưng người gửi không được thực hiện thao tác trên tài nguyên.

Do đó, **test thuật toán** cần nhiều hơn một kiểm tra “client ký và server verify thành công”. Nếu sender và receiver cùng mắc một lỗi, bài test khép kín có thể vẫn xanh. Bài học dùng **known-answer test** độc lập, kiểm thử bất biến, kiểm thử dữ liệu biên, kiểm thử đa provider và kiểm thử đầu cuối.

### Kết quả người học cần đạt

1. Phân biệt **hash không khóa** (SHA-256) và **MAC có khóa** (HMAC-SHA-256), hiểu loại test thích hợp cho từng thuật toán.
2. Kiểm tra kết quả JCA bằng các test vector chuẩn, không chỉ kiểm tra hai hàm nội bộ giống nhau.
3. Viết được các trường hợp sai khác byte, secret, thuật toán, encoding, provider và định dạng tag.
4. Thiết kế fixture canonical request cố định để phát hiện sai thứ tự trường, separator, URI và body digest.
5. Chỉ ra phần nào được kiểm tra bởi thuật toán và phần nào thuộc security pipeline: timestamp/nonce, key rotation, gateway, authorization.
6. Biết cách tổ chức test ổn định trong CI và cách tránh các “bài test xanh giả”.

## 2. Xác định rõ đối tượng cần kiểm thử

Hash và HMAC thường cùng xuất hiện trong một hợp đồng ký HTTP, nhưng chúng **không đồng nhất**:

| Thành phần | Đầu vào | Đầu ra điển hình | Thuộc tính được kiểm thử |
|---|---|---|---|
| `SHA-256` | Dãy byte của raw HTTP body | Digest 32 byte | Cùng byte → cùng digest; khớp vector chuẩn; thay byte làm digest khác với xác suất áp đảo |
| `HMAC-SHA-256` | Secret + canonical request bytes | Tag 32 byte | Khớp vector độc lập; nhạy với key/message; so sánh đúng; tái lập giữa provider |
| `Base64URL` | 32 byte tag | Chuỗi 43 ký tự không padding | Encode/decode và kiểm tra dạng canonical |
| `Canonicalization` | Method, target, signed headers, body digest, metadata | Byte UTF-8 có cấu trúc xác định | Chính xác từng trường, thứ tự, LF, encoding, xử lý dữ liệu biên |
| `Key lookup` | Client ID, key ID, audience | Secret và trạng thái | Không tra nhầm principal/key/version |
| `Replay protection` | Timestamp/nonce đã ký | Chấp nhận/từ chối theo thời gian và kho nonce | Cửa sổ thời gian; ghi nonce nguyên tử; tính nhất quán nhiều node |
| `Authorization` | Principal + action + resource | Allow/deny | Người biết secret vẫn phải có quyền nghiệp vụ |

Không nên viết một test duy nhất cho tất cả: lỗi SHA-256, lỗi HMAC, lỗi canonical hóa và lỗi phân quyền có triệu chứng HTTP tương tự nhưng cách sửa khác nhau.

### 2.1. Thuật toán được chọn theo hợp đồng, không do client tùy ý đổi

Ví dụ hợp đồng ký phiên bản `hmac-v1` quy định **HMAC-SHA-256 đầy đủ 32 byte** với tên thuật toán JCA:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
~~~

`MessageDigest.getInstance("SHA-256")` chỉ dùng cho **digest của body**:

~~~java
byte[] digest = MessageDigest.getInstance("SHA-256").digest(rawBody);
~~~

Hai API này nhận đầu vào khác nhau. Không sử dụng `SHA256(secret + message)` làm một “biến thể HMAC tự chế”. Cũng không chấp nhận algorithm do người gọi tự truyền trong header nếu chưa có chính sách cố định phiên bản được server phê duyệt.

## 3. Những lớp kiểm thử và bằng chứng tương ứng

| Lớp | Cần chứng minh điều gì? | Oracle (nguồn kỳ vọng) |
|---|---|---|
| **Known-answer test (KAT)** | JCA tính đúng HMAC-SHA-256 | Tag công bố độc lập trong RFC 4231 |
| **Hash vector** | SHA-256 body digest không bị nhầm với HMAC | SHA-256 của chuỗi đã biết |
| **API/lifecycle** | `Mac.init/update/doFinal/reset` dùng đúng thứ tự, trạng thái | Hợp đồng JCA và test cùng dữ liệu chia nhiều chunk |
| **Encoding** | UTF-8, Base64URL/hex tạo đúng byte và độ dài | Fixture byte → biểu diễn đã khóa cứng |
| **Canonical request** | Chuỗi ký đúng thứ tự trường, raw URI/body, delimiter | Golden fixture viết độc lập với code sản xuất |
| **Negative/tamper** | Bất kỳ trường an ninh quan trọng bị đổi đều không xác thực | Request test cố định và tag ban đầu |
| **Cross-provider/cross-language** | Client Java, server Java/khác ngôn ngữ có đầu ra tương thích | Cùng fixture, triển khai độc lập |
| **Authentication pipeline** | Chữ ký đúng vẫn phải kiểm tra key status, timestamp, nonce | Test clock và nonce store điều khiển được |
| **Gateway/integration** | HTTP request tại điểm verify là byte theo signing contract | Request gửi qua tuyến proxy thực tế và số liệu test |
| **Authorization/business** | Authenticated principal chỉ được thao tác trong phạm vi | Chính sách truy cập và quyền sở hữu tài nguyên |

Một **test sender.sign(request) rồi receiver.verify(request, signature)** là cần thiết, nhưng **chưa đủ**. Nếu cả sender và receiver dùng sai cùng thứ tự canonical field, test vẫn có thể pass. Phải có vector/fixture độc lập và kiểm thử qua ranh giới thực tế.

## 4. Known-answer test bằng RFC 4231

Một known-answer test đặt trước **khóa và thông điệp đã biết**, chạy thư viện mật mã, rồi so với tag đã công bố độc lập. RFC 4231 cung cấp các test vector HMAC-SHA-224/256/384/512.

Đối với **HMAC-SHA-256**, dùng tối thiểu hai vector sau:

| Test case | Key | Data | Expected tag (hex, 32 byte) |
|---|---|---|---|
| RFC 4231 case 1 | 20 byte có giá trị `0x0b` | ASCII `Hi There` | `b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7` |
| RFC 4231 case 2 | ASCII `Jefe` | ASCII `what do ya want for nothing?` | `5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843` |

Các khóa của test vector được chọn để **kiểm tra thuật toán**, không phải khóa có entropy phù hợp cho production. Một trường hợp test như `Jefe` có thể quá yếu để dùng làm shared secret thực tế.

### 4.1. Các thông số cần ghi nhận khi test JCA

- **Algorithm ID**: `HmacSHA256` (không nhầm với `SHA-256`).
- **Provider** thực tế sau khi khởi tạo khóa; provider tùy runtime.
- **MAC length**: 32 byte với full HMAC-SHA-256.
- **Byte encoding**: chuỗi test ASCII tương thích UTF-8.
- **Test key bytes** và **test message bytes** đã cố định, không dùng charset mặc định.
- **Expected raw tag** đối chiếu theo bytes (giải mã hex test vector).

Trong Java 17+, `HexFormat` có thể parse và format hex trực tiếp; `MessageDigest.isEqual` phù hợp để đối chiếu byte tag khi đã kiểm tra độ dài. Nếu tag không khớp, bài kiểm thử phải **FAIL**. Không in secret production hay dữ liệu nhạy cảm vào log.

### 4.2. Kiểm tra SHA-256 riêng

Hai vector SHA-256 dễ dùng:

~~~text
SHA-256("")   =
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

SHA-256("abc") =
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Chuỗi rỗng là **mảng 0 byte**, không phải chuỗi chứa hai dấu nháy kép hoặc byte `0x00`. Với request không có body, SHA-256 body vẫn có digest 32 byte và chuỗi hex 64 ký tự đúng như vector trên.

## 5. Chương trình kiểm thử tự chạy bằng Java 17

Ví dụ sau dùng **chỉ JDK 17+**, không cần JUnit/Gradle. Nó cố định expected HMAC bằng RFC 4231 và kiểm tra thêm stream, reset, thay đổi key/message, SHA-256, Base64URL và canonical text. Các giá trị khóa trong test được cố định **chỉ để kiểm thử**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacAlgorithmSelfTest {
    private static final String ALG = "HmacSHA256";
    private static final HexFormat HEX = HexFormat.of();

    public static void main(String[] args) throws GeneralSecurityException {
        knownAnswerCase1();
        knownAnswerCase2();
        sha256Vectors();
        streamingAndReset();
        mutationAndEncoding();
        canonicalFixture();
        System.out.println("ALL PASS (6 groups)");
    }

    private static byte[] hmac(byte[] key, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALG);
        mac.init(new SecretKeySpec(key, ALG));
        require(mac.getMacLength() == 32, "MAC length");
        return mac.doFinal(message);
    }

    private static void knownAnswerCase1() throws GeneralSecurityException {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] message = utf8("Hi There");
        byte[] expected = HEX.parseHex(
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7");
        equal(expected, hmac(key, message), "RFC 4231 case 1");
        System.out.println("PASS RFC 4231 case 1");
    }

    private static void knownAnswerCase2() throws GeneralSecurityException {
        byte[] key = utf8("Jefe");
        byte[] message = utf8("what do ya want for nothing?");
        byte[] expected = HEX.parseHex(
                "5bdcc146bf60754e6a042426089575c75"
              + "a003f089d2739839dec58b964ec3843");
        equal(expected, hmac(key, message), "RFC 4231 case 2");
        System.out.println("PASS RFC 4231 case 2");
    }

    private static void sha256Vectors() throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        equal(HEX.parseHex(
                "e3b0c44298fc1c149afbf4c8996fb924"
              + "27ae41e4649b934ca495991b7852b855"),
              digest.digest(new byte[0]), "SHA-256 empty body");
        equal(HEX.parseHex(
                "ba7816bf8f01cfea414140de5dae2223"
              + "b00361a396177a9cb410ff61f20015ad"),
              digest.digest(utf8("abc")), "SHA-256 abc");
        System.out.println("PASS SHA-256 body vectors");
    }

    private static void streamingAndReset()
            throws GeneralSecurityException {
        byte[] key = utf8("Jefe");
        byte[] a = utf8("what do ya want ");
        byte[] b = utf8("for nothing?");
        byte[] all = utf8("what do ya want for nothing?");
        byte[] expected = hmac(key, all);

        Mac mac = Mac.getInstance(ALG);
        mac.init(new SecretKeySpec(key, ALG));
        mac.update(a);
        mac.update(b);
        equal(expected, mac.doFinal(), "chunked MAC");

        // doFinal đưa engine về trạng thái đã init với cùng khóa.
        equal(expected, mac.doFinal(all), "reuse after doFinal");

        // reset xóa dữ liệu đang nạp, nhưng giữ khóa đã init.
        mac.update(utf8("discard this"));
        mac.reset();
        equal(expected, mac.doFinal(all), "reset discards partial data");
        System.out.println("PASS update/doFinal/reset");
    }

    private static void mutationAndEncoding()
            throws GeneralSecurityException {
        byte[] key = HEX.parseHex(
                "000102030405060708090a0b0c0d0e0f"
              + "101112131415161718191a1b1c1d1e1f");
        byte[] message = utf8("POST\n/v1/payments");
        byte[] tag = hmac(key, message);
        require(tag.length == 32, "full tag length");

        String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(tag);
        require(encoded.length() == 43, "base64url tag length");
        equal(tag, Base64.getUrlDecoder().decode(encoded),
                "base64url round-trip");

        byte[] changedMessage = utf8("PUT\n/v1/payments");
        require(!MessageDigest.isEqual(tag, hmac(key, changedMessage)),
                "message tampering must change tag");

        byte[] changedKey = key.clone();
        changedKey[0] ^= 0x01;
        require(!MessageDigest.isEqual(tag, hmac(changedKey, message)),
                "key change must change tag");
        System.out.println("PASS tag size/encoding/mutation");
    }

    private static void canonicalFixture()
            throws GeneralSecurityException {
        String bodyHash = HEX.formatHex(
                MessageDigest.getInstance("SHA-256")
                  .digest(new byte[0]));
        String actual = String.join("\n",
                "hmac-v1",
                "POST",
                "/v1/payments?currency=VND",
                "application/json",
                "merchant-17",
                "key-test-1",
                "1795824000",
                "b75sZVQmhTBcfnX-bNbGqw",
                bodyHash);
        // Golden literal viết độc lập, tránh việc signer và
        // verifier cùng dùng một helper sai mà test vẫn PASS.
        String golden =
                "hmac-v1\n"
              + "POST\n"
              + "/v1/payments?currency=VND\n"
              + "application/json\n"
              + "merchant-17\n"
              + "key-test-1\n"
              + "1795824000\n"
              + "b75sZVQmhTBcfnX-bNbGqw\n"
              + "e3b0c44298fc1c149afbf4c8996fb924"
              + "27ae41e4649b934ca495991b7852b855";
        require(golden.equals(actual), "canonical fixture");
        require(!actual.endsWith("\n"), "no final LF");
        System.out.println("PASS canonical fixture");
    }

    private static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static void equal(byte[] expected, byte[] actual,
                              String label) {
        require(MessageDigest.isEqual(expected, actual), label);
    }

    private static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("FAIL " + label);
        }
    }
}
~~~

Đặt mã trong file `HmacAlgorithmSelfTest.java` và chạy (môi trường người học):

~~~bash
javac HmacAlgorithmSelfTest.java
java HmacAlgorithmSelfTest
~~~

Kết quả kỳ vọng:

~~~text
PASS RFC 4231 case 1
PASS RFC 4231 case 2
PASS SHA-256 body vectors
PASS update/doFinal/reset
PASS tag size/encoding/mutation
PASS canonical fixture
ALL PASS (6 groups)
~~~

Chương trình sẽ ném `AssertionError` khi một kiểm tra sai. Việc kiểm chứng vector bằng thuật toán độc lập tránh một kiểu “test xanh giả”: tự sinh expected bằng chính hàm đang được test. Phần `canonicalFixture` mới là **fixture cấu trúc minh họa**; với hệ thống thật, cần lưu thêm golden vector được tạo độc lập giữa client và server cho toàn bộ HTTP request.

**Phạm vi mẫu:** mã trên không chạy HTTP server, không tra key ID và không có nonce store. Những lớp đó phải được kiểm thử riêng; việc chương trình in `ALL PASS` **không đồng nghĩa** API production an toàn.

## 6. Kiểm thử lựa chọn provider và vòng đời JCA

Trong Java, tên của HMAC-SHA-256 thường là `HmacSHA256` ở `javax.crypto.Mac`. Hãy kiểm tra provider sau khi đã khởi tạo key:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(testKey, "HmacSHA256"));

System.out.println(mac.getAlgorithm());
System.out.println(mac.getProvider().getName());
System.out.println(mac.getMacLength());
~~~

| Ca thử | Mong đợi |
|---|---|
| `Mac.getInstance("HmacSHA256")` trên runtime hỗ trợ | Có engine để khởi tạo |
| Algorithm/provider không tồn tại hoặc không hỗ trợ | `NoSuchAlgorithmException`/`NoSuchProviderException` theo overload |
| `doFinal` trước `init` | `IllegalStateException` |
| Key không được provider chấp nhận | `InvalidKeyException` trong `init` |
| `update(a), update(b), doFinal()` | Trùng `doFinal(a || b)` |
| `doFinal` lần nữa với cùng dữ liệu sau lần kết thúc | Trùng kết quả, vì engine được reset về trạng thái sau init |
| `reset` sau khi update dữ liệu dở | Bỏ phần message đã nạp; **vẫn giữ khóa** |
| Cùng vector trên hai provider hỗ trợ thuật toán và dạng key | Cùng tag; tên provider có thể khác |
| Hai client/luồng đồng thời | Không trộn khóa/dữ liệu giữa request |

**Không chia sẻ một `Mac` static cho nhiều request song song**: `Mac` là engine có trạng thái, chưa được bảo đảm thread-safe. Dùng `Mac.getInstance` và `init` riêng cho mỗi phép tính là cách dễ kiểm tra nhất; thread-local/pool nếu sử dụng phải có quản lý vòng đời chặt chẽ.

Không nên bắt buộc một provider có tên `SunJCE` ở mọi môi trường. Môi trường HSM/PKCS#11 hoặc runtime theo chính sách riêng có provider khác. Nếu yêu cầu bắt buộc pin provider, hãy xác minh availability và tính tương thích của `SecretKey` khi ứng dụng khởi động.

### 6.1. Kiểm thử cross-provider và cross-language

1. Cố định **raw key bytes, canonical bytes, algorithm và output encoding**.
2. Tính tag bằng provider Java A; tính lại bằng provider Java B hoặc implementation thuộc ngôn ngữ khác.
3. So sánh **raw tag bytes**. Nếu khác, kiểm tra ngay byte đầu vào, chuỗi key, algorithm và encoding trước khi suy đoán thư viện sai.
4. Ghi nhận phiên bản runtime/provider và sử dụng vector công khai làm chuẩn chung.

Một test thành công xuyên provider có giá trị đặc biệt khi client Java, cổng thanh toán bên thứ ba, gateway và backend khác ngôn ngữ cùng ký một hợp đồng HTTP.

## 7. Golden fixture cho canonical request

Trong HTTP HMAC, **đúng thuật toán nhưng sai canonicalization vẫn tạo MAC sai**. Hợp đồng ký phải nêu rõ thành phần nào được ký, thứ tự, charset, cách chuẩn hóa URI/header, quy tắc body, ký tự phân cách và cách encode tag.

Một hợp đồng ứng dụng minh họa `hmac-v1`:

| Dòng | Dữ liệu | Quy tắc |
|---|---|---|
| 1 | Phiên bản `hmac-v1` | Literal |
| 2 | Method | HTTP token, ví dụ `POST` |
| 3 | Raw target | Encoded path + query chưa thay đổi, ví dụ `/v1/payments?currency=VND` |
| 4 | Content-Type | Trim hai đầu, lowercase theo `Locale.ROOT`, vắng mặt là chuỗi rỗng |
| 5 | Client ID | `X-Client-Id` đã quy định định dạng |
| 6 | Key ID | `X-Key-Id` |
| 7 | Timestamp | `X-Timestamp`, Unix seconds thập phân canonical |
| 8 | Nonce | `X-Nonce`, Base64URL không padding của 16–32 byte CSPRNG |
| 9 | Body digest | SHA-256 của **raw body bytes**, dạng hex chữ thường |

Các dòng được nối bằng **LF** (`\n`), không có LF ở cuối và không cho phép CR/LF lồng trong trường. Canonical text dùng **UTF-8**; tag truyền đi là `Base64URL` không padding của 32 byte HMAC-SHA-256. `X-Signature` không được đưa vào chính chuỗi ký trong hợp đồng minh họa.

**Golden fixture cần kiểm tra đầy đủ các byte**, không chỉ giá trị sau parse:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-test-1
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-tag>

~~~

Với **body rỗng**, canonical text là:

~~~text
hmac-v1
POST
/v1/payments?currency=VND
application/json
merchant-17
key-test-1
1795824000
b75sZVQmhTBcfnX-bNbGqw
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Không có ký tự LF cuối. Trong ví dụ, `<base64url-hmac-tag>` chỉ là chỗ giữ chỗ; chương trình hoặc test thật phải dùng tag đã tính từ **secret test** và đúng canonical bytes. Việc tự tính expected bằng cùng helper canonical hóa là không đủ; cần fixture đầu vào và expected canonical text viết độc lập.

### 7.1. Các test canonical hóa quan trọng

| Biến thể | Điều phải kiểm tra |
|---|---|
| Query `a=1&b=2` so với `b=2&a=1` | Nếu contract ký raw target, phải là chuỗi ký **khác byte** |
| Encoded slash `%2F` so với dấu `/` | Không tự giải mã/re-encode nếu contract không yêu cầu |
| Raw body `{"a":1,"b":2}` so với `{"b":2,"a":1}` | Dùng **raw bytes**, không dựa vào JSON semantic equality |
| Body rỗng so với body có khoảng trắng | SHA-256 phải khác |
| Content-Type với chữ hoa/thường | Chỉ chuẩn hóa theo quy tắc của contract |
| Duplicate signed headers | Từ chối ambiguity; không tự ghép/chọn giá trị đầu |
| Header bị thiếu | Trường bắt buộc phải được reject; riêng Content-Type có thể dùng chuỗi rỗng nếu contract cho phép |
| Timestamp số thập phân có leading zero | Từ chối nếu contract yêu cầu dạng canonical |
| Nonce chứa Base64 padding hoặc ký tự không hợp lệ | Reject theo định dạng; không sửa đầu vào |
| LF so với CRLF, có LF cuối | Canonical bytes phải khớp **chính xác** hợp đồng |

Kiểm tra **golden fixture** cũng cần xác định các bước normalize diễn ra ở đâu trong đường đi HTTP. Ở điểm verify, framework có thể đã decode URI hoặc parse body; hãy ghi rõ “dữ liệu nào được ký” và không lấy lại từ đối tượng DTO đã deserialize nếu contract ký raw bytes.

## 8. Kiểm thử đối chiếu chữ ký và dữ liệu đầu vào xấu

Một verifier MAC cần kiểm tra **độ dài và dạng encoding** trước khi đối chiếu tag:

~~~java
import java.security.MessageDigest;
import java.util.Base64;

// "expected" là raw HMAC 32 byte đã tính lại bằng secret đúng.
// "signatureHeader" là chữ ký do HTTP client cung cấp.
boolean matches(byte[] expected, String signatureHeader) {
    if (expected == null || expected.length != 32
            || signatureHeader == null || signatureHeader.length() != 43) {
        return false;
    }
    final byte[] received;
    try {
        received = Base64.getUrlDecoder().decode(signatureHeader);
    } catch (IllegalArgumentException e) {
        return false;
    }
    if (received.length != 32
            || !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(received).equals(signatureHeader)) {
        return false;
    }
    return MessageDigest.isEqual(expected, received);
}
~~~

Lưu ý đây là **đoạn method minh họa**, không phải một file Java độc lập. Trong code, `String.equals` chỉ kiểm tra **biểu diễn Base64URL canonical**; `MessageDigest.isEqual` mới so sánh **tag bytes**. Hệ thống phải giới hạn độ dài đầu vào trước khi decode và không log expected tag.

### 8.1. Test case “được sửa một thành phần đã ký”

Sau khi lấy chữ ký hợp lệ của một request, thử thay đổi **chỉ một** thành phần, giữ nguyên tag:

| Thay đổi | Kỳ vọng |
|---|---|
| `POST` thành `GET` | Fail signature |
| `/v1/payments` thành `/v1/refunds` | Fail signature |
| Thêm, bỏ hoặc đảo tham số query được ký | Fail signature theo raw target contract |
| `amount` trong body thay đổi | Fail signature |
| Thay byte body nhưng JSON vẫn tương đương ngữ nghĩa | Fail nếu ký raw body |
| Thay `X-Client-Id` | Không tìm được key phù hợp hoặc MAC fail |
| Thay `X-Key-Id` | Không tìm được key phù hợp hoặc MAC fail |
| Thay `X-Timestamp` hoặc `X-Nonce` | MAC fail; ngoài ra còn quy tắc thời gian/nonce |
| Cắt một byte tag hoặc thêm padding Base64URL | Reject định dạng |
| Cùng dữ liệu, chữ ký encode theo chuẩn Base64 khác | Reject nếu contract yêu cầu Base64URL canonical |

**Ngoại lệ có chủ đích:** Nếu contract chuẩn hóa `Content-Type` thành chữ thường sau khi trim, thay đổi chỉ khác chữ hoa/thường hoặc khoảng trắng đầu/cuối có thể cho **cùng canonical string**. Điều đó không phải lỗi test; hãy phân biệt trường được chuẩn hóa với trường phải bảo toàn raw bytes.

### 8.2. Negative tests không biến thành tấn công brute force

Chỉ cần dùng **các test secrets được cấp riêng** và số ca hữu hạn để thử sai key/algorithm. Không cần thử hàng loạt khóa trên production hoặc đo thời gian API để “chứng minh” HMAC mạnh. Test thuật toán dựa vào RFC vector, kiểm soát nguồn sinh khóa và thiết kế verifier chứ không dùng brute force thực tế làm thước đo an toàn.

## 9. Key rotation và thuật toán: kiểm thử theo trạng thái khóa

Chữ ký HMAC đúng về toán học **chưa bảo đảm** request được chấp nhận. Server phải tra `(clientId, keyId, audience)` để lấy secret và trạng thái:

| Trạng thái khóa | Ý nghĩa | Test mong đợi |
|---|---|---|
| `ACTIVE` | Khóa hiện tại được phép xác minh | Chữ ký, timestamp, nonce hợp lệ có thể tạo principal |
| `VERIFY_ONLY` | Khóa cũ trong cửa sổ chuyển tiếp ngắn | Có thể verify trước deadline; bị từ chối sau deadline |
| `REVOKED` | Khóa đã bị thu hồi | Từ chối kể cả HMAC đúng |
| Key ID không thuộc client | Bản ghi sai principal/audience | Từ chối; không dùng secret client khác |
| Key ID không tồn tại | Không có bản ghi | Từ chối; không fallback default secret |

Các ca test phải chạy cả **trước**, **đúng ranh giới** và **sau** thời điểm hết hạn của key; dùng đồng hồ giả lập để tránh test thất thường. Nếu bên nhận pin thuật toán theo key record hoặc version, phải từ chối chuyển đổi không được phê duyệt. Khi secret bị lộ, quy trình revoke phải có hiệu lực không chờ overlap hết hạn thông thường.

Mỗi lượt verify dùng key cụ thể phải `Mac.init` bằng **khóa của phiên đó**; `mac.reset()` **không** đổi khóa. Nếu ứng dụng pool `Mac`, cần test không bao giờ dùng khóa của tenant A để verify tenant B.

## 10. Timestamp, nonce và idempotency: test ngoài thuật toán

HMAC **không tự chống replay**. Kẻ tấn công có bản sao request/tag hợp lệ có thể phát lại nguyên dữ liệu nếu receiver chỉ kiểm tra MAC.

Chính sách minh họa:

~~~text
now - 300 <= signedTimestamp <= now + 300
verify HMAC-SHA-256 trên đúng canonical bytes
reserve nonce sau MAC thành công với khóa (clientId, keyId, nonce)
insert-if-absent nguyên tử, TTL đủ che phủ khoảng timestamp hợp lệ
~~~

Với cửa sổ ±300 giây, TTL khoảng **600 giây** kể từ lúc nhận nonce lần đầu là một lựa chọn minh họa để bao phủ toàn bộ khoảng timestamp còn có thể hợp lệ. Hệ thống thật cần xét độ lệch đồng hồ, queue delay và nguồn thời gian.

| Ca test | Kỳ vọng |
|---|---|
| Timestamp bằng `now`, MAC đúng, nonce mới | Có thể chấp nhận |
| Timestamp nhỏ hơn `now - 300` | Reject |
| Timestamp lớn hơn `now + 300` | Reject |
| Timestamp đúng ranh giới `now ± 300` | Theo dấu `≤` của hợp đồng |
| Replay cùng MAC, timestamp, nonce | Request thứ hai bị reject |
| Hai request cùng nonce gửi đồng thời tới hai node | Tối đa một reserve thành công |
| Nonce store lỗi hoặc mất kết nối | **Fail closed**, không bỏ qua replay check |
| MAC sai nhưng nonce trùng nonce hợp lệ | Không chiếm chỗ nonce trước khi MAC được xác minh |
| Retry hợp lệ với timestamp/nonce mới | Có thể xác thực lại, nhưng cần **idempotency** để tránh lặp giao dịch |

Kiểm thử không được dựa vào `Thread.sleep` kéo dài để chờ hết hạn. Dùng `Clock` hoặc nguồn thời gian được tiêm vào, cùng nonce store giả lập có semantics nguyên tử khi unit test và Redis/shared store thực trong integration test. Nếu dùng in-memory store trong unit test, test đó **không chứng minh** an toàn qua nhiều node.

## 11. Kiểm thử proxy/gateway và tương thích HTTP

Kết quả HMAC từ JCA có thể chính xác nhưng receiver vẫn reject vì request bị thay đổi trong hạ tầng:

| Thành phần hạ tầng | Tình huống test | Rủi ro/điều cần chứng minh |
|---|---|---|
| API gateway rewrite | `/external/v1` → `/v1` | Điểm verify phải dùng đúng target sender đã ký hoặc contract chuẩn hóa rõ |
| Path normalization | `%2F` so với `/`, `%20`, ký tự `+` | Không âm thầm decode/re-encode sai |
| Query parsing | Đảo thứ tự, query trùng tên, query rỗng | Raw query được giữ hoặc được canonical hóa có quy tắc |
| Header transformation | Duplicate header, case, whitespace, bổ sung `Content-Type` | Signed headers nhất quán và không mơ hồ |
| Body transformation | Gzip/ungzip, UTF-8, JSON reserialize | Raw body hash dùng cùng byte theo contract |
| HTTP/2 → HTTP/1.1 | Chuyển `:path`, authority, framing | Không mất thông tin cần ký |
| Nhiều node | Request replay qua hai instance | Nonce store tập trung và ghi nguyên tử |
| Trusted proxy metadata | Client gửi giả `X-Original-URI` | Proxy phải strip/ghi đè header do bên ngoài khai |

Đường test nên đi qua **chính cấu hình WAF/API gateway/reverse proxy/service** như production. Có thể kiểm tra raw target, body digest và tập signed header bằng test payload không nhạy cảm tại các ranh giới. Không log raw production secret, HMAC dự kiến hoặc body có thông tin cá nhân.

Lựa chọn kiến trúc thường là **verify tại edge trước khi rewrite** hoặc **sử dụng metadata gốc từ proxy đáng tin** theo hợp đồng chính thức. Không sửa lỗi HMAC bằng cách bỏ kiểm tra chữ ký.

### 11.1. Một kịch bản kiểm thử chẩn đoán

Sender ký:

~~~text
POST /public/v1/payments?b=2&a=1
~~~

Gateway đổi prefix và đảo query; backend nhìn thấy:

~~~text
POST /v1/payments?a=1&b=2
~~~

Nếu contract ký **raw request target**, hai chuỗi canonical khác nhau. Trong integration test:

1. Ghi lại **expected raw target** tại sender bằng fixture.
2. Dùng test route qua gateway và ghi nhận **target thực sự verifier sử dụng**.
3. Kiểm tra HMAC fail theo lý do đúng; không che lỗi bằng việc tự chuẩn hóa quá rộng.
4. Đưa verifier lên edge hoặc điều chỉnh cách truyền trusted original target và chạy lại test.

Khác biệt này thuộc **chuẩn hóa HTTP**, không chứng minh HMAC-SHA-256 hoặc `Mac.getInstance` bị lỗi.

## 12. Phân biệt authentication, authorization và test nghiệp vụ

Một request có chữ ký HMAC hợp lệ chứng minh bên gửi biết shared secret của key record tương ứng. Sau xác thực, principal mới được đưa vào kiểm tra quyền:

~~~text
authentication:
  principal = merchant-17
  keyId = key-2026-11
  hmac = valid
  timestamp = valid
  nonce = new

authorization:
  action = payments:create
  resource = order-123
  resourceOwner = merchant-42
  decision = DENY
~~~

Ở ví dụ trên, **thuật toán HMAC phải pass** và **authorization phải deny**, vì principal `merchant-17` không có quyền tạo thanh toán cho tài nguyên của `merchant-42`. Nếu test “chữ ký đúng thì API thành công” mà không có trường hợp khác tenant, bộ kiểm thử bỏ sót một lỗ hổng nghiêm trọng dù thuật toán hoàn hảo.

Ngược lại, khi chữ ký bị sửa, request phải bị reject **trước khi** tạo authenticated principal và trước xử lý nghiệp vụ. Phân tích log/metric nên phân biệt lỗi `invalid_signature`, `stale_timestamp`, `replayed_nonce` và `permission_denied` trong hệ thống nội bộ, nhưng response công khai phải tránh rò rỉ dữ liệu về secret/key.

## 13. Tổ chức bộ kiểm thử trong dự án và CI

Để dễ chẩn đoán, có thể tổ chức kiểm thử thành các nhóm:

~~~text
Crypto KAT:
  SHA-256 vectors
  HMAC-SHA-256 RFC 4231 cases
  provider + tag length

Canonical contract:
  golden byte fixtures
  URI/header/body transformations
  charset/encoding and separators

Verifier:
  correct and incorrect keys
  signature decode and comparison
  key ID/audience/rotation

Replay and authorization:
  boundary timestamps
  atomic nonce contention
  tenant/action/resource policies

Integration:
  HTTP/1.1 and HTTP/2
  reverse proxy/gateway route
  multiple verifier nodes
~~~

**Nguyên tắc để test không xanh giả:**

1. **Expected phải độc lập** với code đang kiểm tra: dùng RFC vector, canonical fixture viết thủ công hoặc implementation thứ hai đáng tin.
2. **Kiểm tra cả output bytes**, không chỉ độ dài, status HTTP hoặc việc method không ném exception.
3. **Cố định timestamp/nonce test**, dùng clock giả lập để kiểm tra ranh giới chính xác.
4. **Không dùng secret production**; dùng key test cố định cho vector và CSPRNG cho test cấp phát khóa.
5. **Không kiểm tra tính mạnh của CSPRNG chỉ bằng vài mẫu thống kê**; review nguồn entropy và quy trình cấp khóa.
6. **Không phụ thuộc provider cụ thể** trừ khi production có ràng buộc provider; nếu ràng buộc thì test rõ configuration.
7. **Không log raw secret hoặc tag kỳ vọng của production** khi test fail; với test dùng vector công khai thì ghi nhận nhãn test và provider là đủ.
8. **Kiểm thử khi thay dependency/JDK/gateway**: điều kiện đổi runtime/provider hoặc proxy làm tăng giá trị của cross-provider/canonical integration tests.

### 13.1. Checklist hoàn thành

| Nhóm | Điều kiện được xem là đạt |
|---|---|
| Algorithm | HMAC-SHA-256 khớp RFC 4231; SHA-256 body khớp vector |
| Byte handling | Key UTF-8, canonical text UTF-8, raw body digest, base64url/hex đúng định dạng |
| Lifecycle | init trước doFinal; không share Mac có trạng thái; reset không thay khóa |
| Tampering | Method, target, signed headers, body, timestamp và nonce bị sửa đều không hợp lệ |
| Key management | Lookup đúng client/key/audience, rotation/revocation được áp dụng |
| Replay | Chặn nonce trùng, xử lý ranh giới clock, test đồng thời nhiều node |
| Gateway | Canonical bytes đúng tại điểm verify ở tuyến triển khai thật |
| Authorization | Principal đúng key nhưng thiếu quyền vẫn bị từ chối |

## 14. Bài tập vận dụng

**Bài 1 — Phân biệt hash và HMAC:** Một người viết `MessageDigest.getInstance("SHA-256").digest(secret || body)` rồi gọi đó là chữ ký HMAC. Hãy chỉ ra lỗi thiết kế và API đúng cần dùng.

**Bài 2 — Test xanh giả:** Sender và receiver đều ghép canonical fields theo thứ tự `method, bodyHash, path` trong khi hợp đồng quy định `method, path, bodyHash`. Tại sao unit test sign–verify tự thân vẫn pass? Bạn sẽ thêm golden fixture nào?

**Bài 3 — Negative test:** Chọn một chữ ký hợp lệ cho request có body JSON. Hãy thiết kế sáu test tampering, trong đó có một test thay whitespace body mà không đổi JSON semantic.

**Bài 4 — Provider:** Hai JDK cho hai tên provider khác nhau nhưng cùng tag RFC 4231. Điều đó nói lên điều gì? Nếu một HSM từ chối `SecretKeySpec`, test nào sẽ phân biệt lỗi key type với lỗi thuật toán?

**Bài 5 — Replay race:** Hai bản sao request cùng nonce được gửi đến hai node verifier gần đồng thời. Thiết kế phép ghi nonce nào được coi là đúng, và vì sao “GET rồi SET” có thể fail?

**Bài 6 — HMAC hợp lệ nhưng bị từ chối:** Request ký đúng bằng key `REVOKED` hoặc truy cập tài nguyên tenant khác. Với mỗi trường hợp, bước nào phải từ chối và vì sao đó không phải lỗi `Mac.getInstance`?

## 15. Ghi nhớ

**Kiểm thử algorithm** trong HMAC request authentication phải chứng minh cả **tính đúng mật mã** và **tính đúng byte giao thức**. Bắt đầu bằng test vector độc lập cho SHA-256 và HMAC-SHA-256, xác minh `Mac.getInstance/init/doFinal`, tag length, encoding và provider. Tiếp đó, cố định canonical request bằng golden fixtures, thử thay đổi method/URI/header/body, kiểm tra key rotation và chống replay, chạy tích hợp qua proxy/gateway và xác nhận authorization độc lập. **Một MAC đúng chỉ là một mắt xích trong quyết định cho phép HTTP request.**

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): định nghĩa HMAC.
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512](https://www.rfc-editor.org/rfc/rfc4231): test vector HMAC độc lập.
- [FIPS 180-4 — Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): họ SHA-2 và định nghĩa SHA-256.
- [Java SE 17 — javax.crypto.Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): getInstance, init, update, doFinal, reset và getMacLength.
- [Java SE 17 — MessageDigest API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): hash, digest và isEqual.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo chuẩn ký các thành phần HTTP. Hợp đồng `hmac-v1` trong bài chỉ là **ví dụ ứng dụng**, không mặc nhiên tuân thủ RFC 9421.

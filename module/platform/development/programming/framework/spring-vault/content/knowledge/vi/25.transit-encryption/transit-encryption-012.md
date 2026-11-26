# HMAC, băm và mục đích sử dụng khác nhau trong Vault Transit

Trong chương **Mã hóa Transit**, chúng ta đã tiếp cận HashiCorp Vault như một dịch vụ mật mã mà ứng dụng Java có thể gọi thông qua Spring Vault. Transit không chỉ mã hóa và giải mã: nó còn **tính hàm băm (hash)**, **tạo mã xác thực thông điệp HMAC** và **xác minh HMAC**. Ba thao tác này thường xuất hiện cạnh nhau nhưng giải quyết những bài toán bảo mật khác nhau.

Ví dụ, dịch vụ thanh toán nhận một thông điệp “đơn hàng 123 đã thanh toán 500.000 đồng”. Nếu chỉ cần tạo dấu vân tay để phát hiện thay đổi khi so sánh với một giá trị tin cậy, SHA-256 có thể phù hợp. Nếu cần xác nhận thông điệp do một thành phần được cấp quyền tạo mã xác thực gửi đến, nên dùng HMAC. Nếu cần che nội dung đơn hàng khỏi người đọc trái phép, phải **mã hóa**, bởi cả hash lẫn HMAC đều không che giấu dữ liệu gốc.

Sau bài này, bạn có thể:

- Phân biệt hash, HMAC, mã hóa và chữ ký số theo mục tiêu bảo mật.
- Gọi đúng API `transit/hash`, `transit/hmac` và `transit/verify`.
- Tạo HMAC bằng `VaultTemplate`/`VaultOperations` trong ứng dụng Spring; xác minh dữ liệu bằng Vault.
- Thiết kế dữ liệu đầu vào, phân quyền và kiểm thử để tránh các lỗi thường gặp như phát lại yêu cầu hoặc nhầm hash với xác thực.

## 1. Hash và HMAC hoạt động như thế nào?

### Hàm băm mật mã (cryptographic hash)

Hàm băm nhận một chuỗi byte có độ dài bất kỳ và tạo một giá trị có độ dài cố định. Ví dụ, SHA-256 tạo đầu ra 256 bit, tức 32 byte. Ký hiệu:

\[
h = \operatorname{SHA256}(m)
\]

Trong đó `m` là dữ liệu đầu vào, `h` là digest. Với cùng thuật toán và **cùng dãy byte**, kết quả luôn giống nhau. Chỉ một thay đổi nhỏ trong dữ liệu cũng thường làm digest thay đổi rất nhiều.

Hàm băm mật mã tốt hướng đến các thuộc tính khó đảo ngược đầu vào, khó tìm đầu vào khác trùng digest và khó tìm hai đầu vào bất kỳ trùng nhau. Tuy vậy, **không thể chứng minh danh tính người tạo dữ liệu chỉ từ hash**: bất kỳ ai biết dữ liệu đều có thể tính lại SHA-256, kể cả kẻ tấn công vừa sửa nội dung.

Ví dụ, SHA-256 của chuỗi UTF-8 `hello` là:

~~~text
2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
~~~

Nếu tải một tệp cùng checksum từ một nguồn **được xác thực độc lập**, có thể dùng hash để phát hiện tệp đã thay đổi trong quá trình truyền. Nếu kẻ tấn công thay được cả tệp lẫn checksum, cơ chế đó không bảo đảm tính xác thực.

### HMAC (Hash-based Message Authentication Code)

HMAC kết hợp một **khóa bí mật** với hàm băm mật mã. Với HMAC-SHA256, chỉ các thành phần có quyền sử dụng khóa tương ứng mới tạo được mã xác thực hợp lệ:

\[
t = \operatorname{HMAC}_{K,\mathrm{SHA256}}(m)
\]

Ở đây `K` là khóa bí mật, `m` là thông điệp và `t` là mã HMAC. Người xác minh có thể kiểm tra thông điệp và mã HMAC có khớp với khóa đó hay không.

HMAC cung cấp **tính toàn vẹn có xác thực**: nếu khóa được bảo vệ và phân quyền đúng, dữ liệu bị thay đổi sẽ không vượt qua bước xác minh. HMAC vẫn **không mã hóa** thông điệp; người nhận vẫn nhìn thấy dữ liệu nếu thông điệp được truyền ở dạng rõ. HMAC cũng không cung cấp tính không thể chối bỏ như chữ ký số bất đối xứng, vì nhiều bên có thể cùng dùng một khóa bí mật.

### Bảng quyết định nhanh

| Cơ chế | Cần khóa bí mật? | Kết quả | Mục đích phù hợp | Điều không bảo đảm |
| --- | --- | --- | --- | --- |
| SHA-256 / SHA-3 | Không | Digest cố định | Dấu vân tay tệp, đối chiếu dữ liệu với digest tin cậy, phát hiện trùng nội dung | Danh tính người gửi, chống sửa đổi khi cả digest cũng có thể bị thay |
| HMAC-SHA256 | Có | Mã xác thực có khóa | Xác thực webhook, lệnh giữa dịch vụ, giá trị lưu trữ cần kiểm tra toàn vẹn có xác thực | Bí mật nội dung, chống phát lại nếu không thêm timestamp/nonce |
| Mã hóa Transit | Có | Ciphertext có thể giải mã bởi bên được cấp quyền | Giữ bí mật thông tin trước nơi lưu trữ hoặc truyền dẫn không tin cậy | Tự động xác thực danh tính người gửi hay ngăn replay ở tầng nghiệp vụ |
| Chữ ký số | Có cặp khóa riêng/công khai | Chữ ký có thể kiểm tra bằng khóa công khai | Xác thực bên ký với nhiều bên kiểm tra độc lập | Bí mật nội dung |

**Quy tắc chọn:** Cần bảo mật nội dung thì mã hóa; cần dấu vân tay không dựa vào khóa thì hash; cần chứng minh dữ liệu được xử lý bởi bên có quyền dùng khóa chung thì HMAC; cần người kiểm tra độc lập với khóa công khai thì cân nhắc chữ ký số.

## 2. Vault Transit thực hiện hash và HMAC

Giả sử Transit được mount ở đường dẫn `transit/`. Các endpoint chính:

| API Vault | Đầu vào nổi bật | Đầu ra nổi bật | Có cần Transit key theo tên? |
| --- | --- | --- | --- |
| `POST /v1/transit/hash/sha2-256` | `input` là Base64 của dữ liệu; có thể đặt `format=hex` | `data.sum` | Không |
| `POST /v1/transit/hmac/orders-mac/sha2-256` | `input` là Base64 của dữ liệu | `data.hmac`, ví dụ dạng `vault:v1:...` | Có |
| `POST /v1/transit/verify/orders-mac/sha2-256` | `input` và mã `hmac` đã nhận | `data.valid` là `true` hoặc `false` | Có |

**Base64 chỉ là cách biểu diễn byte khi gửi JSON**, không phải mã hóa bảo mật. Chẳng hạn, chuỗi UTF-8 `hello` có Base64 là `aGVsbG8=`. Phải dùng cùng byte đầu vào khi tạo và xác minh HMAC: khoảng trắng, ký tự xuống dòng, cách viết hoa và mã hóa ký tự đều ảnh hưởng kết quả.

Transit hash hỗ trợ nhóm SHA-2 và SHA-3; khi không chỉ định, thuật toán mặc định thường là `sha2-256`. Định dạng đầu ra hash mặc định là `hex`, có thể chọn `base64`. HMAC cũng mặc định sử dụng `sha2-256`; mã HMAC trả về chứa thông tin **phiên bản khóa**, do đó nên lưu nguyên chuỗi mà Vault cung cấp.

Transit có kiểu khóa `hmac` dành riêng cho HMAC. Các kiểu Transit key khác cũng có thể dùng HMAC vì Vault quản lý vật liệu khóa HMAC riêng cho từng phiên bản Transit key. Khóa bí mật dùng cho HMAC được giữ ở phía Vault; ứng dụng Java gửi dữ liệu đến Vault và nhận mã xác thực, không cần tải khóa thô về.

### Thử nhanh với Vault CLI

Các lệnh tạo mount và khóa bên dưới dành cho **người quản trị/môi trường thử nghiệm**; ứng dụng production chỉ cần quyền sử dụng những endpoint được cấp.

~~~bash
# Chỉ chạy một lần nếu mount transit chưa tồn tại.
vault secrets enable transit

# Khởi tạo khóa HMAC; không cần cấp quyền tạo khóa cho ứng dụng.
vault write transit/keys/orders-mac type=hmac

# "hello" (không kèm ký tự xuống dòng) -> aGVsbG8=
vault write transit/hash/sha2-256 input=aGVsbG8= format=hex

# Nhận data.hmac, ví dụ vault:v1:<chuỗi do Vault tạo>
vault write transit/hmac/orders-mac/sha2-256 input=aGVsbG8=

# Thay <HMAC_VUA_NHAN> bằng toàn bộ chuỗi data.hmac thực tế.
vault write transit/verify/orders-mac/sha2-256 \
  input=aGVsbG8= \
  hmac='<HMAC_VUA_NHAN>'
~~~

Lệnh hash ở trên phải cho `data.sum` bằng digest SHA-256 của `hello` đã nêu ở mục 1. Với HMAC đúng và dữ liệu đúng, `data.valid=true`; nếu giữ nguyên HMAC nhưng thay dữ liệu đầu vào, kết quả sẽ là `false`. Không lấy một giá trị HMAC mẫu bất kỳ để so sánh: kết quả phụ thuộc vào khóa thực đang được Vault quản lý.

## 3. Tích hợp Spring Vault trong Java

Trong Spring Vault, `VaultTemplate` triển khai `VaultOperations`. Ta có thể gọi API mức cao qua `opsForTransit().getHmac(...)` và dùng `write(...)` để truy cập các endpoint verify/hash. Cách này phù hợp với ứng dụng đã cấu hình Vault endpoint, TLS và xác thực workload (ví dụ Kubernetes auth hoặc AppRole) để có bean `VaultOperations` hoạt động.

Ví dụ sau dùng một khóa cố định `orders-mac`, dữ liệu đầu vào là **byte[]** để tránh phụ thuộc bảng mã mặc định của máy. Việc tạo khóa và cấp policy thực hiện trước bước triển khai ứng dụng.

~~~java
import java.util.Base64;
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.Plaintext;
import org.springframework.vault.support.VaultResponse;

@Service
public class TransitIntegrityService {

    private static final String KEY_NAME = "orders-mac";
    private final VaultOperations vault;

    public TransitIntegrityService(VaultOperations vault) {
        this.vault = vault;
    }

    // Sinh HMAC-SHA256 bằng API cấp cao của Spring Vault.
    public String createHmac(byte[] message) {
        Objects.requireNonNull(message, "message");
        return vault.opsForTransit()
                .getHmac(KEY_NAME, Plaintext.of(message))
                .getHmac();
    }

    // Gửi HMAC cho Vault xác minh; không tự tái tạo/so sánh chuỗi.
    public boolean verifyHmac(byte[] message, String hmac) {
        Objects.requireNonNull(message, "message");
        Objects.requireNonNull(hmac, "hmac");

        VaultResponse response = vault.write(
                "transit/verify/" + KEY_NAME + "/sha2-256",
                Map.of("input", base64(message), "hmac", hmac));

        Object valid = data(response).get("valid");
        if (!(valid instanceof Boolean)) {
            throw new IllegalStateException("Vault thiếu data.valid");
        }
        return Boolean.TRUE.equals(valid);
    }

    // Hash SHA-256 không dùng khóa, trả về chuỗi hex.
    public String sha256Hex(byte[] message) {
        Objects.requireNonNull(message, "message");

        VaultResponse response = vault.write(
                "transit/hash/sha2-256",
                Map.of("input", base64(message), "format", "hex"));

        Object sum = data(response).get("sum");
        if (!(sum instanceof String)) {
            throw new IllegalStateException("Vault thiếu data.sum");
        }
        return (String) sum;
    }

    private static String base64(byte[] bytes) {
        return Base64.getEncoder().encodeToString(bytes);
    }

    private static Map<String, Object> data(VaultResponse response) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Vault không trả về data");
        }
        return response.getData();
    }
}
~~~

Cách gọi từ service khác:

~~~java
import java.nio.charset.StandardCharsets;

byte[] payload = "order=123|amount=500000"
        .getBytes(StandardCharsets.UTF_8);

String mac = transitIntegrityService.createHmac(payload);
boolean accepted = transitIntegrityService.verifyHmac(payload, mac);
String digest = transitIntegrityService.sha256Hex(payload);
~~~

Ở đây `accepted` phải là `true` nếu Vault còn giữ phiên bản khóa tạo ra `mac` và policy cho phép xác minh. Khi thay một byte trong `payload`, xác minh phải trả về `false`. Ngược lại, lỗi mạng, token hết hạn hoặc thiếu quyền gọi Vault **không phải** là “chữ ký không hợp lệ”: Spring Vault có thể ném ngoại lệ và ứng dụng cần xử lý đường lỗi riêng.

Nếu Transit được mount ở tên khác, chẳng hạn `crypto/`, có thể dùng `vault.opsForTransit("crypto")` cho HMAC và đổi đường dẫn `write(...)` tương ứng. Với thuật toán HMAC khác SHA-256, phải bảo đảm endpoint verify sử dụng cùng thuật toán đã dùng lúc tạo.

### Có cần gọi Vault để tính SHA-256 không?

Không bắt buộc. SHA-256 là phép toán công khai, Java có sẵn `MessageDigest`:

~~~java
import java.security.MessageDigest;

byte[] digest = MessageDigest.getInstance("SHA-256").digest(payload);
~~~

Chọn `transit/hash` khi muốn chuẩn hóa luồng thao tác qua Vault hoặc có yêu cầu vận hành cụ thể; chọn `MessageDigest` cục bộ nếu chỉ cần digest chuẩn, không cần chuyến gọi mạng. **HMAC với khóa do Vault quản lý có giá trị bảo mật khác**, vì ứng dụng không phải giữ khóa HMAC trong cấu hình hay bộ nhớ của chính mình.

## 4. Ví dụ nghiệp vụ: xác thực thông điệp thanh toán

Giả sử service A gửi kết quả thanh toán cho service B. Một thiết kế tối thiểu:

1. A xây dựng thông điệp theo quy tắc byte thống nhất, gồm phiên bản định dạng, mã đơn hàng, số tiền, timestamp và nonce.
2. A nhờ Transit tạo HMAC từ chính chuỗi byte đó, rồi gửi thông điệp và HMAC đến B qua HTTPS.
3. B kiểm tra timestamp còn trong khoảng chấp nhận, nonce chưa được sử dụng và định dạng hợp lệ.
4. B gọi `transit/verify` với **chính các byte thông điệp đã nhận** và HMAC; chỉ xử lý giao dịch nếu `valid=true`.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant V as Vault Transit
    participant B as Service B
    A->>V: HMAC(canonicalPayload)
    V-->>A: vault:vN:...
    A->>B: payload + HMAC qua HTTPS
    B->>B: Kiểm tra timestamp, nonce, định dạng
    B->>V: Verify(payload, HMAC)
    V-->>B: valid=true/false
    B->>B: Chấp nhận hoặc từ chối
~~~

Ví dụ chuỗi thông điệp được quy ước rõ ràng:

~~~text
v1
orderId=123
amountMinor=50000000
currency=VND
timestamp=2026-11-25T12:30:00Z
nonce=70fe15e7-9d4b-49cf-8500-9e6f30ae00c1
~~~

Ở ví dụ này, trường `amountMinor` dùng đơn vị nhỏ nhất đã thống nhất trước, tránh cách biểu diễn số thực và dấu phân cách khác nhau. Ngày giờ dùng UTC dạng ISO-8601, khóa trường cố định thứ tự, dấu xuống dòng là LF và nội dung được mã hóa UTF-8. Nếu gửi JSON, cần một quy tắc canonicalization rõ ràng; cùng một đối tượng JSON có thể được biểu diễn bằng các byte khác nhau do thứ tự thuộc tính hoặc khoảng trắng.

**HMAC tự nó không chống phát lại (replay).** Kẻ tấn công có thể gửi lại một thông điệp và HMAC vẫn hợp lệ. Timestamp chỉ giới hạn khoảng thời gian tấn công; nonce duy nhất kèm nơi lưu trạng thái chống trùng mới giúp chặn yêu cầu lặp lại. Service B cũng phải kiểm tra quyền nghiệp vụ, trạng thái đơn hàng và bảo đảm thao tác xử lý idempotent.

## 5. Quyền truy cập Vault theo nguyên tắc tối thiểu

Đội vận hành tạo mount/khóa và cấp các policy khác nhau cho từng workload. Ví dụ policy HCL cho service **tạo** HMAC:

~~~hcl
path "transit/hmac/orders-mac/sha2-256" {
  capabilities = ["update"]
}
~~~

Policy cho service **xác minh** HMAC:

~~~hcl
path "transit/verify/orders-mac/sha2-256" {
  capabilities = ["update"]
}
~~~

Nếu một workload thực sự cần tính hash qua Vault, cấp thêm:

~~~hcl
path "transit/hash/sha2-256" {
  capabilities = ["update"]
}
~~~

Các API trên dùng HTTP `POST` và trong ACL của Vault thường cần capability `update`. Không cấp `transit/keys/*`, quyền xuất khóa, tạo khóa, xóa khóa hay xoay khóa cho service chỉ cần tạo/xác minh HMAC. Nếu một service dùng toàn bộ ba thao tác trong `TransitIntegrityService` thì token của chính service đó phải có đủ ba quyền; trong kiến trúc nhiều service, nên cấp policy riêng theo nhiệm vụ từng service.

Spring Vault sử dụng token từ cơ chế xác thực workload và session manager được cấu hình. Không đặt token Vault trực tiếp vào mã nguồn, log hoặc request của người dùng. Đường truyền đến Vault cần TLS và danh tính Vault server phải được xác minh.

### Vòng đời và phiên bản khóa HMAC

- HMAC Vault thường có dạng `vault:v<key-version>:<digest>`. Giữ nguyên **toàn bộ chuỗi**, kể cả tiền tố phiên bản, khi lưu cùng bản ghi hoặc truyền đến bên xác minh.
- Khi rotate Transit key, Vault sử dụng phiên bản mới cho yêu cầu HMAC mới. Việc xác minh dữ liệu cũ phụ thuộc vào phiên bản khóa tương ứng còn được giữ và chính sách phiên bản cho phép sử dụng.
- Không tự cắt tiền tố `vault:vN:`, không âm thầm tạo lại HMAC cũ bằng khóa hiện hành rồi so sánh, và không thu hồi phiên bản cũ trước khi dữ liệu cần xác minh hết thời gian lưu trữ.
- Cần quy trình quản trị riêng cho tạo/rotate/thu hồi khóa, giới hạn người và ứng dụng có quyền tạo HMAC, đồng thời giám sát lỗi xác thực, phân quyền và truy cập bất thường.

HMAC có tính xác định đối với cùng dữ liệu, thuật toán và phiên bản khóa. Vì vậy, lạm dụng HMAC làm chỉ mục cho dữ liệu có tập giá trị nhỏ có thể làm lộ quan hệ bằng nhau; người có quyền gọi endpoint HMAC còn có thể thử từng ứng viên để suy ra dữ liệu. Phải cân nhắc phân quyền, hạn mức và nhu cầu bảo vệ dữ liệu đầu vào.

## 6. Các lỗi thiết kế cần tránh

| Nhầm lẫn | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng SHA-256 không khóa làm “chữ ký” cho webhook | Kẻ sửa dữ liệu tự tính lại digest hợp lệ | Dùng HMAC hoặc chữ ký số; quản lý khóa và danh tính bên gửi |
| Dùng hash/HMAC để “mã hóa” số tài khoản | Dữ liệu gốc không có cơ chế giải mã; hash thường bị dò với dữ liệu dễ đoán | Dùng Transit encrypt/decrypt nếu cần giữ bí mật và khôi phục dữ liệu |
| Dùng SHA-256 nhanh để lưu mật khẩu | Dễ bị thử đoán hàng loạt khi cơ sở dữ liệu lộ | Dùng thuật toán băm mật khẩu chuyên dụng như Argon2id, scrypt hoặc bcrypt với tham số phù hợp |
| Xác minh HMAC bằng cách so chuỗi kết quả mới với chuỗi cũ | Sai khi rotate khóa; dễ mắc lỗi xử lý định dạng và so sánh nhạy cảm thời gian | Dùng `transit/verify` với nguyên HMAC đã nhận |
| HMAC trên JSON chưa chuẩn hóa | Các biểu diễn cùng ý nghĩa tạo mã khác nhau | Chuẩn hóa byte đầu vào, bảng mã, thứ tự trường và cách biểu diễn số/ngày |
| Chỉ dựa vào HMAC để chặn replay | Yêu cầu cũ hợp lệ vẫn có thể được gửi lại | Dùng timestamp, nonce, bộ nhớ chống trùng, kiểm tra trạng thái và idempotency |
| Coi lỗi 403/timeout của Vault là `valid=false` | Che giấu lỗi phân quyền/hạ tầng và làm sai luồng xử lý | Phân biệt lỗi xác minh và lỗi hệ thống; fail closed, theo dõi metrics |

Khi nhận HTTP 400 từ Vault, kiểm tra Base64, tham số `hmac`, tên thuật toán và định dạng request. Với 403, kiểm tra policy và trạng thái token/workload auth; với 404, kiểm tra mount, key và đường dẫn. Lỗi timeout, 429 hoặc 5xx cần giám sát và áp dụng retry hữu hạn khi phù hợp, tránh làm nghẽn Vault. Không ghi nguyên payload nhạy cảm, token hoặc HMAC vào log ứng dụng.

## 7. Gợi ý kiểm thử tích hợp

Một bài thực hành có thể sử dụng Vault Dev hoặc một Vault test instance có mount Transit và khóa `orders-mac` được tạo trước. Không cần đưa khóa bí mật ra khỏi Vault.

1. **Hash ổn định:** cùng byte `hello` gọi `transit/hash/sha2-256` hai lần phải nhận cùng digest; đối chiếu với SHA-256 do Java `MessageDigest` tính.
2. **HMAC thành công:** gọi `createHmac(payload)`, sau đó `verifyHmac(payload, hmac)` phải cho `true`.
3. **Dữ liệu thay đổi:** sửa một byte của `payload` và xác minh với HMAC cũ phải cho `false`.
4. **HMAC bị sửa:** thay một ký tự trong mã HMAC hợp lệ; yêu cầu phải bị từ chối bằng `valid=false` hoặc báo request không hợp lệ tùy dạng dữ liệu sửa.
5. **Thiếu quyền:** dùng token chỉ có quyền `transit/hash/sha2-256` để gọi `transit/hmac/orders-mac/sha2-256`; phải nhận lỗi phân quyền, không xử lý như xác minh thất bại bình thường.
6. **Xoay khóa:** tạo HMAC trước và sau rotation; xác nhận phiên bản đầu ra thay đổi, rồi kiểm tra khả năng xác minh mã cũ theo chính sách lưu giữ phiên bản đã cấu hình.
7. **Tình huống nghiệp vụ:** gửi lại một request có HMAC đúng nhưng nonce đã dùng; tầng nghiệp vụ phải chặn, dù Vault có thể trả `valid=true`.

Trong CI, nên khởi tạo mount và key qua bước setup có quyền quản trị riêng; workload của ứng dụng dùng token/policy hạn chế. Test cần bao phủ cả khả năng Vault không truy cập được và đường khôi phục của ứng dụng khi token hết hạn, bên cạnh các trường hợp HMAC hợp lệ/không hợp lệ.

## 8. Ghi nhớ

Hash tạo dấu vân tay dữ liệu **không có khóa**; HMAC tạo dấu xác thực **có khóa bí mật**; mã hóa bảo vệ **tính bí mật** của dữ liệu. Vault Transit giúp ứng dụng Spring Vault sử dụng HMAC mà không mang khóa ra khỏi Vault, hỗ trợ key version và kiểm soát quyền theo API. Tính bảo mật thực tế vẫn phụ thuộc vào byte đầu vào nhất quán, phân quyền workload, quản lý khóa và kiểm soát replay ở tầng nghiệp vụ.

### Câu hỏi tự kiểm tra

1. Vì sao `SHA256(message)` không đủ để xác thực một webhook đến từ đối tác?
2. Khi B nhận thông điệp, HMAC và timestamp hợp lệ nhưng nonce đã được xử lý, B phải làm gì? Vì sao?
3. Khi Transit key rotate, việc chỉ lưu phần digest mà bỏ tiền tố phiên bản có thể gây khó khăn gì?
4. Có nên sử dụng endpoint `transit/hash` để băm mọi chuỗi mật khẩu người dùng? Giải thích.
5. Trong Java, điều gì khác biệt giữa kết quả `data.valid=false` và exception do Vault trả về 403 hoặc timeout?

### Tài liệu tham khảo

- [HashiCorp Vault — Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — Transit HTTP API: Hash, HMAC, Verify](https://developer.hashicorp.com/vault/api-docs/secret/transit)
- [Spring Vault — Vault secrets engines, Transit](https://docs.spring.io/spring-vault/reference/4.0/vault/vault-secret-engines.html)
- [Spring Vault — VaultTransitOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTransitOperations.html)

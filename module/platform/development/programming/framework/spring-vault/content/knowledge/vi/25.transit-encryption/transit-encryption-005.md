# Mã hóa và giải mã một giá trị với Spring Vault Transit

## 1. Mục tiêu và bối cảnh

**Transit Secrets Engine** của HashiCorp Vault cung cấp dịch vụ mật mã qua API: ứng dụng gửi dữ liệu cần mã hóa đến Vault, nhận lại bản mã và có thể yêu cầu Vault giải mã khi được cấp quyền. Khóa mã hóa được quản lý bên trong Vault, giúp ứng dụng Java sử dụng khóa mà không cần đọc, lưu trữ hoặc tự luân chuyển khóa thô.

Trong Spring Vault, nhóm API **VaultTransitOperations**, lấy từ **VaultOperations.opsForTransit()** hoặc **VaultTemplate.opsForTransit()**, giúp thao tác với Transit mà không phải tự ghép HTTP request hay tự mã hóa Base64 cho lời gọi mã hóa chuỗi thông thường.

Sau bài này, bạn có thể:

- Chuẩn bị một khóa Transit và chính sách chỉ cho phép mã hóa/giải mã bằng khóa đó.
- Dùng Spring Vault để mã hóa một chuỗi và nhận ciphertext có định dạng do Vault quản lý.
- Giải mã ciphertext trở về chuỗi gốc, phân biệt dữ liệu ứng dụng phải lưu với dữ liệu Vault quản lý.
- Xử lý tình huống sai khóa, thiếu quyền, token hết hạn, Vault không sẵn sàng và kiểm chứng vòng mã hóa–giải mã.

Ví dụ xuyên suốt dùng khóa Transit tên **customer-data** và dữ liệu minh họa **"Mã đơn hàng: DH-2026-001"**. Giá trị này chỉ nhằm minh họa một chuỗi Unicode; không sử dụng dữ liệu bí mật thật trong bản ghi log, commit hoặc bài kiểm thử.

## 2. Điều gì diễn ra khi mã hóa và giải mã?

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant Vault as Vault Transit
    participant Store as Cơ sở dữ liệu
    App->>Vault: encrypt(customer-data, plaintext)
    Note over App,Vault: Gửi qua TLS; token phải có quyền encrypt
    Vault-->>App: ciphertext = vault:v1:...
    App->>Store: Lưu ciphertext
    App->>Store: Đọc ciphertext khi cần
    Store-->>App: vault:v1:...
    App->>Vault: decrypt(customer-data, ciphertext)
    Note over App,Vault: Token phải có quyền decrypt
    Vault-->>App: plaintext ban đầu
~~~

Ở chế độ sử dụng Transit thông thường:

1. Ứng dụng sở hữu plaintext trước khi mã hóa. Vault nhận plaintext qua kết nối được bảo vệ bằng TLS và dùng phiên bản khóa Transit thích hợp để mã hóa.
2. Vault trả về một chuỗi ciphertext, chẳng hạn **vault:v1:...**. Tiền tố thể hiện định dạng ciphertext của Vault và phiên bản khóa, không phải bản thân khóa mật mã.
3. Ứng dụng **tự lưu ciphertext** vào cơ sở dữ liệu hoặc hệ thống lưu trữ. Transit không tự lưu từng bản ghi plaintext/ciphertext hộ ứng dụng.
4. Khi cần đọc dữ liệu, ứng dụng gửi ciphertext và tên khóa đến Vault để giải mã. Vault sử dụng vật liệu khóa phù hợp rồi trả lại plaintext nếu chính sách, phiên bản khóa và dữ liệu hợp lệ.

**Phân biệt mã hóa với Base64:** API HTTP của Transit yêu cầu trường **plaintext** được mã hóa Base64 trước khi gửi. Base64 chỉ là cách biểu diễn byte để truyền qua JSON; nó không bảo mật dữ liệu. Với API mã hóa/giải mã chuỗi của Spring Vault, thư viện đảm nhiệm thao tác chuyển đổi cần thiết; ứng dụng nên truyền chuỗi gốc và xử lý ciphertext được trả về.

**Phạm vi bảo vệ:** Transit giúp giữ khóa trong Vault, nhưng plaintext vẫn xuất hiện trong bộ nhớ ứng dụng trước khi mã hóa và sau khi giải mã, đồng thời đi qua đường truyền đến Vault. Vì vậy phải dùng TLS, bảo vệ dữ liệu trong bộ nhớ khi phù hợp và không ghi plaintext vào log. Transit cũng không thay thế kiểm soát truy cập vào dữ liệu, sao lưu, phân loại dữ liệu hoặc xác thực người dùng cuối.

## 3. Chuẩn bị khóa Transit và chính sách truy cập

Các lệnh dưới đây dành cho môi trường thử nghiệm đã có Vault CLI đăng nhập bằng danh tính **quản trị được phép cấu hình secrets engine**. Không dùng token root trong ứng dụng Java.

~~~bash
# Ví dụ: một quản trị viên bật Transit tại mount path "transit".
vault secrets enable -path=transit transit

# Tạo khóa với tên định danh mà ứng dụng sẽ dùng.
vault write -f transit/keys/customer-data

# Kiểm tra thông tin khóa (không phải vật liệu khóa bí mật).
vault read transit/keys/customer-data
~~~

Chỉ chạy lệnh **secrets enable** khi mount path chưa tồn tại; nếu Transit đã được bật, dùng mount hiện có. Khóa mặc định được Vault giữ và quản lý, thay vì xuất sang mã nguồn ứng dụng.

Chính sách HCL tối thiểu cho một service **vừa mã hóa vừa giải mã**:

~~~hcl
path "transit/encrypt/customer-data" {
  capabilities = ["update"]
}

path "transit/decrypt/customer-data" {
  capabilities = ["update"]
}
~~~

Quản trị viên lưu chính sách trên vào một file HCL thích hợp, chẳng hạn **transit-customer.hcl**, rồi nạp bằng:

~~~bash
vault policy write transit-customer transit-customer.hcl
~~~

Gắn chính sách này với phương thức xác thực workload đang dùng, chẳng hạn Kubernetes authentication hoặc AppRole, để Spring Vault nhận được token có quyền tương ứng. Tên **customer-data** trong Java phải khớp tên khóa đã tạo. Với kiến trúc tách biệt, service chỉ ghi dữ liệu có thể chỉ cần quyền **transit/encrypt/customer-data**; quyền giải mã nên cấp riêng cho service thực sự cần đọc dữ liệu.

Nếu Transit được mount ở một đường dẫn khác, cần điều chỉnh đường dẫn policy và cấu hình Transit operations tương ứng. Ví dụ bên dưới giả định mount path tiêu chuẩn **transit**.

## 4. Mã hóa và giải mã với VaultTemplate

Ứng dụng cần có dependency **org.springframework.vault:spring-vault-core**, một **VaultOperations/VaultTemplate** được cấu hình đúng Vault endpoint và cơ chế xác thực, cùng token có các quyền ở phần trước. Trong dự án Spring Boot dùng Spring Cloud Vault, có thể để cơ chế cấu hình và xác thực của dự án tạo bean **VaultOperations**; tránh tạo token cố định trong lớp nghiệp vụ.

Ví dụ lớp service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;

@Service
public class CustomerDataCryptoService {

    private static final String KEY_NAME = "customer-data";

    private final VaultTransitOperations transit;

    public CustomerDataCryptoService(VaultOperations vaultOperations) {
        this.transit = vaultOperations.opsForTransit();
    }

    public String encrypt(String plaintext) {
        if (plaintext == null || plaintext.isEmpty()) {
            throw new IllegalArgumentException("plaintext không được rỗng");
        }
        return transit.encrypt(KEY_NAME, plaintext);
    }

    public String decrypt(String ciphertext) {
        if (ciphertext == null || ciphertext.isEmpty()) {
            throw new IllegalArgumentException("ciphertext không được rỗng");
        }
        return transit.decrypt(KEY_NAME, ciphertext);
    }
}
~~~

Giải thích các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **VaultOperations** | Điểm truy cập các thao tác Vault đã cấu hình endpoint, authentication và kết nối. |
| **opsForTransit()** | Trả về API thao tác với Transit mount mặc định. |
| **encrypt(KEY_NAME, plaintext)** | Yêu cầu Vault mã hóa giá trị, trả về chuỗi ciphertext như **vault:v1:...**. |
| **decrypt(KEY_NAME, ciphertext)** | Yêu cầu Vault giải mã bằng khóa Transit tương ứng, trả lại plaintext. |
| **KEY_NAME** | Tên khóa trong Transit, không phải khóa thô và không phải mật khẩu. |

Sử dụng service trong logic ứng dụng:

~~~java
String original = "Mã đơn hàng: DH-2026-001";

// Khi ghi dữ liệu: lưu ciphertext vào database.
String encryptedForStorage = customerDataCryptoService.encrypt(original);
// Ví dụ dạng kết quả: vault:v1:...

// Khi có yêu cầu nghiệp vụ hợp lệ: lấy ciphertext ra và giải mã.
String restored = customerDataCryptoService.decrypt(encryptedForStorage);
// restored bằng đúng original.
~~~

Không tự lấy phần sau dấu hai chấm của ciphertext để giải mã, không thay đổi tiền tố phiên bản **vault:vN:**, và không lưu khóa mã hóa trong application.properties. Hãy lưu **toàn bộ ciphertext**, gồm tiền tố, dưới dạng chuỗi. Một chuỗi ciphertext đã mã hóa không tự động trở thành plaintext khi nạp từ database; phải gọi đúng Transit **decrypt** khi thật sự cần.

### Vì sao không tự Base64 dữ liệu trước khi gọi Spring Vault?

Xét ví dụ:

~~~java
String plaintext = "Xin chào Vault";

// Đúng: truyền chuỗi plaintext cho Spring Vault.
String ciphertext = transit.encrypt("customer-data", plaintext);
String restored = transit.decrypt("customer-data", ciphertext);
~~~

Với lời gọi chuỗi ở trên, Spring Vault xử lý phần mã hóa dữ liệu truyền đến Vault. Nếu tự Base64 chuỗi trước rồi truyền vào **encrypt**, bạn sẽ mã hóa chính văn bản Base64 đó; khi giải mã sẽ nhận về chuỗi Base64 thay vì giá trị **"Xin chào Vault"**. Đây là một lỗi tích hợp dễ gặp khi chuyển từ ví dụ REST/CLI sang Java API.

## 5. Thử nghiệm trực tiếp bằng Vault CLI để hiểu đầu vào HTTP

Spring Vault che bớt chi tiết truyền dữ liệu. Với Vault CLI, bạn có thể quan sát rõ ràng trường **plaintext** và **ciphertext**. Ví dụ sau dùng shell Bash và công cụ **jq**; các biến chỉ lưu giá trị minh họa trong phiên thử nghiệm:

~~~bash
PLAIN_B64=$(printf '%s' 'Mã đơn hàng: DH-2026-001' | base64 | tr -d '\r\n')

CIPHER=$(vault write -format=json \
  transit/encrypt/customer-data \
  plaintext="$PLAIN_B64" | jq -r '.data.ciphertext')

printf '%s\n' "$CIPHER"
# Dạng: vault:v1:...

RESTORED_B64=$(vault write -format=json \
  transit/decrypt/customer-data \
  ciphertext="$CIPHER" | jq -r '.data.plaintext')

printf '%s' "$RESTORED_B64" | base64 --decode
# Mã đơn hàng: DH-2026-001
~~~

Ở đây, CLI nhận plaintext dưới dạng Base64 và trả plaintext đã giải mã dưới dạng Base64. Chỉ **ciphertext** là dữ liệu đã được mã hóa bằng Transit. Cần tránh bật shell tracing hoặc lưu lịch sử lệnh chứa bí mật thật khi thử nghiệm với dữ liệu nhạy cảm.

Kết quả từ CLI và Java phải tương thích nếu sử dụng cùng Vault, cùng Transit mount, cùng tên khóa và loại ciphertext hợp lệ. Trong ứng dụng, không cần tự gọi CLI hoặc tạo tiến trình hệ điều hành để thực hiện mã hóa; hãy dùng **VaultTransitOperations**.

## 6. Xử lý lỗi và hành vi ở môi trường thực tế

Một lời gọi Transit có thể thất bại trước khi Vault mã hóa được dữ liệu, hoặc bị từ chối khi giải mã. Các trường hợp thường gặp:

| Tình huống | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Token thiếu quyền encrypt/decrypt | Vault trả lỗi phân quyền, thường là HTTP 403. | Xem policy gắn với workload và path **transit/encrypt/** hoặc **transit/decrypt/**, chỉ cấp capability cần thiết. |
| Sai tên khóa hoặc Transit mount path | Vault báo path/khóa không tồn tại hoặc request không hợp lệ. | Đối chiếu cấu hình mount, tên khóa và quyền; không tự tạo khóa từ mọi request nghiệp vụ. |
| Ciphertext bị cắt, sửa hoặc không đúng định dạng | Vault không thể giải mã hợp lệ. | Kiểm tra kiểu cột, dữ liệu lưu và quá trình serialize; không cố sửa chuỗi ciphertext bằng tay. |
| Dùng sai khóa hoặc phiên bản khóa đã bị chặn giải mã | Decrypt thất bại dù ciphertext có tiền tố trông đúng. | Kiểm tra key mapping và chính sách **min_decryption_version** khi có thay đổi vòng đời khóa. |
| Token hết hạn, lỗi kết nối, TLS hoặc Vault gián đoạn | Request tới Vault thất bại. | Dùng cơ chế xác thực và gia hạn phiên của Spring Vault phù hợp với workload; theo dõi health/latency và retry có giới hạn ở tầng gọi dịch vụ khi phù hợp. |

Không log plaintext, token, dữ liệu trả về của decrypt hoặc nguyên vẹn ciphertext trong thông báo lỗi. Ghi nhận **loại thao tác**, **tên key không nhạy cảm**, **thời gian**, **mã lỗi** và **correlation ID** để giám sát. Không trả nguyên thông điệp lỗi nội bộ của Vault ra API công khai nếu nó có thể lộ thông tin hệ thống.

Lưu ý về retry: cần phân biệt một lỗi tạm thời (mạng/Vault gián đoạn) với lỗi 403 hoặc request sai, vì retry lặp lại lỗi quyền sẽ không giúp gì. Khi encrypt được lặp lại sau timeout, có thể tạo ciphertext khác cho cùng plaintext; ứng dụng không được giả định việc gửi lại sẽ cho ra đúng chuỗi ciphertext trước đó.

## 7. Những quy tắc quan trọng về vòng đời ciphertext

**Mã hóa cùng giá trị nhiều lần:** với cấu hình mã hóa Transit thông thường, mỗi lần mã hóa có thể sinh ciphertext khác nhau do sử dụng nonce; không dùng phép so sánh trực tiếp hai ciphertext để xác định hai plaintext bằng nhau. Cấu hình convergent encryption là trường hợp chuyên biệt, không mặc định áp dụng cho ví dụ này.

**Phiên bản khóa:** tiền tố **vault:v1:** chỉ ra phiên bản khóa đã dùng trong ciphertext. Khi quản trị viên rotate khóa, lần encrypt mới có thể nhận phiên bản mới, trong khi ciphertext cũ vẫn có thể giải mã bằng phiên bản khóa còn được phép. Vì vậy không xóa tiền tố hoặc áp đặt ciphertext chỉ được chứa **v1**.

**Quyền giải mã:** nếu nhiều dịch vụ cùng sử dụng dữ liệu, dịch vụ chỉ ghi dữ liệu nên được tách quyền encrypt khỏi quyền decrypt. Một token được phép encrypt không đương nhiên được phép decrypt.

**Vị trí giải mã:** chỉ giải mã khi cần thực sự sử dụng plaintext, trong phạm vi xử lý được xác thực và phân quyền. Không đưa plaintext vào cache dùng chung, trace, exception message hoặc log để thuận tiện cho việc debug.

**Chi phí vận hành:** mỗi lần encrypt/decrypt thường cần một request đến Vault; việc mã hóa hàng nghìn trường dữ liệu có thể ảnh hưởng đến độ trễ và thông lượng. Với tập dữ liệu lớn hoặc yêu cầu mã hóa phía ứng dụng, nghiên cứu envelope encryption bằng Transit Data Keys; đó là bài toán khác với mã hóa một giá trị bằng Transit API.

## 8. Kiểm thử tích hợp vòng mã hóa–giải mã

Kiểm thử có ý nghĩa cần chạy với Vault thử nghiệm có bật Transit, đã tạo khóa **customer-data**, và workload test có đủ quyền encrypt/decrypt. Đây là kiểm thử tích hợp thực tế, không chỉ mock kết quả trả về của Vault.

Ví dụ JUnit 5 trong dự án Spring Boot đã cấu hình kết nối Vault cho profile test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CustomerDataCryptoServiceIT {

    @Autowired
    private CustomerDataCryptoService cryptoService;

    @Test
    void encryptThenDecryptRestoresUnicodeValue() {
        String original = "Mã đơn hàng: DH-2026-001 – tiếng Việt";

        String ciphertext = cryptoService.encrypt(original);
        String restored = cryptoService.decrypt(ciphertext);

        assertThat(ciphertext).startsWith("vault:v");
        assertThat(ciphertext).isNotEqualTo(original);
        assertThat(restored).isEqualTo(original);
    }
}
~~~

Để kiểm tra giới hạn quyền, chạy thêm một test với danh tính **chỉ có quyền encrypt**: encrypt phải hoạt động và decrypt phải bị Vault từ chối. Kiểm tra ciphertext bị sửa hoặc truyền sai tên khóa phải nhận lỗi có thể quan sát được mà không rò rỉ plaintext. Các test liên quan mất kết nối hoặc token hết hạn nên dùng Vault thử nghiệm/thiết lập tách biệt và giới hạn thời gian chờ.

Không nên viết assertion bắt buộc hai lần encrypt cùng plaintext phải tạo ciphertext **khác nhau** trong mọi cấu hình, vì cách xử lý nonce và tùy chọn khóa có thể thay đổi theo chính sách sử dụng Transit.

## 9. Checklist thực hành

1. Xác nhận Transit mount, khóa **customer-data** và policy của workload đã tồn tại; token runtime chỉ có quyền cần dùng.
2. Mã hóa chuỗi có ký tự tiếng Việt qua **opsForTransit().encrypt(...)** và lưu nguyên ciphertext **vault:vN:...**.
3. Đọc lại ciphertext và gọi **opsForTransit().decrypt(...)** với đúng key; so sánh kết quả byte/chuỗi với dữ liệu gốc.
4. Thử token không có quyền decrypt hoặc ciphertext không hợp lệ, kiểm tra ứng dụng báo lỗi an toàn.
5. Kiểm tra log/tracing không chứa plaintext, token hoặc ciphertext đầy đủ; xác nhận kết nối Vault dùng TLS phù hợp.

Khi hoàn thành, bạn đã thực hiện được thao tác cốt lõi của **Spring Vault Transit**: ứng dụng Java mã hóa và giải mã một giá trị qua **VaultTemplate/VaultOperations** với khóa do HashiCorp Vault quản lý, có phân quyền thao tác rõ ràng và cách kiểm thử tích hợp có thể lặp lại.

# TTL của wrapping token và thời hạn của dữ liệu bên trong

## 1. Vì sao phải phân biệt hai thời hạn?

Trong HashiCorp Vault, **response wrapping** tạo một **wrapping token dùng một lần** để chuyển giao phản hồi bí mật giữa hai thành phần mà không gửi trực tiếp nội dung bí mật qua kênh bàn giao. Phản hồi gốc được Vault lưu tạm trong **cubbyhole gắn với wrapping token**; bên nhận dùng token đó để gọi **unwrap** và nhận lại phản hồi.

Khi dùng **Spring Vault** qua **VaultTemplate/VaultOperations**, ứng dụng Java có thể thao tác với wrapping thông qua **VaultWrappingOperations**. Một lỗi thiết kế phổ biến là cho rằng **TTL 60 giây của wrapping token** cũng đồng thời là thời gian sống của **credential, Vault token hoặc dữ liệu** chứa trong phản hồi. Hai loại thời hạn này độc lập.

**Mục tiêu bài học:**

- Hiểu TTL wrapping token quyết định khoảng thời gian **còn quyền mở lớp bọc**.
- Phân biệt TTL này với **lease TTL** của dynamic secret, **token TTL** của token được bọc, thời hạn chứng thư PKI và thời hạn do ứng dụng tự đặt.
- Phân tích trường hợp token còn sống nhưng dữ liệu bên trong đã hết hạn, hoặc dữ liệu vẫn còn hạn nhưng token bọc không mở được.
- Dùng **opsForWrapping()**, **wrap**, **lookup**, **read/unwrap**, **rewrap** trong Java; đọc trạng thái bằng Vault CLI và xây dựng kiểm thử tích hợp.
- Thiết kế thời gian bàn giao, ghi nhận lỗi và cấp lại bí mật mà không lộ token hoặc plaintext.

Bối cảnh: dịch vụ **Bootstrap Sender** nhận thông tin ban đầu của một workload rồi bàn giao wrapping token cho **Bootstrap Receiver**. Receiver phải unwrap đủ nhanh, kiểm tra *thời hạn thực của dữ liệu* và chỉ dùng dữ liệu nếu vẫn hợp lệ.

## 2. Response wrapping hoạt động như thế nào?

~~~mermaid
sequenceDiagram
    participant Sender as Sender (Java)
    participant Vault as HashiCorp Vault
    participant Receiver as Receiver (Java)
    Sender->>Vault: Gọi API có X-Vault-Wrap-TTL: 60s
    Vault->>Vault: Tạo phản hồi gốc
    Vault->>Vault: Lưu phản hồi trong cubbyhole của wrapping token
    Vault-->>Sender: wrap_info {token, ttl, creation_time, creation_path}
    Sender-->>Receiver: Bàn giao wrapping token an toàn
    Receiver->>Vault: sys/wrapping/lookup (tùy chọn)
    Vault-->>Receiver: Metadata; không lộ payload
    Receiver->>Vault: sys/wrapping/unwrap
    Vault-->>Receiver: Phản hồi gốc (chỉ một lần)
    Note over Receiver,Vault: Wrapping token hết hiệu lực sau unwrap
    Receiver->>Receiver: Kiểm tra hạn thực của secret/lease/token
~~~

Các khái niệm chính:

1. **Wrapping token:** token ngẫu nhiên, ngắn hạn và chỉ dùng một lần để truy xuất *một phản hồi được bọc*. Đây là một dạng bearer token: ai giữ token hợp lệ có thể thực hiện unwrap trong phạm vi mà Vault cho phép.
2. **Cubbyhole:** vùng lưu trữ riêng theo token ở Vault; wrapping sử dụng cubbyhole nội bộ để giữ phản hồi cho đến khi token bị dùng hoặc hết hiệu lực. Người dùng nên truy cập qua **sys/wrapping/unwrap**, không đọc trực tiếp **cubbyhole/response**.
3. **wrap_info:** metadata của token bọc, gồm **token**, **ttl**, **creation_time**, **creation_path**; một số tình huống có thêm **wrapped_accessor** khi phản hồi gốc chứa token.
4. **Payload bên trong:** có thể là một object JSON thường, dữ liệu KV, dynamic database credentials, một token đăng nhập Vault hoặc chứng thư PKI. Mỗi loại có quy tắc thời hạn khác nhau.

Với API HTTP, bên gửi yêu cầu response wrapping bằng header:

~~~http
X-Vault-Wrap-TTL: 60s
~~~

Vault CLI cung cấp lựa chọn **-wrap-ttl=60s**. TTL thực được kiểm soát thêm bởi các ràng buộc cấu hình và policy (nếu có), nên cần đọc **wrap_info** để xác nhận. Việc bật response wrapping cho một request không tự tạo TTL mới cho nội dung của phản hồi gốc.

## 3. Hai đồng hồ độc lập

Đặt:

- **t0**: lúc Vault tạo wrapping token.
- **W**: TTL của wrapping token, ví dụ 60 giây.
- **t_secret**: lúc secret/token/chứng thư bên trong được cấp.
- **S**: thời hạn ban đầu của dữ liệu bên trong, nếu loại dữ liệu đó có TTL.
- **t_unwrap**: lúc receiver thực hiện unwrap.

Khi không có những thay đổi do thu hồi, gia hạn hoặc cấu hình đặc thù:

**Hạn unwrap** xấp xỉ **t0 + W**. Nếu quá thời điểm này, wrapping token không còn cho phép lấy payload; nếu đã unwrap trước đó, token cũng không dùng lại được.

**Hạn sử dụng của payload** được xác định theo chính đối tượng bên trong. Với một dynamic secret có lease được cấp ở **t_secret**, hạn ban đầu xấp xỉ **t_secret + S**. Với X.509, đó là **notAfter**; với token Vault, là TTL và vòng đời token; với KV static, bản thân KV không nhất thiết có TTL để tự hết hạn.

Vì vậy, **unwrap thành công không chứng minh payload còn dùng được**. Ngược lại, wrapping token hết hạn không cho phép suy ra rằng mọi credential đã được tạo bên trong đều tự động bị thu hồi đúng lúc đó. Vòng đời của credential còn phụ thuộc lease, nguồn cấp, token cha và thao tác revoke.

### Bảng phân biệt

| Thành phần | Quy tắc hết hạn | Có bị reset khi unwrap? | Cần kiểm tra ở đâu? |
| --- | --- | --- | --- |
| Wrapping token | TTL tạo khi wrap; hết hạn hoặc mất hiệu lực sau một lần unwrap/rewrap | **Không**; unwrap tiêu thụ token | **wrap_info**, **sys/wrapping/lookup** |
| Vault token được bọc | TTL token kể từ khi tạo/renew, chịu ràng buộc max TTL và revoke | **Không** | **auth/token/lookup**, metadata token sau unwrap |
| Dynamic secret (ví dụ DB credential) | Lease TTL, có thể renew/revoke tùy backend | **Không** | **lease_id**, **lease_duration**, lease lookup/renew và hệ thống đích |
| PKI certificate | **notBefore/notAfter** trên chứng thư; cũng có thể bị revoke | **Không** | Kiểm tra X.509, CRL/OCSP nếu áp dụng |
| KV static secret | Không tự hết hạn chỉ vì được bọc | Không có TTL mặc định gắn với việc wrap | Quy tắc rotate/xóa/version/TTL nghiệp vụ của ứng dụng |
| TTL nghiệp vụ tự đặt | Ví dụ trường **expires_at** bên trong payload | **Không** | Kiểm tra chính trường thời điểm hết hạn của dữ liệu |

**Lưu ý:** **lease_duration** trong phản hồi dynamic secret mô tả thời hạn do Vault cấp ở thời điểm phát hành, không phải phép đo thời gian còn lại được Vault tự điều chỉnh mỗi khi chuyển giao bản JSON đã bọc. Nếu payload được unwrap muộn, đừng lấy toàn bộ **lease_duration** rồi tính lại từ **t_unwrap**.

## 4. Hai kịch bản đối lập với dòng thời gian

### Kịch bản A — Wrapping token hết hạn trước dữ liệu

Giả sử tại **14:00:00**, Vault phát hành credential có lease **15 phút**, đồng thời bọc phản hồi với wrapping TTL **60 giây**.

~~~text
14:00:00  Credential được cấp (hạn dự kiến 14:15:00)
          Wrapping token được tạo, TTL = 60s
14:00:40  Receiver unwrap thành công.
          Credential còn xấp xỉ 14 phút 20 giây
14:01:00  Hạn tối đa của wrapping token nếu chưa unwrap
14:01:10  Nếu đến giờ này mới unwrap: wrapping token đã hết hạn
14:15:00  Mốc hết hạn lease ban đầu (nếu không renew/revoke sớm)
~~~

Tại **14:01:10**, việc không unwrap được không đồng nghĩa credential đã bị xóa hoặc hết hạn tại nguồn. Cần xử lý như một lần bàn giao thất bại và đánh giá việc thu hồi/cấp lại theo quy trình của secrets engine, thay vì cố kéo dài token cũ.

### Kịch bản B — Dữ liệu hết hạn trước wrapping token

Giả sử tại **09:00:00**, Vault phát hành một credential chỉ có lease **30 giây**, nhưng phản hồi lại được bọc bởi wrapping token **5 phút**.

~~~text
09:00:00  Credential được cấp, TTL = 30s
          Wrapping token được tạo, TTL = 5m
09:00:30  Credential đến hạn hết hiệu lực nếu không được renew
09:01:00  Receiver có thể vẫn unwrap được
          nhưng credential bên trong có thể đã hết hạn
09:05:00  Wrapping token hết hạn nếu chưa được dùng
~~~

**Kết quả quan trọng:** **lookup/unwrap** xác nhận tình trạng *lớp bọc*, không xác nhận credential bên trong còn dùng được. Receiver phải kiểm tra thời hạn/lease hoặc trạng thái ở hệ thống đích trước khi sử dụng.

### Quy tắc thiết kế thời gian

Nếu thời gian truyền token và khởi động receiver thường là **D**, có độ trễ dự phòng **M**, hãy chọn **W** đủ cho **D + M** nhưng càng ngắn càng hợp lý theo rủi ro bàn giao. Đồng thời bảo đảm secret bên trong có thời gian sống còn lại đủ để hoàn tất công việc sau khi unwrap.

Ví dụ: receiver thường khởi động trong **10 giây**, thêm dự phòng **20 giây**, có thể cân nhắc wrapping TTL **45–60 giây**, trong khi lease của credential phải đáp ứng nhu cầu thực tế (ví dụ 10–15 phút). Giá trị cụ thể phụ thuộc latency, cấu hình Vault và yêu cầu bảo mật; không có một TTL tối ưu cho mọi workload.

## 5. Thực hành Vault CLI để quan sát wrapping TTL

Các lệnh dưới đây chỉ dùng **payload minh họa** và Vault test đã được cấu hình authentication cùng quyền thích hợp. Không dùng token root trong code Java và không đưa token thật vào lệnh ghi log hoặc pipeline được lưu lại.

### 5.1 Wrap một payload không có lease

Gọi helper endpoint **sys/wrapping/wrap** với TTL **45 giây**:

~~~bash
# Bash + jq; các giá trị "demo" không phải bí mật thật.
WRAPPED_JSON=$(vault write -format=json -wrap-ttl=45s \
  sys/wrapping/wrap \
  message_id="job-42" \
  expires_at="2026-11-25T15:00:00Z")

# Chỉ xem metadata công khai, không in token.
printf '%s' "$WRAPPED_JSON" | jq '{
  has_wrapping_token: (.wrap_info.token != null),
  wrapping_ttl: .wrap_info.ttl,
  creation_time: .wrap_info.creation_time,
  creation_path: .wrap_info.creation_path
}'

# Chỉ giữ token trong biến cục bộ của phiên test.
WRAP_TOKEN=$(printf '%s' "$WRAPPED_JSON" | jq -r '.wrap_info.token')
~~~

Kết quả biểu diễn:

~~~json
{
  "has_wrapping_token": true,
  "wrapping_ttl": 45,
  "creation_time": "<thời điểm tạo token>",
  "creation_path": "sys/wrapping/wrap"
}
~~~

**expires_at** ở payload ở đây là **quy tắc nghiệp vụ tự đặt**, chỉ để minh họa vòng đời bên trong. Vault không tự đọc trường này để hết hạn wrapping token hoặc xóa payload. **WRAP_TOKEN** là bí mật bearer có khả năng mở payload, vì thế phải hạn chế phạm vi truyền và tránh hiển thị.

### 5.2 Lookup không tiêu thụ token

~~~bash
# Trên môi trường test; tuyệt đối không đưa wrapping token vào log.
vault write -format=json sys/wrapping/lookup \
  token="$WRAP_TOKEN" \
  | jq '.data | {
      creation_time,
      creation_path,
      creation_ttl,
      ttl
    }'
~~~

Lookup cho phép kiểm tra token còn tồn tại và nguồn **creation_path** trước khi mở. Một giá trị metadata không có nghĩa payload còn hạn nghiệp vụ; cách diễn giải **ttl** và **creation_ttl** phụ thuộc dữ liệu lookup do phiên bản Vault trả về. Không sử dụng metadata client làm nguồn thay thế cho phép xác minh trực tiếp tại Vault.

### 5.3 Unwrap một lần

~~~bash
# Chỉ thực hiện với payload demo, trước khi wrapping token hết hạn.
vault unwrap -format=json "$WRAP_TOKEN" \
  | jq '.data | keys'
~~~

Lệnh chỉ in **tên trường** để tránh lộ giá trị. Sau lần unwrap thành công, cùng wrapping token không thể unwrap lần hai. Trong ứng dụng thực tế, đừng chạy lại unwrap đơn thuần vì một request timeout: request đầu tiên có thể đã tiêu thụ token, và điều đó cần được xác minh bằng audit/luồng xử lý lỗi.

### 5.4 Wrap một dynamic secret thực tế

Nếu Vault test đã cấu hình Database Secrets Engine và role **readonly**:

~~~bash
vault read -format=json -wrap-ttl=60s database/creds/readonly \
  | jq '{
      has_wrap_info: (.wrap_info != null),
      wrapping_ttl: .wrap_info.ttl,
      data_visible_before_unwrap: (.data != null)
    }'
~~~

Request này **phát hành một dynamic credential thật trong Vault test**. Sau unwrap, phản hồi gốc có thể chứa **lease_id**, **lease_duration**, **renewable** và trường username/password. Phải tính thời gian còn lại từ vòng đời lease, không từ TTL bọc hoặc thời điểm mở bọc.

## 6. Spring Vault: dùng VaultWrappingOperations

Với dependency **org.springframework.vault:spring-vault-core**, Spring Vault cung cấp:

~~~java
VaultWrappingOperations wrapping = vaultOperations.opsForWrapping();
~~~

Trong đó **VaultOperations** thường được hiện thực bởi **VaultTemplate** và cấu hình với Vault endpoint, TLS, session/authentication phù hợp. Các phương thức chính:

| API | Ý nghĩa |
| --- | --- |
| **wrap(Object body, Duration ttl)** | Tạo response wrapping cho dữ liệu do ứng dụng gửi vào helper endpoint; trả **WrappedMetadata**. |
| **lookup(VaultToken token)** | Kiểm tra metadata mà không mở payload; có thể trả **null** nếu token không còn hợp lệ. |
| **read(VaultToken token)** | Unwrap và đọc phản hồi dưới dạng **VaultResponse**; đây là thao tác **tiêu thụ token**. |
| **read(VaultToken token, Class<T> type)** | Unwrap và ánh xạ response có kiểu dữ liệu khi payload phù hợp. |
| **rewrap(VaultToken token)** | Tạo wrapping token mới chứa cùng response, hủy hiệu lực token cũ; **không gia hạn secret bên trong**. |

**Đừng dùng wrapping token như token đăng nhập ứng dụng lâu dài.** Wrapping token chỉ có nhiệm vụ bàn giao một phản hồi và nên được tiêu thụ ở nơi nhận.

### 6.1 Tạo wrapping token cho một payload minh họa

Ví dụ không chứa credential thật, để tập trung vào hai đồng hồ riêng biệt:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;
import org.springframework.vault.support.WrappedMetadata;

@Service
public class WrappedHandoffSender {

    private final VaultWrappingOperations wrapping;

    public WrappedHandoffSender(VaultOperations operations) {
        this.wrapping = operations.opsForWrapping();
    }

    public WrappedMetadata wrapJob(String jobId) {
        // Hạn nội dung: quy tắc NGHIỆP VỤ, không phải Vault lease.
        Instant payloadExpiresAt = Instant.now().plus(Duration.ofMinutes(10));

        Map<String, String> body = Map.of(
                "job_id", jobId,
                "expires_at", payloadExpiresAt.toString()
        );

        // Hạn mở bọc: chỉ 45 giây, độc lập với expires_at.
        return wrapping.wrap(body, Duration.ofSeconds(45));
    }
}
~~~

Ở bên gửi:

~~~java
WrappedMetadata metadata = sender.wrapJob("job-42");

// Metadata: metadata.getTtl(), metadata.getCreationTime(), metadata.getPath().
VaultToken wrappingToken = metadata.getToken();

// Bàn giao wrappingToken bằng kênh được bảo vệ, cho đúng receiver.
// Không log, không đưa token vào URL, không lưu token vào Git.
~~~

**WrappedMetadata.getTtl()** mô tả TTL wrapping token; không được dùng nó làm TTL của payload. Bên nhận không cần biết plaintext payload trước khi unwrap, chỉ cần một cơ chế vận chuyển token an toàn và chỉ cho một receiver được phép.

### 6.2 Bên nhận lookup, unwrap, rồi kiểm tra hạn bên trong

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import org.springframework.vault.support.WrappedMetadata;

@Service
public class WrappedHandoffReceiver {

    private final VaultWrappingOperations wrapping;

    public WrappedHandoffReceiver(VaultOperations operations) {
        this.wrapping = operations.opsForWrapping();
    }

    public Map<String, Object> receive(VaultToken token) {
        WrappedMetadata metadata = wrapping.lookup(token);

        if (metadata == null) {
            throw new IllegalStateException(
                    "Wrapping token không còn hợp lệ hoặc đã được dùng");
        }

        // Chỉ chấp nhận nguồn bọc mong đợi cho luồng demo.
        if (!"sys/wrapping/wrap".equals(metadata.getPath())) {
            throw new IllegalStateException(
                    "Wrapping token có nguồn không đúng");
        }

        // read() thực hiện unwrap và làm token không thể dùng lại.
        VaultResponse response = wrapping.read(token);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Không lấy được payload");
        }

        Map<String, Object> data = response.getData();
        Object value = data.get("expires_at");

        if (!(value instanceof String)) {
            throw new IllegalStateException("Thiếu expires_at hợp lệ");
        }

        Instant payloadExpiresAt;
        try {
            payloadExpiresAt = Instant.parse((String) value);
        } catch (DateTimeParseException ex) {
            throw new IllegalStateException("expires_at sai định dạng", ex);
        }

        if (!Instant.now().isBefore(payloadExpiresAt)) {
            throw new IllegalStateException("Payload đã hết hạn nghiệp vụ");
        }

        return Map.copyOf(data);
    }
}
~~~

Ví dụ dùng token ở receiver:

~~~java
// Giá trị nhận qua kênh bàn giao an toàn; không hardcode trong mã nguồn.
VaultToken token = VaultToken.of(wrappingTokenFromProtectedChannel);
Map<String, Object> payload = receiver.receive(token);
~~~

**Phân biệt rõ:** ví dụ Java này bọc **Map** với **expires_at** do ứng dụng quyết định. Nó **không tạo Vault lease** cho Map. Với một credential sinh từ Database Secrets Engine, receiver còn phải xử lý metadata lease do Vault phát hành và không được tự đặt lại thời hạn dựa trên lúc **receive()** chạy.

**Race condition:** token có thể bị unwrap hoặc hết hạn *giữa lúc lookup và read*. Lookup là bước kiểm tra nhanh nguồn, không khóa token và không bảo đảm lời gọi unwrap tiếp theo thành công; phải xử lý trường hợp **read** trả **null** hoặc ném ngoại lệ.

### 6.3 Rewrap không phải renew payload

~~~java
VaultWrappingOperations wrapping = vaultOperations.opsForWrapping();

WrappedMetadata refreshed = wrapping.rewrap(oldWrappingToken);
VaultToken newWrappingToken = refreshed.getToken();

// oldWrappingToken mất hiệu lực.
// newWrappingToken có TTL bọc mới, nhưng payload không được cấp lại.
~~~

Rewrap cho phép **xoay wrapping token** và cấp lại thời gian mở bọc theo cơ chế wrapping; token cũ mất hiệu lực ngay. **Rewrap không cấp một token đăng nhập mới, không renew lease DB và không kéo dài notAfter của chứng thư PKI.**

Nếu payload sắp hết hạn thật, giải pháp đúng thường là **renew lease/token khi được phép** hoặc **đề nghị secrets engine cấp một credential mới**, rồi thực hiện bàn giao mới. Không dùng rewrap nhiều lần để ngụy tạo việc credential vẫn còn hạn.

## 7. Các trường hợp dữ liệu bên trong cần xử lý riêng

### 7.1 Vault token được bọc

Ví dụ người điều phối tạo một token dành cho workload và yêu cầu wrapping TTL **60 giây**, còn token được tạo có TTL **10 phút**.

Sau khi unwrap thành công ở giây thứ 40, token bên trong không được cộng lại 10 phút; nó đã tiêu hao một phần TTL. Đọc thông tin token từ Vault để xác định còn sống, renewable hay không và có bị giới hạn bởi token cha. **Wrapped accessor** nếu có trong metadata hỗ trợ một số thao tác quản lý token mà không mở giá trị token, nhưng không thay thế kiểm tra trạng thái thực.

Spring Vault có các phương án xác thực như **CubbyholeAuthentication** cho bootstrap token qua response wrapping; lớp này phục vụ luồng xác thực và có vòng đời khác với bài toán wrap một **Map** bằng **VaultWrappingOperations**. Không tái sử dụng nhầm wrapping token làm session token chính của VaultTemplate.

### 7.2 Dynamic database credential

Dynamic secret có thể mang **lease_id**, **lease_duration** và **renewable**. Quyền dùng credential liên quan đến lease tại Vault và trạng thái của hệ thống DB, gồm cả khả năng bị revoke trước TTL.

Giả sử lease là 10 phút và receiver unwrap sau 2 phút: không tự coi credential còn trọn 10 phút. Kiểm tra lease, ghi nhận mốc phát hành và chỉ sử dụng nếu thời gian còn lại đạt ngưỡng an toàn. Nếu cho phép renew, điều phối renew/revoke theo đúng lease của secret, không phải wrapping token.

### 7.3 Chứng thư PKI

Chứng thư được cấp với X.509 **notBefore/notAfter**. Unwrap muộn không thay đổi các mốc này. Sau khi unwrap, Java cần kiểm tra chứng thư còn hiệu lực và có đủ thời gian dự phòng để cài đặt TLS; nếu không, yêu cầu cấp chứng thư mới theo quy trình PKI. Đừng suy ra **notAfter** từ wrapping TTL.

### 7.4 KV secret và dữ liệu tự định nghĩa

KV thông thường lưu dữ liệu tĩnh; một chuỗi **ttl=10m** đặt trong bản ghi KV chỉ là dữ liệu nếu ứng dụng không có cơ chế thực thi tương ứng. Response wrapping **không tự xóa phiên bản KV khi wrapping token hết hạn**. Với expiration nghiệp vụ, dùng trường **expires_at** và logic kiểm tra ở nơi sử dụng, hoặc giải pháp lưu trữ có cơ chế hết hạn riêng.

## 8. Cảnh báo an toàn và xử lý lỗi

| Tình huống | Điều có thể xảy ra | Hành động nên làm |
| --- | --- | --- |
| Sender yêu cầu wrapping nhưng không nhận **wrap_info** | Wrapping không được áp dụng như mong đợi. | Dừng bàn giao, kiểm tra cấu hình/header/policy, không gửi plaintext thay thế theo đường không được duyệt. |
| **lookup** trả null hoặc báo lỗi | Token đã hết hạn, đã dùng, bị revoke hoặc Vault không sẵn sàng. | Phân biệt lỗi kết nối với token không hợp lệ, đối chiếu audit; nếu nghi bị dùng trước, kích hoạt xử lý sự cố. |
| **unwrap** thành công nhưng payload hết hạn | Wrapping TTL đủ dài nhưng inner TTL quá ngắn hoặc có revoke. | Không sử dụng payload; thực hiện cấp lại/renew theo đúng loại secret. |
| Unwrap lần hai hoặc retry sau timeout | Token một lần đã bị tiêu thụ, có thể nhận lỗi token không hợp lệ. | Không retry mù; kiểm tra liệu kết quả lần đầu đã được nhận/ghi nhận, xử lý idempotency ở tầng nghiệp vụ. |
| **rewrap** thành công | Token mới thay token cũ, payload giữ nguyên. | Hủy đường dẫn phân phối token cũ, kiểm tra inner TTL vẫn còn đủ. |
| Nhầm wrapping token với auth token của workload | Token chỉ dùng một lần không thực hiện được các thao tác nghiệp vụ thông thường. | Unwrap để lấy đúng secret/token được bọc; dùng cơ chế đăng nhập Vault phù hợp. |
| Rò rỉ wrapping token | Bên thứ ba có thể unwrap trước receiver hợp lệ. | Không log token, không đặt trong URL/query string, bảo vệ kênh bàn giao và dựa vào audit để điều tra. |

**Chính sách quyền:** sender phải có quyền trên endpoint gốc mà nó gọi; ví dụ helper **sys/wrapping/wrap** yêu cầu capability phù hợp. API lookup/unwrap có thể dùng chính wrapping token theo quy tắc riêng của Vault; khi một service token khác gửi wrapping token dưới dạng tham số, chính sách của service token cũng phải cho phép thao tác cần thiết. Không cấp quyền hệ thống rộng cho workload chỉ để xử lý wrapping; tùy phương pháp đăng nhập và luồng Spring Vault mà xác minh quyền tối thiểu trên Vault test.

Đối với HTTP **sys/wrapping/unwrap**, **không gửi cùng một wrapping token đồng thời trong header X-Vault-Token và trường token của body**, vì có thể làm Vault tiêu thụ token không đúng cách. Dùng API Spring Vault chuẩn hoặc một trong hai hình thức HTTP được tài liệu Vault mô tả.

Chỉ log các thông tin phục vụ chẩn đoán như **operation**, trạng thái unwrap, request/correlation ID, thời gian từ wrap đến unwrap và lỗi phân loại. Không log **wrapping token**, auth token, credential, nội dung **VaultResponse** hoặc lỗi có dữ liệu bí mật. Ghi nhận metric tỷ lệ unwrap thành công/thất bại, thời gian bàn giao và số payload đã hết hạn ngay sau unwrap; điều chỉnh TTL theo dữ liệu quan sát.

## 9. Kiểm thử tích hợp: hai vòng đời thực sự

Chạy test với Vault test có cấu hình xác thực và quyền thao tác trên **sys/wrapping/wrap**, **lookup** và **unwrap**. Ví dụ JUnit 5 + AssertJ dưới đây dùng **payload demo không bí mật**, xác nhận wrapping có thể đọc đúng một lần:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import org.springframework.vault.support.WrappedMetadata;

@SpringBootTest
class WrappingTtlIT {

    @Autowired
    VaultOperations vaultOperations;

    @Test
    void tokenCanBeUnwrappedOnceAndPayloadRetainsItsOwnExpiry() {
        VaultWrappingOperations wrapping = vaultOperations.opsForWrapping();
        String payloadExpiresAt =
                Instant.now().plus(Duration.ofMinutes(10)).toString();

        WrappedMetadata created = wrapping.wrap(
                Map.of("id", "job-test", "expires_at", payloadExpiresAt),
                Duration.ofSeconds(45));

        VaultToken token = created.getToken();

        assertThat(created.getTtl()).isEqualTo(Duration.ofSeconds(45));
        assertThat(wrapping.lookup(token)).isNotNull();

        VaultResponse unwrapped = wrapping.read(token);
        assertThat(unwrapped).isNotNull();
        assertThat(unwrapped.getData())
                .containsEntry("id", "job-test")
                .containsEntry("expires_at", payloadExpiresAt);

        // Sau unwrap, token đã tiêu thụ; không thử mở lại payload.
        assertThat(wrapping.lookup(token)).isNull();
    }
}
~~~

**Giới hạn của test:** đây là test của helper wrapping với trường hạn nghiệp vụ; nó không kiểm thử lease thực của Database Secrets Engine. Kiểm thử tích hợp dynamic secret cần thêm role DB test, ghi nhận thời điểm cấp credential, unwrap sau một khoảng trễ có kiểm soát và xác minh lease/credential ở hệ thống đích. Tránh **Thread.sleep** dài hoặc tạo hàng loạt credential thật chỉ để chờ TTL hết hạn.

Có thể kiểm tra các kịch bản sau trong môi trường cách ly:

1. Wrapping TTL ngắn: chờ quá thời hạn rồi xác nhận **lookup/unwrap** không còn dùng được.
2. Payload chứa **expires_at** đã qua: unwrap vẫn có thể thành công nếu wrapping token còn sống, nhưng logic nghiệp vụ từ chối payload.
3. Unwrap đúng một lần rồi kiểm tra token đã mất hiệu lực; không log giá trị token khi assertion lỗi.
4. Rewrap token trước khi hết hạn, xác minh token cũ mất hiệu lực và dữ liệu bên trong giữ nguyên **expires_at**.
5. Dynamic credential có lease ngắn hơn wrapping TTL: unwrap vẫn có thể mở được phản hồi, sau đó xác minh credential đã mất hiệu lực hoặc không đạt ngưỡng thời gian sử dụng cần thiết.

## 10. Checklist chọn TTL và vận hành

- Đặt **wrapping TTL** dựa trên độ trễ bàn giao và thời gian bootstrap của receiver, giữ ngắn và có dự phòng hợp lý.
- Kiểm tra **TTL của nội dung** theo đúng loại dữ liệu: Vault token, lease của dynamic secret, **notAfter** của chứng thư PKI hoặc **expires_at** do ứng dụng quản lý.
- Chỉ unwrap khi receiver sẵn sàng dùng và xử lý payload; ưu tiên bảo vệ kết quả unwrap trong bộ nhớ, không log token hoặc nội dung bí mật.
- Dùng **lookup** để kiểm tra nguồn và hiệu lực token trước khi unwrap, nhưng vẫn xử lý lỗi do thay đổi trạng thái giữa hai lời gọi.
- Nếu wrapping token hết hạn, bị dùng trước hoặc payload đã hết hạn, phân loại nguyên nhân, quan sát audit và cấp lại đúng nguồn dữ liệu khi cần.
- Nhớ rằng **rewrap chỉ gia hạn cơ hội mở bọc bằng một token mới**, không gia hạn secret, credential, token đăng nhập hay chứng thư nằm bên trong.

Điểm cần ghi nhớ khi tích hợp **SPRING_VAULT**: **wrapping token TTL trả lời câu hỏi “còn mở được gói bàn giao không?”; thời hạn của dữ liệu bên trong trả lời câu hỏi “mở ra rồi còn được phép sử dụng không?”**. Ứng dụng Java phải kiểm tra cả hai theo đúng trách nhiệm để tránh sử dụng credential đã hết hạn hoặc tiếp tục lưu hành token bọc quá lâu.

### Tài liệu tham khảo

- [HashiCorp Vault — Response Wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping).
- [HashiCorp Vault — Lease, Renew, and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease).
- [HashiCorp Vault — Wrapping Unwrap API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-unwrap).
- [HashiCorp Vault — Wrapping Rewrap API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-rewrap).
- [Spring Vault — VaultWrappingOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultWrappingOperations.html).
- [Spring Vault — WrappedMetadata API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/WrappedMetadata.html).

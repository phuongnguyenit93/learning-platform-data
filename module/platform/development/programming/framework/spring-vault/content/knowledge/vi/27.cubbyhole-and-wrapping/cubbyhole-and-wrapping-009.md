# Xử lý token đã unwrap, hết hạn hoặc không đúng nguồn

## 1. Bối cảnh và mục tiêu

Trong kiến trúc microservice, một hệ thống triển khai thường phải chuyển thông tin nhạy cảm tới ứng dụng Java: AppRole SecretID, thông tin đăng nhập tạm thời, credential của dịch vụ hoặc nội dung một phản hồi Vault. Gửi thẳng các giá trị này qua CI log, email, biến môi trường được lưu lâu dài hay một hệ thống trung gian làm tăng khả năng rò rỉ.

**HashiCorp Vault response wrapping** giúp bên phát hành gửi **wrapping token có thời gian sống ngắn** thay cho nội dung nhạy cảm. Giá trị được bọc lưu trong vùng lưu trữ **Cubbyhole** gắn với token đó; bên nhận đổi token lấy giá trị thật bằng thao tác *unwrap*. Token wrapping thông thường là **dùng một lần**: sau khi unwrap thành công, token không thể được sử dụng lại để đọc nội dung đã bọc.

Điều này dẫn đến ba lỗi nghiệp vụ dễ gặp:

1. **Token đã được unwrap:** hệ thống nhận lại cùng token, có consumer khác xử lý trước hoặc token bị người khác dùng.
2. **Token đã hết hạn:** thời gian sống (TTL) của token kết thúc trước khi consumer kịp nhận hoặc xử lý.
3. **Token không đúng nguồn:** token hợp lệ nhưng trỏ tới phản hồi/endpoint không phải loại dữ liệu được mong đợi, hoặc không tương ứng với yêu cầu/đối tượng nhận đã xác minh.

Bài học thuộc chương **Cubbyhole và wrapping** của **Spring Vault (SPRING_VAULT)**, tập trung vào kiểm tra nguồn token, xử lý vòng đời và lỗi khi Java gọi HashiCorp Vault qua `VaultTemplate`/`VaultOperations`. Cơ chế xác thực workload, policy, logging, giám sát và kiểm thử tích hợp được trình bày trong phạm vi luồng nhận secret thực tế.

Sau bài này, bạn có thể phân biệt wrapping token với token đăng nhập Vault, sử dụng `sys/wrapping/lookup` và `sys/wrapping/unwrap`, xử lý các trạng thái thất bại theo hướng an toàn, đồng thời tránh lỗi “retry mù” trên một token dùng một lần.

## 2. Cubbyhole, response wrapping và ba loại thời hạn khác nhau

### 2.1. Cubbyhole giữ gì?

Cubbyhole là secrets engine có **vùng dữ liệu riêng cho từng Vault token**. Quyền truy cập vùng dữ liệu đó gắn với token tương ứng. Response wrapping tận dụng cơ chế này: Vault lưu nội dung phản hồi trong Cubbyhole của một wrapping token mới, còn bên phát hành nhận **thông tin về wrapper** để chuyển cho consumer.

Ví dụ một hệ thống phát hành AppRole SecretID từ Vault:

~~~text
Vault PKI/KV/AppRole endpoint
             |
             | Yêu cầu response wrapping với TTL ngắn
             v
Vault lưu phản hồi gốc trong cubbyhole của wrapping token
             |
             v
Producer nhận wrap_info.token và chuyển cho Consumer
             |
             v
Consumer kiểm tra provenance, rồi gọi unwrap
             |
             v
Vault tiêu thụ wrapping token, trả phản hồi gốc một lần
~~~

Thông thường metadata `wrap_info` có các trường như:

~~~json
{
  "wrap_info": {
    "token": "<WRAPPING_TOKEN>",
    "accessor": "<WRAPPING_ACCESSOR>",
    "ttl": 300,
    "creation_time": "2026-11-25T14:00:00Z",
    "creation_path": "auth/approle/role/orders-api/secret-id"
  }
}
~~~

Đây là ví dụ hình dạng phản hồi, không phải token đã phát hành thật. `token` là **bí mật có thể đổi lấy nội dung**, nên không được ghi trong log. `accessor` dùng để đối chiếu/quan sát theo chính sách vận hành, **không** thay thế token và không tự cho phép unwrap. `creation_path` mô tả endpoint nơi phản hồi được tạo; đây là metadata hữu ích để kiểm tra luồng, nhưng **không xác minh riêng danh tính con người hoặc hệ thống đã chuyển token**.

### 2.2. Phân biệt các loại token và TTL

| Giá trị | Dùng làm gì? | Hết hạn hoặc thu hồi ảnh hưởng gì? |
| --- | --- | --- |
| **Vault authentication token** | Workload đăng nhập và gọi Vault theo policy | Mất quyền gọi Vault khi token hết hạn/bị thu hồi; có thể cần đăng nhập lại |
| **Wrapping token** | Quyền nhận phản hồi đã bọc qua unwrap, thường chỉ dùng một lần | Không thể tiếp tục unwrap khi đã dùng hoặc hết hạn |
| **Secret bên trong wrapper** | Ví dụ AppRole SecretID hoặc credential được cấp | Có vòng đời, TTL, số lần sử dụng và cơ chế thu hồi riêng tùy loại secret |
| **Lease của dynamic secret** | Quản lý thời gian sử dụng/renew/revoke của secret động | Độc lập với việc wrapping token đã được dùng hay chưa |

**TTL của wrapper không phải TTL của secret được bọc.** Một SecretID có thể vẫn còn hiệu lực sau khi wrapping token hết hạn, hoặc ngược lại SecretID có thể hết hiệu lực dù wrapper vẫn chưa được unwrap. Hãy theo dõi riêng thời gian sống của credential, lease và token đăng nhập.

Khi gọi unwrap thành công, token wrapping được tiêu thụ; chương trình không thể “unwrap lại để kiểm tra”. Nếu cần tái phân phối dữ liệu, bên phát hành phải thực hiện **luồng cấp/đóng gói mới đã được cho phép**, không dựa vào việc khôi phục một token đã bị tiêu thụ.

## 3. Luồng xử lý an toàn trước và sau unwrap

~~~mermaid
flowchart TD
    A[Consumer nhận wrapping token] --> B{Yêu cầu có hợp lệ và được phép?}
    B -- Không --> X[Từ chối và ghi audit]
    B -- Có --> C[Kiểm tra correlation ID và metadata kỳ vọng]
    C --> D[Gọi sys/wrapping/lookup]
    D --> E{Lookup hợp lệ?}
    E -- Không --> F[Giữ trạng thái FAILED hoặc UNKNOWN và đối soát]
    E -- Có --> G{creation_path và accessor khớp kỳ vọng?}
    G -- Không --> X
    G -- Có --> H[Khóa xử lý một lần theo request ID]
    H --> I[Gọi sys/wrapping/unwrap một lần]
    I --> J{Nhận được phản hồi hợp lệ?}
    J -- Có --> K[Kiểm tra schema secret và dùng trong bộ nhớ]
    J -- Không/timeout --> L[UNKNOWN: không retry mù, đối soát]
    K --> M[Ghi nhận tiêu thụ thành công, bảo vệ secret]
~~~

Các bước **lookup** và **unwrap** không tạo thành một giao dịch nguyên tử. Giữa hai thao tác, token có thể hết hạn hoặc bị consumer khác sử dụng. Do đó lookup chỉ là kiểm tra sơ bộ; **phản hồi unwrap thành công và kiểm tra nội dung trả về** mới xác nhận ứng dụng đã nhận được dữ liệu.

### 3.1. Khi nào nên lookup trước?

Khi nhận một wrapping token từ kênh chuyển giao, consumer thường đã có kỳ vọng từ phía hệ thống phát hành: loại secret, nơi phát hành, request ID, TTL tối đa và có thể là wrapping accessor được gửi qua **kênh đáng tin riêng**.

`sys/wrapping/lookup` cho phép kiểm tra một số metadata của wrapping token **mà không tiêu thụ nội dung đã bọc**. Hãy so sánh ít nhất `creation_path` với endpoint được phép và đối chiếu `wrapping_accessor` nếu hệ thống có giá trị accessor đáng tin từ trước.

Metadata do chính token trả về không đủ làm bằng chứng rằng “token do đúng producer dự định gửi”: một bên biết token cũng có thể gọi lookup. Muốn bảo đảm nguồn phát, cần **ràng buộc kênh nhận**, danh tính workload, message/request ID và thông tin kỳ vọng được xác thực ở lớp nghiệp vụ.

## 4. Trường hợp 1: wrapping token đã được unwrap

### 4.1. Dấu hiệu và nguyên nhân

Sau lần unwrap thành công, Vault không cho dùng lại cùng wrapping token để lấy cùng phản hồi. Một lần lookup hoặc unwrap kế tiếp thường trả lỗi token wrapping **không tồn tại/không hợp lệ**. Tuy nhiên, **chỉ từ lỗi đó không thể kết luận chắc chắn token đã được unwrap**: token có thể hết hạn, bị revoke, sai chuỗi hoặc không thuộc Vault/mount tương ứng.

Các tình huống tạo ra hiện tượng này:

- Producer gửi trùng message đến hai consumer đang chạy song song.
- Consumer nhận lại event sau khi đã xử lý thành công do cơ chế **at-least-once delivery** của message broker.
- Consumer đã unwrap thành công, nhưng mất kết nối với database khi ghi trạng thái.
- Một actor khác có wrapping token đã unwrap trước consumer hợp lệ.
- Token bị revoke hoặc hết hạn khiến lỗi quan sát tương tự.

### 4.2. Quy tắc xử lý

**Không cố unwrap lại liên tục.** Đây là thao tác một lần; retry khi token đã tiêu thụ không thể khôi phục phản hồi. Trong nhiều trường hợp không thể phân biệt “bị kẻ khác lấy” với “consumer trước đã xử lý” chỉ qua mã lỗi.

Một state machine nghiệp vụ hữu ích:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| `RECEIVED` | Đã nhận wrapper, chưa bắt đầu unwrap | Xác thực yêu cầu, giữ token kín, lookup |
| `IN_PROGRESS` | Có một worker đang xử lý token | Chặn consumer khác xử lý trùng |
| `CONSUMED` | Đã nhận và xác minh phản hồi unwrap, lưu kết quả nghiệp vụ cần thiết | Xử lý message trùng bằng kết quả đã ghi, không gọi Vault lần nữa |
| `UNCERTAIN` | Timeout hoặc lỗi trước khi xác nhận kết quả unwrap | Điều tra, đối soát; không tự động retry vô hạn |
| `REJECTED` | Sai nguồn, sai schema hoặc vi phạm policy nghiệp vụ | Từ chối, cảnh báo và yêu cầu token mới qua luồng đáng tin |

Nếu hệ thống có bản ghi `CONSUMED` đáng tin cậy và cùng request ID đã được xử lý, yêu cầu lặp có thể trả **kết quả nghiệp vụ đã lưu** mà không cần lộ secret. Nếu **không có bằng chứng** đã tiêu thụ hợp lệ, phải đánh dấu nghi vấn, đối soát audit và có thể yêu cầu producer tạo wrapper/credential mới theo quy trình.

### 4.3. Tránh race giữa nhiều instance

Một tiến trình local `synchronized` không bảo vệ được nhiều Pod/instance. Nếu consumer có nhiều replica, nên dùng hàng đợi có phân vùng đúng, idempotency key, khóa phân tán/claim có TTL hoặc cập nhật trạng thái bằng compare-and-set trong database.

Ví dụ logic SQL ở mức ý tưởng:

~~~sql
-- Chỉ một worker có thể claim request đang ở RECEIVED.
UPDATE secret_deliveries
SET state = 'IN_PROGRESS'
WHERE request_id = :request_id
  AND state = 'RECEIVED';

-- Chỉ tiến hành unwrap khi số hàng được cập nhật = 1.
~~~

Nếu worker chết sau khi Vault đã tiêu thụ wrapper mà trước khi đánh dấu `CONSUMED`, bản ghi không tự trở thành thành công: chuyển sang `UNCERTAIN` và đối soát. Đây là ranh giới **at-most-once đối với wrapper**; không thể tự tạo giao dịch nguyên tử giữa Vault và database.

## 5. Trường hợp 2: wrapping token hết hạn

### 5.1. TTL hoạt động như thế nào?

Khi Vault phát hành wrapping token với TTL, thời gian đếm bắt đầu **khi token được tạo**, không phải khi consumer nhận. Việc xếp hàng, retry message, lệch thời gian hệ thống và thời gian chờ deploy đều ăn vào thời gian hiệu lực này.

Ví dụ:

~~~text
14:00:00  Vault tạo wrapper TTL = 5 phút
14:03:30  Message tới hàng đợi consumer
14:05:10  Consumer bắt đầu kiểm tra -> wrapper có thể đã hết hạn
~~~

Thời điểm và TTL trả về từ lookup chỉ phục vụ đánh giá; **Vault là nguồn quyết định cuối cùng** token còn sử dụng được hay không. Tránh tự dựa vào đồng hồ máy ứng dụng để khẳng định token vẫn hợp lệ. Các độ trễ mạng và race có thể khiến token hết hạn ngay sau lookup.

### 5.2. Cách xử lý khi token hết TTL

1. Không cố dùng lại token hoặc tự chỉnh TTL của token cũ.
2. Ghi trạng thái `EXPIRED_OR_INVALID` khi Vault báo token không còn sử dụng được; đừng tự kết luận 100% nguyên nhân hết hạn nếu lỗi không phân biệt.
3. Yêu cầu hệ thống phát hành **thực hiện lại quy trình tạo secret/wrapper mới**, có authorization và correlation ID mới.
4. Nếu secret bên trong còn tồn tại, cân nhắc thu hồi hoặc dọn dẹp theo vòng đời riêng; wrapping token hết hạn **không bảo đảm** credential gốc đã mất hiệu lực.
5. Điều chỉnh vận hành: giảm độ trễ phát message, lập alert cho queue backlog, chọn TTL đủ cho luồng bình thường nhưng không kéo dài vô hạn.

Không tự “renew” hoặc “rewrap” một wrapper đã hết hạn. API `sys/wrapping/rewrap` có thể tạo wrapper mới từ **wrapper đang còn hợp lệ** trong những quy trình phù hợp; nó không khôi phục token đã mất hiệu lực, và không phải phương án sửa lỗi mặc định khi consumer không biết nội dung đã bị ai dùng.

### 5.3. Chọn TTL thực tế

| Môi trường giao nhận | Rủi ro | Gợi ý thiết kế |
| --- | --- | --- |
| Producer/consumer gọi trực tiếp, ít độ trễ | Token có thể bị lộ trong quá trình truyền | TTL ngắn, TLS, không log token, kiểm tra provenance |
| Chuyển giao qua queue hoặc pipeline | Queue backlog làm TTL hết trước khi xử lý | Đo thời gian chờ p95/p99, điều chỉnh TTL và cảnh báo backlog |
| Tiêu thụ sau khi deploy/restart | Pod chưa sẵn sàng hoặc consumer tạm ngưng | Phối hợp thời điểm phát hành gần thời điểm tiêu thụ |
| Incident recovery kéo dài | Token cũ bị thu hồi hoặc không còn khả dụng | Tạo yêu cầu phát hành mới qua danh tính đã xác minh |

Không có TTL an toàn chung cho mọi hệ thống. Dựa trên thời gian phân phối đã đo và mức ảnh hưởng nếu token bị lộ để chọn giới hạn phù hợp.

## 6. Trường hợp 3: token không đúng nguồn hoặc không đúng nội dung

**Một wrapping token còn hiệu lực vẫn có thể là token sai**. Nó có thể đến từ endpoint khác, environment khác, request khác hoặc gửi nhầm tới consumer. Token hợp lệ chỉ chứng minh Vault có dữ liệu tương ứng; **không** chứng minh dữ liệu đó là loại secret hay thuộc người nhận đang mong đợi.

### 6.1. Kiểm tra `creation_path`

Ví dụ consumer chuyên nhận SecretID cho AppRole `orders-api`:

~~~text
Expected creation_path:
auth/approle/role/orders-api/secret-id

Received creation_path from wrapping lookup:
auth/approle/role/payments-api/secret-id

=> REJECT: đúng dạng token wrapping nhưng sai nguồn phát hành kỳ vọng
~~~

Một API khác như `sys/wrapping/wrap` có thể bọc dữ liệu tùy ý và trả `creation_path` khác với endpoint secret chuyên dụng. Vì vậy khi bắt buộc nhận dữ liệu từ endpoint AppRole, nên so sánh **đường dẫn đầy đủ**, không chỉ kiểm tra nó bắt đầu bằng `auth/approle`.

Với môi trường nhiều namespace Vault Enterprise hoặc nhiều Vault cluster, metadata `creation_path` có thể trùng nhau giữa các môi trường. Khi đó cần kiểm chứng cả **định danh cluster/namespace và kênh kết nối đáng tin**, không xem riêng `creation_path` là nhận diện duy nhất của producer.

### 6.2. Đối chiếu accessor và correlation ID

Nếu producer truyền `wrapping_accessor` và mã yêu cầu qua **kênh đã xác thực, không phụ thuộc vào chính token nhận được**, consumer có thể đối chiếu accessor từ lookup trước unwrap. Điều này giúp phát hiện token bị tráo trong lúc chuyển giao.

Nếu cả token, accessor và request ID đều xuất phát từ **cùng một message không được xác thực**, việc so sánh các giá trị đó không chứng minh sender đáng tin. Nên dùng TLS/mTLS, hàng đợi được cấp quyền theo workload, chữ ký thông điệp hoặc một kênh đã định danh để bảo đảm sự ràng buộc cần thiết.

### 6.3. Kiểm tra schema sau unwrap

Giả sử consumer kỳ vọng phản hồi `data.secret_id` từ endpoint AppRole. Sau khi unwrap thành công, nó vẫn phải kiểm tra cấu trúc dữ liệu, kiểu và các ràng buộc cần thiết trước khi dùng. **Đừng tin một JSON chỉ vì nó được trả về từ một wrapping token hợp lệ**; một luồng upstream có quyền wrap dữ liệu tùy ý vẫn có thể gửi nội dung ngoài schema.

Điểm khó là schema chỉ được biết **sau khi token đã tiêu thụ**. Nếu dữ liệu sai, không thể quay lại bước unwrap với cùng token. Hãy báo lỗi vi phạm hợp đồng, cô lập đầu vào và yêu cầu luồng phát hành đúng; không dùng secret sai hoặc cố tiếp tục bằng giá trị mặc định.

## 7. Thao tác Vault CLI và HTTP API

Ví dụ dưới đây dùng một AppRole `orders-api` đã được quản trị tạo trước. Các đoạn dùng placeholder để tránh in token thật vào tài liệu.

### 7.1. Producer yêu cầu phản hồi được bọc

~~~bash
# Môi trường demo với phiên Vault đã đăng nhập bằng policy phù hợp.
# Tùy phiên bản Vault CLI, -wrap-ttl là cờ dùng để yêu cầu response wrapping.
vault write -wrap-ttl=5m -f \
  auth/approle/role/orders-api/secret-id
~~~

Vault trả `wrapping token` và metadata; phản hồi gốc chứa `secret_id` không được xuất trực tiếp tại producer. **Không ghi nguyên stdout chứa wrapping token vào CI log.** Khi tự động hóa, phải thu token và trao qua kênh bí mật được bảo vệ, đồng thời quản lý TTL ngay từ lúc Vault tạo token.

### 7.2. Lookup token trước khi tiêu thụ

~~~http
POST /v1/sys/wrapping/lookup
Content-Type: application/json
X-Vault-Token: <AUTHORIZED_CLIENT_TOKEN>

{
  "token": "<WRAPPING_TOKEN>"
}
~~~

Ví dụ dữ liệu phản hồi (rút gọn):

~~~json
{
  "data": {
    "creation_path": "auth/approle/role/orders-api/secret-id",
    "creation_time": "2026-11-25T14:00:00Z",
    "creation_ttl": 300,
    "wrapping_accessor": "<WRAPPING_ACCESSOR>"
  }
}
~~~

Lookup cung cấp metadata về wrapper, không giải mã hay trả SecretID. Trường metadata và yêu cầu authentication có thể thay đổi theo cách client gửi token và phiên bản Vault; hãy dùng đúng hợp đồng endpoint đang triển khai. Không dùng lookup như một phép xác nhận token chắc chắn sẽ unwrap được về sau.

### 7.3. Unwrap sau khi đã kiểm tra provenance

~~~http
POST /v1/sys/wrapping/unwrap
Content-Type: application/json
X-Vault-Token: <AUTHORIZED_CLIENT_TOKEN>

{
  "token": "<WRAPPING_TOKEN>"
}
~~~

Với ví dụ SecretID của AppRole, phản hồi unwrap thành công chứa dữ liệu như:

~~~json
{
  "data": {
    "secret_id": "<APPROLE_SECRET_ID>",
    "secret_id_accessor": "<SECRET_ID_ACCESSOR>"
  }
}
~~~

**Đừng nhầm `secret_id_accessor` với `wrapping_accessor`**: một giá trị liên quan tới credential AppRole, giá trị còn lại liên quan tới wrapper. Cả token wrapping lẫn SecretID phải được bảo vệ và không ghi vào log.

Vault cũng hỗ trợ dùng wrapping token qua header trong những kiểu gọi tương ứng. Ví dụ chọn **body `token`** để minh họa khi Spring Vault đã có một authentication token khác cho phiên làm việc; tránh ghi đè token đăng nhập của cả client chỉ để unwrap một giá trị.

## 8. Triển khai kiểm tra và unwrap bằng Spring Vault

`VaultTemplate` triển khai interface `VaultOperations`, có thể gọi `sys/wrapping/lookup` và `sys/wrapping/unwrap` qua HTTP API. Trong phương thức `write(...)`, truyền đường dẫn **không thêm `/v1/`**.

Ví dụ dưới đây chỉ xử lý **wrapped AppRole SecretID** của một role đã biết. Trong sản phẩm thực tế cần cung cấp `VaultOperations` qua cấu hình HTTPS, TLS trust và `ClientAuthentication` theo workload (Kubernetes auth, AppRole bootstrap phù hợp, JWT/OIDC...). Mã không chứa token hoặc mật khẩu cố định.

~~~java
package com.example.security;

import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public final class WrappedSecretIdReceiver {

    private static final String EXPECTED_PATH =
            "auth/approle/role/orders-api/secret-id";

    private final VaultOperations vault;

    public WrappedSecretIdReceiver(VaultOperations vault) {
        this.vault = vault;
    }

    /**
     * Chỉ gọi sau khi hệ thống đã xác minh danh tính người gửi,
     * correlation ID và đã claim quyền xử lý một lần trong database.
     * expectedAccessor phải lấy từ kênh đáng tin tách khỏi token nhận.
     */
    public String unwrapSecretId(String wrappingToken,
                                 String expectedAccessor) {
        requireNonBlank(wrappingToken, "wrappingToken");
        requireNonBlank(expectedAccessor, "expectedAccessor");

        VaultResponse lookup = vault.write(
                "sys/wrapping/lookup",
                Map.of("token", wrappingToken));

        Map<String, Object> metadata = requireData(lookup);
        if (!EXPECTED_PATH.equals(metadata.get("creation_path"))) {
            throw new SecurityException("Unexpected wrapping creation_path");
        }

        if (!expectedAccessor.equals(metadata.get("wrapping_accessor"))) {
            throw new SecurityException("Wrapping accessor mismatch");
        }

        // Một lần unwrap. Nếu timeout, trạng thái là UNKNOWN;
        // KHÔNG tự động gọi lại như một request idempotent.
        VaultResponse unwrapped = vault.write(
                "sys/wrapping/unwrap",
                Map.of("token", wrappingToken));

        Map<String, Object> data = requireData(unwrapped);
        Object secret = data.get("secret_id");
        if (!(secret instanceof String secretId) || secretId.isBlank()) {
            throw new SecurityException("Unexpected unwrap payload");
        }

        return secretId; // Dùng trong luồng bảo vệ; tuyệt đối không log.
    }

    private static Map<String, Object> requireData(VaultResponse response) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Vault response data");
        }
        return response.getData();
    }

    private static void requireNonBlank(String value, String field) {
        if (Objects.isNull(value) || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
    }
}
~~~

Ví dụ sử dụng Java 17+ (pattern matching cho `instanceof`). `String` chỉ nhằm minh họa API: SecretID dạng chuỗi có thể nằm trong Java heap và không thể chủ động xóa chắc chắn; trong hệ thống có yêu cầu nghiêm ngặt, giới hạn phạm vi sống của dữ liệu, tránh giữ trong object dùng lâu và không truyền qua log/trace.

**Giới hạn rõ ràng của ví dụ:**

- `expectedAccessor` phải đến từ **nguồn đáng tin riêng**, không được lấy ngay trong chính `lookup` rồi tự so với nó.
- Client được cấu hình hợp lệ và Vault policy phải cho phép cách gọi wrapping endpoint đã chọn.
- Hàm Java chỉ thực hiện kiểm tra dữ liệu và gọi Vault. **Claim trạng thái trong DB, phân quyền người yêu cầu, audit, retry policy và đối soát** thuộc tầng điều phối.
- Với phản hồi gốc chứa `auth` thay vì `data`, cần giải mã theo đúng kiểu phản hồi cụ thể; code này chỉ áp dụng cho SecretID có `data.secret_id`.
- Sau khi nhận secret, caller cần dùng nó tại đúng AppRole/môi trường đã phê duyệt, không chuyển dữ liệu ra API hoặc ngoại vi không đáng tin.

### 8.1. Không biến mọi lỗi thành “đã hết hạn”

Một cách phân loại lỗi ở tầng điều phối:

~~~java
// Pseudocode: repository/audit/exception mapper là thành phần của ứng dụng.
try {
    String secretId = receiver.unwrapSecretId(token, trustedAccessor);
    useSecretIdForApprovedLogin(secretId);
    deliveryRepository.markConsumed(deliveryId);
} catch (SecurityException e) {
    deliveryRepository.markRejected(deliveryId);
    alertSecurityTeam(deliveryId, "provenance-or-payload-mismatch");
} catch (Exception e) {
    // Với lỗi mạng/timeout/trạng thái HTTP không xác định, không
    // giả định Vault chưa tiêu thụ token.
    deliveryRepository.markUncertain(deliveryId);
    scheduleManualOrControlledReconciliation(deliveryId);
}
~~~

Đây chỉ là phác thảo. Production cần phân loại rõ lỗi input trước khi gửi request, lỗi lookup, lỗi unwrap, lỗi downstream và mất kết nối khi ghi DB. Ngoài ra, nếu việc dùng SecretID **đã thành công** nhưng ghi database thất bại, cần đối soát tác dụng nghiệp vụ để không đăng nhập hoặc cấp credential lặp ngoài ý muốn.

## 9. Bảng quyết định cho các lỗi thường gặp

| Hiện tượng quan sát | Điều có thể kết luận | Hành động đề xuất |
| --- | --- | --- |
| Lookup trả lỗi token không hợp lệ | Wrapper không dùng được ở thời điểm lookup; chưa biết chắc đã unwrap hay hết TTL | Kiểm tra delivery journal, audit, thời điểm nhận; cảnh báo nếu không có bằng chứng tiêu thụ hợp lệ |
| Đã có `CONSUMED` cho cùng request ID | Ứng dụng đã ghi nhận kết quả xử lý thành công trước đó | Không gọi unwrap nữa; trả kết quả nghiệp vụ đã ghi |
| TTL dự kiến đã qua | Token có khả năng hết hạn, không bảo đảm nguyên nhân duy nhất | Yêu cầu producer cấp lại qua luồng xác thực; không kéo dài token cũ |
| `creation_path` sai | Token không trỏ đến endpoint phát hành đã kỳ vọng | Từ chối trước unwrap, ghi sự kiện provenance mismatch |
| `wrapping_accessor` khác accessor đáng tin | Token có thể bị tráo hoặc message sai | Cô lập delivery, báo an ninh, không unwrap |
| Lookup thành công nhưng unwrap lỗi | Token có thể hết hạn/bị tiêu thụ giữa hai bước, hoặc Vault/network lỗi | Ghi `UNCERTAIN`, đối soát; không assume success |
| Unwrap thành công nhưng không có `secret_id` | Nội dung không đúng schema luồng AppRole | Từ chối sử dụng nội dung, báo lỗi contract, đề nghị cấp mới |
| HTTP `403` từ client Vault | Auth token/policy hoặc ngữ cảnh xác thực có vấn đề | Kiểm tra workload auth, policy và đường dẫn; không dùng root token để “thử cho chạy” |
| HTTP `429`/`5xx`/timeout | Lỗi tạm thời hoặc trạng thái yêu cầu chưa rõ | Kiểm tra giai đoạn lỗi và khả năng đã tiêu thụ; retry chỉ sau đối soát được phép |

Mã HTTP và chuỗi thông báo lỗi **phụ thuộc phiên bản Vault, chính sách và cách request được gửi**. Không hardcode một mã lỗi duy nhất thành chẩn đoán “already unwrapped” hay “expired”.

## 10. Bảo vệ token và điều tra nguồn phát

Wrapping token là **bearer credential**: ai lấy được nó trước khi unwrap có thể có cơ hội nhận dữ liệu đã bọc. Bảo mật của luồng chuyển giao phụ thuộc vào việc bảo vệ token trong suốt thời gian hiệu lực.

Khuyến nghị:

1. **Không ghi log token:** tránh log header `X-Vault-Token`, `wrap_info.token`, request body `token`, HTTP trace hoặc exception chứa secret.
2. **Bảo vệ đường truyền:** dùng TLS, mTLS khi thích hợp; khóa truy cập queue/secret store theo danh tính workload và phân tách môi trường.
3. **Định danh request:** dùng delivery ID riêng, lưu issuer/endpoint kỳ vọng, thời điểm phát hành và accessor dùng cho đối chiếu. Tránh dùng chính wrapping token làm khóa audit hay idempotency.
4. **Giảm bề mặt truy cập:** producer chỉ được phép phát hành loại secret cần thiết; consumer chỉ được phép lookup/unwrap cho luồng được giao; giới hạn quyền nội bộ theo tenant/owner.
5. **Cảnh báo bất thường:** nhiều token cùng request, provenance mismatch, số lượng unwrap fail tăng, TTL hết trước khi xử lý hoặc đột biến trong queue backlog.

Nếu nghi token bị lộ, hãy ngừng chuyển tiếp token, cách ly yêu cầu và dùng quy trình thu hồi wrapper/credential tương ứng khi còn khả thi. **Thu hồi wrapping token không tự bảo đảm secret gốc đã bị vô hiệu hóa**, nhất là nếu secret đã được unwrap hoặc đang nằm trong một hệ thống khác; cần đánh giá việc revoke AppRole SecretID, database credential hoặc lease tùy loại secret.

### 10.1. Những gì Vault audit và log ứng dụng có thể giúp

Audit Vault (khi được cấu hình) và log nghiệp vụ có thể hỗ trợ đối chiếu thời điểm gọi lookup/unwrap, response status, token accessor hoặc request ID mà không cần lộ token. Cần hiểu cách Vault audit hash/redact dữ liệu, kiểm soát quyền xem audit log và retention.

**Không kỳ vọng audit mặc nhiên chứng minh ai nhận được bản rõ**: request có thể đã xử lý nhưng caller mất kết nối, log có thể thiếu hoặc dữ liệu đã bị tiêu thụ ngoài ứng dụng. Đánh giá kết hợp sự kiện producer, broker, Vault, consumer và hệ thống downstream.

## 11. Kiểm thử tích hợp và fault injection

Để kiểm tra thực tế, dùng Vault test cô lập với chính sách riêng. Có thể chạy Vault trong môi trường kiểm thử với lifecycle rõ ràng, tạo AppRole test và cấp SecretID được response-wrap. Không dùng token/SecretID production trong fixture, sample hay log của test.

| Kịch bản | Cách thực hiện | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | Tạo wrapper TTL phù hợp, lookup đúng path/accessor, unwrap | Nhận `data.secret_id`, đánh dấu `CONSUMED` |
| Unwrap lần hai | Dùng lại token đã tiêu thụ | Vault từ chối; consumer không xử lý thành công lần hai |
| Hết TTL | Tạo wrapper TTL rất ngắn, chờ quá hạn trong test | Lookup/unwrap không còn lấy được payload; đề nghị phát hành mới |
| Sai nguồn | Tạo wrapper từ role hoặc endpoint khác | Bị chặn trước unwrap khi so sánh `creation_path` |
| Accessor bị tráo | Thay expected accessor bằng giá trị hợp lệ của request khác | Bị từ chối trước unwrap |
| Dữ liệu sai schema | Bọc payload có cấu trúc khác nhưng chỉ chấp nhận SecretID | Báo lỗi payload, không login bằng dữ liệu sai |
| Hai consumer song song | Cùng claim một delivery | Chỉ một worker được phép gọi unwrap |
| Timeout sau request | Cắt kết nối hoặc inject failure sau khi gửi unwrap | Trạng thái `UNCERTAIN`; không retry mù |
| Auth token hết hạn | Làm hết hiệu lực session token theo phương thức auth dùng trong test | Báo lỗi auth và xử lý đăng nhập lại; không nhầm với TTL của wrapper |

**Ví dụ khung kiểm thử (JUnit 5/AssertJ):**

~~~java
@Test
void rejectsWrapperFromUnexpectedCreationPath() {
    // Fixture cấp wrapper của role khác, trong Vault test độc lập.
    String otherRoleToken = testVault.wrapSecretId("payments-api");
    String trustedAccessor = testVault.accessorFor(otherRoleToken);

    assertThatThrownBy(() ->
            receiver.unwrapSecretId(otherRoleToken, trustedAccessor))
            .isInstanceOf(SecurityException.class)
            .hasMessageContaining("creation_path");

    // Xác minh ở tầng test rằng thao tác unwrap chưa được gọi.
}
~~~

`testVault` là fixture giả định, cần xây dựng trong dự án. Test này minh họa điều kiện nghiệp vụ; không có nghĩa đoạn mã là một test độc lập có thể chạy ngay. Các test tích hợp cần dùng Vault thật trong môi trường test, kiểm tra quyền token theo workload, và xác nhận wrapper **chưa bị tiêu thụ** ở tình huống sai nguồn.

Với test TTL, dùng thời gian chờ có giới hạn, không để test treo hoặc phụ thuộc một giá trị sleep cố định. Với fault injection, phải quan sát liệu Vault đã tiêu thụ token hay chưa qua hành vi/API/audit thích hợp, thay vì gán một kết luận theo lỗi mạng.

## 12. Bài thực hành: nhận AppRole SecretID an toàn

**Bối cảnh:** pipeline triển khai tạo SecretID cho service `orders-api` và gửi wrapping token qua queue riêng. Consumer Spring Boot nhận token, unwrap và dùng SecretID để login theo AppRole trước khi truy cập KV/Transit/PKI tùy policy được cấp.

Các bước thực hành:

1. Cấu hình Vault test với AppRole `orders-api`, một AppRole `payments-api` dùng để thử sai nguồn, policy phát hành SecretID và policy consumer thích hợp.
2. Tạo wrapping token TTL ngắn từ endpoint `auth/approle/role/orders-api/secret-id`, lưu metadata kiểm chứng trong một bản ghi delivery đáng tin.
3. Dùng `sys/wrapping/lookup` xác nhận `creation_path` và `wrapping_accessor` đúng kỳ vọng; sau đó gọi unwrap một lần.
4. Thử gửi lại cùng token, để token hết TTL, thay token của role khác và thay accessor; ghi nhận trạng thái nội bộ khác nhau.
5. Tạo hai consumer cạnh tranh cùng request, dùng compare-and-set để chỉ một consumer gọi unwrap.
6. Giả lập timeout sau khi gửi unwrap, chuyển request sang `UNCERTAIN`, diễn tập quy trình đối soát và yêu cầu phát hành mới.
7. Kiểm tra dashboard: tỷ lệ thành công, mismatch, lỗi auth, thời gian queue và độ tuổi token khi tới consumer; đảm bảo không log secret/token.

**Câu hỏi tự kiểm tra:**

1. Vì sao không thể coi lỗi “wrapping token invalid” đồng nghĩa chắc chắn với “token đã được unwrap”?
2. `creation_path` chứng minh được điều gì, và không chứng minh được điều gì về người gửi?
3. Vì sao chỉ so sánh accessor lấy từ cùng message không được xác thực là chưa đủ?
4. Khi lookup thành công nhưng unwrap timeout, tại sao retry ngay có thể che mất tình huống token đã được tiêu thụ?
5. TTL của wrapping token khác TTL của AppRole SecretID và lease của dynamic secret thế nào?
6. Tại sao database cần trạng thái `UNCERTAIN` thay vì chỉ hai trạng thái thành công/thất bại?

## 13. Tổng kết

Trong **Vault Cubbyhole và response wrapping**, wrapping token đại diện cho một quyền **đọc phản hồi bí mật một lần trong thời hạn ngắn**. Khi token đã unwrap, hết TTL hoặc không đúng nguồn kỳ vọng, hệ thống phải xử lý theo trạng thái được chứng minh, không suy diễn nguyên nhân từ một mã lỗi chung. Kiểm tra `creation_path`/accessor, ràng buộc danh tính workload và request ID, khóa xử lý trùng, audit và đối soát khi timeout là những điểm then chốt.

Với **Spring Vault**, `VaultOperations` có thể gọi `sys/wrapping/lookup` để xem metadata trước khi gọi `sys/wrapping/unwrap`. Kết quả unwrap chỉ nên được dùng trong nghiệp vụ đã phê duyệt và bảo vệ dữ liệu trong bộ nhớ. Cách thiết kế này giúp ứng dụng Java xử lý được các tình huống đã tiêu thụ, hết hạn và sai nguồn mà vẫn giữ đúng nguyên tắc bí mật, phân quyền và kiểm thử tích hợp của HashiCorp Vault.

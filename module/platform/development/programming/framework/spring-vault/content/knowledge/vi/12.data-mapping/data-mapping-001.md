# VaultResponse, VaultResponseSupport và phần dữ liệu nghiệp vụ

## Mục tiêu bài học

Khi một ứng dụng Java truy cập HashiCorp Vault bằng Spring Vault, kết quả trả về không chỉ có thông tin ứng dụng cần dùng (mật khẩu, khóa API, cấu hình kết nối). Vault còn trả về **thông tin bao ngoài phản hồi** như mã yêu cầu, thông tin lease, cảnh báo và đôi khi là thông tin xác thực. Hai kiểu `VaultResponse` và `VaultResponseSupport<T>` giúp Java biểu diễn các phần này mà không trộn lẫn chúng với dữ liệu nghiệp vụ.

Sau bài này, người học có thể:

1. Phân biệt `VaultResponse` với `VaultResponseSupport<T>` và xác định kiểu dữ liệu do `getData()` trả về.
2. Tách phần dữ liệu nghiệp vụ khỏi metadata, lease và thông tin xác thực của phản hồi Vault.
3. Đọc secrets bằng `VaultOperations`/`VaultTemplate` và `VaultKeyValueOperations`, kể cả sự khác biệt giữa KV v1 và KV v2.
4. Ánh xạ secrets vào `Map<String, Object>` hoặc một kiểu Java cụ thể, đồng thời xử lý trường hợp dữ liệu không tồn tại hoặc không hợp lệ.
5. Tránh ghi lộ secrets khi chẩn đoán lỗi, ghi log và kiểm thử.

> **Phạm vi:** Bài tập trung vào **cấu trúc phản hồi và ánh xạ dữ liệu** trong Spring Vault. Việc thiết lập phương thức xác thực theo workload, cấp policy, gia hạn token/lease, mã hóa Transit và cấp chứng chỉ PKI được nhắc đến để đặt ngữ cảnh; mỗi nội dung đó cần quy trình riêng. Các ví dụ giả định ứng dụng đã có một `VaultOperations`/`VaultTemplate` được cấu hình hợp lệ và Vault policy cho phép đọc đường dẫn tương ứng.

## 1. Hiểu phản hồi của Vault trước khi ánh xạ

Vault cung cấp API qua HTTP. Phản hồi thành công từ nhiều endpoint có dạng JSON tổng quát gần như sau (các giá trị chỉ mang tính minh họa):

```json
{
  "request_id": "request-example",
  "lease_id": "",
  "renewable": false,
  "lease_duration": 0,
  "data": {
    "apiKey": "<gia-tri-bi-mat>",
    "endpoint": "https://payments.internal.example"
  },
  "warnings": null
}
```

Đọc cấu trúc trên theo **hai lớp**:

```text
Phản hồi Vault
├── request_id, lease_id, lease_duration, renewable, warnings, ...
│   └── Thông tin bao ngoài: theo dõi yêu cầu và vòng đời secrets
└── data
    └── Dữ liệu do secrets engine trả về
        ├── apiKey
        └── endpoint
```

`data` là tên **trường trong phản hồi Vault**; nó không tự động đồng nghĩa với một đối tượng Java đã được kiểm tra tính hợp lệ. Với một số secrets engine, chính phần `data` còn chứa các lớp cấu trúc khác. Với một số API xác thực, dữ liệu quan trọng có thể nằm trong `auth`; với một số phản hồi PKI, dữ liệu lại có các trường chứng chỉ và khóa. Vì thế, cần hiểu endpoint đang gọi trước khi quyết định ánh xạ.

Trong ví dụ dịch vụ thanh toán, dữ liệu nghiệp vụ là `apiKey` và `endpoint`. `request_id` hỗ trợ truy vết, còn `lease_id` và `lease_duration` mô tả vòng đời một secret có lease khi endpoint cung cấp những thông tin đó. Không nên đưa các trường bao ngoài vào lớp `PaymentSecret` chỉ vì chúng cùng xuất hiện trong một JSON.

## 2. `VaultResponseSupport<T>` và `VaultResponse` khác nhau thế nào?

Hai lớp nằm trong package `org.springframework.vault.support`:

```java
public class VaultResponseSupport<T> { /* dữ liệu có kiểu T */ }

public class VaultResponse
        extends VaultResponseSupport<Map<String, Object>> { /* ... */ }
```

Đoạn trên mô tả **quan hệ kiểu**, không phải mã cần viết lại trong dự án. `VaultResponseSupport<T>` là kiểu tổng quát chứa dữ liệu `T` và thông tin bao ngoài của phản hồi; `VaultResponse` là biến thể chuyên biệt mà `data` được ánh xạ vào `Map<String, Object>`.

| Khía cạnh | `VaultResponse` | `VaultResponseSupport<T>` |
|---|---|---|
| Kiểu của `getData()` | `Map<String, Object>` | `T` |
| Mục đích thường gặp | Đọc secrets không xác định trước schema, thao tác trực tiếp với API | Đọc secrets đã có schema Java, hoặc phản hồi của API chuyên biệt |
| Ưu điểm | Linh hoạt với các khóa khác nhau | Dễ sử dụng thuộc tính có kiểu, giảm ép kiểu thủ công |
| Điều cần chú ý | Phải kiểm tra khóa, kiểu giá trị và sự tồn tại của dữ liệu | Phải bảo đảm cấu trúc JSON khớp kiểu Java cần ánh xạ |
| Thông tin bao ngoài | Có | Có |

### 2.1. Các phương thức cần nhớ

| Phương thức | Ý nghĩa | Lưu ý |
|---|---|---|
| `getData()` | Lấy phần dữ liệu phản hồi, có thể `null` | Không bảo đảm rằng secret tồn tại hoặc đủ các trường nghiệp vụ |
| `getRequiredData()` | Lấy dữ liệu và yêu cầu nó không được `null` | Ném `IllegalStateException` nếu **phần data của phản hồi** là `null`; không xử lý trường hợp **chính phản hồi** là `null` |
| `getRequestId()` | Lấy mã yêu cầu do Vault trả về, nếu có | Hữu ích để liên hệ log phía Vault mà không ghi giá trị secret |
| `getLeaseId()` | Lấy ID lease, nếu có | Không phải tất cả secrets đều có lease |
| `getLeaseDuration()` | Lấy thời lượng lease phản hồi cung cấp, theo giây | Không được coi là thời gian tồn tại của mọi giá trị KV |
| `isRenewable()` | Cho biết lease trong phản hồi có khả năng gia hạn hay không | Không đồng nghĩa ứng dụng đã gia hạn lease thành công |
| `getWarnings()` | Lấy các cảnh báo do Vault trả về, nếu có | Kiểm tra thông điệp trước khi đưa vào log |
| `getAuth()` | Lấy payload xác thực, nếu endpoint trả về | Có thể chứa token hoặc dữ liệu nhạy cảm; không ghi log nguyên bản |
| `getMetadata()` | Lấy metadata của phản hồi, nếu có | Không mặc định là metadata phiên bản KV v2 |

`getData()` trả `null` là một tình huống hợp lệ ở tầng đối tượng. `getRequiredData()` chỉ là một cách thể hiện giả định “phản hồi này nhất định phải có dữ liệu” và sẽ báo lỗi khi giả định đó sai. Cả hai đều **không thay thế** việc kiểm tra nghiệp vụ, ví dụ xác nhận `apiKey` không rỗng hoặc một URL có định dạng đúng.

### 2.2. Tránh nhầm dữ liệu phản hồi và dữ liệu nghiệp vụ

Giả sử Vault trả về thông tin tài khoản cơ sở dữ liệu từ một dynamic secrets engine:

```json
{
  "request_id": "request-db-example",
  "lease_id": "database/creds/reporting/lease-example",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "generated-user",
    "password": "<gia-tri-bi-mat>"
  }
}
```

Ở đây, `username` và `password` là dữ liệu để kết nối cơ sở dữ liệu. `lease_id`, `lease_duration` và `renewable` mô tả vòng đời của bộ thông tin đăng nhập do Vault cấp. Nếu chỉ lưu hai trường nghiệp vụ mà bỏ qua lease, ứng dụng có thể tiếp tục sử dụng credentials đã hết hạn. Việc theo dõi, gia hạn và thu hồi lease cần cơ chế quản lý vòng đời phù hợp của Spring Vault, thay vì tự kết luận rằng mọi kết quả đọc đều có thời hạn giống nhau.

Ngược lại, một secret lưu tĩnh bằng KV thường không có một lease có thể gia hạn như dynamic credentials. Không dùng `getLeaseDuration() == 0` để suy ra rằng secrets KV “không bao giờ cần xoay vòng”; chính sách rotation của hệ thống vẫn có thể yêu cầu thay đổi giá trị định kỳ.

## 3. Đọc dữ liệu linh hoạt bằng `VaultResponse`

Khi chưa cần DTO riêng hoặc secrets có các thuộc tính linh hoạt, `VaultResponse` là điểm bắt đầu đơn giản. Đoạn mã sau sử dụng KV v1 được mount tại `legacy-kv`:

```java
import java.util.Map;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

public final class LegacyPaymentReader {
    private final VaultKeyValueOperations keyValue;

    public LegacyPaymentReader(VaultOperations vaultOperations) {
        this.keyValue = vaultOperations.opsForKeyValue(
                "legacy-kv", KeyValueBackend.KV_1);
    }

    public String readEndpoint() {
        VaultResponse response = keyValue.get("payments/runtime");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Không tìm thấy cấu hình thanh toán");
        }

        Map<String, Object> data = response.getRequiredData();
        Object endpoint = data.get("endpoint");

        if (!(endpoint instanceof String url) || url.isBlank()) {
            throw new IllegalStateException("Thiếu endpoint hợp lệ");
        }

        return url;
    }
}
```

Ví dụ dùng cú pháp `instanceof` có binding biến của Java 16+; với Java cũ hơn, hãy kiểm tra kiểu rồi ép kiểu theo cú pháp truyền thống.

Quy trình đọc gồm bốn bước: (1) chọn KV mount và version; (2) đọc path **tương đối với mount**; (3) kiểm tra kết quả có tồn tại; (4) lấy `data` rồi kiểm tra từng giá trị nghiệp vụ. `getRequiredData()` chỉ giúp chặn `data == null`; nó không tự bảo đảm rằng khóa `endpoint` tồn tại hoặc chứa chuỗi.

### Khi nào chọn `Map`?

- Hệ thống phải đọc secrets có bộ khóa thay đổi theo môi trường hoặc theo khách hàng.
- Đang viết adapter chung, chưa biết trước kiểu đối tượng Java.
- Cần quan sát cấu trúc phản hồi khi tích hợp một endpoint mới **trong môi trường thử nghiệm**, nhưng không in giá trị bí mật ra log.

Khi cấu trúc đã ổn định, một DTO có kiểu thường giúp mã nghiệp vụ rõ ràng hơn. Với dữ liệu dạng `Map`, không nên dùng `String.valueOf(data.get("apiKey"))` để che giấu giá trị `null`: chuỗi ký tự `"null"` có thể bị hiểu nhầm là một secret hợp lệ.

## 4. Ánh xạ có kiểu bằng `VaultResponseSupport<T>`

Giả sử KV v2 được mount ở `secret`; đường dẫn logic `payments/runtime` chứa các trường sau:

```json
{
  "apiKey": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "timeoutSeconds": 5
}
```

Ứng dụng Java 17+ có thể mô tả phần dữ liệu nghiệp vụ bằng một `record`:

```java
public record PaymentSecret(
        String apiKey,
        String endpoint,
        Integer timeoutSeconds
) {}
```

Đây là **dữ liệu nghiệp vụ**, không chứa `request_id`, `lease_id` hay các thuộc tính nội bộ khác của phản hồi. Giữ `timeoutSeconds` là `Integer` thay vì `int` trong ví dụ để có thể phát hiện trường hợp thuộc tính này bị thiếu (`null`), thay vì vô tình nhận giá trị mặc định `0`.

Sử dụng overload `get(path, Class<T>)` của `VaultKeyValueOperations`:

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class PaymentSecretReader {
    private final VaultKeyValueOperations keyValue;

    public PaymentSecretReader(VaultOperations vaultOperations) {
        this.keyValue = vaultOperations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public PaymentSecret load() {
        VaultResponseSupport<PaymentSecret> response =
                keyValue.get("payments/runtime", PaymentSecret.class);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Chưa có secret cho dịch vụ thanh toán");
        }

        PaymentSecret secret = response.getRequiredData();

        if (secret.apiKey() == null || secret.apiKey().isBlank()) {
            throw new IllegalStateException("Secret thiếu apiKey");
        }
        if (secret.endpoint() == null || secret.endpoint().isBlank()) {
            throw new IllegalStateException("Secret thiếu endpoint");
        }
        if (secret.timeoutSeconds() == null || secret.timeoutSeconds() <= 0) {
            throw new IllegalStateException("timeoutSeconds phải là số dương");
        }

        return secret;
    }
}
```

`VaultResponseSupport<PaymentSecret>` biểu diễn **cả phản hồi có metadata**; `PaymentSecret` chỉ là đối tượng trả về từ `response.getData()`. Spring Vault thực hiện chuyển đổi dữ liệu được đọc sang `PaymentSecret.class` theo cấu hình ánh xạ/JSON tương ứng. Thuộc tính trong secret phải khớp kiểu dữ liệu và cách đặt tên mà bộ ánh xạ hỗ trợ; với các phiên bản Java không hỗ trợ `record`, có thể dùng POJO với constructor và accessor thích hợp.

Phần thiết yếu cần ghi nhớ:

```text
VaultKeyValueOperations.get("payments/runtime", PaymentSecret.class)
                │
                ▼
VaultResponseSupport<PaymentSecret>
                │
                ├── getRequestId()      → thông tin bao ngoài (nếu có)
                ├── getLeaseDuration()  → thông tin lease (nếu có)
                └── getData()           → PaymentSecret
                                             ├── apiKey
                                             ├── endpoint
                                             └── timeoutSeconds
```

**Ưu điểm chính của cách đọc có kiểu** là phần còn lại của ứng dụng không cần thao tác với `Map<String, Object>` và ép kiểu lặp lại. Tuy nhiên, lớp dữ liệu có kiểu không thay cho validation. Ví dụ tên trường sai, một giá trị số không chuyển đổi được, hoặc cấu trúc lồng nhau không khớp DTO có thể dẫn đến thất bại khi ánh xạ; việc có kiểu Java không chứng minh secret hợp lệ về mặt nghiệp vụ.

## 5. Điểm dễ nhầm nhất: KV v1, KV v2 và hai lớp `data`

Vault KV hỗ trợ hai kiểu API. **KV v1** không lưu lịch sử phiên bản của mỗi secret. **KV v2** hỗ trợ phiên bản và trả về cấu trúc JSON lồng nhau ở endpoint dữ liệu.

### 5.1. KV v1: dữ liệu nằm trực tiếp dưới `data`

Với endpoint đại diện `secret/orders`, phản hồi KV v1 có thể trông như sau:

```json
{
  "data": {
    "apiKey": "<gia-tri-bi-mat>"
  }
}
```

Khi dùng `vaultOperations.read("secret/orders")`, `VaultResponse.getData()` cung cấp `Map` chứa khóa `apiKey` (giả sử secret tồn tại và Vault cho phép truy cập).

### 5.2. KV v2: có thêm một `data` lồng trong lớp dữ liệu phản hồi

Với KV v2 mount `secret`, endpoint HTTP đọc secret thực tế có đường dẫn dạng `secret/data/orders`. Phản hồi rút gọn:

```json
{
  "data": {
    "data": {
      "apiKey": "<gia-tri-bi-mat>"
    },
    "metadata": {
      "version": 3,
      "created_time": "2026-01-01T00:00:00Z"
    }
  }
}
```

Vì vậy, nếu gọi API tổng quát `vaultOperations.read("secret/data/orders")`, ta cần chú ý:

```text
VaultResponse.getData()
    └── map chứa "data" và "metadata" của KV v2
        ├── "data"     → map chứa apiKey (dữ liệu nghiệp vụ)
        └── "metadata" → metadata phiên bản KV v2
```

Ví dụ đọc trực tiếp:

```java
VaultResponse response = vaultOperations.read("secret/data/orders");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("Không tìm thấy orders secret");
}

Map<String, Object> outerData = response.getRequiredData();
Object innerData = outerData.get("data");
if (!(innerData instanceof Map<?, ?> values)) {
    throw new IllegalStateException("Phản hồi KV v2 thiếu data hợp lệ");
}

Object key = values.get("apiKey");
if (!(key instanceof String apiKey) || apiKey.isBlank()) {
    throw new IllegalStateException("Thiếu apiKey hợp lệ");
}

// Dùng apiKey nội bộ; tuyệt đối không ghi trực tiếp giá trị vào log.
```

Ở ví dụ này, `outerData.get("metadata")` là metadata **của phiên bản secret KV v2**. Nó khác với việc tùy tiện giả định `response.getMetadata()` của `VaultResponseSupport` luôn chứa version. Hai cấu trúc có nguồn gốc khác nhau và phải được đọc theo đúng API đang dùng.

### 5.3. Chọn `VaultKeyValueOperations` để tránh bóc lớp thủ công

Spring Vault cung cấp `VaultKeyValueOperations` để trừu tượng hóa cách đặt đường dẫn và cấu trúc dữ liệu của KV v1/KV v2:

```java
VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponse response = kv.get("orders");
if (response == null) {
    throw new IllegalStateException("Secret orders không tồn tại");
}

Map<String, Object> businessData = response.getRequiredData();
Object key = businessData.get("apiKey");
```

Trong trường hợp này, `businessData` chứa các trường nghiệp vụ như `apiKey`; người gọi không cần tự thêm `data/` vào đường dẫn hoặc tự mở `data.data`. Tương tự, overload `kv.get("orders", PaymentSecret.class)` có thể trả về dữ liệu đã ánh xạ sang đối tượng Java có kiểu.

| Cách đọc | Path truyền vào | Dữ liệu cần lấy |
|---|---|---|
| `vaultOperations.read(...)` với KV v1 | Đường dẫn đầy đủ, ví dụ `legacy-kv/orders` | `response.getData().get("apiKey")` |
| `vaultOperations.read(...)` với KV v2 | Đường dẫn API đầy đủ, ví dụ `secret/data/orders` | `response.getData().get("data")`, sau đó lấy `apiKey` từ map bên trong |
| `opsForKeyValue("secret", KV_2).get(...)` | Đường dẫn logic tương đối, ví dụ `orders` | `response.getData().get("apiKey")` |
| `opsForKeyValue("secret", KV_2).get(..., PaymentSecret.class)` | Đường dẫn logic tương đối, ví dụ `payments/runtime` | `response.getData()` có kiểu `PaymentSecret` |

Đừng gọi `opsForKeyValue("secret", KV_2).get("data/orders")`: `data/` thuộc đường dẫn API của KV v2, không thuộc đường dẫn logic truyền vào API KV của Spring Vault. Nếu cần truy vấn một **phiên bản cụ thể** hoặc thao tác metadata phiên bản một cách rõ ràng, hãy dùng API chuyên biệt `VaultVersionedKeyValueOperations`.

## 6. Xử lý dữ liệu thiếu, lỗi ánh xạ và giới hạn phân quyền

Một hàm đọc secrets trong ứng dụng thực tế cần phân biệt ít nhất ba tình huống:

| Tình huống | Dấu hiệu có thể gặp | Xử lý đề xuất |
|---|---|---|
| Không có secret ở đường dẫn được đọc | Phương thức `get(...)`/`read(...)` trả `null` khi không tìm thấy | Kiểm tra `response == null` trước; quyết định thiếu cấu hình có phải lỗi khởi động hay không |
| Có phản hồi nhưng `data` rỗng, thiếu trường hoặc sai kiểu | `getData() == null`, thiếu khóa, giá trị không đúng kiểu; hoặc thất bại khi chuyển đổi vào DTO | Xác thực schema, kiểu dữ liệu và các trường bắt buộc; báo lỗi gắn với tên trường, không gắn với giá trị secret |
| Không đủ quyền, không xác thực được, mất kết nối hoặc lỗi máy chủ | Vault/Spring Vault báo lỗi truy cập, xác thực hay I/O | Phân loại sự cố theo quyền, xác thực và kết nối; tránh coi mọi lỗi là “secret không tồn tại” |

Điểm mấu chốt: **không được tự chuyển lỗi 403 thành dữ liệu `null`** chỉ để chạy tiếp. Quyền Vault policy, identity của workload và tên mount/path cần được kiểm tra đúng nguyên nhân. Tương tự, một lỗi deserialize không được biến thành giá trị mặc định rỗng cho một credential bắt buộc.

Mẫu kiểm tra đọc có kiểu nên theo thứ tự:

1. Xác định đúng mount và engine version, sử dụng path phù hợp.
2. Đọc secret và xử lý riêng trường hợp phản hồi không tồn tại.
3. Kiểm tra `response.getData()` hoặc dùng `getRequiredData()` khi đã bảo đảm `response != null`.
4. Kiểm tra giá trị nghiệp vụ (không rỗng, đúng định dạng, đúng phạm vi cho phép).
5. Chỉ đưa đối tượng đã hợp lệ vào cấu phần cần dùng; tránh giữ secrets ở nhiều bản sao không cần thiết.

### Ghi log và giám sát an toàn

**Không** log toàn bộ `VaultResponse`, `VaultResponseSupport<T>`, `response.getData()` hoặc một DTO chứa password/token/API key. Tránh cả `toString()` tự sinh của Java `record`: nó có thể hiển thị tất cả giá trị thuộc tính, kể cả `apiKey`.

Có thể ghi những thông tin được kiểm soát như tên thao tác, tên mount/path **không nhạy cảm**, trạng thái thành công/thất bại, thời lượng truy vấn và mã yêu cầu từ `getRequestId()` nếu chính sách vận hành cho phép. Trước khi log bất kỳ metadata, warnings hoặc auth payload nào, cần cân nhắc khả năng chứa thông tin nhạy cảm. Không log `getAuth()` hay secret value nguyên bản.

Nếu một secret có lease động, thông tin lease trong phản hồi hỗ trợ quan sát vòng đời. Song việc gia hạn/thu hồi thường được quản lý qua cơ chế chuyên dụng của Spring Vault, như quản lý lease và session tương ứng; không nên tự suy diễn rằng mỗi lần gọi `getData()` cũng gia hạn lease hay token.

## 7. Ví dụ tích hợp: chọn lớp nào trong một dịch vụ Java?

Giả sử một dịch vụ Spring cần lấy cấu hình để gọi cổng thanh toán:

```text
Ứng dụng Java
    │
    ├── Xác thực với Vault bằng phương thức phù hợp workload
    │
    └── VaultOperations / VaultTemplate
            │
            └── opsForKeyValue("secret", KV_2)
                    │
                    └── get("payments/runtime", PaymentSecret.class)
                            │
                            └── VaultResponseSupport<PaymentSecret>
                                    └── getRequiredData()
                                            └── PaymentSecret → PaymentClient
```

`PaymentClient` chỉ cần `endpoint` và `apiKey`, không cần biết kết quả HTTP ban đầu có `request_id` hay không. Thành phần đọc Vault chịu trách nhiệm chọn đường dẫn, giải mã/ánh xạ, kiểm tra dữ liệu, và quyết định cách báo lỗi. Cách tách này giúp logic thanh toán không phụ thuộc trực tiếp vào định dạng phản hồi của Vault.

Các lựa chọn thường gặp:

| Nhu cầu | Kiểu nên cân nhắc | Vì sao |
|---|---|---|
| Khám phá hoặc đọc secret với các khóa linh hoạt | `VaultResponse` | Dữ liệu là `Map<String, Object>` |
| Dùng một cấu hình nghiệp vụ có schema ổn định | `VaultResponseSupport<YourDto>` | Mã gọi có thuộc tính và kiểu rõ ràng |
| Đọc KV v1 hoặc KV v2 mà không muốn tự bóc cấu trúc HTTP | `VaultKeyValueOperations` | Đường dẫn và cấu trúc KV được xử lý theo phiên bản được chọn |
| Đọc/ghi phiên bản cụ thể của KV v2 | `VaultVersionedKeyValueOperations` | Hỗ trợ `Versioned<T>` và metadata phiên bản |
| Nhận secret động có lease | Phản hồi chuyên biệt hoặc `VaultResponseSupport<T>` cùng cơ chế quản lý lease | Phải xử lý thêm thời hạn và vòng đời secret |

Đây là tiêu chí thiết kế, không phải quy tắc cứng: lựa chọn cuối cùng phụ thuộc endpoint Vault, phiên bản Spring Vault, schema dữ liệu và yêu cầu vận hành của ứng dụng.

## 8. Thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Đọc secret dạng Map

Tạo KV v1 tại mount thử nghiệm `training-kv`, với đường dẫn logic `demo/payment` và các trường `endpoint`, `timeoutSeconds`. Viết mã dùng `VaultKeyValueOperations.get(...)` để đọc và kiểm tra hai trường này. Thử xóa `endpoint` rồi quan sát cách hàm kiểm tra dữ liệu phản ứng. Không chèn token Vault hoặc secret thật vào mã nguồn hay log.

### Bài tập 2 — Đọc secret có kiểu từ KV v2

Tạo KV v2 tại mount thử nghiệm `training-secret` và lưu cùng cấu trúc. Định nghĩa `PaymentSecret` phù hợp schema, rồi dùng `get("demo/payment", PaymentSecret.class)`. So sánh hai cách truy cập `response.getData()` của `VaultResponse` và `VaultResponseSupport<PaymentSecret>`. Thử ghi sai kiểu `timeoutSeconds` để quan sát lỗi ánh xạ hoặc validation.

### Bài tập 3 — Nhận diện lớp dữ liệu

Cho phản hồi KV v2 rút gọn:

```json
{
  "request_id": "req-42",
  "data": {
    "data": {
      "username": "app-user",
      "password": "<gia-tri-bi-mat>"
    },
    "metadata": { "version": 7 }
  }
}
```

Hãy chỉ ra:

1. Những trường nào là dữ liệu nghiệp vụ cần ánh xạ vào `DatabaseCredentials`?
2. Nếu đọc bằng `vaultOperations.read("training-secret/data/demo/db")`, muốn lấy `username` phải đi qua những cấp `data` nào?
3. Nếu đọc bằng `opsForKeyValue("training-secret", KV_2).get("demo/db", DatabaseCredentials.class)`, `getData()` trả về kiểu gì?
4. Có thể khẳng định `lease_duration == 0` nghĩa là giá trị KV không cần rotation không?

**Đáp án định hướng:** (1) `username`, `password`; (2) phần `data` của phản hồi rồi tiếp tục khóa `data` chứa secret KV v2; (3) `DatabaseCredentials`, khi ánh xạ thành công và dữ liệu có mặt; (4) không, rotation là chính sách quản lý secrets riêng, không suy từ thời lượng lease của phản hồi.

## 9. Những điểm cần ghi nhớ

- `VaultResponseSupport<T>` biểu diễn phản hồi Vault với phần dữ liệu kiểu `T`; `VaultResponse` là trường hợp dữ liệu kiểu `Map<String, Object>`.
- `getData()` có thể trả `null`; `getRequiredData()` ném `IllegalStateException` khi **data** không có, nhưng không xử lý việc biến `response` là `null`.
- Dữ liệu nghiệp vụ được lấy từ phần `data` đã xác định đúng cấp; thông tin lease, auth, warnings và request ID là thông tin bao ngoài với mục đích khác nhau.
- KV v2 có thêm lớp `data` khi gọi endpoint trực tiếp. `VaultKeyValueOperations` giúp ứng dụng truy cập dữ liệu theo đường dẫn logic và giảm việc tự bóc cấu trúc JSON.
- Ánh xạ có kiểu làm rõ hợp đồng dữ liệu, nhưng vẫn phải kiểm tra trường bắt buộc, lỗi quyền truy cập và tránh làm lộ secrets qua log.

## Tài liệu đối chiếu

- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): kiểu dữ liệu, metadata, lease và các accessor như `getData()`/`getRequiredData()`.
- [Spring Vault — `VaultResponse` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponse.html): quan hệ kế thừa `VaultResponseSupport<Map<String, Object>>`.
- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultKeyValueOperations.html): các overload `get(String)` và `get(String, Class<T>)`.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): phân biệt KV v1, KV v2, API có phiên bản và cách đọc KV trực tiếp.

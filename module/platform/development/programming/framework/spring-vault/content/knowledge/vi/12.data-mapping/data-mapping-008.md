# Biểu diễn byte, chuỗi và Base64 theo từng endpoint

## Mục tiêu bài học

Khi ứng dụng Java giao tiếp HashiCorp Vault qua **Spring Vault**, một giá trị có thể trải qua nhiều dạng biểu diễn: **byte** trong bộ nhớ, **chuỗi** theo một charset như UTF-8, **Base64** để đưa byte vào JSON, hoặc **PEM** để truyền chứng chỉ. Cùng một kiểu Java `String` nhưng ý nghĩa của dữ liệu lại khác nhau tùy endpoint: `plaintext` của Transit là chuỗi Base64, `ciphertext` của Transit là chuỗi opaque do Vault định nghĩa, còn `certificate` của PKI thường là văn bản PEM.

Nhầm lẫn các biểu diễn dẫn đến lỗi thật: dữ liệu mã hóa hai lần, ký sai byte, giải mã bằng charset mặc định của máy, cố Base64-decode ciphertext Transit, hoặc làm rò rỉ private key trong log.

Bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**, tập trung vào cách Java sử dụng `VaultTemplate`/`VaultOperations` để trao đổi dữ liệu với các endpoint Vault. Sau bài học, bạn có thể:

1. Phân biệt byte thô, chuỗi Unicode, biểu diễn UTF-8, chuỗi Base64 và ciphertext.
2. Chọn đúng cách encode/decode theo hợp đồng của **KV**, **Transit**, **PKI** và một số endpoint hệ thống.
3. Sử dụng `StandardCharsets.UTF_8`, `Base64` của Java và kiểm tra dữ liệu đầu vào mà không phụ thuộc charset máy.
4. Đọc `VaultResponse`/`Map<String, Object>` với kiểm tra kiểu thay vì ép nhầm `String` thành `byte[]`.
5. Hiểu vì sao PEM chứa Base64 nhưng không nên Base64-decode toàn bộ văn bản chứng chỉ.
6. Thiết kế kiểm thử round-trip, trường hợp Unicode/binary lỗi, kiểm thử tích hợp và quy tắc không ghi secrets vào log.

> **Bối cảnh:** Ứng dụng đã được cấu hình kết nối Vault và xác thực theo workload phù hợp với Vault policy. Phần mã dùng dữ liệu giả. Spring Vault còn hỗ trợ các chủ đề như KV secrets, token/lease lifecycle, Transit encryption, PKI, xử lý lỗi, quan sát và kiểm thử tích hợp; bài này chỉ giải thích **biểu diễn dữ liệu** trong các luồng đó. Việc encode thành Base64 không thay thế TLS, policy hay cơ chế quản lý secrets.

## 1. Bốn khái niệm phải tách bạch

Giả sử cần bảo vệ thông điệp `"hello"`. Trong Java, chuỗi, byte và Base64 là những thứ khác nhau:

```text
Chuỗi Java:                  "hello"
        │ getBytes(UTF_8)
        ▼
Byte UTF-8:                  68 65 6c 6c 6f (hex)
        │ Base64 encode
        ▼
Văn bản Base64:              "aGVsbG8="
        │ đưa vào JSON (theo hợp đồng endpoint)
        ▼
JSON string:                 {"plaintext": "aGVsbG8="}
        │ Vault Transit encrypt
        ▼
Ciphertext Vault:            "vault:v1:..." (ví dụ định dạng, không phải giá trị thật)
```

Chuỗi `"aGVsbG8="` có thể đảo lại thành byte `hello` mà không cần khóa. Ngược lại, ciphertext Transit cần khóa và quyền thực hiện thao tác giải mã của Vault.

| Khái niệm | Bản chất | Ví dụ | Có bảo mật tự thân? |
|---|---|---|---|
| `byte[]` | Dãy byte nhị phân | `[0x68, 0x65, 0x6C, 0x6C, 0x6F]` | Không |
| `String` | Chuỗi ký tự trong Java | `"hello"`, `"Xin chào"` | Không |
| UTF-8 | Quy tắc mã hóa ký tự thành byte | `"hello" → 68 65 6c 6c 6f` | Không |
| Base64 | Quy tắc biểu diễn byte bằng ký tự ASCII | `68 65 6c 6c 6f → aGVsbG8=` | Không |
| Mã hóa bí mật | Phép biến đổi cần khóa và thuật toán | Ciphertext Vault Transit | Bảo vệ tính bí mật theo thiết kế mật mã |
| PEM | Văn bản có header/footer, thường bao Base64 của DER | `-----BEGIN CERTIFICATE-----` | Không mặc nhiên bảo mật |

**Base64 không phải encryption.** Không đưa một password vào Base64 rồi coi là đã bảo vệ password; bất kỳ bên nào đọc được giá trị Base64 đều có thể giải mã ra byte gốc.

### 1.1. “String” không cho biết nội dung có phải text

Một API có thể trả `String` chứa:

- Văn bản UTF-8 bình thường: hostname, username, tên role.
- Base64 của bytes: `plaintext` do Transit decrypt trả về.
- Ciphertext dạng opaque: `"vault:vN:..."`.
- PEM có dòng BEGIN/END và các ký tự Base64 ở giữa.
- Token hoặc lease ID được coi là chuỗi opaque, không được tự giải mã Base64.

**Quy tắc đúng là đọc tài liệu của từng endpoint và field**, không suy ra phép chuyển đổi chỉ từ kiểu Java `String`.

### 1.2. JSON có kiểu string, không có byte array chuẩn

JSON định nghĩa string, number, boolean, null, object và array; nó không có primitive `binary`. Nếu phải đưa byte vào JSON, API thường chọn một biểu diễn **chuỗi** như Base64 hoặc hex. Một số mapper có thể tự serialize `byte[]` thành Base64, nhưng đây là hành vi của bộ chuyển đổi, không phải hợp đồng chung cho mọi endpoint Vault.

## 2. Bảng tra nhanh theo endpoint

| Endpoint/nhóm API | Trường thường gặp | Kiểu trên wire | Cách hiểu ở Java |
|---|---|---|---|
| KV v2 `secret/data/:path` | `data.data.api_key` | JSON string thông thường | `String`; không tự decode Base64 |
| KV v2 lưu binary theo quy ước ứng dụng | `data.data.blob_base64` | JSON string Base64 do **bên ghi quy định** | `String → Base64.getDecoder() → byte[]` |
| Transit `transit/encrypt/:key` | Request `plaintext` | **Base64 của plaintext bytes** | UTF-8 encode (nếu là text), rồi Base64 encode |
| Transit `transit/encrypt/:key` | Response `ciphertext` | Chuỗi ciphertext Vault, thường có tiền tố `vault:v...` | Giữ nguyên `String`, không decode Base64 toàn chuỗi |
| Transit `transit/decrypt/:key` | Request `ciphertext` | Chuỗi ciphertext Vault | Gửi nguyên chuỗi được trả về lúc encrypt |
| Transit `transit/decrypt/:key` | Response `plaintext` | **Base64 của plaintext bytes** | Base64 decode thành byte, chỉ tạo `String` nếu xác định đó là text |
| Transit dùng key dẫn xuất | Field `context` | Base64 của context bytes | Encode đúng byte context; cách bắt buộc phụ thuộc cấu hình key |
| PKI `pki/issue/:role` | `certificate`, `issuing_ca` | Thường là văn bản PEM | Giữ nguyên PEM String hoặc parse bằng API X.509 |
| PKI cấp private key qua issue | `private_key` (khi endpoint tạo/trả khóa) | Văn bản khóa, thường PEM | Xử lý như dữ liệu cực kỳ nhạy cảm, không log |
| PKI response chain | `ca_chain` | JSON array chứa certificate PEM | `List<?>`, kiểm tra từng phần tử `String` |
| Hệ thống `sys/tools/random` | `random_bytes` | Chuỗi theo `format` request/endpoint, ví dụ Base64 hoặc hex | Decode theo format đã yêu cầu |
| Auth/Token | `client_token`, `lease_id` | Opaque string | Giữ nguyên, không đoán là Base64 |

Các đường dẫn trên là ví dụ với mount mặc định/thường dùng. Mount Transit, PKI hay KV có thể được đặt tên khác; chính sách Vault phải cho phép chính xác thao tác và path thực tế.

**Điểm cần nhớ:** `plaintext` không có cùng biểu diễn ở mọi bước, và `ciphertext` không đồng nghĩa với chuỗi Base64 của plaintext. Hãy theo hợp đồng field của endpoint.

## 3. Chuyển `String` và `byte[]` bằng UTF-8 trong Java

Khi plaintext là văn bản, cần chọn charset để biến ký tự thành byte. Dùng `UTF-8` tường minh thay vì `getBytes()` không tham số hoặc `new String(bytes)` không chỉ định charset:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String message = "Xin chào Vault!";
byte[] utf8Bytes = message.getBytes(StandardCharsets.UTF_8);

String roundTrip = new String(
        utf8Bytes,
        StandardCharsets.UTF_8);

System.out.println(message.equals(roundTrip)); // true

// Chỉ xóa bản sao byte sau khi không còn sử dụng.
Arrays.fill(utf8Bytes, (byte) 0);
```

Với ký tự ngoài ASCII như `"à"`, một ký tự có thể chiếm nhiều byte UTF-8. Vì vậy `String.length()` không đại diện cho số byte mà endpoint nhận được. Khi áp dụng giới hạn `N bytes`, hãy kiểm tra kích thước sau khi encode UTF-8 chứ không chỉ đếm ký tự Java.

### 3.1. Byte không phải text thì không nên ép thành String

Một file DER, khóa nhị phân, số ngẫu nhiên hoặc giá trị giải mã từ Transit có thể chứa các byte không phải UTF-8 hợp lệ. Nếu dùng:

```java
String maybeText = new String(
        binaryPayload,
        StandardCharsets.UTF_8);
```

Java có thể thay những byte UTF-8 sai bằng ký tự thay thế. Chuyển ngược lại từ `String` có thể **không** khôi phục byte ban đầu. Đừng lấy byte tùy ý rồi “đổi sang String cho tiện”.

Khi yêu cầu nghiêm ngặt là *dữ liệu phải là UTF-8 hợp lệ*, dùng decoder báo lỗi:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {

    return StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Nếu `decodeUtf8Strict(...)` thất bại, đầu vào không được chấp nhận như văn bản UTF-8 theo hợp đồng này. Không tự thay bằng charset của máy hoặc `ISO-8859-1` để lẩn tránh lỗi trừ khi endpoint thực sự quy định mã hóa đó.

### 3.2. String chứa secrets tồn tại trong bộ nhớ

`String` của Java là đối tượng bất biến; ứng dụng không thể bảo đảm xóa sạch nội dung của nó theo ý muốn. `byte[]` có thể được ghi đè bằng `Arrays.fill` sau sử dụng, nhưng cũng không đảm bảo mọi bản sao bên trong thư viện/heap đã bị xóa. Vì vậy:

- Giữ plaintext trong bộ nhớ ngắn nhất có thể và không tạo nhiều bản sao không cần thiết.
- Không đưa String/byte chứa secret vào log, exception message hoặc trace.
- Tránh dùng `toString()` tự sinh trên DTO/record có password hoặc API key.
- Chỉ dùng byte thay vì String khi API và nhu cầu xử lý cho phép; JSON Base64 vẫn tạo ra biểu diễn text ở biên giao tiếp.

## 4. Base64 chuẩn của Java: encode và decode

Java cung cấp `java.util.Base64`. Với Vault Transit, biểu diễn field `plaintext` theo yêu cầu Base64 thông thường nên dùng **basic Base64** của Java:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String input = "hello";
byte[] source = input.getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(source);
System.out.println(encoded); // "aGVsbG8="

byte[] decoded = Base64.getDecoder().decode(encoded);
String restored = new String(decoded, StandardCharsets.UTF_8);
System.out.println(restored.equals(input)); // true
```

`Base64.getEncoder()` dùng bảng ký tự Base64 cơ bản; `getDecoder()` là decoder tương ứng. `encodeToString` tạo ra chuỗi ASCII hợp lệ để đặt trong trường JSON mà endpoint yêu cầu.

### 4.1. Base64 basic, URL-safe và MIME khác nhau

| Biến thể Java | Chữ ký | Khi nào phù hợp |
|---|---|---|
| Basic | `Base64.getEncoder()/getDecoder()` | Các JSON field yêu cầu Base64 tiêu chuẩn, như Transit `plaintext` |
| URL-safe | `Base64.getUrlEncoder()/getUrlDecoder()` | Khi API cụ thể quy định Base64URL, dùng ký tự `-` và `_` |
| MIME | `Base64.getMimeEncoder()/getMimeDecoder()` | Dữ liệu theo định dạng MIME có thể có xuống dòng |

Không tự thay basic bằng URL-safe hoặc MIME “cho đẹp URL”: cùng dãy byte có thể cho chuỗi khác ở các ký tự `+`, `/`, `-`, `_`. Vault Transit yêu cầu Base64 cho nội dung, không phải tùy ý Base64URL. Nếu tài liệu của một endpoint cho phép format riêng, làm đúng format được ghi trong request và response.

**Padding:** Base64 chuẩn thường có `=` ở cuối để đệm đến độ dài chia hết cho bốn, ví dụ `"aGVsbG8="`. Một số decoder chấp nhận dữ liệu bỏ padding; nếu giao thức yêu cầu dạng chuẩn/canonical, hãy xác nhận cả biểu diễn chứ không chỉ decode được.

### 4.2. Base64 làm dữ liệu dài hơn

Với `n` byte, chuỗi Base64 có padding thường dài `4 × ceil(n / 3)` ký tự. Ví dụ:

- 3 byte → 4 ký tự Base64.
- 5 byte (`"hello"`) → 8 ký tự.
- 1.024 byte → 1.368 ký tự.

Độ dài Base64 lớn hơn dữ liệu gốc khoảng một phần ba trước khi tính overhead JSON. Khi lưu/tải khối binary lớn, cần xem giới hạn kích thước request, giới hạn ứng dụng và giải pháp lưu trữ phù hợp; Vault KV không phải dịch vụ lưu file lớn.

### 4.3. Không echo dữ liệu Base64 khi lỗi

`Base64.getDecoder().decode(...)` có thể ném `IllegalArgumentException` nếu chuỗi không đúng format. Với secrets, không đưa chuỗi đầu vào vào thông báo lỗi:

```java
import java.util.Arrays;
import java.util.Base64;

static byte[] decodeRequiredBase64(
        Object value, String field, int maxBytes) {

    if (!(value instanceof String encoded) || encoded.isBlank()) {
        throw new IllegalArgumentException(
                field + " phải là chuỗi Base64 không rỗng");
    }
    if (maxBytes <= 0) {
        throw new IllegalArgumentException("Giới hạn byte không hợp lệ");
    }

    // Giới hạn sớm để tránh allocate quá nhiều bộ nhớ cho input lớn.
    if (encoded.length() > 4L * ((maxBytes + 2L) / 3L) + 4L) {
        throw new IllegalArgumentException(
                field + " vượt giới hạn kích thước");
    }

    byte[] decoded;
    try {
        decoded = Base64.getDecoder().decode(encoded);
    } catch (IllegalArgumentException invalidBase64) {
        throw new IllegalArgumentException(
                field + " không phải Base64 hợp lệ");
    }

    if (decoded.length > maxBytes) {
        Arrays.fill(decoded, (byte) 0);
        throw new IllegalArgumentException(
                field + " vượt giới hạn sau giải mã");
    }
    return decoded;
}
```

Helper minh họa giới hạn kích thước và bảo vệ nội dung lỗi; giá trị `maxBytes` nên xuất phát từ hợp đồng và giới hạn tài nguyên của hệ thống. Nó không thực hiện encryption hay xác minh tính xác thực dữ liệu. Nếu cần Base64 canonical, có thể kiểm tra chuỗi mã hóa lại bằng encoder tương ứng theo chính sách đã chọn.

## 5. KV v2: JSON value không tự là Base64

KV v2 lưu một object JSON; secret có thể chứa string, number, boolean, object lồng nhau và array. Ví dụ:

```json
{
  "data": {
    "api_token": "<gia-tri-bi-mat>",
    "enabled": true,
    "retry_count": 3,
    "endpoint": "https://internal.example"
  }
}
```

Đây là phần **request body** minh họa khi ghi KV v2 qua endpoint HTTP `secret/data/services/billing`. Các trường `api_token` và `endpoint` là **text bình thường**. Việc response được truyền bằng JSON qua HTTPS không có nghĩa chúng đã được Base64 encode.

### 5.1. Đọc dữ liệu KV bằng Spring Vault

```java
import java.util.Map;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponse response = kv.get("services/billing");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("Không tìm thấy billing secret");
}

Map<String, Object> data = response.getRequiredData();
Object tokenValue = data.get("api_token");
if (!(tokenValue instanceof String token) || token.isBlank()) {
    throw new IllegalArgumentException("api_token không hợp lệ");
}

// Dùng token trong thành phần thực sự cần; không log token hoặc data.
```

Với API KV mức cao, `getData()` ở ví dụ này trỏ đến **dữ liệu nghiệp vụ**; khi đọc trực tiếp endpoint `vaultOperations.read("secret/data/services/billing")`, phản hồi KV v2 có thêm object `data` chứa `data` và `metadata`. Đừng nhầm lớp bọc JSON với quy tắc Base64 của một field.

**Không giải mã `api_token` bằng Base64 theo phỏng đoán.** Token phải được xử lý theo hợp đồng của hệ thống phát hành nó. Một chuỗi có các ký tự hợp lệ cho Base64 không chứng minh nó được cố ý mã hóa theo Base64.

### 5.2. Khi cần lưu dữ liệu binary vào KV

Giả sử ứng dụng quyết định lưu một blob nhị phân nhỏ dưới dạng Base64. Đây là **hợp đồng do ứng dụng đặt ra**, không phải tự động cho mọi field KV:

```json
{
  "blob_base64": "AAECAwQ=",
  "content_type": "application/octet-stream",
  "encoding": "base64"
}
```

`"AAECAwQ="` là Base64 của năm byte `00 01 02 03 04`, không phải một ciphertext. Quy tắc giải mã:

```java
Map<String, Object> data = response.getRequiredData();

if (!"base64".equals(data.get("encoding"))) {
    throw new IllegalArgumentException("encoding không được hỗ trợ");
}

byte[] blob = decodeRequiredBase64(
        data.get("blob_base64"),
        "blob_base64",
        64 * 1024);

try {
    // Chuyển byte đến consumer được phép dùng binary.
    // Không ép blob thành String khi không có hợp đồng charset.
} finally {
    java.util.Arrays.fill(blob, (byte) 0);
}
```

Các đoạn code dùng cùng biến `response` để minh họa luồng đọc; trong ứng dụng thật hãy dùng response từ **path chứa blob**, không dùng response từ `services/billing` nếu schema của nó không có `blob_base64`. Mỗi path cần schema và giới hạn dữ liệu cụ thể.

Nếu DTO có thuộc tính `byte[]`, một số bộ chuyển đổi JSON (ví dụ Jackson mặc định trong nhiều cấu hình) có thể ánh xạ một chuỗi Base64 thành byte array. Nhưng kết quả đó **phụ thuộc converter được cấu hình**, không làm cho mọi `String` trong KV tự thành byte[] và không thay thế kiểm tra encoding hoặc kích thước.

## 6. Transit encrypt: request `plaintext` là Base64, response `ciphertext` là opaque

Transit secrets engine cho phép ứng dụng yêu cầu Vault mã hóa dữ liệu bằng khóa do Vault quản lý, thay vì tải khóa mã hóa về ứng dụng. Với endpoint HTTP:

```text
POST /v1/transit/encrypt/:name
```

Trường `plaintext` trong request là **Base64 của plaintext bytes**. Ví dụ mã hóa năm byte `hello`:

```json
{
  "plaintext": "aGVsbG8="
}
```

Phản hồi rút gọn:

```json
{
  "data": {
    "ciphertext": "vault:v1:..."
  }
}
```

Giá trị `vault:v1:...` chỉ minh họa cấu trúc **ciphertext được Vault tạo ra**, không phải ciphertext thật có thể giải mã. Phần `v1` trong ciphertext là thông tin phiên bản khóa/định dạng của Transit, **không phải** storage version KV v2 và cũng không phải JSON schema version.

### 6.1. Quy trình từng bước

```text
Ứng dụng Java
    │
    ├─ Nội dung dạng String (nếu thực sự là text)
    │      └─ getBytes(UTF_8)
    │              ▼
    │           byte[]
    │              └─ Base64.getEncoder().encodeToString(...)
    │                      ▼
    └──── request {"plaintext":"...base64..."}
                             │
                             ▼
                    Vault Transit encrypt
                             │
                             ▼
                    {"ciphertext":"vault:vN:..."}
                             │
                             ▼
                       Opaque String
```

Không thực hiện `Base64.getDecoder().decode(ciphertext)`. Nếu cần giải mã, gửi **nguyên chuỗi** đó tới endpoint Transit decrypt với đúng khóa và ngữ cảnh (nếu có).

### 6.2. Ví dụ Java gọi Transit qua `VaultOperations.write(...)`

Đoạn mã dùng endpoint HTTP thông qua `VaultOperations` để cho thấy rõ hợp đồng JSON của Transit. Giả sử Transit được mount tại `transit`, đã có khóa `orders-key` và workload có quyền encrypt:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

static String encryptText(
        VaultOperations vault,
        String text) {

    byte[] clearBytes = text.getBytes(StandardCharsets.UTF_8);
    String plaintextBase64 =
            Base64.getEncoder().encodeToString(clearBytes);

    VaultResponse response = vault.write(
            "transit/encrypt/orders-key",
            Map.of("plaintext", plaintextBase64));

    return requireStringData(response, "ciphertext");
}

static String requireStringData(
        VaultResponse response, String field) {
    if (response == null || response.getData() == null) {
        throw new IllegalStateException("Vault không trả dữ liệu");
    }
    Object value = response.getRequiredData().get(field);
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalStateException(
                "Vault không trả trường " + field + " hợp lệ");
    }
    return text;
}
```

Ví dụ mang tính giáo dục; nếu `text` chứa secret, việc tạo `String` và chuỗi Base64 có thể để lại bản sao trong bộ nhớ. Trong ứng dụng cần kiểm soát chặt bí mật, API dạng byte và vòng đời dữ liệu nên được thiết kế riêng. Tuyệt đối không log `text`, `plaintextBase64`, response hoặc payload.

Spring Vault cũng có API cấp cao dành cho Transit qua `VaultOperations.opsForTransit()`; overload và cách biểu diễn dữ liệu có thể phụ thuộc phiên bản Spring Vault. Bài này dùng đường `VaultOperations.write` để giải thích rõ yêu cầu field của Vault HTTP API, không mặc định mọi overload cấp cao đều nhận plaintext/Base64 theo cùng kiểu.

### 6.3. Lưu ý với `context`

Một số Transit key được cấu hình để dẫn xuất khóa theo context. Khi endpoint yêu cầu field `context`, giá trị này cũng là **Base64 của context bytes**:

```java
String contextBase64 = Base64.getEncoder().encodeToString(
        "tenant-example".getBytes(StandardCharsets.UTF_8));

Map<String, Object> body = Map.of(
        "plaintext", plaintextBase64,
        "context", contextBase64);
```

Đoạn trên chỉ minh họa cách tạo hai giá trị chuỗi và giả định `plaintextBase64` đã được tạo. **Đừng coi context là mật khẩu thay cho khóa**, hoặc tự thêm context ngẫu nhiên rồi giả định giải mã vẫn hoạt động. Các thao tác encrypt/decrypt phải đáp ứng đúng yêu cầu về context của key được cấu hình.

## 7. Transit decrypt: trả byte gốc qua field Base64

Để giải mã, ứng dụng gửi **chuỗi ciphertext Vault** tới:

```text
POST /v1/transit/decrypt/:name
```

Request:

```json
{
  "ciphertext": "vault:v1:..."
}
```

Khi giải mã thành công, response có trường `plaintext` là **Base64 của byte ban đầu**:

```json
{
  "data": {
    "plaintext": "aGVsbG8="
  }
}
```

Do đó luồng Java chính xác là:

```text
Opaque Vault ciphertext
        │ gửi nguyên String đến Transit decrypt
        ▼
response.data.plaintext (Base64 String)
        │ Base64.getDecoder().decode(...)
        ▼
byte[] clearBytes
        ├── Nếu byte là UTF-8 text → strict decode → String
        └── Nếu byte là binary    → giữ byte[], không tự chuyển String
```

### 7.1. Ví dụ Java nhận dữ liệu giải mã

```java
import java.util.Base64;
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

static byte[] decryptBytes(
        VaultOperations vault,
        String ciphertext) {

    if (ciphertext == null || ciphertext.isBlank()) {
        throw new IllegalArgumentException(
                "Thiếu ciphertext");
    }

    VaultResponse response = vault.write(
            "transit/decrypt/orders-key",
            Map.of("ciphertext", ciphertext));

    String encodedPlaintext =
            requireStringData(response, "plaintext");

    return decodeRequiredBase64(
            encodedPlaintext,
            "plaintext",
            64 * 1024);
}
```

`requireStringData` và `decodeRequiredBase64` là các helper đã được giới thiệu ở mục trước. Với key có context bắt buộc, request decrypt cần đúng context (và các tham số liên quan) như khi encrypt. Nếu không, Vault có thể từ chối giải mã hoặc trả lỗi xác thực dữ liệu theo cấu hình key.

Ví dụ sử dụng trong bài thực hành:

```java
String ciphertext = encryptText(vaultOperations, "hello");
byte[] clear = decryptBytes(vaultOperations, ciphertext);

try {
    String restored = decodeUtf8Strict(clear);
    System.out.println("Khôi phục đúng: " + restored.equals("hello"));
} finally {
    java.util.Arrays.fill(clear, (byte) 0);
}
```

**Chỉ dùng dữ liệu giả như `"hello"` trong log/test.** Với plaintext thật, không in ra chuỗi đã giải mã. `decodeUtf8Strict` trong ví dụ có thể ném `CharacterCodingException`; phương thức gọi phải khai báo hoặc xử lý checked exception này.

### 7.2. Những field Transit khác dễ gây nhầm

| Trường/endpoint Transit | Biểu diễn thông dụng | Sai lầm cần tránh |
|---|---|---|
| `plaintext` trong encrypt | Base64 bytes | Gửi trực tiếp `"hello"` mà không Base64 encode |
| `ciphertext` trong encrypt/decrypt | Opaque `vault:vN:...` string | Cố decode toàn chuỗi như Base64 |
| `plaintext` trả về từ decrypt | Base64 bytes | Dùng nguyên chuỗi `"aGVsbG8="` như văn bản người dùng |
| `context` | Base64 bytes | Đưa text thô hoặc thay context giữa hai lượt |
| `transit/rewrap/:name` request `ciphertext` | Opaque Vault ciphertext | Decode plaintext về ứng dụng trước khi rewrap một cách không cần thiết |
| `transit/sign/:name` request `input` | Base64 bytes theo hợp đồng endpoint | Nhầm “bytes cần ký” với biểu diễn String đã đổi charset |
| `transit/verify/:name` | Input/signature theo hợp đồng riêng của verify | Coi signature `vault:vN:...` là cùng kiểu với plaintext Base64 |

Với sign, verify, HMAC hay key derivation, cần kiểm tra thêm trường `hash_algorithm`, `prehashed`, `context` và các tùy chọn key tương ứng; không tự áp dụng một quy tắc duy nhất cho mọi field chỉ vì cùng thuộc Transit. Luồng ở đây tập trung vào encrypt/decrypt.

## 8. PKI: chứng chỉ PEM là text có Base64 bên trong

PKI secrets engine cấp và quản lý chứng chỉ. Khi gọi endpoint cấp chứng chỉ, ví dụ:

```text
POST /v1/pki/issue/:role
```

response thường có các field như `certificate`, `issuing_ca`, `ca_chain`, `serial_number`, và trong trường hợp Vault tạo key, có thể có `private_key`.

Một chuỗi PEM có hình thức:

```text
-----BEGIN CERTIFICATE-----
MIIB... (nội dung Base64 minh họa, không phải chứng chỉ hợp lệ)
-----END CERTIFICATE-----
```

**PEM không phải chuỗi Base64 thuần.** Nó có header/footer, newline và phần Base64 mã hóa **DER bytes** ở giữa. Vì vậy không làm:

```java
// SAI: toàn bộ PEM không phải input hợp lệ cho basic Base64 decoder.
// byte[] certificate = Base64.getDecoder().decode(pemText);
```

Hai cách xử lý thông dụng:

1. Giữ nguyên **PEM String** khi consumer thực sự chấp nhận PEM, ví dụ một phần cấu hình TLS.
2. Parse PEM bằng API X.509 trong Java hoặc thư viện PKI phù hợp để thu được `X509Certificate` và kiểm tra thuộc tính/chứng chỉ.

### 8.1. Đọc PEM certificate bằng Java

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.cert.Certificate;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

static X509Certificate parseCertificatePem(String pem)
        throws CertificateException {

    if (pem == null || pem.isBlank()) {
        throw new IllegalArgumentException(
                "certificate phải là PEM không rỗng");
    }

    byte[] encodedText = pem.getBytes(StandardCharsets.US_ASCII);
    ByteArrayInputStream input =
            new ByteArrayInputStream(encodedText);

    Certificate certificate = CertificateFactory
            .getInstance("X.509")
            .generateCertificate(input);

    return (X509Certificate) certificate;
}
```

`CertificateFactory` với `X.509` hỗ trợ đọc chứng chỉ ở dạng mã hóa X.509 phù hợp; nó không tự tạo trust hay xác nhận rằng chứng chỉ được CA mong muốn tin cậy. Kiểm tra chain, hostname/SAN, thời hạn, EKU/key usage, thu hồi và trust anchor tùy kịch bản TLS. Với dữ liệu PEM nhiều chứng chỉ, cần parse theo cấu trúc tương ứng thay vì đọc mỗi chứng chỉ đầu tiên rồi cho rằng đã có chain đầy đủ.

### 8.2. Lấy chứng chỉ từ phản hồi PKI

Ví dụ qua `VaultOperations.write`, giả sử role `service-cert` và policy phù hợp:

```java
import java.util.Map;
import org.springframework.vault.support.VaultResponse;

VaultResponse issued = vaultOperations.write(
        "pki/issue/service-cert",
        Map.of(
                "common_name", "billing.internal.example",
                "ttl", "1h"));

String pem = requireStringData(issued, "certificate");
X509Certificate certificate = parseCertificatePem(pem);

// Có thể đọc certificate.getNotAfter() để quan sát hạn chứng chỉ.
// Không log toàn bộ response; có thể có private_key nhạy cảm.
```

Đoạn này là ví dụ API mức thấp; Spring Vault cũng có API PKI cấp cao phù hợp với một số nghiệp vụ. Endpoint issue có thể trả private key nếu tạo key server-side; tùy cách cấp chứng chỉ/CSR, nội dung response có thể khác. **Không xem `private_key` là metadata an toàn để log** và không nhét nó vào một DTO dùng để ghi trace chung.

### 8.3. DER, PEM và private key

| Dạng | Biểu diễn | Cách xử lý đúng |
|---|---|---|
| DER certificate | Byte nhị phân theo ASN.1 DER | Đưa bytes vào `CertificateFactory` hoặc thư viện phù hợp |
| PEM certificate | Văn bản BEGIN/END + Base64 DER | Giữ nguyên PEM hoặc dùng parser nhận PEM |
| PEM private key | Văn bản BEGIN/END của key, có thể có cấu trúc/định dạng khác nhau | Chỉ parse với công cụ/định dạng khóa đúng, giới hạn truy cập |
| `ca_chain` trong JSON PKI | Thường là mảng PEM certificate | Kiểm tra `List<?>` rồi từng `String`; không coi là một blob Base64 |
| `serial_number` | Chuỗi định danh serial theo API | Không tự Base64-decode |

Một số endpoint PKI trả **raw PEM body** thay vì JSON, ví dụ URL chứa `/pem` theo API cụ thể. `VaultOperations.read(...)` dành cho mô hình phản hồi JSON không phải lúc nào cũng phù hợp để đọc một body PEM thuần. Hãy chọn HTTP client/response body type đúng với endpoint đó; không giả định mọi URL dưới mount `pki` đều trả `VaultResponse` có `data` map.

## 9. Các endpoint khác: format theo request, không theo “cảm giác”

Vault có các endpoint hệ thống hỗ trợ tạo dữ liệu ngẫu nhiên hoặc thao tác encoding với format được khai báo trong request. Ví dụ nhóm `sys/tools/random` có thể trả `random_bytes` theo format như Base64 hoặc hex.

Giả sử API response cung cấp:

```json
{
  "data": {
    "random_bytes": "AAECAwQ="
  }
}
```

Nếu **đã yêu cầu Base64**, có thể decode bằng `Base64.getDecoder()`. Nếu format là hex, chuỗi phải được giải mã theo **hex**, không phải Base64. Nếu endpoint trả raw body, cần đọc body dưới dạng bytes hoặc text theo content type tương ứng.

Đừng áp dụng `Base64.getDecoder()` chỉ vì response chứa một `String` “trông giống Base64”. Với token và lease ID, giá trị có thể là opaque token hoặc identifier; mọi cố gắng “giải mã” không được endpoint quy định có thể làm hỏng dữ liệu.

## 10. Khi nào dùng `String`, `byte[]`, DTO và Map?

| Trường hợp | Kiểu Java gợi ý | Ghi chú |
|---|---|---|
| KV field hostname | `String` | Không decode Base64 |
| KV field binary theo quy ước `blob_base64` | `String` ở DTO wire; `byte[]` sau decode | Kiểm tra kích thước và format trước khi sử dụng |
| Plaintext trước Transit encrypt | `byte[]` nếu dữ liệu nhị phân; `String` nếu là text | Nếu là text, chỉ định UTF-8 trước khi Base64 |
| Transit ciphertext | `String` | Chuỗi opaque; không Base64-decode toàn chuỗi |
| Transit decrypt plaintext response | `String` Base64 tại ranh giới wire → `byte[]` | Chỉ chuyển thành text nếu chắc chắn dữ liệu là UTF-8 |
| PKI certificate PEM | `String` hoặc `X509Certificate` | Parse PEM; không coi toàn chuỗi là Base64 |
| PKI private key | Kiểu key riêng hoặc biểu diễn bảo mật của thư viện | Giới hạn truy cập, tránh log, quản lý vòng đời |
| Các field cùng schema trong một phản hồi | DTO có kiểu | Cần validator, không chỉ dựa vào JSON mapping |
| Field động chưa rõ kiểu | `Map<String, Object>` | Kiểm tra runtime bằng `instanceof` |

### 10.1. Không ép `String` thành `byte[]` qua cast

Trong response `VaultResponse` chưa định kiểu, JSON string thường được deserialize thành Java `String`. Đoạn sau sai:

```java
// Sai: String và byte[] là hai kiểu Java khác nhau.
// byte[] value = (byte[]) data.get("blob_base64");
```

Phải xác định field là text hay encoded binary:

```java
Object raw = data.get("blob_base64");
byte[] bytes = decodeRequiredBase64(
        raw,
        "blob_base64",
        64 * 1024);
```

Và không lẫn **decode Base64** với **decode UTF-8**: Base64 trả ra bytes, còn UTF-8 decoder trả ra ký tự từ bytes.

### 10.2. Tránh tự động double-encode hoặc double-decode

Giả sử nguồn `String` đã chứa Base64 của bytes:

```java
String alreadyEncoded = "aGVsbG8=";
String wrong = Base64.getEncoder().encodeToString(
        alreadyEncoded.getBytes(StandardCharsets.UTF_8));
```

`wrong` là Base64 của chữ `"aGVsbG8="`, **không phải** Base64 của bytes `hello`. Transit decrypt một giá trị đã bị double-encode sẽ trả về bytes của chuỗi Base64 trung gian, dẫn đến dữ liệu bị lệch.

Một nguyên tắc thiết kế hữu ích: đặt tên biến theo **nội dung + biểu diễn**, ví dụ `plaintextBytes`, `plaintextBase64`, `vaultCiphertext`, `certificatePem`, `derBytes`. Tránh những tên quá chung như `data`, `value` hoặc `encoded` trong mã xử lý mật mã.

## 11. Xử lý lỗi: phân biệt lỗi encoding và lỗi Vault

| Nhóm lỗi | Ví dụ | Nên xử lý ra sao |
|---|---|---|
| Input text/UTF-8 | Dữ liệu binary không phải UTF-8 hợp lệ | Báo dữ liệu sai định dạng; không tự đoán charset |
| Base64 | Chuỗi có ký tự hoặc padding không phù hợp | Bắt lỗi decode, báo tên trường; không echo nội dung |
| Mapping JSON | Expected string nhưng nhận object/list/null | Kiểm tra kiểu, từ chối hoặc có quy tắc rõ |
| KV path/schema | Không có path hoặc field `blob_base64` | Phân biệt path không tồn tại với field thiếu |
| Transit quyền/khóa | Key không tồn tại, policy từ chối, context không đúng | Xử lý theo lỗi endpoint; không thay bằng kết quả Base64 rỗng |
| PKI response/PEM | Chứng chỉ không parse được hoặc field `certificate` thiếu | Phân biệt lỗi parser với lỗi issuance/permission |
| Lỗi kết nối/TLS/Vault | HTTP/network exception | Không coi là dữ liệu sai Base64 |
| Kích thước vượt giới hạn | Blob có hàng triệu ký tự | Từ chối sớm theo policy tài nguyên |

Không viết:

```java
try {
    return Base64.getDecoder().decode(encoded);
} catch (Exception ignored) {
    return new byte[0]; // Không an toàn: che lỗi dữ liệu.
}
```

Một field chứa secret không hợp lệ thường phải làm thao tác phụ thuộc nó thất bại có kiểm soát, thay vì thay bằng giá trị rỗng. Tránh tự động retry không giới hạn khi lỗi thuộc dữ liệu; retry chỉ hữu ích với một số lỗi tạm thời và phải theo chính sách của ứng dụng.

### 11.1. Logging và quan sát an toàn

- Không log plaintext, Base64 plaintext, ciphertext chứa dữ liệu nhạy cảm, `private_key`, response KV/Transit/PKI nguyên bản hay DTO có token.
- Không đưa payload vào exception message hoặc label metric; chỉ ghi tên field/endpoint category và lý do khái quát.
- Không tin rằng ciphertext/Base64 “an toàn để log”; ciphertext vẫn có thể lộ ngữ cảnh, khóa/phiên bản, tần suất thao tác hoặc dữ liệu nhạy cảm theo chính sách vận hành.
- Với Transit, có thể theo dõi thành công/thất bại, latency, nhóm lỗi, nhưng phải kiểm soát đường dẫn, tên key và request ID theo phân quyền quan sát.
- Với PKI, hạn chứng chỉ và serial có thể cần giám sát nhưng vẫn nên tránh phát tán thông tin không cần thiết ra log công khai.
- Chuyển mã ở Java không tự renew token Vault, gia hạn lease của credential động hay thực hiện rotation.

## 12. Kiểm thử: round-trip và contract từng endpoint

### 12.1. Unit test UTF-8 và Base64

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class BinaryEncodingTest {

    @Test
    void base64RoundTripsUtf8Vietnamese() throws Exception {
        String text = "Xin chào Vault!";
        byte[] source = text.getBytes(StandardCharsets.UTF_8);
        String encoded = Base64.getEncoder().encodeToString(source);
        byte[] restoredBytes = Base64.getDecoder().decode(encoded);

        assertArrayEquals(source, restoredBytes);
        assertEquals(text, decodeUtf8Strict(restoredBytes));
    }

    @Test
    void base64RoundTripsNonTextBytes() {
        byte[] source = new byte[] {0, 1, 2, (byte) 0xFF};
        String encoded = Base64.getEncoder().encodeToString(source);

        assertArrayEquals(source,
                Base64.getDecoder().decode(encoded));
    }

    @Test
    void rejectsInvalidBase64() {
        assertThrows(IllegalArgumentException.class,
                () -> decodeRequiredBase64(
                        "%invalid%",
                        "blob_base64",
                        1024));
    }

    @Test
    void rejectsWrongJsonFieldType() {
        assertThrows(IllegalArgumentException.class,
                () -> decodeRequiredBase64(
                        12345,
                        "blob_base64",
                        1024));
    }
}
```

Các test minh họa giả định hai helper `decodeUtf8Strict` và `decodeRequiredBase64` nằm trong một utility có thể truy cập từ class kiểm thử (hoặc được gọi qua tên class). Không sử dụng secret thật trong test fixture. Đừng assert/log chuỗi plaintext thật khi triển khai.

### 12.2. Ma trận kiểm thử contract

| Đường đọc/ghi | Input thử nghiệm | Kỳ vọng |
|---|---|---|
| UTF-8 | Chuỗi tiếng Việt có dấu | Encode và strict decode trả chuỗi ban đầu |
| Base64 | Bytes chứa `0x00` và `0xFF` | Round-trip giữ nguyên bytes |
| Base64 | Dữ liệu sai alphabet hoặc vượt giới hạn | Bị từ chối, không in đầu vào |
| KV v2 | JSON string chứa token | Đọc thành `String`, không tự Base64 decode |
| KV v2 `blob_base64` | Base64 của bytes nhị phân | Đọc String rồi decode theo schema |
| Transit encrypt | Plaintext UTF-8 bytes đã Base64 encode | Vault trả opaque `ciphertext` |
| Transit decrypt | Ciphertext được encrypt trước đó | Vault trả Base64 plaintext, decode thành bytes ban đầu |
| Transit decrypt | Ciphertext giả hoặc context sai | Lỗi endpoint; không trả byte rỗng |
| PKI issue | Role cấp chứng chỉ hợp lệ với quyền phù hợp | `certificate` là PEM có thể parse, không log response |
| PKI issue | Field certificate sai kiểu hoặc PEM hỏng | Báo lỗi mapping/parser |
| Auth/Lease | Token hoặc lease ID opaque | Không suy đoán format, không decode |

### 12.3. Kiểm thử tích hợp với Vault cô lập

Unit test của Java chỉ kiểm tra encode/decode; nó không chứng minh endpoint của Vault chấp nhận payload hoặc policy đã đúng. Với môi trường Vault thử nghiệm:

1. Tạo/mount KV v2 và Transit/PKI cần dùng, cấp policy chỉ đủ quyền cho workload kiểm thử.
2. Lưu/read một secret KV có trường `blob_base64` dùng bytes giả, xác nhận dữ liệu khôi phục đúng.
3. Tạo Transit key thử nghiệm, encrypt bytes Unicode/binary, decrypt và kiểm tra `byte[]` bằng `assertArrayEquals`; không đưa dữ liệu sản xuất vào test.
4. Xác minh ciphertext có thể gửi nguyên chuỗi tới decrypt mà không xử lý như Base64.
5. Kiểm thử lỗi do thiếu quyền, thiếu key, context sai hoặc cấu hình Transit không phù hợp; phân biệt chúng với `IllegalArgumentException` của Base64.
6. Nếu có PKI test role, cấp chứng chỉ thử nghiệm, parse PEM và kiểm tra thời hạn/issuer theo policy test.
7. Kiểm tra log, tracing, CI output không chứa plaintext Base64, API key, private key, token hoặc response đầy đủ.

Nếu môi trường không có PKI role/Transit key tương ứng, không tạo quyền rộng hoặc sinh secret thật chỉ để chạy bài học. Có thể dùng mock/unit tests cho phần Java và kiểm thử tích hợp trên hạ tầng thử nghiệm đã được phê duyệt.

## 13. Bài tập thực hành

### Bài tập 1 — Tìm điểm sai của một lời gọi Transit

Một đoạn mã gửi:

```java
vaultOperations.write(
        "transit/encrypt/orders-key",
        Map.of("plaintext", "Xin chào"));
```

Hãy giải thích vì sao field `plaintext` chưa đáp ứng biểu diễn mà endpoint yêu cầu. Viết lại thành thao tác UTF-8 → Base64 và cho biết khi giải mã phải khôi phục nội dung bằng những bước nào.

**Gợi ý:** `String.getBytes(StandardCharsets.UTF_8)` trước `Base64.getEncoder().encodeToString(...)`. Response decrypt trả Base64 plaintext; decode về byte rồi chỉ tạo String khi plaintext là UTF-8 text.

### Bài tập 2 — Dữ liệu nhị phân không phải text

Cho bytes:

```java
byte[] content = {0, 1, 2, (byte) 0xFF};
```

Viết Java encode theo Base64 rồi decode, kiểm tra bằng `Arrays.equals(...)` hoặc `assertArrayEquals(...)`. Vì sao không nên tạo `new String(content, UTF_8)` để lưu tạm? Hãy thử strict UTF-8 decoder xem có chấp nhận `0xFF` ở vị trí cuối không.

### Bài tập 3 — Phân biệt KV, Transit và PKI

Xem ba giá trị giả định:

```text
KV field api_token:        "aGVsbG8="
Transit ciphertext:       "vault:v1:..."
PKI certificate:          "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
```

Giá trị nào **có thể** Base64-decode theo hợp đồng? Với `api_token`, vì sao chuỗi có dáng Base64 vẫn chưa đủ để quyết định giải mã? Với PEM, nên dùng parser nào trong Java?

**Định hướng:** KV token là chuỗi opaque nếu schema không nói khác; Transit ciphertext gửi nguyên chuỗi tới Vault decrypt; PEM đưa vào parser X.509 hoặc consumer chấp nhận PEM thay vì decode toàn bộ.

### Bài tập 4 — Review code chống lộ secrets

Một service đang log `VaultResponse` sau Transit decrypt và log `PKI private_key` để debug. Hãy đề xuất các thay đổi: điều gì có thể log thay thế, cách chẩn đoán lỗi Base64/PEM mà không lộ payload và cách kiểm thử để tránh log rò rỉ.

## 14. Những điểm cần ghi nhớ

- `String`, UTF-8 bytes và Base64 là các lớp biểu diễn khác nhau; Base64 **không phải encryption**.
- Chọn `StandardCharsets.UTF_8` tường minh khi chuyển văn bản ↔ byte; dữ liệu binary không nên được tự động biến thành text.
- Với KV v2, field JSON bình thường không tự mang ý nghĩa Base64. Chỉ decode khi schema field hoặc endpoint quy định.
- Transit `encrypt.plaintext` và `decrypt.plaintext` dùng Base64 bytes; Transit `ciphertext` là **opaque Vault string**, không decode toàn chuỗi như Base64.
- PKI `certificate` thường là PEM: văn bản có Base64 của DER bên trong, phải parse đúng định dạng; private key không được log.
- Token, lease ID và version/key identifier có ý nghĩa riêng; không suy ra chúng là Base64 chỉ từ ký tự.
- Dù dùng `VaultTemplate`, DTO hay raw `VaultOperations.write`, vẫn phải kiểm tra kiểu, kích thước, encoding, lỗi endpoint và policy. Không log plaintext, Base64 secrets, ciphertext hoặc PEM private key.

## Tài liệu tham khảo

- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): KV, Transit và các API hỗ trợ secrets engines.
- [Spring Vault — VaultOperations](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultOperations.html): thao tác đọc/ghi qua VaultTemplate.
- [HashiCorp Vault — Transit Secrets Engine API](https://developer.hashicorp.com/vault/api-docs/secret/transit): `plaintext`, `ciphertext`, `context` và encrypt/decrypt.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): biểu diễn JSON và lớp `data`/`metadata`.
- [HashiCorp Vault — PKI Secrets Engine API](https://developer.hashicorp.com/vault/api-docs/secret/pki): `certificate`, `ca_chain`, `private_key` và cấp chứng chỉ.
- [HashiCorp Vault — System Tools API](https://developer.hashicorp.com/vault/api-docs/system/tools): format dữ liệu của các công cụ hệ thống.
- [Java SE — `Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): các encoder/decoder basic, URL-safe và MIME.
- [Java SE — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): cách dùng UTF-8 tường minh.

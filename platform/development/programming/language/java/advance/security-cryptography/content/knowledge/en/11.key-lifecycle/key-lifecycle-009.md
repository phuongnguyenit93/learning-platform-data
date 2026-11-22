# 11.9. Giới hạn giữ bí mật trong byte[], String, heap dump và thông báo lỗi

Trong mật mã ứng dụng Java, rất nhiều lỗi bảo mật **không nằm ở AES, RSA hay HMAC** mà xảy ra sau khi một khóa, mật khẩu hoặc plaintext đã đi vào tiến trình: giá trị bí mật bị chuyển thành `String`, bị sao chép vào những mảng khó kiểm soát, ở lại trên heap lâu hơn dự kiến, xuất hiện trong heap dump hoặc vô tình bị ghi ra log/thông báo lỗi.

Một chương trình có thể dùng thuật toán mật mã đúng chuẩn mà vẫn làm lộ khóa qua câu lệnh:

```java
logger.debug("AES key: " + keyAsHex);
```

Hoặc làm mất bí mật khi tạo lỗi từ dữ liệu do người dùng gửi:

```java
throw new IllegalArgumentException("Invalid token: " + token);
```

**Nguyên tắc cốt lõi:** trong JVM quản lý bộ nhớ tự động, chúng ta có thể **giảm số bản sao, thời gian tồn tại và bề mặt phơi lộ** của bí mật, nhưng không thể tuyên bố “xóa hoàn toàn mọi dấu vết” chỉ vì đã gọi `Arrays.fill(secret, 0)` hoặc bỏ tham chiếu. Bảo mật thực tế cần kết hợp quản lý vòng đời, API phù hợp, cấu hình runtime/observability, phân quyền vận hành, kiểm soát sự cố và threat model.

## 1. Mục tiêu học tập và phạm vi

Sau bài học, bạn có thể:
- Phân biệt **biểu diễn bí mật** trong `byte[]`, `char[]`, `String`, `SecretKeySpec`, `ByteBuffer` và các object của JCA/JCE.
- Giải thích tại sao `String` là lựa chọn không phù hợp khi ứng dụng muốn chủ động xóa một giá trị bí mật khỏi một buffer.
- Biết chính xác `Arrays.fill(...)` và `PBEKeySpec.clearPassword()` xóa **buffer nào**, nhưng cũng nhận diện những copy không thuộc quyền kiểm soát của caller.
- Xác định dữ liệu nào có thể bị thu thập bởi **heap dump, crash dump, core dump, profiler, debugger, log, tracing, error reporting và telemetry**.
- Thiết kế đường đi của password, AES key, token, ciphertext, plaintext với **mức quyền tối thiểu, vòng đời tối thiểu và báo lỗi an toàn**.
- Phân biệt **public error response** với **internal diagnostic**; tránh rò rỉ khóa, secret, token và lỗi kiểu oracle qua thông báo hoặc thời gian đáp ứng.
- Chạy một ví dụ Java 17+ cho thấy **xóa mảng của caller khác với xóa mọi bản sao bí mật**, và áp dụng checklist kiểm thử/vận hành.

Bài học này thuộc chủ đề **vòng đời khóa**: từ lúc tạo/nhận khóa, sử dụng, dẫn xuất, sao chép, lưu tạm, ghi log, xử lý lỗi, cho đến khi hết nhu cầu. Đây không phải hướng dẫn xây một secure-memory allocator mới hoặc tuyên bố Java/JVM tự bảo đảm zeroization ở mọi tầng.

## 2. Vì sao bí mật dễ rời khỏi “vị trí ta nghĩ”?

Một khóa có thể đi qua nhiều lớp:

```text
Secret source                  Java application                 JVM / Infrastructure
------------------------       -----------------------------    -----------------------------
Vault / KMS / HSM ----+-----> byte[] / char[] input --------> heap, stack, GC regions
Console / login -------+       String / parser / serializer --> extra objects, char/byte copies
Random key generator ---+       SecretKeySpec / PBEKeySpec ---> JCE/provider copies
                               Cipher / Mac / KDF ----------> native/JNI/provider buffers
                               HTTP request/response -------> framework buffers
                               Logging / exception ---------> log files, traces, APM
                               Debugging / profiling -------> heap dumps, crash artifacts
                               Retry / cache / queue -------> longer lifetime and replicas
```

Ứng dụng thường chỉ biết chắc nó đang giữ một tham chiếu như `byte[] secret`. Nhưng sau khi gọi `SecretKeySpec`, `Cipher.init`, thư viện HTTP, JSON serializer hay logger, có thể tồn tại **những bản sao khác** ở nhiều vùng nhớ và hệ thống khác nhau.

Ví dụ: phía client nhận một token dưới dạng header text; ứng dụng có thể giữ:
1. Buffer byte của network.
2. `String` do HTTP framework tạo.
3. Một `String` mới khi trim/substring hoặc nối header.
4. Một object request mang token.
5. Một log message hoặc stack trace chứa token.
6. Một bản copy trong trace collector.

Xóa một biến ở bước 4 **không đồng nghĩa** đã xóa các bản sao 1, 2, 3, 5 và 6. Vì vậy, nguyên tắc thực dụng là **hạn chế nhập bí mật vào tầng không cần bí mật**, đặc biệt logging, tracing, exception message và data serialization.

### 2.1. Có những gì được xem là bí mật?

| Dữ liệu | Mức nhạy cảm | Rủi ro khi lộ |
| --- | --- | --- |
| AES key, HMAC key, RSA private key, seed khóa | **Secret** | Có thể giải mã, giả MAC/chữ ký theo phạm vi khóa |
| Password/passphrase, PIN, recovery code | **Secret** | Đăng nhập, đoán khóa, truy cập tài khoản |
| Access token, refresh token, session cookie, API key | **Bearer secret** | Có thể chiếm phiên hoặc gọi API |
| CEK/DEK đã unwrap, traffic/session key | **Secret** | Truy cập dữ liệu được bảo vệ theo phiên/tệp |
| Plaintext sau giải mã | **Nhạy cảm theo dữ liệu** | Rò rỉ nội dung người dùng/doanh nghiệp |
| Salt, IV/nonce, public key, public certificate | Thường **không bí mật** | Vẫn cần kiểm soát tính đúng và ràng buộc ngữ cảnh |
| Password verifier, encrypted file, metadata KDF | Không phải plaintext secret, nhưng **security-sensitive** | Hỗ trợ tấn công đoán offline, phá quyền riêng tư |
| Log/trace có identifier | Tùy threat model và dữ liệu cá nhân | Liên kết hành vi, thông tin nhạy cảm, lộ metadata |

Không đơn giản nói “đã băm rồi thì không còn nhạy cảm”, hoặc “nonce công khai nên mọi log chứa nonce đều an toàn”. Việc bảo vệ còn phụ thuộc tập dữ liệu, quy mô lưu trữ và khả năng liên kết record.

## 3. `String`: tiện dụng nhưng không thể xóa có chủ đích

`String` trong Java là một kiểu **immutable** (bất biến về mặt API). Khi bạn có:

```java
String password = "...";
```

bạn không có một API công khai an toàn để ghi đè các byte chứa nội dung string bên trong JVM. Gán:

```java
password = null;
```

chỉ làm mất một tham chiếu trong chương trình. Nó **không bảo đảm** vùng nhớ cũ đã bị ghi bằng zero ngay lập tức; garbage collector quản lý thời điểm thu hồi và bộ nhớ có thể còn dấu vết hoặc bản sao.

### 3.1. Tại sao `String` tạo thêm khó khăn?

- `String` bất biến nên không có cơ chế “xóa password” theo API công khai.
- Chuỗi được nối, format, parse, encode, log hoặc truyền qua framework có thể phát sinh **nhiều object/buffer bổ sung**.
- String literal trong source có thể vào constant pool/interning; tuyệt đối **không hardcode production secret** thành literal.
- Các phiên bản JVM hiện đại có tối ưu lưu trữ string, ví dụ Compact Strings ở HotSpot, nhưng chi tiết nội bộ có thể khác nhau. Không nên dựa vào việc `String` dùng `char[]` hay `byte[]` bên trong để tìm cách sửa bằng reflection hoặc `Unsafe`.
- `StringBuilder` có thể giữ backing buffer và phát sinh `String` mới khi gọi `toString()`; dùng builder để “dễ xóa” không tự giải quyết toàn bộ vấn đề.
- Khi một thư viện chỉ nhận `String`, việc bạn tạo string từ `char[]` có thể đã tạo thêm bản sao khó xóa. Cần đánh giá API boundary thay vì cho rằng một bước chuyển đổi là vô hại.

**Tránh các thao tác sau với secret:**

```java
// KHÔNG DÙNG trong code production:
String passwordText = new String(passwordChars);
String secretAsHex = java.util.HexFormat.of().formatHex(aesKeyBytes);
System.out.println("Authorization: Bearer " + token);
throw new RuntimeException("Failed with password=" + passwordText);
```

Đây là các **anti-pattern** để nhận biết, không phải ví dụ cần chạy. In/log/format secret ra text làm tăng nguy cơ persistence và exfiltration.

### 3.2. `char[]` tốt hơn `String` đến mức nào?

`char[]` cho phép caller chủ động ghi đè các phần tử:

```java
char[] password = /* input from controlled source */;
try {
    // Use password with an API accepting char[].
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

Điều này đem lại một lợi thế thực tế: **mảng mà bạn sở hữu** có thể được ghi đè sau khi dùng. Tuy nhiên, nó không bảo đảm:
- Thư viện đã không sao chép mảng.
- JIT/compiler, GC hoặc hệ điều hành không giữ dấu vết ở nơi khác.
- Mật khẩu chưa từng tồn tại dưới dạng `String` trong một tầng trước đó.
- Một heap dump hoặc logger đã không giữ bản sao trước thời điểm xóa.

`char[]` chủ yếu có ích khi **toàn bộ đường xử lý** hạn chế biến bí mật thành string hoặc log và dùng đúng lifetime. Một password đầu tiên đã đọc bằng `String` rồi chuyển qua `char[]` không “xóa” được `String` ban đầu.

### 3.3. Input password trong Java

Trong ứng dụng dòng lệnh có console thực, `Console.readPassword()` trả `char[]`, giúp tránh một số đường tạo `String` thông thường:

```java
java.io.Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Secure console unavailable");
}
char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("No password supplied");
}
try {
    // Use password with an API accepting char[].
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

Đây là một **đoạn minh họa API**, không phải chương trình độc lập; `System.console()` thường là `null` trong IDE, nhiều môi trường container hoặc pipe. Không nên tự động fallback sang đọc password bằng `Scanner.nextLine()` mà không xem xét yêu cầu an ninh của ứng dụng.

Với HTTP, mobile, desktop UI hoặc SDK, dữ liệu thường có thể đã được framework decode vào `String`. Hãy kiểm soát **request logging, tracing, retention, memory lifetime** và tầng vận chuyển; không thể khẳng định caller đã “never held String” nếu framework ở phía trước đã tạo nó.

## 4. `byte[]`: có thể ghi đè, nhưng không đồng nghĩa xóa mọi bản sao

`byte[]` là dạng phổ biến cho AES key, nonce, plaintext, ciphertext, HMAC output và key derivation output. Với một secret byte array do chương trình sở hữu:

```java
byte[] secret = /* securely obtained secret bytes */;
try {
    // Use secret.
} finally {
    java.util.Arrays.fill(secret, (byte) 0);
}
```

Sau khi `Arrays.fill` hoàn tất, phần tử của **chính mảng được truyền vào** đã được gán zero theo mô hình Java bình thường. Nhưng đây không phải cam kết xóa hết bí mật trên toàn hệ thống.

### 4.1. Những lý do vẫn còn bản sao

1. **Constructor có thể copy.** Ví dụ `SecretKeySpec(byte[], algorithm)` lưu bản copy của key bytes. Zero hóa mảng đầu vào không phá hủy object secret key đã tạo.
2. **`getEncoded()` có thể trả bản sao** của khóa mã hóa được; một caller phải quản lý/xóa mảng trả về. Với một số key provider/HSM, `getEncoded()` có thể trả `null` vì khóa không exportable.
3. **Cipher, Mac, KeyAgreement, provider** có thể lưu dữ liệu trong object hoặc native memory; API không hứa xóa mọi bản copy khi caller xóa mảng.
4. **`Arrays.copyOf`, `clone`, `ByteArrayOutputStream.toByteArray()`** tạo mảng khác. `toByteArray()` thường tạo bản copy, còn buffer nội bộ của stream có thể tiếp tục tồn tại.
5. **String/hex/Base64 encoding** tạo text object có thể sống lâu hơn buffer ban đầu. Không dùng encoding này chỉ để “debug xem khóa có đúng không”.
6. **GC, stack và JIT** có quyền sắp xếp/di chuyển/ghi đè dữ liệu bên trong quy tắc runtime. Zeroization best-effort ở Java không cung cấp bảo đảm chống đối thủ có quyền đọc memory dump ở mọi thời điểm.

**Mệnh đề đúng:** “Tôi đã zeroize mảng `secret` do mình nắm giữ.”  
**Mệnh đề không có căn cứ:** “Sau đó không còn bất kỳ byte khóa nào trong tiến trình, swap, heap dump hay bộ nhớ provider.”

### 4.2. Cần dùng `finally` để giảm cửa sổ phơi lộ

Đừng chỉ xóa secret ở cuối happy path:

```java
byte[] keyBytes = loadSensitiveKeyBytes();
doCrypto(keyBytes); // Có thể throw exception.
java.util.Arrays.fill(keyBytes, (byte) 0);
```

Nếu `doCrypto` ném ngoại lệ, việc xóa ở cuối sẽ không chạy. Pattern an toàn hơn:

```java
byte[] keyBytes = loadSensitiveKeyBytes();
try {
    doCrypto(keyBytes);
} finally {
    java.util.Arrays.fill(keyBytes, (byte) 0);
}
```

Đây vẫn là **pseudocode dùng các hàm minh họa** `loadSensitiveKeyBytes()` và `doCrypto()`, không phải Java class độc lập. Nội dung hữu ích là cách đặt cleanup vào `finally`.

Nên kiểm soát thêm lifetime:
- Lấy key **gần nhất có thể** trước thời điểm dùng.
- Tránh giữ key trong static field, singleton lâu dài, session object hoặc global cache trừ khi có threat model và vòng đời cụ thể.
- Tránh tạo quá nhiều bản copy; giới hạn phạm vi secret qua các lớp service.
- Khi không cần key nữa, đóng session/handle của provider theo API được hỗ trợ.
- Xóa cả plaintext buffers cần thiết theo chính sách, không chỉ key bytes.

### 4.3. `Arrays.fill` là best effort chứ không phải secure erase có chứng minh

Trong một JVM managed runtime, ngoài mảng thấy được, dữ liệu có thể còn ở bản copy, register, stack, native state, swap hoặc dump đã chụp trước đó. Tối ưu compiler/JIT và cơ chế garbage collector còn khiến cam kết về **physical memory erasure** khó có thể đưa ra với Java thuần.

Khi threat model yêu cầu zeroization ở mức phần cứng/OS, không nên bịa rằng `Arrays.fill` bảo đảm được. Cần đánh giá secure-memory facilities, HSM/KMS, provider phù hợp, memory-locking nếu khả thi, quyền debug/dump và thiết kế không export secret. Các giải pháp native cũng không xóa được các bản sao mà ứng dụng từng tạo hoặc những secret đã xuất vào log.

Một số API có tên `Destroyable.destroy()` hoặc `isDestroyed()`, nhưng **không phải mọi loại `SecretKey`, `PrivateKey` hay provider đều hỗ trợ destroy thực sự theo cùng cách**. Phải kiểm tra tài liệu/behavior của implementation, xử lý lỗi và không đồng nhất `destroy()` với xóa một khóa nằm trong HSM hoặc bản backup.

## 5. `SecretKeySpec` và sao chép key material

Trong JCA/JCE, một mẫu thường gặp:

```java
byte[] keyBytes = /* AES or HMAC key bytes */;
javax.crypto.spec.SecretKeySpec key =
    new javax.crypto.spec.SecretKeySpec(keyBytes, "AES");
java.util.Arrays.fill(keyBytes, (byte) 0);
```

Lúc này **caller key array có thể đã được xóa**, nhưng `SecretKeySpec` vẫn cần chứa thông tin khóa để thực hiện phép mã hóa. Đó không phải bug: constructor đã quản lý key material riêng.

Hệ quả:

- Không xem zero hóa `keyBytes` là đã hủy toàn bộ `SecretKeySpec`/provider state.
- Tránh giữ `SecretKeySpec` lâu hơn cần thiết, đặc biệt trong object có vòng đời toàn ứng dụng.
- Không gọi `key.getEncoded()` chỉ để in hex hoặc so sánh; nó làm xuất thêm bản copy byte của secret.
- Nếu cần khóa không xuất được, dùng cơ chế provider, KeyStore, PKCS#11/HSM hoặc KMS có API handle phù hợp. **Không giả định** mọi `SecretKey` Java đều thực sự non-extractable; `SecretKeySpec` không phải khóa HSM.
- Quản lý rotation/expiration/revocation và backup của key theo hệ thống lưu khóa, không dựa vào việc GC thu hồi object.

### 5.1. Vì sao xóa mảng gốc không làm `Mac` ngừng hoạt động?

`SecretKeySpec` được tạo từ giá trị khóa đầu vào. Nếu ứng dụng xóa mảng gốc rồi gọi:

```java
javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
mac.init(secretKeySpec);
byte[] tag = mac.doFinal(messageBytes);
```

MAC vẫn có thể hoạt động bình thường vì object khóa còn giữ vật liệu cần thiết. Đây là điểm quan trọng trong ví dụ runnable ở phần 10: **còn dùng được key object** đồng nghĩa không thể kết luận rằng “mọi bản sao khóa đã bị xóa”.

Mặt khác, việc `Mac` có thể dùng object khóa sau đó **không chứng minh** bản thân MAC lưu khóa vô thời hạn. Lifetime phụ thuộc scope, implementation và cách ứng dụng giữ tham chiếu.

## 6. `PBEKeySpec` và password KDF: các bản sao thường bị bỏ qua

Java có `PBEKeySpec` để dùng password dạng `char[]` cùng salt và tham số dẫn xuất khóa:

```java
char[] password = /* user input */;
byte[] salt = /* random salt */;
javax.crypto.spec.PBEKeySpec spec =
    new javax.crypto.spec.PBEKeySpec(password, salt, 100_000, 256);
```

Constructor `PBEKeySpec` tạo bản sao thông tin password theo hợp đồng API. Vì vậy:
- Zero hóa mảng `password` của caller **không đồng nghĩa** `spec` đã mất khả năng dẫn xuất.
- Khi dùng xong, gọi `spec.clearPassword()` để xóa bản sao password do `PBEKeySpec` sở hữu.
- `spec.getPassword()` trả một **bản copy mới**; caller phải quản lý/xóa copy này nếu gọi.
- `SecretKeyFactory.generateSecret(spec)` và `getEncoded()` có thể tạo output/key material khác; quản lý lifetime của từng đối tượng và mảng output, không chỉ mảng password đầu vào.
- `PBEKeySpec` nhận `char[]`, nhưng provider có thể mã hóa password thành byte nội bộ; xóa `spec` không chứng minh tất cả bản sao provider đã bị xóa.
- Dữ liệu salt thường không bí mật, nhưng vẫn phải lưu/giữ đúng để verify password hoặc giải mã theo KDF profile.

Một ví dụ vòng đời:

```text
Caller char[] password
   |
   +-- PBEKeySpec constructor -> internal password copy
   |                                   |
   |                                   +-- SecretKeyFactory -> derived key material
   |                                                                |
   v                                                                v
Caller Arrays.fill(password, '\0')                     Derived byte[] / SecretKey / provider
             |                                                      |
             v                                                      v
Own array cleared                              Must separately scope/clear as supported
                                     |
                          spec.clearPassword() for spec's copy
```

Đối với lưu mật khẩu, dùng password-hashing scheme chuyên dụng và thư viện được thẩm định theo yêu cầu triển khai; `PBKDF2WithHmacSHA256` trong ví dụ chỉ giúp minh họa API và các bản sao. Không dùng direct SHA-256 như password verifier và không coi một giá trị PBKDF2 được lưu công khai là khóa AES có thể dùng lại.

### 6.1. Password từ framework đã là `String` thì sao?

Nếu HTTP framework trả password dạng `String`, việc chuyển sang `char[]` rồi xóa mảng **không xóa bản string đã sinh**. Khi không thể kiểm soát hết đường đi, giảm rủi ro bằng:
- Không log request body, form field hoặc authorization header chứa password.
- Không lưu password trong user/session DTO sống lâu, exception object hoặc async task queue.
- Không đưa password vào template/error message, metrics labels hay tracing span attributes.
- Thực hiện verify/dẫn xuất ngay trong scope ngắn, tránh lưu vào cache.
- Giới hạn quyền đọc heap dump, debugger và process memory.
- Tách dữ liệu cần audit khỏi dữ liệu bí mật; log trạng thái, correlation ID và loại lỗi thay vì giá trị password.

Việc thiết kế boundary phù hợp thường quan trọng hơn tranh luận “String hay char[]” nếu cả pipeline đã nhân bản bí mật qua nhiều nơi.

## 7. `ByteBuffer`, off-heap và native memory: không phải vùng an toàn mặc định

`ByteBuffer` có thể là heap-backed hoặc direct/off-heap. Cả hai cần phân biệt **position management** với **ghi đè dữ liệu**.

Ví dụ:

```java
java.nio.ByteBuffer buffer = java.nio.ByteBuffer.allocateDirect(1024);
buffer.put(secretBytes);
buffer.clear(); // Chỉ đặt lại position/limit. KHÔNG zero memory!
```

`clear()` trong API buffer **không** có nghĩa xóa nội dung; nó chuẩn bị buffer để ghi/đọc theo vị trí mới. Tương tự, `flip()` và `rewind()` là thao tác con trỏ/giới hạn, không có bảo đảm wipe.

Nếu ứng dụng sở hữu một buffer mutable và muốn ghi zero:
- Phải ghi đè **đúng toàn bộ miền buffer nhạy cảm** bằng thao tác được hỗ trợ, chú ý position/limit/slice và các view cùng chia sẻ memory.
- Phải kiểm soát bản sao trong heap, native allocation, JNI/FFI, provider state.
- Phải xử lý lifetime deallocation; off-heap không tự chống crash dump, đọc process memory, swap hoặc privileged debugger.
- Không dựa vào reflection/`Unsafe` để sửa nội bộ `String` hoặc lớp JCE.
- Với yêu cầu bảo mật cao, đánh giá thư viện/native API đã được kiểm toán và chính sách hệ điều hành; bản chất direct memory **không biến nó thành HSM**.

Kể cả khi direct buffer được zero, secret có thể từng đi qua `byte[]` để gọi API hoặc được provider copy; do đó hãy nhìn toàn bộ **data flow**.

## 8. Heap dump, crash dump, profiler và các bản sao hạ tầng

### 8.1. Heap dump có thể chứa những gì?

Heap dump là ảnh chụp của các object Java trên heap vào một thời điểm. Tùy JVM/trạng thái runtime, có thể chứa:
- `String` còn giữ token/password/secret đã được chuyển sang text.
- `byte[]` và `char[]` chứa key, password, nonce, plaintext hoặc dữ liệu nhạy cảm khác.
- DTO request/response, cache entry, message payload, HTTP headers, exception object.
- Object `SecretKeySpec`, KDF context, buffers và các structure còn sống.
- Dữ liệu gián tiếp liên kết người dùng, session, tenant, hostname và hoạt động bảo mật.

Heap dump **không nhất thiết** phản ánh toàn bộ native memory/register/stack hoặc mọi bản sao trong hệ thống, nhưng chỉ riêng phần có thể chứa đã đủ để xem nó như một **tài sản nhạy cảm**. Không nên gửi heap dump production vào ticket, chat hoặc công cụ bên ngoài khi chưa có quyền, quy trình bảo vệ và redaction thích hợp.

### 8.2. Điều kiện tạo dump

Một số JVM có thể được cấu hình tạo heap dump khi out-of-memory, ví dụ `-XX:+HeapDumpOnOutOfMemoryError` và đường dẫn `-XX:HeapDumpPath=...`. Công cụ quản trị/diagnostic cũng có thể yêu cầu heap dump theo quyền tương ứng. Crash dump, core dump hoặc OS memory snapshot có phạm vi khác nhau và **có thể** chứa dữ liệu ngoài Java heap.

Rủi ro thực tế:
- Container ghi dump ra volume dùng chung, object store hoặc thư mục được backup tự động.
- Crash reporting/telemetry upload artifact lên dịch vụ ngoài vùng tin cậy.
- Một developer có quyền debug production tải dump về laptop không mã hóa.
- Dump tồn tại sau incident, không có TTL, access audit hoặc cơ chế xóa.
- Log file/ticket kèm stack trace hoặc command-line args lộ cấu hình/credentials.

**Không cần coi dump là “xấu” để cấm mọi debugging.** Heap dump có giá trị điều tra memory leak và incident. Điều đúng là phải có chính sách xử lý nó như dữ liệu nhạy cảm: quyền truy cập tối thiểu, lưu có mã hóa, retention ngắn, theo dõi truy cập, đường truyền được xác thực, redaction khi khả thi, xóa theo quy trình và không xuất ra môi trường không được phép.

### 8.3. Cấu hình vận hành nên cân nhắc

1. **Access:** giới hạn ai có quyền attach debugger/profiler, tạo hoặc download dump; đánh giá quyền hệ điều hành/container/hypervisor.
2. **Storage:** dump directory/volume với quyền hệ thống tệp chặt, mã hóa at rest và key management riêng nếu phù hợp.
3. **Transfer:** kênh vận chuyển bảo mật; tránh URL dump có quyền công khai hoặc link lâu hạn.
4. **Retention:** thời gian giữ đủ cho điều tra, tự động xóa theo policy, có audit.
5. **Automation:** biết rõ agent nào có thể kích hoạt và upload diagnostic bundles; vô hiệu hóa thu thập nhạy cảm không cần thiết.
6. **Incident response:** nếu có bằng chứng key/password/token đã xuất vào dump không kiểm soát, đánh giá **rotation/revocation** và ảnh hưởng dữ liệu theo scope.
7. **Backups:** kiểm tra dump bị copy sang hệ backup hoặc DR không; xóa primary file không nhất thiết xóa mọi bản backup.
8. **Testing:** dùng canary giả, môi trường staging và công cụ được phê duyệt để kiểm tra rủi ro; không cần thu thập secret production thật để chứng minh.

Heap dump là một **snapshot theo thời gian**. Xóa `byte[]` sau snapshot không xóa được artifact đã chụp. Một lỗi logging hoặc export dump có thể kéo dài tuổi thọ secret từ vài mili giây trong RAM thành nhiều tháng trên storage.

### 8.4. Heap dump khác với log và stack trace

- **Heap dump:** có thể chứa trạng thái object thô ngay cả khi code không chủ động log key.
- **Log:** do ứng dụng/framework tạo ra khi log request, error, object `toString()` hoặc diagnostic.
- **Stack trace:** chứa stack frames và exception messages/causes; nếu exception chứa thông tin nhạy cảm trong message, log stack trace sẽ phát tán nó.
- **Distributed tracing/APM:** có thể copy HTTP headers/body, SQL parameters và baggage/span attributes vào hệ thống khác.
- **Metrics:** label/tag có cardinality cao hoặc chứa token/user identifiers có thể rò rỉ ra dashboards và lưu rất lâu.

Thực tế phải có chính sách cho **từng loại dữ liệu quan sát**; chỉ tắt một logger không loại bỏ đường leak từ tracing, error reporting hoặc crash artifact.

## 9. Thông báo lỗi: nơi secret thường bị đưa ra khỏi tiến trình

### 9.1. Error message không nên chứa secret

Không nên làm:

```java
// Anti-pattern: KHÔNG sử dụng.
throw new IllegalArgumentException("Invalid API key: " + apiKey);
throw new SecurityException("Expected=" + expectedMac + ", actual=" + receivedMac);
logger.error("Failed to decrypt " + plaintext, exception);
```

Rủi ro:
- Exception message có thể đi vào access log, app log, APM, alert, support ticket.
- Framework có thể tự chuyển exception message thành HTTP response.
- Exception `toString()` và stack trace có thể bao gồm message/causes.
- Khi log một object bằng `{}`, `toString()` của nó có thể tiết lộ các field nhạy cảm.
- Exception được ném trong async/retry/queue có thể được lưu hoặc serialize bởi infrastructure.

**Đừng đưa secret vào exception ngay từ đầu.** “Log nội bộ thì được” không phải lý do để gắn password/key/token vào message rồi hy vọng không bị lộ.

### 9.2. Phân tách public error với internal diagnosis

Đối với client chưa tin cậy, trả một **mã lỗi ổn định và thông điệp chung**:

```json
{
  "code": "CRYPTO_OPERATION_FAILED",
  "message": "The requested operation could not be completed."
}
```

Với logic đăng nhập, có thể cần một thông điệp chung kiểu `AUTHENTICATION_FAILED` khi credential sai. Với mã hóa/giải mã, đừng trả “khóa AES đúng nhưng GCM tag sai tại byte X”, “private key đã unwrap được” hoặc giá trị tham số nhạy cảm cho caller bên ngoài.

Trong **internal telemetry có phân quyền**, có thể ghi:
- Correlation/request ID ngẫu nhiên.
- Tên component/op không nhạy cảm (ví dụ `decrypt-document`).
- Mã lỗi được whitelist (ví dụ `AUTH_TAG_INVALID`), mức độ nghiêm trọng và số lần xảy ra.
- Thời gian, phiên bản protocol, key identifier không nhạy cảm **nếu chính sách cho phép**.
- Stack trace đã được đánh giá, không chứa token/password hoặc dữ liệu decrypted.

Không log:
- AES/private/HMAC/traffic keys, seed, session cookie, bearer token, refresh token, password.
- Raw headers `Authorization`, `Cookie`, `Set-Cookie`, secret form fields.
- Plaintext từ tệp bí mật, KDF derived key, key wrap material chưa mã hóa.
- Exception cause hoặc object dump khi chưa biết chắc message và `toString()` không mang bí mật.

Đừng biến `keyId` hoặc hash một field nhạy cảm thành định danh công khai một cách tự động: chúng vẫn có thể lộ metadata, tương quan hoạt động hoặc hỗ trợ đoán nếu đầu vào ít entropy.

### 9.3. Phân biệt mã lỗi để vận hành nhưng không tạo oracle

Một API cần đủ thông tin cho bảo trì, nhưng lỗi mật mã có thể trở thành **oracle** nếu attacker quan sát được khác biệt về:
- Thông báo trả ra: “RSA unwrap succeeded” vs “AES tag invalid”.
- HTTP status/body tùy password tồn tại, token có prefix đúng, private key nào được chọn.
- Thời gian phản hồi phụ thuộc mức kiểm tra/chỗ thất bại.
- Kích thước response, đóng kết nối hay số lần retry khác nhau.
- Timing của so sánh secret bằng string thông thường.

Vì vậy, thiết kế error mapping cần theo **threat model của giao thức**, không chỉ ẩn text trong response. Các nhóm lỗi nhạy cảm có thể cần hợp nhất ở public API, giới hạn request, giữ thời gian hành vi hợp lý, áp rate limiting và kiểm tra khóa theo policy. Điều này **không có nghĩa** có thể dễ dàng bảo đảm constant-time cho toàn bộ HTTP stack; cần dùng thư viện mật mã đã được kiểm tra và tránh tạo nhánh tiết lộ secret rõ ràng.

Ví dụ, nếu một API kiểm tra HMAC và dùng:

```java
if (expectedTagHex.equals(receivedTagHex)) { ... }
```

thì cách so sánh text thông thường không được thiết kế là phép so sánh authentication tag bí mật chống timing leak. Nên **decode đúng wire format, kiểm tra độ dài và dùng API so sánh byte dành cho bảo mật** như `MessageDigest.isEqual(...)` khi thích hợp. Cũng không dùng “thử nhiều thuật toán/khóa tới khi đúng” mà thiếu version/policy, vì dễ có algorithm/key confusion và tạo nhiều đường quan sát lỗi.

## 10. Java 17+: kiểm chứng những giới hạn bộ nhớ và báo lỗi an toàn

Ví dụ runnable này **không cố đo nội dung heap dump** (vốn phụ thuộc JVM/GC/thời điểm), mà kiểm chứng những mệnh đề có thể quan sát qua API:

1. Mảng `char[]` password của caller được xóa; `PBEKeySpec` vẫn có thể cho KDF chạy vì đã sở hữu một bản copy.
2. `PBEKeySpec.clearPassword()` ngăn đọc password qua `getPassword()` sau khi đã clear.
3. Mảng chứa derived KDF output được ghi zero trong `finally`.
4. Mảng byte nguồn dùng tạo `SecretKeySpec` đã bị xóa, nhưng **key object vẫn dùng được** cho HMAC. Đây là minh chứng rằng việc xóa buffer nguồn không xóa hết key material.
5. Một thông báo public error chỉ trả **mã lỗi được allowlist**, không đưa nguyên văn message provider ra ngoài.

Tạo file **`SecretMemoryDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class SecretMemoryDemo {
    static boolean zeroed(char[] value) {
        for (char c : value) {
            if (c != '\0') return false;
        }
        return true;
    }

    static boolean zeroed(byte[] value) {
        for (byte b : value) {
            if (b != 0) return false;
        }
        return true;
    }

    static String publicError(Exception ignored) {
        return "CRYPTO_OPERATION_FAILED";
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        // Public fixture for demonstration only.
        // Do not hardcode real passwords in source.
        char[] password = {'d', 'e', 'm', 'o', '-', 'p', 'a', 's', 's'};
        byte[] salt = new byte[16];
        random.nextBytes(salt);

        PBEKeySpec spec = new PBEKeySpec(password, salt, 100_000, 256);
        Arrays.fill(password, '\0');

        byte[] derived = null;
        try {
            derived = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();

            System.out.println("Caller password cleared: "
                    + zeroed(password));
            System.out.println("KDF still worked after caller clear: "
                    + (derived.length == 32));
        } finally {
            spec.clearPassword();
            if (derived != null) {
                Arrays.fill(derived, (byte) 0);
            }
        }

        boolean passwordAccessRejected = false;
        try {
            spec.getPassword();
        } catch (IllegalStateException expected) {
            passwordAccessRejected = true;
        }
        System.out.println("PBEKeySpec password access rejected: "
                + passwordAccessRejected);
        System.out.println("Derived buffer cleared: "
                + zeroed(derived));

        byte[] originalKeyBytes = new byte[32];
        random.nextBytes(originalKeyBytes);
        SecretKeySpec key = new SecretKeySpec(
                originalKeyBytes, "HmacSHA256"
        );
        Arrays.fill(originalKeyBytes, (byte) 0);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        byte[] tag = mac.doFinal(
                "public demo input".getBytes(StandardCharsets.UTF_8)
        );

        System.out.println("Original key array cleared: "
                + zeroed(originalKeyBytes));
        System.out.println("Key object still usable: "
                + (tag.length == 32));

        Arrays.fill(tag, (byte) 0);
        System.out.println("Tag buffer cleared: " + zeroed(tag));

        try {
            throw new GeneralSecurityException(
                    "provider-specific diagnostic"
            );
        } catch (GeneralSecurityException internal) {
            System.out.println("Public error: "
                    + publicError(internal));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac SecretMemoryDemo.java
java SecretMemoryDemo
```

**Kết quả stdout đã kiểm chứng qua JDK tương thích Java 17:**

```text
Caller password cleared: true
KDF still worked after caller clear: true
PBEKeySpec password access rejected: true
Derived buffer cleared: true
Original key array cleared: true
Key object still usable: true
Tag buffer cleared: true
Public error: CRYPTO_OPERATION_FAILED
```

### 10.1. Diễn giải đúng các dòng output

**“Caller password cleared: true”** chỉ nói mảng `password` của chương trình đã được ghi toàn `'\0'`. Nó không nói password chưa từng có ở một object khác.

**“KDF still worked after caller clear: true”** cho thấy `PBEKeySpec` có dữ liệu password cần thiết dù caller đã xóa mảng input. Nếu code chỉ xóa caller `char[]` nhưng quên `spec.clearPassword()`, bản copy trong spec có thể còn tồn tại cho đến khi object được thu hồi. Một số bước trong provider có thể tạo thêm bản sao không được kiểm soát bởi `clearPassword()`.

**“PBEKeySpec password access rejected: true”** kiểm tra hợp đồng API: sau `clearPassword()`, gọi `getPassword()` bị từ chối. Điều này **không** chứng minh toàn bộ RAM đã được wipe.

**“Derived buffer cleared: true”** xác nhận ứng dụng ghi zero vào chính mảng `derived` trong `finally`. Nội bộ provider, object secret key hoặc JVM có thể còn bản sao. Mỗi buffer có lifetime và cleanup khác nhau.

**“Original key array cleared: true” + “Key object still usable: true”** là điểm quan trọng: `SecretKeySpec` có key material riêng; xóa mảng nguồn không hủy key object. Không nên tuyên bố “key đã được hủy an toàn” chỉ dựa trên mảng gốc đã zero.

**“Tag buffer cleared: true”** minh họa có thể quản lý output buffer. Một HMAC tag thông thường không nhất thiết là secret như key, nhưng rủi ro logging, context và chính sách retention vẫn cần xét. Đây là mẫu quản lý mảng, không phải bắt buộc mọi ứng dụng phải zero tất cả tag công khai.

**“Public error: CRYPTO_OPERATION_FAILED”** minh họa API trả một **mã lỗi ổn định**. Trong production, cần thêm correlation ID, telemetry có phân quyền và quy tắc error mapping theo threat model.

### 10.2. Những giới hạn cố ý của demo

- Password demo được viết trong source bằng các ký tự riêng lẻ. **Không** viết secret thực vào source/config/version control; đây là fixture công khai và không chứng minh input an toàn ở một hệ thống nhận password thực.
- `PBKDF2WithHmacSHA256` với 100.000 iterations **chỉ phục vụ demo memory lifecycle**, không phải tham số production khuyến nghị để lưu mật khẩu. Khi triển khai thật, chọn password-hashing/KDF scheme và cost theo chính sách/benchmark hiện hành, ưu tiên Argon2id khi phù hợp và thư viện tin cậy.
- `SecretKeySpec` tiếp tục tồn tại đến khi hết scope; demo không có API để wipe key material nội bộ của nó. Không suy ra “mảng nguồn zero là process hết secret”.
- Dữ liệu provider, JIT/GC, native heap, swap, profiler và dump **không thể kiểm tra đầy đủ** chỉ bằng unit test này.
- `Arrays.fill` ở cuối không ngăn một heap dump được chụp **trước đó** chứa bí mật.
- Mẫu `publicError` không tự cung cấp security logging, rate limiting, chống timing oracle, access control hoặc incident response.
- Nếu muốn chứng minh hệ thống **không hề log secret**, cần test cả framework, filters, tracing, APM, logging encoder và exception handler.

## 11. Thiết kế một vòng đời bí mật trong ứng dụng Java

Hãy thiết kế “đường đi của secret” thay vì chỉ chọn một container.

### 11.1. Nhận secret

- Lấy secret qua TLS/authenticated channel hoặc KMS/Vault API đã xác thực, không qua query string/URL/cmdline có thể được ghi log.
- Nếu password được nhập bởi người dùng, ưu tiên API nhận `char[]` khi khả thi; với HTTP, kiểm soát logging/DTO và thời gian tồn tại.
- Nếu key ngẫu nhiên do ứng dụng tạo, dùng `SecureRandom` và key-size/scheme đúng chuẩn. Không dùng `java.util.Random` cho khóa.
- Đừng biến secret thành `String`, hex/Base64 hoặc JSON text chỉ để truyền giữa các lớp; nếu phải có text vì wire format, hạn chế các bản sao và tắt logging nhạy cảm.

### 11.2. Sử dụng secret

- Phân biệt key được quản lý dưới dạng byte và **key handle không exportable** từ HSM/KMS; ưu tiên hạn chế việc xuất raw key khi threat model yêu cầu.
- Chỉ cấp quyền truy cập key cho component thực sự cần.
- Tránh lưu key trong field static, cache tổng quát, `toString()` hay DTO có thể serialize.
- Với cryptography, dùng JCA/JCE provider hoặc thư viện thẩm định; không tự viết AES, HMAC hoặc thao tác padding.
- Bảo đảm authorization của hành động dùng key, không chỉ “key tồn tại trong RAM”.

### 11.3. Kết thúc thao tác

- Dùng `try/finally` để clear caller-owned mutable secret buffers kể cả khi lỗi.
- Gọi API cleanup/close/destroy phù hợp cho secret holder và key session nếu implementation hỗ trợ; kiểm tra behavior cụ thể.
- Đừng giữ reference lâu hơn cần thiết. Tránh capture secret trong lambda, callback, async continuation hoặc thread-local không được clear.
- Với borrowed buffers/shared arrays, không tự zero hóa dữ liệu đang còn được phía khác sử dụng; thiết kế ownership rõ ràng ngay từ đầu.
- Giữ lifecycle của plaintext output và decrypted records ngắn; quyền/retention của plaintext cũng quan trọng như key.

### 11.4. Vận hành

- Kiểm soát heap-dump/crash-dump locations và quyền debugger/profiler.
- Chặn logging/tracing secret ở tầng ingress và response filters.
- Đặt retention cho diagnostic artifacts và có thủ tục xóa/thu hồi/rotation khi leak.
- Định kỳ kiểm tra cấu hình APM, exception reporting, HTTP logging, access logs và secret redaction.
- Bảo vệ cache, backup và snapshot chứa memory artifact hoặc plaintext.
- Kiểm thử không làm rơi secret từ lỗi bất thường như timeout, retry, OOM hoặc provider error.

## 12. Ranh giới quan trọng: giữ secret trong tiến trình hay không đưa secret vào đó?

Đối với các hệ thống mức độ nhạy cảm cao, hướng giảm rủi ro tốt nhất đôi khi là **không đưa raw long-term key vào Java heap**.

### 12.1. Khóa trong phần mềm

Một Java service tải AES key từ secret manager, giữ dưới dạng `byte[]` rồi `SecretKeySpec` để gọi `Cipher`. Đây là mô hình phổ biến, nhưng service process sẽ có khả năng sử dụng key và đôi khi có material thô trong heap/provider memory. Nếu process bị xâm nhập đủ sâu, các biện pháp memory hygiene không thể bảo đảm key vẫn bí mật.

### 12.2. Khóa không xuất qua HSM/KMS

Một service có thể gọi `Encrypt/Decrypt/Sign/Verify` qua KMS/HSM hoặc dùng một provider với key handle, để long-term private/key bytes không được export vào Java heap. Lợi ích:
- Giảm số bản sao long-term key trong app memory.
- Dễ phân quyền theo key/purpose và audit hoạt động sử dụng key.
- Hỗ trợ rotation, disable/revoke và chính sách truy cập tập trung.

**Nhưng không có ma thuật:** dịch vụ vẫn có thể đọc plaintext đầu vào/đầu ra và có thể **lạm dụng quyền gọi KMS** nếu bị chiếm. Nếu KMS trả một data key plaintext để app mã hóa dữ liệu, **data key đó vẫn ở process memory**. Cần thiết kế key usage scope, IAM, rate limits, encryption context, audit, blast radius và phòng vệ ứng dụng.

### 12.3. Tránh tuyên bố “secret chưa từng ở RAM”

Một API có thể giấu secret phía client nhưng thư viện TLS, KMS SDK hoặc OS vẫn xử lý dữ liệu trong buffer. Chỉ đưa ra bảo đảm đúng theo threat model và tài liệu provider. “Non-exportable” áp dụng cho **key object/handle cụ thể** không đồng nghĩa mọi plaintext hay derived key của quy trình đều non-exportable.

## 13. Bảng đối chiếu các chiến thuật bảo vệ

| Chiến thuật | Giảm được gì? | Không bảo đảm được gì? |
| --- | --- | --- |
| Dùng `char[]`/`byte[]` thay `String` khi khả thi | Caller có thể ghi đè buffer đang sở hữu | Không xóa các bản sao trước/ngoài buffer |
| `Arrays.fill` trong `finally` | Xóa mảng cụ thể kể cả khi throw | Không xóa `SecretKeySpec`/provider/dump cũ |
| `PBEKeySpec.clearPassword()` | Xóa password copy của `PBEKeySpec` theo API | Không xóa password từng ở `String` hay native provider |
| Giảm lifetime/scope của key | Giảm cửa sổ và số component có quyền thấy secret | Không ngăn attacker với process privilege đủ lớn |
| Tránh hex/Base64/String của key | Giảm object, log và bản sao text | Không loại hết secret material nội bộ JCE |
| HSM/KMS non-exportable key | Giảm việc đưa long-term key bytes vào app | Không ngăn service bị lạm dụng để ký/giải mã |
| Disable/redact request logging | Giảm secret trong log/trace | Không tự kiểm soát heap dump/crash artifact |
| Access controls + mã hóa dump | Giảm người có thể đọc snapshot | Không biến snapshot thành dữ liệu công khai an toàn |
| Error codes ổn định | Giảm lộ secret/diagnostic qua public API | Không tự loại timing oracle/rate-limit issues |
| Security tests/log scanning | Phát hiện nhiều đường rò rỉ quan sát được | Không chứng minh tuyệt đối không có bản sao trong RAM |

### 13.1. Nên ưu tiên thế nào?

Nếu có một ngày để cải thiện hệ thống:
1. Ngừng log request headers/body chứa credential, ngừng log raw key/plaintext; rà soát APM/error reporting.
2. Bảo đảm credential, key và decrypted data chỉ được giữ trong scope cần thiết; thêm `finally` để clear mutable buffers.
3. Kiểm tra các API tạo bản sao (`String`, `PBEKeySpec`, `getEncoded()`, stream, serialization).
4. Kiểm soát quyền tạo/download heap dump và chính sách retention.
5. Tách public error khỏi internal diagnostic, giảm oracle trên endpoint nhạy cảm.
6. Đối với khóa lâu dài có tác động lớn, đánh giá non-exportable key/KMS/HSM và điều chỉnh blast radius.

Không nên đầu tư trước vào mẹo sửa nội bộ `String` bằng reflection, pin memory không được hỗ trợ hoặc “trộn byte cho khó đọc” trong khi vẫn công khai key qua logs và stack traces.

## 14. Tình huống thực tế

### Tình huống A — mật khẩu trên REST API

Endpoint nhận password để login. Framework bind JSON field thành `String`. Dev chuyển qua `char[]` và zero sau verify, nhưng middleware đang log request body.

**Kết luận:** mảng caller được xóa không ngăn password bị ghi ra log, cũng không xóa `String` từ parser. Khắc phục ở ingress/logging, hạn chế DTO retention, dùng password-hashing chuẩn, áp rate limit, xem xét API xử lý secret theo framework.

### Tình huống B — mã hóa tài liệu bằng AES-GCM

Service nhận CEK từ KMS, tạo `SecretKeySpec`, xóa byte[] CEK rồi lưu `SecretKeySpec` vào singleton “để tránh gọi KMS nhiều lần”. Trong thời gian đó heap dump được upload lên ticket.

**Kết luận:** CEK có thể còn trong key object và provider; xóa mảng gốc không đủ. Cần cân nhắc phạm vi/lifetime key, kiểm soát dump và cách dùng KMS/DEK; không đăng dump nhạy cảm ra hệ không tin cậy.

### Tình huống C — lỗi giải mã

Server giải mã AES-GCM thất bại và trả `"Tag failed for keyId X with input token Y"` cho client. Debugging trở nên dễ hơn nhưng error phản hồi lộ metadata hoặc secret và có thể phân biệt trạng thái giải mã.

**Kết luận:** public response dùng code tổng quát; internal telemetry ghi correlation ID và nhóm lỗi an toàn, không chèn secret/token. Cần xem xét oracle/timing và rate limit.

### Tình huống D — debug bằng `toString()`

Một class `ApiRequest` sinh `toString()` chứa `authorizationHeader`; khi exception xảy ra, logger ghi toàn request.

**Kết luận:** sửa DTO/toString, serializer, log filters và test bảo đảm bí mật không xuất hiện; tránh dựa riêng vào regex redaction cuối pipeline vì có thể bỏ sót encoding/format.

### Tình huống E — direct `ByteBuffer.clear()`

Một developer gọi `directBuffer.clear()` rồi tin rằng dữ liệu private key đã bị zero. Một native diagnostic vẫn đọc được buffer.

**Kết luận:** `clear()` không xóa nội dung, chỉ reset position/limit. Cần ghi đè vùng nhạy cảm theo API được hỗ trợ và hiểu những bản sao khác; direct memory không phải vault.

### Tình huống F — mật khẩu có trong stack trace

`InvalidCredentialsException("password="+p)` được ném ở tầng auth; global handler in `exception.printStackTrace()` rồi trả 500.

**Kết luận:** secret đã được nhúng trong message ngay khi tạo exception. Chỉ dùng mã lỗi an toàn, tránh secret trong exception object, kiểm soát logging/cause/response và áp chính sách auth thống nhất.

### Tình huống G — khóa private trong HSM

Java nhận handle `PrivateKey` non-exportable, ký qua provider. App không nhìn thấy raw private key, nhưng vẫn có quyền gửi dữ liệu tới ký.

**Kết luận:** giảm leak của private-key material, nhưng phải ràng buộc quyền ký, nội dung/format ký, rate, tenant, audit và phát hiện lạm dụng. Trộm quyền gọi ký cũng rất nguy hiểm dù không export được key.

## 15. Kiểm thử bảo mật và vận hành có thể chứng minh điều gì?

### 15.1. Unit tests

- Đặt dữ liệu secret giả/fixture, gọi code đúng/sai; assert secret không xuất hiện trong exception message và public response.
- Dùng log-capture test để khẳng định một số đường lỗi không log password/token/khóa giả.
- Kiểm tra cleanup trong `finally` khi API throw.
- Kiểm tra `PBEKeySpec.clearPassword()` sau derive và việc xóa derived buffer do caller sở hữu.
- Kiểm tra DTO `toString()` không in các field nhạy cảm.
- Kiểm tra các phương thức base64/hex serialization chỉ xử lý dữ liệu được phép công bố.

### 15.2. Integration/security tests

- Giả lập HTTP pipeline có proxy, access logging, exception handler, APM instrumentation; tìm marker giả trong log/trace/metrics.
- Gây lỗi mật mã có kiểm soát như sai tag và sai credential; đảm bảo public error không tiết lộ nguyên nhân nhạy cảm, internal logs không chứa secret.
- Kiểm thử quyền tạo/download heap dump theo vai trò vận hành.
- Kiểm tra dump staging bằng marker **không phải secret thật** nếu được phê duyệt; chú ý một snapshot không có marker **không chứng minh** không thể leak ở thời điểm khác.
- Kiểm tra cấu hình container/runtime, core dump/heap dump upload/retention trong CI và production.
- Kiểm tra rotation/revocation nếu nghi ngờ secret xuất hiện trong artifact không an toàn.

### 15.3. Security QA không thể kết luận tuyệt đối

Một unit test cho thấy `byte[]` bằng zero không chứng minh:
- Không có key trong JIT register/stack/native heap.
- Không có `String` được framework tạo trước đó.
- Không có APM hoặc crash dump giữ snapshot cũ.
- Không có secret đã bị log sang server trung tâm.
- Không có copy nằm trong backing buffer của thư viện.

Do đó, báo cáo nên dùng ngôn ngữ chính xác: **“caller-owned buffer cleared”, “public error sanitized”, “no secret found in tested log paths”** thay vì “all secrets permanently erased from RAM”.

## 16. Checklist review code cho một khóa hoặc mật khẩu

### Input / representation
- [ ] Secret đến từ nguồn/truyền tải đã xác thực, không hardcode trong source.
- [ ] Dùng container mutable theo API phù hợp khi cần zeroization; tránh tạo `String` không cần thiết.
- [ ] Không chuyển khóa sang hex/Base64/debug text trừ khi bắt buộc bởi wire format và được bảo vệ.
- [ ] Có giới hạn độ dài input và quy tắc parse để tránh tạo object/bản sao không kiểm soát.

### Usage / lifetime
- [ ] Lifetime của `byte[]`, `char[]`, `SecretKey`, `PBEKeySpec`, `Cipher/Mac` và provider session được ghi nhận.
- [ ] Cleanup nằm trong `finally` hoặc lifecycle đúng API; có xử lý đường exception.
- [ ] Nếu gọi `getEncoded()` hoặc tạo bản copy, caller quản lý/xóa output thích hợp.
- [ ] Key không bị giữ lâu trong static field, cache hoặc DTO mà không có lý do và chính sách.
- [ ] Có ràng buộc IAM/authorization cho việc dùng key và nguyên tắc least privilege.
- [ ] Nếu KMS/HSM, hiểu rõ dữ liệu nào vẫn được đưa vào Java heap và những key nào không exportable.

### Observability / errors
- [ ] Không log `Authorization`, `Cookie`, password, private key, CEK/DEK hoặc plaintext nhạy cảm.
- [ ] `toString()`, JSON serialization và exception message đã được rà soát.
- [ ] Public error dùng mã lỗi phù hợp, không echo secret/provider diagnostics.
- [ ] Trace/APM/metrics/coredump/heap dump không vô tình thu secret.
- [ ] Có rate limiting và đánh giá padding/tag/timing oracle trên API crypto công khai.

### Operations / incidents
- [ ] Quyền debugger/profiler/dump chỉ dành cho người/công cụ được cấp phép.
- [ ] Dump/log có encryption, access audit, storage policy và retention/xóa phù hợp.
- [ ] Có kịch bản rotate/revoke key/token nếu artifact nhạy cảm bị lộ.
- [ ] Incident response bao gồm log backups, object stores, tickets, telemetry vendors, máy developer và tài khoản hỗ trợ.
- [ ] Kiểm thử bằng fixture/canary giả, không tự ý đưa production secret vào test.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Gán `secretString = null` có bảo đảm mật khẩu đã bị xóa khỏi heap chưa?

**Đáp án:** Không. Chỉ bỏ tham chiếu; `String` bất biến, GC quản lý thu hồi và có thể có nhiều bản sao khác.

**Câu 2.** Nếu gọi `Arrays.fill(keyBytes, (byte)0)` ngay sau tạo `SecretKeySpec(keyBytes,"AES")`, khóa trong `SecretKeySpec` có chắc bị xóa không?

**Đáp án:** Không. `SecretKeySpec` giữ key material riêng theo API; khóa vẫn có thể dùng. Phải quản lý lifetime/key provider và không kết luận xóa mọi bản sao.

**Câu 3.** Sau khi gọi `spec.clearPassword()` trên `PBEKeySpec`, còn có thể gọi `spec.getPassword()` không?

**Đáp án:** Không theo hợp đồng API; việc truy cập bị từ chối. Điều đó không nói mọi bản sao password khác đều đã biến mất.

**Câu 4.** Vì sao dùng `ByteBuffer.clear()` không phải zeroization?

**Đáp án:** Nó chỉ thiết lập lại position/limit, không ghi zero vào vùng dữ liệu.

**Câu 5.** Heap dump được chụp trước khi ứng dụng zero byte[]; sau đó ứng dụng zero thành công. Dump có tự an toàn không?

**Đáp án:** Không. Snapshot cũ có thể giữ dữ liệu như lúc chụp. Phải bảo vệ artifact bằng access, encryption, retention và incident process.

**Câu 6.** Có nên trả `"AES tag invalid, unwrap RSA successful"` cho caller không xác thực?

**Đáp án:** Tránh làm vậy; thông điệp có thể tạo oracle và lộ trạng thái xử lý. Dùng public error được thiết kế theo threat model, internal diagnostic an toàn và rate limits.

**Câu 7.** Dùng HSM non-exportable private key có nghĩa plaintext không bao giờ đi qua Java heap?

**Đáp án:** Không. Nó giới hạn đường xuất private key cụ thể; plaintext/hashed input/output và các key khác vẫn có thể xuất hiện trong process tùy thiết kế.

**Câu 8.** Một unit test không tìm thấy key giả trong dump staging có chứng minh production không bao giờ leak secret?

**Đáp án:** Không. Dump chỉ là một snapshot; GC, thời điểm và data flow khác có thể làm thay đổi kết quả. Cần threat model, kiểm thử nhiều tầng và vận hành tốt.

**Câu 9.** Tại sao không nên đưa access token vào log, dù log chỉ được đọc bởi nhân viên nội bộ?

**Đáp án:** Token có thể là bearer credential. Log có nhiều bản sao, retention, tài khoản đọc và đường export; lộ log có thể tương đương lộ quyền truy cập token.

**Câu 10.** Lý do chính để dùng `finally` khi xử lý secret mutable?

**Đáp án:** Đảm bảo logic cleanup của caller chạy cả khi thao tác mật mã/parse/IO throw, giảm thời gian buffer do caller sở hữu chứa secret.

**Câu 11.** Secret đã được mã hóa ở database có thể xuất hiện dưới dạng plaintext trong memory dump không?

**Đáp án:** Có, nếu app giải mã để xử lý rồi giữ plaintext trong heap hoặc native buffer. Encryption at rest không đồng nghĩa mã hóa trong memory của ứng dụng đang sử dụng dữ liệu.

**Câu 12.** Câu nào chính xác hơn: “đã xóa hết password khỏi RAM” hay “đã zero caller char[] và clear PBEKeySpec theo API”?

**Đáp án:** Câu thứ hai kiểm chứng được và giới hạn rõ đối tượng; câu thứ nhất vượt quá bảo đảm của Java managed memory.

## 18. Sơ đồ ghi nhớ

```text
                 SECRET / PASSWORD / KEY
                           |
              +------------+-------------+
              |                          |
          Representations             Infrastructure
          byte[]  char[]              HTTP, logs, APM
          String  objects             heap, crash dumps
          KeySpec provider            debugger, backups
              |                          |
       Limit copies/lifetime         Access control
       Avoid String/logging          Encrypt / retain / audit
       finally + clear own arrays    Secure diagnostic path
              |                          |
              +------------+-------------+
                           |
                  NO ABSOLUTE ZEROIZATION
                  CLAIM FOR ENTIRE JVM
                           |
             Use purpose-bound keys, KMS/HSM
             where appropriate, safe errors,
             least privilege and incident response
```

**Kết luận:** Trong Java, `byte[]` và `char[]` cho phép giảm thời gian tồn tại của dữ liệu **ở đúng mảng mà ứng dụng sở hữu**; `String` không có API xóa nội dung trực tiếp; `SecretKeySpec`, `PBEKeySpec`, provider và các framework có thể tạo bản sao. Heap dump, profiler, log, trace và exception có thể đưa secret ra khỏi vòng đời dự kiến. Một hệ thống an toàn không tuyên bố “RAM đã sạch tuyệt đối”, mà thiết kế **giảm sao chép, giới hạn quyền và lifetime, có cleanup best-effort, bảo vệ diagnostic artifacts, trả lỗi không lộ secret và lập kế hoạch thay khóa khi sự cố xảy ra**.

### Tài liệu tham khảo

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Arrays.fill`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html
- Java SE 17, `PBEKeySpec` và `clearPassword()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html
- Java SE 17, `SecretKeySpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html
- Java SE 17, `SecretKeyFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html
- Java SE 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, `Console.readPassword()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html
- Java SE 17, `Destroyable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html
- OWASP, *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP, *Secrets Management Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP, *Error Handling Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html

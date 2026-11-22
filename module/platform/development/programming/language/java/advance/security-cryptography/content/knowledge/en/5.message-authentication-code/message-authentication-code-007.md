# 5.7. Phân biệt xác thực thông điệp với chống phát lại bằng nonce hoặc số thứ tự

Trong giao thức trao đổi thông điệp, **xác thực (authentication)** trả lời câu hỏi “Thông điệp này có được tạo bởi bên nắm đúng khóa/định danh và còn nguyên vẹn không?”, còn **chống phát lại (anti-replay)** trả lời câu hỏi khác: “Một thông điệp hợp lệ như thế này **đã được chấp nhận trước đó** hoặc đã quá hạn chưa?”. Một thông điệp có HMAC hoặc chữ ký **đúng hoàn toàn vẫn có thể là thông điệp cũ bị gửi lại**. Đây là lý do hệ thống thanh toán, API thao tác trạng thái, webhook và giao thức trao đổi khóa thường cần thêm **nonce, số thứ tự, timestamp và trạng thái phía nhận**.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt kiểm tra nguồn gốc/tính toàn vẹn bằng **MAC, chữ ký số hoặc AEAD** với kiểm tra **freshness**, thứ tự và việc sử dụng một lần.
2. Mô tả một cuộc tấn công replay mà HMAC vẫn hợp lệ; giải thích vì sao hash thuần túy và timestamp đơn lẻ không thay được cơ chế chống phát lại.
3. Chọn giữa **nonce ngẫu nhiên/challenge** và **sequence number** theo yêu cầu truyền thông, thứ tự, đồng bộ trạng thái và khả năng retry.
4. Thiết kế dữ liệu bắt buộc phải được xác thực, replay cache/counter, giới hạn thời gian, và thao tác ghi trạng thái **atomic** trên nhiều máy chủ.
5. Viết và chạy ví dụ **Java 21** dùng `Mac`/HmacSHA256, `SecureRandom`, `MessageDigest.isEqual` và một replay set minh họa; hiểu chính xác giới hạn của ví dụ.

## 1. Hai thuộc tính bảo mật độc lập

Giả sử client hợp lệ gửi lệnh:

```text
POST /transfers
{"to":"Bob","amount":100}
timestamp = 1700000000
nonce = N1
tag = HMAC(secret, method | path | body | timestamp | nonce)
```

Server kiểm tra HMAC thành công và chuyển 100 đơn vị. Kẻ tấn công thu lại nguyên gói đã ký rồi gửi y hệt gói đó lần thứ hai. Vì **byte dữ liệu và tag không thay đổi**, HMAC lần hai vẫn đúng. Nếu server không nhớ `N1` đã dùng, lệnh chuyển tiền có thể được thực hiện lại.

| Thuộc tính/cơ chế | Chứng minh hoặc bảo vệ điều gì? | Tự ngăn replay? |
| --- | --- | --- |
| Hash không khóa, ví dụ SHA-256 | Phát hiện thay đổi khi có nguồn hash đáng tin để so sánh; tự nó không xác thực người gửi | Không |
| MAC/HMAC với khóa bí mật dùng chung | Tính toàn vẹn và chứng minh bên tạo tag biết khóa MAC | **Không** |
| Chữ ký số được xác minh bằng public key phù hợp | Tính toàn vẹn và nguồn gốc gắn với private key; kết quả còn phụ thuộc cách xác thực public key | **Không** |
| AEAD, ví dụ AES-GCM | Bí mật + toàn vẹn/xác thực bản mã và AAD đã chọn | **Không tự động** ở tầng thông điệp ứng dụng |
| Timestamp được xác thực | Giới hạn tuổi thọ/giai đoạn hợp lệ của thông điệp | Không ngăn gửi lại **trong cửa sổ** |
| Nonce đã xác thực **và** kiểm tra dùng một lần | Phát hiện cùng nonce đã được server chấp nhận | Có, trong phạm vi và thời gian lưu trạng thái |
| Sequence number đã xác thực **và** lưu trạng thái nhận | Phát hiện số thứ tự cũ hoặc trùng, tùy quy tắc và cửa sổ | Có, với quy tắc nhận phù hợp |

**Điểm mấu chốt:** tính hợp lệ về mật mã là điều kiện để tin dữ liệu đến từ bên giữ khóa; **tính mới** là ràng buộc bổ sung cần quy tắc giao thức và bộ nhớ của phía nhận. Chỉ sinh nonce rồi bỏ qua nó, hoặc đưa nonce vào header nhưng không đưa vào dữ liệu được HMAC/ký, sẽ không tạo ra bảo vệ chống replay.

### Điều mà anti-replay không hứa hẹn

Nếu kẻ tấn công lấy được một yêu cầu hợp lệ **trước khi** server chấp nhận nó, kẻ đó có thể gửi yêu cầu trước client thật. Hệ thống chống replay có thể bảo đảm **chỉ một yêu cầu được chấp nhận**, nhưng không biết bản nào là “bản gốc” trên mạng. TLS, bảo vệ khóa, xác thực kênh, ràng buộc phiên và các biện pháp giao thức khác vẫn cần thiết. Nếu kẻ tấn công **biết khóa HMAC/private key** và tự tạo thông điệp mới hợp lệ, chặn các nonce trùng cũng không ngăn được việc giả mạo đó.

## 2. Nonce: giá trị riêng cho mỗi yêu cầu

**Nonce** (*number used once*) là giá trị mà giao thức yêu cầu chỉ sử dụng một lần **trong một phạm vi xác định**, ví dụ cho mỗi định danh client + khóa + phiên. Nonce có thể được client sinh ngẫu nhiên hoặc server cấp dưới dạng challenge.

### 2.1 Nonce ngẫu nhiên do client sinh

Quy trình phổ biến cho HTTP API:

1. Client dùng bộ sinh số ngẫu nhiên mật mã (`SecureRandom`), tạo nonce đủ dài, chẳng hạn **128 bit = 16 byte** ngẫu nhiên.
2. Client gửi `clientId/keyId`, thao tác, payload, timestamp và nonce; **MAC/chữ ký phải bao phủ tất cả trường ảnh hưởng đến ý nghĩa thao tác**, nhất là nonce và timestamp.
3. Server xác định khóa theo định danh đã được kiểm soát, xác minh tag, kiểm tra timestamp, rồi tra **replay store** cho nonce trong phạm vi của định danh/khóa.
4. Server **ghi nhận nonce một cách nguyên tử** trước hoặc cùng lúc commit thao tác nghiệp vụ. Nếu nonce đã tồn tại, server từ chối hoặc trả lại kết quả của yêu cầu đã xử lý theo chính sách idempotency.
5. Server giữ bản ghi đủ lâu để một thông điệp cũ không trở lại hợp lệ sau khi record hết hạn.

Nonce ngẫu nhiên có xác suất va chạm rất nhỏ khi sinh đúng, nhưng **tính ngẫu nhiên chỉ làm giảm nguy cơ hai yêu cầu hợp lệ tự chọn cùng nonce**. Kẻ tấn công phát lại cố tình dùng **chính nonce cũ**, vì vậy server phải lưu và kiểm tra việc đã dùng.

### 2.2 Nonce do server cấp (challenge–response)

Trong một số giao thức, server tạo một challenge ngắn hạn, gắn với client/phiên, hành động và thời điểm hết hạn; client ký/MAC cả challenge và yêu cầu; server **đánh dấu challenge đã dùng một lần** khi xác thực. Giải pháp này cho server quyền kiểm soát vòng đời của nonce. Đổi lại, cần thêm lượt giao tiếp và bộ nhớ trạng thái challenge. Một challenge chỉ có giá trị trong phạm vi được cấp; không dùng challenge của phiên/đích này để hợp thức hóa thao tác khác.

### 2.3 Nonce + timestamp: vai trò khác nhau

- **Nonce + replay store:** bắt được cùng yêu cầu được gửi lại.
- **Timestamp đã xác thực:** giới hạn thời gian kiểm tra và thời gian cần giữ record.
- **Chỉ timestamp:** một gói ký hợp lệ có thể được phát lại nhiều lần trong cửa sổ vài phút.
- **Chỉ nonce nhưng không giữ trạng thái:** không phát hiện được việc sử dụng lại.
- **Nonce đặt ngoài MAC/chữ ký:** kẻ tấn công có thể sửa nonce rồi phát lại tag của nội dung khác; cách bố trí này sai thiết kế.

Ví dụ chính sách: chấp nhận `issuedAt` từ **5 phút trước** đến **30 giây trong tương lai** để chịu lệch đồng hồ đã được cân nhắc. Đó là chính sách minh họa, không phải tham số áp dụng máy móc cho mọi hệ thống. Nếu server nhận thông điệp với timestamp tương lai +30 giây, record nonce phải tồn tại ít nhất đến khi thông điệp **không còn hợp lệ** (ví dụ `issuedAt + 300 giây` cộng biên an toàn), chứ không chỉ xóa sau 300 giây tính từ lần nhận. Cần đồng bộ đồng hồ, theo dõi chênh lệch và giới hạn kích thước replay cache.

### 2.4 Phạm vi khóa tra cứu replay

Với nhiều tenant/khóa, lưu khóa replay theo dạng có ranh giới rõ, chẳng hạn:

```text
replayKey = protocolVersion | verifiedClientId | keyId | nonce
```

`verifiedClientId` phải là danh tính đã được xác thực hoặc ràng buộc bằng khóa, không phải chuỗi header do client tự nhận không kiểm tra. Nếu một nonce chỉ được bảo đảm duy nhất trong **từng phiên**, thêm session/epoch vào phạm vi; nếu yêu cầu bảo đảm dùng một lần **trên mọi endpoint** của cùng một khóa, đừng lưu replay cache tách rời từng endpoint. Định nghĩa phạm vi trước khi viết hệ thống.

## 3. Sequence number: số thứ tự có trạng thái

Sequence number (counter) là số tăng dần theo **mỗi sender, key hoặc session**, và bản thân counter cũng phải nằm trong dữ liệu được MAC/ký. Server ghi nhớ giá trị cuối hoặc một cửa sổ các giá trị đã thấy.

### 3.1 Chấp nhận tăng nghiêm ngặt

Giả sử server lưu `lastAccepted = 40`:

- Nhận số **41** với tag hợp lệ → chấp nhận và cập nhật `lastAccepted = 41`.
- Nhận lại **41** → từ chối trùng.
- Nhận **39** → từ chối cũ.
- Nhận **43** trước **42** → có thể chấp nhận 43 nếu quy tắc là `seq > lastAccepted`; sau đó 42 bị coi là cũ. Nếu quy tắc là `seq = lastAccepted + 1`, phải đợi 42 hoặc dùng cơ chế tái sắp xếp.

Phải chọn rõ giao thức yêu cầu **thứ tự tuyệt đối**, **chỉ chống số cũ/trùng**, hay **cho phép lệch thứ tự**. Counter chỉ tăng không tự giải quyết tính hoàn tất của những lệnh bị mất.

Với client có nhiều luồng/thiết bị, một counter chung có thể trở thành nút thắt hoặc gây out-of-order. Thông thường cần counter riêng cho mỗi **security association/session**, hoặc nonce ngẫu nhiên nếu thao tác độc lập và không đòi thứ tự. Counter phải được quản lý bền vững và không được reset thành giá trị cũ khi ứng dụng khởi động lại, trừ khi bắt đầu **epoch/phiên mới** được xác thực.

### 3.2 Sliding window cho thông điệp đến lệch thứ tự

Một lựa chọn cho datagram/stream đến lệch thứ tự là lưu `highestSeen` cùng bitmap các sequence vừa đi qua:

```text
highestSeen = 100; windowSize = 64
Cửa sổ xét: 37..100

seq = 98, bit 98 chưa có -> chấp nhận, đánh dấu 98
seq = 98 lần nữa          -> từ chối vì bit đã đánh dấu
seq = 36                  -> từ chối vì ngoài cửa sổ
seq = 101, tag hợp lệ      -> dịch cửa sổ và đánh dấu 101
```

Đây là **mô tả thuật toán**, chưa phải mã triển khai. Khi shift bitmap phải xử lý đúng overflow, giá trị đầu phiên, reset/rotate khóa, chuyển epoch, số thứ tự lớn hơn nhiều lần kích thước cửa sổ và truy cập đồng thời. Với HTTP API có yêu cầu tài chính, nonce + record nghiệp vụ có thể dễ kiểm toán hơn bitmap cửa sổ.

### 3.3 So sánh nonce và sequence number

| Tiêu chí | Nonce ngẫu nhiên + cache | Counter / sequence number |
| --- | --- | --- |
| Cần sinh dữ liệu mới | `SecureRandom` hoặc server challenge | Counter tăng với mỗi thông điệp |
| Trạng thái phía nhận | Tập nonce đã chấp nhận và TTL/phạm vi | High-watermark, có thể thêm bitmap cửa sổ |
| Gói đến lệch thứ tự | Có thể chấp nhận nếu nonce mới và timestamp hợp lệ | Cần thiết kế cửa sổ hoặc xử lý reorder |
| Client gửi song song | Tự nhiên nếu nonce độc lập | Phải cấp số tránh trùng và điều phối thứ tự |
| Khôi phục sau restart | Persist/cache dùng chung đủ lâu | Persist counter, bảo vệ reset/epoch |
| Hợp với | API request độc lập, webhook, challenge–response | Kênh có thứ tự, giao thức packet/session |
| Lỗi điển hình | Cache riêng mỗi node; TTL quá ngắn; nonce không ký | Counter reset; nhảy số; race cập nhật; drop gói hợp lệ |

Cả hai phương án đều phải chống **thao tác đồng thời**: hai request cùng nonce/sequence tới hai worker khác nhau chỉ được một worker nhận. Các phép “kiểm tra rồi ghi” tách rời là không an toàn.

## 4. Những trường phải được xác thực cùng thông điệp

Tối thiểu, khi sử dụng HMAC hoặc chữ ký cho một thao tác thay đổi trạng thái, bên ký và bên xác minh phải thống nhất **chính xác byte được ký**:

- Phiên bản giao thức và mục đích sử dụng (*domain separation*), ví dụ `payment-v1`.
- Danh tính sender đã ràng buộc với khóa, `keyId`/phiên nếu có; service/tenant/đích nhận để tránh chuyển tiếp chữ ký qua miền tin cậy khác (*cross-context replay*).
- HTTP method, tài nguyên/path, các tham số query hoặc phần message quyết định thao tác.
- Payload dưới một quy ước mã hóa xác định (body bytes, hoặc digest đã được bao phủ bởi chữ ký/MAC theo giao thức).
- Nonce hay sequence number, timestamp, expiration hoặc window khi được dùng.

Không nối chuỗi tùy tiện như `"AB" + "C"` và `"A" + "BC"` vì có thể tạo cùng byte. Dùng length-prefix, encoding nhị phân có định dạng, hoặc quy tắc canonicalization được định nghĩa và kiểm thử cho **cả hai đầu**. JSON có thứ tự field, khoảng trắng và cách biểu diễn số khác nhau; nếu phải ký JSON, cần quy ước canonical JSON hoặc ký nguyên byte body thực nhận. Phải xem ảnh hưởng của proxy, URL normalization và header được phép sửa theo giao thức.

**Sai phổ biến:** ký body mà bỏ method/path dẫn đến chữ ký của một body có thể được gắn sang endpoint khác; ký body và timestamp nhưng bỏ nonce khiến nonce không được bảo vệ; dùng cùng một khóa/MAC format cho nhiều loại thông điệp mà không có trường phiên bản/mục đích làm tăng nguy cơ nhầm ngữ cảnh.

## 5. Thực hành Java 21: HMAC đúng nhưng replay bị từ chối

Ví dụ dưới đây mô phỏng **một client và một server cùng chia sẻ khóa HMAC**, một process, thời gian cố định để có stdout ổn định. Nó minh họa ba phép kiểm: **tag đúng**, **timestamp trong cửa sổ**, **nonce chưa dùng**. Dữ liệu thật cần ánh xạ `clientId` sang khóa riêng, replay store chia sẻ/persist và xử lý nghiệp vụ có giao dịch; phần 7 trình bày.

Tạo đúng file **`ReplayDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class ReplayDemo {
    record Request(String method, String path, String body,
                   long issuedAt, String nonce, String tag) {}

    // Mỗi trường có length-prefix; tránh nhập nhằng khi ghép chuỗi.
    static void field(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    // Tag không được ký lại chính nó. Mọi trường có ý nghĩa đều được ký.
    static byte[] signedBytes(Request request) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        field(out, "replay-demo-v1");
        field(out, request.method());
        field(out, request.path());
        field(out, request.body());
        out.writeLong(request.issuedAt());
        field(out, request.nonce());
        out.flush();
        return buffer.toByteArray();
    }

    static byte[] hmac(SecretKey key, Request request) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(signedBytes(request));
    }

    static Request sign(SecretKey key, String body, long issuedAt)
            throws Exception {
        byte[] random = new byte[16];       // Nonce 128 bit.
        new SecureRandom().nextBytes(random);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(random);
        Request unsigned = new Request(
                "POST", "/payments", body, issuedAt, nonce, "");
        String tag = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(key, unsigned));
        return new Request(unsigned.method(), unsigned.path(),
                unsigned.body(), unsigned.issuedAt(), nonce, tag);
    }

    static boolean verify(SecretKey key, Request request,
                          long now, Set<String> usedNonces)
            throws Exception {
        // Cửa sổ minh họa: tối đa 300 giây cũ, 30 giây tương lai.
        if (request.issuedAt() < now - 300 || request.issuedAt() > now + 30) {
            return false;
        }
        byte[] suppliedTag;
        try {
            suppliedTag = Base64.getUrlDecoder().decode(request.tag());
        } catch (IllegalArgumentException ex) {
            return false;
        }
        // Kiểm tra MAC TRƯỚC khi chiếm nonce trong replay store.
        if (!MessageDigest.isEqual(hmac(key, request), suppliedTag)) {
            return false;
        }
        // Atomic trong một JVM: chỉ lần thêm nonce đầu tiên trả true.
        return usedNonces.add(request.nonce());
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        SecretKey sharedKey = generator.generateKey();
        Set<String> usedNonces = ConcurrentHashMap.newKeySet();
        long now = 1_700_000_000L; // Thời gian giả lập để test ổn định.

        Request first = sign(sharedKey, "{\"amount\":100}", now);
        System.out.println("new request: " +
                verify(sharedKey, first, now, usedNonces));
        System.out.println("exact replay: " +
                verify(sharedKey, first, now, usedNonces));

        Request modified = new Request(first.method(), first.path(),
                "{\"amount\":900}", first.issuedAt(),
                first.nonce(), first.tag());
        System.out.println("tampered body: " +
                verify(sharedKey, modified, now, usedNonces));

        Request expired = sign(sharedKey, "{\"amount\":100}", now - 301);
        System.out.println("stale request: " +
                verify(sharedKey, expired, now, usedNonces));
    }
}
```

Biên dịch và chạy bằng **JDK 21 hoặc compiler mới hơn có hỗ trợ `--release 21`**:

```text
javac -version
mkdir out
javac --release 21 -encoding UTF-8 -d out ReplayDemo.java
java -cp out ReplayDemo
```

Stdout từ chương trình (các nonce và khóa ngẫu nhiên **không** được in nên kết quả ổn định):

```text
new request: true
exact replay: false
tampered body: false
stale request: false
```

### Tại sao kết quả như vậy?

1. **New request = true:** tag đúng, timestamp trong cửa sổ, và `usedNonces.add(nonce)` thêm nonce lần đầu.
2. **Exact replay = false:** payload và HMAC vẫn đúng, nhưng `add` trên nonce đã tồn tại trả `false`. Đây là phần **anti-replay** mà HMAC một mình không cung cấp.
3. **Tampered body = false:** đối tượng giữ tag cũ trong khi `body` đã đổi; xác minh HMAC thất bại ngay trước khi xem replay set.
4. **Stale request = false:** request mới có tag đúng và nonce mới, nhưng timestamp quá cũ 301 giây nên bị từ chối.
5. `MessageDigest.isEqual` là API chuẩn để so sánh byte tag thay vì tự viết vòng lặp dừng ngay tại byte khác; xác minh vẫn phải giới hạn độ dài/định dạng đầu vào và tránh lộ thông tin lỗi nhạy cảm.

### Giới hạn có chủ ý của chương trình

- `ConcurrentHashMap.newKeySet()` có thao tác `add` atomic **trong một JVM**; dữ liệu mất khi process restart, không chia sẻ giữa server node và không có TTL. Đây là **demo**, chưa phải anti-replay triển khai production.
- `now` cố định chỉ để bài thực hành có kết quả lặp lại. Hệ thống thật dùng đồng hồ kiểm soát được (ví dụ `Clock` UTC được inject để test) và chính sách hết hạn/tolerance thích hợp.
- Khóa sinh tạm bằng `KeyGenerator`. Hệ thống thật cấp khóa cho mỗi principal theo quy trình quản lý khóa/KMS/keystore, lưu bí mật an toàn, hỗ trợ luân chuyển và không nhúng khóa thực vào source code/log.
- Demo dùng `String body`. Một HTTP service cần ký đúng **byte payload nhận được** hoặc canonical form đã định nghĩa, kiểm tra method/path/headers cần thiết và ràng buộc principal đã xác thực.
- Demo chưa thực thi nghiệp vụ, không có response idempotency và không giải quyết race giữa replay store với database. Không dùng hàm `verify` đơn lẻ này để bảo đảm giao dịch tài chính.
- Một request mới với **nonce mới** và body giống hệt request cũ có thể được chấp nhận: đó có thể là thao tác mới hợp lệ. Nếu nghiệp vụ yêu cầu “một đơn hàng chỉ bị trừ tiền một lần”, cần thêm **idempotency key/mã nghiệp vụ**.

## 6. Nếu chọn sequence number: quy tắc cập nhật phải atomic

Với giao thức chấp nhận mọi `seq > lastAccepted` và không cho replay, có thể biểu diễn khái niệm cập nhật trong một process bằng `AtomicLong`. **Chỉ chạy bước này sau khi xác minh tag bao gồm `seq` và đã xác định sender/session**:

```java
import java.util.concurrent.atomic.AtomicLong;

public class SequenceGate {
    private final AtomicLong lastAccepted = new AtomicLong(0);

    // Precondition: MAC/signature chứa seq đã được xác minh.
    public boolean accept(long seq) {
        while (true) {
            long last = lastAccepted.get();
            if (seq <= last) {
                return false;
            }
            if (lastAccepted.compareAndSet(last, seq)) {
                return true;
            }
        }
    }

    public static void main(String[] args) {
        SequenceGate gate = new SequenceGate();
        System.out.println(gate.accept(41));
        System.out.println(gate.accept(41));
        System.out.println(gate.accept(40));
        System.out.println(gate.accept(42));
    }
}
```

```text
javac --release 21 SequenceGate.java
java SequenceGate
```

```text
true
false
false
true
```

Ví dụ này là **gate in-memory** với một sender; do không xác minh MAC ở đây, không được gọi trực tiếp trên dữ liệu chưa được xác thực. Nó không đảm bảo thứ tự liên tiếp, không chấp nhận gói đến muộn sau một seq lớn hơn, và mất watermark khi restart. Với sản phẩm thật, lưu **(verified principal, key/session epoch, lastAccepted)** bằng compare-and-swap trong dữ liệu bền vững hoặc transaction có khóa; nếu cần out-of-order, dùng thuật toán sliding window được kiểm thử.

## 7. Thiết kế server thật: xác thực, chống replay và nghiệp vụ

Một pipeline thực tế có thể đi theo các bước:

```text
Nhận request
   |
   v
Parse có giới hạn kích thước, xác định keyId và principal
   |
   v
Lấy khóa từ registry đáng tin + kiểm tra quyền và bối cảnh
   |
   v
Tái tạo đúng bytes phải ký; xác minh HMAC/chữ ký
   | sai --> Reject
   v
Kiểm tra timestamp/expiry, nonce/seq, session/audience
   | sai --> Reject
   v
Giao dịch atomic: claim nonce/seq + xử lý một thao tác nghiệp vụ
   | duplicate --> Reject hoặc trả kết quả idempotent đã lưu
   v
Commit và trả response
```

Ở đây `claim` là thao tác **kiểm tra và ghi** replay key/counter nguyên tử: chỉ một request có cùng replay identity có thể giành được quyền xử lý, kể cả khi có nhiều server chạy đồng thời.

### 7.1 Ví dụ thiết kế dữ liệu cho nonce

Một bảng replay guard có thể dùng unique key:

```sql
CREATE TABLE replay_guard (
    principal_id  VARCHAR(128) NOT NULL,
    key_id        VARCHAR(128) NOT NULL,
    nonce         VARCHAR(128) NOT NULL,
    expires_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (principal_id, key_id, nonce)
);
```

Khi request đã xác thực, mở transaction và thử `INSERT` một record; xung đột unique key nghĩa là nonce đã dùng. Trong **cùng ranh giới transaction**, ghi nhận trạng thái/kết quả và thay đổi nghiệp vụ cần bảo đảm một lần. Commit thành công mới coi request đã được chấp nhận bền vững. Với database khác, cú pháp UPSERT/transaction khác nhau nhưng ý nghĩa phải tương đương. Mã SQL trên thể hiện **schema**, không phải quy trình transaction hoàn chỉnh; production cần giới hạn input, kiểm soát quyền DB, cleanup theo expiry và xử lý lỗi cạnh tranh.

**Không dùng mẫu sai:**

```text
if (!replayStore.contains(key)) {
    businessAction();
    replayStore.put(key);
}
```

Hai luồng có thể cùng thấy “chưa tồn tại” rồi cùng chạy `businessAction()`. `SELECT` rồi `INSERT` tách rời không được bảo vệ bằng khóa/transaction cũng gặp race tương tự.

**Lưu ý lỗi giữa các bước:** nếu chiếm nonce ở Redis bằng `SET NX` rồi business transaction thất bại, client có thể không retry được dù chưa có hiệu ứng nghiệp vụ. Nếu business đã commit nhưng lưu nonce thất bại, có nguy cơ thực hiện lại. Thiết kế trạng thái `processing/succeeded/failed`, unique operation ID, response cache hoặc transaction chung để đạt ngữ nghĩa phù hợp. “Chỉ chấp nhận một lần” không đồng nghĩa “bảo đảm xử lý thành công đúng một lần”.

### 7.2 Đồng bộ nhiều server và TTL

- Mọi node xử lý cùng principal/phạm vi replay phải dùng **một nguồn trạng thái nhất quán**, ví dụ unique constraint trong DB hoặc thao tác atomic của shared store được thiết kế để chịu mất node/failover.
- TTL phải kéo dài **ít nhất đến thời điểm request không còn vượt qua điều kiện freshness**, có biên an toàn cho clock skew, replication và xử lý chậm. Không cho phép record bị xóa trong khi chính request đó vẫn nằm trong validity window.
- Giới hạn số request/nonce theo client, độ dài chuỗi và tốc độ gửi; nếu không, replay store có thể bị lợi dụng để làm cạn tài nguyên. Chỉ ghi nonce **sau khi xác thực thành công** để tránh yêu cầu rác chưa ký lấp bộ nhớ.
- Khi rotate key hoặc reset sequence, định nghĩa rõ `keyId`, epoch, yêu cầu xác thực và thời gian tồn tại của trạng thái cũ; không vô tình mở lại cửa cho thông điệp cũ.
- Lưu log theo event type, principal và request ID; hạn chế log khóa bí mật, raw token, bản rõ dữ liệu nhạy cảm hoặc toàn bộ MAC.

## 8. Replay, retry và idempotency là ba bài toán có liên quan

**Replay độc hại:** bên thứ ba phát lại gói hợp lệ để gây hiệu ứng phụ lặp. **Retry hợp lệ:** client gửi lại khi timeout vì không biết server đã thực hiện chưa. **Idempotency:** nhiều lần gọi cùng *logical operation* chỉ tạo ra một tác động nghiệp vụ theo quy tắc đã định.

Ví dụ client thanh toán gửi operation ID `order-123` với nonce `N1`. Server xử lý xong nhưng response bị mất; client gửi lại **chính request cũ**. Replay guard sẽ từ chối nonce `N1`, nhưng để hỗ trợ retry tốt, server có thể trả lại **response đã lưu** của `order-123` mà không thực hiện chuyển tiền lần hai. Nếu client gửi lại request với nonce **N2 mới**, chống replay tầng giao thức sẽ thấy đây là thông điệp mới; **idempotency key/unique business ID** vẫn phải ngăn thao tác nghiệp vụ bị lặp. Idempotency key phải được ràng buộc với principal và nội dung request: cùng key nhưng payload khác nên báo conflict thay vì âm thầm dùng kết quả cũ.

| Tình huống | Tag hợp lệ? | Nonce/seq check | Điều server nên làm |
| --- | --- | --- | --- |
| Request mới đúng chính sách | Có | Chưa thấy | Nhận và ghi nhận atomically, xử lý thao tác |
| Phát lại nguyên gói | Có | Đã thấy | Không thực thi lại |
| Sửa `amount` nhưng giữ tag cũ | Không | Không cần xét | Từ chối trước khi ghi replay state |
| Request có tag đúng nhưng timestamp hết hạn | Có | Có thể là nonce mới | Từ chối vì không còn freshness |
| Cùng đơn hàng, nonce mới, tag mới | Có | Chưa thấy | Kiểm tra idempotency nghiệp vụ để tránh charge hai lần |
| Hai node nhận cùng request đồng thời | Có | Cùng nonce | Claim atomic đảm bảo chỉ một node được xử lý |
| Counter cũ sau khi restart | Có | Cũ nếu state còn | Từ chối; mất state là lỗ hổng cần khắc phục |

### Ranh giới với TLS và AES-GCM

TLS bảo vệ dữ liệu trên đường truyền và có cơ chế record/sequence riêng. **Không suy ra** rằng một HTTP command đã được gửi lại qua một **kết nối TLS mới** sẽ bị lớp TLS tự loại bỏ. Yêu cầu idempotency/anti-replay ở tầng ứng dụng vẫn tùy thiết kế.

AES-GCM dùng **IV/nonce mật mã** và yêu cầu đặc biệt nghiêm ngặt về việc không tái sử dụng IV với cùng khóa. IV của AES-GCM là dữ liệu phục vụ mã hóa; **application replay nonce** là trường để bên nhận phát hiện thông điệp đã xử lý. Hai khái niệm có thể cùng xuất hiện trong một giao thức nhưng **không mặc định thay thế nhau**. Một bản mã AES-GCM hợp lệ được gửi lại, với tag hợp lệ, vẫn cần cơ chế replay state nếu ứng dụng muốn từ chối lần thứ hai.

## 9. Checklist kiểm thử và lỗi cần tránh

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Gửi cùng request/tag/nonce hai lần | Lần hai không tạo hiệu ứng nghiệp vụ |
| Sửa body, method, path, timestamp hoặc nonce nhưng giữ tag | Xác thực thất bại |
| Timestamp vừa trong và ngay ngoài giới hạn | Xử lý đúng quy tắc lệch đồng hồ/hết hạn |
| Hai request cùng nonce tới hai node đồng thời | Tối đa một request được claim |
| Restart server khi request cũ còn hiệu lực | Replay vẫn bị từ chối nếu đã chấp nhận trước restart |
| Retry sau khi response bị mất | Không trừ tiền/ghi đơn hai lần; phản hồi phù hợp idempotency |
| Gửi sequence lệch thứ tự, thiếu, trùng, quá cửa sổ | Đúng chính sách strict hoặc sliding window đã công bố |
| Rotate key, đổi session/epoch, client nhiều thiết bị | Không mở lại state cũ hoặc trùng counter ngoài ý muốn |
| Replay sau TTL hoặc gần ranh giới skew | Bản cũ đã hết hạn trước khi record được xóa |
| Tag sai với nonce mới | Không chiếm nonce trong replay cache |
| Nonce dài bất thường/gửi liên tục | Giới hạn tài nguyên và có rate limit |

**Những sai lầm thường gặp cần nhớ:**

- “HMAC đúng thì chắc request mới”: **sai**, tag vẫn đúng khi phát lại nguyên gói.
- “Thêm UUID/nonce vào header là đủ”: **sai**, cần được xác thực và lưu trạng thái.
- “Timestamp ký đúng thì hết replay”: **sai**, còn cửa sổ chấp nhận thì còn khả năng gửi lại.
- “Lưu nonce vào `HashSet` trên từng server”: chỉ đủ cho demo một process; hệ thống nhiều node cần trạng thái chung atomic.
- “Kiểm tra nonce rồi xử lý rồi mới ghi”: có race giữa request đồng thời và có thể tạo double effect.
- “Counter tăng nhưng không ký”: kẻ tấn công có thể đổi thành số mới để vượt chốt.
- “Một lần xử lý cho mỗi nonce là một lần xử lý cho mỗi giao dịch”: **sai**, cùng giao dịch có thể được ký lại bằng nonce mới.
- “Nonce của HMAC và IV của AES-GCM đều gọi là nonce nên dùng thay nhau”: **sai**, chúng bảo vệ các thuộc tính khác nhau với ràng buộc khác nhau.

## 10. Bài tập củng cố

1. **Giải thích luồng replay:** vẽ 3 thông điệp giữa client, attacker và server; chỉ ra chính xác bước HMAC vẫn đúng và bước replay store từ chối nonce đã dùng.
2. **Thực hành Java:** chạy `ReplayDemo.java`. Thử bỏ dòng `usedNonces.add(...)` (chỉ trong bản lab) để thấy bản phát lại không còn được kiểm tra. Thử đổi `amount` nhưng giữ tag cũ rồi giải thích vì sao bị từ chối.
3. **Thiết kế theo tình huống:** một API nhận webhook từ nhiều nhà gửi, chạy 4 node và cho phép retry trong 24 giờ. Xác định ai cấp nonce, phạm vi replay key, TTL, nơi lưu shared state, cùng cách trả response cho duplicate.
4. **Chọn sequence hay nonce:** một luồng thông điệp UDP có thể đảo thứ tự, một API tạo đơn hàng song song, và một kênh command bắt buộc thứ tự. Với mỗi tình huống, chọn cơ chế, giải thích trường nào phải ký và cách xử lý thông điệp tới muộn.
5. **Bài toán khó:** nếu server kiểm tra timestamp `now-300 <= issuedAt <= now+30`, tại thời điểm nhận `now` đã chấp nhận message có `issuedAt=now+30`, record nonce cần sống đến lúc nào để chống replay? Giải thích vì sao “TTL đúng 300 giây từ lúc nhận” không luôn đủ.
6. **Đánh giá giao dịch:** mô tả điều gì xảy ra nếu cache đã đánh dấu nonce nhưng DB rollback, hoặc DB commit nhưng cache chưa ghi; đề xuất một unique operation ID + transaction/response cache để tránh double charge.

### Tài liệu tham khảo

- [Java SE 21 — `javax.crypto.Mac`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): API HMAC, khởi tạo khóa, xử lý và xuất tag.
- [Java SE 21 — `java.security.SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): nguồn byte ngẫu nhiên cho nonce.
- [Java SE 21 — `MessageDigest.isEqual`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)): so sánh byte digest/tag.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): thuật toán message authentication code dựa trên hash.
- [RFC 9421, mục 7.2.2 — Signature Replay](https://www.rfc-editor.org/rfc/rfc9421.html#section-7.2.2): nonce/timestamp để giảm phát lại thông điệp ký.
- [NIST SP 800-38D — GCM và GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): đặc tính của AEAD và yêu cầu IV/nonce cho GCM.

**Tự đánh giá:** Nếu một request với MAC/chữ ký hợp lệ xuất hiện lần thứ hai, bạn đã có cơ chế **đủ trạng thái, đủ atomic, đúng phạm vi và tồn tại đủ lâu** để quyết định có được thực thi lại hay không? Trả lời được câu hỏi này mới thực sự phân biệt xác thực thông điệp với chống phát lại.

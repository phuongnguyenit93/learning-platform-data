# Chống phát lại khi ứng dụng cần bảo vệ tính mới (Java 15+)

## 1. Vì sao chữ ký hợp lệ vẫn có thể bị phát lại?

Khi tích hợp chữ ký số vào một API hoặc hệ thống xử lý sự kiện, Java có thể dùng `java.security.Signature` cùng thuật toán **Ed25519** hoặc **Ed448** để xác minh nội dung và khóa ký. Nhưng một chữ ký đã xác minh thành công **không có nghĩa thông điệp mới xuất hiện lần đầu**.

Ví dụ client ký một lệnh thanh toán `POST /payments`. Kẻ tấn công ghi lại nguyên request, gồm body và chữ ký hợp lệ, rồi gửi lại. Vì **bytes không thay đổi**, `Signature.verify` có thể vẫn trả `true`. Nếu server thực thi thanh toán lần nữa, tác động nghiệp vụ bị lặp dù việc xác minh mật mã không hề sai.

Đây là **replay attack** (tấn công phát lại). Cơ chế chống phát lại (*anti-replay*) kiểm tra rằng thông điệp còn trong thời hạn hợp lệ và chưa bị sử dụng trong phạm vi được quy định.

Một giải pháp phù hợp khi ứng dụng thực sự cần bảo vệ **tính mới (*freshness*)** thường kết hợp:

1. **Chữ ký hoặc MAC** bao phủ các thành phần quan trọng của request.
2. **Timestamp/expiration** giới hạn thời gian chữ ký có thể được dùng.
3. **Nonce/request ID/sequence** phân biệt các lần ký.
4. **Replay store nguyên tử** lưu dấu một request đã dùng; các lần gửi trùng bị từ chối.
5. **Kiểm soát side effect/idempotency** để tránh nhân đôi nghiệp vụ khi client retry, mạng lỗi hoặc server crash.

Các nguyên tắc này vẫn áp dụng trong Java hiện đại. Ví dụ dùng những API tiêu chuẩn đã có từ Java 15, không dùng cơ chế legacy và không cần thư viện ngoài JDK.

## 2. Đừng nhầm authenticity, freshness và idempotency

| Thuộc tính | Câu hỏi cần trả lời | Cơ chế |
| --- | --- | --- |
| **Authenticity** | Request được ký bởi khóa tin cậy cho chủ thể này? | `Signature.verify` + trusted key registry và authorization. |
| **Integrity** | Những trường được ký có thay đổi? | Kiểm tra chữ ký trên cùng canonical bytes. |
| **Freshness** | Request còn hạn và nonce chưa dùng? | Timestamp/expiry + nonce + replay store. |
| **Idempotency** | Retry cùng nghiệp vụ có gây side effect thêm lần nữa? | Business idempotency key + lưu trạng thái/kết quả. |
| **Exactly-once effect** | Side effect được commit tối đa một lần? | Transaction, unique constraint, outbox/inbox và reconciliation theo hệ thống. |

`Signature.verify(...) == true` **chỉ là một điều kiện**, không thay thế việc kiểm tra thời gian, trạng thái nonce hoặc quyền thực hiện giao dịch.

Ví dụ: nếu thanh toán đã commit nhưng server mất response, client có thể cần retry. Anti-replay có thể **từ chối gửi lại đúng signed request cũ** (nonce cũ), trong khi hệ thống idempotency cho phép **request mới được ký bằng nonce mới** giữ cùng business idempotency key và trả kết quả cũ **mà không thanh toán lại**.

Vì vậy, không nên xem anti-replay và idempotency là từ đồng nghĩa.

## 3. Những thành phần nên được ký trong một yêu cầu

Một protocol envelope có thể có các trường:

~~~text
version         = request-signature:v1
tenant          = tenantA
key_id          = key1
method          = POST
path_and_query  = /payments
created         = epoch_milliseconds
nonce           = random_128_bit_value
body_bytes      = exact_application_payload
signature       = Ed25519.Sign(privateKey, canonical_fields)
~~~

**Mọi trường có ảnh hưởng đến quyền, ý nghĩa, thời hạn hoặc tính duy nhất của thao tác đều phải được ký hoặc được ràng buộc mật mã đúng cách.** Đặc biệt:

- `tenant` và `key_id` xác định **người ký và phạm vi sử dụng khóa**.
- `method` và `path/query` xác định **operation** được cấp quyền.
- `body` hoặc digest đã kiểm tra ràng buộc **nội dung nghiệp vụ**.
- `created` và `nonce` phải được ký để người khác không thể tự sửa chúng nhằm kéo dài hạn hoặc tránh replay cache.
- `version` / domain separator tránh dùng chữ ký của một giao thức ở giao thức khác.

**Không bao giờ** chấp nhận public key bất kỳ do client gửi như một nguồn xác thực danh tính. Server phải tra public key theo `tenant/key_id` trong registry/certificate trust policy của mình và xác minh khóa có quyền với operation ấy.

Sau xác minh, server phải so sánh method/path/body/tenant đã ký với **request thực sự** và quyết định nghiệp vụ thực sự. Nếu một header không được ký quyết định tài khoản thụ hưởng, attacker có thể sửa header đó mà chữ ký các trường khác vẫn hợp lệ.

### 3.1. Canonicalization phải nhất quán

Một rủi ro của việc tự ghép chuỗi là nhập nhằng:

~~~text
"A" + "|" + "B|C" -> A|B|C
"A|B" + "|" + "C" -> A|B|C
~~~

Hai bộ trường khác nhau tạo cùng chuỗi. Ví dụ Java bên dưới sử dụng **length-prefix**: ghi độ dài byte UTF-8 rồi mới ghi giá trị; timestamp ghi bằng `DataOutputStream.writeLong`. Đây là **protocol minh họa tự định nghĩa**, không phải mã hóa chuẩn cho HTTP Message Signatures.

Nếu triển khai chữ ký cho HTTP thực tế, cần quy tắc về normalization của URL, query string, repeated headers, body bytes, reverse proxy, HTTP/1.1–HTTP/2. **RFC 9421 (HTTP Message Signatures)** mô tả các thành phần được ký, signature base và tham số `nonce`, `created`, `expires`. Nên dùng thư viện hiện hành triển khai đúng RFC khi cần tương thích giữa các hệ thống, thay vì tùy tiện đưa bytes của request vào `String` rồi ký.

## 4. Timestamp: giới hạn độ mới theo thời gian

Một ví dụ policy:

- Cửa sổ quá khứ: **5 phút**.
- Sai lệch thời gian tương lai tối đa: **30 giây**.
- Thời gian hiện tại do **server** cung cấp qua `Clock`.

Với `age = now - created`:

~~~text
-30_000 milliseconds <= age < 300_000 milliseconds
~~~

Nghĩa là request cũ quá 5 phút bị loại, request có timestamp vượt tương lai quá 30 giây cũng bị loại. Giá trị **5 phút/30 giây chỉ là ví dụ**, phải điều chỉnh theo latency, clock synchronization và threat model.

**Timestamp đơn lẻ không chống replay trong cửa sổ còn hạn.** Một thông điệp được ký lúc 10:00 có thể bị gửi lại nhiều lần đến 10:04:59 nếu server không có replay state. Vì vậy, với thao tác có side effect mà ứng dụng muốn tiếp nhận tối đa một lần, cần thêm nonce/counter/challenge và kiểm tra trạng thái đã dùng.

### 4.1. Quy tắc thời gian nên được xác định chính xác

- Thống nhất **UTC/epoch**, tránh phụ thuộc múi giờ.
- Server không dùng giá trị `now` do client cung cấp thay cho đồng hồ của nó.
- Đồng bộ đồng hồ giữa các node và xem xét độ trễ hàng đợi.
- Ràng buộc `created` (và `expires` nếu có) trong chữ ký.
- Chọn điều kiện biên rõ ràng, ví dụ `age >= WINDOW_MS` bị từ chối.
- Trạng thái nonce phải được giữ **ít nhất cho đến khi signed request không còn được phép chấp nhận**. TTL không được hết quá sớm so với policy hiệu lực chữ ký.

Nếu client được phép tạo timestamp ở tương lai trong một khoảng skew, việc tính expiry phải bao phủ khoảng đó và sự khác biệt đồng hồ giữa các instance. Một số giao thức có thêm `expires` được ký để nêu hạn sử dụng cụ thể; verifier phải kiểm tra cả các ràng buộc liên quan.

## 5. Nonce: giá trị duy nhất cho một signed request

Một nonce tốt phải đáp ứng threat model. Với client tự sinh nonce, cách thông dụng là dùng **128 bit ngẫu nhiên từ `SecureRandom`** và gửi dưới dạng Base64URL:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

SecureRandom secureRandom = new SecureRandom();
byte[] bytes = new byte[16];
secureRandom.nextBytes(bytes);

String nonce = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
~~~

Đoạn này là **mã minh họa trong một phương thức**. Không dùng `java.util.Random` hoặc chỉ timestamp làm nonce mật mã. Cũng không nên chỉ dựa vào `UUID`/request ID nếu chưa xác định nguồn sinh và phạm vi uniqueness.

**Nonce phải được ký.** Nếu gửi nonce trong một trường riêng **không được bảo vệ**, người phát lại có thể thay nonce khác để đi qua replay store.

### 5.1. Replay key phải có phạm vi rõ ràng

Một replay store có thể dùng khóa:

~~~text
tenant + authenticated_key_id + nonce
~~~

với các thành phần được xác minh và chuẩn hóa. Tùy protocol, có thể cần audience, session, endpoint namespace hoặc signer identity. **Không dùng phạm vi quá hẹp** khiến một nonce trùng được chấp nhận ở nhiều endpoint trái ý định, cũng **không dùng quá rộng** làm tenant không liên quan chặn lẫn nhau.

Đặc biệt, nếu chính sách quy định “một nonce chỉ được dùng một lần”, **đừng tự thêm body hash vào replay key**: request mới được ký với cùng nonce nhưng body khác có thể lách uniqueness vì hash khác nhau.

Một `requestId` hoặc monotonic sequence có thể thay nonce ngẫu nhiên khi protocol đã định nghĩa cụ thể cách xác thực, uniqueness, lưu trạng thái và xử lý out-of-order. Không có một lựa chọn phù hợp cho mọi hệ thống.

### 5.2. Nonce do client sinh hay challenge do server sinh?

**Client-generated nonce:** client sinh giá trị khó đoán và server ghi nhận khi dùng. Nó chặn request đã được chấp nhận, nhưng kẻ tấn công giữ một signed request có thể gửi bản sao **trước** request chính thức. Chính sách “first accepted wins” có thể ưu tiên bản sao tới trước (*preplay/race*).

**Server-issued challenge:** server phát nonce một lần, có hạn dùng, ràng buộc principal/session/action. Client ký request có challenge; server tiêu thụ challenge bằng thao tác atomic. Cách này bổ sung round trip và trạng thái, nhưng phù hợp khi cần ràng buộc mạnh với một thử thách mới được server cấp.

Dù dùng lựa chọn nào, HTTPS/TLS, bảo vệ private key, authorization, rate limiting và các biện pháp bảo mật tầng transport vẫn cần thiết. Chữ ký **không cung cấp confidentiality**.

## 6. Replay store phải hỗ trợ đánh dấu nguyên tử

Một trình tự tiếp nhận phù hợp:

~~~text
A. Parse và giới hạn input.
B. Tìm khóa công khai đã đăng ký, kiểm tra signer/tenant/audience.
C. Kiểm tra created/expires theo đồng hồ server.
D. Xác minh Signature trên đúng canonical bytes của request.
E. Tính replay key (signer scope, nonce).
F. Atomic insert-if-absent / consume-once với TTL.
G. Nếu đã tồn tại: từ chối REPLAY.
H. Nếu claim thành công: tiếp tục kiểm tra/ghi nghiệp vụ.
~~~

**Không ghi nonce vào replay store trước khi verify chữ ký**: attacker có thể gửi chữ ký giả với nonce của request thật và cố tình làm request thật bị từ chối (cache poisoning/DoS).

### 6.1. Lỗi check-then-put

~~~java
// BUG: minh hoa cach KHONG nen dung.
if (!used.containsKey(nonce)) {
    used.put(nonce, expiry);
    processPayment();
}
~~~

Hai thread có thể cùng nhìn thấy nonce chưa tồn tại, cùng ghi và cùng thực hiện side effect. Trong hệ thống nhiều server, mỗi JVM có cache riêng sẽ làm tình huống này nghiêm trọng hơn.

Thay bằng **phép claim nguyên tử**:

- `ConcurrentHashMap.compute` hoặc `putIfAbsent` chỉ hiệu quả **trong một JVM**.
- **Redis**: `SET key value NX EX seconds` hoặc thao tác tương đương với TTL atomically.
- **Database**: unique constraint trên replay scope và một `INSERT` có xử lý duplicate, tốt nhất đặt cùng transaction với state nghiệp vụ khi cần.
- **Server challenge store**: API consume-once có consistency và durability phù hợp.

Không dùng chuỗi `GET` rồi `SET` rời nhau khi nhiều request có thể chạy song song.

### 6.2. Replay store cần TTL và quản lý capacity

- Mỗi nonce được lưu ít nhất tới thời điểm signed request hết hiệu lực.
- Store phải dùng **chung cho các instance** đang xử lý cùng phạm vi.
- Đánh giá replication, failover, cache eviction, data loss và tính nhất quán; nếu trạng thái nonce mất trước hạn, replay có thể được chấp nhận.
- Hạn chế length nonce, số request và kích thước body để tránh tấn công tiêu hao bộ nhớ/CPU.
- Theo dõi metric số nonce trùng, chữ ký sai, timestamp expired/future và lỗi cache.
- Với thao tác rủi ro cao, nếu replay store không có sẵn, thường cần **fail closed** (không xử lý side effect) thay vì bỏ qua kiểm tra.

### 6.3. Anti-replay không tự tạo exactly-once side effect

Giả sử server đánh dấu nonce thành công rồi **crash trước khi commit thanh toán**: retry cùng nonce bị từ chối, nhưng thanh toán chưa xảy ra. Nếu thanh toán được thực thi **trước claim**, hai request đồng thời có thể thực thi hai lần.

Với nghiệp vụ nhạy cảm, hãy đặt **nonce state và nghiệp vụ trong một transaction** khi cùng database, hoặc sử dụng durable state machine/outbox/idempotency khi side effect nằm ngoài database.

Ví dụ ý tưởng SQL (không phải script chạy độc lập):

~~~sql
BEGIN;

INSERT INTO replay_nonce (tenant, key_id, nonce, expires_at)
VALUES (:tenant, :key_id, :nonce, :expires_at)
ON CONFLICT (tenant, key_id, nonce) DO NOTHING;

-- BẮT BUỘC kiểm tra có đúng một dòng vừa được insert.
-- Nếu nonce đã có, KHÔNG thực hiện giao dịch.

INSERT INTO payment_ledger (business_id, amount)
VALUES (:business_id, :amount);
-- business_id cần ràng buộc uniqueness/idempotency tương ứng.

COMMIT;
~~~

Với database thật phải xử lý rollback, isolation, unique constraints và kết quả insert chính xác. Nếu có **HTTP call tới cổng thanh toán bên ngoài**, transaction nội bộ không thể bảo đảm bên ngoài chỉ thực hiện một lần; cần gửi idempotency key mà đối tác hiểu, phối hợp outbox/reconciliation và quản lý trạng thái.

## 7. Ví dụ Java hoàn chỉnh: Ed25519 + Clock + nonce + concurrency

Ví dụ độc lập dưới đây áp dụng:

- Ed25519 sinh key pair, ký và xác minh bằng `Signature`.
- Nonce 128-bit từ `SecureRandom`.
- Canonical signing bytes có length-prefix, domain separator, tenant/key/method/path/timestamp/nonce/body.
- Time window 5 phút, future skew 30 giây.
- `ConcurrentHashMap.compute` claim một nonce tối đa một lần trong một JVM.
- `Clock.fixed` cho kết quả kiểm thử không phụ thuộc giờ máy.
- 8 thread cùng gọi một request: đúng một lần chấp nhận.

**Đây là demo nội bộ một process**, không thay thế distributed replay store, HTTP canonicalization hoặc transaction khi chạy production.

### 7.1. File `ReplayProtectionDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class ReplayProtectionDemo {
    private static final long WINDOW_MS = 5 * 60_000L;
    private static final long FUTURE_SKEW_MS = 30_000L;
    private static final SecureRandom RANDOM = new SecureRandom();

    static final class Request {
        final String tenant, keyId, method, path, nonce;
        final long createdMillis;
        final byte[] body, signature;

        Request(String tenant, String keyId, String method, String path,
                String nonce, long createdMillis, byte[] body, byte[] signature) {
            this.tenant = tenant;
            this.keyId = keyId;
            this.method = method;
            this.path = path;
            this.nonce = nonce;
            this.createdMillis = createdMillis;
            this.body = body.clone();
            this.signature = signature.clone();
        }

        Request withBody(byte[] newBody) {
            return new Request(tenant, keyId, method, path, nonce,
                    createdMillis, newBody, signature);
        }
    }

    static String randomNonce() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static void field(DataOutputStream out, String text)
            throws Exception {
        byte[] value = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(value.length);
        out.write(value);
    }

    static byte[] signingBytes(Request r) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            field(out, "request-signature:v1");
            field(out, r.tenant);
            field(out, r.keyId);
            field(out, r.method);
            field(out, r.path);
            out.writeLong(r.createdMillis);
            field(out, r.nonce);
            out.writeInt(r.body.length);
            out.write(r.body);
        }
        return buffer.toByteArray();
    }

    static Request sign(String tenant, String keyId, String method,
                        String path, String nonce, long createdMillis,
                        byte[] body, PrivateKey privateKey) throws Exception {
        Request unsigned = new Request(tenant, keyId, method, path,
                nonce, createdMillis, body, new byte[0]);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(signingBytes(unsigned));
        return new Request(tenant, keyId, method, path, nonce,
                createdMillis, body, signer.sign());
    }

    static final class ReplayGuard {
        private final Clock clock;
        private final ConcurrentHashMap<String, Long> used =
                new ConcurrentHashMap<>();

        ReplayGuard(Clock clock) {
            this.clock = clock;
        }

        boolean accept(Request r, String expectedTenant,
                       String expectedKeyId, PublicKey trustedKey)
                throws Exception {
            if (!r.tenant.equals(expectedTenant)
                    || !r.keyId.equals(expectedKeyId)
                    || !r.tenant.matches("[A-Za-z0-9_-]{1,64}")
                    || !r.keyId.matches("[A-Za-z0-9_-]{1,64}")
                    || !r.nonce.matches("[A-Za-z0-9_-]{16,64}")) {
                return false;
            }

            long now = clock.millis();
            long age;
            try {
                age = Math.subtractExact(now, r.createdMillis);
            } catch (ArithmeticException invalidTime) {
                return false;
            }
            if (age >= WINDOW_MS || age < -FUTURE_SKEW_MS) {
                return false;
            }

            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(trustedKey);
            verifier.update(signingBytes(r));
            if (!verifier.verify(r.signature)) {
                return false;
            }

            String scopedNonce = r.tenant + ":" + r.keyId + ":" + r.nonce;
            long expiresAt = Math.addExact(r.createdMillis, WINDOW_MS);
            AtomicBoolean firstUse = new AtomicBoolean(false);
            used.compute(scopedNonce, (key, previousExpiry) -> {
                if (previousExpiry == null || previousExpiry <= now) {
                    firstUse.set(true);
                    return expiresAt;
                }
                return previousExpiry;
            });
            return firstUse.get();
        }

        void removeExpired() {
            long now = clock.millis();
            used.entrySet().removeIf(e -> e.getValue() <= now);
        }
    }

    public static void main(String[] args) throws Exception {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-08T09:00:00Z"), ZoneOffset.UTC);
        long now = clock.millis();

        KeyPair pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        ReplayGuard guard = new ReplayGuard(clock);
        byte[] body = "{\"amount\":42}".getBytes(StandardCharsets.UTF_8);
        String nonce = randomNonce();

        Request req = sign("tenantA", "key1", "POST", "/payments",
                nonce, now, body, pair.getPrivate());
        Request tampered = req.withBody(
                "{\"amount\":43}".getBytes(StandardCharsets.UTF_8));

        System.out.println("tampered=" + guard.accept(
                tampered, "tenantA", "key1", pair.getPublic()));
        System.out.println("first=" + guard.accept(
                req, "tenantA", "key1", pair.getPublic()));
        System.out.println("replay=" + guard.accept(
                req, "tenantA", "key1", pair.getPublic()));

        Request next = sign("tenantA", "key1", "POST", "/payments",
                randomNonce(), now, body, pair.getPrivate());
        System.out.println("freshNonce=" + guard.accept(
                next, "tenantA", "key1", pair.getPublic()));

        Request stale = sign("tenantA", "key1", "POST", "/payments",
                randomNonce(), now - WINDOW_MS - 1, body, pair.getPrivate());
        System.out.println("stale=" + guard.accept(
                stale, "tenantA", "key1", pair.getPublic()));

        Request future = sign("tenantA", "key1", "POST", "/payments",
                randomNonce(), now + FUTURE_SKEW_MS + 1, body, pair.getPrivate());
        System.out.println("future=" + guard.accept(
                future, "tenantA", "key1", pair.getPublic()));

        Request wrongIdentity = sign("tenantA", "key1", "POST", "/payments",
                randomNonce(), now, body, pair.getPrivate());
        System.out.println("wrongTenant=" + guard.accept(
                wrongIdentity, "tenantB", "key1", pair.getPublic()));

        Request race = sign("tenantA", "key1", "POST", "/payments",
                randomNonce(), now, body, pair.getPrivate());
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<Boolean>> futures = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    return guard.accept(
                            race, "tenantA", "key1", pair.getPublic());
                }));
            }
            start.countDown();
            int accepted = 0;
            for (Future<Boolean> f : futures) {
                if (f.get()) accepted++;
            }
            System.out.println("concurrentAccepted=" + accepted);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

### 7.2. Biên dịch và kiểm tra đầu ra

Chạy từ thư mục chứa tệp bằng JDK hỗ trợ Ed25519:

~~~bash
javac --release 15 -encoding UTF-8 ReplayProtectionDemo.java
java ReplayProtectionDemo
~~~

**Đầu ra đã kiểm chứng trên JDK 24 với `--release 15`:**

~~~text
tampered=false
first=true
replay=false
freshNonce=true
stale=false
future=false
wrongTenant=false
concurrentAccepted=1
~~~

Giải thích từng trường hợp:

- **`tampered=false`:** body sau khi ký bị thay từ `amount=42` thành `43`; chữ ký bị từ chối. Vì verify xảy ra **trước claim nonce**, request giả không chiếm nonce hợp lệ.
- **`first=true`:** request có chữ ký đúng, timestamp còn hạn và nonce chưa dùng được tiếp nhận.
- **`replay=false`:** gửi lại cùng request, nonce đã claim nên từ chối.
- **`freshNonce=true`:** request mới với nonce khác và chữ ký tương ứng có thể được chấp nhận.
- **`stale=false`:** created quá cũ so với cửa sổ 5 phút.
- **`future=false`:** created vượt sai lệch 30 giây về tương lai.
- **`wrongTenant=false`:** request cho `tenantA` không được dùng như request của `tenantB`.
- **`concurrentAccepted=1`:** 8 thread cùng claim một nonce; chỉ một thread được chấp nhận nhờ phép `compute` nguyên tử trong map.

`Clock.fixed` làm thời gian kiểm thử ổn định; nonce và cặp khóa được sinh ngẫu nhiên nhưng các kiểm tra không dựa vào giá trị cụ thể của chúng.

### 7.3. Giới hạn của mã mẫu, không được bỏ qua khi triển khai thật

`ReplayGuard` là **mô phỏng single-process**, nên:

- Map chỉ thuộc **một JVM** và mất dữ liệu khi restart.
- `removeExpired()` phải được gọi theo cơ chế dọn nếu muốn giữ map không tăng vô hạn; demo không cài scheduler. Production nên dùng TTL store có quản lý capacity.
- `Clock.fixed` chỉ dùng cho test; production dùng đồng hồ máy chủ đáng tin, ví dụ `Clock.systemUTC()`.
- Phương thức `accept` nhận `trustedKey` đã được caller chọn; production phải truy xuất khóa từ nguồn tin cậy, kiểm tra authorization và key rotation.
- Cấu trúc `Request` chứa method/path/body; adapter HTTP thật cần gắn đúng những dữ liệu đã xác thực vào operation đang thực thi, kể cả query và proxy transformations.
- Mã chưa kiểm soát request size, rate limits, API errors, phân quyền phức tạp, distributed consistency và transaction.
- **`accept=true` không có nghĩa nghiệp vụ đã commit exactly once**. Chỉ khi kết hợp transaction/idempotency và durable state mới có thể đưa ra bảo đảm phù hợp.

Việc `used.compute` có thể giải phóng entry sau expiration không có nghĩa JVM tự loại bỏ mọi entry hết hạn; phần dọn TTL phải được thiết kế trong triển khai thực tế.

## 8. Retry sau lỗi: chống replay phải phối hợp idempotency

Giả sử:

~~~text
1. Client gửi POST /payments (nonce=N), chữ ký hợp lệ.
2. Server claim N và commit thanh toán.
3. Response bị mất trên đường truyền.
4. Client không biết giao dịch đã thành công, gửi lại cùng request N.
5. Server từ chối N vì replay.
~~~

Điều này bảo đảm **signed request không được dùng lần hai**, nhưng chưa cho client biết kết quả nghiệp vụ. Giải pháp thích hợp là tách:

- **Transport nonce:** duy nhất cho mỗi lần yêu cầu được ký.
- **Business idempotency key:** duy nhất cho nghiệp vụ thanh toán, giữ nguyên khi client retry.
- **Operation record:** lưu trạng thái `PENDING/COMPLETED/FAILED` và kết quả có thể tra cứu.

Client có thể tạo **request mới** với nonce và timestamp mới, ký lại, nhưng giữ cùng **business idempotency key** đã ký. Server tra operation record/unique constraint, trả kết quả đã lưu mà không tạo payment thứ hai.

Nếu business idempotency key không được ký, kẻ tấn công có thể sửa key để đánh lừa cách de-duplicate. Nếu API có retry, cần công bố rõ khi nào trả `409 Conflict`, `401/403`, response trạng thái cũ hay error khác theo semantic của endpoint; không chọn status HTTP tùy tiện rồi coi nó là yêu cầu của thuật toán.

## 9. So sánh các lựa chọn thiết kế

| Giải pháp | Phù hợp | Giới hạn |
| --- | --- | --- |
| **Timestamp đơn lẻ** | Giảm thời gian dùng chữ ký đã lộ. | Vẫn replay được trong khoảng còn hạn. |
| **Random nonce + replay store** | Lệnh độc lập cần nhận tối đa một lần trong cửa sổ. | Cần state atomic/durable, TTL, policy failure và chống race. |
| **Server challenge + consume-once** | Tính mới gắn với phiên/action do server chủ động cấp. | Tăng round trip, phải tiêu thụ challenge nguyên tử. |
| **Monotonic counter** | Thiết bị/session có thứ tự thông điệp rõ. | Xử lý out-of-order, reset và đồng bộ phức tạp. |
| **Idempotency key** | Retry nghiệp vụ không gây side effect trùng. | Không tự xác minh chữ ký, key scope và freshness. |
| **RFC 9421 HTTP Message Signatures** | Các hệ thống ký thành phần HTTP chuẩn hóa. | Verifier vẫn phải kiểm tra signature coverage, thời gian, nonce và replay policy. |

Không cần ép mọi endpoint dùng nonce một lần. Một số thao tác **GET chỉ đọc, không side effect** có thể sử dụng authentication và HTTPS phù hợp mà không cần replay store riêng. Ngược lại, các operation **chuyển tiền, duyệt quyền, đặt hàng, thực thi job hoặc nhận sự kiện có tác động** cần threat model và ràng buộc replay/idempotency rõ ràng.

## 10. Lỗi phổ biến cần tránh

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ gọi `Signature.verify` rồi xử lý. | Signed request cũ vẫn có thể được chấp nhận. | Thêm freshness và duplicate state khi cần. |
| Timestamp hoặc nonce không nằm trong chữ ký. | Attacker sửa metadata để tránh TTL/cache. | Ký toàn bộ trường ảnh hưởng đến quyết định. |
| Bỏ method/path/tenant ra khỏi chữ ký. | Dễ tái sử dụng chữ ký khác ngữ cảnh. | Ràng buộc operation, signer, audience và body. |
| Chỉ dùng timestamp. | Replay trong cửa sổ vẫn được xử lý. | Nonce/counter/challenge với claim một lần. |
| Sinh nonce từ timestamp/`Random`. | Có thể đoán/trùng. | `SecureRandom` đủ entropy. |
| Store key là nonce trên toàn bộ tenant. | Trùng giữa các chủ thể gây chặn lẫn nhau. | Scope identity/key/namespace phù hợp. |
| Store key gồm body hash nhưng policy yêu cầu nonce duy nhất. | Cùng nonce + body khác có thể qua cache. | Xác định uniqueness trước khi chọn key. |
| Claim nonce trước verify chữ ký. | Fake request chiếm nonce thật. | Verify/authorization trước atomic claim. |
| `containsKey` rồi `put`. | Hai thread cùng chấp nhận. | Atomic claim hoặc database unique insert. |
| Replay cache riêng ở từng pod. | Replay qua node khác. | Store chung cho toàn hệ thống. |
| TTL ngắn hơn signed request validity. | Nonce bị xóa sớm khi chữ ký còn hiệu lực. | Retain đến khi request không còn được chấp nhận. |
| Replay store lỗi thì bỏ qua. | Hệ thống có thể xử lý trùng. | Fail closed với operation nhạy cảm. |
| Ghi nonce và side effect không có transaction. | Crash gây từ chối nhầm hoặc nhân đôi side effect. | Business state/idempotency/transaction phù hợp. |
| Tin public key do attacker tự gửi. | Tự ký rồi tự xác minh không chứng minh principal. | Trusted key registry + authorization. |
| Dùng nối chuỗi không canonical. | Ambiguous signature base hoặc false reject. | Length-prefix chuẩn hóa hoặc RFC 9421. |
| Xem anti-replay là bảo vệ bí mật. | Dữ liệu vẫn có thể bị lộ khi transport yếu. | Tiếp tục dùng HTTPS/TLS và bảo vệ khóa. |

## 11. Checklist đưa vào production

1. **Xác định dữ liệu và side effect cần bảo vệ**: thanh toán, approval, webhook, event, session, hay request thao tác?
2. **Định nghĩa principal/tenant/audience và khóa tin cậy**; không tin public key tùy ý trong request.
3. **Xác định chính xác signature base**: method, path/query, body, nonce, timestamps, key ID, protocol version và business ID.
4. **Công bố encoding/canonicalization** cho JSON, URL, UTF-8, proxy và HTTP headers; hai bên phải ký/xác minh cùng byte.
5. **Chọn freshness window và skew có căn cứ**, quan sát thời gian server thực tế.
6. **Quy định nonce source/entropy, scope và policy re-use**; dùng server challenge nếu threat model cần.
7. **Dùng shared atomic replay store** có TTL, durability và failover đúng mức.
8. **Thiết kế transaction/idempotency** cho crash, timeout, duplicate concurrency, external side effect.
9. **Fail closed ở operation rủi ro cao** khi không xác định được nonce đã dùng hay chưa.
10. **Kiểm thử âm và concurrency**: tampered payload, wrong endpoint/tenant, invalid key, stale/future, replay, 8+ concurrent duplicates, failover, restart, retry sau commit.
11. **Giám sát và giới hạn tài nguyên**: signature verification cost, replay cache size, abnormal nonce volume và tỉ lệ từ chối.
12. **Kiểm tra trên đúng JDK/provider triển khai**; Java 15 hỗ trợ Ed25519 nhưng policy và trạng thái hệ thống là trách nhiệm ứng dụng.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Vì sao chữ ký Ed25519 hợp lệ không chứng minh request là mới?

**Đáp án:** Signature xác minh dữ liệu và khóa, không lưu lịch sử. Gửi lại nguyên request cũ vẫn tạo cùng kết quả xác minh.

**Câu 2.** Timestamp được ký với hạn 5 phút có đủ ngăn replay không?

**Đáp án:** Không. Trong 5 phút, request có thể được gửi lại. Cần nonce/counter/challenge và trạng thái đã dùng nếu muốn chấp nhận một lần.

**Câu 3.** Vì sao phải ký nonce và method/path?

**Đáp án:** Nếu nonce không được ký, attacker có thể thay nonce để tránh replay cache. Nếu method/path không được ký, chữ ký có thể dùng sai operation.

**Câu 4.** `ConcurrentHashMap.compute` có đủ cho 10 pod không?

**Đáp án:** Không. Nó nguyên tử **trong một JVM**. Các pod phải chia sẻ state store có atomic claim và TTL phù hợp.

**Câu 5.** Ghi nonce trước khi verify có thể gây gì?

**Đáp án:** Request giả chiếm nonce của request thật, gây từ chối dịch vụ. Cần xác minh chữ ký trước khi đánh dấu.

**Câu 6.** Client cần retry payment sau khi response thất lạc thì xử lý thế nào?

**Đáp án:** Tạo signed request mới với nonce mới nhưng giữ business idempotency key; server dùng record nghiệp vụ để không chuyển tiền lần nữa và trả kết quả đã commit.

**Câu 7.** Nonce tự sinh có bảo đảm attacker không thể gửi bản sao đến trước client không?

**Đáp án:** Không. “First accepted wins” không ngăn kẻ có sẵn signed request đua trước. Cần bảo vệ transport/private key và cân nhắc challenge do server phát khi cần freshness nghiêm ngặt.

## Ghi nhớ

- **Chữ ký số xác minh tính xác thực/toàn vẹn, không tự bảo vệ tính mới.**
- **Timestamp giới hạn thời hạn; nonce + store nguyên tử chặn tái sử dụng trong cửa sổ.**
- **Ký đầy đủ metadata liên quan tới quyền, operation, body, timestamp và nonce.**
- **Replay state phải dùng chung nhiều instance, giữ TTL đủ dài và có thao tác claim atomic.**
- **Verify trước claim, nhưng exactly-once side effect cần transaction/idempotency.**
- **Idempotency không đồng nghĩa anti-replay**; thiết kế cả hai theo tình huống retry thực tế.
- **Java demo chạy trong một process để minh họa**, không thay giải pháp production.
- **RFC 9421 và các Java 15+ APIs được dùng vẫn hiện hành**, không cần cơ chế deprecated để xử lý bài toán.

### Tài liệu tham khảo còn áp dụng

- [RFC 9421 – HTTP Message Signatures, `7.2.2 Signature Replay](https://www.rfc-editor.org/rfc/rfc9421.html#section-7.2.2): các rủi ro phát lại và nonce, created/expires.
- [RFC 9421 – Signature Base](https://www.rfc-editor.org/rfc/rfc9421.html#section-2): các quy tắc tạo signature base cho HTTP.
- [Oracle Java 15 – Signature](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/Signature.html): API ký/xác minh.
- [Oracle Java 25 – SecureRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html): ngẫu nhiên an toàn.
- [Oracle Java 25 – Clock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html): đồng hồ có thể tiêm vào để test.
- [Oracle Java 25 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute` và tính nguyên tử trong JVM.
- [JEP 339 – Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): EdDSA được hỗ trợ từ Java 15.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): kiểm tra authorization và bảo mật REST APIs.

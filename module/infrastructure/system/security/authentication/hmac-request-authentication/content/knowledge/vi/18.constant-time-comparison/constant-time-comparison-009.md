# Giới hạn đo timing

**Đo timing** là việc quan sát thời gian thực thi để tìm mối quan hệ giữa thời gian xử lý và một phần dữ liệu cần được bảo vệ. Trong xác thực HTTP request bằng HMAC, điểm nhạy cảm điển hình là so sánh **HMAC tag kỳ vọng** do server tính lại với **HMAC tag client gửi**. Nếu phép so sánh dừng ngay ở byte đầu tiên khác nhau, thời gian xử lý có thể phụ thuộc vào số byte tiền tố đã khớp; đó là một loại *timing side channel*.

Tuy nhiên, đo thời gian không giống với chứng minh an toàn. Một chương trình Java chạy trên JVM có JIT compilation, garbage collector, scheduler và phần cứng CPU phức tạp; một HTTP request còn đi qua TLS, proxy/gateway, key registry, canonicalization, replay store và authorization. Các thành phần này có thể tạo nhiễu lớn hơn tín hiệu từ phép so tag. Ngược lại, việc **không quan sát được chênh lệch trong một phép đo** không chứng minh hệ thống không có rò rỉ.

Bài thuộc chương **Constant-time comparison** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Module dùng shared secret và canonical request gồm method, URI, signed headers và/hoặc body để xác thực HTTP request bằng HMAC; đồng thời cần chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

> **Nguyên tắc:** Constant-time comparison là một biện pháp giảm rò rỉ từ **phép so sánh tag bí mật**. Timing test cung cấp bằng chứng thực nghiệm **trong điều kiện đã đo**, không phải bằng chứng tuyệt đối rằng toàn bộ HTTP authentication flow chạy cùng thời gian hoặc không tồn tại side channel.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cơ chế timing leak do phép so sánh HMAC tag **early exit**.
2. Phân biệt thời gian của **primitive comparison**, **HMAC verifier** và **HTTP request end-to-end**.
3. Nêu giới hạn của các phép đo đơn lẻ, mẫu nhỏ, trung bình/trung vị và p-value.
4. Nhận diện ảnh hưởng của JIT, GC, CPU, thread scheduling, timer overhead, network và gateway.
5. Thiết kế nhóm thí nghiệm có cùng độ dài tag, chỉ khác vị trí byte sai, với warm-up và thứ tự được trộn.
6. Dùng Java 17 `MessageDigest.isEqual` trong đúng phạm vi, không tự tuyên bố bảo đảm constant-time cho cả request.
7. Viết test correctness, thiết kế benchmark minh họa và diễn giải kết quả có giới hạn rõ ràng.
8. Kết hợp biện pháp so tag an toàn với strict signature parsing, expected HMAC, timestamp/nonce, key rotation và authorization.

## 2. Nguồn timing leak khi so HMAC tag

Giả sử HMAC-SHA256 tạo tag đầy đủ **32 byte**:

~~~text
expectedTag: 32 byte server tính bằng secret và canonical request
suppliedTag: 32 byte decode từ X-Signature của caller
~~~

Một vòng lặp so byte thường dùng cho dữ liệu thông thường có thể dừng sớm:

~~~java
// Ví dụ lỗi: không dùng để so tag mật mã.
static boolean insecureEquals(byte[] expected, byte[] supplied) {
    if (expected.length != supplied.length) {
        return false;
    }
    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != supplied[i]) {
            return false; // Dừng ngay ở byte sai đầu tiên.
        }
    }
    return true;
}
~~~

Nếu byte thứ 0 khác nhau, chương trình có thể thực hiện một vòng. Nếu 31 byte đầu giống nhau và chỉ byte 31 khác, chương trình thực hiện gần đủ 32 vòng. Khi attacker có thể gửi nhiều tag thử và quan sát thời gian, đường xử lý này có nguy cơ tiết lộ thông tin về **prefix của expected tag**.

Không thể kết luận rằng một request từ Internet đủ để đo được vị trí sai. Việc khai thác phụ thuộc khả năng lặp phép thử, nhiễu, độ ổn định expected tag, rate limiting và vị trí đo của attacker. Nhưng **chưa chứng minh khai thác được** không phải lý do giữ comparator early exit trong code xác thực.

### 2.1. Bí mật gì đang được bảo vệ?

| Dữ liệu | Vai trò bảo mật | Điều cần tránh |
| --- | --- | --- |
| Shared secret HMAC | Khóa lâu dài hoặc theo phiên | Không log/gửi ra ngoài; bảo vệ secret manager |
| Expected HMAC tag | Kết quả server tự tính, dùng để so | Không tiết lộ mức độ khớp prefix qua xử lý |
| Presented signature | Caller gửi, có thể tùy chọn | Validate format/độ dài; không tin là bằng chứng trước khi so |
| Tag length | Thường công khai theo thuật toán | Có thể reject sai độ dài; không đồng nhất với byte value secret |
| Key ID | Định danh credential, thường không bí mật | Tránh tạo oracle tiết lộ status/ownership ngoài policy |
| Timestamp/nonce | Metadata không bí mật nhưng được ký | Chặn replay với window và atomic nonce store |
| Principal/scope | Quyền từ registry phía server | Không suy từ header caller tự khai |

Mục tiêu timing-safe comparison là tránh lộ **nội dung tag kỳ vọng** thông qua vị trí byte khác; nó không đòi mọi request có body size và method khác nhau phải có cùng latency.

### 2.2. HMAC không thay TLS và replay defense

HMAC kiểm tra tính toàn vẹn và tính xác thực theo shared secret. Nó không mã hóa URI, headers hay body. TLS vẫn cần bảo vệ đường truyền. Một request hợp lệ có thể bị phát lại nguyên vẹn và cho **cùng HMAC tag**, vì vậy cần timestamp/nonce và replay store.

## 3. “Constant-time” nghĩa là gì?

Trong mật mã, mục tiêu constant-time thường được hiểu là tránh để **giá trị bí mật** chi phối các nhánh/đường truy cập bộ nhớ và thời gian thực thi có thể quan sát. Với HMAC-SHA256 full tag, phép so được thiết kế để không dừng ở vị trí byte đầu tiên sai.

Một cấu trúc minh họa:

~~~java
// Minh họa ý tưởng xử lý đủ byte; ưu tiên API thư viện khi triển khai.
static boolean fullScan(byte[] expected, byte[] supplied) {
    if (expected.length != supplied.length) {
        return false; // Tag length hợp lệ là thông tin contract công khai.
    }

    int diff = 0;
    for (int i = 0; i < expected.length; i++) {
        diff |= expected[i] ^ supplied[i];
    }
    return diff == 0;
}
~~~

Ở mức source, vòng lặp không thoát sớm vì byte sai. Nhưng không thể suy rằng JVM/JIT/CPU chắc chắn thực thi **cùng số chu kỳ** từ mỗi giá trị bí mật. Source-level full scan và machine-level timing behavior là hai mức đánh giá khác nhau.

### 3.1. Java 17: MessageDigest.isEqual

Trong Java, lựa chọn tiêu chuẩn cho tag/digest bytes là:

~~~java
import java.security.MessageDigest;

boolean macMatches = MessageDigest.isEqual(expectedTag, suppliedTag);
~~~

API này thích hợp hơn một vòng lặp tự viết thoát sớm hoặc phép so chuỗi hex/Base64URL. Khi sử dụng:

- Kiểm tra **tag length cố định** theo hợp đồng: HMAC-SHA256 đầy đủ = 32 byte.
- Decode chữ ký về `byte[]` trước khi so.
- Đừng so `expectedHex.startsWith(presentedHex)` hoặc chỉ 8/16 byte prefix.
- Đừng tuyên bố phép gọi này bảo đảm constant-time **cho toàn bộ verifier, JVM và HTTP endpoint**.
- Đọc tài liệu API/JDK version được triển khai; độ dài mảng và các bước trước/sau compare có thể ảnh hưởng tổng thời gian.

### 3.2. Vì sao không chọn String.equals / Arrays.equals?

~~~java
// Không nên dùng làm comparator HMAC tag:
boolean a = expectedHex.equals(presentedHex);
boolean b = java.util.Arrays.equals(expectedTag, suppliedTag);
~~~

Các phép so sánh thông thường có thể tối ưu hiệu năng và dừng ngay khi phát hiện sai khác. Hơn nữa, so chuỗi có thể bị ảnh hưởng bởi uppercase/lowercase hex, Base64URL padding hoặc biểu diễn không canonical. Nên **validate encoding**, decode và **so toàn bộ tag bytes**.

### 3.3. Public-length check khác secret-dependent early exit

Nếu signature dài 20 ký tự trong khi contract yêu cầu đúng 43 ký tự Base64URL của HMAC-SHA256, verifier có thể từ chối ở bước format. Caller vốn biết độ dài mình đã gửi. Rủi ro chính của early-exit compare là thời gian phản ánh **nội dung expected tag** khi cả hai tag đều đúng độ dài.

Điều này không có nghĩa mọi early error đều an toàn: response có thể tiết lộ key tồn tại, scope hoặc trạng thái revoked nếu thiết kế sai. Nhưng đó là **những oracle khác**, không đồng nhất với leak do prefix comparison.

## 4. Ba tầng đo timing cần phân biệt

### 4.1. Comparator-only

~~~text
expected[32] + supplied[32]
           |
   MessageDigest.isEqual
           |
        true/false
~~~

Đây là thí nghiệm cô lập so byte tag. Nó bỏ qua parsing, HMAC computation, secret manager, HTTP và network. Nhờ vậy dễ kiểm tra sự phụ thuộc vào vị trí byte sai hơn, nhưng không phản ánh latency cuối cùng của API.

### 4.2. Verifier in-process

~~~text
HTTP adapter
  -> parse signature/keyId/timestamp/nonce
  -> key registry lookup
  -> canonicalize path/query/headers
  -> SHA-256 raw body
  -> HMAC-SHA256 expected tag
  -> decode/compare
  -> freshness, nonce gate
~~~

Thời gian có thể bị chi phối bởi body hashing, key cache, parser hoặc shared nonce store. Chênh lệch giữa “signature sai định dạng” với “HMAC tag sai” không nhất thiết là rò rỉ do comparator; hai nhóm có thể đi qua **những đoạn code khác nhau**.

### 4.3. HTTP end-to-end

~~~text
Client -> TCP/TLS -> load balancer -> WAF/API gateway
       -> HTTP server -> verifier -> application
       -> response network -> Client
~~~

Network round-trip, connection reuse, queueing, WAF, backend node và cache đều tạo nhiễu. Một chênh lệch rất nhỏ bên trong comparator có thể khó nhìn thấy ở tầng ngoài, nhưng **nhiễu không phải cơ chế bảo vệ mật mã đáng tin**.

| Tầng | Có thể tìm được | Không thể suy ra |
| --- | --- | --- |
| Comparator-only | Dấu hiệu vị trí byte sai ảnh hưởng phép compare | Cả HTTP service an toàn |
| Verifier in-process | Khác biệt giữa các bước của verifier | Attacker Internet chắc chắn quan sát được |
| HTTP end-to-end | Phân phối độ trễ từ một vantage point | Không có leak ở mọi network/hardware/runtime |

## 5. Nguồn nhiễu khi đo trên Java 17

### 5.1. JIT, tiered compilation và warm-up

JVM có thể chuyển từ interpreted code sang compiled code, inline methods, thay đổi branch profiling hoặc deoptimization. Vì thế 1.000 phép đo đầu tiên có thể phản ánh quá trình warm-up chứ không đại diện hành vi ổn định.

Một harness tốt nên có warm-up, nhiều lượt đo, lưu runtime/JDK version và không để các nhóm luôn được đo theo một thứ tự cố định.

### 5.2. Garbage collection và allocation

Nếu mỗi phép thử tạo `String`, decode Base64URL, cấp `byte[]` mới, log kết quả hoặc tạo exception, thời gian allocation/GC có thể lấn át comparator.

- Đo comparator: tạo sẵn mảng byte ngoài vùng đo.
- Đo verifier: chấp nhận allocation là một phần pipeline nhưng phân tích riêng.
- Ghi nhận GC pauses/pressure khi có thể.
- Không gán mọi outlier cho secret-dependent comparison.

### 5.3. CPU, memory, scheduler

Nguồn nhiễu gồm cache/TLB, branch prediction, DVFS/Turbo Boost, nhiệt độ, SMT/hyper-threading, context switches, thread migration, VM noisy neighbors, OS interruptions và microcode. Source code có vòng lặp số bước cố định **không phải chứng minh** số chu kỳ máy luôn bằng nhau.

### 5.4. Timer resolution và overhead

`System.nanoTime()` trả về đơn vị nanosecond để đo **thời gian tương đối**, nhưng không cam kết độ phân giải/độ chính xác 1 ns thực tế. Mỗi lần gọi timer có chi phí; một thao tác compare ngắn có thể mất thời gian tương đương hoặc nhỏ hơn overhead đo.

Không đọc kết quả `25 ns` rồi khẳng định phép so chạy **chính xác 25 nanosecond** trên mọi CPU.

### 5.5. Network/proxy noise

| Thành phần | Nguồn biến thiên |
| --- | --- |
| TCP/TLS | Handshake, keep-alive, congestion, retransmission |
| Gateway | Rate limit, WAF, tracing, header/path rewrite |
| Load balancer | Route tới node khác, queue size khác |
| HTTP server | Thread pool saturation, request buffering |
| Key registry | Cache hit/miss, secret manager latency |
| Replay store | Network RTT, shard contention, store failure |
| JVM | GC, JIT, class loading |
| Business layer | DB, authorization và response generation |

Chỉ đo response time của hai HTTP request khác input chưa đủ để kết luận nguyên nhân chênh lệch.

## 6. Không thấy chênh lệch không chứng minh an toàn

Giả sử thí nghiệm quan sát:

~~~text
Group A (sai byte đầu):    median 4.8 ms
Group B (sai byte cuối):   median 4.9 ms
Observed difference:       0.1 ms
~~~

Kết quả này **không đủ để khẳng định** comparator constant-time hoặc chênh lệch đến từ so tag. Có thể mạng nhiễu lớn, sample size nhỏ, time drift, key cache khác nhau hoặc các request đi tới node khác.

### 6.1. Ba cách diễn đạt

| Bằng chứng | Cách diễn đạt phù hợp |
| --- | --- |
| Code có early exit theo vị trí byte sai | Có nguồn rò rỉ ở cấu trúc code cần sửa |
| Benchmark không phát hiện khác biệt | Chưa quan sát khác biệt đủ rõ trong điều kiện đo |
| Nhiều kiểm thử + review thư viện/runtime | Tăng độ tin cậy về biện pháp giảm rò rỉ, không chứng minh tuyệt đối |

### 6.2. p-value lớn không chứng minh hai nhóm bằng nhau

Nếu một kiểm định trả `p = 0.6`, điều đó không chứng minh hai timing distributions giống hệt nhau. Có thể phép thử thiếu power hoặc dữ liệu có nhiễu lớn. Để đánh giá một mức **tương đương trong sai số cho phép**, phải định nghĩa equivalence margin, độ nhạy và confidence bounds.

### 6.3. Cỡ mẫu không có con số cố định

Cỡ mẫu phụ thuộc signal size, variance, heavy tails, vị trí đo, confidence/power và số nhóm. Một comparator thoát sớm nghiêm trọng có thể dễ quan sát cục bộ; một chênh lệch nhỏ qua Internet có thể cần lượng mẫu lớn. Không đưa ra quy tắc “chạy đúng 1.000 lần là đủ”.

### 6.4. Outlier không thể loại bỏ tùy ý

GC pauses, context switches hoặc retransmission tạo outliers. Nếu chỉ xóa mẫu của một nhóm sau khi xem kết quả, sẽ gây bias. Đặt trước quy tắc lọc hoặc phân tích robust, công bố phần dữ liệu bị loại và lý do.

## 7. Thiết kế thí nghiệm cho đúng câu hỏi

Một giả thuyết kiểm thử rõ:

> “Với expected HMAC-SHA256 tag cố định dài 32 byte và các supplied tags cũng dài 32 byte, thời gian compare có phụ thuộc vị trí byte đầu tiên sai hay không?”

### 7.1. Các nhóm input có kiểm soát

~~~text
expected:  32 byte cố định

A: sai duy nhất ở byte 0
B: sai duy nhất ở byte 15
C: sai duy nhất ở byte 31
D: khớp toàn bộ
~~~

Các nhóm A/B/C cùng length, cùng số byte khác biệt và khác **vị trí**. Nếu nhóm A có 16 byte còn nhóm C 32 byte, ta đang đo cả length handling nên không cô lập được prefix leak.

Nhóm D (tag đúng) hữu ích cho correctness, nhưng trong HTTP end-to-end nó có thể tiếp tục tới replay store/authorization, khiến latency khác mạnh. Để đo comparator, nên tách nhóm này khỏi các nhánh nghiệp vụ.

### 7.2. Randomization/counterbalancing

Cách đo dễ nhầm:

~~~text
100.000 lần A
100.000 lần B
100.000 lần C
~~~

JVM/JIT, nhiệt độ CPU và cache có thể thay đổi theo thời gian. Nên trộn hoặc cân bằng các nhóm, dùng nhiều lượt xen kẽ, ghi seed để tái lập. Giữ số mẫu giữa các nhóm tương tự nhau.

### 7.3. Tách setup khỏi vùng đo

Trong comparator-only benchmark:

- Tạo sẵn `expected` và `supplied`.
- Không decode signature, không tạo Random/byte arrays bên trong khoảng đo.
- Không log hay in console trong mỗi lần compare.
- Đảm bảo output được dùng để tránh dead-code elimination.
- Dùng warm-up và kiểm thử các trường hợp đúng/sai trước khi đo.
- Thử nhiều runtime/CPU nếu kết luận ảnh hưởng tới hệ thống có nhiều môi trường triển khai.

### 7.4. Correctness trước timing

Phải chứng minh:

~~~text
expected vs expected          => true
expected vs wrong byte 0      => false
expected vs wrong byte 15     => false
expected vs wrong byte 31     => false
expected vs truncated tag     => false theo contract
invalid Base64URL             => reject
~~~

Một comparator luôn trả `false` có thể đo được thời gian gần đều nhưng hoàn toàn không có giá trị xác minh HMAC.

## 8. Java 17: helper so tag an toàn hơn

Hợp đồng minh họa: client gửi **full HMAC-SHA256 tag** 32 byte, mã hóa thành **43 ký tự Base64URL không padding** trong `X-Signature`.

~~~java
import java.security.MessageDigest;
import java.util.Base64;
import java.util.regex.Pattern;

public final class SignatureCheckV1 {
    private static final Pattern FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private SignatureCheckV1() {}

    public static boolean matches(
            byte[] expectedTag, String presentedSignature) {

        if (expectedTag == null || expectedTag.length != 32
                || presentedSignature == null
                || !FORMAT.matcher(presentedSignature).matches()) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag =
                    Base64.getUrlDecoder().decode(presentedSignature);
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        if (suppliedTag.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(suppliedTag)
                        .equals(presentedSignature)) {
            return false;
        }

        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }
}
~~~

**Giới hạn cố ý của helper:**

- Hàm chỉ so tag, **không** tra secret, tính HMAC, kiểm tra timestamp/nonce hoặc authorization.
- Header duplicate phải bị HTTP adapter từ chối trước khi gọi helper; không chọn first/last value.
- Signature format/độ dài sai có thể bị từ chối sớm. Điều đó không tiết lộ prefix của expectedTag.
- Không dùng `String.equals` thay vì so byte mật mã sau decode.
- Chỉ chấp nhận một encoding/version; không tự thử hex hay Base64 khác đến khi khớp.

### 8.1. Tính expected HMAC trước khi compare

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ExpectedHmacV1 {
    private ExpectedHmacV1() {}

    public static byte[] calculate(
            byte[] trustedSecret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes);
    }
}
~~~

Verifier thực hiện:

~~~java
byte[] expectedTag = ExpectedHmacV1.calculate(
        secretFromTrustedKeyRegistry,
        canonicalBytesRebuiltFromReceivedRequest);

boolean macValid =
        SignatureCheckV1.matches(expectedTag, signatureHeader);
~~~

Không tin expected tag hoặc canonical string do caller tự đưa vào một header. Nếu server dùng digest body, phải hash **raw body bytes thực nhận**; không lấy digest do client khai làm nguồn sự thật.

## 9. Java 17: benchmark local minh họa giới hạn

Ví dụ này không được xem là test chứng minh constant-time; nó chỉ minh họa cách thiết lập input và tránh một số sai lầm phổ biến.

~~~java
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public final class LocalTimingDemo {
    private static volatile int sink;
    private static final int GROUPS = 3;
    private static final int SAMPLES = 10_000;

    public static void main(String[] args) {
        byte[] expected = new byte[32];
        Arrays.fill(expected, (byte) 0x5a);

        byte[][] cases = new byte[GROUPS][];
        for (int g = 0; g < GROUPS; g++) {
            cases[g] = expected.clone();
        }
        cases[0][0] ^= 1;
        cases[1][15] ^= 1;
        cases[2][31] ^= 1;

        // Warm-up cho cả ba nhóm.
        for (int i = 0; i < 100_000; i++) {
            boolean result = MessageDigest.isEqual(
                    expected, cases[i % GROUPS]);
            sink ^= result ? 1 : 0;
        }

        long[][] timings = new long[GROUPS][SAMPLES];
        int[] counts = new int[GROUPS];
        List<Integer> order = new ArrayList<>(GROUPS * SAMPLES);
        for (int k = 0; k < SAMPLES; k++) {
            for (int g = 0; g < GROUPS; g++) {
                order.add(g);
            }
        }

        // Seed cố định để tái lập thứ tự; không phải nonce RNG.
        Collections.shuffle(order, new Random(2026L));

        for (int group : order) {
            long start = System.nanoTime();
            boolean result = MessageDigest.isEqual(
                    expected, cases[group]);
            long elapsed = System.nanoTime() - start;

            sink ^= result ? 1 : 0;
            timings[group][counts[group]++] = elapsed;
        }

        for (int g = 0; g < GROUPS; g++) {
            Arrays.sort(timings[g]);
            System.out.println("Group=" + g
                    + " median(ns)="
                    + percentile(timings[g], 50)
                    + " p90(ns)="
                    + percentile(timings[g], 90));
        }
        System.out.println("sink=" + sink);
    }

    private static long percentile(long[] sorted, int p) {
        int index = (int) Math.ceil(
                sorted.length * p / 100.0) - 1;
        return sorted[Math.max(0, index)];
    }
}
~~~

### 9.1. Có thể học được gì từ demo?

- Ba nhóm cùng độ dài tag và chỉ khác vị trí byte sai.
- Input được cấp phát trước khoảng đo.
- Các nhóm được trộn thay vì đo thành ba khối lớn.
- Có warm-up.
- Có sử dụng kết quả qua biến `volatile` để hạn chế một dạng dead-code elimination.

### 9.2. Không thể kết luận điều gì?

- Không thể kết luận precision của timer là 1 ns.
- Không thể chứng minh Java/JIT/CPU bảo đảm constant-time.
- Không thể suy ra attacker từ xa có thể hoặc không thể đo được signal.
- Không thể suy ra toàn bộ HTTP verifier constant-time.
- Không thể xác định ý nghĩa thống kê chỉ bằng ba trung vị in ra.

Để đo hiệu năng Java nghiêm túc hơn, có thể dùng **JMH** với warm-up, fork và benchmark discipline tốt hơn. Nhưng JMH vẫn không thay thế security review hoặc phép phân tích leakage có threat model rõ.

## 10. Diễn giải thống kê đúng mức

### 10.1. Không chỉ nhìn một trung bình

Một báo cáo nên ghi:

- Số mẫu và cách chọn mẫu.
- Runtime/JDK, JVM flags, OS, CPU, môi trường tải.
- Vantage point và liệu có proxy/gateway.
- Warm-up/fork/run count, randomization order.
- Distribution, median, quantiles, spread và outliers.
- Chênh lệch giữa nhóm với effect size và khoảng tin cậy thích hợp.
- Các biến đã cố định và các giới hạn còn lại.

Hai nhóm có thể có **cùng median nhưng khác tails**. Trung bình có thể bị vài outlier kéo lệch. Nên xem nhiều thống kê thay vì chỉ một con số.

### 10.2. Kiểm định không phải bằng chứng tuyệt đối

Các phương pháp như Welch's t-test, permutation test hoặc bootstrap confidence intervals có thể hỗ trợ nếu dữ liệu và giả định phù hợp. Nhưng:

- Độ trễ HTTP thường có heavy tails, outliers và serial dependence.
- Nhiều nhóm/byte positions tạo multiple-comparison problem.
- `p < 0.05` không tự nói hiệu ứng là rủi ro thực tiễn.
- `p > 0.05` không chứng minh hai phân phối bằng nhau.
- Muốn đánh giá equivalence cần **ngưỡng khác biệt chấp nhận được**, cỡ mẫu và độ nhạy phù hợp.

Nếu điều chỉnh loại outliers hoặc phương pháp cho tới khi có kết quả đẹp, báo cáo có thể bị bias. Nên nêu trước kế hoạch thí nghiệm và ghi lại thay đổi.

### 10.3. “Không phát hiện” khác “không tồn tại”

Ví dụ cách diễn đạt tốt:

> “Với N mẫu tại môi trường JVM/JDK và network đã nêu, thí nghiệm chưa phát hiện chênh lệch timing đủ rõ giữa các nhóm. Kết quả không loại trừ một tín hiệu nhỏ hơn khả năng đo hoặc rò rỉ trong môi trường khác.”

Không dùng:

> “Đã chứng minh endpoint không thể bị timing attack.”

## 11. Những giới hạn của đo từ xa

Đo HTTP từ xa thường chịu:

- TCP/TLS handshake hoặc connection reuse.
- WAF/rate limiter và API gateway filters.
- Load balancing tới các node khác nhau.
- Secret manager/cache hit hoặc miss.
- Thread scheduling và JVM GC.
- Replay store RTT và contention.
- Authorization/DB và response formatting.
- Network jitter, retransmissions và OS buffering.

Nếu so request **HMAC đúng** với request **HMAC sai**, request đúng có thể đi tiếp tới replay gate và business logic. Thời gian khác nhau **không thể quy trực tiếp** cho so sánh tag.

Để đo vị trí byte sai ở tầng verifier, các request nên sai HMAC và có cùng cấu trúc, cùng key/URI/body, cùng signature encoding hợp lệ, chỉ khác vị trí byte tag. Nhưng ngay cả vậy, key cache/network/gateway vẫn có thể tạo nhiễu.

### 11.1. Attacker model quyết định độ tin cậy

Phải xác định attacker có thể:

1. Gửi bao nhiêu request trước khi rate-limited?
2. Lặp lại cùng canonical request trong cửa sổ timestamp?
3. Quan sát status/body khác nhau hay chỉ độ trễ?
4. Đặt request từ Internet xa, cùng vùng cloud hay máy cục bộ?
5. Đi qua gateway ổn định hay nhiều nodes?
6. Thử trong thời gian dài và thu thập phân phối không?

Không nên lấy “latency Internet rất nhiễu” làm lý do không sửa comparator early exit. Một attacker gần hơn hoặc có nhiều mẫu có thể có điều kiện đo khác với người kiểm thử.

### 11.2. Nonce không thay constant-time comparison

Một số hệ thống chỉ ghi nonce vào replay store **sau MAC hợp lệ** để không cho attacker làm bẩn nonce store. Khi đó request **MAC sai** vẫn có thể tới phép compare trước khi bị từ chối. Do vậy, timestamp/nonce giảm replay nhưng không thay biện pháp so tag an toàn.

Rate limiting, generic errors và monitoring cũng là lớp bổ trợ; chúng không biến một comparator branch-dependent thành constant-time.

## 12. Thời gian key lookup, status và oracle khác

Ví dụ:

~~~text
keyId không tồn tại  -> từ chối nhanh
keyId ACTIVE         -> tìm secret + HMAC + compare
keyId REVOKED        -> nhánh policy khác
~~~

Các nhánh có thể tạo timing khác nhau. Điều này **không nhất thiết là leak byte tag**, nhưng có thể tiết lộ trạng thái credential ngoài mức hệ thống muốn công bố.

Biện pháp có thể gồm:

- Generic authentication errors ở bên ngoài.
- Giới hạn tốc độ và giám sát hành vi thử key ID.
- Key registry lookup nhất quán, cache policy rõ.
- Không log/return expected signature hoặc secret.
- Khi threat model yêu cầu, đánh giá dummy MAC path cho unknown keys như một phương án có rủi ro/cost riêng; không cho dummy key xác thực thành công.

Không phải mọi hệ thống đều cần làm toàn bộ key lookup chạy bằng nhau tuyệt đối. Phải xác định **thông tin nào nhạy cảm** và mức độ rủi ro thực tế.

### 12.1. Vì sao không thêm random sleep để che khác biệt?

~~~java
// Ví dụ phản tác dụng: không sửa được early-exit compare.
Thread.sleep(randomDelayMillis);
return unauthorized;
~~~

Random delay có thể tăng noise nhưng không bỏ nguyên nhân rò rỉ; nhiều phép đo có thể trung bình hóa noise, đồng thời delay tăng tải và mở rộng khả năng DoS. Ưu tiên sửa compare, kiểm soát lỗi và giảm oracle rõ ràng.

## 13. HMAC canonical request cũng ảnh hưởng timing

Ví dụ contract ký:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256>

{"orderId":"order-42"}
~~~

Canonical text minh họa:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
currency=VND
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<sha256-of-raw-body>
~~~

Server phải:

1. Xác định method/path/query và signed headers ở ranh giới HTTP tin cậy.
2. Tính SHA-256 của **đúng raw body bytes** theo contract.
3. Tạo canonical bytes UTF-8, LF và thứ tự fields xác định.
4. Tra exact key ID và secret record.
5. Tính expected HMAC-SHA256, decode presented signature rồi so tag bytes.
6. Kiểm tra timestamp/nonce và authorization trước khi business handler chạy.

Một request body 1 MB thường tốn nhiều chi phí hashing hơn một request body 20 byte. Đó là biến thiên theo **kích thước dữ liệu**, không tự chỉ ra comparator rò rỉ prefix.

### 13.1. Parser differential quan trọng hơn timing trong nhiều trường hợp

Nếu verifier normalize `/v1/orders/` thành `/v1/orders` nhưng router phân biệt hai path, HMAC có thể đúng trên một representation trong khi handler thực thi representation khác. Tương tự, duplicate query `tenant=A&tenant=B` có thể được xử lý first-wins/last-wins khác nhau.

Constant-time comparison **không sửa canonicalization/routing/authorization mismatch**. Phải test end-to-end và đặt hợp đồng path/query/header rõ ràng.

## 14. Replay, rotation và authorization trong phép đo

### 14.1. Replay gate thêm nhánh timing riêng

Với signed timestamp/nonce:

~~~text
x-timestamp:<unix-seconds>
x-nonce:<random-identifier>
~~~

Server phải kiểm tra timestamp window và ghi nonce bằng **atomic put-if-absent** trên shared store **chỉ sau khi HMAC hợp lệ**.

Các nhóm:

| Trường hợp | Đường xử lý có thể khác |
| --- | --- |
| Signature malformed | Reject ở parser |
| Signature có format đúng nhưng MAC sai | Tính HMAC + compare rồi reject |
| MAC đúng, timestamp quá hạn | Reject freshness |
| MAC đúng, nonce đã thấy | Replay store → reject |
| MAC đúng, nonce mới | Replay gate → principal/authorization |
| MAC đúng, thiếu quyền | Authorization reject |
| MAC đúng, đủ quyền | Business handler |

Do chúng đi qua các bước khác nhau, không lấy chênh lệch latency giữa những nhóm này để kết luận riêng về comparator.

### 14.2. Key rotation

~~~text
partner-a-k2 -> RETIRING, secret v2
partner-a-k3 -> ACTIVE,   secret v3
~~~

Verifier phải chọn **đúng secret theo key ID**; không thử mọi secret đến khi tag khớp. Cache và trạng thái key có thể tạo timing khác, nhưng đây là bài toán **key lifecycle/policy**, không phải phép so tag.

### 14.3. Authentication khác authorization

Client A có secret hợp lệ vẫn có thể ký một request `DELETE` nhắm tới tenant B. HMAC match có thể đúng, timestamp/nonce mới, nhưng authorization phải kiểm tra principal/action/resource/tenant rồi **từ chối** nếu không đủ quyền.

Không dùng `X-Role` hay `X-Tenant-Id` tự khai làm nguồn cấp quyền, kể cả khi header có HMAC ký.

## 15. Proxy/gateway và giới hạn đo qua mạng

~~~mermaid
sequenceDiagram
    participant C as Tester/Client
    participant G as Gateway/WAF
    participant V as HMAC verifier
    participant R as Replay store
    participant A as Application

    C->>G: HTTPS request + signed fields
    Note over G: TLS, queues, routing, rewrite, rate limits
    G->>V: Forward request
    V->>V: Canonicalize + expected HMAC + tag comparison
    V->>R: Nonce put-if-absent sau MAC hợp lệ
    R-->>V: inserted hoặc replay
    V->>A: Authenticated principal
    A->>C: HTTP response
~~~

Mô hình đơn giản:

~~~text
T_observed ~ T_network + T_gateway + T_queue + T_parse
           + T_key_lookup + T_canonicalize + T_hmac
           + T_compare + T_replay + T_authorization
           + T_response
~~~

Đây là sơ đồ suy luận, **không phải công thức cộng đo tuyệt đối** khi hệ thống có parallel processing/pipelining.

Nếu gateway thay prefix path, trailing slash, query escaping hoặc JSON body thì signer/verifier có thể dùng **canonical bytes khác nhau**. Lỗi HMAC phát sinh do signed semantics, không thể sửa bằng tăng jitter hoặc đổi phép thống kê.

Khi verifier đặt tại gateway, cần bảo vệ context/principal nội bộ sau xác thực. Khi verifier đặt tại backend, gateway phải giữ nguyên signed fields hoặc áp dụng mapping có version đáng tin. Không tin `X-Original-URI` hoặc `X-Forwarded-Host` do caller tự khai.

## 16. Ma trận kiểm thử giới hạn timing

| Nhóm | Test | Mục tiêu |
| --- | --- | --- |
| Correctness | Tag 32 byte đúng | So tag trả true |
| Correctness | Sai byte đầu | Trả false |
| Correctness | Sai byte giữa | Trả false |
| Correctness | Sai byte cuối | Trả false |
| Correctness | Tag ngắn | Reject theo contract |
| Correctness | Base64URL sai | Reject trước compare |
| Comparator timing | Các tag 32 byte sai 1 byte tại vị trí khác | So phân phối, không chỉ một mẫu |
| Comparator timing | Early-exit comparator minh họa | Nhận diện nguồn phụ thuộc prefix |
| Comparator timing | `MessageDigest.isEqual` | Đánh giá trong phạm vi API; không chứng minh toàn bộ HTTP |
| JVM | Có/không warm-up | Nhận diện JIT effects |
| JVM | Nhiều allocation trong vùng đo | Nhận diện GC noise |
| CPU | Máy đang chịu tải | So tác động scheduling/cache |
| Timer | Phép so cực ngắn | Xem overhead/quantization |
| Design | Đo từng nhóm tuần tự | Phát hiện time drift |
| Design | Randomized order | Giảm confounder thứ tự |
| Statistics | Cỡ mẫu nhỏ | Không khẳng định không có leak |
| Statistics | p-value cao | Không suy ra equivalence |
| Statistics | Nhiều groups/byte positions | Chú ý multiple comparisons |
| Verifier | Unknown key ID | Review status/timing oracle |
| Verifier | Tag format sai vs tag byte sai | Không quy chênh lệch parser cho comparator |
| Verifier | Body 1 KB vs 1 MB | Hashing cost thay đổi |
| Verifier | MAC đúng vs MAC sai | Branch replay/authorization khác |
| HTTP | TCP connection reuse thay đổi | Chú thích điều kiện kết nối |
| HTTP | Different gateway nodes | Ghi nhận routing/node effect |
| HTTP | WAF/rate limiting | Thống kê có thể bị chi phối bởi policy |
| HTTP | Proxy path/body rewrite | Kiểm tra canonicalization khác |
| Replay | Nonce lặp | Reject theo atomic replay gate |
| Rotation | k2/k3 overlap | Chọn secret chính xác theo key ID |
| Authorization | Client A gọi tenant B | Reject quyền dù MAC đúng |

### 16.1. Test thời gian phải có functional validation

Không có ích nếu một comparator chạy nhanh và đều vì nó **luôn trả false**. Test phải chứng minh:

- Tag đúng được chấp nhận ở bước compare.
- Tag khác ở bất kỳ byte nào bị reject.
- Không nhận prefix/truncated tag.
- Input encoding sai bị reject.
- HMAC đúng vẫn bị replay/authorization gate từ chối khi cần.

### 16.2. Không suy trực tiếp từ 200 OK và 401 Unauthorized

Một request `200 OK` có thể gọi DB và ghi audit; request `401` dừng sau compare. So độ trễ hai trường hợp chủ yếu đo **những nhánh xử lý khác nhau**, không cô lập được byte-level tag comparison.

## 17. Tình huống thực tế: kết luận sai vì gateway và JVM

Một nhóm kiểm thử đo 500 request sai byte đầu và 500 request sai byte cuối trên API ở Internet. Nhóm đầu có trung vị `4,8 ms`, nhóm sau `5,0 ms` và báo “HMAC đã bị timing attack”.

Để kiểm chứng nhận định, cần:

1. **Code review:** Comparator có early exit hoặc dùng API so tag thích hợp?
2. **Điểm đo:** Request đi qua gateway hay instrument trực tiếp comparator?
3. **Đầu vào:** Cùng 32-byte tag length, cùng method/URI/body/key ID, chỉ khác byte tag?
4. **Thứ tự:** Hai nhóm được đo tuần tự hay xen kẽ?
5. **JVM:** Warm-up/GC/JIT, CPU load và runtime version khác nhau?
6. **HTTP:** TLS reuse, load balancer routing, WAF/rate limit có khác?
7. **Thống kê:** Sample size, effect size, spread, confidence interval, outliers và test assumptions?
8. **Kết luận:** Có dấu hiệu từ code hay chỉ một chênh lệch đo được chưa rõ nguồn?

Một báo cáo đúng có thể viết:

> “Thử nghiệm bên ngoài quan sát chênh lệch thời gian, nhưng chưa phân tách được ảnh hưởng của gateway/JVM khỏi phép so tag. Nếu code review xác nhận comparator dừng sớm theo byte bí mật thì cần sửa độc lập với việc đo từ xa có rõ hay không. Sau khi sửa, các lần thử chưa phát hiện tín hiệu rõ trong điều kiện khảo sát; không tuyên bố an toàn tuyệt đối.”

Đây là kết luận trung thực hơn cả “chắc chắn khai thác được” lẫn “không thể khai thác vì mạng nhiễu”.

## 18. Bài tập thực hành

1. **Đọc code:** Giải thích vì sao `insecureEquals` phụ thuộc vị trí byte sai, ngay cả khi phép đo HTTP không thấy chênh lệch.
2. **JUnit correctness:** Viết tests cho `SignatureCheckV1` với tag đúng, sai byte đầu/giữa/cuối, wrong length, malformed Base64URL và null.
3. **Thiết kế thí nghiệm:** Tạo bảng groups, sample count, warm-up, order randomization, JVM/runtime, effect size và tiêu chí kết luận trước khi đo.
4. **Tách biến:** So benchmark comparator-only với verifier gồm parser/HMAC/key lookup. Chỉ rõ những bước tăng noise.
5. **Giải thích p-value:** Một thí nghiệm có `p = 0.5` có được phép nói “constant-time proven” không? Vì sao?
6. **Proxy test:** Qua gateway rewrite `/public/v1/orders` thành `/v1/orders`, xác định signing boundary và vì sao lỗi signature không phải timing leak.
7. **Replay vs compare:** Gửi lại request MAC đúng nhưng nonce đã dùng. Giải thích vì sao bị từ chối không chứng minh HMAC không khớp.
8. **Authorization:** Client tenant A gửi request đã ký tới tài nguyên tenant B. Tách phần authentication, freshness và authorization.

## 19. Checklist đánh giá timing

- [ ] Threat model nêu rõ attacker, vantage point, khả năng lặp request và quan sát response.
- [ ] So tag mật mã dùng API phù hợp như `MessageDigest.isEqual`; không tự dùng prefix/early-exit loop.
- [ ] HMAC-SHA256 tag đầy đủ 32 byte; strict signature encoding/length.
- [ ] Phân biệt public length validation với secret-dependent comparison.
- [ ] Test correctness trước mọi timing test.
- [ ] Các nhóm comparator timing cùng length, chỉ khác vị trí byte sai.
- [ ] Có warm-up, randomized/counterbalanced order và nhiều lượt đo.
- [ ] Tránh allocation/log/encoding trong vùng đo nếu chỉ đo comparator.
- [ ] Ghi JVM/JDK, CPU/OS, GC, load và sample size.
- [ ] Xem distribution/quantiles/effect size/uncertainty, không chỉ mean.
- [ ] Không dùng p-value cao để chứng minh equivalence.
- [ ] Outlier handling được định nghĩa và công bố nhất quán.
- [ ] Phân biệt local primitive, verifier in-process và remote HTTP timing.
- [ ] Không thêm random sleep như biện pháp chính thay cho sửa leak.
- [ ] Key lookup, revoked status, error responses và logs không tạo oracle nhạy cảm ngoài policy.
- [ ] Canonical URI/headers/body và signature encoding được quy định có version.
- [ ] Gateway/parser xử lý đúng signed semantics, không tin proxy metadata tự khai.
- [ ] Timestamp/nonce được ký, replay store nguyên tử sau MAC, TTL đủ dài.
- [ ] Key rotation chọn secret theo exact key ID, không thử nhiều secret tùy tiện.
- [ ] Authorization kiểm tra principal/action/resource/tenant độc lập với compare.
- [ ] Báo cáo có giới hạn kết luận rõ; không khẳng định constant-time tuyệt đối chỉ từ benchmark.

## 20. Câu hỏi tự kiểm tra

1. **Vì sao early-exit compare nguy hiểm?** Thời gian có thể phụ thuộc vị trí byte đầu tiên khác trong tag.
2. **Không thấy timing difference có chứng minh an toàn không?** Không; nhiễu hoặc cỡ mẫu nhỏ có thể che hiệu ứng.
3. **HTTP latency khác nhau có chứng minh comparator leak không?** Không; còn parser, key lookup, GC, network, replay và authorization.
4. **Với Java 17, dùng API nào cho HMAC tag comparison?** `MessageDigest.isEqual` trên tag bytes đã validate.
5. **Sai tag length bị reject nhanh có tự rò bí mật không?** Không mặc nhiên; length hợp lệ là thông tin contract công khai.
6. **Vì sao không so tag bằng `String.equals`?** Có thể không có thuộc tính timing phù hợp và tạo nhập nhằng encoding.
7. **`System.nanoTime()` có độ chính xác tuyệt đối 1 ns không?** Không, đơn vị trả về không bảo đảm precision.
8. **Warm-up làm gì?** Giảm một phần khác biệt do JIT/tiered compilation chưa ổn định.
9. **Vì sao trộn thứ tự groups?** Hạn chế time drift/JVM/CPU làm confounder.
10. **p-value cao có chứng minh timing của hai nhóm bằng nhau không?** Không; phải xét power, effect size và equivalence margin.
11. **Rate limiting hoặc nonce có thay constant-time compare không?** Không; đó là lớp phòng vệ bổ sung.
12. **Có thể sửa leak bằng random sleep không?** Không đáng tin; noise có thể bị lấy trung bình và nguồn leak còn nguyên.
13. **MAC đúng có nghĩa request chưa replay không?** Không; timestamp/nonce cần được kiểm tra.
14. **Đổi key trong rotation có thể làm timing thay đổi không?** Có do lookup/cache/policy; không nên quy trực tiếp cho comparator.
15. **MAC đúng có cho phép client A sửa dữ liệu tenant B không?** Không; authorization luôn kiểm tra quyền thực.
16. **Báo cáo timing test nên nêu gì?** Điều kiện đo, mẫu, các biến, thống kê, mức độ tin cậy và giới hạn kết luận.

## 21. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng xác thực thông điệp bằng shared secret.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests cho HMAC primitive.
- **Java SE 17 API — `java.security.MessageDigest.isEqual`.** API so digest/tag bytes theo ngữ nghĩa của JDK.
- **Java SE 17 API — `javax.crypto.Mac`, `System.nanoTime`.** Primitive HMAC và đồng hồ tương đối dùng trong benchmark.
- **JMH — Java Microbenchmark Harness.** Công cụ benchmark hiệu năng Java; không tự cung cấp chứng minh về timing side-channel.
- **OWASP timing/side-channel testing guidance.** Bối cảnh về kiểm soát rò rỉ timing trong xác thực ứng dụng.

**Kết luận:** **Giới hạn quan trọng nhất của đo timing là độ khó suy ra một thuộc tính bảo mật từ số đo bị ảnh hưởng bởi hàng loạt thành phần khác.** Không thấy chênh lệch trong benchmark không chứng minh constant-time; một khác biệt latency cũng không tự chứng minh phép compare lộ prefix. Để giảm rủi ro, dùng **HMAC tag full-length, strict parsing, primitive so tag phù hợp, canonical request đáng tin**, đồng thời kiểm tra code/runtime, thiết kế phép đo có kiểm soát, diễn giải thống kê trung thực và duy trì replay protection, key rotation, gateway contract, authorization.

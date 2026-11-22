# 11.6 Quản lý IV hoặc nonce khi có nhiều luồng, nhiều tiến trình và khởi động lại

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **IV/nonce là tài nguyên phải quản lý theo vòng đời khóa**, chứ không chỉ sinh một mảng byte lúc gọi `Cipher.init(...)`.
2. Phân biệt yêu cầu **duy nhất (uniqueness)** của AES-GCM, AES-CTR, ChaCha20-Poly1305 và yêu cầu **khó dự đoán (unpredictability)** của IV CBC; không áp dụng một công thức cho mọi mode.
3. Xây cơ chế cấp nonce an toàn cho **nhiều thread trong một JVM**, hiểu giới hạn của `AtomicLong`/`synchronized` khi có nhiều process hoặc nhiều host.
4. Thiết kế **counter bền vững**, kho cấp dải số (range leasing) và phân vùng namespace nonce theo key/worker; biết thứ tự **reserve → durable commit → encrypt**.
5. Giải thích cách xử lý **crash, restart, retry, deploy song song, backup rollback và failover**, và khi nào bắt buộc **rotate sang khóa mới**.
6. Kiểm thử Java 17 với AES-GCM: 1.600 phép mã hóa chạy nhiều thread và ví dụ cấp sequence qua nhiều JVM bằng `FileChannel`/`FileLock` có giới hạn rõ ràng.

## 1. IV/nonce là gì và vì sao xuất hiện vấn đề vận hành?

**IV (Initialization Vector)** và **nonce (number used once)** là tham số khởi tạo của một số chế độ mã hóa. Trong nhiều mode, IV/nonce **được truyền công khai** bên cạnh ciphertext, không cần giấu như khóa. Nhưng **được công khai không đồng nghĩa tùy ý tái sử dụng**.

Xem bản ghi AEAD:

```text
  key K (bí mật)       nonce N (thường công khai)
        \                  /
         \                /
          AES-GCM encrypt(plaintext, AAD)
                        |
                        v
                  ciphertext || tag

  Dữ liệu lưu/truyền:
  [version] [keyId] [nonce] [ciphertext || tag]
```

Khóa `K` có thể dùng để mã hóa nhiều bản ghi theo **chính sách invocation/key usage**. Nhưng với AES-GCM, **cặp (K,N) không được tái sử dụng khi mã hóa hai tập đầu vào khác nhau**. Bản thân `Cipher.getInstance("AES/GCM/NoPadding")` chỉ thực hiện phép mật mã cho từng instance; nó không sở hữu kho cấp nonce toàn hệ thống.

Một hệ thống có thể triển khai đúng một lần mã hóa riêng lẻ nhưng vẫn nguy hiểm khi:

- Hai thread cùng đọc biến `counter = 7` rồi cùng tạo nonce `...0007`.
- Hai process/JVM trên cùng máy mỗi process khởi tạo counter từ `0`.
- Hai container ở hai node dùng cùng key nhưng không phân chia nonce namespace.
- Restart máy khiến counter in-memory trở về `0` trong khi **khóa cũ vẫn được dùng**.
- Backup/restore hoặc failover đưa database sequence về mốc trước đó.
- Retry request sau timeout tạo ciphertext khác nhưng tái sử dụng nonce đã cấp.
- Dùng cùng một nonce key-pair ở một API nội bộ và một job nền do thiếu quản trị chung.

Bài toán thực sự là **bảo đảm yêu cầu của mode trên tất cả phép mã hóa với cùng vật liệu khóa**, xuyên thread, process, node và thời gian tồn tại của khóa.

## 2. Không phải mode nào cũng yêu cầu IV giống nhau

| Chế độ / thuật toán | Yêu cầu chính đối với IV/nonce | Tái sử dụng gây gì? | Ghi nhớ |
| --- | --- | --- | --- |
| **AES-GCM** | Nonce/IV phải duy nhất theo key trong phạm vi và giới hạn chuẩn; 96 bit thông dụng | Có thể phá confidentiality và integrity, dẫn tới giả mạo tag | Chỉ riêng khác plaintext/AAD **không cứu được** việc reuse |
| **AES-CTR** | Không trùng **counter block** nào với cùng key, kể cả qua nhiều thông điệp | Trùng keystream, lộ quan hệ XOR plaintext | Quản lý cả khối counter bên trong một thông điệp |
| **ChaCha20-Poly1305** | Nonce duy nhất dưới cùng key | Tái sử dụng keystream và rủi ro integrity | Không suy ra an toàn chỉ vì nonce 12 byte |
| **AES-CBC** | IV phù hợp tiêu chuẩn CBC, đặc biệt **khó dự đoán**; dùng IV mới | IV lặp hoặc đoán trước có thể lộ thông tin/cấu trúc | Chỉ counter dễ đoán không phải giải pháp chung cho CBC |
| **AES-ECB** | Không dùng IV | Lộ mẫu khối lặp | Không chọn ECB cho mã hóa payload thông thường |

**Duy nhất** và **khó dự đoán** là hai thuộc tính khác nhau. Với cấu trúc GCM deterministic IV, counter tuần tự có thể an toàn nếu thực sự không lặp dưới cùng key và tuân thủ chính sách. Với CBC, một IV chỉ duy nhất nhưng dễ dự đoán **không tự thỏa yêu cầu CBC**. Vì thế đừng dùng cùng một “nonce generator” cho mọi cipher mode mà không phân tích riêng.

### 2.1 Hậu quả tái sử dụng nonce trong GCM và CTR

GCM dùng cơ chế giống CTR cho tính bí mật. Nếu cùng key/nonce tạo cùng keystream cho hai bản tin, ta gặp dạng:

```text
C1 = P1 XOR S
C2 = P2 XOR S

C1 XOR C2 = P1 XOR P2
```

Đây là phép mô tả phần mã hóa CTR tương ứng, không phải toàn bộ định dạng GCM bao gồm tag. Khi biết hoặc đoán một plaintext, có thể rò rỉ dữ liệu của bản tin khác. Với GCM, ảnh hưởng còn nghiêm trọng hơn vì cơ chế xác thực cũng có thể bị tấn công/giả mạo. **Một lần reuse cặp key/nonce có thể là sự cố bảo mật**, không phải chỉ là “xác suất nhỏ có thể bỏ qua”.

Với CTR, NIST SP 800-38A yêu cầu **mỗi counter block dùng để mã hóa dưới cùng key phải khác tất cả counter block khác**, kể cả ở các bản tin khác nhau. Điều này mạnh hơn yêu cầu “nonce đầu thông điệp khác”: còn phải kiểm soát **counter wrap/overflow và độ dài thông điệp**.

### 2.2 IV/nonce khác tag, AAD và key ID

- **Key**: bí mật mật mã; đổi **thực sự sang key material mới** tạo miền duy nhất mới.
- **Nonce/IV**: đầu vào khởi tạo; với GCM cần không lặp trong **mỗi key**.
- **AAD (Additional Authenticated Data)**: metadata được bảo vệ tính toàn vẹn nhưng không mã hóa; **AAD khác nhau không hợp thức hóa nonce trùng**.
- **Tag**: kết quả xác thực AEAD; **tag dài 128 bit không chống được lỗi tái sử dụng nonce**.
- **Key ID/version**: cho ứng dụng biết dùng key nào; **đổi nhãn key ID mà vẫn dùng chính byte key cũ không tạo miền mật mã mới**.

Đừng dựa vào việc `Cipher.init` đôi khi từ chối reuse một key/IV trên **cùng đối tượng Cipher**. API không có khả năng bảo đảm không process/host khác đã dùng cặp đó. Phòng vệ phải đặt tại tầng **quản lý khóa và cấp nonce toàn hệ thống**.

## 3. Hai chiến lược cấp nonce GCM phổ biến

### 3.1 Nonce ngẫu nhiên 96 bit từ CSPRNG

Một cách dùng thông thường:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);
```

Đây là **đoạn mã nhúng**, không phải chương trình độc lập. Với nguồn ngẫu nhiên mật mã tốt, mỗi lần gọi có nonce 96 bit khó dự đoán. Nhưng **ngẫu nhiên không đồng nghĩa duy nhất tuyệt đối**. Sau nhiều phép mã hóa với cùng key, khả năng trùng tăng theo quy luật birthday bound.

Với `q` nonce được sinh gần đều độc lập từ không gian 96 bit:

```text
P(có ít nhất một cặp trùng)
  ≈ q(q-1) / (2 * 2^96)       khi q << 2^48
```

Ví dụ với `q = 1.000.000`, xác suất xấp xỉ `6,3 × 10^-18` nếu các giả định lý tưởng thực sự đúng. Con số này **không phải bảo đảm** của mọi PRNG/VM/provider và không dùng để bỏ qua giới hạn invocation của chuẩn.

NIST SP 800-38D đặt yêu cầu uniqueness và quy định **giới hạn tổng 2^32 lần gọi authenticated encryption trên một key cho construction dựa vào bộ sinh ngẫu nhiên** (và một số cấu hình khác; xem `8.3). Tổng phải tính **mọi instance và mọi process/host** dùng key đó, không phải “2^32 cho từng thread”.

Ưu điểm: không cần một counter toàn cục trên từng lời gọi. Nhược điểm: xác suất trùng không bằng 0, vẫn phải theo dõi tổng số lần gọi/key và kiểm soát số lượng instance, nguồn entropy, key rotation. Đừng trộn tùy hứng **nonce ngẫu nhiên** và **nonce deterministic** dưới cùng key nếu chính sách/tiêu chuẩn đã chọn một construction.

### 3.2 Nonce deterministic = fixed field || invocation counter

Với 96-bit nonce, một cấu trúc thường dùng là:

```text
96 bit nonce = 32 bit fixed field || 64 bit invocation field

bytes:
[ 4 byte fixed ] [ 8 byte sequence ]

N(0) = fixed || 0000000000000000
N(1) = fixed || 0000000000000001
N(2) = fixed || 0000000000000002
...
```

Nếu **fixed field không đổi** trong cùng namespace và sequence **tăng, không quay lại**, mọi nonce khác nhau. NIST SP 800-38D mô tả cấu trúc deterministic với **fixed field** và **invocation field**; phải phân phối các trường sao cho toàn bộ **cặp key + IV** được duy nhất. Cách chia 32+64 là ví dụ minh họa phổ biến, không mặc định phù hợp mọi giao thức và cấu hình.

Mọi writer dùng **cùng key và cùng fixed field** phải có **một nguồn sequence điều phối thực sự chung**. Nếu các writer được cấp **fixed field khác nhau** dưới cùng key, mỗi writer có thể có counter riêng, nhưng bộ cấp fixed field phải quản lý không trùng và ràng buộc với key/worker/epoch.

**Số 64 bit không phải quyền mã hóa vô hạn.** Vẫn phải kiểm tra capacity của invocation field, budget theo chuẩn, lượng dữ liệu mỗi key, tag length, chính sách key rotation và cảnh báo hoạt động. Không bao giờ để counter wrap về `0`.

## 4. Cấp nonce cho nhiều thread trong cùng một JVM

### 4.1 Race condition với biến thường

Ví dụ không an toàn:

```java
long seq = nextSequence;   // Thread A đọc 17; Thread B đọc 17
nextSequence = seq + 1;
return makeNonce(seq);
```

Ngay cả nếu `long` được đọc/ghi nguyên tử, thao tác **read-modify-write** như trên không phải một transaction. Hai thread có thể cùng lấy giá trị. `volatile` đơn thuần cũng không sửa race này.

Với một JVM, dùng:

- `AtomicLong` với tăng có kiểm tra giới hạn;
- hoặc `synchronized`/lock bao quanh **đúng vùng cấp sequence**;
- một allocator **duy nhất cho mỗi key + fixed field**; không tạo allocator mới theo mỗi HTTP request.

`AtomicLong` đảm bảo các thread trong JVM cấp sequence khác nhau, **không** giúp process/JVM khác nhìn chung counter, **không** lưu tiến độ qua restart.

### 4.2 Thực hành 1: nhiều thread dùng chung allocator và key mới

Chương trình sinh **một AES key mới** cho một lần chạy, một fixed field 4 byte cho allocator đó, cấp nonce dạng `4 + 8`, và thực hiện nhiều phép mã hóa AES-GCM với các thread cùng lúc. Đây là bài kiểm thử **một JVM và một vòng đời key ngắn**, chưa phải giải pháp persistence.

Tạo file **`ConcurrentGcmNonceDemo.java`** (Java 17 trở lên):

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class ConcurrentGcmNonceDemo {
    private static final int THREADS = 8;
    private static final int PER_THREAD = 200;
    private static final long KEY_BUDGET = 1_000_000L;

    private static final class Allocator {
        private final byte[] fixedField;
        private final AtomicLong next = new AtomicLong();

        Allocator(byte[] fixedField) {
            if (fixedField.length != 4) throw new IllegalArgumentException();
            this.fixedField = fixedField.clone();
        }

        byte[] take() {
            long sequence = next.getAndUpdate(old -> {
                if (old >= KEY_BUDGET) {
                    throw new IllegalStateException("Rotate key: nonce budget exhausted");
                }
                return old + 1;
            });
            return ByteBuffer.allocate(12)
                    .put(fixedField).putLong(sequence).array();
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey freshKey = generator.generateKey();

        byte[] fixedField = new byte[4];
        new SecureRandom().nextBytes(fixedField);
        Allocator allocator = new Allocator(fixedField);
        Set<String> seen = ConcurrentHashMap.newKeySet();
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                futures.add(pool.submit(() -> {
                    for (int i = 0; i < PER_THREAD; i++) {
                        byte[] iv = allocator.take();
                        if (!seen.add(HexFormat.of().formatHex(iv))) {
                            throw new IllegalStateException("Duplicate nonce!");
                        }
                        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                        cipher.init(Cipher.ENCRYPT_MODE, freshKey,
                                new GCMParameterSpec(128, iv));
                        cipher.updateAAD("record:v1".getBytes(StandardCharsets.US_ASCII));
                        byte[] sealed = cipher.doFinal(
                                "record".getBytes(StandardCharsets.US_ASCII));
                        if (sealed.length != 6 + 16) {
                            throw new IllegalStateException("Unexpected GCM output");
                        }
                    }
                    return null;
                }));
            }
            for (Future<?> future : futures) future.get();
        } finally {
            pool.shutdown();
        }

        System.out.println("threads: " + THREADS);
        System.out.println("encryptions: " + THREADS * PER_THREAD);
        System.out.println("unique nonces: " + seen.size());
        System.out.println("nonce bytes: " + allocator.take().length);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ConcurrentGcmNonceDemo.java
java ConcurrentGcmNonceDemo
```

Đầu ra đã kiểm tra:

```text
threads: 8
encryptions: 1600
unique nonces: 1600
nonce bytes: 12
```

**Tại sao đúng trong phạm vi demo?**

1. `AtomicLong.getAndUpdate` làm thao tác lấy sequence/tăng sequence nguyên tử trong một JVM; lambda chặn khi đến `KEY_BUDGET`. Không bị cấp lại cùng số dù 8 thread chen nhau.
2. Nonce tạo bằng `ByteBuffer.put(fixedField).putLong(sequence)` có đúng **12 byte**, big-endian; fixed field 4 byte + sequence 8 byte.
3. `ConcurrentHashMap.newKeySet()` kiểm tra trùng nonce trong bài test; tập này không phải thành phần bắt buộc của thuật toán ở production khi có chứng minh uniqueness từ allocator.
4. Mỗi phép mã hóa tạo `Cipher` riêng (đối tượng mutable không mặc định thread-safe), dùng tag GCM 128 bit và AAD trước `doFinal`.
5. `Future.get()` lan truyền lỗi bên trong worker, thay vì im lặng in thành công nếu có task thất bại.
6. Dòng cuối `allocator.take().length` **dành thêm một nonce không dùng để mã hóa** chỉ để kiểm tra độ dài 12 byte. “Đốt bỏ” một số sequence là an toàn; không được tái sử dụng số đó về sau.

**Giới hạn cực kỳ quan trọng:** mỗi lần chạy code **tạo một key AES mới** rồi tạo lại counter từ `0`. Vì key mới, demo không chứng minh vấn đề restart khi giữ key cũ; đừng copy `new Allocator(...)` vào service nơi **cùng key được giữ qua restart**. Nếu process khác dùng cùng key, nó không chia sẻ `AtomicLong` và có nguy cơ đụng sequence.

## 5. Nhiều process/JVM hoặc nhiều node: phải phân chia namespace

Một server có thể có 16 thread, 4 JVM worker, nhiều container chạy đồng thời và job batch. Nếu tất cả cùng mã hóa dưới **một key**, thì namespace nonce phải bao phủ **toàn bộ** các writer đó.

Có ba cách tổ chức cơ bản:

### Cách A — Một bộ cấp sequence có giao dịch bền vững

```text
   Java process A ──┐
   Java process B ──┼──> durable/atomic sequence authority
   Java process C ──┘                |
                                    v
                        [nextSequence per keyId]
                                    |
                    unique reserved ranges / values
                                    |
                                    v
                        nonce = fixed || sequence
```

Cơ quan cấp số có thể là một bảng trong database với update/transaction thực sự **tuyến tính và durable**. Mọi process chỉ dùng số đã được **commit thành công**. Điểm then chốt không phải “đã gọi API tăng counter”, mà là **sau mọi crash/failover, hệ thống không thể cấp lại sequence đã được dùng để mã hóa dưới cùng key**.

Nếu dùng DB, phải đánh giá:

- Transaction atomic khi nhiều transaction cập nhật cùng hàng;
- commit bền vững theo mức chịu lỗi đã tuyên bố;
- việc restore snapshot, replica promotion hoặc failover có thể **lùi lại committed sequence** hay không;
- cơ chế giới hạn quota và key rotation;
- cache hoặc queue có lưu range chưa commit không.

Nếu database rollback sau khi một ciphertext với sequence mới đã được gửi ra ngoài, một lần cấp số mới trùng sequence cũ tạo **reuse**, dù lúc trước code gọi transaction thành công.

### Cách B — Cấp phát range trước, dùng trong process sau

Mỗi lần lấy khóa trong database cho từng thông điệp có thể làm tăng latency. Có thể cấp một **dải số không giao nhau**:

```text
   DB durable counter next = 1000

Process A: reserve [1000, 2000) => commit next = 2000
Process B: reserve [2000, 3000) => commit next = 3000

A dùng 1000, 1001, ...
B dùng 2000, 2001, ...

A bị crash ở số 1050:
[1051, 2000) bị bỏ, TUYỆT ĐỐI KHÔNG trả lại pool.
```

Quy tắc:

1. **Commit durable high-water mark trước khi giao range cho process**.
2. Trong mỗi process, cấp số trong range bằng `AtomicLong`/lock cục bộ.
3. Khi range hết, lấy range mới; **không wrap** hoặc lấy lại range cũ.
4. Sau crash, số trong range chưa dùng được xem như đã tiêu tốn; khoảng trống an toàn, còn reuse thì không.
5. Khi không chắc chắn trạng thái đã commit, **không mã hóa**. Không “fallback” sang counter tại RAM hay reset tạm thời.

Một ví dụ SQL **minh họa kiểu PostgreSQL**, không phải đoạn Java tự chạy:

```sql
-- Bảng nonce_state có một row duy nhất cho mỗi key_id đang hoạt động:
-- (key_id PRIMARY KEY, next_seq BIGINT NOT NULL)
-- :lease_size > 0, :per_key_limit là giới hạn theo chính sách.

BEGIN;
UPDATE nonce_state
SET next_seq = next_seq + :lease_size
WHERE key_id = :key_id
  AND next_seq >= 0
  AND next_seq <= :per_key_limit - :lease_size
RETURNING next_seq - :lease_size AS start_inclusive,
          next_seq               AS end_exclusive;
COMMIT;
```

Phải **lấy kết quả sau khi COMMIT thành công**; không có row hoặc commit lỗi thì **không cấp range**. Hợp đồng thực tế phải giải quyết concurrency, durability/replication và failover của database. Đừng đồng nhất một `RETURNING` xuất hiện trong transaction chưa commit với một range đã được cấp chắc chắn.

### Cách C — Fixed field riêng theo writer, counter riêng trong từng vùng

Nếu không muốn một sequence toàn cục trên mỗi lời gọi, có thể cấp **fixed field riêng** cho từng worker/tenant/node **theo cơ chế trung tâm**, rồi mỗi writer quản lý invocation counter của mình:

```text
same key K
  ├─ writer 01: fixed=0x00000001 || local sequence 0,1,2,...
  ├─ writer 02: fixed=0x00000002 || local sequence 0,1,2,...
  └─ writer 03: fixed=0x00000003 || local sequence 0,1,2,...
```

**Không** tự dùng `PID`, hostname, container ordinal hoặc thời gian để mặc định rằng fixed field là duy nhất. Một worker ID có thể được cấp lại khi autoscaling, pod restart hoặc failover. Nếu writer mới được gán lại cùng fixed field và cùng key, nó **phải tiếp tục counter bền vững trước đó**, không được khởi đầu `0`.

Khi fixed field có số bit hữu hạn, cũng phải quản lý hết namespace writer và giới hạn invocation của từng writer, cộng với giới hạn tổng theo key/chuẩn. Nếu mỗi writer có key vật liệu khác nhau được dẫn xuất bằng KDF có domain separation đúng thiết kế, uniqueness trở thành bài toán theo **từng key mới**, nhưng việc cấp key/rotation lại phải được quản lý nhất quán. Đổi keyId mà không đổi byte key không phải key mới.

## 6. Restart/crash: điều quan trọng nhất là thứ tự ghi trạng thái

Hãy xem hai thứ tự:

**Không an toàn:**

```text
read counter = 42
       |
       v
encrypt(key, nonce=42) --> ciphertext đã gửi
       |
       v
update counter = 43 vào storage     <-- crash trước bước này
       |
       v
restart: đọc counter = 42 --> REUSE nonce
```

**Đúng hướng:**

```text
read counter = 42
       |
       v
atomically reserve 42, persist/COMMIT next=43
       |
       v
chỉ khi commit thành công:
encrypt(key, nonce=42) --> ciphertext
       |
      crash
       |
       v
restart: next >= 43, không cấp lại 42
```

Một số **bị cấp nhưng chưa dùng** vì crash là bình thường; **bỏ số tốt hơn tái sử dụng nonce**.

### 6.1 Phân biệt crash, timeout và retry

- **Crash trước commit**: range/sequence chưa được cấp hợp lệ, không được mã hóa trước đó.
- **Crash sau commit, trước encryption**: sẽ có gap; không hoàn trả sequence.
- **Crash sau encryption, trước lưu ciphertext**: sequence đã tiêu tốn; mã hóa lại cần sequence **khác**, dù plaintext giống nhau.
- **Timeout không rõ kết quả**: không thể “lấy lại” nonce cũ với giả định lần trước chắc chắn chưa mã hóa. Hãy cấp nonce mới, còn idempotency của nghiệp vụ xử lý độc lập.
- **Retry khi nhận được kết quả encryption trước đó**: có thể **gửi lại chính ciphertext/tag cũ** theo chính sách retransmission, khác với **thực hiện encryption mới cùng key/nonce**. Chống replay là bài toán giao thức khác, thường dùng message ID/sequence và AAD.

Nếu kho cấp nonce chưa sẵn sàng hoặc không chứng minh được trạng thái mới nhất: **fail closed**, không bắt đầu encryption dưới key hiện tại. Có thể chuyển sang **key epoch mới với key material mới** theo quy trình phục hồi được kiểm soát.

## 7. Thực hành 2: counter bền vững qua nhiều JVM với file lock

Mục đích ví dụ này là quan sát nguyên tắc:

- Duy trì `nextSequence` trong **file lưu trạng thái**.
- Dùng `FileLock` độc quyền khi nhiều process truy cập cùng **một file trên hệ thống file hỗ trợ khóa đúng cách**.
- Dùng một monitor `synchronized` bổ sung để tránh hai thread **trong cùng JVM** tranh chấp `FileLock` (theo Java API, file locks thuộc về cả JVM).
- Ghi **sequence kế tiếp** và gọi `FileChannel.force(true)` trước khi phát nonce.
- Phát hiện size/magic/checksum hỏng và từ chối thay vì tự reset.
- Dùng `CREATE_NEW` khi **khởi tạo một epoch/key mới duy nhất**, tránh vô ý ghi đè file đang có.

**Quan trọng:** đây là mô hình giáo dục trên local filesystem, **không phải production allocator có bảo đảm atomic crash recovery trên mọi FS**. `FileChannel.force(true)` không thay thế database transaction/WAL, CRC32 không bảo vệ trước sửa đổi ác ý, update in-place có rủi ro torn write, việc tạo directory entry có semantics riêng, và `FileLock` phụ thuộc filesystem/OS. Backup rollback hoặc xóa file rồi `init` lại với **cùng key** vẫn có thể gây reuse. Ở production, cần transaction log/durable sequence authority/fencing được đánh giá rõ và trạng thái phải gắn với **đúng key epoch**.

Trong demo, fixed field `0x10203040` chỉ là một giá trị để thấy byte cấu trúc; **không hề quản lý hay lưu AES key**. Nếu áp dụng vào một khóa thực, phải ràng buộc bất biến fixed field, key ID và durable state với **cùng key material**, đồng thời kiểm soát mọi writer.

Tạo file **`DurableGcmSequenceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.zip.CRC32;

public class DurableGcmSequenceDemo {
    private static final Object IN_JVM_GUARD = new Object();
    private static final byte[] MAGIC =
            "GCMSEQ01".getBytes(StandardCharsets.US_ASCII);
    private static final int RECORD_SIZE = 8 + 8 + 4;
    private static final long KEY_BUDGET = 1_000_000L;
    private static final int FIXED_FIELD = 0x10203040; // Demo: one fresh key/epoch.

    private static int checksum(long sequence) {
        CRC32 crc = new CRC32();
        crc.update(ByteBuffer.allocate(8).putLong(sequence).array());
        return (int) crc.getValue();
    }

    private static byte[] record(long next) {
        return ByteBuffer.allocate(RECORD_SIZE)
                .put(MAGIC).putLong(next).putInt(checksum(next))
                .array();
    }

    private static long readNext(FileChannel channel) throws IOException {
        if (channel.size() != RECORD_SIZE) {
            throw new IOException("Invalid state size: fail closed");
        }
        ByteBuffer buf = ByteBuffer.allocate(RECORD_SIZE);
        while (buf.hasRemaining()) {
            int n = channel.read(buf, buf.position());
            if (n <= 0) throw new IOException("Truncated state");
        }
        buf.flip();
        byte[] magic = new byte[MAGIC.length];
        buf.get(magic);
        long next = buf.getLong();
        int expected = buf.getInt();
        if (!Arrays.equals(magic, MAGIC) ||
                expected != checksum(next) || next < 0) {
            throw new IOException("Corrupted state: fail closed");
        }
        return next;
    }

    private static void persist(FileChannel channel, long next)
            throws IOException {
        ByteBuffer buf = ByteBuffer.wrap(record(next));
        while (buf.hasRemaining()) {
            int n = channel.write(buf, buf.position());
            if (n <= 0) throw new IOException("State write failed");
        }
        channel.force(true);
    }

    private static void initializeNewKeyState(Path path) throws IOException {
        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            persist(channel, 0);
        }
    }

    private static long reserve(Path path) throws IOException {
        synchronized (IN_JVM_GUARD) {
            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileLock lock = channel.lock()) {
                long sequence = readNext(channel);
                if (sequence >= KEY_BUDGET) {
                    throw new IOException("Rotate key: budget exhausted");
                }
                // Reserve and force the NEXT sequence before returning this one.
                persist(channel, sequence + 1);
                return sequence;
            }
        }
    }

    private static byte[] iv(long sequence) {
        return ByteBuffer.allocate(12)
                .putInt(FIXED_FIELD).putLong(sequence).array();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: init|next <state-file>");
        }
        Path path = Path.of(args[1]);
        switch (args[0]) {
            case "init" -> {
                initializeNewKeyState(path);
                System.out.println("initialized: true");
            }
            case "next" -> {
                long sequence = reserve(path);
                System.out.println("iv hex: " + HexFormat.of().formatHex(iv(sequence)));
            }
            default -> throw new IllegalArgumentException("Use init or next");
        }
    }
}
```

Biên dịch và chạy ở **thư mục thử nghiệm**, dùng một file state chưa tồn tại (ví dụ tên `demo-state.bin`):

```bash
javac --release 17 DurableGcmSequenceDemo.java
java DurableGcmSequenceDemo init demo-state.bin
java DurableGcmSequenceDemo next demo-state.bin
java DurableGcmSequenceDemo next demo-state.bin
```

Đầu ra đã kiểm tra bằng các lần gọi `java` độc lập:

```text
initialized: true
iv hex: 102030400000000000000000
iv hex: 102030400000000000000001
```

Đây là hai IV **12 byte**, bắt đầu bằng cùng fixed field `10203040` rồi sequence `0` và `1` big-endian. Khác với chương trình `AtomicLong` chỉ giữ trong RAM, hai lần `next` ở **hai JVM khởi chạy độc lập** đọc cùng file state nên chúng nhận hai sequence liên tiếp.

**Vì sao mã có hai loại lock?** `synchronized (IN_JVM_GUARD)` điều phối các thread cùng JVM; `FileChannel.lock()` điều phối các process trên một hệ thống file thực thi file lock tương thích. Java `FileLock` được giữ “on behalf of entire JVM”, không phải mutex thông thường giữa nhiều thread trong một process. Không dựa vào file lock để thay mọi cơ chế đồng bộ trong một JVM.

**Điểm không được bỏ qua:** chương trình có lệnh `init` nhằm trình diễn tạo state cho **một key epoch mới**, không phải “sửa lỗi” khi mất state. Nếu state file hỏng, mất hoặc quay ngược trong backup, **không khởi tạo lại counter từ `0` dưới key cũ**. Hãy dừng encrypt, điều tra, và nếu không thể phục hồi uniqueness thì rotate sang **key material mới**. Việc restore một bản state cũ nhưng checksum vẫn đúng **không bị CRC32 phát hiện**; cần generation/fencing/nguồn sự thật bền vững ở hệ thống ngoài.

### 7.1 Vì sao ví dụ file chưa thể dùng làm allocator sản phẩm?

`FileChannel.force(true)` cố yêu cầu đồng bộ nội dung/metadata xuống thiết bị; nó **không cung cấp atomic transaction bao trùm key state, ciphertext và mọi replica**. File có thể bị torn write, host crash, mất điện, thiết bị không tuân thủ flush, snapshot quay lui hoặc network filesystem không thực thi đúng khóa. Checksum CRC32 nhận biết một số loại hỏng ngẫu nhiên, không phải MAC bảo mật và không chống được rollback nguyên bản hợp lệ.

Nếu một lần `persist` báo lỗi, trong ứng dụng thật phải **fail closed** và đối chiếu durable state trước khi cấp số tiếp; không cố dùng biến `sequence` còn lưu trong RAM. Nếu không thể chứng minh trạng thái **không lùi**, chuyển key epoch mới. Với hệ phân tán và dữ liệu giá trị cao, hãy dùng database/consensus hoặc cơ quan cấp range có **transaction/fencing** thay vì tự chế counter file chia sẻ qua NFS.

## 8. Retry, backup và failover: những trường hợp rất dễ bỏ sót

| Sự kiện | Rủi ro | Chính sách an toàn |
| --- | --- | --- |
| Two threads đồng thời | Cùng thấy sequence | Một allocator atomic trong mỗi JVM |
| Two JVM cùng key | Mỗi process có counter 0 | Shared durable allocator hoặc prefix namespace được cấp phát |
| Container restart | RAM reset, key cũ vẫn dùng | Đọc durable high-water, không khởi động lại 0 |
| Job retry | Mã hóa lại cùng nonce cũ | Nonce mới cho **mỗi encryption mới**; retransmit ciphertext cũ là hoạt động khác |
| Counter/lease reserve trước rồi crash | Bỏ dở một số sequence | **Đốt bỏ range**, không tái sử dụng |
| DB replica failover | Replica thiếu commit nonce đã dùng | Fencing/consistency bảo đảm không mất committed high-water |
| Restore backup | Counter bị lùi | Dừng encryption dưới key cũ, xác minh trạng thái hoặc dùng **key mới** |
| Rollback phần mềm | Version cũ reset schema/key state | Migration có kiểm soát, bảo vệ bất biến counter |
| Blue-green/canary deploy | Hai version dùng cùng key độc lập | Cùng allocator hoặc writer namespaces không trùng |
| Nhiều region active-active | Cùng sequence/fixed field | Phân vùng prefix/key riêng hoặc single durable authority |
| Đổi keyId nhưng không đổi key bytes | Tưởng có namespace mới | **Không**: nonce uniqueness đi theo key material, không phải nhãn |
| Hết budget/counter wrap | Dùng lại nonce | Chặn mã hóa trước hạn, rotate key và version |

### 8.1 Dữ liệu đã mã hóa dưới key cũ thì sao?

Khi rotate key, bản ghi cũ vẫn cần được giải mã bằng **đúng key version cũ và nonce đã lưu** theo chính sách retention. Key rotation không yêu cầu reencrypt ngay mọi bản ghi, nhưng phải tránh lẫn lộn namespace:

```text
encrypted record:
[formatVersion] [keyId] [nonce] [ciphertext || tag]

current encryption key: key-v2
old record key:       key-v1, read-only decrypt
```

Khi key-v1 đã ngừng được phép **encrypt**, không có phép cấp nonce mới dưới key-v1. Có thể giữ quyền decrypt trong thời hạn được phép. Nếu bản ghi có metadata cần ràng buộc (tenant, keyId, record type, version), đưa canonical byte representation vào **AAD** để chống tráo ngữ cảnh; AAD khác không cho phép reuse nonce.

### 8.2 Fencing token và split brain

Nếu hai node cùng tự cho mình là leader của allocator, một distributed lock quá hạn hoặc một replica lag có thể làm **hai phía cấp cùng range**. Một **fencing token/epoch tăng đơn điệu** được kiểm tra bởi tài nguyên nhận ghi giúp chặn writer cũ tiếp tục cập nhật sau khi mất quyền. Chỉ có TTL lock mà không có kiểm tra epoch tại nơi cấp range có thể không đủ.

Nếu lưu counter trong database phân tán, cần biết rõ:
- transaction được commit ở đâu và durability cấp nào;
- failover có thể mất committed writes hay không;
- leader cũ bị ngăn phát range sau khi lease mất hiệu lực thế nào;
- state backup có đi kèm key epoch và high-water đủ mới hay không.

Cùng một key ở hai region chỉ an toàn khi phân phối nonce namespace **toàn cục**. Giải pháp khác là cấp **key material riêng** cho mỗi region/worker qua key management có phân tách miền (domain separation), vẫn cần quản lý uniqueness dưới mỗi key.

## 9. Công thức kiểm soát giới hạn và giám sát

Một hệ thống nên duy trì ít nhất các trường metadata:

| Thuộc tính | Mục đích |
| --- | --- |
| `keyId`, `keyEpoch`, algorithm/mode | Biết namespace của chính **key material** nào đang cấp nonce |
| `fixedField` / worker namespace | Bảo đảm vùng nonce không trùng |
| `nextSequence` / `reservedUntil` | High-water đã commit trước khi encrypt |
| `invocationsUsed` / `keyBudget` | Giới hạn tổng số lần encryption/key và chính sách rotate |
| `stateVersion` / allocator epoch/fencing token | Phân biệt những lần chuyển giao trách nhiệm |
| `lastDurableCommit` hoặc transaction evidence | Hỗ trợ điều tra khi crash/restart/failover |
| `algorithmParams` (IV length, tag length) | Giải mã đúng theo cùng format |
| `createdAt`/rotation state | Quyết định active-encrypt / decrypt-only / retired |

Bộ đếm chỉ để **giám sát** có thể cache bất đồng bộ, nhưng bộ đếm **dùng để đảm bảo uniqueness** không được dựa vào metric hệ thống cuối cùng nhất quán (eventual consistency) chưa commit.

### 9.1 Không có một “ngưỡng GCM cho mọi thiết kế”

NIST SP 800-38D `8 quy định:

- Yêu cầu **uniqueness của IV dưới cùng key** là thiết yếu cho an toàn GCM.
- Với **RBG-based IV** (random construction) và deterministic IV **không dài 96 bit**, giới hạn chung trong `8.3 là **tối đa 2^32 authenticated-encryption invocations/key** trên mọi instance.
- Với **chỉ deterministic IV 96 bit**, ngoại lệ khỏi giới hạn chung đó **không** có nghĩa không giới hạn: còn phải thỏa cấu trúc field, không wrap invocation field, giới hạn số devices/contexts, lượng dữ liệu/key và chính sách an toàn khác.

Ví dụ `KEY_BUDGET = 1_000_000` trong code là **quota giả định của bài học**, không phải định mức chuẩn bắt buộc hay mức tải sản phẩm nên đặt. Cấu hình thật phải được dẫn từ threat model, chuẩn của mode, phạm vi phân phối nonce và kế hoạch rotate.

## 10. Lựa chọn thiết kế theo hoàn cảnh

| Môi trường | Thiết kế khởi đầu có thể cân nhắc | Ràng buộc không thể thiếu |
| --- | --- | --- |
| CLI ngắn hạn, **key mới cho mỗi lần chạy** | CSPRNG 96-bit nonce với tổng số lần gọi/key nhỏ | Không tái dùng key cũ khi restart; tách key version rõ |
| Một JVM, key chỉ sống trong process | AtomicLong + 96-bit deterministic nonce | Một allocator cho mỗi key, không tạo lại trong cùng key epoch |
| Một JVM, key giữ qua restart | Counter durable hoặc cấp range từ DB | Persist/commit **trước encrypt**, không rollback |
| Nhiều JVM trên cùng host | DB atomic sequence hoặc file lock **chỉ khi FS/durability được chứng minh** | Không dùng `synchronized` để phối hợp process |
| Microservices/many nodes | Durable range authority + lease/fencing, hoặc unique key/prefix domain per writer | Không trùng vùng và state không lùi khi failover |
| Multi-region active-active | Region-specific key material, hoặc globally allocated fixed field/ranges | DR/restore, replica promotion và split-brain phải được kiểm thử |
| GCM qua API bên thứ ba | Theo rõ hợp đồng nonce/IV và invocation limits | Đừng assume provider/tầng transport tự cấp nonce duy nhất toàn cục |

Một **thiết kế phù hợp** thường ưu tiên giữ invariant đơn giản: mỗi encryption dưới cùng key có nonce duy nhất, và ta có bằng chứng vận hành rằng invariant đó còn đúng sau lỗi hệ thống. Hệ thống phức tạp không cần tự implement crypto primitive; chỉ cần quản lý đầu vào của primitive đúng cách.

## 11. Kiểm thử có ý nghĩa trước khi production

Test một lần encrypt/decrypt thành công **không chứng minh** nonce allocator an toàn. Nên thử:

1. **Nhiều thread cùng JVM:** cấp hàng nghìn nonce đồng thời; không có trùng; mọi `Future` lỗi phải làm test fail.
2. **Nhiều process/JVM:** chạy song song trên cùng key namespace/allocator. Không có cặp (key,nonce) trùng trong mọi output.
3. **Restart giữ key cũ:** cấp một số nonce, dừng, khởi động lại; số mới phải lớn hơn high-water đã dùng, không reset.
4. **Crash injection ở từng ranh giới:** trước reserve, sau transaction commit, trước encrypt, sau encrypt và trước ghi record. Gap được phép, reuse không được phép.
5. **Mất quyền leader / fencing:** node cũ không được cấp dải mới sau khi mất lease.
6. **Replica failover:** chỉ chấp nhận failover không làm lùi durable high-water cho key cũ; nếu không có bằng chứng, phải rotate key.
7. **Backup rollback:** giả lập restore bản state cũ. Bộ giám sát/thiết kế phải phát hiện hoặc chặn encryption; checksum file đơn giản **không đủ**.
8. **Counter exhaustion:** tại biên quota, hành động là throw/fail closed và rotate, tuyệt đối không wrap về `0`.
9. **Sai key ID/nonce format:** decrypt từ record có metadata bị tráo phải thất bại qua xác thực AAD hoặc policy.
10. **Giám sát:** cảnh báo tỷ lệ used/budget, lỗi cấp range/commit, tăng nhanh số encryption/key, thiếu khóa mới và hệ thống allocator không khả dụng.

Kiểm thử uniqueness theo một đợt hữu hạn là bằng chứng tích cực nhưng **không thay cho chứng minh thiết kế và kiểm thử recovery**. Một counter in-memory có thể qua mọi bài test multithread mà vẫn reuse ngay sau restart.

## 12. Lỗi thường gặp

- **“`SecureRandom.nextBytes(12)` luôn khác nhau.”** Sai: nonce ngẫu nhiên là uniqueness xác suất; cần giới hạn invocation và chính sách RNG/key.
- **“`AtomicLong` an toàn nên microservices tự dùng AtomicLong được.”** Sai: chỉ atomic giữa các thread chia sẻ cùng đối tượng trong một JVM.
- **“Mỗi container có PID khác, lấy PID làm prefix là đủ.”** Sai: PID/ordinal có thể tái sử dụng, bị trùng giữa host và không ràng buộc key epoch.
- **“Restart thì counter lại 0 nhưng dùng cùng key vẫn ổn.”** Sai: nguy cơ trùng cặp key/nonce đã dùng.
- **“Encrypt trước, lưu counter sau để tăng throughput.”** Sai: crash tạo cửa sổ reuse.
- **“Range đã reserve nhưng chưa dùng thì trả về pool.”** Sai: crash có thể khiến không biết đã dùng đến đâu; burn unused range.
- **“Có file lock thì dùng được trên mọi NFS.”** Sai: hành vi và độ bền phụ thuộc filesystem/OS; `FileLock` không phải distributed transaction.
- **“`force(true)` bảo đảm snapshot không thể rollback.”** Sai: flush không chống restore/replica lag/failover.
- **“GCM tag 128 bit nên nonce reuse không nghiêm trọng.”** Sai: reuse có thể làm suy yếu cả bí mật lẫn xác thực.
- **“Nonce là bí mật nên không nên lưu.”** Thường sai: nonce được lưu/truyền công khai với ciphertext để decrypt; điều cần bảo vệ là **uniqueness/key**.
- **“AAD khác nhau tạo nonce namespace khác.”** Sai: uniqueness vẫn đi theo key và IV.
- **“Đổi tên keyId là coi như có key mới.”** Sai: phải đổi **key material** thực sự.
- **“GCM và CBC dùng chung công thức IV tăng dần.”** Không đúng chung: CBC cần IV khó dự đoán theo đặc tính riêng.
- **“Nếu không biết counter có lùi hay không, cứ thử encrypt rồi đo.”** Không có phép test sau sự cố nào khôi phục tính an toàn của nonce đã tái sử dụng; khi nghi ngờ, **dừng mã hóa bằng key cũ**.

## 13. Câu hỏi tự kiểm tra

**1.** Hai thread dùng `long seq++` thông thường có thể cấp cùng nonce không?  
**Có.** Phép đọc-tăng-ghi không tự atomic; cần AtomicLong hoặc vùng khóa phù hợp.

**2.** Hai JVM trên cùng host dùng `AtomicLong` riêng có đủ an toàn nếu cùng key và fixed field không?  
**Không.** Mỗi JVM đều có thể cấp sequence 0,1,...; cần shared durable authority hoặc namespace thực sự không trùng.

**3.** Vì sao cần commit counter **trước** encrypt?  
Vì nếu crash sau encrypt nhưng trước persist, restart có thể cấp lại nonce đã dùng.

**4.** Một range [100,200) được commit cho process, crash khi mới dùng đến 120. Có được cấp lại [121,200) không?  
**Không.** Range đã reserve được coi là tiêu tốn, bỏ gap an toàn hơn reuse.

**5.** Có nên khởi tạo lại file counter từ 0 khi file cũ bị mất mà vẫn giữ AES key cũ?  
**Không.** Fail closed, đối chiếu durable authority; nếu không chứng minh được state chính xác thì rotate sang key mới.

**6.** Một nonce AES-GCM khác AAD nhưng giữ nguyên key/IV được dùng lại cho thông điệp khác có an toàn không?  
**Không.** AAD khác không cứu được lỗi trùng cặp key/IV.

**7.** Với deterministic nonce 32-bit fixed + 64-bit counter, điểm then chốt để tránh trùng trên nhiều process là gì?  
Duy trì **counter chung được cấp phát atomic và durable**, hoặc cố định field riêng không trùng theo writer/key và counter riêng bền vững trong mỗi namespace.

**8.** Dùng counter tăng cho IV CBC có tự bảo đảm an toàn không?  
**Không.** CBC còn yêu cầu IV khó dự đoán theo chính sách; quy tắc của GCM deterministic nonce không thể sao chép máy móc.

**9.** Chữ “96-bit random nonce” có nghĩa xác suất trùng bằng 0 không?  
**Không.** Xác suất nhỏ nhưng không bằng 0; NIST đặt giới hạn theo construction và mỗi key.

**10.** Việc rotate từ key-v1 sang key-v2 có cho phép xóa ngay key-v1 không?  
Tùy chính sách retention: các ciphertext cũ vẫn cần key-v1 để decrypt cho đến khi được reencrypt hoặc hết thời hạn. Tuy nhiên key-v1 nên chuyển sang **decrypt-only**, không mã hóa mới.

## Tóm tắt

Quy tắc cốt lõi đối với các mode yêu cầu nonce duy nhất:

```text
                    key material K
                          |
                 một namespace nonce
                          |
          +---------------+----------------+
          |                                |
   random IV construction           deterministic IV
   (collision probability)          fixed || counter
          |                                |
   theo dõi invocation/key          atomic allocation
   và giới hạn chuẩn                + durable commit
          |                                |
          +---------------+----------------+
                          |
                          v
              encrypt với nonce chưa dùng
                          |
                          v
           lưu [keyId,nonce,ciphertext,tag]
                          |
                          v
      restart / process / host / failover vẫn
      KHÔNG thể cấp lại nonce dưới cùng key
```

**Quản lý IV/nonce là một phần của vòng đời khóa, không phải chi tiết ngẫu nhiên bên trong một phương thức.** Cần đồng bộ trong JVM, đồng thuận/durability qua process, key-version và policy khôi phục qua restart. Nếu invariant không thể xác nhận, dừng encryption bằng key cũ và khôi phục theo hướng **key mới**.

## Nguồn tham khảo chính thức

- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): `8.1–8.3` về uniqueness IV/key, deterministic vs RBG construction và giới hạn invocation.
- [NIST SP 800-38A — Block Cipher Modes of Operation](https://csrc.nist.gov/pubs/sp/800/38/a/final): yêu cầu IV của CBC và uniqueness của counter blocks trong CTR (Appendix B).
- [Java 17 — Cipher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, việc thay đổi IV cho mỗi encryption.
- [Java 17 — GCMParameterSpec API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tLen của tag (bit) và IV bytes.
- [Java 17 — AtomicLong API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): cấp số nguyên tử trong một JVM.
- [Java 17 — FileLock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): file locks thuộc JVM, giới hạn giữa thread và filesystem/OS.
- [Java 17 — FileChannel API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `lock()`, ghi theo vị trí và `force(true)`.

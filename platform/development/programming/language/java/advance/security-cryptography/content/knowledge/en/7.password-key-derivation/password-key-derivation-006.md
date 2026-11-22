# 7.6. Hiệu chỉnh chi phí tính toán và nâng cấp tham số khi xác thực lại

## Mục tiêu và bối cảnh

Trong hệ thống xác thực mật khẩu, `password hashing` hoặc **password-based key derivation function (KDF)** được dùng để biến mật khẩu thành giá trị kiểm tra có salt và chi phí tính toán đáng kể. Kẻ tấn công có bản sao cơ sở dữ liệu có thể thử đoán mật khẩu **ngoại tuyến**; làm mỗi lần đoán tốn CPU, RAM và thời gian sẽ tăng chi phí tấn công. Ngược lại, phía máy chủ phải đủ nhanh để đăng nhập hợp lệ không bị nghẽn và không biến KDF thành điểm dễ bị tấn công từ chối dịch vụ.

Chi phí tính toán cần được **đo, hiệu chỉnh và tăng theo thời gian** cùng sự phát triển phần cứng và bối cảnh đe dọa. NIST SP 800-63B khuyến nghị chọn chi phí cao nhất có thể mà vẫn phù hợp hiệu năng verifier và tăng dần khi năng lực tính toán thay đổi. OWASP khuyến nghị các thuật toán chuyên dụng như Argon2id, scrypt hoặc PBKDF2 tùy điều kiện.

Sau bài này, bạn có thể:

1. Phân biệt tham số chi phí của **Argon2id**, **scrypt**, **bcrypt** và **PBKDF2**, cũng như ảnh hưởng lên CPU/RAM/latency.
2. Thiết kế bài **benchmark đo trên máy và tải thật**, dựa vào độ trễ p50/p95/p99, số xác thực đồng thời, bộ nhớ và giới hạn chống abuse.
3. Lưu **algorithm, version, parameters, salt và hash** kèm từng tài khoản để hỗ trợ kiểm chứng bản ghi cũ.
4. Thực hiện **verify bằng tham số cũ trước; rehash bằng tham số mới sau khi mật khẩu đúng**, với salt mới và cập nhật nguyên tử.
5. Xử lý tài khoản không đăng nhập lâu, thay đổi thuật toán, đồng thời với đổi mật khẩu và sự cố triển khai.

Phần code dùng **Java 17+** với `PBKDF2WithHmacSHA256` thuộc JCA vì chạy trực tiếp trên JDK. Đây là cách học toàn bộ luồng hiệu chỉnh và nâng cấp; nếu chọn Argon2id cho production, dùng thư viện được duy trì và kiểm chứng, không tự cài đặt thuật toán mật mã.

## 1. Vì sao không dùng một work factor cố định mãi mãi?

Mật khẩu do con người chọn thường có entropy thấp hơn khóa ngẫu nhiên. Salt riêng ngăn việc dùng lại bảng hash tính trước cho mọi tài khoản nhưng **không** ngăn thử đoán từng mật khẩu sau khi database bị rò rỉ. KDF tăng chi phí mỗi lần đoán, đặc biệt với thuật toán dùng nhiều bộ nhớ.

Giả sử hôm nay một cấu hình cho thời gian xác thực chấp nhận được. Khi phần cứng tấn công nhanh hơn, cấu hình cũ trở nên rẻ hơn đối với kẻ tấn công; trong khi đó máy chủ có thể đã có thêm năng lực xử lý để tăng chi phí. Vì vậy cần lưu **tham số riêng cho từng hash** và có kế hoạch **nâng cấp khi người dùng đăng nhập thành công**, thay vì giả sử mọi bản ghi luôn dùng chính sách hiện tại.

Ba khái niệm cần phân biệt:

- **Password verification:** từ mật khẩu người dùng nhập, tính KDF theo **tham số và salt của bản ghi đang lưu**, so sánh với hash đã lưu.
- **Cost calibration:** chạy thử các cấu hình trên môi trường mục tiêu để chọn tham số nằm trong ngân sách latency, CPU, memory và mức chống tấn công mong muốn.
- **Rehash-on-login (opportunistic upgrade):** sau một lần **xác thực thành công bằng cấu hình cũ**, dùng chính mật khẩu vừa nhập để tính hash mới với salt mới và chính sách mới; lưu lại nếu bản ghi vẫn là bản ghi cũ.

**Không thể** đổi trực tiếp một hash PBKDF2/Argon2id đã lưu sang tham số mạnh hơn chỉ bằng cách sửa số vòng hoặc “hash lại hash cũ” rồi coi kết quả là hash chuẩn của mật khẩu. Quá trình xác thực cần biết mật khẩu gốc (hoặc một giao thức chuyển đổi đặc biệt có thiết kế riêng); sau một lần login thành công bạn mới có mật khẩu vừa nhập để rehash. Không lưu mật khẩu plaintext chờ migration.

## 2. Hiểu đúng “chi phí” theo từng thuật toán

| Thuật toán | Tham số cốt lõi | Tài nguyên/đặc tính chính | Khi cân nhắc |
| --- | --- | --- | --- |
| **Argon2id** | `m`: bộ nhớ tính bằng KiB; `t`: số pass; `p`: số lane/song song | **Memory-hard**, làm đoán hàng loạt tốn RAM và băng thông bộ nhớ; cân đối thời gian/bộ nhớ | Ưu tiên cho hệ thống mới nếu có thư viện đáng tin và yêu cầu tuân thủ cho phép. |
| **scrypt** | `N`: CPU/memory cost; `r`: block size; `p`: parallelization | Dùng CPU và bộ nhớ; cần tính cả áp lực RAM khi nhiều request đồng thời | Phương án memory-hard khi không có Argon2id thích hợp. |
| **bcrypt** | `cost` (logarithmic work factor) | Chủ yếu chi phí CPU; tăng cost một đơn vị thường tăng khoảng gấp đôi công việc | Hệ thống hiện hữu; chú ý giới hạn input (phổ biến 72 byte), mã hóa và migration. |
| **PBKDF2-HMAC-SHA256** | `iterations`, số bit output, salt | Chủ yếu CPU, **không memory-hard** | Cần khả năng JCA sẵn có hoặc môi trường có yêu cầu FIPS phù hợp. |

**Không so sánh số work factor giữa các thuật toán như cùng một đơn vị.** Ví dụ `600000` vòng PBKDF2 không tương đương `t=600000` của Argon2id. Với Argon2id, `m` là **tổng bộ nhớ cho một phép băm**, không nhân trực tiếp với `p`; `p` là mức song song nội bộ và không được hiểu là “số vòng lặp”. Công thức tài nguyên thực tế phụ thuộc thư viện và máy chạy.

Các mức khởi điểm hiện được OWASP nêu trong *Password Storage Cheat Sheet* (cần kiểm tra lại tài liệu tại thời điểm triển khai):

- **Argon2id:** ví dụ `m=19456 KiB` (19 MiB), `t=2`, `p=1`; OWASP còn đưa các tổ hợp m/t khác có mức phòng thủ tương đương theo đánh giá của họ.
- **PBKDF2-HMAC-SHA256:** khuyến nghị tham chiếu **600.000 iterations**; phù hợp để xem xét khi cần đường triển khai PBKDF2/FIPS.
- **bcrypt:** tối thiểu cost 10 theo hướng dẫn hiện hành, nhưng cần xem đặc thù giới hạn mật khẩu và tình trạng ứng dụng.
- **scrypt:** tham khảo cặp `N=2^17, r=8, p=1` hoặc các lựa chọn tương đương trong hướng dẫn.

**Đây không phải “cấu hình bảo đảm an toàn” chỉ bằng việc copy số.** Hãy kiểm tra phiên bản nguồn khuyến nghị, sức chịu tải thực tế, khả năng nâng cấp, FIPS của *implementation cụ thể*, và dữ liệu rủi ro. Java 17 có `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`, nhưng **không có engine Argon2id tiêu chuẩn trong JCA core**; muốn dùng Argon2id cần thư viện/provider phù hợp.

## 3. Mô hình bản ghi tự mô tả, có version

Một password record cần đủ metadata để xác thực ngay cả khi chính sách mặc định đã thay đổi:

```text
algorithm | formatVersion | parameters | salt | derivedHash | optionalPepperKeyId
```

Ví dụ cấu trúc dạng chuỗi lưu trong database (chỉ là định dạng minh họa):

```text
pbkdf2-sha256$v1$600000$<salt_base64url>$<hash_base64url>
```

Trong code Java cuối bài, dấu `$` ngăn các trường và `v1` đánh dấu **phiên bản định dạng record**; nó không phải phiên bản thuật toán PBKDF2. Có thể dùng schema có cột riêng thay cho chuỗi; với Argon2id, ưu tiên định dạng chuẩn như **PHC string** nếu thư viện hỗ trợ. Không tự thay đổi thứ tự/ý nghĩa các trường ở bản ghi cũ.

Lưu:

- **Algorithm/version:** giúp chọn đúng verifier, duy trì tương thích và chặn định dạng không hỗ trợ.
- **Parameters per record:** đối với PBKDF2 là số `iterations` và độ dài kết quả; đối với Argon2id gồm `m,t,p`, phiên bản thuật toán và output length theo format.
- **Salt ngẫu nhiên riêng cho mỗi lần tạo hash:** ví dụ **16 byte (128 bit)** từ `SecureRandom`, không cần giữ bí mật. Nâng cấp thì tạo **salt mới**; không dùng salt cố định chung các tài khoản.
- **Derived hash:** lưu bytes dưới Base64/hex, **không** lưu mật khẩu, không log mật khẩu hoặc raw password-derived key.
- **Pepper (nếu có):** là secret chung hoặc quản lý tập trung, **không** đặt giá trị secret cạnh database hash; chỉ có thể lưu ID/version của khóa, quản lý thực tế tại KMS/HSM và thiết kế quy trình xoay pepper riêng.

Việc có salt ngẫu nhiên **không** cho phép bỏ rate limiting. Rate limiting bảo vệ xác thực trực tuyến; KDF làm chậm kiểm thử ngoại tuyến sau lộ dữ liệu. Cả hai giải quyết hai bề mặt tấn công khác nhau.

### Phải có giới hạn khi giải mã record

Các tham số trong database có thể bị hỏng hoặc không đáng tin (ví dụ account import lỗi hoặc database compromise). **Không bao giờ** đọc `iterations` hoặc `m` từ chuỗi rồi vô điều kiện cấp hàng GiB RAM/CPU hàng phút.

- Chỉ chấp nhận **danh sách algorithm và version** đã biết.
- Kiểm tra format, độ dài chuỗi, Base64, salt, hash output length và ranh giới giá trị iterations/m/t/p trước khi chạy KDF.
- Giới hạn input password hợp lý để giảm nguy cơ DoS, nhưng không cắt lặng lẽ mật khẩu; có chính sách nhập liệu và Unicode/encoding nhất quán.
- Trong quá trình tăng chính sách, mở rộng **giới hạn xác thực hash hợp lệ** có kế hoạch, tránh làm người dùng hiện hữu không thể đăng nhập.
- Record sai nên **fail closed**, ghi nhận lỗi theo cách không làm lộ thông tin nhạy cảm và đưa vào quy trình khắc phục/reset phù hợp.

## 4. Xây ngân sách hiệu năng trước khi tăng chi phí

Độ trễ một hash trên máy lập trình cá nhân không phản ánh trực tiếp hàng nghìn login đồng thời trên production. Quy trình hiệu chỉnh nên có các bước sau:

1. **Xác định ngân sách của endpoint đăng nhập:** ví dụ mục tiêu p95 tổng latency, tỷ lệ request thành công, SLO riêng cho CPU/RAM và khả năng bảo vệ khi nhận lưu lượng bất thường. Đây là mục tiêu sản phẩm, **không phải** một con số cố định do Java áp đặt.
2. **Đo baseline hiện tại**: tỷ lệ người dùng đang ở thuật toán/parameter version nào; p50/p95/p99 verify; CPU, RSS/memory, GC, queue time, throughput, số lần authentication đồng thời trên từng instance; phân biệt thời gian KDF thuần và toàn request.
3. **Chọn tập ứng viên** dựa trên khuyến nghị bảo mật và giới hạn hạ tầng. Với Argon2id, phải xem **m × số phép KDF đồng thời** cộng overhead memory; với PBKDF2 tập trung CPU time và số worker/luồng.
4. **Warm up trước khi lấy số**: chạy trên JDK/provider/library, container CPU quota, RAM limit, kiến trúc máy và cấu hình GC tương tự production. Đo nhiều lần, bỏ thời gian khởi động/JIT khỏi phép đo steady-state.
5. **Test tải đồng thời** với tỉ lệ login đúng/sai, tenant đông, các đợt đột biến, signup/đổi mật khẩu và những tài khoản đang cần rehash. Kiểm tra khi resource bị giới hạn: có queue/backpressure và rate limit phù hợp, không làm nghẽn hệ thống.
6. **Chọn cấu hình đủ mạnh nhưng còn dư tải** cho thời điểm cao điểm; đo thêm vòng cấp phát memory và chi phí khi thất bại. Đưa tham số/phiên bản chính sách vào config có version, thử nghiệm canary và quan sát trước rollout.
7. **Định kỳ rà soát** khi thay hardware/JDK/provider, xuất hiện yêu cầu tuân thủ mới, throughput tăng hoặc có hướng dẫn bảo mật mới.

Một phép tính kiểm tra áp lực bộ nhớ (minh họa): nếu một lần Argon2id cần khoảng **19 MiB**, hàng chục phép tính đồng thời có thể dùng hàng trăm MiB chỉ riêng vùng làm việc KDF, chưa gồm heap, native overhead và tác vụ khác. Việc tăng `p` không bảo đảm p95 sẽ tốt lên: nó có thể làm nhiều core cạnh tranh tài nguyên hơn. Phải đo trong cùng mô hình concurrency thực tế.

**Không lấy p95 của 11 lần hash một luồng làm p95 của dịch vụ dưới tải.** Microbenchmark là bộ lọc ứng viên; load test mới cho thấy queue, scheduling, contention, memory pressure và tác dụng của rate limiting.

### Bảng ghi nhận kết quả calibration

| Cấu hình ứng viên | p50 KDF | p95 KDF | p95 login end-to-end | CPU/RAM cao điểm | Throughput/queue | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| Policy đang chạy | Đo | Đo | Đo | Đo | Đo | Baseline |
| Cấu hình đề xuất A | Đo | Đo | Đo | Đo | Đo | Chọn/từ chối có lý do |
| Cấu hình đề xuất B | Đo | Đo | Đo | Đo | Đo | Chọn/từ chối có lý do |

Bảng chỉ là mẫu ghi kết quả **phải tự đo**, không phải số liệu thực nghiệm giả định.

## 5. Java 17: microbenchmark một ứng viên PBKDF2

Lưu file **`Pbkdf2CostBench.java`**:

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Pbkdf2CostBench {
    private Pbkdf2CostBench() {}

    private static byte[] run(SecretKeyFactory factory, char[] password,
            byte[] salt, int iterations) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, 256);
        try {
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java Pbkdf2CostBench <iterations>");
            return;
        }
        int iterations = Integer.parseInt(args[0]);
        if (iterations < 1_000 || iterations > 2_000_000) {
            throw new IllegalArgumentException("Iterations outside benchmark guardrails");
        }

        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        char[] password = "benchmark-only-password".toCharArray();
        SecretKeyFactory factory =
                SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
        try {
            for (int i = 0; i < 3; i++) {
                byte[] hash = run(factory, password, salt, iterations);
                Arrays.fill(hash, (byte) 0);
            }
            long[] elapsed = new long[11];
            for (int i = 0; i < elapsed.length; i++) {
                long begin = System.nanoTime();
                byte[] hash = run(factory, password, salt, iterations);
                elapsed[i] = System.nanoTime() - begin;
                Arrays.fill(hash, (byte) 0);
            }
            Arrays.sort(elapsed);
            System.out.printf(
                    "iterations=%d samples=%d p50Ms=%.2f p95Ms=%.2f%n",
                    iterations, elapsed.length,
                    elapsed[elapsed.length / 2] / 1_000_000.0,
                    elapsed[(int) Math.ceil(0.95 * elapsed.length) - 1]
                            / 1_000_000.0);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Pbkdf2CostBench.java
java Pbkdf2CostBench 10000
java Pbkdf2CostBench 600000
```

Định dạng output:

```text
iterations=<so_vong> samples=11 p50Ms=<ms_do_duoc> p95Ms=<ms_do_duoc>
```

Dòng trên là **mẫu định dạng**, không phải stdout số học cố định: thời gian phụ thuộc CPU, JDK, provider, JIT, tải, nhiệt độ và giới hạn container. `samples=11`, `p50Ms` và `p95Ms` lấy từ 11 mẫu đã sort (p95 theo nearest-rank). Chương trình có 3 lượt warmup và 11 phép đo đơn luồng; dùng để kiểm tra nhanh, **chưa đủ** để quyết định chính sách production.

**Giải thích code:** `SecretKeyFactory` cung cấp PBKDF2-HMAC-SHA256. `PBEKeySpec` chứa password, salt, iteration count và độ dài output **256 bit**; `clearPassword()` cố gắng xóa bản sao nội bộ sau khi dùng. Kết quả được xóa khỏi mảng tạm ngay sau phép đo để hạn chế dữ liệu nhạy cảm tồn tại trong heap. Mật khẩu demo là hằng số để tái lập phép thử; không dùng mật khẩu thật khi benchmark. Mức 10.000 vòng chỉ để chạy thử nhanh, **không phải policy lưu mật khẩu mới**.

Khi đánh giá Argon2id/scrypt thực tế, giữ cùng phương pháp warmup và đo nhiều mẫu, nhưng benchmark luôn bằng **thư viện thuật toán được chọn thực sự**, với `m,t,p` và giới hạn native memory trên server. Đừng suy luận thời gian Argon2id từ thời gian PBKDF2.

## 6. Khi nào phải nâng cấp một hash?

Tách chính sách **tạo hash mới** và **xác thực hash cũ**:

- **Policy hiện tại** nêu thuật toán, version, cost tối thiểu, salt length, output length và các ràng buộc của *credential mới*.
- **Verifier cũ** vẫn hiểu các format/thuật toán legacy còn được cho phép, dựa vào metadata **của bản ghi**, không tự ý dùng cost mới để verify hash cũ.
- **needsRehash(record, policy)** trả true khi algorithm/version đã cũ hoặc tham số thấp hơn policy hiện tại theo đánh giá *cụ thể từng thuật toán*. Không chỉ so sánh một số cost tổng quát giữa bcrypt/PBKDF2/Argon2id.
- Không tự động “hạ cấp” record có tham số mạnh hơn hiện tại; cần một chính sách migration cụ thể nếu thay thuật toán.

Ví dụ trạng thái:

| Bản ghi đang lưu | Password được nhập | Kết quả verify | Hành động |
| --- | --- | --- | --- |
| PBKDF2 12.000 vòng | Đúng | PASS bằng 12.000 vòng | Tạo salt mới, hash lại theo policy mới, cập nhật có kiểm soát. |
| PBKDF2 12.000 vòng | Sai | FAIL | Từ chối, **không rehash** hoặc đổi tham số. |
| PBKDF2 600.000 vòng | Đúng | PASS | Đăng nhập; không rehash nếu đạt policy và algorithm không đổi. |
| Record version không hỗ trợ | Bất kỳ | Không có verifier hợp lệ | Fail closed và xử lý khôi phục có xác thực; không đoán tham số. |
| Hai phiên đăng nhập đồng thời | Đều đúng với snapshot ban đầu | PASS bước verify | Chỉ một cập nhật compare-and-set thắng; bên còn lại cần xác minh trạng thái mới. |
| Password reset thắng trước cập nhật | Password cũ đã verify trên snapshot cũ | Có race | CAS thất bại; kiểm tra credential mới, không đè lại password reset. |

Việc **nâng cấp sau khi xác thực lại** thường có thể làm minh bạch với người dùng: mật khẩu vẫn như cũ, salt/hash/cost thay đổi. Tuy nhiên, tính chi phí của **verify cũ + rehash mới** trong lần đăng nhập đó, vì có hai phép KDF. Nếu hệ thống có nhiều hash legacy, cần chuẩn bị tải và có giới hạn concurrency riêng.

### Flow xác thực và nâng cấp

```text
Nhận password qua kênh bảo vệ
          |
          v
Tải credential record + version
          |
          v
Kiểm tra format/algorithm/cost trong ranh giới cho phép
          |
          v
KDF(password, salt cũ, params cũ)
          |
          v
So sánh kết quả không làm rò rỉ timing theo byte
          |
        Có khớp?
       /        \
     Không       Có
      |           |
 Từ chối       needsRehash?
                  /      \
                Không     Có
                 |         |
               Login    Salt mới + KDF policy mới
                           |
                     Atomic CAS/UPDATE
                           |
               Nếu conflict: đọc lại record
               và kiểm tra mật khẩu hiện hành
```

Một lỗi thiết kế thường gặp là **hash mới bằng cách đổi cost mà giữ derived hash cũ**, hoặc **rehash mọi lần login, kể cả đã đạt policy**, gây tốn tài nguyên không cần thiết. Một lỗi khác là **rehash ngay trước khi verify**, đồng nghĩa tự ghi đè credential khi người dùng nhập sai.

## 7. Java 17: ví dụ đầy đủ verify rồi nâng cấp nguyên tử

`PasswordUpgradeDemo` lưu một chuỗi dạng `pbkdf2-sha256$v1$iterations$salt$hash` trong `AtomicReference` để mô phỏng **một hàng database**. Ví dụ có hai policy:

- `OLD_WORK = 12000`: mô phỏng **record legacy yếu**, cố ý chỉ dùng cho bài học, không phải khuyến nghị production.
- `CURRENT_WORK = 600000`: policy mới minh họa theo mức PBKDF2-HMAC-SHA256 đang được OWASP tham khảo. Trong hệ thống thật, cần **benchmark và cấu hình hóa**, không hard-code vô thời hạn.

Lưu file **`PasswordUpgradeDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordUpgradeDemo {
    private static final String ID = "pbkdf2-sha256";
    private static final String VERSION = "v1";
    private static final int OLD_WORK = 12_000;
    private static final int CURRENT_WORK = 600_000;
    private static final int MAX_ACCEPTED_WORK = 2_000_000;
    private static final int SALT_SIZE = 16;
    private static final int HASH_SIZE = 32;
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private record Stored(int work, byte[] salt, byte[] hash) {}
    private record LoginResult(boolean authenticated, boolean upgraded) {}

    private static byte[] pbkdf2(char[] password, byte[] salt, int work)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, work, HASH_SIZE * 8);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static String encode(char[] password, int work)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_SIZE];
        RNG.nextBytes(salt);
        byte[] hash = pbkdf2(password, salt, work);
        try {
            return String.join("$", ID, VERSION, Integer.toString(work),
                    ENCODER.encodeToString(salt),
                    ENCODER.encodeToString(hash));
        } finally {
            Arrays.fill(hash, (byte) 0);
        }
    }

    private static Stored parse(String encoded) {
        if (encoded == null || encoded.length() > 256) {
            throw new IllegalArgumentException("Invalid credential record");
        }
        String[] f = encoded.split("\\$", -1);
        if (f.length != 5 || !ID.equals(f[0]) || !VERSION.equals(f[1])
                || !f[2].matches("[1-9][0-9]{0,6}")) {
            throw new IllegalArgumentException("Unsupported credential format");
        }
        int work = Integer.parseInt(f[2]);
        if (work > MAX_ACCEPTED_WORK) {
            throw new IllegalArgumentException("Unsupported work factor");
        }
        byte[] salt = DECODER.decode(f[3]);
        byte[] hash = DECODER.decode(f[4]);
        if (salt.length != SALT_SIZE || hash.length != HASH_SIZE) {
            throw new IllegalArgumentException("Invalid salt or hash size");
        }
        return new Stored(work, salt, hash);
    }

    private static boolean matches(char[] password, Stored stored)
            throws GeneralSecurityException {
        byte[] candidate = pbkdf2(password, stored.salt(), stored.work());
        try {
            return MessageDigest.isEqual(stored.hash(), candidate);
        } finally {
            Arrays.fill(candidate, (byte) 0);
        }
    }

    private static LoginResult signIn(AtomicReference<String> account,
            char[] password) throws GeneralSecurityException {
        String observed = account.get();
        Stored stored = parse(observed);
        if (!matches(password, stored)) {
            return new LoginResult(false, false);
        }
        if (stored.work() >= CURRENT_WORK) {
            return new LoginResult(true, false);
        }

        String replacement = encode(password, CURRENT_WORK);
        if (account.compareAndSet(observed, replacement)) {
            return new LoginResult(true, true);
        }

        // A concurrent change (including password reset) may have won.
        // Re-verify current state instead of trusting a stale password.
        return new LoginResult(matches(password, parse(account.get())), false);
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example-only-password".toCharArray();
        char[] wrong = "incorrect".toCharArray();
        try {
            AtomicReference<String> row =
                    new AtomicReference<>(encode(password, OLD_WORK));
            Stored before = parse(row.get());
            System.out.println("oldWork=" + before.work());

            LoginResult first = signIn(row, password);
            Stored after = parse(row.get());
            System.out.println("authenticated=" + first.authenticated());
            System.out.println("upgraded=" + first.upgraded());
            System.out.println("newWork=" + after.work());
            System.out.println("freshSalt=" +
                    !Arrays.equals(before.salt(), after.salt()));
            System.out.println("upgradeAgain=" + signIn(row, password).upgraded());
            System.out.println("wrongPasswordAccepted=" +
                    signIn(row, wrong).authenticated());
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PasswordUpgradeDemo.java
java PasswordUpgradeDemo
```

**Stdout chính xác trong trường hợp chạy thông thường:**

```text
oldWork=12000
authenticated=true
upgraded=true
newWork=600000
freshSalt=true
upgradeAgain=false
wrongPasswordAccepted=false
```

Mặc dù `SecureRandom` tạo salt khác mỗi lần, chương trình chỉ in **kết quả logic** nên stdout không phụ thuộc vào giá trị salt. Xác suất trùng salt ngẫu nhiên 16 byte cực kỳ nhỏ; demo dùng phép so sánh để cho thấy đã tạo salt mới, không coi đây là chứng minh toán học tuyệt đối của tính không trùng.

### Điểm cần đọc kỹ trong code

1. **Tạo hash:** `encode` tạo **salt ngẫu nhiên 16 byte**, dẫn xuất output 256 bit bằng PBKDF2-HMAC-SHA256, rồi lưu algorithm/version/work/salt/hash theo thứ tự đã quy ước. Salt và hash được mã hóa Base64URL. `String.join` chỉ nối trường metadata, không chứa password.
2. **Parse có kiểm tra:** `parse` chỉ nhận format/algorithm/version cho phép, giới hạn iterations, salt 16 byte và hash 32 byte. Giới hạn `MAX_ACCEPTED_WORK` nhằm chặn bản ghi bất thường làm cạn CPU; mọi lần thay policy thật phải cập nhật guardrail có kiểm soát. Trong hệ thống lớn có nhiều algorithm, dùng dispatch rõ ràng theo allowlist và verifier tương ứng.
3. **Verify đúng tham số cũ:** `matches` gọi PBKDF2 bằng `stored.work()` và `stored.salt()`, tức **tham số của record đã lưu**, không dùng `CURRENT_WORK` để xác thực hash cũ. `MessageDigest.isEqual` so sánh byte array; không dùng `==` cho mảng.
4. **Không nâng cấp khi sai:** `signIn` trả `authenticated=false, upgraded=false` ngay khi hash không khớp; không tạo salt/hash mới.
5. **Nâng cấp đúng thời điểm:** chỉ nếu mật khẩu đúng và `work < CURRENT_WORK` thì `encode(password,CURRENT_WORK)` tạo **hash mới + salt mới**. Nếu work đã đạt/nhỉnh hơn policy, tránh hash lại lặp đi lặp lại.
6. **Đảm bảo cập nhật không ghi đè tùy tiện:** `compareAndSet(observed,replacement)` chỉ thành công nếu record vẫn là snapshot vừa xác thực. Nếu có thay đổi đồng thời (gồm password reset), demo **đọc lại và verify mật khẩu hiện hành** trước khi cho phép đăng nhập. Đây là mô phỏng logic CAS, không phải một cơ chế transaction cho database.
7. **Giảm thời gian giữ mật khẩu:** `PBEKeySpec.clearPassword()` xóa bản sao nội bộ; `Arrays.fill(password,'\0')` xóa mảng đầu vào demo sau cùng. Khi ứng dụng nhận password qua String/HTTP body, không thể đảm bảo mọi bản sao immutable bị xóa; hãy giảm log, sao chép và thời gian sống của secret.

**Về benchmark:** demo dùng 600.000 vòng có thể mất thời gian khác nhau trên từng máy. Dùng nó để hiểu luồng migration và kiểm tra API; đo tải thật bằng phương pháp mục 4–5 trước khi đưa production.

## 8. Đưa compare-and-set vào cơ sở dữ liệu và tránh race

`AtomicReference` chỉ mô phỏng dữ liệu một tài khoản trong một tiến trình. Hệ thống thực cần **cập nhật có điều kiện** ở database. Một mẫu SQL minh họa:

```sql
UPDATE accounts
SET password_record = :new_record,
    credential_version = credential_version + 1
WHERE id = :account_id
  AND credential_version = :version_read
  AND password_record = :old_record;
```

Chỉ khi **affected rows = 1** mới đánh dấu nâng cấp thành công. Nếu affected rows = 0, bản ghi đã bị đổi (do rehash từ login khác, đổi mật khẩu hoặc reset) hoặc đã bị xóa. **Không** chạy UPDATE vô điều kiện với password cũ; phải đọc lại và xử lý phù hợp. Một password reset thành công không được bị ghi đè bởi một luồng rehash đã bắt đầu trước đó.

Lưu ý: chỉ so khớp string `password_record` có thể khó tối ưu hoặc không phù hợp một số schema; dùng **credential_version** và optimistic locking, transaction isolation được thiết kế cho hệ thống thật. Nếu một luồng vẫn cấp session dựa trên snapshot cũ đúng lúc password reset, chính sách **session revocation** và điều phối auth/credential write cần được định nghĩa riêng, ngoài ví dụ tối giản này.

Có hai chiến lược thời điểm nâng cấp:

- **Đồng bộ ngay trên login:** dễ hiểu, có kết quả migration chắc chắn trước khi response, nhưng lần login legacy có chi phí **verify cũ + hash mới**. Đặt budget/timeout thích hợp.
- **Chuyển sang job nội bộ sau verify:** chỉ khi password vẫn sẵn trong phạm vi kiểm soát an toàn của operation; tránh lưu mật khẩu plaintext vào queue, log, event hoặc database. Trong nhiều hệ thống, không đưa password sang background queue là lựa chọn đơn giản và an toàn hơn.

Không bao giờ coi một bản ghi legacy là đã nâng cấp chỉ vì xác thực được. Cần **xác nhận UPDATE thành công**, đồng thời tiếp tục hỗ trợ verifier cũ cho bản ghi còn lại trong giai đoạn migration.

## 9. Triển khai nâng cấp toàn hệ thống

### Chính sách theo version và rollout

1. Tạo **bản ghi mới theo policy hiện tại** cho đăng ký và đổi mật khẩu kể từ thời điểm rollout.
2. Tiếp tục **verify hash cũ theo đúng params cũ** cho tài khoản còn được phép đăng nhập.
3. Sau lần verify thành công, nếu policy cho biết cần migration, **rehash với salt mới** và commit CAS.
4. Theo dõi tỷ lệ hash thuộc từng algorithm/params/version và số lần nâng cấp thành công/thất bại **không log password/hash/salt**. Ghi thông số tổng hợp, latency, overload và lỗi parse định dạng.
5. Nếu gặp CPU/memory pressure, giảm lưu lượng KDF bằng rate limit, admission control, queue có giới hạn, autoscaling có kiểm chứng; cân nhắc rollout từng phần hoặc hoãn migration không khẩn cấp theo policy. **Không** âm thầm giảm cost của credential mới để che lỗi tài nguyên.
6. Khi tỷ lệ legacy đã thấp, quyết định mốc ngừng hỗ trợ theo rủi ro và quyền lợi người dùng; tài khoản chưa đăng nhập lâu cần **quy trình reset mật khẩu có xác thực**, không thể tự “tăng iterations” cho hash cũ khi không có plaintext.
7. Đảm bảo rollback phiên bản ứng dụng vẫn **đọc được bản ghi mới**, nếu rollback là khả năng cần có; deploy verifier hỗ trợ version mới **trước** khi bắt đầu ghi hash mới.

### Chuyển thuật toán, không chỉ tăng iterations

Chuyển từ PBKDF2 sang Argon2id là **algorithm migration**: verifier nhận diện record PBKDF2 và xác thực; khi thành công, library Argon2id tạo một record **PHC** mới với m/t/p và salt mới. Không so `iterations` của PBKDF2 với `t` của Argon2id như cùng thước đo. Một hệ thống có thể giữ nhiều verifier cho giai đoạn chuyển đổi, nhưng **chỉ một policy tạo hash mới**.

Với hệ thống bcrypt legacy, chú ý **giới hạn 72 byte** và cách hệ thống cũ xử lý mật khẩu Unicode hoặc dữ liệu dài; thay encoding một cách tùy tiện có thể khiến mật khẩu hợp lệ trước đó bị từ chối. Khi migration thuật toán, phải kiểm thử case non-ASCII và mật khẩu dài theo verifier lịch sử.

### Khi có pepper

Pepper giúp thêm một lớp bảo vệ khi database hash bị lộ nhưng secret bên ngoài vẫn an toàn; thay đổi pepper có thể đòi hỏi **verify bằng pepper key ID cũ rồi tạo record mới dùng pepper mới** hoặc quy trình reset. Đừng lưu plaintext pepper cạnh DB và đừng nghĩ thêm pepper là thay thế cho salt/work factor. Cần thiết kế các failure mode khi HSM/KMS không sẵn sàng, audit truy cập, rotation, key identifier và xử lý tài khoản chưa đăng nhập.

## 10. Rủi ro từ abuse và dữ liệu không đáng tin

Càng tăng cost, một request đăng nhập hợp lệ càng tốn tài nguyên; kẻ tấn công có thể tận dụng endpoint này để gây **CPU/RAM exhaustion**. Cân nhắc các lớp bảo vệ:

- **Rate limit theo account và nguồn**, phát hiện credential stuffing, throttling phù hợp và bảo vệ endpoint khôi phục. Không tạo kênh thông báo cho phép liệt kê user bằng lỗi hoặc thời gian rõ rệt.
- **Bounded concurrency**: chỉ cho số phép KDF đồng thời phù hợp RAM/CPU; hàng chờ phải có giới hạn và timeout. Với Argon2id, đo native memory cùng heap/container memory.
- **Thông số từ record phải qua validate**: không cho account tự yêu cầu iterations cực lớn hoặc m=GiB, không cho attacker đặt algorithm tùy ý trong hệ thống nhận dữ liệu ngoài.
- **Độ dài mật khẩu đầu vào**: cho phép passphrase dài theo chính sách, nhưng đặt trần hợp lý và kiểm thử các thực thi PBKDF2/long password để tránh trường hợp xử lý đầu vào gây chi phí bất thường. Không cắt mật khẩu không thông báo.
- **Khi user không tồn tại**, tránh làm rò rỉ qua response và timing. Một phương án là verifier thực hiện dummy KDF với policy thích hợp trong luồng lỗi; phải tính chi phí vào năng lực chịu tải và kết hợp rate limit. Mục tiêu là hành vi quan sát được nhất quán, không hứa thời gian luôn đồng đều tuyệt đối.
- **Đừng tối ưu bằng fast hash** như SHA-256/MD5 cho password storage. Hash nhanh có ích ở bài toán khác nhưng khiến thử đoán ngoại tuyến quá rẻ.
- **Đầu vào sai, phiên bản không hỗ trợ, hỏng record** phải fail closed và có quy trình hỗ trợ người dùng, không fallback âm thầm sang thuật toán yếu.

Lưu ý về chi phí **người dùng thất bại liên tiếp**: luôn phải kiểm chứng password bằng KDF đối với account có tồn tại và record hợp lệ, nhưng kết hợp rate limit/lockout được thiết kế tránh lợi dụng account DoS; không cho phép bypass KDF qua một đường xác thực “nhanh” riêng.

## 11. Những lỗi hay gặp và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Tăng iterations trong config rồi dùng số mới để verify tất cả hash cũ | Hash lưu được tính với iterations cũ; xác thực đúng sẽ thất bại | Verify theo metadata của **từng record**. |
| Rehash hash cũ thay vì password | Kết quả không tương đương KDF(password, salt mới, params mới) | Chỉ rehash sau khi password đúng và vẫn sẵn trong request. |
| Rehash trước kiểm tra mật khẩu | Ghi đè credential cho request sai | Verify thành công trước, rồi mới tạo record mới. |
| Giữ salt cũ hoặc dùng salt chung | Làm suy yếu tính độc lập giữa bản ghi/lần hash | Salt ngẫu nhiên mới cho mỗi lần hash mới/upgrade. |
| Không lưu algorithm/version/params | Không thể đọc hash cũ khi policy đổi | Định dạng tự mô tả, có migration path. |
| Cho phép cost từ DB không giới hạn | CPU/RAM DoS khi record hỏng hoặc bị sửa | Guardrails và allowlist thuật toán, version. |
| Dùng `Arrays.equals` cho hash và nghĩ nó là constant-time | Không có bảo đảm timing phù hợp | Dùng primitive verify của thư viện hoặc `MessageDigest.isEqual` khi chuẩn hóa độ dài. |
| Cấp ủy quyền dựa trên snapshot cũ sau password reset cạnh tranh | Có thể cho người dùng dùng credential đã thay | CAS, re-check khi conflict, định nghĩa session revocation. |
| UPDATE vô điều kiện sau login | Ghi đè password reset/concurrent migration | Optimistic lock theo credential version/record. |
| Rehash mọi login | Gây CPU/RAM không cần thiết | Chỉ khi `needsRehash` thật, tránh downgrade. |
| Thêm Argon2id mới mà tắt ngay verifier PBKDF2 | Tài khoản legacy không thể login | Deploy verifier đọc cả cũ và mới trước write. |
| “Đo” bằng một request local | Bỏ qua p95/p99, queue, CPU quota, native memory | Warmup + nhiều mẫu + test tải production-like. |
| Nâng cost quá cao mà không có rate limiting | Kẻ tấn công tạo hàng đợi KDF quá tải | Giới hạn concurrency, rate limit và capacity plan. |
| Nghĩ PBKDF2 600k đủ vĩnh viễn | Hardware/khuyến nghị thay đổi | Định kỳ benchmark và xem lại tài liệu chuẩn. |
| Hard-code một giá trị cho mọi thuật toán | Các cost parameter khác ngữ nghĩa | Policy phân loại theo algorithm. |
| Log password hoặc hash để debug | Tăng nguy cơ lộ thông tin xác thực | Ghi log dạng metadata tổng hợp, không ghi secret. |

## 12. Bài tập tình huống

1. **Chọn policy:** bạn có hai server class với giới hạn CPU/RAM khác nhau. Lập bảng ứng viên Argon2id m/t/p hoặc PBKDF2 iterations và thiết kế thử nghiệm với tải 1, 10, 50 phép KDF đồng thời. Nêu rõ vì sao p95 đo đơn luồng không đủ.
2. **Bắt buộc kiểm chứng đúng cost:** tạo PBKDF2 record với 12.000 vòng, thử xác thực bằng 600.000 vòng trên cùng salt/hash. Giải thích vì sao không khớp và cách verify đúng trước khi upgrade.
3. **Thực hành Java:** chạy `PasswordUpgradeDemo`, giải thích lần đầu `upgraded=true`, lần sau `upgradeAgain=false` và vì sao salt thay đổi dù password giữ nguyên.
4. **Đọc lỗi:** thay field iterations của record thành `999999999` hoặc format `v9`; vì sao parser phải từ chối **trước khi gọi KDF**?
5. **Race condition:** hai login hợp lệ đọc cùng record legacy; một phiên cập nhật thành công. Phiên còn lại nên làm gì khi compare-and-set thất bại? Nếu đồng thời có password reset, điều gì thay đổi?
6. **Tài khoản ngủ đông:** 5% người dùng không đăng nhập 2 năm. Không có password plaintext, vì sao không thể rehash trực tiếp? Hãy đề xuất reset hoặc chính sách sunset verifier cũ có kiểm soát.
7. **Chi phí kép:** mỗi lần login legacy phải verify 1 lần với cost cũ và tạo hash 1 lần với cost mới. Dự đoán peak CPU/RAM trong giai đoạn rollout, đề xuất metric và rate-limit/bounded-concurrency phù hợp.
8. **Algorithm migration:** thiết kế pseudo-code verify cả PBKDF2 và Argon2id nhưng **chỉ hash mới bằng Argon2id**. Không đồng nhất số iterations của PBKDF2 với `t` của Argon2id.
9. **Bảo mật thực tế:** giải thích tác dụng riêng của salt, work factor, pepper, rate limit và TLS. Tại sao không thành phần nào thay thế hoàn toàn các thành phần còn lại?

**Tiêu chí nắm vững:** Bạn phân biệt được cost của từng KDF; đo trên hệ thống đại diện; lưu record có version/params/salt; xác thực bằng cost **đã lưu** trước khi upgrade; tạo hash mới bằng **password + salt mới + policy mới**, cập nhật nguyên tử và xử lý race; không gây downgrade hoặc làm cạn tài nguyên khi nhận dữ liệu record bất thường.

## Tài liệu tham khảo

- [OWASP Password Storage Cheat Sheet — Work Factors, Argon2id, PBKDF2 và Upgrading the Work Factor](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [NIST SP 800-63B (Revision 4) — Password Verifiers, salted hashes và cost factor](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java SE 17: `PBEKeySpec` và `clearPassword`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Java SE 17: `SecretKeyFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [Java SE 17: `MessageDigest.isEqual`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [RFC 9106 — Argon2 Memory-Hard Function for Password Hashing](https://www.rfc-editor.org/rfc/rfc9106)

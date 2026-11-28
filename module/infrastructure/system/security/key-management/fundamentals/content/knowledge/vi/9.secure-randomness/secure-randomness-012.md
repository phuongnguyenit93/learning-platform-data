# Kiểm thử randomness đúng cách: Đánh giá nguồn ngẫu nhiên cho hệ thống mật mã

Giả sử một dịch vụ Java dùng **SecureRandom** để tạo khóa AES-256, nonce AES-GCM, khóa HMAC và token khôi phục tài khoản. Nhóm phát triển sinh một triệu byte, quan sát tỷ lệ bit 0/1 gần bằng nhau rồi tuyên bố bộ sinh **an toàn về mật mã**. Kết luận đó **không có cơ sở**: một chuỗi hoàn toàn dự đoán được vẫn có thể vượt qua nhiều phép kiểm tra thống kê. Ngược lại, một nguồn ngẫu nhiên an toàn vẫn đôi lúc tạo ra mẫu bị một phép kiểm định thống kê đánh dấu bất thường do dao động tự nhiên.

**Kiểm thử randomness đúng cách** không phải tìm một phép thử trả kết quả PASS rồi chứng nhận an toàn. Cần kết hợp **đánh giá nguồn entropy**, **thiết kế và trạng thái CSPRNG/DRBG**, **kiểm thử thống kê có diễn giải đúng**, **kiểm thử tích hợp API**, **quản lý nonce/seed**, và **giám sát vận hành**. Mỗi lớp trả lời một câu hỏi riêng.

Trong chương **Secure randomness** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chất lượng nguồn ngẫu nhiên tác động trực tiếp tới vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**. Dù khóa được bảo vệ trong KMS/HSM, mã hóa bằng AES-GCM hay ký bằng ECDSA, key material hoặc tham số mật mã sinh từ nguồn dễ đoán vẫn có thể làm toàn bộ hệ thống mất an toàn. Bài học cũng kết nối KDF, mật mã đối xứng/bất đối xứng, chữ ký số, envelope encryption, IAM và audit.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **randomness thống kê**, **entropy**, **unpredictability** và **cryptographic security**.
2. Giải thích vai trò của **entropy source**, **seed**, **reseed**, **DRBG/CSPRNG** và **health tests**.
3. Hiểu được giới hạn của frequency test, chi-square, kiểm tra va chạm và bộ kiểm thử như **NIST SP 800-22**.
4. Viết *smoke test* Java 17 cho **SecureRandom** mà không nhầm nó với chứng nhận an toàn mật mã.
5. Viết **unit test deterministic** qua dependency injection, bảo đảm bản production vẫn dùng CSPRNG phù hợp.
6. Kiểm thử riêng **nonce duy nhất theo khóa**, token, key generation và các tình huống multi-instance, fork, snapshot/restore.
7. Xây dựng checklist đánh giá provider, KMS/HSM, giám sát và ứng phó sự cố RNG.

## 2. “Ngẫu nhiên” không chỉ có một nghĩa

### 2.1. Trông ngẫu nhiên không có nghĩa khó dự đoán

Xét một chương trình tạo chuỗi giả ngẫu nhiên từ **seed cố định được công khai**:

~~~text
seed = 123456789
generator = deterministicNonCryptoPRNG(seed)
sample = generator.nextBytes(1_000_000)

Tần suất bit 0/1 có thể gần 50/50.
Nhưng ai biết thuật toán và seed cũng tái tạo được toàn bộ sample.
=> Không được dùng để sinh secret key.
~~~

Trong trường hợp ngược lại, việc đồng xu công bằng ra mặt ngửa 16 lần liên tiếp vẫn có xác suất khác 0. Một phép kiểm định báo lỗi trên mẫu ngắn **không chứng minh ngay** bộ sinh bị lỗi.

### 2.2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi muốn trả lời | Giới hạn |
|---|---|---|
| **Statistical uniformity** | Các giá trị có phân bố gần phân bố kỳ vọng không? | Không chứng minh bit tiếp theo khó dự đoán |
| **Independence** | Có dấu hiệu phụ thuộc giữa các mẫu theo mô hình kiểm định không? | Không loại trừ mọi cấu trúc ẩn |
| **Shannon entropy** | Mức bất định trung bình của một phân phối là bao nhiêu? | Không trực tiếp chứng minh an toàn khi đoán secret |
| **Min-entropy** | Giá trị dễ đoán nhất có xác suất lớn tới đâu? | Không thể đo chắc chắn chỉ bằng một histogram ngắn |
| **CSPRNG/DRBG** | Bộ sinh được thiết kế để đầu ra khó dự đoán với giả định seed/state đúng? | Không an toàn nếu seed/state lộ hoặc bị clone |
| **Entropy source** | Nguồn vật lý/môi trường cung cấp vật liệu seed có chất lượng gì? | Không mặc nhiên mạnh vì được quảng bá là hardware RNG |
| **Health test** | Có phát hiện được một số dạng suy giảm/hỏng nguồn? | Không chứng minh mọi tính chất an ninh |

Với biến ngẫu nhiên rời rạc \(X\), **min-entropy** là:

\[
H_{\infty}(X)=-\log_2\left(\max_x\Pr[X=x]\right).
\]

Một bit công bằng có min-entropy **1 bit**. Nếu bit đó bằng 0 với xác suất 0,99, min-entropy thấp hơn rất nhiều. Trong thực tế, đánh giá nguồn entropy phải dựa trên **mô hình nguồn, dữ liệu quan sát được và phương pháp ước lượng phù hợp**, không phải lấy số bit của đầu ra rồi gọi là “số bit entropy”.

**Khóa AES-256 dài 256 bit không mặc nhiên có 256 bit entropy.** Nếu nó được tạo hoàn toàn từ seed chỉ có 20 bit khó đoán, đối thủ có thể vét cạn không gian seed nhỏ thay vì không gian \(2^{256}\) khóa.

## 3. Kiến trúc nguồn randomness dùng trong mật mã

Ứng dụng thường không lấy bit thô từ cảm biến rồi dùng ngay làm khóa. Hệ thống có thể có nhiều lớp:

~~~mermaid
flowchart TD
    E["Entropy source: OS, phần cứng hoặc nguồn nhiễu"] --> H["Conditioning và health monitoring theo thiết kế"]
    H --> S["Seed / entropy input"]
    S --> D["CSPRNG / DRBG có state bí mật"]
    D --> O["Random bytes được trả qua API"]
    O --> K["AES/HMAC key và bearer token"]
    O --> N["Nonce, salt khi chính sách yêu cầu"]
    O --> P["RSA/EC key generation"]
    D --> R["Reseed theo quy tắc provider"]
    H -.-> A["Entropy validation và health tests"]
    D -.-> B["Conformance/self-tests nếu yêu cầu"]
    O -.-> C["Statistical smoke checks, không chứng nhận an ninh"]
~~~

Đây là sơ đồ khái quát. Hệ điều hành, JVM, cloud KMS và HSM có những kiến trúc khác nhau. Trong Java, **SecureRandom là API**, không phải một thuật toán duy nhất. An toàn phụ thuộc vào **algorithm, provider, seed, cấu hình, phiên bản và môi trường vận hành**.

### 3.1. Seed và reseed

- **Seed** là vật liệu dùng khởi tạo hoặc bổ sung trạng thái CSPRNG/DRBG, phải đáp ứng yêu cầu entropy của cơ chế và mức an ninh mong muốn.
- **Reseed** đưa entropy mới vào state theo thiết kế. Khả năng phục hồi sau khi state lộ phụ thuộc DRBG, thời điểm reseed và threat model.
- **Timestamp, PID, username, counter hoặc địa chỉ bộ nhớ** không phải nguồn entropy đủ mạnh để tự sinh khóa mật mã.
- Việc tự truyền **seed có thể dự đoán** vào API không phải cách “tăng bảo mật”; không thay thế đường khởi tạo/reseed an toàn do provider quản lý.

Với Java, hành vi constructor và **SecureRandom.setSeed** phụ thuộc contract/provider; không nên giả định nó thiết lập một seed bí mật mới đủ mạnh chỉ vì đã gọi phương thức. Trong triển khai có yêu cầu cao, kiểm tra chính xác provider và nguồn seed theo chính sách.

### 3.2. Những họ tiêu chuẩn liên quan

| Tiêu chuẩn | Vai trò | Không nên dùng để suy ra |
|---|---|---|
| **NIST SP 800-90A** | Các cơ chế **deterministic random bit generator (DRBG)** được chuẩn hóa | Chọn tên DRBG đúng là đủ bảo đảm nguồn entropy thực |
| **NIST SP 800-90B** | Đánh giá **entropy source**, ước lượng entropy và health tests | Một phép kiểm tra bit của đầu ra SecureRandom chính là đánh giá nguồn |
| **NIST SP 800-90C** | Cấu trúc kết hợp nguồn entropy và DRBG trong các thiết kế chuẩn hóa | Mọi ứng dụng dùng cùng tên API đều có cùng assurance |
| **NIST SP 800-22** | Tập **kiểm định thống kê** cho chuỗi bit | Vượt mọi phép thống kê nghĩa là có cryptographic unpredictability |
| **FIPS 140-3** | Xác nhận mô-đun mật mã theo phạm vi/cấu hình cụ thể | Bất kỳ JVM nào gọi SecureRandom cũng đã FIPS validated |

Không dùng kết quả của **SP 800-22** thay cho đánh giá nguồn entropy theo **SP 800-90B**, kiểm tra cấu trúc DRBG theo **SP 800-90A**, hoặc đánh giá module/cấu hình theo quy trình FIPS áp dụng.

## 4. Phân tầng kiểm thử đúng đối tượng

| Lớp | Câu hỏi | Hoạt động phù hợp | Giới hạn |
|---|---|---|---|
| **Nguồn entropy** | Noise source có entropy và health phù hợp không? | Characterization, min-entropy estimate, startup/online health tests | Đòi hỏi mô hình và dữ liệu nguồn thật |
| **DRBG/provider** | Algorithm/state/reseed và implementation có đúng không? | Review provider, cấu hình, known-answer tests, conformance | Không chứng minh state runtime không bị đánh cắp |
| **Statistical output** | Mẫu đầu ra có sai lệch rõ theo giả thuyết không? | Monobit, byte histogram, chi-square, runs/serial tests | Có false positive/negative, không chứng minh khó dự đoán |
| **Unit/integration** | Ứng dụng dùng đúng API và contract không? | Token length, encoding, key size, dependency injection, error handling | Không chứng minh chất lượng entropy của provider |
| **Nonce uniqueness** | Có lặp nonce với **cùng key** trong concurrency/restart không? | Test counter allocation, failover, rollback, invocation limits | Nonce duy nhất không có nghĩa key material mạnh |
| **Vận hành** | Nguồn/provider có đổi hoặc báo lỗi ngoài dự kiến không? | Inventory, health alerts, audit, change management | Không dùng log raw secret để chứng minh RNG tốt |

**Nhiều phép kiểm tra đạt** giúp củng cố độ tin cậy trong từng phạm vi, nhưng không thể cộng chúng lại thành một chứng nhận an ninh nếu threat model và các giả định nền tảng chưa được kiểm tra.

## 5. Kiểm thử thống kê: Diễn giải bằng mô hình xác suất

### 5.1. Monobit frequency test

Với \(n\) bit độc lập phân bố đều, số bit 1 có kỳ vọng \(n/2\) và độ lệch chuẩn:

\[
\sigma=\sqrt{n\cdot0.5\cdot(1-0.5)}=\sqrt{n/4}.
\]

Với **1 MiB = 1.048.576 byte = 8.388.608 bit**, kỳ vọng có **4.194.304 bit 1** và độ lệch chuẩn xấp xỉ **1.448 bit** trong mô hình tham khảo. Kết quả thực tế hiếm khi chính xác 50%: dao động quanh 50% là điều bình thường.

Không đặt luật “phải có đúng nửa số bit là 1”. Một quy tắc kiểm tra hợp lý cần có **mô hình giả thuyết**, **sample size**, **độ lệch cho phép** và **mức ý nghĩa** được quyết định trước.

### 5.2. Byte histogram và chi-square

Với \(N\) byte độc lập, đều trên 256 giá trị, tần suất kỳ vọng mỗi giá trị là \(E=N/256\). Một thống kê là:

\[
\chi^2=\sum_{i=0}^{255}\frac{(O_i-E)^2}{E},
\]

với \(O_i\) là số lần xuất hiện của giá trị byte \(i\). Khi các điều kiện xấp xỉ phù hợp, có thể tham chiếu phân bố chi-square với **255 bậc tự do**. Tuy nhiên giá trị chi-square trông hợp lý **không chứng minh dãy không bị dự đoán** hoặc có state an toàn.

### 5.3. Runs, serial correlation và nhiều phép kiểm định

Các phép kiểm tra khác xét chiều dài chuỗi bit liên tiếp, tương quan giữa vị trí, phân bố các mẫu con hoặc cấu trúc dài hơn. **NIST SP 800-22**, **TestU01** và **PractRand** có thể cung cấp tín hiệu về sai lệch thống kê trong những điều kiện sử dụng phù hợp. Chúng không thay được phân tích mật mã.

Cần nhớ:

1. **P-value không phải xác suất generator an toàn**; nó được tính dưới giả thuyết và mô hình kiểm định.
2. Một generator tốt vẫn có thể có **false positive** theo ngưỡng đã chọn.
3. Vượt kiểm định không chứng minh không có seed yếu, backdoor, dự đoán state hay side channel.
4. Chạy hàng trăm kiểm định làm tăng khả năng gặp ít nhất một false positive; cần diễn giải **multiple testing** đúng.
5. Không lặp việc sinh mẫu tới khi “PASS”, vì chọn lọc kết quả làm mất ý nghĩa của kiểm định.
6. Cỡ mẫu, cách lấy mẫu, số phép thử và tiêu chí chấp nhận nên được xác định **trước khi** nhìn vào output.

### 5.4. Không thấy collision không phải bằng chứng uniqueness

Với các giá trị độc lập, đều trên không gian \(2^b\), xác suất có ít nhất một cặp trùng sau \(q\) lần sinh **xấp xỉ**, khi xác suất nhỏ:

\[
\Pr[\text{collision}]\approx\frac{q(q-1)}{2^{b+1}}.
\]

Ví dụ nonce ngẫu nhiên **96 bit** của AES-GCM có xác suất collision tăng theo bình phương tổng số lần mã hóa bằng **cùng khóa**. Không thấy trùng trong 1.000 mẫu là điều có thể dự đoán được; nó không chứng minh thiết kế an toàn ở quy mô nhiều tỷ invocation.

Một bộ đếm được cấp phát bền vững, không trùng theo key có thể cho **lập luận cấu trúc về uniqueness**. Đó là vấn đề khác với kiểm tra thống kê của nguồn sinh random.

## 6. Ví dụ Java 17: Statistical smoke test cho SecureRandom

Ví dụ dưới đây chỉ giúp phát hiện **một số lỗi phân bố cực kỳ rõ**, hoàn toàn **không phải chứng nhận entropy hoặc CSPRNG security**. Nó lấy mẫu **1 MiB**, đếm bit 1, tính chi-square trên 256 byte và in tên algorithm/provider để hỗ trợ review cấu hình.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

public final class SecureRandomSmokeTest {
    private static final int SAMPLE_BYTES = 1 << 20; // 1 MiB

    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();
        byte[] sample = new byte[SAMPLE_BYTES];
        random.nextBytes(sample);

        long oneBits = 0;
        int[] counts = new int[256];
        for (byte value : sample) {
            int unsigned = value & 0xFF;
            counts[unsigned]++;
            oneBits += Integer.bitCount(unsigned);
        }

        double bitCount = sample.length * 8.0;
        double expected = bitCount / 2.0;
        double stdDev = Math.sqrt(bitCount / 4.0);
        double z = (oneBits - expected) / stdDev;

        double expectedByteCount = sample.length / 256.0;
        double chiSquare = 0.0;
        for (int observed : counts) {
            double diff = observed - expectedByteCount;
            chiSquare += diff * diff / expectedByteCount;
        }

        System.out.println("Algorithm: " + random.getAlgorithm());
        System.out.println("Provider : " + random.getProvider().getName());
        System.out.println("Samples  : " + sample.length + " bytes");
        System.out.printf("Fraction of 1 bits: %.6f%n", oneBits / bitCount);
        System.out.printf("Monobit z-score   : %.3f%n", z);
        System.out.printf("Byte chi-square   : %.3f%n", chiSquare);

        // Ngưỡng rất rộng chỉ để phát hiện bất thường nghiêm trọng.
        // KHÔNG có nghĩa PASS là an toàn hay được chứng nhận.
        try {
            if (Math.abs(z) > 8.0) {
                throw new AssertionError("Severe frequency anomaly");
            }
        } finally {
            Arrays.fill(sample, (byte) 0);
        }
    }
}
~~~

Lưu thành **SecureRandomSmokeTest.java**, chạy trên JDK 17+:

~~~bash
javac SecureRandomSmokeTest.java
java SecureRandomSmokeTest
~~~

Một kết quả **chỉ mang tính minh họa**:

~~~text
Algorithm: DRBG
Provider : SUN
Samples  : 1048576 bytes
Fraction of 1 bits: 0.500131
Monobit z-score   : 0.758
Byte chi-square   : 247.510
~~~

Tên algorithm/provider và các con số thực tế có thể khác theo hệ điều hành/JDK/provider. Kết quả này **chỉ cho thấy mẫu chưa bộc lộ sai lệch tần suất nghiêm trọng theo phép đo hiện tại**. Không dùng chúng để tuyên bố **min-entropy = 256 bit**, tính chống dự đoán hoặc tuân thủ FIPS.

### 6.1. Nếu cần kiểm định chuyên sâu

- Định nghĩa giả thuyết, kích thước mẫu, mức ý nghĩa và số phép kiểm định trước khi thu thập dữ liệu.
- Kiểm tra điều kiện áp dụng, cách phân nhóm dữ liệu và giới hạn lý thuyết của từng phép kiểm định.
- Phân biệt **mẫu output được tạo để test** với dữ liệu key/token production; không log secret thật để thuận tiện phân tích.
- Xem xét nhiều trạng thái: startup, chạy lâu, tải cao, reseed, restart, failover, snapshot/restore.
- Kiểm tra hiệu ứng **multiple testing**; không chọn lọc kết quả dễ nhìn rồi bỏ kết quả xấu.
- Review **conformance, provider và entropy source**, vì thống kê output chỉ là dữ liệu bổ trợ.

## 7. Kiểm thử entropy source và health tests

**Entropy-source validation** khác với việc đếm bit 1 trên đầu ra SecureRandom. Một nguồn entropy bị suy giảm có thể vẫn cung cấp các seed khiến DRBG tiếp tục phát output trông đều trong một thời gian. Cần đánh giá **nguồn nhiễu**, quá trình conditioning, ước lượng entropy và lỗi phần cứng/phần mềm ở đúng tầng.

### 7.1. Hai health test phổ biến trong NIST SP 800-90B

| Health test | Nguyên lý | Ví dụ lỗi phát hiện | Giới hạn |
|---|---|---|---|
| **Repetition Count Test (RCT)** | Phát hiện một giá trị đầu ra nguồn bị lặp liên tục quá lâu | Noise source kẹt ở một trạng thái | Không bắt được mọi mẫu có thể dự đoán |
| **Adaptive Proportion Test (APT)** | Theo dõi số lần xuất hiện một giá trị trong một cửa sổ mẫu | Một giá trị chiếm tỷ lệ quá cao | Không thay thế phân tích entropy đầy đủ |

Ngưỡng của các test phải dựa vào **mô hình nguồn, entropy estimate và tiêu chí của chuẩn**, không thể tự lấy một con số từ output SecureRandom rồi gọi đó là “đã triển khai RCT/APT theo SP 800-90B”. Nguồn chuyên dụng có thể cần **startup, continuous và on-demand tests** theo thiết kế áp dụng.

Nếu đang dùng HSM hoặc KMS, ứng dụng thường không trực tiếp có quyền truy cập raw noise source. Thay vào đó phải kiểm tra **tài liệu đánh giá, trạng thái health, cấu hình, các giới hạn và cơ chế lỗi của provider**, vẫn giữ trách nhiệm kiểm thử việc ứng dụng sử dụng nonce/key đúng cách.

### 7.2. Khi có cảnh báo health

Quy trình cần làm rõ: thành phần nào lỗi, mức độ tin cậy của cảnh báo, có phải dừng cấp secret mới không, có nguồn dự phòng độc lập đã được phê duyệt không, khoảng thời gian/key nào có thể chịu ảnh hưởng, ai quyết định khôi phục hoạt động và bằng chứng audit nào cần lưu. **Không âm thầm fallback sang java.util.Random hoặc seed dự đoán được** để “giữ hệ thống chạy”.

## 8. Unit test đúng cách: Randomness thật không cần trả kết quả cố định

Một unit test dễ viết nhưng sai mục tiêu:

~~~java
SecureRandom rng = new SecureRandom();
byte[] tokenBytes = new byte[32];
rng.nextBytes(tokenBytes);
// SAI: assertArrayEquals(expectedFixedBytes, tokenBytes);
~~~

Đầu ra của một CSPRNG ở production được thiết kế để **khó dự đoán**. Không thể xây test tin cậy bằng cách yêu cầu nó trả một chuỗi byte cố định. Thứ cần test là **contract của code tiêu thụ random bytes**: chiều dài, encoding, kiểm tra tham số, định dạng, quyền, xử lý lỗi và việc không đưa secret vào log.

Nếu muốn test logic xác định, hãy dùng **dependency injection** cho một nguồn random giả. Nguồn giả chỉ tồn tại trong **test source set**, không được cấu hình làm fallback của production.

### 8.1. Java 17: Token generator với nguồn production và nguồn giả

Code sau minh họa token gồm **32 byte**, mã hóa thành **Base64URL không padding**. **SecureRandomSource** dùng trong production; **FixedSequenceSource** cố ý dự đoán được để kiểm tra logic.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public final class TokenGeneratorDesign {
    @FunctionalInterface
    interface RandomBytes {
        void fill(byte[] destination);
    }

    static final class SecureRandomSource implements RandomBytes {
        private final SecureRandom rng = new SecureRandom();

        @Override
        public void fill(byte[] destination) {
            rng.nextBytes(destination);
        }
    }

    // Fake dành riêng cho unit test, tuyệt đối không dùng production.
    static final class FixedSequenceSource implements RandomBytes {
        private int next = 0;

        @Override
        public void fill(byte[] destination) {
            for (int i = 0; i < destination.length; i++) {
                destination[i] = (byte) (next++);
            }
        }
    }

    static final class TokenGenerator {
        private final RandomBytes random;

        TokenGenerator(RandomBytes random) {
            this.random = java.util.Objects.requireNonNull(random);
        }

        String newToken() {
            byte[] bytes = new byte[32];
            try {
                random.fill(bytes);
                return Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes);
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }
    }

    public static void main(String[] args) {
        TokenGenerator forTest =
                new TokenGenerator(new FixedSequenceSource());

        String first = forTest.newToken();
        String second = forTest.newToken();
        if (first.length() != 43 || second.length() != 43) {
            throw new AssertionError("Wrong Base64URL length");
        }
        if (first.equals(second)) {
            throw new AssertionError("Fake source did not advance");
        }
        if (Base64.getUrlDecoder().decode(first).length != 32) {
            throw new AssertionError("Token does not encode 32 bytes");
        }
        System.out.println("Token contract tests passed");

        // Production wiring PHẢI dùng SecureRandomSource.
        TokenGenerator forProduction =
                new TokenGenerator(new SecureRandomSource());
        String token = forProduction.newToken();
        System.out.println("Production token length: " + token.length());
        // Không log chính token production: nó là bearer credential.
    }
}
~~~

Lưu thành **TokenGeneratorDesign.java**:

~~~bash
javac TokenGeneratorDesign.java
java TokenGeneratorDesign
~~~

Kết quả kỳ vọng:

~~~text
Token contract tests passed
Production token length: 43
~~~

**Fake ở đây không có entropy bảo mật.** Nếu tổ chức muốn đảm bảo không bao giờ đưa fake vào production, hãy đặt nó trong mã test, không đóng gói vào artifact triển khai, và xác minh dependency wiring qua integration/configuration tests. Ví dụ ghép hai nguồn trong một chương trình **chỉ nhằm trình bày sự khác biệt**; triển khai thật cần tách chúng.

### 8.2. Bảng test nên có cho token

| Loại test | Phù hợp trong CI? | Lý do |
|---|---|---|
| Độ dài byte và Base64URL format | **Có** | Kiểm tra hoàn toàn xác định |
| Decode token ra đúng số byte | **Có** | Kiểm tra serialization |
| Lỗi từ random source được xử lý rõ | **Có** | Không fallback sang giá trị yếu, rỗng hoặc cố định |
| Quy tắc expiry, scope và revoke | **Có** | Kiểm tra an ninh nghiệp vụ |
| Hai token nhỏ mẫu không trùng | **Có thể**, chỉ như smoke test | Không chứng minh unpredictability, tránh khẳng định quá mức |
| Token thật bằng đúng một chuỗi cố định | **Không** | Trái mục tiêu CSPRNG |
| Algorithm/provider nằm trong allowlist | **Có**, với integration test | Gắn đúng cấu hình runtime đang chạy |
| Chạy SP 800-22 trên mọi request cấp token | **Không** | Chi phí và kết luận không phù hợp |

**Lưu ý:** Mảng byte chứa token sau khi chuyển thành String đã được xóa best effort, nhưng **String token trả về vẫn nằm trong heap cho đến khi không còn tham chiếu/GC**. Nếu token là credential, cần quản lý lifetime, logging và nơi lưu trữ token riêng; việc xóa mảng gốc không xóa được String.

## 9. Chọn và kiểm tra SecureRandom trong Java

### 9.1. Không dùng PRNG phi mật mã cho secret

| API | Thiết kế cho | Khóa/token/secret? |
|---|---|---|
| **java.util.Random** | PRNG đa dụng, mô phỏng và code có seed tái lập | **Không** |
| **ThreadLocalRandom** | PRNG hiệu năng trong xử lý đồng thời | **Không** |
| **SplittableRandom** | Tách chuỗi giả ngẫu nhiên cho tính toán song song | **Không** |
| **SecureRandom** | API nguồn random dùng trong mật mã theo provider | **Có**, khi provider/cấu hình phù hợp chính sách |

Để sinh key material, nên dùng **KeyGenerator**, **KeyPairGenerator** hoặc API **GenerateDataKey** theo thư viện/provider và chính sách phù hợp, thay vì tự lắp các bit khóa không đúng contract thuật toán.

Ví dụ sử dụng CSPRNG để tạo buffer bí mật tạm thời trong Java 17:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

public final class GenerateSecretBytes {
    public static void main(String[] args) {
        SecureRandom rng = new SecureRandom();
        byte[] secret = new byte[32];
        try {
            rng.nextBytes(secret);
            System.out.println("Generated length: " + secret.length);
            // Chuyển secret cho thành phần được phép; không in raw bytes.
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }
}
~~~

Đây là ví dụ API, không phải quy trình sản xuất/luân chuyển khóa hoàn chỉnh. **Arrays.fill** chỉ xóa chính mảng đang giữ, không bảo đảm mọi bản sao trong provider/JVM đã được hủy.

### 9.2. Kiểm tra provider đúng môi trường

Một quy trình triển khai nên:

1. **Inventory** thuật toán và provider được chọn, phiên bản JDK/OS và cấu hình bảo mật.
2. **Xác minh yêu cầu assurance** của provider theo threat model, quy định và chính sách tổ chức.
3. **Kiểm tra production runtime**, không chỉ máy lập trình viên: security properties và native provider có thể khác.
4. **Đánh giá khả năng block khi thiếu entropy**, thời gian khởi tạo và hiệu năng dưới tải.
5. **Fail closed theo policy** nếu không có provider được chấp thuận; tuyệt đối không fallback sang **Random**.
6. **Ghi nhận và kiểm soát nâng cấp** JDK, provider, HSM firmware và OS vì chúng có thể thay đổi đường entropy/reseed.

**SecureRandom.getInstanceStrong()** chọn thuật toán dựa trên cấu hình **securerandom.strongAlgorithms** và có thể có hành vi blocking/hiệu năng khác tùy nền tảng. Nó **không phải lựa chọn tự động tốt nhất trong mọi request**. Đừng đưa lời gọi vào đường xử lý latency-sensitive mà không kiểm tra trên hệ thống thực.

**SecureRandom.setSeed** cũng không phải cách thay thế seed hệ thống bằng timestamp/PID rồi kỳ vọng có bảo mật. Với cấu hình DRBG cụ thể, chỉ dùng các tham số/cơ chế reseed theo contract của provider.

### 9.3. FIPS và HSM

Nếu dự án yêu cầu **FIPS 140-3**, phải xem đúng **mô-đun, phiên bản, cấu hình và operational environment** nằm trong phạm vi xác nhận. Việc sử dụng một API tên SecureRandom hoặc phần cứng được quảng bá là secure **không tự chứng minh ứng dụng đã FIPS validated**.

HSM có thể tích hợp nguồn entropy và DRBG, cùng self-tests và health monitoring. Ứng dụng cần xác minh **chứng cứ của module/provider và cách sử dụng đúng hợp đồng**, đồng thời vẫn kiểm thử cách cấp nonce, chọn key version và kiểm soát IAM tại tầng ứng dụng.

## 10. Kiểm thử theo mục đích dùng random

### 10.1. Sinh khóa AES, HMAC, RSA và EC

Khóa bí mật cần **khó dự đoán**, không chỉ “trông đều”. Histogram 32 byte khóa không thể chứng minh 256 bit entropy. Sử dụng CSPRNG và API key generation được kiểm chứng, bảo vệ seed/state, key material, quyền truy cập và các thao tác trên khóa.

Với **ECDSA**, nonce ký bí mật (*k*) cần được sinh/thiết lập đúng sơ đồ. Nếu **k lặp hoặc dễ dự đoán**, private signing key có thể bị suy ra. Một số sơ đồ ECDSA dùng nonce xác định theo chuẩn để tránh phụ thuộc random mới cho mỗi chữ ký, nhưng **private key ban đầu vẫn phải được sinh an toàn**. **Ed25519** cũng có quy trình ký theo chuẩn mang tính xác định; điều đó không cho phép sinh private key từ seed yếu.

Với **RSA**, dùng KeyPairGenerator/provider tin cậy theo tham số chính sách, không tự sinh các số nguyên tố từ seed chứa timestamp hoặc bộ đếm.

### 10.2. AES-GCM nonce: Ưu tiên đảm bảo uniqueness

AES-GCM thường dùng nonce 96 bit. Điều kiện thiết yếu là **không tái sử dụng cùng nonce với cùng khóa AES**. Nguồn random mạnh chỉ làm giảm xác suất trùng nếu dùng nonce ngẫu nhiên, **không biến xác suất thành 0**.

~~~mermaid
flowchart TD
    K["Một DEK AES-GCM"] --> Q{"Cấp nonce bằng cách nào?"}
    Q --> R["Random 96 bit từ CSPRNG"]
    Q --> C["Prefix duy nhất + counter bền vững"]
    R --> L["Giới hạn invocation trên tổng toàn hệ thống / DEK"]
    C --> S["Phân phối prefix, state, failover và rollover"]
    L --> E["Encrypt với nonce mới, AAD và tag đúng"]
    S --> E
~~~

Test quan trọng:

- **Multi-instance:** các instance có đang dùng chung DEK và sinh trùng prefix/counter?
- **Restart/snapshot:** counter hoặc DRBG state có quay lùi thành vùng đã dùng?
- **Retry:** mã hóa **lại** với cùng DEK phải dùng nonce mới; trả lại **chính ciphertext đã lưu** cho một thao tác idempotent là vấn đề khác.
- **Counter overflow:** có chặn tràn hoặc phạm vi dùng vượt thiết kế?
- **Usage limits:** tổng số lần mã hóa trên **mỗi DEK** có được theo dõi và rotation đúng hạn?
- **Metadata:** có lưu nonce, tag, key ID/version và thông tin giải mã đúng bản ghi?

Không dùng việc thử 1.000 nonce không thấy trùng để thay lập luận uniqueness theo cấu trúc hoặc xác suất ở quy mô production. Đặc biệt, **AES-256 không cứu được nonce reuse**.

### 10.3. Salt, KDF và password hashing

- **Password salt** thường là giá trị ngẫu nhiên, riêng cho mỗi password verifier. Salt **không phải secret**, nhưng cần được lưu chính xác cùng verifier và tham số **Argon2id/scrypt/PBKDF2** theo policy.
- **HKDF salt** phục vụ Extract; việc dùng salt ngẫu nhiên hoặc có cấu trúc do giao thức quy định. Muốn dẫn xuất lại cùng khóa phải giữ đúng **IKM, salt, info, KDF/version**.
- **HKDF không tăng entropy của password yếu**. Dẫn xuất 32 byte từ một seed có thể đoán vẫn không đem lại bảo mật tương đương 256 bit.
- **Salt** và **nonce/IV** có điều kiện an ninh khác nhau. Không thay thế quy tắc nonce GCM bằng lời khuyên “cứ sinh 12 byte random là đủ mãi mãi”.

### 10.4. Token, OTP và số trong khoảng

Bearer token cần **khó đoán** và có **scope, expiry, revoke, rate limit, lưu trữ và truyền tải an toàn**. Ngay cả token ngẫu nhiên mạnh cũng có thể bị lộ qua log, URL, Referer hoặc quyền đọc database.

**OTP 6 chữ số** chỉ có tối đa khoảng **một triệu khả năng**; dùng CSPRNG không biến nó thành một secret 256-bit. Cần giới hạn số lần thử, thời hạn và ràng buộc phiên/người dùng.

Khi lấy một số trong phạm vi không phải lũy thừa của hai, phép **randomByte % bound** có thể gây **modulo bias**. Dùng API sinh số trong khoảng thích hợp như **SecureRandom.nextInt(bound)** để tránh sai lệch do phép chia lấy dư tự phát.

Với **UUID v4**, có khoảng **122 bit ngẫu nhiên** nếu được tạo bằng nguồn phù hợp (một số bit dành cho version/variant). UUID hỗ trợ nhiều bài toán định danh nhưng không phải mọi loại UUID đều là random token; khi dùng như credential vẫn phải xét threat model, TTL và quyền truy cập.

## 11. Fork, VM snapshot và nhiều instance: Lỗi histogram không thấy

Giả sử hai VM được clone tại thời điểm CSPRNG có cùng state rồi tiếp tục sinh giá trị mà không được reseed/xử lý snapshot đúng. Mỗi chuỗi riêng lẻ **có thể có phân bố rất đẹp**, nhưng hai VM lại phát cùng chuỗi key/token/nonce. Đây là ví dụ tại sao kiểm định output đơn lẻ không đủ.

Không phải mọi OS/JVM/provider đều mắc lỗi clone state: nhiều implementation có cơ chế xử lý fork, VM generation hoặc reseeding. Điều cần làm là **kiểm tra đảm bảo và hành vi thực tế của môi trường**, không mặc định nó đúng hay sai.

Các kịch bản nên có:

1. **Cold boot:** nguồn entropy có sẵn trước khi phát khóa đầu tiên?
2. **Start đồng thời:** container image có vô tình nhúng seed/state cố định?
3. **VM snapshot/restore:** generator/nonce counter có trở lại trạng thái đã dùng?
4. **Fork/process clone:** provider có chính sách tái khởi tạo state như thế nào?
5. **Failover và network partition:** hai node dùng chung DEK có cấp nonce giao nhau?
6. **Upgrade:** thay OS/JDK/provider có ảnh hưởng seed/DRBG hoặc API policy?
7. **Health failure:** thao tác cấp key mới có được dừng và có audit rõ ràng?

**Không log raw RNG stream/key production để so sánh giữa instance.** Nếu cần kiểm tra song song, hãy thu thập dữ liệu test chuyên dụng được quản trị rõ ràng và dùng log metadata thay vì secret.

## 12. KMS/HSM, vòng đời khóa và audit randomness

Một DEK được tạo ngẫu nhiên tốt có thể bị lộ bởi log hoặc tiếp tục bị dùng sau khi nonce space trở nên rủi ro. Một private key sinh đúng có thể bị lạm dụng bởi tài khoản có quyền Sign. Vì vậy random quality là một phần của **key management**, không thay thế các lớp kiểm soát khác.

~~~mermaid
flowchart TD
    E["Entropy source / RNG được chấp thuận"] --> G["KeyGen, GenerateDataKey hoặc nonce allocation"]
    G --> I["Đăng ký keyId, version, owner, purpose"]
    I --> U["Sử dụng theo IAM, thuật toán và limits"]
    U --> A["Audit và theo dõi provider, health, key usage"]
    A --> Q{"Có sự cố hoặc đến hạn rotation?"}
    Q -->|"Chưa"| U
    Q -->|"Có"| D["Điều tra và ngừng cấp mới nếu rủi ro nghiêm trọng"]
    D --> R["Khắc phục nguồn/provider, thay thế khóa"]
    R --> M["Re-encrypt / revoke / key migration nếu cần"]
    M --> X["Xác minh recovery rồi hủy theo policy"]
~~~

| Giai đoạn | Rủi ro | Kiểm soát |
|---|---|---|
| **Generation** | Seed/entropy thấp, DRBG sai cấu hình | Provider assurance, health tests, review nguồn |
| **Provisioning** | Seed/khóa bị clone giữa môi trường | Key ID/version, tách môi trường, không hardcode secret |
| **Storage** | Key/seed bị log, backup hoặc dump | KMS/HSM, wrapping, access policy, redaction |
| **Use** | Nonce GCM trùng, ECDSA k sai, token yếu | Thuật toán đúng, nonce strategy, key usage limits |
| **Audit** | Không biết provider hoặc key nào bị ảnh hưởng | Log metadata, trạng thái, actor, operation, outcome |
| **Rotation** | Tiếp tục encrypt bằng khóa nghi bị yếu | Chuyển key version, giới hạn use, migration |
| **Revocation** | Vẫn có quyền Decrypt/Sign hoặc token đã phát | IAM, disable, token revoke, cache invalidation |
| **Destruction** | Hủy key trong khi backup/bản mã cũ còn cần | Restore tests, kiểm tra phụ thuộc và quy trình phê duyệt |

### 12.1. Khi nghi RNG lỗi có phải mọi khóa đều không an toàn?

**Không thể kết luận khi chưa khoanh vùng**. Phải phân biệt:

- **Một phép kiểm định thống kê báo lỗi:** có thể là false positive, lỗi chọn mẫu hoặc dấu hiệu bất thường; cần điều tra.
- **Health test nguồn entropy báo hỏng nghiêm trọng:** có thể cần dừng sinh secret mới, xử lý theo quy trình thiết bị/provider.
- **Có bằng chứng seed/state dự đoán được hoặc bị clone:** khóa/token/nonce được cấp trong khoảng ảnh hưởng có thể cần thu hồi và thay thế.
- **Khóa tạo từ nguồn độc lập trước khoảng lỗi:** có thể không bị ảnh hưởng về entropy, nhưng vẫn cần xét quyền và lịch sử sử dụng.

Nếu **AES-GCM nonce reuse đã xảy ra**, **rewrap DEK bằng KEK mới không sửa hậu quả**; có thể cần thay DEK và mã hóa lại dữ liệu bị ảnh hưởng. Nếu **private signing key yếu** thì cần rotate/revoke, đánh giá chữ ký có thể bị giả. Nếu **token có thể đoán**, cần thu hồi token, kiểm tra nhật ký truy cập và phản ứng sự cố.

### 12.2. Ghi log thế nào cho đúng?

Ghi **provider/algorithm, JDK version, trạng thái health, key ID/version, số lượt gọi, principal, operation, thời điểm, lỗi và correlation ID** theo chính sách. **Không ghi raw seed/state, key material, plaintext DEK, private key, bearer token hoặc password**. Nếu cần dữ liệu thử thống kê thô, hãy dùng nguồn kiểm thử tách biệt và quản lý dữ liệu đó.

## 13. Tình huống kiến trúc: Auth Service và Customer Data Service

Hệ thống có **Auth Service**, **Customer Data Service**, **KMS** và nhiều container replica. Mục tiêu: phát token khó đoán, mã hóa hồ sơ bằng AES-GCM, scale không gây nonce reuse và có bằng chứng vận hành.

**Phương án kiểm tra và triển khai:**

1. **Provider:** xác định SecureRandom/KMS/HSM được chấp thuận. Không nhúng seed cố định vào image, không fallback Random khi khởi tạo lỗi.
2. **Token tests:** unit test bằng fake để kiểm tra độ dài, Base64URL, expiry và các lỗi; integration test kiểm tra provider thật, format, chính sách, không kết luận entropy từ histogram.
3. **Token operations:** không log bearer token, ràng buộc principal/scope/expiry, có rate limit và cơ chế thu hồi.
4. **DEK generation:** dùng API KMS GenerateDataKey hoặc KeyGenerator được chấp thuận. DEK bản rõ tồn tại ngắn, KEK được giữ theo policy.
5. **AES-GCM:** chọn random nonce với giới hạn tổng invocation hoặc bộ nonce cấu trúc được phân phối; kiểm tra restart, retry, backfill, snapshot và counter rollover.
6. **AAD và authorization:** tenant/record/version được ràng buộc vào AAD và kiểm tra quyền trước khi decrypt. RNG tốt không thay thế IAM và AEAD verification.
7. **Audit:** theo dõi key ID/version, provider, action, health alerts và usage limits. Không đưa key material vào trace.
8. **Incident response:** khi phát hiện RNG/provider bất thường, dừng cấp secret mới nếu thích hợp, khoanh vùng những khóa/token/nonce có khả năng chịu ảnh hưởng, rotate/revoke/re-encrypt và kiểm tra recovery.

Điểm đáng nhớ là có **hai đối tượng kiểm thử khác nhau**: (a) **nguồn/cơ chế tạo random** và (b) **ứng dụng sử dụng random theo contract mật mã**. Kết quả PASS của một bên không tự phủ nhận rủi ro ở bên kia.

## 14. Những ngộ nhận cần tránh

| Ngộ nhận | Vấn đề | Hướng xử lý |
|---|---|---|
| “Tỷ lệ bit 1 gần 50% là đủ” | Chuỗi dự đoán được cũng có thể cân bằng | Đánh giá entropy/DRBG/state, dùng thống kê bổ trợ |
| “Pass SP 800-22 nghĩa là CSPRNG được chứng nhận” | Statistical tests không chứng minh unpredictability | Đánh giá đúng chuẩn và provider |
| “Một p-value nhỏ nghĩa chắc chắn RNG hỏng” | Có false positives và ảnh hưởng mẫu | Điều tra theo kế hoạch kiểm định |
| “Không thấy trùng 1.000 nonce là không thể trùng” | Mẫu quá nhỏ so với sản lượng | Phân tích uniqueness/probability/limits theo key |
| “Timestamp/PID là seed đủ mạnh” | Có thể dự đoán hoặc trùng | Nguồn entropy/provider đúng |
| “Dùng Random để production dễ test hơn” | Secret dễ đoán | Fake trong test, CSPRNG trong production |
| “Hardcode seed trong image giúp mọi máy ổn định” | State/chuỗi có thể bị clone | Không đóng gói seed/secret; kiểm tra fork/restore |
| “getInstanceStrong() luôn có latency và đặc tính tốt nhất” | Phụ thuộc provider và môi trường | Kiểm tra trong runtime thật |
| “Lấy randomByte % n luôn đều” | Có **modulo bias** nếu không chia hết | Bounded sampling phù hợp |
| “Nonce AES-GCM cố định nhưng AES-256 đủ mạnh” | Nonce reuse phá tính bí mật/toàn vẹn | Nonce không trùng theo cùng key |
| “UUID nào cũng là token bí mật” | Version/nguồn và chính sách có thể khác | Dùng token generator/entropy policy riêng |
| “Log toàn bộ sample token để debug RNG” | Chính test làm lộ credential | Test sample riêng; log metadata và số liệu |
| “CSPRNG smoke test đạt là FIPS validated” | Xác nhận áp dụng cho module/cấu hình cụ thể | Xem bằng chứng chứng nhận chính xác |

## 15. Checklist trước khi đưa secure randomness vào production

1. **Mục đích:** giá trị nào cần unpredictability (key/token), giá trị nào cần uniqueness (nonce/counter), giá trị nào chỉ dùng cho mô phỏng?
2. **Provider:** tên/phiên bản JDK, algorithm, cấu hình KMS/HSM có được inventory và đánh giá theo policy?
3. **Entropy:** nguồn, seed/reseed, health monitoring và điều kiện startup đã được xác nhận?
4. **Kiểm thử thống kê:** có giả thuyết, cỡ mẫu, mức ý nghĩa và cách diễn giải false positive?
5. **Không nói quá kết luận:** PASS frequency/chi-square không được xem là bằng chứng cryptographic security.
6. **Unit tests:** dùng fake riêng cho test, production không thể rơi vào nguồn non-crypto.
7. **Key generation:** KeyGenerator/KeyPairGenerator/GenerateDataKey dùng nguồn an toàn và đúng tham số.
8. **AES-GCM:** nonce duy nhất theo mỗi DEK qua concurrency, retry, restart, snapshot và rotation.
9. **Token:** đủ độ dài theo threat model, scope, expiry, revoke, rate limit và không log.
10. **KDF/passwords:** phân biệt salt, IV, seed, IKM và derived key theo từng thuật toán.
11. **Monitoring:** có cảnh báo khi RNG/entropy source hỏng hoặc provider thay đổi bất thường.
12. **Incident response:** biết cách dừng phát secret, khoanh vùng và rotate/revoke/re-encrypt.
13. **Audit:** giữ bằng chứng cấu hình và hành động mà không lộ seed/key/token.
14. **Chuẩn:** nếu áp dụng SP 800-90A/B/C hoặc FIPS 140-3, có bằng chứng theo phạm vi đúng thay vì chỉ dựa test output.

### Câu hỏi tự kiểm tra

**Câu 1.** Một generator được seed bằng hằng số, vượt qua nhiều kiểm định tần suất. Có thể dùng sinh khóa AES không?

**Trả lời:** **Không.** Ai biết seed/thuật toán có thể tái tạo chuỗi; việc trông đều không thay thế unpredictability.

**Câu 2.** Mẫu SecureRandom có 49,9% bit 1. Có thể suy ra nó có 256 bit entropy không?

**Trả lời:** **Không.** Tần suất là một tính chất thống kê của mẫu, không phải entropy estimate của nguồn hay chứng cứ DRBG an toàn.

**Câu 3.** CSPRNG tốt có thể có p-value nhỏ ở một kiểm định không?

**Trả lời:** **Có.** Kiểm định có xác suất false positive, đặc biệt khi chạy nhiều phép kiểm tra. Cần diễn giải theo mô hình và ngưỡng.

**Câu 4.** Vì sao không nên assert đầu ra SecureRandom bằng một chuỗi cố định?

**Trả lời:** Đầu ra thật phải khó dự đoán. Test logic bằng dependency injection và fake ở test, không thay production source.

**Câu 5.** Nonce 96 bit lấy từ SecureRandom có bảo đảm AES-GCM không bao giờ trùng nonce không?

**Trả lời:** **Không.** Đây là cách cấp nonce có xác suất va chạm; phải tính theo **tổng số lần mã hóa cùng DEK**, đặt giới hạn hoặc dùng một thiết kế uniqueness có cấu trúc.

**Câu 6.** RCT/APT theo SP 800-90B có tương đương kiểm tra đếm bit trên output Java SecureRandom không?

**Trả lời:** **Không.** Chúng áp dụng cho health monitoring của nguồn entropy theo mô hình và quy tắc chuẩn, không phải một phép kiểm định output tùy ý.

**Câu 7.** OTP sáu chữ số sinh từ CSPRNG có 256-bit security không?

**Trả lời:** **Không.** Không gian mã chỉ khoảng một triệu khả năng. Cần expiry, rate limit và giới hạn số lần thử.

**Câu 8.** Hai VM clone cùng state DRBG, phát cùng chuỗi. Một histogram trên từng VM có chắc phát hiện được không?

**Trả lời:** **Không.** Mỗi chuỗi riêng lẻ có thể có phân bố đều. Cần kiểm soát clone/reseed và khả năng độc lập giữa instance.

**Câu 9.** Khi DEK có thể đã được sinh từ nguồn seed yếu, rewrap cùng DEK bằng KEK mới có đủ không?

**Trả lời:** **Không.** Rewrap không cải thiện tính khó đoán của chính DEK. Cần đánh giá thay DEK, mã hóa lại dữ liệu và ứng phó theo phạm vi ảnh hưởng.

**Điểm cốt lõi:** **Kiểm thử randomness đúng cách** kết hợp **entropy source được đánh giá, DRBG/CSPRNG đáng tin, kiểm thử thống kê có giới hạn rõ ràng, kiểm thử logic ứng dụng, nonce management và vận hành an toàn**. Một chuỗi “trông ngẫu nhiên” không chứng minh secret khó đoán. Với Java và KMS/HSM, chất lượng randomness phải được quản trị như một phần của **key lifecycle, IAM, audit, rotation và incident response**.

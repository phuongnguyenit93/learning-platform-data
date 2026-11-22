# Chọn seed, tái lập kết quả và nguy cơ phân bố lệch

Trong **thuật toán ngẫu nhiên**, seed (*hạt giống*) là giá trị dùng khởi tạo bộ sinh số giả ngẫu nhiên — **PRNG**. Seed giúp chạy lại một quá trình có lựa chọn ngẫu nhiên: chọn pivot, shuffle, lấy mẫu, mô phỏng hoặc kiểm tra Monte Carlo. Nhưng **tái lập được**, **có phân phối đều**, **độc lập theo mô hình** và **khó dự đoán** là những tính chất khác nhau. Một seed tưởng như đủ ngẫu nhiên không thể sửa một phép lấy mẫu bị thiên lệch do công thức sai.

Bài thuộc nhóm **Ngẫu nhiên hóa** trong **Computer Science Algorithms**. Mục tiêu chính là lựa chọn seed theo mục đích, bảo đảm tái lập, hiểu các nguy cơ lệch phân phối do reseed, phép chia dư, chọn bit và cấu trúc shuffle; quản lý nhiều stream, thống kê kết quả và chọn nguồn phù hợp cho bảo mật. Bài sử dụng **Java 17**, giải thích phép rút có giới hạn, `Random`, `SplittableRandom`, `ThreadLocalRandom`, `SecureRandom`, và có ví dụ hoàn chỉnh với **stdout đã đối chiếu bằng một mô hình số nguyên độc lập**.

## 1. Seed, trạng thái và entropy

Một PRNG duy trì trạng thái `S_t` và cập nhật theo quy tắc xác định:

\[
S_{t+1}=F(S_t),\qquad R_t=G(S_t).
\]

Seed được biến đổi thành trạng thái ban đầu `S_0`. Cùng loại PRNG, cùng seed, cùng dữ liệu và **cùng thứ tự tham số các lời gọi** thường cho đúng cùng chuỗi đầu ra.

**Entropy** đo độ bất định thực sự của một nguồn. Seed được chứa trong `long` 64 bit **không tự có 64 bit entropy**: nếu seed đến từ một trong 1.000 timestamp có thể đoán được, độ bất định tối đa chỉ khoảng `log₂(1000)≈9,97` bit. **min-entropy** xem xét xác suất của giá trị dễ đoán nhất và là một cách đánh giá nguồn trước kẻ tấn công.

Phân biệt:

| Tính chất | Ý nghĩa | Không suy ra được |
| --- | --- | --- |
| Tái lập (*reproducibility*) | Có thể tạo lại đúng một chuỗi quyết định | Khó dự đoán |
| Đồng đều (*uniformity*) | Mỗi lựa chọn có xác suất mong muốn | Dãy thật sự độc lập |
| Độc lập | Lựa chọn sau không phá giả thiết xác suất về lựa chọn trước | Seed phải bí mật |
| Entropy seed | Bất định của nguồn seed | Kích thước kiểu dữ liệu |
| CSPRNG | Thiết kế nhằm chống dự đoán kết quả | Mọi thuật toán ánh xạ đầu ra đều đúng |
| Thuật toán đúng | Bất biến và phân phối của quyết định đáp ứng yêu cầu | Histogram nhìn đẹp là đủ |

Một nguồn vật lý (TRNG) có thể đóng góp entropy nhưng dữ liệu thô vẫn có thể bị lệch; CSPRNG mở rộng trạng thái được seed thích hợp thành đầu ra khó đoán mà không cần đo nhiễu vật lý ở mỗi byte. **Chọn đúng API không thay cho chứng minh đúng của thuật toán.**

## 2. Seed cố định có ích khi nào?

Trong ví dụ hoặc unit test:

~~~java
Random r = new Random(2026L);
int first = r.nextInt(10);
int second = r.nextInt(10);
~~~

Với `java.util.Random` Java 17, `first=9`, `second=0`. Một đối tượng Random mới với cùng seed và lịch gọi cho đúng hai kết quả đó. Bộ 12 lần rút trong chương trình cuối bài:

~~~text
seed=2026
sequence10=[9, 0, 7, 0, 9, 8, 3, 6, 4, 8, 9, 9]
replaySame=true
~~~

Seed cố định phù hợp cho **tái hiện lỗi**, so sánh hai phiên bản mã, tạo ví dụ có stdout kiểm được và benchmark có kiểm soát. Song chỉ ghi seed **chưa đủ** để replay nếu ta thay:
- Loại generator, thuật toán hoặc phiên bản thư viện/JDK.
- Bound hay số lần gọi `nextInt`, kể cả một lời gọi trong nhánh phụ.
- Input và thứ tự xử lý dữ liệu.
- Cách chia stream cho nhiều task/worker hoặc lịch gọi đa luồng.

Hãy log **generator + seed + input + call order + phân chia stream + phiên bản**. Với randomized Quicksort, seed thay đổi đường chọn pivot và chi phí nhưng **mảng cuối vẫn phải được sắp đúng**. Với Monte Carlo, chính ước lượng có thể khác giữa các seed: replay một run và tạo một run mới là hai mục tiêu khác nhau.

## 3. Lỗi reseed trong vòng lặp

Mã sai khi muốn sáu phép rút khác nhau:

~~~java
for (int i = 0; i < 6; i++) {
    int x = new Random(2026L).nextInt(6);
}
~~~

Mỗi lần tạo một RNG **ở cùng trạng thái ban đầu** rồi lấy đúng phần tử đầu. Kết quả:

~~~text
reseedEachDraw=[5, 5, 5, 5, 5, 5]
~~~

Cách dùng một stream:

~~~java
Random rng = new Random(2026L);
for (int i = 0; i < 6; i++) {
    int x = rng.nextInt(6);
}
~~~

Cho:

~~~text
continuousDraws6=[5, 4, 1, 0, 3, 4]
~~~

Đừng nghĩ sáu số trên là sáu nguồn entropy vật lý mới: PRNG vẫn xác định, nhưng đã tiến trạng thái theo trình tự. Dùng timestamp làm seed trong từng vòng cũng rủi ro: hai lần tạo có thể cùng mốc thời gian hoặc seed dễ đoán. Cảnh báo này nói về **cách cố tình reseed từ nguồn yếu/cùng giá trị**, không khẳng định mọi `new Random()` mặc định luôn có seed trùng.

## 4. `java.util.Random` có trạng thái 48 bit

Trong Java 17, Random dùng bộ sinh đồng dư tuyến tính:

\[
S_0=(\text{seed}\oplus25214903917)\ \&\ (2^{48}-1)
\]

\[
\boxed{S_{t+1}=(25214903917S_t+11)\bmod2^{48}.}
\]

Seed là kiểu `long` nhưng trạng thái chỉ giữ **48 bit thấp**, nên hai seed khác nhau một bội `2^{48}` có **cùng trạng thái đầu**:

~~~text
2026
2026 + 2^48 = 281474976712682
~~~

Hai đối tượng Random khởi tạo bằng các seed trên sinh cùng dãy khi lịch gọi giống nhau. Bài có kiểm tra `seedPlus2pow48Same=true` và đối chiếu 128 cặp seed.

**Không suy rộng** tính chất 48 bit sang mọi PRNG. Hai seed khác nhau và không va chạm trạng thái cũng **chưa tự chứng minh độc lập thống kê**, vì các stream có thể có tương quan.

## 5. Bảng lựa chọn nguồn và seed

| Mục đích | Cách dùng hợp lý | Không nên |
| --- | --- | --- |
| Unit test/hồi quy lỗi | `new Random(fixedSeed)` | Mỗi vòng lại reset Random |
| Ví dụ README | Seed, bound và thứ tự gọi cố định | Ghi stdout của một PRNG không nêu tên |
| Benchmark randomized | Nhiều seed và input, lưu toàn bộ kết quả | Chỉ công bố seed nhanh nhất |
| Mô phỏng | Master seed và stream có quy tắc | Coi 100 lần cùng seed là 100 mẫu độc lập |
| Parallel simulation | Phân stream theo task ID ổn định, có logging | Dựa vào scheduler gán số cho worker |
| Token/khóa/secret | SecureRandom hoặc API mật mã chuẩn | Random(seed) hay timestamp đoán được |
| Hệ thống có đầu vào đối kháng | Phân tích threat model và worst-case | Tin rằng seed công khai sẽ bảo vệ thuật toán |

**Seed 0** không mặc nhiên “xấu” cho hồi quy. Một seed long rất lớn cũng không mặc nhiên có nhiều entropy hay bảo mật tốt.

## 6. Modulo bias: sai phân phối ở bước ánh xạ

Giả sử cần chọn `j∈\{0,\ldots,b-1\}` với xác suất `1/b`. Cách sau thường sai:

~~~java
int j = rng.nextInt() % b;
~~~

Vì `nextInt()` có thể âm, `%` Java có thể trả kết quả âm. Dùng `Math.abs(nextInt())%b` cũng sai khi gặp `Integer.MIN_VALUE`, vì `Math.abs(Integer.MIN_VALUE)` vẫn âm. `Math.floorMod` chỉ biến phần dư thành không âm, **không bảo đảm đồng đều** nếu kích thước miền nguồn không chia hết cho b.

### Phản ví dụ chính xác 8→6

Giả sử x lấy đều từ 0..7; trả `x%6`:

| x | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x%6 | 0 | 1 | 2 | 3 | 4 | 5 | 0 | 1 |

Bucket 0,1 có **2 tiền ảnh**, xác suất **2/8=1/4** mỗi bucket; bucket 2,3,4,5 có **1 tiền ảnh**, xác suất **1/8**. Mục tiêu uniform trên 6 bucket là **1/6**. Hai bucket đầu có xác suất **gấp đôi** bốn bucket sau.

Đây là thiên lệch do **cách ánh xạ**, không phải do seed hay PRNG. Ngay cả nguồn 8 giá trị hoàn hảo vẫn cho kết quả lệch.

### Rejection sampling

Với nguồn đều trên N giá trị và đích b bucket, đặt `L=N-(N mod b)`. Rút x trong [0,N); nếu `x≥L`, **từ chối và rút lại**; còn lại trả x%b. Trong miền chấp nhận có đúng `L/b` tiền ảnh cho từng bucket, vì vậy xác suất mỗi bucket **1/b**.

Với N=8,b=6: chấp nhận 0..5, loại 6,7.

Trong Java 17, dùng API bounded thay vì tự chia dư:

~~~java
int j = rng.nextInt(bound);  // 0 <= j < bound
~~~

Với `bound>0`, `Random.nextInt(bound)` dùng cơ chế thích hợp (rejection khi cần) để tránh kiểu modulo bias này. Nếu tính `i+1` làm bound trong Fisher–Yates, bảo đảm không tràn int.

## 7. Histogram mẫu: đồng đều và cố tình lệch

Chạy 60.000 lần từ mỗi đối tượng `new Random(2026L)` riêng:

**Đúng:** `rng.nextInt(6)`.

**Sai có chủ đích:** `rng.nextInt(8)%6`.

Kết quả xác định:

~~~text
boundedHistogram60000=[10002, 10112, 9970, 9867, 9997, 10052]
moduloHistogram60000=[15006, 14886, 7465, 7495, 7582, 7566]
~~~

Trong mô hình xác suất, cách đúng có kỳ vọng **10.000** mỗi bucket; cách sai có kỳ vọng **15.000** tại bucket 0,1 và **7.500** tại bốn bucket còn lại.

Không đòi mọi bucket đúng chính xác kỳ vọng: số đếm mẫu hữu hạn dao động. Với N phép Bernoulli độc lập, xác suất p, `E[C]=Np` và `Var(C)=Np(1-p)`; N=60.000,p=1/6 cho độ lệch chuẩn khoảng **91,3**. Kết quả PRNG seeded cụ thể là xác định, còn mô hình iid chỉ là cách đánh giá phân phối.

Lý do biết bản modulo sai là **đếm tiền ảnh**, không phải vì histogram nhìn xấu. Histogram đẹp không chứng minh PRNG chống được dự đoán.

## 8. Seed tốt không sửa được shuffle sai

Fisher–Yates chuẩn:

~~~text
for i = n-1 downto 1:
    j = uniformInt(0..i)
    swap(a[i], a[j])
~~~

Ở bước i, chọn đều một trong i+1 vị trí chưa chốt. Mỗi hoán vị nhãn của n phần tử phân biệt cần đúng một chuỗi lựa chọn nên có xác suất:

\[
1/n\cdot1/(n-1)\cdots1/2=\boxed{1/n!}.
\]

Một cách xáo trộn sai:

~~~text
for i = n-1 downto 0:
    j = uniformInt(0..n-1)
    swap(a[i], a[j])
~~~

Nó vẫn giữ đầy đủ phần tử nhưng có thể thay lại vị trí đã xử lý. Với **n=3** và input [0,1,2]:
- Fisher–Yates: `3×2=6` đường, 6 hoán vị, mỗi hoán vị 1 đường.
- Shuffle sai: `3³=27` đường, cùng 6 hoán vị nhưng có hoán vị nhận 4 đường, có hoán vị nhận 5 đường.

| Hoán vị | Đúng | Sai |
| --- | ---: | ---: |
| 012 | 1/6 | 4/27 |
| 021 | 1/6 | 5/27 |
| 102 | 1/6 | 5/27 |
| 120 | 1/6 | 4/27 |
| 201 | 1/6 | 5/27 |
| 210 | 1/6 | 4/27 |

Xác suất 4/27 và 5/27 khác nhau, nên sai phân phối **ngay cả với RNG lý tưởng**. Đổi seed hoặc dùng SecureRandom vẫn không sửa được bản shuffle sai.

Một test chỉ kiểm tra sort(mảng trước)=sort(mảng sau) không chứng minh uniformity: hai phương pháp đều giữ nguyên đa tập. Khi phần tử có giá trị trùng, định lý 1/n! áp dụng cho **hoán vị nhãn**, nhiều hoán vị nhãn có thể cùng hiển thị một dãy giá trị.

## 9. Cẩn thận với bit thấp của bộ sinh yếu

Một LCG tổng quát:

\[
s_{t+1}=(as_t+c)\bmod m.
\]

Ví dụ đồ chơi cố ý yếu: `a=5,c=1,m=16`, seed0, lấy **bit thấp** của trạng thái:

~~~text
state=(5*state+1) mod 16
toyLowBits=[1, 0, 1, 0, 1, 0, 1, 0]
~~~

Vì `s_{t+1}≡s_t+1 mod2`, bit thấp **luân phiên hoàn toàn**. Nếu dùng bit này quyết định một nhánh, lịch nhánh có thể bị đoán trước.

**Không được suy** `java.util.Random.nextInt(2)` cũng luân phiên như ví dụ 4-bit. Java Random trích các bit cao của trạng thái và có xử lý bound. Đây là phản ví dụ cho việc chọn bit/trình sinh kém, không phải mô tả `Random.nextInt(2)`.

## 10. Seed và nhiều stream trong thực nghiệm song song

Một lỗi của mô phỏng: thực hiện 100 run với **cùng seed/input/call order**, rồi coi đó là 100 replications độc lập. Thực chất có thể chỉ là cùng một kịch bản lặp 100 lần.

Ba tình huống:
- **Replay:** chủ đích cùng seed để tái hiện một run.
- **Run mới:** tạo stream khác theo một chính sách và ghi cấu hình.
- **Paired design:** đôi khi **cố ý** sử dụng cùng kịch bản ngẫu nhiên cho hai thuật toán để giảm nhiễu chênh lệch; khi đó phải phân tích **phụ thuộc/ghép cặp**, không coi hai kết quả là iid.

`SplittableRandom` có `split()` để tạo stream con, tiện cho mô phỏng và xử lý song song không yêu cầu mật mã. Hai master cùng seed và cùng thứ tự `split` có thể replay; **điều đó không tự chứng minh mọi stream độc lập tuyệt đối**. `ThreadLocalRandom` phù hợp để tránh chia sẻ trạng thái qua thread, nhưng không thiết kế cho việc client đặt seed tùy ý.

Để tái lập theo worker, gán ID task ổn định → stream ID, log master seed, loại generator, cách split và cấu hình. Không dựa vào scheduler để cấp các giá trị từ một RNG chia sẻ cho từng worker. Cộng `workerId` vào seed không phải bảo đảm tổng quát về độc lập.

## 11. Nguồn cho dữ liệu bí mật: SecureRandom

`Random` có tính tái lập thuận tiện nhưng **không phải CSPRNG** và trạng thái Java 17 chỉ 48 bit. Khi sinh token, khóa, mã xác thực hoặc dữ liệu cần khó dự đoán:

~~~java
byte[] token = new byte[16];
new SecureRandom().nextBytes(token);
// Khong in token len console/log.
~~~

Bài demo chỉ in độ dài `secureTokenBytes=16`, không in byte bí mật. `SecureRandom` có thể sử dụng trạng thái CSPRNG và provider; **không nhất thiết mỗi byte là một bit vật lý mới**. Gọi `setSeed(2026L)` không có hợp đồng replay giống `new Random(2026L)` giữa các provider. Không được đánh đồng độ dài 16 byte với một chứng nhận đầy đủ về entropy thực tế, quản lý token hay bảo mật hệ thống.

**Ngay cả SecureRandom** cũng không sửa lỗi `nextInt(8)%6` và shuffle sai j. Độ khó đoán và đúng phân phối là hai điều kiện riêng.

Nếu có đối thủ chọn input sau khi biết lịch pivot hoặc lịch điểm kiểm tra Monte Carlo, các cận kỳ vọng theo **input cố định độc lập với randomness** có thể không áp dụng nguyên xi. Khi cần bảo đảm worst-case, phải chọn thiết kế/phân tích thích hợp.

## 12. Chương trình Java 17 hoàn chỉnh

File **SeedReproducibilityBiasDemo.java** thực hiện:
1. Replay `Random(2026L)`; seed2027 và seed+2^48.
2. So sánh reseed mỗi vòng với một stream liên tục.
3. Fisher–Yates và hai phép shuffle n=3 được vét cạn.
4. Histogram 60.000 mẫu đúng/sai.
5. LCG đồ chơi, replay `SplittableRandom.split()`.
6. Sinh 16 byte SecureRandom và chỉ in độ dài.
7. Kiểm tra **128 seed-pair**, **272.000 bounded draws** và **64 shuffle giữ đa tập**.

Chạy bằng **JDK 17 trở lên**, không cần thư viện ngoài.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.TreeMap;

public class SeedReproducibilityBiasDemo {
    static final long SEED = 2026L;
    static final int SAMPLES = 60_000;

    static int[] firstDraws(long seed, int count, int bound) {
        if (count < 0 || bound <= 0)
            throw new IllegalArgumentException();
        Random rng = new Random(seed);
        int[] a = new int[count];
        for (int i = 0; i < count; i++)
            a[i] = rng.nextInt(bound);
        return a;
    }

    // Sai co y: reset RNG moi lan.
    static int[] reseedEachTime(
            long seed, int count, int bound) {
        int[] a = new int[count];
        for (int i = 0; i < count; i++)
            a[i] = new Random(seed).nextInt(bound);
        return a;
    }

    static void swap(int[] a, int i, int j) {
        int t = a[i];
        a[i] = a[j];
        a[j] = t;
    }

    // Fisher-Yates dung.
    static void fisherYates(int[] a, Random rng) {
        for (int i = a.length - 1; i > 0; i--) {
            int j = rng.nextInt(i + 1);
            swap(a, i, j);
        }
    }

    // VET CAN cac duong shuffle n=3.
    static void enumerate(
            int i, int[] a, boolean wrong,
            Map<String,Integer> counts) {
        if (i < 0) {
            String key = "" + a[0] + a[1] + a[2];
            counts.merge(key, 1, Integer::sum);
            return;
        }
        int bound = wrong ? a.length : i + 1;
        for (int j = 0; j < bound; j++) {
            int[] b = a.clone();
            swap(b, i, j);
            enumerate(i - 1, b, wrong, counts);
        }
    }

    static Map<String,Integer> allOutcomes(boolean wrong) {
        Map<String,Integer> result = new TreeMap<>();
        enumerate(2, new int[]{0,1,2}, wrong, result);
        return result;
    }

    static int paths(Map<String,Integer> map) {
        return map.values().stream()
                .mapToInt(Integer::intValue).sum();
    }

    static int[] exactModuloCounts() {
        int[] a = new int[6];
        for (int x = 0; x < 8; x++)
            a[x % 6]++;
        return a;
    }

    static int[] boundedHistogram() {
        Random rng = new Random(SEED);
        int[] a = new int[6];
        for (int i = 0; i < SAMPLES; i++)
            a[rng.nextInt(6)]++;
        return a;
    }

    // Sai phan phoi: 8 gia tri ve 6 bucket.
    static int[] moduloHistogram() {
        Random rng = new Random(SEED);
        int[] a = new int[6];
        for (int i = 0; i < SAMPLES; i++)
            a[rng.nextInt(8) % 6]++;
        return a;
    }

    static int[] toyLowBits() {
        int state = 0;
        int[] bits = new int[8];
        for (int i = 0; i < bits.length; i++) {
            state = (5 * state + 1) & 15;
            bits[i] = state & 1;
        }
        return bits;
    }

    static boolean splitReplay() {
        SplittableRandom m1 = new SplittableRandom(SEED);
        SplittableRandom m2 = new SplittableRandom(SEED);
        SplittableRandom a1 = m1.split(), a2 = m2.split();
        SplittableRandom b1 = m1.split(), b2 = m2.split();
        for (int i = 0; i < 32; i++) {
            if (a1.nextInt(1_000_000)
                    != a2.nextInt(1_000_000))
                return false;
            if (b1.nextInt(1_000_000)
                    != b2.nextInt(1_000_000))
                return false;
        }
        return true;
    }

    record Stats(int seeds, int bounded, int shuffles) {}

    static Stats verify() {
        Map<String,Integer> good = allOutcomes(false);
        Map<String,Integer> wrong = allOutcomes(true);
        if (good.size() != 6 || paths(good) != 6
                || good.values().stream().anyMatch(v -> v != 1))
            throw new AssertionError("Good shuffle");
        if (wrong.size() != 6 || paths(wrong) != 27
                || wrong.values().stream().anyMatch(
                    v -> v != 4 && v != 5))
            throw new AssertionError("Wrong shuffle");
        if (!Arrays.equals(exactModuloCounts(),
                new int[]{2,2,1,1,1,1}))
            throw new AssertionError("Modulo mapping");

        int seeds = 0;
        for (long seed = 0; seed < 128; seed++) {
            Random a = new Random(seed);
            Random b = new Random(seed);
            Random upper = new Random(seed + (1L << 48));
            for (int i = 0; i < 32; i++) {
                int x = a.nextInt(1000);
                if (x != b.nextInt(1000)
                        || x != upper.nextInt(1000))
                    throw new AssertionError("Seed mismatch");
            }
            seeds++;
        }

        int bounded = 0;
        for (int bound = 1; bound <= 17; bound++) {
            for (int seed = 0; seed < 16; seed++) {
                Random rng = new Random(seed);
                for (int i = 0; i < 1000; i++) {
                    int x = rng.nextInt(bound);
                    if (x < 0 || x >= bound)
                        throw new AssertionError("Bad bound");
                    bounded++;
                }
            }
        }

        int shuffles = 0;
        for (long seed = 0; seed < 64; seed++) {
            int[] a = {0,1,2,3,4,5,6,7,8,9};
            fisherYates(a, new Random(seed));
            Arrays.sort(a);
            if (!Arrays.equals(a,
                    new int[]{0,1,2,3,4,5,6,7,8,9}))
                throw new AssertionError("Lost element");
            shuffles++;
        }

        if (seeds != 128 || bounded != 272_000
                || shuffles != 64)
            throw new AssertionError("Test count mismatch");
        return new Stats(seeds, bounded, shuffles);
    }

    public static void main(String[] args) {
        System.out.println("seed=" + SEED);

        int[] seq = firstDraws(SEED, 12, 10);
        System.out.println("sequence10="
                + Arrays.toString(seq));
        System.out.println("replaySame="
                + Arrays.equals(
                    seq, firstDraws(SEED, 12, 10)));
        System.out.println("sequence10OtherSeed="
                + Arrays.toString(
                    firstDraws(SEED + 1, 12, 10)));
        System.out.println("seedPlus2pow48Same="
                + Arrays.equals(
                    seq, firstDraws(
                        SEED + (1L << 48), 12, 10)));

        System.out.println("reseedEachDraw="
                + Arrays.toString(
                    reseedEachTime(SEED, 6, 6)));
        System.out.println("continuousDraws6="
                + Arrays.toString(
                    firstDraws(SEED, 6, 6)));

        int[] sample = {0,1,2,3,4,5,6,7,8,9};
        fisherYates(sample, new Random(SEED));
        System.out.println("fisherYates10="
                + Arrays.toString(sample));

        System.out.println("exactMod8To6Counts="
                + Arrays.toString(exactModuloCounts()));
        System.out.println("boundedHistogram60000="
                + Arrays.toString(boundedHistogram()));
        System.out.println("moduloHistogram60000="
                + Arrays.toString(moduloHistogram()));

        Map<String,Integer> good = allOutcomes(false);
        Map<String,Integer> wrong = allOutcomes(true);
        System.out.println("good3Paths=" + paths(good));
        System.out.println("good3Counts=" + good);
        System.out.println("wrong3Paths=" + paths(wrong));
        System.out.println("wrong3Counts=" + wrong);

        System.out.println("toyLowBits="
                + Arrays.toString(toyLowBits()));
        System.out.println("absMinIntNegative="
                + (Math.abs(Integer.MIN_VALUE) < 0));
        System.out.println("splitReplay=" + splitReplay());

        byte[] secret = new byte[16];
        new SecureRandom().nextBytes(secret);
        System.out.println("secureTokenBytes=" + secret.length);

        Stats s = verify();
        System.out.println("verifiedSeedPairs=" + s.seeds());
        System.out.println("verifiedBoundedDraws=" + s.bounded());
        System.out.println("verifiedShuffleMultisets="
                + s.shuffles());
        System.out.println("verification=PASS");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SeedReproducibilityBiasDemo.java
java SeedReproducibilityBiasDemo
~~~

**Stdout dự kiến:**

~~~text
seed=2026
sequence10=[9, 0, 7, 0, 9, 8, 3, 6, 4, 8, 9, 9]
replaySame=true
sequence10OtherSeed=[5, 8, 8, 4, 8, 7, 6, 4, 6, 0, 9, 5]
seedPlus2pow48Same=true
reseedEachDraw=[5, 5, 5, 5, 5, 5]
continuousDraws6=[5, 4, 1, 0, 3, 4]
fisherYates10=[0, 8, 1, 2, 5, 3, 7, 6, 4, 9]
exactMod8To6Counts=[2, 2, 1, 1, 1, 1]
boundedHistogram60000=[10002, 10112, 9970, 9867, 9997, 10052]
moduloHistogram60000=[15006, 14886, 7465, 7495, 7582, 7566]
good3Paths=6
good3Counts={012=1, 021=1, 102=1, 120=1, 201=1, 210=1}
wrong3Paths=27
wrong3Counts={012=4, 021=5, 102=5, 120=4, 201=5, 210=4}
toyLowBits=[1, 0, 1, 0, 1, 0, 1, 0]
absMinIntNegative=true
splitReplay=true
secureTokenBytes=16
verifiedSeedPairs=128
verifiedBoundedDraws=272000
verifiedShuffleMultisets=64
verification=PASS
~~~

**Ý nghĩa:** cùng seed cho cùng sequence; seed+2^48 cũng cho cùng sequence ở Java Random; reseed 6 lần tạo 6 số 5; stream liên tục cho 6 số khác nhau; modulo 8→6 làm hai bucket đông hơn; shuffle sai không đồng đều; bộ sinh 4-bit đồ chơi có bit thấp luôn luân phiên; `splitReplay=true` chỉ là replay stream theo cùng cấu trúc, không chứng minh độc lập tuyệt đối; `secureTokenBytes=16` **không in secret**.

## 13. Kiểm chứng trước khi ghi kết luận

**Mô hình PRNG độc lập:** trạng thái 48-bit của `Random` được mô phỏng bằng số nguyên lớn, không dùng `double` để nhân `25214903917×state` vì phép nhân này có thể mất bit. Mô hình tái lập dãy 12 số với seed 2026,2027,2026+2^48, sáu lần bounded, Fisher–Yates và hai histogram. Đây là đối chiếu số học độc lập, **không phải khẳng định đã biên dịch/chạy Java bằng javac trong môi trường biên soạn**.

**Vét cạn shuffle:** duyệt mọi lựa chọn j trên n=3 mà không dựa vào PRNG. Kết quả 6 đường→6 hoán vị đều cho đúng; 27 đường→6 hoán vị xuất hiện 4 hoặc5 lần cho sai. Điều này chứng minh bias **do thuật toán**, không phải hên xui một seed.

**Bounded API:** `bound=1..17`, `seed=0..15`, mỗi cấu hình 1.000 rút, tổng **272.000** phép kiểm `0≤x<bound`. Kiểm tra này chứng minh trong những ca đã thử không có giá trị ngoài miền, **không phải** chứng minh mọi xác suất bucket bằng nhau.

**Seed-pair:** thử seed 0..127 và seed+2^48, 32 lần rút mỗi cặp, **128 cặp khớp**. Công thức mask 48-bit giải thích tổng quát tại sao xảy ra va chạm này.

**Đa tập sau shuffle:** 64 seed xáo trộn mảng 0..9, sort lại và so bản gốc. Mọi lần đủ phần tử, nhưng test này **không đủ** phát hiện shuffle lệch, nên kết hợp vét cạn đường lựa chọn.

**Giới hạn kiểm thử:** histogram gần đều không chứng minh các giá trị iid hay khó dự đoán; p-value cao không chứng nhận RNG hoàn hảo. Nếu đánh giá nhiều seed, cần công bố cách chọn, tránh chỉ báo seed nhanh nhất (**selection bias**). Nếu hai thuật toán dùng cùng các kịch bản ngẫu nhiên để so sánh, phải phân tích bằng **paired design**, không coi chúng là hai mẫu độc lập.

## 14. Vì sao các kết luận đúng?

- **Replay:** PRNG xác định; cùng trạng thái đầu và cùng lời gọi cho dãy giống nhau.
- **Va chạm seed:** thêm 2^48 không đổi 48 bit thấp được giữ trong trạng thái `Random`.
- **Modulo bias:** các bucket có số tiền ảnh khác nhau nên có xác suất khác nhau.
- **Rejection sampling:** miền chấp nhận L chia hết cho b, mỗi bucket có chính xác L/b tiền ảnh, nên xác suất có điều kiện là 1/b.
- **Fisher–Yates:** ở mỗi bước chốt một vị trí từ i+1 lựa chọn đều; mỗi hoán vị nhãn có đúng một chuỗi lựa chọn, xác suất `1/n!`.
- **Shuffle sai:** n=3 có 27 đường đồng khả năng nhưng chia thành 6 hoán vị với tần suất 4/5, không thể đều.
- **LCG 4-bit:** từ `s'=5s+1 mod16` suy ra `s'≡s+1 mod2`; bit thấp đảo mỗi bước.

## 15. Độ phức tạp

| Thao tác | Thời gian | Bộ nhớ |
| --- | --- | --- |
| `nextInt(bound)` một lần | Thường O(1) kỳ vọng, rejection có thể lặp | O(1) |
| N phép rút vào b bucket | O(N+b) | O(b) |
| Fisher–Yates n phần tử | O(n) | O(1) phụ |
| Vét cạn Fisher–Yates | O(n!) đường | Rất lớn với n tăng |
| Vét cạn shuffle sai toàn mảng | O(n^n) đường | Rất lớn |
| Sinh L byte bằng SecureRandom | Phụ thuộc provider/thuật toán, thường tỷ lệ L | O(L) output |

Việc chọn thuật toán mapping sai có thể rất nhanh nhưng **không đúng yêu cầu**; không xem đó là tối ưu hợp lệ.

## 16. Lỗi phổ biến

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Tạo `new Random(seed)` trong mọi vòng | Lặp giá trị đầu | Một RNG cho stream |
| Lấy timestamp làm seed mỗi phần tử | Dễ đoán/có thể trùng | Chiến lược stream có tổ chức |
| Coi mọi seed long khác nhau là dãy khác nhau | Random có trạng thái 48-bit | Hiểu thuật toán PRNG |
| Coi hai seed khác ⇒ độc lập | Có thể va chạm/tương quan | Thiết kế và ghi stream |
| `nextInt()%bound` | Âm và modulo bias | `nextInt(bound)` |
| `abs(nextInt())%bound` | MIN_VALUE và bias | Bounded API/rejection |
| `floorMod(nextInt(),bound)` rồi gọi đều | Chỉ sửa dấu | Chứng minh số tiền ảnh |
| Shuffle với j toàn mảng mỗi bước | Hoán vị lệch | Fisher–Yates j∈[0,i] |
| Test chỉ giữ nguyên đa tập | Không bắt bias | Vét cạn n nhỏ |
| Dùng bit thấp LCG yếu | Tương quan | Nguồn/cách trích bit phù hợp |
| 100 run cùng seed mà gọi độc lập | Dữ liệu lặp | Stream khác nhau, có log |
| Dùng RNG chia sẻ và đòi replay theo thread | Scheduler thay call order | Stream theo task ID |
| Dùng Random cho token | Có thể dự đoán | SecureRandom |
| SecureRandom với mapping sai | Vẫn lệch | Sửa phép lấy mẫu |
| Một histogram đẹp ⇒ an toàn | Không chứng minh crypto | Threat model riêng |
| Chọn seed nhanh nhất rồi không công bố | Selection bias | Ghi đầy đủ benchmark |
| Đổi call order nhưng mong kết quả cũ | Không replay | Ghi version/call order |

## 17. Bài tập và đáp án

**Bài 1.** Cùng seed luôn cho cùng dãy không?

*Đáp án:* Chỉ khi cùng generator, trạng thái và thứ tự lời gọi.

**Bài 2.** Seed lưu trong long 64-bit có mặc định 64-bit entropy không?

*Đáp án:* Không; entropy phụ thuộc phân phối nguồn seed.

**Bài 3.** Java Random có trạng thái bao nhiêu bit?

*Đáp án:* 48 bit trong thuật toán Java 17 này.

**Bài 4.** Seed 2026 và seed 2026+2^48 cho Random thế nào?

*Đáp án:* Cùng trạng thái đầu, cùng dãy nếu gọi giống nhau.

**Bài 5.** Vì sao tạo Random(2026) sáu lần rồi mỗi lần lấy số đầu giống nhau?

*Đáp án:* Mỗi lần reset về cùng seed.

**Bài 6.** Muốn một chuỗi sáu số tái lập, nên đặt RNG ở đâu?

*Đáp án:* Ngoài vòng lặp, dùng liên tục.

**Bài 7.** x đều 0..7, x%6: bucket nào có xác suất gấp đôi?

*Đáp án:* 0 và 1.

**Bài 8.** Rejection 8→6 cần bỏ x nào?

*Đáp án:* 6 và 7.

**Bài 9.** Vì sao Math.abs(Integer.MIN_VALUE) vẫn âm?

*Đáp án:* Trị tuyệt đối 2^31 không nằm trong int dương.

**Bài 10.** floorMod có tự sửa modulo bias không?

*Đáp án:* Không; chỉ sửa phần dư âm.

**Bài 11.** Fisher–Yates lấy j từ khoảng nào ở bước i?

*Đáp án:* Từ 0..i.

**Bài 12.** n=3 có bao nhiêu đường Fisher–Yates?

*Đáp án:* 6.

**Bài 13.** Shuffle sai toàn mảng n=3 có bao nhiêu đường?

*Đáp án:* 27, phân thành 4 hoặc5 đường mỗi hoán vị.

**Bài 14.** Vì sao test đa tập không chứng minh shuffle đều?

*Đáp án:* Swap sai vẫn giữ nguyên đa tập.

**Bài 15.** Bit thấp của LCG 4-bit đồ chơi cho chuỗi nào?

*Đáp án:* 1,0,1,0,...

**Bài 16.** Có suy Java Random.nextInt(2) luôn luân phiên không?

*Đáp án:* Không; cách trích bit khác ví dụ đồ chơi.

**Bài 17.** 60.000 lần chọn đều 6 bucket, kỳ vọng mỗi bucket?

*Đáp án:* 10.000.

**Bài 18.** nextInt(8)%6 cho kỳ vọng bucket 0 và bucket 3?

*Đáp án:* 15.000 và 7.500.

**Bài 19.** Histogram đều chứng minh CSPRNG không?

*Đáp án:* Không, khó dự đoán không suy ra từ tần suất.

**Bài 20.** 100 run cùng seed/input/lịch gọi có là 100 replication độc lập?

*Đáp án:* Không, có thể là cùng run lặp.

**Bài 21.** Cùng kịch bản cho hai thuật toán so sánh có luôn sai không?

*Đáp án:* Không; paired/common-random-numbers design có thể hợp lệ, cần tính tương quan.

**Bài 22.** Muốn replay đa luồng cần log gì?

*Đáp án:* Seed, PRNG, mapping task→stream, lịch split/call, input và version.

**Bài 23.** Vì sao một RNG chia sẻ khó replay từng worker?

*Đáp án:* Interleaving thay đổi worker nhận số nào.

**Bài 24.** SecureRandom.setSeed(2026) có bảo đảm replay mọi provider không?

*Đáp án:* Không.

**Bài 25.** SecureRandom sửa được shuffle chọn j sai miền không?

*Đáp án:* Không; phải sửa thuật toán.

**Bài 26.** Với N=60.000,p=1/6 theo iid, độ lệch chuẩn số đếm khoảng bao nhiêu?

*Đáp án:* \(\sqrt{Np(1-p)}\approx91,3\).

**Bài 27.** Chỉ báo seed chạy nhanh nhất trong 100 seed có vấn đề gì?

*Đáp án:* Selection bias; cần công bố phương pháp chọn/các run.

**Bài 28.** Một p-value lớn chứng nhận PRNG hoàn hảo không?

*Đáp án:* Không, chỉ chưa phát hiện lệch theo kiểm định.

**Bài 29.** Seed cố định phù hợp trong tình huống nào?

*Đáp án:* Unit test, demo có stdout, tái lập lỗi.

**Bài 30.** Có nên dùng cùng Random(2026) cho demo và token đăng nhập không?

*Đáp án:* Không; token cần SecureRandom và chính sách bí mật phù hợp.

## 18. Checklist thực hành

1. Xác định mục tiêu: replay, sampling, Monte Carlo, bảo mật hay chống input đối kháng.
2. Ghi thuật toán RNG, seed, input, lịch gọi, bound, version và cách phân stream.
3. Dùng một RNG cho một stream, không reseed cùng giá trị mỗi lần rút.
4. Hiểu trạng thái hiệu dụng của generator; `Random` Java 17 chỉ 48 bit.
5. Dùng `nextInt(bound)` hoặc rejection, tránh %bound tùy tiện.
6. Shuffle đúng dùng j từ 0..i ở bước i.
7. Không nhầm giữ đa tập với xáo trộn đều.
8. Dùng stream ổn định theo task để tái lập song song.
9. Chạy nhiều seed và công bố phương pháp, tránh cherry-picking.
10. Dùng SecureRandom cho secrets và không in log.
11. Xác định mô hình đầu vào có đối thủ và worst-case nếu cần.
12. Kết hợp vét cạn nhỏ, chứng minh xác suất và kiểm thử thống kê.
13. Không coi histogram gần đều là chứng chỉ iid hoặc mật mã.
14. Không coi seed to là nguồn có entropy cao.
15. Giải thích riêng reproducibility, uniformity, independence và unpredictability.

## Tổng kết

Seed giúp **tái lập đường chạy**, không tự chứng minh **đúng phân phối**. Trong `java.util.Random` Java 17, seed long được ánh xạ xuống trạng thái **48 bit**, nên hai seed cách `2^{48}` có thể tạo cùng dãy. Tạo lại cùng RNG ở mỗi vòng lặp có thể chỉ tạo một giá trị lặp đi lặp lại.

Nguy cơ lệch có thể xuất hiện **ở phép ánh xạ** chứ không phải ở seed: `nextInt(8)%6` tạo hai bucket xác suất gấp đôi, và shuffle sai j trên toàn mảng tạo các hoán vị có xác suất 4/27 hoặc5/27 thay vì 1/6. Đổi sang SecureRandom **không sửa** thuật toán mapping sai.

Để thiết kế thuật toán ngẫu nhiên đáng tin, hãy chọn generator theo mục đích, quản lý seed/stream, chứng minh cách lấy mẫu, kiểm thử mọi nhánh nhỏ và đánh giá các giả thiết thống kê. Dùng **SecureRandom** cho bí mật, còn seeded PRNG cho các thí nghiệm cần replay.

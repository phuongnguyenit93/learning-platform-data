# Seed – Hạt giống ngẫu nhiên cho bộ sinh số mật mã

**Seed** (giá trị khởi tạo, thường gọi là *hạt giống*) là dữ liệu đầu vào dùng để thiết lập trạng thái ban đầu của một **bộ sinh số giả ngẫu nhiên**. Với hệ thống mật mã, seed phải được xử lý theo đúng thuật toán và có đủ **entropy (độ khó dự đoán)** để bộ sinh số ngẫu nhiên mật mã (**CSPRNG/DRBG**) tạo ra đầu ra không thể dự đoán trong giới hạn bảo mật được thiết kế.

Trong chương **Secure randomness** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, seed là mắt xích đầu tiên của nhiều vòng đời khóa: **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Nếu nguồn entropy hoặc cách khởi tạo bộ sinh số sai, khóa AES, cặp khóa bất đối xứng, mã định danh phiên và các bí mật được tạo về sau có thể bị đoán được, dù thuật toán mã hóa, chữ ký số, KMS/HSM hay envelope encryption đều được cấu hình đúng.

> **Điều quan trọng nhất:** **Độ dài seed không đồng nghĩa lượng entropy của seed**. Một chuỗi 32 byte toàn số 0 vẫn có 256 bit dữ liệu biểu diễn nhưng gần như **không có entropy bí mật** nếu giá trị đó được biết trước. Không được biến timestamp, PID hoặc một hằng số trong mã nguồn thành seed cho bộ sinh khóa mật mã.

## 1. Seed là gì và liên hệ thế nào với entropy?

Một bộ sinh số giả ngẫu nhiên là thuật toán xác định: với **cùng trạng thái nội bộ** và cùng chuỗi thao tác, một cài đặt xác định của nó sẽ sinh cùng chuỗi kết quả. Nó không tự tạo ra tính khó đoán chỉ vì đầu ra trông hỗn loạn; sự khó đoán phải đến từ **nguồn entropy thích hợp** và cách bộ sinh số biến nguồn đó thành trạng thái bí mật.

Có ba khái niệm liên quan nhưng không đồng nhất:

- **Entropy source (nguồn entropy):** nguồn cung cấp dữ liệu có tính bất định, chẳng hạn cơ chế thu thập entropy được hệ điều hành/hệ thống phần cứng hỗ trợ.
- **Seed/seed material:** vật liệu được bộ sinh số sử dụng khi khởi tạo hoặc tái khởi tạo. Cách chuẩn hóa đầu vào, yêu cầu entropy và định dạng phụ thuộc thuật toán/provider.
- **Internal state (trạng thái nội bộ):** trạng thái bí mật mà DRBG dùng để sinh đầu ra, rồi cập nhật sau các phép sinh.

~~~mermaid
flowchart TD
    SRC["Nguồn entropy đáng tin cậy"] --> CONDITION["Thu thập và xử lý theo cơ chế đã kiểm chứng"]
    CONDITION --> SEED["Seed material có đủ entropy"]
    SEED --> INIT["Khởi tạo CSPRNG / DRBG"]
    INIT --> STATE["Trạng thái nội bộ bí mật"]
    STATE --> OUT["Sinh byte ngẫu nhiên mật mã"]
    OUT --> KEYS["Khóa AES, private key, token, nonce theo quy tắc"]
    OUT --> UPDATE["Cập nhật trạng thái nội bộ"]
    UPDATE --> STATE
    SRC --> RESEED["Bổ sung entropy khi reseed theo chính sách"]
    RESEED --> STATE
~~~

Sơ đồ là mô hình khái niệm, **không phải thứ tự API bắt buộc** của mọi provider. Một số CSPRNG được hệ điều hành cung cấp qua giao diện công khai; ứng dụng không trực tiếp thấy seed hay trạng thái. Các DRBG chuẩn hóa như các cơ chế trong **NIST SP 800-90A** có quy tắc khởi tạo, sinh và tái khởi tạo cụ thể.

### 1.1. Phân biệt độ dài bit và entropy

| Ví dụ nguồn seed | Dài bao nhiêu? | Mức khó đoán thực tế |
| --- | --- | --- |
| 32 byte cố định ghi trong source code | 256 bit biểu diễn | Nếu công khai hoặc suy được, **không tạo bí mật**. |
| 32 byte chỉ gồm một timestamp được lặp lại | 256 bit biểu diễn | Phụ thuộc rất ít vào không gian timestamp có thể đoán. |
| 32 byte sinh bằng CSPRNG đang hoạt động đúng | 256 bit biểu diễn | Có thể cung cấp đầu vào khó đoán ở mức cao, tùy nguồn và mô hình bảo mật. |
| 32 byte từ tệp cache được sao chép vào 100 container | 256 bit biểu diễn | Các bản sao có **cùng seed**; có thể tạo cùng trạng thái trong một thiết kế DRBG xác định. |

Điều kiện an toàn không phải “đã có 256 bit” mà là **số bit entropy được bảo đảm, đặc tính nguồn, cách kết hợp nguồn, DRBG và mức an toàn yêu cầu**. Không thể tăng entropy chỉ bằng cách băm SHA-256 một giá trị đoán được: hash có thể trộn bytes nhưng không tạo thêm bí mật mới.

### 1.2. Vì sao không nên tự “trộn” nguồn ngẫu nhiên?

Các cách như XOR timestamp với PID, nối MAC address với hostname, rồi băm chuỗi bằng SHA-3 có vẻ phức tạp nhưng những thành phần đó thường **dễ quan sát hoặc có không gian tìm kiếm nhỏ**. Nếu mọi thành phần bị đoán được, hash đầu ra vẫn có thể bị tính lại.

Một nguồn entropy không đáng tin không trở nên đáng tin chỉ vì đã đưa qua một hàm băm. Hãy sử dụng **CSPRNG/DRBG do hệ điều hành, provider mật mã hoặc KMS/HSM hỗ trợ**, không tự thiết kế bộ trộn seed cho khóa sản xuất.

## 2. Seed, PRNG, CSPRNG và DRBG khác nhau ra sao?

| Thuật ngữ | Vai trò | Có thích hợp tạo khóa bí mật? |
| --- | --- | --- |
| **Seed** | Dữ liệu khởi tạo một bộ sinh xác định. | Chỉ khi được dùng đúng cơ chế, có entropy phù hợp; bản thân nó không phải thuật toán. |
| **PRNG thông thường** | Sinh chuỗi giả ngẫu nhiên cho mô phỏng, trò chơi hoặc thuật toán không mật mã. | **Không**: nhiều PRNG có thể đoán trạng thái từ đầu ra. |
| **CSPRNG** | Bộ sinh số ngẫu nhiên mật mã có mục tiêu chống dự đoán đầu ra. | **Có**, khi được thiết kế, khởi tạo và vận hành đúng. |
| **DRBG** | Một lớp bộ sinh bit ngẫu nhiên xác định phục vụ mục tiêu mật mã, có cơ chế quản lý trạng thái/entropy theo đặc tả. | **Có**, khi mức bảo mật, entropy, giới hạn sinh và reseed đúng. |
| **TRNG / nguồn ngẫu nhiên vật lý** | Thu thập bất định từ quá trình vật lý/hardware. | Thường là **nguồn entropy**; đầu ra có thể cần health tests và conditioning theo thiết kế. |

Trong Java, **java.util.Random**, **Math.random()**, **ThreadLocalRandom** và **SplittableRandom** không phải API dành cho mục đích mật mã. Dùng chúng để sinh khóa AES, password reset token, API secret, OTP seed hoặc private key là sai mục đích.

**java.security.SecureRandom** là API đúng để yêu cầu bytes ngẫu nhiên mật mã từ một provider của Java. Tuy nhiên kết quả an toàn còn phụ thuộc **provider, cách cấp entropy, cấu hình môi trường và cách ứng dụng dùng những bytes ấy**; từ khóa SecureRandom không tự thay thế thiết kế vòng đời khóa.

### 2.1. Tính xác định không đồng nghĩa yếu

Một DRBG mật mã được thiết kế **xác định sau khi đã khởi tạo**; đó là đặc tính bình thường. Điều quan trọng là kẻ tấn công không biết và không đoán được **trạng thái khởi tạo**, không thể suy ra trạng thái từ các đầu ra đã thấy và không thể điều khiển quá trình reseed.

Ngược lại, một PRNG thông thường có thể sinh các con số trông phân bố đều nhưng vẫn dễ dự đoán. Những phép thử thống kê đơn giản như “không thấy chuỗi lặp” hay “phân bố có vẻ đồng đều” **không chứng minh độ an toàn mật mã**.

## 3. Quá trình seeding và reseeding

**Seeding (khởi tạo seed)** tạo trạng thái ban đầu cho bộ sinh số. **Reseeding (bổ sung entropy/tái khởi tạo trạng thái)** cập nhật bộ sinh với đầu vào entropy mới theo quy tắc của thuật toán và provider.

Một DRBG có thể có các thao tác khái niệm:

~~~text
Instantiate(entropy_input, optional_nonce, optional_personalization)
    -> secret_internal_state

Generate(secret_internal_state, requested_length, optional_additional_input)
    -> random_bits + updated_internal_state

Reseed(secret_internal_state, fresh_entropy_input, optional_additional_input)
    -> refreshed_internal_state
~~~

Đây là **giả mã minh họa**, không phải cú pháp Java hay giao diện chính xác cho mọi DRBG. Một số thuật toán có nonce hoặc personalization string trong quá trình khởi tạo; ý nghĩa và yêu cầu của những trường đó do đặc tả quy định.

### 3.1. Reseed giúp điều gì?

- **Làm mới trạng thái bằng entropy mới** theo chính sách thuật toán, giảm việc phụ thuộc mãi vào một trạng thái.
- Hỗ trợ giới hạn số lần sinh trước khi phải cập nhật, theo đặc tả hoặc cấu hình provider.
- Có thể góp phần phục hồi khả năng chống dự đoán **sau khi trạng thái từng bị lộ**, nếu nguồn entropy mới và quy trình phục hồi đã trở lại đáng tin cậy.

Nhưng reseed **không biến những khóa đã bị lộ thành khóa mới**. Nếu một private key hoặc DEK đã được sinh từ trạng thái RNG bị chiếm đoạt, phải đánh giá thay khóa và ảnh hưởng đến dữ liệu liên quan; không chỉ gọi reseed rồi tuyên bố sự cố kết thúc.

### 3.2. Không nhầm “reseed” với “đặt lại một seed cố định”

- **Reseed đúng:** bộ sinh nhận **entropy mới** từ nguồn được phép, theo quy tắc của provider.
- **Reset seed cố định:** ép mọi phiên bắt đầu từ cùng một giá trị đoán được; điều này có thể làm lặp chuỗi đầu ra trong một PRNG/DRBG xác định.
- **Bổ sung seed qua một API:** có thể chỉ trộn thêm dữ liệu vào trạng thái hiện tại, **không bảo đảm đặt lại** chuỗi đầu ra như kỳ vọng.

Với Java, **SecureRandom.setSeed(...)** là API *bổ sung seed* theo hành vi/provider và **không nên được dùng để ép đầu ra tái lập** trong sản xuất hay kiểm thử. Không giả định mọi SecureRandom triển khai một thuật toán giống nhau hoặc đặt seed sẽ khiến nó trở về cùng trạng thái.

### 3.3. Prediction resistance và backtracking resistance

Trong bảo mật DRBG, cần phân biệt:

- **Backtracking resistance (chống truy hồi):** nếu kẻ tấn công biết trạng thái hiện tại, việc suy ra các đầu ra bí mật **trước đó** vẫn phải khó theo mức bảo đảm của thiết kế.
- **Prediction resistance (chống dự đoán tương lai):** một số cấu hình có thể yêu cầu entropy mới trước các lần sinh để giảm khả năng dự đoán **đầu ra tương lai** khi trạng thái từng bị lộ.

Các thuộc tính này phụ thuộc **thuật toán, phiên bản, cơ chế reseed và môi trường**. Không thể chỉ nhìn số byte seed hoặc tên DRBG mà khẳng định trạng thái đã được phục hồi sau sự cố.

## 4. Phân biệt seed với key, salt, nonce/IV và personalization

Các giá trị này đều có thể xuất hiện trong mật mã, nhưng **mục đích, tính bí mật và quy tắc tái sử dụng khác nhau**.

| Giá trị | Vai trò | Thường có cần giữ bí mật? | Yêu cầu điển hình |
| --- | --- | --- | --- |
| **Seed của DRBG** | Khởi tạo/cập nhật trạng thái bộ sinh. | Vật liệu chứa entropy bí mật phải được bảo vệ; cách quản lý do provider quyết định. | Nguồn đủ entropy, không đoán được, không nhân bản trạng thái. |
| **Secret key / private key** | Mã hóa, ký số, giải mã, MAC hoặc thỏa thuận khóa. | **Có**. | Đúng thuật toán, key usage, vòng đời, giới hạn truy cập. |
| **Salt của password KDF** | Làm kết quả xử lý mật khẩu khác nhau giữa các bản ghi. | **Không**. | Ngẫu nhiên/riêng biệt theo thiết kế; có thể lưu cùng hash. |
| **Nonce của AES-GCM** | Phân biệt các lần mã hóa dưới cùng khóa. | **Không**. | **Không trùng với cùng key**, kể cả qua restart/node. |
| **IV của chế độ mã hóa** | Tham số khởi tạo theo mode. | Thường không, nhưng yêu cầu phụ thuộc mode. | Tuân thủ độ dài, ngẫu nhiên/duy nhất/không đoán được theo mode cụ thể. |
| **Personalization / domain separation** | Phân biệt ngữ cảnh sử dụng của DRBG/KDF theo chuẩn. | Thường không phải bí mật. | Rõ mục đích; **không thay thế entropy**. |

**Quan trọng:** Có một nghĩa khác của từ **seed** trong một số định dạng **private key**. Chẳng hạn “Ed25519 private key seed” có thể chỉ **32 byte bí mật dùng để xác định khóa ký** theo định dạng/giao thức cụ thể. Đây là **vật liệu private key**, không phải seed tùy ý để khởi tạo SecureRandom. Nếu bị lộ, phải xử lý như **lộ private key**.

Tương tự, một **recovery seed phrase** trong một hệ sinh thái khóa phân cấp có thể là bí mật gốc để tái tạo nhiều khóa; không được coi nó là một salt công khai. Luôn xác định **seed của thứ gì** trước khi quyết định lưu, sao lưu, chia sẻ hay hủy.

## 5. Ví dụ Java 17: sinh bí mật từ SecureRandom

Trong ứng dụng Java, cách thông dụng là **để SecureRandom được provider khởi tạo phù hợp**, sau đó dùng API mật mã chuyên dụng để sinh khóa. Không cần tự đặt seed từ timestamp hoặc một hằng số.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class SecureSeedDemo {
    public static void main(String[] args) throws Exception {
        // Provider chọn nguồn và cách khởi tạo thích hợp.
        SecureRandom rng = new SecureRandom();

        // Token ngẫu nhiên: dùng đủ entropy và mã hóa an toàn khi lưu/truyền.
        byte[] tokenA = new byte[32];
        byte[] tokenB = new byte[32];
        rng.nextBytes(tokenA);
        rng.nextBytes(tokenB);

        // Không ghi token thật ra console/log.
        System.out.println("Token length: " + tokenA.length);
        System.out.println("Token samples differ: "
                + !Arrays.equals(tokenA, tokenB));

        // Sinh DEK AES-256 bằng API quản lý khóa thích hợp.
        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(256, rng);
        SecretKey dek = aes.generateKey();

        // Sinh cặp khóa bất đối xứng bằng provider mật mã.
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(3072, rng);
        KeyPair signingPair = rsa.generateKeyPair();

        // Không xuất private key hoặc bytes của DEK để debug.
        System.out.println("DEK algorithm: " + dek.getAlgorithm());
        System.out.println("Key pair algorithm: "
                + signingPair.getPublic().getAlgorithm());

        // Demo: dọn hai mảng token đang giữ trong RAM.
        Arrays.fill(tokenA, (byte) 0);
        Arrays.fill(tokenB, (byte) 0);
    }
}
~~~

**Giải thích:**

1. **new SecureRandom()** lấy implementation theo cấu hình provider; môi trường có thể cần các thiết lập bảo mật riêng. Ứng dụng **không tự seed** bằng giá trị có thể đoán.
2. **nextBytes(...)** cấp bytes ngẫu nhiên mật mã. Ví dụ sinh hai token và so sánh chỉ minh họa cách gọi API; hai token khác nhau **không phải bằng chứng** RNG đạt chuẩn.
3. **KeyGenerator** và **KeyPairGenerator** dùng API đúng thuật toán thay vì biến các chuỗi ngẫu nhiên thành khóa bằng cách cắt/nối tùy tiện.
4. **RSA-3072** chỉ được sinh để minh họa; nếu sau này ký thì cần chọn **RSA-PSS**, còn nếu mã hóa bất đối xứng thì chọn cơ chế phù hợp như RSA-OAEP theo chính sách.
5. **Arrays.fill(...)** chỉ xóa hai mảng token trong ví dụ. JVM, provider hoặc các bản sao dữ liệu khác có thể vẫn giữ bytes bí mật; không xem lệnh này là phương án zeroization toàn bộ.
6. Trong production, nên tạo và giữ **private key/KEK** ở **KMS/HSM** nếu yêu cầu bảo vệ và khả năng của nhà cung cấp phù hợp; ứng dụng có thể chỉ giữ **key ID**.

### 5.1. Những cách dùng Java không phù hợp

~~~java
// KHÔNG dùng để sinh khóa, token xác thực hay secret:
long predictableSeed = System.currentTimeMillis();
java.util.Random weak = new java.util.Random(predictableSeed);
byte[] keyBytes = new byte[32];
weak.nextBytes(keyBytes);

// KHÔNG dựa vào seed cố định để "tái hiện" khóa ở production:
SecureRandom random = new SecureRandom();
random.setSeed(new byte[] {1, 2, 3, 4});

// setSeed chỉ bổ sung seed theo implementation; không thể coi đây
// là cách reset một DRBG hoặc tạo ra chuỗi lặp lại có kiểm soát.
~~~

Trong kiểm thử thuần logic cần tính **reproducible**, có thể dùng PRNG có seed cố định **chỉ với dữ liệu mô phỏng không nhạy cảm**. Để kiểm thử mã dùng mật mã, nên truyền một abstraction cung cấp randomness hoặc dùng **test vector chuẩn trong môi trường test**; không đưa fixed seed, deterministic key hay các secret kiểm thử vào cấu hình production.

**Lưu ý:** SecureRandom.getInstanceStrong() có thể chọn một implementation phù hợp chính sách “strong” của JVM nhưng có thể khác về hiệu năng và khả năng chờ nguồn entropy. Không mặc định rằng gọi API này luôn tốt hơn cho mọi request, và không gọi tạo đối tượng “strong” liên tục ở đường nóng mà chưa đánh giá hiệu năng/provider.

## 6. Seed trong container, VM, snapshot và hệ phân tán

Một rủi ro quan trọng là **sao chép trạng thái bộ sinh** thay vì chỉ sao chép source code. Nếu hai hệ thống khôi phục **đúng cùng trạng thái PRNG/DRBG** rồi thực hiện cùng chuỗi lệnh sinh, chúng có thể tạo những byte đầu ra trùng nhau.

### 6.1. VM snapshot và checkpoint/restore

Giả sử một VM được checkpoint khi một DRBG đã khởi tạo, sau đó khởi chạy hai bản sao từ cùng snapshot. Nếu ứng dụng hoặc provider khôi phục đúng trạng thái cũ **mà không được reseed hoặc bảo vệ chống trùng trạng thái**, hai bản sao có thể tạo cùng token hoặc cùng vật liệu khóa.

**Không suy luận rằng mọi VM/container hiện đại đều gặp lỗi này**: hệ điều hành, hypervisor và provider có thể có cơ chế khôi phục entropy/reseed riêng. Nhưng đây là threat model cần kiểm tra khi sử dụng checkpoint/restore, image clone hoặc cơ chế khôi phục trạng thái tiến trình.

### 6.2. Tiến trình fork và nhiều worker

Khi tạo process con hoặc clone một tiến trình đã khởi tạo RNG, cần xác minh provider và OS có xử lý **fork safety** hoặc tái khởi tạo trạng thái đúng không. Không tự “giải quyết” bằng cách thêm PID hoặc timestamp vào seed vì những giá trị này có thể đoán được và không bảo đảm đủ entropy.

Các worker có thể dùng chung một hệ thống KMS để sinh khóa mà không cần chia sẻ seed. **Một bộ sinh số đáng tin cậy không cần được ứng dụng quản lý bằng seed chung cho toàn bộ cluster.**

### 6.3. Cùng seed có làm nonce AES-GCM an toàn không?

**Không.** Seed phục vụ tính khó đoán của bộ sinh; **nonce AES-GCM** có yêu cầu **không được trùng dưới cùng khóa**. Ngay cả khi nonce lấy từ CSPRNG tốt, việc sinh nonce ngẫu nhiên vẫn có xác suất va chạm, tăng theo số phép mã hóa.

Ở hệ thống mã hóa lưu lượng lớn, cần thiết kế chính sách nonce đúng chuẩn (ví dụ phân bổ miền/đếm theo node có tính bền vững) và giới hạn số lượt mã hóa theo từng DEK. Một seed tốt **không thay thế** ngân sách sử dụng key/nonce.

| Rủi ro | Dấu hiệu hoặc nguyên nhân | Phòng vệ |
| --- | --- | --- |
| Fixed seed trong image container | Cùng secret được đóng vào nhiều môi trường. | Không đóng gói seed/khóa bí mật vào image; dựa trên CSPRNG/KMS lúc chạy. |
| Snapshot nhân bản DRBG state | Hai bản sao xuất cùng chuỗi đầu ra. | Đánh giá cơ chế restore, khởi tạo/reseed phù hợp và kiểm thử luồng triển khai. |
| RNG sẵn quá sớm với nguồn entropy chưa phù hợp | Seed có thể dự đoán hoặc trùng trong thiết bị đặc thù. | Dùng nguồn entropy đã được hệ điều hành/provider bảo đảm; kiểm tra readiness theo nền tảng. |
| Tự thêm timestamp/PID khi thấy trùng | Không thực sự giải quyết vấn đề entropy. | Sửa nguồn RNG và kiến trúc khởi tạo, không tự pha trộn giá trị dễ đoán. |
| Sinh nonce GCM không quản lý quy mô | Va chạm nonce, làm giảm an toàn mã hóa. | Quản lý uniqueness, số lần mã hóa và rotation của DEK. |
| Đưa seed nội bộ vào metrics/log | Lộ trạng thái hoặc vật liệu entropy. | Không log seed, state hoặc key material; chỉ ghi metadata không nhạy cảm. |

## 7. Seed và vòng đời khóa trong KMS/HSM

Một **KMS (Key Management Service)** có thể cung cấp API sinh khóa, wrap/unwrap, ký hoặc giải mã; một **HSM (Hardware Security Module)** có thể bảo vệ vật liệu khóa và sử dụng cơ chế sinh số ngẫu nhiên bên trong ranh giới phần cứng. Kiến trúc và mức bảo đảm cụ thể phụ thuộc nhà cung cấp, thuật toán và cấu hình.

Khi yêu cầu an toàn cao, ưu tiên **để KMS/HSM sinh key material** trong ranh giới đã kiểm soát. Ứng dụng nhận key ID, public key hoặc kết quả phép toán theo API, hạn chế phải nhận trực tiếp seed/private key/KEK dạng rõ.

**Chú ý:** Không mặc định mọi HSM đều có nguồn entropy tốt chỉ vì là phần cứng. Nên xem chính sách vận hành, thông tin kiểm định/kiểm tra sức khỏe RNG, cơ chế cấp entropy, xử lý lỗi và khuyến nghị về backup/redundancy của nhà cung cấp. Không tự xác nhận chất lượng RNG dựa trên tên thiết bị.

### 7.1. Seed có phải được lưu để khôi phục khóa không?

Thông thường, **không nên cố giữ seed DRBG để tái tạo lại khóa về sau**. Việc giữ seed lâu dài có thể tạo ra một bí mật gốc với phạm vi ảnh hưởng rất lớn; nếu bị lộ, các khóa được suy ra từ nó theo một thiết kế xác định có thể bị ảnh hưởng.

Các phương án khôi phục khóa phù hợp hơn gồm:

- Chính sách backup/replica khóa trong **KMS/HSM** theo cơ chế được hỗ trợ.
- **Envelope encryption**: giữ DEK ở dạng đã bọc dưới KEK được quản lý và có kế hoạch phục hồi.
- Khóa ký hoặc khóa giải mã có **key ID, phiên bản và chính sách lưu trữ/khôi phục** rõ ràng.
- Với một ứng dụng thật sự yêu cầu **dẫn xuất khóa xác định từ seed**, dùng **KDF/chuẩn dẫn xuất có mục đích và domain separation**; coi seed gốc là bí mật có mức độ nhạy cảm ít nhất tương đương các khóa con.

**Seed DRBG, master seed và recovery phrase không tự là một khái niệm.** Cần xác định rõ chức năng kỹ thuật trước khi lưu trữ hoặc quyết định khả năng khôi phục.

### 7.2. Seed và tính an toàn của các loại khóa

| Đầu ra liên quan | Seed/RNG ảnh hưởng gì? | Bảo vệ bổ sung |
| --- | --- | --- |
| **DEK đối xứng** | Sinh AES key khó đoán. | Dùng AEAD đúng nonce, giới hạn dữ liệu theo key, wrap dưới KEK. |
| **Private key RSA/EC/Ed25519** | Sinh vật liệu bí mật phù hợp thuật toán. | Chọn tham số đúng, quản lý public key tin cậy, hạn chế xuất private key. |
| **Khóa HMAC/KMAC** | Sinh secret dùng cho MAC. | Tách theo purpose/tenant, phân quyền, không dùng cùng một khóa cho mã hóa. |
| **Session token/reset token** | Đầu ra khó đoán hạn chế khả năng giả mạo. | Thời hạn, một lần dùng khi cần, lưu trữ an toàn, rate limit và thu hồi. |
| **Nonce/IV** | RNG có thể cấp bytes theo chế độ. | Theo dõi **uniqueness/IV policy**, không chỉ độ ngẫu nhiên. |
| **Salt password KDF** | CSPRNG có thể cấp salt riêng cho mỗi bản ghi. | Salt không cần bí mật; password KDF vẫn cần work factor phù hợp. |

Dù seed đủ entropy, một **private key** có thể bị lộ do log, backup hoặc quyền API ký quá rộng. Bảo vệ randomness chỉ là **điều kiện cần** của key management, không phải bảo đảm hoàn chỉnh cho toàn hệ thống.

## 8. Hậu quả và ứng phó khi nghi nguồn seed không an toàn

Giả sử đội vận hành phát hiện một phiên bản ứng dụng dùng **seed cố định**, hoặc sau khi khôi phục VM có hai máy tạo cùng token bí mật. Đây là sự cố cần xử lý ở cấp **vật liệu khóa và danh tính**, không chỉ là lỗi random nhỏ.

Quy trình xử lý có thể gồm:

1. **Ngăn sinh bí mật mới bằng nguồn bị nghi vấn:** tách node/phiên bản lỗi khỏi đường sinh khóa, token và hoạt động bảo mật mới. Nếu ảnh hưởng production, dùng phương án chuyển tuyến đã chuẩn bị.
2. **Xác định phạm vi thời gian và thành phần:** phiên bản ứng dụng, instance, thời điểm boot/restore, provider RNG, loại giá trị đã sinh và nơi lưu bản sao.
3. **Phân loại bí mật bị ảnh hưởng:** AES DEK, private key ký/giải mã, HMAC key, refresh token/reset token, nonce và certificate/key pair đã cấp phát.
4. **Thay thế bí mật và vô hiệu hóa quyền cũ:** tạo khóa bằng nguồn đáng tin, chuyển sang phiên bản mới, thu hồi token hoặc key usage theo chính sách; xử lý public key/chứng chỉ liên quan.
5. **Đánh giá bản mã lịch sử:** nếu DEK bị đoán được, chỉ rotate **KEK** không sửa được dữ liệu đã mã hóa bởi DEK yếu; cần xem xét re-encrypt dưới DEK mới.
6. **Xem xét chữ ký và danh tính:** private key yếu có thể cho phép ký giả. Cần cập nhật trust policy và điều tra các chữ ký phát sinh trong khoảng ảnh hưởng.
7. **Điều tra nonce reuse:** nếu RNG sự cố làm trùng nonce dưới cùng khóa AES-GCM, phải đánh giá cả tính bí mật và xác thực của những bản mã liên quan.
8. **Sửa nguyên nhân và lưu bằng chứng:** khôi phục nguồn entropy/provider đáng tin, bổ sung kiểm soát cấu hình, kiểm toán, điều kiện triển khai và tiêu chí kết thúc sự cố.

**Reseed sau phát hiện không chữa được bản mã đã bị lộ hoặc chữ ký giả đã phát hành.** Nó chỉ có thể cải thiện trạng thái sinh ngẫu nhiên *về sau* theo bảo đảm của hệ thống. Vòng đời xoay vòng/thu hồi/hủy khóa vẫn là công việc riêng.

## 9. Kiểm soát truy cập và kiểm toán liên quan đến seed

Đa số ứng dụng **không cần đọc hoặc lưu seed DRBG**. Giới hạn khả năng truy cập vật liệu này giúp giảm nguy cơ ảnh hưởng dây chuyền.

| Hoạt động | Được phép ghi audit | Không được ghi |
| --- | --- | --- |
| Khởi tạo RNG/provider | Tên provider được phê duyệt, phiên bản runtime, trạng thái health-check/ready khi có. | Seed thực, state DRBG, dữ liệu entropy thô nhạy cảm. |
| Sinh key pair/DEK/KEK | Key ID, thuật toán, key usage, owner, thời gian, kết quả. | Private key, bytes KEK/DEK, seed bí mật. |
| Reseed/recovery | Sự kiện, trạng thái, nguyên nhân, actor được phép, mã yêu cầu. | Bản dump trạng thái bộ sinh. |
| Quản lý KMS/HSM | Quyền Create/Generate/Sign/Decrypt, thay đổi policy, trạng thái lỗi. | Key material dạng rõ hoặc secret có thể dùng để tái tạo khóa. |
| Ứng phó sự cố RNG | Phạm vi instance/version, quyết định thu hồi/xoay, bằng chứng kỹ thuật đã lọc. | Token phiên, dữ liệu nhạy cảm hoặc seed phục hồi đưa vào ticket công khai. |

Hệ thống cần áp dụng **least privilege** cho người quản trị RNG/KMS/HSM và cho ứng dụng tạo khóa. Hãy tách quyền **tạo, sử dụng, sao lưu và hủy** khóa theo mức rủi ro, đồng thời bảo vệ nhật ký kiểm toán khỏi sửa đổi.

Không nên tự xây một dashboard hiển thị seed để “chứng minh entropy tốt”. Việc kiểm tra nhà cung cấp, health test, phiên bản cấu hình và kết quả tự kiểm tra được thiết kế đúng an toàn hơn việc ghi lại bí mật.

## 10. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Seed CSPRNG bằng timestamp/PID/hostname | Đầu vào có thể dự đoán hoặc trùng. | Để OS/provider/KMS/HSM cấp entropy đáng tin. |
| Dùng java.util.Random để sinh khóa AES, API token | Chuỗi có thể được dự đoán. | Dùng SecureRandom và API sinh khóa mật mã. |
| Băm seed yếu bằng SHA-256 rồi coi là đủ entropy | Hash không tạo thêm bí mật cho nguồn đoán được. | Sửa nguồn entropy gốc, không “trang trí” seed. |
| Đóng seed cố định vào image/container | Nhiều instance có thể dùng chung chuỗi bí mật. | Không phát hành seed bí mật trong image; khởi tạo an toàn lúc chạy. |
| Dựa vào setSeed để tái lập output SecureRandom | Hành vi không portable; có thể gây hiểu nhầm về trạng thái. | Dùng test vectors/abstraction cho kiểm thử; không áp fixed seed trong production. |
| Nhân bản VM đã chứa trạng thái RNG | Khả năng trùng token/khóa sau snapshot. | Đánh giá fork/restore-safety của OS và provider. |
| Tin rằng CSPRNG tốt thì nonce GCM không bao giờ trùng | Nonce ngẫu nhiên vẫn có xác suất va chạm. | Thiết kế nonce uniqueness và giới hạn sử dụng theo key. |
| Log seed hoặc state để debug | Có thể làm lộ nhiều đầu ra/khóa tương lai hoặc lịch sử. | Audit metadata không nhạy cảm, không lưu vật liệu nội bộ. |
| Để ứng dụng tự xuất seed/KEK từ HSM | Mở rộng phạm vi bí mật có thể bị đánh cắp. | Ưu tiên sinh và giữ khóa non-exportable khi hệ thống hỗ trợ. |
| Reseed rồi bỏ qua khóa đã được sinh từ RNG lỗi | Khóa cũ vẫn có thể bị đoán. | Kiểm kê, rotate/revoke và đánh giá bản mã/chữ ký liên quan. |
| Đồng nhất seed của private key với seed của DRBG | Áp sai quy trình sao lưu, chia sẻ hoặc hủy. | Gắn rõ loại seed và bảo vệ theo bản chất bí mật. |
| Tự chứng minh entropy bằng vài phép thử thống kê | Có thể bỏ sót nguồn dễ đoán. | Dựa vào thiết kế/kiểm định nguồn, provider và threat model. |

## 11. Câu hỏi tự kiểm tra

1. Tại sao seed dài 256 bit nhưng toàn giá trị cố định không cung cấp 256 bit entropy?
2. PRNG thông thường khác CSPRNG/DRBG ở mục tiêu an toàn nào?
3. Khi nào việc **reseed** là cần thiết và nó có thay được quy trình **rotate key** không?
4. Vì sao không nên gọi **SecureRandom.setSeed(timestamp)** để tạo khóa hoặc “tăng độ an toàn”?
5. Seed DRBG khác salt password KDF và nonce AES-GCM như thế nào?
6. Điều gì có thể xảy ra khi hai VM phục hồi cùng trạng thái DRBG từ một snapshot?
7. Một seed tốt có tự bảo đảm nonce AES-GCM không trùng trên hàng tỷ lần mã hóa không?
8. “Ed25519 private key seed” nên được bảo vệ như một seed ngẫu nhiên công khai hay như private key?
9. Nếu phát hiện nguồn RNG yếu đã tạo DEK, việc chỉ rotate KEK có đủ bảo vệ bản mã cũ không?
10. Vì sao không nên lưu seed để “phục hồi khóa” khi đã có KMS/HSM và cơ chế backup/rewrap phù hợp?
11. Trong Java 17, nên dùng API nào để cấp bytes ngẫu nhiên mật mã? Vì sao Math.random() không phù hợp?
12. Nên ghi gì vào audit log về RNG và thao tác sinh khóa mà không làm lộ vật liệu bí mật?

**Ghi nhớ:** **Seed** đóng vai trò khởi tạo trạng thái cho bộ sinh số xác định, còn **entropy** quyết định mức khó đoán của vật liệu đầu vào. Hệ thống mật mã an toàn cần CSPRNG/DRBG được khởi tạo và reseed đúng, tránh seed đoán được hoặc trạng thái bị nhân bản, đồng thời bảo vệ khóa sinh ra bằng KMS/HSM, phân quyền, kiểm toán và quy trình xoay vòng/thu hồi/hủy. **Randomness an toàn là nền tảng; quản lý khóa và cách sử dụng khóa mới quyết định an toàn trọn vẹn.**

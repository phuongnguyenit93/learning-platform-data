# 7.3 Vai trò của salt, số vòng lặp, độ dài đầu ra và phiên bản cấu hình

Khi lưu mật khẩu hoặc dẫn xuất khóa từ mật khẩu trong Java, ta thường gặp các tham số **salt**, **iteration count (số vòng lặp)**, **derived key length (độ dài đầu ra)** và **configuration version (phiên bản cấu hình)**. Chúng trả lời bốn câu hỏi riêng biệt:

1. **Salt:** hai lần xử lý cùng một mật khẩu có tạo cùng kết quả hay không, và có thể dùng bảng tính sẵn hoặc chia sẻ kết quả tấn công cho nhiều tài khoản hay không?
2. **Số vòng lặp / chi phí:** một lần thử đoán mật khẩu đòi hỏi bao nhiêu công việc tính toán?
3. **Độ dài đầu ra:** kết quả nhị phân có bao nhiêu bit/byte để so sánh hoặc dùng làm vật liệu khóa?
4. **Phiên bản cấu hình:** làm sao biết kết quả cũ được tạo bằng thuật toán và tham số nào, xác minh được nó rồi nâng cấp an toàn khi chính sách thay đổi?

Bốn tham số **không thay thế nhau**. Salt không làm một mật khẩu yếu trở nên khó đoán; tăng output từ 256 lên 512 bit không làm entropy mật khẩu tăng; số vòng lặp cần được hiệu chỉnh theo phần cứng và nhu cầu vận hành; còn phiên bản cấu hình giúp hệ thống di chuyển từ chính sách cũ sang chính sách mới.

Bài này thuộc chủ đề **mật khẩu và dẫn xuất khóa**. Cần phân biệt hai mục tiêu: **password hashing để xác minh đăng nhập** và **password-based key derivation để tạo khóa mã hóa**. Cả hai có thể dùng KDF, nhưng vòng đời và cách lưu kết quả khác nhau.

## 1. Khung khái niệm: mật khẩu, KDF và verifier

Một hàm dẫn xuất khóa từ mật khẩu thường có dạng trừu tượng:

```text
derived = KDF(password, salt, cost_parameters, output_length, algorithm)
```

Với **PBKDF2-HMAC-SHA256**, mô hình có thể viết:

```text
DK = PBKDF2-HMAC-SHA256(P, S, c, dkLen)
P      = mật khẩu
S      = salt
c      = số vòng lặp (iteration count)
dkLen  = độ dài đầu ra mong muốn (byte theo đặc tả PBKDF2)
DK     = derived key (các byte kết quả)
```

Trong Java `PBEKeySpec(char[] password, byte[] salt, int iterationCount, int keyLength)` dùng `keyLength` **theo bit**, khác ký hiệu `dkLen` **theo byte** trong đặc tả PBKDF2. Vì vậy **256** trong `PBEKeySpec(..., 256)` tạo mục tiêu đầu ra **256 bit = 32 byte**, không phải 256 byte.

**KDF** là khái niệm rộng; từng họ có tham số chi phí riêng:

| Thuật toán | Tham số chi phí chính | Đặc tính | Nơi thường gặp |
| --- | --- | --- | --- |
| **PBKDF2-HMAC-SHA256** | `iterations` | Gia tăng chi phí CPU theo số vòng lặp | Java JCA/JCE, hệ thống cần PBKDF2 |
| **Argon2id** | `memory`, `time cost`, `parallelism` | Memory-hard, nhằm tăng chi phí tấn công song song/GPU | Hệ thống có thư viện Argon2id đáng tin |
| **scrypt** | `N`, `r`, `p` | Memory-hard với tham số tài nguyên | Một số hệ thống password hashing/KDF |
| **bcrypt** | Cost factor (logarithmic) | Cơ chế chi phí riêng, có giới hạn đầu vào cần chú ý | Password verifier của ứng dụng legacy/hiện hữu |

Không thể so sánh trực tiếp “PBKDF2 200.000 vòng” với “Argon2id 3 vòng” hoặc “bcrypt cost 12”: chúng đo **các công việc khác nhau**. Chọn thuật toán và cấu hình theo mô hình đe dọa, tài nguyên máy chủ và hướng dẫn bảo mật hiện hành, rồi **đo trên phần cứng thực tế**.

### 1.1. Password hashing khác mã hóa có thể giải mã

Để **xác minh đăng nhập**, backend lưu một **verifier** được dẫn xuất từ mật khẩu, không lưu mật khẩu gốc hoặc bản mã có thể giải mã bằng khóa ứng dụng. Khi người dùng đăng nhập, backend lấy *salt và tham số đã lưu*, tính lại KDF cho mật khẩu vừa nhập và so sánh kết quả. Không cần biết mật khẩu gốc.

Để **dẫn xuất khóa mã hóa từ mật khẩu**, output có thể dùng làm vật liệu khóa cho AES hoặc cơ chế khác. Khi mật khẩu và các tham số được nhập lại đúng, KDF trả cùng byte khóa để mở dữ liệu. Trường hợp này phải quản lý thêm IV/nonce, authenticated encryption, thay mật khẩu, khôi phục dữ liệu và tính ổn định của tham số. Đừng tự suy diễn rằng cùng một output KDF được phép tái sử dụng đồng thời làm verifier, AES key và HMAC key: các mục đích cần **tách khóa hoặc tách miền dẫn xuất**.

### 1.2. Các thành phần cần lưu cùng kết quả

Trong hệ thống xác minh mật khẩu, một bản ghi tối thiểu thường gồm **định danh thuật toán**, **tham số chi phí**, **salt**, **độ dài đầu ra/khuôn dạng**, **digest đã dẫn xuất** và **phiên bản cấu hình**. Các trường không chứa plaintext password.

Ví dụ sơ đồ bản ghi (tên trường là mô tả cấu trúc, không phải chuỗi verifier đã được tính sẵn):

```text
CredentialRecord
  formatVersion      : 2
  algorithm          : PBKDF2WithHmacSHA256
  iterations         : 180000
  derivedKeyBits     : 256
  salt               : binary, 16 bytes (stored as Base64URL)
  verifier           : binary, 32 bytes (stored as Base64URL)
```

**180.000 vòng ở ví dụ này chỉ là tham số minh họa cho luồng nâng cấp, không phải khuyến nghị cấu hình production.** Trong hệ thống thật cần kiểm tra yêu cầu chính sách và benchmark ở thời điểm triển khai.

## 2. Salt: giá trị ngẫu nhiên riêng cho mỗi lần tạo verifier

**Salt** là dữ liệu đầu vào bổ sung cho KDF. Với một mật khẩu cụ thể, thay salt sẽ làm kết quả dẫn xuất khác nhau trong thực hành mật mã:

```text
KDF("example-password", salt_A, params) != KDF("example-password", salt_B, params)
```

Hai tài khoản dùng chung mật khẩu **không nên có cùng verifier**. Nếu chúng có salt độc lập đủ dài được sinh ngẫu nhiên, các kết quả KDF hầu như chắc chắn khác nhau. Điều này cản trở việc phát hiện mật khẩu trùng chỉ bằng cách so sánh hash và buộc kẻ tấn công thực hiện công việc đoán mật khẩu riêng cho từng salt, thay vì dùng kết quả tính sẵn cho một salt chung.

### 2.1. Tại sao phải có salt?

- **Chống bảng tra cứu tính trước:** rainbow table/lookup table cho hash không salt không áp dụng nguyên vẹn cho mọi salt độc lập.
- **Ngăn verifier trùng hàng loạt:** hai người cùng dùng mật khẩu sẽ có giá trị verifier khác nhau khi salt khác nhau.
- **Hạn chế chia sẻ chi phí tấn công giữa nhiều mục tiêu:** kẻ tấn công phải xét salt tương ứng của từng bản ghi.
- **Giữ tính kiểm chứng:** bản ghi chứa salt cho phép backend tính lại cùng KDF với mật khẩu nhập sau này.

Salt **không ngăn** kẻ tấn công đoán một mật khẩu cụ thể theo kiểu offline nếu đã lấy được verifier và salt. Salt cũng không tạo thêm entropy cho mật khẩu. Một mật khẩu yếu vẫn dễ bị đoán tương đối khi dùng KDF rẻ hoặc số lượt thử không bị giới hạn.

### 2.2. Salt phải ngẫu nhiên, độc lập, đủ dài

Với hệ thống mới, ví dụ thực hành dễ hiểu là **16 byte (128 bit) salt sinh bằng `SecureRandom`** cho mỗi verifier. Một số thuật toán/định dạng có yêu cầu riêng; phải làm theo đặc tả của thuật toán, thư viện hoặc định dạng lưu trữ đang sử dụng.

```java
byte[] salt = new byte[16];
new java.security.SecureRandom().nextBytes(salt);
```

Đây là đoạn minh họa, chưa phải chương trình độc lập. **Tạo salt mới khi tạo verifier mới**, kể cả khi hai người dùng chọn cùng một mật khẩu. Khi nâng cấp cấu hình bằng rehash sau đăng nhập, nên tạo **salt mới** cùng bản ghi mới.

Tránh dùng một salt toàn cục cho mọi tài khoản, dùng username/email làm salt, chỉ lấy timestamp hoặc bộ đếm dự đoán được để sinh salt, hoặc tạo salt từ một bộ sinh ngẫu nhiên không phù hợp như `Random`. Dữ liệu định danh có thể là một phần cấu trúc giao thức, nhưng **không thay thế salt ngẫu nhiên** khi hệ thống yêu cầu salt ngẫu nhiên.

Với salt ngẫu nhiên 128 bit, khả năng va chạm giữa hai salt độc lập rất nhỏ ở quy mô thông thường. Tuy nhiên yếu tố quyết định là **bộ sinh ngẫu nhiên mật mã và việc tạo riêng cho từng lần**, không chỉ độ dài mảng byte.

### 2.3. Salt có bí mật không?

**Không. Salt thường được lưu công khai bên cạnh verifier** trong cơ sở dữ liệu. Người xác minh cần đọc đúng salt để tái tạo output. Bảo mật dựa vào mật khẩu khó đoán và KDF có chi phí phù hợp, **không dựa vào việc giấu salt**.

- **Salt:** không bí mật, riêng từng bản ghi, dùng để tạo đầu ra khác nhau.
- **Pepper (nếu có):** bí mật dùng chung hoặc theo scope, được bảo quản ngoài DB, ví dụ KMS/HSM/secret manager. Pepper không thể thay salt; việc thêm và thay pepper cần thiết kế thuật toán/rotation riêng.
- **Nonce/IV:** có vai trò khác trong giao thức mã hóa, không tự đồng nghĩa với salt.
- **Secret key:** khóa cần giữ bí mật; không biến salt thành secret hoặc dùng salt như khóa AES/HMAC.

Nếu bản ghi bị sao chép sang môi trường khác mà thiếu salt, việc xác minh lại có thể **không thực hiện được**, vì output KDF phụ thuộc chính xác vào salt.

### 2.4. Salt khác nhau và salt bị thay đổi

Với cùng mật khẩu, cùng thuật toán và cùng số vòng:

```text
KDF(P, S1, 100000, 32 bytes) -> output_1
KDF(P, S2, 100000, 32 bytes) -> output_2
```

Kết quả `output_1` và `output_2` khác nhau vì `S1 != S2`. Nếu backend vô tình dùng salt mới mỗi lần người dùng *đăng nhập* thay vì dùng salt đã lưu, việc xác minh **sẽ thất bại**. Salt mới chỉ được tạo lúc tạo verifier mới hoặc rehash được kiểm soát.

Không coi một salt “dài 16 byte” là bằng chứng đủ an toàn: phải biết nó **được tạo bằng gì**, có bị reuse quy mô lớn không và có được lưu/đọc đúng byte hay không.

## 3. Số vòng lặp: điều chỉnh chi phí thử mật khẩu

Với PBKDF2, `iterationCount` là số vòng thực hiện chuỗi PRF bên trong thuật toán. Khi các yếu tố khác giữ nguyên, tăng số vòng lặp làm mỗi lần dẫn xuất tốn thêm CPU và thời gian. Điều này có ích vì kẻ tấn công offline thường cần thử rất nhiều giả thuyết mật khẩu.

Tuy nhiên, **chi phí cao tác động cả phía hợp lệ**: đăng nhập, reset mật khẩu, batch migration và mở khóa dữ liệu đều có thể tốn thêm CPU, gây nghẽn hoặc tạo điều kiện cho DoS nếu không giới hạn tốc độ.

### 3.1. Vì sao không dùng hash nhanh để lưu mật khẩu?

SHA-256 là hash nhanh, được thiết kế để xử lý dữ liệu hiệu quả. Nếu hệ thống lưu `SHA256(password)` hoặc chỉ `SHA256(salt || password)`, kẻ tấn công có thể thử nhiều mật khẩu rất nhanh khi có cơ sở dữ liệu verifier.

Password KDF thêm **chi phí tính toán có chủ đích**. Với PBKDF2, mỗi phép thử phải chạy số vòng đã cấu hình. Với Argon2id/scrypt, mục tiêu còn có thể bao gồm chi phí bộ nhớ, khiến tấn công song song trên GPU/ASIC khó tối ưu hơn.

**Thêm salt vào SHA-256 không thay thế PBKDF2/Argon2id/scrypt** trong vai trò password KDF có cấu hình chi phí phù hợp.

### 3.2. Chọn số vòng bằng chính sách và benchmark

Một cấu hình sản xuất cần quyết định theo các bước:

1. Chọn thuật toán KDF được hỗ trợ, được đánh giá phù hợp với threat model và các yêu cầu tương thích/compliance.
2. Đọc hướng dẫn bảo mật **còn hiệu lực tại thời điểm triển khai**. Số vòng “tốt” có thể thay đổi theo tốc độ phần cứng và thuật toán.
3. Đo **p50/p95/p99** thời gian của một phép xác minh trên phần cứng/instance thực tế, trong điều kiện có tải đồng thời.
4. Đặt ngân sách latency/CPU và bảo vệ trước brute force/DoS; cân nhắc quota, rate limit, MFA và giới hạn số request xác minh song song.
5. Ghi cấu hình đã phê duyệt vào version/policy, giám sát hiệu năng và có kế hoạch tăng chi phí trong các lần nâng cấp.

**Không dùng các giá trị demo 100.000 hoặc 180.000 vòng trong ví dụ Java dưới đây làm con số khuyến nghị production.** Chúng chỉ giúp thấy cơ chế giữ cấu hình cũ, xác minh và chuyển sang cấu hình mới.

### 3.3. Tăng số vòng tác động thế nào?

Nếu thời gian PBKDF2 với 100.000 vòng trên một máy là khoảng 50 ms, 200.000 vòng **thường** sẽ gần gấp đôi về phần công việc CPU của KDF trên cùng điều kiện. Đây là **quan hệ xu hướng**, không phải cam kết thời gian thực; provider, JVM, CPU, tải, cache và môi trường đều ảnh hưởng benchmark.

Kẻ tấn công vẫn có thể tối ưu phần cứng, chạy song song và đoán mật khẩu yếu. Số vòng **không tạo ra** một mật khẩu có entropy cao hơn. Vì vậy cần mật khẩu/passphrase đủ mạnh, xác thực đa yếu tố khi phù hợp và bảo vệ các điểm thử trực tuyến.

### 3.4. Argon2id và bcrypt không dùng cùng ý nghĩa “số vòng”

- **Argon2id:** tham số chi phí thường gồm bộ nhớ (ví dụ KiB), số pass/time cost và độ song song. Đánh giá theo **bộ ba này**, không nhìn riêng một chữ “iterations”. Argon2id có tham số phiên bản thuật toán riêng; cấu hình must include cả bộ tham số.
- **scrypt:** dùng các tham số `N`, `r` và `p` liên quan công việc và bộ nhớ; `N` không thể so sánh trực tiếp với vòng PBKDF2.
- **bcrypt:** cost factor quy định mức công việc tăng theo hàm mũ; nhích thêm 1 cost khác với tăng thêm 1 vòng PBKDF2. Bcrypt cũng có giới hạn/đặc thù xử lý độ dài password theo implementation, nên cần xét quy tắc encoding và cách xử lý chuỗi dài.

Không thiết kế một cấu hình tên `rounds=3` chung cho mọi KDF rồi kỳ vọng nó có ý nghĩa giống nhau. Khi migrate thuật toán, **đổi schema/tham số và algorithm ID tương ứng**.

## 4. Độ dài đầu ra: số byte kết quả, không phải độ mạnh mật khẩu

**Derived key length** nói về kích thước vật lý của kết quả KDF. Với `PBKDF2WithHmacSHA256`, có thể yêu cầu đầu ra với số bit cấu hình, ví dụ 128, 256 hoặc 512 bit nếu phù hợp sử dụng và provider hỗ trợ.

| Đầu ra | Nhị phân | Biểu diễn hex | Base64 chuẩn có padding |
| --- | ---: | ---: | ---: |
| 128 bit | 16 byte | 32 ký tự ASCII | 24 ký tự |
| 256 bit | 32 byte | 64 ký tự ASCII | 44 ký tự |
| 512 bit | 64 byte | 128 ký tự ASCII | 88 ký tự |

**Cảnh báo:** 256-bit output **không đồng nghĩa 256-bit password security**. Nếu password chỉ được đoán từ một tập nhỏ, attacker có thể chạy KDF cho các password đoán được. Tăng độ dài kết quả không làm tăng số khả năng của mật khẩu.

### 4.1. Kích thước kết quả theo mục đích

- **Password verifier:** chọn độ dài output theo thiết kế thuật toán/policy. Cần lưu đủ byte để so sánh, tránh tự truncate mà không có đặc tả.
- **Khóa AES-128:** cần 16 byte key; **AES-256** cần 32 byte key. Nhưng chỉ nên dùng output KDF trực tiếp làm khóa khi thiết kế KDF, salt, context và key lifecycle phù hợp.
- **Khóa HMAC:** key material và MAC output length là các đại lượng riêng; output 32 byte của KDF không mặc nhiên yêu cầu MAC cũng 32 byte trong mọi thuật toán.
- **HKDF sau password KDF:** một thiết kế có thể tạo một secret trung gian phù hợp rồi dẫn xuất các key theo mục đích bằng HKDF; cần xác định rõ domain, context và bảo vệ root/intermediate key. Không tái sử dụng thẳng một output cho nhiều chức năng.

Với PBKDF2 theo RFC, `dkLen` trong thuật toán là **byte**, giới hạn bởi số block của PRF. Với Java `PBEKeySpec`, `keyLength` là **bit**. Kiểm tra cả tên tham số **lẫn đơn vị** trước khi truyền giá trị cho API.

### 4.2. Byte, bit, hex, Base64 không phải một con số

Một verifier 32 byte có thể được lưu vào DB dưới dạng **64 ký tự hex** hoặc **44 ký tự Base64 chuẩn có padding**. Nếu dùng Base64URL không padding, 32 byte thường thành **43 ký tự ASCII**. Đây là overhead do encoding, **không thay đổi thuật toán KDF**.

Ví dụ:

```java
byte[] derived = /* output KDF, ví dụ 32 byte */;
String encoded = java.util.Base64.getUrlEncoder()
        .withoutPadding().encodeToString(derived);
```

Đoạn minh họa chưa là chương trình độc lập. **Không được biến byte digest tùy ý trực tiếp thành `new String(derived, UTF_8)`**, vì digest có thể chứa byte không biểu diễn được bằng UTF-8 hợp lệ.

### 4.3. Độ dài salt và độ dài output độc lập

Một cấu hình có **salt 16 byte + output 32 byte** là hoàn toàn bình thường. Không có quy tắc salt phải dài bằng hash, hoặc output phải bằng password string length. Với record minh họa:

- Salt: 16 byte random = 128 bit, thường Base64URL không padding dài 22 ký tự.
- Derived verifier: 32 byte = 256 bit, Base64URL không padding dài 43 ký tự.
- Iterations: một số nguyên chi phí, **không phải bit/byte**.
- Version: mã định danh chính sách, **không phải mức bảo mật**.

## 5. Phiên bản cấu hình: xác minh được dữ liệu cũ và nâng cấp được dữ liệu mới

Thông số KDF phải thay đổi theo thời gian khi phần cứng nhanh hơn, thuật toán mới được hỗ trợ, chính sách thay đổi hoặc có yêu cầu bảo mật mới. Nếu chỉ lưu mỗi hash mà **không lưu salt/thuật toán/chi phí/kích thước**, hệ thống có thể không biết phải tính lại như thế nào cho những tài khoản cũ.

**Configuration version** là một nhãn chính sách giúp quản lý lịch sử. Nó **không thay thế** việc lưu các thông số quan trọng của từng record.

Ví dụ phân biệt:

| Trường | Vai trò |
| --- | --- |
| `formatVersion` | Phiên bản schema/record hoặc chính sách ứng dụng, ví dụ v1/v2 |
| `algorithm` | Chính xác thuật toán/KDF dùng khi tạo record |
| `iterations` hoặc `timeCost/memoryCost/parallelism` | Chi phí thực tế của record |
| `derivedKeyBits` | Độ dài đầu ra đã dùng |
| `salt` | Byte salt thực tế của record |
| `hash/verifier` | Byte kết quả đã lưu để so sánh |
| `encoding` | Cách biểu diễn byte sang text, ví dụ Base64URL |
| `pepperKeyId` (nếu dùng) | Định danh key ngoài DB, không phải giá trị pepper bí mật |

### 5.1. Phân biệt ba kiểu “version”

1. **Application policy version:** do đội vận hành xác định, ví dụ `policy=2` khi tăng cost hoặc chuyển KDF. Các tên policy là dữ liệu nội bộ và phải được hiểu theo schema cụ thể.
2. **Record format version:** version của cách serialize/deserialize record; có thể đổi mà KDF không đổi (ví dụ chuyển từ hai cột DB sang chuỗi mã hóa chuẩn).
3. **Algorithm version:** phiên bản *bản thân thuật toán* trong một số họ (ví dụ Argon2 có tham số version). Nó khác với version do ứng dụng tự đặt.

Không dùng một trường `v=2` với ý nghĩa nhập nhằng “chắc chắn đã mạnh”. Một record mang v2 nhưng bị sửa iterations xuống 1 vẫn nguy hiểm nếu code không kiểm tra policy và giới hạn tham số.

### 5.2. Mẫu record giàu thông tin

Một representation có thể dùng cấu trúc:

```text
formatVersion | algorithm | iterations | outputBits | saltBase64Url | verifierBase64Url
```

Hoặc các cấu trúc chuẩn do thư viện password hashing cung cấp, ví dụ **PHC string format** khi thích hợp. Điều quan trọng là server hiểu rõ và validate từng trường. Không tự đặt một chuỗi dùng delimiter có thể lẫn dữ liệu chưa escape; trong môi trường thật cần parser chặt chẽ, giới hạn độ dài và trường hợp có version không hỗ trợ.

**Không lưu pepper trong record**, nếu có dùng nó. Pepper phải thuộc ranh giới secret manager/KMS và được chọn bằng key ID/phiên bản phù hợp.

### 5.3. Luồng đăng nhập với record cũ và nâng cấp

Giả sử server đang nhận record v1 và policy mới là v2:

1. **Đọc record cũ** và kiểm tra format/algorithm/parameter bounds từ allowlist. Không chấp nhận số vòng quá lớn hoặc cấu hình không được hỗ trợ dẫn đến tiêu tốn tài nguyên khi verify.
2. **Xác minh password** nhập bằng **salt và tham số của chính record v1**, không thay tất cả bằng policy v2 trước khi tính lại; làm vậy sẽ khiến mọi password cũ thất bại.
3. Nếu không khớp, **từ chối đăng nhập** và không nâng cấp record.
4. Nếu khớp, tạo **salt mới**, chạy **KDF theo chính sách hiện hành v2** với **password nhập đang có**, tạo verifier mới.
5. **Ghi lại record mới** bằng transaction hoặc cơ chế compare-and-swap dựa vào version/etag của record cũ để tránh ghi đè nâng cấp đồng thời hoặc thay đổi mật khẩu vừa xảy ra.
6. Xóa dữ liệu password tạm theo khả năng, kiểm tra policy kết quả và giữ audit metadata phù hợp.

Đây là **rehash on successful login**. Không thể “nâng vòng lặp” bằng cách chỉ hash lại verifier cũ rồi coi tương đương KDF của password gốc; nếu không có password gốc thì không thể tính lại cùng biểu thức KDF mới. Với tài khoản không đăng nhập lâu, có thể phải giữ hỗ trợ verify legacy trong thời gian xác định hoặc yêu cầu reset password theo chính sách.

### 5.4. Thay thuật toán hoặc tăng chi phí không được làm mất khả năng đăng nhập

Phương án kiểm soát migration:

- **Mọi đăng ký/đổi mật khẩu mới:** tạo record bằng current policy.
- **Đăng nhập thành công của account cũ:** verify bằng old parameters, rehash bằng current policy, cập nhật atomically.
- **Đăng nhập sai:** giữ record cũ, báo lỗi chung và áp rate limiting.
- **Record dùng thuật toán không còn chấp nhận hoặc vi phạm policy tối thiểu:** xử lý theo nhánh migration/reset được duyệt, không tự động cho phép thuật toán yếu mãi mãi.
- **Record không parse được:** fail closed; không thử mọi thuật toán/cấu hình một cách không giới hạn.
- **Thay password:** hash password mới với salt mới, current parameters, đánh dấu phiên bản mới.
- **Rollback ứng dụng:** chỉ thực hiện nếu phiên bản rollback có thể hiểu các record mới hoặc đã có kế hoạch tương thích; không âm thầm downgrade record về cấu hình yếu hơn.

## 6. Java 17+: tạo verifier, xác minh và rehash theo phiên bản

Ví dụ độc lập dưới đây dùng **PBKDF2WithHmacSHA256** có sẵn trong JCA/JCE để minh họa **đủ bốn tham số**. Chương trình tạo salt 16 byte bằng `SecureRandom`, dẫn xuất output 256 bit, lưu cấu hình với record, xác minh bằng thông số được lưu và nâng một record v1 lên v2 **sau khi password chính xác được xác nhận**.

Các giá trị **100.000 và 180.000 vòng chỉ dùng cho demo chạy nhanh và thấy được sự khác biệt phiên bản; không phải mức cấu hình triển khai**. Ở sản phẩm cần chọn password KDF và cost theo hướng dẫn hiện hành cùng benchmark riêng.

Lưu thành **PasswordPolicyDemo.java**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordPolicyDemo {
    static final String ALG = "PBKDF2WithHmacSHA256";
    static final int HASH_BITS = 256;
    static final int OLD_ROUNDS = 100_000;
    static final int CURRENT_ROUNDS = 180_000;
    static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    record Credential(int version, String algorithm, int iterations,
                      int bits, String saltBase64Url, String hashBase64Url) {}

    static byte[] pbkdf2(char[] password, byte[] salt,
                         int iterations, int bits)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, bits);
        try {
            return SecretKeyFactory.getInstance(ALG)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static Credential enroll(char[] password, int version, int iterations)
            throws GeneralSecurityException {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] hash = pbkdf2(password, salt, iterations, HASH_BITS);
        try {
            return new Credential(version, ALG, iterations, HASH_BITS,
                    ENCODER.encodeToString(salt),
                    ENCODER.encodeToString(hash));
        } finally {
            Arrays.fill(hash, (byte) 0);
        }
    }

    static boolean verify(char[] password, Credential stored)
            throws GeneralSecurityException {
        // Chính sách đọc record: từ chối thuật toán/tham số không hỗ trợ.
        if (!ALG.equals(stored.algorithm()) || stored.version() < 1
                || stored.version() > 2 || stored.iterations() < 10_000
                || stored.iterations() > 1_000_000
                || stored.bits() != HASH_BITS) {
            return false;
        }

        byte[] salt;
        byte[] expected;
        try {
            salt = DECODER.decode(stored.saltBase64Url());
            expected = DECODER.decode(stored.hashBase64Url());
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }
        if (salt.length != 16 || expected.length != HASH_BITS / 8) {
            return false;
        }

        byte[] actual = pbkdf2(password, salt,
                               stored.iterations(), stored.bits());
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    static boolean needsUpgrade(Credential c) {
        return c.version() < 2 || c.iterations() < CURRENT_ROUNDS;
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example-password-only".toCharArray();
        Credential old = enroll(password, 1, OLD_ROUNDS);
        Credential another = enroll(password, 1, OLD_ROUNDS);

        System.out.println("salt bytes: "
                + DECODER.decode(old.saltBase64Url()).length);
        System.out.println("derived bytes: "
                + DECODER.decode(old.hashBase64Url()).length);
        System.out.println("correct password: " + verify(password, old));
        System.out.println("wrong password: "
                + verify("wrong-password".toCharArray(), old));
        System.out.println("distinct salts: "
                + !old.saltBase64Url().equals(another.saltBase64Url()));
        System.out.println("distinct hashes: "
                + !old.hashBase64Url().equals(another.hashBase64Url()));

        Credential changedSalt = new Credential(
                old.version(), old.algorithm(), old.iterations(), old.bits(),
                another.saltBase64Url(), old.hashBase64Url());
        System.out.println("changed salt rejected: "
                + !verify(password, changedSalt));
        System.out.println("old needs upgrade: " + needsUpgrade(old));

        if (verify(password, old)) {
            Credential fresh = enroll(password, 2, CURRENT_ROUNDS);
            System.out.println("new verifies: " + verify(password, fresh));
            System.out.println("new needs upgrade: " + needsUpgrade(fresh));
        }
        Arrays.fill(password, (char) 0);
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac -encoding UTF-8 PasswordPolicyDemo.java
java PasswordPolicyDemo
```

Stdout kỳ vọng (đã kiểm tra hành vi KDF bằng Java; byte salt ngẫu nhiên không được in ra):

```text
salt bytes: 16
derived bytes: 32
correct password: true
wrong password: false
distinct salts: true
distinct hashes: true
changed salt rejected: true
old needs upgrade: true
new verifies: true
new needs upgrade: false
```

**Cách đọc code theo từng tham số:**

- **Salt:** `new SecureRandom().nextBytes(salt)` tạo salt 16 byte riêng khi `enroll()` chạy. Hai lần enroll cùng password có salt khác nhau và verifier khác nhau. Cả salt và verifier được encode Base64URL (không padding) để minh họa cách lưu text.
- **Số vòng:** `PBEKeySpec(..., iterations, bits)` truyền số vòng của từng record. `verify()` dùng lại `stored.iterations()`; rehash v2 dùng `CURRENT_ROUNDS`. Các ngưỡng kiểm tra trong `verify()` là giới hạn demo để không thực thi cấu hình không kiểm soát.
- **Độ dài output:** `HASH_BITS = 256` tương ứng output 32 byte; `HASH_BITS / 8` dùng để kiểm tra độ dài mảng hash sau khi decode.
- **Version:** `Credential` lưu `version` và `algorithm` cùng các tham số. `needsUpgrade()` so sánh với chính sách mới; bản ghi mới chỉ được tạo trong nhánh password đã được xác minh.
- **Giữ password:** `char[]` và `PBEKeySpec.clearPassword()` giảm một số tồn lưu không cần thiết, nhưng không bảo đảm toàn bộ password biến mất ngay khỏi JVM memory; input demo là chuỗi literal, tuyệt đối không áp dụng cách hardcode đó cho password thật.
- **So sánh:** `MessageDigest.isEqual(byte[], byte[])` dùng cho verifier byte array. Tránh chuyển output nhị phân thành chuỗi không rõ encoding; không log verifier hay password.
- **Quy tắc chống tấn công tài nguyên:** `verify()` giới hạn version, iteration, output size và salt length. Nếu xử lý record từ DB bị thao túng, phải áp **allowlist + giới hạn thực tế theo policy** trước khi gọi KDF để tránh DoS qua iterations cực lớn.
- **Lưu trữ:** ví dụ chỉ tạo các `record` trong memory; phần cập nhật **transaction/cas** của database không được giả làm đã triển khai. Trong ứng dụng thực, cần atomic update và bảo vệ trước thay đổi mật khẩu/rehash đồng thời.

Các mệnh đề “distinct salts/hashes” có tính xác suất rất cao khi nguồn ngẫu nhiên hoạt động đúng; việc hai salt 128 bit ngẫu nhiên tình cờ trùng nhau là cực kỳ hiếm, không phải bất khả thi về mặt toán học.

### 6.1. Cấu hình minh họa khác gì cấu hình production?

Chương trình nhằm làm rõ luồng dữ liệu nên cố ý giản lược:

- Demo chỉ có **hai version**, cùng một thuật toán PBKDF2; sản phẩm có thể cần **registry** cho nhiều thuật toán, key ID pepper và nhiều phiên bản cùng tồn tại.
- Demo mã hóa record thành các trường Java, chưa cung cấp parser DB hoặc giao thức serialized chống sửa đổi metadata; trong triển khai thật, ràng buộc schema và quyền sửa DB rất quan trọng.
- Demo so sánh password đúng/sai trong bộ nhớ, không có bảo vệ login endpoint (rate limiting, MFA, logging an toàn, abuse detection).
- Demo hiển thị số vòng để giải thích, không benchmarking và không cam kết một thời gian chạy cụ thể trên JVM khác.
- Demo không bàn giao output KDF làm khóa mã hóa; khi dùng KDF cho encryption cần thiết kế key lifecycle và bảo vệ data tương ứng.

## 7. Cách triển khai phiên bản và nâng cấp không làm mất dữ liệu

### 7.1. Mỗi record tự mô tả cấu hình đã tạo ra nó

Một credential lưu bằng PBKDF2 với 100.000 vòng và salt 16 byte phải **được xác minh bằng đúng thông số đó**; dù ứng dụng đã nâng policy lên 180.000 vòng, bạn không thể tự ý bỏ qua metadata cũ.

Tránh thiết kế chỉ có các biến global hiện hành:

```text
CURRENT_ROUNDS = 180000
verify(oldCredential, password) = PBKDF2(password, oldSalt, CURRENT_ROUNDS)
```

Dạng này sẽ **làm sai kết quả** với record v1. Thay vào đó, chọn thuật toán và chi phí lưu trong record sau khi parser đã validate, verify trước, rồi rehash với current policy.

### 7.2. Nâng cấp tại thời điểm xác thực thành công

Một quy trình triển khai rõ ràng:

```text
READ credential record
    -> VALIDATE supported schema, alg, cost and length limits
    -> VERIFY using stored parameters
       -> mismatch: reject, do not modify credential
       -> match:
          -> if current policy satisfied: sign in
          -> else: generate NEW salt + current parameters
                   derive NEW verifier from entered password
                   persist atomically (version/CAS condition)
                   sign in
```

Khi current policy mới dùng **Argon2id** nhưng record cũ là **PBKDF2**, verifier cũ vẫn dùng PBKDF2 để verify; sau khi thành công có thể chuyển sang Argon2id qua thư viện được phê duyệt. Không tự chọn thuật toán mới dựa trên `hash.length` hoặc chuỗi tự đặt.

### 7.3. Điều chỉnh tham số phải xét hiệu năng và abuse

Các rủi ro vận hành:

- Một lượng lớn account nâng cấp đồng thời có thể tăng CPU/memory usage; cần capacity planning.
- Nếu attacker có thể làm server xử lý một record với `iterations` cực lớn hoặc `memoryCost` quá mức, endpoint login dễ bị DoS. Validate bounds trước khi gọi KDF.
- Nếu tăng cost nhưng không giới hạn retry, attacker vẫn gây tải lớn cho dịch vụ xác minh.
- Nếu cho phép “downgrade” dễ dàng qua client header hoặc record do user sửa, một số luồng có thể tiếp tục dùng policy yếu vô hạn.
- Nếu thay đổi chuẩn hóa/encoding Unicode của password mà không version hóa, cùng chuỗi hiển thị có thể tạo byte đầu vào khác; người dùng hợp lệ bị từ chối.

## 8. Encoding password, Unicode và interoperability

Salt và verifier là byte array. Nhưng người dùng nhập **ký tự**; khi đưa password sang KDF, phải có cách chuyển ký tự thành byte rõ ràng theo thuật toán/provider.

- Với `PBEKeySpec`, input là `char[]` của Java (các đơn vị mã UTF-16); provider KDF xử lý theo định nghĩa thuật toán/provider. Khi cần **tương thích giữa Java và ngôn ngữ khác**, phải kiểm tra quy tắc encoding cụ thể bằng test vector và ghi cùng version; không tự giả định tất cả thư viện có cùng biến đổi Unicode.
- Một số hệ thống chuẩn hóa Unicode (ví dụ NFC) trước KDF; một số không chuẩn hóa. Đây là quyết định tương thích và bảo mật phải giữ ổn định cho record cũ. **Không tự thêm bước normalize ở phiên bản mới mà không có migration**.
- Không dùng `String.length()` để đo số byte UTF-8 của password; khi cần byte length, chuyển encoding đúng rồi đếm. Với bcrypt, chú ý giới hạn byte đầu vào theo implementation, đặc biệt với Unicode.
- Tốt hơn nên có test vector cho password chứa dấu tiếng Việt, ký tự ngoài BMP, salt và tham số biết trước để kiểm chứng toàn bộ hệ thống client/server/server mới.

Bảo vệ input password trên đường truyền bằng TLS, không đưa password vào URL, log, analytics, exception hoặc crash report. Ở mức ứng dụng, đừng trim hay đổi chữ hoa/thường của password theo ý thích: thay đổi này có thể ảnh hưởng tính đúng đắn và làm giảm không gian mật khẩu.

## 9. Salt, số vòng và version trong dẫn xuất khóa mã hóa

Nếu một password KDF tạo **khóa AES để mở dữ liệu**, các tham số có tác dụng tương tự nhưng hậu quả nâng cấp khác password verifier:

- Đổi salt, iterations, KDF hoặc output length sẽ **tạo khóa byte khác**, nên dữ liệu mã hóa cũ có thể không giải mã được.
- Phải lưu metadata KDF cùng envelope dữ liệu mã hóa, hoặc có hệ thống quản lý key version và salt đúng với từng payload.
- Khi muốn nâng cấu hình, thường cần lấy lại mật khẩu, dẫn xuất khóa cũ, **giải mã an toàn**, rồi mã hóa lại bằng khóa mới; hoặc dùng mô hình **key-encryption key / data-encryption key** để hỗ trợ rewrap theo thiết kế.
- Nếu vừa dùng cùng password cho verifier và mã hóa, không được sử dụng **cùng derived bytes** trực tiếp cho hai mục đích. Có thể thiết kế tách KDF purpose/context rõ ràng hoặc một bước HKDF dẫn xuất subkey có scope khác nhau sau khi tạo vật liệu thích hợp.
- Lựa chọn output 32 byte cho AES-256 **không chứng minh khóa có entropy 256 bit** nếu password yếu. Sự an toàn còn phụ thuộc việc attacker có offline oracle để kiểm tra password không.
- Quản lý **nonce/IV** của thuật toán mã hóa riêng biệt với salt của KDF. Với AES-GCM chẳng hạn, nonce cần duy nhất với cùng AES key; nó không được thay thế bằng “một salt bất kỳ” rồi bỏ qua quy tắc nonce.

Đối với password verifier, rehash sau đăng nhập thành công đơn giản hơn vì server chỉ cần lưu verifier mới. Đối với encryption, phải bảo đảm **khôi phục được dữ liệu cũ** trước khi thay khóa hoặc khóa bọc.

## 10. Các lỗi thường gặp và hậu quả

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một salt cho tất cả tài khoản | Cùng password tạo cùng verifier, tấn công đa mục tiêu dễ hơn | Sinh salt ngẫu nhiên riêng khi tạo mỗi record |
| Coi salt là secret key | Thiết kế sai ranh giới và không bảo vệ password phù hợp | Salt công khai; nếu có pepper, quản lý bí mật riêng |
| Salt tạo từ email, username hoặc timestamp | Dễ đoán, dễ lặp hoặc quá ít entropy | Dùng CSPRNG với độ dài theo KDF/policy |
| Tăng output 256 → 512 bit để “tăng entropy password” | Không cải thiện độ khó đoán password yếu | Dùng password/passphrase tốt và chi phí KDF hợp lý |
| Dùng SHA-256 nhanh trực tiếp | Dễ thử nhiều candidate offline | Chọn password KDF có cost phù hợp |
| Truyền `32` vào `PBEKeySpec` khi muốn 32 byte | Chọn nhầm 32 bit output | Truyền **256 bit**, kiểm tra byte length |
| Tăng PBKDF2 iteration chỉ dựa trên phỏng đoán | Có thể quá yếu hoặc gây chậm/DoS | Benchmark, policy, giới hạn concurrency và rate limiting |
| Đem cùng số iterations dùng cho Argon2id/bcrypt | Chi phí thuật toán hoàn toàn khác | Dùng bộ tham số đúng của từng KDF |
| Chỉ lưu digest, không lưu salt/chi phí/alg | Không xác minh/migrate được record cũ | Lưu self-describing format và policy version |
| Verify record cũ bằng parameters hiện hành | Người dùng đúng password vẫn bị từ chối | Verify bằng stored config, rehash sau khi pass |
| Chỉ sửa số vòng trong DB, giữ nguyên verifier | Verifier không khớp với password | Rehash lại với **password đúng** và salt mới |
| Cho record tự khai cost không giới hạn | DoS thông qua yêu cầu KDF quá nặng | Allowlist và giới hạn tham số trước khi thực thi |
| Truncate/encode digest tùy tiện | Verifier không khớp hoặc bị rút ngắn ngoài policy | Lưu chính xác output bytes và encoding |
| Bỏ qua Unicode normalization/version | Password hợp lệ có thể ngừng hoạt động | Giữ cùng quy tắc encoding theo version và test vector |
| Dùng cùng output KDF làm verifier/AES/HMAC key | Cross-purpose key reuse | Tách vật liệu khóa/context/purpose rõ ràng |
| Ghi plaintext password hoặc pepper trong DB/log | Rò rỉ thông tin xác thực/secret | Chỉ lưu verifier, salt và metadata; pepper bảo quản riêng |
| In toàn bộ verifier để debug | Tăng nguy cơ lộ dữ liệu hỗ trợ tấn công offline | Log metadata không nhạy cảm và correlation ID, hạn chế truy cập DB |

## 11. Checklist kiểm tra một cấu hình password KDF

1. **Thuật toán:** đã chọn KDF phù hợp với mục đích password hashing/password-based key derivation và điều kiện sử dụng chưa?
2. **Salt:** có **salt ngẫu nhiên độc lập** cho mỗi record, đủ dài và lưu đúng byte, không lẫn với pepper/nonce không?
3. **Chi phí:** PBKDF2 iterations hoặc Argon2id memory/time/parallelism được đo trên phần cứng triển khai và cập nhật theo policy chưa?
4. **Output:** hiểu rõ bit hay byte theo API; verifier có độ dài và encoding đúng không?
5. **Version:** record lưu alg, params, salt, output, format/policy version; parser có allowlist, bounds và xử lý version không hỗ trợ không?
6. **Verification:** dùng đúng thông số record cũ, so sánh byte an toàn, có rate limiting và tránh leak dữ liệu qua error/log không?
7. **Migration:** sau đăng nhập đúng có rehash theo current policy với salt mới và cập nhật atomically không? Account ít đăng nhập có kế hoạch migration/reset không?
8. **Encoding:** password Unicode được xử lý nhất quán giữa JVM/provider, phiên bản sản phẩm và các client không?
9. **Secret/pepper:** nếu có pepper, nó được quản lý ngoài DB và có quy trình rotation/recovery không?
10. **Ứng dụng crypto:** nếu output thành khóa mã hóa, đã thiết kế restore/rewrap/re-encrypt, key separation và IV/nonce độc lập chưa?

## 12. Câu hỏi tình huống để tự kiểm tra

**Câu 1.** Alice và Bob đều chọn cùng password; hệ thống dùng PBKDF2 với salt 16 byte sinh độc lập. Hai verifier có nhất thiết giống nhau không?  
**Trả lời:** **Không**. Salt khác nhau nên output KDF hầu như chắc chắn khác, dù password và parameters giống nhau.

**Câu 2.** Salt bị lộ nhưng password chưa lộ. Hệ thống có lập tức mất toàn bộ tính bảo mật không?  
**Trả lời:** Không chỉ vì salt lộ, vì salt vốn không cần giữ bí mật. Nhưng nếu attacker có cả verifier và salt, họ có thể thử password offline; độ mạnh password và KDF vẫn rất quan trọng.

**Câu 3.** Một policy mới tăng PBKDF2 iterations từ cũ lên mức mới. Khi kiểm tra login cho record cũ, dùng số nào?  
**Trả lời:** Dùng **iterations lưu trong record cũ** để verify, rồi sau khi password khớp, rehash bằng số vòng **policy mới** và salt mới.

**Câu 4.** `PBEKeySpec` cần đầu ra 32 byte. `keyLength` là bao nhiêu?  
**Trả lời:** **256**, vì Java nhận độ dài theo bit. `byte[].length` của output dự kiến là **32**.

**Câu 5.** Đổi output từ 32 byte sang 64 byte làm mật khẩu “password123” mạnh gấp đôi không?  
**Trả lời:** **Không**. Output dài hơn không làm mật khẩu dễ đoán tăng entropy. Chi phí thử và chất lượng password cần đánh giá riêng.

**Câu 6.** Người dùng có verifier v1 nhưng database bị đổi `iterations=999999999`. Backend có nên chạy KDF theo đó?  
**Trả lời:** **Không**. Phải validate version/algorithm và giới hạn cost trước khi thực thi; dữ liệu bất hợp lệ nên bị từ chối và xử lý theo chính sách.

**Câu 7.** Cùng password, salt và KDF parameters, nhưng hai implementation dùng quy tắc Unicode encoding khác nhau. Verifier có bảo đảm khớp không?  
**Trả lời:** **Không**. Cần ghi rõ cách chuyển password thành input, test vector liên nền tảng và version hóa thay đổi này.

**Câu 8.** Bản ghi chứa output 32 byte, salt 16 byte và tên thuật toán nhưng không lưu iteration count. Có đủ để xác minh nhiều version theo cách xác định không?  
**Trả lời:** **Không đủ** nếu các version dùng số vòng khác nhau. Phải có iteration count hoặc ánh xạ version → tham số tuyệt đối rõ ràng, không nhập nhằng, lâu dài.

**Câu 9.** Đổi password người dùng và salt nhưng giữ nguyên dữ liệu được mã hóa bằng khóa dẫn xuất từ password cũ. Dữ liệu có tự mở bằng khóa mới không?  
**Trả lời:** **Không**. Phải thiết kế giải mã/mã hóa lại hoặc key wrapping/rewrap theo kiến trúc quản lý khóa và phiên bản.

### Điều cần nhớ

**Salt** bảo đảm tính riêng biệt giữa các bản ghi; **iteration/cost** làm mỗi phép thử password tốn tài nguyên hơn; **output length** xác định kích thước byte kết quả; **configuration version** giữ được khả năng xác minh, nâng cấp và tương thích. Một password KDF được vận hành an toàn cần đủ cả bốn, cộng với mật khẩu đủ mạnh, giới hạn thử đăng nhập, xử lý Unicode nhất quán và quản lý vòng đời cấu hình rõ ràng.

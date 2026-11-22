# SCryptPasswordEncoder, Argon2PasswordEncoder và chi phí bộ nhớ

> **Ngữ cảnh:** Spring Security — Authentication → **Băm mật khẩu**. Bài học làm rõ cách `SCryptPasswordEncoder` và `Argon2PasswordEncoder` tạo/kiểm tra mật khẩu theo các thuật toán *memory-hard*, ý nghĩa của tham số chi phí, cách ước lượng **bộ nhớ cho mỗi phép kiểm và nhiều yêu cầu đồng thời**, lựa chọn tham số theo tài nguyên thực tế và cách triển khai/migrating an toàn với Spring Security. Ví dụ độc lập dùng Java 17, Spring Security 6.5.11 và Bouncy Castle 1.86.

## 1. Kết quả học tập

Sau bài này, bạn sẽ làm được các việc sau:

1. Giải thích tại sao không lưu mật khẩu bản rõ, không dùng SHA-256 đơn lẻ cho mật khẩu và không coi hash là mã hóa có thể giải mã.
2. Phân biệt `encode(rawPassword)`, `matches(rawPassword, encodedPassword)`, salt ngẫu nhiên, tham số work factor và `upgradeEncoding(...)` của `PasswordEncoder`.
3. Hiểu scrypt với `N`, `r`, `p`, `dkLen` và `saltLength`; ước lượng bộ nhớ lõi bằng `128 × N × r` byte.
4. Hiểu Argon2id với `m` (KiB), `t` (iterations), `p` (parallelism), kích thước salt/hash; biết `m` là bộ nhớ **tổng** của một phép băm, không tự nhân `m` với `p`.
5. Phân biệt **memory-hardness của thuật toán** với **heap/RSS thật của JVM**, ảnh hưởng của đồng thời, GC, container limit và giới hạn tốc độ đăng nhập.
6. Chạy một chương trình Java 17 để kiểm thành công/thất bại với cả hai encoder, dùng `DelegatingPasswordEncoder` để phân biệt format và đọc kết quả tính bộ nhớ.
7. Thiết kế chiến lược benchmark, quản lý thread/concurrency, chống DoS và nâng tham số/thuật toán cho hệ thống đang hoạt động.

## 2. Vì sao cần hàm băm mật khẩu thích ứng và tốn bộ nhớ?

Giả sử database lưu mật khẩu. Nếu lưu bản rõ, khi mất database kẻ tấn công biết ngay mật khẩu. Nếu dùng một phép hash nhanh như `SHA-256(password)`, attacker có thể thử lượng lớn mật khẩu mỗi giây với GPU/ASIC. Thêm salt ngẫu nhiên giúp chống việc nhiều user có cùng hash hay tra cứu từ bảng chuẩn bị trước, **nhưng một hàm hash quá nhanh vẫn không đủ chống đoán offline**.

Một password hashing function phù hợp cần:

- **Một chiều:** đầu ra không thể “giải mã” để lấy mật khẩu ban đầu theo thiết kế.
- **Salt ngẫu nhiên cho mỗi bản ghi:** hai lần `encode("same-password")` thường khác nhau; salt không cần giữ bí mật nhưng phải được lưu cùng encoded hash hoặc bằng format tương thích.
- **Work factor thích ứng:** phép `matches` đủ tốn tài nguyên để làm chậm đoán mật khẩu offline, đồng thời vẫn dùng được với lưu lượng chính đáng.
- **Memory hardness (đối với scrypt/Argon2):** một phép thử cần lượng bộ nhớ đáng kể, gây bất lợi cho phần cứng có mật độ phép thử cao.
- **Format và version ổn định:** cần biết thuật toán/tham số của hash cũ để vẫn kiểm được khi nâng cấp.

**Scrypt** được thiết kế để khiến việc tính hash hàng loạt phải sử dụng lượng RAM đáng kể. **Argon2** là họ thuật toán thắng cuộc Password Hashing Competition; biến thể **Argon2id** phối hợp các đặc điểm của Argon2i/Argon2d và là hướng chọn phổ biến cho password hashing. Spring Security cung cấp encoder cho cả scrypt và Argon2.

Điểm dễ nhầm: một password hash chứa salt và tham số **không phải access token**, **không phải encryption key** và **không phải bằng chứng người dùng đã đăng nhập**. Nó chỉ là dữ liệu dùng để kiểm mật khẩu khi một lần xác thực thực sự diễn ra.

## 3. Hợp đồng PasswordEncoder trong Spring Security

Các phương thức chính:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **chữ ký khái quát** giúp học API; mã nguồn thư viện có thể thêm kiểm tra null và triển khai cụ thể. Các encoder cung cấp format lưu trữ riêng và đều hiện thực hợp đồng chính.

| API | Input | Điều thực hiện | Điều không thực hiện |
| --- | --- | --- | --- |
| `encode(...)` | Mật khẩu thô từ luồng đăng ký/reset đáng tin | Tạo hash thích ứng có salt/tham số | Không tạo `Authentication` hoặc tự lưu DB |
| `matches(...)` | Mật khẩu người dùng vừa nhập và hash được lưu | Tính/đối chiếu theo metadata hash | Không kiểm user locked, enabled, role, MFA |
| `upgradeEncoding(...)` | Hash đang lưu | Cho biết có thể cần tạo lại hash theo chính sách encoder | Không tự thay đổi bản ghi DB |
| `PasswordEncoderFactories.createDelegatingPasswordEncoder()` | Không cần input | Tạo encoder đa định dạng với thuật toán encode mặc định theo framework | Không có nghĩa mặc định mọi password mới đều là scrypt/Argon2 |

Ví dụ đúng về kiểm:

~~~java
String stored = passwordEncoder.encode("example-secret");
boolean accepted = passwordEncoder.matches("example-secret", stored);
~~~

**Không so sánh `encode(input).equals(stored)`:** hai lần encode thường tạo salt khác nhau nên không có cùng chuỗi hash. Thay vì so sánh hai hash mới, `matches` đọc salt và tham số từ hash cũ rồi tính để xác minh.

**Không tạo custom `PasswordEncoder` trả true luôn** cho user đã tìm thấy trong cache. Tầng cache account và việc kiểm password là hai trách nhiệm khác nhau.

## 4. SCryptPasswordEncoder: N, r, p và ước lượng bộ nhớ

### 4.1. Tạo encoder bằng preset chính thức

~~~java
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

SCryptPasswordEncoder encoder =
        SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Theo Javadoc Spring Security 6.5, preset `defaultsForSpringSecurity_v5_8()` có:

| Tham số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `cpuCost`, ký hiệu scrypt `N` | `65_536` = `2^16` | Tham số chi phí CPU/bộ nhớ; phải là lũy thừa của 2 hợp lệ |
| `memoryCost`, ký hiệu `r` | `8` | Tham số block size của scrypt; **không phải trực tiếp là 8 MiB** |
| `parallelization`, ký hiệu `p` | `1` | Tham số song song/số luồng trộn theo định nghĩa thuật toán |
| `keyLength` / `dkLen` | `32` byte | Chiều dài khóa/hash đầu ra |
| `saltLength` | `16` byte | Độ dài salt ngẫu nhiên |

Tên `cpuCost` và `memoryCost` là tên **tham số constructor của Spring**, trong khi tên chuẩn thuật toán thường là `N` và `r`. Đừng hiểu `memoryCost=8` là chỉ cấp 8 MB. Bộ nhớ chính cần được tính từ `N` và `r`.

Khởi tạo tường minh có cùng thông số:

~~~java
SCryptPasswordEncoder scrypt =
        new SCryptPasswordEncoder(
                1 << 16, // N
                8,       // r
                1,       // p
                32,      // dkLen
                16);     // saltLength (bytes)
~~~

Khi chỉnh tham số, ưu tiên kiểm cả giới hạn hợp lệ của implementation và thời gian/bộ nhớ thực trên môi trường chạy. Không chọn `N` tùy ý không phải lũy thừa 2; cũng không tự suy ra tăng `p` sẽ làm tăng tuyến tính độ an toàn trong mọi cấu hình.

### 4.2. Công thức ước lượng bộ nhớ lõi

Với scrypt, ước tính cho bảng nhớ lớn trong thuật toán:

\[
M_{\text{scrypt,base}} \approx 128 \times N \times r\quad\text{byte}
\]

Thay preset:

\[
128 \times 65\,536 \times 8
= 67\,108\,864\ \text{byte}
= 64\ \text{MiB}.
\]

**64 MiB là ước tính kích thước bộ nhớ chính của scrypt cho một phép tính**, không phải cam kết JVM heap tăng đúng 64 MiB, không phải giá trị RSS đo thực tế và cũng không bao gồm mọi buffer/cấu trúc/phụ phí của thư viện.

Các tham số liên quan:
- Tăng `N` thường làm tăng CPU và bộ nhớ lõi.
- Tăng `r` làm tăng bộ nhớ lõi và chi phí tính toán.
- Tăng `p` ảnh hưởng số khối/tải tính toán và có thể có tác động bộ nhớ bổ sung, nhưng không được dùng công thức sai `128 × N × r × p` như một khẳng định về chính bảng nhớ lớn của mọi implementation.
- `dkLen` là độ dài đầu ra (32 byte trong preset), **không** phải lượng RAM cho phép tính.

### 4.3. Ví dụ các mức scrypt để hiểu tỷ lệ

Giữ `r=8` và `p=1`:

| N | `128 × N × r` | Kích thước ước tính |
| ---: | ---: | ---: |
| `2^14` = 16.384 | 16.777.216 byte | 16 MiB |
| `2^15` = 32.768 | 33.554.432 byte | 32 MiB |
| `2^16` = 65.536 | 67.108.864 byte | 64 MiB |
| `2^17` = 131.072 | 134.217.728 byte | 128 MiB |

Đây là **phép tính lý thuyết**, không phải benchmark latency hoặc tiêu chuẩn tham số tối thiểu cho mọi máy. Tăng `N` gấp đôi tăng xấp xỉ gấp đôi bảng nhớ chính, nhưng thời gian đo được còn phụ thuộc kiến trúc CPU, bandwidth RAM, phiên bản Bouncy Castle/Spring Security, GC và đồng thời.

## 5. Argon2PasswordEncoder: memory, iterations, parallelism

### 5.1. Preset Spring Security

~~~java
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;

Argon2PasswordEncoder encoder =
        Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Theo Javadoc Spring Security 6.5, preset này khởi tạo:

~~~java
Argon2PasswordEncoder argon2 =
        new Argon2PasswordEncoder(
                16,       // saltLength (bytes)
                32,       // hashLength (bytes)
                1,        // parallelism (p)
                1 << 14,  // memory (KiB)
                2);       // iterations (t)
~~~

| Tham số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `saltLength` | 16 byte | Độ dài salt ngẫu nhiên |
| `hashLength` | 32 byte | Độ dài hash |
| `parallelism` = `p` | 1 | Số lane theo thuật toán |
| `memory` = `m` | 16.384 KiB | Tổng mức bộ nhớ cấu hình cho một phép Argon2 |
| `iterations` = `t` | 2 | Số pass/lượt xử lý theo thuật toán |

**Đổi đơn vị đúng:** `16_384 KiB / 1_024 = 16 MiB`. Trong Java constructor này, `memory` không phải “16.384 byte”, và cũng không phải “16.384 MiB”. Sai đơn vị có thể dẫn tới cấu hình quá nhẹ hoặc làm quá tải memory.

### 5.2. Tham số nào tác động điều gì?

- **`memory`/`m`:** đặt ngân sách bộ nhớ thuật toán theo KiB. Tăng `m` làm attacker tốn tài nguyên bộ nhớ hơn, nhưng ứng dụng cũng phải đủ RAM.
- **`iterations`/`t`:** tăng số lượt tính toán. Thường làm latency lớn hơn mà không đơn giản nhân bộ nhớ lớn nhất với `t`; `t` là số pass, không phải “t bản sao RAM”.
- **`parallelism`/`p`:** mô tả số lane; **`m` là tổng bộ nhớ**, không phải mỗi lane dùng riêng `m` KiB. Một số runtime tối ưu đa luồng, nhưng Spring Security implementation dựa trên Bouncy Castle hiện có ghi chú **không khai thác parallelism/optimizations theo cách attacker có thể khai thác**.
- **`saltLength` và `hashLength`:** cấu hình kích thước của salt/hash, không thay thế work factor.

Một dấu hiệu tốt của encoded hash Argon2id là format chứa thông số thuật toán như `m`, `t`, `p` cùng salt và hash theo format tương thích. **Không tự tự chế chuỗi hoặc chỉnh tham số nằm trong encoded hash**; `matches` cần đúng format do implementation phát hành và salt gốc.

### 5.3. Hiểu đúng việc tính bộ nhớ

Mức mặc định Argon2 ở trên là **16 MiB cho một phép theo tham số m**. Khi `p` lớn hơn 1, không suy ra cơ sở memory thành `m × p`; memory được chia thành lane theo thuật toán. Tuy nhiên **số yêu cầu xác thực đồng thời** là số phép độc lập và **có thể** khiến nhu cầu RAM tăng gần tuyến tính theo số phép hash đang chạy.

Ví dụ 8 request cùng verify:
- Scrypt với bảng nhớ chính 64 MiB/request → khoảng **512 MiB** trước overhead.
- Argon2 với `m=16 MiB`/request → khoảng **128 MiB** trước overhead.

Đây không phải bảo đảm rằng Argon2 luôn ít RAM hơn hoặc an toàn hơn scrypt trong mọi cấu hình: **hai preset của framework có tham số khác nhau**. Muốn đánh giá thuật toán cần so trên cùng phần cứng, ngưỡng latency, mô hình đe dọa và ngân sách tài nguyên hợp lệ.

## 6. SCrypt và Argon2: so sánh theo câu hỏi thực tế

| Tiêu chí | SCryptPasswordEncoder | Argon2PasswordEncoder |
| --- | --- | --- |
| Thuật toán | scrypt | Argon2 (thường định dạng Argon2id) |
| Preset v5_8 | `N=65536,r=8,p=1` | `m=16384 KiB,t=2,p=1` |
| Bộ nhớ nền theo preset | ≈64 MiB | 16 MiB |
| Điều chỉnh chi phí | `N`, `r`, `p` | `m`, `t`, `p` |
| Độ dài salt/hash preset | Salt 16 B, derived key 32 B | Salt 16 B, hash 32 B |
| Đặc điểm JVM | Bảng nhớ và buffer lớn, chịu tác động GC/heap | Bouncy Castle, cần dependency, có lưu ý về tối ưu song song |
| Kết quả lưu | Hash chứa metadata/salt theo format scrypt của Spring | Hash chứa metadata/salt của Argon2 |
| API chung | `encode`, `matches`, `upgradeEncoding` | `encode`, `matches`, `upgradeEncoding` |
| Dùng với DelegatingPasswordEncoder | Có | Có |
| Có tự làm tài khoản authenticated? | Không | Không |

### Khi nên chọn thuật toán nào?

Không có đáp án “luôn chọn vì một phép có nhiều MiB hơn”. Hãy đánh giá:

1. **Chính sách bảo mật/tuân thủ:** thuật toán được tổ chức chấp thuận, thư viện còn được hỗ trợ và có bản vá.
2. **Mô hình tấn công:** chống đoán mật khẩu offline khi hash bị lộ; salt ngẫu nhiên, rate limiting và password policy vẫn cần.
3. **Ngân sách server:** memory/concurrency, container quotas, thời gian chờ login, khả năng mở rộng node.
4. **Implementation thực tế:** Argon2 trên Bouncy Castle có đặc điểm tối ưu khác thư viện native; benchmark trên môi trường sẽ vận hành.
5. **Khả năng migrate:** database có hash từ bcrypt/scrypt/Argon2/PBKDF2 trước đây và cần xác minh trong giai đoạn chuyển đổi.
6. **Vòng đời sản phẩm:** chính sách tăng cost factor qua nhiều năm và đường đổi hash khi user đăng nhập thành công.

Spring Security đưa ra các preset **điểm xuất phát**, không thay thế việc benchmark. Tài liệu password storage khuyến nghị điều chỉnh độ nặng cho một lần verification vào khoảng **1 giây** trên máy mục tiêu như một hướng dẫn tham khảo; đây **không phải SLA bắt buộc**. Một dịch vụ lưu lượng lớn hoặc có giới hạn bộ nhớ nghiêm ngặt phải cân bằng thêm concurrency và UX.

## 7. Bộ nhớ theo request đồng thời: điểm nhiều ứng dụng bỏ sót

### 7.1. Từ một hash đến nhiều login đồng thời

Giả sử mỗi verify scrypt dùng ước tính 64 MiB vùng làm việc lớn. Nếu 8 verification cùng đang ở đoạn dùng nhiều bộ nhớ, chỉ riêng phần bảng nhớ có thể tới khoảng:

\[
8 \times 64\ \text{MiB} = 512\ \text{MiB}.
\]

Nếu 32 request cùng verify thì ước tính lên đến **2 GiB**, chưa tính heap của các đối tượng ứng dụng, thread stack, HTTP buffers, JVM code cache, off-heap/direct buffers, cache người dùng và các thư viện khác.

Với Argon2 `m=16 MiB` và 32 request đồng thời, phần work memory thuật toán xấp xỉ **512 MiB**. Hệ thống không có nghĩa có thể chạy 4 lần nhiều login hơn theo thông số này; latency, CPU, bandwidth RAM và mức tối ưu khác nhau còn ảnh hưởng throughput.

### 7.2. Bảng ước lượng nhanh (không phải số đo thực)

| Số phép hash đang chạy | Scrypt v5_8 (64 MiB cơ sở) | Argon2 v5_8 (16 MiB cơ sở) |
| ---: | ---: | ---: |
| 1 | 64 MiB | 16 MiB |
| 2 | 128 MiB | 32 MiB |
| 4 | 256 MiB | 64 MiB |
| 8 | 512 MiB | 128 MiB |
| 16 | 1.024 MiB (1 GiB) | 256 MiB |
| 32 | 2.048 MiB (2 GiB) | 512 MiB |

Công thức ở đây là **ước tính trên số phép đang thực hiện đồng thời**, không phải “số connection đang mở” và không phải “số user đang online”. Nếu 10.000 người có session hợp lệ, không có nghĩa server đang giữ 10.000 vùng nhớ hash đang hoạt động.

### 7.3. Heap, off-heap, RSS, limit container

- **JVM heap:** bộ nhớ Java objects được GC quản lý. Nhiều implementation tạo arrays lớn trong heap; cần theo dõi allocation rate và peak heap.
- **Native/off-heap:** các thành phần khác hoặc thuật toán/implementation khác có thể dùng bộ nhớ ngoài heap; không giả định `-Xmx` là toàn bộ RSS.
- **RSS (resident set size):** RAM resident của process; bị ảnh hưởng bởi heap thực dùng, off-heap, thread stack và shared mappings.
- **Container memory limit:** cgroup/container giới hạn toàn bộ process; JVM có thể OOM/GC áp lực hoặc container bị OOM-kill trước khi app kịp trả lỗi.
- **GC pauses/CPU bandwidth:** không chỉ RAM; password hashing có thể tranh CPU/cache/RAM bandwidth với database/client request của chính ứng dụng.

Vì vậy không thể lấy bảng “64 MiB × concurrency” làm sizing cuối. Nó là **cảnh báo sớm**. Cần đo trên JVM runtime, image, kiến trúc CPU và hạn mức container thực, cùng load test có giới hạn an toàn.

### 7.4. Ví dụ ngân sách tài nguyên

Một instance có memory limit 1 GiB; sau khi dành vùng cho heap ứng dụng, buffers và an toàn hoạt động, giả sử ngân sách thực dành cho password verification chỉ **256 MiB**. Dùng ước tính nền 64 MiB/scrypt thì **4 phép đồng thời đã chạm toàn bộ 256 MiB**, *chưa tính overhead*.

Không nên cấu hình “max concurrent=4” chỉ vì phép chia đúng bằng ngân sách. Cần **headroom** cho overhead, variance, GC, retry và các request không liên quan; ví dụ bắt đầu giới hạn thấp hơn rồi benchmark. Các con số là một bài toán sizing minh họa, không phải khuyến nghị cố định cho mọi dịch vụ.

## 8. Demo Java 17 chạy được: so sánh encode/matches và tính memory budget

Demo này chỉ dùng Spring Security Crypto và Bouncy Castle, **không cần Spring MVC/Boot**. Nó thực sự tính hash bằng hai encoder (không mô phỏng thuật toán) và in **kết quả boolean/ước lượng bộ nhớ lý thuyết**, không in password/hash.

### 8.1. Cấu trúc thư mục

~~~text
password-memory-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/passwordcost/
    └── PasswordMemoryLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'password-memory-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
    implementation 'org.bouncycastle:bcprov-jdk18on:1.86'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.passwordcost.PasswordMemoryLab'
}
~~~

**Tại sao thêm Bouncy Castle?** Spring Security `Argon2PasswordEncoder` hiện dựa vào thư viện này. Khi thiếu dependency, ứng dụng có thể gặp `NoClassDefFoundError` lúc encode/matches. Bản Bouncy Castle nêu ở đây dành cho ví dụ; môi trường thật phải rà soát advisory/BOM và cập nhật các bản vá tương thích khi phát hành.

### 8.2. Tệp Java đầy đủ

`src/main/java/example/passwordcost/PasswordMemoryLab.java`:

~~~java
package example.passwordcost;

import java.util.Map;

import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

public class PasswordMemoryLab {

    public static void main(String[] args) {
        // Mật khẩu giả chỉ dùng trong thí nghiệm local.
        String rawPassword = "demo-password!";

        SCryptPasswordEncoder scrypt =
                SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
        Argon2PasswordEncoder argon2 =
                Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        // Không in salt/hash vì mỗi lần encode có salt ngẫu nhiên.
        String scryptHash = scrypt.encode(rawPassword);
        String argon2Hash = argon2.encode(rawPassword);

        System.out.println("scrypt-correct="
                + scrypt.matches(rawPassword, scryptHash));
        System.out.println("scrypt-wrong="
                + scrypt.matches("wrong-password", scryptHash));

        System.out.println("argon2-correct="
                + argon2.matches(rawPassword, argon2Hash));
        System.out.println("argon2-wrong="
                + argon2.matches("wrong-password", argon2Hash));

        // Ước tính vùng nhớ lớn của thuật toán, KHÔNG phải RSS/heap đo thực.
        long scryptBaseBytes = 128L * (1 << 16) * 8;
        long scryptBaseMiB = scryptBaseBytes / (1024 * 1024);
        long argon2BaseKiB = 1L << 14;
        long argon2BaseMiB = argon2BaseKiB / 1024;

        System.out.println("scrypt-base-mib=" + scryptBaseMiB);
        System.out.println("argon2-base-mib=" + argon2BaseMiB);

        int simultaneous = 8;
        System.out.println("scrypt-8-base-mib="
                + (simultaneous * scryptBaseMiB));
        System.out.println("argon2-8-base-mib="
                + (simultaneous * argon2BaseMiB));

        // ID do demo tự đặt: ứng dụng thật phải duy trì mapping tương thích
        // với toàn bộ hash đã được lưu từ trước.
        PasswordEncoder delegating = new DelegatingPasswordEncoder(
                "argon2-v58",
                Map.of(
                        "argon2-v58", argon2,
                        "scrypt-v58", scrypt));

        String newlyEncoded = delegating.encode(rawPassword);
        String storedScrypt = "{scrypt-v58}" + scryptHash;

        System.out.println("current-id-match="
                + delegating.matches(rawPassword, newlyEncoded));
        System.out.println("old-id-match="
                + delegating.matches(rawPassword, storedScrypt));
        System.out.println("old-id-upgrade="
                + delegating.upgradeEncoding(storedScrypt));
    }
}
~~~

### 8.3. Chạy thử

Tại thư mục `password-memory-lab` với JDK 17+ và Gradle hoặc Gradle Wrapper tương thích:

~~~bash
gradle run --quiet
~~~

Nếu có wrapper:

~~~bash
./gradlew run --quiet
~~~

Trên Windows PowerShell, dùng `.\gradlew.bat run --quiet`.

**Kết quả từ `System.out.println`** (không tính thông báo của Gradle hoặc thư viện):

~~~text
scrypt-correct=true
scrypt-wrong=false
argon2-correct=true
argon2-wrong=false
scrypt-base-mib=64
argon2-base-mib=16
scrypt-8-base-mib=512
argon2-8-base-mib=128
current-id-match=true
old-id-match=true
old-id-upgrade=true
~~~

**Tại sao output boolean ổn định?** Salt ngẫu nhiên khiến chuỗi hash khác nhau mỗi lần, nhưng `matches` đọc đúng salt/metadata từ hash tương ứng nên kết quả là true cho password đúng và false cho password sai. `DelegatingPasswordEncoder` giữ cả hai ID để xác minh hash cũ; khi `idForEncode` là `argon2-v58` thì bản có ID `scrypt-v58` được đánh dấu cần nâng cấp.

**Không được hiểu sai phần “memory”:** những dòng `base-mib` tính đúng tham số/preset bằng phép toán Java, **không đo peak heap, RSS hay thời gian thực thi**. Chúng không tự chứng minh hệ thống đủ tài nguyên để chạy 8 hash đồng thời.

### 8.4. Biến thể nâng tham số (đoạn tích hợp)

Thay preset bằng cấu hình tường minh nếu đã benchmark và kiểm chính sách:

~~~java
SCryptPasswordEncoder strongerScrypt =
        new SCryptPasswordEncoder(
                1 << 17, 8, 1, 32, 16); // 128 MiB cơ sở

Argon2PasswordEncoder strongerArgon2 =
        new Argon2PasswordEncoder(
                16, 32, 1, 1 << 16, 3); // m=64 MiB, t=3
~~~

**Đây chỉ là biến thể giải thích tham số**, không phải khuyến nghị “nên dùng” chung. Tăng chi phí có thể đẩy ứng dụng vào OOM dưới tải login, đặc biệt ở container nhỏ. Trước khi dùng trong production phải đo latency, memory peak, throughput và stress behavior; đồng thời lập lộ trình nâng hash cũ phù hợp.

## 9. Tích hợp vào Spring Boot và DaoAuthenticationProvider

Với tài khoản trong database, `DaoAuthenticationProvider` dùng `UserDetailsService` để tải user và `PasswordEncoder.matches(...)` để so mật khẩu nhập vào với hash lưu. Provider chỉ trả `Authentication` thành công nếu kiểm bằng chứng và trạng thái account hợp lệ.

Luồng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Authentication Filter
    participant M as AuthenticationManager
    participant P as DaoAuthenticationProvider
    participant U as UserDetailsService
    participant E as PasswordEncoder
    C->>F: Username + password qua HTTPS
    F->>M: Authentication chưa xác thực
    M->>P: authenticate(request)
    P->>U: loadUserByUsername(username)
    U-->>P: UserDetails + encodedPassword
    P->>E: matches(raw, encoded)
    alt Bằng chứng và account status hợp lệ
        E-->>P: true
        P-->>M: Authentication đã xác thực
    else Bằng chứng sai / tài khoản không được phép
        E-->>P: false hoặc check trạng thái thất bại
        P-->>M: AuthenticationException
    end
~~~

Cấu hình khái niệm khi muốn dùng scrypt cho password mới:

~~~java
// Trong một lớp @Configuration của Spring Boot, import @Bean tương ứng.
@Bean
PasswordEncoder passwordEncoder() {
    return SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

Hoặc Argon2:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

Hai đoạn này là **lựa chọn cấu hình**, không phải đặt cả hai bean cùng type mà không chỉ định `@Primary`/`@Qualifier`. Ứng dụng đang có hash nhiều thuật toán thường cần `DelegatingPasswordEncoder` với mapping ID thay vì đổi bean trực tiếp và làm hỏng login cũ.

**Lưu ý:** hash phải được tạo trên đường đăng ký/reset/change password, lưu vào DB cùng metadata cần thiết. `UserDetailsService` đọc đúng giá trị encoded từ DB; không hash lại password đã hash khi load user. Trong authentication, không áp dụng `encode(raw) == storedHash` mà dùng `matches`.

## 10. DelegatingPasswordEncoder và nâng cấp không làm khóa tài khoản cũ

### 10.1. Vì sao phải giữ ID thuật toán?

Một hệ thống có thể đang lưu bcrypt, scrypt tham số cũ và Argon2 ở nhiều phiên bản. Format chuẩn khi dùng `DelegatingPasswordEncoder`:

~~~text
{id}encodedPassword
~~~

Ví dụ ứng dụng tự định nghĩa:

~~~text
{scrypt-v58}<hash-scrypt-hợp-lệ>
{argon2-v58}<hash-argon2-hợp-lệ>
~~~

`idForEncode` quyết định thuật toán **cho password mới**; các ID khác trong map cho phép **xác minh hash cũ**. `DelegatingPasswordEncoder` không biết ID tự nhiên nếu ứng dụng chưa định nghĩa mapping tương ứng. Các tên `scrypt-v58`, `argon2-v58` trong demo là **ID tùy chọn**, không phải tên mặc định của Spring Security.

**Đặc biệt với factory mặc định:**

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` thường chọn `bcrypt` để encode mới trong Spring Security 6.5, dù factory cũng có mapping nhiều encoder khác. Mapping được Spring Security đăng ký bao gồm ID cũ như `scrypt`/`argon2` và ID preset mới như `scrypt@SpringSecurity_v5_8` / `argon2@SpringSecurity_v5_8`. **Không suy luận rằng chỉ đổi bean từ bcrypt sang Argon2 là các hash bcrypt cũ tự nhận diện được** nếu chưa còn encoder tương thích.

### 10.2. Migration khi đăng nhập thành công

Một cách nâng cấp dần:

~~~text
1. Lưu hash có ID/version của thuật toán.
2. Người dùng gửi password qua kênh đăng nhập bảo mật.
3. DelegatingPasswordEncoder.matches(raw, storedHash).
4. Nếu hợp lệ và upgradeEncoding(storedHash) == true:
   - encode(raw) với policy hiện tại;
   - cập nhật DB với kiểm tra phiên bản/so sánh hash cũ để tránh race;
   - không lưu/log raw password;
   - đảm bảo giao dịch và audit phù hợp.
5. Kết thúc xác thực theo cơ chế Spring Security.
~~~

Trong Spring Security, `DaoAuthenticationProvider` hỗ trợ tích hợp nâng hash qua `UserDetailsPasswordService` khi được cấu hình; đây là vị trí phù hợp hơn việc tự chép raw password vào controller/async queue. Nếu ứng dụng không đăng nhập username/password thường xuyên (OIDC, passkey), cần chiến lược migration khác cho các tài khoản hiếm đăng nhập.

**Nâng cấp không đồng nghĩa reset password:** hash mới có thể được tạo từ cùng raw password sau khi đã được kiểm đúng ở thời điểm login; không thể đổi hash cũ sang Argon2 một cách chính xác chỉ từ bcrypt/scrypt hash mà không có raw password hay một quy trình reset hợp lệ.

### 10.3. Không cho phép fallback nguy hiểm

Khi `DelegatingPasswordEncoder` gặp ID không nhận diện hoặc không có prefix, mặc định có thể ném `IllegalArgumentException`. Đừng khắc phục bằng `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder.getInstance())` trong production: như vậy có thể biến dữ liệu không biết định dạng thành đường so mật khẩu dạng bản rõ.

Nếu đang có hash thiếu ID từ hệ thống cũ, migration phải được **giới hạn theo nguồn dữ liệu đáng tin**, kiểm định format, lập kế hoạch chuyển đổi và không giảm yêu cầu bảo mật chung. Những định dạng rất cũ hoặc đã bị coi không an toàn nên ưu tiên reset password có kiểm chứng.

### 10.4. UpgradeEncoding không tự cứu hệ thống

Một encoder có thể trả `false` cho `upgradeEncoding` dù security policy của tổ chức đã thay đổi, hoặc không có dữ liệu phiên bản đủ rõ. Cần kiểm triển khai và test. Ngoài ra, `upgradeEncoding(...)` **chỉ đưa ra tín hiệu**; nếu không có bước lưu hash mới thì account vẫn giữ hash cũ.

## 11. Benchmark đúng: không dùng con số latency mượn từ laptop khác

### 11.1. Những thứ cần đo

Trên environment càng giống production càng tốt, thu:

- `p50/p95/p99` thời gian `matches` và `encode` theo từng thuật toán/params.
- Peak heap/RSS và GC khi 1, 2, 4, 8, ... request hash đồng thời.
- Throughput (số verification hoàn thành mỗi giây) và queue wait.
- CPU utilization, memory bandwidth, page fault, container memory pressure.
- Login latency toàn phần, bao gồm DB/UserDetailsService và filter/authorization.
- Tác động của side load: API thường, batch jobs, cache và health checks.
- Hành vi khi vượt giới hạn: bounded queue, 429/503 theo policy, circuit breaker/timeout, metrics; không crash JVM.

Không dùng `System.currentTimeMillis()` một lần rồi chốt tham số cho cả hệ thống. JIT warm-up, CPU frequency, nhiệt độ, GC, hash random salt, load đồng thời và máy ảo đều làm kết quả dao động. Một benchmark nhỏ chỉ chứng minh code chạy, không chứng minh mức độ chống brute-force hoặc khả năng chịu tấn công.

### 11.2. Mã đo latency minh họa (không độc lập)

~~~java
// Nằm trong benchmark/test có PasswordEncoder và storedHash hợp lệ.
long start = System.nanoTime();
boolean ok = encoder.matches(rawPassword, storedHash);
long elapsedNs = System.nanoTime() - start;
System.out.println("verified=" + ok);
System.out.println("elapsed-ms=" + (elapsedNs / 1_000_000.0));
~~~

Đây là **đoạn tích hợp**, biến `encoder`, `rawPassword`, `storedHash` phải được thiết lập. Output `elapsed-ms` **không cố định**, vì phụ thuộc runtime. Trong kiểm thử hiệu năng thực, dùng JMH hoặc load tool có warm-up, thống kê nhiều mẫu và telemetry container để tránh phép đo thiếu chính xác.

### 11.3. Chọn tham số theo service, không chỉ theo user

Giả sử đo `matches` mất một khoảng mà trải nghiệm đăng nhập chấp nhận được ở concurrency=1. Bạn vẫn phải kiểm concurrency=8/16. Nếu memory pressure gây stop-the-world GC hay OOM, tăng tham số có thể làm **giảm bảo mật vận hành** vì attacker khiến dịch vụ từ chối login chính đáng dễ hơn.

Chọn cost factor là bài toán tối ưu đa mục tiêu:
- Làm chậm thử mật khẩu offline trên hash bị lộ.
- Giữ đăng nhập hợp lệ có độ trễ chấp nhận được.
- Giữ headroom dưới lưu lượng đỉnh và lỗi bất thường.
- Có khả năng cập nhật tham số khi phần cứng/thuật toán thay đổi.

Nên lưu **policy version**, benchmark có ngày/phần cứng và kế hoạch nâng cấp, thay vì chỉ ghi “Argon2 an toàn” mà không đo.

## 12. Chống từ chối dịch vụ khi mật khẩu cố tình tốn bộ nhớ

Memory-hard KDF giúp chống offline cracking, nhưng cũng khiến **mỗi lần login trực tuyến** tốn RAM/CPU của chính server. Một attacker có thể gửi nhiều request login để tạo áp lực bộ nhớ nếu thiếu kiểm soát.

Các biện pháp nên phối hợp:

1. **Rate limit nhiều chiều:** theo IP/source, account, session/device/risk; tránh chỉ khóa username và tạo điều kiện cho attacker DoS tài khoản người khác.
2. **Bounded concurrency:** dùng queue/semaphore hoặc pool phù hợp để giới hạn số phép hash đang chạy cùng lúc. Không dùng hàng đợi vô hạn trong giờ cao điểm.
3. **Global resource budget:** dành headroom cho database, API thông thường và health check; kiểm container limit.
4. **Thời gian chờ hợp lý:** client timeout và server timeout phải tương thích với thời gian xác thực đã đo. Hạn chế retry đồng loạt.
5. **Monitoring:** số hash đang chạy, queue length, reject count, heap usage, RSS, GC, OOM-kill, p95 login latency.
6. **Thiết kế session/token:** sau khi xác minh mật khẩu thành công, dùng session hoặc short-lived token phù hợp thay vì bắt client gửi password để hash lại trên mọi API request.
7. **Tách identity workload nếu cần:** login worker riêng, resource isolation, auto-scaling có giới hạn thực, không để KDF ảnh hưởng đến toàn bộ dữ liệu/nghiệp vụ.

**Không khuyến nghị giảm cost factor mạnh chỉ để “chữa” việc attacker spam login.** Hãy thiết kế kiểm soát lưu lượng và tài nguyên, rồi chọn tham số theo benchmark hợp lý. Nếu buộc phải hạ cost trong sự cố, cần đánh giá an ninh và lộ trình khôi phục vì nó làm giảm chi phí thử offline.

### 12.1. Ví dụ ước lượng concurrency theo headroom

Giả định budget riêng cho hashing là 320 MiB, scrypt nền 64 MiB/phép:

\[
C_{\text{lý thuyết}} = \left\lfloor \frac{320}{64} \right\rfloor = 5.
\]

Đừng lập tức cho 5 phép đồng thời: còn bộ nhớ phụ, GC và tải biến động. Bắt đầu với giới hạn thấp hơn theo benchmark, đo thực và tăng dần. Với Argon2 m=16 MiB cùng budget, phép chia ra 20; **điều đó không có nghĩa 20 phép cũng đạt latency/CPU SLA**, vì bottleneck có thể chuyển từ RAM sang CPU hoặc memory bandwidth.

### 12.2. Không nhầm login concurrency với toàn bộ HTTP threads

Một ứng dụng có 200 servlet threads không nhất thiết cùng xác minh mật khẩu; nhiều request chỉ dùng bearer/session. Nhưng khi attacker nhắm endpoint login, số phép hash có thể tiến đến số request được phép chạy song song. Do đó giới hạn cần áp vào **đường verification thực tế**, không chỉ tăng/max HTTP threads.

## 13. Vấn đề bảo mật thường bị bỏ qua

### 13.1. Salt ngẫu nhiên không phải pepper

**Salt** do encoder sinh riêng cho từng password và được lưu với hash; không cần giữ bí mật. **Pepper** là secret cấp hệ thống được quản lý riêng (KMS/HSM hoặc kho secret), có thể được thêm ở một thiết kế đã được đánh giá. Không tự chèn pepper vào password bằng nối chuỗi không có quy tắc version/rotation rồi cho rằng mọi thuật toán tự hỗ trợ.

Nếu dùng pepper, mất pepper có thể buộc reset password, và rotation cần thiết kế riêng; đây không phải phần thay thế cho salt hay KDF memory-hard.

### 13.2. Hash bị lộ vẫn có thể bị crack offline

Ngay cả scrypt/Argon2 với work factor hợp lý cũng không biến password yếu thành an toàn tuyệt đối. Attacker có hash và salt có thể thử từ điển offline. Cần password policy phù hợp, MFA/phishing-resistant authentication khi cần, phát hiện credential stuffing và kế hoạch ứng phó nếu database lộ.

### 13.3. Không lưu raw password/hash vào logs

Không log `rawPassword`, password hash, encoded storage string, `Authentication.toString()` chứa credential, hoặc request body chứa password. Hash dù là đầu ra một chiều vẫn là dữ liệu nhạy cảm hữu ích cho offline cracking.

### 13.4. Không tự tạo salt bằng username hoặc thời gian

Encoder chuẩn dùng salt ngẫu nhiên an toàn; không thay bằng `salt = username`, ID người dùng, timestamp hoặc constant chung. Salt đoán được/đụng nhau làm giảm khả năng chống bảng precompute và phân tích nhóm mật khẩu giống nhau.

### 13.5. Không mặc định hash kích thước lớn đồng nghĩa an toàn hơn

`hashLength=32` byte là chiều dài đầu ra; tăng lên 64 byte **không tương đương nhân đôi độ khó đoán mật khẩu** khi password entropy thấp. Work factor, salt, chính sách mật khẩu và bảo vệ server quan trọng hơn việc chỉ tăng length.

### 13.6. Khi dùng cloud/serverless

Ở container nhỏ hoặc serverless có memory limit thấp, scrypt preset 64 MiB có thể làm application chịu áp lực dưới concurrency. Serverless còn có cold start, CPU allocation theo memory tier và timeouts; điều chỉnh thông số dựa trên benchmark cho chính môi trường đó.

## 14. Kiểm thử chức năng và vận hành

| Test | Input/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Round-trip scrypt | Password đúng, hash do scrypt tạo | `matches` trả `true` |
| Sai password scrypt | Password khác, cùng encoded hash | `false` |
| Round-trip Argon2 | Password đúng, hash do Argon2 tạo | `true` |
| Sai password Argon2 | Password khác, cùng encoded hash | `false` |
| Salt ngẫu nhiên | Hai lần encode cùng password | Thường khác encoded string, nhưng đều matches |
| Different formats | Scrypt hash đưa trực tiếp vào Argon2 matches | Không được giả định tương thích; dùng đúng encoder/ID |
| Delegating old hash | Có `{scrypt-v58}...`, map có ID | `matches` thành công; `upgradeEncoding` có thể báo true |
| ID không có trong map | Chuỗi `{unknown}...` | Fail-safe, không tự cho thành công |
| Input null/không hợp lệ | Null, encoded hash sai format | Xử lý đúng hợp đồng/exception, không trả true |
| Mất Bouncy Castle | Runtime thiếu dependency | Build/test phát hiện lỗi trước production |
| Concurrency | 8/16/32 login hashes cùng lúc | Không OOM, có giới hạn/số liệu latency |
| Sai cấu hình `memory` | Truyền đơn vị byte thay KiB | Test config phát hiện số param sai |
| Migration | Hash old ID và new ID cùng tồn tại | Cả hai xác minh đúng, new encode dùng current ID |
| Upgrade after login | Hash cũ đã matches rồi rehash | Bản ghi mới được commit an toàn, không mất quyền/đối tượng |
| Brute force pressure | Lưu lượng lỗi bất thường | Rate-limit, queue và alerts hoạt động |
| Session reuse | User đã login có session hợp lệ | Không hash mật khẩu trên mọi API request |
| Cache user | UserDetails được cache | Password vẫn được kiểm khi authentication mới, cache không tương đương login |

**Kiểm thử trong Spring Boot:** sử dụng integration test với `DaoAuthenticationProvider`, `UserDetailsService` và `PasswordEncoder` thật. Một test chỉ dùng `@WithMockUser` kiểm authorization nhưng không kiểm thuật toán hash mật khẩu. Muốn khẳng định KDF hoạt động hãy dùng `encode/matches` thật hoặc request login qua filter/provider thật.

## 15. Những lỗi rất thường gặp

1. **Đặt `memoryCost=8` của scrypt bằng “8 MB”.** Sai: đó là `r`, còn bộ nhớ chính xấp xỉ `128 × N × r`.
2. **Tưởng Argon2 `memory=16384` là byte.** Sai: đơn vị KiB, tương đương 16 MiB.
3. **Nhân `m×p` để ước tính tổng RAM Argon2.** `m` là bộ nhớ toàn phép, không mặc định là bộ nhớ cho mỗi lane.
4. **Tăng `t` rồi nhân RAM x `t`.** Số pass chủ yếu tăng thời gian, không đơn giản nhân peak RAM theo số iteration.
5. **Dùng `encode(input).equals(storedHash)`.** Salt mới khiến so sánh chuỗi sai; dùng `matches`.
6. **Dùng SHA-256(password) thay adaptive password encoder.** Quá nhanh cho chống offline guessing.
7. **Lưu salt cố định/username làm salt.** Không thay thế random salt do encoder chuẩn sinh.
8. **Đặt N/m quá cao trên node ít RAM rồi không giới hạn concurrency.** Dễ OOM/DoS khi nhiều login.
9. **Tắt khả năng decode format old hash khi migration.** Có thể khóa hàng loạt user cũ.
10. **Thấy `upgradeEncoding=true` rồi nghĩ DB tự cập nhật.** Phải có bước rehash và lưu an toàn.
11. **Gán raw memory estimate bằng RSS đo thực.** Không tính GC, native, stack, cache và nhiều process.
12. **Bật Argon2 mà quên Bouncy Castle.** Có thể lỗi runtime dù compile được.
13. **So latency Argon2 với scrypt preset rồi kết luận thuật toán mạnh/yếu tuyệt đối.** Tham số và implementation khác nhau.
14. **Không test login thất bại ở tải cao.** KDF chạy cả khi password sai cho các account hợp lệ.
15. **Coi “password hash được match” là đủ cấp quyền.** Provider còn kiểm account status; authorization vẫn phải kiểm role, authority, tenant và resource.
16. **Ghi hash vào log để debug salt.** Hash là dữ liệu nhạy cảm có thể bị dùng để cracking.
17. **Gửi password mỗi request thay vì dùng session/token ngắn hạn phù hợp.** Tạo tải hash không cần thiết.
18. **Đặt tham số theo benchmark 1 request trên laptop cá nhân.** Không đại diện cho pod production/concurrency.
19. **Quên chính sách retry khi identity service chậm.** Retry có thể nhân số phép hash đang chạy, tăng nguy cơ cạn tài nguyên.
20. **Tùy tiện bật fallback plaintext cho hash không rõ ID.** Tạo đường đăng nhập yếu và lỗi bảo mật.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** Trong `new SCryptPasswordEncoder(65536,8,1,32,16)`, tham số `8` có nghĩa 8 MB?  
**Đáp án:** Không, đó là `r`. Bộ nhớ lõi khoảng `128×65536×8 = 64 MiB`.

**Câu 2:** Argon2 constructor nhận `memory=16384`. Một phép hash cần đúng 16.384 byte?  
**Đáp án:** Không, tham số memory đo bằng KiB. Mức cấu hình khoảng 16 MiB, chưa tính mọi overhead.

**Câu 3:** Tăng `iterations` Argon2 từ 2 lên 4 có nghĩa RAM tăng từ 16 lên 32 MiB?  
**Đáp án:** Không theo cách hiểu đó. `t` tăng số pass/tải tính toán; `m` vẫn là ngân sách bộ nhớ lớn của thuật toán.

**Câu 4:** 8 request cùng dùng preset scrypt 64 MiB có thể tiêu tốn tối thiểu bao nhiêu cho bảng nhớ lớn nếu đồng thời ở giai đoạn cao điểm?  
**Đáp án:** Ước tính **512 MiB** trước JVM/implementation overhead. Đo thực để lập giới hạn.

**Câu 5:** Dùng `encode("abc").equals(storedHash)` để kiểm login có đúng?  
**Đáp án:** Không. Salt ngẫu nhiên khiến hash thường khác; dùng `matches("abc", storedHash)`.

**Câu 6:** Nếu `matches` đúng, có thể bỏ kiểm enabled/locked?  
**Đáp án:** Không. `PasswordEncoder` chỉ kiểm mật khẩu; `DaoAuthenticationProvider` còn kiểm account status, và authorization kiểm quyền.

**Câu 7:** Vì sao Bouncy Castle cần có trên classpath khi dùng `Argon2PasswordEncoder`?  
**Đáp án:** Spring Security implementation dùng Bouncy Castle cho Argon2; thiếu dependency có thể lỗi runtime.

**Câu 8:** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có mặc định tạo Argon2 hash mới không?  
**Đáp án:** Không. Trong Spring Security 6.5, factory mặc định encode theo ID `bcrypt`; các thuật toán khác là mapping để tương thích/kiểm hash tương ứng.

**Câu 9:** Có thể đổi toàn bộ bcrypt hash đã lưu sang Argon2 mà không cần biết raw password?  
**Đáp án:** Không thể chuyển hash một chiều thành hash Argon2 tương đương của password gốc nếu không có password; dùng rehash khi login thành công hoặc quy trình reset đã xác minh.

**Câu 10:** Tại sao `upgradeEncoding` hữu ích?  
**Đáp án:** Nó báo hash hiện tại có thể cần nâng về policy encode mới. Nhưng cần mã cập nhật DB (hoặc `UserDetailsPasswordService`), không tự ghi.

**Câu 11:** `p=4` ở Argon2 nghĩa RAM = `4×m`?  
**Đáp án:** Không. `m` là tổng bộ nhớ cấu hình; số lane thay đổi cách sử dụng, không làm phép nhân đơn giản đó.

**Câu 12:** Nếu benchmark một phép hash 300 ms thì an toàn để chạy 1000 phép cùng lúc?  
**Đáp án:** Không. Cần kiểm RAM, CPU, thread queues, container limit, p95/p99 và chính sách rate limiting.

**Câu 13:** Khi nào nên thay scrypt bằng Argon2?  
**Đáp án:** Khi tổ chức chọn thuật toán phù hợp, thư viện/phiên bản được hỗ trợ, benchmark đáp ứng budget và có lộ trình bảo toàn xác thực hash cũ. Không có lý do chọn chỉ từ số MiB của preset.

**Câu 14:** Vì sao memory-hard KDF không thay rate limiting?  
**Đáp án:** Nó làm phép thử offline tốn kém, nhưng cũng tiêu tốn bộ nhớ server mỗi lần login. Attacker online vẫn có thể gửi nhiều yêu cầu để gây cạn tài nguyên nếu không giới hạn.

## 17. Checklist áp dụng cho production

- [ ] Dùng `PasswordEncoder` thích ứng, salt ngẫu nhiên và không lưu plaintext password.
- [ ] Xác định rõ scrypt `N,r,p` hoặc Argon2id `m(KiB),t,p` cùng format/version hash.
- [ ] Kiểm đơn vị byte/KiB/MiB, ghi rõ công thức và assumptions trong tài liệu vận hành.
- [ ] Benchmark `matches` và `encode` trên phần cứng/container production tương tự, có warm-up và sample thống kê.
- [ ] Đo peak heap/RSS/GC, thông lượng và p95 login dưới concurrency, không chỉ latency một request.
- [ ] Đặt headroom cho JVM và giới hạn số phép hash đang chạy đồng thời.
- [ ] Có rate limiting và cơ chế phản hồi an toàn khi identity hashing pool quá tải.
- [ ] Nếu dùng Argon2 Spring Security, kiểm Bouncy Castle version và dependency audit.
- [ ] Nếu dùng `DelegatingPasswordEncoder`, ID format/hash cũ vẫn được map đúng.
- [ ] Không bật plaintext fallback cho hash không rõ format.
- [ ] Có kế hoạch nâng cost factor theo thời gian và rehash khi login thành công.
- [ ] Kiểm `UserDetailsPasswordService`/DB update bảo đảm atomicity và không để credential rò rỉ.
- [ ] Không in raw password, password hash, salt hoặc token vào application logs.
- [ ] Dùng HTTPS, bảo vệ database, giới hạn quyền đọc hash và backup.
- [ ] Kiểm account status, MFA khi cần và authorization độc lập với `matches`.
- [ ] Theo dõi tỷ lệ hash thành công/thất bại, queue depth, timeout, GC, memory pressure, OOM và p95/p99 login.
- [ ] Có quy trình thay đổi cost khi tăng tải: canary, benchmark, rollback và policy rehash/hash version.

**Ghi nhớ:** Scrypt và Argon2 tăng chi phí thử mật khẩu offline bằng cách yêu cầu **CPU và bộ nhớ**. Nhưng cùng chi phí ấy cũng được **dịch vụ đăng nhập của bạn trả cho mỗi phép verify**. Bởi vậy, chọn tham số theo hai chiều: đủ mạnh trước tấn công, đồng thời phải giới hạn concurrency và giữ headroom vận hành. Spring Security giúp triển khai `encode/matches` và lưu version hash; chính ứng dụng phải thiết kế database, migration, rate limiting và ngân sách memory.

### Tài liệu chính thức và tiêu chuẩn

- Spring Security 6.5 — Password Storage: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — SCryptPasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/scrypt/SCryptPasswordEncoder.html
- Spring Security 6.5 — Argon2PasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html
- Spring Security 6.5 — DelegatingPasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- RFC 7914 — scrypt Password-Based Key Derivation Function: https://www.rfc-editor.org/rfc/rfc7914
- RFC 9106 — Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications: https://www.rfc-editor.org/rfc/rfc9106
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

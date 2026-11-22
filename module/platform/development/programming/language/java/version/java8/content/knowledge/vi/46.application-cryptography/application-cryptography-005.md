# SecureRandom.getInstanceStrong và cấu hình nguồn entropy trong Java

**Chủ đề:** Java 8 → Mật mã ứng dụng → SecureRandom.getInstanceStrong và cấu hình nguồn entropy.

**`SecureRandom`** là API Java dùng để tạo dữ liệu ngẫu nhiên có tính chất mật mã. Từ **Java 8**, ứng dụng có thể gọi **`SecureRandom.getInstanceStrong()`** để lấy implementation được lựa chọn theo cấu hình bảo mật của nền tảng. API này phù hợp khi ứng dụng cần tạo những giá trị quan trọng như khóa, nonce hoặc token bí mật và muốn tuân theo danh sách SecureRandom mạnh do JDK/provider công bố.

Điều cần hiểu đúng là:

> `getInstanceStrong()` **chọn một implementation theo security property `securerandom.strongAlgorithms`**. Nó không phải tên của một thuật toán cụ thể, không tự đặt mức 256 bit cho mọi provider, và không có nghĩa mỗi byte trả về là một byte entropy vật lý mới.

Một SecureRandom implementation có thể dùng **DRBG** (Deterministic Random Bit Generator): lấy seed từ nguồn entropy của hệ điều hành/provider, sau đó dùng thuật toán mật mã để tạo chuỗi byte giả ngẫu nhiên an toàn. Vì vậy cần phân biệt ba lớp:

1. **Entropy source:** nơi cung cấp seed khó đoán, thường là hệ điều hành hoặc thiết bị/provider.
2. **RNG/DRBG implementation:** cơ chế tạo và có thể reseed dữ liệu ngẫu nhiên.
3. **`getInstanceStrong()`:** cơ chế chọn implementation từ danh sách được cấu hình cho nền tảng.

`SecureRandom.getInstanceStrong()` có từ **Java 8** và vẫn là API hiện hành. **DRBG**, `DrbgParameters`, `SecureRandom.getParameters()` và các overload reseed/nextBytes có tham số được bổ sung từ **Java 9**. Bài phân biệt rõ hai mốc phiên bản và tập trung vào cách dùng hiện đại, không khuyến khích các mẹo cấu hình cũ hoặc tự tạo entropy bằng thời gian hệ thống.

Các ví dụ nền tảng chạy trên Java 17+; ví dụ `getInstanceStrong()` cơ bản cũng tương thích Java 8. Ví dụ DRBG yêu cầu Java 9+ và cần provider hỗ trợ yêu cầu tham số.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `SecureRandom` khác `Random`, `ThreadLocalRandom` và `SplittableRandom` như thế nào.
2. Dùng `SecureRandom.getInstanceStrong()` để chọn implementation theo security policy.
3. Phân biệt **thuật toán**, **provider**, **nguồn entropy** và **DRBG mechanism**.
4. Đọc `securerandom.strongAlgorithms`, `securerandom.drbg.config` và `securerandom.source`.
5. Kiểm tra implementation thực tế qua `getAlgorithm()`, `getProvider()` và `getParameters()`.
6. Hiểu vì sao `getInstanceStrong()` có thể chọn thuật toán khác nhau trên Windows, Linux, macOS hoặc JDK vendor khác.
7. Nhận biết khi nào `nextBytes()`, `generateSeed()` hoặc `reseed()` có thể chờ nguồn entropy.
8. Không tự seed SecureRandom bằng timestamp, `System.nanoTime()`, process ID hoặc giá trị dễ đoán.
9. Phân biệt `nextBytes()` với `generateSeed()` và `setSeed()`.
10. Dùng DRBG có security strength, reseed capability và prediction resistance theo yêu cầu.
11. Cấu hình nguồn entropy đúng phạm vi JDK/provider, tránh áp dụng máy móc đường dẫn riêng của một hệ điều hành.
12. Tạo token an toàn, chọn số ngẫu nhiên trong một miền không bị modulo bias.
13. Tái sử dụng SecureRandom thread-safe và tránh khởi tạo generator trong mọi request.
14. Kiểm thử mà không yêu cầu kết quả ngẫu nhiên phải giống nhau hoặc tự kết luận RNG an toàn chỉ từ một bài thống kê.

## 2. SecureRandom là gì?

`java.security.SecureRandom` là lớp sinh số ngẫu nhiên dùng cho mục đích mật mã. Nó cung cấp các API quen thuộc:

- `nextBytes(byte[])`: điền các byte ngẫu nhiên vào mảng.
- `nextInt()`, `nextLong()`, `nextBoolean()` và các method kế thừa từ `Random`.
- `nextInt(bound)`: tạo số nguyên trong miền giới hạn.
- `generateSeed(int)`: lấy byte seed, thường dùng để seed một RNG khác.
- `reseed()` (Java 9+): yêu cầu lấy entropy để reseed nếu implementation hỗ trợ.
- `getAlgorithm()` và `getProvider()`: xem implementation thực tế.

Ví dụ:

~~~java
import java.security.SecureRandom;

public class SecureRandomBasicsDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();

        byte[] bytes = new byte[16];
        random.nextBytes(bytes);

        System.out.println("byteCount=" + bytes.length);
        System.out.println("algorithm=" + random.getAlgorithm());
        System.out.println("provider=" + random.getProvider().getName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SecureRandomBasicsDemo.java
java SecureRandomBasicsDemo
~~~

`byteCount=16` là cố định. `algorithm` và `provider` phụ thuộc JDK, hệ điều hành, security providers và cấu hình của môi trường. Không nên ghi cứng một tên provider vào expected của test chạy trên nhiều nền tảng.

**Không in nội dung token/secret trong production log.** Chỉ in độ dài hoặc metadata không nhạy cảm khi cần chẩn đoán.

### 2.1. SecureRandom khác Random như thế nào?

| API | Mục đích chính | Dùng cho secret mật mã? |
|---|---|---|
| `java.util.Random` | Số giả ngẫu nhiên cho logic thông thường | Không |
| `ThreadLocalRandom` | Random hiệu năng cao cho tác vụ nhiều thread | Không |
| `SplittableRandom` | Random cho mô phỏng/tính toán, hỗ trợ split | Không |
| `java.security.SecureRandom` | Random dùng cho khóa, nonce, token và dữ liệu bảo mật | Có |

Các generator thông thường ưu tiên tính tiện lợi hoặc throughput. Không dùng chúng cho session ID, reset token, API key, nonce mật mã hoặc giá trị bí mật.

**Lưu ý:** `SecureRandom` kế thừa `Random`, nên có thể gọi `nextInt()` hoặc `nextLong()`. Việc có cùng superclass **không làm SecureRandom mất tính chất bảo mật**; implementation của SecureRandom cung cấp nguồn dữ liệu phù hợp.

### 2.2. Random mật mã vẫn có thể là pseudorandom

Tên “pseudo-random” không đồng nghĩa yếu. Một DRBG dùng thuật toán mật mã tạo đầu ra xác định từ seed bí mật, khó đoán đối với người không biết trạng thái/seed. Nguồn entropy tạo seed ban đầu và có thể cung cấp dữ liệu mới khi reseed.

Không cần một phần cứng tạo “true random” riêng cho từng byte token. Một DRBG được seed và vận hành đúng là mô hình chuẩn trong nhiều hệ thống mật mã.

## 3. `SecureRandom.getInstanceStrong()` làm gì?

Chữ ký:

~~~java
public static SecureRandom getInstanceStrong()
        throws NoSuchAlgorithmException
~~~

Method này được giới thiệu từ **Java 8**. Nó trả về một `SecureRandom` được lựa chọn dựa trên security property:

~~~text
securerandom.strongAlgorithms
~~~

Property này thuộc lớp `java.security.Security`, không phải một biến hệ thống thông thường. JDK distribution khai báo các implementation được coi là strong cho nền tảng đó. Java SE yêu cầu mỗi implementation cung cấp ít nhất một implementation strong.

**“Strong” ở đây là lựa chọn theo cấu hình nền tảng.** Method không có tham số để yêu cầu 256 bit, không yêu cầu prediction resistance cụ thể, và không ép mọi hệ điều hành dùng cùng một thuật toán.

### 3.1. Ví dụ Java 8: lấy strong implementation và sinh byte

Lưu thành **`StrongRandomDemo.java`**:

~~~java
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;

public class StrongRandomDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {

        SecureRandom random =
                SecureRandom.getInstanceStrong();

        byte[] secret = new byte[32];
        random.nextBytes(secret);

        System.out.println("algorithm="
                + random.getAlgorithm());

        System.out.println("provider="
                + random.getProvider().getName());

        System.out.println("bytes=" + secret.length);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StrongRandomDemo.java
java StrongRandomDemo
~~~

**Stdout đã xác minh trên môi trường JDK 24.0.2 / Windows:**

~~~text
algorithm=Windows-PRNG
provider=SunMSCAPI
bytes=32
~~~

Tên thuật toán và provider trên máy khác có thể khác. Ví dụ này chứng minh cách gọi và cách kiểm tra implementation, **không khẳng định Windows-PRNG là lựa chọn mặc định cho Linux/macOS hoặc mọi JDK**.

### 3.2. Khi nào chọn getInstanceStrong?

Phù hợp khi:

- Ứng dụng có policy rõ ràng yêu cầu implementation trong danh sách `securerandom.strongAlgorithms`.
- Tạo giá trị có mức độ quan trọng cao như material cho khóa dài hạn, token nhạy cảm hoặc nonce cần chất lượng mật mã.
- Muốn tuân theo lựa chọn strong do JDK/provider của môi trường triển khai cung cấp.

Với nhiều ứng dụng, `new SecureRandom()` cũng là một CSPRNG hợp lệ và đã được API định nghĩa để tạo dữ liệu ngẫu nhiên mạnh. Không nên suy luận rằng mọi lần gọi `new SecureRandom()` đều không an toàn.

**Chọn getInstanceStrong khi policy yêu cầu lựa chọn strong đã cấu hình**, không phải chỉ vì tên method nghe mạnh hơn.

### 3.3. Lỗi NoSuchAlgorithmException

`getInstanceStrong()` có thể ném `NoSuchAlgorithmException` nếu không tìm được implementation khả dụng trong danh sách cấu hình. Điều này có thể xảy ra khi:

- Security property bị sửa sai.
- Provider được chỉ định không được cài đặt.
- Provider không cung cấp algorithm được liệt kê.
- Môi trường JDK đã bị thay đổi hoặc cấu hình provider không nhất quán.

Không được âm thầm fallback sang `Random`, `ThreadLocalRandom` hoặc một thuật toán yếu hơn. Nếu ứng dụng bắt buộc phải có strong generator, hãy **fail startup hoặc từ chối thao tác bảo mật**, ghi lỗi cấu hình không chứa secret và sửa môi trường triển khai.

## 4. `securerandom.strongAlgorithms`: danh sách chọn implementation

`getInstanceStrong()` đọc danh sách algorithm/provider trong security property `securerandom.strongAlgorithms`.

Ví dụ một môi trường có thể hiển thị:

~~~text
securerandom.strongAlgorithms=Windows-PRNG:SunMSCAPI,DRBG:SUN
~~~

Đây là ví dụ cấu hình theo môi trường Windows/JDK cụ thể, **không phải giá trị dùng chung cho mọi hệ điều hành**.

Ý nghĩa các phần:

- `Windows-PRNG`: tên SecureRandom algorithm.
- `SunMSCAPI`: tên provider.
- `DRBG`: một algorithm SecureRandom khác.
- `SUN`: provider tương ứng.
- Dấu phẩy phân tách các lựa chọn được liệt kê.

`getInstanceStrong()` tìm implementation theo danh sách của nền tảng. Việc algorithm/provider nào thực sự được chọn phải được kiểm tra ở runtime bằng `getAlgorithm()` và `getProvider()`.

### 4.1. Không nhầm tên algorithm và provider

~~~java
SecureRandom random = SecureRandom.getInstanceStrong();

System.out.println(random.getAlgorithm());
System.out.println(random.getProvider().getName());
~~~

`getAlgorithm()` trả tên algorithm. `getProvider().getName()` trả provider cung cấp implementation. Hai tên này không phải cùng một khái niệm.

### 4.2. Không hard-code provider nếu không có yêu cầu

Provider có thể khác nhau theo:

- JDK vendor và phiên bản.
- Hệ điều hành.
- Provider tích hợp.
- Provider phần cứng/PKCS#11 đã cấu hình.
- Security policy của tổ chức.

Hard-code `SunMSCAPI`, `SUN` hoặc một provider cụ thể làm ứng dụng khó di chuyển và có thể bỏ qua provider phần cứng đã được quản trị viên cài đặt.

Chỉ chỉ định provider cụ thể khi có yêu cầu triển khai/compliance đã xác nhận và môi trường bảo đảm provider đó tồn tại.

## 5. Kiểm tra cấu hình entropy bằng Security.getProperty

Các property quan trọng:

| Security property | Vai trò |
|---|---|
| `securerandom.strongAlgorithms` | Danh sách algorithm/provider mà `getInstanceStrong()` sử dụng |
| `securerandom.drbg.config` | Cấu hình DRBG của SUN provider; có thể chọn mechanism, algorithm và default instantiation parameters |
| `securerandom.source` | Nguồn entropy mặc định mà một số implementation, trong đó có DRBG của SUN provider, sử dụng |

Đọc security property bằng **`Security.getProperty(...)`**:

~~~java
import java.security.Security;

public class SecureRandomPropertyProbe {
    public static void main(String[] args) {
        String[] keys = {
                "securerandom.strongAlgorithms",
                "securerandom.drbg.config",
                "securerandom.source"
        };

        for (String key : keys) {
            System.out.println(
                    key + "=" + Security.getProperty(key));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SecureRandomPropertyProbe.java
java SecureRandomPropertyProbe
~~~

**Stdout quan sát được trên JDK 24.0.2 / Windows:**

~~~text
securerandom.strongAlgorithms=Windows-PRNG:SunMSCAPI,DRBG:SUN
securerandom.drbg.config=
securerandom.source=file:/dev/random
~~~

Đây là cấu hình được quan sát ở một runtime cụ thể. Giá trị `securerandom.source` có thể phụ thuộc implementation/provider và không nên diễn giải độc lập như bằng chứng rằng mọi provider trên Windows đều mở đúng một file Unix. Hãy đọc tài liệu JDK/provider đang triển khai và kiểm tra implementation thực tế.

**Không dùng `System.getProperty("securerandom.strongAlgorithms")` để đọc Security property.** `System` properties và `Security` properties là hai vùng cấu hình khác nhau.

### 5.1. Xem security settings từ command line

Trên JDK hỗ trợ tùy chọn này, có thể xem security settings bằng:

~~~bash
java -XshowSettings:security -version
~~~

Output phụ thuộc JDK, provider và cấu hình runtime. Đây là cách kiểm tra môi trường, không phải kết quả có thể dùng làm expected giống nhau trên mọi máy.

## 6. Cấu hình nguồn entropy: ba property không làm cùng một việc

Một hiểu lầm phổ biến là thay đổi `securerandom.source` sẽ tự động thay algorithm mà `getInstanceStrong()` lựa chọn. Hai việc này độc lập.

### 6.1. `securerandom.strongAlgorithms`

Quyết định **implementation nào được coi là strong để chọn**.

Ví dụ, danh sách có thể chứa `DRBG:SUN` hoặc một implementation native/hardware khác. Việc thêm tên một algorithm không tự làm algorithm đó tốt hơn; provider phải thực sự cung cấp implementation và nó phải đáp ứng policy.

### 6.2. `securerandom.drbg.config`

Cấu hình DRBG của SUN provider. Trong implementation tham chiếu của JDK, property này có thể xác định:

- DRBG mechanism, ví dụ `Hash_DRBG` hoặc `CTR_DRBG`.
- DRBG algorithm, ví dụ `SHA-256` hoặc `AES-256`.
- Default security strength.
- Capability mặc định liên quan đến reseeding và prediction resistance.

Theo tài liệu Oracle Java SE 26, DRBG SUN mặc định sử dụng **Hash_DRBG với SHA-256** khi không có cấu hình khác; default instantiation request là **128 bit**, không yêu cầu prediction resistance và không có personalization string. Đây là mô tả cho implementation SUN của JDK tham chiếu, không phải cam kết cho mọi provider.

### 6.3. `securerandom.source`

Xác định nguồn entropy mặc định được một số implementation sử dụng. Trong DRBG SUN, tài liệu JDK nêu rõ nguồn entropy hệ thống được xác định bởi property này. `generateSeed(int)` của implementation đó cũng đọc trực tiếp từ nguồn entropy hệ thống này.

**Đây không phải API portable để ứng dụng tự cung cấp một mảng byte entropy.** Cách diễn giải giá trị và cách truy cập OS source phụ thuộc JDK/provider và hệ điều hành.

### 6.4. Nơi đặt cấu hình trong JDK hiện đại

Security properties thường được nạp từ file:

~~~text
<JAVA_HOME>/conf/security/java.security
~~~

Đây là vị trí thường dùng trong JDK hiện đại; vị trí thực tế có thể khác theo vendor/package.

Oracle cho phép security properties được đặt tĩnh trong security properties file hoặc thay đổi động qua API `Security.setProperty(...)`. Tuy nhiên, các cấu hình này có phạm vi toàn JVM và có thể ảnh hưởng nhiều thành phần.

**Không thay property toàn cục theo từng request.** Nếu tổ chức cần thay đổi, hãy:

1. Xác định requirement bảo mật và provider được phép.
2. Đọc tài liệu JDK/provider tương ứng.
3. Thay đổi cấu hình ở môi trường triển khai có quản lý.
4. Khởi động lại process nếu cấu hình/implementation đã được khởi tạo và cần nạp lại.
5. Kiểm tra property thực tế và algorithm/provider sau khi triển khai.
6. Chạy test latency, entropy readiness và security acceptance trên đúng OS/JDK.

Không sao chép nguyên một dòng `securerandom.source` từ một máy Linux sang Windows hoặc ngược lại.

## 7. Entropy source và DRBG: mô hình hoạt động

Một mô hình khái niệm:

~~~text
OS / phần cứng / nhiễu môi trường
              |
              v
       Entropy source
              |
       seed / reseed input
              |
              v
          DRBG
     (Hash_DRBG, CTR_DRBG...)
              |
        nextBytes(...)
              |
              v
       byte ngẫu nhiên
       cho ứng dụng
~~~

**Entropy source** cung cấp seed khó đoán. **DRBG** dùng seed để sinh một lượng lớn output giả ngẫu nhiên theo thuật toán mật mã. Khi reseed, DRBG tiếp nhận entropy mới theo cơ chế của provider.

Không được coi 32 byte output từ một DRBG là 32 byte entropy vật lý độc lập được lấy trực tiếp từ cảm biến. Độ an toàn phụ thuộc nguồn seed, DRBG, cách reseed, provider và cấu hình.

### 7.1. Nguồn entropy của hệ điều hành

Các hệ điều hành hiện đại thường cung cấp kernel CSPRNG dựa trên entropy thu thập từ thiết bị và các nguồn nhiễu môi trường. JDK/provider có thể sử dụng native OS API, thiết bị entropy hoặc provider phần cứng.

Ví dụ trên Linux:

- `/dev/urandom` cung cấp output của kernel CSPRNG.
- `/dev/random` có semantics blocking riêng.
- `getrandom()` mặc định dùng urandom source và chờ entropy pool được khởi tạo trước khi trả dữ liệu ở chế độ blocking mặc định.

Theo Linux man-pages hiện hành, với hầu hết ứng dụng, nên dùng `/dev/urandom` hoặc `getrandom()` không đặt `GRND_RANDOM`; việc đọc `/dev/random` hoặc dùng `GRND_RANDOM` có thể block lâu và làm tăng độ phức tạp. Chi tiết còn phụ thuộc kernel/version.

**Không áp dụng quy tắc Linux cho Windows/macOS** và không giả định mọi JDK provider đều gọi cùng một OS interface.

### 7.2. Không tự tạo entropy bằng timestamp

Các giá trị sau không phải nguồn entropy đủ tin cậy để seed generator mật mã:

~~~java
System.currentTimeMillis();
System.nanoTime();
new Random().nextLong();
Thread.currentThread().getId();
ProcessHandle.current().pid();
~~~

Chúng có thể đoán được, có miền giá trị hạn chế hoặc tương quan với trạng thái hệ thống. Ghép nhiều giá trị dễ đoán lại với nhau không tự tạo ra entropy mạnh.

Hãy để SecureRandom/provider lấy seed từ nguồn entropy được cấu hình và quản trị bởi nền tảng.

### 7.3. Entropy không đồng nghĩa với throughput

Nguồn entropy thật có thể thu thập chậm hơn tốc độ DRBG tạo output. DRBG cho phép sinh nhiều byte từ seed ban đầu và reseed theo cơ chế phù hợp. Không cần yêu cầu kernel cung cấp từng byte mới cho mọi lần gọi `nextBytes`.

## 8. Vì sao SecureRandom có thể block?

Tài liệu `SecureRandom` nêu rằng tùy implementation, các method sau có thể block trong khi thu thập entropy:

- `generateSeed(int)`.
- `reseed()`.
- `nextBytes(byte[])`.

Một PRNG SecureRandom mới có thể được seed lười. Lần gọi `nextBytes` đầu tiên có thể kích hoạt việc tự seed từ nguồn entropy do implementation lựa chọn.

**Không phải mọi lần gọi `getInstanceStrong()` đều block**, và không phải mọi implementation strong đều dùng nguồn blocking. Tình huống cụ thể phụ thuộc provider, OS, cấu hình và trạng thái entropy source.

### 8.1. Tách thời gian tạo instance và thời gian sinh byte

Khi điều tra chậm:

1. Đo thời gian `SecureRandom.getInstanceStrong()`.
2. Đo riêng lần `nextBytes()` đầu tiên.
3. Đo những lần `nextBytes()` tiếp theo.
4. Nếu dùng `generateSeed` hoặc `reseed`, đo riêng chúng.
5. Ghi JDK version, provider, algorithm, OS/kernel và cấu hình entropy.

Nếu chỉ đo thời gian khởi tạo object, bạn có thể bỏ sót chi phí lazy seeding ở lần dùng đầu tiên.

### 8.2. Cách xử lý khi ứng dụng cần latency ổn định

- Khởi tạo và warm-up SecureRandom ở giai đoạn startup có kiểm soát nếu phù hợp với hệ thống.
- Đo latency thật trong container/VM và trên máy production tương đương.
- Đảm bảo OS entropy pool đã sẵn sàng khi service bắt đầu phục vụ request.
- Kiểm tra cấu hình provider và entropy source thay vì tự thay bằng một RNG yếu.
- Theo dõi thời gian khởi tạo và lỗi provider.
- Không âm thầm fallback sang `Random` khi SecureRandom bị chậm hoặc lỗi.

Warm-up có thể chuyển thời gian chờ từ request đầu sang startup; nó không loại bỏ yêu cầu entropy.

### 8.3. Không mặc định “blocking” đồng nghĩa “an toàn hơn”

Một implementation có tên `NativePRNGBlocking` có thể dùng nguồn blocking trên nền tảng tương ứng, nhưng tên này không thay thế việc đánh giá provider, OS và security policy. Chỉ chọn algorithm cụ thể khi có yêu cầu được xác nhận và tài liệu implementation phù hợp.

## 9. Không tự seed SecureRandom bằng dữ liệu dễ đoán

Đây là một lỗi bảo mật rất quan trọng:

~~~java
// KHÔNG dùng:
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis());
~~~

`setSeed(...)` **bổ sung seed do caller cung cấp**, không phải một lệnh “bật chế độ bảo mật”. Nếu gọi `setSeed` trước lần `nextBytes`/`reseed` đầu tiên, một PRNG SecureRandom sẽ không tự seed theo cơ chế mặc định. Caller phải đảm bảo dữ liệu seed có đủ entropy.

### 9.1. Các anti-pattern

~~~java
random.setSeed(System.nanoTime());
random.setSeed(new Random().nextLong());
random.setSeed(userId);
random.setSeed(processId);
random.setSeed(123456789L);
~~~

Các nguồn này có thể dự đoán hoặc có miền quá nhỏ. Không dùng chúng để thay thế entropy source của nền tảng.

### 9.2. Có cần gọi setSeed thủ công không?

Trong ứng dụng thông thường, **không**. Tạo SecureRandom theo constructor hoặc factory phù hợp, rồi dùng `nextBytes`/`nextInt`.

Nếu hệ thống có thiết kế seed management đặc biệt, hãy dùng entropy source đã được đánh giá và làm theo tài liệu provider. Không trộn seed tự tạo từ dữ liệu dễ đoán vào một generator rồi tuyên bố nó an toàn.

### 9.3. `setSeed(byte[])` và `setSeed(long)` khác nhau

- `setSeed(byte[])`: thêm mảng byte seed vào trạng thái.
- `setSeed(long)`: dùng tám byte từ long; method tồn tại để tương thích với `Random`.
- Cả hai không tự chứng minh seed đầu vào có entropy.
- Nếu gọi trước lần sinh đầu tiên, caller có trách nhiệm đảm bảo seed đủ khó đoán.

Không dùng `setSeed(long)` với clock, counter hoặc một số ID.

### 9.4. SecureRandom(byte[] seed)

Constructor nhận seed cũng yêu cầu caller có seed phù hợp. Đừng dùng seed cố định trong code production:

~~~java
// Không dùng cho secret production:
new SecureRandom(new byte[] {1, 2, 3, 4});
~~~

Seed cố định làm mất tính không dự đoán được cần thiết. Để tạo dữ liệu ngẫu nhiên mật mã, dùng constructor/factory tự seed hoặc provider đã cấu hình.

## 10. `nextBytes`, `generateSeed` và `reseed` khác nhau

| Method | Mục đích | Ghi chú |
|---|---|---|
| `nextBytes(byte[])` | Sinh byte ngẫu nhiên cho ứng dụng | Dùng cho token/nonce/secret bytes |
| `generateSeed(int)` | Sinh byte seed để seed RNG khác | Có thể đọc trực tiếp entropy source và block |
| `setSeed(...)` | Bổ sung seed do caller cung cấp | Caller phải có seed đủ entropy |
| `reseed()` | Lấy entropy từ entropy source để reseed | Java 9+, provider có thể không hỗ trợ |
| `getSeed(int)` | Static API lấy seed | Chỉ giữ cho tương thích ngược; ưu tiên instance + `generateSeed` |

### 10.1. Sinh token bằng nextBytes

~~~java
byte[] tokenBytes = new byte[32];
random.nextBytes(tokenBytes);
~~~

Đây là cách thông thường để tạo 32 byte ngẫu nhiên cho token. `32` byte tương đương 256 bit dữ liệu đầu ra; độ an toàn cuối cùng còn phụ thuộc security strength của generator và cách token được quản lý.

### 10.2. Khi nào dùng generateSeed?

Ví dụ bạn đang triển khai một RNG khác và cần seed bytes từ nguồn seed của SecureRandom:

~~~java
byte[] seed = random.generateSeed(32);
~~~

Không gọi `generateSeed` thay cho `nextBytes` trong mọi trường hợp. Hai method có mục đích khác nhau và có thể đi qua đường lấy entropy khác nhau tùy provider.

### 10.3. Reseed không phải thao tác bắt buộc sau mỗi request

DRBG có thể tự reseed theo giới hạn tuổi seed/cơ chế provider. Ứng dụng có thể gọi `reseed()` khi có yêu cầu, nếu implementation hỗ trợ. Không nên gọi reseed vô tội vạ trong mỗi request vì có thể làm tăng latency hoặc tiêu thụ entropy không cần thiết.

`reseed()` được thêm từ Java 9 và có thể ném `UnsupportedOperationException` nếu provider không triển khai.

## 11. DRBG trong Java 9+: yêu cầu strength và capability

Java 9 giới thiệu `DrbgParameters` để mô tả yêu cầu khởi tạo và sinh byte cho DRBG.

Ba khái niệm quan trọng:

- **Security strength:** mức an toàn yêu cầu theo bit.
- **Capability:** yêu cầu hỗ trợ reseeding và/hoặc prediction resistance.
- **Personalization string:** dữ liệu phân biệt mục đích/instance; nó không thay thế entropy source.

Các capability thường gặp:

| Capability | Ý nghĩa |
|---|---|
| `NONE` | Không yêu cầu khả năng reseed/prediction resistance bổ sung |
| `RESEED_ONLY` | Yêu cầu hỗ trợ reseeding |
| `PR_AND_RESEED` | Yêu cầu prediction resistance và reseeding |

`PR_AND_RESEED` biểu thị capability được yêu cầu/hỗ trợ. Nếu muốn yêu cầu prediction resistance cho một lần sinh byte, truyền `DrbgParameters.NextBytes` với `predictionResistance=true`.

### 11.1. Tạo DRBG với 256-bit strength

Lưu thành **`ConfiguredDrbgDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.DrbgParameters;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;

public class ConfiguredDrbgDemo {
    public static void main(String[] args)
            throws GeneralSecurityException {

        byte[] personalization =
                "application-token-v1".getBytes(
                        StandardCharsets.UTF_8);

        SecureRandom drbg = SecureRandom.getInstance(
                "DRBG",
                DrbgParameters.instantiation(
                        256,
                        DrbgParameters.Capability.PR_AND_RESEED,
                        personalization));

        byte[] output = new byte[32];

        drbg.nextBytes(
                output,
                DrbgParameters.nextBytes(-1, true, null));

        DrbgParameters.Instantiation actual =
                (DrbgParameters.Instantiation)
                        drbg.getParameters();

        System.out.println("algorithm="
                + drbg.getAlgorithm());

        System.out.println("provider="
                + drbg.getProvider().getName());

        System.out.println("strength="
                + actual.getStrength());

        System.out.println("reseed="
                + actual.getCapability().supportsReseeding());

        System.out.println("predictionResistance="
                + actual.getCapability()
                        .supportsPredictionResistance());

        System.out.println("bytes=" + output.length);
    }
}
~~~

Biên dịch và chạy trên Java 9+:

~~~bash
javac -encoding UTF-8 ConfiguredDrbgDemo.java
java ConfiguredDrbgDemo
~~~

**Stdout đã xác minh trên JDK 24.0.2 / SUN provider:**

~~~text
algorithm=DRBG
provider=SUN
strength=256
reseed=true
predictionResistance=true
bytes=32
~~~

### 11.2. Yêu cầu không có nghĩa mọi provider đều đáp ứng

`getInstance("DRBG", params)` yêu cầu provider hỗ trợ ít nhất các tham số được chỉ định. Nếu provider không thể đáp ứng, việc tạo instance có thể thất bại với exception bảo mật phù hợp.

Không bắt exception rồi âm thầm tạo một DRBG yếu hơn. Hãy quyết định rõ:

- Ứng dụng có bắt buộc 256 bit không?
- Có cần prediction resistance không?
- Provider/thiết bị triển khai có hỗ trợ không?
- Nếu không hỗ trợ, hệ thống phải từ chối thao tác hay dùng một cấu hình đã được phê duyệt khác?

### 11.3. Kiểm tra effective parameters

Sau khi tạo, gọi `getParameters()` để đọc **tham số thực tế**. Yêu cầu truyền vào và effective parameters không nhất thiết có cùng object/biểu diễn, nhưng implementation phải đáp ứng tối thiểu yêu cầu được chấp nhận.

Với implementation không phải DRBG hoặc provider không sử dụng parameters, `getParameters()` có thể là `null`. Không cast mù:

~~~java
if (random.getParameters()
        instanceof DrbgParameters.Instantiation) {

    DrbgParameters.Instantiation actual =
            (DrbgParameters.Instantiation)
                    random.getParameters();

    System.out.println(actual.getStrength());
}
~~~

### 11.4. Personalization string không phải password hay seed bí mật

Personalization string giúp phân biệt mục đích/instance trong quá trình instantiate DRBG. Ví dụ `"application-token-v1"` chỉ là nhãn ngữ cảnh.

Không đưa password, private key, token bí mật hoặc dữ liệu nhạy cảm vào personalization string. Nó không phải nguồn entropy và không biến seed yếu thành seed mạnh.

## 12. `getInstanceStrong()` và DRBG explicit: chọn cái nào?

| Nhu cầu | API phù hợp |
|---|---|
| Dùng strong implementation theo policy nền tảng | `SecureRandom.getInstanceStrong()` |
| Dùng default CSPRNG của JDK | `new SecureRandom()` |
| Yêu cầu rõ DRBG algorithm family và tham số | `SecureRandom.getInstance("DRBG", params)` (Java 9+) |
| Cần đọc implementation đã chọn | `getAlgorithm()`, `getProvider()` |
| Cần kiểm tra DRBG effective strength/capability | `getParameters()` (Java 9+) |
| Cần byte cho token | `nextBytes(byte[])` |
| Cần seed cho RNG khác | `generateSeed(int)` |

**Đừng đánh đồng hai API sau:**

~~~java
SecureRandom a = SecureRandom.getInstanceStrong();
SecureRandom b = SecureRandom.getInstance("DRBG");
~~~

`a` được chọn theo `securerandom.strongAlgorithms`. `b` yêu cầu algorithm tên `DRBG` theo provider order. Một instance DRBG không tự động là implementation mà property strong đã chọn; ngược lại `getInstanceStrong()` có thể trả một algorithm không phải tên `"DRBG"`.

Nếu muốn cả DRBG lẫn strength/capability cụ thể, yêu cầu bằng `getInstance("DRBG", DrbgParameters...)` và kiểm tra effective parameters. Nếu policy tổ chức bắt buộc implementation strong theo property, không tự bỏ qua policy bằng cách gọi một algorithm khác.

## 13. Tạo token URL-safe bằng SecureRandom

Token thường cần:

- Có đủ byte ngẫu nhiên.
- Không dùng seed dự đoán được.
- Encode an toàn để truyền qua URL/header.
- Không ghi token vào log.
- Có thời hạn, phạm vi và cơ chế thu hồi phù hợp.

### 13.1. Demo token 32 byte

Lưu thành **`SecureTokenDemo.java`**:

~~~java
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {

        SecureRandom random =
                SecureRandom.getInstanceStrong();

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);

        System.out.println("rawBytes=" + bytes.length);
        System.out.println("tokenChars=" + token.length());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SecureTokenDemo.java
java SecureTokenDemo
~~~

**Stdout:**

~~~text
rawBytes=32
tokenChars=43
~~~

Độ dài cố định vì 32 byte khi Base64 URL-safe và bỏ padding sẽ thành 43 ký tự. Giá trị token thay đổi mỗi lần chạy và **không được in ra stdout**.

### 13.2. Độ dài token cần dựa vào threat model

32 byte thường là lựa chọn thực tế cho bearer token có 256 bit dữ liệu ngẫu nhiên. Với hệ thống khác, cần đánh giá:

- Khả năng đoán trực tuyến.
- Rate limit.
- Thời hạn token.
- Phạm vi quyền.
- Lưu trữ/hash token ở server.
- Cơ chế revoke và rotation.
- Tác động nếu token bị lộ.

Không coi một chuỗi dài là an toàn nếu nó được tạo từ timestamp, counter hoặc dữ liệu dễ đoán.

### 13.3. Không dùng UUID như một thay thế tự động

UUID có nhiều phiên bản và semantics khác nhau. Không tự suy mọi UUID đều có entropy hoặc unpredictability giống token 256 bit từ SecureRandom. Nếu protocol yêu cầu token bí mật, hãy dùng byte từ SecureRandom với encoding phù hợp.

## 14. Số nguyên trong một miền: tránh modulo bias

Nếu cần số ngẫu nhiên từ 0 đến `bound-1`, dùng:

~~~java
int value = random.nextInt(bound);
~~~

`nextInt(bound)` cung cấp giá trị trong miền hợp lệ theo API của Random/SecureRandom.

Không viết:

~~~java
int value = Math.abs(random.nextInt()) % bound;
~~~

Cách viết này có hai vấn đề:

1. `Math.abs(Integer.MIN_VALUE)` vẫn âm do overflow.
2. Dùng `% bound` trực tiếp có thể tạo **modulo bias** nếu số lượng giá trị đầu vào không chia hết cho bound.

Nếu chọn một ký tự trong alphabet:

~~~java
char selected = alphabet.charAt(
        random.nextInt(alphabet.length()));
~~~

Hãy kiểm tra alphabet không rỗng. Với chuỗi Unicode nhiều code point, dùng code point array nếu muốn chọn một ký tự theo code point thay vì một UTF-16 code unit.

## 15. SecureRandom có thread-safe không?

Tài liệu API xác nhận `SecureRandom` an toàn khi nhiều thread cùng sử dụng. Provider có thể khai báo service thread-safe; nếu không, lớp SecureRandom đồng bộ những lời gọi SPI liên quan theo hợp đồng.

Vì vậy một cách triển khai phổ biến là:

~~~java
private static final SecureRandom RANDOM =
        new SecureRandom();
~~~

Hoặc inject một instance SecureRandom vào service để dễ quản lý và kiểm thử.

Không cần tạo một SecureRandom mới cho từng token nếu không có lý do rõ ràng. Tạo liên tục có thể lặp lại chi phí khởi tạo/lazy seeding và tăng latency.

**Thread-safe không đồng nghĩa không có chi phí đồng bộ.** Nếu throughput cao, đo workload thật, kiểm tra provider và cân nhắc thiết kế sở hữu instance theo service. Không tự chuyển sang `Random` chỉ để tránh lock.

## 16. Kiểm thử SecureRandom đúng cách

Không có cách unit test đơn giản nào chứng minh một RNG là cryptographically secure chỉ bằng cách nhìn một vài output. Chất lượng phụ thuộc thuật toán, seed, provider, cấu hình và môi trường.

### 16.1. Những gì nên test

- Tạo instance thành công theo policy.
- `getAlgorithm()` và provider thuộc nhóm được phép nếu tổ chức có allowlist.
- `nextBytes` điền đúng số byte.
- Token encoding có độ dài/format đúng.
- `nextInt(bound)` luôn nằm trong miền hợp lệ.
- Lỗi cấu hình không bị nuốt.
- Nếu dùng DRBG, effective strength/capability đáp ứng yêu cầu.
- Nếu môi trường có startup latency budget, đo riêng thời gian khởi tạo và lần sinh đầu.

### 16.2. Những gì không nên test

- Không assert byte output bằng một chuỗi cố định.
- Không assert hai lần sinh chắc chắn khác nhau như một bằng chứng mật mã.
- Không chỉ đếm số byte 0/1 rồi kết luận an toàn.
- Không dùng test thống kê tự viết để thay thế đánh giá thuật toán/provider.
- Không dùng `setSeed(fixedValue)` để ép SecureRandom sinh kết quả ổn định trong test production-like.

### 16.3. Unit test format bằng dependency injection

Nếu logic của bạn chỉ cần kiểm tra token encoding, có thể tách interface sinh byte và cung cấp implementation giả cho unit test. Khi test generator thực tế, dùng SecureRandom thật trong một integration test riêng.

Cách này giữ test business logic deterministic mà không đưa một seed yếu vào đường code production.

### 16.4. Kiểm thử không log secret

Khi kiểm thử, chỉ ghi:

- Độ dài byte.
- Tên algorithm/provider không nhạy cảm.
- Security strength/capability nếu provider công bố.
- Thời gian thực thi.
- Kết quả PASS/FAIL.

Không ghi token, seed, private key hoặc byte output vào log chỉ để debug.

## 17. Chẩn đoán entropy starvation và startup chậm

Khi SecureRandom bị chậm, điều tra theo thứ tự:

1. JDK vendor/version và provider.
2. Giá trị `securerandom.strongAlgorithms`.
3. Giá trị `securerandom.drbg.config`.
4. Giá trị `securerandom.source`.
5. OS/kernel và trạng thái entropy source.
6. Máy vật lý, VM hoặc container.
7. Thời gian `getInstanceStrong`, `nextBytes` lần đầu, `generateSeed` và `reseed`.
8. Có provider phần cứng/PKCS#11 nào đang được dùng không.

Trên VM/container mới khởi động, chất lượng và trạng thái nguồn ngẫu nhiên của host có thể ảnh hưởng thời gian khởi tạo. Đảm bảo môi trường runtime có kernel CSPRNG hoạt động và cấu hình provider được hỗ trợ.

**Không xử lý bằng cách tự seed từ clock, bỏ qua entropy initialization hoặc fallback sang Random.** Cần khắc phục nguồn entropy hoặc chọn implementation đã được phê duyệt theo security policy.

### 17.1. Tách chậm do entropy và chậm do provider

Một provider phần cứng, HSM hoặc PKCS#11 có thể có độ trễ do thiết bị, kết nối hoặc session. Chậm không nhất thiết đồng nghĩa entropy pool cạn.

Ghi provider và algorithm thực tế trước khi kết luận. Nếu provider không sẵn sàng, xử lý lỗi theo chính sách triển khai thay vì tự động chọn một provider không được phê duyệt.

## 18. Cấu hình và portability giữa các hệ điều hành

Không nên dùng một giá trị property cho mọi hệ thống mà chưa kiểm chứng.

| Môi trường | Điều cần kiểm tra |
|---|---|
| Windows | Provider native/MSCAPI, DRBG, entropy source và security properties |
| Linux | Kernel CSPRNG, `getrandom`, provider SUN/native, trạng thái boot |
| macOS | Provider JDK và nguồn entropy hệ thống |
| Container | Kernel/host, startup, entropy readiness và provider runtime |
| VM | Hypervisor/guest OS, trạng thái khởi động và nguồn entropy được cung cấp |
| HSM/PKCS#11 | Provider, thiết bị, policy, key generation và latency |

Các tên như `NativePRNG`, `NativePRNGBlocking`, `NativePRNGNonBlocking`, `Windows-PRNG` hoặc `DRBG` phụ thuộc provider. Không hard-code tên chỉ vì thấy nó trong output của một máy.

### 18.1. Không áp dụng máy móc mẹo `/dev/random` và `/dev/urandom` cũ

Các bài hướng dẫn cũ đôi khi khuyên đổi `securerandom.source` hoặc truyền một JVM flag để tránh block. Những hướng dẫn đó có thể phụ thuộc phiên bản JDK, kernel và provider.

Trên Linux hiện đại, kernel CSPRNG và `getrandom()` có semantics cụ thể; `/dev/urandom` không nên bị mô tả đơn giản là “không an toàn”, và `/dev/random` không phải lựa chọn luôn cần thiết cho mọi ứng dụng.

Hãy dựa trên tài liệu JDK/provider và Linux man-pages hiện hành, không copy cấu hình từ một bài blog cũ sang production.

### 18.2. `securerandom.source` không phải đường dẫn portable

Một giá trị kiểu `file:/dev/random` là đường dẫn đặc thù Unix-like. Windows không có cùng filesystem path. Provider có thể bỏ qua hoặc diễn giải nguồn entropy theo cách riêng.

Không đổi property này nếu không biết implementation nào đang đọc nó và thay đổi ảnh hưởng đến algorithm nào.

## 19. Các API và mốc phiên bản

| API | Có từ | Ghi chú |
|---|---:|---|
| `SecureRandom()` | Java 1.1 | Default SecureRandom implementation |
| `SecureRandom.getInstance(...)` | Java 1.2 | Chọn algorithm/provider cụ thể |
| `SecureRandom.getInstanceStrong()` | **Java 8** | Chọn theo `securerandom.strongAlgorithms` |
| `SecureRandom.nextBytes(byte[])` | Java 1.1 | Sinh byte ngẫu nhiên |
| `SecureRandom.generateSeed(int)` | Java 1.2 | Sinh seed bytes |
| `Security.getProperty(...)` | Java 1.2 | Đọc security properties |
| `DrbgParameters` | **Java 9** | Tham số instantiate/generate/reseed DRBG |
| `SecureRandom.getParameters()` | **Java 9** | Đọc effective parameters |
| `SecureRandom.reseed()` | **Java 9** | Yêu cầu reseed |
| `nextBytes(byte[], SecureRandomParameters)` | **Java 9** | Sinh byte với tham số bổ sung |

**Nếu project chỉ chạy Java 8:** dùng `getInstanceStrong`, `nextBytes`, `getAlgorithm`, `getProvider`, `Security.getProperty`. Không dùng `DrbgParameters`, `getParameters()` hoặc `reseed()` trong source Java 8.

**Nếu project chạy Java 9+:** có thể yêu cầu DRBG và tham số rõ ràng, nhưng vẫn phải kiểm tra provider hỗ trợ.

## 20. Những lỗi bảo mật thường gặp

1. **Dùng `Random` cho token bí mật.** Random thông thường không phải CSPRNG.
2. **Dùng `ThreadLocalRandom` cho session ID hoặc reset token.** Nó phục vụ concurrency/performance, không phải cryptographic randomness.
3. **Nghĩ `getInstanceStrong()` là tên algorithm.** Nó là factory method chọn theo security property.
4. **Nghĩ mọi OS đều chọn cùng provider.** Algorithm/provider phụ thuộc runtime.
5. **Nghĩ `getInstanceStrong()` tự yêu cầu 256 bit.** Nó không có tham số strength.
6. **Nghĩ strong luôn đồng nghĩa non-blocking.** Một implementation có thể chờ entropy.
7. **Chỉ đo thời gian tạo object.** Lazy seeding có thể xảy ra ở lần `nextBytes` đầu.
8. **Gọi `setSeed(System.nanoTime())`.** Đây là seed dễ đoán.
9. **Gọi `setSeed(long)` trước `nextBytes` mà không có seed entropy đủ mạnh.** Việc này có thể ngăn self-seeding tự động.
10. **Dùng `new SecureRandom(constantSeed)`.** Seed cố định không phù hợp cho secret production.
11. **Dùng `generateSeed` để tạo mọi token.** `nextBytes` là API phù hợp để sinh byte dùng trực tiếp.
12. **Gọi `reseed()` trên mọi request.** Không có lợi ích chung và có thể tăng latency.
13. **Sửa `securerandom.source` để chữa chậm mà không xác định provider.** Có thể không tác động implementation đang dùng.
14. **Dùng `System.getProperty` để đọc security property.** Phải dùng `Security.getProperty`.
15. **Hard-code provider từ một máy dev.** Có thể làm hỏng portability hoặc bỏ qua provider được quản trị.
16. **Tự fallback sang Random khi `getInstanceStrong()` lỗi.** Có thể biến lỗi cấu hình bảo mật thành lỗ hổng.
17. **Tưởng `DRBG` mặc định luôn có prediction resistance.** Cần kiểm tra effective capability và yêu cầu đúng khi sinh.
18. **Tưởng `getInstanceStrong()` và `getInstance("DRBG")` tương đương.** Chúng chọn implementation theo hai cách khác nhau.
19. **Tự tạo entropy bằng cách ghép timestamp, PID, UUID và counter.** Nhiều giá trị dễ đoán không tạo seed mạnh.
20. **In token/seed ra log.** Có thể làm lộ credential.
21. **Kiểm thử output cố định.** SecureRandom không phải generator deterministic cho expected value.
22. **Dùng `% bound` để chọn ký tự.** Có thể tạo modulo bias và index sai với số âm.
23. **Tạo SecureRandom mới trong mọi vòng lặp.** Có thể lặp chi phí khởi tạo và seeding.
24. **Cho rằng thread-safe đồng nghĩa zero-cost.** Vẫn cần đo hiệu năng và latency.
25. **Tự coi một test thống kê ngắn là bằng chứng RNG an toàn.** Cần tin cậy thuật toán/provider/entropy configuration.
26. **Tưởng 32 byte output là 256 bit entropy vật lý.** Output của DRBG không đồng nghĩa từng byte mới lấy trực tiếp từ entropy source.
27. **Đổi property toàn JVM theo request.** Security properties có phạm vi toàn cục và ảnh hưởng các thành phần khác.
28. **Chọn thuật toán theo tên nghe mạnh mà không đọc tài liệu provider.** Cần hiểu semantics và môi trường.
29. **Tự thêm provider không rõ nguồn gốc.** Provider là một phần của trusted computing base.
30. **Tuyên bố FIPS compliance chỉ vì gọi getInstanceStrong.** Cần module/provider đã được xác nhận và cấu hình phù hợp tiêu chuẩn.

## 21. Checklist production

- [ ] Đã xác định loại dữ liệu ngẫu nhiên có dùng cho mục đích mật mã hay không.
- [ ] Không dùng `Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc `Math.random()` cho secret.
- [ ] Chọn `getInstanceStrong()` khi policy yêu cầu implementation strong theo platform.
- [ ] Ghi nhận algorithm và provider thực tế.
- [ ] Kiểm tra `securerandom.strongAlgorithms`.
- [ ] Kiểm tra `securerandom.drbg.config` nếu dùng DRBG SUN.
- [ ] Kiểm tra `securerandom.source` theo provider/OS đang chạy.
- [ ] Không copy property từ máy khác mà không đánh giá.
- [ ] Không tự seed bằng timestamp, counter, PID hoặc seed cố định.
- [ ] Dùng `nextBytes()` cho byte token/secret.
- [ ] Dùng `nextInt(bound)` thay vì modulo thủ công.
- [ ] Nếu dùng DRBG parameters, kiểm tra effective strength/capability.
- [ ] Không giả định prediction resistance được bật nếu chưa yêu cầu và xác minh.
- [ ] Có kiểm thử provider không hỗ trợ yêu cầu.
- [ ] Đo riêng khởi tạo và lần sinh đầu tiên nếu startup latency quan trọng.
- [ ] Không fallback sang RNG yếu khi cấu hình bảo mật thất bại.
- [ ] Tái sử dụng SecureRandom phù hợp; class thread-safe.
- [ ] Không log seed, token hoặc private bytes.
- [ ] Test format/length thay vì test output ngẫu nhiên cố định.
- [ ] Môi trường CI/VM/container có OS CSPRNG sẵn sàng.
- [ ] Nếu có compliance requirement, dùng provider/module được phê duyệt riêng.

## 22. Bài tập thực hành

### Bài 1 — Quan sát implementation strong

Chạy `SecureRandom.getInstanceStrong()`, in `getAlgorithm()` và `getProvider().getName()`. Chạy trên Windows và Linux. Vì sao output khác nhau?

### Bài 2 — Đọc security properties

Viết chương trình in ba property `securerandom.strongAlgorithms`, `securerandom.drbg.config` và `securerandom.source`. Vì sao cần dùng `Security.getProperty`?

### Bài 3 — Sinh token

Tạo 32 byte bằng `nextBytes`, encode bằng Base64 URL-safe không padding. Vì sao token dài 43 ký tự?

### Bài 4 — So sánh default và strong

Khởi tạo `new SecureRandom()` và `SecureRandom.getInstanceStrong()`. In algorithm/provider. Vì sao không thể kết luận default SecureRandom không an toàn chỉ từ tên method?

### Bài 5 — Seed dễ đoán

Giải thích điều gì có thể xảy ra nếu gọi `setSeed(System.currentTimeMillis())` trước lần `nextBytes()` đầu tiên. Vì sao method này không phải “bổ sung thêm bảo mật”?

### Bài 6 — DRBG 256 bit

Dùng `DrbgParameters.instantiation(256, PR_AND_RESEED, personalization)`. Kiểm tra effective strength và capability. Nếu provider không hỗ trợ, hệ thống nên làm gì?

### Bài 7 — Prediction resistance

Tạo DRBG hỗ trợ PR. Gọi `nextBytes(..., DrbgParameters.nextBytes(-1, true, null))`. Khác gì so với `nextBytes(byte[])` thông thường?

### Bài 8 — Blocking

Đo thời gian khởi tạo instance và lần `nextBytes()` đầu. Tại sao cần tách hai phép đo?

### Bài 9 — Modulo bias

Viết hai cách chọn ký tự từ alphabet: `nextInt(length)` và `nextInt() % length`. Giải thích vì sao cách đầu đúng hơn.

### Bài 10 — Unit test

Thiết kế unit test cho service tạo token mà không assert giá trị token cụ thể. Tách phần format test khỏi kiểm tra generator/provider.

### Bài 11 — Cấu hình source

Đọc tài liệu JDK hiện tại và giải thích vai trò của `securerandom.source`. Vì sao không được áp dụng đường dẫn `/dev/random` cho mọi OS?

### Bài 12 — Compliance

Nếu ứng dụng phải tuân thủ FIPS, hãy liệt kê thông tin cần xác minh về provider/module, chế độ hoạt động, algorithm và cấu hình triển khai. Vì sao `getInstanceStrong()` riêng lẻ chưa đủ chứng minh compliance?

## 23. Câu hỏi ôn tập và đáp án

**1. `SecureRandom` dùng để làm gì?** — Tạo dữ liệu ngẫu nhiên có tính chất mật mã.

**2. `getInstanceStrong()` có từ Java nào?** — Java 8.

**3. `getInstanceStrong()` chọn theo property nào?** — `securerandom.strongAlgorithms`.

**4. `getInstanceStrong()` có phải tên algorithm không?** — Không, là factory method.

**5. Mỗi Java SE implementation phải hỗ trợ gì?** — Ít nhất một strong SecureRandom implementation.

**6. Vì sao algorithm/provider có thể khác giữa OS?** — Provider và security configuration khác nhau.

**7. `Security.getProperty` dùng để làm gì?** — Đọc security properties.

**8. `securerandom.drbg.config` điều khiển gì?** — Cấu hình DRBG của provider hỗ trợ property này, ví dụ SUN.

**9. `securerandom.source` điều khiển gì?** — Nguồn entropy hệ thống mặc định cho một số implementation, như SUN DRBG.

**10. DRBG là gì?** — Deterministic Random Bit Generator, sinh output giả ngẫu nhiên từ seed.

**11. Mọi byte DRBG có phải entropy vật lý mới không?** — Không.

**12. `nextBytes` dùng để làm gì?** — Sinh byte ngẫu nhiên cho ứng dụng.

**13. `generateSeed` thường dùng cho gì?** — Lấy seed bytes để seed RNG khác.

**14. Có cần gọi `setSeed(System.nanoTime())` không?** — Không.

**15. `setSeed` trước lần `nextBytes` đầu có ảnh hưởng gì?** — Có thể ngăn self-seeding tự động; caller phải cung cấp seed đủ entropy.

**16. DRBG và DrbgParameters có từ Java nào?** — Java 9.

**17. `getParameters()` trả gì?** — Effective parameters nếu implementation hỗ trợ; có thể null với implementation không cung cấp parameters.

**18. `PR_AND_RESEED` có nghĩa gì?** — Yêu cầu hỗ trợ prediction resistance và reseeding.

**19. Làm sao yêu cầu prediction resistance cho lần sinh?** — Dùng `nextBytes(bytes, DrbgParameters.nextBytes(-1, true, additionalInput))`.

**20. `SecureRandom` có thread-safe không?** — Có, theo hợp đồng API.

**21. Có nên tạo một instance mới cho mỗi token không?** — Thường không; tái sử dụng instance phù hợp.

**22. Có thể block ở đâu?** — Tùy implementation, `generateSeed`, `reseed` hoặc `nextBytes` có thể block khi thu thập entropy.

**23. Có nên fallback sang Random nếu getInstanceStrong lỗi?** — Không, nếu nghiệp vụ yêu cầu strong randomness.

**24. 32 byte ngẫu nhiên encode Base64 URL-safe không padding dài bao nhiêu?** — 43 ký tự.

**25. Có nên in token vào log không?** — Không.

**26. Có nên dùng `nextInt() % bound` không?** — Không; dùng `nextInt(bound)` để tránh modulo bias.

**27. `getInstanceStrong()` có tự bảo đảm FIPS compliance không?** — Không; cần provider/module và cấu hình được xác nhận.

**28. Có nên đổi `securerandom.source` chỉ để tăng tốc mà không hiểu provider không?** — Không.

**29. Nên kiểm thử SecureRandom bằng output cố định không?** — Không; test contract, length, format, provider policy và lỗi.

**30. Nguồn entropy và DRBG khác nhau thế nào?** — Nguồn entropy cung cấp seed khó đoán; DRBG dùng seed đó để sinh output mật mã.

## 24. Tổng kết

**`SecureRandom.getInstanceStrong()` là cách lấy implementation SecureRandom theo danh sách strong do JDK/provider cấu hình.** Nó hữu ích cho dữ liệu mật mã quan trọng, nhưng không thay thế việc hiểu provider, entropy source, DRBG và yêu cầu triển khai.

Những điều cần nhớ:

- `SecureRandom` là API dành cho random mật mã; không thay bằng `Random`, `ThreadLocalRandom` hoặc `SplittableRandom`.
- `getInstanceStrong()` có từ Java 8 và chọn theo `securerandom.strongAlgorithms`.
- Algorithm/provider được chọn có thể khác theo OS, JDK vendor và security properties.
- `securerandom.strongAlgorithms`, `securerandom.drbg.config` và `securerandom.source` có vai trò khác nhau.
- Entropy source cung cấp seed; DRBG dùng seed để sinh output. Output byte không đồng nghĩa từng byte entropy vật lý mới.
- `nextBytes()` dùng để sinh byte cho ứng dụng; `generateSeed()` dùng cho seed material.
- Không tự seed bằng clock, PID, counter hoặc constant.
- DRBG parameters từ Java 9 cho phép yêu cầu strength/capability; phải kiểm tra effective parameters.
- Một số implementation có thể block trong lần seed/generate/reseed đầu; đo riêng latency và kiểm tra OS entropy readiness.
- SecureRandom thread-safe; tái sử dụng instance hợp lý.
- Không fallback âm thầm sang RNG yếu, không log token và không tự nhận compliance từ tên API.
- Kiểm thử contract và format, không yêu cầu output random phải giống nhau.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — SecureRandom: getInstanceStrong, nextBytes, generateSeed, reseed và thread safety](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html)
- [Oracle Java SE 26 — Security: getProperty, setProperty và security properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html)
- [Oracle Java SE 26 — DrbgParameters: strength, capability, personalization và DRBG behavior](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/DrbgParameters.html)
- [Oracle Java SE 26 — DrbgParameters.Instantiation: effective strength/capability](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/DrbgParameters.Instantiation.html)
- [Oracle Java SE 26 — Security Developer’s Guide: SecureRandom, provider, strongAlgorithms và DRBG configuration](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf)
- [NIST SP 800-90A Rev. 1 — Recommendation for Random Number Generation Using DRBGs](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final)
- [NIST SP 800-90B — Recommendation for the Entropy Sources Used for Random Bit Generation](https://csrc.nist.gov/pubs/sp/800/90/b/final)
- [NIST SP 800-90C — Recommendation for Random Bit Generator Constructions, Final 2025](https://csrc.nist.gov/pubs/sp/800/90/c/final)
- [Linux man-pages — random(7): kernel CSPRNG, /dev/urandom, /dev/random và getrandom](https://man7.org/linux/man-pages/man7/random.7.html)

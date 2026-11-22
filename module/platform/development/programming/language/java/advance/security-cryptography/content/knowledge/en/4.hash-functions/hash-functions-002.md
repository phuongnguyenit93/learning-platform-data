# 4.2 MessageDigest với SHA-2, SHA-3 và việc kiểm tra khả năng hỗ trợ

## Mục tiêu học tập

Sau bài này, bạn có thể: sử dụng `java.security.MessageDigest` để băm một mảng byte hoặc luồng dữ liệu; phân biệt SHA-2 với SHA-3 và chọn đúng **tên thuật toán chuẩn trong Java**; kiểm tra thuật toán có thực sự hoạt động trên JVM/provider mục tiêu; đọc và xử lý `NoSuchAlgorithmException`; và tránh các lỗi bảo mật như coi digest là bằng chứng xác thực hoặc băm mật khẩu trực tiếp.

Đây là bài về **hàm băm mật mã (cryptographic hash)** trong kiến trúc JCA, không phải mã hóa/giải mã. Với cùng một chuỗi byte đầu vào và cùng thuật toán, đầu ra băm là xác định; dữ liệu đầu vào dài tùy ý tạo ra digest có độ dài cố định. Thay đổi dữ liệu đầu vào thường làm digest thay đổi mạnh, nhưng **digest không thể dùng để khôi phục plaintext** và cũng không thể tự chứng minh ai là người gửi dữ liệu.

## 1. SHA-2 và SHA-3: cùng mục tiêu, khác thuật toán

Cả SHA-2 (chuẩn FIPS 180-4) và SHA-3 (chuẩn FIPS 202) đều là các họ hàm băm mật mã. SHA-2 dùng các cấu trúc dựa trên các hàm nén; SHA-3 dựa trên cấu trúc *sponge* của Keccak. Cùng số bit đầu ra không có nghĩa hai thuật toán cho cùng digest hoặc có thể thay thế tùy tiện trong giao thức đã triển khai.

| Họ | Tên chuẩn truyền cho `MessageDigest.getInstance(...)` | Digest (bit) | Byte | Hex ký tự |
| --- | --- | ---: | ---: | ---: |
| SHA-2 | `SHA-224` | 224 | 28 | 56 |
| SHA-2 | `SHA-256` | 256 | 32 | 64 |
| SHA-2 | `SHA-384` | 384 | 48 | 96 |
| SHA-2 | `SHA-512` | 512 | 64 | 128 |
| SHA-2 | `SHA-512/224` | 224 | 28 | 56 |
| SHA-2 | `SHA-512/256` | 256 | 32 | 64 |
| SHA-3 | `SHA3-224` | 224 | 28 | 56 |
| SHA-3 | `SHA3-256` | 256 | 32 | 64 |
| SHA-3 | `SHA3-384` | 384 | 48 | 96 |
| SHA-3 | `SHA3-512` | 512 | 64 | 128 |

**Điểm dễ nhầm:**

- `SHA-256` thuộc **SHA-2**, còn `SHA3-256` thuộc **SHA-3**. Hai giá trị băm đều 256 bit, nhưng **khác nhau đối với cùng dữ liệu**. Một hệ thống đã dùng SHA-256 không thể tự đổi thành SHA3-256 khi verify dữ liệu cũ.
- `SHA-512/256` là **một biến thể SHA-2 được xác định riêng** (có giá trị khởi tạo riêng), không tương đương với lấy 32 byte đầu của kết quả `SHA-512`.
- `SHA3-256` là tên SHA-3 được chuẩn hóa theo FIPS 202; không coi các đầu ra có nhãn `Keccak-256` ở thư viện khác là tương thích mặc định vì quy ước padding/domain separation có thể khác.
- `SHA-1` **không** thuộc họ SHA-2 và đã không phù hợp cho các ứng dụng mới cần chống va chạm. `MD5` cũng không nên dùng để bảo vệ tính toàn vẹn trước đối thủ chủ động.

Tên trên là các **standard algorithm names** của Java SE 17; chúng mô tả cách đặt tên, không bảo đảm **mọi provider** đều cài mọi biến thể. Thực tế khả dụng phụ thuộc bản JDK, provider đã đăng ký và cấu hình runtime. Đặc biệt, đừng giả định SHA3 luôn có ở mọi bản phân phối hoặc mọi provider.

### Đầu vào/đầu ra thực chất là byte

`MessageDigest` xử lý `byte[]`/`ByteBuffer` hoặc các phần byte được truyền qua `update`; nó không biết JSON, Unicode, tệp hay nội dung giao thức. Bạn phải quy định cách chuyển **chính xác** dữ liệu thành byte: ví dụ `"abc".getBytes(StandardCharsets.UTF_8)`. UTF-8 của các ký tự, dấu xuống dòng `LF`/`CRLF`, khoảng trắng, thứ tự trường JSON hoặc Unicode normalization khác nhau có thể tạo digest khác nhau dù người đọc thấy văn bản gần giống nhau.

Giá trị trả về là `byte[]`, không phải chuỗi hex. Hex chỉ là cách **biểu diễn**: mỗi byte được viết thành hai ký tự hex. Java 17 có `HexFormat.of().formatHex(digestBytes)` để in ổn định.

## 2. Vòng đời của `MessageDigest`

Bốn thao tác cốt lõi:

1. **Chọn engine/thuật toán:** `MessageDigest.getInstance("SHA-256")` yêu cầu một provider triển khai dịch vụ JCA có loại `MessageDigest` và tên `SHA-256`.
2. **Nạp dữ liệu:** `update(byte[])`, `update(byte[], offset, length)` hoặc `update(ByteBuffer)` có thể gọi nhiều lần, theo đúng thứ tự các byte. Có thể thay bằng `digest(byte[])` nếu toàn bộ nội dung đã ở trong mảng.
3. **Kết thúc phép băm:** `digest()` xử lý toàn bộ các byte đã `update` rồi trả về `byte[]`; `digest(byte[])` đồng thời xử lý mảng byte đó. Hai cách cho cùng kết quả nếu chuỗi byte giống nhau.
4. **Trạng thái sau khi kết thúc:** sau một lần `digest()`, đối tượng `MessageDigest` được reset để có thể tính digest mới. Gọi `digest()` tiếp mà không nạp lại dữ liệu sẽ băm **chuỗi rỗng**, không lặp lại kết quả cũ.

Mã minh họa **đặt bên trong phương thức có xử lý `NoSuchAlgorithmException`**:

```java
byte[] input = "abc".getBytes(StandardCharsets.UTF_8);

// Một lần: truyền toàn bộ byte.
byte[] whole = MessageDigest.getInstance("SHA-256").digest(input);

// Nhiều phần: thứ tự và các byte ghép lại phải giống nhau.
MessageDigest md = MessageDigest.getInstance("SHA-256");
md.update((byte) 'a');
md.update("bc".getBytes(StandardCharsets.UTF_8));
byte[] parts = md.digest();

boolean equal = MessageDigest.isEqual(whole, parts); // true
```

Đoạn trên chỉ là một phần chương trình; import cần `java.security.MessageDigest` và `java.nio.charset.StandardCharsets`. Đối tượng `MessageDigest` có trạng thái thay đổi qua `update` nên **không chia sẻ một instance cho nhiều luồng đồng thời** nếu không có cơ chế đồng bộ phù hợp. Cách đơn giản là tạo instance riêng cho từng tác vụ. `getDigestLength()` thường cho số byte đầu ra, nhưng theo API có thể trả `0` nếu provider không xác định được; `digest().length` là độ dài thực tế của kết quả đã tính.

## 3. Chương trình Java 17 chạy được: SHA-2, SHA-3 và hỗ trợ theo provider

Tạo đúng tệp **`HashFamiliesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;
import java.util.List;

public final class HashFamiliesDemo {
    public static void main(String[] args) throws Exception {
        byte[] abc = "abc".getBytes(StandardCharsets.UTF_8);

        for (String algorithm : List.of(
                "SHA-256", "SHA-512/256", "SHA3-256", "SHA3-512")) {
            try {
                MessageDigest digest = MessageDigest.getInstance(algorithm);
                byte[] bytes = digest.digest(abc);
                System.out.printf("%-11s bits=%3d provider=%s%n",
                        algorithm, bytes.length * 8, digest.getProvider().getName());
                if (algorithm.equals("SHA-256") || algorithm.equals("SHA3-256")) {
                    System.out.println("  abc=" + HexFormat.of().formatHex(bytes));
                }
            } catch (NoSuchAlgorithmException e) {
                System.out.println(algorithm + " unsupported");
            }
        }

        MessageDigest incremental = MessageDigest.getInstance("SHA-256");
        incremental.update((byte) 'a');
        incremental.update("bc".getBytes(StandardCharsets.UTF_8));
        byte[] chunked = incremental.digest();
        byte[] oneShot = MessageDigest.getInstance("SHA-256").digest(abc);
        System.out.println("SHA-256 one-shot == incremental: "
                + MessageDigest.isEqual(oneShot, chunked));

        System.out.println("MessageDigest names advertised: "
                + Security.getAlgorithms("MessageDigest").size());
        System.out.println("Providers registering SHA3-256:");
        boolean found = false;
        for (Provider provider : Security.getProviders()) {
            Provider.Service service = provider.getService("MessageDigest", "SHA3-256");
            if (service == null) {
                continue;
            }
            found = true;
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA3-256", provider);
                System.out.printf("  %s -> %s (%d bits)%n",
                        provider.getName(), service.getAlgorithm(),
                        digest.digest(abc).length * 8);
            } catch (NoSuchAlgorithmException e) {
                System.out.println("  " + provider.getName()
                        + ": registered but unavailable");
            }
        }
        if (!found) {
            System.out.println("  none");
        }

        if (args.length > 0) {
            byte[] fileHash = hashFile(Path.of(args[0]), "SHA-256");
            System.out.println("SHA-256(file)=" + HexFormat.of().formatHex(fileHash));
        }
    }

    private static byte[] hashFile(Path file, String algorithm)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance(algorithm);
        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
        }
        return digest.digest();
    }
}
```

Biên dịch/run bằng JDK 17 trở lên (ví dụ mã đã kiểm bằng `javac --release 17`):

```bash
javac --release 17 HashFamiliesDemo.java
java HashFamiliesDemo
```

Một lần chạy trên JVM có provider `SUN` cho các thuật toán được thử cho kết quả:

```text
SHA-256     bits=256 provider=SUN
  abc=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
SHA-512/256 bits=256 provider=SUN
SHA3-256    bits=256 provider=SUN
  abc=3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532
SHA3-512    bits=512 provider=SUN
SHA-256 one-shot == incremental: true
MessageDigest names advertised: 13
Providers registering SHA3-256:
  SUN -> SHA3-256 (256 bits)
```

Đây là **stdout thực tế của một cấu hình thử nghiệm**, không phải kết quả bắt buộc của mọi máy. Tên provider, tổng số tên đăng ký, số provider và những thuật toán báo `unsupported` phụ thuộc môi trường. Hai chuỗi hex nêu trên là **test vector chuẩn của dữ liệu UTF-8 `abc`**; nếu có implementation SHA-256/SHA3-256 tuân thủ chuẩn, hai digest này phải trùng.

Khi chạy với đối số là đường dẫn tệp, ví dụ:

```bash
java HashFamiliesDemo document.bin
```

chương trình còn in `SHA-256(file)=...` cho **toàn bộ các byte** của tệp `document.bin`. Tệp phải tồn tại; đây là thao tác tùy chọn khi người học cung cấp tệp thật. Không có dòng kết quả cố định cho tệp bất kỳ vì nó phụ thuộc vào nội dung tệp.

### Vì sao cách băm tệp an toàn về bộ nhớ?

Hàm `hashFile` đọc tối đa một buffer 8 KiB cho mỗi vòng lặp rồi gọi `update(buffer, 0, count)`. Nó không cần giữ toàn bộ tệp trong RAM. Dùng **đúng `count` byte đã đọc** là quan trọng: `update(buffer)` sẽ đưa cả phần byte cũ còn sót trong buffer vào digest khi lần đọc cuối có ít hơn 8192 byte. Độ dài buffer có thể thay đổi mà không đổi giá trị digest miễn chuỗi byte đầu vào giữ nguyên.

Chú ý: hàm băm đọc nội dung tệp tại thời điểm mở/đọc. Nếu có tiến trình khác sửa tệp trong lúc băm, digest thu được không nhất thiết đại diện cho một snapshot nhất quán; tùy yêu cầu, cần đóng băng nguồn/kiểm tra metadata hoặc dùng cơ chế lưu trữ có snapshot.

## 4. Kiểm tra khả năng hỗ trợ: ba lớp bằng chứng

### 4.1 Tên chuẩn của Java

Tài liệu **Java Security Standard Algorithm Names** liệt kê những tên như `SHA-256`, `SHA-512/256`, `SHA3-256`. Dùng đúng tên chuẩn để giảm phụ thuộc alias riêng của provider. Đừng coi tên chuẩn tồn tại trong tài liệu là bằng chứng rằng JVM đang chạy đã cài provider cung cấp nó.

### 4.2 Danh sách thuật toán được đăng ký

`Security.getAlgorithms("MessageDigest")` trả về tập các tên thuật toán được những provider đăng ký cho engine `MessageDigest` tại thời điểm gọi. Ví dụ đoạn sau **không phải chương trình độc lập**:

```java
Set<String> names = Security.getAlgorithms("MessageDigest");
names.stream().sorted(String.CASE_INSENSITIVE_ORDER).forEach(System.out::println);
```

Cần import `java.security.Security` và `java.util.Set`. Đây là công cụ **khám phá** runtime; không dùng thứ tự/tên và số lượng trả về làm hợp đồng portable giữa nhiều JVM. Việc xuất hiện tên trong danh sách đăng ký chưa chứng minh một instance khởi tạo và tính digest thành công.

### 4.3 Kiểm tra provider cụ thể rồi thực hiện digest

`Security.getProviders()` liệt kê các provider đã đăng ký. Dùng:

- `provider.getService("MessageDigest", "SHA3-256")` để xem provider đó **công bố** dịch vụ thích hợp (có thể nhận tên chính hoặc alias đã đăng ký). `null` là không tìm thấy service với tên được yêu cầu ở provider đó.
- `MessageDigest.getInstance("SHA3-256", provider)` để yêu cầu **chính provider đó** tạo implementation. Nếu thành công, kiểm tra thêm kết quả `digest` bằng vector chuẩn.
- `digest.getProvider().getName()` để xác định provider của instance đã tạo khi dùng overload **không** chỉ định provider.
- `Security.getProviders("MessageDigest.SHA3-256")` là một filter khác cho các provider phù hợp; API có thể trả `null` nếu không tìm được, nên phải kiểm tra null trước khi duyệt.

Khi gọi `MessageDigest.getInstance("SHA3-256")` **không truyền provider**, JCA chọn trong tập provider đã đăng ký theo cơ chế lựa chọn của runtime. JDK Reference Implementation còn có cấu hình ưu tiên theo thuật toán; đừng suy ra chắc chắn lựa chọn cuối chỉ từ vị trí trong `Security.getProviders()`.

| Mức kiểm tra | API | Có thể kết luận |
| --- | --- | --- |
| Tên chuẩn | Standard Algorithm Names | Tên hợp lệ theo tiêu chuẩn đặt tên |
| Đăng ký chung | `Security.getAlgorithms("MessageDigest")` | Runtime quảng bá tên cho engine hiện tại |
| Đăng ký từng provider | `provider.getService(type, name)` | Provider quảng bá một dịch vụ phù hợp |
| Tạo implementation | `MessageDigest.getInstance(name, provider)` | Provider tạo được instance khi thử |
| Hoạt động chính xác | `digest(input)` và so test vector | Implementation đã tạo tính đúng với dữ liệu thử nghiệm |

Nếu provider cung cấp alias như `SHA256` cho `SHA-256`, alias đó **không bắt buộc** phải tồn tại trong provider khác. Dùng tên chuẩn `SHA-256` cho API công khai/trường dữ liệu hệ thống, đồng thời ghi rõ tên thuật toán cùng digest khi trao đổi giữa các dịch vụ: cả hai bên phải dùng đúng cùng một họ và biến thể.

## 5. Chính sách ứng dụng khi thuật toán không có sẵn

`MessageDigest.getInstance("SHA3-256")` có thể ném `NoSuchAlgorithmException` nếu không provider nào cung cấp dịch vụ. Khi thuật toán là một phần của giao thức, chữ ký dữ liệu, kiểm tra checksum hay định dạng file, **hãy fail fast và báo thiếu capability** hoặc triển khai provider đã được phê duyệt. **Không tự fallback** `SHA3-256` → `SHA-256` chỉ vì hai digest đều dài 256 bit, hoặc SHA-256 → MD5/SHA-1 để “chạy cho được”: cả hai thay đổi hợp đồng dữ liệu, và fallback yếu còn làm giảm bảo mật.

Một cách tổ chức kiểm tra ở startup là đặt tên yêu cầu trong cấu hình rõ ràng:

```java
static MessageDigest requireDigest(String standardName) {
    try {
        return MessageDigest.getInstance(standardName);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException(
                "Required MessageDigest unavailable: " + standardName, e);
    }
}
```

Đoạn trên là phương thức minh họa để chèn vào một class Java có import `MessageDigest` và `NoSuchAlgorithmException`. Chọn/chấp nhận provider theo chính sách deployment. Khi yêu cầu tuân thủ FIPS hoặc provider phần cứng, kiểm tra và chỉ định đúng provider được phép; một instance “tồn tại” trong JVM không tự chứng minh môi trường đạt yêu cầu tuân thủ.

Nếu sản phẩm **thực sự hỗ trợ nhiều lựa chọn** theo một giao thức có thương lượng, cần đưa algorithm identifier vào metadata, ràng buộc danh sách cho phép ở hai phía và kiểm tra digest theo đúng thuật toán được thỏa thuận. Không dựa vào độ dài digest để đoán thuật toán.

## 6. Tính toàn vẹn, xác thực và so sánh digest

Giả sử bạn lưu SHA-256 của một bản phát hành, rồi kiểm tra bản tải về. Khi digest khớp, bạn có bằng chứng byte tải về giống **nội dung gắn với digest mà bạn đang tin cậy**, với giới hạn bảo mật của thuật toán. Nhưng nếu đối thủ có thể thay **cả tệp lẫn digest công bố**, digest thuần không chứng minh nguồn gốc và không bảo vệ khỏi giả mạo.

- Để kiểm tra dữ liệu bị thay đổi vô ý hoặc so khớp với digest đã xác thực từ kênh tin cậy: `MessageDigest` phù hợp.
- Để **xác thực thông điệp** bằng khóa bí mật: dùng engine `Mac` như `HmacSHA256` với quản lý khóa đúng; không tự tạo “MAC” bằng cách nối chuỗi bí mật và dữ liệu rồi gọi `SHA-256`.
- Để **xác thực nguồn gốc bằng khóa bất đối xứng**: dùng `Signature` với thuật toán/mode thích hợp và kiểm tra khóa công khai được tin cậy.
- Để lưu mật khẩu: **không dùng SHA-256/SHA3-256 trực tiếp** dù thêm salt; sử dụng cơ chế password-hashing chuyên dụng có salt riêng, chi phí tính toán phù hợp (ví dụ Argon2id, scrypt, bcrypt hoặc PBKDF2 theo yêu cầu hệ thống).

So hai mảng byte digest bằng `MessageDigest.isEqual(expected, actual)` thay vì kiểm tra reference với `==`. Phương thức hỗ trợ so sánh nội dung byte; nó **không biến digest không khóa thành chữ ký/MAC** và không giải quyết vấn đề tin cậy đối với digest mong đợi. Không tự chuyển digest sang `String` bằng charset text; dùng `HexFormat` hoặc Base64 khi cần lưu/trao đổi.

## 7. Lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Khả năng gây ra và cách sửa |
| --- | --- |
| `NoSuchAlgorithmException: SHA3-256` | Provider trong runtime hiện tại không cung cấp tên được yêu cầu; kiểm tra tên chuẩn, `Security.getProviders()` và thử `getInstance` theo từng provider |
| `SHA3_256` hoặc `SHA-3-256` không nhận | Sai tên chuẩn; trong JCA dùng `SHA3-256` (không gạch nối giữa `SHA` và `3`) |
| Hai chương trình băm “cùng text” ra hai chuỗi hex khác nhau | So lại **byte** UTF-8, newline, BOM, Unicode normalization, ký tự khoảng trắng và cùng tên thuật toán |
| `SHA-512/256` không trùng với 256 bit đầu của `SHA-512` | Đây là hai thuật toán khác nhau; `SHA-512/256` có đặc tả riêng |
| Băm một file lớn bị thiếu bộ nhớ | Chuyển từ `Files.readAllBytes` sang streaming `InputStream` + `update` theo buffer |
| Kết quả băm lần thứ hai bất ngờ | `digest()` reset trạng thái; phải nạp lại dữ liệu cho lần mới. Không chia sẻ instance có trạng thái giữa các thread |
| Nhìn thấy `SHA3-256` trong danh sách nhưng `getInstance` thất bại | Thông tin quảng bá chưa chắc chứng minh khởi tạo thành công; thử đúng overload với provider và kiểm tra ngoại lệ |
| Hash khớp nhưng vẫn không tin nguồn gửi | Digest không có khóa không cung cấp authentication; xác thực digest qua kênh đáng tin hoặc dùng MAC/chữ ký |

### Kiểm tra trước khi đưa vào production

1. Xác nhận thuật toán yêu cầu bằng **tên chuẩn**, khả năng hỗ trợ trong đúng JVM/container và chính sách provider cần dùng.
2. Chuẩn hóa cách biểu diễn **byte đầu vào** (charset, định dạng serialization, newline, thứ tự trường, canonicalization) cho cả phía tạo lẫn phía kiểm tra.
3. Dùng dữ liệu kiểm thử cố định: SHA-256(UTF-8 `abc`) = `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`; SHA3-256(UTF-8 `abc`) = `3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532`.
4. Với dữ liệu lớn, dùng `update` từng phần và đo bộ nhớ; giữ đúng thứ tự byte, đọc đúng số lượng byte thực nhận.
5. Khi thiếu thuật toán bắt buộc, lỗi rõ ràng tại startup hoặc điểm dùng; không đổi thuật toán một cách ngầm định.
6. Ghi/chuyển algorithm identifier cùng hash khi dữ liệu đi qua ranh giới hệ thống; nhớ rằng digest không chứng minh tính xác thực nếu nguồn digest chưa được tin cậy.

## Bài tự luyện

1. Chạy chương trình, ghi lại các tên SHA-2/SHA-3 được hỗ trợ, provider được chọn cho từng tên và tập provider quảng bá `SHA3-256`.
2. Sửa đoạn `update` thành ba lần truyền từng ký tự `a`, `b`, `c`, kiểm tra giá trị `SHA-256` có giữ nguyên không; sau đó đảo thứ tự hai phần để quan sát thay đổi digest.
3. Tạo hai tệp UTF-8 chỉ khác newline cuối cùng, chạy chương trình với từng đường dẫn. Giải thích vì sao hash khác nhau.
4. Thử `MessageDigest.getInstance("SHA3-256", provider)` với từng provider trong máy và phân biệt **“provider công bố service”** với **“instance chạy đúng test vector”**.
5. Thiết kế metadata cho hệ thống kiểm tra tệp gửi qua mạng: cần lưu hash, tên thuật toán, cách tạo byte đầu vào và **cơ chế tin cậy digest** ra sao?

## Tài liệu tham khảo

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): các tên SHA-2/SHA-3 chuẩn, kích thước digest và yêu cầu hỗ trợ.
- [Java SE 17 — `MessageDigest` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `getInstance`, `update`, `digest`, `reset` và `isEqual`.
- [Java SE 17 — `Security` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html): `getAlgorithms`, `getProviders` và lọc provider.
- [Java SE 17 — `Provider` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.html): `getService`, `getServices` và tên thuật toán provider hỗ trợ.
- [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): các biến thể SHA-2.
- [NIST FIPS 202](https://csrc.nist.gov/pubs/fips/202/final): định nghĩa SHA-3.

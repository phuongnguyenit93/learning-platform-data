# 2.1 Mô hình engine class, SPI và security provider

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao ứng dụng Java gọi một API mật mã thống nhất nhưng vẫn sử dụng được nhiều cách triển khai khác nhau.
- Phân biệt chính xác **engine class** (API ứng dụng gọi), **Service Provider Interface – SPI** (hợp đồng triển khai) và **security provider** (đơn vị đăng ký/cung cấp dịch vụ).
- Theo dõi đường đi của lời gọi `getInstance()`, hiểu vai trò của `Provider.Service` và thứ tự ưu tiên provider.
- Đọc thông tin provider thực tế, xử lý lỗi tra cứu thuật toán và nhận ra các rủi ro khi cố định provider hoặc viết SPI.

## 1. Bức tranh tổng thể của JCA

**Java Cryptography Architecture (JCA)** là kiến trúc API và cơ chế chọn triển khai các dịch vụ bảo mật trong Java: hàm băm, chữ ký số, mã hóa, sinh khóa, quản lý khóa/chứng chỉ, số ngẫu nhiên bảo mật, v.v. Các API trải trên `java.security` và `javax.crypto`; tên **JCE** thường dùng cho nhóm API mật mã mở rộng nhưng cùng sử dụng kiến trúc provider của JCA.

JCA tách câu hỏi **“ứng dụng muốn làm gì?”** khỏi **“mã nào thực hiện thuật toán?”**. Ứng dụng chọn loại dịch vụ và thuật toán; framework tìm một provider có triển khai tương ứng, sau đó tạo engine để ứng dụng sử dụng.

```text
Ứng dụng Java
    |
    | MessageDigest.getInstance("SHA-256")
    v
Engine class / API: java.security.MessageDigest
    |
    | tra cứu (service type, algorithm)
    v
Danh sách security provider / Provider.Service
    |
    | chọn triển khai phù hợp
    v
Lớp provider triển khai MessageDigestSpi
    |
    | engineUpdate(), engineDigest(), engineReset(), ...
    v
Kết quả digest trả về qua API MessageDigest
```

Sơ đồ diễn tả luồng logic. Ở một số engine (đặc biệt loại cần khóa, như `Signature`/`Cipher`), việc quyết định triển khai cụ thể có thể được trì hoãn đến khi khởi tạo với khóa hoặc tham số; không nên giả định mọi `getInstance()` đều khóa cứng provider ngay tại thời điểm gọi.

Ba lợi ích chính:

1. **Độc lập triển khai:** mã ứng dụng không cần khởi tạo lớp triển khai mật mã của từng hãng.
2. **Khả năng mở rộng:** provider mới có thể đăng ký thêm thuật toán/triển khai mà không cần thay đổi API engine.
3. **Khả năng thay thế và tích hợp:** có thể chọn provider phần mềm, provider bên thứ ba, hoặc provider kết nối thiết bị/HSM khi môi trường hỗ trợ.

## 2. Ba vai trò không được nhầm lẫn

| Thành phần | Ai sử dụng/định nghĩa? | Trách nhiệm chính | Ví dụ |
| --- | --- | --- | --- |
| **Engine class** | Lập trình viên ứng dụng sử dụng | API công khai, giữ trạng thái sử dụng và điều phối lời gọi | `MessageDigest`, `Signature`, `Cipher` |
| **SPI class** | Tác giả provider triển khai | Hợp đồng các thao tác `engine...()` mà provider phải hiện thực | `MessageDigestSpi`, `SignatureSpi`, `CipherSpi` |
| **Security provider** | Đơn vị triển khai/cấu hình và runtime JCA | Đăng ký tên dịch vụ, thuật toán, alias, lớp triển khai và thông tin provider | Một đối tượng kế thừa `java.security.Provider` |
| **Provider.Service** | Framework JCA dùng để tra cứu | Mô tả một dịch vụ cụ thể: loại engine, thuật toán, implementation class, alias, thuộc tính | `("MessageDigest", "SHA-256")` |

**Engine class** là điểm vào ổn định. Ví dụ `MessageDigest.getInstance("SHA-256")` trả về đối tượng kiểu `MessageDigest`; code chỉ gọi `update()`, `digest()`, `reset()`, không cần biết provider cài thuật toán ở lớp nào.

**SPI** thường là lớp trừu tượng có hậu tố `Spi`. Provider viết lớp kế thừa rồi triển khai các phương thức `protected engine...`. Engine chuyển yêu cầu từ API ứng dụng đến các thao tác SPI tương ứng. Chẳng hạn:

- `MessageDigest.update(byte[])` → thao tác cập nhật trên `MessageDigestSpi`.
- `MessageDigest.digest()` → `engineDigest()` của triển khai.
- `Signature.initSign(privateKey)` → logic `engineInitSign(...)` của triển khai.
- `Cipher.init(...)` và `Cipher.doFinal(...)` → các thao tác khởi tạo/xử lý của `CipherSpi`.

Một số implementation có cấu trúc lớp kế thừa đặc thù; điều cần nắm là **hợp đồng engine/SPI và cơ chế provider**, không phải giả định mọi engine đều được hiện thực bằng đúng một kiểu wrapper nội bộ.

**Provider** là đối tượng `Provider` mô tả một tập dịch vụ. Nó không đồng nghĩa với một thuật toán, một engine instance, hay nhất thiết một thư viện đơn lẻ. Một provider có thể công bố nhiều dịch vụ và chỉ hỗ trợ một phần những thuật toán JCA định nghĩa.

## 3. Nhận diện engine và SPI tương ứng

| Loại dịch vụ | Engine API | Hợp đồng SPI | Ví dụ tên thuật toán/transformation |
| --- | --- | --- | --- |
| Hàm băm | `java.security.MessageDigest` | `MessageDigestSpi` | `SHA-256` |
| Chữ ký số | `java.security.Signature` | `SignatureSpi` | `SHA256withRSA` |
| Mã hóa/giải mã | `javax.crypto.Cipher` | `CipherSpi` | `AES/GCM/NoPadding` |
| Xác thực thông điệp | `javax.crypto.Mac` | `MacSpi` | `HmacSHA256` |
| Số ngẫu nhiên bảo mật | `java.security.SecureRandom` | `SecureRandomSpi` | Tùy thuật toán/provider |
| Kho khóa | `java.security.KeyStore` | `KeyStoreSpi` | `PKCS12`, `PKCS11` (tùy provider) |

Phân biệt hai chiều thông tin:

- **Service type** là loại engine, ví dụ `MessageDigest` hoặc `Cipher`.
- **Algorithm** là tên thuật toán trong service đó, ví dụ `SHA-256` hoặc `HmacSHA256`. Riêng `Cipher` thường yêu cầu **transformation** đầy đủ `algorithm/mode/padding`, ví dụ `AES/GCM/NoPadding`.

Do đó `SHA-256` không phải provider; `MessageDigest` không phải thuật toán; `SUN`/`SunJCE` trong một số JDK là tên provider, không phải tên loại engine. Danh sách và tên provider được cài đặt phụ thuộc JDK và môi trường.

## 4. `getInstance()` chọn provider ra sao?

Ba dạng factory thông dụng (minh họa với `MessageDigest`):

```java
MessageDigest automatic = MessageDigest.getInstance("SHA-256");

// Chỉ thành công khi provider có tên này đã được đăng ký trong JVM:
MessageDigest named = MessageDigest.getInstance("SHA-256", "SUN");

// Có thể truyền trực tiếp đối tượng Provider mà không đăng ký toàn cục:
MessageDigest explicit = MessageDigest.getInstance("SHA-256", providerObject);
```

Đoạn trên là **minh họa các overload**, không phải chương trình chạy độc lập: `providerObject` phải là biến `Provider` hợp lệ; tên `SUN` chỉ có ý nghĩa trên runtime thật sự cài provider đó.

Khi không chỉ định provider, framework tra cứu các provider đã đăng ký theo **thứ tự ưu tiên** và tìm dịch vụ phù hợp với loại engine + tên thuật toán. Đối với engine cần khóa/tham số, khả năng hỗ trợ khóa cũng có thể ảnh hưởng đến provider được chọn trong bước khởi tạo. Khi bạn truyền provider theo tên hay đối tượng, lựa chọn bị giới hạn vào provider được chỉ định; nếu không có dịch vụ phù hợp, lời gọi thất bại thay vì tự động chuyển sang provider khác.

`Provider.Service` ghi nhận thông tin giúp framework tạo triển khai:

- `getType()`: loại dịch vụ, chẳng hạn `MessageDigest`.
- `getAlgorithm()`: tên thuật toán chính.
- `getProvider()`: provider sở hữu service.
- `getClassName()`: tên lớp triển khai do provider công bố.
- `getAttribute(name)`: thuộc tính tùy chọn; alias có thể ánh xạ nhiều tên về cùng một dịch vụ.

Tài liệu/API không đảm bảo mọi máy đều có cùng tập provider, thứ tự provider hoặc mọi alias. Nên ưu tiên **tên thuật toán chuẩn**, chỉ cố định provider khi có yêu cầu cụ thể đã được kiểm chứng (ví dụ thiết bị, chứng nhận hoặc khả năng tương thích).

## 5. Thực hành 1: tra cứu engine và xác định provider thực tế

Lưu chương trình sau thành **`JcaEngineLookup.java`** (Java 17 trở lên):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Provider;
import java.util.HexFormat;

public class JcaEngineLookup {
    public static void main(String[] args) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        Provider provider = digest.getProvider();
        byte[] result = digest.digest("abc".getBytes(StandardCharsets.UTF_8));

        System.out.println("SHA-256: " + HexFormat.of().formatHex(result));
        System.out.println("Provider selected: " + (provider != null));
        System.out.println("Service registered: " +
                (provider.getService("MessageDigest", "SHA-256") != null));
        System.out.println("Provider name: " + provider.getName());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 JcaEngineLookup.java
java JcaEngineLookup
```

Ba dòng đầu cho kết quả sau trên runtime có hỗ trợ SHA-256:

```text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Provider selected: true
Service registered: true
```

Dòng cuối `Provider name: ...` hiển thị **tên provider do JVM thực tế lựa chọn** (ví dụ `SUN` trên một số JDK), nên không được xem một tên cụ thể là đầu ra bất biến.

Điều cần quan sát:

1. Mã ứng dụng chỉ yêu cầu loại dịch vụ `MessageDigest` và thuật toán `SHA-256`.
2. `digest.getProvider()` cho biết provider đang cung cấp engine đó.
3. `getService("MessageDigest", "SHA-256")` kiểm tra bản ghi dịch vụ của provider; `Provider.Service` mô tả triển khai, còn `MessageDigest` là API để gọi thao tác.
4. SHA-256 của chuỗi `"abc"` là kết quả thuật toán chuẩn; provider khác tuân thủ cùng thuật toán phải cho cùng digest.

Muốn khám phá danh sách provider, có thể chạy đoạn sau trong một chương trình Java bất kỳ:

```java
for (Provider p : java.security.Security.getProviders()) {
    System.out.println(p.getName() + " / " + p.getVersionStr());
    for (Provider.Service s : p.getServices()) {
        if (s.getType().equalsIgnoreCase("MessageDigest")) {
            System.out.println("  " + s.getAlgorithm());
        }
    }
}
```

Đây là **đoạn mã nhúng**, không có `main`/import riêng. Tên, số lượng provider và thuật toán in ra thay đổi theo JVM, cấu hình bảo mật và provider được cài thêm.

## 6. Thực hành 2: tự tạo SPI và provider tối giản để thấy đường đi của API

Ví dụ dưới đây **chỉ mô phỏng cơ chế đăng ký và ủy nhiệm**, hoàn toàn **không phải thuật toán băm mật mã**. Nó cộng các byte theo modulo 2³² rồi trả về bốn byte. Kẻ tấn công có thể dễ dàng tạo va chạm; tuyệt đối không dùng cho lưu mật khẩu, chữ ký số, kiểm tra tính toàn vẹn có đối thủ, hoặc hệ thống thực tế.

Lưu thành **`JcaSpiProviderDemo.java`** (Java 17 trở lên):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.MessageDigestSpi;
import java.security.Provider;
import java.util.HexFormat;
import java.util.Objects;

public class JcaSpiProviderDemo {
    public static final class EducationalProvider extends Provider {
        public EducationalProvider() {
            super("EduProvider", "1.0", "Provider minh hoa, KHONG dung trong bao mat");

            // Đăng ký service type + algorithm -> lớp triển khai SPI.
            put("MessageDigest.EDU-CHECKSUM32", ToyDigestSpi.class.getName());
        }
    }

    public static final class ToyDigestSpi extends MessageDigestSpi {
        private int sum;

        @Override
        protected void engineUpdate(byte input) {
            sum += input & 0xff;
        }

        @Override
        protected void engineUpdate(byte[] input, int offset, int len) {
            Objects.checkFromIndexSize(offset, len, input.length);
            for (int i = offset; i < offset + len; i++) {
                engineUpdate(input[i]);
            }
        }

        @Override
        protected byte[] engineDigest() {
            int value = sum;
            engineReset();
            return new byte[] {
                (byte) (value >>> 24),
                (byte) (value >>> 16),
                (byte) (value >>> 8),
                (byte) value
            };
        }

        @Override
        protected void engineReset() {
            sum = 0;
        }

        @Override
        protected int engineGetDigestLength() {
            return 4;
        }
    }

    public static void main(String[] args) throws Exception {
        Provider provider = new EducationalProvider();

        // Provider object được dùng trực tiếp, không cần Security.addProvider().
        MessageDigest digest = MessageDigest.getInstance(
                "EDU-CHECKSUM32", provider);

        byte[] bytes = digest.digest("ABC".getBytes(StandardCharsets.US_ASCII));
        System.out.println(digest.getProvider().getName());
        System.out.println(HexFormat.of().formatHex(bytes));
        System.out.println(provider.getService(
                "MessageDigest", "EDU-CHECKSUM32") != null);
    }
}
```

Chạy:

```bash
javac --release 17 JcaSpiProviderDemo.java
java JcaSpiProviderDemo
```

Đầu ra đã được kiểm tra:

```text
EduProvider
000000c6
true
```

Giải thích theo đúng các lớp trách nhiệm:

1. `EducationalProvider` là **provider**: khai báo tên `EduProvider` và đăng ký `MessageDigest.EDU-CHECKSUM32` trỏ tới lớp SPI.
2. `ToyDigestSpi` là **implementation**: override các phương thức `engineUpdate`, `engineDigest`, `engineReset` và `engineGetDigestLength`. Các phép cộng là cơ chế checksum giả lập, không có tính an toàn mật mã.
3. `MessageDigest.getInstance(..., provider)` là **factory của engine**: thông qua thông tin provider để tạo engine dựa trên SPI đã đăng ký.
4. `digest.digest("ABC"... )` đi qua API của `MessageDigest` rồi kích hoạt SPI. Các byte ASCII `A=65`, `B=66`, `C=67` có tổng `198 = 0xC6` nên bốn byte kết quả là `00 00 00 C6`.
5. Đưa thẳng đối tượng `Provider` cho factory **không thay đổi danh sách provider toàn cục**. Cách này phù hợp để quan sát/thử nghiệm một provider riêng.

Ở provider sản xuất, việc cài SPI còn đòi hỏi xử lý trạng thái, tham số, lỗi, đối tượng khóa, hiệu năng, luồng đồng thời, kiểm thử theo chuẩn và bảo vệ trước tấn công. Cú pháp `Provider.put(...)` ở đây là cách đăng ký đơn giản cho mục đích học tập; JCA còn cung cấp `Provider.Service` và `putService(...)` để khai báo dịch vụ một cách có cấu trúc.

## 7. Đăng ký provider và thứ tự ưu tiên

Có ba tình huống thường gặp:

| Tình huống | Cách dùng | Phạm vi ảnh hưởng |
| --- | --- | --- |
| Dùng mặc định | `getInstance("SHA-256")` | JCA chọn từ provider đã đăng ký |
| Chỉ định provider | `getInstance("SHA-256", provider)` | Chỉ engine được tạo; đối tượng provider không bắt buộc đăng ký toàn cục |
| Thay đổi danh sách | `Security.addProvider(p)` / `Security.insertProviderAt(p, position)` | Ảnh hưởng thứ tự tìm kiếm provider trong cùng JVM |

`Security.getProviders()` trả danh sách provider đã đăng ký theo thứ tự ưu tiên. `addProvider` thường thêm provider vào cuối danh sách nếu chưa có; `insertProviderAt` yêu cầu vị trí bắt đầu từ 1 và dùng khi thực sự cần thay đổi mức ưu tiên. Provider cũng có thể được cấu hình lúc khởi động qua cấu hình bảo mật Java tùy bản phân phối/cách chạy.

**Không chèn/xóa hoặc đổi ưu tiên provider tùy tiện trong xử lý mỗi request:** thay đổi danh sách toàn cục có thể làm các thành phần khác trong JVM chọn triển khai khác, kéo theo thay đổi tương thích, hiệu năng hoặc chính sách mật mã. Với thư viện, ưu tiên không tự động thay đổi toàn cục; chỉ định `Provider` trực tiếp khi hợp đồng thực sự đòi hỏi.

## 8. Khi nào chọn sai hoặc không tìm thấy provider?

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Không có service/algorithm phù hợp, hoặc không thể tạo engine | Kiểm tra chính xác service type, tên thuật toán, provider có cài và `getServices()` |
| `NoSuchProviderException` | Tên provider chỉ định chưa đăng ký | Kiểm tra `Security.getProviders()`; cân nhắc overload nhận `Provider` |
| `NoSuchPaddingException` với `Cipher` | Transformation yêu cầu padding mà provider không hỗ trợ | Kiểm tra tên `algorithm/mode/padding` và khả năng triển khai |
| `InvalidKeyException` khi `init(...)` | Khóa không phù hợp thuật toán/provider hoặc bị provider từ chối | Kiểm tra kiểu khóa, kích thước, khả năng provider/HSM |
| `ProviderException` hoặc lỗi khởi tạo | Triển khai provider/hạ tầng phía dưới có vấn đề | Giữ stack trace, xem cấu hình provider và nguyên nhân gốc |

Ví dụ `Cipher.getInstance("AES/GCM/NoPadding")` yêu cầu **transformation**, không chỉ “AES”. Việc tạo engine thành công cũng **không đồng nghĩa** đã có khóa/nonce hợp lệ hoặc đã thao tác đúng; với GCM phải bảo đảm nonce không tái sử dụng với cùng khóa và xử lý authentication tag đúng cách. Các vấn đề đó thuộc mức sử dụng thuật toán, ngoài trách nhiệm thuần túy của cơ chế chọn provider.

Một số engine có thể trì hoãn chọn provider đến `init(...)` vì cần xét hỗ trợ khóa. Lấy `getProvider()` có thể buộc lựa chọn sớm ở một số implementation. Vì vậy khi gỡ lỗi, hãy ghi **engine, algorithm/transformation, khóa/tham số, tên provider thực tế và thời điểm phát sinh lỗi** thay vì chỉ dựa vào thứ tự provider.

## 9. Những hiểu lầm và lỗi thiết kế thường gặp

- **Nhầm API với implementation:** ứng dụng gọi `MessageDigest`, không nên khởi tạo trực tiếp lớp SPI của một provider bằng reflection. SPI là hợp đồng dành cho tác giả provider.
- **Nhầm provider với thuật toán:** provider chỉ là bên cung cấp dịch vụ; việc `getInstance()` trả về đối tượng không chứng minh thuật toán đã được dùng an toàn trong quy trình nghiệp vụ.
- **Cố định tên vendor trên mọi môi trường:** provider `SUN` hay `SunJCE` không phải cam kết chung cho mọi JVM. Nếu thật sự cần nhà cung cấp cụ thể, kiểm tra điều kiện triển khai ngay lúc khởi động.
- **Cho rằng thứ tự ưu tiên luôn quyết định mọi trường hợp:** engine có trạng thái khởi tạo/khóa có thể chọn provider muộn hoặc từ chối khóa không tương thích.
- **Dùng chung engine mutable giữa nhiều thread:** `MessageDigest`, `Signature`, `Cipher` thường giữ trạng thái đang xử lý; không mặc định coi instance là thread-safe. Tạo instance riêng theo tác vụ hoặc quản lý đồng bộ đúng hợp đồng.
- **Xem checksum/`MessageDigest` như mã hóa hay lưu mật khẩu an toàn:** digest không đảo ngược thành plaintext và không thay thế được hàm băm mật khẩu có salt, cost phù hợp. `EDU-CHECKSUM32` ở ví dụ chỉ dạy SPI.
- **Bỏ qua lỗi khi provider thay đổi:** cùng API nhưng khác provider có thể khác khả năng hỗ trợ, cách xử lý tham số, hiệu năng hoặc yêu cầu triển khai. Kiểm thử trên runtime đích và sử dụng test vector chuẩn.

## 10. Tự kiểm tra kiến thức

1. Tại sao `MessageDigest.getInstance("SHA-256")` không cần biết lớp Java cài SHA-256 của provider nào? **Vì engine là API ổn định, còn JCA dùng bảng service của provider để tìm implementation SPI.**
2. Nếu muốn thử một provider nhưng không muốn đổi cấu hình cho toàn JVM, dùng overload nào? **`getInstance(algorithm, Provider)`.**
3. `Provider.Service` khác `MessageDigest` thế nào? **Service là bản mô tả loại dịch vụ/thuật toán/lớp triển khai; MessageDigest là đối tượng engine mà ứng dụng thao tác.**
4. Vì sao `getInstance()` thành công chưa chứng minh thao tác chữ ký/mã hóa chắc chắn thành công? **Vì bước `init` với khóa/tham số, hỗ trợ provider và các điều kiện mật mã vẫn có thể thất bại.**

Khi hiểu mối quan hệ **engine API → tra cứu provider/service → SPI implementation**, bạn có thể đọc chính xác một lệnh JCA, chẩn đoán vì sao runtime chọn một provider cụ thể, và biết phần code nào thuộc ứng dụng hay thuộc nhà triển khai thuật toán.

## Tài liệu chính thức để đối chiếu

- [Java 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java 17 — How to Implement a Provider](https://docs.oracle.com/en/java/javase/17/security/howtoimplaprovider.html)
- [Java 17 — Provider.Service API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.Service.html)
- [Java 17 — MessageDigestSpi API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigestSpi.html)

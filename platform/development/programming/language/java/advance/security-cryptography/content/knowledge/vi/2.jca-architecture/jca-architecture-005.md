# 2.5. Khám phá `Provider.Service` và danh sách thuật toán đang có trong tiến trình

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa kiến trúc Java Cryptography Architecture (JCA), `Provider`, `Provider.Service` và các API kiểu `getInstance(...)`.
- Liệt kê **provider đang đăng ký trong chính JVM hiện tại**, các loại dịch vụ và thuật toán mà chúng công bố.
- Tìm provider cung cấp một cặp **loại dịch vụ + thuật toán**, xem thông tin triển khai và xác nhận provider thực sự được chọn khi tạo đối tượng.
- Phân biệt **được quảng bá trong registry**, **có thể tạo instance**, và **sử dụng được với key/tham số thực tế**.

Ví dụ dùng Java 17+; danh sách provider và thuật toán phụ thuộc JDK, nhà cung cấp JDK, bản cấu hình, thư viện cài đặt và thời điểm quan sát. Không có một danh sách đầu ra cố định cho mọi máy.

## 1. `Provider.Service` nằm ở đâu trong JCA?

JCA dùng kiến trúc có thể thay thế implementation. Ứng dụng gọi một **engine API** như `MessageDigest`, `Signature`, `KeyStore` hoặc `SecureRandom`. Một **provider** đăng ký các implementation cho từng loại dịch vụ và tên thuật toán. `Provider.Service` là **bản mô tả đăng ký** cho một implementation: dịch vụ gì, thuật toán nào, provider nào, lớp triển khai nào và có những thuộc tính gì.

```text
Ứng dụng: MessageDigest.getInstance("SHA-256")
                    |
            JCA engine / factory
                    |
       Danh sách provider được đăng ký
                    |
          Provider -> Provider.Service
                    |
              Implementation (SPI)
```

- `Security.getProviders()` trả về các provider **đã đăng ký** trong JVM, theo thứ tự ưu tiên (vị trí 1 được xét trước). Một JAR có trên classpath/module path chưa đồng nghĩa provider của nó đã được đăng ký.
- `provider.getServices()` trả về tập các bản mô tả dịch vụ mà provider công bố. Cùng một loại và thuật toán có thể xuất hiện ở **nhiều provider** khác nhau.
- Với `MessageDigest.getInstance("SHA-256")`, JCA tìm implementation phù hợp qua cơ chế lựa chọn provider. Nếu không chỉ định provider, đừng giả định tên provider luôn cố định. Một số engine có thể trì hoãn việc chọn implementation đến khi biết key/tham số.
- Registry có thể thay đổi khi ứng dụng đăng ký, chèn ưu tiên hoặc gỡ provider; kết quả khám phá chỉ phản ánh **tiến trình và thời điểm đã đọc**.

Các engine tiêu biểu: `MessageDigest` (băm), `Signature` (chữ ký số), `Cipher` (mã hóa/giải mã), `Mac` (mã xác thực thông điệp), `KeyAgreement` (thỏa thuận khóa), `KeyFactory`, `KeyGenerator`, `KeyStore`, `SecureRandom` và `SSLContext`. Mỗi engine có ý nghĩa, thuật toán và điều kiện sử dụng khác nhau.

## 2. Bộ API khám phá cần biết

| Câu hỏi | API Java | Ý nghĩa |
| --- | --- | --- |
| JVM đã đăng ký những provider nào? | `Security.getProviders()` | Mảng provider theo thứ tự ưu tiên. |
| Tìm một provider theo tên? | `Security.getProvider(name)` | Trả về `Provider` hoặc `null`. |
| Provider cung cấp những dịch vụ nào? | `provider.getServices()` | Tập `Provider.Service` không thể sửa qua tập trả về; không dựa vào thứ tự duyệt. |
| Provider có cặp type/algorithm này không? | `provider.getService(type, algorithm)` | Trả về descriptor hoặc `null`; tên thuật toán có thể là tên chính hoặc alias provider biết. |
| Tên thuật toán đang được quảng bá cho một loại dịch vụ? | `Security.getAlgorithms(type)` | Tập tên thuật toán/kiểu có sẵn theo registry, không thể sửa trực tiếp; nếu không có trả tập rỗng. |
| Provider nào công bố một cặp dịch vụ/thuật toán? | `Security.getProviders("MessageDigest.SHA-256")` | Mảng provider phù hợp, hoặc `null` nếu không có. |
| Instance cụ thể đã chọn provider nào? | `engineInstance.getProvider()` | Provider thực tế của đối tượng, có ý nghĩa hơn dự đoán từ registry. |

Trên mỗi `Provider.Service`, các getter thiết yếu là:

- `getProvider()`: provider sở hữu descriptor.
- `getType()`: tên loại dịch vụ, chẳng hạn `MessageDigest`.
- `getAlgorithm()`: tên thuật toán hoặc kiểu do provider đăng ký, chẳng hạn `SHA-256`.
- `getClassName()`: tên lớp triển khai mà provider khai báo; chủ yếu hữu ích cho chẩn đoán, **không có nghĩa** ứng dụng nên tự tải hay khởi tạo lớp SPI đó.
- `getAttribute(name)`: thuộc tính tùy chọn theo tên, trả `null` khi không có. Ví dụ một số dịch vụ/provider có `KeySize` hoặc `SupportedKeyClasses`; đừng giả định tất cả đều có.
- `supportsParameter(...)` và `newInstance(...)` là các cơ chế framework dùng theo quy ước từng engine. Trong code ứng dụng, ưu tiên factory công khai (`MessageDigest.getInstance`, `Cipher.getInstance`...) thay vì tự gọi `newInstance(...)`.

**Chi tiết quan trọng về alias:** `Provider.Service` có thể chứa các tên thay thế bên trong descriptor nhưng **không có public getter `getAliases()`**. Muốn kiểm tra một alias cụ thể, dùng `provider.getService(type, alias)` hoặc thử factory tương ứng; đừng suy ra danh sách alias đầy đủ chỉ từ `getAlgorithm()`.

## 3. Chương trình liệt kê provider, service và thuật toán

Lưu toàn bộ mã sau vào **`ProviderExplorer.java`**. Mặc định chỉ in các service `MessageDigest` để dễ đọc. Có thể truyền loại dịch vụ khác, hoặc `*` để xem tất cả service. Chương trình **chỉ quan sát**, không thêm/gỡ/thay đổi provider.

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public final class ProviderExplorer {
    private ProviderExplorer() {
    }

    public static void main(String[] args) throws NoSuchAlgorithmException {
        if (args.length > 1) {
            System.err.println("Cách dùng: java ProviderExplorer [serviceType|*]");
            return;
        }

        String typeFilter = args.length == 0 ? "MessageDigest" : args[0];
        Provider[] providers = Security.getProviders();

        System.out.printf("Java: %s (%s)%n",
                System.getProperty("java.version"),
                System.getProperty("java.vendor"));
        System.out.printf("So provider: %d%n", providers.length);

        for (int i = 0; i < providers.length; i++) {
            Provider provider = providers[i];
            System.out.printf("%n[%02d] %s | version %s%n",
                    i + 1, provider.getName(), provider.getVersionStr());

            provider.getServices().stream()
                    .filter(service -> typeFilter.equals("*")
                            || service.getType().equalsIgnoreCase(typeFilter))
                    .sorted(Comparator
                            .comparing(Provider.Service::getType,
                                    String.CASE_INSENSITIVE_ORDER)
                            .thenComparing(Provider.Service::getAlgorithm,
                                    String.CASE_INSENSITIVE_ORDER))
                    .forEach(service -> System.out.printf(
                            "  %-20s %-32s %s%n",
                            service.getType(),
                            service.getAlgorithm(),
                            service.getClassName()));
        }

        if (!typeFilter.equals("*")) {
            Set<String> names = Security.getAlgorithms(typeFilter);
            TreeSet<String> sortedNames = new TreeSet<>(names);

            System.out.printf("%nThuat toan (%s): %d%n",
                    typeFilter, names.size());
            for (String name : sortedNames) {
                System.out.println("  " + name);
            }
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.printf("%nSHA-256 duoc chon tu provider: %s%n",
                digest.getProvider().getName());
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 ProviderExplorer.java
java ProviderExplorer
java ProviderExplorer Signature
java ProviderExplorer Cipher
java ProviderExplorer "*"
```

Cách đọc kết quả:

1. Dòng `Java` ghi phiên bản và vendor runtime; `So provider` là số lượng provider **đang đăng ký**, không phải số provider có trên máy.
2. `[01]`, `[02]`, ... thể hiện **thứ tự ưu tiên ban đầu** từ `Security.getProviders()`. Mỗi dòng dịch vụ gồm **type**, **algorithm** và **implementation class**; kết quả đã được sắp xếp **trong từng provider** để dễ đối chiếu.
3. Cuối kết quả, `Security.getAlgorithms(typeFilter)` cho tập **tên thuật toán phân biệt theo service type** trên toàn bộ provider. Tập này là bản tổng hợp, vì vậy tên xuất hiện ở hai provider vẫn chỉ là một mục trong tập.
4. Dòng cuối cho provider của instance `MessageDigest("SHA-256")` mà JCA đã tạo. Đó là quan sát tại runtime, không phải cam kết mọi máy đều chọn cùng provider.
5. Với `*`, chương trình duyệt **mọi loại dịch vụ** và bỏ qua phần tổng hợp `Security.getAlgorithms` vì `*` không phải tên engine hợp lệ. Kết quả có thể rất dài.

Ví dụ, trên một JDK có provider tên `SUN`, bạn *có thể* thấy `MessageDigest / SHA-256` thuộc provider này. Tên provider, version, số service, thứ tự, lớp triển khai và tên thuật toán thực tế **không được coi là output cố định**. Nếu lọc loại không được đăng ký, không có dòng dịch vụ tương ứng và tập thuật toán có thể rỗng.

## 4. Tra cứu dịch vụ cụ thể và các provider cùng hỗ trợ

Đoạn sau là **snippet đặt bên trong một phương thức** (với `import java.security.Provider;` và `import java.security.Security;`), không phải chương trình độc lập:

```java
Provider[] candidates =
        Security.getProviders("MessageDigest.SHA-256");

if (candidates == null) {
    System.out.println("Khong co provider phu hop");
} else {
    for (Provider provider : candidates) {
        Provider.Service service =
                provider.getService("MessageDigest", "SHA-256");

        System.out.printf("%s -> %s%n",
                provider.getName(),
                service == null ? "(khong co descriptor)" :
                        service.getClassName());
    }
}
```

Chỉ rõ cả **type và algorithm** rất quan trọng: `SHA-256` trong `MessageDigest` không phải dịch vụ cùng loại với một thuật toán `Signature` hay `Mac`. `Security.getProviders(filter)` trả `null` khi không có provider thỏa điều kiện; cần kiểm tra trước khi duyệt. Khi đã có `Provider`, `getService(type, algorithm)` hỗ trợ tên thuật toán chính hoặc **alias mà provider nhận biết**, và có thể trả `null`.

Khi cần in metadata, ví dụ `service.getAttribute("KeySize")`, hãy xử lý `null`. Attribute là thông tin provider công bố, không thay thế kiểm tra ràng buộc thực tế của key, mode, padding hay policy.


## 5. Đọc metadata sâu mà không nhầm descriptor với engine

Sau khi đã chạy `ProviderExplorer` ở mục 3, chọn một dòng `MessageDigest / SHA-256` hoặc một service khác và kiểm tra các tầng sau. `Provider.Service` là **metadata có thể tra cứu**, còn việc tạo engine và thực hiện phép toán là **bằng chứng sử dụng**. Không cần lặp một chương trình băm `abc` chỉ để chứng minh giá trị SHA-256 đã biết.

~~~java
// Snippet đặt trong một phương thức có xử lý ngoại lệ thích hợp.
// "provider" là một Provider lấy từ Security.getProviders().
Provider.Service service = provider.getService("MessageDigest", "SHA-256");

if (service != null) {
    System.out.println("type=" + service.getType());
    System.out.println("algorithm=" + service.getAlgorithm());
    System.out.println("class=" + service.getClassName());
    System.out.println("provider=" + service.getProvider().getName());

    // Một thuộc tính tùy chọn; null là bình thường.
    String formats = service.getAttribute("SupportedKeyFormats");
    System.out.println("formatsAdvertised=" + (formats != null));

    // Kiểm tra khả năng tạo instance bằng API công khai, không new SPI.
    java.security.MessageDigest engine =
            java.security.MessageDigest.getInstance("SHA-256", provider);
    System.out.println("digestLength="
            + engine.digest("catalog".getBytes(
                    java.nio.charset.StandardCharsets.UTF_8)).length);
}
~~~

Với SHA-256 đúng chuẩn, `digestLength=32` khi nhánh chạy được. **Tên class, provider và attribute** phụ thuộc implementation, nên không thể ghi stdout cố định cho chúng. Đây là snippet để chèn vào vòng lặp `ProviderExplorer`, không phải file độc lập; import `java.security.Provider` là đủ nếu đã có biến `provider`.

Điểm cần đối chiếu: (a) descriptor tồn tại; (b) engine tạo được với **chính provider này**; (c) digest dùng được. Với `Signature` hoặc `Cipher`, bước (c) phải gồm `init` với khóa/tham số đại diện cho điều kiện thật. `supportsParameter(...)` là một gợi ý nội bộ theo loại service: kết quả `true` có thể chỉ nghĩa “có thể hỗ trợ/chưa rõ”, **không phải xác nhận rằng mọi khóa hay operation đều chạy được**.


## 6. Ba mức bằng chứng khi lập bản đồ dịch vụ runtime

| Bằng chứng | Kết luận được phép | Kết luận chưa được phép |
| --- | --- | --- |
| `Security.getAlgorithms(type)` | Tên đang được quảng bá theo service type trong registry | Toàn bộ alias, mọi transformation hoặc khả năng với khóa cụ thể |
| `provider.getServices()` / `getService(type, algorithm)` | Descriptor của provider, type, tên chính/alias, class triển khai, attribute tùy chọn | Provider chắc chắn tạo được mọi engine và xử lý thành công |
| `getInstance(..., provider)` + `init` + phép toán | Tổ hợp thuật toán, key, tham số được thử trên runtime/provider này | Mọi key, mọi version, mọi trạng thái HSM đều được bảo đảm |

**Bẫy catalog:** `Security.getAlgorithms("Cipher")` không sinh tất cả tổ hợp mode/padding; một provider có `Cipher.AES` có thể chấp nhận `AES/GCM/NoPadding` dù `getService("Cipher", "AES/GCM/NoPadding")` không cho descriptor trực tiếp. Khi kiểm tra transformation, hãy thử chính `Cipher.getInstance(transformation, provider)` và thao tác có tham số hợp lệ. Tương tự, alias có thể được `getService` phân giải dù không xuất hiện như một service riêng; `Provider.Service` không có public `getAliases()`.

**Bẫy ưu tiên:** thứ tự `Security.getProviders()` giúp mô tả registry, nhưng không thay thế việc quan sát `engine.getProvider()` khi engine đã khởi tạo đủ thông tin. **Bẫy an toàn:** registry có thể còn MD5 hoặc thuật toán cũ vì tương thích; có service không đồng nghĩa được phép dùng trong giao thức mới.

Bảng khám phá là **ảnh chụp tại thời điểm chạy**. Nếu ứng dụng thêm/gỡ provider trong cùng JVM, hoặc chạy trên HSM/JDK khác, cần chụp lại cấu hình; không mang một bản catalog từ laptop áp đặt cho production.

## 7. Quy trình chẩn đoán có thể lặp lại

Khi một môi trường báo `NoSuchAlgorithmException`, `NoSuchPaddingException` hoặc provider được chọn khác dự kiến, tiến hành theo thứ tự:

1. Ghi **`java.version`, `java.vendor`** và danh sách `Security.getProviders()` của chính tiến trình lỗi. Không lấy danh sách của laptop để kết luận về container/server đang chạy.
2. Xác định **engine type chính xác** (ví dụ `MessageDigest` hay `Cipher`) và tên thuật toán/transformation mà code thật đang yêu cầu. Lấy `Security.getAlgorithms(type)` để định hướng, rồi tìm descriptor qua từng `provider.getService(type, algorithm)`.
3. Tìm các provider ứng viên với `Security.getProviders("Type.Algorithm")` khi bộ lọc phù hợp; nhớ kiểm tra kết quả `null`. Với transformation `Cipher`, kiểm tra thêm bằng factory thực tế.
4. Thử `getInstance(...)` và, nếu cần, `init(...)`/thao tác thật với key và tham số hợp lệ. Đọc `getProvider()` của đối tượng đã chọn và ghi lỗi đầy đủ nếu thất bại.
5. So sánh **cùng phiên bản JDK, security configuration, provider đăng ký, thứ tự ưu tiên, dependencies và môi trường chạy**. Provider PKCS#11/HSM/native có thể phụ thuộc cấu hình thiết bị; có tên trong registry vẫn chưa chứng minh sẵn sàng vận hành.
6. Giữ chẩn đoán ở chế độ chỉ đọc; tránh thêm/gỡ provider toàn cục chỉ để “thử”, vì có thể làm thay đổi hành vi các luồng khác trong cùng JVM. Không log key, mật khẩu, secret hay dữ liệu nhạy cảm.

## 8. Những nhầm lẫn phổ biến và tự kiểm tra

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “JAR provider có trên classpath là đã được chọn.” | Provider cần được đăng ký hoặc được cơ chế runtime nạp phù hợp; quan sát bằng `Security.getProviders()`. |
| “`getServices()` có thứ tự ưu tiên trong từng Set.” | Thứ tự ưu tiên nằm ở **mảng provider**; hãy tự sort service khi in. |
| “`Security.getAlgorithms("Cipher")` liệt kê mọi transformation.” | Đây là tập tên được registry công bố cho service type, không phải tích Descartes của thuật toán/mode/padding. |
| “Có `Provider.Service` nghĩa là mọi key đều được chấp nhận.” | Cần thử factory và thao tác thực với key/params; implementation có thể từ chối. |
| “`getClassName()` là lớp API nên new trực tiếp.” | Nên dùng engine factory; SPI là chi tiết implementation. |
| “Provider đầu tiên luôn là provider mà `Cipher` dùng.” | Có thể xảy ra lựa chọn muộn theo key và tham số; kiểm tra instance thực tế. |
| “Thuật toán có trong registry thì an toàn.” | Khả năng cung cấp không phải khuyến nghị bảo mật. |

**Bài tự kiểm tra:**

1. Chạy `java ProviderExplorer MessageDigest` và `java ProviderExplorer Signature`. So sánh provider nào đăng ký các type này và vì sao hai danh sách thuật toán khác nhau.
2. Chạy `java ProviderExplorer Cipher`, sau đó tra API `Cipher.getInstance("AES/GCM/NoPadding")`. Giải thích vì sao không thể suy ra mọi transformation chỉ từ `getAlgorithms("Cipher")`.
3. Tìm một cặp `type + algorithm` có ở hơn một provider (nếu môi trường có). So sánh `getClassName()`, sau đó quan sát `getProvider()` từ instance được tạo mà không ép provider.
4. Nếu `Security.getProviders("MessageDigest.SHA-256")` trả `null`, điều đó nói gì về registry của tiến trình tại thời điểm gọi? Vì sao chưa nên kết luận cùng một điều về JVM khác?

## Tài liệu API chính thức (Java 17)

- [`Security` — `getProviders`, `getAlgorithms`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html)
- [`Provider` — `getServices`, `getService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.html)
- [`Provider.Service` — cấu trúc descriptor và các phương thức](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.Service.html)
- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)

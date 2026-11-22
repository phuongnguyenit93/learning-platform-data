# 2.2 Lấy dịch vụ qua `getInstance` và lựa chọn provider theo thứ tự ưu tiên

Trong Java Cryptography Architecture (JCA), ứng dụng yêu cầu **loại dịch vụ + tên thuật toán**, còn JCA tìm một **provider** cung cấp triển khai tương ứng. Điểm mấu chốt của bài này là biết `getInstance(...)` chọn triển khai nào, vì sao kết quả có thể khác giữa các môi trường và lúc nào nên chỉ định provider.

Sau bài học, bạn có thể:
- Phân biệt **engine class**, **algorithm/transformation**, **provider** và **SPI**.
- Sử dụng ba dạng `getInstance`: chọn tự động, khóa theo tên provider, khóa theo đối tượng `Provider`.
- Đọc thứ tự provider, kiểm tra một dịch vụ có được công bố và nhận biết provider thực sự đang dùng.
- Giải thích trường hợp provider ưu tiên cao không phù hợp, ngoại lệ khi không có dịch vụ, và những lưu ý về chọn provider trễ.
- Quyết định khi nào để JCA tự chọn và khi nào phải cấu hình provider cụ thể.


## 1. Đọc đúng câu hỏi đặt ra cho `getInstance`

Trước khi chọn provider, cần xác định **loại engine** và **yêu cầu thuật toán**. Trong `MessageDigest.getInstance("SHA-256")`, `MessageDigest` là API engine, `SHA-256` là algorithm, còn provider là triển khai sẽ được JCA chọn. Mỗi provider đăng ký các cặp service/algorithm qua `Provider.Service`, kết nối tới implementation SPI. Đây là các vai trò khác nhau: một provider có thể cung cấp nhiều dịch vụ, và một ứng dụng có thể dùng nhiều provider cho nhiều engine.

| Điều cần quyết định | Ví dụ | Hệ quả khi nhầm |
| --- | --- | --- |
| **Engine** | `MessageDigest`, `Signature`, `Cipher` | Đưa `AES` vào digest hoặc `SHA-256` vào cipher là sai loại dịch vụ |
| **Algorithm/transformation** | `SHA-256`, `SHA256withRSA`, `AES/GCM/NoPadding` | Tên cipher thiếu mode/padding có thể khiến hành vi phụ thuộc provider |
| **Provider selection** | Tự tìm, khóa theo tên, hoặc truyền đối tượng `Provider` | Khả năng tương thích, HSM và chính sách fallback thay đổi |

Bài này **đi sâu vào quyết định lựa chọn**: khi nào dùng overload tự động, khi nào buộc một provider, ưu tiên nào có hiệu lực và tại sao lựa chọn có thể diễn ra muộn đến `init`. Các chi tiết viết SPI/provider nằm ở phần kiến trúc; tại đây, mã thí nghiệm sẽ đo **sự thay đổi provider thực tế** khi thay thứ tự đăng ký.

## 2. Ba cách gọi `getInstance`

Dùng `MessageDigest` làm ví dụ; các engine có phương thức tương tự, nhưng ngoại lệ và tham số có thể khác.

| Lệnh | Cách chọn | Ràng buộc |
| --- | --- | --- |
| `MessageDigest.getInstance("SHA-256")` | JCA tìm trong các provider đã đăng ký theo cơ chế ưu tiên của JVM. | Linh hoạt, có khả năng tận dụng provider thích hợp trên môi trường đang chạy. |
| `MessageDigest.getInstance("SHA-256", "SUN")` | Chỉ dùng provider **có tên** `SUN`. | Provider phải đã được đăng ký; tên chỉ là ví dụ, không bảo đảm tồn tại. |
| `MessageDigest.getInstance("SHA-256", provider)` | Chỉ dùng đúng **đối tượng** `Provider` được truyền vào. | Với overload này, đối tượng provider không nhất thiết phải có trong danh sách đã đăng ký. |

Không có overload tự động “thử provider khác” khi **đã chỉ định rõ** provider mà nó không hỗ trợ thuật toán. Nếu `getInstance("SHA-256", "ProviderX")` thất bại, bạn phải xử lý ngoại lệ hoặc có chính sách fallback tường minh của ứng dụng. Đừng âm thầm đổi sang provider khác nếu yêu cầu bảo mật bắt buộc dùng một HSM hoặc provider được kiểm định.

Lưu ý tên thuật toán và loại engine là hai thành phần của khóa tìm kiếm: `MessageDigest/SHA-256` khác với `Signature/SHA256withRSA`. Với `Cipher`, hãy nêu transformation đầy đủ (thuật toán/chế độ/padding), chẳng hạn `AES/GCM/NoPadding`; `Cipher.getInstance("AES")` thiếu thông tin chế độ và padding, dễ dẫn đến lựa chọn không mong muốn tùy provider.

Java định nghĩa **standard algorithm names**; nên dùng tên chuẩn thay vì dựa vào alias riêng của một provider. Tên thuật toán được tra cứu không phân biệt chữ hoa/thường theo API, nhưng điều đó không biến một tên sai thành một thuật toán hợp lệ.

## 3. Provider được chọn như thế nào?

### 3.1. Thứ tự ưu tiên khi không chỉ định provider

`Security.getProviders()` trả về các provider đang đăng ký của JVM theo thứ tự ưu tiên; **vị trí 1 là ưu tiên cao nhất**. Danh sách được thiết lập lúc khởi động từ cấu hình bảo mật của JVM và có thể được ứng dụng thay đổi bằng API.

Giả sử danh sách logic như sau:

| Vị trí | Provider | Các dịch vụ công bố trong ví dụ |
| --- | --- | --- |
| 1 | P1 | `Signature/SHA256withRSA` |
| 2 | P2 | `MessageDigest/SHA-256` và `Signature/SHA256withRSA` |
| 3 | P3 | `MessageDigest/SHA-256` |

Khi gọi `MessageDigest.getInstance("SHA-256")`, P1 bị bỏ qua vì không có dịch vụ digest được yêu cầu; P2 là ứng viên phù hợp đầu tiên. Với `Signature.getInstance("SHA256withRSA")`, P1 là ứng viên có ưu tiên cao nhất. Khi chỉ định P3 trực tiếp cho `SHA-256`, thứ tự P1/P2 không quyết định kết quả.

Đây là **mô hình mặc định**; không suy ra rằng provider ở hàng đầu tiên của `Security.getProviders()` luôn được dùng trong mọi trường hợp. Còn có những điểm tinh tế sau:

1. **Phạm vi engine và thuật toán:** provider được ưu tiên cao chỉ có ý nghĩa nếu công bố đúng loại dịch vụ và tên thuật toán (hoặc alias tương thích).
2. **Có khả năng khởi tạo/sử dụng:** một dịch vụ được công bố không đồng nghĩa mọi khóa, tham số hoặc hoàn cảnh sử dụng đều được chấp nhận. Ngoại lệ khi gọi `init` hay thực hiện phép toán phải được xử lý riêng.
3. **Ưu tiên theo thuật toán của JDK:** bản triển khai tham chiếu JDK có security property `jdk.security.provider.preferred`, có thể đặt thứ tự ưu tiên **cho thuật toán cụ thể** khác với thứ tự hiện ra từ `Security.getProviders()`. Vì vậy, danh sách đăng ký là thông tin cần kiểm tra, còn `getProvider()` của đối tượng sử dụng mới là bằng chứng về provider đã chọn.
4. **Chọn provider trễ:** một số engine/triển khai, đặc biệt `Signature`, có thể trì hoãn việc chốt provider cho đến khi `initSign`/`initVerify` biết khóa cụ thể. Gọi `getProvider()` **trước** lúc `init` trong các trường hợp đó có thể buộc chọn sớm và làm mất cơ hội tìm triển khai phù hợp với khóa. Nên kiểm tra provider sau khởi tạo khi cần quan sát chính xác.
5. **Thay đổi động:** thứ tự provider có thể bị thay đổi sau khi JVM khởi động; kết quả truy vấn ở hai thời điểm không nhất thiết trùng nhau. Đừng giả định thay đổi danh sách sẽ chuyển provider của các đối tượng đã tạo.

Một cách nhớ chính xác: **`getInstance(algorithm)` yêu cầu JCA tìm triển khai phù hợp theo chính sách lựa chọn của JVM; `getInstance(algorithm, provider)` ràng buộc lựa chọn vào provider được chỉ định.**

### 3.2. Phân biệt chọn thuật toán, chọn provider và khởi tạo

- **Chọn thuật toán:** `getInstance("SHA-256")` xác định yêu cầu làm hàm băm SHA-256.
- **Chọn provider:** JCA xác định lớp triển khai cung cấp yêu cầu đó.
- **Khởi tạo/tác nghiệp:** các engine như `Cipher`/`Signature` còn cần `init` với khóa, chế độ thao tác và tham số phù hợp. `getInstance` thành công không bảo đảm `init` thành công.

Ví dụ: provider công bố thuật toán chữ ký nhưng không chấp nhận một loại `PrivateKey` nhất định có thể ném `InvalidKeyException` tại `initSign`. Không nên hiểu đó là “thuật toán không tồn tại”; cũng không nên tùy tiện đổi provider nếu khóa chỉ nằm trong thiết bị phần cứng bắt buộc.

## 4. Quan sát provider và service trên JVM hiện tại

Các API cốt lõi:

- `Security.getProviders()`: mọi provider đã đăng ký theo thứ tự ưu tiên chung.
- `Security.getProvider("Tên")`: lấy provider đăng ký theo tên; trả `null` nếu không có.
- `Security.getProviders("MessageDigest.SHA-256")`: lọc provider công bố dịch vụ/thuật toán này; có thể trả **`null`** khi không có ứng viên.
- `provider.getService("MessageDigest", "SHA-256")`: lấy mô tả `Provider.Service`, hoặc `null` nếu provider không công bố dịch vụ đó.
- `provider.getServices()`: xem những dịch vụ provider công bố; tránh in toàn bộ trong log vận hành.
- `engine.getProvider()`: provider của engine đã được chọn; với các engine chọn trễ, xem sau `init`.
- `Security.getProperty("jdk.security.provider.preferred")`: tham khảo cấu hình ưu tiên riêng của JDK khi cần giải thích kết quả không trùng thứ tự chung.

### Ví dụ chạy được: kiểm tra SHA-256 và provider thực tế

Lưu toàn bộ thành **`JcaDiscovery.java`** (Java 17+):

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;

public class JcaDiscovery {
    public static void main(String[] args) throws GeneralSecurityException {
        Provider[] installed = Security.getProviders();

        System.out.println("Registered providers (global order):");
        for (int i = 0; i < installed.length; i++) {
            Provider p = installed[i];
            Provider.Service service = p.getService("MessageDigest", "SHA-256");
            System.out.printf("%d. %s | SHA-256: %s%n",
                    i + 1, p.getName(),
                    service == null ? "not advertised" : "advertised");
        }

        Provider[] candidates =
                Security.getProviders("MessageDigest.SHA-256");
        System.out.println("Advertised SHA-256 providers: "
                + (candidates == null ? 0 : candidates.length));

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        Provider selected = digest.getProvider();
        String hex = HexFormat.of().formatHex(
                digest.digest("abc".getBytes(StandardCharsets.UTF_8)));

        System.out.println("Selected provider: " + selected.getName());
        System.out.println("SHA-256(abc): " + hex);

        // Hai cách khóa vào đúng provider đã quan sát:
        MessageDigest byName =
                MessageDigest.getInstance("SHA-256", selected.getName());
        MessageDigest byObject =
                MessageDigest.getInstance("SHA-256", selected);
        System.out.println("Explicit name/object: "
                + byName.getProvider().getName() + "/"
                + byObject.getProvider().getName());
    }
}
~~~

Chạy ở thư mục chứa tệp:

~~~bash
javac JcaDiscovery.java
java JcaDiscovery
~~~

Giá trị **bất biến** trong đầu ra là:

~~~text
SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Số lượng provider, thứ tự, tên provider được chọn và phần `Explicit name/object` **phụ thuộc JVM/cấu hình**; không nên chép một danh sách `SUN`/`SunJCE` làm kết quả cố định. Trong phạm vi chương trình này, hai overload tường minh đều phải trả về đúng tên provider đã được chọn cho `digest`.

Ví dụ dùng `SHA-256` chỉ để quan sát JCA. Đừng dùng một digest SHA-256 đơn lẻ làm phương pháp lưu mật khẩu; đó là bài toán khác, cần thuật toán dẫn xuất mật khẩu chuyên dụng.

## 5. Thí nghiệm độc lập: thay thứ tự ưu tiên để nhìn thấy sự khác biệt

Để kiểm chứng mà không phụ thuộc danh sách provider cài sẵn, ta đăng ký **hai provider đồ chơi**, cùng công bố thuật toán giả `LESSON-ONLY`. Chúng trả về một byte ký hiệu khác nhau: A cho `0a`, B cho `0b`, **hoàn toàn không phải hàm băm mật mã**. Chỉ chạy ví dụ này trong một chương trình thử nghiệm riêng.

Lưu thành **`ProviderPriorityDemo.java`** (Java 17+):

~~~java
import java.security.MessageDigest;
import java.security.MessageDigestSpi;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;

public class ProviderPriorityDemo {
    // SPI giả, chỉ trả về marker; không tạo digest bảo mật.
    public static class A extends MessageDigestSpi {
        @Override
        protected void engineUpdate(byte input) {}

        @Override
        protected void engineUpdate(byte[] input, int offset, int len) {}

        @Override
        protected byte[] engineDigest() {
            return new byte[] { 0x0a };
        }

        @Override
        protected void engineReset() {}

        @Override
        protected int engineGetDigestLength() {
            return 1;
        }
    }

    public static class B extends A {
        @Override
        protected byte[] engineDigest() {
            return new byte[] { 0x0b };
        }
    }

    static class DemoProvider extends Provider {
        DemoProvider(String name, Class<? extends MessageDigestSpi> spi) {
            super(name, "1.0", "Teaching-only marker, NOT cryptography");
            putService(new Service(this, "MessageDigest", "LESSON-ONLY",
                    spi.getName(), null, null));
        }
    }

    private static void show(String label, MessageDigest md) {
        System.out.println(label + " -> " + md.getProvider().getName()
                + ":" + HexFormat.of().formatHex(
                        md.digest(new byte[] { 42 })));
    }

    public static void main(String[] args) throws Exception {
        String pa = "LessonA";
        String pb = "LessonB";

        if (Security.getProvider(pa) != null
                || Security.getProvider(pb) != null) {
            throw new IllegalStateException("Provider name taken");
        }

        try {
            Security.insertProviderAt(new DemoProvider(pb, B.class), 1);
            Security.insertProviderAt(new DemoProvider(pa, A.class), 1);
            // A vừa chiếm vị trí 1; B bị đẩy xuống vị trí 2.

            show("default", MessageDigest.getInstance("LESSON-ONLY"));
            show("pinned B", MessageDigest.getInstance("LESSON-ONLY", pb));

            Security.removeProvider(pa);
            show("after removing A",
                    MessageDigest.getInstance("LESSON-ONLY"));
        } finally {
            Security.removeProvider(pa);
            Security.removeProvider(pb);
        }
    }
}
~~~

~~~bash
javac ProviderPriorityDemo.java
java ProviderPriorityDemo
~~~

Với một JVM bình thường không có cấu hình đặc biệt cho thuật toán giả này, stdout:

~~~text
default -> LessonA:0a
pinned B -> LessonB:0b
after removing A -> LessonB:0b
~~~

Phân tích từng bước:

1. Đăng ký B ở vị trí 1, rồi đăng ký A ở vị trí 1; A trở thành provider ưu tiên nhất cho `MessageDigest/LESSON-ONLY`.
2. `getInstance("LESSON-ONLY")` chọn A. Dùng tên `LessonB` tường minh vẫn chọn B, bất kể thứ tự.
3. Sau khi bỏ A, lần gọi `getInstance` **mới** chọn B; ví dụ không yêu cầu một engine đã được tạo phải tự thay provider.
4. `finally` dọn hai provider ví dụ ngay cả khi phát sinh ngoại lệ.

`Security.insertProviderAt(provider, 1)` chèn provider ở đầu; `Security.addProvider(provider)` thêm vào cuối danh sách, còn `Security.removeProvider(name)` gỡ provider. Hai hàm thêm trả **`-1`** nếu provider cùng tên đã được cài đặt, nên khi viết mã thật cần kiểm tra kết quả. Nếu muốn **chuyển vị trí** một provider đã đăng ký, API quy định phải gỡ rồi đăng ký lại; không giả định `insertProviderAt` tự di chuyển provider cũ.

**Cảnh báo về phạm vi:** danh sách provider là trạng thái bảo mật ở cấp JVM; thay đổi nó trong ứng dụng nhiều luồng có thể ảnh hưởng các phần khác. Ví dụ trên chỉ để học và kiểm chứng; trong hệ thống thực tế, cấu hình provider cần được quản lý ở giai đoạn khởi động, với kiểm thử và kiểm soát triển khai.

## 6. Xử lý lỗi đúng điểm phát sinh

| Tình huống | Ngoại lệ/kết quả đáng chú ý | Cách hiểu và xử lý |
| --- | --- | --- |
| Không provider nào cung cấp `MessageDigest/SHA-256` | `NoSuchAlgorithmException` từ `getInstance` | Kiểm tra tên thuật toán, dịch vụ, danh sách và cấu hình provider. |
| Chỉ định tên provider chưa được đăng ký | `NoSuchProviderException` | Kiểm tra `Security.getProvider(name)` và cách cấu hình/deploy provider. |
| Provider có tồn tại nhưng không công bố thuật toán được chỉ định | `NoSuchAlgorithmException` | Tên provider hợp lệ không có nghĩa nó hỗ trợ mọi engine/algorithm. |
| Chỉ định chuỗi tên provider rỗng/null | `IllegalArgumentException` | Cần tên provider không rỗng với overload nhận `String`. |
| Chỉ định đối tượng `Provider` là null | `IllegalArgumentException` | Cần tham chiếu đối tượng hợp lệ. |
| `Signature`/`Cipher` nhận khóa hoặc tham số không phù hợp lúc `init` | Chẳng hạn `InvalidKeyException`/`InvalidAlgorithmParameterException` | Phân tích tương thích khóa/tham số; `getInstance` thành công chưa chứng minh thao tác mật mã sẽ thành công. |
| `Cipher` nhận transformation với padding không được hỗ trợ | Có thể gặp `NoSuchPaddingException` | Kiểm tra chính xác transformation và nhà cung cấp; đừng lặng lẽ đổi sang cấu hình yếu hơn. |
| `Security.getProviders(filter)` không thấy ứng viên | Trả `null` (không phải mảng rỗng được bảo đảm) | Kiểm tra null trước khi duyệt hoặc gọi `length`. |

Không nên viết kiểu “thử `getInstance` với provider A; bắt mọi `Exception` rồi âm thầm dùng provider B”. Trong yêu cầu HSM/FIPS, fallback như vậy có thể vi phạm mục tiêu bảo mật. Với phần mềm phổ thông, thường hãy dùng overload không gắn provider và xử lý lỗi rõ ràng khi dịch vụ không sẵn có.

## 7. Vì sao provider được chọn khác giữa máy phát triển và production?

Những nguyên nhân thường gặp:

- **Khác bản phân phối JDK hoặc hệ điều hành:** tập provider sẵn có và các dịch vụ được hỗ trợ khác nhau.
- **Khác cấu hình JVM:** `conf/security/java.security` (đường dẫn điển hình trong JDK) và các security properties liên quan, đặc biệt `jdk.security.provider.preferred` của bản triển khai tham chiếu.
- **Có đăng ký provider bổ sung:** thư viện mật mã, thiết bị HSM/PKCS#11, provider tối ưu phần cứng hoặc cấu hình khi khởi động.
- **Khóa không tương thích:** một provider có thuật toán nhưng không xử lý được một đối tượng khóa cụ thể. Với engine chọn trễ, provider thực tế có thể chỉ được chốt sau `init`.
- **Thời điểm quan sát:** ứng dụng có thể thêm/gỡ provider trong lúc chạy.

Quy trình chẩn đoán gọn:

1. Ghi nhận `java -version`, cấu hình bảo mật và tên engine/algorithm/transformation yêu cầu.
2. In `Security.getProviders()` cùng thứ tự; lọc đúng dịch vụ qua `getProviders("MessageDigest.SHA-256")` hoặc `Provider.getService`.
3. Với `MessageDigest`, đọc `getProvider()` sau `getInstance`; với `Signature` hoặc `Cipher`, ưu tiên kiểm tra sau `init` tương ứng.
4. Kiểm tra khóa/tham số và ngoại lệ tại đúng điểm phát sinh; nếu kết quả không khớp thứ tự chung, kiểm tra chính sách ưu tiên theo thuật toán của JDK.
5. Nếu buộc dùng provider cụ thể, xác minh tên, dịch vụ, deployment và hành vi thao tác thực tế trên môi trường đích.

Tên provider là thông tin chẩn đoán hữu ích, nhưng **không phải hợp đồng di động giữa mọi JDK**. `SUN` trong một bản OpenJDK không phải đảm bảo bắt buộc ở một Java runtime khác.

## 8. Khi nào để tự chọn, khi nào khóa provider?

**Ưu tiên để JCA tự chọn** (`getInstance(algorithm)`) khi bài toán cần thuật toán chuẩn và tính di động giữa các môi trường. Cách này cho phép JVM dùng provider đã cấu hình, bao gồm các bản triển khai được tối ưu cho môi trường đó.

**Chỉ định provider** (`getInstance(algorithm, name/object)`) khi yêu cầu nghiệp vụ hoặc an ninh thực sự cần một triển khai xác định, ví dụ khóa chỉ dùng được qua HSM, cơ chế PKCS#11, chứng nhận cần kiểm chứng hoặc quy tắc triển khai bắt buộc. Khi đó cần làm rõ cơ chế cài provider, thứ tự đăng ký, quản lý khóa, ngoại lệ và **không tự động fallback ngoài chính sách**.

Không dùng việc thay provider để thay thế việc chọn thuật toán, mode và tham số an toàn. Ví dụ, chọn đúng provider vẫn không làm một transformation `AES` thiếu mode/padding trở nên rõ ràng.

## 9. Câu hỏi tự kiểm tra

1. Danh sách có P1 (chỉ `Signature/SHA256withRSA`), P2 (chỉ `MessageDigest/SHA-256`) và P3 (cả hai). `MessageDigest.getInstance("SHA-256")` thường chọn ai? **P2**, nếu không có ngoại lệ ưu tiên theo thuật toán hoặc điều kiện triển khai đặc biệt.
2. `MessageDigest.getInstance("SHA-256", "P1")` có tự chuyển sang P2 không? **Không**; nếu P1 không hỗ trợ `MessageDigest/SHA-256` sẽ ném `NoSuchAlgorithmException`.
3. `MessageDigest.getInstance("SHA-256", providerObject)` có yêu cầu providerObject phải đăng ký trong `Security.getProviders()` không? **Không**; overload nhận đối tượng có thể dùng provider chưa đăng ký.
4. Vì sao chỉ nhìn thứ tự từ `Security.getProviders()` chưa đủ kết luận provider thật được dùng? **Vì** phải xét engine/algorithm, khả năng khởi tạo, cấu hình ưu tiên theo thuật toán và có thể cả chọn provider trễ sau `init`.
5. Tại sao không nên gọi `Signature.getProvider()` trước `initSign(key)` chỉ để log? **Vì** một số triển khai có thể chốt provider sớm, bỏ qua lựa chọn dựa trên loại khóa.

## 10. Tài liệu chính thức

- [Oracle JCA Reference Guide (JDK 17)](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html) — kiến trúc engine/provider, đăng ký và thứ tự ưu tiên.
- [MessageDigest API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) — các overload `getInstance`, `getProvider` và ngoại lệ; có ghi chú `jdk.security.provider.preferred`.
- [Security API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html) — `getProviders`, `insertProviderAt`, `addProvider`, `removeProvider`.
- [Signature API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — chu trình `initSign`/`initVerify` và lỗi liên quan đến khóa.

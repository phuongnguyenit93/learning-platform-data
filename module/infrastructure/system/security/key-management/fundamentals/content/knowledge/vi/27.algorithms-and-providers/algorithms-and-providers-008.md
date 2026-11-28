# Provider update

Trong Java Cryptography Architecture (JCA), **provider** là thành phần cung cấp implementation cho các dịch vụ mật mã như `Cipher`, `Signature`, `MessageDigest`, `KeyStore`, `Mac`, `KeyAgreement` và `KEM`. Ứng dụng gọi API chuẩn của Java; provider thực hiện thuật toán cụ thể. Vì vậy, cập nhật provider có thể ảnh hưởng trực tiếp đến cách hệ thống tạo khóa, mã hóa, ký số, xác minh chữ ký và đọc kho khóa.

Một bản cập nhật provider có thể sửa lỗi bảo mật, bổ sung thuật toán, thay đổi cách xử lý tham số hoặc cải thiện hiệu năng. Tuy nhiên, nó cũng có thể làm thay đổi hành vi tương thích, thứ tự lựa chọn implementation hoặc khả năng đọc dữ liệu cũ. Trong hệ thống quản lý khóa, cập nhật provider cần được kiểm soát như một thay đổi mật mã có ảnh hưởng đến toàn bộ vòng đời khóa.

## 1. Provider trong JCA hoạt động như thế nào?

JCA định nghĩa các API và cơ chế tìm implementation. Provider đăng ký một hoặc nhiều dịch vụ mật mã với tên dịch vụ và tên thuật toán cụ thể. Ví dụ:

| Dịch vụ JCA/JCE | Ví dụ thuật toán hoặc transformation |
|---|---|
| `Cipher` | `AES/GCM/NoPadding`, `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` |
| `Signature` | `SHA256withRSA`, `Ed25519` |
| `MessageDigest` | `SHA-256`, `SHA-384` |
| `KeyStore` | `PKCS12`, `JKS`, `JCEKS` |
| `Mac` | `HmacSHA256` |
| `KeyAgreement` | `ECDH` |
| `KEM` | `DHKEM` trên JDK/provider có hỗ trợ API và thuật toán tương ứng |

Một provider có thể cung cấp nhiều dịch vụ; một dịch vụ/thuật toán cũng có thể được cung cấp bởi nhiều provider. JCA tra cứu implementation dựa trên tên dịch vụ, thuật toán, khóa và tham số. Provider có thể được tích hợp sẵn trong JDK hoặc được cài thêm từ thư viện hay thiết bị mật mã bên ngoài.

Các provider thường gặp trong JDK Oracle/OpenJDK gồm `SUN`, `SunRsaSign`, `SunEC`, `SunJSSE`, `SunJCE` và các provider khác. Tên và dịch vụ cụ thể phụ thuộc bản phân phối, phiên bản JDK và cấu hình. Không nên giả định mọi môi trường đều có cùng provider hoặc cùng tập thuật toán.

## 2. Phân biệt cập nhật provider và đăng ký provider

Hai công việc thường bị gọi chung là “provider update”, nhưng chúng giải quyết hai vấn đề khác nhau:

| Công việc | Thay đổi | Ví dụ |
|---|---|---|
| Cập nhật phần mềm provider | Thay phiên bản JAR, module, native library hoặc bản JDK chứa provider | Nâng thư viện provider bên thứ ba từ bản đã triển khai lên bản vá mới |
| Đăng ký/cấu hình provider | Thay đổi provider nào được JVM nhận diện và thứ tự tra cứu | Thêm provider HSM vào danh sách hoặc đưa provider đã cài lên vị trí ưu tiên |

Gọi `Security.addProvider()` không tải xuống hay cập nhật mã thư viện provider. Phương thức này chỉ đăng ký một đối tượng `Provider` đã có sẵn trong tiến trình. Tương tự, đổi thứ tự provider không thay thế phiên bản JAR hoặc sửa lỗi bên trong provider.

Nếu provider được đóng gói trong JDK, việc cập nhật thường gắn với việc cập nhật JDK theo bản phân phối và chính sách vá lỗi của tổ chức. Nếu provider là thư viện bên ngoài, cần cập nhật artifact, module hoặc gói cài đặt đúng theo hướng dẫn của nhà cung cấp.

## 3. Kiểm kê provider đang hoạt động

Trước khi cập nhật, cần xác định JVM đang nạp những provider nào, phiên bản nào và provider nào cung cấp dịch vụ mà ứng dụng đang sử dụng.

```java
import java.security.Provider;
import java.security.Security;

public final class ProviderInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s | version=%s | info=%s%n",
                    provider.getName(),
                    provider.getVersionStr(),
                    provider.getInfo());

            for (Provider.Service service : provider.getServices()) {
                System.out.printf(
                        "  %s.%s%n",
                        service.getType(),
                        service.getAlgorithm());
            }
        }
    }
}
```

`Security.getProviders()` trả về danh sách provider đang đăng ký theo thứ tự ưu tiên. `Provider.getServices()` liệt kê các dịch vụ mà provider công bố. Kết quả kiểm kê nên được lưu cùng thông tin phiên bản JDK, hệ điều hành, kiến trúc CPU, cấu hình provider và phiên bản thư viện ứng dụng để phục vụ đối chiếu sau này.

Không nên chỉ dựa vào tên provider. Cần xác định đúng implementation thực tế cho từng thao tác. Ví dụ, một ứng dụng có thể dùng provider này cho `KeyStore` nhưng dùng provider khác cho `Cipher`.

## 4. Cách JCA chọn provider

Khi ứng dụng gọi `getInstance()` mà không chỉ định provider, JCA tìm implementation phù hợp trong danh sách provider đã đăng ký và theo quy tắc lựa chọn của runtime. Thứ tự provider có thể ảnh hưởng đến implementation được chọn khi nhiều provider cùng cung cấp một dịch vụ/thuật toán.

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
System.out.println(cipher.getProvider().getName());
```

Để yêu cầu một provider cụ thể, ứng dụng có thể chỉ định tên hoặc đối tượng provider:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", "SunJCE");
// Hoặc dùng một đối tượng Provider đã được kiểm tra:
Cipher anotherCipher = Cipher.getInstance("AES/GCM/NoPadding", provider);
```

Chỉ định provider tường minh giúp ứng dụng dự đoán implementation được dùng, nhưng làm tăng sự phụ thuộc vào provider đó. Nếu provider không có trong môi trường hoặc không hỗ trợ transformation/khóa/tham số cần thiết, thao tác sẽ thất bại. Cần có kiểm tra khả năng hỗ trợ và kế hoạch tương thích rõ ràng.

Với thao tác nhạy cảm như ký số, giải mã khóa hoặc dùng khóa HSM, nên cân nhắc lựa chọn provider tường minh sau khi xác minh nguồn gốc và cấu hình. Với các dịch vụ phổ thông cần khả năng thay thế linh hoạt, có thể để JCA lựa chọn theo thứ tự đã được kiểm soát.

## 5. Đăng ký, chèn và gỡ provider trong runtime

Java cung cấp lớp `java.security.Security` để quản lý danh sách provider trong tiến trình.

```java
import java.security.Provider;
import java.security.Security;

public final class ProviderRegistration {
    public static void register(Provider provider) {
        int position = Security.addProvider(provider);
        if (position == -1) {
            throw new IllegalStateException(
                    "Provider is already registered: " + provider.getName());
        }
        System.out.println("Registered at position: " + position);
    }

    public static void insertFirst(Provider provider) {
        int position = Security.insertProviderAt(provider, 1);
        if (position == -1) {
            throw new IllegalStateException(
                    "Provider is already registered: " + provider.getName());
        }
        System.out.println("Inserted at position: " + position);
    }

    public static void remove(String providerName) {
        Security.removeProvider(providerName);
    }
}
```

Ý nghĩa các API:

- `Security.addProvider(provider)`: thêm provider vào cuối danh sách ưu tiên.
- `Security.insertProviderAt(provider, position)`: chèn provider tại vị trí yêu cầu; vị trí bắt đầu từ 1.
- `Security.removeProvider(name)`: gỡ provider có tên tương ứng khỏi danh sách đăng ký.
- `Security.getProvider(name)`: lấy provider đang đăng ký theo tên; trả về `null` nếu không tìm thấy.
- `Security.getProviders()`: lấy danh sách provider hiện được đăng ký.

`addProvider()` và `insertProviderAt()` trả về vị trí đăng ký nếu thành công; trả về `-1` nếu provider đã được đăng ký. Việc thêm provider không bảo đảm mọi thuật toán của nó sẽ được chọn: thứ tự và khả năng hỗ trợ cụ thể vẫn quyết định kết quả tra cứu.

Không nên gỡ provider đang được ứng dụng hoặc thư viện khác sử dụng khi tiến trình còn hoạt động. Các đối tượng JCA đã tạo trước đó không tự chuyển sang implementation mới, còn các thao tác tạo mới có thể gặp hành vi khác sau khi danh sách provider thay đổi. Cấu hình runtime nên được thực hiện trong giai đoạn khởi tạo ứng dụng và được kiểm thử trước.

## 6. Cấu hình provider trong java.security

JDK cho phép cấu hình provider mặc định trong tệp bảo mật `java.security`. Trên các bản JDK hiện đại, tệp thường nằm tại:

```text
$JAVA_HOME/conf/security/java.security
```

Các bản JDK cũ có thể đặt tệp ở vị trí khác. Trong tệp cấu hình, các mục dạng `security.provider.N` khai báo provider và thứ tự ưu tiên. Ví dụ minh họa:

```properties
security.provider.1=SUN
security.provider.2=SunRsaSign
security.provider.3=SunEC
security.provider.4=SunJSSE
security.provider.5=SunJCE
```

Đây chỉ là ví dụ về cấu trúc thuộc tính; không dùng danh sách này để thay thế cấu hình mặc định của một JDK cụ thể. Tệp cấu hình thực tế có thể chứa provider bổ sung, tham số cấu hình HSM hoặc các thuộc tính bảo mật khác. Cần giữ nguyên những mục do bản phân phối và tổ chức quản lý.

Một số provider bên ngoài cần cấu hình riêng, chẳng hạn đường dẫn native library, thông tin thiết bị hoặc tên slot. Cú pháp phụ thuộc nhà cung cấp và phiên bản. Không chép cấu hình từ môi trường khác nếu chưa xác minh đường dẫn, quyền truy cập và khả năng tương thích.

Thay đổi `java.security` là thay đổi cấu hình bảo mật ở cấp runtime. Để bảo đảm ứng dụng khởi động với đúng danh sách provider và thứ tự đã định, nên triển khai cấu hình cùng JDK/application image rồi khởi động lại tiến trình. Tránh chỉnh sửa trực tiếp tệp JDK đang được nhiều ứng dụng dùng chung mà không có quản lý cấu hình và kế hoạch quay lui.

## 7. Quy trình cập nhật thư viện provider

Với provider bên ngoài, cập nhật phiên bản thư viện là một thay đổi chuỗi cung ứng phần mềm và mật mã. Một quy trình cơ bản gồm:

1. Xác định provider, phiên bản hiện tại, phiên bản mục tiêu và lý do cập nhật.
2. Đọc thông báo bảo mật, ghi chú phát hành và ma trận tương thích từ nhà cung cấp.
3. Lấy artifact từ nguồn phân phối chính thức; xác minh chữ ký, checksum và nguồn gốc gói theo quy trình tổ chức.
4. Kiểm tra tương thích với JDK, hệ điều hành, kiến trúc CPU, module system, native library và các thư viện phụ thuộc.
5. Cập nhật dependency lockfile, manifest hoặc cấu hình triển khai để cố định phiên bản đã phê duyệt.
6. Kiểm thử trên môi trường staging với đúng JDK, provider configuration và loại khóa đang sử dụng.
7. Triển khai theo từng nhóm máy chủ hoặc vùng dịch vụ; giám sát lỗi mật mã và hiệu năng.
8. Giữ artifact và cấu hình phiên bản trước đó để có thể quay lui theo quy trình đã kiểm thử.

Không tải JAR provider tùy tiện từ kho không xác định hoặc tự động thay JAR trong thư mục cài đặt đang chạy. Provider có thể thực thi mã native hoặc xử lý trực tiếp khóa riêng; một gói giả mạo có thể chiếm quyền ký, giải mã hoặc trích xuất bí mật của ứng dụng.

## 8. Kiểm thử sau khi cập nhật

Kiểm thử phải xác nhận provider mới cung cấp đúng dịch vụ, dùng đúng thuật toán và vẫn xử lý được dữ liệu hiện có. Tối thiểu nên kiểm tra:

| Nhóm kiểm thử | Nội dung |
|---|---|
| Đăng ký | Provider xuất hiện đúng tên, phiên bản và vị trí dự kiến |
| Khả năng cung cấp dịch vụ | Các thuật toán bắt buộc có thể được tạo bằng `getInstance()` |
| Lựa chọn implementation | `getProvider()` trả về provider mong đợi khi không chỉ định hoặc khi chỉ định tường minh |
| Chức năng mật mã | Mã hóa/giải mã, ký/xác minh, MAC và key agreement chạy với test vector đã được phê duyệt |
| Tương thích khóa | Đọc được keystore/certificate và sử dụng được khóa đã tạo từ phiên bản trước |
| Tham số | Padding, mode, IV/nonce, key size, curve và thuật toán digest giữ đúng chính sách |
| Lỗi và biên | Sai khóa, sai tham số, dữ liệu bị sửa và provider không khả dụng được xử lý an toàn |
| Hiệu năng | Độ trễ, throughput, CPU, bộ nhớ và tải HSM nằm trong ngưỡng vận hành |
| Khởi động lại | Ứng dụng khởi động lại và đăng ký provider ổn định với cấu hình mới |

Ví dụ kiểm tra provider thực tế của một transformation:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Provider selected = cipher.getProvider();

if (!"SunJCE".equals(selected.getName())) {
    throw new IllegalStateException(
            "Unexpected provider: " + selected.getName());
}
```

Tên `SunJCE` trong ví dụ chỉ là điều kiện minh họa cho một môi trường cụ thể. Trong hệ thống thực tế, thay bằng provider được phê duyệt hoặc kiểm tra capability thay vì cố định tên provider không phù hợp với kiến trúc.

## 9. Tác động đến khóa và dữ liệu đã lưu

Cập nhật provider không đồng nghĩa với tạo khóa mới hoặc xoay vòng khóa. Giá trị toán học của khóa không tự thay đổi chỉ vì thư viện provider được nâng phiên bản. Tuy nhiên, provider mới có thể thay đổi thuật toán bảo vệ entry, cách xử lý định dạng, thuật toán mặc định hoặc chính sách từ chối các thuật toán yếu.

Trước khi cập nhật, cần xác định:

- Ứng dụng đang lưu khóa ở JKS, JCEKS, PKCS12, HSM hay một kho riêng của provider.
- Khóa được tạo bởi provider nào và có phụ thuộc định dạng hoặc metadata riêng không.
- Provider mới có thể đọc các keystore và entry được tạo từ phiên bản cũ không.
- Các thuật toán cũ có bị vô hiệu hóa hoặc bị giới hạn bởi security properties không.
- Có cần chuyển đổi định dạng hoặc tạo khóa mới theo kế hoạch riêng không.

Không nên chuyển đổi keystore hoặc xuất/nhập khóa trong cùng một bước nâng cấp provider nếu chưa có kế hoạch riêng và bản sao lưu đã kiểm tra. Tách biệt thay đổi provider với thay đổi định dạng hoặc xoay vòng khóa giúp khoanh vùng lỗi và dễ quay lui hơn.

## 10. Thứ tự provider và rủi ro thay đổi mặc định

Đưa một provider lên đầu danh sách có thể khiến JCA chọn implementation của provider đó cho các lệnh `getInstance()` không chỉ định provider. Điều này có thể thay đổi hành vi của ứng dụng mà không cần sửa mã nguồn.

Rủi ro thường gặp:

- Provider mới không hỗ trợ đầy đủ transformation hoặc tham số mà ứng dụng đang dùng.
- Hai provider có cùng tên thuật toán nhưng khác giới hạn key size, cách mã hóa tham số hoặc cách xử lý lỗi.
- Provider bên thứ ba nhận một yêu cầu mà trước đó được xử lý bởi provider tích hợp sẵn.
- Một số thư viện phụ thuộc vào provider cụ thể hoặc thứ tự provider, dẫn đến lỗi khi cấu hình toàn JVM thay đổi.
- Gỡ provider cũ làm mất khả năng đọc kho khóa hoặc thực hiện thao tác với khóa được tạo từ trước.

Vì vậy, chỉ thay đổi thứ tự khi có yêu cầu kiến trúc rõ ràng và đã kiểm thử toàn bộ ứng dụng. Nếu chỉ một thành phần cần provider đặc biệt, ưu tiên chỉ định provider cho đúng thao tác đó thay vì thay đổi thứ tự toàn cục.

## 11. Provider FIPS và yêu cầu tuân thủ

Một số hệ thống cần provider hoạt động theo chế độ FIPS hoặc theo hồ sơ tuân thủ mật mã cụ thể. Cập nhật provider trong các môi trường này cần thận trọng hơn vì trạng thái chứng nhận có thể gắn với phiên bản phần mềm, cấu hình, nền tảng và chế độ vận hành chính xác.

Trước khi nâng cấp, cần kiểm tra tài liệu chính thức của nhà cung cấp và hồ sơ chứng nhận có liên quan. Không suy luận rằng một phiên bản mới tự động nằm trong phạm vi chứng nhận của phiên bản trước, hoặc chỉ cần provider có tên chứa “FIPS” là mọi thao tác đều chạy trong chế độ được phê duyệt.

Kiểm thử cần xác nhận ứng dụng thực sự sử dụng đúng provider, đúng chế độ, đúng thuật toán được cho phép và không âm thầm chuyển sang provider khác khi gặp lỗi. Log và bằng chứng cấu hình cần đủ để phục vụ kiểm toán nhưng không được chứa khóa hoặc bí mật xác thực.

## 12. Rollback và ứng phó khi cập nhật thất bại

Nếu phiên bản mới gây lỗi, cần có khả năng quay lại artifact và cấu hình đã được xác minh. Trước khi triển khai nên lưu:

- Phiên bản JDK và provider trước/sau cập nhật.
- Danh sách provider cùng thứ tự ưu tiên.
- Cấu hình `java.security`, cấu hình provider bên ngoài và tham số HSM liên quan.
- Dependency lockfile, checksum/chữ ký artifact và manifest triển khai.
- Kết quả kiểm thử với các keystore và khóa đại diện.

Rollback cần được thử trong staging. Nếu provider mới đã ghi lại keystore bằng định dạng hoặc thuật toán mà provider cũ không đọc được, chỉ khôi phục JAR cũ có thể chưa đủ. Khi đó cần khôi phục bản sao keystore tương thích hoặc dùng quy trình chuyển đổi đã được chuẩn bị. Không ghi đè kho khóa gốc bằng một bản sao chưa được xác minh.

Nếu nghi ngờ provider mới bị giả mạo hoặc có lỗ hổng làm lộ khóa, cần coi đây là sự cố an ninh: cô lập phiên bản bị ảnh hưởng, xác định thao tác mật mã và khóa có thể đã bị truy cập, đánh giá nhu cầu xoay vòng hoặc thu hồi, bảo toàn log kiểm toán và triển khai phiên bản đã được xác minh.

## 13. Checklist cập nhật Java Security Provider

- Kiểm kê provider, phiên bản, dịch vụ, thuật toán và thứ tự ưu tiên hiện tại.
- Phân biệt cập nhật mã provider với đăng ký/cấu hình provider trong JVM.
- Xác minh nguồn tải, chữ ký, checksum và nguồn gốc artifact.
- Kiểm tra tương thích JDK, hệ điều hành, native library, module và HSM.
- Đọc release notes, thông báo bảo mật và yêu cầu FIPS/compliance nếu có.
- Cố định phiên bản dependency và cấu hình provider đã phê duyệt.
- Kiểm thử thuật toán, transformation, key size, tham số, keystore cũ và hiệu năng.
- Kiểm tra provider thực tế qua `getProvider()` và danh sách `Security.getProviders()`.
- Hạn chế thay đổi thứ tự provider toàn cục; chỉ định provider cụ thể khi cần.
- Triển khai theo giai đoạn, giám sát lỗi và giữ phương án rollback đã kiểm thử.
- Không nhầm cập nhật provider với xoay vòng khóa; thực hiện chuyển đổi khóa theo quy trình riêng.
- Khởi động lại và xác minh cấu hình runtime sau khi thay đổi thư viện hoặc `java.security`.

Cập nhật Java Security Provider là một phần của quản trị nền tảng mật mã. Quy trình tốt phải kiểm soát cả mã implementation, cấu hình đăng ký, thứ tự lựa chọn, tương thích dữ liệu khóa và bằng chứng kiểm toán. Khi những yếu tố này được kiểm tra cùng nhau, tổ chức có thể tiếp nhận bản vá bảo mật và thuật toán mới mà vẫn duy trì tính toàn vẹn, tính sẵn sàng và khả năng sử dụng khóa trong toàn hệ thống.

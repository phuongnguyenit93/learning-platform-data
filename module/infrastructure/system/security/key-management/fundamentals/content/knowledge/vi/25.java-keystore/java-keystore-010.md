# KeyStore password

Một Java KeyStore có thể chứa khóa riêng, khóa bí mật đối xứng và chứng thư tin cậy. Để đọc hoặc cập nhật kho, ứng dụng thường phải cung cấp mật khẩu. Tuy nhiên, trong Java có nhiều thao tác nhận tham số mật khẩu với mục đích khác nhau. Hiểu đúng **KeyStore password** giúp tránh nhầm mật khẩu mở kho với mật khẩu bảo vệ từng khóa, đồng thời thiết kế được quy trình cấp phát, lưu trữ, thay đổi và khôi phục thông tin xác thực an toàn.

Trong quản lý khóa mật mã, mật khẩu của keystore là một phần của cơ chế bảo vệ dữ liệu khóa khi lưu trữ. Nó cần được quản lý như một bí mật có giá trị cao: giới hạn người và dịch vụ được truy cập, tránh lưu cạnh tệp keystore, kiểm toán việc sử dụng và có kế hoạch xử lý khi bị lộ. Mật khẩu tốt không thay thế quyền truy cập tệp, bảo vệ tiến trình đang chạy hay các cơ chế chuyên dụng như KMS/HSM.

## 1. KeyStore password là gì?

`KeyStore password` là mật khẩu được truyền cho các thao tác nạp hoặc lưu một đối tượng `KeyStore`. Với API Java, hai thao tác chính là:

```java
keyStore.load(inputStream, storePassword);
keyStore.store(outputStream, storePassword);
```

Mật khẩu này được provider sử dụng theo cơ chế của loại keystore để kiểm tra tính toàn vẹn và/hoặc bảo vệ dữ liệu trong kho. Cách sử dụng chính xác phụ thuộc vào định dạng và provider. Vì vậy, không nên suy luận rằng mọi keystore đều dùng store password theo cùng một cách, hoặc rằng mật khẩu này luôn mã hóa toàn bộ nội dung tệp.

Với nhiều loại keystore, chứng thư công khai không cần mã hóa vì bản thân chứng thư không chứa khóa riêng. Khóa riêng và khóa bí mật cần được bảo vệ riêng theo cơ chế của từng loại entry. Một số định dạng dùng store password để bảo vệ tính toàn vẹn của toàn kho, trong khi entry password được dùng để mã hóa hoặc giải mã khóa. Một số định dạng/provider kết hợp các vai trò này hoặc yêu cầu cùng một mật khẩu.

## 2. Phân biệt store password và key password

Trong Java KeyStore, hai khái niệm thường gặp là:

| Khái niệm | Phạm vi | API hoặc công cụ thường dùng |
|---|---|---|
| **Keystore password** (store password) | Nạp/lưu kho; kiểm tra tính toàn vẹn và/hoặc bảo vệ cấu trúc kho theo provider | `KeyStore.load`, `KeyStore.store`, `keytool -storepass` |
| **Key password** (entry password) | Bảo vệ một entry chứa khóa riêng hoặc khóa bí mật | `KeyStore.getKey`, `KeyStore.getEntry`, `KeyStore.setKeyEntry`, `keytool -keypass` |

Ví dụ một kho có thể chứa:

- Alias `tls-server`: `PrivateKeyEntry` gồm khóa riêng TLS và chuỗi chứng thư.
- Alias `data-aes`: `SecretKeyEntry` chứa khóa AES.
- Alias `company-root`: `TrustedCertificateEntry` chứa chứng thư CA.

Store password được dùng khi nạp hoặc lưu kho. Key password được dùng để lấy hoặc đặt khóa trong entry tương ứng. `TrustedCertificateEntry` chỉ chứa chứng thư công khai nên không có khóa riêng cần bảo vệ bằng key password.

Hai mật khẩu có thể giống nhau hoặc khác nhau. Dùng mật khẩu riêng cho entry có thể tách quyền mở kho và quyền sử dụng một khóa, nhưng chỉ có ý nghĩa khi định dạng/provider hỗ trợ và ứng dụng thực sự kiểm soát hai thông tin này độc lập. Nếu provider yêu cầu cùng mật khẩu, việc truyền hai chuỗi khác nhau có thể khiến thao tác lưu hoặc đọc entry thất bại.

## 3. Mật khẩu được dùng ở những thao tác nào?

Các API của `KeyStore` nhận mật khẩu tại những thời điểm khác nhau:

| API | Vai trò của mật khẩu |
|---|---|
| `load(InputStream, char[])` | Nạp kho; provider có thể dùng mật khẩu để kiểm tra tính toàn vẹn hoặc giải mã dữ liệu kho. |
| `store(OutputStream, char[])` | Ghi kho; provider dùng mật khẩu để tạo cơ chế bảo vệ toàn vẹn và/hoặc bảo vệ dữ liệu theo định dạng. |
| `getKey(alias, char[])` | Lấy khóa riêng hoặc khóa bí mật thuộc alias; mật khẩu bảo vệ entry đó. |
| `getEntry(alias, ProtectionParameter)` | Lấy entry với thông tin bảo vệ được truyền qua `ProtectionParameter`, thường là `PasswordProtection`. |
| `setKeyEntry(alias, key, char[], chain)` | Thêm khóa cùng chuỗi chứng thư; mật khẩu bảo vệ khóa entry theo provider. |
| `setEntry(alias, entry, ProtectionParameter)` | Thêm entry với tham số bảo vệ được chỉ định. |

Đừng truyền nhầm key password vào `load()` rồi cho rằng ứng dụng đã xác thực được khóa trong entry. `load()` xử lý việc nạp kho; ứng dụng vẫn cần cung cấp thông tin bảo vệ phù hợp khi truy xuất entry có khóa.

Một trường hợp đặc biệt là truyền `null` vào `load()`. Theo hợp đồng API, điều này cho phép provider bỏ qua kiểm tra tính toàn vẹn khi định dạng hỗ trợ cách nạp đó. Không nên dùng `null` để né yêu cầu mật khẩu trong một kho cần bảo vệ. Khả năng chấp nhận mật khẩu rỗng hoặc `null`, cũng như ý nghĩa của chúng, phụ thuộc định dạng và provider. Hãy kiểm tra tài liệu của provider và chính sách ứng dụng trước khi sử dụng.

## 4. Hành vi khác nhau giữa JKS, JCEKS và PKCS12

Store password và key password không phải một quy tắc cố định áp dụng đồng nhất cho mọi định dạng. Ví dụ thường gặp trong các provider Java:

| Loại keystore | Store password | Key/entry password | Lưu ý |
|---|---|---|---|
| JKS truyền thống | Dùng để kiểm tra tính toàn vẹn của kho | Có thể dùng riêng để bảo vệ `PrivateKeyEntry` | Mật khẩu kho và mật khẩu khóa có thể khác nhau. |
| JCEKS của SunJCE | Dùng trong cơ chế kiểm tra tính toàn vẹn của kho | Dùng để bảo vệ khóa bí mật hoặc khóa riêng trong entry | Hỗ trợ `SecretKeyEntry`; thuật toán bảo vệ phụ thuộc provider và phiên bản JDK. |
| PKCS12 của provider SunPKCS12 | Thường bảo vệ MAC/tính toàn vẹn của kho | Trong nhiều cấu hình Java, mật khẩu khóa phải trùng với store password | Hành vi cụ thể phụ thuộc phiên bản JDK, provider và cấu hình. |

PKCS12 là định dạng chuẩn được hỗ trợ rộng rãi và là loại mặc định của `KeyStore` trong nhiều bản Java hiện đại khi ứng dụng không chỉ định loại khác. Tuy nhiên, việc chuẩn PKCS12 có thể biểu diễn các cơ chế bảo vệ khác nhau không có nghĩa mọi provider Java đều hỗ trợ mọi tổ hợp mật khẩu. Trước khi chuyển đổi hoặc đặt mật khẩu riêng cho từng entry, hãy kiểm tra chính xác provider và phiên bản JDK đang chạy.

Một tệp có đuôi `.jks`, `.jceks` hoặc `.p12` cũng không tự chứng minh định dạng bên trong. Khi nạp, ứng dụng cần chỉ định loại keystore đúng, hoặc dùng cơ chế phát hiện định dạng có kiểm soát nếu kiến trúc hỗ trợ.

## 5. Cách đặt và sử dụng mật khẩu bằng Java

Ví dụ sau nạp một kho JKS và lấy khóa theo alias. `storePassword` và `keyPassword` được truyền từ bên gọi, nơi có thể lấy chúng từ secret manager hoặc một cơ chế cấp phát bí mật đã được kiểm soát.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;

public final class KeyStorePasswordExample {
    public static Key loadPrivateKey(
            Path keyStoreFile,
            char[] storePassword,
            char[] keyPassword) throws Exception {

        KeyStore keyStore = KeyStore.getInstance("JKS");
        try (InputStream input = Files.newInputStream(keyStoreFile)) {
            keyStore.load(input, storePassword);
        }

        Key key = keyStore.getKey("tls-server", keyPassword);
        if (key == null) {
            throw new IllegalStateException("Key alias was not found");
        }
        return key;
    }
}
```

Khi lưu một khóa riêng mới vào JKS, ứng dụng có thể dùng `setKeyEntry()` để chỉ định key password, sau đó dùng store password khi ghi kho:

```java
keyStore.setKeyEntry(
        "tls-server",
        privateKey,
        keyPassword,
        certificateChain);

try (OutputStream output = Files.newOutputStream(keyStoreFile)) {
    keyStore.store(output, storePassword);
}
```

Ví dụ này giả định provider JKS cho phép hai mật khẩu riêng biệt. Với PKCS12 hoặc provider khác, hãy kiểm tra yêu cầu tương thích; có thể cần dùng cùng một mật khẩu cho store và private key entry.

Nếu dùng `getEntry()`, có thể biểu diễn mật khẩu entry bằng `KeyStore.PasswordProtection`:

```java
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(keyPassword);
try {
    KeyStore.Entry entry = keyStore.getEntry("tls-server", protection);
    if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
        throw new IllegalStateException("Unexpected entry type");
    }
    KeyStore.PrivateKeyEntry privateKeyEntry =
            (KeyStore.PrivateKeyEntry) entry;
    // Sử dụng privateKeyEntry theo mục đích đã được cấp quyền.
} finally {
    protection.destroy();
}
```

`PasswordProtection` là một đối tượng quản lý tham số bảo vệ entry. Gọi `destroy()` khi hoàn tất để xóa bản sao mật khẩu mà đối tượng đang quản lý. Ứng dụng cũng nên xóa mảng mật khẩu do mình sở hữu trong khối `finally`, ví dụ:

```java
java.util.Arrays.fill(storePassword, '\0');
java.util.Arrays.fill(keyPassword, '\0');
```

Việc ghi đè mảng giúp giảm thời gian bí mật tồn tại trong vùng nhớ do ứng dụng kiểm soát, nhưng không bảo đảm xóa mọi bản sao do JVM, provider hoặc thư viện khác tạo ra. Không log `char[]`, không chuyển mật khẩu thành `String` nếu không cần thiết vì `String` là bất biến và không thể chủ động ghi đè nội dung.

## 6. Quản lý bằng keytool

`keytool` cho phép chỉ định store password và key password bằng các tùy chọn khác nhau. Nếu bỏ qua tùy chọn mật khẩu, công cụ thường có thể hỏi tương tác trong terminal, tùy lệnh và phiên bản.

Liệt kê nội dung kho:

```bash
keytool -list -v \
  -keystore server.jks \
  -storetype JKS
```

Tạo cặp khóa và chứng thư tự ký trong JKS:

```bash
keytool -genkeypair \
  -alias tls-server \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -keystore server.jks \
  -storetype JKS
```

Khi được hỏi, nhập store password và key password theo chính sách. Trong JKS, hai mật khẩu có thể khác nhau. Khi thao tác với PKCS12, cần tuân theo yêu cầu của provider; không giả định `-keypass` luôn được chấp nhận như với JKS.

Một số lệnh quản trị mật khẩu:

```bash
# Thay mật khẩu của keystore
keytool -storepasswd -keystore server.jks -storetype JKS

# Thay mật khẩu bảo vệ khóa của alias (nếu loại keystore hỗ trợ)
keytool -keypasswd -alias tls-server -keystore server.jks -storetype JKS
```

Không truyền mật khẩu thật trực tiếp bằng `-storepass` hoặc `-keypass` trong script, CI log hay lịch sử shell nếu có nguy cơ lộ tham số tiến trình. Ưu tiên cơ chế hỏi tương tác trong terminal quản trị an toàn hoặc cách cấp bí mật được nền tảng triển khai hỗ trợ. Một số tùy chọn `keytool` cho phép lấy mật khẩu từ file hoặc biến môi trường, nhưng chúng cũng cần được bảo vệ vì người có quyền đọc file hoặc môi trường tiến trình có thể lấy được bí mật.

## 7. Chọn mật khẩu và bảo vệ khỏi đoán ngoại tuyến

Kẻ tấn công có thể sao chép một tệp keystore rồi thử đoán mật khẩu ngoại tuyến mà không cần truy cập ứng dụng đang chạy. Vì vậy, giới hạn số lần đăng nhập ở giao diện ứng dụng không ngăn được việc đoán mật khẩu trên bản sao tệp.

Các nguyên tắc chọn mật khẩu:

- Dùng mật khẩu dài, khó đoán và được tạo từ bộ sinh mật khẩu ngẫu nhiên hoặc secret manager.
- Ưu tiên entropy thực tế và độ dài hơn các quy tắc thay thế ký tự hình thức.
- Không tái sử dụng mật khẩu tài khoản người dùng, mật khẩu cơ sở dữ liệu hoặc mật khẩu giữa các môi trường.
- Không dùng tên ứng dụng, tên máy chủ, ngày tháng, alias hoặc chuỗi có thể suy ra từ mã nguồn làm mật khẩu.
- Không đặt mật khẩu mặc định dùng chung cho mọi bản cài đặt.
- Đổi mật khẩu ngay khi có bằng chứng hoặc nghi ngờ bị lộ; đánh giá cả các bản sao keystore và bản sao lưu.

Mật khẩu mạnh vẫn phụ thuộc thuật toán dẫn xuất khóa, salt, số vòng lặp và cơ chế bảo vệ mà provider sử dụng. Các tham số này có thể khác nhau giữa JKS, JCEKS, PKCS12 và các phiên bản JDK. Hãy dùng cấu hình được hỗ trợ và còn phù hợp với chính sách mật mã của tổ chức; không thể khắc phục một cơ chế bảo vệ lỗi thời chỉ bằng cách kéo dài mật khẩu.

## 8. Lưu trữ, cấp phát và kiểm soát truy cập

Không lưu store password ngay cạnh tệp keystore trong cùng thư mục hoặc cùng gói triển khai. Nếu kẻ tấn công lấy được cả hai, lớp bảo vệ bằng mật khẩu mất tác dụng. Một quy trình phù hợp thường có các bước:

1. Tạo mật khẩu ngẫu nhiên khi khởi tạo môi trường hoặc kho khóa.
2. Lưu mật khẩu trong secret manager hoặc kho bí mật có kiểm soát truy cập.
3. Cấp quyền cho đúng service identity cần nạp keystore; tránh dùng tài khoản cá nhân hoặc tài khoản dùng chung.
4. Cấp mật khẩu vào tiến trình qua kênh được bảo vệ, hạn chế ghi ra đĩa và log.
5. Ghi audit việc đọc bí mật, thay đổi quyền, thay mật khẩu và khôi phục.
6. Thu hồi quyền truy cập khi dịch vụ, nhân sự hoặc môi trường không còn cần sử dụng kho.

Tệp keystore cũng cần quyền filesystem tối thiểu. Chỉ tài khoản dịch vụ cần thiết mới được đọc tệp; quyền ghi chỉ cấp cho quy trình quản trị hoặc tiến trình thực sự phải cập nhật kho. Bản sao lưu, snapshot, image container và artifact triển khai cần được bảo vệ tương đương bản gốc.

Mật khẩu không phải cơ chế phân quyền theo alias. Nếu nhiều ứng dụng cùng được cấp store password và có thể đọc tệp, chúng có thể có khả năng truy xuất nhiều entry hơn mức cần thiết. Với yêu cầu phân quyền theo khóa, audit từng thao tác và thu hồi quyền tập trung, cần xem xét KMS/HSM thay vì chia sẻ một keystore cùng mật khẩu cho nhiều dịch vụ.

## 9. Đổi mật khẩu khác với xoay vòng khóa

Đây là hai thao tác thường bị nhầm lẫn:

| Thao tác | Điều thay đổi | Điều không tự động thay đổi |
|---|---|---|
| Đổi store password | Bí mật dùng để nạp/lưu kho và kiểm tra toàn vẹn theo provider | Giá trị khóa AES hoặc khóa riêng trong entry |
| Đổi key/entry password | Bí mật bảo vệ một entry khóa, nếu định dạng/provider hỗ trợ | Giá trị toán học của khóa mật mã |
| Xoay vòng khóa | Tạo khóa mật mã mới và chuyển hệ thống sang dùng khóa mới | Không tự động đổi mật khẩu của tệp keystore hoặc xóa bản sao khóa cũ |

Ví dụ, nếu mật khẩu keystore bị lộ nhưng khóa chưa bị lộ, tổ chức có thể thay mật khẩu, kiểm tra bản sao tệp và đánh giá phạm vi truy cập. Nếu chính khóa AES hoặc khóa riêng đã bị lộ, chỉ đổi store password không giải quyết được sự cố. Cần tạo khóa mới, chuyển dữ liệu hoặc danh tính sang khóa mới, thu hồi chứng thư liên quan khi phù hợp và xử lý khóa cũ theo chính sách.

Khi đổi store password, ứng dụng thường nạp kho bằng mật khẩu cũ rồi lưu lại bằng mật khẩu mới. Entry password có thể vẫn giữ nguyên nếu provider cho phép tách hai loại mật khẩu. Nếu provider yêu cầu dùng chung mật khẩu, cần cập nhật quy trình tương ứng và kiểm tra mọi ứng dụng phụ thuộc.

## 10. Sao lưu, khôi phục và xử lý khi mất mật khẩu

Mất store password có thể khiến ứng dụng không nạp được kho hoặc không xác minh được tính toàn vẹn của kho. Mất key password có thể khiến ứng dụng không lấy được khóa trong một entry ngay cả khi nạp kho thành công. Khả năng khôi phục phụ thuộc loại keystore, provider, cấu hình và việc tổ chức có lưu bản sao bí mật an toàn hay không.

Không nên giả định có thể khôi phục mật khẩu từ tệp keystore. Trong một số trường hợp, nếu mất mật khẩu bảo vệ khóa và không có bản sao hoặc cơ chế phục hồi hợp lệ, khóa có thể không còn sử dụng được. Vì vậy:

- Lưu thông tin khôi phục trong hệ thống quản lý bí mật có kiểm soát, tách quyền người yêu cầu và người phê duyệt khi cần.
- Sao lưu keystore cùng metadata về loại keystore, provider, alias và phiên bản ứng dụng; bảo vệ bản sao bằng quyền truy cập và mã hóa phù hợp.
- Kiểm thử khôi phục định kỳ trong môi trường cô lập, bao gồm việc nạp kho và sử dụng được các entry quan trọng.
- Ghi nhận người thực hiện, thời điểm, lý do và kết quả của thao tác khôi phục.
- Khi mất mật khẩu hoặc nghi ngờ bị lộ, đánh giá tác động đến tính sẵn sàng và tính bí mật; nếu không thể khôi phục an toàn, tạo khóa mới và chuyển đổi theo kế hoạch ứng phó.

Sao lưu keystore mà không sao lưu an toàn thông tin cần để giải mã hoặc xác minh nó có thể tạo ra một bản sao không dùng được. Ngược lại, lưu mật khẩu cùng bản sao không kiểm soát làm tăng nguy cơ cả hai bị lấy cắp cùng lúc. Cần thiết kế hai quy trình này như một cặp phụ thuộc nhưng có kiểm soát truy cập phù hợp.

## 11. Khi nào nên dùng KMS hoặc HSM?

KeyStore password phù hợp với mô hình ứng dụng cần đọc một kho khóa dạng tệp và có thể kiểm soát quyền truy cập ở cấp máy chủ. Khi số lượng khóa tăng, nhiều dịch vụ cần dùng chung khóa, hoặc yêu cầu audit và phân quyền trở nên nghiêm ngặt, quản lý mật khẩu tệp có thể trở nên khó vận hành.

KMS có thể quản lý vòng đời khóa, phân quyền theo danh tính dịch vụ, ghi log thao tác, hỗ trợ xoay vòng và cung cấp API mã hóa/giải mã hoặc ký mà ứng dụng không cần tự giữ khóa gốc. HSM bảo vệ khóa trong phần cứng chuyên dụng và có thể hạn chế việc xuất khóa khỏi thiết bị. Một KMS cũng có thể dựa trên HSM để thực hiện thao tác mật mã.

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Ứng dụng Java nhỏ, số lượng entry ít, cần tương thích với kho tệp hiện có | Java KeyStore với quản lý mật khẩu và quyền tệp chặt chẽ |
| Cần định dạng trao đổi rộng giữa Java và công cụ khác | PKCS12, sau khi kiểm thử provider và entry |
| Nhiều dịch vụ cần phân quyền, audit và xoay vòng tập trung | KMS |
| Khóa gốc cần được bảo vệ trong phần cứng hoặc có yêu cầu hạn chế trích xuất | HSM hoặc KMS được hỗ trợ bởi HSM |

Việc dùng KMS/HSM không loại bỏ mọi bí mật phía ứng dụng: ứng dụng vẫn cần xác thực với dịch vụ, bảo vệ token hoặc credential và giới hạn quyền API. Tuy nhiên, mô hình này có thể giảm việc phân phối mật khẩu keystore và khóa thô tới nhiều máy chủ.

## 12. Checklist rà soát KeyStore password

- Xác định loại keystore và provider cụ thể; ghi nhận phiên bản JDK đang chạy.
- Phân biệt store password với key/entry password trong tài liệu vận hành.
- Xác minh provider hỗ trợ mật khẩu riêng hay yêu cầu dùng chung.
- Dùng mật khẩu ngẫu nhiên đủ mạnh; không dùng mặc định hoặc tái sử dụng giữa môi trường.
- Lưu mật khẩu trong secret manager, tách khỏi tệp keystore và giới hạn quyền đọc.
- Tránh ghi mật khẩu vào mã nguồn, log, lịch sử shell, tham số tiến trình hoặc artifact triển khai.
- Kiểm tra quyền đọc/ghi tệp, bản sao lưu, snapshot và pipeline triển khai.
- Xóa mảng `char[]` và hủy `PasswordProtection` khi không còn cần dùng.
- Kiểm thử việc nạp kho, lấy entry, lưu lại và khôi phục bằng thông tin xác thực dự phòng.
- Phân biệt đổi mật khẩu với xoay vòng khóa; xác định quy trình khi mật khẩu hoặc khóa bị lộ.
- Đánh giá KMS/HSM khi cần phân quyền, audit, xoay vòng hoặc bảo vệ khóa tập trung.

Quản lý KeyStore password đúng cách giúp bảo vệ khả năng nạp và sử dụng kho khóa trong suốt vòng đời ứng dụng. Hiệu quả bảo vệ phụ thuộc vào định dạng, provider, cách quản lý entry password, nơi lưu bí mật, quyền truy cập và quy trình khôi phục. Các yếu tố này cần được thiết kế cùng nhau để khóa mật mã luôn được sử dụng đúng người, đúng mục đích và có thể xử lý an toàn khi thông tin xác thực gặp sự cố.

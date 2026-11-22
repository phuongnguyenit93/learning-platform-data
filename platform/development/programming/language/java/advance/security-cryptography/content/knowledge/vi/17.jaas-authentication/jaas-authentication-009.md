# 17.9 Ranh giới giữa cấu hình JAAS với mô hình security provider của JCA

## Mục tiêu học tập

Sau bài này, bạn có thể chỉ ra chính xác thành phần nào quyết định **cách xác thực một chủ thể** và thành phần nào cung cấp **hiện thực thuật toán/dịch vụ bảo mật** trong Java. Bạn cũng có thể giải thích vì sao hai cơ chế đều được gọi là “provider” nhưng không dùng chung một danh sách đăng ký, nhận ra điểm giao đặc biệt ở `Configuration.getInstance(...)` và chẩn đoán lỗi ở đúng lớp.

**Ý chính:** Cấu hình JAAS chọn và phối hợp các `LoginModule` cho một ứng dụng đăng nhập. Mô hình `java.security.Provider` của JCA chọn hiện thực của một dịch vụ theo loại dịch vụ và tên thuật toán. Một `LoginModule` có thể *sử dụng* dịch vụ JCA, nhưng việc đăng ký provider JCA không tự đăng ký hay thay thế `LoginModule`.

## 1. Hai trục mở rộng khác nhau

| Câu hỏi | JAAS (Java Authentication and Authorization Service) | JCA (Java Cryptography Architecture / Java Security provider) |
|---|---|---|
| Đối tượng cần giải quyết | Ai đang đăng nhập, dùng cơ chế xác thực nào, kết hợp các bước xác thực ra sao? | Ai cung cấp hiện thực cho `MessageDigest`, `Signature`, `Cipher`, `KeyStore`, `Mac`, `SecureRandom`…? |
| API khởi đầu thường gặp | `new LoginContext("AppName")` rồi `login()` | `MessageDigest.getInstance("SHA-256")`, `Signature.getInstance("SHA256withRSA")`… |
| Nơi chọn hiện thực | `javax.security.auth.login.Configuration` ánh xạ tên ứng dụng sang danh sách lớp `LoginModule` cùng control flag/options | Danh sách `java.security.Provider` đăng ký các `Provider.Service` theo loại dịch vụ và thuật toán |
| Đơn vị được “cắm” | Lớp triển khai `javax.security.auth.spi.LoginModule` | Một provider đăng ký các hiện thực SPI như `MessageDigestSpi`, `SignatureSpi`, `CipherSpi` |
| Kết quả điển hình | Trạng thái đăng nhập và `Subject` chứa `Principal`/credentials sau khi xác thực thành công | Một engine object có hiện thực thuật toán được chọn, ví dụ `MessageDigest` hoặc `Signature` |
| Quy tắc kết hợp | Thứ tự module và `required`, `requisite`, `sufficient`, `optional` | Thứ tự ưu tiên provider, dịch vụ/thuật toán được hỗ trợ, provider chỉ định rõ nếu có |
| Khi thay đổi cấu hình | Đổi phương pháp hoặc chuỗi xác thực cho entry đăng nhập | Đổi hiện thực cryptography/security service được gọi bởi API JCA |

Vì vậy, “thay đổi nơi kiểm tra danh tính” và “thay đổi thư viện thực hiện chữ ký/giải mã” là hai thao tác khác nhau. Chúng có thể phối hợp trong cùng một luồng xác thực, nhưng không thay thế nhau.

## 2. Cấu hình JAAS điều khiển `LoginContext` như thế nào?

Một cấu hình JAAS thường có dạng sau (ví dụ minh họa cho môi trường **đã có Kerberos**, không tự chạy nếu máy chưa được cấu hình Kerberos):

```text
BackendLogin {
    com.sun.security.auth.module.Krb5LoginModule required
        useTicketCache="true";
};
```

- `BackendLogin` là **tên entry JAAS**. Lời gọi `new LoginContext("BackendLogin")` tra cứu chính tên này, không tra cứu tên provider JCA hay tên thuật toán.
- `com.sun.security.auth.module.Krb5LoginModule` là **tên lớp LoginModule**; cơ chế của nó là xác thực Kerberos. Một module khác có thể kiểm tra tài khoản, token, chứng chỉ hoặc tích hợp hệ thống bên ngoài.
- `required` là **control flag** cho toàn bộ tiến trình đăng nhập; `useTicketCache` là option do *chính* `Krb5LoginModule` hiểu. JAAS không suy luận option này thành một dịch vụ JCA.
- `LoginContext` đọc `Configuration`, tạo các `LoginModule` được khai báo, gọi `initialize` và điều phối các bước. Nếu entry được yêu cầu không tồn tại, nó có thể thử entry mặc định `other`; nếu cả hai thiếu, việc tạo `LoginContext` thất bại.

Các control flag có ý nghĩa bảo mật rõ ràng:

| Flag | Nếu module thất bại | Nếu module thành công |
|---|---|---|
| `required` | Tiếp tục chạy các module sau nhưng toàn bộ lần đăng nhập cuối cùng vẫn thất bại | Tiếp tục chạy module sau; thành công của module này là điều kiện bắt buộc |
| `requisite` | Kết thúc xử lý đăng nhập ngay với thất bại | Tiếp tục chạy module sau; cũng là điều kiện bắt buộc |
| `sufficient` | Thường tiếp tục chạy module sau | Có thể kết thúc sớm với thành công nếu chưa có `required`/`requisite` trước đó thất bại |
| `optional` | Thường tiếp tục chạy module sau | Thường tiếp tục chạy module sau; chỉ góp phần vào kết quả chung |

Nếu không có module `required` hay `requisite` thì ít nhất một module `sufficient` hoặc `optional` phải thành công. Đặt sai flag hay thứ tự có thể tạo luồng xác thực yếu hơn dự định. Một `sufficient` thành công **không** xóa lỗi của `required` đã chạy trước đó.

Luồng xử lý điển hình:

```text
Ứng dụng
  -> LoginContext("BackendLogin")
  -> Configuration.getAppConfigurationEntry("BackendLogin")
  -> các LoginModule theo thứ tự và control flag
  -> login() từng module (kiểm chứng dữ liệu đầu vào)
  -> nếu toàn bộ đăng nhập đạt: commit() các module
     nếu thất bại: abort() và thu dọn trạng thái
  -> Subject với Principal/credentials sau commit thành công
  -> logout() khi kết thúc phiên xử lý
```

`CallbackHandler` cho phép module yêu cầu dữ liệu đầu vào qua `NameCallback`, `PasswordCallback`… thay vì phụ thuộc giao diện nhập liệu cụ thể. `Subject` là nơi tập hợp danh tính/credential sau xác thực; một `Principal` có thể là tên người dùng hoặc danh tính khác. **Có `Subject` không đồng nghĩa mọi API sẽ tự kiểm tra quyền:** ứng dụng/hệ thống còn phải thực thi quy tắc authorization phù hợp.

Quan trọng về ranh giới: dù `LoginModule` là một SPI trong package `javax.security.auth.spi`, nó **không phải** một `java.security.Provider`. Việc thêm `LoginModule` vào file JAAS không đưa module đó vào `Security.getProviders()`.

## 3. JCA chọn `Provider` như thế nào?

JCA tách API mà ứng dụng dùng khỏi hiện thực của các dịch vụ bảo mật. Với ví dụ bên dưới, ứng dụng yêu cầu **loại dịch vụ `MessageDigest` + thuật toán `SHA-256`**, không yêu cầu đăng nhập một người dùng:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
System.out.println(digest.getAlgorithm());
System.out.println(digest.getProvider().getName());
```

Đây là **đoạn mã đặt trong một method**; cần import `java.security.MessageDigest`. Tên provider ở dòng thứ hai phụ thuộc JDK và cấu hình runtime, vì vậy không nên giả định luôn là một tên cố định.

Cơ chế lựa chọn:

1. `Security.getProviders()` trả về các `Provider` đã đăng ký và thứ tự ưu tiên của chúng.
2. Mỗi provider khai báo các `Provider.Service`, ví dụ dịch vụ `MessageDigest` hỗ trợ `SHA-256` hay dịch vụ `Signature` hỗ trợ `SHA256withRSA`.
3. `getInstance("thuật-toán")` không chỉ định provider sẽ tìm một hiện thực phù hợp theo cơ chế ưu tiên của runtime; JDK có thể áp dụng ưu tiên riêng theo thuật toán qua `jdk.security.provider.preferred`.
4. `getInstance("thuật-toán", "ProviderName")` yêu cầu provider cụ thể; provider hoặc dịch vụ không tồn tại sẽ dẫn tới exception tương ứng.
5. Engine API gọi xuống SPI của hiện thực đã chọn, ví dụ `MessageDigestSpi`. Provider có thể triển khai bằng Java, thư viện native hay phần cứng bảo mật.

Có thể cấu hình provider từ file security của JDK bằng `security.provider.N` hoặc quản lý tại runtime bằng `Security.addProvider(...)` / `Security.insertProviderAt(...)`. Đây là thay đổi **danh sách dịch vụ JCA trong JVM**, không phải chỉnh chuỗi `LoginModule` của một entry JAAS. Đừng thay đổi thứ tự provider toàn cục một cách tùy tiện: mọi thành phần dùng JCA trong JVM đều có thể bị ảnh hưởng.

JCA/security provider không chỉ có primitive mật mã. Cơ chế provider còn hỗ trợ một số service bảo mật khác, trong đó có `Configuration` của JAAS (xem phần 4). Đây là nguồn gốc của sự nhầm lẫn tên gọi.

## 4. Điểm giao tinh tế: provider của `Configuration` không phải provider của `LoginModule`

Từ “provider” có ít nhất ba ngữ cảnh cần tách bạch:

| Cách gọi | Thành phần thực sự | Được chọn bằng gì? |
|---|---|---|
| Authentication provider trong tài liệu JAAS | Một lớp `LoginModule` thực hiện công nghệ xác thực | Entry `Configuration`, tên lớp, thứ tự và flag |
| Login configuration provider | Một hiện thực `javax.security.auth.login.Configuration` cung cấp danh sách `LoginModule` | `Configuration.getConfiguration()`/`setConfiguration(...)` hoặc một factory `getInstance(...)` |
| JCA security provider | `java.security.Provider` đăng ký các dịch vụ/thuật toán bằng SPI | Danh sách security providers và factory `getInstance(...)` của service |

Hai con đường tạo `Configuration` rất dễ bị lẫn:

**Đường 1 — cấu hình JAAS mặc định/được cài đặt cho JVM.** `Configuration.getConfiguration()` lấy đối tượng `Configuration` đã được cài bằng `Configuration.setConfiguration(...)`, hoặc khởi tạo hiện thực mặc định. Security property `login.configuration.provider` có thể chỉ định **tên lớp** của hiện thực `Configuration`. Với hiện thực đọc file, đối tượng này đọc entry trong file JAAS. Việc đổi property này không tương đương `Security.addProvider(...)`.

**Đường 2 — factory dùng chính mô hình provider của JCA.** `Configuration.getInstance("JavaLoginConfig", null)` tra cứu service **`Configuration`/`ConfigurationSpi`** trong danh sách security providers đã đăng ký, trả về một đối tượng `Configuration` do provider hỗ trợ. Đây đúng là một điểm tích hợp với JCA. Nếu service/type được yêu cầu không có, factory có thể ném `NoSuchAlgorithmException`. Không nên mặc định mọi vendor/JDK sẽ chọn cùng provider.

```java
import javax.security.auth.login.Configuration;

// Trích đoạn đặt trong method; provider hỗ trợ JavaLoginConfig phải có trong JVM.
Configuration config = Configuration.getInstance("JavaLoginConfig", null);
System.out.println(config.getProvider().getName());
```

Sau khi có đối tượng `config`, việc xác thực vẫn phải dựa vào các `AppConfigurationEntry` mà `config` trả về. Chính các entry ấy xác định **lớp `LoginModule`**. `Configuration.getInstance(...)` không biến danh sách `LoginModule` thành danh sách `Provider.Service`.

Lập trình viên còn có thể truyền trực tiếp `Configuration` cho constructor `LoginContext(String, Subject, CallbackHandler, Configuration)` để chủ động chọn cấu hình của lần đăng nhập đó, thay vì chỉ phụ thuộc cấu hình JAAS toàn cục.

Một `LoginModule` có thể dùng các engine JCA bên trong: ví dụ kiểm tra chữ ký số bằng `Signature`, truy cập khóa qua `KeyStore`, hay chạy thao tác mã hóa qua `Cipher`. Lúc ấy **JAAS chọn module**, còn **JCA chọn hiện thực cryptography/security service mà module gọi**:

```text
LoginContext -> Configuration -> LoginModule -> kiểm tra credential -> Subject
                                       |
                                       +-> Signature/KeyStore/Cipher.getInstance(...)
                                                -> JCA Provider -> SPI hiện thực
```

Điểm chung là khả năng thay thế hiện thực; ranh giới là **chọn quy trình xác thực** so với **chọn hiện thực một dịch vụ bảo mật**.

## 5. Phân biệt các tên cấu hình rất giống nhau

| Tên/API | Loại | Quyết định điều gì? |
|---|---|---|
| `-Djava.security.auth.login.config=demo-jaas.conf` | JVM **system property** | Vị trí file entry JAAS cho hiện thực cấu hình file mặc định |
| `login.config.url.1`, `login.config.url.2`… | **Security properties** trong `conf/security/java.security` | Các URL cấu hình JAAS cho hiện thực đọc file |
| `login.configuration.provider` | **Security property** | Tên lớp hiện thực `Configuration` được dùng cho cấu hình JAAS mặc định |
| `Configuration.setConfiguration(config)` | Java API | Thay đối tượng `Configuration` JAAS toàn cục đã cài đặt |
| `Configuration.getInstance(type, params)` | Java API sử dụng provider | Tìm hiện thực `ConfigurationSpi` của type qua JCA provider registry |
| `security.provider.1`, `security.provider.2`… | **Security properties** | Đăng ký/thứ tự ưu tiên provider JCA |
| `Security.addProvider(provider)` / `insertProviderAt(...)` | Java API | Thêm provider JCA tại runtime |

Các system property bắt đầu bằng `-D` không đồng nhất với security properties lấy qua `Security.getProperty(...)`. File `java.security` là file cấu hình security của JDK; file `demo-jaas.conf` chứa **entry LoginModule**. Hai file phục vụ mục đích khác nhau.

Khi hỏi “tôi đã cài provider rồi sao JAAS không đổi?”, cần kiểm tra bạn vừa cài **`java.security.Provider`**, đổi **`Configuration`**, hay sửa **entry `LoginModule`**. Ba thao tác không hoán đổi cho nhau.

## 6. Ví dụ Java 17+: một lần JAAS login và một lần chọn provider JCA độc lập

Ví dụ này chạy với JDK có JAAS/JCA tiêu chuẩn, không cần Kerberos. Để tập trung vào **cơ chế chọn module**, `DemoLoginModule` cố ý chấp nhận mọi lần đăng nhập và gắn principal giả lập. **Nó không xác thực credential thật, tuyệt đối không dùng để bảo vệ ứng dụng.**

Tạo ba file cùng thư mục.

**File `demo-jaas.conf`** — JAAS chọn lớp và control flag:

```text
Demo {
    DemoLoginModule required;
};
```

**File `DemoLoginModule.java`** — triển khai JAAS SPI:

```java
import java.security.Principal;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.spi.LoginModule;

public class DemoLoginModule implements LoginModule {
    private Subject subject;
    private Principal principal;
    private boolean passed;

    @Override
    public void initialize(Subject subject, CallbackHandler handler,
                           Map<String, ?> sharedState, Map<String, ?> options) {
        this.subject = subject;
    }

    @Override
    public boolean login() {
        passed = true; // Chỉ minh họa cơ chế; không xác thực người dùng thật.
        return true;
    }

    @Override
    public boolean commit() {
        if (!passed) return false;
        principal = () -> "demo-user";
        subject.getPrincipals().add(principal);
        return true;
    }

    @Override
    public boolean abort() {
        return logout();
    }

    @Override
    public boolean logout() {
        if (principal != null) subject.getPrincipals().remove(principal);
        principal = null;
        passed = false;
        return true;
    }
}
```

**File `BoundaryDemo.java`** — ứng dụng gọi hai hệ thống:

```java
import java.security.MessageDigest;
import javax.security.auth.login.LoginContext;

public class BoundaryDemo {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("Demo");
        context.login();
        System.out.println("JAAS principal: " +
                context.getSubject().getPrincipals().iterator().next().getName());

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("JCA algorithm: " + digest.getAlgorithm());
        System.out.println("JCA provider assigned: " + (digest.getProvider() != null));

        context.logout();
        System.out.println("JAAS principals after logout: " +
                context.getSubject().getPrincipals().size());
    }
}
```

Biên dịch và chạy trong thư mục chứa ba file:

```bash
javac BoundaryDemo.java DemoLoginModule.java
java -Djava.security.auth.login.config=demo-jaas.conf BoundaryDemo
```

**Kết quả chuẩn** (đã kiểm chứng bằng biên dịch/chạy trên OpenJDK; phần provider chỉ in boolean nên không phụ thuộc tên vendor):

```text
JAAS principal: demo-user
JCA algorithm: SHA-256
JCA provider assigned: true
JAAS principals after logout: 0
```

Hãy lần theo đúng **hai đường chọn hiện thực**:

1. `LoginContext("Demo")` tìm entry `Demo` trong file cấu hình JAAS. Entry chỉ định `DemoLoginModule` với flag `required`. `login()` rồi `commit()` thêm principal vào `Subject`; `logout()` gỡ principal.
2. `MessageDigest.getInstance("SHA-256")` tra registry JCA để tìm provider của thuật toán SHA-256; không nhìn tên `Demo`, tên `DemoLoginModule` hay control flag `required`.
3. Thay `DemoLoginModule` trong `demo-jaas.conf` sẽ thay luồng JAAS. Thay provider cung cấp `SHA-256` sẽ ảnh hưởng lần tạo `MessageDigest`. Mỗi thao tác độc lập trừ khi module xác thực tự gọi JCA ở bên trong.

Ví dụ chỉ kiểm chứng wiring/luồng gọi. Trong hệ thống thật, `login()` phải kiểm tra bằng chứng xác thực qua dịch vụ đáng tin, xử lý bí mật phù hợp, sau đó mới `commit()` dữ liệu danh tính; không được xem một `Principal` do ứng dụng tự thêm là bằng chứng đã xác thực.

## 7. Định vị lỗi theo lớp thay vì sửa nhầm cấu hình

| Triệu chứng | Nên kiểm tra trước | Không nên kết luận vội |
|---|---|---|
| `LoginException` báo thiếu `LoginModule` cho entry | Tên trong `LoginContext("...")`, file JAAS được load, entry `other`, tên lớp/cú pháp | “Chưa cài cryptographic provider” |
| `LoginException` / `FailedLoginException` trong module | Credential, callback, tùy chọn, thứ tự và flag của module | “Sai thuật toán SHA-256” |
| `ClassNotFoundException` hoặc lỗi tạo `LoginModule` | Classpath/module path, tên lớp, visibility/constructor, dependency | “Phải gọi `Security.addProvider`” |
| `NoSuchAlgorithmException` từ `MessageDigest.getInstance`/`Signature.getInstance` | Tên thuật toán/dịch vụ và provider nào hỗ trợ nó | “Thiếu entry `LoginModule`” |
| `NoSuchProviderException` khi chỉ rõ provider JCA | Tên/đăng ký provider JCA thực sự hiện diện | “JAAS control flag sai” |
| `NoSuchAlgorithmException` từ `Configuration.getInstance` | Provider nào hỗ trợ service `Configuration` và type như `JavaLoginConfig` | “Mọi `LoginModule` đều chạy qua JCA” |
| Login thành công nhưng vẫn truy cập tài nguyên sai | Authorization của ứng dụng, mapping principal → quyền, phiên làm việc | “`Subject` tự động bảo vệ tất cả API” |

Hướng kiểm tra ngắn gọn: tìm **API ném lỗi đầu tiên**. Lỗi ở `LoginContext`/`LoginModule` thường thuộc đường JAAS; lỗi từ engine `getInstance` thuộc việc chọn JCA service; lỗi authorization là lớp quyết định quyền độc lập. Nếu `LoginModule` gọi JCA bên trong, stack trace có thể đi qua **cả hai**; xác định chính xác bước thất bại.

## 8. Khi hai hệ thống cùng xuất hiện trong ứng dụng thực tế

**Trường hợp A — thay phương thức đăng nhập:** chuyển từ module kiểm tra tài khoản sang Kerberos/LDAP bằng cách đổi cấu hình `LoginModule` và chuẩn bị hạ tầng tương ứng. Thêm provider SHA-256 không thực hiện chuyển đổi phương thức đăng nhập.

**Trường hợp B — khóa nằm trong HSM/PKCS#11:** đăng ký provider JCA/PKCS#11 để `KeyStore`/`Signature` dùng phần cứng. Một `LoginModule` có thể dùng nó khi xác thực dựa trên chữ ký/chứng chỉ, nhưng quy tắc “ai được đăng nhập” và cách ánh xạ sang `Principal` vẫn do luồng xác thực quản lý.

**Trường hợp C — ứng dụng đã xác thực nhưng cần ký tài liệu:** JAAS xác lập `Subject` của người dùng; API nghiệp vụ kiểm tra quyền được ký, rồi `Signature` lấy hiện thực từ JCA provider. “Xác thực thành công”, “có quyền ký” và “thuật toán ký hợp lệ” là ba kiểm tra riêng biệt.

**Trường hợp D — đổi provider JCA toàn JVM:** thay đổi có thể ảnh hưởng TLS, chữ ký, keystore và các engine khác cùng dùng provider. Hãy nêu lý do cụ thể khi pin tên provider; để JCA tự chọn khi không có yêu cầu tương thích, thiết bị hay tuân thủ đặc biệt.

## 9. Nguyên tắc an toàn và ghi nhớ

- **Không nhầm xác thực với phân quyền.** `Subject`/`Principal` mô tả danh tính sau JAAS; ứng dụng phải kiểm tra quyền trên tài nguyên, và một đối tượng `Subject` không tự khiến mọi API được bảo vệ.
- **Không coi sự hiện diện của provider là bằng chứng xác thực.** `Security.getProviders()` chỉ cho biết dịch vụ JCA sẵn có; `MessageDigest` tạo được không nói gì về danh tính người dùng.
- **Không đưa bí mật vào ví dụ demo hoặc log.** `CallbackHandler` nên chuyển dữ liệu nhập tới `LoginModule`; module phải kiểm chứng với hệ thống tin cậy và dọn credential khi không cần. Không dùng `SHA-256` đơn thuần để lưu mật khẩu; hệ thống mật khẩu cần phương pháp KDF phù hợp, salt và cấu hình công sức tính toán.
- **Đọc thứ tự và control flag JAAS như một chính sách bảo mật.** `required`, `requisite`, `sufficient`, `optional` thay đổi điều kiện thành công; review bằng ca thành công và thất bại cho từng module.
- **Phân biệt nơi cấu hình.** File JAAS chứa entry `LoginModule`; security properties cấu hình `Configuration` hoặc provider registry; mã ứng dụng gọi API quyết định bước nào được sử dụng.

Tự kiểm tra hiểu bài:

1. Gọi `Security.addProvider(new MyProvider())` có tự bổ sung `MyLoginModule` vào `LoginContext("App")` không? **Không**; phải cấu hình entry JAAS hoặc cung cấp `Configuration` tương ứng.
2. Đổi `required` thành `sufficient` có ảnh hưởng `MessageDigest.getInstance("SHA-256")` không? **Không trực tiếp**; nó đổi chính sách kết hợp các module xác thực.
3. Vì sao `Configuration.getInstance("JavaLoginConfig", null)` là ngoại lệ đáng nhớ? Vì **đối tượng cấu hình JAAS** trong API này được chọn qua cơ chế **JCA provider/`ConfigurationSpi`**; nội dung cấu hình ấy vẫn quyết định `LoginModule`.
4. Nếu `LoginModule` dùng `Signature.getInstance(...)` và thiếu thuật toán, bạn sửa đâu? Kiểm tra **JCA service/algorithm/provider** mà module yêu cầu, đồng thời giữ nguyên việc JAAS quyết định module nào được gọi.

## Tài liệu chính thức

- Oracle, *JAAS Reference Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-authentication-authorization-service-jaas-reference-guide.html
- Oracle, *JAAS LoginModule Developer's Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html
- Java SE 21 API, `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/Configuration.html
- Java SE 21 API, `LoginContext`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/LoginContext.html
- Oracle, *JCA Reference Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html

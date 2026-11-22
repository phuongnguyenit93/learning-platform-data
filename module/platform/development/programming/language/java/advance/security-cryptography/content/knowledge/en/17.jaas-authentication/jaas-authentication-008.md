# 17.8 Quản lý credential, `Subject` chỉ đọc và xử lý `LoginException`

## 1. Mục tiêu học tập

Trong **JAAS (Java Authentication and Authorization Service)**, đăng nhập thành công không chỉ là trả về `true`. Hệ thống còn phải quản lý **danh tính (`Principal`)**, **credential**, đối tượng **`Subject`**, vòng đời đăng nhập–đăng xuất và các trường hợp xác thực thất bại. Những thao tác tưởng đơn giản như đưa password vào `String`, đánh dấu `Subject` chỉ đọc quá sớm hoặc nuốt `LoginException` đều có thể khiến bí mật tồn tại lâu hơn cần thiết hoặc khiến ứng dụng chấp nhận trạng thái xác thực sai.

Sau bài học, bạn có thể:

1. Phân biệt `Principal`, **public credential**, **private credential** và secret chỉ dùng tạm trong lúc đăng nhập.
2. Hiểu vai trò của `LoginContext`, `LoginModule`, `CallbackHandler`, `PasswordCallback` và `Configuration`.
3. Quản lý credential từ lúc thu nhận, xác thực, đưa vào `Subject`, sử dụng, đăng xuất đến **hủy bí mật** bằng `Destroyable`.
4. Giải thích chính xác điều `Subject.setReadOnly()` làm và **không làm**, đặc biệt là khác biệt giữa **khóa cấu trúc các tập** và **xóa/hủy dữ liệu bên trong đối tượng credential**.
5. Xử lý `LoginException`/`FailedLoginException` theo nguyên tắc **fail closed**, rollback/cleanup đúng pha, logging tối thiểu và không làm rò rỉ password.
6. Chạy một ví dụ **Java 17+** minh họa đăng nhập, snapshot chỉ đọc, cleanup bình thường, logout với `Subject` đã khóa và đăng nhập thất bại.

**Phạm vi:** JAAS cấp ứng dụng / Java SE, không phải hướng dẫn viết một nhà cung cấp xác thực production. Chương trình mẫu dùng mật khẩu giả lập cứng chỉ để kiểm thử lifecycle và **không** thay thế Kerberos, LDAP, IAM, KMS, password hashing hay credential store thực.

## 2. JAAS có những thành phần nào?

```text
      Giao diện/ứng dụng                  Cơ chế xác thực (có thể cắm thêm)
      ------------------                 ---------------------------------
      Tạo LoginContext
           |
           | name + CallbackHandler + Configuration (+ Subject tùy chọn)
           v
      LoginContext.login()
           |
           +-------> LoginModule A.login()   <--- CallbackHandler
           |                 |                        NameCallback
           +-------> LoginModule B.login()            PasswordCallback
           |                 |
           |          Kết quả và control flags
           v
      Nếu overall success:
           LoginModule.commit()   --> Subject:
                                     - Principals
                                     - Public credentials
                                     - Private credentials

      Nếu overall failure:
           LoginModule.abort()    --> dọn trạng thái tạm/đã thêm

      Khi kết thúc phiên:
           LoginContext.logout()  --> LoginModule.logout()
                                       xóa credential/principal do module thêm
                                       và hủy secrets theo khả năng
```

| Kiểu/API | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `javax.security.auth.Subject` | Vật chứa danh tính và các credential liên quan tới một thực thể | Không tự xác thực ai cả; **phải được cập nhật từ quy trình đáng tin** |
| `java.security.Principal` | Một danh tính/tên/role được biểu diễn bằng object | Không phải password hoặc token |
| `Subject.getPublicCredentials()` | Tập credentials có thể chia sẻ theo chính sách, tùy từng loại | “Public” không nghĩa bất kỳ ai cũng có quyền ghi |
| `Subject.getPrivateCredentials()` | Tập credential riêng tư, có thể chứa ticket/key/token | **Không bảo đảm tự mã hóa, tự xóa hay ngăn log** |
| `javax.security.auth.login.LoginContext` | Điểm vào của client tới chu trình đăng nhập/đăng xuất | Dựa vào cấu hình các `LoginModule` |
| `javax.security.auth.spi.LoginModule` | Plugin thực hiện `initialize/login/commit/abort/logout` | Trách nhiệm auth thực tế, thêm/xóa state do mình sở hữu |
| `CallbackHandler` | Kết nối module với nguồn username/password/OTP v.v. | Không để module phụ thuộc cách nhập dữ liệu |
| `NameCallback` | Xin/nhận username | Username chưa chứng minh danh tính |
| `PasswordCallback` | Nhận password bằng **`char[]`** | `clearPassword()` xóa bản lưu bên trong callback |
| `Configuration` / `AppConfigurationEntry` | Chọn module và JAAS control flag | Các flags quyết định overall success/failure |
| `LoginException` | Checked exception của JAAS login/logout | Không được chuyển lỗi thành đăng nhập thành công |
| `Destroyable` | Contract `destroy()` / `isDestroyed()` | Xóa tài nguyên bí mật ở mức credential implementation |

**Phân biệt authentication với authorization:** `LoginContext.login()` chỉ xác lập danh tính và credential theo module. Việc một `Subject` chứa `Principal("alice")` không tự cấp phép Alice được truy cập tài khoản, tài nguyên hoặc nghiệp vụ cụ thể. Authorization phải kiểm tra thêm quyền/role, resource, tenant, scope, policy và trạng thái phiên. Cũng không nên cho phép người dùng tự gọi `subject.getPrincipals().add(new Principal(...))` trên một `Subject` đang được coi là nguồn danh tính đáng tin.

## 3. `Principal`, public credential và private credential khác nhau thế nào?

Ví dụ một người dùng đăng nhập bằng Kerberos, một `Subject` có thể mang identity principal và các ticket/keys thích hợp. Với một module tùy chỉnh khác, thông tin có thể là:

```text
Subject (đối tượng gắn với login)
|
+-- Set<Principal>
|     +-- UserPrincipal("alice")              // danh tính
|
+-- Set<Object> publicCredentials
|     +-- chứng thư public / dữ liệu được phép công bố, nếu cần
|
+-- Set<Object> privateCredentials
      +-- phiên/ticket/token/secret object, nếu module cần
```

**Các tập `Subject` là những tập `Set`, không phải kho bí mật chuyên dụng.** Private credentials vẫn là các Java objects bình thường, chịu quy tắc `Subject`/SecurityManager theo runtime, nhưng **không phải encrypted vault**, không được xóa tự động bởi garbage collector đúng một thời điểm định trước, và không bảo đảm có cơ chế thu hồi trên server. Nếu một credential là token truy cập trong production, nó cần **scope, expiry, rotation, revoke** và chính sách riêng.

### 3.1 Phân loại theo độ nhạy cảm

| Dữ liệu | Thường đặt ở đâu? | Nguyên tắc |
| --- | --- | --- |
| Tên người dùng hoặc service identity | `Principal` sau khi xác thực | Không coi tên tự khai là authenticated identity |
| Certificate công khai đã được kiểm tra | `publicCredentials` nếu use case cần | Kiểm tra issuer/trust/usage trước khi tin |
| Kerberos ticket, private key handle, access token | `privateCredentials` **khi cần** và có policy | Giữ ngắn nhất, giới hạn quyền truy cập, tránh in/log |
| Password nhập vào login | `PasswordCallback` tạm thời / bộ nhớ xử lý auth | **Không** giữ như “credential phiên” sau login |
| Password raw dạng `String` | **Tránh** | `String` bất biến, không thể chủ động xóa nội dung trong heap |
| Mật khẩu/hệ số chứng minh được lưu bởi auth server | Dịch vụ identity chuyên biệt | Không lấy từ JAAS `Subject` để làm kho password |

Không nhất thiết module phải có cả ba loại tập: `Subject` chỉ chứa `Principal` là bình thường nếu không cần credential sau login. Ngược lại, giữ tất cả raw passwords dưới `privateCredentials` vì “đã là private” là cách thiết kế nguy hiểm.

### 3.2 Hai phương thức lấy private credentials không giống nhau

```java
// Mảnh code minh họa khi đã có một Subject đáng tin:
java.util.Set<Object> liveSet = subject.getPrivateCredentials();
java.util.Set<MyCredential> filtered =
        subject.getPrivateCredentials(MyCredential.class);
```

- `getPrivateCredentials()` trả **tập backed bởi `Subject`**. Nếu `Subject` còn sửa được và có quyền, thao tác add/remove vào tập này làm thay đổi subject.
- `getPrivateCredentials(Class<T>)` trả **một tập mới đã lọc theo kiểu**, không phải tập backed bởi subject; sửa tập lọc **không** thêm/xóa credential trong subject.
- Khi có SecurityManager, việc duyệt private credentials có thể chịu `PrivateCredentialPermission`/security checks; đừng dựa vào code mẫu chạy không có SecurityManager rồi suy ra mọi runtime đều có quyền.
- **Đừng** log `getPrivateCredentials().toString()`, iterate rồi in secret, hoặc serialize `Subject` tự do. Dù một credential hiện có `toString()` redacted, implementation khác có thể không như vậy.

**Quyền quản lý không tự đồng nghĩa quyền truy cập:** đối tượng private credential có thể tự thực hiện hạn chế hoặc là handle tới HSM/KMS. Một số key không xuất ra byte được; cố ép `getEncoded()` rồi log/fallback thường phá mô hình bảo vệ khóa.

## 4. Vòng đời credential: thu nhận, dùng tạm, commit, destroy

Một chu trình đúng cần phân biệt **password do người dùng nhập** và **credential được cấp sau khi xác thực**.

```text
[Thu nhận]           [Xác thực]                 [Đã đăng nhập]        [Logout]
char[] password ---> LoginModule.login() ---> LoginModule.commit() ---> logout()
                         |                           |                     |
                       kiểm tra                add Principal,       remove owned items
                       password                session credential   destroy secret
                         |                           |
                  clear callback & copies      KHÔNG lưu raw password
                         |
                  fail -> LoginException -> abort/cleanup
```

### 4.1 Vì sao dùng `char[]` thay vì `String`?

`PasswordCallback` dùng `char[]` để ứng dụng có thể chủ động xóa dữ liệu nhạy cảm sau khi dùng:

```java
// Mảnh minh họa trong LoginModule.login(), với callback đã cung cấp password.
javax.security.auth.callback.PasswordCallback pwd =
        new javax.security.auth.callback.PasswordCallback("Password", false);
callbackHandler.handle(new javax.security.auth.callback.Callback[]{pwd});
char[] supplied = pwd.getPassword(); // lấy một bản sao để xử lý
pwd.clearPassword();                 // xóa bản trong PasswordCallback
try {
    // Xác minh với dịch vụ identity đáng tin; tuyệt đối không log supplied.
} finally {
    if (supplied != null) java.util.Arrays.fill(supplied, '\0');
}
```

Với `PasswordCallback`, `setPassword()` sao chép mảng được truyền vào; `getPassword()` trả một mảng sao; `clearPassword()` zero hóa credential của callback. Vì thế phải xử lý **mọi bản sao** do ứng dụng tạo, không chỉ gọi `clearPassword()` rồi tin đã xóa toàn bộ dữ liệu trong process.

Chúng ta không kiểm soát chắc chắn mọi bản sao tạm do JVM/JIT/OS tạo trong bộ nhớ, nhưng cách dùng `char[]` với giới hạn thời gian tồn tại và xóa trong `finally` vẫn giảm rủi ro. **Không thể cam kết xóa tuyệt đối mọi byte trên hệ thống chỉ vì `Arrays.fill`.** Với credential production, cần provider/keystore/HSM/password verification service tùy threat model.

### 4.2 `CallbackHandler` có trách nhiệm riêng

Một `LoginModule` không nên tự đọc `System.console()` hoặc lấy password từ global variable. Nó yêu cầu các `Callback` cần thiết và để ứng dụng cấp một `CallbackHandler`:

- `NameCallback`: username.
- `PasswordCallback`: password char[].
- `UnsupportedCallbackException`: khi handler không đáp ứng callback cần thiết, cần biến thành failure có kiểm soát.
- `IOException`: lỗi đọc input/nguồn credential, cũng phải xử lý như authentication infrastructure failure.

**Không** in password ra console trong callback handler, không giữ `char[]` làm field dùng lâu dài. Trường hợp password lấy từ một request body, phải bảo đảm request framework và logging đã bảo vệ bí mật trước khi đến JAAS.

### 4.3 `Destroyable`: hủy **nội dung** credential

API `javax.security.auth.Destroyable` định nghĩa:

```java
// Định nghĩa contract, không phải lớp triển khai:
void destroy() throws javax.security.auth.DestroyFailedException;
boolean isDestroyed();
```

Một credential tự quản lý material có thể triển khai `destroy()` bằng việc zero hóa byte[]/char[] hoặc đóng handle native. `destroy()` cần được thiết kế không tiết lộ bí mật qua error message. Đối tượng đã destroyed không được dùng lại; cần kiểm tra `isDestroyed()` nếu logic ứng dụng phải quyết định trạng thái.

**Ranh giới trách nhiệm:** `Subject.getPrivateCredentials().remove(token)` chỉ **gỡ tham chiếu khỏi tập**, không tự bảo đảm memory chứa secret bị xóa. Ngược lại, `token.destroy()` có thể xóa material bên trong nhưng **không** tự gỡ object khỏi `Subject`. Muốn kết thúc phiên tốt phải xử lý **cả việc remove và destroy** theo khả năng và lifecycle thực tế.

### 4.4 Credential thật phải có lifecycle ngoài Java heap

Việc hủy `byte[]` không tự revoke một OAuth token phía server, không xóa ticket cache của nhà cung cấp, không thu hồi key trong HSM và không hoàn thành network logout. Những bước đó phụ thuộc credential provider. Khi xử lý sự cố phải xem xét:

- Secret có thể bị sao chép hoặc ghi vào heap dump/trace trước khi hủy.
- Token có thể còn hợp lệ phía server sau local destroy.
- Phiên đăng nhập ở một thread có thể đang bị thread khác sử dụng.
- Role/authorization đã cached có thể tồn tại sau khi `logout`.
- Expiry/revocation/rotation quyết định tính hợp lệ thực, không chỉ trường `isDestroyed()` của một Java object.

## 5. `Subject.setReadOnly()`: chính xác nó khóa điều gì?

Một `Subject` có ba `Set` principal/public/private credentials. Gọi:

```java
Subject subject = new Subject();
// Khi đã hoàn tất những thay đổi cấu trúc mà ứng dụng cho phép:
subject.setReadOnly();
boolean locked = subject.isReadOnly();
```

Khi `subject.isReadOnly() == true`:

1. **Không thể add/remove** phần tử trong `getPrincipals()`, `getPublicCredentials()` hoặc `getPrivateCredentials()`; thao tác sửa tập ném `IllegalStateException` (các kiểm tra permission khác có thể có trên runtime dùng SecurityManager).
2. `setReadOnly()` là thay đổi **một chiều**; Java không có `setWritable()` để đảo trạng thái đó.
3. Trạng thái read-only **không tự biến các object bên trong thành immutable**: một `Principal` có trường mutable hoặc một credential tùy chỉnh có thể vẫn bị thay đổi nội bộ nếu API cho phép.
4. Theo contract Java SE, thao tác **`destroy()` trên các credential vẫn được phép**. Đây là khác biệt quan trọng với add/remove trong các tập.
5. `setReadOnly()` **không xác thực** danh tính; nó chỉ ngăn việc sửa cấu trúc chủ thể sau khi được khóa.

```text
Before setReadOnly:
    Subject Principals: [Alice]
    Subject PrivateCredentials: [SessionCredential]
           |
        add/remove allowed (theo quyền và runtime)
           |
       setReadOnly()
           v
After setReadOnly:
    Subject Principals: [Alice]           -- không thể remove khỏi Subject
    Subject PrivateCredentials: [token]   -- không thể remove khỏi Subject
                                                  |
                                                  +-- token.destroy() vẫn có thể
                                                      xóa secret trong token
```

**Sai lầm phổ biến:** “Đã `setReadOnly` thì private credential an toàn tuyệt đối.” Sai: read-only không mã hóa secret, không giữ danh tính đáng tin tự động, không chặn việc gọi method thay đổi **bên trong object**, và không thay thế destroy/rotation/revocation.

### 5.1 Tại sao khóa `Subject` quá sớm dễ làm `LoginModule.logout()` khó xử lý?

Thông thường `LoginModule.commit()` thêm principal/credential do nó sở hữu; `logout()` **gỡ** các phần tử ấy và **hủy** secrets. Nếu application gọi `subject.setReadOnly()` ngay sau đăng nhập, các tập không thể bị sửa nữa. Hướng dẫn JAAS `LoginModule` của Oracle nêu mô hình: với subject read-only, module nên **hủy những credential do nó thêm nếu destroyable**, không thể remove chúng khỏi subject; nếu credentials không thể destroy, logout có thể phải báo `LoginException`.

Có nghĩa:

- Logout của **Subject mutable**: remove những principal/credential do module đã thêm, rồi destroy tài nguyên bí mật tương ứng.
- Logout của **Subject read-only**: không thể remove các entry đã gắn vào subject; module có thể destroy **nội dung credential**; principal/credential object vẫn tồn tại trong set dù credential đã bị hủy.
- `logout()` thành công trên một subject chỉ đọc **không bảo đảm** `subject.getPrincipals().isEmpty()` hoặc `getPrivateCredentials().isEmpty()`.
- Nếu một module tự viết cứ gọi `.remove()` trên subject read-only mà không kiểm tra trạng thái thì có thể bị `IllegalStateException`, cần xử lý failure thay vì âm thầm coi logout thành công.

### 5.2 Thiết kế an toàn hơn: subject sống và bản identity snapshot tách riêng

Nếu cần một representation danh tính **không cho caller tự sửa**, nhưng vẫn muốn JAAS logout có thể remove credentials, có thể:

1. **Giữ `Subject` thuộc `LoginContext` ở trạng thái mutable** trong vòng đời đăng nhập/log out theo ownership module.
2. Sau login thành công, tạo **một `Subject` khác chỉ sao chép principal bất biến đã kiểm chứng**, không sao chép private credentials.
3. Gọi `setReadOnly()` trên **snapshot chỉ chứa identity**, rồi đưa snapshot tới tầng đọc danh tính khi thực sự cần; không cho tầng đó quyền trực tiếp quản trị live Subject.
4. Khi hết phiên, gọi `LoginContext.logout()` trên **live Subject**, để module cleanup và destroy.

Điều này chỉ là một **pattern tùy ứng dụng**: một bản sao `Subject` không tự mang tất cả trạng thái/authorization JAAS, không tự cập nhật khi original thay đổi và không phải bằng chứng danh tính đã được cryptographically sealed. **Không** cho phép sử dụng snapshot để tiếp tục các phiên sau khi authorization thực đã hết hạn. Nên dùng principal objects **immutable**; read-only Subject không deep-freeze các objects bên trong.

Một chiến lược khác là đóng subject gốc khi đã chắc chắn module/provider có lifecycle hỗ trợ read-only logout và credentials đều destroyable; phải kiểm thử module cụ thể. Không lấy code mẫu `setReadOnly()` làm blanket best practice cho mọi JAAS provider.

## 6. Chu trình `LoginModule`: `login`, `commit`, `abort`, `logout`

JAAS có **hai pha** trong `LoginContext.login()`:

```text
Phase 1: LoginModule.login()
    - Đọc callback; xác minh credential
    - Trả true, false (ignore) hoặc ném LoginException
    - Không tự ý add Principal trước overall success

Overall success theo JAAS control flags?
    YES -> Phase 2: LoginModule.commit()
             - Đưa state đã xác thực vào Subject
    NO  -> Phase 2: LoginModule.abort()
             - Hủy trạng thái tạm, rollback nếu cần

Sau khi ứng dụng sử dụng phiên:
    LoginContext.logout() -> LoginModule.logout()
             - Dọn đúng Principal/credential module sở hữu
```

Các `LoginModule` trong cùng login context có thể chia sẻ **cùng object Subject** và `sharedState`; vì thế module A **không được** gọi `subject.getPrincipals().clear()` hay `getPrivateCredentials().clear()` để dọn phần của mình, vì có thể xóa cả dữ liệu module B hoặc dữ liệu đã có từ trước.

| Method | Khi dùng | Điều nên làm | Điều cần tránh |
| --- | --- | --- | --- |
| `initialize(...)` | JAAS dựng module | Nhận `Subject`, handler, shared state, options | Lưu bí mật lâu không cần thiết |
| `login()` | Pha xác thực | Lấy password qua callback, kiểm tra, ghi trạng thái **private của module**; `return true` khi thành công | Đưa raw password vào Subject/log; tự retry hàng loạt |
| `commit()` | Overall login thành công | Thêm **đúng principal/credential module sở hữu** vào Subject | Thêm khi module chưa thành công; nuốt lỗi commit |
| `abort()` | Overall login thất bại | Hủy state tạm, rollback các thay đổi sở hữu theo khả năng | Để lại session token hoặc principal từ login đã bị hủy |
| `logout()` | Application kết thúc phiên | Remove owned state (nếu mutable), destroy secret và gọi revoke của provider nếu cần | Xóa dữ liệu của module khác; giả định read-only subject có thể remove |

### 6.1 JAAS control flags ảnh hưởng overall success

Các `AppConfigurationEntry.LoginModuleControlFlag` thông dụng:

| Flag | Ý nghĩa chung |
| --- | --- |
| `REQUIRED` | Module **phải thành công** để overall success, nhưng các module tiếp theo vẫn thường được gọi |
| `REQUISITE` | Module **phải thành công**; thất bại có thể chấm dứt sớm quá trình auth |
| `SUFFICIENT` | Thành công có thể cho phép kết thúc sớm nếu không có `REQUIRED`/`REQUISITE` thất bại trước đó |
| `OPTIONAL` | Kết quả phụ thuộc tổ hợp các module và overall rules |

Không tự viết một `LoginContext` vòng lặp gọi `login()` rồi `commit()` bất kể các module khác thất bại. Dùng contract do JAAS quản lý, vì module có thể sinh tạm token trước khi được phép ghi vào subject.

## 7. `LoginException` và cách phân loại failure

`javax.security.auth.login.LoginException` là **checked exception** cho lỗi đăng nhập/đăng xuất trong JAAS. Các subclass như `FailedLoginException`, `AccountExpiredException`, `CredentialExpiredException` giúp phân loại lỗi khi provider thật hỗ trợ. Không phải lúc nào exception nhận ở application cũng là đúng subclass gốc: nhiều module và provider có thể bọc lỗi hoặc dùng `LoginException` chung.

### 7.1 Login failure không có nghĩa tiếp tục như guest đã xác thực

```java
// Mảnh code trong ứng dụng có LoginContext loginContext:
try {
    loginContext.login();
    javax.security.auth.Subject authenticated =
            loginContext.getSubject();
    // Chỉ sau thành công mới cấp quyền theo policy phù hợp.
} catch (javax.security.auth.login.LoginException ex) {
    // Ghi audit event không có password/token/secret.
    // Từ chối truy cập, hủy context tạm/cleanup theo API provider.
    throw new SecurityException("Authentication unsuccessful");
}
```

`login()` ném `LoginException` thì ứng dụng **không được** suy ra authentication thành công từ một `Subject` đang có tên hoặc từ việc callback trả password. `LoginContext.getSubject()` có thể trả `null` nếu overall login chưa thành công; khi truyền một `Subject` từ ngoài vào, vẫn cần kiểm tra success trước khi coi principal trong đó là authenticated.

### 7.2 Không để mất nguyên nhân kỹ thuật, nhưng cũng không tiết lộ bí mật

Trong module, khi `CallbackHandler.handle(...)` ném `IOException` hoặc `UnsupportedCallbackException`, có thể bọc vào `LoginException` và giữ cause:

```java
// Mảnh code trong catch (IOException | UnsupportedCallbackException cause):
javax.security.auth.login.LoginException ex =
        new javax.security.auth.login.LoginException("Callback failed");
ex.initCause(cause);
throw ex;
```

**Ứng dụng phía ngoài** có thể log mã lỗi và correlation ID, nhưng không nên in cause chứa raw password, token, callback content, full authentication headers hay các input secrets. Trả về client một thông điệp chung “Authentication unsuccessful”, không phân biệt quá chi tiết “user tồn tại nhưng sai password” nếu điều đó giúp dò tài khoản.

Phân loại đúng:

- `FailedLoginException`: thông tin chứng thực không khớp.
- `CredentialExpiredException` / `AccountExpiredException`: credential/tài khoản hết hạn theo chính sách provider.
- Lỗi callback, cấu hình, không kết nối identity backend: **infrastructure/authentication failure**.
- `LoginException` trong `commit`/`abort`/`logout`: lỗi lifecycle; cần cleanup hoặc phản hồi security event, không được nói rằng secret đã bị hủy khi chưa xác minh.

### 7.3 Ai chịu trách nhiệm retry?

Tài liệu JAAS `LoginModule` của Oracle hướng dẫn **module không tự retry hoặc sleep/delay trong `login()` khi xác thực thất bại**; chính application/gateway chịu trách nhiệm policy retry, rate limits, backoff, lockout và telemetry. Việc tự loop gọi callback nhiều lần trong module có thể làm sai state của một lần login, kéo dài password trong memory và tạo lỗ hổng brute force.

### 7.4 Khi `commit()` thất bại một phần

Nếu module đã thêm principal nhưng chưa thêm credential thì bị exception, phải rollback **phần do chính module vừa thêm**, hủy secret đã tạo và ném `LoginException`. Không tự `return true` rồi để subject mang identity mà credential chưa sẵn sàng.

Ngược lại, nếu `abort()`/`logout()` cần cleanup nhưng credential provider đã mất kết nối, module phải xử lý theo documented contract và báo lỗi phù hợp. Đối với một token còn hợp lệ ở server, local `Destroyable.destroy()` không thay thế remote revocation; cần đánh dấu phiên không còn được chấp nhận ở tầng application và theo dõi reconciliation.

## 8. Chương trình Java 17+ hoàn chỉnh: `Subject`, credential và `LoginException`

Chương trình sau độc lập, không cần cấu hình JAAS ngoài. Nó cung cấp một `Configuration` **in-memory** chọn `ExampleModule` với control flag `REQUIRED`, dùng `OneUseHandler` để đưa password vào `PasswordCallback`, và sinh một `SessionCredential` ngẫu nhiên sau khi xác thực mẫu.

Chương trình kiểm chứng các tình huống:

1. Đăng nhập với demo user `alice`/password tạm `demo`, ghi một principal và một **demo session secret** vào `Subject`.
2. Tạo **snapshot chỉ gồm principal** rồi `setReadOnly()`, thử sửa snapshot và quan sát `IllegalStateException`; snapshot **không** chứa private credentials.
3. `logout()` trên **live Subject mutable** gỡ principal/credential và zero hóa token.
4. Trường hợp khác: đánh dấu **live Subject read-only** trước `logout`; module chỉ có thể destroy credential, không gỡ được principal/credential khỏi các tập.
5. Đăng nhập sai `bad` bị từ chối bằng `LoginException`; không commit principal/credential.
6. Không in password, token bytes hoặc nội dung private credential.

> **Lưu ý an ninh:** Module dùng password `demo` cứng trong mã và `Arrays.equals` **chỉ để minh họa API/chu trình**. **Không dùng** cách này trong production: không hardcode password, không so sánh password plaintext như cơ chế auth thật, không dùng random bytes demo như session token có quyền truy cập. Ứng dụng thật cần provider xác thực đã kiểm chứng, salted password hashing/identity service, MFA nếu cần, secret rotation, KMS/HSM/keystore, rate limit và chính sách phiên.

Tạo file **`JaasCredentialLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.security.Principal;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Destroyable;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasCredentialLifecycleDemo {
    public record UserId(String value) implements Principal {
        @Override public String getName() { return value; }
    }

    public static final class SessionCredential implements Destroyable {
        private final byte[] material = new byte[16];
        private boolean destroyed;

        public SessionCredential() {
            new SecureRandom().nextBytes(material);
        }

        @Override public synchronized void destroy() {
            Arrays.fill(material, (byte) 0);
            destroyed = true;
        }

        @Override public synchronized boolean isDestroyed() {
            return destroyed;
        }

        @Override public String toString() {
            return "SessionCredential[redacted]";
        }
    }

    public static final class OneUseHandler implements CallbackHandler {
        private final String user;
        private final char[] password;

        public OneUseHandler(String user, char[] password) {
            this.user = user;
            this.password = password; // takes ownership of caller array
        }

        @Override public void handle(Callback[] callbacks)
                throws IOException, UnsupportedCallbackException {
            try {
                for (Callback callback : callbacks) {
                    if (callback instanceof NameCallback name) {
                        name.setName(user);
                    } else if (callback instanceof PasswordCallback pwd) {
                        pwd.setPassword(password); // PasswordCallback copies it
                    } else {
                        throw new UnsupportedCallbackException(callback);
                    }
                }
            } finally {
                Arrays.fill(password, '\0');
            }
        }
    }

    public static final class ExampleModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private boolean authenticated;
        private boolean committed;
        private UserId principal;
        private SessionCredential credential;

        @Override public void initialize(Subject subject,
                CallbackHandler handler, Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override public boolean login() throws LoginException {
            NameCallback name = new NameCallback("User");
            PasswordCallback pwd = new PasswordCallback("Password", false);
            try {
                handler.handle(new Callback[] {name, pwd});
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException("Callback failed");
                failure.initCause(e);
                throw failure;
            }
            char[] actual = pwd.getPassword();
            pwd.clearPassword();
            char[] expected = {'d','e','m','o'}; // demonstration ONLY
            try {
                if (!"alice".equals(name.getName())
                        || actual == null
                        || !Arrays.equals(actual, expected)) {
                    throw new FailedLoginException("Invalid credentials");
                }
                principal = new UserId(name.getName());
                credential = new SessionCredential();
                authenticated = true;
                return true;
            } finally {
                if (actual != null) Arrays.fill(actual, '\0');
                Arrays.fill(expected, '\0');
            }
        }

        @Override public boolean commit() throws LoginException {
            if (!authenticated) return false;
            try {
                subject.getPrincipals().add(principal);
                subject.getPrivateCredentials().add(credential);
                committed = true;
                return true;
            } catch (RuntimeException e) {
                try {
                    if (!subject.isReadOnly()) {
                        subject.getPrincipals().remove(principal);
                        subject.getPrivateCredentials().remove(credential);
                    }
                } finally {
                    credential.destroy();
                }
                LoginException failure = new LoginException("Commit failed");
                failure.initCause(e);
                throw failure;
            }
        }

        private void cleanup() {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(principal);
                subject.getPrivateCredentials().remove(credential);
            }
            if (credential != null) credential.destroy();
            credential = null;
            principal = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() {
            if (!authenticated && !committed) return false;
            cleanup();
            return true;
        }

        @Override public boolean logout() {
            cleanup();
            return true;
        }
    }

    private static Configuration configuration() {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"Example".equals(name)) return null;
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                            ExampleModule.class.getName(),
                            AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                            Map.of())
                };
            }
        };
    }

    private static LoginContext context(Subject subject, char[] password)
            throws LoginException {
        return new LoginContext("Example", subject,
                new OneUseHandler("alice", password), configuration());
    }

    public static void main(String[] args) throws Exception {
        Subject live = new Subject();
        LoginContext ok = context(live, new char[] {'d','e','m','o'});
        ok.login();
        SessionCredential token = live.getPrivateCredentials(
                SessionCredential.class).iterator().next();
        System.out.println("Login principal count: " +
                live.getPrincipals().size());
        System.out.println("Private credential count: " +
                live.getPrivateCredentials().size());

        Subject snapshot = new Subject(false,
                new HashSet<>(live.getPrincipals()), Set.of(), Set.of());
        snapshot.setReadOnly();
        boolean modificationBlocked = false;
        try {
            snapshot.getPrincipals().add(new UserId("mallory"));
        } catch (IllegalStateException expected) {
            modificationBlocked = true;
        }
        System.out.println("Identity snapshot read-only: " +
                snapshot.isReadOnly());
        System.out.println("Snapshot mutation rejected: " +
                modificationBlocked);
        System.out.println("Snapshot has private credentials: " +
                !snapshot.getPrivateCredentials().isEmpty());

        ok.logout();
        System.out.println("Mutable Subject cleared at logout: " +
                (live.getPrincipals().isEmpty()
                        && live.getPrivateCredentials().isEmpty()));
        System.out.println("Session credential destroyed: " +
                token.isDestroyed());

        Subject frozen = new Subject();
        LoginContext frozenContext = context(
                frozen, new char[] {'d','e','m','o'});
        frozenContext.login();
        SessionCredential frozenToken = frozen.getPrivateCredentials(
                SessionCredential.class).iterator().next();
        frozen.setReadOnly();
        frozenContext.logout();
        System.out.println("Frozen Subject still holds identity: " +
                !frozen.getPrincipals().isEmpty());
        System.out.println("Frozen credential destroyed: " +
                frozenToken.isDestroyed());

        Subject rejected = new Subject();
        LoginContext wrong = context(rejected, new char[] {'b','a','d'});
        boolean failed = false;
        try {
            wrong.login();
        } catch (LoginException expected) {
            failed = true;
        }
        System.out.println("Wrong password rejected: " + failed);
        System.out.println("Failed login Subject empty: " +
                (rejected.getPrincipals().isEmpty()
                        && rejected.getPrivateCredentials().isEmpty()));
    }
}
```

Biên dịch với **Java 17+** (không dùng preview features; ví dụ có `record` và pattern matching `instanceof` đã là tính năng chuẩn):

```bash
javac --release 17 JaasCredentialLifecycleDemo.java
java JaasCredentialLifecycleDemo
```

**Stdout được kiểm chứng trên JDK hỗ trợ Java 17 syntax/API:**

```text
Login principal count: 1
Private credential count: 1
Identity snapshot read-only: true
Snapshot mutation rejected: true
Snapshot has private credentials: false
Mutable Subject cleared at logout: true
Session credential destroyed: true
Frozen Subject still holds identity: true
Frozen credential destroyed: true
Wrong password rejected: true
Failed login Subject empty: true
```

### 8.1 Giải thích từng phần và kết quả

**`UserId implements Principal`:** `record` giữ identity string ở dạng immutable. `getName()` trả tên để các JAAS API làm việc được. Chỉ module thêm `UserId` **sau khi xác thực thành công**; không được coi một object `UserId` tự tạo từ request là bằng chứng của authentication.

**`SessionCredential implements Destroyable`:** chứa 16 byte giả lập, tạo mới với `SecureRandom`. Trong demo nó **không phải access token production**, không được bên nào sử dụng để cấp quyền. `destroy()` zero hóa buffer và đánh dấu destroyed, `isDestroyed()` cho phép kiểm chứng; `toString()` cố ý chỉ trả `[redacted]`. Bảo vệ bộ nhớ không tuyệt đối, và zero hóa không hủy các bản sao ngoài object nếu đã tồn tại.

**`OneUseHandler`:** nhận ownership của mảng password do caller truyền, đưa password vào `PasswordCallback` rồi xóa mảng gốc ở `finally`. `PasswordCallback` tự có bản sao, được module xóa bằng `clearPassword()`. Module cũng xóa mảng `actual` mà `getPassword()` trả về. Handler được thiết kế **dùng một lần**; đừng dùng nó để retry nhiều login với password đã được xóa.

**`ExampleModule.login()`:** kiểm tra `name` và `password` giả lập, throw `FailedLoginException` khi sai; không add Principal lúc này. Password expected từ char array trong bài là ví dụ **không an toàn cho production**, chỉ minh họa việc phải hủy các mảng tạm. Với provider thật, việc kiểm tra có thể được thực hiện bởi identity service, Kerberos/KDC, PAM, LDAP qua TLS, salted password verifier hoặc thiết bị bảo mật.

**`commit()`:** chỉ khi `authenticated == true` mới add `UserId` và `SessionCredential` vào Subject. Nếu một bước add ném runtime exception thì rollback phần do module vừa thử thêm, destroy token và bọc failure dưới `LoginException`. Demo không có multi-thread, nên việc kiểm tra `subject.isReadOnly()` rồi thao tác tập được minh họa trong một luồng; hệ thống thực cần quản lý ownership/concurrency và provider-specific cleanup.

**`snapshot.setReadOnly()`:** snapshot chỉ có principal đã xác thực (được sao chép qua constructor `Subject(false, ...)`). Thêm principal mới vào snapshot ném `IllegalStateException`. Snapshot không chứa private credentials, nên không làm rò rỉ demo token. Nó không phải tài khoản đăng nhập mới và không tự sống mãi sau phiên gốc.

**`ok.logout()` trên live Subject mutable:** module remove đúng principal/token đã add rồi `token.destroy()`. Kết quả `Mutable Subject cleared at logout: true` và `Session credential destroyed: true` xác nhận **gỡ tham chiếu khỏi subject** cùng **hủy material**.

**`frozen.setReadOnly()` trước logout:** Subject đã khóa cấu trúc, module **không thể remove** phần tử. Module demo dùng `isReadOnly()` để chỉ destroy nội dung token; vì vậy `Frozen Subject still holds identity: true` và `Frozen credential destroyed: true` **không mâu thuẫn**. Tình huống này cho thấy vì sao đóng live Subject quá sớm có thể khiến identity cũ tồn tại sau logout và cần quản lý trust/lifetime ở tầng khác.

**Sai password:** module throw `FailedLoginException`; `LoginContext.login()` báo failure, không có `commit` thành công. `Subject rejected` vẫn trống. Ứng dụng chỉ biết **đăng nhập bị từ chối**, không nên trao quyền hay hiển thị chi tiết có thể giúp dò username.

### 8.2 Không suy rộng demo thành production JAAS module

Mã trên cố ý đơn giản: một module, một user giả, một luồng, `Configuration` in-memory và secret không được sử dụng cho giao dịch. Nó **không** gồm distributed revocation, bảo vệ cache/ticket, multi-module shared state, logout race giữa threads, account locking, rate limiting, secure password store, remote backend, audit logging, authorization hoặc credentials do provider quản lý. Một triển khai `LoginModule` production còn cần thiết kế exception cleanup ngay cả khi revoke thất bại hoặc subject bị thay đổi bởi các module khác.

Đặc biệt, không được copy `Arrays.equals(actual, expected)` để thay cho cơ chế kiểm tra password production; **không hardcode password** hoặc chọn scheme hash yếu.

## 9. So sánh hai chiến lược “Subject chỉ đọc” lúc logout

| Vấn đề | Khóa live `Subject` sau login | Giữ live mutable, tạo snapshot read-only |
| --- | --- | --- |
| Người dùng code bên ngoài có sửa principals trên live object? | Không thể sửa các tập sau `setReadOnly()` | Chỉ snapshot bị khóa; cần tránh lộ tham chiếu live Subject |
| Logout có remove được principal/credential? | **Không**: Subject đã khóa | Có, nếu module đúng và không có ràng buộc khác |
| Credential `Destroyable` có bị hủy được? | Có thể, theo contract và implementation module | Có thể, module remove và destroy |
| Trạng thái principals còn trong Subject sau logout? | Có thể còn | Có thể trống nếu dọn đủ |
| Snapshot có credential riêng? | Không áp dụng | Tùy thiết kế: nên **chỉ sao chép identity cần thiết**, tránh secrets |
| Dễ dùng nhầm identity cũ sau logout? | Rủi ro cao nếu vẫn giữ tham chiếu live read-only Subject | Vẫn cần invalidate snapshot/token ở application |
| Phù hợp khi nào? | Chỉ khi module/provider được thiết kế cho read-only cleanup | Khi muốn tách trách nhiệm auth lifecycle và identity view |

**Nguyên tắc bảo mật:** Không dựa vào `Subject.isReadOnly()` làm bằng chứng người dùng **đang đăng nhập**. Một `Subject` có thể read-only dù chưa từng xác thực, và có thể read-only mà chứa principal cũ sau logout. Phải dựa vào **authentication result, thời hạn phiên và policy**.

## 10. Lỗi thực tế và cách khắc phục

| Lỗi/triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Login thành công nhưng Subject không có Principal | Module không `commit`, commit trả sai, hoặc flags fail | Dùng đúng flow `LoginContext` và kiểm tra `commit` |
| `FailedLoginException` | Username/password/credential không khớp | Từ chối, áp policy retry, không tiết lộ chi tiết |
| `CredentialExpiredException` | Credential hết hạn theo provider | Yêu cầu re-auth/renew có kiểm soát |
| `AccountExpiredException` | Account hết hạn theo policy | Từ chối, không tự bỏ qua expiration |
| `LoginException` khi `CallbackHandler` chạy | Callback không hỗ trợ, I/O failure | Bọc cause an toàn; không log secret |
| `LoginException` trong `commit` | Read-only Subject, permission denial, lỗi add state | Rollback owned changes, destroy secret, fail closed |
| `IllegalStateException` khi `getPrincipals().add()` | `Subject.setReadOnly()` đã được gọi | Không chỉnh sửa read-only Subject; thiết kế snapshot hoặc lifecycle khác |
| `logout()` xong nhưng Principal còn | Live Subject đã read-only, không gỡ entry được | Đừng dùng Subject ấy làm session active; invalidate authorization/session |
| `logout()` xong nhưng secret còn | `remove` không đồng nghĩa zero hóa; provider không destroy/revoke | Hủy `Destroyable`, remote revoke và audit |
| Credential đã `destroy` vẫn trong `getPrivateCredentials()` | Destroy không tự remove, hoặc subject read-only | Dùng module cleanup tương thích, không coi presence là active |
| Bị `SecurityException` khi đọc private credentials | Runtime có SecurityManager/credential permissions | Kiểm tra security policy, không tắt kiểm soát truy cập |
| Password vô tình xuất hiện trong logs | Logger in callback hoặc `Subject`/credential `toString` | Redact, chỉ log status/correlation ID |
| `getPrivateCredentials(MyType.class).clear()` không làm gì với subject | Typed accessor trả copy, không backed set | Module phải remove từ raw backed set khi mutable và được phép |
| Tài khoản vẫn có quyền sau logout | Cache/token external chưa bị revoke | Kiểm tra session registry, TTL, invalidation, audit |
| User mượn `Subject` rồi tự thêm role | Live Subject writable bị leak | Encapsulation, immutable principal snapshot, auth boundaries |
| `LoginModule.abort()` không dọn token tạm | Cleanup thiếu khi overall login thất bại | Dọn state của module trong abort và `finally` |

**Lưu ý đặc biệt:** `Subject.setReadOnly()` khóa *các tập* chứ không deep-freeze `Principal`/credential, nên một credential do application tự viết có setter vẫn có thể đổi nội dung sau khi subject read-only. Dùng immutable principal, credential có lifecycle rõ ràng và không cung cấp setter tùy tiện cho secret.

## 11. Checklist review code JAAS credential và logout

- [ ] `LoginContext` được dựng với đúng tên cấu hình, handler và `Configuration`/flags do hệ thống quản lý.
- [ ] `LoginModule.login()` chỉ xác thực và giữ state tối thiểu, không commit Principal trước overall success.
- [ ] Raw password không ghi vào `String`, logs, Subject hoặc exception messages.
- [ ] `PasswordCallback.clearPassword()` được gọi; bản sao từ `getPassword()` và từ handler được xóa trong `finally`.
- [ ] Module không tự loop retry khi thất bại; application áp dụng rate limit/backoff/lockout.
- [ ] `commit()` thêm **chính xác owned Principal/credential**; xử lý partial commit failure an toàn.
- [ ] `abort()` dọn state tạm nếu overall authentication fail; `logout()` dọn state module sở hữu.
- [ ] Private credentials có scope/expiry và `Destroyable`/provider cleanup phù hợp; remove và destroy không được coi là một thao tác.
- [ ] Không hiển thị raw `Subject`/credential trên logger; `toString` của credential không tiết lộ material.
- [ ] Nếu Subject read-only, biết `getPrincipals`/credential sets không remove được, nhưng credential destroy vẫn có thể.
- [ ] Không đặt `setReadOnly()` lên live Subject trước khi biết module có hỗ trợ logout read-only.
- [ ] Snapshot identity, nếu dùng, **không** chứa private credentials; principal objects immutable.
- [ ] `LoginException` dẫn tới fail closed, không coi Subject nonempty là authenticated.
- [ ] Audit logs tách user-safe error khỏi diagnostic nội bộ, không lộ account existence/cause có secret.
- [ ] Có integration tests cho success, wrong password, callback failure, read-only mutation, logout cleanup, abort, credential destroy, expired/revoked token và race conditions.

## 12. Bài tập thực hành

**Bài 1 — Phân biệt remove và destroy.**  
Sửa tạm code `ExampleModule.cleanup()` chỉ remove token mà không gọi `destroy()`, rồi quan sát object `SessionCredential` bạn còn giữ ngoài subject. Vì sao `isDestroyed()` vẫn `false`? Sửa lại để cleanup thực sự xóa secret.

**Bài 2 — Read-only trước commit.**  
Thử `live.setReadOnly()` trước `LoginContext.login()`, quan sát commit không thể thêm principal/token. Trình bày vì sao **chỉ callback password đúng không đồng nghĩa login thành công** khi commit thất bại. Không để module `return true` sau exception.

**Bài 3 — Snapshot không giữ secret.**  
Sau login, tạo snapshot chỉ gồm principal. Thử đổi set của snapshot và kiểm tra `IllegalStateException`; kiểm tra `snapshot.getPrivateCredentials().isEmpty()` vẫn đúng. Sau logout live Subject, cân nhắc vì sao snapshot cũ không được xem là active session.

**Bài 4 — Logout Subject đã đóng.**  
Gọi `frozen.setReadOnly()` trước logout. Vì sao module không thể `.remove()` nhưng vẫn có thể `destroy()`? Thử một credential không hỗ trợ `Destroyable` và phân tích failure policy; đừng tuyên bố nó chắc chắn được hủy.

**Bài 5 — Callback failure.**  
Cho `CallbackHandler` ném `UnsupportedCallbackException` khi gặp `PasswordCallback`. Module nên trả `false`, `true` hay ném `LoginException`? Vì sao phải dọn state trong `abort` khi overall login fail?

**Bài 6 — Chính sách timeout và revocation.**  
Với credential dạng access token thật, mô tả tại sao zero hóa mảng trong JVM chưa hủy quyền truy cập của token ở server. Bổ sung TTL, revoke event và invalidation của session registry.

**Bài 7 — Multi-module ownership.**  
Tưởng tượng hai modules cùng thêm principals vào một Subject. Vì sao `subject.getPrincipals().clear()` trong logout của module A là sai? Sửa để A chỉ gỡ principal/credential do chính A thêm.

**Bài 8 — Ranh giới authorization.**  
Một request gửi `"user": "admin"`; application tự tạo `new UserId("admin")` và đưa vào Subject. Vì sao `getPrincipals` chứa admin **không** đủ để cấp quyền admin? Hãy nêu cách identity phải đến từ login success và policy server.

## 13. Câu hỏi tự kiểm tra

**1. `Subject.getPrivateCredentials()` có phải một kho token đã tự mã hóa không?**  
Không. Nó là một tập object có cơ chế quyền truy cập theo JAAS/runtime, **không bảo đảm encryption, zeroization hoặc remote revocation**.

**2. `PasswordCallback.clearPassword()` đã xóa mọi bản sao password chưa?**  
Chưa. Nó xóa bản lưu của callback; mảng nguồn ở handler và bản sao trả về từ `getPassword()` phải được xử lý riêng, tốt nhất trong `finally`.

**3. `Subject.setReadOnly()` chặn thao tác nào?**  
Chặn thêm/xóa phần tử trong principal/public/private credential sets. Nó **không** deep-freeze object, không ngăn destroy credential, không chứng minh user đã xác thực.

**4. Vì sao `logout()` có thể thành công nhưng read-only Subject vẫn giữ principal?**  
Vì các tập không thể bị sửa sau `setReadOnly`; module có thể chỉ hủy secret trong credential. **Presence của principal sau logout không xác nhận session còn hợp lệ.**

**5. Khi `LoginModule.login()` thành công thì có thể add principal luôn không?**  
Thông thường phải chờ **overall login success** và `commit()`. Nếu một module khác fail, `abort()` được gọi và state tạm phải được dọn.

**6. `LoginException` chỉ báo sai password?**  
Không. Nó cũng đại diện lỗi callback, cấu hình, provider hoặc lifecycle; `FailedLoginException` là một trường hợp thường dùng cho credentials không hợp lệ.

**7. Tại sao typed `getPrivateCredentials(MyType.class)` không phải nơi gỡ credentials khỏi subject?**  
Vì accessor đã lọc trả một **tập mới**; thay đổi tập mới không sửa tập backed bởi Subject.

**8. Khi nào dùng snapshot `Subject` chỉ có principals?**  
Khi muốn cung cấp danh tính đã kiểm tra ở dạng **không sửa cấu trúc** cho code bên ngoài, mà vẫn cho live Subject của `LoginContext` có thể logout/cleanup theo lifecycle. Snapshot không tự duy trì thời hạn phiên.

**9. `Destroyable.destroy()` có thể thay thế remote revoke không?**  
Không. Nó chỉ là lifecycle của local credential object; quyền ở server/IdP cần cơ chế revoke/expiry riêng.

**10. Ứng dụng có thể tiếp tục xử lý request sau khi `login()` ném `LoginException` không?**  
Chỉ có thể tiếp tục theo nhánh **unauthenticated** phù hợp, không được cấp quyền dựa vào trạng thái login không được xác nhận.

## 14. Tài liệu chính thức

- [Java SE 17 — `Subject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): principal/public/private credentials, `setReadOnly`, `isReadOnly`, typed credentials accessor và hành vi destroy khi read-only.
- [Java SE 17 — `LoginContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): `login`, `getSubject`, `logout`, constructors và configuration.
- [Java SE 17 — `LoginModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): `initialize`, `login`, `commit`, `abort`, `logout`.
- [Java SE 17 — `LoginException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginException.html): checked authentication/login exception.
- [Java SE 17 — `FailedLoginException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/FailedLoginException.html): xác thực thất bại.
- [Java SE 17 — `PasswordCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): `setPassword`, `getPassword`, `clearPassword`.
- [Java SE 17 — `Destroyable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html): destroyable secrets/credential lifecycle.
- [Java SE 17 — `Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): cấu hình JAAS modules.
- [Oracle Java SE 17 — JAAS Authentication](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication.html): kiến trúc Subject, LoginContext, CallbackHandler và JAAS config.
- [Oracle Java SE 17 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): two-phase login, `commit/abort/logout`, ownership và credential destroy khi Subject read-only.

**Tóm tắt:** `Subject` giữ **identity và credentials** nhưng không tự xác thực/giữ bí mật cho ứng dụng. `LoginModule` phải quản lý `login → commit/abort → logout`, xóa password tạm và hủy credential có thể hủy. **`setReadOnly()` chỉ khóa cấu trúc các tập, không khóa hay thu hồi quyền của secret và không thể thay thế `logout`.** Khi `LoginException` xuất hiện, phải **từ chối quyền**, dọn trạng thái thuộc module và giữ logs sạch bí mật.

# 17.3 LoginContext, Configuration và mô hình LoginModule có thể thay thế

Trong Java Authentication and Authorization Service (**JAAS**), ứng dụng muốn xác thực người dùng hoặc dịch vụ không nhất thiết phải tự viết một hàm đăng nhập gắn chặt với database, Kerberos, LDAP hay hệ thống SSO. JAAS đưa ra mô hình **xác thực có thể thay thế (*pluggable authentication*)**: ứng dụng gọi **`LoginContext`**, một **`Configuration`** quyết định các **`LoginModule`** được kích hoạt và thứ tự/chính sách kết hợp chúng, còn mỗi `LoginModule` hiện thực một cơ chế xác thực cụ thể.

Ba vai trò cốt lõi:

- **`LoginContext`** là bộ **điều phối quy trình đăng nhập/đăng xuất** theo tên ứng dụng. Nó đọc cấu hình, gọi các module qua vòng đời chuẩn và cung cấp một **`Subject`** sau khi đăng nhập thành công.
- **`Configuration`** là **bản thiết kế** xác thực: mỗi application name ánh xạ tới một **danh sách có thứ tự** các `AppConfigurationEntry` gồm tên class `LoginModule`, cờ điều khiển `REQUIRED`/`REQUISITE`/`SUFFICIENT`/`OPTIONAL`, và `options` cho module.
- **`LoginModule`** là **SPI (Service Provider Interface)** gồm năm phương thức `initialize`, `login`, `commit`, `abort`, `logout`. Module thực hiện việc kiểm tra credential và chỉ **gắn Principal/credential vào Subject ở bước commit** khi quá trình chung thành công.

Bài này thuộc phần **17. Xác thực JAAS** trong Java Advanced Security & Cryptography. Các ví dụ dùng **Java 17+**, không cần kết nối Internet hay server Kerberos. Ta sẽ chạy ba chương trình độc lập: xác thực qua callback và `Subject`, mô phỏng các **control flags**, và nạp JAAS `Configuration` từ file. Ví dụ cố tình dùng mật khẩu test/hành vi cho phép hoặc từ chối giả lập để minh họa **contract JAAS**, **không** phải thư viện xác thực password an toàn cho production.

## 1. Mô hình tổng quan và đường đi một lần login

```text
APPLICATION
    |
    | 1. new LoginContext("LearningApp", subject, callback, config)
    v
LoginContext
    |
    | tra cấu hình theo application name
    v
Configuration
    |
    +-- AppConfigurationEntry #1
    |      className = ...PasswordModule
    |      flag = REQUIRED
    |      options = {...}
    |
    +-- AppConfigurationEntry #2
    |      className = ...MfaModule
    |      flag = REQUIRED
    |      options = {...}
    |
    +-- AppConfigurationEntry #3
           className = ...AuditModule
           flag = OPTIONAL
           options = {...}
    |
    v
LoginContext.login()
    |
    +-- instantiate/initialize module(s)
    |       Subject + CallbackHandler + sharedState + options
    |
    +-- PHASE 1: call login() theo thứ tự + control flags
    |
    +-- Nếu xác thực chung thành công:
    |       PHASE 2: call commit()
    |       -> Subject chứa Principal/credentials phù hợp
    |
    +-- Nếu thất bại:
            PHASE 2: call abort()
            -> dọn state/credential tạm
    |
    v
Application receives success / LoginException
    |
    +-- login.getSubject(): danh tính đã xác thực khi thành công
    |
    +-- logout() -> từng LoginModule.logout()
```

**Điểm quan trọng:** `LoginContext` không tự biết mật khẩu đúng là gì, không tự nối LDAP, không sinh token, và không tự đưa user vào role được phép. Module xác thực trả kết quả; `LoginContext` áp dụng cờ và vòng đời; ứng dụng/phần authorization riêng **đánh giá quyền truy cập** từ danh tính và policy.

### 1.1 Bốn đối tượng dễ nhầm

| Thành phần | Vai trò | Có chứa password/credential không? | API |
| --- | --- | --- | --- |
| **`LoginContext`** | Điều phối login, commit/abort và logout; cung cấp Subject | Không tự làm kho password; chuyển CallbackHandler/Subject cho module | `javax.security.auth.login.LoginContext` |
| **`Configuration`** | Quyết định *những module nào*, thứ tự, cờ, option | **Không nên** chứa password/secret hardcode | `javax.security.auth.login.Configuration` |
| **`LoginModule`** | Xác thực theo công nghệ cụ thể; quản lý state/Subject của mình | Có thể **tạm thời** xử lý credential, phải bảo vệ và xóa phù hợp | `javax.security.auth.spi.LoginModule` |
| **`CallbackHandler`** | Cung cấp dữ liệu tương tác như username, password, OTP hoặc nguồn credential | Có thể đưa credential vào `Callback`; không phải nơi kết luận trust | `javax.security.auth.callback.CallbackHandler` |

**`Subject` không phải `LoginContext`.** `Subject` đại diện thực thể đã xác thực, có các tập `Principal`, public credentials và private credentials. Sau khi `login()` thành công, ứng dụng thường nhận nó qua `getSubject()`. Mỗi `Principal` biểu diễn một tên/thuộc tính identity; một `Principal` có tên `admin` không tự trao quyền quản trị nếu ứng dụng chưa có chính sách authorization tương ứng.

## 2. LoginContext: hợp đồng với ứng dụng

Cách dùng phổ biến:

```java
// Minh họa bên trong phương thức có callbackHandler hợp lệ.
LoginContext login = new LoginContext(
        "LearningApp", callbackHandler);
login.login();
Subject subject = login.getSubject();
try {
    // Chỉ dùng các thuộc tính identity đã được xác thực.
} finally {
    login.logout();
}
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập vì thiếu imports, `callbackHandler` và cách quản lý exception. Ví dụ đầy đủ ở mục 7 sẽ chạy được.

### 2.1 Các constructor đáng nhớ

| Constructor | Ý nghĩa |
| --- | --- |
| `new LoginContext(String name)` | Đọc installed `Configuration`, tìm entry của `name`, callback tùy default config |
| `new LoginContext(String name, CallbackHandler handler)` | Installed `Configuration`, handler do caller cung cấp |
| `new LoginContext(String name, Subject subject)` | Xác thực **Subject đã cung cấp**, callback theo default nếu cần |
| `new LoginContext(String name, Subject subject, CallbackHandler handler)` | Installed `Configuration`, Subject và handler tường minh |
| `new LoginContext(String name, Subject subject, CallbackHandler handler, Configuration config)` | **Configuration riêng** cho context; phù hợp ứng dụng muốn kiểm soát rõ module stack, không đổi global config |

**Không có** constructor tiêu chuẩn `LoginContext(String, CallbackHandler, Configuration)` trong Java 17; muốn truyền config riêng cần overload **bốn tham số** với `Subject` có thể đặt `null`. Mẫu chạy được:

```java
LoginContext ctx = new LoginContext(
        "LearningApp", null, callbackHandler, configuration);
```

Khi caller không cung cấp `Subject`, `LoginContext` tạo Subject mới theo contract; khi cung cấp Subject, hệ thống dùng chính Subject đó. **Không nên tái sử dụng một `LoginContext` cho nhiều người dùng/Subject khác nhau**; tài liệu API khuyến nghị context riêng cho mỗi Subject.

### 2.2 Application name là khóa tra cứu, không phải loại xác thực

`"LearningApp"`, `"MyService"` hay `"FileDemo"` là **tên entry** trong Configuration:

```text
LoginContext("LearningApp") --> Configuration.getAppConfigurationEntry("LearningApp")
                                     |
                                     +--> list of LoginModules + flags + options
```

Nếu không có entry cho `name`, `LoginContext` theo contract còn thử entry **`"other"`**. Nếu cả hai đều không có, constructor có thể ném `LoginException`. Chính sách fallback này hữu ích cho một số hệ thống, nhưng có thể gây **thay thế nhầm cơ chế xác thực** nếu cấu hình `other` quá dễ dãi. Với ứng dụng có nhiều trust domain, hãy kiểm tra tên entry và cấu hình fallback một cách có chủ ý.

### 2.3 login(), getSubject(), logout()

- **`login()`:** thực hiện các module theo cấu hình, hoàn thành cơ chế xác thực chung hoặc ném `LoginException`.
- **`getSubject()`:** lấy `Subject` tương ứng. Đừng dùng Subject như bằng chứng đăng nhập trước khi `login()` trả về thành công; trường hợp chưa đăng nhập có thể trả `null` theo điều kiện constructor/trạng thái.
- **`logout()`:** gửi yêu cầu logout đến các module trong context; **module tự dọn** Principal và credential mà nó đã thêm. Logout không tự revoke session token/JWT ở dịch vụ bên ngoài nếu module không triển khai.
- **Không tự động retry** khi password sai: rate limiting, lockout, backoff, CAPTCHA hoặc quy tắc retry thuộc application/auth service. Tài liệu JAAS hướng dẫn module không tự đặt delay/retry mơ hồ trong `login()`.

## 3. Configuration: cách chọn và thay LoginModule

`Configuration` là abstract class trả về **`AppConfigurationEntry[]`** cho application name. Mỗi entry có ba phần:

```text
AppConfigurationEntry {
    loginModuleName: "com.example.auth.PasswordModule"
    controlFlag: REQUIRED
    options: {"debug": "false", "realm": "example"}
}
```

Về mặt Java:

```java
// Đoạn API minh họa, không phải file độc lập.
AppConfigurationEntry item = new AppConfigurationEntry(
        PasswordModule.class.getName(),
        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
        Map.of("realm", "demo"));
```

**Các thuộc tính:**

1. **Class name**: fully qualified name của một `LoginModule` có thể load được, triển khai interface đúng và **có public no-argument constructor**. Khi dùng nested class trong demo, Java class name có dấu **`$`**.
2. **Control flag**: quy tắc kết hợp thành công/thất bại với module khác; không phải “mức độ bảo mật” hay “priority”.
3. **Options**: map **riêng cho module**, module quyết định tên và ý nghĩa. `debug`, `tryFirstPass`, `useFirstPass` không được bảo đảm có chung semantics cho mọi module.

### 3.1 Declarative JAAS configuration file

Một cấu hình file thường có cú pháp:

```text
ApplicationName {
    fully.qualified.ModuleClass required optionName="value";
    another.ModuleClass optional debug="false";
};
```

Các module trong cùng block chạy theo **đúng thứ tự được liệt kê**, tùy cờ có thể dừng sớm. Dấu chấm phẩy **sau từng module** và sau dấu đóng `}` có ý nghĩa cú pháp; option string được đặt trong dấu ngoặc kép theo default configuration syntax.

Đoạn minh họa cho một hệ thống xác thực nhiều bước:

```text
ServiceLogin {
    com.example.auth.PasswordLoginModule required realm="employees";
    com.example.auth.OtpLoginModule required issuer="company";
    com.example.auth.AuditLoginModule optional debug="false";
};
```

**Các class `com.example.auth.*` chỉ là tên minh họa, không phải class có sẵn trong JDK.** Ví dụ runnable thực tế ở mục 9 sử dụng class có thật được định nghĩa trong file Java kèm theo. Config chỉ định **module**, không tạo implementation và cũng không tự cài đặt LDAP/OTP.

Với default ConfigFile implementation của JDK, có thể cung cấp file theo system property:

```bash
java -Djava.security.auth.login.config=jaas.conf MainClass
```

Nếu application dùng installed config, nó truy vấn `Configuration.getConfiguration()`. Cấu hình cụ thể có thể đến từ system properties, các `login.config.url.n` security properties và provider, với precedence theo reference implementation và cách khởi động. Đừng suy đoán một file `jaas.conf` chắc chắn được app dùng khi code truyền **Configuration riêng** vào constructor bốn tham số.

**Không đặt password, secret token, private key hoặc thông tin kết nối nhạy cảm vào JAAS conf**: option không tự được mã hóa, có thể hiện trong file, memory, diagnostics và process config. Dùng secret management thích hợp, cấu hình file nên chứa **tên realm, issuer, mode, endpoint đã kiểm soát** và các tùy chọn không bí mật.

### 3.2 Configuration lập trình được

Thay vì dựa vào file toàn JVM, ứng dụng có thể subclass:

```java
// Đoạn minh họa; MyLoginModule phải tồn tại và implement LoginModule.
Configuration config = new Configuration() {
    @Override
    public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
        if (!"LearningApp".equals(name)) {
            return null;
        }
        return new AppConfigurationEntry[]{
            new AppConfigurationEntry(
                    MyLoginModule.class.getName(),
                    AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                    Map.of())
        };
    }
};

LoginContext context = new LoginContext(
        "LearningApp", null, callbackHandler, config);
```

**Đây là mã minh họa không độc lập** vì `MyLoginModule` và `callbackHandler` chưa khai báo. Bài code hoàn chỉnh ở mục 7 tự định nghĩa module và Configuration tương tự.

Ưu điểm: tách policy xác thực theo tenant, environment hoặc test mà **không thay global installed Configuration**. Cần cố định/cập nhật version config cho một login attempt; đừng thay module stack giữa chừng một cách không xác định.

### 3.3 Installed configuration và refresh

`Configuration.getConfiguration()` lấy installed JAAS configuration; `Configuration.setConfiguration(...)` thay cài đặt global trong runtime. Khi có nhiều app/library trong cùng JVM, việc gọi `setConfiguration` để sửa một bài toán cục bộ có thể ảnh hưởng những caller khác.

`Configuration.refresh()` là yêu cầu provider **nạp lại/cập nhật** cấu hình theo implementation. Không được suy ra rằng:
- Mọi provider đều hỗ trợ hot reload tức thời;
- Một `LoginContext` đã tạo sẽ tự thay module list giữa một login;
- `setConfiguration` hoặc `refresh` là một thao tác atomic migration mọi active sessions.

**Nếu cần cấu hình động**, xây quy trình versioning, đồng bộ thay đổi, tạo context mới và test consistency; sử dụng Configuration được truyền tường minh cho context sẽ dễ cô lập thay đổi hơn.

## 4. Mô hình LoginModule có thể thay thế

Một `LoginModule` là **plugin xác thực**, không phụ thuộc trực tiếp vào giao diện web/console. Hai module có thể triển khai cùng SPI nhưng xác thực bằng kỹ thuật rất khác:

```text
Application:
    LoginContext("ServiceLogin").login()

Configuration A:
    PasswordDatabaseLoginModule required

Configuration B:
    KerberosLoginModule required

Configuration C:
    CertificateLoginModule required
    AuditLoginModule optional

Configuration D:
    PasswordLoginModule required
    OneTimePasswordModule required
```

Ứng dụng gọi LoginContext vẫn như cũ, nhưng **cơ chế thực tế đổi theo config và module implementation**. Điều này gọi là **pluggable authentication**. Tuy nhiên, module thay thế phải tương thích với yêu cầu về `Subject`/Principal type, credential source, trust level, exception semantics và authorization contract của ứng dụng. Thay module không có nghĩa tự bảo đảm **bảo mật tương đương**.

### 4.1 LoginModule interface: năm phương thức

```java
package javax.security.auth.spi;

// Chữ ký giải thích, không phải file nguồn mới để tự tạo package javax.
public interface LoginModule {
    void initialize(
            Subject subject,
            CallbackHandler callbackHandler,
            Map<String, ?> sharedState,
            Map<String, ?> options);
    boolean login() throws LoginException;
    boolean commit() throws LoginException;
    boolean abort() throws LoginException;
    boolean logout() throws LoginException;
}
```

Bảng nhiệm vụ:

| Phương thức | Thời điểm | Công việc chính | Điều nên tránh |
| --- | --- | --- | --- |
| **`initialize`** | Sau khi JAAS tạo instance, trước các phase | Lưu Subject, CallbackHandler, sharedState, options cần dùng | Kết nối tốn kém không có timeout, tự thêm Principal trước khi kiểm tra |
| **`login`** | Phase 1 | Nhận credential, xác thực, lưu tạm identity/auth status **trong module** | Thêm Principal vào Subject quá sớm; log password; tự retry vô hạn |
| **`commit`** | Phase 2, khi tổng thể authentication thành công | Nếu module của mình thành công, thêm Principal/credential hợp lệ vào Subject; xóa state tạm | Commit identity của module thất bại; giữ plaintext password lâu |
| **`abort`** | Phase 2, khi authentication chung thất bại hoặc cần rollback | Hủy credential/state tạm, rollback những thay đổi module chịu trách nhiệm | Để lại Principal/token do một nửa quá trình sinh ra |
| **`logout`** | Khi `LoginContext.logout()` được gọi | Gỡ Principal/credential do **module** đã thêm và hủy session/resource nếu thuộc trách nhiệm | `subject.getPrincipals().clear()` bừa bãi, xóa dữ liệu của module khác |

Module phải có **public constructor không tham số** để được LoginContext tạo qua provider/class loading. Public **static nested class** với default no-arg constructor cũng dùng được cho demo.

### 4.2 Tại sao login và commit phải tách?

Giả sử stack có hai module:

```text
PasswordModule  REQUIRED  -> password đúng
OtpModule       REQUIRED  -> OTP sai
```

Nếu `PasswordModule.login()` **đã thêm Principal vào Subject**, sau khi OTP thất bại Subject có thể lưu một phần identity dù **overall login bị từ chối**. Do đó giao ước chuẩn:

```text
PHASE 1:
    PasswordModule.login() -> true (giữ pending state riêng)
    OtpModule.login()      -> throws FailedLoginException

OVERALL FAILURE:
    PasswordModule.abort()
    OtpModule.abort()
    Subject không có identity mới được commit
```

Nếu cả hai thành công:

```text
PHASE 1:
    PasswordModule.login() -> true
    OtpModule.login()      -> true

PHASE 2:
    PasswordModule.commit() -> thêm Principal vào Subject
    OtpModule.commit()      -> bổ sung credential/assurance nếu phù hợp
    LoginContext.login()    -> returns successfully
```

**Điểm quyết định:** `login() == true` của **một module** không đồng nghĩa **overall LoginContext success**. Chính các **control flags** của Configuration quyết định ngưỡng thành công, và `commit` chỉ chạy theo logic phase sau khi điều kiện chung thỏa.

## 5. REQUIRED, REQUISITE, SUFFICIENT, OPTIONAL

Bốn cờ có ý nghĩa kiểm soát **thứ tự xác thực và điều kiện thành công**. Đây là trọng tâm khiến JAAS hỗ trợ stack module thay vì một hàm boolean.

| Flag | Khi module thành công | Khi module thất bại | Ảnh hưởng tới kết quả chung |
| --- | --- | --- | --- |
| **`REQUIRED`** | Tiếp tục đánh giá các module sau | **Vẫn tiếp tục** đánh giá module sau | Module này **phải thành công**; lỗi của nó không bị một `SUFFICIENT` phía sau xóa bỏ |
| **`REQUISITE`** | Tiếp tục đánh giá module sau | **Dừng ngay** phase login stack | Module này **phải thành công**; khi thất bại trả lỗi sớm |
| **`SUFFICIENT`** | Có thể **dừng sớm thành công** nếu **chưa có lỗi REQUIRED/REQUISITE trước đó** | Tiếp tục các module sau | Không bắt buộc; một SUFFICIENT thành công có thể giúp kết thúc stack |
| **`OPTIONAL`** | Tiếp tục các module sau | Tiếp tục các module sau | Không bắt buộc, trừ trường hợp stack không có required/requisite thì cần ít nhất một sufficient/optional thành công |

**Quy tắc chung theo Java `Configuration`:** tất cả module **REQUIRED/REQUISITE đã được thực thi liên quan** phải thành công. Nếu một `SUFFICIENT` thành công, các module REQUIRED/REQUISITE **đứng trước nó** phải thành công để kết thúc sớm. Nếu không có REQUIRED hoặc REQUISITE nào, cần **ít nhất một SUFFICIENT hoặc OPTIONAL thành công**.

### 5.1 Thứ tự tạo ra sự khác biệt

Các stack sau cho kết quả khác nhau:

```text
A. OPTIONAL fail -> REQUIRED pass
   => SUCCESS

B. REQUIRED fail -> SUFFICIENT pass
   => FAILURE (required fail không được bỏ qua)

C. REQUISITE fail -> OPTIONAL pass
   => FAILURE; optional không được gọi

D. SUFFICIENT pass -> REQUIRED fail
   => SUCCESS sớm; required phía sau không được gọi

E. OPTIONAL fail (chỉ một module)
   => FAILURE vì không module nào thành công
```

Lưu ý khác biệt **lỗi ném `LoginException`** và **`login()` trả `false`**: LoginModule contract cho phép trả `false` khi module nên được bỏ qua; không dùng `return false` để diễn tả “mật khẩu sai” cho module xác thực bắt buộc trong code minh họa. Ví dụ cố ý ném **`FailedLoginException`** khi một module phủ quyết, để ý nghĩa test rõ ràng.

### 5.2 Vì sao không dùng OPTIONAL cho tất cả?

Một stack gồm `AuditModule OPTIONAL` và `PasswordModule OPTIONAL` có thể **chấp thuận** nếu audit module trả success dù password module thất bại. Cấu hình cờ sai có thể tạo **bypass xác thực**. Đặc biệt, module “audit/logging” không nên được thiết kế trả về `true` theo cách biến một stack toàn OPTIONAL thành thành công khi không có module xác thực thực sự.

**Nguyên tắc:** thiết kế cờ theo **threat model**, không theo ý muốn “login ít báo lỗi”; unit-test từng tổ hợp thành công/thất bại, bảo đảm mọi yếu tố bắt buộc thực sự là bắt buộc. MFA muốn **password và OTP đều đúng** thường cần các module có policy tương ứng, ví dụ cả hai REQUIRED hoặc xử lý logic xác thực tập trung đã kiểm định; không gắn một bước MFA là OPTIONAL chỉ vì đôi khi người dùng không có OTP.

## 6. Subject, Principal và Credentials

`javax.security.auth.Subject` đại diện thực thể được xác thực và có ba tập dữ liệu chính:

```text
Subject
  |
  +-- Set<Principal>
  |      ví dụ: UserPrincipal("student"),
  |              RolePrincipal("reader") (nếu trusted policy cấp)
  |
  +-- publicCredentials
  |      dữ liệu credential có thể công khai theo contract
  |
  +-- privateCredentials
         credential bí mật/nhạy cảm, phải bảo vệ quyền đọc và vòng đời
```

`Principal` là interface có `getName()`; trong Java 17 ta có thể dùng **`record AppPrincipal(String getName) implements Principal`** cho ví dụ nhỏ. Trong hệ thống thật, thiết kế Principal types ổn định, mapping identity → role, tenant, scope và authorization policy **cần được phân tích riêng**. Không suy ra `subject.getPrincipals().contains("admin")` là đủ quyền nếu không có Principal type/issuer/trust contract đúng.

### 6.1 Khi nào cập nhật Subject?

- **Trước login:** Subject mới/cũ có thể có Principals được cấp bởi module khác; module cần giữ nguyên nếu không sở hữu.
- **Trong login:** lưu identity tạm (`pendingPrincipal`) trong instance **không** thêm vào Subject.
- **Trong commit:** chỉ thêm identity nếu module mình đã xác thực thành công, overall flow thành công.
- **Trong abort:** xóa state/tokens tạm, rollback những thay đổi có thể đã phát sinh.
- **Trong logout:** gỡ **đúng những Principal/credential của module mình**. Không xóa toàn bộ `Subject.getPrincipals()` vì module khác có thể đã thêm data hợp lệ.
- **Subject read-only:** nếu caller khóa `Subject.setReadOnly()`, việc thêm/gỡ Principal sẽ bị từ chối; module nên xử lý fail-closed và báo `LoginException` phù hợp.

### 6.2 Đừng gắn password thô làm Principal

Principal biểu diễn danh tính (user, service hoặc role đã xác thực), **không phải password**. Mật khẩu chỉ dùng để kiểm tra, sau đó nên dọn memory tạm; không đưa `PasswordCallback` hoặc plaintext vào `Subject.getPublicCredentials()`, log hoặc error. Với token/session key trong privateCredentials, bảo đảm vòng đời phù hợp và `Destroyable` khi loại credential hỗ trợ.

## 7. Java 17+ chạy được: LoginContext + custom LoginModule + Subject

Ví dụ này không cần file cấu hình: ta tạo `Configuration` trong code và truyền trực tiếp cho `LoginContext`. `PasswordModule` minh họa vòng đời đầy đủ; `CallbackHandler` nhận user/password từ input test; `commit` thêm `AppPrincipal`, `logout` gỡ Principal, login sai ném `FailedLoginException`.

**Lưu ý bảo mật:** `"lab-only"` là mật khẩu test được hardcode để demo. Chương trình **không** có database password hashes, Argon2id/PBKDF2, throttle hay lưu trữ thông tin đăng nhập an toàn. So sánh `char[]` chỉ nhằm kiểm chứng JAAS callback lifecycle, **không phải một password authenticator dành cho production**.

Lưu **`JaasLoginDemo.java`**:

```java
import java.security.Principal;
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasLoginDemo {
    public record AppPrincipal(String getName) implements Principal {}

    public static final class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private AppPrincipal pending;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                               Map<String, ?> sharedState,
                               Map<String, ?> options) {
            this.subject = Objects.requireNonNull(subject);
            this.handler = Objects.requireNonNull(handler);
        }

        @Override
        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("Username: ");
            PasswordCallback password =
                    new PasswordCallback("Password: ", false);
            try {
                handler.handle(new Callback[]{name, password});
                char[] received = password.getPassword();
                char[] expected = "lab-only".toCharArray();
                boolean correctUser =
                        "student".equals(name.getName());
                boolean correctPassword =
                        constantTimeEqual(received, expected);
                Arrays.fill(expected, '\0');

                if (!correctUser || !correctPassword) {
                    throw new FailedLoginException("Invalid credentials");
                }
                pending = new AppPrincipal(name.getName());
                loggedIn = true;
                return true;
            } catch (UnsupportedCallbackException
                     | java.io.IOException e) {
                LoginException ex = new LoginException("Callback failed");
                ex.initCause(e);
                throw ex;
            } finally {
                password.clearPassword();
            }
        }

        private static boolean constantTimeEqual(
                char[] left, char[] right) {
            if (left == null || right == null) return false;
            int diff = left.length ^ right.length;
            int max = Math.max(left.length, right.length);
            for (int i = 0; i < max; i++) {
                char a = i < left.length ? left[i] : 0;
                char b = i < right.length ? right[i] : 0;
                diff |= a ^ b;
            }
            return diff == 0;
        }

        @Override
        public boolean commit() throws LoginException {
            if (!loggedIn) return false;
            if (subject.isReadOnly()) {
                throw new LoginException("Subject read-only");
            }
            subject.getPrincipals().add(pending);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            reset();
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed) {
                if (subject.isReadOnly()) {
                    throw new LoginException("Subject read-only");
                }
                subject.getPrincipals().remove(pending);
            }
            reset();
            return true;
        }

        private void reset() {
            pending = null;
            loggedIn = false;
            committed = false;
        }
    }

    public static final class UserCallbacks implements CallbackHandler {
        private final String user;
        private final char[] pass;

        UserCallbacks(String user, char[] pass) {
            this.user = user;
            this.pass = pass.clone();
        }

        @Override
        public void handle(Callback[] callbacks)
                throws UnsupportedCallbackException {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName(user);
                } else if (callback instanceof PasswordCallback pwd) {
                    pwd.setPassword(pass);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        }

        void clear() {
            Arrays.fill(pass, '\0');
        }
    }

    public static final class InMemoryConfiguration
            extends Configuration {
        @Override
        public AppConfigurationEntry[] getAppConfigurationEntry(
                String name) {
            if (!"LearningApp".equals(name)) return null;
            return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(
                            PasswordModule.class.getName(),
                            AppConfigurationEntry
                                    .LoginModuleControlFlag.REQUIRED,
                            Map.of())
            };
        }
    }

    public static void main(String[] args) throws Exception {
        Configuration config = new InMemoryConfiguration();

        UserCallbacks good = new UserCallbacks(
                "student", "lab-only".toCharArray());
        try {
            LoginContext login = new LoginContext(
                    "LearningApp", null, good, config);
            login.login();
            Subject subject = login.getSubject();
            System.out.println("Login successful: "
                    + (subject != null));
            System.out.println("Principals after login: "
                    + subject.getPrincipals().stream()
                            .map(Principal::getName)
                            .sorted().toList());

            login.logout();
            System.out.println("Principals after logout: "
                    + subject.getPrincipals().size());
        } finally {
            good.clear();
        }

        UserCallbacks bad = new UserCallbacks(
                "student", "wrong".toCharArray());
        try {
            LoginContext login = new LoginContext(
                    "LearningApp", null, bad, config);
            boolean rejected = false;
            try {
                login.login();
            } catch (LoginException expected) {
                rejected = true;
            }
            System.out.println("Wrong password rejected: "
                    + rejected);
        } finally {
            bad.clear();
        }
    }
}
```

Biên dịch/chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 JaasLoginDemo.java
java JaasLoginDemo
```

Stdout trên Java 17+ (đã thử nghiệm):

```text
Login successful: true
Principals after login: [student]
Principals after logout: 0
Wrong password rejected: true
```

### 7.1 Giải thích từng lớp

- **`AppPrincipal`** là `record` triển khai `Principal`. Tên người dùng được expose qua `getName()`. Java record `equals`/`hashCode` dựa trên state nên phù hợp minh họa trong `Set<Principal>`.
- **`PasswordModule`** là public static nested class, có no-arg constructor mặc định để `LoginContext` nạp thông qua `PasswordModule.class.getName()` (dạng `JaasLoginDemo$PasswordModule` ở runtime).
- **`initialize`** nhận `Subject`/`CallbackHandler` cùng hai maps. Demo không dùng `sharedState` hoặc `options`, hợp lệ vì module có quyền bỏ qua tùy nhu cầu.
- **`NameCallback` và `PasswordCallback`** là hai object giao thức callback. Module không cần biết credential đến từ console, GUI, HTTP request đã được validate hay test handler.
- **`login`** so sánh input của test, đặt `pending` và `loggedIn` riêng trong module; **chưa thêm Principal**.
- **`commit`** chỉ thêm `pending` vào `Subject` khi bản thân module login thành công và tổng thể được JAAS chuyển đến phase commit.
- **`abort`/`logout`** dọn state của module, remove Principal mà module quản lý; không gọi `subject.getPrincipals().clear()`.
- **`InMemoryConfiguration`** trả đúng một `AppConfigurationEntry` với flag REQUIRED; một login sai dẫn đến `LoginException`.
- **`main`** dùng **hai LoginContext riêng** cho hai lần login: thành công rồi logout, sau đó login sai bị từ chối.

### 7.2 Những giới hạn bảo mật có chủ ý

**Mật khẩu demo không an toàn:** `constantTimeEqual` ở đây chỉ tránh nhánh trả sớm dựa trên nội dung ký tự; runtime/độ dài input và nhiều yếu tố khác vẫn có thể bị quan sát. Nó không thay thế **password hashing chậm**, salt ngẫu nhiên và các kiểm soát login cần thiết. Production nên dùng identity provider hoặc password verification có **Argon2id/scrypt/bcrypt/PBKDF2** theo chính sách, TLS khi truyền credential, rate limiting, audit, MFA và bảo vệ credential trong memory.

**Không lưu password trong Subject:** demo gỡ password khỏi `PasswordCallback` bằng `clearPassword()`. Handler riêng vẫn có buffer được xóa ở finally; mảng do `PasswordCallback.getPassword()` trả và các bản sao trong JVM có thể có vòng đời khác. Không đảm bảo **xóa mọi bản sao heap** chỉ bằng `Arrays.fill`.

**Không dùng module để tự phát role:** xác thực `student` không tự suy ra `role=admin`. Nếu cần roles/entitlements, chúng phải đến từ nguồn đáng tin và được kiểm tra tại thời điểm authorization.

**Lưu ý lỗi commit:** nếu Subject read-only khiến `commit` thất bại, cách module xử lý exception/rollback phải fail closed. Dù code lab đơn giản, production module cần quản lý cleanup nhất quán, không để Principal/credential sót lại sau thất bại một phần.

## 8. Java 17+: kiểm thử thứ tự các cờ bằng một LoginModule dùng lại

Một LoginModule có thể **được cấu hình nhiều lần** trong cùng stack với các options khác nhau. Ví dụ sau định nghĩa **`StepModule`** luôn quyết định kết quả theo option `allow`, đồng thời ghi tên các module mà `login()` thực sự được gọi. Nhờ vậy có thể quan sát chính xác **REQUIRED, REQUISITE, SUFFICIENT, OPTIONAL** và vị trí của mỗi module.

**Chỉ dành cho kiểm thử logic cờ**: `allow="true"` trong configuration là hành vi giả lập, hoàn toàn **không** xác thực một người thật; tuyệt đối không dùng module như thế trong production.

Lưu **`JaasStackDemo.java`**:

```java
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasStackDemo {
    private static final List<String> TRACE = new ArrayList<>();

    public static final class StepModule implements LoginModule {
        private String label;
        private boolean allow;
        private boolean authenticated;

        @Override
        public void initialize(
                Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            label = (String) options.get("label");
            allow = Boolean.parseBoolean((String) options.get("allow"));
        }

        @Override
        public boolean login() throws LoginException {
            TRACE.add(label);
            if (!allow) {
                throw new FailedLoginException("Denied by " + label);
            }
            authenticated = true;
            return true;
        }

        @Override
        public boolean commit() {
            return authenticated;
        }

        @Override
        public boolean abort() {
            authenticated = false;
            return true;
        }

        @Override
        public boolean logout() {
            authenticated = false;
            return true;
        }
    }

    static AppConfigurationEntry entry(
            String label, boolean allow,
            AppConfigurationEntry.LoginModuleControlFlag flag) {
        return new AppConfigurationEntry(
                StepModule.class.getName(),
                flag,
                Map.of(
                        "label", label,
                        "allow", Boolean.toString(allow)));
    }

    public static void main(String[] args) throws Exception {
        var required =
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED;
        var requisite =
                AppConfigurationEntry.LoginModuleControlFlag.REQUISITE;
        var sufficient =
                AppConfigurationEntry.LoginModuleControlFlag.SUFFICIENT;
        var optional =
                AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL;

        run("optional_then_required",
                new AppConfigurationEntry[]{
                        entry("optional-fail", false, optional),
                        entry("required-pass", true, required)
                });

        run("required_fail_before_sufficient",
                new AppConfigurationEntry[]{
                        entry("required-fail", false, required),
                        entry("sufficient-pass", true, sufficient)
                });

        run("requisite_short_circuit",
                new AppConfigurationEntry[]{
                        entry("requisite-fail", false, requisite),
                        entry("later-pass", true, optional)
                });

        run("sufficient_short_circuit",
                new AppConfigurationEntry[]{
                        entry("sufficient-pass", true, sufficient),
                        entry("later-fail", false, required)
                });

        run("only_optional_failed",
                new AppConfigurationEntry[]{
                        entry("only-optional-fail", false, optional)
                });
    }

    static void run(String scenario, AppConfigurationEntry[] entries)
            throws Exception {
        TRACE.clear();

        Configuration config = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                return scenario.equals(name)
                        ? entries.clone() : null;
            }
        };

        LoginContext ctx = new LoginContext(
                scenario, null, callbacks -> {}, config);
        boolean passed;
        try {
            ctx.login();
            passed = true;
        } catch (LoginException expected) {
            passed = false;
        }
        if (passed) ctx.logout();

        System.out.println(
                scenario + ": " + passed
                        + "; ran=" + String.join(",", TRACE));
    }
}
```

```bash
javac -encoding UTF-8 JaasStackDemo.java
java JaasStackDemo
```

Stdout đã kiểm tra trên JDK:

```text
optional_then_required: true; ran=optional-fail,required-pass
required_fail_before_sufficient: false; ran=required-fail,sufficient-pass
requisite_short_circuit: false; ran=requisite-fail
sufficient_short_circuit: true; ran=sufficient-pass
only_optional_failed: false; ran=only-optional-fail
```

### 8.1 Đọc năm case theo thứ tự

**Case 1 — OPTIONAL fail, REQUIRED pass:** OPTIONAL thất bại nhưng không bắt buộc. REQUIRED thành công nên overall login thành công.

**Case 2 — REQUIRED fail, SUFFICIENT pass:** SUFFICIENT vẫn được gọi, nhưng **không thể che lỗi REQUIRED trước đó**. Kết quả false dù module sau báo thành công.

**Case 3 — REQUISITE fail:** dừng ngay phase login; `later-pass` không xuất hiện trong `TRACE`. Điều này tránh chạy những module phía sau khi một điều kiện bắt buộc không đạt.

**Case 4 — SUFFICIENT pass:** khi không có lỗi required/requisite trước, JAAS có thể kết thúc phase login sớm; `later-fail` không được gọi. Thứ tự và flag quyết định đường đi.

**Case 5 — Chỉ có OPTIONAL fail:** không có module nào xác thực thành công, nên overall login vẫn thất bại. **OPTIONAL không đồng nghĩa “cho phép login không cần xác thực”.**

**Giới hạn test:** `StepModule` không thêm Principal vào Subject; nó chỉ mô phỏng control flow. `TRACE` là static list cho single-threaded unit test, **không** phù hợp theo dõi người dùng/concurrent logins trong production. Với module thật, cần test luôn commit/abort/logout và cleanup của từng plugin.

### 8.2 Những stack đáng nghi

```text
# NGUY HIỂM nếu AuditModule trả success mà PasswordModule fail:
Service {
    com.example.AuditModule optional;
    com.example.PasswordModule optional;
};

# NGUY HIỂM nếu SufficientPassModule có thể luôn success:
Service {
    com.example.SufficientPassModule sufficient;
    com.example.RequiredPasswordModule required;
};
```

Hai block trên là **mã cấu hình minh họa, không có implementation thực tế**. Chúng cho thấy vì sao việc thay module/cờ **là thay đổi security policy**, không chỉ thay file config vô hại. Có module optional ghi log lỗi không đồng nghĩa module nên trả `true` như một proof of authentication.

## 9. Java 17+: nạp Configuration từ file jaas.conf

Hai ví dụ trước truyền `Configuration` object tường minh. Tiếp theo ta kiểm tra **default JAAS configuration parser**: ứng dụng gọi constructor `LoginContext("FileDemo", handler)`, còn module class và option được lấy từ file `jaas.conf`.

Để demo chạy độc lập, ta định nghĩa `AllowModule` là static nested class. Nó **luôn chấp nhận** user — **chỉ để chứng minh file config thực sự được đọc**, không phải một authentication mechanism.

Tạo **hai file trong cùng thư mục**.

**File 1 — `jaas.conf`**:

```text
FileDemo {
    JaasFileConfigDemo$AllowModule required principalName="from-file";
};
```

Dấu **`$`** là một phần tên JVM của nested class `JaasFileConfigDemo.AllowModule`; với class có package trong production sẽ dùng **fully qualified class name** theo classpath/modulepath đúng. `principalName` là **option tùy biến** do module của ví dụ định nghĩa, không phải key JAAS hỗ trợ tự động.

**File 2 — `JaasFileConfigDemo.java`**:

```java
import java.security.Principal;
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasFileConfigDemo {
    public record AppPrincipal(String getName) implements Principal {}

    // Module "cho qua" chỉ để minh họa cấu hình file;
    // tuyệt đối không sử dụng làm cơ chế xác thực thật.
    public static final class AllowModule implements LoginModule {
        private Subject subject;
        private AppPrincipal assigned;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(
                Subject subject, CallbackHandler cb,
                Map<String, ?> shared, Map<String, ?> options) {
            this.subject = subject;
            this.assigned = new AppPrincipal(
                    (String) options.get("principalName"));
        }

        @Override
        public boolean login() {
            loggedIn = true;
            return true;
        }

        @Override
        public boolean commit() {
            if (!loggedIn) return false;
            subject.getPrincipals().add(assigned);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() {
            if (committed) {
                subject.getPrincipals().remove(assigned);
            }
            loggedIn = false;
            committed = false;
            return true;
        }

        @Override
        public boolean logout() {
            if (committed) {
                subject.getPrincipals().remove(assigned);
            }
            loggedIn = false;
            committed = false;
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        LoginContext login = new LoginContext(
                "FileDemo",
                (CallbackHandler) callbacks -> {});
        login.login();
        System.out.println("Principal from file config: "
                + login.getSubject().getPrincipals()
                        .iterator().next().getName());
        login.logout();
        System.out.println("Principal count after logout: "
                + login.getSubject().getPrincipals().size());
    }
}
```

Biên dịch và truyền property **trước tên main class**:

```bash
javac -encoding UTF-8 JaasFileConfigDemo.java
java -Djava.security.auth.login.config=jaas.conf JaasFileConfigDemo
```

Stdout:

```text
Principal from file config: from-file
Principal count after logout: 0
```

**Điều chứng minh được:**

1. `LoginContext("FileDemo", handler)` không truyền config tường minh nên dùng installed Configuration theo Java.
2. File `jaas.conf` ánh xạ tên `FileDemo` tới `JaasFileConfigDemo$AllowModule` và option `principalName="from-file"`.
3. `LoginContext` nạp class, gọi `initialize` với options, sau đó gọi `login`/`commit`.
4. Module tạo `AppPrincipal("from-file")` trong `commit` và gỡ khỏi Subject trong `logout`.
5. Không có password/OTP/CA trong bài test; **kết quả thành công không phải bằng chứng xác thực thật**.

Nếu đường dẫn `jaas.conf` sai, tên entry `FileDemo` không khớp, class không tìm được hoặc file syntax sai, constructor hoặc `login()` có thể thất bại (tùy nguyên nhân và thời điểm). Cần giữ nguyên **cause** để chẩn đoán nhưng không log credential.

## 10. CallbackHandler: tách giao diện nhập credential khỏi LoginModule

`CallbackHandler` là một **cầu nối** giữa module xác thực và nguồn dữ liệu của ứng dụng. Module đưa ra yêu cầu `Callback[]` và handler cung cấp giá trị.

```text
PasswordModule.login()
     |
     +-- NameCallback("Username")
     +-- PasswordCallback("Password")
                  |
                  v
          CallbackHandler.handle(callbacks)
                  |
            +-----+--------------+
            |                    |
      Console handler       GUI / server handler
            |                    |
       user input           credential đã nhận/validate
            |                    |
            +----------+---------+
                       v
                callbacks đã điền
                       |
                       v
             module.verify(credentials)
```

Một module có thể yêu cầu callback cho **username, password, text, confirmation**, hoặc callback đặc thù khác theo provider. Handler phải nhận đúng các `Callback` hoặc ném `UnsupportedCallbackException`; không lặng lẽ trả chuỗi rỗng và coi là xác thực thành công.

**Phân biệt trách nhiệm:**

- `CallbackHandler` cung cấp dữ liệu cho module; **không** tự tạo `Subject` đã xác thực.
- `LoginModule` xác minh credential, đưa trạng thái vào phase commit.
- `LoginContext` quản lý các module theo policy và trả success/failure chung.
- `Subject` là nơi chứa identity/credentials sau khi quá trình được xác nhận.

### 10.1 Vệ sinh PasswordCallback

- Dùng `char[]` thay vì giữ password dưới dạng `String` cố định khi API cho phép.
- Gọi `PasswordCallback.clearPassword()` và dọn các buffer mà ứng dụng thực sự sở hữu; nhận biết các bản sao có thể tồn tại trong heap.
- Không lưu callback object vào static fields, không cache password trong sharedState giữa request.
- Nếu xác thực dựa trên password storage, dùng **password hashing phù hợp** như Argon2id/PBKDF2 theo yêu cầu hệ thống; **không so sánh plaintext hardcode** như demo.
- Không để messages/exception tiết lộ user tồn tại, password đúng/sai hay secret. Có retry throttling và audit tại tầng auth service.

## 11. sharedState và options: cùng là Map nhưng mục đích khác

Khi `LoginContext` khởi tạo module:

```java
void initialize(
        Subject subject,
        CallbackHandler callbackHandler,
        Map<String, ?> sharedState,
        Map<String, ?> options)
```

**`sharedState`** là **Map chung** giữa các module trong cùng login context/stack; có thể dùng để chia sẻ một số thông tin cần thiết theo hợp đồng của các module. **`options`** là **cấu hình tĩnh riêng** của mỗi `AppConfigurationEntry`.

| Thuộc tính | sharedState | options |
| --- | --- | --- |
| Nguồn | LoginContext cung cấp để các module cùng tham chiếu | `Configuration` gắn từng module entry |
| Mục đích | Chia sẻ state/credential tạm giữa modules khi thật sự cần | Realm, endpoint, mode, debug flags, timeout hoặc policy được module định nghĩa |
| Biến đổi trong login | Có thể do module ghi/đọc; cần hợp đồng và cleanup | Thông thường đọc cấu hình, không dùng như vùng state chung |
| Rủi ro | Credential bị leak sang module khác, state còn sót sau abort/logout | Hardcoded password/token hoặc option không được module hiểu |
| API | `Map<String, ?> sharedState` | `Map<String, ?> options` |

**Tên options không phải tính năng JAAS chung**. Ví dụ `useFirstPass`, `tryFirstPass`, `storePass`, `clearPass` xuất hiện ở các module/provider khác nhau, có thể dùng state/password giữa các modules theo quy ước riêng. Phải kiểm tra **tài liệu của chính LoginModule** trước khi dùng; không tin rằng đặt `useFirstPass="true"` trong mọi module đều hoạt động.

Khi chia sẻ state, định nghĩa namespace cho key, tránh va chạm, xóa secret sau khi xong và không mở rộng phạm vi tin cậy tùy tiện: một module có quyền đọc sharedState có thể nhìn thấy thông tin của module khác. **Không coi JAAS sharedState như một key vault bảo mật**.

## 12. Thay module mà không sửa ứng dụng: khả năng và giới hạn

Sức mạnh JAAS nằm ở hợp đồng:

```java
// Caller chỉ biết application name.
LoginContext lc = new LoginContext("ServiceLogin", callbackHandler);
lc.login();
// ...
lc.logout();
```

Cấu hình có thể đổi từ:

```text
ServiceLogin {
    com.example.auth.DatabasePasswordModule required;
};
```

sang:

```text
ServiceLogin {
    com.example.auth.KerberosAuthModule required;
};
```

hoặc:

```text
ServiceLogin {
    com.example.auth.PasswordModule required;
    com.example.auth.TotpModule required;
};
```

Các class **`com.example.auth.*` chỉ là ví dụ tên plugin**, không thuộc JDK. Sau khi có implementation đúng và được triển khai trên classpath/modulepath, application caller có thể giữ nguyên. Tuy nhiên, đây là **khả năng thay bằng cấu hình**, không phải lời hứa mọi plugin có semantics tương đương hoặc có thể **hot swap giữa request đang login**.

### 12.1 Những điều phải ổn định khi thay plugin

- **Cấu trúc Subject/Principal:** ứng dụng downstream kỳ vọng loại Principal nào? Nếu đổi từ `UserPrincipal` sang `KerberosPrincipal`, code authorization có cần adapter không?
- **Mức độ bảo đảm danh tính:** password, Kerberos ticket, certificate hoặc MFA có trust assumptions và assurance khác nhau; đổi plugin có thể thay threat model.
- **Nguồn credential/callback:** plugin mới yêu cầu callback khác (password, token, smart card PIN), application handler phải hỗ trợ.
- **Lỗi và timeout:** LDAP/network failure có semantics khác sai password; phải fail closed và không leak tài khoản.
- **LoginModule options:** `debug`, `realm`, `issuer`, `useFirstPass` là provider-specific.
- **Lifecycle state:** module mới phải tuân thủ login/commit/abort/logout, rollback và không rò session.
- **Hiệu năng/concurrency:** authenticate đến service ngoài có timeout, circuit breakers, pool hoặc per-request sessions thích hợp.
- **Authorization mapping:** Principal đã xác thực không tự cấp quyền; phải mapping danh tính/roles từ nguồn đáng tin cậy.
- **Test/release:** không đưa module mới vào production chỉ bằng sửa JAAS config chưa có regression tests về flags và negative cases.

### 12.2 Java modules và class loading

Một LoginModule được nêu bằng **tên class fully qualified** trong Configuration. Runtime phải **load được class**, nó phải public hoặc truy cập được theo cơ chế của provider, triển khai đúng `LoginModule` và có public no-arg constructor. Khi Java Module System (JPMS) được sử dụng, còn cần packaging/access/exports/opens phù hợp theo cơ chế provider. Không nhầm **JAAS LoginModule** với **`module-info.java`** của JPMS: từ “module” ở đây chỉ **plugin xác thực**, không nhất thiết là Java Platform Module.

**Báo lỗi “module class not found”** cần kiểm tra JAR trên classpath/modulepath, tên class, quyền truy cập và provider; không phải lỗi password.

## 13. Luồng lỗi và fail-closed

| Lỗi/hiện tượng | Xuất hiện ở đâu | Ý nghĩa và xử lý |
| --- | --- | --- |
| `LoginException` khi tạo `LoginContext` | Tên ứng dụng không có entry và `other` không hợp lệ, config/class vấn đề tùy implementation | Kiểm tra `name`, file config, installed Configuration và class name |
| `FailedLoginException` | `LoginModule.login()` | Credential bị từ chối; hiển thị thông báo chung, không lộ user/password |
| `UnsupportedCallbackException` | `CallbackHandler.handle` | Handler không hỗ trợ callback type module yêu cầu; chỉnh bridge/UI, không bỏ qua |
| `IOException` khi handler lấy dữ liệu | Callback/input credential | Lỗi I/O; chuyển thành `LoginException` có cause an toàn |
| Exception khi `commit` | Subject read-only, quyền/provider, lỗi thêm Principal/credential | Fail closed, rollback/abort, không để lại identity nửa vời |
| Không gọi module sau trong stack | `REQUISITE` fail hoặc `SUFFICIENT` pass hợp lệ | Có thể là **đúng control flow**, không phải module “bị mất” |
| Module trả `true` nhưng `LoginContext.login()` thất bại | Có REQUIRED/REQUISITE khác thất bại hoặc phase commit lỗi | Kiểm tra cả stack, không quy kết riêng module |
| `logout()` thất bại | Module không dọn được token/session/Subject | Ghi lại và xử lý lifecycle an toàn, tránh dùng session như còn hợp lệ |
| App login thành công nhưng Principal rỗng | Module có thể không gắn Principal hoặc commit logic sai | Kiểm tra module contract, không tự coi success là quyền |
| Cấu hình file thay đổi nhưng kết quả không đổi | Context/provider dùng snapshot, cache hoặc config tường minh | Xác minh config source, `refresh`, context mới và strategy rollout |

**Fail closed:** khi thiếu module, không tìm được config, callback bị lỗi, identity provider không phản hồi hoặc password hashing backend unavailable, không tự tạo một `AllowAllLoginModule` để dịch vụ chạy được. Nếu app cần degraded mode, phải có threat model và policy tường minh **không giảm yêu cầu xác thực ngoài ý muốn**.

### 13.1 Cách ghi log an toàn

Có thể log (với policy bảo vệ): mã tình huống, service/realm, module class, login result, duration, error reason tổng quát, trace ID. **Không log** password/OTP/private credentials, toàn bộ `sharedState`, callback payload, raw token hoặc thông tin có thể trở thành oracle tài khoản. Tính năng `debug` của module cần được xem tài liệu provider trước khi bật.

### 13.2 Retry, lockout và chống brute force

JAAS quy định SPI và vòng đời, nhưng **không triển khai sẵn** rate-limit toàn ứng dụng, lockout, account recovery hay password policy. Cần thực hiện ở identity service/gateway/backend theo threat model:

- Giới hạn lần thử theo user và các tín hiệu phù hợp, chống enumeration;
- Dùng password hashing có salt/cost phù hợp, tránh plaintext hoặc fast SHA-256 đơn thuần;
- Xác thực credential qua TLS hoặc kênh được bảo vệ;
- Quản lý MFA, thiết bị tin cậy, recovery và revoke sessions;
- Audit các sự kiện cần thiết nhưng loại secret khỏi logs.

## 14. Authentication không đồng nghĩa Authorization

`LoginContext.login()` xác nhận **người hoặc service này đã vượt qua cơ chế xác thực được cấu hình**. Nó không tự cho phép đọc database hay chuyển tiền.

```text
Authentication:
    credentials + LoginModules -> Subject/Principals

Authorization:
    authenticated identity + resource/action + policy
        -> ALLOW or DENY
```

Một `Subject` có `AppPrincipal("student")` không chứng minh student được gọi admin API. Hệ thống cần authorization riêng, ví dụ RBAC/ABAC hoặc rule engine/identity policy phù hợp. Các khái niệm authorization cổ điển của JAAS từng liên quan `Subject.doAs`, `AccessControlContext` và SecurityManager; **Security Manager đã bị deprecated for removal trong JDK 17** và không nên chọn mô hình `java.security.Policy`/SecurityManager cũ làm nền tảng bảo vệ mới. Hành vi các API liên quan thay đổi theo bản JDK, vì vậy kiểm tra docs của runtime nếu gặp code legacy.

**Tư duy đúng trong ứng dụng hiện đại:** JAAS có thể xác thực và sinh Principal; sau đó framework/security layer độc lập đánh giá quyền truy cập theo token/identity đã được xác thực, không giả định principal name tự cấp quyền.

## 15. Kịch bản kiểm thử bắt buộc khi dùng LoginModule stack

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| Password hợp lệ; module REQUIRED thành công | `LoginContext.login()` thành công, `Subject` có Principal đúng |
| Password sai | `LoginException`, không có Principal mới được commit |
| Một REQUIRED fail, SUFFICIENT sau thành công | **Overall fail**; lỗi required không bị che |
| Một REQUISITE fail | **Dừng** module phía sau, fail và cleanup |
| SUFFICIENT thành công trước các module phía sau và không có required lỗi trước | Có thể **kết thúc sớm**, test không bỏ qua bắt buộc ngoài ý muốn |
| OPTIONAL fail nhưng REQUIRED pass | Overall pass nếu mọi bắt buộc khác đạt |
| Tất cả OPTIONAL fail | Overall fail |
| `commit` thất bại giữa chừng | Rollback đúng, không để credential/Principal sót |
| `abort` sau một module đã login thành công | Dọn pending state và secret, Subject không bị cập nhật sai |
| `logout` | Remove đúng Principal của module; không xóa Principal của module khác |
| `CallbackHandler` thiếu callback type | Lỗi rõ, không bypass |
| Configuration sai app name hoặc fallback `other` | Kết quả theo policy mong muốn, không tự chuyển sang auth yếu |
| Config options không hợp lệ | Fail closed hoặc ghi lỗi cấu hình, không ngầm chấp nhận |
| Nhiều người dùng đăng nhập đồng thời | Không rò `sharedState`/credential giữa contexts, không dùng static state |
| Thay module/password provider | Kiểm thử contract Subject, flags, timeout, error và authorization |
| Subject read-only | Module không thể thêm Principal; phải thất bại an toàn và dọn state |

Các chương trình ở mục 7–9 là **unit/behavior demos**. Một dự án production cần thêm integration tests với identity provider thật, test mạng lỗi, load/concurrency, secret rotation, negative cases, kiểm thử phân quyền và audit.

## 16. Câu hỏi tự luyện có lời giải

**Câu 1.** Ứng dụng gọi `new LoginContext("Portal", handler)`. Class LoginModule nào được chọn?  
**Đáp:** Do **installed `Configuration`** trả cho entry `"Portal"` quyết định. Nếu không có, theo contract JAAS còn có thể tra entry `"other"`; không được đoán từ tên class trong ứng dụng.

**Câu 2.** `LoginContext` có tự kiểm tra username/password không?  
**Đáp:** Không. Nó điều phối các **LoginModule**; module thực hiện kiểm chứng credential theo công nghệ và policy của nó.

**Câu 3.** `login()` của PasswordModule trả true, nhưng OTP module REQUIRED thất bại. Có nên thêm `UserPrincipal` vào Subject không?  
**Đáp:** Không. **Overall login thất bại**, `abort` dọn state; chỉ `commit` sau overall success mới gắn Principal phù hợp.

**Câu 4.** `REQUIRED` thất bại rồi `SUFFICIENT` thành công, kết quả?  
**Đáp:** **Thất bại**. SUFFICIENT không bỏ qua REQUIRED thất bại trước đó.

**Câu 5.** `REQUISITE` thất bại, module kế tiếp có được gọi không?  
**Đáp:** Không trong phase login stack; fail sớm. Module lifecycle cleanup/abort vẫn cần được thực hiện đúng.

**Câu 6.** `SUFFICIENT` thành công đầu stack, phía sau có REQUIRED. Có thể module sau không chạy không?  
**Đáp:** Có. Nếu không có required/requisite thất bại phía trước, SUFFICIENT có thể kết thúc sớm. Đó là lý do **thứ tự và flag là security-critical**.

**Câu 7.** Có một `AuditModule OPTIONAL` trả true, còn `PasswordModule OPTIONAL` fail. Có thể login pass không?  
**Đáp:** Có thể theo quy tắc stack không có REQUIRED/REQUISITE nếu một OPTIONAL thành công. Đó có thể là **lỗ hổng policy nghiêm trọng**; phải thiết kế flag và semantics module đúng.

**Câu 8.** `sharedState` và `options` khác nhau thế nào?  
**Đáp:** `sharedState` là Map được **chia sẻ** giữa modules trong cùng context; `options` là cấu hình **riêng của từng AppConfigurationEntry**. Cả hai đều không phải secret vault.

**Câu 9.** Sau login, Subject có `AppPrincipal("student")`. Có đủ quyền admin?  
**Đáp:** Không. **Authentication** không phải **Authorization**; quyền cần xác minh theo policy đáng tin riêng.

**Câu 10.** Muốn thay module xác thực password bằng Kerberos, có thể chỉ đổi config?  
**Đáp:** Về kiến trúc **có thể**, nếu plugin Kerberos được triển khai và caller/callback/Subject/authorization contract phù hợp. Không phải cứ đổi tên class là tự có Kerberos, hay bảo đảm bảo mật tương đương.

**Câu 11.** Gọi `Configuration.setConfiguration(...)` cho một test trong JVM chạy nhiều app có tác động gì?  
**Đáp:** Có thể thay **installed global configuration** và ảnh hưởng những caller khác. Thường nên truyền Configuration riêng vào constructor bốn tham số.

**Câu 12.** Mật khẩu từ PasswordCallback đã được so sánh và login thành công. Có nên giữ nó trong publicCredentials?  
**Đáp:** Không. Dọn credential tạm; nếu cần session credential thì dùng đối tượng được bảo vệ với lifecycle/quyền truy cập rõ.

**Câu 13.** `LoginContext.login()` thành công thì `logout()` có tự revoke JWT do dịch vụ ngoài cấp không?  
**Đáp:** Không tự động. LoginModule/provider phải hiện thực cleanup/revocation hoặc application cần cơ chế lifecycle riêng.

**Câu 14.** JAAS `LoginModule` và Java `module-info.java` có phải cùng một khái niệm không?  
**Đáp:** Không. JAAS LoginModule là **plugin xác thực** theo SPI; JPMS module là **đơn vị đóng gói và encapsulation của Java Platform Module System**.

## 17. Checklist thiết kế LoginModule thay thế được

1. **Định nghĩa authentication contract**: application name, loại identity, Principal classes, callback types, assurance level và metadata cho authorization.
2. **Viết LoginModule có no-arg constructor** và tuân thủ đủ `initialize/login/commit/abort/logout`.
3. **Chỉ commit sau overall success**; login giữ pending state riêng; abort/logout dọn đúng state/Principals do module quản lý.
4. **Thiết kế Configuration có thứ tự và flags an toàn**: REQUIRED/REQUISITE/SUFFICIENT/OPTIONAL, không để module phụ trợ thay thế proof of authentication.
5. **Tránh secrets trong options, Source, logs**; dùng backend secret management, password hashing thích hợp, TLS và rate limiting.
6. **Cẩn thận với fallback `other`**, global Configuration và phiên bản/hot reload; ưu tiên config riêng cho ứng dụng khi cần isolation.
7. **Kiểm soát sharedState**: phân quyền/namespace/cleanup, không chuyển secret cho module không tin cậy.
8. **Phân biệt Subject identity và quyền**: bảo đảm authorization policy độc lập, kiểm tra role/tenant/resource/action ở mỗi điểm cần thiết.
9. **Kiểm thử đúng JDK/provider/packaging**: class loading, classpath/modulepath, callback, flags, phase rollback và concurrent requests.
10. **Bảo đảm failure-safe**: network/LDAP/Kerberos lỗi không bị biến thành success; exception sanitization, audit, lockout.
11. **Không dùng SecurityManager legacy làm mô hình bảo vệ mới**; đọc tài liệu JDK runtime khi duy trì legacy JAAS authorization.
12. **Có kế hoạch thay module**: test plugin mới, mapping Principal, dry-run/canary, rollback, rotation credential và giám sát lỗi.

## 18. Tài liệu chính thức

- [Java SE 17 — `LoginContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): constructor, configuration fallback, `login`/`logout` và `getSubject`.
- [Java SE 17 — `Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): cú pháp module stack, control flags, `getAppConfigurationEntry`, installed configuration và `refresh`.
- [Java SE 17 — `AppConfigurationEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): module class name, cờ và options.
- [Java SE 17 — `LoginModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): hợp đồng SPI của năm phương thức.
- [Java SE 17 — `Subject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html) và [`Principal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html): identity, principals và credentials.
- [Java SE 17 — `CallbackHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html), [`NameCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/NameCallback.html), [`PasswordCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): cơ chế nhận thông tin từ nguồn credential.
- [Oracle JDK 17 — JAAS LoginModule Developer’s Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): cấu trúc một module, hai phase, callback, cleanup, testing.
- [Java SE 17 — `ConfigFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/login/ConfigFile.html): implementation cấu hình JAAS dựa trên file.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): lưu ý về các mẫu JAAS authorization dựa vào SecurityManager ở JDK cũ.

**Ghi nhớ:** `LoginContext` là **bộ điều phối**; `Configuration` là **danh sách plugin + thứ tự + chính sách cờ**; `LoginModule` là **cơ chế xác thực thay thế được**; `Subject` mang danh tính được commit khi login chung thành công. Nhờ sự tách biệt này, Java có thể hỗ trợ nhiều công nghệ xác thực mà caller không cần ràng buộc trực tiếp vào công nghệ đó — nhưng **cấu hình flags, callback, xử lý credential, rollback và authorization** vẫn là các yêu cầu bảo mật cốt lõi.
# 17.4 CallbackHandler tách thu thập thông tin đăng nhập khỏi cơ chế xác thực

Trong Java Authentication and Authorization Service (**JAAS**), người lập trình thường muốn xác thực một người dùng nhưng **không muốn mô-đun xác thực phụ thuộc trực tiếp vào giao diện nhập liệu**. Một ứng dụng desktop có ô mật khẩu, một chương trình dòng lệnh có `Console`, một web service nhận request đã qua HTTPS, và một service có secrets từ vault có cách thu thập thông tin rất khác nhau. Nếu mô-đun xác thực tự gọi `System.in`, tự hiển thị dialog hoặc đọc HTTP request, logic kiểm credentials sẽ bị buộc cứng vào môi trường và khó kiểm thử/thay đổi.

**`javax.security.auth.callback.CallbackHandler` là ranh giới tách việc *cung cấp thông tin theo yêu cầu* khỏi việc *kiểm chứng thông tin và quyết định đăng nhập*.** `LoginModule` mô tả nó cần dữ liệu nào bằng các `Callback` như `NameCallback`, `PasswordCallback`; `CallbackHandler` của ứng dụng điền dữ liệu vào các callback đó; còn mô-đun xác thực kiểm chứng với nguồn tin cậy rồi báo thành công/thất bại cho `LoginContext`. Sau khi JAAS hoàn tất bước `commit()`, kết quả danh tính được thể hiện dưới dạng `Subject` và `Principal`.

Điểm mấu chốt:

> **Handler thu thập hoặc cung cấp credentials; LoginModule kiểm chứng credentials. Handler không tự biến dữ liệu đầu vào thành danh tính đáng tin.**

Bài học giải thích hợp đồng API, luồng đăng nhập, cách quản lý mật khẩu kiểu `char[]`, các tình huống callback không hỗ trợ, quan hệ với `login/commit/abort/logout`, trường hợp interactive và headless, và một chương trình **Java 17+** biên dịch/chạy độc lập. Ví dụ sử dụng dữ liệu giả **chỉ cho lab**, không phải hướng dẫn hard-code mật khẩu sản xuất.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Mô tả vai trò của `LoginContext`, `Configuration`, `LoginModule`, `CallbackHandler`, `Callback`, `Subject` và `Principal` trong JAAS.
2. Giải thích vì sao `NameCallback` chứa tên đăng nhập và `PasswordCallback` chứa credential dạng `char[]` nhưng **không làm nhiệm vụ xác thực**.
3. Triển khai `CallbackHandler.handle(Callback[])` hỗ trợ đúng các loại callback đã được thỏa thuận và ném `UnsupportedCallbackException` nếu gặp loại không hỗ trợ.
4. Xử lý `IOException`, `UnsupportedCallbackException`, `FailedLoginException`, `LoginException` và trường hợp người dùng hủy nhập liệu mà không trả thông báo lộ thông tin đăng nhập.
5. Giải thích `PasswordCallback.setPassword()` / `getPassword()` / `clearPassword()`, sự tồn tại của **nhiều bản sao char[]** và yêu cầu xóa từng bản sao theo quyền sở hữu.
6. Xây luồng JAAS `initialize → login → commit` hoặc `abort` và `logout`, biết khi nào `Principal` được thêm/loại khỏi `Subject`.
7. Thay đổi nguồn credentials từ CLI sang UI, request hoặc secret manager mà không sửa logic xác thực cốt lõi.
8. Phân biệt demo so sánh password trong RAM với hệ production phải có password hashing/KDF, rate limiting, TLS, MFA/challenge, audit và authorization.
9. Viết test cho đăng nhập đúng/sai, handler thiếu, callback lạ, cleanup, logout và khả năng tái sử dụng cơ chế xác thực với nhiều handler.

## 2. Vị trí của CallbackHandler trong kiến trúc JAAS

Một sơ đồ luồng điển hình:

```text
                     ỨNG DỤNG
       (CLI / desktop / web / worker / secret provider)
                          |
                          | tạo CallbackHandler thích hợp
                          v
                 JAAS LoginContext
                          |
                          | load LoginModule từ Configuration
                          | initialize(Subject, handler, sharedState, options)
                          v
                     LoginModule
                          |
                          | "Tôi cần tên đăng nhập và mật khẩu"
                          v
              Callback[] {NameCallback,
                          PasswordCallback}
                          |
                          | handler.handle(callbacks)
                          v
                   CallbackHandler
                          |
               thu thập / lấy dữ liệu đầu vào
                          |
                          | setName(...), setPassword(...)
                          v
                     LoginModule
                          |
                verify với nguồn tin cậy
                          |
          +---------------+----------------+
          |                                |
       thành công                        thất bại
          |                                |
         commit()                        abort()
          |                                |
          v                                v
    Subject có Principal             Không cấp danh tính
          |
       logout()
          |
    Dọn Principal/credentials theo chính sách
```

Luồng hoạt động ngược với cách lập trình UI trực tiếp: **mô-đun xác thực chủ động yêu cầu thông tin thông qua callback object, còn ứng dụng quyết định làm thế nào để lấy thông tin đó**. Nhờ vậy cùng một `LoginModule` có thể sử dụng nhiều `CallbackHandler` khác nhau.

### Ranh giới trách nhiệm

| Thành phần | Nhiệm vụ | Không nên làm |
| --- | --- | --- |
| `LoginContext` | Điều phối các LoginModule theo JAAS Configuration; thực hiện `login()` và `logout()` | Không tự hiển thị form hay xác minh password hash |
| `Configuration` | Liệt kê LoginModule, control flags, options cho ứng dụng login | Không dùng làm kho mật khẩu plaintext |
| `LoginModule` | Yêu cầu callbacks, xác minh credentials, xác định kết quả, đóng góp Principal/credentials vào Subject | Không gọi trực tiếp Swing/console/HTTP nếu muốn dùng lại |
| `CallbackHandler` | Điền dữ liệu cho callback types được hỗ trợ; giao tiếp UI/secret source của ứng dụng | Không tự cấp Principal “đã xác thực” chỉ vì được nhập tên |
| `NameCallback` | Mang prompt/default name và nhận tên bằng `setName` | Không thực hiện lookup tài khoản đáng tin |
| `PasswordCallback` | Mang prompt/echo setting và nhận mật khẩu kiểu `char[]` | Không kiểm password hash hay tự bảo vệ credential ở nguồn bên ngoài |
| `Subject` | Chứa tập Principal và public/private credentials đã được mô-đun thêm theo lifecycle | Không mặc định mọi Principal do bất kỳ code thêm đều đã được xác thực |
| `Principal` | Đại diện cho một danh tính/name theo loại cụ thể | Không đại diện cho mật khẩu; không bao hàm mọi quyền |

**Nguồn dữ liệu đầu vào chưa đáng tin:** Nếu một HTTP client gửi username và password, CallbackHandler có thể copy chúng vào callbacks; nhưng dữ liệu chỉ thành kết quả authentication sau khi `LoginModule` kiểm chứng dựa trên nguồn **server-side** có quyền và `LoginContext` hoàn tất theo control flags.

## 3. Interface CallbackHandler và hợp đồng gọi

Java 17 định nghĩa giao diện trung tâm:

```java
public interface CallbackHandler {
    void handle(Callback[] callbacks)
            throws IOException, UnsupportedCallbackException;
}
```

Đây là chữ ký API, không phải file Java độc lập. Mỗi phần tử trong `Callback[]` mô tả một nhu cầu dữ liệu hoặc tương tác. Một handler thường duyệt từng phần tử và xử lý theo kiểu:

```java
// Minh họa trong một method của CallbackHandler, có username/secret hợp lệ.
for (Callback callback : callbacks) {
    if (callback instanceof NameCallback name) {
        name.setName(username);
    } else if (callback instanceof PasswordCallback password) {
        password.setPassword(secret);
    } else {
        throw new UnsupportedCallbackException(callback);
    }
}
```

**Handler không return một object credentials riêng.** Nó cập nhật các `Callback` được truyền vào. `LoginModule` lấy dữ liệu từ `NameCallback.getName()` và `PasswordCallback.getPassword()` sau khi `handle` trả về. Đây là cách tách **nguồn của dữ liệu** khỏi **cơ chế kiểm chứng**.

### Vì sao `Callback[]` là một mảng?

LoginModule có thể cần nhiều thông tin trong một lần xử lý:

- Tên đăng nhập (NameCallback).
- Mật khẩu hoặc một bí mật nhạy cảm (PasswordCallback).
- Chọn một realm hoặc phương án xác thực (ChoiceCallback).
- Nhập thêm thông tin ít nhạy cảm (TextInputCallback).
- Hiển thị cảnh báo/hướng dẫn (TextOutputCallback).
- Xác nhận tiếp tục/hủy bỏ (ConfirmationCallback).
- Các callback chuyên biệt hoặc tùy biến theo provider.

Gọi handler với nhiều callback giúp UI có thể **gom thành một form duy nhất**. Tuy nhiên mỗi `CallbackHandler` phải công khai tập callback types nó thực sự xử lý. Việc nhận một callback lạ và âm thầm bỏ qua có thể khiến LoginModule tưởng đã nhận dữ liệu đầy đủ trong khi thực tế chưa có.

### Không làm gì khi callback không hỗ trợ?

Hợp đồng chuẩn cho callback không hỗ trợ là ném `UnsupportedCallbackException`, có thể kèm callback gây lỗi. LoginModule có thể bắt lỗi rồi chuyển thành một `LoginException` phù hợp. **Đừng** coi callback không hiểu là “đăng nhập thành công” hoặc lặng lẽ trả null cho phần tử quan trọng.

Nếu handler không thể lấy dữ liệu vì I/O, người dùng đóng màn hình, stream bị lỗi hoặc secret manager không khả dụng, nó có thể ném `IOException` hoặc cơ chế báo lỗi phù hợp với contract; mô-đun xác thực nên **fail closed**, không fallback sang tài khoản mặc định.

## 4. NameCallback: tên định danh không phải bằng chứng xác thực

`NameCallback` thường chứa prompt cho tên đăng nhập và có thể có default name. Các API:

```java
NameCallback callback = new NameCallback("User: ");
callback.setName("alice");
String submittedName = callback.getName();
```

Đây là ví dụ biểu diễn dữ liệu, chưa có phép xác thực. Tên `"alice"` do client cung cấp **không đủ** để kết luận caller là Alice.

Lưu ý:

- `getPrompt()` dành cho người dùng hoặc hệ thống cung cấp credentials; không để prompt điều khiển việc truy cập nguồn dữ liệu không tin cậy.
- `getDefaultName()` là gợi ý UI nếu constructor có default; không phải danh tính được chứng minh.
- Username là `String`, thường không được xem là password secret, nhưng có thể là PII; vẫn cần log/retention policy.
- Normalize/canonicalize tên đăng nhập theo chính sách danh tính (Unicode, case, realm, tenant) **ở phía verifier**, không tự trim/lowercase mọi username tùy tiện.
- Nếu credential store hỗ trợ nhiều tenant, không để handler chỉ đặt một tên rồi vô tình lookup sang tenant khác mà không xác thực tenant scope.
- Không gán `Subject.getPrincipals().add(new UserPrincipal(name))` từ UI handler trước khi credential được kiểm chứng.

## 5. PasswordCallback: truyền mật khẩu bằng char[] và giới hạn thực tế

`PasswordCallback` có constructor `PasswordCallback(String prompt, boolean echoOn)`. Cờ `echoOn` là chỉ dẫn giao diện về việc có hiển thị ký tự người dùng nhập hay không; nó **không phải cơ chế mã hóa** và không ép mọi GUI/terminal phải tuân tuyệt đối nếu handler bỏ qua. Với mật khẩu, thông thường dùng `false`.

```java
PasswordCallback callback = new PasswordCallback("Password: ", false);
char[] secret = {'p', 'a', 's', 's'};
try {
    callback.setPassword(secret);
    char[] provided = callback.getPassword();
    try {
        // Chỉ giao cho verifier hợp lệ; không log, không chuyển thành String.
    } finally {
        if (provided != null) Arrays.fill(provided, '\0');
    }
} finally {
    callback.clearPassword();
    Arrays.fill(secret, '\0');
}
```

Đoạn trên là mã minh họa, cần import `java.util.Arrays` và `javax.security.auth.callback.PasswordCallback`. Đây là **secret giả** trong bài học, không phải password mẫu dùng sản xuất.

### Sao chép và xóa mật khẩu: phải nắm rõ ownership

Với implementation JDK thông dụng:

1. `PasswordCallback.setPassword(char[])` lưu một **bản sao** của mảng truyền vào, không chiếm ownership mảng gốc.
2. `PasswordCallback.getPassword()` trả một **bản sao** để bên nhận xử lý; caller phải tự xóa mảng này.
3. `PasswordCallback.clearPassword()` xóa/ghi đè nội dung mật khẩu đang được giữ trong callback.
4. Việc gọi `clearPassword()` **không** xóa mảng ban đầu trong UI/handler hoặc những bản sao mà `getPassword()` đã trả.
5. Trong JDK 17 được thử nghiệm, sau `clearPassword()`, `getPassword()` có thể trả một mảng đã bị ghi đè bằng ký tự trắng thay vì `null`. Do đó **không kiểm “đã xóa” bằng biểu thức `getPassword() == null`**.
6. Java không hứa xóa mọi bản sao do GC/runtime/native/UI/encoding có thể tạo; sử dụng `char[]` là phương án **giảm thời gian tồn tại** của plaintext trong bộ nhớ, không phải cam kết memory erasure tuyệt đối.
7. Không nên chuyển mật khẩu sang `String` để tiện log/compare vì `String` bất biến và khó xóa có chủ đích. Hệ thống nhập liệu, thư viện HTTP hoặc framework có thể đã tạo String; cần hiểu nguồn và giảm bản sao ở những ranh giới bạn kiểm soát được.

### Trình tự cleanup đúng

```text
UI/source secret char[]   --clone--> Handler-owned char[]
                                  |
                                  | PasswordCallback.setPassword(...)
                                  v
                            Callback internal char[]
                                  |
                                  | getPassword()
                                  v
                            LoginModule local char[]
                                  |
                                  v
                             verifier

Sau xử lý:
  - LoginModule Arrays.fill(localCopy, '\0')
  - LoginModule PasswordCallback.clearPassword()
  - Handler.close() Arrays.fill(ownedCredential, '\0')
  - Application Arrays.fill(sourceSecret, '\0')
```

Không log nội dung của `PasswordCallback` hoặc dùng `Arrays.toString(password)`. Không đặt password trong exception message, `Subject.Principal`, JAAS config file, JVM system property hoặc field lưu dài hạn của LoginModule.

## 6. Sự khác nhau giữa handler và verifier

Xem hai cách viết.

**Thiết kế kết dính (không khuyến nghị):**

```java
// Chỉ minh họa anti-pattern, không phải chương trình độc lập.
boolean login() {
    String name = console.readLine("User: ");
    char[] password = console.readPassword("Password: ");
    return callCredentialDatabase(name, password);
}
```

Mô-đun xác thực ở đây phụ thuộc vào `console`. Khi ứng dụng chạy trong servlet không có console, một bài test không có terminal, hoặc worker dùng secret manager, bạn phải sửa code xác thực.

**Thiết kế tách biệt với JAAS:**

```text
LoginModule:
    NameCallback + PasswordCallback
        -> handler.handle(...)
        -> verifier.verify(name, password)
        -> commit Principal nếu authentication thành công

CLI CallbackHandler:
    console.readLine/readPassword

GUI CallbackHandler:
    input từ form hiển thị theo UI framework

Web CallbackHandler:
    dữ liệu từ request đã qua HTTPS và session/auth flow đúng

Service CallbackHandler:
    lấy secret từ vault hoặc identity bootstrap theo chính sách
```

Verifier được xây từ **credential store đáng tin**; không lấy expected password từ cùng request đầu vào của attacker. CallbackHandler có thể được thay mà không phải thay policy kiểm chứng. Đây là lợi ích về **separation of concerns**, testability, portability và quản trị trust boundary.

## 7. LoginContext và Configuration điều phối ra sao?

`LoginContext` điều phối một hoặc nhiều `LoginModule` dựa trên `Configuration`. Một entry thường chứa:

- Tên class của LoginModule.
- Control flag: `REQUIRED`, `REQUISITE`, `SUFFICIENT` hoặc `OPTIONAL`.
- Options của module, chẳng hạn tên realm hoặc identifier của credential service, nhưng **không phải mật khẩu plaintext**.

Ví dụ pseudo-config:

```text
sample {
    com.example.security.DirectoryLoginModule required
      realm="members";
};
```

Đây là **cú pháp ý tưởng** cho JAAS config; class trên chỉ là tên minh họa, không phải class có sẵn trong JDK. Chương trình hoàn chỉnh ở mục 10 dùng `Configuration` tạo bằng Java để không cần file ngoài.

Ví dụ khởi tạo:

```java
// Minh họa, giả sử subject/handler/config đều có nguồn tin cậy.
LoginContext loginContext =
        new LoginContext("sample", subject, handler, config);

loginContext.login();             // điều phối LoginModule.login + commit/abort
Subject authenticated = loginContext.getSubject();
loginContext.logout();            // gọi logout các modules đã tham gia
```

### Control flags ảnh hưởng kết quả tổng thể

| Flag | Ý nghĩa tóm tắt | Rủi ro khi hiểu sai |
| --- | --- | --- |
| `REQUIRED` | Module phải thành công; dù fail, các module khác trong chuỗi có thể vẫn được thử trước khi báo failure | Tưởng login thành công do module sau pass dù module required fail |
| `REQUISITE` | Module phải thành công; failure thường làm toàn login kết thúc ngay | Bỏ qua việc fail closed cho bước bắt buộc |
| `SUFFICIENT` | Thành công có thể cho phép kết thúc sớm nếu chưa có required/requisite failure cần xét | Dùng sai để bypass bước xác thực/kiểm chính sách bắt buộc |
| `OPTIONAL` | Đóng góp vào policy tổng thể theo quy tắc JAAS; không mặc nhiên bắt buộc | Tưởng optional module đảm bảo MFA hoặc policy bắt buộc |

Kết quả **của một LoginModule** không đồng nghĩa kết quả **toàn bộ LoginContext** khi có nhiều module. Đừng tự lắp nhiều bước password/OTP bằng các control flags mà không hiểu xử lý lỗi, thứ tự, short-circuit và `commit/abort`. Một mô hình MFA đúng cần protocol và binding giữa các bước, không chỉ có hai ô nhập.

### CallbackHandler có thể được truyền vào nhiều modules

`LoginContext` có thể sử dụng cùng handler cho các LoginModule trong cấu hình, nhưng callback types mà mỗi module yêu cầu có thể khác. Nếu module mới yêu cầu `TextInputCallback` mà handler chỉ hỗ trợ Name/Password, `handle` có thể ném `UnsupportedCallbackException`. Đây là tín hiệu tích hợp phải cập nhật hoặc cấu hình lại handler **có chủ đích**, không phải lý do âm thầm bỏ qua bước mới.

## 8. LoginModule lifecycle: initialize, login, commit, abort, logout

Đối với `javax.security.auth.spi.LoginModule`, những phương thức cốt lõi:

```java
void initialize(Subject subject, CallbackHandler handler,
        Map<String, ?> sharedState, Map<String, ?> options);
boolean login() throws LoginException;
boolean commit() throws LoginException;
boolean abort() throws LoginException;
boolean logout() throws LoginException;
```

Ý nghĩa:

1. `initialize` nhận `Subject`, handler, sharedState và options. Không nên lập tức công bố Principal chưa xác thực.
2. `login` yêu cầu callbacks, kiểm credentials và ghi trạng thái tạm của module. Thành công chưa nhất thiết đồng nghĩa nên thêm Principal ngay; LoginContext còn xử lý kết quả nhiều modules.
3. `commit` được gọi khi JAAS quyết định đăng nhập tổng thể thành công, mô-đun có thể thêm `Principal` và credentials thích hợp vào `Subject`.
4. `abort` được gọi khi đăng nhập tổng thể thất bại; mô-đun phải bỏ state tạm và rollback những thay đổi đã commit nếu áp dụng.
5. `logout` dọn identity/credentials mà module **chính nó** đã đóng góp, và kết thúc session theo hợp đồng.

**Chỉ commit sau xác thực.** Một nguyên nhân phổ biến của lỗi an ninh là handler được nhập username rồi thêm ngay Principal vào Subject, trong khi password check sau đó fail. Tách callback collection khỏi authentication và commit giúp tránh trạng thái danh tính nửa vời.

### Subject và Principal không phải nơi lưu mật khẩu

`Subject` có tập `Principal`, public credentials và private credentials. Mô-đun chỉ thêm những gì cần theo policy và có nghĩa rõ ràng. Đừng đưa mật khẩu plaintext vào Principal name hoặc permanent credential set chỉ vì dễ dùng lại. Với session/token, phải có lifecycle, quyền đọc/xóa, expiration, refresh và logout phù hợp.

Trong Java, `Subject` có thể bị đánh dấu read-only, khi đó thay đổi các tập dữ liệu có thể thất bại. LoginModule nên xử lý việc commit vào Subject read-only như lỗi cấu hình/policy thay vì âm thầm coi commit thành công.

## 9. Kiến trúc mẫu cho một ứng dụng thực

Giả sử hệ thống có ba nguồn:

```text
+---------------------+   +---------------------+
| Desktop UI Handler  |   | Web Request Handler |
+---------------------+   +---------------------+
          |                           |
          +-------------+-------------+
                        |
                        v
                NameCallback
                PasswordCallback
                        |
                        v
               DirectoryLoginModule
                        |
                        v
                CredentialVerifier
          (trusted credential database/service)
                        |
         +--------------+-------------+
         |                            |
      authenticated                 rejected
         |                            |
        Subject                     LoginException
        Principal                   no Principal
```

Bạn có thể thay `DirectoryLoginModule` bằng module khác nếu contract callbacks/verification khác, hoặc thay UI handler mà giữ nguyên module. Tuy nhiên, việc “dùng chung” không được làm nhòe trust boundary: web request là dữ liệu attacker-controlled, còn stored password hash/secret verifier là dữ liệu được bảo vệ riêng. Handler không nên chọn arbitrary credential database endpoint do user gửi.

### Các interface/phân tầng dễ kiểm thử

```text
CredentialsProvider (thuộc tầng application/UI)
    -> cung cấp username + char[] theo scope request

CallbackHandler (adapter JAAS)
    -> dịch yêu cầu callback thành dữ liệu

LoginModule (orchestration/JAAS integration)
    -> chọn verifier, biến kết quả thành JAAS state

CredentialVerifier (server-side policy)
    -> password hashing/KDF, account state, lockout/rate limits, MFA

Subject/Principal (authenticated identity)
    -> authorization layer kiểm quyền nghiệp vụ
```

Không bắt buộc triển khai tất cả thành class riêng trong mọi ứng dụng nhỏ; đây là cách nghĩ giúp thay đổi UI và credential backend mà không kéo thay đổi mật mã vào presenter.

## 10. Java 17+ — chương trình độc lập kiểm chứng CallbackHandler

Ví dụ dùng hoàn toàn **JDK 17**, không cần database, JAAS config file hay thư viện ngoài. Nó gồm:

- `UserPrincipal` kiểu Java record chứa **tên**, không chứa password.
- `LabLoginModule` thực hiện yêu cầu `NameCallback`/`PasswordCallback` và một kiểm tra **giả lập**.
- `FixedHandler` nạp thông tin vào callbacks, giữ bản sao `char[]` và triển khai `AutoCloseable` để xóa bản sao.
- `Configuration` tạo trực tiếp trong code với một module `REQUIRED`.
- `LoginContext` cho trường hợp đúng và sai; kiểm số Principal sau commit/logout/failure.
- Test `UnsupportedCallbackException` cho loại callback không được hỗ trợ.
- Test `PasswordCallback.clearPassword()` loại bỏ giá trị cũ mà **không dựa vào `getPassword() == null`**.

**Cảnh báo về credential giả:** chương trình có một password demo gắn trong source **chỉ để test sự tách biệt callback và login**. `Arrays.equals` và password hard-code **không** là thiết kế kiểm mật khẩu production. Một hệ thống thật phải gọi credential verifier đáng tin với password hashing/KDF, salt, rate limiting và account/MFA policy. Không đưa demo này vào Internet-facing authentication service.

Lưu file **`JaasCallbackDemo.java`**:

```java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.TextInputCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasCallbackDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override public String getName() { return name; }
    }

    public static final class LabLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal pending;
        private boolean authenticated;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) throw new LoginException("No callback handler");
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            char[] submitted = null;
            char[] expected = {'d','e','m','o','-','p','a','s','s'};
            try {
                handler.handle(new Callback[] {name, password});
                submitted = password.getPassword();
                if (!"alice".equals(name.getName())
                        || submitted == null
                        || !Arrays.equals(submitted, expected)) {
                    throw new FailedLoginException("Invalid credentials");
                }
                pending = new UserPrincipal(name.getName());
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException(
                        "Credential collection failed");
                failure.initCause(e);
                throw failure;
            } finally {
                if (submitted != null) Arrays.fill(submitted, '\0');
                Arrays.fill(expected, '\0');
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() throws LoginException {
            if (!authenticated) return false;
            if (subject.isReadOnly()) throw new LoginException("Read-only subject");
            subject.getPrincipals().add(pending);
            committed = true;
            return true;
        }

        private void clearState() {
            authenticated = false;
            committed = false;
            pending = null;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            clearState();
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(pending);
            }
            clearState();
            return true;
        }
    }

    public static final class FixedHandler
            implements CallbackHandler, AutoCloseable {
        private final String username;
        private final char[] credential;
        private boolean closed;

        FixedHandler(String username, char[] credential) {
            this.username = username;
            this.credential = credential.clone();
        }

        @Override
        public void handle(Callback[] callbacks)
                throws IOException, UnsupportedCallbackException {
            if (closed) throw new IOException("Handler is closed");
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName(username);
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(credential);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        }

        @Override
        public void close() {
            Arrays.fill(credential, '\0');
            closed = true;
        }
    }

    private static Configuration labConfiguration() {
        return new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"sample".equals(name)) return null;
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                        LabLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };
    }

    public static void main(String[] args) throws Exception {
        Configuration config = labConfiguration();
        char[] good = {'d','e','m','o','-','p','a','s','s'};
        try (FixedHandler handler = new FixedHandler("alice", good)) {
            LoginContext context = new LoginContext(
                    "sample", new Subject(), handler, config);
            context.login();
            System.out.println("Valid login: true");
            System.out.println("Authenticated principal: " +
                    context.getSubject().getPrincipals(UserPrincipal.class)
                            .iterator().next().getName());
            System.out.println("Principal count after login: " +
                    context.getSubject().getPrincipals().size());
            context.logout();
            System.out.println("Principal count after logout: " +
                    context.getSubject().getPrincipals().size());
        } finally {
            Arrays.fill(good, '\0');
        }

        char[] wrong = {'n','o','t','-','r','i','g','h','t'};
        try (FixedHandler handler = new FixedHandler("alice", wrong)) {
            LoginContext context = new LoginContext(
                    "sample", new Subject(), handler, config);
            try {
                context.login();
                System.out.println("Wrong password rejected: false");
            } catch (LoginException expected) {
                System.out.println("Wrong password rejected: true");
                System.out.println("Principal count after failure: " +
                        context.getSubject().getPrincipals().size());
            }
        } finally {
            Arrays.fill(wrong, '\0');
        }

        char[] placeholder = {'x'};
        try (FixedHandler handler = new FixedHandler("alice", placeholder)) {
            try {
                handler.handle(new Callback[] {new TextInputCallback("OTP: ")});
                System.out.println("Unsupported callback rejected: false");
            } catch (UnsupportedCallbackException expected) {
                System.out.println("Unsupported callback rejected: true");
            }
        } finally {
            Arrays.fill(placeholder, '\0');
        }

        PasswordCallback callback = new PasswordCallback("Password: ", false);
        char[] temporary = {'x'};
        callback.setPassword(temporary);
        char[] independentCopy = callback.getPassword();
        callback.clearPassword();
        char[] afterClear = callback.getPassword();
        boolean originalRemoved = afterClear == null
                || !Arrays.equals(independentCopy, afterClear);
        Arrays.fill(temporary, '\0');
        Arrays.fill(independentCopy, '\0');
        if (afterClear != null) Arrays.fill(afterClear, '\0');
        System.out.println("Original callback password removed: " +
                originalRemoved);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 JaasCallbackDemo.java
java JaasCallbackDemo
```

**Stdout chính xác đã kiểm chứng với JDK 17 trong môi trường thử nghiệm:**

```text
Valid login: true
Authenticated principal: alice
Principal count after login: 1
Principal count after logout: 0
Wrong password rejected: true
Principal count after failure: 0
Unsupported callback rejected: true
Original callback password removed: true
```

### Vì sao chương trình hoạt động như vậy?

1. `FixedHandler` chỉ biết `username`/`credential` đầu vào và hai loại callback mà nó hỗ trợ. Không có logic “mật khẩu hợp lệ hay không” trong handler.
2. `LabLoginModule.login()` tự tạo `NameCallback` và `PasswordCallback`, yêu cầu handler điền dữ liệu, rồi mới so sánh với mock verifier. Đây là điểm đổi sang credential service thật trong ứng dụng production.
3. `NameCallback.setName` và `PasswordCallback.setPassword` đưa dữ liệu vào callback objects. Sau `handle`, module lấy `getName()`/`getPassword()`. Dù có password, `Subject` chưa có Principal cho đến `commit`.
4. `char[] submitted` do `getPassword` trả về được ghi đè trong `finally`. Mật khẩu callback được xóa bằng `clearPassword`, mật khẩu mà handler copy được xóa ở `close`, còn password nguồn do `main` giữ được xóa bằng `Arrays.fill`.
5. `expected` là mật khẩu giả được dựng cục bộ trong module và xóa trước khi trả. **Đây không phải mật khẩu lưu trong một secure credential store**, và dùng `Arrays.equals` không phải password-verification design thích hợp trên server sản xuất.
6. `commit` thêm `UserPrincipal("alice")` sau khi đã có kết quả xác thực. `logout` gỡ principal do module tạo. Nếu có nhiều module hoặc nhiều principal trùng nhau, code production cần quản lý ownership/phạm vi xóa cẩn thận hơn.
7. Trường hợp password sai ném `FailedLoginException` rồi LoginContext thất bại; `Subject` demo vẫn có **0 Principal**. Đây là kiểm thử không cấp quyền sau failed login.
8. `TextInputCallback` không được handler demo hỗ trợ; `handle` ném `UnsupportedCallbackException` đúng hợp đồng. Một handler thực muốn hỗ trợ OTP/challenge cần chính sách riêng, không thể chỉ thêm một nhánh trả text rồi coi đó là MFA.
9. `PasswordCallback.clearPassword` không được kiểm bằng `getPassword() == null`. Test tạo một bản sao trước khi clear và xác nhận giá trị cũ không còn trong callback sau clear; đồng thời xóa mọi bản sao được code nắm giữ.
10. `Configuration` tạo trực tiếp bằng Java chỉ để ví dụ dễ chạy. Trong hệ thống triển khai, configuration provider, module discovery, options và classpath có thể do application server/container quản lý.

### Giới hạn của ví dụ

Ví dụ không mở console hoặc kết nối mạng, không nạp user directory, không gọi password hashing service, không kiểm rate limit/MFA, không có concurrent sessions, không có thực thi authorization ngoài Subject, và không chứng minh credential lifecycle trong một web framework. Nó **kiểm chứng cơ chế callback và JAAS login lifecycle**, không phải xác thực người dùng Internet theo chuẩn production.

## 11. CallbackHandler cho CLI: Console và điều kiện không có terminal

Với CLI interactive, một handler có thể dùng `System.console()` để hỏi username/password. Ví dụ **mã minh họa**, không độc lập:

```java
Console console = System.console();
if (console == null) {
    throw new IOException("Interactive console unavailable");
}
String username = console.readLine("User: ");
char[] password = console.readPassword("Password: ");
try {
    nameCallback.setName(username);
    passwordCallback.setPassword(password);
} finally {
    if (password != null) Arrays.fill(password, '\0');
}
```

Cần import `java.io.Console`, `java.io.IOException`, `java.util.Arrays` và giả sử `nameCallback`/`passwordCallback` đúng kiểu đã được cung cấp. Đây là một đoạn **trong handler**, không phải logic verifier.

Các lưu ý:

- `System.console()` có thể trả `null` khi chạy trong IDE, CI, Docker, daemon, redirected stdin hoặc môi trường không có console tương tác. Không fallback sang `Scanner.nextLine()` đọc mật khẩu hiển thị trần một cách vô tình.
- `Console.readPassword` hỗ trợ đọc mật khẩu tránh echo trên terminal phù hợp, nhưng vẫn cần bảo vệ môi trường, quyền truy cập process và lịch sử shell.
- Có người dùng hủy hoặc EOF; không truyền `null` vào verifier rồi coi là password rỗng hợp lệ.
- Một CLI handler có thể được gọi trên thread khác tùy framework; nếu UI chỉ chạy một thread, xử lý luồng đồng bộ/khóa input an toàn.
- Không lưu password trong `String`, environment variable hoặc command-line arguments khi có thể tránh; các nguồn này có thể lộ qua process inspection, logs và core dumps.

## 12. CallbackHandler cho web và headless services

Trong ứng dụng web, thông tin đăng nhập có thể đến từ request đã qua HTTPS, browser challenge, reverse proxy hoặc một identity provider. **CallbackHandler không tự kiểm TLS**, không bảo đảm request chính chủ và không thay CSRF/anti-automation/rate limiting.

### Request-scoped handler

Một handler nhận username/char[] cho **một login attempt** nên có lifetime hẹp:

```text
HTTPS request -> input validation -> request-scoped CallbackHandler
      -> JAAS LoginContext.login()
      -> LoginModule -> credential verifier
      -> JAAS Subject -> session mapping
      -> request cleanup / wipe char[] / close handler
```

Không để singleton handler giữ `username`/`password` từ nhiều request; có thể gây **credential mix-up** giữa users. Nên tạo handler/`LoginContext` mới theo request/session context và không dùng ThreadLocal không kiểm soát với async execution hoặc thread pools.

### Headless service với vault

Một service có thể cần đăng nhập tới một hệ thống khác bằng secret đã được cấp từ vault/KMS/secret manager. Handler có thể xin password/token từ provider theo identity của workload, điền callback rồi xóa bản sao. LoginModule vẫn chịu trách nhiệm đưa dữ liệu đó tới verifier của hệ đích và bảo vệ trạng thái xác thực.

Không coi việc secret manager trả credential là chứng minh caller hiện tại đã được authorization. Dùng IAM, workload identity, scoping theo environment/tenant và audit retrieval. Nếu secret retrieval thất bại, handler báo lỗi rõ ràng ở kênh nội bộ và login fail closed, không dùng mật khẩu rỗng hoặc default backup credential.

### Sự khác biệt khi dùng modern authentication

JAAS `CallbackHandler` thường xuất hiện trong JDK security providers, application servers, Kerberos/SASL hoặc cơ chế login module tùy biến. Với OIDC/OAuth2/SAML, phần xác thực có thể do protocol/framework chuyên trách xử lý; đừng tự lấy access token và ép nó thành “password” cho `PasswordCallback` nếu không có adapter/protocol design rõ ràng.

Tách thu thập credentials khỏi verifier là một **nguyên tắc kiến trúc**, không phải yêu cầu mọi ứng dụng hiện đại phải dùng JAAS làm gateway cho tất cả identity protocols.

## 13. Callback chuyên biệt: OTP, lựa chọn phương thức và MFA

Ngoài Name/Password, JAAS cung cấp những callback khác. Chúng có **semantics khác nhau** và không nên diễn giải mọi giá trị nhập thành mật khẩu.

| Callback | Dữ liệu/vai trò | Ví dụ sử dụng |
| --- | --- | --- |
| `NameCallback` | Username hoặc identifier | Chọn danh tính người dùng |
| `PasswordCallback` | Secret dạng `char[]`, tùy policy yêu cầu echo off | Mật khẩu/challenge response bí mật |
| `TextInputCallback` | Input text thường | Nhập tên realm/thuộc tính; **cẩn thận nếu chứa OTP/secret** |
| `TextOutputCallback` | Trình bày thông tin/thông báo | Thông báo policy, hướng dẫn |
| `ChoiceCallback` | Chọn một/nhiều phương án trong danh sách | Chọn realm/auth method |
| `ConfirmationCallback` | Xác nhận/cancel | Người dùng đồng ý tiếp tục |
| `LanguageCallback` | Locale muốn dùng | UI nội địa hóa |
| Callback đặc thù provider | Dữ liệu không được chuẩn hóa cho mọi module | Hardware token, challenge, key handle |

Với OTP hoặc WebAuthn/FIDO2, không chỉ “thêm một ô nhập” là có MFA. Cần xác minh challenge nonce, thời hạn, binding với attempt/user/session, replay resistance, rate limiting và trust model của authenticator. Nếu thông tin OTP là secret nhạy cảm, dùng loại dữ liệu/handler phù hợp và cleanup theo threat model; `TextInputCallback` dùng `String` có thể làm tăng secret lifetime.

### Khi UI không hỗ trợ callback mới

Khi nâng cấp LoginModule để cần một callback bổ sung, handler cũ nên trả `UnsupportedCallbackException`. Hệ thống cần phát hiện mismatch trong integration tests và rollout handler/client tương ứng; không “mặc định OTP pass” hoặc bỏ qua optional-looking prompt. Nếu một module bắt buộc callback để xác thực mà không thể thu thập dữ liệu, **login phải thất bại**.

## 14. Ngoại lệ và xử lý lỗi an toàn

`CallbackHandler.handle` khai báo hai checked exceptions:

- `IOException`: nguồn nhập liệu I/O hoặc hoạt động thu thập thông tin không thể hoàn thành, chẳng hạn console/vault/network adapter lỗi.
- `UnsupportedCallbackException`: handler không hỗ trợ loại callback được yêu cầu.

Trong `LoginModule.login()`, thường chuyển ngoại lệ phù hợp thành `LoginException` (giữ cause nội bộ) rồi để LoginContext điều phối failure/abort. Credentials sai theo chính sách xác thực có thể ném `FailedLoginException`.

### Phân biệt ba loại thất bại

| Tình huống | Bản chất | Hành vi đúng |
| --- | --- | --- |
| Username/password sai | Authentication failed | Từ chối và áp rate limiting/lockout policy |
| Handler không hỗ trợ callback | Integration/configuration failure | Từ chối, ghi dấu lỗi nội bộ, sửa handler/module |
| Không đọc được secret source | Availability/I/O failure | Từ chối theo policy, không fallback thiếu kiểm soát |

Đối với client không tin cậy, tránh phản hồi chi tiết “username tồn tại nhưng password sai” hoặc “vault key cho tenant X tồn tại”. Thông báo bên ngoài nên nhất quán và không tiết lộ người dùng/secret inventory; log nội bộ có loại lỗi, correlation ID và metadata đã làm sạch.

### Cleanup trong mọi nhánh

Trong demo, `finally` luôn dọn `submitted` và `PasswordCallback`, kể cả khi `handle` ném `IOException` hoặc `UnsupportedCallbackException`. Khi login thất bại, `abort` phải dọn trạng thái module; handler vẫn phải `close` và xóa buffer nó sở hữu.

**Đừng chỉ xóa password khi login thành công.** Credential thất bại vẫn nhạy cảm, thậm chí có thể là mật khẩu đúng của người dùng nhưng nhập nhầm username.

### Tránh bắt ngoại lệ quá rộng để tuyên bố thành công

Không làm kiểu:

```java
// Anti-pattern, không phải chương trình độc lập.
try {
    loginContext.login();
} catch (Exception ignored) {
    session.setAuthenticated(true); // NGUY HIỂM.
}
```

Ngoại lệ bất kỳ trong login phải khiến kết quả auth thất bại theo policy. Nếu application cần thông tin kỹ thuật để khắc phục, ghi log server-side an toàn, không phơi exception chain có secret.

## 15. Thread safety, vòng đời và khả năng tái nhập

Không nên mặc định một `CallbackHandler` là thread-safe. Interface chỉ quy định `handle(Callback[])`; nó **không** cam kết:

- Handler không bị gọi đồng thời từ nhiều login attempts.
- Một callback chỉ được điền một lần.
- UI luôn có interactive thread.
- Handler có quyền tiếp tục đọc secret sau khi login attempt kết thúc.
- `Callback[]` chỉ chứa NameCallback và PasswordCallback mãi mãi.
- `LoginModule` có thể reuse an toàn giữa request khác nhau.

Một handler có field `username`/`credential` thường nên **request-scoped hoặc attempt-scoped**. Nếu cần global credential provider, nên truyền vào một service thread-safe có trust boundary rõ, nhưng giữ secret data ngắn hạn trong từng instance.

### Nguy cơ race conditions

Giả sử singleton handler có `currentUsername` và `currentPassword` dùng chung. Request A đặt Alice rồi bị scheduler tạm dừng; request B ghi Bob vào cùng fields; sau đó handler của A chạy và có thể trả username Bob/password Alice hoặc ngược lại. Đây không chỉ là lỗi logic mà có thể tạo sự cố xác thực/định danh nghiêm trọng. Giải pháp: **không giữ request credentials trong state toàn cục**, bảo đảm snapshot theo attempt và quản lý cleanup đúng scope.

### Không truy cập UI thread sai cách

Desktop UI frameworks như Swing/JavaFX có quy tắc thread riêng. Một JAAS LoginModule có thể gọi handler từ worker thread; handler muốn hiển thị dialog phải điều phối tới UI thread hợp lệ mà không deadlock/đóng băng giao diện. Không dùng `System.console()` trong server process chỉ vì interface yêu cầu password.

## 16. Password verifier sản xuất: đừng đặt niềm tin vào UI

Handler có thể lấy secret “đúng định dạng” nhưng **điều đó không xác thực credential**. LoginModule/verifier phải dựa vào nguồn được bảo vệ và chính sách mật khẩu, thường:

1. Lấy tài khoản từ directory/database đã xác định theo tenant/realm và bảo vệ chống user enumeration.
2. Lấy salted password verifier/hash, không lưu plaintext.
3. Dùng password hashing/KDF có thông số thích hợp, ví dụ Argon2id, scrypt, bcrypt hoặc PBKDF2 theo tiêu chuẩn và khả năng thư viện/tổ chức. Không dùng SHA-256 đơn lẻ của password làm verifier production.
4. So sánh theo cơ chế phù hợp, tránh nhánh timing leak đáng kể; đánh giá rehash/migration khi chính sách thay đổi.
5. Có rate limiting, backoff/lockout có kiểm soát, giám sát brute force/credential stuffing và MFA khi cần.
6. Kiểm trạng thái tài khoản/credential expiry/revocation, chống replay/challenge reuse theo protocol.
7. Khi thành công, tạo Principal/session với phạm vi danh tính và quyền cụ thể; session và authorization do tầng ứng dụng quyết định.
8. Không giữ password sau khi hoàn tất; clear callback và các bản sao do app kiểm soát.
9. Không ghi password, hash/raw challenge response hoặc token vào logs/traces/exception messages.
10. Đánh giá nguồn credentials đã đi qua HTTPS/secure channel; browser/password manager/IdP flows cần CSRF/session controls phù hợp.

`Arrays.equals(submitted, expected)` trong Java demo chỉ là thao tác so hai mảng **giả** dễ đọc để chứng minh CallbackHandler không verify. Nó **không** thay thế password verifier KDF an toàn và không phải constant-time password protocol.

## 17. Test strategy: kiểm module và handler độc lập

Để tận dụng kiến trúc tách biệt, nên có **ba lớp kiểm thử**.

### 17.1 Test riêng Handler

Dùng callbacks mẫu, kiểm handler:

- Điền đúng `NameCallback`.
- Điền `PasswordCallback` với dữ liệu của đúng login attempt.
- Ném `UnsupportedCallbackException` nếu gặp callback ngoài support.
- Fail closed nếu nguồn credential không có hoặc handler đã đóng.
- Không trả password của request khác khi có concurrent attempts.
- Không làm lộ dữ liệu trong log hoặc exception.
- Xóa buffer nó sở hữu sau `close`, kể cả khi `handle` thất bại.

### 17.2 Test riêng LoginModule

Cấp fake handler cho module và fake credential verifier (hoặc lab verifier). Kiểm:

- Login đúng -> `login()` thành công; `commit()` mới thêm Principal.
- Login sai -> `FailedLoginException`/`LoginException`, không có authenticated Principal.
- `PasswordCallback.getPassword()` trả null/empty -> authentication failure theo policy.
- Handler ném `IOException`/`UnsupportedCallbackException` -> LoginException và cleanup.
- `abort()` dọn state tạm khi module khác trong cùng LoginContext thất bại.
- `logout()` gỡ đúng Principal do module tạo và không xóa identity của module khác.
- Subject read-only -> commit thất bại có kiểm soát.
- Credential verifier bị outage -> fail closed; không fallback sang password mặc định.
- Password cleanup không chỉ chạy trong success branch.

### 17.3 Integration test LoginContext

Chạy JAAS Configuration thực:

| Tình huống | Kỳ vọng |
| --- | --- |
| Handler đúng username/secret, module REQUIRED | `LoginContext.login()` thành công; Subject có Principal |
| Handler sai password | LoginException; không cấp Principal |
| Handler trả username khác tenant | Server-side verifier từ chối hoặc xác định đúng namespace, không trộn session |
| Handler không hỗ trợ callback cần thiết | Login thất bại, log tích hợp an toàn |
| Handler bị đóng trước khi login | I/O/integration failure, không xác thực |
| Login thành công rồi logout | Principal/credentials do module sở hữu được dọn |
| Multiple modules REQUIRED | Một required fail -> kết quả tổng thể fail |
| MFA module bắt buộc | Không có callback/response hợp lệ -> fail |
| Nhiều request đồng thời | Không rò credentials giữa attempts |
| PasswordCallback clear | Giá trị cũ không còn trong callback-owned storage; caller-owned copies cũng được xóa |
| LoginModule verifier lỗi mạng | Không tạo Principal thành công giả |
| UI password hiển thị | Echo policy được handler/UI tuân, không log |
| Reusable UI | Cùng LoginModule dùng handler CLI và handler web hợp đồng giống nhau |

**Điều quan trọng:** test thành công không chỉ là “handler đã điền tên/password”; phải quan sát authentication result qua LoginContext/Subject. Ngược lại, một Subject chứa Principal do ứng dụng tự tạo không chứng minh LoginContext đã verify nếu dữ liệu được thêm ở sai chỗ.

## 18. Lỗi thường gặp và hướng sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `LoginModule` tự đọc `System.in`/UI trực tiếp | Không test/headless được, gắn chặt môi trường | Yêu cầu callbacks và truyền handler |
| CallbackHandler tự quyết định “password đúng” | Lẫn data collection với credential verification | Đưa xác minh vào LoginModule/verifier đáng tin |
| Tự thêm Principal trong handler | Có thể cấp danh tính trước xác thực | Chỉ commit Principal sau authentication |
| Không gọi `setSSLParameters`? | Không liên quan bài JAAS | Không pha lẫn network TLS configuration với JAAS callbacks |
| Handler bỏ qua callback lạ | Bước authentication mới có thể bị bypass/thiếu dữ liệu | Ném `UnsupportedCallbackException` |
| Chỉ xử lý NameCallback mà bỏ PasswordCallback | Login nhận null/empty secret hoặc lỗi không rõ | Handler hỗ trợ đúng contract hoặc fail |
| Chuyển char[] password thành String | Khó cleanup secret trong RAM | Giữ char[] khi API cho phép |
| Chỉ gọi `clearPassword` | Bản sao trong handler/module vẫn còn | Xóa mọi buffer theo ownership |
| Nghĩ `clearPassword` luôn cho `getPassword()==null` | Kiểm cleanup sai trong JDK17 | Kiểm contract overwrite, không đòi null |
| Dùng `Arrays.equals` làm password verifier production | Thiếu hash/KDF/mitigation và policy | Dùng trusted password verifier |
| Đặt password trong JAAS options | Rò secret qua config/log | Dùng secret manager/credential store |
| Dùng singleton handler chứa request credentials | Race/cross-user credential mix-up | Handler per attempt, no global secret state |
| Console null thì đọc secret bằng `Scanner` có echo | Lộ password trong console/log | Fail closed hoặc dùng input an toàn |
| Lộ lỗi “tài khoản X tồn tại” | User enumeration | Thông báo chung; log nội bộ đã làm sạch |
| `login()` fail vẫn gọi application authenticated | Bypass auth | Chỉ cấp session khi LoginContext.login thành công |
| Không triển khai `abort/logout` đúng | Principal/credential bị giữ sai lifecycle | Dọn state và chỉ gỡ identity mình đã thêm |
| Cho module tùy ý được handler request key/vault scope | SSRF/secret enumeration/tenant isolation lỗi | Allowlist trust realm/key lookup server-side |
| Coi JAAS login = authorization | Người dùng authenticated có thể làm quá quyền | RBAC/ABAC theo tenant/resource/action |
| Trộn handler đa mục đích không kiểm callback | Bỏ sót MFA/challenge và dễ misuse | Explicit supported callback types + integration tests |
| Reuse Subject mutable chung giữa request | Trộn principal/session | Isolation và Subject lifecycle per security context |

Trong hàng “`setSSLParameters`”, điểm nhấn là **không trộn logic các mô-đun an ninh khác nhau**: `SSLParameters` thuộc cấu hình JSSE/TLS, không phải API thu thập mật khẩu JAAS. Nếu cần TLS cho transport, cấu hình/kiểm tra ở tầng network, còn `CallbackHandler` phục vụ data handoff cho authentication module.

## 19. Checklist triển khai an toàn

Trước khi đưa adapter JAAS vào môi trường thật, hãy xác nhận:

1. **Thành phần nào yêu cầu callbacks?** LoginModule/provider phải có hợp đồng callback types, thứ tự/ý nghĩa rõ ràng và cơ chế failure.
2. **Ai tạo handler?** Ứng dụng tạo handler theo request/attempt và truyền vào LoginContext; handler không nên giữ secret global.
3. **Nguồn credential ở đâu?** UI, HTTPS request, vault hoặc token provider; scope, quyền và thời hạn dữ liệu rõ.
4. **Input validation ở đâu?** Giới hạn kích thước/encoding, normalization theo policy; không để prompt/username biến thành path/URL query tùy ý.
5. **Verifier có đáng tin?** Server-side credential store/password hash, policy độ mạnh, rate limits, lockout, MFA và monitoring.
6. **Password ownership ra sao?** Liệt kê mọi char[]/String/encoded copies ở nguồn, callback, module và provider; wipe phần kiểm soát được.
7. **Callback không được hỗ trợ xử lý thế nào?** Ném đúng exception và không cho login pass.
8. **Các LoginModule được cấu hình ra sao?** Control flags và required checks không tạo bypass.
9. **Principal được commit khi nào?** Chỉ sau successful authentication, không từ handler hoặc unauthenticated request.
10. **Abort/logout có idempotent và đúng ownership?** Không để lại Principal/credential khi login fail hoặc logout.
11. **Logging có an toàn?** Không in password, token, hash, credential store responses; có correlation ID, audit và giới hạn retention.
12. **Concurrent attempts có cách ly?** Không reuse mutable handler/Subject sai scope.
13. **Transport có an toàn?** HTTPS/TLS peer identity và session security áp dụng độc lập với JAAS.
14. **Test âm đã có?** Sai password, unknown user/tenant, unsupported callback, null handler, vault outage, cancellation và concurrency.
15. **UI hỗ trợ người dùng?** Echo off, accessibility/localization, cancel/timeout và thông báo lỗi không tiết lộ secret.
16. **Identity được cấp quyền đúng?** Sau JAAS authentication, ứng dụng vẫn kiểm authorization cho tenant/resource/action.
17. **Secrets có rotate/revoke?** Password reset, account disable, token/key rotation và login sessions phản ánh policy thực.
18. **Provider/JDK có đặc tính riêng?** Kiểm trên đúng Java 17+ build, app server/container và cách JAAS Configuration được nạp.
19. **Observability đo đúng?** Đo login result/failure reasons đã làm sạch, latency và callback integration errors, không thu password content.
20. **Không tự chế protocol MFA:** Nếu cần OIDC/WebAuthn/OTP, dùng implementation chuẩn được review và binding đầy đủ, không chỉ đọc một String làm OTP.

## 20. Bài tập thực hành

### Bài 1 — Thay nguồn credentials mà giữ nguyên verifier

Giữ `LabLoginModule` từ bài lab, viết một `CallbackHandler` khác nhận username/password từ một cấu trúc request object giả thay vì `FixedHandler`. Không sửa code xác minh của LoginModule. Kiểm login đúng/sai và các bản sao char[] được xóa theo đúng ownership.

### Bài 2 — Callback không hỗ trợ

Gọi handler với `NameCallback` + `TextInputCallback`. Yêu cầu xử lý rõ ràng `UnsupportedCallbackException`, không im lặng bỏ qua. Nêu cách một hệ thống có thêm OTP nên rollout handler mới và policy MFA mà không tạo bypass.

### Bài 3 — Console có thể không tồn tại

Triển khai handler tương tác bằng `System.console()` và `readPassword()` trong CLI lab. Chạy ở terminal và IDE/CI headless. Khi console trả null, handler phản ứng thế nào? Vì sao không tự động đọc mật khẩu bằng echo-on?

### Bài 4 — Kiểm password copies

Dùng `PasswordCallback` và nhiều `char[]` độc lập. Thử sửa mảng nguồn sau `setPassword` rồi xem callback có bị thay không; thử sửa mảng trả về từ `getPassword` rồi xem bản lưu trong callback; gọi `clearPassword` và giải thích vì sao phải wipe cả bản sao tự quản. Không dùng password thật trong test.

### Bài 5 — Lifecycle JAAS

Thêm một `LoginModule` thứ hai với control flag `REQUIRED` mà trả failure. Kiểm `abort` của module đầu tiên được gọi và Subject không chứa Principal được coi là authenticated. Thử logic `commit` và `logout` với nhiều Principal để bảo đảm mỗi module chỉ xóa thông tin do nó đóng góp.

### Bài 6 — Thiết kế CredentialVerifier sản xuất

Thay demo so sánh mảng bằng một fake interface `CredentialVerifier.verify(username, char[])`, sau đó phác thảo adapter thật dùng salted password hash/KDF, account state và rate limiting. Giải thích vì sao không nên truyền expected password qua CallbackHandler hay JAAS options và cách giảm user enumeration.

### Bài 7 — Cách ly multi-tenant/concurrency

Dựng hai login attempts Alice/tenant A và Bob/tenant B chạy song song. Chứng minh một singleton mutable handler có thể làm credential mix-up. Viết test dùng handler per-attempt và trusted tenant context để ngăn trộn danh tính.

### Bài 8 — Web application integration

Thiết kế luồng HTTPS request → input adapter → JAAS LoginContext → Subject → session principal → authorization cho API. Nêu cách dọn char[] sau request, xử lý LoginException an toàn, CSRF/session fixation/MFA khi cần và tại sao JAAS Subject không tự cấp quyền đọc dữ liệu nghiệp vụ.

### Bài 9 — CallbackHandler không đồng nghĩa authentication

Một attacker gửi `username="admin"` và một password bất kỳ; handler điền Name/Password callbacks hoàn hảo. Tại sao ứng dụng vẫn phải từ chối? Vạch rõ điểm cần verifier, điểm commit Principal và điểm kiểm authorization.

**Điều kiện đạt:** bạn có thể tạo một LoginModule **không phụ thuộc terminal, UI hoặc HTTP**, triển khai nhiều handlers cho những nguồn credentials khác nhau, xử lý callback types/exception đúng hợp đồng, bảo vệ dữ liệu nhạy cảm bằng cleanup theo ownership, và chỉ đưa Principal vào Subject sau khi JAAS xác thực thành công theo chính sách.

## 21. Tài liệu tham khảo

- [Java SE 17 — CallbackHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html): `handle(Callback[])`, `IOException` và `UnsupportedCallbackException`.
- [Java SE 17 — Callback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/Callback.html): marker interface cho yêu cầu tương tác.
- [Java SE 17 — NameCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/NameCallback.html): prompt và tên đăng nhập.
- [Java SE 17 — PasswordCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): `setPassword`, `getPassword`, `clearPassword`, echoOn.
- [Java SE 17 — UnsupportedCallbackException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/UnsupportedCallbackException.html): callback types không được hỗ trợ.
- [Java SE 17 — LoginContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): đăng nhập, đăng xuất và điều phối JAAS.
- [Java SE 17 — LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): lifecycle `initialize/login/commit/abort/logout`.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html) và [AppConfigurationEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): khai báo modules/control flags.
- [Java SE 17 — Subject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): Principal, credentials và danh tính JAAS.
- [Java SE 17 — Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html): đối tượng danh tính.
- [Java SE 17 — JAAS Authentication Tutorial](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication-tutorial.html): quan hệ LoginContext, LoginModule và CallbackHandler.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực ứng dụng, responses, logging, MFA và brute-force controls.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salted password hashing/KDF, rehash và bảo vệ verifier.

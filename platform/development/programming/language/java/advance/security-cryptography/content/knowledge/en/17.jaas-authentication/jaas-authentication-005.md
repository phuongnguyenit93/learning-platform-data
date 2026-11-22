# 17.5. Vòng đời initialize, login, commit, abort và logout của LoginModule

**JAAS** (Java Authentication and Authorization Service) cho phép ứng dụng Java thay đổi cơ chế xác thực mà không phải viết lại phần điều phối. Ứng dụng gọi `javax.security.auth.login.LoginContext`; một hoặc nhiều thành phần cung cấp xác thực triển khai `javax.security.auth.spi.LoginModule`.

Điểm mấu chốt của bài học: **JAAS xác thực theo hai pha**. Pha `login()` kiểm credential, lưu trạng thái thành công **tạm trong module**. Sau khi các module được đánh giá theo các control flags, `LoginContext` gọi **`commit()` nếu tổng thể thành công** hoặc **`abort()` nếu tổng thể thất bại**. `logout()` là một thao tác riêng khi ứng dụng muốn kết thúc phiên đã đăng nhập. `initialize()` truyền bối cảnh để module bắt đầu làm việc.

Bài này thuộc **17. Xác thực JAAS**, tập trung vào vòng đời đủ năm phương thức, các đường đi khi thành công/thất bại, trách nhiệm cập nhật và dọn `Subject`, cách phối hợp nhiều modules, cùng ví dụ Java 21 có thể biên dịch và chạy.

## Mục tiêu học tập

- Biết `LoginContext`, `LoginModule`, `Configuration`, `AppConfigurationEntry`, `CallbackHandler`, `Subject` và `Principal` đóng vai trò gì.
- Giải thích đúng `initialize → login → commit/abort` và `logout`, kể cả trường hợp một module thành công nhưng module khác làm tổng thể thất bại.
- Phân biệt `true`, `false` và `LoginException` từ `login/commit/abort/logout`; không dùng `false` để che giấu mật khẩu sai.
- Hiểu các control flags `REQUIRED`, `REQUISITE`, `SUFFICIENT` và `OPTIONAL`.
- Viết module chỉ thêm principal sau `commit`, chỉ xóa những gì module thật sự sở hữu khi `abort`/`logout`, và dọn password.
- Chạy ba tình huống trong Java 21: đăng nhập đúng, password sai, module REQUIRED phía sau từ chối; diễn giải trace và số principal.
- Thiết kế test xử lý partial failure, callback không hỗ trợ, Subject read-only, duplicate principal, retry/logout và bí mật.
- Phân biệt JAAS authentication với session web, MFA, password hashing, authorization nghiệp vụ và rollback database.

## 1. Kiến trúc JAAS trước khi nói về vòng đời

`LoginContext` là cổng của ứng dụng. Nó đọc `Configuration` theo tên ứng dụng, tạo các `LoginModule` và quyết định module nào phải thành công. Mỗi `LoginModule` tự xác thực theo cơ chế được cắm vào, không tự tuyên bố kết quả của toàn bộ hệ thống.

```text
Application
  |
  +--> new LoginContext("demo", Subject?, CallbackHandler, Configuration)
  |
  +--> LoginContext.login()
          |
          +--> LoginModule A: kiểm username/password
          +--> LoginModule B: kiểm điều kiện khác nếu cấu hình yêu cầu
          |
          +--> JAAS tổng hợp kết quả theo control flags
                   |
                   +--> SUCCESS: commit()
                   +--> FAILURE: abort()
  |
  +--> LoginContext.getSubject() khi thành công
  |
  +--> LoginContext.logout() khi kết thúc phiên
```

| Thành phần | Trách nhiệm |
| --- | --- |
| `LoginContext` | Quản lý luồng login, lựa chọn modules, điều phối commit/abort/logout và cung cấp Subject |
| `LoginModule` | Thực hiện một phương pháp xác thực và giữ private state của nó |
| `Configuration` | Xác định tên ứng dụng, danh sách module, control flags và options |
| `AppConfigurationEntry` | Cấu hình một LoginModule với class, flag và map options |
| `CallbackHandler` | Cung cấp callback để lấy input như `NameCallback` và `PasswordCallback` |
| `Subject` | Đối tượng chứa các principals, public/private credentials của subject đã được xác thực |
| `Principal` | Định danh, nhóm hoặc vai trò theo mô hình của ứng dụng; không phải quyền tuyệt đối |
| `sharedState` | Map chia sẻ cho các modules trong cùng quá trình; phải có quy ước và cleanup |
| `options` | Map cấu hình riêng của từng module; không phải kho password |

Một ứng dụng có thể gọi `LoginContext.login()` mà không biết bên dưới đang dùng Kerberos, password, smart card hay một module tùy biến. Mọi mô hình vẫn phải tuân theo **quy tắc state của JAAS**.

## 2. Hợp đồng interface: năm methods không thể tráo vai trò

Interface chuẩn `javax.security.auth.spi.LoginModule` (đã có trong JDK, **không viết lại**) có chữ ký:

```java
void initialize(Subject subject,
                CallbackHandler callbackHandler,
                Map<String, ?> sharedState,
                Map<String, ?> options);

boolean login() throws LoginException;
boolean commit() throws LoginException;
boolean abort() throws LoginException;
boolean logout() throws LoginException;
```

| Method | Pha | Điều nhận/đọc | Điều thực hiện |
| --- | --- | --- | --- |
| `initialize` | Chuẩn bị | Subject, handler, shared state, options | Lưu context/cấu hình, chưa xác thực |
| `login` | Pha 1 | Credential/identity từ callback hoặc provider | Xác thực và giữ trạng thái **tạm** |
| `commit` | Pha 2, khi tổng thể chấp nhận | Kết quả `login` của module | Thêm Principal/Credential vào Subject, đánh dấu commit |
| `abort` | Pha 2, khi tổng thể từ chối | State login/commit cần rollback | Dọn pending state và những gì module đã thêm nếu có |
| `logout` | Sau khi đăng nhập được chấp nhận | State đã commit | Dọn Principal/Credential thuộc module và đóng phiên liên quan |

**Không có `LoginContext.initialize()` công khai cho ứng dụng gọi để kích hoạt từng module.** Chính `LoginContext` khởi tạo và gọi `LoginModule.initialize(...)` khi module được xử lý. Tài liệu JAAS mô tả hai pha, nhưng thứ tự initialize của các module khác nhau có thể xen kẽ với login, không nhất thiết “initialize tất cả trước rồi mới login bất kỳ module nào”.

`LoginModule` cần public constructor không tham số để `LoginContext` khởi tạo qua reflection. Nếu đặt class lồng nhau, nó cần là `public static` và tên binary class phải được cấu hình đúng.

## 3. Pha 1: `initialize` và `login`

### 3.1 `initialize(...)` nhận context, không cấp quyền

```java
@Override
public void initialize(Subject subject, CallbackHandler handler,
                       Map<String, ?> sharedState,
                       Map<String, ?> options) {
    this.subject = subject;
    this.handler = handler;
}
```

Đây chỉ là **đoạn minh họa trong một class**, không phải chương trình chạy riêng. `initialize` trả `void`, không được thêm Principal hoặc public/private credential vào Subject như thể user đã được xác thực.

- `subject` là đối tượng sẽ được cập nhật về sau, thường ở `commit`.
- `handler` có thể là `null`. Nếu module cần input tương tác thì phải xử lý trường hợp này bằng lỗi có kiểm soát trong `login`.
- `sharedState` có thể chứa dữ liệu do module khác chia sẻ; nếu chia sẻ secret, phải quy định ai sở hữu, ai xóa và tránh rò rỉ giữa các lần đăng nhập.
- `options` lấy từ cấu hình của module như realm, debug flag, endpoint. Cần validate và không ghi log password/secret.

Không dùng field `static` làm nơi lưu `Subject` hoặc credentials của user: những phiên khác nhau có thể chạy đồng thời, gây rò rỉ danh tính.

### 3.2 `login()` kiểm credentials và lưu private state

```java
boolean login() throws LoginException;
```

Một thực hiện đúng thường sẽ gọi `CallbackHandler.handle(...)`, lấy username/password hoặc token, kiểm bằng cơ chế xác thực đã thiết kế, rồi đánh dấu `authenticated=true` và giữ `pendingPrincipal` sau khi thành công.

**Không thêm principal vào Subject trong `login()`.** Nếu module A đã thành công nhưng module B `REQUIRED` thất bại, tổng thể cần `abort`; việc đã thêm principal quá sớm làm Subject chứa danh tính chưa được chấp nhận.

Ba kết quả cần phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| `return true` | Module đã xác thực thành công. Đây **chưa** bảo đảm toàn bộ LoginContext thành công. |
| `return false` | Module chọn **được bỏ qua** hoặc không áp dụng trường hợp hiện tại. Không tự coi là lỗi mật khẩu. |
| `throw FailedLoginException` hoặc `LoginException` | Xác thực thực sự thất bại hoặc không thể hoàn tất; LoginContext xử lý theo flag của module. |

Nếu module đã nhận mật khẩu và xác định mật khẩu **không đúng**, đừng `return false` để lặng lẽ bỏ qua. Trong stack có `OPTIONAL`/`SUFFICIENT`, việc dùng sai return value có thể khiến một cách xác thực khác được chấp nhận khi chính sách thực tế đòi yếu tố vừa bị bỏ qua.

`LoginModule.login()` không nên tự làm retry/backoff nhiều lần hay ngủ chờ. Theo hướng dẫn JAAS, retry thuộc caller/application và chính sách bảo vệ login; module phải báo thành công hoặc thất bại một cách rõ ràng.

### 3.3 Xóa dữ liệu từ `PasswordCallback`

`PasswordCallback.getPassword()` trả `char[]`. Sau khi sử dụng, code nên xóa bản sao tự giữ (`Arrays.fill`), gọi `PasswordCallback.clearPassword()` trong `finally` và không đưa password vào log. Việc cleanup một mảng không xóa được mọi bản sao tiềm ẩn trong JVM/provider. Khi input ban đầu là `String` bất biến, đặc biệt với framework web, không thể hứa xóa toàn bộ bí mật khỏi heap.

Một module production không được so sánh password với literal nằm trong source. Cần hệ thống lưu verifier an toàn (Argon2id hoặc PBKDF2 với salt/work factor theo policy), chống brute-force/rate limit và xác thực đa yếu tố nếu cần.

## 4. Pha 2 thành công: `commit()`

```java
boolean commit() throws LoginException;
```

Khi `LoginContext` xác định **tổng thể đăng nhập** thành công theo control flags, pha commit được thực hiện trên những module liên quan. Một module có `login() == true` sẽ chuyển identity đã xác thực thành các `Principal` và/hoặc credentials trong `Subject`.

Mẫu tư duy:

```text
login() -> authenticated=true, pendingPrincipal=UserPrincipal("alice")
overall LoginContext login succeeds
commit() -> subject.getPrincipals().add(pendingPrincipal)
           -> ghi nhớ phần đã thực sự thêm
           -> xóa pending state/secret không còn cần
           -> return true
```

Nếu module không có xác thực thành công hoặc đã được bỏ qua, `commit()` thường dọn state rồi `return false`. Nếu commit **cần thiết nhưng thất bại**, ví dụ Subject read-only hoặc provider không tạo được credential, hãy `throw LoginException`; không báo `true` khi Subject ở trạng thái không phù hợp.

### 4.1 Sở hữu principal rất quan trọng

Ví dụ:

```java
boolean added = subject.getPrincipals().add(new UserPrincipal("alice"));
```

Nếu Subject đã có một Principal bằng giá trị, set có thể trả `false`. Module **không được xóa** principal đó khi logout, vì nó không phải thứ module vừa thêm. Theo dõi object thuộc module như `ownedPrincipal`, và chỉ remove khi thực sự sở hữu. Cách này đặc biệt quan trọng khi nhiều LoginModule cùng bổ sung identities/roles.

`commit` không phải một database transaction. Những side effects tới API, database, token store phải có ranh giới giao dịch hoặc compensating actions riêng; JAAS **không tự hoàn tác** một token đã phát hoặc một dòng dữ liệu đã ghi.

## 5. Pha 2 thất bại: `abort()`

```java
boolean abort() throws LoginException;
```

Khi **tổng thể** thất bại, `LoginContext` chuyển sang nhánh abort. Điều này xảy ra ngay cả khi **bản thân module A đã xác thực thành công** nhưng module `REQUIRED`/`REQUISITE` khác thất bại.

`abort()` phải:

1. Xóa pending identities, sensitive data và authentication state được tạo ở `login`.
2. Nếu có state đã được commit một phần trước khi phát hiện lỗi, chỉ xóa những Principal/Credential **do module đó thêm**.
3. Đóng resource/revoke tạm theo policy; không xóa contribution của module khác.
4. Reset trạng thái nội bộ, không dùng lại kết quả login cũ cho lần khác.
5. Trả `true` khi cleanup phần đã tham gia thành công, `false` khi module vốn được bỏ qua/chưa xác thực, hoặc ném `LoginException` nếu cleanup cần thiết thất bại.

Ngay cả module thất bại trong `login` cũng có thể nhận `abort()`. Bởi vậy hàm cleanup phải an toàn khi state gần như trống.

**Không nhầm abort với logout:** abort là kết thúc một **lần đăng nhập không được chấp nhận**; logout là kết thúc một **phiên đã thành công**.

## 6. `logout()`: dọn phần đã commit của chính module

```java
boolean logout() throws LoginException;
```

Khi ứng dụng gọi `LoginContext.logout()`, JAAS gọi logout trên modules theo cơ chế đã cấu hình. Module cần remove Principal và credential do chính nó thêm ở `commit`, destroy các secret do nó quản lý và reset state.

Điểm dễ sai:

- **Không** gọi `subject.getPrincipals().clear()` vì có thể xóa identity từ module khác.
- **Không** xóa principal chỉ dựa vào class/name nếu không biết module có thật sự thêm nó.
- Với `Subject.isReadOnly() == true`, thao tác thay đổi set principals bị cấm; xử lý theo hợp đồng (destroy credentials có thể có quy tắc riêng), ném `LoginException` nếu không thể cleanup yêu cầu.
- `logout()` không tự kết thúc HTTP session, xóa browser cookie hoặc revoke OAuth token nếu module/ứng dụng chưa triển khai riêng.
- Nên kiểm thử cleanup nhiều lần và theo chính sách state thực tế, tránh double-release và rò secret.

| Tình huống | Method cần tập trung | Trạng thái Subject |
| --- | --- | --- |
| Password đúng, toàn bộ modules đúng | `commit` | Có principals/credentials đã xác thực |
| Password sai | `abort` | Không được có principal mới |
| Module A đúng, module B REQUIRED fail | `abort` của A và B | Không được còn state của lần login thất bại |
| Phiên thành công sau đó người dùng đăng xuất | `logout` | Contributions do module sở hữu được loại bỏ |
| Subject read-only | `commit/abort/logout` có thể báo lỗi cleanup | Không tự lách chính sách immutability |

## 7. Control flags quyết định đường đi tổng thể

`AppConfigurationEntry.LoginModuleControlFlag` có bốn loại:

| Flag | Khi thành công | Khi thất bại |
| --- | --- | --- |
| `REQUIRED` | Bắt buộc thành công, rồi tiếp tục xét module khác | Tổng thể sẽ thất bại, thường vẫn tiếp tục xét các module còn lại trước khi báo lỗi |
| `REQUISITE` | Bắt buộc thành công, rồi tiếp tục | Dừng sớm khi thất bại; tổng thể thất bại |
| `SUFFICIENT` | Có thể kết thúc sớm và thành công nếu không có lỗi REQUIRED/REQUISITE trước đó | Thất bại riêng không bắt buộc làm tổng thể thất bại |
| `OPTIONAL` | Có thể góp phần vào thành công | Thất bại riêng không bắt buộc làm tổng thể thất bại; khi không có module bắt buộc, vẫn cần ít nhất một SUFFICIENT/OPTIONAL thành công |

Chẳng hạn:

```text
PasswordModule REQUIRED  → login true
DenyModule     REQUIRED  → login throws FailedLoginException
----------------------------------------------
overall failure → PasswordModule.abort(), DenyModule.abort()
```

Dù PasswordModule đã trả `true`, **không được commit Principal** do một REQUIRED khác thất bại. Đây là mục tiêu của cơ chế hai pha.

`SUFFICIENT` có thể short-circuit; do đó **đừng giả định tất cả modules sẽ chắc chắn nhận mọi callback**. Thứ tự modules và flags thay đổi được control flow. `false` từ `login` nghĩa là module muốn được bỏ qua, khác với exception khi credential thật sự sai. Cấu hình flag là một phần chính sách bảo mật, cần integration tests, không chỉ unit test từng module.

## 8. Chương trình Java 21 độc lập: ba nhánh lifecycle

Ví dụ có hai nested modules:

- `PasswordModule` xác thực username `alice` cùng password **lab-only** `lab-secret`. Nó không thêm Principal trong `login`; chỉ thêm trong `commit`. `cleanup` chỉ xóa Principal do chính module sở hữu.
- `DenyModule` ném `FailedLoginException` để mô phỏng một module `REQUIRED` thứ hai từ chối, qua đó kích hoạt `abort` của cả stack.

`Configuration` được tạo **trong chương trình**, không cần file `jaas.conf`. Password literal và phép so sánh `Arrays.equals` là **mã kiểm tra luồng JAAS**, không phải thuật toán kiểm password an toàn cho production. Không có callback UI hay database thật.

Tạo file **`JaasLifecycleDemo.java`**:

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
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasLifecycleDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override public String getName() { return name; }
    }

    public static final class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal pending;
        private UserPrincipal owned;
        private boolean authenticated;
        private boolean committed;

        @Override public void initialize(Subject subject, CallbackHandler handler,
                                         Map<String, ?> sharedState,
                                         Map<String, ?> options) {
            System.out.println("password initialize");
            this.subject = subject;
            this.handler = handler;
        }

        @Override public boolean login() throws LoginException {
            System.out.println("password login");
            authenticated = false;
            pending = null;
            if (handler == null) throw new LoginException("Handler required");
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            try {
                handler.handle(new Callback[]{name, password});
                char[] supplied = password.getPassword();
                char[] expected = "lab-secret".toCharArray();
                try {
                    if (!"alice".equals(name.getName()) ||
                        !Arrays.equals(supplied, expected)) {
                        throw new FailedLoginException("Invalid credentials");
                    }
                    pending = new UserPrincipal(name.getName());
                    authenticated = true;
                    return true;
                } finally {
                    if (supplied != null) Arrays.fill(supplied, '\0');
                    Arrays.fill(expected, '\0');
                }
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException("Callback error");
                failure.initCause(e);
                throw failure;
            } finally {
                password.clearPassword();
            }
        }

        @Override public boolean commit() throws LoginException {
            System.out.println("password commit");
            if (!authenticated) return false;
            if (subject.isReadOnly()) throw new LoginException("Read-only Subject");
            boolean added = subject.getPrincipals().add(pending);
            owned = added ? pending : null; // Never remove another module's Principal.
            committed = true;
            pending = null;
            return true;
        }

        private void cleanup() throws LoginException {
            if (owned != null) {
                if (subject.isReadOnly())
                    throw new LoginException("Cannot remove from read-only Subject");
                subject.getPrincipals().remove(owned);
            }
            pending = null;
            owned = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() throws LoginException {
            System.out.println("password abort");
            boolean participated = authenticated || committed;
            cleanup();
            return participated;
        }

        @Override public boolean logout() throws LoginException {
            System.out.println("password logout");
            cleanup();
            return true;
        }
    }

    public static final class DenyModule implements LoginModule {
        @Override public void initialize(Subject s, CallbackHandler h,
                                         Map<String, ?> sharedState,
                                         Map<String, ?> options) {
            System.out.println("deny initialize");
        }
        @Override public boolean login() throws LoginException {
            System.out.println("deny login");
            throw new FailedLoginException("Second REQUIRED module rejects");
        }
        @Override public boolean commit() {
            System.out.println("deny commit");
            return false;
        }
        @Override public boolean abort() {
            System.out.println("deny abort");
            return false;
        }
        @Override public boolean logout() {
            System.out.println("deny logout");
            return true;
        }
    }

    static Configuration configuration(boolean addDeny) {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"demo".equals(name)) return null;
                AppConfigurationEntry password = new AppConfigurationEntry(
                        PasswordModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of());
                if (!addDeny) return new AppConfigurationEntry[]{password};
                AppConfigurationEntry deny = new AppConfigurationEntry(
                        DenyModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of());
                return new AppConfigurationEntry[]{password, deny};
            }
        };
    }

    static CallbackHandler handler(String value) {
        return callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(value.toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        System.out.println("-- success --");
        LoginContext good = new LoginContext("demo", null,
                handler("lab-secret"), configuration(false));
        good.login();
        System.out.println("principal count after commit: " +
                good.getSubject().getPrincipals(UserPrincipal.class).size());
        good.logout();
        System.out.println("principal count after logout: " +
                good.getSubject().getPrincipals(UserPrincipal.class).size());

        System.out.println("-- wrong password --");
        LoginContext wrong = new LoginContext("demo", null,
                handler("wrong"), configuration(false));
        try {
            wrong.login();
            throw new AssertionError("Unexpected success");
        } catch (LoginException expected) {
            System.out.println("wrong password rejected: true");
        }

        System.out.println("-- later REQUIRED failure --");
        LoginContext denied = new LoginContext("demo", null,
                handler("lab-secret"), configuration(true));
        try {
            denied.login();
            throw new AssertionError("Unexpected success");
        } catch (LoginException expected) {
            System.out.println("required module failure rejected: true");
        }
    }
}
```

### 8.1 Biên dịch/chạy

Sử dụng JDK 21 hoặc compiler hỗ trợ `--release 21`:

```text
java -version
javac -version
javac --release 21 -encoding UTF-8 JaasLifecycleDemo.java
java JaasLifecycleDemo
```

**Stdout đã kiểm thử chính xác:**

```text
-- success --
password initialize
password login
password commit
principal count after commit: 1
password logout
principal count after logout: 0
-- wrong password --
password initialize
password login
password abort
wrong password rejected: true
-- later REQUIRED failure --
password initialize
password login
deny initialize
deny login
password abort
deny abort
required module failure rejected: true
```

Ba kết quả cần hiểu:

**Thành công:** `login` xác thực tạm, `commit` mới thêm một `UserPrincipal` vào Subject. `logout` xóa đúng Principal do module thêm nên count từ **1 xuống 0**.

**Mật khẩu sai:** `FailedLoginException` được ném ngay trong `login`; `abort` dọn state, **không có dòng `password commit`**, caller nhận LoginException.

**Module sau thất bại:** `PasswordModule.login` đã thành công, `DenyModule.login` từ chối khi flag REQUIRED, rồi `abort` được gọi trên cả hai; không module nào được commit. Trace còn chứng minh `deny initialize` có thể xảy ra **sau** `password login`, vì JAAS có thể khởi tạo từng module khi cần.

Chương trình có public nested modules với no-arg constructor; `AppConfigurationEntry` lấy binary class name từ `PasswordModule.class.getName()`, tránh lỗi tên khi nạp class lồng nhau. Kết quả này đã được biên dịch và chạy với `javac --release 21` trên JDK có JAAS chuẩn.

### 8.2 Giải thích lựa chọn trạng thái trong code

- `pending` chỉ có sau khi credential đúng, không tự làm Subject có principal.
- `authenticated` lưu kết quả pha 1 trong instance, tránh truyền “thành công” qua shared static variable.
- `owned` chỉ được gán nếu `subject.getPrincipals().add(pending)` trả `true`. Nếu Principal bằng giá trị đã tồn tại, module không nhận ownership và không xóa người khác ở logout.
- `commit` kiểm `subject.isReadOnly()` trước khi sửa; nếu không thể commit thì ném LoginException.
- `cleanup` xóa `owned`, đặt `pending` và các boolean về trạng thái sạch. `abort` gọi cleanup ngay cả khi `login` chưa thành công.
- `DenyModule.abort` trả `false` bởi module không có successful state để commit; đây không phải một lần đăng nhập thành công bị đảo ngược.
- `PasswordCallback.clearPassword()` và `Arrays.fill` dọn những mảng có thể dọn; String literal trong demo vẫn tồn tại theo semantics JVM, không phải kỹ thuật xử lý secret production.

## 9. Cấu hình ngoài bằng JAAS file và khác biệt với ví dụ

Một cách phổ biến khác là dùng file cấu hình JAAS:

```text
demo {
    JaasLifecycleDemo$PasswordModule required;
    JaasLifecycleDemo$DenyModule required;
};
```

Dấu `$` là một phần **binary class name** của nested class trong ví dụ. Trong dự án thật, một LoginModule thường là class top-level ở package được quản lý. Mỗi stanza gồm tên class, flag và options; file phải nằm ở nơi deployment có quyền đọc, không chứa mật khẩu dạng hardcoded.

Khi dùng installed `Configuration` từ file, ứng dụng thường khởi tạo `new LoginContext("demo", callbackHandler)` hoặc tương đương. Có thể cấu hình location qua `java.security.auth.login.config` theo cơ chế JDK/triển khai. **Ví dụ Java ở phần 8 không sử dụng file này** vì truyền `Configuration` trong bộ nhớ trực tiếp vào constructor; đừng đặt file rồi kỳ vọng chương trình tự đọc nó.

Cấu hình `required` của file tương ứng `AppConfigurationEntry.LoginModuleControlFlag.REQUIRED`, nhưng phải kiểm thứ tự modules và các options. Không dùng quyền mặc định hoặc “other” entry mà chưa hiểu đối tượng được xác thực.

## 10. Trường hợp biên cần kiểm thử khi viết LoginModule

### 10.1 Một module thành công nhưng module khác fail

Đây là kịch bản quan trọng để chứng minh **tính nhất quán của Subject**. Test phải xác nhận `commit` **không** được gọi trên module trước khi tổng thể chấp nhận, và sau `abort` không còn pending identities hoặc external tokens.

### 10.2 Commit thất bại sau khi đã tạo một phần state

Ví dụ module đã thêm một group Principal rồi bước tạo credential thất bại. `commit` phải ném LoginException; cleanup/abort phải xóa group Principal **thuộc module đó**, đồng thời revoke resources ngoài hệ thống. JAAS không rollback database tự động. Hãy viết tests cho partial commit, không chỉ success/login fail.

### 10.3 Subject đã read-only

`Subject.setReadOnly()` ngăn thay đổi các tập principals/credentials theo cách thông thường. Nếu module phải ghi Subject ở commit, cần xử lý bằng LoginException. Logout có thể không remove được một Principal thuộc module; cần tuân thủ semantics read-only và các credential hỗ trợ destroy; không ép truy cập bằng cách bỏ kiểm tra.

### 10.4 Duplicate Principal từ module khác

Nếu Subject có sẵn `UserPrincipal("alice")`, lệnh `add` theo set semantics có thể trả false. Nếu module A không thêm phần tử mới nhưng vẫn `logout` và xóa theo tên/class, module có thể xóa state của B. Theo dõi **ownership object** và xử lý duplicate đúng.

### 10.5 Shared state và nhiều lần đăng nhập

`sharedState` là map chia sẻ giữa modules được cấu hình. Khi dùng để trao đổi tên user hoặc credential, phải giới hạn key, type, quyền đọc và xóa secret sau khi dùng. Không tái sử dụng module instance/`LoginContext` cho nhiều Subject; tài liệu `LoginContext` lưu ý không dùng một context để xác thực **nhiều Subject**.

Nếu ứng dụng retry, state của lần cũ phải được reset. Không giữ password hoặc pending principal khi lần đầu thất bại rồi lần hai bắt đầu, và không có static fields dùng chung cho mọi account.

### 10.6 Không biến JAAS thành nơi lưu session

JAAS quản lý quá trình xác thực và cập nhật Subject. Token, cookie, SSO, expiration, revocation, timeout, authorization, audit và network/TLS còn thuộc các tầng liên quan khác. `LoginContext.logout` không tự thu hồi JWT đã phát nếu hệ thống chưa triển khai cơ chế thu hồi tương ứng.

## 11. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Module `login` đúng nhưng app login vẫn fail | Module REQUIRED/REQUISITE khác thất bại | Kiểm cấu hình và trace từng module, xác nhận abort |
| `Subject` có Principal sau khi tổng thể login fail | Module thêm quá sớm trong login, thiếu abort cleanup | Chỉ thêm trong commit; theo dõi ownership |
| Không có `commit` dù PasswordModule đã true | Overall failure hoặc short-circuit theo flags | Kiểm `LoginContext` và control flags |
| `CallbackHandler` bị null/NPE | Constructor/config không cung cấp handler | Check null, ném LoginException có kiểm soát |
| `UnsupportedCallbackException` | Handler không hỗ trợ Name/Password callback | Kiểm hợp đồng callback, không log secret |
| Mật khẩu sai nhưng vẫn đăng nhập được | Trả false thay vì FailedLoginException, cấu hình OPTIONAL/SUFFICIENT yếu | Kiểm phân biệt ignored/failure và policy |
| `commit` ném lỗi read-only Subject | Set principal/credential bị khóa | Kiểm lifecycle setReadOnly và xử lý cleanup |
| Logout xóa Principal của module khác | Xóa theo class/name thay vì ownership | Chỉ xóa contribution thực sự đã thêm |
| Logout không dọn credential | Không implement cleanup hoặc thiếu destroy | Test Subject trước/sau, xử lý secret resources |
| Retry dùng lại kết quả cũ | Không reset boolean/pending identity | Mỗi lần xử lý state rõ ràng; dùng LoginContext riêng |
| `LoginModule` không được nạp | Sai binary name, JAR/classpath, no-arg constructor | Kiểm deployment và `Class.getName()` |
| Trace để lộ password/token | In callbacks/exception details hoặc debug state | Chỉ log phase/result, ẩn secret và PII |

**Không** tự thêm delay hoặc retry vòng lặp trong LoginModule để “chống brute force”. Đặt giới hạn tốc độ, MFA, kiểm soát lockout và giám sát ở những tầng được thiết kế; tránh làm module bị treo hoặc đưa thông tin sai về kết quả.

## 12. Bài tập và checklist hoàn thành

1. Chạy chương trình Java 21, vẽ ba luồng từ `initialize` đến `commit/abort/logout`. Vì sao không có `commit` khi mật khẩu sai?
2. Dùng `DenyModule REQUIRED` để giải thích trường hợp một module đã `login true` nhưng **không có Principal** mới trong Subject.
3. Thay `DenyModule` thành `OPTIONAL` rồi dự đoán kết quả tổng thể. Hãy lý giải cách flag thay đổi điều kiện success/failure.
4. Thiết kế một `LoginModule` trả `false` khi không nhận loại credential phù hợp. Vì sao làm như vậy khác với ném `FailedLoginException` khi password sai?
5. Thêm một `UserPrincipal("alice")` trước khi commit; xem `Set.add` trả true hay false. Khi logout, module có quyền xóa Principal đã tồn tại trước đó không?
6. Viết unit test `abort` trên state trống: module đã bị từ chối ngay trong `login` vẫn phải dọn an toàn.
7. Giả lập lỗi ở giữa `commit` sau khi thêm một role Principal. Xác định cách xóa role đó và bù trừ external side effect mà JAAS không tự thực hiện.
8. Gọi `Subject.setReadOnly` trước commit. Phải xử lý thế nào để không báo đăng nhập thành công giả?
9. Xây một `CallbackHandler` an toàn không dùng literal password; mô tả khi nào `clearPassword` và `Arrays.fill` được gọi.
10. Nếu user đã đăng xuất nhưng web JWT vẫn dùng được, phần nào của hệ thống chịu trách nhiệm sửa? `LoginContext.logout` có tự revoke JWT không?
11. Với `SUFFICIENT` thành công sớm, có được giả định mọi module sau đều được initialize/login không? Hãy giải thích ảnh hưởng của short-circuit.
12. Thiết kế test concurrency cho hai Subject khác nhau. Vì sao một mutable static `Principal` hay password buffer là lỗi nghiêm trọng?

**Tiêu chí hoàn thành:** bạn xác định được **initialize = nhận context; login = xác thực và giữ state tạm; commit = ghi Subject khi cả stack được chấp nhận; abort = dọn khi thất bại; logout = dọn contribution của phiên đã thành công**, và không nhầm JAAS với password hashing, quản trị session hoặc authorization.

## 13. Tài liệu tham khảo

- [Java SE 21 — `javax.security.auth.spi.LoginModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/spi/LoginModule.html): hợp đồng năm phương thức, two-phase login và kết quả boolean/exception.
- [Java SE 21 — `javax.security.auth.login.LoginContext`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/LoginContext.html): điều phối modules, constructor, Subject và logout.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/Configuration.html) và [`AppConfigurationEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): module flags và configuration.
- [Java SE 21 — `Subject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Subject.html): principal/credential sets và read-only.
- [Java SE 21 — `CallbackHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html) và [`PasswordCallback`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): lấy và dọn input.
- [Oracle Java 21 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): hai pha, initialize/login/commit/abort/logout.
- [Oracle Java 21 — JAAS Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-reference-guide.html): control flags, JAAS config và Subject.

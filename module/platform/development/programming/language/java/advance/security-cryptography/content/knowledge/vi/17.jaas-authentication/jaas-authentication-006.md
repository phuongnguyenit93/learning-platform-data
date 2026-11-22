# 17.6 required, requisite, sufficient, optional và phối hợp nhiều LoginModule

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách **JAAS (Java Authentication and Authorization Service)** dùng `LoginContext`, `Configuration`, `LoginModule`, `Subject`, `Principal` và `CallbackHandler` để kết hợp nhiều nguồn xác thực trong Java 17.
2. Phân biệt bốn **LoginModule control flags**: `required`, `requisite`, `sufficient` và `optional` — đặc biệt là quy tắc tiếp tục, dừng sớm và kết quả **toàn bộ stack**.
3. Dự đoán đúng các trường hợp khó: `required` thất bại nhưng `sufficient` phía sau thành công; `sufficient` thành công trước một `required`; nhiều `optional`; `requisite` thất bại giữa stack.
4. Hiểu hai giai đoạn của JAAS: `login()` để kiểm tra từng module, sau đó `commit()` hoặc `abort()`; dùng `logout()` để gỡ identity/credential do module thêm.
5. Tạo và chạy **hai chương trình Java 17 độc lập**: mô phỏng ma trận control flags và chứng minh cấu hình **MFA có OTP `optional`** có thể vô tình cho phép đăng nhập khi OTP sai.
6. Phân biệt **OR (các cơ chế thay thế)** với **AND (nhiều yếu tố bắt buộc)**; thiết kế cấu hình, callback, shared state, quản lý lỗi và kiểm thử để tránh đường vòng bảo mật.

## 1. JAAS hỗ trợ “stacked authentication” như thế nào?

JAAS là mô hình đăng nhập có thể thay thế và kết hợp nhiều thành phần xác thực. Ứng dụng không cần biết chi tiết đang kiểm password, Kerberos, smart card hay một cơ chế khác; nó gọi `LoginContext`. Các thành phần xác thực cụ thể triển khai interface `javax.security.auth.spi.LoginModule`.

Một sơ đồ:

```text
Application
    |
    | new LoginContext("AppName", handler)
    | context.login()
    v
JAAS LoginContext
    |
    +--> Configuration: AppName
    |       |
    |       +-- PasswordModule  required
    |       +-- OtpModule       required
    |       +-- AuditModule     optional
    |
    +--> LoginModule.login() theo thứ tự
    |
    +--> Đánh giá các control flags
    |
    +--> Nếu login phase thành công: commit()
    |      và cập nhật Subject/Principal
    |
    +--> Nếu login phase thất bại: abort()
           và xóa trạng thái tạm
    |
    v
Application nhận Subject nếu thành công
```

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| `LoginContext` | Đầu mối ứng dụng gọi `login()`, `getSubject()`, `logout()`; điều phối nhiều module |
| `Configuration` | Danh sách module, **thứ tự**, flag, options theo tên ứng dụng |
| `AppConfigurationEntry` | Mô tả một module class, một flag, options map |
| `LoginModule` | Kiểm một hình thức xác thực, quản lý lifecycle của trạng thái/Principal |
| `CallbackHandler` | Cơ chế module lấy thông tin đầu vào, ví dụ username/password hoặc mã xác thực |
| `sharedState` | Map cùng phiên đăng nhập được chia sẻ giữa các module; cần tránh chứa secret không cần thiết |
| `Subject` | Thực thể đã xác thực và tập `Principal`/credentials của nó |
| `Principal` | Danh tính/thuộc tính chủ thể ở mức identity; **không tự chứng minh quyền truy cập** |

Lời gọi ứng dụng có thể rất đơn giản:

```java
LoginContext context = new LoginContext("MyApplication", callbackHandler);
context.login(); // Thành công thì trả về; thất bại ném LoginException
Subject subject = context.getSubject();
// Sử dụng subject theo chính sách ứng dụng, rồi:
context.logout();
```

Đây là **đoạn code nhúng**, không phải file Java độc lập: cần imports, định nghĩa `callbackHandler` và cấu hình JAAS cho tên `MyApplication`. `LoginContext` quyết định module nào được gọi dựa trên cấu hình, không phải caller tự chạy từng `LoginModule.login()` để “lấy phiếu”.

**Thứ tự module là một phần của chính sách bảo mật.** Cùng danh sách nhưng đổi vị trí `sufficient` hoặc `requisite` có thể đổi kết quả và số cơ chế xác thực thực sự được yêu cầu.

## 2. Cấu trúc cấu hình và bốn control flags

Một login configuration file thường có cấu trúc:

```text
ApplicationName {
    module.class.Name required  optionA="value";
    module.class.Name requisite optionB="value";
    module.class.Name sufficient optionC="value";
    module.class.Name optional  optionD="value";
};
```

Đây là **cú pháp minh họa cấu trúc**, không phải cấu hình chạy được vì các class name trong đoạn này chỉ mô tả vị trí và không phải class đã được triển khai. Mỗi module entry kết thúc bằng `;`, nhóm ứng dụng kết thúc bằng `};`. Tên app được truyền vào `LoginContext`.

Tài liệu `Configuration` của Java 17 nêu chính xác:

| Flag | Phải thành công để toàn bộ stack hợp lệ? | Nếu `login()` thành công | Nếu `login()` thất bại |
| --- | --- | --- | --- |
| **`required`** | **Có** | Tiếp tục module phía sau | **Vẫn tiếp tục**, nhưng kết quả toàn stack sẽ fail |
| **`requisite`** | **Có** | Tiếp tục module phía sau | **Dừng phase login ngay**, trả failure |
| **`sufficient`** | Không bắt buộc | **Có thể kết thúc sớm thành công** nếu **chưa có `required`/`requisite` phía trước thất bại** | Tiếp tục module phía sau |
| **`optional`** | Không bắt buộc | Tiếp tục module phía sau | Tiếp tục module phía sau |

**Điều kiện tổng thể:** tất cả module `required` và `requisite` **được áp dụng trước khi kết thúc sớm hợp lệ** phải thành công. Nếu cấu hình **không có `required`/`requisite`**, ít nhất **một** `sufficient` hoặc `optional` phải thành công. `SUFFICIENT` thành công có thể chặn việc thực thi các module nằm phía sau; do đó không thể hiểu câu “mọi required luôn phải chạy” một cách tách rời thứ tự cấu hình.

### 2.1 `required` — bắt buộc nhưng không dừng ngay khi thất bại

Ví dụ:

```text
PasswordCheck  required  -> FAIL
DeviceCheck    optional  -> PASS
AuditCheck     optional  -> PASS

Kết quả cuối: FAIL
```

`LoginContext` vẫn gọi các module sau `PasswordCheck`. Ưu điểm: giúp tránh tiết lộ quá rõ việc thất bại xảy ra ở bước nào chỉ bằng **việc dừng ngay**, và cho phép các thành phần khác thực hiện công việc đã được thiết kế. Nhưng điều này **không tự đảm bảo thời gian phản hồi constant-time** vì các module có thể mất thời gian khác nhau.

**Không** xem kết quả `optional` thành công là “cứu” được một `required` đã thất bại.

### 2.2 `requisite` — bắt buộc và có khả năng short-circuit thất bại

Ví dụ:

```text
AccountExists  requisite -> FAIL
PasswordCheck  required  -> KHÔNG login()
OtpCheck       required  -> KHÔNG login()

Kết quả cuối: FAIL
```

Nếu `requisite` thất bại, JAAS dừng **phase kiểm tra `login()`** ngay. Tuy nhiên, cơ chế cleanup `abort()` vẫn được gọi theo lifecycle; “dừng sớm” không có nghĩa bỏ sạch xử lý hậu kỳ.

Đặt `requisite` ở phía trước có thể **tiết kiệm chi phí** khi không cần xử lý các bước sau lúc một điều kiện bắt buộc đã hỏng. Đổi lại, thời gian hoặc cách truy cập external system có thể lộ dấu hiệu lý do lỗi nếu không thiết kế thông báo và timing phù hợp.

### 2.3 `sufficient` — đủ để hoàn tất sớm nếu không có thất bại bắt buộc trước đó

Hai ví dụ cần phân biệt:

```text
Case A:
PasswordCheck  required   -> PASS
TrustedTicket  sufficient -> PASS
ExtraCheck     optional   -> KHÔNG login()

Kết quả: PASS (không có mandatory failure phía trước)
```

```text
Case B:
PasswordCheck  required   -> FAIL
TrustedTicket  sufficient -> PASS
ExtraCheck     optional   -> vẫn login()

Kết quả: FAIL (required failure đã xảy ra)
```

Điều kiện “không có lỗi bắt buộc trước đó” là **điểm dễ bị ghi thiếu** khi tóm tắt JAAS. `SUFFICIENT` không xóa một lỗi `REQUIRED`/`REQUISITE` đã phát sinh.

Ngược lại, `sufficient` **ở quá sớm** có thể tạo lỗ hổng policy:

```text
CachedTicket   sufficient -> PASS
PasswordCheck  required   -> KHÔNG login()

Kết quả: PASS
```

Nếu business rule yêu cầu password **luôn phải kiểm**, cách xếp trên là sai. Không thể nói “PasswordCheck được đánh dấu required, nên chắc chắn password bắt buộc” khi đã có `sufficient` được phép dừng sớm trước đó.

### 2.4 `optional` — không phải “cấm”, cũng không phải “phải kiểm”

`Optional` có thể thành công hoặc thất bại mà vẫn cho JAAS chạy tiếp:

```text
PasswordCheck  required -> PASS
OtpCheck       optional -> FAIL

Kết quả: PASS
```

Nếu team nghĩ OTP là **bắt buộc**, đây là một cấu hình MFA sai nghiêm trọng. `optional` thích hợp cho module bổ sung hợp lệ theo thiết kế (ví dụ optional environment identity enrichment), không phải cho yếu tố bảo mật quan trọng mà user **phải** vượt qua.

Khi chỉ có các module `optional`:

```text
A optional -> FAIL
B optional -> PASS
=> PASS

A optional -> FAIL
B optional -> FAIL
=> FAIL
```

Ít nhất một module phải thành công nếu không có module mandatory. Đây là quy tắc aggregate, **không phải `optional` nghĩa “luôn cho phép login”**.

## 3. Cách hình dung thuật toán tổng hợp

Để dự đoán kết quả, có thể dùng mô hình khái niệm sau (không phải source code nội bộ JDK):

```text
mandatoryFailure = false
anySuccess = false

for each LoginModule in Configuration order:
    result = module.login()

    nếu REQUIRED:
        thành công -> anySuccess = true
        thất bại  -> mandatoryFailure = true
        luôn tiếp tục

    nếu REQUISITE:
        thành công -> anySuccess = true, tiếp tục
        thất bại  -> dừng phase login, overall FAIL

    nếu SUFFICIENT:
        thành công:
            anySuccess = true
            nếu !mandatoryFailure: kết thúc phase login sớm PASS
            nếu mandatoryFailure: tiếp tục, overall cuối vẫn FAIL
        thất bại -> tiếp tục

    nếu OPTIONAL:
        thành công -> anySuccess = true
        thất bại  -> tiếp tục

sau phase login:
    nếu mandatoryFailure: overall FAIL
    nếu không mandatoryFailure và có đủ thành công: overall PASS
    nếu không có module nào xác thực thành công: overall FAIL

overall PASS -> commit phase
overall FAIL -> abort phase
```

Mô hình cố ý giản lược các chi tiết `LoginModule.login()` trả `false` (module xin **bị bỏ qua**, xem mục 8), thứ tự exception ưu tiên và cơ chế commit/abort; không dùng nó để tự viết engine JAAS thay `LoginContext`.

Một cách kiểm tra nhanh khi review config:

1. Đọc module **từ trên xuống**.
2. Đánh dấu lỗi `required`/`requisite` bắt buộc.
3. Nếu một `requisite` thất bại: dừng phase login ngay.
4. Nếu `sufficient` thành công: kiểm **trước nó** có mandatory failure không; nếu không có, các module **sau nó không còn là điều kiện login**.
5. Nếu hết stack: tất cả mandatory phải pass; trường hợp toàn optional/sufficient phải có ít nhất một pass.

## 4. Thực hành 1 — Java 17 kiểm chứng ma trận tám trường hợp

Chương trình sau tạo **một `Configuration` ở bộ nhớ**, không thay đổi global JAAS configuration hoặc file của máy. Nó dùng `ProbeModule` giả lập kết quả `login()` dựa trên options của từng entry: `pass`, `fail` hoặc `ignore`. Mục tiêu là nhìn thấy **module nào được chạy** và **kết quả toàn stack**.

Dữ liệu là giả lập, **không xác thực người dùng thật**. Không dùng cơ chế “`behavior=pass`” làm LoginModule production. Chương trình vẫn triển khai đầy đủ interface `LoginModule` và dùng `LoginContext` thật để kiểm nghiệm hành vi.

Tạo file **`JaasFlagsMatrixDemo.java`**:

```java
import java.security.Principal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasFlagsMatrixDemo {
    static final List<String> CALLED = new ArrayList<>();

    static final class DemoPrincipal implements Principal {
        private final String name;
        DemoPrincipal(String name) { this.name = name; }
        public String getName() { return name; }
    }

    public static class ProbeModule implements LoginModule {
        private Subject subject;
        private String name;
        private String behavior;
        private boolean passed;
        private DemoPrincipal principal;

        public ProbeModule() {}

        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            name = (String) options.get("name");
            behavior = (String) options.get("behavior");
            passed = false;
        }

        public boolean login() throws LoginException {
            CALLED.add(name);
            if ("fail".equals(behavior)) {
                throw new LoginException(name + " rejected");
            }
            if ("ignore".equals(behavior)) return false;
            passed = true;
            return true;
        }

        public boolean commit() {
            if (!passed) return false;
            principal = new DemoPrincipal(name);
            subject.getPrincipals().add(principal);
            return true;
        }

        public boolean abort() {
            logout();
            passed = false;
            return true;
        }

        public boolean logout() {
            if (principal != null) subject.getPrincipals().remove(principal);
            principal = null;
            passed = false;
            return true;
        }
    }

    static AppConfigurationEntry entry(String name,
            AppConfigurationEntry.LoginModuleControlFlag flag, String behavior) {
        return new AppConfigurationEntry(ProbeModule.class.getName(), flag,
                Map.of("name", name, "behavior", behavior));
    }

    static void trial(String label, AppConfigurationEntry... stack)
            throws Exception {
        CALLED.clear();
        Configuration config = new Configuration() {
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                return "lab".equals(name) ? stack.clone() : null;
            }
        };
        LoginContext context = new LoginContext(
                "lab", new Subject(), (CallbackHandler) null, config);
        String result = "PASS";
        try {
            context.login();
        } catch (LoginException e) {
            result = "FAIL";
        }
        System.out.println(label + " -> " + result +
                "; login calls=" + String.join(",", CALLED));
        if ("PASS".equals(result)) context.logout();
    }

    public static void main(String[] args) throws Exception {
        var required = AppConfigurationEntry.LoginModuleControlFlag.REQUIRED;
        var requisite = AppConfigurationEntry.LoginModuleControlFlag.REQUISITE;
        var sufficient = AppConfigurationEntry.LoginModuleControlFlag.SUFFICIENT;
        var optional = AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL;

        trial("required-fail-then-sufficient-pass",
              entry("A", required, "fail"),
              entry("B", sufficient, "pass"),
              entry("C", optional, "pass"));
        trial("required-pass-sufficient-pass",
              entry("A", required, "pass"),
              entry("B", sufficient, "pass"),
              entry("C", optional, "fail"));
        trial("requisite-fail-stops",
              entry("A", optional, "pass"),
              entry("B", requisite, "fail"),
              entry("C", optional, "pass"));
        trial("only-optional-one-pass",
              entry("A", optional, "fail"),
              entry("B", optional, "pass"));
        trial("only-optional-all-fail",
              entry("A", optional, "fail"),
              entry("B", optional, "ignore"));
        trial("required-pass-optional-fail",
              entry("A", required, "pass"),
              entry("B", optional, "fail"));
        trial("sufficient-before-required",
              entry("A", sufficient, "pass"),
              entry("B", required, "fail"));
        trial("sufficient-fail-required-pass",
              entry("A", sufficient, "fail"),
              entry("B", required, "pass"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 JaasFlagsMatrixDemo.java
java JaasFlagsMatrixDemo
```

**Stdout đã kiểm tra bằng JDK có Java 17-compatible APIs:**

```text
required-fail-then-sufficient-pass -> FAIL; login calls=A,B,C
required-pass-sufficient-pass -> PASS; login calls=A,B
requisite-fail-stops -> FAIL; login calls=A,B
only-optional-one-pass -> PASS; login calls=A,B
only-optional-all-fail -> FAIL; login calls=A,B
required-pass-optional-fail -> PASS; login calls=A,B
sufficient-before-required -> PASS; login calls=A
sufficient-fail-required-pass -> PASS; login calls=A,B
```

### 4.1 Phân tích từng dòng kết quả

| Kịch bản | Đọc thứ tự module | Kết quả và lý do |
| --- | --- | --- |
| `required-fail-then-sufficient-pass` | A required fail, B sufficient pass, C optional pass | **FAIL**: lỗi mandatory A tồn tại; B không thể short-circuit để xóa lỗi A |
| `required-pass-sufficient-pass` | A required pass, B sufficient pass, C optional fail | **PASS**: B đủ điều kiện kết thúc sớm, C không được gọi trong login phase |
| `requisite-fail-stops` | A optional pass, B requisite fail, C optional pass | **FAIL**: B dừng phase login ngay, C không được gọi |
| `only-optional-one-pass` | A optional fail, B optional pass | **PASS**: không có mandatory và ít nhất một optional pass |
| `only-optional-all-fail` | A optional fail, B optional return false | **FAIL**: không có module nào xác thực thành công |
| `required-pass-optional-fail` | A required pass, B optional fail | **PASS**: B không bắt buộc |
| `sufficient-before-required` | A sufficient pass, B required fail nếu được gọi | **PASS**: B **không được gọi** vì A kết thúc sớm; đây là nguy cơ sai cấu hình |
| `sufficient-fail-required-pass` | A sufficient fail, B required pass | **PASS**: A không bắt buộc, B pass |

**Chú ý:** bảng và stdout theo dõi **những lời gọi `login()`**. Khi một `sufficient` kết thúc phase login sớm, vòng đời phase hai của JAAS vẫn cần được giải quyết. Không dùng danh sách `login calls` để tự suy ra chắc chắn mỗi `commit()/abort()` trên mọi provider đã được gọi thế nào; `LoginModule` phải xử lý an toàn ngay cả khi module chưa có trạng thái login thành công.

### 4.2 Giải thích code

1. `AppConfigurationEntry` mang class name, control flag và options. Trong một stack, cùng class `ProbeModule` được dùng nhiều lần với tên/behavior khác nhau — các instance riêng vẫn có thể xuất hiện.
2. `Configuration#getAppConfigurationEntry("lab")` trả **danh sách entry đúng thứ tự**. Demo cung cấp cấu hình trực tiếp qua constructor `LoginContext(..., config)`, không đổi cấu hình bảo mật toàn JVM.
3. `ProbeModule.login()` minh họa **true** khi thành công, **LoginException** khi thất bại, **false** khi module chọn bị bỏ qua. Trên hệ thống thật phải kiểm credential/identity đúng nghĩa.
4. `commit()` chỉ thêm `Principal` vào `Subject` khi module có `passed=true`. Nếu module không login thành công, trả false để không thêm danh tính giả.
5. `abort()` và `logout()` dọn `Principal` do module thêm, không xóa `Principal` của module khác; vòng đời này cần được triển khai chính xác để tránh state leak.
6. `CALLED` là danh sách static chỉ dùng để **quan sát một process lab chạy tuần tự**, không phù hợp làm global request trace cho dịch vụ đa luồng.

## 5. Hai giai đoạn `login/commit/abort`: chi tiết bảo mật rất quan trọng

Nhiều người chỉ đọc bảng flag mà bỏ qua lifecycle. Theo `LoginModule` Developer's Guide:

**Giai đoạn 1 — thử xác thực:**
- `initialize(Subject, CallbackHandler, sharedState, options)` trước các lời gọi của module.
- `login()` xác minh credential hoặc trạng thái đối với cơ chế đó và ghi **trạng thái tạm riêng** (ví dụ `succeeded`).
- Module nên **không** vội công bố identity/credential lâu dài cho `Subject` ngay khi `login()` thành công: các module mandatory **khác có thể vẫn thất bại**.
- `login()` trả `true` nếu module xác thực thành công; trả `false` nếu module chọn “ignore”; ném `LoginException` nếu authentication thất bại.

**Giai đoạn 2 — hoàn tất hoặc hủy:**
- Nếu kiểm tra tổng thể thành công, `LoginContext` gọi `commit()` trên các module theo lifecycle: module có trạng thái thành công thêm `Principal`/credential được phép vào `Subject`.
- Nếu tổng thể thất bại, `abort()` được gọi để hủy trạng thái đăng nhập tạm, xóa password/token ngắn hạn và tránh rò rỉ state.
- Nếu `commit()` ở một module thất bại, engine phải xử lý failure/abort; bản thân module cần thực hiện cleanup đầy đủ.
- Sau phiên thành công, `LoginContext.logout()` gọi `logout()` để gỡ những identity/credentials **do module đó thêm**, không xóa của module khác.

```text
Module A.login() PASS ---+
                         |
Module B.login() FAIL ---+--> Overall FAIL
                         |
                         v
                 abort() / cleanup
                 (KHÔNG publish Subject được xác thực)
```

```text
Module A.login() PASS ---+
                         |
Module B.login() PASS ---+--> Overall PASS
                         |
                         v
                       commit()
                         |
                         v
                   Subject Principals
                         |
                         v
                       logout()
                         |
                         v
                Dọn identity/credential đã thêm
```

**Không được tự gọi `module.commit()` để “cứu” một stack thất bại.** Giao thức hai phase bảo vệ tính nhất quán của danh tính giữa nhiều module và hỗ trợ rollback.

### 5.1 Đừng nhầm `LoginModule.login()` trả `false` và ném exception

Theo interface `LoginModule`:

- `return true`: module xác thực thành công.
- `return false`: module muốn được **bỏ qua** (ignored), không phải hình thức báo rõ một lần kiểm tra credential đã thất bại.
- `throw new LoginException(...)`: module báo **authentication failed**.

Vì flag được đánh giá trên kết quả module, **không** tùy tiện thay việc ném `LoginException` bằng `return false` trong module dùng làm chính sách bắt buộc. Việc module tự tuyên bố ignored có semantics khác với explicit failed và có thể gây hậu quả không mong đợi cho quá trình tổng hợp.

Hãy tuân theo contract của module/provider thực tế và có unit/integration tests cho cả ba kiểu kết quả. Đừng dùng `catch (Exception ignored) { return true; }` hoặc nuốt lỗi network/credential rồi cho JAAS pass.

### 5.2 `Subject` sau login có đúng những danh tính nào?

`Subject` chứa tập `Principal`, public credentials và private credentials. Mỗi module có thể đóng góp danh tính (account ID, realm, role đã xác thực...) trong `commit()` nếu module đó thực sự thành công.

Hai vấn đề:

- **Conflicting identity**: nếu password module xác thực user A nhưng token module xác thực user B và cả hai cùng trả pass, hệ thống không nên tự xem đó là cùng một chủ thể. Cần ràng buộc identity/tenant/session xuyên module.
- **Privilege pollution**: nếu một module không bắt buộc thêm role/quyền một cách thiếu kiểm soát, `Subject` có thể mang Principal có ý nghĩa quá mạnh so với bằng chứng. Tách việc **xác thực danh tính** với **ủy quyền thao tác** dựa trên policy.

`Principal` chỉ là object đại diện danh tính. Bản thân việc có `Principal("admin")` trong `Subject` không phải chứng chỉ cho phép truy cập nếu ứng dụng không xác minh nguồn và quy tắc cấp quyền.

## 6. AND versus OR: chọn flag để biểu đạt chính sách

### 6.1 Chính sách AND — phải qua nhiều điều kiện

Ví dụ ứng dụng đòi **password và OTP**:

```text
PasswordModule required
OtpModule      required
```

Tổng thể pass nếu **cả hai** pass. Một trong hai fail thì phải reject, nhưng `required` vẫn cho module sau chạy. Nếu muốn dừng ngay khi password fail để tránh OTP request vô ích (với đánh đổi về timing), có thể:

```text
PasswordModule requisite
OtpModule      required
```

Cả hai vẫn là mandatory khi được gọi theo thứ tự. Tuy nhiên **đặt một `sufficient` trước các bước bắt buộc** có thể biến “AND” thành OR ngoài ý muốn.

### 6.2 Chính sách OR — một cơ chế đáng tin cậy có thể đủ

Ví dụ một ứng dụng có thể xác thực bằng **một trong hai cơ chế thay thế**, với policy cho phép:

```text
KerberosTicketModule sufficient
FallbackPasswordModule required
```

Nếu ticket hợp lệ, stack có thể kết thúc sớm, không kiểm password; nếu ticket không hợp lệ, module password trở thành đường thay thế bắt buộc. Chỉ dùng nếu **hai cơ chế thực sự được tổ chức đánh giá là đủ độc lập cho cùng mức bảo mật**, không phải một yếu tố yếu được phép bỏ qua yếu tố mạnh.

Không được viết “`sufficient` == MFA thành công” hay “`required` được bỏ qua vì đã có một cơ chế khác” như quy tắc tổng quát. Sự cho phép bypass phải được mô tả trong threat model và test.

### 6.3 Một module “audit” nên ở đâu?

Nếu audit/logging là **hành động bắt buộc**, không nên dựa vào một `AuditModule optional` đứng sau `SufficientModule`: module audit có thể không được gọi ở phase login khi sufficient short-circuit. Audit tập trung ở tầng điều phối trước/sau `LoginContext.login()` hoặc hệ thống eventing được thiết kế rõ có thể phù hợp hơn, và phải test các đường dừng sớm/failure.

Vì `LoginModule` dành cho authentication, việc nhét mọi side effect như audit, provisioning, billing vào callback đăng nhập có thể khiến các control flags bất ngờ thay đổi cách hoạt động của chúng.

## 7. Thực hành 2 — Minh họa MFA bị bỏ qua khi OTP chuyển thành OPTIONAL

Bài lab sau dùng hai `LoginModule`:

1. `PasswordModule` mô phỏng xác minh username/password cố định cho **user lab**.
2. `OtpModule` mô phỏng so mã OTP cố định trong bộ nhớ **chỉ để minh họa control flag**, không triển khai TOTP/HOTP/chống replay thật.

Hai module dùng chung một `Subject`, `CallbackHandler` và `sharedState`. `PasswordModule` ghi **username không bí mật** vào shared state sau khi xác minh; `OtpModule` đọc username này rồi xác minh OTP. Đừng lưu password, OTP hoặc khóa MFA vào shared state theo cách không kiểm soát.

Chương trình thử ba cấu hình:

- Password required, OTP required và mã đúng → **PASS** với hai Principal.
- Password required, OTP required và mã sai → **FAIL**.
- Password required, OTP **optional** và mã sai → **PASS** với **một** Principal: đây là bằng chứng rằng optional không thực thi MFA.

**Security notice:** password `lab-pass` và OTP `123456` cố định chỉ dành cho lab. `Arrays.equals` trên mảng password demo không thay thế password KDF/PBKDF2/Argon2id trong sản phẩm. Đây là bài về **JAAS orchestration**, không phải hướng dẫn viết hệ thống password hoặc OTP production.

### 7.1 Mã Java 17 `JaasTwoFactorPolicyDemo.java`

```java
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public class JaasTwoFactorPolicyDemo {
    public record UserPrincipal(String name) implements Principal {
        public String getName() { return name; }
    }
    public record FactorPrincipal(String name) implements Principal {
        public String getName() { return name; }
    }

    public static class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private Map<String, Object> shared;
        private boolean success;
        private Principal added;

        @SuppressWarnings("unchecked")
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
            this.shared = (Map<String, Object>) sharedState;
        }

        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("Username");
            PasswordCallback password = new PasswordCallback("Password", false);
            char[] typed = null;
            try {
                handler.handle(new Callback[] {name, password});
                typed = password.getPassword();
                char[] demoExpected = "lab-pass".toCharArray();
                boolean match = "student".equals(name.getName()) &&
                        typed != null && Arrays.equals(typed, demoExpected);
                Arrays.fill(demoExpected, '\0');
                if (!match) throw new LoginException("Password factor rejected");
                shared.put("user", name.getName()); // Không đưa secret vào shared state
                success = true;
                return true;
            } catch (Exception ex) {
                if (ex instanceof LoginException le) throw le;
                throw new LoginException("Callback failed");
            } finally {
                if (typed != null) Arrays.fill(typed, '\0');
                password.clearPassword();
            }
        }

        public boolean commit() {
            if (!success) return false;
            added = new UserPrincipal((String) shared.get("user"));
            subject.getPrincipals().add(added);
            return true;
        }

        public boolean abort() { return logout(); }

        public boolean logout() {
            if (added != null) subject.getPrincipals().remove(added);
            added = null;
            success = false;
            if (shared != null) shared.remove("user");
            return true;
        }
    }

    public static class OtpModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private Map<String, ?> shared;
        private boolean success;
        private Principal added;

        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
            this.shared = sharedState;
        }

        public boolean login() throws LoginException {
            if (!"student".equals(shared.get("user"))) {
                throw new LoginException("Password factor must succeed first");
            }
            TextInputCallback input = new TextInputCallback("Demo OTP");
            try { handler.handle(new Callback[]{input}); }
            catch (Exception ex) { throw new LoginException("OTP callback failed"); }
            if (!"123456".equals(input.getText())) {
                throw new LoginException("OTP factor rejected");
            }
            success = true;
            return true;
        }

        public boolean commit() {
            if (!success) return false;
            added = new FactorPrincipal("otp");
            subject.getPrincipals().add(added);
            return true;
        }

        public boolean abort() { return logout(); }

        public boolean logout() {
            if (added != null) subject.getPrincipals().remove(added);
            added = null;
            success = false;
            return true;
        }
    }

    static final class Inputs implements CallbackHandler {
        private final String user, password, otp;

        Inputs(String user, String password, String otp) {
            this.user = user; this.password = password; this.otp = otp;
        }

        public void handle(Callback[] callbacks) throws UnsupportedCallbackException {
            for (Callback cb : callbacks) {
                if (cb instanceof NameCallback nc) nc.setName(user);
                else if (cb instanceof PasswordCallback pc)
                    pc.setPassword(password.toCharArray());
                else if (cb instanceof TextInputCallback tc) tc.setText(otp);
                else throw new UnsupportedCallbackException(cb);
            }
        }
    }

    private static void test(String label, String otp,
            AppConfigurationEntry.LoginModuleControlFlag otpFlag)
            throws Exception {
        Configuration config = new Configuration() {
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"twoFactor".equals(name)) return null;
                return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(PasswordModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED, Map.of()),
                    new AppConfigurationEntry(OtpModule.class.getName(),
                        otpFlag, Map.of())
                };
            }
        };

        LoginContext context = new LoginContext(
            "twoFactor", new Subject(),
            new Inputs("student", "lab-pass", otp), config);
        try {
            context.login();
            System.out.println(label + ": PASS, principals=" +
                    context.getSubject().getPrincipals().size());
            context.logout();
            System.out.println(label + ": after logout=" +
                    context.getSubject().getPrincipals().size());
        } catch (LoginException e) {
            System.out.println(label + ": FAIL");
        }
    }

    public static void main(String[] args) throws Exception {
        test("both-required-correct-otp", "123456",
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED);
        test("both-required-wrong-otp", "000000",
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED);
        test("otp-optional-wrong-otp", "000000",
                AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 JaasTwoFactorPolicyDemo.java
java JaasTwoFactorPolicyDemo
```

Đầu ra **đã biên dịch và chạy kiểm chứng**:

```text
both-required-correct-otp: PASS, principals=2
both-required-correct-otp: after logout=0
both-required-wrong-otp: FAIL
otp-optional-wrong-otp: PASS, principals=1
otp-optional-wrong-otp: after logout=0
```

### 7.2 Tại sao thay một flag làm mất chính sách MFA?

Ở trường hợp OTP `REQUIRED`, khi OTP sai, `OtpModule.login()` ném `LoginException`. Dù password module đã pass, toàn `LoginContext.login()` phải thất bại. `PasswordModule.abort()` được dùng để xóa trạng thái tạm — `Subject` không được coi đã xác thực hai yếu tố.

Khi OTP `OPTIONAL`, lỗi OTP không phải mandatory. Password `REQUIRED` đã pass nên toàn stack **có thể PASS**. `Subject` khi đó có `UserPrincipal` nhưng **không có `FactorPrincipal("otp")`** (stdout có một Principal). Nếu ứng dụng cấp quyền như đã hoàn thành MFA chỉ vì `LoginContext.login()` thành công, nó đã tạo đường bỏ qua OTP.

**Cách xử lý:** nếu MFA thực sự bắt buộc, phải thể hiện bằng `REQUIRED/REQUISITE` hoặc policy điều phối tương đương không bị bypass, và áp dụng quy tắc chỉ cấp quyền “MFA-complete” khi đủ bằng chứng. Không nên chữa lỗi bằng cách “OTP optional nhưng login code sau đó đoán xem user đã nhập mã hay chưa” mà không có authorization policy rõ ràng.

### 7.3 Những chi tiết đáng học từ code

- `LoginContext(..., config)` nhận `Configuration` riêng nên không cần file global và không vô tình đổi cấu hình JAAS của ứng dụng khác.
- `CallbackHandler` chuyển username/password/OTP đến module qua các loại `Callback` tương ứng; không log credential.
- `sharedState` được `PasswordModule` ghi **sau khi xác minh**, rồi `OtpModule` đọc. Demo ép thứ tự Password trước OTP; đảo thứ tự này sẽ khiến `OtpModule` không thấy user.
- `commit()` mới thêm các `Principal` có ý nghĩa vào `Subject` sau khi tổng thể pass.
- `logout()` gỡ đúng những Principal do module thêm. Stdout `after logout=0` là kiểm tra cleanup trong lab.
- Một implementation thật phải dùng password hashing chuẩn, TOTP/HOTP/WebAuthn kiểm tra chống replay/rate limit, source of truth người dùng và session-bound MFA; không dùng mã cố định hoặc `String` immutable chứa secret như trong demo.
- Với nhiều module xác thực nhiều factor, cần **ràng buộc các bằng chứng với cùng principal/session**; không để account A dùng password và account B dùng OTP mà app vẫn coi là MFA cho một user.

## 8. Cấu hình JAAS dạng file và cấu hình programmatic

### 8.1 Cấu hình file

Có thể cung cấp file cấu hình cho JDK qua property:

```bash
java -Djava.security.auth.login.config=jaas.conf MyApplication
```

Đây là **mẫu lệnh cấu hình**, không chạy độc lập khi chưa có file `jaas.conf` và class ứng dụng `MyApplication`. Cách mở/config bảo mật có thể khác theo framework/container.

Ví dụ một file `jaas.conf` **tham khảo dùng chính các class được triển khai trong demo thứ hai** (các class phải nằm trên classpath):

```text
twoFactor {
    JaasTwoFactorPolicyDemo$PasswordModule required;
    JaasTwoFactorPolicyDemo$OtpModule      required;
};
```

Đối với cấu hình này, ứng dụng cần gọi `new LoginContext("twoFactor", handler)` với một `CallbackHandler` cung cấp username/password/OTP; nguồn class demo ở trên dùng `Configuration` programmatic nên **không tự đọc file này** khi chạy `JaasTwoFactorPolicyDemo.main`. Để tích hợp config file, caller phải không truyền `Configuration` tùy chỉnh vào constructor.

**Cẩn thận:** tên module là **tên binary class** (`Outer$Nested`), không phải `Outer.Nested` của mã nguồn; đó là lý do config trên dùng ký tự `$`. Trong hệ thống thật nên dùng class có package namespace rõ ràng, ví dụ tự xây `com.company.auth.PasswordLoginModule` và `com.company.auth.OtpLoginModule` thay vì default package của demo.

Không ghi credential, password hoặc private key làm `ModuleOptions` trong file config. Options phù hợp cho tham số không bí mật như realm, chế độ debug có kiểm soát hoặc cấu hình endpoint đã được bảo vệ.

### 8.2 Programmatic `Configuration`

Hai demo ở trên dùng:

```java
Configuration config = new Configuration() {
    public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
        return "lab".equals(name) ? stack.clone() : null;
    }
};
LoginContext ctx = new LoginContext(
        "lab", new Subject(), handler, config);
```

Đây là đoạn nhúng giải thích API; cần các biến `stack` và `handler`. Cách này hữu ích khi cần test **nhiều tổ hợp flags** trong một process, mỗi test có cấu hình độc lập, không chỉnh global `Configuration.setConfiguration(...)`.

Ngoài ra, khi caller dùng cấu hình cài sẵn qua `Configuration.getConfiguration()`, tên ứng dụng không có entry có thể được xử lý bằng entry `other` nếu đã định nghĩa; nếu không có entry tương ứng, `LoginContext` báo `LoginException`. Không vô tình dùng `other` quá rộng vì một lỗi đánh máy `appName` có thể đưa request tới **stack yếu hơn mong muốn**.

### 8.3 Thứ tự và việc nạp lại cấu hình

`Configuration` kiểm soát thứ tự entry theo đúng danh sách. Có thể có nhiều ứng dụng/realm với nhiều chính sách khác nhau. Một thay đổi flag hoặc vị trí module nên được code review tương tự thay đổi security policy:

- Không xếp cơ chế `sufficient` yếu trước yếu tố `required` mà business bắt buộc.
- Không chuyển `required` sang `optional` chỉ để giảm tỉ lệ login fail khi upstream down nếu yếu tố đó thuộc yêu cầu bảo mật.
- Nếu triển khai fallback, phân biệt **fallback thay thế được phép** với **bypass điều kiện bắt buộc**.
- Nếu config lấy từ file/DB/config service, kiểm soát quyền sửa, version/approval và hành vi reload; không cho user tự chọn cấu hình kém an toàn bằng request parameter.

## 9. CallbackHandler, options và sharedState: cách phối hợp an toàn

### 9.1 CallbackHandler và dữ liệu nhạy cảm

`CallbackHandler` là ranh giới giữa ứng dụng/UI và các module. Những callback JAAS phổ biến:

| Callback | Để lấy/đưa thông tin | Lưu ý |
| --- | --- | --- |
| `NameCallback` | Tên user | Không tin giá trị name nếu chưa được xác minh |
| `PasswordCallback` | Mảng `char[]` password | `getPassword()` và `clearPassword()`, tránh tạo bản sao String không cần thiết |
| `TextInputCallback` | Text phụ như OTP trong demo | Chỉ minh họa; secret thực cần policy bảo vệ memory/log riêng |
| `ConfirmationCallback` | Yêu cầu user xác nhận | Không đồng nghĩa bằng chứng xác thực cryptographic |
| `UnsupportedCallbackException` | Handler không hỗ trợ callback | Cần fail authentication theo policy, không tự pass |

Đừng đặt password/token vào log, trace, exception message hoặc `sharedState` kéo dài quá scope. Password phải được xác minh qua phương thức an toàn chuyên dụng; `PasswordCallback` chỉ là cơ chế truyền input, không thay thế password hashing/KDF hoặc rate limiting.

### 9.2 sharedState cho nhiều module

`initialize` nhận:

```java
public void initialize(
    Subject subject,
    CallbackHandler handler,
    Map<String, ?> sharedState,
    Map<String, ?> options)
```

Đây là chữ ký method ở mức **đoạn nhúng**, cần một class triển khai `LoginModule`. `sharedState` cho phép các module trong một lần `LoginContext` trao đổi state, còn `options` là cấu hình dành cho từng entry.

Các lưu ý:

- Chỉ đặt giá trị thật sự cần chia sẻ; tránh password/OTP/raw credential.
- Xác định **nguồn nào có quyền viết** một key và cách bên đọc xác thực nguồn.
- Không dùng `sharedState` để bỏ qua bước xác minh: module sau cần kiểm kết quả/identity đủ mạnh, không tin một khóa `"authenticated"` do module tùy ý set.
- Cleanup trong `abort/logout`, tránh dữ liệu cũ còn trong Map khi retry hoặc tái sử dụng.
- Thứ tự module quyết định dữ liệu nào đã được đưa vào shared state trước thời điểm module khác được gọi.
- Nếu module cung cấp Kerberos/SSO cùng password, kiểm identity có nhất quán; principal từ hai nguồn không khớp không được tự gộp quyền.

### 9.3 Exceptions và thông điệp lỗi

Một `requisite` có thể dừng sớm, trong khi `required` tiếp tục module phía sau dù fail. Điều này có thể làm thời gian phản hồi hoặc side effects khác nhau:

```text
A requisite -> FAIL:  B, C không login
A required  -> FAIL:  B, C vẫn có thể login
```

Việc chọn flag **không thay thế** kiểm soát account enumeration, rate limiting, audit và thông báo lỗi chung. Nếu ứng dụng trả về “OTP sai” khác “password sai”, kẻ tấn công có thể học thêm trạng thái tài khoản. Nên giữ error messages thống nhất ở bên ngoài, phân loại nguyên nhân trong audit nội bộ có kiểm soát, và bảo đảm mọi nhánh đều không cấp phiên trên failure.

## 10. Khi nào cần REQUIRED, REQUISITE, SUFFICIENT, OPTIONAL?

| Yêu cầu | Cách nghĩ về flag | Cảnh báo |
| --- | --- | --- |
| Phải có password và OTP | Cả hai `required` hoặc một số `requisite`/`required` theo thứ tự hợp lý | Không đặt OTP optional hoặc bị bypass bởi sufficient trước đó |
| Chỉ cần một trong hai phương thức SSO/Password **được phê duyệt là tương đương** | Dùng `sufficient` cho phương thức ưu tiên, fallback phù hợp | Cần kiểm độ mạnh/issuer/tenant, không mặc định mọi SSO đủ mạnh |
| Cần module kiểm mandatory trước khi làm việc tốn chi phí | `requisite` phía trước | Khác biệt timing/side effects và abort phải được đánh giá |
| Một phép enrichment không quyết định login | `optional` | Không cho phép module tùy ý thêm quyền nhạy cảm |
| Một điều kiện bắt buộc nhưng vẫn muốn chạy các module còn lại để giảm tiết lộ điểm lỗi | `required` | Vẫn phải có timeout và giới hạn chi phí |
| Audit/telemetry bắt buộc dù login thành công sớm | Tổ chức bên ngoài stack hoặc cơ chế đảm bảo audit riêng | `optional` đứng sau `sufficient` có thể không chạy login() |
| Nhiều nguồn identity trong cùng phiên | Stack có quy tắc identity binding rõ | Một Principal pass không có nghĩa user của các module khác là một người |

Không có flag nào tự giải quyết authorization, MFA phishing resistance hoặc credential storage. Đây chỉ là **control-flow và aggregation của nhiều LoginModule**.

## 11. Test matrix trước khi đưa cấu hình vào production

Không chỉ test “password đúng” và “password sai”. Ít nhất nên có:

1. **Một required fail, optional/sufficient khác pass:** toàn stack phải fail.
2. **Requisite fail giữa stack:** module phía sau không được gọi trong login phase; state tạm được dọn.
3. **Sufficient pass trước mandatory:** chứng minh các mandatory phía sau **bị skip**, kiểm xem đây có phải policy mong muốn.
4. **Sufficient pass sau mandatory pass:** skip phần không còn cần thiết, vẫn trả pass.
5. **Sufficient fail rồi required pass:** fallback hợp lệ nếu business rule cho phép.
6. **Chỉ optional, ít nhất một pass:** pass.
7. **Chỉ optional, tất cả fail/ignore:** fail.
8. **Required pass, optional fail:** pass — với module bảo mật quan trọng, đây có thể là lỗ hổng policy.
9. **Hai factor đều required, OTP sai:** fail và không cấp principal MFA.
10. **OTP bị cấu hình optional:** test phải phát hiện nếu yêu cầu MFA bắt buộc.
11. **Login succeeded, commit module sau thất bại:** abort/cleanup các state/Principal đã thêm đúng.
12. **Login failed ở module cuối:** không còn token, password buffer, session hoặc Principal bị rò qua retry.
13. **Logout sau success:** chỉ gỡ credential/Principal do đúng module thêm; không xóa dữ liệu thuộc module khác.
14. **CallbackHandler thiếu callback:** fail đúng chính sách, không ngầm trả true hoặc chấp nhận dữ liệu null.
15. **Hai module xác thực identity khác nhau:** reject hoặc rõ ràng map identity theo chính sách, không cộng quyền tùy ý.
16. **Config name sai/`other` fallback:** không vô tình dùng realm yếu.
17. **Config order thay đổi/rollout:** snapshot test bảo đảm policy mạnh không bị làm yếu vì reorder.
18. **Concurrency:** không chia sẻ mutable `LoginContext`/`LoginModule`/static sharedState giữa phiên độc lập.
19. **Timeout/upstream unavailable:** không chuyển mandatory module thành optional tự động.
20. **Audit/logging:** tất cả đường success/failure/short-circuit có record sự kiện đủ điều tra, không lộ secret.

**Bảo mật của stack là bảo mật của mọi đường đi có thể thành công**, không chỉ cấu hình nhìn “có required ở vài dòng”. Một `sufficient` thành công quá sớm có thể tạo đường đăng nhập không thực hiện yếu tố bắt buộc ở cuối.

## 12. Các sai lầm thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “`required` fail thì Java dừng ngay.” | Không; nó tiếp tục module phía sau nhưng kết quả toàn stack cuối cùng fail. |
| “`requisite` giống `required` hoàn toàn.” | Cả hai mandatory, nhưng requisite fail **dừng login phase ngay**. |
| “`sufficient` pass luôn thắng, kể cả required trước đó fail.” | Không; prior mandatory failure vẫn khiến tổng thể fail. |
| “Một `required` ở cuối file sẽ luôn chạy.” | Có thể không: `sufficient` thành công trước đó có thể short-circuit. |
| “`optional` không ảnh hưởng gì.” | Optional success có thể tạo tổng thể pass khi không có mandatory; nó cũng có thể thêm Principal khi commit đúng. |
| “Tất cả optional fail cũng cho qua.” | Không; nếu không có mandatory, phải có ít nhất một optional/sufficient success. |
| “OTP optional là MFA bắt buộc vì ứng dụng hiển thị ô nhập OTP.” | Sai; required password pass đủ làm toàn stack pass nếu OTP optional fail. |
| “`LoginModule.login` trả false và ném `LoginException` giống nhau.” | Không; `false` là ignored theo contract, exception báo failure. |
| “Ngay khi module pass thì ghi role vào Subject luôn.” | Nên đợi commit sau tổng thể pass, tránh publish identity từ stack thất bại. |
| “`Subject` chứa admin Principal là có quyền admin.” | Không; quyền phải dựa vào policy, nguồn Principal đáng tin và authorization. |
| “`sufficient` short-circuit nên không cần abort/commit nữa.” | Phase login dừng sớm nhưng lifecycle xử lý trạng thái vẫn cần đúng. |
| “`requisite` fail thì cleanup không chạy.” | Sai: abort phase vẫn có trách nhiệm dọn state. |
| “Các module dùng chung sharedState nên có thể tin mọi key trong đó.” | Không; cần kiểm provenance, scope và identity binding. |
| “Global static list trace dùng được trong multi-user server.” | Không; demo chạy tuần tự, production cần trace theo request/login context. |
| “Chỉ cần đặt `required` cho nhiều module là bảo vệ MFA khỏi phishing.” | Không; còn phụ thuộc loại factor, tính chống phishing, replay, session binding và chính sách. |
| “Thay config không phải thay code nên không cần security review.” | Sai; chỉ reorder/đổi flag có thể thay đổi toàn bộ login policy. |

## 13. Câu hỏi tự kiểm tra

**1.** `required` và `requisite` khác nhau ở điểm nào khi fail?  
**Đáp:** Cả hai làm tổng thể fail; required **tiếp tục** module phía sau, requisite **dừng ngay phase login**.

**2.** Một `required` trước đó đã thất bại, sau đó `sufficient` thành công. Có cho login không?  
**Đáp:** Không. Prior mandatory failure chưa được xóa, tổng thể vẫn fail.

**3.** Một `sufficient` thành công đứng trước `required`. Module required phía sau có chạy không?  
**Đáp:** Không trong phase login nếu sufficient short-circuit hợp lệ. Vì vậy placement có thể tạo bypass.

**4.** Có hai module `optional`; một fail, một pass. Tổng thể ra sao khi không có mandatory?  
**Đáp:** Pass vì có ít nhất một module xác thực thành công.

**5.** Cả hai optional đều fail/ignored, không có required/requisite; có thành công không?  
**Đáp:** Không; thiếu bất kỳ thành công nào.

**6.** Password required pass nhưng OTP optional fail, ứng dụng có thể login thành công không?  
**Đáp:** Có; đó là lý do không dùng optional cho yếu tố MFA bắt buộc.

**7.** `commit()` được dùng để làm gì?  
**Đáp:** Hoàn tất các identity/credential của module đã thành công sau khi **tổng thể** login phase đạt điều kiện.

**8.** `abort()` khi nào được gọi?  
**Đáp:** Khi quy trình xác thực tổng thể fail hoặc cần rollback trạng thái; nó xóa state tạm và các thay đổi phải hủy theo contract.

**9.** `CallbackHandler` và `sharedState` khác nhau thế nào?  
**Đáp:** Handler là giao diện yêu cầu/cung cấp input, sharedState là map trao đổi state **giữa các module cùng LoginContext**.

**10.** `LoginContext.logout()` nên làm gì với `Subject`?  
**Đáp:** Các module dọn Principal/credential do **chính module đó thêm**, không xóa tài nguyên của module khác.

**11.** Nếu một module xác thực user A và module khác xác thực user B, đều pass, có nên ghép quyền?  
**Đáp:** Không. Phải ràng buộc đúng cùng identity/session và áp dụng policy authorization.

**12.** Vì sao một cấu hình JAAS thay đổi từ `required` sang `optional` phải được review bảo mật?  
**Đáp:** Vì đó là thay đổi điều kiện thành công của login; có thể biến một yếu tố bắt buộc thành không bắt buộc.

## Tổng kết

```text
required  = bắt buộc, fail vẫn tiếp tục login() module sau
requisite = bắt buộc, fail dừng login() ngay
sufficient= không bắt buộc; pass có thể dừng sớm nếu
            không có required/requisite failure trước đó
optional  = không bắt buộc; luôn tiếp tục module sau

Nếu không có required/requisite:
    cần ít nhất một sufficient/optional thành công

JAAS authentication lifecycle:
    login() các module theo config order
                |
       aggregate flags/result
        /                \
     success             failure
       |                    |
     commit()             abort()
       |
     Subject/Principal
       |
     logout()

Bảo mật phụ thuộc vào:
    flags + THỨ TỰ + identity binding + cleanup + policy.
```

**Kết luận:** bốn control flags không chỉ là nhãn mô tả “mức quan trọng” của từng module; chúng quyết định **đường đi của toàn bộ quy trình đăng nhập**. `REQUIRED` và `REQUISITE` dùng cho điều kiện bắt buộc, `SUFFICIENT` thể hiện cơ chế có thể **đủ để dừng sớm**, còn `OPTIONAL` không thể thực thi một yếu tố MFA bắt buộc. Muốn đúng, phải **test các nhánh thành công/thất bại và thứ tự module**, không chỉ đọc một dòng cấu hình.

## Tài liệu tham khảo chính thức

- [Java SE 17 — Configuration API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): định nghĩa chính xác bốn flags, quy tắc tổng hợp và thứ tự module.
- [Java SE 17 — AppConfigurationEntry.LoginModuleControlFlag](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.LoginModuleControlFlag.html): các hằng `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL`.
- [Java SE 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): stacked authentication, `login`, `getSubject`, `logout`, cấu hình và CallbackHandler.
- [Java SE 17 — LoginModule API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): `initialize`, `login`, `commit`, `abort`, `logout`.
- [Oracle — JAAS LoginModule Developer's Guide (Java 17)](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): hai phase, giá trị return, cleanup và Subject.
- [Java SE 17 — Subject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): Principal/credentials và vòng đời subject.
- [Java SE 17 — NameCallback / PasswordCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/package-summary.html): callback framework và handling dữ liệu đăng nhập.

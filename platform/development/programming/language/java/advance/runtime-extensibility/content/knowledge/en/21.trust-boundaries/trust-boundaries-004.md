# Security Manager được đánh dấu loại bỏ từ JDK 17 và vô hiệu vĩnh viễn từ JDK 24

**Java Security Manager** từng cung cấp mô hình kiểm tra quyền bằng `Permission`, `Policy`, `AccessController` và các phương thức `SecurityManager.check...`. Một số ứng dụng cũ dùng nó để hạn chế thao tác file, mạng hoặc hành động nhạy cảm của đoạn mã được nạp động. Tuy nhiên, cách tiếp cận đó không còn là nền tảng phù hợp cho bảo mật Java hiện đại.

Hai mốc cần phân biệt **chính xác**:

- **JDK 17 — JEP 411:** `SecurityManager` và những API liên quan được **đánh dấu deprecated for removal** (dự kiến loại bỏ trong một bản Java tương lai). Đây **không** phải thời điểm API bị xóa khỏi JDK hay Security Manager bị vô hiệu hóa vĩnh viễn.
- **JDK 24 — JEP 486:** Security Manager **bị vô hiệu hóa vĩnh viễn**. Không thể bật từ lệnh khởi động, không thể cài bằng `System.setSecurityManager(...)`, và API bảo mật liên quan có hành vi đã được sửa đổi. **API vẫn hiện diện trong JDK 24, nhưng được dự kiến xóa trong phiên bản tương lai.**

**Đối với runtime extensibility:** Nếu ứng dụng cho phép chạy plugin, script, mã Java được biên dịch động hoặc class nạp bằng `URLClassLoader`, **không thể lấy Security Manager làm ranh giới cô lập mã không tin cậy trên JDK 24**. Thay vào đó cần mô hình quyền nghiệp vụ tường minh và, với mã không tin cậy, **cô lập bằng tiến trình/container/VM cùng kiểm soát quyền ở hệ điều hành và kênh giao tiếp**.

Bài này đi từ ý nghĩa lịch sử, thay đổi API thực tế, ví dụ Java 17/24 đến cách kiểm kê và di chuyển kiến trúc một cách an toàn.

## 1. Security Manager từng kiểm soát điều gì?

Trong mô hình cũ, Java có các lớp liên quan như:

| Thành phần | Vai trò trước đây |
|---|---|
| `java.lang.SecurityManager` | Điểm kiểm tra chính sách khi các thư viện Java thực hiện một số thao tác nhạy cảm |
| `java.security.Permission` | Biểu diễn một loại quyền như đọc file hoặc kết nối mạng |
| `java.security.Policy` | Cung cấp tập quyền áp dụng cho mã/nguồn code |
| `java.security.ProtectionDomain` | Tập hợp thông tin miền bảo vệ của class, code source và permissions |
| `java.security.AccessController` | Thực hiện một số kiểm tra quyền và hoạt động trong security context |
| `java.security.AccessControlContext` | Biểu diễn ngữ cảnh kiểm tra quyền |
| `java.security.AccessController.doPrivileged(...)` | Trước đây liên quan cách đánh giá stack-based access control |

Một sơ đồ khái niệm của **mô hình lịch sử**:

```text
Plugin / script / Java library
              |
     gọi thao tác nhạy cảm
              |
              v
    Java Platform API
              |
    [nếu Security Manager được bật
     và API thực sự gọi kiểm tra]
              |
              v
SecurityManager / AccessController
              |
              v
   Policy + Permission + context
       /                    \
    cho phép             từ chối
      |                     |
 thao tác tiếp tục     SecurityException
```

Đây chỉ là sơ đồ cơ chế thời kỳ Security Manager còn được hỗ trợ. Nó **không có nghĩa mọi thao tác của mọi thư viện hoặc native code đều đi qua Security Manager**, và không nên coi việc “có Security Manager” là bảo chứng cô lập hoàn toàn. Tính hiệu lực phụ thuộc API nào có kiểm tra và quyền của mã thực thi.

Với mã không tin cậy, hai vấn đề quan trọng xuất hiện:

1. Security Manager hoạt động **bên trong cùng JVM** và phải duy trì một mô hình kiểm tra rất rộng, khó bao phủ mọi API mới và luồng truy cập bên ngoài JDK.
2. Quyền truy cập thực tế của mã còn chịu ảnh hưởng hệ điều hành, native library, process identity, cấu hình JVM và nhiều service đã được cấp quyền.

Việc deprecated rồi vô hiệu hóa là quyết định ở cấp **nền tảng Java**, không đồng nghĩa Java bỏ các API mật mã, TLS hoặc xác thực. `JCA`, `JSSE`, `KeyStore`, kiểm soát quyền OS và cơ chế phân quyền ứng dụng vẫn tồn tại và phục vụ mục đích khác.

## 2. Timeline: deprecated ở JDK 17 khác disabled ở JDK 24

| Giai đoạn | Trạng thái Security Manager | Hệ quả thực tế |
|---|---|---|
| Trước JDK 17 | Security Manager là cơ chế cũ có các API policy/permission | Một số ứng dụng triển khai việc cài manager hoặc dùng policy file |
| **JDK 17** | **JEP 411**: deprecated for removal | Code dùng API này nhận cảnh báo deprecation; một số đường bật manager thời kỳ chuyển tiếp còn được hỗ trợ theo quy tắc của bản JDK |
| JDK 17–23 | Giai đoạn chuyển tiếp, hỗ trợ cũ bị hạn chế và cảnh báo; hành vi bật động phụ thuộc phiên bản/cấu hình | Nên kiểm kê và loại phụ thuộc, không xây tính năng sandbox mới trên API cũ |
| **JDK 24** | **JEP 486**: permanently disabled | Không thể kích hoạt/cài manager; các lời gọi legacy có hành vi mới xác định |
| Các bản tương lai | API Security Manager được lên kế hoạch **loại bỏ** | Code còn phụ thuộc tên kiểu/phương thức có nguy cơ không biên dịch được |

### 2.1. “Deprecated for removal” chính xác là gì?

Trong API Java 17, `java.lang.SecurityManager` được đánh dấu:

```java
@Deprecated(since = "17", forRemoval = true)
public class SecurityManager {
    // Khai báo minh họa dạng annotation.
}
```

Đây là **minh họa annotation**, không phải bản khai báo đầy đủ của class JDK và không dùng làm mã ứng dụng. Ý nghĩa của `forRemoval = true`: API đã được đánh dấu để loại bỏ trong tương lai, trình biên dịch/công cụ có thể cảnh báo ở thời điểm sử dụng. Nó **không** có nghĩa class lập tức biến mất hoặc mọi chương trình JDK 17 gọi nó đều gặp lỗi lúc biên dịch.

Ở JDK 17, vẫn có giai đoạn cho phép bật Security Manager trong những điều kiện lịch sử phù hợp, đồng thời phát cảnh báo. Những cơ chế chuyển tiếp đó **không phải hợp đồng bền vững** để dùng tiếp trên Java 24.

### 2.2. “Permanently disabled” chính xác là gì?

Từ JDK 24:

- **Không bật Security Manager lúc khởi động.** Những tùy chọn cố bật/cho phép nó khiến JVM **không khởi động**, chứ không chỉ in warning.
- **Không cài Security Manager trong runtime.** `System.setSecurityManager(...)` ném `UnsupportedOperationException`, kể cả khi truyền `null`.
- `System.getSecurityManager()` luôn trả `null`.
- Nhiều phương thức trong các class security-policy cũ trả giá trị mặc định, đi qua lời gọi, hoặc ném exception theo quy tắc JEP 486; không còn thực thi mô hình stack-based permission checks như trước.
- Các JDK API từng tham chiếu vào Security Manager để có thể chặn thao tác nhạy cảm nay thường **không thực hiện kiểm tra Security Manager đó**. Vì thế việc ứng dụng còn giữ một `Policy` hoặc gọi `doPrivileged` không tạo ra sự cô lập.
- Tệp policy hệ thống `$JAVA_HOME/conf/security/java.policy` được loại khỏi cấu hình JDK 24; những property chính sách Security Manager liên quan không còn được hỗ trợ như trước.

**Đừng nhầm disabled với removed:** Một API có thể vẫn biên dịch nhưng đã mang hành vi vô dụng hoặc khác trước. Điều đó nguy hiểm hơn lỗi biên dịch rõ ràng nếu ứng dụng tưởng rằng “không thấy exception” nghĩa là các quyền vẫn được kiểm tra.

## 3. Bảng hành vi API trọng yếu trên JDK 24

| API hoặc cơ chế | Hành vi từ JDK 24 | Ý nghĩa khi nâng cấp |
|---|---|---|
| `System.getSecurityManager()` | Luôn `null` | Các nhánh `if (sm != null)` không chạy |
| `System.setSecurityManager(...)` | Luôn ném `UnsupportedOperationException` | Không thể cài custom manager, kể cả để gỡ bằng `null` |
| Khởi động `-Djava.security.manager=allow` hoặc tùy chọn bật tương tự | JVM báo lỗi khởi tạo và thoát | Không còn chế độ opt-in Security Manager |
| `AccessController.doPrivileged(...)` | Thực thi action trực tiếp như khi không có Security Manager | Không tạo giới hạn quyền hay sandbox |
| `AccessController.checkPermission(...)` | Ném `AccessControlException` | Không còn là cơ chế kiểm tra quyền nghiệp vụ hợp lệ |
| `SecurityManager.check...(...)` | Các phương thức kiểm tra cũ ném `SecurityException` khi gọi trực tiếp | Không suy luận rằng JDK vẫn tự gọi chúng để bảo vệ filesystem/network |
| `java.security.Policy.setPolicy(...)` | Ném `UnsupportedOperationException` | Không thể thay policy để kích hoạt kiểm soát cũ |
| `Policy.getPolicy()` | Policy với các phép kiểm tra quyền không cấp quyền | Không có nghĩa JDK đang từ chối thao tác OS dựa trên policy |
| Các lời gọi JDK từng hỏi Security Manager | Không còn gọi kiểm tra theo mô hình cũ | Cần policy kiểm soát khác ở ranh giới tin cậy |

**Chi tiết dễ nhầm:** Việc gọi trực tiếp `AccessController.checkPermission(...)` hoặc `SecurityManager.checkPermission(...)` có thể **ném lỗi ngay cả khi một thao tác đọc file thông thường vẫn thành công**. Vì vậy không thể dùng kết quả của phương thức kiểm tra thủ công để kết luận JVM đang thực thi policy Security Manager lên mọi API.

### 3.1. Vì sao các nhánh legacy có thể im lặng chạy tiếp?

Một mẫu code cũ:

```java
// Ví dụ về code cũ; KHÔNG khuyến nghị cho ứng dụng mới.
@SuppressWarnings("removal")
static void oldCheck() {
    SecurityManager manager = System.getSecurityManager();
    if (manager != null) {
        manager.checkRead("/opt/data/report.csv");
    }
}
```

Đây là **phương thức minh họa**, không phải chương trình độc lập. Trên JDK 24, `System.getSecurityManager()` luôn `null` nên `manager.checkRead(...)` **không được gọi**. Code tiếp tục chạy mà không có kiểm soát quyền tương ứng. Tương tự, những đoạn chỉ bọc logic trong `AccessController.doPrivileged(...)` không tạo ra sự phân quyền; action đơn giản được thực thi.

Đừng sửa đoạn trên bằng cách bỏ điều kiện rồi gọi `new SecurityManager().checkRead(...)`: việc gọi check thủ công trên JDK 24 không biến nó thành bộ lọc chính sách và có thể chỉ ném exception vô điều kiện. **Giải pháp đúng là thiết kế lại quyền ở tầng host/OS.**

### 3.2. Tùy chọn khởi động trên JDK 24

Lệnh sau **không nên còn xuất hiện trong quy trình khởi động**:

```bash
java -Djava.security.manager=allow -jar app.jar
```

Từ JDK 24, khi JVM được yêu cầu bật hoặc cho phép Security Manager, kết quả là lỗi khởi tạo VM, ví dụ phần đầu thông báo:

```text
Error occurred during initialization of VM
java.lang.Error: A command line option has attempted to allow or enable the Security Manager. Enabling a Security Manager is not supported.
```

Đây là đoạn thông báo minh họa, không bao gồm stack trace vốn có thể đổi theo bản JDK. Hệ thống giám sát phải xem đây là **lỗi khởi động**, không tự retry vô hạn cùng cấu hình hoặc nghĩ rằng chỉ là warning có thể tắt.

## 4. Ví dụ Java 17+ dùng để kiểm tra ứng dụng legacy trên JDK 24

Để quan sát đúng hành vi thay đổi, chương trình sau thực hiện hai việc: đọc trạng thái và **thử gọi API cài manager cũ**. Đây chỉ là **mã kiểm thử di trú**, không phải code nên đưa vào đường xử lý production.

Lưu tên **`LegacySecurityManagerProbe.java`**:

```java
public final class LegacySecurityManagerProbe {

    @SuppressWarnings("removal")
    public static void main(String[] args) {
        System.out.println(
                "feature=" + Runtime.version().feature());

        System.out.println("manager="
                + (System.getSecurityManager() == null
                   ? "null" : "present"));

        try {
            System.setSecurityManager(null);
            System.out.println("set=accepted");
        } catch (UnsupportedOperationException exception) {
            System.out.println("set=UnsupportedOperationException");
        }
    }
}
```

Biên dịch theo Java 17 với JDK có hỗ trợ `--release 17`, rồi **chạy bằng JDK 24**:

```bash
javac --release 17 LegacySecurityManagerProbe.java
java LegacySecurityManagerProbe
```

Stdout đã được kiểm tra trên **JDK 24**:

```text
feature=24
manager=null
set=UnsupportedOperationException
```

**Cách đọc kết quả:**

- `feature=24` đến từ `Runtime.version().feature()`: cho biết major feature version đang chạy. Nếu chạy bản Java khác, con số thay đổi.
- `manager=null`: trên JDK 24 không tồn tại một Security Manager đang hoạt động. Điều này không có nghĩa JVM đã bật một chính sách mặc định để chặn mọi hoạt động.
- `set=UnsupportedOperationException`: `System.setSecurityManager(null)` bị từ chối. Đây là thay đổi behavior do JEP 486, không phải lỗi phân quyền của một policy file cụ thể.
- `@SuppressWarnings("removal")` chỉ nhằm tránh cảnh báo khi **biên dịch ví dụ kiểm thử legacy**; nó không kích hoạt Security Manager, không thay runtime behavior và **không nên** được dùng để che nợ kỹ thuật ở code production.

**Phạm vi áp dụng:** ví dụ này chỉ có ý nghĩa khi API legacy còn hiện diện, như trên JDK 17–24. Khi chạy trên JDK 17–23, `System.setSecurityManager(null)` có thể hành xử theo quy tắc/kích hoạt tương ứng của phiên bản đó, nên **không yêu cầu stdout giống JDK 24**. Khi API bị loại bỏ trong một bản tương lai, nguồn dùng chúng sẽ cần sửa thay vì tiếp tục dùng đoạn probe.

## 5. Vì sao điều này đặc biệt quan trọng với plugin, script và mã biên dịch động?

### 5.1. ClassLoader không phải sandbox

`URLClassLoader`, class loader tùy chỉnh và `ModuleLayer` giúp JVM quản lý **không gian tên class, quan hệ loader, module readability và lifecycle**. Chúng không tự tạo hạn mức filesystem, network, process creation hoặc quyền hệ điều hành.

Nếu một plugin được nạp vào cùng JVM và có thể gọi host Java APIs, nó thường chạy dưới **process identity** của ứng dụng. Chỉ tạo child class loader không ngăn plugin:

- Đọc file mà tiến trình Java có quyền đọc.
- Gửi kết nối tới endpoint mà tiến trình Java được mạng cho phép.
- Gọi `System.exit(...)` hoặc tạo thread tiêu thụ CPU, nếu không có kiểm soát độc lập.
- Tiếp cận service/secret mà classpath và capability của tiến trình cho phép.
- Dùng các đường Java/native khác ngoài những interface plugin mà ứng dụng dự định công bố.

**JPMS `exports`/`opens` và class loader delegation không tương đương chính sách quyền OS.** Các công cụ này hữu ích để tổ chức module và quản lý tương thích, nhưng không phải cơ chế thay thế Security Manager để thực thi mã không tin cậy.

### 5.2. ScriptEngine, JShell và runtime compiler không bảo vệ quyền truy cập

Các API như `javax.script.ScriptEngine`, `jdk.jshell.JShell` và `javax.tools.JavaCompiler` phục vụ **đánh giá script, tương tác code và biên dịch**. Chúng không tự bảo đảm rằng code nhận từ người dùng chỉ có thể đọc những gì được phép.

- `JavaCompiler` tạo bytecode, không khiến bytecode ấy an toàn khi chạy.
- `ScriptEngine` có thể expose Java host objects/class lookup tùy engine. `Bindings.put("api", facade)` chỉ xác định những object host chủ động cung cấp, chưa chứng minh engine ngăn các đường host interop khác.
- `JShell` là công cụ thực thi/snippet evaluation, không nên coi nó là bộ lọc quyền thay Security Manager.
- Một plugin dùng cùng JVM có thể giữ static state, singleton, thread và tài nguyên của tiến trình, làm “quyền hạn tối thiểu” theo một interface là chưa đủ.

Nếu script do đội ngũ phát triển kiểm soát và xem như mã tin cậy, một **API facade nhỏ** là phương pháp thiết kế tốt. Nếu script hoặc plugin đến từ bên không tin cậy, cần **đường chạy ngoài process** hoặc môi trường sandbox có bằng chứng bảo vệ thật, với policy OS/network.

### 5.3. Các kiểu lỗi điển hình sau nâng cấp

| Biểu hiện | Nguyên nhân cần kiểm tra |
|---|---|
| JVM không khởi động khi nâng lên JDK 24 | Script launch/manifest/container còn yêu cầu bật Security Manager |
| `System.setSecurityManager(...)` gây `UnsupportedOperationException` | API cũ đã bị vô hiệu vĩnh viễn |
| Code `if (getSecurityManager() != null)` không gọi kiểm tra nữa | Getter luôn `null` |
| Gọi `AccessController.checkPermission` luôn gặp lỗi | Đã thay đổi thành kiểm tra không còn phù hợp trong mô hình runtime |
| Đoạn `doPrivileged` vẫn chạy bình thường | Không có Security Manager để thay đổi đánh giá permission; không suy ra có bảo vệ |
| Policy file vẫn tồn tại trong dự án nhưng không có tác dụng mong đợi | Cơ chế Security Manager policy không còn thực thi |
| Plugin “bị cách ly” bằng class loader nhưng vẫn đọc được file | Class loader không giới hạn quyền hệ điều hành |
| Test chỉ chạy trên Java 17 thành công nhưng Java 24 lỗi | Test migration chưa bao phủ launch flags, API behavior và threat model |

## 6. Thay thế bằng những cơ chế nào?

**Không có một API trong JDK thay thế trực tiếp 1:1 cho toàn bộ Security Manager.** Cơ chế phù hợp phụ thuộc mục đích thật sự của việc dùng Security Manager trước đây.

| Mục đích cũ | Cách thiết kế hiện nay | Giới hạn cần nhớ |
|---|---|---|
| Kiểm tra ai được xem/sửa dữ liệu | Authentication + authorization tại API/service/database | Phải kiểm tra lại theo actor/tenant và thao tác |
| Plugin tin cậy gọi chức năng của host | Interface/capability tối thiểu, allowlist provider, audit | Không tự bảo vệ khỏi plugin độc hại chạy cùng JVM |
| Chạy script hoặc mã Java **không tin cậy** | Tiến trình/container/VM cô lập, OS permissions và resource quotas | Container phải được cấu hình thực chất, không mặc định bất khả xâm phạm |
| Ngăn truy cập file tùy ý | User/namespace riêng, mount chỉ đọc hoặc không mount, quyền filesystem | Chỉ kiểm Java `Path` ở UI không đủ |
| Ngăn kết nối tới mạng nội bộ | Network namespace, egress policy, firewall và proxy/gateway | Phải kiểm tra cả DNS, redirect và endpoint metadata |
| Hạn chế CPU/RAM/fork | cgroups/OS process limits/timeout, giới hạn số process | `Thread.interrupt()` không dừng chắc mọi mã độc |
| Giới hạn tác vụ nhạy cảm | Gateway nhận operation ID được phép, schema validation, quota | Không mở endpoint gọi reflection/class/method tùy ý |
| Theo dõi thao tác thay vì kiểm soát quyền | Logging/observability, tracing hoặc instrumentation có kiểm soát | Quan sát không tự biến thành cơ chế sandbox |
| Bảo vệ kênh truyền và bí mật | TLS/mTLS, keystore, secrets management và JCA | Không liên quan quyền thực thi của bytecode không tin cậy |

**Phân lớp theo mức độ tin cậy:**

1. **Mã host tin cậy**: áp dụng secure coding, quyền OS tối thiểu, authz tại ranh giới nghiệp vụ, dependency và supply-chain checks.
2. **Plugin đã được duyệt nội bộ**: dùng SPI ổn định, API facade/capabilities, version pinning, review và quy trình nâng cấp; coi như mã có quyền của process trừ khi có cô lập thêm.
3. **Mã script hoặc plugin của đối tác chưa tin cậy hoàn toàn**: đưa thao tác có quyền qua gateway, giới hạn engine host access và cân nhắc chạy ngoài process.
4. **Mã người dùng không tin cậy**: chạy trong worker process/container/VM riêng, uid không đặc quyền, filesystem/mạng/secrets hạn chế, timeout và quotas. Không dùng class loader hoặc một “SecurityManager giả” làm ranh giới duy nhất.

## 7. Ví dụ Java 17 thay cách kiểm tra bằng quyền nghiệp vụ tường minh

Trong ứng dụng cũ, một số tác giả có thể nghĩ rằng `SecurityManager` sẽ chặn script đọc báo cáo của người khác. Nhưng **phân quyền nghiệp vụ** nên được thực thi ở chính service/gateway, không dựa vào trạng thái toàn cục của Security Manager.

Ví dụ sau chỉ làm rõ **hợp đồng truy cập**. Nó không thực thi script và không có tham vọng tạo sandbox cho mã độc; caller chưa tin cậy vẫn phải kết nối qua ranh giới process/gateway được bảo vệ.

Lưu tên **`CapabilityBoundaryDemo.java`**:

```java
import java.util.Set;

public final class CapabilityBoundaryDemo {

    enum Operation {
        READ_REPORT,
        EXPORT_REPORT
    }

    record AccessContext(String tenant, Set<Operation> grants) {}

    record ReportRecord(String tenant, String content) {}

    static String readReport(
            AccessContext context, ReportRecord report) {

        if (!context.grants().contains(Operation.READ_REPORT)
                || !context.tenant().equals(report.tenant())) {
            throw new SecurityException("DENIED");
        }
        return report.content();
    }

    public static void main(String[] args) {
        AccessContext context = new AccessContext(
                "team-a", Set.of(Operation.READ_REPORT));

        System.out.println("own=" + readReport(
                context, new ReportRecord("team-a", "report-1")));

        try {
            readReport(
                    context, new ReportRecord("team-b", "private"));
        } catch (SecurityException exception) {
            System.out.println("other=" + exception.getMessage());
        }

        System.out.println("exportGranted="
                + context.grants().contains(
                        Operation.EXPORT_REPORT));
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac --release 17 CapabilityBoundaryDemo.java
java CapabilityBoundaryDemo
```

Stdout đã được kiểm tra:

```text
own=report-1
other=DENIED
exportGranted=false
```

**Giải thích:**

- Host cấp `READ_REPORT` cho tenant `team-a`, nên chỉ đọc được bản ghi thuộc tenant đó.
- Đọc báo cáo của `team-b` bị từ chối với lỗi `DENIED`.
- Không có grant `EXPORT_REPORT` nên quyền export không được cấp.
- Không có lời gọi `SecurityManager`, `AccessController` hay policy file; kiểm tra nằm ngay trong thao tác nghiệp vụ.

**Không hiểu sai mô hình bảo vệ:** Đây là ví dụ giới hạn hành động **cho caller phải đi qua `readReport`**. Nếu mã không tin cậy được chạy **bên trong cùng JVM**, nó vẫn có thể tìm một đường khác tới dữ liệu hoặc API tùy khả năng truy cập của môi trường. Vì thế trong sản phẩm thực, `AccessContext` phải được host khởi tạo từ danh tính đã xác thực và **không** được script tự tạo rồi coi là đáng tin; thao tác đọc phải đi qua một gateway/repository đã enforce ACL, và với mã không tin cậy cần thêm cô lập process/OS.

Để production-grade, nên dùng authn/authz thật, bảo vệ tenant scope ở truy vấn dữ liệu, audit decisions, giới hạn kích thước/truy vấn, cấm bypass và kiểm thử negative cases. Một record `AccessContext` trong code demo chỉ là biểu diễn dễ hiểu, không phải cơ chế chứng thực.

## 8. Kiến trúc tham khảo khi cần chạy plugin hoặc script không tin cậy

Một kiến trúc có thể phân tách việc **thực thi mã** với **truy cập quyền của host**:

```text
Client / tenant
      |
      v
Host API: authn + authz + quota
      |
      +--> Tạo execution request (script, inputs, run ID)
                    |
                    v
          Sandbox worker process
           - uid không đặc quyền
           - không mount secrets/host FS
           - network egress mặc định đóng
           - cgroups/CPU/RAM/process limits
           - deadline + kill process khi quá hạn
                    |
                    | IPC (schema cố định, auth context)
                    v
          Host capability gateway
           - allowlist thao tác
           - tenant/actor được host xác thực
           - validate đầu vào
           - phân quyền từng lời gọi
           - rate limit và audit
                    |
                    v
          Java services / database
                    |
                    v
              DTO lọc dữ liệu
```

Trong mô hình này:

- **Script worker không giữ quyền database hoặc secrets của host.** Khi cần công việc được cấp, nó gửi operation nhỏ: `report.read`, `report.list` hoặc `event.emit`.
- **Gateway không chấp nhận tên class/phương thức tùy ý.** Không expose `evalJava`, `invoke(String className, String method)`, `openFile(String path)` hoặc arbitrary URL nếu nghiệp vụ không yêu cầu.
- **Actor/tenant được xác định ở host**. Không tin một trường `tenantId` tự cung cấp trong payload của script.
- **Ranh giới process** cho phép đặt uid, syscall/OS policy, mount, network namespace, RAM/CPU limits và dừng worker khi quá hạn mà không giết JVM host.
- **Kết quả đưa về dạng DTO/JSON giới hạn kích thước**, tránh trả object Java chứa `ClassLoader`, `Connection`, `Path`, `DataSource` hay quyền truy cập rộng hơn.
- **Chấm dứt tiến trình không khôi phục side effects đã commit**. Các operation ghi cần idempotency keys, transaction boundaries, timeout reconciliation và retry policy.
- **Container chỉ là một lớp**: cấu hình privileged, host filesystem mount, token service account hoặc network mở vẫn có thể khiến worker có quyền quá rộng.

### 8.1. Tránh dùng SecurityException sai nghĩa

Ứng dụng Java vẫn có thể **tự ném `SecurityException`** như ví dụ `DENIED` để chỉ lỗi nghiệp vụ; việc class exception còn tồn tại **không có nghĩa Security Manager vẫn hoạt động**. Trong hệ thống API thực, thường nên trả mã lỗi ứng dụng cụ thể như `PERMISSION_DENIED` hoặc `TENANT_SCOPE_VIOLATION`; không dựa vào `java.security.Policy` để xác định grant.

## 9. Kế hoạch chuyển đổi từ Security Manager trên JDK 17–23 sang JDK 24+

Một migration cần kiểm tra cả **cấu hình chạy, Java source, dependency, test và mục đích bảo mật**.

### Bước 1. Kiểm kê các phụ thuộc và giả định

Tìm trong source code và cấu hình:

- `System.setSecurityManager(...)`, `System.getSecurityManager()`, `new SecurityManager()`, custom `SecurityManager` subclass.
- `AccessController.checkPermission(...)`, `AccessController.doPrivileged(...)`, `Policy.setPolicy(...)`, `Policy.getPolicy()`, `AccessControlContext`, `ProtectionDomain.getPermissions()`.
- Cấu hình `-Djava.security.manager`, `-Djava.security.policy`, `java.policy`, startup flags trong container image, scripts, service manager, build/test runners.
- Thư viện dùng Security Manager để chặn `System.exit`, hạn chế file/network, sandbox plugin hoặc chạy code người dùng.
- Thư viện chỉ kiểm tra `getSecurityManager()!=null` để quyết định có gọi check; nhóm này có thể **âm thầm bỏ kiểm tra** trên JDK 24.
- RMI remote class downloading hoặc plugin framework có đường thiết kế từng phụ thuộc Security Manager.

Hãy xác định **lý do** mỗi đường sử dụng Security Manager: bảo vệ dữ liệu, hạn chế I/O, chặn exit, log việc sử dụng API, hay chỉ tương thích thư viện cũ. Không thể thay tất cả bằng một giải pháp duy nhất.

### Bước 2. Dùng công cụ và kiểm thử chuyển tiếp

Trên bản JDK có `jdeprscan` tương thích, có thể quét các class/JAR để tìm tham chiếu đến API đã deprecated for removal:

```bash
jdeprscan --release 17 --for-removal app.jar
```

`jdeprscan` là công cụ **quét API trong bytecode**, không đảm bảo phát hiện đường reflection, config flag, JAR được tải về lúc chạy hoặc script gọi API động. Cần bổ sung code search và inventory dependency. Trên bản JDK 17–23, có thể chạy ứng dụng với tùy chọn `-Djava.security.manager=disallow` để tìm code cố cài manager động; đây là **bài test migration trong giai đoạn chuyển tiếp**, không phải cách khôi phục Security Manager ở JDK 24.

Kiểm tra cả **cách khởi động thật** của dịch vụ: docker entrypoint, systemd, test JVM args, framework flags và CI pipeline. Nếu Java 24 không khởi động do `-Djava.security.manager=allow`, cần sửa cấu hình thay vì suppress error.

### Bước 3. Phân loại và thay thế theo mục đích

- **Application authorization:** chuyển sang kiểm tra tại service/repository/gateway theo actor, resource, action, tenant.
- **Sandbox third-party code:** chuyển workload sang worker process/container/VM với OS resource policy và IPC tối thiểu.
- **Plugin lifecycle:** vẫn dùng `ClassLoader`/`ModuleLayer` để quản lý version/nạp mã, nhưng tách rõ đây không phải security boundary.
- **API interception:** đánh giá static analysis, instrumentation hoặc thiết kế wrapper thay cho SecurityManager hook; công cụ intercept không tự đảm bảo sandbox.
- **DoPrivileged legacy:** xem lại vì sao đặc quyền được yêu cầu; trên JDK 24 action chạy bình thường, không có mô hình privilege escalation theo Security Manager để dựa vào.
- **Testing assumptions:** cập nhật test từng mong đợi `SecurityException` từ thư viện nền tảng khi Security Manager chặn; hành vi nay có thể khác.

### Bước 4. Triển khai an toàn trước khi loại code legacy

1. Thiết kế **threat model**: ai cung cấp mã/script, dữ liệu nào cần bảo vệ, thao tác nào phải bị chặn.
2. Thiết lập ranh giới mới **trước khi** gỡ các kiểm tra Security Manager cũ. Tránh gỡ xong rồi mới nhận ra plugin không tin cậy đã có quyền rộng.
3. Tạo test cho những tình huống bị từ chối: đọc file host, đọc secrets, kết nối tới mạng nội bộ, tạo process, gọi operation không được phép và vượt quota.
4. Chạy thử trên JDK 24 với startup flags đã làm sạch; đo thành công, lỗi API, cảnh báo của dependency và hành vi thực tế của worker sandbox.
5. Ghi nhận audit/log, phân biệt lỗi permission app với lỗi OS, giới hạn lộ thông tin nhạy cảm.
6. Chỉ đưa vào production khi các policy cũ đã có biện pháp tương đương hoặc tốt hơn theo threat model.

## 10. Ma trận kiểm thử đề xuất

| Kiểm thử | Kỳ vọng |
|---|---|
| JDK 17 biên dịch code cũ có `SecurityManager` | Có cảnh báo deprecation for removal theo compiler/option |
| JDK 24 gọi `System.getSecurityManager()` | Luôn `null` |
| JDK 24 gọi `System.setSecurityManager(null)` | Ném `UnsupportedOperationException` |
| JDK 24 dùng `-Djava.security.manager=allow` | JVM lỗi khởi tạo, không chạy ứng dụng |
| JDK 24 gọi `AccessController.doPrivileged` | Action chạy; không tạo permission sandbox |
| JDK 24 gọi `AccessController.checkPermission` | Ném `AccessControlException`, không dùng làm authz mới |
| Ứng dụng dùng `getSecurityManager()!=null` để chặn file | Nhánh kiểm tra không chạy; phải có kiểm soát thay thế |
| Plugin nạp bằng loader riêng cố đọc file host | Loader riêng không phải ranh giới OS; test sandbox tiến trình |
| Script gọi gateway để đọc tenant khác | Gateway từ chối, không trả dữ liệu |
| Worker không tin cậy cố gọi mạng nội bộ | Egress policy chặn ở OS/network |
| Worker quá CPU/time/memory budget | Host hạn chế/kill worker, không làm treo JVM chính |
| Worker bị dừng sau một lệnh ghi | Có chính sách idempotency/reconciliation, không nhân đôi side effect |
| Quét ứng dụng bằng `jdeprscan` | Phát hiện tham chiếu deprecated trong phạm vi bytecode quét |
| Đóng gói JDK runtime image tùy chỉnh | Security model vẫn không dựa vào Security Manager |

Hãy kiểm thử trên đúng hệ điều hành, container runtime và JDK được sử dụng ở production, vì một container sai mount/network policy không thể được sửa bằng Java code gọi `SecurityManager`.

## 11. Các sai lầm phổ biến

1. **“Deprecated ở JDK 17 nghĩa là đã bị xóa.”** Sai: JDK 17 đánh dấu loại bỏ trong tương lai; JDK 24 mới vô hiệu hóa vĩnh viễn.
2. **“Disabled ở JDK 24 nghĩa là đã xóa API.”** Sai: API vẫn tồn tại trong JDK 24 nhưng hành vi đã thay; việc xóa được lên kế hoạch sau.
3. **“Thêm `-Djava.security.manager=allow` sẽ bật lại manager.”** Sai trên JDK 24; JVM không khởi động.
4. **“`System.setSecurityManager(null)` chắc chắn chỉ gỡ manager nên an toàn.”** Sai trên JDK 24: vẫn ném `UnsupportedOperationException`.
5. **“`System.getSecurityManager()==null` nghĩa là tất cả quyền đã bị từ chối.”** Sai: nó chỉ báo không có Security Manager đang hoạt động.
6. **“`AccessController.doPrivileged` đang cung cấp một mức quyền riêng.”** Sai trên JDK 24: action chạy như không có Security Manager.
7. **“Gọi `checkPermission` thủ công đủ để mô phỏng policy trước đây.”** Sai: nhiều method giờ ném lỗi vô điều kiện, không thực thi chính sách quyền cũ.
8. **“`URLClassLoader` hoặc `ModuleLayer` là sandbox đáng tin cậy.”** Sai: đó là công cụ cấu trúc class/module, không hạn chế process/network/OS.
9. **“ScriptEngine/JShell/JavaCompiler tự hạn chế quyền người dùng.”** Sai: chúng phục vụ đánh giá/biên dịch/thực thi theo cơ chế riêng và cần boundary tin cậy.
10. **“Một interface Java nhỏ đảm bảo script độc hại không gọi gì khác.”** Sai nếu engine cho phép host interop hoặc mã chạy chung JVM.
11. **“`SecurityException` còn được ném nghĩa là Security Manager còn hoạt động.”** Sai: ứng dụng/JDK API khác vẫn có thể ném exception vì các lý do riêng.
12. **“Container mặc định tạo isolation đầy đủ.”** Sai: privileged mode, mount, mạng mở và identity có quyền cao có thể phá ý nghĩa của ranh giới.
13. **“Quét bytecode một lần là đủ.”** Sai: cần kiểm tra launch flags, reflection, cấu hình, scripts, plugin được thêm lúc chạy và dependency.
14. **“Giải pháp thay thế Security Manager chỉ là chuyển sang framework auth.”** Framework auth quản lý quyền request/data; nó **không** cô lập mã độc có quyền của tiến trình host.
15. **“Chỉ bỏ các API deprecated là đã an toàn.”** Trước khi bỏ, phải khôi phục/thiết kế các bất biến bảo mật và test negative cases tại đúng boundary.

## 12. Checklist ứng dụng Java 24+ có nạp mã động

- Không còn cố cài/bật `SecurityManager` qua API hay JVM flags.
- Không còn dùng `getSecurityManager()` như điều kiện duy nhất để quyết định có kiểm tra quyền.
- Không dựa vào `java.policy`, `Policy`, `AccessController.checkPermission` hay `doPrivileged` làm cơ chế bảo vệ mới.
- Đã kiểm kê dependency, plugin, script và đường biên dịch/nạp class.
- Đã phân loại mã thành **được tin cậy**, **tin cậy có điều kiện** và **không tin cậy**.
- Đã có capability/authorization tại service/gateway với actor/tenant/grants do host xác thực.
- Đã bảo vệ dữ liệu bằng quyền OS, secrets management, database ACL và network policies phù hợp.
- Nếu chạy mã không tin cậy: worker riêng với uid/FS/network isolation, CPU/RAM/deadline/process limits, chống bypass qua IPC.
- Đã cấm endpoint nhận arbitrary class/method/command nếu không có nhu cầu nghiệp vụ; giới hạn input/output/side effects.
- Đã thử tấn công vượt quyền, timeout, resource exhaustion, giả mạo tenant, retry sau lỗi và upgrade JDK thực tế.
- Đã viết rõ ranh giới bảo mật nào thuộc Java application, ranh giới nào do OS/container/hypervisor thực thi.
- Đã gỡ các test chỉ giả định “Security Manager vẫn bật” và thay bằng kiểm thử các policy thực sự enforce.

### Tài liệu gốc

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [Security Manager Is Permanently Disabled — Java SE 24 Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html)
- [SecurityManager API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html)

**Kết luận:** **JDK 17** đánh dấu Security Manager là API **sắp loại bỏ**; **JDK 24** **vô hiệu hóa vĩnh viễn** cơ chế này, dù API vẫn còn hiện diện để hỗ trợ giai đoạn chuyển đổi. Một hệ thống Java có khả năng nạp plugin hoặc script không thể dựa vào `SecurityManager` để cách ly mã lạ. Cần chuyển sang **quyền nghiệp vụ tường minh**, **capability/gateway có xác thực**, và **cô lập tiến trình/hệ điều hành** khi thực thi mã không tin cậy.
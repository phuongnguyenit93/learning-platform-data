# Security Manager: trạng thái hỗ trợ theo phiên bản và hướng thay thế

Trong Java Advance Compatibility Migration, nhiều ứng dụng cũ sử dụng `SecurityManager` để giới hạn thao tác file, mạng, nạp native library, đọc system property hoặc gọi `System.exit`. Một số application server, hệ thống plugin, công cụ test và thư viện Java còn có code gọi `System.setSecurityManager(...)`, `AccessController.doPrivileged(...)` hoặc đọc file `java.policy`. Các cơ chế từng hoạt động trên JDK 8 hoặc JDK 11 có thể phát cảnh báo trên JDK 17–23 và không còn hoạt động khi chuyển sang JDK 24 trở lên.

**Điểm quan trọng nhất:** Security Manager **không có một API Java SE mới thay thế tương đương 1:1**. Java đã thay đổi định hướng khỏi sandbox quyền chi tiết theo code trong cùng một JVM. Vì vậy cần xác định Security Manager đang bảo vệ tài nguyên gì, code nào được xem là tin cậy, ranh giới nguy cơ ở đâu, rồi chuyển kiểm soát phù hợp sang **hệ điều hành/process, container/VM, quyền file và mạng, cơ chế xác thực/phân quyền ứng dụng, IAM và quản trị phụ thuộc**.

Bài học này trình bày trạng thái theo JDK release, cách nhận diện dependency còn dựa vào Security Manager, các thay đổi về API/option, ví dụ migration và kế hoạch triển khai an toàn. Trọng tâm của chương **Bảo mật và quyền truy cập** là không vô tình làm mất ranh giới bảo vệ khi nâng cấp Java.

## 1. Security Manager từng được dùng để làm gì?

`java.lang.SecurityManager` là cơ chế cũ để kiểm tra quyền trước khi một số API Java thực hiện thao tác nhạy cảm. Khi một Security Manager được kích hoạt, JDK hoặc ứng dụng có thể gọi các phương thức như `checkRead`, `checkWrite`, `checkConnect`, `checkPermission` nhằm cho phép hoặc từ chối thao tác dựa trên policy và context.

Ví dụ cách kiểm tra quyền trong ứng dụng cũ:

~~~java
SecurityManager manager = System.getSecurityManager();
if (manager != null) {
    manager.checkRead("/srv/app/config.yml");
}
~~~

Với mô hình cũ, một ứng dụng có thể dùng:
- `java.security.Permission` và các loại `FilePermission`, `SocketPermission`, `RuntimePermission`.
- `java.security.Policy` và file policy cấp quyền theo code source, signer hoặc protection domain.
- `AccessController.checkPermission` và `AccessController.doPrivileged`.
- System property `java.security.manager` để bật hoặc cho phép cài Security Manager.
- System property `java.security.policy` hoặc file `java.policy` để chỉ định chính sách.

Nhưng mô hình này có các giới hạn kiến trúc: code cùng process/JVM chia sẻ nhiều tài nguyên, API mới cần tích hợp check phù hợp, JNI/native code và những cơ chế runtime khác làm việc dựng một sandbox tin cậy rất khó. Security Manager cũng không phải một lớp kiểm soát cho mọi loại resource access. Do đó, một ứng dụng đã chạy với Security Manager **không mặc nhiên là một sandbox đủ mạnh cho mã không tin cậy**.

### 1.1. Không nhầm Security Manager với những cơ chế bảo mật khác

Các khái niệm sau độc lập với Security Manager:

| Khái niệm | Công dụng | Có phụ thuộc Security Manager không? |
|---|---|---|
| Java Cryptography Architecture (JCA/JCE) | Mã hóa, chữ ký, hash, provider, key | Không cần Security Manager để thực hiện chức năng crypto thông thường |
| TLS/JSSE | Bảo vệ kết nối qua mạng | Không phải một chế độ Security Manager |
| JAAS, Subject, principal | Identity và security context ở API liên quan | Một số API tương tác Security Manager cũ thay đổi; kiểm tra phiên bản |
| Application authorization | Kiểm tra ai được đọc/sửa dữ liệu nghiệp vụ | Do ứng dụng/service thực thi, không thể giao hoàn toàn cho Security Manager |
| JPMS | Modularization và strong encapsulation | Không phải sandbox cho code không tin cậy |
| Container/OS isolation | Giới hạn tài nguyên và đặc quyền của process | Độc lập với Security Manager |
| Dependency integrity | Chọn artifact, chữ ký, checksum, supply chain | Cần cơ chế quản lý build/deployment riêng |

Việc bỏ Security Manager **không có nghĩa bỏ toàn bộ bảo mật Java**. Nó có nghĩa các kiểm tra quyền theo policy cũ của Security Manager không còn là cơ chế có thể dựa vào trong những JDK hiện đại.

## 2. Trạng thái Security Manager theo phiên bản JDK

Trạng thái thay đổi theo từng giai đoạn, nên đừng viết một quy tắc duy nhất áp cho JDK 8, 17 và 24.

| JDK | Trạng thái hỗ trợ | Hệ quả cho migration |
|---|---|---|
| JDK 8 | Security Manager tồn tại và có thể được kích hoạt | Ứng dụng có thể phụ thuộc `java.policy`, custom SecurityManager, `doPrivileged` |
| JDK 9–16 | Vẫn tồn tại; một số cơ chế nền tảng/JPMS thay đổi cách tiếp cận | Cần thử lại policy, module access và thư viện |
| JDK 17 | **Deprecated for removal** theo JEP 411 | Compiler/API cảnh báo; bật hoặc cài manager có cảnh báo runtime |
| JDK 18–23 | Vẫn có giai đoạn hỗ trợ có điều kiện; cài động mặc định bị hạn chế | Không nên dựa vào việc `setSecurityManager` thành công khi không có launch option phù hợp |
| **JDK 24 trở lên** | **Permanently disabled** theo JEP 486 | Không thể bật tại startup hay cài tại runtime; nhiều API liên quan còn tồn tại nhưng đổi semantics hoặc ném exception |

Các bản Java update hoặc JDK vendor có thể có khác biệt về tooling, đóng gói hoặc các tính năng ngoài đặc tả. Khi khảo sát hệ thống, ghi rõ **vendor, major, update/build và JVM runtime thực tế**. Không kết luận theo phiên bản Java trên máy build.

### 2.1. JEP 411 trên JDK 17: cảnh báo và chuẩn bị loại bỏ

JEP 411 đánh dấu Security Manager và các API liên quan là **deprecated for removal** từ JDK 17. Điều này có nghĩa có kế hoạch loại bỏ trong tương lai, **không phải JDK 17 đã xóa class `SecurityManager`**.

Trên giai đoạn JDK 17–23, ứng dụng còn có thể dùng Security Manager trong các điều kiện được runtime hỗ trợ, nhưng nên:
- Nhận diện các use case đang cần policy-based permission checks.
- Tìm mọi vị trí gọi `System.setSecurityManager`, `Policy.setPolicy` hoặc check permission.
- Theo dõi warning ở compile/runtime.
- Kiểm tra runbook và startup option.
- Lập kế hoạch bỏ phụ thuộc trước khi lên JDK 24+.

Trong JDK 17–23, có thể dùng `-Djava.security.manager=disallow` để **thử ứng dụng khi không cho phép cài Security Manager**. Khi code cố cài một manager bằng `System.setSecurityManager`, thử nghiệm có thể phát hiện `UnsupportedOperationException`. Đây là phép thử chuẩn bị migration, không phải giải pháp cho ứng dụng cần sandbox thật.

### 2.2. Cài động và mặc định không giống nhau trên mọi JDK

Một số code cũ gọi:

~~~java
System.setSecurityManager(new SecurityManager());
~~~

Trước kia, hành vi phụ thuộc trạng thái hiện tại và cách JVM được khởi động. Trong các JDK 18–23, nếu không cho phép cài động theo launch configuration, việc cài có thể bị từ chối. Các giá trị của `java.security.manager` như `allow`, `disallow`, `default` có vai trò khác nhau theo release.

**Không di chuyển nguyên launch flags của JDK 17/21 sang JDK 24.** Trên JDK 24+, cách bật hoặc cho phép Security Manager tại startup là lỗi khởi tạo JVM. Không có flag mới nào “bật lại” cơ chế Security Manager đã bị vô hiệu hóa.

### 2.3. JEP 486 trên JDK 24+: vô hiệu hóa vĩnh viễn

Từ JDK 24, Security Manager **bị vô hiệu hóa vĩnh viễn**:
- Khởi động JVM với `-Djava.security.manager` nhằm bật hoặc cho phép manager (ví dụ `allow`, `default` hoặc tên custom class) dẫn đến lỗi khởi động.
- Gọi `System.setSecurityManager(SecurityManager)` sẽ ném `UnsupportedOperationException`.
- `System.getSecurityManager()` luôn trả `null`.
- `AccessController.doPrivileged(...)` thực thi action như khi không có Security Manager, không cấp quyền đặc biệt như cơ chế cũ.
- Các phương thức permission-check nghiêm ngặt như `AccessController.checkPermission` và `SecurityManager.check*` có hành vi luôn từ chối/throw theo API được điều chỉnh.
- `Policy.setPolicy(...)` ném `UnsupportedOperationException`; các cơ chế policy file cho Security Manager không còn ý nghĩa thực thi cũ.
- File system policy `$JAVA_HOME/conf/security/java.policy` không còn thuộc cơ chế cấu hình của JDK theo cách trước.

**Phân biệt “bị vô hiệu hóa” với “API đã được xóa”.** Trong JDK 24/25, nhiều tên class/method deprecated vẫn có thể tồn tại để hỗ trợ linkage của các thư viện cũ, nhưng không còn chức năng Security Manager trước đây. Những API này vẫn có kế hoạch bị loại bỏ trong một bản JDK tương lai. Code compile được nhờ tên class còn tồn tại **không chứng minh chính sách cũ vẫn hoạt động**.

### 2.4. Tác động đến classpath/module path và startup

Ví dụ một script cũ:

~~~bash
java \
  -Djava.security.manager \
  -Djava.security.policy=/opt/app/security/app.policy \
  -jar legacy-app.jar
~~~

Đối với JDK 24+, lệnh này không thể được giữ như một cách kích hoạt policy. Phải tìm mục đích của `app.policy` rồi thay bằng ranh giới quyền khác, đồng thời bỏ flag kích hoạt Security Manager.

Chỉ xóa flag để JVM chạy là **chưa hoàn tất migration bảo mật**. Khi chính sách trước đây cấm đọc file hoặc kết nối ra ngoài, việc bỏ cơ chế đó có thể làm process có nhiều quyền hơn. Cần thay kiểm soát trước hoặc cùng lúc với việc thay runtime.

## 3. Các API và hành vi cần kiểm tra riêng

Bởi nhiều thư viện vẫn gọi Security Manager API, việc hiểu chính xác hành vi từ JDK 24 sẽ giúp phân biệt code “tạm chạy” và code bị phá contract.

| API hoặc cơ chế | Hành vi cần lưu ý từ JDK 24 | Hướng xử lý |
|---|---|---|
| `System.getSecurityManager()` | Luôn trả `null` | Bỏ nhánh kiểm tra Security Manager; không dùng null để suy ra “đã được sandbox” |
| `System.setSecurityManager(...)` | Luôn ném `UnsupportedOperationException` | Loại bỏ logic cài manager và thay cơ chế kiểm soát |
| `AccessController.doPrivileged(...)` | Chạy action trực tiếp theo semantics không có manager | Có thể tồn tại trong thư viện nhưng không mang ý nghĩa cấp quyền cũ |
| `AccessController.checkPermission(...)` | Ném `AccessControlException` | Thay bằng authorization model riêng nếu ứng dụng dùng để kiểm quyền |
| `SecurityManager.checkPermission/check*` | Các check từ đối tượng manager không còn dùng được để thiết kế policy cũ | Bỏ custom checker và chuyển nơi thực thi quyền thích hợp |
| `Policy.setPolicy(...)` | Ném `UnsupportedOperationException` | Không dựa vào Java policy file để tạo sandbox |
| `java.security.policy`, `java.policy` | Không còn điều khiển Security Manager | Chuyển điều khiển tài nguyên sang OS/container/app |
| `Permission/ProtectionDomain` liên quan policy | Một số method trả empty/null/false theo semantics mới | Không dùng chúng làm nguồn quyết định authorization |

Điều cần tránh là tự khái quát rằng “Security Manager API đều no-op”. **Một số method không làm gì, một số trả null/false, nhưng một số ném exception vô điều kiện**. Quy trình migration phải dựa trên API cụ thể và JDK đích.

### 3.1. Idiom “nếu có Security Manager thì kiểm quyền”

Ví dụ trong thư viện cũ:

~~~java
SecurityManager manager = System.getSecurityManager();
if (manager != null) {
    manager.checkPermission(new RuntimePermission("createClassLoader"));
}
~~~

Trên JDK 24+, `getSecurityManager()` luôn trả `null`, nên nhánh kiểm tra không chạy. Nếu thư viện chỉ dùng đoạn này để hợp tác với cơ chế Security Manager tùy chọn, nó có thể tiếp tục hoạt động. Nhưng nếu ứng dụng dựa vào check này như **hàng rào bảo mật chính**, hàng rào đã biến mất.

Không nên “sửa” bằng cách trực tiếp tạo một đối tượng SecurityManager rồi gọi `checkPermission` để ép kiểm tra: semantics của các method này đã thay đổi và không còn là framework phân quyền được hỗ trợ.

### 3.2. Idiom doPrivileged

Code cũ:

~~~java
String value = java.security.AccessController.doPrivileged(
        (java.security.PrivilegedAction<String>)
        () -> System.getProperty("app.mode")
);
~~~

Trong môi trường có Security Manager trước đây, `doPrivileged` tương tác permission-check stack. Trên JDK 24+, action được thực hiện như một lời gọi bình thường.

Nếu chỉ cần đọc system property cho chức năng ứng dụng, có thể rút gọn:

~~~java
String value = System.getProperty("app.mode");
~~~

Tuy nhiên, trước khi bỏ wrapper ở nhiều chỗ, kiểm tra có checked exception, overload khác hoặc context propagation nào được thư viện sử dụng không. Việc dọn các API deprecated cần làm có chủ đích và kiểm thử hành vi.

### 3.3. Permission checker tự viết là một vấn đề khác

Một số framework dùng `AccessController.checkPermission` như một phần engine phân quyền tự xây. Trên JDK 24+, nó không trở thành một hàm cho phép kiểm quyền ở cấp ứng dụng; method này ném exception theo semantics mới.

Nếu ứng dụng muốn kiểm “user A có quyền xuất báo cáo?” hoặc “plugin P có được truy cập bí mật Q?”, phải có policy/authorization của chính hệ thống:
- Identity của caller/service/plugin.
- Tài nguyên và action cụ thể.
- Quy tắc kiểm quyền có dữ liệu và version.
- Audit decision và kiểm tra deny-by-default.
- Chỗ thực thi quyết định không thể bị bypass qua API khác.

Đừng dùng các class `java.security.Permission` như một bộ authorization framework mặc định mới chỉ vì tên có chữ Security.

## 4. Kiểm kê sự phụ thuộc trước khi nâng JDK

Security Manager có thể được kích hoạt bởi entrypoint chính, launcher của application server, test framework, build plugin, agent hoặc thư viện bắc cầu. Chỉ tìm `new SecurityManager()` trong source chính là chưa đủ.

### 4.1. Tìm trong source và cấu hình

Với ripgrep:

~~~bash
rg -n --hidden \
  -g '!**/.git/**' -g '!**/build/**' -g '!**/target/**' \
  'SecurityManager|setSecurityManager|getSecurityManager|AccessController|AccessControlContext|Policy\.setPolicy|checkPermission' .

rg -n --hidden \
  -g '!**/.git/**' \
  'java\.security\.manager|java\.security\.policy|\.policy|doPrivileged|checkRead|checkWrite|checkConnect' .
~~~

Khi gặp `.policy`, phải phân biệt Java Security Manager policy với policy thuộc hệ thống khác. Không xóa file chỉ vì có extension giống.

Đừng quên:
- Gradle/Maven plugin, test runner, agent.
- Startup scripts, systemd, Windows service, Dockerfile, Helm chart.
- CI variables như JAVA_TOOL_OPTIONS hoặc JDK_JAVA_OPTIONS.
- Application server configuration, policy file hoặc VM option ngoài repository.
- Third-party JAR dùng reflection/dynamic class loading.
- Consumer/plugin được nạp ở runtime mà build-time source không chứa.

### 4.2. Tìm API deprecated trong artifact

Với JDK hỗ trợ `jdeprscan`, có thể kiểm tra JAR đã build:

~~~bash
jdeprscan --release 17 app.jar
~~~

Chọn `--release` được tool hiện tại hỗ trợ và phù hợp baseline cần rà. `jdeprscan` báo những API Java SE bị deprecated được tham chiếu tĩnh trong class file; nó không chứng minh code đã bật Security Manager hay tìm được mọi lời gọi qua reflection.

Trên JDK 17–23, Java launcher thường cảnh báo khi Security Manager được bật/cài theo cơ chế deprecated. Ghi lại cảnh báo này như một bằng chứng, nhưng **không dựa chỉ vào warning**: thư viện có thể có nhánh code chỉ chạy khi feature flag/plug-in được bật.

### 4.3. Dùng JDK 17–23 để phát hiện cài Security Manager động

Trên một JDK trong phạm vi 17–23 có hỗ trợ cấu hình thử này, có thể chạy ứng dụng:

~~~bash
java \
  -Djava.security.manager=disallow \
  -jar app.jar
~~~

Nếu startup hoặc một luồng chức năng cố `System.setSecurityManager`, có thể phát hiện lỗi `UnsupportedOperationException`. Chạy đủ đường nghiệp vụ, plugin, test và job quan trọng, không chỉ health check.

**Không dùng command này trên JDK 24+ như một phép thử tương đương.** Security Manager đã bị vô hiệu hóa vĩnh viễn; ý nghĩa của launch options và API không còn giống giai đoạn cũ.

### 4.4. Lập dependency inventory

Một mẫu inventory hữu ích:

| Trường | Ví dụ |
|---|---|
| Source/artifact | `legacy-plugin-engine:2.3` |
| Caller | `PluginLoader.installSandbox` |
| API | `System.setSecurityManager` |
| Mục tiêu trước đây | Chặn plugin đọc file hệ thống |
| JDK baseline | JDK 11 |
| JDK đích | JDK 25 |
| Hành vi nếu bỏ | Plugin chạy trong process có thể truy cập file theo quyền OS của service |
| Rủi ro | Mất ranh giới bảo vệ giữa plugin và secret |
| Replacement | Chạy plugin ở process/container riêng, chỉ cấp file/network tối thiểu |
| Owner | Nhóm nền tảng |
| Kiểm thử | Kiểm tra plugin không thể đọc secret mount không được cấp |
| Trạng thái | Pending / Migrate / Verified |

Chú ý phân biệt **phụ thuộc bắt buộc** vào Security Manager với **code tương thích có điều kiện**. Một thư viện chỉ kiểm tra `getSecurityManager() == null` có thể chạy bình thường; thư viện tạo custom policy engine bằng `AccessController.checkPermission` sẽ cần thay đổi sâu hơn.

## 5. Mô hình đe dọa: Security Manager từng bảo vệ điều gì?

Muốn thay đúng, trước tiên xác định đối tượng cần bảo vệ và kiểu code đang được kiểm soát.

| Kịch bản | Rủi ro cần giới hạn | Nơi đặt kiểm soát thay thế |
|---|---|---|
| Service đọc/ghi file | Lộ secret hoặc sửa file hệ thống | Quyền user/process, filesystem ACL, mount read-only, cấp phát secret tối thiểu |
| Service kết nối mạng | Truy cập database không được phép hoặc exfiltrate dữ liệu | Network policy, egress firewall/proxy, identity và TLS |
| Plugin do đối tác cung cấp | Mã không tin cậy chạy bên trong JVM và chạm vào tài nguyên process | Tách process/container/VM; API giao tiếp có authentication/authorization |
| App nhiều tenant | Dữ liệu tenant này bị đọc bởi tenant khác | Tenant isolation ở data layer/service, query authorization và audit; tách process khi cần |
| Chạy script/biểu thức do người dùng gửi | Arbitrary code execution hoặc tiêu thụ tài nguyên | Sandbox process chuyên dụng được harden, quotas, timeouts, syscall/network controls |
| Dùng System.exit | Code phụ làm dừng process | Quản lý lifecycle, tách process, thiết kế plugin API; agent interception không phải sandbox bảo mật |
| Test framework dùng SecurityManager để chặn exit | Test bị kết thúc khi code gọi System.exit | Test trong subprocess/fork, assert exit code và output |
| RMI remote code download | Code tải từ nguồn khác rồi chạy trong JVM | Loại bỏ cơ chế remote loading không cần thiết, kiểm soát artifact distribution và trusted deployment |

**Một cơ chế thay thế hiếm khi giải quyết tất cả hàng trong bảng.** Ví dụ, NetworkPolicy hạn chế network nhưng không kiểm soát việc code đọc file secret đã mount trong container. Role-based authorization bảo vệ API nghiệp vụ, nhưng không chặn native code đọc một file mà process có quyền OS.

### 5.1. Bảo vệ khỏi code không tin cậy là use case khó nhất

Nếu mô hình cũ chạy plugin/script không tin cậy cùng JVM và hy vọng Security Manager cấm thao tác nguy hiểm, cần thay đổi ranh giới thực thi. Code trong cùng process thường có khả năng quan sát/tác động đến nhiều tài nguyên do process chia sẻ. Một `ClassLoader` hoặc JPMS module **không phải** security boundary thay thế.

Một thiết kế vững hơn:

~~~text
                     Trusted application
                             |
             Validated request + capabilities
                             |
                    Authenticated IPC
                             |
                    Plugin worker process
                    /        |         \
             restricted   resource     timeout
               files      quotas       policy
                    \        |         /
                       OS/container
                         isolation
                             |
                   Minimal external access
~~~

Worker nhận **chỉ những input/capability thật sự cần**, hoạt động bằng service account khác hoặc trong sandbox runtime được cấu hình bảo vệ, giao tiếp qua protocol có version và authorization. Không cung cấp database root credential hoặc thư mục chứa secret của ứng dụng chính cho worker nếu không cần.

Containers hỗ trợ phân tách nhưng **không tự bảo đảm sandbox an toàn khi chạy mặc định**. Cần đánh giá kernel isolation, quyền root/capabilities, mount, seccomp, AppArmor/SELinux, network, namespace, cgroup limits, image integrity và chính sách nâng cấp. Với mức độ tin cậy rất thấp hoặc dữ liệu nhạy cảm cao, có thể cần VM/microVM hoặc hạ tầng biệt lập phù hợp hơn.

## 6. Thay thế theo lớp kiểm soát

### 6.1. File system: quyền process thay cho FilePermission

Một Java policy cũ có thể giới hạn plugin chỉ đọc thư mục nhất định. Khi chuyển sang OS controls:
- Chạy service/worker dưới user riêng với quyền tối thiểu.
- Dùng file ownership/permission/ACL phù hợp.
- Mount chỉ những directory cần thiết, read-only nơi có thể.
- Không mount socket Docker host, thư mục home hoặc secret store vào worker không tin cậy.
- Áp dụng hạn chế OS/container như read-only root filesystem khi workload cho phép.
- Ghi audit khi cần theo dõi thao tác bất thường.

Ví dụ về nguyên tắc: nếu worker chỉ cần đọc `/data/input` và ghi `/data/output`, đừng cấp cả `/srv/app` hoặc thư mục chứa credential. Java code vẫn dùng `Files.readString` bình thường; access control thực thi ở lớp OS/filesystem.

### 6.2. Network: policy egress và identity

Một `SocketPermission` trước đây có thể hạn chế host/port. Hướng thay thế:
- NetworkPolicy hoặc firewall/egress gateway cho process/container.
- DNS và route policy phù hợp; tránh dựa riêng vào kiểm tra string hostname.
- Service identity, mutual TLS hoặc token phạm vi hẹp cho kết nối được phép.
- Phân vùng mạng để worker không gọi thẳng metadata service, control plane hoặc database không liên quan.
- Log và alert cho hành vi egress vi phạm.

Network policy không thay authentication/authorization. Nếu worker được phép gọi một API, API đó vẫn phải kiểm tra quyền của danh tính worker và từng tài nguyên được yêu cầu.

### 6.3. Process và resource controls

Trong môi trường OS/container, có thể dùng:
- User/group riêng, namespace và các cơ chế giảm đặc quyền.
- CPU/memory/pid quotas, timeout, watchdog.
- Seccomp hoặc sandbox tương đương để giới hạn syscall phù hợp.
- Filesystem mount namespace, read-only mounts và volume permission.
- Isolated process để quản lý `System.exit`, JVM crash hoặc unbounded memory allocation.
- Process supervisor có thể restart/reap worker và ghi telemetry.

Không có một option duy nhất cho mọi OS. Thiết kế phải khớp threat model, môi trường triển khai và loại code cần xử lý. Tính tương thích giữa security policy của OS với ứng dụng native/JNI cũng cần được kiểm tra.

### 6.4. Authorization trong ứng dụng

Nếu Security Manager được dùng để kiểm “người dùng này có được xuất hóa đơn?” thì nên chuyển sang một authorization service/layer riêng thay vì kiểm `RuntimePermission`.

Ví dụ interface ở cấp domain:

~~~java
public interface AuthorizationService {
    boolean canReadInvoice(String principalId, String invoiceId);
}
~~~

Sử dụng:

~~~java
public final class InvoiceService {
    private final AuthorizationService authorization;

    public InvoiceService(AuthorizationService authorization) {
        this.authorization = authorization;
    }

    public String readInvoice(String principalId, String invoiceId) {
        if (!authorization.canReadInvoice(principalId, invoiceId)) {
            throw new SecurityException("Invoice access denied");
        }
        return loadInvoiceFromDatabase(invoiceId);
    }

    private String loadInvoiceFromDatabase(String invoiceId) {
        // Minh họa: truy vấn qua repository có tenant/resource scoping.
        return "invoice:" + invoiceId;
    }
}
~~~

Đây là ví dụ về vị trí kiểm tra quyền, **không phải triển khai authorization hoàn chỉnh**. Trong sản phẩm thật, danh tính phải được xác thực, không tin vào `principalId` do client tùy ý gửi; truy vấn database và repository cần enforcing tenant/resource scope, cùng audit/deny-by-default. Check trước rồi thực hiện thao tác bằng một API khác không kiểm quyền có thể tạo bypass hoặc TOCTOU issue.

### 6.5. IAM và secret management

Nếu code cũ dùng Security Manager để không cho plugin đọc environment variable hoặc cấu hình có secret, mô hình mới nên dựa vào:
- Cấp secret tối thiểu cho đúng process.
- Workload identity/role của service, token ngắn hạn và quyền truy cập hẹp.
- Tách credential giữa application chính và worker.
- Secret store/KMS với policy và audit.
- Không ghi secret vào log, dump hoặc command line.
- Rotate và revoke credential khi nghi ngờ bị lộ.

Một khi secret đã được mount hoặc đưa vào memory của process, việc cố “cấm” một library cùng process đọc nó bằng một API Java đơn thuần không phải hàng rào đáng tin cậy cho mã không tin cậy.

## 7. Ví dụ migration: thay Java policy bằng isolation ngoài process

Giả sử một hệ thống plugin cũ có chính sách:

~~~java
grant codeBase "file:/opt/app/plugins/*" {
    permission java.io.FilePermission "/srv/shared/public/-", "read";
    permission java.net.SocketPermission "api.partner.example:443", "connect,resolve";
};
~~~

Đây là ví dụ **legacy policy syntax**, không phải cấu hình có hiệu lực trên JDK 24+. Ý định cũ là giới hạn plugin chỉ đọc một vùng filesystem và kết nối một điểm mạng. Nếu chỉ xóa `-Djava.security.manager`, plugin có thể được hưởng quyền file/network rộng của process ứng dụng.

Hướng migration:
1. Đưa plugin sang process/worker riêng; không chạy code plugin trực tiếp cùng JVM chứa secret.
2. Chạy worker với user/identity hẹp.
3. Chỉ mount dữ liệu cần đọc; không mount thư mục ứng dụng chính.
4. Chỉ cho phép outbound traffic tới service được phê duyệt bằng policy egress.
5. API đích xác thực worker và kiểm tra quyền tài nguyên theo danh tính.
6. Giao tiếp giữa ứng dụng chính và worker qua protocol xác định; validate input/output.
7. Có timeout, memory limit và cơ chế dừng/restart process worker.
8. Tạo test bảo mật chứng minh plugin không thể đọc file/mạng ngoài phạm vi.

### 7.1. Test phải xác minh hành vi bị từ chối

Không chỉ test “plugin xử lý tác vụ hợp lệ thành công”. Cần thêm các ca:
- Thử đọc một file bí mật không mount/cấp quyền.
- Thử ghi vào directory read-only.
- Thử mở kết nối tới host ngoài allowlist.
- Thử dùng identity worker truy cập tài nguyên tenant khác.
- Thử làm task quá CPU/memory/time quota.
- Thử crash hoặc gọi `System.exit` trong worker: application chính không nên chết theo.
- Thử gửi payload sai schema hoặc quá lớn vào IPC endpoint.

**Bằng chứng cần ghi** gồm quyết định OS/network/auth layer, exit status và log; không chỉ việc Java method có ném `SecurityException` hay không. Security Manager đã không còn là lớp thực thi quyết định.

### 7.2. Giữ chức năng cũ mà không giữ cơ chế cũ

Nếu mục đích thực chỉ là “plugin được phép xử lý dữ liệu đầu vào và tạo kết quả”, có thể thiết kế API plugin nhận dữ liệu đã được ủy quyền, không cho plugin trực tiếp đọc file/network. Điều này giảm cả quyền cần cấp và phạm vi có thể bị lạm dụng.

Tuy vậy, API hướng capability chỉ có ý nghĩa khi những capability không thể bị bỏ qua bằng đường truy cập khác trong cùng security boundary. Nếu plugin không tin cậy vẫn chạy trong process có toàn bộ secret, việc truyền một `RestrictedFileReader` object không tự ngăn nó gọi `Files.readAllBytes` với quyền OS của process. Vì vậy, **API design và process isolation phải đi cùng nhau** khi cần chống mã không tin cậy.

## 8. Test framework và nhu cầu chặn System.exit

Một số test framework cũ cài Security Manager để chặn `System.exit(1)` của code đang test. Trên JDK 24+, cách cài đó không dùng được.

### 8.1. Thay thử nghiệm bằng subprocess

Thay vì chạy code có thể gọi exit ngay trong JVM của test runner, cho nó chạy ở một Java process riêng:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class ExitCodeHarness {
    public static void main(String[] args) throws Exception {
        String javaBin = Path.of(
                System.getProperty("java.home"), "bin", "java"
        ).toString();

        Process process = new ProcessBuilder(
                javaBin,
                "-cp",
                System.getProperty("java.class.path"),
                "com.example.cli.Main"
        ).inheritIO().start();

        boolean finished = process.waitFor(
                Duration.ofSeconds(10).toMillis(),
                TimeUnit.MILLISECONDS
        );
        if (!finished) {
            process.destroyForcibly();
            throw new IllegalStateException("CLI exceeded timeout");
        }

        int exit = process.exitValue();
        if (exit != 0) {
            throw new AssertionError("Unexpected exit code: " + exit);
        }
    }
}
~~~

Trong ví dụ, `com.example.cli.Main` là class của ứng dụng cần thử. Process con có exit status riêng nên không kết thúc JVM test runner. Với test thực tế cần kiểm soát stdout/stderr, kích thước output, classpath/module path, biến môi trường, cleanup process tree và timeout. Không dùng `inheritIO` nếu cần giữ output làm assertion hoặc lo ngại log chứa secret.

### 8.2. Refactor code để dễ kiểm thử

Khi có quyền sửa ứng dụng, có thể tách logic nghiệp vụ khỏi entrypoint:
- Method nghiệp vụ trả kết quả hoặc throw exception phù hợp.
- `main` mapping kết quả thành exit code.
- Unit test gọi logic trực tiếp mà không phải cài Security Manager.
- Integration test chạy process để xác minh exit code.

Cách này giảm nhu cầu intercept `System.exit`. Java agent dùng bytecode instrumentation có thể giúp một số test/framework, nhưng **không phải cơ chế sandbox bảo mật** và không thay thế process boundary đối với code không tin cậy.

## 9. Tính tương thích của thư viện và framework

Không phải tất cả dependency dùng Security Manager đều làm ứng dụng thất bại trên JDK 24. Cần phân loại:

**Nhóm 1: dùng manager theo cách tùy chọn.**

~~~java
if (System.getSecurityManager() != null) {
    // permission checks khi manager thực sự bật
}
~~~

Trên JDK 24+, nhánh này không chạy. Nếu ứng dụng không phụ thuộc permission check ấy để bảo vệ tài nguyên, thư viện có thể tiếp tục vận hành, dù vẫn nên cập nhật version và bỏ API deprecated.

**Nhóm 2: bọc hành động trong doPrivileged.**

~~~java
AccessController.doPrivileged(() -> {
    initializeCache();
    return null;
});
~~~

Trên JDK 24+, action thực thi như lời gọi thường. Code có thể chạy nhưng không nên giữ wrapper như một bằng chứng về security boundary.

**Nhóm 3: cài custom manager hoặc policy động.**

~~~java
System.setSecurityManager(new MySecurityManager());
~~~

Đây là blocker rõ cho JDK 24+ vì operation không còn được hỗ trợ. Cần cập nhật framework hoặc thay kiến trúc.

**Nhóm 4: gọi checkPermission như một engine phân quyền.**

~~~java
AccessController.checkPermission(
    new RuntimePermission("someOperation")
);
~~~

Hành vi JDK 24+ không tương đương engine policy cũ; cần thay bằng application authorization hoặc boundary ngoài process. Không chỉ bắt exception rồi bỏ qua, vì có thể biến deny thành allow.

**Nhóm 5: phụ thuộc remote code download/RMI behavior cũ.**

Một số khả năng nạp code RMI từng dựa trên Security Manager; JDK 24 loại bỏ cơ chế remote code downloading mặc định đó. Nên chuyển sang distribution/deployment artifact được kiểm soát, không tự bật lại code tải động từ nguồn không tin cậy. Nếu ứng dụng thật sự có plugin remote, cần thiết kế lại trust, verification và process isolation.

## 10. Đừng nhầm Security Manager với các kiểm soát khác của JDK

### 10.1. JPMS không thay thế Security Manager

JPMS quản lý:
- Module readability.
- Exported packages.
- Open packages cho reflection.
- Cấu trúc dependency và encapsulation.

JPMS giúp hạn chế **những cách truy cập API** không được khai báo, nhưng không phải sandbox cho untrusted Java bytecode. `--add-opens`, `--add-exports` và `--add-reads` là option module-access; chúng **không bật lại Security Manager** và không cấm process đọc file hay mở kết nối theo quyền OS.

### 10.2. Security properties khác với java.policy

Java vẫn có cơ chế security properties cho JCA, provider, thuật toán bị hạn chế, TLS và nhiều tính năng khác. Không xóa toàn bộ file `java.security` hoặc bỏ cấu hình TLS chỉ vì Security Manager không còn được hỗ trợ.

Cần phân biệt:
- Property riêng phục vụ `SecurityManager`/policy file cũ.
- Security property phục vụ JCA/JSSE, provider và thuật toán.
- Policy/role của ứng dụng hoặc hệ thống ngoài.

Một số property từng dùng cho Security Manager trở nên không được hỗ trợ trên JDK 24, nhưng các cấu hình bảo mật khác của Java vẫn có hiệu lực. Đọc tài liệu release cụ thể trước khi dọn startup flags.

### 10.3. Java agent không thay thế OS sandbox

Một agent có thể dùng `java.lang.instrument` để quan sát hoặc sửa bytecode khi class load. Điều đó phù hợp với observability, kiểm thử hoặc instrumentation được kiểm soát. Nhưng agent không phải ranh giới thực thi tin cậy cho mã không tin cậy cùng process: còn có class loading động, native code, method handles, các đường gọi không được instrument và rủi ro bypass.

Nếu mục tiêu là hạn chế plugin không tin cậy đọc secret hoặc kết nối mạng, ưu tiên isolation ở cấp OS/container/VM và kiến trúc cấp quyền tối thiểu.

## 11. Kiểm tra trên từng phiên bản JDK

### 11.1. Xác định runtime thực sự

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Khi ứng dụng chạy trong container/service, phải dùng Java của **process thực tế**. Kiểm tra Docker ENTRYPOINT, Kubernetes command/args, startup script, service unit và environment injection. Đừng suy luận từ JDK cài trên máy phát triển.

### 11.2. Ma trận kiểm thử minh họa

| Test | JDK 11 hoặc baseline | JDK 17–23 | JDK 24+ |
|---|---|---|---|
| JVM khởi động không bật Security Manager | Thường chạy | Thường chạy | Chạy nếu không phụ thuộc cơ chế cũ |
| Cài manager qua startup flag | Có thể chạy theo policy cũ | Có điều kiện và warning | **Không hỗ trợ, có thể lỗi ngay lúc startup** |
| Gọi System.setSecurityManager | Phụ thuộc policy/config | Có điều kiện; có thể ném UOE | **Luôn ném UOE** |
| Kiểm tra System.getSecurityManager() | Có thể null hoặc non-null | Có thể null hoặc non-null | **Luôn null** |
| AccessController.doPrivileged | Hành vi liên quan manager nếu bật | Tùy trạng thái manager | **Chạy action trực tiếp** |
| Permission policy từ java.policy | Có thể là kiểm soát cũ | Có điều kiện | **Không thực thi sandbox cũ** |
| OS file/network permission | Được OS enforce | Được OS enforce | Được OS enforce |
| App authentication/authorization | Theo implementation ứng dụng | Theo implementation ứng dụng | Theo implementation ứng dụng |

UOE ở đây là `UnsupportedOperationException`. Ma trận giúp lập kế hoạch, **không thay thế test trên vendor/build cụ thể**.

### 11.3. Thử nghiệm có chủ đích để phát hiện phụ thuộc còn sót

Trên JDK 17–23:
1. Chạy ứng dụng với các feature quan trọng.
2. Kiểm tra warning Security Manager.
3. Chạy một bản thử với `-Djava.security.manager=disallow` để phát hiện cài động.
4. Chạy dependency scanner để tìm deprecated API references.
5. Ghi những luồng nghiệp vụ còn cần permission checks.

Trên JDK 24+:
1. **Không dùng** flag bật/cho phép Security Manager.
2. Chạy startup, load plugin, integration test và các đường code custom policy.
3. Xác minh không có `setSecurityManager` hoặc `Policy.setPolicy` làm startup/feature lỗi.
4. Kiểm tra cơ chế sandbox thay thế thực sự từ chối truy cập ngoài phạm vi.
5. Đảm bảo OS/container IAM/permission configuration được deploy đồng thời.

Lưu stack trace, JDK version, artifact checksum, launch command và kết quả deny tests. Không làm “pass” bằng cách đơn thuần bắt rồi bỏ qua `SecurityException` hoặc `UnsupportedOperationException`.

## 12. Quy trình migration theo bước

### Bước 1: Lập danh sách nơi dùng Security Manager

Tìm source, configuration, dependency, framework, test và policy files. Xác định ai cài manager, ai kiểm quyền và những tài nguyên được bảo vệ.

### Bước 2: Phân loại theo vai trò

Tối thiểu chia thành:
- Sandbox cho code/plugin không tin cậy.
- Policy hạn chế file/network/process.
- Authorization nghiệp vụ.
- Test chặn `System.exit`.
- Thư viện chỉ gọi `getSecurityManager/doPrivileged` khi có manager.
- Thư viện trực tiếp dùng `checkPermission` hay dynamic policy.

Mỗi nhóm có replacement khác nhau; không tạo một wrapper thay thế SecurityManager chung cho mọi mục đích.

### Bước 3: Thiết kế ranh giới quyền mới

Nếu cần chống code không tin cậy, chuyển sang process/container/VM phù hợp. Nếu chỉ kiểm quyền người dùng, dùng authorization tại API/data layer. Nếu chỉ cần test exit code, dùng subprocess. Nếu một thư viện dùng API deprecated mà không cần sandbox, nâng thư viện và bỏ wrapper khi an toàn.

### Bước 4: Xây test “deny” trước khi bỏ policy cũ

Tạo các ca truy cập bị cấm: file, secret, network, tenant khác, process lifecycle và resource exhaustion. Test phải đo ranh giới mới, không chỉ assert rằng manager vẫn tồn tại.

### Bước 5: Cập nhật build, dependency và launch config

- Pin phiên bản JDK và thư viện có support matrix phù hợp.
- Loại `-Djava.security.manager` nhằm bật/cho phép manager.
- Loại cấu hình Java policy legacy khỏi startup khi đã có cơ chế thay thế.
- Không xóa security properties không liên quan.
- Cập nhật container user, mount, network policy, workload identity và secrets.
- Cập nhật framework/plugin version để không cài manager động.

### Bước 6: Kiểm thử trên JDK đích

Chạy unit, integration, contract và security tests. Kiểm tra cả startup, plugin load, data access và tình huống vi phạm quyền. Đối với plugin nguy cơ cao, thử phá boundary với quyền thực tế được cấp trong môi trường thử nghiệm biệt lập; không dựa vào việc không thấy SecurityException.

### Bước 7: Rollout và vận hành

Triển khai từ staging/canary, theo dõi denied access, lỗi start, plugin failures, crash, timeout, event audit, network egress và secret access. Có phương án rollback rõ, đồng thời tránh rollback vô thức sang mô hình đã mất isolation ở mức triển khai.

### Bước 8: Bỏ phụ thuộc dài hạn

Khi mọi use case đã có replacement, loại API deprecated và file policy không còn dùng, bổ sung regression check vào CI. Ghi trong runbook rằng Security Manager không phải cơ chế bảo mật được hỗ trợ trên JDK 24+.

## 13. Những sai lầm cần tránh

- **Cho rằng JDK 17 đã loại bỏ class SecurityManager:** JDK 17 mới deprecated for removal, JDK 24+ mới permanently disabled.
- **Cho rằng JDK 24 đã xóa toàn bộ API khỏi bytecode:** nhiều method vẫn tồn tại nhưng semantics thay đổi; chúng có thể bị loại bỏ trong tương lai.
- **Chỉ xóa launch flag để ứng dụng chạy:** có thể làm mất kiểm soát file, mạng hoặc plugin đã dựa vào policy cũ.
- **Dùng --add-opens/--add-exports để “bật lại” manager:** JPMS access option không khôi phục Security Manager.
- **Bắt UnsupportedOperationException rồi tiếp tục:** có thể biến ranh giới an toàn trước đây thành no-op.
- **Coi AccessController.doPrivileged là một sandbox:** từ JDK 24 nó thực thi action bình thường.
- **Coi AccessController.checkPermission là authorization API còn được hỗ trợ:** semantics Security Manager đã thay đổi.
- **Chỉ tìm trong source app:** dependency, agent, application server và test runner có thể cài manager.
- **Cho rằng Docker mặc định là sandbox hoàn chỉnh:** cần hardening, ít quyền, network restriction và bảo vệ host.
- **Dùng RBAC để thay file/network isolation:** RBAC bảo vệ business API nhưng không tự chặn syscall của process.
- **Chỉ test “allow” mà không test “deny”:** không chứng minh chính sách mới thực sự giới hạn quyền.
- **Bỏ policy security mà không ghi threat model:** không biết chức năng nào đã từng được bảo vệ.
- **Lẫn java.policy với Java security properties khác:** có thể vô tình làm yếu cấu hình TLS/JCA.
- **Coi ClassLoader/JPMS là sandbox của untrusted bytecode:** đây không phải security boundary thay thế.
- **Không phân biệt code tùy chọn với code bắt buộc:** thư viện chỉ gọi getSecurityManager có thể chạy; engine Policy tự viết có thể phải thiết kế lại.

## 14. Checklist trước khi chuyển production

- [ ] Đã ghi JDK vendor/build, JDK baseline và JDK đích.
- [ ] Đã xác nhận trạng thái Security Manager theo JDK (JDK 17 deprecated, JDK 24+ disabled).
- [ ] Đã tìm mọi launch flag `java.security.manager`, `java.security.policy` và file `java.policy`.
- [ ] Đã rà source, bytecode/dependency và test runner cho `setSecurityManager`, `Policy`, `AccessController` và `checkPermission`.
- [ ] Đã phân loại use case: sandbox, OS resource, authorization, lifecycle test hay optional compatibility.
- [ ] Đã ghi threat model và danh sách resource cần giới hạn.
- [ ] Nếu có untrusted code, đã thiết kế boundary ngoài process/JVM phù hợp.
- [ ] Các process chạy với user/identity và filesystem/network permission tối thiểu.
- [ ] Secret không được cấp cho worker/plugin ngoài phạm vi cần thiết.
- [ ] Các API nghiệp vụ kiểm identity, resource và tenant authorization ở đúng chỗ.
- [ ] Có test deny access, timeout, memory/CPU quotas và process crash isolation.
- [ ] Không còn code cài Security Manager trên JDK 24+ trong đường chạy bắt buộc.
- [ ] Đã kiểm tra dependency/plugin/framework có version hỗ trợ JDK đích.
- [ ] Đã cập nhật startup command, container config, runbook và CI.
- [ ] Đã thực thi test bảo mật trên deployment tương đương production.
- [ ] Có log/audit/alert cho quyền bị từ chối và hành vi vượt giới hạn.
- [ ] Có owner, evidence và kế hoạch xử lý những trường hợp migration còn dang dở.

## 15. Tài liệu tham khảo chính thức

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): bối cảnh và thay đổi ở JDK 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): thay đổi thực thi từ JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): hành vi cụ thể của launcher, API và hướng migration.
- [Java SE 17 SecurityManager API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html): trạng thái deprecated for removal trên JDK 17.

Khi đối chiếu, ưu tiên tài liệu của **release và vendor runtime thực tế**. Những API có tên giống nhau giữa các JDK có thể mang semantics khác; kết luận luôn phải được kiểm tra bằng startup và scenario thực tế.

## 16. Kết luận

**Security Manager đã deprecated for removal từ JDK 17 và bị vô hiệu hóa vĩnh viễn từ JDK 24.** Nhiều API liên quan còn hiện diện trong JDK mới nhưng không còn thực hiện kiểm soát quyền theo mô hình `java.policy` trước đây; một số API trả null hoặc thực thi trực tiếp, một số khác luôn ném exception. Vì vậy migration không thể chỉ xóa cảnh báo compiler, bắt ngoại lệ hoặc thêm một JVM flag khác.

Muốn giữ mục tiêu bảo mật, trước tiên xác định Security Manager đang bảo vệ tài nguyên và code nào, rồi chuyển sang ranh giới đúng: quyền OS/container/VM cho tài nguyên và untrusted code, network/IAM cho truy cập dịch vụ, authorization cho dữ liệu nghiệp vụ và subprocess cho test/lifecycle isolation. Sau đó kiểm chứng **các trường hợp bị từ chối**, không chỉ đường chạy thành công. Cách tiếp cận này giúp nâng JDK mà không vô tình xóa đi lớp phòng vệ mà hệ thống cũ từng phụ thuộc.

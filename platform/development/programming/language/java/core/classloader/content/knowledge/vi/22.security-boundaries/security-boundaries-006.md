# SecurityManager là cơ chế lịch sử và cần đối chiếu phiên bản JDK

**`java.lang.SecurityManager` là cơ chế kiểm soát quyền truy cập tài nguyên mang tính lịch sử của Java; không phải công cụ sandbox được khuyến nghị cho ứng dụng Java hiện đại.** Khi đọc tài liệu cũ về `ClassLoader`, plugin, `ProtectionDomain` hoặc `java.security.Policy`, rất dễ gặp ví dụ cài `SecurityManager` để giới hạn quyền đọc file, mở socket hay tạo class loader. Những ví dụ đó cần được hiểu theo **đúng phiên bản JDK**, vì Java đã thay đổi chính sách rất lớn.

Các mốc quan trọng:

- **JDK 8–16:** `SecurityManager` là một phần của mô hình bảo mật truyền thống, có thể được cấu hình trong những điều kiện cụ thể. Không nên mặc định tất cả chương trình đều kích hoạt nó.
- **JDK 17:** **JEP 411** đánh dấu `SecurityManager` cùng nhiều API liên quan là **deprecated for removal**. Cơ chế cũ vẫn còn, nhưng ứng dụng mới không nên dựa vào nó.
- **JDK 17–23:** còn giai đoạn tương thích lịch sử; khả năng bật/cài động và thông báo cảnh báo **phụ thuộc phiên bản và cấu hình**. Không lấy hành vi của một JDK trong khoảng này làm hợp đồng cho JDK sau.
- **Từ JDK 24:** **JEP 486** làm `SecurityManager` **permanently disabled**. Không thể bật nó lúc khởi động hoặc cài một custom manager lúc runtime. Các API liên quan còn tồn tại để tương thích trong một số phiên bản nhưng nhiều phương thức đã đổi semantics; bản thân API được dự kiến loại bỏ trong tương lai.

**Ý chính của bài học:** Class loader quy định **tìm và định nghĩa lớp nào trong namespace nào**; SecurityManager lịch sử là một cơ chế **kiểm tra quyền thao tác**; JPMS quy định **ranh giới module và quyền truy cập API/reflective access**. Chúng không thay thế cho nhau. Để chạy plugin không đáng tin, phải thiết kế **ranh giới bảo mật ngoài JVM hoặc process isolation**, thay vì chỉ tạo một `ClassLoader` riêng.

## 1. SecurityManager từng giải quyết vấn đề gì?

Trong những ứng dụng Java lịch sử, hệ thống có thể muốn chạy code đến từ nguồn ít tin cậy hơn và hạn chế những hành động nhạy cảm:

- Đọc, ghi hoặc xóa tệp trên filesystem.
- Mở kết nối mạng, lắng nghe socket.
- Tạo subprocess hoặc yêu cầu JVM thoát.
- Tạo class loader, thay đổi system properties hoặc một số cấu hình runtime.
- Truy cập package, reflection hoặc các thao tác nhạy cảm theo những `Permission` tương ứng.

Ý tưởng tổng quát:

```text
Code gọi một API nhạy cảm
         |
         v
Java library/runtime (trong môi trường có SecurityManager)
         |
         v
SecurityManager.checkPermission(permission)
         |
         +-- quyền cho phép -> API tiếp tục
         |
         +-- quyền bị từ chối -> SecurityException
```

Những classes/khái niệm xuất hiện trong tài liệu lịch sử:

| Thành phần | Vai trò lịch sử |
|---|---|
| `SecurityManager` | Entry point kiểm tra quyền với các `check...` methods |
| `Permission` | Biểu diễn yêu cầu quyền, ví dụ `FilePermission` hoặc `SocketPermission` |
| `Policy` | Nguồn cấu hình những quyền được cấp |
| `ProtectionDomain` | Gắn class/code với domain, code source và quyền |
| `AccessControlContext` | Ngữ cảnh kiểm tra quyền ở call stack |
| `AccessController` | Kiểm tra quyền và thao tác `doPrivileged` trong mô hình cũ |
| `ClassLoader` | Tải/định nghĩa class, ảnh hưởng code source và `ProtectionDomain` khi dùng overload phù hợp |

**Điều kiện then chốt:** Trong JDK lịch sử, những kiểm tra đó chỉ có tác dụng khi SecurityManager thực sự được bật/cài đặt và thư viện/runtime gọi đúng điểm kiểm tra. Chỉ tồn tại `Permission` hoặc `ProtectionDomain` **không tự động khiến ứng dụng bị sandbox**.

## 2. Các phiên bản JDK và những thay đổi phải ghi nhớ

| Dòng JDK | Trạng thái SecurityManager | Điều cần hiểu |
|---|---|---|
| **JDK 8–16** | Cơ chế bảo mật truyền thống còn khả dụng | Cấu hình/việc cài manager và policies quyết định hành vi; không mặc nhiên bật |
| **JDK 17** | **Deprecated for removal** theo JEP 411 | Các API vẫn có để tương thích; có cảnh báo deprecation và cảnh báo khi sử dụng |
| **JDK 18–23** | Tiếp tục lộ trình deprecation/giảm hỗ trợ | Đừng giả định property/default startup và khả năng `setSecurityManager` giống JDK 17 |
| **JDK 24 trở lên** | **Permanently disabled** theo JEP 486 | Không được bật/install; các API liên quan có behaviors bị thu hẹp hoặc thay đổi |
| **Một phiên bản JDK tương lai** | API có thể bị loại bỏ | Việc API còn compile ở một release không bảo đảm tồn tại ở mọi release sau |

Đây là **bảng định hướng**, không thay cho migration guide của chính vendor/runtime đang triển khai. Đặc biệt, những cụm “deprecated” và “disabled” mang nghĩa **khác nhau**.

### Deprecated for removal khác permanently disabled

- **Deprecated for removal:** compiler và tooling cảnh báo không nên dùng và API có kế hoạch bị loại bỏ; ở JDK 17, một số use cases lịch sử vẫn có thể hoạt động khi cấu hình cho phép.
- **Permanently disabled:** kể từ **JDK 24**, manager không thể được kích hoạt để thực thi policy cũ, dù API `SecurityManager` có thể vẫn hiện diện trong class library cho mục đích tương thích.
- **Removed:** API không còn trong một phiên bản; đây **không phải** mô tả tương đương với việc “bị disable” trong JDK 24. Khi gặp báo cáo lỗi, phải ghi đúng phiên bản và trạng thái.

**Tránh câu sai:** “SecurityManager đã bị xóa khỏi Java 17” — Java 17 **deprecated for removal**, chứ không xóa. Cũng tránh “SecurityManager vẫn dùng bình thường ở mọi JDK mới vì class còn tồn tại” — từ JDK 24 cơ chế kiểm soát đó **không hoạt động như trước**.

## 3. Khi Java 17 còn cho cấu hình SecurityManager

Trong Java SE 17, SecurityManager có thể được cài khi khởi động trong các cấu hình được hỗ trợ. Một ví dụ tài liệu lịch sử:

```bash
# CHỈ mang ý nghĩa nghiên cứu ứng dụng cũ trên JDK 17;
# không dùng làm cách sandbox plugin mới.
java -Djava.security.manager=default -jar legacy-app.jar
```

Một cơ chế khác của Java 17 là khai báo chính sách quyền qua file policy và các code source/protection domains. Các cấu hình này có ngữ nghĩa và hạn chế riêng; không thể chỉ viết một file `.policy` rồi mặc nhiên mọi code trong JVM bị cô lập.

Theo Java SE 17 API, `java.security.manager` có các giá trị như `allow` và `disallow` cùng những giá trị lịch sử kích hoạt manager. Ví dụ:

- `disallow`: không cài manager lúc startup và ngăn cài động, khiến `System.setSecurityManager(...)` ném `UnsupportedOperationException`.
- `allow`: không cài manager lúc startup nhưng cho phép thử cài động theo contract của JDK 17 và policy đang áp dụng.
- `default` (hoặc cấu hình lịch sử tương ứng): có thể cài default manager khi khởi động JDK 17.

**Không mang nguyên các quy tắc property ở JDK 17 áp sang JDK 24+.** Trên JDK 24, một tùy chọn cố bật/cho phép SecurityManager lúc khởi động là **lỗi khởi tạo JVM**, không phải chỉ cảnh báo deprecation.

### JDK 24+: bật SecurityManager là lỗi startup

Ví dụ lệnh trên Bash:

```bash
java -Djava.security.manager=allow -version
```

Trên **Windows PowerShell 5.1**, nên đặt argument `-D...=...` trong dấu nháy để tránh cách shell phân tích dấu bằng:

```powershell
java '-Djava.security.manager=allow' -version
```

Với OpenJDK 24, JVM không khởi động được và thông báo chính gồm:

```text
Error occurred during initialization of VM
java.lang.Error: A command line option has attempted to allow or enable the Security Manager. Enabling a Security Manager is not supported.
```

Đây là **hai dòng nội dung chính**; stack trace và số dòng `System.java` thay đổi theo patch release/vendor. Lệnh kết thúc với mã lỗi (trong phép thử OpenJDK 24 là **exit code 1**). Không dùng exit code/thông báo đó làm contract xử lý nghiệp vụ; nó minh họa rằng tính năng không thể bật nữa.

Ở JDK 24+, `System.setSecurityManager(...)` luôn ném **`UnsupportedOperationException`**. Đừng thiết kế chương trình mới gọi nó rồi bắt lỗi để bật sandbox dự phòng.

## 4. Ví dụ Java 17+ chạy được: kiểm tra phiên bản, manager và host API

Ví dụ dưới đây minh họa ba điều không nên lẫn:

1. Kiểm tra **phiên bản Java runtime thực tế**, không chỉ phiên bản mà source được biên dịch nhắm tới.
2. Quan sát liệu có SecurityManager đang cài hay không — **không tự cố cài một manager**.
3. Host API có thể chủ động từ chối thao tác theo contract nghiệp vụ mà **không phụ thuộc** vào SecurityManager.

Lưu một file **`SecurityBoundaryDemo.java`**:

```java
public final class SecurityBoundaryDemo {

    interface HostApi {
        String readSetting();
        void changeSetting(String value);
    }

    static final class ReadOnlyHostApi implements HostApi {
        @Override
        public String readSetting() {
            return "safe-config";
        }

        @Override
        public void changeSetting(String value) {
            throw new SecurityException(
                    "Host API forbids this operation");
        }
    }

    @SuppressWarnings("removal")
    static boolean oldManagerInstalled() {
        return System.getSecurityManager() != null;
    }

    public static void main(String[] args) {
        int feature = Runtime.version().feature();

        System.out.println("Java feature: " + feature);
        System.out.println("SecurityManager present: "
                + oldManagerInstalled());

        System.out.println("Status: " + (feature >= 24
                ? "permanently disabled"
                : "legacy, check runtime configuration"));

        HostApi api = new ReadOnlyHostApi();
        System.out.println("Read via host API: "
                + api.readSetting());

        try {
            api.changeSetting("new-config");
            System.out.println("Unexpected host API success");
        } catch (SecurityException expected) {
            System.out.println("Write via host API: denied");
        }
    }
}
```

Biên dịch trên Java 17+:

```bash
javac --release 17 SecurityBoundaryDemo.java
java SecurityBoundaryDemo
```

Đầu ra đã kiểm chứng trên **OpenJDK 24**, biên dịch đích **Java 17**:

```text
Java feature: 24
SecurityManager present: false
Status: permanently disabled
Read via host API: safe-config
Write via host API: denied
```

Nếu chạy trên **JDK 17–23**, dòng `Java feature` và `Status` sẽ khác; `SecurityManager present` có thể thay đổi theo việc manager có được bật hay không. Ví dụ **không bảo đảm stdout y hệt trên mọi JDK**. Cũng không nên suy đoán feature version khi dùng runtime vendor tùy biến: hãy quan sát giá trị chương trình in ra.

### Tại sao có @SuppressWarnings("removal")?

`System.getSecurityManager()` được đánh dấu deprecated for removal từ Java 17. Annotation ở ví dụ chỉ nhằm **giữ compiler output gọn cho bài kiểm tra compatibility**. Nó **không** làm phương thức trở lại thành API nên dùng, không thay đổi runtime behavior và **không được xem là giải pháp migration**.

Trong production code mới, nếu bạn không tích hợp legacy code nào, tốt nhất **không cần gọi `getSecurityManager()`**. Hãy tập trung vào security boundary thật sự do ứng dụng/hạ tầng thiết kế.

### Vì sao ReadOnlyHostApi không phải sandbox?

Method `changeSetting` chủ động ném `SecurityException`. Đây chỉ là **hạn chế do host API đặt ra với caller tuân thủ contract**.

Một plugin tùy ý chạy trong **cùng JVM** vẫn có thể cố gọi `java.nio.file.Files`, `java.net.Socket` hoặc APIs khác bằng chính code của nó. `ReadOnlyHostApi` không chặn được các lối truy cập ấy chỉ vì nó ném exception trong một method.

Do đó **không dùng API wrapper đơn thuần làm ranh giới thực thi mã độc**. Nó hữu ích cho ứng dụng/plugin đáng tin và thiết kế least-authority ở tầng nghiệp vụ; với code không đáng tin cần **OS/process isolation**.

## 5. ClassLoader và SecurityManager giải quyết hai câu hỏi khác nhau

`ClassLoader` chủ yếu trả lời: **Lớp nào được tìm/định nghĩa, bởi loader nào và dưới namespace nào?**

`SecurityManager` lịch sử trả lời: **Thao tác nhạy cảm này có được policy cho phép trong ngữ cảnh đang thực thi không?**

Ví dụ:

```text
CustomClassLoader
    |
    +--> findClass("plugin.Worker")
    |       |
    |       +--> defineClass(bytecode)
    |                 |
    |                 +--> runtime class identity
    |
    +--> loadClass("shared.api.Plugin")
            |
            +--> delegate to parent
```

Việc loader tạo namespace riêng cho `plugin.Worker` không tự hạn chế quyền đọc tệp hoặc gọi subprocess. Dù plugin nằm trong một loader riêng, code của nó vẫn chạy trong **cùng process** nếu không có boundary khác.

| Cơ chế | Nó làm tốt điều gì? | Điều không thể tự đảm bảo |
|---|---|---|
| Parent delegation | Dùng chung kiểu nền tảng và shared API | Không bảo đảm plugin không truy cập filesystem/network |
| Defining ClassLoader riêng | Class identity, dependency isolation, loader lifecycle | Không phải sandbox OS/runtime permissions |
| `ProtectionDomain`, `CodeSource` | Ghi nhận provenance/metadata và hỗ trợ các cơ chế tương ứng | Không tự biến class thành untrusted/sandboxed ở JDK mới |
| SecurityManager lịch sử | Một số permission checks khi được bật trong JDK hỗ trợ | Không là security boundary khả dụng từ JDK 24 |
| JPMS `exports` / `opens` | Kiểm soát truy cập giữa named modules và reflection/package resources | Không phải chặn hệ thống tệp, network hay mọi native APIs |
| Process/container/OS policy | Có thể áp đặt các quyền ở ranh giới hệ điều hành phù hợp | Cần cấu hình thật, không tự an toàn chỉ vì chạy trong container |

**Điểm rất dễ nhầm:** “Một plugin một loader” có thể giúp các phiên bản `com.vendor.Library` sống song song, nhưng không có nghĩa mỗi plugin có một tập OS permissions riêng.

## 6. ProtectionDomain, CodeSource và Permission vẫn xuất hiện — hiểu đúng ngữ cảnh

Các ví dụ custom loader lâu năm thường viết:

```java
ProtectionDomain domain =
        new ProtectionDomain(codeSource, permissions, loader, null);

Class<?> type = defineClass(
        binaryName, bytes, 0, bytes.length, domain);
```

Đây là **snippet minh họa**, cần có biến và imports thực tế trong một subclass `ClassLoader`.

Trong thiết kế lịch sử, `ProtectionDomain` có thể mang `CodeSource` (URL, certificates) và collection `Permission` được cấp; SecurityManager/AccessController dùng ngữ cảnh để đánh giá nhiều access checks.

Nhưng:

- **Tạo ProtectionDomain không tự bật SecurityManager**.
- Truyền `PermissionCollection` vào `defineClass` **không bảo đảm** JDK 24 áp dụng sandbox trên mỗi thao tác Java API.
- Với JDK 24, nhiều APIs từng phục vụ SecurityManager có behavior “degraded”; ví dụ theo hướng dẫn Oracle JDK 24/25, `Policy` không còn dùng để cấp quyền thực thi như mô hình cũ.
- `ProtectionDomain.getCodeSource()` vẫn hữu ích trong một số tác vụ provenance/diagnostics, nhưng provenance **khác** authorization.
- Lấy URL code source không chứng minh bytecode là đáng tin, không xác minh chữ ký và không thay thế bảo vệ supply chain.

Nếu đọc source/framework cũ có `SecureClassLoader`, `ProtectionDomain` hoặc permission checks, **không lập tức kết luận rằng nó an toàn như bản triển khai cũ ở JDK 8/11**. Phải xem phiên bản runtime và lớp bảo vệ khác của deployment.

## 7. AccessController.doPrivileged và checkPermission không còn đồng nghĩa kiểm soát quyền

Trong mô hình lịch sử, `AccessController.doPrivileged(...)` thường xuất hiện ở code thư viện cần thực hiện một thao tác được cấp quyền có kiểm soát, trong bối cảnh stack-based permission checking.

Ví dụ cũ:

```java
// Mẫu legacy để nhận diện khi đọc code; không khuyến nghị dùng mới.
return AccessController.doPrivileged(
        (java.security.PrivilegedAction<String>)
        () -> System.getProperty("example.setting"));
```

Đây là **snippet minh họa trong method** có kiểu `AccessController` được import; không phải chương trình độc lập.

**Trên JDK 24+:**

- Các `AccessController.doPrivileged(...)` variants còn tồn tại **chạy action trực tiếp**, như khi không có SecurityManager trong các phiên bản cũ.
- `AccessController.checkPermission(...)` theo đặc tả đã thay đổi sẽ **luôn ném `AccessControlException`**.
- `SecurityManager.check...` variants có thể **luôn ném `SecurityException`** trong API đã bị degraded.
- `System.getSecurityManager()` luôn trả **`null`**.
- `System.setSecurityManager(...)` luôn ném **`UnsupportedOperationException`**.

**Không suy diễn sai hai chiều:**

1. Vì `doPrivileged` còn chạy, **không** có nghĩa security policy cũ còn có hiệu lực.
2. Vì `checkPermission` ném exception, **không** có nghĩa toàn hệ thống đang được bảo vệ bởi policy; gọi trực tiếp API legacy đã đổi semantics không phản ánh access control của filesystem/network.

Từng API có behavior riêng. Đừng tự tổng quát “tất cả SecurityManager APIs đều no-op”; ở JDK 24 có phương thức no-op, phương thức trả `null`, và phương thức luôn ném exception.

## 8. SecurityException không chứng minh đã bật SecurityManager

`SecurityException` là loại exception phổ biến của Java được dùng cho nhiều ràng buộc **không phụ thuộc** việc có installed SecurityManager.

Ví dụ trong class loading:

```java
// Bên trong một custom ClassLoader subclass:
return defineClass("java.fake.Reserved", bytes, 0, bytes.length);
```

Đây là **snippet minh họa** (cần class-file bytes phù hợp). `ClassLoader#defineClass` có quy tắc riêng: custom/application loader thông thường không được định nghĩa class có tên bắt đầu `java.`. `SecurityException` có thể xảy ra **ngay cả khi `System.getSecurityManager() == null`**.

Một số nguyên nhân khác cần phân biệt:

- Không nhất quán signer certificates khi cùng loader định nghĩa classes trong một package.
- Custom library/framework tự ném `SecurityException` theo chính sách riêng.
- Một API/loader kiểm tra namespace/package/bytecode/môi trường và từ chối.
- Trên JDK lịch sử, SecurityManager thực sự từ chối một Permission.

Do đó chẩn đoán phải đọc **stack trace, nguyên nhân và JDK version**, không chỉ tên `SecurityException`.

### Một bảng so sánh ngắn

| Triệu chứng | Có chắc do SecurityManager? | Hướng kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Không | Tên, classpath/module path, defining loader, parent delegation |
| `SecurityException: Prohibited package name: java...` | Không | Quy tắc `ClassLoader#defineClass` dành cho `java.*` |
| `IllegalAccessError` | Không | Java access rules, runtime package và module access |
| `InaccessibleObjectException` | Không | Reflection/JPMS `opens` và caller module |
| `UnsupportedOperationException` ở `System.setSecurityManager` (JDK 24+) | Có liên quan API legacy bị vô hiệu hóa | Nâng cấp thiết kế, không tìm flag bật lại |
| Startup error khi `-Djava.security.manager=allow` trên JDK 24+ | Có liên quan cơ chế bị vô hiệu hóa | Xóa cấu hình legacy và thay cách ly khác |

Đừng “chữa” các lỗi này bằng cách cài SecurityManager mới. Điều đó không giải quyết class/module identity và từ JDK 24 cũng không khả thi.

## 9. JPMS là một ranh giới khác, không phải sandbox cho plugin

Java 9+ có **Java Platform Module System (JPMS)**, khai báo:

```java
module host.api {
    exports host.api;
}
```

```java
module plugin.alpha {
    requires host.api;
}
```

Đây là **hai file `module-info.java` minh họa ở hai modules khác nhau**, không ghép thành một file nguồn.

JPMS giúp:

- Tổ chức dependencies qua `requires`.
- Chỉ định public packages được truy cập từ module khác bằng `exports`.
- Quy định reflection/deep access qua `opens`.
- Phát hiện một số module graph/split package conflicts.
- Quản lý plugin modules trong `ModuleLayer` khi kiến trúc phù hợp.

Nhưng nếu plugin code trong `plugin.alpha` được chạy **trong cùng JVM process**, JPMS không tự ngăn nó gọi các API filesystem/network mà module đó có thể truy cập. Một module descriptor hợp lệ **không phải policy tài nguyên kiểu SecurityManager**.

### ClassLoader không tự “mở” mọi package của module

Một custom loader có thể tìm được class file, nhưng việc gọi reflection vào private members của một named module vẫn chịu quy tắc `opens`. Ngược lại, thêm `--add-opens` có thể cấp một phạm vi reflective access, **không** biến custom loader thành sandbox hoặc cấp một bộ quyền file độc lập.

Vì vậy ba câu hỏi phải tách biệt:

1. Loader nào tìm/định nghĩa class?
2. Caller module có quyền truy cập package/member không?
3. Code/process có được phép dùng tài nguyên hệ điều hành không?

Ba câu trả lời này thuộc những lớp kiểm soát khác nhau.

## 10. Những gì ứng dụng Java hiện đại nên làm thay vì SecurityManager

### A. Code đáng tin: dùng contract rõ và kiểm soát ở tầng ứng dụng

Nếu các plugin được **tin cậy và phát hành cùng tổ chức**, thiết kế:

- Shared SPI/DTO với API nhỏ và versioning rõ ràng.
- Host API chỉ cung cấp các thao tác plugin thật sự cần.
- Access checks ở service boundary (tenant, user, RBAC, quota, audit).
- Input validation, authentication/authorization ở các điểm tiếp nhận.
- Secrets không phát tán qua global static fields/system properties.
- Logging và exception handling nhất quán.

Đây là kiến trúc sạch và dễ kiểm thử, nhưng **không phải ranh giới chống plugin độc hại khi cùng process**. Code tùy ý vẫn có thể gọi APIs khác nếu môi trường cho phép.

### B. Plugin không đáng tin: process isolation

Nếu cần chạy code của khách hàng hoặc third-party không tin cậy, cân nhắc:

```text
Host Process
  |
  | validated RPC/IPC messages
  v
Plugin Worker Process
  |
  +-- OS user/permissions riêng
  +-- filesystem mounts hạn chế
  +-- network policy/egress hạn chế
  +-- CPU/memory/process quotas
  +-- short-lived credentials
  +-- timeout và kill/restart
```

Các biện pháp có thể gồm **containers**, VM isolation/hypervisors, Linux namespace/seccomp, Windows sandbox/job objects hoặc những cơ chế macOS phù hợp. Không một công nghệ nào tự an toàn bằng tên gọi; cần cấu hình và kiểm thử quyền thực tế.

Hãy thiết kế host↔plugin interface bằng dữ liệu đơn giản hoặc schema (JSON, Protobuf...) để tránh lộ object references nội bộ và dễ giới hạn tài nguyên.

### C. Least privilege ở OS/cloud boundary

- Không chạy plugin process với quyền administrator/root nếu không cần.
- Chỉ mount các thư mục phải đọc/ghi; phân tách read-only và writable storage.
- Giới hạn network egress, DNS, socket/listening ports theo yêu cầu.
- Dùng credentials thời hạn ngắn và scope hẹp.
- Giới hạn CPU, memory, số process/thread và thời gian chạy.
- Cô lập secrets và log dữ liệu nhạy cảm có kiểm soát.
- Xác minh chữ ký/artifact provenance, dependency scanning và update policy.

**SecurityManager không còn là nơi triển khai những yêu cầu đó trên Java 24+.**

## 11. Khi đang bảo trì framework/plugin cũ

Một số code đã viết từ JDK 8/11 có thể:

```java
@SuppressWarnings("removal")
static void legacyCheck() {
    SecurityManager sm = System.getSecurityManager();
    if (sm != null) {
        sm.checkPermission(
                new java.io.FilePermission(
                        "config.properties", "read"));
    }
}
```

Đây là **snippet legacy minh họa**, không phải biện pháp authorization cho code mới.

- Trên JDK 17 khi có SecurityManager thật, check có thể từ chối thao tác theo policy hiện hành.
- Trên JDK 24+, `System.getSecurityManager()` luôn trả `null`, nên nhánh `if` sẽ không chạy. Không có permission gate nào ở đoạn code đó.
- Nếu một thư viện tự gọi `AccessController.checkPermission` không điều kiện trên JDK 24+, nó có thể **ném exception không điều kiện**, khiến chương trình hỏng theo cách khác.
- Với code chứa `doPrivileged`, behavior vẫn có thể là chạy action ngay, nhưng không có mô hình stack-based permission gating cũ.

**Việc code cũ vẫn compile/runs không chứng minh mô hình bảo mật còn giữ nguyên.** Cần kiểm tra chính xác tác dụng của từng API trên JDK target.

### Kế hoạch migration thực tế

1. **Chốt runtime hiện tại và mục tiêu:** `java -version`, JDK vendor, patch release, options startup.
2. **Tìm cấu hình lịch sử:** `-Djava.security.manager`, `-Djava.security.policy`, policy files, custom `SecurityManager` classes.
3. **Tìm API deprecated:** `System.getSecurityManager`, `System.setSecurityManager`, `SecurityManager`, `AccessController`, `Policy` và các `Permission` checks.
4. **Phân loại mục đích:** code thật sự dùng enforcement, chỉ kiểm tra sự hiện diện, hay dùng `doPrivileged` vì compatibility?
5. **Xác định threat model:** code từ nguồn không tin cậy, sandbox tài nguyên, ngăn `System.exit`, restrict filesystem/network hay chỉ permission ở nghiệp vụ?
6. **Chọn cơ chế thay:** process/OS boundary cho mã không tin cậy; authorization/capability API cho code tin cậy; bytecode instrumentation nếu use case là intercept APIs trong một môi trường kiểm soát, với hạn chế riêng.
7. **Thử nghiệm JDK 24+:** không sử dụng startup flags bị cấm; test các code paths formerly secured.
8. **Dọn deprecated calls:** không chỉ tắt warnings; thay assumptions bị lỗi và update tests/runbooks.
9. **Kiểm tra security sau migration:** xác minh không mở thêm quyền ngoài dự kiến và không tạo bypass khi `getSecurityManager() == null`.
10. **Theo dõi phiên bản tiếp theo:** API có thể bị loại bỏ trong tương lai, nên tránh tích lũy code chỉ chạy vì compatibility tạm thời.

### Các lệnh hỗ trợ kiểm kê

```bash
java -version
javac -version

# Quét class/JAR được biên dịch để phát hiện APIs deprecated
# (tham số/khả năng hỗ trợ phụ thuộc phiên bản công cụ).
jdeprscan --release 17 path/to/application.jar
```

Lệnh `jdeprscan` là **ví dụ chẩn đoán**; thay `path/to/application.jar` bằng artifact thực. Kết quả phụ thuộc file được quét và JDK chứa công cụ. Không nên chỉ quét một JAR rồi kết luận mọi dynamic/reflection use of SecurityManager đã được tìm thấy; hãy kết hợp source/config search và kiểm thử.

Đừng dùng `jdeps --jdk-internals` như cách kiểm tra toàn bộ deprecated SecurityManager APIs; nó có mục đích khác (phân tích sử dụng internal JDK APIs).

## 12. Có thể dùng Java agent để chặn System.exit không?

Một use case từng dùng SecurityManager là chặn plugin gọi `System.exit(int)`. Theo tài liệu Oracle cho JDK 24+, khi SecurityManager đã bị vô hiệu hóa, có thể dùng **agent/bytecode instrumentation** trong những trường hợp cần kiểm soát calls:

```text
Class loading
    |
    +--> ClassFileTransformer
             |
             +--> tìm bytecode gọi System.exit(int)
             +--> thay bằng một đoạn ném RuntimeException
    |
    +--> JVM định nghĩa class đã được transform
```

Đây là mô hình công cụ, không phải giải pháp sandbox tổng quát.

**Cảnh báo:** Instrumentation có thể bị bỏ qua qua các lối gọi khác (native code, reflection, method handles, alternate APIs, attach/agent configuration, dynamic class loading...) nếu threat model không được xử lý đầy đủ. Nếu mã plugin thực sự **không đáng tin**, một agent chặn vài method **không thay thế OS isolation**.

Khi cần bảo vệ điều kiện “một plugin không thể kết thúc JVM của host”, giải pháp robust thường là **chạy plugin ở process riêng** để process-level actions không đồng nghĩa hủy cả host.

## 13. Lưu ý về bản thân ClassLoader và bytecode security

`ClassLoader` có ích cho namespace và plugin lifecycle, nhưng vẫn có những **ràng buộc nội tại** của JVM:

- Không phải loader ứng dụng nào cũng được `defineClass` tùy ý trong namespace `java.*`.
- JVM verifier/linker kiểm tra class-file format và type safety theo quy tắc JVM.
- Runtime class identity dựa trên **(binary name, defining loader)**.
- Runtime package identity dựa trên **(package name, defining loader)**, ảnh hưởng package-private access.
- JPMS `exports`/`opens` và module resolution vẫn áp dụng.
- Security-sensitive native libraries/OS privileges có những chính sách riêng.

Những quy tắc này vẫn quan trọng ở JDK 24 **mà không cần SecurityManager**. Nhưng sự tồn tại của verifier, `java.*` restriction hoặc module encapsulation **không biến ClassLoader thành sandbox quyền file/network**.

Ví dụ, `ClassLoader#defineClass` có thể ném `SecurityException` khi một custom loader cố định nghĩa `java.fake.Reserved`; sự kiện đó không nói rằng permission policy JDK 8 đã quay lại.

### Kết luận về các lớp bảo vệ

```text
Untrusted plugin code
    |
    +--> ClassLoader: namespace/classes/delegation
    |
    +--> JVM verifier, linking, type identity
    |
    +--> JPMS: modules/API/reflection access
    |
    +--> Host API authorization: business contract
    |
    +--> Process/OS/cloud controls: security boundary thực tế
```

Các lớp bảo vệ **bổ sung** cho nhau nhưng không cùng vai trò. Với JDK mới, **không đặt SecurityManager vào sơ đồ như một bước enforcement còn hoạt động**.

## 14. Những lỗi hiểu sai thường gặp

| Nhận định sai | Sửa lại |
|---|---|
| “Java 17 đã xóa SecurityManager.” | Java 17 **deprecated for removal**, cơ chế chưa bị xóa lúc đó. |
| “JDK 24 có class SecurityManager nên vẫn bật được.” | JDK 24 **permanently disabled**, startup/install đều bị chặn. |
| “Đổi `java.security.manager=allow` là đủ.” | JDK 24 coi flag cho phép/bật manager là **lỗi khởi tạo VM**. |
| “SecurityManager là tính năng bật mặc định của Java.” | Không nên giả định vậy, kể cả trong JDK cũ. |
| “ClassLoader riêng sandbox được plugin.” | Nó cách ly runtime type/namespace, **không** giới hạn mọi quyền OS. |
| “Có `ProtectionDomain` tức là file permission policy sẽ hoạt động.” | Permission enforcement phụ thuộc cơ chế/runtime; JDK 24 không dùng SecurityManager như trước. |
| “`AccessController.doPrivileged` còn chạy thì sandbox còn chạy.” | Ở JDK 24+, `doPrivileged` chạy action trực tiếp; không chứng minh permission gating. |
| “`AccessController.checkPermission` ném exception nghĩa là sandbox an toàn.” | JDK 24 có thể ném không điều kiện; không thay thế kiểm soát tài nguyên thật. |
| “JPMS `exports` và `opens` bảo vệ filesystem của plugin.” | Chúng quản lý module/package access, không phải quyền OS. |
| “SecurityException luôn từ SecurityManager.” | Có nhiều API có independent checks, kể cả `ClassLoader#defineClass`. |
| “Agent chặn System.exit là sandbox hoàn chỉnh.” | Một số API interception không đủ cho threat model mã độc. |
| “Chỉ cần tắt deprecation warnings là migrate xong.” | Phải thay security model và tests, không chỉ đổi compiler options. |

## 15. Câu hỏi tự kiểm tra

**1. JDK 17 đã làm gì với SecurityManager?** Đánh dấu **deprecated for removal** theo JEP 411; không phải loại bỏ ngay.

**2. Từ phiên bản nào SecurityManager bị permanently disabled?** Từ **JDK 24**, theo JEP 486.

**3. `System.getSecurityManager()` trả gì trên JDK 24+?** `null` theo API behavior mới.

**4. `System.setSecurityManager(...)` trên JDK 24+ có thể cài manager nếu cấu hình `allow` không?** Không. Method ném `UnsupportedOperationException`; flag cho phép/bật manager tại startup gây lỗi khởi tạo JVM.

**5. `AccessController.doPrivileged` có tự nâng quyền trên JDK 24 không?** Không. Nó thực thi action như khi không có SecurityManager, không cung cấp cơ chế permission-based escalation cũ.

**6. `AccessController.checkPermission(...)` trên JDK 24 có thể dùng để thay permission service nội bộ không?** Không. API này có behavior bị thay đổi, có thể ném `AccessControlException` không điều kiện; cần thiết kế authorization riêng.

**7. Một plugin có ClassLoader riêng có bị chặn đọc file tự động không?** Không. Loader quản lý nạp/định danh classes, không phải sandbox OS.

**8. `ProtectionDomain` có đủ để cấm plugin mở socket không?** Không, đặc biệt với SecurityManager bị vô hiệu hóa; cần boundary runtime/OS thực sự được enforce.

**9. `SecurityException` khi `defineClass("java.fake.X", ...)` có chứng minh SecurityManager đang bật không?** Không. Quy tắc namespace `java.*` của `defineClass` độc lập với installed manager.

**10. JPMS và SecurityManager có cùng nhiệm vụ không?** Không. JPMS giải quyết module/API access; SecurityManager lịch sử nhắm tới permission checks của một số thao tác tài nguyên.

**11. Khi migrate từ Java 8/11 sang JDK 24+, tìm những gì?** Startup flags/policy files, custom manager, calls tới `get/setSecurityManager`, `AccessController`, `Policy` và các lớp bảo vệ dự kiến còn hiệu lực.

**12. Cách an toàn hơn để chạy plugin không đáng tin trên JDK hiện đại là gì?** Cô lập bằng process/container/OS policy với quyền tối thiểu, resource limits, IPC contract và kiểm thử threat model.

## 16. Tài liệu chính thức và mốc phiên bản

- **JEP 411 — Deprecate the Security Manager for Removal** (gắn với JDK 17): https://openjdk.org/jeps/411
- **JEP 486 — Permanently Disable the Security Manager** (gắn với JDK 24): https://openjdk.org/jeps/486
- **Java SE 17 API — `SecurityManager`**, chú thích `@Deprecated(forRemoval=true)` và cách hoạt động legacy: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html
- **Java SE 17 API — `System.getSecurityManager` và `System.setSecurityManager`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- **Oracle JDK 25 Security Developer’s Guide — The Security Manager Is Permanently Disabled** (mô tả hành vi thay đổi có hiệu lực từ JDK 24): https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html
- **Oracle JDK 25 Migration Guide — Migrating from JDK 8 to Later JDK Releases**: https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html
- **Java SE 17 API — `ClassLoader`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `ProtectionDomain` / `AccessController`** (chỉ để hiểu mã legacy): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/AccessController.html

**Ghi nhớ:** **SecurityManager là một cơ chế lịch sử cần đọc theo phiên bản JDK**. JDK 17 **deprecated for removal**, còn **JDK 24+ vô hiệu hóa vĩnh viễn**. `ClassLoader`, `ProtectionDomain` và JPMS vẫn có ý nghĩa riêng nhưng **không thay thế sandbox quyền tài nguyên của SecurityManager**. Nếu bài toán là plugin không đáng tin, thiết kế process/OS isolation và kiểm soát quyền thực tế ngay từ đầu.

# Tránh lấy tên lớp hoặc đường dẫn tùy ý từ dữ liệu không tin cậy

## 1. Vấn đề và nguyên tắc an toàn

Một ứng dụng Java có plugin, ClassLoader, reflection hoặc xử lý file có thể nhận chuỗi từ HTTP request, tenant configuration, queue message hay metadata bên thứ ba. Chuỗi ấy trông vô hại khi còn là dữ liệu, nhưng trở thành **quyết định có quyền hạn** nếu chuyển trực tiếp vào `Class.forName`, `ClassLoader.loadClass`, `Files.readString`, `getResourceAsStream` hay `URLClassLoader`.

~~~java
// PHẢN VÍ DỤ: chỉ minh họa, không phải chương trình độc lập.
String className = request.getParameter("class");
Object plugin = Class.forName(className)
        .getConstructor().newInstance();

String path = request.getParameter("file");
String content = Files.readString(Path.of(path));
~~~

Đầu vào bên ngoài lúc này có thể chọn class để khởi tạo hoặc file để đọc, ngoài dự kiến nghiệp vụ. Java vẫn thực thi các quy tắc class loading và Java access control; tuy nhiên **khả năng tìm được class/file không tự chứng minh caller có quyền sử dụng nó**.

**Nguyên tắc:** Client chọn **mã chức năng hay ID tài nguyên đã cấp phép**, còn host quản lý ánh xạ đến implementation, ClassLoader, JAR, resource và đường dẫn thực.

Ví dụ tốt hơn:

~~~text
Client chọn "health" ──> AuthZ ──> Factory HealthJob đã đăng ký
Client chọn "guide"  ──> AuthZ ──> docs/guide.txt từ trusted registry
Client gửi FQCN hoặc ../../secret ──> từ chối
~~~

Chỉ kiểm tra cú pháp tên class, tên file hoặc regex **chưa phải** kiểm tra quyền nghiệp vụ.

## 2. Những đầu vào cần cảnh giác

| Input không tin cậy | API nhận input | Vấn đề |
|---|---|---|
| Tên binary class như `demo.plugin.Report` | `Class.forName(name)` | Input quyết định class được yêu cầu initialize |
| Tên class từ cấu hình ngoài | `loader.loadClass(name)` | Input quyết định class mà loader tìm |
| Tên provider | Reflection, dependency injection, `ServiceLoader` | Có thể khởi tạo code implementation không được phê duyệt |
| Resource name | `getResource` / `getResourceAsStream` | Đọc/tiết lộ resource nội bộ |
| File path | `Path.of(input)` và `Files.readString` | Path traversal, absolute path, symlink |
| URL nguồn class | `new URLClassLoader(urls, parent)` | Nạp bytecode từ artifact không đáng tin |
| URL cần mở | `URL.openStream()` | Truy cập nguồn bất ngờ/SSRF nếu ứng dụng cho phép |
| ZIP/JAR entry name | Giải nén file | Zip Slip, ghi file ngoài thư mục dự kiến |

Không phải các API trên tự nhiên có lỗ hổng; rủi ro là ứng dụng **trao quyền chọn đích cho untrusted input** mà thiếu kiểm soát nguồn và authorization.

## 3. Chọn chức năng qua allowlist, không qua FQCN

Thay vì cho user gửi `"java.lang.Runtime"`, `"demo.admin.ResetAll"` hoặc tên class bất kỳ, API nên chỉ nhận các **token đã định nghĩa** như `"health"` và `"version"`.

~~~java
// Mã minh họa, cần Job/HealthJob/VersionJob và các import.
Map<String, Supplier<Job>> allowed = Map.of(
        "health", HealthJob::new,
        "version", VersionJob::new
);
Supplier<Job> factory = allowed.get(userKey);
if (factory == null) {
    throw new IllegalArgumentException("Unsupported operation");
}
Job selected = factory.get();
~~~

Điểm an toàn đến từ **nguồn điều khiển map**: nếu client có thể gửi cả `key` lẫn FQCN rồi tự đăng ký entry mới, bảng này không còn là allowlist do host kiểm soát.

Đừng chỉ blacklist vài tên class nhạy cảm hoặc kiểm tra rằng một tên nằm dưới prefix `com.mycompany.plugins`. Một JAR không đáng tin có thể tự khai báo class cùng package đó. Nguồn bytecode, quyền đăng ký implementation và quyền chọn chức năng đều phải được kiểm soát.

Ngoài allowlist, vẫn cần AuthN/AuthZ: người dùng chỉ được thực thi các chức năng mà vai trò/tenant/scope của họ cho phép.

## 4. Chọn tài liệu qua key, không nhận raw path

Một endpoint tài liệu nên nhận `"guide"` hoặc `"rules"` thay vì `"docs/guide.txt"` hay `"../../config/secret.txt"` từ client.

~~~java
// Mã minh họa.
Map<String, String> documents = Map.of(
        "guide", "docs/guide.txt",
        "rules", "docs/rules.txt"
);
String allowedPath = documents.get(documentKey);
if (allowedPath == null) {
    throw new IllegalArgumentException("Unknown document");
}
~~~

Đường dẫn vật lý nằm trong config/registry chỉ host được quyền sửa. Nếu tài liệu chứa dữ liệu theo tenant, còn phải xác minh ID tài liệu thuộc tenant đã được xác thực. **Không nhận tenant ID từ query string mà không kiểm tra quyền**.

Ngay cả khi path đến từ allowlist, việc đọc vẫn nên kiểm soát root, symlink, loại file, dung lượng và vòng đời tài nguyên, nhất là khi nhiều bên có thể sửa filesystem.

## 5. Chương trình Java 17+ đầy đủ: factory và resource an toàn

Ví dụ độc lập sau tạo hai tác vụ, hai file trong thư mục tạm, kiểm tra token không hợp lệ và từ chối path traversal. Chương trình không dùng class name nhận từ client để nạp bytecode.

Tạo file **`SafeSelectionDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Supplier;

public final class SafeSelectionDemo {
    private SafeSelectionDemo() {
    }

    interface Job {
        String run();
    }

    static final class HealthJob implements Job {
        @Override
        public String run() {
            return "HEALTH_OK";
        }
    }

    static final class VersionJob implements Job {
        @Override
        public String run() {
            return "VERSION_1";
        }
    }

    private static final Map<String, Supplier<Job>> JOBS = Map.of(
            "health", HealthJob::new,
            "version", VersionJob::new
    );

    private static final Map<String, String> DOCS = Map.of(
            "guide", "docs/guide.txt",
            "rules", "docs/rules.txt"
    );

    static Job selectJob(String key) {
        Supplier<Job> factory = JOBS.get(key);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown job");
        }
        return factory.get();
    }

    static String selectDocument(Path root, String key)
            throws IOException {
        String relative = DOCS.get(key);
        if (relative == null) {
            throw new IllegalArgumentException("Unknown document");
        }
        return readConfinedFile(root, relative);
    }

    // Defense in depth, không chống tuyệt đối filesystem races.
    static String readConfinedFile(Path root, String input)
            throws IOException {
        if (input == null || input.isBlank()) {
            throw new SecurityException("Empty path");
        }

        final Path relative;
        try {
            relative = Path.of(input);
        } catch (InvalidPathException ex) {
            throw new SecurityException("Invalid path", ex);
        }

        if (relative.isAbsolute()) {
            throw new SecurityException("Absolute path denied");
        }

        Path base = root.toRealPath();
        Path candidate = base.resolve(relative).normalize();

        if (!candidate.startsWith(base)) {
            throw new SecurityException("Path escapes root");
        }

        Path step = base;
        for (Path part : base.relativize(candidate)) {
            step = step.resolve(part);
            if (Files.isSymbolicLink(step)) {
                throw new SecurityException("Symlink denied");
            }
        }

        Path real = candidate.toRealPath();
        if (!real.startsWith(base) || !Files.isRegularFile(real)) {
            throw new SecurityException("Not a confined regular file");
        }

        return Files.readString(real, StandardCharsets.UTF_8).strip();
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("safe-selection-");
        Path docs = root.resolve("docs");
        Path guide = docs.resolve("guide.txt");
        Path rules = docs.resolve("rules.txt");

        try {
            Files.createDirectories(docs);
            Files.writeString(guide, "GUIDE_OK\n",
                    StandardCharsets.UTF_8);
            Files.writeString(rules, "RULES_OK\n",
                    StandardCharsets.UTF_8);

            System.out.println("job health: "
                    + selectJob("health").run());
            System.out.println("job version: "
                    + selectJob("version").run());

            boolean classDenied = false;
            try {
                selectJob("java.lang.Runtime");
            } catch (IllegalArgumentException expected) {
                classDenied = true;
            }
            System.out.println("arbitrary class rejected: "
                    + classDenied);

            System.out.println("document guide: "
                    + selectDocument(root, "guide"));
            System.out.println("document rules: "
                    + selectDocument(root, "rules"));

            boolean documentDenied = false;
            try {
                selectDocument(root, "../secret");
            } catch (IllegalArgumentException expected) {
                documentDenied = true;
            }
            System.out.println("unknown document rejected: "
                    + documentDenied);

            boolean traversalDenied = false;
            try {
                readConfinedFile(root, "../private.txt");
            } catch (SecurityException expected) {
                traversalDenied = true;
            }
            System.out.println("path traversal rejected: "
                    + traversalDenied);
        } finally {
            Files.deleteIfExists(guide);
            Files.deleteIfExists(rules);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(root);
        }
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 17 trở lên**; mở terminal tại thư mục chứa file:

~~~bash
javac -encoding UTF-8 SafeSelectionDemo.java
java SafeSelectionDemo
~~~

Hai lệnh chạy trên Bash, PowerShell và Command Prompt khi JDK nằm trong `PATH`. Không cần thư viện ngoài.

**Stdout:**

~~~text
job health: HEALTH_OK
job version: VERSION_1
arbitrary class rejected: true
document guide: GUIDE_OK
document rules: RULES_OK
unknown document rejected: true
path traversal rejected: true
~~~

**Giải thích:** Hai factory được chọn qua key; `"java.lang.Runtime"` bị từ chối như một key không hợp lệ chứ không được truyền vào reflection. Tương tự, `"../secret"` không thuộc danh sách tài liệu; đoạn thử trực tiếp `readConfinedFile(root, "../private.txt")` phát hiện candidate thoát root sau chuẩn hóa và từ chối. Chương trình tạo/xóa dữ liệu thử trong thư mục tạm, không in đường dẫn phụ thuộc máy.

Ví dụ có chủ đích **không** nhận input thực từ mạng; nó tái hiện các giá trị caller có thể gửi để kiểm tra hành vi. Hàm path checking minh họa **một lớp bảo vệ bổ sung**, chưa phải giải pháp atomic chống thao túng filesystem đồng thời.

## 6. Vì sao normalize + startsWith chưa đủ?

Một cách kiểm tra hay thấy:

~~~java
// Minh họa: root và relative đã được cấu hình.
Path base = root.toAbsolutePath().normalize();
Path file = base.resolve(relative).normalize();

if (!file.startsWith(base)) {
    throw new SecurityException("Outside resource root");
}
~~~

Nó giúp từ chối path chứa `../` mà sau normalize thoát root, nhưng không giải quyết mọi tình huống:

- **Symlink:** `base/docs/link` có thể trỏ tới file/thư mục ngoài root; đường cú pháp vẫn có thể bắt đầu bằng `base`.
- **TOCTOU:** Giữa bước `Files.isSymbolicLink`/`toRealPath` và `Files.readString`, entry trên filesystem có thể bị thay.
- **Filesystem aliases:** Hard link, mount points, Windows drive/UNC path và case sensitivity có thể ảnh hưởng cách hiểu root.
- **Root bị attacker ghi:** Nếu adversary kiểm soát directory tree, họ có thể thay tên/entry ngay cả sau khi validation hoàn tất.

Demo gọi `toRealPath()`, từ chối symlink trong các thành phần dưới root và kiểm tra lại real path. Đây là **defense in depth**, không phải bảo đảm mạnh trước TOCTOU.

Đối với production, tốt nhất là **không cho untrusted caller kiểm soát filesystem root**. Nếu cần chống race trong directory được phép thay đổi, cân nhắc `SecureDirectoryStream` khi filesystem provider hỗ trợ hoặc cơ chế file descriptor/directory handle của OS. Có thể áp dụng process/container isolation với quyền chỉ đọc/ghi đúng thư mục đã cấp.

## 7. Những dạng path cần nhận diện

| Input | Vấn đề |
|---|---|
| `../secrets/data.txt` | Parent traversal |
| `/etc/passwd` | Absolute path Unix |
| `C:\Windows\...` | Drive path trên Windows |
| `\\server\share\...` | UNC network path |
| `docs/link/private.txt` | Symlink có thể thoát root |
| `%2e%2e%2fsecret` | Encoding của traversal nếu protocol decode |
| `..%252fsecret` | Double decoding giữa các tầng |
| `../../target.txt` trong ZIP | Zip Slip khi giải nén |

Không nên sửa bằng blacklist các chuỗi `..`, `%2e`, dấu `/` đơn thuần: cách decode, separators và Unicode normalization có thể thay đổi giữa các tầng. Decode ở đúng protocol boundary, validate **giá trị thực tế đưa vào filesystem**, ưu tiên chỉ nhận một ID nghiệp vụ thay vì path.

Nếu giải nén JAR/ZIP do người ngoài cung cấp, hãy kiểm soát mỗi destination theo root và xử lý symlink/overwrite đúng trước khi ghi file. Không ghép `entry.getName()` thẳng với target directory mà không kiểm soát.

## 8. ClassLoader resource visibility khác quyền người dùng

`ClassLoader.getResource(name)` tìm URL; `getResourceAsStream(name)` mở stream; `getResources(name)` có thể liệt kê nhiều resources cùng tên. Đây là **lookup API**, không phải phương thức authorization cho người dùng cuối.

~~~java
// Minh họa: cần InputStream và một biến loader hợp lệ.
try (InputStream input =
             loader.getResourceAsStream("internal/settings.json")) {
    // Có stream không có nghĩa được trả nội dung cho mọi HTTP caller.
}
~~~

Một loader có thể nhìn thấy resource nội bộ nhưng client **không có quyền** xem nó. Nếu bạn chuyển trực tiếp input `"internal/settings.json"` từ request vào `getResourceAsStream` và trả bytes ra ngoài, bạn có thể tạo đường tiết lộ dữ liệu.

Cũng cần nhớ:

- `ClassLoader.getResource("pkg/name.txt")` thường nhận path từ root, không có dấu slash đầu.
- `SomeClass.class.getResource("name.txt")` hiểu tên tương đối với package class, còn `"/pkg/name.txt"` là root-relative.
- Parent-first resource lookup có thể trả resource của parent khi trùng tên với child; named modules còn có encapsulation/`opens`.
- Việc loader tìm được file trong JAR **không** chứng minh user được truy xuất, kể cả khi tên file khó đoán.

**Cách an toàn:** Resource được chỉ định từ trusted map/config theo **ID và quyền**; tránh để caller chọn mọi resource mà loader nhìn thấy.

## 9. Không nhận URL plugin JAR từ request

Phản ví dụ:

~~~java
// KHÔNG AN TOÀN: input được phép quyết định nguồn code và class.
URL artifact = new URL(requestUrl);
try (URLClassLoader child = new URLClassLoader(
        new URL[] {artifact},
        ClassLoader.getSystemClassLoader())) {
    Object plugin = child.loadClass(requestClassName)
            .getConstructor().newInstance();
}
~~~

Đây là đoạn minh họa, không phải chương trình chạy độc lập. Nếu `requestUrl`/`requestClassName` đến từ nơi không tin cậy, host có thể nạp và chạy bytecode ngoài chính sách của ứng dụng.

Một chuỗi cấp phép tốt hơn:

~~~text
pluginId từ client
      |
      v
AuthN / AuthZ và tenant policy
      |
      v
Trusted registry do host quản lý
      |
      v
Artifact ID + version + content digest đã duyệt
      |
      v
Xác minh nguồn/chữ ký/checksum theo trust policy
      |
      v
Nạp loader từ artifact đã phê duyệt
      |
      v
Provider triển khai shared API của host
~~~

Không nên coi “JAR có chữ ký” là bằng chứng code không thể làm hại hệ thống. Chữ ký hỗ trợ xác minh nguồn gốc/toàn vẹn theo chính sách tin cậy, còn review, runtime permissions, update policy và isolation vẫn là vấn đề riêng.

## 10. Class.forName có thể khởi tạo class

Với overload:

~~~java
// Mã minh họa; typeName đã được chọn từ trusted registry.
Class<?> type = Class.forName(typeName);
~~~

Java yêu cầu initialization của class (nếu chưa initialize). Static initializers và static field initializers có thể thực thi, **trước cả bước gọi constructor tường minh**.

~~~java
// Mã minh họa, không phải class chính của demo.
public final class SampleComponent {
    static {
        System.out.println("Static initializer runs");
    }

    public SampleComponent() {
        System.out.println("Constructor runs");
    }
}
~~~

Overload `Class.forName(name, false, loader)` không yêu cầu initialization ngay nhưng **không phải authorization**: caller vẫn chọn class được tải, và việc instantiate/call về sau có thể chạy mã.

Không nên dùng phương pháp “chỉ cho phép tên class bắt đầu bằng `demo.trusted.`”. Tác giả JAR không tin cậy có thể tự tạo class với tên đó. **Source artifact và quyền triển khai** quan trọng hơn một tiền tố package.

## 11. ServiceLoader và discovery cũng cần nguồn tin cậy

`ServiceLoader.load(Service.class, trustedLoader)` tìm provider theo service descriptor, ví dụ `META-INF/services/demo.api.Service`. Nếu attacker có thể thay JAR/descriptor, họ có thể làm framework phát hiện một provider class khác.

`ServiceLoader` kiểm tra quy tắc provider/service type, nhưng **không đánh giá động cơ bảo mật của implementation**. Vì thế cần bảo vệ quyền cài plugin, sửa artifact, thay service registry và cấu hình loader. Nếu chỉ thay TCCL sang một loader chưa được tin cậy, mọi API dựa vào TCCL cũng có thể khám phá sai nguồn.

Shared interface/DTO nên được host/parent loader định nghĩa để tránh hai bản API class identity khác nhau. Đừng cho metadata của user tự chọn defining loader hoặc URL của service provider.

## 12. ClassLoader không phải sandbox

ClassLoader quản lý **loading, namespace, delegation, class identity và resource lookup**. Nó không mặc định chặn plugin gọi filesystem/network APIs theo quyền của JVM process, không giới hạn CPU/memory và không thu hồi mọi tác dụng của mã đã chạy khi `URLClassLoader.close()` được gọi.

- Parent-first delegation không tương đương “plugin ít quyền hơn”.
- JPMS `exports`/`opens` chủ yếu phục vụ encapsulation và reflective access, không thay thế OS isolation.
- Trong Java 17, `SecurityManager` đã **deprecated for removal**; không nên giả định một security manager tự động bảo vệ plugin trong JVM hiện đại.
- Với mã thực sự không tin cậy, cần **process/container isolation**, giới hạn quyền filesystem/network, resource quotas và giao tiếp qua API/IPC có xác thực.

Allowlist class/path là lớp phòng vệ cần thiết nhưng **không thể biến bất kỳ bytecode nào thành an toàn** nếu bạn cố thực thi nó với quyền của host.

## 13. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `Class.forName(userInput)` | User chọn class được yêu cầu initialize | Token → trusted factory |
| Chỉ regex FQCN hoặc prefix package | Tên hợp lệ không chứng minh quyền và nguồn code | Trusted registry + artifact policy |
| `Path.of(userInput)` rồi đọc ngay | Absolute path, traversal, symlink | Document ID + root/OS permission |
| Chỉ dùng `normalize().startsWith(root)` | Không chống symlink/TOCTOU | Root ownership, directory-handle/isolation |
| Nhận tùy ý `getResourceAsStream(name)` | Có thể lộ resource nội bộ | Allowed resource names + AuthZ |
| Client tự cung cấp URL plugin | Có thể nạp bytecode không đáng tin | Approved artifact registry + version pin |
| Coi `ServiceLoader` là trust validator | Provider hợp lệ về type vẫn có thể độc hại | Kiểm tra source và quyền triển khai |
| Coi loader là sandbox | Code plugin có quyền process | Isolate khi không tin bytecode |
| Trả stack trace/path cho client | Rò thông tin filesystem/module | Error code chung, log nội bộ |
| Khi validation fail tự fallback rộng hơn | Fail-open, phá chính sách | Từ chối và ghi nhận lỗi |
| Để user sửa map key→class | User vòng qua allowlist | Cấu hình chỉ bên tin cậy được sửa |

## 14. Checklist bảo vệ ClassLoader boundary

1. **Nguồn dữ liệu:** class name/path/plugin URL có thể bị ai sửa?
2. **AuthZ:** caller/tenant được phép gọi tính năng, xem tài liệu hoặc cài plugin chưa?
3. **Registry:** map ID → class/resource/artifact có do bên tin cậy kiểm soát không?
4. **Class loading:** có chỗ nào dùng FQCN trực tiếp từ request với `Class.forName`/`loadClass` không?
5. **Artifact:** JAR được pin version/content digest và provenance không?
6. **Resource:** có thể dùng key thay vì raw path/resource name không?
7. **Filesystem:** root có thuộc quyền attacker không; có xử lý absolute/traversal/symlink/race không?
8. **Module:** có kiểm tra module encapsulation nhưng vẫn giữ authorization riêng không?
9. **Lifecycle:** stream, thread, TCCL, listener và loader có được dọn đúng không?
10. **Isolation:** cần tiến trình/container riêng nếu bytecode không đáng tin không?
11. **Observability:** các trường hợp reject có log đủ dùng nhưng không lộ secret không?
12. **Tests:** đã thử `../`, absolute path, symlink, key lạ, artifact chưa phê duyệt chưa?

## 15. Tự kiểm tra

**Câu 1.** Regex xác nhận `"java.lang.Runtime"` là tên lớp hợp lệ. Có thể truyền trực tiếp vào `Class.forName` từ request không?

**Đáp án:** Không. Hợp lệ cú pháp không phải quyền chọn implementation; dùng allowlist token và kiểm tra quyền.

**Câu 2.** Vì sao `Class.forName(name, false, loader)` không làm tên class tùy ý trở thành an toàn?

**Đáp án:** Nó chỉ tránh yêu cầu initialization ngay; việc nạp/chọn class vẫn do input quyết định, và code có thể chạy trong bước sử dụng về sau.

**Câu 3.** `normalize().startsWith(root)` đã chống mọi path escape chưa?

**Đáp án:** Chưa. Symlink và race giữa check/open là các giới hạn quan trọng; cần root ownership và hỗ trợ từ filesystem/OS.

**Câu 4.** Loader tìm thấy `internal/secret.json` có nghĩa HTTP user được xem file ấy không?

**Đáp án:** Không. Loader visibility khác với authorization của user.

**Câu 5.** Vì sao nên nhận `"guide"` thay vì `"docs/guide.txt"`?

**Đáp án:** Host tự chọn đường dẫn từ danh sách tài liệu được phê duyệt, thay vì cho client quyết định path.

**Câu 6.** Plugin JAR được tải qua `URLClassLoader` có tự bị hạn chế network/file permissions không?

**Đáp án:** Không. ClassLoader không phải sandbox; code không tin cậy cần process/container/OS isolation.

**Câu 7.** Cùng package prefix `com.trusted.plugins` có đủ xác minh class an toàn không?

**Đáp án:** Không. Package name do tác giả bytecode tự khai báo; phải kiểm soát artifact nguồn và quyền triển khai.

## 16. Tài liệu chính thức

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource` và resource lookup.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String)): initialization trong overload mặc định.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `toRealPath`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`, `isSymbolicLink`.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): relative directory operations.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URLs và vòng đời loader.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): thay đổi SecurityManager ở Java 17.

**Ghi nhớ:** **Không để dữ liệu chưa tin cậy trực tiếp chọn tên class, đường dẫn resource/file hay URL nguồn plugin.** Dùng **business key + authorization + allowlist do host sở hữu**; kiểm soát filesystem traversal, symlink/TOCTOU và quyền OS khi cần file. ClassLoader tổ chức việc nạp class, **không phải ranh giới bảo mật cho mã tùy ý**.
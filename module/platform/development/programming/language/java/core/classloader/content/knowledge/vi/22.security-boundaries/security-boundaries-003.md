# Kiểm soát nguồn JAR, tính toàn vẹn và phụ thuộc được phép

Ứng dụng Java có thể nạp bytecode từ JAR thông qua `URLClassLoader`, plugin framework, `ServiceLoader` hoặc `ModuleLayer`. Tuy nhiên **“nạp được class” không có nghĩa “JAR đáng tin và được phép thực thi”**. Trước khi cho code từ bên ngoài chạy trong JVM, cần kiểm soát đồng thời **nguồn xuất bản**, **định danh artifact và phiên bản**, **tính toàn vẹn bytes**, **chuỗi phụ thuộc** và **quyền thực thi ở runtime**.

Đây là một vấn đề **ranh giới bảo mật và software supply chain**. Một JAR có checksum đúng vẫn có thể chứa mã độc hoặc CVE; một JAR ký số hợp lệ vẫn có thể được ký bởi người không được tổ chức phê duyệt; một JAR được phép nhưng mang theo dependency ngoài allowlist vẫn có thể khiến JVM thực thi code ngoài ý định.

**Nguyên tắc xuyên suốt:** Xây dựng **cổng kiểm tra artifact** trước class loading; chỉ tạo loader/define module từ **đúng bản bytes đã được chấp thuận**. Nếu một điều kiện không kiểm chứng được, **fail closed**, không fallback sang repository hoặc đường nạp khác để “chạy cho được”.

## 1. Ba lớp kiểm soát phải tách bạch

| Câu hỏi | Dữ liệu cần có | Điều nó không tự chứng minh |
| --- | --- | --- |
| **Nguồn JAR có được phê duyệt?** | Publisher, repository, tọa độ artifact, version, chính sách release | Nội dung có nguyên vẹn hay không |
| **Artifact có đúng bản đã duyệt?** | SHA-256 pin từ trusted policy, chữ ký và signer trust khi yêu cầu | Code không chứa lỗi hoặc hành vi độc hại |
| **Có được phép dùng các phụ thuộc này?** | Full resolved dependency graph, versions, hashes, scopes, allowlist runtime | Code không dùng reflection, native library hoặc tải thêm thứ khác |

Ba lớp này tạo một đường dẫn kiểm soát:

~~~text
Publisher / CI build đáng tin
            |
            v
   Repository được phép
            |
            v
    JAR + metadata phát hành
            |
            v
        POLICY GATE
        /    |      \
       v     v       v
   Origin   SHA-256  Graph dependency
       \     |       /
        \    |      /
         v   v     v
       staging được bảo vệ
               |
               v
      ClassLoader / ModuleLayer
               |
               v
       Runtime isolation + audit
~~~

Không được gộp ba câu hỏi thành một cờ `isTrusted=true` không rõ xuất xứ. Nếu JAR đi qua nhiều lớp (CI, artifact registry, cache triển khai, host plugin manager), mỗi lớp cần biết **ai là nguồn sự thật** cho digest/identity/phê duyệt và ai có quyền cập nhật.

### Những nguy cơ cần bao phủ

- **Tampering:** một file JAR bị thay đổi sau thời điểm build hoặc sau khi phê duyệt.
- **Publisher compromise:** tài khoản phát hành hoặc CI bị chiếm, tạo một bản trông hợp lệ về tên và phiên bản.
- **Dependency confusion:** artifact thuộc namespace nội bộ bị giải từ public repository do trùng tên hoặc mapping sai.
- **Typosquatting:** artifact có tên gần giống thư viện hợp lệ.
- **Transitive dependency ngoài ý muốn:** một dependency trực tiếp kéo theo package mới chưa được duyệt.
- **Version drift/downgrade:** phiên bản hoặc bytes thay đổi vì ranges, snapshot, mirror, cache hay lock thiếu.
- **Runtime graph drift:** `Class-Path` trong manifest, loader được thêm URL, service provider, native library hoặc downloader đưa thêm code vào process.
- **Vulnerability ở artifact nguyên vẹn:** JAR đúng hash nhưng phiên bản vốn có CVE, backdoor, rủi ro license hoặc quyền hoạt động vượt mức cần thiết.

HTTPS/TLS và repository nội bộ giảm nhiều nguy cơ, nhưng **không tự xác nhận publisher/artifact code an toàn**. Một endpoint có TLS hợp lệ vẫn có thể chứa bản phát hành bị đầu độc.

## 2. Chính sách nguồn (origin/identity allowlist)

Một cơ chế chấp nhận JAR không nên chỉ kiểm tra đuôi file `.jar` hoặc tên thư mục. Với Maven-style artifacts, cần ghi nhận **tọa độ và nguồn**:

~~~yaml
# Minh họa một chính sách tự thiết kế, KHÔNG phải schema Maven/Gradle.
artifact: com.acme.plugins:greeter:1.0.0
repository: internal-approved-registry
publisher: approved-release-identity
sha256: "digest-64-hex-được-lấy-từ-trusted-policy"
runtime_dependencies:
  - com.acme.api:plugin-contract:2.3.0
  - org.example:safe-parser:4.2.1
manifest_class_path: deny
native_libraries: deny
network_code_downloads: deny
~~~

Đây chỉ là **pseudocode cấu hình**, chuỗi `sha256` minh họa chỗ đặt digest đã duyệt, không phải digest thực. Policy thực tế cần schema và validator cụ thể, versioning, approver và quy trình cập nhật đáng tin.

**Cần chốt ít nhất:**

1. **Group/artifact/version/classifier** (nếu có), không chấp nhận một JAR có tên đẹp nhưng thiếu danh tính phát hành.
2. **Registry/repository được phép**, mapping namespace nội bộ rõ ràng, credential và quyền publish tối thiểu.
3. **Signer hoặc provenance identity**, nguồn evidence độc lập đủ mạnh để liên kết digest với bản phát hành đúng.
4. **SHA-256 của từng artifact** ở bản deploy, không chỉ metadata package.
5. **Allowlist cho toàn bộ dependency graph**, gồm direct, transitive, runtime và mọi thành phần được nhúng.
6. **Version và policy revocation**, để một bản từng được chấp nhận có thể bị gỡ khi phát hiện compromise hoặc CVE nghiêm trọng.
7. **Audit evidence**: ai đã approve, lúc nào, manifest đã kiểm tra, digest cuối, loader/plugin nào tiêu thụ.

### Không so đường dẫn bằng chuỗi thô

Sai về nguyên tắc:

~~~java
// Fragment sai: "/approved-evil/x.jar" cũng bắt đầu bằng "/approved".
if (jarPath.toString().startsWith("/approved")) {
    allow();
}
~~~

Đây là **fragment phản ví dụ**, không phải chương trình độc lập. Trong Java, nên kiểm tra đường dẫn đã canonical hóa bằng `Path.toRealPath()` và `Path.startsWith(Path)`, xem xét symlink, filesystem permissions và writable directories.

**Nhưng đường dẫn đúng chưa có nghĩa file không đổi:** Giữa lúc tính checksum và lúc `URLClassLoader` mở file có thể xảy ra **TOCTOU (time-of-check/time-of-use)**. Môi trường production cần **staging immutable/read-only do bên tin cậy kiểm soát**, bảo đảm loader đọc đúng bytes vừa verify; không cho một writer chưa được kiểm soát thay file giữa hai bước.

## 3. Kiểm tra tính toàn vẹn bằng SHA-256

Với JAR `greeter-1.0.jar`, tính digest trên **toàn bộ bytes JAR**:

~~~text
SHA256(actual-final-JAR-bytes) == trustedExpectedDigest
~~~

Một bản build khác có thể chứa bytecode tương đương nhưng ZIP metadata, timestamp hoặc thứ tự entry khác, khiến **hash toàn JAR khác nhau**. Điều này không nhất thiết là tấn công, nhưng **artifact cuối đã được pin** thì phải khớp toàn bộ bytes.

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\approved\greeter-1.0.jar -Algorithm SHA256
~~~

Trên Linux:

~~~bash
sha256sum approved/greeter-1.0.jar
~~~

Trên macOS có thể dùng `shasum -a 256`. Các lệnh này **chỉ tính** digest hiện tại; tự chúng chưa quyết định hash ấy đáng tin hay không.

### Hash kỳ vọng phải đến từ đâu?

Đây là bẫy quan trọng nhất của checksum: Nếu kẻ tấn công kiểm soát endpoint phát tán và cung cấp cả `plugin.jar` lẫn `plugin.jar.sha256` thì việc hai file khớp nhau **không chứng minh điều gì về publisher**. Kẻ tấn công chỉ cần thay **cả hai**.

Giá trị kỳ vọng phải được lấy theo policy độc lập, chẳng hạn:

- Trusted build/release manifest do pipeline được phê duyệt tạo và ký, gắn với tọa độ artifact.
- Signed attestation với trust root và builder/publisher identity được tổ chức xác minh.
- Cơ sở dữ liệu triển khai có quyền ghi/phê duyệt chặt, chỉ lưu digest đã review từ quy trình tin cậy.
- Giá trị pin được truyền out-of-band qua kênh quản trị đã xác thực.

**Hash không phải chữ ký.** SHA-256 trả lời “bytes có đúng với pin hay không”, không trả lời “ai đã xuất bản” nếu pin không có provenance. `String.hashCode()`, CRC32 hay một file MD5 cũ không thay thế SHA-256 cho kiểm soát tính toàn vẹn đối kháng hiện đại.

### So trên artifact cuối

Nếu JAR bị repack, shaded, re-signed, stripped hoặc biến đổi sau khi hash, cần phê duyệt digest **đúng artifact được đưa vào loader**. Không dựa vào checksum của source JAR trước biến đổi để tuyên bố fat JAR mới đã được xác minh.

Nếu dependency có nhiều JAR, **mỗi JAR phải có artifact identity và digest**. Hash một file plugin không tự kiểm soát những thư viện bên ngoài mà nó sẽ nạp.

## 4. Chữ ký JAR: hợp lệ về mật mã chưa đủ “được tin”

Java JDK cung cấp `jarsigner` để ký và kiểm tra JAR. Với một JAR **có ký số**, có thể điều tra bằng:

~~~bash
jarsigner -verify -strict -verbose -certs approved/greeter-1.0.jar
~~~

Đây là lệnh tham khảo cho JAR có chữ ký và trust policy thực tế; JAR ví dụ ở phần 7 mặc định **chưa được ký**.

Cần kiểm tra **nhiều điều kiện**, không chỉ nhìn một dòng output:

- **Signature integrity:** dữ liệu và digest những entry được ký không bị thay; signature block xác minh đúng về mật mã.
- **Coverage:** mọi entry yêu cầu bảo vệ đã được ký chưa? Có entry bị thêm sau khi ký hoặc không được ký?
- **Signer identity:** certificate/public key có thuộc tổ chức publisher cho phép không? Có trust anchor/key pin thích hợp không?
- **Trust chain và thời hạn:** certificate chain, algorithm policy, key strength, timestamp và cảnh báo liên quan có thỏa quy tắc?
- **Artifact binding:** signer đã ký đúng version/digest và release channel được chấp nhận chưa?
- **Revocation/review:** có thông báo thu hồi hoặc incident liên quan signer/artifact không?

`-strict` có thể khiến cảnh báo nghiêm trọng ảnh hưởng exit status, nhưng lệnh kiểm tra và policy trust cần được thiết kế rõ. Một JAR **không được ký** không tự được approve chỉ vì tool không in lỗi tuyệt đối. Ngược lại, một chữ ký do bất kỳ certificate nào tạo cũng **không** đủ để mở quyền chạy.

**Đừng nhầm `new JarFile(file, true)` với một verifier toàn diện.** `JarFile` hỗ trợ verify chữ ký của các entry ký khi chúng được đọc. Nó không tự động đọc hết tất cả entry hoặc áp chính sách signer/trust của doanh nghiệp. Nếu muốn xác thực signer phải có một bước độc lập, đầy đủ và fail-closed.

| Cơ chế | Khả năng | Giới hạn |
| --- | --- | --- |
| SHA-256 + pin đáng tin | Khớp chính xác bytes đã duyệt | Không chứng minh code không có CVE, không xác nhận origin nếu pin không tin |
| Chữ ký JAR + trust policy | Ràng buộc chữ ký/entry với signer được phê duyệt | Không bao phủ dependency ngoài hay quyền runtime |
| Signed provenance | Bằng chứng đã xác minh về builder/source/release workflow | Không chứng minh mọi hành vi code là an toàn |
| SBOM + SCA | Inventory dependencies và phát hiện lỗ hổng đã biết | Có thể thiếu shaded/dynamic components; không thay checksum |
| Isolation/least privilege | Hạn chế tác động khi code chạy | Không tự chứng minh artifact nguyên vẹn |

## 5. Kiểm soát mọi dependency được phép

Một plugin có thể có đồ thị:

~~~text
com.acme:greeter-plugin:1.0.0
 ├─ com.acme:plugin-api:2.3.0
 ├─ org.example:parser:4.2.1
 │    └─ org.example:codec-core:1.8.0
 └─ org.example:logging:3.1.0
~~~

Nếu chỉ approve `greeter-plugin` và `parser`, phiên bản `codec-core` bắc cầu có thể vẫn được resolve và thực thi. **Policy phải bao phủ kết quả resolve cuối**, không chỉ khai báo direct dependency.

Các nguồn dependency cần quản lý:

1. **Build-time:** Maven/Gradle resolve POM, BOM, dependency substitutions, conflict resolutions và transitive graph.
2. **Runtime:** classpath/module path thực tế khi process chạy, bao gồm injected JAR ngoài kết quả build.
3. **Manifest:** thuộc tính `Class-Path` của JAR có thể mở rộng đường tìm class/resource của một `URLClassLoader`.
4. **Loader động:** `URLClassLoader.addURL`, custom loader, plugin resolver, `ModuleFinder`/`ModuleLayer`.
5. **Discovery:** `META-INF/services`, `ServiceLoader` hoặc framework reflection tạo provider triển khai.
6. **Code nhúng và native:** shaded/fat JAR, nested JAR, JNI, `System.load`/`System.loadLibrary` hoặc downloader tải mã trong runtime.

**Tên JAR không đủ làm dependency identity.** Cần version, coordinate, digest, source và scope tương ứng. Những thư viện shaded có thể không còn là JAR độc lập, nhưng vẫn cần inventory các component thực sự được đóng trong artifact.

### API chung giữa host và plugin

Host và plugin trao đổi object thông qua interface/DTO/exception type dùng chung. Với class/interface, **type identity = (binary name, defining class loader)**. Nếu plugin đóng gói và tự định nghĩa một bản `com.acme.api.Task` thay vì dùng định nghĩa API của host, host có thể gặp `ClassCastException` hoặc provider không hợp lệ dù cùng tên.

Một class loading policy thường có dạng:

~~~text
java.* / platform modules         → runtime/platform loaders
com.acme.api.*                    → shared/parent loader do host kiểm soát
plugin.impl.*                     → plugin loader đã phê duyệt
approved private dependencies     → loader plugin theo policy version
unknown packages/JAR providers    → reject hoặc lookup đã kiểm soát
~~~

Đây là **mô hình kiến trúc**, không phải behavior tự động của Java. Khi cần child-first cho implementation, vẫn phải bảo đảm parent-first cho API được chia sẻ. Ranh giới supply chain và type identity bổ sung cho nhau: JAR đúng hash nhưng nạp API sai loader vẫn có thể phá giao tiếp.

### Manifest Class-Path và dynamic lookup

`URLClassLoader` hỗ trợ các URL JAR, thư mục và cơ chế class/resource lookup. Một manifest có:

~~~text
Class-Path: lib/extra.jar
~~~

có thể đưa thêm dependency vào đường tra cứu của loader theo cách xử lý manifest của Java. Nếu hệ plugin không hỗ trợ kiểu mở rộng này, **từ chối JAR chứa thuộc tính `Class-Path`**; nếu hỗ trợ, resolve URL an toàn và verify **từng artifact phụ** trước khi nạp. Đừng tin rằng chỉ truyền một URL vào constructor là toàn bộ class loading graph chỉ có một file.

## 6. Quy trình phê duyệt từ build tới runtime

~~~text
Source + dependency policy được review
        |
        v
CI/toolchain/runner được kiểm soát
        |
        v
Resolve từ repository được phép
        |
        +-- pin direct/transitive versions
        +-- kiểm tra hashes/signers
        +-- SCA / license policy
        +-- SBOM / provenance metadata
        |
        v
Build artifact cuối
        |
        v
Promotion/approval, signed release manifest
        |
        v
Immutable artifact cache/staging
        |
        v
Check digest/signature + dependency closure
        |
        v
Instantiate ClassLoader / ModuleLayer
        |
        v
Runtime restrictions + audit + revocation
~~~

Các yếu tố quan trọng:

- **Reproducible build** giúp so sánh kết quả từ source và toolchain, nhưng vẫn phải kiểm soát build scripts và dependency artifacts.
- **SBOM** nên bao gồm thư viện direct, transitive, shaded hoặc bundled theo khả năng phân tích build và runtime. Nó có thể không thấy các dependency được nạp động.
- **SCA** nên liên tục kiểm tra advisory/CVE và chính sách sử dụng; lỗ hổng mới có thể khiến một artifact đã duyệt phải bị thu hồi.
- **Provenance/attestation** cần xác minh trust root, builder/publisher identity và artifact digest; không tin chỉ vì có tệp tên `provenance.json`.
- **Phê duyệt runtime** phải đối chiếu đúng bytes đã được đặt vào production, không chỉ lời khai rằng CI từng kiểm tra một bản tương tự.

Khi gate từ chối JAR, không được im lặng tìm bản khác ở public registry. Đó là đường đi phổ biến khiến **dependency confusion** hoặc downgrade.

## 7. Java 17 runnable: kiểm tra JAR trước URLClassLoader

Ví dụ học tập có các chính sách cụ thể:

- Chỉ nhận file `greeter-1.0.jar` trong thư mục `approved`.
- Canonicalize đường dẫn và xác nhận đúng vị trí.
- Stream toàn file để tính SHA-256, so với pin hex 64 ký tự do caller cung cấp.
- Từ chối manifest có `Class-Path`.
- Chỉ khi các điều kiện trên đều đạt mới tạo `URLClassLoader` và gọi class `plugin.Greeter`.
- Không có dependency ngoài `java.base`, vì vậy parent `ClassLoader.getPlatformClassLoader()` đủ cho mục tiêu demo.

**Giới hạn:** Chương trình chưa xác thực certificate/trusted signer, chưa validate transitive graph và chưa chống TOCTOU nếu thư mục có writer không tin cậy. Nó **không** tạo sandbox hoặc bảo vệ trước một plugin vốn đã độc hại. Đây là ví dụ về **thứ tự kiểm tra trước khi tải class**, không phải một trình quản lý supply chain production đầy đủ.

Cấu trúc file:

~~~text
jar-gate-demo/
├── JarGate.java
├── src/
│   └── plugin/
│       └── Greeter.java
├── classes/                     (thư mục output)
└── approved/
    └── greeter-1.0.jar          (JAR được tạo ở bước build)
~~~

### File 1: src/plugin/Greeter.java

~~~java
package plugin;

public final class Greeter {
    public static String message() {
        return "hello from pinned JAR";
    }
}
~~~

### File 2: JarGate.java

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarGate {
    private static final String APPROVED_FILE = "greeter-1.0.jar";

    private static byte[] sha256(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return digest.digest();
    }

    private static void checkManifest(Path jar) throws Exception {
        try (JarFile file = new JarFile(jar.toFile())) {
            Manifest manifest = file.getManifest();
            if (manifest != null && manifest.getMainAttributes()
                    .getValue(Attributes.Name.CLASS_PATH) != null) {
                throw new SecurityException("manifest Class-Path not allowed");
            }
        }
    }

    private static void run(Path approvedDir, Path input,
                            String expectedHex) throws Exception {
        if (!expectedHex.matches("[0-9a-fA-F]{64}")) {
            throw new SecurityException("invalid pinned SHA-256");
        }

        Path root = approvedDir.toRealPath();
        Path jar = input.toRealPath();

        if (!Files.isRegularFile(jar, LinkOption.NOFOLLOW_LINKS)
                || !jar.startsWith(root)
                || !jar.getFileName().toString().equals(APPROVED_FILE)) {
            throw new SecurityException("source not allowlisted");
        }

        byte[] pinned = HexFormat.of().parseHex(expectedHex);
        byte[] actual = sha256(jar);
        if (!MessageDigest.isEqual(actual, pinned)) {
            throw new SecurityException("SHA-256 mismatch");
        }

        checkManifest(jar);
        System.out.println("Approved source: true");
        System.out.println("SHA-256 matches: true");
        System.out.println("Manifest Class-Path absent: true");

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jar.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> plugin = Class.forName(
                    "plugin.Greeter", true, pluginLoader);

            System.out.println("Plugin result: "
                    + plugin.getMethod("message").invoke(null));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.out.println("Usage: java JarGate <dir> <jar> <sha256>");
            return;
        }

        try {
            run(Path.of(args[0]), Path.of(args[1]), args[2]);
        } catch (SecurityException denied) {
            System.out.println("DENIED: " + denied.getMessage());
        }
    }
}
~~~

**Chương trình đã được kiểm thử** trên OpenJDK với flag `--release 17`: một JAR hợp lệ được chấp nhận, còn pin hash sai bị từ chối. Dưới đây là cách tự chạy.

### Build project

Tạo thư mục output trước:

~~~bash
mkdir -p classes approved
javac --release 17 -d classes src/plugin/Greeter.java
jar --create --file approved/greeter-1.0.jar -C classes .
javac --release 17 JarGate.java
~~~

Khối trên dùng Bash/Linux/macOS. Trên Windows PowerShell, tạo thư mục bằng lệnh tương đương:

~~~powershell
New-Item -ItemType Directory -Force classes, approved | Out-Null
javac --release 17 -d classes src/plugin/Greeter.java
jar --create --file approved/greeter-1.0.jar -C classes .
javac --release 17 JarGate.java
~~~

### Trường hợp được chấp nhận

**Chỉ cho demo local**, tính pin từ JAR mà người học vừa tự build:

~~~powershell
$expected = (Get-FileHash .\approved\greeter-1.0.jar -Algorithm SHA256).Hash
java JarGate approved approved/greeter-1.0.jar $expected
~~~

Hoặc trên Bash:

~~~bash
expected=$(sha256sum approved/greeter-1.0.jar | cut -d' ' -f1)
java JarGate approved approved/greeter-1.0.jar "$expected"
~~~

**Stdout của lệnh Java:**

~~~text
Approved source: true
SHA-256 matches: true
Manifest Class-Path absent: true
Plugin result: hello from pinned JAR
~~~

**Cảnh báo:** Bước tính `$expected` hoặc `expected=$(sha256sum ...)` **chỉ phù hợp cho bài thực hành** khi tự build từ source đáng tin. Trong production không được lấy hash kỳ vọng từ **chính artifact chưa tin cậy**, rồi tuyên bố artifact đã được chứng thực. Giá trị `expectedHex` phải đến từ trusted release manifest / signed policy / pinned configuration độc lập.

### Trường hợp SHA-256 không khớp

Trên PowerShell:

~~~powershell
$wrong = '0' * 64
java JarGate approved approved/greeter-1.0.jar $wrong
~~~

**Stdout:**

~~~text
DENIED: SHA-256 mismatch
~~~

Không có `URLClassLoader` nào được tạo ở nhánh bị từ chối đó. Nếu đầu vào thuộc root không hợp lệ hoặc tên JAR không nằm trong allowlist, chương trình in `DENIED: source not allowlisted` sau khi path đã resolve thành công.

### Vì sao ví dụ kiểm tra trước Class.forName?

`Class.forName("plugin.Greeter", true, pluginLoader)` yêu cầu **load và initialize** class. Static initializer của code plugin (nếu có) có thể thực thi mã. Do đó gate phải thành công **trước khi tạo/tra cứu class plugin và trước khi kích hoạt initialization**, chứ không thể “load thử xem có an toàn không” rồi mới hash.

### Đọc code theo từng lớp kiểm soát

1. `Path.toRealPath` và `Path.startsWith(Path)` xác nhận canonical location trong thư mục đã duyệt. Tên JAR được so bằng exact equality.
2. `sha256` dùng `InputStream` và `MessageDigest` theo chunks nên không phải load toàn bộ JAR vào byte array chỉ để hash.
3. `HexFormat.of().parseHex` (Java 17) chuyển pin hex 64 ký tự thành 32 byte.
4. `MessageDigest.isEqual` so sánh digest thực với pin kỳ vọng.
5. `JarFile` kiểm tra manifest. Nếu có `Class-Path` thì từ chối để tránh một đường mở rộng URL dependency **trong thiết kế demo**.
6. `URLClassLoader` chỉ có một URL JAR được duyệt. `getPlatformClassLoader` là parent phù hợp cho ví dụ plugin độc lập; plugin host thật có thể cần một **shared API parent loader** khác.
7. `Class.forName` khiến class của JAR được load/initialize sau gate. Method `message()` trả kết quả cố định.
8. `try-with-resources` đóng URLClassLoader sau khi dùng. Điều này không bảo đảm unload tất cả class lập tức.

**Không suy rộng:** Tên file allowlist và SHA-256 của riêng JAR không đủ kiểm soát mọi dependency, vì code vẫn có thể truy cập những class do parent định nghĩa, thao tác file, mạng, native library hay loader khác. Đó là ranh giới của ví dụ.

## 8. Vấn đề TOCTOU và staging artifact

Một lỗi thiết kế tinh vi:

~~~text
T1: verifier mở file /approved/greeter.jar, hash khớp
T2: process khác thay /approved/greeter.jar
T3: URLClassLoader mở file theo path
T4: JVM nạp bytes khác với bản verifier kiểm tra
~~~

`toRealPath()` không chặn việc thay file. Một file có digest đúng ở thời điểm kiểm tra vẫn có thể bị thay bởi writer có quyền sau đó.

Các biện pháp thường cần trong hệ thống thực:

- Chỉ cho pipeline/artifact manager đáng tin **ghi** vào staged artifact directory; runtime chỉ **đọc**.
- Đặt file ở đường dẫn theo **content digest** và bảo vệ quyền thay/ghi, thay vì một tên JAR chung có thể bị overwrite.
- Download sang file tạm dưới quyền kiểm soát, xác minh đầy đủ, rồi **promote** sang kho release chỉ đọc theo thao tác atomic và policy ownership phù hợp.
- Đảm bảo class loader đọc đúng file staged đã xác minh, không tự lấy lại từ URL khác khi runtime.
- Re-verify lúc deployment/startup theo threat model; không dùng một bản allowlist không được bảo vệ.
- Audit digest của bản thật đã loaded và xử lý quy trình thu hồi khi phát hiện bản sai.

Không có **một lời gọi Java Path API đơn lẻ** nào tự mang tới end-to-end assurance nếu attacker vẫn có quyền sửa file hoặc thay artifact repository.

## 9. Maven: direct và transitive dependency

Với Maven, `pom.xml` có dependencies và `dependencyManagement`/BOM; Maven giải quyết graph dựa trên profiles, scopes, repositories và policies. Nên:

1. Pin versions bằng release manifest và tránh version ranges hoặc SNAPSHOT không kiểm soát trong production.
2. Quản lý artifact qua mirror/internal registry có namespace mapping, quyền publish rõ ràng.
3. Kiểm tra toàn bộ graph đã resolve:

~~~bash
mvn dependency:tree
~~~

Lệnh trên cần môi trường Maven và Maven Dependency Plugin tương ứng; output phụ thuộc project nên không có stdout cố định.

4. Áp dụng policy như Maven Enforcer `bannedDependencies`, `dependencyConvergence` hoặc `requireUpperBoundDeps` khi phù hợp để ngăn tọa độ/phiên bản xung đột hoặc bị cấm.
5. Phát hành resolved artifact list kèm versions, source repositories và hashes như một phần release manifest đã ký/phê duyệt.
6. Chạy SCA và license policy liên tục, review dependency changes qua pull request.

**BOM không tự là lockfile hash của toàn bộ artifact graph.** BOM giúp quản lý phiên bản nhưng không bảo đảm mọi dependency đã được pin, verify theo digest và từ đúng nguồn. Bản deploy phải đối chiếu **graph thực** và artifact bytes cuối.

Cũng đừng nhầm graph Maven với toàn bộ runtime nếu ứng dụng dùng server-injected libraries, `ModuleLayer` nạp động hoặc plugin manager bổ sung JAR sau build.

## 10. Gradle: lock phiên bản khác verify bytes

Gradle cung cấp hai nhóm tính năng khác nhau:

- **Dependency locking:** khóa các phiên bản đã resolved, tránh thay đổi không kiểm soát.
- **Dependency verification:** đối chiếu checksum/chữ ký artifact với verification metadata được quản lý.
- **Repository content filters/exclusive content:** giới hạn artifact coordinate có thể đến từ repository nào.

Một fragment Kotlin DSL ví dụ:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Đây là **cấu hình minh họa**, không phải tệp Gradle build hoàn chỉnh. Để thực sự khóa, cần tạo và review lock state, bảo quản lockfiles trong version control và áp dụng đúng configurations.

Xem một resolved runtime graph phù hợp:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tên configuration có thể khác tùy plugin (Android, multi-project, custom runtime), nên phải chọn đúng graph được deploy. Bật locking mà không quản lý actual runtime configuration không bảo vệ toàn bộ artifact nạp sau này.

**Verification metadata phải được review**, đặc biệt khi tạo lần đầu hoặc khi dependency thay đổi. Nếu cho tool tự thêm hash của artifact tải từ nguồn bị đầu độc mà không có bước xác thực publisher/provenance độc lập, hệ thống chỉ khóa **bytes độc hại**.

~~~text
Repository policy   → artifact được lấy từ đâu?
Lockfile            → version nào được resolve?
Verification        → bytes/signatures nào được chấp nhận?
SCA/SBOM            → component nào và rủi ro đã biết nào?
Runtime loader gate → artifact cuối thực sự được nạp là bản nào?
~~~

Mỗi câu hỏi phải có câu trả lời riêng và bằng chứng kiểm thử.

## 11. SCA, SBOM, provenance và revocation

**SBOM (Software Bill of Materials)** cung cấp danh sách các thành phần của một bản phát hành. Nó hữu ích cho inventory, ứng phó CVE và truy ra transitive dependencies. Khi có fat JAR/shading, cần bảo đảm các thành phần nhúng vẫn được ghi nhận; khi runtime nạp JAR khác ngoài build, cần bổ sung nguồn inventory runtime.

**SCA (Software Composition Analysis)** so danh sách dependency với cơ sở dữ liệu advisory, phiên bản bị ảnh hưởng và chính sách tổ chức. Quét có thể có false positive/false negative, và CVE mới xuất hiện sau lúc release; vì vậy phải giám sát liên tục, không chỉ scan một lần.

**Provenance/attestation** có thể xác nhận claim về source, toolchain, builder, workflow và artifact digest. Nhưng validator phải kiểm tra **trust root, signer/builder identity, claim constraints và digest**, không chỉ parse một JSON tên `provenance`.

**Revocation:** Artifact từng đạt SHA-256 và chữ ký vẫn có thể bị thu hồi sau incident hoặc phát hiện lỗ hổng. Allowlist phải có cơ chế cập nhật và audit: ai gỡ pin, vì sao, deployment nào bị ảnh hưởng, cách rollback/patch ra sao.

Một chính sách mạnh sẽ tự động từ chối bản bị revoked, kể cả khi bytes còn khớp pin cũ — bởi vì **“bytes đúng” không đồng nghĩa “được phép hôm nay”**.

## 12. ClassLoader, ServiceLoader, ModuleLayer có kiểm tra trust không?

**URLClassLoader** tìm class/resource theo URLs và parent delegation. Nó không biết policy doanh nghiệp về nguồn JAR, signer hoặc artifact version. `loader.getURLs()` cũng không trình bày toàn bộ class có thể nhận từ parent hay những nguồn code động khác.

**ServiceLoader** tìm provider đã đăng ký ở `META-INF/services` hoặc `provides ... with ...` trong named module. Metadata có thể khiến framework instantiate code của provider. Phải xác nhận service contract thuộc API được phê duyệt, provider class từ artifact/loader được duyệt, và TCCL không vô tình chỉ về plugin cũ.

**ModuleLayer** cho phép định nghĩa dynamic named modules theo module graph. `ModuleFinder`, `Configuration.resolve` và `defineModules...` thực hiện module resolution/definition, **không tự thực thi allowlist publisher, integrity pin hay security sandbox**.

**CodeSource/ProtectionDomain** có thể giúp debug class đã nạp từ URL nào:

~~~java
Class<?> type = /* một Class<?> đã có */;
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
~~~

Đây là **fragment**, chưa phải chương trình độc lập. `CodeSource` hữu ích cho quan sát nhưng không phải certificate of trust; custom loader có thể gán metadata không phản ánh toàn bộ lịch sử supply chain. Bootstrap classes và class sinh động có thể không có URL vật lý rõ ràng.

**Không dùng ClassLoader như security sandbox.** Class loader tổ chức namespace/type identity/lookup. Plugin bị coi là không tin cậy nên chạy trong **process/container cô lập** nếu cần ngăn truy cập secrets, filesystem, network, native code hoặc OS resources. Quyền OS, network policy, resource limits và monitoring là những lớp riêng.

## 13. Các phản ví dụ cần tránh

**“JAR có HTTPS download thành công nên được tin.”** Chưa chắc. TLS bảo vệ kết nối, không xác nhận build/publisher không bị compromise.

**“Hash của JAR và hash trong file cạnh nó khớp nên an toàn.”** Chưa chắc. Nếu cả hai từ nguồn bị kiểm soát, attacker có thể thay cả hai.

**“jarsigner verify thành công nên người ký được phép.”** Không đủ. Phải validate signer/trust/coverage và policy; chữ ký hợp lệ không tự bảo đảm code không độc hại.

**“Khớp SHA-256 nghĩa không có CVE.”** Sai. Digest chỉ ràng buộc bytes với bản được pin.

**“Chỉ cần allowlist dependency trực tiếp.”** Sai. Phải review **full closure** gồm transitive, shaded, runtime JARs và những cơ chế nạp động liên quan.

**“Một URLClassLoader có một URL sẽ chỉ dùng một JAR.”** Không bảo đảm vì parent, manifest `Class-Path`, module/service lookup và runtime loading khác.

**“Có Maven BOM là mọi bytes đã khóa.”** Sai. BOM quản lý versions, không tự pin toàn bộ binary artifacts và nguồn phát hành.

**“Tôi có thể sửa lỗi bằng cách fallback sang repository public khác khi SHA mismatch.”** Sai. Làm vậy phá fail-closed và tạo cơ hội dependency confusion/downgrade.

**“JAR được phê duyệt là an toàn để chạy ngay trong host process.”** Không. Một artifact đúng nguồn vẫn có thể có lỗi, quyền vượt mức hoặc bị khai thác; cần runtime isolation/monitoring theo threat model.

**“Chỉ canonicalize path là chống sửa file sau kiểm tra.”** Không. TOCTOU vẫn tồn tại nếu writer chưa tin cậy có thể thay bytes trước khi loader đọc.

## 14. Checklist trước khi nạp plugin JAR

1. Xác định **threat model**: plugin có tin cậy như host không? Nếu không, cần isolation ngoài class loader.
2. Allowlist **publisher/repository/group/artifact/version** và chặn namespace confusion.
3. Có release manifest **đã ký/phê duyệt** ràng buộc digest và dependency graph.
4. Tính SHA-256 trên **bản artifact cuối** và so với **pin độc lập/trusted**.
5. Nếu policy yêu cầu signer, validate chữ ký, trust chain, identity và entry coverage.
6. Review các dependencies **trực tiếp, bắc cầu, runtime, shaded và native** cùng versions/digests/sources.
7. Quét **SCA**, so SBOM và xử lý vulnerability/license policy.
8. Kiểm soát manifest `Class-Path`, loader URL expansion, TCCL/SPI và dynamic module loading.
9. Stage artifact **bất biến/chỉ đọc**, có quyền filesystem và ownership phù hợp; ngăn TOCTOU.
10. Chỉ sau đó mới tạo loader/module layer và chạy plugin; bảo toàn shared API class identity.
11. Ghi audit artifact ID, digest, nguồn, signer, policy version, quyết định allow/deny và thời gian.
12. Có kế hoạch update/revoke/rollback, shutdown plugin threads, cleanup TCCL và loader references.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một server phát cả `plugin.jar` lẫn `plugin.jar.sha256` và hai file khớp nhau. Đã chứng minh nguồn publisher đúng chưa?

**Đáp án:** Chưa. Cả hai có thể bị thay cùng lúc. Hash pin phải đến từ trusted source độc lập/signed metadata.

**Câu 2.** Vì sao phải allowlist transitive dependencies chứ không chỉ direct?

**Đáp án:** Runtime có thể nạp code từ toàn bộ resolved graph. Một transitive artifact không được duyệt vẫn có thể thực thi.

**Câu 3.** JAR ký số hợp lệ nhưng signer không nằm trong policy. Cho chạy không?

**Đáp án:** Không. Chữ ký mật mã hợp lệ không tự đồng nghĩa publisher được cho phép.

**Câu 4.** JAR hash đúng nhưng chứa `Class-Path: lib/extra.jar`. Chắc chắn chỉ dùng JAR đầu không?

**Đáp án:** Không. Manifest có thể mở rộng đường tìm class/resource. Phải approve JAR phụ hoặc từ chối cơ chế Class-Path.

**Câu 5.** `Path.toRealPath` kiểm tra trước `URLClassLoader` có ngăn file bị thay trước lúc loader đọc không?

**Đáp án:** Không. Cần staging immutable và quyền ghi được kiểm soát để xử lý TOCTOU.

**Câu 6.** Một plugin đã qua gate có thể tải native library hoặc gọi network API không?

**Đáp án:** Nếu process có quyền, có thể. Class loader không phải sandbox; cần OS/process isolation và network restrictions.

**Câu 7.** Maven BOM/Gradle lockfile có bảo đảm mọi artifact có SHA-256 đúng policy không?

**Đáp án:** Không tự động. Lock version và verification hash/signature là các lớp kiểm soát khác nhau.

**Câu 8.** Vì sao phải duy trì revocation dù digest JAR không đổi?

**Đáp án:** Bản bytes từng được phê duyệt có thể bị phát hiện backdoor/CVE hoặc publisher compromise về sau. “Khớp pin” không đồng nghĩa luôn còn được phép.

## Ghi nhớ

**Nguồn hợp lệ, bytes khớp pin và dependency graph được phép là ba điều kiện độc lập.** Trước `URLClassLoader`/`ServiceLoader`/dynamic `ModuleLayer`, hãy kiểm tra artifact từ repository/publisher đã phê duyệt, SHA-256 từ trusted metadata, signer khi cần, toàn bộ transitive/runtime dependencies và staged bytes cuối. **Không tự pin hash từ chính JAR chưa tin**, không xem chữ ký là bằng chứng code vô hại và không xem class loader là sandbox. Khi có nghi ngờ, **fail closed**, audit và dùng runtime isolation phù hợp.

**Tài liệu chính thức và hướng dẫn tham khảo:**

- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- JDK `jarsigner`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 API, `MessageDigest` và `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- OWASP Software Supply Chain Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html
- Gradle Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Maven Enforcer: https://maven.apache.org/enforcer/maven-enforcer-plugin/

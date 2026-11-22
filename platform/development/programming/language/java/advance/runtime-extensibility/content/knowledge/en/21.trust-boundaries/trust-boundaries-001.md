# Đánh giá nguồn gốc JAR, mã Java và kịch bản trước khi thực thi

## 1. Ranh giới tin cậy của hệ thống runtime extensibility

Plugin JAR, source Java biên dịch động và script đều có thể đưa **mã do bên khác cung cấp** vào một ứng dụng host. Điểm nguy hiểm là từ 'phát hiện được' đến 'thực thi được' thường chỉ cách một lời gọi `ServiceLoader`, `Class.forName`, `JavaCompiler`, `JShell.eval` hoặc `ScriptEngine.eval`. Sự kiện một tệp xuất hiện trong thư mục plugin không chứng minh nó an toàn, chính hãng hay được phép chạy.

Cần tách ba câu hỏi:

1. **Provenance (nguồn gốc):** ai phát hành artifact, artifact đến qua kênh nào, có thuộc nhà cung cấp được tổ chức cho phép không?
2. **Integrity (toàn vẹn):** bytes nhận được có đúng với bản đã được phê duyệt hay bị sửa đổi trên đường truyền, trong kho lưu trữ hoặc trên ổ đĩa?
3. **Authorization/Execution policy:** ngay cả artifact thật và chưa đổi, liệu mã này có được chạy trong môi trường cụ thể, với phiên bản/khả năng/quyền nào?

**Chữ ký hoặc checksum không chứng minh mã là vô hại.** Artifact có thể được ký bởi nhà phát hành đáng tin cậy nhưng vẫn có lỗ hổng, mã độc do tài khoản phát hành bị chiếm, hoặc hành vi không phù hợp chính sách host. Bảo đảm an toàn cần nhiều lớp kiểm soát trước và trong khi thực thi.

## 2. Ba loại đầu vào cần đánh giá khác nhau

| Đầu vào | Điều cần xác minh trước tiên | Rủi ro đặc thù |
|---|---|---|
| **JAR plugin** | Danh tính publisher, hash/chữ ký, dependency tree, class/module metadata, version | Class initialization, `ServiceLoader` provider constructors, native libs, class loader leaks |
| **Source Java** | Nguồn nộp, commit/review, policy import/dependency, compiler options, kết quả build | Annotation processor, generated sources, static initializer khi load class, mã compile nhưng gây side effect lúc chạy |
| **Script** | Tác giả, định dạng, engine/version, input schema, quyền host objects, allowlist API | `eval` truy cập tài nguyên hệ thống, overload/proxy reflection, vòng lặp vô hạn, tài nguyên quá mức |

Không coi các tệp văn bản tự động vô hại. `javac` có thể chạy annotation processors khi được bật; JShell/script execution có thể gọi Java API hoặc thực hiện I/O tùy quyền của process và engine.

## 3. Quy trình kiểm soát từ nhận artifact đến activation

```text
Receive artifact (quarantine, chưa load)
  -> Xác thực kênh và danh tính publisher
  -> Tính hash / xác minh chữ ký, provenance statement
  -> Kiểm tra allowlist, phiên bản, dependency, SBOM
  -> Quét malware/SCA, policy & review phù hợp mức rủi ro
  -> Staging bất biến, hạn chế quyền truy cập
  -> Pre-activation validation (metadata, API compatibility)
  -> Execution isolation và resource limits
  -> Observability, audit, revoke/rollback
```

Phải hoàn tất các bước **không thực thi mã** trước khi tạo instance plugin, gọi static initializer hoặc đánh giá script. Ví dụ `Class.forName(name, true, loader)` có thể kích hoạt class initialization; gọi constructor của provider rõ ràng là code execution. Trong luồng đánh giá, chỉ đọc manifest/ZIP metadata cũng phải tránh giải nén tùy tiện hoặc ghi ra path không kiểm soát.

### 3.1. Quarantine và chống thay đổi giữa kiểm tra với load

Lưu artifact mới trong staging không được application class loader đọc và không để nội dung có thể thay đổi bởi actor không đáng tin. Sau khi hash/phê duyệt, **load đúng bytes đã kiểm tra**: copy vào kho artifact immutable hoặc directory versioned với ownership/permission phù hợp. Nếu kiểm tra file A rồi load lại đường dẫn có thể bị thay thế, phát sinh race condition (TOCTOU).

Không nhận đường dẫn từ người dùng rồi dùng trực tiếp làm `URLClassLoader` input trước khi xác thực đường dẫn, canonical location, symlink, file type và quyền truy cập.

## 4. Xác minh integrity bằng SHA-256

SHA-256 là hash mật mã phù hợp để so sánh nội dung với **digest mong đợi lấy từ nguồn đáng tin cậy**. Nếu attacker có thể thay cả JAR lẫn checksum bên cạnh nó, checksum không tạo ra xác thực nguồn gốc. Vì thế checksum phải gắn với một manifest phát hành, registry/artifact metadata hoặc kênh xác thực độc lập.

### Ví dụ Java 17+ chạy độc lập

Tạo file `VerifyJar.java`:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class VerifyJar {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java VerifyJar <file.jar> <expected-sha256>");
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Not a regular file: " + jar);
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(jar)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        String actual = HexFormat.of().formatHex(digest.digest());
        String expected = args[1].toLowerCase(java.util.Locale.ROOT);
        if (!expected.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Expected SHA-256 must be 64 hex characters");
        }

        byte[] expectedBytes = HexFormat.of().parseHex(expected);
        byte[] actualBytes = HexFormat.of().parseHex(actual);
        boolean matches = MessageDigest.isEqual(expectedBytes, actualBytes);
        System.out.println("sha256: " + actual);
        System.out.println("verified: " + matches);
        if (!matches) System.exit(1);
    }
}
```

Biên dịch và tạo một JAR đơn giản bằng JDK 17+, chạy trong shell POSIX:

```bash
javac VerifyJar.java
mkdir -p demo-classes
printf 'hello\n' > demo-classes/README.txt
jar --create --file demo.jar -C demo-classes .
sha256sum demo.jar
```

Giả sử `sha256sum` in ra digest thực tế là `<DIGEST>` (64 chữ số hex), dùng giá trị **đúng từ lệnh trên**:

```bash
java VerifyJar demo.jar <DIGEST>
```

Output có định dạng:

```text
sha256: <DIGEST>
verified: true
```

`<DIGEST>` là ký hiệu thay cho giá trị hash thực nhận, không phải stdout cố định. Nếu muốn kiểm thử mismatch, đưa một chuỗi 64 ký tự hex khác với hash thật; chương trình in `verified: false` và trả exit code 1. Trên Windows có thể tính hash bằng `Get-FileHash demo.jar -Algorithm SHA256` rồi truyền kết quả cho chương trình.

**Giới hạn:** Ví dụ chỉ xác nhận bytes của file tại thời điểm đọc. Nó không xác minh signer, không scan malware, không kiểm tra chứng chỉ và không tránh TOCTOU nếu loader sau đó mở một file có thể bị thay thế. Trong production nên triển khai kho immutable và tránh thay đổi file đã phê duyệt.

## 5. Chữ ký JAR và trust policy

JAR có thể được ký bằng cơ chế JAR signing. Các công cụ phổ biến của JDK gồm `jarsigner` và `keytool`:

```bash
jarsigner -verify -verbose -certs plugin.jar
```

Chữ ký JAR giúp phát hiện thay đổi những entry đã ký và cung cấp thông tin signer theo cơ chế Java JAR signing. Nhưng xác minh chữ ký kỹ thuật **khác** với đánh giá publisher có đáng tin và còn được cấp quyền hay không.

Host cần chính sách rõ:

- Chỉ chấp nhận signer/public key đã được phê duyệt hoặc chuỗi chứng chỉ theo trust policy.
- Kiểm tra hiệu lực chứng chỉ, thu hồi, thuật toán yếu và thời gian ký nếu áp dụng.
- Xử lý JAR không ký, một phần entry không được ký, nhiều signer và file manifest bất thường theo quy tắc đã xác định.
- Có quy trình xoay khóa, thu hồi publisher và xử lý artifact đã được phát hành trước khi một key bị lộ.
- Không cho phép một chữ ký hợp lệ bỏ qua kiểm tra version, dependency và quyền thực thi.

Không coi một lệnh `jarsigner -verify` thành hệ thống supply-chain security hoàn chỉnh. Trong các pipeline cao hơn, có thể liên kết artifact với attestation/provenance build, SBOM, commit, CI identity và registry bất biến. Những chứng cứ ấy cũng phải được xác thực bằng khóa/identity policy đáng tin.

## 6. Dependency, transitive risk và provenance

Plugin có thể chỉ chứa vài class tự viết nhưng kéo theo hàng chục JAR dependency. Cần kiểm tra không chỉ plugin chính mà **toàn bộ dependency được nạp ở runtime**:

- Artifact coordinates, version lock và origin registry.
- Checksums/signatures cho dependency, kể cả transitive dependencies.
- SBOM hoặc inventory dependency thực tế (mối liên hệ giữa component và build artifact).
- CVE/advisory phù hợp phiên bản; kết quả scan là tín hiệu rủi ro chứ không chứng minh mã sạch.
- License, provenance của build tool/plugins và policy tổ chức.
- Những dependency bị shading/đóng gói trong fat JAR, native binaries và resource được trích xuất.

Với plugin loader cô lập, một dependency bị thay bằng bản khác vẫn có thể gây lỗ hổng dù API contract không đổi. Khi dùng Maven/Gradle, khóa version, verify artifact và kiểm soát repository mirror trong CI/CD. Tránh tải dependency tùy ý tại runtime từ URL do plugin mô tả mà không qua gate kiểm tra.

## 7. Đánh giá source Java trước khi biên dịch hoặc load

Source Java có thể được đọc và phân tích tĩnh để phát hiện import/usage đáng ngờ, nhưng kiểm tra static không đủ để chứng minh an toàn. Reflection, dynamic class loading, native calls và dependency có thể làm hành vi thực tế khác source nhìn thấy.

Checklist cho hệ thống biên dịch lúc chạy:

1. Nhận source qua kênh xác thực, gắn submitter/project ID, commit/hash và policy cho ngôn ngữ/API.
2. Kiểm tra path, số file, kích thước, encoding, symlink và package namespace được phép.
3. Biên dịch trong môi trường tách biệt theo quyền OS và giới hạn CPU, RAM, thời gian, disk/network.
4. Chỉ định class path/module path của contract API từ các artifact đã phê duyệt.
5. Không tự động cho phép annotation processors từ dependency của source; nếu không cần, dùng `-proc:none`.
6. Thu thập `Diagnostic` nhưng không hiển thị path hoặc secret nội bộ cho người nộp nguồn.
7. Phê duyệt bytecode/JAR đầu ra theo policy, lưu vào artifact store versioned trước activation.

Ví dụ tùy chọn `JavaCompiler`:

```java
var options = java.util.List.of(
    "--release", "17",
    "-proc:none",
    "-encoding", "UTF-8"
);
```

Đoạn này chỉ là **mảnh cấu hình**, không phải chương trình độc lập. `-proc:none` tắt annotation processing trong những compiler áp dụng tùy chọn này; nó không khiến code biên dịch trở nên an toàn để thực thi. Compile còn có thể cần plugin của compiler hoặc công cụ build khác; tất cả công cụ tham gia pipeline cần được kiểm soát.

## 8. Đánh giá script trước khi eval

Script engine JSR 223 có thể cho script truy cập API host, Java objects trong bindings, file/network và native functionality tùy engine. Ngay cả khi script chỉ có vài dòng, `eval` có thể mang side effect nghiêm trọng.

Host nên:

- Xác thực nguồn gốc script: tác giả, revision, checksum/signature, review status và engine/version.
- Xác định ngôn ngữ/engine allowlist; từ chối engine không có trong chính sách.
- Áp dụng schema cho đầu vào/đầu ra, không đưa các object quyền cao (`ClassLoader`, `Runtime`, DB admin client, credential store) vào bindings.
- Kiểm tra policy permissions/capabilities theo từng tenant hoặc nhóm plugin.
- Dùng process/container cô lập cho script không tin cậy, giới hạn filesystem, network, CPU, memory, execution time và OS user.
- Đảm bảo logging/audit không lộ nội dung nhạy cảm hay script secrets.

### Ví dụ cổng kiểm tra trước khi đánh giá

```java
static Object evaluateApproved(
        javax.script.ScriptEngine engine,
        String script,
        java.util.Set<String> approvedHashes) throws Exception {
    java.security.MessageDigest digest =
        java.security.MessageDigest.getInstance("SHA-256");
    byte[] bytes = script.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    String hash = java.util.HexFormat.of().formatHex(digest.digest(bytes));
    if (!approvedHashes.contains(hash)) {
        throw new SecurityException("Script not approved");
    }
    return engine.eval(script);
}
```

Đây là **đoạn minh họa** trong class Java đã có engine thực tế; không tự chạy độc lập. Nó thực hiện check hash nhưng không cách ly script, và `approvedHashes` phải được quản lý từ nguồn đáng tin cậy. Chuỗi ký tự có cùng nội dung nhưng khác encoding/normalization có thể có hash khác; pipeline cần thống nhất byte representation trước khi ký/phê duyệt.

## 9. ClassLoader, ModuleLayer và các ranh giới không phải sandbox

Một plugin có thể được nạp bằng `URLClassLoader`, `ServiceLoader` hoặc `ModuleLayer`. Các công cụ này tổ chức dependency và class identity; **chúng không tạo ranh giới quyền OS**.

- Custom class loader có thể cô lập phiên bản thư viện, nhưng plugin vẫn chạy trong JVM process host với quyền tương tự nếu không có cơ chế khác.
- JPMS `exports`/`opens` giới hạn truy cập module API/reflection theo quy tắc JVM, nhưng không phải cơ chế để chạy arbitrary hostile code an toàn.
- Java Security Manager đã bị deprecate for removal từ Java 17 và không nên xem nó là lớp sandbox mặc định cho hệ thống plugin hiện đại.
- Nếu cần chạy mã không tin cậy, dùng subprocess/container/VM với OS permissions, seccomp/cgroup/namespace hoặc cơ chế nền tảng tương ứng, và giao tiếp qua protocol giới hạn capability.

Phân biệt **isolation để tránh xung đột dependency** và **isolation để giới hạn tác động của mã đối kháng**. Một Java process chạy cùng quyền host có thể mở file, tạo network connection hoặc giữ CPU dù class loader của nó độc lập.

## 10. Policy ra quyết định theo mức độ tin cậy

| Tình huống | Policy gợi ý |
|---|---|
| Plugin nội bộ được build từ CI đã xác minh | Pin artifact, verify digest/signature, scan dependencies, test và kiểm soát release |
| Plugin của vendor đã phê duyệt | Verify publisher identity, attestation nếu có, compatibility, allowlist capabilities, resource limits |
| Plugin cộng đồng chưa review | Không thực thi trong host JVM; yêu cầu review và process isolation |
| Source Java do người dùng upload | Compile ở worker cô lập, tránh processors, kiểm tra outputs, không tự động activate |
| Script từ tenant không tin cậy | Sandboxed process với API/bindings tối thiểu, timeout và quota |

Không dùng một cờ boolean `trusted=true` không có nguồn gốc hoặc thời hạn. Trust policy nên có version, người phê duyệt, scope, thời điểm hết hạn và cơ chế revoke. Với hệ thống nhiều tenant, quyền của plugin còn phải gắn với tenant context của yêu cầu cụ thể.

## 11. Logging, audit và ứng phó khi nguồn bị xâm phạm

Mọi lần activation cần ghi ít nhất: artifact ID/hash, signer/publisher ID, version, nguồn tải, policy decision, environment, dependency set và kết quả startup. Không log private keys, secrets hay raw sensitive script inputs.

Khi phát hiện key bị lộ hoặc plugin độc hại:

1. Thu hồi khả năng tải/kích hoạt phiên bản đó và mọi artifact liên quan.
2. Ngừng routing request mới tới plugin, dọn tài nguyên và chấm dứt worker process khi phù hợp.
3. Lưu evidence cần thiết (hash, logs, artifact metadata) theo incident policy.
4. Xác định blast radius: data access, network activity, credentials, downstream systems.
5. Rotate credentials và rollback/redeploy từ artifact đã xác minh.

Một quy trình revoke hiệu quả phải chặn **activation mới**, không chỉ xóa file trên registry. Các plugin đang chạy có thể vẫn giữ code và state trong memory; nếu là mã đối kháng, cách ly/dừng process riêng đáng tin hơn việc chỉ đóng class loader.

## 12. Lỗi thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Tin file vì nằm trong `plugins/` | Thư mục có thể bị ghi bởi attacker hoặc pipeline lỗi | Quarantine, file ownership, artifact policy |
| So SHA-256 với `.sha256` cạnh JAR không xác thực | Attacker có thể đổi cả hai | Dùng digest từ registry/manifest đã xác thực |
| Có chữ ký thì chạy ngay | Signer có thể không thuộc allowlist hoặc bản ký chứa lỗi | Verify signer trust, version và policy |
| Chỉ scan JAR chính | Dependency độc hại không được phát hiện | Scan/capture toàn bộ dependency closure |
| Compile source với processors không kiểm soát | Processor có thể chạy code trong lúc build | `-proc:none` hoặc processor allowlist trong worker cô lập |
| Gọi `Class.forName(..., true, ...)` trước khi check | Kích hoạt static initializer của mã chưa được phê duyệt | Validate artifact trước class initialization |
| Dùng class loader như sandbox | Không hạn chế quyền OS | Process/container isolation |
| Không khóa artifact sau verification | TOCTOU: bytes load khác bytes đã kiểm tra | Immutable staged artifact, quyền hạn chặt |

## 13. Checklist tối thiểu trước khi production

- [ ] Mỗi JAR/source/script có artifact ID, origin và hash được ghi nhận.
- [ ] Hash/chữ ký đối chiếu với nguồn đáng tin và publisher được allowlist.
- [ ] Dependency và transitive artifact được kiểm tra, version được khóa.
- [ ] Không thực thi code trước khi hoàn tất policy; kể cả class initialization, processors và constructors.
- [ ] Artifact đã xác minh được lưu immutable để tránh TOCTOU.
- [ ] Class path/module path và API version được kiểm soát.
- [ ] Có isolation theo mức độ tin cậy và resource limits.
- [ ] Có audit log, revoke/rollback và kế hoạch xử lý compromise.

**Kết luận:** Đánh giá nguồn gốc mã trước khi thực thi không chỉ là kiểm tra checksum. Host cần chứng minh artifact đến từ nguồn được phép, bytes chưa bị thay đổi, dependencies/phiên bản đúng policy và execution environment có giới hạn phù hợp. Đặc biệt, Java class loader, module layer, `ServiceLoader` và script API hỗ trợ mở rộng runtime nhưng không tự cung cấp sandbox cho mã không tin cậy.

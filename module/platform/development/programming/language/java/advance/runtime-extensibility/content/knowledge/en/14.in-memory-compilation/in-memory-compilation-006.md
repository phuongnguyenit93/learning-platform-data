# Định danh kết quả theo mã nguồn, tùy chọn và phụ thuộc để quản lý bộ nhớ đệm

## 1. Mục tiêu và điều kiện đúng của compilation cache

Khi ứng dụng Java nhận mã nguồn lúc chạy, nó có thể dùng `javax.tools.JavaCompiler` và `JavaFileManager` để biên dịch `.java` thành `.class` trong RAM. Nếu cùng một yêu cầu xuất hiện nhiều lần (rule engine, code playground, scripting, plugin generator), việc biên dịch lại từ đầu làm tăng CPU, cấp phát bộ nhớ và độ trễ. **Compilation cache** giữ kết quả biên dịch đã thành công rồi tái sử dụng.

Tuy nhiên, “mã nguồn không đổi” **không đủ** để cho phép cache hit. Kết quả có thể phụ thuộc vào tùy chọn `javac`, thư viện/module được tìm thấy, annotation processor, các file source phụ, compiler implementation và JDK version. Cache key thiếu một input có thể trả về bytecode cũ dù yêu cầu đã đổi.

Hai đặc tính cần giữ:

- **Không false hit:** hai yêu cầu có cùng key phải tương đương đối với output mà cache hứa cung cấp. False hit có thể gây lỗi chạy, kết quả sai hoặc lộ dữ liệu.
- **Tránh false miss không cần thiết:** hai yêu cầu tương đương nên có key giống nhau. False miss gây tốn tài nguyên nhưng thường không sai kết quả.

Ví dụ:

~~~text
Compile #1:
  source: Rule.java gọi Api.LIMIT
  options: --release 17 -proc:none
  dependency: api.jar có LIMIT = 10
  → output A → lưu cache K1

Compile #2:
  source/option vẫn y nguyên
  dependency: api.jar đổi, LIMIT = 20
  → KHÔNG dùng lại K1 nếu fingerprint phụ thuộc phản ánh bytes khác.

Compile #3:
  toàn bộ source/options/dependencies/toolchain như #1
  → có thể lấy output A từ cache mà không gọi compiler.
~~~

**Mục tiêu bài học:** xây khóa định danh theo mã nguồn, tùy chọn và phụ thuộc; hiểu cấu trúc kết quả `JavaCompiler`; thực hiện fingerprint/invalidation; kiểm soát concurrent compilation và tách bytecode cache khỏi class loading.

## 2. Chọn đơn vị cache trước khi tạo key

Một source `Outer.java` có thể sinh nhiều `.class` (nested/anonymous classes). Một batch nhiều source có thể phụ thuộc lẫn nhau; annotation processors còn có thể sinh source/resource. Vì thế không nên coi giá trị cache luôn là một `byte[]` của class chính.

| Phạm vi cache | Input cần đưa vào key | Kết quả lưu | Khi nên chọn |
| --- | --- | --- | --- |
| Một source đơn giản | Logical name + source text + môi trường compile | **Tất cả** class files phát sinh | Rule độc lập, không phụ thuộc source khác |
| Một batch nhiều source | Toàn bộ source units, options, dependencies | Class map và generated outputs của batch | Mã nguồn tham chiếu lẫn nhau |
| Một JPMS module | Source + `module-info.java` + module path + resolution config | Toàn bộ output module | Plugin modular |
| Incremental graph | Dependency/symbol graph và fingerprints của từng node | Kết quả theo node/module | Build service lớn đã có tracking chính xác |

**Khuyến nghị khởi đầu:** cache **toàn bộ compilation request**; khi một input trong request thay đổi, compile lại toàn bộ. Chỉ chuyển sang incremental per-class sau khi kiểm chứng dependency closure, constant inlining, annotation processing và classpath visibility.

Phân biệt ba đối tượng:

- `CompilationRequest`: toàn bộ thông tin compiler thực sự tiêu thụ.
- `CompilationArtifact`: bytecode map, generated resources và metadata cần dùng lại.
- `RuntimeGeneration`: classloader/layer định nghĩa class từ artifact. Hai generation có thể dùng cùng bytecode cached nhưng định nghĩa các runtime `Class<?>` riêng.

## 3. Công thức cache key an toàn

Một dạng tổng quát:

~~~text
key = SHA-256(
    canonicalEncode(
        cacheSchemaVersion,
        compilerIdentity,
        platformIdentity,
        sourcesSortedByLogicalPath,
        effectiveOptionsInSemanticOrder,
        dependencyArtifactsInLookupOrder,
        annotationProcessorInputs,
        relevantEnvironment
    )
)
~~~

Từ khóa là **canonicalEncode**: encode có ranh giới trường, version và thứ tự xác định. Không nối chuỗi bằng `a + b + c` khi không có length-prefix: các phần `"ab","c"` và `"a","bc"` sẽ cho cùng chuỗi `"abc"`. Có thể dùng encoding nhị phân ghi số lượng trường + số byte + bytes UTF-8, hoặc JSON canonical được chuẩn hóa bằng quy tắc chặt chẽ.

### 3.1. Các thành phần bắt buộc phải cân nhắc

| Input | Tác động | Fingerprint phù hợp |
| --- | --- | --- |
| Source unit name + source content | Package, declarations, symbols, diagnostics | Logical path/binary name + SHA-256 exact content |
| Tập source của batch | Type resolution và generated class | Sort theo logical path, hash từng nội dung |
| `--release`, debug, `-parameters`, `-Xlint` | Bytecode target/metadata/diagnostics | Effective compiler option tokens |
| Classpath/module path | Class, method, constants, module visibility | Ordered entries: identity + content digest |
| Sourcepath/implicit sources | Compiler có thể tự đọc/compile source khác | Fingerprint các source thực sự cho phép đọc |
| Processor path và `-A` options | Generated sources/classes/resources | Processor artifact/dependencies/config/deterministic inputs |
| Compiler provider/JDK build | Toolchain có thể sinh output khác | Compiler ID/vendor/exact version/schema |
| Môi trường có ảnh hưởng | Charset, processor read files/env/clock | Cấu hình tường minh hoặc **non-cacheable** |

Đối với cache diagnostics, cần thêm các input ảnh hưởng định dạng lỗi (ví dụ locale hoặc source URI) và warning policy. Đối với cache **chỉ** bytecode, có thể bỏ một số input không ảnh hưởng bytecode **nếu đã chứng minh được**; mặc định fingerprint bảo thủ dễ đúng hơn.

### 3.2. Manifest mô tả input

Đây là một **mẫu biểu diễn khái niệm**, không phải API của JDK và các digest không phải giá trị thực:

~~~json
{
  "schema": "java-inmem-compilation/v1",
  "compiler": {
    "implementation": "javac",
    "vendor": "recorded-vendor",
    "build": "recorded-exact-build"
  },
  "sources": [
    {"path": "com/example/Rule.java", "sha256": "digest-of-actual-source"}
  ],
  "options": ["--release", "17", "-proc:none", "-parameters"],
  "classpath": [
    {"order": 0, "id": "api.jar", "sha256": "digest-of-actual-jar"}
  ],
  "modulepath": [],
  "processors": [],
  "environment": {"policy": "controlled"}
}
~~~

Trong triển khai thật, phải điền digest từ bytes đang dùng, cố định cách biểu diễn từng field và **version hóa schema**. Lưu manifest bên cạnh key giúp giải thích cache miss: source, option, dependency hay JDK nào đã đổi.

## 4. Mã nguồn: hash chính xác phần compiler đọc

### 4.1. Nguồn dạng String hoặc bytes

Với `SimpleJavaFileObject.getCharContent(...)` nhận Java `String`, có thể hash nội dung UTF-8 của chuỗi compiler thực sự dùng. Với file trên đĩa, phải chọn charset rõ ràng và hash **nội dung sau khi các bước tiền xử lý cần thiết đã diễn ra**.

Ví dụ pipeline:

~~~text
template + user input
     ↓ validate/normalize theo policy đã công bố
generated source String
     ↓ tạo key từ chính String + config của template/transform
JavaFileObject.getCharContent()
     ↓
JavaCompiler
~~~

Nếu code được inject import, đổi package, expand macro hoặc sinh source từ template, **hash source sau transform** hoặc hash cả phiên bản và input của transform. Hash source gốc nhưng compile nguồn đã sửa sẽ tạo cơ hội false hit.

Không tự ý `trim()`, xóa comments, đổi line endings hay Unicode normalize chỉ để tăng hit rate. Các thay đổi này có thể ảnh hưởng source positions, diagnostics, Unicode escapes hoặc công cụ xử lý annotation. Nếu compiler thật sự nhận text đã chuẩn hóa, chỉ khi đó mới hash text chuẩn hóa.

### 4.2. Tên logical source là một input riêng

Nguồn `com.example.Rule` thường được biểu diễn bằng URI `string:///com/example/Rule.java`. Tên file/URI có thể ảnh hưởng diagnostic, quy tắc public top-level type và source lookup. Vì vậy source fingerprint nên là cặp:

~~~text
logicalPath = com/example/Rule.java
contentDigest = SHA-256(UTF-8 of exact source String)
~~~

Không suy tên class chỉ bằng regex trên source bất kỳ: comment, Unicode escapes, nested classes và nhiều top-level type có thể làm regex sai. Yêu cầu caller cung cấp logical unit name hoặc dùng parser/contract nhất quán.

### 4.3. Batch nhiều file phải gồm toàn bộ tập

Nếu compiler nhận `Policy.java` và `Rule.java`, sửa `Policy.java` có thể thay output của `Rule.java` dù bản thân `Rule.java` y nguyên. Key batch phải fingerprint cả hai. Hãy sort source units theo logical path để thứ tự duyệt `HashMap` không gây false miss; từ chối duplicate logical path vì mơ hồ. **Không sort classpath/option theo cách này**, vì thứ tự của chúng có thể mang ý nghĩa.

### 4.4. Hash nào không phù hợp?

- `File.lastModified()`: file bị ghi đè trong cùng độ phân giải timestamp hoặc giữ nguyên mtime.
- Kích thước file: nội dung khác có thể cùng length.
- `String.hashCode()`: hash 32-bit không đủ làm content-addressed key an toàn.
- Tên JAR, Maven coordinates, đường dẫn: không đảm bảo bytes.
- SHA-256 của **canonical manifest gồm toàn bộ input**: phương án thực dụng.

Đừng dùng hash để kết luận artifact “đáng tin”: cache nhiều tenant còn phải kiểm tra quyền, namespace, tính toàn vẹn và nguồn xuất bản.

## 5. Compiler options: dùng cấu hình effective, không dùng một vài checkbox UI

`JavaCompiler.getTask(...)` nhận danh sách option tokens. Để tạo key, phải lấy **options cuối cùng mà adapter truyền vào compiler**, sau khi áp dụng mọi default, policy và overrides. Những nhóm dễ bị bỏ sót:

- **Target và platform:** `--release 17`; hoặc `-source/-target` kết hợp platform configuration tương ứng. `--release` không dùng đồng thời với `-source/-target`.
- **Bytecode metadata:** `-g`/`-g:none`, `-parameters`, source level; một số option warnings có thể ảnh hưởng diagnostic hoặc thành bại khi đi cùng `-Werror`.
- **Symbol resolution:** `--class-path`/`-cp`, `--module-path`, `--module-source-path`, `--source-path`, `--patch-module`, `--add-modules`, `--add-exports` và lựa chọn liên quan theo chế độ hợp lệ.
- **Annotation processing:** `-proc:none`, `-processor`, `--processor-path`, `--processor-module-path`, `-Aname=value`.
- **Encoding:** `-encoding` cho nguồn file bytes; file manager custom có thể truyền char content đã decode từ trước.
- **Compiler plugins:** các extension compiler, file manager settings và version adapter.

**Giữ thứ tự option tokens** ở bước đầu để không bỏ qua ngữ nghĩa của repeated options và path ordering. Nếu muốn canonicalize `-cp` và `--class-path` thành một dạng, phải chứng minh chính compiler đang dùng hiểu chúng tương đương, và cần fingerprint **nội dung** các artifact mà option đó tham chiếu.

Tránh default ngầm từ current working directory hoặc `CLASSPATH`: chúng có thể khiến một request “trông giống nhau” nhưng compiler nhìn thấy class khác. Nên thiết lập classpath/modulepath tường minh, hoặc fingerprint các default thực tế. `JDK_JAVAC_OPTIONS` tác động tới `javac` command launcher; đừng tự giả định nó là options tự động được JavaCompiler API nhận trong cùng cách thức.

**Điểm quan trọng:** `--release 17` không cam kết bytecode giống nhau trên mọi compiler/JDK build, dù cùng API target. Include compiler/toolchain identity trong key.

## 6. Phụ thuộc: hash content của toàn bộ compile-visible graph

### 6.1. JAR có thể thay đổi mà path không đổi

~~~text
--class-path lib/api.jar

Lần đầu: lib/api.jar chứa Api.VERSION = 1
Lần sau: cùng path nhưng JAR chứa Api.VERSION = 2
~~~

Nếu key chỉ lưu `"lib/api.jar"`, cache có thể trả bytecode cũ. Compiler Java có thể **inline** các compile-time constant như `public static final int`. Vì vậy ngay cả thay đổi chỉ trong classpath JAR, source y nguyên cũng có thể yêu cầu compile lại.

Hash **bytes JAR thực**. Nếu ZIP timestamp/metadata khác nhưng classes không đổi, toàn-file digest gây false miss an toàn. Chỉ chuyển sang ABI hashing sau khi có mô hình chính xác về class ABI, constants, annotations và processors.

### 6.2. Classpath order không thể sort tùy tiện

Với hai JAR cùng chứa `com.example.Api`, compiler chọn class theo classpath lookup behavior. Đổi thứ tự:

~~~text
[api-v1.jar, api-v2.jar]
[api-v2.jar, api-v1.jar]
~~~

có thể cho kết quả khác. Trong manifest, mỗi entry nên có **logical artifact identity, lookup ordinal và content digest**. Không sort theo tên JAR để “canonicalize”, vì điều đó có thể làm hai input khác nhau thành cùng key.

### 6.3. Dependency trực tiếp và bắc cầu

JavaCompiler có thể đọc superclass, generic bound, interface method, annotation, module metadata, static constant, package class và source phụ, không chỉ các class xuất hiện ở `import`. Vì vậy hash “những JAR được import trực tiếp” là chưa đủ.

Điểm xuất phát đúng đắn là fingerprint **toàn bộ effective classpath/modulepath/sourcepath mà task có thể truy cập**, kể cả transitive JARs. Đây là một **superset an toàn**, có thể tạo miss khi thư viện không liên quan thay đổi. Cách tối ưu incremental dựa trên symbol dependency graph là một bài toán chuyên sâu; đừng chỉ dò `import` text.

### 6.4. Classpath directory và in-memory dependencies

Nếu dependency là thư mục `build/classes`, phải hash các file bên trong theo **relative path + content digest**; hash tên folder hoặc lastModified của folder là không đủ. Với modular code cần xét `module-info.class` và resolution config.

Nếu compiler lấy dependency bytecode từ một **MemoryFileManager** hoặc in-memory class map, key phải hash đúng các `byte[]` mà file manager trả cho compiler. Dùng cùng loại fingerprint cho persisted JAR và in-memory dependency, nhưng ghi rõ identity và thứ tự lookup để tránh va chạm giữa các nguồn.

### 6.5. Processor paths và input bên ngoài

Annotation processor có thể tạo class, source và resource dựa trên:
- implementation JAR và dependencies của processor;
- `-A` options, annotations, resources, config files;
- filesystem, env vars, clock, random, network.

Nếu không thể xác định và snapshot hết inputs mà processor được phép dùng, đánh dấu request **non-cacheable** hoặc chạy processor trong môi trường đã được ràng buộc/deterministic. Processor là mã chạy tại compile time; bản thân việc cho chạy processor không tin cậy trong host JVM cũng cần cân nhắc an toàn.

Trong ví dụ chạy được bên dưới dùng `-proc:none` để loại trừ processor khỏi luồng chính.

## 7. JDK/toolchain identity và reproducibility

Một cache key nên ghi toolchain ID, ví dụ:

~~~text
compiler implementation/provider: javax.tools JavaCompiler implementation
java.vendor
java.runtime.version
compile adapter schema/version
--release / platform configuration
processor plugins and their versions
~~~

Dùng exact version/build thường **bảo thủ nhưng đúng**; đổi JDK patch có thể tạo miss dù bytecode thực tế giống nhau. Không cần hash toàn bộ mọi environment variable vì nhiều biến không liên quan, làm giảm hit rate và có thể lộ secret. Những input bên ngoài mà processor thực sự đọc phải được khai báo và fingerprint hoặc tắt caching cho request ấy.

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu runtime image không cung cấp JDK compiler; production phải xử lý tình huống này. Nếu dùng Eclipse compiler hay một provider riêng, không dùng key namespace chung với javac trừ khi có kiểm chứng mạnh về tương thích output.

Nếu cache bao gồm formatted diagnostics, locale, source URI, warning/error policy cần được định danh chính xác. Một compilation success không có nghĩa diagnostics có thể tái sử dụng vô điều kiện cho tenant khác.

## 8. Quy trình canonicalization, lookup và lưu cache

~~~text
CompileRequest
    │
    ├── Validate logical names, policy, options
    ├── Materialize exact source bytes/text
    ├── Resolve and snapshot real dependency artifacts
    ├── Build effective compiler options/toolchain fingerprint
    │
    ▼
Canonical manifest → SHA-256 → cache key
    │
    ├── HIT → verify schema/integrity → immutable CompilationArtifact
    │
    └── MISS → single-flight → JavaCompiler + MemoryFileManager
                   │
                success?
                 /    \
               no      yes
               │        │
       diagnostics,     snapshot ALL bytecode and generated outputs
       no success       validate → atomic publish
       cache record         │
                            ▼
                      CompilationArtifact
                            │
                  Runtime ClassLoader generation
~~~

**Snapshot phải nhất quán.** Nếu một thread tính SHA-256 của `api.jar`, rồi file trên đĩa bị ghi đè trước khi compiler đọc, key mô tả bytes A nhưng output được tạo từ bytes B. Khắc phục bằng immutable content-addressed artifacts, bản sao snapshot rồi compile từ chính snapshot, hoặc cơ chế khóa/version/integrity phù hợp. Không nên dùng cùng đường dẫn mutable cho hai bước mà thiếu kiểm soát.

### Những thứ không nên đưa vào key

- `createdAt` và `lastAccessAt`: phục vụ eviction, không phải compile input.
- Random request ID không ảnh hưởng compiler: làm mọi lần miss.
- Absolute temporary directory nếu compiler không thấy và diagnostics không thuộc contract.
- ClassLoader generation ID khi **chỉ cache bytes biên dịch**; có thể load cùng bytes trong generation khác.
- Secret thô, user data không cần thiết; nếu cần tenant isolation, đặt namespace/quyền ở storage layer.

## 9. Ví dụ Java 17+ chạy được: tạo key và cache bytecode trong RAM

Ví dụ sau có một source `demo.Hello` không dùng thư viện bên ngoài; `-proc:none` vô hiệu hóa annotation processing. `JavaCompiler` tạo `.class` trong RAM qua `ForwardingJavaFileManager`; một `Cache` giữ byte arrays theo fingerprint có length-prefix và SHA-256.

### 9.1. Tệp CompileCacheDemo.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompileCacheDemo {
    static final class SourceUnit extends SimpleJavaFileObject {
        private final String content;

        SourceUnit(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output = new ByteArrayOutputStream();

        ClassBytes(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] snapshot() {
            return output.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> outputs = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            ClassBytes target = new ClassBytes(className, kind);
            outputs.put(className, target);
            return target;
        }

        Map<String, byte[]> classSnapshots() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            outputs.forEach((name, file) -> result.put(name, file.snapshot()));
            return result;
        }
    }

    static Map<String, byte[]> deepCopy(Map<String, byte[]> data) {
        Map<String, byte[]> copy = new LinkedHashMap<>();
        data.forEach((name, bytes) -> copy.put(name, bytes.clone()));
        return copy;
    }

    static void field(DataOutputStream out, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String sha256(byte[] input) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(input));
    }

    static String key(String binaryName, String source,
                      List<String> options, List<String> dependencies)
            throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            field(out, "java-inmem-compile-cache/v1");
            field(out, compiler.getClass().getName());
            field(out, System.getProperty("java.vendor"));
            field(out, System.getProperty("java.runtime.version"));
            field(out, binaryName);
            field(out, source);

            out.writeInt(options.size());
            for (String option : options) {
                field(out, option);
            }

            out.writeInt(dependencies.size());
            for (String dependency : dependencies) {
                field(out, dependency);
            }
        }
        return sha256(bytes.toByteArray());
    }

    static Map<String, byte[]> compileOnce(
            String binaryName, String source, List<String> options)
            throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (MemoryFileManager fileManager = new MemoryFileManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {
            Boolean success = compiler.getTask(
                    null, fileManager, diagnostics, options, null,
                    List.of(new SourceUnit(binaryName, source))).call();

            if (!Boolean.TRUE.equals(success)) {
                throw new IllegalStateException(
                        "Compile failed: " + diagnostics.getDiagnostics());
            }
            return fileManager.classSnapshots();
        }
    }

    // Single-threaded example. Add concurrency/eviction for production.
    static final class Cache {
        private final Map<String, Map<String, byte[]>> entries = new HashMap<>();
        private int compilerCalls;

        Map<String, byte[]> compile(
                String binaryName, String source, List<String> options,
                List<String> dependencyFingerprints) throws Exception {
            String fingerprint = key(
                    binaryName, source, options, dependencyFingerprints);
            Map<String, byte[]> existing = entries.get(fingerprint);
            if (existing != null) {
                System.out.println("HIT");
                return deepCopy(existing);
            }

            Map<String, byte[]> generated =
                    compileOnce(binaryName, source, options);
            entries.put(fingerprint, deepCopy(generated));
            compilerCalls++;
            System.out.println("MISS");
            return deepCopy(generated);
        }
    }

    public static void main(String[] args) throws Exception {
        String source = "package demo; public class Hello { "
                + "public static int twice(int x) { return x * 2; } }";
        String changed = source.replace("x * 2", "x * 3");
        List<String> options = List.of("--release", "17", "-proc:none");
        List<String> withParameters = List.of(
                "--release", "17", "-proc:none", "-parameters");

        Cache cache = new Cache();
        Map<String, byte[]> first =
                cache.compile("demo.Hello", source, options, List.of());
        Map<String, byte[]> again =
                cache.compile("demo.Hello", source, options, List.of());
        cache.compile("demo.Hello", changed, options, List.of());
        cache.compile("demo.Hello", source, withParameters, List.of());

        System.out.println("same bytes=" + Arrays.equals(
                first.get("demo.Hello"), again.get("demo.Hello")));
        System.out.println("compiler calls=" + cache.compilerCalls);

        // Fingerprints below are ONLY a key-change illustration.
        // They are not real JAR digests and are not compilation inputs.
        String depA = sha256("api-v1".getBytes(StandardCharsets.UTF_8));
        String depB = sha256("api-v2".getBytes(StandardCharsets.UTF_8));
        boolean dependencyKeyChanged =
                !key("demo.Hello", source, options, List.of("api:" + depA))
                .equals(key("demo.Hello", source, options,
                        List.of("api:" + depB)));
        System.out.println("dependency key changed=" + dependencyKeyChanged);
    }
}
~~~

Lệnh tại thư mục chứa file, máy có **JDK 17+**:

~~~powershell
javac --release 17 -encoding UTF-8 CompileCacheDemo.java
java CompileCacheDemo
~~~

Stdout được thiết kế cho chương trình:

~~~text
MISS
HIT
MISS
MISS
same bytes=true
compiler calls=3
dependency key changed=true
~~~

**Vì sao bốn lần gọi tạo ba lần biên dịch?**

1. Request đầu tiên: key chưa tồn tại → `MISS`; compiler được gọi.
2. Request thứ hai: cùng source + options + toolchain + dependency list → `HIT`, trả bytecode copy từ cache.
3. Request thứ ba: đổi thân hàm `x * 2` thành `x * 3` → source khác → `MISS`.
4. Request thứ tư: source cũ, bật `-parameters` → option khác → `MISS`.
5. Hai chuỗi `api-v1`/`api-v2` **chỉ để cho thấy dependency fingerprint khác tạo key khác**; ví dụ này không biên dịch dựa trên JAR ngoài. Trong production, `dependencyFingerprints` bắt buộc được tính từ **artifact thật mà JavaCompiler nhìn thấy**.

Lệnh `javac` tạo `CompileCacheDemo.class` và các nested class của **chương trình demo** trên đĩa. Source `demo.Hello` được biên dịch trong RAM; `MemoryFileManager` giữ `demo.Hello` bytecode trong `Map<String,byte[]>` mà không ghi `demo/Hello.class` xuống filesystem.

### 9.2. Vai trò từng lớp

- `SourceUnit`: dùng `SimpleJavaFileObject` có URI logical `.java` và cung cấp `CharSequence` từ `String`.
- `ClassBytes`: `SimpleJavaFileObject` đại diện output `.class`, nhận bytes qua `openOutputStream()`.
- `MemoryFileManager`: `ForwardingJavaFileManager` giữ cách tìm dependency của standard manager và override `getJavaFileForOutput` để thu output trong RAM.
- `Cache`: key → toàn bộ class map; clone `byte[]` khi lưu/trả để caller không sửa dữ liệu cache.
- `key`: encode có length-prefix, bao gồm compiler identity/JDK identity, source, ordered options và dependency fingerprints rồi dùng `MessageDigest SHA-256`.
- `compileOnce`: gọi `JavaCompiler.getTask`, thu diagnostics, chỉ trả artifact khi `call()` thành công.

**Giới hạn có chủ đích:** chương trình single-threaded, mỗi request một source, không có annotation processor, dependency ngoài, disk cache hoặc class loading. Muốn dùng với nhiều source thì truyền danh sách `JavaFileObject`, hash tất cả source cùng logical paths và giữ toàn bộ generated outputs. Nếu bật annotation processing, cần thu thêm các loại output mà processor tạo (kể cả `getFileForOutput` cho resources). Chỉ dùng code này làm nền để học, không nhận là caching classpath hoàn chỉnh nếu danh sách dependency vẫn rỗng.

## 10. Hash JAR/đầu ra thư mục đúng cách

### 10.1. Đoạn minh họa hash một JAR (không chạy độc lập)

~~~java
static String digestJar(java.nio.file.Path jar) throws Exception {
    java.security.MessageDigest digest =
            java.security.MessageDigest.getInstance("SHA-256");
    try (java.io.InputStream in = java.nio.file.Files.newInputStream(jar)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return java.util.HexFormat.of().formatHex(digest.digest());
}
~~~

Nếu `--class-path` là danh sách JAR, ghi các entry theo đúng lookup order:

~~~text
ClasspathEntry(kind=JAR, order=0, logicalId=api.jar, sha256=...)
ClasspathEntry(kind=JAR, order=1, logicalId=util.jar, sha256=...)
...
~~~

Với directory chứa classfiles, tạo manifest gồm **relative path + SHA-256 file content** cho mỗi mục mà compiler có thể đọc; sort theo relative path và hash manifest. Không lấy directory modification time làm dấu vân tay. Khi dùng symlink hoặc mount, cần quy ước resolve/snapshot rõ ràng; nếu classpath thay đổi đồng thời thì việc hash và compile có thể không nhất quán.

### 10.2. Đổi đường dẫn và đổi nội dung khác nhau

JAR cùng bytes nhưng ở một đường dẫn tạm mới có thể cùng content fingerprint. Tuy vậy nếu đường dẫn được ghi vào output/diagnostics, ảnh hưởng resource/package lookup hoặc được processor sử dụng, đường dẫn vẫn là input cần quản lý. **Đừng bỏ path vô điều kiện**; ghi logical ID và path policy đủ để compiler đọc đúng nguồn và hệ thống quyết định thế nào là request tương đương.

### 10.3. Compile-time ABI và constants

Chỉ hash public method signatures đôi khi chưa đủ. Ví dụ:

~~~java
// API dependency v1
public static final int MAX = 10;

// API dependency v2
public static final int MAX = 20;
~~~

Hai snippet này là **minh họa, không phải hai file Java độc lập**. Nếu caller compile `return Api.MAX;`, compiler có thể inline giá trị constant vào bytecode. Dù chữ ký field giống nhau, output phụ thuộc vào giá trị. ABI hashing nâng cao phải tính cả constants, generic signatures, annotations, visibility, hierarchy, modules và thứ processor có thể quan sát. **Hash nguyên JAR** thường đơn giản và an toàn hơn.

## 11. Invalidation: đầu vào nào đổi thì cache miss?

| Sự kiện | Kết quả theo key bảo thủ | Tại sao |
| --- | --- | --- |
| Source text thay đổi | **MISS** | Compiler nhận nội dung mới |
| Source mtime đổi, bytes không đổi | HIT nếu mtime không có nghĩa | Không hash metadata thuần túy |
| Thêm/bớt source trong batch | **MISS** | Symbol table/output thay đổi |
| Source collection đảo thứ tự không có nghĩa | HIT nếu đã canonical sort | Logical units vẫn như cũ |
| `--release 17` thành `--release 21` | **MISS** | Ngôn ngữ/platform/target khác |
| Bật `-parameters` hoặc đổi debug flags | **MISS** | Metadata classfile khác |
| JDK/compiler provider/version đổi | **MISS** theo policy bảo thủ | Toolchain có thể sinh output khác |
| JAR cùng path nhưng bytes mới | **MISS** | Class/method/constant thay |
| Đảo effective classpath order | **MISS** | Resolve class có thể khác |
| Thay một JAR không liên quan trong full path | MISS theo whole-path model | False miss an toàn; tối ưu về sau |
| Processor JAR/option/source phụ đổi | **MISS** hoặc non-cacheable | Generated classes/resources thay |
| Process restart, inputs/toolchain giữ nguyên | Có thể HIT trong persistent cache | Chỉ khi schema và integrity hợp lệ |
| Loader generation mới, bytecode input cũ | Compile cache có thể HIT | Runtime Class cần loader mới |
| Cache TTL hết hạn | Recompile khi entry bị evict | TTL quản lý lưu trữ, không thay fingerprints |

Cần phân biệt **cache invalidation theo nội dung** và **eviction theo thời gian/dung lượng**. TTL không sửa được một key thiếu dependency; entry còn TTL vẫn có thể sai nếu JAR đã đổi mà không được phản ánh vào key.

## 12. Cache value, integrity và âm bản lỗi

Một success entry đủ dùng:

~~~text
CompilationArtifact
  key and schema version
  compiler/platform identity
  source/option/dependency manifest for debugging
  status = SUCCESS
  classes: Map<binaryName, immutable byte[]>
  generatedSources/generatedResources (nếu contract yêu cầu)
  diagnostics (nếu được định danh và cho phép reuse)
  artifact/blob digest for integrity
  createdAt, lastAccessAt, sizeBytes (eviction metadata)
~~~

**Không chỉ lưu class chính.** Nếu compile sinh `Outer$Nested.class`, thiếu nó có thể làm class loader phát sinh `NoClassDefFoundError` khi chương trình dùng nested class. Generated resources của annotation processor cũng có thể ảnh hưởng runtime plugin.

**Không dùng `Map.copyOf` để coi byte[] bất biến:** map không cho thêm/bớt nhưng các arrays bên trong vẫn mutable. Dùng defensive copies, immutable blob storage hoặc policy không cấp byte arrays mutable trực tiếp cho plugin.

**Không ghi compile failure thành success entry.** Lỗi có thể do source không hợp lệ, dependency tạm mất, file manager/IO hoặc timeout. Nếu muốn negative cache, chỉ cache lỗi thật sự deterministic theo key đầy đủ, TTL ngắn và phân biệt transient errors. Bảo vệ diagnostics theo tenant, tránh trả thông tin source của user khác.

**Integrity khi đọc persistent/distributed cache:** xác minh schema, namespace/quyền, digest của blob output và manifest. Content digest giảm rủi ro corruption, nhưng một attacker có thể thay cả manifest/blob nếu không có access control; chữ ký/nguồn tin cậy vẫn cần thiết theo chính sách bảo mật.

## 13. Đồng thời: tránh compile trùng và publish chưa hoàn chỉnh

Nếu hai request đến cùng key lúc cache chưa có entry, cả hai có thể tự compile cùng source. Điều đó không sai về mặt correctness nhưng tốn tài nguyên. Dùng **single-flight theo key**, ví dụ một `ConcurrentHashMap<Key, CompletableFuture<CompilationArtifact>>` hoặc thư viện cache có compute-once semantics rõ ràng.

~~~text
Request A ----\
               +--- fingerprint K --- inFlight[K] --- một compilation task
Request B ----/                               |
                                          completed artifact
                                          /             \
                                        A nhận       B nhận
~~~

Đây là **sơ đồ thiết kế**, không phải Java chạy độc lập. Cần bảo đảm:

1. Có khóa/in-flight entry **theo đúng key** và không ép hai key khác compile chung.
2. Completion chỉ publish sau khi JavaCompiler kết thúc và toàn bộ output được snapshot.
3. Failures/cancellations được propagate; remove failed future theo policy để không cache exception vô hạn.
4. Giới hạn số compile đồng thời, CPU, heap và thời gian chạy.
5. Không mặc định chia sẻ một `JavaFileManager` mutable cho nhiều task đồng thời; mỗi task có state riêng hoặc cơ chế đồng bộ chính xác.
6. Một waiter timeout không nhất thiết hủy tác vụ đang phục vụ waiter khác.
7. Trước khi lưu artifact, xác minh lại consistency nếu inputs có thể thay đổi giữa fingerprint và compile.

Một `HashMap` như demo là **chỉ cho tuần tự**. Trong production, concurrent cache, per-key coordination và immutable artifact là phần thiết kế bắt buộc.

## 14. Bytecode cache không phải cache của ClassLoader

Một loader đã định nghĩa binary name `demo.Rule` từ bytes v1 không thể cứ gọi `defineClass` lại tên đó với bytes v2 để tạo cùng class identity mới. JVM gắn runtime class với **(binary name, defining loader)**.

Để thay plugin/rule được biên dịch mới:

~~~text
source/options/dependency input → compile key → bytecode map
                                                |
                        ┌───────────────────────┴───────────────────┐
                        ▼                                           ▼
                generation loader A                         generation loader B
                  Rule.class v1                                Rule.class v2
                        │                                           │
                   request cũ                                  request mới
                        └────────── drain/stop/release ─────────────┘
~~~

Bytecode cùng key có thể được dùng ở **hai loader mới khác nhau**, nhưng không đồng nghĩa các `Class<?>` object có cùng identity. Không nên cache `Class<?>` hoặc `ClassLoader` chung với bytecode mà không định nghĩa rõ generation lifecycle: cache đó có thể giữ strong references tới classloader cũ, gây leak Metaspace và giữ threads/resources.

`URLClassLoader.close()` (nếu dùng) giải phóng tài nguyên loader, không ép unload class tức thì. `ServiceLoader.reload()` xóa cache provider của service loader, cũng **không** làm source bytecode được biên dịch lại hoặc class đã load thay đổi.

## 15. Quy trình thử nghiệm và QA

| Test | Cách thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Lặp input y hệt | Compile hai lần source/options/deps/toolchain giống | HIT lần hai, compiler call = 1 |
| Source đổi một literal | Thay `x * 2` thành `x * 3` | MISS; bytecode tương ứng |
| Same source length | Thay nội dung nhưng giữ số ký tự | MISS; không dùng length làm key |
| Mtime giữ nguyên nhưng JAR đổi | Replace API JAR với bytes khác | MISS |
| Classpath order đảo | Hai JAR có trùng class name | MISS, resolution đúng |
| Transitive dependency đổi | Đổi constant/method của thư viện gián tiếp | MISS |
| Compiler option thay | `--release`, `-parameters` hoặc processor flags đổi | MISS |
| Annotation processor đọc input phụ | Đổi config/resource của processor | MISS hoặc non-cacheable |
| Compiler/toolchain nâng version | JDK patch/build/vendor đổi | MISS theo policy |
| Source batch thêm nested class | Compiler sinh nhiều class output | Cache giữ đủ tất cả `.class` |
| Missing dependency | Xóa classpath JAR bắt buộc | Không trả stale success; lỗi compile phản ánh input mới |
| Đồng thời cùng key | 20 request cùng lúc | Chỉ một compile, cùng artifact toàn vẹn |
| Lỗi compile | Source có cú pháp sai | Không tạo success entry |
| Cache blob corruption | Sửa cached bytes | Integrity check reject, recompile |
| Eviction | Xóa cache entry theo quota/TTL | Request tiếp theo compile lại chính xác |
| Runtime generation mới | Class cùng binary name v1 rồi v2 | Loader mới; không định nghĩa lại trong loader cũ |

**Lab mở rộng A — Dependency path không đổi:** biên dịch `return Api.LIMIT;` với dependency chứa `public static final int LIMIT = 10`; replace JAR cùng path bằng bản `LIMIT = 20`. So sánh cache chỉ hash path với cache hash JAR bytes để thấy nguy cơ stale constant.

**Lab mở rộng B — Một batch:** compile cùng lúc `Policy.java` và `Rule.java`; chỉ sửa `Policy.java` thì key batch phải đổi, dù text `Rule.java` không đổi.

**Lab mở rộng C — Tính ổn định:** cho collection source order thay đổi ngẫu nhiên, nhưng canonical source manifest sort theo logical path; xác minh key không đổi. Đảo **classpath order** thì key phải đổi.

**Lab mở rộng D — Đo hiệu năng:** dùng tập N request với K unique fingerprints, so hit rate = hits / lookups; compiler calls, p95/p99 compile latency, bytes cached, heap/Metaspace và eviction. Không “tối ưu” hit rate bằng cách lược bỏ dependency inputs.

## 16. Những sai lầm cần tránh

### 16.1. Chỉ hash mã nguồn

Cùng source nhưng compiler version, options, JAR/module path hoặc processor khác có thể tạo output khác. Key phải phản ánh các inputs khả dĩ ảnh hưởng.

### 16.2. Chỉ hash path/mtime/size của JAR

JAR có thể bị deploy lại với cùng path, timestamp và kích thước. Hash bytes thực tế compiler dùng; đảm bảo compiler đọc **cùng snapshot** đã hash để tránh TOCTOU.

### 16.3. Dùng `String.hashCode()`

Hash 32-bit không đủ làm content key. Dùng SHA-256 trên encoding canonical có length-prefix và namespace/schema version.

### 16.4. Sort classpath để key “đẹp”

Classpath lookup order có thể đổi version class được chọn. Giữ thứ tự có ý nghĩa; chỉ sort các collection logic dạng tập khi thứ tự thực sự không ảnh hưởng compile.

### 16.5. Bỏ dependency bắc cầu và generated sources

Compile có thể phụ thuộc vào superclass, annotation, generic type, constants và source tìm qua sourcepath. Annotation processor còn phát sinh outputs mới. Whole-path/batch fingerprint là lựa chọn ban đầu đáng tin.

### 16.6. Dùng lại bytecode object khi compiler output chưa đầy đủ

Một compile success phải snapshot **tất cả** class files; không publish map đang được `OutputStream` ghi. Không dùng `Map.copyOf` rồi giả định mảng bytes không thể bị sửa.

### 16.7. Cache lỗi vĩnh viễn hoặc dùng TTL để thay invalidation

Lỗi transient phải có đường retry. TTL chỉ loại bỏ entry theo thời gian; key thiếu dependency vẫn có thể hit sai trong thời gian TTL.

### 16.8. Coi ClassLoader là cache compiler

`ClassLoader` quản lý định nghĩa class runtime; compilation cache quản lý bytecode có thể dùng lại. Muốn version runtime mới cần generation/loader mới. Giữ `Class<?>` từ loader cũ có thể khiến unload không xảy ra.

### 16.9. Chạy processor/mã nguồn không tin cậy trong host mà không cách ly

Annotation processors là mã Java được thực thi lúc compile; bytecode do user viết có thể tác động tài nguyên khi thực thi. ClassLoader/JPMS không phải sandbox. Với mã không tin cậy, cân nhắc compilation/execution process riêng, giới hạn OS resources, timeouts và kiểm soát quyền.

## 17. Checklist thiết kế hệ thống thực tế

1. **Định nghĩa CompilationRequest:** một source, batch hay module; nguồn và logical names được validate.
2. **Đặt profile compiler:** version/toolchain, `--release`, file manager locations, processor policy.
3. **Snapshot inputs:** toàn bộ source và compile-visible artifacts, không để JAR đổi giữa fingerprint và task.
4. **Canonical manifest:** source sort theo logical path; options/classpath giữ thứ tự khi có ý nghĩa; hash nội dung và namespace version.
5. **SHA-256 key:** encoding có ranh giới trường, không gộp các input không tương đương.
6. **Compile:** `JavaCompiler.getTask` với `JavaFileManager` thích hợp; thu diagnostics và mọi output.
7. **Cache success:** bytecode map clone/immutable blob, schema/integrity, atomic publish; failure handling riêng.
8. **Concurrency:** single-flight per key, task resources và timeout/eviction.
9. **Runtime loading:** dùng classloader generation, không tái định nghĩa class cùng tên trong loader cũ.
10. **Verify:** source/options/dependency/toolchain thay đổi thì cache miss đúng; cùng input thì hit; test corruption, version drift và concurrency.

**Nguyên tắc xuyên suốt:** cache key phải đại diện cho **toàn bộ môi trường biên dịch có thể ảnh hưởng output**, không chỉ source text. Với JavaCompiler chạy trong bộ nhớ, một manifest ổn định gồm source + effective options + dependency content + compiler identity, được hash SHA-256 và dùng với input snapshot bất biến, là nền tảng để cache bytecode đúng và có thể mở rộng.

## 18. Tài liệu tham khảo Java SE 17

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- JavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html
- ForwardingJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- SimpleJavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- StandardJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- javac options, processor paths và --release: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- MessageDigest: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- ClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

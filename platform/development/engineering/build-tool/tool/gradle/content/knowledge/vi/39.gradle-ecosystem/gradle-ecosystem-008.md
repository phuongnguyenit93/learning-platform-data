# Tích hợp công cụ frontend qua task hoặc plugin có khai báo đầu vào, đầu ra trong Gradle

## 1. Vì sao không chỉ gọi npm từ Gradle?

Một dự án Java 17 đóng gói cả frontend vào JAR/WAR. Frontend được xây bằng Node.js, npm, pnpm, Yarn, Vite hoặc Webpack. Developer muốn khi chạy `gradle jar`, Gradle tự tạo bundle JavaScript/CSS rồi đưa bundle vào resources; nhưng nếu source frontend không đổi, Gradle không nên build lại.

Một giải pháp ban đầu có thể là:

~~~kotlin
tasks.register("buildWeb") {
    doLast {
        // Anti-pattern: chưa có input/output contract.
        project.exec {
            commandLine("npm", "run", "build")
        }
    }
}
~~~

Đoạn code này không phải thiết kế tốt cho Gradle hiện đại. Nó không khai các inputs như source tree, package-lock, Vite config, Node version, environment và không khai output directory. Ngoài ra, gọi `project.exec` trong task action dễ xung đột Configuration Cache; nên dùng `Exec` task hoặc injected `ExecOperations`.

**Điểm cốt lõi:** Gradle không cần tự hiểu JavaScript. Nó chỉ cần biết *đầu vào nào làm thay đổi kết quả*, *đầu ra thuộc về task nào*, *công cụ nào được gọi* và *task nào tiêu thụ đầu ra*. Khi contract đúng, Gradle sẽ thực hiện up-to-date checks và xây task graph an toàn.

Bài thuộc nhóm **Hệ sinh thái Gradle** của module **Build Tool Gradle**. Ta học hai con đường: tự viết typed task chạy Node, hoặc dùng Node Gradle plugin để tích hợp npm/pnpm/Yarn. Đồng thời thực hành đóng gói frontend vào Java resources và kiểm correctness của incremental build.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `Exec`, custom task + `ExecOperations`, `NodeTask` và `NpmTask`.
2. Khai `@InputDirectory`, `@InputFiles`, `@InputFile`, `@Input`, `@OutputDirectory`, `@OutputFile`.
3. Dùng Gradle runtime API `inputs.files`, `inputs.property` và `outputs.dir` cho các task loại Exec/NpmTask.
4. Chọn `PathSensitivity.RELATIVE` thay vì absolute paths khi frontend bundler phụ thuộc relative imports.
5. Hiểu `UP-TO-DATE` khác `FROM-CACHE` và khi nào dùng `@CacheableTask`.
6. Quản lý package.json và package-lock.json/pnpm-lock.yaml/yarn.lock trong dependency graph.
7. Phân biệt npm install/npm ci và chọn deterministic installation cho CI.
8. Dùng `tasks.register`, `TaskProvider`, `Provider.flatMap` để nối frontend producer vào `processResources`/`jar`.
9. Tránh copy generated files vào `src/main/resources` hoặc cho hai tasks ghi cùng `dist`.
10. Kiểm Node runtime, registry/proxy, lockfile integrity, CI matrix và reproducibility.
11. Viết Kotlin DSL project đầy đủ dùng Java17, Node ES module, Gradle typed task và resource packaging.
12. Chạy `javac/java` độc lập, `node` độc lập và Gradle tasks với expected stdout.
13. Xác định vì sao một task không rebuild sau config/env changes hoặc rebuild quá nhiều.
14. Phân biệt Configuration Cache, Build Cache, Gradle Daemon và package manager caches.
15. Thiết kế convention plugin cho nhiều frontend modules mà không làm mất lazy configuration.

## 2. Mô hình producer → consumer

~~~text
frontend/src/index.html
frontend/src/app.js
frontend/src/style.css
frontend/build.mjs
        |
        | Gradle declares source/script/mode as inputs
        v
:buildFrontend
        |
        | Node process transforms frontend
        v
build/generated/frontend/
  index.html
  app.js
  style.css
        |
        | TaskProvider.flatMap(output directory)
        v
:processResources
        |
        v
build/resources/main/public/
        |
        +--> :jar (packaged public/* resources)
        +--> :run (Java runtime classpath)
~~~

Gradle xây dependency graph. Node chạy transform. Java plugin copy output thành resources. Đó là khác biệt quan trọng so với một script shell chỉ chạy command theo thứ tự, không khai ownership của file.

### 2.1. Một frontend build task có contract gì?

Một task chuyển input set I thành output set O:

~~~text
O = bundle(
    source files,
    bundler script/config,
    dependency lockfile,
    build mode,
    public environment,
    toolchain versions
)
~~~

Mọi thứ ảnh hưởng bytes của O cần được theo dõi bằng Gradle task input hoặc ràng buộc một môi trường hermetic. Output phải nằm trong directory do task quản lý, không phải state tuỳ ý dưới workspace.

### 2.2. Những inputs thường bị bỏ quên

| Input | Ví dụ | Hậu quả nếu không khai |
| --- | --- | --- |
| Frontend source | `frontend/src/**/*` | Sửa code nhưng bundle không chạy lại |
| Public resources | `frontend/public/**/*` | Logo/font không cập nhật |
| Build script | `frontend/build.mjs` | Sửa transformer mà task UP-TO-DATE sai |
| Bundler config | `vite.config.ts`, `webpack.config.cjs` | Đổi base URL/chunk config mà output cũ |
| TypeScript config | `tsconfig*.json`, extends chain | Type/build emit khác nhưng không rebuild |
| Package manifest | `package.json` | Scripts/dependencies thay đổi không được nhận |
| Lockfile | `package-lock.json` / `pnpm-lock.yaml` / `yarn.lock` | Dependency graph drift |
| Environment | `NODE_ENV`, `PUBLIC_BASE_URL` | Build mode/API base không đúng |
| Tool versions | Node/npm/pnpm/Yarn/Vite/esbuild | Bytes có thể khác theo runtime |
| Generated schema | OpenAPI/GraphQL/protobuf | Client code không sync với backend |
| Assets ngoài source tree | Fonts/icons/static files | Đầu ra bị stale |

Đừng khai mọi file trong repo là input nếu chỉ một vài files thật sự ảnh hưởng output: quá rộng thì task rebuild quá thường xuyên. Nhưng khai thiếu còn nguy hiểm hơn, vì tạo **false UP-TO-DATE**.

### 2.3. Output phải được sở hữu độc lập

Thông thường:

~~~text
build/generated/frontend/
├── index.html
├── app.js
└── style.css
~~~

Không để một task khác cùng ghi nơi này. Không khai `frontend/src` vừa là input vừa là output; nếu bundler viết ngược vào source directory, source snapshot đổi sau mỗi build, gây vòng lặp invalidation và dirty Git tree.

## 3. Gradle task input/output APIs

### 3.1. Typed task annotations

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sources: DirectoryProperty

@get:InputFile
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val builderScript: RegularFileProperty

@get:Input
abstract val mode: Property<String>

@get:OutputDirectory
abstract val destination: DirectoryProperty
~~~

Đây là **snippet trong custom task**, cần Gradle imports và task class. Trong Kotlin DSL, annotations đặt trên getter qua `@get:...`. Gradle sẽ fingerprint inputs và outputs. Nếu không khai input làm thay đổi output, Gradle không thể tự phát hiện.

### 3.2. @InputFiles và @SkipWhenEmpty

Với một task nhận nhiều file collections:

~~~kotlin
@get:InputFiles
@get:SkipWhenEmpty
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

`@SkipWhenEmpty` có thể làm task trả `NO-SOURCE` khi không có files. Dùng khi task có semantics hợp lý nếu không có source; nếu source bắt buộc để bundler hoạt động, `@InputDirectory` required và báo lỗi sớm có thể thích hợp hơn.

### 3.3. @OutputFile vs @OutputDirectory

- `@OutputFile`: task tạo một file có path biết trước, ví dụ `manifest.json`.
- `@OutputDirectory`: task sở hữu cả directory tree, phù hợp JS chunks/static bundle.
- `@OutputFiles`/`@OutputDirectories`: nhiều outputs, chỉ dùng khi task thật sự có contract đó.
- `@LocalState`: state cục bộ không được cache giống portable artifacts.
- `@Internal`: property chỉ dùng nội bộ, **không** tác động outputs — nếu tác động outputs mà đánh Internal, task model sẽ sai.

### 3.4. PathSensitivity

| Mức | Path data được fingerprint | Lời khuyên |
| --- | --- | --- |
| `ABSOLUTE` | Đường tuyệt đối | Chỉ khi tool thực sự dùng absolute path cho output |
| `RELATIVE` | Đường tương đối dưới input root | Phù hợp import relative paths của JS/TS |
| `NAME_ONLY` | Chỉ filename | Nguy cơ trùng tên ở thư mục khác |
| `NONE` | Không tính file path | Chỉ khi output hoàn toàn không phụ thuộc tên/vị trí |

Dùng `RELATIVE` cho frontend sources thông thường. Nếu di chuyển `src/components/Button.ts` sang `src/pages/Button.ts`, bundler module graph có thể khác dù bytes giữ nguyên. `NONE` có thể tạo kết luận không đổi sai.

### 3.5. Input normalization và output portability

`@IgnoreEmptyDirectories` và `@NormalizeLineEndings` có thể giảm invalidation giữa platforms khi thật sự hợp semantics. Đừng normalize line endings cho raw binary assets hoặc các files mà CRLF/LF thay đổi output bytes. Một task copy bytes nguyên trạng **không** được tự tuyên bố tương đương nếu line ending đổi.

## 4. Up-to-date và Build Cache

### 4.1. UP-TO-DATE

Nếu task có inputs/outputs đủ, Gradle ghi snapshot. Lần sau không đổi source/config/output, task có thể báo:

~~~text
> Task :buildFrontend UP-TO-DATE
~~~

Node/npm process **không được gọi lại**. Thay input, xóa output hoặc thay task implementation sẽ làm Gradle xét chạy lại.

### 4.2. FROM-CACHE

Nếu task được phép cache và Gradle có matching cached output:

~~~text
> Task :buildFrontend FROM-CACHE
~~~

thì Gradle restore artifact thay vì execute external tool. Cần **task thật sự cacheable**, chứ không phải chỉ có `outputs.dir` hoặc `org.gradle.caching=true`.

### 4.3. Cacheability của frontend cần chứng minh

Task Node có thể phụ thuộc những yếu tố chưa khai:

- Node executable bytes/version mà `executable="node"` không theo dõi.
- npm package manager version/lockfile và resolved tarball integrity.
- OS/CPU architecture cho packages có native binaries (esbuild/sharp/swc).
- Environment variables, locale, timezone, random IDs.
- Remote font/icons/API schemas và network response.
- Timestamps/Git SHA trong generated banners.
- Plugin/bundler implementation classpath.
- Absolute workspace paths trong source maps.
- Non-deterministic file ordering.

Vì thế trong lab ta dùng `@DisableCachingByDefault`: cho phép **up-to-date checks** nhưng không mặc định lưu/restore outputs qua remote Build Cache khi toolchain chưa hermetic.

### 4.4. Khi nào dùng @CacheableTask?

Chỉ sau khi:

1. Pin Node/runtime/package manager/bundler versions.
2. Khai tất cả source/lock/config/env/tool inputs.
3. Chạy build từ hai clean workspaces và so outputs SHA-256.
4. Kiểm relocation khác absolute path.
5. Kiểm OS/architecture khi có native packages.
6. Không build với hidden network requests.
7. Giữ output deterministic, không chứa volatile timestamps/random.
8. Dùng Gradle TestKit hoặc CI thực nghiệm cache hits và output correctness.

Khi đó mới gắn `@CacheableTask` cho typed task hoặc enable caching theo documented APIs. Không dùng `outputs.cacheIf { true }` bừa bãi để "bật nhanh hơn".

### 4.5. Configuration Cache khác Build Cache

| Công nghệ | Reuse cái gì? |
| --- | --- |
| Configuration Cache | Kết quả configuration/task graph giữa invocations |
| Build Cache | Task outputs theo cache keys |
| Up-to-date checks | Bỏ execution khi local input/output snapshot không đổi |
| Gradle Daemon | JVM/JIT/classes/in-memory state |
| npm/pnpm/Yarn cache | Downloaded packages/tarballs/store |

Một task có thể `UP-TO-DATE` dù Build Cache tắt. Một Configuration Cache hit không bảo đảm Node bundler được skip.

## 5. Lựa chọn công cụ

### 5.1. Gradle Exec task

`Exec` là core Gradle task type, phù hợp lệnh Node ngắn:

~~~kotlin
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.PathSensitivity

val generatedDir =
    layout.buildDirectory.dir("generated/frontend")

tasks.register<Exec>("buildFrontendExec") {
    executable = "node"
    args(
        file("frontend/build.mjs").absolutePath,
        file("frontend/src").absolutePath,
        generatedDir.get().asFile.absolutePath,
        "production"
    )

    inputs.dir("frontend/src")
        .withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.file("frontend/build.mjs")
        .withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.property("mode", "production")
    inputs.property("nodeExecutable", "node")
    outputs.dir(generatedDir)
}
~~~

Đây là **fragment** cho frontend files như lab phần 7, không phải một dự án đầy đủ thứ hai. `Exec` đã có process action; không cần `doLast { project.exec(...) }`. Task được `register` lazily. `generatedDir.get()` được gọi khi task config, không ở top-level, nhưng typed managed properties còn rõ ràng hơn.

### 5.2. Custom typed task + ExecOperations

Dùng typed task nếu muốn:

- Khai input/output qua annotations.
- Reuse trong nhiều modules qua convention plugin.
- Test task logic dễ dàng.
- Tránh truy Gradle `Project` từ `@TaskAction`.
- Có typed `DirectoryProperty`, `RegularFileProperty`, `Property<String>`.
- Thiết lập cacheability policy rõ.

Gradle `ExecOperations` là service được inject bằng `javax.inject.Inject`. Thực thi process từ task action qua service này phù hợp hơn với Configuration Cache so với `project.exec` trong action.

### 5.3. Community Node Gradle plugin

Plugin `com.github.node-gradle.node` cung cấp Node/npm/pnpm/Yarn provisioning và task types như `NodeTask`, `NpmTask`. Theo Gradle Plugin Portal đã kiểm tra, bản **7.1.0** là release mới nhất được hiển thị. Cần pin/review version và xem docs của version áp dụng.

Plugin hỗ trợ setup Node runtime, nhưng **không tự đoán hết inputs/outputs của bundle Vite**; người viết build vẫn phải declare đúng.

## 6. Lab runnable: Java 17 + Node frontend + Gradle

### 6.1. Mục tiêu lab

Lab không dùng npm dependency ngoài; chỉ Node built-in modules. Chạy được khi máy có:

- JDK 17 (hoặc JDK mới được Gradle hỗ trợ, với Java17 toolchain).
- Gradle distribution hỗ trợ Java17; khi có Wrapper nên dùng Wrapper.
- Node.js hỗ trợ ES modules/`node:fs/promises` (ví dụ Node22).
- Files đúng theo cây thư mục.

Ta sẽ chứng minh:

- `buildFrontend` chỉ chạy khi inputs/outputs thay đổi.
- `processResources` tiêu thụ frontend output mà không hard-code đường generated file.
- `jar` chứa `public/index.html`, `public/app.js`, `public/style.css`.
- `run` khởi Java application đọc packaged resources.
- `javac/java` độc lập chạy được một Java17 class.
- `node frontend/build.mjs ...` độc lập tạo assets.

### 6.2. Cây thư mục

~~~text
frontend-gradle-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── frontend/
│   ├── build.mjs
│   └── src/
│       ├── index.html
│       ├── app.js
│       └── style.css
└── src/main/java/demo/frontend/
    ├── AssetInspector.java
    └── StandaloneCheck.java
~~~

Thư mục `build/` được Gradle tạo, không commit. Lab mới chưa có `gradlew`; dùng `gradle` đã cài hoặc tạo Wrapper theo quy trình team.

### 6.3. settings.gradle.kts

~~~kotlin
rootProject.name = "frontend-gradle-lab"
~~~

### 6.4. build.gradle.kts — toàn bộ file

~~~kotlin
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.language.jvm.tasks.ProcessResources
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

plugins {
    application
}

group = "demo.frontend"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

application {
    mainClass.set("demo.frontend.AssetInspector")
}

@DisableCachingByDefault(
    because = "Node runtime and process environment are not fully pinned"
)
abstract class BundleFrontend @Inject constructor(
    private val execOperations: ExecOperations
) : DefaultTask() {

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sources: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val builderScript: RegularFileProperty

    @get:Input
    abstract val mode: Property<String>

    @get:Input
    abstract val nodeExecutable: Property<String>

    @get:OutputDirectory
    abstract val destination: DirectoryProperty

    @TaskAction
    fun bundle() {
        execOperations.exec {
            commandLine(
                nodeExecutable.get(),
                builderScript.get().asFile.absolutePath,
                sources.get().asFile.absolutePath,
                destination.get().asFile.absolutePath,
                mode.get()
            )
        }.assertNormalExitValue()
    }
}

val buildFrontend = tasks.register<BundleFrontend>("buildFrontend") {
    group = "frontend"
    description = "Bundles tracked frontend sources"

    sources.set(
        layout.projectDirectory.dir("frontend/src")
    )
    builderScript.set(
        layout.projectDirectory.file("frontend/build.mjs")
    )
    mode.convention(
        providers.gradleProperty("frontendMode")
            .orElse("production")
    )
    nodeExecutable.convention(
        providers.gradleProperty("nodeBinary")
            .orElse("node")
    )
    destination.set(
        layout.buildDirectory.dir("generated/frontend")
    )
}

tasks.named<ProcessResources>("processResources") {
    from(buildFrontend.flatMap { it.destination }) {
        into("public")
    }
}
~~~

#### Giải thích từng thành phần

1. `application` core plugin tạo `run` và Java source sets; không cần external Gradle plugin.
2. `java.toolchain` chọn JDK17 cho compile/runtime tasks; `options.release` giới hạn bytecode/API target.
3. `BundleFrontend` là typed task; `ExecOperations` được inject vào constructor.
4. `@InputDirectory sources` theo dõi source tree.
5. `@InputFile builderScript` theo dõi Node transform logic.
6. `@Input mode` theo dõi `-PfrontendMode`.
7. `@Input nodeExecutable` theo dõi literal executable option; **không** theo dõi actual binary bytes khi gọi `node` trên PATH.
8. `@OutputDirectory destination` theo dõi tree do task tạo.
9. `@PathSensitive(RELATIVE)` giảm phụ thuộc absolute workspace path.
10. `@DisableCachingByDefault` nói rõ lý do không bật Build Cache; nó **không tắt local up-to-date checks**.
11. `TaskProvider<BundleFrontend>` được giữ trong `buildFrontend`.
12. `processResources.from(buildFrontend.flatMap...)` tạo source provider mang producer task identity.
13. Gradle suy ra dependency trước khi copy assets; không cần `dependsOn(buildFrontend)` trùng lặp.
14. Không dùng `project.exec` hoặc `project.file` trong task action.
15. External Node command exit nonzero khiến task fail, build không được báo xanh giả.
16. Paths được lấy từ managed `DirectoryProperty`/`RegularFileProperty` thay vì raw static `build/...` strings.
17. Task action không chứa credentials hoặc network requests.

### 6.5. frontend/build.mjs

~~~javascript
import {
    mkdir,
    readFile,
    rm,
    writeFile
} from "node:fs/promises";
import { join, resolve } from "node:path";

const [sourceArgument, targetArgument, mode] =
    process.argv.slice(2);

if (!sourceArgument || !targetArgument || !mode) {
    throw new Error("Expected sourceDir targetDir mode");
}

if (!["production", "development"].includes(mode)) {
    throw new Error("Unsupported mode: " + mode);
}

const sourceDirectory = resolve(sourceArgument);
const targetDirectory = resolve(targetArgument);
const files = ["index.html", "app.js", "style.css"];

// This lab's build output is controlled by its Gradle task.
await rm(targetDirectory, {
    recursive: true,
    force: true
});
await mkdir(targetDirectory, { recursive: true });

for (const filename of files) {
    let content = await readFile(
        join(sourceDirectory, filename),
        "utf8"
    );

    if (filename === "app.js") {
        content = "// mode=" + mode + "\n" + content;
    }

    await writeFile(
        join(targetDirectory, filename),
        content,
        "utf8"
    );
}

console.log("FRONTEND_BUNDLE=OK");
~~~

Script dùng built-in Node APIs, nên không cần `npm install` để chạy lab. Output deterministic theo input files và mode. Script xóa `targetDirectory` để không giữ stale assets, nhưng với production hãy validate output path; không truyền đường dẫn tuỳ ý dẫn ra ngoài workspace hoặc directory chứa dữ liệu quan trọng.

### 6.6. frontend/src/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Gradle frontend</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1 id="headline">Gradle + Node</h1>
  <script type="module" src="app.js"></script>
</body>
</html>
~~~

### 6.7. frontend/src/app.js

~~~javascript
const title = document.getElementById("headline");

if (title) {
    title.dataset.ready = "yes";
}
~~~

### 6.8. frontend/src/style.css

~~~css
h1 {
    color: #2563eb;
    font-family: sans-serif;
}
~~~

### 6.9. src/main/java/demo/frontend/AssetInspector.java

~~~java
package demo.frontend;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class AssetInspector {
    private AssetInspector() {
    }

    public static void main(String[] args)
            throws IOException {

        try (
            InputStream htmlStream =
                AssetInspector.class.getResourceAsStream(
                    "/public/index.html"
                );
            InputStream jsStream =
                AssetInspector.class.getResourceAsStream(
                    "/public/app.js"
                )
        ) {
            if (htmlStream == null || jsStream == null) {
                throw new IllegalStateException(
                    "Frontend resources missing"
                );
            }

            String html = new String(
                htmlStream.readAllBytes(),
                StandardCharsets.UTF_8
            );
            String script = new String(
                jsStream.readAllBytes(),
                StandardCharsets.UTF_8
            );

            boolean htmlFound = html.contains(
                "Gradle + Node"
            );
            boolean production = script.startsWith(
                "// mode=production\n"
            );

            System.out.println(
                "HTML_FOUND=" + htmlFound
            );
            System.out.println(
                "BUNDLE_MODE=" +
                    (production ? "production" : "other")
            );
        }
    }
}
~~~

Java method không chạy JavaScript; nó chỉ mở resources từ classpath và xác minh contents. Không cần HTTP server cho phép thử này.

### 6.10. src/main/java/demo/frontend/StandaloneCheck.java

~~~java
package demo.frontend;

public final class StandaloneCheck {
    private StandaloneCheck() {
    }

    public static void main(String[] args) {
        System.out.println("JAVA17_STANDALONE=OK");
    }
}
~~~

### 6.11. Chạy frontend task

Từ project root:

~~~bash
java -version
node --version
gradle --version
gradle clean buildFrontend --console=plain
~~~

Khi task execute, Node script in marker:

~~~text
FRONTEND_BUNDLE=OK
~~~

Outputs:

~~~text
build/generated/frontend/
├── index.html
├── app.js
└── style.css
~~~

Chạy lại:

~~~bash
gradle buildFrontend --console=plain
~~~

Nếu không đổi source/script/mode/output, Gradle thường báo `UP-TO-DATE` và không in marker. Khi runtime Node trên PATH thay đổi nhưng literal `nodeBinary` không đổi, Gradle chưa tự phát hiện tool change — đây là giới hạn có chủ ý của lab, cần pin tool trong production.

### 6.12. Chạy Java app qua Gradle

~~~bash
gradle clean run --quiet
~~~

Với mode mặc định `production`, stdout ổn định từ hai chương trình:

~~~text
FRONTEND_BUNDLE=OK
HTML_FOUND=true
BUNDLE_MODE=production
~~~

Dòng đầu từ Node; hai dòng sau từ Java main. Nếu Gradle/plugins môi trường thêm logging ngoài `--quiet`, có thể có dòng phụ; ba markers này vẫn là kết quả cần kiểm.

Tại sao `run` chạy frontend? Application plugin tạo task `run` dựa trên runtime classpath, trong đó có `processResources`; CopySpec của `processResources` lấy files từ Provider của `buildFrontend`, nên producer được scheduled khi cần.

### 6.13. Đóng gói JAR

~~~bash
gradle clean jar --console=plain
jar tf build/libs/frontend-gradle-lab-1.0.0.jar
~~~

Những archive entries cần thấy:

~~~text
public/index.html
public/app.js
public/style.css
demo/frontend/AssetInspector.class
demo/frontend/StandaloneCheck.class
~~~

`jar` của core Java/Application plugin không tự tạo fat JAR hoặc Main-Class manifest. Muốn chạy `java -jar` cần packaging/manifest/runtime classpath phù hợp; dùng `gradle run` là cách đơn giản trong lab.

### 6.14. Mode là input thực sự

~~~bash
gradle buildFrontend -PfrontendMode=development \
    --console=plain
~~~

PowerShell:

~~~powershell
gradle buildFrontend -PfrontendMode=development --console=plain
~~~

Mode changed → input fingerprint changed → frontend action chạy lại khi cần. Output `app.js` bắt đầu bằng:

~~~javascript
// mode=development
~~~

Chạy Java app với property tương ứng:

~~~bash
gradle run -PfrontendMode=development --quiet
~~~

Java in `BUNDLE_MODE=other` vì program chỉ phân biệt literal `production`. Đó là kiểm tra intentional rằng mode đã ảnh hưởng artifact bytes.

### 6.15. Source/script change

Sửa `frontend/src/app.js` hoặc `frontend/build.mjs` rồi chạy:

~~~bash
gradle buildFrontend --info --console=plain
~~~

Gradle nhìn thấy input được khai đổi. Nếu script tự đọc file cấu hình khác ngoài hai inputs, bạn phải khai thêm file đó, nếu không task model vẫn có blind spot.

### 6.16. Dry run

~~~bash
gradle run --dry-run --console=plain
~~~

Xem task graph nhưng không chạy Node/Java actions. Nếu thấy `:buildFrontend` trước `:processResources`, bạn đã xác nhận quan hệ graph; **không** chứng minh assets được sinh ra thực sự.

### 6.17. Chạy Node độc lập

Linux/macOS hoặc PowerShell:

~~~bash
node frontend/build.mjs frontend/src manual-dist production
~~~

Stdout chính xác:

~~~text
FRONTEND_BUNDLE=OK
~~~

Output vào `manual-dist`, không tạo Gradle task history. Dùng để debug script; muốn kiểm task orchestration phải dùng Gradle commands.

### 6.18. javac/java độc lập trên Java 17

Linux/macOS:

~~~bash
mkdir -p manual-java
javac --release 17 -d manual-java \
    src/main/java/demo/frontend/StandaloneCheck.java
java -cp manual-java demo.frontend.StandaloneCheck
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force manual-java | Out-Null
javac --release 17 -d manual-java src\main\java\demo\frontend\StandaloneCheck.java
java -cp manual-java demo.frontend.StandaloneCheck
~~~

Stdout chính xác:

~~~text
JAVA17_STANDALONE=OK
~~~

Chạy độc lập không yêu cầu Node hay Gradle, nên nó không xác nhận resource packaging; hai phép thử có mục tiêu khác nhau.

## 7. Node Gradle plugin: phiên bản 7.1.0

Theo Gradle Plugin Portal tại thời điểm biên soạn, `com.github.node-gradle.node` bản **7.1.0** là release mới nhất hiển thị. Plugin hỗ trợ Node/npm/pnpm/Yarn tasks và có thể provision Node runtime.

### 7.1. Thêm plugin

Một cấu hình **thay thế** cho project tích hợp Node qua plugin:

~~~kotlin
import com.github.gradle.node.task.NodeTask
import org.gradle.api.tasks.PathSensitivity

plugins {
    id("com.github.node-gradle.node") version "7.1.0"
}

node {
    version.set("22.14.0")
    download.set(true)
    nodeProjectDir.set(file("frontend"))
}
~~~

Cần Plugin Portal/mirror được phép truy cập để tải plugin. `download=true` yêu cầu plugin provision Node distribution nếu chưa có. Nếu `download=false`, Node trên PATH/environment phải do team/CI quản lý. Không đặt cả plugin task và core custom task cùng ghi một output directory.

### 7.2. NodeTask runnable với script lab

~~~kotlin
val pluginOutput = layout.buildDirectory.dir(
    "generated/frontend-plugin"
)

val frontendViaPlugin =
    tasks.register<NodeTask>("frontendViaPlugin") {
        script.set(file("frontend/build.mjs"))

        args.set(
            pluginOutput.map { directory ->
                listOf(
                    file("frontend/src").absolutePath,
                    directory.asFile.absolutePath,
                    "production"
                )
            }
        )

        inputs.dir("frontend/src")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.file("frontend/build.mjs")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.property("mode", "production")
        inputs.property("nodeVersion", "22.14.0")

        outputs.dir(pluginOutput)
    }
~~~

Đây là **snippet cho build đã áp Node plugin 7.1.0** và dùng files của lab; nó không thay thế mọi dòng trong Java Application setup. Gradle plugin cung cấp `NodeTask` và Node setup; bạn vẫn phải khai inputs/outputs theo source/config thực tế.

### 7.3. Dùng output plugin vào Java resource

Nếu **chọn NodeTask thay cho typed task lab**, cấu hình consumer tương ứng:

~~~kotlin
tasks.named<ProcessResources>("processResources") {
    from(pluginOutput) {
        into("public")
    }
    dependsOn(frontendViaPlugin)
}
~~~

Snippet trên tường minh `dependsOn` nhưng dùng một Provider của directory chưa mang producer provenance tự động; tốt hơn khi plugin task outputs có Provider identity hoặc nối `from(frontendViaPlugin)` sau khi xác minh task outputs. Không bật đồng thời cả hai producers vào cùng `public/`; phải chọn **một** con đường.

### 7.4. Cấu hình repository khi Node download bị chặn

Node Gradle plugin có thể thêm Ivy repository để tải Node distributions. Với repository policy `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, plugin `download=true` có thể gặp lỗi vì không được thêm project repository. FAQ plugin có hướng dẫn khai Ivy repository ở `settings.gradle.kts` và chỉnh `distBaseUrl` thích hợp, hoặc CI có thể preinstall Node và tắt plugin download. Không tự bỏ strict repository policy chỉ để vượt lỗi provisioning.

## 8. NpmTask và npmInstall

### 8.1. npm ci là gì?

Khi project có `package.json` và committed `package-lock.json` tương thích:

~~~bash
npm ci
npm run build
~~~

`npm ci` cài dependencies theo lockfile trong môi trường clean; không chủ ý sửa lockfile. Nếu lockfile lệch manifest, nên fail sớm. `npm install` có thể cập nhật dependency resolution/lockfile, nên không thay npm ci trong release CI một cách vô thức.

### 8.2. Node plugin cài dependency

Trong `build.gradle.kts` đã apply Node plugin:

~~~kotlin
import com.github.gradle.node.npm.task.NpmTask

node {
    nodeProjectDir.set(file("frontend"))
    npmInstallCommand.set("ci")
}
~~~

`npmInstall` là task do plugin cung cấp; `npmInstallCommand` cho phép chọn command `ci`. Cần có lockfile hợp lệ. Không đặt property này trong project vanilla JS nếu không có package.json/package-lock.

### 8.3. Một package.json Vite minh họa

~~~json
{
  "name": "web-client",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "vite build --outDir ../build/generated/vite"
  },
  "devDependencies": {
    "vite": "6.3.6"
  }
}
~~~

Đây là **manifest minh họa**, không tự đủ để chạy `npm ci`. Tạo `package-lock.json` bằng npm phù hợp rồi commit; kiểm version package, security policy và availability trước khi dùng production.

### 8.4. NpmTask khai inputs/outputs

~~~kotlin
import com.github.gradle.node.npm.task.NpmTask
import org.gradle.api.tasks.PathSensitivity

val viteOutput = layout.buildDirectory.dir(
    "generated/vite"
)

val buildVite = tasks.register<NpmTask>("buildVite") {
    dependsOn(tasks.named("npmInstall"))
    npmCommand.set(listOf("run", "build"))

    inputs.files(
        "frontend/package.json",
        "frontend/package-lock.json"
    ).withPathSensitivity(PathSensitivity.RELATIVE)

    inputs.files(
        fileTree("frontend/src") {
            include("**/*")
        }
    ).withPathSensitivity(PathSensitivity.RELATIVE)

    inputs.files(
        fileTree("frontend") {
            include("vite.config.*")
            include("tsconfig*.json")
            include("postcss.config.*")
        }
    ).withPathSensitivity(PathSensitivity.RELATIVE)

    inputs.property("nodeVersion", "22.14.0")
    inputs.property("mode", "production")
    outputs.dir(viteOutput)
}
~~~

Đây là fragment cho Vite option `--outDir ../build/generated/vite`, giả định root build directory mặc định. Trong production nên pass output path qua một Provider/env/CLI argument để `viteOutput` và Vite script không bị lệch khi `layout.buildDirectory` thay đổi. Nếu `frontend/public`, `tsconfig.base.json` hoặc shared workspace modules ảnh hưởng output, **bổ sung chúng vào inputs**.

### 8.5. dependsOn install không thay declared inputs

`dependsOn(tasks.named("npmInstall"))` bảo đảm installation task được xét trước bundler. Nó **không tự khai** mọi source/config/lockfile/env inputs của `buildVite`. Nếu khóa dependency đổi, manifest+lockfile fingerprint phải invalidate bundle dù source JS giống nhau.

### 8.6. NodeTask/NpmTask không tự trở thành cacheable

Plugin giúp process execution/version management; task vẫn cần output và input model. Không gắn `outputs.dir` với thư mục mà command thực tế không ghi. Không bật cache nếu build còn phụ thuộc environment hidden hoặc node_modules native binary khác platform.

## 9. Các package managers khác

### 9.1. pnpm

~~~bash
pnpm install --frozen-lockfile
pnpm run build
~~~

Theo dõi `pnpm-lock.yaml`, `pnpm-workspace.yaml`, package.json và workspace packages. pnpm stores/symlinks có đặc tính khác npm; không đổi command đơn giản mà vẫn giữ npm lockfile/task semantics.

### 9.2. Yarn

Modern Yarn:

~~~bash
yarn install --immutable
yarn build
~~~

Yarn Classic v1 dùng options khác như `--frozen-lockfile`. Với Yarn Berry/Plug'n'Play, có thể không có node_modules; thêm `.yarnrc.yml`, `.pnp.cjs`, `.yarn/` khi chúng ảnh hưởng build và tuân security policy.

### 9.3. Không giữ nhiều lockfiles tùy tiện

Khi `package-lock.json`, `pnpm-lock.yaml` và `yarn.lock` cùng có trong repo mà không có policy, local/CI có thể cài dependency graphs khác nhau. Chọn một package manager version, commit lockfile đúng loại và đưa vào input fingerprints.

### 9.4. Workspaces

Nếu frontend phụ thuộc package `shared-ui` trong npm/pnpm workspace, khai source/manifest của shared-ui và **root lockfile**. Chỉ khai `frontend/src` là thiếu input, sẽ dẫn đến bundle stale khi shared-ui đổi.

## 10. Đóng gói vào Java resources

### 10.1. Java Application plugin

Trong lab:

~~~kotlin
tasks.named<ProcessResources>("processResources") {
    from(buildFrontend.flatMap { it.destination }) {
        into("public")
    }
}
~~~

Gradle nối output producer vào input consumer. `jar` sau đó lấy compiled classes và resources qua Java source set. Không cần copy output vào tracked `src/main/resources`.

### 10.2. Spring Boot

Với Spring Boot serving static resources, có thể thay `into("public")` bằng:

~~~kotlin
tasks.named<ProcessResources>("processResources") {
    from(buildFrontend.flatMap { it.destination }) {
        into("static")
    }
}
~~~

Đây là **phương án thay thế**, không phải add-on nếu đã có CopySpec `public`. Kiểm `bootJar` archive entries và framework static path conventions. Không giả định WAR, executable JAR và static-site distribution có cùng layout.

### 10.3. Direct Jar.from

~~~kotlin
tasks.named<Jar>("jar") {
    from(buildFrontend.flatMap { it.destination }) {
        into("META-INF/web")
    }
}
~~~

Đây là một phương án nếu muốn assets dưới `META-INF/web` thay vì Java resources root. Không đồng thời copy cùng files vào cùng path qua cả `processResources` và `jar` khiến duplicate entries.

### 10.4. War và distributions

WAR plugin thường có webapp root layout khác Java classpath resources. Application distributions có `distributions.main.contents.from(...)`. Chọn đúng target contract của deployment, tránh hard-code rằng tất cả frontend phải nằm ở `build/resources/main/public`.

### 10.5. Kiểm output chứ không chỉ kiểm task status

~~~bash
gradle clean jar
jar tf build/libs/frontend-gradle-lab-1.0.0.jar
~~~

Kiểm archive thực tế có assets, mode phù hợp và không chứa node_modules. Task UP-TO-DATE chỉ là tối ưu, không thay validation artifact contents.

## 11. CI: thống nhất orchestration

### 11.1. Pipeline

~~~text
checkout -> JDK 17 & Node 22 setup
         -> Gradle Wrapper
         -> :buildFrontend (or :npmInstall -> :buildVite)
         -> :processResources -> :jar
         -> tests/verification
         -> artifact archive/publish
~~~

Nên để Gradle task graph quản lý order, tránh một CI step chạy npm build và Gradle chạy lại task khác xuất cùng directory.

### 11.2. GitHub Actions minh họa

~~~yaml
name: Gradle frontend and Java

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/setup-node@v4
        with:
          node-version: '22.14.0'

      - uses: gradle/actions/setup-gradle@v6

      - name: Build
        run: ./gradlew clean build --stacktrace --console=plain

      - name: Keep diagnostics
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: frontend-gradle-diagnostics
          retention-days: 7
          if-no-files-found: warn
          path: |
            build/generated/frontend/
            build/reports/
            build/libs/
~~~

Snippet **giả định repo đã commit Gradle Wrapper**, không phải project lab chưa tạo Wrapper. Team cần pin action commit SHAs nếu security policy yêu cầu, xác minh action major versions/trust và tách secrets khỏi untrusted fork PRs. `always()` không cứu upload nếu runner đã chết.

### 11.3. Nếu plugin download Node

Nếu dùng `node.download=true`, Gradle plugin quản lý Node version; không nhất thiết cần `actions/setup-node`. Nhưng nếu CI chạy npm commands **ngoài Gradle**, phải tránh hai Node versions. Khi CI/laptop khác nhau, so version, environment variables, executable path và lockfile.

### 11.4. Build artifacts

Giữ khi cần:

- Java JAR/WAR đúng version.
- Asset manifest/stats/source maps nếu policy cho phép.
- Gradle build logs và Node/npm errors.
- Test/coverage reports.
- SHA-256 checksums và toolchain metadata.
- Lockfile / package-manager version evidence.

Không upload cả `~/.gradle`, `node_modules` hoặc private npm tokens như diagnostic artifact thông thường.

## 12. Reproducibility và security

### 12.1. Package scripts có quyền chạy code

`npm ci` có thể chạy install lifecycle scripts. Một dependency độc hại có thể đọc workspace/environment. Dùng trusted registries, lockfile/integrity checking, dependency scanning, least privilege CI tokens và isolate untrusted PR builds.

### 12.2. Secrets không được embed vào frontend

Static JS/CSS/HTML được người dùng tải về. Biến `PUBLIC_API_BASE_URL` có thể là public config hợp lệ; `NPM_TOKEN`, database password, OAuth client secret không được đưa vào bundle. CI masking ở console không làm raw ZIP/JAR chứa secret trở nên an toàn.

### 12.3. Node/toolchain version phải là input hoặc môi trường được pin

Literal `nodeBinary = "node"` không fingerprint executable bytes. Muốn remote cache an toàn, dùng Gradle Node plugin/toolchain provisioning hoặc explicit file/provider, pin version và kiểm cross-platform behavior. Nếu build tool động tải mới nhất từ remote, task không hermetic.

### 12.4. Build outputs phải deterministic

Không chèn current time, random hash không kiểm soát, absolute checkout path hoặc environment noise vào bundle nếu muốn stable outputs. Asset hash theo content thường tốt; timestamp-based filename có thể phá cache relocation.

### 12.5. Source maps

Sourcemaps có thể chứa original source code và path metadata. Đừng upload/publish public khi chưa đánh giá security/compliance. Giữ retention policy và control access cho debug artifacts.

### 12.6. Native packages và OS matrix

esbuild/swc/sharp có thể sử dụng binary dành riêng cho CPU/OS. Task caching giữa macOS ARM64 và Linux x86_64 có thể sai nếu bạn không model platform-sensitive inputs; phải test và giới hạn cache scope phù hợp.

## 13. Multi-project frontend

Một repository có:

~~~text
root/
├── backend/
├── admin-ui/
└── customer-ui/
~~~

Mỗi frontend module nên có output directory riêng:

~~~text
admin-ui/build/generated/frontend/
customer-ui/build/generated/frontend/
~~~

Không để cả hai tasks đồng thời ghi root `build/generated/frontend`. Nếu backend cần cả hai, dùng artifact variants/project dependencies hoặc provider wiring có ownership rõ; task `processResources` có thể copy chúng vào prefix khác nhau.

### 13.1. Convention plugin

Với nhiều modules, đóng gói custom task type và Node plugin setup trong convention plugin `build-logic`. Mỗi subproject chỉ khai sourceDir/outputDir/mode/tool version. Tránh root `subprojects { tasks.create(...) }` eager và cross-project mutation order-dependent.

### 13.2. Included builds/composite builds

Nếu frontend là included build, đừng giả định có thể lấy trực tiếp raw output path bằng string; thiết kế publication/consumption artifact hoặc task dependency bridge đúng model. Consumer phải biết producer identity, không chỉ biết tên directory.

### 13.3. Monorepo package workspaces

Nguồn `shared-ui` đổi → `admin-ui`/`customer-ui` bundle có thể đổi. Khai workspace manifests, root lockfile và shared source inputs; nếu chỉ khai mỗi module's local src, Gradle sẽ skip sai.

## 14. Groovy DSL tương đương

### 14.1. Exec variant

~~~groovy
tasks.register('buildFrontendExec', Exec) {
    def outputDir = layout.buildDirectory
        .dir('generated/frontend')

    commandLine(
        'node',
        file('frontend/build.mjs').absolutePath,
        file('frontend/src').absolutePath,
        outputDir.get().asFile.absolutePath,
        'production'
    )

    inputs.dir('frontend/src')
        .withPathSensitivity(PathSensitivity.RELATIVE)

    inputs.file('frontend/build.mjs')
        .withPathSensitivity(PathSensitivity.RELATIVE)

    inputs.property('mode', 'production')
    outputs.dir(outputDir)
}
~~~

Đây là một **fragment thay thế**, không chứa full Java/Application config của lab.

### 14.2. Node plugin Groovy DSL

~~~groovy
plugins {
    id 'com.github.node-gradle.node' version '7.1.0'
}

node {
    version = '22.14.0'
    download = true
    nodeProjectDir = file('frontend')
}
~~~

Cùng Gradle task modeling, syntax khác. Đối chiếu version-specific plugin docs vì API syntax/feature có thể đổi theo major release.

## 15. Chẩn đoán incremental behavior

### 15.1. Task luôn chạy lại

Có thể do:

- Output directory bị `clean`/CI cleanup xóa.
- Task ghi ngoài declared output directory.
- Source input chứa generated files tự thay đổi.
- Inputs gồm timestamps/volatile env.
- npm install thay node_modules/lockfile mỗi lần.
- Bundler emit file ngẫu nhiên.
- Task implementation/source inputs đổi.

Dùng:

~~~bash
gradle buildFrontend --info --console=plain
~~~

để đọc lý do out-of-date; không mặc định chữa bằng tăng Gradle daemon heap.

### 15.2. Task không chạy dù source config đổi

Có thể thiếu `inputs.file("vite.config.ts")`, lockfile, public env property hoặc shared workspace sources. Mở build script và enumerate **đúng mọi file tool thật sự đọc**. Dùng `--rerun-tasks` chỉ là chẩn đoán tạm, không sửa model.

### 15.3. Build Cache restore sai output

Có thể toolchain/OS/env không được fingerprint hoặc output nondeterministic. Tạm tắt cache cho task, thu artifact hashes, so Gradle task key inputs và đề xuất schema input còn thiếu.

### 15.4. CI "Cannot find module"

Kiểm npm/pnpm install task có chạy, working directory của package manager, package.json lockfile, runtime classpath/registry credentials và project workspace layout. Đừng chỉ thêm `dependsOn("npmInstall")` nếu Node task đang chạy ở folder không có module đó.

### 15.5. Missing resource trong Java

Kiểm:

~~~bash
gradle processResources --info
gradle jar
jar tf build/libs/frontend-gradle-lab-1.0.0.jar
~~~

Nếu `public/index.html` không có, kiểm producer output directory, CopySpec `into`, plugin resource configuration và task graph. Không tự sửa Java `getResourceAsStream` trước khi biết archive thiếu hay classpath sai.

### 15.6. Plugin không resolve được

`com.github.node-gradle.node` được tìm qua Gradle Plugin Portal/mirror, không phải npm registry. Kiểm `pluginManagement.repositories` trong Gradle settings, Gradle Wrapper version, offline/proxy/TLS/corporate plugin allowlist.

### 15.7. node.download bị repository mode chặn

Plugin cần Node distribution repo. Với `FAIL_ON_PROJECT_REPOS`, có thể cần khai Node Ivy repo ở settings theo FAQ hoặc dùng preinstalled runtime. Không hạ repository security policy tùy tiện.

### 15.8. npm ci fail

Nếu package-lock v3 không khớp package.json, npm ci trả error; có thể cần tạo lại lockfile bằng matching npm major, commit đầy đủ, sau đó CI dùng clean install. Đừng xóa lockfile để CI "hết fail".

## 16. Những lỗi phổ biến khi tích hợp

### Lỗi 1. Chạy npm trong configuration phase

**Vấn đề:** `gradle help` hoặc IDE sync đã chạy npm/network I/O dù không cần build frontend.

**Sửa:** task actions/plugin tasks lazy, không gọi process từ build script top-level.

### Lỗi 2. Quên output declaration

**Vấn đề:** Gradle không theo dõi `dist`, không up-to-date đúng.

**Sửa:** `@OutputDirectory` hoặc `outputs.dir` trỏ đúng directory tool tạo.

### Lỗi 3. Quên bundler script input

**Vấn đề:** đổi `build.mjs` nhưng task skip.

**Sửa:** `@InputFile`/`inputs.file` cho script và configs.

### Lỗi 4. Quên package-lock

**Vấn đề:** thay dependencies mà output cũ.

**Sửa:** lockfile là declared input, toolchain được pin.

### Lỗi 5. Đầu ra nằm trong đầu vào

**Vấn đề:** self-trigger, dirty source tree.

**Sửa:** dùng `layout.buildDirectory`.

### Lỗi 6. Hai tasks ghi chung output

**Vấn đề:** output overlap/race, cache unsafe.

**Sửa:** một task sở hữu một output directory riêng.

### Lỗi 7. Runtime Node từ PATH không được fingerprint

**Vấn đề:** máy khác Node version nhưng task vẫn UP-TO-DATE/cache key giống.

**Sửa:** pin/provision tool version và không cache khi runtime identity thiếu.

### Lỗi 8. UP-TO-DATE bị hiểu là FROM-CACHE

**Sửa:** phân biệt local snapshot và Build Cache output retrieval.

### Lỗi 9. --no-build-cache không ép task chạy

**Sửa:** dùng `--rerun-tasks` cho diagnostics; không nhầm cache với up-to-date.

### Lỗi 10. Task luôn rerun vì include build output làm input

**Sửa:** exclude `dist`/`build`/`node_modules` khi theo dõi frontend source tree.

### Lỗi 11. Copy trực tiếp vào src/main/resources

**Sửa:** processResources.from(output provider) với directory dưới build/.

### Lỗi 12. Chỉ dependsOn mà hard-code file path

**Sửa:** dùng Provider property/source để giữ output location + task dependency provenance.

### Lỗi 13. mustRunAfter thay dependsOn

**Sửa:** ordering constraint không tự schedule producer; dùng dependsOn/provider wiring.

### Lỗi 14. Ignore exit code từ npm

**Sửa:** fail Gradle task và CI job khi bundler lỗi.

### Lỗi 15. Coi npm ci là cache hit

**Sửa:** npm ci là dependency install, không phải Gradle Build Cache.

### Lỗi 16. npm ci không có lockfile

**Sửa:** generate+commit lockfile đúng package manager version.

### Lỗi 17. YARN v1 dùng --immutable

**Sửa:** dùng flags đúng Yarn major version; Yarn Classic có `--frozen-lockfile`.

### Lỗi 18. pnpm workspace đổi nhưng bundle không rerun

**Sửa:** khai root lockfile/shared packages/`pnpm-workspace.yaml`.

### Lỗi 19. Vite config đổi không tác động cache

**Sửa:** khai `vite.config.*`, TypeScript/PostCSS/Tailwind configs.

### Lỗi 20. Gradle Node plugin được coi là Gradle core plugin

**Sửa:** `com.github.node-gradle.node` là community plugin; pin version và cấu hình plugin repositories.

### Lỗi 21. npm node_modules được đưa vào JAR

**Sửa:** copy chỉ generated dist assets.

### Lỗi 22. Cache frontend build phụ thuộc network

**Sửa:** provision inputs offline/pin remote content; cache chỉ khi deterministic.

### Lỗi 23. Timestamp trong bundle

**Sửa:** loại volatile values hoặc mô hình hóa input có chủ đích, tránh false caching.

### Lỗi 24. Source map chứa sensitive code

**Sửa:** quyền truy cập và publishing rules rõ ràng.

### Lỗi 25. Build CLI pass nhưng CI thiếu node

**Sửa:** provision Node plugin hoặc CI setup-node, kiểm PATH/JDK/Gradle versions.

### Lỗi 26. Node plugin download=true và FAIL_ON_PROJECT_REPOS

**Sửa:** khai Ivy Node repo ở settings hoặc provision externally, theo plugin FAQ.

### Lỗi 27. Copy frontend vào JAR hai lần

**Sửa:** chọn một điểm nối `processResources` hoặc `jar.from`; không duplicate paths.

### Lỗi 28. Vite output path và Gradle outputs.dir khác nhau

**Sửa:** dùng một source of truth, test artifacts actually exist.

### Lỗi 29. Dùng @CacheableTask trước khi test relocation

**Sửa:** build trong hai clean workspaces, so hashes và task cache outcomes.

### Lỗi 30. Test only --dry-run

**Sửa:** dry-run chỉ kiểm graph; phải chạy actual tasks để kiểm bytes và Java runtime.

### Lỗi 31. Build chạy npm install hai lần

**Sửa:** CI và Gradle dùng một orchestrator có task graph thống nhất.

### Lỗi 32. Secrets đặt trong frontend PUBLIC_ variables

**Sửa:** chỉ đưa public configuration; never embed secrets vào static assets.

## 17. Bài tập có đáp án

### Bài 1. Vì sao `doLast { npm run build }` chưa đủ?

**Đáp án:** Thiếu inputs/outputs/tool identity, Gradle không thể quyết định up-to-date/cache đúng.

### Bài 2. Source directory dùng annotation nào?

**Đáp án:** `@InputDirectory`, thường kết hợp `@PathSensitive(PathSensitivity.RELATIVE)`.

### Bài 3. Bundler script được khai gì?

**Đáp án:** `@InputFile` để đổi script invalidates outputs.

### Bài 4. Destination dùng gì?

**Đáp án:** `@OutputDirectory` cho bundle chứa nhiều files.

### Bài 5. Build mode ảnh hưởng asset contents?

**Đáp án:** Là `@Input Property<String>` hoặc `inputs.property(...)`.

### Bài 6. Output mặc định lab?

**Đáp án:** `build/generated/frontend`.

### Bài 7. Java resources directory?

**Đáp án:** `build/resources/main/public/` qua `processResources.from(...)`.

### Bài 8. Vì sao processResources biết chạy buildFrontend?

**Đáp án:** CopySpec lấy `buildFrontend.flatMap { it.destination }`; provider mang producer identity để Gradle suy ra dependency.

### Bài 9. Chạy Gradle clean run --quiet in gì?

**Đáp án:**

~~~text
FRONTEND_BUNDLE=OK
HTML_FOUND=true
BUNDLE_MODE=production
~~~

### Bài 10. Node script chạy độc lập?

**Đáp án:** `node frontend/build.mjs frontend/src manual-dist production` in `FRONTEND_BUNDLE=OK`.

### Bài 11. Java17 độc lập in gì?

**Đáp án:**

~~~text
JAVA17_STANDALONE=OK
~~~

khi dùng `javac --release 17` rồi `java -cp manual-java demo.frontend.StandaloneCheck`.

### Bài 12. Chạy lại không đổi source?

**Đáp án:** Task có thể `UP-TO-DATE` nếu outputs vẫn nguyên vẹn.

### Bài 13. Xóa output app.js?

**Đáp án:** Task cần chạy lại hoặc được restore nếu cacheable; lab sẽ chạy lại vì không cacheable mặc định.

### Bài 14. Thay mode production→development?

**Đáp án:** Task rerun do `@Input mode` đổi; `app.js` bắt đầu `// mode=development`.

### Bài 15. Tại sao không gắn @CacheableTask cho lab?

**Đáp án:** Node executable từ PATH và external environment chưa được pin/fingerprint đầy đủ.

### Bài 16. NpmTask cần gì?

**Đáp án:** `npmCommand`, install dependency, source/lock/config/mode inputs và output declaration.

### Bài 17. npm ci không có package-lock?

**Đáp án:** Fail; phải có matching committed lockfile.

### Bài 18. Đổi Vite config nhưng no rerun?

**Đáp án:** Có thể thiếu input, bổ sung `vite.config.ts` và transitive configs.

### Bài 19. pnpm lockfile tên gì?

**Đáp án:** Thường là `pnpm-lock.yaml`.

### Bài 20. Yarn Berry immutable option?

**Đáp án:** `yarn install --immutable`; Yarn Classic dùng flags khác.

### Bài 21. Build Cache khác npm cache?

**Đáp án:** Build Cache lưu Gradle task outputs; npm cache lưu downloaded packages/tarballs.

### Bài 22. Spring Boot static assets?

**Đáp án:** Đưa đúng classpath directory `static` hoặc `public` theo Boot conventions, kiểm `bootJar`.

### Bài 23. Multi-module output overlap?

**Đáp án:** Mỗi frontend task sở hữu output directory riêng, consumer merge có kiểm soát.

### Bài 24. --no-build-cache làm UP-TO-DATE tắt?

**Đáp án:** Không. Muốn buộc task action, dùng `--rerun-tasks`.

### Bài 25. Khi nào bật remote cache?

**Đáp án:** Sau khi pin toolchain/inputs, test deterministic outputs, relocation, OS/architecture và security, không có hidden network/env state.

## 18. Checklist review production

| Kiểm tra | Trạng thái mong muốn |
| --- | --- |
| Gradle/Java/Node versions | Pin bằng Wrapper/toolchain/CI setup |
| Input source | Toàn bộ relevant HTML/JS/TS/CSS/assets |
| Config inputs | Vite/Webpack/Babel/PostCSS/TS config |
| Package inputs | package.json + đúng lockfile/workspace metadata |
| Runtime inputs | Node/npm/pnpm/Yarn/plugin versions/OS nếu cần |
| Mode | Public env flags là `@Input`, không đưa secrets |
| Output directory | Một task sở hữu, nằm dưới build/ |
| Path sensitivity | RELATIVE nếu relative paths mang semantics |
| Task action | Exec hoặc injected ExecOperations, không project.exec |
| Task registration | tasks.register/TaskProvider |
| Producer wiring | flatMap output→consumer |
| Build Cache | Chỉ bật sau kiểm hermetic/deterministic |
| CI | Failed frontend task làm job fail, logs được lưu |
| Java packaging | processResources/JAR chứa đúng static assets |
| Incremental tests | No-change UP-TO-DATE, change relevant input rerun |
| Reproducibility | Clean workspaces và platforms đã được test |
| Security | Lockfile/registry trust, không lưu secrets/source maps tuỳ tiện |
| Multi-project | Không overlapping outputs, đúng ownership |
| Documentation | Biết lệnh chạy, output paths, troubleshooting |

**Kết luận:** Một frontend build được tích hợp tốt với Gradle phải có **input/output contract** rõ ràng, chứ không đơn thuần chạy npm command. Dùng `Exec` cho bài toán nhỏ, typed task + `ExecOperations` cho model mở rộng/test được, hoặc Node Gradle plugin để quản lý Node/npm/pnpm/Yarn. Khai source/config/lock/env/tool inputs, output directory do task sở hữu, dùng `TaskProvider.flatMap` nối vào `processResources`/`jar`, và chỉ bật Build Cache khi runtime/outputs thực sự deterministic. Khi đó Gradle có thể skip công việc thừa mà vẫn đóng gói frontend đúng trong Java application.

## 19. Nguồn tham khảo chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html) — inputs/outputs, path sensitivity, up-to-date checks và validation.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — typed tasks/annotations/TaskAction.
- [Gradle — Service Injection](https://docs.gradle.org/current/userguide/service_injection.html) — injected ExecOperations.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — register/named/TaskProvider.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html) — Provider.flatMap/implicit dependencies.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — @CacheableTask và cache policy.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — process/task action isolation.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — processResources/JAR.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — run/runtime classpath.
- [Gradle Plugin Portal — com.github.node-gradle.node](https://plugins.gradle.org/plugin/com.github.node-gradle.node) — verified plugin 7.1.0.
- [Node Gradle plugin — Usage](https://github.com/node-gradle/gradle-node-plugin/blob/main/docs/usage.md) — NodeTask/NpmTask/Node setup.
- [Node Gradle plugin — Kotlin example](https://github.com/node-gradle/gradle-node-plugin/blob/main/src/test/resources/fixtures/kotlin/build.gradle.kts) — property syntax.
- [Node Gradle plugin — FAQ](https://github.com/node-gradle/gradle-node-plugin/blob/main/docs/faq.md) — npm ci, centralized repositories, up-to-date.
- [npm CLI — npm ci](https://docs.npmjs.com/cli/v10/commands/npm-ci) — lockfile-based clean installs.
- [pnpm — install](https://pnpm.io/cli/install) — frozen lockfile and workspaces.
- [Yarn — install](https://yarnpkg.com/cli/install) — modern immutable install.
- [Vite — Build Options](https://vite.dev/config/build-options) — outDir/sourcemap/bundle output.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `--release 17`.

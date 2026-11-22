# Khai báo tác vụ build

Trong một hệ thống dùng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL) để xây dựng và triển khai phần mềm, **tác vụ build (build task)** là một đơn vị công việc có đầu vào, đầu ra, điều kiện thực thi và quan hệ phụ thuộc được mô tả rõ ràng. Ví dụ, một dự án có thể cần phân tích DSL, sinh mã nguồn, biên dịch, chạy kiểm thử, đóng gói và tạo tài liệu. Thay vì chạy các lệnh theo một chuỗi thủ công, build system quản lý những công việc này như một đồ thị tác vụ.

Khai báo tác vụ build mô tả cho hệ thống biết một tác vụ làm gì, cần dữ liệu nào, tạo ra sản phẩm nào và phải chạy sau những tác vụ nào. Build engine dùng các khai báo đó để lập kế hoạch, xác định thứ tự, bỏ qua công việc không cần thiết, chạy song song khi an toàn, lưu cache và báo lỗi ở đúng bước.

Một khai báo tốt cần có contract tường minh. Nếu đầu vào hoặc đầu ra không được khai báo đầy đủ, build engine có thể chạy sai thứ tự, dùng kết quả cũ, bỏ qua một thay đổi hoặc ghi đè sản phẩm của tác vụ khác. DSL xây dựng và triển khai cần giúp người viết mô tả công việc theo cách có thể phân tích, kiểm tra và thực thi lặp lại.

## 1. Tác vụ build là gì?

Một task là một đơn vị công việc có danh tính và hành vi xác định trong build graph. Tùy dự án, task có thể:

- Phân tích tệp DSL và tạo mô hình trung gian.
- Sinh Java source hoặc cấu hình runtime.
- Biên dịch mã nguồn.
- Chạy unit test hoặc integration test.
- Kiểm tra định dạng, schema hoặc chất lượng.
- Đóng gói JAR, container image hoặc deployment bundle.
- Tạo tài liệu và báo cáo.
- Triển khai artifact lên môi trường đích.
- Dọn output tạm hoặc thu thập metadata.

Ví dụ DSL giả định:

~~~text
task "generateSources" {
    input files("src/main/dsl/**/*.dsl")
    output directory("build/generated/sources")
    action {
        runDslGenerator()
    }
}

task "compile" {
    dependsOn "generateSources"
    input directory("src/main/java")
    input directory("build/generated/sources")
    output directory("build/classes")
    action {
        compileJava()
    }
}
~~~

Trong ví dụ, generateSources và compile là hai task khác nhau. Task thứ hai khai báo phụ thuộc vào task thứ nhất và sử dụng output do task trước tạo ra. Build engine có thể suy ra rằng generator phải hoàn thành trước khi compile bắt đầu.

Khai báo task không nhất thiết thực thi công việc ngay tại thời điểm parser đọc DSL. Nó thường tạo một mô tả có cấu trúc để build engine lập kế hoạch và chạy sau đó.

## 2. Task declaration và task execution

Cần phân biệt hai giai đoạn:

- **Task declaration/configuration:** định nghĩa task, thuộc tính, input, output, dependency và action.
- **Task execution:** thực hiện action khi build engine quyết định task cần chạy.

Ví dụ:

~~~text
task "package" {
    output file("build/app.jar")
    action {
        createPackage()
    }
}
~~~

Khi build file được đọc, engine đăng ký task package và ghi nhận output/action. Khi người dùng yêu cầu build package, engine mới lập kế hoạch và thực thi task nếu cần.

Sự tách biệt này giúp build system biết toàn bộ graph trước khi chạy, kiểm tra dependency, phát hiện chu trình và xác định task nào có thể chạy song song.

Nếu khai báo task đồng thời thực thi ngay mọi hành động I/O, engine khó tối ưu, khó cache và khó lập kế hoạch. DSL nên có semantics rõ về thời điểm đánh giá cấu hình và thời điểm thực thi action.

## 3. Cấu trúc của một khai báo task

Một task declaration thường có các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| ID/name | Tên duy nhất trong phạm vi build hoặc namespace |
| Description | Mục đích và thông tin trợ giúp |
| Type | Loại task hoặc contract chuyên biệt |
| Inputs | Tệp, thư mục, giá trị hoặc artifact được đọc |
| Outputs | Tệp, thư mục hoặc artifact được tạo |
| Dependencies | Task phải hoàn thành trước |
| Ordering constraints | Quan hệ thứ tự không nhất thiết truyền output |
| Options | Tham số và cấu hình |
| Action | Công việc thực tế |
| Conditions | Điều kiện có được thực thi |
| Cache policy | Có thể cache và điều kiện cache |
| Timeout/retry | Giới hạn thời gian và chính sách thử lại |
| Resource requirements | CPU, memory, worker hoặc lock cần dùng |

Một khai báo đầy đủ hơn:

~~~text
task "generateApi" {
    description "Generate API clients from service contracts"
    type "dsl.codegen"

    input files("contracts/**/*.api")
    input file("generator/config.yml")
    output directory("build/generated/api")

    dependsOn "validateContracts"

    option "language" = "java"
    option "packageName" = "com.example.api"

    cacheable true

    action {
        runGenerator(
            source = inputs.contracts,
            config = inputs.config,
            target = outputs.generatedApi
        )
    }
}
~~~

Tên thuộc tính và cú pháp cụ thể tùy DSL. Điều quan trọng là mỗi thành phần có ý nghĩa ổn định, có thể được type checker hoặc build engine xác minh.

## 4. Định danh và namespace của task

Tên task cần ổn định để người dùng có thể gọi từ CLI, task khác có thể tham chiếu và build report có thể nhận diện.

Ví dụ:

~~~text
task "compile"
task "test"
task "package"
task "deploy"
~~~

Trong build nhiều module, có thể dùng tên đầy đủ:

~~~text
task "api.generate"
task "api.compile"
task "web.bundle"
task "service.integrationTest"
~~~

Một số nguyên tắc:

- Không dùng tên phụ thuộc vào thứ tự khai báo.
- Không tái sử dụng một ID cho hai task khác nghĩa trong cùng namespace.
- Dùng namespace cho module, plugin hoặc convention.
- Đổi description không làm thay đổi task identity.
- Có quy tắc phân biệt chữ hoa/thường.
- Task do plugin cung cấp cần có namespace hoặc cơ chế tránh va chạm.

Tên hiển thị có thể thân thiện với người dùng, trong khi task ID dùng cho dependency và API. Hai khái niệm nên tách nếu hệ thống cần hỗ trợ localization hoặc đổi tên.

## 5. Task action

Action mô tả công việc task thực hiện khi chạy. Có thể là lời gọi hàm built-in, plugin action, script hoặc một chuỗi bước được định nghĩa trong DSL.

Ví dụ:

~~~text
task "validateDsl" {
    input files("src/main/dsl/**/*.dsl")
    action {
        for each source in inputs.sources {
            parse(source)
            validateTypes(source)
            validateDomainRules(source)
        }
    }
}
~~~

Một action nên có contract rõ:

- Dữ liệu đầu vào nào được đọc.
- Output nào được tạo hoặc cập nhật.
- Có side effect nào ngoài build workspace không.
- Có thể chạy lại an toàn không.
- Có thể chạy song song với task khác không.
- Có thể hủy giữa chừng không.
- Lỗi được biểu diễn như thế nào.

Action nên nhận input/output thông qua context do build engine cung cấp. Truy cập trực tiếp một đường dẫn ngầm hoặc đọc biến môi trường tùy tiện khiến engine khó xác định đầy đủ dependency.

## 6. Khai báo input

Input là mọi dữ liệu có thể ảnh hưởng đến kết quả task. Các loại thường gặp:

- File hoặc tập file.
- Thư mục.
- Giá trị cấu hình.
- Phiên bản tool.
- Dependency artifact.
- Environment value được cho phép.
- Source set hoặc model snapshot.
- Nội dung từ task upstream.

Ví dụ:

~~~text
task "compile" {
    input files("src/main/java/**/*.java")
    input directory("build/generated/sources")
    input value("javaRelease", 21)
    input value("compilerOptions", ["-Xlint:all"])
}
~~~

Khai báo input giúp engine biết khi nào kết quả có thể đã lỗi thời. Nếu compile đọc một file config nhưng file đó không được khai báo là input, thay đổi config có thể không làm task chạy lại.

### 6.1. Input file và file collection

Một file input có thể là đường dẫn đơn. File collection mô tả một tập file được chọn theo pattern hoặc từ source set.

Cần xác định:

- Pattern dùng glob hay regex.
- Có bao gồm file ẩn không.
- Thứ tự file có ổn định không.
- Symbolic link được xử lý ra sao.
- File không tồn tại là lỗi hay tập rỗng.
- File mới được tạo có làm input set thay đổi không.

Nếu thứ tự file ảnh hưởng kết quả, cần sắp xếp theo quy tắc xác định thay vì phụ thuộc thứ tự filesystem trả về.

### 6.2. Input value

Input không phải file cũng cần được khai báo. Ví dụ compiler release, locale, feature flag hoặc target platform có thể ảnh hưởng output.

~~~text
input value("target", "linux-x64")
input value("optimization", "release")
input value("schemaVersion", 4)
~~~

Các giá trị nên có kiểu rõ ràng. Tránh chuyển mọi option thành chuỗi nếu build engine cần phân biệt boolean, number, path và enum.

### 6.3. Input environment

Environment variable có thể ảnh hưởng build nhưng thường khó tái lập. Nếu cần dùng, khai báo chính xác tên biến và cách xử lý khi thiếu:

~~~text
input environment("BUILD_REGION", required = true)
input environment("SOURCE_DATE_EPOCH", required = false)
~~~

Không nên đưa secret trực tiếp vào cache key hoặc log. Nếu một secret chỉ xác thực quyền truy cập nhưng không ảnh hưởng nội dung output, cần phân biệt nó với input nội dung để tránh lộ dữ liệu nhạy cảm.

## 7. Khai báo output

Output là sản phẩm mà task chịu trách nhiệm tạo. Ví dụ:

- File generated source.
- Thư mục classes.
- Resource bundle.
- Test report.
- Package archive.
- Metadata hoặc manifest.
- Container image reference.

Ví dụ:

~~~text
task "compile" {
    input files("src/main/java/**/*.java")
    output directory("build/classes")
    action {
        invokeCompiler()
    }
}
~~~

Output declaration cho build engine biết task sở hữu vùng dữ liệu nào và task downstream có thể tiêu thụ kết quả ở đâu.

Cần bảo đảm action thực sự tạo output đã khai báo. Nếu task báo thành công nhưng output thiếu hoặc không hợp lệ, task downstream có thể thất bại khó hiểu.

### 7.1. Một hay nhiều output

Task có thể tạo nhiều output:

~~~text
task "generate" {
    output directory("build/generated/java")
    output directory("build/generated/resources")
    output file("build/metadata/generator-report.json")
    action {
        generateAll()
    }
}
~~~

Mỗi output cần được quản lý rõ. Nếu một output chỉ được tạo trong một số điều kiện, build engine cần biết output optional hay bắt buộc.

### 7.2. Output ownership

Một output path nên có một task owner rõ ràng. Hai task cùng ghi vào một thư mục có thể gây race condition hoặc xóa nhầm kết quả của nhau.

Nếu nhiều task cần đóng góp vào cùng một artifact, có thể dùng task tổng hợp, staging riêng rồi merge bằng một task duy nhất hoặc output partition theo namespace.

### 7.3. Không khai báo output không được tạo

Nếu task khai báo thư mục output nhưng action không ghi gì, engine có thể liên tục xem task là chưa hoàn tất hoặc downstream nhận thư mục rỗng. Có thể khai báo output optional, hoặc task cần tạo một manifest rỗng hợp lệ nếu semantics yêu cầu.

## 8. Input và output là contract, không chỉ là đường dẫn

Input/output declaration là một phần của contract giữa task và build engine. Nó cho phép engine:

- Xác định task có thể được bỏ qua hay cần chạy.
- Tính fingerprint.
- Tạo cache key.
- Xác định task downstream phụ thuộc dữ liệu nào.
- Kiểm soát task chạy song song.
- Kiểm tra output ownership.
- Lập kế hoạch cleanup và phục hồi.

Một task có thể đọc thêm dữ liệu ngầm mà không khai báo. Khi đó, build engine không thể bảo đảm incremental correctness. Ví dụ task đọc tất cả file trong thư mục home nhưng chỉ khai báo một config trong project. Kết quả có thể thay đổi mà engine không biết.

## 9. Quan hệ dependency giữa các task

Dependency cho biết task nào phải hoàn thành trước task khác. Ví dụ compile phụ thuộc generate source, test phụ thuộc compile, package phụ thuộc test hoặc compile.

~~~text
task "generate" { ... }

task "compile" {
    dependsOn "generate"
    ...
}

task "test" {
    dependsOn "compile"
    ...
}

task "package" {
    dependsOn "test"
    ...
}
~~~

Build engine tạo đồ thị có hướng. Một cạnh A -> B nghĩa là B cần A hoàn thành trước khi chạy.

~~~mermaid
flowchart TD
    A[generate] --> B[compile]
    B --> C[test]
    C --> D[package]
    D --> E[deploy]
~~~

Khi người dùng yêu cầu package, engine có thể lần ngược dependency để xác định các task cần chạy.

### 9.1. Dependency bắc cầu

Nếu package phụ thuộc test, test phụ thuộc compile và compile phụ thuộc generate, package gián tiếp phụ thuộc generate. Engine thường tự tính dependency bắc cầu.

Không cần khai báo lặp tất cả dependency nếu graph đã thể hiện đúng quan hệ. Tuy nhiên, khai báo trực tiếp có thể cần thiết nếu task thực sự tiêu thụ output hoặc contract của một task khác mà không đi qua đường dependency hiện có.

### 9.2. Phụ thuộc output

Dependency nên phản ánh quan hệ dữ liệu. Nếu task B đọc output của task A, B phải phụ thuộc A. Cách tốt nhất là tham chiếu output provider của A thay vì chỉ ghi một đường dẫn chuỗi:

~~~text
task "compile" {
    input from task("generate").output("sources")
}
~~~

Cơ chế provider giúp engine liên kết task producer và consumer, biết đường dẫn output chỉ sau khi cấu hình hoàn tất và tránh hard-code.

## 10. Dependency và ordering constraint

Không phải mọi quan hệ thứ tự đều là dependency dữ liệu.

- **dependsOn:** task cần task khác hoàn thành trước và thường tiêu thụ kết quả của nó.
- **mustRunAfter:** nếu cả hai task cùng được chọn, task này phải chạy sau task kia; không nhất thiết kéo task kia vào graph.
- **shouldRunAfter:** gợi ý thứ tự nếu có thể, nhưng không phải ràng buộc cứng.
- **finalizedBy/finalizer:** task dọn dẹp hoặc thu thập kết quả được chạy sau task khác theo policy.

Ví dụ:

~~~text
task "integrationTest" {
    dependsOn "startTestEnvironment"
    finalizedBy "stopTestEnvironment"
}

task "report" {
    mustRunAfter "test"
}
~~~

report chỉ cần chạy sau test nếu cả hai được chọn. mustRunAfter không tự động có nghĩa report kéo test vào build.

Cần tránh dùng ordering constraint thay cho dependency dữ liệu. Nếu task đọc output của task khác, chỉ đặt thứ tự chạy là chưa đủ để mô tả contract.

## 11. Phát hiện chu trình dependency

Build graph thông thường cần là DAG (Directed Acyclic Graph). Chu trình khiến engine không thể tìm được thứ tự thực thi hợp lệ.

Ví dụ lỗi:

~~~text
task "compile" {
    dependsOn "generate"
}

task "generate" {
    dependsOn "compile"
}
~~~

Chu trình:

~~~mermaid
flowchart LR
    A[compile] --> B[generate]
    B --> A
~~~

Engine nên phát hiện cycle trước khi thực thi và báo đường đi gây chu trình. Thông báo hữu ích có thể là:

~~~text
Circular task dependency:
compile -> generate -> compile
~~~

Không nên để build treo hoặc đợi vô hạn vì dependency cycle. Với một số workflow phức tạp có thể có vòng lặp nghiệp vụ, nhưng cần mô hình riêng như iterative task hoặc pipeline có giới hạn, không biểu diễn bằng dependency cycle thông thường.

## 12. Cấu hình task bằng tham số

Task có thể nhận options để thay đổi hành vi mà không phải định nghĩa task mới cho mỗi trường hợp.

~~~text
task "compile" {
    option "release" type Integer default 21
    option "warningsAsErrors" type Boolean default false
    option "target" type TargetPlatform default "current"

    action {
        compile(
            release = options.release,
            warningsAsErrors = options.warningsAsErrors,
            target = options.target
        )
    }
}
~~~

Một option tốt cần:

- Có kiểu dữ liệu.
- Có default rõ ràng nếu được phép.
- Có validation.
- Được đưa vào fingerprint nếu ảnh hưởng output.
- Có giá trị hiển thị trong task report.
- Không chứa secret không cần thiết.

Nếu một option ảnh hưởng output nhưng không nằm trong cache key, cache có thể trả sản phẩm tạo bằng cấu hình khác.

## 13. Task type và convention

Build DSL có thể hỗ trợ task type để tái sử dụng cấu trúc input/output và action.

Ví dụ:

~~~text
taskType "JavaCompile" {
    input sourceFiles: FileCollection
    input classpath: FileCollection
    input release: Integer
    output classes: Directory

    action {
        invokeJavaCompiler(
            sourceFiles,
            classpath,
            release,
            classes
        )
    }
}

task "compileMain" of "JavaCompile" {
    sourceFiles = files("src/main/java/**/*.java")
    classpath = configurations.mainCompile
    release = 21
    classes = directory("build/classes/main")
}
~~~

Task type giúp chuẩn hóa cách khai báo, tái sử dụng validation, tích hợp plugin, hiển thị task metadata nhất quán và hỗ trợ tool-specific optimization.

Convention là giá trị mặc định có thể được override theo project hoặc task. Cần xác định precedence giữa global convention, module convention, task default và command-line option.

## 14. Task registration và task realization

Ở build lớn, số lượng task có thể rất nhiều. Nếu tạo object và cấu hình action cho mọi task ngay khi đọc build file, thời gian configuration có thể cao.

Một build DSL có thể phân biệt:

- **Registration:** đăng ký task provider và metadata cơ bản.
- **Realization:** tạo/cấu hình task object khi thực sự cần.
- **Execution:** chạy action.

Ví dụ khái niệm:

~~~text
register task "compileTest" of "JavaCompile" {
    sourceFiles = files("src/test/java/**/*.java")
    classes = directory("build/classes/test")
}
~~~

Provider cho phép tham chiếu output hoặc property của task mà chưa cần tạo toàn bộ task ngay lập tức. Điều này giúp lazy configuration và giảm chi phí khi người dùng chỉ chạy một phần build.

Cần tránh truy cập property buộc realization quá sớm nếu task không nằm trong graph cần chạy.

## 15. Configuration phase và execution phase

Build system thường có hai giai đoạn chính:

1. **Configuration phase:** đọc build model, tạo task graph, giải quyết cấu hình và kiểm tra quan hệ.
2. **Execution phase:** thực thi các task đã chọn theo graph.

Một số hệ thống còn có initialization phase để xác định project, module và settings.

~~~mermaid
flowchart TD
    A[Start build] --> B[Initialization]
    B --> C[Configuration]
    C --> D[Task graph ready]
    D --> E[Execution]
    E --> F[Build result]
~~~

Không nên thực hiện I/O nặng hoặc chạy compiler trong configuration phase nếu công việc đó thuộc task action. Làm vậy khiến mọi lệnh build đều trả chi phí dù task không được yêu cầu.

Configuration phase nên tập trung mô tả graph và thiết lập property. Execution phase mới thực hiện công việc có side effect.

## 16. Điều kiện thực thi và task selection

Một task có thể chỉ chạy trong một số trường hợp:

~~~text
task "publishDocs" {
    onlyIf {
        options.publishDocumentation == true
    }
    action {
        publishDocumentation()
    }
}
~~~

Có thể có các cơ chế:

- Task được chọn trực tiếp từ CLI.
- Task được kéo vào graph bởi dependency.
- Điều kiện runtime.
- Platform hoặc environment condition.
- Task chỉ chạy khi output chưa tồn tại hoặc input thay đổi.
- Task chỉ chạy trong profile cụ thể.

Cần phân biệt task không được chọn với task được chọn nhưng bị skip do condition. Build report nên thể hiện lý do skip.

Điều kiện cần deterministic và có dependency rõ. Nếu condition đọc file hoặc environment value, dữ liệu đó nên được khai báo để engine biết khi nào cần đánh giá lại.

## 17. Task up-to-date và incremental execution

Build engine có thể bỏ qua task nếu input/output không thay đổi so với lần chạy trước. Đây là cơ chế up-to-date checking.

Một task có thể được xem là up-to-date khi:

- Tập input giống lần trước.
- Nội dung input không thay đổi.
- Options và tool version không đổi.
- Dependency output không đổi.
- Output hiện tại còn tồn tại và hợp lệ.
- Không có lý do buộc chạy lại.

Ví dụ:

~~~text
task "generateApi" {
    input files("contracts/**/*.api")
    input file("generator/config.yml")
    output directory("build/generated/api")
    cacheable true
    action {
        generateApiClients()
    }
}
~~~

Nếu contract hoặc config đổi, task cần chạy lại. Nếu không đổi và output còn nguyên, engine có thể báo UP-TO-DATE.

Up-to-date checking không giống build cache. Up-to-date nghĩa output tại workspace hiện tại được xem là hợp lệ. Cache có thể khôi phục output từ một lần build khác nếu fingerprint khớp.

## 18. Build cache và cache key

Build cache lưu output của task để tái sử dụng. Một cache key nên phụ thuộc mọi yếu tố ảnh hưởng kết quả:

- Task implementation hoặc action version.
- Input file content.
- Input value/options.
- Generator/compiler version.
- Platform hoặc target.
- Dependency artifacts.
- Environment values đã khai báo.
- Output-affecting configuration.

Có thể mô tả:

~~~text
cacheKey = hash(
    taskImplementation
    + inputFingerprints
    + declaredOptions
    + toolchainVersion
    + dependencyFingerprints
)
~~~

Nếu cache key thiếu một input, engine có thể trả output sai. Nếu cache key chứa dữ liệu không ổn định như absolute path hoặc timestamp không cần thiết, cache hit rate có thể giảm.

Cacheable task nên có tính xác định: cùng input và cấu hình phải tạo cùng output theo contract. Nếu action đọc thời gian hiện tại hoặc random seed, cần inject giá trị đó làm input hoặc không cache task.

## 19. Deterministic và reproducible task

Build reproducible nghĩa là cùng source, toolchain và cấu hình tạo ra output có thể tái lập. Một task có thể không reproducible nếu phụ thuộc vào:

- Timestamp hiện tại.
- Thứ tự filesystem không ổn định.
- Locale hoặc timezone máy.
- Absolute path của workspace.
- Environment variable không khai báo.
- Random value.
- Network resource thay đổi.
- Dependency version không pin.
- Compiler/tool version không cố định.

Biện pháp:

- Chuẩn hóa thứ tự đầu vào.
- Pin dependency và toolchain.
- Dùng encoding/newline cố định.
- Inject clock hoặc epoch cố định nếu cần.
- Tránh absolute path trong output metadata.
- Khai báo environment inputs.
- Lưu checksum và provenance.
- Không tải dependency động không có version constraint.

Một task chỉ nên cacheable khi build engine có thể xác định đầy đủ điều kiện ảnh hưởng output.

## 20. Parallel execution và resource constraints

Nếu hai task không phụ thuộc nhau và không tranh chấp tài nguyên/output, engine có thể chạy song song.

Ví dụ:

~~~mermaid
flowchart TD
    A[generateSources] --> C[compile]
    B[generateDocs] --> D[packageDocs]
    C --> E[package]
    D --> E
~~~

generateSources và generateDocs có thể chạy đồng thời. compile chờ source generation; packageDocs chờ docs generation; task package cuối chờ cả hai nhánh.

Task cần khai báo hoặc tôn trọng resource constraints:

- CPU workers.
- Memory.
- Exclusive file lock.
- Port hoặc server instance.
- GPU hoặc thiết bị đặc biệt.
- External service rate limit.
- Shared output directory.

Nếu hai task ghi cùng một output, parallel execution có thể gây race. Output ownership và dependency graph phải thể hiện xung đột.

### 20.1. Worker limits

Build engine có thể giới hạn số worker đồng thời. Task nặng memory có thể yêu cầu resource reservation hoặc chạy trong worker riêng.

### 20.2. Exclusive resource

Một task chạy database migration có thể cần lock để không có hai tiến trình cùng cập nhật schema. DSL có thể cung cấp resource declaration:

~~~text
task "migrateDatabase" {
    uses exclusive("database-schema")
    action {
        runMigrations()
    }
}
~~~

Resource lock giúp engine điều phối các task trong cùng build. Nếu nhiều build process cùng tác động một hệ thống ngoài, cần lock phân tán hoặc cơ chế idempotency ở hệ thống đích.

## 21. Task finalizer và cleanup

Một số tác vụ cần cleanup dù task chính thành công hay thất bại. Ví dụ start test server rồi chạy integration test, sau đó dừng server.

~~~text
task "integrationTest" {
    dependsOn "startTestServer"
    finalizedBy "stopTestServer"
    action {
        runIntegrationTests()
    }
}
~~~

Finalizer cần được chạy theo semantics đã định, kể cả khi task chính thất bại hoặc bị hủy trong phạm vi có thể. Build engine nên báo lỗi cleanup riêng để người dùng biết môi trường có thể còn tài nguyên đang chạy.

Cleanup task không nên xóa output thuộc task khác. Nó cần biết ownership và chỉ thao tác trên resource đã được tạo hoặc cấp cho nó.

## 22. Task failure và propagation

Một task có thể thất bại do lỗi cú pháp, compiler, test, I/O, dependency hoặc external service.

Khi task A thất bại, task phụ thuộc B thường không được chạy vì input của B có thể chưa tồn tại hoặc không hợp lệ. Các nhánh độc lập có thể tiếp tục tùy failure policy.

Ví dụ:

~~~mermaid
flowchart TD
    A[compile] --> B[test]
    A --> C[generateDocs]
    B --> D[package]
    C --> D
    A --> E[notifyFailure]
~~~

Nếu compile lỗi, test và package thường bị skip; generateDocs có thể vẫn chạy nếu không phụ thuộc compile. Một task báo cáo lỗi có thể chạy sau failure theo policy.

Build report cần phân biệt:

- SUCCESS: hoàn tất.
- FAILED: action lỗi.
- SKIPPED: không được chạy hoặc dependency thất bại.
- UP-TO-DATE: output hợp lệ, không cần thực thi.
- FROM-CACHE: output được khôi phục từ cache.
- NO-SOURCE: không có input source phù hợp.
- CANCELLED: bị hủy.

## 23. Retry và idempotency

Task gọi external service hoặc tải tài nguyên có thể thất bại tạm thời. Retry có thể hữu ích nhưng chỉ an toàn nếu action có semantics phù hợp.

Ví dụ:

~~~text
task "uploadArtifact" {
    retry maxAttempts = 3
    backoff exponential(initial = 1s, max = 10s)
    action {
        upload(packageFile)
    }
}
~~~

Cần phân biệt lỗi tạm thời với lỗi vĩnh viễn. Retry lỗi cú pháp hoặc permission thường không giúp ích.

Task có side effect cần idempotent hoặc dùng idempotency key. Nếu lần upload đầu thành công ở server nhưng kết nối bị ngắt trước khi client nhận response, retry có thể tạo artifact trùng nếu server không hỗ trợ deduplication.

Không nên retry mù mọi lỗi. Chính sách cần quy định loại lỗi, số lần thử, backoff, jitter và thời gian tổng.

## 24. Task timeout và cancellation

Một task có thể chạy quá lâu do compiler treo, test không kết thúc hoặc network request bị kẹt. Timeout giúp giới hạn thời gian:

~~~text
task "integrationTest" {
    timeout 15m
    action {
        runIntegrationTests()
    }
}
~~~

Cancellation có thể xuất phát từ người dùng, CI timeout hoặc task dependency bị hủy. Action nên hỗ trợ cancellation hợp tác, đóng stream, giải phóng lock và dừng process con khi có thể.

Hủy một task không đảm bảo side effect bên ngoài đã được hoàn tác. Nếu task đang triển khai lên cloud, cần có quy trình kiểm tra trạng thái và bù trừ riêng.

## 25. Task graph nhiều module

Dự án lớn thường có nhiều module:

~~~text
root
  api
  domain
  service
  web
  deployment
~~~

Task có thể phụ thuộc giữa các module:

~~~text
task "service.compile" {
    dependsOn "domain.compile"
    dependsOn "api.compile"
}

task "web.bundle" {
    dependsOn "service.package"
}

task "deployment.image" {
    dependsOn "web.bundle"
}
~~~

Build DSL cần xác định namespace task, project path và cách tham chiếu task xuyên module. Tránh tên ngắn mơ hồ nếu nhiều module có task cùng tên.

Một task ở module consumer có thể tiêu thụ artifact output từ producer module. Dùng project dependency hoặc artifact provider giúp build engine xác định đúng version và variant.

## 26. Variant và build profile

Một project có thể tạo nhiều biến thể output:

- Debug và release.
- Development và production.
- Linux, Windows và macOS.
- Java 17 và Java 21.
- Community và enterprise edition.
- Các region hoặc deployment target khác nhau.

Có thể biểu diễn variant:

~~~text
task "package" {
    variant "release-linux" {
        input value("optimization", "full")
        input value("target", "linux-x64")
        output file("build/dist/app-linux.tar")
    }
}
~~~

Mỗi variant cần có input/output identity riêng để cache không dùng nhầm artifact giữa các target. Nếu hai variant ghi cùng một output path, cần phân biệt rõ hoặc không cho chạy đồng thời.

Build profile có thể cung cấp convention cho một nhóm task, nhưng precedence giữa profile, command-line option và task option cần được định nghĩa.

## 27. Dynamic task và task discovery

Một số task được tạo từ danh sách module, schema hoặc test suite. Ví dụ mỗi DSL file tạo một task validate riêng.

~~~text
for each contract in contracts {
    register task "validate-" + contract.name {
        input file(contract.path)
        action {
            validateContract(contract)
        }
    }
}
~~~

Dynamic task hữu ích nhưng cần tránh phụ thuộc vào dữ liệu runtime quá muộn. Task graph cần được xác định đủ sớm để engine lập kế hoạch. Nếu danh sách task được khám phá từ network trong execution phase, build có thể khó cache và khó dự đoán.

Tên task động cần được chuẩn hóa và phát hiện collision. Khi đầu vào thay đổi làm một task không còn được đăng ký, build system cần xử lý output cũ của task đó theo ownership.

## 28. Task graph và artifact provider

Task thường không nên truyền dữ liệu bằng cách ghi đường dẫn chuỗi tùy ý. Một artifact provider thể hiện producer, output type và cách consumer nhận giá trị.

Ví dụ:

~~~text
task "generateSchema" {
    output schemaFile = file("build/schema/order.json")
}

task "validateExamples" {
    input schema = outputOf("generateSchema", "schemaFile")
    input files("examples/**/*.json")
    action {
        validateExamples(schema, inputs.examples)
    }
}
~~~

Provider có thể trì hoãn việc resolve path đến khi build engine cần, đồng thời tạo dependency ngầm từ consumer đến producer.

Typed artifact giúp tránh nhầm file schema với file report hoặc package. Có thể khai báo artifact type như JavaSources, SchemaDocument, ContainerImage hoặc TestReport.

## 29. Build task và triển khai (deployment)

Deployment thường là task có side effect trên môi trường ngoài. Ví dụ:

~~~text
task "deployStaging" {
    dependsOn "package"
    input artifact from task("package")
    option "environment" = "staging"
    uses exclusive("staging-deployment")
    action {
        deploy(
            artifact = inputs.artifact,
            environment = options.environment
        )
    }
}
~~~

Một task deployment cần xác định:

- Artifact nào được triển khai.
- Môi trường đích.
- Credential lấy từ secret provider nào.
- Có yêu cầu approval không.
- Có dry-run/plan mode không.
- Có thể retry an toàn không.
- Có health check sau deploy không.
- Rollback hoặc compensating action là gì.
- Audit event nào được ghi.

Không nên coi deployment task giống một task compile thuần. Nó có thể tác động đến hệ thống đang chạy và cần policy riêng về quyền, xác nhận, concurrency và rollback.

## 30. Task dry-run và plan

Plan mode hiển thị công việc sẽ được thực hiện mà không thực hiện side effect. Nó hữu ích cho deployment, migration hoặc cleanup.

Ví dụ:

~~~text
task "deployProduction" {
    plan {
        showArtifact()
        showTarget()
        showChanges()
    }
    action {
        deployToProduction()
    }
}
~~~

Dry-run cần phản ánh chính xác kế hoạch thực tế. Nếu plan và action dùng hai logic khác nhau, preview có thể gây hiểu lầm. Một cách tốt là tạo immutable execution plan trước; cả preview và execution đều dựa trên plan đó.

Dry-run không nên ghi output chính thức hoặc thay đổi registry trừ khi những thay đổi đó là phần được định nghĩa rõ của việc lập kế hoạch.

## 31. Logging, progress và build report

Task nên phát ra log có cấu trúc và progress event:

- Task ID.
- Trạng thái.
- Thời điểm bắt đầu/kết thúc.
- Thời gian chạy.
- Input/output summary.
- Cache result.
- Warning/error.
- Worker hoặc process.
- Dependency và retry count.

Ví dụ:

~~~text
> Task :generateSources
> Task :compile
> Task :test
> Task :package

BUILD SUCCESSFUL
4 tasks executed, 2 up-to-date, 1 from cache
~~~

Không nên log secret, token hoặc nội dung file nhạy cảm. Với task chạy song song, log nên có task identity để người dùng phân biệt thông điệp xen kẽ.

Build report có thể hỗ trợ tìm task chậm, cache miss và dependency graph. Thông tin này giúp tối ưu build dựa trên dữ liệu thực.

## 32. Bảo mật khi khai báo và chạy task

Build task có thể đọc file, chạy process, truy cập network và ghi dữ liệu. Build script vì thế là mã có quyền đáng kể.

Các rủi ro:

- Task đọc hoặc ghi ngoài workspace.
- Command injection qua option từ DSL.
- Dependency tải về bị thay thế.
- Plugin không đáng tin cậy.
- Secret bị đưa vào log hoặc cache.
- Task chạy process con không giới hạn.
- Hai task cùng ghi output gây corruption.
- Deployment nhầm environment.
- Task cleanup xóa file do người dùng quản lý.

Biện pháp:

- Dùng typed API thay vì ghép chuỗi shell tùy tiện.
- Giới hạn file access theo workspace hoặc capability.
- Pin dependency và xác minh checksum/signature khi phù hợp.
- Quản lý secret qua provider riêng.
- Không cache secret hoặc output chứa credential.
- Kiểm soát process, timeout và memory.
- Xác định output ownership.
- Phân quyền deployment và yêu cầu approval cho môi trường nhạy cảm.
- Ghi audit cho side effect quan trọng.

Một task chỉ nên nhận capability cần thiết. Task biên dịch có thể không cần quyền deploy hoặc truy cập production secret.

## 33. Kiểm thử task declaration

Build DSL cần kiểm tra cả cấu trúc khai báo và hành vi task.

### 33.1. Kiểm thử cấu trúc

- Task ID duy nhất.
- Dependency tham chiếu đến task tồn tại.
- Không có cycle.
- Input/output có kiểu hợp lệ.
- Output ownership không xung đột.
- Required option có giá trị.
- Task type được đăng ký.

### 33.2. Kiểm thử graph

- Task chạy theo dependency order.
- Task độc lập có thể chạy song song.
- Ordering constraint không vô tình kéo task vào graph.
- Failure propagation đúng.
- Finalizer được gọi theo policy.

### 33.3. Kiểm thử incremental và cache

- Thay đổi input làm task chạy lại.
- Thay đổi option ảnh hưởng output làm cache key đổi.
- Input không đổi cho kết quả up-to-date.
- Cache hit khôi phục đúng output.
- Tool version thay đổi làm invalidation khi cần.
- Output bị xóa hoặc hỏng khiến task được chạy lại.

### 33.4. Kiểm thử action và lỗi

- Action tạo đủ output.
- Lỗi được gắn với đúng task.
- Timeout và cancellation giải phóng tài nguyên.
- Retry không tạo side effect trùng.
- Cleanup không xóa output không thuộc task.

### 33.5. Kiểm thử reproducibility và security

- Cùng input tạo output xác định.
- Không phụ thuộc thứ tự filesystem hoặc locale ngầm.
- Không truy cập file ngoài phạm vi được cấp.
- Secret không xuất hiện trong log/cache.
- Deployment task tuân thủ approval và environment policy.

## 34. Ví dụ build graph hoàn chỉnh

Giả sử một ứng dụng được mô tả bằng DSL. Build cần validate DSL, sinh Java và resource, compile, test, đóng gói rồi triển khai staging.

~~~text
task "validateDsl" {
    input files("src/main/dsl/**/*.dsl")
    action {
        validateAllDslSources()
    }
}

task "generate" {
    dependsOn "validateDsl"
    input files("src/main/dsl/**/*.dsl")
    input file("generator/config.yml")
    output directory("build/generated")
    action {
        generateSourcesAndResources()
    }
}

task "compile" {
    dependsOn "generate"
    input directory("src/main/java")
    input directory("build/generated/java")
    output directory("build/classes")
    action {
        compileApplication()
    }
}

task "test" {
    dependsOn "compile"
    input directory("build/classes")
    input files("src/test/**/*.java")
    output directory("build/reports/tests")
    action {
        runTests()
    }
}

task "package" {
    dependsOn "test"
    input directory("build/classes")
    input directory("build/generated/resources")
    output file("build/distributions/app.jar")
    action {
        createJar()
    }
}

task "deployStaging" {
    dependsOn "package"
    input file("build/distributions/app.jar")
    uses exclusive("staging-environment")
    action {
        deployToStaging()
    }
}
~~~

Đồ thị:

~~~mermaid
flowchart TD
    A[validateDsl] --> B[generate]
    B --> C[compile]
    C --> D[test]
    D --> E[package]
    E --> F[deployStaging]
~~~

Khi yêu cầu package, task deploy không cần chạy vì nó không phải dependency của package. Khi yêu cầu deployStaging, engine chạy các task upstream cần thiết. Nếu input không đổi và output hợp lệ, một số task có thể được đánh dấu up-to-date hoặc khôi phục từ cache.

## 35. Quy trình thiết kế khai báo task

Có thể thiết kế task theo trình tự:

1. **Xác định trách nhiệm:** một task nên có mục đích cụ thể, có thể mô tả ngắn gọn.
2. **Định danh:** chọn task ID ổn định trong namespace phù hợp.
3. **Chọn task type:** dùng type/convention nếu có contract chung.
4. **Khai báo input:** liệt kê toàn bộ dữ liệu ảnh hưởng kết quả.
5. **Khai báo output:** xác định sản phẩm và owner của từng output path.
6. **Khai báo dependency:** thể hiện quan hệ dữ liệu giữa task.
7. **Thiết lập options:** dùng kiểu dữ liệu và default rõ.
8. **Viết action:** nhận input/output từ task context, tránh truy cập ngầm.
9. **Chọn cache policy:** chỉ cache khi task xác định và khai báo đủ input.
10. **Chọn execution policy:** resource, parallelism, timeout, retry và cancellation.
11. **Kiểm tra graph:** dependency tồn tại, không cycle và không xung đột output.
12. **Kiểm thử:** up-to-date, cache, failure, reproducibility và side effect.

## 36. Nguyên tắc thiết kế

- **Một task, một trách nhiệm rõ:** task nhỏ dễ cache, kiểm thử và tái sử dụng.
- **Khai báo đầy đủ input:** mọi dữ liệu ảnh hưởng output cần nằm trong contract.
- **Khai báo output và ownership:** tránh task ghi đè hoặc xóa sản phẩm của nhau.
- **Dùng dependency cho quan hệ dữ liệu:** ordering constraint chỉ dùng khi thật sự cần thứ tự.
- **Giữ graph không chu trình:** phát hiện cycle trước khi thực thi.
- **Tách configuration và execution:** build model được lập kế hoạch trước khi action chạy.
- **Dùng typed options và artifact provider:** giảm lỗi đường dẫn và kiểu dữ liệu.
- **Cache chỉ task xác định:** fingerprint phải bao gồm mọi yếu tố ảnh hưởng kết quả.
- **Chạy song song khi an toàn:** quản lý resource và output conflict rõ ràng.
- **Thiết kế failure, retry và cancellation:** tránh side effect trùng hoặc tài nguyên bị bỏ lại.
- **Tách build thuần khỏi deployment:** task tác động môi trường cần quyền và audit riêng.
- **Bảo vệ workspace và secret:** giới hạn capability, process và file access.
- **Báo cáo trạng thái có ý nghĩa:** phân biệt executed, up-to-date, cached, skipped và failed.
- **Kiểm thử graph lẫn action:** một task chạy được riêng lẻ chưa bảo đảm build tổng thể đúng.
- **Ưu tiên reproducibility:** cùng input, toolchain và cấu hình cần tạo output có thể tái lập.

Khai báo tác vụ build là cách mô tả công việc của dự án thành một đồ thị có thể phân tích và thực thi. Khi task có identity, input/output contract, dependency, action và execution policy rõ ràng, build engine có thể lập kế hoạch chính xác, tận dụng incremental build và cache, chạy song song an toàn, đồng thời báo lỗi và phục hồi có kiểm soát.

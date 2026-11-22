# Kiểm soát đầu vào, phụ thuộc và công cụ chạy trong giai đoạn biên dịch

Trong một nền tảng Java có khả năng mở rộng lúc chạy, host có thể nhận mã nguồn plugin, lấy thư viện phụ thuộc, chạy trình biên dịch Java và tạo bytecode để nạp sau đó. Mọi bước ấy đều nằm trên **ranh giới tin cậy**: nội dung do người dùng hoặc plugin gửi lên chưa mặc nhiên được tin, thư viện tải về có nguồn gốc và quyền hạn khác với mã host, còn compiler/annotation processor/build plugin có thể chạy với quyền của tiến trình thực hiện build.

Sai lầm thường gặp là nghĩ rằng **chưa chạy file .class thì giai đoạn biên dịch chắc chắn an toàn**. Điều đó không đúng. Việc javac chỉ phân tích một Java source thông thường không tự động chạy static initializer của lớp nguồn, nhưng **annotation processors, javac plugins, build scripts, build-tool plugins, code generators và các công cụ phụ trợ** có thể thực thi mã ngay trong lúc biên dịch. Đồng thời, dù không có công cụ mở rộng, một input lớn hoặc độc hại vẫn có thể chiếm CPU, RAM, đĩa, kéo dài thời gian biên dịch hoặc kích hoạt lỗi công cụ.

Mục tiêu của bài học là phân biệt **những gì được biên dịch** với **những gì được thực thi trong quá trình biên dịch**, rồi thiết kế quy trình kiểm soát **đầu vào → phụ thuộc → toolchain → tác vụ biên dịch → artifact**. Phần thực hành dùng **Java 17+**, có chương trình độc lập lấy JavaCompiler, áp dụng cấu hình cố định, kiểm tra đầu vào, không bật annotation processing và chỉ xác minh bytecode được tạo ra; tuyệt đối không coi ví dụ in-process là sandbox cho mã chưa tin cậy.

## 1. Xác định ranh giới và đối tượng cần bảo vệ

Trong một dịch vụ compile plugin, những tài sản cần bảo vệ không chỉ là mã ứng dụng chủ:

- **Máy/tiến trình build**: CPU, RAM, threads, file descriptors, disk và thời gian xử lý. Một yêu cầu compile không được làm kẹt toàn bộ host.
- **Bí mật và cấu hình**: tokens trong environment, credential của kho artifact, khóa ký, dữ liệu người dùng hoặc metadata của build agent.
- **Filesystem**: file nguồn, artifact của tenant khác, cache dependency, file cấu hình và thư mục làm việc của hệ thống.
- **Mạng và dịch vụ bên ngoài**: repository, database nội bộ, metadata endpoint, service điều khiển plugin.
- **Chuỗi cung ứng**: phiên bản JDK, annotation processors, compiler plugins, dependencies, build plugins và nguồn tải JAR.
- **Tính đúng của kết quả**: bytecode phải xuất phát từ chính input/dependency/toolchain đã được chấp nhận; không có sản phẩm cũ lẫn vào build mới.
- **Ranh giới giữa các tenant**: mã và thư viện của tenant A không được đọc hoặc sửa nguồn, output hoặc secret của tenant B.

Cần hỏi **ai được quyền quyết định phần nào**. Mã nguồn do người dùng cung cấp chỉ nên được coi là **dữ liệu biên dịch**; người dùng không mặc nhiên được quyết định compiler executable, JDK options, processor path, network endpoint hay vùng output của worker.

Một sơ đồ có phân chia quyền:

~~~text
[Người gửi plugin chưa tin cậy]
   |
   | source + metadata khai báo theo schema giới hạn
   v
[Ingress validator] -- reject --> [Kết quả có lý do]
   |
   | source đã chuẩn hóa; request ID; quota
   v
[Policy/dependency resolver] <-- chỉ repo/artifact đã phê duyệt
   |
   | manifest phiên bản + SHA-256 + danh sách quyền
   v
[Isolated compile worker]
   |  JDK/compiler tin cậy đã pin phiên bản
   |  classpath/module path được xây từ allowlist
   |  processor mặc định tắt; không có secret
   |  CPU/RAM/time/disk/network giới hạn từ OS
   v
[Output artifact quarantine]
   |
   | xác minh binary names, file count, metadata, hash
   v
[Artifact được duyệt] -- bước kích hoạt riêng --> [Plugin runtime]
~~~

Sơ đồ này là **mô hình vận hành**, không phải một tính năng tự có của javax.tools. Nếu chỉ gọi compiler.getTask() trong JVM của host, các bước isolation/quarantine phải do kiến trúc khác bảo đảm.

### Các vai trò và vùng tin cậy

| Thành phần | Độ tin cậy mặc định | Quyết định nên được phép |
| --- | --- | --- |
| Source Java do user upload | Chưa tin cậy | Định nghĩa logic plugin trong API được phép, không chọn quyền hệ thống |
| Metadata build do user gửi | Dữ liệu có schema | Chỉ các field đã allowlist: tên plugin, phiên bản, dependency ID được phép |
| Artifact dependency từ repository | Phụ thuộc xác minh provenance | Được resolver chấp nhận đúng tọa độ/hash, không tự thành tool thực thi |
| Annotation processor | **Mã thực thi tại compile-time** | Chỉ chạy khi host đã tin cậy, pin phiên bản và cho phép cụ thể |
| javac/toolchain | Thành phần quản trị tin cậy | Version, binary path, flags, module graph cố định theo policy |
| Build script/plugin | **Mã thực thi tại build-time** | Cần xét như chương trình có quyền, không như file cấu hình thuần |
| Output .class/.jar | Chưa tự động tin cậy | Chỉ đưa sang vùng artifact đã duyệt sau xác minh; chạy là bước riêng |

## 2. Mô hình đe dọa theo từng giai đoạn

### 2.1. Input được coi là dữ liệu, không phải một lệnh thực thi

Đầu vào có thể chứa mã Java hợp lệ nhưng gây nguy hiểm khi **chạy**; hoặc chứa cấu trúc nguồn/đường dẫn/tên file làm hỏng compiler workspace **ngay lúc xử lý**. Không phải mọi rủi ro đều đòi hỏi code execution.

Ví dụ các nhóm vấn đề:

- **Resource exhaustion**: source quá lớn, số class quá nhiều, biểu thức/kiểu generic phức tạp, nhiều file hoặc cấu trúc gây tiêu tốn tài nguyên khi phân tích.
- **Path traversal và lưu trữ file**: tên tệp dùng đường dẫn tuyệt đối, ../, đường dẫn tương đương trên Windows, symlink hoặc tên được chuẩn hóa không đúng, dẫn tới ghi ngoài workspace.
- **Archive input**: JAR/ZIP hoặc bundle có file lặp, path traversal trong ZIP entry, tỉ lệ giải nén quá lớn hoặc nhiều entry làm đầy disk.
- **Namespace collision**: source cố định nghĩa lại gói API của host, tên package được dành riêng hoặc tên class trùng với lớp khác trong workspace.
- **Tùy chọn biên dịch ngoài ý muốn**: user đặt compiler options, output directory, classpath hoặc processor path thay cho host.
- **Thông tin rò rỉ qua diagnostics**: đường dẫn host, classpath, source excerpt, tên package nội bộ, system environment bị log cho sai người xem.

Chính sách **bảo vệ trước khi chạy compiler** nên quyết định rõ file nào được phép, loại input nào chấp nhận, kích thước tối đa, cấu trúc package, độ sâu cây thư mục, đường dẫn nguồn và nơi ghi output. Tuy nhiên kiểm tra cú pháp hoặc regex trên source **không phải sandbox** để chứng minh mọi code được phép chạy sau đó.

### 2.2. Dependency và tool là các cửa thực thi riêng

Trong Java 17, công cụ javac có thể khám phá và thực thi **annotation processors** ở giai đoạn compile. Theo tài liệu javac của JDK 17, nếu không cấu hình đường processor riêng, các processor có thể được tìm trên **classpath**. Một dependency được thêm vào để tham chiếu kiểu, nhưng có kèm khai báo service processor, vì vậy có thể trở thành đường dẫn mã thực thi khi annotation processing được bật.

Build tool còn tạo thêm ranh giới: ví dụ một Maven/Gradle plugin, task hoặc script do người upload tự cung cấp có thể chạy lệnh hệ thống ngay trong giai đoạn build, bất kể có javac hay không. Phụ thuộc ở compile classpath và công cụ **được chạy** không nên trộn thành một nhóm quyền.

**Bài học cốt lõi:** chỉ đưa JAR lên classpath không có nghĩa các class trong đó đều tự chạy; nhưng công cụ được cấu hình để **load provider/processor/plugin** có thể biến một JAR thành mã có quyền lúc build. Phải kiểm soát cả **cơ chế khám phá** lẫn **danh sách công cụ thực thi**.

## 3. Kiểm soát đầu vào: giới hạn rõ và chuẩn hóa đúng

Một hợp đồng upload tốt nên chỉ chứa thông tin được kiểm soát, ví dụ:

~~~json
{
  "pluginId": "formatter-basic",
  "language": "java",
  "targetRelease": 17,
  "sources": [
    {
      "binaryName": "demo.generated.FormatterImpl",
      "content": "package demo.generated; public final class FormatterImpl {}"
    }
  ],
  "dependencyIds": ["public-plugin-api:1.2"]
}
~~~

**Đây là payload ví dụ**, không phải API chuẩn của Java. Host **không** chấp nhận các key kiểu compilerCommand, arbitraryFlags, shellScript, processorJarPath, uploadOutputPath hay absoluteClasspath từ đối tượng chưa tin cậy. Nếu có lựa chọn cấu hình, mỗi lựa chọn phải gắn với một policy được cấp quyền cụ thể.

### 3.1. Giới hạn dung lượng và cấu trúc

Kiểm tra tối thiểu **trước khi tạo workspace**:

1. Xác thực chủ thể gửi yêu cầu và quyền compile cho plugin/tenant đó.
2. Giới hạn kích thước tổng request, kích thước từng source theo byte UTF-8, số source, độ dài tên, số package và số artifact dependency.
3. Chỉ chấp nhận encoding đã quy định, thường UTF-8; không dựa vào encoding mặc định của máy build.
4. Kiểm tra binary class name và phần package theo grammar Java; một dấu chấm hoặc một ký tự Unicode trông giống nhau không tự có nghĩa là tên hợp lệ.
5. Cho phép các package/namespace đã cấp quyền; từ chối **java.**, các namespace nội bộ của host và package API mà plugin không được định nghĩa.
6. Không cho source mới ghi đè file có sẵn của tenant khác hoặc của chính toolchain.
7. Kiểm tra số lượng file, tổng byte sau giải nén và số byte output dự kiến theo quota.
8. Không coi một source bị parse lỗi là chứng cứ user đã tấn công: trả về **VALIDATION_FAILED** hoặc **COMPILE_FAILED** phù hợp, nhưng ghi nhận các dấu hiệu cố gắng vượt policy.

Giới hạn input ngăn nhiều tình huống DoS đơn giản, nhưng không giới hạn được mọi độ phức tạp của compiler. Một input nhỏ vẫn có thể gây tiêu thụ CPU hoặc lỗi parser; worker cần hạn mức ngoài tiến trình.

### 3.2. Tên lớp và đường dẫn là hai khái niệm khác nhau

Một binary name hợp lệ như demo.generated.FormatterImpl có thể được ánh xạ sang:

~~~text
workspace/src/demo/generated/FormatterImpl.java
~~~

Không làm:

~~~java
// MÃ MINH HỌA SAI: rawFileName đến từ request chưa tin cậy.
Path output = workspace.resolve(rawFileName);
Files.writeString(output, source);
~~~

Ví dụ này không phải class độc lập và cố tình bỏ validation để minh họa nguy cơ. Nếu rawFileName bắt đầu bằng đường dẫn tuyệt đối, chứa traversal, symlink hoặc được diễn giải khác nhau trên hệ điều hành, output có thể không nằm nơi dự định.

Cách tiếp cận đúng là **host tạo đường dẫn từ một binary name đã được xác minh**, giới hạn namespace, phân đoạn tên thành các phần Java identifier, gắn đuôi cố định .java và chỉ thao tác trong workspace do host tạo. Dùng Path.normalize và kiểm tra startsWith trên đường dẫn tuyệt đối đã được chuẩn hóa là một bước cần thiết, nhưng **chưa đủ chống symlink/race** khi kẻ khác có khả năng sửa cây thư mục. Worker thực tế cần filesystem/mount có ownership đúng, không dùng chung workspace có quyền ghi cho phía không tin cậy và xử lý symlink theo policy.

### 3.3. Khi nhận ZIP/JAR chứa nguồn

Một vòng duyệt entry cần:

- Từ chối entry tuyệt đối, entry traversal, tên không hợp lệ, device/special files, những entry và link không cho phép.
- Giải nén vào workspace riêng, không theo symlink do archive tạo.
- Giới hạn **số entry**, **độ sâu**, **kích thước nén**, **kích thước giải nén** và **tổng output**, kiểm tra cả khi đang streaming để tránh ZIP bomb.
- Phát hiện tên trùng sau chuẩn hóa (bao gồm khác biệt hoa/thường ở filesystem tương ứng), tránh overwrite entry ngoài ý muốn.
- Không tự thực thi các script hoặc build files được upload cùng archive.
- Không dùng tên file do archive cung cấp để cấu thành lệnh shell hoặc đường dẫn tool.

**ZIP entry kiểm tra trước khi trích xuất chưa đủ** nếu quy trình giải nén sau đó theo symlink hoặc không kiểm tra quota trong lúc stream. Cần giữ ranh giới kiểm soát ở cả lớp API và lớp filesystem.

## 4. Kiểm soát dependency: classpath không phải kho JAR tùy ý

Dependency làm compiler tìm được các kiểu, phương thức và annotation. Nếu để người gửi request tự tải bất kỳ tọa độ Maven hoặc URL nào, tính năng compile có thể trở thành một cổng mạng hoặc kho thực thi công cụ thiếu kiểm soát.

### 4.1. Chính sách resolver an toàn hơn

- **Cho phép qua ID/catalog đã đăng ký** thay vì nhận trực tiếp URL hoặc đường dẫn tuyệt đối từ request.
- Resolver ánh xạ ID sang **group/artifact/version và hash bất biến**, nguồn repository tin cậy, giấy phép và danh sách transitive dependencies.
- Kiểm tra hash/signature phù hợp chính sách; TLS bảo vệ transport nhưng không thay thế việc pin nội dung.
- Kiểm tra dependency graph hoàn chỉnh: không có phiên bản trôi, vòng trùng không mong muốn hoặc thư viện làm thay đổi API identity của host.
- Dùng local cache có quyền truy cập phù hợp, kiểm tra tính toàn vẹn ngay cả khi lấy lại từ cache.
- Nếu không cần tải qua mạng trong lúc compile, khóa egress để source không lợi dụng khả năng resolve nhằm liên hệ dịch vụ nội bộ.
- Dùng SBOM, quét lỗ hổng, provenance và review theo yêu cầu của môi trường vận hành; không coi một máy quét tự động là bảo đảm thư viện hoàn toàn an toàn.

**Pin phiên bản không đồng nghĩa pin nội dung** khi repository cho phép thay thế artifact có cùng version. Khóa bằng hash và nguồn xuất bản là phần quan trọng của build tái lập.

### 4.2. Tách ba nhóm đường phụ thuộc

| Nhóm | Mục đích | Ranh giới quyền |
| --- | --- | --- |
| **Compile classpath / module path** | Cung cấp API và class để compiler phân giải kiểu | Chỉ dependency được phép, version/hash đã pin |
| **Processor path / processor module path** | Chứa annotation processors chạy trong giai đoạn compile | Nhóm **mã thực thi**, cần phê duyệt riêng; tắt nếu không cần |
| **Compiler/build tool runtime** | JDK, javac, build plugins và tool/helper được chạy | Do platform quản lý, không để plugin chọn executable/flags tùy ý |

Dùng cùng một thư mục JAR làm mọi nhóm làm ranh giới tin cậy mờ đi. Trong Java 17, nếu annotation processing được bật mà **không khai báo processor path tách biệt**, javac có thể tìm processor trên user classpath. Cấu hình an toàn mặc định là **-proc:none** cho những tác vụ không cần code generation dựa trên annotation.

### 4.3. Classpath/module path phải tường minh

Nếu không khai báo -classpath/--class-path, javac có thể lấy CLASSPATH từ môi trường hoặc current directory. Điều này làm compiler nhìn thấy thư viện ngoài manifest được duyệt. Vì vậy dùng **classpath do host dựng**, không dựa vào môi trường worker.

Với explicit JPMS modules, dùng **--module-path** có kiểm soát, kiểm tra module names, requires, exports và tránh split packages. Đừng thêm mọi thư viện có trên máy bằng wildcard nếu chính sách chỉ cho một tập artifact; không được dựa vào class loader ngẫu nhiên của host để xác định tập dependency mà source có thể tham chiếu.

Khi chuẩn bị compile input chưa tin cậy, xem cả **source path**: nếu để mặc định compiler tìm các file .java khác trên classpath, một compilation task có thể kéo thêm source ngoài danh sách request. Gán **-sourcepath** tới thư mục nguồn được phép hoặc rỗng khi dùng in-memory source, sau đó kiểm tra artifact output thực tế.

## 5. Annotation processor và compiler plugin: trọng tâm của rủi ro compile-time

Annotation processing không phải chỉ đọc metadata. Một implementation của **javax.annotation.processing.Processor** là class Java có code, có thể được compiler nạp, khởi tạo và gọi khi xử lý annotation. Nó có thể sinh source, resource, truy cập filesystem, dùng mạng hoặc chạy logic phức tạp trong quyền của **quá trình compiler**.

### 5.1. Vì sao một JAR dependency có thể biến thành processor?

Trong một JAR có thể có file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung nêu class implementation của Processor. Đây là cơ chế Service Provider để javac phát hiện annotation processors khi annotation processing đang hoạt động và đường tìm processor cho phép.

Giả sử ứng dụng upload một thư viện chỉ vì cần annotation trong source. Nếu compiler mặc định quét classpath làm processor path, thư viện có đăng ký processor có thể làm **code processor chạy tại compile-time**, kể cả khi host không chủ động gọi method của thư viện đó sau biên dịch.

Không đánh đồng mọi thư viện chứa annotation với mã thực thi: **annotation chỉ là metadata**, còn **processor** là một chương trình chạy trong compile environment. Vấn đề phát sinh khi công cụ được cấu hình khám phá và gọi processor.

### 5.2. Các lựa chọn cấu hình

**Không cần annotation processing:**

~~~text
-proc:none
~~~

Trên **javac Java 17**, tùy chọn này vô hiệu hóa annotation processing cho lần compile. Đây là mặc định nên chọn đối với các plugin nguồn bình thường nếu business không yêu cầu processor.

**Có nhu cầu chạy processor tin cậy:**

~~~text
-processor com.example.approved.SafeProcessor
-processorpath /approved/processors
~~~

Hai dòng trên là **các option minh họa**, không phải lệnh javac độc lập. Với project modular, có thể cần --processor-module-path thay cho processor path thông thường. Host phải pin exact processor artifact, dependencies và những tùy chọn processor được phép. Cách khai báo -processor chỉ định processor nào được dùng, nhưng **không biến processor chưa tin cậy thành an toàn**.

**Không bao giờ** nhận processor class name, processor path hoặc -Akey=value tùy ý từ người chưa được cấp quyền. Một số processor đọc file/cấu hình dựa trên option; giá trị -A cũng cần validate theo schema nếu host có chủ trương hỗ trợ.

### 5.3. Compiler plugins và build tool

Ngoài annotation processor còn có javac plugins và nhiều cơ chế build-time code execution:

- **-Xplugin**: cơ chế plugin compiler ở các công cụ javac hỗ trợ. Chỉ cho phép plugin từ toolchain đã phê duyệt, không đi từ source request.
- **Maven/Gradle plugins, tasks và scripts**: nếu cho user upload pom.xml hoặc build.gradle rồi thực thi đầy đủ, host đã cho phép một chương trình build tùy biến chạy trong worker. Kiểm tra Java source không kiểm soát được điều này.
- **Code generators/native tools**: protobuf/thrift/codegen tools, script shell/PowerShell, formatter/analyzer có khả năng chạy code, cần danh sách executable và tham số được phép.
- **Javac runtime flags**: các cờ của JVM hoặc mở quyền module nội bộ có thể thay đổi môi trường chạy tool; không truyền nguyên một list compiler flags do user gửi.
- **File manager tùy biến**: JavaCompiler API cho phép JavaFileManager và JavaFileObject do application cài. Một implementation không tin cậy có thể đọc/ghi dữ liệu khi compiler gọi tới; nó cũng phải nằm trong ranh giới review.

Không chỉ định -proc:none rồi mặc định các plugin/build scripts khác bị tắt. **-proc:none chỉ điều khiển annotation processing**; không có tác dụng chung đối với toàn bộ hoạt động toolchain bên ngoài.

### 5.4. Bảng đánh giá khả năng thực thi tại compile-time

| Đầu vào/công cụ | Có thể chạy code lúc biên dịch? | Chính sách |
| --- | --- | --- |
| Source Java thông thường được javac phân tích | **Không mặc nhiên chạy static initializer hoặc main của source** | Validate và giới hạn tài nguyên; output không được tự chạy |
| Processor được javac khám phá | **Có** | Tắt với -proc:none hoặc allowlist processor đã duyệt |
| Plugin javac được bật | **Có** | Cấm options tùy ý; pin plugin từ toolchain tin cậy |
| Build script/task/plugin | **Có** | Không thực thi build file do user upload trong host có quyền; dùng pipeline do nền tảng định nghĩa |
| External code generator | **Có** | Binary/version/args được phép, chạy trong worker cô lập |
| Dependency JAR chỉ nằm trên compile path, không làm processor/plugin | Thường được đọc để phân giải kiểu, **không tự động gọi business code** | Vẫn xác minh provenance, hash, class identity và lỗi tool |
| Bytecode .class sinh ra sau compile | **Chưa tự chạy chỉ vì đã tạo file** | Kiểm tra artifact; tải/thực thi ở giai đoạn trust boundary riêng |

Bảng này không hứa parser hay compiler không có lỗ hổng; compiler vẫn là một chương trình xử lý input phức tạp, nên phải có patching và isolation ở cấp worker.

## 6. Kiểm soát compiler/toolchain: khả năng, phiên bản và tham số

### 6.1. Chọn công cụ qua chính sách, không qua source request

Một định nghĩa build đáng tin nên pin:

- JDK distribution và phiên bản patch; ví dụ JDK 17.x do tổ chức hỗ trợ.
- Đường dẫn binary/compiler implementation và checksum/container image digest.
- Mục tiêu bytecode qua **--release 17** hoặc target phù hợp với runtime cần hỗ trợ.
- Encoding **UTF-8**; locale/timezone của worker khi cần build tái lập.
- Classpath, module path, source path, processor path theo manifest đã được duyệt.
- Output root riêng, quyền file của workspace, cách loại bỏ file tạm.
- CPU/RAM/disk/process count/time/network limits và quyền truy cập secrets.
- Chính sách đối với compiler diagnostics, caches và artifact publication.

Với Java Compiler API, lấy compiler qua:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "Runtime không cung cấp system Java compiler");
}
~~~

Đây là snippet để đặt trong một method có import javax.tools.JavaCompiler và javax.tools.ToolProvider. Trên Java 17, **javax.tools** nằm trong module **java.compiler**, còn implementation compiler hệ thống do **jdk.compiler** cung cấp nếu khả dụng. Một custom runtime image có thể chạy Java được nhưng không có system compiler; nhánh null phải báo **TOOLCHAIN_UNAVAILABLE** hoặc cấu hình thất bại, không được coi là source syntax error.

### 6.2. Công dụng và giới hạn của các option phổ biến

| Option | Mục đích đúng | Không nên hiểu nhầm |
| --- | --- | --- |
| **--release 17** | Biên dịch theo API/language/bytecode target của release được hỗ trợ | Không hạn chế quyền của code sau khi thực thi |
| **-encoding UTF-8** | Xử lý source với encoding ổn định | Không làm source trở nên đáng tin |
| **-proc:none** | Tắt annotation processing trong javac | Không tắt mọi plugin/codegen hay chống compiler resource exhaustion |
| **-classpath / --class-path** | Chỉ định library/class lookup cho classpath compilation | Không giống OS sandbox hoặc danh sách dependency verified tự động |
| **--module-path** | Chỉ định module lookup khi biên dịch module | Không tự quyết định nguồn gốc/trust của module JAR |
| **-sourcepath** | Giới hạn nơi tìm source khác khi compiler cần | Không chống path traversal nếu tool input/output tùy ý |
| **-d** | Đưa bytecode vào output directory được chỉ định | Không tự bảo đảm output nằm trong sandbox nếu workspace bị can thiệp |
| **-processorpath / -processor** | Chỉ định processor khi quyết định dùng nó | Không phải cơ chế bảo vệ khỏi processor độc hại |

Khi compile code từ người dùng, **không cho raw options đi xuyên qua API**. Một người dùng không nên tự cung cấp các cờ làm thay đổi đường processor, đường output, classpath, cách thực thi plugin hay đường đọc argfile.

### 6.3. Những biến môi trường không nên bỏ qua

Khi chạy javac thành **process riêng**, các biến môi trường có thể tác động tới launcher và tool. Ví dụ **JDK_JAVAC_OPTIONS** được javac dùng để bổ sung options cho command line; **JAVA_TOOL_OPTIONS** và các tùy chọn launcher liên quan cũng có thể thay đổi cách JVM mới được khởi động. Nếu một worker kế thừa environment từ tiến trình có chứa token, proxy hoặc flags không mong muốn, chỉ truyền một argv sạch là chưa đủ.

Với ProcessBuilder, cần xây environment **tối thiểu theo hệ điều hành** và công cụ, chủ động bỏ các biến không được phép, đặc biệt biến ảnh hưởng compiler/launcher và secrets. Không xóa bừa toàn bộ environment rồi giả định javac hoạt động trên mọi nền tảng; worker cần một tập biến cố định được kiểm thử trên OS/locale tương ứng.

**JDK_JAVAC_OPTIONS không ảnh hưởng trực tiếp đến API getTask trong cùng JVM theo cách command-line parser của javac.exe**, nhưng khi host khởi chạy chương trình javac ngoài tiến trình, biến này là một đầu vào phải kiểm soát. Tách biệt hai kiểu chạy là cần thiết để thiết kế policy đúng.

## 7. Biên dịch trong JVM hay process riêng?

### 7.1. JavaCompiler API trong cùng JVM

Ưu điểm: input in-memory, diagnostics có cấu trúc, JavaFileManager tùy biến và không cần spawn process cho mỗi lần compile. Ví dụ:

~~~java
// MÃ MINH HỌA: cần các đối tượng sourceFile, options hợp lệ.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Compiler unavailable");
}
try (StandardJavaFileManager manager =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    boolean success = Boolean.TRUE.equals(
            compiler.getTask(
                    null, manager, diagnostics,
                    options, null, List.of(sourceFile)).call());
}
~~~

Đoạn này **không phải chương trình độc lập**, vì diagnostics/options/sourceFile là thành phần do caller cung cấp. Đường chạy này phù hợp với **source tin cậy hoặc worker đã được cách ly**, nhưng không tạo ranh giới bảo mật mới giữa source/processor và host.

Nếu annotation processor hoặc plugin do bên chưa tin cậy được chạy, code ấy có thể nhận quyền của JVM/compiler. Một tác vụ compile chiếm bộ nhớ quá mức cũng có thể gây tác động trực tiếp tới JVM host; API JavaCompiler không cung cấp một tham số timeout/heap quota riêng cho từng CompilationTask.call().

### 7.2. Process riêng được cấu hình cẩn thận

Dùng ProcessBuilder với **danh sách tham số**, **không ghép command line thành shell string**, để tránh diễn giải ký tự shell từ tên file/tham số.

~~~java
// MÃ MINH HỌA CẤU TRÚC, KHÔNG PHẢI CHƯƠNG TRÌNH ĐỘC LẬP.
// javacPath, approvedClasspath, sourceFile, outputDir, workDir
// đều do HOST tạo và kiểm tra; không lấy nguyên giá trị từ user.
ProcessBuilder builder = new ProcessBuilder(
        javacPath.toString(),
        "--release", "17",
        "-proc:none",
        "-encoding", "UTF-8",
        "-classpath", approvedClasspath.toString(),
        "-d", outputDir.toString(),
        sourceFile.toString());
builder.directory(workDir.toFile());

// Trước builder.start(): áp dụng allowlist environment,
// xử lý stdout/stderr, quyền filesystem, network, quota và timeout.
~~~

**ProcessBuilder chỉ giải quyết việc truyền argv mà không đi qua shell; bản thân nó không phải sandbox.** Compiler process vẫn có quyền OS của tài khoản chạy nó. Không mở quyền truy cập thư mục host, network hoặc secret cho worker nếu không cần; dùng user/process/container riêng, mount giới hạn và kiểm soát egress.

Quản lý process cần:

1. Giới hạn wall time, CPU, bộ nhớ, số process và dung lượng output **từ OS/container**.
2. Thu stdout/stderr song song hoặc redirect vào một sink có giới hạn. Nếu gọi waitFor nhưng không đọc các pipe đầy, process có thể bị block và timeout giả.
3. Khi timeout, ghi nhận kết quả **TIMEOUT**; hủy process **và tiến trình con** theo policy, không coi một destroyForcibly đơn lẻ là đủ cho toàn bộ process tree.
4. Bảo vệ cleanup khi parent crash; dùng supervisor/worker lease và cơ chế thu hồi workspace sau failure.
5. Không publish artifact nếu compiler exit code không thành công, task bị hủy hoặc output validation thất bại.
6. Với source không tin cậy, cân nhắc worker **không có mạng**, không secret và chỉ có quyền ghi vào output/workspace được cấp.

**Quan trọng:** ngay cả khi -proc:none và compiler nhận source qua file, chỉ chuyển sang subprocess mà vẫn chạy dưới tài khoản có đầy đủ quyền host chưa phải một trust boundary có ý nghĩa. Ranh giới thật nằm ở quyền hệ điều hành, filesystem isolation, resource limits và đường artifact được công bố có kiểm tra.

## 8. Ví dụ Java 17 độc lập: compile input cố định dưới policy tối thiểu

Ví dụ này giúp nhìn thấy **cách cấu hình đúng** JavaCompiler trước khi triển khai một service. Nó chỉ biên dịch **source hardcoded tin cậy**, không chạy bytecode, không tải dependency bên ngoài, không dùng annotation processors, và xóa output sau kiểm tra.

**Không sử dụng ví dụ in-process này để chạy source từ người lạ trên host production.** Nó chỉ trình bày những điểm kiểm soát trong API; isolation và quotas thật phải nằm ở worker như phần 7.

### 8.1. File CompilationBoundaryDemo.java

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

import javax.lang.model.SourceVersion;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilationBoundaryDemo {
    private static final String BINARY_NAME =
            "demo.generated.SafeValue";

    private static final String SOURCE = """
            package demo.generated;

            public final class SafeValue {
                public static String value() {
                    return "OK";
                }
            }
            """;

    private CompilationBoundaryDemo() {
    }

    public static void main(String[] args) throws Exception {
        // Capability của runtime, không liên quan source syntax.
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("compiler=unavailable");
            return;
        }
        System.out.println("compiler=available");

        validateInput(BINARY_NAME, SOURCE);
        System.out.println("source=accepted");

        // Workspace không chia sẻ với lần compile khác.
        Path workspace = Files.createTempDirectory(
                "compile-boundary-demo-");

        try {
            Path output = Files.createDirectories(
                    workspace.resolve("classes"));
            Path emptyDependencies = Files.createDirectories(
                    workspace.resolve("empty-dependencies"));

            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();

            JavaFileObject sourceFile =
                    new InMemorySource(BINARY_NAME, SOURCE);

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-proc:none",
                    "-classpath", emptyDependencies.toString(),
                    "-sourcepath", emptyDependencies.toString(),
                    "-d", output.toString()
            );

            boolean ok;
            try (StandardJavaFileManager manager =
                         compiler.getStandardFileManager(
                                 diagnostics,
                                 Locale.ROOT,
                                 StandardCharsets.UTF_8)) {

                JavaCompiler.CompilationTask task =
                        compiler.getTask(
                                null,
                                manager,
                                diagnostics,
                                options,
                                null,
                                List.of(sourceFile));

                ok = Boolean.TRUE.equals(task.call());
            }

            System.out.println("compile=" +
                    (ok ? "success" : "failure"));

            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + "@line=" +
                            d.getLineNumber());
                }
                return;
            }

            Path classFile = output.resolve(
                    "demo/generated/SafeValue.class");
            System.out.println(
                    "artifact=" + Files.isRegularFile(classFile));
            // Cố ý KHÔNG nạp/chạy bytecode vừa sinh ra.
        } finally {
            deleteRecursively(workspace);
        }
    }

    private static void validateInput(
            String binaryName, String source) {

        if (!binaryName.startsWith("demo.generated.")) {
            throw new IllegalArgumentException(
                    "Namespace is not permitted");
        }
        for (String part : binaryName.split("\\.", -1)) {
            if (!SourceVersion.isIdentifier(part)
                    || SourceVersion.isKeyword(part)) {
                throw new IllegalArgumentException(
                        "Invalid Java binary name");
            }
        }
        if (source.length() > 16_000) {
            throw new IllegalArgumentException(
                    "Source exceeds demo character limit");
        }
    }

    private static void deleteRecursively(Path root)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    private static final class InMemorySource
            extends SimpleJavaFileObject {

        private final String code;

        InMemorySource(String binaryName, String source) {
            super(URI.create(
                    "string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return code;
        }
    }
}
~~~

### 8.2. Lệnh chạy và stdout

Lưu file đúng tên **CompilationBoundaryDemo.java**, UTF-8. Mở terminal tại thư mục chứa file, dùng một JDK 17 đầy đủ:

~~~bash
javac --release 17 -encoding UTF-8 CompilationBoundaryDemo.java
java CompilationBoundaryDemo
~~~

**Stdout dự kiến trên JDK 17 đầy đủ, có quyền tạo/xóa thư mục tạm và compiler làm việc bình thường:**

~~~text
compiler=available
source=accepted
compile=success
artifact=true
~~~

Nếu file class của chính ví dụ đã được build từ trước và được chạy trên runtime **có API java.compiler nhưng không cung cấp system compiler**, nhánh đúng là:

~~~text
compiler=unavailable
~~~

Đây là hai môi trường chạy khác nhau, không phải output của cùng một lệnh. Nếu hệ thống không cho ghi thư mục tạm hoặc compiler gặp lỗi hạ tầng, chương trình có thể ném exception; lỗi đó phải phân loại riêng trong ứng dụng sản xuất.

### 8.3. Mỗi biện pháp trong ví dụ làm được gì?

**validateInput** kiểm tra một namespace đơn giản, các segment của binary name và giới hạn ký tự trong một source cố định. Nó minh họa validation ở ingress, nhưng **chưa đầy đủ cho hệ upload thật**: giới hạn byte UTF-8, tổng số file, path traversal, ZIP entries, nguồn gốc và quyền của request vẫn cần được triển khai.

**InMemorySource** làm cho đầu vào biên dịch là một JavaFileObject do host tạo, không phải path tùy ý từ request. File manager vẫn có thể truy cập filesystem theo quyền process và compiler vẫn có thể tiêu tốn tài nguyên, nên **in-memory không biến compile thành sandbox**.

**--release 17** giữ target Java 17, **-encoding UTF-8** tránh phụ thuộc encoding môi trường, **-proc:none** chặn annotation processing, **-classpath** và **-sourcepath** trỏ đến thư mục rỗng do host tạo để không âm thầm dựa vào CLASSPATH/current directory. Khi compile dự án thật có dependency, thay thư mục rỗng bằng **tập artifact đã xác minh**.

**-d** chỉ định output khác với input. Mỗi task có output root mới, giúp tránh dùng class file từ build trước. Dùng **Boolean.TRUE.equals(task.call())** để nhận kết quả, còn diagnostics ghi loại lỗi và vị trí mà không hứa nguyên văn message ổn định theo JDK/vendor/locale.

**Không nạp class được biên dịch**: việc tạo .class và việc thực thi mã là hai giai đoạn riêng. Ví dụ chỉ xác minh class file tồn tại. Đối với plugin chưa tin cậy, giai đoạn thực thi cần một ranh giới process/container được thiết kế riêng, không lấy URLClassLoader làm biện pháp cách ly đủ dùng.

**Cleanup** được gọi trong finally sau khi manager đã đóng. Trong production cần cơ chế dọn orphan workspace khi process crash, xử lý lỗi xóa file và không để cleanup exception che mất kết quả build quan trọng.

## 9. Vì sao một vài cấu hình trông an toàn nhưng vẫn chưa đủ?

### 9.1. Chỉ dùng -proc:none

Đúng là option này tắt annotation processors của javac cho compilation. Tuy nhiên nó không tắt build scripts, javac plugins đã được bật bằng flag khác, native codegen hoặc tác vụ toolchain mà pipeline gọi trước/sau javac. Nó cũng không giới hạn CPU/RAM của parser và không bảo vệ giai đoạn nạp class sau compile.

Do đó -proc:none là một **lớp bảo vệ có mục tiêu**, không phải toàn bộ chính sách bảo mật.

### 9.2. Chỉ lọc source bằng regex

Lọc một số từ khóa như Runtime, ProcessBuilder hoặc java.io không làm mã an toàn; Java có reflection, thư viện, các cấu trúc ngôn ngữ và nhiều đường biểu đạt. Trước khi chạy bytecode, hệ thống phải dùng isolation dựa trên quyền thực tế. Static analysis và allowlist API có thể cung cấp thêm tín hiệu, nhưng không thay thế OS sandbox.

### 9.3. Chỉ dùng ProcessBuilder không gọi shell

Argument array tránh nhiều lỗi shell quoting và injection truyền thống, nhưng **javac vẫn có ngữ nghĩa riêng với các argument**, ví dụ argfile dạng @filename và các compiler options khác. Nếu cho user kiểm soát argv, họ có thể khiến tool đọc file hoặc thay đổi cách compile dù không có shell.

Giải pháp là host tạo **toàn bộ option vector** từ các tham số có kiểu/đã validate; không gắn raw compilerArg vào lệnh. Bên cạnh đó vẫn phải giới hạn quyền process và filesystem.

### 9.4. Chỉ dùng --release 17

--release quản lý API/language target, không cấm import mã ở dependency mà host đã cho vào classpath, không cấm annotation processor và không giới hạn quyền runtime. Dùng nó để bảo đảm khả năng tương thích bytecode, **không làm chính sách sandbox**.

### 9.5. Chỉ dùng một thư mục temp khác cho mỗi request

Thư mục riêng giúp tránh ghi đè lẫn nhau nhưng không bảo vệ nếu compiler process vẫn có quyền đọc thư mục home, credential hoặc file của tenant khác. Môi trường file cần ownership, mount và quyền riêng của worker; process không nên kế thừa quyền mạnh của host.

### 9.6. Chỉ kiểm tra compile thành công

CompilationTask.call() thành công nghĩa là tool cho rằng compilation đã thành công, **không có nghĩa artifact an toàn, đúng tenant, được phép nạp hay tương thích với host API**. Trước khi publish cần kiểm tra output origin, cấu trúc, hash, policy và khi có thể đối chiếu module/class metadata. Không dùng compilation success làm approval cho runtime execution.

## 10. Quản lý output: từ file .class sang artifact được duyệt

Output nên được tạo ở **vùng tạm cách ly** và chỉ đi tới registry sau bước xác minh riêng:

1. Gắn job ID, tenant ID, source digest, dependency manifest digest, compiler image digest và chính sách được áp dụng.
2. Tạo output directory mới; không dùng chung thư mục output với job khác, không reuse file cũ.
3. Giới hạn kích thước tổng .class/.jar, số file, package names và số entry; không theo symlink.
4. Kiểm tra mọi output nằm trong workspace được phép; source và output không viết qua vùng chia sẻ không tin cậy.
5. Kiểm tra bytecode/JAR có cấu trúc phù hợp, main/provider metadata nếu hợp đồng plugin yêu cầu. Không coi bytecode verification là malware detection.
6. Chỉ publish artifact khi **compile success, output validation success, provenance đủ và policy approve**.
7. Ghi checksum/content-addressed artifact ID để việc tải và kích hoạt sau này xác nhận chính xác bytes.
8. Không trộn output của các job với nhau; rollback chỉ dùng artifact đã được ghi nhận, không lấy lại file temp bị can thiệp.

Lưu ý: Java package name và binary name tương thích chưa chứng minh provider có đúng interface của host. Đó là bước **API compatibility validation** tiếp theo ở vùng được cô lập. Không load provider vào JVM production chỉ để “kiểm tra cho chắc” khi code vẫn chưa đáng tin.

### Build reproducibility và công thức artifact

Một bản ghi kiểm chứng có thể mô tả:

~~~text
BuildIdentity =
  SHA-256(source manifest + normalized contents)
  + SHA-256(dependency lock manifest)
  + compiler image/version digest
  + normalized compiler options
  + build policy revision

PublishedArtifact =
  artifact SHA-256 + BuildIdentity + diagnostics/attestation
~~~

Đây là **sơ đồ khái niệm**, không phải một công thức hash chuẩn: trong hiện thực phải dùng serialization canonical, thuật toán ký/hashing rõ ràng và tránh ghép các chuỗi mơ hồ. Hai lần compile không luôn sinh bytes tuyệt đối giống nhau nếu có timestamps, non-deterministic processors, resource ordering hoặc công cụ không reproducible. Lưu provenance giúp đối chiếu, còn khả năng reproducible cần test thực tế.

## 11. Kịch bản hệ thống thực: mở rộng từ ví dụ tối thiểu

### 11.1. Host chỉ cần compile interface implementation đơn giản

Đối với source sinh từ template tin cậy do chính host điều khiển, nhiều trường hợp có thể dùng JavaCompiler API trong worker process đã quản lý. Không cho user chọn compiler flags; dependency là API artifact được pin, processor mặc định tắt, output riêng. Sau đó artifact đi qua một bước kích hoạt plugin độc lập.

Nếu source thật sự do bên ngoài viết và chưa tin cậy, nên đặt compiler bên trong **worker ít quyền** ngay cả khi đã tắt processors, do compiler vẫn xử lý input phức tạp và có khả năng tiêu tốn tài nguyên.

### 11.2. Plugin cần annotation processor

Không thể chỉ bật lại annotation processing rồi giữ các giả định cũ. Cần chính sách:

1. Xác nhận nhu cầu codegen của plugin và processor cần dùng.
2. Phê duyệt processor artifact và dependencies riêng với compile dependencies; pin version/hash và quyền.
3. Chạy processor trong worker cô lập với quota, không secret và network hạn chế.
4. Quy định -processor, processor path/module path và các -A options hợp lệ.
5. Kiểm soát file được processor sinh, tổng lượng output và nơi ghi.
6. Ghi processor identity trong build attestation.
7. Kiểm thử lỗi/hành vi không xác định; processor có thể sinh source khác ở vòng xử lý tiếp theo.

Nếu processor cần quyền mạng/ghi file đặc biệt, xử lý đó phải là **một năng lực có chủ đích và được duyệt**, không mặc nhiên cấp vì một dependency khai báo cần processor.

### 11.3. Plugin gửi cả Maven/Gradle project

Đây là trường hợp khác hoàn toàn với việc gửi các file Java đơn. Một build project có thể chứa script và các plugin/task thực thi. Host không nên dùng shell gọi **mvn** hoặc **gradle** với file build của người dùng trong cùng tài khoản có secret chỉ vì source Java đã qua validate.

Các phương án kiến trúc:

- Nhận **source + dependency manifest có schema hạn chế**, platform tạo build script/tác vụ cố định.
- Hoặc nếu hỗ trợ build project tùy ý, chạy trong **build worker được cách ly mạnh** với quyền và mạng hạn chế, không mount host secrets/cache nhạy cảm, có quota/timeout và policy artifact verification.
- Cần pin Maven/Gradle distribution, settings, plugin repositories, dependency repositories và checksum tương ứng.
- Không cho build tự ý truy cập Docker socket, host filesystem, cloud credentials hoặc network internal.

Đừng đánh đồng dependency resolution với dependency execution: Gradle plugin hoặc Maven plugin có quyền chạy code trong worker, khác với việc javac đơn thuần đọc một JAR để phân giải kiểu.

## 12. Logging, diagnostics và kết quả có kiểu

Một hệ thống nên phân loại lỗi thay vì trả một boolean chung:

| Mã kết quả | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| **INPUT_REJECTED** | Ingress | Sai schema, vượt quota, package/path không được phép |
| **DEPENDENCY_REJECTED** | Resolve | Artifact/version/hash hoặc transitive graph không đúng policy |
| **TOOLCHAIN_UNAVAILABLE** | Prepare compiler | Không có compiler/JDK image hoặc binary không hợp lệ |
| **TOOL_POLICY_REJECTED** | Prepare task | Có processor/plugin/option hoặc executable không được duyệt |
| **COMPILATION_FAILED** | Compile | Source không biên dịch thành công; diagnostics dành cho tác giả |
| **COMPILER_TIMEOUT** | Compile worker | Hết hạn tài nguyên/thời gian; phải xử lý process tree và output |
| **INFRASTRUCTURE_ERROR** | Worker/I/O | File manager, temp workspace, disk, network được phép hoặc cleanup lỗi |
| **ARTIFACT_REJECTED** | Post-build | Output vượt giới hạn, không đúng cấu trúc/hash/provenance |
| **APPROVED** | Publish | Artifact đủ điều kiện để lưu; **không tự động được thực thi** |

Đối với ToolProvider.getSystemJavaCompiler() trả null, dùng **TOOLCHAIN_UNAVAILABLE**, không lẫn với COMPILATION_FAILED. Với JavaCompiler.getTask(...).call() trả false, dùng COMPILATION_FAILED và lấy DiagnosticCollector. IOException hoặc RuntimeException trong worker có thể là INFRASTRUCTURE_ERROR, nhưng cần phân loại theo ngữ cảnh, không giấu lỗi bất ngờ.

### Diagnostics không phải log công khai nguyên văn

Diagnostic có thể chứa **đường dẫn source, tên file, dòng/cột, đoạn trích mã và thông tin phụ thuộc**. Hãy giới hạn số lượng và dung lượng message, loại bỏ đường dẫn máy chủ/secrets trước khi trả, tránh đưa raw command line hay toàn bộ environment vào log client.

Ghi theo job ID/tenant ID với mức truy cập phù hợp:

~~~text
job=build-42
tenant=tenant-a
stage=compile
toolchain=approved-jdk17-digest
processors=disabled
dependency-lock=sha256:...
source-count=2
outcome=COMPILATION_FAILED
diagnostics-count=3
artifact-published=false
~~~

Dòng trên chỉ là **ví dụ log minh họa**, không phải stdout của chương trình phần 8. Log phải giữ đủ thông tin để tái hiện lỗi, nhưng không tiết lộ source hoặc token cho tenant khác.

## 13. Những trường hợp test bắt buộc trước khi triển khai

Test nên tách **unit validation**, **integration compiler** và **isolation/system tests**.

### 13.1. Validation và dependency policy

- Source rỗng, vượt byte limit, quá nhiều file, tên class có segment không hợp lệ hoặc namespace bị cấm.
- Upload ZIP có entry traversal, đường dẫn tuyệt đối, symlink, tên trùng sau normalization, tỉ lệ giải nén vượt quota.
- Dependency ID không được duyệt, hash mismatch, dependency có version trôi hoặc transitives không có trong lockfile.
- User cố gửi raw flags, processor path, output directory hoặc shell script trong request schema: **INPUT_REJECTED/TOOL_POLICY_REJECTED**.
- Hai tenant dùng cùng binary name và chạy đồng thời: workspace/output/cache không ghi đè nhau.
- User tạo source hợp lệ có package/class không khớp metadata: reject hoặc báo compile error rõ, không âm thầm đổi tên.

### 13.2. Toolchain và compiler behavior

- JDK 17 đầy đủ có system JavaCompiler: source nội bộ hợp lệ biên dịch thành công.
- Custom runtime image không có jdk.compiler: getSystemJavaCompiler() null, báo TOOLCHAIN_UNAVAILABLE.
- Source lỗi cú pháp: task.call() false, diagnostics được thu, không publish artifact.
- Dependency thiếu: compiler báo lỗi không tìm thấy kiểu, không tự quét thư viện ngoài allowlist.
- Một JAR có đăng ký annotation processor nhưng config -proc:none: processor không được gọi.
- Chế độ processor allowlist: chỉ processor đã được duyệt được chạy trong worker cô lập.
- Bất kỳ option từ user không được ghép vào argv; kiểm thử tên file lạ và ký tự shell không thay đổi hành vi tool.
- Compiler process nhận environment đã scrub, không bị JDK_JAVAC_OPTIONS do tenant inject.
- Output artifact bị thay đổi giữa compile và publish: kiểm tra hash/ownership để reject.

### 13.3. Resource isolation và failure handling

- Compiler loop lâu hoặc chiếm nhiều RAM: worker bị giới hạn/hủy theo policy; host chính vẫn phục vụ request khác.
- Output quá lớn, disk full, file manager error: báo đúng mã và dọn workspace, không publish artifact nửa vời.
- Process timeout: thu hồi cả process tree, không để subprocess sống sót tiếp tục dùng tài nguyên.
- Worker crash lúc đang compile: scheduler đánh dấu job thất bại, janitor dọn orphan temp/artifacts.
- Không mạng/không token: một tool/plugin thử truy cập vùng không được cấp quyền phải bị OS/network policy chặn.
- Rollout artifact vừa build: nạp/kiểm thử trong vùng plugin runtime phù hợp, không coi compiler security policy là runtime sandbox.
- Thay JDK minor, update dependency hoặc processor: chạy lại reproducibility/test matrix trước khi phát hành.

**Phân biệt test bảo vệ bằng validator và test bảo vệ bằng isolation.** Một unit test thấy regex reject là hữu ích, nhưng không chứng minh process container ngăn được truy cập filesystem/network hoặc hủy được tiến trình con.

## 14. Các lỗi cấu hình phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách sửa ưu tiên |
| --- | --- | --- |
| Annotation processor chạy bất ngờ | javac quét user classpath làm processor path | Dùng -proc:none; nếu cần processor, path/allowlist riêng |
| Build đọc thư viện ngoài danh sách | Dùng CLASSPATH/current directory mặc định | Khai báo classpath/module path/source path theo manifest cố định |
| Source upload ghi ra ngoài thư mục build | Tin raw filename hoặc giải nén ZIP thiếu kiểm soát | Tạo path từ binary name hợp lệ; kiểm tra filesystem/symlink/quota |
| JavaCompiler trả null | Runtime không có jdk.compiler | Dùng toolchain image phù hợp, trả TOOLCHAIN_UNAVAILABLE |
| Lỗi compile bị coi là thiếu compiler | Gộp false/exception/null | Tách capability, diagnostics, infrastructure status |
| User được truyền -processor hoặc -Xplugin | Raw tool flags không được kiểm soát | Dùng schema và option builder do host sở hữu |
| Một JAR dependency tải từ mạng tự được tin | Không pin checksum/provenance | Approved repository + lock manifest + hash |
| Process compile vẫn đọc được secret | Worker dùng quyền và environment host | Least privilege, sanitized env, no secrets, mount/net isolation |
| Output lẫn class từ lần trước | Reuse output directory | Fresh output per job; kiểm tra và publish theo job ID |
| Process timeout nhưng còn child sống | Chỉ kill top-level process | Supervisor/process group/container cleanup |
| Compile pass nhưng artifact gây lỗi runtime | Nhầm compile success với runtime validation | Tách artifact review, API compatibility, activation sandbox |
| Không thể tái hiện build | Toolchain/dependency/options không được pin | Build identity, digests, manifests, normalized config |
| Phân tích security chỉ qua regex source | Không xét compiler plugins/build scripts/isolation | Threat model ở cả source, tools, deps và runtime |

## 15. Checklist kiểm soát biên dịch plugin

**Trước khi nhận input**

- Xác thực tenant/quyền compile, có rate limit và quota.
- API chỉ chấp nhận metadata có schema; không nhận raw shell command/compiler argv.
- Kiểm tra source count, UTF-8 bytes, binary names, package allowlist, độ sâu và tổng kích thước.
- Nếu input là archive, chống traversal, symlink, duplicate entries và decompression bomb.

**Trước khi resolve dependency**

- Chỉ nhận dependency IDs được phép; pin transitive graph, version và hash.
- Xác minh repository/provenance và cache ownership; không tự mở mạng nội bộ.
- Tách compile classpath/module path khỏi processor path và build-tool runtime.
- Bảo đảm API chung của host không bị plugin định nghĩa bản sao tùy tiện.

**Trước khi chạy compiler**

- Dùng compiler/JDK image đã duyệt, có version/digest và môi trường được kiểm soát.
- Kiểm tra ToolProvider khác null hoặc xác minh javac executable của worker.
- Dựng options tường minh: --release, encoding, classpath/module path, source path, output path.
- **-proc:none nếu không cần annotation processors**; nếu cần, pin và allowlist processor riêng.
- Không chấp nhận -Xplugin, argfile, JVM flags hoặc codegen task không được duyệt từ user.
- Chạy trong process/container ít quyền khi nguồn chưa tin cậy; không có secrets, network giới hạn.
- Có CPU/memory/disk/time/process limits và cơ chế xử lý timeout/process tree.

**Sau khi compile**

- Phân biệt null compiler, source compile false, worker exception và timeout.
- Thu DiagnosticCollector/output có giới hạn, bảo vệ đường dẫn và dữ liệu nhạy cảm.
- Đóng JavaFileManager/streams, dọn workspace và xử lý crash cleanup.
- Xác minh toàn bộ output thuộc job, kích thước/tên/schema phù hợp, hash và provenance.
- Chỉ publish artifact đã duyệt; việc nạp/thực thi plugin được kiểm soát bằng một ranh giới riêng.

**Kết luận:** Ranh giới tin cậy của quá trình biên dịch **không dừng ở nội dung file .java**. Phải kiểm soát **đầu vào có cấu trúc**, **dependency graph và nguồn JAR**, **processor/plugin/build tool có thể chạy code**, **phiên bản và option của javac**, **quyền process cùng hạn mức tài nguyên**, và **artifact sau khi sinh**. Tắt annotation processing, dùng classpath tường minh và validate source là những lớp cần thiết nhưng **không thay thế isolation cho nguồn chưa tin cậy**. Tách compile khỏi activation giúp hệ runtime extensibility vừa linh hoạt vừa không trao quyền của host cho plugin qua đường build.

## Tài liệu chính thức để đối chiếu

- Java SE 17 — **javac command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html — options, annotation processing, classpath, processor path, JDK_JAVAC_OPTIONS và --release.
- Java SE 17 — **JavaCompiler**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html — getTask, StandardJavaFileManager, diagnostics và compilation results.
- Java SE 17 — **ToolProvider**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html — getSystemJavaCompiler() và khả năng trả null.
- Java SE 17 — **Processor**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html — hợp đồng thực thi annotation processor.
- OpenJDK — **JEP 411**: https://openjdk.org/jeps/411 — Security Manager bị deprecated for removal trên Java 17; không coi một cơ chế sandbox nội JVM mặc định là đủ để cô lập code chưa tin cậy.
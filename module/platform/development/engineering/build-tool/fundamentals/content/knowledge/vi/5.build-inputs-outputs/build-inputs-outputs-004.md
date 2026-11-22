# Đầu ra trung gian, artifact cuối cùng và báo cáo kiểm chứng

Một quy trình build Java tạo ra nhiều loại đầu ra ở những thời điểm khác nhau. Có file chỉ phục vụ bước tiếp theo trong quá trình build, có file là sản phẩm cần giao cho người dùng hoặc hệ thống khác, và có file lưu bằng chứng rằng các bước kiểm tra đã chạy như thế nào. Nếu gom tất cả vào khái niệm “file build”, nhóm sẽ khó biết file nào cần giữ, file nào có thể tạo lại, file nào được phép phát hành và file nào phải được lưu để điều tra khi có lỗi.

Trong Gradle, các đầu ra này thường nằm dưới thư mục **build/** của từng project. Tuy nhiên, vị trí và tên file cụ thể phụ thuộc vào plugin, task, cấu hình và loại module. Điều quan trọng là hiểu vai trò của từng đầu ra, quan hệ của nó với task tạo ra nó và cách xác minh nó trước khi sử dụng.

Bài học này phân biệt ba nhóm chính:

1. **Đầu ra trung gian (intermediate outputs):** các file được tạo trong quá trình build để phục vụ một hoặc nhiều task tiếp theo.
2. **Artifact cuối cùng (final artifacts):** sản phẩm đã được đóng gói để chạy, phân phối, lưu trữ hoặc chuyển sang một bước triển khai khác.
3. **Báo cáo kiểm chứng (verification reports):** dữ liệu cho biết build, test và các bước kiểm tra đã thực hiện ra sao.

Ba nhóm có thể cùng nằm trong **build/**, nhưng chúng có mục đích và chính sách lưu trữ khác nhau.

## 1. Nhìn toàn bộ vòng đời đầu ra

Một build Java điển hình có thể được hình dung như sau:

~~~mermaid
flowchart TD
    A["Source code và cấu hình"] --> B["Đầu ra trung gian"]
    B --> C["Artifact cuối cùng"]
    A --> D["Các bước kiểm chứng"]
    B --> D
    C --> E["Kiểm tra artifact"]
    D --> F["Báo cáo kiểm chứng"]
    E --> F
    C --> G["Lưu trữ hoặc phát hành"]
    F --> H["CI lưu báo cáo và bằng chứng"]
~~~

Ví dụ, khi build một ứng dụng Java:

- Mã nguồn được biên dịch thành các file .class.
- Tài nguyên được sao chép hoặc xử lý vào thư mục output.
- Mã nguồn được sinh tự động có thể được biên dịch cùng mã nguồn viết tay.
- Test source được biên dịch thành test classes.
- Test được chạy và tạo báo cáo.
- Các class và resource cần thiết được đóng gói thành JAR.
- JAR được kiểm tra cấu trúc, metadata hoặc checksum.
- CI có thể lưu JAR và báo cáo theo từng lần chạy.

Đầu ra của một task có thể trở thành đầu vào của task khác. Ví dụ, task biên dịch tạo class files; task đóng gói dùng class files và resources để tạo JAR. Vì vậy, một file trung gian vẫn rất quan trọng đối với tính đúng đắn của build, dù nó không phải sản phẩm được phát hành.

## 2. Đầu ra trung gian là gì?

Đầu ra trung gian là những file hoặc thư mục được tạo ra để hỗ trợ các bước tiếp theo trong build. Chúng thường có thể tái tạo từ source code, cấu hình, dependency và toolchain.

Trong một Gradle Java project, các ví dụ thường gặp gồm:

| Đầu ra trung gian | Task hoặc giai đoạn thường tạo ra | Mục đích |
|---|---|---|
| Generated source files | compile hoặc task sinh mã, annotation processor | Bổ sung source để biên dịch |
| Compiled classes | compileJava | Chuyển source Java thành class files |
| Processed resources | processResources | Sao chép hoặc xử lý resource |
| Test classes | compileTestJava | Tạo class phục vụ kiểm thử |
| Test working/output files | Task test hoặc task tùy biến | Phục vụ thực thi và kiểm tra test |
| Temporary files | Task tùy biến hoặc công cụ đóng gói | Dữ liệu tạm trong một bước xử lý |
| Transformed dependency artifacts | Dependency transforms | Chuẩn bị dependency cho cách sử dụng cụ thể |

Với cấu trúc mặc định phổ biến, một phần output có thể xuất hiện như sau:

~~~text
orders-service/
└── build/
    ├── classes/
    │   └── java/
    │       ├── main/
    │       └── test/
    ├── generated/
    │   └── sources/
    ├── resources/
    │   └── main/
    └── tmp/
~~~

Đây là sơ đồ minh họa. Plugin hoặc build logic của dự án có thể dùng đường dẫn khác, tạo thêm thư mục hoặc không tạo một số thư mục nếu task tương ứng không chạy.

### 2.1. Generated sources và compiled classes

Một số dự án tạo source tự động từ schema, annotation processor, OpenAPI specification hoặc dữ liệu cấu hình. Source được sinh ra thường nằm trong thư mục build thay vì thư mục source do người phát triển quản lý.

Ví dụ:

- Annotation processor tạo class hỗ trợ dependency injection hoặc mapping.
- Một task sinh Java model từ schema.
- Một task tạo source từ file metadata.
- Gradle compile các source được khai báo trong source set.

Source sinh tự động là đầu ra của một task và có thể là đầu vào của compileJava. Không nên sửa trực tiếp file đã sinh để khắc phục lỗi, vì lần build tiếp theo có thể tạo lại và ghi đè thay đổi. Hãy sửa source gốc, schema, cấu hình hoặc task chịu trách nhiệm sinh file.

Class files trong **build/classes/java/main** cũng là đầu ra trung gian. Chúng được dùng bởi test, packaging hoặc các task khác. Thông thường, nhóm không cần commit các file .class này vào Git vì chúng có thể được tạo lại từ source và toolchain phù hợp.

### 2.2. Processed resources

Resource trong **src/main/resources** có thể được sao chép hoặc xử lý trước khi đưa vào classpath và JAR. Ví dụ, build có thể thay placeholder bằng giá trị cấu hình hoặc tạo file resource từ template.

Cần phân biệt:

- Resource nguồn: file do nhóm quản lý.
- Processed resource: kết quả do build tạo.
- Resource nằm trong artifact: nội dung thực tế được đóng gói để ứng dụng sử dụng.

Ba thứ này có thể giống nhau về tên nhưng khác nhau về nội dung. Khi ứng dụng chạy sai cấu hình, kiểm tra file nguồn chưa chắc đã đủ; cần xem processed resource hoặc nội dung thực tế trong JAR.

### 2.3. Test classes và dữ liệu tạm

Test code thường được biên dịch riêng với production code. Gradle Java plugin tổ chức source set main và test; các plugin khác có thể bổ sung integration test hoặc source set riêng.

Test output, file tạm, log của test hoặc dữ liệu do test tạo ra có thể hữu ích khi điều tra lỗi. Tuy nhiên, chúng không mặc nhiên là artifact phát hành. Cần xác định file nào là output có ý nghĩa, file nào chỉ là trạng thái tạm và file nào chứa dữ liệu nhạy cảm.

### 2.4. Vì sao đầu ra trung gian cần được khai báo chính xác?

Gradle sử dụng mô hình task input/output để xác định một task có cần thực thi lại hay không. Nếu task đọc một file nhưng không khai báo file đó là input, Gradle có thể không nhận ra rằng dữ liệu đã thay đổi. Khi đó, output cũ có thể bị tái sử dụng không đúng.

Với task tùy biến, cần dùng các property và annotation phù hợp như:

- @Input cho giá trị đầu vào.
- @InputFile hoặc @InputFiles cho file đầu vào.
- @OutputFile hoặc @OutputDirectory cho đầu ra.
- Các kiểu property chuyên biệt như RegularFileProperty và DirectoryProperty khi viết task theo Gradle API.

Ví dụ minh họa:

~~~groovy
abstract class GenerateVersionFile extends DefaultTask {
    @Input
    abstract Property<String> getVersion()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = 'version=' + version.get() + '\n'
    }
}
~~~

Ví dụ này thể hiện ý tưởng khai báo một giá trị input và một file output. Task thực tế còn cần được đăng ký, cấu hình và tích hợp với các task tiêu thụ file đó. Khi input thay đổi, Gradle có thể xác định output cần được cập nhật theo contract đã khai báo.

Khai báo chính xác giúp incremental build và build cache hoạt động đáng tin cậy. Nó cũng giúp người đọc hiểu file nào được tạo từ dữ liệu nào.

## 3. Artifact cuối cùng là gì?

Artifact cuối cùng là sản phẩm build được đóng gói để chuyển sang một mục đích sử dụng tiếp theo. Tùy loại module, artifact có thể là:

- JAR của Java library.
- Executable JAR của ứng dụng Spring Boot.
- WAR nếu ứng dụng được đóng gói theo mô hình triển khai tương ứng.
- ZIP hoặc TAR chứa distribution.
- Một gói chứa binary và file cấu hình phục vụ runtime.
- Container image hoặc một gói triển khai được tạo bởi pipeline phù hợp.

Artifact không nhất thiết là một file duy nhất. Một distribution có thể gồm JAR, script khởi động, file cấu hình mẫu và thư viện đi kèm. Một pipeline triển khai container có thể tạo image và metadata liên quan.

Điểm quan trọng là artifact phải có danh tính và mục đích rõ ràng: nó thuộc project nào, được tạo từ phiên bản source nào, dành cho môi trường nào và được tạo bởi task nào.

### 3.1. JAR thông thường và executable JAR

Với Java plugin, task jar đóng gói output của source set chính thành JAR. Với Spring Boot Gradle plugin, task bootJar có thể tạo executable JAR chứa ứng dụng cùng các dependency runtime theo cấu trúc mà Spring Boot Loader sử dụng.

Ví dụ cấu trúc thường thấy của executable Spring Boot JAR:

~~~text
orders-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
├── BOOT-INF/
│   ├── classes/
│   └── lib/
└── ...
~~~

JAR thông thường của library có thể chứa package class và resource trực tiếp ở cấp gốc, cùng metadata trong META-INF/. Vì vậy, hai file đều có đuôi .jar nhưng không nhất thiết có cùng mục đích hoặc cách chạy.

Không nên suy luận loại artifact chỉ từ tên file. Hãy xem task tạo ra nó, cấu hình packaging và cấu trúc bên trong.

### 3.2. Artifact cuối cùng phải gắn với đúng đầu vào

Một file có tên orders-service.jar chưa đủ chứng minh đó là artifact của commit đang kiểm tra. File có thể còn sót từ lần build trước hoặc được copy từ một thư mục khác.

Để xác định artifact, cần liên kết nó với các thông tin như:

- Project/module tạo artifact.
- Source revision hoặc commit.
- Phiên bản ứng dụng.
- Gradle task và cấu hình đã tạo artifact.
- Dependency resolution hoặc lock state.
- JDK/toolchain và môi trường build khi cần.
- Checksum của file sau khi tạo.

Các thông tin này giúp tránh việc phát hành nhầm artifact cũ, nhầm module hoặc nhầm biến thể.

### 3.3. Không dùng wildcard thay cho việc xác định artifact

Lệnh như:

~~~bash
cp build/libs/*.jar release/
~~~

có thể copy nhiều file nếu thư mục chứa JAR chính, JAR phụ, JAR có classifier hoặc output từ lần build trước. Kết quả phụ thuộc vào nội dung thư mục tại thời điểm chạy.

Khi cần lưu artifact, hãy xác định output cụ thể từ task hoặc cấu hình của dự án. Trong Gradle build logic, có thể lấy archive output từ task provider thay vì tự ghép đường dẫn hoặc tìm file bằng wildcard. Ở CI, hãy lưu đúng file đã được build và kiểm tra trong chính lần chạy đó.

## 4. Báo cáo kiểm chứng là gì?

Báo cáo kiểm chứng lưu lại bằng chứng về kết quả của những bước xác minh. Chúng giúp trả lời câu hỏi: build đã kiểm tra những gì, kiểm tra trên đầu vào nào và kết quả ra sao?

Các loại báo cáo thường gặp:

| Báo cáo hoặc bằng chứng | Nội dung | Dùng để làm gì |
|---|---|---|
| Test report HTML | Tổng hợp test, trạng thái, lỗi và stack trace | Người phát triển xem và điều tra test |
| Test result XML | Kết quả test dạng máy đọc được | CI, dashboard và công cụ phân tích |
| Coverage report | Mức độ code được test thực thi | Hiểu phạm vi kiểm thử |
| Static analysis report | Vi phạm quy tắc hoặc vấn đề code | Đánh giá chất lượng tĩnh |
| Dependency report | Dependency graph và phiên bản được chọn | Điều tra xung đột hoặc thay đổi dependency |
| Build log | Task, thông báo và lỗi trong quá trình build | Tái hiện và chẩn đoán |
| Checksum file | Hash của artifact | Phát hiện file thay đổi ngoài dự kiến |
| Build scan hoặc build metadata | Task timeline, môi trường, dependency và hiệu năng | Phân tích build sâu hơn |

Báo cáo thường là output của task, nhưng không phải artifact runtime. Ví dụ, test report không được đóng vào executable JAR để ứng dụng chạy. Nó phục vụ người phát triển, CI hoặc quy trình kiểm soát chất lượng.

### 4.1. Test report

Với Gradle Java plugin, task test thường tạo báo cáo HTML và kết quả XML dưới thư mục build của project. Đường dẫn mặc định phổ biến là:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-*.xml
        └── ...
~~~

Đường dẫn có thể thay đổi theo cấu hình hoặc plugin. HTML phù hợp cho người đọc; XML phù hợp để CI và công cụ khác xử lý.

Khi test thất bại, báo cáo có thể cho biết:

- Test class hoặc test method nào thất bại.
- Assertion mong đợi và giá trị thực tế.
- Exception và stack trace.
- Test nào pass, fail hoặc bị bỏ qua.
- Tổng thời gian thực thi.

Không nên chỉ nhìn dòng BUILD FAILED để kết luận nguyên nhân. Hãy xác định task thất bại, mở test report và tìm lỗi gốc. Nếu build dừng trước khi task test chạy, có thể không có báo cáo test mới; điều đó khác với trường hợp test đã chạy và pass.

### 4.2. Coverage và static analysis

Coverage report cho biết test đã thực thi những phần code nào theo công cụ coverage đang dùng. Coverage cao không tự chứng minh test có assertion tốt hoặc bao phủ đầy đủ tình huống nghiệp vụ. Nó là một góc nhìn bổ sung, không phải chứng nhận chất lượng tuyệt đối.

Static analysis report có thể ghi nhận lỗi định dạng, vi phạm coding rule, bug pattern hoặc vấn đề bảo mật tiềm ẩn tùy công cụ. Các task này thường được gắn vào lifecycle verification của dự án. Báo cáo cần được đọc cùng cấu hình rule và mức độ nghiêm trọng; một cảnh báo không tự động có cùng ý nghĩa với lỗi làm build thất bại.

### 4.3. Dependency và build reports

Dependency report cho thấy các dependency trực tiếp và bắc cầu được resolve. Nó hữu ích khi:

- Một thư viện đổi phiên bản ngoài dự kiến.
- Có xung đột version.
- Một dependency được kéo vào bởi plugin hoặc module khác.
- Cần giải thích khác biệt giữa hai môi trường.

Build scan hoặc metadata tương tự có thể cung cấp timeline task, cache outcome, dependency resolution và thông tin môi trường. Nếu dữ liệu được gửi tới dịch vụ bên ngoài, cần tuân theo chính sách chia sẻ dữ liệu của tổ chức.

### 4.4. Checksum và bằng chứng toàn vẹn

Checksum là giá trị hash được tính từ nội dung file, ví dụ SHA-256. Nó giúp xác nhận hai bản sao có cùng nội dung nếu hash được so sánh với một giá trị tham chiếu đáng tin cậy.

~~~bash
sha256sum build/libs/orders-service.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\build\libs\orders-service.jar -Algorithm SHA256
~~~

Checksum không tự chứng minh ai đã tạo file hoặc file đến từ một pipeline đáng tin cậy. Nếu kẻ tấn công có thể thay cả artifact lẫn file checksum, hai thứ vẫn có thể khớp nhau. Để xác minh nguồn gốc mạnh hơn, pipeline có thể bổ sung chữ ký, provenance hoặc attestation theo hệ thống phát hành của tổ chức.

## 5. Quan hệ giữa đầu ra trung gian, artifact và báo cáo

Ba nhóm đầu ra có thể liên hệ với nhau như sau:

| Đặc điểm | Đầu ra trung gian | Artifact cuối cùng | Báo cáo kiểm chứng |
|---|---|---|---|
| Mục đích | Cung cấp dữ liệu cho task khác | Phân phối hoặc sử dụng sản phẩm | Chứng minh và giải thích kết quả kiểm tra |
| Ví dụ | Generated source, class files, processed resources | JAR, WAR, ZIP, image | Test report, coverage, static analysis, log |
| Người/tiến trình tiêu thụ | Task tiếp theo trong build graph | Runtime, người dùng, hệ thống triển khai | Developer, CI, reviewer, auditor |
| Có thể tạo lại? | Thường có, từ input và task | Thường có, nếu input và môi trường được kiểm soát | Thường có khi chạy lại bước kiểm chứng |
| Có nên phát hành? | Thường không | Có, nếu vượt qua điều kiện phát hành | Lưu theo chính sách CI; không đóng chung vào runtime artifact trừ khi có mục đích |
| Chính sách lưu trữ | Thường có thể xóa và tạo lại | Lưu theo vòng đời release | Lưu đủ lâu để điều tra và kiểm toán |

Có những trường hợp ranh giới không tuyệt đối. Ví dụ, một file JSON do task tạo ra có thể là output trung gian ở một bước nhưng trở thành artifact đầu vào cho một pipeline khác. Một báo cáo SBOM có thể được phát hành kèm artifact vì nó mô tả thành phần phần mềm. Điều quyết định là hợp đồng sử dụng: ai tiêu thụ file đó, vì mục đích gì và yêu cầu lưu giữ ra sao.

## 6. Gradle quản lý các nhóm đầu ra như thế nào?

Gradle mô hình hóa công việc bằng task. Mỗi task có thể khai báo input, output và quan hệ phụ thuộc. Build graph kết nối các task để Gradle biết thứ tự thực thi cần thiết.

Với Java plugin, một số task phổ biến gồm:

| Task | Vai trò |
|---|---|
| compileJava | Biên dịch source Java chính |
| processResources | Xử lý resource chính |
| classes | Gom các bước tạo output chính |
| compileTestJava | Biên dịch test source |
| processTestResources | Xử lý test resource |
| test | Chạy test và tạo test result/report |
| jar | Đóng gói output chính thành JAR |
| check | Gom các bước verification đã được cấu hình |
| assemble | Gom các bước tạo artifact |
| build | Lifecycle task kết hợp verification và assembly |

Task thực tế phụ thuộc plugin và cấu hình. Spring Boot plugin có thể bổ sung bootJar; plugin khác có thể thêm task cho integration test, coverage, static analysis hoặc distribution.

Trong Java plugin, build thường phụ thuộc vào check và assemble. Điều này giúp một lệnh lifecycle có thể vừa chạy kiểm chứng vừa tạo artifact. Tuy vậy, hãy kiểm tra task graph của dự án thay vì giả định mọi repository đều có cùng cấu hình.

### 6.1. Một số lệnh quan sát hữu ích

Liệt kê task của project:

~~~bash
./gradlew :orders-service:tasks --all
~~~

Xem task graph dự kiến mà không thực thi:

~~~bash
./gradlew :orders-service:build --dry-run
~~~

Chạy build và lấy thêm thông tin khi cần chẩn đoán:

~~~bash
./gradlew :orders-service:build --info --stacktrace
~~~

Xem dependency của runtime classpath:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

Các lệnh này giúp xác định task và dependency trước khi kết luận output nào sẽ được tạo. Tham số --dry-run chỉ hiển thị task dự kiến; nó không tạo artifact hoặc chứng minh build thành công.

### 6.2. Xem artifact thực tế

Sau khi build, có thể liệt kê các file trong thư mục output:

~~~powershell
Get-ChildItem -LiteralPath .\module\orders-service\build\libs -File
~~~

Đường dẫn trên chỉ là ví dụ; hãy điều chỉnh theo vị trí project thực tế. Sau đó kiểm tra cấu trúc JAR:

~~~bash
jar tf path/to/orders-service.jar
~~~

Có thể đọc manifest:

~~~bash
unzip -p path/to/orders-service.jar META-INF/MANIFEST.MF
~~~

Với executable Spring Boot JAR, kiểm tra sự hiện diện của BOOT-INF/classes và BOOT-INF/lib nếu cấu hình đóng gói dự kiến tạo cấu trúc đó. Với library JAR, hãy kiểm tra package, class và resource cần cung cấp cho consumer.

Không nên chỉ kiểm tra file có tồn tại. Hãy xác nhận nó được tạo bởi task đúng, thuộc module đúng và có nội dung đúng với mục đích sử dụng.

## 7. Lifecycle build, assemble và check

Ba lifecycle task thường gây nhầm lẫn:

- **assemble** tập trung vào việc tạo các artifact.
- **check** tập trung vào các bước kiểm chứng.
- **build** thường kết hợp cả check và assemble.

Ví dụ:

~~~bash
./gradlew :orders-service:assemble
./gradlew :orders-service:check
./gradlew :orders-service:build
~~~

Nếu chỉ chạy assemble, không thể kết luận rằng test và các bước verification đã pass. Nếu chỉ chạy check, có thể chưa có artifact cuối cùng cần giao. Build thường là entry point tổng quát hơn, nhưng kết quả vẫn phụ thuộc các task đã được gắn vào lifecycle.

Một task có thể có outcome như:

- **SUCCESS:** task thực thi và hoàn tất.
- **UP-TO-DATE:** Gradle xác định output hiện tại đã phù hợp với input đã khai báo.
- **FROM-CACHE:** Gradle phục hồi output từ build cache.
- **SKIPPED:** task không thực thi do điều kiện hoặc cấu hình.
- **NO-SOURCE:** không có source phù hợp để task xử lý.
- **FAILED:** task thất bại.

UP-TO-DATE và FROM-CACHE là các outcome hợp lệ trong build tối ưu; chúng không đồng nghĩa với việc task đã chạy lại trong lần này. Khi đọc kết quả, cần hiểu task đã được thực thi hay output được tái sử dụng, và xác nhận output tương ứng vẫn là đầu ra cần dùng.

## 8. Kiểm chứng artifact theo một quy trình có thể tái hiện

Một quy trình xác minh nên đi từ phạm vi build đến nội dung artifact và bằng chứng kiểm tra.

### Bước 1: Ghi nhận đầu vào

Ghi lại commit, project path, JDK/toolchain, Gradle Wrapper, tham số build và các biến cấu hình có ảnh hưởng. Không ghi giá trị secret vào log.

~~~bash
git rev-parse --short HEAD
java -version
./gradlew --version
~~~

### Bước 2: Chạy đúng lifecycle task

Ví dụ với một module ứng dụng có task bootJar:

~~~bash
./gradlew :orders-service:clean :orders-service:build
~~~

Nếu yêu cầu cần kiểm tra riêng executable JAR, xác nhận task bootJar nằm trong task graph hoặc chạy task đó theo cấu hình của dự án. Với library, task đóng gói có thể là jar.

clean xóa output build của project và hữu ích khi cần xác minh từ trạng thái sạch. Không nhất thiết phải chạy clean trước mọi build hằng ngày; incremental build là một phần bình thường của Gradle.

### Bước 3: Xem kết quả kiểm chứng

Mở test report, static analysis report hoặc coverage report nếu các task tương ứng đã được cấu hình và chạy. Xác định test nào pass, fail hoặc bị skip. Nếu build dừng trước bước test, ghi nhận rằng không có kết quả test mới thay vì coi đó là pass.

### Bước 4: Kiểm tra artifact

Xác định đúng file output, kiểm tra kích thước, cấu trúc, manifest và resource cần thiết. Nếu artifact phải chạy được, thực hiện smoke test trong môi trường thử nghiệm phù hợp. Smoke test chỉ xác minh một số hành vi cơ bản; nó không thay thế bộ test đầy đủ.

### Bước 5: Tính checksum và lưu metadata

Nếu cần kiểm tra tính toàn vẹn hoặc so sánh hai lần build, tạo checksum và lưu cùng thông tin commit, phiên bản công cụ và đường dẫn artifact. Nếu cần chứng minh nguồn gốc phát hành, dùng cơ chế chữ ký hoặc provenance của pipeline.

### Bước 6: Lưu bằng chứng

Lưu artifact và báo cáo theo cùng một định danh lần chạy hoặc release. Khi có lỗi, lưu log và test report ngay cả khi bước publish không diễn ra. Người khác cần có thể xác định báo cáo thuộc build nào và artifact nào.

## 9. Xử lý khi build thất bại giữa chừng

Không phải mọi lần build đều tạo đủ ba nhóm output. Nếu compileJava thất bại, có thể không có class output mới. Nếu compile thành công nhưng test thất bại, class files có thể tồn tại và test report có thể cho biết lỗi. Nếu packaging thất bại, một số intermediate outputs vẫn còn nhưng artifact cuối cùng có thể không tồn tại hoặc không hoàn chỉnh.

Vì vậy, cần phân biệt:

- **Output đã được tạo:** file tồn tại trong thư mục build.
- **Output hợp lệ:** file phản ánh đúng input và task đã hoàn tất theo contract.
- **Artifact được chấp nhận:** sản phẩm đã vượt qua các điều kiện kiểm chứng cần thiết để chuyển tiếp.
- **Artifact đã phát hành:** file đã được đưa vào nơi phân phối theo quy trình release.

Một file tồn tại không đồng nghĩa với artifact hợp lệ. Nếu task đóng gói thất bại, không nên lấy một file cùng tên từ thư mục output rồi mặc định đó là kết quả mới. Hãy xác định timestamp, task outcome, checksum và mối liên hệ với lần chạy hiện tại.

Trong CI, nên cấu hình lưu test report và log ngay cả khi build job thất bại, trong khi bước publish artifact chỉ chạy khi các điều kiện bắt buộc đã pass. Cách này giữ được bằng chứng điều tra mà không phát hành sản phẩm chưa được xác minh.

## 10. Lưu trữ và dọn dẹp đầu ra đúng cách

Không phải file nào trong build/ cũng cần lưu lâu dài. Chính sách phù hợp phụ thuộc mục đích:

| Loại đầu ra | Chính sách thường dùng |
|---|---|
| Class files, generated temporary files | Có thể xóa và tạo lại từ build |
| Intermediate processed resources | Giữ trong workspace khi cần; thường không phát hành |
| Local test reports | Giữ đủ lâu để developer điều tra |
| CI test/verification reports | Lưu theo retention policy của CI |
| Release artifact | Lưu theo vòng đời phát hành và chính sách phân phối |
| Checksum, signature, provenance | Lưu cùng artifact hoặc trong hệ thống phát hành đáng tin cậy |
| Log có thể chứa thông tin nhạy cảm | Giới hạn quyền truy cập và thời gian lưu |

Một số lưu ý:

- Không commit thư mục build/ nếu repository không có chủ đích quản lý những file đó.
- Không xóa intermediate output trong khi task khác đang sử dụng chúng.
- Không dùng output của lần chạy trước để thay thế kết quả hiện tại khi chưa xác minh.
- Không xóa báo cáo lỗi trước khi đã thu thập bằng chứng cần thiết.
- Không lưu report và artifact ở cùng một nơi mà thiếu định danh hoặc quy tắc phân biệt.
- Dùng retention policy phù hợp với dung lượng, nhu cầu điều tra và yêu cầu kiểm toán.

clean thường xóa thư mục build của project. Nó hữu ích để tạo lại output từ đầu, nhưng nếu dùng không đúng lúc có thể làm mất báo cáo hoặc file cần cho điều tra. Trước khi dọn dẹp một build thất bại, hãy lưu những bằng chứng cần thiết.

## 11. Artifact và báo cáo trong CI/CD

CI/CD cần phân biệt rõ giai đoạn tạo sản phẩm và giai đoạn xác minh sản phẩm. Một pipeline có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Build intermediate outputs"]
    B --> C["Run tests and checks"]
    C --> D{"Verification passed?"}
    D -->|No| E["Archive logs and reports"]
    D -->|Yes| F["Package final artifact"]
    F --> G["Inspect and calculate checksum"]
    G --> H["Archive artifact and metadata"]
    H --> I["Publish or deploy"]
~~~

Một số pipeline đóng gói artifact trước hoặc trong lúc chạy test vì task graph cho phép các bước này cùng thuộc một lifecycle. Dù tổ chức theo cách nào, điều kiện phát hành phải dựa trên kết quả verification đã được xác định.

CI nên lưu các loại output theo cách có thể truy nguyên:

- Artifact gắn với commit hoặc pipeline run.
- Test report gắn với cùng lần chạy.
- Log và metadata môi trường.
- Checksum hoặc chữ ký nếu quy trình yêu cầu.
- Trạng thái kiểm chứng rõ ràng.

Nếu build fail, pipeline vẫn nên giữ lại log và report đã được tạo. Nếu build pass, artifact được lưu và chuyển sang bước publish theo điều kiện. Việc này giúp tránh nhầm lẫn giữa “đã tạo file” và “được phép phát hành file”.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế cần hiểu |
|---|---|
| File trong build/ nào cũng là artifact phát hành | Phần lớn có thể là intermediate output hoặc report |
| JAR tồn tại nghĩa là build thành công | JAR có thể cũ, sai module hoặc không hoàn chỉnh |
| BUILD SUCCESSFUL chứng minh ứng dụng chạy đúng | Nó chỉ phản ánh các task trong build invocation đã hoàn tất theo cấu hình |
| test không xuất hiện trong log là test đã pass | Test có thể chưa chạy hoặc bị skip |
| Test report là một phần của executable JAR | Thông thường report nằm riêng để phục vụ kiểm chứng |
| Checksum chứng minh nguồn gốc artifact | Checksum chỉ so sánh nội dung với giá trị tham chiếu; nguồn gốc cần bằng chứng bổ sung |
| Có thể xóa mọi file build/ ngay sau khi lỗi | Báo cáo và log có thể cần để điều tra |
| assemble và check có cùng mục đích | Một bên tạo artifact, bên kia chạy verification |
| Wildcard luôn chọn đúng artifact mới nhất | Có thể chọn nhiều file hoặc file cũ |

## 13. Ví dụ tổng hợp cho một module Java

Giả sử project orders-service có Java plugin và Spring Boot plugin. Một lần build có thể tạo ra:

~~~text
module/orders-service/build/
├── classes/
│   └── java/
│       ├── main/
│       └── test/
├── generated/
│   └── sources/
├── resources/
│   └── main/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
├── test-results/
│   └── test/
│       └── TEST-*.xml
└── libs/
    ├── orders-service.jar
    └── orders-service-boot.jar
~~~

Tên file trong ví dụ chỉ mang tính minh họa; output thực tế phụ thuộc cấu hình archive name, version, classifier và task. Một project cũng không nhất thiết tạo đồng thời cả hai JAR.

Khi nhận kết quả, người phát triển có thể phân loại:

- classes/, generated/, resources/: intermediate outputs.
- JAR được chọn để chạy hoặc phân phối: final artifact.
- reports/tests/ và test-results/: verification reports.

Sau đó, kiểm tra đúng JAR theo mục đích. Nếu module là ứng dụng Spring Boot, executable JAR thường là output của bootJar. Nếu module là library, JAR từ jar thường là sản phẩm cần cung cấp cho consumer. Không lấy cả hai và đặt tên chung chung nếu chưa có quy ước phân biệt.

## 14. Checklist xác định và sử dụng đầu ra

Khi hoàn tất một build, hãy xác nhận:

- [ ] Biết task nào tạo từng intermediate output quan trọng.
- [ ] Biết output nào là source do người viết quản lý và output nào được sinh tự động.
- [ ] Các task tùy biến đã khai báo input/output chính xác.
- [ ] Xác định đúng artifact cuối cùng theo loại module và mục đích sử dụng.
- [ ] Artifact được liên kết với đúng project, source revision và lần chạy.
- [ ] Đã kiểm tra cấu trúc hoặc nội dung artifact theo yêu cầu.
- [ ] Test và verification reports thuộc đúng lần build.
- [ ] Đã phân biệt PASS, FAILED, SKIPPED, UP-TO-DATE và FROM-CACHE.
- [ ] Khi build thất bại, đã lưu log và báo cáo cần thiết trước khi dọn output.
- [ ] Artifact chỉ được publish sau khi điều kiện verification đã đạt.
- [ ] Checksum, signature hoặc provenance được lưu nếu quy trình phát hành yêu cầu.
- [ ] Có retention policy phù hợp cho intermediate outputs, reports và release artifacts.

## Kết luận

Đầu ra trung gian, artifact cuối cùng và báo cáo kiểm chứng đều được tạo trong quy trình build, nhưng phục vụ những mục đích khác nhau. Intermediate outputs giúp các task tiếp theo thực hiện công việc; final artifacts là sản phẩm được chạy hoặc phân phối; verification reports lưu bằng chứng về chất lượng và kết quả kiểm tra.

Khi phân biệt đúng ba nhóm, nhóm phát triển biết file nào có thể tạo lại, file nào cần kiểm tra trước khi phát hành và file nào cần lưu để điều tra. Gradle cung cấp task graph cùng mô hình input/output để quản lý các bước tạo output; CI giúp lưu artifact và báo cáo theo từng lần chạy. Kết hợp hai phần này với quy tắc định danh, xác minh và lưu trữ rõ ràng sẽ làm cho kết quả build dễ kiểm chứng và dễ truy nguyên hơn.

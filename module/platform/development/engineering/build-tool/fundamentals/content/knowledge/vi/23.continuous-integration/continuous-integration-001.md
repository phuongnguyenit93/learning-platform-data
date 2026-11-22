# Vai trò của CI trong việc kiểm chứng một thay đổi mã nguồn

Khi lập trình viên tạo một thay đổi mã nguồn, việc mã chạy được trên máy cá nhân mới chỉ là bước kiểm tra ban đầu. Môi trường local có thể đã có dependency trong cache, dùng JDK khác với môi trường phát hành, chứa file generated chưa được commit hoặc có cấu hình riêng của IDE. Một thay đổi cũng có thể ảnh hưởng đến module khác, làm hỏng test tích hợp hoặc vi phạm quy tắc chất lượng mà người viết chưa chạy.

Continuous Integration (CI) đưa thay đổi vào một quy trình build và kiểm chứng tự động, thường chạy trên môi trường sạch sau khi có commit hoặc pull request. CI lấy đúng source revision, thiết lập toolchain, resolve dependency, compile, chạy test và các kiểm tra đã được nhóm thống nhất. Kết quả được gửi lại dưới dạng trạng thái pass/fail, log và báo cáo để nhóm quyết định có thể review, merge hoặc phát hành thay đổi hay không.

CI không tự chứng minh chương trình hoàn toàn đúng. Giá trị của CI nằm ở việc áp dụng cùng một quy trình kiểm tra cho mọi thay đổi, phát hiện lỗi sớm, tạo bằng chứng có thể truy vết và ngăn thay đổi chưa đạt điều kiện đi tiếp trong quy trình phát triển.

## 1. Continuous Integration là gì?

Continuous Integration là thực hành tích hợp các thay đổi mã nguồn thường xuyên vào một nhánh chung và tự động kiểm tra chúng bằng build/test pipeline. Mỗi lần có thay đổi phù hợp, hệ thống CI có thể checkout source, chạy build và báo kết quả cho nhóm.

~~~mermaid
flowchart TD
    A["Lập trình viên commit thay đổi"] --> B["Push branch hoặc mở pull request"]
    B --> C["CI nhận sự kiện"]
    C --> D["Checkout đúng revision"]
    D --> E["Thiết lập JDK và build tool"]
    E --> F["Compile và kiểm tra"]
    F --> G["Unit / integration tests"]
    G --> H["Phân tích và lưu báo cáo"]
    H --> I{"Các required checks đạt?"}
    I -->|Không| J["Trả trạng thái fail và chi tiết lỗi"]
    I -->|Có| K["Cho phép review/merge theo chính sách"]
~~~

CI thường được tích hợp với hệ thống quản lý source như GitHub, GitLab, Bitbucket hoặc Azure DevOps. Pipeline được kích hoạt bởi push, pull request, merge request, tag hoặc lịch chạy định kỳ.

### 1.1. CI giải quyết những vấn đề nào?

- Phát hiện lỗi compile và test ngay sau khi thay đổi được gửi lên.
- Xác nhận source trong repository có thể build trên môi trường được kiểm soát.
- Kiểm tra ảnh hưởng của thay đổi đến module hoặc consumer khác.
- Áp dụng cùng formatter, static analysis, test và security checks cho mọi thay đổi.
- Cung cấp log/report để reviewer hiểu kết quả thay đổi.
- Ngăn merge khi required checks chưa đạt.
- Tạo dấu vết về commit, môi trường và artifact được tạo.

Nếu không có CI, nhóm thường dựa vào việc từng lập trình viên tự chạy một tập lệnh khác nhau. Điều đó làm kết quả phụ thuộc vào thói quen và môi trường cá nhân, đồng thời khiến lỗi tích hợp chỉ xuất hiện muộn.

### 1.2. CI và Continuous Delivery/Deployment

CI tập trung vào việc tích hợp và kiểm chứng thay đổi. Continuous Delivery mở rộng quy trình để sản phẩm sau khi kiểm chứng có thể được đóng gói và sẵn sàng phát hành. Continuous Deployment tự động đưa thay đổi đã đạt điều kiện lên môi trường đích theo chính sách.

| Thực hành | Trọng tâm |
|---|---|
| Continuous Integration | Tích hợp thường xuyên và tự động kiểm chứng thay đổi |
| Continuous Delivery | Duy trì khả năng phát hành sản phẩm sau khi các kiểm tra đạt |
| Continuous Deployment | Tự động triển khai thay đổi đủ điều kiện lên môi trường đã chọn |

Một pipeline có thể thực hiện CI mà không tự deploy production. Việc deploy cần thêm kiểm soát môi trường, quyền truy cập, approval, rollback và quan sát sau triển khai.

## 2. CI kiểm chứng một thay đổi ở những thời điểm nào?

Pipeline thường được thiết kế theo sự kiện để đưa phản hồi đến đúng thời điểm.

### 2.1. Khi push commit

Khi lập trình viên push một commit lên branch, CI có thể chạy build và test cho revision mới. Điều này giúp phát hiện lỗi sớm trước khi tạo pull request hoặc trước khi merge vào nhánh chung.

### 2.2. Khi mở hoặc cập nhật pull request

Pull request là điểm quan trọng để kiểm tra thay đổi trong ngữ cảnh tích hợp. CI có thể chạy trên head commit của pull request, hoặc trên một merge result giả lập giữa branch nguồn và branch đích tùy nền tảng.

Hai cách này trả lời các câu hỏi khác nhau:

- Kiểm tra head commit xác nhận riêng nội dung branch nguồn.
- Kiểm tra merge result giúp phát hiện vấn đề chỉ xuất hiện khi kết hợp với branch đích hiện tại.

Nền tảng có thể tạo merge commit tạm thời để chạy CI. Cần biết pipeline đang kiểm tra revision nào và hiển thị SHA đó trong log/report.

### 2.3. Khi merge vào nhánh chính

Sau khi merge, pipeline trên nhánh chính xác nhận trạng thái tích hợp thực tế. Kết quả pull request trước merge không thay thế hoàn toàn build sau merge, vì branch đích có thể đã thay đổi hoặc quá trình merge tạo ra một revision mới.

### 2.4. Khi tạo tag hoặc release

Release pipeline thường chạy lại các kiểm tra cần thiết trên tag hoặc commit phát hành, tạo artifact và lưu metadata. Việc phát hành nên gắn với một revision xác định để có thể truy vết artifact về source.

### 2.5. Chạy theo lịch

Một số kiểm tra không cần chạy trên mọi commit, ví dụ full integration test tốn nhiều thời gian, kiểm tra tương thích với nhiều JDK hoặc OS, dependency vulnerability scan toàn diện, kiểm tra hiệu năng hoặc dependency update.

Pipeline định kỳ bổ sung cho kiểm tra pull request. Không nên dùng lịch chạy thay cho các kiểm tra nhanh cần thiết trước khi merge.

## 3. CI bắt đầu bằng checkout đúng source

Một pipeline chỉ có ý nghĩa nếu biết nó đang kiểm tra source nào.

Thông tin nên được ghi nhận:

- Repository và commit SHA.
- Branch/tag hoặc pull request number.
- Base revision và head revision nếu là pull request.
- Submodule commit nếu repository sử dụng submodule.
- Git LFS object nếu có.
- Trạng thái working tree sau checkout.

### 3.1. Checkout sạch

CI runner thường checkout source vào workspace mới hoặc workspace được làm sạch trước khi chạy. Điều này giúp tránh phụ thuộc vào file chưa commit hoặc output cũ từ lần build trước.

Checkout sạch không tự bảo đảm toàn bộ môi trường sạch: dependency cache, tool cache, Docker image hoặc remote service có thể vẫn được tái sử dụng. Tuy nhiên, source tree nên phản ánh đúng revision được yêu cầu.

### 3.2. Submodule và Git LFS

Nếu repository sử dụng Git submodule, pipeline cần khởi tạo và checkout đúng commit submodule được tham chiếu. Nếu dùng Git LFS, pipeline cần tải đúng nội dung object thay vì chỉ lấy pointer file. Thiếu submodule hoặc LFS object có thể làm build thất bại hoặc khiến task xử lý sai dữ liệu.

### 3.3. Không kiểm tra nhầm revision

Trong pull request, một số nền tảng cung cấp ref đặc biệt đại diện cho merge result. Hãy ghi SHA thực tế được checkout trong log. Khi điều tra lỗi, so sánh revision CI chạy với revision mà reviewer nghĩ đang được kiểm tra.

## 4. Thiết lập môi trường build nhất quán

CI cần thiết lập build tool và JDK theo yêu cầu dự án. Nếu dùng Gradle hoặc Maven Wrapper, pipeline nên chạy Wrapper từ repository thay vì dựa vào bản cài toàn cục trên runner.

### 4.1. Gradle Wrapper

Gradle Wrapper giúp cố định Gradle distribution của dự án. Các file thường được commit gồm:

    gradlew
    gradlew.bat
    gradle/wrapper/gradle-wrapper.jar
    gradle/wrapper/gradle-wrapper.properties

Pipeline có thể chạy:

    ./gradlew --version
    ./gradlew clean check

Wrapper cố định Gradle version, nhưng JDK dùng để chạy Gradle và toolchain compile vẫn cần được thiết lập riêng.

### 4.2. Maven Wrapper

Maven Wrapper giúp dự án sử dụng Maven version được khai báo trong repository:

    ./mvnw --version
    ./mvnw --batch-mode clean verify

Trên Windows, pipeline có thể dùng mvnw.cmd. Wrapper giúp giảm khác biệt giữa máy cá nhân và CI do mỗi nơi cài một Maven version khác nhau.

### 4.3. JDK và Java toolchain

Pipeline nên chọn JDK vendor/version phù hợp với dự án. Cần phân biệt JDK chạy Gradle/Maven, JDK toolchain dùng để compile/test, Java release mà bytecode/API hướng tới và runtime Java dùng để chạy artifact trong môi trường đích.

Ví dụ, Gradle có thể chạy trên JDK 21 nhưng compile hướng tới Java 17:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }

Nếu local dùng JDK 21 nhưng CI dùng JDK 17, build có thể cho kết quả khác hoặc không khởi chạy được Gradle/plugin. Hãy ghi log java -version, javac -version và phiên bản Wrapper ở đầu pipeline.

### 4.4. Hệ điều hành và kiến trúc

Một pipeline dùng runner Linux có thể không phát hiện lỗi chỉ xảy ra trên Windows hoặc macOS. Các yếu tố như case sensitivity của filesystem, line endings, shell, quyền executable, native library và CPU architecture có thể ảnh hưởng build.

Nếu sản phẩm hỗ trợ nhiều môi trường, có thể dùng CI matrix để chạy các tổ hợp OS/JDK quan trọng. Không nhất thiết chạy mọi tổ hợp trên mọi commit; hãy chọn tập kiểm tra phù hợp với rủi ro và thời gian phản hồi.

## 5. Các bước kiểm chứng thường có trong pipeline Java

Một pipeline Java có thể bao gồm nhiều lớp kiểm tra. Mỗi lớp có mục tiêu và chi phí khác nhau.

| Bước | Mục tiêu | Ví dụ |
|---|---|---|
| Validate build configuration | Kiểm tra cấu hình và plugin | Gradle help, Maven validate |
| Compile | Phát hiện lỗi source/type/API | JavaCompile, Maven Compiler |
| Format check | Đảm bảo source theo formatter | Spotless check |
| Style/lint | Kiểm tra quy ước và mẫu code | Checkstyle, PMD |
| Static analysis | Tìm lỗi tiềm ẩn | SpotBugs, Error Prone, Sonar analyzers |
| Unit test | Kiểm tra hành vi đơn vị | JUnit |
| Integration test | Kiểm tra tương tác giữa thành phần | Testcontainers, test database |
| Coverage | Đo phần code được test thực thi | JaCoCo |
| Dependency/security scan | Phát hiện dependency có rủi ro | Dependency scanner, SBOM tooling |
| Package | Tạo artifact | JAR, WAR |

Không phải dự án nào cũng cần tất cả các bước trên ở mọi lần chạy. Điều quan trọng là nhóm xác định bước nào bắt buộc trước merge, bước nào chạy định kỳ và bước nào cần trước release.

### 5.1. Compile

Compile kiểm tra source có hợp lệ với compiler, classpath và Java release đã chọn hay không. Đây là phản hồi nhanh và thường nên chạy trên mọi pull request.

### 5.2. Unit test

Unit test kiểm tra các hành vi nhỏ với input và dependency được kiểm soát. CI nên chạy test và lưu report để biết test nào fail, assertion nào không đạt và stack trace liên quan.

### 5.3. Integration test

Integration test xác nhận các thành phần phối hợp, ví dụ ứng dụng với database, HTTP service, message broker hoặc file system. Test này có thể cần service container, credential hoặc dữ liệu fixture.

Nếu integration test tốn thời gian, có thể tách thành job riêng nhưng vẫn phải quyết định rõ test nào là required check trước merge và test nào chạy ở pipeline sâu hơn.

### 5.4. Static analysis và formatting

Formatter check, Checkstyle, PMD, SpotBugs hoặc Sonar analysis giúp phát hiện vấn đề mà compile/test có thể bỏ sót. Các rule và threshold cần được quản lý trong repository hoặc hệ thống quality profile để mọi lần chạy có chính sách nhất quán.

### 5.5. Coverage

JaCoCo có thể tạo báo cáo coverage và kiểm tra threshold. Coverage là tín hiệu về phần code được thực thi, không phải thước đo trực tiếp cho chất lượng assertion hoặc số bug còn lại. Nên xem coverage của code mới và kết hợp với test review.

### 5.6. Security và dependency checks

Dependency scan có thể phát hiện thư viện chứa lỗ hổng đã biết. Kết quả phụ thuộc database vulnerability, version dependency và policy của tổ chức. Nên lưu thời điểm scan, tool version và nguồn advisory để giải thích vì sao cùng source có thể có kết quả scan khác nhau ở các ngày khác nhau.

## 6. CI với Gradle

Gradle Java plugin cung cấp lifecycle task check để tập hợp các bước verification. Các plugin như Checkstyle, PMD, JaCoCo và Spotless có thể tạo task riêng và nối chúng vào check.

Một build script có thể cấu hình:

    plugins {
        id 'java'
        id 'checkstyle'
        id 'pmd'
        id 'jacoco'
        id 'com.diffplug.spotless' version '6.25.0'
    }

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
        options.release = 17
    }

    spotless {
        java {
            googleJavaFormat()
        }
    }

    tasks.named('check') {
        dependsOn('spotlessCheck')
    }

Đây là cấu hình minh họa; phiên bản plugin cần được chọn theo Gradle/JDK mà dự án hỗ trợ. Một số plugin tự nối task của mình vào check, vì vậy hãy kiểm tra task graph trước khi thêm dependency trùng lặp.

Chạy verification:

    ./gradlew clean check

Nếu cần đóng gói:

    ./gradlew clean build

Với Java plugin, build thường phụ thuộc vào check và assemble, nên build là điểm vào tổng hợp cho verification và packaging theo convention. Dự án có thể tùy chỉnh lifecycle, do đó cần xác nhận các task bắt buộc thực sự được nối vào.

### 6.1. Chạy task riêng để điều tra

Khi pipeline fail ở một bước, có thể chạy task tương ứng:

    ./gradlew test
    ./gradlew checkstyleMain
    ./gradlew jacocoTestReport
    ./gradlew dependencies --configuration runtimeClasspath

Task path có thể khác khi dự án nhiều module. Dùng project path rõ ràng, ví dụ :service:check hoặc :library:test.

### 6.2. Build scan và log

Gradle log ở mức info/debug có thể giúp hiểu task nào chạy, task nào up-to-date, task nào lấy từ cache và dependency nào được resolve. Build scan có thể cung cấp thông tin chi tiết hơn về task graph, thời gian và môi trường, tùy dịch vụ và cấu hình.

Trước khi publish build scan, cần xem chính sách dữ liệu của tổ chức vì scan có thể chứa tên project, đường dẫn, thông tin môi trường hoặc metadata build.

## 7. CI với Maven

Maven có default lifecycle với các phase như validate, compile, test, package, verify, install và deploy. Pipeline có thể chạy đến phase phù hợp để kích hoạt các plugin goals đã được gắn vào lifecycle.

Ví dụ:

    ./mvnw --batch-mode clean verify

Lệnh này chạy các phase trước và bao gồm verify trong default lifecycle. Nếu plugin chỉ được khai báo mà goal không được gắn vào phase hoặc không được gọi trực tiếp, nó có thể không chạy khi thực hiện lệnh này.

### 7.1. Vì sao thường dùng verify trong CI?

Verify là một phase thích hợp để chạy các bước xác minh bổ sung sau test/package, ví dụ integration checks, static analysis hoặc coverage verification. Dự án cần cấu hình plugin executions để các bước này thực sự chạy ở phase tương ứng.

### 7.2. Phân biệt verify, install và deploy

- verify: chạy các kiểm tra được gắn đến phase verify.
- install: cài artifact vào local Maven repository.
- deploy: publish artifact lên remote repository theo cấu hình.

CI pull request thường không cần deploy artifact production. Release pipeline mới thực hiện publish/deploy theo quyền và approval được kiểm soát.

### 7.3. Xem dependency graph và effective POM

Khi local và CI resolve dependency khác nhau, có thể dùng:

    ./mvnw dependency:tree -Dverbose
    ./mvnw help:effective-pom

Dependency tree cho biết dependency bắc cầu và version được chọn; effective POM giúp hiểu parent, profile, plugin và dependency management sau khi hợp nhất.

## 8. Thiết kế pipeline nhiều giai đoạn

Một pipeline không nhất thiết chạy mọi thứ trong một job. Có thể chia thành các stage hoặc job để phản hồi nhanh và cô lập môi trường.

~~~mermaid
flowchart TD
    A["Checkout"] --> B["Compile và format"]
    B --> C["Unit tests"]
    C --> D["Static analysis và coverage"]
    D --> E["Integration tests"]
    E --> F["Package artifact"]
    F --> G["Lưu artifact và reports"]
    G --> H["Release/deploy stage có kiểm soát"]
~~~

Ví dụ cách chia:

- Job nhanh: compile, format, unit test.
- Job phân tích: static analysis, coverage, dependency scan.
- Job tích hợp: database/service containers và integration tests.
- Job package: tạo JAR/WAR và lưu artifact.
- Job release: chỉ chạy từ tag hoặc nhánh được phép, có quyền publish/deploy.

Một job có thể phụ thuộc vào kết quả job khác. Nếu compile fail, không cần chạy integration test sử dụng artifact chưa được tạo. Tuy nhiên, nếu muốn thu thập nhiều loại finding cùng lúc, có thể cấu hình một số job chạy song song và tổng hợp kết quả sau.

## 9. CI matrix: kiểm tra nhiều JDK và hệ điều hành

CI matrix chạy cùng một job với nhiều tổ hợp giá trị. Ví dụ, một thư viện cần hỗ trợ Java 17 và 21 có thể có hai job tương ứng, mỗi job thiết lập một JDK rồi chạy cùng lệnh verification.

~~~yaml
strategy:
  matrix:
    java: [17, 21]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '21'
  - name: Verify
    run: ./gradlew clean check
~~~

Đây là ví dụ cấu trúc GitHub Actions; trong workflow thật, giá trị matrix cần được truyền vào java-version theo cú pháp expression của nền tảng. Nếu build tool chỉ chạy trên một số JDK, có thể tách JDK chạy Gradle khỏi toolchain compile.

Matrix hữu ích khi thư viện hỗ trợ nhiều Java release, ứng dụng chạy trên nhiều OS, có native code/platform-specific resource hoặc cần xác nhận tương thích với nhiều database/runtime.

Không nên tạo matrix quá lớn cho mọi pull request nếu chi phí cao. Có thể chạy một tổ hợp nhanh trên pull request và mở rộng matrix trên nhánh chính hoặc lịch định kỳ.

## 10. Required checks và branch protection

CI chỉ có tác dụng ngăn merge nếu kết quả pipeline được liên kết với quy tắc của repository. Một job có thể fail nhưng pull request vẫn merge được nếu branch protection không yêu cầu trạng thái đó.

Các khái niệm:

- **Status check:** trạng thái do CI job hoặc integration gửi về hệ thống quản lý source.
- **Required check:** status check bắt buộc phải thành công trước khi merge.
- **Branch protection/ruleset:** chính sách bảo vệ nhánh, quy định required checks, review và các điều kiện khác.

Một pull request có thể yêu cầu build và unit test pass, format/static analysis pass, required integration checks pass, review từ người có quyền và branch được cập nhật với trạng thái mới nhất của base branch.

Tên required check cần ổn định. Nếu đổi tên job trong workflow mà branch protection vẫn yêu cầu tên cũ, repository có thể chặn merge hoặc không áp dụng đúng kiểm tra mong muốn.

### 10.1. Tránh status check không đại diện cho công việc

Một job tổng hợp có thể báo success dù một job con bị bỏ qua ngoài ý muốn. Hãy kiểm tra điều kiện if/needs và cách workflow xử lý skipped jobs. Required check phải phản ánh đúng các kiểm tra bắt buộc.

### 10.2. Re-run và kết quả mới nhất

Khi CI fail do lỗi hạ tầng tạm thời, có thể re-run job. Tuy nhiên, kết quả cần gắn với cùng source revision và cần ghi rõ lần chạy nào được dùng để quyết định merge. Không dùng một kết quả pass cũ cho commit đã thay đổi.

## 11. Phản hồi CI phải dễ hiểu và có thể hành động

CI không chỉ chạy lệnh; nó cần truyền thông tin cho người chịu trách nhiệm sửa thay đổi.

Một phản hồi tốt gồm trạng thái tổng thể pass/fail, job/task/phase thất bại, commit SHA và pull request liên quan, log đủ để thấy lỗi đầu tiên có ý nghĩa, test/static analysis/coverage report, artifact hoặc file đầu ra khi cần và link tới tài liệu hoặc rule liên quan.

### 11.1. Phân biệt lỗi source và lỗi hạ tầng

Một pipeline có thể fail vì compile error hoặc test assertion fail, quality gate không đạt, dependency repository timeout, runner image không sẵn sàng, credentials hết hạn, service container không khởi động hoặc quota/storage CI bị vượt.

Không nên gán mọi build failure cho code của lập trình viên. Hãy phân loại lỗi trước khi sửa. Nếu là lỗi hạ tầng, nhóm cần khôi phục runner/repository/service và chạy lại đúng revision.

### 11.2. Lưu report ngay cả khi job fail

Test report và static analysis report có thể được tạo trước khi pipeline thất bại. Cấu hình upload với điều kiện luôn chạy khi job còn khả năng thực thi giúp giữ bằng chứng điều tra.

Ví dụ GitHub Actions:

~~~yaml
- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-reports
    path: |
      **/build/reports/tests/**
      **/build/test-results/**
    if-no-files-found: ignore
~~~

Đường dẫn này phù hợp với ví dụ Gradle. Với Maven, report thường nằm dưới target; cần bổ sung đường dẫn tương ứng. Không upload secret hoặc file cấu hình nhạy cảm cùng report.

### 11.3. Thông báo phải dẫn đến bước tiếp theo

Thông báo chỉ ghi “Build failed” không đủ hữu ích. Nên có link tới job, log, report và commit. Nếu có nhiều job, summary nên nêu rõ job nào fail, job nào bị skipped và vì sao.

## 12. Test ổn định và flaky tests

Flaky test là test đôi khi pass, đôi khi fail với cùng source và điều kiện dự kiến. Nguyên nhân có thể là race condition, thời gian, random, phụ thuộc network, test dùng chung trạng thái hoặc thứ tự thực thi.

Flaky test làm giảm niềm tin vào CI. Khi nhóm thường xuyên re-run đến khi pass, một lỗi thật có thể bị xem như nhiễu.

### 12.1. Nguyên nhân thường gặp

- Test phụ thuộc thứ tự chạy.
- Chia sẻ database, file hoặc port giữa test.
- Dùng sleep cố định thay vì chờ điều kiện.
- Phụ thuộc API bên ngoài hoặc network không ổn định.
- Không reset trạng thái trước/sau test.
- Dùng thời gian hiện tại hoặc random seed không kiểm soát.
- Race condition hoặc timeout quá ngắn.
- Resource của CI runner bị giới hạn hơn máy local.

### 12.2. Cách điều tra

1. Lưu log, seed, thời gian và môi trường của lần fail.
2. Chạy lại cùng test riêng lẻ để xác định có phụ thuộc test khác không.
3. Chạy test lặp nhiều lần trong môi trường tương tự CI.
4. Kiểm tra resource, concurrency, port, file và dữ liệu dùng chung.
5. Loại phụ thuộc dịch vụ ngoài bằng fake/mock/container phù hợp.
6. Sửa nguyên nhân race/timeout thay vì chỉ tăng timeout tùy tiện.

### 12.3. Re-run có kiểm soát

Một lần re-run có thể giúp phân biệt lỗi tạm thời của hạ tầng với lỗi lặp lại. Nhưng không nên tự động re-run mọi failure vô hạn. Nếu policy cho phép retry, giới hạn số lần, lưu kết quả ban đầu và ghi nhận test nào flaky.

Một test được đánh dấu quarantine có thể không chặn pipeline tạm thời, nhưng phải có owner và thời hạn xử lý. Quarantine không nên biến thành cách bỏ qua test vĩnh viễn.

## 13. CI và dependency/build cache

CI runner có thể sử dụng dependency cache hoặc Gradle build cache để giảm thời gian. Hai loại cache có vai trò khác nhau:

- Dependency cache lưu JAR/POM/module metadata đã resolve.
- Gradle build cache lưu output của task cacheable.
- CI cache action có thể lưu thư mục cache giữa các runner/job.
- Remote build cache có thể chia sẻ task outputs qua nhiều máy.

### 13.1. Cache không thay thế kiểm chứng

Build cache có thể khôi phục output task khi cache key phù hợp. Task không cacheable vẫn phải chạy. Test phụ thuộc trạng thái bên ngoài không nên được cache nếu mục tiêu là xác nhận trạng thái hiện tại.

### 13.2. Cache key của CI

Nếu CI dùng cache action để lưu dependency cache, key thường cần xét OS, JDK hoặc file lock/version build tool tùy nội dung cache. Cache key quá rộng có thể khôi phục trạng thái không tương thích; key quá hẹp làm giảm cache hit.

Với Gradle remote build cache, cache key do Gradle tính dựa trên task inputs/implementation. Không nên tự tạo một CI cache key rồi nhầm nó với cache key task của Gradle.

### 13.3. Bảo vệ remote cache

Không cấp quyền push remote build cache cho untrusted pull request. Một thay đổi từ fork có thể sửa build logic hoặc task implementation và ghi output mà các build tin cậy sử dụng sau này.

Nên tách read/write credentials, giới hạn write cho branch/workflow tin cậy và theo dõi cache backend. Cache output phải được xem như dữ liệu có nguồn gốc cần kiểm soát.

## 14. CI và bảo mật của pipeline

Pipeline có quyền truy cập source, dependency repository, package registry, deployment environment và secret. Vì vậy, workflow CI cũng là một phần của bề mặt bảo mật.

### 14.1. Quyền tối thiểu

Chỉ cấp quyền cần thiết cho từng job. Job compile/test thường không cần quyền deploy production. Job đọc dependency repository không nhất thiết cần token publish.

### 14.2. Secret

- Lưu secret trong secret manager của nền tảng CI.
- Không ghi token/password vào build script hoặc source control.
- Không in secret vào log.
- Hạn chế cấp secret cho pull request từ fork.
- Tách credential đọc repository, publish package và deploy.
- Luân chuyển secret theo chính sách tổ chức.

### 14.3. Untrusted pull request

Pull request từ fork có thể sửa workflow, build script và task. Không chạy code không tin cậy trong context có quyền ghi package, deploy hoặc đọc secret nhạy cảm nếu nền tảng không bảo vệ đúng cách.

Hãy kiểm tra event type, permission token và workflow trigger. Một job chỉ cần build/test nên có quyền read-only hoặc không có secret nếu dependency công khai.

### 14.4. Pin action và tool

Action, container image, plugin và tool được tải trong CI đều là đầu vào của pipeline. Pin version hoặc commit SHA theo chính sách supply chain của tổ chức. Review cập nhật định kỳ và xác minh nguồn cung cấp.

### 14.5. Artifact và provenance

Artifact được tạo bởi CI nên gắn với commit SHA, build run ID, toolchain và checksum. Với pipeline phát hành, có thể tạo SBOM và provenance để biết artifact gồm thành phần nào và được tạo từ source/quy trình nào.

## 15. CI artifact và build output

Artifact là đầu ra mà pipeline lưu để job khác hoặc người dùng tải xuống. Ví dụ JAR/WAR, test report và coverage report, static analysis report, SBOM, Docker image digest hoặc generated documentation.

### 15.1. Phân biệt artifact tạm và artifact phát hành

Artifact của pull request có thể chỉ dùng để kiểm thử hoặc review. Artifact release cần có version, checksum, provenance và chính sách lưu trữ rõ ràng.

Không nên để một artifact snapshot từ pull request tự động trở thành artifact production nếu chưa qua release gate.

### 15.2. Truyền artifact giữa các job

Nếu job package tạo JAR và job integration test cần dùng nó, pipeline nên upload/download artifact rõ ràng. Điều này bảo đảm job sau kiểm tra đúng binary đã được tạo ở job trước, thay vì tự build lại với môi trường có thể khác.

### 15.3. Không dùng artifact name làm định danh duy nhất

Nhiều build có thể tạo cùng tên file nhưng nội dung khác nhau. Hãy gắn artifact với run ID, commit SHA, version và checksum. Khi tải artifact để điều tra, xác nhận digest trước khi sử dụng.

## 16. CI trong dự án nhiều module

Một repository Gradle/Maven nhiều module có thể chứa thư viện dùng chung và nhiều ứng dụng. Thay đổi ở một module có thể ảnh hưởng consumer khác.

### 16.1. Build đúng phạm vi nhưng không bỏ sót consumer

Gradle có thể dùng project path và task graph để build module cùng prerequisite:

    ./gradlew :order-app:check

Maven có thể chọn module và dependency trong reactor:

    ./mvnw -pl order-app -am verify

Đây là cách chạy phạm vi có chủ đích. Tuy nhiên, nếu thay đổi shared library, chỉ build một consumer có thể chưa đủ. CI cần xác định consumer liên quan và chạy test phù hợp.

### 16.2. Full build và affected-module build

Với monorepo lớn, chạy full build trên mọi pull request có thể tốn kém. Có thể xác định module bị ảnh hưởng và consumer phụ thuộc để chỉ chạy phần liên quan, nhưng logic xác định affected modules phải chính xác.

Nếu dependency graph hoặc script không nhận diện được quan hệ, pipeline có thể bỏ sót module cần test. Một chiến lược phổ biến là chạy affected tests nhanh trên pull request và chạy full build định kỳ hoặc trước release.

### 16.3. Contract và integration tests

Shared library hoặc API contract nên được kiểm tra cùng các consumer quan trọng. Khi public API thay đổi, pipeline có thể build/test các module sử dụng API đó để phát hiện lỗi compile hoặc behavior sớm.

## 17. Thời gian phản hồi và thứ tự ưu tiên

CI hiệu quả cần cân bằng tốc độ và độ bao phủ. Nếu mọi pull request phải chờ một pipeline rất dài, lập trình viên có thể trì hoãn tích hợp hoặc bỏ qua kết quả.

Một thứ tự thường hữu ích:

1. Kiểm tra cấu hình và compile.
2. Format/style check.
3. Unit test nhanh.
4. Static analysis và coverage.
5. Integration test.
6. Security scan và compatibility matrix.
7. Package và release-specific verification.

Thứ tự chính xác phụ thuộc dependency giữa task và mục tiêu phản hồi. Một số job độc lập có thể chạy song song. Những bước rẻ và thường phát hiện lỗi nên chạy sớm.

### 17.1. Không đánh đổi độ tin cậy để lấy tốc độ

Nếu build chậm, hãy đo task nào tốn thời gian. Có thể dùng Gradle build cache, test partitioning, parallel execution, dependency caching hoặc runner phù hợp. Không nên bỏ required test mà không đánh giá rủi ro.

### 17.2. Chia pipeline nhanh và sâu

- Pull request: compile, unit test, formatting, static analysis cơ bản.
- Main branch: full integration, matrix quan trọng và scan sâu.
- Nightly: compatibility, performance, dependency updates và full test suite.
- Release: clean verification, package, SBOM/provenance và publish/deploy có kiểm soát.

Phân tầng không có nghĩa là kiểm tra quan trọng bị bỏ qua. Nó xác định thời điểm và điều kiện thực thi phù hợp.

## 18. Ví dụ pipeline CI cho Gradle trên GitHub Actions

Workflow minh họa dưới đây chạy khi có pull request và push lên main:

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Show toolchain
        run: |
          java -version
          ./gradlew --version

      - name: Verify
        run: ./gradlew clean check --build-cache

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-reports
          path: |
            **/build/reports/**
            **/build/test-results/**
          if-no-files-found: ignore
~~~

Đây là ví dụ tối giản. Version action và JDK cần được pin theo chính sách của tổ chức; pipeline thực tế có thể cần quyền read dependency repository, matrix, integration services hoặc remote cache credentials. Nếu build cần Java toolchain khác JDK chạy Gradle, cấu hình toolchain trong build script và cung cấp JDK tương ứng.

Để ngăn merge khi kiểm tra fail, cấu hình branch protection/ruleset yêu cầu status check của job verify. Chỉ khai báo workflow không tự tạo chính sách chặn merge.

## 19. Ví dụ pipeline CI cho Maven

Một job Maven có thể chạy:

~~~yaml
name: Maven CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Show versions
        run: |
          java -version
          ./mvnw --version

      - name: Verify
        run: ./mvnw --batch-mode --no-transfer-progress clean verify

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: maven-reports
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
            **/target/site/**
          if-no-files-found: ignore
~~~

Workflow này giả định repository có Maven Wrapper và plugin/report được cấu hình. Surefire thường lưu unit test report; Failsafe thường lưu integration test report. Các đường dẫn khác tùy plugin.

## 20. Quản lý build failure

Khi CI fail, mục tiêu đầu tiên là xác định đúng lớp nguyên nhân.

### 20.1. Compile failure

Đọc compiler diagnostic đầu tiên có ý nghĩa, xác định file/dòng và kiểm tra JDK/release/classpath. Lỗi dây chuyền phía sau có thể là hậu quả của lỗi đầu tiên.

### 20.2. Test failure

Xem test report và stack trace, xác định assertion, setup hoặc dependency ngoài. Chạy riêng test thất bại với cùng JDK/property nếu có thể.

### 20.3. Quality gate failure

Xem report của formatter, linter, static analyzer hoặc coverage. Xác định rule và phạm vi áp dụng; không sửa code chỉ để làm biến mất cảnh báo khi chưa hiểu nguyên nhân.

### 20.4. Infrastructure failure

Các lỗi như repository timeout, runner mất kết nối, service container không khởi động hoặc quota bị vượt cần được xử lý ở hạ tầng. Nếu retry, giữ lại log lần đầu và ghi nhận đây là retry do infrastructure.

### 20.5. Không che giấu failure bằng continue-on-error

Một số workflow cho phép tiếp tục job dù bước trước fail. Điều này hữu ích khi muốn thu thập nhiều report, nhưng nếu bước bắt buộc bị đánh dấu continue-on-error và summary vẫn success, gate có thể bị vô hiệu hóa.

Hãy dùng điều kiện chạy tiếp để thu thập thông tin, sau đó tổng hợp trạng thái fail đúng cách. Required check phải phản ánh tất cả bước bắt buộc.

## 21. CI và chất lượng của thay đổi, không chỉ trạng thái build

Build pass chỉ xác nhận những kiểm tra đã được cấu hình đều đạt ở revision/môi trường đó. Nó không chứng minh logic đáp ứng mọi yêu cầu nghiệp vụ, test bao phủ mọi trường hợp quan trọng, thiết kế dễ bảo trì, không có lỗ hổng chưa biết hoặc hiệu năng production luôn đạt.

Vì vậy, CI cần kết hợp với code review, thiết kế, test strategy, security review và quan sát runtime. CI cung cấp bằng chứng lặp lại được để hỗ trợ quyết định, không thay thế trách nhiệm kỹ thuật của nhóm.

### 21.1. Code review vẫn cần thiết

Reviewer đánh giá ý định thay đổi, thiết kế, API, khả năng bảo trì, rủi ro và các trường hợp mà automated checks chưa mô hình hóa. CI giúp reviewer không phải tự chạy mọi lệnh và có thể tập trung vào nội dung.

### 21.2. Test quality quan trọng hơn số lượng

Một pipeline có hàng nghìn test vẫn có thể bỏ sót lỗi nếu assertion yếu hoặc test không kiểm tra điều kiện quan trọng. Hãy review test mới như một phần của thay đổi.

### 21.3. Theo dõi sau khi deploy

Một số lỗi chỉ xuất hiện với traffic, dữ liệu hoặc môi trường production. Logging, metrics, tracing, alert và rollback là phần bổ sung sau CI/CD. Không nên coi CI pass là kết thúc hoàn toàn việc kiểm chứng sản phẩm.

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| CI chỉ là chạy build trên server | CI là quy trình tích hợp, kiểm chứng, báo kết quả và áp dụng chính sách |
| Local build pass nghĩa là CI chắc chắn pass | JDK, dependency, environment, source revision và service có thể khác |
| Pull request đã pass thì build sau merge không cần chạy | Merge result/branch chính có thể là revision khác |
| Có workflow là merge đã bị chặn khi fail | Cần cấu hình required checks/branch protection |
| Build pass chứng minh ứng dụng không có bug | Chỉ các kiểm tra đã chạy mới được xác nhận |
| Mọi test nên chạy trên mọi commit | Có thể phân tầng nhanh/sâu, nhưng phải xác định gate trước merge |
| Re-run đến khi pass là xử lý flaky test | Cần lưu failure ban đầu và tìm nguyên nhân |
| Cache giúp CI bỏ qua mọi test | Cache chỉ áp dụng cho task phù hợp và không thay thế kiểm tra trạng thái cần chạy |
| Artifact có cùng tên là cùng nội dung | Cần commit/version và checksum để nhận diện |
| CI failure luôn do source code | Có thể là lỗi toolchain, repository, credentials hoặc runner |
| Continue-on-error chỉ ảnh hưởng log | Nó có thể làm trạng thái gate không phản ánh lỗi bắt buộc |

## 23. Checklist thiết kế CI cho thay đổi mã nguồn

Khi thiết lập hoặc review pipeline, hãy xác nhận:

1. Pipeline được kích hoạt bởi đúng sự kiện và đúng branch/PR?
2. Log ghi nhận commit SHA và revision thực tế được checkout?
3. Submodule/LFS được lấy đúng nếu dự án sử dụng?
4. Gradle/Maven Wrapper và JDK/toolchain được cố định?
5. Compile, unit test và các required checks được chạy?
6. Integration test cần thiết có service và fixture phù hợp?
7. Formatter, static analysis, coverage và security checks được cấu hình theo policy?
8. Log và report được lưu ngay cả khi job fail?
9. CI status được cấu hình thành required check trước merge?
10. Job có quyền tối thiểu và secret không bị cấp cho code không tin cậy?
11. Cache được dùng đúng mục đích và remote cache có quyền read/write phù hợp?
12. Artifact được gắn với commit, run ID và checksum?
13. Lỗi source được phân biệt với lỗi hạ tầng?
14. Flaky test có owner và quy trình xử lý?
15. Release/deploy có điều kiện và quyền riêng?

CI đóng vai trò kiểm chứng tự động cho từng thay đổi bằng cách chạy cùng một quy trình trên source revision xác định và môi trường được quản lý. Nó giúp phát hiện compile/test/quality failure sớm, cung cấp report cho review và kết nối kết quả với required checks để kiểm soát merge. Một pipeline đáng tin cậy cần cố định Wrapper/JDK, xác định đúng revision, chạy các bước phù hợp, lưu bằng chứng, bảo vệ secret/cache và phân loại lỗi source với lỗi hạ tầng. CI là một lớp bảo đảm quan trọng trong quy trình phát triển; nó hỗ trợ code review và kiểm chứng sau triển khai, chứ không thay thế chúng.

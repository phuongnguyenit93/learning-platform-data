# JaCoCo: thu thập dữ liệu, tạo báo cáo và đặt ngưỡng coverage

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Chất lượng mã

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích **code coverage** đo những phần mã đã được thực thi bởi bộ kiểm thử, không đo trực tiếp độ đúng đắn hay chất lượng của các assertions.
2. Phân biệt ba giai đoạn độc lập nhưng liên quan: **thu thập JaCoCo execution data**, **tạo coverage report**, và **kiểm tra ngưỡng coverage** để quyết định build PASS/FAIL.
3. Dùng core plugin **jacoco** của Gradle với **Java 17 + JUnit Jupiter**, hiểu agent instrumentation hoạt động trong test JVM và file **build/jacoco/test.exec** có ý nghĩa gì.
4. Cấu hình đúng các task **test**, **jacocoTestReport**, **jacocoTestCoverageVerification** và **check**; biết các task nào **không tự có dependency** với nhau.
5. Chọn định dạng báo cáo **HTML, XML, CSV**, hiểu đường dẫn, consumer của từng định dạng và cách đưa XML vào CI/SonarQube hoặc công cụ phân tích tương thích.
6. Thiết lập rule theo **BUNDLE/CLASS/PACKAGE**, các bộ đếm **LINE, BRANCH, INSTRUCTION, METHOD, CLASS, COMPLEXITY**, và **COVEREDRATIO/MISSEDRATIO/MISSEDCOUNT**.
7. Hiểu ý nghĩa giá trị ngưỡng: **minimum = 0.80** nghĩa là tỷ lệ tối thiểu 80%, không phải 0,80%; một rule được áp trên đúng **đối tượng và tập classDirectories**.
8. Thực hành thay ngưỡng để tạo **coverage gate thất bại có chủ ý**, rồi bổ sung test cho nhánh chưa được kiểm thử để khôi phục PASS.
9. Phân biệt **coverage của task test đang chạy** với report cũ/được cache, biết vì sao dữ liệu .exec có thể thiếu hoặc không khớp class files.
10. Xử lý **multi-project build, custom Test task/integrationTest, exclusions có kiểm soát, aggregation, configuration cache, CI artifacts** và các lỗi coverage thường gặp.

**Kết luận trước:** JaCoCo không chỉ là một số phần trăm. Gradle **test** chạy code có JaCoCo agent và ghi execution data; **jacocoTestReport** kết hợp dữ liệu đó với classes/sources để tạo HTML/XML/CSV; **jacocoTestCoverageVerification** so dữ liệu với các rules và có thể làm build thất bại. Nếu không kết nối task dependencies và thống nhất phạm vi đo, CI có thể báo test thành công nhưng không có báo cáo hoặc không kiểm tra ngưỡng.

## 1. JaCoCo là gì? Coverage nói được và không nói được điều gì?

**JaCoCo** (Java Code Coverage) là công cụ phân tích coverage dựa trên việc instrument Java bytecode và ghi những điểm mã được thực thi. Gradle cung cấp **core plugin** có ID **jacoco**, tích hợp JaCoCo agent với các task JVM thích hợp và cung cấp task báo cáo/verification.

Khái niệm đơn giản:

~~~text
Java source -> javac -> .class
                           |
Test task + JaCoCo agent -> test JVM instrumented classes
                           |
                           v
                    test.exec (execution data)
                           |
   .class files -----------+
   .java sources ----------+
                           v
                  jacocoTestReport
                           |
                 +---------+----------+
                 |         |          |
                HTML       XML        CSV
                           |
        execution data + class files
                           v
             jacocoTestCoverageVerification
                           |
                 PASS hoặc FAIL gate
~~~

**Coverage đo việc thực thi**, ví dụ một câu lệnh if có được đi qua nhánh true/false chưa. Nó không cho biết:

- Assertion có kiểm tra đúng yêu cầu nghiệp vụ hay không.
- Đầu ra có đúng khi gặp dữ liệu hiếm, thời gian thực hoặc hệ thống ngoài hay không.
- Test suite có ổn định, không flaky, đủ integration tests hay không.
- Có lỗ hổng bảo mật, race condition hoặc deadlock hay không.
- Dự án có đáp ứng performance, accessibility hay maintainability requirements hay không.

Một test gọi method nhưng **không assert gì** vẫn có thể nâng coverage. Vì vậy **coverage cao ≠ test tốt**, và **coverage 100% ≠ phần mềm không lỗi**.

### 1.1. Ba câu hỏi cần tách riêng

| Câu hỏi | Cơ chế trả lời | Kết quả điển hình |
|---|---|---|
| Những bytecode points nào được chạy? | JaCoCo Java agent trong JVM kiểm thử | **build/jacoco/test.exec** |
| Coverage của source/class/package là bao nhiêu? | JacocoReport so execution data với bytecode/sources | HTML, XML, CSV |
| Coverage có vượt chính sách không? | JacocoCoverageVerification + violationRules | Task PASS hoặc FAILED |

**Không thể suy ra báo cáo từ chỉ .exec** nếu không có class files tương ứng. Cũng **không thể suy ra ngưỡng đã được kiểm tra** chỉ vì HTML report tồn tại.

### 1.2. JaCoCo là core Gradle plugin

Trong Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}
~~~

**id 'jacoco' không cần version** trong plugins block vì nó đi kèm Gradle distribution. Khác với **JaCoCo tool version** được cấu hình qua extension:

~~~groovy
jacoco {
    toolVersion = '0.8.14'
}
~~~

- **Gradle Wrapper version:** phiên bản Gradle đang chạy.
- **JaCoCo Gradle core plugin:** code tích hợp được cung cấp cùng Gradle.
- **JaCoCo toolVersion:** phiên bản agent/report libraries thực sự được tải để thu coverage.
- **Java toolchain:** JDK dùng biên dịch/chạy test, ví dụ Java 17.
- **JUnit version:** framework/engine cung cấp và thực thi test methods.

Đây là những số phiên bản **khác nhau**. Ví dụ chọn JaCoCo 0.8.14 là một bản tool được tài liệu Gradle sử dụng, đủ cho Java 17 trong bài thực hành; nó **không khẳng định đây là phiên bản mới nhất**. Khi nâng JDK hoặc sử dụng tính năng bytecode mới, hãy kiểm tra compatibility của phiên bản JaCoCo đã chọn.

## 2. Giai đoạn 1: thu thập execution data

Khi Java Plugin và JaCoCo Plugin cùng áp dụng, Gradle thêm một **JacocoTaskExtension** cho các task kiểu **Test**. Khi task thực thi test JVM, Gradle dùng JaCoCo agent để ghi nhận bytecode instructions/branches được đi qua.

Quy trình:

~~~text
./gradlew test
     |
     v
Gradle Test task
     |
     +-- Compile test classes (khi cần)
     +-- Fork test JVM (nếu test thật sự thực thi)
     +-- Gắn JaCoCo Java agent
     +-- JUnit Platform chạy @Test methods
     +-- Java agent ghi probes đã thực thi
     |
     v
build/jacoco/test.exec
~~~

**File .exec là binary execution data**, không phải HTML report và không thể mở bằng trình duyệt để xem tỉ lệ ngay. Bạn cần JacocoReport với class files tương ứng để phân tích.

### 2.1. Dùng mặc định trước khi tùy chỉnh

Cấu hình cơ bản:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Khi tests **thực sự chạy**, file mặc định thường là:

~~~text
build/jacoco/test.exec
~~~

Nếu test task tên **integrationTest**, file execution data mặc định có thể là:

~~~text
build/jacoco/integrationTest.exec
~~~

Đây là convention theo **tên task**. Một custom JavaExec có agent riêng cũng có destination khác. Không mặc định mọi task luôn ghi vào cùng test.exec.

### 2.2. Khi test không thực thi, có data mới không?

Một task có thể:

- **UP-TO-DATE:** Gradle không gọi lại các test methods.
- **FROM-CACHE:** Gradle có thể phục hồi outputs của Test task từ cache.
- **SKIPPED/NO-SOURCE:** Không có bộ test được thực thi.
- **Executed:** Tests thực sự chạy nếu được phát hiện/chọn và không ở dry-run mode.

Với **UP-TO-DATE/FROM-CACHE**, đừng nói file .exec là chứng cứ các tests vừa chạy trong invocation hiện tại. Nó có thể được giữ lại hoặc khôi phục từ build state/cache tương ứng.

**JaCoCo plugin xóa destination execution data file khi một task được instrument bắt đầu thực thi**, để tránh vô tình giữ dữ liệu cũ. Tuy nhiên nếu test không thật sự được thực thi, hoặc pipeline dùng file thủ công/đổi task graph, bạn vẫn phải xác minh provenance của .exec và phạm vi tests.

### 2.3. Cấu hình JaCoCo agent cho test

Ví dụ tùy chỉnh destination:

~~~groovy
tasks.named('test') {
    jacoco {
        enabled = true
        destinationFile = layout.buildDirectory
                .file('jacoco/unit-tests.exec')
                .get()
                .asFile
    }
}
~~~

Đây là **snippet thay thế** mặc định, không phải đoạn cần thêm vào lab chính. Nếu đổi destinationFile, phải bảo đảm JacocoReport/JacocoCoverageVerification đọc đúng execution data. Với build chuẩn, thường nên giữ convention **build/jacoco/test.exec** để giảm cấu hình.

Agent extension còn hỗ trợ:
- includes/excludes theo **class-name patterns** ở instrumented classes.
- classDumpDir để debug class instrumentation.
- dumpOnExit, output (FILE/TCP), sessionId.
- excludeClassLoaders, includeNoLocationClasses trong tình huống đặc biệt.

**Lưu ý:** Agent excludes và **report classDirectories excludes** không phải một thao tác giống nhau. Agent excludes ngăn instrumentation một số classes; report exclusions thay **đối tượng được tính vào mẫu số** của coverage metrics.

### 2.4. Bên trong .exec là gì?

Execution data lưu các thông tin phục vụ mapping những probes đã được thực thi về classes đúng phiên bản. Nó **không chứa source code hoàn chỉnh**, không phải một bản test report XML và không phải binary Java application.

Nếu cùng tên class nhưng bytecode thay đổi giữa lúc chạy tests và lúc tạo report, class IDs có thể không khớp. Khi đó JaCoCo có thể coi class chưa covered dù methods thực sự đã chạy. Cần đảm bảo **test execution và report analysis dùng cùng compiled class files**.

### 2.5. Nhận diện dữ liệu cũ

Đừng chẩn đoán bằng timestamp duy nhất. Một file .exec có thể tồn tại từ lượt trước hoặc được cache phục hồi. Một cách quan sát chắc hơn khi cần kiểm tra **fresh execution**:

~~~bash
./gradlew clean test --rerun-tasks --no-build-cache --console=plain
~~~

Vẫn cần đảm bảo task test có test cases thực và không bị exclude/dry-run. Với Gradle version hỗ trợ task option --rerun, bạn có thể dùng:

~~~bash
./gradlew test --rerun --no-build-cache --console=plain
~~~

Cách thứ hai tránh rerun mọi task dependency khi không cần. Không ép fresh run ở mọi build nếu unit tests deterministic và caching là chính sách hợp lệ; sử dụng khi đánh giá độ tin cậy của dữ liệu hoặc integration tests phụ thuộc môi trường.

## 3. Giai đoạn 2: tạo báo cáo coverage

Khi Java + JaCoCo plugins cùng áp dụng, Gradle cung cấp task **jacocoTestReport** loại **JacocoReport**.

Chạy trực tiếp:

~~~bash
./gradlew jacocoTestReport
~~~

**Điểm rất dễ nhầm:** Theo tài liệu Gradle, **jacocoTestReport KHÔNG tự dependsOn test**. Nếu chưa có execution data, report có thể không có dữ liệu để tạo hoặc task không có việc cần thiết. Để đảm bảo test được yêu cầu trước report:

~~~groovy
tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
}
~~~

Có thể dùng:

~~~groovy
tasks.named('test') {
    finalizedBy tasks.named('jacocoTestReport')
}
~~~

để report được lên lịch sau test. Nhưng **finalizedBy** và **dependsOn** có mục đích khác:
- **dependsOn test**: yêu cầu test là prerequisite khi chạy report.
- **finalizedBy report**: tự lập lịch report như finalizer sau khi test task hoàn thành, ngay cả khi bạn chỉ yêu cầu test (trong những điều kiện Gradle cho phép).
- Nếu phải chọn thứ tự rõ ràng cho CI, có thể dùng **dependsOn** và gọi task report/verification qua pipeline.
- Không cần dùng cả hai trong mọi project nếu nó làm task graph khó hiểu.

**Quan trọng:** Việc task test là prerequisite không có nghĩa nó luôn **thực thi test methods mới**; task vẫn có thể UP-TO-DATE hoặc FROM-CACHE. Nếu CI cần fresh execution, phải xử lý cache/up-to-date riêng.

### 3.1. Ba định dạng báo cáo

| Định dạng | Mục đích | Ai thường đọc? |
|---|---|---|
| **HTML** | Trang trực quan theo package/class/line, màu covered/partly/missed | Developer, reviewer, QA |
| **XML** | Dữ liệu có cấu trúc cho hệ thống CI/code quality | SonarQube, report parsers, dashboards |
| **CSV** | Dữ liệu dạng bảng để nhập xử lý/thống kê | Scripts, spreadsheet, phân tích nội bộ |

Ví dụ bật HTML + XML và không tạo CSV:

~~~groovy
tasks.named('jacocoTestReport') {
    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}
~~~

Theo convention trong Gradle Java project:

~~~text
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
~~~

Khi bật CSV, một file .csv được tạo trong report directory phù hợp. Nếu bạn **tùy chỉnh reportsDirectory hoặc outputLocation**, đường dẫn thực tế đổi; không hardcode path từ ví dụ khác để cấu hình CI mà chưa kiểm tra.

### 3.2. HTML report có những gì?

Một báo cáo HTML thường có:
- Tổng coverage theo bundle/module.
- Danh sách packages/classes.
- Mức instruction/branch coverage.
- Số missed/covered lines/methods/classes/complexity.
- Source highlighting ở những nơi có source và class debug information tương ứng.
- Sessions page để xem class IDs gắn với execution data.

Màu nguồn thường:
- **Đỏ:** chưa covered.
- **Vàng:** partially covered.
- **Xanh:** fully covered.

**Màu của một line không có nghĩa mọi tình huống nghiệp vụ của line ấy đã được kiểm thử**. Một line có thể chứa nhiều bytecode instructions và nhiều nhánh.

### 3.3. XML report phục vụ tooling

Một XML report có thể chứa các elements như:

~~~xml
<report name="coverage-lab">
  <package name="demo">
    <class name="demo/GradePolicy">
      <counter type="LINE" missed="1" covered="5"/>
      <counter type="BRANCH" missed="2" covered="4"/>
    </class>
  </package>
</report>
~~~

Đây là **ví dụ cấu trúc rút gọn** với các con số **minh họa**, không phải output chính xác được bảo đảm của bài lab. XML thực tế có DOCTYPE, sourcefile elements và counters ở nhiều cấp. Để đọc coverage ratio từ XML, dùng **covered/(covered+missed)** của đúng counter và đúng cấp đối tượng.

**Không lấy number of JUnit tests passed rồi gọi nó là percentage covered.** Hai chỉ số độc lập: số test cases và số bytecode/branches được thực thi.

### 3.4. XML không phải ngưỡng

Bật:

~~~groovy
reports {
    xml.required = true
}
~~~

chỉ tạo báo cáo dữ liệu. Nó **không** có nghĩa build tự FAIL khi coverage thấp hơn 80%. Muốn có coverage gate, phải cấu hình và chạy **jacocoTestCoverageVerification** với rules phù hợp.

### 3.5. Cấu hình thư mục report

JaCoCo extension của project có thể đặt:

~~~groovy
jacoco {
    toolVersion = '0.8.14'
    reportsDirectory = layout.buildDirectory.dir('quality/jacoco')
}
~~~

Đây là **phương án tùy chọn**. Khi đổi reportsDirectory, hãy cập nhật CI artifact paths. Trong bài lab chính, ta giữ **reportsDirectory mặc định** để đơn giản hóa các bước kiểm tra.

### 3.6. Vì sao report cần đúng classes và sources?

JaCoCo report tiêu thụ ba nhóm đầu vào:

1. **executionData**: probes từ JaCoCo agent.
2. **classDirectories**: bytecode tương ứng với những classes muốn đánh giá.
3. **sourceDirectories**: mã nguồn để hiển thị source highlighting.

Nếu bytecode được compile lại sau test trước khi report, hoặc class files khác với những gì test JVM đã load, class IDs có thể không khớp. Nếu thiếu source hoặc source roots sai, HTML có thể chỉ hiển thị class-level metrics mà không tô màu source đúng.

Hãy hạn chế thay đổi classes giữa bước test và report. Khi gặp 0% bất thường, kiểm tra Sessions trong HTML và class ID mismatches trước khi tự động tăng ngưỡng/đổi excludes.

## 4. Giai đoạn 3: đặt ngưỡng với JacocoCoverageVerification

Gradle tạo task **jacocoTestCoverageVerification** loại **JacocoCoverageVerification**. Nó đọc execution data/classes và kiểm tra **violationRules**.

Ví dụ ngưỡng 80% line coverage cho toàn project:

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}
~~~

**Diễn giải đúng:**
- **element = 'BUNDLE'**: đo tổng bundle/module được report.
- **counter = 'LINE'**: quan sát line coverage.
- **value = 'COVEREDRATIO'**: đo tỷ lệ covered trên covered + missed lines.
- **minimum = 0.80**: đạt từ **80%** trở lên.
- Nếu dưới ngưỡng, task **jacocoTestCoverageVerification FAILED**.
- 0.80 là một số tỷ lệ từ 0 tới 1, **không phải 0.80%**.

**Chưa có rule không có nghĩa mặc định kiểm 80%.** Task chỉ dùng các rules mà build định nghĩa.

### 4.1. Các cấp element

| Element | Ý nghĩa | Dùng khi nào? |
|---|---|---|
| **BUNDLE** | Tổng module/bundle của report scope | Gate tổng coverage project |
| **PACKAGE** | Từng package | Tránh để một package yếu bị che bằng package mạnh |
| **CLASS** | Từng class | Gate lớp quan trọng hoặc phát hiện class hoàn toàn chưa test |
| **SOURCEFILE** | Từng file nguồn | Chính sách source-level, chú ý nhiều classes trong một file |
| **METHOD** | Từng method | Gate rất chi tiết; thường dễ gây nhiễu nếu áp toàn bộ |

Bạn có thể dùng includes/excludes trong một rule để lọc **những elements được đánh giá**. Chọn element phù hợp với mục tiêu:
- BUNDLE 80% là ngưỡng tổng.
- CLASS 80% là **mỗi class** được chọn phải đạt.
- METHOD 80% là **mỗi method** được chọn phải đạt, dễ quá chặt cho getters/constructors/edge cases.

**Không đồng nhất “80% tổng project” với “mọi class 80%”.** Hai rule có thể cho kết quả PASS/FAIL khác nhau trên cùng execution data.

### 4.2. Các bộ đếm coverage

Theo JaCoCo:

| Counter | Đếm gì? | Ghi chú |
|---|---|---|
| **INSTRUCTION** | Java bytecode instructions | C0 coverage; không phụ thuộc source line format |
| **BRANCH** | Các nhánh từ if/switch | C1 coverage; **exception handlers không được tính như branches** theo định nghĩa JaCoCo |
| **LINE** | Những source lines có bytecode thực thi được | Cần debug line information để mapping |
| **METHOD** | Methods/constructors/static initializers được thực thi | Một method covered nếu ít nhất một instruction thực thi |
| **CLASS** | Classes có phương thức nào đó được thực thi | Constructors/static initializers có thể tính vào |
| **COMPLEXITY** | Cyclomatic complexity có thể phân thành covered/missed | Không đồng nghĩa test cases |
  
**BRANCH COVEREDRATIO 80% không có nghĩa 80% dòng code**. Một line có thể chứa nhiều branches; các counters phải được nêu rõ trong tài liệu/CI policy.

### 4.3. Các giá trị rule

Một JaCoCo rule có thể dùng:

| Value | Ý nghĩa |
|---|---|
| **COVEREDRATIO** | covered / (covered + missed), từ 0 tới 1 |
| **MISSEDRATIO** | missed / (covered + missed), từ 0 tới 1 |
| **COVEREDCOUNT** | Số đơn vị đã covered |
| **MISSEDCOUNT** | Số đơn vị chưa covered |
| **TOTALCOUNT** | Tổng số đơn vị |

Ví dụ:
- **minimum 0.80** với COVEREDRATIO: phải đạt ít nhất 80%.
- **maximum 0.20** với MISSEDRATIO: không được thiếu quá 20%.
- **maximum 0** với MISSEDCOUNT: không được bỏ sót đơn vị nào theo counter.
- **minimum 15** với COVEREDCOUNT: ít nhất 15 units covered (khác hoàn toàn 15%).

**Thận trọng:** Ratio coverage có vấn đề khi mẫu số là 0 (ví dụ class không có branch). JaCoCo/Gradle có semantics riêng cho counter không áp dụng; đừng đòi mọi class không có if phải đạt 100% branch theo cách thủ công. Hãy xem report và loại rule không hợp lý.

### 4.4. Nhiều rules có thể cùng áp dụng

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }

        rule {
            element = 'BUNDLE'
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.70
            }
        }
    }
}
~~~

Các limits/rules đều được đánh giá; **một violation đủ làm task FAILED**. Gradle JaCoCo plugin hiện mô tả rằng JaCoCo chỉ báo **violation đầu tiên**, nên đừng giả định log sẽ liệt kê tất cả ngưỡng vi phạm. Để phân tích toàn bộ chỗ thiếu, dùng HTML/XML report.

### 4.5. Rule CLASS và excludes

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    violationRules {
        rule {
            element = 'CLASS'
            includes = ['demo.service.*']
            excludes = ['demo.service.generated.*']
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.75
            }
        }
    }
}
~~~

Đây là **snippet minh họa**, không thuộc lab chạy độc lập nếu không có package demo.service. Nó đặt ngưỡng mỗi class trong nhóm được chọn. **Những pattern phải khớp qualified class names do JaCoCo dùng**; hãy xác nhận thực tế qua report và Gradle docs, không giả định package names của một project khác.

Việc đặt exclude giúp tránh tính lớp được sinh ra hoặc không thuộc phạm vi policy **chỉ khi có lý do hợp lệ**. Không dùng exclusions để xóa khỏi báo cáo những business classes khó kiểm thử nhằm làm đẹp KPI.

## 5. Task graph: vì sao một lệnh build có thể bỏ qua coverage gate?

Một khi áp Java + JaCoCo plugins, các task quan trọng tồn tại:

~~~text
test
jacocoTestReport
jacocoTestCoverageVerification
check
~~~

Nhưng **mối quan hệ mặc định không đồng nghĩa quy trình đầy đủ**:

- **jacocoTestReport** không tự dependsOn **test**.
- **jacocoTestCoverageVerification** không tự nằm trong **check** của Java Plugin theo tài liệu Gradle.
- **jacocoTestReport** sinh file, nhưng không tự verify threshold.
- **check** mặc định có các kiểm tra Java như test, nhưng không có nghĩa đã kiểm JaCoCo gate.

**Cấu hình workflow đề xuất:**

~~~groovy
tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('jacocoTestReport')
}

tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

Khi chạy:

~~~bash
./gradlew check
~~~

Gradle sẽ có quan hệ logic:

~~~text
check
  |
  v
jacocoTestCoverageVerification
  |
  v
jacocoTestReport
  |
  v
test
  |
  v
compileTestJava / testClasses / classes (các dependency cần thiết)
~~~

**Đây là trình tự dependency minh họa**, không phải danh sách task output duy nhất. Với mô hình này, nếu threshold fail, HTML/XML report có cơ hội được sinh ra **trước khi verification báo lỗi**, giúp developer điều tra ngay. Nếu test task fail thì quá trình có thể dừng trước report; dùng chính sách --continue/finalizer phù hợp khi bạn cần thu thập report ngay cả khi tests fail, nhưng không coi report sau test fail là bằng chứng build PASS.

### 5.1. Vì sao không chỉ dùng finalizedBy?

Một số dự án cấu hình:

~~~groovy
tasks.named('test') {
    finalizedBy tasks.named('jacocoTestReport')
}
~~~

Điều này tiện để sinh report sau test. Tuy nhiên:
- Nó **không tự** ràng buộc gate vào check.
- Nó không đảm bảo tất cả rules được kiểm.
- Nó không kiểm tra tests thực sự chạy mới nếu test UP-TO-DATE/FROM-CACHE.
- Một report task có thể phải chờ execution data có sẵn và source/class match.

Có thể dùng finalizedBy cùng những task dependencies phù hợp, nhưng phải hiểu luồng và tránh tạo cycles. Với lab này ta chọn **check → verification → report → test**.

### 5.2. Cách chạy từng bước

| Lệnh | Tác dụng chính | Điều cần kiểm tra |
|---|---|---|
| **./gradlew test** | Compile/chạy test theo Gradle task state | Có .exec mới hay data từ lượt cũ/cache? |
| **./gradlew jacocoTestReport** | Sinh HTML/XML/CSV khi có execution data | Có dependency tới test nếu build có cấu hình rõ? |
| **./gradlew jacocoTestCoverageVerification** | Đánh giá rules | Có dữ liệu, class dirs đúng, verification task có chạy không? |
| **./gradlew check** | Java lifecycle verification + JaCoCo gate nếu đã nối | Rule có thực sự là dependency của check? |
| **./gradlew clean check** | Xóa outputs cũ rồi kiểm tra | Build cache có thể vẫn khôi phục results |
| **./gradlew check --rerun-tasks --no-build-cache** | Buộc xử lý lại tasks, tránh reuse cache | Tests được chọn thật sự chạy? |

**Đừng báo “coverage 80% PASS” chỉ vì lệnh test hoặc build thành công** khi chưa kiểm tra task verification có trong task graph.

## 6. Bài lab hoàn chỉnh: Java 17 + Gradle + JUnit 5 + JaCoCo

Bài lab này tạo một class **GradePolicy**, hai test cases kiểm tra score hợp lệ và một ngưỡng coverage vừa phải. Bạn sẽ cố tình đặt ngưỡng branch 100% để thấy verification **FAIL**, sau đó thêm hai tests cho dữ liệu không hợp lệ để đạt coverage tốt hơn.

### 6.1. Yêu cầu

- JDK 17 tương thích với Gradle Wrapper bạn dùng.
- Một Gradle Wrapper version hỗ trợ Java 17; khuyến nghị dùng Wrapper được commit cùng project.
- Kết nối Maven Central khi chưa có JaCoCo/JUnit trong dependency cache.
- Không cần database, Docker hay web services.

**Cấu trúc:**

~~~text
jacoco-quality-lab/
├── settings.gradle
├── build.gradle
├── gradlew                      # nếu đã tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── src/
│   ├── main/java/demo/GradePolicy.java
│   └── test/java/demo/GradePolicyTest.java
└── manual/demo/Main.java        # chương trình Java tùy chọn chạy ngoài Gradle tests
~~~

Nếu chưa có Wrapper, tạo project files rồi dùng một Gradle đã cài chạy **gradle wrapper** từ root, sau đó sử dụng ./gradlew hoặc .\gradlew.bat. Wrapper distribution có thể cần network để tải lần đầu; đó không phải lỗi JaCoCo agent.

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'jacoco-quality-lab'
~~~

### 6.3. build.gradle — ví dụ đầy đủ

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    // BOM giúp đồng bộ các thành phần JUnit.
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

jacoco {
    // Pin version đã kiểm thử với Java/Gradle của dự án.
    toolVersion = '0.8.14'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

// Không phụ thuộc 'test' theo mặc định: khai báo rõ.
tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}

// Dùng cùng execution data/classDirs như standard test report.
tasks.named('jacocoTestCoverageVerification') {
    // Tạo report trước để khi gate FAIL vẫn có HTML/XML để đọc.
    dependsOn tasks.named('jacocoTestReport')

    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.50
            }
        }
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.50
            }
        }
    }
}

// Gradle mặc định không tự đưa JaCoCo verification vào check.
tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

**Ý nghĩa:**
1. **java** và **jacoco** đều là core plugins, không cần plugin version riêng.
2. Maven Central chỉ phục vụ library dependencies và JaCoCo/JUnit artifacts được resolve qua cấu hình cần thiết.
3. Toolchain dùng Java 17, không sửa phiên bản JaCoCo.
4. junit-bom 5.10.2 căn chỉnh JUnit Jupiter và Platform artifacts.
5. test task bật useJUnitPlatform để chạy JUnit 5.
6. JaCoCo agent được gắn vào Test task và ghi execution data khi tests thực thi.
7. jacocoTestReport phụ thuộc test, tạo HTML và XML.
8. jacocoTestCoverageVerification phụ thuộc report và kiểm tra **hai bundle-level rules**: line coverage ≥50%, branch coverage ≥50%.
9. check phụ thuộc verification: đây là **coverage gate có thể làm CI fail**.
10. Chưa khai báo custom reporting, exclusions hoặc external services nên scope nhỏ, dễ hiểu.

**Vì sao chọn 50% ở baseline?** Đây là một **ngưỡng thử nghiệm thấp**, đủ để quan sát cấu hình và thấy PASS ở hai test cases ban đầu. Dự án thực tế cần ngưỡng có lý do (ví dụ theo module, loại code, trend và rủi ro), không sao chép 50% như chính sách chất lượng mặc định.

### 6.4. GradePolicy.java

**src/main/java/demo/GradePolicy.java**

~~~java
package demo;

public final class GradePolicy {
    private GradePolicy() {
    }

    public static String classify(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException(
                    "score must be between 0 and 100"
            );
        }

        if (score >= 60) {
            return "PASS";
        }
        return "FAIL";
    }
}
~~~

**Giải thích behavior:**
- Score âm hoặc lớn hơn 100 → IllegalArgumentException.
- 60 tới 100 → "PASS".
- 0 tới 59 → "FAIL".
- Thân method có các nhánh cần kiểm thử, bao gồm validation boundary và threshold boundary.

Khi chỉ test 80 và 20, hai đường trả PASS/FAIL được chạy, nhưng các nhánh ném lỗi validation **chưa được chạy**. Chính điều này tạo cơ sở cho bài tập tăng BRANCH threshold lên 100%.

### 6.5. GradePolicyTest.java — hai tests ban đầu

**src/test/java/demo/GradePolicyTest.java**

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GradePolicyTest {

    @Test
    void acceptsPassingScore() {
        assertEquals("PASS", GradePolicy.classify(80));
        System.out.println("TEST_EXECUTED=pass");
    }

    @Test
    void rejectsFailingScore() {
        assertEquals("FAIL", GradePolicy.classify(20));
        System.out.println("TEST_EXECUTED=fail");
    }
}
~~~

Cả hai methods là JUnit Jupiter tests hợp lệ. Khi được **thực thi thật**, assertions pass và in:

~~~text
TEST_EXECUTED=pass
TEST_EXECUTED=fail
~~~

Đây là **hai dòng marker**, nhưng thứ tự methods không được bảo đảm. Gradle có thể thêm tên test, nhãn PASSED và những thông điệp khác quanh stdout. Không dùng thứ tự console của hai markers làm tiêu chí QA.

**Chưa có test nào** gọi GradePolicy.classify(-1) hoặc GradePolicy.classify(101), nên validation error branches chưa được bao phủ. Điều này là chủ đích của lab.

### 6.6. Chạy và tạo dữ liệu JaCoCo

Linux/macOS:

~~~bash
./gradlew clean test --rerun-tasks --no-build-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test --rerun-tasks --no-build-cache --console=plain
~~~

Nếu JDK, dependencies và framework phù hợp:
- test task chạy hai test methods.
- JUnit assertions pass.
- Test task với JaCoCo agent sinh execution data cho lượt test.
- File thường được tạo tại **build/jacoco/test.exec**.
- HTML/XML JaCoCo **chưa nhất thiết được tạo** chỉ vì bạn gọi test, do lab dùng report.dependsOn test chứ không dùng test.finalizedBy report.

Chỉ định **test --rerun-tasks --no-build-cache** ở đây để dễ quan sát một lượt test thật; nếu cache/up-to-date vốn đã đáp ứng chính sách, không cần cờ này trong các build thường ngày.

### 6.7. Sinh báo cáo

~~~bash
./gradlew jacocoTestReport --console=plain
~~~

Do ta đã cấu hình dependsOn(test), task test sẽ được yêu cầu trước report; trong lần chạy tiếp theo mà source/inputs không đổi, test **có thể UP-TO-DATE**. Report vẫn có thể dùng execution data hợp lệ từ lượt trước.

Mở:

~~~text
build/reports/jacoco/test/html/index.html
~~~

XML cho CI:

~~~text
build/reports/jacoco/test/jacocoTestReport.xml
~~~

Những đường dẫn trên giả định giữ reportsDirectory/outputLocation mặc định và JaCoCo task names chuẩn. Nếu file không có, xem task outcome, source sets, .exec, report settings và Gradle/JDK logs.

### 6.8. Kiểm tra ngưỡng ở baseline

~~~bash
./gradlew jacocoTestCoverageVerification --console=plain
~~~

Hoặc chạy lifecycle gate:

~~~bash
./gradlew check --console=plain
~~~

Với test class/production code như trên và coverage rules 50% LINE và BRANCH theo bundle, kỳ vọng gate **PASS**. Không cần biết chính xác tỷ lệ hiển thị đến bao nhiêu chữ số để hiểu việc thiết lập rules; JaCoCo tính dựa trên bytecode, debug info và method/constructor boundaries.

Trong bài lab này:
- Các đường trả "PASS" và "FAIL" được thực thi.
- Các nhánh ném IllegalArgumentException chưa được test.
- Tỷ lệ line/branch coverage **chưa đạt 100%**.
- Ngưỡng tối thiểu 50% được chọn để baseline có thể vượt qua với code như trên.

**Đừng biến giá trị 50% minh họa thành định nghĩa của “đủ kiểm thử”.** Chất lượng assertions và test boundaries mới là trọng tâm thực tế.

### 6.9. Thí nghiệm A — đặt ngưỡng quá cao để thấy gate FAIL

Trong **chỉ** rule BRANCH ở build.gradle, thay:

~~~groovy
minimum = 0.50
~~~

bằng:

~~~groovy
minimum = 1.00
~~~

Giữ rule LINE ở 0.50. Cấu hình BRANCH lúc này có dạng:

~~~groovy
rule {
    element = 'BUNDLE'
    limit {
        counter = 'BRANCH'
        value = 'COVEREDRATIO'
        minimum = 1.00
    }
}
~~~

Chạy:

~~~bash
./gradlew check --console=plain
~~~

**Kết quả kỳ vọng:** jacocoTestCoverageVerification **FAILED** vì vẫn còn nhánh validation không được thực thi. Gradle có thể báo violation tương tự “covered ratio is ... but expected minimum is 1.00”; giá trị thực tế và format lỗi phụ thuộc JaCoCo/Gradle version.

Điểm quan trọng:
- Hai JUnit tests **vẫn có thể PASS**.
- Report HTML vẫn được tạo nhờ dependencies đã cấu hình.
- **Coverage gate FAIL** vì chưa đạt yêu cầu BRANCH 100%.
- Đây không phải lỗi Gradle, cũng không có nghĩa assertEquals bị sai; nó là quyết định chất lượng của build.

### 6.10. Thí nghiệm B — thêm tests cho nhánh chưa covered

Bổ sung import:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
~~~

Và **thêm hai test methods** trong class GradePolicyTest:

~~~java
@Test
void rejectsNegativeScore() {
    assertThrows(
            IllegalArgumentException.class,
            () -> GradePolicy.classify(-1)
    );
    System.out.println("TEST_EXECUTED=negative");
}

@Test
void rejectsScoreAboveMaximum() {
    assertThrows(
            IllegalArgumentException.class,
            () -> GradePolicy.classify(101)
    );
    System.out.println("TEST_EXECUTED=aboveMaximum");
}
~~~

Đây là **đoạn bổ sung vào file GradePolicyTest.java**, không phải file standalone thứ hai. Sau khi thêm, có tổng cộng **4 test methods**.

**Vì sao cần hai case?**
- -1 làm nhánh **score < 0** true.
- 101 làm score < 0 false nhưng **score > 100** true.
- 80 và 20 đi qua hai kết quả score >= 60 true/false.
- Với class GradePolicy như trong lab, các nhánh điều kiện chính đều được thực thi.

Chạy:

~~~bash
./gradlew check --rerun-tasks --no-build-cache --console=plain
~~~

Nếu bạn chỉ thay ngưỡng BRANCH lên 1.00 và thêm hai tests nêu trên, kỳ vọng:
- 4 JUnit methods PASS.
- JacocoTestReport cập nhật từ execution data mới.
- JacocoTestCoverageVerification **PASS** với branch coverage đạt 100% cho class chính theo nhánh if/short-circuit đang đo.
- HTML/XML phản ánh source/bytecode/test version hiện tại.

**Lưu ý:** Không cố ấn định những giá trị covered lines/instructions/complexity phải giống hệt mọi JDK/JaCoCo version. Bài lab cố định **logic nhánh cần chạy**, còn metrics chi tiết do JaCoCo tính từ bytecode phát sinh.

### 6.11. Thí nghiệm C — đổi counter để hiểu ngưỡng

Giữ 4 tests và thay BRANCH bằng INSTRUCTION:

~~~groovy
rule {
    element = 'BUNDLE'
    limit {
        counter = 'INSTRUCTION'
        value = 'COVEREDRATIO'
        minimum = 0.80
    }
}
~~~

Cách hiểu: ít nhất 80% bytecode instructions đã được thực thi. Điều này **không tương đương** tối thiểu 80% branches hay 80% source lines. Hãy đọc HTML/XML để quan sát các counters khác nhau; đừng kỳ vọng tỉ lệ giống hệt.

Nếu muốn kiểm tra **mỗi class riêng**, đặt element='CLASS'. Nhưng class chỉ có private constructor chưa được gọi hoặc compiler-generated code có thể làm class-level instruction/line coverage khác với branch coverage. Hãy chọn rule theo ý nghĩa thực tế.

### 6.12. Java 17 demo không phụ thuộc JUnit

Để kiểm tra business behavior bằng javac/java ngoài Gradle test, tạo file:

**manual/demo/Main.java**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GradePolicy.classify(80));
        System.out.println(GradePolicy.classify(20));
    }
}
~~~

Vì thư mục **manual** không thuộc main source set mặc định, file này **không được tính vào coverage denominator của :test**. Nó chỉ là chương trình demo.

Biên dịch source main của Gradle:

~~~bash
./gradlew classes
~~~

Linux/macOS:

~~~bash
mkdir -p build/manual-classes
javac -encoding UTF-8 -cp build/classes/java/main \
  -d build/manual-classes manual/demo/Main.java
java -cp "build/classes/java/main:build/manual-classes" demo.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -encoding UTF-8 -cp build\classes\java\main -d build\manual-classes manual\demo\Main.java
java -cp "build\classes\java\main;build\manual-classes" demo.Main
~~~

**Stdout chính xác từ Main.main:**

~~~text
PASS
FAIL
~~~

**Quan trọng:** Chạy demo bằng java trực tiếp **không tự dùng JaCoCo agent**, nên lệnh trên **không bổ sung coverage vào test.exec**. Nếu muốn đo coverage của chương trình không phải Test task, hãy instrument JVM bằng JaCoCo hoặc dùng Gradle jacoco.applyTo trên một JavaForkOptions task đúng cách.

## 7. Phân biệt test report và JaCoCo report

| Nguồn báo cáo | Ví dụ đường dẫn | Trả lời câu hỏi gì? |
|---|---|---|
| **JUnit/Gradle test XML** | build/test-results/test/TEST-demo.GradePolicyTest.xml | Bao nhiêu test methods chạy/pass/fail/skip? |
| **Gradle test HTML** | build/reports/tests/test/index.html | Kết quả từng test và exceptions |
| **JaCoCo execution data** | build/jacoco/test.exec | Những code probes được đánh dấu trong lúc thực thi |
| **JaCoCo HTML** | build/reports/jacoco/test/html/index.html | Những packages/classes/lines/branches nào covered? |
| **JaCoCo XML** | build/reports/jacoco/test/jacocoTestReport.xml | Coverage counters ở dạng structured data cho CI |
| **Verification result** | Task :jacocoTestCoverageVerification | Coverage có đạt violationRules đã cấu hình? |

**Hai JUnit tests pass** có thể đi kèm **coverage 60%** hoặc **coverage 100%**, tùy chúng đi qua bytecode nào. Ngược lại, coverage 100% có thể đạt bằng tests không assert bất kỳ điều kiện nghiệp vụ quan trọng nào. Vì vậy cần ít nhất **test results + coverage metrics + review assertions**.

### 7.1. Vì sao test task FROM-CACHE khiến QA khó kết luận?

Nếu Test task bị FROM-CACHE, bộ kết quả và .exec tương ứng có thể được tái sử dụng. JaCoCo report có thể hợp lệ với inputs đã khóa, nhưng **nó không chứng minh tests được thực thi lại trong CI job hiện tại**.

Khi yêu cầu **fresh test execution**, dùng --rerun/--rerun-tasks cùng --no-build-cache và xác minh test methods thực sự được chọn/không bị skip. Khi mục tiêu chỉ là **đánh giá coverage của code có inputs không đổi**, reuse có thể phù hợp và tiết kiệm thời gian.

**Không dùng timestamps của HTML/XML như chứng cứ duy nhất** về fresh execution; các file có thể được tạo lại/restore từ cache mà không có test methods mới.

### 7.2. Khi test FAIL, report có được sinh không?

Với graph **verification → report → test**, nếu test task FAIL, Gradle có thể dừng trước khi chạy report. Nếu dự án cần coverage report **ngay cả khi tests fail**, có thể:
- Dùng task finalizer hợp lý như test.finalizedBy jacocoTestReport.
- Chạy Gradle với --continue để các task độc lập tiếp tục khi dependencies cho phép.
- Thiết kế pipeline thu artifacts và giữ exit status lỗi thật.

**Không bật test.ignoreFailures = true chỉ để tạo report rồi tuyên bố build chất lượng PASS.** Nếu quyết định cho phép test task không fail build trong một diagnostic workflow, báo cáo phải chỉ rõ sự thật.

## 8. Tách coverage theo class, package và module

### 8.1. Bundle-level thresholds

~~~groovy
violationRules {
    rule {
        element = 'BUNDLE'
        limit {
            counter = 'LINE'
            value = 'COVEREDRATIO'
            minimum = 0.80
        }
    }
}
~~~

Ưu điểm: dễ duy trì, tính tổng. Nhược: một package rất nhiều dòng được test tốt có thể **che** một package quan trọng ít dòng không được test.

### 8.2. Class-level thresholds

~~~groovy
violationRules {
    rule {
        element = 'CLASS'
        includes = ['demo.service.*']
        limit {
            counter = 'BRANCH'
            value = 'COVEREDRATIO'
            minimum = 0.70
        }
    }
}
~~~

Đây là snippet **minh họa** với package khác lab, dùng khi thật sự muốn mỗi class trong một nhóm đạt ngưỡng. Những utility classes không có branches có thể có counter semantics đặc biệt; không nên áp một ngưỡng branch cứng cho toàn bộ classes mà chưa xem report.

### 8.3. Package-level thresholds

~~~groovy
violationRules {
    rule {
        element = 'PACKAGE'
        includes = ['demo.*']
        limit {
            counter = 'LINE'
            value = 'COVEREDRATIO'
            minimum = 0.65
        }
    }
}
~~~

Dùng khi tổ chức muốn tất cả packages có coverage cơ bản. Khi một package là generated code hoặc chỉ chứa models, cần phân tích tính hợp lý trước khi đặt ngưỡng.

### 8.4. Ngưỡng theo module trong multi-project

Một Gradle multi-project build:

~~~text
root
├── core/
├── service/
└── app/
~~~

Nếu mỗi subproject Java áp jacoco, mỗi project thường có:
- **:core:test**, **:core:jacocoTestReport**, **:core:jacocoTestCoverageVerification**,
- **:service:test**, **:service:jacocoTestReport**, **:service:jacocoTestCoverageVerification**,
- **:app:test**, **:app:jacocoTestReport**, **:app:jacocoTestCoverageVerification**.

**Root project không tự có coverage cho tất cả subprojects** chỉ vì root áp jacoco. Tương tự, một report ở :app không mặc nhiên gom mọi JaCoCo execution data của các tests tại :core/:service.

Có thể áp một **convention plugin** để thiết lập common rules theo nhóm module; mỗi subproject áp plugin phù hợp theo policy. Nhưng module thực thi ít logic (DTOs) và module nghiệp vụ nhiều nhánh có thể cần ngưỡng khác nhau.

### 8.5. Aggregated coverage không tự có từ root task

Gradle cung cấp core plugin **jacoco-report-aggregation** để tạo báo cáo tổng cho JVM test suites theo mô hình variant-aware/aggregation. Nó là bài toán khác với jacocoTestReport đơn dự án.

Snippet minh họa trong project cần aggregate:

~~~groovy
plugins {
    id 'jacoco-report-aggregation'
}
~~~

Plugin này cần được dùng đúng với JVM Test Suite/Java models và khai báo **jacocoAggregation** hoặc project dependencies thích hợp. Một số aggregations có thể tự lấy dependencies khi áp trong distribution/application project. Nó **không phải** lệnh “quét mọi build/jacoco/*.exec của mọi project”.

Tài liệu Gradle hiện hành nói aggregation tạo **một report cho từng test suite name** (test, integrationTest...), không tự gộp tất cả suites thành một báo cáo duy nhất. Hãy thiết kế đúng module/test suite coverage scope trước khi đặt ngưỡng tổng.

## 9. Integration test và JaCoCo data của nhiều task

Nếu bạn có **integrationTest** kiểu Test, JaCoCo plugin có thể instrument nó như test:

~~~groovy
tasks.named('integrationTest') {
    useJUnitPlatform()
}
~~~

**Snippet yêu cầu project đã có task integrationTest đăng ký đúng.** Một dự án chỉ có Java Plugin thông thường không tự có integrationTest task. Bạn phải đăng ký source set/JVM test suite/task tương ứng trước.

Trong build có hai Test tasks:

~~~text
test            -> build/jacoco/test.exec
integrationTest -> build/jacoco/integrationTest.exec
~~~

Default **jacocoTestReport chỉ xử lý test suite test**, không tự gộp mọi integrationTest.exec. Nếu muốn report tổng cả hai suites **trong một project**, bạn có thể tạo custom JacocoReport task, chỉ định:
- executionData từ **cả hai Test tasks**,
- sourceSets main,
- dependencies đúng với cả hai Test tasks,
- reporting locations riêng.

### 9.1. Custom report minh họa

Với task integrationTest đã tồn tại:

~~~groovy
tasks.register('combinedCoverageReport', JacocoReport) {
    dependsOn tasks.named('test'), tasks.named('integrationTest')
    executionData tasks.named('test'), tasks.named('integrationTest')
    sourceSets sourceSets.main

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}
~~~

Đây là **snippet tùy chọn**; đừng chèn vào lab một-project chỉ có test task, vì integrationTest chưa tồn tại. Hình thức executionData task collection được JaCoCoReport API hỗ trợ với các Test/JaCoCo instrumented tasks. Nếu cấu trúc project phức tạp, hãy kiểm tra file paths và execute task dependencies trước khi kết luận đã merge đúng.

### 9.2. Verification phải đo cùng scope với report

Nếu combinedCoverageReport lấy test + integrationTest, nhưng jacocoTestCoverageVerification mặc định chỉ dùng **test.exec**, bạn có thể thấy:
- Combined HTML report đạt 85%.
- Verification trên test-only data báo 65% hoặc FAIL.

Đây là **khác scope**, không phải JaCoCo tính sai. Muốn gate tổng, tạo custom JacocoCoverageVerification task dùng cùng executionData/classDirectories/sourceDirectories theo chính sách đó. Không chỉ nhìn file HTML tổng rồi cho rằng task verification mặc định áp ngưỡng cho tổng.

### 9.3. Dữ liệu execution của project khác

Không gộp mọi .exec vào một report nếu:
- Class files được compile từ commits khác nhau.
- Các modules có duplicate class names/class IDs khác nhau.
- Cùng Java class xuất hiện với versions khác nhau.
- Tests dùng bytecode khác với classDirectories đưa vào report.

JaCoCo cần mapping execution data với **đúng class identities**. Nếu đưa dữ liệu không tương thích, report có thể cảnh báo hoặc đánh dấu missed mặc dù các tests thực tế đã chạy.

### 9.4. Chỉ muốn coverage từ unit tests?

Hãy giữ **jacocoTestReport** với test task, và mô tả policy rõ ràng:
- Unit coverage dùng làm regression signal.
- Integration coverage là một pipeline riêng.
- Nếu yêu cầu “tổng coverage”, cung cấp report aggregation/combined semantics đúng.

Tránh một con số không nói rõ suites mà người đọc tưởng nó đã bao gồm end-to-end tests.

## 10. Exclusions: tránh làm đẹp số liệu bằng cách loại mã khó test

### 10.1. Hai kiểu exclude khác nhau

| Cách exclude | Tầng tác động | Hậu quả |
|---|---|---|
| **Agent excludes** | JaCoCo Java agent không instrument classes khớp pattern | Không thu probes cho classes ấy |
| **Report classDirectories exclusions** | Không đưa classes vào dữ liệu phân tích/report | Classes ấy không ở denominator của report/verification nếu áp giống nhau |
| **Rule includes/excludes** | Chỉ lọc elements nào chịu rule | Report có thể vẫn hiển thị class ấy, nhưng threshold rule không đánh giá nó |
| **Test filtering** | Chọn test cases nào chạy | Thay lượng code được thực thi, không trực tiếp lọc classes khỏi denominator |

Nếu yêu cầu “không tính generated code vào KPI”, thường cần lọc **classDirectories** của **cả report và verification**, thay vì chỉ set agent excludes.

### 10.2. Một ví dụ report exclusion có kiểm soát

Giả sử code generator sinh classes dưới package demo.generated và tổ chức quyết định không tính chúng. Mẫu minh họa (không thuộc lab gốc):

~~~groovy
def qualityClasses = sourceSets.main.output.classesDirs
        .asFileTree
        .matching {
            exclude '**/generated/**'
        }

tasks.named('jacocoTestReport') {
    classDirectories.setFrom(qualityClasses)
}

tasks.named('jacocoTestCoverageVerification') {
    classDirectories.setFrom(qualityClasses)
}
~~~

Ý nghĩa: cả report và verification dùng **cùng tập class files đã lọc**, tránh chênh lệch số liệu. Path pattern phải khớp thực tế **compiled classes directories**, không phải chỉ path của source .java.

**Cẩn thận:** Quy tắc exclude ở đây có thể phải thay theo source sets, Kotlin/Android output paths hoặc generated class naming conventions. Không copy một pattern mà chưa xem các class có thật.

### 10.3. Chính sách exclude nên minh bạch

Hợp lý để cân nhắc exclude:
- Boilerplate/generated files mà tổ chức không kiểm soát behavior.
- Generated API clients do tool tái sinh và được test theo một chiến lược khác.
- Những adapter/framework glue classes thực sự không phù hợp gate riêng, có lý do review.

Không hợp lý:
- Exclude service xử lý thanh toán vì hiện chỉ có 20% coverage.
- Exclude toàn bộ nhánh exception vì khó test.
- Loại riêng class bị fail khi muốn tăng KPI ngay trước release.
- Đổi denominator mà không thông báo cho người so sánh trends.

Coverage trend chỉ có ý nghĩa khi **phạm vi đo** tương đối ổn định. Một dự án nâng từ 55% lên 90% sau khi exclude 40% classes không chứng minh tăng chất lượng kiểm thử.

## 11. Report XML trong CI và code quality platforms

### 11.1. Thu HTML và XML như build artifacts

Một CI job có thể chạy:

~~~bash
./gradlew clean check --console=plain
~~~

Khi cấu hình check → coverage verification → report → test:
- Nếu pass, có test results và coverage outputs.
- Nếu coverage threshold fail, report được sinh trước để lưu artifact, miễn tests thành công.
- CI phải lưu **exit code của check**, không chỉ upload HTML.
- CI nên archive **build/reports/jacoco/test/html/** và **build/reports/jacoco/test/jacocoTestReport.xml** cùng unit test reports.

**Đừng cấu hình CI chỉ chạy ./gradlew test rồi kết luận ngưỡng đã được áp**. Với mẫu bài lab, test không tự gọi report/verification.

### 11.2. SonarQube và XML ingestion

Các nền tảng như SonarQube/quality dashboards có thể nhập **JaCoCo XML**. Ví dụ thuộc tính thường dùng của SonarQube:

~~~properties
sonar.coverage.jacoco.xmlReportPaths=build/reports/jacoco/test/jacocoTestReport.xml
~~~

Đây là **snippet cấu hình công cụ phân tích**, không phải một trường cấu hình bắt buộc trong build.gradle của lab. Tên thuộc tính/đường dẫn cần đối chiếu với phiên bản tool đang sử dụng. **JaCoCo .exec không phải XML**; các integration hiện đại thường cần XML.

Nếu project là multi-module:
- Có thể cần nhiều XML paths hoặc một aggregate XML phù hợp.
- Report của mỗi module phải khớp compiled class/source files của module.
- Không cho cùng một XML vào nhiều module rồi mong công cụ hiểu scope tự động.

### 11.3. Coverage gate Gradle khác quality gate của dịch vụ ngoài

**jacocoTestCoverageVerification**: Gradle kiểm ngưỡng trực tiếp bằng JaCoCo rule trong build.

**SonarQube quality gate hoặc CI dashboard**: hệ thống bên ngoài có thể áp chính sách riêng, bao gồm coverage trên **new code**, code smells, duplication, security, tests hoặc metrics khác.

Hai gate này có thể đặt thresholds khác nhau và báo kết quả khác nhau. Chọn một **nguồn chính sách rõ ràng**, tránh bắt developer debug hai số 80% với denominators/scope không giống nhau mà không giải thích.

### 11.4. Cần test report và coverage report song song

Một release gate có thể yêu cầu:
- 100% unit test cases được chọn chạy thành công.
- BUNDLE line coverage ≥80%.
- BRANCH coverage ≥70%.
- Không có critical quality violations.
- Integration tests quan trọng pass trên môi trường phù hợp.

Đừng lấy line coverage 80% thay tiêu chí “unit tests phải pass”. Coverage là **một tín hiệu bổ sung**, không thay assertion correctness.

### 11.5. Khi report FAIL nhưng vẫn muốn giữ artifact

Nếu task verification FAIL sau khi report được sinh, CI nên thu thập report trong bước **always** hoặc tương đương theo CI platform. Không xóa build outputs trước khi archive. Bạn có thể đẩy artifact lưu tạm, nhưng giữ job status **FAILED**. Report dùng để điều tra, không phải lý do bỏ qua gate.

## 12. Những lỗi JaCoCo thường gặp và cách xử lý

### Lỗi 1 — Chạy test thành công nhưng không có HTML coverage

**Nguyên nhân:** Chỉ chạy test; jacocoTestReport không tự được lên lịch. Hoặc report task chưa có execution data.

**Cách sửa:** Chạy ./gradlew jacocoTestReport, thiết lập dependsOn test, kiểm tra build/jacoco/test.exec và task outcomes. Bật html.required nếu dự án đã tắt HTML.

### Lỗi 2 — Chạy check không kiểm tra ngưỡng

**Nguyên nhân:** Mặc định jacocoTestCoverageVerification không tự là dependency của check.

**Cách sửa:** Cấu hình check.dependsOn jacocoTestCoverageVerification; đồng thời bảo đảm verification có execution data và rules thực sự được định nghĩa.

### Lỗi 3 — Có HTML/XML nhưng gate không FAIL khi coverage thấp

**Nguyên nhân:** Report không phải verification; chưa có violationRules hoặc verification task không chạy.

**Cách sửa:** Thiết lập counter/value/minimum đúng, chạy jacocoTestCoverageVerification hoặc check được nối task graph. Kiểm tra selected rule element và classDirectories.

### Lỗi 4 — Đặt minimum = 80 thay vì 0.80

**Nguyên nhân:** COVEREDRATIO là tỷ lệ từ 0.0 đến 1.0, không phải số phần trăm 0–100.

**Cách sửa:** Dùng minimum = 0.80 cho 80%. Không dùng 80 trừ khi cấu hình kiểu/giá trị thực sự hỗ trợ notation khác và đã xác minh.

### Lỗi 5 — Nhầm LINE coverage và BRANCH coverage

**Nguyên nhân:** Một dòng if có thể được thực thi, nhưng chưa chạy cả true và false branches.

**Cách sửa:** Xem hai counters độc lập; viết test cho case boundary/invalid/else chứ không chỉ gọi method một lần.

### Lỗi 6 — File test.exec thiếu hoặc kích thước 0

**Nguyên nhân có thể:** Test không được chạy, không có test classes, JaCoCo agent bị disabled, test worker crash trước khi dump data, sai destination path hoặc report đọc sai file.

**Cách sửa:** Xem task :test outcome, test reports, JacocoTaskExtension.enabled/destinationFile, Gradle logs. Khi cần xác nhận fresh run, dùng --rerun-tasks --no-build-cache.

### Lỗi 7 — Coverage 0% mặc dù test methods đã chạy

**Nguyên nhân có thể:** execution data và class files không khớp; class loaders/proxies thay đổi bytecode; report trỏ nhầm classDirectories; test thực thi một phiên bản library khác.

**Cách sửa:** Mở HTML Sessions page kiểm tra class IDs; xác nhận Gradle Test task và JacocoReport đọc đúng outputs từ cùng build/source commit.

### Lỗi 8 — Source HTML không được tô màu

**Nguyên nhân:** Thiếu Java line debug information hoặc sourceDirectories không khớp đường dẫn class/package.

**Cách sửa:** Compile class files với debug info, cấu hình source root đúng, kiểm tra JaCoCo FAQ và report. Không tự thay phần trăm để che vấn đề hiển thị.

### Lỗi 9 — Ngưỡng CLASS fail nhưng BUNDLE pass

**Nguyên nhân:** BUNDLE là tỷ lệ tổng còn CLASS được áp cho từng class. Một class yếu có thể bị các classes tốt che trong tổng.

**Cách sửa:** Chọn policy đúng mức rủi ro, review excludes/included elements. Không coi kết quả khác nhau là lỗi của JaCoCo.

### Lỗi 10 — Chỉ thấy violation đầu tiên

**Nguyên nhân:** JaCoCo violation reporting có thể chỉ báo lỗi đầu tiên.

**Cách sửa:** Dùng HTML/XML để xem các class/branch chưa covered, tách rules hoặc nâng test quality rồi chạy lại verification.

### Lỗi 11 — Task FROM-CACHE nhưng team bảo tests mới chạy

**Nguyên nhân:** Gradle reused task outputs. .exec và coverage report có thể hợp lệ nhưng không chứng minh có fresh JUnit execution.

**Cách sửa:** Ghi nhận task outcomes rõ ràng; khi cần kiểm tra thời điểm hiện tại, rerun task thật và xác minh test events mới.

### Lỗi 12 — integrationTest không xuất hiện trong report

**Nguyên nhân:** Mặc định jacocoTestReport gắn với test suite test, không tự gộp integrationTest.exec.

**Cách sửa:** Tạo combined JacocoReport/JacocoCoverageVerification có cùng executionData/scope hoặc dùng aggregation plugin theo suite names.

### Lỗi 13 — Multi-project root báo coverage thấp bất thường

**Nguyên nhân:** Root report chỉ đo một project, thiếu data các modules, class directories sai hoặc có duplicate versions.

**Cách sửa:** Dùng jacoco-report-aggregation đúng variant/project dependencies, hoặc generate reports từng module rồi tổng hợp bằng công cụ phù hợp; xác định scope trước khi so metrics.

### Lỗi 14 — Report và verification có % khác nhau

**Nguyên nhân:** Hai task dùng khác executionData/classDirectories, exclusions, filtered elements hoặc thresholds đo counters khác nhau.

**Cách sửa:** Đối chiếu cả ba input groups và rule element/counter; bảo đảm policy đo đúng cùng tập mã.

### Lỗi 15 — Exclude generated code mà coverage tăng đột ngột

**Nguyên nhân:** Mẫu số coverage giảm; đây là thay đổi phạm vi tính, không phải nhất thiết viết thêm tests.

**Cách sửa:** Công bố policy excludes, giữ các rules đồng bộ và chú thích khi so sánh trends.

### Lỗi 16 — JaCoCo instrumentation lỗi sau khi nâng JDK

**Nguyên nhân:** JaCoCo version cũ có thể chưa hỗ trợ bytecode class-file format hoặc các tính năng Java mới.

**Cách sửa:** Kiểm tra JaCoCo changelog/compatibility, nâng toolVersion tương thích rồi chạy lại; đừng thay plugin ID core tùy tiện bằng một external version.

### Lỗi 17 — Report sinh nhưng Gradle task được đánh dấu NO-SOURCE/SKIPPED

**Nguyên nhân:** Không có execution data, test classes hoặc inputs phù hợp, task condition không được thỏa.

**Cách sửa:** Kiểm tra task graph và trạng thái ở từng giai đoạn test → report → verification; không công bố quality gate PASS nếu verification chưa thực thi.

### Lỗi 18 — Coverage data bị trộn giữa các commits

**Nguyên nhân:** Dùng .exec từ test run khác với compiled classes hiện tại; class IDs mismatch.

**Cách sửa:** Sinh test data và report từ cùng source/compiled artifacts trong pipeline có kiểm soát; bỏ data cũ không tương thích, tránh copy .exec tùy tiện.

### Lỗi 19 — Không có branch coverage trong class không chứa if/switch

**Nguyên nhân:** BRANCH counter đo những quyết định bytecode cụ thể, không có nghĩa mỗi class luôn có branches.

**Cách sửa:** Không ép branch ratio của class không có branches theo cách thiếu ý nghĩa; chọn BUNDLE/PACKAGE policies hoặc phân loại classes.

### Lỗi 20 — Thay ngưỡng 100% rồi thêm test nhưng gate vẫn fail

**Nguyên nhân có thể:** Còn branch chưa covered, generated class trong scope, compiler bytecode có nhánh bổ sung, test filter không chọn case mới, .exec/cache cũ, hoặc verification đang đọc khác classDirectories.

**Cách sửa:** Đọc HTML/XML theo class/counter, chạy tests mới thật, xác nhận report regenerated và điều chỉnh **đúng tests**. Không giảm ngưỡng mù chỉ để build xanh.

## 13. Checklist triển khai trong dự án thật

1. Đã áp **java/java-library** và **jacoco** vào đúng subproject?
2. JaCoCo **toolVersion** có phù hợp JDK/Gradle của CI?
3. Test framework dependencies/JUnit Platform có cấu hình đúng không?
4. Task **test** có thực thi thật khi cần fresh data không?
5. JaCoCo execution data file có đúng path và gắn với test task tương ứng?
6. Report task có **dependsOn test** hoặc task ordering hợp lệ?
7. HTML/XML required flags có đúng và file được sinh trong CI?
8. classDirectories/sourceDirectories có khớp compiled classes và sources được test?
9. Verification task có rules và đọc đúng executionData?
10. **check** đã dependsOn verification khi coverage là bắt buộc?
11. Ngưỡng dùng COVEREDRATIO từ 0 đến 1, không nhầm %?
12. Counter LINE/BRANCH/INSTRUCTION đúng theo KPI cần đo?
13. Element BUNDLE/CLASS/PACKAGE đúng phạm vi tổ chức?
14. Exclusions có lý do review, không cố giấu business logic chưa test?
15. Report và verification có thống nhất scope/exclusions không?
16. Multi-project/tests suites đã được aggregate theo mô hình phù hợp?
17. CI có archive HTML/XML/test report khi gate FAIL không?
18. Có ghi rõ task cache hits/UP-TO-DATE vs fresh tests không?
19. Tests có assertions tốt và edge cases quan trọng, không chỉ coverage 100%?
20. Team có xem biến động coverage theo **cùng denominator** và giữ gate trong version control không?

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1.** Có thể tạo HTML coverage chỉ bằng execution data .exec, không có .class files không?

**Bài 2.** Khi chỉ chạy ./gradlew test, Gradle có bắt buộc tạo HTML JacocoTestReport không?

**Bài 3.** Tại sao report.dependsOn(test) không đồng nghĩa tests luôn chạy mới trong CI job?

**Bài 4.** jacocoTestCoverageVerification có tự chạy khi gọi check theo mặc định không? Phải làm gì nếu muốn bắt buộc?

**Bài 5.** Rule minimum = 0.80 với LINE COVEREDRATIO nghĩa là bao nhiêu phần trăm?

**Bài 6.** BUNDLE LINE 80% có bảo đảm mỗi class đều LINE 80% không?

**Bài 7.** LINE và BRANCH coverage khác nhau thế nào với if/else?

**Bài 8.** Vì sao một test không có assertion vẫn có thể làm JaCoCo coverage tăng?

**Bài 9.** File build/jacoco/test.exec có thể chứng minh tests chạy hôm nay khi :test FROM-CACHE không?

**Bài 10.** Trong bài lab, hai tests 80 và 20 đã cover cả hai kết quả PASS/FAIL. Vì sao BRANCH 100% chưa chắc đạt?

**Bài 11.** Hai test cases nào cần thêm trong lab để cover input validation score <0 và score >100?

**Bài 12.** Trường hợp JacocoTestReport HTML đạt 90% nhưng JacocoCoverageVerification báo FAIL 75%, bạn sẽ kiểm tra điều gì trước?

**Bài 13.** Custom integrationTest task có data integrationTest.exec. Default jacocoTestReport có tự gộp file ấy không?

**Bài 14.** Nếu report classDirectories exclude generated code nhưng verification không exclude, hai kết quả có thể khác nhau không?

**Bài 15.** Một project không có branch nào. Có phù hợp bắt mọi class BRANCH 100% không?

**Bài 16.** JaCoCo count constructors và static initializers trong những counters nào?

**Bài 17.** Vì sao thay JDK/JaCoCo version có thể làm tỉ lệ lines/instructions thay đổi dù source giống nhau?

**Bài 18.** Muốn công cụ CI phân tích code quality đọc report, HTML hay XML thường là lựa chọn phù hợp hơn?

**Bài 19.** Nếu muốn kiểm tra ngưỡng cho **mỗi class**, element phải đặt thế nào?

**Bài 20.** Tại sao một rule có minimum=0.50 không có nghĩa project có chất lượng 50%?

### Gợi ý đáp án

1. **Không.** Cần .class bytecode phù hợp; sources giúp map/tô màu lines.
2. **Không.** Mặc định jacocoTestReport không phải phần bắt buộc của test.
3. Test task vẫn có thể UP-TO-DATE/FROM-CACHE, không gọi JUnit mới.
4. **Không tự động**; thêm check.dependsOn jacocoTestCoverageVerification.
5. **80%**.
6. **Không.** BUNDLE tính tổng; từng class có thể thấp hơn.
7. LINE quan sát source lines có instructions được chạy; BRANCH quan sát đường true/false/switch, một line có thể chỉ covered một nhánh.
8. JaCoCo đo execution, không đánh giá độ mạnh của assertion.
9. **Không.** .exec có thể là output cũ hoặc được cache phục hồi.
10. Validation cho -1 và 101 chưa được thực thi, còn branches chưa covered.
11. Thêm assertThrows cho classify(-1) và classify(101).
12. Kiểm tra **counter, element, executionData, classDirectories, exclusions và test suite scope** có giống nhau không.
13. **Không**; cần combined report hoặc aggregation đúng suite.
14. **Có**; denominator khác, policy khác.
15. **Thường không**; branch counter có thể không áp dụng cho class ấy.
16. Chúng có thể được tính trong **METHOD/CLASS** và INSTRUCTION/LINE nếu có bytecode tương ứng.
17. Bytecode/line mapping khác nhau, JaCoCo instrumentation/counters có thể thay đổi theo JDK/compiler version.
18. **XML** cho machine ingestion; HTML để người đọc xem.
19. **element = 'CLASS'**.
20. Coverage chỉ phản ánh phần code được thực thi dưới những test inputs, không đo mức độ đúng đắn, assertions, security, concurrency hoặc behavior coverage.

## Tài liệu chính thức

- [Gradle User Manual — The JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): plugin, agent, jacocoTestReport, jacocoTestCoverageVerification, default wiring và violationRules.
- [Gradle DSL — JacocoReport](https://docs.gradle.org/current/dsl/org.gradle.testing.jacoco.tasks.JacocoReport.html): executionData, classDirectories, sourceDirectories và reports.
- [Gradle DSL — JacocoCoverageVerification](https://docs.gradle.org/current/dsl/org.gradle.testing.jacoco.tasks.JacocoCoverageVerification.html): violationRules và ngưỡng kiểm tra.
- [Gradle API — JacocoTaskExtension](https://docs.gradle.org/current/javadoc/org/gradle/testing/jacoco/plugins/JacocoTaskExtension.html): agent destinationFile, includes/excludes, dumpOnExit.
- [Gradle User Manual — JaCoCo Report Aggregation](https://docs.gradle.org/current/userguide/jacoco_report_aggregation_plugin.html): aggregation theo JVM test suite và project variants.
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Java Test task, JUnit Platform, test results, rerun/skip semantics.
- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): UP-TO-DATE/FROM-CACHE, cacheable Test/JacocoReport tasks.
- [JaCoCo Official Documentation — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): LINE/BRANCH/INSTRUCTION/METHOD/CLASS/COMPLEXITY definitions.
- [JaCoCo Official Documentation — Report Checks](https://www.jacoco.org/jacoco/trunk/doc/ant.html): rule elements, counters, ratio/count values và thresholds.
- [JaCoCo Official Documentation — FAQ](https://www.jacoco.org/jacoco/trunk/doc/faq.html): debug symbols, matching classes, source highlighting.
- [JaCoCo Official Documentation — Class IDs](https://www.jacoco.org/jacoco/trunk/doc/classids.html): class-file mismatch và coverage 0% bất thường.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter @Test, assertEquals, assertThrows.

**Ghi nhớ:** **test** chạy Java/JUnit với JaCoCo agent và tạo **.exec**; **jacocoTestReport** phân tích data/classes/sources thành HTML/XML/CSV; **jacocoTestCoverageVerification** thực thi ngưỡng coverage. **Report không tự chạy test; verification không tự nằm trong check** — hãy nối task graph rõ ràng. Dùng đúng **counter, element, minimum và class scope**, test các nhánh quan trọng, tránh exclusions làm sai mẫu số, và không đánh đồng coverage cao với assertions đúng hoặc chất lượng phần mềm đã được bảo đảm.
# onlyIf, enabled, điều kiện bỏ qua và xử lý lỗi task trong Gradle

## 1. Mục tiêu bài học

Một task trong Gradle có thể **được chọn vào task graph** nhưng không chạy phần việc của chính nó. Ngược lại, khi một task gặp lỗi, Gradle có thể dừng build, chạy tác vụ dọn dẹp hoặc tiếp tục những task độc lập theo cách được yêu cầu. Hai câu hỏi “có chạy hay không?” và “nếu chạy thất bại thì xử lý ra sao?” cần được giải quyết riêng.

Bài học thuộc chủ đề **Task và đồ thị**, tập trung vào:

- Dùng **onlyIf { ... }** để đặt điều kiện chạy task; hiểu thời điểm đánh giá và trạng thái **SKIPPED**.
- Dùng **enabled = false** để vô hiệu hóa task và hiểu sự khác biệt với **onlyIf**.
- Phân biệt **SKIPPED**, **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**, **FAILED** và task không được đưa vào graph.
- Hiểu tác động lên **dependsOn**, **mustRunAfter**, **finalizedBy** và những task dùng output của task bị bỏ qua.
- Phân biệt **StopActionException**, **StopExecutionException**, lỗi thực sự và lựa chọn **--continue**.
- Xây dựng ví dụ Java 17 và Gradle Groovy DSL có thể chạy, thử từng trường hợp và giải thích stdout/exit status.
- Áp dụng các nguyên tắc thực tế cho unit test, CI và phát hành mà không che giấu lỗi.

## 2. Task graph được xác định trước khi xét nhiều điều kiện bỏ qua

Gradle đọc settings/build scripts, nhận các task được yêu cầu và lập **đồ thị phụ thuộc** (task graph). Mỗi task có thể có quan hệ:

- **dependsOn(X)**: task hiện tại yêu cầu X hoàn thành trước.
- **mustRunAfter(X)**: khi cả hai task cùng có mặt trong graph, task hiện tại phải chạy sau X; quan hệ này **không** tự đưa X vào graph.
- **shouldRunAfter(X)**: ưu tiên thứ tự mềm khi khả thi, không tạo dependency và có thể không áp dụng trong một số tình huống.
- **finalizedBy(X)**: bổ sung task X để làm công việc cuối cùng khi task chính được lên lịch, hữu ích cho dọn dẹp tài nguyên.

Ví dụ:

~~~groovy
def prepare = tasks.register('prepare') {
    doLast { println 'PREPARED' }
}

tasks.register('packageReport') {
    dependsOn(prepare)
    doLast { println 'PACKAGED' }
}
~~~

Khi chạy **./gradlew -q packageReport**, Gradle chạy **prepare** trước **packageReport**:

~~~text
PREPARED
PACKAGED
~~~

Thêm **onlyIf { false }** vào **packageReport** sẽ bỏ qua action của chính task này khi đến lượt kiểm tra; việc **prepare** đã được đưa vào graph bằng quan hệ **dependsOn** không tự biến mất. Điều kiện chạy task khác với điều kiện **tạo graph**. Đây là nguồn gốc của nhiều nhầm lẫn: “Tôi đã skip task đích, sao dependency vẫn chạy?”.

Mô hình khái niệm:

~~~text
Yêu cầu packageReport
        |
        v
Graph chứa prepare -> packageReport
        |
        v
prepare được xử lý
        |
        v
Đến lượt packageReport
        |
        +-- onlyIf false / enabled=false --> SKIPPED, bỏ qua actions
        |
        +-- điều kiện cho phép --> xét trạng thái input/output, thực thi nếu cần
~~~

Sơ đồ đã lược bớt các bước tối ưu và kiểm tra đặc thù của Gradle. **Điều quan trọng:** điều kiện skip không phải cơ chế dựng lại graph để loại tất cả các task phụ thuộc đã được chọn.

## 3. onlyIf: điều kiện chạy được đánh giá khi đến lượt task

### 3.1. Cú pháp cơ bản

**onlyIf** là API trên task, nhận một predicate. Khi predicate trả **true**, task được phép đi tiếp; khi trả **false**, các action của task không chạy và kết quả có thể hiển thị **SKIPPED**.

~~~groovy
tasks.register('conditionalReport') {
    onlyIf { false }
    doLast {
        println 'REPORT'
    }
}
~~~

Chạy:

~~~bash
./gradlew conditionalReport
~~~

Kỳ vọng thấy dòng trạng thái tương tự:

~~~text
> Task :conditionalReport SKIPPED
~~~

Không thấy **REPORT** vì action không được thực thi. Build vẫn có thể kết thúc thành công vì đây là một quyết định bỏ qua có chủ đích, không phải lỗi task.

Predicate được Gradle kiểm tra **ngay trước khi task cần được thực thi**, không phải ngay khi đăng ký trong configuration phase. Vì vậy nó phù hợp với quyết định “task có thực sự nên làm công việc này trong lần chạy hiện tại hay không?”.

### 3.2. Đưa lý do vào onlyIf

Trong Gradle hiện đại, có thể truyền một chuỗi mô tả:

~~~groovy
tasks.register('report') {
    onlyIf('demo.report=true mới tạo báo cáo') {
        true
    }
    doLast {
        println 'REPORT GENERATED'
    }
}
~~~

Ở đây predicate luôn true, chỉ minh họa chữ ký API. Một ví dụ có điều kiện thực tế:

~~~groovy
def reportFlag = providers.gradleProperty('demo.report').map { raw ->
    if (raw != 'true' && raw != 'false') {
        throw new GradleException('demo.report chỉ nhận true hoặc false')
    }
    raw == 'true'
}.orElse(false)

tasks.register('report') {
    onlyIf('demo.report phải bằng true') {
        reportFlag.get()
    }
    doLast {
        println 'REPORT GENERATED'
    }
}
~~~

Nếu không truyền **-Pdemo.report=true**, action không chạy. Nếu truyền **-Pdemo.report=true**, action chạy. **reportFlag** là **Provider<Boolean>**, được khai báo ở configuration rồi đọc tại thời điểm predicate được đánh giá.

Trong log, chạy:

~~~bash
./gradlew report --info
~~~

Khi predicate false, Gradle có thể in nguyên nhân tương ứng với chuỗi mô tả của **onlyIf**, giúp phân biệt một lần skip có chủ đích với lỗi input khác.

### 3.3. Nhiều onlyIf có quan hệ AND

Một task có thể được cấu hình nhiều predicate qua những lời gọi **onlyIf** riêng:

~~~groovy
tasks.register('protectedTask') {
    onlyIf { true }
    onlyIf { false }
    doLast { println 'NEVER' }
}
~~~

Gradle chỉ cho phép task chạy nếu **tất cả predicate đều thỏa**. Chỉ cần một predicate trả false, task bị bỏ qua. Quy tắc này hữu ích khi nhiều plugin/convention cùng thêm điều kiện, nhưng cũng làm khó debug nếu bạn chỉ nhìn điều kiện gần nhất.

Nếu một task bất ngờ **SKIPPED**, hãy kiểm tra mọi nơi cấu hình **onlyIf**, không chỉ block trong **build.gradle** hiện tại. Có thể có plugin hoặc convention plugin gắn thêm điều kiện.

### 3.4. Điều kiện nên nhỏ, dễ hiểu và không có side effect

Predicate nên biểu diễn một quyết định boolean, ví dụ “cờ báo cáo được bật” hoặc “môi trường có hỗ trợ công cụ này”. Tránh đặt vào predicate một lệnh xóa file, gọi mạng, xuất bản artifact hay sửa task khác. Một predicate có side effect có thể gây lỗi khi build được chạy lại hoặc sử dụng configuration cache.

Với điều kiện lấy từ Gradle property, parse rõ ràng giá trị **String**. Ví dụ **-Pdemo.report=false** tạo chuỗi **'false'**, là chuỗi không rỗng và được Groovy xem như true trong kiểm tra truthiness; đừng viết:

~~~groovy
onlyIf {
    providers.gradleProperty('demo.report').get() // String 'false' vẫn truthy
}
~~~

Hãy chuyển sang boolean đúng nghĩa như **raw == 'true'** hoặc validate cả hai lựa chọn như trên.

**Nếu điều kiện bắt buộc phải có kết quả trước khi lập task graph**, chỉ dùng **onlyIf** là chưa đủ. Khi đó cần thiết kế lifecycle task/graph hoặc tạo task theo điều kiện ở thời điểm cấu hình một cách rõ ràng, đảm bảo configuration cache và việc chọn task được kiểm soát.

## 4. enabled: bật hoặc tắt cả task

Mỗi Task có thuộc tính **enabled**, mặc định true. Đặt **enabled = false** khiến Gradle không chạy action của task; task được ghi nhận là **SKIPPED** khi được chọn.

~~~groovy
tasks.register('disabledReport') {
    enabled = false
    doLast {
        println 'THIS MUST NOT APPEAR'
    }
}
~~~

Chạy **./gradlew disabledReport**:

~~~text
> Task :disabledReport SKIPPED
~~~

Điểm khác biệt với **onlyIf**:

| Góc nhìn | **onlyIf { predicate }** | **enabled = false** |
| --- | --- | --- |
| Mục đích | Chạy có điều kiện theo predicate | Vô hiệu hóa task |
| Kiểu quyết định | Boolean được đánh giá khi task đến lượt | Thuộc tính trạng thái của Task, thường đặt trong configuration |
| Mô tả lý do | Có overload **onlyIf('lý do') { ... }**, quan sát qua **--info** | Không tự có lý do predicate; nên tài liệu hóa tại điểm đặt |
| Kết quả khi task được chọn | **SKIPPED** nếu predicate false | **SKIPPED** khi disabled |
| Tác động tới dependency | Không tự loại toàn bộ task dependency khỏi graph | Cũng không phải cách tự cắt toàn bộ graph |
| Phù hợp | Job tùy chọn có chính sách rõ ràng | Vô hiệu hóa một task không được sử dụng trong build cụ thể |

Trong thực tế, nên dùng **onlyIf** cho một task hợp lệ nhưng chỉ thực hiện ở vài môi trường; dùng **enabled = false** khi muốn tắt hẳn một task do plugin cung cấp, chẳng hạn vì module không có nhu cầu chạy task đó. Trước khi vô hiệu hóa task mặc định của Java/QA/publishing plugin, kiểm tra xem những task khác có phụ thuộc vào đầu ra của nó không.

Ví dụ cấu hình một task plugin được tạo sẵn:

~~~groovy
plugins {
    id 'java'
}

tasks.named('jar', Jar) {
    enabled = false
}
~~~

Đây là **đoạn minh họa có chủ đích**: tắt **jar** có thể làm hỏng các quy trình phụ thuộc artifact của module. Không áp dụng bừa bãi trong một dự án cần publish JAR. Hãy xem **enabled** là chính sách vô hiệu hóa một task cụ thể, không phải mẹo tăng tốc build vô điều kiện.

## 5. SKIPPED khác những trạng thái không chạy khác

Khi quan sát output Gradle, cần phân biệt những trạng thái sau:

| Trạng thái | Ý nghĩa khái quát | Hướng điều tra |
| --- | --- | --- |
| **EXECUTED** hoặc không có nhãn | Task có action được thực thi bình thường | Kiểm tra stdout, output, report |
| **SKIPPED** | Task được đưa vào graph nhưng action không chạy vì điều kiện/disabled/cách skip khác | Xem **onlyIf**, **enabled**, **--info** |
| **UP-TO-DATE** | Gradle xác định task không cần làm lại công việc vì trạng thái input/output phù hợp | Xem khai báo input/output, incremental build |
| **FROM-CACHE** | Output của task đủ điều kiện được tái sử dụng từ build cache | Xem build cache và tính đúng đắn input/output |
| **NO-SOURCE** | Task có loại input nguồn cần xử lý nhưng không tìm thấy nguồn cần thiết | Kiểm tra source set, include/exclude, đường dẫn |
| **FAILED** | Task gặp lỗi, exception hoặc một kiểm tra bắt buộc không đạt | Đọc lỗi đầu tiên, stacktrace và report |
| **Không xuất hiện trong graph** | Task không được chọn, không là dependency/finalizer cần thiết hoặc đã bị loại khỏi graph | Xem task path, task graph, **-x** và lifecycle |

Ví dụ khi lệnh **./gradlew build** cho thấy **:compileJava NO-SOURCE**, đó không có nghĩa có một predicate **onlyIf** từ chối chạy. Nếu thấy **:test UP-TO-DATE**, cũng không tương đương task test bị vô hiệu hóa. Với CI, **SKIPPED** và **UP-TO-DATE** có ý nghĩa chất lượng khác nhau; cần kiểm tra bằng chứng test/report, không chỉ nhìn **BUILD SUCCESSFUL**.

### 5.1. Vì sao -x test khác onlyIf?

Lệnh:

~~~bash
./gradlew build -x test
~~~

chủ động **loại task test khỏi tập task cần chạy** theo cơ chế exclude-task. Task **test** và những dependency chỉ riêng nó cần có thể không xuất hiện trong graph. Ngược lại, task có **onlyIf { false }** có thể vẫn được lên lịch cùng các dependency của nó rồi mới bị ghi **SKIPPED**.

Điều này giải thích vì sao **-x test** đôi khi nhanh hơn theo một cách khác, nhưng cũng nguy hiểm hơn: nó có thể cắt bỏ cả những kiểm tra chất lượng hoặc output được task khác mong đợi. Gradle khuyến nghị thiết kế lifecycle task phù hợp thay vì thường xuyên dùng **-x** để né những kiểm tra quan trọng.

### 5.2. --rerun-tasks không phá điều kiện false

~~~bash
./gradlew report --rerun-tasks
~~~

**--rerun-tasks** yêu cầu thực thi lại những task có thể được chạy, bỏ qua cơ chế up-to-date; nó **không biến một predicate onlyIf false thành true**. Nếu task vẫn SKIPPED, đừng cố xóa cache hoặc clean liên tục; hãy kiểm tra điều kiện chạy.

## 6. Tác động lên dependency, consumer và graph

### 6.1. Task dependency có thể chạy dù task đích bị skip

Ví dụ:

~~~groovy
def prepare = tasks.register('prepareData') {
    doLast { println 'PREPARE DATA' }
}

tasks.register('publishData') {
    dependsOn(prepare)
    onlyIf { false }
    doLast { println 'PUBLISH DATA' }
}
~~~

Khi gọi **./gradlew -q publishData**, dòng in từ các action:

~~~text
PREPARE DATA
~~~

**PUBLISH DATA** không được in. Điều này bình thường: Gradle đã lập graph chứa **prepareData** vì **publishData** phụ thuộc nó, sau đó mới đánh giá skip của task đích.

### 6.2. Task consumer có thể lỗi nếu producer bị skip

Giả sử **generateFile** tạo **build/generated/config.json**, còn **processFile** phụ thuộc vào file đó. Nếu **generateFile** bị skip nhưng consumer vẫn cố đọc file, hành vi có thể là:

- Consumer báo file không tồn tại.
- Consumer vô tình đọc một file cũ còn lại từ lần chạy trước.
- Consumer sử dụng fallback không được kiểm soát, dẫn đến kết quả sai.

**Không coi SKIPPED như một bằng chứng output đã được tạo.** Nếu hai task chỉ hợp lệ khi bật cùng tính năng, hãy đặt điều kiện nhất quán lên cả hai task hoặc thiết kế consumer có input tùy chọn và kiểm tra trạng thái file đúng API. Tốt hơn nữa, dùng **RegularFileProperty/Provider** để mô tả producer–consumer, khai báo input/output và dependency; không đọc file output trong configuration phase.

Nếu một task producer không làm công việc của nó, bạn phải quyết định **consumer có nên chạy hay không**. Gradle không thể tự suy luận tất cả nghiệp vụ của ứng dụng từ **onlyIf false**.

### 6.3. mustRunAfter không phải dependsOn

~~~groovy
def first = tasks.register('first') {
    doLast { println 'FIRST' }
}

tasks.register('second') {
    mustRunAfter(first)
    doLast { println 'SECOND' }
}
~~~

Chạy **./gradlew -q second** chỉ cần in **SECOND**; **first** không được thêm vào graph bằng **mustRunAfter**. Khi cả hai cùng được chọn, Gradle tôn trọng thứ tự **FIRST** trước **SECOND**.

Trong các ví dụ dọn dẹp hoặc dữ liệu bắt buộc, dùng **dependsOn** hay **finalizedBy** khi thực sự cần task khác tham gia, đừng dùng **mustRunAfter** như cách thay cho dependency.

## 7. StopActionException và StopExecutionException: bỏ qua khi task đã bắt đầu

Gradle cung cấp hai loại exception đặc biệt cho chuỗi task actions:

- **StopActionException**: dừng action hiện tại và tiếp tục với action kế tiếp của **cùng task**.
- **StopExecutionException**: dừng action hiện tại và bỏ qua các action còn lại của **task hiện tại**, rồi tiếp tục các task khác theo graph.

Chúng là cơ chế điều khiển luồng chuyên biệt, **khác với GradleException hoặc một lỗi Java thông thường**. Dùng **onlyIf** nếu có thể biểu diễn điều kiện trước khi thực thi; chỉ dùng các exception này khi cần quyết định trong quá trình action đang chạy, hoặc muốn ngắt các action có sẵn của task plugin.

### 7.1. StopActionException

Đoạn minh họa Groovy DSL:

~~~groovy
tasks.register('partialAction') {
    doFirst {
        println 'ACTION 1'
        throw new StopActionException()
    }
    doLast {
        println 'ACTION 2'
    }
}
~~~

Chạy **./gradlew -q partialAction**. Các dòng do ví dụ in:

~~~text
ACTION 1
ACTION 2
~~~

Exception đã dừng phần còn lại của action thứ nhất, nhưng action thứ hai vẫn chạy. Nếu action đầu có câu lệnh sau chỗ throw, câu lệnh ấy sẽ không chạy.

### 7.2. StopExecutionException

~~~groovy
tasks.register('stopCurrentTask') {
    doFirst {
        println 'CHECK'
        throw new StopExecutionException()
    }
    doLast {
        println 'NOT EXECUTED'
    }
}

tasks.register('nextTask') {
    dependsOn('stopCurrentTask')
    doLast {
        println 'NEXT TASK'
    }
}
~~~

Chạy **./gradlew -q nextTask**. Các dòng do hai task in:

~~~text
CHECK
NEXT TASK
~~~

**NOT EXECUTED** không xuất hiện vì các action còn lại của **stopCurrentTask** bị bỏ qua. Build có thể tiếp tục mà không coi chính exception đặc biệt này là lỗi build.

Chú ý: **StopExecutionException không quay ngược công việc đã thực hiện** trước lúc throw. Nếu action đã tạo file hoặc tác động hệ thống bên ngoài, các thay đổi đó không tự được rollback. Với điều kiện đơn giản, **onlyIf** đặt trước actions giúp tránh phần việc dở dang.

## 8. Task thất bại thật: lỗi, exit status và --continue

### 8.1. Exception thông thường làm task FAILED

~~~groovy
tasks.register('failingDemo') {
    doLast {
        println 'START FAILING TASK'
        throw new GradleException('Lỗi minh họa có chủ đích')
    }
}
~~~

Khi gọi **./gradlew failingDemo**, task thất bại và Gradle báo **BUILD FAILED** với exit code khác 0. Đây là kết quả đúng: ta đã ném **GradleException** thông thường, không phải một exception điều khiển luồng bỏ qua task.

Trong Java plugin, một lỗi biên dịch, lỗi test hoặc lỗi xử lý artifact cũng có thể làm task thất bại. Đừng biến **FAILED** thành **SKIPPED** chỉ để pipeline có dấu xanh; cần đọc nguyên nhân.

### 8.2. --continue chạy thêm task độc lập nhưng build vẫn FAILED

Khi gặp task lỗi, hành vi mặc định là ngừng các task tiếp theo theo đường thực thi đang được xử lý. Tùy chọn:

~~~bash
./gradlew failingDemo unrelatedDemo --continue
~~~

cho phép Gradle tiếp tục những task mà **toàn bộ dependency bắt buộc của chúng đã hoàn thành thành công**. Những task có dependency thất bại **không được phép chạy** chỉ vì có **--continue**. Cuối cùng Gradle vẫn tổng hợp lỗi và trả build status **FAILED** nếu có lỗi chưa xử lý.

**--continue** hữu ích cho CI muốn thu thập nhiều lỗi độc lập trong một lượt, chẳng hạn test nhiều module. Nó không phải “ignore errors” hay công tắc bắt mọi task tiếp tục bất kể dữ liệu có hợp lệ hay không.

### 8.3. finalizedBy để chạy dọn dẹp khi task chính lỗi

Ví dụ dùng finalizer task:

~~~groovy
def cleanup = tasks.register('cleanupDemo') {
    doLast {
        println 'CLEANUP'
    }
}

tasks.register('failingDemo') {
    finalizedBy(cleanup)
    doLast {
        println 'FAIL START'
        throw new GradleException('FAIL_DEMO')
    }
}
~~~

Chạy **./gradlew failingDemo**: task chính in **FAIL START** rồi thất bại; finalizer được chạy và in **CLEANUP**, nhưng trạng thái build cuối cùng vẫn **FAILED**. Finalizer cũng được Gradle chạy nếu task đã hoàn thành ở trạng thái **UP-TO-DATE** theo quy tắc của finalizer.

Dùng finalizer khi cần **đóng server thử nghiệm, giải phóng tài nguyên, dọn môi trường** ngay cả khi integration test thất bại. Đừng dùng finalizer để xóa bằng chứng lỗi (logs/report) mà CI còn cần.

### 8.4. Task không được bỏ qua lỗi tùy tiện

Một antipattern:

~~~groovy
tasks.register('deploy') {
    doLast {
        try {
            throw new GradleException('deploy thất bại')
        } catch (Exception ignored) {
            println 'DEPLOY OK'
        }
    }
}
~~~

Đoạn này cố ý sai về nghiệp vụ: nó nuốt lỗi rồi in **DEPLOY OK**, dẫn đến CI có thể hiểu thành công dù triển khai thất bại. Khi lỗi phải làm build thất bại, hãy để exception đi lên hoặc ném **GradleException** có thông tin rõ ràng. Chỉ catch một lỗi khi có **phương án phục hồi đúng và có thể chứng minh**.

Với môi trường sản xuất, tách trạng thái **build**, **test**, **publish** và **deploy**. Không sử dụng **onlyIf** hoặc **enabled=false** như cách làm một đợt phát hành thất bại “biến mất”.

## 9. Xử lý lỗi kiểm thử: ignoreFailures, failFast và quality gate

Task kiểu **Test** trong Gradle có các property riêng:

- **ignoreFailures** (mặc định false với Java plugin): khi true, kiểm thử có thể thất bại nhưng task không chặn toàn build; báo cáo test vẫn cần được đọc.
- **failFast**: dừng sớm trong quá trình test sau khi gặp test thất bại, thích hợp khi tiết kiệm thời gian quan trọng.
- **onlyIf** trên task Test: có thể bỏ qua **toàn bộ quá trình chạy test** theo điều kiện.
- **enabled = false** trên task Test: vô hiệu hóa task test đã cấu hình.
- **--continue**: giữ lỗi test là lỗi nhưng tiếp tục các task độc lập khác đủ điều kiện.

**Đoạn minh họa**, chỉ dùng trong project đã áp dụng Java plugin:

~~~groovy
plugins {
    id 'java'
}

tasks.named('test', Test) {
    ignoreFailures = false
    failFast = false
}
~~~

Với JUnit 5, còn cần dependency test phù hợp và **useJUnitPlatform()**. Không thay **ignoreFailures = true** vào cấu hình CI chỉ vì muốn tạo report sau khi test fail: thường có thể dùng **--continue**, **finalizedBy** hoặc cơ chế lưu report của CI mà vẫn giữ kết quả quality gate là lỗi.

### 9.1. Tình huống CI thực tế

Giả sử hai module **:core:test** và **:api:test** độc lập. Chạy:

~~~bash
./gradlew :core:test :api:test --continue
~~~

Nếu **:core:test** thất bại nhưng **:api:test** không phụ thuộc task lỗi đó, Gradle có thể tiếp tục kiểm thử **:api** và sau cùng vẫn báo **BUILD FAILED**. Với bản phát hành, kết quả này phải chặn publish nếu test là quality gate bắt buộc.

Ngược lại, nếu dùng **ignoreFailures = true** ở task Test, pipeline có thể hoàn tất như thành công dù báo cáo ghi nhận test thất bại. Chỉ dùng lựa chọn này trong trường hợp đã được thiết kế rõ để thu thập hoặc quan sát test không chặn build, và hiển thị rủi ro của kết quả đó.

## 10. Bài thực hành Java 17 độc lập: skip, enable, error, cleanup

Ví dụ sau có thể dựng lại bằng các file được liệt kê. Nó dùng **Gradle Groovy DSL** với plugin **application** và chương trình Java thuần, thêm các task kiểm tra điều kiện và lỗi. Phần lỗi có chủ đích tách riêng để không làm hỏng lệnh build mặc định.

### 10.1. Cấu trúc thư mục

~~~text
task-conditions-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/TaskConditionsApp.java
~~~

Các file Wrapper có thể được sinh một lần bằng **gradle wrapper** nếu máy đã cài Gradle phù hợp, sau đó commit Wrapper và sử dụng **./gradlew** hoặc **.\gradlew.bat**. Cần JDK đáp ứng bản Gradle đã chọn và Java 17 toolchain có sẵn hoặc được cấu hình để cung cấp.

**settings.gradle**:

~~~groovy
rootProject.name = 'task-conditions-lab'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example.learning'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.TaskConditionsApp'
}

def reportFlag = providers.gradleProperty('demo.report').map { raw ->
    if (raw != 'true' && raw != 'false') {
        throw new GradleException('demo.report chỉ nhận true hoặc false')
    }
    raw == 'true'
}.orElse(false)

def prepare = tasks.register('prepareReport') {
    group = 'demo'
    doLast {
        println 'PREPARE'
    }
}

tasks.register('generateReport') {
    group = 'demo'
    dependsOn(prepare)
    onlyIf('demo.report phải bằng true') {
        reportFlag.get()
    }
    doLast {
        println 'GENERATE'
    }
}

tasks.register('disabledDemo') {
    group = 'demo'
    enabled = false
    doLast {
        println 'SHOULD NOT PRINT'
    }
}

tasks.register('partialAction') {
    group = 'demo'
    doFirst {
        println 'FIRST ACTION'
        throw new StopActionException()
    }
    doLast {
        println 'SECOND ACTION'
    }
}

tasks.register('stoppedTask') {
    group = 'demo'
    doFirst {
        println 'BEFORE STOP'
        throw new StopExecutionException()
    }
    doLast {
        println 'AFTER STOP'
    }
}

tasks.register('afterStoppedTask') {
    group = 'demo'
    dependsOn('stoppedTask')
    doLast {
        println 'NEXT'
    }
}

def cleanup = tasks.register('cleanupDemo') {
    group = 'demo'
    doLast {
        println 'CLEANUP'
    }
}

tasks.register('failingDemo') {
    group = 'demo'
    finalizedBy(cleanup)
    doLast {
        println 'FAIL START'
        throw new GradleException('DEMO_FAIL')
    }
}

tasks.register('unrelatedDemo') {
    group = 'demo'
    doLast {
        println 'UNRELATED'
    }
}
~~~

**src/main/java/demo/TaskConditionsApp.java**:

~~~java
package demo;

public final class TaskConditionsApp {
    private TaskConditionsApp() {
    }

    public static void main(String[] args) {
        System.out.println("Java 17: task demo OK");
    }
}
~~~

Giải thích thiết kế:

1. **application** tạo task Java **run**, thiết lập main class.
2. **reportFlag** là Provider có parse boolean nghiêm ngặt: chỉ **true** hoặc **false**, mặc định false.
3. **generateReport** có **dependsOn(prepare)** nên **prepareReport** được chạy ngay cả khi **generateReport** SKIPPED.
4. **disabledDemo** luôn bị vô hiệu hóa.
5. **partialAction** cho phép action thứ hai chạy sau **StopActionException**.
6. **stoppedTask** dừng phần còn lại của chính task qua **StopExecutionException** nhưng **afterStoppedTask** vẫn có thể chạy.
7. **failingDemo** luôn ném lỗi thông thường; **cleanupDemo** được nối bằng **finalizedBy**.
8. **unrelatedDemo** không phụ thuộc task lỗi nên có thể chạy khi dùng **--continue**.

### 10.2. Chạy các trường hợp thành công

**Linux/macOS:**

~~~bash
./gradlew -q run
./gradlew generateReport
./gradlew -q generateReport -Pdemo.report=true
./gradlew disabledDemo
./gradlew -q partialAction
./gradlew -q afterStoppedTask
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat generateReport
.\gradlew.bat -q generateReport -Pdemo.report=true
.\gradlew.bat disabledDemo
.\gradlew.bat -q partialAction
.\gradlew.bat -q afterStoppedTask
~~~

Kết quả mong đợi **chỉ đối với các dòng do code/task chủ động in**, không bao gồm log Gradle:

| Lệnh | Những dòng stdout do ví dụ in | Quan sát |
| --- | --- | --- |
| **run** | **Java 17: task demo OK** | Main class Java chạy được |
| **generateReport** không có cờ | **PREPARE** | **generateReport SKIPPED**, dependency vẫn đã chạy |
| **generateReport -Pdemo.report=true** | **PREPARE**, rồi **GENERATE** | Predicate true, action chạy |
| **disabledDemo** | Không có dòng từ action | Task báo **SKIPPED** trong log thường |
| **partialAction** | **FIRST ACTION**, rồi **SECOND ACTION** | StopActionException chỉ dừng action hiện tại |
| **afterStoppedTask** | **BEFORE STOP**, rồi **NEXT** | StopExecutionException bỏ các action còn lại của stoppedTask |

Khi không có cờ report, chạy:

~~~bash
./gradlew generateReport --info
~~~

Đọc phần log liên quan **onlyIf**. Nếu truyền giá trị không hợp lệ:

~~~bash
./gradlew generateReport -Pdemo.report=maybe
~~~

Provider ném GradleException với thông điệp **demo.report chỉ nhận true hoặc false** khi điều kiện được đọc. Đây là lỗi cấu hình tham số, không nên bị chuyển thành skip im lặng.

### 10.3. Thử task thất bại và cleanup

**Linux/macOS:**

~~~bash
./gradlew failingDemo
./gradlew failingDemo unrelatedDemo --continue
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat failingDemo
.\gradlew.bat failingDemo unrelatedDemo --continue
~~~

Cả hai lệnh **được thiết kế để thất bại** và báo **BUILD FAILED**. Với lần đầu, dòng do ví dụ in bao gồm **FAIL START** và **CLEANUP**. Với lần sau, **--continue** cho phép task độc lập **unrelatedDemo** chạy, vì vậy cũng có dòng **UNRELATED**. Thứ tự tuyệt đối của log có thể khác theo task scheduling, nhưng finalizer phải chạy sau task chính.

Trong shell script CI, mã thoát khác 0 của những lệnh này là dự kiến khi đang học; **không dùng lệnh failingDemo** trong lifecycle build production. Task lỗi được đặt riêng có chủ đích.

### 10.4. Xác minh riêng Java bằng javac/java

Mã Java không phụ thuộc Gradle API nên có thể kiểm tra độc lập:

**Linux/macOS:**

~~~bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/TaskConditionsApp.java
java -cp out demo.TaskConditionsApp
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out src\main\java\demo\TaskConditionsApp.java
java -cp out demo.TaskConditionsApp
~~~

Dòng stdout của chương trình Java:

~~~text
Java 17: task demo OK
~~~

Biên dịch bằng **javac** xác minh Java source; chạy các lệnh **gradlew** mới chứng minh cách xử lý task graph, predicate, trạng thái SKIPPED và lỗi trong Gradle.

## 11. Những trường hợp dễ làm CI báo xanh sai

### 11.1. Tắt task test nhưng vẫn chạy build

~~~groovy
tasks.named('test', Test) {
    enabled = false
}
~~~

Khi test bị disabled, phần kiểm thử trong task ấy **không chạy**. Nếu các bước khác thành công, build có thể hiển thị **BUILD SUCCESSFUL**, nhưng đó không chứng minh các test đã qua. Cần thể hiện điều kiện một cách công khai trong pipeline, không gắn success với chất lượng khi test không thực hiện.

### 11.2. Skip vì file đã tồn tại

Một điều kiện kiểu:

~~~groovy
onlyIf {
    file('build/output.txt').exists()
}
~~~

có thể tạo logic ngược: file output chưa tồn tại nên task cần tạo nó lại bị skip. Ngoài ra, việc truy cập **Project.file** trong task execution-time predicate có thể không tương thích configuration cache. Nếu task cần tạo output, hãy khai báo **inputs/outputs** cho Gradle dùng up-to-date checks. Nếu muốn tùy chọn kiểm tra file input, lấy đường dẫn qua provider phù hợp, xác định policy thiếu input rõ ràng và cân nhắc tác động configuration cache.

### 11.3. Skip vì chưa có dependency tải về

Một task bị skip không giúp sửa lỗi **Could not resolve dependencies** trong giai đoạn configuration hoặc task khác. Nếu lỗi xảy ra **trước lúc Gradle đánh giá onlyIf**, predicate không có cơ hội bỏ qua lỗi. Hãy sửa repository, proxy, version plugin/dependency hoặc tách configuration chỉ cần khi task thực sự dùng.

### 11.4. Dùng --continue để che giấu lỗi

**--continue** giúp thu thập lỗi ở nhiều nhánh; nó không xóa lỗi. Nếu pipeline bỏ qua exit code cuối cùng, đó là lỗi của shell/pipeline hoặc cách bắt exception, không phải bảo đảm của Gradle. CI cần giữ mã thoát và báo cáo những task thất bại.

### 11.5. Dùng doLast catch Exception rồi im lặng

~~~groovy
tasks.register('badCheck') {
    doLast {
        try {
            throw new IllegalStateException('Bị lỗi')
        } catch (Exception ignored) {
            println 'CHECK PASSED'
        }
    }
}
~~~

Đây là **đoạn minh họa anti-pattern**, không được đưa vào quality gate: đã có lỗi nhưng task in thông báo thành công. Nếu lỗi có thể phục hồi, phải thể hiện phục hồi thật sự, giữ bằng chứng và chỉ chuyển thành success khi hậu điều kiện nghiệp vụ vẫn đúng.

## 12. Quy trình chẩn đoán task không chạy hoặc bị lỗi

### 12.1. Trường hợp task hiện SKIPPED

1. Chạy lại cùng task với **--info** để tìm lý do skip được Gradle log.
2. Kiểm tra **enabled** ở nơi khai báo task, convention plugin và plugin bên ngoài.
3. Tìm mọi điều kiện **onlyIf**, bao gồm các predicate do plugin khác thêm.
4. Kiểm tra giá trị từ **-P**, **gradle.properties** và environment có được parse đúng kiểu không; chuỗi **'false'** không phải boolean false.
5. Xem task graph để phân biệt task có mặt nhưng SKIPPED với task không được chọn.
6. Đối chiếu **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**; không kết luận mọi task không có output mới đều SKIPPED.
7. Nếu dependencies vẫn chạy, xem có quan hệ **dependsOn** hay **finalizedBy** nào chủ động thêm chúng hay không.

Lệnh hữu ích:

~~~bash
./gradlew generateReport --info
./gradlew generateReport -Pdemo.report=true --info
./gradlew help --stacktrace
./gradlew tasks --all
~~~

Chọn task phù hợp với dự án; **generateReport** thuộc ví dụ lab, không tự có trong mọi build.

### 12.2. Trường hợp task FAILED

1. Xác định câu báo **Execution failed for task ':... '** và lỗi gốc theo stacktrace.
2. Nếu lỗi từ **GradleException**, **Java compilation**, **Test** hoặc process exit, khắc phục nguyên nhân theo layer tương ứng.
3. Dùng **--stacktrace** khi cần nguồn lỗi chi tiết, **--info** để xem hành vi task và lý do skip; thận trọng với **--debug** vì log có thể chứa dữ liệu môi trường nhạy cảm.
4. Kiểm tra task thất bại có **finalizedBy** để bảo đảm tài nguyên được dọn, nhưng không phá log hoặc report.
5. Nếu cần biết thêm lỗi độc lập trong một lần CI, chạy **--continue**, vẫn giữ build status FAILED.
6. Đánh giá chất lượng: có nên cho bước publish/deploy tiếp tục không? Với quality gate bắt buộc, câu trả lời thường là **không**.

### 12.3. Bảng chẩn đoán ngắn

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| **Task :x SKIPPED** | **onlyIf** false, **enabled=false** hoặc cơ chế skip | **--info**, kiểm tra predicate/flag |
| **Task :x UP-TO-DATE** | Input/output không thay đổi | Kiểm tra khai báo input/output, không vội sửa onlyIf |
| **Task :x FROM-CACHE** | Output được khôi phục từ cache | Xác minh build cache và task inputs |
| **Task :x NO-SOURCE** | Không có source/input phù hợp | Xem source sets, đường dẫn, include/exclude |
| Không thấy task trong log | Không nằm trong graph hoặc bị **-x** loại | Kiểm tra task path, graph, dependencies |
| Skip task đích nhưng dependency vẫn chạy | **dependsOn** tạo graph trước khi skip | Thiết kế lại graph/gate nếu muốn bỏ cả nhánh |
| Consumer đọc file cũ khi producer skip | Output không được tạo mới, state không hợp lệ | Chỉnh input/output và logic tùy chọn |
| Chạy **-Pflag=false** mà task vẫn chạy | Dùng truthiness của String | Parse boolean thật |
| **--continue** nhưng task phụ thuộc không chạy | Dependency đã FAILED | Đây là đúng; chỉ task độc lập đủ điều kiện được chạy |
| Build xanh nhưng test chưa chạy | **enabled=false**, **onlyIf** false, **-x test** hoặc ignoreFailures | Điều chỉnh quality gate, ghi rõ lý do skip |
| Exception trong **doLast** khiến BUILD FAILED | Lỗi thực sự của task action | Đọc stacktrace, sửa nguyên nhân, không catch im lặng |
| Cleanup không chạy khi task lỗi | Chưa nối bằng finalizer, task không được lên lịch | Dùng **finalizedBy** cho tài nguyên cần dọn |
| Predicate ném exception | Input không hợp lệ hoặc logic predicate lỗi | Validate và báo lỗi rõ; đừng coi exception là skip |

## 13. Bài tập củng cố

**Bài tập 1 — Quan sát skip:** Với lab ở mục 10, chạy **generateReport** khi không có cờ và khi có **-Pdemo.report=true**. Ghi rõ task nào in **PREPARE**, task nào in **GENERATE**, và vì sao dependency vẫn chạy khi task đích SKIPPED.

**Bài tập 2 — Mở rộng onlyIf:** Thêm một predicate thứ hai, ví dụ **onlyIf { false }**, vào **generateReport** rồi chạy với cờ **true**. Đưa ra quy tắc kết hợp của các predicate.

**Bài tập 3 — enabled:** Đổi **disabledDemo** thành **enabled = true**, chạy lại và so với trạng thái cũ. Sau đó đưa về disabled và giải thích khi nào nên dùng cách này thay cho onlyIf.

**Bài tập 4 — Exception đặc biệt:** Chạy **partialAction** và **afterStoppedTask**. Vì sao **SECOND ACTION** được in nhưng **AFTER STOP** không được in?

**Bài tập 5 — Lỗi độc lập:** Chạy **failingDemo unrelatedDemo --continue**. Ghi các dòng **FAIL START**, **CLEANUP**, **UNRELATED** và trạng thái build cuối cùng. Thử thêm task phụ thuộc **failingDemo** để xem vì sao nó không chạy.

**Bài tập 6 — Chất lượng CI:** Một pipeline dùng **build -x test** rồi publish bản release. Giải thích những rủi ro và đề xuất cách quản lý quality gate/test report sao cho có thể phân biệt **test passed**, **test skipped** và **test failed**.

**Câu hỏi tự kiểm tra:**

1. **onlyIf** được đánh giá khi nào?
2. **enabled = false** khác **onlyIf false** về mục đích sử dụng thế nào?
3. **SKIPPED** khác **UP-TO-DATE** và **NO-SOURCE** ở điểm nào?
4. Có phải task skip thì mọi task dependency được bỏ qua?
5. Vì sao **-x test** không tương đương **onlyIf false**?
6. **StopActionException** khác **StopExecutionException**?
7. **GradleException** thường tác động ra sao lên task và build?
8. **--continue** có làm build thành công khi một task thất bại không?
9. **finalizedBy** dùng khi nào và có xóa lỗi gốc không?
10. **ignoreFailures = true** trên Test có rủi ro gì với phát hành?

**Đáp án gợi ý:** (1) khi task đến lượt xử lý trong execution; (2) điều kiện runtime so với vô hiệu hóa task; (3) nguyên nhân không thực thi khác nhau; (4) không; (5) -x loại task khỏi graph; (6) dừng action hiện tại so với dừng các action còn lại của task; (7) task FAILED, build thường FAILED; (8) không, chỉ tiếp tục task độc lập và vẫn báo lỗi; (9) dọn dẹp kể cả task lỗi, không biến lỗi thành success; (10) test có thể fail nhưng pipeline vẫn báo xanh nếu không có quality gate bổ sung.

## 14. Checklist áp dụng vào dự án thật

Trước khi thêm điều kiện skip hoặc xử lý lỗi cho một task, hãy xác nhận:

- **Điều kiện nghiệp vụ** được diễn đạt rõ ràng: task nào được chạy, task nào được bỏ qua, lý do cụ thể.
- **Đối tượng phù hợp:** chọn **onlyIf** nếu task hợp lệ nhưng phụ thuộc một điều kiện; chọn **enabled** khi muốn vô hiệu hóa task rõ ràng; tránh dùng cả hai tùy tiện.
- **Thời điểm:** predicate không có side effect, không đòi dữ liệu chưa tồn tại hoặc tạo phụ thuộc vào Project state không an toàn cho configuration cache.
- **Task graph:** kiểm tra dependencies, producer/consumer, finalizers và task order; skip một task không tự giải quyết toàn bộ graph.
- **Trạng thái:** phân biệt **SKIPPED**, **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE** và **FAILED** bằng log thực.
- **Xử lý lỗi:** không nuốt lỗi build/test/deploy; dùng **--continue** để thu thập lỗi độc lập và **finalizedBy** cho cleanup khi cần.
- **Kiểm thử:** chạy các nhánh true/false, giá trị đầu vào không hợp lệ, lỗi thực sự và cleanup; lưu report làm bằng chứng.
- **CI:** quality gate có trạng thái rõ ràng; task test bị skip phải được coi là một quyết định công khai, không tự động hiểu là PASS.

## 15. Tài liệu Gradle chính thức

- [Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Task API — onlyIf, enabled, finalizedBy, StopActionException, StopExecutionException](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html)
- [Understanding Tasks — Task Outcomes](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle Command-Line Interface — --continue, -x, --rerun-tasks](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Testing in Java & JVM Projects — ignoreFailures, failFast, task skipping](https://docs.gradle.org/current/userguide/java_testing.html)
- [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html)

**Kết luận:** **onlyIf** và **enabled** kiểm soát việc thực thi actions của một task, nhưng không phải cách thay thế thiết kế task graph. **SKIPPED** là quyết định không làm việc; **FAILED** báo công việc không hoàn thành đúng yêu cầu. **--continue** giữ thêm task độc lập được chạy, còn **finalizedBy** giúp bảo đảm công việc dọn dẹp sau lỗi. Khi sử dụng các cơ chế này với quan hệ input/output rõ ràng và quality gate nghiêm túc, Gradle build vừa linh hoạt theo môi trường vừa cung cấp tín hiệu thành công/thất bại đáng tin cậy.

# Đồ thị task và thời điểm xác định thứ tự thực thi trong Gradle

## 1. Mục tiêu bài học

Một lần chạy Gradle thường gọi một task, nhưng nhiều task khác được thực hiện trước nó. Ví dụ khi yêu cầu đóng gói ứng dụng, Gradle có thể phải tạo mã nguồn, biên dịch, xử lý tài nguyên, chạy kiểm tra và tạo artifact. **Gradle Task Graph (đồ thị task)** mô tả các task cần tham gia trong lần build đó và quan hệ thứ tự giữa chúng.

Sau bài này, bạn cần giải thích và thực hành được:

1. Task graph là gì; tại sao **đăng ký task** khác **đưa task vào đồ thị thực thi**.
2. Gradle xác định tập task và các ràng buộc thứ tự **ở thời điểm nào** trong ba giai đoạn của build lifecycle.
3. Phân biệt **dependsOn**, **mustRunAfter**, **shouldRunAfter** và **finalizedBy**.
4. Dự đoán thứ tự nào **được bảo đảm**, thứ tự nào chưa được xác định giữa các task độc lập.
5. Dùng Gradle Wrapper và **--dry-run** để xem kế hoạch chạy trước khi thực hiện hành động thật.
6. Hiểu tác động của lazy configuration, configuration cache, up-to-date check, task bị skip và chạy song song.
7. Tránh lỗi phổ biến khi cố thay đổi đồ thị task quá muộn.

Bài nằm trong nhóm **Vòng đời build** của Build Tool Gradle, tập trung vào quan hệ thời gian giữa **khai báo task → tạo task graph → lập lịch và thực thi**.

## 2. Khái niệm: Task Graph là một DAG

**Task** là một đơn vị công việc do Gradle hoặc plugin cung cấp. Một task có tên, đường dẫn, cấu hình, đầu vào/đầu ra, các ràng buộc và có thể có những action được chạy khi được chọn.

**Task graph** là đồ thị các task Gradle lập ra cho **một lần thực thi cụ thể**:

- **Đỉnh (node):** các task cần xét trong kế hoạch.
- **Cạnh:** phụ thuộc công việc, ràng buộc thứ tự hoặc mối liên hệ khiến task khác được thêm vào kế hoạch.
- **DAG — Directed Acyclic Graph:** những phụ thuộc bắt buộc phải không tạo chu trình; nếu A phụ thuộc B và B phụ thuộc A, Gradle không thể giải quyết thứ tự hợp lệ.
- **Tính theo yêu cầu:** chạy task X có thể tạo đồ thị khác với chạy task Y dù cả hai ở cùng một repository.

Ví dụ về một chuỗi ràng buộc:

~~~text
prepare -> compileDemo -> packageDemo -> deliver
~~~

Mũi tên trong sơ đồ này có nghĩa **phải hoàn tất bước bên trái trước bước bên phải**. Trong build.gradle, quan hệ thực tế được khai báo từ task tiêu thụ về task tiền đề: **compileDemo.dependsOn(prepare)**, **packageDemo.dependsOn(compileDemo)**, v.v.

Với nhánh độc lập:

~~~text
             +--> compileApi ----+
prepareData -+                    +--> bundle
             +--> renderDocs ----+
~~~

- **prepareData** phải xong trước cả **compileApi** và **renderDocs**.
- **bundle** phải chờ cả hai.
- **Không có cạnh bắt buộc giữa compileApi và renderDocs**, nên không được dựa vào việc một task luôn chạy trước task kia. Tùy Gradle version, tùy chọn song song, tài nguyên và scheduler, chúng có thể được sắp thứ tự khác nhau hoặc chạy đồng thời khi được hỗ trợ.

Đồ thị task **khác** với đồ thị dependency của thư viện (ví dụ nhóm Maven coordinates bên trong một Gradle configuration). Một bên quản lý **các bước làm việc**, bên kia quản lý **những component/artifact cần resolve**. Task có thể dùng artifact sau khi resolve dependencies, nhưng hai đồ thị không phải cùng một cấu trúc.

## 3. Thời điểm xác định thứ tự: ba giai đoạn build lifecycle

Một lần build Gradle có ba giai đoạn logic:

| Giai đoạn | Gradle làm gì? | Liên hệ với task graph |
| --- | --- | --- |
| **1. Initialization** | Đọc settings.gradle hoặc settings.gradle.kts, xác định root project và các project liên quan | Biết cấu trúc build và phạm vi project |
| **2. Configuration** | Đọc/áp dụng build logic, plugin; đăng ký/cấu hình task cần thiết; phân tích dependencies và các ràng buộc | **Tính ra task graph của yêu cầu hiện tại trước khi thực thi task** |
| **3. Execution** | Xem task nào đã sẵn sàng, kiểm tra trạng thái, thực thi hoặc skip các task trong kế hoạch | **Dùng task graph đã tính** để lập lịch và chạy action |

Có thể hình dung:

~~~text
Lệnh: ./gradlew deliver
          |
          v
Initialization: xác định project
          |
          v
Configuration: khai báo task + quan hệ;
               Gradle tính tập task và ràng buộc thứ tự
          |
          v
Execution: task tiền đề sẵn sàng -> task kế tiếp -> deliver
~~~

**Điểm quyết định:** Gradle hoàn thành việc xác định đồ thị cần chạy **trước khi bắt đầu thực thi các task**. Thứ tự dựa trên dependencies và ràng buộc đã khai báo; Gradle không thực hiện tuần tự từng dòng build.gradle như một script shell.

Cần phân biệt ba thời điểm:

- **Đăng ký task:** tasks.register('name') cho Gradle biết task có thể tồn tại; không có nghĩa task đã thực hiện.
- **Cấu hình/realize task:** Gradle tạo và cấu hình đối tượng Task khi cần; có thể diễn ra lười (lazy) trong configuration.
- **Thực thi action:** doFirst/doLast hoặc @TaskAction chạy ở execution phase, nếu task không bị skip.

Với **Configuration Cache** đã bật và có cache hit hợp lệ, Gradle có thể **khôi phục kế hoạch task đã lưu**, tránh chạy lại phần cấu hình tương ứng. Khi đó không được giả định mỗi invocation đều đánh giá lại các dòng build.gradle. Ba vai trò logic vẫn giữ nguyên: có một kế hoạch hợp lệ trước khi task chạy.

## 4. Ví dụ chạy được: một chuỗi dependency

Chuẩn bị một dự án Gradle tối giản với Gradle Wrapper. Tại root của dự án:

**settings.gradle**

~~~groovy
rootProject.name = 'task-graph-demo'
~~~

**build.gradle** (Groovy DSL):

~~~groovy
def prepare = tasks.register('prepare') {
    doLast {
        println 'prepare'
    }
}

def compileDemo = tasks.register('compileDemo') {
    dependsOn(prepare)
    doLast {
        println 'compileDemo'
    }
}

def packageDemo = tasks.register('packageDemo') {
    dependsOn(compileDemo)
    doLast {
        println 'packageDemo'
    }
}

tasks.register('deliver') {
    dependsOn(packageDemo)
    doLast {
        println 'deliver'
    }
}
~~~

Trong macOS/Linux:

~~~bash
./gradlew -q deliver
~~~

Trong Windows PowerShell:

~~~powershell
.\gradlew.bat -q deliver
~~~

**Stdout chính xác do các task này in ra khi chạy thành công và chưa có can thiệp khác:**

~~~text
prepare
compileDemo
packageDemo
deliver
~~~

**Giải thích:**

- Lệnh CLI chỉ yêu cầu **deliver**, nhưng Gradle đi ngược các cạnh dependsOn để đưa ba task tiền đề vào graph.
- **dependsOn(prepare)** yêu cầu prepare hoàn thành trước compileDemo.
- **-q** (quiet) ẩn phần lớn log của Gradle để phần output minh họa dễ quan sát.
- **tasks.register** tạo task theo hướng lazy; việc gọi tên provider không chạy task ngay.
- Nếu chạy **./gradlew -q prepare**, chỉ task prepare được yêu cầu bởi ví dụ này, nên không tự động kéo theo compileDemo, packageDemo hay deliver.

Với bài thực hành trên, những task được khai báo chỉ in chữ, không cần Java plugin hay file mã nguồn Java. Nếu thư mục chưa có Wrapper, cần tạo hoặc khôi phục Wrapper theo quy trình chuẩn của dự án; không mặc định luôn có sẵn ./gradlew.

### 4.1. Tự dự đoán đồ thị theo task được chọn

| Lệnh | Các task thuộc chuỗi có thể được chọn |
| --- | --- |
| ./gradlew prepare | prepare |
| ./gradlew compileDemo | prepare → compileDemo |
| ./gradlew packageDemo | prepare → compileDemo → packageDemo |
| ./gradlew deliver | prepare → compileDemo → packageDemo → deliver |

Trong build thật, plugin có thể bổ sung task và dependency khác. Bảng trên đúng cho **ví dụ tối giản** đã khai báo, không nhằm mô tả mọi build Gradle.

## 5. Xem kế hoạch bằng --dry-run

Không cần chạy thật để kiểm tra Gradle dự định đưa task nào vào graph. Dùng:

~~~bash
./gradlew deliver --dry-run --console=plain
~~~

Hoặc PowerShell:

~~~powershell
.\gradlew.bat deliver --dry-run --console=plain
~~~

Một phần output điển hình:

~~~text
:prepare SKIPPED
:compileDemo SKIPPED
:packageDemo SKIPPED
:deliver SKIPPED
~~~

Các phiên bản Gradle và chế độ console có thể định dạng log khác nhau. Dữ liệu quan trọng là **đường dẫn task xuất hiện theo ràng buộc**. Từ **SKIPPED** trong dry-run là kết quả mô phỏng; không có nghĩa task tương ứng bị skip vì lỗi hoặc điều kiện trong một lần build thực.

**Lưu ý:** --dry-run bỏ qua **task action thực tế**, nhưng Gradle vẫn phải xử lý build configuration đủ để lập kế hoạch. Build script có tác dụng phụ ngay trong configuration (viết file, gọi mạng, v.v.) vẫn có thể gây tác động ngay cả khi dry-run. Vì thế nên đặt công việc có tác dụng phụ trong task action phù hợp, không thực hiện tùy tiện ở phần cấu hình.

Nếu muốn xem thứ tự task được lập kế hoạch, **--dry-run** thường là công cụ đơn giản và an toàn hơn việc gắn listener sâu vào Gradle internals.

## 6. Bốn loại quan hệ cần nắm chắc

| Cấu hình | Có thêm task liên quan vào graph khi task chính được chọn? | Ràng buộc thứ tự | Khi nào dùng? |
| --- | --- | --- | --- |
| **dependsOn(A)** trên B | **Có**, A là tiền đề của B | A trước B | B cần kết quả/công việc của A |
| **mustRunAfter(A)** trên B | **Không**, chỉ áp dụng nếu cả A và B đều trong graph | A trước B, ràng buộc mạnh | Hai task cần trật tự nhưng không muốn kéo task khác vào |
| **shouldRunAfter(A)** trên B | **Không** | A trước B nếu khả thi; có thể bỏ qua trong một số tình huống | Ưu tiên mềm để tối ưu thứ tự |
| **finalizedBy(C)** trên B | **Có**, C được lên lịch làm finalizer khi B được lên lịch | C sau B | Dọn tài nguyên hoặc công việc cuối sau B |

Bốn quan hệ trên **không đồng nghĩa**. Hai lỗi tư duy thường gặp là tưởng mustRunAfter sẽ tự gọi task A hoặc tưởng finalizedBy chỉ là một lời nhắc thứ tự và không thêm task.

### 6.1. dependsOn: quan hệ công việc phải hoàn thành trước

Trong ví dụ ở mục 4:

~~~groovy
tasks.register('deliver') {
    dependsOn(packageDemo)
    doLast {
        println 'deliver'
    }
}
~~~

Nếu yêu cầu deliver, Gradle phải xét packageDemo và các tiền đề của packageDemo. **Phụ thuộc là quan hệ có ý nghĩa công việc**. Nếu producer tạo artifact mà consumer cần, cần khai báo input/output hoặc dependency đúng thay vì chỉ hy vọng CLI chạy producer trước.

Một task có thể phụ thuộc nhiều task:

~~~groovy
tasks.register('bundle') {
    dependsOn('compileApi', 'renderDocs')
}
~~~

Khai báo trên yêu cầu cả hai tiền đề trước bundle nhưng **không tự quy định compileApi chạy trước renderDocs hay ngược lại**.

### 6.2. mustRunAfter: thứ tự mạnh, không kéo task vào

Có thể thử ví dụ **độc lập** sau trong build.gradle của một dự án thử nghiệm:

~~~groovy
def fastCheck = tasks.register('fastCheck') {
    doLast {
        println 'fast'
    }
}

tasks.register('slowCheck') {
    mustRunAfter(fastCheck)
    doLast {
        println 'slow'
    }
}
~~~

Chạy **chỉ slowCheck**:

~~~bash
./gradlew -q slowCheck
~~~

Stdout:

~~~text
slow
~~~

**fastCheck không được gọi** vì mustRunAfter không tạo dependency.

Chạy cả hai:

~~~bash
./gradlew -q slowCheck fastCheck
~~~

Stdout:

~~~text
fast
slow
~~~

Dù CLI liệt kê slowCheck trước, ràng buộc mustRunAfter bắt buộc slowCheck nằm sau fastCheck khi cả hai được chọn. Task trước đó **không nhất thiết phải thành công** thì task sau mới được phép chạy khi sử dụng những cơ chế tiếp tục thực thi như --continue; mustRunAfter chỉ là ràng buộc thứ tự, không phải phụ thuộc kết quả.

**Không dùng mustRunAfter để thay dependsOn** khi task sau thực sự cần sản phẩm từ task trước.

### 6.3. shouldRunAfter: thứ tự ưu tiên mềm

Một ví dụ khác:

~~~groovy
def quickValidation = tasks.register('quickValidation') {
    doLast {
        println 'quick'
    }
}

tasks.register('longValidation') {
    shouldRunAfter(quickValidation)
    doLast {
        println 'long'
    }
}
~~~

Nếu cả hai được yêu cầu và không có ràng buộc xung đột, Gradle thường thực hiện quickValidation trước longValidation. Nhưng **shouldRunAfter không bảo đảm tuyệt đối**:

1. Gradle có thể bỏ qua ưu tiên mềm nếu nó gây chu trình thứ tự.
2. Trong một số tình huống chạy song song, Gradle có thể thực hiện task đã sẵn sàng dù task mà nó nên chờ chưa hoàn thành.

Dùng shouldRunAfter khi thứ tự chỉ mang tính **ưu tiên**, chẳng hạn muốn kiểm tra nhanh trước để sớm có feedback. Nếu ràng buộc thứ tự là yêu cầu chính xác, dùng mustRunAfter; nếu task sau phải cần kết quả task trước, dùng dependsOn.

### 6.4. finalizedBy: thêm task kết thúc

Ví dụ **độc lập**:

~~~groovy
def useResource = tasks.register('useResource') {
    doLast {
        println 'using resource'
    }
}

tasks.register('cleanupResource') {
    doLast {
        println 'cleanup resource'
    }
}

useResource.configure {
    finalizedBy('cleanupResource')
}
~~~

Lệnh:

~~~bash
./gradlew -q useResource
~~~

Stdout:

~~~text
using resource
cleanup resource
~~~

Khi useResource có trong kế hoạch, cleanupResource cũng được đưa vào task graph như một finalizer. Gradle cố gắng chạy finalizer **ngay cả khi task được finalization thất bại hoặc đã UP-TO-DATE**. Đây là cơ chế phù hợp để thu hồi tài nguyên do build quản lý, nhưng không nên cam kết cleanup trong trường hợp tiến trình bị hệ điều hành kill, mất điện hoặc môi trường chạy ngừng đột ngột.

## 7. Bài tập nâng cao: đồ thị phân nhánh và thứ tự không xác định

Xét một build.gradle **độc lập** khác:

~~~groovy
def fetchSchema = tasks.register('fetchSchema') {
    doLast {
        println 'fetch schema'
    }
}

def compileApi = tasks.register('compileApi') {
    dependsOn(fetchSchema)
    doLast {
        println 'compile API'
    }
}

def renderDocs = tasks.register('renderDocs') {
    dependsOn(fetchSchema)
    doLast {
        println 'render docs'
    }
}

tasks.register('bundle') {
    dependsOn(compileApi, renderDocs)
    doLast {
        println 'bundle'
    }
}
~~~

Lệnh:

~~~bash
./gradlew -q bundle
~~~

**Bảo đảm từ graph:**

- fetchSchema phải xảy ra trước compileApi và renderDocs.
- bundle chỉ chạy sau compileApi và renderDocs.
- Không có bảo đảm task nào trong **compileApi/renderDocs** sẽ chạy trước task còn lại.

Một thứ tự hợp lệ là:

~~~text
fetch schema
compile API
render docs
bundle
~~~

Một thứ tự hợp lệ khác là:

~~~text
fetch schema
render docs
compile API
bundle
~~~

Không nên coi một trong hai thứ tự trên là **stdout cố định của Gradle** cho mọi phiên bản và mọi môi trường. Thứ tự giữa những task không bị ràng buộc là quyết định của scheduler. Nếu thực tế cần renderDocs sau compileApi, hãy nêu ra quan hệ phù hợp; nếu renderDocs tiêu thụ kết quả compileApi, khai báo dependency/input/output.

### 7.1. Có thể dùng mustRunAfter để xếp thứ tự nhánh

Nếu chỉ muốn compileApi đi trước renderDocs khi hai task đều được chọn:

~~~groovy
renderDocs.configure {
    mustRunAfter(compileApi)
}
~~~

Đoạn này chỉ là **phần bổ sung** vào build.gradle của ví dụ phân nhánh trên, sau khi đã khai báo hai TaskProvider compileApi và renderDocs. Nó không tạo file build hoàn chỉnh nếu đứng một mình.

Do bundle phụ thuộc cả hai, graph của bundle sẽ có cả compileApi và renderDocs và thứ tự mạnh sẽ có tác dụng. Nếu chỉ gọi renderDocs riêng lẻ, mustRunAfter không tự thêm compileApi, dù renderDocs vẫn phụ thuộc fetchSchema theo cấu hình đã có.

### 7.2. Vì sao không dùng sleep để điều khiển thứ tự?

Câu lệnh sleep trong action không biểu đạt phụ thuộc dữ liệu; nó chỉ làm chậm một task. Tương tự, việc liệt kê task theo thứ tự trên command line không thay thế dependency graph, nhất là khi build song song hoặc plugin bổ sung task khác. Các quan hệ **dependsOn/input-output/mustRunAfter** mới truyền tải yêu cầu thật cho Gradle scheduler.

## 8. Dependency ngầm định từ task input/output

Gradle hỗ trợ hai cách liên kết công việc:

**Phụ thuộc tường minh:** task B gọi **dependsOn(A)**.

**Phụ thuộc ngầm định thông qua dữ liệu:** đầu vào của B được nối với **đầu ra do task A khai báo** qua Provider/FileCollection mang thông tin producer. Gradle có thể suy ra cần đưa producer A vào graph trước consumer B. Đây là cách quan trọng trong build phức tạp, vì quan hệ đã gắn trực tiếp với dữ liệu thật mà consumer sử dụng.

Ví dụ ý tưởng:

~~~text
generateSources: output = build/generated/sources
compileGenerated: input = output provider của generateSources
~~~

Khi compileGenerated dùng trực tiếp provider chứa thông tin producer và Gradle nhận diện liên hệ đầu vào–đầu ra, graph có thể thêm generateSources trước compileGenerated.

**Cần phân biệt:** gán vào input một chuỗi path tĩnh (ví dụ 'build/generated/sources') không tự nói cho Gradle biết task nào đã tạo path ấy. Nếu làm mất quan hệ Provider/TaskProvider, Gradle có thể báo lỗi validation về dependency ngầm định hoặc thực thi sai thứ tự. Hãy nối output provider đúng cách hoặc khai báo dependsOn tường minh.

Một task **không cần phụ thuộc vào mọi task biên dịch trong repository**; nó chỉ cần các producer thật sự cung cấp input của nó. Mô hình hóa đúng quan hệ input/output vừa giảm số task không cần thiết vừa hỗ trợ incremental build và cache.

## 9. Đồ thị được hình thành khi nào và có thể thay đổi lúc nào?

### 9.1. Mô hình thời điểm

Trong configuration phase, plugin và build script:

1. Khai báo và đăng ký các TaskProvider.
2. Khai báo các quan hệ dependsOn, finalizedBy, mustRunAfter, shouldRunAfter và input/output.
3. Gradle xác định task nào được yêu cầu từ CLI và mở rộng các quan hệ cần thiết.
4. Gradle tạo/realize các task cần thiết và tính đồ thị trước execution.

**Điều quan trọng:** Không nhất thiết mọi task đã đăng ký đều được realize hoặc cấu hình. **tasks.register** và **tasks.named** là cách làm việc lazy; Gradle chỉ cấu hình task khi nó thực sự cần.

Ở execution phase, Gradle kiểm tra các task đã có trong kế hoạch; việc đặt cấu hình dependency mới trong doLast thường đã **quá muộn** để thay đổi graph của lần build hiện tại. Nếu thứ tự là yêu cầu của hệ thống, phải khai báo nó trong lúc cấu hình.

### 9.2. Thực hành phân biệt configuration và execution

Một build.gradle **độc lập**:

~~~groovy
println 'CONFIG: evaluate build.gradle'

tasks.register('phaseDemo') {
    println 'CONFIG: configure phaseDemo'

    doLast {
        println 'EXECUTE: phaseDemo'
    }
}
~~~

Chạy:

~~~bash
./gradlew -q phaseDemo --no-configuration-cache
~~~

Stdout từ ví dụ trên:

~~~text
CONFIG: evaluate build.gradle
CONFIG: configure phaseDemo
EXECUTE: phaseDemo
~~~

Giải thích:

- Dòng nằm ở phần thân build.gradle được thực hiện khi Gradle đánh giá file build.
- Dòng bên trong cấu hình task được thực hiện khi task **được realize/cấu hình**; ở ví dụ này phaseDemo được yêu cầu nên việc đó xảy ra.
- Dòng trong **doLast** chỉ chạy khi action của phaseDemo được thực thi.

Cờ **--no-configuration-cache** được dùng trong ví dụ này để buộc Gradle đi qua phần cấu hình thay vì có khả năng khôi phục đồ thị đã cache. Chỉ đăng ký task khác mà không chạy nó thì không được suy luận rằng closure cấu hình của task đó luôn được thực hiện. Ngược lại, với **tasks.create**, task được tạo ngay, làm tăng khả năng thực hiện công việc cấu hình không cần thiết.

### 9.3. Configuration Cache có làm thay đổi ý nghĩa thứ tự không?

Khi chạy một tập task giống nhau và đầu vào cấu hình không đổi, Gradle có thể khôi phục graph đã lưu từ Configuration Cache. Điều này giúp giảm chi phí configuration; **dependsOn và các quan hệ vẫn được tôn trọng** trong kế hoạch được khôi phục.

Không viết build logic dựa trên giả định một callback được đăng ký trong configuration phải chạy lại mỗi lần build. Các listener/hook dạng **gradle.taskGraph.whenReady**, **gradle.taskGraph.afterTask**, hoặc listener tương tự có những hạn chế tương thích với Configuration Cache và không nên là lựa chọn mặc định để điều khiển phụ thuộc công việc. Ưu tiên khai báo task dependency/input/output trực tiếp. Với nghiệp vụ quan sát kết quả build, tìm API dành cho build services hoặc flow actions phù hợp phiên bản Gradle.

## 10. Một task nằm trong graph không có nghĩa action chắc chắn chạy

Task graph cho biết Gradle **dự định xét task** và quan hệ thứ tự của nó. Khi đến lượt, Gradle còn có thể quyết định **không chạy action** của task vì nhiều lý do:

| Trạng thái hoặc điều kiện | Điều quan trọng |
| --- | --- |
| **UP-TO-DATE** | Đầu vào/đầu ra không đổi theo kiểm tra của Gradle; action có thể không chạy |
| **FROM-CACHE** | Kết quả có thể được khôi phục từ build cache; action không nhất thiết được thực thi |
| **NO-SOURCE** | Task yêu cầu nguồn đầu vào nhưng không có nguồn để làm |
| **SKIPPED / onlyIf false** | Điều kiện chạy task không đạt; action bị bỏ qua |
| **Disabled** | Task bị tắt qua cấu hình; không thực hiện action thông thường |
| **--dry-run** | Task được liệt kê như mô phỏng nhưng action không chạy |

Do đó:

- **Task có mặt trong graph** không đồng nghĩa **println trong doLast đã chạy**.
- Phụ thuộc công việc không buộc một task vốn UP-TO-DATE phải làm lại action.
- Đồ thị và trạng thái thực thi phải được quan sát riêng khi tìm nguyên nhân “task không chạy”.

Khi một task đã có trong graph mà không chạy action, hãy xem nhãn trạng thái trên console, task inputs/outputs, onlyIf, enabled, exclude hoặc cache; đừng vội kết luận dependency bị thiếu.

## 11. Graph, chạy song song và thất bại

### 11.1. Chỉ ràng buộc tạo ra thứ tự bắt buộc

Nếu **B dependsOn A**, B chỉ được xét sau A theo ràng buộc dependency. Nếu **C** độc lập với A và B, scheduler có thể đặt C ở nhiều vị trí hợp lệ. Với các khả năng chạy song song được hỗ trợ trong phiên bản và cấu hình Gradle hiện tại, A và C có thể được thực hiện đồng thời; B vẫn phải chờ A.

Lệnh **--parallel** cho phép Gradle tận dụng các nhánh công việc độc lập theo khả năng của phiên bản và build. Không nên viết task cùng thay đổi một file chung mà không khai báo quan hệ hoặc cơ chế điều phối phù hợp, vì chạy song song có thể gây race condition.

### 11.2. --continue không đổi dependency thành ordering mềm

Mặc định khi một task thất bại, Gradle dừng công việc build theo chính sách lỗi. Với **--continue**, Gradle cố gắng tiếp tục **những task độc lập** vẫn có thể chạy, đồng thời tổng hợp báo lỗi.

Tuy nhiên, task **phụ thuộc vào task đã thất bại** thường không đủ điều kiện chạy bình thường vì prerequisite của nó chưa thành công. Ngược lại, **mustRunAfter** chỉ là thứ tự; sau một task thất bại, task khác chỉ có quan hệ mustRunAfter có thể tiếp tục trong một số trường hợp --continue. Finalizer có hành vi dọn dẹp riêng.

Tránh dùng --continue để “chữa” dependency sai; cờ này phục vụ thu thập nhiều lỗi độc lập trong một lần chạy.

### 11.3. Chu trình là một lỗi cấu hình

Ví dụ sai về mặt dependency:

~~~groovy
tasks.register('taskA') {
    dependsOn('taskB')
}

tasks.register('taskB') {
    dependsOn('taskA')
}
~~~

Nếu Gradle cần chạy các task này, không tồn tại thứ tự thỏa cả **taskA sau taskB** và **taskB sau taskA**. Gradle báo lỗi circular dependency thay vì chạy một thứ tự tùy ý.

Cách sửa là xem **mối quan hệ dữ liệu** thực sự: tách phần chuẩn bị chung thành task tiền đề riêng, bỏ cạnh không cần thiết hoặc điều chỉnh trách nhiệm của các task. Không dùng shouldRunAfter để che đậy một chu trình dependency bắt buộc.

## 12. Task graph trong multi-project build

Trong project có các module, đường dẫn đầy đủ giúp xác định chính xác task:

~~~text
:lib:compileJava
:lib:jar
:app:compileJava
:app:jar
~~~

Lệnh (nếu task và các project tương ứng tồn tại):

~~~bash
./gradlew :app:jar --dry-run --console=plain
~~~

Gradle có thể đưa task của **:lib** vào graph nếu cấu hình dependency giữa các project yêu cầu đầu ra của lib cho app. Không suy luận mọi task trong lib đều được chạy chỉ vì app phụ thuộc lib; graph gồm các bước cần thiết theo các quan hệ thực tế của build và các plugin.

Một task ở project khác có thể được tham chiếu bằng task path đầy đủ, nhưng với dependency giữa sản phẩm của hai project, nên cấu hình dependency dự án và Provider/output liên quan đúng cơ chế Gradle, thay vì tạo một chuỗi task thủ công và phụ thuộc vào thứ tự tình cờ.

## 13. Cách kiểm tra task graph khi gặp sự cố

Thực hiện trên **Gradle Wrapper cùng phiên bản dự án**:

1. Xác định task cuối được gọi và path của nó (ví dụ :app:jar).
2. Chạy **--dry-run --console=plain** với đúng tham số để xem các task được lập kế hoạch và ràng buộc thực tế.
3. Kiểm tra quan hệ **dependsOn/finalizedBy** trong build logic và quan hệ input/output từ plugin.
4. Nếu một task xuất hiện nhưng action không chạy, xem trạng thái **UP-TO-DATE, FROM-CACHE, NO-SOURCE, SKIPPED** hoặc điều kiện onlyIf.
5. Nếu thứ tự giữa hai task không đúng kỳ vọng, hỏi: **hai task có thật sự phụ thuộc công việc hay chỉ cần ưu tiên chạy trước?**
6. Nếu terminal và CI khác nhau, so sánh Wrapper, plugin, CLI options, environment, Configuration Cache và cấu hình chạy song song.
7. Khi kiểm tra lần build có cache hit, lưu ý các dòng println ở configuration có thể không xuất hiện như ở lần cache miss.

Ví dụ lệnh điều tra:

~~~bash
./gradlew :app:jar --dry-run --console=plain
./gradlew :app:jar --info --console=plain
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat :app:jar --dry-run --console=plain
.\gradlew.bat :app:jar --info --console=plain
~~~

**--info** cho thông tin chi tiết hơn về task và môi trường, nhưng có thể tạo log dài. Không dựa vào thứ tự vài dòng log của các task độc lập để xác lập ràng buộc ổn định. Nếu muốn biết vì sao task bị skip hoặc lấy từ cache, xem phần giải thích trạng thái/task inputs trong log.

## 14. Các lỗi thiết kế phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ dùng mustRunAfter trong khi B thực sự cần output của A | Chạy B riêng không tự đưa A vào graph | Khai báo input/output liên kết bằng Provider hoặc dependsOn |
| Viết dependsOn trong doLast | Khi action bắt đầu, task graph cho lần chạy đã được tính | Khai báo dependency trong configuration |
| Dùng shouldRunAfter cho yêu cầu thứ tự bắt buộc | Quy tắc mềm có thể bị bỏ qua | Dùng mustRunAfter hoặc dependsOn tùy bản chất |
| Coi tên task trên CLI luôn là thứ tự duy nhất | Graph có dependencies và scheduler riêng | Dựa trên quan hệ đã khai báo, kiểm tra bằng dry-run |
| Coi task được đăng ký là sẽ chạy | tasks.register không đồng nghĩa task được chọn | Gọi task tương ứng hoặc tạo quan hệ dependency đúng |
| Coi task nằm trong graph là đã thực hiện action | Có thể UP-TO-DATE, FROM-CACHE hoặc skip | Xem trạng thái thực thi và đầu vào/đầu ra |
| Thực hiện I/O hoặc gọi API ngoài trong phần cấu hình build.gradle | Chạy ngay cả khi task action không được chọn; gây chậm và khó cache | Đưa công việc vào task action, mô hình hóa inputs/outputs |
| Dùng path file tĩnh và bỏ thông tin producer | Gradle không suy ra task tạo ra file | Nối output Provider hoặc khai báo explicit dependency |
| Lạm dụng gradle.taskGraph.whenReady để sửa task | Muộn, khó tái lập và có hạn chế Configuration Cache | Khai báo quan hệ tại thời điểm cấu hình |
| Phụ thuộc chéo thành vòng tròn | Không tồn tại thứ tự topo hợp lệ | Tách trách nhiệm và loại bỏ chu trình |
| Dùng sleep hoặc đọc file chung không đồng bộ | Không mô hình hóa ràng buộc; dễ race khi parallel | Dùng dependency và quản lý tài nguyên đúng cách |

## 15. Bài tập kiểm tra hiểu biết

Cho cấu hình:

~~~groovy
def a = tasks.register('a') {
    doLast { println 'A' }
}
def b = tasks.register('b') {
    dependsOn(a)
    doLast { println 'B' }
}
def c = tasks.register('c') {
    mustRunAfter(b)
    doLast { println 'C' }
}
tasks.register('allDemo') {
    dependsOn(b, c)
    doLast { println 'ALL' }
}
~~~

**Câu 1.** Chạy **./gradlew -q b** thì có các dòng nào?

Trả lời: **A, B**. b phụ thuộc a; c không được yêu cầu.

**Câu 2.** Chạy **./gradlew -q c** thì có dòng B không?

Trả lời: **Không**. c chỉ mustRunAfter(b), không dependsOn(b). Với cấu hình này, stdout của task là **C**.

**Câu 3.** Chạy **./gradlew -q allDemo** thì thứ tự các dòng?

Trả lời: **A, B, C, ALL**. allDemo phụ thuộc b và c; b phụ thuộc a; c mustRunAfter b, nên thứ tự bị ràng buộc hoàn toàn.

**Câu 4.** Nếu thay **mustRunAfter(b)** của c thành **shouldRunAfter(b)**, có nên viết test khẳng định tuyệt đối dòng B luôn trước C trong mọi cấu hình chạy song song?

Trả lời: **Không**. shouldRunAfter chỉ là ưu tiên mềm và có trường hợp bị bỏ qua; nếu đầu ra C thực sự cần từ B, hãy khai báo dependency.

**Câu 5.** Chạy **./gradlew allDemo --dry-run**, có thấy task trong kế hoạch nhưng không thấy các dòng A/B/C/ALL do doLast in ra không?

Trả lời: **Đúng**. Dry-run hiển thị kế hoạch task mà không thực thi các action đó.

## 16. Kết luận áp dụng

Khi viết Gradle build logic, hãy **khai báo trước** tất cả quan hệ và nguồn đầu ra/đầu vào trong configuration, rồi để Gradle tạo task graph và quyết định lịch chạy. Để chọn API đúng, hãy tự hỏi:

- **B cần A hoàn thành để làm việc của mình?** → **dependsOn** hoặc liên kết input/output có metadata producer.
- **Cần A trước B nếu cả hai cùng chạy, nhưng B vẫn chạy được độc lập?** → **mustRunAfter**.
- **Chỉ ưu tiên A trước B nếu tiện?** → **shouldRunAfter**.
- **Cần dọn dẹp sau A?** → **finalizedBy**.
- **Muốn xem graph mà chưa thực thi task action?** → **--dry-run**.
- **Muốn phân biệt script cấu hình và task action?** → dùng ví dụ **phaseDemo** và quan sát CONFIG/EXECUTE.
- **Muốn lý giải task không in output?** → kiểm tra task có trong graph không, rồi kiểm tra trạng thái skip/up-to-date/cache.

Nắm chắc **thời điểm tính graph** và **bản chất từng quan hệ** sẽ giúp bạn dự đoán build đáng tin cậy, phát hiện sớm lỗi chu trình/phụ thuộc thiếu và tối ưu task mà không dựa vào thứ tự tình cờ.

## 17. Tài liệu chính thức

- Gradle Build Lifecycle: https://docs.gradle.org/current/userguide/build_lifecycle.html
- Controlling Task Execution (dependsOn, ordering, finalizer, skipping): https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Task Configuration Avoidance (tasks.register, TaskProvider, lazy relationships): https://docs.gradle.org/current/userguide/task_configuration_avoidance.html
- Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Command-Line Interface: https://docs.gradle.org/current/userguide/command_line_interface.html

Khi áp dụng vào dự án cụ thể, hãy dùng **tài liệu đúng phiên bản Gradle Wrapper** vì chi tiết về scheduler, Configuration Cache và API lifecycle có thể thay đổi giữa các release.
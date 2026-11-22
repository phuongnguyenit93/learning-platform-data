# Thực thi song song dựa trên đồ thị phụ thuộc

Build tool có thể rút ngắn thời gian build bằng cách thực hiện đồng thời những công việc độc lập. Tuy nhiên, không phải task nào cũng có thể chạy ở bất kỳ thời điểm nào. Một bước biên dịch có thể cần output từ bước sinh mã; một bước đóng gói cần các lớp đã biên dịch; một module có thể cần thư viện được tạo bởi module khác. Build tool phải tôn trọng những quan hệ đó khi lập lịch.

Cơ chế nền tảng là **đồ thị phụ thuộc (dependency graph)**. Mỗi task hoặc module là một nút. Quan hệ phụ thuộc xác định nút nào phải hoàn tất trước nút nào. Những nút đã sẵn sàng và không bị ràng buộc thứ tự với nhau có thể được thực hiện song song nếu build tool, plugin và tài nguyên cho phép.

~~~text
                 build
                /     \
               v       v
            check    assemble
              |         |
              v         v
             test      jar
              |         |
              v         v
        testClasses   classes
~~~

Trong sơ đồ này, các nhánh có quan hệ phụ thuộc phải chờ đúng đầu vào. Nếu hai nhánh không phụ thuộc lẫn nhau, build tool có thể thực hiện chúng đồng thời. Task graph quyết định điều gì được phép chạy; bộ lập lịch và giới hạn worker quyết định mức song song thực tế.

Bài học này tập trung vào cách build tool lập lịch công việc theo dependency graph, cách bật và điều chỉnh thực thi song song trong Gradle và Maven, cùng những điều kiện cần để tránh race condition, ghi đè output và kết quả build không ổn định.

## 1. Vì sao build tool cần đồ thị phụ thuộc?

Một lệnh build thường yêu cầu nhiều công việc. Ví dụ, để tạo JAR ứng dụng, build tool có thể cần:

1. Biên dịch mã nguồn Java.
2. Xử lý và sao chép tài nguyên.
3. Biên dịch mã kiểm thử.
4. Chạy kiểm thử.
5. Đóng gói lớp và tài nguyên thành JAR.
6. Tạo báo cáo hoặc artifact bổ sung.

Một số công việc phụ thuộc trực tiếp vào công việc khác. Không thể đóng gói lớp Java trước khi lớp đó được biên dịch. Nhưng một tác vụ kiểm tra tài liệu độc lập có thể chạy cùng lúc với một tác vụ kiểm thử, nếu chúng không dùng chung tài nguyên theo cách gây xung đột.

Nếu build tool chỉ chạy mọi task theo một danh sách cố định, nhiều thời gian có thể bị lãng phí khi CPU hoặc I/O đang rảnh. Nếu chạy tất cả task cùng lúc mà không quan tâm dependency, kết quả có thể sai vì task đọc một file trước khi task tạo file đó hoàn tất.

Dependency graph giải quyết hai yêu cầu:

- Bảo đảm thứ tự bắt buộc giữa các công việc có quan hệ phụ thuộc.
- Cho phép thực hiện đồng thời những công việc độc lập khi có tài nguyên.

## 2. Đồ thị phụ thuộc là gì?

Đồ thị phụ thuộc là mô hình biểu diễn các công việc và quan hệ giữa chúng.

- **Nút (node):** một task, module hoặc đơn vị công việc.
- **Cạnh phụ thuộc (dependency edge):** quan hệ cho biết một nút cần kết quả từ nút khác.
- **Nút sẵn sàng (ready node):** mọi dependency bắt buộc của nó đã hoàn tất.
- **Nút hoàn tất (completed node):** công việc đã kết thúc với trạng thái được build tool ghi nhận.
- **Đồ thị có hướng không chu trình (DAG):** đồ thị trong đó không có đường phụ thuộc quay trở lại chính nút ban đầu.

~~~text
compileCore ───────┐
                   v
               compileApp ──────┐
                                 v
                              package
                                 ^
                                 |
processResources ───────────────┘
~~~

Task package cần compileApp và processResources. compileApp lại cần compileCore. Vì vậy, package chưa sẵn sàng cho đến khi các dependency cần thiết hoàn tất.

Một đồ thị hợp lệ không có chu trình phụ thuộc. Nếu task A cần task B, task B lại cần task A, build tool không thể tìm ra thứ tự thực thi hợp lệ. Gradle thường báo lỗi circular dependency khi lập kế hoạch; Maven reactor cũng không thể xây dựng thứ tự module hợp lệ khi có vòng phụ thuộc giữa các project.

### Cạnh phụ thuộc không nhất thiết có nghĩa là chạy ngay sau nhau

Nếu task B phụ thuộc task A, điều đó có nghĩa B phải chờ A hoàn tất. Không có nghĩa B phải bắt đầu ngay khi A xong. Build tool có thể thực hiện một task khác đã sẵn sàng trước B, tùy lịch và tài nguyên.

Ví dụ:

~~~text
       A
      / \
     v   v
     B   C
      \ /
       v
       D
~~~

A phải hoàn tất trước B và C. B và C độc lập nên có thể chạy đồng thời. D phải chờ cả B lẫn C. Nếu C hoàn tất trước B, D vẫn phải chờ B.

## 3. Cách bộ lập lịch chọn task có thể chạy

Một build tool thường thực hiện các bước khái quát sau:

1. Nhận các task hoặc lifecycle mục tiêu từ lệnh người dùng.
2. Lần theo dependency để xây dựng graph đầy đủ.
3. Kiểm tra graph có hợp lệ và không có chu trình hay không.
4. Xác định những task có dependency đã hoàn tất.
5. Chọn task sẵn sàng theo thứ tự và giới hạn tài nguyên.
6. Khi một task hoàn tất, cập nhật graph và đưa các task mới vào tập sẵn sàng.
7. Tiếp tục đến khi mọi task trong graph đã hoàn tất hoặc build thất bại/bị hủy.

~~~text
Thời điểm 1: A sẵn sàng
             |
             v
           [A]

Thời điểm 2: A hoàn tất, B và C cùng sẵn sàng
             |
             +--------+
             v        v
            [B]      [C]

Thời điểm 3: B và C hoàn tất, D sẵn sàng
             |
             v
            [D]
~~~

Đây là mô hình minh họa, không phải cam kết về số luồng hoặc thứ tự log của một build cụ thể. Plugin, task type, giới hạn worker và trạng thái up-to-date/cache có thể làm thay đổi các công việc thực sự được thực thi.

### Task có trong graph nhưng không nhất thiết chạy hành động

Một task có thể được đưa vào graph nhưng được đánh dấu up-to-date, restored from cache, no-source hoặc skipped. Khi đó build tool vẫn xử lý trạng thái của task trong kế hoạch nhưng không nhất thiết chạy toàn bộ action của nó.

Do đó, số task được liệt kê trong graph không đồng nghĩa với số task thực sự chiếm CPU cùng lúc.

### Task thất bại ảnh hưởng đến graph ra sao?

Nếu một task thất bại, các task phụ thuộc cần output của nó thường không thể tiếp tục bình thường. Những nhánh độc lập có thể đã chạy hoặc vẫn được thực hiện tùy cơ chế fail-fast, cấu hình và build tool. Không nên dựa vào việc một task độc lập luôn hoàn tất sau khi một task khác thất bại; hãy đọc trạng thái task và log của lần build đó.

## 4. Phụ thuộc dữ liệu và phụ thuộc thứ tự

Một build script cần mô tả đúng lý do task này phải chờ task khác.

**Phụ thuộc dữ liệu** có nghĩa task B cần output do task A tạo ra. Đây thường là quan hệ dependency thực sự.

**Phụ thuộc thứ tự** có nghĩa task B chỉ cần chạy sau A nếu cả hai đều đã được chọn vào build graph. Quan hệ này không nhất thiết yêu cầu A phải được chạy.

Trong Gradle, các cơ chế thường gặp:

| Cơ chế | Tác dụng | Có tự đưa task được nhắc đến vào graph? |
|---|---|---|
| dependsOn | Yêu cầu dependency hoàn tất trước task hiện tại. | Có. |
| mustRunAfter | Nếu cả hai task được chọn, task hiện tại phải chạy sau task kia. | Không. |
| shouldRunAfter | Nếu cả hai được chọn, ưu tiên thứ tự đó khi có thể. | Không. |
| finalizedBy | Đăng ký task finalizer chạy sau task được finalize. | Có, khi task chính được chọn. |

Ví dụ:

~~~groovy
tasks.register('generateConfig') {
    // Tạo file cấu hình build/generated/app.yml
}

tasks.register('packageApp') {
    dependsOn tasks.named('generateConfig')
}
~~~

packageApp cần file do generateConfig tạo nên dùng dependsOn. Nếu chỉ dùng mustRunAfter, Gradle có thể chạy packageApp mà không chạy generateConfig khi task đó chưa được yêu cầu bởi graph.

Ví dụ ordering rule:

~~~groovy
tasks.named('publishReport') {
    mustRunAfter tasks.named('test')
}
~~~

Quy tắc này chỉ sắp xếp thứ tự nếu test và publishReport đều có trong graph. Nó không làm cho lệnh chạy publishReport tự động chạy test.

### Vì sao khai báo sai quan hệ làm mất tính đúng đắn?

Nếu task B đọc file do task A tạo nhưng không khai báo dependency hoặc output provider phù hợp, build tool có thể xem B là độc lập. Khi chạy song song, B có thể bắt đầu trước khi file tồn tại hoặc đọc phiên bản cũ. Build có thể lúc thành công, lúc thất bại tùy thời điểm lập lịch.

Hãy khai báo quan hệ dữ liệu thật sự. Đừng dùng một ordering rule chỉ để làm log trông có thứ tự nếu task cần output của nhau.

## 5. Gradle: thực thi song song giữa các project

Gradle xây dựng task graph cho build. Với multi-project build, một cách tăng mức song song là cho phép các task thuộc những project khác nhau chạy đồng thời.

Mặc định, thực thi song song giữa project không được bật. Có thể bật bằng option dòng lệnh:

~~~shell
./gradlew build --parallel
~~~

Trên Windows:

~~~powershell
.\gradlew.bat build --parallel
~~~

Hoặc đặt trong gradle.properties:

~~~properties
org.gradle.parallel=true
~~~

Khi bật, Gradle có thể chạy các task sẵn sàng từ những project khác nhau đồng thời, miễn là quan hệ phụ thuộc và điều kiện thực thi cho phép.

### Giới hạn số worker

Dùng --max-workers để giới hạn số worker được sử dụng:

~~~shell
./gradlew build --parallel --max-workers=4
~~~

Có thể cấu hình trong gradle.properties:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=4
~~~

Giới hạn worker là giới hạn tài nguyên thực thi, không phải yêu cầu Gradle phải luôn chạy đúng số task đó. Nếu graph chỉ có một task sẵn sàng, chỉ một task có thể chạy. Nếu task bị chặn bởi dependency hoặc tài nguyên dùng chung, số worker đang hoạt động có thể thấp hơn giới hạn.

### Ví dụ multi-project

Giả sử repository có ba module:

~~~text
workspace/
├── settings.gradle
├── api/
│   └── build.gradle
├── service/
│   └── build.gradle
└── web/
    └── build.gradle
~~~

Module service và web cùng phụ thuộc api:

~~~groovy
// service/build.gradle
dependencies {
    implementation project(':api')
}
~~~

~~~groovy
// web/build.gradle
dependencies {
    implementation project(':api')
}
~~~

Có thể yêu cầu build hai module ứng dụng:

~~~shell
./gradlew :service:build :web:build --parallel --max-workers=4
~~~

Gradle phải hoàn thành những task cần thiết của api trước các task phụ thuộc vào output của nó. Sau khi dependency dùng chung đã sẵn sàng, các nhánh độc lập của service và web có thể được thực hiện đồng thời.

~~~text
             api:classes
               /    \
              v      v
    service:compile  web:compile
              |      |
              v      v
        service:test web:test
              |      |
              v      v
        service:jar  web:jar
~~~

Sơ đồ không thể hiện mọi task nội bộ của Java plugin, nhưng cho thấy nguyên tắc: hai module không phụ thuộc lẫn nhau có thể chạy song song sau khi output chung đã sẵn sàng.

### Task trong cùng project và task ở project khác

Option --parallel chủ yếu cho phép Gradle thực thi task đồng thời giữa các project. Không nên hiểu nó là mọi task trong cùng một project sẽ tự động chạy song song. Nếu một task cần xử lý nhiều đơn vị công việc độc lập bên trong chính task đó, task author có thể sử dụng Worker API hoặc cơ chế song song riêng.

Đây là hai lớp song song khác nhau:

- **Project/task parallelism:** nhiều task thuộc các project khác nhau được chạy đồng thời.
- **Work-item parallelism:** một task chia công việc thành nhiều đơn vị và gửi chúng đến worker để xử lý đồng thời.

## 6. Gradle Worker API và công việc bên trong một task

Một task có thể thực hiện một vòng lặp dài qua nhiều file hoặc nhiều đơn vị dữ liệu. Nếu xử lý tuần tự, một task duy nhất có thể trở thành nút thắt dù các đơn vị công việc độc lập.

Gradle Worker API cho phép task author gửi các đơn vị công việc đến worker queue. Gradle quản lý việc thực thi và giới hạn concurrency dựa trên worker leases và cấu hình build.

Ví dụ khái niệm:

~~~text
Task: processResources
       |
       +----> Work item A
       |
       +----> Work item B
       |
       +----> Work item C
       |
       +----> Work item D

Các work item độc lập có thể được xử lý đồng thời.
~~~

Worker API có các chế độ isolation khác nhau:

- **No isolation:** worker dùng chung môi trường classloader với build logic. Phù hợp khi work action an toàn với trạng thái dùng chung.
- **Classloader isolation:** worker dùng classloader riêng, hữu ích khi cần tách classpath hoặc trạng thái static.
- **Process isolation:** worker chạy trong process riêng, có mức cách ly cao hơn nhưng chi phí khởi tạo và bộ nhớ lớn hơn.

Task author phải thiết kế input/output của từng work item rõ ràng. Nếu nhiều worker ghi cùng một file hoặc dùng chung mutable state không được đồng bộ, vẫn có race condition dù Gradle quản lý worker queue.

### Worker API không tự làm task an toàn

Worker API giúp lập lịch và cách ly công việc. Nó không tự xác định dữ liệu có thể chia sẻ an toàn hay không. Người viết task phải bảo đảm:

- Mỗi work item nhận đúng input của nó.
- Các work item không ghi đè output của nhau.
- Không dùng mutable static state không an toàn.
- Tài nguyên dùng chung có cơ chế đồng bộ hoặc giới hạn concurrency.
- Output được khai báo để Gradle có thể theo dõi.

Nếu công việc không đủ lớn hoặc phải chờ một dịch vụ tuần tự, tạo nhiều worker có thể làm build chậm hơn.

## 7. Song song hóa kiểm thử trong Gradle

Test task có thể chạy test trong các JVM fork riêng. Đây là lớp song song khác với việc Gradle chạy nhiều project task đồng thời.

Ví dụ:

~~~groovy
tasks.test {
    maxParallelForks = 2
}
~~~

Thiết lập này cho phép tối đa hai test process fork đồng thời cho task test. Mặc định thường là một process. Test framework bên trong mỗi process cũng có thể có cơ chế parallel execution riêng.

Nếu bật cả hai lớp, tổng mức concurrency có thể lớn hơn dự kiến. Ví dụ Gradle chạy hai Test task của hai project đồng thời, mỗi task lại fork hai JVM. Khi đó có thể có đến bốn test JVM hoạt động, chưa kể worker khác.

### Parallel test và dữ liệu dùng chung

Test có thể không độc lập nếu chúng cùng:

- Ghi vào một database schema.
- Dùng chung port cố định.
- Ghi cùng file tạm hoặc thư mục output.
- Sửa cùng một file cấu hình.
- Dùng chung tài khoản hoặc trạng thái của external service.
- Phụ thuộc thứ tự chạy hoặc dữ liệu do test trước tạo.

Trước khi tăng maxParallelForks, hãy bảo đảm test độc lập hoặc cấp namespace/database/file/port riêng cho từng process.

### Parallel execution trong JUnit

JUnit Jupiter có hỗ trợ cấu hình parallel execution. Đây là thiết lập của test framework, không phải option --parallel của Gradle. Có thể bật qua cấu hình JUnit Platform và execution mode phù hợp với phiên bản JUnit đang dùng.

Khi kết hợp parallel test ở JUnit với nhiều fork JVM từ Gradle, cần tính đến concurrency tổng thể. Bắt đầu với một lớp song song, đo thời gian và tài nguyên, sau đó mới tăng dần.

## 8. Maven: song song hóa multi-module reactor

Maven có mô hình reactor để xây dựng nhiều module trong một multi-module project. Reactor đọc quan hệ dependency giữa các module, sắp xếp thứ tự build hợp lệ và có thể thực thi các module độc lập đồng thời.

Dùng option -T để bật multi-threaded reactor build.

~~~shell
mvn -T 4 clean verify
~~~

Lệnh trên yêu cầu Maven dùng tối đa bốn thread cho reactor build.

Có thể dùng số thread theo số core:

~~~shell
mvn -T 1C clean verify
~~~

1C yêu cầu một thread cho mỗi CPU core mà Maven nhận diện. Có thể dùng hệ số như 1.5C nếu cần thử nghiệm, nhưng nên đo tải thực tế và tránh cấp quá nhiều thread cho máy hoặc CI runner có giới hạn CPU.

### Ví dụ multi-module Maven

Cấu trúc:

~~~text
parent/
├── pom.xml
├── api/
│   └── pom.xml
├── service/
│   └── pom.xml
└── web/
    └── pom.xml
~~~

Parent POM khai báo module:

~~~xml
<modules>
    <module>api</module>
    <module>service</module>
    <module>web</module>
</modules>
~~~

service và web khai báo dependency đến api. Reactor phải build api trước những module cần artifact của nó. Sau đó service và web có thể được build đồng thời nếu không có quan hệ phụ thuộc khác.

~~~shell
mvn -T 1C clean verify
~~~

Maven vẫn tuân thủ dependency order. Parallel reactor không có nghĩa mọi module chạy cùng lúc hoặc bỏ qua thứ tự dependency.

### Chọn một nhóm module cụ thể

Maven hỗ trợ chọn project trong reactor:

~~~shell
mvn -pl service,web -am -T 1C verify
~~~

- -pl chọn các project cần build.
- -am yêu cầu Maven cũng build những project trong reactor mà các project được chọn phụ thuộc.
- -amd có thể dùng để chọn các project phụ thuộc vào project được chỉ định.

Ví dụ, nếu chỉ chọn api và dùng -amd, Maven có thể bao gồm các module downstream phụ thuộc api. Hãy xem reactor summary để xác nhận đúng module được chọn.

## 9. Plugin thread safety trong Maven

Maven parallel reactor có thể thực thi các module đồng thời, nhưng plugin goal phải an toàn khi được gọi song song trên nhiều project.

Một plugin goal được đánh dấu thread-safe cho biết nhà phát triển plugin tuyên bố goal có thể được thực thi đồng thời trong reactor theo hợp đồng của plugin. Nếu plugin không khai báo thread safety, Maven có thể hiển thị cảnh báo khi chạy parallel build.

Cần chú ý:

- Cảnh báo thread safety không nhất thiết có nghĩa build chắc chắn sai, nhưng là tín hiệu cần kiểm tra.
- Không nên bỏ qua cảnh báo nếu plugin ghi vào file dùng chung hoặc sửa trạng thái toàn cục.
- Nâng plugin lên phiên bản có hỗ trợ thread safety nếu có.
- Kiểm tra tài liệu plugin và issue/release note.
- Nếu plugin không an toàn, có thể chạy build tuần tự hoặc tách phần công việc gây xung đột.

### Output riêng cho từng module

Plugin nên ghi output vào thư mục build của module tương ứng, thường là target/. Không nên để nhiều module cùng ghi một file ở thư mục chung mà không có cơ chế phối hợp.

Nếu plugin dùng file tạm, hãy đặt tên theo module/build execution hoặc dùng API tạo file tạm an toàn. Nếu plugin kết nối một dịch vụ bên ngoài, cần xác định giới hạn đồng thời và dữ liệu có thể chia sẻ hay không.

## 10. Vì sao parallel build đôi khi không nhanh hơn?

Song song hóa không bảo đảm thời gian build giảm theo tỷ lệ số worker. Có nhiều giới hạn:

- **Critical path:** chuỗi dependency dài nhất vẫn phải chờ theo thứ tự.
- **Công việc tuần tự:** một số task hoặc module không có phần độc lập để chạy song song.
- **CPU contention:** quá nhiều worker tranh CPU làm tăng context switching.
- **Memory pressure:** nhiều compiler/test JVM cùng chạy có thể làm thiếu RAM hoặc gây GC nhiều.
- **Disk I/O:** nhiều task cùng đọc/ghi ổ đĩa có thể tranh băng thông.
- **Network:** tải dependency hoặc gọi dịch vụ ngoài đồng thời có thể bị giới hạn.
- **Synchronization:** lock và tài nguyên dùng chung buộc task phải chờ.
- **Startup overhead:** tạo process, JVM hoặc worker có chi phí đáng kể.

Một mô hình đo lường đơn giản:

~~~text
Speedup = Thời gian build tuần tự / Thời gian build song song
~~~

Nếu build tuần tự mất 10 phút và build song song mất 6 phút, speedup là khoảng 1,67 lần. Không nên kỳ vọng dùng bốn worker sẽ tự động làm build nhanh gấp bốn lần.

### Critical path quyết định giới hạn tốc độ

Nếu một chuỗi task chiếm phần lớn thời gian và tất cả task sau phụ thuộc vào chuỗi đó, tăng số worker không làm chuỗi này ngắn đi. Muốn cải thiện, cần tối ưu task trên critical path, giảm công việc không cần thiết hoặc tách phần xử lý độc lập.

### Cân bằng CPU và memory

Compiler, test JVM và worker process đều tiêu thụ bộ nhớ. Một máy có nhiều CPU core nhưng ít RAM có thể build chậm hoặc OOM khi chạy quá nhiều task đồng thời. Hãy đo CPU, RAM, disk và thời gian task trước khi tăng giới hạn.

## 11. Race condition và output dùng chung

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các công việc đồng thời truy cập dữ liệu chung.

Ví dụ hai task cùng ghi một file:

~~~text
Task A ───────┐
              ├──> build/generated/version.txt
Task B ───────┘
~~~

Nếu cả hai ghi file cùng lúc, nội dung cuối có thể phụ thuộc task nào ghi sau hoặc hai lần ghi có thể xen kẽ. Build tool không thể tự suy ra rằng output dùng chung là không an toàn nếu build script không mô tả hoặc bảo vệ tài nguyên đó.

### Cách thiết kế an toàn

- Mỗi task có output directory/file riêng.
- Task chỉ ghi output đã khai báo.
- Task đọc output từ provider/dependency của task tạo ra nó.
- Không dùng thư mục tạm chung với tên file cố định cho nhiều worker.
- Không dựa vào thứ tự thực thi không được khai báo.
- Dùng lock hoặc build service khi thật sự cần chia sẻ tài nguyên.
- Test độc lập dữ liệu và external resource.

### Shared Build Service trong Gradle

Gradle Build Service có thể quản lý một tài nguyên dùng chung giữa nhiều task, chẳng hạn client kết nối đến dịch vụ hoặc giới hạn số lần gọi một API. Service có thể khai báo mức sử dụng song song tối đa để kiểm soát truy cập.

Đây là lựa chọn phù hợp hơn việc tạo một biến static toàn cục trong build logic. Tuy nhiên, service cần được thiết kế với lifecycle, đồng bộ và giới hạn tài nguyên rõ ràng.

### Không dựa vào thứ tự log

Khi task chạy song song, log từ nhiều task có thể xen kẽ. Thứ tự dòng log không nhất thiết phản ánh thứ tự dependency hoặc nguyên nhân lỗi. Hãy dùng tên task, timestamp, build scan hoặc log của task cụ thể để điều tra.

## 12. Các quy tắc để task an toàn khi chạy song song

Một task có thể chạy song song tốt khi nó đáp ứng các điều kiện:

1. Input của task được khai báo và không bị sửa trong lúc task đang chạy.
2. Output của task có vị trí riêng hoặc có cơ chế ghi đồng bộ.
3. Task không dựa vào mutable global state dùng chung.
4. Mọi dependency dữ liệu được mô tả bằng task dependency hoặc provider wiring.
5. External resource có giới hạn concurrency và timeout rõ ràng.
6. Task không dựa vào thứ tự tình cờ của các task độc lập.
7. Plugin được hỗ trợ thread safety theo cách nó được sử dụng.
8. Test không dùng chung trạng thái có thể làm thay đổi kết quả.

### Task configuration và task execution

Gradle có giai đoạn configuration để cấu hình project/task và giai đoạn execution để chạy task actions. Không nên tạo hoặc sửa cấu hình project tùy tiện từ task action, đặc biệt khi build bật các tính năng isolation hoặc configuration cache. Build logic hiện đại nên dùng task properties và provider để truyền dữ liệu.

Parallel task execution là vấn đề ở giai đoạn thực thi. Configuration cache và isolated projects là các cơ chế khác liên quan đến tốc độ/cách ly cấu hình; chúng không phải tên khác của task parallelism.

## 13. Maven và Gradle khác nhau ở phạm vi song song

| Khía cạnh | Gradle | Maven |
|---|---|---|
| Mô hình lập kế hoạch | Task graph | Reactor graph và lifecycle/plugin goals |
| Đơn vị song song chính | Task giữa các project; work items qua Worker API; test fork | Các module độc lập trong reactor |
| Bật song song | --parallel hoặc org.gradle.parallel=true | -T 4 hoặc -T 1C |
| Giới hạn concurrency | --max-workers hoặc org.gradle.workers.max | Số thread trong -T |
| Quan hệ dependency | dependsOn và project dependency | Module dependency trong reactor |
| Điều kiện an toàn | Task/plugin không tranh chấp state và output | Plugin goal cần hỗ trợ thread-safe |
| Song song test | Test forks và test framework parallel settings | Surefire/Failsafe fork và framework settings |
| Quan sát | Task graph, log, build scan | Reactor build order, thread log, plugin warnings |

Không nên so sánh trực tiếp --parallel với -T như thể chúng điều khiển đúng cùng một đơn vị công việc. Gradle task graph và Maven reactor có cấu trúc khác nhau. Hãy xác định bottleneck nằm ở module, task, test process hay work item trước khi chọn option.

## 14. Quan sát và chẩn đoán parallel execution

### Gradle

Xem task graph ở chế độ dry run:

~~~shell
./gradlew build --dry-run
~~~

Chạy với parallel execution và log chi tiết:

~~~shell
./gradlew build --parallel --max-workers=4 --info
~~~

Có thể dùng --scan nếu tổ chức cho phép tạo và chia sẻ Build Scan. Build Scan giúp quan sát thời gian task, dependency, worker và các điểm nghẽn. Kiểm tra chính sách dữ liệu trước khi publish scan ra dịch vụ bên ngoài.

Trong multi-project build, dùng đường dẫn task để giới hạn phạm vi:

~~~shell
./gradlew :service:build :web:build --parallel --max-workers=4
~~~

Nếu muốn xác định task nào đang chờ, xem graph và log; không suy luận chỉ từ thời điểm dòng log xuất hiện.

### Maven

Chạy reactor song song với log:

~~~shell
mvn -T 4 -Dstyle.color=never clean verify
~~~

Maven hiển thị thông tin reactor build order và summary. Theo dõi cảnh báo plugin không thread-safe, lỗi ghi file chung và module nào thất bại.

Có thể giới hạn project trong reactor bằng -pl và chọn dependency/dependent modules bằng -am hoặc -amd. Đọc reactor summary để biết chính xác module nào được build.

### So sánh lần chạy tuần tự và song song

Để đo hiệu quả, hãy dùng cùng commit, cùng JDK, cùng dependency state và cùng lệnh build tương đương. Thực hiện nhiều lần nếu có biến động do cache hoặc I/O. Ghi lại:

- Thời gian tổng.
- Thời gian các task/module lớn.
- CPU và memory peak.
- Số worker/process hoạt động.
- Lỗi hoặc cảnh báo concurrency.
- Trạng thái cache và dependency resolution.

Không so sánh lần chạy đầu tiên tải toàn bộ dependency với lần chạy thứ hai đã có cache rồi kết luận toàn bộ chênh lệch là do parallelism.

## 15. Tăng mức song song từng bước

Một cách thực hành an toàn:

1. Chạy build tuần tự để xác nhận baseline.
2. Xem graph và xác định các nhánh độc lập.
3. Bật parallel execution với giới hạn worker nhỏ.
4. Chạy lại test và kiểm tra output.
5. Tăng worker từng bước nếu CPU/RAM còn dư.
6. Nếu xuất hiện lỗi ngẫu nhiên, giảm concurrency và tìm resource dùng chung.
7. Chỉ giữ mức song song đem lại lợi ích ổn định.

Ví dụ Gradle:

~~~shell
./gradlew clean test --max-workers=2
./gradlew clean test --parallel --max-workers=2
./gradlew clean test --parallel --max-workers=4
~~~

Ví dụ Maven:

~~~shell
mvn clean verify
mvn -T 2 clean verify
mvn -T 1C clean verify
~~~

Các lệnh trên minh họa cách đo. Không nên chạy chúng đồng thời trên cùng working directory vì chúng có thể cùng xóa hoặc ghi output. Chạy tuần tự và bảo đảm mỗi phép đo dùng trạng thái đầu vào tương đương.

## 16. Các trường hợp nên hạn chế hoặc tắt song song

Có những công việc nên chạy tuần tự hoặc có giới hạn concurrency:

- Migration database dùng cùng schema.
- Test tích hợp dùng chung dữ liệu hoặc port cố định.
- Plugin cũ ghi vào một file output dùng chung.
- Công cụ license/build chỉ cho phép một phiên chạy.
- Tác vụ publish cùng một artifact/version đến repository.
- Task sửa cùng file generated.
- Dịch vụ ngoài có rate limit thấp.
- Build runner có memory hạn chế.

Không nhất thiết phải tắt song song toàn bộ build. Có thể tách task gây xung đột, dùng service giới hạn concurrency, tạo database/schema riêng hoặc dùng ordering/dependency rule đúng mục đích.

Nếu phải dùng mustRunAfter để tránh hai task xung đột, hãy xác định rõ cả hai task có thực sự cùng xuất hiện trong graph không. Nếu task B cần task A chạy trước trong mọi lần B được yêu cầu, dependsOn hoặc dependency dữ liệu phù hợp hơn.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Bật --parallel nghĩa là mọi task chạy đồng thời | Chỉ task sẵn sàng và không bị ràng buộc mới có thể chạy đồng thời; worker limit và tài nguyên còn giới hạn concurrency. |
| Task độc lập trong log luôn phải xuất hiện theo một thứ tự | Thứ tự có thể thay đổi giữa các lần chạy; không dựa vào log order nếu chưa khai báo dependency. |
| mustRunAfter tương đương dependsOn | mustRunAfter chỉ sắp xếp task đã có trong graph; dependsOn đưa dependency vào graph. |
| --max-workers=4 bảo đảm có bốn task chạy cùng lúc | Đây là giới hạn tối đa, không phải số lượng bắt buộc. |
| Gradle --parallel và Maven -T điều khiển cùng một phạm vi | Gradle chủ yếu song song task giữa project; Maven song song các module trong reactor. |
| Task nào cũng an toàn khi chạy song song | Shared state, output và external resource có thể gây race condition. |
| Worker API tự làm code thread-safe | Task author vẫn phải thiết kế input/output và state an toàn. |
| Build nhanh hơn khi tăng worker vô hạn | CPU, memory, disk, network và critical path giới hạn tốc độ. |
| Maven -T luôn an toàn với mọi plugin | Plugin goal cần hỗ trợ thread safety; cảnh báo phải được xem xét. |
| Test parallelism giống project parallelism | Test fork/framework concurrency là một lớp riêng, có thể nhân mức concurrency tổng. |
| Nếu một task có trong graph thì nó luôn thực thi action | Task có thể up-to-date, from-cache, no-source hoặc skipped. |
| Build chạy tuần tự thành công thì chạy song song chắc chắn thành công | Parallel execution có thể bộc lộ race condition và giả định thứ tự bị thiếu. |

## 18. Quy trình điều tra lỗi chỉ xuất hiện khi chạy song song

Nếu build tuần tự thành công nhưng build song song thất bại, hãy điều tra theo thứ tự:

1. Ghi lại commit, wrapper version, JDK và lệnh chính xác.
2. Xác định task/module đầu tiên thất bại.
3. Xem task đó đọc và ghi những file nào.
4. Kiểm tra có task khác cùng đọc/ghi output hoặc resource không.
5. Kiểm tra dependency edge có bị thiếu không.
6. Kiểm tra plugin có cảnh báo thread safety không.
7. Kiểm tra test có dùng chung database, port, file hoặc tài khoản không.
8. Giảm worker để xem lỗi có liên quan concurrency không.
9. Chạy lại với log chi tiết và cùng input.
10. Sửa mô hình dependency hoặc cô lập tài nguyên, rồi bật lại song song để xác nhận.

### Ví dụ: file generated bị ghi đè

Hai task generateA và generateB cùng ghi build/generated/config.json. Build tuần tự có thể luôn cho kết quả của task chạy sau. Khi chạy song song, file có thể bị ghi xen kẽ hoặc nội dung thay đổi không dự đoán được.

Cách sửa là cho mỗi task tạo output riêng, sau đó có một task tổng hợp đọc cả hai output và tạo file cuối. Nếu thật sự cần một file chung, phải có một task duy nhất sở hữu output đó hoặc một cơ chế phối hợp được thiết kế rõ ràng.

### Ví dụ: integration test dùng cùng database

Hai test suite cùng xóa bảng hoặc tạo record với cùng ID. Khi chạy đồng thời, một suite có thể xóa dữ liệu mà suite kia đang kiểm tra. Giải pháp có thể là cấp schema/database riêng cho từng worker, dùng dữ liệu test độc lập hoặc giới hạn concurrency của nhóm test đó.

## 19. Bài thực hành

Thực hành trên một multi-project build có ít nhất ba module:

1. Tạo module api, service và web.
2. Khai báo service và web cùng phụ thuộc api.
3. Chạy build tuần tự và ghi lại thời gian.
4. Chạy Gradle với --parallel và giới hạn --max-workers=2.
5. Quan sát task graph và xác định những nhánh có thể chạy đồng thời.
6. Tăng worker lên 4 nếu máy có đủ CPU/RAM, sau đó so sánh thời gian và mức sử dụng tài nguyên.
7. Tạo một task tùy chỉnh có output riêng, rồi khai báo dependency cho task tiêu thụ output đó.
8. Thử tạo hai task ghi cùng một file trong môi trường thử nghiệm để hiểu race condition; sau đó thiết kế lại output riêng và task tổng hợp.
9. Bật test fork concurrency ở mức nhỏ và xác nhận test không dùng chung dữ liệu gây xung đột.
10. Nếu có Maven multi-module project, chạy tuần tự rồi chạy với -T 2 hoặc -T 1C; đọc cảnh báo plugin thread safety và reactor summary.
11. Ghi lại critical path, task/module tốn thời gian và mức concurrency ổn định.
12. Viết hướng dẫn cho nhóm về mức parallelism phù hợp trên máy phát triển và CI runner.

Sau bài thực hành, bạn cần giải thích được task graph quyết định thứ tự bắt buộc thế nào, tại sao các nhánh độc lập có thể chạy đồng thời, cách bật/giới hạn parallel execution trong Gradle và Maven, và vì sao thread safety cùng output isolation quan trọng.

## 20. Tiêu chí sử dụng parallel execution trong dự án

Một cấu hình song song phù hợp cần thỏa mãn:

- Dependency graph mô tả đủ các quan hệ dữ liệu.
- Task/module độc lập có thể chạy đồng thời mà không tranh chấp output.
- Plugin và task tùy chỉnh an toàn với cách chạy được chọn.
- Test không phụ thuộc thứ tự hoặc dữ liệu dùng chung không được cô lập.
- CPU, memory, disk và network đủ cho mức concurrency.
- Build vẫn tạo kết quả đúng và ổn định qua nhiều lần chạy.
- Thời gian build thực tế được đo trên môi trường tương đương.
- CI và máy phát triển dùng cấu hình worker phù hợp với tài nguyên của từng môi trường.

Song song hóa là một cách tận dụng các công việc độc lập đã được mô tả đúng trong build graph. Nếu graph thiếu dependency hoặc task chia sẻ trạng thái không an toàn, tăng worker chỉ làm lỗi xuất hiện nhanh và khó đoán hơn. Hãy mô hình hóa đúng quan hệ trước, sau đó tăng concurrency và đo hiệu quả.




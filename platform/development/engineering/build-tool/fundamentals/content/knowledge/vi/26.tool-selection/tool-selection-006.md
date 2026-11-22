# Chi phí học, bảo trì, hiệu năng và khả năng hỗ trợ của nhóm

Chọn build tool cho một dự án Java là quyết định ảnh hưởng đến cách nhóm phát triển, kiểm thử và phát hành phần mềm trong nhiều năm. Một công cụ có thể rất mạnh nhưng yêu cầu nhiều kiến thức chuyên sâu, build script khó bảo trì hoặc chỉ một vài người trong nhóm hiểu cách vận hành. Một công cụ khác có thể đơn giản để bắt đầu nhưng không đáp ứng tốt khi repository tăng lên nhiều module hoặc pipeline cần chia sẻ kết quả build giữa các máy.

Vì vậy, không nên chọn build tool chỉ dựa trên một bài benchmark, số lượng tính năng hoặc sở thích của một lập trình viên. Cần đánh giá tổng chi phí sở hữu: thời gian học, công sức viết và bảo trì build logic, thời gian chờ build, độ ổn định của plugin, khả năng tích hợp IDE/CI, nguồn hỗ trợ khi gặp lỗi và mức độ phù hợp với kỹ năng hiện có của nhóm.

Với Java, Maven và Gradle là hai lựa chọn phổ biến; Ant vẫn có thể phù hợp với hệ thống cũ hoặc quy trình đặc thù. Các công cụ như Bazel có thể đáng cân nhắc khi cần build graph nghiêm ngặt, tính tái lập và quy mô lớn, nhưng thường đòi hỏi đầu tư đáng kể vào cấu hình và cách tổ chức repository. Công cụ phù hợp là công cụ giúp nhóm hoàn thành công việc với chi phí hợp lý trong suốt vòng đời dự án.

## 1. Bốn yếu tố cần cân nhắc cùng lúc

Khi đánh giá build tool, nên xem xét ít nhất bốn nhóm chi phí và năng lực:

| Yếu tố | Câu hỏi chính | Dấu hiệu cần quan sát |
|---|---|---|
| Chi phí học | Nhóm cần bao lâu để sử dụng đúng và tự xử lý lỗi thường gặp? | Tài liệu, khái niệm, thời gian onboarding, số người có thể hỗ trợ nhau |
| Bảo trì | Build logic có dễ đọc, nâng cấp, kiểm thử và thay đổi không? | Độ phức tạp script, plugin, convention, số workaround và phụ thuộc vào chuyên gia |
| Hiệu năng | Build có đáp ứng tốc độ phản hồi ở quy mô thực tế không? | Thời gian cold/warm build, incremental, parallel, cache, memory và CI throughput |
| Hỗ trợ nhóm | Khi gặp lỗi, nhóm có tài liệu, cộng đồng, plugin và người có kinh nghiệm để giải quyết không? | IDE/CI integration, plugin health, release cadence, community/commercial support |

Không yếu tố nào tự quyết định lựa chọn. Một công cụ có hiệu năng tốt hơn một chút có thể làm tổng chi phí tăng nếu build logic phức tạp và chỉ một người hiểu. Ngược lại, một công cụ dễ học nhưng thiếu tính năng cần thiết có thể buộc nhóm duy trì nhiều script bên ngoài, khiến chi phí tăng theo thời gian.

## 2. Đánh giá theo vòng đời, không chỉ thời điểm bắt đầu

Build tool thường được chọn ở giai đoạn repository còn nhỏ. Khi đó, một file cấu hình đơn giản có thể đủ dùng. Sau vài năm, dự án có thể có thêm module, plugin, test integration, code generation, native tool, CI matrix, dependency constraints, release automation và nhiều consumer.

Chi phí vì thế thay đổi theo vòng đời:

~~~mermaid
flowchart TD
    A["Bắt đầu dự án"] --> B["Onboarding và thiết lập build"]
    B --> C["Phát triển hàng ngày"]
    C --> D["Repository và dependency mở rộng"]
    D --> E["Nâng cấp toolchain và plugin"]
    E --> F["CI, release và vận hành lâu dài"]
    F --> G["Đánh giá lại tổng chi phí"]
    G --> C
~~~

Một lựa chọn có chi phí khởi đầu thấp chưa chắc có chi phí dài hạn thấp. Ví dụ, build script thủ công có thể nhanh chóng hoàn thành vài task đầu tiên, nhưng khi nhiều module cần dùng chung logic, nhóm phải tự xây dựng quy ước, xử lý thứ tự task và quản lý dependency. Chi phí ban đầu tiết kiệm được có thể chuyển thành chi phí bảo trì.

Ngược lại, chọn một hệ thống build phân tán phức tạp ngay từ đầu cho một ứng dụng nhỏ cũng có thể tạo gánh nặng không cần thiết. Nên chọn mức công cụ tương xứng với quy mô và yêu cầu có thể dự đoán hợp lý.

## 3. Chi phí học và onboarding

Chi phí học không chỉ là thời gian đọc tài liệu. Nó bao gồm thời gian để lập trình viên hiểu cấu trúc project, chạy task thường dùng, đọc log, sửa dependency, thêm module, xử lý plugin và tự điều tra lỗi build.

### 3.1. Đường cong học tập

Một công cụ có thể dễ bắt đầu nhưng khó làm chủ. Khi đánh giá, hãy phân biệt:

- **Time to first build:** thời gian để một người mới chạy được build đầu tiên.
- **Time to contribute:** thời gian để người đó tự thêm dependency, test hoặc module theo convention của nhóm.
- **Time to troubleshoot:** thời gian để người đó tìm nguyên nhân lỗi build thường gặp.
- **Time to maintain:** thời gian để người đó thay đổi build logic, nâng plugin hoặc cập nhật toolchain an toàn.

Nếu chỉ đo thời gian chạy lệnh đầu tiên, nhóm có thể đánh giá thấp chi phí học thực tế.

### 3.2. Maven và mô hình convention

Maven dùng project object model (POM) và lifecycle phase. Cấu trúc thư mục, cách khai báo dependency và nhiều bước build tuân theo convention phổ biến. Điều này giúp người đã biết Maven có thể đọc một dự án mới mà không cần học một DSL riêng cho từng repository.

Ưu điểm về onboarding:

- POM XML có cấu trúc tương đối quen thuộc.
- Lifecycle phase như compile, test, package, verify, install và deploy có ý nghĩa rõ.
- Parent POM và dependencyManagement giúp chia sẻ quy ước.
- Nhiều thư viện và tài liệu Java mô tả cấu hình Maven.

Chi phí học vẫn tăng khi dự án dùng nhiều profile, inheritance, plugin execution, property interpolation hoặc effective POM phức tạp. Người mới cần hiểu cả POM gốc, parent POM, profile được kích hoạt và plugin binding để giải thích vì sao một goal chạy.

### 3.3. Gradle và DSL

Gradle dùng build script Groovy hoặc Kotlin DSL, task graph và plugin model. Gradle có thể mô tả build rất linh hoạt và hỗ trợ convention plugin để tổ chức logic dùng chung.

Người mới cần hiểu:

- Project, task và task graph.
- Configuration phase và execution phase.
- Plugin, extension và convention.
- Dependency configuration như implementation, api, runtimeOnly và testImplementation.
- Provider/lazy configuration và cách khai báo input/output.
- Toolchain, build cache và configuration cache khi cần tối ưu.

Kotlin DSL có lợi thế về type checking và IDE assistance trong nhiều trường hợp, nhưng người chưa quen Kotlin có thể cần thêm thời gian. Groovy DSL linh hoạt nhưng đôi khi khó dò lỗi kiểu dữ liệu hoặc method resolution hơn.

### 3.4. Ant và build script thủ công

Ant sử dụng XML target/task và thường yêu cầu nhóm tự định nghĩa nhiều bước cũng như quan hệ phụ thuộc. Nó có thể dễ hiểu nếu quy trình chỉ gồm vài target cụ thể, nhưng một build lớn có thể cần nhiều convention và logic mà Maven/Gradle cung cấp sẵn.

Với hệ thống Ant cũ, chi phí học có thể thấp nếu nhóm đã quen. Khi đưa người mới vào hoặc mở rộng build, cần đánh giá mức độ phụ thuộc vào target tự viết, macro, property và script ngoài.

### 3.5. Đo onboarding bằng một bài tập thật

Thay vì hỏi lập trình viên thấy công cụ nào dễ hơn, hãy giao một bài tập giống công việc hằng ngày:

1. Checkout repository mới và chạy build.
2. Thêm một dependency test.
3. Thêm một unit test và chạy riêng test đó.
4. Thêm module nhỏ theo convention.
5. Đọc và giải thích một lỗi dependency hoặc plugin.
6. Thay đổi một compiler option và xác nhận task bị ảnh hưởng.

Ghi lại thời gian, số lần cần trợ giúp và những phần gây nhầm lẫn. Thực hiện với một vài thành viên có mức kinh nghiệm khác nhau để tránh kết quả chỉ phản ánh kiến thức của người thử nghiệm.

## 4. Chi phí bảo trì build logic

Build script là mã nguồn vận hành dự án. Nó cần được review, kiểm thử, nâng cấp và hiểu bởi nhiều người. Khi build logic trở nên khó bảo trì, mỗi thay đổi nhỏ có thể cần một chuyên gia, và rủi ro build hỏng tăng lên.

### 4.1. Những nguồn tạo ra chi phí bảo trì

- Số lượng plugin và mức độ phụ thuộc giữa chúng.
- Custom task hoặc script tự viết.
- Cấu hình bị lặp giữa nhiều module.
- Profile/flag theo môi trường.
- Build logic nằm rải rác ở nhiều repository.
- Workaround cho phiên bản JDK, IDE hoặc CI.
- Plugin không còn được duy trì.
- Nâng cấp Gradle/Maven kéo theo nhiều thay đổi.
- Thiếu test cho convention plugin và task custom.

Số dòng build script không phải chỉ số đủ tốt. Một script ngắn nhưng phụ thuộc vào convention ngầm hoặc plugin không ổn định vẫn có thể khó bảo trì. Ngược lại, một convention plugin có cấu trúc rõ có thể có nhiều dòng nhưng giảm lặp và giúp các module nhất quán.

### 4.2. Convention giúp giảm chi phí lặp

Trong Maven, parent POM và pluginManagement có thể tập trung version plugin, compiler configuration và quy tắc chung. Trong Gradle, convention plugin có thể đóng gói cấu hình Java, test, lint hoặc publication dùng chung.

Ví dụ convention plugin Gradle:

~~~kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
~~~

Đây là phần minh họa một convention dùng chung. Thay vì sao chép cấu hình vào mọi module, nhóm áp dụng plugin nội bộ. Khi thay đổi Java release hoặc encoding, nhóm có một nơi để quản lý.

Tuy nhiên, abstraction quá sớm cũng có chi phí. Nếu convention plugin che giấu quá nhiều behavior, người mới phải tìm qua nhiều tầng để biết một task được cấu hình thế nào. Nên trừu tượng hóa những quy tắc thực sự lặp lại và đặt tên theo mục đích dễ hiểu.

### 4.3. Giữ build logic dễ đọc

Một số nguyên tắc giúp giảm chi phí:

- Dùng tên task, property và plugin thể hiện mục đích.
- Tách logic dùng chung khỏi logic riêng của một module.
- Tránh cấu hình cùng một thuộc tính ở nhiều nơi.
- Hạn chế script phụ thuộc vào thứ tự khai báo không rõ ràng.
- Ghi rõ lý do của workaround và điều kiện có thể xóa nó.
- Pin plugin/tool version và review nâng cấp có chủ đích.
- Không để secret hoặc machine-specific path trong build file.
- Giữ task input/output khai báo đầy đủ.

### 4.4. Kiểm thử build logic

Build logic cũng có thể có bug. Với Gradle, TestKit cho phép kiểm thử plugin/task trong một Gradle build mẫu. Với Maven plugin, có thể dùng plugin testing harness hoặc integration test theo cách triển khai plugin.

Các test hữu ích:

- Plugin áp dụng đúng extension và task.
- Task nhận đúng input và tạo đúng output.
- Thay input làm task chạy lại.
- Cấu hình cache không trả output lỗi thời.
- Task hoạt động trên môi trường/đường dẫn workspace khác nhau.
- Nâng version toolchain không làm thay đổi behavior ngoài dự kiến.

Không cần viết test cho mọi dòng cấu hình đơn giản. Nên ưu tiên custom task, convention plugin và logic điều kiện có ảnh hưởng đến nhiều module.

## 5. Chi phí nâng cấp và tương thích plugin

Build tool không đứng một mình. Nó làm việc với JDK, compiler, test framework, code generator, formatter, static analyzer, repository manager, IDE và CI action. Nâng cấp một thành phần có thể ảnh hưởng thành phần khác.

### 5.1. Plugin ecosystem

Khi đánh giá plugin, hãy xem:

- Plugin có hỗ trợ phiên bản build tool dự kiến không?
- Có hỗ trợ JDK hiện tại và Java release mục tiêu không?
- Release gần đây có đều đặn không?
- Issue quan trọng có được xử lý không?
- Tài liệu và migration guide có rõ không?
- Plugin có được dùng rộng rãi hoặc có đơn vị duy trì đáng tin cậy không?
- Plugin có thể thay thế bằng chức năng built-in không?

Số lượng plugin lớn không đồng nghĩa với hệ sinh thái tốt. Điều quan trọng là các plugin nhóm thật sự cần có chất lượng, tương thích và người duy trì.

### 5.2. Dependency của build logic

Plugin và extension là dependency của chính quá trình build. Nếu plugin bị bỏ duy trì hoặc phụ thuộc vào API nội bộ của build tool, nhóm có thể phải fork hoặc thay thế. Hãy ghi nhận owner và phương án thay thế cho plugin quan trọng.

### 5.3. Kế hoạch nâng cấp

Nên có chu kỳ nâng cấp định kỳ:

1. Theo dõi release và security advisory của build tool/JDK/plugin.
2. Chọn một phiên bản đích đã được hỗ trợ.
3. Đọc release notes và migration guide.
4. Chạy build trên branch nâng cấp.
5. Kiểm tra warning/deprecation và plugin compatibility.
6. Chạy test/CI matrix và so sánh artifact khi cần.
7. Merge thay đổi nâng cấp thành một thay đổi có thể review.

Nếu để quá lâu mới nâng cấp, nhóm có thể phải xử lý nhiều breaking changes cùng lúc. Nâng cấp nhỏ, đều đặn thường dễ điều tra hơn một lần nhảy qua nhiều major version.

## 6. Hiệu năng build cần được đo như thế nào?

Hiệu năng không chỉ là thời gian của lệnh build tổng thể. Cần biết thời gian nằm ở đâu và ai đang phải chờ.

Các thành phần thời gian thường gặp:

- Startup và khởi tạo build tool.
- Configuration phase.
- Dependency resolution và tải artifact.
- Compile và code generation.
- Unit/integration test.
- Static analysis.
- Packaging và upload artifact.
- Queue time hoặc thời gian chờ runner trong CI.

Một công cụ có thể compile nhanh nhưng configuration chậm ở monorepo lớn. Một công cụ khác có thể chạy tốt trên local nhưng CI runner mới phải tải dependency nhiều. Đo tổng thời gian và phân rã theo giai đoạn giúp xác định nút thắt.

### 6.1. Cold build và warm build

Cold build là lần chạy khi chưa có output/cache phù hợp. Warm build là lần chạy có thể tái sử dụng output hoặc cache. Cần đo cả hai:

| Loại đo | Mục tiêu |
|---|---|
| Cold build từ workspace sạch | Đánh giá chi phí build đầy đủ và khả năng setup |
| Warm build không đổi source | Đánh giá up-to-date checking và cache |
| Incremental build sau một thay đổi nhỏ | Đánh giá phản hồi khi lập trình viên sửa code |
| Build sau thay đổi dependency | Đánh giá resolve và phạm vi rebuild |
| CI build trên runner mới | Đánh giá môi trường pipeline thực tế |
| Full verification/release build | Đánh giá thời gian từ commit đến kết quả đủ điều kiện |

Không nên so sánh warm build của công cụ A với cold build của công cụ B. Hãy giữ điều kiện tương đương.

### 6.2. Đo median và phân phối, không chỉ một lần chạy

Thời gian build thay đổi do tải CPU, disk, network, cache và runner. Một lần chạy đơn lẻ có thể gây hiểu nhầm. Nên chạy nhiều lần trong điều kiện tương tự, ghi median và độ phân tán hoặc percentile phù hợp.

Ghi nhận thêm CPU và memory peak, disk I/O và network download, số task được thực thi/up-to-date/FROM-CACHE, số worker và mức parallelism, dependency cache state, runner image và JDK version.

### 6.3. Đo trên workload đại diện

Benchmark nên dùng repository, module graph, dependency, test và code generation gần với công việc thật. Một project mẫu chỉ có vài class Java không phản ánh được hiệu năng của monorepo lớn, nhiều plugin hoặc test suite dài.

## 7. Các cơ chế hiệu năng của Gradle

Gradle có một số cơ chế có thể cải thiện tốc độ build, nhưng lợi ích phụ thuộc cách build được cấu hình.

### 7.1. Incremental build và up-to-date checking

Gradle có thể bỏ qua task nếu input/output không thay đổi hoặc chỉ xử lý phần input bị ảnh hưởng nếu task hỗ trợ incremental execution. Để cơ chế hoạt động đúng, task cần khai báo input/output chính xác.

Task custom đọc file hoặc environment mà không khai báo có thể bị đánh giá up-to-date sai. Tối ưu hiệu năng không được đánh đổi tính đúng đắn.

### 7.2. Build cache

Build cache lưu output của task cacheable theo cache key. Local cache giúp một máy tái sử dụng kết quả; remote cache có thể chia sẻ kết quả giữa nhiều máy và CI job.

Build cache có giá trị cao với compile, code generation và analysis có input xác định. Task có side effect hoặc phụ thuộc thời gian/network không khai báo thường không phù hợp.

### 7.3. Configuration cache

Configuration cache lưu kết quả cấu hình build để giảm thời gian configuration phase ở lần chạy sau. Nó khác build cache task output. Một build có thể bật configuration cache nhưng vẫn phải thực thi task; ngược lại, task có thể được lấy từ build cache mà configuration phase vẫn chạy.

### 7.4. Parallel execution

Gradle có thể chạy các task độc lập song song. Lợi ích phụ thuộc task graph, tài nguyên máy và việc task có khai báo dependency đúng hay không. Nếu task custom ghi cùng file hoặc chia sẻ trạng thái không an toàn, parallel execution có thể làm lộ race condition.

### 7.5. Daemon và worker

Gradle daemon giữ JVM chạy nền để giảm chi phí khởi động giữa các lần build. Worker API có thể giúp task chia nhỏ công việc. Các cơ chế này có thể tăng throughput nhưng cũng sử dụng memory và CPU; cấu hình cần phù hợp với runner và máy lập trình viên.

## 8. Hiệu năng và đặc tính của Maven

Maven có lifecycle và dependency model tương đối dễ dự đoán. Hiệu năng thực tế phụ thuộc plugin, module structure, dependency download, test execution và khả năng chạy song song.

### 8.1. Parallel builds

Maven hỗ trợ parallel reactor build bằng tùy chọn thread, ví dụ:

    ./mvnw -T 1C clean verify

Tùy chọn này yêu cầu Maven dùng số thread theo số core theo quy tắc của Maven. Nó có thể giúp build nhiều module độc lập nhanh hơn, nhưng plugin hoặc module có shared state không an toàn có thể gây lỗi khi chạy song song.

### 8.2. Incremental behavior và plugin

Maven plugin có cách quản lý input/output và incremental behavior riêng. Một số plugin kiểm tra file timestamp để bỏ qua công việc; plugin khác luôn thực thi goal. Không nên giả định mọi goal có incremental behavior giống Gradle task.

### 8.3. Dependency cache

Local Maven repository giúp tránh tải lại dependency. CI có thể lưu thư mục repository giữa các job, nhưng cần kiểm soát snapshot/update policy và concurrency. Dependency cache không đồng nghĩa với task-output build cache.

### 8.4. Build cache bổ sung

Maven core lifecycle truyền thống không có cùng mô hình task-output build cache tích hợp như Gradle. Có thể sử dụng extension hoặc dịch vụ ngoài, nhưng cần tính thêm chi phí cài đặt, hỗ trợ, tương thích plugin và vận hành backend.

## 9. Hiệu năng không chỉ là build nhanh

Một công cụ nhanh hơn vài giây có thể không đáng đổi nếu tạo ra nhiều giờ bảo trì hoặc làm CI khó ổn định. Nên xem hiệu năng trong bối cảnh năng suất tổng thể.

Ví dụ:

- Nếu lập trình viên chạy build nhỏ hàng chục lần mỗi ngày, incremental build có ảnh hưởng lớn đến trải nghiệm.
- Nếu CI chạy hàng trăm job mỗi ngày, remote cache và runner utilization có thể ảnh hưởng chi phí hạ tầng.
- Nếu release build chỉ chạy mỗi tuần, độ tin cậy và khả năng tái lập có thể quan trọng hơn vài phút tiết kiệm.
- Nếu test suite chiếm phần lớn thời gian, đổi build tool có thể không cải thiện đáng kể nếu test không được phân vùng hoặc tối ưu.

Trước khi thay công cụ, hãy xác định bottleneck. Có thể vấn đề nằm ở test chậm, dependency repository, network, plugin, cấu hình task hoặc thiếu cache chứ không phải build tool cốt lõi.

## 10. Khả năng hỗ trợ của nhóm

Build tool cần được hỗ trợ trong thực tế: người có thể review cấu hình, xử lý incident, nâng cấp plugin và giúp đồng nghiệp khi pipeline fail.

### 10.1. Phân bố kiến thức

Hãy hỏi:

- Có bao nhiêu người hiểu build logic?
- Có ít nhất hai người có thể xử lý lỗi build quan trọng không?
- Người mới có thể tự tìm tài liệu và làm task thường gặp không?
- Build script có phụ thuộc vào một cá nhân viết DSL/plugin custom không?
- Nhóm platform/build engineering có thể hỗ trợ không?

Nếu chỉ một người hiểu build, người đó trở thành điểm nghẽn. Khi người này nghỉ phép hoặc rời nhóm, mọi nâng cấp và sự cố đều chậm lại.

### 10.2. Pairing và ownership

Với build logic quan trọng, nên có code owner hoặc nhóm chịu trách nhiệm. Tuy nhiên, ownership không nên đồng nghĩa chỉ một người được phép sửa. Có thể dùng review bắt buộc từ một người có chuyên môn, kết hợp tài liệu và pairing để lan tỏa kiến thức.

### 10.3. Tài liệu nội bộ

Tài liệu nên trả lời cách setup JDK và build tool, lệnh build/test thường dùng, cách chạy task cho một module, cách thêm dependency hoặc plugin, cách debug dependency resolution, cách cập nhật toolchain, cách xử lý CI failure phổ biến và ai sở hữu build logic.

Tài liệu nội bộ có thể giảm đáng kể chi phí onboarding, nhất là khi repository có convention riêng.

## 11. Hệ sinh thái, tài liệu và hỗ trợ bên ngoài

Khả năng hỗ trợ không chỉ là có câu trả lời trên diễn đàn. Cần đánh giá chất lượng và độ tin cậy của nguồn hỗ trợ.

### 11.1. Tài liệu chính thức

Kiểm tra tài liệu có hướng dẫn bắt đầu và reference đầy đủ, ví dụ đúng với phiên bản đang dùng, migration guide giữa các version, giải thích rõ API/plugin và giới hạn, hướng dẫn troubleshooting, lịch phát hành và thông tin support policy.

Tài liệu cũ hoặc ví dụ không khớp phiên bản có thể làm tăng chi phí học và debug.

### 11.2. Cộng đồng và hệ sinh thái

Một hệ sinh thái lớn có thể giúp tìm plugin, ví dụ và kinh nghiệm thực tế. Nhưng cần xem chất lượng câu trả lời, mức hoạt động của maintainer và khả năng tái hiện issue. Số lượng kết quả tìm kiếm không đảm bảo câu trả lời đúng.

### 11.3. Hỗ trợ thương mại

Với tổ chức có yêu cầu thời gian khôi phục, tuân thủ hoặc build infrastructure quan trọng, hỗ trợ thương mại có thể đáng giá. Hãy đánh giá SLA và thời gian phản hồi, hỗ trợ phiên bản đang dùng, quy trình escalation khi build blocker, khả năng hỗ trợ migration/performance tuning, chi phí license/seat/usage và điều khoản dữ liệu/bảo mật.

Không phải dự án nào cũng cần hợp đồng hỗ trợ thương mại. Với nhóm nhỏ, tài liệu chính thức và cộng đồng có thể đủ; với nền tảng build của tổ chức lớn, chi phí hỗ trợ có thể thấp hơn chi phí gián đoạn.

## 12. Tích hợp IDE, CI và công cụ phát triển

Build tool không chỉ được gọi từ terminal. Nó cần hoạt động với IDE, code review, CI, artifact repository và các công cụ phân tích.

### 12.1. IDE

Kiểm tra IDE có import/sync project ổn định không, có nhận diện source set/test source/generated source không, có chạy test/debug theo đúng build configuration không, có hỗ trợ Wrapper version dự án dùng không và thông báo sync failure có đủ rõ không.

Nếu developer thường xuyên phải duy trì cấu hình IDE riêng ngoài build script, nhóm có thể gặp khác biệt giữa local và CI.

### 12.2. CI

Kiểm tra runner có thể cài và chạy Wrapper không, cache có phù hợp không, log/report có được thu thập không, và pipeline có thể chạy đúng project/module path không. Build tool cần hỗ trợ cách CI phân phối công việc và lưu artifact của tổ chức.

### 12.3. Artifact repository

Xem mức độ hỗ trợ publish/resolve, metadata, snapshot/release, credentials, signing, staging và dependency verification. Với hệ thống nhiều module, BOM/platform và variant metadata có thể quan trọng.

### 12.4. Developer tooling

Formatter, linter, test runner, code generator, static analyzer, license/security scanner và release automation đều có thể cần plugin. Hãy lập danh sách công cụ thực sự cần và xác minh plugin tương thích trước khi chọn build tool.

## 13. Đánh giá các lựa chọn thường gặp trong Java

Không có bảng nào thay thế được thử nghiệm trên repository thật, nhưng có thể dùng đặc tính chung để xác định công cụ cần đưa vào vòng đánh giá.

| Công cụ | Điểm mạnh thường gặp | Chi phí/rủi ro cần cân nhắc |
|---|---|---|
| Maven | Convention rõ, lifecycle quen thuộc, POM dễ chia sẻ giữa nhóm Java | POM/profile/plugin có thể phức tạp; custom workflow đôi khi cần plugin hoặc extension |
| Gradle | DSL linh hoạt, task graph, incremental build, build cache và convention plugin mạnh | Cần học model/configuration phase; build logic tùy biến dễ phình nếu thiếu quy ước |
| Ant | Kiểm soát target/task trực tiếp; hữu ích cho hệ thống cũ hoặc quy trình đặc thù | Nhiều convention phải tự xây; build lớn có thể khó tổ chức và tái sử dụng |
| Bazel | Build graph rõ, khả năng hermetic/remote execution và scale cho monorepo lớn | Đầu tư thiết lập cao; rule ecosystem, toolchain và migration cần chuyên môn |

### 13.1. Khi Maven thường là lựa chọn hợp lý

Maven thường phù hợp khi dự án chủ yếu là Java/JVM với cấu trúc module quen thuộc, nhóm ưu tiên convention và cấu hình có thể đọc theo POM, build lifecycle không cần nhiều logic tùy biến, nhiều thành viên đã có kinh nghiệm Maven và plugin cần thiết có hỗ trợ tốt.

Maven vẫn có thể hỗ trợ dự án lớn. Parent POM, BOM, reactor build và plugin configuration có thể đáp ứng nhiều nhu cầu. Cần chú ý profile/inheritance không trở thành một mạng cấu hình khó hiểu.

### 13.2. Khi Gradle thường là lựa chọn hợp lý

Gradle thường phù hợp khi repository có nhiều module và cần convention plugin, build có nhiều task custom hoặc code generation, incremental execution/build cache đem lại lợi ích rõ, cần cấu hình linh hoạt cho nhiều loại source/platform và nhóm có hoặc sẵn sàng xây dựng năng lực Gradle.

Lợi ích chỉ xuất hiện khi nhóm có kỷ luật tổ chức build logic và đủ người hiểu Gradle để bảo trì. Ưu tiên plugin/convention rõ ràng và lazy configuration thay vì script imperative dài.

### 13.3. Khi Ant vẫn có thể phù hợp

Ant có thể phù hợp khi duy trì một hệ thống legacy đã ổn định, khi quy trình gồm nhiều bước đặc thù hoặc khi migration sang Maven/Gradle có chi phí/rủi ro lớn hơn lợi ích dự kiến.

Nếu bắt đầu dự án mới, cần cân nhắc liệu việc tự quản lý dependency, lifecycle, test integration và convention có đem lại lợi ích đủ lớn để bù chi phí hay không.

### 13.4. Khi nên đánh giá Bazel hoặc hệ thống build khác

Với monorepo rất lớn, nhiều ngôn ngữ, remote execution, hermetic build hoặc yêu cầu tái lập nghiêm ngặt, Bazel hoặc một hệ thống build chuyên biệt có thể đáng đánh giá. Tuy nhiên, lợi ích thường đi cùng đầu tư về rule, toolchain, dependency modeling, developer workflow và migration.

Đừng chọn công cụ này chỉ vì một công ty lớn sử dụng nó. Hãy xác định vấn đề cụ thể mà build hiện tại không giải quyết được và chứng minh công cụ mới giải quyết vấn đề đó trong repository của nhóm.

## 14. Tổng chi phí sở hữu (TCO)

Total Cost of Ownership (TCO) bao gồm chi phí trực tiếp và gián tiếp trong một khoảng thời gian xác định.

~~~text
TCO = Chi phí onboarding
    + Chi phí viết và bảo trì build logic
    + Chi phí chờ build và CI
    + Chi phí nâng cấp/tool compatibility
    + Chi phí hạ tầng và license
    + Chi phí sự cố và gián đoạn
    + Chi phí migration/lock-in
~~~

### 14.1. Chi phí con người

Ước lượng số giờ cho học và onboarding thành viên mới, viết convention/plugin/task, sửa lỗi build thường gặp, nâng cấp build tool/plugin, hỗ trợ đồng nghiệp và xử lý CI incident.

Chi phí con người thường lớn hơn license của build tool. Một cải thiện nhỏ về thời gian build có thể rất có giá trị khi được nhân lên theo số developer và số lần build mỗi ngày.

### 14.2. Chi phí hạ tầng

Ghi nhận runner minutes, CPU/memory, storage cache, network transfer, artifact repository và dịch vụ build cache. Công cụ có thể giảm thời gian job nhưng tăng storage/network hoặc yêu cầu backend riêng.

### 14.3. Chi phí sự cố

Build không ổn định có thể chặn merge, trì hoãn release và chiếm thời gian của nhiều người. Nên xem số lần pipeline fail do infrastructure/build logic, thời gian khôi phục và số người bị ảnh hưởng.

### 14.4. Chi phí chuyển đổi

Migration từ Maven sang Gradle hoặc ngược lại có thể cần chuyển POM/build script, plugin, CI, IDE setup, publication metadata, dependency constraints và tài liệu. Cần tính cả giai đoạn hai hệ thống cùng tồn tại và chi phí hỗ trợ sau migration.

## 15. Ma trận chấm điểm có trọng số

Để so sánh các ứng viên, nhóm có thể dùng ma trận trọng số. Trọng số phải phản ánh mục tiêu dự án; không có bộ trọng số đúng cho mọi tổ chức.

Ví dụ một nhóm Java có nhiều module và CI thường xuyên:

| Tiêu chí | Trọng số ví dụ | Cách đo |
|---|---:|---|
| Chi phí học/onboarding | 20% | Thời gian hoàn thành bài tập onboarding, số lần cần trợ giúp |
| Bảo trì build logic | 25% | Độ rõ ràng, số custom plugin/script, công sức thay đổi |
| Hiệu năng local và CI | 25% | Median cold/warm/incremental build, runner minutes |
| Hỗ trợ và hệ sinh thái | 20% | Plugin cần thiết, tài liệu, IDE/CI, maintainer/support |
| Migration và rủi ro | 10% | Số thành phần phải đổi, compatibility và khả năng rollback |

Chấm từng tiêu chí theo thang 1 đến 5:

- 1: không đáp ứng hoặc rủi ro lớn.
- 2: đáp ứng một phần, cần nhiều workaround.
- 3: đáp ứng nhu cầu cơ bản.
- 4: đáp ứng tốt, chi phí hợp lý.
- 5: rất phù hợp và có bằng chứng thực tế.

Công thức điểm tổng:

\[
\text{Điểm tổng} = \sum_i \left(\text{Trọng số}_i \times \text{Điểm}_i\right)
\]

Nếu trọng số biểu diễn dưới dạng phần trăm, có thể chia tổng cho 100 để giữ thang điểm 1–5. Bên cạnh điểm tổng, ghi rõ giả định, bằng chứng và rủi ro không thể quy đổi thành điểm.

### 15.1. Không để điểm số tạo cảm giác chính xác giả

Một ứng viên có điểm 4,1 và ứng viên khác 4,0 chưa chắc khác biệt có ý nghĩa. Nếu hai công cụ gần nhau, hãy xem tiêu chí nào tạo ra chênh lệch và có liên quan đến mục tiêu quan trọng nhất hay không.

Một tiêu chí bắt buộc như hỗ trợ JDK, policy bảo mật hoặc khả năng publish có thể là điều kiện loại, không nên cho phép điểm hiệu năng cao bù lại việc không đáp ứng.

## 16. Thực hiện proof of concept công bằng

Proof of concept (PoC) giúp xác nhận giả định bằng workload thật trước khi cam kết lâu dài.

### 16.1. Chọn phạm vi đại diện

Chọn một phần repository có nhiều module và dependency nội bộ, compile/unit/integration test, một plugin hoặc generator quan trọng, publication JAR/POM hoặc BOM, CI pipeline và cache, cùng một số tác vụ thường xuyên mà developer thực hiện.

Không chỉ chọn module nhỏ nhất hoặc module thuận lợi nhất cho công cụ mới.

### 16.2. Giữ điều kiện tương đương

Để so sánh công bằng:

- Dùng cùng source revision.
- Dùng cùng JDK vendor/version và Java release.
- Dùng cùng dependency versions.
- Dùng cùng test set và quality gates.
- Dùng runner có cấu hình tương đương.
- Phân biệt cold cache và warm cache.
- Ghi nhận cấu hình parallelism.
- Chạy đủ số lần để giảm ảnh hưởng của nhiễu.

Nếu một công cụ được phép bỏ qua test hoặc dùng dependency khác, kết quả benchmark không còn so sánh cùng một công việc.

### 16.3. Đo công việc bảo trì, không chỉ benchmark

Trong PoC, hãy giao một số thay đổi:

1. Thêm module Java mới.
2. Thêm dependency và quản lý version.
3. Thêm test framework hoặc static analysis plugin.
4. Tạo một task code generation.
5. Chia sẻ cấu hình giữa nhiều module.
6. Publish artifact vào staging repository.
7. Nâng JDK hoặc plugin.
8. Điều tra một build failure có chủ đích.

Ghi thời gian, số file phải sửa, mức độ dễ review và số lần cần chuyên gia hỗ trợ. Đây là bằng chứng trực tiếp về chi phí học và bảo trì.

### 16.4. Đặt tiêu chí thành công trước khi thử

Ví dụ:

- Người mới có thể chạy build và test trong một buổi onboarding.
- Thay đổi source nhỏ tạo incremental feedback dưới ngưỡng thời gian nhóm chấp nhận.
- Full CI build đáp ứng mục tiêu thời gian.
- Tất cả required checks có thể được tích hợp.
- Publication metadata và dependency resolution tương đương.
- Có ít nhất hai thành viên có thể sửa build logic.
- Plugin quan trọng được hỗ trợ bởi phiên bản tool dự kiến.

Ngưỡng cần được chọn theo dự án. Không nên đặt tiêu chí sau khi đã biết công cụ nào thắng vì điều đó dễ tạo thiên lệch.

## 17. Ví dụ ra quyết định theo bối cảnh nhóm

### 17.1. Nhóm nhỏ, ứng dụng Java đơn giản

Nhóm có một ứng dụng, vài module, ít custom task và phần lớn thành viên đã biết Maven. Maven có thể là lựa chọn hợp lý vì convention rõ, onboarding thấp và nhu cầu build chưa cần nhiều logic đặc thù.

Nếu Gradle không giải quyết vấn đề cụ thể nào, chuyển đổi chỉ vì một benchmark ngắn có thể không đáng chi phí.

### 17.2. Nhiều module và build logic dùng chung

Nhóm có nhiều module, nhiều task code generation, convention lặp lại và cần cache output giữa CI job. Gradle có thể đem lại lợi ích từ task graph, convention plugin, incremental execution và remote build cache.

Lợi ích chỉ xuất hiện khi nhóm có kỷ luật tổ chức build logic và đủ người hiểu Gradle để bảo trì.

### 17.3. Hệ thống legacy Ant

Một hệ thống Ant đã ổn định, ít thay đổi và có nhiều script đặc thù. Migration có thể làm thay đổi output hoặc quy trình phát hành. Nhóm nên cân nhắc tiếp tục duy trì, cải thiện từng phần hoặc chuyển đổi theo module dựa trên lợi ích đo được, thay vì coi công cụ cũ tự động là sai.

### 17.4. Monorepo rất lớn, nhiều ngôn ngữ

Nhóm cần build graph chính xác, remote execution và tính tái lập mạnh. Bazel có thể đáng thử, nhưng PoC phải tính chi phí chuyển dependency model, toolchain, IDE workflow, rule maintenance và đào tạo. Nếu phần lớn repository vẫn là Java/Maven với thời gian build chấp nhận được, migration toàn bộ có thể chưa hợp lý.

## 18. Khi nào nên giữ công cụ hiện tại?

Không phải mọi vấn đề build đều cần đổi build tool. Trước khi migration, hãy kiểm tra:

- Build có đang chậm vì test hoặc network chứ không phải build engine?
- Dependency cache/remote build cache đã được cấu hình đúng chưa?
- Có thể chia nhỏ test hoặc chạy task độc lập song song không?
- Plugin cũ có thể được thay bằng plugin được duy trì tốt hơn không?
- Build logic có thể được gom thành convention mà không đổi tool không?
- Runner CI có thiếu CPU, memory hoặc disk không?
- Có thể nâng build tool hiện tại theo từng bước không?

Nếu nguyên nhân nằm ở một plugin, repository hoặc test suite, đổi công cụ có thể không giải quyết được. Nên sửa nút thắt gốc và đo lại trước khi quyết định migration.

## 19. Lập kế hoạch migration nếu cần đổi công cụ

Migration build tool là thay đổi kỹ thuật có rủi ro vì nó tác động đến cách build, test, package và publish.

Một lộ trình có thể gồm:

1. Lập danh sách task, plugin, profile, dependency và publication hiện tại.
2. Xác định hành vi cần giữ: output, test set, artifact coordinates và metadata.
3. Chọn một module đại diện để thử nghiệm.
4. Thiết lập toolchain và build logic mới.
5. So sánh dependency graph và artifact output.
6. Chạy CI song song trên cùng source revision.
7. Đào tạo ít nhất hai người có thể bảo trì cấu hình mới.
8. Chuyển module theo từng nhóm và có kế hoạch rollback.
9. Cập nhật IDE setup, tài liệu, cache và release pipeline.
10. Loại bỏ build cũ sau khi xác nhận mọi consumer đã chuyển.

### 19.1. Giữ kết quả có thể so sánh

Trong giai đoạn chạy song song, hãy so sánh class files và Java release, resource filtering và generated source, test results và quality reports, dependency graph và transitive dependencies, POM/Gradle metadata và publication coordinates, checksum artifact khi kỳ vọng byte-for-byte giống nhau.

Không phải mọi archive đều phải giống byte-for-byte nếu build cũ có timestamp không ổn định. Khi đó, cần phân biệt khác biệt metadata đóng gói với khác biệt bytecode/resource thực sự.

### 19.2. Tránh duy trì hai hệ thống quá lâu

Chạy song song giúp giảm rủi ro nhưng cũng tạo chi phí kép: hai bộ build script, hai tập plugin, hai cách debug và hai pipeline. Đặt thời hạn và điều kiện hoàn tất migration. Nếu PoC cho thấy lợi ích không đủ, ghi lại kết quả và dừng chuyển đổi có chủ đích.

## 20. Quản trị build tool trong nhóm

Sau khi chọn công cụ, cần có cách quản trị để build không phân mảnh theo từng module hoặc từng lập trình viên.

### 20.1. Xác định owner

Chỉ định người hoặc nhóm chịu trách nhiệm:

- Version Gradle/Maven Wrapper.
- JDK/toolchain baseline.
- Plugin và repository policy.
- Convention plugin/parent POM.
- CI templates và cache configuration.
- Release/publishing logic.

Owner chịu trách nhiệm định hướng và hỗ trợ, nhưng thay đổi vẫn nên được review bởi các thành viên liên quan.

### 20.2. Chuẩn hóa cách dùng

Tài liệu hóa lệnh chuẩn cho build, test, check, module-specific task và publish. Dùng Wrapper để local/CI gọi cùng phiên bản. Tránh để mỗi module tự chọn compiler release, formatter hoặc plugin version khác nhau nếu không có lý do.

### 20.3. Theo dõi sức khỏe build

Có thể theo dõi thời gian CI median và p95, tỷ lệ build fail do infrastructure/build logic, cache hit rate và runner utilization, thời gian onboarding, số plugin hết hỗ trợ hoặc có issue nghiêm trọng, số workaround và custom task chưa có owner, thời gian trung bình từ phát hiện đến khôi phục build.

Các chỉ số này giúp nhóm biết chi phí đang tăng ở đâu và khi nào cần cải thiện.

## 21. Những sai lầm khi lựa chọn build tool

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Chọn theo sở thích cá nhân | Khó tạo đồng thuận và thiếu bằng chứng | Dùng tiêu chí chung và PoC |
| Chọn theo benchmark project nhỏ | Không phản ánh repository thật | Dùng workload đại diện |
| Chỉ tính thời gian build | Bỏ qua onboarding và bảo trì | Đánh giá TCO |
| Chọn công cụ mạnh nhất dù không cần | Tăng complexity và vận hành | Bắt đầu từ yêu cầu thực tế |
| Giữ công cụ cũ chỉ vì đã quen | Có thể duy trì nút thắt tốn kém | Định kỳ đánh giá chi phí hiện tại |
| Đổi tool để chữa test chậm | Không giải quyết bottleneck | Phân tích thời gian theo task |
| Dùng quá nhiều plugin | Tăng rủi ro compatibility và nâng cấp | Ưu tiên tính năng built-in, plugin có owner |
| Một người sở hữu toàn bộ build | Tạo điểm nghẽn kiến thức | Chia sẻ ownership và pairing |
| Migration toàn bộ cùng lúc | Rủi ro và khó rollback | Chuyển theo module với tiêu chí rõ |
| Không đo lại sau lựa chọn | Không biết quyết định còn phù hợp | Theo dõi chỉ số build định kỳ |

## 22. Checklist lựa chọn công cụ cho nhóm

Trước khi quyết định, hãy trả lời:

1. Dự án có bao nhiêu module và dependency nội bộ?
2. Build có bao nhiêu task custom, generator và plugin đặc thù?
3. Nhóm đã có kinh nghiệm Maven, Gradle, Ant hoặc công cụ khác ở mức nào?
4. Người mới cần bao lâu để tự chạy và sửa build?
5. Ai sẽ chịu trách nhiệm nâng cấp và xử lý sự cố?
6. Build logic có thể được đọc và review bởi nhiều người không?
7. Plugin quan trọng có được duy trì và hỗ trợ toolchain mục tiêu không?
8. IDE, CI và artifact repository có tích hợp tốt không?
9. Cold, warm và incremental build trên workload thật ra sao?
10. CI runner minutes, cache storage và network cost thay đổi thế nào?
11. Có thể tái lập build và kiểm soát dependency/toolchain không?
12. Migration cần bao nhiêu công sức và có thể rollback không?
13. Có ít nhất hai người đủ khả năng hỗ trợ build logic không?
14. Lựa chọn có đáp ứng yêu cầu bảo mật, support và release không?

## 23. Kết luận thực hành

Chọn build tool là chọn một phần của quy trình làm việc mà cả nhóm sẽ sử dụng và bảo trì trong nhiều năm. Chi phí học quyết định tốc độ onboarding; chi phí bảo trì quyết định mức độ dễ thay đổi build logic; hiệu năng quyết định thời gian phản hồi local và CI; khả năng hỗ trợ quyết định nhóm có thể xử lý lỗi và nâng cấp bền vững hay không.

Hãy bắt đầu từ workload và năng lực hiện có, lập danh sách yêu cầu bắt buộc, rồi thử các ứng viên trên cùng source revision và điều kiện. Đo cold/warm/incremental build, thử những thay đổi bảo trì thực tế và hỏi nhiều thành viên tham gia. Tính cả con người, hạ tầng, plugin, sự cố và migration trong TCO. Maven thường có lợi thế convention và độ quen thuộc; Gradle có lợi thế linh hoạt, task model và các cơ chế tối ưu; Ant có thể hợp lý khi duy trì hệ thống đặc thù; Bazel đáng đánh giá khi quy mô và yêu cầu build graph justify khoản đầu tư. Quyết định tốt là quyết định có bằng chứng, phù hợp với công việc của nhóm và có thể được nhiều người cùng hỗ trợ trong suốt vòng đời dự án.

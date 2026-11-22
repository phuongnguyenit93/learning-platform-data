# Đọc kế hoạch thực thi và giải thích vì sao tác vụ được chọn

Khi chạy một lệnh Gradle như **./gradlew build**, Gradle không thực thi mọi task có trong dự án. Trước tiên, nó xác định những task cần thiết để đáp ứng yêu cầu, mở rộng các quan hệ phụ thuộc, áp dụng các ràng buộc thứ tự rồi tạo thành một **task graph** (đồ thị tác vụ). Sau đó Gradle thực thi các task trong đồ thị theo thứ tự hợp lệ.

Đọc được kế hoạch thực thi giúp trả lời ba câu hỏi quan trọng: task nào sẽ được chạy, task đó được đưa vào kế hoạch vì lý do gì, và vì sao một task xuất hiện trong log nhưng không thực hiện action. Đây là kỹ năng hữu ích khi build lâu bất thường, một task không chạy như mong đợi, hoặc một thay đổi ở module này làm phát sinh công việc trong module khác.

## 1. Task graph là gì?

Trong Gradle, một **task** là một đơn vị công việc có thể được thực hiện trong quá trình build. Ví dụ, một dự án Java có thể có các task để biên dịch mã nguồn, sao chép tài nguyên, chạy kiểm thử, tạo JAR và kiểm tra chất lượng.

Task graph là đồ thị có hướng mô tả các task được chọn cho một lần build và các quan hệ cần thiết giữa chúng. Mỗi nút là một task. Các quan hệ phụ thuộc cho biết task nào cần hoàn thành trước task nào.

Có thể hình dung một phần graph như sau:

~~~text
build
├── check
│   └── test
│       └── testClasses
│           ├── compileTestJava
│           └── processTestResources
└── assemble
    └── jar
        └── classes
            ├── compileJava
            └── processResources
~~~

Sơ đồ trên minh họa các quan hệ thường gặp khi dùng Java plugin. Đây là cách biểu diễn rút gọn để giải thích: task **build** phụ thuộc vào các task vòng đời **check** và **assemble**; **check** dẫn đến kiểm thử; **assemble** dẫn đến tạo JAR; các task này tiếp tục cần những công việc biên dịch hoặc xử lý tài nguyên.

Trong quan hệ phụ thuộc, task ở phía trên cần các task phía dưới hoàn thành trước. Vì vậy, khi yêu cầu **build**, Gradle sẽ đưa các dependency cần thiết vào graph. Task có thể xuất hiện trong graph dù người dùng không gõ tên task đó trực tiếp trên dòng lệnh.

Task graph thường là một đồ thị có hướng không chu trình (DAG — Directed Acyclic Graph). Một task có thể là dependency của nhiều task khác, nhưng trong cùng một lần build, Gradle không cần thực hiện task đó lặp lại chỉ vì nhiều nhánh cùng phụ thuộc vào nó.

## 2. Gradle chọn task từ đâu?

Điểm bắt đầu của graph là các task được yêu cầu trong lệnh chạy Gradle. Ví dụ:

~~~bash
./gradlew test
~~~

Lệnh này yêu cầu task **test**. Gradle tiếp tục tìm những task mà **test** phụ thuộc vào, rồi tìm dependency của các task đó cho đến khi graph có đủ các công việc cần thiết.

Nếu yêu cầu nhiều task:

~~~bash
./gradlew clean build
~~~

thì **clean** và **build** đều là task gốc được yêu cầu. Gradle kết hợp các nhánh dependency của chúng thành một graph. Nếu nhiều nhánh cần cùng một task, task đó chỉ có một nút trong graph của lần build.

Ngoài các task được yêu cầu trực tiếp, graph có thể bao gồm task được thêm vào bởi:

- Quan hệ **dependsOn** được khai báo trong build script hoặc plugin.
- Các task vòng đời do plugin cung cấp, chẳng hạn **build**, **check**, **assemble**.
- Quan hệ **finalizedBy**, dùng để chỉ định task cần chạy sau một task khác như một bước hoàn tất.
- Các dependency được xác định từ cấu hình của dự án, ví dụ task của module phụ thuộc vào đầu ra của module khác.

Vì vậy, để giải thích một task được chọn, hãy lần ngược từ task đó đến task gốc của lệnh chạy, rồi xác định chuỗi dependency hoặc quy tắc đã đưa nó vào graph.

## 3. Phân biệt quan hệ phụ thuộc và quan hệ thứ tự

Đây là điểm quan trọng nhất khi đọc graph. Gradle có các cơ chế liên quan đến thứ tự task, nhưng chúng không có cùng ý nghĩa.

### dependsOn: phụ thuộc và kéo task vào graph

Khi khai báo:

~~~kotlin
tasks.register("report") {
    dependsOn("test")
}
~~~

task **report** phụ thuộc vào **test**. Khi chạy **report**, Gradle cũng chọn **test** và các dependency của **test**. Task phụ thuộc phải được thực hiện trước task đang phụ thuộc vào nó.

Đây là quan hệ trực tiếp giải thích vì sao một task được chọn dù tên của nó không xuất hiện trong lệnh gọi.

### mustRunAfter: ràng buộc thứ tự giữa các task đã được chọn

~~~kotlin
tasks.named("report") {
    mustRunAfter("test")
}
~~~

Quy tắc này yêu cầu **report** chạy sau **test** nếu cả hai task đã có trong graph. Bản thân **mustRunAfter** không khiến **test** được chọn khi chỉ chạy **report**.

Nếu chạy:

~~~bash
./gradlew report
~~~

thì chỉ có **report** và dependency của nó được chọn. Nếu **test** không được chọn bằng một con đường khác, ràng buộc thứ tự không tự thêm **test** vào graph.

### shouldRunAfter: gợi ý thứ tự

~~~kotlin
tasks.named("report") {
    shouldRunAfter("test")
}
~~~

**shouldRunAfter** cũng chỉ tác động đến thứ tự khi cả hai task đã được chọn. Đây là gợi ý thứ tự mềm; Gradle có thể không tuân theo nếu việc áp dụng nó tạo ra xung đột hoặc chu trình với các ràng buộc khác.

### finalizedBy: thêm task hoàn tất

~~~kotlin
tasks.named("test") {
    finalizedBy("testReport")
}
~~~

Khi **test** được chọn, task **testReport** được đưa vào kế hoạch như một task hoàn tất. Cơ chế này thường dùng để tạo báo cáo, dọn dẹp hoặc thực hiện công việc cần chạy sau task chính.

Có thể nhớ sự khác nhau như sau:

| Cơ chế | Có tự đưa task liên quan vào graph? | Vai trò |
|---|---|---|
| **dependsOn** | Có | Khai báo dependency cần thực hiện |
| **mustRunAfter** | Không | Bắt buộc thứ tự nếu cả hai task đã được chọn |
| **shouldRunAfter** | Không | Gợi ý thứ tự nếu cả hai task đã được chọn |
| **finalizedBy** | Có, khi task được hoàn tất được chọn | Đưa task hoàn tất vào kế hoạch |

Khi điều tra một task xuất hiện ngoài dự kiến, trước hết hãy tìm **dependsOn** hoặc **finalizedBy**. Chỉ thấy **mustRunAfter** hay **shouldRunAfter** trong build script thì chưa đủ để kết luận task được chọn bởi quy tắc đó.

## 4. Ví dụ: vì sao chạy build lại chọn nhiều task?

Khi dùng Java plugin, Gradle cung cấp các task vòng đời để gom nhóm những công việc phổ biến:

- **classes** gom các công việc biên dịch mã nguồn chính và xử lý tài nguyên chính.
- **test** thực hiện kiểm thử và cần các lớp kiểm thử được biên dịch.
- **check** gom các tác vụ kiểm tra, trong đó thường có **test**.
- **jar** tạo JAR từ đầu ra của source set chính.
- **assemble** gom các tác vụ tạo sản phẩm build, thường có **jar**.
- **build** là task vòng đời cấp cao, kết hợp **check** và **assemble**.

Do đó, khi chạy:

~~~bash
./gradlew build
~~~

Gradle chọn các task cần thiết cho nhánh kiểm tra và nhánh tạo sản phẩm. Một phần kế hoạch có thể được minh họa như sau:

~~~text
build
├── check
│   └── test
│       └── testClasses
│           ├── compileTestJava
│           └── processTestResources
└── assemble
    └── jar
        └── classes
            ├── compileJava
            └── processResources
~~~

Nếu chỉ chạy:

~~~bash
./gradlew jar
~~~

thì mục tiêu là tạo JAR. Gradle cần các task tạo đầu ra chính như **classes**, nhưng không cần chạy nhánh kiểm thử chỉ vì task **test** có tồn tại trong dự án.

Tương tự, chạy:

~~~bash
./gradlew test
~~~

không có nghĩa là Gradle phải chạy mọi task thuộc **assemble**. Task được chọn dựa trên dependency của task gốc, không phải dựa trên việc task đó có được định nghĩa trong dự án hay không.

Tên và dependency cụ thể có thể thay đổi theo plugin, cấu hình source set và phiên bản Gradle. Khi cần giải thích một dự án thật, hãy kiểm tra graph và build script của chính dự án đó thay vì chỉ dựa vào sơ đồ khái quát.

## 5. Xem kế hoạch bằng --dry-run

Cách trực tiếp để xem task nào nằm trong kế hoạch là chạy Gradle với tùy chọn **--dry-run**:

~~~bash
./gradlew build --dry-run
~~~

Trên Windows dùng Gradle Wrapper:

~~~powershell
.\gradlew.bat build --dry-run
~~~

Gradle vẫn thực hiện các bước cần thiết để cấu hình build và xác định task graph, nhưng không thực hiện action của các task trong kế hoạch. Kết quả thường hiển thị mỗi task cùng trạng thái **SKIPPED** vì đây là chế độ chạy thử.

Ví dụ đầu ra minh họa:

~~~text
> Task :compileJava SKIPPED
> Task :processResources SKIPPED
> Task :classes SKIPPED
> Task :compileTestJava SKIPPED
> Task :processTestResources SKIPPED
> Task :testClasses SKIPPED
> Task :test SKIPPED
> Task :check SKIPPED
> Task :jar SKIPPED
> Task :assemble SKIPPED
> Task :build SKIPPED

BUILD SUCCESSFUL
~~~

Tên và thứ tự thực tế phụ thuộc vào dự án. Mục đích của ví dụ là cho thấy những task nào được chọn, không phải khẳng định mọi dự án đều có đúng danh sách này.

Đọc kết quả theo cách sau:

1. Dòng **> Task :...** cho biết task đó nằm trong kế hoạch của lần chạy.
2. Đường dẫn task cho biết project và tên task. Ví dụ **:app:test** là task **test** của project **app**.
3. Hậu tố **SKIPPED** trong chế độ dry run cho biết action không được thực thi do đang xem thử kế hoạch.
4. Nếu task không xuất hiện, task đó không thuộc graph được in ra cho lệnh hiện tại.

**Lưu ý:** **SKIPPED** trong kết quả dry run không có nghĩa task bị bỏ qua do điều kiện **onlyIf**, cũng không cho biết task sẽ là **UP-TO-DATE** hoặc **FROM-CACHE** khi chạy thật. Dry run cố ý không thực hiện task action, nên không thể dùng kết quả này để kết luận trạng thái thực thi thực tế.

Có thể kết hợp với chế độ console đơn giản để log dễ đọc hơn:

~~~bash
./gradlew build --dry-run --console=plain
~~~

Với dự án nhiều module, hãy thử task path đầy đủ để xem riêng nhánh cần điều tra:

~~~bash
./gradlew :app:test --dry-run --console=plain
~~~

## 6. Dùng log để hiểu vì sao task được chọn hoặc bị bỏ qua

Dry run trả lời câu hỏi task nào có trong graph. Khi cần tìm nguyên nhân sâu hơn, có thể bật log mức **--info**:

~~~bash
./gradlew build --info --console=plain
~~~

Mức log này cung cấp thêm thông tin về cấu hình, task và quyết định thực thi. Tùy trường hợp, log có thể cho biết task không cần chạy lại vì đầu vào và đầu ra không thay đổi, hoặc một điều kiện khiến task bị bỏ qua.

Có thể dùng riêng task đang được điều tra để giảm lượng log:

~~~bash
./gradlew :app:test --info --console=plain
~~~

Một số tùy chọn hữu ích khác:

| Lệnh hoặc tùy chọn | Mục đích |
|---|---|
| **./gradlew tasks --all** | Liệt kê các task có thể gọi, kể cả nhiều task không xuất hiện trong danh sách mặc định |
| **./gradlew help --task test** | Hiển thị thông tin trợ giúp về một task |
| **--dry-run** | Xem các task trong kế hoạch mà không chạy task action |
| **--info** | Hiển thị thêm thông tin để chẩn đoán quyết định của Gradle |
| **--console=plain** | Dùng đầu ra console đơn giản, thuận tiện khi đọc hoặc lưu log |

Đừng nhầm **./gradlew tasks --all** với kế hoạch thực thi. Lệnh đó liệt kê các task đã được đăng ký trong dự án; nó không nói rằng tất cả các task đó sẽ chạy trong lần build tiếp theo. Muốn biết task nào được chọn cho một yêu cầu cụ thể, hãy dùng **--dry-run** với chính lệnh cần kiểm tra.

Mức **--debug** tạo log rất chi tiết, thường chỉ cần khi **--info** chưa đủ. Log debug có thể chứa nhiều thông tin nội bộ của môi trường build; hãy thận trọng khi chia sẻ log từ máy hoặc pipeline có thông tin nhạy cảm.

## 7. Đọc trạng thái task trong một lần chạy thật

Sau khi đã xem graph, có thể chạy lệnh bình thường để quan sát trạng thái thực tế:

~~~bash
./gradlew build --console=plain
~~~

Gradle có thể hiển thị các trạng thái khác nhau. Chúng giúp phân biệt task được chọn nhưng không cần thực hiện action với task không nằm trong graph.

| Trạng thái | Ý nghĩa |
|---|---|
| Không có hậu tố đặc biệt | Task đã chạy các action cần thiết và hoàn tất |
| **UP-TO-DATE** | Gradle xác định đầu vào và đầu ra của task không thay đổi theo cách cần thiết để chạy lại |
| **FROM-CACHE** | Đầu ra phù hợp được khôi phục từ build cache |
| **SKIPPED** | Task được chọn nhưng action bị bỏ qua, ví dụ do điều kiện thực thi không thỏa mãn |
| **NO-SOURCE** | Task được chọn nhưng không có tệp nguồn phù hợp để xử lý |
| **FAILED** | Task thực thi thất bại |

Ví dụ:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources NO-SOURCE
> Task :test
> Task :jar
~~~

Có thể diễn giải như sau:

- **compileJava** vẫn là task được chọn, nhưng Gradle không cần biên dịch lại vì kết quả còn hợp lệ.
- **processResources** được chọn, nhưng không có tài nguyên nguồn phù hợp để xử lý.
- **test** được thực thi.
- **jar** được thực thi để tạo sản phẩm.

Đây là khác biệt quan trọng:

- **Không được chọn:** task không có trong task graph của lệnh hiện tại.
- **Được chọn nhưng không chạy action:** task có trong graph, nhưng Gradle quyết định không thực hiện action vì trạng thái hoặc điều kiện cụ thể.

Một task **UP-TO-DATE** không phải task bị quên hoặc không được chọn. Nó đã được xem xét trong graph và Gradle xác định rằng không cần thực hiện lại công việc.

## 8. Những lý do thường gặp khiến task được chọn nhưng bị bỏ qua

### Đầu vào và đầu ra không thay đổi

Gradle theo dõi inputs và outputs của task. Nếu task có đầu ra hợp lệ và Gradle xác định các đầu vào không thay đổi, task có thể mang trạng thái **UP-TO-DATE**.

Ví dụ, nếu mã nguồn Java không thay đổi giữa hai lần build, task biên dịch có thể không cần chạy lại.

### Đầu ra được khôi phục từ build cache

Nếu task có thể dùng build cache và Gradle tìm được đầu ra tương ứng, trạng thái có thể là **FROM-CACHE**. Task vẫn được chọn vì dependency graph yêu cầu nó, nhưng Gradle dùng kết quả đã lưu thay cho việc chạy lại action.

### Không có mã nguồn để xử lý

Một task xử lý tài nguyên hoặc biên dịch có thể được chọn nhưng không có tệp đầu vào phù hợp. Gradle có thể đánh dấu task là **NO-SOURCE**.

### Điều kiện onlyIf không thỏa mãn

Task có thể khai báo điều kiện chạy bằng **onlyIf**:

~~~kotlin
tasks.register("publishReport") {
    onlyIf {
        providers.gradleProperty("publishReport").orNull == "true"
    }
    doLast {
        println("Publishing report")
    }
}
~~~

Khi điều kiện trả về **false**, task vẫn có thể nằm trong graph nhưng action bị bỏ qua. Muốn chạy task với điều kiện này, có thể gọi:

~~~bash
./gradlew publishReport -PpublishReport=true
~~~

### Task bị vô hiệu hóa

Task có thể được cấu hình với **enabled = false**:

~~~kotlin
tasks.named("publishReport") {
    enabled = false
}
~~~

Task bị vô hiệu hóa sẽ không thực hiện action. Khi đọc log, hãy phân biệt trường hợp này với việc task không được chọn ngay từ đầu.

## 9. Phân tích task không xuất hiện trong kế hoạch

Khi kỳ vọng một task sẽ chạy nhưng không thấy nó trong kết quả dry run, hãy kiểm tra các nguyên nhân theo thứ tự:

1. **Task có được yêu cầu trực tiếp không?** Xác nhận chính xác lệnh Gradle, task name và project path.
2. **Có dependency dẫn đến task đó không?** Tìm khai báo **dependsOn** ở task gốc hoặc các task trung gian.
3. **Task có thuộc đúng project không?** Trong dự án nhiều module, **test** và **:app:test** có thể chỉ đến các phạm vi khác nhau. Dùng task path đầy đủ khi cần.
4. **Bạn đang nhầm quan hệ thứ tự với dependency không?** **mustRunAfter** và **shouldRunAfter** không tự đưa task vào graph.
5. **Task có được thêm thông qua plugin hoặc finalizer không?** Kiểm tra cấu hình plugin và **finalizedBy**.
6. **Task có thực sự được đăng ký trong cấu hình hiện tại không?** Dùng **tasks --all** để xem task có tồn tại trong lần cấu hình đó.

Ví dụ, nếu có:

~~~kotlin
tasks.register("integrationTest") {
    // Cấu hình tác vụ kiểm thử tích hợp
}

tasks.named("check") {
    dependsOn("integrationTest")
}
~~~

thì chạy **check** sẽ kéo **integrationTest** vào graph thông qua **dependsOn**.

Nếu thay bằng:

~~~kotlin
tasks.named("integrationTest") {
    shouldRunAfter("test")
}
~~~

thì chạy **test** không tự chọn **integrationTest**. Quy tắc trên chỉ có ý nghĩa nếu cả hai task đã được chọn bằng những con đường khác.

Khi task không xuất hiện, hãy lần theo dependency từ task gốc. Việc chỉ nhìn thấy task trong danh sách **tasks --all** không chứng minh task đó thuộc kế hoạch thực thi.

## 10. Dự án nhiều module và task path

Trong dự án Gradle nhiều module, tên task có thể giống nhau ở nhiều project. Ví dụ, cả project gốc và project con đều có thể có task **test**.

Task path giúp xác định đúng vị trí:

- **:test**: task **test** ở project gốc.
- **:app:test**: task **test** trong project con **app**.
- **:service:test**: task **test** trong project con **service**.

Để xem kế hoạch của một module cụ thể:

~~~bash
./gradlew :app:build --dry-run --console=plain
~~~

Nếu chạy task ở project gốc, các dependency giữa project có thể kéo thêm task từ module khác vào graph. Chẳng hạn, một module cần đầu ra của module thư viện, vì vậy build module ứng dụng có thể cần chạy task biên dịch hoặc đóng gói ở module thư viện trước.

Khi đọc output, hãy chú ý phần project path trước tên task. Nếu log có **:core:compileJava**, đó là task biên dịch của project **core**, không phải của project gốc hoặc project **app**.

## 11. Vì sao thứ tự hiển thị không phải lúc nào cũng là một chuỗi cố định?

Task graph thể hiện các ràng buộc thứ tự, không nhất thiết là một danh sách tuyến tính duy nhất. Nếu hai task không phụ thuộc nhau và không có ràng buộc thứ tự, Gradle có thể thực thi chúng theo những thứ tự khác nhau. Khi bật thực thi song song, log cũng có thể xen kẽ giữa các task.

Ví dụ, hai task xử lý tài nguyên và biên dịch có thể cùng là dependency của một task tổng hợp. Nếu không có quan hệ bắt buộc giữa chúng, không nên suy ra rằng task xuất hiện trước trong log là dependency của task xuất hiện sau.

Hãy đọc quan hệ phụ thuộc trong graph:

- Nếu **A dependsOn B**, B phải hoàn tất trước A.
- Nếu A và B chỉ là hai dependency độc lập của cùng một task, chúng có thể chạy theo thứ tự khác nhau.
- Nếu có **mustRunAfter** hoặc **shouldRunAfter**, hãy xét thêm ràng buộc thứ tự giữa các task đã được chọn.
- Nếu có **finalizedBy**, task hoàn tất được đưa vào kế hoạch để chạy sau task được hoàn tất.

Vì vậy, output console hữu ích để xem task được chọn và trạng thái của chúng, còn dependency graph và cấu hình mới giải thích quan hệ giữa các task.

## 12. Quy trình thực hành: giải thích vì sao một task được chọn

Giả sử một thành viên trong nhóm hỏi: “Vì sao khi chạy **build**, Gradle lại chạy **compileTestJava**?”

Có thể điều tra theo quy trình sau.

**Bước 1: Xác nhận lệnh gốc**

~~~bash
./gradlew build --dry-run --console=plain
~~~

Xác nhận **compileTestJava** thực sự xuất hiện trong graph của lệnh này.

**Bước 2: Lần theo task vòng đời**

Với Java plugin, **build** bao gồm nhánh **check**. Nhánh **check** cần **test**; task **test** cần các lớp kiểm thử đã được chuẩn bị, trong đó có **compileTestJava**.

Có thể mô tả đường dependency khái quát:

~~~text
build
  -> check
     -> test
        -> testClasses
           -> compileTestJava
~~~

**Bước 3: Xác nhận cấu hình thực tế**

Nếu dự án có plugin hoặc build script tùy chỉnh, dùng log và kiểm tra cấu hình task để xác nhận các dependency thực tế. Không giả định graph của mọi dự án đều giống hoàn toàn graph mặc định của Java plugin.

**Bước 4: Phân biệt lựa chọn với thực thi**

Nếu dry run hiển thị:

~~~text
> Task :compileTestJava SKIPPED
~~~

điều đó cho biết task nằm trong graph nhưng action không chạy vì đang ở chế độ dry run. Khi chạy thật, task có thể thực thi, ở trạng thái **UP-TO-DATE**, hoặc được khôi phục từ cache.

**Bước 5: Trình bày lời giải thích**

Một lời giải thích đầy đủ cần nêu:

- Task gốc được gọi là **build**.
- **build** cần **check**.
- **check** cần **test**.
- Nhánh kiểm thử cần biên dịch mã nguồn kiểm thử, vì vậy **compileTestJava** được đưa vào graph.
- Trạng thái thực thi của task phải được đọc từ lần chạy thật, không suy ra từ dry run.

Cách giải thích này cho thấy cả nguyên nhân task được chọn và trạng thái thực thi của nó.

## 13. Checklist đọc kế hoạch thực thi

Khi xem một task graph hoặc log Gradle, hãy tự hỏi:

- Lệnh nào đã khởi tạo lần build?
- Task nào được yêu cầu trực tiếp?
- Những task nào được kéo vào qua **dependsOn**?
- Có task hoàn tất nào được thêm bằng **finalizedBy** không?
- Có quy tắc **mustRunAfter** hoặc **shouldRunAfter** ảnh hưởng đến thứ tự không?
- Task path cho biết task thuộc project nào?
- Task không xuất hiện vì không được chọn, hay xuất hiện với trạng thái cho biết action không chạy?
- Kết quả đang xem đến từ **--dry-run** hay từ một lần thực thi thật?
- Nếu task không cần chạy lại, trạng thái là **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE** hay **SKIPPED**?

Một câu trả lời tốt cho câu hỏi “Vì sao task X được chọn?” nên chỉ ra được đường đi từ task gốc đến X qua các dependency hoặc cơ chế thêm task. Một câu trả lời tốt cho câu hỏi “Vì sao task X không thực hiện?” cần chỉ ra task có nằm trong graph hay không, sau đó giải thích trạng thái thực thi tương ứng.

## 14. Những nguyên tắc cần nhớ

- Gradle chỉ chọn task cần thiết cho những task được yêu cầu và các quan hệ liên quan; task được định nghĩa trong dự án không tự động chạy.
- Task graph mô tả tập hợp task được chọn và các ràng buộc giữa chúng.
- **dependsOn** tạo dependency và đưa task cần thiết vào graph.
- **mustRunAfter** và **shouldRunAfter** điều chỉnh thứ tự giữa những task đã được chọn; chúng không tự chọn task.
- **finalizedBy** thêm task hoàn tất khi task được hoàn tất được chọn.
- **--dry-run** là cách nhanh để xem kế hoạch mà không thực hiện task action.
- **tasks --all** liệt kê task có thể gọi, không phải kế hoạch của một lệnh build cụ thể.
- **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE** và **SKIPPED** mô tả các trường hợp task đã được xem xét nhưng không thực hiện action theo cách thông thường.
- Thứ tự log không phải lúc nào cũng chứng minh quan hệ phụ thuộc, nhất là khi có task độc lập hoặc build chạy song song.
- Với dự án nhiều module, hãy dùng task path đầy đủ để xác định đúng project.

Khi nắm được cách Gradle hình thành task graph và đọc được các trạng thái task, ta có thể giải thích rõ vì sao một task được chọn, vì sao một task không xuất hiện, và vì sao một task có trong kế hoạch nhưng không chạy action. Đây là nền tảng để chẩn đoán build hiệu quả và hiểu cách các plugin phối hợp trong một quy trình build lớn.

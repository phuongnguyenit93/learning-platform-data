# Từ mục tiêu dòng lệnh đến tập tác vụ cần chạy

Khi gọi một lệnh build, người phát triển thường chỉ nêu một mục tiêu như **build**, **test** hoặc **run**. Công cụ build phải chuyển yêu cầu đó thành một tập công việc cụ thể: xác định tác vụ được yêu cầu, tìm các tác vụ phụ thuộc, áp dụng những ràng buộc về thứ tự, rồi thực thi các tác vụ đủ điều kiện chạy.

Vì vậy, một lệnh như **gradlew build** không đơn giản có nghĩa là chạy một tác vụ duy nhất tên build. Trong dự án Gradle, tác vụ build thường là tác vụ tổng hợp phụ thuộc vào nhiều tác vụ khác. Gradle xây dựng đồ thị tác vụ từ mục tiêu dòng lệnh và các quan hệ được khai báo trong cấu hình dự án. Hiểu quá trình này giúp đọc log, dự đoán những gì sẽ chạy và tìm nguyên nhân khi một tác vụ xuất hiện hoặc bị bỏ qua ngoài dự kiến.

## 1. Mục tiêu dòng lệnh là điểm bắt đầu

Khi chạy Gradle Wrapper, đối số sau tên wrapper thường chỉ định tác vụ hoặc nhóm tác vụ mà người dùng muốn thực hiện.

Ví dụ:

    ./gradlew build
    ./gradlew test
    ./gradlew clean build

Trên Windows:

    gradlew.bat build
    gradlew.bat test
    gradlew.bat clean build

Trong các lệnh trên:

- **build** yêu cầu Gradle thực hiện tác vụ build của dự án.
- **test** yêu cầu thực hiện tác vụ kiểm thử tương ứng.
- **clean build** yêu cầu cả clean và build. Gradle sẽ xem xét quan hệ phụ thuộc và thứ tự cần thiết giữa những tác vụ này.

Tên tác vụ trên dòng lệnh là điểm bắt đầu để chọn công việc. Nó chưa mô tả toàn bộ những gì sẽ chạy. Một tác vụ có thể phụ thuộc vào nhiều tác vụ khác, và các tác vụ phụ thuộc lại có thể có những phụ thuộc riêng.

Nếu không chỉ định tác vụ, Gradle có thể chạy tác vụ mặc định do dự án cấu hình bằng **defaultTasks**. Nếu dự án không cấu hình tác vụ mặc định, việc gọi wrapper mà không có task selector không đồng nghĩa với việc tự động chạy build. Có thể xem danh sách tác vụ bằng:

    ./gradlew tasks

Lệnh này giúp khám phá những tác vụ được công bố trong dự án. Muốn xem chi tiết một tác vụ:

    ./gradlew help --task build

## 2. Tác vụ được yêu cầu có thể là tác vụ tổng hợp

Trong Gradle, một tác vụ có thể phụ thuộc vào các tác vụ khác. Tác vụ tổng hợp thường gom nhiều bước thành một mục tiêu dễ gọi.

Ví dụ giản lược:

    tasks.register('preparePackage') {
        dependsOn 'compileJava', 'processResources'
    }

    tasks.register('assembleApp') {
        dependsOn 'preparePackage', 'jar'
    }

Khi yêu cầu **assembleApp**, Gradle cần đưa các tác vụ phụ thuộc vào đồ thị. Nếu **preparePackage** phụ thuộc vào **compileJava** và **processResources**, những tác vụ đó cũng được đưa vào tập công việc cần thực hiện.

Quan hệ phụ thuộc có thể được hình dung như sau:

    assembleApp
       |----> preparePackage
       |          |----> compileJava
       |          +----> processResources
       |
       +----> jar

Sơ đồ cho thấy một mục tiêu dòng lệnh có thể mở rộng thành nhiều tác vụ. Trong dự án thực tế, các plugin Java, Application, War hoặc các plugin khác thường tạo sẵn nhiều tác vụ và quan hệ phụ thuộc. Người phát triển không cần tự khai báo toàn bộ đồ thị tiêu chuẩn đó.

## 3. Gradle hình thành đồ thị tác vụ

Có thể chia quá trình xử lý một lệnh Gradle thành ba giai đoạn lớn:

1. **Initialization:** Gradle xác định build nào tham gia, đọc cấu trúc dự án và các tệp settings cần thiết.
2. **Configuration:** Gradle đánh giá các build script, tạo và cấu hình các project/task, đồng thời ghi nhận các quan hệ phụ thuộc và điều kiện liên quan.
3. **Execution:** Gradle thực hiện các tác vụ trong đồ thị đã chọn theo các quan hệ phụ thuộc và thứ tự hợp lệ.

Ví dụ, khi chạy **./gradlew build**, Gradle cần biết project nào có trong build, tác vụ build nằm ở đâu, task đó phụ thuộc vào những tác vụ nào và những task đó có phụ thuộc tiếp hay không. Sau khi cấu hình, Gradle xác định tập tác vụ cần thực hiện và thứ tự thực thi phù hợp.

Điểm quan trọng là Gradle không chạy mọi task chỉ vì chúng được khai báo trong build script. Một task có thể tồn tại trong dự án nhưng không được đưa vào đồ thị của lệnh hiện tại. Task chỉ tham gia khi được yêu cầu trực tiếp, được kéo vào qua quan hệ phụ thuộc, được thêm như finalizer phù hợp hoặc được chọn bởi cơ chế khác của build.

## 4. Đồ thị phụ thuộc quyết định những tác vụ nào được chọn

Đồ thị tác vụ (task graph) biểu diễn các tác vụ và quan hệ giữa chúng. Với quan hệ **dependsOn**, tác vụ được yêu cầu kéo các tác vụ phụ thuộc vào đồ thị.

Ví dụ:

    tasks.register('compileDomain') {
        dependsOn 'compileJava'
    }

    tasks.register('verifyApp') {
        dependsOn 'test', 'checkstyleMain'
    }

Nếu chạy:

    ./gradlew verifyApp

Gradle cần thực hiện **verifyApp**, **test** và **checkstyleMain**, cùng với những phụ thuộc của các tác vụ đó. Nếu **test** phụ thuộc vào **testClasses**, và **testClasses** phụ thuộc vào **compileTestJava**, các tác vụ này cũng được đưa vào đồ thị.

Một sơ đồ ví dụ:

    verifyApp
       |----> test
       |        |----> testClasses
       |        |        +----> compileTestJava
       |        +----> test runtime dependencies
       |
       +----> checkstyleMain

Đồ thị không nhất thiết là một cây. Hai tác vụ có thể cùng phụ thuộc vào một tác vụ khác. Ví dụ, cả **test** và **jar** đều có thể cần **classes**. Trong trường hợp đó, tác vụ chung chỉ cần được thực hiện một lần trong một lần gọi build, sau khi những điều kiện phụ thuộc của nó được đáp ứng.

## 5. Yêu cầu nhiều tác vụ trên dòng lệnh

Người dùng có thể yêu cầu nhiều task selector trong cùng một lệnh:

    ./gradlew clean test

Hoặc:

    ./gradlew test jar

Gradle kết hợp các yêu cầu vào một đồ thị chung. Nếu hai mục tiêu cùng cần một tác vụ phụ thuộc, tác vụ đó không bị chạy lặp lại chỉ vì được tham chiếu từ hai nhánh.

Thứ tự các tên task trên dòng lệnh không phải lúc nào cũng là cách mô tả đầy đủ thứ tự thực thi. Các quan hệ phụ thuộc và ràng buộc thứ tự trong đồ thị mới quyết định thứ tự hợp lệ. Nếu cần bảo đảm một tác vụ chạy trước tác vụ khác, hãy khai báo quan hệ phù hợp thay vì dựa vào thứ tự gõ tên trên dòng lệnh.

Ví dụ, nếu **clean** và **build** được yêu cầu cùng lúc, dự án nên có quan hệ rõ ràng để đầu ra được dọn trước khi build tạo lại chúng. Với những tác vụ được gọi độc lập, không nên dựa vào giả định rằng Gradle sẽ luôn chạy chúng theo đúng thứ tự xuất hiện trong lệnh.

## 6. Task path trong dự án nhiều module

Một build Gradle có thể gồm nhiều project con. Khi đó, cùng một tên task có thể tồn tại trong nhiều project. Task path giúp xác định chính xác project và task.

Ví dụ cấu trúc:

    product-app/
      settings.gradle
      build.gradle
      app/
        build.gradle
      domain/
        build.gradle

Một số task path có thể là:

    :
    :app:build
    :app:test
    :domain:build
    :domain:test

Dấu hai chấm đầu tiên biểu thị root project. **:app:test** yêu cầu task test của project app; **:domain:build** yêu cầu task build của project domain.

Có thể chạy một task ở module cụ thể:

    ./gradlew :app:test

Hoặc yêu cầu nhiều module:

    ./gradlew :app:build :domain:test

Khi một task ở module phụ thuộc vào task của module khác, quan hệ project dependency có thể khiến các task cần thiết ở module kia cũng được đưa vào đồ thị. Ví dụ, nếu app phụ thuộc vào domain, quá trình biên dịch app cần có đầu ra phù hợp từ domain.

Nếu chỉ gõ tên task không có task path trong build nhiều module, Gradle có thể chọn những task khớp với tên đó theo quy tắc task selector. Để tránh mơ hồ, hãy dùng task path đầy đủ khi cần nhắm chính xác một project.

## 7. Phân biệt dependsOn với các ràng buộc thứ tự

Không phải mọi quan hệ giữa task đều làm task kia được chọn để chạy. Gradle có một số cơ chế khác nhau, mỗi cơ chế có ý nghĩa riêng.

### dependsOn

**dependsOn** biểu thị một tác vụ cần tác vụ khác làm công việc phụ thuộc. Tác vụ phụ thuộc được đưa vào đồ thị khi tác vụ chính được yêu cầu.

    tasks.register('verifyRelease') {
        dependsOn 'test'
    }

Chạy **verifyRelease** sẽ kéo **test** vào tập tác vụ cần chạy.

### mustRunAfter

**mustRunAfter** quy định thứ tự nếu cả hai tác vụ đã được đưa vào đồ thị. Nó không tự chọn tác vụ được nhắc tới để chạy.

    tasks.named('publish') {
        mustRunAfter 'test'
    }

Nếu chỉ chạy **publish**, task **test** không tự động được thêm chỉ vì có **mustRunAfter**. Nếu cả **test** và **publish** đều được chọn, Gradle sẽ cố gắng đặt test trước publish theo ràng buộc này.

### shouldRunAfter

**shouldRunAfter** là ràng buộc thứ tự mềm. Gradle cố gắng tuân theo khi có thể, nhưng có thể bỏ qua nếu ràng buộc xung đột với các yêu cầu khác hoặc làm đồ thị không thể sắp xếp hợp lệ.

Nó cũng không tự thêm task được nhắc tới vào đồ thị.

### finalizedBy

**finalizedBy** đăng ký một tác vụ finalizer cần chạy sau tác vụ được hoàn tất. Finalizer có thể được đưa vào đồ thị khi tác vụ được finalize được chọn.

    tasks.register('integrationTest') {
        finalizedBy 'collectTestReport'
    }

    tasks.register('collectTestReport') {
        doLast {
            println 'Collecting integration test report'
        }
    }

Khi **integrationTest** được chọn, **collectTestReport** được thêm làm tác vụ hoàn tất. Cơ chế finalizer hữu ích cho việc thu thập báo cáo hoặc dọn tài nguyên sau một tác vụ. Cần thiết kế cẩn thận để finalizer không xóa dữ liệu mà tác vụ khác còn cần.

| Cơ chế | Có tự thêm task liên quan vào đồ thị? | Ý nghĩa chính |
| --- | --- | --- |
| **dependsOn** | Có | Chọn công việc phụ thuộc |
| **mustRunAfter** | Không | Bắt buộc thứ tự khi cả hai đã được chọn |
| **shouldRunAfter** | Không | Gợi ý thứ tự khi có thể |
| **finalizedBy** | Có, như tác vụ hoàn tất | Chạy tác vụ finalizer sau task được finalize |

Đây là khác biệt quan trọng khi phân tích vì sao một task xuất hiện hoặc không xuất hiện trong đồ thị.

## 8. Điều kiện chạy và loại trừ task

Sau khi tập tác vụ đã được xác định, vẫn có những lý do khiến một task không thực hiện phần công việc của nó.

### Điều kiện onlyIf

Task có thể khai báo điều kiện để chỉ chạy khi điều kiện đúng:

    tasks.register('publishSnapshot') {
        onlyIf {
            project.hasProperty('snapshot')
        }
        doLast {
            println 'Publishing snapshot'
        }
    }

Nếu điều kiện **onlyIf** trả về false, task được bỏ qua khi thực thi. Task đã được chọn vào đồ thị nhưng không thực hiện hành động chính. Đây là khác biệt với việc task không được chọn ngay từ đầu.

### Loại trừ bằng -x

Có thể loại trừ một task bằng tùy chọn **-x**:

    ./gradlew build -x test

Lệnh này yêu cầu build nhưng loại trừ task test theo selector. Cần thận trọng vì những tác vụ khác có thể giả định rằng kiểm thử đã được thực hiện. Loại trừ task có thể làm thay đổi ý nghĩa của mục tiêu build và làm giảm mức kiểm chứng của kết quả.

### Task bị vô hiệu hóa hoặc không có nguồn

Một task có thể bị vô hiệu hóa bằng thuộc tính **enabled**. Một số task xử lý tập tệp rỗng cũng có thể hiển thị **NO-SOURCE** vì không có đầu vào nguồn phù hợp để xử lý.

Những trạng thái này cần được phân biệt với việc task không tồn tại hoặc không được chọn vào đồ thị.

## 9. Task graph không đồng nghĩa với mọi task sẽ thực thi

Có ba khái niệm cần tách biệt:

1. **Task được chọn:** task được yêu cầu trực tiếp hoặc được đưa vào do phụ thuộc, finalizer hay cơ chế lựa chọn khác.
2. **Task trong đồ thị:** task thuộc tập công việc Gradle đã lập kế hoạch cho lần gọi hiện tại.
3. **Task thực sự thực thi hành động:** task có thể chạy hành động, được đánh dấu up-to-date, lấy đầu ra từ cache, bị bỏ qua bởi điều kiện hoặc không có nguồn để xử lý.

Ví dụ, **compileJava** có thể nằm trong đồ thị nhưng hiển thị **UP-TO-DATE** vì đầu vào và đầu ra không thay đổi. Nó đã được chọn và được kiểm tra, nhưng phần biên dịch không cần thực hiện lại.

Một task khác có thể hiển thị **FROM-CACHE** vì đầu ra phù hợp được khôi phục từ build cache. Task được xử lý trong đồ thị, nhưng công việc không cần chạy lại trên máy hiện tại.

Do đó, khi đọc log, đừng kết luận rằng task không thuộc đồ thị chỉ vì nó không in ra thông điệp trong **doLast**. Hãy phân biệt trạng thái task và phần hành động mà task thực hiện.

## 10. Xem trước tập tác vụ bằng dry-run

Gradle có tùy chọn **--dry-run** để hiển thị các task sẽ được thực hiện mà không chạy các hành động của task:

    ./gradlew build --dry-run

Trên Windows:

    gradlew.bat build --dry-run

Tùy chọn này hữu ích để quan sát những task được chọn và thứ tự thực thi dự kiến. Gradle vẫn cần khởi tạo và cấu hình build để xác định đồ thị, vì vậy build script và logic cấu hình vẫn có thể được đánh giá. Dry-run không phải môi trường sandbox để kiểm tra mọi tác động của quá trình cấu hình.

Có thể kết hợp dry-run với task path:

    ./gradlew :app:build --dry-run

Khi cần tìm hiểu tại sao một task được chọn, hãy xem quan hệ **dependsOn**, finalizer và cấu hình plugin. Khi một task không được chọn, kiểm tra xem có task nào thực sự kéo nó vào đồ thị hay không.

## 11. Đọc log và tìm nguyên nhân task xuất hiện

Tùy chọn **--info** cung cấp thêm thông tin trong quá trình build:

    ./gradlew build --info

Tùy chọn **--console=plain** có thể giúp log dễ đọc hơn trong terminal hoặc khi lưu vào tệp:

    ./gradlew build --console=plain --info

Khi đọc log, hãy xác định:

- Task selector nào được truyền từ dòng lệnh.
- Task path nào được chọn trong từng project.
- Task nào được kéo vào qua phụ thuộc.
- Task nào có ràng buộc thứ tự hoặc finalizer.
- Task nào thực thi, up-to-date, from-cache, skipped hoặc no-source.
- Có lỗi nào làm quá trình thực thi dừng lại hay không.

Nếu build có nhiều module, tên đầy đủ như **:app:compileJava** dễ nhận biết hơn tên **compileJava** đứng riêng. Task path giúp xác định chính xác project sở hữu task.

## 12. Ví dụ tổng hợp: từ lệnh build đến đồ thị

Giả sử một dự án Java có các task:

    build
      |----> check
      |        |----> test
      |        |        +----> testClasses
      |        |                  +----> compileTestJava
      |        |
      |        +----> checkstyleMain
      |
      +----> assemble
               +----> jar
                        +----> classes
                                  |----> compileJava
                                  +----> processResources

Khi chạy:

    ./gradlew build

Gradle bắt đầu từ task build, mở rộng quan hệ phụ thuộc, đưa các task cần thiết vào đồ thị, rồi sắp xếp chúng theo quan hệ hợp lệ. Nếu **compileJava** và **processResources** đã up-to-date, Gradle có thể bỏ qua hành động của chúng nhưng vẫn dùng đầu ra hiện có để thực hiện **jar**.

Nếu chạy:

    ./gradlew :app:test

Gradle chọn task test ở project app và các task cần thiết cho việc kiểm thử. Task build tổng thể và những nhánh không liên quan không nhất thiết được chọn.

Nếu chạy:

    ./gradlew build -x test

Gradle vẫn chọn build và các phụ thuộc còn lại theo cấu hình, nhưng loại trừ task test. Điều này có thể làm thay đổi tập công việc thực hiện so với build thông thường.

Các ví dụ cho thấy tên mục tiêu dòng lệnh chỉ là điểm bắt đầu. Tập tác vụ thực tế phụ thuộc vào cấu trúc dự án, plugin, quan hệ phụ thuộc, selector, tùy chọn dòng lệnh và điều kiện cấu hình.

## 13. Cách thiết kế đồ thị tác vụ dễ hiểu

Một đồ thị tốt thể hiện rõ công việc và quan hệ dữ liệu giữa các bước:

- Dùng task có ý nghĩa rõ ràng, thể hiện một công việc cụ thể.
- Dùng **dependsOn** khi một task thực sự cần đầu ra hoặc công việc từ task khác.
- Dùng ràng buộc thứ tự cho yêu cầu về thứ tự mà không tạo phụ thuộc dữ liệu.
- Dùng finalizer cho công việc cần thực hiện sau task chính, chẳng hạn thu thập báo cáo.
- Tránh tạo phụ thuộc vòng giữa các task.
- Để plugin tiêu chuẩn quản lý các task biên dịch, kiểm thử và đóng gói khi có thể.
- Dùng task path rõ ràng khi làm việc với build nhiều module.

Phụ thuộc vòng khiến Gradle không thể sắp xếp đồ thị thành thứ tự thực thi hợp lệ và build sẽ báo lỗi. Nếu hai task phụ thuộc lẫn nhau, hãy xem lại ranh giới công việc: có thể cần tách một bước dùng chung thành task thứ ba hoặc thay đổi cách tạo đầu vào.

Không nên thêm **dependsOn** chỉ để ép log có vẻ chạy theo một thứ tự mong muốn. Phụ thuộc nên phản ánh quan hệ công việc thật. Nếu chỉ cần sắp xếp hai task đã được chọn, hãy dùng cơ chế thứ tự phù hợp.

## 14. Quy trình thực hành khi phân tích một lệnh build

Khi muốn biết một mục tiêu dòng lệnh sẽ làm những gì, có thể làm theo trình tự:

1. Đọc lệnh đầy đủ, bao gồm wrapper, task selector, task path và tùy chọn như **-x**, **--continue** hoặc **--dry-run**.
2. Xác định project và task được yêu cầu. Với build nhiều module, kiểm tra task path.
3. Xem mô tả task bằng **help --task** và danh sách task bằng **tasks** nếu chưa biết task selector.
4. Tìm các quan hệ **dependsOn**, **finalizedBy**, **mustRunAfter** và **shouldRunAfter** có liên quan.
5. Chạy dry-run để quan sát tập task và thứ tự dự kiến.
6. Chạy với **--info** khi cần biết trạng thái thực thi hoặc lý do một task bị bỏ qua.
7. Đối chiếu kết quả với đầu vào, đầu ra và cấu hình của task nếu tập công việc không như dự kiến.

Lệnh build không phải danh sách thao tác cố định được chạy giống nhau trong mọi hoàn cảnh. Nó là một yêu cầu được giải quyết dựa trên cấu hình và đồ thị của dự án tại thời điểm build. Khi hiểu cách selector mở rộng thành task graph, người phát triển có thể dự đoán chính xác hơn những phần công việc cần chạy và giải thích được vì sao một task được đưa vào, bị loại trừ hoặc không cần thực thi.

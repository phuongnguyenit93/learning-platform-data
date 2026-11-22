# Khi nào bỏ qua một bước làm thay đổi ý nghĩa của build thành công

Một lệnh build kết thúc với mã thoát bằng 0 thường được hiểu là thành công. Tuy nhiên, kết quả đó chỉ có ý nghĩa trong phạm vi những mục tiêu và bước kiểm tra mà lệnh thực sự yêu cầu, cùng với cách dự án cấu hình chúng. Nếu một bước quan trọng bị bỏ qua, lệnh vẫn có thể kết thúc thành công trong khi sản phẩm chưa được kiểm tra hoặc tạo ra theo mức bảo đảm mà nhóm mong đợi.

Điều quan trọng là phân biệt việc bỏ qua để tối ưu một công việc đã có kết quả hợp lệ với việc bỏ qua một công việc vốn mang ý nghĩa kiểm chứng hoặc tạo sản phẩm. Build tăng dần và build cache thường giúp tránh thực thi lại mà vẫn giữ kết quả đúng. Ngược lại, loại trừ kiểm thử, tắt bước kiểm tra hoặc chạy một mục tiêu ngắn hơn có thể làm thay đổi ý nghĩa của chữ “thành công”.

## 1. Build thành công có nghĩa là gì?

Build thành công có nghĩa công cụ đã hoàn tất yêu cầu được đưa ra theo cấu hình hiện tại mà không gặp lỗi khiến lệnh thất bại. Nó không tự động có nghĩa:

- Tất cả mã nguồn và mọi module trong repository đều đã được biên dịch.
- Tất cả unit test, integration test và kiểm thử hệ thống đều đã chạy.
- Các quy tắc chất lượng, bảo mật và định dạng mã đều đã được kiểm tra.
- Sản phẩm đã được thử trên môi trường triển khai thực tế.
- Không có task nào bị bỏ qua hoặc lấy kết quả cũ.

Ví dụ, lệnh chỉ biên dịch có thể thành công dù không chạy kiểm thử. Lệnh đóng gói có thể thành công khi một task kiểm tra tùy chọn đã bị loại trừ. Lệnh build có thể thành công dù test được cấu hình bỏ qua khi có lỗi. Trong các trường hợp đó, mã thoát bằng 0 vẫn phản ánh kết quả của cấu hình và yêu cầu hiện tại, nhưng mức bảo đảm thấp hơn một pipeline đầy đủ.

Vì vậy, khi đọc thông báo “BUILD SUCCESSFUL” hoặc “BUILD SUCCESS”, cần hỏi: **lệnh đã yêu cầu những bước nào, những bước nào thực sự được thực hiện, và những bước nào đã bị bỏ qua?**

## 2. Không phải mọi trạng thái bỏ qua đều có cùng ý nghĩa

Các công cụ build có nhiều lý do để không thực thi một bước. Một số trạng thái thể hiện tối ưu hợp lệ; một số trạng thái thể hiện bước không có việc để làm; một số trạng thái có thể bỏ qua kiểm tra quan trọng.

| Trạng thái hoặc cách bỏ qua | Điều gì xảy ra? | Ảnh hưởng thường gặp đến ý nghĩa build |
| --- | --- | --- |
| **UP-TO-DATE** | Đầu vào và đầu ra được theo dõi vẫn phù hợp với lần chạy trước; dùng đầu ra hiện có. | Thường là tối ưu hợp lệ nếu khai báo đầu vào/đầu ra chính xác. |
| **FROM-CACHE** | Khôi phục đầu ra phù hợp từ build cache thay vì thực thi task. | Thường vẫn đáp ứng mục tiêu nếu task cacheable và khóa đầu vào đầy đủ. |
| **NO-SOURCE** | Task không có tệp nguồn phù hợp để xử lý. | Có thể hợp lệ nếu phần nguồn đó thật sự không tồn tại; đáng nghi nếu nguồn bắt buộc bị cấu hình sai. |
| **SKIPPED** do điều kiện | Task đã được chọn nhưng điều kiện thực thi không thỏa mãn. | Phụ thuộc vào việc điều kiện có phù hợp với yêu cầu kiểm chứng hay không. |
| Bị loại khỏi task graph | Task không được chọn hoặc bị loại trừ khỏi đồ thị. | Mục tiêu có thể không còn bao gồm bước kiểm tra mà người đọc tưởng rằng nó có. |
| Task bị vô hiệu hóa | Task có thể nằm trong đồ thị nhưng không chạy hành động của nó. | Có thể làm mất một phần bảo đảm nếu task đó là bước bắt buộc. |
| Chỉ chạy dry-run | Công cụ hiển thị kế hoạch mà không thực hiện hành động task. | Không chứng minh sản phẩm đã được build hoặc kiểm thử. |

Không nên chỉ nhìn chữ **SKIPPED** để kết luận build an toàn hay không an toàn. Cần tìm nguyên nhân và xem bước đó có thuộc tiêu chí thành công của công việc hay không.

## 3. Bỏ qua do UP-TO-DATE hoặc FROM-CACHE thường là tối ưu hợp lệ

Một bước không cần chạy lại nếu kết quả đã có vẫn hợp lệ với đầu vào hiện tại.

### UP-TO-DATE

Gradle có thể đánh dấu task là **UP-TO-DATE** khi trạng thái đầu vào và đầu ra của task không thay đổi so với lần chạy trước. Ví dụ:

    ./gradlew build
    ./gradlew build

Nếu lần đầu build thành công và lần thứ hai không có thay đổi liên quan, các task như compileJava hoặc processResources có thể được bỏ qua vì đầu ra vẫn dùng được.

Trong trường hợp này, việc không thực thi lại không có nghĩa bỏ qua kiểm tra chất lượng. Nếu task test được chọn, Gradle cũng có thể không chạy lại test khi kết quả kiểm thử được xác định là up-to-date theo cấu hình của task. Trạng thái đó vẫn khác với việc loại hẳn test khỏi build.

### FROM-CACHE

Với task có thể cache, Gradle có thể khôi phục đầu ra từ build cache nếu tìm thấy kết quả tương ứng với các đầu vào đã khai báo. Task không cần chạy lại trên máy hiện tại nhưng kết quả được tái sử dụng.

Đây là tối ưu hợp lệ khi task có tính tái lập và khai báo đầy đủ những yếu tố ảnh hưởng kết quả. Nếu task đọc một biến môi trường hoặc tệp cấu hình nhưng không khai báo nó là đầu vào, công cụ có thể tái sử dụng kết quả không phù hợp. Khi đó, vấn đề nằm ở mô tả đầu vào của task, không nằm ở bản thân cơ chế cache.

### Vì sao hai trường hợp này khác với bỏ qua kiểm thử?

UP-TO-DATE và FROM-CACHE nhằm cung cấp kết quả của một công việc đã được xác định là còn hợp lệ. Loại trừ test hoặc tắt một task kiểm tra có nghĩa công việc kiểm chứng đó không được thực hiện trong lần build hiện tại. Một kết quả biên dịch cũ hợp lệ có thể thay thế việc biên dịch lại; nhưng một lần test chưa từng chạy không thể được xem là đã kiểm chứng chỉ vì task test không báo lỗi.

## 4. Bỏ qua task bằng tùy chọn dòng lệnh

Người dùng có thể chủ động loại một task khỏi yêu cầu build. Đây là cách nhanh để rút ngắn thời gian hoặc chẩn đoán, nhưng nó thay đổi tập công việc của lệnh.

### Gradle: loại trừ bằng -x

Ví dụ:

    ./gradlew build -x test

Với plugin Java tiêu chuẩn, task build thường phụ thuộc vào assemble và check; check lại bao gồm test cùng các kiểm tra khác được cấu hình. Tùy chọn **-x test** loại task test khỏi đồ thị của lần gọi đó. Những phần còn lại của build vẫn có thể hoàn tất và lệnh có thể báo **BUILD SUCCESSFUL**.

Kết quả này không có nghĩa unit test đã vượt qua. Nó có nghĩa mục tiêu build đã hoàn tất sau khi task test bị loại trừ. Nếu tiêu chí phát hành yêu cầu test phải chạy, lệnh này không đủ để chứng minh tiêu chí đó.

### Maven: bỏ qua chạy test

Với Maven, lệnh:

    mvn package -DskipTests

thường bỏ qua việc thực thi test nhưng vẫn biên dịch mã kiểm thử. Gói có thể được tạo thành công dù các test không chạy.

Lệnh:

    mvn package -Dmaven.test.skip=true

bỏ qua cả biên dịch test và thực thi test đối với các plugin Maven phổ biến hỗ trợ thuộc tính này, chẳng hạn Maven Compiler Plugin và Maven Surefire Plugin. Đây là mức bỏ qua rộng hơn.

Tên thuộc tính và cách hỗ trợ có thể phụ thuộc plugin. Hãy kiểm tra cấu hình plugin trong dự án khi dùng thuộc tính bỏ qua.

### Tác động

Trong cả hai hệ sinh thái, tùy chọn bỏ qua có thể hữu ích khi đang chỉnh sửa tài liệu, cần đóng gói tạm để kiểm tra một phần hoặc chẩn đoán lỗi ở bước khác. Nhưng nếu dùng cùng lệnh trong CI hoặc trước phát hành mà không có một bước test riêng, pipeline có thể báo thành công dù không có bằng chứng kiểm thử mới.

## 5. Bỏ qua do điều kiện hoặc cấu hình task

Một task có thể được chọn vào đồ thị nhưng không chạy hành động do điều kiện.

### Gradle onlyIf

Ví dụ:

    tasks.register('verifyRelease') {
        onlyIf {
            providers.gradleProperty('runReleaseChecks').orNull == 'true'
        }

        doLast {
            println 'Running release checks'
        }
    }

Nếu không truyền thuộc tính **runReleaseChecks=true**, task có thể bị bỏ qua:

    ./gradlew verifyRelease

Lệnh vẫn có thể thành công dù phần kiểm tra phát hành không chạy. Nếu đây là kiểm tra bắt buộc, điều kiện mặc định false có thể tạo ra cảm giác an toàn giả: người chạy thấy lệnh thành công nhưng không biết gate đã bị bỏ qua.

Khi điều kiện phụ thuộc vào môi trường, cần thể hiện rõ môi trường nào bắt buộc bật kiểm tra. Ví dụ, pipeline phát hành nên truyền tham số hoặc cấu hình để các bước kiểm tra bắt buộc được thực thi.

### Task bị vô hiệu hóa

Gradle task có thuộc tính **enabled**. Khi task bị đặt disabled, Gradle không thực hiện hành động task đó. Cấu hình này có thể hữu ích khi một tính năng không áp dụng cho module cụ thể, nhưng nguy hiểm nếu vô hiệu hóa một task gate dùng chung.

Hãy tìm nơi đặt **enabled = false**, điều kiện onlyIf và các thuộc tính cấu hình liên quan khi một task đột nhiên hiển thị skipped.

### Maven profile và cấu hình plugin

Maven có thể bật/tắt plugin execution theo profile, điều kiện kích hoạt profile hoặc cấu hình plugin. Một lệnh Maven có thể thành công nhưng một execution không được kích hoạt trong profile hiện tại.

Ví dụ, profile kiểm tra bổ sung chỉ được bật trong môi trường CI. Nếu người dùng chạy build ở local mà profile đó không kích hoạt, kết quả local không chứng minh các kiểm tra của profile đã chạy.

Khi phân tích build Maven, cần xem các profile đang hoạt động và các execution gắn với lifecycle phase, không chỉ nhìn dòng cuối cùng của log.

## 6. Chọn mục tiêu ngắn hơn có thể bỏ qua các phase phía sau

Mỗi công cụ build có mô hình lifecycle riêng. Chọn một mục tiêu sớm hơn trong lifecycle có nghĩa là các phase phía sau không được yêu cầu.

### Maven lifecycle

Trong Maven, các phase chính của default lifecycle được thực hiện theo thứ tự. Ví dụ:

    validate
    compile
    test
    package
    verify
    install
    deploy

Khi chạy:

    mvn package

Maven thực hiện các phase trước và bao gồm package, nhưng không tự chạy những phase sau như verify, install hoặc deploy.

Khi chạy:

    mvn verify

Maven đi qua các phase trước đó và đến verify. Các kiểm tra tích hợp được cấu hình ở các phase tương ứng có thể được thực hiện.

Do đó, **mvn package** thành công không đồng nghĩa với việc toàn bộ kiểm tra gắn với **verify** đã hoàn tất. Nếu tiêu chí dự án yêu cầu integration test hoặc kiểm tra bổ sung trong verify, phải gọi mục tiêu phù hợp.

### Gradle lifecycle

Với plugin Java tiêu chuẩn, task **build** là mục tiêu tổng hợp thường bao gồm **assemble** và **check**. Task **assemble** tạo các sản phẩm có thể phân phối; task **check** gom các bước kiểm tra, trong đó thường có test.

Nếu chỉ chạy:

    ./gradlew assemble

thì việc tạo sản phẩm có thể hoàn tất mà không chạy toàn bộ các bước kiểm tra được gom trong check. Lệnh này hữu ích khi chỉ cần tạo artifact, nhưng không nên được diễn giải như một lần xác minh đầy đủ.

Nếu chỉ chạy:

    ./gradlew test

thì kiểm thử được yêu cầu cùng những task phụ thuộc cần thiết, nhưng không nhất thiết tạo artifact phân phối như task jar hoặc assemble.

Hãy chọn mục tiêu phù hợp với mức bảo đảm cần có: compile để kiểm tra biên dịch, test để chạy kiểm thử, assemble để tạo artifact, build để thực hiện tập công việc build tiêu chuẩn của plugin và verify hoặc pipeline phát hành nếu dự án định nghĩa các gate bổ sung.

## 7. Bỏ qua kiểm thử có thể làm thay đổi ý nghĩa của thành công

Kiểm thử là ví dụ dễ thấy nhất vì một build có thể biên dịch và đóng gói tốt nhưng chương trình vẫn có lỗi hành vi.

### Không chạy test

Nếu test bị loại trừ hoặc bị skip, lệnh build không có bằng chứng rằng các test liên quan đã chạy trong lần build đó. Mã nguồn có thể biên dịch thành công trong khi một thay đổi làm sai logic, gây regression hoặc phá vỡ hợp đồng giữa các module.

### Test có chạy nhưng lỗi bị bỏ qua

Một cấu hình khác là cho phép test thất bại mà không làm build thất bại.

Trong Gradle, task Test có thuộc tính **ignoreFailures**. Nếu đặt true, lỗi kiểm thử có thể không làm task thất bại theo cách mặc định:

    tasks.withType(Test).configureEach {
        ignoreFailures = true
    }

Trong Maven Surefire, cấu hình **testFailureIgnore** cũng có thể cho phép build tiếp tục khi test thất bại:

    <plugin>
        <artifactId>maven-surefire-plugin</artifactId>
        <configuration>
            <testFailureIgnore>true</testFailureIgnore>
        </configuration>
    </plugin>

Những cấu hình này có thể hữu ích trong một số quy trình thu thập báo cáo hoặc migration, nhưng chúng làm thay đổi ý nghĩa của kết quả cuối. Build có thể kết thúc thành công dù báo cáo chứa test thất bại.

Nếu nhóm dùng các thiết lập đó, cần có bước riêng đọc báo cáo và quyết định gate. Không nên chỉ dựa vào exit code của build để kết luận test đã pass.

### Không có nguồn test

Trạng thái **NO-SOURCE** có thể hoàn toàn hợp lệ khi module không có test hoặc task không có tệp phù hợp. Nhưng nếu module đáng lẽ phải có test mà source set hoặc đường dẫn bị cấu hình sai, task vẫn có thể không có gì để chạy.

Đối với module quan trọng, cần xác định test có thực sự được phát hiện hay không. Một task test kết thúc mà không tìm thấy test không cung cấp cùng mức bảo đảm với một tập test đã chạy và pass.

## 8. Dry-run không phải là một lần build thực tế

Gradle hỗ trợ:

    ./gradlew build --dry-run

Dry-run hiển thị các task trong kế hoạch thực thi mà không chạy hành động của task. Nó hữu ích để xem task graph, nhưng không chứng minh mã nguồn biên dịch được, test pass hoặc artifact được tạo.

Nếu pipeline chỉ chạy dry-run mà vẫn gắn nhãn là build verification thành công, nhãn đó gây hiểu nhầm. Dry-run là bước kiểm tra kế hoạch; cần một lần thực thi thật để xác nhận kết quả build.

Tương tự, việc xem danh sách task bằng **gradlew tasks** hoặc xem mô tả task bằng **help --task** chỉ cung cấp thông tin cấu hình, không thực hiện build.

## 9. --continue không có nghĩa là bỏ qua lỗi

Gradle có tùy chọn:

    ./gradlew build --continue

Tùy chọn này cho phép Gradle tiếp tục thực hiện các task độc lập có thể chạy sau khi một task thất bại, thay vì dừng ngay khi gặp lỗi đầu tiên. Tuy nhiên, build vẫn được báo thất bại nếu có task thất bại.

Đây là khác biệt với việc cấu hình bỏ qua lỗi hoặc loại trừ task. **--continue** giúp thu thập nhiều lỗi trong một lần chạy; nó không biến một build có lỗi thành build thành công.

Khi đọc log, cần phân biệt:

- Task bị bỏ qua do điều kiện.
- Task bị loại khỏi đồ thị.
- Task up-to-date hoặc from-cache.
- Task thất bại nhưng các task độc lập khác vẫn tiếp tục chạy.

Các trạng thái đó mang ý nghĩa khác nhau đối với chất lượng và mức hoàn tất của build.

## 10. Tác động đến CI và quy trình phát hành

Một pipeline CI thường gồm nhiều gate, mỗi gate trả lời một câu hỏi khác nhau:

| Gate | Câu hỏi cần trả lời |
| --- | --- |
| Compile | Mã nguồn có biên dịch được với cấu hình đã chọn không? |
| Unit test | Các hành vi nhỏ có đáp ứng kỳ vọng không? |
| Integration test | Các thành phần có phối hợp đúng với nhau không? |
| Static analysis | Mã có vi phạm quy tắc chất lượng hoặc lỗi tiềm ẩn không? |
| Package | Artifact có được tạo theo cấu hình không? |
| Security checks | Dependency và mã nguồn có vượt qua các kiểm tra bảo mật được yêu cầu không? |
| Acceptance/deployment checks | Sản phẩm có đáp ứng điều kiện của môi trường mục tiêu không? |

Nếu một gate bị bỏ qua, pipeline không còn chứng minh được câu hỏi tương ứng. Các gate khác vẫn có thể thành công, nhưng không thể thay thế lẫn nhau.

Ví dụ, compile thành công không thay thế unit test; unit test thành công không thay thế integration test; package thành công không chứng minh artifact đã được triển khai và kiểm tra trên môi trường thực.

Một pipeline nên định nghĩa rõ:

- Những bước nào bắt buộc cho mọi pull request.
- Những bước nào chỉ chạy cho nhánh chính hoặc trước phát hành.
- Những bước nào có thể bỏ qua trong quá trình phát triển local.
- Điều kiện nào được phép bỏ qua một bước.
- Ai hoặc quy trình nào có quyền chấp nhận một gate bị bỏ qua.

Nếu một gate bắt buộc bị bỏ qua, trạng thái tổng thể nên thể hiện điều đó thay vì gộp chung vào nhãn thành công không phân biệt.

## 11. Ví dụ: build xanh nhưng kiểm thử chưa chạy

Giả sử pipeline có lệnh:

    ./gradlew build -x test

Kết quả hiển thị:

    BUILD SUCCESSFUL

Nhìn riêng dòng cuối, người đọc có thể nghĩ toàn bộ build tiêu chuẩn đã hoàn tất. Nhưng task test đã bị loại trừ. Kết quả thực tế chỉ cho biết các task còn lại trong đồ thị đã hoàn tất theo cấu hình.

Nếu thay bằng:

    ./gradlew build

và task test được chạy thành công, pipeline có thêm bằng chứng kiểm thử. Nếu task test hiển thị UP-TO-DATE, Gradle đang dùng trạng thái kiểm thử đã được xác định còn hợp lệ theo cơ chế theo dõi của task. Nếu task test hiển thị SKIPPED do onlyIf, cần kiểm tra điều kiện để hiểu vì sao kiểm thử không chạy.

Một pipeline tốt có thể chạy build thông thường ở pull request và có gate phát hành bổ sung. Nếu cần cho phép bỏ qua test khi phát triển local, nên giữ tùy chọn đó ở lệnh local và không để nó vô tình áp dụng trong pipeline bắt buộc.

## 12. Cách đọc trạng thái trong log

Khi một build thành công nhưng bạn nghi ngờ có bước bị bỏ qua, hãy xem log chi tiết:

    ./gradlew build --info --console=plain

Đối với Maven, có thể xem log chi tiết hơn:

    mvn verify -X

Tùy chọn Maven **-X** tạo log debug rất nhiều thông tin; dùng khi cần điều tra cấu hình plugin hoặc lifecycle execution.

Hãy tìm:

1. Mục tiêu chính xác trên dòng lệnh.
2. Các task hoặc phase đã được chọn.
3. Trạng thái của từng task: thực thi, up-to-date, from-cache, skipped, no-source hoặc failed.
4. Lý do skip, điều kiện onlyIf hoặc thuộc tính bỏ qua.
5. Profile Maven đang hoạt động và plugin execution nào được kích hoạt.
6. Báo cáo test, integration test và phân tích chất lượng nếu các bước đó không chạy hoặc lỗi bị bỏ qua.

Đừng chỉ kiểm tra dòng tổng kết. Dòng tổng kết phản ánh kết quả của yêu cầu đã chạy; log và báo cáo cho biết yêu cầu đó thực sự bao gồm những gì.

## 13. Quy trình quyết định có thể chấp nhận một bước bị bỏ qua hay không

Khi thấy một task bị bỏ qua, có thể phân tích theo trình tự:

1. **Xác định task:** bước nào bị bỏ qua và nó chịu trách nhiệm tạo hoặc kiểm tra điều gì?
2. **Xác định nguyên nhân:** up-to-date, from-cache, no-source, onlyIf, disabled, bị loại khỏi đồ thị, hay mục tiêu dòng lệnh không yêu cầu?
3. **Xác định yêu cầu:** bước này có bắt buộc trong mục tiêu hiện tại, pull request hoặc phát hành không?
4. **Xác định bằng chứng thay thế:** có kết quả cache hợp lệ, báo cáo từ một gate khác hoặc bằng chứng được chấp nhận theo chính sách không?
5. **Đánh giá ảnh hưởng:** nếu không có bước này, build còn chứng minh được điều gì và không còn chứng minh được điều gì?
6. **Ghi nhận ngoại lệ:** nếu bỏ qua là có chủ đích, làm rõ lý do và phạm vi chấp nhận.

Ví dụ:

| Tình huống | Cách đánh giá |
| --- | --- |
| compileJava UP-TO-DATE, đầu ra hợp lệ | Thường có thể chấp nhận; công việc biên dịch đã có kết quả còn hiệu lực. |
| compileJava FROM-CACHE với đầu vào đầy đủ | Thường có thể chấp nhận; đầu ra được khôi phục từ cache. |
| test bị loại bằng -x test trong CI bắt buộc test | Không đáp ứng gate kiểm thử. |
| test SKIPPED vì onlyIf mặc định false | Cần kiểm tra cấu hình và mục tiêu của pipeline. |
| test NO-SOURCE ở module không có test theo thiết kế | Có thể chấp nhận nếu đã xác nhận đúng kỳ vọng. |
| test NO-SOURCE ở module bắt buộc có test | Có thể là lỗi cấu hình source set hoặc thiếu test. |
| chạy build --dry-run | Chỉ xác nhận kế hoạch, chưa xác nhận build thực tế. |
| test có lỗi nhưng ignoreFailures bật | Build xanh không chứng minh test pass; cần đọc báo cáo và gate riêng. |

## 14. Thiết kế thông báo kết quả rõ nghĩa

Một thông báo build hữu ích nên cho người đọc biết:

- Lệnh và profile/cấu hình đã dùng.
- Các gate bắt buộc đã chạy.
- Các gate được bỏ qua cùng lý do.
- Task nào dùng kết quả up-to-date hoặc cache.
- Test có thất bại hay không, kể cả khi cấu hình cho phép build tiếp tục.
- Artifact nào đã được tạo và ở vị trí nào.

Ví dụ, thay vì chỉ ghi “Build thành công”, có thể mô tả:

    Build package completed.
    Compilation: passed (some tasks UP-TO-DATE).
    Unit tests: skipped by -x test.
    Integration tests: not requested.
    Artifact: build/libs/app.jar.

Thông tin này không làm thay đổi kết quả kỹ thuật, nhưng giúp người nhận hiểu đúng mức xác minh đã được thực hiện. Trong CI, nên giữ log và báo cáo test như artifact để có thể kiểm tra lại.

## 15. Nguyên tắc sử dụng bước bỏ qua

Việc bỏ qua một task có thể phù hợp trong quá trình phát triển, nhưng cần giữ rõ ranh giới giữa tối ưu và giảm mức kiểm chứng:

- Cho phép tái sử dụng đầu ra khi công cụ xác định đầu vào và đầu ra vẫn hợp lệ.
- Chỉ loại trừ task khi mục tiêu hiện tại thực sự không cần công việc đó.
- Không dùng cấu hình bỏ qua test để làm xanh một gate yêu cầu test pass.
- Không coi dry-run là bằng chứng build đã thực thi.
- Không xem NO-SOURCE là thành công kiểm thử nếu dự án kỳ vọng có test.
- Không để onlyIf hoặc profile mặc định vô tình tắt gate bắt buộc.
- Khi cho phép bỏ qua, ghi rõ bước nào không chạy và lý do.
- Tách mục tiêu tạo artifact khỏi mục tiêu xác minh chất lượng khi quy trình cần hai mức bảo đảm khác nhau.

Một build chỉ có ý nghĩa khi kết quả được diễn giải cùng với tập công việc đã được yêu cầu và thực hiện. UP-TO-DATE hoặc FROM-CACHE có thể giữ nguyên mức bảo đảm vì đầu ra hợp lệ được tái sử dụng. Việc loại trừ kiểm thử, tắt gate, chọn lifecycle phase quá sớm hoặc chỉ chạy dry-run có thể làm giảm phạm vi xác minh. Vì thế, hãy đọc trạng thái task và báo cáo kiểm tra trước khi kết luận một build thành công có đủ điều kiện để tích hợp hoặc phát hành hay không.

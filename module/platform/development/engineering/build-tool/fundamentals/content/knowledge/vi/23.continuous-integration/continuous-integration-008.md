# Lưu báo cáo kiểm thử, log và checksum để truy vết

Một build trong CI không chỉ tạo ra JAR, WAR hoặc container image. Nó còn tạo ra bằng chứng cho biết mã nguồn nào đã được build, những kiểm thử nào đã chạy, lỗi xuất hiện ở đâu, và artifact cuối cùng có còn nguyên vẹn sau khi được lưu trữ hoặc chuyển sang môi trường khác hay không.

Ba loại dữ liệu thường cần được lưu cùng mỗi lần build là:

- **Báo cáo kiểm thử:** cho biết test nào được phát hiện, đã chạy, thất bại, bị bỏ qua hoặc không thực thi.
- **Log build:** ghi lại lệnh, task, phase, thông báo, lỗi và ngữ cảnh thực thi.
- **Checksum:** dấu vân tay mật mã của artifact hoặc gói bằng chứng, giúp phát hiện nội dung bị thay đổi trong quá trình lưu trữ và truyền tải.

Nếu chỉ giữ artifact mà không lưu báo cáo và log, nhóm có thể biết build đã tạo ra file nào nhưng khó giải thích vì sao build thất bại hoặc chất lượng kiểm thử ra sao. Nếu chỉ lưu log mà không ghi checksum, nhóm khó xác nhận file triển khai có đúng là artifact đã được tạo và kiểm tra hay không.

Lưu trữ đúng cách giúp điều tra sự cố, so sánh các lần build, truy nguyên artifact đã phát hành, hỗ trợ audit và tái hiện lỗi. Nội dung lưu cần gắn với một định danh build duy nhất, có đường dẫn rõ ràng, thời hạn lưu phù hợp và quyền truy cập an toàn.

## 1. Bằng chứng của một lần build gồm những gì?

Một build có thể tạo ra nhiều nhóm đầu ra:

| Nhóm dữ liệu | Ví dụ | Câu hỏi được trả lời |
| --- | --- | --- |
| Artifact | JAR, WAR, ZIP, container image | Đã tạo ra sản phẩm nào? |
| Báo cáo test | JUnit XML, HTML report | Test nào đã chạy và kết quả ra sao? |
| Log | Console output, build.log, test log | Build đã thực hiện những bước nào và lỗi ở đâu? |
| Checksum | SHA-256 file, manifest checksum | Nội dung artifact có bị thay đổi không? |
| Metadata build | Commit, branch, build ID, JDK, Gradle/Maven version | Artifact được tạo từ đầu vào và môi trường nào? |
| Dependency evidence | Dependency tree, lockfile, resolved versions | Build đã sử dụng những thư viện nào? |

Không phải dự án nào cũng cần lưu mọi loại dữ liệu ở mọi lần chạy. Tuy nhiên, với CI dùng để phát hành, tối thiểu nên giữ artifact, báo cáo test, log và checksum gắn với cùng build ID.

### Phân biệt log, report và checksum

- Log là bản ghi sự kiện và thông điệp trong quá trình thực thi.
- Report là dữ liệu có cấu trúc được công cụ test tạo ra để tổng hợp test case, trạng thái và thời lượng.
- Checksum là giá trị tính từ bytes của một file; nó không giải thích nội dung file hoặc lý do build thành công/thất bại.

Các loại dữ liệu bổ sung cho nhau. Một báo cáo XML cho biết test nào thất bại; log có thể chứa stack trace và thông tin môi trường; checksum giúp xác nhận artifact được phân tích hoặc triển khai chính là file đã được build.

## 2. Gắn tất cả đầu ra với một build ID

Mỗi lần chạy CI nên có một định danh duy nhất, chẳng hạn:

    project-api/
      2026-11-13/
        build-1842/
          metadata/
            build-info.txt
            dependency-tree.txt
          reports/
            unit-tests/
            integration-tests/
          logs/
            build.log
          artifacts/
            application.jar
            SHA256SUMS

Tên thư mục thực tế phụ thuộc nền tảng CI. Có thể dùng build number, pipeline ID, run ID hoặc một ID kết hợp commit và attempt.

Không nên dùng tên chung như latest hoặc test-report.xml làm nơi lưu trữ duy nhất, vì build sau có thể ghi đè bằng chứng của build trước. Tên có build ID giúp:

- Liên kết report, log và artifact với đúng lần chạy.
- Giữ riêng kết quả của các lần retry.
- So sánh build trên các commit khác nhau.
- Truy tìm file được triển khai sau này.
- Tránh nhiều job ghi đè cùng một đường dẫn.

Nếu một pipeline có nhiều job hoặc matrix theo JDK, OS, module hay architecture, hãy thêm các thuộc tính đó vào tên hoặc metadata. Ví dụ build-1842-jdk21-linux và build-1842-jdk17-windows cần có report và log riêng.

## 3. Lưu báo cáo kiểm thử để biết chính xác test đã chạy

Báo cáo test giúp nhóm trả lời:

- Có bao nhiêu test được phát hiện?
- Bao nhiêu test pass, fail, error hoặc skipped?
- Test nào thất bại và stack trace là gì?
- Test chạy trong module hoặc suite nào?
- Thời gian thực thi của từng test ra sao?
- Có test nào không được chạy do filter, skip hoặc discovery sai không?

Báo cáo có cấu trúc thường được ưu tiên vì CI có thể đọc và hiển thị kết quả tự động. JUnit XML là định dạng trao đổi phổ biến, dù nhiều framework không phải JUnit cũng có thể xuất báo cáo theo định dạng này.

HTML report thuận tiện cho con người đọc, trong khi XML phù hợp cho CI, công cụ tổng hợp và phân tích tự động. Nên lưu cả hai khi chi phí lưu trữ cho phép.

## 4. Đường dẫn báo cáo Maven Surefire

Maven Surefire chạy unit test trong phase test. Báo cáo mặc định thường được tạo tại:

    target/surefire-reports/

Thư mục này thường chứa:

- Tệp XML theo lớp hoặc suite test.
- Tệp TXT với thông tin kết quả và lỗi.
- Các dữ liệu phụ trợ tùy phiên bản plugin và cấu hình.

Ví dụ:

    target/
      surefire-reports/
        TEST-com.example.OrderServiceTest.xml
        com.example.OrderServiceTest.txt

Với dự án nhiều module, mỗi module thường có thư mục target riêng:

    api/target/surefire-reports/
    service/target/surefire-reports/
    web/target/surefire-reports/

Khi upload báo cáo lên CI, cần thu thập tất cả module cần thiết. Chỉ upload target/surefire-reports ở root có thể bỏ sót báo cáo nằm trong module con.

### Cấu hình Surefire

Ví dụ cấu hình plugin:

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <reportsDirectory>
                        ${project.build.directory}/surefire-reports
                    </reportsDirectory>
                    <trimStackTrace>false</trimStackTrace>
                </configuration>
            </plugin>
        </plugins>
    </build>

reportsDirectory chỉ định nơi plugin ghi báo cáo. trimStackTrace=false giữ stack trace đầy đủ hơn trong báo cáo, hữu ích khi điều tra lỗi. Cấu hình thực tế cần tương thích với phiên bản plugin của dự án.

### Lưu báo cáo khi test thất bại

Surefire thường ghi báo cáo ngay cả khi test thất bại và làm Maven kết thúc với mã lỗi. Pipeline cần có bước upload báo cáo được chạy ngay cả khi bước test trả về lỗi.

Không nên thêm tùy chọn làm build luôn thành công chỉ để có thể upload report. Giữ nguyên exit code thất bại để CI phản ánh đúng trạng thái test; cấu hình bước lưu artifact chạy theo điều kiện always/finally của nền tảng CI.

## 5. Đường dẫn báo cáo Maven Failsafe

Maven Failsafe thường chạy integration test ở các phase integration-test và verify. Báo cáo mặc định thường nằm tại:

    target/failsafe-reports/

Ví dụ:

    target/
      failsafe-reports/
        TEST-com.example.OrderApiIT.xml
        com.example.OrderApiIT.txt

Không nên gộp báo cáo Surefire và Failsafe mà mất thông tin phân biệt loại test. Unit test và integration test có mục tiêu, môi trường, thời gian và cách xử lý lỗi khác nhau.

Có thể lưu riêng:

    reports/unit-tests/
    reports/integration-tests/

Trong multi-module build, giữ thêm tên module để không ghi đè báo cáo cùng tên.

### Chạy đến đúng phase

Lệnh:

    mvn test

chạy unit test được cấu hình ở phase test, nhưng không nhất thiết chạy integration test của Failsafe.

Lệnh:

    mvn verify

đi qua các phase integration-test và verify, do đó thường là lệnh phù hợp khi cần chạy cả integration test đã gắn vào lifecycle.

Nếu chỉ gọi compile hoặc package với cấu hình tùy chỉnh, cần xác nhận plugin và phase thực sự được thực thi. Báo cáo không xuất hiện có thể là do test chưa được yêu cầu chạy, không phải do upload artifact bị lỗi.

## 6. Báo cáo test trong Gradle

Với Java Plugin, Gradle Test task thường tạo:

    build/reports/tests/test/
    build/test-results/test/

Trong đó:

- build/reports/tests/test/index.html là báo cáo HTML mặc định thường gặp.
- build/test-results/test/ chứa kết quả XML và dữ liệu liên quan.

Nếu project có nhiều module:

    api/build/reports/tests/test/
    service/build/reports/tests/test/
    web/build/reports/tests/test/

Task test có thể được cấu hình riêng cho unit, integration hoặc các suite khác, do đó tên thư mục đầu ra có thể khác. Hãy kiểm tra task path và cấu hình reports của từng suite.

### Cấu hình HTML và JUnit XML

Ví dụ với Gradle Kotlin DSL:

    tasks.withType<Test>().configureEach {
        reports {
            junitXml.required.set(true)
            html.required.set(true)
        }
        testLogging {
            events("passed", "skipped", "failed")
            exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        }
    }

Với Groovy DSL:

    tasks.withType(Test).configureEach {
        reports {
            junitXml.required = true
            html.required = true
        }
        testLogging {
            events "passed", "skipped", "failed"
            exceptionFormat "full"
        }
    }

Cú pháp có thể khác theo phiên bản Gradle. Cần kiểm tra tài liệu của Gradle Wrapper đang dùng nếu API reports hoặc testLogging thay đổi.

### Nhiều Test task

Một dự án có thể có các task:

    test
    integrationTest
    functionalTest

Mỗi task có thể có thư mục kết quả và báo cáo riêng. Khi upload, nên giữ đúng tên suite và module:

    reports/
      app/
        unit/
        integration/
      domain/
        unit/

Không nên gom mọi XML vào một thư mục phẳng nếu có thể có tên tệp trùng nhau. Giữ cấu trúc module/task giúp CI và người điều tra xác định nguồn báo cáo.

## 7. Kiểm tra số lượng test và trạng thái

Một báo cáo tồn tại không đồng nghĩa với test đã chạy. Có thể report được tạo với số test bằng 0, tất cả test bị skipped, hoặc báo cáo cũ còn từ lần build trước.

Khi thu thập kết quả, cần lưu hoặc tổng hợp ít nhất:

- tests: tổng số test case được báo cáo.
- failures: số assertion thất bại.
- errors: số lỗi thực thi hoặc exception.
- skipped: số test không thực thi.
- thời lượng tổng và thời lượng theo test/suite nếu có.

Đối với JUnit XML, các số liệu này thường nằm trong thuộc tính của thẻ testsuite hoặc testsuites. CI có thể parse XML để tổng hợp kết quả, nhưng cần tránh đếm trùng nếu cùng test được xuất hiện trong nhiều báo cáo hoặc retry.

### Test bị skip và test không được phát hiện

Hai trường hợp này khác nhau:

- Test được phát hiện nhưng bị skip có thể có lý do như @Disabled, assumption hoặc điều kiện môi trường.
- Không có test được phát hiện có thể do source directory, naming pattern, engine, filter hoặc task sai.

Hãy lưu report gốc và log để phân biệt. Không chỉ ghi một con số pass/fail tổng hợp rồi bỏ các trạng thái còn lại.

### Báo cáo cũ

Nếu build không chạy test, thư mục report cũ có thể vẫn tồn tại. Khi upload, CI có thể vô tình lưu báo cáo từ lần chạy trước.

Để tránh nhầm:

- Dùng workspace sạch hoặc xóa output của đúng module trước khi chạy khi phù hợp.
- Ghi thời điểm tạo report.
- Gắn report với build ID và commit.
- Không dùng lại thư mục artifact chung giữa nhiều job.
- Kiểm tra log xác nhận task test đã chạy trong lần hiện tại.

## 8. Lưu log build

Log build là bản ghi của quá trình thực thi. Nó có thể chứa:

- Lệnh build và task/phase được gọi.
- Phiên bản JDK, Gradle/Maven và plugin.
- Dependency resolution hoặc repository messages.
- Thông báo compiler và annotation processor.
- Kết quả test và stack trace.
- Cảnh báo deprecation hoặc cấu hình.
- Lỗi hệ thống, timeout, OOM hoặc network.
- Mã thoát cuối cùng.

CI thường lưu console output mặc định, nhưng nên có bản log riêng trong artifact nếu log cần được giữ lâu hơn thời gian truy cập giao diện job.

### Maven: log dễ đọc cho CI

Ví dụ:

    mvn -B -ntp clean verify

- -B bật batch mode, phù hợp cho CI.
- -ntp tắt tiến trình tải thanh tiến độ transfer, giúp log gọn hơn.
- clean verify chạy lifecycle từ clean tới verify.

Có thể lưu stdout/stderr ra tệp tùy shell và CI runner. Trên PowerShell:

    mvn -B -ntp clean verify *>&1 |
        Tee-Object -FilePath build.log

Tee-Object vừa hiển thị log vừa ghi vào build.log. Cần kiểm tra cách pipeline PowerShell xử lý exit code để không làm mất trạng thái thất bại của Maven khi lưu log. Trong CI, nên dùng cơ chế capture log chuẩn của runner nếu nó giữ được cả stdout, stderr và exit code.

### Gradle: log ổn định cho CI

Ví dụ:

    ./gradlew clean build --console=plain --stacktrace

- --console=plain tránh giao diện console tương tác và giúp log dễ đọc/lưu trữ.
- --stacktrace hiển thị stack trace khi có lỗi.
- --info có thể bổ sung thông tin chẩn đoán.
- --debug tạo log rất chi tiết và có thể chứa dữ liệu nhạy cảm hoặc URL nội bộ.

Chỉ bật debug khi cần và kiểm tra nội dung trước khi lưu vào nơi nhiều người có thể truy cập.

### Không làm mất exit code khi ghi log

Một lỗi thường gặp là dùng lệnh pipe để ghi log nhưng vô tình khiến CI chỉ nhận exit code của lệnh ghi file thay vì build tool.

Ví dụ trong một số shell, lệnh:

    mvn verify | tee build.log

có thể khiến trạng thái pipeline không phản ánh đúng mã thoát của Maven nếu không bật pipefail hoặc xử lý riêng.

Hãy dùng cơ chế capture output của CI hoặc cấu hình shell để giữ exit code của lệnh build. Việc lưu log không được biến một build thất bại thành thành công.

## 9. Mức độ chi tiết của log

Không phải lúc nào cũng cần log ở mức debug.

| Mức log | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Lifecycle/default | Build thông thường | Đủ cho trạng thái và lỗi phổ biến |
| Info | Điều tra task, dependency hoặc cấu hình | Có thêm chi tiết nhưng vẫn tương đối dễ đọc |
| Debug | Điều tra lỗi khó tái hiện | Có thể chứa đường dẫn, URL, property hoặc dữ liệu nhạy cảm |
| Stack trace đầy đủ | Phân tích exception | Giữ cause và stack frame có ích |

Nên lưu log mặc định cho mọi build và chỉ bật mức chi tiết hơn khi điều tra hoặc trong job chẩn đoán riêng. Nếu log debug được lưu, cần kiểm soát quyền truy cập và thời gian retention.

Không in toàn bộ environment variables, settings.xml, credential store hoặc secret vào log. Các nền tảng CI thường hỗ trợ masking secret nhưng không thể bảo đảm che mọi cách mã hóa hoặc biến đổi dữ liệu. Build script cần tránh echo token, password, private key và URL có chứa credential.

## 10. Lưu log của test riêng với log build

Build log cho biết task test đã chạy và kết quả tổng thể. Test report cung cấp cấu trúc test case. Một số framework hoặc test harness còn tạo log riêng như:

- Log của test JVM fork.
- Log ứng dụng khởi động trong integration test.
- Log container hoặc service test.
- Log browser/driver của UI test.
- Log server hoặc database tạm.

Nếu các log này cần cho điều tra, hãy cấu hình chúng được ghi vào thư mục artifact có tên rõ ràng và gắn với test suite. Tránh ghi tất cả vào một file chung vì các test chạy song song có thể trộn dòng log và làm mất thứ tự sự kiện.

Khi test chạy song song, mỗi worker có thể cần file log riêng hoặc structured logging có thread/process ID. Ghi timestamp theo định dạng nhất quán và giữ timezone hoặc thông tin UTC trong metadata để so sánh giữa các máy.

## 11. Checksum là gì?

Checksum mật mã là giá trị được tính từ nội dung bytes của một file bằng một thuật toán hash. Với SHA-256, cùng một nội dung đầu vào sẽ tạo cùng một digest; thay đổi dù chỉ một byte sẽ tạo digest khác với xác suất va chạm cực thấp trong thực tế.

Ví dụ:

    SHA256(application.jar) = 8f...a2

Checksum có thể dùng để:

- Xác nhận artifact tải về giống file đã được tạo.
- Phát hiện file bị hỏng hoặc thay đổi khi copy.
- So sánh artifact giữa hai môi trường.
- Kiểm tra file được triển khai có đúng artifact đã được duyệt.
- Tạo danh mục checksum cho nhiều artifact.

SHA-256 là lựa chọn phổ biến. Không nên dùng MD5 hoặc SHA-1 cho mục đích bảo đảm toàn vẹn chống sửa đổi có chủ đích vì các thuật toán đó không còn phù hợp cho mục tiêu này.

### Checksum không phải chữ ký số

Checksum chỉ cho biết nội dung có khớp với digest đã biết hay không. Nếu kẻ tấn công có thể thay cả artifact lẫn file checksum không được bảo vệ, checksum không chứng minh nguồn phát hành đáng tin cậy.

Để xác thực nguồn phát hành, có thể cần chữ ký số, provenance/attestation được ký, hoặc lưu checksum trong một hệ thống metadata có kiểm soát truy cập và lịch sử bất biến.

## 12. Tạo checksum SHA-256 trên Linux và macOS

Sau khi artifact đã được tạo xong:

    sha256sum application.jar

Ví dụ đầu ra:

    8f2c...a2  application.jar

Ghi kết quả vào file:

    sha256sum application.jar > SHA256SUMS

Với nhiều artifact:

    sha256sum artifacts/*.jar > SHA256SUMS

Kiểm tra lại:

    sha256sum -c SHA256SUMS

Nếu nội dung đúng, công cụ báo OK. Nếu file bị thay đổi hoặc không tìm thấy, kiểm tra thất bại.

Trên macOS, có thể dùng:

    shasum -a 256 application.jar
    shasum -a 256 application.jar > SHA256SUMS
    shasum -a 256 -c SHA256SUMS

Hãy tạo checksum sau khi mọi bước repackage, signing hoặc chỉnh sửa artifact cuối cùng đã hoàn tất. Nếu tính checksum trước khi sửa JAR hoặc trước khi đóng gói lại, digest sẽ không còn đại diện cho file cuối cùng.

## 13. Tạo và kiểm tra checksum trên Windows

PowerShell có lệnh Get-FileHash:

    Get-FileHash -Algorithm SHA256 -LiteralPath '.\artifacts\application.jar'

Để ghi một manifest đơn giản:

    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath '.\artifacts\application.jar'
    "$($hash.Hash)  application.jar" |
        Set-Content -Encoding ascii '.\artifacts\SHA256SUMS'

Kiểm tra lại:

    $expected = (Get-Content -LiteralPath '.\artifacts\SHA256SUMS').Split(' ')[0]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath '.\artifacts\application.jar').Hash
    if ($expected -ne $actual) {
        throw 'SHA-256 checksum mismatch'
    }

Với nhiều file, nên tạo manifest có đường dẫn tương đối ổn định và xác minh từng dòng. Không dùng đường dẫn tuyệt đối của workspace trong manifest nếu artifact sẽ được tải xuống hoặc kiểm tra ở máy khác.

PowerShell cũng có thể xuất object metadata thành JSON hoặc CSV nếu cần danh mục artifact, nhưng checksum cần được tính trên đúng file bytes, không phải trên tên file hoặc metadata.

## 14. Manifest artifact và checksum

Một manifest giúp người nhận biết những file nào thuộc một lần build và digest tương ứng.

Ví dụ:

    algorithm: SHA-256
    buildId: 1842
    commit: 7f3c2a1
    artifacts:
      - path: application.jar
        sizeBytes: 482193
        checksum: 8f2c...a2
      - path: application-sources.jar
        sizeBytes: 182044
        checksum: 6a10...9b

Đây chỉ là cấu trúc minh họa; có thể dùng JSON, YAML hoặc định dạng manifest chuẩn của tổ chức. Nên ghi:

- Tên artifact và đường dẫn tương đối.
- Kích thước bytes.
- Thuật toán hash.
- Digest.
- Build ID và commit.
- Thời điểm tạo.
- Phiên bản JDK và build tool nếu cần.

Không nên đưa checksum của chính manifest vào trong manifest theo cách tạo vòng lặp. Nếu cần bảo vệ manifest, hãy ký manifest hoặc lưu digest của nó trong metadata bên ngoài.

## 15. Khi nào cần checksum cho báo cáo và log?

Thông thường, checksum quan trọng nhất với artifact được phát hành hoặc triển khai. Tuy nhiên, gói bằng chứng CI cũng có thể được nén thành một archive:

    evidence-build-1842.zip

Có thể tạo checksum cho archive:

    sha256sum evidence-build-1842.zip > evidence-build-1842.zip.sha256

Điều này giúp xác nhận gói report/log tải về không bị thay đổi. Với từng report/log riêng, checksum chỉ cần thiết nếu có yêu cầu audit, lưu trữ bất biến hoặc truyền qua nhiều hệ thống.

Nếu report và log chứa dữ liệu nhạy cảm, việc tính checksum không làm chúng an toàn hơn. Vẫn cần kiểm soát quyền truy cập, mã hóa khi lưu/truyền và retention.

## 16. Quy trình tạo artifact và checksum đúng thứ tự

Thứ tự thao tác quan trọng. Một pipeline có thể tổ chức:

    Build và test
         |
         v
    Tạo artifact
         |
         v
    Repackage / sign / finalize
         |
         v
    Kiểm tra artifact cuối
         |
         v
    Tính SHA-256
         |
         v
    Tạo manifest và metadata
         |
         v
    Lưu artifact + report + log + checksum
         |
         v
    Xác minh khi tải hoặc triển khai

Nếu ký artifact, cần thống nhất checksum được tính cho file trước hay sau khi ký. Thông thường, checksum của file được phân phối cuối cùng nên được tính sau mọi thay đổi cuối cùng. Nếu có cả file unsigned và signed, hãy ghi riêng digest cho từng file.

Không sửa artifact sau khi checksum đã được tạo. Nếu có bước copy, nén hoặc chuyển đổi làm thay đổi bytes, cần tính checksum mới cho file đầu ra cuối cùng.

## 17. Ví dụ pipeline Maven tổng quát

Một pipeline Maven có thể thực hiện:

1. Checkout đúng commit.
2. Ghi metadata build.
3. Chạy Maven verify và lưu console log.
4. Thu thập Surefire/Failsafe reports ngay cả khi test thất bại.
5. Nếu build thành công, thu thập artifact.
6. Tính checksum cho artifact.
7. Upload reports, logs, artifacts và checksum với build ID.

Lệnh build:

    mvn -B -ntp clean verify

Đầu ra cần lưu:

    target/surefire-reports/**
    target/failsafe-reports/**
    **/target/surefire-reports/**
    **/target/failsafe-reports/**
    **/target/*.jar
    **/target/*.war
    build.log

Trong multi-module, glob cần phù hợp với cấu trúc repository và tránh upload artifact trung gian không cần thiết. Có thể tạo thư mục evidence riêng để sao chép đúng các file cần lưu trước khi upload.

### Ví dụ PowerShell gom evidence

    New-Item -ItemType Directory -Force -Path 'evidence\reports' | Out-Null
    New-Item -ItemType Directory -Force -Path 'evidence\artifacts' | Out-Null
    Get-ChildItem -Path . -Directory -Recurse -Filter surefire-reports |
        ForEach-Object {
            Copy-Item -Path $_.FullName -Destination 'evidence\reports' -Recurse -Force
        }

Đoạn lệnh minh họa việc thu thập report; trong dự án thực tế cần giữ tên module để không ghi đè thư mục trùng tên. Cũng cần xử lý Failsafe report và chỉ sao chép artifact cuối được phát hành.

Nếu Maven thất bại ở test, bước upload report/log vẫn phải chạy. Artifact phát hành có thể không tồn tại hoặc không được publish; pipeline nên phân biệt rõ bằng chứng chẩn đoán với artifact đủ điều kiện phát hành.

## 18. Ví dụ pipeline Gradle tổng quát

Lệnh:

    ./gradlew clean build --console=plain --stacktrace

Đầu ra thường cần lưu:

    **/build/reports/tests/**
    **/build/test-results/**
    **/build/libs/*.jar
    build.log

Với multi-project build, cần thu thập report từ tất cả module hoặc suite bắt buộc. Nếu một task test thất bại, Gradle thường vẫn ghi report cho những test đã thực hiện. Bước upload cần chạy ngay cả khi lệnh build trả về mã khác 0.

### Ví dụ PowerShell thu thập report

    New-Item -ItemType Directory -Force -Path 'evidence\reports' | Out-Null
    Get-ChildItem -Path . -Directory -Recurse -Filter test-results |
        ForEach-Object {
            $destination = Join-Path 'evidence\reports' $_.Parent.Name
            Copy-Item -Path $_.FullName -Destination $destination -Recurse -Force
        }

Đây là ví dụ cơ bản; nếu nhiều project có cùng tên, cần dùng đường dẫn project đầy đủ hoặc task name để tránh đè kết quả. HTML reports cũng cần được sao chép nếu muốn lưu bản dễ đọc cho người dùng.

## 19. Upload artifact ngay cả khi build thất bại

Một lỗi CI phổ biến là bước upload chỉ chạy khi build thành công. Khi test fail, pipeline dừng trước khi lưu report và log, khiến bằng chứng quan trọng nhất bị mất.

Nên tách:

- Bước build/test: giữ exit code chính xác.
- Bước thu thập và upload evidence: chạy với điều kiện luôn thực hiện sau bước build, kể cả khi build thất bại hoặc bị hủy nếu nền tảng hỗ trợ.
- Bước publish/deploy: chỉ chạy khi các gate bắt buộc thành công.

### Ví dụ GitHub Actions

    - name: Build and test
      run: ./gradlew clean build --console=plain --stacktrace

    - name: Upload test reports and logs
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: evidence-${{ github.run_id }}-${{ github.run_attempt }}
        path: |
          **/build/reports/tests/**
          **/build/test-results/**
          build.log
        if-no-files-found: warn

Điều kiện always() giúp bước upload chạy sau khi bước trước thất bại. Tên artifact gắn với run ID và attempt để tránh trùng giữa các lần chạy lại.

Ví dụ chỉ minh họa cách tổ chức; cần kiểm tra glob, working directory và phiên bản action phù hợp với repository. Nếu build log chưa được ghi vào build.log, cần thêm bước capture log hoặc dùng console log của nền tảng.

### Ví dụ GitLab CI

    build_and_test:
      script:
        - ./gradlew clean build --console=plain --stacktrace
      artifacts:
        when: always
        paths:
          - '**/build/reports/tests/'
          - '**/build/test-results/'
          - build.log
        reports:
          junit:
            - '**/build/test-results/test/*.xml'

when: always giúp giữ artifact kể cả khi job thất bại. reports:junit cho phép GitLab hiển thị test report nếu XML khớp định dạng và đường dẫn. Cần điều chỉnh path theo cấu trúc module thực tế.

### Không biến upload thành cách che lỗi

Không dùng:

    ./gradlew build || true

chỉ để pipeline tiếp tục upload. Cách này làm mất trạng thái thất bại của build nếu không có bước kiểm tra khác khôi phục exit code.

Hãy để build/test thất bại đúng cách, dùng điều kiện always cho bước lưu evidence, và giữ publish/deploy ở nhánh chỉ chạy khi build pass.

## 20. Tách bằng chứng test khỏi artifact phát hành

Không phải mọi file được lưu đều được phép phát hành.

Ví dụ:

    evidence/
      reports/
      logs/
      metadata/
      dependency/
    release/
      application.jar
      SHA256SUMS
      provenance.json

Report, log và dependency tree là bằng chứng cho quá trình build. Artifact release là sản phẩm được phân phối. Có thể lưu chung trong cùng build record nhưng nên phân biệt loại, quyền truy cập và retention.

Nếu test thất bại, report và log vẫn cần lưu để điều tra, nhưng artifact không nhất thiết đủ điều kiện publish. Pipeline cần thể hiện rõ:

- Build/test status.
- Artifact generated hay không.
- Artifact approved for release hay không.
- Upload evidence status.

Không nên coi việc upload thành công là bằng chứng build thành công.

## 21. Metadata build để truy vết nguồn gốc

Báo cáo và log có ích hơn khi gắn với metadata:

- Build ID, pipeline ID và attempt.
- Repository URL hoặc tên project.
- Commit SHA và branch/tag.
- Thời điểm bắt đầu/kết thúc.
- Người hoặc hệ thống kích hoạt nếu chính sách cho phép.
- Hệ điều hành và architecture của runner.
- Phiên bản JDK.
- Phiên bản Gradle/Maven Wrapper.
- Lệnh build và task/phase.
- Profile hoặc build properties quan trọng.
- Trạng thái test.
- Tên artifact và checksum.

Ví dụ file build-info.txt:

    buildId=1842
    commit=7f3c2a1
    branch=main
    javaVersion=21
    buildTool=Gradle 8.x
    command=./gradlew clean build
    testStatus=PASSED
    artifact=application.jar
    checksumAlgorithm=SHA-256

Không ghi credential, token, private key, session cookie hoặc dữ liệu cá nhân không cần thiết vào metadata.

## 22. Lưu dependency evidence

Khi điều tra lỗi sau phát hành, chỉ biết commit và JAR có thể chưa đủ. Dependency graph giúp xác định thư viện và version mà build đã dùng.

Maven:

    mvn dependency:tree -DoutputFile=dependency-tree.txt
    mvn help:effective-pom -Doutput=effective-pom.xml

Gradle:

    ./gradlew dependencies --configuration runtimeClasspath
    ./gradlew dependencies --configuration testRuntimeClasspath

Có thể lưu:

- Dependency tree của compile/runtime/test configuration.
- Lockfile của Gradle nếu dự án dùng dependency locking.
- Effective POM hoặc thông tin BOM/version management của Maven.
- Version catalog và plugin version.

Các tệp này nên gắn cùng build ID và commit. Chúng giúp giải thích vì sao một máy chọn version hoặc variant cụ thể.

Không cần upload toàn bộ dependency cache hoặc local repository cho mọi build. Chúng có thể rất lớn, chứa nhiều dữ liệu không liên quan và khó truy vết. Thường nên lưu dependency report và metadata cần thiết thay vì toàn bộ cache.

## 23. Bảo vệ log và report khỏi lộ bí mật

Log và report có thể chứa:

- URL repository nội bộ.
- Đường dẫn workspace và tên máy.
- Tên người dùng hoặc thông tin môi trường.
- Dữ liệu request/response của integration test.
- Token hoặc password nếu build script in nhầm.
- Dữ liệu mẫu có thông tin cá nhân.
- Stack trace chứa thông tin hệ thống nội bộ.

Trước khi lưu ở nơi chia sẻ rộng, cần áp dụng:

- Secret masking trong CI.
- Không echo credential hoặc toàn bộ environment.
- Không bật debug vô thời hạn.
- Dùng dữ liệu giả hoặc đã ẩn danh cho test.
- Hạn chế quyền đọc report/log nhạy cảm.
- Mã hóa artifact khi lưu hoặc truyền nếu chính sách yêu cầu.
- Đặt retention phù hợp với mức nhạy cảm.

Không nên chỉnh sửa report gốc theo cách làm sai lệch bằng chứng. Nếu cần bản đã ẩn dữ liệu, hãy lưu bản redacted riêng và giữ quyền truy cập bản gốc theo chính sách bảo mật.

## 24. Retention và lưu trữ lâu dài

Không phải bằng chứng nào cũng cần lưu cùng thời gian.

| Dữ liệu | Retention gợi ý theo chính sách dự án | Lý do |
| --- | --- | --- |
| Log của build thường ngày | Ngắn đến trung bình | Điều tra lỗi gần thời điểm phát sinh |
| Test reports | Trung bình hoặc theo vòng đời release | Theo dõi xu hướng test và regression |
| Artifact release | Theo chính sách phát hành/sản phẩm | Khả năng rollback và tái triển khai |
| Checksum và provenance release | Dài hạn theo artifact | Truy nguyên và xác minh tính toàn vẹn |
| Debug log chi tiết | Ngắn và có kiểm soát | Có thể chứa thông tin nhạy cảm, dung lượng lớn |
| Báo cáo security/compliance | Theo yêu cầu tổ chức hoặc quy định | Audit và bằng chứng tuân thủ |

Các thời hạn cụ thể phải theo chính sách công ty, yêu cầu pháp lý và chi phí lưu trữ. Không nên áp dụng một thời hạn duy nhất cho tất cả loại dữ liệu.

Với release quan trọng, nên lưu artifact, checksum, metadata và bằng chứng kiểm thử trong kho có retention dài hơn build thử nghiệm. Dùng storage có versioning hoặc immutable retention nếu cần bảo vệ bằng chứng khỏi bị ghi đè/xóa.

## 25. Tên file và cấu trúc thư mục dễ truy vết

Một cấu trúc gợi ý:

    evidence/
      project-api/
        build-1842/
          metadata/
            build-info.json
            dependency-tree.txt
          reports/
            unit/
              module-api/
              module-service/
            integration/
              module-api/
          logs/
            build.log
            test-service.log
          artifacts/
            application.jar
            SHA256SUMS
            provenance.json

Tên thư mục nên có build ID hoặc pipeline attempt. Nếu cùng một job chạy trên nhiều JDK/OS, thêm matrix dimension vào đường dẫn.

Tránh:

- Ghi mọi report vào cùng một thư mục phẳng.
- Dùng tên file cố định trên storage dùng chung.
- Ghi đè artifact của build cũ bằng build mới.
- Đặt report của retry lên report của lần chạy đầu.
- Chỉ lưu link đến workspace tạm đã bị CI xóa.

## 26. Xác minh checksum khi tải artifact

Khi artifact được tải về môi trường staging hoặc production, hãy xác minh digest trước khi triển khai.

Linux:

    sha256sum -c SHA256SUMS

macOS:

    shasum -a 256 -c SHA256SUMS

Windows PowerShell:

    $expected = '8F2C...A2'
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath '.\application.jar').Hash
    if ($actual -ne $expected) {
        throw 'Artifact checksum verification failed'
    }

Nếu checksum không khớp:

1. Dừng triển khai artifact đó.
2. Kiểm tra file tải xuống có bị hỏng hoặc copy thiếu không.
3. Xác nhận manifest thuộc đúng build ID và artifact path.
4. Tải lại từ kho artifact đáng tin cậy.
5. Kiểm tra log upload/download và quyền ghi storage.
6. Điều tra khả năng artifact hoặc manifest bị thay đổi.

Không cập nhật manifest bằng digest của file không rõ nguồn chỉ để bỏ qua lỗi. Cần xác định artifact nào là bản được build và phê duyệt.

## 27. Checksum, chữ ký và provenance

Ba khái niệm này bổ sung cho nhau:

- **Checksum:** kiểm tra bytes có khớp digest đã biết không.
- **Digital signature:** xác thực rằng nội dung hoặc metadata được ký bởi chủ thể giữ khóa ký tương ứng.
- **Build provenance/attestation:** mô tả artifact được tạo từ source, builder, workflow và tham số nào.

Một checksum đơn lẻ không cho biết ai đã build artifact. Một chữ ký xác nhận người ký nhưng không tự mô tả đầy đủ môi trường build. Provenance giúp kết nối artifact với nguồn và quy trình.

Với release quan trọng, có thể lưu:

    application.jar
    SHA256SUMS
    SHA256SUMS.sig
    provenance.json
    test-reports/

Chữ ký cần được xác minh bằng public key hoặc hệ thống tin cậy đã được phân phối độc lập. Không lưu private signing key trong artifact hoặc log.

## 28. Khi build thất bại ở các giai đoạn khác nhau

Pipeline nên lưu bằng chứng phù hợp với giai đoạn:

| Giai đoạn thất bại | Bằng chứng cần giữ |
| --- | --- |
| Dependency resolution | Build log, effective settings/POM hoặc Gradle dependency diagnostics |
| Compile | Compiler log, source/test compile task output, toolchain metadata |
| Unit test | Surefire/Gradle test XML, HTML report, test worker log |
| Integration test | Failsafe report, service/container log, test environment metadata |
| Package | Build log, artifact nếu đã tạo, manifest/checksum nếu artifact hoàn chỉnh |
| Upload/publish | Artifact local, checksum, upload log và remote object identifier |
| Deploy/startup | Artifact checksum, deploy log, startup log và runtime metadata |

Không phải giai đoạn nào cũng có đủ artifact cuối. Ví dụ compile thất bại thì không có JAR phát hành hợp lệ, nhưng build log và compiler diagnostics vẫn phải được lưu.

Nếu bước checksum chưa chạy vì build thất bại trước khi package, không nên tạo một manifest giả. Metadata nên thể hiện artifact chưa được tạo hoặc checksum chưa có.

## 29. Xử lý retry và flaky test

Một test có thể fail ở lần đầu và pass khi retry. Nếu chỉ giữ report cuối, nhóm có thể mất bằng chứng cho lần fail ban đầu.

Khi có retry:

- Lưu kết quả lần chạy đầu.
- Lưu kết quả retry riêng.
- Ghi số lần thử và lý do retry.
- Giữ test name, module và commit nhất quán.
- Phân biệt test flaky với test đã pass ổn định.

Không ghi đè report của attempt 1 bằng attempt 2. Dùng tên như:

    reports/attempt-1/
    reports/attempt-2/

Hoặc metadata tương ứng. Tổng hợp cuối có thể cho biết kết quả cuối cùng, nhưng cần giữ dữ liệu gốc để phân tích độ ổn định.

## 30. Tự động kiểm tra evidence trước khi upload

Một pipeline có thể kiểm tra:

- Có report XML cho những suite bắt buộc không?
- Report có số test hợp lý hay không?
- Có test fail hoặc skipped bất thường không?
- Build log có được tạo và không rỗng không?
- Artifact mong đợi có tồn tại không?
- Checksum có được tạo sau khi artifact hoàn tất không?
- Manifest có liệt kê đúng artifact không?
- Tất cả file evidence có thuộc cùng build ID không?

Không nên dùng một kiểm tra chung kiểu “có ít nhất một XML” cho toàn bộ dự án. Một module quan trọng có thể không chạy test trong khi module khác tạo report. Nên xác định suite/module bắt buộc và kiểm tra theo phạm vi.

Nếu một module được phép không có test, hãy ghi rõ ngoại lệ. Điều quan trọng là không để build xanh khi test bắt buộc không chạy.

## 31. Ví dụ cấu trúc pipeline đầy đủ

Một quy trình tổng quát có thể được tổ chức như sau:

    Checkout source
         |
         v
    Capture build metadata
         |
         v
    Run compile and tests
         |
         +----> Save console log
         |
         +----> Generate test reports
         |
         v
    If successful: package final artifact
         |
         v
    Inspect artifact and create checksum
         |
         v
    Build evidence manifest
         |
         v
    Upload evidence (always)
         |
         v
    Verify artifact/checksum
         |
         v
    Publish/deploy only if gates pass

Điểm quan trọng:

- Lưu log và test report ngay cả khi test thất bại.
- Chỉ publish artifact khi các gate phát hành thành công.
- Tạo checksum cho file cuối cùng sau mọi bước thay đổi.
- Gắn mọi đầu ra với build ID, commit và attempt.
- Giữ exit code gốc của build.
- Upload evidence bằng bước luôn chạy sau build.

## 32. Checklist cho một lần build có thể truy vết

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Build từ commit nào? | Commit SHA, branch/tag |
| Dùng công cụ nào? | JDK, Maven/Gradle Wrapper, OS |
| Lệnh nào được chạy? | Command/task/phase trong metadata và log |
| Test nào đã chạy? | JUnit XML và HTML report |
| Có test fail/skip không? | Counts và danh sách test trong report |
| Build lỗi ở đâu? | Console/build log và stack trace |
| Artifact nào được tạo? | Tên, kích thước, đường dẫn và build ID |
| Artifact có nguyên vẹn không? | SHA-256 manifest và kết quả xác minh |
| Artifact đến từ build nào? | Metadata/provenance |
| Có thể truy cập lại bằng chứng không? | CI artifact store, retention và quyền truy cập |
| Log có lộ bí mật không? | Kiểm soát masking, redaction và access policy |

## 33. Những sai lầm thường gặp

### Chỉ lưu report khi build thành công

Khi test fail, report là bằng chứng quan trọng nhất. Bước upload cần chạy cả khi build thất bại.

### Chỉ lưu log console trên giao diện CI

Job có thể hết retention hoặc log khó tìm. Với release và sự cố quan trọng, lưu log thành artifact gắn build ID.

### Chỉ upload report ở root project

Multi-module build thường có report trong từng module. Cần thu thập đúng toàn bộ đường dẫn.

### Dùng report cũ

Thư mục output còn từ lần trước có thể làm CI upload sai kết quả. Dùng workspace sạch hoặc kiểm tra thời gian và build ID.

### Tính checksum trước bước repackage

Checksum sẽ không còn khớp artifact cuối. Tính sau mọi bước thay đổi nội dung.

### Nghĩ checksum chứng minh artifact đáng tin cậy

Checksum chỉ xác nhận bytes khớp digest. Cần bảo vệ digest hoặc dùng chữ ký/provenance để xác thực nguồn.

### Ghi đè bằng chứng của lần retry

Giữ report/log riêng cho từng attempt và tạo bản tổng hợp nếu cần.

### Làm build luôn thành công để upload report

Không che exit code. Upload evidence phải là bước riêng chạy theo điều kiện always.

### Lưu debug log mà không kiểm soát quyền

Debug log có thể chứa URL nội bộ, property và dữ liệu nhạy cảm. Hạn chế mức log, quyền đọc và thời hạn lưu.

## 34. Nguyên tắc thực hành

- Gắn artifact, report, log, checksum và metadata với một build ID duy nhất.
- Lưu cả JUnit XML và HTML report nếu cần máy đọc lẫn người đọc.
- Thu thập Surefire, Failsafe và Gradle reports từ mọi module/suite liên quan.
- Upload report và log ngay cả khi test hoặc build thất bại.
- Giữ nguyên exit code của build để CI phản ánh đúng kết quả.
- Ghi log dễ đọc cho CI; chỉ bật debug khi cần và bảo vệ dữ liệu nhạy cảm.
- Tính SHA-256 sau khi artifact đã được hoàn tất, repackage hoặc ký.
- Xác minh checksum trước khi triển khai hoặc phân phối.
- Lưu manifest có tên, kích thước, digest, commit và build ID.
- Giữ retry report riêng và không ghi đè bằng chứng gốc.
- Đặt retention và quyền truy cập theo loại dữ liệu.
- Dùng chữ ký/provenance khi cần xác thực nguồn phát hành, không chỉ kiểm tra checksum.

Lưu báo cáo kiểm thử, log và checksum giúp mỗi lần build có thể được giải thích và truy nguyên sau khi pipeline kết thúc. Report cho biết chất lượng kiểm thử, log cho biết quá trình thực thi và nguyên nhân lỗi, còn checksum giúp xác nhận artifact không bị thay đổi. Khi tất cả được gắn với cùng build ID, lưu trong kho có retention và quyền truy cập phù hợp, nhóm có thể điều tra sự cố, xác minh artifact và tái hiện quá trình phát hành đáng tin cậy hơn.

# Tránh phụ thuộc công cụ khi thiết kế lệnh build và kiểm thử cốt lõi

## 1. Vì sao cần tách lệnh cốt lõi khỏi công cụ CI?

Một dự án có thể chạy build và test trên máy lập trình viên, trong CI, trong container hoặc trên một máy build độc lập. Nếu logic build và kiểm thử chỉ tồn tại trong cấu hình của một nền tảng CI, việc chạy lại ở môi trường khác sẽ khó khăn.

Ví dụ, pipeline có thể chứa hàng chục bước shell, lệnh cài dependency, điều kiện theo branch, cách ghép tham số test và quy tắc tạo artifact. Người phát triển muốn tái hiện lỗi phải tự tìm đúng các bước trong giao diện CI, sao chép lệnh và đoán các biến môi trường mà pipeline đã cung cấp.

Cách thiết kế bền vững là đặt các lệnh build và test cốt lõi trong repository, sử dụng build tool và wrapper được quản lý cùng mã nguồn. CI chỉ điều phối các lệnh đó: lấy source, chuẩn bị môi trường, cung cấp credential, chạy command, lưu kết quả và quyết định bước phát hành tiếp theo.

Mục tiêu là cùng một command có thể chạy ở máy lập trình viên và trong CI với cùng ý nghĩa. Nền tảng CI có thể thay đổi mà quy trình build/test của dự án vẫn sử dụng được.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, cách tiếp cận này hỗ trợ pipeline dưới dạng mã, khả năng tái lập, truy vết và kiểm thử trước khi phát hành. Nó cũng giúp phân biệt lỗi của dự án với lỗi do runner, plugin hoặc cấu hình riêng của một nền tảng CI.

## 2. Phân biệt logic dự án và logic điều phối

Không phải mọi bước trong pipeline đều cần nằm trong repository. Cần phân biệt hai nhóm trách nhiệm.

| Nhóm | Trách nhiệm | Ví dụ |
|---|---|---|
| Lệnh cốt lõi của dự án | Xác định cách build, test, lint, package và kiểm tra chất lượng | mvnw verify, gradlew check, npm test |
| Điều phối CI | Chọn lúc chạy, runner, matrix, quyền, cache và artifact transfer | Trigger theo PR, cấp JDK, upload report, chờ approval |
| Vận hành phát hành | Triển khai, xác minh, rollback và ghi release record | Deploy artifact digest, canary, smoke test |
| Hạ tầng CI | Cung cấp worker, network, credential và dịch vụ hỗ trợ | Runner image, secret store, concurrency group |

Quy tắc hữu ích:

- Nếu một bước xác định chất lượng hoặc tính đúng đắn của mã nguồn, hãy đặt logic ở repository hoặc công cụ build của dự án.
- Nếu một bước quyết định khi nào và ở đâu chạy, quyền nào được cấp hoặc kết quả được lưu ở đâu, đó thường là trách nhiệm điều phối.
- Nếu một thao tác cần thay đổi môi trường thật, hãy tách thành command/deployment workflow có hợp đồng và quyền rõ ràng.

Ví dụ, kiểm tra unit test nên là task của build tool. Việc chạy task đó trên mỗi pull request là quyết định của CI. Upload JUnit report là tích hợp của CI với kết quả do build tool tạo ra.

## 3. Thiết kế command contract rõ ràng

Một command cốt lõi là giao diện giữa repository, lập trình viên và hệ thống tự động hóa. Giao diện này cần ổn định và dễ hiểu.

Một command contract nên xác định:

1. **Tên và mục đích:** command làm gì, không làm gì.
2. **Working directory:** chạy từ thư mục nào.
3. **Inputs:** tham số, biến môi trường, file cấu hình và phiên bản toolchain.
4. **Outputs:** artifact, report, log và file trung gian.
5. **Exit code:** điều kiện thành công và thất bại.
6. **Side effects:** có ghi file, gọi mạng, sửa database hoặc deploy không.
7. **Thời gian và tài nguyên:** có timeout, concurrency hoặc giới hạn bộ nhớ không.
8. **Tính lặp lại:** chạy lại có tạo trạng thái sai hoặc nhân đôi dữ liệu không.

Ví dụ hợp đồng cho lệnh kiểm tra Java:

~~~text
Command: ./mvnw -B -ntp verify

Working directory:
  thư mục gốc repository

Inputs:
  source code, pom.xml, Maven Wrapper, JDK được khai báo

Outputs:
  target/*.jar (nếu cấu hình package)
  target/surefire-reports/
  target/failsafe-reports/ (nếu có cấu hình integration test)

Exit code:
  0: các phase tới verify hoàn tất
  khác 0: build hoặc một bước kiểm tra thất bại

Side effects:
  tạo file trong target/
  tải dependency nếu chưa có trong local cache
~~~

Một command không cần quá nhiều tham số để trở nên linh hoạt. Hãy giữ các tùy chọn phổ biến ở mức dễ dùng, còn những trường hợp đặc biệt có thể được biểu diễn bằng task hoặc profile có tên rõ ràng.

## 4. Repository là nguồn sự thật của build và test

Các quy tắc cần thiết để tái tạo build nên được version hóa cùng repository:

- Build descriptor như pom.xml, build.gradle.kts hoặc package.json.
- Wrapper và cấu hình phiên bản build tool.
- Cấu hình JDK/toolchain hoặc runtime cần thiết.
- Dependency lockfile và quy tắc kiểm tra dependency.
- Script hỗ trợ có thể chạy độc lập.
- Test configuration, fixture và test data phù hợp.
- Cấu hình formatter, linter, static analysis và coverage.
- Hướng dẫn command chuẩn trong tài liệu dự án.

Nếu command chỉ tồn tại trong Jenkinsfile hoặc cấu hình workflow của một nhà cung cấp, lập trình viên có thể không biết cách chạy đúng ở máy cá nhân. Khi đó CI trở thành nơi duy nhất hiểu cách build dự án.

CI vẫn cần cấu hình riêng, nhưng phần cốt lõi của build/test nên có thể đọc, review, version hóa và chạy bên ngoài CI.

## 5. Dùng wrapper thay vì phụ thuộc tool cài toàn máy

Wrapper giúp repository kiểm soát phiên bản build tool mà dự án sử dụng. Người chạy không cần cài đúng phiên bản Maven hoặc Gradle toàn cục.

Với Maven, dùng Maven Wrapper:

- Unix-like: ./mvnw
- Windows: .\mvnw.cmd

Với Gradle, dùng Gradle Wrapper:

- Unix-like: ./gradlew
- Windows: .\gradlew.bat

Wrapper thường tải distribution đã được cấu hình nếu máy chưa có. Vì vậy, cần version hóa wrapper files và kiểm tra URL/distribution checksum theo khả năng của công cụ.

Với repository chạy trên Unix-like, cần giữ executable bit của file mvnw trong Git để người dùng có thể gọi trực tiếp. Nên bật xác minh checksum của distribution nếu wrapper hỗ trợ và review thay đổi wrapper như một thay đổi toolchain có ảnh hưởng tới toàn bộ build.

Không nên giả định mọi máy đều có mvn, gradle hoặc phiên bản giống nhau. Lệnh gọi tool toàn cục có thể chạy được trên một runner đã cài sẵn nhưng thất bại ở máy mới hoặc dùng phiên bản khác.

### 5.1. Ghim phiên bản toolchain

Wrapper kiểm soát phiên bản build tool, nhưng chưa tự kiểm soát toàn bộ môi trường. Cần quản lý cả:

- JDK hoặc runtime version.
- Compiler target/release.
- Node.js, Python hoặc tool phụ trợ nếu có.
- Phiên bản formatter, linter và scanner.
- Dependency và plugin version.
- Container image digest nếu build dựa trên container.

Với Gradle Java toolchain, có thể khai báo:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Với Maven, có thể dùng cấu hình compiler plugin để đặt release phù hợp và dùng Maven Toolchains khi cần chọn JDK cụ thể. Cần đảm bảo CI và máy phát triển đều có thể cung cấp toolchain đã khai báo.

Không nên chỉ dựa vào JAVA_HOME đang trỏ tới bất kỳ JDK nào trên runner mà không kiểm tra version trước khi build.

## 6. Đặt tên task theo mục đích thay vì theo nền tảng CI

Command nên mô tả việc dự án cần làm:

~~~text
./mvnw test
./mvnw verify
./gradlew test
./gradlew check
./gradlew build
~~~

Tên task nên có ý nghĩa với người làm dự án. Tránh tạo task như jenkinsBuild, githubActionTest hoặc azureReleaseCheck cho logic cốt lõi nếu mục tiêu thực tế là compile, test, lint hay package.

Nếu cần lệnh tổng hợp, có thể định nghĩa task chuẩn:

- check: kiểm tra chất lượng và chạy test cần thiết.
- test: chạy test suite được cấu hình.
- build: tạo artifact và thực hiện các kiểm tra build.
- integrationTest: chạy nhóm integration test riêng nếu dự án có cấu hình.
- verify: thực hiện các bước xác minh trước khi artifact được chấp nhận.

Tên và ý nghĩa cụ thể phụ thuộc build tool. Cần ghi rõ dự án định nghĩa task nào và CI phải gọi task nào.

## 7. Giữ logic trong build tool hoặc script có thể tái sử dụng

Một pipeline dễ bảo trì thường gọi một số ít command đã được định nghĩa trong repository.

Ví dụ, thay vì viết nhiều lệnh Maven riêng trong workflow:

~~~yaml
steps:
  - run: ./mvnw -B -ntp clean
  - run: ./mvnw -B -ntp compile
  - run: ./mvnw -B -ntp test
  - run: ./mvnw -B -ntp package
~~~

có thể dùng một command tổng hợp nếu đó là hợp đồng build của dự án:

~~~yaml
steps:
  - run: ./mvnw -B -ntp verify
~~~

Cách này giảm nguy cơ pipeline quên một phase hoặc chạy các bước theo thứ tự khác với cách nhóm lập trình viên kiểm tra tại local.

Không phải lúc nào một command duy nhất cũng là tốt nhất. Integration test cần database hoặc service phụ trợ có thể phải chạy ở job riêng. Khi đó, hãy định nghĩa task rõ ràng trong build tool và để CI chuẩn bị dependency rồi gọi task tương ứng.

## 8. Tránh phụ thuộc biến môi trường riêng của CI

Một script build không nên âm thầm phụ thuộc vào các biến chỉ tồn tại trên một nền tảng, chẳng hạn tên branch, run number hoặc workspace path của CI vendor.

Thay vào đó:

- Đưa tham số cần thiết qua command-line argument hoặc biến môi trường có tên do dự án định nghĩa.
- Cung cấp default an toàn khi có thể.
- Kiểm tra input bắt buộc và thông báo lỗi rõ ràng.
- Không suy ra môi trường deploy từ tên máy runner.
- Không để logic test thay đổi chỉ vì biến CI vô tình tồn tại.

Ví dụ, nếu integration test cần URL service:

~~~text
APP_BASE_URL=http://localhost:8080 ./mvnw -B -ntp -Pintegration verify
~~~

Trên Windows PowerShell:

~~~powershell
$env:APP_BASE_URL = "http://localhost:8080"
.\mvnw.cmd -B -ntp -Pintegration verify
~~~

Tên biến môi trường do dự án định nghĩa và có ý nghĩa ngoài CI. Pipeline chỉ truyền giá trị tương ứng.

Nếu command cần biết build đang chạy trên CI để điều chỉnh log hoặc report location, hãy dùng một biến tùy chọn có documented behavior. Không để biến đó thay đổi semantics của test mà không có chủ đích.

## 9. Viết script portable và kiểm soát shell

Một script chỉ chạy trên Bash có thể thất bại trên PowerShell hoặc shell mặc định của runner khác. Các khác biệt thường gặp gồm:

- Cách đặt biến môi trường.
- Cách nối command.
- Dấu nháy và escape.
- Cách xử lý exit code.
- Path separator.
- Wildcard expansion.
- Working directory.
- Encoding và line ending.

Nếu cần script shell, hãy chọn shell rõ ràng và ghi trong script. Nếu cần hỗ trợ nhiều hệ điều hành, có thể dùng script riêng cho POSIX và PowerShell với cùng hợp đồng, hoặc dùng ngôn ngữ đa nền tảng như Python/Node khi runtime đã được quản lý.

Không nên viết một script phức tạp trong YAML nhiều tầng quoting. Đưa logic vào file có thể lint, test và review dễ hơn.

### 9.1. Xử lý đường dẫn và working directory

Tránh hard-code đường dẫn tuyệt đối do runner cấp như C:/agent/work/project hoặc /home/runner/work/project. Dùng đường dẫn tương đối với repository root hoặc xác định root từ vị trí script.

Các nguyên tắc:

- Dùng API xử lý đường dẫn của ngôn ngữ thay vì tự ghép dấu phân cách theo hệ điều hành.
- Quote đường dẫn có dấu cách.
- Xác định rõ command được chạy từ repository root hay module directory.
- Không phụ thuộc vào shell tự expand wildcard.
- Không giả định workspace sạch nếu CI có thể tái sử dụng runner.

Một command chuẩn phải có working directory được tài liệu hóa. Nếu dự án là monorepo, mỗi module có thể có command riêng và root command có thể điều phối các module.

## 10. Exit code là hợp đồng máy có thể hiểu

CI thường quyết định pass/fail dựa trên exit code. Vì vậy, command phải trả exit code đúng với kết quả.

Quy ước thông thường:

- 0: thành công.
- Khác 0: có lỗi hoặc điều kiện không đạt.

Một script không được in thông báo "Tests failed" nhưng vẫn kết thúc với exit code 0. Tương tự, không nên bỏ qua exit code của command con bằng cách ghi đè kết quả cuối.

Ví dụ shell:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

./mvnw -B -ntp verify
~~~

Với script PowerShell:

~~~powershell
& .\mvnw.cmd -B -ntp verify
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

Các ví dụ trên thể hiện cách truyền lỗi từ build tool ra caller. Với Bash, cần hiểu hành vi set -e trong các cấu trúc điều kiện, pipeline và command substitution; không nên coi nó là cơ chế xử lý lỗi hoàn chỉnh cho mọi tình huống.

Không nên dùng || true để làm pipeline xanh khi test hoặc scanner thất bại, trừ khi kết quả đó được phân loại rõ là non-blocking và vẫn được lưu lại.

## 11. Tách các tầng kiểm thử theo chi phí và mục đích

Không phải mọi lần chạy đều cần toàn bộ test suite. Tuy nhiên, tiêu chí pass của release phải rõ ràng.

Một cách phân tầng:

| Tầng | Nội dung | Khi thường chạy |
|---|---|---|
| Fast checks | Format, lint, compile, unit test nhanh | Local và mỗi PR |
| Integration tests | Database, queue, API hoặc service phụ trợ | PR phù hợp và CI |
| Contract tests | Tương thích API/event giữa producer và consumer | PR/release |
| End-to-end tests | Luồng nghiệp vụ xuyên hệ thống | CI trước release hoặc môi trường kiểm thử |
| Security/quality checks | SAST, SCA, secret scan, license và policy | PR, merge, scheduled hoặc release |
| Smoke tests | Xác minh artifact đang chạy sau deploy | Sau triển khai |

Lệnh local cần cho phép chạy từng tầng. Pipeline có thể ghép các tầng thành job hoặc stage theo thời gian và tài nguyên.

Không nên đặt toàn bộ kiểm thử trong một script duy nhất không có cách chọn nhóm. Cũng không nên tạo quá nhiều command trùng lặp làm người dùng không biết lệnh nào là chuẩn.

## 12. Kiểm thử cần độc lập với thứ tự và môi trường

Test suite tốt cần tránh phụ thuộc vào:

- Thứ tự test được runner chọn.
- File còn sót từ lần chạy trước.
- Database dùng chung mà test khác có thể sửa.
- Port cố định đã bị tiến trình khác chiếm.
- Thời gian hệ thống hoặc timezone không được kiểm soát.
- Network service không được quản lý.
- Secret cá nhân có trên máy lập trình viên.

Cần tạo fixture có thể tái tạo, dọn tài nguyên sau test và phân vùng dữ liệu theo từng test hoặc worker. Với test cần service phụ trợ, nên mô tả cách khởi động dependency và cách xác minh nó sẵn sàng.

Test flaky không nên được che bằng retry vô hạn. Có thể có retry giới hạn để phân loại lỗi hạ tầng, nhưng lần retry và kết quả ban đầu phải được ghi nhận để nhóm sửa nguyên nhân.

## 13. Quản lý dependency và cache mà không làm sai kết quả

Dependency cache giúp build nhanh nhưng không nên là điều kiện để build thành công.

Các nguyên tắc:

- Version hóa dependency declaration.
- Dùng lockfile khi hệ sinh thái hỗ trợ.
- Ghim plugin/tool version.
- Dùng dependency verification/checksum khi phù hợp.
- Cache theo key chứa thông tin toolchain và dependency state.
- Có thể build từ cache rỗng.
- Không lưu secret trong cache.
- Không dùng cache làm nơi lưu artifact phát hành.

Cache là tối ưu hiệu năng, không phải nguồn sự thật. Nếu build chỉ thành công khi cache cũ còn tồn tại, quy trình chưa đủ tái lập.

CI nên có cách chạy clean hoặc cache miss định kỳ để phát hiện dependency không được khai báo, nhưng không nhất thiết xóa cache trong mọi job vì sẽ làm chậm pipeline.

## 14. Kiểm soát đầu ra: artifact và report

Command cốt lõi cần tạo output ở vị trí và định dạng ổn định.

Ví dụ:

- Maven: target/.
- Gradle: build/.
- JUnit XML: vị trí report do plugin/build tool cấu hình.
- Coverage: JaCoCo hoặc định dạng tương ứng.
- Package: JAR, WAR, ZIP hoặc container image.

CI có thể upload report hoặc artifact, nhưng không nên tự suy luận đường dẫn bằng cách quét toàn bộ workspace nếu dự án có thể công bố output contract rõ ràng.

Phân biệt:

- **Temporary output:** file có thể tái tạo, thường được dọn sau build.
- **Test evidence:** report cần lưu theo retention policy.
- **Release artifact:** output bất biến được publish và định danh bằng version/digest.
- **Cache:** dữ liệu có thể tạo lại để tăng tốc.

Không build lại ở từng môi trường nếu mục tiêu là triển khai cùng một artifact đã được kiểm thử. Build một lần, publish theo digest, sau đó promote artifact đó qua các môi trường.

## 15. Không trộn build, test và deploy vào một command mơ hồ

Một command release có thể nghe tiện lợi nhưng nếu nó vừa build, vừa test, vừa publish, vừa deploy production thì khó biết bước nào đã xảy ra khi có lỗi giữa chừng.

Nên phân chia trách nhiệm:

~~~text
validate:
  compile + lint + unit/integration checks

package:
  tạo artifact từ source đã được xác minh

publish:
  đưa artifact bất biến lên repository

deploy:
  triển khai artifact digest đã được phê duyệt

verify:
  smoke test và kiểm tra tín hiệu sau deploy
~~~

Có thể tạo command tổng hợp để gọi các bước trên trong một môi trường, nhưng từng bước vẫn cần có trạng thái, output và lỗi riêng.

Đặc biệt, lệnh build/test cốt lõi không nên tự triển khai production hoặc thay đổi tài nguyên cloud chỉ vì biến môi trường đang có sẵn. Side effect phát hành cần một workflow có quyền và phê duyệt riêng.

## 16. Truyền cấu hình và secret qua giao diện rõ ràng

Command build/test đôi khi cần token để tải dependency riêng hoặc kết nối dịch vụ kiểm thử. Không nên hard-code credential trong script hoặc commit vào repository.

Nên:

- Đọc secret từ secret manager hoặc biến môi trường được CI cấp.
- Kiểm tra biến bắt buộc trước khi chạy.
- Không in giá trị secret ra log.
- Không đưa secret vào command-line argument nếu process list hoặc log có thể lộ.
- Dùng credential có phạm vi và thời hạn tối thiểu.
- Phân biệt cấu hình không nhạy cảm với secret.
- Cho phép chạy local bằng cách cung cấp credential riêng theo hướng dẫn bảo mật.

Một command nên báo tên biến còn thiếu, nhưng không được in giá trị của biến. Test cốt lõi cũng nên dùng fake credential hoặc service giả lập nếu không cần truy cập hệ thống thật.

## 17. Ví dụ Java với Maven Wrapper

Một dự án Maven có thể định nghĩa command chuẩn như sau:

~~~text
# Kiểm tra unit test
./mvnw -B -ntp test

# Chạy toàn bộ các phase xác minh tới verify
./mvnw -B -ntp verify

# Windows PowerShell
.\mvnw.cmd -B -ntp verify
~~~

-B bật batch mode, phù hợp với môi trường tự động hóa. -ntp tắt transfer progress trong các phiên bản Maven hỗ trợ tùy chọn này (Maven 3.6.1 trở lên), giúp log gọn hơn.

Maven Surefire thường chạy unit test trong phase test. Nếu dự án cấu hình Maven Failsafe, integration test thường được chạy ở các phase integration-test và verify. Chỉ gọi verify sẽ thực hiện integration test khi plugin và lifecycle đã được cấu hình đúng.

Ví dụ cấu hình compiler plugin cần đặt Java release rõ ràng. Phiên bản plugin nên được quản lý trong pom.xml, không dựa vào plugin version mặc định thay đổi theo môi trường.

Không nên dùng -DskipTests trong gate phát hành nếu yêu cầu là test phải chạy. Cờ này bỏ qua việc thực thi test; maven.test.skip còn có thể bỏ cả compile test tùy cách dùng. Nếu có job chỉ compile/package để chẩn đoán, hãy đặt tên và phân loại rõ để kết quả không bị hiểu nhầm là quality gate đầy đủ.

## 18. Ví dụ Java với Gradle Wrapper

Với Gradle, có thể dùng:

~~~text
# Chạy test
./gradlew test

# Chạy các kiểm tra chuẩn được gắn vào check
./gradlew check

# Build artifact
./gradlew build

# Windows PowerShell
.\gradlew.bat check
~~~

Gradle Wrapper định nghĩa distribution version trong gradle/wrapper/gradle-wrapper.properties. Cần version hóa wrapper scripts và file cấu hình này.

Task check phụ thuộc vào các task kiểm tra mà plugin và build script đã đăng ký, thường bao gồm test của Java plugin. Nếu dự án có integration test source set riêng, cần đăng ký task và dependency vào lifecycle phù hợp.

Không nên cho rằng task check tự động chạy mọi kiểm tra mà nhóm kỳ vọng. Hãy đọc build script và xác minh task graph, test report cùng exit code. Có thể dùng ./gradlew tasks hoặc ./gradlew check --dry-run để hiểu cấu trúc task; không nên dùng dry-run như bằng chứng test đã chạy.

## 19. Ví dụ pipeline chỉ điều phối command của repository

Một pipeline tổng quát có thể thể hiện:

~~~yaml
jobs:
  verify_and_package:
    steps:
      - checkout_source
      - setup_declared_jdk
      - restore_dependency_cache
      - run: ./mvnw -B -ntp verify
      - upload: target/surefire-reports/
      - upload_if_present: target/failsafe-reports/
      - publish: target/*.jar
~~~

Đây là YAML giả lập để giải thích trách nhiệm, không phải cú pháp của một nhà cung cấp CI cụ thể. Maven phase verify đã đi qua package, nên ví dụ publish artifact từ cùng job với lần verify. Nếu cần tách publish thành job riêng, hãy chuyển artifact đã tạo sang job đó; không build lại source một lần nữa.

Nếu verify thất bại, CI vẫn nên thu thập các test report đã được tạo trước khi job kết thúc. Cấu hình upload-on-failure hoặc cơ chế tương đương phụ thuộc nền tảng, còn định dạng và vị trí report thuộc hợp đồng output của repository.

Một thiết kế tốt gọi command đã được định nghĩa trong repository. CI chịu trách nhiệm chuẩn bị runner, cache, secret, trigger, upload report và lưu artifact.

## 20. Làm cho command có thể chạy lại và dễ chẩn đoán

Command cốt lõi nên hỗ trợ chẩn đoán khi lỗi:

- Log hiển thị bước đang chạy.
- Phiên bản toolchain có thể được in ra mà không lộ secret.
- Lỗi có ngữ cảnh và chỉ ra file/task liên quan.
- Report được giữ ngay cả khi test thất bại.
- Exit code được truyền đúng.
- Temporary output được quản lý.
- Có chế độ verbose khi cần điều tra.
- Có thể chạy lại cùng command với cùng inputs.

Tránh phụ thuộc vào một bước setup bí mật chỉ có trên runner. Nếu cần tạo file cấu hình tạm, hãy để script tự tạo từ input rõ ràng và dọn đúng cách.

Khi lỗi chỉ xuất hiện trên CI, hãy so sánh command, toolchain, environment, dependency state, working directory và quyền truy cập. Đừng vội kết luận do nền tảng CI trước khi tái hiện bằng cùng command.

## 21. Kiểm tra tính độc lập với công cụ

Có thể đánh giá mức độ độc lập của build/test bằng một bài kiểm tra đơn giản:

1. Clone repository vào một máy hoặc container sạch.
2. Không cài build tool toàn cục nếu dự án có wrapper.
3. Cài đúng runtime/toolchain đã khai báo.
4. Chạy command trong tài liệu từ repository root.
5. Chạy lại với cache dependency rỗng.
6. Kiểm tra exit code và report.
7. So sánh artifact digest khi các input giống nhau và build được thiết kế deterministic.
8. Chạy cùng command trên runner CI.
9. Kiểm tra output path và report có ổn định.
10. Xác nhận không cần truy cập vào giao diện hoặc biến riêng của CI để hoàn tất build/test.

Không phải mọi build đều bit-for-bit reproducible do timestamp, archive metadata hoặc toolchain. Nếu chưa đạt deterministic build, cần ghi rõ yếu tố biến thiên và vẫn giữ artifact digest để xác định chính xác binary đã phát hành.

## 22. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Build logic chỉ nằm trong YAML CI | Khó chạy local và khó chuyển nền tảng | Đưa logic vào build tool hoặc script trong repo |
| Gọi Maven/Gradle toàn cục | Mỗi máy có thể dùng phiên bản khác | Dùng wrapper đã version hóa |
| Hard-code workspace path của runner | Command lỗi trên máy khác | Dùng repository-relative path |
| Phụ thuộc biến CI vendor trong test | Test không chạy độc lập | Dùng input có tên và hợp đồng của dự án |
| Script YAML quá dài | Khó lint, test và review | Chuyển logic vào file script/build task |
| Bỏ qua exit code | Pipeline xanh giả | Truyền đúng exit code và kiểm tra kết quả |
| Dùng || true cho test thất bại | Che lỗi chất lượng | Phân loại non-blocking và lưu decision |
| Cache là điều kiện bắt buộc | Build sạch thất bại | Đảm bảo cache chỉ là tối ưu |
| Build lại ở từng môi trường | Artifact có thể khác nhau | Build một lần, promote theo digest |
| Command build tự deploy production | Trộn quyền và side effect | Tách deploy workflow có phê duyệt |
| Không ghi rõ working directory | Lỗi phụ thuộc vị trí gọi | Chuẩn hóa repository root/module root |
| Test phụ thuộc thứ tự hoặc dữ liệu cũ | Flaky và khó tái hiện | Fixture cô lập và cleanup rõ ràng |
| Một command không phân biệt test và package | Khó biết bước nào đã đạt | Định nghĩa task theo mục đích |

## 23. Checklist thiết kế lệnh build và kiểm thử cốt lõi

**Command contract**

- [ ] Có command chuẩn được tài liệu hóa.
- [ ] Working directory và inputs được xác định.
- [ ] Exit code phản ánh đúng kết quả.
- [ ] Output và report path ổn định.
- [ ] Side effect và yêu cầu network được nêu rõ.

**Toolchain và dependency**

- [ ] Có wrapper được version hóa.
- [ ] Phiên bản runtime/JDK được khai báo.
- [ ] Plugin và dependency quan trọng được ghim phiên bản.
- [ ] Có lockfile hoặc dependency verification khi phù hợp.
- [ ] Build vẫn chạy được khi cache rỗng.

**Tính độc lập và tái lập**

- [ ] Lệnh cốt lõi chạy được ngoài CI.
- [ ] Không phụ thuộc path hoặc biến riêng của runner.
- [ ] Script có xử lý path, quote và exit code phù hợp.
- [ ] Test không phụ thuộc thứ tự hoặc trạng thái còn sót.
- [ ] Có thể tái hiện lỗi CI bằng cùng command.

**CI và phát hành**

- [ ] CI gọi command đã định nghĩa trong repository.
- [ ] CI chủ yếu điều phối runner, secret, cache và report.
- [ ] Unit/integration/contract/e2e được phân tầng.
- [ ] Không bỏ qua test trong release gate.
- [ ] Artifact được định danh và promote theo digest.
- [ ] Deploy và rollback là bước riêng có quyền phù hợp.

## 24. Kết luận

Lệnh build và kiểm thử cốt lõi nên thuộc về repository, có command contract rõ ràng và chạy được bên ngoài một nền tảng CI cụ thể. Wrapper, toolchain được ghim phiên bản, dependency được quản lý, đường dẫn portable, exit code chính xác và report ổn định giúp nhóm tái hiện kết quả ở local lẫn CI.

CI vẫn rất quan trọng, nhưng vai trò chính là điều phối: chọn trigger, cung cấp runner và credential, gọi command, lưu bằng chứng và kiểm soát bước phát hành. Khi build/test được tách khỏi đặc thù nền tảng, dự án dễ chuyển CI provider, dễ điều tra lỗi và có thể chứng minh artifact được tạo ra bằng cùng một quy trình đã được review và kiểm thử.

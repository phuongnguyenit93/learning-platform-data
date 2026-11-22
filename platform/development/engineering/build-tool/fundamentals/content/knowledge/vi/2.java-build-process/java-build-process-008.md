# Các hạn chế khi duy trì quy trình thủ công bằng lệnh hoặc script

Trong một dự án Java, quy trình build thường gồm nhiều bước liên tiếp: chuẩn bị môi trường, biên dịch mã nguồn, resolve dependency, chạy test, đóng gói artifact, kiểm tra đầu ra và đôi khi phát hành hoặc triển khai. Khi dự án còn nhỏ, người phát triển có thể nhớ các lệnh cần chạy và thực hiện chúng trực tiếp trong terminal. Một vài script shell cũng có thể gom các lệnh đó thành một chuỗi thao tác.

Cách làm này hữu ích khi khám phá dự án, chạy một tác vụ ngắn hoặc xử lý một tình huống ít lặp lại. Tuy nhiên, khi quy trình được nhiều người sử dụng, chạy trên nhiều máy hoặc trở thành một phần của CI/CD, việc duy trì nó bằng các lệnh rời rạc và script tự quản lý sẽ bộc lộ nhiều giới hạn.

Điểm cần phân biệt là script không tự động đồng nghĩa với một quy trình build đáng tin cậy. Script chỉ lưu lại và thực thi các thao tác. Để quy trình có thể bảo trì, nó còn cần mô tả đầu vào, đầu ra, quan hệ giữa các bước, cách xử lý lỗi, môi trường thực thi và bằng chứng xác minh. Nếu những thông tin đó vẫn nằm trong trí nhớ của người viết hoặc trạng thái riêng của máy, script chỉ làm cho quy trình cũ chạy nhanh hơn mà chưa giải quyết được các vấn đề nền tảng.

## 1. Phụ thuộc vào trí nhớ và kinh nghiệm của từng người

Với quy trình thủ công, người phát triển thường phải nhớ:

- Cần chạy lệnh nào trước và lệnh nào sau.
- Đang đứng ở thư mục nào khi chạy lệnh.
- Cần đặt biến môi trường hoặc tham số nào.
- Module nào cần build và module nào có thể bỏ qua.
- Khi một bước lỗi thì có được tiếp tục hay phải dừng.
- Artifact được tạo ở đâu và cần kiểm tra điều gì.

Những chi tiết này dễ trở thành kiến thức truyền miệng. Người đã quen dự án có thể biết rằng trước khi chạy test phải khởi động một service phụ trợ, hoặc phải chạy một script sinh mã trước khi biên dịch. Người mới chỉ nhìn thấy một danh sách lệnh sẽ khó biết bước nào là bắt buộc, bước nào chỉ phục vụ một tình huống đặc biệt.

Ví dụ, hai thành viên cùng làm một module có thể thực hiện hai quy trình khác nhau:

    # Thành viên A
    ./gradlew :orders-service:clean
    ./gradlew :orders-service:test
    ./gradlew :orders-service:bootJar

    # Thành viên B
    ./gradlew :orders-service:build

Cả hai lệnh có thể kết thúc thành công, nhưng phạm vi task và trạng thái output có thể khác nhau. Nếu nhóm không định nghĩa rõ tiêu chí xác minh, câu nói “máy tôi build được” không cho biết hai người đã kiểm tra cùng một thứ.

Khi số lượng người dùng tăng, nhóm phải tốn thời gian giải thích, hướng dẫn và xử lý những khác biệt do thao tác. Quy trình trở nên mong manh vì một bước quan trọng chỉ được biết bởi một vài cá nhân.

## 2. Thứ tự thao tác và trạng thái máy dễ trở thành phụ thuộc ẩn

Một chuỗi lệnh thủ công thường dựa vào thứ tự thực hiện. Chẳng hạn:

1. Xóa output cũ.
2. Sinh một file cấu hình.
3. Biên dịch.
4. Chạy test.
5. Đóng gói JAR.

Nếu người dùng bỏ qua bước thứ hai, build có thể sử dụng file được sinh từ lần chạy trước. Kết quả vẫn có thể thành công nhưng không phản ánh mã nguồn hiện tại. Nếu chạy bước đóng gói trước khi test hoàn tất, artifact có thể được tạo ra dù kiểm tra chất lượng đã thất bại.

Script có thể ghi lại thứ tự, nhưng nếu không kiểm tra điều kiện trước và sau từng bước, nó vẫn có thể để lại trạng thái dở dang. Ví dụ, một lệnh sinh mã dừng giữa chừng và chỉ ghi được một phần file. Lần chạy tiếp theo có thể dùng lẫn file mới và file cũ.

Các phụ thuộc ẩn thường gặp gồm:

- File sinh ra từ lần chạy trước nhưng không được cập nhật.
- Biến môi trường còn tồn tại trong terminal hiện tại.
- Một service cục bộ đã được khởi động thủ công.
- Dependency đã có trong cache của một máy nhưng chưa có trên máy khác.
- Thư mục làm việc hiện tại khác với thư mục mà script giả định.
- Một tiến trình khác đang ghi vào cùng thư mục output.

Những phụ thuộc này làm cho kết quả khó giải thích. Khi một build pass trên máy A nhưng fail trên máy B, nguyên nhân có thể nằm ở trạng thái trước đó của máy A chứ không nằm trong source code.

Build tool như Gradle có mô hình task và quan hệ phụ thuộc để mô tả phần lớn công việc build. Khi input/output của task được khai báo đúng, Gradle có thể xác định task nào cần chạy lại, task nào đã up-to-date và task nào có thể dùng kết quả từ build cache. Một chuỗi lệnh ngoài build tool thường không có đủ thông tin để đưa ra các quyết định đó.

## 3. Môi trường và hệ điều hành làm giảm tính nhất quán

Lệnh terminal phụ thuộc vào shell, hệ điều hành, đường dẫn, quyền truy cập và các chương trình được cài đặt trên máy.

Ví dụ, một script viết cho Bash có thể sử dụng cú pháp biến, cách xử lý pipeline và lệnh hệ thống không có sẵn trong PowerShell hoặc Command Prompt. Đường dẫn trên Windows thường dùng dấu phân cách khác Unix-like systems; hệ thống file cũng có thể khác về phân biệt chữ hoa/chữ thường. Một script dựa vào lệnh `rm`, `sed` hoặc `grep` có thể cần môi trường tương thích khi chạy trên Windows.

Ngay cả khi mọi máy đều dùng Java, phiên bản JDK và Gradle cũng có thể khác nhau. Một máy chạy Gradle cài toàn cục, máy khác chạy Gradle Wrapper; một máy biên dịch bằng JDK 21, máy khác lại dùng JDK 17. Khi đó, kết quả build có thể khác hoặc lỗi xuất hiện ở những giai đoạn khác nhau.

Một số nguyên nhân thường gặp:

| Khác biệt | Hệ quả có thể xảy ra |
|---|---|
| JDK hoặc Java toolchain | Khác hành vi compiler, API khả dụng hoặc target bytecode |
| Phiên bản Gradle | Khác plugin compatibility, task behavior hoặc dependency resolution |
| Shell | Script không chạy được hoặc xử lý lỗi khác nhau |
| Biến môi trường | Dùng profile, endpoint hoặc cấu hình khác |
| Quyền truy cập | Không đọc được file, không ghi được output hoặc không chạy được script |
| Đường dẫn và encoding | Không tìm thấy file hoặc xử lý nội dung khác nhau |
| Cache dependency | Máy này build offline được nhưng máy khác phải tải dependency |

Gradle Wrapper giúp chuẩn hóa phiên bản Gradle của dự án. Java toolchain giúp khai báo phiên bản Java cần cho compile/test. Tuy nhiên, những cơ chế đó chỉ phát huy tác dụng khi quy trình thực sự dùng chúng và môi trường được cấu hình nhất quán.

Nếu script tự gọi `javac`, `java`, `jar` hoặc một Gradle cài toàn cục tùy ý, nhóm có thể vô tình bỏ qua cấu hình toolchain và quy tắc build đã được dự án quản lý.

## 4. Xử lý lỗi trong chuỗi lệnh thường không rõ ràng

Một giới hạn quan trọng của quy trình thủ công là cách lỗi được truyền từ lệnh này sang lệnh tiếp theo.

Xét script đơn giản:

    ./gradlew :orders-service:clean
    ./gradlew :orders-service:test
    ./gradlew :orders-service:bootJar
    echo "Build finished"

Nếu lệnh test thất bại nhưng script vẫn tiếp tục, lệnh đóng gói có thể thành công. Dòng thông báo cuối cùng cũng có thể khiến người đọc tưởng toàn bộ quy trình đã hoàn tất. Exit code cuối cùng khi đó không đại diện cho kết quả của tất cả các bước trước.

Các shell có cơ chế kiểm soát lỗi riêng. Bash thường dùng `set -e` hoặc `set -Eeuo pipefail`, còn PowerShell có biến `$LASTEXITCODE` để đọc exit code của chương trình native. Nhưng chỉ thêm một tùy chọn dừng khi lỗi không giải quyết được mọi trường hợp: điều kiện, pipeline, lệnh được gọi trong hàm hoặc các bước cleanup có thể có ngữ nghĩa riêng. Script vẫn cần kiểm tra và báo lỗi có chủ đích.

Ví dụ kiểm tra từng lệnh trong PowerShell:

    & .\gradlew.bat :orders-service:test
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

Đây là cách thể hiện rõ việc dừng khi Gradle trả về exit code khác `0`. Nếu có nhiều bước, script còn phải quyết định cách xử lý output một phần, file tạm và tài nguyên đã mở.

Các vấn đề khó hơn xuất hiện khi một quy trình có nhiều tác động:

- Bước đầu đã tạo file nhưng bước sau thất bại.
- Một service phụ trợ được khởi động nhưng không được dừng.
- Artifact cũ vẫn nằm cạnh artifact mới chưa hoàn chỉnh.
- Script chạy lại và lặp thao tác đã hoàn tất.
- Một bước publish đã xảy ra trước khi bước xác minh cuối cùng hoàn thành.

Nếu không thiết kế khả năng dừng, cleanup và chạy lại an toàn, người vận hành phải tự phán đoán trạng thái sau lỗi. Điều này đặc biệt rủi ro với những bước có side effect như upload, publish hoặc deploy.

## 5. Khó mô tả quan hệ giữa các bước và tận dụng incremental build

Một danh sách lệnh chỉ mô tả thứ tự thao tác ở mức tổng quát. Nó không nhất thiết cho build tool biết task nào phụ thuộc vào task nào, file nào là input, file nào là output và điều kiện nào làm kết quả mất hiệu lực.

Ví dụ, script có thể luôn chạy:

    ./gradlew :orders-service:compileJava
    ./gradlew :orders-service:test
    ./gradlew :orders-service:bootJar

Mỗi lần gọi Gradle riêng có thể phát sinh thêm chi phí khởi động và làm quy trình khó quan sát như một execution graph thống nhất. Nếu script còn gọi compiler hoặc đóng gói bằng công cụ riêng, Gradle không thể tự quản lý đầy đủ các bước đó như task thuộc build graph của nó.

Trong Gradle, task graph biểu diễn quan hệ phụ thuộc. Task khai báo input/output chính xác có thể được bỏ qua khi output vẫn hợp lệ (`UP-TO-DATE`) hoặc nhận output từ build cache (`FROM-CACHE`). Những cơ chế này giúp tránh làm lại công việc không cần thiết và hỗ trợ build nhất quán hơn.

Một script tự quản lý file output có thể bỏ lỡ các lợi ích đó. Nó có thể chạy lại tất cả mọi thứ dù input không đổi, hoặc tệ hơn, bỏ qua một bước dù input đã thay đổi vì script chỉ kiểm tra sự tồn tại của file.

Ví dụ, điều kiện “nếu file JAR đã tồn tại thì bỏ qua build” không chứng minh JAR đó được tạo từ commit hiện tại. Muốn kiểm tra tính hợp lệ, phải liên hệ artifact với input, cấu hình và dependency đã tạo ra nó.

Không phải mọi script đều mất khả năng incremental build. Nếu script chỉ gọi Gradle Wrapper và để Gradle quản lý compile/test/package, các task bên trong vẫn có thể dùng up-to-date checking và cache. Hạn chế xuất hiện khi script tự thay thế hoặc che khuất mô hình task, input/output và dependency của build tool.

## 6. Quản lý dependency bằng lệnh rời rạc dễ thiếu nhất quán

Trong Java, dependency không chỉ là một danh sách JAR. Một thư viện có thể phụ thuộc vào nhiều thư viện khác; các dependency có thể yêu cầu những phiên bản khác nhau của cùng một module. Build cần resolve graph, áp dụng constraint, exclusion, platform hoặc version alignment theo quy tắc thống nhất.

Nếu script tự tải JAR từ URL, chép file vào thư mục `lib` hoặc ghép classpath bằng tay, nhóm phải tự xử lý:

- Phiên bản thư viện và nguồn tải.
- Dependency bắc cầu (transitive dependencies).
- Xung đột phiên bản.
- Checksum hoặc xác minh artifact.
- Phân biệt dependency dùng khi compile, test và runtime.
- Cập nhật đồng bộ giữa các module.
- Khả năng tải lại dependency trên máy mới.

Một lệnh tải file thành công chỉ chứng minh file đã được tải về. Nó không chứng minh dependency graph hợp lệ hoặc artifact có nguồn gốc và nội dung mong đợi.

Gradle dependency management cung cấp cơ chế khai báo dependency, version constraint, dependency locking và dependency verification. Khi build logic là nguồn quản lý dependency, nhóm có thể xem và kiểm soát cách phiên bản được chọn. Nếu mỗi script tự quyết định classpath, các module dễ dùng những tập thư viện khác nhau mà không có một nơi quản lý rõ ràng.

## 7. Khả năng quan sát và truy nguyên thường không đủ

Khi chạy lệnh thủ công, bằng chứng thường chỉ nằm trong terminal của người thực hiện. Terminal đóng, log bị cuộn mất hoặc người dùng chỉ gửi một ảnh chụp phần cuối thì người khác không thể tái dựng đầy đủ điều đã xảy ra.

Một quy trình cần trả lời được:

- Commit hoặc source version nào đã được build?
- JDK, Gradle và các plugin phiên bản nào được dùng?
- Task nào đã chạy, task nào bị skip?
- Dependency nào đã được resolve?
- Test nào pass hoặc fail?
- Artifact nào được tạo và nằm ở đâu?
- Nếu thất bại, task đầu tiên lỗi là gì và nguyên nhân gốc ở đâu?

Nếu script chỉ in “Success” hoặc “Failed”, thông tin chẩn đoán rất hạn chế. Nếu script ghi toàn bộ output vào một file chung, lần chạy sau có thể ghi đè bằng chứng của lần trước. Nếu log quá ít, khó tìm nguyên nhân; nếu log quá nhiều mà không có cấu trúc, người đọc lại khó xác định phần quan trọng.

Gradle có test report, task outcome, stack trace và các mức log như `--info` hoặc `--stacktrace`. CI có thể lưu báo cáo và artifact theo từng lần chạy, gắn với commit hoặc workflow run. Script bên ngoài vẫn có thể thu thập những dữ liệu đó, nhưng nhóm phải tự xây dựng quy tắc lưu trữ, đặt tên, liên kết và bảo toàn chúng.

Build scan cũng có thể cung cấp thêm thông tin về task timeline, dependency resolution và môi trường. Việc xuất bản scan có thể chia sẻ dữ liệu build với dịch vụ bên ngoài, do đó cần tuân theo chính sách dữ liệu của tổ chức.

## 8. Khó phối hợp khi nhiều module hoặc nhiều người cùng chạy

Khi dự án có nhiều module, một script có thể lần lượt gọi build cho từng module. Cách làm này nhanh chóng trở nên phức tạp khi một module phụ thuộc module khác, hoặc chỉ một phần dự án cần build lại.

Nếu script tự quy định thứ tự bằng một danh sách tên module, danh sách đó phải được cập nhật mỗi khi cấu trúc dự án thay đổi. Một dependency mới có thể khiến thứ tự cũ không còn đúng. Nếu hai người hoặc hai CI job chạy cùng lúc, chúng có thể ghi vào cùng thư mục output, dùng chung file tạm hoặc tranh chấp một service cục bộ.

Build tool có thể mô tả project dependency và xác định thứ tự task theo graph. CI có thể chia job, cô lập workspace và kiểm soát tài nguyên theo chiến lược của dự án. Một script tùy biến vẫn có thể thực hiện các việc này, nhưng càng nhiều logic điều phối thì càng nhiều mã cần kiểm tra và duy trì.

Các dấu hiệu cho thấy quy trình đang vượt quá khả năng của một script đơn giản:

- Danh sách module hoặc điều kiện chạy tăng liên tục.
- Phải tự sắp xếp thứ tự phụ thuộc giữa module.
- Có nhiều bước chạy song song và cần đồng bộ output.
- Phải tự khóa thư mục hoặc quản lý trạng thái dùng chung.
- Nhiều nhóm duy trì các bản script gần giống nhau.
- Một thay đổi trong build logic buộc phải sửa nhiều script ở nhiều nơi.

## 9. Chi phí bảo trì tăng theo số lượng script và ngoại lệ

Script thường bắt đầu rất ngắn. Theo thời gian, nhóm thêm điều kiện cho Windows, Linux, local development, CI, từng module, từng profile và từng loại artifact. Script dần chứa logic nghiệp vụ build mà không có cấu trúc hoặc quy ước chung.

Một số vấn đề bảo trì thường gặp:

- Một lệnh Gradle được lặp lại ở nhiều script.
- Tên module hoặc đường dẫn được hard-code ở nhiều nơi.
- Điều kiện môi trường bị sao chép nhưng không đồng bộ.
- Không có test cho chính script.
- Không rõ ai sở hữu script và khi nào cần cập nhật.
- Thay đổi cách build phải sửa cả tài liệu, script local và cấu hình CI.
- Script cũ tiếp tục được dùng vì không có thông báo hoặc cơ chế loại bỏ.

Khi script trở thành nơi chứa nhiều logic, việc sửa một bước nhỏ có thể ảnh hưởng tới nhiều workflow khác. Người bảo trì phải hiểu cả ngôn ngữ shell, môi trường chạy và quy ước nội bộ của dự án trước khi thay đổi.

Đưa logic build vào Gradle task hoặc convention plugin giúp gom quy tắc ở nơi phù hợp với hệ thống build. Script bên ngoài có thể giữ vai trò gọi một entry point ổn định, ví dụ Gradle Wrapper, thay vì tự triển khai compile, test, dependency resolution và packaging lần nữa.

## 10. Rủi ro bảo mật và side effect khó kiểm soát

Script có thể đọc biến môi trường, token, mật khẩu hoặc thông tin kết nối để gọi dịch vụ ngoài. Nếu in toàn bộ environment, bật log quá chi tiết hoặc truyền secret trực tiếp trong command line, dữ liệu nhạy cảm có thể xuất hiện trong log hoặc lịch sử terminal.

Các thao tác như tải script từ URL rồi chạy, dùng đường dẫn được ghép từ input chưa kiểm tra, hoặc dùng lệnh shell có `eval` cũng tạo ra rủi ro thực thi ngoài ý muốn. Quy trình publish/deploy còn có thể tạo side effect khó đảo ngược nếu script tiếp tục chạy sau khi một bước xác minh thất bại.

Một số nguyên tắc cần có khi duy trì script:

- Không hard-code token hoặc mật khẩu trong file được quản lý bằng Git.
- Chỉ truyền secret qua cơ chế secret phù hợp của môi trường chạy.
- Không in giá trị secret vào log.
- Quote đường dẫn và tham số đúng theo shell đang sử dụng.
- Không thực thi nội dung tải từ nguồn chưa được xác minh.
- Kiểm tra input trước khi ghép vào lệnh.
- Tách bước build/test khỏi bước publish/deploy có side effect.
- Chỉ thực hiện publish sau khi các điều kiện xác minh đã pass.

Đây không phải vấn đề riêng của shell script. Gradle build logic và CI workflow cũng cần được bảo vệ. Tuy nhiên, script tự do thường dễ tích lũy các thao tác đặc quyền mà thiếu một ranh giới rõ ràng giữa build và phát hành.

## 11. Script có thể được cải thiện, nhưng cần biết giới hạn của nó

Không nên kết luận rằng mọi script đều xấu hoặc phải thay thế ngay. Script là công cụ phù hợp cho những thao tác điều phối nhỏ, đặc biệt khi cần gọi một vài chương trình hệ thống hoặc chuẩn bị môi trường.

Một script có thể đáng tin cậy hơn khi:

- Được lưu trong repository và review như mã nguồn.
- Có hướng dẫn về shell, phiên bản công cụ và cách chạy.
- Xác định thư mục gốc dự án thay vì phụ thuộc terminal hiện tại.
- Kiểm tra tham số và điều kiện tiên quyết.
- Xử lý exit code của từng chương trình native.
- Dừng đúng lúc và cleanup tài nguyên khi thất bại.
- Không dựa vào file tạm hoặc output cũ mà không xác minh.
- Ghi log đủ để truy nguyên và không làm lộ secret.
- Có kiểm thử cho các nhánh xử lý quan trọng.
- Được chạy trong CI với môi trường đã xác định.

Ví dụ, thay vì gọi nhiều task Gradle trong nhiều tiến trình riêng biệt, một script có thể gọi một entry point:

    ./gradlew :orders-service:build

Gradle sẽ quản lý các task thuộc lifecycle build của project theo cấu hình hiện hành. Script có thể đảm nhận việc chọn module, chuẩn bị biến môi trường và lưu log. Compile, test, dependency resolution và packaging vẫn nên được quản lý trong build logic để task graph, incremental build và báo cáo hoạt động đúng.

Nếu dự án có một quy trình riêng cần gom nhiều task, có thể tạo lifecycle task trong Gradle thay vì duy trì một danh sách lệnh ở nhiều nơi. Ví dụ với Java plugin:

    tasks.register("verifyAndPackage") {
        dependsOn("check", "jar")
    }

Ví dụ này tạo một task tổng hợp để biểu diễn quan hệ phụ thuộc. Trong dự án thực tế, cần chọn đúng task packaging theo loại module; ứng dụng Spring Boot có thể dùng `bootJar`, còn library thường dùng `jar`.

## 12. Khi nào nên chuyển logic vào build tool hoặc CI?

Hãy xem xét vị trí phù hợp của từng loại công việc:

| Công việc | Nơi thường phù hợp |
|---|---|
| Compile Java, xử lý resource, test, đóng gói JAR | Gradle task |
| Khai báo dependency, version constraint và toolchain | Gradle build logic |
| Sinh file dựa trên source/configuration của module | Gradle task có khai báo input/output |
| Quy tắc dùng chung giữa nhiều project | Convention plugin hoặc plugin phù hợp |
| Chọn commit, cấu hình runner và kích hoạt pipeline | CI workflow |
| Lưu test report, artifact và kết quả theo từng lần chạy | CI artifact/report |
| Chuẩn bị một service cục bộ hoặc gọi công cụ hệ thống | Script nhỏ, có kiểm soát |
| Publish hoặc deploy sau khi xác minh | Job/pipeline có điều kiện rõ ràng |

Một quy tắc thực tế là: nếu một thao tác cần tham gia vào dependency graph, incremental build, cache hoặc lifecycle của project, hãy cân nhắc đưa nó thành Gradle task. Nếu thao tác điều phối runner, trigger workflow hoặc quản lý bước giữa các hệ thống, CI thường là nơi thích hợp. Script có thể kết nối các phần này nhưng không nên trở thành một build system thứ hai.

## 13. Quy trình chuyển đổi mà không làm gián đoạn nhóm

Khi một chuỗi lệnh đã được sử dụng lâu, không nên thay đổi tất cả cùng lúc. Có thể chuyển dần theo các bước:

1. **Ghi lại cách làm hiện tại.** Thu thập lệnh, thứ tự, biến môi trường, file đầu vào/đầu ra và điều kiện cần thiết. Xác định bước nào là bắt buộc, bước nào chỉ là thao tác cá nhân.
2. **Tìm logic thuộc build.** Compile, test, dependency resolution, resource processing và packaging nên được mô tả trong Gradle khi có thể.
3. **Xác định một entry point chuẩn.** Ví dụ một task lifecycle cho module hoặc một lệnh Gradle Wrapper được tài liệu hóa.
4. **Đưa quy trình lặp lại vào CI.** Chạy cùng entry point trên runner đã xác định và lưu test report, log cùng artifact.
5. **Giữ script ở vai trò điều phối nhỏ.** Loại bỏ phần logic đã được build tool quản lý để tránh hai nơi cùng quyết định một việc.
6. **So sánh kết quả trước và sau.** Kiểm tra phạm vi task, dependency, test, artifact và điều kiện môi trường. Chỉ bỏ quy trình cũ sau khi quy trình mới đã được nhóm sử dụng và xác minh.

Trong quá trình chuyển đổi, cần giữ lại khả năng chạy local. CI không thay thế việc phát triển trên máy cá nhân; nó cung cấp một môi trường kiểm chứng nhất quán hơn cho quy trình đã được chuẩn hóa.

## 14. Ví dụ tổng hợp: từ chuỗi lệnh cá nhân đến quy trình có thể duy trì

Giả sử một nhóm có hướng dẫn trong chat:

    cd module/orders-service
    ./gradlew clean
    ./gradlew test
    ./gradlew bootJar
    cp build/libs/*.jar ../../release/

Hướng dẫn này có một số điểm không rõ:

- Người chạy phải biết chính xác thư mục bắt đầu.
- Ba lần gọi Gradle tạo thành ba tiến trình build riêng.
- Không có quy tắc rõ ràng về xử lý lỗi trước khi copy.
- Wildcard có thể copy nhiều JAR nếu thư mục chứa nhiều artifact.
- Không có xác minh rằng JAR được copy là artifact của lần build hiện tại.
- Không ghi lại commit, phiên bản công cụ hoặc test report.
- Thư mục release có thể chứa file từ lần chạy trước.

Một cách tổ chức rõ ràng hơn là để Gradle quản lý lifecycle build và xác định output, còn script chỉ gọi wrapper từ thư mục gốc:

    ./gradlew :orders-service:build

Sau đó, nếu cần đóng gói artifact để lưu trữ, CI có thể lấy đúng đường dẫn artifact đã biết, kiểm tra file tồn tại và lưu cùng metadata của lần chạy. Nếu cần publish, thực hiện trong một job riêng chỉ chạy sau khi build và kiểm tra đã thành công.

Cách tổ chức này làm rõ trách nhiệm: Gradle biết cách build module; CI biết khi nào cần chạy và lưu kết quả; script nhỏ chỉ xử lý phần điều phối mà hai công cụ trên không đảm nhiệm. Nhóm có thể xem lại task outcome, test report và artifact của từng lần chạy mà không phải dựa vào lịch sử terminal của một cá nhân.

## 15. Checklist nhận biết quy trình thủ công đang trở thành gánh nặng

Hãy xem xét chuẩn hóa quy trình khi xuất hiện một hoặc nhiều dấu hiệu sau:

- [ ] Người mới phải hỏi nhiều lần mới biết đầy đủ lệnh và thứ tự chạy.
- [ ] Hai người làm theo cùng hướng dẫn nhưng tạo ra kết quả khác nhau.
- [ ] Build phụ thuộc vào file, service hoặc biến môi trường không được ghi nhận.
- [ ] Script có nhiều nhánh theo OS, module, profile và ngoại lệ.
- [ ] Lỗi ở một bước nhưng các bước sau vẫn chạy hoặc thông báo cuối gây hiểu nhầm.
- [ ] Phải tự kiểm tra file output cũ/mới bằng các điều kiện rời rạc.
- [ ] Các script tự tải hoặc tự quản lý dependency.
- [ ] Nhiều script lặp lại cùng một đoạn logic build.
- [ ] Không thể truy lại commit, toolchain, task outcome và artifact của một lần chạy.
- [ ] Nhiều người hoặc CI job có thể ghi đè lên cùng output.
- [ ] Thay đổi build logic buộc phải cập nhật nhiều script và tài liệu.
- [ ] Không rõ ai chịu trách nhiệm bảo trì và xác minh script.

Không phải cứ có một dấu hiệu là phải viết lại toàn bộ hệ thống. Hãy xác định nguyên nhân cụ thể, mức độ ảnh hưởng và nơi phù hợp để quản lý logic đó.

## Kết luận

Lệnh thủ công và script nhỏ phù hợp cho công việc đơn giản, ít bước và có phạm vi rõ. Khi quy trình Java phát triển, những hạn chế chính xuất hiện ở sự phụ thuộc vào con người, trạng thái môi trường ẩn, xử lý lỗi, quản lý dependency, khả năng quan sát, phối hợp nhiều module và chi phí bảo trì.

Script có thể lưu lại thao tác và giảm lỗi gõ lệnh, nhưng chỉ riêng việc gom lệnh chưa tạo ra một quy trình build có thể lặp lại và chẩn đoán được. Muốn duy trì lâu dài, cần đưa compile, test, dependency và packaging vào mô hình build có task graph và input/output rõ ràng; dùng CI để chạy và lưu bằng chứng trong môi trường chuẩn hóa; giữ script ở phạm vi điều phối nhỏ. Khi mỗi công cụ đảm nhận đúng phần việc của mình, quy trình dễ hiểu hơn, kết quả có thể kiểm chứng và thay đổi cũng ít gây ảnh hưởng ngoài dự kiến hơn.

# Tải phụ thuộc từ nguồn được kiểm soát

## 1. Vì sao nguồn tải dependency quan trọng?

Một lần build thường lấy về nhiều thành phần mà nhóm không trực tiếp viết: thư viện, plugin build, compiler, image nền, package của công cụ kiểm thử và các thành phần bắc cầu (transitive dependencies). Mỗi thành phần đều ảnh hưởng đến kết quả build, độ an toàn và khả năng tái tạo phiên bản.

Nếu pipeline tải dependency từ nhiều nguồn công khai và không được kiểm soát, nhóm có thể gặp các vấn đề:

- Một package bị thay thế hoặc bị phát hành phiên bản độc hại.
- Dependency có tên gần giống package nội bộ bị chọn nhầm từ registry công khai.
- Một registry tạm thời không truy cập được khiến build thất bại.
- Hai máy build lấy metadata hoặc phiên bản khác nhau.
- Một dependency bị xóa hoặc thay đổi khiến không thể tái tạo bản phát hành cũ.
- Credential của repository bị ghi vào log, tệp cấu hình hoặc cache.
- Cache chứa package không đáng tin cậy được dùng lại trong pipeline có quyền cao.

Vì vậy, quản lý dependency không chỉ là khai báo tên thư viện. Nhóm cần kiểm soát **nguồn**, **danh tính**, **tính toàn vẹn**, **phiên bản**, **quyền truy cập** và **cách lưu cache**.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, mục tiêu là xây dựng luồng build và kiểm thử tự động có thể truy vết, quản lý artifact và môi trường, bảo vệ bí mật và phát hành có kiểm soát. Một nguồn dependency đáng tin cậy giúp pipeline nhận được đầu vào ổn định, giảm rủi ro chuỗi cung ứng và hỗ trợ điều tra khi một bản build có vấn đề.

## 2. Nguồn dependency và vai trò của repository manager

Dependency thường được phân phối qua package registry hoặc repository. Ví dụ:

- Maven Central cho artifact Java và JVM.
- npm registry cho package JavaScript.
- PyPI cho package Python.
- NuGet Gallery cho package .NET.
- Container registry cho image.
- Repository nội bộ cho thư viện do tổ chức tự phát triển.

Nhóm có thể tải trực tiếp từ registry công khai, nhưng trong môi trường CI/CD cần một điểm kiểm soát thống nhất. Repository manager như Nexus Repository, JFrog Artifactory hoặc một dịch vụ registry tương đương có thể đứng giữa pipeline và nguồn upstream.

Một repository manager thường cung cấp ba loại repository:

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Proxy/remote | Lấy và cache package từ upstream theo chính sách | Proxy Maven Central hoặc npm registry |
| Hosted/local | Lưu package do tổ chức tự phát hành | Thư viện nội bộ hoặc package release |
| Group/virtual | Gom nhiều repository dưới một endpoint | Kết hợp package nội bộ và proxy upstream |

Pipeline có thể dùng một endpoint nội bộ thống nhất. Repository manager sẽ áp dụng chính sách định tuyến, xác thực, cache, allowlist và audit ở phía sau.

Một luồng tải dependency điển hình:

~~~mermaid
flowchart LR
    A["CI runner"] --> B["Repository nội bộ"]
    B --> C{"Package đã có trong cache?"}
    C -- "Có" --> D["Trả package đã lưu"]
    C -- "Chưa" --> E["Kiểm tra chính sách và upstream"]
    E --> F["Registry upstream được phép"]
    F --> G["Xác minh và cache package"]
    G --> D
    D --> H["Build và kiểm thử"]
    I["Repository package nội bộ"] --> B
~~~

Repository manager giúp kiểm soát đường đi của package, nhưng không tự động biến mọi package thành an toàn. Nhóm vẫn cần xác minh phiên bản, checksum hoặc chữ ký, nguồn gốc, lỗ hổng và chính sách sử dụng.

### 2.1. Proxy repository

Proxy repository nhận yêu cầu package từ client, truy cập upstream khi cần và lưu nội dung theo chính sách cache. Khi package đã được cache, các lần tải sau có thể được phục vụ từ hệ thống nội bộ.

Lợi ích:

- Giảm phụ thuộc vào tính sẵn sàng của registry công khai.
- Tăng tốc build lặp lại.
- Tạo một điểm để áp dụng allowlist, scan và audit.
- Giảm lượng request từ CI runner ra Internet.
- Có thể giữ lại phiên bản đã được sử dụng trong thời gian phù hợp.

Cần xác định upstream nào được phép, cache bao lâu, package nào bị chặn và cách xử lý khi upstream thay đổi hoặc package bị thu hồi.

### 2.2. Hosted repository

Hosted repository lưu package do tổ chức sở hữu hoặc được phép phân phối. Đây thường là nơi publish thư viện nội bộ sau khi build và kiểm tra.

Nên phân tách quyền đọc và ghi. CI của ứng dụng thông thường chỉ cần quyền đọc. Pipeline phát hành thư viện mới cần quyền ghi vào đúng repository và namespace. Không cấp credential publish cho mọi job build.

### 2.3. Group hoặc virtual repository

Group repository cung cấp một URL duy nhất cho nhiều nguồn. Nó giúp dự án không phải khai báo nhiều endpoint và cho phép quản trị viên thay đổi nguồn phía sau mà ít ảnh hưởng đến cấu hình dự án.

Tuy nhiên, thứ tự ưu tiên và cách xử lý package trùng tọa độ phải rõ ràng. Nếu một package nội bộ có cùng tọa độ với package công khai, kết quả phụ thuộc cấu hình định tuyến có thể tạo ra dependency confusion. Nhóm cần dành namespace riêng cho package nội bộ và quy định repository nào có quyền cung cấp namespace đó.

## 3. Thiết kế nguồn tải theo nguyên tắc kiểm soát

Một thiết kế nguồn dependency nên có các nguyên tắc sau:

1. **Có danh sách nguồn được phép:** chỉ dùng registry hoặc repository đã được phê duyệt cho từng hệ sinh thái.
2. **Ưu tiên endpoint nội bộ:** CI runner tải package qua proxy hoặc virtual repository do tổ chức quản lý.
3. **Tách package nội bộ và package công khai:** namespace nội bộ phải được kiểm soát rõ ràng.
4. **Không fallback tùy tiện:** khi nguồn tin cậy không truy cập được, pipeline không tự chuyển sang registry không được kiểm soát.
5. **Giới hạn quyền:** build job chỉ có quyền đọc; publish job có quyền ghi theo phạm vi cần thiết.
6. **Dùng TLS và xác thực:** bảo vệ kết nối và danh tính truy cập.
7. **Lưu audit trail:** ghi nhận package, phiên bản, nguồn, thời điểm và danh tính đã truy cập hoặc publish.
8. **Có chính sách retention:** giữ package cần thiết cho việc tái tạo bản build và tuân thủ yêu cầu lưu trữ.

### 3.1. Tránh dependency confusion

Dependency confusion xảy ra khi hệ thống chọn package từ nguồn không mong muốn do trùng hoặc gần trùng tên, namespace hay tọa độ package.

Ví dụ, ứng dụng nội bộ dùng package có tọa độ Maven **com.company:payment-client**. Nếu cấu hình repository cho phép tìm package đó ở cả repository nội bộ và registry công khai mà không có quy tắc ưu tiên, một package công khai cùng tọa độ có thể được chọn trong một số tình huống.

Các biện pháp:

- Dùng groupId hoặc namespace riêng cho package nội bộ.
- Cấu hình repository manager để namespace nội bộ chỉ được phục vụ từ hosted repository tương ứng.
- Không cho dự án tự thêm repository công khai tùy ý nếu chính sách yêu cầu tập trung nguồn.
- Dùng content filtering hoặc exclusive repository mapping khi package manager hỗ trợ.
- Review thay đổi tọa độ dependency và repository.
- Theo dõi package mới xuất hiện trong namespace nội bộ.

Không nên dựa duy nhất vào thứ tự khai báo repository. Cần kiểm tra hành vi thực tế của package manager và repository manager khi có nhiều nguồn cùng chứa một tọa độ.

### 3.2. Phân biệt nguồn release và snapshot

Package phát hành chính thức và package đang phát triển có vòng đời khác nhau.

Với Maven, release repository thường lưu phiên bản bất biến như **2.3.1**; snapshot repository lưu phiên bản phát triển có thể thay đổi như **2.4.0-SNAPSHOT**. Không nên để pipeline production lấy snapshot tùy tiện vì nội dung có thể thay đổi giữa hai lần build dù tọa độ nhìn giống nhau.

Tách repository giúp:

- Cấp quyền publish riêng.
- Áp dụng retention khác nhau.
- Dùng chính sách kiểm tra khác nhau.
- Ngăn dependency thử nghiệm đi vào luồng phát hành chính thức.
- Điều tra dễ hơn khi một package snapshot gây lỗi.

## 4. Xác minh danh tính và tính toàn vẹn của package

Kiểm soát nguồn tải trả lời câu hỏi package đến từ đâu. Kiểm tra tính toàn vẹn trả lời câu hỏi nội dung nhận được có đúng với nội dung được công bố hay không.

### 4.1. Checksum

Checksum là giá trị băm được tính từ nội dung file, thường dùng SHA-256 hoặc thuật toán mạnh tương đương. Client có thể tính lại checksum sau khi tải và so sánh với giá trị tham chiếu.

Checksum giúp phát hiện:

- File bị hỏng trong quá trình truyền hoặc lưu trữ.
- Nội dung package không khớp với metadata đã công bố.
- Một số trường hợp package bị thay thế ngoài dự kiến.

Checksum chỉ có giá trị khi nguồn cung cấp checksum đáng tin cậy. Nếu attacker thay được cả package và checksum ở cùng một nguồn, việc so sánh vẫn có thể thành công. Với package quan trọng, cần kết hợp chữ ký số, provenance hoặc nguồn tham chiếu độc lập.

### 4.2. Chữ ký số

Chữ ký số cho phép xác minh package hoặc metadata được ký bởi khóa tương ứng. Nhóm cần biết:

- Ai hoặc hệ thống nào có quyền ký.
- Khóa công khai được phân phối và tin cậy bằng cách nào.
- Khóa bị thu hồi hoặc thay đổi thì xử lý ra sao.
- Chữ ký được kiểm tra ở thời điểm tải, publish hay trước phát hành.
- Kết quả xác minh được lưu ở đâu.

Không nên chấp nhận chữ ký chỉ vì package có một file chữ ký đi kèm. Pipeline phải xác minh khóa ký nằm trong tập tin cậy và thuật toán/chính sách đáp ứng yêu cầu.

### 4.3. Provenance và SBOM

Provenance mô tả package hoặc artifact được tạo ra như thế nào: nguồn mã, commit, pipeline, builder, tham số build và các bước liên quan. SBOM (Software Bill of Materials) liệt kê thành phần phần mềm có trong sản phẩm.

Hai loại thông tin này bổ sung cho nhau:

- Checksum xác định nội dung file.
- Chữ ký xác minh danh tính bên ký.
- Provenance giải thích nguồn gốc và quy trình tạo.
- SBOM cho biết sản phẩm chứa dependency nào.

Khi có cảnh báo lỗ hổng trong một thư viện, SBOM giúp xác định phiên bản sản phẩm nào bị ảnh hưởng. Provenance giúp truy lại bản build và nguồn mã đã tạo ra artifact đó.

## 5. Pin phiên bản và lock dependency

Một dependency được khai báo bằng khoảng phiên bản hoặc tên tag có thể cho kết quả khác nhau ở các thời điểm build khác nhau.

Ví dụ, một khai báo cho phép mọi phiên bản từ **1.4** trở lên có thể chọn **1.4.3** hôm nay và **1.8.0** sau này. Phiên bản mới có thể thay đổi API, hành vi hoặc dependency bắc cầu.

Để tăng khả năng tái tạo:

- Pin phiên bản trực tiếp và phiên bản plugin quan trọng.
- Dùng lockfile hoặc dependency locking để ghi lại phiên bản đã giải quyết.
- Kiểm soát phiên bản toolchain và package manager.
- Tránh **latest**, dynamic version và version range không cần thiết trong release.
- Ghi lại repository và checksum hoặc metadata xác minh.
- Review thay đổi lockfile như thay đổi mã nguồn.

Pin phiên bản không có nghĩa là giữ dependency cũ mãi mãi. Nhóm cần một quy trình cập nhật có chủ đích: đề xuất phiên bản mới, chạy kiểm thử, scan lỗ hổng, review thay đổi và phát hành lại artifact.

### 5.1. Maven

Với Maven, dependency được xác định bằng groupId, artifactId, version và có thể thêm classifier/type. Một dependency release nên khai báo phiên bản cụ thể. Tránh dùng LATEST, RELEASE hoặc version range trong quy trình build cần tái lập.

Maven có thể cấu hình mirror trong **settings.xml** để chuyển yêu cầu repository qua endpoint nội bộ.

~~~xml
<settings>
  <mirrors>
    <mirror>
      <id>company-maven</id>
      <mirrorOf>*</mirrorOf>
      <url>https://packages.example.invalid/repository/maven-public/</url>
    </mirror>
  </mirrors>

  <servers>
    <server>
      <id>company-maven</id>
      <username>INJECTED_AT_RUNTIME</username>
      <password>INJECTED_AT_RUNTIME</password>
    </server>
  </servers>
</settings>
~~~

Trong ví dụ, URL thuộc miền minh họa. Credential được chèn vào tệp settings tạm thời từ secret manager của CI; không commit token vào repository. ID trong phần servers phải khớp với ID của mirror để Maven tìm đúng thông tin xác thực. Tệp tạm cần được bảo vệ quyền đọc và xóa sau khi job kết thúc.

Mirror áp dụng cho mọi repository khi cấu hình mirrorOf theo chính sách tập trung nguồn tải. Điều này chỉ phù hợp khi endpoint nội bộ được cấu hình để phục vụ đầy đủ các repository cần thiết. Nếu có ngoại lệ, cần khai báo và review rõ ràng.

Có thể yêu cầu Maven thất bại khi checksum từ repository không khớp hoặc không có theo chính sách:

~~~xml
<releases>
  <checksumPolicy>fail</checksumPolicy>
</releases>
~~~

Chính sách checksum chỉ kiểm tra giá trị mà repository cung cấp. Nó không thay thế xác minh chữ ký hoặc provenance. Với cấu hình mirror tập trung, nhóm nên kiểm tra cách Maven áp dụng repository policy trong dự án thực tế và tránh khai báo URL ngoài chính sách ở từng POM.

### 5.2. Gradle

Gradle cho phép khai báo repository tập trung trong **settings.gradle** và hạn chế project tự thêm nguồn khác.

Ví dụ Groovy DSL:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        maven {
            name = "companyMirror"
            url = uri("https://packages.example.invalid/repository/gradle-public/")

            credentials {
                username = providers.environmentVariable("MAVEN_REPO_USER").orNull
                password = providers.environmentVariable("MAVEN_REPO_TOKEN").orNull
            }
        }
    }
}
~~~

FAIL_ON_PROJECT_REPOS khiến Gradle báo lỗi khi project tự khai báo repository riêng, giúp giữ nguồn dependency ở một nơi được quản lý. Credential chỉ có mặt trong môi trường build và phải được cấp theo quyền đọc tối thiểu.

Gradle hỗ trợ dependency locking để ghi lại phiên bản đã được giải quyết. Có thể bật locking trong cấu hình phù hợp:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo hoặc cập nhật lock state bằng một lần chạy có chủ đích, review các file lock được thay đổi và commit chúng cùng mã nguồn. Cần hiểu cấu hình nào được lock và tác động của configuration resolution để tránh bỏ sót dependency dùng trong build hoặc plugin.

Gradle dependency verification có thể lưu checksum và chữ ký được tin cậy trong **gradle/verification-metadata.xml**. Ví dụ tạo metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Metadata được sinh ra cần được review trước khi commit. Không nên mặc định tin mọi checksum chỉ vì lệnh tạo metadata đã tải package thành công; với dependency quan trọng, đối chiếu nguồn và chữ ký đáng tin cậy trước khi chấp nhận giá trị ban đầu.

### 5.3. npm và Python

Với npm, có thể cấu hình registry nội bộ trong **.npmrc** và dùng lockfile như **package-lock.json** để ghi lại phiên bản cùng integrity metadata.

~~~ini
registry=https://packages.example.invalid/repository/npm-public/
@company:registry=https://packages.example.invalid/repository/npm-internal/
//packages.example.invalid/repository/npm-public/:_authToken=${NPM_READ_TOKEN}
always-auth=true
~~~

Token trong ví dụ là biến môi trường được CI cung cấp. Tệp .npmrc có thể được commit nếu chỉ chứa URL và tham chiếu biến, nhưng tuyệt đối không commit giá trị token thật. Cần bảo đảm quy tắc scope nội bộ không bị ghi đè bởi cấu hình cấp người dùng hoặc một bước cài đặt khác.

Với Python, có thể cấu hình index-url hoặc extra-index-url trỏ tới package index nội bộ. Cần đặc biệt thận trọng khi kết hợp nhiều index: pip không xem một index là nguồn ưu tiên an toàn tuyệt đối cho mọi package trong mọi trường hợp. Nên dùng repository proxy có namespace và policy rõ ràng, pin phiên bản, hash-checking mode hoặc công cụ lock phù hợp. Không dùng trusted-host như một cách chữa lỗi TLS thông thường vì nó làm suy yếu xác minh kết nối.

## 6. Credential và quyền truy cập repository

CI runner cần credential để đọc package private hoặc publish artifact. Credential này phải được xem là secret và cấp đúng phạm vi.

Các nguyên tắc:

- Dùng token chỉ đọc cho job build thông thường.
- Dùng token ghi riêng cho job publish.
- Tách credential theo môi trường hoặc repository khi cần.
- Ưu tiên token ngắn hạn hoặc workload identity nếu hệ thống hỗ trợ.
- Không truyền token qua command line nếu có thể xuất hiện trong process listing hoặc log.
- Không ghi nội dung settings file có secret vào log.
- Không cache file credential trong workspace hoặc cache dùng chung.
- Thu hồi và xoay vòng token khi có nghi ngờ bị lộ.
- Giới hạn IP, repository hoặc namespace nếu dịch vụ hỗ trợ.

Một pull request từ fork là nguồn mã chưa được tin cậy. Không cấp secret đọc package nội bộ hoặc credential publish cho job chạy mã đó nếu không có cơ chế bảo vệ rõ ràng. Có thể chạy bộ kiểm tra không cần secret trước, rồi chỉ cấp quyền trong job riêng sau khi thay đổi đã qua review và thỏa chính sách.

## 7. Cache dependency: tăng tốc nhưng không thay thế kiểm soát nguồn

Cache giữ lại package đã tải để lần build sau không phải tải lại. Cache có thể nằm ở nhiều lớp:

1. Cache cục bộ của package manager trên runner.
2. Cache phân tán do CI platform cung cấp.
3. Cache phía repository manager hoặc proxy.
4. Cache của công cụ build như Gradle hoặc Maven.
5. Cache image layer của container builder.

Các lớp này có mục tiêu khác nhau. Repository manager kiểm soát nguồn và lưu trữ package dùng chung. CI cache giảm thời gian giữa các lần chạy. Local cache giúp build lặp lại trên cùng runner. Không nên nhầm cache với kho lưu trữ artifact phát hành.

### 7.1. Chọn cache key

Cache key cần phản ánh đầu vào quyết định nội dung cache. Với dependency, các thành phần thường dùng gồm:

- Hệ điều hành và kiến trúc runner.
- Phiên bản JDK hoặc runtime.
- Phiên bản package manager.
- Lockfile hoặc file khai báo dependency.
- Cấu hình repository có ảnh hưởng đến nguồn tải.
- Phiên bản build tool hoặc wrapper.

Ví dụ, cache Gradle có thể phân biệt theo hệ điều hành, JDK và hash của các file Gradle liên quan. Khi lockfile hoặc build script thay đổi, key mới giúp tránh tái sử dụng cache không còn phù hợp.

Không nên đặt cache key chỉ theo tên nhánh nếu các nhánh có thể dùng dependency khác nhau. Cũng không nên chia sẻ cache giữa job có mức tin cậy khác nhau nếu nội dung cache có thể bị ghi bởi mã chưa được tin cậy.

### 7.2. Cache poisoning

Cache poisoning xảy ra khi nội dung không đáng tin cậy được ghi vào cache rồi được dùng lại bởi pipeline khác. Rủi ro tăng khi:

- Job từ pull request bên ngoài có quyền ghi cache dùng chung.
- Cache dùng chung giữa nhánh không tin cậy và nhánh phát hành.
- Cache không phân biệt hệ điều hành hoặc phiên bản toolchain.
- Nội dung cache được dùng mà không xác minh checksum.
- Credential hoặc file cấu hình nhạy cảm bị đưa vào cache.

Biện pháp giảm thiểu:

- Tách cache theo phạm vi tin cậy.
- Hạn chế job nào có quyền ghi cache.
- Dùng lockfile và checksum/signature verification.
- Không cache secret, token hoặc file settings chứa credential.
- Có thể xóa cache theo quy trình khi nghi ngờ bị nhiễm.
- Giữ đường build sạch để xác minh độc lập với cache.

### 7.3. Cache không được là nguồn sự thật duy nhất

Một build thành công nhờ cache không chứng minh rằng mọi dependency vẫn có thể tải từ nguồn được kiểm soát. Nên có các lần build sạch định kỳ hoặc trong release pipeline để xác minh:

- Repository nội bộ còn phục vụ đầy đủ dependency.
- Lockfile và checksum thực sự đủ để tái tạo.
- Không có dependency chỉ tồn tại trong cache cá nhân của một runner.
- Các package cần thiết còn được giữ theo retention policy.
- Cấu hình nguồn không bị thay đổi ngoài dự kiến.

Có thể dùng cache để tăng tốc build thường ngày, nhưng cần có một cơ chế xác minh độc lập và khả năng tái tạo bản phát hành.

## 8. Quản lý metadata, retention và tính sẵn sàng

Repository manager không chỉ lưu file package. Nó còn lưu metadata, phiên bản, thông tin checksum, cache response và quan hệ giữa artifact.

Cần xác định:

- Metadata release được giữ ổn định như thế nào.
- Snapshot hoặc package phát triển có TTL ra sao.
- Cache của metadata động được làm mới khi nào.
- Package bị thu hồi hoặc phát hiện lỗ hổng được xử lý ra sao.
- Phiên bản cũ cần giữ bao lâu để tái tạo release.
- Dung lượng, backup và phục hồi repository được quản lý thế nào.

Không nên xóa package chỉ vì nó không còn là phiên bản mới nhất. Nếu package đã được dùng để tạo artifact production, giữ nó trong thời gian phù hợp giúp điều tra và tái tạo. Ngược lại, cache snapshot hoặc metadata thay đổi liên tục cần TTL phù hợp để tránh dùng trạng thái cũ quá lâu.

Repository manager cũng là dịch vụ quan trọng của pipeline. Cần theo dõi:

- Tỷ lệ request thành công và lỗi.
- Độ trễ tải package.
- Cache hit ratio.
- Dung lượng lưu trữ và tốc độ tăng.
- Lỗi xác thực hoặc truy cập bị từ chối.
- Lỗi upstream và số lần retry.
- Các package bị chặn bởi policy.

Có thể cấu hình nhiều node hoặc backup theo năng lực nền tảng. Tuy nhiên, tính sẵn sàng không được đánh đổi bằng cách tự động fallback sang nguồn không được kiểm soát.

## 9. Ghi nhận nguồn gốc dependency trong build

Để điều tra một bản build, nhóm cần biết dependency thực tế được sử dụng, không chỉ biết file khai báo ban đầu.

Có thể ghi lại:

- Tọa độ package, phiên bản và repository nguồn.
- Checksum hoặc digest.
- Phiên bản package manager và build tool.
- Lockfile hoặc dependency graph.
- Thời điểm tải và lần build sử dụng.
- Kết quả kiểm tra lỗ hổng và license.
- Provenance của artifact cuối cùng.

Với Gradle, có thể xuất dependency report hoặc dependency insight để hiểu vì sao một phiên bản được chọn. Với Maven, dependency tree giúp xem dependency bắc cầu và phiên bản được giải quyết. Báo cáo cần gắn với commit và artifact phát hành.

Khi một dependency có lỗ hổng, nhóm có thể truy ngược:

1. Package và phiên bản bị ảnh hưởng là gì?
2. Dependency đó được kéo trực tiếp hay gián tiếp?
3. Những artifact hoặc phiên bản sản phẩm nào chứa nó?
4. Artifact được tạo từ commit và pipeline nào?
5. Có bản sửa hoặc phiên bản thay thế đã được kiểm tra chưa?
6. Cần build và triển khai lại những dịch vụ nào?

SBOM và dependency graph giúp trả lời các câu hỏi này nhanh hơn.

## 10. Cổng chất lượng cho dependency

Dependency có thể được kiểm tra trước khi merge, trước khi publish artifact hoặc trước khi triển khai production. Mỗi giai đoạn có mục đích khác nhau.

| Giai đoạn | Kiểm tra phù hợp |
|---|---|
| Pull request | Package mới, thay đổi lockfile, license, version range và repository source |
| Build | Checksum, chữ ký, dependency resolution và khả năng tải từ nguồn được phép |
| Publish | Metadata, provenance, SBOM và artifact digest |
| Release | Vulnerability policy, license policy, nguồn gốc và ngoại lệ đã duyệt |
| Production | Artifact đã xác minh, không resolve dependency mới trong lúc triển khai |

Một số quy tắc có thể được tự động hóa:

- Không dùng package từ registry ngoài allowlist.
- Không dùng version range hoặc dynamic version trong release build nếu chính sách yêu cầu pin.
- Không chấp nhận package có checksum sai.
- Không chấp nhận signature không nằm trong tập tin cậy.
- Không cho phép package có lỗ hổng vượt ngưỡng bị chặn nếu chưa có ngoại lệ.
- Không publish package nội bộ từ job không có quyền ghi.
- Không để production tải dependency mới trong lúc khởi động nếu artifact có thể đóng gói dependency trước đó.

Cổng chất lượng cần có lý do rõ ràng và chủ sở hữu. Cảnh báo license hoặc lỗ hổng mức thấp có thể cần review, trong khi checksum sai hoặc nguồn package không được phép nên làm pipeline thất bại.

## 11. Ví dụ luồng dependency có kiểm soát cho Java

Giả sử một dịch vụ Java dùng Maven hoặc Gradle, có thư viện nội bộ và package công khai.

Luồng đề xuất:

1. Nhà phát triển khai báo dependency và cập nhật lockfile hoặc metadata xác minh.
2. Pull request chạy kiểm tra diff dependency, license, vulnerability và repository policy.
3. CI runner nhận credential chỉ đọc từ secret manager.
4. Maven hoặc Gradle chỉ truy cập repository nội bộ.
5. Repository manager lấy package từ upstream đã được allowlist, xác minh theo chính sách và cache.
6. Package manager xác minh checksum hoặc signature theo cấu hình.
7. Build và test chạy trên dependency graph đã được giải quyết.
8. Pipeline tạo artifact, SBOM và provenance.
9. Artifact được lưu trong registry có kiểm soát và gắn digest.
10. Release pipeline promote artifact đã xác minh mà không resolve dependency lại.

Một điểm quan trọng: dependency resolution phải diễn ra trong giai đoạn build. Khi triển khai, ứng dụng nên nhận artifact hoàn chỉnh đã đóng gói dependency cần thiết. Điều này giúp môi trường production không phụ thuộc vào việc registry bên ngoài có sẵn sàng ở thời điểm khởi động hay không.

## 12. Những lỗi thường gặp khi tải dependency

| Biểu hiện | Rủi ro | Hướng xử lý |
|---|---|---|
| Mỗi project khai báo registry riêng | Khó kiểm soát nguồn và credential | Chuẩn hóa repository qua settings hoặc convention |
| Cho phép fallback sang registry công khai | Có thể chọn package sai namespace | Dùng mirror/proxy và allowlist tập trung |
| Dùng phiên bản động trong release | Kết quả build thay đổi theo thời gian | Pin version và lock dependency |
| Chỉ dựa vào checksum cùng nguồn | Kẻ tấn công có thể thay cả package và checksum | Kết hợp signature, provenance và nguồn tin cậy |
| Dùng token ghi cho mọi job | Tăng tác động khi runner bị xâm nhập | Tách quyền đọc và publish |
| Cache chia sẻ giữa job tin cậy và không tin cậy | Có thể bị cache poisoning | Tách cache theo trust boundary |
| Cache package không có retention rõ | Mất khả năng tái tạo hoặc phình dung lượng | Đặt retention theo loại package |
| Không kiểm tra dependency bắc cầu | Lỗ hổng có thể đến từ package gián tiếp | Lưu dependency graph và scan toàn bộ |
| Cài dependency khi ứng dụng khởi động production | Tăng phụ thuộc mạng và khó kiểm soát phiên bản | Đóng gói dependency vào artifact |
| Bỏ qua lỗi TLS bằng trusted-host | Suy yếu xác minh kết nối | Cấu hình CA và chứng chỉ đúng cách |

## 13. Checklist cấu hình nguồn dependency

**Nguồn và repository**

- [ ] Registry hoặc repository được phê duyệt và có chủ sở hữu.
- [ ] CI sử dụng endpoint nội bộ hoặc nguồn đã được kiểm soát.
- [ ] Namespace package nội bộ được bảo vệ khỏi dependency confusion.
- [ ] Release và snapshot được phân tách theo chính sách.
- [ ] Không có fallback ngoài allowlist.

**Danh tính và tính toàn vẹn**

- [ ] Kết nối sử dụng TLS và xác thực phù hợp.
- [ ] Checksum được xác minh.
- [ ] Chữ ký được kiểm tra nếu chính sách yêu cầu.
- [ ] Dependency có phiên bản cụ thể và lock state được review.
- [ ] SBOM hoặc dependency report được lưu theo yêu cầu.
- [ ] Nguồn và provenance có thể truy vết.

**Credential và quyền**

- [ ] Job build dùng token chỉ đọc.
- [ ] Job publish có credential ghi riêng.
- [ ] Token được cấp từ secret manager và không commit.
- [ ] Mã từ fork không nhận secret nhạy cảm.
- [ ] Credential không bị đưa vào cache hoặc log.
- [ ] Có quy trình xoay vòng và thu hồi token.

**Cache và tái lập**

- [ ] Cache key phản ánh lockfile, toolchain và nền tảng.
- [ ] Cache được phân tách theo trust boundary.
- [ ] Chỉ job phù hợp được ghi cache.
- [ ] Có build sạch định kỳ hoặc trong release pipeline.
- [ ] Repository giữ package đủ lâu để tái tạo release.
- [ ] Cache không phải nguồn duy nhất của dependency.

## 14. Kết luận

Tải dependency từ nguồn được kiểm soát là nền tảng để tạo ra build có thể tin cậy và tái tạo. Nhóm cần thống nhất repository được phép, quản lý namespace nội bộ, dùng proxy hoặc virtual repository khi phù hợp, xác minh checksum và chữ ký, pin phiên bản, lock dependency và cấp credential theo quyền tối thiểu.

Cache giúp giảm thời gian build, nhưng chỉ là lớp tối ưu. Nguồn package, tính toàn vẹn và dependency graph mới là căn cứ để xác minh đầu vào. Khi mỗi artifact có thể truy ngược đến commit, package, phiên bản, repository và kết quả kiểm tra, pipeline có thể phát hành nhanh hơn mà vẫn giữ được khả năng kiểm soát và điều tra chuỗi cung ứng phần mềm.

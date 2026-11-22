# Giới hạn quyền của tiến trình build và thay đổi đến từ mã không tin cậy

Maven và Gradle thực thi nhiều loại code trong quá trình build: build script, plugin, extension, annotation processor, code generator, test và shell command. Code đó thường chạy với quyền của tài khoản đang khởi chạy build. Nếu build process có thể đọc toàn bộ home directory, truy cập Docker socket, dùng cloud credential hoặc ghi vào cache dùng chung, một thay đổi độc hại trong pull request có thể tận dụng các quyền đó.

Vì vậy, an toàn build không chỉ phụ thuộc vào việc chọn plugin đáng tin cậy. Cần giới hạn quyền của chính tiến trình build và xác định rõ mức độ tin cậy của source đang được build. Mã từ nhánh đã được review có thể chạy trong pipeline có quyền phát hành theo policy; mã từ fork hoặc pull request chưa review cần chạy trong môi trường ít quyền hơn, không có release secret và không thể ghi vào tài nguyên mà pipeline phát hành tin cậy sử dụng.

Bài này trình bày cách áp dụng nguyên tắc least privilege cho tài khoản, filesystem, network, process, secret, cache và artifact; cách tách pipeline cho mã không tin cậy; cùng các điểm cấu hình thực tế trong Maven, Gradle và CI.

## 1. Build process có thể làm gì?

Build tool không phải một trình phân tích cấu hình thụ động. Khi build chạy, nó có thể nạp và thực thi code từ nhiều nguồn:

- Maven/Gradle plugin và dependency của plugin.
- Maven core extension, Gradle init script và convention plugin.
- Annotation processor và compiler plugin.
- Build logic trong pom.xml, build.gradle hoặc build.gradle.kts.
- Test code, integration test và test framework.
- Code generator và executable bên ngoài.
- Script shell, PowerShell hoặc lệnh do task gọi.
- Wrapper script/JAR và build tool distribution.

Code được thực thi thường có quyền của OS user và tiến trình cha. Nếu runner có thể đọc một file, mở kết nối mạng hoặc gọi một chương trình, plugin/script trong cùng quyền đó thường cũng có thể thử làm việc tương tự.

Ví dụ, một job build có thể có các quyền:

| Tài nguyên | Quyền thường cần | Rủi ro nếu cấp quá rộng |
|---|---|---|
| Workspace source | Đọc; ghi output build | Sửa source, script hoặc artifact |
| User home | Đọc một số cache/config cần thiết | Lấy SSH key, token, settings và dữ liệu cá nhân |
| Maven/Gradle cache | Đọc artifact; có thể ghi cache | Đầu độc cache được job khác tin cậy sử dụng |
| Network | Truy cập repository và dịch vụ cần thiết | Gửi source/secret ra ngoài hoặc tải executable tùy ý |
| Environment variables | Đọc biến phục vụ build | Lấy token, signing credential hoặc cloud key |
| Docker/container runtime | Thường không cần cho compile thông thường | Có thể mở rộng quyền tới host nếu socket được mount |
| Artifact repository | Đọc dependency | Ghi đè hoặc phát hành artifact trái phép |
| Signing service | Ký release đã được phê duyệt | Ký artifact do mã không tin cậy tạo ra |

Không phải build nào cũng cần mọi quyền trên. Hãy xác định task thực sự cần gì và cấp quyền tương ứng.

## 2. Xác định trust boundary của source

Không phải mọi commit đều có cùng mức độ tin cậy. Một pull request từ nhánh nội bộ đã được review, một pull request từ fork bên ngoài và một commit trên protected release branch cần được xử lý theo những chính sách khác nhau.

Các nguồn code thường gặp:

| Nguồn | Mức độ tin cậy điển hình | Cách xử lý quyền |
|---|---|---|
| Commit trên protected branch | Đã qua review và policy của dự án | Có thể chạy build chính; quyền publish vẫn cần job riêng |
| Pull request từ nhánh nội bộ | Chưa được merge/review hoàn tất | Chạy validation với quyền hạn chế |
| Pull request từ fork bên ngoài | Không kiểm soát được tác giả và code | Không cấp release secret; runner/cache riêng |
| Dependency/plugin mới | Code bên thứ ba | Review nguồn, version, checksum và quyền thực thi |
| Generated code từ schema/input ngoài | Phụ thuộc nguồn input và generator | Kiểm tra generator và output trước khi đưa vào release |
| Script tải từ mạng | Phụ thuộc endpoint và nội dung tải | Pin nguồn/version/digest; hạn chế network và thực thi |

Mã không tin cậy không chỉ là file .java. Người gửi pull request có thể thay đổi build file, test, wrapper, CI workflow, annotation processor configuration hoặc script. Các thay đổi này có thể chạy trước khi ứng dụng được compile hoặc trước khi bước kiểm tra quyền diễn ra.

### 2.1. Build file cũng là code

Một pull request có thể sửa:

- pom.xml, parent POM hoặc .mvn/extensions.xml.
- settings.gradle, build.gradle hoặc convention plugin.
- gradlew, gradlew.bat, Gradle Wrapper JAR/properties.
- Maven Wrapper scripts/properties.
- CI workflow và shell/PowerShell script.
- Test hoặc code generator.

Review chỉ các file source ứng dụng là chưa đủ. Thay đổi build logic có thể thêm plugin, đổi repository, chạy command hoặc đọc secret ngay trong quá trình build.

### 2.2. Test cũng có thể thực thi hành vi tùy ý

Test runner nạp và chạy code test. Một test có thể gọi process, truy cập file, mở network connection hoặc đọc environment variables. Vì vậy, không nên cấp production secret cho job chạy test từ pull request chưa tin cậy.

Chạy test trong CI không biến test code thành code an toàn. Hãy áp dụng cùng trust boundary cho test, plugin và script như với phần source còn lại.

## 3. Nguyên tắc least privilege

Least privilege nghĩa là mỗi tiến trình, user hoặc job chỉ nhận những quyền tối thiểu cần để hoàn thành nhiệm vụ.

Áp dụng cho build:

1. **Tài khoản:** chạy bằng user riêng, không dùng root/Administrator nếu không cần.
2. **Filesystem:** chỉ mount hoặc cấp quyền ghi vào workspace, cache và output cần thiết.
3. **Network:** chỉ cho phép truy cập repository và dịch vụ cần thiết.
4. **Credential:** chỉ cấp token đúng phạm vi, đúng thời điểm và thời hạn ngắn.
5. **Process:** giới hạn khả năng khởi chạy privileged process hoặc truy cập container runtime.
6. **Cache:** không để job không tin cậy ghi dữ liệu mà release job tin cậy sử dụng.
7. **Publication:** chỉ job được bảo vệ mới có quyền ký và publish release.
8. **Thời gian sống:** ưu tiên runner ephemeral và xóa trạng thái sau job.

Quyền tối thiểu không chỉ giảm khả năng tấn công. Nó còn giúp điều tra dễ hơn vì mỗi job có một phạm vi tài nguyên rõ ràng.

## 4. Tách job kiểm thử và job phát hành

Một trong những kiểm soát hiệu quả nhất là tách pipeline chạy mã chưa tin cậy khỏi pipeline có quyền phát hành.

~~~text
Pull request / fork chưa được tin cậy
             |
             v
Validation job
  - Runner dùng một lần
  - Dependency access chỉ đọc
  - Không có release/signing secret
  - Không ghi cache dùng chung với release
  - Compile, test, static analysis
             |
             v
Review và merge vào protected branch
             |
             v
Protected build
  - Checkout commit đã review
  - Runner sạch
  - Build và tạo artifact
  - Tạo SBOM/provenance
             |
             v
Release gate
             |
             v
Release job riêng
  - Credential publish giới hạn
  - Signing key qua dịch vụ bảo vệ
  - Xác minh digest/signature
  - Publish version bất biến
~~~

Job validation cần đủ quyền để compile và test, nhưng không cần quyền phát hành production. Job release chỉ chạy từ commit đã được bảo vệ và được policy cho phép.

### 4.1. Không truyền secret vào job chạy pull request không tin cậy

Nếu build script hoặc test có thể đọc token, chỉ cần một thay đổi trong pull request để gửi token ra ngoài. Ẩn secret khỏi log không giải quyết được vấn đề này; code vẫn có thể đọc giá trị trong process.

Đối với pull request từ fork hoặc nguồn chưa tin cậy:

- Không cấp signing key, release token hoặc cloud credential có quyền cao.
- Dùng read-only token riêng nếu cần truy cập private dependency.
- Nếu private dependency không thể được truy cập an toàn, cân nhắc một validation path không cần credential đó hoặc dùng dependency mirror/cache được kiểm soát.
- Không chạy lại workflow từ fork trong context có secret chỉ để làm CI xanh.
- Không dùng artifact hoặc cache do job không tin cậy tạo ra như đầu vào trực tiếp của release.

### 4.2. Phân biệt quyền đọc và quyền ghi

Một build kiểm thử thường chỉ cần quyền đọc dependency. Quyền ghi repository nên chỉ có trong job publish.

Nên tách:

- Token đọc dependency.
- Token publish snapshot.
- Token publish release.
- Quyền ký artifact.
- Quyền deploy ứng dụng.

Không dùng một token có toàn bộ quyền cho mọi giai đoạn. Nếu token read-only bị lộ, phạm vi thiệt hại sẽ nhỏ hơn token có quyền ghi/xóa release.

### 4.3. Chú ý trigger và workflow context

Mỗi CI provider có quy tắc riêng về workflow nào được chạy, source workflow được lấy từ nhánh nào và secret có được cung cấp cho pull request từ fork hay không. Cần đọc đúng semantics của nền tảng CI đang dùng.

Không giả định rằng một điều kiện kiểm tra branch ở cuối workflow đủ bảo vệ secret. Nếu code không tin cậy đã được checkout và chạy trước điều kiện đó, secret có thể đã bị truy cập. Đặt ranh giới tin cậy ở cấp job/workflow và quyền runner.

## 5. Giới hạn quyền của OS user

Build nên chạy bằng user riêng, không phải tài khoản developer có SSH key, browser profile, cloud CLI login hoặc quyền quản trị máy.

Các thực hành hữu ích:

- Dùng user service riêng cho CI runner.
- Không chạy Maven/Gradle bằng root hoặc Administrator.
- Không mount thư mục home cá nhân vào container build.
- Không cấp quyền đọc thư mục chứa private key, password manager hoặc token cá nhân.
- Giới hạn quyền ghi vào workspace và cache.
- Tách user hoặc VM giữa job không cùng trust level.
- Thu hồi credential sau khi job kết thúc nếu credential có vòng đời ngắn.

Nếu build báo lỗi permission, hãy xác định file hoặc thư mục nào cần quyền. Sửa owner/ACL của workspace hoặc output cụ thể thay vì chạy lại toàn bộ build với quyền quản trị.

## 6. Giới hạn filesystem và mount

Một plugin/script có thể đọc hoặc sửa file mà OS user được phép truy cập. Cần giới hạn filesystem mà runner nhìn thấy.

### 6.1. Workspace riêng

Mỗi job nên có workspace riêng. Không để pull request chưa tin cậy ghi vào source checkout, output hoặc thư mục tạm mà job release sau đó sử dụng.

Workspace ephemeral giúp giảm nguy cơ:

- File độc hại còn sót từ job trước.
- Script bị thay thế nhưng không xuất hiện trong Git diff.
- Artifact cũ bị trộn với artifact mới.
- Symlink hoặc file được tạo ngoài dự kiến.

### 6.2. Không mount toàn bộ home directory

Home directory có thể chứa:

- ~/.ssh/ và private key.
- ~/.m2/settings.xml với credential repository.
- ~/.gradle/gradle.properties hoặc init script.
- Cloud CLI credentials.
- Git credential helper hoặc token.
- Cache và cấu hình cá nhân khác.

Nếu container build được mount toàn bộ home, code chạy trong container có thể đọc các file đó nếu quyền cho phép. Hãy dùng home/cache riêng cho job và chỉ mount dữ liệu cần thiết.

### 6.3. Cẩn thận với symlink và output path

Task generator hoặc script có thể tạo symlink hay ghi file theo path do input điều khiển. Nếu job sau đó chạy với quyền cao hoặc copy output ra vị trí nhạy cảm, path không được kiểm tra có thể dẫn đến ghi ngoài workspace.

Với generator nhận input không tin cậy:

- Giới hạn output directory.
- Chuẩn hóa và kiểm tra đường dẫn trước khi ghi.
- Không chạy bước copy/deploy privileged trên output chưa được xác minh.
- Tránh mount thư mục host nhạy cảm ở chế độ ghi.

## 7. Giới hạn network access

Build thường cần tải plugin và dependency, nhưng không phải task nào cũng cần truy cập Internet tùy ý.

Một runner có outbound network rộng có thể cho phép plugin/script:

- Gửi source code hoặc secret ra ngoài.
- Tải và thực thi executable không được review.
- Gọi API cloud hoặc dịch vụ nội bộ.
- Truy cập metadata endpoint của hạ tầng.
- Thay đổi nguồn dependency trong lúc build.

Các biện pháp:

- Cho phép truy cập repository manager nội bộ đã được phê duyệt.
- Hạn chế outbound hostname/port theo nhu cầu.
- Dùng proxy egress có log và policy nếu phù hợp.
- Chặn truy cập đến service metadata hoặc mạng quản trị không cần thiết.
- Tách network policy của pull request và release job.
- Không cho build tùy ý truy cập Docker daemon hoặc control plane.

Một mô hình phổ biến:

~~~text
Build runner
    |
    | HTTPS, read-only
    v
Repository manager nội bộ
    |
    | Upstream được kiểm soát
    v
Public artifact repositories
~~~

Repository manager có thể cache và kiểm soát nguồn upstream. Điều đó giảm số endpoint mà runner cần truy cập trực tiếp. Tuy nhiên, repository manager vẫn cần policy, audit và bảo vệ credential riêng.

## 8. Container và sandbox

Container có thể giúp đóng gói JDK/build tool và giới hạn filesystem/network, nhưng container mặc định không phải sandbox tuyệt đối.

### 8.1. Dùng container đúng cách

Một build container nên:

- Chạy non-root.
- Không dùng privileged mode nếu không cần.
- Không mount Docker socket của host.
- Chỉ mount workspace và cache cần thiết.
- Dùng image được pin theo version/digest.
- Giới hạn CPU, memory, process và thời gian.
- Có filesystem read-only cho phần toolchain nếu phù hợp.
- Không chứa secret cố định trong image layer.

Nếu mount Docker socket hoặc Docker named pipe, process trong container có thể điều khiển Docker daemon trên host. Đây có thể tương đương quyền rất cao trên host. Chỉ cấp quyền này cho job thật sự cần và có trust level phù hợp.

### 8.2. Ephemeral VM cho mã không tin cậy

Với pull request từ fork hoặc plugin chưa được tin cậy, VM dùng một lần có thể tạo ranh giới cô lập mạnh hơn container chia sẻ kernel với host. Sau job, hủy VM và cache tạm.

Mức cô lập cần thiết phụ thuộc threat model và hạ tầng. Container vẫn hữu ích, nhưng nếu job chạy code tùy ý và có quyền truy cập host resource thì chỉ đóng gói bằng container không đủ.

### 8.3. Giới hạn tài nguyên

Build script có thể vô tình hoặc cố ý tiêu thụ tài nguyên:

- Tạo nhiều process.
- Chạy vòng lặp vô hạn.
- Sinh file rất lớn.
- Dùng hết memory hoặc disk.
- Tạo quá nhiều thread.
- Chờ network không giới hạn.

CI runner nên có quota CPU, memory, disk, process count và timeout. Điều này giảm ảnh hưởng của lỗi hoặc hành vi từ chối dịch vụ trong build.

## 9. Credential, environment variable và signing key

Credential được cấp cho build process có thể được đọc bởi plugin, test hoặc script chạy trong cùng quyền. Vì vậy, cách an toàn nhất cho job không tin cậy là không cấp secret có giá trị.

### 9.1. Tránh secret trong build file

Không ghi credential thật vào:

- pom.xml.
- build.gradle hoặc build.gradle.kts.
- settings.gradle hoặc settings.gradle.kts.
- gradle.properties được commit.
- Shell/PowerShell script.
- Source code, resource hoặc manifest.
- URL repository chứa username/password.

Dùng CI secret store, Maven settings file được bảo vệ hoặc cơ chế credential injection phù hợp. Nhưng cần nhớ: nếu secret được đưa vào environment của process build, plugin/script trong process đó có thể đọc nó.

### 9.2. Secret ngắn hạn và quyền hẹp

Ưu tiên:

- Token chỉ đọc dependency cho validation job.
- Token publish có thời hạn ngắn và chỉ dùng trong release job.
- Quyền ký thông qua signing service thay vì private key file được mount vào runner.
- OIDC hoặc workload identity có điều kiện trust chặt nếu hạ tầng hỗ trợ.
- Không dùng credential cá nhân của developer cho CI.

OIDC không tự động an toàn chỉ vì dùng token ngắn hạn. Trust policy cần giới hạn repository, branch, workflow, environment và audience theo nền tảng. Nếu token có thể được cấp cho workflow chạy từ fork, ranh giới bảo vệ vẫn bị phá vỡ.

### 9.3. Không để secret trong log và artifact

Build log, test report, diagnostic dump và generated file có thể vô tình chứa environment hoặc credential. Không in toàn bộ environment. Không tạo debug report chứa settings file. Không upload workspace nguyên trạng nếu trong đó có file secret.

Masking log chỉ là lớp hỗ trợ; nó không ngăn code đọc và gửi secret qua network. Không cấp secret cho job không tin cậy vẫn là kiểm soát chính.

## 10. Bảo vệ Maven trong môi trường build

### 10.1. Maven settings.xml

Maven thường lấy credential repository từ settings.xml, trong phần servers, với ID khớp repository hoặc mirror. File này nên nằm ngoài source repository và chỉ được cấp cho job cần quyền tương ứng.

Ví dụ cấu hình dạng placeholder:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-read</id>
            <username>READ_USER</username>
            <password>TOKEN_FROM_SECRET_STORE</password>
        </server>
    </servers>
</settings>
~~~

Đối với job pull request, settings chỉ nên có credential read-only nếu thật sự cần private dependency. Release settings nên được cấp trong job riêng sau khi source đã qua review.

### 10.2. Maven local repository

Maven local repository mặc định thường nằm trong ~/.m2/repository. Cache này chứa artifact đã tải và có thể được chia sẻ giữa nhiều build nếu runner dùng chung user.

Không để job không tin cậy ghi vào local repository được job release tin cậy sử dụng nếu không có kiểm soát. Có thể cấu hình local repository riêng cho job:

~~~bash
./mvnw -Dmaven.repo.local=/work/cache/m2-pr-123 clean verify
~~~

Đường dẫn chỉ là ví dụ. CI nên tạo thư mục riêng cho job hoặc trust class, kiểm soát quyền truy cập và xóa khi hết vòng đời cần thiết.

### 10.3. Maven core extension và wrapper

Review .mvn/extensions.xml, extension trong POM và Maven Wrapper scripts/configuration. Core extension có thể được nạp trước khi lifecycle chạy. Wrapper script/JAR là code bootstrap và cần được bảo vệ trong review.

Không cho phép pull request thay wrapper hoặc extension rồi chạy trong job có release secret. Nếu cần kiểm tra thay đổi wrapper từ pull request, thực hiện trong job không có secret và runner cô lập.

### 10.4. Tách install và deploy

mvn install cài artifact vào local repository; mvn deploy upload lên remote repository. Validation job thường chỉ cần package/verify hoặc install trong local cache riêng. Quyền deploy nên được cấp riêng cho release job.

## 11. Bảo vệ Gradle trong môi trường build

### 11.1. Gradle user home và cache

Gradle lưu distribution, dependency cache, daemon state, init script và một số cấu hình trong Gradle User Home, thường là ~/.gradle.

Nếu nhiều job dùng chung thư mục này, cần xem xét:

- Job nào có quyền ghi?
- Job nào có quyền đọc?
- Init script nào được nạp?
- Cache có được chia sẻ qua trust boundary không?
- Daemon có còn chạy sau job không?

Có thể dùng Gradle User Home riêng cho job qua biến GRADLE_USER_HOME:

~~~bash
GRADLE_USER_HOME=/work/gradle-home-pr-123 ./gradlew --no-daemon clean build
~~~

Ví dụ trên dành cho shell Unix-like; trên Windows có thể đặt environment variable theo cú pháp của PowerShell/CI. Tạo home riêng giúp tách cache và init script, nhưng không thay thế việc giới hạn quyền của process.

### 11.2. Gradle daemon

Gradle daemon là tiến trình nền tái sử dụng để tăng tốc build. Daemon có thể giữ state và chạy dưới cùng user của runner. Không nên chia sẻ daemon giữa build có mức độ tin cậy khác nhau hoặc giữa user khác nhau.

Với job untrusted, có thể dùng --no-daemon và runner ephemeral. Gradle vẫn có thể tạo single-use daemon tùy yêu cầu JVM arguments; điều quan trọng là process không được tái sử dụng qua trust boundary và runner bị hủy sau job.

Sau khi hoàn thành trên runner dài hạn, có thể dừng daemon bằng:

~~~bash
./gradlew --stop
~~~

Không dựa vào --stop như ranh giới bảo mật duy nhất. User home riêng, process isolation và runner lifecycle mới là các lớp kiểm soát chính.

### 11.3. Init script và Gradle properties

Kiểm tra init script trong Gradle User Home hoặc được truyền qua command line. Init script có thể thêm repository, plugin hoặc thay đổi build behavior ngoài repository source.

Không dùng chung gradle.properties có credential hoặc init script cá nhân cho job chạy mã không tin cậy. Cấp file cấu hình riêng theo trust level và tránh đặt secret trong file có thể được job khác đọc.

### 11.4. Phân biệt dependency cache và build cache

Dependency cache lưu module/metadata đã tải. Build cache lưu output task. Cả hai đều có thể bị ảnh hưởng nếu job không tin cậy có quyền ghi vào cache dùng chung.

Remote build cache nên có quyền ghi giới hạn. Một mô hình thường dùng là:

- Validation job không tin cậy chỉ đọc cache hoặc dùng cache riêng.
- Protected build có quyền ghi cache dành cho protected branch.
- Release job chỉ lấy output từ nguồn đã được xác minh hoặc tự build lại.

## 12. Bảo vệ artifact và output từ job không tin cậy

Artifact do pull request tạo ra hữu ích cho việc xem test report hoặc tải bản preview, nhưng không nên tự động trở thành artifact release.

Rủi ro:

- Artifact chứa file thực thi hoặc backdoor.
- Test report chứa dữ liệu nhạy cảm.
- Output đã bị sửa bởi plugin độc hại.
- Artifact dùng chung tên với release artifact.
- Job sau giải nén archive không an toàn vào workspace có quyền cao.

Thực hành tốt:

- Gắn artifact với commit, job và trust level.
- Không dùng artifact PR làm đầu vào release.
- Build lại từ protected commit trong runner sạch.
- Xác minh digest và provenance trước promotion.
- Kiểm tra nội dung archive và đường dẫn trước khi giải nén.
- Không để job không tin cậy ghi vào release bucket/repository.
- Giữ preview artifact trong khu vực riêng, có thời hạn.

### 12.1. Promotion và rebuild

Một mô hình release có thể build artifact từ commit đã review, xác minh rồi promote cùng artifact digest giữa các môi trường. Nếu tổ chức chọn rebuild ở giai đoạn release, build phải dùng cùng source commit và môi trường được kiểm soát.

Không nên promote artifact do một job untrusted tạo ra chỉ vì test đã xanh. Test pass không chứng minh artifact không có hành vi độc hại.

## 13. Kiểm soát repository và plugin source

Build plugin và dependency là code từ bên ngoài. Nguồn tải cần được giới hạn và kiểm soát.

### 13.1. Repository manager nội bộ

Repository manager có thể proxy/cache upstream, kiểm soát quyền và audit. Runner chỉ cần truy cập endpoint nội bộ được phê duyệt thay vì nhiều public repository.

Tuy nhiên, repository manager cần được cấu hình:

- Upstream allowlist hoặc policy phù hợp.
- Namespace nội bộ không rơi về public repository.
- Quyền read/write riêng.
- Release artifact bất biến.
- Audit log và retention.
- Kiểm tra metadata/checksum/signature theo chính sách.

### 13.2. Maven repository policy

Maven dùng repositories, pluginRepositories, settings.xml mirrors và distributionManagement cho các mục đích khác nhau. Kiểm tra mirror và profile để bảo đảm plugin/dependency được resolve từ nguồn được duyệt.

Credential trong servers phải ghép với ID thực tế Maven sử dụng. Không đưa token vào POM hoặc URL.

### 13.3. Gradle repository policy

Gradle có pluginManagement.repositories, dependencyResolutionManagement.repositories, project repositories, buildscript.repositories và publishing.repositories. Dùng repositoriesMode, content filter và exclusive content khi phù hợp để giới hạn nguồn cho group nội bộ.

Plugin DSL có thể resolve plugin marker trước implementation module. Khi dùng repository nội bộ, cần xác nhận marker và implementation đều được phục vụ hoặc mapping plugin ID đã được review.

## 14. Wrapper và build tool bootstrap

Wrapper chạy trước nhiều bước khác của build. Nếu wrapper script/JAR hoặc distribution URL bị thay đổi, code độc hại có thể chạy ngay từ đầu.

### 14.1. Gradle Wrapper

Các file quan trọng gồm:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Kiểm tra distribution URL và distributionSha256Sum nếu được cấu hình. Khi nâng version, xác minh checksum distribution từ nguồn chính thức/được tổ chức tin cậy và review toàn bộ diff của wrapper files.

### 14.2. Maven Wrapper

Maven Wrapper cũng có script bootstrap, properties và wrapper component tùy chế độ phân phối. Review thay đổi wrapper, distribution URL và nguồn Maven distribution. Nếu tổ chức dùng mirror, bảo vệ mirror và xác minh nội dung distribution theo policy.

### 14.3. Không tin wrapper chỉ vì nó nằm trong repository

Pull request có thể sửa wrapper. Khi chạy validation cho pull request, wrapper mới vẫn là code không tin cậy. Nếu cần chạy wrapper đó để kiểm tra, dùng runner không secret và không có quyền ghi vào tài nguyên release.

## 15. Cô lập cache và trạng thái giữa các job

Cache dùng chung là một ranh giới tin cậy quan trọng. Nếu job A không tin cậy ghi cache và job B tin cậy đọc lại, job B có thể nhận dữ liệu do A kiểm soát.

Các nguyên tắc:

- Phân vùng cache theo trust level, project và branch khi cần.
- Không cho PR từ fork ghi remote build cache dùng chung với release.
- Dùng quyền read-only cho cache trong validation job nếu phù hợp.
- Chỉ job tin cậy được ghi cache chia sẻ với release.
- Không dùng chung Gradle daemon hoặc workspace qua trust boundary.
- Không copy local Maven repository từ job untrusted sang release mà không có verification.
- Đặt retention và cleanup để tránh tích lũy file cũ.

Cache key nên phản ánh các đầu vào ảnh hưởng output. Tuy nhiên, key đúng không giải quyết được việc một bên không tin cậy có quyền ghi vào cache của bên tin cậy. Phân quyền ghi/đọc vẫn cần được thiết kế riêng.

## 16. Giới hạn resource và ngăn build làm cạn runner

Mã không tin cậy có thể gây quá tải dù không truy cập secret:

- Fork hàng nghìn process.
- Tạo file lớn hoặc lặp vô hạn.
- Dùng hết heap/native memory.
- Mở nhiều socket.
- Chiếm CPU hoặc thread.
- Chạy test không kết thúc.

Runner nên có:

- Job timeout.
- CPU và memory limit.
- Disk quota.
- Process/thread limit.
- Network timeout.
- Giới hạn concurrency.
- Cleanup sau job.

Các giới hạn nên phù hợp với workload Java thực tế để tránh build hợp lệ bị kill. Với task cần resource cao, cấp profile riêng có giới hạn rõ ràng và chỉ cho project/branch phù hợp.

## 17. Ví dụ cấu hình Maven cho validation job

Một validation job có thể dùng local repository riêng và settings chỉ đọc. Ví dụ:

~~~bash
./mvnw -Dmaven.repo.local=/work/cache/m2-pr-123 clean verify
~~~

CI có thể cấp một settings.xml riêng qua -s:

~~~bash
./mvnw -s /run/config/maven-readonly-settings.xml \
  -Dmaven.repo.local=/work/cache/m2-validation \
  -B clean verify
~~~

File settings chỉ nên chứa credential read-only nếu cần private dependency. Không dùng settings release có quyền deploy trong job chạy pull request.

Đối với release, dùng job riêng, checkout protected commit, settings có quyền publish giới hạn và signing service được bảo vệ. Không tái sử dụng workspace hoặc local repository có thể ghi bởi job không tin cậy.

## 18. Ví dụ cấu hình Gradle cho validation job

Gradle có thể dùng Gradle User Home riêng:

~~~bash
GRADLE_USER_HOME=/work/gradle-home-validation ./gradlew --no-daemon clean build
~~~

Trong CI, đặt biến môi trường theo cú pháp nền tảng. Nếu cần repository credential read-only, chỉ cấp biến đó trong validation job và không cấp token publish/signing.

Có thể giới hạn repository trong settings.gradle.kts:

~~~kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "companyPublic"
            url = uri("https://repo.example.com/repository/maven-public/")
        }
    }
}
~~~

Ví dụ này tập trung dependency repository. Plugin repository vẫn cần được cấu hình riêng trong pluginManagement. Nếu build dùng init script toàn cục, hãy kiểm tra và kiểm soát nó trong runner image.

## 19. Bảo vệ remote service và cloud identity

Build job đôi khi cần truy cập cloud để tải test data, publish image hoặc deploy. Không nên cấp role rộng chỉ để một task hoạt động.

Thực hành tốt:

- Dùng identity riêng cho mỗi pipeline/job.
- Giới hạn quyền theo resource, action và environment.
- Ưu tiên workload identity/OIDC với trust condition cụ thể nếu nền tảng hỗ trợ.
- Tránh lưu long-lived cloud key trong runner.
- Không cho PR untrusted nhận identity có quyền deploy.
- Giới hạn truy cập metadata endpoint của cloud VM/container nếu không cần.
- Audit việc cấp token và truy cập service.

Nếu build cần Docker để integration test, cân nhắc service/container test được quản lý hoặc runner chuyên dụng. Không tự động mount host Docker socket vào mọi build job.

## 20. Theo dõi hành vi của build process

Least privilege giảm quyền nhưng vẫn cần quan sát hành vi. Các tín hiệu hữu ích:

- Process nào được khởi chạy.
- Network destination và lượng dữ liệu gửi đi.
- File ngoài workspace được đọc/ghi.
- Repository và plugin version được resolve.
- Artifact được tạo và digest tương ứng.
- Secret nào được cấp cho job.
- Job chạy từ commit/branch/workflow nào.

CI log nên ghi nhận metadata đủ để điều tra nhưng không ghi secret. Network egress log, runner audit, repository audit và artifact provenance có thể giúp nối các sự kiện thành một chuỗi.

Không phải mọi kết nối mạng hoặc file access khác thường đều độc hại; plugin hợp lệ có thể cần tải dependency hoặc ghi cache. Hãy so sánh với behavior mong đợi và thay đổi đã review.

## 21. Quy trình khi nghi ngờ mã không tin cậy đã vượt quyền

Nếu phát hiện build job từ pull request đã đọc secret, ghi cache release hoặc truy cập tài nguyên ngoài dự kiến:

1. Dừng job và ngăn job tiếp theo sử dụng output của nó.
2. Lưu log, commit, workflow identity, runner identity và artifact digest.
3. Thu hồi/rotate credential có khả năng đã bị truy cập.
4. Kiểm tra audit log của repository, cloud, signing service và CI.
5. Xác định cache, artifact, workspace hoặc runner nào có thể bị ảnh hưởng.
6. Xóa hoặc cách ly cache/output bị nghi ngờ theo quy trình incident response.
7. Tạo runner sạch và tái build từ commit tin cậy.
8. Xác minh artifact digest, signature, SBOM và provenance.
9. Sửa permission, workflow trigger hoặc secret scope đã tạo ra lỗ hổng.
10. Ghi nhận nguyên nhân và kiểm tra các pipeline tương tự.

Không tiếp tục ký hoặc publish artifact được tạo trong một build có khả năng bị xâm nhập cho đến khi nguồn gốc và tính toàn vẹn được xác minh.

## 22. Mô hình quyền tham khảo

| Hoạt động | Dependency read | Cache write dùng chung | Signing | Release publish | Cloud deploy |
|---|---:|---:|---:|---:|---:|
| Pull request từ fork | Không hoặc read-only tối thiểu | Không | Không | Không | Không |
| Pull request nội bộ chưa merge | Read-only | Cache riêng hoặc read-only | Không | Không | Không |
| Protected branch validation | Read-only | Có thể ghi cache protected | Không | Không | Không |
| Release build | Read-only | Theo policy | Qua signing service | Chỉ khi được phê duyệt | Không mặc định |
| Deploy job | Chỉ phần cần thiết | Không cần mặc định | Không cần mặc định | Không cần mặc định | Role giới hạn theo môi trường |

Bảng này là một mẫu thiết kế, không phải ma trận bắt buộc. Một số dự án cần quyền đặc biệt để test hoặc deploy preview; khi đó hãy giới hạn quyền vào tài nguyên riêng và thời gian ngắn.

## 23. Checklist cho pull request và release pipeline

Trước khi chạy pull request chưa tin cậy:

- [ ] Runner dùng user không có quyền quản trị.
- [ ] Workspace và cache tách khỏi release job.
- [ ] Không cấp signing key hoặc release token.
- [ ] Dependency credential, nếu cần, chỉ có quyền đọc.
- [ ] Không mount Docker socket, SSH key hoặc home directory cá nhân.
- [ ] Network egress được giới hạn theo nhu cầu.
- [ ] Wrapper, plugin và build script được xem là code không tin cậy.
- [ ] Job có timeout và quota tài nguyên.
- [ ] Artifact/report được lưu trong vùng riêng và gắn với commit/job.

Trước khi phát hành:

- [ ] Source đến từ protected commit/tag đã review.
- [ ] Release job chạy trên runner sạch, có trust boundary riêng.
- [ ] Credential publish và signing chỉ được cấp trong job cần thiết.
- [ ] Dependency/plugin version và repository policy được kiểm soát.
- [ ] Cache/output từ job untrusted không được dùng làm đầu vào tin cậy.
- [ ] Artifact digest, SBOM và provenance được lưu.
- [ ] Signature/checksum được xác minh.
- [ ] Artifact được publish theo version bất biến.
- [ ] Audit log không chứa secret.

## 24. Những điều cần ghi nhớ

- Maven/Gradle plugin, build script, test, annotation processor và shell task có thể chạy code với quyền của build process.
- Pull request có thể thay đổi build logic và CI workflow, không chỉ source ứng dụng.
- Phân loại source theo trust level: fork, pull request chưa review, protected branch và release.
- Dùng user riêng, runner ephemeral, workspace riêng và quyền filesystem tối thiểu.
- Hạn chế network egress và không mount Docker socket hoặc home directory cá nhân nếu không cần.
- Không cấp release/signing secret cho job chạy code không tin cậy.
- Tách dependency read, cache write, publish và deploy credentials.
- Cô lập Maven local repository, Gradle User Home, daemon và remote build cache giữa các trust boundary.
- Review wrapper, init script, extension, plugin, generator và repository changes.
- Chỉ promote artifact từ protected build đã được xác minh; test pass không chứng minh artifact an toàn.
- Giới hạn CPU, memory, disk, process và thời gian để giảm tác động của build độc hại hoặc lỗi.
- Lưu digest, SBOM, provenance và audit metadata để truy vết artifact.

Giới hạn quyền của tiến trình build là cách giảm thiệt hại khi một plugin, dependency hoặc thay đổi pull request có hành vi không mong muốn. Hãy tách job theo trust level, cấp credential đúng lúc và đúng quyền, cô lập workspace/cache, kiểm soát filesystem/network và chỉ cho pipeline phát hành đã được bảo vệ ký hoặc publish. Khi các ranh giới này được thiết kế rõ, một build validation vẫn có thể compile và test mã mới mà không đồng thời nắm quyền kiểm soát bản phát hành hoặc hạ tầng quan trọng.

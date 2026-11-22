# Quản lý biến môi trường, bí mật và quyền truy cập kho

Build trong CI thường cần đọc dependency từ Maven repository hoặc Gradle repository riêng của tổ chức. Kho có thể yêu cầu username/password, access token hoặc danh tính workload. CI cũng cần các biến cấu hình như JDK, endpoint, profile và đường dẫn. Nếu quản lý các giá trị này không đúng cách, build có thể thất bại vì thiếu quyền, hoặc nghiêm trọng hơn là làm lộ credential trong source code, log, artifact hay cache.

Nguyên tắc cốt lõi là tách **cấu hình**, **bí mật** và **quyền truy cập**. Biến môi trường cung cấp cấu hình cho process build. Secret store của CI giữ giá trị nhạy cảm và cấp chúng khi cần. Repository credential xác định ai được đọc hoặc publish artifact. Mỗi job chỉ nên nhận đúng quyền và thời gian cần thiết.

## 1. Biến môi trường trong build CI là gì?

Biến môi trường (environment variable) là cặp tên/giá trị được process cha truyền cho process con khi khởi chạy. CI runner có thể đặt biến môi trường trước khi gọi Gradle, Maven, shell script hoặc công cụ khác.

Ví dụ trên Linux/macOS:

```bash
export JAVA_TOOL_OPTIONS="-Xmx2g"
export APP_ENV="test"
./gradlew test
```

Ví dụ PowerShell:

```powershell
$env:JAVA_TOOL_OPTIONS = "-Xmx2g"
$env:APP_ENV = "test"
.\gradlew.bat test
```

Gradle, Maven và process con có thể đọc các biến này. Chúng phù hợp cho những giá trị thay đổi theo môi trường chạy, ví dụ:

- Tên môi trường: APP_ENV=test.
- Đường dẫn cache hoặc workspace.
- URL của repository nội bộ.
- Tên user của repository.
- Access token cấp tạm thời.
- Cấu hình JVM như JAVA_TOOL_OPTIONS.

Không phải mọi biến môi trường đều là bí mật. APP_ENV hoặc JAVA_HOME thường là cấu hình thông thường; PRIVATE_REPO_TOKEN là thông tin xác thực cần bảo vệ.

### Biến môi trường chỉ có hiệu lực trong phạm vi process

Khi CI đặt biến cho một step, process được khởi chạy từ step đó có thể nhận giá trị. Phạm vi thực tế tùy nền tảng:

- Một số CI cho phép khai báo ở cấp workflow/pipeline, job hoặc step.
- Một số CI phân biệt biến protected, masked, environment-scoped hoặc deployment-scoped.
- Biến được export trong một shell thường không tự tồn tại ở shell độc lập tiếp theo, trừ khi nền tảng lưu và truyền output theo cơ chế riêng.
- Process con thường kế thừa environment của process cha, nên biến có thể lan sang Gradle daemon, Maven plugin, test worker hoặc script được gọi.

Do đó, nên cấp biến ở phạm vi hẹp nhất có thể: step nào cần credential thì chỉ step đó nhận credential.

## 2. Phân biệt cấu hình thông thường và bí mật

Không nên đưa mọi cấu hình vào secret store. Hãy phân loại trước khi quyết định nơi lưu.

| Loại giá trị | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| Cấu hình công khai | Tên profile, bật/tắt feature test | File cấu hình hoặc CI variable thông thường |
| Đường dẫn/endpoint không nhạy cảm | URL repository public | Build script hoặc CI variable |
| Thông tin nhận dạng | Username service account | Secret store hoặc identity provider theo chính sách |
| Credential | Password, access token, API key | Secret store, credential provider |
| Private key | Khóa ký artifact hoặc deploy | Secret manager/HSM/KMS hoặc cơ chế ký từ xa |
| Token ngắn hạn | OIDC/workload token | Cấp động tại job, không lưu lâu dài |

Một URL repository nội bộ có thể không phải secret, nhưng username/password dùng để truy cập thì có. Không nên nhầm “không công khai” với “bí mật”: endpoint nội bộ vẫn có thể được ghi trong build config nếu chính sách cho phép, còn credential phải được bảo vệ riêng.

### Không commit bí mật vào repository

Không đặt token hoặc password trực tiếp trong:

- build.gradle hoặc build.gradle.kts.
- pom.xml.
- settings.gradle hoặc settings.gradle.kts.
- gradle.properties được commit.
- settings.xml được commit.
- Dockerfile hoặc script build.
- File .env có chứa credential.
- Test fixture, log hoặc tài liệu.

Một khi secret đã được commit, xóa dòng đó ở commit sau không xóa secret khỏi lịch sử Git, fork, clone, cache hoặc log. Cần thu hồi/rotate credential đã lộ và xử lý lịch sử theo quy trình của tổ chức.

## 3. Secret store của CI hoạt động như thế nào?

Secret store là nơi nền tảng CI lưu giá trị nhạy cảm và cho phép workflow tham chiếu khi chạy. Ví dụ có thể là repository secrets, project/group variables hoặc secret manager tích hợp.

Quy trình điển hình:

```text
Quản trị viên lưu credential trong secret store
                 |
                 v
CI xác định job được phép nhận secret
                 |
                 v
Runner khởi chạy step có phạm vi cần thiết
                 |
                 v
Secret được đưa vào environment hoặc file tạm
                 |
                 v
Gradle/Maven dùng credential để đọc repository
                 |
                 v
Step kết thúc, credential hết phạm vi sử dụng
```

Secret store giúp tránh hardcode credential trong source. Nhưng nó không tự bảo vệ secret nếu job được cấp quyền chạy mã không tin cậy. Một build script hoặc test có thể đọc environment rồi gửi giá trị ra ngoài nếu process được cấp secret.

Vì vậy, chỉ cấp secret cho code và runner mà tổ chức tin cậy, ở đúng job, với quyền nhỏ nhất.

### Masking không phải ranh giới bảo mật

Nền tảng CI thường cố che giá trị secret trong log. Ví dụ token có thể hiển thị thành ***. Đây là lớp hỗ trợ giảm rò rỉ vô ý, không phải bảo đảm tuyệt đối.

Masking có thể không nhận diện được:

- Giá trị đã encode hoặc biến đổi.
- Một phần token bị in riêng lẻ.
- Secret được ghép với chuỗi khác.
- Giá trị được ghi vào file artifact.
- Secret được gửi qua network hoặc output của process.
- Log được tạo bởi tool ngoài cơ chế masking của CI.

Không được cố tình in secret với kỳ vọng CI sẽ tự che. Không dùng masking làm lý do để cấp credential cho job không tin cậy.

## 4. Quy tắc bảo vệ secret trong script và log

Không in secret:

```bash
# Không làm như vậy
echo "$PRIVATE_REPO_TOKEN"

# Chỉ kiểm tra biến đã được cấp, không in giá trị
if [ -z "$PRIVATE_REPO_TOKEN" ]; then
  echo "Missing repository token"
  exit 1
fi
```

PowerShell:

```powershell
if ([string]::IsNullOrWhiteSpace($env:PRIVATE_REPO_TOKEN)) {
    throw "Missing repository token"
}
Write-Output "Repository credential is configured"
```

Một số nguyên tắc:

- Không dùng echo, Write-Host, printenv hoặc env trên toàn bộ environment trong job có secret.
- Tránh set -x hoặc shell tracing khi chạy lệnh có credential.
- Hạn chế Gradle --debug và Maven -X trong job có secret; chỉ bật khi cần và kiểm tra log trước khi chia sẻ.
- Không ghép secret vào URL như https://user:token@repo.example.com.
- Không truyền token trong command-line argument nếu có cơ chế environment/file/credential provider phù hợp; process list hoặc log có thể làm lộ argument.
- Không đưa secret vào tên task, test assertion, exception message hoặc build scan tag.
- Không upload file cấu hình chứa credential thành artifact.
- Không lưu secret trong cache có thể được job khác hoặc pull request không tin cậy khôi phục.

### Kiểm tra có/không, không in giá trị

Trong CI, chỉ cần xác nhận biến tồn tại:

```bash
test -n "$PRIVATE_REPO_USER"
test -n "$PRIVATE_REPO_TOKEN"
echo "Repository credentials are available"
```

Nếu muốn kiểm tra token có hợp lệ, gọi endpoint xác thực hoặc truy cập artifact cần thiết và chỉ in trạng thái thành công/thất bại. Không in response body nếu nó có thể chứa thông tin nhạy cảm.

## 5. Quyền truy cập repository cần được chia theo mục đích

Không phải mọi build job đều cần quyền giống nhau.

| Tác vụ | Quyền thường cần |
|---|---|
| Resolve dependency từ repository public | Không cần credential riêng |
| Đọc package private | Read/download packages |
| Đọc plugin nội bộ | Read package/plugin repository |
| Publish snapshot | Write/publish vào snapshot repository |
| Publish release | Write/publish vào release repository, thường có approval |
| Deploy artifact | Quyền triển khai tới môi trường đích |
| Ký artifact | Quyền dùng khóa ký hoặc dịch vụ ký |

Nên tách credential đọc và credential ghi. Một job chỉ chạy unit test thường chỉ cần quyền đọc dependency private. Nó không cần quyền publish release hoặc deploy production.

### Least privilege

Quyền tối thiểu có nghĩa là:

- Token chỉ đọc đúng repository hoặc package namespace cần thiết.
- Không cấp quyền xóa package nếu job chỉ tải dependency.
- Không cấp quyền publish cho mọi pull request.
- Credential có thời hạn và phạm vi nhỏ.
- Tách credential theo môi trường development, staging và production.
- Dùng service identity riêng cho CI thay vì tài khoản cá nhân.
- Thu hồi quyền khi job, project hoặc người sở hữu không còn cần.

Nếu repository hỗ trợ token read-only theo package, hãy dùng loại đó cho compile/test. Nếu chỉ có token rộng hơn, cần giới hạn job và thời gian cấp, đồng thời đánh giá rủi ro của quyền dư thừa.

## 6. Quyền đọc dependency và quyền publish artifact là hai việc khác nhau

Một pipeline có thể có các job:

```text
Pull request validation
  |
  +--> Resolve private dependencies (read-only)
  +--> Compile and test
  +--> No publish/deploy credential

Main branch build
  |
  +--> Resolve dependencies (read-only)
  +--> Compile and test
  +--> Package artifact

Release job
  |
  +--> Verify release candidate
  +--> Publish artifact (write permission)
  +--> Sign/deploy (separate permission)
```

Không nên cấp một token toàn quyền cho cả pipeline chỉ vì bước publish cần nó. Hãy đặt credential write ở job publish riêng, sau khi các điều kiện branch, tag, approval và kiểm thử đã được đáp ứng.

Tách job giúp giảm số process có thể đọc credential write. Nếu job test chạy mã từ pull request, job đó không nên có quyền publish hoặc deploy.

## 7. Truy cập Maven repository riêng trong Gradle

Gradle hỗ trợ credentials trong khai báo Maven repository. Repository URL và credential nên được tách riêng.

Ví dụ Groovy DSL:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')

        credentials {
            username = providers.environmentVariable('PRIVATE_REPO_USER').getOrElse('')
            password = providers.environmentVariable('PRIVATE_REPO_TOKEN').getOrElse('')
        }
    }
}
```

Trong ví dụ này:

- URL repository được khai báo trong build config.
- Username và token được đọc từ environment.
- Token không nằm trong source code.
- CI cấp biến cho job cần đọc repository.

Tên biến chỉ là ví dụ. Hãy dùng tên theo quy ước của dự án.

### Kiểm tra biến bắt buộc

getOrElse với chuỗi rỗng giúp build script cấu hình được khi biến không có, nhưng repository private có thể thất bại sau đó với lỗi xác thực khó hiểu. Với job cần private dependency, nên kiểm tra biến trước hoặc dùng provider bắt buộc để lỗi xuất hiện rõ ràng.

Ví dụ đọc provider:

```groovy
def repoUser = providers.environmentVariable('PRIVATE_REPO_USER')
def repoToken = providers.environmentVariable('PRIVATE_REPO_TOKEN')

repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
        credentials {
            username = repoUser.getOrElse('')
            password = repoToken.getOrElse('')
        }
    }
}
```

Đoạn cấu hình vẫn cần được kết hợp với bước kiểm tra biến tại job CI. Không nên in giá trị để debug.

### Dùng Gradle project properties qua environment

Gradle hỗ trợ map environment variable có tiền tố ORG_GRADLE_PROJECT_ thành project property. Ví dụ:

```bash
export ORG_GRADLE_PROJECT_repoUser="ci-reader"
export ORG_GRADLE_PROJECT_repoPassword="$PRIVATE_REPO_TOKEN"
./gradlew test
```

Build script có thể đọc property qua provider:

```groovy
def repoUser = providers.gradleProperty('repoUser')
def repoPassword = providers.gradleProperty('repoPassword')
```

Cách này hữu ích khi convention plugin hoặc build logic đã chuẩn hóa việc đọc Gradle property. Không được ghi token thật vào gradle.properties trong repository. Nếu dùng ~/.gradle/gradle.properties ở máy cá nhân, phải bảo vệ file và không đưa nó vào CI artifact/cache.

## 8. Maven repository riêng: credentials nằm trong settings.xml

Maven tách repository metadata trong POM khỏi thông tin xác thực trong settings.xml.

POM có thể khai báo repository không chứa password:

```xml
<repositories>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven/releases</url>
    </repository>
</repositories>
```

Trong settings.xml, khai báo server có cùng ID:

```xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.PRIVATE_REPO_USER}</username>
            <password>${env.PRIVATE_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven ghép thông tin server theo id. Nếu repository trong POM có ID company-releases nhưng server trong settings dùng ID khác, Maven có thể không tìm được credential tương ứng.

### Vị trí settings.xml

Maven thường đọc user settings từ:

```text
~/.m2/settings.xml
```

Có thể chỉ định file settings riêng bằng -s:

```bash
mvn -s "$RUNNER_TEMP/settings.xml" verify
```

Đường dẫn này là ví dụ cho môi trường Unix CI. Trên Windows runner, dùng biến đường dẫn tạm tương ứng. File settings có thể được tạo bởi bước setup CI hoặc được mount từ secret store. Không commit file có credential vào repository và không upload file đó thành artifact.

### Phân biệt repository và server ID

- repository id xác định repository trong POM.
- server id trong settings liên kết credential với repository hoặc server tương ứng.
- URL xác định endpoint.
- Username/password xác thực quyền truy cập.

Đặt ID nhất quán giúp cấu hình dễ kiểm tra và tránh lỗi 401 Unauthorized do credential không được ghép đúng.

## 9. Không đưa credential vào POM hoặc URL

Không nên viết:

```xml
<repository>
    <id>company</id>
    <url>https://user:token@repo.example.com/maven/releases</url>
</repository>
```

URL có thể xuất hiện trong log, effective POM, error message, process output hoặc artifact build. Credential trong URL cũng khó quản lý rotation và dễ bị copy sang nơi khác.

Cũng không nên viết password trực tiếp trong POM hoặc settings được commit. Thay vào đó, để settings.xml tham chiếu environment hoặc dùng cơ chế credential provider được nền tảng hỗ trợ.

Maven có thể mã hóa password trong settings bằng cơ chế master password, nhưng mã hóa cục bộ không thay thế secret manager và không biến file settings đã commit thành an toàn. Nếu build cần chạy trên CI, nên inject credential từ secret store tại runtime.

## 10. Cấp biến môi trường trong GitHub Actions

GitHub Actions hỗ trợ repository, organization và environment secrets. Có thể đưa secret vào env ở cấp job hoặc step.

Ví dụ step chỉ cần đọc private dependency:

```yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Compile and test
        run: ./gradlew test
        env:
          PRIVATE_REPO_USER: ${{ secrets.PRIVATE_REPO_USER }}
          PRIVATE_REPO_TOKEN: ${{ secrets.PRIVATE_REPO_READ_TOKEN }}
```

Ví dụ minh họa cách truyền secret cho step. Trong workflow thật, hãy đặt secret ở cấp hẹp nhất có thể. Nếu các step khác không cần token, không khai báo token ở cấp job hoặc workflow.

### Secret scope và protected environment

GitHub Environment có thể áp dụng required reviewers, branch/tag deployment rules và environment-specific secrets. Với job release, có thể yêu cầu approval trước khi cấp credential publish hoặc deploy.

### Không cấp secret cho code từ fork không tin cậy

Pull request từ fork có thể chứa thay đổi build script, test hoặc plugin code. Nếu workflow đưa secret vào process chạy mã đó, mã có thể đọc và gửi secret ra ngoài.

Thông thường, secrets không được cung cấp cho workflow pull_request đến từ fork. Không nên tìm cách vượt qua giới hạn này bằng cách chuyển sang pull_request_target rồi checkout và chạy code của pull request không tin cậy với secret hoặc write token.

Một mô hình an toàn hơn:

- Workflow pull request không tin cậy chỉ chạy các bước không cần secret.
- Job cần đọc package private chỉ chạy trong ngữ cảnh code và runner được tin cậy, với quyền read-only.
- Publish/deploy chỉ chạy trên branch/tag được bảo vệ và sau approval theo chính sách.
- Nếu cần kiểm tra fork có dependency private, thiết kế một quy trình phê duyệt riêng; không chạy mã chưa tin cậy trong job giữ secret.

## 11. Cấp biến trong GitLab CI/CD

GitLab hỗ trợ CI/CD variables ở nhiều phạm vi, ví dụ project, group và instance. Có thể cấu hình Masked, Protected và Environment scope tùy loại variable và phiên bản GitLab.

Ví dụ .gitlab-ci.yml:

```yaml
verify:
  image: gradle:8.10.2-jdk21
  script:
    - ./gradlew test
```

Credential không nên được ghi trực tiếp vào YAML. Hãy cấu hình chúng trong phần CI/CD Variables của GitLab, sau đó job nhận các biến theo scope và policy.

Có thể kiểm tra biến tồn tại mà không in giá trị:

```yaml
verify-private:
  script:
    - test -n "$PRIVATE_REPO_USER"
    - test -n "$PRIVATE_REPO_TOKEN"
    - ./gradlew test
```

Masked giúp hạn chế lộ giá trị trong log. Protected giới hạn biến cho protected branches/tags theo cấu hình dự án. Environment scope giúp chỉ cấp biến cho môi trường phù hợp.

Cần kiểm tra cẩn thận quyền của runner và pipeline từ fork/merge request. Runner có quyền truy cập mạng nội bộ hoặc secret có thể bị lạm dụng nếu chạy code không tin cậy.

## 12. Dùng secret file khi công cụ cần file credential

Một số công cụ cần file cấu hình thay vì environment variable. Ví dụ Maven đọc settings.xml; một công cụ ký có thể cần file key hoặc cấu hình provider.

Trong trường hợp này:

- Tạo file ở thư mục tạm của runner.
- Giới hạn quyền đọc file cho user chạy job.
- Không đặt file trong workspace được upload artifact.
- Không in nội dung file.
- Không cache file cùng dependency cache.
- Xóa file sau khi dùng, nếu nền tảng không tự hủy workspace.
- Không ghi file secret vào Docker image layer.

Ví dụ trên Linux:

```bash
umask 077
mkdir -p "$RUNNER_TEMP"
# CI setup step tạo settings.xml tại đường dẫn tạm từ secret store.
mvn -s "$RUNNER_TEMP/settings.xml" verify
rm -f "$RUNNER_TEMP/settings.xml"
```

Ví dụ chỉ minh họa vòng đời file. Việc tạo file phải dùng cơ chế secret injection phù hợp của CI, tránh ghép chuỗi thiếu an toàn hoặc in secret trong shell trace.

Trên Windows, cần dùng thư mục temp của runner và ACL phù hợp; xóa file bằng lệnh phù hợp sau khi job hoàn thành.

## 13. Secret có thể bị lộ qua process con

Khi CI khởi chạy Gradle hoặc Maven với environment chứa token, process build và các process con có thể kế thừa environment. Điều này bao gồm:

- Gradle daemon.
- Compiler hoặc test worker.
- Annotation processor.
- Maven plugin.
- Shell script và external tool.
- Test code.

Một plugin hoặc test độc hại có thể đọc biến môi trường và gửi ra ngoài. Vì vậy, việc chỉ cấp secret cho một step vẫn có rủi ro nếu step đó chạy code không tin cậy.

Giảm rủi ro bằng cách:

- Chỉ cấp secret cho job thực sự cần.
- Dùng token read-only.
- Không chạy mã PR không tin cậy trong job có secret.
- Tách resolve private dependency khỏi test nếu kiến trúc cho phép và vẫn bảo đảm an toàn.
- Dùng runner cô lập, ephemeral và không tái sử dụng workspace có credential.
- Thu hồi token sau khi hết nhu cầu.
- Hạn chế network egress của runner nếu chính sách hỗ trợ.

Không có cách đặt biến môi trường nào khiến secret hoàn toàn vô hình với process được cấp nó. Quyền chạy code và quyền nhận secret phải được xem xét cùng nhau.

## 14. Token ngắn hạn và OIDC/workload identity

Credential dài hạn có thể bị lộ rồi được sử dụng trong thời gian dài. Khi hệ thống hỗ trợ, nên ưu tiên token ngắn hạn được cấp cho job.

Mô hình workload identity:

```text
CI job bắt đầu
     |
     v
CI cấp identity token có audience/subject giới hạn
     |
     v
Cloud hoặc repository identity provider xác minh token
     |
     v
Cấp credential ngắn hạn với quyền được chỉ định
     |
     v
Gradle/Maven đọc package private
     |
     v
Token hết hạn sau job hoặc sau TTL
```

OIDC cho phép CI chứng minh danh tính workflow với cloud hoặc dịch vụ hỗ trợ federation mà không cần lưu một long-lived cloud secret trong CI. Provider thường kiểm tra claims như repository, branch, environment, workflow hoặc audience.

Cần cấu hình trust policy chặt chẽ:

- Chỉ chấp nhận issuer đúng.
- Giới hạn audience.
- Giới hạn repository/project.
- Giới hạn branch/tag/environment.
- Giới hạn service account và role được assume.
- Cấp quyền read package nếu chỉ cần tải dependency.
- Dùng TTL ngắn nhất đáp ứng công việc.

Không phải Maven repository nào cũng hỗ trợ OIDC trực tiếp. Có thể cần identity broker, cloud artifact registry hoặc credential helper chuyển đổi workload identity thành token ngắn hạn.

## 15. Credential cho repository private trên máy phát triển

Máy cá nhân cũng cần truy cập private repository, nhưng không nên chia sẻ credential cá nhân trong source code hoặc file chung của nhóm.

Các lựa chọn:

- Login qua SSO hoặc credential helper của tổ chức.
- Dùng token cá nhân read-only có thời hạn nếu chính sách cho phép.
- Lưu credential trong user-level Gradle properties hoặc Maven settings.
- Dùng environment variable trong terminal cho phiên làm việc cần thiết.
- Dùng công cụ quản lý secret của hệ điều hành hoặc tổ chức.

Ví dụ Gradle user-level properties:

```properties
repoUser=developer-account
repoPassword=token-from-secure-store
```

File thường nằm trong Gradle user home, ví dụ ~/.gradle/gradle.properties, không nằm trong repository. File vẫn cần được bảo vệ bằng quyền truy cập của hệ điều hành và không được đưa vào cache/artifact chia sẻ.

Ví dụ Maven user settings:

```text
~/.m2/settings.xml
```

Không gửi file này qua chat, pull request hoặc commit. Nếu cần hỗ trợ lỗi xác thực, hãy chia sẻ ID repository, thông báo lỗi đã redaction và tên biến (không phải giá trị).

## 16. Quản lý quyền đọc và ghi theo repository

Nên thiết kế quyền theo loại repository:

| Repository | Job đọc | Job ghi |
|---|---|---|
| Public dependency proxy | Có thể không cần secret | Không cần |
| Internal release dependencies | Read-only token | Không cần trong verify job |
| Internal snapshots | Read-only token | Snapshot publisher riêng |
| Release repository | Read-only trong consumer build | Release publisher được bảo vệ |
| Container registry | Pull permission | Push permission chỉ cho image build/publish |
| Signing service | Không cần cho compile/test | Chỉ release signing job |
| Deployment environment | Không cần cho build validation | Deploy job riêng |

Một token có cả quyền read/write/delete ở mọi repository làm tăng hậu quả nếu bị lộ. Nên chia token theo chức năng và repository namespace.

### Không dùng credential cá nhân làm credential CI lâu dài

Tài khoản cá nhân có thể bị khóa, đổi vai trò hoặc nghỉ việc. Service account hoặc workload identity có ownership rõ ràng và quyền được giới hạn sẽ phù hợp hơn cho pipeline.

Nếu buộc phải dùng token cá nhân trong một tình huống tạm thời, cần thời hạn ngắn, owner rõ ràng, quyền nhỏ và kế hoạch thay thế.

## 17. Rotation và thu hồi credential

Secret cần có vòng đời:

1. Tạo credential với quyền tối thiểu.
2. Lưu vào secret store.
3. Cấp cho job cần thiết.
4. Theo dõi sử dụng và thời hạn.
5. Rotate trước khi hết hạn hoặc theo lịch.
6. Cập nhật secret store và xác nhận pipeline hoạt động.
7. Thu hồi credential cũ.
8. Điều tra nếu credential có dấu hiệu bị lộ.

Nếu nghi ngờ token đã bị lộ:

- Thu hồi token hoặc disable credential ngay theo quy trình incident.
- Tạo token mới với scope tối thiểu.
- Cập nhật secret store.
- Kiểm tra audit log của repository và package registry.
- Xem job/artifact/log/cache nào có thể đã chứa token.
- Xóa hoặc hạn chế truy cập bản sao bị lộ theo quy trình.
- Xác minh token cũ không còn hoạt động.

Chỉ xóa secret khỏi CI variable không thu hồi token ở phía repository. Cần revoke tại hệ thống phát hành token.

## 18. Cẩn trọng với cache và artifact của CI

Cache thường được chia sẻ giữa các lần chạy để tăng tốc. Nhưng cache có thể chứa nhiều dữ liệu hơn dự kiến nếu lưu toàn bộ user home hoặc workspace.

Tránh cache:

- ~/.m2/settings.xml có credential.
- ~/.gradle/gradle.properties chứa token.
- File .env nhạy cảm.
- File private key.
- File tạm do secret injection tạo.
- Log debug có thể chứa request hoặc thông tin xác thực.

Ưu tiên cache các thư mục dependency/artifact cần thiết và loại trừ file cấu hình credential. Đọc kỹ glob/path của bước upload artifact; pattern rộng như **/* có thể vô tình đưa file secret vào artifact.

Không nên upload toàn bộ Gradle user home hoặc Maven local repository mà không xem nội dung và quyền truy cập. Cache cần được xem như dữ liệu có thể được job khác khôi phục, vì vậy chỉ đưa vào những gì có thể chia sẻ an toàn.

## 19. Repository credentials trong Docker build

Nếu build Java bên trong Docker, không truyền secret bằng ARG hoặc ENV để lưu vào image layer.

Ví dụ không nên:

```dockerfile
ARG REPO_TOKEN
ENV REPO_TOKEN=$REPO_TOKEN
RUN ./gradlew build
```

Build argument và environment trong image có thể xuất hiện trong metadata/layer hoặc bị giữ lại ngoài ý muốn.

Nếu dùng Docker BuildKit, secret mount cho phép đưa secret tạm vào một bước build mà không ghi nó vào image layer theo cơ chế mount secret:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM gradle:8.10.2-jdk21 AS build
WORKDIR /workspace
COPY . .
RUN --mount=type=secret,id=repo_token \
    PRIVATE_REPO_TOKEN="$(cat /run/secrets/repo_token)" \
    ./gradlew build
```

Đây là ví dụ khái niệm. Cần truyền secret bằng tùy chọn BuildKit phù hợp từ CI và bảo đảm lệnh build không in giá trị. Secret mount chỉ tồn tại trong bước được chỉ định; không ghi token vào file output hoặc cache. Với Docker build không có BuildKit, hãy dùng cơ chế secret phù hợp của nền tảng thay vì nhúng credential vào image.

## 20. Phân biệt secret, variable và artifact trong CI

| Khái niệm | Ví dụ | Có nên lưu trong Git? |
|---|---|---|
| CI variable không nhạy cảm | APP_ENV=test | Có thể, nếu là cấu hình ổn định |
| Secret variable | PRIVATE_REPO_TOKEN | Không |
| Secret file | settings.xml, signing config | Không |
| Build artifact | JAR, test report | Theo chính sách artifact |
| Cache | Dependency cache, task output cache | Theo chính sách cache |
| Build metadata | Commit SHA, JDK version, build number | Thường có thể lưu |
| Credential audit record | Token ID, actor, thời gian cấp | Lưu ở hệ thống audit, không lưu token value |

Một artifact có thể chứa thông tin nội bộ nhưng không nhất thiết là secret. Ngược lại, file log có vẻ vô hại nhưng có thể chứa token. Cần xác định dữ liệu bên trong trước khi chia sẻ.

## 21. Lỗi xác thực repository thường gặp

### HTTP 401 Unauthorized

Có thể do:

- Thiếu username/token.
- Token hết hạn hoặc bị thu hồi.
- Maven server ID không khớp repository ID.
- Secret variable không được cấp cho branch/job hiện tại.
- Token sai loại hoặc sai audience.
- Credential không được Gradle/Maven đọc đúng tên biến.

Hãy kiểm tra biến tồn tại mà không in giá trị, xác nhận scope và quyền của token, rồi kiểm tra ID repository/server.

### HTTP 403 Forbidden

Credential có thể hợp lệ nhưng không có quyền đọc package/repository. Kiểm tra scope, project/package access và policy của repository.

### HTTP 404 Not Found

Có thể tọa độ hoặc URL sai, repository không chứa artifact, hoặc repository cố ý trả 404 khi caller không có quyền. Kiểm tra group/artifact/version, repository endpoint và quyền đọc.

### Build chạy local nhưng fail trong CI

Nguyên nhân thường gặp:

- Local settings.xml hoặc Gradle properties có credential nhưng CI không có.
- CI secret chỉ áp dụng cho protected branch.
- Job chạy từ fork không nhận secret.
- Biến tên khác chữ hoa/thường.
- CI dùng Maven/Gradle user home khác.
- Runner không truy cập được network/repository.
- Certificate hoặc proxy khác môi trường local.

Không nên copy credential cá nhân vào source để làm CI pass. Hãy cấu hình secret store hoặc service identity đúng cách.

## 22. Debug xác thực mà không làm lộ secret

Một quy trình an toàn:

1. Kiểm tra tên biến đã được cấu hình và có mặt trong step.
2. Xác nhận job/branch/environment có quyền nhận secret.
3. Xác nhận URL repository và ID tương ứng.
4. Xác nhận token còn hiệu lực và có scope đọc package.
5. Kiểm tra runner truy cập endpoint qua HTTPS.
6. Dùng log mức bình thường để xem status code và module bị từ chối.
7. Chỉ bật debug trong môi trường được kiểm soát, sau khi hiểu log có thể chứa gì.
8. Redact dữ liệu trước khi chia sẻ log.

Không yêu cầu người khác gửi token để chẩn đoán. Thông tin đủ dùng thường là tên biến, loại token, repository ID, status code và thông báo lỗi đã loại bỏ URL query hoặc dữ liệu nhạy cảm.

## 23. Ví dụ GitHub Actions: build đọc package private, publish riêng

Một pipeline nên tách job verify và publish. Job verify chỉ cần quyền đọc dependency; job publish nhận credential ghi sau khi branch/tag và approval thỏa mãn.

Ví dụ cấu trúc:

```yaml
name: Java build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify-pr:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Test without repository secret
        run: ./gradlew test

  verify-main:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Test with read-only package access
        run: ./gradlew test
        env:
          PRIVATE_REPO_USER: ${{ secrets.PRIVATE_REPO_USER }}
          PRIVATE_REPO_TOKEN: ${{ secrets.PRIVATE_REPO_READ_TOKEN }}
```

Ví dụ này cố ý chạy pull request trong job không có secret; job dùng read-only token chỉ chạy khi push lên main. Trong dự án thực tế, có thể cần một workflow riêng cho release tag, đặt trong protected environment và có approval trước khi cấp quyền publish. Điều chỉnh trigger, approval, permissions và điều kiện branch theo chính sách thực tế. Không checkout và thực thi mã fork không tin cậy trong job có secret.

## 24. Ví dụ Maven settings được tạo trong CI

CI có thể cấp hai biến PRIVATE_REPO_USER và PRIVATE_REPO_TOKEN. Một file settings tạm tham chiếu environment:

```xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.PRIVATE_REPO_USER}</username>
            <password>${env.PRIVATE_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Sau đó gọi:

```bash
mvn -s "$RUNNER_TEMP/settings.xml" -B -ntp verify
```

Không upload settings.xml. Nếu job dùng nhiều repository, mỗi server ID cần khớp với repository ID tương ứng. Nếu settings file được tạo từ template, hãy kiểm soát escaping và không in file ra log.

## 25. Không đưa credential vào build scan hoặc test report

Build Scan, test report và build log có thể được chia sẻ với nhiều người hơn secret store. Trước khi publish hoặc upload, kiểm tra:

- Build scan custom value/tag có chứa token hoặc username nhạy cảm không.
- Test failure có in request header hoặc config không.
- Maven debug log có chứa URL query hoặc server configuration không.
- Gradle debug log có in request hoặc environment không.
- Report có lưu request/response fixture thật không.
- Artifact có chứa settings.xml, .env hoặc file key không.

Không gắn secret vào build scan tag hoặc custom value. Dùng ID không nhạy cảm như commit SHA, job number hoặc tên môi trường.

## 26. Quyền truy cập repository và network runner

Credential đúng vẫn chưa đủ nếu runner không có đường mạng tới repository.

Cần kiểm tra:

- DNS resolution.
- HTTPS/TLS certificate chain.
- Proxy configuration.
- Firewall và egress rules.
- Repository allowlist.
- Runner network segment.
- Repository availability.
- Authentication gateway hoặc SSO policy.

Không tắt TLS certificate validation để giải quyết lỗi kết nối. Nếu môi trường dùng certificate nội bộ, cài trust chain phù hợp vào runner/JDK theo hướng dẫn quản trị.

Một runner có quyền truy cập mạng nội bộ rộng cũng cần được bảo vệ. Nếu chạy mã không tin cậy, attacker có thể thử truy cập service nội bộ ngay cả khi không có secret. Cô lập runner và giới hạn network egress giúp giảm phạm vi tác động.

## 27. Quy trình vận hành credential an toàn

Một quy trình cho repository private:

1. Tạo service identity hoặc workload identity dành riêng cho CI.
2. Cấp quyền read-only đúng repository/package namespace.
3. Lưu credential trong secret store hoặc cấu hình federation.
4. Chỉ truyền credential vào job cần resolve private dependency.
5. Cấu hình Gradle/Maven đọc credential từ environment hoặc settings file tạm.
6. Không in, cache, upload hoặc commit file chứa credential.
7. Tách job publish/deploy với quyền ghi riêng.
8. Giới hạn branch/tag/environment có thể nhận credential.
9. Theo dõi expiration và audit log.
10. Rotate/thu hồi khi hết nhu cầu hoặc có dấu hiệu lộ.
11. Xác minh build vẫn hoạt động sau rotation.
12. Xem lại quyền định kỳ và loại bỏ token không còn dùng.

## 28. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Đặt token trong environment là tự động an toàn | Process con có thể đọc environment; chỉ cấp cho code và job tin cậy. |
| CI masking bảo đảm secret không thể lộ | Masking chỉ giảm rò rỉ log vô ý; không ngăn code gửi secret ra ngoài. |
| Read token có thể dùng để publish | Quyền đọc và ghi nên được tách riêng. |
| Private repository URL là đủ để xác thực | URL xác định endpoint; credential và permission mới quyết định quyền truy cập. |
| Maven server ID có thể tùy ý khác repository ID | Server ID cần khớp repository ID để Maven liên kết credential. |
| Gradle/Maven nên chứa password trong build file | Build file chỉ tham chiếu biến hoặc provider; secret được cấp từ bên ngoài. |
| Secret không xuất hiện trong log nghĩa là không thể bị lấy | Code chạy trong job có thể đọc secret và gửi qua network hoặc artifact. |
| Có thể cấp secret cho fork PR nếu CI che log | Mã PR không tin cậy vẫn có thể đọc và exfiltrate secret. |
| Xóa token khỏi CI variable là thu hồi token | Cần revoke tại repository/identity provider. |
| Cache toàn bộ user home luôn an toàn | User home có thể chứa settings, properties hoặc credential file. |
| Dùng token cá nhân lâu dài cho CI là tiện nhất | Service identity hoặc workload identity có ownership và scope rõ ràng hơn. |

## 29. Checklist trước khi bật private repository trong CI

- Repository URL dùng HTTPS và đúng endpoint.
- Repository ID và Maven server ID khớp.
- Gradle/Maven đọc credential từ nguồn bên ngoài source code.
- Secret được lưu trong secret store hoặc cấp qua identity provider.
- Token chỉ có quyền đọc package cần thiết.
- Credential chỉ được cấp cho job cần nó.
- Pull request từ fork không nhận secret.
- Job chạy code không tin cậy không có quyền publish/deploy.
- Không có echo, printenv, shell tracing hoặc log debug làm lộ secret.
- Credential không nằm trong URL, POM, build script hoặc Docker layer.
- Settings/credential file tạm không bị upload hoặc cache.
- Runner có network access và trust certificate đúng.
- Có quy trình rotate/revoke và owner chịu trách nhiệm.
- CI artifact/cache không chứa file nhạy cảm.
- Log chia sẻ đã được kiểm tra và redaction.

## 30. Checklist khi lỗi truy cập repository

Khi build trả về 401, 403 hoặc không tìm thấy artifact:

1. Job có được phép nhận secret không?
2. Tên biến environment có đúng không?
3. Biến có tồn tại trong đúng step không, mà không cần in giá trị?
4. Token còn hiệu lực và đúng audience không?
5. Token có quyền đọc đúng package/repository không?
6. Gradle repository credentials có lấy đúng provider không?
7. Maven server ID có khớp repository ID không?
8. URL, group, artifact và version có đúng không?
9. Runner có truy cập được host và TLS certificate không?
10. Có proxy/firewall hoặc repository policy chặn không?
11. Có dùng local cache khiến lỗi mới bị che hoặc kết quả cũ được tái sử dụng không?
12. Log/artifact có vô tình chứa credential không?

## 31. Nguyên tắc áp dụng trong thực tế

Biến môi trường giúp truyền cấu hình vào process build; secret store bảo vệ giá trị nhạy cảm khi cấp cho CI; quyền repository xác định job được phép đọc hoặc publish artifact nào. Ba phần này cần được thiết kế cùng nhau.

Với Gradle, khai báo repository và đọc credential qua provider/environment. Với Maven, để POM mô tả repository và đặt credential trong user settings hoặc settings file tạm, ghép bằng server ID. Trong CI, dùng read-only credential cho verify job, quyền write riêng cho publish, giới hạn secret theo branch/environment và không cấp secret cho code không tin cậy.

Masking, cache và file tạm chỉ là lớp hỗ trợ. Bảo vệ thực sự đến từ least privilege, runner/job isolation, code trust, credential ngắn hạn, rotation và việc không để secret đi vào source, log, cache hoặc artifact. Khi những nguyên tắc này được áp dụng nhất quán, build có thể truy cập private repository mà vẫn giữ được quyền kiểm soát và khả năng truy vết.

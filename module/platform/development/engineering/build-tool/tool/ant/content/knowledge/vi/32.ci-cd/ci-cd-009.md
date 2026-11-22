# Tách quyền và thông tin xác thực giữa build kiểm tra và phát hành trong Apache Ant CI/CD

## 1. Vì sao cần tách hai loại build?

Trong một dự án Java sử dụng **Apache Ant**, cùng một file **build.xml** có thể khai báo các target biên dịch, kiểm thử, đóng gói và xuất bản. Tuy nhiên, trong môi trường CI/CD, **build kiểm tra** và **phát hành** có ranh giới tin cậy rất khác nhau.

**Build kiểm tra (verification build)** nhận thay đổi từ commit hoặc pull request để trả lời: mã có biên dịch được không, test có đạt không, artifact có đóng gói được không? Một pull request có thể được tạo bởi người chưa có quyền phát hành, và nội dung build.xml, script hay mã test trong pull request có thể bị sửa. Vì thế, những lệnh Ant do pull request kích hoạt cần được xem là **mã chưa tin cậy**.

**Build/phần việc phát hành (release/publish)** đưa artifact đã được duyệt vào kho phân phối: GitHub Releases, Maven repository, Nexus, Artifactory, object storage hoặc một kênh triển khai. Để làm việc đó, job phải có **danh tính** và **quyền ghi** tương ứng. Nếu giao quyền ghi cho job kiểm tra pull request, một thay đổi độc hại trong build.xml có thể chạy task **exec** hoặc Java code để gửi credential ra ngoài.

Vì vậy, hai mục tiêu phải được thiết kế riêng:

- **Verify:** checkout, biên dịch, chạy test, tạo artifact, xuất báo cáo. Không nhận credential xuất bản.
- **Release:** kiểm tra nguồn phát hành và gate phê duyệt, nhận đúng artifact đã kiểm chứng, dùng credential giới hạn để publish, lưu kết quả công bố.

Điểm cốt lõi: **file build.xml quyết định Ant sẽ làm gì; nền tảng CI và registry quyết định job nào được phép thực hiện hành động nhạy cảm**. Không thể dùng một property trong Ant thay thế IAM, quyền của token hoặc chính sách phê duyệt.

## 2. Ranh giới tin cậy, danh tính và quyền

### 2.1. Ai thực sự sở hữu quyền?

| Thành phần | Trách nhiệm | Quyền thường cần |
|---|---|---|
| **build.xml và mã nguồn** | Mô tả compile, test, package | Không tự có quyền ghi release |
| **Verify job** | Thực thi mã đang được đề xuất | Đọc repository, ghi output tạm trong runner |
| **Artifact storage của CI** | Lưu JAR, checksum, test report theo workflow run | Nhận và cung cấp artifact trong phạm vi phù hợp |
| **Release gate** | Kiểm tra ref, trạng thái job, quy tắc review và approval | Quyền quyết định việc cấp quyền publish |
| **Release job** | Tải artifact đã kiểm tra và gọi API/CLI publish | Chỉ ghi vào đích phát hành được chỉ định |
| **Registry/kho phát hành** | Xác thực job và lưu artifact | Chính sách riêng để chấp nhận hoặc từ chối upload |

Tách job là cách làm rõ trách nhiệm, nhưng còn phải bảo đảm **credential của release không xuất hiện ở verify job**, kể cả qua biến môi trường toàn cục, thư mục làm việc chung, secret file hoặc runner dùng lại không được làm sạch.

### 2.2. Ma trận quyền tối thiểu

| Hành động | Verify job | Release job |
|---|---|---|
| Đọc mã nguồn | Có | Có thể không cần nếu nhận artifact |
| Chạy Ant compile/test | Có | Thường không cần chạy lại |
| Tạo JAR trung gian | Có | Dùng JAR đã kiểm tra |
| Đọc secret của registry/production | **Không** | Chỉ khi thực sự cần |
| Tạo hoặc cập nhật public release | **Không** | Có, trong phạm vi hạn chế |
| Thay đổi branch/tag được bảo vệ | Không | Chỉ nếu quy trình cho phép |
| Triển khai production | Không | Chỉ sau gate phê duyệt |
| Ghi kết quả và audit phát hành | Ghi log kiểm tra | Ghi release ID, digest, thời điểm công bố |

Một token cấp cho toàn bộ tổ chức hoặc tài khoản cá nhân thường rộng hơn nhu cầu của một lần upload. Cấp quyền nên theo **hành động**, **tài nguyên đích** và **thời hạn**. Ví dụ, job upload một JAR vào repository release không cần quyền xóa mọi version hay quản trị toàn bộ registry.

### 2.3. Luồng tin cậy

~~~mermaid
flowchart TD
    PR["PR hoặc commit được đề xuất"] --> V["Verify job chạy Ant với quyền đọc"]
    V --> T{"Compile, test, package đạt?"}
    T -->|Không| Stop["Dừng, lưu lỗi"]
    T -->|Có| A["Artifact + SHA-256 + CI run ID"]
    A --> Gate{"Tag/ref được bảo vệ và approval đạt?"}
    Gate -->|Không| Hold["Không cấp quyền publish"]
    Gate -->|Có| R["Release job dùng danh tính riêng"]
    R --> Repo["Kho phát hành xác nhận artifact"]
    Repo --> Audit["Lưu digest, revision, release ID, publishedAt"]
~~~

Một PR vượt qua kiểm tra không tự động được quyền phát hành. **Gate** là chính sách ở hệ thống CI, repository và registry; người có thể sửa build.xml không được tự đặt điều kiện đó thành đạt.

## 3. Quản lý credential đúng theo vòng đời

### 3.1. Chọn danh tính cho từng đích

| Đích phát hành | Loại credential phù hợp | Giới hạn cần áp dụng |
|---|---|---|
| GitHub Releases | Token workflow của release job | Quyền nội dung chỉ tại repository liên quan |
| Maven/Nexus/Artifactory | Deploy token, service account hoặc workload identity | Chỉ repository/kênh cần publish |
| Object storage | Workload identity hoặc token ngắn hạn | Chỉ bucket và prefix chứa artifact |
| Container registry | Danh tính có quyền push | Chỉ image repository và namespace đích |
| Hệ thống triển khai | Service identity tách riêng | Chỉ ứng dụng và environment cụ thể |

Nếu CI và nhà cung cấp hỗ trợ **OpenID Connect (OIDC)**, release job có thể xác minh danh tính workload với phía registry/cloud rồi đổi lấy credential **ngắn hạn**. Phía nhận phải kiểm tra claim như repository, workflow, ref và environment; chỉ cấp role phù hợp. Trong GitHub Actions, quyền **id-token: write** cho phép job yêu cầu OIDC token, nhưng **không tự cấp** quyền ghi ở cloud; IAM trust policy vẫn phải được cấu hình.

Nếu chỉ có token tĩnh, dùng **scoped token** cất trong secret manager của CI, hạn chế thời gian sống, có lịch xoay vòng và cơ chế thu hồi. Tránh token cá nhân toàn quyền. Cố gắng giới hạn secret ở **một job hoặc step publish** để các lệnh Ant khác không thể đọc nó.

### 3.2. Những chỗ không nên để credential

- **build.xml**, release.properties, source code, Docker image hoặc manifest JAR được commit.
- Tham số chạy Ant như **-Dpassword=...** nếu tham số có thể xuất hiện trong history, log hoặc process list.
- URL chứa token ở query string, command line hoặc test report.
- Cache, artifact kiểm tra, workspace tái sử dụng, log debug hoặc file tạm được upload ra ngoài.
- Biến môi trường ở cấp toàn workflow nếu một job chạy mã PR không tin cậy có thể đọc.

**Log masking** chỉ giảm khả năng hiển thị một chuỗi bí mật; nó không ngăn mã đang chạy gửi token đến máy chủ khác, biến đổi/giải mã token hoặc ghi vào file. Biện pháp mạnh nhất là **không cấp secret cho job chưa cần sử dụng**.

### 3.3. Vì sao property Ant không phải tường phân quyền?

Ví dụ:

~~~xml
<target name="publish" if="release.enabled">
    <!-- Upload artifact -->
</target>
~~~

Điều kiện **if="release.enabled"** chỉ điều khiển xem Ant có chạy target hay không. Một người có thể truyền tham số **-Drelease.enabled=true** hoặc chỉnh sửa build.xml nếu họ kiểm soát đầu vào của pipeline. Nó không quyết định danh tính nào được registry chấp nhận. **CI/IAM/registry phải từ chối quyền ghi** nếu job chưa vượt qua điều kiện phát hành.

## 4. Tổ chức Ant theo mục tiêu kiểm chứng

Ví dụ sau giữ Ant tập trung vào **biên dịch, kiểm thử và đóng gói**. CI chịu trách nhiệm kiểm soát quyền và xuất bản file đã được kiểm tra.

### 4.1. Cấu trúc dự án mẫu

~~~text
ant-ci-demo/
├── build.xml
├── src/
│   ├── main/java/example/App.java
│   └── test/java/example/SmokeTest.java
└── .github/workflows/verify-and-release.yml
~~~

File **src/main/java/example/App.java**:

~~~java
package example;

public final class App {
    private App() {}

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

File **src/test/java/example/SmokeTest.java**:

~~~java
package example;

public final class SmokeTest {
    private SmokeTest() {}

    public static void main(String[] args) {
        if (App.add(2, 3) != 5) {
            throw new AssertionError("Unexpected result");
        }
        System.out.println("Smoke test passed");
    }
}
~~~

File **build.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ci-demo" default="package" basedir=".">
    <property name="main.src" location="src/main/java"/>
    <property name="test.src" location="src/test/java"/>
    <property name="main.classes" location="build/classes"/>
    <property name="test.classes" location="build/test-classes"/>
    <property name="dist.dir" location="build/dist"/>

    <!-- Mốc kỹ thuật cho entry JAR; không phải ngày release. -->
    <property name="archive.timestamp" value="2024-01-01T00:00:00Z"/>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile">
        <mkdir dir="${main.classes}"/>
        <javac srcdir="${main.src}"
               destdir="${main.classes}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"/>
    </target>

    <target name="test" depends="compile">
        <mkdir dir="${test.classes}"/>
        <javac srcdir="${test.src}"
               destdir="${test.classes}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17">
            <classpath>
                <pathelement location="${main.classes}"/>
            </classpath>
        </javac>

        <java classname="example.SmokeTest"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${main.classes}"/>
                <pathelement location="${test.classes}"/>
            </classpath>
        </java>
    </target>

    <target name="package" depends="test">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/app.jar"
             basedir="${main.classes}"
             includes="**/*.class"
             modificationtime="${archive.timestamp}"/>
        <checksum file="${dist.dir}/app.jar"
                  algorithm="SHA-256"
                  fileext=".sha256"/>
    </target>
</project>
~~~

Chạy bằng:

~~~bash
ant -noinput clean package
~~~

Target **package** phụ thuộc **test**, vì thế một lỗi compile hoặc test sẽ làm Ant dừng trước khi đóng gói. Task **java** sử dụng **failonerror="true"** để trả trạng thái lỗi khi SmokeTest kết thúc không thành công. Nếu build đạt, kết quả gồm **build/dist/app.jar** và **build/dist/app.jar.sha256**.

Ví dụ yêu cầu JDK hỗ trợ **release 17** và Apache Ant **1.10.2 trở lên** (để dùng thuộc tính **jar modificationtime**). Mốc archive cố định chỉ phục vụ metadata của JAR; nó không có ý nghĩa là sản phẩm đã phát hành vào ngày đó. Với dự án lớn, để có build tái lập còn phải kiểm soát version Ant, JDK, dependency và các nguồn metadata khác.

Trong build.xml không có credential, target upload hay URL registry. Điều này có chủ đích: target biên dịch/test có thể được chạy trên PR với quyền thấp; **khâu phát hành nằm ở job có chính sách riêng**.

## 5. Ví dụ phân quyền bằng GitHub Actions

Dưới đây là một workflow minh họa **verify** và **release** là hai job. Cách thiết kế tương tự có thể triển khai trên GitLab CI, Jenkins hoặc nền tảng khác bằng token/job scope và protected environment tương ứng.

File **.github/workflows/verify-and-release.yml**:

~~~yaml
name: Verify and release Ant artifact

on:
  pull_request:
  push:
    tags:
      - 'v*'

# Mặc định toàn workflow chỉ có quyền đọc repository.
permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant
          ant -version

      - name: Compile, test and package
        run: ant -noinput clean package

      - name: Preserve verified JAR for tag releases
        if: startsWith(github.ref, 'refs/tags/v')
        uses: actions/upload-artifact@v4
        with:
          name: ant-verified-jar
          path: build/dist/
          if-no-files-found: error

  release:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    needs: verify
    runs-on: ubuntu-24.04
    environment: production

    # Chỉ job release có quyền tạo GitHub Release.
    permissions:
      contents: write

    steps:
      - name: Download verified artifact
        uses: actions/download-artifact@v4
        with:
          name: ant-verified-jar
          path: dist

      - name: Publish GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
        run: |
          gh release create "$GITHUB_REF_NAME" \
            dist/app.jar dist/app.jar.sha256 \
            --verify-tag --generate-notes
~~~

### 5.1. Job verify nhận quyền gì?

Workflow mặc định khai báo **contents: read**. Job verify checkout source, cài JDK/Ant, chạy compile/test/package. Với một PR, Ant thực thi code mà người mở PR có thể sửa, nhưng **không được nhận credential xuất bản**. Nếu test thất bại, job kết thúc thất bại và job release (có **needs: verify**) không tiếp tục.

Bước **upload-artifact** ở ví dụ chỉ chạy khi ref là tag phát hành. Nó lưu kết quả vào artifact storage của **chính workflow run**, chứ chưa công bố ra GitHub Release. Với pull request, workflow chỉ kiểm tra, không gọi upload của kênh public release.

### 5.2. Job release nhận quyền gì?

Điều kiện **if** yêu cầu sự kiện **push** với tag dạng **v***. Job release cần job verify thành công, đặt **environment: production** và khai báo riêng **contents: write**. Token của job được cung cấp cho đúng bước **gh release create** qua **GH_TOKEN**. **GH_REPO** giúp CLI xác định repository khi job không checkout mã nguồn.

Job release **chỉ tải artifact và publish**; nó không chạy lại build.xml hoặc code test khi token ghi đã có mặt. Quyền ghi không lan sang job verify.

Ví dụ giả định **gh** có sẵn trên GitHub-hosted Ubuntu runner. Với runner riêng, cần chuẩn bị CLI tương ứng. Trong môi trường sản xuất, nên pin action theo commit SHA đã kiểm chứng và chốt phiên bản toolchain; lệnh cài Ant bằng package manager từ kho hiện hành có thể thay đổi phiên bản theo thời gian.

### 5.3. Các điều kiện bảo vệ phải cấu hình ngoài YAML

**Không thể coi biểu thức if là toàn bộ ranh giới bảo mật.** Nhóm cần áp dụng thêm:

1. **Branch protection/ruleset** và review cho mã nguồn, build.xml và file workflow. Người không được quyền phát hành không được tùy ý thay đổi logic workflow rồi merge.
2. **Tag protection/ruleset** giới hạn ai có thể tạo, cập nhật hoặc xóa tag theo mẫu phát hành; tag không được trỏ tùy tiện vào commit chưa được xét duyệt.
3. **Protected environment production** với required reviewers hoặc điều kiện bảo vệ phù hợp. Chỉ ghi tên environment trong YAML không tự tạo một bước phê duyệt nếu chưa cấu hình protection rules.
4. **Quyền mặc định thấp** của workflow; chỉ release job cần **contents: write**. Với OIDC, chỉ job thật sự đổi danh tính mới nên có **id-token: write**.
5. **Repository và registry policy** phải kiểm chứng ref/danh tính, độc lập với một điều kiện do mã nguồn kiểm soát.

Một workflow có nhãn release vẫn có thể thiếu kiểm soát nếu bất kỳ ai được tạo tag hoặc sửa workflow. Ranh giới thực sự là tổng hợp của review, protected refs, approval, token scope và xác thực tại đích publish.

## 6. Dùng đúng artifact đã qua kiểm tra

Giả sử verify job tạo **app.jar** với SHA-256 **H1**. Sau approval, release job tải **chính file app.jar** do verify job lưu và xuất bản với digest **H1**. Quy trình lý tưởng:

~~~text
protected tag / source revision
              |
              v
     Ant compile + test
              |
              v
      app.jar / SHA-256 H1
              |
              v
    Workflow artifact storage
              |
       approval / gate
              |
              v
     Release job (scoped identity)
              |
              v
  Registry confirms artifact H1
~~~

Nếu release job **build lại** từ mã nguồn thay vì dùng file đã test, có thêm một lần biên dịch mới với khả năng thay đổi công cụ, dependency và timestamp. Dù một dự án có thể đạt byte-for-byte reproducibility, việc tái build vẫn tạo thêm bước cần kiểm chứng. Chuyển giao trực tiếp artifact đã kiểm thử giúp giữ quan hệ rõ ràng giữa **bằng chứng kiểm tra** và **file phát hành**.

Checksum giúp phát hiện byte thay đổi khi truyền/lưu. Tuy nhiên, nếu cả JAR và checksum cùng bị ghi đè bởi một nguồn không tin cậy, hai file vẫn có thể khớp nhau. Nên ràng buộc artifact với **CI run ID, commit SHA, ref, quyền ghi của artifact storage** và, theo mức độ bảo đảm, dùng thêm **provenance/attestation hoặc chữ ký**.

Registry cũng nên ghi release record chứa **artifact digest**, mã nguồn và trạng thái upload. Nếu một version đã tồn tại với digest khác, quy trình phải dừng để điều tra thay vì ghi đè âm thầm.

## 7. Phát hành lên registry bên ngoài

Mô hình quyền tương tự vẫn áp dụng với Maven repository, Nexus, Artifactory, object storage và container registry:

1. **Verify job** chạy Ant và tạo JAR, chỉ có quyền đọc nguồn và ghi file tạm.
2. **Gate** kiểm tra nguồn, kết quả CI, phê duyệt và môi trường được phép.
3. **Release job** tải artifact theo đúng run/commit, nhận credential của registry.
4. **Publish step** dùng token giới hạn để tải lên đúng repository hoặc prefix; registry xác nhận đã nhận artifact.
5. **Release record** lưu version, digest, source revision, CI run, thời gian công bố và đích phân phối.

Mã giả trung lập với nhà cung cấp:

~~~yaml
# Pseudocode: điều chỉnh theo cú pháp CI và registry đang dùng.
release_job:
  protected_environment: production
  identity: registry-publisher
  steps:
    - download_verified_artifact
    - check_artifact_digest
    - run:
        command: registry-cli upload dist/app.jar
        env:
          REGISTRY_TOKEN: scoped_release_secret
    - record_publish_result
~~~

Ví dụ này mô tả ý tưởng **cấp credential tại bước upload**, không phải cú pháp chạy nguyên vẹn trên một nền tảng CI cụ thể.

Nếu bắt buộc dùng một Ant task để upload như **scp**, **sshexec** hoặc custom task tích hợp registry, vẫn phải **chỉ chạy target ấy trong release job**. Cẩn trọng với cách task đọc password/property, log **-verbose/-debug**, thông báo lỗi và việc task đưa credential vào command line. Một CLI upload riêng trong release job thường làm ranh giới credential dễ kiểm soát hơn.

## 8. Các kịch bản tấn công và lỗi vận hành thường gặp

### 8.1. Pull request sửa build.xml để truy cập secret

Một contributor có thể thêm một target gọi process hoặc mở kết nối mạng trong build.xml, script và mã Java test. Do đó, ngay cả công việc có tên **test** cũng là thực thi code không đáng tin cậy. Verify job **không được nhận secret hay quyền publish**.

Đặc biệt chú ý sự kiện **pull_request_target** trên GitHub Actions: nó chạy trong ngữ cảnh của branch đích và có thể có quyền/secret mạnh hơn so với **pull_request**. Không checkout rồi thực thi mã từ PR chưa được xét duyệt trong job có quyền cao. Nếu phải bình luận lên PR, hãy dùng metadata hoặc kết quả đã kiểm chứng trong một workflow riêng có quyền phù hợp.

### 8.2. Lộ credential do log Ant

Các lệnh **echo**, **exec**, custom task, Ant logger hoặc công cụ bên ngoài có thể in property/biến môi trường. Masking của CI không thể bảo vệ nếu token bị biến đổi, ghi sang file, được đưa vào URL hoặc gửi ra mạng. Giải pháp là không cấp secret cho verify và hạn chế việc log dữ liệu xác thực trong release step.

### 8.3. Cache hoặc artifact trung gian bị thay thế

Cache dùng để tăng tốc build không phải kho artifact phát hành có nguồn gốc đã xác minh. PR không được phép ghi lên vị trí mà job release tin tưởng như nguồn artifact cuối. Dùng artifact storage có liên kết tới đúng **workflow run và commit**, xác minh digest, giới hạn quyền ghi và không tự chọn file từ một run khác chỉ vì tên giống nhau.

### 8.4. Runner tự quản lý chia sẻ trạng thái

Tách job trong YAML chưa đủ khi runner tự quản lý tái sử dụng workspace, Docker socket, credential helper hoặc file token giữa các job. Job PR nên chạy trong môi trường tạm thời có quyền thấp, không tiếp cận production network/secrets. Runner release cần tách biệt và làm sạch trạng thái đúng cách.

### 8.5. Lỗi Classpath/test và lỗi quyền registry bị lẫn nhau

Nếu Ant thất bại ở compile/test, lỗi thuộc phạm vi **verify**, có thể là build.xml, dependency hoặc môi trường Java. Nếu JAR đã qua kiểm tra nhưng registry trả về **401 Unauthorized** hoặc **403 Forbidden**, cần điều tra credential, role, token scope, expiry và chính sách môi trường của **release**. Không nên sửa logic kiểm thử để xử lý lỗi phân quyền registry.

### 8.6. Quy trình retry và version bất biến

Upload có thể thành công nhưng CI bị ngắt trước khi ghi nhận kết quả. Khi retry, job cần tra registry theo **version và digest**: nếu cùng digest đã tồn tại, có thể xác nhận/reconcile theo chính sách; nếu version trùng nhưng byte khác, cần dừng. Tránh overwrite không có dấu vết. Một bản phát hành không nên được công bố là thành công chỉ vì upload đã bắt đầu.

## 9. Bảng quyết định khi thiết kế pipeline

| Câu hỏi | Quyết định phù hợp |
|---|---|
| PR có được chạy build.xml và test không? | Có, trong verify job hạn chế quyền |
| PR có được truy cập token publish không? | Không |
| Có nên dùng token cá nhân toàn quyền? | Ưu tiên workload identity hoặc token riêng scope nhỏ |
| Ant property có thể bảo vệ target publish không? | Không, đây chỉ là điều kiện thực thi trong build |
| Gate release nằm ở đâu? | Protected ref, environment/approval và policy registry |
| Release có cần build lại JAR? | Nên dùng đúng artifact đã kiểm chứng |
| Có nên lưu secret trong build.xml? | Không, cấp tại bước publish ở CI |
| Release thất bại do registry từ chối token? | Kiểm tra quyền và danh tính release job |
| JAR và checksum trùng có đủ chứng minh nguồn gốc? | Chưa đủ; cần ràng buộc run/commit và nguồn tin cậy |
| Có thể cho PR và release dùng cùng self-hosted runner? | Chỉ khi có cô lập/cleanup đáng tin cậy; ưu tiên tách runner |

## 10. Ghi dấu vết kiểm toán

Sau khi registry xác nhận upload, release job có thể lưu một bản ghi như sau:

~~~json
{
  "component": "ant-ci-demo",
  "version": "1.0.0",
  "sourceRevision": "<full-commit-sha>",
  "verificationRunId": "<ci-run-id>",
  "artifact": "app.jar",
  "artifactSha256": "<sha256-of-verified-jar>",
  "releaseEnvironment": "production",
  "publishedAt": "<timestamp-confirmed-after-upload>",
  "result": "PUBLISHED"
}
~~~

Đây là **mẫu dữ liệu**, không phải thông số của một lần chạy thực tế. Các giá trị trong dấu ngoặc nhọn phải được điền từ CI và registry. **publishedAt** phản ánh thời điểm công bố được xác nhận, khác với timestamp archive chuẩn hóa trong JAR hoặc thời gian job verify bắt đầu.

Audit record nên đủ thông tin truy vết: commit nào tạo artifact, run nào kiểm thử, digest nào được publish, ai hoặc gate nào phê duyệt, registry nào nhận, release ID là gì. Cùng thông tin này hỗ trợ rollback sang một artifact đã biết, thay vì rebuild một phiên bản cũ mà không chắc đầu vào đã trùng.

## 11. Những nguyên tắc cần ghi nhớ

**Tách quyền** nghĩa là verify job có thể thực thi Ant trên mã chưa được duyệt nhưng không nhận quyền ghi phát hành. **Tách thông tin xác thực** nghĩa là credential chỉ xuất hiện trong bước publish được bảo vệ, có thời hạn và phạm vi vừa đủ; việc đặt secret ở CI không có nghĩa mọi job được phép truy cập.

**Ant kiểm soát target build; nền tảng CI và registry kiểm soát quyền và phê duyệt.** Không dùng điều kiện trong build.xml, tên tag hoặc tên environment như một bằng chứng phân quyền duy nhất. Cần kết hợp protected refs, workflow review, environment rules và IAM.

**Chỉ phát hành artifact đã được kiểm chứng**, ràng buộc với revision và digest, và ghi kết quả sau khi registry xác nhận. Cách này phân biệt rõ lỗi kỹ thuật của build với lỗi quyền phát hành, đồng thời cho phép audit, retry và rollback một cách có căn cứ.

### Tài liệu tham khảo

- [Apache Ant Manual — Using Ant](https://ant.apache.org/manual/using.html): project, target, depends và property.
- [Apache Ant Manual — Java Task](https://ant.apache.org/manual/Tasks/java.html): chạy Java test với failonerror.
- [Apache Ant Manual — Jar Task](https://ant.apache.org/manual/Tasks/jar.html): tạo archive và metadata.
- [Apache Ant Manual — Checksum Task](https://ant.apache.org/manual/Tasks/checksum.html): mã băm và kiểm tra tính toàn vẹn.
- [GitHub Docs — Automatic token authentication](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication): phân quyền GITHUB_TOKEN.
- [GitHub Docs — Using environments for deployment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): environment và protection rules.
- [GitHub Docs — OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect): danh tính workload và OIDC.
- [GitHub Docs — Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): quyền, secret và mã không tin cậy.

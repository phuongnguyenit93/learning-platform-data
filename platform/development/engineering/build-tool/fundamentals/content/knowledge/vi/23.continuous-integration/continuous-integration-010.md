# Ma trận phiên bản Java, điều kiện thất bại và phạm vi kiểm chứng

Một dự án Java thường cần chạy trên nhiều phiên bản JDK. Một thư viện có thể tuyên bố hỗ trợ nhiều phiên bản Java; một service có thể được triển khai trên một JDK cụ thể nhưng cần được kiểm tra khi nâng cấp runtime; một build plugin có thể phải hoạt động với nhiều phiên bản Gradle hoặc Maven. Nếu chỉ chạy CI trên một JDK, nhóm có thể bỏ sót lỗi tương thích chỉ xuất hiện ở phiên bản khác.

**Ma trận phiên bản Java** (Java version matrix) là cách CI tạo nhiều lượt build hoặc kiểm thử từ cùng một thay đổi, mỗi lượt dùng một phiên bản JDK hoặc một tổ hợp môi trường khác nhau. Ma trận giúp kiểm chứng phạm vi tương thích đã cam kết. Tuy nhiên, cần quyết định rõ:

- Phiên bản Java nào là phiên bản được hỗ trợ chính thức?
- Mỗi phiên bản cần chạy compile, unit test, integration test hay chỉ một số bước?
- Lỗi ở một phiên bản có làm cả pipeline thất bại không?
- Có phiên bản thử nghiệm được phép thất bại mà không chặn merge không?
- Những lượt nào là required checks và những lượt nào chỉ cung cấp thông tin?
- Artifact nào được publish và từ lượt build nào?

Một ma trận tốt làm rõ hợp đồng hỗ trợ của sản phẩm, đồng thời kiểm soát thời gian CI và tài nguyên. Ma trận quá nhỏ có thể bỏ sót lỗi; ma trận quá lớn làm pipeline chậm, tốn runner và tạo nhiều kết quả khó diễn giải.

## 1. Ma trận CI là gì?

Trong CI, một matrix job lấy một tập giá trị cho một hoặc nhiều chiều (axis), rồi mở rộng thành nhiều job độc lập. Mỗi job nhận một tổ hợp giá trị cụ thể.

Ví dụ một thư viện hỗ trợ Java 17 và Java 21:

~~~text
Matrix:
  java = [17, 21]

Jobs:
  build-java-17
  build-java-21
~~~

Hai job có thể chạy đồng thời trên các runner riêng. Mỗi job checkout cùng commit, thiết lập JDK tương ứng và chạy các bước build/test đã định nghĩa.

Ma trận có thể có nhiều chiều:

~~~text
java = [17, 21]
os   = [linux, windows]

Tổ hợp:
  Java 17 + Linux
  Java 17 + Windows
  Java 21 + Linux
  Java 21 + Windows
~~~

Với hai giá trị Java và hai hệ điều hành, CI tạo bốn tổ hợp. Nếu thêm kiến trúc, database hoặc phiên bản framework, số job có thể tăng nhanh theo tích của các chiều.

### 1.1. Matrix job khác một job chạy nhiều lệnh

Một job có thể lần lượt cài nhiều JDK rồi chạy nhiều lệnh, nhưng cách đó không tương đương ma trận độc lập:

- các bước dùng chung workspace và trạng thái;
- một bước có thể thay đổi dependency hoặc output của bước sau;
- lỗi sớm có thể ngăn các phiên bản sau chạy;
- log và test report khó gắn với một JDK cụ thể;
- không tận dụng được runner song song theo từng phiên bản.

Matrix thường tạo job riêng cho từng tổ hợp, giúp log, kết quả, timeout và trạng thái rõ ràng hơn. Nếu mục tiêu chỉ là kiểm tra một số cấu hình tuần tự trên cùng runner, job đơn có thể phù hợp hơn; hãy chọn theo cách cần cô lập và báo cáo.

## 2. Xác định hợp đồng hỗ trợ Java trước khi tạo ma trận

Không nên chọn phiên bản JDK chỉ vì chúng đang có sẵn trên runner. Trước tiên, cần xác định sản phẩm cam kết hỗ trợ phiên bản nào.

| Nhóm phiên bản | Ý nghĩa | Cách xử lý trong CI |
|---|---|---|
| Minimum supported JDK | Phiên bản thấp nhất mà sản phẩm cam kết hỗ trợ | Required build và test |
| Current supported JDKs | Các phiên bản đang được hỗ trợ chính thức | Required checks theo chính sách |
| Preferred/recommended JDK | Phiên bản nhóm khuyến nghị triển khai | Có thể là lượt kiểm thử đầy đủ và release |
| Next/early-access JDK | Phiên bản sắp tới hoặc bản thử nghiệm | Informational hoặc allow-failure |
| Unsupported JDK | Nằm ngoài hợp đồng hỗ trợ | Không nhất thiết nằm trong PR matrix |

Ví dụ, một thư viện tuyên bố hỗ trợ Java 17 và Java 21, còn Java 25 đang được đánh giá. Khi đó, Java 17 và 21 là ma trận bắt buộc; Java 25 có thể chạy ở nightly hoặc lượt thử nghiệm được phép thất bại. Khi nhóm chính thức hỗ trợ Java 25, hãy chuyển nó thành required check và cập nhật tài liệu hỗ trợ.

Các số phiên bản trong ví dụ chỉ minh họa cách tổ chức. Ma trận thật phải theo chính sách hỗ trợ và toolchain của dự án.

### 2.1. Minimum version và maximum tested version

Hai thông tin này không giống nhau:

- **Minimum supported version:** phiên bản thấp nhất mà code và API được phép sử dụng.
- **Latest tested version:** phiên bản mới nhất mà pipeline đã kiểm tra.

Nếu thư viện khai báo minimum Java 17 nhưng chỉ test trên Java 21, nhóm chưa có bằng chứng trực tiếp rằng binary chạy trên Java 17. Ngược lại, nếu build bằng JDK 17 nhưng không chạy trên JDK mới hơn, nhóm có thể bỏ sót thay đổi runtime hoặc warning/API tương thích mới.

Hãy kiểm tra cả compile target và runtime thực tế để chứng minh hợp đồng hỗ trợ.

### 2.2. Phân biệt JDK dùng để build và Java version mục tiêu

Một pipeline có thể chạy compiler trên JDK 21 nhưng tạo bytecode/API tương thích Java 17 bằng tùy chọn release. Điều đó không có nghĩa ứng dụng đã được chạy trên runtime Java 17.

Có ba câu hỏi khác nhau:

1. JDK nào chạy Maven/Gradle và compiler?
2. Compiler được phép sử dụng API/bytecode của Java version nào?
3. Test và ứng dụng được thực thi trên runtime Java version nào?

Ma trận cần mô tả đúng câu hỏi mà từng job xác minh. Chỉ đặt JDK matrix mà không kiểm soát toolchain hoặc runtime có thể khiến các job tưởng như khác phiên bản nhưng thực tế vẫn dùng cùng một JDK để compile và test.

## 3. Ma trận phiên bản Java kiểm chứng điều gì?

Một matrix entry có thể thực hiện nhiều cấp kiểm chứng. Cần nêu rõ phạm vi của từng lượt.

| Phạm vi | Nội dung | Điều được chứng minh |
|---|---|---|
| Compile | Biên dịch source bằng compiler/JDK cụ thể | Code và API tương thích với compiler configuration |
| Unit test | Chạy test trong JVM phiên bản cụ thể | Hành vi ở mức unit trên runtime đó |
| Integration test | Chạy cùng service/database/container trong runtime cụ thể | Tương tác với dependency và nền tảng |
| Packaging | Tạo JAR/WAR/distribution | Quy trình đóng gói chạy được trong tổ hợp đó |
| Smoke test | Khởi động artifact và gọi luồng cơ bản | Artifact có thể khởi chạy trong môi trường đó |
| Compatibility test | Chạy binary đã tạo trên các runtime khác nhau | Một artifact tương thích với nhiều runtime |

Một job chỉ chạy compile không chứng minh test đã pass. Một job chỉ chạy test trên JDK 21 không chứng minh ứng dụng chạy trên JDK 17, dù compiler có target release 17.

### 3.1. Build riêng trên từng JDK

Mỗi matrix job có thể chạy clean verify/build bằng JDK tương ứng. Cách này kiểm tra cả compiler, test runtime và plugin behavior trên từng JDK, tùy cách toolchain được cấu hình.

Ưu điểm:

- mỗi phiên bản có log và kết quả riêng;
- phát hiện lỗi compiler/plugin chỉ xuất hiện trên một JDK;
- dễ gắn test report với runtime;
- không phụ thuộc output từ job khác.

Chi phí là compile và test lặp lại trên từng runner.

### 3.2. Compile một lần, test cùng binary trên nhiều runtime

Với một thư viện hoặc ứng dụng phát hành một binary dùng trên nhiều JDK, có thể tạo artifact một lần bằng compiler release phù hợp rồi chạy chính artifact đó trên từng runtime.

~~~text
Source commit
    |
    v
Compile/package once with target release
    |
    v
Immutable artifact
    |
    +----> Test runtime Java 17
    |
    +----> Test runtime Java 21
    |
    +----> Test runtime Java 25
~~~

Cách này kiểm tra runtime compatibility của cùng một binary, tránh mỗi job tạo ra artifact khác nhau. Tuy nhiên, nó không kiểm tra việc compile bằng từng JDK. Nếu compiler compatibility cũng là yêu cầu, cần thêm lượt compile matrix riêng.

### 3.3. Kết hợp hai cách

Một pipeline có thể:

- compile bằng JDK thấp nhất với release target;
- compile/test trên mỗi JDK được hỗ trợ;
- build một artifact release duy nhất;
- chạy smoke test artifact đó trên từng runtime;
- publish chỉ sau khi các required checks hoàn tất.

Phạm vi kiểm chứng phải được ghi rõ để tránh hiểu nhầm rằng một ma trận runtime đã kiểm tra mọi compiler/toolchain.

## 4. Chọn các chiều của ma trận

Ma trận không chỉ có Java version. Có thể thêm OS, architecture, database, framework hoặc build tool version.

| Chiều | Ví dụ giá trị | Khi nào cần |
|---|---|---|
| Java/JDK | 17, 21, 25 | Hợp đồng hỗ trợ runtime/compiler |
| OS | Linux, Windows, macOS | Có script, path, filesystem hoặc native behavior khác nhau |
| Architecture | x86_64, ARM64 | Có native library hoặc image theo kiến trúc |
| Database | PostgreSQL, MySQL | Có SQL/dialect hoặc driver khác nhau |
| Build tool | Gradle versions, Maven versions | Sản phẩm là plugin hoặc build extension |
| Framework | Spring/framework release lines | Cần xác minh compatibility với nhiều phiên bản framework |
| Test profile | unit, integration, compatibility | Các cấp kiểm chứng khác nhau |

Mỗi chiều phải trả lời một yêu cầu tương thích cụ thể. Không nên thêm mọi OS, database và framework version chỉ vì CI hỗ trợ.

### 4.1. Tránh tích Descartes quá lớn

Nếu có 3 JDK, 3 OS, 2 database và 2 build tool version, ma trận đầy đủ tạo:

~~~text
3 x 3 x 2 x 2 = 36 jobs
~~~

Nếu mỗi job mất 10 phút và chạy đồng thời có giới hạn, chi phí runner và thời gian tổng thể tăng đáng kể.

Có thể chọn chiến lược:

- chạy tất cả JDK trên Linux;
- chạy minimum và recommended JDK trên Windows/macOS;
- chạy integration test với database chính trên một JDK;
- chạy compatibility smoke test trên toàn bộ runtime;
- chạy full cross-product nightly thay vì mọi pull request.

Mục tiêu là bao phủ các rủi ro có ý nghĩa, không phải tạo nhiều tổ hợp nhất có thể.

### 4.2. Dùng include và exclude

Matrix thường cho phép loại tổ hợp không hợp lệ hoặc bổ sung metadata riêng cho một entry.

Ví dụ:

~~~yaml
strategy:
  matrix:
    java: [17, 21]
    os: [ubuntu-latest, windows-latest]
    exclude:
      - java: 17
        os: windows-latest
    include:
      - java: 25
        os: ubuntu-latest
        experimental: true
~~~

Ví dụ này tạo các tổ hợp cơ bản, bỏ một tổ hợp không cần thiết và thêm một lượt thử nghiệm. Cú pháp cụ thể phụ thuộc CI provider. Hãy xác nhận cách provider kết hợp include/exclude và các field bổ sung.

## 5. Điều kiện thất bại và fail-fast

Một ma trận cần chính sách rõ ràng về việc một job matrix thất bại ảnh hưởng đến các job còn lại như thế nào.

### 5.1. Fail-fast

Fail-fast quyết định liệu CI có hủy các job matrix đang chạy hoặc chưa bắt đầu khi một entry thất bại hay không.

| Cấu hình | Hành vi | Phù hợp khi |
|---|---|---|
| fail-fast: true | Một entry thất bại có thể khiến các entry khác bị hủy | Muốn dừng sớm, tiết kiệm runner khi lỗi đã đủ kết luận |
| fail-fast: false | Các entry còn lại tiếp tục để thu thập kết quả | Muốn biết đầy đủ phiên bản/OS nào bị ảnh hưởng |

Với Java compatibility matrix, fail-fast false thường hữu ích trên pull request hoặc nightly vì nhóm muốn biết lỗi chỉ xảy ra ở JDK nào. Tuy nhiên, nếu ma trận rất lớn và một lỗi chung đã làm mọi entry vô nghĩa, fail-fast true có thể tiết kiệm tài nguyên.

Fail-fast không phải là quy tắc cho phép lỗi. Nó chỉ điều khiển việc hủy các job khác sau khi một job thất bại.

### 5.2. Một matrix job thất bại có làm toàn workflow thất bại không?

Thông thường, nếu một entry bắt buộc trong matrix thất bại thì matrix job có kết quả thất bại và workflow không đạt. Đây là hành vi cần thiết để required check phản ánh đầy đủ hợp đồng hỗ trợ.

Nếu một entry là thử nghiệm hoặc không nằm trong phạm vi hỗ trợ chính thức, có thể dùng policy allow-failure riêng. Không nên vô tình cho phép mọi JDK thất bại mà vẫn merge.

### 5.3. continue-on-error

continue-on-error cho phép một job hoặc step thất bại mà không làm kết quả workflow bị coi là thất bại theo cách thông thường. Đây là công cụ hữu ích cho phiên bản thử nghiệm, nightly compatibility hoặc bước thu thập thông tin không chặn merge.

Ví dụ GitHub Actions:

~~~yaml
continue-on-error: ${{ matrix.experimental || false }}
~~~

Chỉ entry có thuộc tính experimental true được phép thất bại. Các phiên bản được hỗ trợ chính thức vẫn phải pass.

Không dùng continue-on-error cho toàn bộ matrix chỉ để tránh pipeline đỏ. Khi đó, lỗi ở minimum supported JDK cũng có thể không chặn merge.

### 5.4. Fail-fast và continue-on-error là hai quyết định khác nhau

- fail-fast quyết định có hủy các entry khác khi một entry thất bại không.
- continue-on-error quyết định lỗi của entry/step có làm job/workflow bị đánh dấu thất bại không.

Có thể đặt fail-fast false để thu thập mọi kết quả, nhưng vẫn để mọi phiên bản được hỗ trợ là required. Cũng có thể cho phép một entry experimental thất bại trong khi các entry chính thức tiếp tục được kiểm tra.

## 6. Điều kiện chạy job và step

CI có thể chạy ma trận khác nhau tùy sự kiện, nhánh, đường dẫn file hoặc trạng thái của job trước.

Các điều kiện thường gặp:

- chỉ chạy trên pull request hoặc push vào nhánh chính;
- chạy full matrix khi thay đổi source Java hoặc build configuration;
- chạy smoke test khi thay đổi tài liệu;
- chạy integration test khi có service/container cần thiết;
- chạy release job sau khi toàn bộ required checks pass;
- bỏ qua publish với pull request từ fork;
- chạy nightly matrix mở rộng theo lịch.

### 6.1. Điều kiện ở cấp job

Job-level condition quyết định có tạo/chạy job hay không. Nếu một job bị skip, required check và dependency graph của workflow có thể thể hiện trạng thái khác với job pass.

Hãy bảo đảm các điều kiện không vô tình skip lượt kiểm tra bắt buộc trên pull request. Nếu một job là required check, branch protection cần được cấu hình theo trạng thái mà CI provider công bố.

### 6.2. Điều kiện ở cấp step

Step-level condition có thể bỏ qua một bước phụ, ví dụ upload report khi file report tồn tại. Nếu test thất bại, bước upload report thường vẫn nên chạy để giữ bằng chứng.

Ví dụ với GitHub Actions:

~~~yaml
- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-reports-${{ matrix.java }}
    path: |
      **/target/surefire-reports/**
      **/build/test-results/**
    if-no-files-found: ignore
~~~

Điều kiện always giúp bước thu thập report chạy cả khi test step thất bại hoặc bị skip theo một số trạng thái. Cần kiểm tra cú pháp và semantics của provider khi dùng điều kiện tương tự.

### 6.3. Điều kiện publish

Publish nên có điều kiện chặt hơn test:

- chỉ chạy trên nhánh/tag phát hành được phép;
- chỉ chạy sau khi required matrix checks pass;
- không publish từ pull request không đáng tin cậy;
- chỉ publish một lần cho một version;
- không dùng một matrix entry tùy ý làm nguồn artifact cuối.

Không nên đặt publish trong từng matrix entry nếu tất cả entry cùng tạo và upload một tọa độ/version. Điều này dễ tạo xung đột, publish lặp hoặc ghi đè artifact.

## 7. Ví dụ GitHub Actions: ma trận Java cơ bản

Workflow dưới đây minh họa một thư viện hỗ trợ Java 17 và 21. Mỗi entry chạy trên Ubuntu, cài JDK tương ứng và thực hiện Maven verify.

~~~yaml
name: Java compatibility

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    name: Verify on Java ${{ matrix.java }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Verify
        run: ./mvnw -B verify
~~~

Mỗi matrix entry có runner riêng. fail-fast false cho phép các phiên bản còn lại tiếp tục sau khi một entry thất bại, giúp nhóm xem toàn bộ kết quả.

Trong workflow thật, cần chọn action version, JDK distribution và runner theo chính sách của repository. Wrapper phải có trong source control và lệnh cần tương thích với hệ điều hành runner.

### 7.1. Thêm phiên bản thử nghiệm được phép thất bại

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    continue-on-error: ${{ matrix.experimental || false }}
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21]
        include:
          - java: 25
            experimental: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
      - run: ./mvnw -B verify
~~~

Java 17 và 21 vẫn là phiên bản được hỗ trợ chính thức và phải pass. Java 25 được chạy để phát hiện sớm vấn đề nhưng được đánh dấu experimental. Khi chính thức hỗ trợ Java 25, bỏ thuộc tính experimental hoặc chuyển entry vào danh sách required.

Đừng chỉ dựa vào tên job để phân biệt required và informational. Cần xem cách provider đánh giá continue-on-error và cách branch protection chọn required status checks.

### 7.2. Thêm chiều hệ điều hành

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: [17, 21]
    os: [ubuntu-latest, windows-latest]
    exclude:
      - java: 17
        os: windows-latest
~~~

Ma trận này chạy các tổ hợp được giữ lại. Nếu có script shell chỉ chạy trên Linux hoặc path handling khác trên Windows, OS matrix giúp phát hiện lỗi nền tảng. Không cần chạy mọi test integration trên mọi OS nếu rủi ro không tương xứng với chi phí.

## 8. Ví dụ GitHub Actions: compile một lần, test artifact trên nhiều runtime

Nếu mục tiêu là kiểm tra cùng một JAR trên nhiều runtime, có thể tách build job và runtime matrix:

~~~yaml
jobs:
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: 21
          cache: maven
      - run: ./mvnw -B clean package -DskipTests
      - uses: actions/upload-artifact@v4
        with:
          name: application-package
          path: target/application.jar

  runtime-test:
    needs: package
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21, 25]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: application-package
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
      - name: Smoke test
        run: java -jar application.jar --smoke-test
~~~

Đây là ví dụ về mô hình, không phải mọi ứng dụng đều có tham số --smoke-test. Artifact phải được tạo với target bytecode phù hợp và có dependency runtime đầy đủ. Nếu JAR cần database hoặc service, runtime job phải cung cấp môi trường test tương ứng.

Điểm quan trọng là các job runtime tải cùng artifact từ package job. Chúng không build lại source thành những JAR khác nhau.

### 8.1. Không bỏ qua test cần thiết khi package

Ví dụ trên dùng skipTests chỉ để minh họa việc tách package và runtime smoke test. Trong pipeline thực tế, vẫn cần một job kiểm thử đầy đủ trước khi publish. Có thể package cùng lúc với test ở job build, rồi upload artifact sau khi test pass; hoặc tạo artifact rồi test chính artifact đó trước khi promote.

Không publish artifact chỉ vì bước package thành công nếu các test bắt buộc chưa chạy.

## 9. Gradle: chọn JDK cho từng matrix entry

Gradle Wrapper xác định phiên bản Gradle, còn JDK trên runner có thể được cài qua CI action. Java toolchain trong build script quyết định compiler/test launcher theo cấu hình.

Ví dụ Gradle CI job:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: [17, 21]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: ${{ matrix.java }}
  - uses: gradle/actions/setup-gradle@v4
  - run: ./gradlew clean check
~~~

Nếu build dùng toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

thì mỗi matrix entry có thể vẫn chọn JDK 21 làm compiler/test toolchain, dù runner JDK khác. Nếu muốn mỗi entry thật sự compile/test bằng JDK của matrix, hãy để toolchain version lấy từ cấu hình matrix hoặc cấu hình build phù hợp.

Một cách truyền giá trị vào Gradle:

~~~kotlin
val ciJavaVersion = providers.gradleProperty("ciJavaVersion")
    .map(String::toInt)
    .orElse(21)

java {
    toolchain {
        languageVersion = ciJavaVersion.map(JavaLanguageVersion::of)
    }
}
~~~

Lệnh CI:

~~~bash
./gradlew clean check -PciJavaVersion=17
~~~

Ví dụ này minh họa cách nối matrix value với toolchain. Cần bảo đảm JDK tương ứng đã có sẵn hoặc toolchain resolver được cấu hình để cung cấp nó.

### 9.1. Runner JDK và toolchain JDK

Gradle daemon chạy trên một JVM. Compiler và test task có thể dùng toolchain JVM khác. Vì vậy, log cần ghi nhận:

- JDK chạy Gradle daemon;
- JDK compiler dùng;
- JDK test worker dùng;
- target release của bytecode.

Nếu cả matrix entry đều dùng toolchain cố định, thay JDK runner có thể không tạo ra coverage như dự định.

## 10. Maven: toolchain và compiler release

Maven có thể chạy bằng JDK của runner và chọn compiler toolchain theo cấu hình. Cần phân biệt JDK chạy Maven với JDK mà Maven Compiler Plugin dùng.

### 10.1. Cấu hình compiler release

Trong POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Compiler release giới hạn API Java và bytecode mục tiêu theo phiên bản được chọn. Nếu build chạy trên JDK 21 với release 17, code được kiểm tra theo API/bytecode Java 17; nhưng test process vẫn có thể chạy trên JDK 21.

### 10.2. Chọn compiler toolchain

Maven Toolchains Plugin cho phép build yêu cầu một JDK toolchain được cấu hình trên máy. File toolchains của developer/CI ánh xạ version/vendor sang đường dẫn cài đặt JDK.

Một ví dụ khai báo yêu cầu toolchain trong POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>17</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Máy chạy build phải có toolchain matching trong cấu hình Maven toolchains. Chỉ thêm plugin vào POM không tự cài JDK. CI cần thiết lập JDK và toolchain mapping đúng với matrix entry.

### 10.3. Test runtime cũng cần đúng JDK

Compiler toolchain và test JVM là hai lựa chọn khác nhau. Nếu yêu cầu kiểm tra runtime Java 17, Surefire/Failsafe phải chạy fork bằng Java 17. Chỉ cấu hình compiler release 17 nhưng test trên JDK 21 không chứng minh runtime Java 17.

Khi chạy một job matrix cho mỗi JDK, cách đơn giản là runner/JAVA_HOME tương ứng với entry và để test plugin dùng JDK đó, trừ khi project cấu hình toolchain test riêng.

## 11. --release, sourceCompatibility và targetCompatibility

Các tùy chọn này thường bị nhầm với ma trận runtime.

| Cấu hình | Mục đích |
|---|---|
| JDK/Java toolchain | Chọn compiler hoặc JVM được dùng |
| source compatibility | Giới hạn cú pháp/source language level |
| target compatibility | Chọn mức bytecode được tạo |
| javac --release | Chọn language level, target và tập API nền tảng tương ứng |
| Runtime matrix | Chạy ứng dụng/test trên từng JDK thực tế |

Với Java hiện đại, --release thường là cách phù hợp để compile một target Java cũ từ JDK mới, vì nó cũng giới hạn API nền tảng có thể tham chiếu. Chỉ đặt target bytecode mà không kiểm soát API có thể dẫn đến class compile được nhưng không chạy trên runtime cũ.

Ví dụ:

~~~bash
javac --release 17 -d out src/main/java/example/Main.java
~~~

Lệnh này tạo bytecode và kiểm tra API theo Java 17. Để chứng minh binary chạy trên Java 17, vẫn cần chạy test hoặc smoke test bằng runtime Java 17.

## 12. Thiết kế ma trận theo loại sản phẩm

Ma trận phù hợp phụ thuộc loại dự án.

### 12.1. Thư viện Java

Mục tiêu chính:

- không dùng API cao hơn minimum supported version;
- compile target đúng;
- test binary trên các runtime được hỗ trợ;
- kiểm tra public API và dependency compatibility.

Một chiến lược thường dùng:

| Job | JDK | Phạm vi |
|---|---|---|
| Compile compatibility | Minimum supported | Compile với release thấp nhất |
| Test matrix | Mỗi JDK được hỗ trợ | Unit test |
| API/packaging | Recommended JDK | JAR, sources, Javadoc và metadata |
| Early access | JDK sắp tới | Informational/nightly |

### 12.2. Ứng dụng service

Nếu service chỉ deploy trên một JDK chính thức, có thể:

- build và test đầy đủ trên JDK triển khai;
- chạy smoke/compatibility test trên JDK sắp nâng cấp;
- chạy một lượt trên minimum runtime nếu vẫn hỗ trợ nhiều runtime;
- kiểm tra container image và base image tương ứng.

Không cần compile và package lại trên mọi JDK nếu mục tiêu là chạy cùng artifact trên các runtime.

### 12.3. Build plugin hoặc thư viện tích hợp build tool

Plugin có thể cần ma trận hai chiều:

- JDK chạy Gradle/Maven;
- phiên bản Gradle/Maven được hỗ trợ.

Ví dụ một Gradle plugin có thể cần test trên nhiều Gradle release lines, kết hợp với các JDK mà từng Gradle version hỗ trợ. Đây là ma trận compatibility của build tool, không chỉ Java runtime.

Hãy dùng include/exclude để loại tổ hợp mà Gradle/Maven không thể chạy trên JDK đó. Tài liệu compatibility của chính build tool là nguồn xác định tổ hợp hợp lệ.

### 12.4. Ứng dụng native hoặc có JNI

Nếu có native library, ma trận cần xem xét OS và architecture ngoài JDK. Một JDK matrix trên Linux x86_64 không chứng minh native code hoạt động trên Windows ARM64.

Chạy smoke test trên đúng target platform và kiểm tra thư viện native được đóng gói/resolve đúng.

## 13. Phạm vi kiểm chứng theo loại sự kiện CI

Không phải mọi event cần chạy cùng một ma trận.

| Sự kiện | Phạm vi thường phù hợp | Mục tiêu |
|---|---|---|
| Pull request | Ma trận JDK được hỗ trợ, unit test, compile và kiểm tra nhanh | Phản hồi nhanh trước merge |
| Push vào main | Required matrix đầy đủ, integration test chọn lọc | Xác nhận trạng thái nhánh chính |
| Nightly | Ma trận rộng hơn, OS/framework/early-access, stress hoặc compatibility | Phát hiện vấn đề không cần chặn từng PR |
| Release candidate | Full verification, package, smoke test và kiểm tra provenance | Xác nhận sản phẩm sắp phát hành |
| Tag/release | Publish đúng artifact sau required checks | Phát hành có kiểm soát |

PR matrix nên đủ để bắt lỗi ảnh hưởng cam kết hỗ trợ, nhưng không nhất thiết chứa mọi tổ hợp OS/database/early-access. Nightly có thể mở rộng phạm vi để giảm thời gian phản hồi trên PR.

### 13.1. Không để PR bỏ qua minimum supported JDK

Nếu Java 17 là minimum supported, job Java 17 nên là required check trên PR. Không nên chỉ chạy JDK mới nhất rồi giả định tương thích ngược.

### 13.2. Nightly không thay thế required check

Nightly có thể chạy các phiên bản thử nghiệm hoặc tổ hợp đắt tiền. Nhưng nếu một phiên bản nằm trong hợp đồng hỗ trợ, kiểm chứng thiết yếu nên chạy trước merge hoặc trước phát hành theo chính sách của nhóm.

### 13.3. Release phải dùng cùng phạm vi đã định nghĩa

Release job nên phụ thuộc các required verification. Nếu release dùng một JDK khác hoặc build lại với tham số khác, cần chạy kiểm tra tương ứng và ghi nhận artifact mới.

## 14. Required checks và branch protection

CI matrix có thể tạo nhiều job với tên động theo JDK/OS. Branch protection cần yêu cầu đúng trạng thái kiểm tra.

Ví dụ tên:

~~~text
Verify (Java 17)
Verify (Java 21)
Verify (Java 25 experimental)
~~~

Hai job đầu có thể là required; job Java 25 informational. Cần kiểm tra provider có thể biểu diễn required status theo matrix entry như mong muốn không. Một số hệ thống yêu cầu tên check ổn định hoặc một aggregate job.

### 14.1. Aggregate gate

Có thể tạo một job tổng hợp phụ thuộc các matrix jobs:

~~~yaml
jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21]
    runs-on: ubuntu-latest
    steps:
      - run: ./mvnw -B verify

  required-gate:
    if: always()
    needs: verify
    runs-on: ubuntu-latest
    steps:
      - name: Require supported matrix
        run: |
          test "$${{ needs.verify.result }}" = "success"
~~~

Ví dụ này chỉ minh họa aggregate status cho một matrix job. Với workflow phức tạp có nhiều required jobs, aggregate gate cần kiểm tra kết quả của tất cả dependency bắt buộc và phân biệt failure với skipped/cancelled. Không nên dùng always() rồi chỉ kiểm tra một trạng thái nếu job còn có các dependency khác.

### 14.2. Skipped khác success

Một job bị skip do condition không nhất thiết có nghĩa kiểm chứng đã pass. Nếu required check bị skip vì biểu thức branch/path sai, branch protection có thể chặn merge hoặc, tùy cấu hình provider, trạng thái tổng hợp có thể không phản ánh mong muốn.

Hãy kiểm tra trạng thái thực tế của workflow khi:

- PR thay đổi file ngoài source;
- PR từ fork;
- job matrix bị hủy;
- một entry experimental thất bại;
- job dependency bị skip;
- workflow được chạy thủ công.

## 15. Điều kiện thất bại trong từng lượt matrix

Một entry matrix nên có kết quả dễ diễn giải:

- **Pass:** mọi bước bắt buộc trong phạm vi entry thành công.
- **Fail:** compile/test/package hoặc kiểm chứng bắt buộc thất bại.
- **Skipped:** điều kiện không cho chạy; cần biết lý do.
- **Cancelled:** bị hủy bởi fail-fast, timeout hoặc người dùng.
- **Allowed failure:** lỗi được chấp nhận theo policy, thường cho phiên bản thử nghiệm.
- **Neutral/informational:** kết quả cung cấp thông tin nhưng không chặn merge, tùy provider.

Không gộp các trạng thái này thành “green” mà không hiểu ý nghĩa. Một lượt bị skipped không phải bằng chứng tương thích.

### 15.1. Phân loại lỗi

Khi một JDK matrix entry fail, cần phân biệt:

1. **Product failure:** code hoặc test thực sự không tương thích.
2. **Toolchain failure:** JDK không được cài đúng hoặc Maven/Gradle không chạy được.
3. **Infrastructure failure:** runner, network, repository hoặc service bị lỗi.
4. **Test flakiness:** kết quả không ổn định do race, timing hoặc trạng thái dùng chung.
5. **Policy/configuration error:** entry không nên chạy hoặc được cấu hình sai.

Chỉ product failure mới trực tiếp cho thấy sản phẩm không đáp ứng hợp đồng Java. Các lỗi khác vẫn cần xử lý nhưng không nên kết luận vội về tương thích.

### 15.2. Retry có kiểm soát

Retry có thể phù hợp với lỗi hạ tầng tạm thời, nhưng không nên tự động retry mọi test fail rồi coi lần pass sau là thành công không cần ghi nhận. Hãy giữ kết quả lần đầu, số lần retry và nguyên nhân.

Nếu lỗi chỉ xuất hiện trên một JDK, cần tái hiện trên cùng runtime và kiểm tra stack trace, compiler/runtime version cùng dependency.

## 16. Phạm vi test cần chạy trên từng JDK

Chạy toàn bộ test trên mọi JDK có thể tốn kém. Có thể chia test thành các nhóm theo rủi ro.

| Nhóm kiểm thử | Trên mỗi supported JDK? | Lý do |
|---|---|---|
| Compile source/API compatibility | Có, hoặc có job compile release riêng | Phát hiện API/bytecode không tương thích |
| Unit test cốt lõi | Thường có | Xác nhận hành vi runtime |
| Serialization/reflection/class loading | Nên có nếu sản phẩm dùng nhiều | Có thể thay đổi theo runtime |
| Integration test nặng | Theo JDK chính và các phiên bản có rủi ro | Chi phí service cao |
| Database/container integration | Có thể giới hạn tổ hợp | Tránh nhân chi phí vô ích |
| UI/native/platform test | Theo OS/architecture liên quan | Phụ thuộc nền tảng |
| Smoke test artifact | Nên chạy trên mọi runtime được hỗ trợ | Kiểm tra binary thực tế |
| Performance benchmark | Chạy riêng, môi trường ổn định | Không nên làm PR gate nếu kết quả nhiễu |

Không có quy tắc một ma trận phù hợp cho mọi dự án. Hãy xác định phạm vi theo rủi ro, thời gian CI và cam kết tương thích.

## 17. Ma trận và artifact: tránh publish nhiều lần

Nếu mỗi matrix entry chạy package, tất cả có thể tạo cùng tên artifact nhưng bytecode hoặc metadata khác nhau. Nếu mỗi entry publish cùng tọa độ/version lên repository, chúng có thể ghi đè hoặc xung đột.

Một pipeline phát hành an toàn thường:

1. chạy các matrix jobs để kiểm chứng;
2. có một job package/release được chọn làm nguồn artifact;
3. tạo artifact một lần với toolchain và release target đã xác định;
4. chạy smoke/compatibility test trên artifact đó nếu cần;
5. publish đúng một lần sau khi required checks pass;
6. ghi lại checksum, commit và build metadata.

### 17.1. Tên artifact theo matrix

Nếu cần lưu output của từng entry để chẩn đoán, tên phải chứa giá trị matrix:

~~~text
test-report-java-17-linux
test-report-java-21-linux
package-java-17
package-java-21
~~~

Không upload nhiều file khác nội dung dưới cùng một tên artifact nếu CI provider coi tên đó là duy nhất.

### 17.2. Chọn artifact release

Nếu release cần một binary duy nhất, hãy chỉ định rõ job nào tạo nó. Không lấy ngẫu nhiên artifact từ entry đầu tiên hoặc artifact cuối cùng upload.

Với thư viện compile target Java 17, có thể tạo release JAR một lần từ build đã cấu hình release 17, sau đó chạy cùng JAR trên mọi runtime supported. Các matrix jobs khác chủ yếu cung cấp bằng chứng compatibility.

## 18. Cache trong Java version matrix

Cache giúp matrix job không phải tải dependency từ đầu, nhưng cache key cần phản ánh những yếu tố làm thay đổi output.

### 18.1. Dependency cache

Maven local repository hoặc Gradle dependency cache có thể được chia sẻ qua cache action theo wrapper files và build files. Việc dùng chung dependency cache giữa các JDK thường có thể phù hợp nếu artifact dependency giống nhau; tuy nhiên, cần tính đến native classifier, toolchain-specific artifact hoặc metadata khác.

### 18.2. Build output cache

Nếu output bytecode hoặc generated output phụ thuộc JDK, cache key/task input phải bao gồm toolchain/compiler version. Gradle thường tính toolchain và task inputs vào cache key theo task model, nhưng custom task cần khai báo input đầy đủ.

### 18.3. Cache key có chứa Java version?

Nếu cache chỉ lưu dependency downloads và các file này độc lập với JDK, có thể không cần tách hoàn toàn theo Java version. Nếu cache lưu compiled output, annotation processing output hoặc native artifact phụ thuộc JDK/OS/architecture, cần bảo đảm cache key phân biệt các input đó.

Đừng thêm Java version vào mọi cache key một cách máy móc; cũng đừng dùng chung compiled output giữa toolchain khác nhau khi output có thể khác.

## 19. Ma trận OS và Java: các vấn đề riêng

Một số lỗi chỉ xuất hiện trên một OS:

- đường dẫn và ký tự phân tách;
- phân biệt chữ hoa/chữ thường trong tên file;
- quyền executable của script;
- symlink;
- line endings;
- tên file dành riêng trên Windows;
- native library và architecture;
- shell khác nhau.

Ví dụ một resource tên config/Database.properties có thể được truy cập khác nhau trên filesystem phân biệt hoa thường. Test chỉ chạy Windows có thể không phát hiện sai chữ hoa/chữ thường mà Linux phát hiện.

Hãy chọn OS matrix theo rủi ro thực tế. Nếu sản phẩm chỉ deploy trên Linux, có thể chạy full suite Linux và một smoke check Windows cho script developer. Nếu phân phối desktop đa nền tảng, OS matrix cần rộng hơn.

## 20. Ma trận phiên bản build tool

Đối với sản phẩm là Gradle plugin, Maven plugin hoặc build extension, ma trận Java đơn lẻ chưa đủ. Cần xác định:

- JDK chạy build tool;
- phiên bản Gradle/Maven được hỗ trợ;
- JDK toolchain dùng để compile project;
- test runtime;
- phiên bản API/plugin mà extension tích hợp.

Ví dụ Gradle plugin:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    gradle: ["8.x", "9.x"]
    java: [17, 21]
~~~

Đây chỉ là ma trận minh họa. Không phải mọi tổ hợp đều hợp lệ; cần loại tổ hợp mà Gradle version không hỗ trợ JDK đó hoặc plugin không cam kết hỗ trợ.

Ma trận compatibility có thể dùng include để chọn tổ hợp đại diện, thay vì chạy toàn bộ tích Descartes.

## 21. Báo cáo kết quả ma trận

Một ma trận có giá trị khi người đọc biết entry nào đã chạy và phạm vi nào đã được kiểm chứng.

Report nên thể hiện:

- commit hoặc source revision;
- JDK vendor/version;
- Java release target;
- build tool và plugin version;
- OS/architecture;
- task/phase đã chạy;
- test count, pass/fail/skipped;
- artifact digest nếu có;
- thời gian và trạng thái job;
- có retry hoặc continue-on-error không.

### 21.1. Tách report theo entry

Mỗi job nên upload report với tên duy nhất. Nếu nhiều job cùng ghi một path trên runner riêng, artifact upload vẫn cần tên khác để tránh trùng khi hợp nhất.

### 21.2. Tổng hợp sau matrix

Một aggregate job có thể thu thập report từ các matrix entries và tạo bảng:

| JDK | Compile | Unit test | Integration | Smoke | Required |
|---|---|---|---|---|---|
| 17 | Pass | Pass | Pass | Pass | Yes |
| 21 | Pass | Pass | Pass | Pass | Yes |
| 25 | Pass | Pass | Skipped | Pass | Informational |

Bảng này là ví dụ. Skipped cần có lý do rõ ràng, chẳng hạn integration service không được cấu hình trong early-access job. Không nên diễn giải skipped là pass.

## 22. Troubleshooting ma trận Java

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Chỉ JDK thấp nhất compile fail | Dùng API hoặc syntax mới hơn minimum version | Kiểm tra release/toolchain và dependency bytecode |
| Compile pass nhưng runtime cũ fail | Binary hoặc dependency dùng API mới hơn | Chạy artifact trên runtime cũ, kiểm tra dependency và class version |
| Mọi entry fail cùng bước setup | Action, network, wrapper hoặc CI config | Xem log setup trước khi kết luận product failure |
| Một JDK fail, các JDK khác pass | Runtime/compiler behavior hoặc dependency compatibility | Ghi java -version, stack trace và dependency tree |
| Matrix job bị cancelled sau lỗi đầu | fail-fast đang bật | Tắt fail-fast nếu cần thu thập đủ kết quả |
| Experimental failure làm PR đỏ | continue-on-error hoặc required checks chưa đúng | Xem job policy và branch protection |
| Job xanh dù supported JDK bị skip | Condition hoặc aggregate gate sai | Kiểm tra job result và required status |
| Nhiều artifact cùng version bị upload | Publish nằm trong từng matrix entry | Tách một release job duy nhất |
| Matrix chạy quá lâu | Quá nhiều tổ hợp hoặc integration test nhân theo JDK | Chọn phạm vi theo rủi ro, shard hoặc nightly |
| Test report bị ghi đè | Artifact/report name không chứa matrix value | Tạo tên riêng theo JDK/OS/shard |
| Mỗi entry dùng cùng một JDK dù matrix khác | Toolchain cố định không lấy matrix value | Kiểm tra runner JDK và compiler/test toolchain |
| Build cache trả output từ JDK khác | Cache key/task input thiếu toolchain dimension | Kiểm tra task inputs và cache key |

### 22.1. Kiểm tra JDK thực tế trong job

Thêm bước ghi phiên bản:

~~~bash
java -version
javac -version
./mvnw -version
./gradlew --version
~~~

Các lệnh này cho biết JDK mà process nhìn thấy và build tool đang dùng. Nếu project có toolchain riêng, cần thêm log để xác nhận compiler/test launcher thực tế.

### 22.2. Kiểm tra class file version

Nếu nghi binary không tương thích runtime, có thể dùng javap:

~~~bash
javap -verbose -classpath target/classes com.example.Main
~~~

Phần major version cho biết class file target. Nhưng class version chỉ là một phần; dependency cũng có thể chứa class được biên dịch bằng Java mới hơn.

### 22.3. Kiểm tra dependency

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra cả dependency bắc cầu. Một thư viện chính có thể tương thích Java 17 nhưng dependency bắc cầu mới hơn lại yêu cầu Java 21.

## 23. Chính sách thất bại đề xuất

Một chính sách dễ hiểu có thể chia thành ba lớp:

| Lớp | Ví dụ | Kết quả khi fail |
|---|---|---|
| Required compatibility | Minimum và mọi JDK được hỗ trợ | Chặn merge/release |
| Extended verification | OS/database/framework matrix mở rộng | Chặn release hoặc yêu cầu xử lý theo policy |
| Experimental compatibility | Early-access JDK hoặc tổ hợp chưa hỗ trợ | Báo cáo, không chặn merge trong giai đoạn thử nghiệm |

Chính sách cần được ghi trong repository documentation và cấu hình CI tương ứng. Nếu một phiên bản chuyển từ experimental sang supported, thay đổi cả ma trận, required checks và tài liệu hỗ trợ trong cùng một thay đổi có chủ đích.

### 23.1. Điều kiện để một JDK trở thành supported

Nhóm có thể yêu cầu:

- compile thành công với target API phù hợp;
- unit test pass trên runtime đó;
- integration/smoke test đại diện pass;
- dependency/framework được xác nhận tương thích;
- CI check trở thành required;
- tài liệu cài đặt và hỗ trợ được cập nhật;
- release artifact được thử chạy trên runtime đó.

Không nên chỉ thêm số JDK vào matrix rồi tuyên bố hỗ trợ nếu test hoặc dependency chưa bao phủ.

### 23.2. Khi ngừng hỗ trợ một JDK

Khi bỏ hỗ trợ:

- cập nhật minimum/maximum support policy;
- loại JDK khỏi required matrix;
- giữ hoặc bỏ nightly coverage theo nhu cầu;
- cập nhật compiler release/toolchain;
- thông báo trong release notes;
- xác định version cuối cùng còn hỗ trợ JDK đó.

Việc loại JDK khỏi CI mà không cập nhật tài liệu có thể khiến người dùng hiểu nhầm sản phẩm vẫn hỗ trợ.

## 24. Quy trình thiết kế ma trận từ đầu

1. **Viết hợp đồng hỗ trợ:** xác định minimum, supported và experimental JDK.
2. **Chọn câu hỏi cần kiểm chứng:** compile, unit test, integration, smoke hay build plugin compatibility.
3. **Tách runner JDK, toolchain và target release:** không để một cấu hình đại diện nhầm cho cấu hình khác.
4. **Chọn các matrix axes:** Java, OS, architecture, database hoặc build tool khi có lý do.
5. **Kiểm tra tổ hợp hợp lệ:** loại các tổ hợp không được build tool/framework hỗ trợ.
6. **Đặt failure policy:** required, fail-fast, allow-failure và conditions.
7. **Đặt phạm vi theo event:** PR, main, nightly và release.
8. **Giới hạn concurrency:** cân nhắc runner quota, database, memory và thời gian.
9. **Đặt tên report/artifact:** gắn Java/OS/shard để tránh ghi đè.
10. **Tách publish:** chỉ một job phát hành artifact sau required checks.
11. **Kiểm tra branch protection:** bảo đảm required checks không bị skip hoặc allow-failure nhầm.
12. **Ghi nhận kết quả:** JDK thực tế, target release, test scope và artifact digest.
13. **Cập nhật khi support policy thay đổi:** matrix và tài liệu phải đi cùng nhau.

## 25. Ví dụ ma trận thực tế cho thư viện Java

Giả sử thư viện cam kết hỗ trợ Java 17 và 21, đồng thời muốn theo dõi Java 25. Có thể thiết kế:

| Job | JDK | Công việc | Policy |
|---|---|---|---|
| compile-minimum | 17 | Compile với release 17 | Required |
| test-java-17 | 17 | Unit test và compatibility test | Required |
| test-java-21 | 21 | Unit test và compatibility test | Required |
| runtime-java-25 | 25 | Smoke test hoặc unit test đại diện | Experimental |
| os-windows | 21 | Test path/script liên quan Windows | Required hoặc extended |
| nightly-full | 17, 21, 25 | Integration và matrix mở rộng | Nightly policy |
| release-package | JDK được chọn | Package một artifact bất biến | Chỉ sau required checks |

Trong mô hình này, Java 17/21 là hợp đồng hỗ trợ; Java 25 cung cấp tín hiệu sớm. Release job tạo một artifact duy nhất theo release target và được test trên các runtime cần thiết trước khi publish.

## 26. Bài tập thực hành

### Bài 1 — Tạo Java matrix hai phiên bản

Tạo workflow CI với hai JDK được hỗ trợ. Mỗi entry checkout cùng commit, cài JDK, chạy Maven verify hoặc Gradle check và có tên job chứa Java version. Xác nhận hai entry có log và report riêng.

### Bài 2 — Phân biệt compiler và runtime

Chạy compiler bằng JDK mới với release target thấp hơn. Sau đó chạy cùng artifact trên runtime thấp nhất và runtime mới hơn. Ghi lại điều gì được kiểm chứng ở mỗi bước.

### Bài 3 — Thêm experimental JDK

Thêm một entry early-access/next JDK, bật fail-fast false và allow-failure chỉ cho entry đó. Kiểm tra lỗi ở supported JDK vẫn làm required check thất bại.

### Bài 4 — Kiểm tra fail-fast

Tạo một matrix test có một entry cố ý fail. Chạy với fail-fast true rồi false. Quan sát các entry còn lại bị hủy hay tiếp tục, và phân biệt với continue-on-error.

### Bài 5 — Mở rộng OS matrix

Thêm Windows vào matrix. Chọn một test file/path hoặc script có khác biệt nền tảng. Kiểm tra báo cáo chỉ ra đúng tổ hợp OS/JDK.

### Bài 6 — Compile một lần, test nhiều runtime

Tạo một artifact với target Java phù hợp, upload artifact từ package job rồi download trong runtime matrix. Xác nhận các runtime jobs dùng cùng một checksum.

### Bài 7 — Required check và skipped job

Tạo một job có điều kiện chạy theo đường dẫn file. Thử PR thay đổi file ngoài điều kiện và quan sát trạng thái job/aggregate gate. Điều chỉnh để required check không bị bỏ qua ngoài chủ đích.

### Bài 8 — Tách publish khỏi matrix

Thiết kế workflow trong đó matrix chỉ verify. Một release job duy nhất chờ tất cả required checks, tạo hoặc nhận artifact đã kiểm thử và publish một lần. Đặt tên artifact có version và digest.

### Bài 9 — Ước lượng chi phí matrix

Tính số job khi thêm Java, OS, database và build tool axes. Chọn tổ hợp cần chạy trên PR, nightly và release; giải thích rủi ro nào được bao phủ bởi mỗi lượt.

## 27. Câu hỏi tự kiểm tra

1. Matrix CI là gì và một matrix entry đại diện cho điều gì?
2. Vì sao số job tăng theo tích của các chiều?
3. Minimum supported JDK khác latest tested JDK như thế nào?
4. JDK chạy build, compiler toolchain, target release và runtime test khác nhau ở đâu?
5. Một compile matrix có chứng minh runtime compatibility không?
6. Khi nào nên compile một lần rồi chạy cùng artifact trên nhiều runtime?
7. fail-fast khác continue-on-error như thế nào?
8. Vì sao không nên cho phép mọi supported JDK thất bại?
9. Include và exclude giúp kiểm soát tổ hợp ra sao?
10. Khi nào nên chạy full matrix trên PR và khi nào chuyển một phần sang nightly?
11. Branch protection cần bảo đảm điều gì với required matrix checks?
12. Vì sao skipped không đồng nghĩa pass?
13. Tại sao publish không nên nằm trong từng matrix entry?
14. Cache key cần phản ánh Java version trong trường hợp nào?
15. Làm thế nào phân biệt lỗi sản phẩm với lỗi runner/toolchain?
16. Một thư viện Java cần những kiểm chứng nào trước khi tuyên bố hỗ trợ JDK mới?
17. Khi ngừng hỗ trợ một JDK, cần cập nhật những phần nào?

Ma trận phiên bản Java là cách biến cam kết tương thích thành các kiểm chứng có thể quan sát trong CI. Hãy xác định rõ phiên bản được hỗ trợ, phân biệt compiler với runtime, đặt điều kiện thất bại theo mức độ cam kết và chọn phạm vi test theo rủi ro. Khi artifact được tạo và publish một lần sau các required checks, pipeline sẽ cho biết chính xác phiên bản nào đã được kiểm chứng và binary nào đã được phát hành.

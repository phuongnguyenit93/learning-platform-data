# Cache dependency trong CI/CD

## 1. Dependency cache là gì?

**Dependency cache** là vùng lưu trữ tạm các package, thư viện, metadata và file phân phối mà build tool đã tải hoặc xử lý. Pipeline khôi phục cache ở lần chạy sau để giảm thời gian tải dependency từ Maven Central, Gradle Plugin Portal, npm registry hoặc repository nội bộ.

Ví dụ trong dự án Java:

- Maven lưu dependency và plugin đã tải trong local repository, mặc định `~/.m2/repository`.
- Gradle lưu artifact và metadata trong Gradle User Home, thường là `~/.gradle/caches`.
- Maven Wrapper và Gradle Wrapper tải bản phân phối build tool vào thư mục wrapper riêng.
- npm lưu package metadata và tarball trong cache, mặc định `~/.npm` trên Linux/macOS.

Cache hữu ích trên CI runner dùng một lần (ephemeral runner), nơi mỗi job bắt đầu trong môi trường sạch. Không có cache, mỗi build có thể phải tải lại hàng trăm dependency và plugin.

Cache là tối ưu hiệu năng, không phải điều kiện để build chạy đúng. Pipeline phải build được khi cache miss, cache bị xóa hoặc cache service tạm thời không khả dụng.

## 2. Cache hoạt động trong pipeline như thế nào?

Một pipeline có dependency cache thường đi qua chu trình:

1. Checkout source code và lockfile.
2. Thiết lập JDK, build tool và môi trường.
3. Tạo cache key từ hệ điều hành, kiến trúc, build tool và file khai báo dependency.
4. CI tìm cache phù hợp và khôi phục các đường dẫn đã cấu hình.
5. Maven/Gradle/npm kiểm tra cache nội bộ, chỉ tải thành phần còn thiếu hoặc cần cập nhật.
6. Job compile, test và package như bình thường.
7. Khi job hoàn tất theo chính sách CI, cache được lưu lại để lần chạy sau sử dụng.

**Cache hit** nghĩa là tìm được cache phù hợp. **Cache miss** nghĩa là không tìm được cache phù hợp; build tool sẽ tải dependency từ repository và CI có thể lưu cache mới sau khi job thành công.

Cache miss là trạng thái bình thường, không phải lỗi build. Build phải dựng lại được môi trường từ source và lockfile.

## 3. Phân biệt dependency cache, build cache và artifact

| Loại | Nội dung | Mục đích |
|---|---|---|
| Dependency cache | JAR, POM, package tarball, metadata đã tải | Tránh tải dependency nhiều lần |
| Build cache | Kết quả task đã tính toán, ví dụ output compile hoặc transform | Tránh chạy lại task khi input không đổi |
| Artifact | JAR/WAR, test report, coverage report, log do job tạo ra | Lưu kết quả của lần chạy hoặc chuyển dữ liệu giữa job |

`~/.m2/repository` là dependency cache của Maven. `target/app.jar` được tạo từ job là artifact. Gradle build cache lưu output task và có thể tái sử dụng kết quả compile; nó khác dependency cache.

Trong GitLab CI, dùng `cache` cho dependency được tải từ Internet và `artifacts` để chuyển file build/test report giữa các stage. Trong GitHub Actions cũng có sự phân biệt tương tự giữa cache và workflow artifact.

Không dùng cache làm nơi lưu bản phát hành duy nhất. Cache có thể hết hạn, bị eviction hoặc không được khôi phục ở lần chạy tiếp theo.

## 4. Cache path và file tạo key

| Công cụ | Cache path phổ biến | File nên tính vào cache key |
|---|---|---|
| Maven | `~/.m2/repository` | `pom.xml`, POM module, Maven Wrapper properties, extensions |
| Gradle | `~/.gradle/caches` | `build.gradle`, `build.gradle.kts`, `gradle.properties`, wrapper properties, version catalog, `gradle.lockfile` |
| Maven Wrapper | `~/.m2/wrapper/dists` | `.mvn/wrapper/maven-wrapper.properties` |
| Gradle Wrapper | `~/.gradle/wrapper` | `gradle/wrapper/gradle-wrapper.properties` |
| npm | `~/.npm` | `package-lock.json` hoặc `npm-shrinkwrap.json` |
| Yarn | cache của Yarn hoặc offline mirror | `yarn.lock` |

Đường dẫn thực tế phụ thuộc OS, user home và cấu hình runner. Có thể kiểm tra bằng `mvn help:evaluate`, `gradle properties` hoặc `npm config get cache`.

Không cache toàn bộ thư mục home một cách tùy tiện. Chỉ đưa các thư mục cần thiết vào cache để tránh lưu nhầm credential, log, file tạm hoặc dữ liệu của job khác.

## 5. Thiết kế cache key

Cache key quyết định lúc nào một cache có thể được tái sử dụng. Một key tốt thay đổi khi dependency hoặc môi trường khiến cache không còn tương thích.

Cấu trúc thường dùng:

~~~text
<schema>-<os>-<arch>-<build-tool>-<tool-version>-<dependency-hash>
~~~

Các thành phần:

- **Schema/version:** chủ động bỏ cache cũ khi thay đổi cách lưu hoặc định dạng.
- **OS và architecture:** cần thiết khi package chứa native binary khác nhau theo nền tảng.
- **Build tool/version:** tránh dùng metadata cache không tương thích giữa các phiên bản tool.
- **Dependency hash:** hash lockfile hoặc file khai báo dependency để tạo cache mới khi dependency thay đổi.

Ví dụ key thủ công cho Maven trên GitHub Actions:

~~~yaml
key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml', '.mvn/wrapper/maven-wrapper.properties') }}
~~~

Không dùng một key cố định cho mọi commit và mọi nhánh nếu dependency có thể thay đổi. Với monorepo, phải đưa mọi file ảnh hưởng đến dependency resolution của module vào key. Chỉ hash POM gốc là chưa đủ nếu POM con có thể thay đổi dependency độc lập.

## 6. Lockfile và tính tái lập của build

Cache và lockfile giải quyết hai vấn đề khác nhau:

- Cache giảm thời gian tải và phân giải dependency.
- Lockfile hoặc dependency locking cố định phiên bản dependency được sử dụng.

Nếu chỉ dùng cache mà không khóa dependency, build có thể nhận version mới từ version range, dynamic version hoặc SNAPSHOT sau khi metadata hết hạn.

- Maven: khai báo version rõ ràng trong `pom.xml`, dùng `dependencyManagement` để quản lý version tập trung; tránh version range trong release build.
- Gradle: dùng dependency locking và commit `gradle.lockfile` hoặc các lockfile trong `gradle/dependency-locks/`.
- npm: commit `package-lock.json` và dùng `npm ci` trong CI.

Gradle hỗ trợ tạo lock state bằng:

~~~bash
./gradlew dependencies --write-locks
~~~

Có thể bật dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Lockfile phải được review như source code. Khi nâng cấp dependency, kiểm tra diff để biết thư viện nào đổi và dependency bắc cầu nào bị ảnh hưởng.

## 7. Maven dependency cache

Maven lưu artifact đã tải trong local repository, mặc định:

~~~text
~/.m2/repository
~~~

Local repository có thể chứa JAR, POM, metadata, Maven plugin và dependency của plugin. Maven cho phép đổi local repository bằng settings hoặc system property:

~~~bash
mvn -Dmaven.repo.local=.m2/repository verify
~~~

Trong CI, có thể đặt repository trong workspace để GitLab Runner lưu cache path:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" verify
~~~

Các lệnh hữu ích:

~~~bash
mvn -B -ntp dependency:go-offline
mvn -B -ntp verify
mvn -o -B -ntp verify
mvn -U -B -ntp verify
mvn dependency:tree
~~~

- `dependency:go-offline` tải trước dependency và plugin cần thiết.
- `verify` chạy các phase kiểm tra của Maven lifecycle.
- `-o` chạy offline, chỉ dùng dữ liệu đã có trong local repository.
- `-U` yêu cầu kiểm tra cập nhật đối với SNAPSHOT và artifact bị thiếu theo cơ chế Maven.
- `dependency:tree` hiển thị cây dependency đã resolve.

Offline mode xác nhận cache đã đủ cho một build cụ thể. Nếu thiếu plugin hoặc artifact, build báo lỗi; hãy chạy lại online để tải phần còn thiếu.

Không đưa `~/.m2/settings.xml` vào cache. File này có thể chứa username, password, server credential, private key hoặc mirror nội bộ.

## 8. Gradle dependency cache

Gradle User Home mặc định là `~/.gradle`. Dependency cache chủ yếu nằm dưới:

~~~text
~/.gradle/caches/modules-2
~~~

Gradle giữ hai loại dữ liệu chính:

- File store chứa artifact tải về, ví dụ JAR, POM và metadata file.
- Metadata store chứa kết quả resolve module, version động, artifact và repository đã cung cấp dữ liệu.

Gradle lưu artifact theo checksum và ghi nhận repository nguồn. Cùng một tọa độ dependency nhưng hai repository trả về binary khác nhau có thể được xử lý thành các artifact riêng. Cách lưu này giúp hạn chế ghi đè binary giữa các nguồn.

Các lệnh thường dùng:

~~~bash
./gradlew build
./gradlew --offline build
./gradlew --refresh-dependencies build
./gradlew dependencies
./gradlew dependencyInsight --dependency commons-lang3
~~~

- `--offline` chỉ dùng dependency đã có trong cache; thiếu artifact thì build thất bại.
- `--refresh-dependencies` yêu cầu Gradle kiểm tra lại metadata và artifact, nhưng không nhất thiết tải lại mọi file nếu checksum không đổi.
- `dependencyInsight` giải thích vì sao một version được chọn cho dependency cụ thể.

Gradle xử lý dynamic version và changing module, ví dụ SNAPSHOT, theo thời gian cache. Mặc định, kết quả resolve của các dependency loại này thường được cache trong 24 giờ. Khi dùng dependency thay đổi thường xuyên, cần hiểu rõ TTL và chính sách refresh.

Cache Gradle có file locking. Nhiều process chỉ truy cập đồng thời an toàn khi chúng có thể phối hợp qua cơ chế locking. Không mount một writable Gradle cache dùng chung giữa nhiều container độc lập đang build đồng thời; trong CI, ưu tiên khôi phục cache archive riêng cho từng job hoặc dùng cơ chế cache chuyên dụng được Gradle hỗ trợ.

## 9. npm cache trong pipeline JavaScript đi kèm

Một dự án Java có thể có frontend build chạy bằng npm. npm lưu cache content-addressable, mặc định trong `~/.npm`.

Trong CI, cache package download và vẫn cài lại dependency theo lockfile:

~~~bash
npm ci --cache .npm --prefer-offline
~~~

`npm ci` yêu cầu `package-lock.json` hoặc `npm-shrinkwrap.json` hiện có, kiểm tra sự khớp giữa lockfile và `package.json`, xóa `node_modules` đang có trước khi cài và không cập nhật lockfile.

Kiểm tra cache:

~~~bash
npm cache verify
~~~

npm tự kiểm tra integrity khi ghi và đọc cache. `npm cache clean --force` thường không cần dùng để sửa lỗi thông thường; trước tiên hãy dùng `npm cache verify` và đọc lỗi cụ thể.

Trong GitLab, cache npm theo lockfile bằng path trong workspace:

~~~yaml
cache:
  key:
    files:
      - package-lock.json
  paths:
    - .npm/
script:
  - npm ci --cache .npm --prefer-offline
~~~

Không cache `.npmrc` nếu file chứa registry token hoặc credential.

## 10. GitHub Actions: cache Maven với setup-java

`actions/setup-java` hỗ trợ cache dependency cho Maven, Gradle và sbt. Cấu hình `cache` giúp tránh tự viết đường dẫn cache và key thủ công.

Ví dụ workflow Maven:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '24'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            **/.mvn/wrapper/maven-wrapper.properties
            **/.mvn/extensions.xml
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Build and test
        run: mvn -B -ntp verify
~~~

Trong ví dụ:

- `cache: maven` bật dependency cache của Maven.
- `cache-dependency-path` chỉ ra các file dùng để tạo hash; hữu ích trong monorepo.
- `cache-read-only` cho phép pull request khôi phục cache mà không lưu thay đổi cache mới.
- `mvn -B -ntp verify` chạy Maven ở batch mode và hạn chế transfer progress output.

Setup Java quản lý cache dependency, Maven/Gradle Wrapper và JDK cache thành các entry riêng. Key nội bộ có thành phần OS, architecture, package manager và hash của file dependency. Với monorepo, hãy bảo đảm toàn bộ POM hoặc build file ảnh hưởng tới dependency đều được tính vào key.

Để cache Maven đầy đủ hơn, có thể chạy:

~~~bash
mvn -B -ntp dependency:go-offline dependency:resolve-plugins
~~~

Với Gradle, đổi `cache: maven` thành `cache: gradle` và chạy `./gradlew --no-daemon build`. Các file dùng để hash có thể gồm `**/*.gradle*`, `gradle.properties`, `gradle-wrapper.properties` và version catalog.

## 11. GitHub Actions: cache key thủ công và restore key

Khi cần kiểm soát cache path hoặc key riêng, có thể dùng action cache trực tiếp. Quy trình restore/save tách biệt giúp job chỉ đọc cache hoặc chỉ seed cache.

Ví dụ:

~~~yaml
- name: Restore Maven dependencies
  id: maven-cache
  uses: actions/cache/restore@v4
  with:
    path: ~/.m2/repository
    key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml') }}
    restore-keys: |
      maven-v2-${{ runner.os }}-${{ runner.arch }}-

- name: Build
  run: mvn -B -ntp verify

- name: Save Maven dependencies
  if: steps.maven-cache.outputs.cache-hit != 'true'
  uses: actions/cache/save@v4
  with:
    path: ~/.m2/repository
    key: maven-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('**/pom.xml') }}
~~~

`restore-keys` cho phép tìm cache có prefix phù hợp khi key chính không có exact match. GitHub chọn cache mới nhất khớp prefix. Cache được tạo bằng key mới sau khi job thành công; cache entry hiện có không thể sửa nội dung tại chỗ.

Dùng restore key theo thứ tự cụ thể đến rộng. Prefix quá rộng có thể khôi phục cache cũ không phù hợp và làm tăng thời gian kiểm tra lại. Package manager vẫn phải xác nhận dependency đúng với lockfile hoặc POM.

Nếu dùng `setup-java` đã bật cache, không cần thêm action cache cho cùng thư mục trừ khi có yêu cầu đặc biệt. Hai cơ chế ghi vào cùng path dễ làm pipeline khó hiểu và tốn thời gian nén/giải nén.

## 12. GitLab CI: cache Maven repository

GitLab Runner cache các đường dẫn phù hợp với workspace của project. Có thể đổi local Maven repository sang thư mục trong project:

~~~yaml
stages:
  - build

maven-build:
  image: maven:3.9.12-eclipse-temurin-24
  stage: build
  cache:
    key:
      files:
        - pom.xml
        - .mvn/wrapper/maven-wrapper.properties
    paths:
      - .m2/repository/
    policy: pull-push
  script:
    - mvn -B -ntp -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" verify
~~~

Key dựa trên nội dung POM và Maven Wrapper properties. Khi dependency hoặc wrapper thay đổi, GitLab tạo key mới. Với Maven multi-module, cần tính các POM module vào key; có thể tạo key từ hash của tất cả POM hoặc chiến lược riêng cho từng module.

`policy: pull-push` là mặc định: job tải cache lúc bắt đầu và upload thay đổi lúc kết thúc. Khi nhiều job song song dùng cùng cache, có thể dùng một job seed với `policy: push` và các job test chỉ dùng `policy: pull` để tránh nhiều job cùng upload.

## 13. GitLab CI: cache Gradle

Gradle User Home có thể đặt bên trong project để GitLab Runner cache được:

~~~yaml
variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle-user-home"

gradle-build:
  image: gradle:9.2.1-jdk24
  stage: build
  cache:
    key:
      files:
        - gradle/wrapper/gradle-wrapper.properties
        - gradle/libs.versions.toml
    paths:
      - .gradle-user-home/caches/modules-2/
      - .gradle-user-home/wrapper/dists/
    policy: pull-push
  script:
    - gradle --no-daemon build
~~~

Ví dụ này cache dependency metadata/artifact và Gradle Wrapper distribution. Nếu project không có version catalog, hãy thay file key bằng lockfile hoặc file build phù hợp.

GitLab `cache:key:files` hỗ trợ một số lượng file giới hạn trong mỗi key definition. Với monorepo có nhiều file build, tạo key từ manifest tổng hợp hoặc tách cache theo module thay vì bỏ sót file dependency.

Không đưa toàn bộ Gradle User Home vào cache nếu không cần. Tránh cache daemon state, log, credential và dữ liệu tạm. Với runner chạy container, mỗi job nên nhận bản cache riêng, không chia sẻ writable cache live giữa các process độc lập.

## 14. Cache trong monorepo và pipeline nhiều job

Monorepo có thể chứa nhiều ứng dụng Maven/Gradle, module frontend và nhiều lockfile. Nếu tất cả dùng chung một key rộng, một thay đổi nhỏ có thể làm mất cache của cả repo hoặc khiến module dùng nhầm cache.

Một số chiến lược:

- Key theo module: `backend-maven-<hash pom>`, `frontend-npm-<hash lockfile>`.
- Key tổng hợp: tính hash của toàn bộ POM, Gradle build file, version catalog và lockfile.
- Key theo platform: thêm OS/architecture khi dependency chứa native binary.
- Key theo toolchain: thêm Maven/Gradle major hoặc JDK major nếu cache phụ thuộc định dạng/tool version.
- Dùng một job seed cache và nhiều job read-only để giảm upload trùng lặp.

Với GitHub Actions matrix, một job có thể tải dependency trước và các job matrix dùng cache ở chế độ read-only. Cách này giúp giảm số lần ghi cache và tải repository.

Đối với Gradle, nếu cần cache output task giữa nhiều job hoặc runner, xem Gradle Build Cache/Develocity. Dependency cache chỉ xử lý dependency resolution; nó không tự chia sẻ kết quả compile/test của task.

## 15. Cache và bảo mật chuỗi cung ứng

Cache có thể trở thành đường truyền dữ liệu giữa workflow khác nhau. Một cache được tạo bởi job ít tin cậy có thể bị khôi phục bởi workflow có quyền cao hơn. Nếu cache chứa executable, script hoặc build output bị thay đổi, workflow sau có thể chạy mã không mong muốn.

Nguyên tắc bảo mật:

- Không cache secret, access token, signing key, private key hoặc file settings chứa password.
- Không đưa `.m2/settings.xml`, file `.npmrc` có token, `gradle.properties` chứa credential hoặc `.env` vào cache.
- Xem cache được chia sẻ giữa branch, pull request và workflow nào.
- Dùng cache read-only cho job từ pull request hoặc matrix consumer khi phù hợp.
- Để workflow đáng tin cậy trên default branch tạo/cập nhật cache dùng chung.
- Không bật chế độ ghi cache cho workflow xử lý source không tin cậy nếu cache đó sẽ được workflow có quyền cao khôi phục.
- Xem nội dung cache đã khôi phục là input cần được kiểm soát.
- Dùng lockfile, checksum và dependency verification để xác minh artifact.

GitHub giới hạn quyền cache theo branch/ref và một số loại trigger. Workflow ít tin cậy có thể bị giới hạn chỉ đọc cache của default branch. Không chủ động bật write mode cho `pull_request_target`, `issue_comment` hoặc `workflow_run` nếu chưa đánh giá nguy cơ cache poisoning.

Cache không thay thế việc xác minh dependency. Gradle có thể dùng `gradle/verification-metadata.xml` để xác minh checksum hoặc chữ ký artifact. Nên dùng SHA-256/SHA-512 và review nguồn checksum; checksum không rõ nguồn không tự chứng minh artifact đáng tin.

## 16. Cache dependency không đảm bảo build reproducible

Một build tái lập cần cùng source, dependency version, toolchain, cấu hình và môi trường để tạo kết quả nhất quán. Cache chỉ làm nhanh bước tải hoặc tái sử dụng dữ liệu.

Các thực hành hỗ trợ reproducible build:

- Commit lockfile và wrapper properties.
- Pin phiên bản JDK, Maven/Gradle và plugin.
- Tránh version range, dynamic version hoặc SNAPSHOT trong release pipeline nếu không có chính sách refresh rõ ràng.
- Dùng dependency verification hoặc checksum policy.
- Kiểm soát repository/mirror được phép dùng.
- Giữ build script và dependency declaration trong version control.
- Kiểm tra pipeline bằng một run không có cache định kỳ.
- Không để build thành công chỉ vì máy runner còn file chưa được khai báo trong source.

Cache hit không nên làm thay đổi tập dependency được resolve. Nếu clean runner build thất bại còn runner có cache lại thành công, đó là dấu hiệu build đang phụ thuộc vào state ngoài source.

## 17. Cache invalidation và dọn cache

Cache key thay đổi khi dependency hoặc môi trường thay đổi là cách invalidation thông thường. Có thể tăng schema version, ví dụ từ `maven-v2` sang `maven-v3`, khi thay đổi cache path, cách nén, tool version hoặc cấu trúc.

Khi cache không còn hợp lệ:

- Maven: dùng `-U` để kiểm tra SNAPSHOT và artifact cần cập nhật; chỉ xóa đúng artifact trong local repository nếu đã xác định file cache hỏng.
- Gradle: dùng `--refresh-dependencies` để kiểm tra lại metadata/artifact; cache tự quản lý và có cơ chế dọn các artifact cũ không dùng.
- npm: chạy `npm cache verify` trước khi cân nhắc dọn cache.
- GitHub Actions: tạo key mới khi cần cache entry mới; không thể sửa nội dung cache entry đã tồn tại.

Không xóa toàn bộ cache chỉ vì một build chậm. Trước tiên hãy xác định cache miss, key mismatch, repository chậm, metadata stale, credential hết hạn hay dependency chưa được warm.

Cache có giới hạn dung lượng và retention theo nền tảng. Không coi cache là dữ liệu bền vững; nếu bị eviction, pipeline phải có thể tải lại dependency.

## 18. Đo hiệu quả cache

Để biết cache có giúp ích hay không, đo trước và sau khi bật cache trong workload tương đương.

Các chỉ số hữu ích:

- Thời gian restore cache.
- Dung lượng cache được tải lên và tải xuống.
- Cache hit rate và miss rate.
- Thời gian dependency resolution.
- Tổng thời gian build/test.
- Network transfer và số request tới repository.
- Tỷ lệ job thất bại do cache hoặc repository.
- Dung lượng cache theo branch và theo thời gian.

Cache lớn không phải lúc nào cũng nhanh hơn. Nếu nén/giải nén 1 GB mất nhiều thời gian hơn tải dependency cần thiết, cache có thể làm pipeline chậm đi. Chọn path nhỏ và ổn định; bỏ bớt file tạm, daemon, log và dữ liệu có thể tái tạo nhanh.

Nên so sánh thời gian median và p95 qua nhiều lần chạy. Một cache hit duy nhất không đủ để kết luận pipeline đã nhanh hơn.

## 19. Troubleshooting

### Không có cache hit

Kiểm tra key có thay đổi không, file dependency có đúng path không, cache path có tồn tại lúc save không, OS/architecture có giống nhau không và cache có hết hạn/eviction không.

### Cache hit nhưng Maven vẫn tải dependency

Kiểm tra local repository path Maven đang dùng, profile/mirror, SNAPSHOT update policy, plugin dependency và credential của private repository. Cache được khôi phục vào một path nhưng Maven dùng path khác sẽ không giúp ích.

### Cache hit nhưng Gradle vẫn tải artifact

Kiểm tra Gradle User Home, Gradle wrapper version, repository URL/identity và changing dependency TTL. Gradle lưu metadata theo repository nên thay đổi repository có thể khiến cần resolve lại.

### Offline build thất bại

Cache chưa chứa toàn bộ artifact hoặc plugin cần thiết. Chạy build online để hoàn tất resolve; với Maven có thể chạy `dependency:go-offline` và `dependency:resolve-plugins`; với Gradle chạy task cần thiết trước khi kiểm tra offline.

### Cache bị stale

Dùng Maven `-U` cho snapshot/update check hoặc Gradle `--refresh-dependencies`. Kiểm tra xem lockfile có thay đổi không và cache key có tính file đó không.

### Cache tăng dung lượng quá nhanh

Thu hẹp path, tăng độ chính xác của key, bỏ log/daemon/build output không cần thiết và xem retention. Chỉ cache dependency cần tái sử dụng.

### Job song song ghi đè cache

Dùng một job seed/push và các job consumer/pull hoặc read-only. Tránh nhiều job đồng thời ghi vào một cache key chung khi nền tảng không bảo đảm kết quả mong muốn.

### Build thành công chỉ khi có cache

Kiểm tra source có thiếu dependency declaration, wrapper hoặc generated file không. Thực hiện clean build trên runner mới và xác nhận mọi dependency đều được khai báo, khóa và tải được.

## 20. Ví dụ Java hoàn chỉnh để kiểm tra Maven cache

Ví dụ dùng thư viện Apache Commons Lang để xác nhận dependency được tải và tái sử dụng.

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>dependency-cache-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.17.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tạo file `src/main/java/demo/CacheDemo.java`:

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class CacheDemo {
    public static void main(String[] args) {
        System.out.println("READY " + StringUtils.capitalize("dependency cache"));
    }
}
~~~

Chạy lần đầu online để tải dependency và plugin:

~~~bash
mvn -B -ntp verify
~~~

Chạy lại offline để xác nhận local repository đã có đủ thành phần:

~~~bash
mvn -o -B -ntp verify
~~~

Có thể compile trực tiếp với JDK 17+ sau khi dependency đã có trong local repository:

~~~bash
javac --release 17 -cp "$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar" -d target/classes src/main/java/demo/CacheDemo.java
~~~

Chạy class đã compile:

~~~bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar" demo.CacheDemo
~~~

Stdout chính xác:

~~~text
READY Dependency cache
~~~

Trong môi trường kiểm thử với Maven 3.9.12 và JDK 24.0.2, lần chạy online thành công; lần chạy offline trên cùng local repository cũng thành công. Thời gian verify offline của lần kiểm tra là 1.091 giây. Thời gian thực tế phụ thuộc runner, plugin và cache.

## 21. Ví dụ Gradle để kiểm tra dependency cache

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'dependency-cache-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

application {
    mainClass = 'demo.CacheDemo'
}
~~~

Dùng cùng file `CacheDemo.java` ở ví dụ Maven. Chạy online:

~~~bash
gradle run
~~~

Sau khi dependency đã được tải, chạy offline:

~~~bash
gradle --offline run
~~~

Stdout chính xác:

~~~text
READY Dependency cache
~~~

Trong kiểm thử với Gradle 9.2.1 và JDK 24.0.2, cả `gradle run` và `gradle --offline run` đều thành công và in cùng output. Build offline chỉ chạy được khi cache đã có tất cả dependency cần thiết.

Với dự án thật, commit Gradle Wrapper và dùng `./gradlew` để cố định phiên bản Gradle. Dependency cache sẽ được đặt trong Gradle User Home của runner.

## 22. Checklist triển khai dependency cache

- [ ] Xác định build tool và cache path thực tế trên runner.
- [ ] Cache dependency download thay vì cache mọi file trong workspace.
- [ ] Tạo key theo OS, architecture, build tool và lockfile/dependency file.
- [ ] Bao gồm POM module, Gradle version catalog, wrapper properties và lockfile có liên quan.
- [ ] Dùng versioned prefix để chủ động invalidation.
- [ ] Giữ lockfile và dependency version trong version control.
- [ ] Dùng Maven `-o`, Gradle `--offline` hoặc npm cache verification để kiểm tra cache.
- [ ] Dùng GitHub `setup-java` cache hoặc GitLab `cache:key:files` đúng với layout project.
- [ ] Dùng `pull`/read-only cho job tiêu thụ cache song song khi phù hợp.
- [ ] Không cache credentials, signing key, `.env` hoặc settings chứa secret.
- [ ] Xem cache được khôi phục là input cần kiểm soát và phòng cache poisoning.
- [ ] Phân biệt cache với artifact dùng để chuyển kết quả build giữa job.
- [ ] Đo restore time, cache hit rate, network và tổng thời gian pipeline.
- [ ] Chạy clean build không cache định kỳ để xác nhận build không phụ thuộc state cũ.
- [ ] Đảm bảo cache miss hoặc cache eviction không làm pipeline mất khả năng build.

## 23. Tài liệu tham khảo

- [GitHub Actions — Dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching): mục đích cache, artifact so với cache và cache security.
- [GitHub Actions — Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): cache key, restore key, cache hit/miss, branch scope và cache poisoning.
- [actions/setup-java](https://github.com/actions/setup-java): cấu hình Maven/Gradle cache, cache-dependency-path, wrapper cache và read-only cache.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): artifact/metadata cache, repository identity, checksum, changing dependencies, offline và refresh.
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum và signature verification cho dependency.
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html): local repository và user settings.
- [Apache Maven — Settings reference](https://maven.apache.org/ref/3.9.9/maven-settings/settings.html): localRepository, offline, mirror, proxy và server settings.
- [GitLab — Caching in CI/CD](https://docs.gitlab.com/ci/caching/): cache path, key strategy và cache so với artifact.
- [GitLab — CI/CD caching examples](https://docs.gitlab.com/ci/caching/examples/): cache key theo lockfile và ví dụ npm.
- [npm — npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/): clean install dựa trên lockfile cho CI.
- [npm — npm cache](https://docs.npmjs.com/cli/v11/commands/npm-cache/): content-addressable cache và npm cache verify.

Dependency cache giúp CI/CD giảm thời gian tải thư viện và plugin. Hiệu quả lâu dài đến từ cache key chính xác, lockfile ổn định, cache path nhỏ, quyền ghi có kiểm soát và một pipeline vẫn build thành công khi cache không tồn tại.

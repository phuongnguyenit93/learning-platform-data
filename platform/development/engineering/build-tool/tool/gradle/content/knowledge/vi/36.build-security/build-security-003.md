# Ngăn dependency confusion bằng repository policy và content filter

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** An toàn build

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **dependency confusion**, **repository shadowing**, **namespace/package squatting** và nguy cơ rò rỉ tên module nội bộ ra public repositories.
2. Hiểu cách Gradle tra cứu **group:artifact:version (GAV)** theo thứ tự repositories, chọn metadata/artifact từ nguồn nào và vì sao thứ tự khai báo không phải một biện pháp bảo vệ đủ mạnh.
3. Phân biệt **repositories của project dependencies**, **pluginManagement repositories**, **buildscript classpath repositories**, **publishing repositories** và repositories của **included builds**.
4. Dùng **dependencyResolutionManagement** trong settings.gradle để tập trung repository declarations; so sánh **PREFER_PROJECT**, **PREFER_SETTINGS** và **FAIL_ON_PROJECT_REPOS**.
5. Dùng **content { includeGroup, includeGroupByRegex, includeModule, excludeGroup, excludeModule }** đúng phạm vi và hiểu vì sao filter include trên một repository **không cấm** repository khác cung cấp cùng namespace.
6. Dùng **exclusiveContent { forRepository {...}; filter {...} }** để giữ một internal group độc quyền ở một trusted repository, không fallback sang repository kém tin cậy.
7. Tạo **bài lab Gradle Groovy DSL + Java 17** với hai Maven repositories cục bộ có cùng GAV nhưng JAR trả kết quả khác nhau; kiểm chứng sự khác biệt giữa cấu hình thiếu bảo vệ và cấu hình an toàn mà không tải hay thực thi mã độc thật.
8. Phân biệt **mavenLocal()**, Maven Central, artifact proxy, private Maven registry và remote plugin repository về độ tin cậy; tránh làm Gradle vô tình lấy local/public artifact thay internal release.
9. Hiểu **repository stickiness** trong Gradle dependency cache và vì sao đổi thứ tự repositories không luôn lập tức đổi artifact đã resolve; biết thiết kế thí nghiệm sạch với Gradle User Home riêng.
10. Bổ sung **dependency locking**, **dependency verification (SHA-256/PGP)**, fixed versions, HTTPS, credential management, quyền publish và kiểm soát CI nhằm bảo vệ nhiều lớp.
11. Biết repository filter **không phải** dependency vulnerability scanner, không kiểm tra toàn vẹn bytes và không ngăn một người có quyền publish vào trusted repository đưa artifact sai.
12. Lập runbook khi private repository bị lỗi/missing artifact: **fail closed**, không tự fallback sang public repository có GAV trùng.
13. Chẩn đoán các lỗi: module not found, wrong group regex, plugin marker không resolve, project repository bị chặn, transitive dependencies thiếu repo, cached artifact cũ, verification mismatch và dependency locking conflict.
14. Thiết kế checklist và bài kiểm thử CI chứng minh nhóm nội bộ không thể được tải từ public repositories trong **đúng từng resolution scope**.

**Nguyên tắc trung tâm:** Mỗi **namespace nội bộ** phải có **nguồn cung được phép rõ ràng**. Chỉ khai báo trusted repository trước public repository không đủ: thứ tự và trạng thái cache có thể thay đổi, còn internal artifact tạm thời không có ở trusted repo có thể bị truy vấn ở public. Hãy khóa nguồn theo **repository content policy**, tốt nhất dùng **exclusive content** khi ownership thật sự độc quyền; tập trung policy ở settings, kiểm tra plugin/buildscript scopes riêng và kết hợp verification/locking để có defense in depth.

## 1. Dependency confusion là gì?

Một dependency Maven/Gradle thường được yêu cầu bằng tọa độ:

~~~text
group:artifact:version

com.acme.internal:auth-client:2.4.0
~~~

Tọa độ đó **không tự kèm theo chứng chỉ** chứng minh ai sở hữu namespace. Nếu build có nhiều repositories, một nguồn kém tin cậy có thể cũng chứa module mang đúng GAV, hoặc một tên trông giống GAV chuẩn. Kịch bản:

1. Tổ chức có thư viện riêng **com.acme.internal:auth-client:2.4.0** trong private Maven registry.
2. Build vô tình dùng public repository song song với private registry mà không lọc namespace.
3. Tên internal artifact bị lộ qua logs/CI, tài liệu, metadata hoặc những truy vấn tới public repository.
4. Một nguồn không được ủy quyền cung cấp artifact với cùng coordinates, hoặc một version dùng trong dynamic selection.
5. Khi lookup/routing sai, Gradle có thể resolve nhầm metadata/JAR, làm build sử dụng nội dung không đáng tin.

**Repository shadowing** là tình huống một source không mong muốn cung cấp cùng module coordinates và chiếm precedence. **Name/package squatting** còn có biến thể cố tạo namespace gần giống tên hợp lệ để đánh lừa người khai báo dependencies. **Version confusion** có thể xảy ra khi dynamic selector mở rộng tập candidate versions.

Trong bài học này, “artifact không tin cậy” chỉ là **JAR vô hại in chuỗi SHADOW_PUBLIC**, dùng để chứng minh nguy cơ lựa chọn sai nguồn. Không dùng payload gây hại hoặc artifact từ nguồn công cộng thật.

### 1.1. Ba tài sản cần bảo vệ

| Tài sản | Nguy cơ | Phản ứng đúng |
|---|---|---|
| **Tên private GAV** | Public repo nhận được truy vấn tên module nội bộ | Filter để Gradle không hỏi public repo về group nội bộ |
| **Artifact bytes** | Nhận JAR sai dù GAV đúng | Exclusive source, verification SHA-256/PGP, trusted publishing |
| **Dependency graph** | Version/plugin/metadata sai hoặc transitive dependency bị điều hướng | Pinned versions/locking, review changes, repository policy ở mọi scope |

**Không xem một gói từ private repository mặc định an toàn tuyệt đối.** Nếu credentials bị lộ hoặc registry bị xâm nhập, content filter vẫn dẫn bạn tới chính nguồn đã bị xâm phạm. Vì vậy phải dùng nhiều lớp kiểm soát.

### 1.2. Điều gì làm dependency confusion khác lỗ hổng thư viện?

- Dependency confusion: **mình đã tải đúng package/nguồn chưa?**
- Integrity/provenance verification: **bytes và chữ ký có khớp bản được tin cậy không?**
- Vulnerability scanning: **thư viện đúng tác giả đó có CVE hoặc nguy cơ đã biết không?**
- License/compliance: **có được phép phân phối/sử dụng thư viện không?**

Một JAR có SHA-256 đúng với artifact đã whitelist vẫn có thể chứa CVE. Một JAR không có CVE được công bố vẫn có thể đến sai nguồn. Repository policy giải quyết câu hỏi **routing và ownership**, không thay các cơ chế khác.

## 2. Gradle tìm dependency trong repositories như thế nào?

Ví dụ:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.internal.example.invalid/releases')
    }
    mavenCentral()
}
~~~

Khi Gradle cần module version cố định, nó lần lượt kiểm tra repositories được phép. Nếu tìm thấy module metadata ở repository đầu, Gradle thường dùng repository đó làm nguồn cho artifacts thuộc module, thay vì chọn JAR tuỳ ý ở repo tiếp theo. Thứ tự repositories **có tác động đến kết quả**.

Với dynamic versions, Gradle có thể cần khảo sát metadata các versions từ nhiều repositories trước khi quyết định version, nên không được suy luận thuật toán luôn dừng ở lần tìm thấy artifact đầu tiên trong mọi chế độ.

**Quan trọng:** Nếu trusted repo không chứa GAV được yêu cầu, source khác không bị filter vẫn có thể được hỏi. Đây chính là lý do **“internal repo trước Maven Central” không phải hàng rào an toàn đủ mạnh**.

### 2.1. Một sơ đồ lỗi policy

~~~text
Dependency request:
    com.acme.internal:auth-client:2.4.0
                |
                v
  PRIVATE REPO (đặt đầu)
          module missing
                |
                v
  PUBLIC REPO (không filter)
          same GAV exists
                |
                v
  Artifact được chọn từ PUBLIC  ← dependency confusion
~~~

Nếu public repository đứng trước private và chứa GAV, shadowing còn dễ hình dung hơn. Nhưng đổi thứ tự chỉ giảm một số tình huống, không sửa gốc rễ.

### 2.2. Thứ tự không đồng nghĩa version ưu tiên tuyệt đối

Một quy tắc sai là “Gradle luôn chọn version cao nhất ở mọi repository” hoặc “Gradle sẽ chuyển repo nếu JAR thiếu sau khi đã tìm thấy POM”. Với version cố định có metadata, Gradle gắn source repository; artifact được lấy từ nguồn đã cung cấp metadata. Dynamic version selectors, repository metadata và dependency conflict selection là các bước bổ sung với quy tắc riêng.

**Không dùng resolutionStrategy.force để sửa sai repository routing**. Force có thể khóa version, nhưng không bảo đảm GAV/version được lấy từ trusted repository.

### 2.3. Dependency cache có ghi nhớ nguồn

Gradle lưu metadata/cache của modules **theo repository origin**. Khi một artifact đã được resolve từ một repository, Gradle có cơ chế **repository stickiness** nhằm hạn chế đổi nguồn ngoài ý muốn.

Hệ quả:
- Vừa sửa settings.gradle nhưng Gradle vẫn báo/hiển thị trạng thái cũ có thể do cache.
- Dùng **--refresh-dependencies** hỗ trợ refresh metadata nhưng không phải “công tắc bỏ mọi repository provenance”.
- Để kiểm chứng chính sách trong lab, nên dùng **hai Gradle User Home riêng** hoặc môi trường clean, rồi quan sát artifact thực.
- Không xóa toàn bộ ~/.gradle của máy đang làm việc như một phương án mặc định.

**Thay đổi repository policy là một thay đổi supply-chain**, cần được review và kiểm thử trong clean CI environment.

## 3. Repository scopes: một policy không bao phủ mọi nơi

Gradle dùng những nơi khai báo repositories khác nhau:

| Scope | Cách khai báo | Được dùng để tìm |
|---|---|---|
| **Project dependencies** | dependencyResolutionManagement.repositories trong settings hoặc repositories trong build.gradle | Các dependencies ở implementation/api/runtimeOnly/testImplementation... |
| **Plugin DSL** | pluginManagement.repositories trong settings | Plugin markers và plugin implementation dependencies trong plugin resolution |
| **Legacy buildscript classpath** | buildscript { repositories {...} dependencies { classpath ... } } | Buildscript/plugin classpath legacy |
| **Publishing destination** | publishing { repositories {...} } | Nơi **upload** artifacts, không phải nơi resolve consumer dependencies |
| **Included build** | settings.gradle của build đó | Dependencies/plugins thuộc included build theo cấu trúc riêng |
| **Init scripts / enterprise policy** | Gradle initialization/enterprise configuration | Có thể thêm repositories hoặc thay build behavior theo quy tắc riêng |

**Sai lầm nguy hiểm:** Tạo content filter ở dependencyResolutionManagement rồi tuyên bố mọi plugin classpath và buildSrc/included builds đã an toàn. Plugin management là **resolution scope riêng**; buildscript repositories và các build khác cũng cần audit theo Gradle version và cấu hình tổ chức.

### 3.1. Repository được khai báo trong build.gradle có thể vượt policy

Mặc định, Gradle 9.9 dùng repository mode **PREFER_PROJECT**: repositories ở project có thể ghi đè ưu tiên repository policy đặt trong settings. Một developer hoặc third-party plugin có thể khai báo thêm nguồn mà người review settings chưa nhìn thấy.

Để có quyền kiểm soát rõ, **tập trung repository policy tại settings.gradle** và chọn mode thích hợp.

## 4. Central repository policy bằng dependencyResolutionManagement

**settings.gradle** (Groovy DSL) có thể khai báo:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}
~~~

Trong production, mavenCentral() chỉ là ví dụ public source. Nếu có internal namespaces, phải bổ sung trusted repo và content rules trước khi coi policy an toàn.

### 4.1. Ba chế độ repository management

| Mode | Hành vi | Phù hợp |
|---|---|---|
| **PREFER_PROJECT** | Mặc định: project repositories ưu tiên; settings policy có thể bị override | Legacy builds hoặc project cần repositories riêng, nhưng ít phù hợp kiểm soát tập trung |
| **PREFER_SETTINGS** | Settings repositories ưu tiên; nếu project/plugin khai báo repo khác, Gradle cảnh báo | Giai đoạn migration ít gây vỡ build hơn |
| **FAIL_ON_PROJECT_REPOS** | Repository khai báo ở project hoặc bởi project plugin gây lỗi cấu hình | Policy enforce chặt cho multi-project build |

**Khuyến nghị với build nội bộ đã kiểm soát được:** **FAIL_ON_PROJECT_REPOS** và một danh sách sources/filters đã được review. Dùng PREFER_SETTINGS làm bước chuyển tiếp nếu phải quan sát những plugin đang tự thêm repositories trước khi sửa.

### 4.2. Tại sao fail là tốt hơn silent override?

Nếu ai đó thêm:

~~~groovy
// consumer/build.gradle — sai khi settings đã enforce repositories.
repositories {
    mavenCentral()
}
~~~

và settings đang FAIL_ON_PROJECT_REPOS, Gradle sẽ báo lỗi về repository được thêm từ project. Đó là **tín hiệu policy hoạt động**, không phải lý do để tắt mode ngay.

Nếu một plugin bên thứ ba tự inject Maven repository, cần:
- Nâng cấp/sửa plugin hoặc loại repo injection.
- Đưa source hợp lệ vào settings policy.
- Kiểm tra plugin có cấu hình private/public routing cần thiết không.
- Không thay FAIL_ON_PROJECT_REPOS thành PREFER_PROJECT chỉ để build xanh mà bỏ qua kiểm soát.

### 4.3. Mode này không tự whitelist namespaces

**FAIL_ON_PROJECT_REPOS chặn project tự thêm repositories**; nó không phân chia namespace nào được dùng ở repo nào nếu settings.repositories vẫn chứa public và private mà không filter. Cần cả **centralization** lẫn **content policy**.

## 5. content filter: kiểm soát repository được hỏi

Gradle cho phép một **repository-local content filter**:

~~~groovy
repositories {
    maven {
        url = uri('https://packages.example.invalid/maven')

        content {
            includeGroup('com.acme.internal')
        }
    }

    mavenCentral()
}
~~~

Ý nghĩa:
- Repository packages.example.invalid **chỉ được Gradle hỏi** khi module thuộc group com.acme.internal (bỏ qua những groups khác).
- **Không có nghĩa Maven Central bị cấm cung cấp com.acme.internal**.
- Nếu internal repo không có module, Maven Central vẫn có thể được tra cứu vì không có exclusivity.
- Filter chỉ áp cho chính repository nó nằm trong.

Đây là khác biệt quan trọng nhất của bài.

### 5.1. includeGroup và includeGroupByRegex

~~~groovy
content {
    // Chỉ group đúng 100%, không tự gồm subgroups.
    includeGroup('com.acme.internal')
}
~~~

Nếu dùng nhiều groups:

~~~groovy
content {
    includeGroup('com.acme.internal')
    includeGroup('com.acme.platform')
}
~~~

Khi cần nhóm phân cấp có chuẩn naming rõ:

~~~groovy
content {
    includeGroupByRegex('com\\.acme\\.internal(\\..+)?')
}
~~~

Regex trên gồm **com.acme.internal** và những groups bắt đầu bằng **com.acme.internal.** theo cấu trúc phân đoạn. Đừng dùng regex quá rộng như **com\\.acme\\..*** nếu chỉ một số namespace thực sự do tổ chức sở hữu. **includeGroup** so khớp chính xác group; group Maven không có quan hệ cha-con được ngầm thừa kế.

### 5.2. includeModule và excludeModule

Nếu chỉ muốn một artifact cụ thể:

~~~groovy
content {
    includeModule('com.acme.internal', 'auth-client')
}
~~~

Ngược lại, public repository có thể được cấu hình:

~~~groovy
mavenCentral {
    content {
        excludeGroup('com.acme.internal')
        excludeModule('com.acme.legacy', 'unsafe-module')
    }
}
~~~

Ví dụ Maven Central ở trên là một **snippet minh họa** thuộc repositories block; cú pháp đầy đủ:

~~~groovy
repositories {
    mavenCentral {
        content {
            excludeGroup('com.acme.internal')
        }
    }
}
~~~

**Đừng dựa vào một blacklist không được cập nhật.** Nếu tổ chức còn group **com.acme.security**, **com.acme.build** hoặc nhiều private namespaces khác, rule chỉ exclude một group sẽ không bảo vệ tất cả.

### 5.3. Include vs exclude: tác động lên nhóm transitive

Một module internal có thể phụ thuộc:

~~~text
com.acme.internal:auth-client:2.4.0
  └── org.slf4j:slf4j-api:2.0.x
~~~

Filter internal repository chỉ cho com.acme.internal **không tự loại bỏ transitive org.slf4j**. Gradle vẫn cần repository public hoặc trusted proxy cho org.slf4j. Repository policy phải cho phép từng namespace của toàn dependency graph ở một source phù hợp.

Nếu bạn accidentally include **mọi dependency chỉ ở internal repository**, quá trình resolve transitive public libs có thể fail. Nguyên tắc là **routing theo ownership**, không phải cấm tất cả external modules.

## 6. exclusiveContent: bảo vệ namespace độc quyền

Gradle cung cấp **exclusiveContent** để nói rõ một nhóm chỉ được resolve từ repository được chỉ định **trong cùng RepositoryHandler**.

Ví dụ:

~~~groovy
repositories {
    mavenCentral()

    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://packages.example.invalid/internal')
            }
        }
        filter {
            includeGroup('com.acme.internal')
        }
    }
}
~~~

**Hiệu ứng:** Group com.acme.internal được dành độc quyền cho private repository đã khai báo trong forRepository. Gradle tự áp loại trừ tương ứng khỏi các repository khác trong cùng handler. Nếu private repository không có một internal module, Gradle phải **báo không resolve được**, thay vì âm thầm dùng module trùng tọa độ từ Maven Central.

**Đây là fail closed** — hành vi đúng đối với một namespace có owner được xác nhận.

### 6.1. includeGroup chỉ có một chiều, exclusiveContent có hai chiều

~~~text
content { includeGroup('com.acme.internal') } trên PRIVATE:
  PRIVATE: com.acme.internal được phép
  PUBLIC : com.acme.internal vẫn có thể được phép
  => CÓ THỂ fallback/sai nguồn

exclusiveContent { forRepository PRIVATE; includeGroup(...) }:
  PRIVATE: com.acme.internal được phép
  PUBLIC : com.acme.internal bị loại trừ trong cùng scope
  => Không fallback sang PUBLIC cho internal group
~~~

Nếu một build thiếu exclusiveContent nhưng áp đồng bộ:
- Private repo includeGroup(com.acme.internal).
- **Mọi** public repo excludeGroup(com.acme.internal).

thì kết quả routing vẫn có thể đúng. Tuy nhiên exclusiveContent biểu diễn **quy tắc ownership ở một chỗ**, giảm rủi ro thêm repository mới mà quên exclude. Trong Gradle user guide, exclusive content filtering được khuyến nghị như best practice.

### 6.2. Nhiều private repositories cùng sở hữu một namespace

Nếu thật sự có release và snapshot repositories cùng thuộc **một trust boundary**, có thể cần khai báo cả hai là allowed sources trong một exclusive group, kèm Maven content rules để phân biệt releases/snapshots. **Đừng chỉ độc quyền ở một repository rồi kỳ vọng release từ repository còn lại vẫn resolve.**

Khuyến nghị về architecture:
- Dùng một vetted internal Maven proxy/virtual repository nếu có thể.
- Hoặc explicit authorized repositories trong exclusive content policy.
- Có quyền publish và ACL tách biệt giữa snapshots/releases.
- Test những dependencies thực sự được resolve, kể cả parents và transitive metadata.

### 6.3. Caveat: pluginManagement exclusiveContent

Tài liệu Gradle cảnh báo: Khi dùng **exclusive content filtering trong pluginManagement.repositories** của settings.gradle, việc thêm repositories sau đó trong project **buildscript.repositories** có thể trở thành bất hợp lệ và làm build fail.

Điều này cần được kế hoạch hóa khi migrate plugins legacy dùng buildscript classpath. Đừng copy block exclusiveContent từ dependencyResolutionManagement sang pluginManagement mà không kiểm tra các legacy buildscript.repositories và Gradle version thực tế.

### 6.4. Không có exclusivity xuyên mọi build tree

Một exclusiveContent block **không tự áp toàn hệ thống**:
- dependencyResolutionManagement.repositories: project dependency resolution scope.
- pluginManagement.repositories: plugin DSL resolution scope.
- buildscript.repositories: khác.
- Included build: có settings và policy riêng.
- Maven Local, nếu được đưa vào một scope khác, vẫn là nguồn cần review.
- Publishing destinations: thuộc loại hoạt động khác.

**Kiểm thử source ownership trong từng scope**, không suy luận từ một settings block đã secure.

## 7. Bài lab không mạng: hai Maven repositories cùng GAV

Bài lab dùng **Java 17 + Gradle Groovy DSL** và hai Maven repositories trên filesystem:
- **repos/trusted-internal** là nguồn nội bộ được cho phép.
- **repos/public-simulated** đóng vai nguồn public kém tin cậy.
- Cả hai chứa cùng GAV **com.example.internal:greeting-api:1.0.0**.
- JAR từ trusted in **TRUSTED_INTERNAL**.
- JAR từ simulated public in **SHADOW_PUBLIC**.
- Bản “shadow” không làm gì ngoài trả một chuỗi, hoàn toàn không có mã độc.

Dùng **repoMode=unsafe** cho cấu hình **cố ý không an toàn** và **repoMode=safe** cho policy có content filters/exclusiveContent. **Chỉ dùng unsafe trong lab này**, không vận hành policy đó trong project thật.

### 7.1. Yêu cầu và cấu trúc

Cần:
- JDK 17 (có javac và JavaCompiler API).
- Gradle Wrapper phù hợp Java 17 (ví dụ Gradle 9.x) hoặc Gradle đã cài để tạo Wrapper.
- Không cần Maven Central hay internet cho artifact resolution của bài lab sau khi Wrapper có sẵn.
- Không cần private credentials hoặc external servers.
- Bash/Git Bash/WSL cho lệnh Linux/macOS; có lệnh PowerShell tương ứng.

~~~text
repository-defense-lab/
├── settings.gradle
├── gradlew                    # nếu có Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── consumer/
│   ├── build.gradle
│   └── src/main/java/demo/consumer/Main.java
├── tools/
│   └── SeedRepositories.java
└── repos/                     # sẽ được Java seed tool tạo
    ├── trusted-internal/
    │   └── com/example/internal/greeting-api/1.0.0/
    │       ├── greeting-api-1.0.0.pom
    │       └── greeting-api-1.0.0.jar
    └── public-simulated/
        └── com/example/internal/greeting-api/1.0.0/
            ├── greeting-api-1.0.0.pom
            └── greeting-api-1.0.0.jar
~~~

**Tệp repos/** được tạo ở bước sau. Không cần download dependency hoặc push artifact thật lên Maven Central. Tên GAV **com.example.internal** chỉ tồn tại trong bài lab này.

### 7.2. settings.gradle — repository policy điều khiển bằng -P

**settings.gradle** (Groovy DSL):

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'repository-defense-lab'
include 'consumer'

// Chỉ dùng repoMode=unsafe để chứng minh nguy cơ trong lab.
def mode = gradle.startParameter.projectProperties.get('repoMode') ?: 'safe'

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        if (mode == 'unsafe') {
            // Sai có chủ ý: source shadow đứng trước trusted.
            maven {
                name = 'SimulatedPublic'
                url = uri(new File(settingsDir, 'repos/public-simulated'))
            }
            maven {
                name = 'TrustedInternal'
                url = uri(new File(settingsDir, 'repos/trusted-internal'))
            }
        } else if (mode == 'safe') {
            maven {
                name = 'SimulatedPublic'
                url = uri(new File(settingsDir, 'repos/public-simulated'))

                // Defense in depth; exclusiveContent bên dưới
                // cũng tự exclude group này ở repositories khác.
                content {
                    excludeGroup('com.example.internal')
                }
            }

            exclusiveContent {
                forRepository {
                    maven {
                        name = 'TrustedInternal'
                        url = uri(new File(
                            settingsDir, 'repos/trusted-internal'
                        ))
                    }
                }
                filter {
                    includeGroup('com.example.internal')
                }
            }
        } else {
            throw new GradleException(
                'repoMode must be safe or unsafe'
            )
        }
    }
}
~~~

**Giải thích từng phần:**
1. **-PrepoMode=...** được đọc ở settings qua Gradle start parameters. Trong ví dụ khác, Gradle property Provider cũng có thể được sử dụng nếu scope hỗ trợ; ở đây một mode cố định dễ quan sát.
2. **FAIL_ON_PROJECT_REPOS** bảo đảm consumer không thêm repo riêng sau đó.
3. Nhánh unsafe **cố ý** cho public-simulated đứng trước. Hai repositories đều có cùng module metadata, Gradle sẽ ưu tiên nguồn đầu.
4. Nhánh safe loại private group khỏi public và dành private group độc quyền cho TrustedInternal.
5. **settingsDir** dùng đường dẫn cục bộ tới nơi chứa repositories; không dùng HTTP và không truyền secrets.
6. Cùng GAV/version trong hai sources nhưng **repository ownership** mới là điểm phân biệt.
7. Không có pluginManagement vì consumer chỉ áp **application** là Gradle core plugin; trong production cần audit plugin DSL riêng.

**Lưu ý:** Đây là một lab điều khiển mode bằng -P nhằm mô phỏng lỗi. Trong production, **không nên để policy bảo mật được tắt bằng cờ -P tùy ý**; dùng settings policy cố định, reviewed và được bảo vệ bằng quyền sửa repo/CI.

### 7.3. consumer/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.consumer.Main'
}

dependencies {
    implementation 'com.example.internal:greeting-api:1.0.0'
}
~~~

**Không có repositories block** trong consumer. Gradle lấy sources từ policy trong settings.gradle. Nếu đặt repositories { mavenCentral() } ở đây, **FAIL_ON_PROJECT_REPOS** sẽ từ chối repository injection.

### 7.4. consumer/src/main/java/demo/consumer/Main.java

~~~java
package demo.consumer;

import com.example.internal.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.origin());
    }
}
~~~

**Main.java tự nó chưa chạy được** khi chưa có greeting-api JAR trên classpath. Sau khi seed hai Maven repositories, Gradle sẽ resolve JAR đúng hoặc sai tùy policy. Public API của hai JAR giống nhau; khác biệt nằm ở **method body trả chuỗi**.

### 7.5. tools/SeedRepositories.java — tạo hai artifact hoàn toàn vô hại

Chương trình Java 17 dưới đây tạo **source file, class bytecode, JAR và Maven POM** cho cả hai repositories. Nó dùng **JavaCompiler** của JDK, không gọi shell hoặc network.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class SeedRepositories {
    private SeedRepositories() {
    }

    private static void seed(Path repository, String marker)
            throws Exception {

        Path temporary = Files.createTempDirectory("repo-policy-lab-");
        Path source = temporary.resolve(
                "src/com/example/internal/Greeting.java"
        );
        Path classes = temporary.resolve("classes");

        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        // Không có network, exec hay side effect ngoài file lab.
        String javaSource =
                "package com.example.internal;\n"
                + "public final class Greeting {\n"
                + "    private Greeting() {}\n"
                + "    public static String origin() {\n"
                + "        return \"" + marker + "\";\n"
                + "    }\n"
                + "}\n";

        Files.writeString(
                source, javaSource, StandardCharsets.UTF_8
        );

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                    "Use JDK 17, not a runtime without javac"
            );
        }

        int exit = compiler.run(
                null, null, null,
                "--release", "17",
                "-encoding", "UTF-8",
                "-d", classes.toString(),
                source.toString()
        );

        if (exit != 0) {
            throw new IllegalStateException(
                    "javac failed with exit code " + exit
            );
        }

        Path versionDir = repository.resolve(
                "com/example/internal/greeting-api/1.0.0"
        );
        Files.createDirectories(versionDir);

        Path jar = versionDir.resolve(
                "greeting-api-1.0.0.jar"
        );
        Path bytecode = classes.resolve(
                "com/example/internal/Greeting.class"
        );

        try (JarOutputStream out = new JarOutputStream(
                Files.newOutputStream(jar)
        )) {
            JarEntry entry = new JarEntry(
                    "com/example/internal/Greeting.class"
            );
            entry.setTime(0L);
            out.putNextEntry(entry);
            Files.copy(bytecode, out);
            out.closeEntry();
        }

        String pom = """
                <?xml version="1.0" encoding="UTF-8"?>
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example.internal</groupId>
                  <artifactId>greeting-api</artifactId>
                  <version>1.0.0</version>
                  <packaging>jar</packaging>
                </project>
                """;

        Files.writeString(
                versionDir.resolve("greeting-api-1.0.0.pom"),
                pom,
                StandardCharsets.UTF_8
        );
    }

    public static void main(String[] args) throws Exception {
        seed(Path.of("repos/trusted-internal"),
                "TRUSTED_INTERNAL");
        seed(Path.of("repos/public-simulated"),
                "SHADOW_PUBLIC");
        System.out.println("seed=complete");
    }
}
~~~

**Rà soát Java:**
- **ToolProvider.getSystemJavaCompiler()** cần JDK, không chỉ JRE.
- Compiler dùng **--release 17**, biên dịch đúng class cùng package.
- Hai JAR có **cùng class name và public API**, nhưng method origin trả hai marker khác.
- **JarOutputStream** tạo entry com/example/internal/Greeting.class.
- **POM** có đầy đủ modelVersion/groupId/artifactId/version/packaging.
- Artifact nằm đúng Maven layout: group với dấu chấm đổi thành path slash, artifact/version và JAR/POM cùng tên.
- **Không có mã độc**: class chỉ trả một String hằng. Tool này dành cho local lab, không phát hành lên remote repo.
- Temporary compilation dirs được tạo bằng JDK temporary-directory API. Production cleanup có thể cần thêm; trong bài lab nhỏ chúng không ảnh hưởng output.

### 7.6. Compile và seed bằng javac/java (Linux/macOS)

Từ repository-defense-lab root:

~~~bash
mkdir -p tools/classes

javac --release 17 -encoding UTF-8 \
    -d tools/classes \
    tools/SeedRepositories.java

java -cp tools/classes SeedRepositories
~~~

**Stdout chính xác của SeedRepositories.main:**

~~~text
seed=complete
~~~

Nội dung hai Maven local repositories được tạo sau khi lệnh hoàn tất.

### 7.7. Compile và seed trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force tools\classes | Out-Null
javac --release 17 -encoding UTF-8 -d tools\classes tools\SeedRepositories.java
java -cp tools\classes SeedRepositories
~~~

**Stdout chính xác:**

~~~text
seed=complete
~~~

Tệp JAR và POM ở cả hai repositories có cùng GAV nhưng class content khác nhau, được tạo hoàn toàn offline.

### 7.8. Thử unsafe mode — minh họa repository shadowing

Chạy trên Linux/macOS:

~~~bash
./gradlew \
    --gradle-user-home .gradle-home-unsafe \
    -PrepoMode=unsafe \
    :consumer:run \
    --rerun-tasks --no-build-cache --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --gradle-user-home .gradle-home-unsafe -PrepoMode=unsafe :consumer:run --rerun-tasks --no-build-cache --quiet
~~~

**Stdout do Java Main.main in:**

~~~text
SHADOW_PUBLIC
~~~

Trong unsafe mode, public-simulated đứng trước và có POM/JAR với đúng GAV, nên Gradle resolve module từ repository ấy trong môi trường mới. Đây là **lỗi routing có thể quan sát**, không phải exploit.

**Giải thích các flags:**
- **--gradle-user-home .gradle-home-unsafe** tạo dependency cache riêng cho thí nghiệm; tránh cache đã pin source khác.
- **--rerun-tasks** ép thực thi task thay vì dựa vào up-to-date outcome.
- **--no-build-cache** không dùng task output cache trong thí nghiệm.
- **--quiet** giảm logs, nhưng Java application stdout vẫn hiển thị.
- Nếu Wrapper chưa được tải trong Gradle User Home này, lần đầu có thể cần tải Gradle distribution từ nguồn Wrapper; đây không phải truy vấn Maven external của artifact lab.

**Tại sao kết quả khác dù version vẫn 1.0.0?** Vì repository policy cho phép **một nguồn khác cung cấp cùng GAV** và bản source shadow đứng trước.

### 7.9. Thử safe mode — chặn confusion với exclusiveContent

Linux/macOS:

~~~bash
./gradlew \
    --gradle-user-home .gradle-home-safe \
    -PrepoMode=safe \
    :consumer:run \
    --rerun-tasks --no-build-cache --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --gradle-user-home .gradle-home-safe -PrepoMode=safe :consumer:run --rerun-tasks --no-build-cache --quiet
~~~

**Stdout do Java Main.main in:**

~~~text
TRUSTED_INTERNAL
~~~

Gradle chỉ được lấy com.example.internal từ TrustedInternal trong safe policy. Public-simulated có cùng GAV **nhưng bị filter và exclusivity loại khỏi candidates**.

**Quan trọng:** Hai thí nghiệm dùng Gradle User Home khác nhau để làm rõ source selection. Dùng một cache chung rồi đổi policy có thể bị ảnh hưởng bởi repository stickiness và những entry đã resolve trước đó; vì thế không dùng một log cũ làm bằng chứng cấu hình mới sai.

### 7.10. Kiểm tra artifacts được tạo

Linux/macOS:

~~~bash
jar --list --file \
  repos/trusted-internal/com/example/internal/greeting-api/1.0.0/greeting-api-1.0.0.jar

jar --list --file \
  repos/public-simulated/com/example/internal/greeting-api/1.0.0/greeting-api-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
jar --list --file repos\trusted-internal\com\example\internal\greeting-api\1.0.0\greeting-api-1.0.0.jar
jar --list --file repos\public-simulated\com\example\internal\greeting-api\1.0.0\greeting-api-1.0.0.jar
~~~

Entry cần có ở cả hai:

~~~text
com/example/internal/Greeting.class
~~~

Chỉ xem JAR entry không phân biệt method body. Dùng execution stdout hoặc kiểm tra hashes của JAR/Class để chứng minh bytes khác nhau.

### 7.11. Bài thử negative: private repository thiếu artifact

Ở safe mode, nếu TrustedInternal không có **com.example.internal:greeting-api:1.0.0**:
- Dù public-simulated có artifact ấy, Gradle **không được fallback**.
- Dependency resolution phải thất bại với module not found/không có nguồn phù hợp.
- Đó là kết quả đúng của fail-closed policy.

Bài thử có thể thực hiện **trong bản sao riêng của lab**, đổi tên thư mục version của TrustedInternal rồi dùng một Gradle User Home mới cho safe mode. Sau thử, trả thư mục về và không đưa thao tác xóa này vào repo thật. Không xóa ~/.gradle của người dùng và không disable content filter để làm CI xanh giả.

### 7.12. Bài thử negative: chặn repositories block trong consumer

Tạm thêm vào **consumer/build.gradle**:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Khi chạy task bất kỳ cần configuration, Gradle phải báo lỗi do **RepositoriesMode.FAIL_ON_PROJECT_REPOS**. Đây là một kiểm thử riêng, không để block này trong lab chính.

**Kết luận kiểm thử:**
- Unsafe mode: artifact shadow được chọn → **SHADOW_PUBLIC**.
- Safe mode: artifact trusted được chọn → **TRUSTED_INTERNAL**.
- Safe + missing trusted artifact: **resolution fail**, không fallback.
- Safe + consumer repositories injection: **configuration fail**.

Bốn kết quả trên kiểm tra cả **repository ownership** lẫn **policy enforcement**.

## 8. Phân tích những sai lầm khi dùng content filters

### 8.1. Chỉ include group ở private repo

~~~groovy
repositories {
    maven {
        url = uri('https://internal.example.invalid/maven')
        content {
            includeGroup('com.acme.internal')
        }
    }
    mavenCentral()
}
~~~

**Vấn đề:** Maven Central vẫn không bị cấm cung cấp com.acme.internal. Khi private thiếu artifact, public có thể được hỏi.

**Khắc phục:** exclusiveContent hoặc cấm group đó ở **mọi** public repo trong cùng resolution scope.

### 8.2. Dùng excludeGroup ở một public repo rồi thêm public repo khác

~~~groovy
repositories {
    mavenCentral {
        content {
            excludeGroup('com.acme.internal')
        }
    }

    maven {
        url = uri('https://mirror.example.invalid/public')
    }
}
~~~

**Vấn đề:** Mirror không filter nên vẫn có thể cung cấp GAV internal. Mọi source cần thuộc một policy rõ. exclusiveContent giúp tự áp exclusions khi thêm repo mới trong cùng handler.

### 8.3. Regex quá rộng

~~~groovy
content {
    includeGroupByRegex('com\\..*')
}
~~~

Regex này cho phép quá nhiều packages thuộc nhiều tổ chức/nhà phát hành khác nhau. Khi định nghĩa ownership, nên dùng exact groups hoặc regex phản ánh đúng namespace có quyền kiểm soát.

### 8.4. Regex quá hẹp

~~~groovy
content {
    includeGroup('com.acme.internal')
}
~~~

Không bao gồm **com.acme.internal.auth**, vì group Maven là một string chính xác. Nếu có child groups, thêm từng group hoặc dùng anchored regex hợp lý.

### 8.5. Coi danh sách group là tên thư mục Maven

Gradle match **group** trong GAV, ví dụ com.acme.internal, không phải đường dẫn filesystem com/acme/internal. Đường dẫn chỉ là cách Maven repositories lưu artifact. Đừng viết includeGroup('com/acme/internal').

### 8.6. Filter source nhưng quên transitive modules

Internal POM có thể tham chiếu org.slf4j, Jackson, Guava hoặc platform BOM. Chúng cần các repositories được phép tương ứng; không đưa toàn bộ transitive dependencies về private repo nếu nguồn đó không proxy public dependencies.

### 8.7. Không kiểm tra POM/Gradle metadata

Artifact không chỉ là JAR. POM, parent POM, BOM và Gradle Module Metadata có thể mang dependency constraints/transitive edges. Nếu metadata đến sai nguồn, build graph có thể bị ảnh hưởng trước khi class được load.

Vì vậy **repository source và metadata integrity** cũng thuộc supply-chain policy.

### 8.8. Dùng mavenLocal() vô tội vạ

~~~groovy
repositories {
    mavenLocal()
    mavenCentral()
}
~~~

Maven Local có thể chứa artifact do một build/dev install trước đó xuất bản, với cùng GAV/version nhưng khác bytes. Nó là local filesystem cache/repository, **không phải trusted corporate release registry**.

Trong CI/release:
- Tránh thêm mavenLocal() mặc định nếu không có lý do rõ.
- Không dùng mavenLocal() để vượt strict repository policy.
- Nếu cần thử local publishing, nên có môi trường/test source riêng và không dùng làm căn cứ provenance production.
- Cân nhắc repository stickiness khi artifact JAR/POM thiếu hoặc sai.

## 9. PluginManagement: plugin marker cũng có thể bị nhầm nguồn

Plugins DSL dùng plugin ID và version:

~~~groovy
plugins {
    id 'com.acme.build.quality' version '1.2.0'
}
~~~

Gradle thường resolve plugin marker module dựa trên plugin ID rồi resolve implementation module/transitives. Đây là **resolution domain khác** với dependencies { implementation ... } của application.

Một settings production có thể có plugin policy riêng:

~~~groovy
pluginManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    url = uri(
                        'https://plugins.example.invalid/internal'
                    )
                }
            }
            filter {
                includeGroupByRegex(
                    'com\\.acme\\.build(\\..+)?'
                )
            }
        }
        gradlePluginPortal()
    }
}
~~~

**Đây là snippet kiến trúc, chưa phải một lab có server thật.** Đường **.invalid** không phải endpoint hoạt động. Khi dùng thật:
- Kiểm tra **plugin marker group** (thường liên quan plugin ID).
- Kiểm tra **implementation module group** có thể **khác** marker group.
- Map tất cả các groups thực sự thuộc nội bộ vào allowed sources.
- Không đưa internal implementation module vào public repository chỉ vì marker đã được filter.
- Audit các transient plugin dependencies và compatible repositories.
- Chú ý caveat exclusiveContent với legacy **buildscript.repositories** như mục 6.3.
- Khi dùng Gradle core plugins như java/application, không cần tải marker từ Plugin Portal.

**FAIL_ON_PROJECT_REPOS không thay thế pluginManagement repository policy.**

## 10. Legacy buildscript và included builds

### 10.1. buildscript repositories

Legacy plugin application:

~~~groovy
buildscript {
    repositories {
        maven {
            url = uri(
                'https://build-tools.example.invalid/repository'
            )
        }
    }

    dependencies {
        classpath 'com.acme.build:legacy-plugin:1.2.0'
    }
}
~~~

Đây là ví dụ minh họa, không có thật plugin endpoint. Buildscript classpath resolution không nên mặc định được coi là đã được bảo vệ chỉ vì project dependencyResolutionManagement có exclusiveContent cho một namespace.

**Việc phải làm:** Khi còn legacy classpath:
- Kiểm kê plugin artifacts và nguồn.
- Migrate sang plugins DSL hoặc convention plugins khi phù hợp.
- Kiểm soát buildscript.repositories và dependencies đúng scope.
- Test compatibility với pluginManagement exclusiveContent.
- Không thêm public fallback cho plugin nội bộ.

### 10.2. Included build và build-logic

Một included build như **build-logic** có settings/build scripts riêng. Nó có thể tự resolve dependencies/plugins mà project root policy không định tuyến giống hệt.

Hãy:
- Có chuẩn repository policy cho **từng settings.gradle** nếu included build tự chủ.
- Đồng bộ ownership mappings bằng convention/policy phù hợp, nhưng không giả định một settings block tự lan sang mọi included build.
- Test plugin markers, build-logic dependencies và root application dependencies.
- Tránh đọc credentials từ hardcoded text khi shared build logic.

### 10.3. Publishing repositories khác resolution repositories

Mẫu:

~~~groovy
publishing {
    repositories {
        maven {
            url = uri(
                'https://publish.example.invalid/internal'
            )
        }
    }
}
~~~

Đây là **upload destination**, không giúp consumer tự resolve từ đúng nơi. Một tổ chức phải có cả:
- Publish path ACL/checksums/signatures.
- Consumer repository routing/exclusivity.
- Artifact version policy.
- Audit/review/rollback procedures.

Không nhầm **maven-publish** với dependencyResolutionManagement.

## 11. Quản lý credentials, HTTPS và repository permissions

Một cấu hình production cho trusted Maven repository có thể như sau:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'InternalReleases'
                    url = uri(
                        'https://maven.example.invalid/releases'
                    )
                    credentials {
                        username = providers.gradleProperty(
                            'internalRepoUser'
                        ).get()
                        password = providers.gradleProperty(
                            'internalRepoPassword'
                        ).get()
                    }
                }
            }
            filter {
                includeGroupByRegex(
                    'com\\.acme\\.internal(\\..+)?'
                )
            }
        }

        mavenCentral()
    }
}
~~~

**Mẫu minh họa**: thay URL .invalid bằng server chính thức và cấp properties qua CI secret manager hoặc Gradle user home riêng của developer. Nếu credentials thiếu, .get() sẽ **fail**, phù hợp một policy yêu cầu authenticated source. Với repo hỗ trợ trusted read-only anonymous access, có thể thiết kế credentials block có điều kiện rõ ràng.

**Không commit passwords vào repo**. Không log secrets, không bỏ qua certificate verification và không bật allowInsecureProtocol để tạm xử lý TLS lỗi. Đừng đặt credentials ở một artifact public report.

### 11.1. Quyền truy cập tối thiểu

- **Developer builds**: read artifacts, không được publish release tùy ý.
- **CI release job**: publish theo service identity scoped tới namespace/repository/version policy.
- **Pull requests không tin cậy**: không nhận write credentials hoặc khả năng thay đổi repo policy trên trusted pipeline.
- **Repository administrators**: review group ownership, retention, immutability và access logs.
- **Artifact consumers**: được quyền đọc đúng scope, không dùng publish token có quyền ghi.
- **Signers**: giữ signing key riêng, không đặt trong public build logs/Gradle cache.

### 11.2. “Internal first” cần có thêm điều kiện

Ngay cả khi private repo đầu tiên:
- Một missing artifact có thể bị fallback.
- Có thể có thêm public repo trong plugin scope.
- Một plugin có thể thêm project repo nếu không FAIL_ON_PROJECT_REPOS.
- Local repository cache có thể giữ origin cũ.
- Credentials sai/TLS lỗi không được giải quyết bằng public fallback.

Chính sách phòng thủ thực sự là **approved namespace ownership + enforced repo declaration + independent integrity validation**.

## 12. Defense in depth: locking, verification và version policy

### 12.1. Dependency locking

Dependency locking cố định resolved versions cho các configurations đã được khóa, giảm rủi ro dynamic version drift.

Ví dụ khai báo trên project:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Khi khởi tạo/update locks theo workflow được kiểm soát:

~~~bash
./gradlew dependencies --write-locks
~~~

**Cần lưu ý:** Lock files không tự chứng minh artifact đến từ trusted repository hoặc bytes đúng. Cùng GAV/version có thể tồn tại ở hai repos. Locking bảo vệ **version selection**, còn exclusiveContent bảo vệ **source routing**.

Trong CI, không tùy tiện xóa lockfiles hoặc tự regenerate locks sau mỗi resolution error để build xanh.

### 12.2. Dependency verification

Gradle hỗ trợ **SHA-256 checksum** và **PGP signature verification**, qua:

~~~text
gradle/verification-metadata.xml
~~~

Có thể bootstrap metadata:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

**Cảnh báo quan trọng:** Bootstrap lấy hashes/signatures từ **artifacts đã resolve hiện tại**. Nếu một artifact shadow đã được resolve trước khi policy được sửa, metadata có thể ghi checksum của **artifact sai**. Phải review origins, PGP keys và hashes qua nguồn độc lập, không coi file sinh tự động là bằng chứng tin cậy.

Verification có thể phát hiện nội dung byte bị đổi với cùng coordinates khi checksums đã được thiết lập đáng tin cậy; nhưng không quyết định ownership routing thay exclusiveContent.

### 12.3. Bộ ba phân công trách nhiệm

| Công cụ | Cái được bảo vệ | Điều không tự bảo vệ |
|---|---|---|
| **exclusiveContent/content filters** | Repository nào được phép cung cấp group/module | Artifact bytes/signature có đáng tin không |
| **Dependency locking** | Resolved versions đã pin | Nguồn repository hoặc integrity của cùng GAV |
| **Dependency verification** | Checksums/signatures so với trust metadata đã review | Lựa chọn namespace owner và CVEs |
| **Vulnerability scanning** | Lỗ hổng công khai đã biết trong thư viện | GAV có đến đúng producer không |
| **HTTPS + credentials + ACL** | Kênh truyền, authentication và quyền | Artifact từng được trusted account publish có đúng không |
| **Fixed version + review** | Giảm dynamic/version selection bất ngờ | Shadowing của cùng fixed GAV nếu source policy sai |

**Không có một công tắc thần kỳ.** Những công cụ này bổ sung cho nhau.

### 12.4. Dynamic versions và changing modules

Tránh phụ thuộc runtime nguy cơ cao bằng:

~~~groovy
dependencies {
    // Ưu tiên version được review:
    implementation 'com.acme.internal:auth-client:2.4.0'
}
~~~

hơn:

~~~groovy
dependencies {
    // Anti-pattern cho supply-chain critical dependency:
    implementation 'com.acme.internal:auth-client:2.+'
}
~~~

Dynamic selectors có thể mở rộng candidate versions ở nhiều repositories; snapshots/changing modules có bytes thay đổi theo thời gian. Version locking + repository policy + verification phải được đánh giá cùng nhau.

## 13. Một repository policy production gọn và rõ

Giả sử tổ chức có:
- **com.acme.internal** và các subgroups do private registry sở hữu.
- Các thư viện public từ Maven Central.
- Gradle plugins của tổ chức thuộc một namespace plugin riêng.

**settings.gradle** ở build chính:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        // Cần phân loại marker/implementation plugin đúng groups.
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'InternalReleases'
                    url = uri(
                        'https://maven.example.invalid/releases'
                    )
                }
            }
            filter {
                includeGroupByRegex(
                    'com\\.acme\\.internal(\\..+)?'
                )
            }
        }

        mavenCentral()
    }
}

rootProject.name = 'secure-multi-module'
include 'app'
~~~

**Đoạn này là ví dụ kiến trúc, không chạy được khi chưa có internal Maven server.** Riêng pluginManagement ở trên chỉ cấu hình Gradle Plugin Portal; nếu tổ chức có **internal plugins**, cần thêm approved plugin repository/filters ngay tại pluginManagement như mục 9, không giả định snippet này đã bảo vệ plugin nội bộ.

Không thêm **mavenLocal()** hoặc “public fallback mirror” chưa được review. Không để child project tự thêm repositories.

### 13.1. Quy tắc audit ownership

Lập bảng ngắn cho repository policy:

| Namespace | Owner | Nguồn hợp lệ | Cơ chế enforce |
|---|---|---|---|
| com.acme.internal.* | Internal platform team | Corporate releases registry | exclusiveContent |
| com.acme.build.* | Build platform team | Internal plugin registry | pluginManagement exclusive/filter |
| org.slf4j.* | Public upstream | Maven Central/trusted mirror | Public policy; có thể whitelist khi yêu cầu |
| org.junit.* | Public upstream | Maven Central/trusted mirror | Public policy |
| Unknown private group | Chưa xác định | **Không tự fallback** | Full audit và fail closed |

Trong môi trường chỉ cho phép proxy nội bộ, có thể cho **mọi** public dependencies đi qua **một vetted repository manager**, nhưng vẫn cần tách namespace ownership bằng routing/permissions tại proxy và Gradle nếu policy yêu cầu.

### 13.2. CI contract tests

Một pipeline production nên:
1. Chạy clean Gradle User Home để test source policy.
2. Dùng một fixture chứa duplicate harmless GAV ở trusted/public simulated repos.
3. Assert safe mode không chọn public copy.
4. Assert trusted artifact missing → resolution failure, không fallback.
5. Assert project repositories injection → configuration failure.
6. Test plugin marker nhóm nội bộ không rơi về Plugin Portal.
7. Test transitive public modules vẫn resolve từ allowed public source.
8. Test dependency verification vẫn PASS với approved artifacts.
9. Test included builds/build-logic có policy tương đương.
10. Báo Gradle Wrapper/version, selected graph, cache state và artifacts đã verify.

**Không xây test bằng cách publish một GAV giả mạo lên Maven Central thật.** Dùng fixture Maven directories/servers cục bộ đã cô lập.

## 14. Kiểm tra nguồn và chẩn đoán dependency resolution

Một số Gradle commands hữu ích:

~~~bash
./gradlew :consumer:dependencies \
    --configuration runtimeClasspath --console=plain

./gradlew :consumer:dependencyInsight \
    --dependency greeting-api \
    --configuration runtimeClasspath \
    --console=plain

./gradlew :consumer:run --info --console=plain

./gradlew :consumer:run --refresh-dependencies \
    --info --console=plain
~~~

**Các giới hạn:**
- **dependencies** hiển thị graph, resolved versions và dependency relationships; không phải một chứng thư provenance đầy đủ về repository origin.
- **dependencyInsight** chỉ ra lý do chọn version/variant; nó không thay một kiểm tra được JAR bytes/source.
- **--info** có thể cung cấp logs hữu ích về repository fetch/cache, nhưng log format khác theo Gradle version và cache hits có thể không truy vấn network.
- **--refresh-dependencies** refresh resolution cache, không bỏ content filters hoặc thay role của dependency verification.
- **--offline** có thể thành công bằng cached artifact cũ; thành công offline **không chứng minh repository policy mới đã được thực thi với một fresh lookup**.

### 14.1. Cách xác định artifact thật đã được dùng

Trong lab:
- Hai JAR có method **origin()** trả marker khác nhau.
- Chạy application và kiểm tra stdout.
- Dùng two isolated Gradle User Homes để tránh repository stickiness che source selection.
- So jar SHA-256 trong repositories để chứng minh bytes khác.
- Thử negative missing trusted artifact để xác minh **không fallback**.

Trong production:
- Dùng checksum/signature verification và approved provenance.
- Kiểm tra repository access logs khi nghi ngờ.
- Lưu dependency graph/lockfile/build scan theo policy.
- Không chỉ nhìn xem một tọa độ có tồn tại trong ~/.gradle hay không.

### 14.2. Bảo vệ khỏi “repo poisoned earlier”

Nếu một build từng resolve GAV từ repo sai:
1. Tạm cô lập CI agent/Gradle User Home bị nghi ngờ.
2. Kiểm tra repository policy đã enforce ở đúng scope.
3. Xác minh checksum/signature từ nguồn độc lập.
4. Chạy thử trong clean environment với trusted source.
5. Nếu có dấu hiệu xâm phạm, báo incident cho security/repository owners.
6. Không tự tạo whitelist SHA-256 từ artifact nghi vấn.
7. Review token/ACL và khả năng cache hoặc downstream binaries đã bị ảnh hưởng.

Một kết quả “build lại thành công” không tự chứng minh binary đã hết bị ảnh hưởng.

## 15. Troubleshooting thường gặp

### Lỗi 1 — Chỉ includeGroup ở private repo nhưng vẫn tải sai GAV

**Nguyên nhân:** includeGroup chỉ giới hạn private repo; public repo vẫn có thể cung cấp cùng group.

**Cách sửa:** exclusiveContent cho private namespace hoặc exclude tương ứng ở mọi public repo.

### Lỗi 2 — Internal repo đứng đầu nhưng public shadow artifact vẫn được chọn

**Nguyên nhân:** Internal repo không có metadata/version mong đợi, hoặc một source khác được chọn do thứ tự, cache/metadata hoặc dynamic resolution.

**Cách sửa:** Kiểm tra routing, fixed version và repository origin; không dựa vào thứ tự. Chọn exclusiveContent và negative missing-module test.

### Lỗi 3 — Internal artifact bị thiếu nên Gradle báo module not found

**Nguyên nhân:** Exclusive policy hoạt động đúng nhưng trusted repo chưa publish module/version.

**Cách sửa:** Sửa publication/mirroring/credentials ở trusted repo. **Không** tạm bật public fallback cho internal namespace.

### Lỗi 4 — Một transitive public module không resolve

**Nguyên nhân:** Filter vô tình cấm public group hoặc chỉ có internal repo mà không có trusted public mirror.

**Cách sửa:** Đưa transitive public namespaces vào approved public/proxy source; không nới private group ra public.

### Lỗi 5 — FAIL_ON_PROJECT_REPOS làm third-party plugin fail

**Nguyên nhân:** Plugin tự khai báo một project repository.

**Cách sửa:** Migrate/upgrade plugin, chuyển repo vào settings policy hoặc sửa plugin; không tắt enforcement không review.

### Lỗi 6 — PREFER_SETTINGS được bật nhưng vẫn có cảnh báo repo injection

**Nguyên nhân:** Project/plugin khai repo, Gradle cảnh báo và ưu tiên settings.

**Cách sửa:** Dọn khai báo để có thể lên FAIL_ON_PROJECT_REPOS; không coi warning vô hại mãi mãi.

### Lỗi 7 — Plugin không resolve dù application dependency bình thường

**Nguyên nhân:** pluginManagement.repositories là scope riêng, cần plugin marker/implementation source phù hợp.

**Cách sửa:** Kiểm tra plugin ID/version/marker GAV/group và exclusive filters của plugin scope.

### Lỗi 8 — pluginManagement exclusiveContent làm legacy buildscript.repositories lỗi

**Nguyên nhân:** Caveat được Gradle docs mô tả: exclusive filter trong pluginManagement có thể khiến bổ sung buildscript repositories bất hợp lệ.

**Cách sửa:** Centralize repositories và migrate legacy plugin, hoặc thiết kế non-exclusive content filtering khi bắt buộc; kiểm tra trade-off bảo mật.

### Lỗi 9 — included build vẫn truy vấn public GAV nội bộ

**Nguyên nhân:** Included build có settings/repositories riêng; main settings policy không tự bảo vệ tất cả scope.

**Cách sửa:** Audit từng build, áp policy tương đương hoặc enterprise policy được kiểm tra kỹ.

### Lỗi 10 — Đổi repositories nhưng vẫn thấy artifact origin cũ

**Nguyên nhân:** Dependency metadata cache và repository stickiness.

**Cách sửa:** Test trong clean Gradle User Home; dùng --refresh-dependencies có chủ đích, không xóa cache toàn máy mù quáng.

### Lỗi 11 — mavenLocal() gây kết quả khác giữa CI và máy cá nhân

**Nguyên nhân:** Maven Local chứa artifact do local publish trước đó, với bytes/metadata không giống official source.

**Cách sửa:** Không đưa mavenLocal() vào production resolution policy nếu không có lý do rõ; isolate local publishing labs.

### Lỗi 12 — dependency locking pass nhưng artifact bytes vẫn sai

**Nguyên nhân:** Lock chỉ pin resolved version, không xác minh GAV được lấy từ source đáng tin.

**Cách sửa:** Exclusive source + SHA-256/PGP verification đã review.

### Lỗi 13 — Dependency verification mismatch

**Nguyên nhân:** Artifact thật không khớp checksum đã tin cậy, do repository metadata khác, tampering, proxy rewrite hoặc local cache corruption.

**Cách sửa:** Điều tra source, xác minh từ độc lập, không tự update checksum từ artifact nghi vấn để “sửa” lỗi.

### Lỗi 14 — --write-verification-metadata làm build pass sau khi có shadow artifact

**Nguyên nhân:** Bootstrap ghi checksum của dependency đã resolve, kể cả copy sai nguồn.

**Cách sửa:** Dừng, kiểm tra artifact source và signers, review generated metadata qua nguồn độc lập rồi mới commit.

### Lỗi 15 — Regex excludeGroupByRegex vô tình chặn public library

**Nguyên nhân:** Regex rộng/thiếu anchors hoặc namespace ownership nhầm.

**Cách sửa:** Dùng exact includeGroup khi có thể; với regex, review kèm unit-like test cho accepted/rejected groups.

### Lỗi 16 — Internal group có subgroups nhưng includeGroup chỉ khớp group cha

**Nguyên nhân:** Group Maven là string, không có implicit hierarchy.

**Cách sửa:** Thêm từng group hoặc includeGroupByRegex biểu diễn subgroups rõ ràng.

### Lỗi 17 — Build offline pass nên team nghĩ policy đã an toàn

**Nguyên nhân:** Cached artifact đã tồn tại; offline resolution không tạo một fresh network lookup.

**Cách sửa:** Chạy clean acceptance tests với isolated caches/fixture repos và test missing private artifact.

### Lỗi 18 — HTTP repository hoạt động nhưng build bị downgrade bảo mật

**Nguyên nhân:** Chấp nhận insecure protocol hoặc bỏ TLS verification khi gặp lỗi cấu hình.

**Cách sửa:** Dùng HTTPS/valid certificates, sửa CA/proxy/cert chain theo policy; không chấp nhận transport không bảo mật cho critical dependencies.

### Lỗi 19 — Plugin implementation group nằm ngoài marker regex

**Nguyên nhân:** Gradle plugin marker và implementation artifact có thể ở GAV khác group.

**Cách sửa:** Inventory và filter **cả marker lẫn implementation/transitives** đúng ownership.

### Lỗi 20 — Một repository mới được thêm vào settings rồi nguồn internal bị lộ

**Nguyên nhân:** Policy chỉ exclude ở một public repo cũ, source mới không được filter.

**Cách sửa:** exclusiveContent cho internal groups; test namespace querying khi add repository.

### Lỗi 21 — Artifact release bị ghi đè cùng GAV/version

**Nguyên nhân:** Internal registry cho phép overwrite immutable release hoặc có credential misuse.

**Cách sửa:** Enforce immutability và publish ACL ở server; dùng verification, incident response khi mismatch.

### Lỗi 22 — Dynamic version 2.+ bất ngờ chọn release khác

**Nguyên nhân:** Dynamic selectors có thể thấy metadata versions mới, ảnh hưởng resolution graph/behavior.

**Cách sửa:** Pin approved versions và dependency locking, tránh public source cho internal namespace.

### Lỗi 23 — CI báo “build xanh” nhưng dùng artifact từ wrong scope

**Nguyên nhân:** Tests kiểm behavior chưa đủ phân biệt source, plugin scope hoặc cache đã che thay đổi.

**Cách sửa:** Thêm policy acceptance tests, negative fallback, verification metadata và provenance reporting.

### Lỗi 24 — Repository policy kiểm soát resolve nhưng không kiểm soát publish

**Nguyên nhân:** publishing.repositories độc lập và server có quyền ghi riêng.

**Cách sửa:** Enforce publishing ACL/signing/immutability và review separate upload destinations.

### Lỗi 25 — Dependency confusion test không tái hiện khi đổi unsafe/safe liên tiếp

**Nguyên nhân:** Gradle cache/repository stickiness hoặc task output caching giữ trạng thái trước đó.

**Cách sửa:** Dùng isolated Gradle User Homes riêng và --rerun-tasks --no-build-cache trong lab, giữ seed artifacts giống nhau.

## 16. Checklist khi đưa policy vào production

1. Đã có **inventory** tất cả internal group/module namespaces?
2. Mỗi namespace có **owner** và trusted source được công bố?
3. Có phân biệt group chính xác và subgroups cần regex không?
4. Project repositories tập trung ở settings.gradle?
5. repositoriesMode đã chọn FAIL_ON_PROJECT_REPOS khi tương thích?
6. Có audit project/plugin tự inject repositories?
7. Internal groups dùng exclusiveContent hoặc exclusions đầy đủ?
8. Có test private missing artifact phải fail, không public fallback?
9. Public repos không bị hỏi về internal coordinates?
10. Transitive public dependencies vẫn resolve đúng nguồn?
11. Plugin marker and implementation groups đã được map?
12. pluginManagement repositories có policy độc lập?
13. Legacy buildscript repositories đã được inventory?
14. Included builds/build-logic đã được đánh giá riêng?
15. Không vô tình đưa mavenLocal vào CI/release?
16. Repository precedence không được coi là rào chắn duy nhất?
17. HTTPS/certificates/hostnames được kiểm soát?
18. Credentials không nằm trong repo hoặc logs?
19. Publish identities và read identities có least privilege?
20. Registry có release immutability và audit logs?
21. Fixed versions/locking được dùng cho critical dependencies?
22. Dependency verification SHA-256/PGP metadata được review?
23. Verification bootstrap không tin các bytes từ một nguồn chưa được kiểm chứng?
24. Có vulnerability scanning và license policy riêng?
25. Tests thực sự chạy ở isolated cache environment khi kiểm nguồn?
26. Có negative test chặn project repository injection?
27. Có negative test plugin source shadowing?
28. Có runbook xử lý dependency verification mismatch?
29. Có baseline repo/Gradle Wrapper versions và logs cho incident?
30. Mỗi thay đổi settings/repository policy được code review/CI gate trước khi merge?

## 17. Bài tập

**Bài 1.** Dependency confusion xảy ra khi nào dù group:artifact:version vẫn giống nhau?

**Bài 2.** Vì sao đặt private repository trước Maven Central chưa đủ an toàn?

**Bài 3.** content { includeGroup('com.acme.internal') } trên private repo có tự cấm Maven Central chứa cùng group không?

**Bài 4.** exclusiveContent có ích khác content filter thông thường ở điểm nào?

**Bài 5.** Trong safe mode của lab, public-simulated có cùng GAV nhưng Main.main phải in gì?

**Bài 6.** Trong unsafe mode của lab, public-simulated đứng trước và có POM/JAR; Main.main in gì?

**Bài 7.** TrustedInternal không có artifact nhưng public-simulated có; safe mode nên fail hay fallback?

**Bài 8.** Nếu project/build.gradle tự khai repositories khi FAIL_ON_PROJECT_REPOS, outcome gì?

**Bài 9.** So sánh PREFER_PROJECT, PREFER_SETTINGS và FAIL_ON_PROJECT_REPOS.

**Bài 10.** includeGroup('com.acme.internal') có tự bao gồm com.acme.internal.auth không?

**Bài 11.** Nếu chỉ module auth-client được phép ở repo thử nghiệm, nên dùng filter nào?

**Bài 12.** Vì sao một private repo chỉ chứa internal JAR vẫn cần có public repo/proxy cho transitive org.slf4j?

**Bài 13.** Dependency locking có đảm bảo JAR bytes/nguồn cùng GAV là tin cậy không?

**Bài 14.** Dependency verification có tự chặn public repo queries cho internal groups không?

**Bài 15.** Tại sao --write-verification-metadata trên máy đã resolve shadow artifact là nguy hiểm?

**Bài 16.** Một dependency có CVE nhưng checksum/signature đúng: verification có phát hiện CVE không?

**Bài 17.** Vì sao pluginManagement cần repository policy riêng?

**Bài 18.** Có nên xem buildSrc/included builds tự động nhận hết main build repositories không?

**Bài 19.** Vì sao mavenLocal có thể làm hai developer cùng checkout cho kết quả khác nhau?

**Bài 20.** Repository stickiness là gì, nên kiểm chứng source selection bằng cách nào?

**Bài 21.** Vì sao dùng một group regex quá rộng để include có thể tạo nguy cơ?

**Bài 22.** Khi HTTPS private repo gặp lỗi cert, có nên bật allowInsecureProtocol?

**Bài 23.** Tại sao các publish credentials phải tách khỏi consumer read credentials?

**Bài 24.** Nếu policy cho phép public fallback vì internal repo tạm down, rủi ro là gì?

**Bài 25.** Nêu ít nhất bốn CI acceptance tests về repository policy.

**Bài 26.** Khi artifact verification mismatch, điều đầu tiên KHÔNG nên làm là gì?

### Gợi ý đáp án

1. Khi build nhận metadata/artifact cùng tọa độ từ một source không được ủy quyền.
2. Khi internal module missing/lookup order/cache khác, public vẫn có thể được hỏi.
3. **Không.** Filter ấy chỉ áp cho private repo.
4. **exclusiveContent** còn tự exclude namespace đã dành độc quyền khỏi repositories khác trong cùng scope.
5. **TRUSTED_INTERNAL**.
6. **SHADOW_PUBLIC**.
7. **Fail closed**, không lấy copy từ public.
8. Configuration error do repository injection.
9. PREFER_PROJECT ưu tiên project repo; PREFER_SETTINGS ưu tiên settings và cảnh báo; FAIL_ON_PROJECT_REPOS từ chối project repo.
10. **Không.** includeGroup khớp group string chính xác.
11. **includeModule('com.acme.internal','auth-client')**.
12. Transitive dependency có group khác và phải lấy từ một approved source.
13. **Không.** Lock pin version, không chứng minh artifact origin hoặc bytes.
14. **Không.** Verification kiểm tra integrity/provenance theo metadata, không làm namespace routing.
15. Có thể vô tình whitelist checksum của artifact sai.
16. **Không.** Cần vulnerability scanning riêng.
17. Plugin markers/implementation resolution khác project dependencies.
18. **Không.** Audit settings/repositories của từng scope/build.
19. Maven Local chứa những bản publish local khác bytes/metadata của registry chính thức.
20. Gradle ghi nhớ source của resolved artifact; test bằng Gradle User Home sạch hoặc tách biệt.
21. Cho nguồn không mong muốn được quyền cung cấp groups ngoài ownership.
22. **Không.** Sửa chứng chỉ/TLS và authentication.
23. Least privilege; consumer không cần quyền publish artifacts.
24. Khi trusted repo down, public có thể shadow GAV, gây confusion.
25. Shadow GAV safe test, private missing fail test, project injection fail, plugin marker routing, transitive public resolution, included build audit.
26. Không tự regenerate hoặc cập nhật hash từ artifact nghi vấn để ép PASS.

## 18. Tài liệu chính thức

- [Gradle User Manual — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): dependency confusion, name leakage, central repository policy và content filters.
- [Gradle User Manual — Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html): include/exclude groups/modules, exclusiveContent và pluginManagement caveat.
- [Gradle User Manual — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): repositoriesMode PREFER_PROJECT/PREFER_SETTINGS/FAIL_ON_PROJECT_REPOS.
- [Gradle User Manual — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html): Maven, Ivy, local/custom repositories.
- [Gradle User Manual — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html): search order và metadata/artifact sourcing.
- [Gradle User Manual — Dependency Graph Resolution](https://docs.gradle.org/current/userguide/dependency_graph_resolution.html): fixed/dynamic version metadata lookup.
- [Gradle User Manual — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): repository stickiness, source metadata cache và --refresh-dependencies.
- [Gradle User Manual — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): SHA-256/PGP verification, bootstrap limitations và trust review.
- [Gradle User Manual — Locking Dependency Versions](https://docs.gradle.org/current/userguide/dependency_locking.html): version locking và lockfile workflows.
- [Gradle User Manual — Declaring Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): pluginManagement và plugin resolution scopes.
- [Gradle User Manual — Maven Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): repository declaration, Maven/local/artifact formats.
- [Gradle API — RepositoryContentDescriptor](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/repositories/RepositoryContentDescriptor.html): includeGroup/excludeGroup/includeModule filters.
- [Gradle API — InclusiveRepositoryContentDescriptor](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/repositories/InclusiveRepositoryContentDescriptor.html): exclusive content group/module patterns.
- [Gradle API — RepositoriesMode](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/resolve/RepositoriesMode.html): enforcement modes.

**Ghi nhớ:** **Thứ tự repositories không đủ để chống dependency confusion**. **content.includeGroup** chỉ hạn chế một repo, còn **exclusiveContent** biểu diễn ownership và loại group nội bộ khỏi các repo khác trong cùng resolution scope. Đặt project repositories trong **dependencyResolutionManagement** với **FAIL_ON_PROJECT_REPOS**, đồng thời audit **pluginManagement**, legacy buildscript và included builds riêng. Khi trusted artifact thiếu, hãy **fail closed**; không fallback public. Kết hợp version locking, checksum/PGP verification có review, HTTPS, credentials tối thiểu và CI acceptance tests. Build an toàn là build dùng **đúng module, đúng nguồn và đúng bytes**, không chỉ build chạy thành công.
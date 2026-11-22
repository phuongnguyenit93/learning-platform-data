# Thứ tự repository và tác động đến kết quả phân giải trong Gradle

## Mục tiêu học tập

Khi một project khai báo nhiều **repository** (kho cung cấp thư viện), thứ tự khai báo không chỉ ảnh hưởng tốc độ tải. Nó có thể quyết định **Gradle lấy metadata và JAR từ đâu**, gây lỗi khi một kho chứa metadata nhưng thiếu artifact, hoặc làm cùng một dependency có kết quả khác nhau giữa máy phát triển và CI. Những ảnh hưởng này càng quan trọng khi phối hợp **Maven Central**, kho nội bộ, mirror, **mavenLocal()**, repository của plugin và dependency cache.

Sau bài này bạn có thể:

1. Giải thích chính xác việc Gradle tìm **module có version cố định** theo thứ tự repository.
2. Phân biệt **metadata** (POM, Ivy descriptor, Gradle Module Metadata) với **artifact** (JAR, ZIP, AAR...) và hiểu quy tắc lấy artifact từ kho chứa metadata.
3. Biết vì sao **dynamic versions** như **1.+** khác trường hợp version cố định; không áp dụng máy móc “repo đầu tiên luôn thắng” cho bước chọn version.
4. Phân biệt **repositories của dependencies**, **pluginManagement.repositories**, **buildscript.repositories** và chính sách repositories trong **settings.gradle**.
5. Tổ chức mirror/kho nội bộ và public repo bằng **content filters**, **exclusiveContent** và **RepositoriesMode** thay vì chỉ thay đổi thứ tự.
6. Giải thích repository stickiness, dependency cache, **--offline** và **--refresh-dependencies** khi thứ tự thay đổi.
7. Tự tạo hai kho Maven cục bộ có cùng **group:name:version** nhưng JAR khác nhau để kiểm chứng nguồn được chọn mà không phụ thuộc vào Internet khi phân giải dependency.
8. Chẩn đoán lỗi missing module, missing artifact, lỗi mạng, dependency confusion và khác biệt local/CI.

**Đối tượng:** người đã biết **build.gradle**, **settings.gradle**, **dependencies { ... }**, tọa độ Maven **group:name:version**. Ví dụ chính dùng **Gradle Groovy DSL**, có đối chiếu **Kotlin DSL**. Các endpoint **.invalid** chỉ là địa chỉ minh họa, không dùng làm repository thật.

## 1. Repository là nơi Gradle tìm module, không phải nơi khai báo version

Ví dụ **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()

    maven {
        name = 'companyReleases'
        url = uri('https://repo.company.example.invalid/releases')
    }
}

dependencies {
    implementation 'org.example:library:1.2.3'
}
~~~

Trong ngữ cảnh này:

- **dependencies** nói **cần module nào**: group **org.example**, name **library**, version **1.2.3**.
- **repositories** nói **Gradle được phép tìm các module ấy ở đâu**, theo thứ tự đã khai báo.
- **mavenCentral()** khai báo kho Maven Central; **maven { url = ... }** khai báo kho Maven tùy chỉnh.
- **repositories** không tự tải ngay mọi thư viện. Gradle phân giải một configuration khi công việc cần nó, chẳng hạn **compileClasspath** khi biên dịch Java.
- **Version catalog** nếu có chỉ giúp đặt alias cho tọa độ và version; bản thân catalog không chỉ định nguồn tải artifact.

**Lưu ý:** URL **repo.company.example.invalid** là giả định. Nếu sao chép nguyên vào build, việc phân giải từ URL này sẽ thất bại. Trong production cần thay bằng URL HTTPS thật, tài khoản/credentials phù hợp và chính sách bảo mật của tổ chức.

Bài học tập trung vào **dependency repositories**. **Plugin repositories** là một tập độc lập, không được suy ra từ **repositories { ... }** trong Project.

## 2. Thuật toán tìm module có version cố định: thứ tự có ý nghĩa

Giả sử cấu hình dùng:

~~~groovy
repositories {
    maven {
        name = 'first'
        url = uri('https://first.example.invalid/maven')
    }
    maven {
        name = 'second'
        url = uri('https://second.example.invalid/maven')
    }
}

dependencies {
    implementation 'com.acme:shared:1.0'
}
~~~

Khi giải quyết module **com.acme:shared:1.0** với version **1.0** cụ thể, mô hình cơ bản của Gradle là:

1. Xem những repository **đủ điều kiện** sau khi áp dụng content filters và chính sách thực tế.
2. Kiểm tra **metadata** của module theo thứ tự các repository khai báo.
3. Nếu repository đầu tiên không chứa metadata/module phù hợp, thử repository tiếp theo, với điều kiện lỗi nhận được là loại cho phép tiếp tục tra cứu.
4. Khi tìm thấy metadata của module ở một repository, chọn repository ấy làm **nguồn artifact** của module.
5. Lấy những artifact tương ứng của module **từ cùng repository**, thay vì tùy tiện ghép metadata của kho A với JAR của kho B.
6. Lưu metadata, kết quả tra cứu (kể cả không tìm thấy) và thông tin repository nguồn vào dependency cache.

Đây là logic cho **một module/version cụ thể**, không có nghĩa Gradle luôn dùng repository đầu cho *mọi dependency trong graph*. Dependency A có thể được lấy từ kho A; dependency B chỉ có ở kho B nên được lấy từ kho B.

### 2.1. Ví dụ cùng tọa độ, hai nội dung khác nhau

Hai repository chứa:

| Repository | Metadata | JAR của **com.acme:shared:1.0** |
| --- | --- | --- |
| **first** | POM cho version 1.0 | JAR chứa câu trả lời **FIRST** |
| **second** | POM cho version 1.0 | JAR chứa câu trả lời **SECOND** |

Nếu đang phân giải mới, cả hai repository hợp lệ và **first** được khai báo trước, Gradle thường chọn metadata ở **first**, rồi JAR ở **first**. Nếu đảo thứ tự trong một môi trường phân giải mới, kết quả có thể đổi sang **second** dù **tọa độ dependency không thay đổi**.

**Không coi đây là cơ chế ưu tiên bản “mới hơn”, “đúng hơn” hoặc “đáng tin hơn”.** Với cùng version cố định, thứ tự repository chỉ là một phần chính sách chọn nguồn. Nếu hai kho xuất bản byte khác nhau dưới cùng GAV, đó là rủi ro reproducibility và supply chain.

### 2.2. Sơ đồ luồng kiểm tra

~~~text
Yêu cầu com.acme:shared:1.0
           |
           v
   Repository A đủ điều kiện?
           |
      metadata tồn tại?
      /           \
    có             không
    |                |
    v                v
Chọn A         Thử Repository B
    |                |
    v           metadata tồn tại?
Lấy artifacts       /     \
từ A             có      không
                  |        |
                  v        v
             Chọn B      Thử tiếp /
             lấy JAR B   không tìm thấy
~~~

Sơ đồ trên chỉ mô tả nhánh **module có version xác định** khi nguồn có thể truy cập và phản hồi bình thường. Lỗi server/timeout, cache, metadata formats, module rules và chính sách repository làm quy trình thực tế phức tạp hơn.

### 2.3. Khi nào đi tiếp được, khi nào không?

- **Không tìm thấy module tại kho A (ví dụ phản hồi kiểu not found):** Gradle có thể tiếp tục tìm kho B nếu kho B được cho phép.
- **Đã tìm thấy metadata của module tại kho A nhưng JAR cần thiết bị thiếu ở A:** không mặc định thử lấy JAR của cùng module ở kho B. Phân giải có thể thất bại.
- **Kho A báo lỗi mạng, 5xx hoặc bị coi là unavailable:** không coi đây là “không tìm thấy”. Gradle có logic retry/disable repository; quá trình phân giải thường thất bại thay vì âm thầm bỏ qua kho bị lỗi để chọn nguồn khác.
- **Kho A bị loại bởi content filter:** Gradle không cần truy vấn A cho tọa độ đó; thứ tự chỉ áp dụng lên tập repository còn được phép.

Vì vậy, câu “Gradle luôn thử repo tiếp theo khi repo trước không trả được dependency” là **quá đơn giản và có thể sai**.

## 3. Metadata không phải JAR: vì sao tìm thấy POM trước lại quan trọng?

Một module Maven thường có:

~~~text
com/acme/shared/1.0/
├── shared-1.0.pom       # mô tả module, dependencies, packaging
└── shared-1.0.jar       # artifact nhị phân
~~~

Gradle còn hỗ trợ metadata như **.module** (Gradle Module Metadata) hoặc **ivy.xml** (Ivy descriptor). Metadata có thể nói module có **những dependencies bắc cầu**, variants, khả năng, thuộc tính, danh sách artifacts và thông tin khác.

### 3.1. Trường hợp POM tồn tại nhưng JAR bị thiếu

Giả sử:

| Kho | shared-1.0.pom | shared-1.0.jar |
| --- | --- | --- |
| **A (khai báo trước)** | Có | **Không** |
| **B (khai báo sau)** | Có | Có |

Gradle nhìn thấy metadata ở A, quyết định A là nguồn của module, rồi thử lấy JAR ở A. Việc B có cùng JAR không tự biến B thành nguồn fallback. Build có thể báo **artifact not found**.

**Cách sửa đúng:** hoàn thiện publication ở A, hoặc sửa chính sách để tọa độ này chỉ được phân giải từ B. Không sửa bằng cách thêm **mavenCentral()** hoặc **mavenLocal()** ngẫu nhiên rồi chờ Gradle “bù JAR thiếu”.

### 3.2. Kho A chỉ có JAR, không có POM thì sao?

Trong Maven repository, Gradle mặc định ưu tiên **module metadata**. Việc dùng một JAR rời không có POM không tự động giống hệt module có metadata.

Bạn có thể bật **artifact()** trong **metadataSources** nếu thực sự cần repository artifact-only:

~~~groovy
repositories {
    maven {
        url = uri('https://legacy.example.invalid/maven')
        metadataSources {
            mavenPom()
            artifact()
        }
    }
}
~~~

Tùy chọn **artifact()** làm Gradle có thể coi artifact là nguồn thông tin module nếu metadata theo định dạng khác không có. Tuy nhiên điều này **không tái tạo được toàn bộ thông tin dependencies/variants bị thiếu**. Không bật để che lỗi repository xuất bản POM thiếu hay sai.

**Thứ tự metadata sources** bên trong một repository và **thứ tự các repository khác nhau** là hai vấn đề tách biệt. Gradle có thứ tự và khả năng hỗ trợ metadata formats khác nhau theo loại repository.

### 3.3. Transitive dependencies đi qua bước phân giải riêng

Nếu **com.acme:shared:1.0** khai báo phụ thuộc **org.libs:utility:2.0**, Gradle cần phân giải **utility** như một module khác. Vì vậy:

- shared có thể lấy metadata và JAR từ kho nội bộ.
- utility có thể lấy từ Maven Central nếu kho nội bộ không có và chính sách cho phép.
- Nhưng **POM của shared từ kho A + JAR của shared từ kho B** không phải kết quả bình thường cần mong đợi.

Phân biệt **module source stickiness** với **toàn bộ graph phải đến cùng repository**. Một graph có thể dùng nhiều kho hợp lệ, mỗi module giữ nguồn nhất quán.

## 4. Ngoại lệ quan trọng: dynamic version phải tìm nhiều repository

Dependency với version **cụ thể** khác dependency với **dynamic version**:

~~~groovy
dependencies {
    implementation 'com.acme:shared:1.0'   // Cố định
    // implementation 'com.acme:shared:1.+'  // Dynamic, chỉ minh họa
}
~~~

Với **1.+**, Gradle cần xác định những version thực sự tồn tại. Để làm việc đó, nó có thể kiểm tra **danh sách version ở tất cả repository đủ điều kiện**, không chỉ dừng ở repository đầu tiên trả về metadata cho một version.

Ví dụ:

| Repository | Version có sẵn |
| --- | --- |
| **A** | 1.1, 1.2 |
| **B** | 1.3 |

Khi dùng **1.+**, Gradle có thể chọn **1.3** dựa trên các version nhìn thấy và quy tắc version selection, dù version **1.3** chỉ có ở B và B đứng sau A. Sau khi **version cụ thể 1.3** được chọn, quy tắc chọn metadata/artifact repository của version ấy mới áp dụng.

Đây là lý do **“repo đầu tiên luôn thắng” không đúng cho lựa chọn version động**. Cần tách hai bước:

1. **Chọn version** từ các candidate trên các repository.
2. **Chọn repository nguồn** của module/version đã xác định và lấy artifact tương ứng.

Những yếu tố khác như **conflict resolution**, dependency constraints, strictly/prefer/reject, version ranges và variant selection cũng có thể ảnh hưởng kết quả. **Repository order không phải cơ chế thay thế cho version constraints hoặc dependency locking.**

### 4.1. TTL của dynamic và changing dependencies

Gradle cache kết quả dynamic versions và changing modules, mặc định thường khoảng **24 giờ**. Nếu repository B vừa có version 1.4, môi trường đã cache thông tin cũ có thể chưa thấy nó.

Có thể cấu hình thời gian cache trong một configuration:

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

Đây là ví dụ policy có tác động trên các configuration đang cấu hình, **không phải lời khuyên luôn giảm TTL trong production**: TTL ngắn tăng số lượt tra cứu và có thể giảm khả năng tái lập. Với bản phát hành, ưu tiên **version cố định**, dependency locking/verification và chính sách repositories rõ ràng.

## 5. Kho nào đang có hiệu lực? Đừng nhìn sai repositories block

Gradle có **nhiều scope repository** khác nhau. Một project có thể sử dụng cả plugin, script dependency và application/library dependency.

| Nơi cấu hình | Phục vụ chủ yếu | Ví dụ |
| --- | --- | --- |
| **settings.gradle: pluginManagement { repositories { ... } }** | Phân giải plugin theo **plugins DSL** và plugin marker | Plugin Portal, plugin Maven repo |
| **settings.gradle: dependencyResolutionManagement { repositories { ... } }** | Kho dùng cho dependencies của các project theo repositoriesMode | Kho nội bộ, Maven Central |
| **build.gradle: repositories { ... }** | Dependencies của project khi chính sách cho phép | **implementation**, **testImplementation**, runtime |
| **build.gradle: buildscript { repositories { ... } }** | Dependencies trên classpath của chính build script qua **buildscript.dependencies** | Artifact build tool/plugin cũ |
| **init scripts, convention plugins, included builds** | Có thể thiết lập repository trong scope riêng | Repository policy từ tổ chức hoặc build logic |

**Không nhầm:** thêm **mavenCentral()** trong **project.repositories** không tự làm Gradle tìm thấy plugin trong **plugins { id 'some.plugin' version '...' }**. Plugin resolution cần cấu hình **pluginManagement.repositories** tương ứng.

### 5.1. Plugin repository order là danh sách khác

Trong **settings.gradle**:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Đây là ví dụ xác định nguồn plugin. Plugin DSL có cơ chế phân giải **plugin marker artifact** và các dependency plugin tương ứng; thứ tự và filters trong scope này có ảnh hưởng riêng. Nếu tổ chức có private plugin, cần khai báo repository thích hợp ở đây, không chỉ trong **dependencies repositories**.

Lưu ý **pluginManagement { ... }** thường phải nằm đúng vị trí được Gradle cho phép trong settings script; không được đặt tùy ý sau nhiều statement cấu hình khác.

### 5.2. buildscript.repositories khác project.repositories

Ví dụ dạng cũ:

~~~groovy
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'com.example:build-helper:1.0'
    }
}
~~~

Đây là classpath dependency của script. Nó **không** đồng nghĩa với:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.example:build-helper:1.0'
}
~~~

Nếu bạn phân tích lỗi “could not resolve buildscript classpath”, phải kiểm tra **buildscript.repositories**, không chỉ repository cho **implementation**.

### 5.3. Multi-project và included builds

Mỗi Project có thể có repositories riêng nếu tổ chức chưa tập trung hóa. Một plugin cũng có thể thêm repository. Với **included builds**, hãy kiểm tra settings/build logic riêng vì không nên giả định mọi included build tự động dùng cùng repository policy.

Khi debugging, xác định **configuration nào đang được phân giải**, **project/build nào sở hữu configuration**, rồi mới tìm nơi khai báo repository thực sự có hiệu lực.

## 6. Tập trung repository trong settings.gradle

Ở dự án nhiều module, việc để mỗi **build.gradle** tự thêm repository có thể gây tình trạng module A dùng kho A→B nhưng module B dùng B→A.

Gradle cung cấp **dependencyResolutionManagement** trong **settings.gradle**:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
        maven {
            name = 'companyMirror'
            url = uri('https://repo.company.example.invalid/maven')
        }
    }
}

rootProject.name = 'my-build'
include('app', 'core')
~~~

**Đây là template chính sách**, URL không có thật; phải thay bằng mirror hợp lệ. Khi chọn **FAIL_ON_PROJECT_REPOS**, những repository khai báo trực tiếp ở Project hoặc được project plugin thêm có thể làm build thất bại. Lợi ích là CI và các module áp dụng cùng danh sách do settings quyết định.

### 6.1. Ba giá trị RepositoriesMode

| Chế độ | Cách xử lý | Hệ quả |
| --- | --- | --- |
| **PREFER_PROJECT** | Nếu project có repositories, project repositories được ưu tiên so với settings | **Mặc định**; cấu hình settings không nhất thiết thắng |
| **PREFER_SETTINGS** | Dùng repositories từ settings; project repositories bị bỏ qua/cảnh báo | Thích hợp chuẩn hóa nhưng cần xử lý repository do plugin thêm |
| **FAIL_ON_PROJECT_REPOS** | Khai báo repository ở cấp project tạo lỗi | Policy nghiêm ngặt để không ai lén thêm nguồn khác |

Đặc biệt: **PREFER_PROJECT không có nghĩa Gradle luôn nối settings repositories rồi project repositories thành một danh sách**, sau đó mới áp thứ tự. Khi project khai báo kho, lựa chọn mode quyết định scope nào thực sự được dùng.

### 6.2. Kotlin DSL tương ứng

**settings.gradle.kts**:

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
        maven {
            name = "companyMirror"
            url = uri("https://repo.company.example.invalid/maven")
        }
    }
}

rootProject.name = "my-build"
include("app", "core")
~~~

Kotlin DSL dùng lời gọi **set(...)**, chuỗi kép và cú pháp Kotlin; không được dán nguyên Groovy DSL vào file **.gradle.kts**. Cả hai biểu đạt cùng mục tiêu tập trung hóa.

## 7. Content filtering: chính sách nguồn rõ hơn thứ tự

Đổi thứ tự repository **không đủ** nếu một nhóm dependency **chỉ được phép** xuất phát từ một nguồn. Ví dụ nội bộ **com.company.\*** không được bị truy vấn ở public repository, dù kho nội bộ có lỗi tạm thời.

### 7.1. Filter repository theo group

~~~groovy
repositories {
    maven {
        name = 'privateRepo'
        url = uri('https://repo.company.example.invalid/maven')

        content {
            includeGroup('com.company.internal')
        }
    }

    mavenCentral {
        content {
            excludeGroup('com.company.internal')
        }
    }
}
~~~

Trong ví dụ:

- Private repo chỉ nhận yêu cầu thuộc **group chính xác com.company.internal**.
- Maven Central không nhận yêu cầu thuộc đúng group đó.
- Những module khác có thể được lấy từ Maven Central theo policy.

Đây là **hai filter độc lập**, không phải một lệnh “public tự biết private group”. **includeGroup** khớp chính xác một group; nếu các artifact thuộc **com.company.internal.util** hoặc nhiều group con, cần đưa thêm các group thích hợp hoặc dùng API **includeGroupAndSubgroups** trên Gradle 8.1+.

Bộ lọc có thể dùng:

- **includeGroup**, **excludeGroup**.
- **includeGroupByRegex**, **excludeGroupByRegex**.
- **includeModule(group, name)** và **excludeModule(...)**.
- **includeGroupAndSubgroups** / **excludeGroupAndSubgroups** ở bản Gradle hỗ trợ.

**Một repository có include không ngăn repository khác có cùng module.** Nếu chỉ đặt include ở private repo nhưng để Maven Central không bị filter, module vẫn có thể được yêu cầu ở Central tùy thứ tự và tình huống. Với chính sách nguồn bắt buộc, dùng **exclusiveContent**.

### 7.2. exclusiveContent: nguồn độc quyền cho tọa độ được chọn

Trong **settings.gradle**, ví dụ:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'privateRepo'
                    url = uri('https://repo.company.example.invalid/maven')
                }
            }
            filter {
                includeGroup('com.company.internal')
            }
        }

        mavenCentral()
    }
}
~~~

Ý nghĩa:

1. Module thuộc **com.company.internal** chỉ được tìm ở **privateRepo**.
2. Maven Central không được hỏi về module thuộc group exclusive này, dù kho public đứng trước hoặc sau trong danh sách.
3. Private repo không trở thành nguồn chung cho mọi group khác.
4. Nếu module cần có bị thiếu ở privateRepo, Gradle **không fallback** sang Central; đây là chính sách bảo vệ chủ động.

**Đây thường là lựa chọn tốt hơn việc đặt private repo trước mavenCentral rồi hy vọng source không bao giờ thay đổi.** Nội bộ có thể đặt những group khác nhau ở nhiều kho, nhưng cần quy định group/module ownership rõ ràng.

### 7.3. Transitive dependencies với exclusiveContent

Giả sử module **com.company.internal:engine:1.0** trong privateRepo phụ thuộc **org.slf4j:slf4j-api:2.x**. Dependency bắc cầu này có **group khác**; nó có thể được lấy từ Maven Central nếu policy cho phép. Exclusive content **không ép tất cả transitives của engine phải đến privateRepo**. Nó giới hạn **những tọa độ khớp filter**.

### 7.4. Cẩn trọng với exclusiveContent trong pluginManagement

Khi dùng **exclusiveContent** ở **pluginManagement**, Gradle có thêm ràng buộc: việc bổ sung **buildscript.repositories** từ project có thể trở thành không hợp lệ và gây lỗi configuration. Trước khi triển khai trong repository lớn, cần xác định toàn bộ plugin/buildscript dependency repositories được khai báo ở nơi phù hợp.

Đây là lý do không nên sao chép một block exclusive từ dependencyResolutionManagement sang pluginManagement mà không đọc tài liệu.

## 8. Maven Local, flatDir, mirror và kho nội bộ

### 8.1. mavenLocal() có thể gây “máy tôi chạy, CI lỗi”

Maven Local thường ở **~/.m2/repository** và có thể chứa thư viện do developer vừa publish từ build khác:

~~~groovy
repositories {
    mavenLocal()
    mavenCentral()
}
~~~

Nếu Maven Local chứa metadata **com.acme:shared:1.0**, Gradle có thể chọn metadata đó trước. Nếu JAR ở Local thiếu, không chắc Gradle sẽ lấy artifact từ Maven Central dù Central có bản đầy đủ. Nếu Local có một JAR khác với Central nhưng cùng GAV, developer có thể biên dịch với bytes khác CI.

**Khuyến nghị:** chỉ thêm **mavenLocal()** cho trường hợp phát triển/tích hợp cần thiết, hiểu tác động của thứ tự và giới hạn thời gian sử dụng. Không đặt Maven Local trước kho được kiểm soát trong release pipeline chỉ vì “tiện thử bản mới”.

### 8.2. flatDir không phải Maven repository đầy đủ

~~~groovy
repositories {
    flatDir {
        dirs 'libs'
    }
}
~~~

**flatDir** chỉ nhìn artifact trong một folder theo quy tắc của repository loại này và thiếu metadata transitive/variants như Maven/Ivy/Gradle Module Metadata. Nó không nên là lựa chọn đầu tiên cho dependency quản lý phiên bản nghiêm túc.

Một library được có mặt ở Maven repository với metadata có thể được Gradle ưu tiên hợp lý so với artifact-only repository dù bạn trông đợi “flatDir đứng đầu sẽ luôn thắng”. Hãy dùng repository có metadata đầy đủ hoặc một project dependency khi có source.

### 8.3. Mirror cần chính sách rõ

Kho nội bộ nhiều khi là **mirror/proxy** của Maven Central hoặc Plugin Portal. Hai mô hình khác nhau:

| Mô hình | Ý định | Chính sách |
| --- | --- | --- |
| **Mirror duy nhất** | Tất cả dependency qua proxy được kiểm soát | Chỉ khai báo mirror; đảm bảo mirror có đủ module và metadata |
| **Kho private + Maven Central** | Private có nội bộ, Central có công khai | Content filtering hoặc exclusiveContent cho group nội bộ |
| **Mirror + Central fallback** | Khi module không được mirror cung cấp thì thử Central | Chỉ phù hợp với policy cho phép; không lẫn với sự cố mạng/missing artifact |
| **Kho snapshot + kho release** | Phân tách module thay đổi và bản phát hành | Dùng MavenContent và filter/version phù hợp |

Đặt một mirror trước Central **không đồng nghĩa** “nếu mirror gặp mọi lỗi thì Central tự cứu được”. Kho mirror bị unavailable hoặc trả metadata không có artifact có thể làm resolution thất bại. Mirror cần health checks, chính sách sync, quyền truy cập và khả năng phản hồi metadata/artifact nhất quán.

### 8.4. Khai báo mavenContent theo loại phiên bản

Gradle cung cấp filter riêng cho Maven repositories:

~~~groovy
repositories {
    maven {
        name = 'snapshots'
        url = uri('https://repo.company.example.invalid/snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }

    maven {
        name = 'releases'
        url = uri('https://repo.company.example.invalid/releases')
        mavenContent {
            releasesOnly()
        }
    }
}
~~~

Các filter này giảm những truy vấn không cần thiết khi backend tách snapshot/release. Chúng **không thay thế** xác định group ownership: với module nội bộ nhạy cảm, vẫn cần giới hạn nơi một group được tìm.

## 9. Dependency cache, repository stickiness và hiệu ứng khi đổi thứ tự

Một kết quả resolution không phụ thuộc duy nhất vào **danh sách repository hiện tại**. Gradle cache:

- metadata module và artifact đã tải,
- kết quả chọn version động,
- kết quả không tìm thấy module/artifact tại một repository,
- thông tin repository gốc của từng module,
- timestamp/TTL của entry.

Cache dependency thường nằm trong **GRADLE_USER_HOME/caches/modules-2/**. Nó khác với **build/** và khác **build cache** lưu outputs của task.

### 9.1. Vì sao đổi thứ tự nhưng JAR chưa đổi?

Gradle ghi nhận nguồn đã dùng để phân giải module. **Repository stickiness** nghĩa là Gradle tránh tự ý chuyển cùng module sang repository khác trong những trường hợp cache đã gắn nó với một nguồn cụ thể, giúp tránh dùng binary khác mà bạn không nhận ra.

Vì vậy, thử nghiệm:

1. Hôm qua dùng repo A trước, module tải từ A.
2. Hôm nay đổi repo B lên trước.
3. Trên máy cũ vẫn có cache origin của A, còn máy CI mới có cache lạnh.

Kết quả có thể không giống nhau ngay cả khi build script đang hiển thị cùng thứ tự mới. **Không dùng sự khác nhau này để kết luận Gradle “bỏ qua thứ tự”**. Hãy xét **cache và nguồn đã được gắn**.

### 9.2. --refresh-dependencies làm gì?

~~~bash
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

**--refresh-dependencies** yêu cầu Gradle tái kiểm tra metadata/artifacts theo chính sách, nhưng **không có nghĩa mọi JAR nhất định bị tải lại**. Gradle có thể kiểm tra checksum hoặc thông tin từ server để tái sử dụng byte đã có. Nó cũng không thay thế việc sửa policy nếu kho được chọn chứa metadata nhưng thiếu JAR.

**Không vội xóa toàn bộ ~/.gradle/caches** để debug một dependency. Hãy kiểm tra repository order, filters, origin, TTL và chạy refresh có chủ đích trước. Xóa cache toàn cục gây tải lại nhiều thư viện, khó tái hiện và có thể ảnh hưởng các project khác.

### 9.3. --offline làm gì?

~~~bash
./gradlew dependencies --configuration runtimeClasspath --offline
~~~

**--offline** hạn chế phân giải vào dữ liệu đã cache; nếu một module chưa có trong cache, build có thể thất bại dù repository còn hoạt động. Nó không biến Gradle thành một bộ chọn “không cần repository”. Khi debug thứ tự, **offline không phải cách chứng minh kho nào sẽ được hỏi ở lần phân giải mạng mới**.

### 9.4. Thử nghiệm hai cache độc lập

Để so sánh **repo A trước** với **repo B trước** công bằng, dùng **hai môi trường dependency cache độc lập** hoặc những bản CI sạch được kiểm soát. Gradle hỗ trợ:

~~~bash
./gradlew --gradle-user-home .gradle-home-a clean run
~~~

và sau khi đổi thứ tự:

~~~bash
./gradlew --gradle-user-home .gradle-home-b clean run
~~~

Lưu ý: Gradle Wrapper có thể phải tải/khởi tạo distribution trong mỗi Gradle User Home mới nếu nó chưa được cache; bước chuẩn bị Wrapper có thể yêu cầu kết nối mạng dù dependencies của project chỉ ở local repositories. Ví dụ này chủ yếu nhằm cô lập **dependency cache origin**.

## 10. Thực hành hoàn chỉnh: hai Maven repositories cùng GAV, JAR khác nhau

Phần này là một **lab chạy được bằng Java 17+ và Gradle Wrapper hợp lệ**, mô tả điều gì xảy ra khi thứ tự repository thay đổi. Không dùng thư viện bên ngoài; các Maven repositories là **folder cục bộ** do một chương trình Java tạo ra.

### 10.1. Cây project

Tạo thư mục mới:

~~~text
repository-order-lab/
├── settings.gradle
├── build.gradle
├── FixtureRepositories.java
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/demo/App.java
└── lab-repos/                     # sẽ được tạo bằng chương trình Java
    ├── first/demo/origin/1.0/
    │   ├── origin-1.0.pom
    │   └── origin-1.0.jar
    └── second/demo/origin/1.0/
        ├── origin-1.0.pom
        └── origin-1.0.jar
~~~

**gradlew/gradlew.bat và gradle/wrapper** phải đến từ Wrapper hợp lệ, không tự tạo JAR bằng tay. Dùng Gradle đã được cài hoặc một project có Wrapper để khởi tạo nếu cần.

Hai repository cung cấp **cùng tọa độ Maven demo:origin:1.0**, nhưng class **demo.Origin** có **repository()** trả về hai giá trị khác nhau: **FIRST** và **SECOND**. Đây là **bài lab có chủ ý** tạo xung đột, không phải cách xuất bản release production.

### 10.2. settings.gradle

~~~groovy
rootProject.name = 'repository-order-lab'
~~~

### 10.3. Chương trình tạo Maven repository cục bộ

Tạo file **FixtureRepositories.java** ở root:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class FixtureRepositories {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Chạy bằng JDK 17+, không phải JRE");
        }

        createRepository(compiler, "first", "FIRST");
        createRepository(compiler, "second", "SECOND");
        System.out.println("Generated: first and second");
    }

    private static void createRepository(
            JavaCompiler compiler, String name, String label
    ) throws IOException {
        Path temp = Path.of("lab-fixtures", name);
        Path source = temp.resolve("src/demo/Origin.java");
        Path classes = temp.resolve("classes");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        String javaSource =
                "package demo;\n" +
                "public final class Origin {\n" +
                "  public static String repository() { return \"" + label + "\"; }\n" +
                "}\n";
        Files.writeString(source, javaSource, StandardCharsets.UTF_8);

        int exit = compiler.run(
                null, null, null,
                "--release", "17",
                "-d", classes.toString(),
                source.toString()
        );
        if (exit != 0) {
            throw new IOException("javac failed for " + name);
        }

        Path destination = Path.of(
                "lab-repos", name, "demo", "origin", "1.0"
        );
        Files.createDirectories(destination);

        String pom = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>demo</groupId>
                  <artifactId>origin</artifactId>
                  <version>1.0</version>
                  <packaging>jar</packaging>
                </project>
                """;
        Files.writeString(
                destination.resolve("origin-1.0.pom"),
                pom,
                StandardCharsets.UTF_8
        );

        Path jarFile = destination.resolve("origin-1.0.jar");
        try (JarOutputStream jar =
                     new JarOutputStream(Files.newOutputStream(jarFile))) {
            JarEntry entry = new JarEntry("demo/Origin.class");
            jar.putNextEntry(entry);
            Files.copy(classes.resolve("demo/Origin.class"), jar);
            jar.closeEntry();
        }
    }
}
~~~

Giải thích chương trình:

- Dùng **JavaCompiler** từ JDK 17+ để biên dịch **demo.Origin**; không cần tải thư viện build.
- Với **first**, code biên dịch trả **FIRST**; với **second**, trả **SECOND**.
- Tạo POM tối thiểu tại đường dẫn Maven chuẩn **demo/origin/1.0/origin-1.0.pom**.
- Đóng gói class vào file **origin-1.0.jar** bằng **JarOutputStream**.
- Hai POM mô tả cùng module/version, hai JAR chứa cùng tên class nhưng bytecode khác.

Chạy tại root bằng lệnh dùng được trên Linux/macOS/Windows có JDK 17+:

~~~bash
javac FixtureRepositories.java
java FixtureRepositories
~~~

Dòng stdout cuối chương trình:

~~~text
Generated: first and second
~~~

Có thể nhìn thấy thêm lỗi của trình biên dịch nếu JDK không đúng hoặc thư mục không cho phép ghi; khi chạy thành công, lệnh tạo hai cây **lab-repos/** tương ứng.

### 10.4. build.gradle khai báo first trước second

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'firstLocal'
        url = uri('lab-repos/first')
    }
    maven {
        name = 'secondLocal'
        url = uri('lab-repos/second')
    }
}

dependencies {
    implementation 'demo:origin:1.0'
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**application** là Gradle core plugin, không cần plugin bên ngoài. Dependencies được phân giải từ **Maven repositories nằm trên filesystem**; việc cài đặt Wrapper hoặc JDK toolchain có thể có yêu cầu môi trường riêng như đã nêu.

Cả hai folder Maven chứa metadata và JAR của **demo:origin:1.0**. Khi cache chưa có origin cũ và **firstLocal** đứng trước, Gradle chọn module này từ **firstLocal**.

### 10.5. src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("Loaded: " + Origin.repository());
    }
}
~~~

File **App.java** được biên dịch bởi Java plugin, còn **Origin** đến từ dependency **demo:origin:1.0**.

### 10.6. Chạy lần đầu

Linux/macOS:

~~~bash
./gradlew clean run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean run
~~~

Trong môi trường phân giải mới với **firstLocal** là nguồn được chọn, stdout của **App** là:

~~~text
Loaded: FIRST
~~~

Gradle còn in tên task và thông báo build; dòng trên là stdout duy nhất mà class **App** chủ động in.

**Cách diễn giải:** dù **secondLocal** cũng có class demo.Origin, Gradle không so sánh hai JAR để chọn “bản tốt hơn”. Nó dùng metadata của firstLocal theo thứ tự, rồi lấy JAR của module từ cùng kho.

### 10.7. Đảo thứ tự và thử bằng cache khác

Sửa duy nhất thứ tự trong **build.gradle**:

~~~groovy
repositories {
    maven {
        name = 'secondLocal'
        url = uri('lab-repos/second')
    }
    maven {
        name = 'firstLocal'
        url = uri('lab-repos/first')
    }
}
~~~

**Giữ nguyên** dependency **implementation 'demo:origin:1.0'**, không cần thay App.

Với cache resolution mới/độc lập, stdout dự kiến:

~~~text
Loaded: SECOND
~~~

Nếu đổi thứ tự nhưng trên máy hiện tại vẫn thấy FIRST, kiểm tra **dependency cache origin**, thử **--refresh-dependencies** có chủ đích hoặc dùng một **Gradle User Home độc lập**. **Không kết luận rằng Gradle luôn tự chuyển repo khi đảo thứ tự trên cache cũ.**

**Bài lab cần hai giai đoạn**:
- First case: firstLocal trước secondLocal, chạy trong môi trường resolution mới → **Loaded: FIRST**.
- Second case: secondLocal trước firstLocal, chạy trong môi trường resolution mới khác → **Loaded: SECOND**.

Chỉ một câu lệnh **clean** không xóa dependency cache origin, nên không đủ để tái hiện chắc chắn tác động thứ tự.

### 10.8. Kiểm chứng “POM ở A nhưng JAR thiếu”

Đây là biến thể trên **fixture lab riêng**, không thực hiện trên repository production:

1. Dùng thứ tự **firstLocal** trước secondLocal.
2. Giữ **lab-repos/first/demo/origin/1.0/origin-1.0.pom**.
3. Tạm chuyển file **origin-1.0.jar** của first ra ngoài folder repository, vẫn giữ JAR của second.
4. Chạy resolve ở **môi trường cache mới**.

Kết quả **đáng kỳ vọng**: Gradle nhận metadata module từ first nhưng không tìm được JAR ở đó nên lỗi phân giải; nó không lấy JAR ở second để “bù”. Sau bài tập, **khôi phục JAR fixture** hoặc chạy lại **java FixtureRepositories**.

**Tại sao nhấn mạnh cache mới?** Nếu cache đã chứa JAR hợp lệ của first, Gradle có thể sử dụng dữ liệu cache và bạn sẽ không thật sự kiểm tra tình huống missing artifact. Không dựa vào test xóa file repository đơn lẻ khi cache vẫn nóng.

### 10.9. Biến thể exclusiveContent trên local repositories

Có thể chủ động khóa module group **demo** vào secondLocal, kể cả khi firstLocal đứng trước:

~~~groovy
repositories {
    maven {
        name = 'firstLocal'
        url = uri('lab-repos/first')
    }

    exclusiveContent {
        forRepository {
            maven {
                name = 'secondLocal'
                url = uri('lab-repos/second')
            }
        }
        filter {
            includeGroup('demo')
        }
    }
}
~~~

Với cache mới, **demo:origin:1.0** được lấy từ **secondLocal** vì **group demo** đã thuộc riêng repository đó. Đây là bằng chứng rằng **content policy có thể quan trọng hơn thứ tự các kho còn lại**.

Không thêm **mavenCentral()** để bài lab chạy: cả hai repository đã nằm trên máy, đủ metadata và artifact.

## 11. Kiểm tra kết quả resolution bằng công cụ Gradle

### 11.1. Xem dependency graph của một configuration

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Với ví dụ lab, trong graph cần thấy module **demo:origin:1.0**. Báo cáo **dependencies** chủ yếu cho biết **các module/version đã được chọn**, không phải lúc nào cũng trực tiếp in URL repository đã cung cấp JAR. Muốn xác nhận nguồn, hãy kiểm tra **--info/--debug**, kết quả từ lab, hoặc quan sát luồng request có kiểm soát.

### 11.2. dependencyInsight giải thích vì sao version được chọn

~~~bash
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency demo:origin
~~~

Windows PowerShell viết một dòng để tránh khác biệt line continuation:

~~~powershell
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency demo:origin
~~~

**dependencyInsight** hữu ích cho version conflict, constraint và lý do chọn variant/module. Nó không thay thế việc kiểm tra **repository provenance** khi hai kho chứa cùng tọa độ và cùng version nhưng khác bytes.

### 11.3. --info và --debug

~~~bash
./gradlew compileJava --info --refresh-dependencies
~~~

Với trường hợp khó, có thể dùng:

~~~bash
./gradlew compileJava --debug
~~~

**--debug** rất nhiều log, có thể bao gồm chi tiết URL và thông tin liên quan môi trường. Không chia sẻ log thô nếu nó chứa endpoint nội bộ, headers hoặc credentials. Nên lấy phần liên quan tới dependency cụ thể, che dữ liệu nhạy cảm trước khi gửi hỗ trợ.

### 11.4. Kiểm tra bằng môi trường sạch hoặc CI

Để xác định thứ tự mà không bị cache cũ che phủ:

- Chạy với một **GRADLE_USER_HOME** mới dành riêng cho lab (có thể phát sinh tải Gradle distribution).
- Giữ nguyên Wrapper, JDK, settings, repositoriesMode và dependency declarations giữa hai lần.
- Dùng cùng một **fixed version** và cùng file POM/JAR fixture.
- Xác định nội dung JAR được chọn bằng hành vi **Origin.repository()**, không chỉ tên file (cả hai JAR cùng tên).
- Với production, nên kiểm tra thêm SHA-256 hoặc dependency verification metadata thay vì chỉ dựa vào console output.

### 11.5. Không dùng build scan như bằng chứng duy nhất khi quyền riêng tư quan trọng

Một số công cụ báo cáo build có thể chứa thông tin về dependency graph, repositories hoặc endpoints. Nếu dùng build scan/DPE theo chính sách tổ chức, kiểm tra cấu hình chia sẻ dữ liệu và không đăng tải URL/private coordinates ra dịch vụ không được phê duyệt.

## 12. Bảo mật: repository order và dependency confusion

Giả sử bạn có module nội bộ **com.company.internal:payments-sdk:1.0**, nhưng build khai báo:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.company.example.invalid/maven')
    }
}
~~~

Nếu một nhóm tọa độ đáng lẽ chỉ tồn tại ở private repo xuất hiện trên public repo trước và không được filter, Gradle có nguy cơ chọn module từ nguồn không mong muốn. Ngoài ra, việc hỏi public repo về tên module nội bộ có thể làm rò rỉ **coordinates**.

Các rủi ro cần phân biệt:

1. **Repository shadowing:** một module cùng GAV từ kho đứng trước thay thế nguồn mong muốn.
2. **Dependency confusion:** package mang tên/tọa độ nội bộ được công bố ở môi trường public hoặc kho không tin cậy và vô tình được chọn.
3. **Metadata/artifact mismatch:** metadata ở kho đã chọn nhưng artifact không đầy đủ hoặc không tương ứng.
4. **Credential leakage:** cấu hình logging/URL hoặc script làm lộ token repository.
5. **Non-reproducible dependencies:** cùng version nhưng bytes khác nhau giữa local, mirror, cache và CI.

**Biện pháp phòng ngừa theo thứ tự ưu tiên**:

- **exclusiveContent** cho group/module cần nguồn độc quyền.
- **content filters** cho mọi repository khi nhiều nguồn tồn tại.
- **repositoriesMode = FAIL_ON_PROJECT_REPOS** để tránh plugin/subproject âm thầm thêm nguồn khác.
- **HTTPS và credential providers**; không hardcode username/password/token trong Git.
- **Dependency verification** bằng checksum/signature được review từ nguồn tin cậy.
- **Fixed versions**, dependency locking/constraints cho reproducibility; hạn chế version động trong release.
- Hạn chế **mavenLocal()** trong CI và tránh dùng kho thử nghiệm làm nguồn production.
- Theo dõi availability của private repo/mirror thay vì phụ thuộc vào fallback thiếu kiểm soát.

### 12.1. Credentials và URL: không đưa secret vào DSL

Ví dụ tư duy cho kho cần xác thực:

~~~groovy
repositories {
    maven {
        name = 'company'
        url = uri('https://repo.company.example.invalid/maven')
        credentials(PasswordCredentials)
    }
}
~~~

Đoạn này chỉ là **minh họa API**, cần cung cấp credential properties qua môi trường/secret store đúng theo cơ chế Gradle và tên repository thật. **Đừng đưa mật khẩu vào URL** hoặc commit nó trong **gradle.properties** của repository.

Đặt repository HTTPS và bảo vệ credentials không đảm bảo module đến đúng kho nếu bạn vẫn mở public fallback không kiểm soát; authentication và **content routing** giải quyết hai lớp vấn đề khác nhau.

### 12.2. Dependency verification khác với khóa repository

Gradle có file **gradle/verification-metadata.xml** để lưu những checksum/signature kỳ vọng. Với phiên bản bất biến và chính sách xác thực đúng, verification giúp phát hiện bytes bất thường.

Tuy nhiên:

- **exclusiveContent** quyết định **nơi được phép lấy module**.
- **dependency locking** kiểm soát **version được chọn**.
- **dependency verification** kiểm tra **artifact/metadata được nhận**.
- Chúng là các biện pháp **bổ sung**, không thay thế lẫn nhau.

Khi bootstrap verification metadata, cần review checksum và provenance: việc tự ghi lại checksum của một binary đã bị tấn công không biến nó thành đáng tin cậy.

## 13. Các trường hợp lỗi điển hình

| Hiện tượng | Nguyên nhân khả dĩ | Hành động đúng |
| --- | --- | --- |
| **Could not find group:name:version** | Không repository nào đủ điều kiện chứa module; group filter quá chặt; repositoriesMode bỏ qua repository mong đợi | Xác định configuration/scope, đọc nguồn effective, kiểm tra tọa độ, policy và metadata |
| Có POM trong repo A nhưng JAR nằm repo B | Gradle đã chọn A khi thấy metadata | Sửa publication A hoặc routing cho module sang đúng repository; không mong tự trộn nguồn |
| Đảo thứ tự mà dependency vẫn lấy bản cũ | Origin stickiness/metadata cache, build outputs hoặc policy khác | Dùng cache độc lập cho thử nghiệm, kiểm tra --refresh-dependencies và filters |
| Maven Local làm dev khác CI | Local có bản GAV khác hoặc POM/JAR thiếu | Loại mavenLocal khỏi release, thử môi trường sạch, kiểm tra artifact checksum |
| Maven Central có cùng group nội bộ | Public repo được hỏi hoặc được ưu tiên | exclusiveContent cho group nội bộ, chặn public tìm group đó |
| Plugin không tìm thấy nhưng implementation resolve được | Plugin repositories khác project repositories | Kiểm tra **pluginManagement.repositories** |
| buildscript dependency không resolve | **buildscript.repositories** thiếu kho | Kiểm tra buildscript block và chính sách plugin |
| Kho A 500/timeout nên Gradle không dùng B | Lỗi mạng không phải not-found | Kiểm tra availability/auth/proxy, không dựa vào fallback im lặng |
| Gradle không thấy version mới dù repo đã publish | Dynamic/changing cache TTL | Xác nhận version request; kiểm tra TTL và --refresh-dependencies |
| Chỉ mavenLocal chứa jar nhưng không thấy transitive deps | Artifact-only/metadata thiếu | Dùng repository Maven chuẩn có POM/module metadata đầy đủ |
| Repo filter include group nhưng public vẫn được truy vấn | Filter ở một repo không ảnh hưởng repo khác | Thêm exclude tương ứng hoặc dùng exclusiveContent |
| Settings đã khai báo Central nhưng project lại dùng repo khác | **PREFER_PROJECT** làm project repositories thắng | Xem repositoriesMode; cân nhắc PREFER_SETTINGS/FAIL_ON_PROJECT_REPOS |
| build vẫn thành công khi cache đã nóng nhưng CI lỗi | Cache local che việc thiếu module/artifact | Tái hiện môi trường clean, kiểm tra repository origin/publishing |
| Có nhiều versions và dependency được nâng ngoài ý muốn | Dynamic version hoặc conflict resolution | Dùng version cố định, dependency locking, dependencyInsight |
| 401/403 ở private repository | Credential/permission sai | Kiểm tra secret store, URL, identity và access policy; không log secrets |

### 13.1. Quy trình debug theo thứ tự

1. **Phân loại dependency**: plugin, buildscript hay project dependency?
2. **Xác định configuration**: compileClasspath, runtimeClasspath, testRuntimeClasspath, classpath khác?
3. **Đọc policy có hiệu lực**: settings **dependencyResolutionManagement**, repositoriesMode, project repositories, filter/exclusive.
4. **Xác định GAV** và là **fixed** hay **dynamic/changing**.
5. **Kiểm tra metadata và artifact của repository được chọn**; đừng chỉ nhìn JAR ở kho khác.
6. **Kiểm tra lỗi mạng**: 404 khác 401/403/5xx, timeout và proxy.
7. **Kiểm tra cache origin**: local/CI, TTL, offline, refresh.
8. **Kiểm tra dependencyInsight** cho vấn đề version/variant, so sánh bytes/checksum khi nghi shadowing.
9. **Sửa chính sách tại nguồn**: mapping group→repo, quyền truy cập, publication, lock/verification; chỉ dùng cache mới để thử nghiệm có kiểm soát.

## 14. Best practices cho dự án Java nhiều module

Một policy tốt cần thể hiện rõ **ai sở hữu repository list** và **group nào đến từ nguồn nào**.

### 14.1. Mẫu kiến trúc repository đề xuất

~~~text
settings.gradle
├── pluginManagement.repositories
│   ├── plugin mirror đã kiểm soát
│   └── plugin portal (nếu policy cho phép)
└── dependencyResolutionManagement
    ├── repositoriesMode = FAIL_ON_PROJECT_REPOS
    └── repositories
        ├── exclusiveContent: group nội bộ -> private repo
        └── mavenCentral(): modules public
build.gradle / modules
└── dependencies { implementation ... }
    (không tự thêm repository)
~~~

Kiến trúc này giúp giảm khác biệt giữa các module. Khi có một artifact nội bộ mới, thường chỉ cần publish đúng repository thuộc group đó; không cần cho từng module tự thêm URL repository.

### 14.2. Checklist trước khi merge thay đổi repositories

- Thứ tự repository có mục đích và được review chưa?
- Có repository public nào đang nhận request chứa tên module nội bộ không?
- **mavenLocal()**, flatDir hoặc test repository có vô tình nằm trong release path không?
- Nếu kho A có metadata nhưng thiếu artifact, build có lỗi có thể hành động được không?
- Có khai báo **content filters/exclusiveContent** cho những group cần nguồn cố định không?
- Dependency có dùng **fixed version** và khóa version nếu cần không?
- Verification metadata có được tạo và review đúng cách không?
- RepositoriesMode có loại trừ repository do plugin/subproject tự thêm không?
- Plugin repositories và buildscript repositories có được xem riêng khỏi project dependencies không?
- Có test với **cache lạnh** để tránh kết quả cũ che policy mới không?
- Có giám sát mirror/private repo không? Lỗi 5xx/401/403 có được phân biệt với module missing không?
- CI và local dùng cùng Wrapper, settings, policy và credentials được cấp quyền thích hợp không?

## 15. Bài tập tự kiểm tra có đáp án

### Bài 1 — Một module, hai kho

A và B đều có metadata và JAR của **demo:origin:1.0**. A đứng trước B, môi trường cache mới, không filter.

**Đáp án:** Gradle tìm metadata ở A trước và lấy artifact module từ A. B không được dùng để “so sánh nội dung JAR”. Trong lab mục 10, ứng dụng in **Loaded: FIRST**.

### Bài 2 — POM ở A, JAR chỉ ở B

A đứng trước B, cả hai có POM, chỉ B có JAR.

**Đáp án:** phân giải có thể thất bại khi lấy artifact ở A, không tự fallback sang JAR cùng module ở B. Cần sửa publication hoặc định tuyến đúng repository trước khi resolve.

### Bài 3 — Dynamic 1.+

A có version 1.2, B có version 1.3; dependency **1.+**.

**Đáp án:** Gradle có thể xem version ở nhiều repository để chọn candidate phù hợp, nên không được mặc định version 1.2 thắng chỉ vì A đứng trước. Sau khi version cụ thể được chọn, áp dụng quy tắc module/metadata.

### Bài 4 — Có group private nhưng mavenCentral đứng trước

**Hỏi:** Có an toàn chỉ đổi private repo lên đầu rồi giữ nguyên public repo nhận mọi group không?

**Đáp án:** chưa đủ. Public repo vẫn có thể được hỏi về module nội bộ trong những tình huống nhất định. Nên dùng **exclusiveContent** hoặc filter phối hợp và giới hạn quyền truy cập.

### Bài 5 — project và settings khai báo repositories khác nhau

Settings có Central; Project có private repo; mode mặc định.

**Đáp án:** chế độ mặc định **PREFER_PROJECT** cho phép project repositories thắng settings trong ngữ cảnh có project declaration. Nếu cần mọi module dùng nguồn thống nhất, cấu hình **FAIL_ON_PROJECT_REPOS** và chuyển repo hợp lệ về settings.

### Bài 6 — --refresh-dependencies có xóa hết JAR?

**Đáp án:** không. Gradle có thể xác minh checksum và tái sử dụng bytes còn hợp lệ; flag buộc tái kiểm tra resolution, không phải luôn download mọi artifact.

### Bài 7 — Phân biệt loại lỗi

Kho A trả **404 module not found**; kho B có module. Khác gì A trả **HTTP 500**?

**Đáp án:** không tìm thấy module ở A thường cho phép thử B; lỗi server khiến Gradle có thể disable/fail repository theo cơ chế retry và thường không fallback một cách im lặng. Phải điều tra availability chứ không coi hai phản hồi như nhau.

### Bài 8 — Tại sao lab chạy trong cùng GRADLE_USER_HOME có thể gây nhầm?

**Đáp án:** dependency cache ghi origin/repository stickiness và dữ liệu module đã giải quyết. Đổi thứ tự mà dùng cùng cache có thể không cho thấy ngay JAR khác. Cần môi trường resolution độc lập, giữ các điều kiện khác như nhau.

## Tài liệu chính thức của Gradle

- [Declaring Repositories — Advanced](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html): thứ tự repository và chọn nơi lấy artifact khi tìm thấy metadata.
- [Dependency Graph Resolution](https://docs.gradle.org/current/userguide/dependency_graph_resolution.html): metadata retrieval, dynamic version đi qua nhiều kho, module version cụ thể và lỗi repository.
- [Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): tách plugin repositories khỏi dependency repositories.
- [Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): dependencyResolutionManagement và RepositoriesMode.
- [Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html): include/exclude, exclusiveContent, Maven-specific filters.
- [Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): group ownership, dependency confusion, giảm rò rỉ tọa độ nội bộ.
- [Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): sticky repository source, cache, offline, refresh và TTL.
- [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum và chữ ký artifact.
- [Maven Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html): repository types, mavenLocal, flatDir và local repositories.

**Kết luận:** thứ tự repository quyết định nơi Gradle tìm **metadata của module có version cụ thể**, và khi đã chọn nguồn, artifact của module được lấy từ **nguồn ấy**. Nhưng thứ tự không đủ để bảo đảm an toàn: dynamic versions có cơ chế dò nhiều repo, cache giữ lịch sử nguồn và mỗi scope có repository riêng. Muốn kết quả **dễ kiểm chứng, nhất quán giữa local/CI và chống dependency confusion**, hãy kết hợp **repository policy tập trung + content/exclusive filters + version locking/verification + kiểm thử cache lạnh**.
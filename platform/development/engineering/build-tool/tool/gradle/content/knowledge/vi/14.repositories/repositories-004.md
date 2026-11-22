# Vai trò của Maven Central, Google Maven, kho nội bộ và mavenLocal trong Gradle

## 1. Vì sao một dự án cần nhiều kho thư viện?

Một dự án Java hiếm khi chỉ dùng mã do nhóm tự viết. Nó có thể phụ thuộc thư viện logging, JSON, testing, HTTP, Spring, AndroidX hoặc những module riêng của công ty. Gradle phải tìm đúng **tọa độ thư viện**, lấy metadata để biết quan hệ phụ thuộc, tải artifact tương ứng và đặt chúng vào classpath của task cần sử dụng.

Nơi Gradle tìm các thành phần đó được gọi là **repository** (kho thư viện). Với các thư viện phát hành theo định dạng Maven, bốn nguồn thường gặp là:

- **Maven Central:** kho công khai lớn cho thư viện Java/JVM và nhiều hệ sinh thái liên quan.
- **Google Maven:** kho Maven của Google, đặc biệt quan trọng đối với Android/AndroidX và một số thành phần của hệ sinh thái Google.
- **Kho Maven nội bộ:** kho do tổ chức quản lý, chứa thư viện riêng hoặc hoạt động như proxy/cache có chính sách truy cập.
- **`mavenLocal()`:** tham chiếu tới kho Maven trên máy người phát triển, thường nằm dưới `~/.m2/repository`, hữu ích khi thử một artifact vừa build/publish cục bộ.

Đừng hiểu một kho như một **dependency**. Một kho là **nơi tìm**, còn một dependency là **thứ cần tìm**. Ví dụ `org.apache.commons:commons-lang3:3.14.0` là tọa độ của một thư viện; `mavenCentral()` là chỉ dẫn cho Gradle biết một nguồn có thể chứa artifact theo tọa độ đó.

Mô hình:

```text
build.gradle / build.gradle.kts
   |
   +--> dependencies { implementation("group:name:version") }
   |
   v
Gradle dependency resolution
   |
   +--> Maven Central         (thư viện công khai)
   +--> Google Maven          (Android/Google artifacts)
   +--> Maven nội bộ          (module riêng hoặc proxy)
   +--> Maven Local           (artifact đã cài ở máy này)
   |
   v
Metadata + artifact + dependency graph
   |
   v
compileClasspath / runtimeClasspath / testRuntimeClasspath ...
   |
   v
compileJava, test, run, jar và những task tiêu thụ dependency
```

Bài này phân biệt nhiệm vụ của bốn loại kho, cách cấu hình bằng Groovy/Kotlin DSL, thứ tự tìm kiếm, cache, xác thực, khả năng tái lập build và quy trình chẩn đoán khi không tải được một dependency.

## 2. Kho Maven chứa những gì? Tọa độ và metadata

Một dependency Maven thường được nhận diện bởi ba thành phần chính:

```text
group : artifact : version
```

Ví dụ:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

- `group`: nhóm định danh nhà phát hành hoặc tổ chức, ví dụ `org.apache.commons`.
- `artifact`: tên module, ví dụ `commons-lang3`.
- `version`: phiên bản cụ thể, ví dụ `3.14.0`.

Kho Maven thường sắp xếp artifact theo đường dẫn suy ra từ tọa độ:

```text
org/apache/commons/commons-lang3/3.14.0/
├── commons-lang3-3.14.0.pom
└── commons-lang3-3.14.0.jar
```

Đây là sơ đồ mô tả cách tổ chức thông thường; một phiên bản có thể có thêm tài liệu, source JAR, checksum hoặc metadata khác. File `.pom` chứa thông tin dự án và có thể khai báo các dependency đi kèm. Gradle cũng có thể dùng Gradle Module Metadata (`.module`) khi repository và module cung cấp, để biểu diễn biến thể/thuộc tính phong phú hơn POM.

**Không phải mọi tọa độ đều đi kèm một JAR chính.** Một module có thể là BOM, POM-only hoặc sản phẩm đóng gói theo định dạng khác. Gradle giải quyết dependency dựa trên metadata, yêu cầu biến thể và cấu hình, chứ không chỉ ghép URL tới `.jar`.

Ví dụ một thư viện có dependency gián tiếp:

```text
application
   |
   +--> library-A:1.0
          |
          +--> library-B:2.1
```

Gradle cần metadata của `library-A` để biết nó phụ thuộc `library-B`, rồi tìm artifact cần thiết. Vì vậy repository không chỉ là nơi tải file nhị phân; nó còn là **nguồn thông tin về cấu trúc dependency graph**.

### 2.1. Tọa độ không nói kho nào đang dùng

`implementation("group:name:version")` không tự chứa URL Maven Central hay kho nội bộ. Việc chọn kho dựa trên cấu hình repository của build và các chính sách khác.

Hai module có tọa độ cùng kiểu có thể nằm ở hai kho khác nhau: `commons-lang3` ở Maven Central, còn `com.example.internal:pricing-api:1.2.0` có thể chỉ tồn tại trong kho công ty. Nếu quên khai báo kho phù hợp, Gradle không thể tự đoán URL nội bộ.

### 2.2. Maven repository khác flat directory hoặc Ivy repository

Gradle cũng hỗ trợ các loại repository khác như Ivy và flat-directory. Bài này tập trung các **kho theo định dạng Maven**. Đừng đồng nhất thuật ngữ “Gradle có repository” với “mọi repository đều có POM và cấu trúc Maven giống nhau”.

## 3. Maven Central: nguồn phổ biến của thư viện Java/JVM công khai

Cách khai báo thường thấy trong `build.gradle` bằng Groovy DSL:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Kotlin DSL:

```kotlin
repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Maven Central là lựa chọn hợp lý cho nhiều thư viện mã nguồn mở của Java, Kotlin/JVM, kiểm thử và công cụ. Gradle có thể sử dụng nó để tải cả module trực tiếp lẫn các dependency bắc cầu được khai báo trong metadata.

**Những điều không nên hiểu sai:**

1. **Java plugin không tự biến Maven Central thành kho dependency cho mọi dự án.** Repository cần được khai báo trong project hoặc trong chính sách repository ở mức settings, hoặc được cung cấp bởi cấu hình khác.
2. Maven Central không nhất thiết chứa thư viện nội bộ của công ty.
3. Một thư viện có tên group bắt đầu bằng `com.google` không có nghĩa bắt buộc nằm ở Google Maven; hãy kiểm tra nơi nhà phát hành thực sự công bố artifact.
4. Chỉ thêm `mavenCentral()` không chứng minh dependency tải thành công. Tên/phiên bản có thể sai, mạng không hoạt động hoặc metadata yêu cầu biến thể không phù hợp.
5. Maven Central là một **nguồn phân phối**, không thay thế quy trình đánh giá giấy phép, rủi ro bảo mật và chính sách cho phép sử dụng thư viện của tổ chức.

Với thư viện Java chung, cách cấu hình tối thiểu thường là `mavenCentral()` + khai báo dependency bằng tọa độ cố định. Sau khi giải quyết thành công, Gradle lưu thông tin/artefact trong cache dependency cục bộ để những lần chạy sau không nhất thiết cần tải lại mọi file.

## 4. Google Maven: nguồn quan trọng đối với hệ sinh thái Android

Gradle cung cấp cách khai báo ngắn:

```groovy
repositories {
    google()
    mavenCentral()
}
```

Hoặc bằng Kotlin DSL:

```kotlin
repositories {
    google()
    mavenCentral()
}
```

`google()` thêm repository Maven do Google cung cấp. Nó đặc biệt quan trọng khi build Android, vì nhiều artifact AndroidX và thành phần liên quan Android được xuất bản tại đó.

Ví dụ dependency AndroidX trong **một module Android đã áp dụng plugin Android phù hợp**:

```kotlin
dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
```

Đoạn trên là **minh họa dependency**, không phải `build.gradle.kts` độc lập có thể chạy bằng Java plugin thuần. Để biên dịch ứng dụng Android, cần Android Gradle Plugin (AGP), Android SDK, thiết lập Android và môi trường tương thích. **Chỉ thêm `google()` vào một dự án Java không biến nó thành dự án Android.**

### 4.1. Google Maven và Maven Central bổ sung cho nhau

Trong một build Android, có thể cần:

- Thành phần AndroidX/Google được công bố ở Google Maven.
- Thư viện Java/JVM chung từ Maven Central.
- Module riêng của công ty từ kho nội bộ.

Vì vậy, nhiều Android build dùng đồng thời `google()` và `mavenCentral()`. Thứ tự và chính sách lọc nên phản ánh các nhóm module thực sự thuộc kho nào, chứ không phải suy luận chỉ từ tên group.

### 4.2. Còn plugin Android thì sao?

**Kho dùng để tải plugin không nhất thiết trùng với kho dùng để tải thư viện của ứng dụng.** Android Gradle Plugin có cơ chế resolution ở khu vực cấu hình plugin. Ví dụ `settings.gradle.kts` của một build Android có thể khai báo:

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}
```

- `pluginManagement.repositories` phục vụ việc tìm plugin được yêu cầu qua DSL `plugins`.
- `dependencyResolutionManagement.repositories` phục vụ dependency thông thường của các project theo chính sách settings.
- `gradlePluginPortal()` là kho phổ biến cho các plugin Gradle được phát hành qua Plugin Portal; nó **không phải** tên khác của `mavenCentral()`.
- Không nên cho rằng `mavenCentral()` trong `dependencyResolutionManagement` sẽ tự giải quyết một plugin Gradle chưa tìm thấy ở plugin repositories.

Với project dùng chỉ các plugin lõi tích hợp sẵn như `java` hoặc `application`, Gradle không cần tải plugin lõi đó như một plugin bên ngoài từ Maven Central.

## 5. Kho Maven nội bộ: thư viện riêng và điểm kiểm soát của tổ chức

Tổ chức có thể duy trì repository Maven bằng các hệ thống quản lý artifact, ví dụ Artifactory, Nexus hoặc một dịch vụ repository tương thích Maven. Vai trò phổ biến:

1. **Phân phối thư viện riêng:** `com.example.internal:auth-client:2.4.0` hoặc các module không được công khai.
2. **Proxy/cache upstream:** giảm số lần truy cập trực tiếp nguồn bên ngoài, hỗ trợ quy định mạng, hạn chế phụ thuộc vào tình trạng một dịch vụ công khai.
3. **Kiểm soát bảo mật và giấy phép:** áp dụng chính sách phê duyệt thư viện, truy xuất nguồn gốc artifact và hạn chế version.
4. **Phân tách môi trường:** repository snapshot cho bản thử nghiệm, repository release cho artifact đã phát hành.
5. **Tập trung quyền truy cập:** dùng token, tài khoản service hoặc SSO tùy hệ thống.

Một kho nội bộ có thể chỉ lưu artifact riêng, hoặc vừa lưu artifact riêng vừa làm proxy cho Maven Central. Vì vậy **“kho nội bộ” không nhất thiết đồng nghĩa “không có thư viện công khai”**; điều đó phụ thuộc cách hệ thống repository được cấu hình.

### 5.1. Ví dụ khai báo Maven repository có xác thực

Đoạn này là **minh họa cấu hình Groovy DSL**, dùng URL và group giả định. Không sao chép URL giả để build thực tế nếu chưa có kho tương ứng:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.org/maven/releases')

        credentials {
            username = providers.environmentVariable('REPO_USER').orNull
            password = providers.environmentVariable('REPO_TOKEN').orNull
        }

        content {
            includeGroup 'com.example.internal'
        }
    }

    mavenCentral()
}
```

Ý nghĩa:

- `url` là URL repository Maven nội bộ do nhóm vận hành cung cấp.
- `credentials` lấy thông tin xác thực từ biến môi trường, thay vì đặt trực tiếp tên đăng nhập/token bí mật trong repository Git.
- `content { includeGroup ... }` giúp Gradle chỉ tìm group riêng của tổ chức tại repository này.
- `mavenCentral()` tiếp tục phục vụ các module công khai.

Nếu kho cần xác thực nhưng `REPO_USER` hoặc `REPO_TOKEN` vắng, resolution có thể thất bại với lỗi xác thực. Với hệ thống thực, tên biến môi trường, phương thức HTTP authentication và quyền truy cập phải theo tài liệu vận hành. **Không in token vào log để chẩn đoán**.

Một số repository dùng token trong header thay vì username/password, hoặc cần credential theo tên repository. Gradle có API riêng cho HTTP header credentials. Không nên giả định mọi kho nội bộ dùng Basic Authentication. Chọn cơ chế mà server hỗ trợ và tổ chức cho phép.

### 5.2. Snapshot và release

Kho Maven nội bộ thường có chính sách khác nhau cho hai kiểu artifact:

- **Release:** phiên bản ổn định được công bố, ví dụ `2.4.0`. Nên giữ nguyên nội dung một tọa độ đã phát hành.
- **Snapshot:** phiên bản đang phát triển, ví dụ `2.5.0-SNAPSHOT`, có thể được cập nhật nhiều lần và vì vậy kém tái lập hơn release.

Nếu dùng snapshot, hãy hiểu chính sách cập nhật metadata và thời hạn cache của changing modules. Không nên xây hệ thống phát hành sản phẩm yêu cầu tái lập hoàn toàn dựa trên artifact có cùng phiên bản nhưng nội dung thay đổi âm thầm.

### 5.3. Content filtering không thay thế xác thực

Lọc group giúp Gradle biết kho nào nên được hỏi, nhưng không trao quyền truy cập nếu server không cho phép. Ngược lại, có token hợp lệ cũng không có nghĩa Gradle nên tìm **mọi** group trong kho riêng. Hai cơ chế phục vụ hai mục đích:

- Authentication/authorization: ai được đọc artifact.
- Content filtering/routing: artifact thuộc nhóm nào nên được tìm ở kho nào.

Chúng nên được thiết kế kết hợp khi công ty quản lý cả kho nội bộ lẫn nguồn công khai.

## 6. `mavenLocal()`: kho Maven trên máy, không phải cache của Gradle

Ví dụ:

```groovy
repositories {
    mavenLocal()
    mavenCentral()
}
```

`mavenLocal()` cho phép Gradle tìm artifact trong **kho Maven cục bộ của người dùng**, thường ở `~/.m2/repository`. Đây là nơi Maven có thể cài artifact bằng `mvn install` và Gradle cũng có thể publish một artifact bằng `publishToMavenLocal` nếu project dùng plugin `maven-publish`.

Đừng nhầm ba vị trí:

| Vị trí/cơ chế | Vai trò |
| --- | --- |
| `~/.m2/repository` / `mavenLocal()` | Kho Maven cục bộ chứa artifact đã được cài/publish |
| `~/.gradle/caches` | Cache của Gradle chứa dependency, metadata và dữ liệu phục vụ build |
| `build/libs` | Artifact sinh bởi một project sau task như `jar` |

Chỉ có một file JAR nằm trong `build/libs` **không đồng nghĩa** thư viện đó đã có trong `mavenLocal()`. Muốn project khác giải quyết bằng tọa độ Maven qua `mavenLocal()`, cần publish/install artifact cùng metadata/tọa độ tương ứng vào kho Maven cục bộ.

### 6.1. Khi nào `mavenLocal()` có ích?

Ví dụ bạn phát triển hai repository riêng:

- Project `library` đang xây thư viện `com.example.training:math-utils:1.0.0`.
- Project `application` cần thử phiên bản này ngay trước khi thư viện được phát hành lên kho nội bộ.

Quy trình có thể là:

1. Build `library` bằng Gradle.
2. Dùng `maven-publish` và `publishToMavenLocal` để cài artifact có tọa độ Maven vào kho máy.
3. Trong `application`, bật `mavenLocal()` và khai báo `implementation 'com.example.training:math-utils:1.0.0'`.
4. Chạy build ứng dụng để thử thư viện mới.
5. Khi hoàn tất, phát hành thư viện chính thức và bỏ phụ thuộc vào kho cục bộ để CI cũng build được.

`mavenLocal()` là **cơ chế phát triển cục bộ thuận tiện**, không phải repository mặc định nên có trong tất cả build. Các artifact cục bộ có thể khác giữa máy A và máy B, gây ra lỗi “chạy trên máy tôi nhưng CI không chạy”.

### 6.2. Rủi ro tái lập build

Nếu máy lập trình viên có một artifact `com.example.training:math-utils:1.0.0` tự sửa, còn CI tìm phiên bản cùng tọa độ trên kho nội bộ, hai build có thể dùng **hai nội dung khác nhau**. Điều này đặc biệt khó phát hiện vì cả hai vẫn ghi cùng `group:artifact:version`.

Vì vậy nên:

- Không bật `mavenLocal()` vô điều kiện trong build phục vụ CI/release.
- Bật rõ ràng bằng một project property chỉ khi cần phát triển cục bộ.
- Hạn chế group mà Maven Local được phép phục vụ.
- Dùng release version và dependency verification/locking nếu phù hợp.
- Không coi “artifact lấy từ máy” là bằng chứng artifact đã được tổ chức phê duyệt.

### 6.3. Cấu hình Maven Local theo nhu cầu

Ví dụ trong `settings.gradle`:

```groovy
dependencyResolutionManagement {
    repositories {
        if (providers.gradleProperty('useMavenLocal').orNull == 'true') {
            mavenLocal {
                content {
                    includeGroup 'com.example.training'
                }
            }
        }

        mavenCentral()
    }
}
```

Chạy bình thường:

```bash
./gradlew build
```

Chạy khi chủ động muốn dùng artifact cục bộ cho group đã cho phép:

```bash
./gradlew build -PuseMavenLocal=true
```

Đặt `mavenLocal()` trước `mavenCentral()` ở ví dụ vì người dùng **chủ ý ưu tiên thử bản cục bộ** của group đã lọc. Đừng vô tình đặt nó đầu tiên cho mọi group và mọi môi trường. Khi dùng settings tập trung, tránh khai báo một danh sách repository trái ngược tại từng project con.

## 7. Thứ tự repository: Gradle tìm trong danh sách ra sao?

Khi nhiều Maven repository cùng được khai báo, **thứ tự và bộ lọc nội dung có ý nghĩa**. Gradle không ghép bừa mọi file từ tất cả các kho để tạo ra một module hoàn chỉnh.

Mô hình đơn giản:

```text
Yêu cầu: com.example.internal:billing-client:2.0.0
        |
        v
Kho 1 có được phép phục vụ group này?
        | Không -> bỏ qua
        | Có
        v
Tìm metadata / module version
        | Không tìm thấy -> thử kho tiếp theo nếu phù hợp
        | Tìm thấy
        v
Dùng repository phù hợp đã cung cấp metadata để lấy artifact
        |
        v
Tạo graph dependency và classpath
```

Một điểm rất quan trọng là **Gradle thường gắn artifact với repository mà nó đã tìm thấy metadata của module**. Nếu metadata được tìm ở kho A nhưng artifact yêu cầu bị thiếu trong kho A, không nên giả định Gradle sẽ tự lấy phần còn thiếu từ kho B như một cơ chế fallback hoàn hảo.

Những trường hợp nên cảnh giác:

- Hai kho công bố **cùng tọa độ** nhưng nội dung khác nhau.
- Một kho proxy có metadata stale hoặc artifact chưa được đồng bộ đầy đủ.
- Kho nội bộ trả lỗi `401 Unauthorized`/`403 Forbidden` chứ không phải “module không tồn tại”.
- Repository có bộ lọc `includeGroup` nên một group không hề được tìm ở đó.
- Cùng một group riêng có thể bị công bố ở kho công khai, tạo nguy cơ dependency confusion nếu định tuyến lỏng lẻo.

Với module nội bộ, đừng chỉ đặt kho riêng lên trước rồi tin rằng như vậy đã đủ bảo vệ. Nên dùng **exclusive content** hoặc chính sách repository tập trung để một nhóm tọa độ được định tuyến **chỉ đến nguồn được tin cậy**.

### 7.1. Phân biệt `content` và `exclusiveContent`

`content { includeGroup(...) }` gắn với một repository: “Repository này chỉ được tra cứu với group phù hợp”. Nhưng điều đó **không tự cấm** những repository khác phục vụ cùng group.

`exclusiveContent` mô tả quan hệ chặt chẽ hơn: một tập module chỉ được tìm trong repository được chỉ định. Ví dụ Groovy DSL, trong một khối `repositories` hợp lệ:

```groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                name = 'trustedCompany'
                url = uri('https://repo.example.org/maven/releases')

                credentials {
                    username = providers.environmentVariable('REPO_USER').orNull
                    password = providers.environmentVariable('REPO_TOKEN').orNull
                }
            }
        }

        filter {
            includeGroup 'com.example.internal'
        }
    }

    mavenCentral()
}
```

Đây là cấu hình **minh họa**: URL, credential và group cần thay theo tổ chức. Với chính sách này, nhóm `com.example.internal` được định tuyến độc quyền đến kho công ty, thay vì có thể rơi sang Maven Central khi kho riêng không tìm thấy.

Sự đánh đổi là có chủ đích: nếu kho riêng không hoạt động, build của group nội bộ sẽ thất bại, **không âm thầm chuyển sang một kho không được tin cậy**. Trong môi trường doanh nghiệp, đó thường là hành vi mong muốn.

### 7.2. “Thứ tự” không phải cách kiểm soát tất cả phiên bản

Nếu nhiều dependency yêu cầu các phiên bản khác nhau của cùng module, Gradle còn phải áp dụng quy tắc giải quyết xung đột phiên bản, variant matching và constraint. Repository order quyết định nơi tìm module; nó không có nghĩa “phiên bản nào nằm ở kho đầu tiên thì luôn thắng mọi dependency constraint”.

Chẳng hạn khi `library-A` yêu cầu `commons-lang3:3.12.0` và `library-B` yêu cầu `commons-lang3:3.14.0`, Gradle cần giải quyết phiên bản theo dependency graph, không đơn thuần chọn kho đầu tiên.

## 8. Nên khai báo repository ở đâu trong Gradle?

Ba vị trí thường gây nhầm lẫn nhất là:

| Khối cấu hình | Phục vụ việc gì? | Vị trí thường gặp |
| --- | --- | --- |
| `repositories { ... }` trong project | Dependency của project như `implementation` và `testImplementation` | `build.gradle` hoặc `build.gradle.kts` |
| `dependencyResolutionManagement { repositories { ... } }` | Chính sách dependency repositories tập trung cho project | `settings.gradle` hoặc `settings.gradle.kts` |
| `pluginManagement { repositories { ... } }` | Kho để giải quyết plugin được khai báo qua `plugins` | `settings.gradle` hoặc `settings.gradle.kts` |

Một vùng nữa là **`buildscript.repositories`**, dành cho những dependency đưa vào classpath của build script theo cơ chế `buildscript` truyền thống. Nó khác với repository của mã ứng dụng. Khi dùng DSL `plugins` hiện đại, ưu tiên cấu hình plugin resolution trong `pluginManagement` thay vì trộn lẫn các loại repository.

### 8.1. Centralize dependency repositories trong settings

Ví dụ `settings.gradle` của project Java:

```groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'repository-demo'

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
    }
}
```

`RepositoriesMode.FAIL_ON_PROJECT_REPOS` giúp dự án **từ chối khai báo repository dependency riêng ở các project** khi chính sách tập trung đang quản lý. Điều này làm thứ tự/nguồn thư viện nhất quán hơn và tránh plugin hoặc project con âm thầm thêm kho ngoài danh sách được phê duyệt.

Khi đã chọn chính sách này, **đừng tiếp tục thêm `repositories { mavenCentral() }` vào `build.gradle`** của project. Nó có thể bị xem là vi phạm chính sách và làm build thất bại.

Các chế độ khác cho phép mức độ linh hoạt khác nhau. Với dự án nhỏ, một `repositories` trong `build.gradle` có thể đủ; với multi-project hoặc tổ chức có quy định bảo mật, cấu hình tập trung ở settings thường dễ kiểm soát hơn.

### 8.2. Plugin repository không tự áp dụng cho runtime dependency

Ví dụ một settings dùng plugin bên ngoài:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        google()
        mavenCentral()
    }
}
```

Nó **không** tự bảo đảm `implementation 'org.apache.commons:commons-lang3:3.14.0'` tìm được. Bạn vẫn cần dependency repositories thông thường ở project hoặc `dependencyResolutionManagement`.

Ngược lại, chỉ có `dependencyResolutionManagement { repositories { mavenCentral() } }` không có nghĩa Gradle biết tìm mọi plugin bên ngoài trong Maven Central. Đó là hai luồng giải quyết khác nhau.

Một plugin có thể tự tạo dependency và task sau khi được áp dụng, nhưng điều đó cũng không biến các repository cấu hình plugin thành repository cho mọi dependency của ứng dụng.

## 9. Bài thực hành có thể chạy: Java 17 dùng thư viện từ Maven Central

Bài này dùng **Gradle Groovy DSL**, Java 17 và `commons-lang3` từ Maven Central. Mục tiêu là quan sát repository resolution bằng một ứng dụng rất nhỏ, không cần Android SDK hoặc kho nội bộ.

### 9.1. Cây file

```text
repository-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

**File `settings.gradle`:**

```groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'repository-demo'

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
    }
}
```

**File `build.gradle`:**

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

**File `src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String input = "gradle repositories";
        System.out.println(StringUtils.capitalize(input));
    }
}
```

### 9.2. Chạy chương trình

Cần có JDK 17 phù hợp hoặc đã cấu hình cơ chế cung cấp toolchain. Gradle cần Internet khi `commons-lang3:3.14.0` chưa có trong cache và không có repository proxy phù hợp.

Nếu project chưa có Gradle Wrapper, dùng một bản Gradle đã cài và tương thích để tạo Wrapper một lần:

```bash
gradle wrapper
```

Sau đó trên Linux/macOS:

```bash
./gradlew -q run
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat -q run
```

Stdout **do `Main.main` in ra** khi dependency được giải quyết và build thành công:

```text
Gradle repositories
```

`-q` giảm log Gradle; thông báo môi trường nếu có không phải output của ứng dụng. Lưu ý `StringUtils.capitalize` chỉ viết hoa chữ cái đầu của chuỗi, không biến mọi từ thành Title Case; vì vậy `gradle repositories` thành `Gradle repositories`.

Nếu không có `mavenCentral()` trong settings/project phù hợp và dependency chưa được cung cấp qua cơ chế khác, task biên dịch hoặc chạy cần dependency này sẽ không giải quyết được `commons-lang3`.

### 9.3. Quan sát dependency graph

Chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

- `dependencies` hiển thị đồ thị dependency của cấu hình được chọn.
- `dependencyInsight` giúp xem vì sao module được đưa vào cấu hình và có lựa chọn phiên bản/variant nào liên quan.
- Những lệnh này **không thay thế** việc chạy ứng dụng hoặc kiểm tra output biên dịch.

Muốn biết chi tiết Gradle thử giải quyết dependency như thế nào:

```bash
./gradlew --info compileJava
```

Log `--info` có thể chứa chi tiết hữu ích về resolution, tải artifact hoặc lý do task được bỏ qua. Nội dung và độ chi tiết khác nhau tùy phiên bản Gradle và tình trạng cache; không nên giả định log luôn in một URL tải cụ thể.

### 9.4. Kiểm tra cache và offline

Sau một lần giải quyết thành công, thử:

```bash
./gradlew --offline -q run
```

Nếu tất cả dependency cần thiết và dữ liệu Gradle liên quan đã có trong cache địa phương, lệnh có thể chạy mà không truy cập repository từ xa. Nếu chưa có artifact, metadata hoặc plugin cần thiết, `--offline` có thể thất bại.

**`--offline` không có nghĩa Gradle chuyển sang dùng `mavenLocal()`.** Nó chỉ yêu cầu không truy cập các nguồn mạng khi giải quyết dependency. Maven Local có được xét hay không vẫn phụ thuộc vào cấu hình repository.

Nếu nghi metadata cũ, `--refresh-dependencies` yêu cầu Gradle kiểm tra lại trạng thái dependency theo cơ chế của nó:

```bash
./gradlew --refresh-dependencies compileJava
```

Tùy chọn này **không bảo đảm tải lại mọi byte JAR** khi Gradle có thể xác nhận artifact cache vẫn hợp lệ. Nó cũng không sửa lỗi URL, quyền xác thực hoặc tọa độ dependency sai.

## 10. Ví dụ Kotlin DSL tương đương cho repository tập trung

Một dự án mới dùng Kotlin DSL có thể chọn:

**`settings.gradle.kts`:**

```kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = "repository-demo"

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
    }
}
```

**`build.gradle.kts`:**

```kotlin
plugins {
    application
}

application {
    mainClass.set("demo.Main")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Cùng file `src/main/java/demo/Main.java` ở mục 9 sẽ chạy qua `./gradlew -q run` với output `Gradle repositories`. Sự khác biệt chính:

- Groovy DSL dùng `id 'application'` và `implementation 'group:name:version'`.
- Kotlin DSL dùng `application` trong `plugins` (accessor plugin lõi) và `implementation("group:name:version")`.
- Kotlin DSL thường dùng `.set(...)` cho property như `mainClass` và `languageVersion`.

Cả hai đều dùng cùng mô hình Gradle repository, dependency configuration và task. **Không tạo đồng thời `settings.gradle` và `settings.gradle.kts` với các cấu hình mâu thuẫn rồi giả định Gradle sẽ gộp chúng.** Hãy chọn một DSL nhất quán cho từng file settings/build theo dự án.

## 11. Thử kho nội bộ và Maven Local mà không làm hỏng build chuẩn

Bài Java mục 9 chỉ dùng Maven Central, nên là baseline thích hợp. Khi mở rộng để dùng thư viện riêng, thực hiện theo thứ tự:

1. Xác định tọa độ `group:artifact:version` và repository chính thức của thư viện.
2. Kiểm tra kho nội bộ có metadata/artifact tương ứng không, người chạy build có quyền đọc không.
3. Thêm repository nội bộ trong settings chính sách tập trung, không nhét bí mật vào source code.
4. Giới hạn group nội bộ bằng content filter hoặc exclusive routing khi cần.
5. Khai báo dependency của project con.
6. Chạy `dependencyInsight` hoặc `dependencies` rồi build thật.
7. Chỉ khi đang thử artifact chưa phát hành, mới bật `mavenLocal()` có điều kiện.
8. Trước khi merge/CI/release, chạy lại với cấu hình **không dùng Maven Local**.

### 11.1. Một cách publish artifact sang Maven Local

Trong **project thư viện riêng**, sử dụng plugin `maven-publish`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.training'
version = '1.0.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

Đây là **file build minh họa cho một project thư viện riêng**, không phải phần cần chép vào project ứng dụng mục 9. `MavenPublication` cần kiểu xuất hiện trong DSL plugin; nếu IDE/build script không có import ngầm phù hợp, thêm `import org.gradle.api.publish.maven.MavenPublication` ở đầu file.

Sau khi project thư viện có mã Java và cấu hình hoàn chỉnh:

```bash
./gradlew publishToMavenLocal
```

Gradle tạo publication Maven (bao gồm metadata cần thiết) trong kho Maven Local của người dùng. Tên artifact mặc định thường dựa trên project name và có thể cấu hình. Ví dụ nếu tên module được đặt là `math-utils`, group `com.example.training` và version `1.0.0`, tọa độ tiêu thụ là:

```text
com.example.training:math-utils:1.0.0
```

Project ứng dụng cần khai báo `mavenLocal()` và dependency tương ứng trong phạm vi phù hợp. Nếu artifact version/tên khác với những gì đã publish, resolution vẫn thất bại dù thư mục Maven Local có một số file.

**Không nhầm `publishToMavenLocal` với `publish` lên repository từ xa**. Việc publish tới kho nội bộ là luồng riêng cần khai báo `publishing.repositories` và credential phù hợp.

## 12. Kho để tiêu thụ dependency khác kho để publish artifact

Khi một build cần **tải** thư viện, ta cấu hình repositories phục vụ dependency resolution:

```groovy
repositories {
    mavenCentral()
}
```

Khi một project cần **phát hành** artifact tới kho riêng, plugin `maven-publish` sử dụng một cấu hình khác:

```groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.org/maven/releases')

            credentials {
                username = providers.environmentVariable('REPO_USER').orNull
                password = providers.environmentVariable('REPO_TOKEN').orNull
            }
        }
    }
}
```

Đoạn này minh họa **phần cấu hình publishing** của một project đã áp dụng `maven-publish`; URL và biến môi trường là ví dụ, cần thay bằng thông tin thật phù hợp. Nó không đồng nghĩa ứng dụng đã được cấu hình **đọc** dependency từ URL đó.

Bốn khái niệm dễ nhầm:

| Mục đích | Cấu hình/command |
| --- | --- |
| Tải dependency cho code Java | `repositories` hoặc `dependencyResolutionManagement.repositories` |
| Tải plugin bên ngoài | `pluginManagement.repositories` |
| Publish artifact tới remote Maven | `publishing.repositories` + task publish |
| Publish artifact vào Maven Local | `publishToMavenLocal` của `maven-publish` |

Nếu một nhóm có repository “releases” chỉ cho đọc, lệnh publish tới đó vẫn có thể bị từ chối; quyền ghi và quyền đọc là hai chính sách độc lập.

## 13. Bảo mật, độ tin cậy và khả năng tái lập

Dùng nhiều repository không chỉ là vấn đề hiệu năng. Nó cũng ảnh hưởng **nguồn gốc dependency**, bảo mật và khả năng xây lại đúng artifact.

### 13.1. Dependency confusion

Một nguy cơ là attacker công bố một module công khai có cùng group/artifact với thư viện nội bộ hoặc một tên mà tổ chức tưởng chỉ dùng trong mạng riêng. Nếu build được phép tìm nhóm nội bộ ở cả kho công khai, nó có thể chọn nguồn không mong muốn trong những tình huống nhất định.

Các biện pháp:

- Dùng group nội bộ được quản lý chặt.
- Dùng `exclusiveContent` hoặc chính sách routing tương đương cho module riêng.
- Không xem thứ tự repository là biện pháp bảo vệ duy nhất.
- Xác thực và phân quyền kho nội bộ đúng cách.
- Dùng dependency verification, kiểm tra checksum/chữ ký khi phù hợp và kiểm soát artifact được phát hành.

### 13.2. Không để lộ credential

Tránh:

```groovy
// Không an toàn: minh họa hành vi cần tránh.
credentials {
    username = 'real-account'
    password = 'secret-in-git'
}
```

Thay vào đó, dùng biến môi trường, Gradle properties an toàn hoặc credential management theo nền tảng CI. Không in giá trị bí mật trong log, issue hoặc báo cáo build. Cũng đừng nghĩ việc đưa token vào `gradle.properties` của repository và commit file là “an toàn” chỉ vì Gradle đọc được.

Đối với CI, token nên có phạm vi quyền tối thiểu và vòng đời luân chuyển phù hợp. Nếu lệnh chỉ cần đọc dependency, không cấp quyền publish artifact.

### 13.3. Cố định dependency và kiểm soát nguồn

- Ưu tiên version cụ thể, ví dụ `3.14.0`, khi cần tái lập và đã đánh giá thư viện.
- Với dynamic version như `1.+` hoặc changing module/snapshot, hiểu rõ TTL và tác động của metadata đổi theo thời gian.
- Dùng dependency locking khi muốn kiểm soát phiên bản được chọn cho configuration.
- Dùng dependency verification/checksum nếu tổ chức cần xác minh tính toàn vẹn artifact.
- Không publish đè cùng một release version bằng nội dung khác: tọa độ không đổi nhưng hash khác sẽ khiến cache và build khác nhau.
- Giới hạn các nhóm repository được phép cung cấp nội dung và quản lý việc thay đổi danh sách repository qua review.

**Version pinning là cần nhưng chưa đủ**. Nếu cùng tọa độ lấy được từ nhiều nguồn khác nhau với nội dung không đồng nhất, chỉ cố định version vẫn có nguy cơ dùng artifact khác nhau. Vì thế chính sách repository và xác thực nguồn gốc rất quan trọng.

## 14. Cache, offline và sự khác biệt giữa các máy

Gradle có nhiều cache:

| Cơ chế | Chứa gì? | Có thay thế repository declaration không? |
| --- | --- | --- |
| Dependency cache trong `~/.gradle/caches` | Metadata/artifact đã giải quyết, dữ liệu cần để tránh tải lại | Không phải cấu hình nguồn chính thức của project |
| Build cache | Output của task có thể cache | Không phải kho Maven |
| Configuration cache | Trạng thái cấu hình/graph tương thích | Không phải kho Maven |
| Maven Local `~/.m2/repository` | Artifact được cài/publish cục bộ theo layout Maven | Chỉ được sử dụng khi `mavenLocal()` được khai báo |
| Remote Maven repository | Artifact/metadata do kho công bố | Là nguồn resolution khi được cấu hình và có thể truy cập |

Một dependency đã được tải vào cache Gradle có thể dùng lại mà không cần tải từ mạng trong những tình huống phù hợp. Điều này **không chứng minh kho gốc hiện vẫn hoạt động**. Nếu cần kiểm tra build sạch, CI hoặc môi trường không có cache sẽ cung cấp bằng chứng khác với laptop đã build nhiều lần.

`--refresh-dependencies` không phải lệnh “xóa sạch tất cả cache”. `--offline` không buộc Gradle dùng Maven Local. `clean` thường xóa output của project, **không xóa toàn bộ Gradle dependency cache**. Đọc đúng cơ chế trước khi dùng một tùy chọn để chẩn đoán.

### 14.1. Vì sao build chạy trên laptop nhưng thất bại ở CI?

Các nguyên nhân phổ biến:

1. Laptop có `mavenLocal()` với artifact chưa phát hành, CI không có.
2. Laptop đã cache dependency; CI cần truy cập kho từ xa nhưng bị chặn mạng.
3. Credential chỉ tồn tại trên máy cá nhân, chưa cấu hình secret của CI.
4. URL nội bộ chỉ truy cập được trong VPN hoặc mạng doanh nghiệp.
5. Build script khai báo repository ở project con nhưng settings trên CI dùng `FAIL_ON_PROJECT_REPOS`.
6. Version snapshot/changing đã thay đổi và máy có cache khác nhau.
7. Repository hoặc filter chỉ cho phép một số group, còn dependency yêu cầu group khác.

Đừng vội “sửa” bằng cách bật `mavenLocal()` khắp nơi. Cần xác định lỗi thuộc **tọa độ, repository, quyền, mạng, metadata, cache hay Java/Gradle version**.

## 15. Chẩn đoán lỗi resolve dependency có hệ thống

Khi Gradle báo `Could not resolve ...` hoặc `Could not find ...`:

### Bước 1 — đọc đúng tọa độ

Kiểm tra `group:artifact:version` và configuration dùng nó. Gõ sai `commons-lang3` hoặc một version không được công bố sẽ thất bại dù Maven Central hoạt động.

### Bước 2 — tìm nơi khai báo repository

Kiểm tra dự án đang dùng:

- `settings.gradle` với `dependencyResolutionManagement` hay không.
- `build.gradle` của đúng project con, nếu chính sách cho phép.
- `pluginManagement` nếu lỗi thực sự liên quan plugin.
- `publishing.repositories` chỉ nếu lỗi xuất hiện trong lúc publish.

Đừng sửa `pluginManagement.repositories` để xử lý lỗi của `runtimeClasspath` khi vấn đề nằm ở dependency repositories.

### Bước 3 — kiểm tra filter và thứ tự

Nếu group riêng được lọc bởi `exclusiveContent`, nó sẽ không được hỏi ở Maven Central. Đảm bảo kho nội bộ có module đó. Nếu nhiều repository có module giống nhau, kiểm tra chính sách định tuyến và metadata.

### Bước 4 — phân biệt lỗi xác thực và không tìm thấy

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| `401 Unauthorized` | Credential thiếu, sai hoặc hết hạn |
| `403 Forbidden` | Tài khoản có thể không được cấp quyền, policy server |
| `404 Not Found` | URL, tọa độ hoặc module/version chưa có ở nơi được hỏi |
| Timeout/DNS/TLS error | Mạng, proxy, chứng chỉ hoặc server |
| `Could not find group:module:version` | Có thể chưa khai báo đúng kho, metadata, group/version, filter |
| Artifact/POM bị thiếu | Kho publish chưa đầy đủ hoặc metadata chỉ tới file không còn tồn tại |
| Plugin not found | Kiểm tra `pluginManagement.repositories` và plugin id/version, không chỉ dependency repositories |

HTTP code là tín hiệu quan trọng, nhưng cần đọc thông báo đầy đủ và URL thực tế. Không phải mọi lỗi 403 đều được giải bằng đổi mật khẩu; có thể là quyền repository, firewall hoặc chính sách server.

### Bước 5 — dùng các lệnh chẩn đoán

Trong project `repository-demo` ở mục 9:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew --info compileJava
./gradlew --refresh-dependencies compileJava
```

`--info` thường có dữ liệu hữu ích nhưng có thể rất dài; tập trung vào dependency/module bị lỗi. Nếu cần dấu vết lỗi chi tiết, thử `--stacktrace` sau khi đã xác định vấn đề.

### Bước 6 — kiểm chứng không phụ thuộc vào Maven Local

Nếu một build chỉ chạy khi thêm `mavenLocal()`, hãy kiểm tra thư viện đã được phát hành đến repository mà CI/release sử dụng chưa. Chạy lại với `mavenLocal()` tắt để tránh chỉ xác nhận môi trường máy cá nhân.

## 16. Các lỗi cấu hình hay gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `implementation(...)` không tìm thấy thư viện Java | Chưa có repository phù hợp hoặc tọa độ sai | Kiểm tra Maven Central/URL phù hợp, group/artifact/version |
| AndroidX không tìm thấy | Thiếu `google()` trong dependency repository phù hợp | Thêm Google Maven ở settings/project theo chính sách |
| AGP/plugin bên ngoài không resolve được | Plugin repository chưa được cấu hình đúng | Kiểm tra `pluginManagement.repositories` |
| Build báo project repository bị cấm | Settings dùng `FAIL_ON_PROJECT_REPOS` nhưng project vẫn khai báo `repositories` | Chuyển repo về settings, bỏ khai báo trùng |
| Lỗi `401` với kho riêng | Biến môi trường credential thiếu/sai | Kiểm tra secret và quyền truy cập, không in token |
| Group nội bộ bị tìm ở kho công khai | Chưa có routing/filter độc quyền | Dùng `exclusiveContent`/repository policy |
| Laptop resolve được nhưng CI không | Dùng Maven Local hoặc cache cá nhân | Publish chính thức, tắt Maven Local trong CI |
| Dependency snapshot bỗng đổi hành vi | Cùng tọa độ có thể đổi artifact theo chính sách snapshot | Pin release, kiểm soát changing module/TTL |
| Dùng `--offline` rồi lỗi | Artifact/metadata cần thiết chưa cache | Build online trước hoặc cung cấp nguồn được phê duyệt |
| `clean` không khiến dependency tải lại | `clean` xóa output project, không phải cache dependency | Hiểu cache; chỉ refresh khi có lý do |
| Repository đầu tiên có POM nhưng thiếu JAR | Nội dung kho không đầy đủ | Sửa bản publish/proxy; đừng trông chờ ghép artifact từ kho khác |
| `publishToMavenLocal` xong nhưng app không thấy module | Thiếu `mavenLocal()`, sai tọa độ hoặc chưa publish đúng publication | Kiểm tra group/artifact/version và cấu hình tiêu thụ |
| Thêm Maven Central vào `pluginManagement` nhưng `implementation` vẫn lỗi | Khai báo nhầm loại repository | Dùng dependency repositories |
| Tải một JAR rồi đặt dưới `build/libs` nhưng dependency không resolve | JAR output chưa được publish theo tọa độ Maven | Publish/install hoặc khai báo dependency file tường minh phù hợp |
| Kho công ty trả 403 | Không đủ quyền, chưa được cấp đọc repository | Xin quyền theo quy trình, không sửa bằng token hard-code |

## 17. Bài tập áp dụng

**Bài tập A — phân biệt vai trò kho.** Với bốn module giả định: thư viện logging Java công khai, AndroidX, thư viện `com.example.internal:auth-sdk` và artifact tự build chưa phát hành, hãy nêu kho nên dùng cho từng loại. Giải thích vì sao Maven Central và Google Maven có thể xuất hiện cùng nhau trong một build Android.

**Bài tập B — chạy ứng dụng dùng Maven Central.** Tạo project mục 9, chạy `./gradlew -q run` và kiểm tra stdout `Gradle repositories`. Sau đó chạy `dependencies --configuration runtimeClasspath` và chỉ ra tọa độ `commons-lang3` trong graph.

**Bài tập C — thử offline.** Sau khi build thành công online, chạy `./gradlew --offline -q run`. Nếu chạy được, giải thích vai trò cache. Nếu không chạy, đọc dependency/plugin nào chưa có. Không suy luận offline tự dùng Maven Local.

**Bài tập D — tập trung repository.** Thử thêm `repositories { mavenCentral() }` vào `build.gradle` của ví dụ khi `settings.gradle` đang dùng `FAIL_ON_PROJECT_REPOS`. Quan sát thông báo lỗi và sửa bằng cách xóa khai báo không đúng chỗ.

**Bài tập E — chuẩn bị kho nội bộ.** Viết một khối repository có URL giả, credential từ biến môi trường và `content { includeGroup 'com.example.internal' }`. Giải thích vì sao không nên đưa token thật vào Git. Chỉ chạy với repository thực mà bạn có quyền dùng.

**Bài tập F — Maven Local có điều kiện.** Tạo một thư viện `math-utils`, publish vào Maven Local bằng `maven-publish` và thử tiêu thụ bằng tọa độ tương ứng. Chạy ứng dụng với/không có `-PuseMavenLocal=true` để phân biệt sự khác nhau.

**Bài tập G — repository order và nguồn gốc.** Giả sử kho A và B đều công bố tọa độ `com.example.internal:core:1.0.0` với nội dung khác nhau. Vì sao chỉ đổi thứ tự repository là một biện pháp yếu? Hãy đề xuất routing độc quyền và quản lý release version.

**Bài tập H — giải quyết lỗi.** Một build trả `401 Unauthorized` khi tải `com.example.internal:client:2.0.0`. Hãy phân biệt vấn đề này với `Could not find` do version chưa công bố; nêu những kiểm tra có thể làm mà không lộ token.

### Câu hỏi tự kiểm tra

1. Repository và dependency khác nhau ở điểm nào?
2. `group:artifact:version` giúp Gradle xác định thứ cần tìm như thế nào?
3. Maven Central phù hợp cho loại thư viện nào? Có tự được Java plugin bật không?
4. Khi nào `google()` thường cần thiết và vì sao Java plugin đơn lẻ không đủ để build Android?
5. Kho nội bộ có thể đóng vai trò proxy cho Maven Central không?
6. `mavenLocal()` trỏ vào cơ chế nào? Nó có phải `~/.gradle/caches` không?
7. `publishToMavenLocal` khác với task `jar` như thế nào?
8. Nếu hai kho có cùng tọa độ nhưng artifact khác nhau, vì sao build có thể kém tái lập?
9. `exclusiveContent` bổ sung điều gì so với `content { includeGroup ... }`?
10. Tại sao cần tách `pluginManagement.repositories` và `dependencyResolutionManagement.repositories`?
11. `FAIL_ON_PROJECT_REPOS` giúp duy trì chính sách như thế nào?
12. `--offline`, `--refresh-dependencies` và `clean` xử lý ba vấn đề khác nhau ra sao?
13. Làm sao nhận diện lỗi 401/403 so với lỗi version không tồn tại?
14. Tại sao CI không nên phụ thuộc vào artifact chỉ có trong Maven Local của một lập trình viên?
15. Khi nào nên dùng dependency locking và dependency verification?

**Ghi nhớ:** **Maven Central** phục vụ phần lớn thư viện Java/JVM công khai; **Google Maven** bổ sung những artifact Android/Google cần thiết; **kho nội bộ** quản lý thư viện riêng, proxy và chính sách tổ chức; **`mavenLocal()`** dành chủ yếu cho thử nghiệm artifact đã cài trên máy. Hãy phân biệt repository tải dependency, repository tải plugin và repository publish artifact; quản lý thứ tự và group filtering chặt chẽ, tránh lộ credential, cố định phiên bản và kiểm chứng build không phụ thuộc vào cache hoặc Maven Local cá nhân.
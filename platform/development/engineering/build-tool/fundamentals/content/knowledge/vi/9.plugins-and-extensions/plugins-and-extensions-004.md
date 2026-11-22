# Quản lý phiên bản plugin và khả năng tương thích với công cụ build

Plugin mở rộng build tool bằng cách cung cấp task, configuration, extension và các quy ước cho một loại dự án. Ví dụ, Java plugin bổ sung các task biên dịch và kiểm thử; Spring Boot plugin bổ sung những công việc đóng gói và chạy ứng dụng Spring Boot; plugin kiểm tra chất lượng có thể thêm task phân tích mã nguồn.

Vì plugin tham gia trực tiếp vào quá trình cấu hình và thực thi build, phiên bản plugin cần tương thích với phiên bản Gradle hoặc Maven, với JDK đang sử dụng và đôi khi với các plugin khác trong cùng dự án. Nếu phiên bản không phù hợp, build có thể lỗi ngay khi cấu hình, lỗi khi thực thi task hoặc tạo ra hành vi khác với dự kiến.

Quản lý phiên bản plugin có ba mục tiêu: xác định rõ phiên bản đang dùng, giữ các module trong cùng build nhất quán và nâng cấp có kiểm soát sau khi kiểm tra khả năng tương thích.

## 1. Plugin version và build tool version là hai phiên bản khác nhau

Một dự án Gradle thường có ít nhất hai nhóm phiên bản cần quan tâm:

- **Phiên bản Gradle:** xác định build tool và API mà build script, plugin sẽ chạy trên đó.
- **Phiên bản plugin:** xác định phần mở rộng cung cấp task, extension hoặc quy tắc build.

Ngoài ra còn có phiên bản JDK chạy Gradle, phiên bản Java toolchain dùng để biên dịch và phiên bản dependency của ứng dụng. Những phiên bản này có quan hệ với nhau nhưng không thay thế cho nhau.

Ví dụ, cấu hình sau xác định phiên bản Gradle qua Wrapper và phiên bản plugin Spring Boot trong build script:

```text
gradle/wrapper/gradle-wrapper.properties
    -> Gradle distribution version

build.gradle
    -> Spring Boot plugin version

java.toolchain
    -> JDK version used by Java tasks
```

Nếu chỉ nâng phiên bản plugin mà không kiểm tra Gradle, plugin có thể yêu cầu một Gradle API mới hơn phiên bản Wrapper đang dùng. Ngược lại, nâng Gradle có thể làm lộ các API cũ đã bị loại bỏ hoặc thay đổi hành vi của plugin.

## 2. Gradle phân giải plugin như thế nào?

### 2.1. Khối plugins

Cách khai báo plugin hiện đại trong Gradle là khối `plugins`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}
```

`id` là định danh plugin. Với plugin ngoài Gradle core, khối này thường cần một phiên bản rõ ràng hoặc một phiên bản mặc định được cấu hình ở cấp Settings. Gradle dùng yêu cầu plugin để tìm plugin marker và artifact triển khai plugin trong các repository dành cho plugin.

Các plugin core như `java`, `java-library` hoặc `application` được Gradle cung cấp nên không cần chỉ định version trong khối `plugins`.

### 2.2. Repository dành cho plugin

Repository dùng để tìm plugin được cấu hình ở `pluginManagement.repositories` trong `settings.gradle` hoặc `settings.gradle.kts`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'order-platform'
```

`gradlePluginPortal()` là repository phổ biến để tìm plugin Gradle được công bố trên Plugin Portal. Có thể bổ sung Maven repository riêng nếu tổ chức phát hành plugin nội bộ ở đó.

Không nên nhầm repository plugin với repository dependency của ứng dụng:

```groovy
// settings.gradle
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven { url = uri('https://repo.example.com/gradle-plugins') }
    }
}
```

```groovy
// build.gradle
repositories {
    mavenCentral()
    maven { url = uri('https://repo.example.com/libraries') }
}
```

`pluginManagement.repositories` phục vụ việc phân giải plugin được yêu cầu trong khối `plugins`. `repositories` của project phục vụ dependency của project như thư viện logging, JSON hoặc database driver. Cấu hình một nhóm repository không tự động thay thế nhóm còn lại.

### 2.3. Plugin marker và implementation artifact

Với plugin được phát hành theo cơ chế plugin DSL, Gradle thường tìm một plugin marker artifact dựa trên plugin ID và version. Marker trỏ đến artifact chứa implementation thực tế.

Vì vậy, khi Gradle báo không tìm thấy plugin, nguyên nhân có thể nằm ở nhiều điểm:

- Plugin ID bị viết sai.
- Phiên bản không tồn tại hoặc chưa được phát hành.
- Repository dành cho plugin chưa được cấu hình.
- Repository yêu cầu thông tin xác thực nhưng build chưa cung cấp.
- Mạng hoặc proxy không cho phép truy cập repository.
- Plugin được phát hành theo cách khác và cần cấu hình resolution riêng.

Thông báo lỗi phân giải plugin thường xuất hiện trong giai đoạn cấu hình, trước khi các task biên dịch hoặc kiểm thử được thực thi.

## 3. Những cách khai báo và quản lý phiên bản plugin trong Gradle

### 3.1. Khai báo version trực tiếp

Với project nhỏ, có thể khai báo plugin và version ngay tại build script:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
```

Cách này dễ đọc vì người xem biết ngay project đang sử dụng plugin version nào. Tuy nhiên, nếu có nhiều module cùng dùng một plugin, việc lặp lại version trong nhiều build script sẽ làm tăng nguy cơ lệch phiên bản.

Không nên dùng một version khác nhau giữa các module trong cùng build nếu không có lý do rõ ràng. Plugin có thể tạo task hoặc extension tương tác với nhau; cấu hình không đồng nhất khiến việc nâng cấp và chẩn đoán khó hơn.

### 3.2. Khai báo version mặc định trong pluginManagement

Có thể tập trung version plugin ở `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }

    plugins {
        id 'org.springframework.boot' version '3.3.5'
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'order-platform'
include 'api', 'worker'
```

Các project có thể yêu cầu plugin mà không lặp lại version:

```groovy
// api/build.gradle
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
```

Khối `plugins` trong `pluginManagement` cung cấp version mặc định cho plugin request có cùng ID khi request không tự chỉ định version. Đây là cách phù hợp khi nhiều project cần dùng chung phiên bản plugin.

`pluginManagement` được xử lý ở giai đoạn Settings, trước khi Gradle cấu hình các project. Vì vậy, đây là vị trí phù hợp để quản lý repository, version mặc định và quy tắc phân giải plugin cho toàn build.

### 3.3. Dùng apply false ở root project

Một cách phổ biến khác là khai báo plugin version tại root build script với `apply false`, sau đó áp dụng plugin trong từng module:

```groovy
// build.gradle ở root project
plugins {
    id 'org.springframework.boot' version '3.3.5' apply false
    id 'io.spring.dependency-management' version '1.1.6' apply false
}
```

```groovy
// api/build.gradle
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
```

`apply false` yêu cầu Gradle phân giải plugin và đưa version vào phạm vi quản lý của build mà không áp dụng plugin lên project root. Các project con có thể yêu cầu cùng plugin mà không cần khai báo lại version.

Cách này phù hợp với một số build nhiều module. Với build mới, cũng có thể cân nhắc quản lý version qua `pluginManagement` hoặc version catalog để quy tắc tập trung hơn. Chọn một cơ chế rõ ràng và thống nhất để người đọc dễ biết version đến từ đâu.

### 3.4. Dùng Version Catalog cho plugin

Gradle hỗ trợ Version Catalog để tập trung tên và version dependency/plugin trong file TOML. Catalog mặc định thường nằm ở `gradle/libs.versions.toml`.

Ví dụ:

```toml
[versions]
spring-boot = "3.3.5"
dependency-management = "1.1.6"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dependency-management = { id = "io.spring.dependency-management", version.ref = "dependency-management" }
```

Trong build script, dùng alias:

```kotlin
plugins {
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dependency.management)
}
```

Với alias trong Version Catalog, Gradle tạo accessor theo tên alias. Trong ví dụ, alias `spring-boot` được truy cập bằng `libs.plugins.spring.boot` trong Kotlin DSL. Nếu dùng Groovy DSL, cách truy cập accessor có cú pháp tương ứng theo generated accessor của Gradle.

Ưu điểm của Version Catalog:

- Tập trung version plugin và dependency ở một nơi.
- Dùng version reference để nhiều alias chia sẻ cùng một version.
- Tên alias giúp build script dễ đọc hơn các chuỗi ID dài.
- Khi nâng cấp, có thể thay đổi version tại catalog thay vì tìm và sửa nhiều file.

Version Catalog quản lý cách khai báo version; nó không tự đảm bảo plugin tương thích với Gradle hoặc JDK. Sau khi thay version trong catalog, vẫn cần kiểm tra compatibility và chạy build.

### 3.5. Chọn cách quản lý phù hợp

| Cách khai báo | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Version trực tiếp trong project | Project nhỏ hoặc plugin chỉ dùng ở một nơi | Dễ lặp version trong nhiều module |
| `pluginManagement.plugins` | Muốn đặt version mặc định ở cấp Settings | Phải hiểu plugin request và phạm vi Settings |
| Root `plugins { ... apply false }` | Nhiều project dùng cùng plugin và muốn root quản lý version | Cần tránh trộn nhiều cơ chế quản lý không cần thiết |
| Version Catalog | Muốn quản lý tập trung plugin và dependency bằng alias | Catalog chỉ quản lý version/alias, không kiểm chứng compatibility |
| Convention plugin | Muốn chuẩn hóa cả cách áp dụng và cấu hình plugin cho nhiều module | Cần quản lý riêng build logic và vòng đời của convention plugin |

Với build lớn, Version Catalog thường hữu ích cho danh mục version, còn convention plugin hữu ích cho quy tắc áp dụng và cấu hình. Hai cơ chế có thể kết hợp: catalog cung cấp version, convention plugin đóng gói cách cấu hình project.

## 4. Plugin resolution strategy và plugin nội bộ

### 4.1. Khi cần ánh xạ plugin ID

Đôi khi tổ chức có plugin nội bộ hoặc plugin cũ được phân phối theo tọa độ Maven nhưng không có marker artifact theo quy ước mặc định. `pluginManagement.resolutionStrategy` có thể ánh xạ plugin request sang module implementation:

```groovy
pluginManagement {
    repositories {
        maven { url = uri('https://repo.example.com/gradle-plugins') }
        gradlePluginPortal()
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'com.example.company-build') {
                useModule('com.example.build:company-gradle-plugin:2.4.0')
            }
        }
    }
}
```

`useModule` chỉ định module chứa implementation plugin cho request tương ứng. Cần đảm bảo repository có artifact đó và version được quản lý có chủ đích. Không nên thêm quy tắc ánh xạ rộng khiến plugin ID hợp lệ vô tình trỏ đến module khác.

### 4.2. Plugin nội bộ dưới dạng included build

Với build logic được quản lý trong cùng repository, Gradle hỗ trợ composite build và convention plugin. Một cách tổ chức thường gặp là thư mục `build-logic` được include trong Settings:

```groovy
// settings.gradle
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Build `build-logic` có thể định nghĩa convention plugin, ví dụ `com.example.java-library-conventions`, để các module áp dụng một quy tắc thống nhất. Convention plugin có thể áp dụng Java plugin, đặt toolchain, cấu hình test và thêm các quy tắc dùng chung.

Lợi ích là module chỉ cần khai báo ý định:

```groovy
plugins {
    id 'com.example.java-library-conventions'
}
```

Thay vì lặp lại hàng chục dòng cấu hình trong từng `build.gradle`, logic chung nằm trong một plugin có thể kiểm soát và kiểm thử riêng. Tuy nhiên, build logic này cũng cần có yêu cầu phiên bản Gradle/JDK phù hợp và phải được bảo trì như một phần của hệ thống build.

## 5. Cơ chế cũ: buildscript classpath và apply plugin

Gradle từng thường được cấu hình plugin qua khối `buildscript` và lệnh `apply plugin`:

```groovy
buildscript {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    dependencies {
        classpath 'com.example:legacy-gradle-plugin:1.8.0'
    }
}

apply plugin: 'com.example.legacy'
```

`buildscript.repositories` và `buildscript.dependencies` khai báo classpath để chạy build script/plugin. Sau đó `apply plugin` áp dụng plugin đã có trên classpath vào project.

Cơ chế này vẫn tồn tại trong các build cũ và một số tình huống đặc thù. Với plugin mới, khối `plugins` thường là lựa chọn ưu tiên vì khai báo rõ ID/version, hỗ trợ resolution có cấu trúc và dễ quản lý tập trung hơn.

Không nhầm `buildscript.dependencies` với `dependencies` của ứng dụng:

| Cấu hình | Dùng cho |
|---|---|
| `buildscript.dependencies { classpath ... }` | Classpath của build script và plugin được nạp theo cơ chế cũ |
| `dependencies { implementation ... }` | Thư viện mà mã nguồn ứng dụng sử dụng |
| `plugins { id ... version ... }` | Yêu cầu plugin theo cơ chế plugin DSL |

Plugin build thường chạy trong tiến trình Gradle và có thể ảnh hưởng đến toàn bộ quá trình cấu hình. Vì vậy, plugin cần được xem là một thành phần của môi trường build, không phải dependency runtime thông thường của ứng dụng.

## 6. Khả năng tương thích giữa plugin, Gradle và JDK

### 6.1. Tương thích với phiên bản Gradle

Plugin sử dụng Gradle API để đăng ký task, tạo extension, đọc cấu hình hoặc tương tác với lifecycle. Một plugin được phát triển và kiểm thử với một dải phiên bản Gradle nhất định có thể không hoạt động trên phiên bản quá cũ hoặc phiên bản mới đã loại bỏ API mà plugin đang dùng.

Các dấu hiệu không tương thích có thể gồm:

- Không tìm thấy class hoặc method của Gradle API.
- Lỗi `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassNotFoundException` khi áp dụng plugin.
- Lỗi cấu hình do API cũ đã bị loại bỏ.
- Plugin yêu cầu phiên bản Gradle tối thiểu cao hơn Wrapper của project.
- Plugin hoạt động trên một phiên bản Gradle nhưng task thất bại trên phiên bản khác.

Không nên suy luận rằng plugin có version mới hơn thì luôn chạy được trên Gradle cũ hơn. Cần kiểm tra tài liệu plugin, release notes và yêu cầu Gradle tối thiểu/tối đa nếu tác giả công bố.

### 6.2. Tương thích với JVM chạy Gradle

Gradle chạy trong một JVM. Phiên bản Java dùng để khởi động Gradle phải nằm trong dải phiên bản được chính phiên bản Gradle đó hỗ trợ.

Đây là điểm khác với Java toolchain:

| Thành phần | Vai trò |
|---|---|
| JVM chạy Gradle | Nạp Gradle, build script và plugin |
| Java toolchain | Chọn JDK/compiler/runtime cho các task Java được cấu hình sử dụng toolchain |
| `sourceCompatibility` / `targetCompatibility` hoặc `options.release` | Điều khiển mức ngôn ngữ/bytecode/API mục tiêu theo cấu hình compiler |

Ví dụ, một project có thể dùng JDK mới để chạy Gradle nhưng chọn Java 17 toolchain để biên dịch ứng dụng. Điều đó không có nghĩa plugin có thể chạy trên mọi JDK hoặc mọi Gradle version. Plugin vẫn phải tương thích với JVM đang chạy Gradle và với Gradle API được sử dụng.

### 6.3. Tương thích với plugin khác

Hai plugin có thể cùng tạo extension hoặc task, cùng cấu hình source set, dependency configuration hay lifecycle hook. Một plugin có thể yêu cầu plugin khác hoặc giả định plugin kia đã được áp dụng.

Ví dụ, plugin Spring Boot thường phối hợp với Java plugin và các plugin liên quan đến dependency management. Plugin kiểm tra chất lượng có thể cần biết source set và compile classpath. Nếu thay đổi version của một plugin, cần xem release notes để biết có yêu cầu nâng version plugin liên quan hay thay đổi cấu hình không.

Không nên nâng cấp từng plugin một cách độc lập khi chúng tạo thành một bộ công cụ có ràng buộc phiên bản. Với các plugin thuộc cùng hệ sinh thái, nên kiểm tra ma trận tương thích do nhà phát triển công bố.

### 6.4. Tương thích với dependency của ứng dụng

Plugin có thể thêm dependency, thay đổi configuration hoặc quản lý version qua BOM/platform. Khi nâng plugin framework, các dependency runtime có thể được quản lý theo một bộ version khác.

Ví dụ, Spring Boot Gradle plugin thường được phát hành cùng Spring Boot release. Khi nâng Spring Boot plugin, cần xem xét bộ dependency được Spring Boot quản lý và các plugin hỗ trợ liên quan. Không nên chỉ thay plugin version rồi giữ mọi dependency tùy chỉnh mà không kiểm tra compatibility.

## 7. Gradle Wrapper và Java toolchain trong quản lý tương thích

### 7.1. Wrapper khóa phiên bản Gradle

Gradle Wrapper cho phép repository xác định phiên bản Gradle cần dùng. Thông tin distribution thường nằm trong:

```text
gradle/wrapper/gradle-wrapper.properties
```

Ví dụ:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
```

Khi chạy `./gradlew`, Wrapper tải hoặc sử dụng bản Gradle đã chỉ định. Nhờ đó, các máy trong nhóm không vô tình chạy những phiên bản Gradle khác nhau chỉ vì cài đặt toàn cục khác nhau.

Khi nâng Gradle, nên dùng task Wrapper hoặc cập nhật cấu hình Wrapper theo quy trình của dự án, commit các file Wrapper đã thay đổi và chạy lại các bước kiểm tra. Không nên chỉ thay một con số mà bỏ qua việc kiểm tra checksum, URL distribution hoặc các file Wrapper đi kèm.

### 7.2. Toolchain kiểm soát JDK cho task Java

Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain giúp chọn JDK cho compile/test hoặc các task Java được cấu hình sử dụng toolchain. Nó giải quyết một lớp khác của bài toán tương thích so với Wrapper.

Một cấu hình ổn định thường xác định cả hai:

- Wrapper chỉ định phiên bản Gradle.
- Toolchain chỉ định phiên bản Java cần cho các task Java.

JDK chạy Gradle cũng phải phù hợp với phiên bản Gradle. Không thể dùng toolchain để khắc phục trường hợp JVM khởi động Gradle không được Gradle hỗ trợ.

## 8. Quy trình chọn và nâng cấp plugin an toàn

Khi thêm plugin mới hoặc nâng version, nên thực hiện theo một quy trình có thể kiểm tra:

### Bước 1: xác định nhu cầu

Xác định plugin cần cung cấp tính năng nào, project nào sử dụng và liệu plugin có thật sự cần thiết hay chức năng đã có trong Gradle core hoặc plugin hiện tại.

### Bước 2: kiểm tra nguồn phát hành

Xác minh plugin ID, repository, version và cách phát hành. Ưu tiên tài liệu chính thức hoặc repository đáng tin cậy. Với plugin nội bộ, xác định repository và cơ chế xác thực tương ứng.

### Bước 3: kiểm tra compatibility

Đối chiếu ít nhất các yếu tố:

- Phiên bản Gradle Wrapper hiện tại.
- JVM dùng để chạy Gradle.
- Java toolchain và mức Java mà project cần.
- Phiên bản plugin và các plugin có quan hệ với nó.
- Phiên bản framework/dependency mà plugin quản lý.
- Các thay đổi breaking change hoặc deprecated API trong release notes.

### Bước 4: quản lý version tập trung

Chọn một cơ chế quản lý version phù hợp như `pluginManagement`, `apply false`, Version Catalog hoặc convention plugin. Giữ các module dùng chung một version trừ khi có lý do kỹ thuật được ghi nhận.

### Bước 5: nâng cấp có kiểm soát

Thay đổi một nhóm version có liên quan, đọc hướng dẫn migration, xử lý cấu hình đã bị deprecated và chạy các task xác minh. Nếu có nhiều thay đổi lớn, chia thành các bước nhỏ để dễ xác định nguyên nhân khi build lỗi.

### Bước 6: xác nhận trên CI

Chạy cùng Wrapper và toolchain trên CI. Kiểm tra compile, test, package và các task đặc thù do plugin cung cấp. Một plugin chỉ cấu hình thành công nhưng task chính chưa chạy không thể được xem là đã xác minh đầy đủ.

## 9. Quản lý version plugin trong Maven

Maven cũng có plugin và version riêng. Plugin Maven thực hiện các goal được gắn vào lifecycle phase. Phiên bản plugin có thể được khai báo trực tiếp trong `build/plugins` hoặc quản lý tập trung trong `build/pluginManagement`.

### 9.1. Khai báo plugin trực tiếp

Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Khai báo này đưa Maven Compiler Plugin vào build với version và cấu hình rõ ràng. `release` điều khiển mức Java mà compiler nhắm tới; nó không phải phiên bản Maven hoặc phiên bản plugin.

### 9.2. Quản lý version bằng pluginManagement

Trong project nhiều module, parent POM có thể quản lý version và cấu hình plugin dùng chung:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>21</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Module con có thể khai báo plugin trong `build/plugins` để kích hoạt cấu hình đã được quản lý:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

`pluginManagement` định nghĩa version và cấu hình mặc định cho plugin khi được khai báo ở phạm vi build tương ứng; nó không tự động kích hoạt mọi plugin được liệt kê. Đây là điểm cần phân biệt với `<plugins>`, nơi plugin được đưa vào build của project.

### 9.3. Maven Wrapper và JDK

Maven Wrapper (`mvnw` hoặc `mvnw.cmd`) khóa phiên bản Maven cho project thông qua cấu hình trong `.mvn/wrapper/`. Wrapper giúp máy local và CI sử dụng cùng Maven distribution.

Maven vẫn chạy trong một JVM, nên JDK chạy Maven phải tương thích với phiên bản Maven và plugin đang dùng. Thuộc tính compiler như `maven.compiler.release` quyết định mức Java mà mã nguồn được biên dịch hướng tới; nó không thay thế yêu cầu JDK để khởi chạy Maven hoặc plugin.

## 10. Những lỗi thường gặp khi quản lý plugin

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| `Plugin ... was not found` | Sai ID/version hoặc thiếu plugin repository | Kiểm tra plugin ID, version và `pluginManagement.repositories` |
| Plugin yêu cầu Gradle mới hơn | Wrapper đang dùng quá cũ | Đối chiếu yêu cầu plugin và nâng Wrapper có kiểm soát |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | Plugin không tương thích với Gradle API/JVM hoặc xung đột classpath | Kiểm tra compatibility matrix, release notes và dependency plugin |
| Build chạy ở máy này nhưng lỗi ở máy khác | Gradle/JDK hoặc nguồn version khác nhau | Dùng Wrapper, toolchain và cấu hình tập trung; kiểm tra Gradle User Home |
| Các module dùng plugin version khác nhau | Khai báo version phân tán | Tập trung version trong Settings, catalog hoặc root build logic |
| Nâng plugin làm task cũ mất hoặc đổi hành vi | Breaking change hoặc cấu hình deprecated | Đọc migration guide và cập nhật cấu hình theo phiên bản mới |
| Plugin không tải được trong CI | Repository riêng, proxy hoặc credentials chưa cấu hình | Kiểm tra mạng và secret/repository credentials của CI |
| Plugin DSL không tìm thấy plugin nội bộ | Plugin không có marker hoặc chưa include build | Cấu hình resolution strategy, repository hoặc included build phù hợp |

Khi gặp lỗi, hãy xác định lỗi xảy ra ở bước phân giải plugin, áp dụng plugin, cấu hình project hay thực thi task. Các bước này có nguyên nhân khác nhau và cần cách điều tra khác nhau.

## 11. Một số lệnh hỗ trợ điều tra Gradle

```bash
# Xem phiên bản Gradle và JVM đang chạy Gradle
./gradlew --version

# Xem project và task sau khi plugin được áp dụng
./gradlew projects
./gradlew tasks --all

# Xem task cụ thể
./gradlew help --task test

# Chạy build với log chi tiết
./gradlew build --info

# Buộc task chạy lại để kiểm tra hành vi
./gradlew build --rerun-tasks
```

`./gradlew --version` cho biết Gradle version và JVM hiện dùng để chạy Gradle. Nó không nhất thiết cho biết mọi Java toolchain mà các task sẽ chọn. Để hiểu toolchain, hãy đọc cấu hình `java.toolchain` và log của các task liên quan.

Khi cần xác minh plugin cụ thể, nên kết hợp log build với tài liệu và release notes của plugin. Không nên kết luận plugin không tương thích chỉ từ một thông báo lỗi cuối cùng nếu chưa xác định được bước thất bại đầu tiên.

## 12. Ví dụ quản lý plugin tập trung trong một build nhiều module

Giả sử hai module `api` và `worker` cùng sử dụng Java plugin và Spring Boot plugin. Có thể dùng Version Catalog để quản lý version:

`gradle/libs.versions.toml`:

```toml
[versions]
spring-boot = "3.3.5"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
```

Root `build.gradle`:

```kotlin
plugins {
    alias(libs.plugins.spring.boot) apply false
}
```

`api/build.gradle`:

```kotlin
plugins {
    java
    alias(libs.plugins.spring.boot)
}
```

`worker/build.gradle`:

```kotlin
plugins {
    java
    alias(libs.plugins.spring.boot)
}
```

Hai module sử dụng cùng alias và do đó cùng version plugin. Khi cần nâng cấp, nhóm thay version reference trong catalog, kiểm tra tài liệu tương thích, rồi chạy pipeline để xác minh cả hai module.

Trong dự án thực tế, nếu plugin Spring Boot không cần áp dụng cho root project, `apply false` giúp root chỉ quản lý version. Nếu các module còn cần nhiều cấu hình chung, có thể tạo convention plugin để áp dụng Java, cấu hình toolchain, test và các quy tắc nội bộ tại một điểm.

## 13. Nguyên tắc quản lý plugin lâu dài

- **Ghi rõ version.** Tránh dựa vào version ngầm hoặc version động cho build cần tái lập.
- **Tập trung version.** Dùng Settings, Version Catalog hoặc convention build logic để giảm sai lệch giữa các module.
- **Phân biệt plugin và dependency ứng dụng.** Plugin phục vụ build; dependency ứng dụng phục vụ compile/runtime/test của phần mềm.
- **Phân biệt plugin repository với dependency repository.** Cấu hình đúng nơi Gradle tìm plugin và nơi tìm thư viện của project.
- **Khóa phiên bản Gradle bằng Wrapper.** Không dựa vào bản Gradle cài toàn cục trên từng máy.
- **Quản lý JDK riêng.** Xác định JVM chạy Gradle và Java toolchain cho task Java.
- **Kiểm tra tương thích trước khi nâng cấp.** Đọc yêu cầu Gradle/JDK, release notes và migration guide của plugin.
- **Nâng cấp có kiểm soát.** Thay đổi version theo nhóm có quan hệ và chạy compile, test, package cùng task đặc thù.
- **Dùng convention plugin cho quy tắc lặp lại.** Giữ build script module ngắn, rõ vai trò và nhất quán.
- **Xác minh trên CI.** Dùng cùng Wrapper và cấu hình đã quản lý để phát hiện khác biệt môi trường.

## 14. Bài tập vận dụng

Một build có ba module `api`, `worker` và `admin`. Cả ba dùng plugin Java, còn `api` và `worker` dùng thêm plugin framework. Hãy phân tích:

1. Nếu mỗi module khai báo một version framework khác nhau, những rủi ro nào có thể xuất hiện?
2. Nên đặt version plugin ở `pluginManagement`, root `plugins { ... apply false }` hay Version Catalog trong trường hợp này? Vì sao?
3. Repository nào cần cấu hình để Gradle tìm plugin? Repository nào tìm dependency của ứng dụng?
4. Nếu plugin mới yêu cầu Gradle version cao hơn Wrapper hiện tại, cần thay đổi những gì và kiểm tra điều gì trước khi nâng cấp?
5. Nếu Gradle chạy bằng JDK 21 nhưng project biên dịch bằng Java 17 toolchain, hai phiên bản này có ý nghĩa gì?
6. Làm thế nào xác minh plugin tương thích với các plugin khác trong cùng build?
7. Khi plugin nội bộ không có marker artifact, có những cách nào để Gradle phân giải implementation của nó?

Có thể thực hành bằng một build nhiều module nhỏ: tập trung version plugin vào một cơ chế, chạy `./gradlew --version`, `./gradlew projects`, `./gradlew tasks --all` và `./gradlew build`. Sau đó thay đổi version trong catalog hoặc Settings, đọc release notes và quan sát lỗi cấu hình/task nếu tổ hợp phiên bản không được hỗ trợ.

Khi quản lý plugin, hãy luôn xác định ba câu hỏi: **plugin nào đang được áp dụng, version được lấy từ đâu, và tổ hợp plugin–Gradle–JDK nào được hỗ trợ?** Trả lời được ba câu hỏi này giúp build có thể tái lập, nâng cấp có kiểm soát và giảm lỗi phát sinh từ khác biệt môi trường.

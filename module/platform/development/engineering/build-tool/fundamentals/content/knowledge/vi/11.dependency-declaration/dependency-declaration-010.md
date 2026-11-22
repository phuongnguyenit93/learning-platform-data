# Tập trung khai báo phiên bản và hạn chế cấu hình trùng lặp

Khi một dự án Java có nhiều module, cùng một thư viện có thể được khai báo ở nhiều `build.gradle` hoặc `pom.xml`. Nếu mỗi module tự ghi version, repository và các tùy chọn giống nhau, cấu hình nhanh chóng bị lặp. Một lần nâng cấp thư viện có thể phải sửa nhiều file; nếu bỏ sót một module, các phần của ứng dụng có thể dùng những version khác nhau.

Build tool cung cấp nhiều cơ chế để tổ chức cấu hình dùng chung. Trong Gradle, **Version Catalog** giúp tập trung tên và version dependency, **platform/BOM** giúp căn chỉnh version của một nhóm thư viện, còn cấu hình ở Settings hoặc convention plugin giúp thống nhất repository và quy ước giữa các module. Trong Maven, có thể dùng properties, `dependencyManagement`, BOM và parent POM để đạt mục tiêu tương tự.

Điều quan trọng là phân biệt từng cơ chế giải quyết vấn đề nào. Tập trung khai báo giúp tránh lặp lại thông tin; quản lý version trong dependency graph giúp các thư viện tương thích được chọn cùng nhau; convention plugin hoặc parent POM giúp các module tuân theo một quy tắc cấu hình chung.

## 1. Vì sao cần tập trung quản lý phiên bản?

Giả sử một build có ba module `api`, `worker` và `admin`. Cả ba đều dùng Jackson:

```groovy
// api/build.gradle
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}

// worker/build.gradle
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}

// admin/build.gradle
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

Ba khai báo này đang lặp cùng một tọa độ và version. Khi nâng Jackson lên version mới, người bảo trì phải tìm và sửa cả ba nơi. Nếu một module vẫn giữ version cũ, build có thể phân giải graph khác nhau theo module hoặc tạo ra hành vi khó dự đoán.

Những vấn đề thường gặp khi cấu hình bị lặp:

- **Khó nâng cấp:** một thay đổi version cần sửa nhiều file.
- **Lệch phiên bản:** các module vô tình dùng version khác nhau.
- **Khó review:** người đọc phải tìm nhiều nơi để biết chính sách version của dự án.
- **Cấu hình phân tán:** repository, exclusion, dependency constraint hoặc tùy chọn dùng chung có thể bị khai báo không nhất quán.
- **Khó tái lập:** máy local và CI có thể nhận cấu hình khác nhau nếu mỗi nơi bổ sung giá trị riêng.

Tập trung cấu hình làm cho version và quy ước dùng chung có một nơi quản lý rõ ràng. Các module vẫn khai báo những dependency mà chính chúng sử dụng, nhưng có thể tham chiếu cùng một nguồn version hoặc chính sách chung.

## 2. Các mức độ tập trung cấu hình

Không phải mọi loại cấu hình đều nên được gom vào cùng một cơ chế. Có thể phân biệt ba lớp:

| Lớp | Câu hỏi cần trả lời | Cơ chế tiêu biểu |
|---|---|---|
| Khai báo và đặt tên | Dependency nào được sử dụng, alias của nó là gì, version tham chiếu ở đâu? | Gradle Version Catalog, Maven properties |
| Căn chỉnh và giải quyết version | Các module thư viện liên quan cần dùng version nào trong dependency graph? | Gradle platform/BOM, dependency constraints, Maven BOM và `dependencyManagement` |
| Quy ước build dùng chung | Module nào dùng repository, plugin, toolchain hoặc cấu hình test nào? | Gradle Settings, convention plugin, root build logic; Maven parent POM |

Ví dụ, Version Catalog có thể định nghĩa alias `jackson-databind` và version `jackson`. Nhưng catalog không tự đưa thư viện vào classpath và cũng không thay thế cơ chế BOM để căn chỉnh một nhóm thư viện. Project vẫn phải khai báo dependency trong configuration thích hợp.

## 3. Gradle Version Catalog

### 3.1. Version Catalog là gì?

Version Catalog là một danh mục tập trung tên alias, tọa độ và version của dependency hoặc plugin. Catalog mặc định của Gradle thường được đặt tại `gradle/libs.versions.toml`. Gradle tự động nạp file mặc định này thành catalog tên `libs`.

Các build script có thể dùng accessor được sinh ra để tham chiếu dependency mà không phải lặp lại tọa độ và version.

### 3.2. Khai báo version và library trong TOML

Ví dụ file `gradle/libs.versions.toml`:

```toml
[versions]
jackson = "2.17.2"
slf4j = "2.0.13"
junit = "5.10.3"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
jackson-core = { module = "com.fasterxml.jackson.core:jackson-core", version.ref = "jackson" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
```

File này có hai phần chính:

- `[versions]` đặt các version có tên để tái sử dụng.
- `[libraries]` định nghĩa alias cho module và tham chiếu version bằng `version.ref`.

`module` chứa tọa độ `group:artifact`. Khi version được tham chiếu bằng `version.ref`, alias dùng version đã khai báo trong phần `[versions]`.

### 3.3. Sử dụng alias trong build script

Với Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation(libs.jackson.databind)
    implementation(libs.slf4j.api)
    testImplementation(libs.junit.jupiter)
}
```

Với Groovy DSL (`build.gradle`):

```groovy
dependencies {
    implementation libs.jackson.databind
    implementation libs.slf4j.api
    testImplementation libs.junit.jupiter
}
```

Gradle tạo accessor từ alias. Dấu gạch ngang trong tên alias được chuyển thành các phần accessor lồng nhau; ví dụ `jackson-databind` có thể được truy cập qua `libs.jackson.databind`.

Khi cần nâng Jackson, chỉ cần cập nhật version:

```toml
[versions]
jackson = "2.18.0"
```

Các alias dùng `version.ref = "jackson"` sẽ tham chiếu version mới. Không cần sửa từng module đang sử dụng alias.

### 3.4. Alias không tự thêm dependency vào project

Một mục trong catalog chỉ là định nghĩa có thể tham chiếu. Khai báo alias trong TOML không có nghĩa tất cả project đều tự động có thư viện đó. Project cần sử dụng nó vẫn phải khai báo:

```groovy
dependencies {
    implementation libs.jackson.databind
}
```

Configuration `implementation`, `testImplementation`, `runtimeOnly` hoặc configuration khác tiếp tục quyết định phạm vi sử dụng. Catalog chỉ giúp tập trung cách mô tả dependency.

### 3.5. Dùng version trực tiếp hoặc version reference

Một library alias có thể chứa version trực tiếp:

```toml
[libraries]
some-library = { module = "com.example:some-library", version = "1.4.0" }
```

Hoặc tham chiếu version dùng chung:

```toml
[versions]
some-library = "1.4.0"

[libraries]
some-library = { module = "com.example:some-library", version.ref = "some-library" }
```

Nếu nhiều module của cùng một thư viện hoặc nhiều alias cần dùng chung một version, `version.ref` giúp giảm lặp. Nếu một artifact có version độc lập và chỉ được dùng ở một nơi, version trực tiếp cũng có thể dễ hiểu. Điều quan trọng là giữ chính sách version rõ ràng và tránh tạo quá nhiều tên version không cần thiết.

### 3.6. Dùng bundle để nhóm dependency thường đi cùng nhau

Catalog hỗ trợ bundle, cho phép nhóm nhiều alias thành một tập hợp có tên:

```toml
[versions]
jackson = "2.17.2"
slf4j = "2.0.13"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }

[bundles]
json-logging = ["jackson-databind", "slf4j-api"]
```

Project có thể khai báo bundle:

```groovy
dependencies {
    implementation libs.bundles.json.logging
}
```

Bundle giúp giảm số dòng khai báo khi một nhóm thư viện thường được sử dụng cùng nhau. Tuy nhiên, bundle vẫn chỉ là cách nhóm các dependency declaration. Nó không tạo ra một platform và không đảm bảo các thư viện có version tương thích với nhau.

Không nên tạo bundle quá rộng hoặc gộp các dependency chỉ tình cờ xuất hiện cùng nhau. Bundle nên đại diện cho một nhóm có ý nghĩa trong cách sử dụng của project.

### 3.7. Dùng catalog cho nhiều module

Các project trong cùng Gradle build có thể dùng catalog `libs` mặc định. Khi mỗi module có build script riêng, chúng vẫn có thể tham chiếu cùng alias:

```groovy
// api/build.gradle
dependencies {
    implementation libs.jackson.databind
}

// worker/build.gradle
dependencies {
    implementation libs.jackson.databind
    testImplementation libs.junit.jupiter
}
```

Hai module sử dụng cùng alias và do đó cùng định nghĩa version trong catalog. Mỗi module vẫn quyết định dependency nào thực sự cần thiết.

### 3.8. Catalog bổ sung hoặc catalog từ file khác

Gradle cho phép tạo thêm version catalog trong Settings:

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    versionCatalogs {
        create("testLibs") {
            from(files("gradle/test-libs.versions.toml"))
        }
    }
}
```

Sau đó, build script có thể dùng catalog `testLibs` với accessor tương ứng. Thông thường, một catalog `libs` rõ ràng đã đủ cho đa số dự án. Chỉ tạo nhiều catalog khi có ranh giới quản lý hợp lý, ví dụ danh mục công cụ kiểm thử riêng hoặc catalog dùng chung được nhập từ một build convention.

## 4. Dùng platform và BOM để căn chỉnh version

### 4.1. Catalog và BOM giải quyết hai vấn đề khác nhau

Version Catalog tập trung tọa độ, alias và version để build script không lặp chuỗi dependency. BOM (Bill of Materials) hoặc platform mô tả một tập version tương thích của nhiều module.

Ví dụ, một framework có nhiều module như core, web, security và test. Nhà phát hành framework có thể cung cấp BOM để chỉ định các version được thiết kế để hoạt động cùng nhau. Nếu tự đặt version từng module trong catalog, project vẫn có thể vô tình trộn các version không tương thích.

Khi đó, BOM/platform là nguồn chính sách version cho dependency graph. Catalog vẫn có thể dùng để đặt alias cho các dependency mà project khai báo.

### 4.2. Import Maven BOM trong Gradle

Gradle có thể sử dụng Maven BOM thông qua `platform(...)`:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

BOM cung cấp dependency constraints để các module Spring Boot được căn chỉnh version. Các starter vẫn phải được khai báo nếu project muốn sử dụng chúng. Chỉ import BOM không tự đưa tất cả dependency trong BOM vào classpath.

Nếu muốn tập trung version BOM trong catalog, có thể khai báo:

```toml
[versions]
spring-boot = "3.3.5"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-validation = { module = "org.springframework.boot:spring-boot-starter-validation" }
```

Sau đó dùng trong build script:

```groovy
dependencies {
    implementation platform(libs.spring.boot.bom)
    implementation libs.spring.boot.web
    implementation libs.spring.boot.validation
}
```

Trong ví dụ, catalog giữ tọa độ và version BOM, còn BOM cung cấp các version được quản lý cho starter. Hai cơ chế phối hợp nhưng không thay thế nhau.

### 4.3. Tạo platform riêng cho tổ chức

Nếu tổ chức có nhiều project cần dùng một nhóm version chung, có thể tạo Gradle platform project bằng plugin `java-platform`:

```groovy
// platform/build.gradle
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api 'org.slf4j:slf4j-api:2.0.13'
        api 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
        api 'org.junit.jupiter:junit-jupiter:5.10.3'
    }
}
```

Các module sử dụng platform:

```groovy
dependencies {
    implementation platform(project(':platform'))
    implementation 'org.slf4j:slf4j-api'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

Platform công bố version constraints. Module tiêu thụ khai báo các dependency thực sự sử dụng nhưng có thể không cần lặp version vì platform đã quản lý chúng.

Platform là một project chuyên quản lý version, không phải ứng dụng thông thường. Nó hữu ích khi một tổ chức muốn phát hành bộ version chuẩn cho nhiều module hoặc nhiều repository.

### 4.4. Dependency constraints

Khi không cần một BOM đầy đủ, Gradle cho phép khai báo constraint:

```groovy
dependencies {
    constraints {
        implementation('com.fasterxml.jackson.core:jackson-core:2.17.2') {
            because 'Align Jackson modules to the same release line'
        }
    }
}
```

Constraint ảnh hưởng đến version được chọn nếu module đó xuất hiện trong graph. Bản thân constraint không nhất thiết thêm module vào graph. Đây là điểm khác với khai báo dependency:

- Dependency declaration yêu cầu module có mặt trong configuration.
- Dependency constraint cung cấp quy tắc version cho module khi nó được yêu cầu.

Không nên dùng constraint thay cho dependency declaration khi project trực tiếp cần API của thư viện.

### 4.5. Platform thường và enforcedPlatform

Gradle có `platform(...)` và `enforcedPlatform(...)`. Platform thông thường đưa các constraints vào resolution; các yêu cầu khác trong graph vẫn có thể ảnh hưởng đến version được chọn theo quy tắc Gradle. `enforcedPlatform` áp đặt version mạnh hơn và có thể truyền ảnh hưởng đó tới project tiêu thụ.

Chỉ dùng `enforcedPlatform` khi thực sự cần chính sách version bắt buộc và đã hiểu ảnh hưởng tới consumer. Với thư viện được phát hành để project khác sử dụng, một enforced platform có thể áp đặt lựa chọn mà consumer không mong muốn. Trong nhiều trường hợp, platform thông thường hoặc constraints là lựa chọn linh hoạt hơn.

## 5. Tập trung repository và cấu hình dependency trong Gradle

### 5.1. Khai báo repository ở Settings

Trong build nhiều module, nếu mỗi `build.gradle` tự khai báo `mavenCentral()`, cấu hình repository bị lặp. Gradle cho phép quản lý repository dependency ở cấp Settings:

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven {
            url = uri("https://repo.example.com/releases")
        }
    }
}

rootProject.name = "order-platform"
include("api", "worker", "admin")
```

Khi repository được quản lý ở Settings, các project có thể dùng chung danh sách repository. `dependencyResolutionManagement` cũng hỗ trợ `repositoriesMode` để quyết định cách xử lý khi project tự khai báo repository.

Ví dụ:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
```

`FAIL_ON_PROJECT_REPOS` làm build thất bại nếu project tự khai báo repository, giúp enforce chính sách tập trung. Các mode khác có hành vi khác nhau; hãy chọn theo mức kiểm soát mà tổ chức muốn.

### 5.2. Phân biệt repository plugin và repository dependency

Repository cho plugin được cấu hình trong `pluginManagement.repositories`. Repository cho thư viện của project được cấu hình trong `dependencyResolutionManagement.repositories` hoặc `repositories` của project.

```kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

Tập trung repository giúp mọi module dùng cùng nguồn artifact, giảm tình trạng một module tìm thư viện ở repository riêng mà module khác không biết. Với repository nội bộ, cần quản lý credentials qua cơ chế bảo mật của môi trường build; không ghi token hoặc mật khẩu vào file được commit.

## 6. Maven properties để giảm lặp version

### 6.1. Dùng property cho version

Trong Maven, có thể khai báo version dưới `<properties>`:

```xml
<properties>
    <jackson.version>2.17.2</jackson.version>
    <slf4j.version>2.0.13</slf4j.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>${jackson.version}</version>
    </dependency>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>${slf4j.version}</version>
    </dependency>
</dependencies>
```

Khi nâng Jackson, chỉ cần thay `<jackson.version>`. Mọi dependency tham chiếu property này sẽ dùng version mới.

Properties giúp giảm lặp chuỗi version, nhưng mỗi module vẫn có thể phải khai báo tọa độ dependency và tham chiếu property. Trong build nhiều module, parent POM và `dependencyManagement` có thể tập trung hơn nữa.

### 6.2. Parent POM và dependencyManagement

Parent POM có thể quản lý version dependency cho các module con:

```xml
<!-- Parent pom.xml -->
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>order-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <jackson.version>2.17.2</jackson.version>
        <slf4j.version>2.0.13</slf4j.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson.core</groupId>
                <artifactId>jackson-databind</artifactId>
                <version>${jackson.version}</version>
            </dependency>
            <dependency>
                <groupId>org.slf4j</groupId>
                <artifactId>slf4j-api</artifactId>
                <version>${slf4j.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <modules>
        <module>api</module>
        <module>worker</module>
    </modules>
</project>
```

Module con có thể khai báo dependency mà không lặp version:

```xml
<!-- api/pom.xml -->
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

`dependencyManagement` cung cấp version và cấu hình quản lý cho dependency khi module con khai báo nó. Nó không tự thêm dependency vào classpath của mọi module. Module nào cần Jackson vẫn phải khai báo trong `<dependencies>`.

### 6.3. Import BOM trong Maven

Khi một framework cung cấp BOM, parent POM có thể import BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó module có thể khai báo starter mà không cần lặp version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

BOM tập trung version của một hệ sinh thái thư viện. Parent POM tập trung cấu hình cho các module con của dự án. Hai cơ chế có thể được kết hợp: parent POM import BOM và các module kế thừa parent.

### 6.4. `dependencies` và `dependencyManagement` khác nhau

| Phần POM | Chức năng |
|---|---|
| `<dependencies>` | Khai báo dependency thực sự của project |
| `<dependencyManagement>` | Quản lý version, scope và cấu hình mặc định cho dependency khi nó được khai báo hoặc kế thừa trong phạm vi phù hợp |
| `<properties>` | Đặt giá trị có tên để tham chiếu lại trong POM |
| BOM import | Nhập một bộ quy tắc quản lý dependency từ POM khác |

Một dependency xuất hiện trong `dependencyManagement` không tự động trở thành dependency trực tiếp. Điều này tương tự sự khác biệt giữa version catalog/constraint và dependency declaration trong Gradle: nơi quản lý version không nhất thiết là nơi yêu cầu thư viện xuất hiện trong classpath.

## 7. Tập trung plugin và cấu hình build dùng chung

Ngoài dependency version, build nhiều module thường lặp lại repository, Java toolchain, test options và plugin. Có thể tổ chức các phần này ở phạm vi phù hợp.

### 7.1. Gradle convention plugin

Convention plugin đóng gói cấu hình dùng chung cho một loại module. Ví dụ, các Java library trong tổ chức đều cần Java 21, JUnit Platform và một số quy tắc kiểm tra.

Một convention plugin có thể áp dụng Java Library plugin, cấu hình toolchain và test. Các module chỉ cần áp dụng convention plugin thay vì lặp lại toàn bộ cấu hình.

```groovy
// Trong build-logic/src/main/groovy/company.java-library-conventions.gradle
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Module áp dụng:

```groovy
plugins {
    id 'company.java-library-conventions'
}
```

Convention plugin phù hợp để chia sẻ **cách cấu hình**. Version Catalog phù hợp để chia sẻ **tên và version dependency**. Có thể dùng cả hai: convention plugin áp dụng cấu hình chuẩn và tham chiếu dependency alias từ catalog.

### 7.2. Maven parent POM

Parent POM có thể quản lý:

- `properties` dùng chung.
- `dependencyManagement`.
- `pluginManagement`.
- Cấu hình compiler, test và các plugin khác.
- Repository hoặc distribution management theo chính sách tổ chức.

Các module kế thừa parent có thể dùng cấu hình đó mà không phải sao chép mọi phần vào từng POM. Tuy nhiên, parent POM quá lớn hoặc chứa nhiều cấu hình không liên quan có thể làm module con khó hiểu. Nên giữ parent tập trung vào quy ước thực sự dùng chung.

## 8. Tránh cấu hình trùng lặp nhưng vẫn giữ dependency rõ ràng

Tập trung version không có nghĩa gom toàn bộ dependency của mọi module vào một danh sách rồi áp dụng cho tất cả. Mỗi module vẫn nên khai báo đúng những thư viện nó sử dụng.

Ví dụ, `api` cần Jackson nhưng `worker` chỉ cần SLF4J. Cả hai có thể dùng cùng catalog:

```groovy
// api/build.gradle
dependencies {
    implementation libs.jackson.databind
}

// worker/build.gradle
dependencies {
    implementation libs.slf4j.api
}
```

Catalog giúp cả hai dùng chung nguồn version. Nó không buộc worker phải nhận Jackson hoặc api phải nhận JUnit nếu không cần.

Những nguyên tắc nên giữ:

- **Tập trung version, phân tán dependency declaration theo module.** Mỗi module khai báo những gì nó thực sự dùng.
- **Dùng BOM/platform cho nhóm thư viện cần căn chỉnh.** Không tự đồng bộ các version không liên quan chỉ vì chúng cùng xuất hiện trong một catalog.
- **Dùng convention plugin cho cấu hình lặp lại.** Tránh sao chép các khối task, toolchain và test options.
- **Giữ repository theo chính sách chung.** Tránh mỗi module thêm repository tùy ý mà không có lý do.
- **Không tạo alias hoặc bundle quá mức.** Tên cần phản ánh thành phần và mục đích sử dụng.
- **Không khai báo version ở nhiều tầng mà không hiểu độ ưu tiên.** Nếu catalog, platform và constraint cùng tác động một module, cần xem kết quả resolution thực tế.

## 9. Các lỗi thường gặp khi tập trung quản lý version

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| `libs.some.library` không được nhận diện | Alias sai hoặc catalog chưa được nạp | Kiểm tra TOML, tên alias và accessor được sinh ra |
| Module vẫn dùng version cũ | Build script còn khai báo version trực tiếp hoặc dùng catalog khác | Tìm mọi khai báo, xác định nguồn version có hiệu lực |
| BOM không thêm thư viện vào classpath | BOM chỉ quản lý version, không khai báo dependency sử dụng | Khai báo library trong `dependencies` hoặc `<dependencies>` |
| Các module vẫn resolve version khác nhau | Platform không được áp dụng vào configuration cần thiết hoặc graph khác nhau | Kiểm tra configuration và dependencyInsight |
| Một module có dependency thừa | Dùng chung bundle hoặc convention quá rộng | Giữ dependency declaration theo nhu cầu của module |
| Gradle báo repository project bị cấm | `repositoriesMode` đang enforce Settings repository | Chuyển repository về Settings hoặc điều chỉnh policy có chủ đích |
| Maven module không nhận version được quản lý | Module không kế thừa parent hoặc không import BOM đúng phạm vi | Kiểm tra parent relationship và `dependencyManagement` |
| Version bị ghi đè ngoài dự kiến | Constraint, platform hoặc dependency declaration cùng tác động | Xem dependency graph và lý do version được chọn |

## 10. Kiểm tra dependency sau khi tập trung cấu hình

Sau khi chuyển version sang catalog hoặc BOM, hãy xác nhận dependency graph vẫn đúng.

### 10.1. Gradle

```bash
# Xem dependency của một module
./gradlew :api:dependencies

# Xem runtime classpath
./gradlew :api:dependencies --configuration runtimeClasspath

# Truy tìm lý do một version được chọn
./gradlew :api:dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath

# Chạy kiểm tra của build
./gradlew build
```

`dependencies` hiển thị graph của configuration. `dependencyInsight` cho biết các yêu cầu version, đường dẫn và lý do Gradle chọn version cụ thể. Dùng lệnh trên từng module khi cần xác nhận các module thực sự nhận cùng chính sách version.

### 10.2. Maven

```bash
# Xem dependency tree
./mvnw dependency:tree

# Xem dependency tree của module cụ thể trong reactor build
./mvnw -pl api dependency:tree

# Chạy kiểm tra đến verify
./mvnw verify
```

`dependency:tree` giúp xác nhận dependency trực tiếp, bắc cầu, scope và version được chọn. Khi version được quản lý qua parent POM hoặc BOM, hãy kiểm tra tree của từng module tiêu thụ.

## 11. Quản lý nâng cấp version và tính tái lập

Tập trung version giúp thay đổi dễ hơn, nhưng nâng cấp vẫn cần được kiểm tra. Một version mới có thể thay đổi API, hành vi hoặc dependency bắc cầu.

### 11.1. Nâng cấp theo nhóm có liên quan

Nếu nhiều module thuộc cùng một hệ sinh thái, hãy nâng BOM/platform hoặc version reference chung. Đọc release notes để biết các breaking change và yêu cầu JDK/Gradle mới. Chạy compile, test và package cho các module bị ảnh hưởng.

Không nên nâng tất cả dependency cùng lúc nếu dự án có nhiều thư viện độc lập và không có kế hoạch kiểm thử phù hợp. Chia thay đổi theo nhóm giúp dễ tìm nguyên nhân khi build hoặc test thất bại.

### 11.2. Dependency locking

Gradle dependency locking có thể ghi nhận version đã được phân giải cho các configuration được khóa. Nhờ đó, build không tự chuyển sang version mới chỉ vì metadata trong repository thay đổi.

Locking bổ sung cho Version Catalog hoặc platform:

- Catalog giúp tập trung version và alias.
- Platform/BOM căn chỉnh version liên quan.
- Locking ghi nhận kết quả resolution đã chọn.

Khi nâng cấp có chủ đích, nhóm cập nhật lock state và review diff để biết chính xác những module nào đổi version.

### 11.3. Dependency verification

Gradle dependency verification hỗ trợ kiểm tra checksum hoặc chữ ký của artifact đã tải. Cơ chế này giúp phát hiện artifact không khớp với dữ liệu đã được tin cậy. Nó giải quyết tính toàn vẹn của artifact, không thay thế catalog, BOM hoặc locking.

### 11.4. Không dùng version động cho build cần tái lập

Các khai báo như `1.+` hoặc `latest.release` có thể khiến lần chạy sau chọn version khác khi repository xuất hiện release mới. Dù version được tập trung ở một file, version động vẫn có thể làm kết quả thay đổi theo thời điểm.

Với build cần tái lập, ưu tiên version cụ thể, platform/BOM có version rõ ràng và dependency locking khi phù hợp. Việc cập nhật nên là một thay đổi được review và kiểm thử.

## 12. Ví dụ hoàn chỉnh: Gradle multi-project dùng catalog và platform

Giả sử build có ba project:

```text
order-platform/
├── settings.gradle
├── build.gradle
├── gradle/
│   └── libs.versions.toml
├── platform/
│   └── build.gradle
├── api/
│   └── build.gradle
└── worker/
    └── build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'order-platform'
include 'platform', 'api', 'worker'

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

`gradle/libs.versions.toml`:

```toml
[versions]
jackson = "2.17.2"
slf4j = "2.0.13"
junit = "5.10.3"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
```

`platform/build.gradle`:

```groovy
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api libs.jackson.databind
        api libs.slf4j.api
        api libs.junit.jupiter
    }
}
```

`api/build.gradle`:

```groovy
plugins {
    id 'java'
}

dependencies {
    implementation platform(project(':platform'))
    implementation libs.jackson.databind
    implementation libs.slf4j.api
}
```

`worker/build.gradle`:

```groovy
plugins {
    id 'java'
}

dependencies {
    implementation platform(project(':platform'))
    implementation libs.slf4j.api
    testImplementation libs.junit.jupiter
}
```

Trong ví dụ:

- Catalog tập trung tọa độ và version của Jackson, SLF4J và JUnit.
- Platform project công bố constraints dùng chung cho các module.
- `api` chỉ khai báo dependency nó cần là Jackson và SLF4J.
- `worker` chỉ khai báo SLF4J và JUnit trong phạm vi test.
- Repository Maven Central được cấu hình tập trung ở Settings.

Khi nâng Jackson, thay version trong catalog rồi kiểm tra graph và chạy build. Các module tham chiếu catalog và platform sẽ sử dụng chính sách version mới theo cấu hình.

## 13. Ví dụ hoàn chỉnh: Maven parent POM và BOM

Một cấu trúc Maven nhiều module có thể dùng parent POM:

```text
order-platform/
├── pom.xml
├── api/
│   └── pom.xml
└── worker/
    └── pom.xml
```

Parent POM quản lý version và import BOM:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>order-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <spring-boot.version>3.3.5</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <modules>
        <module>api</module>
        <module>worker</module>
    </modules>
</project>
```

Module `api` khai báo dependency cần dùng mà không lặp version:

```xml
<project>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>order-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>api</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
```

Module `worker` có thể khai báo starter khác từ cùng BOM. Version Spring Boot chỉ được quản lý tại parent POM, còn mỗi module khai báo dependency thực sự cần dùng.

## 14. Lựa chọn cơ chế nào cho tình huống nào?

| Nhu cầu | Gradle | Maven |
|---|---|---|
| Tập trung tọa độ và version | Version Catalog | Properties và dependencyManagement |
| Đặt version cho một nhóm thư viện tương thích | Platform/BOM | Import BOM trong dependencyManagement |
| Quản lý version đã phân giải | Dependency locking | Quản lý version trong parent/BOM và cơ chế build phù hợp |
| Tập trung repository | `dependencyResolutionManagement` trong Settings | Repository ở parent POM hoặc Settings của Maven theo chính sách tổ chức |
| Chia sẻ quy tắc cấu hình build | Convention plugin | Parent POM và pluginManagement |
| Xem dependency graph | `dependencies`, `dependencyInsight` | `dependency:tree` |

Không có một cơ chế duy nhất giải quyết mọi vấn đề. Chọn công cụ theo mục tiêu: catalog/properties giảm lặp khai báo; BOM/platform đồng bộ version; parent/convention plugin chia sẻ quy ước; locking giúp giữ kết quả resolution ổn định.

## 15. Nguyên tắc duy trì cấu hình tập trung

- **Có một nguồn version dễ tìm.** Người bảo trì nên biết cần sửa file nào khi nâng thư viện.
- **Module tự khai báo nhu cầu của mình.** Đừng thêm dependency không cần thiết vào mọi module chỉ để giảm số dòng cấu hình.
- **Dùng BOM/platform cho bộ thư viện liên quan.** Không tự tạo một danh sách version chung thiếu căn cứ tương thích.
- **Không nhầm quản lý version với khai báo dependency.** Catalog, constraint và dependencyManagement không nhất thiết làm thư viện xuất hiện trong classpath.
- **Tập trung repository theo chính sách.** Hạn chế repository tùy tiện và quản lý credentials an toàn.
- **Dùng convention plugin hoặc parent POM cho cấu hình lặp lại.** Tránh sao chép toolchain, test options và plugin configuration.
- **Tránh nhiều nguồn ghi đè không rõ ràng.** Nếu catalog, BOM, constraint và khai báo trực tiếp cùng tác động, hãy kiểm tra version thực sự được chọn.
- **Review thay đổi version.** Đọc release notes, kiểm tra compatibility và chạy test sau khi nâng cấp.
- **Giữ build có thể tái lập.** Dùng version cụ thể, locking hoặc verification khi mức độ ổn định của dự án yêu cầu.

## 16. Bài tập vận dụng

Một hệ thống có bốn module `api`, `worker`, `admin` và `reporting`. Cả bốn đều dùng SLF4J; `api` và `reporting` dùng Jackson; `worker` dùng JUnit trong test. Nhóm muốn nâng SLF4J và Jackson nhưng tránh sửa nhiều file.

Hãy xác định:

1. Những version nào nên được khai báo tập trung trong Gradle Version Catalog?
2. Mỗi module vẫn cần khai báo những dependency nào trong configuration của nó?
3. Nếu các module Jackson cần cùng một release line, khi nào nên dùng BOM/platform?
4. Vì sao Version Catalog không tự đảm bảo các module Jackson tương thích với nhau?
5. Có thể dùng Settings để quản lý repository chung như thế nào?
6. Nếu dùng Maven, nên đặt version trong properties, parent `dependencyManagement` hay import BOM trong trường hợp nào?
7. Sau khi nâng version, dùng lệnh nào để xác nhận dependency graph và version được chọn?
8. Dependency locking và dependency verification giải quyết hai vấn đề gì khác nhau?

Có thể thực hành bằng cách tạo `libs.versions.toml`, khai báo alias và tham chiếu trong hai module. Sau đó thêm một platform, chạy `./gradlew dependencies` và `./gradlew dependencyInsight` để quan sát tác động của catalog và platform. Với Maven, thử chuyển version sang parent POM rồi chạy `./mvnw dependency:tree`.

Khi cấu hình build bắt đầu lặp lại giữa nhiều module, hãy xác định phần nào là version, phần nào là chính sách căn chỉnh dependency và phần nào là quy ước build. Đặt mỗi loại thông tin vào cơ chế phù hợp giúp việc nâng cấp có một điểm kiểm soát rõ ràng, trong khi từng module vẫn thể hiện đúng những thư viện mà nó thực sự cần.

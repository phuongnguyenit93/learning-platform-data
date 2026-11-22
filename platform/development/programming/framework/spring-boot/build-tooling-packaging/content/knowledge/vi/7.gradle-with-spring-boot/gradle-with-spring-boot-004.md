# Quản lý phiên bản plugin qua pluginManagement và apply false trong Gradle

## 1. Mục tiêu và bối cảnh

Một dự án Spring Boot có thể gồm nhiều Gradle subproject: **:app** là ứng dụng Spring Boot tạo executable JAR; **:core** là thư viện Java bình thường. Khi mỗi module tự khai báo phiên bản plugin, chúng có thể vô tình sử dụng Spring Boot Gradle Plugin khác nhau, hoặc module thư viện bị áp dụng plugin Boot và nhận những task không cần thiết.

Gradle có hai cách phổ biến để **quản lý phiên bản plugin tập trung**:

1. **pluginManagement { ... }** trong **settings.gradle**: xác định kho phân giải plugin, phiên bản mặc định cho mỗi plugin ID và quy tắc plugin resolution của build.
2. **apply false** trong **plugins { ... }** của **root build.gradle**: Gradle phân giải plugin và đưa vào plugin classpath, **nhưng chưa áp dụng** nó cho root; mỗi subproject cần plugin thì yêu cầu nó bằng ID.

Hai cơ chế giúp chia sẻ phiên bản mà vẫn để **mỗi project tự quyết định plugin nào được áp dụng**. Chúng không thay thế việc khai báo dependency ứng dụng, BOM hoặc cấu hình Java.

Bài sử dụng **Gradle 8.5, Java 17, Spring Boot Gradle Plugin 3.3.5 và io.spring.dependency-management 1.1.6** làm bộ phiên bản minh họa. Đây là ví dụ có chủ đích cho Gradle 8.x/Spring Boot 3.3, không phải khẳng định phiên bản mới nhất. Khi sử dụng phiên bản mới, kiểm tra yêu cầu tương thích giữa Gradle Wrapper, JDK, Spring Boot và plugin.

## 2. Plugin khác dependency ứng dụng

Xem một phần **build.gradle** của ứng dụng Spring Boot:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Trong ví dụ:

- **plugins** chứa các **Gradle plugins**. Plugin có thể tạo task, extension và quy tắc build. **id 'java'** là core plugin đã có trong Gradle, vì vậy không ghi version. **org.springframework.boot** là plugin bên ngoài cần phiên bản cụ thể hoặc thông tin version từ cấu hình chung.
- **dependencies** chứa **thư viện ứng dụng**. Starter là dependency được code Java sử dụng khi chạy, không phải Gradle plugin.
- **repositories { mavenCentral() }** trong build.gradle dành để phân giải dependency của project. Kho phân giải **plugins DSL** được cấu hình riêng qua **pluginManagement.repositories** (hoặc mặc định Gradle Plugin Portal).
- **io.spring.dependency-management** là một plugin hỗ trợ quản lý phiên bản dependency thông qua BOM; không được nhầm tên nó với khối **pluginManagement** trong settings.gradle.

**Quy tắc cơ bản:** Version của **plugin** ảnh hưởng đến logic Gradle dùng để build. Version của **dependency** ảnh hưởng đến các thư viện xuất hiện trên compile/runtime classpath. Không thể đổi một loại bằng cách sửa cấu hình của loại còn lại.

## 3. Gradle xử lý các khối cấu hình theo thứ tự nào?

~~~text
./gradlew :app:bootJar
          |
          v
Initialization
  ├── Đọc settings.gradle
  ├── pluginManagement: plugin repos, versions, resolution rules
  └── Đọc rootProject.name, include 'app', 'core'
          |
          v
Configuration
  ├── Đọc build.gradle của root và các subproject
  ├── Resolve/apply plugin trong plugins của từng project
  ├── :app nhận Java, Spring Boot, dependency-management
  └── :core chỉ nhận java-library
          |
          v
Execution
  └── Chạy task graph của :app:bootJar
~~~

**pluginManagement phải là khối đầu tiên trong settings.gradle(.kts)** khi file có khối đó, bởi nó cấu hình plugin resolution từ sớm. Khối **plugins { ... }** trong một **build.gradle** là yêu cầu áp dụng plugin trên **Project tương ứng**. Khối **plugins { ... }** đứng trực tiếp trong **settings.gradle** lại dành cho **Settings plugins**, không tự áp dụng plugin Boot cho các subproject.

**Chú ý cú pháp:** Plugins DSL trong build.gradle có các quy tắc chặt chẽ về vị trí và biểu thức. Nó phải ở đầu script theo quy định và không được đặt trong vòng lặp hoặc câu điều kiện tùy ý. Khi cần lấy version từ property/logic động, **pluginManagement** là vị trí phù hợp hơn.

Plugin resolution thường đi theo cơ chế **plugin ID → plugin marker artifact → plugin implementation**. Gradle tìm plugin trên repository được phép, chọn version, đưa plugin vào classpath và áp dụng plugin theo yêu cầu của build script. Mỗi bước có ý nghĩa khác nhau khi chẩn đoán lỗi.

## 4. Cách A: khai báo phiên bản mặc định bằng pluginManagement

Tạo build có hai module: **app** chạy Spring Boot, **core** là thư viện Java. File **settings.gradle** (Groovy DSL) ở thư mục gốc:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version '3.3.5'
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

Mỗi phần có vai trò riêng:

1. **pluginManagement.repositories**: chỉ ra nơi Gradle tìm plugin. Trong ví dụ, đó là Gradle Plugin Portal. Nếu tự khai báo danh sách repository, nên đưa **gradlePluginPortal()** vào danh sách khi vẫn muốn dùng portal này.
2. **pluginManagement.plugins**: ánh xạ **plugin ID → version mặc định** cho các yêu cầu plugin không ghi version.
3. **rootProject.name**: tên root project; không quyết định phiên bản plugin.
4. **include 'app', 'core'**: cho Gradle biết hai subproject thuộc build; không có nghĩa hai subproject tự dùng plugin Boot.

Điểm quan trọng: **pluginManagement.plugins không tự apply plugin**. Khai báo version Spring Boot ở settings chỉ cung cấp thông tin cho những project sau này có **plugins { id 'org.springframework.boot' }**.

### 4.1. app/build.gradle: ứng dụng Spring Boot

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **toàn bộ build.gradle** mẫu cho app. Hai plugin bên ngoài **không ghi version trong app** vì settings.gradle đã cung cấp version mặc định. App thật sự áp dụng **org.springframework.boot**, do đó có task Boot như **bootJar** và **bootRun** khi kết hợp với Java plugin.

Vì app còn áp dụng **io.spring.dependency-management**, Spring Boot Gradle Plugin tự tích hợp **spring-boot-dependencies BOM** cho app. Các dependency Spring Boot được BOM quản lý có thể không cần version ở dependencies block; việc này là **dependency version management**, hoàn toàn khác với pluginManagement.

### 4.2. core/build.gradle: thư viện Java thuần

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đây là **toàn bộ build.gradle** cho core của ví dụ không có dependency ngoài. Plugin **java-library** đã mang theo chức năng Java plugin; core có thể tạo **jar** thông thường và được app phụ thuộc bằng **project(':core')**.

Core **không áp dụng** Boot plugin mặc dù settings đã chứa version Boot. Vì vậy core **không có bootJar**. Đây là ranh giới đúng: ứng dụng tạo executable Spring Boot JAR; thư viện chia sẻ xuất JAR thường.

### 4.3. “Version mặc định” không có nghĩa “khóa tuyệt đối”

PluginManagement.plugins cung cấp **mặc định** khi plugin request không ghi version. Nó **không phải cơ chế bắt buộc mọi module tuyệt đối không thể yêu cầu version khác**. Nếu cần enforce chính sách toàn repository, cần áp dụng quy ước build, convention plugin, kiểm tra cấu hình hoặc resolution rules được thiết kế phù hợp.

Không nên để một module ghi phiên bản trực tiếp khác với phiên bản mặc định trong settings mà không có chủ đích, vì có thể dẫn đến version không nhất quán hoặc xung đột classpath.

## 5. Cách B: định nghĩa plugin tại root với apply false

Một phương án thay thế là **không khai báo default version trong pluginManagement**, mà khai báo plugin ở **root build.gradle**:

**settings.gradle**:

~~~groovy
rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

**build.gradle ở root**:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5' apply false
    id 'io.spring.dependency-management' version '1.1.6' apply false
}
~~~

Hai file **app/build.gradle** và **core/build.gradle** ở mục 4 giữ nguyên. Root build.gradle chỉ định version rồi dùng **apply false** để **không áp dụng plugin lên root**. Subproject app tiếp tục viết:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
~~~

Các dòng plugin không có version ở app vì phiên bản đã sẵn trên plugin classpath được cung cấp từ parent/root build. Core không yêu cầu Boot plugin, nên không bị áp dụng Boot.

**apply false nghĩa chính xác là gì?**

- Gradle **resolve plugin** từ ID/version và đưa plugin vào plugin classpath.
- Gradle **không gọi áp dụng plugin** vào project đang chứa request apply false (ở đây là root).
- Plugin sẽ được **áp dụng** trong project khác nếu project đó chủ động yêu cầu **id 'org.springframework.boot'**.
- apply false **không tự áp dụng cho mọi subproject**, cũng không có nghĩa “tắt plugin cho tất cả”.

Nếu root bỏ chữ **apply false**:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

thì Boot plugin được **áp dụng vào root**, mặc dù root không phải ứng dụng. Điều này có thể tạo những task/configuration Boot không cần thiết, thậm chí đóng gói lỗi khi root không có main class phù hợp. Tránh áp Boot plugin lên root chỉ để chia sẻ version.

**Một lưu ý về độ sớm của resolution:** Khối root **plugins { id ... apply false }** vẫn là một **plugin request**, nên Gradle có thể phải tải plugin ở giai đoạn configuration ngay cả khi root chưa dùng task do plugin cung cấp. Còn **pluginManagement.plugins** chủ yếu khai báo default version trong Settings và không tự tạo plugin request cho mọi plugin đã liệt kê.

## 6. So sánh pluginManagement và apply false

| Tiêu chí | pluginManagement | root plugins + apply false |
| --- | --- | --- |
| Vị trí | **settings.gradle**, khối đầu tiên | **build.gradle** của root |
| Định nghĩa version mặc định? | Có, qua **pluginManagement.plugins** | Chọn version của plugin được resolve tại root |
| Resolve plugin ngay vì khai báo? | Khai báo default version không tự áp plugin hay buộc resolve mọi plugin | **plugins request** có thể resolve plugin dù apply false |
| Áp plugin lên root? | Không | **Không** khi dùng apply false |
| Áp plugin lên subproject? | Không, subproject phải request | Không, subproject phải request |
| Khai báo plugin repository? | Có, qua **repositories** | Không phải chức năng của apply false |
| Chỉnh mapping plugin ID → implementation? | Có, qua **resolutionStrategy** | Không phải chức năng của apply false |
| Phù hợp multi-project? | Có | Có |
| Thay cho dependency BOM? | Không | Không |

**Chọn cách nào?** Nếu mục tiêu gồm cả kho plugin nội bộ, version từ gradle.properties và chính sách plugin resolution, dùng **pluginManagement**. Nếu mục tiêu chính là để root chia sẻ một tập plugin/verson rõ ràng nhưng root không tự chạy ứng dụng Boot, **apply false** là cách ngắn gọn. Hai cách có thể cùng tồn tại khi có mục đích rõ ràng, nhưng không nên lặp các version ở hai nơi để rồi lệch nhau.

Trong một dự án **chỉ có một module**, bạn có thể ghi trực tiếp plugin cùng version vào **build.gradle** của ứng dụng mà không cần hai cơ chế này. Chúng phát huy ích lợi rõ hơn khi nhiều project cùng dùng plugin.

## 7. Bài thực hành chạy được: một app Spring Boot dùng thư viện core

### 7.1. Cấu trúc thư mục

~~~text
plugin-versions-demo/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/java/com/example/app/PluginVersionApplication.java
│       └── test/java/com/example/app/MessageServiceTest.java
└── core/
    ├── build.gradle
    └── src/main/java/com/example/core/MessageService.java
~~~

Với **cách A**, sử dụng **settings.gradle + app/build.gradle + core/build.gradle** ở mục 4. Với **cách B**, dùng **settings.gradle + root build.gradle** ở mục 5 và giữ nguyên app/core build scripts. Không cần tạo cả hai bộ version trong một dự án.

Ví dụ cần **Gradle Wrapper 8.5**, **JDK 17** và kết nối tới repository để tải plugin/dependency. Nếu tự tạo thư mục thủ công, wrapper phải được tạo từ một bản Gradle cài sẵn hoặc lấy từ skeleton Gradle tương thích; chỉ viết tên **gradlew** trong cây thư mục không tự tạo wrapper hoạt động.

### 7.2. Java class của thư viện core

Tệp **core/src/main/java/com/example/core/MessageService.java**:

~~~java
package com.example.core;

public final class MessageService {
    public String message() {
        return "PLUGIN_VERSION_OK";
    }
}
~~~

Đây là class Java thuần, không phụ thuộc Spring Boot. **core** dùng java-library plugin, biên dịch class và đưa nó vào JAR thường.

### 7.3. Spring Boot application ở app

Tệp **app/src/main/java/com/example/app/PluginVersionApplication.java**:

~~~java
package com.example.app;

import com.example.core.MessageService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PluginVersionApplication implements CommandLineRunner {
    public static void main(String[] args) {
        SpringApplication.run(PluginVersionApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(new MessageService().message());
    }
}
~~~

**@SpringBootApplication** khởi động ứng dụng Spring Boot. Class implements **CommandLineRunner**, nên Spring Boot gọi **run** sau khi application context được khởi tạo. MessageService là class Java thuần và được tạo trực tiếp; không cần khai báo Spring bean riêng.

Tệp **app/src/test/java/com/example/app/MessageServiceTest.java**:

~~~java
package com.example.app;

import com.example.core.MessageService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("PLUGIN_VERSION_OK", new MessageService().message());
    }
}
~~~

Test thuộc module app, dùng JUnit Jupiter qua **spring-boot-starter-test**. Với **tasks.named('test') { useJUnitPlatform() }**, Gradle dùng JUnit Platform chạy test.

### 7.4. Các lệnh kiểm tra và chạy

Đứng ở thư mục root:

~~~bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew :core:tasks --all
./gradlew :app:test :app:bootJar
./gradlew :app:bootRun
~~~

Trên Windows, thay **./gradlew** bằng **gradlew.bat**.

Kết quả mong đợi về **cấu trúc build**:

- **projects** liệt kê **:app** và **:core**.
- **:app:tasks --all** có task **bootJar** và **bootRun** vì app thực sự áp dụng Boot plugin và Java plugin.
- **:core:tasks --all** có task Java library như **jar**, nhưng **không có bootJar**, vì core không áp dụng Boot plugin.
- **:app:test** chạy JUnit test và xác nhận app đọc được class thuộc core.
- **:app:bootJar** tạo executable Spring Boot JAR tại thư mục **app/build/libs/**; tên file phụ thuộc vào version/project configuration.
- **:app:bootRun** chạy CommandLineRunner; bên cạnh log của Gradle/Spring Boot, chương trình in dòng stdout do code tạo ra:

~~~text
PLUGIN_VERSION_OK
~~~

Ví dụ không tạo HTTP endpoint hoặc yêu cầu cổng 8080, nên không cần curl. Output đầy đủ của Gradle/Spring Boot gồm nhiều log phụ thuộc môi trường; chỉ dòng từ System.out.println ở trên được xác định cố định.

**Kiểm tra chiều ngược lại:** **./gradlew :core:bootJar** sẽ không có task bootJar trong :core theo cấu hình ví dụ. Đó là bằng chứng core chưa áp dụng Spring Boot plugin, chứ không phải lỗi cần sửa.

### 7.5. Kiểm chứng version dependency riêng với version plugin

Chạy:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Hai lệnh hiển thị dependency graph đã resolve của app. Plugin **io.spring.dependency-management** khi phối hợp với Spring Boot Gradle Plugin quản lý version starter/test dependencies qua BOM của Spring Boot. Việc quản lý version plugin ở settings/root không tự thay version của mọi thư viện khác và không có nghĩa mọi module đều tự có BOM.

## 8. Đọc version từ gradle.properties trong pluginManagement

Với team nhiều người, đưa version plugin vào **gradle.properties** có thể tiện khi nâng cấp:

~~~properties
springBootPluginVersion=3.3.5
springDependencyManagementVersion=1.1.6
~~~

**settings.gradle** có thể dùng pluginManagement để lấy property:

~~~groovy
pluginManagement {
    def bootVersion = providers.gradleProperty('springBootPluginVersion').get()
    def depMgmtVersion = providers.gradleProperty('springDependencyManagementVersion').get()

    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version bootVersion
        id 'io.spring.dependency-management' version depMgmtVersion
    }
}

rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

Đây là **phiên bản thay thế** của settings.gradle ở mục 4. Đọc property qua **providers.gradleProperty** giúp mô tả nguồn version rõ ràng. Nếu property chưa được định nghĩa, **.get()** sẽ báo thiếu giá trị; có thể chủ động đặt default bằng API Provider nếu dự án cần.

**Không sao chép logic Groovy với def/if vào plugins block ở app/build.gradle**: project plugins block có cú pháp ràng buộc. **pluginManagement** được thiết kế để xử lý việc lựa chọn phiên bản sớm và cho phép cách tính version linh hoạt hơn.

Nếu dự án dùng **gradle/libs.versions.toml** (version catalog), alias plugin là một phương án quản lý version khác. Dù khai báo plugin bằng alias, **apply false** vẫn có ý nghĩa khi muốn đưa plugin vào scope chung mà chưa áp cho root. Chọn một nguồn version nhất quán cho team.

## 9. Phân biệt plugin repositories và dependency repositories

Hai cấu hình này **không thay thế nhau**:

**Kho tìm plugin** trong settings.gradle:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

**Kho tìm thư viện ứng dụng** trong app/build.gradle:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Plugin resolution dùng cơ chế plugin marker, còn dependencies dùng Maven/Gradle module metadata theo thông tin tọa độ dependency. Vì vậy lỗi **Plugin [id: 'org.springframework.boot'] was not found** không chắc được chữa chỉ bằng cách thêm **mavenCentral()** ở app/build.gradle.

Nếu tổ chức dùng kho plugin riêng, dạng cấu hình minh họa là:

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('https://plugins.example.org/maven')
        }
        gradlePluginPortal()
    }
}
~~~

**plugins.example.org là URL ví dụ, không phải server hoạt động**. Khi áp dụng thực tế, cần URL thật, plugin marker/implementation phù hợp và chính sách credential của tổ chức. Không hard-code token/password vào Gradle file được commit.

Khi tự khai báo pluginManagement.repositories, cần đưa các repository mình muốn dùng vào danh sách; nếu bỏ **gradlePluginPortal()**, Gradle không tự thêm lại portal theo ý muốn của ta.

## 10. resolutionStrategy và plugin phát triển trong nội bộ

**pluginManagement.resolutionStrategy** cho phép thay cách resolve plugin request; ví dụ một plugin nội bộ có ID **com.example.build-conventions** nhưng implementation artifact ở một Maven coordinate do tổ chức tự chọn.

~~~groovy
pluginManagement {
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'com.example.build-conventions') {
                useModule('com.example.tools:build-conventions-plugin:1.0.0')
            }
        }
    }
    repositories {
        maven {
            url = uri('https://plugins.example.org/maven')
        }
    }
}
~~~

Đây là **đoạn minh họa**, chưa có artifact/repository thật nên không phải cấu hình có thể chạy nguyên trạng. **useModule** ánh xạ plugin ID thành artifact implement plugin. Với Spring Boot Plugin công khai, thông thường không cần resolutionStrategy; dùng version trong pluginManagement.plugins hoặc root apply false là đủ.

Nếu plugin nội bộ được xây dựng trong một included build riêng, Gradle còn hỗ trợ **pluginManagement.includeBuild('build-logic')**. Chỉ dùng khi thực sự có build-logic project định nghĩa plugin có ID phù hợp; includeBuild không tự sinh ra plugin hoặc project.

## 11. Lỗi phổ biến khi cấu hình pluginManagement và apply false

**Lỗi 1 — pluginManagement không phải khối đầu tiên của settings.gradle.** Đặt pluginManagement ở đầu file, trước rootProject.name và include; Gradle cần plugin resolution rules từ giai đoạn initialization.

**Lỗi 2 — Bỏ version trong subproject mà không khai báo default version hay root apply false.** Gradle không biết version của external plugin trong plugins DSL, nên có thể báo **Plugin not found**. Cung cấp version tập trung hoặc đặt version trực tiếp nếu dự án chỉ có một module.

**Lỗi 3 — Vừa root apply false vừa viết version khác trong app.** Plugin đã được đưa vào classpath bởi root, nên request plugin có version lặp lại ở subproject có thể gây lỗi **already on the classpath** hoặc xung đột version. app nên chỉ khai báo plugin ID.

**Lỗi 4 — Nghĩ apply false tự apply plugin lên mọi subproject.** apply false không tự gắn Boot plugin vào app/core. Module cần plugin phải yêu cầu nó rõ ràng bằng plugins block hoặc convention plugin.

**Lỗi 5 — Root bị áp dụng Boot plugin không cần thiết.** Nếu root chỉ là aggregator, dùng apply false khi khai báo plugin ở root. Không áp plugin lên root rồi tắt bootJar thủ công chỉ để xử lý hậu quả.

**Lỗi 6 — Dùng apply false với core java plugin.** Core plugin **java** đã được phân phối cùng Gradle; nó không cần version riêng và không phải trường hợp cần khai báo apply false. Cứ áp **id 'java'** hoặc **id 'java-library'** tại module thích hợp.

**Lỗi 7 — Nhầm settings.plugins với pluginManagement.plugins.** Một **plugins** block trực tiếp trong settings.gradle phục vụ Settings plugins; một **plugins** block bên trong pluginManagement khai báo default plugin versions. Đừng coi chúng là tương đương.

**Lỗi 8 — Chỉ khai báo pluginManagement.plugins rồi mong thấy bootJar.** Settings chỉ cung cấp default version, không áp Boot plugin. Kiểm tra app/build.gradle đã yêu cầu **org.springframework.boot** và Java plugin chưa.

**Lỗi 9 — Thiếu plugin repositories hoặc plugin repo bị chặn.** Thêm đúng kho vào **pluginManagement.repositories**; kiểm tra mạng, proxy, marker artifact và credential khi dùng private repo. Project repositories phục vụ mục đích khác.

**Lỗi 10 — Plugin version đúng nhưng Gradle/JDK không tương thích.** Kiểm tra **./gradlew --version** và Java runtime chạy Gradle, đọc release notes của Spring Boot Gradle Plugin. pluginManagement không tự nâng Gradle Wrapper hoặc JDK.

**Lỗi 11 — Code trong project plugins block không hợp cú pháp.** Không đặt **plugins { ... }** tùy ý trong if/loop hay chèn script statement trước nó sai vị trí. Dùng version literals, alias hoặc policy version trong pluginManagement.

**Lỗi 12 — Nhầm plugin version với Spring Boot dependency BOM.** app có Boot plugin không đồng nghĩa mọi dependency được quản lý nếu thiếu dependency-management plugin hoặc native BOM platform. Đặt phạm vi BOM ở project có yêu cầu thực sự.

**Lỗi 13 — Nghĩ core phải có bootJar.** core là java-library và nên sinh JAR thư viện; app áp Boot plugin để sinh executable JAR. Dùng **:core:jar**, **:app:bootJar** thay vì cố chạy mọi task ở root.

**Lỗi 14 — Phối hợp hai nguồn version mâu thuẫn.** Nếu khai báo cả settings.pluginManagement và root apply false, phải thống nhất version và mục tiêu; tránh chỉnh một nơi rồi quên nơi khác.

**Lỗi 15 — Lấy plugin trong private repository không có marker.** Plugins DSL thường resolve plugin marker rồi implementation artifact. Khi repository có implementation nhưng không có marker, cần publish marker đúng hoặc dùng pluginManagement.resolutionStrategy ánh xạ chính xác.

## 12. Khi nào nên chọn chiến lược nào?

| Bối cảnh | Lựa chọn thường hợp lý |
| --- | --- |
| Một ứng dụng Spring Boot duy nhất | Khai báo version trực tiếp trong app/build.gradle cho đơn giản. |
| Multi-project có các app dùng chung version, root không là app | Root **plugins ... apply false** hoặc **settings.pluginManagement**. |
| Cần riêng plugin repositories, proxy, resolution rule | **pluginManagement**. |
| Muốn tải version từ gradle.properties | **pluginManagement.plugins**. |
| Nhiều quy tắc Java/test/quality lặp lại | **Convention plugin** để gói logic chung. |
| Module thư viện không chạy Spring Boot | Chỉ **java-library**, không áp Boot plugin nếu không cần. |

Quy trình kiểm tra sau khi chỉnh:

1. Đảm bảo Gradle Wrapper/JDK tương thích với Spring Boot plugin version được chọn.
2. Xác định một nơi quản lý version plugin, rồi bỏ version lặp ở app/core.
3. Kiểm tra nơi resolve plugin và nơi resolve dependency được cấu hình đúng.
4. Chạy **./gradlew projects** để xác nhận multi-project setup.
5. Chạy **./gradlew :app:tasks --all** và **:core:tasks --all** để kiểm tra plugin áp dụng đúng module.
6. Chạy **./gradlew :app:test :app:bootJar** để phát hiện sớm lỗi version/plugin resolution.
7. Chạy **./gradlew :app:bootRun** để xác nhận hành vi ứng dụng.
8. Khi nâng plugin, kiểm tra kết quả build/test, dependency graph và yêu cầu tương thích thay vì chỉ xác nhận Gradle tải được plugin.

## 13. Tài liệu tham khảo chính thức

- Gradle — Working with Plugins: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- Gradle — Build Lifecycle: https://docs.gradle.org/current/userguide/build_lifecycle.html
- Gradle — Best Practices for Structuring Builds: https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html
- Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Spring Boot 3.3 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot — Gradle Plugin Managing Dependencies: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html

**Ghi nhớ:** **pluginManagement** trong settings xác định nơi tìm và phiên bản mặc định của plugin; **apply false** trong root build.gradle resolve plugin để module con dùng mà không áp nó lên root. **Subproject vẫn cần yêu cầu plugin để nhận task và chức năng của plugin đó.** Tách đúng ba trách nhiệm này giúp build Spring Boot nhiều module nhất quán mà không gắn Boot plugin vào thư viện Java.
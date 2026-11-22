# Khai báo `org.crac:crac` trong Maven hoặc Gradle

Để viết mã Java sử dụng API CRaC, dự án cần khai báo thư viện `org.crac:crac` trong hệ thống quản lý dependency. Thư viện này cung cấp các kiểu API như `Resource`, `Context` và `Core`, cho phép ứng dụng đăng ký callback xử lý trước checkpoint và sau restore. Cách khai báo phụ thuộc vào công cụ build mà dự án sử dụng: Maven khai báo dependency trong `pom.xml`, còn Gradle khai báo trong khối `dependencies` của file build.

Dependency giúp mã nguồn biên dịch và liên kết với API CRaC. Bản thân việc thêm dependency không biến một JDK thông thường thành runtime có khả năng checkpoint/restore. Khi triển khai chức năng CRaC thực tế, ứng dụng vẫn cần chạy trên JDK hoặc runtime có hỗ trợ CRaC và môi trường triển khai phù hợp.

## 1. Dependency có vai trò gì?

`org.crac:crac` là tọa độ dependency theo quy ước Maven gồm ba phần:

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| Group ID | `org.crac` | Nhóm phát hành thư viện |
| Artifact ID | `crac` | Tên artifact cung cấp API CRaC |
| Version | Ví dụ `1.5.0` | Phiên bản thư viện mà dự án muốn sử dụng |

Khi dự án khai báo dependency, Maven hoặc Gradle sẽ tìm artifact theo tọa độ này trong các repository đã cấu hình, tải artifact cùng các dependency liên quan nếu có, rồi đưa nó vào classpath tương ứng.

Ví dụ, mã nguồn có thể import API:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
```

Nếu dependency chưa được khai báo hoặc không được đưa vào compile classpath, trình biên dịch không tìm thấy các kiểu `org.crac` và báo lỗi như `package org.crac does not exist`.

## 2. Khai báo trong Maven

Maven quản lý dependency của một dự án trong file `pom.xml`. Khai báo `org.crac:crac` bên trong phần tử `<dependencies>` của module có mã nguồn sử dụng API.

### 2.1. Khai báo trực tiếp

Ví dụ phần dependency trong `pom.xml`:

```xml
<project>
    <!-- Các phần tử project khác được lược bỏ trong ví dụ này. -->

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>1.5.0</version>
        </dependency>
    </dependencies>
</project>
```

`1.5.0` là phiên bản minh họa cho cú pháp. Khi áp dụng vào dự án, hãy chọn phiên bản đã được dự án phê duyệt và kiểm tra tính tương thích với JDK/runtime CRaC sẽ sử dụng. Không nên hiểu ví dụ này là cam kết rằng đây luôn là phiên bản mới nhất.

Trong Maven, scope mặc định của dependency là `compile`. Nếu không chỉ định `<scope>`, dependency có mặt trên compile classpath và runtime classpath, đồng thời được sử dụng trong các giai đoạn build phù hợp. Đây thường là lựa chọn đúng khi ứng dụng trực tiếp triển khai các lớp như `Resource` và cần các kiểu API đó lúc chạy.

### 2.2. Quản lý phiên bản bằng property

Để tránh lặp lại số phiên bản trong nhiều dependency hoặc module, có thể đặt phiên bản trong `<properties>`:

```xml
<project>
    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <crac.version>1.5.0</crac.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>${crac.version}</version>
        </dependency>
    </dependencies>
</project>
```

Khi cần nâng cấp, chỉ cần thay giá trị `crac.version` tại một nơi. Ví dụ `maven.compiler.release` trong đoạn trên chỉ minh họa cấu hình compiler; hãy đặt mức Java phù hợp với phiên bản JDK mà dự án thực sự hỗ trợ.

### 2.3. Dự án Maven nhiều module

Với Maven multi-module, có thể quản lý phiên bản tập trung trong phần `<dependencyManagement>` của parent POM:

```xml
<project>
    <properties>
        <crac.version>1.5.0</crac.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.crac</groupId>
                <artifactId>crac</artifactId>
                <version>${crac.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Module có mã nguồn sử dụng CRaC vẫn phải khai báo dependency trong `<dependencies>` của chính module đó:

```xml
<dependencies>
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
    </dependency>
</dependencies>
```

`dependencyManagement` chỉ quản lý thông tin dependency như version và scope mặc định; nó không tự thêm dependency vào mọi module con. Cách tách này giúp các module dùng API một cách tường minh trong khi vẫn thống nhất phiên bản trên toàn dự án.

## 3. Khai báo trong Gradle

Gradle khai báo thư viện trong khối `dependencies`. Configuration quyết định dependency xuất hiện ở classpath nào và được công khai ra sao đối với module khác.

### 3.1. Gradle Groovy DSL

Với file `build.gradle` dùng Groovy DSL:

```groovy
def cracVersion = '1.5.0'

dependencies {
    implementation "org.crac:crac:${cracVersion}"
}
```

Có thể dùng cú pháp không cần biến nếu dự án chỉ khai báo ở một vị trí:

```groovy
dependencies {
    implementation 'org.crac:crac:1.5.0'
}
```

### 3.2. Gradle Kotlin DSL

Với file `build.gradle.kts` dùng Kotlin DSL:

```kotlin
val cracVersion = "1.5.0"

dependencies {
    implementation("org.crac:crac:$cracVersion")
}
```

Kotlin DSL dùng lời gọi hàm `implementation(...)`; chuỗi tọa độ dependency có thể nội suy biến bằng `$cracVersion`.

### 3.3. Tập trung phiên bản trong `gradle.properties`

Khi nhiều module cùng dùng dependency, có thể khai báo phiên bản ở `gradle.properties` tại root project:

```properties
cracVersion=1.5.0
```

Trong `build.gradle`:

```groovy
def cracVersion = providers.gradleProperty('cracVersion').get()

dependencies {
    implementation "org.crac:crac:${cracVersion}"
}
```

Trong `build.gradle.kts`:

```kotlin
val cracVersion = providers.gradleProperty("cracVersion").get()

dependencies {
    implementation("org.crac:crac:$cracVersion")
}
```

Cả hai cách đều lấy cùng một giá trị từ `gradle.properties`, giúp các module sử dụng một phiên bản thống nhất.

### 3.4. Dùng Gradle version catalog

Với dự án dùng version catalog, có thể quản lý tọa độ và phiên bản trong `gradle/libs.versions.toml`:

```toml
[versions]
crac = "1.5.0"

[libraries]
crac-api = { module = "org.crac:crac", version.ref = "crac" }
```

Sau đó tham chiếu alias trong `build.gradle.kts`:

```kotlin
dependencies {
    implementation(libs.crac.api)
}
```

Với alias `crac-api`, Gradle tạo accessor `libs.crac.api`. Cách này hữu ích khi dự án có nhiều module và muốn tập trung danh mục dependency trong một file.

## 4. Chọn configuration hoặc scope phù hợp

Khi khai báo dependency, cần chọn configuration phù hợp với cách mã nguồn sử dụng API.

| Công cụ | Khai báo thường dùng | Ý nghĩa |
|---|---|---|
| Maven | Không khai báo scope, mặc định `compile` | Có trên compile và runtime classpath |
| Gradle | `implementation` | Dependency nội bộ của module, có trên compile và runtime classpath của module |
| Gradle | `api` | Dùng khi module là thư viện và kiểu CRaC xuất hiện trong public API cần truyền tới compile classpath của consumer |
| Gradle | `testImplementation` | Chỉ phục vụ mã nguồn test; không đủ nếu mã production import API CRaC |
| Gradle | `compileOnly` | Chỉ có trên compile classpath; chỉ dùng khi runtime chắc chắn cung cấp API tương ứng |

Đối với một ứng dụng Java thông thường, `implementation` trong Gradle hoặc scope mặc định `compile` trong Maven là lựa chọn dễ hiểu và phù hợp khi ứng dụng trực tiếp dùng API CRaC.

Nếu module đang xây dựng là một thư viện và public method, public field hoặc kiểu generic của nó để lộ kiểu `org.crac` cho module tiêu thụ, Gradle `api` có thể là lựa chọn phù hợp. Nếu CRaC chỉ được dùng bên trong implementation của thư viện, ưu tiên `implementation` để không làm dependency trở thành một phần API compile của consumer.

Không chọn `testImplementation` cho dependency mà mã production cần. Cũng không chuyển sang `compileOnly` chỉ để giảm kích thước artifact khi chưa xác định runtime có cung cấp các lớp API cần thiết hay không; thiếu lớp ở runtime có thể dẫn tới lỗi nạp lớp như `NoClassDefFoundError`.

## 5. Dùng API sau khi khai báo dependency

Sau khi dependency đã được tải và đưa vào classpath, mã nguồn có thể triển khai `Resource` để xử lý vòng đời checkpoint/restore.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {

    public CacheResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Đưa tài nguyên về trạng thái an toàn trước checkpoint.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Tạo lại hoặc làm mới tài nguyên sau restore.
    }
}
```

Ví dụ tập trung vào việc minh họa các kiểu API mà dependency cung cấp. Phần xử lý tài nguyên cần được thay bằng logic phù hợp với ứng dụng, chẳng hạn dừng công việc đang chạy và đóng kết nối trước checkpoint, sau đó mở lại kết nối sau restore.

Đặt dependency trong module có lớp `CacheResource`. Nếu lớp nằm ở module `infrastructure` nhưng dependency chỉ được khai báo trong module `application`, module `infrastructure` có thể không biên dịch được vì classpath của nó không tự nhận dependency khai báo ở module khác.

## 6. Kiểm tra dependency đã được resolve

Sau khi chỉnh file build, hãy kiểm tra công cụ build đã tìm thấy đúng dependency và đưa nó vào classpath mong muốn.

### 6.1. Maven

Chạy lệnh sau tại thư mục chứa `pom.xml`:

```bash
mvn dependency:tree -Dincludes=org.crac:crac
```

Nếu dự án dùng Maven Wrapper, có thể thay `mvn` bằng `./mvnw` trên môi trường Unix-like hoặc `mvnw.cmd` trên Windows:

```bash
./mvnw dependency:tree -Dincludes=org.crac:crac
```

Kết quả cần thể hiện `org.crac:crac` cùng phiên bản được chọn trong dependency graph. Nếu không thấy dependency, kiểm tra module đang chạy lệnh, vị trí khai báo trong `pom.xml`, profile Maven đang kích hoạt và cấu hình repository.

### 6.2. Gradle

Với Gradle, kiểm tra dependency trong `runtimeClasspath`:

```bash
./gradlew dependencyInsight --dependency crac --configuration runtimeClasspath
```

Trên Windows có thể chạy `gradlew.bat` thay cho `./gradlew`:

```powershell
.\gradlew.bat dependencyInsight --dependency crac --configuration runtimeClasspath
```

Lệnh `dependencyInsight` cho biết dependency được chọn, đường dẫn nó đi vào graph và lý do Gradle chọn phiên bản đó. Nếu dependency xuất hiện trong `compileClasspath` nhưng không có trong `runtimeClasspath`, hãy kiểm tra xem có khai báo nhầm `compileOnly` hay configuration tùy chỉnh hay không.

### 6.3. Kiểm tra biên dịch

Sau khi xác nhận dependency graph, chạy compile task tương ứng:

```bash
# Maven
mvn -q -DskipTests compile

# Gradle
./gradlew compileJava
```

Nếu import `org.crac.*` vẫn không được nhận diện, kiểm tra dependency đã được khai báo trong đúng module, cấu hình build có được đồng bộ lại trong IDE và phiên bản dependency có được resolve thành công hay không. Compile thành công xác nhận API có mặt trên compile classpath; nó chưa chứng minh môi trường hiện tại có thể tạo checkpoint hoặc restore.

## 7. Phân biệt thư viện API với CRaC-enabled JDK

Đây là điểm quan trọng khi cấu hình môi trường thực hành:

| Thành phần | Trách nhiệm |
|---|---|
| `org.crac:crac` | Cung cấp các kiểu API Java để mã nguồn tham chiếu và đăng ký resource callbacks |
| JDK/runtime có hỗ trợ CRaC | Cung cấp khả năng thực thi checkpoint/restore ở cấp runtime |
| Môi trường triển khai | Cung cấp điều kiện hệ điều hành, quyền và cấu hình cần thiết để checkpoint/restore hoạt động |
| Maven hoặc Gradle | Resolve dependency, tạo classpath và thực hiện build |

Vì vậy, một dự án có thể biên dịch thành công sau khi thêm `org.crac:crac`, nhưng vẫn không thể thực hiện checkpoint nếu chạy bằng JDK không hỗ trợ CRaC. Ngược lại, cài CRaC-enabled JDK không thay thế việc khai báo dependency nếu mã nguồn cần import API mà build không có trên classpath.

Khi chọn phiên bản dependency, hãy kiểm tra release tương ứng, yêu cầu Java tối thiểu và hướng dẫn của runtime CRaC mà dự án triển khai. Nên ghi nhận phiên bản JDK, phiên bản thư viện và công cụ build trong tài liệu môi trường để nhóm phát triển có thể tái tạo cùng cấu hình.

## 8. Các lỗi cấu hình thường gặp

### Thiếu version trong Maven

Nếu không có version trong `<dependency>` và cũng không có version được quản lý bởi `<dependencyManagement>`, Maven có thể báo lỗi thiếu thông tin phiên bản. Hãy khai báo version trực tiếp hoặc quản lý version trong parent POM.

### Đặt dependency ở sai module

Trong dự án nhiều module, dependency chỉ có hiệu lực đối với module được khai báo theo cấu hình tương ứng. Hãy thêm `org.crac:crac` vào module có mã nguồn import `org.crac.*`; khai báo ở module khác không tự động đưa dependency vào classpath của module này.

### Nhầm `dependencyManagement` với `dependencies`

Maven `dependencyManagement` quản lý phiên bản và metadata nhưng không tự thêm dependency. Module cần sử dụng API vẫn phải khai báo dependency trong `<dependencies>`.

### Dùng nhầm Gradle configuration

Nếu mã production import API nhưng dependency chỉ được khai báo bằng `testImplementation`, compile task của production source set sẽ không có thư viện. Nếu dùng `compileOnly`, ứng dụng có thể biên dịch nhưng thiếu lớp khi chạy nếu runtime không cung cấp API đó.

### Có nhiều phiên bản trong dependency graph

Dependency bắc cầu từ thư viện khác có thể đưa thêm một phiên bản `org.crac:crac` vào graph. Dùng `mvn dependency:tree` hoặc Gradle `dependencyInsight` để tìm nguồn đưa dependency vào và xác định phiên bản cuối cùng được chọn. Quản lý version tập trung để tránh các module dùng những phiên bản không thống nhất.

### Chỉ thêm dependency rồi chạy trên JDK bất kỳ

Dependency cung cấp API cho build. Khả năng checkpoint/restore phụ thuộc vào JDK/runtime CRaC và môi trường triển khai. Hãy xác nhận runtime đang chạy thực sự hỗ trợ CRaC trước khi kiểm thử chức năng checkpoint.

## 9. Quy trình cấu hình đề xuất

Khi thêm CRaC vào một dự án mới hoặc dự án hiện có, có thể thực hiện theo thứ tự sau:

1. Xác định module nào trực tiếp sử dụng API `org.crac`.
2. Xác định JDK/runtime CRaC mục tiêu và phiên bản thư viện tương thích.
3. Khai báo `org.crac:crac` trong `pom.xml`, `build.gradle` hoặc `build.gradle.kts` của module đó.
4. Tập trung quản lý version bằng Maven property, parent `dependencyManagement`, `gradle.properties` hoặc version catalog tùy cấu trúc dự án.
5. Chọn scope/configuration phù hợp; thông thường dùng Maven compile mặc định hoặc Gradle `implementation` cho ứng dụng.
6. Kiểm tra dependency graph và compile task.
7. Chạy ứng dụng trên CRaC-enabled runtime để kiểm tra các thao tác checkpoint/restore và callback tài nguyên trong môi trường mục tiêu.

Khai báo đúng `org.crac:crac` giúp Maven hoặc Gradle cung cấp API CRaC cho mã nguồn Java. Quản lý phiên bản tập trung, chọn đúng scope và xác nhận dependency graph giúp cấu hình build ổn định giữa các module. Sau cùng, cần kiểm tra riêng JDK/runtime triển khai vì dependency API và khả năng checkpoint/restore là hai phần khác nhau của môi trường CRaC.

# Chuẩn bị dependency:go-offline và kiểm chứng build ngoại tuyến với Maven

## 1. Tại sao Maven cần chuẩn bị trước khi mất mạng?

Maven không chỉ dùng mã nguồn trong thư mục dự án. Trong lúc build, Maven có thể cần tải:

- **Dependencies của dự án**: JAR/POM dùng cho mã chính và mã kiểm thử, kể cả các dependencies bắc cầu.
- **Maven plugins**: Clean, Resources, Compiler, Surefire, JAR, Dependency, Exec... và những dependencies của plugin.
- **Parent POM, BOM và metadata**: thông tin để Maven xây dựng effective model và chọn phiên bản.
- **Thành phần chỉ phát sinh ở một bước cụ thể**: ví dụ provider/engine kiểm thử, công cụ tạo source, plugin đóng gói hoặc dependency được một plugin nạp theo điều kiện.

Những artifact đã tải thường được lưu trong **local Maven repository**, mặc định ở `~/.m2/repository`, nhưng có thể được đổi bằng `settings.xml` hoặc `-Dmaven.repo.local`. Khi máy mất mạng, Maven chỉ xây dựng được dự án nếu các thành phần cần thiết đã sẵn có tại local repository hoặc có thể tạo ra từ reactor hiện tại.

Maven cung cấp hai công cụ có vai trò **khác nhau**:

- **`dependency:go-offline`**: goal của Maven Dependency Plugin, chủ động phân giải và chuẩn bị dependencies, plugins, report plugins cùng các dependencies liên quan trước khi mất mạng.
- **`mvn -o ...`** (hoặc `--offline`): chuyển Maven sang chế độ offline, không lấy thêm artifact từ remote repositories bằng cơ chế giải quyết phụ thuộc thông thường.

**Mấu chốt:** chạy `dependency:go-offline` thành công **không tự chứng minh** toàn bộ build có thể chạy khi không có mạng. Cần thử chính lifecycle/goal của dự án với **`-o`**, cùng cấu hình và local repository mà bạn định sử dụng.

```text
POM + active profiles + settings + JDK + Maven
                       |
                 CÓ KẾT NỐI MẠNG
                       |
        dependency:go-offline (chuẩn bị cache)
                       |
     chạy đầy đủ lifecycle/goal thật để warm cache
                       |
                    NGẮT MẠNG
                       |
              mvn -o clean verify
                       |
                 BUILD SUCCESS?
                  /          \
               Có             Không
               |               |
        Cache đủ cho      Đọc lỗi artifact,
        lệnh đã thử       plugin, profile,
                           repo, JDK và sửa
```

Bài này hướng dẫn cơ chế, ví dụ Maven Java 17 với JUnit 5 chạy được, cách dùng kho cache cô lập, kiểm thử ngoại tuyến, các hạn chế của `go-offline` và phương pháp chẩn đoán build lỗi sau khi ngắt mạng.

## 2. Phân biệt go-offline, offline flag và tải dependency thông thường

| Lệnh/cơ chế | Nó làm gì? | Có chứng minh build offline thành công? |
| --- | --- | --- |
| `mvn dependency:go-offline` | Phân giải dependencies của dự án, plugins, reports và các dependencies liên quan | **Chưa**; chỉ chuẩn bị cache theo mô hình mà goal nhận diện |
| `mvn -o clean verify` | Yêu cầu Maven build tới `verify` nhưng không tải artifact từ remote repositories | **Có**, đối với chính lệnh, cấu hình và môi trường vừa thử nếu thành công |
| `mvn clean verify` khi online | Xây dựng và chạy test đầy đủ, tải các thành phần phát sinh thật trong quá trình chạy | Giúp warm cache, nhưng bản thân lần chạy online chưa chứng minh offline |
| `mvn -U clean verify` khi online | Ép Maven kiểm tra cập nhật SNAPSHOT và metadata liên quan theo chính sách | Không; `-U` không phải cờ offline |
| `mvn dependency:tree` | Hiển thị graph dependencies của dự án | Không; thường không đủ để kiểm tra plugin/provider cần khi build |
| `mvn -o package` | Build tới phase package bằng local cache | Chỉ chứng minh tới `package`, không nhất thiết chứng minh `verify`, `install` hay goal khác |

**Không nhầm goal với phase:** `go-offline` là **goal** của Maven Dependency Plugin, không phải một phase trong default lifecycle. Chạy `mvn dependency:go-offline` không đồng nghĩa đã compile, test, package hay verify dự án.

**Không nhầm `-o` với `go-offline`:** `mvn -o dependency:go-offline` trên cache rỗng thường thất bại. Muốn tải các artifact còn thiếu, lần chuẩn bị phải chạy trong môi trường có truy cập được repository phù hợp.

## 3. Maven cần cache những gì để build offline?

Một build Maven có nhiều lớp phân giải:

### 3.1. Project dependencies

Ví dụ trong POM:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn POM**, không phải POM hoàn chỉnh.

Maven không chỉ cần hai JAR trực tiếp: các POM và thư viện bắc cầu của JUnit cũng có thể cần cho test. Nếu chỉ chép một JAR từ internet về mà không có POM/transitive dependencies cần thiết, lần chạy offline có thể thất bại.

### 3.2. Plugin và plugin dependencies

Ngay cả khi không khai báo dependency nào, `mvn clean package` vẫn cần các Maven plugins gắn vào lifecycle: Clean, Resources, Compiler, Surefire, JAR... tùy packaging và cấu hình.

Các plugin có **classpath riêng**. Plugin version có thể được quản lý bởi POM hoặc default lifecycle; plugin JAR và những dependencies của plugin cũng cần ở local cache. Vì vậy chỉ chạy `dependency:resolve` cho project dependencies **chưa tương đương** chuẩn bị một build đầy đủ.

### 3.3. Parent POM, imported BOM, extensions và metadata

Nếu dự án kế thừa parent hoặc nhập BOM bằng `type=pom`, `scope=import`, Maven phải đọc những POM đó để tạo model. Build dùng core/build extensions, plugin prefix resolution, version range hay plugin được chọn động cũng có thể phát sinh nhu cầu metadata hoặc artifact.

Nếu thiếu **parent POM**, Maven có thể thất bại **trước khi** vào lifecycle, dù các JAR của mã Java đã có. Vì thế việc cache phải được chuẩn bị trên chính cấu hình dự án, không chỉ bằng danh sách thư viện ước lượng.

### 3.4. Test provider, generated sources và công cụ nạp động

Một số plugin chỉ phát hiện hoặc tải một thành phần khi goal thực sự chạy. Ví dụ, Maven Surefire có thể dùng provider theo test framework hiện diện; các plugin sinh mã hoặc kiểm thử tích hợp cũng có thể yêu cầu artifact phát sinh theo điều kiện môi trường.

Do đó **`dependency:go-offline` là bước chuẩn bị quan trọng nhưng không phải bảo đảm tuyệt đối**. Sau khi chạy nó, cách chắc chắn hơn là **chạy một lượt build/test đầy đủ khi còn online**, sau đó **lặp lại chính những lệnh ấy với `-o`**.

## 4. Maven Dependency Plugin: goal go-offline hoạt động thế nào?

Goal chuẩn:

```bash
mvn dependency:go-offline
```

Khi plugin được phân giải, Maven cố gắng tải các artifact cần cho dependency graph của dự án, các plugin và báo cáo theo mô hình đã biết. Tài liệu Maven mô tả mục tiêu này là giải quyết **project dependencies, plugins, reports và dependencies của chúng**.

Một cách gọi rõ version plugin, tránh phụ thuộc vào việc Maven chọn version goal prefix:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.9.0:go-offline
```

Đây là cú pháp **groupId:artifactId:version:goal**. Version `3.9.0` được chọn để làm ví dụ nhất quán; không có nghĩa nó là phiên bản mới nhất. Khi POM đã ghim version của Maven Dependency Plugin, dạng `mvn dependency:go-offline` thường đủ rõ và thuận tiện.

### Phạm vi giải quyết và các tham số cần cân nhắc

Theo tài liệu goal, mặc định nó nhắm tới project dependencies theo các phạm vi liên quan và cả plugin/report dependencies. Một số tham số lọc:

- `includeScope` và `excludeScope`: lọc tập dependencies; ý nghĩa là **ngưỡng classpath**, không đơn giản so sánh chuỗi `scope` khai báo trong POM. Mặc định **không cần lọc**, nhất là khi cần chạy tests.
- `excludeGroupIds`, `excludeArtifactIds`, `excludeTypes`: loại một nhóm artifact khỏi phần chuẩn bị; dùng thiếu hiểu biết có thể khiến offline build thất bại.
- `excludeTransitive`: nếu bật sẽ bỏ qua dependencies bắc cầu trong phần lọc; không phù hợp với mục tiêu chuẩn bị đầy đủ.
- `excludeReactor`: mặc định **`true`**; plugin không cố tải những artifact/plugin thuộc reactor hiện tại theo cách như artifact remote. Với multi-module, cần xét cả các module sẽ được xây dựng cùng nhau.
- `skip`: có thể khiến goal không thực hiện; đừng đặt một cờ skip vô tình trong pipeline chuẩn bị cache.

**Không nên thêm `-DincludeScope=compile` để “tối ưu cache” rồi hy vọng `mvn test` offline vẫn chạy.** Test scope và dependencies của kiểm thử có thể bị bỏ qua tùy lựa chọn; dùng mặc định hoặc cấu hình có lý do rồi thực hiện thử nghiệm offline thực tế.

## 5. Ví dụ độc lập: Java 17, Commons Lang, JUnit 5

Để quan sát rõ cache project dependencies **và plugins**, tạo một dự án nhỏ, có compile, unit test, JAR và goal chạy chương trình. Các plugin quan trọng được ghim version để giảm phụ thuộc vào cách chọn plugin mặc định giữa các máy.

Cấu trúc:

```text
offline-maven-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/
    │       ├── Greeting.java
    │       └── App.java
    └── test/
        └── java/dev/example/
            └── GreetingTest.java
```

### 5.1. pom.xml hoàn chỉnh

Tạo `offline-maven-lab/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>offline-maven-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.9.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Lý do ghim version:

- **Clean Plugin** được chạy ở lifecycle `clean`.
- **Resources/Compiler/Surefire/JAR Plugins** hỗ trợ build/test/package theo cấu trúc `jar`.
- **Dependency Plugin** cung cấp goal `dependency:go-offline`.
- **Exec Plugin** cho phép chạy chương trình với runtime classpath của Maven thay vì tự ghép JAR.

Các plugin trong POM **không phải dependencies của mã Java**. Ngược lại, JUnit `scope=test` không thuộc runtime classpath của ứng dụng thông thường. Khi chuẩn bị offline, phải xét cả hai loại artifact.

### 5.2. Mã Java 17

Tạo `src/main/java/dev/example/Greeting.java`:

```java
package dev.example;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String forName(String name) {
        if (name == null) {
            throw new IllegalArgumentException("Tên không được null");
        }
        if (StringUtils.isBlank(name)) {
            return "Xin chào, Khách!";
        }
        String normalized = name.strip().toLowerCase(Locale.ROOT);
        return "Xin chào, " + StringUtils.capitalize(normalized) + "!";
    }
}
```

Tạo `src/main/java/dev/example/App.java`:

```java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.forName("  mAVeN  "));
    }
}
```

Chương trình gọi `StringUtils.isBlank` và `StringUtils.capitalize` từ Commons Lang. JVM cần có Commons Lang trên runtime classpath; Exec Maven Plugin sẽ cấp classpath theo graph Maven khi chạy đúng cấu hình.

### 5.3. Ba unit tests JUnit Jupiter

Tạo `src/test/java/dev/example/GreetingTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void normalizesName() {
        assertEquals("Xin chào, Maven!",
                Greeting.forName("  mAVeN  "));
    }

    @Test
    void usesFallbackForBlankInput() {
        assertEquals("Xin chào, Khách!",
                Greeting.forName("   "));
    }

    @Test
    void rejectsNullName() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.forName(null));
    }
}
```

Ba test độc lập, không truy cập mạng, file hoặc thời gian; chúng chỉ cần code chính, Commons Lang, JUnit và test runner phù hợp. Khi chạy qua Surefire, kết quả mong đợi là **3 tests thành công, không lỗi và không thất bại**.

### 5.4. Chạy chương trình bình thường

Từ thư mục có `pom.xml`:

```bash
mvn -version
mvn clean verify
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Khi dependencies/plugins có thể tải và JDK phù hợp, `verify` tạo các đầu ra thường gặp:

```text
target/classes/dev/example/Greeting.class
target/classes/dev/example/App.class
target/test-classes/dev/example/GreetingTest.class
target/surefire-reports/
target/offline-maven-lab-1.0.0-SNAPSHOT.jar
```

Stdout **do chương trình Java tạo ra** là chính xác:

```text
Xin chào, Maven!
```

Maven có thể in log riêng. Không coi một lần chạy `java -cp target/classes dev.example.App` bị lỗi thiếu Commons Lang là bằng chứng cache sai: lệnh JVM đó không tự đưa các JAR bên ngoài vào classpath. Dùng Exec Plugin hoặc runtime classpath được xây dựng đúng.

## 6. Quy trình chuẩn bị cache riêng và xác minh offline

Thí nghiệm nên dùng một **local repository riêng** để không nhầm thành công nhờ cache đã tích lũy của các dự án khác trên máy. Ta đặt cache tại `.maven-repo-lab/` bên trong thư mục dự án **chỉ cho mục đích thực hành**, và phải bỏ qua nó trong Git.

**Không xóa hoặc làm sạch local repository dùng chung của người dùng.** Cache riêng giúp quan sát rõ Maven đã tải gì; nó có thể chiếm dung lượng lớn nhưng không ảnh hưởng tới `~/.m2/repository` mặc định.

### Bước 1 — Chọn một local repository riêng

Bash/zsh trên Linux/macOS (chạy từ `offline-maven-lab`):

```bash
mvn -version
export MAVEN_LAB_REPO="$PWD/.maven-repo-lab"
```

Windows PowerShell:

```powershell
mvn -version
$MAVEN_LAB_REPO = Join-Path (Get-Location).Path ".maven-repo-lab"
```

Dùng cùng đường dẫn repository ở mọi lệnh tiếp theo. Trên Bash, đối số `"-Dmaven.repo.local=$MAVEN_LAB_REPO"` được quote nguyên khối để đường dẫn có khoảng trắng không bị tách.

Thêm vào `.gitignore` của **dự án lab**:

```gitignore
target/
.maven-repo-lab/
```

Đây là ví dụ nội dung file `.gitignore`, không phải lệnh shell. Không commit cache Maven, file metadata cục bộ hoặc artifact build.

### Bước 2 — Chuẩn bị với go-offline khi còn mạng

Bash/zsh:

```bash
mvn -B -ntp "-Dmaven.repo.local=$MAVEN_LAB_REPO" dependency:go-offline
```

Windows PowerShell:

```powershell
mvn -B -ntp "-Dmaven.repo.local=$MAVEN_LAB_REPO" dependency:go-offline
```

Với POM bài thực hành, version Dependency Plugin đã được ghim nên Maven biết goal plugin cần gọi. Nếu muốn gọi bằng tọa độ đầy đủ, tương đương là:

```bash
mvn -B -ntp "-Dmaven.repo.local=$MAVEN_LAB_REPO" org.apache.maven.plugins:maven-dependency-plugin:3.9.0:go-offline
```

Ý nghĩa cờ:

- `-B`: batch mode, thích hợp với CI.
- `-ntp`: không in thanh tiến độ tải.
- `-Dmaven.repo.local=...`: chỉ định local repository **cho chính lần chạy này**.
- `dependency:go-offline`: chủ động phân giải dependencies/plugins/reports mà goal nhìn thấy.

**Kết quả cần kiểm tra:** Maven báo `BUILD SUCCESS` khi goal hoàn tất. Nếu `Could not transfer artifact`, `PKIX path building failed`, timeout, unauthorized hoặc lỗi tương tự, cache có thể chưa đầy đủ. Hãy sửa kết nối/repository/settings trong pha online, **đừng coi lỗi đó là QA nội dung hoặc mặc định mọi artifact đã có đủ**.

### Bước 3 — Warm cache bằng chính build thật khi còn online

Tiếp tục ở môi trường có mạng, dùng **đúng cùng repository**.

Bash/zsh và PowerShell đều dùng:

```bash
mvn -B -ntp "-Dmaven.repo.local=$MAVEN_LAB_REPO" clean verify
mvn -q "-Dmaven.repo.local=$MAVEN_LAB_REPO" -Dexec.mainClass=dev.example.App exec:java
```

Lệnh thứ nhất phải biên dịch và chạy cả ba test; lệnh thứ hai chạy App và in `Xin chào, Maven!`. Bước này cố ý bổ sung cho `go-offline` vì plugin có thể phân giải một số thành phần **chỉ khi execution thực tế chạy**, ví dụ provider kiểm thử hoặc công cụ phụ được chọn động.

Nếu dự án thật có thêm `javadoc:javadoc`, `spotbugs:check`, code generation, Docker/build image, integration tests, deploy hay custom goals, cần chạy **đúng các goal cần dùng sau khi mất mạng** trong pha warm-up khi chúng có thể truy cập mạng. Tuy nhiên không thực hiện `deploy` vào môi trường production chỉ để warm cache; hãy thiết kế pipeline chuẩn bị an toàn hoặc dùng môi trường test được cấp quyền.

### Bước 4 — Xác minh offline bằng Maven -o

Khi pha online đã thành công, có thể **ngắt kết nối mạng** rồi thử:

Bash/zsh và PowerShell:

```bash
mvn -B -ntp -o "-Dmaven.repo.local=$MAVEN_LAB_REPO" clean verify
mvn -q -o "-Dmaven.repo.local=$MAVEN_LAB_REPO" -Dexec.mainClass=dev.example.App exec:java
```

Đây mới là **phép kiểm chứng ngoại tuyến**.

Kết quả thành công mong đợi:

1. Maven hoàn tất `clean verify` với trạng thái `BUILD SUCCESS` trong offline mode.
2. Surefire chạy **3 tests**, tất cả pass.
3. JAR chính có tại `target/offline-maven-lab-1.0.0-SNAPSHOT.jar`.
4. Lệnh Exec Plugin offline chạy thành công và stdout từ Java là:

```text
Xin chào, Maven!
```

**Kết luận chính xác:** cache đang được kiểm tra **đủ cho hai lệnh này**, trên **Maven/JDK/settings/profiles/POM/local repository** hiện tại. Nó **không tự chứng minh** mọi goal khác, mọi profile khác hay một bản build từ mã nguồn đã đổi đều sẽ chạy offline.

### Bước 5 — Kiểm tra cache và tình huống lỗi có kiểm soát

Tại thư mục dự án trên Bash:

```bash
ls "$MAVEN_LAB_REPO/org/apache/commons/commons-lang3/3.17.0/"
ls "$MAVEN_LAB_REPO/org/junit/jupiter/junit-jupiter/5.11.4/"
ls "$MAVEN_LAB_REPO/org/apache/maven/plugins/maven-surefire-plugin/3.5.2/"
```

Trên PowerShell:

```powershell
Get-ChildItem (Join-Path $MAVEN_LAB_REPO "org/apache/commons/commons-lang3/3.17.0")
Get-ChildItem (Join-Path $MAVEN_LAB_REPO "org/junit/jupiter/junit-jupiter/5.11.4")
Get-ChildItem (Join-Path $MAVEN_LAB_REPO "org/apache/maven/plugins/maven-surefire-plugin/3.5.2")
```

Cấu trúc thực tế có thể chứa JAR, POM và metadata khác. Thấy ba thư mục **không chứng minh cache đầy đủ**, vì các transitive/plugin dependencies khác vẫn có thể thiếu. Phép kiểm chứng quyết định vẫn là build ở `-o`.

Để hiểu bản chất của thiếu cache, có thể tạo **một cache lab khác hoàn toàn trống** rồi chạy `mvn -o ... clean verify`. Lệnh này thường báo thiếu artifact/plugin khi cache mới chưa được chuẩn bị. **Không xóa cache đang dùng chung hoặc cache của lab vừa xác minh** chỉ để tạo lỗi. Hãy dùng đường dẫn mới, hoặc bỏ qua thử nghiệm phá vỡ nếu máy có dữ liệu quan trọng.

## 7. Vì sao go-offline có thể báo thành công nhưng mvn -o vẫn thất bại?

Đây là giới hạn thực tế quan trọng nhất.

### 7.1. Plugin tải thành phần động khi goal chạy

Một số plugin có lựa chọn dependency/provider dựa vào project classpath, cấu hình goal hoặc môi trường ở thời điểm chạy. `go-offline` có thể phân giải các dependencies tĩnh được khai báo nhưng không biết mọi thành phần được tải động trong tương lai.

**Ví dụ điển hình:** bộ chạy test Surefire có thể phải giải quyết một provider thích hợp trong lúc chạy test. Nếu provider chưa có trong local repository, `go-offline` có thể thành công nhưng `mvn -o test` sau đó vẫn lỗi.

**Khắc phục:** chạy online những phase/goal thật như `mvn clean verify` để warm cache, rồi kiểm chứng lại bằng `-o`. Tránh tuyên bố `go-offline` đảm bảo tuyệt đối cho mọi plugin/version.

### 7.2. Một profile khác thay đổi dependency graph

Nếu chuẩn bị cache không có profile `integration` nhưng offline build lại chạy `mvn -P integration verify`, profile có thể bật dependencies, plugins hoặc repository khác chưa từng được tải.

Dùng cùng lựa chọn profile ở cả hai pha:

```bash
mvn -P integration dependency:go-offline
mvn -P integration clean verify
mvn -o -P integration clean verify
```

Đây là **mẫu quy trình**, chỉ chạy nguyên văn khi POM thật sự định nghĩa profile `integration`. Dự án bài thực hành ở mục 5 **không có profile này**, nên không chạy ba lệnh ấy trên POM mẫu.

### 7.3. Khác settings, mirror hoặc local repository

Hai lệnh Maven có thể dùng cache khác nhau vì:

- Một lệnh dùng `-s settings-ci.xml`, lệnh khác dùng `~/.m2/settings.xml`.
- Một lệnh đặt `-Dmaven.repo.local=/cache/a`, lệnh khác đặt `/cache/b`.
- Mirror/repository ID khác nhau khiến metadata về nguồn artifact khác và Maven không thể xác nhận artifact thích hợp có sẵn trong offline mode.
- Một machine/CI worker có local repository trống dù máy lập trình viên đã warm.

Không đủ chỉ có thư mục tên `repository`; phải bảo đảm **đúng đường dẫn, đúng nguồn repository và đúng những artifact được phân giải cho build thực tế**.

### 7.4. POM, plugin version hoặc JDK thay đổi

Nếu sau warm-up bạn đổi:

- Version của dependency, imported BOM hoặc parent POM.
- Plugin version, packaging, profile hoặc bước chạy.
- JDK/toolchain hay hệ điều hành theo cách kích hoạt dependencies/classifiers khác nhau.
- Các mục cấu hình mở rộng plugin hoặc module được build.

thì cache cũ có thể không còn đủ. Một offline build đạt PASS hôm qua không chứng minh offline build ngày mai vẫn chạy sau khi đổi POM.

### 7.5. Phiên bản SNAPSHOT và metadata

Một `1.0.0-SNAPSHOT` có thể được xuất bản nhiều lần ở remote repository. Khi offline, Maven **không thể kiểm tra bản SNAPSHOT mới từ remote**, nên có thể dùng bản đã cache hoặc thất bại nếu thiếu artifact phù hợp.

Khi chuẩn bị online, dùng chính sách cập nhật hợp lý (có thể dùng `-U` trong một lệnh online nếu cần kiểm tra SNAPSHOT mới). **Không ghép `-U` với `-o` rồi kỳ vọng Maven cập nhật từ xa trong offline mode.** Đối với build cần độ tái lập cao, ưu tiên các release versions bất biến và quản lý checksum/supply chain.

### 7.6. Test, báo cáo và tích hợp ngoài Maven Resolver

`-o` ngăn Maven thực hiện việc giải quyết artifact từ remote repository bằng cơ chế chuẩn. Nhưng một **plugin hoặc ứng dụng bên thứ ba tự gọi HTTP** có thể vẫn cố truy cập dịch vụ bên ngoài trong quá trình chạy goal; tính năng offline của Maven không phải firewall.

Ví dụ integration tests gọi API thực, Docker image pull, plugin tải browser executable hoặc cơ chế code generation tự gọi endpoint. Khi muốn chứng minh **không cần mạng thật sự**, kiểm tra thêm dưới môi trường mạng bị ngắt/chặn theo chính sách, không chỉ nhìn trạng thái Maven `BUILD SUCCESS` với cờ `-o`.

## 8. Tại sao cần phân biệt cache Maven với target/ và Git?

| Thư mục | Nội dung | Vai trò offline |
| --- | --- | --- |
| `src/main/java`, `src/test/java`, `pom.xml` | Mã nguồn và mô hình dự án | Đầu vào cần có; thường được version control |
| `target/` | Class, test reports và JAR do build tạo | Có thể xóa bằng `mvn clean`; không phải cache artifact Maven |
| `~/.m2/repository` hoặc kho chọn bằng `maven.repo.local` | Dependencies, plugins, POM, metadata đã phân giải | Nguồn artifact cục bộ để Maven chạy khi offline |
| `.mvn/wrapper/` và `mvnw` nếu có | File cấu hình/script Maven Wrapper | Giúp chọn Maven version, nhưng bản phân phối Maven Wrapper cần sẵn trên máy |
| `.maven-repo-lab/` trong bài thực hành | Local repository riêng để thử | Không commit; chỉ là cache của lab |

Khi chạy `mvn clean verify`, Maven xóa `target/` rồi tạo lại class và reports. Nó **không mặc định xóa toàn bộ local repository**. Do đó một cache được warm đúng vẫn có thể build offline sau `clean`.

Không commit toàn bộ `~/.m2/repository` vào Git như giải pháp lâu dài. Cache có thể rất lớn, chứa artifact không thuộc dự án và metadata gắn với repository khác. Trong CI, việc cache artifact phải được kiểm soát theo độ tin cậy của nguồn và checksum; không được xem cache là thư viện nguồn đáng tin chỉ vì nó tồn tại trên đĩa.

## 9. Maven Wrapper và JDK cũng phải có trước khi offline

Nếu dự án dùng Maven Wrapper (`./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows), cần phân biệt:

1. **Maven distribution** mà wrapper chỉ tới (có thể phải tải ở lần chạy đầu).
2. **Maven local repository** chứa artifact mà Maven dùng.
3. **JDK/toolchain** để biên dịch mã nguồn.

`dependency:go-offline` tập trung vào **dependencies/plugins của dự án Maven**, không đảm bảo bạn đã tải Maven distribution của wrapper hoặc cài JDK vào máy. Một laptop chưa từng chạy wrapper có thể thất bại offline **trước khi Maven bắt đầu**.

Khi chuẩn bị một máy chạy offline:

- Chạy wrapper online ít nhất một lần để Maven distribution đã được chuẩn bị, hoặc dùng bản Maven được provision trước.
- Xác nhận `mvn -version` hoặc `./mvnw -version` cho đúng Maven và JDK.
- Nếu sử dụng toolchain, annotation processor hoặc generator đặc biệt, đảm bảo các thành phần đó cũng sẵn có.
- Không giả định cùng cache giữa Linux và Windows khi có dependencies phân loại theo OS/architecture.

## 10. Dự án nhiều module (reactor) và offline build

Một dự án multi-module có thể có cấu trúc:

```text
parent/
├── pom.xml
├── common/
│   └── pom.xml
└── api/
    └── pom.xml
```

Module `api` có thể phụ thuộc module `common` cùng version SNAPSHOT. Khi build toàn reactor, Maven có thể giải quyết dependency giữa các module từ kết quả đang được xây dựng trong reactor, **không cần tải module common từ remote repository**.

Với Maven Dependency Plugin `go-offline`, tham số `excludeReactor` mặc định `true` nghĩa là không cố phân giải những artifact thuộc reactor hiện tại như dependency cần tải từ remote. Đây thường là hành vi phù hợp để warm những thứ bên ngoài reactor.

Nhưng nếu lúc offline chỉ build module `api` và bỏ `common`, dependency nội bộ đó có thể không còn trong reactor. Khi ấy cần:

- Build các module phụ thuộc cùng nhau (ví dụ dùng `-pl api -am` từ root).
- Hoặc đã cài/xuất bản artifact của module `common` vào một local repository phù hợp trước đó.

Ví dụ **chỉ dành cho dự án multi-module có module `api` thật**:

```bash
mvn -pl api -am clean verify
mvn -o -pl api -am clean verify
```

`-pl` chọn module; `-am` yêu cầu Maven build thêm các module mà module được chọn phụ thuộc. Dự án demo mục 5 là **single-module**, không có `api`; không chạy những lệnh này trên nó.

**Lỗi thường gặp:** cache chỉ chứa dependencies bên ngoài, nhưng không có module nội bộ cần khi build riêng. `go-offline` không thể thay thế việc chọn đúng reactor hoặc cài/xuất bản module tự viết.

## 11. Chuẩn bị cache cho CI hoặc môi trường không có mạng

Một pipeline có thể tách thành hai pha:

### Pha A: có mạng và được phép truy cập repository

- Checkout đúng commit, dùng đúng Maven/JDK/settings/profiles.
- Chạy `dependency:go-offline`.
- Chạy lifecycle thật (ví dụ `clean verify`) và những plugin goals cần sau này để warm các thành phần động.
- Lưu cache local Maven repository phù hợp vào kho cache của CI nếu chính sách nền tảng cho phép.
- Kiểm soát quyền truy cập, nguồn repository, checksum, cỡ cache và vòng đời lưu trữ.

### Pha B: môi trường offline

- Dùng cùng commit/POM và cấu hình tương thích.
- Phục hồi cache vào **đúng local repository** được Maven chỉ định.
- Xác nhận Maven/JDK/toolchains và những công cụ ngoài Maven đã được provision.
- Chạy `mvn -o clean verify` hoặc lệnh tương ứng, không tự thêm goals chưa warm.
- Báo lỗi đúng artifact/plugin thiếu; không tự bí mật bật network để “chữa” offline build.

**Lưu ý:** cache CI đôi khi dùng key theo POM, lock version của wrapper/JDK/OS; key quá rộng có thể chứa artifact lỗi thời hoặc artifact từ repo không đáng tin. Cache không thay thế một artifact repository nội bộ và không thay thế việc kiểm soát phiên bản dependencies.

### Ví dụ skeleton Bash cho hai giai đoạn

Giả định repository ở `$PWD/.maven-repo-lab` và pipeline thật đã có Maven/JDK:

```bash
# Online preparation
REPO="$PWD/.maven-repo-lab"
mvn -B -ntp "-Dmaven.repo.local=$REPO" dependency:go-offline
mvn -B -ntp "-Dmaven.repo.local=$REPO" clean verify

# Sau khi cache duoc mang sang moi truong offline:
mvn -B -ntp -o "-Dmaven.repo.local=$REPO" clean verify
```

Đây là **mẫu logic**, không phải cấu hình cho một nhà cung cấp CI cụ thể. Bước copy/cache giữa các môi trường cần làm theo chính sách pipeline. Không dùng đường dẫn tuyệt đối có tên máy cá nhân trong artifact cache, vì chúng không tự phù hợp với runner mới.

## 12. Các thông báo lỗi khi build offline và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Cannot access ... in offline mode` | Maven cần artifact từ một remote repository nhưng cache phù hợp chưa có | Quay lại pha online với cùng settings/repo, warm artifact rồi thử lại |
| `Plugin ... has not been downloaded from it before` | Plugin hoặc metadata cần thiết không ở cache tương ứng | Ghim plugin version, chạy goal/lifecycle online rồi xác minh offline |
| `No plugin found for prefix ...` | Plugin prefix/metadata chưa được giải quyết, plugin chưa khai báo rõ | Khai báo plugin trong POM hoặc gọi full coordinates và warm online |
| `Could not resolve dependencies` khi chạy test | Thiếu JUnit/transitive/provider hoặc profile test khác pha chuẩn bị | Warm `clean verify` online đúng profile, kiểm tra dependency tree |
| `Non-resolvable parent POM` | Thiếu parent hoặc repository chứa parent | Kiểm tra parent coordinates, offline cache và `relativePath` nếu thích hợp |
| `Could not find artifact ... SNAPSHOT` | Snapshot chưa cache, đổi version hoặc metadata nguồn khác | Tải đúng SNAPSHOT online với repo/settings tương ứng |
| `go-offline` thành công nhưng `verify` offline thất bại | Plugin giải quyết thêm artifact lúc thực thi | Chạy đủ lifecycle online để warm rồi xác minh `-o` |
| Offline thành công trên laptop nhưng lỗi CI | CI có cache trống, settings/mirror khác, JDK/OS khác | So sánh cache path, POM, profiles, settings, wrapper/JDK |
| Maven Wrapper thất bại trước khi load POM | Bản Maven distribution chưa có trên máy | Provision/warm wrapper khi online |
| `mvn -o clean verify` pass nhưng test HTTP vẫn lỗi | Test/plugin tự truy cập dịch vụ ngoài Maven Resolver | Mock/service stub hoặc provision service offline |
| Một số mục ở `~/.m2/repository` mà Maven vẫn đòi tải | Metadata theo repository, local repo path khác hoặc artifact thiếu POM/JAR | Xem effective settings và lỗi đầy đủ; không chép JAR ngẫu nhiên |
| `mvn dependency:go-offline` offline thất bại ngay | Chạy goal chuẩn bị trong khi cache còn thiếu | Chuyển sang pha có quyền tải trước khi thử `-o` |
| Chỉ `package` offline pass nhưng `verify` fail | Goal ở giai đoạn verify/report/integration test cần artifact khác | Warm đúng phase/goal theo yêu cầu |
| `mvn clean` xóa `target` nhưng cache vẫn còn | `clean` không xóa local Maven repository | Đây là hành vi bình thường |

Khi phân tích lỗi, hãy đọc **tọa độ artifact/plugin thiếu**, **repository ID/URL liên quan**, **phase/goal gây lỗi** và **local repository thật**. Lỗi offline thường là thiếu một đầu vào, chứ không phải do câu lệnh `-o` “không hoạt động”.

**Không làm việc sau đây**: xóa toàn bộ `~/.m2/repository` trên máy làm việc chung để “refresh” khi còn chưa biết vấn đề; ghi đè các artifact release bằng JAR tải từ nguồn không rõ; chuyển tạm `-o` thành build online trong CI mà không báo; hoặc tắt test chỉ để đạt trạng thái BUILD SUCCESS.

## 13. Offline build có đồng nghĩa reproducible hoặc hermetic build?

Ba khái niệm liên quan nhưng không đồng nhất:

- **Offline build:** Maven không phải lấy thêm artifact từ repository từ xa theo cơ chế giải quyết thông thường và vẫn chạy được với các đầu vào đã sẵn có.
- **Reproducible build:** với đầu vào và công cụ tương đương, nội dung artifact tạo ra có thể được tạo lại một cách nhất quán; còn phụ thuộc cấu hình timestamp, encoding, toolchain, filesystem và plugin.
- **Hermetic build:** kiểm soát toàn bộ các đầu vào và chặn phụ thuộc không khai báo vào môi trường ngoài; `-o` chỉ tác động tới Maven Resolver nên chưa đủ để đảm bảo hermetic.

Một bài lab có thể chứng minh `mvn -o clean verify` đạt PASS nhưng chưa chứng minh JAR bit-for-bit giống nhau giữa máy. Tương tự, `mvn -o` không chặn plugin tự gửi HTTP request tới dịch vụ ngoài Maven.

Nếu tổ chức cần build tái lập và bảo mật cao, nên kết hợp ghim versions, repository mirror được kiểm soát, kiểm tra checksum, toolchain rõ ràng, kiểm soát biến môi trường, tách secret và một môi trường build hạn chế network thật sự.

## 14. Checklist kiểm chứng go-offline có đáng tin không?

Trước khi kết luận dự án hỗ trợ offline build, kiểm tra:

1. Đã dùng **đúng POM/commit/branch** sẽ dùng ở môi trường offline.
2. **Maven và JDK** đã được cài hoặc wrapper distribution đã được chuẩn bị.
3. POM ghim versions của dependencies và plugins quan trọng; parent/BOM có thể phân giải.
4. **Cùng settings, mirror, active profiles và local repository** được sử dụng trong cả pha chuẩn bị và pha offline.
5. `dependency:go-offline` đã chạy **online thành công** mà không vô tình loại scope/test/transitive cần thiết.
6. Đã chạy **toàn bộ lifecycle/goal cần dùng** khi online để warm phần tải động.
7. Cache có POM/JAR/plugin và metadata phù hợp với repository đã phân giải.
8. Đã chạy **`mvn -o clean verify`** với cùng cấu hình; không chỉ chạy `compile` hoặc `package` nếu CI cần verify.
9. Đã thử **các custom goals** hoặc integration tests cần dùng với `-o`.
10. Nếu yêu cầu **thực sự không có mạng**, đã thử ở môi trường ngắt mạng/chặn egress phù hợp.
11. Nếu dùng multi-module, đã chọn đúng reactor và nội bộ module có sẵn.
12. Đã ghi lại phạm vi chứng minh: **lệnh nào, profile nào, JDK/Maven nào, cache nào** đã PASS.

## 15. Bài tập và câu hỏi tự kiểm tra

1. Giải thích sự khác nhau giữa `dependency:go-offline` và `mvn -o clean verify`. Lệnh nào chủ yếu **chuẩn bị**, lệnh nào **kiểm chứng**?
2. Tạo dự án `offline-maven-lab`, chọn cache `.maven-repo-lab/` và chạy goal `go-offline` trong lúc có mạng.
3. Chạy `mvn clean verify` online với **cùng local repository**, xác nhận ba test đều PASS. Tại sao warm cả goal test quan trọng hơn chỉ đọc danh sách dependencies?
4. Ngắt mạng hoặc hạn chế truy cập repository, chạy `mvn -o clean verify` và `mvn -o exec:java`. Ghi lại stdout `Xin chào, Maven!`.
5. Chọn một local repository **khác và trống**, thử `mvn -o clean verify`. Dự đoán kiểu lỗi và giải thích tại sao cache trước đó không tự đi theo sang đường dẫn mới.
6. Trong một dự án khác, chỉ chạy `go-offline` mà không warm test. Nếu Surefire cần provider phát sinh khi chạy, điều gì có thể xảy ra offline?
7. Tạo profile test (trong một POM riêng để thử), chỉ bật khi chạy `-P integration`. Vì sao chuẩn bị không bật profile ấy có thể bỏ sót dependencies?
8. Tại sao `mvn dependency:tree` không thay thế việc kiểm chứng đầy đủ cả Maven plugins và custom goals?
9. Trong dự án multi-module có `common` và `api`, vì sao nên dùng `-pl api -am` khi chỉ chọn module api để build offline?
10. Phân biệt lỗi thiếu parent POM, thiếu plugin, thiếu test provider, JDK chưa được provision và lỗi HTTP do test tự gọi dịch vụ ngoài.
11. Nếu có SNAPSHOT dependency mới vừa được publish, `-o` có tự lấy bản mới không? Tại sao?
12. Một nhóm muốn tuyên bố “hermetic build” chỉ vì `mvn -o clean verify` pass. Cần những điều kiện nào khác để lời tuyên bố đó chính xác?

## 16. Kết luận

**`dependency:go-offline` là bước chuẩn bị, `mvn -o` là cơ chế xây dựng ngoại tuyến và phép kiểm chứng phù hợp phải chạy đúng workflow thực tế.** Maven cần nhiều thứ hơn các JAR của mã chính: parent POM, BOM, plugins, transitive dependencies, test provider và đôi khi những thành phần phát sinh động.

Cách học và áp dụng đáng tin nhất:

1. Dùng một local repository rõ ràng, không nhầm với `target/`.
2. Chạy `dependency:go-offline` khi còn mạng.
3. Warm đầy đủ lifecycle/goal khi online.
4. Chạy lại cùng workflow với `-o` trên cùng cache, tốt nhất trong môi trường đã ngắt mạng nếu mục tiêu yêu cầu.
5. Khi lỗi, sửa thiếu artifact/plugin hoặc khác biệt cấu hình **theo bằng chứng**, không xóa cache bừa hoặc bỏ test.

## 17. Tài liệu chính thức

- [Apache Maven Dependency Plugin — dependency:go-offline](https://maven.apache.org/components/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Apache Maven Dependency Plugin — Overview](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Apache Maven — Introduction to Repositories, Building Offline](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)

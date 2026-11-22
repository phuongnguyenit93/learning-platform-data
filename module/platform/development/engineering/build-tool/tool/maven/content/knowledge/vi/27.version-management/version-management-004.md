# Cập nhật phiên bản dự án, parent hoặc dependency có kiểm soát trong Maven

## 1. Ba thay đổi version khác nhau, ba loại rủi ro

Một repository Maven có thể chứa phiên bản của **artifact đang build**, **parent POM**, **dependency**, **BOM**, **build plugin** và **JDK/Maven**. Các giá trị này nằm ở những phần POM khác nhau và có tác động khác nhau.

- **Đổi project version** từ `1.0.0-SNAPSHOT` thành `1.1.0-SNAPSHOT`: đổi định danh GAV của artifact được tạo. Với multi-module, cần thống nhất version của parent, children và những tham chiếu tới module nội bộ.
- **Đổi parent version** từ `2.4.0` thành `2.5.0`: có thể đổi toàn bộ effective model được kế thừa như plugin versions, dependency management, Maven profiles, compiler level, repositories và policy.
- **Đổi dependency version** của `org.apache.commons:commons-lang3` từ `3.14.0` thành `3.16.0`: thay một thư viện trong compile/runtime classpath thực sự, có thể đổi API, ABI, transitive dependencies hoặc minimum Java.
- **Đổi BOM version**: một dòng `<version>` của BOM có thể kéo theo nhiều phiên bản dependency được quản lý. Không nên coi là thay đổi nhỏ chỉ vì Git diff ngắn.
- **Đổi Maven plugin version**: sửa chính công cụ biên dịch, chạy test hoặc đóng gói. Tác động khác với nâng một thư viện ứng dụng.

**Cập nhật có kiểm soát** nghĩa là có một version đích được phê duyệt, một phạm vi thay đổi rõ, bản so sánh trước–sau, kiểm thử phù hợp, cách rollback và một bước review trước publish. `mvn package` xanh chưa chứng minh mọi thay đổi tương thích production.

Mục tiêu học tập: phân biệt các nơi quản lý version; sử dụng đúng goal của **MojoHaus Versions Maven Plugin**; nâng project/parent/dependency mà không thay nhầm những artifact khác; kiểm tra bằng `help:effective-pom`, `dependency:tree`, unit/integration tests; và xử lý backups/rollback an toàn.

## 2. Bản đồ version trong POM

| Nơi khai báo | Ý nghĩa | Tác động cần kiểm tra |
| --- | --- | --- |
| `project/version` | Version của project artifact, một phần GAV. | Module siblings, parent references, JAR name, release metadata. |
| `parent/version` | Version của parent POM dùng để kế thừa model. | Effective POM, plugin defaults, dependencyManagement, Java target. |
| `dependencies/dependency/version` | Version của một dependency trực tiếp. | Classpath và các đường transitive. |
| `dependencyManagement/.../version` | Version/metadata khi một dependency **được sử dụng**. | Những modules thực sự khai báo dependency đó. |
| `properties` | Biến để thay các versions được tham chiếu. | Phạm vi nơi property được sử dụng/override. |
| BOM `type=pom`, `scope=import` | Nhập một bộ managed versions. | Nhiều selected dependency versions có thể đổi. |
| `build/plugins` | Plugin thực sự được khai báo cho build. | Goal, lifecycle, Maven/JDK prerequisites. |
| `build/pluginManagement` | Version/config của plugin khi được sử dụng. | Không tự kích hoạt mọi goal hoặc tạo dependency ứng dụng. |

**`dependencyManagement` không tự thêm dependency vào classpath.** Nếu parent có quản lý `commons-lang3` nhưng child không khai báo và cũng không nhận qua dependency graph, cập nhật managed version không làm ứng dụng tự dùng Commons Lang. Khi module thực sự có `<dependency>`, phiên bản được quản lý mới có hiệu lực.

Tương tự, `<modules>` thu thập projects vào Maven Reactor; khai báo một module trong `<modules>` không có nghĩa module khác phụ thuộc vào nó. Một dependency thật giữa hai modules mới tạo cạnh sắp thứ tự cần thiết.

## 3. Không hiểu Maven version là Semantic Versioning bắt buộc

Các giá trị hợp lệ thường thấy:

~~~text
1.0.0-SNAPSHOT
1.0.0
1.1.0-RC1
2.0.0
2026.11
~~~

Maven có cơ chế so sánh version riêng, **không bắt buộc mọi thư viện tuân thủ SemVer**. Vì thế không thể suy ra “patch luôn an toàn”, “major chắc chắn phá API” hoặc “latest chắc chắn tốt nhất”.

- `-SNAPSHOT` là bản phát triển có thể được publish lại theo metadata của snapshot repository. Dependency SNAPSHOT làm build kém tái lập hơn release version cố định.
- Một release coordinate như `3.16.0` thường ổn định hơn SNAPSHOT, nhưng tính bất biến file artifact còn phụ thuộc chính sách repository.
- RC/milestone/beta có thể chưa phù hợp cho production dù plugin báo có version cao hơn.
- Một version mới có thể nâng minimum JDK, đổi package/module names, API, reflection contracts hoặc các dependencies bắc cầu.
- **Đừng dùng dải version động như một cách thay thế review tương thích.** Với dependency quan trọng, ưu tiên pin release version đã kiểm chứng.

Ví dụ Commons Lang `3.14.0` và `3.16.0` dùng ở bài là các version có thật; **không có ý nói 3.16.0 là bản mới nhất** hoặc luôn nên nâng lên nó.

## 4. Bắt đầu từ một bản kế hoạch thay đổi

Trước khi sửa POM, lập một bản change record ngắn:

~~~text
Mục tiêu            Nâng Commons Lang trong module app
Artifact            org.apache.commons:commons-lang3
Từ version          3.14.0
Đến version         3.16.0
Nguồn quản lý       root pom.xml / property commons-lang3.version
Phạm vi             Những modules thực sự dùng Commons Lang
Không thay          Project version, parent version, JUnit, compiler plugin
Kiểm chứng          clean verify + effective POM + dependency tree
Rollback            Revert đúng property/backup của thao tác
Phê duyệt           Review release notes, CI, pull request
~~~

Đây là **mẫu kế hoạch**, không phải thông tin từ một dự án thật. Một PR chỉ đổi đúng một loại version thường dễ kiểm thử và rollback hơn PR đồng thời nâng parent, BOM, plugins và tất cả dependencies.

Đối với parent hoặc project version, record cần bổ sung: root/children nào bị đổi GAV, consumer bên ngoài có tham chiếu version cũ không, và artifact nào sẽ được phát hành từ phiên bản mới.

## 5. Versions Maven Plugin: đọc và sửa là hai nhóm goal

**MojoHaus Versions Maven Plugin** cung cấp các goal khác nhau. Tài liệu này dùng **plugin `2.22.0`** được gọi bằng đầy đủ GAV/goal, tránh vô tình dùng version khác qua plugin prefix resolution.

### Goal giúp quan sát candidate versions

~~~text
versions:display-dependency-updates
versions:display-property-updates
versions:display-parent-updates
versions:display-plugin-updates
~~~

Những goal này hiển thị các phiên bản mà repository/mirror được cấu hình cho Maven có thể tìm thấy. **Kết quả là đầu vào phân tích, không phải quyết định phê duyệt nâng cấp.**

### Goal thay đổi POM

| Goal | Mục đích | Cảnh báo |
| --- | --- | --- |
| `versions:set` | Đổi project version và cập nhật matching child/parent references trong aggregation. | Kiểm tra mọi POM bị sửa; không tự động sửa toàn bộ file ngoài POM. |
| `versions:set-property` | Đặt một version property đến giá trị chỉ định. | Không tự bảo đảm version tồn tại hay API tương thích. |
| `versions:update-parent` | Chọn parent version mới, có thể giới hạn bằng range. | Nếu chạy mặc định có thể nhảy tới version ngoài kế hoạch. |
| `versions:use-dep-version` | Đặt version cụ thể cho dependency được chọn. | Xác định version đang ghi trực tiếp hay đến từ property/BOM. |
| `versions:update-properties` | Tìm/nâng version properties theo cấu hình. | Có thể làm đổi nhiều dependencies; đọc toàn bộ diff. |
| `versions:use-latest-releases` | Thay nhiều release deps bằng release mới nhất tìm thấy. | Không nên chạy vô điều kiện trên branch phát hành. |
| `versions:commit` | Xóa `pom.xml.versionsBackup`. | **Không phải Git commit**, không chạy test hoặc publish. |
| `versions:revert` | Khôi phục POM từ plugin backup. | Không gọi mù nếu có thay đổi hợp lệ sau khi tạo backup. |

Các lệnh sửa POM nên chạy **riêng với lệnh build** vì Maven đã nạp model trước khi goal thay file. Ví dụ tốt:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.1.0-SNAPSHOT
mvn -B -ntp clean verify
~~~

Đây là **hai lần chạy Maven riêng biệt**. Không gộp goal sửa POM với `clean verify` trong cùng command rồi giả định Maven luôn xây lại model mới ngay lập tức.

## 6. Ví dụ multi-module Java 17 chạy được

Dự án thực hành có root **`version-control-lab`**, hai modules `core-lib` và `app`, JUnit Jupiter và Commons Lang. Cấu trúc:

~~~text
version-control-lab/
├── pom.xml
├── core-lib/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/versions/core/CoreLabel.java
│       └── test/java/vn/example/versions/core/CoreLabelTest.java
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/versions/app/App.java
        └── test/java/vn/example/versions/app/AppTest.java
~~~

Yêu cầu để chạy ví dụ: **JDK 17+**, Maven 3.9+ và Maven repository có thể cung cấp các dependencies/plugin được chốt version. Không cần Docker hay DB. Cả project dùng **một version chung `1.0.0-SNAPSHOT`** để minh họa `versions:set` đồng bộ parent và modules.

### 6.1. Root `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.versions</groupId>
    <artifactId>version-control-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core-lib</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <commons-lang3.version>3.14.0</commons-lang3.version>
        <junit.version>5.10.2</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>vn.example.versions</groupId>
                <artifactId>core-lib</artifactId>
                <version>${project.version}</version>
            </dependency>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons-lang3.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Giải thích cách thiết kế:**

- Root packaging `pom` đóng vai trò **aggregator** vì có `<modules>`, và **parent** vì children có `<parent>` trỏ tới root. Aggregation và inheritance vẫn là hai cơ chế độc lập.
- `commons-lang3.version` chỉ định một **nguồn version** cho Commons Lang. Module `app` không lặp version nữa.
- JUnit cũng được quản lý qua property nhưng `core-lib` và `app` cần khai báo JUnit **thật sự** ở `<dependencies>` nếu muốn dùng test API.
- Managed `core-lib` dùng `${project.version}`. Trong mô hình children cùng version, giá trị được resolve theo version project đã cập nhật, tránh hardcode sibling version riêng.
- `pluginManagement` chốt compiler/Surefire/JAR versions khi lifecycle sử dụng. Đừng nâng plugin chỉ vì đang làm một PR nâng Commons Lang.
- Source encoding và Java release được nêu tường minh để giảm khác biệt giữa các máy build.

### 6.2. `core-lib/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.versions</groupId>
        <artifactId>version-control-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Child kế thừa groupId/project version từ parent. Relative path giúp Maven tìm đúng parent POM khi build từ checkout.

### 6.3. `app/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.versions</groupId>
        <artifactId>version-control-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example.versions</groupId>
            <artifactId>core-lib</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Ở đây `app` có **actual dependency** vào `core-lib` và `commons-lang3`. Do vậy Maven Reactor build core trước app và root dependencyManagement mới được áp dụng.

Nếu app chỉ có managed entries trong root mà **không khai báo `<dependencies>`**, nó không tự có classes `CoreLabel` hoặc `StringUtils` trên compile classpath.

### 6.4. `core-lib/src/main/java/vn/example/versions/core/CoreLabel.java`

~~~java
package vn.example.versions.core;

public final class CoreLabel {
    private CoreLabel() {
    }

    public static String message() {
        return "core ready";
    }

    public static void main(String[] args) {
        System.out.println("Core: " + message());
    }
}
~~~

### 6.5. `core-lib/src/test/java/vn/example/versions/core/CoreLabelTest.java`

~~~java
package vn.example.versions.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CoreLabelTest {
    @Test
    void coreBehaviorStaysStable() {
        assertEquals("core ready", CoreLabel.message());
    }
}
~~~

### 6.6. `app/src/main/java/vn/example/versions/app/App.java`

~~~java
package vn.example.versions.app;

import org.apache.commons.lang3.StringUtils;
import vn.example.versions.core.CoreLabel;

import java.util.Locale;

public final class App {
    private App() {
    }

    public static String describe() {
        return "APP: " + StringUtils.upperCase(
                CoreLabel.message(), Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(describe());
    }
}
~~~

`App` trực tiếp dùng API Commons Lang và `CoreLabel`. Nâng version Commons Lang ảnh hưởng đường thực thi này; đó là lý do unit test phải kiểm tra hành vi chứ không chỉ kiểm tra con số trên POM.

### 6.7. `app/src/test/java/vn/example/versions/app/AppTest.java`

~~~java
package vn.example.versions.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void appStillFormatsCoreMessage() {
        assertEquals("APP: CORE READY", App.describe());
    }
}
~~~

Trong cấu trúc này có **hai unit test methods**, không cần Docker hoặc network service. Source Java phù hợp JDK 17. `StringUtils.upperCase(String, Locale)` có trong các Commons Lang versions được dùng trong ví dụ.

## 7. Baseline: chạy build trước khi sửa version

Từ thư mục root:

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

Kỳ vọng Maven Reactor build root, `core-lib`, `app`, các unit tests pass. Không assert thứ tự/số dòng log console ngoài phạm vi plugin được cấu hình, vì log phụ thuộc Maven/JDK/cache.

Chạy main độc lập của core:

~~~bash
java -cp core-lib/target/classes vn.example.versions.core.CoreLabel
~~~

Stdout **chính xác** của lệnh Java này:

~~~text
Core: core ready
~~~

Trên Windows PowerShell:

~~~powershell
java -cp core-lib\target\classes vn.example.versions.core.CoreLabel
~~~

Main của app còn cần Commons Lang và core. Để chạy nó **một cách có quản lý classpath** trên sandbox, trước hết cài artifact của reactor vào **local Maven repository**, sau đó dùng Exec Maven Plugin:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp -f app/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=vn.example.versions.app.App
~~~

Lệnh `install` **chỉ ghi local repository** (thường `.m2`), **không phải deploy lên remote**. `exec:java` dùng dependencies của app làm classpath; sau local install nó resolve được core-lib. Dòng do **`App.main` tự in**, không tính log của Maven/Exec Plugin:

~~~text
APP: CORE READY
~~~

Nếu mục đích chỉ là kiểm tra thay version tại source, `mvn clean verify` đã cho baseline unit tests. Với sản phẩm phát hành cần thêm smoke/integration tests trên artifact được publish.

## 8. Trước khi nâng: kiểm tra Git và phạm vi

Trên branch làm việc:

~~~bash
git status --short
git branch --show-current
mvn --version
~~~

Đọc các kết quả trước khi sửa. Nếu có thay đổi POM không thuộc nhiệm vụ, không dùng `git reset --hard`, `git restore .` hoặc `git clean -fd` để xóa chúng. Hãy tạo branch/worktree riêng hoặc bảo toàn thay đổi theo quy trình nhóm.

Một phiên bản được chọn nên có release notes, hướng dẫn migration và xác nhận Java/Maven compatibility. Tránh thay hàng loạt chỉ vì goal “latest” trả về con số cao nhất.

## 9. Tìm candidate versions trước, không tự động nâng

Gọi những goal chỉ quan sát:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-property-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-plugin-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-parent-updates
~~~

Đây là **công cụ khám phá**. Các candidates phụ thuộc repository/mirror, metadata và ruleSet; kết quả mới hơn **không đồng nghĩa an toàn hơn**.

Trước khi chốt target version, kiểm tra changelog, API/ABI compatibility, minimum Java, dependency graph, security advisories, license và môi trường vận hành. Tách stable release khỏi snapshot/RC theo policy.

## 10. Trường hợp A: nâng version của chính reactor

Giả sử mục tiêu là đồng bộ tất cả modules:

~~~text
1.0.0-SNAPSHOT -> 1.1.0-SNAPSHOT
~~~

Chạy tại root:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.1.0-SNAPSHOT
~~~

Với cấu trúc POM ví dụ, Versions Plugin `set` sẽ xử lý project version của root và những child/parent references phù hợp trong aggregation. **Vẫn phải đọc Git diff** chứ không coi việc plugin báo BUILD SUCCESS là bảo đảm mọi tham chiếu trong repository đã đúng.

Kỳ vọng root nhận:

~~~xml
<version>1.1.0-SNAPSHOT</version>
~~~

Mỗi child cập nhật parent reference:

~~~xml
<parent>
    <groupId>vn.example.versions</groupId>
    <artifactId>version-control-lab</artifactId>
    <version>1.1.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Còn managed dependency `core-lib` ở root là `${project.version}`, nên với mô hình cùng version, effective value theo project mới.

Sau thao tác:

~~~bash
git diff -- pom.xml core-lib/pom.xml app/pom.xml
mvn -B -ntp clean verify
mvn -B -ntp -pl :app help:effective-pom -Doutput=effective-app.xml
~~~

Trong effective POM của `app`, kiểm tra project version, parent version, version được resolve cho `core-lib` đều **`1.1.0-SNAPSHOT`**.

**Không suy ra Dockerfile, Git tag, Helm chart, CI artifact upload filename hay release documentation cũng được sửa.** Những file ngoài phạm vi POM phải được rà soát riêng.

### Nếu mỗi module có version độc lập?

Một số reactor không chia chung version: library có version `1.x`, CLI `2.x`. `versions:set` hỗ trợ các bộ lọc `groupId`, `artifactId`, `oldVersion`, `processAllModules`, `processFromLocalAggregationRoot`... nhưng phạm vi ảnh hưởng phải được xem kỹ theo plugin version.

**Đừng dùng `-DprocessAllModules=true` để ép tất cả project đổi version nếu các modules thực sự release độc lập.** Hãy lên kế hoạch từng module và references từ consumers.

## 11. Trường hợp B: nâng external parent

Đừng nhầm **đổi version của parent artifact nội bộ** ở trường hợp A với việc **đổi parent bên ngoài mà ứng dụng kế thừa**.

Một project giả định có:

~~~xml
<parent>
    <groupId>vn.example.build</groupId>
    <artifactId>team-parent</artifactId>
    <version>2.4.0</version>
    <relativePath/>
</parent>
~~~

**GAV này chỉ để minh họa**, không nằm trong project demo runnable. `<relativePath/>` giúp Maven resolve external parent từ configured repositories, thay vì mặc định tìm parent ở `../pom.xml`.

Nếu ban build platform phê duyệt **đúng `2.5.0`**, cách dễ review nhất là sửa riêng `<parent><version>` từ `2.4.0` thành `2.5.0`, xác minh parent artifact có tồn tại và đọc effective POM trước–sau.

Nếu muốn **cho phép một dải patch versions** đã duyệt:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:update-parent "-DparentVersion=[2.5.0,2.6.0)"
~~~

Ví dụ range `[2.5.0,2.6.0)` cho phép version `>=2.5.0` và `<2.6.0`. Nó **không khóa chính xác 2.5.0** nếu repository có patch version mới hơn trong dải. Lệnh chỉ áp dụng khi đang đứng trong **project thực sự có external parent cần cập nhật**, không chạy trên root demo không có parent.

Không dùng mặc định:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:update-parent
~~~

trên branch release mà chưa xác định giới hạn: goal có thể chọn parent mới hơn dự kiến theo repository metadata. Các tham số `parentVersion` và `skipResolution` tồn tại nhưng `skipResolution=true` bỏ bước resolve target version, dễ viết một version chưa có artifact; chỉ dùng khi lý do và fallback được kiểm soát.

### Vì sao parent upgrade cần full regression?

Parent mới có thể đổi:

- Compiler Plugin version hoặc `maven.compiler.release`.
- Surefire/Failsafe providers, test discovery/parallel/forks.
- DependencyManagement hoặc imported BOM versions.
- Resource filtering, generated sources, annotation processors.
- Plugin executions/lifecycle bindings, Enforcer quality gates.
- Repositories, profiles và activation.
- Build JDK/Maven minimum requirements.

Một dòng Git diff ở `<parent>` có thể làm **hàng chục selected versions và plugin behaviors thay đổi**. Đọc `help:effective-pom`, `dependency:tree` và chạy full `verify`; với ứng dụng deploy còn phải smoke test artifact cuối.

**Nếu parent là module của chính reactor**, việc nâng version đồng bộ cả root/children nên đi theo `versions:set` tại aggregation root (hoặc migration multi-module cụ thể), không dùng `update-parent` để tìm một release “latest” bên ngoài.

## 12. Trường hợp C: nâng dependency được điều khiển bởi property

Trong project demo, parent quản lý:

~~~xml
<commons-lang3.version>3.14.0</commons-lang3.version>
~~~

và trong dependencyManagement:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>${commons-lang3.version}</version>
</dependency>
~~~

Child app khai báo actual dependency **không có version literal**:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
~~~

Đặt target **3.16.0**:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:set-property -Dproperty=commons-lang3.version -DnewVersion=3.16.0
~~~

Expected source change chỉ là:

~~~xml
<commons-lang3.version>3.16.0</commons-lang3.version>
~~~

**`versions:set-property` không tự chạy API compatibility checks hoặc bảo đảm version được tải thành công**. Nó đặt property theo yêu cầu. Hãy kiểm tra:

~~~bash
git diff -- pom.xml app/pom.xml core-lib/pom.xml
mvn -B -ntp clean verify
mvn -B -ntp -pl :app help:effective-pom -Doutput=effective-app.xml
~~~

Trong effective POM của app, Commons Lang phải được resolve thành **3.16.0**, còn project version/JUnit/parent không thay đổi ngoài scope.

Kiểm tra dependency tree:

~~~bash
mvn -B -ntp -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Với goal chạy riêng và app phụ thuộc một reactor sibling, có thể cần `core-lib` artifact đã được cài local. Sau khi build:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

`install` chỉ ghi local repository; đây là bước tùy chọn để xem graph/chạy App trong sandbox, không phải thay thế tests. Đọc selected version trong graph thay vì chỉ search `commons-lang3` trong source XML.

Sau local install, có thể chạy app:

~~~bash
mvn -B -ntp -f app/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=vn.example.versions.app.App
~~~

Dòng **App.main** tự in phải là:

~~~text
APP: CORE READY
~~~

Test này chỉ kiểm tra phần API demo đang dùng, **không chứng minh mọi đường ứng dụng thật đều tương thích** với Commons Lang version mới.

## 13. Dependency khai báo version trực tiếp: sửa đúng nơi nguồn

Một project khác có thể ghi:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Với một dependency duy nhất, sửa thủ công `<version>` thành `3.16.0` có thể rõ ràng nhất. Nếu muốn dùng Versions Plugin để đặt một target cụ thể:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:use-dep-version -Dincludes=org.apache.commons:commons-lang3 -DdepVersion=3.16.0
~~~

Goal `use-dep-version` có thể ảnh hưởng những dependency declarations phù hợp trong phạm vi mà plugin hỗ trợ; **xem các parameters `processDependencies`, `processDependencyManagement`, `excludeReactor` và Git diff**.

Nếu version được quản lý qua `${commons-lang3.version}`, **thay property gốc** thường tốt hơn việc cố thay một resolved version ở child. Nếu version đến từ imported BOM, xem owner/version của BOM và phạm vi cập nhật trước khi sửa.

**Tránh nhiều nguồn version cho cùng artifact.** Ví dụ parent quản lý Commons Lang 3.14.0 nhưng child override thành 3.16.0 ở một profile có thể làm local và CI chọn version khác nhau. Khi có nhu cầu override có chủ đích, ghi lý do, phạm vi và test đúng profiles.

## 14. Nâng BOM: một dòng thay nhưng diện ảnh hưởng rộng

Một imported BOM minh họa:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **GAV giả định**, không phải artifact cần tải của project runnable. BOM là một **catalog managed versions**, không tự thêm tất cả thư viện trong BOM vào runtime.

Nâng BOM `2.4.0 -> 2.5.0` có thể đổi hàng chục transitive/selected versions. Quy trình hợp lý:

1. Xem release notes và danh sách managed versions cũ/mới.
2. Xác định modules thực sự dùng những artifacts bị đổi.
3. So effective POM trước và sau.
4. So selected dependency tree ở module đại diện; kiểm tra scopes.
5. Chạy API/contract/integration tests ở những modules chịu tác động.
6. Chỉ hợp nhất khi các đổi khác được chấp thuận; nếu diện thay đổi quá rộng, chia rollout.

**Số dòng Git diff không đo độ rủi ro version change**. Một BOM version mới có thể mạnh hơn việc sửa nhiều dependencies riêng lẻ.

## 15. Plugin upgrade khác dependency upgrade

Khi bạn nâng `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-shade-plugin` hoặc `maven-assembly-plugin`, bạn thay công cụ thực thi build. Điều này có thể làm đổi:

- Compiler options, Java target, annotation processing.
- Test discovery, JUnit provider, forked JVM và report files.
- Resource processing, manifest hoặc ServiceLoader metadata.
- Packaging, artifact classifiers và generated POM.
- Maven/JDK version prerequisites.

Vì vậy đừng thêm một plugin upgrade vào PR nâng Commons Lang chỉ vì thấy `display-plugin-updates` báo version mới. Đặt một thay đổi riêng, pin plugin version và chạy đúng lifecycle, kể cả `verify` và artifact smoke tests.

### Enforcer để nhận diện xung đột

Maven Enforcer có những rule như **`requireMavenVersion`**, **`requireJavaVersion`**, **`dependencyConvergence`** và **`requireUpperBoundDeps`**.

- `dependencyConvergence`: kiểm tra các đường dependency không dùng version xung đột của cùng artifact theo cấu hình.
- `requireUpperBoundDeps`: kiểm tra resolved version không thấp hơn versions được yêu cầu theo các đường dependency.

Hai rule có ngữ nghĩa khác nhau. Chúng **không bảo đảm mọi thay đổi API/ABI tương thích**; cần đọc lỗi và kiểm thử thực tế, không tạo exclusions quá rộng để im lặng mọi cảnh báo.

## 16. Effective POM và dependency tree: hai góc nhìn bổ sung

Maven tạo effective model từ child POM, parent chain, dependencyManagement/BOM, pluginManagement, properties và profiles.

Xuất effective POM:

~~~bash
mvn -B -ntp -pl :app help:effective-pom -Doutput=effective-app.xml
~~~

Đọc riêng những vùng:

~~~text
project/version
project/parent/version
project/properties
project/dependencyManagement/dependencies
project/dependencies
project/build/plugins
project/build/pluginManagement
~~~

**Đừng tìm thấy chuỗi `commons-lang3` ở bất kỳ vị trí nào rồi kết luận app runtime có Commons Lang.** Chuỗi có thể chỉ nằm trong managed catalog.

Đánh giá property trong project demo:

~~~bash
mvn -q -pl :app help:evaluate -Dexpression=commons-lang3.version -DforceStdout
~~~

Trước đổi:

~~~text
3.14.0
~~~

Sau đổi property:

~~~text
3.16.0
~~~

Các stdout trên là dự kiến của **property được cấu hình trong demo** khi Help Plugin chạy thành công. File `effective-app.xml` là output quan sát, không phải POM nguồn để chỉnh sửa/commit.

### Dependency mediation

Ví dụ graph:

~~~text
app
  |-- lib-a --> lib-c:1.4
  |-- lib-b --> lib-c:2.0
~~~

Đây là **đồ thị minh họa**. Maven có rules như nearest definition và dependencyManagement để chọn version theo effective model. Nâng `lib-b` không tự bảo đảm `lib-c:2.0` được runtime chọn. Phải xem **resolved tree** và kiểm tra graph sau build.

## 17. Parent, project, child: những lỗi đồng bộ version đặc trưng

Nếu chỉ sửa root:

~~~xml
<version>1.1.0-SNAPSHOT</version>
~~~

nhưng giữ child:

~~~xml
<parent>
    <groupId>vn.example.versions</groupId>
    <artifactId>version-control-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

child có thể không resolve đúng parent local hoặc dùng parent cũ từ repository. Đó là lý do `versions:set` hữu ích trong reactor có **shared project version**.

Nhưng `versions:set` không tự sửa mọi script CI, Docker tag, documentation, version trong file JSON, Helm chart hoặc external consumer references. Sau chỉnh POM, rà **đúng các nơi sử dụng GAV của sản phẩm** theo phạm vi được phép; đừng chạy tìm-thay toàn bộ version string không có ngữ cảnh.

Nếu module releases độc lập hoặc một parent được publish trước children, cần kế hoạch migration theo artifact, không ép mọi module dùng một version.

## 18. `versions:commit`, `versions:revert` và Git khác nhau

Khi goals chỉnh POM với `generateBackupPoms=true`, Versions Plugin thường tạo file:

~~~text
pom.xml.versionsBackup
~~~

Trong reactor có thể có nhiều backup, tương ứng những POM được sửa.

- **`versions:commit`** loại bỏ backup do plugin tạo. Nó **không làm Git commit**, không review, không test và không deploy.
- **`versions:revert`** khôi phục POM từ backup còn lại. Nó **có thể ghi đè những chỉnh sửa hợp lệ được thực hiện sau lúc tạo backup**.
- **Git revert/restore** hoạt động theo Git state và cần chọn đúng paths/commit. Không dùng lệnh hủy toàn bộ workspace chỉ để rollback một version change.

Câu lệnh khi **chủ đích chấp nhận changes ở mức plugin backup**:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:commit
~~~

Câu lệnh khi **chủ đích trả về POM backup và chắc chắn không làm mất edits mới**:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:revert
~~~

Một quy trình an toàn là: chạy một goal thay version; xem `git diff`; chạy `mvn clean verify`; nếu đúng thì quản lý backups và mở PR; nếu sai thì rollback đúng changes của goal, không đụng vào những chỉnh sửa khác.

`-DgenerateBackupPoms=false` có thể giảm file backup, nhưng chỉ phù hợp khi đã có Git/backup thay thế đáng tin. Với người mới nên giữ backups rồi dọn chúng có chủ đích sau review.

## 19. CI-friendly versions: trường hợp `${revision}`

Apache Maven hỗ trợ placeholder version đặc biệt như:

~~~text
${revision}
${sha1}
${changelist}
~~~

Một cách thiết kế **thay thế** cho root POM, không áp dụng đồng thời với POM runnable trên:

~~~xml
<version>${revision}</version>
<properties>
    <revision>1.1.0-SNAPSHOT</revision>
</properties>
~~~

Có thể điều khiển từ CLI:

~~~bash
mvn -Drevision=1.1.0-SNAPSHOT clean verify
~~~

Cần lưu ý:

1. Không dùng một property bất kỳ như `${customVersion}` thay `project/version` rồi mặc định Maven hiểu như `${revision}`.
2. Trong multi-module, Maven hướng dẫn dùng `${project.version}` khi tham chiếu sibling dependency version trong những tình huống phù hợp.
3. Với Maven 3 CI-friendly POM khi `install/deploy`, cần nghiên cứu **Flatten Maven Plugin** để POM đã publish không còn unresolved placeholders khiến consumers không resolve được.
4. `versions:set` có semantics riêng với literal versions; đừng dùng nó trên `${revision}` mà chưa thử scope và effective model.
5. Chiến lược versioning tốt cần thống nhất giữa local, CI, artifact publication và consumers.

POM chính của bài cố tình dùng **literal `1.0.0-SNAPSHOT`** và property riêng cho Commons Lang để phân biệt rõ hai cơ chế.

## 20. SNAPSHOT, release và điều kiện publish

Đổi từ `1.0.0-SNAPSHOT` sang `1.0.0` trên POM chỉ đổi version string; nó **không tự tạo một release hoàn chỉnh**.

Một bản release phải kiểm tra:

- Project/parent/child versions và dependency nội bộ nhất quán.
- Các external dependencies/plugins không dùng SNAPSHOT trái chính sách.
- Build trên JDK/Maven đúng, tests và integration checks pass.
- Artifact JAR/WAR và generated POM mang GAV/metadata chính xác.
- SCM commit/tag trỏ tới source được build.
- License, SBOM, artifact signing, checksum/provenance nếu được yêu cầu.
- Remote repository, credentials, release approvals và rollback đều được kiểm soát.

**`mvn deploy` là hành động ghi remote repository**, không phải lệnh test vô hại. Ví dụ học tập chỉ cần `verify` hoặc `install` local khi có chủ đích, không tự publish.

## 21. Quy trình thay đổi version từ đầu tới cuối

~~~text
1. Chọn mục tiêu và approved target version
2. Chụp baseline: Git state, Maven/JDK, effective POM, dependency tree
3. Đọc release notes + minimum Java/Maven requirements
4. Tạo branch/worktree và xác định files được phép sửa
5. Thực hiện đúng một goal sửa POM hoặc edit thủ công
6. Đọc diff: file nào, property/version nào thay đổi?
7. Chạy Maven invocation mới: clean verify
8. Kiểm tra effective model và selected dependency graph
9. Smoke/integration test artifact phát hành nếu bị ảnh hưởng
10. Xem security/license/policy và quality gates
11. Review, merge/tag/publish theo quy trình được phê duyệt
12. Có thể rollback riêng version change và biết bằng chứng đã kiểm thử
~~~

Không nên thực hiện hàng loạt updates khi CI đỏ do nguyên nhân chưa được hiểu. Hãy xác định root cause trước: thiếu artifact, sai parent resolution, JDK quá cũ, classpath xung đột hay behavior library đổi.

## 22. Ma trận kiểm chứng theo loại version change

| Kiểm chứng | Project version | Parent version | Dependency version |
| --- | --- | --- | --- |
| Git diff POM | **Bắt buộc** | **Bắt buộc** | **Bắt buộc** |
| Child parent/internal references | **Rất quan trọng** | Khi parent là internal | Khi sibling dependency bị đổi |
| Effective POM | Có | **Rất quan trọng** | **Rất quan trọng** |
| Dependency tree | Nếu graph đổi | **Rất quan trọng** | **Bắt buộc** |
| Plugin/JDK prerequisites | Có thể | **Bắt buộc** | Theo release requirements |
| Unit tests | Có | Có | **Bắt buộc** |
| Integration/contract tests | Theo release policy | Theo phạm vi inherited changes | Theo bề mặt API/ABI |
| Artifact/version metadata | **Bắt buộc** | Khi packaging/plugin đổi | Khi runtime deps đổi |
| Security/license review | Theo policy | Theo inherited deps/plugins | Theo dependency mới |
| Rollback plan | **Bắt buộc** | **Bắt buộc** | **Bắt buộc** |

Độ sâu kiểm thử còn tùy sản phẩm. Một unit test cho method `StringUtils.upperCase` không bao phủ các đường reflection, serialization, network integration hoặc service loaders khác của app thật.

## 23. Những lỗi phổ biến sau khi nâng version

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `Non-resolvable parent POM` | Parent GAV không tồn tại, repository sai hoặc `relativePath` không khớp. | Đọc `<parent>`, repository settings và parent artifact. |
| `dependencies.dependency.version is missing` | Dependency thật không có version/direct management. | Đọc effective dependencyManagement và dependency identity. |
| Child vẫn dùng version cũ | Root được sửa nhưng child `<parent><version>` chưa đồng bộ. | `versions:set` đúng reactor, đọc diff mọi child POM. |
| App vẫn resolve Commons Lang cũ | Sửa property không được tham chiếu, child/profile override. | `help:evaluate`, effective POM, dependency tree. |
| `dependency:tree` chưa resolve core | Chạy goal riêng khi sibling artifact chưa cài/resolved. | Build/install sandbox hoặc chạy reactor goals phù hợp. |
| Unit tests pass nhưng runtime `NoSuchMethodError` | Runtime classpath khác test classpath, binary incompatibility. | Kiểm tra packaged JARs, dependency graph, integration tests. |
| `UnsupportedClassVersionError` | New dependency cần Java cao hơn runtime. | Kiểm tra minimum Java, bytecode/JVM target và policy. |
| `versions:update-parent` nhảy major ngoài dự kiến | Không giới hạn parentVersion range. | Chọn version chính xác hoặc range phê duyệt, rollback. |
| Enforcer dependency convergence fail | Các đường transitive có versions khác nhau. | Phân tích từng đường dependency, không tắt rule bừa. |
| Test discovery thay đổi sau nâng parent | Surefire/JUnit/plugin inherited versions/config đổi. | So effective plugin config và surefire-reports. |
| `versions:revert` xóa edits mới | POM có thay đổi sau khi backup được tạo. | Không revert mù; rollback đúng patch có owner rõ. |
| `versions:commit` nhưng Git chưa có commit | Nhầm commit backup với Git commit. | Kiểm tra `git status`, review, tạo Git commit riêng. |
| JAR filename/upload sai version | CI script hardcode tên cũ; package metadata chưa kiểm. | Kiểm tra artifact GAV/classifier và publish selection. |
| BOM chỉ đổi một dòng nhưng nhiều modules fail | BOM kéo nhiều managed versions mới. | So trước/sau effective POM + dependency tree từng module. |
| Build local pass, CI fail | Local `.m2` có artifact khác, JDK/version khác hoặc profile khác. | Xác minh `mvn --version`, repository, CI profile/cache. |

**Không kết luận “Versions Plugin bị lỗi” chỉ vì build không chạy sau khi version tăng.** Goal sửa POM có thể làm đúng việc của nó nhưng mục tiêu version không tương thích. Tách lỗi chỉnh text/version khỏi lỗi dependency resolution và lỗi runtime.

## 24. Bài tập A — nâng đồng bộ project version

1. Tạo ba POM và bốn class Java như mục 6.
2. Chạy baseline `mvn -B -ntp clean verify`.
3. Chạy `versions:set` với `1.1.0-SNAPSHOT` trong một branch thử nghiệm.
4. So `git diff` root và hai child POM.
5. Đọc parent reference ở mỗi child, project version và dependency nội bộ trong effective POM app.
6. Chạy lại `mvn clean verify`.
7. Tìm những chỗ ngoài POM có tên artifact/version hardcode (nếu có) mà plugin không cập nhật.
8. Thực hành rollback chỉ patch thay version, không xóa source edits khác.

**Câu hỏi:** tại sao chỉ sửa root version không đủ nếu child vẫn có `<parent><version>1.0.0-SNAPSHOT</version></parent>`?

## 25. Bài tập B — nâng một dependency qua property

1. Trở về baseline riêng (không trộn với bài project version).
2. Chọn Commons Lang `3.16.0` sau khi xem thay đổi so với `3.14.0`.
3. Dùng `versions:set-property` để đổi đúng `commons-lang3.version`.
4. Kiểm tra `junit.version`, project version và plugin versions không đổi.
5. Chạy `mvn clean verify`.
6. Dùng `help:evaluate` xác nhận property.
7. Dùng `dependency:tree` xác nhận **selected** Commons Lang version ở app.
8. Có thể chạy `App.main` trong sandbox và đối chiếu **APP: CORE READY**.
9. Ghi lại những API/integration paths của ứng dụng thật chưa được unit test bao phủ.

**Câu hỏi:** vì sao dependencyManagement chứa Commons Lang nhưng một child không khai báo Commons Lang sẽ không tự có nó trên classpath?

## 26. Bài tập C — nâng external parent có giới hạn

Một dự án giả định dùng `vn.example.build:team-parent:2.4.0`, và mục tiêu được duyệt là 2.5.x:

1. Xác minh parent artifact thật tồn tại trong repository tin cậy.
2. Chọn nâng đúng `2.5.0` bằng sửa thủ công, hoặc dùng Versions Plugin với range `[2.5.0,2.6.0)` nếu chính sách cho phép mọi patch trong dải.
3. Đọc Git diff, không nâng các project dependencies không liên quan.
4. So effective POM trước/sau để tìm inherited plugin/dependency changes.
5. Chạy full lifecycle và integration/smoke tests cần thiết.
6. Kiểm tra minimum JDK/Maven requirements.
7. Review với chủ sở hữu build platform và ghi rollback plan.
8. Không sử dụng `update-parent` không giới hạn hoặc `skipResolution=true` chỉ để đạt một version nhìn có vẻ mới.

**Câu hỏi:** vì sao một dòng parent version trong Git diff có thể tạo hàng chục thay đổi build/selected dependency versions?

## 27. Checklist trước khi hợp nhất một version-upgrade PR

1. Target version được phê duyệt và tìm được từ repository đáng tin.
2. Phân biệt rõ project, parent, dependency, BOM và build plugin.
3. Không sửa ngoài phạm vi đã thống nhất.
4. Child parent versions và sibling dependency references khớp khi có shared project version.
5. Không nhầm `dependencyManagement` với actual dependencies.
6. Đúng property nguồn quản lý version của thư viện được nâng.
7. Effective POM xác nhận inherited configuration mong muốn.
8. Dependency tree xác nhận resolved version và transitive graph hợp lý.
9. Maven/JDK prerequisites vẫn đáp ứng.
10. Unit/integration/artifact smoke tests đúng phạm vi pass.
11. Git diff không có chỉnh sửa POM ngẫu nhiên hoặc backup rác.
12. Rollback không làm mất thay đổi không thuộc nhiệm vụ.
13. `versions:commit` không bị nhầm với Git commit.
14. Không tự động nâng `latest`/major ngoài chính sách.
15. SNAPSHOT/release coordinates đúng môi trường đích.
16. Security/license/compatibility được đánh giá theo policy.
17. Release scripts, artifact names, SCM tags và CI config được kiểm tra.
18. Không publish trước khi có review và kết quả kiểm chứng.
19. Tài liệu nâng cấp ghi rõ trước/sau, phạm vi, tests và điểm chưa kiểm chứng.
20. Có thể tái lập build từ một checkout mới với Maven/JDK được ghi lại.

### Kết luận

**Cập nhật version Maven có kiểm soát không phải một thao tác thay chuỗi duy nhất.** Với project version nên dùng `versions:set` và xác nhận parent/child/internal references; với external parent nên chọn version chính xác hoặc dải giới hạn rồi kiểm tra effective POM; với dependency qua property nên dùng `versions:set-property`; với dependency literal có thể sửa trực tiếp hoặc dùng `versions:use-dep-version` cho artifact được chọn.

Các goal `display-*` giúp tìm candidates nhưng **không tự quyết định compatibility**. Sau mỗi sửa POM, hãy **đọc Git diff, build ở Maven invocation mới, kiểm tra effective POM/dependency tree, chạy tests và có rollback**. Parent/BOM có thể tạo tác động lan rộng; plugin version có thể đổi hành vi build; dependency version có thể đổi API hoặc minimum runtime. Publish chỉ khi những tác động này được kiểm chứng và phê duyệt.

### Tài liệu chính thức và tham khảo

- [MojoHaus Versions Maven Plugin — Overview](https://www.mojohaus.org/versions/versions-maven-plugin/)
- [MojoHaus Versions Plugin — versions:set](https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html)
- [MojoHaus Versions Plugin — versions:set-property](https://www.mojohaus.org/versions/versions-maven-plugin/set-property-mojo.html)
- [MojoHaus Versions Plugin — versions:update-parent](https://www.mojohaus.org/versions/versions-maven-plugin/update-parent-mojo.html)
- [MojoHaus Versions Plugin — versions:use-dep-version](https://www.mojohaus.org/versions/versions-maven-plugin/use-dep-version-mojo.html)
- [MojoHaus Versions Plugin — Update Parent Example](https://www.mojohaus.org/versions/versions-maven-plugin/examples/update-parent.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — CI-friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Enforcer Rules](https://maven.apache.org/enforcer/enforcer-rules/)
- [Maven Central — Commons Lang 3.16.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.16.0)

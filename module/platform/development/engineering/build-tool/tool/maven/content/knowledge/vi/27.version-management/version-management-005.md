# Rà soát tệp POM sau khi công cụ thay đổi phiên bản trong Maven

## 1. Vì sao phải rà soát POM dù công cụ báo thành công?

Một lần chạy Maven Versions Plugin, Maven Release Plugin, công cụ nâng cấp dependency (Dependabot, Renovate), IDE refactoring hoặc một script CI có thể sửa một hay nhiều tệp `pom.xml`. Công cụ có thể **thành công về mặt ghi file** nhưng vẫn để lại cấu hình không phù hợp với ý định phát hành:

- Parent POM đã nâng lên `1.3.0-SNAPSHOT` nhưng POM con vẫn trỏ `1.2.0-SNAPSHOT`.
- Một dependency nội bộ dùng phiên bản khác với module hiện có trong Reactor.
- Plugin compiler/test/build bị nâng version mà CI JDK hoặc Maven runtime chưa hỗ trợ.
- Version property dùng chung thay đổi khiến nhiều dependency cùng được nâng ngoài dự kiến.
- BOM được nâng, làm các phiên bản dependency **được quản lý gián tiếp** thay đổi dù không thấy version trong từng `<dependency>`.
- Một lệnh release chỉnh thêm `<scm><tag>`, commit/tag Git hoặc chuyển sang phiên bản phát triển tiếp theo.
- Công cụ format lại XML quá nhiều, che mất những thay đổi quan trọng.
- Các bản backup `pom.xml.versionsBackup` tồn tại sau khi đổi version.
- Dự án compile thành công trên máy local nhờ cache cũ, nhưng build mới từ source thất bại trong CI.

Bài Knowledge thuộc chủ đề **Quản lý phiên bản**. Trọng tâm không phải “làm thế nào tìm bản mới nhất bằng mọi giá”, mà là **xác minh thay đổi POM do công cụ thực hiện đúng phạm vi, đúng tọa độ và không làm hỏng hợp đồng build**.

Sau bài này, bạn có thể:

1. Nhận diện các phần của POM chịu tác động bởi phiên bản project, parent, dependency, plugin, property, BOM và SCM.
2. Rà soát thay đổi bằng `git status`, `git diff`, `git diff --check` và phân biệt tracked/untracked files.
3. Hiểu cơ chế backup, `versions:revert` và `versions:commit` của Versions Maven Plugin.
4. Đối chiếu parent, modules và dependency nội bộ trong Reactor sau khi tăng phiên bản.
5. Kiểm tra `dependencyManagement`, `pluginManagement`, imported BOM, profiles và build extensions.
6. Xác nhận Maven model hợp lệ bằng `validate`, `help:effective-pom`, `help:evaluate`, `dependency:tree` và build/test.
7. Thực hành Java 17 với root aggregator và hai modules `core`/`app`; thay version từ `1.2.0-SNAPSHOT` sang `1.3.0-SNAPSHOT` rồi rà soát.
8. Nhận biết thay đổi đặc biệt từ Maven Release Plugin để không nhầm một lượt version bump thông thường với hoạt động tag/commit release.
9. Viết checklist QA cho pull request hoặc CI có cập nhật phiên bản tự động.

Ví dụ dùng Maven 3.x, Java 17 và Maven Versions Plugin `2.21.0`. Plugin version được ghi tường minh để tái hiện, không phải yêu cầu dự án thật phải dùng phiên bản đó; hãy kiểm tra release notes và tương thích với môi trường sử dụng.

## 2. Bắt đầu bằng việc xác định công cụ nào đã sửa POM

Không phải mọi công cụ versioning có cùng phạm vi hay tác dụng phụ:

| Công cụ / thao tác | Thay đổi có thể gặp | Lưu ý khi rà soát |
| --- | --- | --- |
| `versions:set` | `<project><version>` và references phù hợp trong các modules liên quan. | Kiểm tra parent/child/dependency versions, backups và lựa chọn module. |
| `versions:update-parent` | `<parent><version>`. | Kiểm tra parent mới tồn tại, child model và các thay đổi kế thừa. |
| `versions:update-properties` | Các property phiên bản được liên kết với artifacts. | Một property có thể dùng ở nhiều chỗ, gây thay đổi rộng. |
| `versions:use-next-releases` / `use-latest-releases` | Dependency versions cụ thể. | “Next” và “latest” có thể khác, phải kiểm tra tương thích. |
| `versions:update-child-modules` | Cố sửa parent reference sai trong child POMs. | Không phải giải pháp cho mọi lỗi dependency/parent. |
| Maven Release Plugin `release:prepare` | Release/development version, SCM metadata, Git commits/tags. | Có tác dụng lên SCM, không chỉ sửa XML. |
| Dependabot/Renovate | Dependency/plugin/BOM/property version bumps trong PR. | Xem release notes, policies, lock/integration impacts. |
| IDE refactoring hoặc script CI | Các thẻ version, property và đôi khi formatting/XML khác. | Đối chiếu mọi dòng thay đổi thay vì tin vào tên công cụ. |

**Quy tắc làm việc:** trước khi chấp nhận, biết **command thật**, **plugin/tool version**, **working directory**, **root aggregator**, **những tệp đã sửa** và **phiên bản đích mong muốn**.

Ví dụ lệnh:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:set -DnewVersion=1.3.0-SNAPSHOT
~~~

Đây là một **goal có thể sửa POM**. Khác với lệnh kiểm tra chỉ đọc:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Lệnh thứ hai không có mục tiêu sửa tệp POM nguồn nhưng có thể tạo file output; cần đặt các báo cáo sinh ra ở nơi phù hợp và không đưa nhầm vào commit.

## 3. Những nơi chứa version trong POM

Một POM không có duy nhất một `<version>`. Với ví dụ rút gọn:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>2.1.0</version>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>billing-service</artifactId>
    <version>1.2.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <junit.version>5.11.4</junit.version>
        <jackson.version>2.17.2</jackson.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>${jackson.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM fragment để giải thích, không phải toàn bộ POM runnable**: chưa có namespace/XSD đầy đủ và không khai báo các source files. Những vị trí cần phân biệt:

- `/project/version`: phiên bản của project hiện tại, nếu không kế thừa từ parent.
- `/project/parent/version`: phiên bản **parent project**, không tự trùng project version.
- `/project/dependencies/dependency/version`: version dependency khai báo trực tiếp.
- `/project/dependencyManagement/dependencies/dependency/version`: version được quản lý; có thể thay đổi hiệu lực dù chỗ sử dụng bỏ trống `<version>`.
- `/project/build/plugins/plugin/version`: version plugin build được thực thi.
- `/project/build/pluginManagement/plugins/plugin/version`: version quản lý cho plugins.
- `/project/properties/*`: property có thể được tham chiếu ở nhiều chỗ, kể cả plugins/BOMs.
- `/project/profiles/profile/...`: cấu hình chỉ kích hoạt trong một số môi trường; bỏ sót profile là lỗi review thường gặp.
- `/project/reporting/plugins/...`: reporting plugin versions, nếu dự án có cấu hình reporting.

Một công cụ sửa `<version>` ở vị trí A không nhất thiết sửa `<version>` ở B. Điều gì được xử lý phụ thuộc goal, arguments và cách các thẻ đã được khai báo.

### Đọc XML theo quan hệ cha–con, không theo chuỗi text

Nếu có:

~~~xml
<parent>
    <version>2.1.0</version>
</parent>
<version>1.2.0-SNAPSHOT</version>
~~~

thì đổi `parent.version` thành `2.2.0` không tự có nghĩa project đổi version. Tương tự thay `junit.version` không đổi `project.version`.

**Đừng dùng find-and-replace toàn bộ chuỗi `1.2.0` không có ngữ cảnh XML**; có thể vô tình đổi phần mô tả, plugin version, BOM hoặc đường dẫn không liên quan.

## 4. Quy trình rà soát trước–sau bằng Git

Nếu project được quản lý bằng Git, trước khi chạy công cụ sửa version nên có baseline rõ ràng.

### 4.1. Kiểm tra trạng thái trước khi chỉnh

~~~bash
git status --short
git diff --check
git diff -- pom.xml
~~~

Lý tưởng là không có thay đổi không liên quan. Nếu working tree đã bẩn, **không bỏ qua các thay đổi hiện có**: cần tách commit/branch hoặc ghi lại baseline để không gán nhầm mọi khác biệt cho công cụ.

Một cách làm an toàn trên nhánh riêng:

~~~bash
git switch -c chore/review-maven-version
~~~

Lệnh trên chỉ dùng khi tên nhánh chưa tồn tại và bạn có quyền tạo nhánh. **Không bắt buộc** dùng đúng tên; cũng không chạy nó trên nhánh phát hành nếu chính sách team không cho phép.

### 4.2. Chạy công cụ sửa version một lần

Ví dụ (chỉ trên project demo hoặc branch đã chuẩn bị):

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:set -DnewVersion=1.3.0-SNAPSHOT
~~~

Sau đó:

~~~bash
git status --short
git diff --stat
git diff --check
git diff -- pom.xml core/pom.xml app/pom.xml
~~~

Nếu công cụ sửa nhiều files, `git diff --stat` cho biết quy mô trước khi đọc chi tiết. `git diff --check` phát hiện một số lỗi whitespace như trailing whitespace, nhưng **không kiểm tra XML/POM hợp lệ**.

### 4.3. Đọc diff theo ý định

Khi mục tiêu chỉ đổi project version từ `1.2.0-SNAPSHOT` sang `1.3.0-SNAPSHOT`, các thay đổi có thể hợp lý gồm:

~~~diff
-    <version>1.2.0-SNAPSHOT</version>
+    <version>1.3.0-SNAPSHOT</version>
~~~

trong root POM; các child POM thường cần cập nhật parent reference:

~~~diff
     <parent>
         <groupId>dev.example</groupId>
         <artifactId>pom-review-demo</artifactId>
-        <version>1.2.0-SNAPSHOT</version>
+        <version>1.3.0-SNAPSHOT</version>
     </parent>
~~~

Nếu thấy cả `junit.version` tăng, plugin version đổi, SCM URL thay hoặc hàng trăm dòng formatting thay đổi, cần hỏi **công cụ có thật sự được phép đụng các phần đó không?** Đừng coi mọi diff do automation là hợp lệ.

### 4.4. Phân biệt tracked và untracked files

Lệnh `git diff` mặc định so những thay đổi **chưa stage của tracked files**. Nó không cho bạn thấy nội dung của mọi **untracked backup** hoặc file do plugin mới tạo.

Hãy dùng:

~~~bash
git status --short
git ls-files --modified
~~~

Nếu đã stage changes, so thêm:

~~~bash
git diff --cached -- pom.xml core/pom.xml app/pom.xml
~~~

Không chỉ đọc `git diff` trong khi mọi thay đổi đã được stage: kết quả có thể rỗng dù POM đã khác `HEAD`.

### 4.5. Nhìn tổng mọi thay đổi so với commit nền

Khi cần rà soát phần đã stage lẫn chưa stage:

~~~bash
git diff HEAD -- pom.xml core/pom.xml app/pom.xml
~~~

Lệnh này giả định repo có commit `HEAD` hợp lệ. Nếu repo mới `git init` mà chưa commit, cần tạo baseline phù hợp trước; đừng dùng một lệnh tự động xóa file để “dọn” workspace.

**Nguyên tắc reviewer:** cần biết chính xác tệp nào đổi, đoạn nào đổi, vì sao đổi, và sự khác biệt đó được xác minh bằng cách nào.

## 5. Dùng Maven Versions Plugin có kiểm soát

Versions Maven Plugin thuộc group `org.codehaus.mojo`. Trong ví dụ, ta gọi goal bằng tọa độ plugin đầy đủ:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:set -DnewVersion=1.3.0-SNAPSHOT
~~~

Cú pháp này làm rõ chính xác plugin version, tránh phụ thuộc việc Maven plugin prefix `versions` đang resolve ra phiên bản nào.

### `versions:set` tác động đến gì?

Goal `set` được thiết kế để đổi version của project hiện tại và truyền thay đổi đến những child modules liên quan theo cấu hình. Những tham số cần biết:

| Tham số | Ý nghĩa |
| --- | --- |
| `newVersion` | Version mới muốn đặt, ví dụ `1.3.0-SNAPSHOT`. |
| `generateBackupPoms` | Có tạo backup POM trước thay đổi hay không; mặc định `true` của goal trong plugin 2.21.0. |
| `processAllModules` | Xử lý mọi module trong phạm vi thay vì chỉ các module khớp tọa độ chọn ban đầu; dùng thận trọng trong reactor có version độc lập. |
| `updateMatchingVersions` | Có cập nhật các version khai báo tường minh trùng điều kiện trong child modules; mặc định `true` theo goal docs. |
| `processParent` | Có xét parent references khi cập nhật hay không. |
| `processDependencies` | Có xét các dependency references liên quan không. |
| `processFromLocalAggregationRoot` | Có bắt đầu từ local aggregator root phù hợp hay không. |

Không hiểu `processAllModules=true` là “luôn an toàn và luôn cần”: trong repository có các modules phiên bản riêng, thay hàng loạt có thể đi ngược release policy. Nếu chỉ một module được version riêng, hãy xác minh selection, aggregation và commit diff thay vì áp một cờ rộng.

### `versions:update-properties` không giống `versions:set`

Goal `update-properties` tìm version cập nhật cho những property được liên kết với artifacts và có thể sửa nhiều thuộc tính cùng lúc. Ví dụ:

~~~xml
<properties>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

nếu property này được tham chiếu trong test dependency, tool có thể đề xuất/ghi phiên bản mới theo metadata và rules. Nhưng **không khẳng định đầu ra là một version cụ thể**: nó phụ thuộc repository metadata, excludes, version rules, snapshots và thời điểm chạy.

Sau lệnh nâng properties, phải đọc lại **mọi chỗ sử dụng `${junit.version}`**, không chỉ một dòng trong root POM. Một property dùng bởi nhiều dependency/plugin có thể làm thay đổi nhiều đường đi của build.

### `versions:update-parent` không tự đảm bảo parent mới tương thích

Nếu tool đổi parent:

~~~diff
 <parent>
     <groupId>dev.example</groupId>
     <artifactId>company-parent</artifactId>
-    <version>2.1.0</version>
+    <version>2.2.0</version>
 </parent>
~~~

bạn cần so:

- Parent POM 2.2.0 có resolve được qua `relativePath`/repositories không?
- Có thay `dependencyManagement`, pluginManagement, enforcer rules hoặc active profiles không?
- Có đổi Java release, Surefire/JUnit provider, packaging plugins không?
- Parent mới có điều kiện Maven/JDK cao hơn không?
- Có thay repositories, distributionManagement hoặc nguồn credentials không?

Rà soát **effective POM sau update** mới cho biết nhiều cấu hình được kế thừa mà child POM không hiển thị trực tiếp.

### `versions:use-next-releases` và `use-latest-releases`

“Next” là phiên bản release tăng tiếp theo theo chính sách so sánh; “latest” là phiên bản release cao nhất được chọn theo metadata/rules. Những tên này **không bảo đảm compatibility theo semantic versioning**, đặc biệt với thư viện không tuân thủ SemVer hoặc có major breaking change.

Không chạy tự động goal nâng latest releases trên toàn bộ build production mà không có review: compiler API, plugin parameters, test provider, JDK hoặc runtime classpath có thể thay đổi.

### Khi nào dùng `versions:update-child-modules`?

Một trường hợp đặc biệt: root aggregator đồng thời là parent ở version mới, nhưng child POM `<parent><version>` vẫn trỏ bản cũ khiến Maven không thể tạo model. Versions Plugin cung cấp `update-child-modules` để hỗ trợ sửa loại inconsistency này.

Tuy nhiên nó **không thay thế review**: công cụ không thể biết một child module được cố ý giữ parent version khác, hoặc child là một project release độc lập. Trước khi chạy, so POM root với mọi child và xác nhận quan hệ parent chính xác.

## 6. Backup POM, `versions:revert` và `versions:commit`

Theo tài liệu Versions Maven Plugin 2.21.0:

- `generateBackupPoms=true` (mặc định của `versions:set`) có thể tạo các file dạng `pom.xml.versionsBackup` ở những POM đã được sửa.
- `versions:revert` khôi phục POM từ **bản backup ban đầu** còn tồn tại.
- `versions:commit` **loại bỏ backup POM**, về bản chất chấp nhận thay đổi ở tầng plugin.
- **`versions:commit` KHÔNG phải `git commit`**. POM mới vẫn có thể là thay đổi chưa commit trong Git.

### Luồng an toàn khi dùng backup

~~~text
POM phiên bản 1.2.0-SNAPSHOT
              │
              ▼
       versions:set
              │
              ├── pom.xml mới: 1.3.0-SNAPSHOT
              └── pom.xml.versionsBackup giữ bản ban đầu
                       │
           Rà soát diff + build/test
                       │
             ┌─────────┴────────┐
             ▼                  ▼
      Chấp nhận              Hoàn tác
      versions:commit        versions:revert
      xóa backup             khôi phục backup
             │                  │
      Git review/commit      Git status/diff
~~~

Cú pháp goal tường minh:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:commit
~~~

và:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:revert
~~~

**Hai lệnh trên là lựa chọn thay thế tùy kết quả QA, không chạy liên tiếp “cho chắc”.** Nếu đã commit backups rồi, `revert` không còn bản backup ban đầu để phục hồi. Nếu `generateBackupPoms=false`, bạn cũng không nên chờ `versions:revert` khôi phục một backup không tồn tại.

### Backup không phải hệ thống version control

Backup POM hữu ích cho một lượt Versions Plugin, nhưng không thay thế:

- Git commit/branch và lịch sử thay đổi.
- Pull request reviews.
- CI build/test results.
- Changelog/release notes.
- Trạng thái release tag nếu đã dùng Maven Release Plugin.

Đừng thêm tất cả `*.versionsBackup` vào Git commit. Trước khi xóa chúng, xác nhận chúng thuộc **lần thao tác hiện tại** và không phải backup quan trọng từ lượt thay đổi trước; nên dùng `versions:commit`/`revert` đúng ngữ cảnh.

### Nếu POM đã bị sửa tay sau khi Versions Plugin tạo backup

`versions:revert` khôi phục bản backup, nên có nguy cơ **ghi đè những chỉnh sửa tiếp theo** trong các POM liên quan. Đừng chạy revert mù nếu đã có thay đổi tay quan trọng. Dùng `git diff` trước, lưu/tách những thay đổi cần giữ và quyết định phương án khôi phục có kiểm soát.

Tương tự, tránh dùng `git reset --hard` hoặc lệnh xóa toàn bộ untracked files chỉ để hoàn tác một version bump: chúng có thể hủy công việc không liên quan trong workspace.

## 7. Dự án Java 17 thực hành với parent và hai modules

Ta tạo một dự án Maven ba POM:

~~~text
pom-review-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/demo/core/Greeting.java
│       └── test/java/demo/core/GreetingTest.java
└── app/
    ├── pom.xml
    └── src/main/java/demo/app/Main.java
~~~

Vai trò:

- Root `pom.xml`: vừa **aggregator** (có `<modules>`), vừa **parent** để thống nhất groupId/version và pluginManagement.
- `core`: Java library trả về lời chào, có JUnit Jupiter tests.
- `app`: Java application phụ thuộc `core` đang được build trong Reactor.
- Cả hai child POM có parent version bắt đầu là `1.2.0-SNAPSHOT`.
- `app` dùng version `${project.version}` cho dependency `core`; sau bump, expression này tự resolve theo project version mới nếu quan hệ POM đúng.

### 7.1. Root `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>pom-review-demo</artifactId>
    <version>1.2.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

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
                    <version>3.5.4</version>
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

Lưu ý:

- Root packaging `pom`, không tạo application JAR từ chính root.
- `<modules>` trỏ thư mục `core` và `app`.
- Plugin versions có ở `pluginManagement`. Các goals từ lifecycle của `jar` modules có thể sử dụng phiên bản quản lý này.
- Parent cung cấp `junit.version` nhưng chỉ child nào khai báo JUnit dependency thì mới có nó trên test classpath.
- XML namespace/XSD dùng Maven POM model 4.0.0; dữ liệu của các POM sau phải giữ quan hệ parent hợp lệ.

### 7.2. `core/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>pom-review-demo</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Child không có `/project/version` riêng, nên nó **kế thừa version từ parent**. Tuy nhiên child vẫn khai báo `/project/parent/version` tường minh: sau bump parent, phải rà soát version này có được cập nhật theo hay không.

### 7.3. `app/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>pom-review-demo</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

`app` phụ thuộc vào `core` cùng project version. Dùng `${project.version}` có ích khi các modules được phát hành theo **cùng một version**. Trong repository có nhiều module được phát hành độc lập, không được ép chúng dùng expression này nếu dependency thực cần version khác.

### 7.4. `core/src/main/java/demo/core/Greeting.java`

~~~java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is blank");
        }
        return "Hello " + name + " from core";
    }
}
~~~

Java 17 cung cấp `String.isBlank()`. Với `name="Maven"`, hàm trả lời chào cố định.

### 7.5. `core/src/test/java/demo/core/GreetingTest.java`

~~~java
package demo.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void createsGreeting() {
        assertEquals(
                "Hello Maven from core",
                Greeting.hello("Maven"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Greeting.hello("   "));
    }
}
~~~

Đây là **hai** JUnit Jupiter test methods. Surefire 3.5.4 xử lý tên `*Test` theo naming convention và dùng JUnit Platform provider khi classpath phù hợp.

### 7.6. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.hello("Maven"));
    }
}
~~~

Module `app` cần dependency `core` trên compile/runtime classpath. Vì root aggregator chứa hai modules, Maven Reactor có thể build `core` trước `app`.

### 7.7. Chạy baseline TRƯỚC khi đổi version

Từ root `pom-review-demo`:

~~~bash
mvn --version
java -version
mvn -B -ntp clean verify
~~~

Kỳ vọng:

- Maven build root POM, `core` và `app` theo Reactor dependency order.
- `core` có **2 tests PASS**, `0 failures/errors/skipped`.
- `app` compile được `Main.java` nhờ dependency `core`.
- Build kết thúc `BUILD SUCCESS` nếu môi trường Maven/JDK/repository hợp lệ.
- `core/target/core-1.2.0-SNAPSHOT.jar` và `app/target/app-1.2.0-SNAPSHOT.jar` được tạo từ lifecycle.
- Root `pom.xml` không tạo JAR vì packaging là `pom`.

**Không coi toàn bộ Maven console là stdout cố định**: log còn có version, thời gian, download và đường dẫn.

Chạy ứng dụng với output directories của cả hai modules.

Linux/macOS:

~~~bash
java -cp "app/target/classes:core/target/classes" demo.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "app\target\classes;core\target\classes" demo.app.Main
~~~

**Stdout chính xác của chương trình Java:**

~~~text
Hello Maven from core
~~~

Vì hai module JAR là thin JAR và không có manifest `Main-Class`, ví dụ chủ ý dùng `java -cp`. Đừng giả định `java -jar app/target/app-...jar` tự chạy thành công.

## 8. Thực hành thay version: `1.2.0-SNAPSHOT` → `1.3.0-SNAPSHOT`

Trước khi chạy, bảo đảm chỉ đang thử trên repository demo/branch phù hợp. Nếu có Git:

~~~bash
git status --short
git diff --check
~~~

Sau đó chạy từ root:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:set -DnewVersion=1.3.0-SNAPSHOT -DgenerateBackupPoms=true
~~~

**Goal này có tác dụng sửa tệp POM.** Không thực thi trên repository production nếu team chưa quyết định version mới.

### 8.1. Những thay đổi hợp lý cần tìm

Trong root `pom.xml`:

~~~diff
-    <version>1.2.0-SNAPSHOT</version>
+    <version>1.3.0-SNAPSHOT</version>
~~~

Trong `core/pom.xml` và `app/pom.xml`, phần `<parent><version>` phải trỏ root version mới, nếu các modules được cập nhật đồng bộ:

~~~diff
     <parent>
         <groupId>dev.example</groupId>
         <artifactId>pom-review-demo</artifactId>
-        <version>1.2.0-SNAPSHOT</version>
+        <version>1.3.0-SNAPSHOT</version>
         <relativePath>../pom.xml</relativePath>
     </parent>
~~~

Còn dependency `core` trong app POM có:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>core</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

**Biểu thức này nên giữ nguyên**; giá trị effective version sẽ là `1.3.0-SNAPSHOT` sau khi app kế thừa parent mới. Công cụ không cần thay dòng XML thành literal mới chỉ để effective dependency version thay đổi.

### 8.2. Vì sao cần đọc đủ ba POM?

Chỉ xem root POM sẽ bỏ sót lỗi child vẫn trỏ parent cũ. Chỉ xem child POM sẽ bỏ sót việc root bị đổi thành version ngoài dự kiến hoặc bị sửa pluginManagement.

Chạy:

~~~bash
git status --short
git diff --stat
git diff --check
git diff HEAD -- pom.xml core/pom.xml app/pom.xml
~~~

Trên repo có baseline commit, bạn sẽ thấy các thay đổi có thể đánh giá. Đặc biệt tìm:

- Root project version đúng `1.3.0-SNAPSHOT`.
- Cả hai child `<parent><version>` cũng đúng `1.3.0-SNAPSHOT`.
- App dependency `core` dùng `${project.version}` và resolve đúng bản mới.
- `junit.version` vẫn `5.11.4`, vì thao tác đang thực hiện chỉ đổi **project version**.
- Plugin versions `3.13.0`, `3.5.4` và `3.4.2` vẫn theo ý định.
- `<modules>core/app</modules>` không bị thêm/xóa vô cớ.
- Không có thay đổi bất thường về groupId, artifactId, packaging hoặc source code.
- Không có SCM changes không được yêu cầu; `versions:set` không phải lệnh prepare release.
- Có thể có `*.versionsBackup` theo cấu hình backup; không xem chúng là source files phát hành.

**Nếu không thấy child version được cập nhật**, không bỏ qua lỗi chỉ vì command exit code 0. Kiểm tra goal parameters, phạm vi aggregator/module, cách inheritance thực tế và cân nhắc mục đích của `update-child-modules`; không gõ lệnh thay thế mù trong repo có cấu hình đặc biệt.

### 8.3. Chạy Maven validation và build sau thay đổi

~~~bash
mvn -B -ntp validate
mvn -B -ntp clean verify
~~~

Kết quả dự kiến:

- `validate` xác nhận Maven có thể đọc các POM và tạo mô hình Reactor cho version mới.
- Build/tests compile thành công, `GreetingTest` có 2 test methods PASS.
- Maven tạo `core/target/core-1.3.0-SNAPSHOT.jar` và `app/target/app-1.3.0-SNAPSHOT.jar`.
- Reactor summary của build thể hiện các modules thuộc cùng version mới.
- Java stdout vẫn là `Hello Maven from core` khi chạy bằng classpath ở mục 7.

**Lưu ý:** `validate` không đảm bảo dependency binary compatibility, test coverage hoặc không có vulnerability. Nó là bước đầu của xác nhận POM, không thay cho `verify` và kiểm thử hành vi.

### 8.4. Chỉ chấp nhận sau khi QA xong

Nếu diff đúng, effective POM đúng và build/test pass, có thể loại backup:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:commit
~~~

Sau đó:

~~~bash
git status --short
git diff HEAD -- pom.xml core/pom.xml app/pom.xml
~~~

Khi Git diff đã được reviewer chấp nhận, **Git commit là bước riêng** theo quy trình team. Goal `versions:commit` không tự tạo Git commit.

Nếu thay đổi **không đạt QA**, khi backups của chính lượt thao tác vẫn tồn tại và không có thay đổi cần giữ sau đó, có thể dùng:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.21.0:revert
~~~

Rồi đọc lại `git diff`/`git status` để bảo đảm trạng thái đúng. **Không chạy cả commit lẫn revert như hai bước bắt buộc**: đó là hai nhánh chấp nhận/hoàn tác.

## 9. Kiểm tra `effective-pom`: những thay đổi ẩn

Một thay đổi version được khai báo trong POM có thể làm nhiều **giá trị hiệu lực** thay đổi do inheritance, profiles, BOM imports hoặc plugin management. Đọc POM nguồn là bước đầu; **effective POM** cho bạn thấy mô hình Maven sau nội suy/kế thừa/merge theo ngữ cảnh hiện tại.

Lệnh cơ bản:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Trong reactor nhiều module, hãy xác nhận file output thuộc **module nào** hoặc dùng goal với project selection thích hợp để lấy đúng effective POM cần so. Không suy luận một file effective POM ở root đại diện đầy đủ mọi module.

Ví dụ kiểm tra app module:

~~~bash
mvn -pl :app help:effective-pom -Doutput=app-effective-pom.xml
~~~

Maven Help Plugin có thể ghi output theo project base directory và cấu hình plugin; xác định vị trí file thực tế qua log. File này **là tài liệu sinh ra**, không phải POM nguồn được phép sửa thủ công để đổi phiên bản.

### Những điều cần xác minh

Trong effective POM của `app`:

- Effective project version = `1.3.0-SNAPSHOT`.
- Parent/version đúng và resolve được.
- Dependency `dev.example:core` dùng version `1.3.0-SNAPSHOT`, dù source có `${project.version}`.
- Compiler Plugin nhận Java release `17` và version được quản lý.
- Plugin Surefire/JAR versions nhận từ parent/pluginManagement.
- Không có repositories, active profiles hoặc exclusions ngoài dự kiến.

Có thể dùng Help Plugin để xem một biểu thức:

~~~bash
mvn -q -pl :app help:evaluate -Dexpression=project.version -DforceStdout
~~~

Với demo và môi trường thực thi phù hợp, giá trị hiệu lực mong đợi là:

~~~text
1.3.0-SNAPSHOT
~~~

**Đây là giá trị của biểu thức, không phải cam kết stdout toàn bộ lệnh không có bất kỳ log nào trong mọi Maven/plugin version.** `-q`/`-DforceStdout` giúp giảm output, nhưng một số môi trường còn in warning hoặc thông báo khác.

### Đừng nhầm effective POM với diff nguồn

- `git diff` cho thấy **dòng XML do tool sửa thực sự**.
- `help:effective-pom` cho thấy **cấu hình cuối Maven dùng**, kể cả inherited/managed values.
- `dependency:tree` cho thấy **dependency resolution** theo graph khi Maven thực thi.

Cần cả ba khi version bump có ảnh hưởng đến dependency graph hoặc plugin behavior.

## 10. Kiểm tra dependency graph và plugins

Sau khi đổi phiên bản, chạy ví dụ:

~~~bash
mvn -pl :app -am dependency:tree
~~~

Trong demo, app phụ thuộc core `1.3.0-SNAPSHOT`. Tree có thể còn các dependency của test ở `core` khi in tree cho từng module, tùy goal options và scope.

Một đoạn ý nghĩa:

~~~text
dev.example:app:jar:1.3.0-SNAPSHOT
\- dev.example:core:jar:1.3.0-SNAPSHOT:compile
~~~

Đây là **trích đoạn minh họa** của dependency tree, không phải toàn bộ output cố định. Nếu actual tree cho thấy `core:1.2.0-SNAPSHOT`, có thể parent/dependency/reference vẫn chưa đồng bộ.

### Plugin version cũng cần kiểm tra

Maven plugins không giống library dependencies: thay Compiler/Surefire/JAR/Resources/Assembly/Shade Plugin version có thể đổi goal parameters, defaults, compatibility, generated archive và test provider.

Khi công cụ nâng plugin versions, hãy rà soát:

- `build/plugins` và `build/pluginManagement`.
- `reporting/plugins` nếu có.
- Các executions và phase bindings có còn hợp lệ?
- Có goal/parameter nào bị deprecated hoặc đổi hành vi?
- JDK/Maven tối thiểu của plugin mới có phù hợp môi trường CI?
- Có plugin-generated source/resources/artifacts nào cần kiểm chứng?
- Có khai báo plugin version ở parent nhưng bị override trong child?
- Có differences giữa profile local và profile CI không?

Đừng dùng mỗi kết quả unit test của một module để phán quyết plugin upgrade ảnh hưởng cả reactor. Một plugin packaging có thể chỉ chạy ở `package`/`verify`, còn lệnh `mvn test` chưa chạm đến.

## 11. Rà soát versions quản lý bằng properties và BOM

Một project thường đặt version tại parent:

~~~xml
<properties>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

và dùng ở dependency:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.version}</version>
    <scope>test</scope>
</dependency>
~~~

Nếu công cụ sửa `junit.version`, **mọi chỗ tham chiếu property** có thể được thay hiệu lực cùng lúc. Review phải trả lời:

1. Property này được dùng ở những POM/module nào?
2. Có dùng cho cả dependency và plugin không?
3. Value mới có tương thích Java, Surefire/JUnit engine và classpath?
4. Parent hoặc active profile có override property khác không?
5. Có mối tương quan giữa version của API và runtime/engine cần giữ không?

### BOM import

Trong `dependencyManagement`, có thể nhập một BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh minh họa về cú pháp BOM**, không phải dependency có thật trong project runnable ở mục 7. Khi cập nhật BOM từ version A sang B, nhiều dependency versions được quản lý có thể thay đổi **mà không có dòng diff trực tiếp trong từng `<dependency>`**.

Do đó sau nâng BOM:

- Đọc changelog/compatibility policy của BOM.
- So `effective-pom` và dependency tree.
- Kiểm tra dependency convergence/duplicate versions nếu hệ thống có yêu cầu.
- Chạy compile/tests/integration tests của các modules chịu ảnh hưởng.
- Tránh dùng “Git diff chỉ thay một dòng” làm bằng chứng rủi ro bằng không.

### Imported BOM không biến mọi dependency thành dependency thực

`dependencyManagement` quản lý version và thuộc tính khi dependency được dùng; nó **không tự bổ sung** từng managed dependency vào classpath. Vì vậy một thay đổi BOM có thể **không ảnh hưởng** module không khai báo bất kỳ dependency nào chịu quản lý, nhưng có thể ảnh hưởng mạnh module khác.

## 12. Rà soát parent, child và dependency nội bộ trong Reactor

Trong multi-module Maven, lỗi version management phổ biến nhất là **tọa độ nội bộ không còn thống nhất** sau khi tool rewrite POM.

Bảng kiểm tra:

| Quan hệ | Trước | Sau mong đợi | Nếu sai |
| --- | --- | --- | --- |
| Root project version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` | Lệnh set không đạt mục tiêu. |
| `core` parent version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` | Parent không resolve hoặc dùng model cũ. |
| `app` parent version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` | Mismatch với aggregator parent. |
| `core` project version | Kế thừa parent | `1.3.0-SNAPSHOT` | Child không kế thừa đúng parent. |
| `app` project version | Kế thừa parent | `1.3.0-SNAPSHOT` | Child có explicit version khác ngoài ý định. |
| `app` dependency `core` | `${project.version}` | Resolve `1.3.0-SNAPSHOT` | Intra-reactor dependency không khớp GAV. |

**Không áp dụng bảng cho dự án cố ý dùng versions độc lập ở từng module.** Nếu mỗi module có lifecycle release riêng, việc tự động ép tất cả lên một version có thể là sai về thiết kế, mặc dù Maven có thể build.

### Khi parent có `relativePath`

Child POM trong demo:

~~~xml
<relativePath>../pom.xml</relativePath>
~~~

là đường dẫn đến parent trong checkout. Nếu công cụ đổi `parent.version` thành version không khớp parent file, Maven có thể báo non-resolvable parent hoặc mismatch.

Nếu parent thực sự ở một repository khác và không phải file local, có thể cần `<relativePath/>` để Maven không tìm local parent mặc định; **không chèn tùy tiện `<relativePath/>` vào demo** vì parent nằm tại `../pom.xml`.

### Profile có thể che lỗi

Ví dụ project có profile `ci` override một property version; chạy `mvn validate` không bật `ci` chưa đủ. Khi build production chạy `-Pci` hoặc một property activation, cần kiểm tra model và build **đúng profile đang phát hành**.

Trong demo không định nghĩa profile; đây là hướng dẫn cho dự án thực.

## 13. Maven Release Plugin: trường hợp tool không chỉ sửa POM

Maven Release Plugin `release:prepare` thường làm những việc lớn hơn một version bump thông thường:

1. Kiểm tra trạng thái SCM và điều kiện chuẩn bị release.
2. Kiểm tra các SNAPSHOT dependencies theo quy tắc release.
3. Đổi POM sang release version, ví dụ `1.2.0-SNAPSHOT` → `1.2.0`.
4. Điều chỉnh `<scm>` information/tag theo cấu hình.
5. Chạy preparation goals/tests.
6. Commit trạng thái release POM.
7. Tạo SCM tag.
8. Đổi working copy sang phiên bản phát triển tiếp, ví dụ `1.3.0-SNAPSHOT`.
9. Commit trạng thái phát triển mới.

Đây là luồng khái niệm của một release chuẩn; các phases/configuration và SCM implementation có thể thay đổi. Vì release goal **có khả năng commit/tag**, đừng chạy trực tiếp `mvn release:prepare` trong repository thật chỉ để xem POM sẽ đổi thế nào.

### Dry run trước khi làm release

Theo tài liệu chính thức, có thể dùng:

~~~bash
mvn release:prepare -DdryRun=true
~~~

trong môi trường được phép và với release plugin đã cấu hình đúng. Dry run có thể sinh các POM mô phỏng như `pom.xml.tag` / `pom.xml.next` để review thay đổi mà không commit/tag như release thật.

**Không dùng “dry run” như lời bảo đảm tuyệt đối rằng mọi side effect đều bằng không** nếu project có plugin hooks/custom scripts: hãy đọc log, cấu hình và thực hiện trên branch/checkout phù hợp.

### Những điểm cần đối chiếu sau release tool

- Release version và next development version có đúng policy không?
- Mọi module versions, parent references và internal dependencies đã đổi đồng bộ chưa?
- `<scm><tag>` có trỏ đúng release tag dự kiến?
- Có SNAPSHOT dependencies còn sót trong POM của bản release không?
- Git commits/tags nào được tạo; có thay đổi ngoài POM không?
- Artifact được build từ tag nào; POM release và POM development khác nhau ra sao?
- Có file backup/state như `release.properties` hoặc `pom.xml.releaseBackup` cần xử lý theo plugin lifecycle không?
- Nếu rollback, có cần `release:rollback` và chính sách SCM hay không?

**Không nhầm `versions:revert` với `release:rollback`.** Hai goal thuộc plugin khác nhau, lưu trạng thái và áp dụng side effects khác nhau. Với release đã đẩy tag/commit lên remote, rollback local không nhất thiết đảo ngược mọi tác động trên remote; cần quy trình SCM/release của tổ chức.

## 14. Các loại thay đổi bất ngờ cần báo khi review

### 14.1. XML bị format lại quá nhiều

Công cụ có thể đổi whitespace, namespace formatting, indentation hoặc line endings. Một diff dài không chắc là sai, nhưng khiến review khó hơn.

Nên:

- Đọc `git diff --stat` và các phần đổi ngoài version.
- Phân biệt formatting-only với thay đổi giá trị.
- Không tự format tất cả POM cùng lúc nếu ticket chỉ yêu cầu version bump.
- Xem thay đổi ở comment, profiles, repositories, license và distributionManagement.
- Dùng XML parser/Maven model validation thay vì so bằng regex.

### 14.2. Build output timestamp

Một số versions goal có tham số xử lý `project.build.outputTimestamp` phục vụ reproducible builds. Nếu công cụ thay đổi property này ngoài project version, hãy xác nhận theo policy của dự án, đặc biệt khi pipeline yêu cầu reproducible artifacts.

Không tự động coi một khác biệt về outputTimestamp là lỗi, nhưng cũng không bỏ qua nó khi release policy đòi cố định timestamp.

### 14.3. SNAPSHOT ↔ release

Thay `1.2.0-SNAPSHOT` thành `1.2.0` có thể chuyển project từ development sang release coordinate; đây không phải đổi tên file đơn giản. Phải kiểm tra:

- Repository lưu artifacts có cho overwrite release không?
- SCM tag và release notes tương ứng chưa?
- Các module dependency versions có hết SNAPSHOT đúng phạm vi không?
- CI có đang chạy test trên artifact release hay artifact SNAPSHOT mới?

Không tự xóa chuỗi `-SNAPSHOT` trên toàn bộ các POM chỉ vì Maven có goal làm điều đó.

### 14.4. Version ranges hoặc dynamic expressions

Dependency version dạng range, dùng `LATEST`/`RELEASE` ở cấu hình cũ hoặc dynamic CI property có thể dẫn đến resolution khác khi metadata thay đổi. Một tool rewrite các giá trị này cần được kiểm tra bằng effective model, dependency tree và reproducible build expectations.

Ưu tiên version tường minh/được quản lý rõ theo policies thay vì phụ thuộc một tọa độ quá động khiến hai build cùng commit lấy binary khác nhau.

### 14.5. Plugin upgrade kéo theo build behavior change

Nâng Compiler/Surefire/JAR/Resources/Shade Plugin có thể ảnh hưởng classfile target, test discovery, manifest, resource filtering, dependency shading và archive contents. Sau plugin upgrade, cần chạy phase phù hợp để kiểm tra: `mvn test` không thể thay `mvn package` nếu plugin mục tiêu chỉ chạy ở packaging.

### 14.6. Khác biệt local và CI

Một build local có thể PASS nhờ local repository chứa SNAPSHOT từ commit trước. Để phát hiện, hãy chạy CI trên checkout phù hợp và chú ý `-pl ... -am` cho các upstream reactor modules khi build chọn lọc.

Đừng kết luận một dependency được build từ source hiện tại chỉ vì `mvn -pl :app package` thành công; nếu không có `-am`, Maven có thể lấy artifact đã cài cũ.

## 15. Chẩn đoán lỗi thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| `Non-resolvable parent POM` sau version bump. | Child `<parent><version>` không khớp root hoặc parent ngoài không có ở repo. | So parent coordinates, `relativePath` và repositories. |
| App không resolve được `core` version mới. | App dependency vẫn version cũ, module không có trong Reactor hoặc chạy `-pl` thiếu `-am`. | Đọc app POM, root modules và dùng reactor `-am`. |
| Tool báo success nhưng Git diff không có. | Version đã đúng, file không tracked, command nhắm sai root hoặc changes đã stage. | `git status`, `git diff --cached`, command/working directory. |
| Có file `pom.xml.versionsBackup`. | Versions Plugin tạo backup mặc định. | Review POM trước khi `versions:commit`/`revert`. |
| `versions:revert` không khôi phục. | Backup không tồn tại/đã xóa hoặc lần chỉnh sửa thuộc plugin khác. | Kiểm tra backup và Git history, không revert mù. |
| `versions:commit` chạy xong nhưng Git vẫn có changes. | Goal chỉ xóa backup, không commit Git. | `git status` và quy trình Git commit riêng. |
| JUnit test fail sau update properties. | JUnit API/engine/Surefire mismatch hoặc thay đổi test behavior. | Xem dependency tree, plugin versions, reports. |
| Compiler fail dù chỉ đổi parent. | Parent mới thay compiler configuration hoặc JDK requirement. | Xem effective POM và Maven/JDK runtime. |
| `validate` PASS nhưng `verify` FAIL. | Model parse được nhưng compile/tests/packaging có vấn đề. | Đọc goal/phase thất bại và reports. |
| Plugin report một version không mong đợi. | Parent/pluginManagement/profile override. | Xem effective POM của đúng module/profile. |
| BOM đổi một dòng nhưng nhiều dependency versions khác. | Imported BOM quản lý transitive/managed versions. | So dependency tree và release notes của BOM. |
| CI build PASS với module library cũ. | Chỉ build consumer, resolver dùng SNAPSHOT cache. | Dùng `-pl :app -am clean verify`. |
| POM đổi cả SCM tags. | Release Plugin hoặc script đã can thiệp release metadata. | So `<scm>`, Git tags/commits và release plan. |
| Tệp format bị sửa hàng trăm dòng. | XML rewriter thay indentation/line endings. | Kiểm tra semantic diff, giảm nhiễu formatting. |
| Module project version khác parent ngoài ý định. | Child có explicit `<version>` hoặc tool chọn sai scope. | So parent/project version trong từng POM. |
| DependencyManagement mới nhưng runtime vẫn thiếu class. | Managed dependency không tự trở thành dependency thực. | Kiểm tra `<dependencies>` và tree. |
| Backup của nhiều lượt thay đổi bị lẫn. | Chạy nhiều goals khi chưa chấp nhận/hoàn tác lượt trước. | Tách thay đổi, kiểm tra backup và Git state. |
| CI không tìm thấy profile properties. | Profile khác nhau local/CI. | Re-run với đúng `-P`/property activation. |
| Nâng version lên release dù mong SNAPSHOT. | Chọn sai `newVersion` hoặc release workflow. | So policy/version, revert đúng công cụ. |

## 16. Checklist PR sau khi công cụ sửa POM

### Nhóm A — Phạm vi và provenance

- [ ] Biết công cụ/goal chính xác, version, arguments và working directory.
- [ ] Đã có baseline Git commit/branch rõ trước khi thay đổi.
- [ ] `git status --short` chỉ ra mọi tracked/untracked files có liên quan.
- [ ] `git diff --stat` và `git diff HEAD` thể hiện đúng phạm vi.
- [ ] Không có thay đổi source, CI, SCM, repositories hoặc plugin ngoài yêu cầu.
- [ ] Đã kiểm tra backup files; không đưa `*.versionsBackup` vào PR vô ý.

### Nhóm B — POM model

- [ ] Root project version đúng dự kiến; hiểu SNAPSHOT/release semantics.
- [ ] Child `<parent><version>` khớp parent tương ứng.
- [ ] Các module phụ thuộc nhau dùng GAV/version đúng theo chính sách.
- [ ] Child có explicit `<version>` được rà soát, không bị ép cùng version nếu release độc lập.
- [ ] Property version và mọi nơi sử dụng được kiểm tra.
- [ ] `dependencyManagement`, imported BOM và `pluginManagement` không đổi ngoài ý định.
- [ ] Profiles, repositories, build extensions và reporting plugins được xét khi liên quan.
- [ ] XML/POM hợp lệ, namespace và encoding không bị phá.
- [ ] `git diff --check` không báo lỗi whitespace cần sửa.

### Nhóm C — Xác minh build

- [ ] `mvn validate` PASS với đúng Maven/JDK.
- [ ] `help:effective-pom` của modules chịu ảnh hưởng có values mong đợi.
- [ ] `dependency:tree` không lộ dependency version mismatch/duplicate ngoài dự định.
- [ ] `mvn clean verify` PASS trên Reactor hiện hành.
- [ ] Test reports không có failures/errors và số tests thực chạy phù hợp.
- [ ] Nếu packaging/plugin upgrade, đã kiểm tra artifact JAR/WAR, manifest/resources.
- [ ] Nếu có profiles CI/release, đã test đúng profile và môi trường.
- [ ] CI chạy trên checkout sạch/đại diện, không chỉ dựa cache cũ.

### Nhóm D — Chấp nhận hoặc hoàn tác

- [ ] Chỉ sau QA mới dùng `versions:commit` để loại backup, nếu luồng Versions Plugin có backup.
- [ ] Nếu QA không đạt, biết cách `versions:revert`/Git restore có kiểm soát, không xóa công việc khác.
- [ ] Git commit/PR review là bước riêng, không nhầm với `versions:commit`.
- [ ] Nếu dùng Release Plugin, đã kiểm tra Git tags/commits/SCM và chính sách rollback.
- [ ] Không deploy/release tự động chỉ vì version bump tool báo success.

## 17. Bài tập thực hành

### Bài A — Phân loại các version

Với:

~~~xml
<parent>
    <groupId>org.example</groupId>
    <artifactId>platform-parent</artifactId>
    <version>3.0.0</version>
</parent>
<artifactId>invoice-app</artifactId>
<version>1.4.0-SNAPSHOT</version>
<properties>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

Hãy trả lời:

1. Version của project và parent có bắt buộc bằng nhau không?
2. Nếu tool chỉ sửa `junit.version`, project coordinate có đổi không?
3. Nếu tool đổi parent từ `3.0.0` sang `4.0.0`, có cần đọc effective POM không?
4. Nếu `invoice-app` nằm trong multi-module Reactor, tại sao cần kiểm tra dependency versions của các module nội bộ?
5. Vì sao nhìn `git diff` rỗng không đủ chứng minh không có thay đổi khi đã stage POM?

**Đáp án:** project version và parent version không bắt buộc trùng; nâng JUnit property không đổi project coordinate; parent mới có thể thay inherited management nên cần effective POM; internal version mismatch có thể phá Reactor resolution; khi staged changes cần xem `git diff --cached` hoặc `git diff HEAD`.

### Bài B — Chạy Java 17 multi-module

1. Tạo root POM, `core/pom.xml` và `app/pom.xml` như mục 7.
2. Tạo `Greeting.java`, `GreetingTest.java` và `Main.java` đúng package/path.
3. Chạy `mvn -B -ntp clean verify` và xác nhận 2 unit tests PASS.
4. Chạy Java từ `target/classes`, đối chiếu stdout `Hello Maven from core`.
5. Đảm bảo baseline Git rõ, rồi chạy `versions:set` với version `1.3.0-SNAPSHOT` như mục 8.
6. Mở `git diff HEAD -- pom.xml core/pom.xml app/pom.xml` và xác định mọi thay đổi version.
7. Kiểm tra effective app project version và dependency core.
8. Chạy lại `mvn -B -ntp clean verify`; xem tên các JAR `*-1.3.0-SNAPSHOT.jar`.
9. Thử luồng `versions:revert` khi còn backup, rồi xác nhận POM trở về phiên bản ban đầu; **hoặc** dùng `versions:commit` để chấp nhận, không chạy hai nhánh trên cùng một lượt.
10. Giải thích tại sao `versions:commit` không tương đương một Git commit/PR.

### Bài C — Nâng version property có tác động ngoài ý muốn

Parent POM có:

~~~xml
<properties>
    <shared.version>1.0.0</shared.version>
</properties>
~~~

Hai dependencies dùng `${shared.version}` dù chúng không thuộc cùng release train. Một tool cập nhật property lên `2.0.0`. Hãy:

- Liệt kê các module/dependency đang dùng property.
- Xác minh phiên bản `2.0.0` có tồn tại và tương thích cho **cả hai** hay không.
- Nếu không phù hợp, tách thành hai properties có tên rõ ràng thay vì ép chúng share version.
- Chạy effective POM, dependency tree và test modules chịu ảnh hưởng.
- Giải thích tại sao không thể chỉ nhìn một dòng diff trong parent để ước lượng phạm vi.

### Bài D — Phân tích release prepare

Một build script chạy `release:prepare` khiến root `pom.xml` và `<scm><tag>` thay đổi, đồng thời xuất hiện Git tag. Hãy nêu:

1. Những giai đoạn release chuẩn có thể đã chạy?
2. Có thể dùng `versions:revert` để đảo mọi Git commits/tags không?
3. Những file/state và Git references nào phải kiểm tra?
4. Vì sao nên dry run trên branch/checkout an toàn trước?
5. Làm thế nào để phân biệt release version với next development SNAPSHOT?

## 18. Mẫu quy trình review dùng trong nhóm

Khi nhận một pull request “bump Maven versions”, một reviewer có thể ghi kết luận:

~~~text
Mục tiêu:
  root + core + app: 1.2.0-SNAPSHOT -> 1.3.0-SNAPSHOT
  không đổi JUnit/plugin versions

Phạm vi:
  pom.xml
  core/pom.xml
  app/pom.xml

Đã kiểm:
  Git diff: root version và child parent references phù hợp
  Effective POM app: project.version = 1.3.0-SNAPSHOT
  Effective dependency core = 1.3.0-SNAPSHOT
  Reactor build: core trước app
  clean verify: PASS, core 2 tests PASS
  Java stdout: Hello Maven from core

Quyết định:
  CHẤP NHẬN nếu không có thay đổi ngoài phạm vi và CI tương đương PASS
  HOÀN TÁC/CHỈNH SỬA nếu thiếu child parent update,
  dependency/plugin đổi ngoài dự kiến hoặc CI fail
~~~

Đây là **mẫu kết luận dự kiến của demo**, không phải log được lấy từ một workspace cụ thể. Trong dự án thật, cần ghi commit, PR, Maven/JDK versions, profiles và link CI run để truy vết.

## 19. Tổng kết

**Công cụ đổi version giúp tự động hóa chỉnh POM, nhưng không thay thế trách nhiệm review về build và publication contract.**

Quy trình đáng tin cậy:

~~~text
Biết công cụ/command và version mục tiêu
                │
                ▼
Tạo baseline Git / kiểm tra working tree
                │
                ▼
Chạy công cụ sửa version trên đúng project
                │
                ▼
Xem git status + diff + backups
                │
                ▼
Kiểm tra project/parent/dependency/plugin/property/BOM/SCM
                │
                ▼
Maven validate + effective POM + dependency tree
                │
                ▼
Maven clean verify + kiểm tra artifact/runtime
                │
            ┌───┴────┐
            ▼        ▼
        Chấp nhận   Hoàn tác
       backup commit  backup revert
       + Git review   hoặc khôi phục có kiểm soát
~~~

Nhớ ba điểm cốt lõi:

1. **Version trong XML có nhiều vai trò**; phải xác định nơi đổi và các giá trị hiệu lực bị ảnh hưởng.
2. **`versions:commit` không phải Git commit**, `versions:revert` không phải rollback SCM release.
3. **Build PASS là cần nhưng chưa đủ**: vẫn phải xác minh đúng module, đúng version, dependency graph, profiles và artifact phát hành.

## Tài liệu chính thức

- MojoHaus Versions Maven Plugin — `versions:set`, parameters và backups: https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html
- MojoHaus Versions Maven Plugin — `versions:revert`: https://www.mojohaus.org/versions/versions-maven-plugin/revert-mojo.html
- MojoHaus Versions Maven Plugin — `versions:commit`: https://www.mojohaus.org/versions/versions-maven-plugin/commit-mojo.html
- MojoHaus Versions Maven Plugin — `versions:update-properties`: https://www.mojohaus.org/versions/versions-maven-plugin/update-properties-mojo.html
- MojoHaus Versions Maven Plugin — Fixing a Multi-module Build: https://www.mojohaus.org/versions/versions-maven-plugin/examples/update-child-modules.html
- MojoHaus Versions Maven Plugin — Advancing dependency versions: https://www.mojohaus.org/versions/versions-maven-plugin/examples/advancing-dependency-versions.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — Maven Release Plugin (Prepare a Release): https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html
- Apache Maven — Maven Release Plugin (Plugin Information): https://maven.apache.org/maven-release/maven-release-plugin/plugin-info.html

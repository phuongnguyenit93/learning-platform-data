# Dependency convergence, phiên bản bị cấm và phụ thuộc trùng trong Maven

## 1. Mục tiêu: biến rủi ro dependency thành cổng chất lượng

Maven tự giải quyết các dependency trực tiếp và bắc cầu để tạo classpath khi biên dịch, kiểm thử và chạy ứng dụng. Việc build thành công **không có nghĩa** dependency graph của project đã tuân thủ chính sách phiên bản, bảo mật hoặc không có class trùng.

Ba vấn đề phải phân biệt:

1. **Dependency convergence**: các đường dẫn dependency khác nhau cùng yêu cầu một artifact nhưng ở **những version khác nhau**. Maven có thể chọn một version duy nhất bằng dependency mediation, nhưng sự bất đồng trong graph vẫn tồn tại.
2. **Phiên bản/artifact bị cấm**: một dependency (trực tiếp hoặc bắc cầu) khớp quy tắc không được phép sử dụng, ví dụ bản `org.slf4j:slf4j-simple:2.0.12` bị cấm **theo chính sách minh họa** của dự án.
3. **Phụ thuộc trùng** có ít nhất hai nghĩa:
   - **Duplicate POM declaration**: cùng `groupId:artifactId:type:classifier` được khai báo nhiều lần trong `<dependencies>` của một POM.
   - **Duplicate classes**: hai JAR **khác nhau** chứa cùng một tên class, ví dụ cùng có entry `org/apache/commons/logging/Log.class`.

Các hiện tượng này **không đồng nghĩa**, không do cùng một Enforcer rule phát hiện, và có cách sửa khác nhau.

Bài học tập trung vào **Maven Enforcer Plugin** như một quality gate tự động, với các rules:

- `dependencyConvergence`.
- `bannedDependencies`.
- `banDuplicatePomDependencyVersions`.
- `banDuplicateClasses` từ **MojoHaus Extra Enforcer Rules** (không phải rule built-in).
- Quy tắc bổ sung khi cần: `requireUpperBoundDeps` và `banDynamicVersions`.

Sau bài này, bạn có thể thiết kế cổng chất lượng ở phase `validate`, đọc lỗi Enforcer, phân tích bằng `dependency:tree`, sửa bằng version alignment, BOM, exclusions hoặc loại dependency khai báo sai, rồi tích hợp kiểm tra vào CI.

Ví dụ dùng **Java 17+**, Maven 3.9.x, Apache Maven Enforcer Plugin **3.6.3** và MojoHaus Extra Enforcer Rules **1.12.1**. Các version được ghim để bài có thể tái lập; không hiểu chúng là lời khẳng định về mọi phiên bản mới nhất ở tương lai.

## 2. Vì sao BUILD SUCCESS chưa chắc đủ?

Một ví dụ dependency graph:

~~~text
my-app
├── framework-a:1.0
│   └── shared-api:1.0
└── framework-b:2.0
    └── shared-api:2.0
~~~

Maven không đơn giản đưa cả hai version của cùng một artifact vào classpath. Cơ chế **dependency mediation** xác định version được chọn dựa trên quy tắc độ gần:

- Version ở dependency path **gần root project hơn** thường thắng (nearest definition).
- Nếu cùng khoảng cách, **khai báo xuất hiện trước** thường thắng.
- Khai báo dependency trực tiếp và `dependencyManagement` có thể điều khiển kết quả theo quy tắc Maven.

Do đó, ứng dụng có thể compile với `shared-api:1.0` trong khi một thư viện được biên dịch dựa trên `shared-api:2.0`. Không phải mọi mismatch đều lập tức thất bại; một số chỉ phát sinh khi chạy tới code path có binary incompatibility, ví dụ `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi resource/service provider.

**Enforcer không thay thế Maven Resolver.** Nó không tự sửa dependency graph hay tự tăng version. Nó **đánh giá graph/chính sách** và làm build thất bại để developer phải quyết định cách xử lý.

## 3. Bốn loại vi phạm: bảng phân biệt

| Vấn đề | Tình huống | Rule phù hợp | Phạm vi kiểm tra |
| --- | --- | --- | --- |
| Version không hội tụ | A → C:1.0 và B → C:2.0 | `dependencyConvergence` | Đường dẫn/version trong dependency tree |
| Artifact hoặc version bị cấm | `legacy-lib:1.5` không được dùng | `bannedDependencies` | Dependencies theo include/exclude pattern, trực tiếp/bắc cầu |
| Khai báo dependency lặp | Hai khai báo cùng GA/type/classifier trong POM | `banDuplicatePomDependencyVersions` | Khai báo trong POM project |
| Class trùng giữa các JAR | JAR X và Y đều chứa `p/q/Service.class` | `banDuplicateClasses` (extra rule) | Nội dung class entries của dependency JARs |

Một dependency tree **hội tụ hoàn toàn** vẫn có thể chứa **hai JAR khác coordinates nhưng cùng class**. Ngược lại, một POM không có dependency declaration trùng vẫn có thể có version conflict ở transitive dependencies.

Không dùng một rule để thay thế tất cả những kiểm tra còn lại.

## 4. Cơ chế Maven Enforcer Plugin

Maven Enforcer Plugin chạy những **rules** do bạn cấu hình. Goal chính là:

~~~text
org.apache.maven.plugins:maven-enforcer-plugin:enforce
~~~

Goal `enforce` được thiết kế để gắn vào Maven lifecycle; **phase mặc định là `validate`** theo metadata của plugin. Khi plugin được khai báo với execution/goal phù hợp, lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

thường thực hiện Enforcer rất sớm, **trước compile/test/package**.

Nếu một rule báo vi phạm và `fail=true`, Maven kết thúc với mã thoát lỗi; CI nên xem đây là một **quality gate failure**.

Các tùy chọn quan trọng:

- `<fail>true</fail>`: build fail khi rule không đạt; đây là giá trị mặc định.
- `<failFast>false</failFast>`: cho phép tiếp tục đánh giá nhiều rules để thu thập lỗi thay vì dừng ngay tại lỗi đầu tiên; mặc định false ở goal.
- `<skip>true</skip>` hoặc CLI `-Denforcer.skip=true`: **bỏ qua cổng chất lượng**, chỉ dùng trong tình huống có kiểm soát để chẩn đoán, không dùng trong CI chính thức.
- `<rules>...</rules>`: tập rule có hiệu lực.
- Plugin có thể chạy **một lần trên mỗi module** trong reactor, không phải một kiểm tra duy nhất cho toàn repository.

**Quan trọng với parent POM:** chỉ đặt plugin trong `<pluginManagement>` chủ yếu cung cấp version/configuration **khi plugin được dùng**. Muốn thực sự chạy execution, khai báo plugin trong `<build><plugins>` của parent hoặc module, với inheritance theo chính sách của repo.

## 5. Dependency convergence hoạt động ra sao?

Rule `dependencyConvergence` yêu cầu những đường dẫn dẫn tới cùng một dependency artifact thống nhất version. Nó xem **graph đã khai báo/resolved paths**, chứ không chỉ hỏi Maven cuối cùng chọn version nào cho classpath.

Ví dụ:

~~~text
policy-demo:1.0.0
├── org.slf4j:slf4j-api:2.0.13          (direct)
└── org.slf4j:slf4j-simple:2.0.12     (direct)
    └── org.slf4j:slf4j-api:2.0.12    (transitive)
~~~

Theo nguyên tắc nearest definition, Maven thường chọn `slf4j-api:2.0.13` vì nó là dependency trực tiếp. Nhưng hai đường dẫn vẫn **yêu cầu** 2.0.13 và 2.0.12. Enforcer `dependencyConvergence` sẽ phát hiện xung đột, ngay cả khi Maven đã loại version 2.0.12 khỏi classpath hiệu dụng bằng mediation.

Đây là điểm cốt lõi của **convergence**: không chỉ ép runtime có đúng một JAR, mà còn yêu cầu **mọi đường dẫn dependency liên quan nhất quán**.

### Mismatch không luôn gây lỗi runtime ngay lập tức

Với hai phiên bản gần nhau của SLF4J, một ứng dụng đơn giản có thể chạy được mặc dù Enforcer thất bại. Việc có thể chạy một code path **không chứng minh** các thư viện hoàn toàn tương thích hoặc policy được đáp ứng.

Đừng đưa ra dự đoán “chắc chắn NoSuchMethodError” nếu chưa có bằng chứng. Enforcer là kiểm tra tính nhất quán của graph; runtime error phụ thuộc những API thực sự được dùng.

### Cú pháp cấu hình cơ bản

~~~xml
<dependencyConvergence/>
~~~

Hoặc khi cần tùy chỉnh:

~~~xml
<dependencyConvergence>
    <uniqueVersions>false</uniqueVersions>
</dependencyConvergence>
~~~

`uniqueVersions=false` là hành vi mặc định: với SNAPSHOT, so sánh logical SNAPSHOT versions thay vì các timestamped build identifiers. Chỉ đặt true khi chính sách muốn phân biệt timestamped SNAPSHOT artifacts.

### Các scope mặc định

Theo tài liệu rule, `dependencyConvergence` **mặc định loại `provided` và `test` khỏi phạm vi tính lỗi** qua `excludedScopes`. Nếu dự án cần chặn conflict cả ở test classpath, cân nhắc cấu hình scope theo tài liệu tương ứng thay vì mặc định cho rằng mọi test-only mismatch đều bị chặn.

Ví dụ chỉ quan tâm một số nhóm:

~~~xml
<dependencyConvergence>
    <includes>
        <include>org.slf4j</include>
        <include>com.fasterxml.jackson.core</include>
    </includes>
</dependencyConvergence>
~~~

Đây là **đoạn rule configuration**, không phải một POM đầy đủ. `includes` giới hạn artifacts cần check; `excludes` tạo ngoại lệ. Đừng tạo ngoại lệ quá rộng chỉ để pipeline xanh: bạn có thể che một conflict thật.

## 6. Phiên bản bị cấm: bannedDependencies

Rule built-in `bannedDependencies` làm build fail nếu một dependency khớp danh sách `<excludes>`, trừ những ngoại lệ xác định trong `<includes>`.

Ví dụ policy **minh họa, không phải advisory bảo mật**:

~~~xml
<bannedDependencies>
    <excludes>
        <exclude>org.slf4j:slf4j-simple:[2.0.12]</exclude>
    </excludes>
    <message>
        Ban 2.0.12 by this lab's version-alignment policy.
    </message>
</bannedDependencies>
~~~

Ý nghĩa: không được có dependency có coordinates `org.slf4j:slf4j-simple` ở **chính xác version 2.0.12** trong graph theo scope mà rule kiểm tra.

**Không khẳng định version 2.0.12 có CVE.** Ở đây nó chỉ là phiên bản bị **chính sách bài lab** từ chối. Trong dự án thật, danh sách banned versions cần dựa trên quyết định kỹ thuật, bảo mật, license, tổ chức hoặc compatibility có căn cứ.

### searchTransitive

Mặc định:

~~~xml
<searchTransitive>true</searchTransitive>
~~~

Có nghĩa cả dependencies trực tiếp **và bắc cầu** có thể bị kiểm tra. Nếu chỉ muốn kiểm tra direct dependencies:

~~~xml
<searchTransitive>false</searchTransitive>
~~~

Đừng tắt kiểm tra transitive nếu policy là “không cho artifact này xuất hiện trên runtime classpath”, vì artifact có thể lọt vào qua một third-party library.

### Banned coordinates có định dạng gì?

Tài liệu Maven Enforcer mô tả:

~~~text
groupId[:artifactId][:version][:type][:scope][:classifier]
~~~

Các trường sau `groupId` là tùy chọn. Có thể dùng wildcard `*` để khớp một phần hoặc toàn bộ segment.

Ví dụ:

| Pattern | Ý nghĩa chính |
| --- | --- |
| `org.legacy` | Cấm mọi artifact trong groupId cụ thể |
| `org.legacy:old-api` | Cấm artifactId cụ thể bất kể version |
| `org.slf4j:slf4j-simple:[2.0.12]` | Cấm đúng version 2.0.12 |
| `org.example:lib:[1.0,2.0)` | Cấm các version ≥1.0 và dưới 2.0 |
| `org.example:*:*:jar:test` | Cấm JAR artifacts của group ở test scope |
| `org.example:*:[3.0,)` | Cấm version 3.0 trở lên, nếu đó thực sự là policy |

**Lưu ý Maven/Enforcer version range:** một version viết trần như `2.0.12` ở pattern không nên mặc định được hiểu là “chỉ đúng 2.0.12”. Tài liệu `bannedDependencies` giải thích version trần có thể mang ý nghĩa **ngưỡng tối thiểu**; muốn chặn đúng một version, viết **`[2.0.12]`**.

### includes là ngoại lệ, không phải allowlist độc lập

~~~xml
<bannedDependencies>
    <excludes>
        <exclude>org.example:*</exclude>
    </excludes>
    <includes>
        <include>org.example:approved-api</include>
    </includes>
</bannedDependencies>
~~~

Ở đây `includes` loại một artifact khỏi tập đã bị `excludes` match. Nếu không có `excludes`, chỉ có `includes` **không** tạo ra chính sách “chỉ cho phép đúng danh sách này”.

Để xây allowlist nghiêm ngặt, phải thiết kế pattern/ngoại lệ chính xác và kiểm tra trên actual resolved graph.

## 7. Phụ thuộc trùng loại 1: duplicate POM declarations

Trong cùng một POM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.13</version>
    </dependency>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.12</version>
    </dependency>
</dependencies>
~~~

Đây là **hai khai báo cùng GA/type/classifier**. Chúng không trở thành “hai dependency khác nhau” chỉ vì version khác nhau.

Maven model yêu cầu dependency declarations trong một danh sách phải có unique key dựa trên:

~~~text
groupId : artifactId : type : classifier
~~~

`banDuplicatePomDependencyVersions` phát hiện dạng khai báo trùng này và làm build fail theo cấu hình. Maven 3 có thể cảnh báo ngay ở bước đọc model, nhưng **không nên dựa vào warning** làm quality gate. Maven version khác có thể xử lý invalid model nghiêm hơn.

**Điểm dễ hiểu nhầm:** tên rule chứa chữ “Versions”, nhưng vấn đề là **khai báo trùng key**, kể cả hai khai báo dùng cùng một version. Rule này không phải công cụ quét những class trùng giữa nhiều JAR.

Cách sửa:

- Giữ **một khai báo duy nhất** trong `<dependencies>`.
- Nếu chỉ muốn gom version dùng chung, đặt version trong `<dependencyManagement>` của parent/BOM phù hợp.
- Không thêm cùng dependency nhiều lần vì một lần cho compile và một lần cho test; đó thường là lỗi modeling.

## 8. Phụ thuộc trùng loại 2: duplicate classes giữa các JAR

Hai artifact có thể có coordinates khác nhau nhưng lại chứa cùng tên fully qualified class:

~~~text
library-a.jar
  └── org/apache/commons/logging/Log.class

library-b.jar
  └── org/apache/commons/logging/Log.class
~~~

Java class loading có thể chọn implementation theo thứ tự classpath/module loader, làm behavior khó dự đoán; class bytecode khác nhau có thể gây `LinkageError`, `NoSuchMethodError` hoặc runtime behavior không tương thích.

**Maven dependency mediation không giải quyết hết vấn đề này**, vì hai JAR có **GA khác nhau**. Cơ chế chọn một version cho cùng GA không tự phát hiện trùng class với artifact tên khác.

Rule phù hợp:

~~~xml
<banDuplicateClasses/>
~~~

Nhưng nó **không phải Enforcer built-in rule**. Phải thêm plugin dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>extra-enforcer-rules</artifactId>
        <version>1.12.1</version>
    </dependency>
</dependencies>
~~~

Đoạn này đặt **bên trong chính `<plugin>maven-enforcer-plugin</plugin>`**, không đặt vào project `<dependencies>`. Đây là hai classpaths khác nhau: Enforcer plugin cần nạp class của extra rule, nhưng ứng dụng Java không cần lấy extra-enforcer-rules làm runtime dependency.

### Cách kiểm soát rule

~~~xml
<banDuplicateClasses>
    <findAllDuplicates>true</findAllDuplicates>
    <ignoreWhenIdentical>false</ignoreWhenIdentical>
</banDuplicateClasses>
~~~

- `findAllDuplicates=true`: báo nhiều duplicate classes thay vì dừng khi thấy lỗi đầu.
- `ignoreWhenIdentical=false`: kể cả hai class files giống byte-for-byte cũng bị coi là trùng. Đây là hành vi nghiêm ngặt và là mặc định.
- `ignoreWhenIdentical=true`: cho phép trùng nếu bytecode giống hệt; chỉ bật khi có lý do và đánh giá runtime/classloader.
- `ignoreClasses`: danh sách exceptions theo class name/wildcard.
- `scopes`/`ignoredScopes`: điều khiển scopes được quét.
- `searchTransitive`: theo cấu hình/rule docs, có thể kiểm tra transitive dependencies.

Rule này xem **các class entries trong dependency artifacts**; không nên coi nó là một phép chứng minh tổng quát rằng application JAR/uber JAR cuối hoặc classpath của container hoàn toàn không có duplicate classes. Khi dùng shading, repackage hoặc framework loader riêng, cần bổ sung artifact/runtime checks.

## 9. Phân biệt duplicate declaration và duplicate class

| Tiêu chí | Duplicate POM dependency | Duplicate class |
| --- | --- | --- |
| Đối tượng | Khai báo dependency trong POM | Class files trong dependency JARs |
| Có nhất thiết cùng GA? | Có, theo dependency uniqueness key | Không |
| Có cần hai version khác nhau? | Không | Không |
| Maven model có thể cảnh báo? | Có | Không nhất thiết |
| Built-in Enforcer rule? | Có | Không, cần extra-enforcer-rules |
| Cách sửa | Bỏ khai báo lặp | Loại/exclude JAR trùng, đổi bridge, chỉnh packaging |
| Có bị dependencyConvergence chặn? | Không phải mục đích của rule đó | Không phải mục đích của rule đó |

**Một ca điển hình:** `commons-logging:commons-logging` và `org.springframework:spring-jcl` có thể cùng cung cấp những class thuộc namespace `org.apache.commons.logging`. Đây là **hai artifacts khác nhau** và có thể trigger duplicate-class policy nếu cả hai có mặt trong dependency set được quét.

Đừng chữa một duplicate-class violation bằng cách chỉ đặt `dependencyManagement` cho một trong hai GA: version management không làm hai JAR khác tên biến thành cùng một dependency.

## 10. Một POM Java 17 chạy được để thử Enforcer

Ta tạo một project duy nhất để minh họa rõ ràng **dependencyConvergence + bannedDependencies** rồi sửa cho build PASS. Sau đó bổ sung các phép thử độc lập để thấy duplicate POM declarations và duplicate classes.

Cấu trúc:

~~~text
dependency-policy-lab/
├── pom.xml
└── src/
    ├── main/java/dev/example/policy/App.java
    └── test/java/dev/example/policy/AppTest.java
~~~

Demo cố ý chọn:

- Direct `slf4j-api:2.0.13`.
- Direct `slf4j-simple:2.0.12`, bản này cần `slf4j-api:2.0.12` qua transitive dependency.
- Chính sách bài lab cấm `slf4j-simple:2.0.12`.

Do vậy **trạng thái đầu** có hai lỗi độc lập: version conflict và banned version. Sau đó đổi simple lên 2.0.13 để hai lỗi được giải quyết.

### 10.1. pom.xml — phiên bản cố ý FAIL tại validate

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>dependency-policy-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.12</version>
            <scope>runtime</scope>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>

                <executions>
                    <execution>
                        <id>dependency-quality-gate</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <fail>true</fail>
                            <failFast>false</failFast>
                            <rules>
                                <dependencyConvergence/>

                                <bannedDependencies>
                                    <excludes>
                                        <exclude>org.slf4j:slf4j-simple:[2.0.12]</exclude>
                                    </excludes>
                                    <searchTransitive>true</searchTransitive>
                                    <message>
                                        Lab policy: slf4j-simple 2.0.12 is banned.
                                    </message>
                                </bannedDependencies>

                                <banDuplicatePomDependencyVersions/>

                                <banDuplicateClasses>
                                    <findAllDuplicates>true</findAllDuplicates>
                                    <ignoreWhenIdentical>false</ignoreWhenIdentical>
                                </banDuplicateClasses>
                            </rules>
                        </configuration>
                    </execution>
                </executions>

                <dependencies>
                    <dependency>
                        <groupId>org.codehaus.mojo</groupId>
                        <artifactId>extra-enforcer-rules</artifactId>
                        <version>1.12.1</version>
                    </dependency>
                </dependencies>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích POM:**

- `maven-enforcer-plugin` nằm trong project `build/plugins`, nên execution được bind và **thực sự chạy**.
- `<phase>validate</phase>` làm quality gate fail sớm.
- `dependencyConvergence` so các versions theo graph.
- `bannedDependencies` cấm **chính xác** simple 2.0.12; đây là policy minh họa.
- `banDuplicatePomDependencyVersions` từ chối dependency declarations lặp trong cùng POM.
- `banDuplicateClasses` kiểm tra overlapping class files giữa dependency JARs.
- `extra-enforcer-rules` được khai báo **là dependency của Enforcer plugin**, không phải dependency của ứng dụng.
- `slf4j-simple` dùng runtime scope; `slf4j-api` dùng compile scope. Việc simple có scope runtime **không làm mất đường dẫn transitive tới slf4j-api** trong dependency-resolution graph được kiểm tra; vẫn cần version alignment.
- JUnit scope test phục vụ unit test, không tự đi vào main JAR.
- Đây là **POM cố ý FAIL**, nên không nên kỳ vọng `mvn clean verify` tạo app JAR trong trạng thái ban đầu.

### 10.2. App.java

Đường dẫn: `src/main/java/dev/example/policy/App.java`.

~~~java
package dev.example.policy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class App {
    private static final Logger LOG = LoggerFactory.getLogger(App.class);

    private App() {
    }

    public static String message(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        LOG.debug("Starting dependency policy lab");
        System.out.println(message("Maven"));
    }
}
~~~

Đoạn Java 17 dùng SLF4J API, có method `main` hợp lệ. `LOG.debug` có thể không in do default log level, nên khi nói “stdout của chương trình” ta chỉ xét dòng `System.out.println`.

**Stdout của App.main:**

~~~text
Hello, Maven
~~~

Nếu chạy qua Maven plugin, Maven còn có thể ghi các log khác; đoạn trên chỉ là **dòng do Java application in**.

### 10.3. AppTest.java

Đường dẫn: `src/test/java/dev/example/policy/AppTest.java`.

~~~java
package dev.example.policy;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsMessage() {
        assertEquals("Hello, Maven", App.message("Maven"));
    }
}
~~~

Test độc lập với stdout, kiểm tra giá trị trả về; không cần chạy application main hay tạo Spring context.

### 10.4. Lệnh tái hiện FAIL

Từ thư mục `dependency-policy-lab`:

~~~bash
mvn -version
mvn -B -ntp clean verify
~~~

Kỳ vọng Maven kết thúc **BUILD FAILURE ở validate**. Nội dung lỗi cụ thể thay đổi theo plugin version/logging, nhưng các ý cần nhìn thấy là:

~~~text
Rule ... DependencyConvergence failed ...
... slf4j-api ... 2.0.13 ...
... slf4j-api ... 2.0.12 ...
Rule ... BannedDependencies failed ...
... slf4j-simple ... 2.0.12 ...
BUILD FAILURE
~~~

Đây là **sơ đồ nội dung lỗi**, không phải log stdout được sao chép nguyên văn từ một lần chạy cụ thể.

Nếu plugin fail tại validate, Maven chưa thực hiện compiler/test lifecycle goals; vì vậy chưa thể đánh giá `AppTest`. **Content QA của dependency policy** và **unit test QA** là hai cổng khác nhau.

## 11. Xác nhận nguyên nhân bằng dependency:tree

Dùng Maven Dependency Plugin với version được ghim:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose
~~~

Một phiên bản chỉ xem SLF4J:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose -Dincludes=org.slf4j
~~~

Flag `-Dverbose` của goal `dependency:tree` yêu cầu hiển thị cả các dependency nodes bị omitted do conflicts/duplicates theo khả năng của plugin.

Đoạn output dự kiến có dạng:

~~~text
dev.example:dependency-policy-lab:jar:1.0.0
+- org.slf4j:slf4j-api:jar:2.0.13:compile
+- org.slf4j:slf4j-simple:jar:2.0.12:runtime
|  \- (org.slf4j:slf4j-api:jar:2.0.12:runtime - omitted for conflict with 2.0.13)
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
~~~

Sơ đồ đã rút gọn nhánh JUnit để tập trung vào conflict; không phải cam kết output `dependency:tree` đúng từng dấu cách và thứ tự trên mọi Maven version.

**Đọc graph đúng:**

- `slf4j-api:2.0.13` direct là version được dùng theo mediation.
- `slf4j-api:2.0.12` là requirement xuất hiện qua simple 2.0.12.
- Dòng `omitted for conflict` không có nghĩa requirement này biến mất khỏi lý do rule convergence báo lỗi.
- `bannedDependencies` là kiểm tra độc lập: chính artifact `slf4j-simple:2.0.12` đang hiện diện và bị policy cấm.

Nếu muốn xuất tree ra file:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose -DoutputFile=target/dependency-tree.txt
~~~

Một số plugin goals được gọi trực tiếp có thể không chạy `validate` của project trước. Đừng dùng việc dependency:tree thành công để suy luận Enforcer quality gate PASS; hai goals phục vụ mục đích khác nhau.

## 12. Sửa để convergence và bannedDependencies cùng PASS

Trong POM lab, chỉ thay dependency:

**Trước:**

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.12</version>
    <scope>runtime</scope>
</dependency>
~~~

**Sau:**

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.13</version>
    <scope>runtime</scope>
</dependency>
~~~

Giữ `slf4j-api:2.0.13` direct. Bây giờ hai requirement routes về API thống nhất ở version 2.0.13. Đồng thời không còn `slf4j-simple:2.0.12` nằm trong phạm vi cấm.

Chạy lại:

~~~bash
mvn -B -ntp clean verify
~~~

Khi project/repositories hợp lệ:

- Enforcer rules PASS.
- Main classes được compile bằng Java 17.
- `AppTest` PASS.
- Main JAR được tạo trong `target/dependency-policy-lab-1.0.0.jar`.
- Maven kết thúc `BUILD SUCCESS`.

**Chạy class ứng dụng qua Maven Exec Plugin** sau khi package:

~~~bash
mvn -B -ntp -q org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=dev.example.policy.App
~~~

Dòng ứng dụng in:

~~~text
Hello, Maven
~~~

Đây là mã chạy trực tiếp từ Maven project classpath thông qua exec goal, **không chứng minh main JAR là fat/executable JAR**. Nếu muốn phân phối một CLI độc lập, cần thêm manifest và runtime dependency distribution; đó là vấn đề packaging riêng.

### Một cách điều phối version tốt hơn

Trong dự án nhiều modules, dùng property:

~~~xml
<properties>
    <slf4j.version>2.0.13</slf4j.version>
</properties>
~~~

rồi tham chiếu:

~~~xml
<version>${slf4j.version}</version>
~~~

cho các SLF4J artifacts direct. Cách này hữu ích với một nhóm thư viện có yêu cầu align version; nhưng khi có BOM/parent dependency management phù hợp, hãy ưu tiên chiến lược chung để tránh nhiều nguồn version truth.

## 13. Fix bằng dependencyManagement hoặc BOM

Nếu dependency graph lớn, một conflict có thể tới từ các thư viện bạn không kiểm soát. Maven cho phép project quản lý version được chọn cho transitive dependencies bằng `dependencyManagement`.

Ví dụ đoạn POM minh họa:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Ý nghĩa: khi dependency `slf4j-api` xuất hiện trong resolved project graph, version 2.0.13 được quản lý theo Maven rules.

**Nhưng:** chỉ pin API không tự khiến một provider/adapter/library cũ trở nên binary-compatible hoặc được phép bởi policy. Nếu `slf4j-simple:2.0.12` là artifact bị cấm, phải **loại hoặc nâng chính artifact đó**, không chỉ pin API version.

Với **BOM**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **ví dụ về cấu trúc import BOM**, không phải một BOM được phát hành thật tại `org.example:platform-bom:1.0.0`. Dùng coordinates BOM có thật của framework/platform, ghim version và xem effective POM để chắc chắn rule management đã áp dụng.

**Các nguyên tắc:**

- BOM giúp quản lý các versions tương thích theo một tập có chủ đích.
- `dependencyManagement` **không tự thêm dependency** vào project; nó quản lý version khi dependency được khai báo/được đưa vào graph.
- BOM và parent management không điều khiển dependency của Maven plugins giống như project dependencies.
- Nếu nhiều BOM quản lý cùng artifact, cần hiểu ưu tiên declaration/inheritance/import order và kiểm tra effective POM.
- Nếu rule convergence vẫn FAIL sau BOM import, xem các paths thật; đừng vội thêm broad excludes vào Enforcer.

## 14. Fix bằng exclusions khi dependency bắc cầu không cần thiết

Giả sử library A kéo theo artifact `legacy-logging` mà ứng dụng đã thay thế bằng một logging implementation khác. Bạn có thể loại transitive dependency này khỏi đúng path:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>library-a</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.legacy</groupId>
            <artifactId>legacy-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là **POM fragment minh họa**, không phải tọa độ chắc chắn tồn tại trên Maven Central.

Exclusion xử lý **một đường dẫn dependency**. Nếu một library khác vẫn kéo `legacy-logging` vào graph, artifact có thể tiếp tục xuất hiện; cần kiểm tra các paths khác.

**Cảnh báo:** Exclude bừa có thể tạo runtime `ClassNotFoundException`, `NoClassDefFoundError` hoặc lỗi service provider vì thư viện thực sự cần artifact ấy. Luôn xem dependency tree, chạy tests và bảo đảm một replacement tương thích khi cần.

Exclusion cũng không sửa được vi phạm **duplicate declaration** do cùng dependency được ghi hai lần trong POM. Khi ấy phải sửa chính các khai báo.

## 15. Thử lỗi duplicate POM declarations

Sau khi **đã sửa lab sang slf4j-simple 2.0.13** và `mvn clean verify` PASS, thử bổ sung **tạm thời** một khai báo thứ hai cho `slf4j-api` trong cùng `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.13</version>
</dependency>
~~~

Đây là **khai báo thêm thứ hai**, không phải yêu cầu thay bản đã có.

Chạy:

~~~bash
mvn -B -ntp validate
~~~

Maven 3 có thể in warning về dependency uniqueness và Enforcer rule `banDuplicatePomDependencyVersions` làm build fail. Cách hiển thị lỗi phụ thuộc Maven version, nhưng bạn cần đọc thấy duplicate key `org.slf4j:slf4j-api:jar` trong ngữ cảnh project.

**Sửa:** xóa khai báo thêm, giữ đúng một dependency entry. Không cố “sửa” bằng cách đổi version ở khai báo thứ hai: **hai khai báo cùng key vẫn trùng**.

Sau thử nghiệm, chạy lại `mvn clean verify` để xác nhận POM đã trở về trạng thái sạch.

## 16. Thử lỗi duplicate classes từ hai artifact khác GA

Một ví dụ thường gặp liên quan logging:

~~~xml
<dependency>
    <groupId>commons-logging</groupId>
    <artifactId>commons-logging</artifactId>
    <version>1.2</version>
</dependency>

<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-jcl</artifactId>
    <version>6.1.13</version>
</dependency>
~~~

Đây là **hai khai báo thêm có chủ đích**, dùng cho một phép thử độc lập **sau khi lab cơ sở đã PASS**.

Hai thư viện có chức năng quanh Commons Logging API; bản JAR cụ thể có thể chứa overlapping classes trong namespace `org.apache.commons.logging`. Khi cả hai có mặt trong dependencies được `banDuplicateClasses` quét, rule có thể báo class files trùng. Không nhầm lỗi này với hai version của cùng `groupId:artifactId`: ở đây **GA khác nhau**, nên version mediation không tự chọn bỏ một trong hai.

Chạy:

~~~bash
mvn -B -ntp validate
~~~

Nếu rule in duplicate-class names, đọc hai artifact paths trong thông báo. Bạn có thể kiểm tra file bytes/entry names trước khi kết luận:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=commons-logging,org.springframework:spring-jcl
~~~

Lệnh tree giúp xác nhận hai artifacts có mặt, nhưng **không chứng minh tên class trùng**. Muốn kiểm tra chính archive, dùng `jar tf` trên đúng JAR files đã resolve:

~~~bash
jar tf path/to/commons-logging-1.2.jar
jar tf path/to/spring-jcl-6.1.13.jar
~~~

Đường dẫn ở ví dụ chỉ là **ký hiệu**: thay bằng file thực từ local Maven repository, không chạy nguyên dòng rồi trông chờ tồn tại file `path/to/...`.

**Sửa:** nếu project dùng Spring, thông thường chọn bridge/implementation logging phù hợp theo dependency policy của stack; loại `commons-logging` thừa khỏi direct dependencies hoặc exclusion trên đúng transitive path. Đừng xóa `spring-jcl` bừa nếu Spring Framework cần nó.

Sau phép thử, bỏ hai khai báo vừa thêm hoặc giữ đúng dependency thật cần thiết, rồi chạy full `clean verify`.

## 17. Ignore duplicate class: dùng rất hạn chế

Nếu có trường hợp đặc biệt đã được phân tích, rule cho phép:

~~~xml
<banDuplicateClasses>
    <ignoreClasses>
        <ignoreClass>com.example.generated.SomeClass</ignoreClass>
    </ignoreClasses>
    <findAllDuplicates>true</findAllDuplicates>
    <ignoreWhenIdentical>false</ignoreWhenIdentical>
</banDuplicateClasses>
~~~

Đây là đoạn cấu hình con của Enforcer rule.

**Không dùng**:

~~~xml
<ignoreClass>*</ignoreClass>
~~~

để qua cửa kiểm tra, vì điều đó làm rule gần như mất giá trị.

Và:

~~~xml
<ignoreWhenIdentical>true</ignoreWhenIdentical>
~~~

không có nghĩa “hai JAR là như nhau”. Nó chỉ cho phép những class files có bytes giống hệt nhau vượt qua **một loại kiểm tra**. Các resources, services, signatures, provenance, license hay toàn bộ dependency versions vẫn có thể khác.

### Ignore theo dependency

MojoHaus còn hỗ trợ chỉ định dependency-specific ignore classes, nhưng configuration phức tạp hơn và nên dựa vào chính xác JAR/GA đang gây conflict. Trong multi-module parent-child, muốn child **append** ignore entries thay vì ghi đè danh sách của parent, tài liệu mô tả dùng `combine.children="append"` trên các collection elements như `ignoreClasses`.

**Chính sách thực tế:** ưu tiên sửa dependency graph. Exceptions chỉ dùng khi có lý do ghi lại, phạm vi hẹp và kiểm thử runtime bổ sung.

## 18. requireUpperBoundDeps khác dependencyConvergence

Hai rule nghe gần giống nhưng điều kiện khác:

**dependencyConvergence** yêu cầu mọi paths dẫn tới cùng dependency version thống nhất.

**requireUpperBoundDeps** yêu cầu version được chọn **không thấp hơn version cao nhất gặp trên các transitive paths** theo logic rule. Nó không đòi tất cả path versions phải giống nhau.

Ví dụ:

~~~text
app
├── api:2.0.13  (direct, được chọn)
└── helper:1.0
    └── api:2.0.12  (transitive requirement)
~~~

Trong điều kiện này:

- `dependencyConvergence` **FAIL**, vì 2.0.12 khác 2.0.13.
- `requireUpperBoundDeps` có thể **PASS** nếu 2.0.13 là upper bound cao nhất được chọn và không có yêu cầu cao hơn.

Ngược lại:

~~~text
app
├── api:2.0.12  (direct, được chọn)
└── helper:1.0
    └── api:2.0.13  (transitive requirement)
~~~

thì version được chọn thấp hơn requirement 2.0.13. `requireUpperBoundDeps` có thể FAIL, và `dependencyConvergence` cũng FAIL.

### Cấu hình tùy chọn

~~~xml
<requireUpperBoundDeps/>
~~~

Rule này hữu ích như một **hàng rào tránh downgrade transitive dependencies**, nhưng không thay thế policy convergence nghiêm ngặt. Chọn rule nào phụ thuộc khả năng tương thích, nhu cầu reproducibility và mức noise chấp nhận.

## 19. banDynamicVersions và các version khó tái lập

Ngoài danh sách banned artifacts cụ thể, Maven Enforcer còn có `banDynamicVersions`. Rule này có thể chặn các cách khai báo version làm build thay đổi theo repository metadata, ví dụ:

- Version ranges như `[1.0,2.0)` khi được dùng như **dependency version declaration**.
- Special placeholders `LATEST` hoặc `RELEASE`.
- `-SNAPSHOT` theo cấu hình mặc định của rule.

Cấu hình ví dụ:

~~~xml
<banDynamicVersions/>
~~~

**Đừng nhầm:** version range ở một **`bannedDependencies` rule pattern** mô tả tập phiên bản **bị cấm**; version range trong project `<dependency><version>...</version>` mô tả **cách chọn dependency**. Hai vị trí có mục đích và hiệu lực khác nhau.

Nếu dự án đang phát triển cần SNAPSHOT nội bộ, `banDynamicVersions` có những options như `allowSnapshots`; điều chỉnh minh bạch theo policy thay vì bỏ toàn bộ quality gate.

## 20. Chính sách với scope, optional và transitive dependencies

Maven dependency scope ảnh hưởng classpath và tập dependency có liên quan:

- `compile`: classpath compile/runtime theo Maven rules.
- `runtime`: cần ở runtime nhưng không nhất thiết cần để compile.
- `provided`: cần khi compile nhưng dự kiến được môi trường cung cấp ở runtime.
- `test`: chỉ dành cho test compilation/execution.
- `optional`: ảnh hưởng tính lan truyền dependency tới project tiêu thụ, không tự nghĩa là dependency vô hại.

Các rule có **default scope semantics riêng**:

- `dependencyConvergence` theo docs mặc định loại provided/test khỏi convergence errors.
- `bannedDependencies` mặc định `searchTransitive=true`, còn pattern có thể chỉ định scope.
- `banDuplicateClasses` có `scopes`, `ignoredScopes`, `ignoreOptionals` và `searchTransitive`.

**Đừng suy từ một rule sang rule khác**. Nếu CI muốn kiểm tra cả test dependency graph, cấu hình cụ thể và xác minh bằng một test fixture tạo vi phạm ở test scope.

Với ứng dụng chạy trong servlet container, một dependency provided có thể quan trọng nhưng nằm ngoài deploy artifact. Có thể cần quality gate riêng cho platform/runtime classpath.

## 21. Một lưu ý về dependencyManagement và plugin dependencies

Một parent POM có:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- project dependencies -->
    </dependencies>
</dependencyManagement>
~~~

quản lý **project dependencies**, không tự áp version tương ứng lên các thư viện mà **Maven plugins** sử dụng.

Ví dụ `extra-enforcer-rules` nằm trong:

~~~xml
<plugin>
    <artifactId>maven-enforcer-plugin</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>extra-enforcer-rules</artifactId>
            <version>1.12.1</version>
        </dependency>
    </dependencies>
</plugin>
~~~

Đó là một **plugin dependency** để Maven tải custom rule implementation. Không khai báo nó trong application dependencies rồi kỳ vọng Enforcer có thể tự tìm extra rule từ app classpath.

Nếu cần kiểm soát plugin security và versions, dùng `pluginManagement`, versions explicit và các rules/plugins phù hợp dành riêng cho plugins.

## 22. Multi-module Reactor: đặt quality gate ở đâu?

Một repository có root parent/aggregator và nhiều child modules:

~~~text
platform/
├── pom.xml                  (packaging pom)
├── core/
│   └── pom.xml              (packaging jar)
└── service/
    └── pom.xml              (packaging jar)
~~~

Nếu muốn mọi module thực thi rule, có thể khai báo Enforcer trong **root `<build><plugins>`** để các module con kế thừa execution, hoặc thiết kế plugin configuration ở từng module theo nhu cầu.

Lưu ý:

1. Root packaging `pom` vẫn có thể chạy Enforcer tại validate. Nếu root không có project dependencies, dependency rules của root có thể ít việc phải làm.
2. Parent `<pluginManagement>` **không đủ** để bảo đảm execution ở child nếu child/parent không khai báo plugin để sử dụng.
3. Goal `enforce` chạy **một lần trên mỗi module** theo chính plugin docs; không phải một rule toàn cục quét gộp mọi classpath giữa các modules.
4. Một module có graph PASS không chứng minh module khác PASS.
5. `mvn -N validate` từ root aggregator **chỉ check root project**, không tự thực thi Enforcer của từng child.
6. Cần full reactor build trong CI, hoặc một lựa chọn `-pl ... -am` đủ bao phủ modules bắt buộc.
7. Nếu child override rule configuration, cần kiểm tra Maven plugin inheritance/merge và effective POM. Đừng vô tình xóa `bannedDependencies` khi muốn thêm một exception cho `banDuplicateClasses`.

### Mẫu parent POM — phần plugin

Đoạn sau được đặt trong root `<build><plugins>`, không phải một POM độc lập:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>enforce-shared-policy</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                    <banDuplicatePomDependencyVersions/>
                    <bannedDependencies>
                        <excludes>
                            <exclude>org.legacy:old-library</exclude>
                        </excludes>
                    </bannedDependencies>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Ở đây `org.legacy:old-library` là **tọa độ minh họa** cho policy, không phải artifact được khẳng định đang tồn tại. Nếu thêm extra rule banDuplicateClasses, phải thêm plugin dependency phù hợp vào cùng Enforcer plugin.

## 23. Tích hợp thành CI quality gate

Một pipeline mức ý tưởng:

~~~text
Checkout source
       |
       v
Pin JDK 17 + Maven version (wrapper nếu có)
       |
       v
mvn -B -ntp clean verify
       |
       +-- validate
       |     └-- Maven Enforcer
       |         ├-- dependencyConvergence
       |         ├-- bannedDependencies
       |         ├-- banDuplicatePomDependencyVersions
       |         └-- banDuplicateClasses
       |
       +-- compile/test/package nếu validate PASS
       |
       v
Publish artifact chỉ nếu toàn bộ quality gates PASS
~~~

### Điều phải bảo đảm

- CI thật sự chạy `enforcer:enforce`; đọc log plugin goal/execution.
- `fail=true` trong môi trường release.
- Không chèn `-Denforcer.skip=true` trong lệnh build chính thức.
- Không dùng Maven offline/local cache như bằng chứng duy nhất về dependency health; artifacts đã được resolve có thể cũ.
- Maven Wrapper và JDK được pin khi cần reproducibility.
- Luôn chạy tests và packaging checks sau khi policy PASS.
- Nếu pipeline chỉ chạy `mvn -N validate` ở root, phải có job riêng check tất cả modules.
- Rule exceptions phải được review, có reason, có owner và được rà soát định kỳ.

**Cổng chất lượng dependency không thay thế vulnerability scanning, SBOM, license audits hoặc runtime integration testing.** Enforcer so version/coordinates/classes theo rules; CVE và licensing cần công cụ/quy trình dữ liệu riêng.

## 24. Cách đọc và phân loại một lỗi Enforcer

Một dòng Maven thường chứa tên rule:

~~~text
Rule ... DependencyConvergence failed
Rule ... BannedDependencies failed
Rule ... BanDuplicatePomDependencyVersions failed
Rule ... BanDuplicateClasses failed
~~~

Đây là **dạng thông điệp rút gọn**, không phải stdout nguyên văn của một lần chạy thật.

Thứ tự xử lý nên là:

1. Đọc đầy đủ **rule name**, module và error details.
2. Nếu convergence: ghi lại tất cả dependency paths, versions và nơi version được quản lý.
3. Nếu banned dependency: ghi lại pattern match, dependency direct/transitive và scope.
4. Nếu duplicate POM: tìm khai báo lặp trong POM của module đang fail.
5. Nếu duplicate class: tìm **hai hoặc nhiều JAR** cung cấp class bị trùng, sau đó quyết định library nào được phép.
6. Kiểm tra effective POM, BOM/parent, active profiles và managed versions.
7. Sửa nguyên nhân tại đúng POM/dependency path.
8. Chạy `dependency:tree` để kiểm chứng graph.
9. Chạy lại `mvn clean verify` trên toàn module scope liên quan.
10. Với thay đổi quan trọng, chạy application/integration tests để xác nhận runtime behavior.

Đừng chỉ chụp dòng cuối `BUILD FAILURE`. Thông tin chính thường nằm ở vài chục dòng phía trên, đặc biệt các paths được Enforcer liệt kê.

## 25. Khi dependency:tree chưa đủ

`dependency:tree` giúp nhìn dependencies/version mediation; nó **không đọc nội dung mọi class file** bên trong JAR. Vì thế:

- Convergence/banned artifacts: tree rất hữu ích.
- Duplicate declarations: cần xem raw/effective POM và model warning.
- Duplicate classes: cần đọc Enforcer duplicate-class output và có thể dùng `jar tf`/bytecode inspection.
- Runtime classpath khác test/compile: cần xem packaging, `java -cp`/`java -jar`, Boot loader hoặc container distribution.
- Maven plugins dùng classloader riêng: project dependency tree không phản ánh đầy đủ plugin dependencies.

Với build reproducibility, ghi lại actual dependency report và Maven versions để tránh tranh luận trên một tree được in từ profile/build environment khác.

### Lệnh chẩn đoán hữu ích

~~~bash
mvn -version

mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml

mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose

mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=org.slf4j

mvn -B -ntp clean verify
~~~

Đọc output theo module, nếu project multi-module. Không lấy dependency tree của parent packaging `pom` rồi cho rằng đó là tree của mọi child module.

## 26. Các cách “chữa lỗi” sai thường gặp

| Cách xử lý sai | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Đặt `-Denforcer.skip=true` vĩnh viễn | Bỏ quality gate | Sửa dependency graph và bật lại Enforcer |
| Đặt `<fail>false</fail>` trong CI | Error chỉ thành warning | Cho build fail có kiểm soát |
| Exclude mọi artifact ở dependencyConvergence | Che conflicts thật | Align versions hoặc exception rất hẹp |
| Chỉ pin slf4j-api nhưng để banned simple cũ | Banned artifact vẫn tồn tại | Upgrade/remove provider bị cấm |
| Chỉ đổi version của declaration lặp | Duplicate POM key vẫn trùng | Xóa một declaration |
| Chỉ sửa dependencyManagement khi 2 GA khác nhau chứa class trùng | Không loại hai JAR khác coordinates | Exclude/replace một dependency |
| `ignoreWhenIdentical=true` không có lý do | Che duplicate class policy | Giữ strict mặc định hoặc ghi exception có kiểm soát |
| Dùng exclusion để xóa dependency cần thiết | Có thể lỗi runtime | Xác nhận replacement/compatibility |
| Giả định compile success nghĩa convergence PASS | Maven mediation có thể che xung đột | Chạy Enforcer validate |
| Giả định Enforcer là CVE scanner | Rule không tự biết mọi advisory mới | SBOM/vulnerability scan riêng |
| Chỉ check root POM trong multi-module repo | Children có graph khác nhau | Full reactor verify |
| Đọc tree của profile sai | Resolved graph khác production | Chạy đúng profiles/settings |
| Dùng version range trong banned rule nhưng hiểu sai ý nghĩa | Cấm nhiều/hẹp hơn dự kiến | Dùng `[exact]` hay range syntax chính xác |
| Exclude tràn lan thư viện bridge | Lỗi logging/service provider | Chọn logging stack thống nhất |
| Đưa extra-enforcer-rules vào project dependencies | Enforcer plugin không nhất thiết nạp được rule | Đặt dưới Maven Enforcer plugin dependencies |

## 27. Thực hành kiểm chứng policy theo từng bước

Để tránh nhiều lỗi chồng nhau làm khó học, chạy theo trình tự:

1. Tạo POM/Java/test đúng mục 10, với simple **2.0.12**.
2. Chạy `mvn clean verify`. Xác nhận **BUILD FAILURE tại validate**, đọc convergence và bannedDependencies.
3. Chạy `dependency:tree -Dverbose` bằng goal đã pin version để quan sát hai đường dẫn slf4j-api.
4. Sửa simple thành **2.0.13**. Chạy `mvn clean verify` và xác nhận PASS.
5. Chạy ứng dụng bằng Exec Plugin và nhìn dòng `Hello, Maven`.
6. Thêm một duplicate declaration `slf4j-api` (mục 15), chạy `mvn validate`, quan sát duplicate POM rule. Xóa declaration thừa.
7. Thêm `commons-logging` và `spring-jcl` (mục 16), chạy `mvn validate`, kiểm tra duplicate-class error; xác minh JAR entries và bỏ dependency thừa.
8. Sau mỗi phép thử âm, khôi phục POM sạch; cuối cùng `mvn clean verify` phải PASS.
9. Nếu muốn xem khác biệt `requireUpperBoundDeps`, thêm rule này tạm thời trong một branch riêng rồi so version path scenarios, không pha lẫn với bản baseline.
10. Tích hợp các rules thành CI gate và giữ ngoại lệ hẹp.

**Lưu ý:** Bài lab dùng artifact/version thật trên Maven Central để minh họa. Nội dung log cụ thể phụ thuộc Maven/plugin version, repository mirror, active profiles, platform và cache. Không nên hard-code toàn bộ error text vào test mà nên xác minh **rule + coordinates + cause**.

## 28. Bài tập có đáp án

1. **dependencyConvergence khác Maven mediation ở đâu?**  
   **Đáp án:** Mediation chọn version dùng; convergence yêu cầu paths nhất quán version.

2. **Nearest definition nghĩa là gì?**  
   **Đáp án:** Version có dependency path gần root hơn thường thắng.

3. **Hai đường dẫn cùng độ sâu, version nào thắng trong mediation?**  
   **Đáp án:** Theo nguyên tắc first declaration, dependency khai báo trước thường thắng.

4. **slf4j-api direct 2.0.13 và transitive 2.0.12 có thể compile không?**  
   **Đáp án:** Có thể, nhưng dependencyConvergence vẫn FAIL.

5. **Cấm đúng version 2.0.12 bằng pattern gì?**  
   **Đáp án:** Dùng `org.slf4j:slf4j-simple:[2.0.12]`.

6. **Pattern version trần `2.0.12` có nên hiểu là exact version?**  
   **Đáp án:** Không; dùng bracket syntax để tránh ý nghĩa range/ngưỡng ngoài dự kiến.

7. **bannedDependencies có kiểm tra transitive deps theo mặc định không?**  
   **Đáp án:** Có, `searchTransitive=true`.

8. **includes khi không có excludes có thành allowlist không?**  
   **Đáp án:** Không; includes là ngoại lệ cho phần excludes.

9. **Rule nào chặn hai lần khai báo cùng GA/type/classifier?**  
   **Đáp án:** `banDuplicatePomDependencyVersions`.

10. **Nếu hai declarations có cùng version, có còn trùng không?**  
    **Đáp án:** Có, khi cùng dependency uniqueness key.

11. **Rule nào kiểm tra hai JAR chứa cùng class?**  
    **Đáp án:** `banDuplicateClasses` từ MojoHaus Extra Enforcer Rules.

12. **banDuplicateClasses có thuộc built-in Enforcer không?**  
    **Đáp án:** Không, phải thêm plugin dependency `extra-enforcer-rules`.

13. **Đặt extra-enforcer-rules ở dependencies nào?**  
    **Đáp án:** Dưới `maven-enforcer-plugin/<dependencies>`, không dưới application dependencies.

14. **banDuplicateClasses có thể chỉ phát hiện vi phạm trên cùng GA không?**  
    **Đáp án:** Không, class trùng có thể đến từ JAR khác group/artifact.

15. **ignoreWhenIdentical=true nghĩa là gì?**  
    **Đáp án:** Cho qua duplicate class nếu bytes class giống hệt; không chứng minh JARs hoàn toàn giống.

16. **Vì sao pin slf4j-api không tự sửa banned slf4j-simple?**  
    **Đáp án:** Banned rule match chính simple artifact/version.

17. **dependencyManagement có tự thêm thư viện vào project không?**  
    **Đáp án:** Không, nó quản lý version khi dependency tham gia graph.

18. **BOM import thường cần type và scope nào?**  
    **Đáp án:** `<type>pom</type>` và `<scope>import</scope>` trong dependencyManagement.

19. **Exclusion loại dependency ở đâu?**  
    **Đáp án:** Ở path của dependency khai báo exclusion; paths khác có thể vẫn đưa artifact vào.

20. **requireUpperBoundDeps khác convergence ra sao?**  
    **Đáp án:** UpperBound yêu cầu resolved version không thấp hơn requirement cao nhất, còn convergence muốn các paths có cùng version.

21. **Rule nào chặn ranges/SNAPSHOT dynamic theo policy?**  
    **Đáp án:** `banDynamicVersions`, với options nếu cần cho phép exceptions.

22. **Phase phù hợp để enforce fail sớm?**  
    **Đáp án:** `validate`.

23. **Đặt plugin chỉ trong pluginManagement có chắc goal chạy không?**  
    **Đáp án:** Không, cần plugin được dùng/bind execution.

24. **Root Maven multi-module PASS có chắc mọi child dependency graph đã check?**  
    **Đáp án:** Chỉ khi Enforcer thật sự được bind/chạy trên children theo reactor selection.

25. **Lệnh nào hiển thị omitted dependency conflict nodes?**  
    **Đáp án:** `dependency:tree -Dverbose` với Maven Dependency Plugin hỗ trợ.

26. **Maven Enforcer có tự vá CVE không?**  
    **Đáp án:** Không; rules tuân thủ policy, không thay thế scanner và remediation.

27. **Vì sao test classpath và runtime classpath có thể khác?**  
    **Đáp án:** Maven scopes, packaging, optional/exclusions và environment quyết định tập dependency khác nhau.

28. **Hai JAR có cùng class nhưng API version thống nhất thì convergence có bắt lỗi đó không?**  
    **Đáp án:** Không nhất thiết; dùng duplicate-class detection.

29. **Có nên để `-Denforcer.skip=true` trong CI chính thức?**  
    **Đáp án:** Không, trừ quyết định ngoại lệ có kiểm soát; thông thường phải khôi phục gate.

30. **Điều quan trọng nhất của dependency quality gate?**  
    **Đáp án:** Nhìn đúng resolved graph, chặn sớm vi phạm, sửa nguyên nhân và chạy lại full build/tests.

## 29. Checklist áp dụng vào dự án thật

- [ ] Ghìm Maven/JDK versions hoặc dùng Maven Wrapper phù hợp.
- [ ] Xác định rõ dependency quality policy của tổ chức: convergence, banned, duplicate declarations, duplicate classes.
- [ ] Đặt Enforcer Plugin vào `build/plugins` và bind goal vào `validate`.
- [ ] Dùng một Enforcer version được kiểm chứng với Maven đang chạy.
- [ ] Thêm `extra-enforcer-rules` làm plugin dependency nếu dùng banDuplicateClasses.
- [ ] Ưu tiên `fail=true` và không skip trong CI release.
- [ ] Chạy `dependency:tree -Dverbose` để chẩn đoán xung đột versions.
- [ ] Dùng `dependencyManagement`/BOM khi cần căn chỉnh versions theo một chính sách.
- [ ] Không dùng excludes bừa bãi để che các transitive dependencies bắt buộc.
- [ ] Dùng brackets cho **exact version** ở bannedDependencies patterns.
- [ ] Đặt `searchTransitive` phù hợp với mục tiêu policy.
- [ ] Không nhầm duplicate POM declarations với duplicate classes.
- [ ] Xác minh class collisions bằng artifact paths/entry names nếu rule báo lỗi.
- [ ] Dùng `ignoreClasses` hoặc `ignoreWhenIdentical` chỉ khi có tài liệu đánh giá và exception hẹp.
- [ ] Kiểm tra Scope/Optional/test/provided semantics riêng của từng rule.
- [ ] Khi multi-module, Enforcer thực sự chạy ở mọi module cần kiểm tra.
- [ ] Không để `-N` hoặc `-pl` chọn thiếu modules trong full CI quality job.
- [ ] Theo dõi effective POM, BOM import order và active profiles.
- [ ] Chạy unit/integration tests sau khi Enforcer PASS.
- [ ] Kiểm tra artifact/runtime classpath khi dùng Shade, Spring Boot hoặc container packaging.
- [ ] Dùng SBOM, vulnerability scanning và license checks bổ sung; Enforcer không thay thế chúng.
- [ ] Đưa exceptions có owner, reason và ngày xem lại vào code review.
- [ ] Không coi BUILD SUCCESS khi Enforcer bị skip là quality gate PASS.
- [ ] Ghi lại violated coordinates, dependency paths và cách sửa trong PR.
- [ ] Giữ phiên bản policy nhất quán giữa local, PR CI và release pipeline.

## 30. Tài liệu tham khảo chính thức

- [Apache Maven — Dependency Convergence Rule](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html): paths, version consistency, SNAPSHOT uniqueness, includes/excludes/scopes.
- [Apache Maven — Banned Dependencies Rule](https://maven.apache.org/enforcer/enforcer-rules/bannedDependencies.html): excludes/includes, pattern matching, version ranges, transitive checks.
- [Apache Maven — Ban Duplicate POM Dependency Versions](https://maven.apache.org/enforcer/enforcer-rules/banDuplicatePomDependencyVersions.html): duplicate declarations theo GA/type/classifier.
- [Apache Maven — Require Upper Bound Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html): constraint về version cao nhất.
- [Apache Maven — Ban Dynamic Versions](https://maven.apache.org/enforcer/enforcer-rules/banDynamicVersions.html): tránh ranges/latest/release/SNAPSHOT theo policy.
- [Apache Maven — Enforcer Plugin Usage](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html): cách bind goals, fail/failFast/skip.
- [Apache Maven — Enforcer Enforce Goal](https://maven.apache.org/enforcer/maven-enforcer-plugin/enforce-mojo.html): default phase validate và cấu hình goal.
- [MojoHaus — Extra Enforcer Rules Usage](https://www.mojohaus.org/extra-enforcer-rules/usage.html): khai báo `extra-enforcer-rules` làm plugin dependency.
- [MojoHaus — Ban Duplicate Classes](https://www.mojohaus.org/extra-enforcer-rules/banDuplicateClasses.html): detection, ignoreClasses, scopes, ignoreWhenIdentical, inheritance.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, nearest definition, dependencyManagement và BOM.
- [Apache Maven — Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): tree, verbose, includes, output formats.
- [Apache Maven — Introduction to POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): POM model, dependencies và inheritance.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): API/provider version compatibility và logging provider guidance.
- [Maven Central — slf4j-simple 2.0.12](https://central.sonatype.com/artifact/org.slf4j/slf4j-simple/2.0.12): dependency POM của phiên bản dùng trong lab.
- [Maven Central — slf4j-simple 2.0.13](https://central.sonatype.com/artifact/org.slf4j/slf4j-simple/2.0.13): POM sau khi căn chỉnh version.

**Kết luận:** Cổng chất lượng dependency tốt phải xử lý **ba trục độc lập**: đồng nhất version trên mọi đường dẫn (`dependencyConvergence`), tuân thủ chính sách phiên bản/artifact (`bannedDependencies`), và tránh khai báo/class trùng (`banDuplicatePomDependencyVersions`, `banDuplicateClasses`). Maven Enforcer giúp **chặn lỗi sớm ở validate**, nhưng chỉ đạt chất lượng thật khi bạn đọc dependency graph, sửa nguyên nhân, giữ exceptions hẹp và kiểm chứng lại compile/test/runtime của artifact.

# Bước học tiếp theo sau Java Core JDK Tooling

Bài này thuộc nhóm **Tổng kết JDK Tooling**. Sau khi biết cài JDK, kiểm tra JAVA_HOME/PATH, biên dịch bằng javac, chạy bằng java, đóng gói bằng jar và chẩn đoán bằng công cụ JDK, bước tiếp theo là dùng các kỹ năng đó để xây dựng một ứng dụng có cấu trúc, có test, quản lý dependency và có thể bàn giao cho người khác.

Mục tiêu không phải học framework càng sớm càng tốt. Hãy hoàn thành một vòng đời phát triển nhỏ trước: hiểu Java language, tổ chức source, tự động hóa build, kiểm thử, debug, đóng gói và chạy artifact. Nền tảng này dùng được cho backend, desktop, cloud, data processing và các hướng chuyên sâu về JVM.

## 1. Đích đến sau JDK Tooling

Một project Java cơ bản đi qua các bước:

~~~text
Yêu cầu
  |
  v
Thiết kế class, package và API
  |
  v
Viết source Java
  |
  v
Biên dịch và kiểm thử
  |
  v
Quản lý dependency và build
  |
  v
Đóng gói JAR hoặc distribution
  |
  v
Chạy thử artifact
  |
  v
Ghi tài liệu và phát hành
~~~

Bạn đã sẵn sàng khi có thể tự giải thích vì sao cần JDK, source được biên dịch thành bytecode thế nào, build tool chọn dependency ra sao, test chạy ở bước nào và file nào thực sự được đưa tới người dùng.

## 2. Ôn lại kiến thức đã có

Trước khi học phần mới, hãy tự làm một bài kiểm tra ngắn:

- Dùng java -version và javac -version để xác định runtime/compiler.
- Giải thích JAVA_HOME và PATH, biết tìm executable bằng where.exe hoặc command -v.
- Biên dịch source với javac --release 17.
- Chạy class bằng java -cp và hiểu classpath.
- Tạo JAR bằng jar, xem entry và manifest.
- Dùng javap xem bytecode và jdeps xem dependency.
- Phân biệt lỗi compiler, classpath và runtime.
- Đọc stack trace để tìm exception và dòng source liên quan.

Nếu còn vướng một mục, thực hành lại đúng công cụ đó. Không cần thuộc mọi option; cần hiểu công cụ giải quyết vấn đề nào và biết tra tài liệu khi cần.

## 3. Học chắc Java language

Hãy đi theo thứ tự sau:

1. Kiểu dữ liệu, biến, toán tử, điều kiện, vòng lặp và mảng.
2. Method, tham số, giá trị trả về, overload và phạm vi biến.
3. Class, object, constructor, encapsulation và access modifier.
4. Interface, inheritance, composition và polymorphism.
5. Exception, try-with-resources và cách xử lý lỗi.
6. Enum, record, generics và annotation.
7. Lambda, method reference và functional interface.
8. Collections, Stream API và Optional.

Với mỗi khái niệm, viết một ví dụ nhỏ, thử input hợp lệ, trường hợp biên và trường hợp sai. Sau đó giải thích được vì sao kết quả xuất hiện.

## 4. Thiết kế class và interface

Một ứng dụng có nhiều class với trách nhiệm riêng. Hãy luyện cách phân chia:

- Model biểu diễn dữ liệu và quy tắc bất biến.
- Service thực hiện nghiệp vụ.
- Repository hoặc gateway truy cập dữ liệu.
- CLI, controller hoặc UI nhận input và trình bày output.
- Test kiểm tra hành vi công khai.

Ví dụ Study Planner có StudySession để biểu diễn một buổi học, StudyPlan để quản lý các buổi học và StudyPlanApp làm điểm vào chương trình.

Không tạo class chỉ để tăng số lượng file. Một class nên có trách nhiệm rõ, tên thể hiện ý định và API vừa đủ. Dùng composition khi một đối tượng cần chức năng của đối tượng khác; chỉ dùng inheritance khi có quan hệ thay thế hợp lý.

## 5. Học exception và validation

Phân biệt các nhóm lỗi:

- Input hoặc trạng thái không hợp lệ: thường kiểm tra sớm và ném IllegalArgumentException hoặc IllegalStateException.
- Lỗi I/O: có thể phát sinh IOException và cần quyết định xử lý hay truyền tiếp.
- Lỗi lập trình: như NullPointerException hoặc IndexOutOfBoundsException thường cần sửa nguyên nhân.
- Lỗi nghiệp vụ dự kiến: biểu diễn rõ theo hợp đồng ứng dụng.

Không bắt Exception rồi bỏ qua. Không dùng exception để thay thế điều kiện bình thường. Thông báo lỗi nên có ngữ cảnh nhưng không ghi password, token hoặc dữ liệu nhạy cảm vào log.

## 6. Học Collections, Generics và Stream API

| API | Mục đích |
|---|---|
| List | Lưu phần tử theo thứ tự, cho phép trùng |
| Set | Lưu tập giá trị duy nhất |
| Map | Ánh xạ key sang value |
| Queue/Deque | Mô hình hàng đợi hoặc hai đầu |
| Generics | Giữ kiểu dữ liệu rõ và giảm ép kiểu |
| Stream | Lọc, biến đổi, sắp xếp và tổng hợp dữ liệu |

Ví dụ tính tổng thời lượng:

~~~java
int totalMinutes = sessions.stream()
        .mapToInt(StudySession::minutes)
        .sum();
~~~

Collection lưu dữ liệu; stream mô tả pipeline xử lý. Không chuyển mọi vòng lặp thành stream nếu vòng lặp thường dễ đọc hơn.

## 7. Mở rộng sang Java Core API

| Nhóm | Nội dung nên thực hành |
|---|---|
| Collections | List, Set, Map, Queue, Comparator |
| Date/Time | LocalDate, Instant, Duration, ZoneId |
| I/O và NIO | Path, Files, InputStream, Reader, Writer |
| Text | String, StringBuilder, regex, Formatter |
| Functional | Optional, Predicate, Function, Stream |
| Networking | URI, HttpClient, HttpRequest, HttpResponse |
| Concurrency | Thread, ExecutorService, synchronization, CompletableFuture |
| Resource management | try-with-resources, AutoCloseable |

Học Date/Time trước khi tự xử lý ngày giờ bằng chuỗi. Học Path/Files trước khi tự nối đường dẫn bằng dấu slash. Học HttpClient trước khi tự viết HTTP protocol.

JSON, YAML và database thường cần thư viện hoặc driver ngoài JDK. Khi tới phần đó, học cách thêm dependency và kiểm tra version tương thích.

## 8. Tổ chức package và source tree

Một project không nên để mọi class trong một thư mục hoặc package mặc định. Với Maven, source chính nằm trong src/main/java và test nằm trong src/test/java:

~~~text
study-planner/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/study/
│   │   │   ├── StudySession.java
│   │   │   ├── StudyPlan.java
│   │   │   └── StudyPlanApp.java
│   │   └── resources/
│   └── test/
│       ├── java/com/example/study/
│       │   └── StudyPlanTest.java
│       └── resources/
└── README.md
~~~

Tên package viết thường và thường dựa trên tên miền đảo ngược của tổ chức. Class dùng PascalCase; method và biến dùng camelCase. Không đưa JUnit vào dependency runtime nếu chỉ dùng để chạy test.

## 9. Dùng IDE sau khi hiểu command line

Hãy chọn một IDE và học các thao tác cốt lõi:

- Import project từ Maven hoặc Gradle.
- Chọn Project SDK/JDK và language level.
- Tạo class, package và test class.
- Tìm symbol, rename và refactor.
- Đặt breakpoint, step over, step into và xem biến.
- Chạy một test hoặc toàn bộ test suite.
- Xem dependency tree và build output.

IDE tăng tốc thao tác, nhưng vẫn phải hiểu project đang dùng JDK nào, build task nào chạy và output nằm ở đâu. Thỉnh thoảng build từ terminal để chắc project không phụ thuộc cấu hình riêng của IDE.

## 10. Học một build tool trước

Build tool tự động hóa compile, test, package và dependency resolution. Có thể học Maven trước vì POM và lifecycle rõ ràng, hoặc học Gradle nếu project/nhóm dùng Gradle.

Không cần thành thạo cả hai cùng lúc. Học sâu một tool trước rồi ánh xạ khái niệm sang tool còn lại.

| Khái niệm | Maven | Gradle |
|---|---|---|
| Cấu hình project | pom.xml | build.gradle hoặc build.gradle.kts |
| Dependency | dependencies trong POM | dependencies block |
| Compile | mvn compile | compileJava |
| Test | mvn test | test |
| Package | mvn package | jar hoặc assemble |
| Verify | mvn verify | check hoặc build |
| Wrapper | mvnw / mvnw.cmd | gradlew / gradlew.bat |

Ưu tiên wrapper đã được project cung cấp để nhóm dùng cùng phiên bản build tool.

## 11. Học Maven lifecycle và POM

POM mô tả coordinates, properties, dependencies và plugins. Các phase chính:

- validate: kiểm tra project và thông tin cần thiết.
- compile: biên dịch source chính.
- test: chạy unit test.
- package: tạo JAR/WAR.
- verify: chạy kiểm tra bổ sung.
- install: cài artifact vào local repository.
- deploy: đưa artifact lên remote repository.

Các lệnh thường dùng:

~~~bash
mvn clean
mvn compile
mvn test
mvn package
mvn verify
~~~

Khi gọi một phase, Maven chạy các phase trước nó trong default lifecycle. verify gồm compile, test và package theo lifecycle, nhưng không tự bảo đảm project đã cấu hình smoke test trên JAR cuối cùng.

Hãy học cách đọc dependency tree, scope compile/test/runtime, transitive dependency, repository, plugin và toolchain.

## 12. Học Gradle cơ bản nếu project sử dụng Gradle

Gradle dùng task graph. Java plugin cung cấp compileJava, processResources, classes, compileTestJava, test, jar, assemble, check và build.

Ví dụ build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.study.StudyPlanApp'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các lệnh:

~~~bash
./gradlew tasks
./gradlew dependencies
./gradlew test
./gradlew build
~~~

Trên Windows dùng gradlew.bat. Học wrapper, plugin, dependency configuration, task graph và toolchain trước khi tự viết custom task.

## 13. Quản lý dependency

Khi thêm thư viện, hãy xác định:

- Thư viện giải quyết vấn đề nào?
- Version có hỗ trợ Java release của project không?
- Dependency thuộc compile, runtime hay test?
- Có dependency bắc cầu nào được kéo vào?
- License và chính sách bảo mật có phù hợp không?
- Có cần pin version hoặc dùng BOM không?

Không copy dependency từ blog cũ mà không kiểm tra tài liệu chính thức. Không thêm thư viện chỉ vì nó có một hàm tiện lợi nếu JDK đã có API phù hợp.

Dùng dependency tree để biết vì sao một thư viện xuất hiện. Khi có xung đột version, tìm dependency đưa version cũ vào và xử lý ở đúng nơi thay vì thêm JAR thủ công vào classpath.

## 14. Bắt đầu kiểm thử bằng JUnit

Kiểm thử xác nhận hành vi bằng những ví dụ có thể chạy lại. Với JUnit Jupiter, các annotation/assertion cơ bản gồm:

- @Test đánh dấu test.
- @BeforeEach và @AfterEach chuẩn bị/dọn dữ liệu.
- assertEquals, assertTrue và assertFalse kiểm tra kết quả.
- assertThrows kiểm tra exception mong đợi.
- @ParameterizedTest chạy cùng một test với nhiều dữ liệu.

Tên test nên diễn tả hành vi. Chuẩn bị input rõ ràng và kiểm tra kết quả quan trọng. Tránh test phụ thuộc thứ tự chạy hoặc dùng state chung có thể bị test khác sửa đổi.

## 15. Phân biệt các tầng kiểm thử

| Loại | Kiểm tra | Ví dụ |
|---|---|---|
| Unit | Một class hoặc hành vi nhỏ | Tính tổng thời lượng |
| Integration | Nhiều thành phần phối hợp | Service đọc/ghi file |
| Contract/API | Hợp đồng giữa thành phần | HTTP request/response |
| Smoke | Artifact có khởi chạy đường quan trọng không | Chạy JAR đã package |
| End-to-end | Luồng nghiệp vụ qua nhiều lớp | Tạo, lưu và xem kế hoạch |

Không cần viết test cho mọi getter/setter. Ưu tiên logic có quy tắc, input biên, lỗi dự kiến và hành vi ảnh hưởng người dùng. Unit test nhanh giúp phát hiện lỗi sớm; integration/smoke test xác nhận các thành phần được nối đúng.

## 16. Thiết kế test tốt

Với mỗi method quan trọng, hãy nghĩ tới:

1. Trường hợp bình thường.
2. Input rỗng hoặc thiếu.
3. Giá trị biên.
4. Input không hợp lệ.
5. Trạng thái không có dữ liệu.
6. Exception hoặc lỗi I/O.
7. Thứ tự và tính ổn định của kết quả nếu có yêu cầu.

Test không nên lặp lại implementation. Nếu code dùng stream để tính tổng, test xác nhận kết quả nghiệp vụ, không kiểm tra rằng stream được gọi. Nếu refactor nội bộ mà hành vi không đổi, test tốt vẫn tiếp tục pass.

## 17. Debug có phương pháp

Khi có lỗi, thu thập bằng chứng trước khi sửa:

- Đọc exception và stack trace.
- Tìm frame đầu tiên thuộc source của project.
- Xác định input và trạng thái tại thời điểm lỗi.
- Tái hiện bằng test nhỏ.
- Dùng breakpoint và step execution trong IDE hoặc jdb.
- Kiểm tra giả thuyết bằng thay đổi nhỏ.
- Thêm regression test để ngăn lỗi quay lại.

Phân biệt compile error, test failure, exception runtime, lỗi cấu hình và lỗi môi trường. Không sửa bằng cách catch mọi exception hoặc tăng timeout khi chưa hiểu nguyên nhân.

## 18. Tận dụng JDK diagnostic tools

| Tool | Dùng để |
|---|---|
| jps | Liệt kê JVM đang chạy |
| jcmd | Gửi diagnostic command tới JVM |
| jstack | Lấy thread dump |
| jfr | Xem hoặc phân tích Flight Recorder recording |
| jconsole | Quan sát JVM qua giao diện |
| jmap | Xem thông tin heap |
| jdeps | Phân tích dependency class/module |
| javadoc | Sinh tài liệu API |
| javap | Xem cấu trúc class/bytecode |
| jdb | Debug chương trình Java |

Ví dụ, thay PID mẫu bằng PID thật của process:

~~~bash
jps -l
jcmd -l
jcmd 12345 VM.version
jstack 12345
~~~

Một số lệnh cần chạy cùng user với process và có thể bị giới hạn bởi quyền hệ điều hành/container. Không chạy diagnostic command trên production nếu chưa hiểu tác động và quy trình vận hành.

## 19. Học logging và quan sát ứng dụng

Ứng dụng thực tế cần log có cấu trúc và mức độ phù hợp:

- ERROR: thao tác thất bại cần xử lý.
- WARN: bất thường nhưng ứng dụng vẫn tiếp tục.
- INFO: sự kiện nghiệp vụ hoặc vòng đời quan trọng.
- DEBUG: thông tin chi tiết để điều tra.
- TRACE: chi tiết sâu, thường chỉ bật khi cần.

Bắt đầu với java.util.logging hoặc thư viện logging mà project sử dụng. Không in mọi thứ bằng System.out trong ứng dụng dài hạn. Không ghi password, access token, private key hoặc dữ liệu cá nhân không cần thiết.

Log nên có context như request ID hoặc operation ID khi phù hợp. Chọn một tầng chịu trách nhiệm log lỗi để tránh ghi cùng stack trace nhiều lần.

## 20. Viết tài liệu API và README

Dùng Javadoc để mô tả mục đích, tham số, kết quả, exception và ví dụ sử dụng cho public API.

~~~bash
javadoc -d docs/api -sourcepath src/main/java com.example.study
~~~

README của project nên có:

- Project làm gì và dành cho ai.
- Yêu cầu JDK/build tool.
- Cách build, test và chạy.
- Cấu trúc thư mục.
- Ví dụ input/output.
- Cách cấu hình.
- Giới hạn đã biết và hướng phát triển.

Tài liệu phải khớp với lệnh và hành vi thực tế. Khi đổi dependency, version hoặc cách chạy, cập nhật README cùng thay đổi đó.

## 21. Học Git và làm việc nhóm

Hãy biết clone, status, add, commit, pull, push, tạo branch, đọc diff, giải quyết conflict và tạo pull request.

Không commit secret hoặc build output nếu project không yêu cầu. Commit message nên mô tả thay đổi. Một pull request tốt có mục tiêu rõ, test đi cùng code và hướng dẫn xác minh. Đọc code review là cách tốt để học cách đặt tên, chia class và xử lý lỗi.

## 22. Capstone: xây dựng Study Planner

Để kết hợp kiến thức mới, hãy làm ứng dụng CLI tên Study Planner. Phiên bản đầu lưu buổi học trong bộ nhớ, kiểm tra dữ liệu và tính tổng thời lượng.

Yêu cầu:

- Mỗi StudySession có topic và số phút.
- Topic không rỗng; minutes phải lớn hơn 0.
- StudyPlan thêm buổi học và trả về danh sách chỉ đọc.
- Ứng dụng in số buổi, tổng thời lượng và trung bình.
- JUnit kiểm tra dữ liệu hợp lệ, dữ liệu sai và kế hoạch rỗng.
- Maven build với Java release 17.
- JAR có Main-Class và chạy được bằng java -jar.

Sau khi hoàn thành, mở rộng theo từng bước: lưu file, đọc dữ liệu, thêm lệnh CLI, lọc theo chủ đề, thêm ngày giờ, rồi thay lưu file bằng database khi đã học JDBC/SQL.

## 23. Cấu trúc project capstone

~~~text
study-planner/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/study/
    │       ├── StudySession.java
    │       ├── StudyPlan.java
    │       └── StudyPlanApp.java
    └── test/
        └── java/com/example/study/
            └── StudyPlanTest.java
~~~

StudySession mô hình hóa một buổi học; StudyPlan quản lý collection và phép tính; StudyPlanApp là entry point; StudyPlanTest kiểm tra hành vi.

## 24. Mã nguồn StudySession.java

Dùng record cho dữ liệu nhỏ, bất biến. Compact constructor chuẩn hóa topic và từ chối dữ liệu sai:

~~~java
package com.example.study;

import java.util.Objects;

public record StudySession(String topic, int minutes) {
    public StudySession {
        topic = Objects.requireNonNull(topic, "topic").strip();
        if (topic.isEmpty()) {
            throw new IllegalArgumentException("topic must not be blank");
        }
        if (minutes <= 0) {
            throw new IllegalArgumentException("minutes must be positive");
        }
    }
}
~~~

Record tự cung cấp accessor, equals, hashCode và toString. Constructor vẫn cần validation vì dữ liệu không hợp lệ không nên đi vào domain model.

## 25. Mã nguồn StudyPlan.java

~~~java
package com.example.study;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;

public final class StudyPlan {
    private final List<StudySession> sessions = new ArrayList<>();

    public void add(StudySession session) {
        sessions.add(Objects.requireNonNull(session, "session"));
    }

    public List<StudySession> sessions() {
        return List.copyOf(sessions);
    }

    public int totalMinutes() {
        return sessions.stream().mapToInt(StudySession::minutes).sum();
    }

    public OptionalDouble averageMinutes() {
        return sessions.stream().mapToInt(StudySession::minutes).average();
    }
}
~~~

List.copyOf trả về danh sách không thể sửa qua reference được trả ra. OptionalDouble thể hiện rõ rằng kế hoạch rỗng không có giá trị trung bình. Đây là ví dụ về encapsulation, immutable view và API biểu diễn trường hợp không có kết quả.

## 26. Mã nguồn StudyPlanApp.java

~~~java
package com.example.study;

import java.util.Locale;

public final class StudyPlanApp {
    private StudyPlanApp() {
    }

    public static void main(String[] args) {
        StudyPlan plan = new StudyPlan();
        plan.add(new StudySession("Java collections", 45));
        plan.add(new StudySession("Maven basics", 30));
        plan.add(new StudySession("Unit testing", 40));

        System.out.println("STUDY_PLAN sessions=" + plan.sessions().size());
        System.out.println("TOTAL_MINUTES=" + plan.totalMinutes());
        System.out.println("AVERAGE_MINUTES="
                + String.format(Locale.ROOT, "%.1f",
                        plan.averageMinutes().orElse(0.0)));
    }
}
~~~

Locale.ROOT giúp format số thập phân nhất quán giữa máy local và CI. Ứng dụng chỉ giữ dữ liệu trong bộ nhớ; khi process kết thúc, dữ liệu mất. Lưu trữ bền vững là phần mở rộng tiếp theo.

## 27. Mã nguồn StudyPlanTest.java

JUnit test kiểm tra tổng, trung bình, dữ liệu sai và kế hoạch rỗng:

~~~java
package com.example.study;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class StudyPlanTest {
    @Test
    void recordsSessionsAndCalculatesTotals() {
        StudyPlan plan = new StudyPlan();
        plan.add(new StudySession("Collections", 45));
        plan.add(new StudySession("Testing", 30));

        assertEquals(2, plan.sessions().size());
        assertEquals(75, plan.totalMinutes());
        assertEquals(37.5, plan.averageMinutes().orElseThrow());
    }

    @Test
    void rejectsInvalidSessionData() {
        assertThrows(IllegalArgumentException.class,
                () -> new StudySession("   ", 10));
        assertThrows(IllegalArgumentException.class,
                () -> new StudySession("Java", 0));
    }

    @Test
    void averageIsEmptyForAnEmptyPlan() {
        assertTrue(new StudyPlan().averageMinutes().isEmpty());
    }
}
~~~

Test đầu xác nhận dữ liệu và phép tính. Test thứ hai xác nhận validation. Test thứ ba kiểm tra trạng thái không có dữ liệu. Có thể bổ sung test cho null, danh sách trả về không thể sửa và các quy tắc mới.

## 28. pom.xml cho capstone

POM đặt release Java 17, thêm JUnit cho test, cấu hình Surefire và ghi Main-Class vào manifest để JAR chạy độc lập:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>study-planner</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.study.StudyPlanApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

JUnit có scope test nên không được đưa vào runtime dependency của ứng dụng. Maven Compiler Plugin dùng release 17; Maven JAR Plugin ghi main class. Trong project thật, thêm Maven Wrapper để nhóm dùng cùng phiên bản Maven.

## 29. Build, test và chạy capstone

Từ thư mục có pom.xml:

~~~bash
mvn clean verify
java -jar target/study-planner-1.0.0.jar
~~~

Nếu project đã có Maven Wrapper, dùng mvnw hoặc mvnw.cmd tương ứng với hệ điều hành.

Kết quả kiểm thử mong đợi:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Output ứng dụng:

~~~text
STUDY_PLAN sessions=3
TOTAL_MINUTES=115
AVERAGE_MINUTES=38.3
~~~

Nếu build thành công nhưng JAR không chạy, kiểm tra manifest có Main-Class, class có được đóng gói và runtime có hỗ trợ bytecode. Đừng chỉ chạy code trong IDE rồi kết luận artifact đã đúng.

## 30. Thực hành debug capstone

Tạo lỗi có chủ đích, ví dụ đổi minutes thành 0. Test phải thất bại vì constructor từ chối dữ liệu. Đọc failure report để xác định test nào phát hiện lỗi và dòng source liên quan.

Thử thêm các tình huống:

- Topic là chuỗi rỗng hoặc chỉ có khoảng trắng.
- Kế hoạch không có buổi học.
- Thêm cùng chủ đề nhiều lần.
- Gọi sessions() rồi thử sửa danh sách trả về.
- Thêm thời lượng rất lớn.
- Truyền null vào add.
- Chạy ứng dụng từ JAR sau clean build.

Mỗi lần sửa lỗi, giữ test tái hiện lỗi đó. Khi test pass, chạy lại verify để chắc thay đổi không làm hỏng hành vi khác.

## 31. Thêm CI cho project

Tự động build và test mỗi lần push hoặc mở pull request. Ví dụ GitHub Actions khi project đã commit Maven Wrapper:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

CI cần dùng cùng release target với local build và lưu test report khi thất bại. Sau đó có thể thêm matrix cho nhiều JDK, static analysis, dependency scanning và artifact upload. Không đưa signing key hoặc secret vào repository hay log.

## 32. Mở rộng sau capstone

Mở rộng từng chức năng:

1. Persistence: lưu và đọc StudySession bằng Path/Files.
2. CLI: hỗ trợ add, list, remove và summary.
3. Date/Time: gắn ngày học và lọc theo tuần.
4. Testing: thêm parameterized test và integration test.
5. Database: học SQL/JDBC, transaction và migration.
6. HTTP: tạo API sau khi hiểu request/response.
7. Packaging: tạo distribution ZIP hoặc runtime image bằng jlink.
8. Observability: thêm logging, metrics và JFR khi cần.
9. Security: validate input, kiểm tra dependency và bảo vệ secret.
10. Release: versioning, changelog, checksum và pipeline phát hành.

Mỗi phần mở rộng nên có yêu cầu rõ, test đi kèm và một bản chạy được. Tránh thêm framework trước khi hiểu vấn đề mà framework giải quyết.

## 33. Chọn hướng học chuyên sâu

| Hướng | Nên học tiếp |
|---|---|
| Backend/API | HTTP, REST, SQL, JDBC, transaction, Spring Boot hoặc framework tương đương |
| Desktop | JavaFX, event-driven UI, persistence và packaging |
| Data processing | Collections, Streams, SQL, batch processing và concurrency |
| Cloud/services | HTTP client/server, container, configuration, observability và CI/CD |
| JVM/platform | Class loading, bytecode, garbage collection, JFR, profiling và performance |
| Build/release engineering | Maven/Gradle nâng cao, dependency verification, reproducible build và signing |

Dù chọn hướng nào, vẫn cần nền tảng về Java language, collections, exception, testing, Git và build tool. Framework thay đổi nhanh hơn những nền tảng này.

## 34. Thứ tự học theo mốc hoàn thành

| Mốc | Việc cần làm | Bằng chứng hoàn thành |
|---|---|---|
| Java language | Viết class, interface, record, exception và generic | Chương trình nhiều class |
| Core API | Dùng collections, stream, date/time và I/O | Xử lý dữ liệu và file đúng |
| Project structure | Tách package, main/test source và resource | Project có cấu trúc rõ |
| Build | Dùng Maven hoặc Gradle Wrapper | Build sạch thành công |
| Testing | Viết unit và integration test | Test report pass |
| Debugging | Dùng breakpoint, stack trace và log | Tái hiện và sửa bug |
| Packaging | Tạo JAR/distribution và chạy artifact | Artifact chạy ngoài IDE |
| Collaboration | Dùng Git và review | Commit/PR rõ ràng |
| Specialization | Chọn backend, desktop, cloud hoặc JVM | Project hoàn chỉnh |

Chuyển sang mốc tiếp theo khi có thể giải thích và tự làm được kết quả của mốc hiện tại, không chỉ khi đã đọc hết tài liệu.

## 35. Sai lầm thường gặp khi học tiếp

- Học Spring Boot trước khi hiểu class, interface, exception và collections.
- Thêm dependency mà không biết version, scope hoặc transitive dependency.
- Chỉ chạy bằng nút Run trong IDE, không biết build từ terminal.
- Viết code nghiệp vụ trực tiếp trong main method.
- Không test validation và trường hợp biên.
- Bắt exception rồi bỏ qua.
- Dùng static global state để chia sẻ dữ liệu.
- Commit file JAR/build output mà không có lý do.
- Rebuild artifact khác sau khi đã test artifact trước.
- Học nhiều framework cùng lúc mà không hoàn thành project nào.

Giữ phạm vi nhỏ, hoàn thành một luồng đầu-cuối rồi mới mở rộng. Một ứng dụng nhỏ có cấu trúc tốt, test rõ và build tái lập sẽ liên kết được nhiều kỹ năng hơn các đoạn code rời rạc.

## 36. Checklist sẵn sàng cho project Java đầu tiên

- [ ] Biết dùng javac và java từ terminal.
- [ ] Hiểu package, class, interface và exception.
- [ ] Biết chọn List, Set và Map phù hợp.
- [ ] Biết dùng Path/Files để thao tác file.
- [ ] Tạo project có main source và test source.
- [ ] Dùng Maven hoặc Gradle Wrapper.
- [ ] Thêm dependency với version và scope rõ ràng.
- [ ] Viết JUnit test cho logic và input biên.
- [ ] Debug được stack trace và breakpoint.
- [ ] Sinh Javadoc cho API cần công bố.
- [ ] Build JAR và chạy chính artifact đó.
- [ ] Dùng Git để lưu thay đổi theo từng bước.
- [ ] Có README với lệnh build, test và run.
- [ ] Biết kiểm tra hash và nội dung artifact trước khi phát hành.

Nếu chưa đạt hết checklist, chọn một mục yếu và bổ sung vào capstone. Không cần chờ đến khi biết mọi API mới bắt đầu làm project; project chính là nơi các khái niệm liên kết với nhau.

## Tài liệu học tiếp

- Dev.java — [General Java Learning Path](https://dev.java/learn/).
- Dev.java — [Java Language: OOP, Generics, Exceptions and Pattern Matching](https://dev.java/learn/language/).
- Dev.java — [Collections and Streams](https://dev.java/learn/api/collections-and-streams/).
- Oracle — [JDK 26 Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html).
- Apache Maven — [Getting Started Guide](https://maven.apache.org/guides/getting-started/).
- Apache Maven — [Maven in 5 Minutes](https://maven.apache.org/guides/getting-started/maven-in-five-minutes.html).
- Gradle — [Getting Started and Beginner Tutorial](https://docs.gradle.org/current/userguide/getting_started.html).
- JUnit — [JUnit 5 User Guide](https://docs.junit.org/5.12.0/user-guide/).
- Oracle — [JDK Documentation and API References](https://docs.oracle.com/en/java/javase/26/).

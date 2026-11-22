# Phân biệt skipTests, maven.test.skip và loại trừ tác vụ test của Gradle

## 1. Vì sao “không chạy test” có nhiều ý nghĩa khác nhau?

Trong một dự án Spring Boot, khi muốn tạo JAR nhanh để thử thủ công, lập trình viên thường gặp ba lệnh:

~~~bash
./mvnw clean package -DskipTests
./mvnw clean package -Dmaven.test.skip=true
./gradlew clean build -x test
~~~

Trông chúng đều có vẻ “build không kiểm thử”, nhưng cơ chế **không giống nhau**:

- **Maven -DskipTests**: với **Maven Surefire Plugin**, bỏ qua **thực thi unit tests**, trong khi Maven Compiler Plugin vẫn **biên dịch test source** theo lifecycle thông thường.
- **Maven -Dmaven.test.skip=true**: property được Maven Compiler Plugin, Surefire và Failsafe nhận biết; nó bỏ qua **test compilation** lẫn **test execution** qua những plugin này.
- **Gradle -x test** (viết đầy đủ là **--exclude-task test**): loại task **test** ra khỏi đồ thị thực thi Gradle của lệnh đó, đồng thời có thể loại các dependency tasks mà chỉ task test cần. Nó **không phải** một Maven property và không có nghĩa mọi task kiểm thử trong build đều bị loại.

Câu hỏi quan trọng không chỉ là “có chạy assertions hay không”, mà còn là:

1. Có biên dịch **src/test/java** không?
2. Có xử lý/copy **src/test/resources** không?
3. Có chạy **unit test** không?
4. Có chạy **integration test**, **functional test** hoặc một custom Test task khác không?
5. Các task/plugins khác như quality checks, packaging, coverage, verification còn chạy không?
6. CI có thể tuyên bố build **đã được kiểm thử** dựa trên kết quả ấy không?

**Mục tiêu:** phân biệt chính xác các lựa chọn, hiểu Maven lifecycle và Gradle task graph, đọc dấu hiệu trong log/output, thực hành với project Java 17 + Spring Boot, và dùng cờ skip có kiểm soát mà không tạo ra cảm giác an toàn giả.

## 2. Nắm nền tảng: Maven phase khác Gradle task

### 2.1. Maven: chạy lifecycle đến một phase

Với packaging **jar**, khi gọi **./mvnw package**, Maven đi qua các phase trước đó trong **default lifecycle** và các plugin goals được bind vào chúng. Có thể hình dung:

~~~text
validate
   |
process-resources       -> copy/filter main resources
   |
compile                 -> maven-compiler-plugin:compile
   |
process-test-resources  -> copy/filter test resources
   |
test-compile            -> maven-compiler-plugin:testCompile
   |
test                    -> maven-surefire-plugin:test (khi được bind)
   |
package                 -> tạo JAR/WAR; Spring Boot có thể repackage
~~~

Sơ đồ trên chỉ thể hiện các phase/goal tiêu biểu. Có nhiều phase khác giữa chúng; binding cuối cùng còn tùy **packaging**, parent POM, plugin executions và profiles. Quan trọng là **test-compile đứng trước test**; nếu chỉ bỏ chạy Surefire, Maven vẫn có thể đến test-compile.

Trong Spring Boot project kế thừa **spring-boot-starter-parent** và khai báo **spring-boot-maven-plugin**, phase package thông thường tạo archive rồi thực hiện **repackage** thành executable JAR. **-DskipTests** hay **-Dmaven.test.skip** không mặc nhiên bỏ qua compile main, package hoặc repackage.

### 2.2. Gradle: chọn task, rồi giải dependency graph

Với Java plugin, các task thường gặp:

~~~text
classes ----> compileJava, processResources
    |
    +----------------------+
                           |
testClasses ----> compileTestJava, processTestResources
    |                      |
    v                      v
   test ---------------> check --------> build
                                            ^
                                            |
                                assemble / jar / bootJar ...
~~~

Đây là **sơ đồ khái niệm** để nhớ mối quan hệ, không phải output một Gradle graph chính xác: trên thực tế **test** phụ thuộc vào **testClasses**, **check** phụ thuộc vào **test**, **build** phụ thuộc vào **check** và **assemble**; **testClasses** lại cần main classes; **assemble**/bootJar có các dependency riêng. Lệnh **./gradlew build** thông thường sẽ kích hoạt task test của Java plugin. Lệnh **./gradlew bootJar** tập trung vào đóng gói executable archive và **không mặc nhiên phải chạy task test**.

**-x test** thay đổi **tập task được chọn** cho một lần gọi. Nó khác với cấu hình **test.enabled = false** hay **test.onlyIf { false }**, vì những cách sau giữ task ở đồ thị nhưng bỏ chạy actions. Sự khác nhau đó ảnh hưởng việc **compileTestJava** có còn được chọn không.

## 3. Bảng so sánh bốn lựa chọn cốt lõi

| Cách gọi/điều khiển | Compile main? | Compile test source? | Thực thi unit tests? | Các bước khác? |
| --- | --- | --- | --- | --- |
| **./mvnw clean package** | Có | Có | Có, nếu Surefire và tests được cấu hình | Package và các plugin goals khác vẫn chạy |
| **./mvnw clean package -DskipTests** | Có | **Có** | **Không** với Surefire | Package vẫn chạy; integration tests tùy Failsafe version/config |
| **./mvnw clean package -Dmaven.test.skip=true** | Có | **Không**, với Compiler Plugin nhận property | **Không**, với Surefire/Failsafe nhận property | Package vẫn chạy; plugin custom có thể khác |
| **./gradlew clean build -x test** | Có khi graph cần | **Thường không** trong Java plugin chuẩn nếu chỉ test cần | **Không**, vì task test bị loại | build/assemble/check khác vẫn có thể chạy |

**Điều kiện của bảng:** dự án Maven chuẩn có Maven Compiler Plugin và Surefire, dự án Gradle chuẩn áp dụng Java + Spring Boot plugins, không có custom dependency graph đặc biệt. Nếu có custom test task, integration-test plugin, source set riêng, code generation ở testCompile hay profile đặc thù, cần kiểm tra build thật: không suy luận “mọi test đều bị skip” chỉ từ một dòng cờ.

**Lưu ý về test resources:** -Dmaven.test.skip không phải lệnh “xóa toàn bộ src/test”. Maven lifecycle vẫn có thể thực hiện **process-test-resources** nếu goal resources được bind. Tương tự, Gradle -x test có thể không chọn processTestResources khi chỉ task test cần, nhưng task khác có thể sử dụng output ấy. Hãy phân biệt rõ **copy resources**, **biên dịch tests**, **chạy tests**.

## 4. Maven -DskipTests: bỏ chạy Surefire, vẫn biên dịch test

### 4.1. Lệnh và cơ chế

~~~bash
./mvnw clean package -DskipTests
./mvnw clean verify -DskipTests=true
~~~

Hai cách truyền cờ tương đương về giá trị boolean đối với cấu hình Surefire hỗ trợ **skipTests**. Maven truyền một **user property** tên **skipTests**; Maven Surefire Plugin nhận property này và không thực thi unit tests.

Điều quan trọng:

- Maven vẫn biên dịch **src/main/java**.
- Trong lifecycle chuẩn, Maven Compiler Plugin vẫn chạy **testCompile** và cố biên dịch **src/test/java**.
- Một lỗi **cú pháp hoặc kiểu dữ liệu trong test source** có thể làm build thất bại ngay cả khi **-DskipTests=true**, vì test compile vẫn được thực hiện.
- Surefire không chạy các test methods/classes được phát hiện. Không có kết quả test mới chứng minh assertions đã pass ở lượt build này.
- Maven vẫn có thể tạo executable Spring Boot JAR nếu các phase/goals khác thành công.

**Tình huống phù hợp:** cần tạo JAR nhanh để debug nhưng vẫn muốn kiểm tra **test source còn biên dịch được**. Đây là một thỏa hiệp ít rủi ro hơn việc bỏ cả test compilation, nhưng **không thay thế kiểm thử**.

### 4.2. Vì sao skipTests không “bỏ hết test”?

Surefire thực hiện **test execution** ở phase test; Compiler Plugin phụ trách **test compilation** ở phase test-compile. Cờ **skipTests** là tham số của Surefire và không mặc định là tham số skip của compiler. Vì vậy:

~~~text
-DskipTests=true
      |
      +--> compiler:compile       -> VẪN chạy
      +--> compiler:testCompile   -> VẪN chạy
      +--> surefire:test          -> KHÔNG thực thi test cases
      +--> package/repackage      -> VẪN có thể chạy
~~~

Các dòng là mô tả hành vi điển hình, không phải log Maven nguyên văn. Build vẫn có thể dừng ở một lỗi trước package hoặc một plugin khác.

### 4.3. Kết quả cần quan sát

Sau build sạch thành công với **-DskipTests**, Maven thông thường có thể tạo:

~~~text
target/classes/          # class của ứng dụng
target/test-classes/     # class của test đã biên dịch
target/<artifact>.jar    # JAR được đóng gói
~~~

Còn **target/surefire-reports** có thể không tồn tại sau **clean** vì Surefire chưa thực thi tests trong lượt đó. Nếu bạn thấy report cũ khi không clean, **không được tính report ấy là bằng chứng test của lần build hiện tại đã chạy**.

Đọc log để tìm các goal **maven-compiler-plugin:testCompile** và **maven-surefire-plugin:test**. Nếu plugin báo skip, kết luận là **bỏ thực thi**, không phải test đã pass.

## 5. Maven -Dmaven.test.skip=true: bỏ cả test compilation

### 5.1. Lệnh và cơ chế

~~~bash
./mvnw clean package -Dmaven.test.skip=true
./mvnw clean verify -Dmaven.test.skip=true
~~~

**maven.test.skip** là property được **Maven Compiler Plugin**, **Maven Surefire Plugin** và **Maven Failsafe Plugin** sử dụng theo tài liệu của chúng. Với giá trị **true**:

- **Compiler Plugin** bỏ qua việc biên dịch test source.
- **Surefire** bỏ qua thực thi unit tests.
- **Failsafe** bỏ qua integration tests do plugin đó xử lý khi được cấu hình trong build.
- **Main source** vẫn được biên dịch; package/repackage vẫn có thể hoạt động.
- **Không** xác nhận rằng code trong **src/test/java** có compile được.

Đây là sự khác biệt lớn so với **-DskipTests**. Một test dùng method không tồn tại, import sai hoặc có lỗi syntax sẽ **không bị phát hiện** qua bước compile test nếu test compilation bị bỏ qua.

### 5.2. Sơ đồ cơ chế

~~~text
-Dmaven.test.skip=true
      |
      +--> compiler:compile       -> VẪN chạy
      +--> compiler:testCompile   -> BỎ QUA
      +--> surefire:test          -> BỎ QUA
      +--> failsafe:*             -> BỎ QUA test/verify liên quan theo config
      +--> package/repackage      -> VẪN có thể chạy
~~~

**Không coi maven.test.skip là “tắt tất cả hoạt động kiểm thử trong mọi plugin”.** Plugin tự phát triển hoặc check chất lượng (Checkstyle, SpotBugs, JaCoCo, integration test plugin khác, frontend tests...) có thể **không đọc property này**. Các phase khác vẫn chạy. Nếu pipeline có security checks hoặc custom validation, chúng vẫn có thể hoạt động hoặc thất bại.

### 5.3. Khi nào nên dùng?

Chỉ nên dùng có chủ đích trong một môi trường cần đóng gói tạm thời, khi test compilation đang bị một vấn đề **đã được nhận diện** cản trở và bạn chấp nhận không kiểm tra test code trong lượt build đó. Ví dụ kiểm tra riêng hành vi runtime của main artifact trong quá trình chẩn đoán, **không** dùng để tạo bản phát hành “đã kiểm thử”.

Rủi ro là bạn có thể tạo JAR thành công dù test source không còn compile. Vì vậy lệnh này nên hiện rõ trong build log và không được ngầm hóa vào chính sách release.

## 6. Maven Failsafe và integration tests: lưu ý khác biệt theo phiên bản

Spring Boot project chỉ có starter-test **không mặc nhiên chạy integration tests bằng Failsafe**. Failsafe thường phải được khai báo và bind goals **integration-test**, **verify** vào lifecycle thích hợp; những tests đó có thể dùng hậu tố tên như **IT** hoặc **ITCase** theo conventions của plugin.

Ba cờ liên quan là:

| Property | Ý nghĩa với plugin tiêu biểu |
| --- | --- |
| **-DskipTests=true** | Surefire bỏ unit test execution. Với **Failsafe 3.6.0 trở lên**, không còn tự liên kết CLI property này để skip integration tests |
| **-DskipITs=true** | Failsafe bỏ chạy integration tests, vẫn cho phép compile test source |
| **-Dmaven.test.skip=true** | Compiler Plugin bỏ test compilation; Surefire/Failsafe bỏ test execution |

**Quan trọng về phiên bản:** Một số hướng dẫn Failsafe cũ nói **-DskipTests** cũng bỏ integration tests. Từ **Failsafe 3.6.0**, Failsafe **không còn bind** tham số skipTests của nó với user property **skipTests**; tài liệu chính thức yêu cầu **-DskipITs** để bỏ integration tests. Vì vậy nếu pipeline vừa chạy Surefire vừa chạy Failsafe, **không thể mặc định -DskipTests bỏ cả hai**. Hãy đọc phiên bản Failsafe **thực sự được resolve** qua effective POM rồi xem báo cáo/log của từng plugin.

Khi muốn chỉ chạy integration tests mà không chạy unit tests (ví dụ suite IT có setup đủ), có thể dùng **-DskipTests** trong môi trường Failsafe 3.6+; nó không được bảo đảm đúng với Failsafe cũ hoặc cấu hình custom. Khi muốn bỏ riêng ITs trong Failsafe nhưng vẫn chạy Surefire unit tests:

~~~bash
./mvnw verify -DskipITs=true
~~~

Lệnh vẫn biên dịch test classes theo lifecycle thông thường. Để kiểm tra plugin version và executions trong dự án:

~~~bash
./mvnw help:effective-pom
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=integration-test -Ddetail=true
~~~

**Thứ tự goal của Failsafe quan trọng:** plugin thường có goal **integration-test** chạy tests và goal **verify** đánh giá kết quả để quyết định build thất bại. Chạy **mvn verify** với Failsafe được bind và không bỏ test cho pipeline kiểm thử đầy đủ, thay vì dừng ở **mvn package** rồi tuyên bố các integration tests đã được kiểm tra.

Nguồn chính thức:
- https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html
- https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html
- https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html

## 7. Gradle -x test: loại task khỏi execution graph

### 7.1. Lệnh cơ bản

~~~bash
./gradlew build -x test
./gradlew clean build --exclude-task test
~~~

Cờ **-x** có tên đầy đủ **--exclude-task**. Khi Gradle dựng graph cho **build**, task tên **test** được loại khỏi các task sẽ thực thi theo phạm vi task resolution của lệnh. Với Java plugin thông thường, khi không còn consumer khác cần test outputs, các task chỉ phục vụ nó như **compileTestJava** hoặc **processTestResources** cũng có thể không được chọn.

Tuy nhiên:

- **compileJava**, **processResources**, **classes**, **jar**, **bootJar**, **assemble**... vẫn có thể chạy theo dependency graph.
- **build** vẫn có thể thành công vì task test không được thực thi; thành công **không chứng minh unit tests đã pass**.
- Nếu build có custom **integrationTest**, **functionalTest**, **testSmoke** hoặc task type **Test** khác, **-x test** không tự động loại hết chúng; phải xem tên/path và graph thực tế.
- Một task test **được người dùng yêu cầu trực tiếp** hoặc task tùy biến có behavior riêng cần được phân tích theo graph; tránh dự đoán chỉ từ tên.
- Khi nhiều subprojects, cần chỉ rõ bạn muốn bỏ task nào (ví dụ **:app:test**) và kiểm tra bằng **--dry-run** hoặc task outputs, tránh tưởng một tham số sẽ tương đương chính sách của mọi module.

### 7.2. -x tác động cả các dependency task chỉ dùng để test

Sơ đồ Java plugin thường thấy:

~~~text
build
├── assemble
│   └── jar / bootJar / classes
└── check
    └── test
        └── testClasses
            ├── compileTestJava
            └── processTestResources
~~~

Khi gọi **./gradlew build -x test**, nhánh **test** bị loại. Những task chỉ được cần bởi nhánh này có thể biến mất khỏi graph. Điều này **khác** Maven **-DskipTests**: Maven vẫn đi qua test-compile, trong khi Gradle -x test **thường không compile test source** trong cấu trúc Java plugin tiêu chuẩn.

**Đừng tuyên bố tuyệt đối** rằng Gradle -x test luôn bỏ test compilation. Một plugin khác hoặc một task được gọi thêm trên CLI vẫn có thể phụ thuộc **testClasses** hoặc **compileTestJava**, khi ấy các task đó vẫn được chọn. Muốn biết chắc, xem graph của lệnh thực tế.

### 7.3. Xem kế hoạch mà không chạy test

~~~bash
./gradlew build --dry-run
./gradlew build -x test --dry-run
~~~

So sánh tập task được in. Ở lệnh đầu, task test thường xuất hiện khi Java plugin tham gia; ở lệnh thứ hai, task **test** bị loại. Trong Gradle dry-run, những task còn lại có thể được in với **SKIPPED** vì Gradle đang mô phỏng task actions — đây **không phải** bằng chứng rằng code đã biên dịch hay test đã chạy. -x làm task **biến khỏi graph**, khác với task **còn trong graph nhưng được đánh dấu SKIPPED**.

**Cảnh báo:** dry-run vẫn evaluate settings/build scripts và plugins; nó không đảm bảo toàn bộ configuration phase không có I/O/side effects. Dùng cho quan sát kế hoạch, không coi là một sandbox tuyệt đối.

Nguồn: https://docs.gradle.org/current/userguide/java_testing.html và https://docs.gradle.org/current/userguide/controlling_task_execution.html

## 8. Gradle: -x, enabled=false và onlyIf khác nhau

### 8.1. Bảng so sánh

| Cách | Task test có nằm trong graph không? | Task actions chạy không? | Test compile dependency có thể chạy không? |
| --- | --- | --- | --- |
| **build -x test** | **Không** (task bị loại khỏi graph theo lựa chọn) | Không | Chỉ khi các task khác vẫn cần compile test |
| **test.enabled = false** | Thường vẫn có task trong graph, trạng thái SKIPPED | Không | **Có thể** vì task dependencies vẫn được giải/thực thi |
| **test.onlyIf { false }** | Task vẫn được chọn nhưng actions không chạy, ghi SKIPPED | Không | **Có thể** vì dependency tasks có thể thực thi |
| **build** bình thường | Có khi Java plugin cấu hình chuẩn | Có nếu không bị UP-TO-DATE/NO-SOURCE/skip | Có khi có test source |

Nếu muốn **bỏ chạy test nhưng vẫn giữ test compilation** gần với tinh thần Maven **-DskipTests**, một cách là **đặt điều kiện onlyIf trên task test** thay vì loại toàn bộ task bằng -x. Tuy nhiên vẫn phải xác nhận các dependencies và input/output, và lệnh không cần biên dịch test nếu project không có test source.

### 8.2. Ví dụ condition theo project property

Trong **build.gradle** (Groovy DSL), cấu hình bổ sung:

~~~groovy
tasks.named('test') {
    onlyIf("skipUnitTests property is absent") {
        !providers.gradleProperty('skipUnitTests').isPresent()
    }
}
~~~

Đây là **đoạn ghép vào project đã có Java plugin/test task**, không phải build.gradle độc lập. Với cờ **-PskipUnitTests**:

~~~bash
./gradlew clean build -PskipUnitTests
~~~

Gradle vẫn có task test trong graph nhưng **không chạy test actions** vì điều kiện false. Các task dependency của test (chẳng hạn compileTestJava) **vẫn có thể chạy** theo graph thông thường; dùng **--dry-run** hoặc log thực để kiểm tra.

Khi không truyền **-PskipUnitTests**, condition true và task test chạy như bình thường khi có input phù hợp. Ưu điểm là lệnh build cho thấy một điều kiện cụ thể có tên dễ hiểu, không phải một cờ loại trừ task tùy ý. Dù vậy, **không nên mặc định skip unit tests trong release CI**.

Tùy chọn đơn giản nhưng kém linh hoạt hơn là:

~~~groovy
tasks.named('test') {
    enabled = false
}
~~~

Đoạn này khiến task test bị disabled cho cấu hình đó, nên nếu commit vào mainline mà không điều kiện, các build sau sẽ liên tục bỏ test — một rủi ro lớn. Hãy ưu tiên cấu hình có thể bật lại và được kiểm soát bằng CI policy.

### 8.3. Gradle không hiểu Maven properties theo mặc định

~~~bash
./gradlew build -DskipTests=true
./gradlew build -Dmaven.test.skip=true
~~~

Hai cờ **-D** ở đây là cách truyền **JVM system property cho Gradle**, không tự kích hoạt skip Surefire/Maven Compiler Plugin; một build Gradle chỉ làm gì đó với chúng nếu build script/plugin **cố ý đọc các property đó**. Không nên áp dụng công thức Maven sang Gradle rồi tưởng tests đã được bỏ qua.

Ngược lại, **-x test** không phải cú pháp hợp lệ để Maven tự chọn một test phase cần bỏ: **./mvnw package -x test** không tương đương Gradle.

## 9. Ví dụ chạy được: một project Spring Boot có unit test

Ta sử dụng cùng một bộ Java source cho hai cách build **Maven hoặc Gradle**. Chỉ chọn một build tool và cấu hình tương ứng trong project. Bài sử dụng Java 17+, Spring Boot 3.5.16, JUnit Jupiter qua Spring Boot starter-test; ví dụ này chỉ kiểm tra một phép cộng để dễ quan sát khác biệt giữa **biên dịch test**, **chạy test** và **đóng gói**.

### 9.1. Cấu trúc source

~~~text
skip-demo/
├── pom.xml                  (chỉ khi dùng Maven)
│   hoặc build.gradle        (chỉ khi dùng Gradle)
├── settings.gradle          (nếu dùng Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...       (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/java/com/example/skipdemo/
    │   ├── SkipDemoApplication.java
    │   └── Calculator.java
    └── test/java/com/example/skipdemo/
        └── CalculatorTest.java
~~~

Wrapper phải được tạo bằng Spring Initializr hoặc công cụ Wrapper của build tool; việc gõ pom.xml/build.gradle không tự tạo các script. Dùng Maven/Gradle/Java trong dải Spring Boot release thực tế hỗ trợ.

### 9.2. Mã Java main

Tệp **src/main/java/com/example/skipdemo/Calculator.java**:

~~~java
package com.example.skipdemo;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

Tệp **src/main/java/com/example/skipdemo/SkipDemoApplication.java**:

~~~java
package com.example.skipdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SkipDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SkipDemoApplication.class, args);
    }
}
~~~

Ứng dụng không thêm starter-web và không khai báo controller nên **không mong đợi HTTP server trên cổng 8080**. Nếu gọi **java -jar**, Spring context khởi động, sau đó ứng dụng có thể kết thúc bình thường khi không có non-daemon worker. Log startup thay đổi theo máy và phiên bản.

### 9.3. Mã kiểm thử JUnit

Tệp **src/test/java/com/example/skipdemo/CalculatorTest.java**:

~~~java
package com.example.skipdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void additionWorks() {
        Calculator calculator = new Calculator();
        assertEquals(5, calculator.add(2, 3));
    }
}
~~~

Đây là test hợp lệ, **biên dịch được** và **PASS** khi được chạy với JUnit Jupiter. Vì assertEquals so sánh 5 với 2 + 3 = 5, không có phụ thuộc bên ngoài làm kết quả thay đổi.

### 9.4. Lựa chọn A — Maven pom.xml đầy đủ

Tệp **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>skip-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là project đơn giản, không tự custom Surefire. Spring Boot parent quản lý phiên bản phù hợp cho các dependency/plugins thông dụng; **spring-boot-starter-test** đưa JUnit Jupiter vào test classpath. Trong một Maven project chuẩn, testCompile và Surefire test goal được bind vào lifecycle tương ứng.

Chạy trên Linux/macOS (Windows dùng **mvnw.cmd**):

~~~bash
./mvnw --version
./mvnw clean verify
./mvnw clean package -DskipTests
./mvnw clean package -Dmaven.test.skip=true
~~~

Ba dòng sau là **ba lần build độc lập để so sánh**, không phải các bước phải chạy theo thứ tự trong pipeline production. **clean** trước mỗi lần giúp giảm việc quan sát test classes/reports cũ và tránh hiểu nhầm kết quả của lần trước.

### 9.5. Lựa chọn B — Gradle build.gradle đầy đủ

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'skip-demo'
~~~

Tệp **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot Gradle Plugin tạo executable archive thông qua **bootJar**, Spring dependency-management plugin import BOM phiên bản tương ứng, **java** plugin tạo task **test**. Cấu hình JUnit Platform cho phép JUnit Jupiter tests được Gradle phát hiện.

Với Gradle Wrapper 8.14 (phù hợp Java 17 và dải Boot 3.5), trên Linux/macOS chạy (Windows dùng **gradlew.bat**):

~~~bash
./gradlew --version
./gradlew clean build
./gradlew clean build -x test
./gradlew clean build -x test --dry-run
~~~

Các lệnh minh họa lựa chọn thay nhau. Lệnh cuối chỉ in task plan, không chạy biên dịch/test/package task actions, nên không dùng làm bằng chứng đã có artifact mới.

### 9.6. Kết quả dự kiến của các lần chạy

Với **CalculatorTest** hợp lệ, lệnh Maven **clean verify** và Gradle **clean build** có thể chạy test và PASS. Các bản skip tests cũng có thể build thành công, nhưng **không chứng minh đã chạy assertions**.

Đầu ra theo bản dựng mặc định:

| Công cụ | Main classes | Test classes khi compile | Test reports khi test chạy | Executable Boot JAR |
| --- | --- | --- | --- | --- |
| Maven | target/classes | target/test-classes | target/surefire-reports | target/skip-demo-1.0.0.jar |
| Gradle | build/classes/java/main | build/classes/java/test | build/test-results/test, build/reports/tests/test | build/libs/skip-demo-1.0.0.jar |

**Không khẳng định** test report hiện hữu khi skip tests, nhất là nếu **clean** đã xóa output. Khi Gradle **-x test**, **build/classes/java/test** thường không được tạo trong clean build của project đơn giản vì test source compilation không còn task consumer. Nếu không clean, output cũ có thể vẫn nằm đó; thấy file không chứng minh nó được tạo trong lượt build hiện tại.

Nếu muốn chạy JAR:

~~~bash
java -jar target/skip-demo-1.0.0.jar
~~~

hoặc:

~~~bash
java -jar build/libs/skip-demo-1.0.0.jar
~~~

Chỉ dùng lệnh tương ứng build tool đã chọn. Chạy thành công chứng minh artifact có thể khởi động trong môi trường đó, **không chứng minh unit tests đã chạy**.

## 10. Thí nghiệm phân biệt compile-test và run-test

Để nhìn thấy khác biệt một cách trực tiếp, hãy làm thí nghiệm trong **bản sao/dev branch**, không cố ý phá source chính của nhóm. Hai tình huống dưới dùng **test code làm phép thử**; đây không phải thiết kế test nên đưa vào production.

### 10.1. Thí nghiệm A — test biên dịch nhưng assertion FAIL

Trong **CalculatorTest.java**, đổi:

~~~java
assertEquals(5, calculator.add(2, 3));
~~~

thành:

~~~java
assertEquals(6, calculator.add(2, 3));
~~~

Mã Java vẫn biên dịch hợp lệ nhưng JUnit khi chạy sẽ phát hiện **expected 6, actual 5**. Với cấu hình demo:

| Lệnh | Kết quả mong đợi |
| --- | --- |
| **./mvnw clean verify** | FAIL ở Surefire/JUnit vì assertion sai |
| **./mvnw clean package -DskipTests** | Test vẫn compile; assertions không chạy; build có thể PASS |
| **./mvnw clean package -Dmaven.test.skip=true** | Không compile/test; build có thể PASS |
| **./gradlew clean build** | FAIL ở task test vì assertion sai |
| **./gradlew clean build -x test** | Test task bị loại; build có thể PASS |

“PASS” trong hai dòng skip chỉ là trạng thái **bản dựng không chạy test này**, **không** có nghĩa phép cộng thỏa yêu cầu test đã viết. Sau thí nghiệm phải hoàn tác assertion đúng.

### 10.2. Thí nghiệm B — test source không thể biên dịch

Khác thí nghiệm A, thêm vào phương thức test một dòng Java cố tình sai kiểu:

~~~java
int invalid = "not-an-int";
~~~

Đây là **đoạn test sai có chủ đích**, phải hoàn tác sau khi quan sát. Compiler sẽ báo không chuyển được String thành int. Kết quả điển hình trong clean build:

| Lệnh | Kết quả mong đợi |
| --- | --- |
| **./mvnw clean package** | FAIL tại testCompile |
| **./mvnw clean package -DskipTests** | **Vẫn FAIL** tại testCompile; skipTests không bỏ test compilation |
| **./mvnw clean package -Dmaven.test.skip=true** | Test compilation bỏ qua; main package có thể PASS |
| **./gradlew clean build** | FAIL tại compileTestJava |
| **./gradlew clean build -x test** | Với Java plugin chuẩn, compileTestJava thường cũng không được chọn; main build có thể PASS |
| **./gradlew clean testClasses -x test** | **FAIL** tại compileTestJava nếu testClasses vẫn được yêu cầu trực tiếp |

Dòng cuối rất hữu ích: cùng có **-x test**, nhưng người dùng vẫn yêu cầu **testClasses** trực tiếp nên Gradle phải compile test source. Điều này chứng minh Gradle quyết định qua **task graph**, không phải biến boolean toàn cục “test compilation disabled”.

**Chú ý:** các kết quả là dự kiến cho project demo và phiên bản plugin tương thích, không phải kết quả chạy thực nghiệm do bài viết đã ghi nhận. Các custom plugins, generated test source, module dependency, profile, cache hoặc task graph có thể làm kết quả khác.

## 11. “Skip”, “chỉ chạy một phần test” và “bỏ qua lỗi test” là ba việc khác nhau

### 11.1. Chọn một phần test thay vì bỏ hết

Khi sửa bug, **chạy đúng test liên quan** thường tốt hơn bỏ tất cả tests:

Maven Surefire:

~~~bash
./mvnw test -Dtest=CalculatorTest
./mvnw test -Dtest=CalculatorTest#additionWorks
~~~

Gradle Java/JUnit Platform:

~~~bash
./gradlew test --tests com.example.skipdemo.CalculatorTest
./gradlew test --tests 'com.example.skipdemo.CalculatorTest.additionWorks'
~~~

Những lệnh này **thực sự chạy test được chọn** (nếu tên/method có trong project) và không phải skip. Chúng hữu ích cho vòng phát triển nhanh, sau đó vẫn cần chạy test suite phù hợp trong CI.

### 11.2. Để tests FAIL nhưng build vẫn xanh là một chính sách khác

Maven Surefire có cấu hình **maven.test.failure.ignore**, Gradle Test task có **ignoreFailures**. Chúng không giống **skip**:

- Test **có thể được chạy** và phát hiện lỗi.
- Plugin có thể được cấu hình để **không làm toàn bộ build thất bại** vì test failure.
- Pipeline có thể báo build thành công nhưng report vẫn có failing tests.

Không nên dùng cách này để hợp thức hóa build phát hành. Nếu tạm thời cho phép lỗi, hãy ghi rõ trong CI/report và đặt tiêu chí chấm dứt ngoại lệ. **Không nhầm “BUILD SUCCESSFUL” với “0 test failures”** khi đã bật các cờ làm nhẹ kiểm tra.

### 11.3. UP-TO-DATE/FROM-CACHE/NO-SOURCE cũng không phải skip có chủ đích

Trong Gradle log:
- **UP-TO-DATE**: task không phải chạy lại vì input/output theo Gradle được coi là không đổi.
- **FROM-CACHE**: Gradle phục hồi output phù hợp từ cache.
- **NO-SOURCE**: task không có source theo cấu hình.
- **SKIPPED**: task bị bỏ actions vì điều kiện/disabled hoặc lý do khác.
- **-x test**: task test không được chọn nên thường **không hiện** trong task list.

Chúng mang ý nghĩa khác nhau. Một test task từ cache có thể là kết quả xác minh các input đã biết, còn **-x test** chủ động loại bỏ task. Khi điều tra tại sao test không chạy, cần xem cờ CLI, task condition, inputs và task outcomes.

## 12. Các trường hợp thực tế của Spring Boot

### Tình huống A — muốn thử đóng gói executable JAR nhanh

Với Maven, nếu cần đảm bảo test source vẫn compile:

~~~bash
./mvnw clean package -DskipTests
~~~

Với Gradle, nếu chỉ cần thử **bootJar** và chưa muốn xây cả bộ validation tasks:

~~~bash
./gradlew clean bootJar
~~~

**bootJar thường không yêu cầu task test**, nên không nhất thiết phải thêm **-x test**. Nhưng nếu build script custom buộc bootJar phụ thuộc test, cần xem graph. Việc build JAR không chạy tests vẫn phải được ghi nhận và cần một pipeline đầy đủ chạy tests sau đó.

### Tình huống B — phát hiện test source có compile error, nhưng cần kiểm tra main artifact

Maven **-DskipTests** sẽ không cứu được build khỏi lỗi test compilation. Nếu thật sự cần tạo JAR tạm thời phục vụ chẩn đoán:

~~~bash
./mvnw clean package -Dmaven.test.skip=true
~~~

Chỉ dùng như một ngoại lệ cục bộ; sau đó phải sửa compilation error và chạy lại **./mvnw clean verify**. Gradle có thể tạo riêng **bootJar** hoặc loại test task khi build, nhưng vẫn phải kiểm tra những plugin/task khác còn yêu cầu test outputs hay không.

### Tình huống C — chỉ unit tests chạy, integration tests tạm chưa có môi trường

Maven project đã bind Failsafe ở integration-test/verify phases có thể dùng:

~~~bash
./mvnw verify -DskipITs=true
~~~

Cờ này chỉ có ý nghĩa đối với Failsafe khi được dùng; nếu project không áp dụng Failsafe, nó không tự tạo hay tắt integration tests của một công cụ khác. Với Gradle, integration tests thường là **custom Test task** hoặc một test suite khác; -x test không đồng nghĩa -x integrationTest. Cần xem **./gradlew tasks --all** và task graph rồi chọn cách loại trừ/điều kiện theo đúng test suite.

### Tình huống D — CI build vẫn cần xác nhận test

Một pipeline nên có bước rõ ràng chạy unit tests và integration tests phù hợp trước khi phát hành. Có thể tách:
1. **Build/compile/assemble** để phát hiện compile/package errors sớm.
2. **Unit test** trên mỗi thay đổi.
3. **Integration/contract tests** tại môi trường có các dependency cần thiết.
4. **Release gate** chỉ cho phép publish/deploy từ artifact và commit đã đi qua những bước kiểm tra bắt buộc.

Đừng để cờ skip tests trong một môi trường “build nhanh” tự động được tái sử dụng trong release job. Tên job, status checks và logs phải nói rõ **đã chạy test gì** chứ không chỉ nói **build success**.

## 13. Multi-module: phạm vi cờ và task cần xét riêng

### 13.1. Maven reactor

Trong Maven multi-module, property **-DskipTests** được truyền trong invocation tới các module tham gia reactor, nhưng **tác dụng còn tùy plugin execution và cấu hình POM của từng module**. Một module không có Java test source, module chỉ packaging **pom**, hoặc module dùng plugin custom sẽ không có hành vi giống module Java application.

Ví dụ chỉ build module api cùng các dependencies cần thiết:

~~~bash
./mvnw -pl api -am package -DskipTests
~~~

**-pl** chọn project, **-am** bổ sung các project mà nó cần trong reactor. Surefire của những module liên quan đọc property skipTests nếu cấu hình chuẩn. Không cho rằng một lệnh đã chạy tests ở các module không được chọn, hoặc Failsafe 3.6+ cũng skip IT chỉ vì có skipTests.

### 13.2. Gradle multi-project

Để xem task paths:

~~~bash
./gradlew tasks --all
./gradlew :api:build --dry-run
./gradlew :api:build -x :api:test --dry-run
~~~

Giả sử subproject tên **api** thực sự tồn tại. Tham số **-x :api:test** chỉ đích danh task test trong module api; những task Test khác như **:worker:integrationTest** không tự biến mất vì cách chỉ định này. Tùy đường dependency giữa modules, các task cần thiết ở subproject khác vẫn có thể được chọn.

Nếu muốn bỏ **tất cả Test tasks** trong một mục đích đặc biệt, không nên chọn bừa nhiều -x tên task; hãy thiết kế task lifecycle/phân nhóm rõ ràng và xem graph. Một số plugin cung cấp nhiệm vụ verification khác không phải Test task: static checks, code generation validation, lint, vulnerability scanning. Bỏ test không đồng nghĩa mọi kiểm tra đều bị vô hiệu.

## 14. Kiểm tra log/report trước khi kết luận đã test

### 14.1. Maven

Trong project Java Maven chuẩn:

~~~text
target/classes/           # main classes
target/test-classes/      # test classes, nếu đã compile
target/surefire-reports/  # Surefire reports khi unit test được chạy
target/failsafe-reports/  # Failsafe reports nếu plugin IT đã chạy
~~~

Kiểm tra thứ tự goal trong output:
- **compiler:compile**
- **compiler:testCompile**
- **surefire:test**
- **failsafe:integration-test** / **failsafe:verify** (nếu cấu hình)
- **jar:jar**, **spring-boot:repackage** (nếu là Maven Boot application)

Một report có thể còn từ lần build trước nếu không clean. Với một build có **-Dmaven.test.skip=true**, thiếu test-classes sau clean là điều có thể mong đợi; với **-DskipTests**, test-classes thường có nhưng không có report test mới. **Không** tuyên bố test PASS vì package goal kết thúc thành công.

### 14.2. Gradle

Trong Java Gradle project thông thường:

~~~text
build/classes/java/main/
build/classes/java/test/
build/test-results/test/
build/reports/tests/test/
build/libs/
~~~

Xem output task **:test** và trạng thái. Nếu Gradle -x test, task test không có trong execution graph của lệnh được xét. Nếu task có trạng thái **SKIPPED** vì **onlyIf** hoặc disabled, nó có mặt nhưng không thực thi actions. Nếu có **UP-TO-DATE** hoặc **FROM-CACHE**, cần xét inputs/cache và chính sách CI.

Với pipeline release, kiểm tra **báo cáo kiểm thử thuộc commit/build id hiện tại**, không chỉ sự tồn tại của một thư mục report.

## 15. Bảng quyết định: chọn lệnh nào cho mục đích nào?

| Nhu cầu | Maven | Gradle | Điều cần chấp nhận |
| --- | --- | --- | --- |
| Chạy unit tests và package | **./mvnw clean verify** | **./gradlew clean build** | Tốn thời gian hơn; thực sự kiểm tra test |
| Package nhưng vẫn compile test | **./mvnw clean package -DskipTests** | Cấu hình **test.onlyIf** để skip actions khi cần | Không chứng minh assertions PASS |
| Package và bỏ cả test compilation | **./mvnw clean package -Dmaven.test.skip=true** | **./gradlew clean build -x test** trong cấu trúc tiêu chuẩn | Có thể che lỗi test source |
| Chỉ tạo executable JAR để smoke test | **./mvnw package** (thường chạy tests trừ khi cấu hình khác) | **./gradlew bootJar** | Không suy luận test nào đã chạy từ tên task |
| Chạy một test cụ thể | **./mvnw test -Dtest=CalculatorTest** | **./gradlew test --tests ...** | Chỉ có subset được kiểm tra |
| Skip integration tests Failsafe nhưng giữ unit tests | **./mvnw verify -DskipITs** | Exclude/onlyIf đúng custom **integrationTest** task | Phải xem plugin version và graph |
| Xem trước task list không thực thi task actions | Maven: effective POM/lifecycle/plugin help | **./gradlew build --dry-run** | Đây là kế hoạch, không phải test evidence |

Trong bảng, **-x test** không được coi là tương đương tuyệt đối với **maven.test.skip**: một bên thay **Gradle graph**, một bên là **Maven property** được một số plugin tôn trọng. Hai cách có thể tạo hiệu ứng tương tự trong một Java project tiêu chuẩn, nhưng có khác biệt ở custom tasks, integration tests và source sets.

## 16. Những lỗi và hiểu nhầm phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| **-DskipTests** vẫn FAIL ở **testCompile** | Test source lỗi; skipTests chỉ bỏ Surefire execution | Maven log, test compiler errors |
| **-Dmaven.test.skip=true** PASS nhưng test source không compile | Đã bỏ test compilation | Bỏ cờ rồi chạy **./mvnw clean test** |
| **./gradlew build -x test** PASS dù test assertion sai | Task test bị loại khỏi graph | Chạy **./gradlew test**, xem báo cáo |
| **./gradlew build -x test** vẫn chạy compileTestJava | Task khác còn phụ thuộc compileTestJava | So sánh **--dry-run**, inspect graph |
| **-DskipTests** nhưng integration tests vẫn chạy | Failsafe 3.6+ không bind skipTests CLI; hoặc IT plugin khác | Xem Failsafe version, config và logs |
| **-DskipITs** nhưng unit tests vẫn chạy | Đúng mục đích: skip Failsafe IT, không skip Surefire unit tests | Xem surefire-reports/failsafe-reports |
| **-x test** nhưng integrationTest vẫn chạy | integrationTest là task riêng | Xem **tasks --all** và task paths |
| Log **SKIPPED** ở Gradle | Task có thể bị onlyIf/disabled/NO-SOURCE hoặc đang --dry-run | Đọc task outcome và cờ CLI |
| Thấy report khi đã skip tests | Có thể là report cũ vì chưa clean hoặc task khác sinh ra | Đối chiếu timestamp, build id, task logs |
| Chạy **bootJar** không thấy unit test | bootJar không mặc nhiên phụ thuộc test task | Gọi **build** hoặc **test** rõ ràng |
| Tests báo PASS nhưng build vẫn FAIL | Plugin khác như packaging/quality/integration test thất bại | Xem đúng task/goal lỗi |
| Maven **mvn test -DskipTests=false** vẫn không chạy tests | Không phát hiện tests, custom config, tests absent, profile/plugin thay đổi | Maven Surefire config, test discovery |
| CI xanh sau khi bật ignoreFailures | Test có thể fail nhưng không làm build đỏ | Đọc report thay vì chỉ đọc exit code |

**Nguyên tắc xử lý:** xác định **lỗi trong compile main, compile test, execute unit tests, execute integration tests, package hay verification khác**. Chỉ dùng skip sau khi biết chính xác đang bỏ phần nào; đừng dùng skip làm giải pháp lâu dài cho một lỗi test thực.

## 17. Checklist thực hành an toàn trong CI và release

- [ ] Xác định công cụ: Maven hay Gradle; không trộn cờ của hai CLI.
- [ ] Với Maven, phân biệt **-DskipTests** (bỏ chạy Surefire) và **-Dmaven.test.skip=true** (bỏ test compilation và Surefire/Failsafe execution).
- [ ] Nếu dùng Failsafe, xác định phiên bản; **3.6+** dùng **-DskipITs** để skip integration tests, **-DskipTests** chỉ ảnh hưởng Surefire theo mặc định.
- [ ] Với Gradle, hiểu **-x test** loại graph task và các dependency chỉ dùng cho task đó, không tự loại custom Test tasks khác.
- [ ] Khi muốn test vẫn compile nhưng không chạy, cân nhắc **onlyIf** có điều kiện và kiểm tra graph; tránh disable test vĩnh viễn.
- [ ] Không coi **BUILD SUCCESSFUL** hoặc JAR được tạo thành bằng chứng tests đã PASS nếu cờ skip hiện diện.
- [ ] Phân biệt test source output, test reports mới và các output đã cũ/từ cache.
- [ ] CI release có bước verification bắt buộc, lưu test reports và có kiểm soát thay đổi cờ skip.
- [ ] Sau khi debug bằng skip, hoàn tác cờ và chạy lại **test + integration tests** phù hợp trước release.
- [ ] Nếu chỉ cần tăng tốc vòng dev, thử **chạy subset tests**, incremental build hoặc test caching thay vì bỏ mọi kiểm thử.

## 18. Tự đánh giá nhanh

**Câu 1.** Mã unit test có lỗi cú pháp. Vì sao **./mvnw package -DskipTests** vẫn có thể FAIL?

**Trả lời:** Vì Compiler Plugin vẫn biên dịch test source ở phase test-compile; skipTests chỉ yêu cầu Surefire không thực thi tests. Muốn bỏ cả test compilation (chỉ khi có lý do hợp lệ) dùng **-Dmaven.test.skip=true**.

**Câu 2.** Một lần **./gradlew clean build -x test** PASS. Có nghĩa compileTestJava đã chạy và không có lỗi?

**Trả lời:** Không. Với Java plugin chuẩn, compileTestJava có thể không thuộc graph khi test bị loại. Cần xem output tasks, hoặc chạy **./gradlew testClasses**/**./gradlew test** để xác minh test source.

**Câu 3.** Với Failsafe 3.6+, **-DskipTests** có chắc skip integration tests không?

**Trả lời:** Không. Từ 3.6.0, Failsafe không còn bind tham số skipTests với CLI property skipTests. Dùng **-DskipITs=true** để skip Failsafe ITs; kiểm tra version/config thật.

**Câu 4.** Để skip test execution trong Gradle nhưng vẫn cho compiler kiểm tra test source, nên cân nhắc gì?

**Trả lời:** Điều kiện **test.onlyIf** có thể bỏ test actions mà vẫn để dependencies như compileTestJava tham gia graph. Cần kiểm tra graph trong project cụ thể. **-x test** thường loại cả các task chỉ phục vụ test.

**Câu 5.** Có nên giữ **-Dmaven.test.skip=true** trong CI release vì build nhanh hơn?

**Trả lời:** Không nên: CI release mất tín hiệu compile test source và chạy unit/integration tests. Chỉ cho phép ngoại lệ có lý do, ghi nhận và chặn phát hành nếu các bước test bắt buộc chưa đạt.

**Câu 6.** Nếu Gradle **bootJar** tạo thành công executable JAR, có chắc unit tests đã chạy?

**Trả lời:** Không. **bootJar** thường là packaging task và không phụ thuộc task test; cần chạy **test**, **check** hoặc **build** theo chính sách xác minh của project.

**Câu 7.** Maven **-DskipTests** và Gradle **-x test** có tương đương tuyệt đối không?

**Trả lời:** Không. Maven skipTests là property do Surefire đọc, thường vẫn compile test; Gradle -x loại test task và những dependencies chỉ phục vụ nó khỏi graph. Cần phân tích từng plugin/task và mỗi suite test.

## 19. Kết luận và tài liệu tham khảo

Ba cách viết dễ nhớ:

~~~text
MAVEN -DskipTests
    -> biên dịch main: có
    -> biên dịch test: có
    -> chạy Surefire tests: không

MAVEN -Dmaven.test.skip=true
    -> biên dịch main: có
    -> biên dịch test bằng Compiler Plugin: không
    -> chạy Surefire/Failsafe tests: không

GRADLE build -x test
    -> loại task test khỏi graph
    -> các dependencies chỉ cần cho test có thể cũng bị loại
    -> task khác (ví dụ integrationTest) không tự động bị loại
~~~

Các dòng mô tả hành vi tiêu chuẩn của công cụ, không phải quy tắc bao phủ mọi plugin. Với Spring Boot, điều quan trọng nhất là biết **mình đang chứng minh điều gì**: một artifact có thể được đóng gói thành công dù tests không chạy, và **đóng gói thành công không đồng nghĩa với kiểm thử thành công**.

### Tài liệu chính thức

- Apache Maven Surefire — Skipping Tests: https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html
- Apache Maven Surefire — Goal Test and skipTests property: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Apache Maven Failsafe — Skipping Tests (bao gồm thay đổi 3.6.0): https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html
- Apache Maven Failsafe — integration-test goal parameters: https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html
- Apache Maven Compiler Plugin — testCompile / maven.test.skip: https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html
- Apache Maven — Introduction to Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle — Testing in Java and JVM Projects (Skipping the Tests): https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle — Command-Line Interface (-x / --exclude-task): https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Java Plugin Task Dependencies: https://docs.gradle.org/current/userguide/java_plugin.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/

# Không có kiểm thử được chạy: phát hiện cấu hình sai

Một lệnh build có thể kết thúc với trạng thái thành công nhưng không chạy bất kỳ kiểm thử nào. Điều này thường xảy ra khi thư mục test không đúng, tên lớp không khớp quy tắc discovery, framework hoặc engine chưa được cấu hình, task bị loại trừ, profile tắt kiểm thử hoặc lệnh build chưa đi tới giai đoạn chạy test.

Thông báo “BUILD SUCCESSFUL” hoặc “BUILD SUCCESS” chỉ cho biết các bước được yêu cầu đã hoàn tất theo cấu hình hiện tại. Nếu số lượng test bằng 0, kết quả đó không chứng minh hành vi của ứng dụng đã được kiểm tra. Trong CI, tình trạng này đặc biệt nguy hiểm vì pipeline có thể màu xanh dù bộ kiểm thử không được phát hiện.

Bài học này trình bày cách xác định nguyên nhân “không có kiểm thử được chạy” trong Maven và Gradle, cách đọc trạng thái và báo cáo, cách cấu hình để phát hiện tình trạng không có test, và cách bảo đảm pipeline thực sự thực hiện những kiểm tra cần thiết.

## 1. Phân biệt các trạng thái khi test không chạy

Không phải mọi trường hợp không thực thi test đều có cùng nguyên nhân. Trước khi sửa cấu hình, cần xác định công cụ đang báo điều gì.

| Trạng thái | Ý nghĩa | Việc cần kiểm tra |
| --- | --- | --- |
| Không tìm thấy test | Công cụ không phát hiện lớp hoặc phương thức test phù hợp. | Thư mục nguồn, tên lớp, annotation, framework và engine. |
| Không có nguồn test | Không có tệp nguồn trong source set hoặc thư mục test đã cấu hình. | Đường dẫn source set và module đang build. |
| Test bị skip | Task hoặc plugin được yêu cầu nhưng điều kiện hay tùy chọn khiến nó không chạy. | Cờ skip, profile, onlyIf, enabled và log. |
| Task không được chọn | Lệnh build không yêu cầu test hoặc test bị loại khỏi task graph/lifecycle. | Lệnh gọi, dependency graph, phase và tùy chọn loại trừ. |
| Test đã up-to-date | Công cụ dùng kết quả test trước đó vì đầu vào và đầu ra không đổi. | Lịch sử task, đầu vào, đầu ra và báo cáo hiện có. |
| Test được phát hiện nhưng không có test case chạy | Framework tìm thấy lớp nhưng không có phương thức test hợp lệ hoặc điều kiện chạy không thỏa mãn. | Annotation, engine, điều kiện test và báo cáo. |
| Test có chạy nhưng báo cáo rỗng hoặc không cập nhật | Có thể đang xem nhầm báo cáo cũ, sai module hoặc sai task. | Thời gian tạo báo cáo, đường dẫn output và task thực tế. |

Một task hiển thị **NO-SOURCE** thường có nghĩa không có nguồn phù hợp để xử lý. **SKIPPED** cho biết task hoặc phần công việc bị bỏ qua vì một lý do nào đó. **UP-TO-DATE** có nghĩa task có kết quả hiện tại được xem là còn hợp lệ. Ba trạng thái này khác nhau và không nên gộp chung thành “test pass”.

## 2. Quy trình chẩn đoán tổng quát

Khi build báo không có test, hãy đi từ lệnh được gọi đến báo cáo được tạo:

1. Xác nhận lệnh build có yêu cầu chạy test hay không.
2. Xác định module hoặc project nào thực sự được build.
3. Kiểm tra source directory và test source set.
4. Kiểm tra test class đã được biên dịch hay chưa.
5. Kiểm tra tên lớp, annotation và framework.
6. Kiểm tra engine/provider được nạp ở runtime.
7. Kiểm tra filter, include/exclude, profile và các cờ skip.
8. Đọc log và báo cáo test của đúng module.
9. Cấu hình build để không âm thầm chấp nhận số lượng test bằng 0 nếu dự án yêu cầu test.

Sơ đồ chẩn đoán:

    Lệnh build có yêu cầu test?
          |
          +-- Không --> Chọn task/phase phù hợp
          |
          +-- Có
               |
               v
        Có test source?
          |
          +-- Không --> Kiểm tra source directory/module
          |
          +-- Có
               |
               v
        Test class đã biên dịch?
          |
          +-- Không --> Kiểm tra test compiler và lỗi compile
          |
          +-- Có
               |
               v
        Framework/engine nhận diện test?
          |
          +-- Không --> Kiểm tra dependency, provider, annotation
          |
          +-- Có
               |
               v
        Filter/điều kiện có loại hết test?
          |
          +-- Có --> Kiểm tra include/exclude/skip/profile
          |
          +-- Không --> Đọc báo cáo và log của đúng task

## 3. Kiểm tra lệnh build có thực sự yêu cầu chạy test

Một nguyên nhân đơn giản là người phát triển chạy một mục tiêu chỉ biên dịch hoặc đóng gói một phần.

### Với Maven

Maven có lifecycle mặc định. Một số phase quan trọng:

    validate
    compile
    test
    package
    verify
    install
    deploy

Lệnh:

    mvn compile

chỉ yêu cầu đến phase compile. Nó biên dịch mã nguồn chính nhưng không chạy unit test.

Lệnh:

    mvn test

đi tới phase test, bao gồm các phase trước đó và thực thi test được cấu hình trong Maven Surefire Plugin.

Lệnh:

    mvn package

đi qua phase test trước package, vì vậy unit test được cấu hình trong lifecycle thông thường có cơ hội chạy. Nếu test vẫn không chạy, cần kiểm tra plugin, profile và cờ skip.

Đối với integration test, dự án thường dùng Maven Failsafe Plugin và các phase integration-test, verify. Có thể chạy:

    mvn verify

Chỉ chạy compile hoặc package không thay thế các kiểm tra bổ sung được cấu hình ở phase verify.

### Với Gradle

Với plugin Java, các task thường gặp:

- **compileJava:** biên dịch mã nguồn chính.
- **compileTestJava:** biên dịch mã nguồn test.
- **testClasses:** chuẩn bị các lớp test.
- **test:** thực thi test.
- **check:** gom các bước kiểm tra, thường phụ thuộc vào test.
- **build:** mục tiêu tổng hợp gồm assemble và check.

Lệnh:

    ./gradlew compileJava

không yêu cầu chạy test.

Lệnh:

    ./gradlew test

yêu cầu task test và các task phụ thuộc.

Lệnh:

    ./gradlew check
    ./gradlew build

thường bao gồm test theo cấu hình plugin Java tiêu chuẩn. Tuy nhiên, task có thể bị loại trừ hoặc vô hiệu hóa bởi cấu hình của dự án.

Trên Windows, dùng **gradlew.bat** thay cho **./gradlew**.

## 4. Kiểm tra đúng module hoặc project

Trong dự án nhiều module, test có thể nằm ở module con thay vì root project.

Ví dụ Maven:

    product-app/
      pom.xml
      api/
        pom.xml
        src/test/java/
      service/
        pom.xml
        src/test/java/

Nếu root POM chỉ là aggregator với packaging pom, root project có thể không có test riêng. Các test nằm trong api và service. Khi build, hãy xác nhận hai module đó có nằm trong danh sách modules của POM gốc và có được đưa vào reactor hay không.

Có thể chạy một module cụ thể cùng các dependency cần thiết:

    mvn -pl service -am test

Trong đó **-pl** chọn project, còn **-am** yêu cầu Maven build thêm các project cần thiết mà project đã chọn phụ thuộc vào.

Với Gradle multi-project:

    product-app/
      settings.gradle
      app/
      domain/

Có thể chạy test ở module cụ thể:

    ./gradlew :app:test
    ./gradlew :domain:test

Lệnh **./gradlew test** từ root có thể chạy các task test được chọn trong các project theo cấu hình. Nếu module không được include trong settings.gradle, task của module đó không tham gia build.

Hãy xem task path đầy đủ trong log, ví dụ **:service:test** hoặc **:app:test**, để chắc chắn đang kiểm tra đúng module.

## 5. Kiểm tra thư mục chứa mã nguồn test

Quy ước mặc định phổ biến:

| Công cụ | Mã nguồn chính | Mã nguồn test | Tài nguyên test |
| --- | --- | --- | --- |
| Maven | src/main/java | src/test/java | src/test/resources |
| Gradle Java Plugin | src/main/java | src/test/java | src/test/resources |

Ví dụ:

    src/
      main/
        java/
          com/example/OrderService.java
      test/
        java/
          com/example/OrderServiceTest.java
        resources/
          orders-fixture.json

Nếu đặt test trong **src/main/java**, công cụ có thể coi đó là mã nguồn ứng dụng thay vì test. Nếu đặt test ở thư mục tùy chỉnh nhưng không khai báo source directory hoặc source set tương ứng, công cụ sẽ không phát hiện chúng.

### Maven: testSourceDirectory

Maven mặc định dùng **src/test/java**. Nếu dự án đặt test ở đường dẫn khác, cần cấu hình:

    <build>
        <testSourceDirectory>tests/java</testSourceDirectory>
    </build>

Đường dẫn được tính tương đối với thư mục project. Nếu thư mục test có nhiều nguồn hoặc cấu trúc đặc biệt, có thể cần plugin hỗ trợ thêm source root.

### Gradle: test source set

Gradle Java Plugin mặc định tạo source set **test**. Nếu test ở thư mục khác, cấu hình source set:

    sourceSets {
        test {
            java {
                srcDirs = ['tests/java']
            }
            resources {
                srcDirs = ['tests/resources']
            }
        }
    }

Nếu ghi đè srcDirs, hãy bảo đảm không vô tình loại bỏ thư mục mặc định hoặc các source root khác mà dự án cần. Sau khi cấu hình, kiểm tra task compileTestJava có thực sự nhìn thấy các tệp test.

## 6. Kiểm tra test class đã được biên dịch chưa

Test source có thể tồn tại nhưng chưa được biên dịch do source directory sai, lỗi compiler, task test compilation bị tắt hoặc build chỉ chạy một phase/task không bao gồm test.

Với Maven, test class thường nằm trong:

    target/test-classes/

Với Gradle, test class thường nằm trong:

    build/classes/java/test/

Kiểm tra thư mục này giúp phân biệt lỗi discovery với lỗi test compile.

Nếu thư mục trống:

- Xem log compileTestJava hoặc Maven test-compile.
- Kiểm tra source directory.
- Kiểm tra lỗi biên dịch test.
- Kiểm tra tùy chọn skip test compilation.
- Kiểm tra module đang được build.

Nếu đã có class file, tiếp tục kiểm tra tên lớp, annotation và framework.

## 7. Kiểm tra tên test theo quy tắc discovery

Một số plugin dùng quy tắc đặt tên để tìm test. Đặc biệt, Maven Surefire có các mẫu tên mặc định phổ biến:

    **/Test*.java
    **/*Test.java
    **/*Tests.java
    **/*TestCase.java

Ví dụ các tên thường được phát hiện:

    TestOrderService.java
    OrderServiceTest.java
    OrderServiceTests.java
    OrderServiceTestCase.java

Nếu lớp có tên **OrderServiceSpec.java** hoặc **OrderServiceCheck.java**, Surefire có thể không chọn theo mẫu mặc định. Có thể cấu hình include:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
            <includes>
                <include>**/*Spec.java</include>
                <include>**/*Test.java</include>
            </includes>
        </configuration>
    </plugin>

Khi khai báo includes tùy chỉnh, cần giữ lại tất cả mẫu mà dự án muốn hỗ trợ. Nếu chỉ thêm một mẫu mà quên các mẫu mặc định cần thiết, một số test có thể biến mất khỏi discovery.

Gradle không dùng cùng bộ mẫu mặc định của Maven Surefire. Gradle giao việc phát hiện cho test framework/provider và quét các lớp test đã biên dịch theo framework đang cấu hình. Tuy nhiên, các mẫu include/exclude của task Test và test filter vẫn có thể loại lớp khỏi quá trình chạy.

Không nên đổi tên tất cả test theo cảm tính. Trước tiên hãy xem quy tắc discovery của plugin và framework mà dự án thực sự sử dụng.

## 8. Kiểm tra annotation và framework

Một lớp có tên kết thúc bằng Test chưa chắc đã là test hợp lệ. Framework cần nhận diện annotation hoặc cấu trúc lớp theo quy tắc của nó.

### JUnit 4

Ví dụ JUnit 4:

    import org.junit.Test;
    import static org.junit.Assert.assertEquals;

    public class OrderServiceTest {
        @Test
        public void calculatesTotal() {
            assertEquals(10, 5 + 5);
        }
    }

Lớp cần dùng annotation của JUnit 4 và có dependency JUnit 4 trên test classpath. Với JUnit 4, các test method theo mô hình thông thường phải là public và không nhận tham số.

### JUnit Jupiter (JUnit 5)

Ví dụ JUnit Jupiter:

    import org.junit.jupiter.api.Test;
    import static org.junit.jupiter.api.Assertions.assertEquals;

    class OrderServiceTest {
        @Test
        void calculatesTotal() {
            assertEquals(10, 5 + 5);
        }
    }

Annotation **org.junit.jupiter.api.Test** khác với **org.junit.Test** của JUnit 4. Dùng nhầm import có thể khiến runner không nhận diện phương thức như mong đợi.

### TestNG

Ví dụ TestNG:

    import org.testng.annotations.Test;
    import org.testng.Assert;

    public class OrderServiceTest {
        @Test
        public void calculatesTotal() {
            Assert.assertEquals(5 + 5, 10);
        }
    }

Nếu dự án viết test bằng TestNG nhưng build vẫn cấu hình runner JUnit, test có thể không được phát hiện. Cần cấu hình đúng framework ở Maven Surefire hoặc Gradle Test task.

## 9. Kiểm tra dependency và test engine

Có annotation trong mã nguồn chưa đủ; test framework phải có mặt trên classpath phù hợp.

### JUnit 5 cần engine

JUnit 5 tách API, engine và platform. Test viết bằng JUnit Jupiter cần Jupiter engine để thực thi. Dùng dependency tổng hợp **junit-jupiter** thường đưa API, params và engine vào cùng dependency.

Gradle:

    dependencies {
        testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
        testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
    }

    tasks.named('test', Test) {
        useJUnitPlatform()
    }

Launcher nên được căn phiên bản tương thích với JUnit Platform mà dự án dùng. Cấu hình chính xác phụ thuộc phiên bản Gradle và JUnit.

Nếu chỉ khai báo junit-jupiter-api mà thiếu engine, test có thể biên dịch được nhưng không có engine phù hợp để thực thi.

### Gradle phải bật JUnit Platform

Gradle Java Plugin thường dùng JUnit 4 làm framework mặc định. Để chạy JUnit Jupiter, cần cấu hình:

    tasks.test {
        useJUnitPlatform()
    }

Nếu bỏ cấu hình này, test viết bằng JUnit 5 có thể không được chạy dù dependency và mã nguồn tồn tại.

Đối với JUnit 4:

    dependencies {
        testImplementation 'junit:junit:4.13.2'
    }

Không cần gọi useJUnitPlatform() nếu dự án chạy JUnit 4 bằng runner mặc định.

Đối với TestNG:

    dependencies {
        testImplementation 'org.testng:testng:7.10.2'
    }

    tasks.test {
        useTestNG()
    }

### Maven cần Surefire/provider phù hợp

Với JUnit Jupiter, có thể cấu hình:

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>

Surefire phiên bản hiện đại có hỗ trợ JUnit Platform. Với dự án dùng JUnit 5, cần bảo đảm plugin/provider và dependency engine tương thích. Nếu dùng phiên bản plugin quá cũ, test có thể không được nhận diện dù mã nguồn biên dịch.

Nếu một dự án trộn JUnit 4 và JUnit 5 trên JUnit Platform, có thể cần JUnit Vintage Engine để chạy các test JUnit 4 thông qua platform. Không nên thêm Vintage nếu dự án không cần tương thích với test JUnit 4.

## 10. Kiểm tra filter, include và exclude

Test có thể bị loại khỏi discovery bởi một bộ lọc.

### Gradle test filter

Ví dụ:

    ./gradlew test --tests com.example.OrderServiceTest

Lệnh này chỉ chạy test khớp filter. Nếu tên lớp hoặc package sai, không có test nào phù hợp.

Có thể chạy một phương thức:

    ./gradlew test --tests 'com.example.OrderServiceTest.calculatesTotal'

Nếu filter quá hẹp hoặc viết sai chữ hoa/chữ thường, kết quả có thể là không tìm thấy test phù hợp. Kiểm tra lại tên đầy đủ của lớp và phương thức.

### Gradle include/exclude

Task Test có thể cấu hình:

    tasks.test {
        include '**/*Test.class'
        exclude '**/integration/**'
    }

Nếu mẫu include không khớp đường dẫn class file thực tế hoặc exclude quá rộng, test có thể bị loại. Khi sửa filter, cần xem đường dẫn tương đối trong thư mục testClassesDirs.

Gradle có thuộc tính **failOnNoMatchingTests** để kiểm soát việc task thất bại khi một test filter không khớp test nào. Thuộc tính này hữu ích cho lệnh chạy test được chọn cụ thể. Nó không thay thế kiểm tra source set rỗng hoặc bảo đảm rằng toàn bộ bộ test dự kiến đã được phát hiện.

### Maven -Dtest

Surefire hỗ trợ chọn test theo tên:

    mvn -Dtest=OrderServiceTest test

Chạy nhiều lớp:

    mvn -Dtest=OrderServiceTest,PaymentServiceTest test

Nếu filter không khớp tên lớp, Maven có thể báo không tìm thấy test được chỉ định. Hãy kiểm tra tên lớp và cấu hình include/exclude của Surefire.

Maven Surefire cũng có thể được cấu hình bằng:

    <includes>
        <include>**/*Test.java</include>
    </includes>

    <excludes>
        <exclude>**/slow/**</exclude>
    </excludes>

Một exclude quá rộng có thể vô tình loại hết test. Đặc biệt, hãy kiểm tra profile và cấu hình kế thừa nếu include/exclude chỉ xuất hiện ở một môi trường.

## 11. Kiểm tra các tùy chọn skip

Một build có thể hoàn tất mà không chạy test vì cờ skip được truyền trên dòng lệnh hoặc cấu hình trong build file.

### Maven skipTests

Lệnh:

    mvn package -DskipTests

thường yêu cầu Surefire bỏ qua việc thực thi test nhưng vẫn biên dịch test. Đây là lựa chọn thường dùng khi muốn đóng gói nhanh nhưng không chạy test trong lần đó.

### Maven maven.test.skip

Lệnh:

    mvn package -Dmaven.test.skip=true

bỏ qua cả biên dịch test và thực thi test đối với các plugin Maven phổ biến hỗ trợ thuộc tính này, gồm Maven Compiler Plugin và Surefire. Vì test không được biên dịch, lỗi mã nguồn test cũng có thể không được phát hiện.

### Cấu hình trong POM hoặc profile

Tìm các cấu hình như:

    <skipTests>true</skipTests>

    <maven.test.skip>true</maven.test.skip>

Chúng có thể nằm trong POM cha, profile hoặc cấu hình plugin. Một profile chỉ được bật trên CI hoặc local cũng có thể làm thay đổi hành vi test.

Xem profile đang hoạt động:

    mvn help:active-profiles

Xem cấu hình hợp nhất:

    mvn help:effective-pom

### Gradle enabled và onlyIf

Task test có thể bị vô hiệu hóa:

    tasks.named('test') {
        enabled = false
    }

Hoặc chỉ chạy khi điều kiện đúng:

    tasks.named('test') {
        onlyIf {
            project.hasProperty('runTests')
        }
    }

Nếu lệnh không truyền property runTests, task bị skip:

    ./gradlew test

Muốn điều kiện đúng:

    ./gradlew test -PrunTests

Không nên để điều kiện mặc định false cho một gate kiểm thử bắt buộc. Nếu chỉ muốn tùy chọn bỏ qua test trong local, hãy bảo đảm pipeline CI không sử dụng cấu hình đó ngoài ý muốn.

## 12. Kiểm tra Maven Surefire và Failsafe

Maven thường dùng hai plugin cho hai loại test khác nhau:

| Plugin | Mục đích | Phase thường gắn |
| --- | --- | --- |
| Surefire | Unit test | test |
| Failsafe | Integration test | integration-test và verify |

Surefire dùng các mẫu tên mặc định phổ biến như:

    **/Test*.java
    **/*Test.java
    **/*Tests.java
    **/*TestCase.java

Failsafe thường dùng:

    **/IT*.java
    **/*IT.java
    **/*ITCase.java

Ví dụ một lớp **OrderServiceIT** có thể được Failsafe chọn, nhưng không được Surefire chọn theo mẫu mặc định. Nếu chạy **mvn test**, integration test có thể không chạy vì dự án đã cấu hình chúng cho Failsafe ở các phase sau. Chạy:

    mvn verify

để đi qua các phase integration-test và verify.

### Failsafe phải được liên kết đúng lifecycle

Ví dụ cấu hình:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.2.5</version>
        <executions>
            <execution>
                <goals>
                    <goal>integration-test</goal>
                    <goal>verify</goal>
                </goals>
            </execution>
        </executions>
    </plugin>

Failsafe tách việc thực thi integration test khỏi việc đánh giá kết quả cuối ở verify, giúp báo cáo và xử lý teardown được thực hiện theo lifecycle phù hợp. Nếu chỉ gọi mvn test, các goal này chưa được yêu cầu.

## 13. Cấu hình để build không âm thầm chấp nhận zero tests

Nếu dự án yêu cầu test phải tồn tại, nên cấu hình build để số lượng test bằng 0 trở thành lỗi cần xử lý.

### Maven Surefire failIfNoTests

Surefire có tham số **failIfNoTests**. Có thể cấu hình:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
            <failIfNoTests>true</failIfNoTests>
        </configuration>
    </plugin>

Khi không có test nào được phát hiện, Surefire có thể làm build thất bại thay vì chỉ ghi thông báo không có test. Hành vi và phạm vi áp dụng cần được kiểm tra theo phiên bản plugin đang dùng.

Nếu một module hợp lệ không có test, bật failIfNoTests ở mọi module có thể làm build thất bại không mong muốn. Có thể cấu hình theo module hoặc profile, hoặc chỉ áp dụng cho những module mà test là yêu cầu bắt buộc.

### Gradle failOnNoMatchingTests

Gradle Test task có thuộc tính **failOnNoMatchingTests** để làm task thất bại khi filter được chỉ định không khớp test nào. Ví dụ:

    tasks.named('test', Test) {
        failOnNoMatchingTests = true
    }

Đây là bảo vệ hữu ích khi chạy test theo filter, chẳng hạn trong CI chạy riêng một nhóm test. Tuy nhiên, thuộc tính này không có nghĩa tự động thất bại trong mọi trường hợp source set rỗng hoặc không có test nào trong project. Cần kiểm tra thêm test report và source set.

### Tự kiểm tra số lượng test

Một pipeline có thể đọc báo cáo XML và xác nhận số test đã chạy lớn hơn 0. Nếu dự án có nhiều module, nên kiểm tra theo module hoặc theo nhóm test bắt buộc để một module rỗng hợp lệ không che giấu việc module quan trọng không chạy test.

Điều kiện “ít nhất một test” là mức tối thiểu. Dự án lớn nên xác định phạm vi test dự kiến, ví dụ unit test của module domain, integration test của service và smoke test của ứng dụng.

## 14. Đọc log và báo cáo test

Không nên chỉ dựa vào dòng tổng kết build. Hãy kiểm tra task thực tế, số lượng test và báo cáo được tạo.

### Báo cáo Gradle

Với Java Plugin, báo cáo HTML mặc định thường nằm ở:

    build/reports/tests/test/index.html

Báo cáo XML thường nằm trong:

    build/test-results/test/

Khi chạy test ở module con, đường dẫn thường nằm dưới thư mục build của module đó, ví dụ:

    app/build/reports/tests/test/index.html

Mở báo cáo và kiểm tra tổng số tests, failures, skipped và danh sách class/method. Nếu số test là 0, hãy xác định đó là module không có test theo thiết kế hay do discovery sai.

Có thể chạy:

    ./gradlew test --info --console=plain

Log **--info** cung cấp thêm thông tin về task và test execution. Khi cần xem task nào được chọn:

    ./gradlew test --dry-run

Dry-run chỉ hiển thị kế hoạch, không thực thi test. Không dùng kết quả dry-run làm bằng chứng test đã chạy.

### Báo cáo Maven Surefire

Surefire thường tạo báo cáo trong:

    target/surefire-reports/

Tệp XML và TXT có thể cho biết lớp test được phát hiện, số test, số failure, error và skipped. Trong multi-module, mỗi module có thư mục target riêng.

### Báo cáo Maven Failsafe

Failsafe thường tạo báo cáo trong:

    target/failsafe-reports/

Nếu integration test không chạy, kiểm tra plugin có được liên kết với lifecycle và lệnh có đi đến phase verify hay không.

### Báo cáo cũ

Một báo cáo HTML hoặc XML có thể còn từ lần build trước. Nếu task test không chạy ở lần hiện tại, báo cáo cũ vẫn có thể tồn tại và gây hiểu nhầm. Kiểm tra thời gian cập nhật, log của lần chạy hiện tại và kết quả sau một build sạch khi cần.

Không xóa báo cáo trước khi lưu lại bằng chứng cần điều tra. Khi cần xác nhận từ đầu, có thể dùng clean rồi chạy đúng task test.

## 15. Ví dụ chẩn đoán với Gradle

Giả sử dự án có test JUnit 5 trong:

    src/test/java/com/example/OrderServiceTest.java

Nhưng chạy:

    ./gradlew test

và báo không có test.

Kiểm tra theo từng lớp:

### Bước 1: Xác nhận task test được gọi

    ./gradlew test --dry-run

Nếu task không xuất hiện, kiểm tra task path, plugin Java và cấu hình task graph. Nếu task xuất hiện, tiếp tục.

### Bước 2: Kiểm tra test source và compile

    ./gradlew testClasses

Xem log compileTestJava và kiểm tra:

    build/classes/java/test/com/example/OrderServiceTest.class

Nếu class file không tồn tại, kiểm tra sourceSets, test source path và compiler.

### Bước 3: Kiểm tra JUnit Platform

Trong build.gradle:

    dependencies {
        testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
        testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
    }

    tasks.test {
        useJUnitPlatform()
    }

Nếu thiếu useJUnitPlatform(), Gradle có thể đang dùng framework mặc định không nhận diện JUnit Jupiter.

### Bước 4: Kiểm tra filter và điều kiện

Tìm các cấu hình include, exclude, onlyIf, enabled và tham số --tests. Chạy test lớp cụ thể:

    ./gradlew test --tests com.example.OrderServiceTest --info

Nếu filter không khớp, kiểm tra package và tên class thực tế.

### Bước 5: Xem báo cáo

Mở build/reports/tests/test/index.html và kiểm tra tổng số test. Nếu không có test nào, báo cáo sẽ giúp xác nhận task không tìm thấy test hay test bị bỏ qua.

## 16. Ví dụ chẩn đoán với Maven

Giả sử test JUnit Jupiter nằm trong:

    src/test/java/com/example/OrderServiceTest.java

Chạy:

    mvn test

nhưng Surefire báo không có test.

### Bước 1: Kiểm tra test đã biên dịch chưa

    mvn test-compile

Xác nhận lớp được tạo trong:

    target/test-classes/com/example/OrderServiceTest.class

Nếu không có class file, kiểm tra testSourceDirectory, test compiler và lỗi biên dịch.

### Bước 2: Kiểm tra dependency JUnit Jupiter

POM cần có dependency test phù hợp:

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.10.2</version>
        <scope>test</scope>
    </dependency>

Nếu chỉ có API mà không có engine, Surefire không có engine phù hợp để thực thi Jupiter test.

### Bước 3: Kiểm tra Surefire

Khai báo phiên bản plugin hỗ trợ JUnit Platform:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
    </plugin>

Sau đó chạy:

    mvn -Dtest=OrderServiceTest test

Nếu test được chọn, kiểm tra báo cáo trong target/surefire-reports.

### Bước 4: Kiểm tra profile và skip

    mvn help:active-profiles
    mvn help:effective-pom

Tìm skipTests, maven.test.skip, include/exclude và cấu hình plugin được kế thừa từ POM cha.

## 17. Những nguyên nhân thường gặp và dấu hiệu

| Nguyên nhân | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Chạy nhầm task/phase | Chỉ có compile hoặc package một phần, không thấy test task/goal. | Chạy Gradle test/check/build hoặc Maven test/verify theo mục tiêu. |
| Sai thư mục test | Source test tồn tại nhưng compileTestJava/test-compile không thấy nguồn. | Đặt vào src/test/java hoặc khai báo source set/testSourceDirectory. |
| Sai tên test với Surefire | Có class file nhưng Surefire không chọn lớp. | Đổi tên theo mẫu mặc định hoặc cấu hình includes phù hợp. |
| Sai annotation/import | Lớp được compile nhưng runner không nhận test method. | Dùng annotation của đúng framework. |
| Thiếu engine/provider | Test JUnit 5 biên dịch được nhưng không có engine thực thi. | Thêm Jupiter engine/dependency và dùng JUnit Platform. |
| Gradle chưa gọi useJUnitPlatform | Test Jupiter không được chạy như dự kiến. | Cấu hình test task dùng JUnit Platform. |
| TestNG nhưng cấu hình JUnit | Không có test phù hợp với runner. | Thêm TestNG dependency và cấu hình useTestNG hoặc Surefire provider. |
| Filter quá hẹp | Chạy toàn bộ có thể thấy test, nhưng lệnh lọc không khớp. | Kiểm tra tên lớp, package, phương thức và include/exclude. |
| Cờ skip | Log có thông báo test skipped hoặc plugin skip. | Bỏ cờ skip trong gate bắt buộc; kiểm tra cấu hình/profile. |
| Module không được chọn | Root build không chạy module chứa test. | Kiểm tra reactor/modules hoặc task path multi-project. |
| Test compile bị bỏ qua | Không có class trong test-classes. | Kiểm tra maven.test.skip hoặc cấu hình compileTestJava. |
| Báo cáo cũ | Report tồn tại nhưng thời gian không khớp lần build hiện tại. | Đối chiếu log và thời gian tạo report; chạy lại đúng task khi cần. |

## 18. Thiết kế CI để phát hiện cấu hình sai

Một pipeline chất lượng không nên coi số lượng test bằng 0 là thành công mặc định khi dự án yêu cầu test.

Có thể áp dụng:

- Chạy task hoặc phase test rõ ràng trong CI.
- Với Maven, dùng failIfNoTests ở module cần có test.
- Với Gradle, bật failOnNoMatchingTests cho các lệnh chạy test có filter.
- Kiểm tra báo cáo XML để xác nhận test count theo module hoặc nhóm bắt buộc.
- Lưu báo cáo test làm artifact của pipeline.
- Phân biệt unit test và integration test trong tên task/phase.
- Không dùng cờ skip ở pipeline bắt buộc.
- Kiểm tra profile, biến môi trường và điều kiện onlyIf ở môi trường CI.
- Thực hiện một bước smoke test để xác nhận pipeline không vô tình chạy một build rỗng.

Ví dụ pipeline có thể chia thành:

    compile
       |
       v
    unit tests
       |
       v
    integration tests
       |
       v
    package
       |
       v
    report/test-count gate

Thứ tự thực tế phụ thuộc công cụ build và quy trình của dự án. Điểm quan trọng là mỗi gate phải có bằng chứng đầu ra và điều kiện thành công rõ ràng.

Nếu một module không có test theo thiết kế, hãy ghi nhận ngoại lệ rõ ràng thay vì vô hiệu hóa kiểm tra zero tests cho toàn bộ build. Có thể kiểm tra test count ở cấp module quan trọng hoặc nhóm test cụ thể.

## 19. Phân biệt “không có test” với “test đã chạy nhưng tất cả bị skip”

Một test suite có thể được phát hiện nhưng không thực thi phương thức test do điều kiện:

- JUnit có @Disabled ở lớp hoặc phương thức.
- TestNG có enabled = false.
- Test có assumption không thỏa mãn.
- Điều kiện môi trường hoặc tag filter loại test.
- Test được cấu hình chỉ chạy ở một profile.

Trong trường hợp này, số lượng test được phát hiện có thể khác số lượng test thực sự chạy. Báo cáo thường tách riêng số tests, skipped, failures và errors. Hãy xem từng chỉ số thay vì chỉ nhìn tổng số.

Nếu tất cả test bị disable hoặc skip, pipeline cũng có thể không cung cấp mức kiểm chứng mong muốn. Cần xem lý do skip có hợp lệ trong môi trường hiện tại hay không.

Ví dụ JUnit Jupiter:

    @Disabled("Waiting for external test environment")
    @Test
    void connectsToService() {
        // test body
    }

Test này được phát hiện nhưng không chạy. Nếu môi trường CI đã sẵn sàng mà annotation Disabled vẫn còn, đó có thể là cấu hình hoặc mã test cần được cập nhật.

## 20. Checklist điều tra một build không chạy test

Khi gặp tình huống này, ghi lại các thông tin sau:

| Câu hỏi | Bằng chứng cần tìm |
| --- | --- |
| Lệnh có yêu cầu test? | Command line và task/phase trong log. |
| Đúng module chưa? | Module path, reactor summary hoặc Gradle task path. |
| Có test source? | src/test/java hoặc source set tùy chỉnh. |
| Test có biên dịch? | target/test-classes hoặc build/classes/java/test. |
| Đúng framework? | Import annotation và dependency test. |
| Có engine/provider? | Runtime test classpath và plugin version. |
| Discovery có lọc hết? | Include/exclude, --tests, -Dtest và naming patterns. |
| Có skip? | skipTests, maven.test.skip, onlyIf, enabled, profile. |
| Có test thực sự chạy? | Báo cáo XML/HTML, số tests và skipped. |
| Có thể build xanh với zero tests? | failIfNoTests, failOnNoMatchingTests và CI test-count gate. |

## 21. Nguyên tắc duy trì cấu hình test đáng tin cậy

- Giữ test ở source set chuẩn trừ khi có lý do rõ ràng để thay đổi.
- Đặt tên test theo quy tắc discovery của plugin hoặc cấu hình include rõ ràng.
- Dùng đúng annotation, framework và engine.
- Cố định phiên bản Maven Surefire/Failsafe và plugin test trong dự án.
- Cấu hình Gradle Test task theo framework đang dùng.
- Kiểm tra task/phase thực sự được gọi trong local và CI.
- Tránh đặt điều kiện mặc định khiến test bị skip âm thầm.
- Bật fail-on-zero-tests ở phạm vi mà dự án yêu cầu test.
- Đọc báo cáo để xác nhận số test, failure và skipped.
- Lưu log và báo cáo của đúng lần build đang điều tra.

Khi build báo không có kiểm thử được chạy, hãy xác định công cụ chưa tìm thấy test, không có nguồn, không có engine, bị filter, bị skip hay chưa được yêu cầu. Những nguyên nhân này cần cách sửa khác nhau. Chỉ khi test được phát hiện, thực thi theo cấu hình mong muốn và báo cáo cho thấy kết quả phù hợp, build mới cung cấp bằng chứng kiểm thử mà nhóm kỳ vọng.

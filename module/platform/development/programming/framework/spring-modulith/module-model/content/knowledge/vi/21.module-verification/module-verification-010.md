# Đưa verification vào test build

## Mục tiêu

Spring Modulith giúp xác minh các ranh giới module bằng cách phân tích cấu trúc package và các phụ thuộc thể hiện trong mã nguồn. Để quy tắc kiến trúc được kiểm tra mỗi lần nhóm build ứng dụng, hãy đặt lời gọi verification trong một bài test JUnit và để bài test tham gia lifecycle test mặc định của dự án.

Sau bài học này, bạn có thể:

- Viết test gọi ApplicationModules.verify() từ lớp ứng dụng.
- Khai báo dependency cần thiết cho test build.
- Tích hợp test với Gradle hoặc Maven.
- Đưa lệnh test vào CI và bảo đảm lỗi verification làm build thất bại.
- Nhận diện trường hợp test không được phát hiện hoặc bị bỏ qua.
- Phân biệt static module verification với test khởi động Spring và test nghiệp vụ.

## Vì sao verification cần nằm trong test lifecycle?

Một thay đổi có thể biên dịch thành công nhưng vẫn vi phạm kiến trúc. Ví dụ, module orders có thể import một repository nằm trong package nội bộ của inventory, hoặc hai module có thể tạo thành một chu trình phụ thuộc. Compiler Java không áp dụng các quy tắc module của Spring Modulith thay cho nhóm.

Lời gọi ApplicationModules.verify() kiểm tra mô hình module và ném exception khi phát hiện vi phạm. Khi đặt lời gọi này trong một test được build tool phát hiện, kết quả verification trở thành một phần của kết quả test:

- Verification thành công: test pass và lifecycle tiếp tục.
- Verification thất bại: test fail, build task trả về lỗi.
- CI chạy cùng test task: pull request có vi phạm sẽ không đạt bước kiểm tra bắt buộc.

Không cần tạo một tiến trình kiểm tra riêng hoặc khởi động toàn bộ Spring ApplicationContext chỉ để kiểm tra cấu trúc module. Một test JUnit thông thường là đủ cho static verification.

## Bước 1: Tạo bài test kiến trúc

Giả sử lớp ứng dụng nằm trong package gốc com.acme.shop:

~~~text
src
├── main
│   └── java
│       └── com/acme/shop
│           ├── ShopApplication.java
│           ├── orders
│           ├── inventory
│           └── catalog
└── test
    └── java
        └── com/acme/shop
            └── ModularityTests.java
~~~

Tạo ModularityTests.java:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test sử dụng lớp ShopApplication làm điểm bắt đầu để Spring Modulith phát hiện các module. Đặt test trong source set test và dùng đúng lớp ứng dụng của hệ thống đang kiểm tra.

ApplicationModules.of(...) xây dựng mô hình từ package và bytecode có trên classpath. Lời gọi verify() kiểm tra các quy tắc module trên mô hình đó. Bản thân thao tác này không cần tạo Spring ApplicationContext.

Nếu repository chứa nhiều ứng dụng Spring Boot độc lập, hãy tạo test tương ứng cho từng lớp application root. Không dùng nhầm lớp ứng dụng của một service khác, vì kết quả sẽ phản ánh mô hình của service đó.

## Bước 2: Thêm dependency cho test

Test cần JUnit Jupiter và Spring Modulith Core. Trong dự án Spring Boot, spring-boot-starter-test thường cung cấp JUnit Jupiter cùng các thư viện test phổ biến; spring-modulith-core cung cấp ApplicationModules và API verification.

Nếu ứng dụng đã có các dependency này trong compile classpath, không cần khai báo trùng chỉ để làm ví dụ. Nếu chỉ bài test kiến trúc sử dụng API core, có thể đặt dependency core ở test scope.

### Gradle

Ví dụ Groovy DSL khi dự án đã quản lý phiên bản Spring Modulith bằng BOM:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-core")
}
~~~

Nếu dự án chưa import Spring Modulith BOM, hãy cấu hình BOM phù hợp với phiên bản Spring Boot và Spring Modulith mà dự án đang dùng. Tránh tự đặt các phiên bản khác nhau cho từng artifact trong cùng một dòng phát hành.

Bật JUnit Platform cho test task:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Với Kotlin DSL, cú pháp tương ứng:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Nếu dự án đã dùng Spring Boot Gradle plugin hoặc convention plugin cấu hình JUnit Platform, giữ cấu hình hiện tại và xác nhận test task thực sự chạy JUnit Jupiter.

### Maven

Khi dự án dùng Spring Boot parent hoặc dependency management tương ứng, khai báo các dependency test:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-core</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu mã production đã dùng annotation hoặc API Spring Modulith, dependency tương ứng phải có trong compile classpath của production thay vì chỉ khai báo test scope. Phần ví dụ trên chỉ thể hiện trường hợp bài test cần core API để xây dựng mô hình.

Đảm bảo Maven Surefire sử dụng phiên bản hỗ trợ JUnit Platform. Spring Boot parent thường quản lý cấu hình plugin tương thích; nếu dự án tự quản lý plugin, kiểm tra cấu hình Surefire và JUnit provider theo phiên bản Maven đang dùng.

Spring Modulith cũng cung cấp starter test cho những dự án sử dụng các tiện ích kiểm thử module như @ApplicationModuleTest. Với bài test chỉ gọi ApplicationModules.verify(), có thể dùng core API cùng JUnit mà không cần khởi tạo module test context.

## Bước 3: Chạy verification qua Gradle

Gradle chạy các test trong source set test thông qua task test. Từ thư mục dự án:

~~~bash
./gradlew test
~~~

Trong multi-project build, chỉ rõ subproject chứa ứng dụng nếu muốn chạy đúng module:

~~~bash
./gradlew :shop-app:test
~~~

Thay shop-app bằng tên subproject thực tế. Nếu pipeline chạy nhiều project, hãy bảo đảm task test của subproject chứa ShopApplication nằm trong tập task CI thực thi.

Khi test được phát hiện, log Gradle sẽ liệt kê ModularityTests. Nếu verification phát hiện vi phạm, task test thất bại và Gradle trả exit code khác 0. Pipeline có thể dùng kết quả đó để chặn bước tiếp theo.

Không cần tạo task riêng chỉ để gọi verify() nếu bài test kiến trúc đã nằm trong test task mặc định. Một task riêng có thể hữu ích khi tổ chức có nhiều nhóm test và muốn phân luồng thời gian chạy, nhưng CI phải gọi task đó như một điều kiện bắt buộc.

## Bước 4: Chạy verification qua Maven

Maven thực thi test trong lifecycle test. Từ thư mục dự án:

~~~bash
./mvnw test
~~~

Trong Maven reactor nhiều module, có thể chọn module ứng dụng và các dependency module cần thiết:

~~~bash
./mvnw -pl shop-app -am test
~~~

-pl chọn project được yêu cầu; -am yêu cầu Maven xây dựng các project mà project đó phụ thuộc. Thay shop-app bằng artifact hoặc module path phù hợp với repository.

Maven Surefire phải nhận diện test JUnit. Theo quy tắc tên mặc định phổ biến, các class như ModularityTest, ModularityTests hoặc ModularityTestCase được phát hiện. Nếu dự án thay đổi include/exclude pattern, hãy kiểm tra class ModularityTests không bị loại khỏi cấu hình.

Khi verification thất bại, JUnit đánh dấu test fail và Surefire làm Maven test phase thất bại. Các phase tiếp theo trong lifecycle không được xem là thành công.

## Bước 5: Đưa test vào CI như một quality gate

Pipeline CI cần chạy test task trên đúng module ứng dụng trước khi cho phép hợp nhất thay đổi.

Ví dụ luồng CI:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Compile"]
    B --> C["Chạy test task"]
    C --> D["ModularityTests"]
    D --> E{"verify() PASS?"}
    E -->|"Không"| F["Build thất bại"]
    E -->|"Có"| G["Các test còn lại PASS?"]
    G -->|"Không"| F
    G -->|"Có"| H["Cho phép bước build tiếp theo"]
~~~

Có thể tổ chức CI theo thứ tự:

1. Checkout mã nguồn và thiết lập JDK phù hợp.
2. Khôi phục dependency cache nếu có.
3. Chạy test task của subproject ứng dụng hoặc toàn bộ build theo chính sách repository.
4. Lưu báo cáo test để reviewer xem tên test và nguyên nhân thất bại.
5. Chỉ tiếp tục đóng gói hoặc triển khai khi task bắt buộc thành công.

Không chỉ dựa vào việc CI có một bước mang tên Architecture. Hãy xác nhận lệnh thực tế chạy đúng test class và build trả lỗi khi test fail.

Trong GitHub Actions, GitLab CI hoặc hệ thống CI khác, nguyên tắc vẫn giống nhau: lệnh test phải là một bước bắt buộc, exit code phải được giữ nguyên và branch protection phải yêu cầu job đó thành công trước khi merge.

## Bước 6: Đảm bảo verification không bị vô hiệu hóa

Một test có thể tồn tại trong repository nhưng không bảo vệ được kiến trúc nếu build không chạy nó hoặc bỏ qua kết quả thất bại.

Kiểm tra các trường hợp sau:

| Cấu hình hoặc cách chạy | Hệ quả |
|---|---|
| Gradle test chạy với JUnit Platform | Test JUnit được thực thi |
| Maven Surefire nhận diện *Test hoặc *Tests | Test được đưa vào test phase |
| Gradle chạy với -x test | Task test bị loại khỏi lần build đó |
| Maven chạy với -DskipTests | Test không được thực thi |
| Maven chạy với -Dmaven.test.skip=true | Test compile và execution đều bị bỏ qua |
| Gradle ignoreFailures = true | Test có thể thất bại nhưng task không làm build thất bại |
| Surefire testFailureIgnore=true | Test thất bại nhưng Maven vẫn tiếp tục như cấu hình cho phép |
| Test có @Disabled | JUnit bỏ qua test đó |
| Test bắt exception rồi không ném lại | Verification có thể thất bại nhưng test vẫn pass |

Các tùy chọn bỏ qua test đôi khi cần thiết cho một tác vụ cục bộ cụ thể. Tuy nhiên, quality gate của CI và pipeline phát hành không được âm thầm sử dụng chúng.

Đặc biệt, không bọc verify() bằng try/catch chỉ để log lỗi:

~~~java
@Test
void verifiesModuleStructure() {
    try {
        ApplicationModules.of(ShopApplication.class).verify();
    } catch (RuntimeException exception) {
        System.err.println(exception.getMessage());
        // Không ném lại exception: test sẽ không báo lỗi.
    }
}
~~~

Cách đúng là để exception truyền ra khỏi test:

~~~java
@Test
void verifiesModuleStructure() {
    ApplicationModules.of(ShopApplication.class).verify();
}
~~~

Khi verification thất bại, báo cáo test cần phản ánh đúng trạng thái đó để nhóm xử lý nguyên nhân.

## Bước 7: Đọc kết quả và sửa đúng nguyên nhân

Khi test fail, đọc thông báo vi phạm của Spring Modulith. Thường cần xác định:

- Module nguồn đang tạo dependency.
- Module đích bị sử dụng.
- Package hoặc type bị truy cập.
- Dependency có vượt allowlist hay truy cập package nội bộ không.
- Có chu trình giữa các module không.

Ví dụ, orders import com.acme.shop.inventory.internal.StockRepository. Nếu inventory không công bố package này, verification sẽ phát hiện việc truy cập vượt ranh giới.

Hướng sửa có thể là:

- Gọi API công khai của inventory.
- Công bố một named interface nếu package con thực sự là hợp đồng cần dùng.
- Chuyển giao tiếp sang application event nếu consumer chỉ cần phản ứng với sự kiện.
- Loại bỏ dependency không cần thiết hoặc xử lý chu trình ở cấp thiết kế.

Sau khi sửa, chạy lại cùng test task. Không chỉ thêm module vào allowedDependencies hoặc đánh dấu module OPEN để làm test pass nếu chưa xác nhận đó là quyết định kiến trúc đúng.

## Bước 8: Dùng custom detection strategy nhất quán

Nếu ứng dụng có custom ApplicationModuleDetectionStrategy, static verification cần nhìn thấy strategy và cấu hình tương ứng.

Nếu strategy chỉ phục vụ test hoặc sinh tài liệu, có thể đặt lớp trong src/test/java và cấu hình trong src/test/resources. Nếu runtime components cũng sử dụng mô hình đó, lớp strategy và cấu hình phải nằm trong production sources.

Điều quan trọng đối với test build là test và runtime không được vô tình sử dụng hai quy tắc phát hiện module khác nhau. Nếu runtime cần custom strategy, hãy chia sẻ cùng một lớp triển khai và đăng ký nó trong production configuration, sau đó để test dùng cùng mô hình.

Sau khi thay đổi strategy, test kiến trúc nên xác nhận cả danh sách module được phát hiện lẫn kết quả verify(). Chỉ kiểm tra verify() mà không kiểm tra package được chọn có thể bỏ sót trường hợp strategy vô tình loại một module cần thiết khỏi mô hình.

## Bước 9: Khi nào cần test module hoặc integration test?

Static verification kiểm tra cấu trúc phụ thuộc. Nó không xác nhận Spring bean được inject đúng, transaction hoạt động đúng hay event listener hoàn tất công việc.

Nếu cần kiểm tra một module trong Spring context, có thể dùng @ApplicationModuleTest từ Spring Modulith Test. Nếu cần xác nhận nhiều module phối hợp qua API hoặc event, hãy viết integration test phù hợp với phạm vi đó.

Phân biệt các loại kiểm tra:

| Loại test | Mục tiêu |
|---|---|
| ApplicationModules.verify() | Quy tắc cấu trúc và dependency giữa module |
| @ApplicationModuleTest | Khởi tạo và kiểm tra một module trong phạm vi được chọn |
| Integration test | Xác nhận nhiều thành phần phối hợp trong Spring context |
| Unit test | Kiểm tra logic của một lớp hoặc thành phần nhỏ |
| Event publication test | Kiểm tra việc phát, lưu và xử lý event theo yêu cầu |

Các bài test này bổ sung cho nhau. Không cần biến static verification thành @SpringBootTest nếu mục tiêu chỉ là kiểm tra dependency graph.

## Bài thực hành

Một ứng dụng Spring Boot có package gốc com.acme.shop với các module orders, inventory và catalog. Nhóm muốn bảo đảm mọi pull request đều kiểm tra ranh giới module.

Hãy thực hiện:

1. Tạo ModularityTests trong src/test/java/com/acme/shop.
2. Dùng ApplicationModules.of(ShopApplication.class).verify() trong một phương thức có @Test.
3. Khai báo JUnit Jupiter và Spring Modulith Core trong test dependencies, hoặc dùng các starter đã có sẵn và được quản lý phiên bản thống nhất.
4. Cấu hình Gradle useJUnitPlatform() hoặc Maven Surefire để phát hiện JUnit test.
5. Chạy ./gradlew test hoặc ./mvnw test từ đúng project.
6. Xác nhận báo cáo test có ModularityTests và build task trả thành công khi kiến trúc hợp lệ.
7. Tạo một dependency sai trong môi trường thử nghiệm, chẳng hạn import package internal của module khác, rồi chạy lại test.
8. Xác nhận verification làm test thất bại và build trả exit code khác 0.
9. Sửa dependency bằng API công khai hoặc named interface phù hợp rồi chạy lại test.
10. Đưa lệnh test vào CI và bảo đảm job là điều kiện bắt buộc trước khi merge.

Kết quả mong đợi:

- Test kiến trúc được phát hiện trong test lifecycle mặc định.
- Build thành công khi các quy tắc module được đáp ứng.
- Build thất bại khi verification phát hiện vi phạm.
- CI hiển thị báo cáo để reviewer xác định module và dependency gây lỗi.
- Không có cấu hình bỏ qua test hoặc bỏ qua test failure trong quality gate.

## Checklist review

Trước khi coi verification đã được tích hợp vào test build, hãy xác nhận:

- Test gọi ApplicationModules.verify() nằm trong source set test của đúng ứng dụng.
- Test dùng đúng lớp application root.
- Dependency core và JUnit có trên test classpath.
- Gradle sử dụng JUnit Platform hoặc Maven Surefire nhận diện JUnit test.
- Lệnh build mặc định thực thi test kiến trúc.
- CI gọi đúng test task của subproject chứa ứng dụng.
- Test failure làm task và job CI thất bại.
- Không có @Disabled, ignoreFailures, testFailureIgnore hoặc cấu hình skip làm vô hiệu hóa quality gate.
- Custom module detection được cấu hình nhất quán giữa test và runtime nếu cả hai cần dùng.
- Integration test riêng được bổ sung khi cần xác nhận hành vi Spring hoặc nghiệp vụ.

## Tiêu chí hoàn tất

Bạn đã hoàn thành bài học khi có thể đặt một bài test kiến trúc gọi ApplicationModules.verify(), cấu hình dependency và JUnit discovery cho Gradle hoặc Maven, chứng minh test được thực thi trong build lifecycle, và bảo đảm vi phạm kiến trúc làm CI thất bại với báo cáo có thể điều tra.

Tài liệu tham khảo:

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)

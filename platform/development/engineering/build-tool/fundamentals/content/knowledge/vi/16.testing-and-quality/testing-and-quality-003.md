# Tổ chức unit test và integration test trong chuỗi build

Một chuỗi build đáng tin cậy cần kiểm tra cả logic nhỏ của từng thành phần và cách các thành phần phối hợp khi chạy cùng nhau. **Unit test** tập trung vào một đơn vị mã nguồn trong phạm vi hẹp; **integration test** kiểm tra sự phối hợp giữa nhiều thành phần hoặc với hệ thống bên ngoài như cơ sở dữ liệu, HTTP service, filesystem hay message broker.

Trong Gradle, có thể tổ chức hai nhóm kiểm thử thành các source set và task riêng. Cách tổ chức này giúp mỗi nhóm có dependency, classpath, cấu hình và thời gian chạy phù hợp. Sau đó, ta liên kết các task kiểm thử vào lifecycle task **check** để lệnh **build** thực hiện đầy đủ các bước xác minh.

## 1. Unit test và integration test khác nhau ở đâu?

### Unit test

Unit test kiểm tra hành vi của một đơn vị nhỏ, thường là một class hoặc một nhóm hàm có trách nhiệm rõ ràng. Mục tiêu là phát hiện lỗi trong logic mà không cần khởi động toàn bộ hệ thống.

Ví dụ, một lớp tính giá đơn hàng có thể được kiểm tra với các đầu vào khác nhau:

~~~java
class PriceCalculator {
    int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("Values must be non-negative");
        }
        return unitPrice * quantity;
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void calculatesTotal() {
        assertEquals(150, calculator.total(50, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.total(50, -1)
        );
    }
}
~~~

Unit test thường có các đặc điểm:

- Chạy nhanh và có thể thực hiện thường xuyên.
- Dùng dữ liệu kiểm soát được.
- Không phụ thuộc vào mạng, database thật hoặc dịch vụ dùng chung.
- Dễ xác định nguyên nhân khi thất bại.
- Có thể dùng fake, stub hoặc mock khi cần cô lập một dependency.

Không phải unit test nào cũng cần mock mọi dependency. Nếu một đối tượng nhỏ có thể chạy với implementation thật, đơn giản và ổn định, dùng trực tiếp thường giúp test dễ đọc hơn.

### Integration test

Integration test kiểm tra các thành phần khi phối hợp với nhau. Phạm vi có thể là nhiều lớp trong cùng ứng dụng, ứng dụng với database, hoặc ứng dụng với dịch vụ bên ngoài.

Ví dụ, thay vì chỉ kiểm tra một phương thức tính giá, integration test có thể kiểm tra luồng lưu và đọc đơn hàng qua service, repository và database:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderRepositoryIntegrationTest {
    private final OrderRepository repository = TestDatabase.createRepository();

    @Test
    void savesAndLoadsOrder() {
        Order order = new Order("ORD-100", 250);

        repository.save(order);

        Order loaded = repository.findById("ORD-100").orElseThrow();
        assertEquals(250, loaded.total());
    }
}
~~~

**TestDatabase.createRepository()** ở đây đại diện cho phần thiết lập database kiểm thử. Trong dự án thật, có thể dùng database riêng, database chạy trong container, hoặc một dịch vụ test được quản lý bởi fixture.

Integration test thường:

- Chạy lâu hơn unit test.
- Cần khởi tạo và dọn dẹp tài nguyên.
- Có thể cần database, filesystem, server hoặc network.
- Kiểm tra cấu hình, mapping, serialization và giao tiếp thực tế.
- Cần kiểm soát dữ liệu để tránh test ảnh hưởng lẫn nhau.

### So sánh nhanh

| Tiêu chí | Unit test | Integration test |
|---|---|---|
| Phạm vi | Một đơn vị logic nhỏ | Nhiều thành phần phối hợp |
| Mục tiêu | Kiểm tra hành vi và quy tắc nghiệp vụ | Kiểm tra kết nối và tương tác thực tế |
| Tốc độ | Thường nhanh | Thường chậm hơn |
| Dependency bên ngoài | Thường được cô lập | Có thể dùng implementation thật |
| Môi trường | Ít yêu cầu | Có thể cần dịch vụ hoặc dữ liệu riêng |
| Vị trí thường dùng | **src/test/java** | **src/integrationTest/java** |
| Task Gradle | **test** | **integrationTest** do dự án tạo |

Hai loại test bổ sung cho nhau. Unit test giúp phát hiện lỗi logic sớm; integration test phát hiện vấn đề khi các thành phần kết hợp, chẳng hạn sai SQL, cấu hình kết nối hoặc serialization không tương thích.

## 2. Chuỗi build thường tổ chức kiểm thử như thế nào?

Với Java plugin, Gradle tạo source set **main** và **test**, cùng các task biên dịch và kiểm thử tương ứng.

Một chuỗi build đơn giản có thể hình dung:

~~~text
build
├── check
│   └── test
│       ├── compileTestJava
│       └── processTestResources
└── assemble
    └── jar
        └── classes
            ├── compileJava
            └── processResources
~~~

Trong đó:

- **compileJava** biên dịch mã nguồn chính.
- **compileTestJava** biên dịch mã nguồn unit test.
- **test** chạy các test thuộc source set **test**.
- **check** là lifecycle task gom các bước xác minh.
- **assemble** tạo các sản phẩm build.
- **build** kết hợp **check** và **assemble**.

Khi dự án thêm task integration test, task đó không tự động trở thành một phần của **check** chỉ vì nó có tên chứa từ test. Cần liên kết task một cách rõ ràng:

~~~text
build
├── check
│   ├── test
│   └── integrationTest
└── assemble
~~~

Khi đã thêm dependency từ **check** đến **integrationTest**, lệnh **build** sẽ kéo cả hai nhóm kiểm thử vào graph.

## 3. Tổ chức thư mục test

Một cấu trúc Java phổ biến:

~~~text
my-app/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   ├── test/
│   │   ├── java/
│   │   └── resources/
│   └── integrationTest/
│       ├── java/
│       └── resources/
└── build.gradle.kts
~~~

Ý nghĩa:

- **src/main/java**: mã nguồn ứng dụng.
- **src/main/resources**: tài nguyên được đóng gói cùng ứng dụng.
- **src/test/java**: unit test.
- **src/test/resources**: dữ liệu và cấu hình dành cho unit test.
- **src/integrationTest/java**: integration test.
- **src/integrationTest/resources**: dữ liệu và cấu hình dành cho integration test.

Gradle Java plugin tự nhận biết **main** và **test**. Source set **integrationTest** là source set bổ sung do dự án tạo, vì vậy cần cấu hình classpath, dependency configuration và task chạy riêng.

Có thể dùng tên khác như **functionalTest** hoặc **acceptanceTest** nếu phù hợp với cách nhóm phân chia kiểm thử. Điều quan trọng là tên source set và task phải thể hiện rõ phạm vi kiểm thử.

## 4. Dependency dành cho từng nhóm test

Unit test và integration test có thể dùng chung framework như JUnit Jupiter, nhưng integration test đôi khi cần thêm thư viện hoặc driver để kết nối môi trường kiểm thử.

Ví dụ dependencies trong Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    // Dependency riêng cho integration test có thể được thêm
    // vào integrationTestImplementation sau khi tạo source set.
}
~~~

Một số configuration thường gặp:

| Configuration | Mục đích |
|---|---|
| **testImplementation** | Dependency cần để biên dịch unit test |
| **testRuntimeOnly** | Dependency chỉ cần khi chạy unit test |
| **integrationTestImplementation** | Dependency cần để biên dịch integration test |
| **integrationTestRuntimeOnly** | Dependency chỉ cần khi chạy integration test |
| **integrationTestCompileOnly** | Dependency chỉ cần trong compile classpath của integration test |

Nếu integration test cần cùng framework và một số dependency test như unit test, có thể cho các configuration integration test kế thừa từ configuration test tương ứng. Như vậy không phải khai báo lặp lại cùng một framework.

Không nên tự động cho integration test kế thừa tất cả dependency của production hoặc test nếu không cần. Hãy giữ dependency rõ ràng để classpath của từng nhóm test dễ kiểm soát.

## 5. Tạo source set integrationTest trong Gradle Kotlin DSL

Ví dụ sau tạo source set **integrationTest**, cho phép integration test sử dụng lớp đã biên dịch từ **main**, kế thừa dependency test cần thiết, và tạo task **integrationTest**.

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val integrationTestSourceSet = sourceSets.create("integrationTest") {
    // Integration test cần truy cập lớp production.
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}

// Dùng lại framework và dependency kiểm thử chung.
configurations.named(integrationTestSourceSet.implementationConfigurationName) {
    extendsFrom(configurations.testImplementation.get())
}

configurations.named(integrationTestSourceSet.runtimeOnlyConfigurationName) {
    extendsFrom(configurations.testRuntimeOnly.get())
}

configurations.named(integrationTestSourceSet.compileOnlyConfigurationName) {
    extendsFrom(configurations.testCompileOnly.get())
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

val integrationTestTask = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath

    // Bảo đảm source set được biên dịch trước khi chạy.
    dependsOn(integrationTestSourceSet.classesTaskName)

    // Nếu test và integrationTest cùng được chọn, chạy test trước.
    shouldRunAfter(tasks.test)
}

// Đưa integration test vào lifecycle verification.
tasks.named("check") {
    dependsOn(integrationTestTask)
}
~~~

Các phần chính:

1. **sourceSets.create("integrationTest")** tạo source set bổ sung.
2. **compileClasspath** và **runtimeClasspath** được bổ sung output của source set **main**, giúp test truy cập mã ứng dụng.
3. Các configuration integration test kế thừa dependency của unit test.
4. **tasks.withType<Test>().configureEach { useJUnitPlatform() }** bật JUnit Platform cho cả hai task.
5. **tasks.register<Test>("integrationTest")** tạo task thực thi riêng.
6. **dependsOn(integrationTestSourceSet.classesTaskName)** đảm bảo test class được biên dịch trước.
7. **shouldRunAfter(tasks.test)** đặt thứ tự khi cả hai task đã được chọn.
8. **check** phụ thuộc vào **integrationTest**, do đó **build** sẽ bao gồm integration test.

Tên configuration được lấy từ source set để tránh phải tự ghép chuỗi. Ví dụ source set **integrationTest** tạo ra các configuration có tên như **integrationTestImplementation** và **integrationTestRuntimeOnly**.

Nếu integration test cần một thư viện riêng, có thể thêm:

~~~kotlin
dependencies {
    add(
        integrationTestSourceSet.implementationConfigurationName,
        "org.testcontainers:junit-jupiter:1.19.8"
    )
}
~~~

Ví dụ này minh họa cách thêm dependency vào configuration implementation của source set. Phiên bản và thư viện thực tế cần phù hợp với Java, Gradle và môi trường test của dự án.

## 6. Cấu hình unit test và integration test riêng biệt

Hai task **test** và **integrationTest** có thể có cấu hình khác nhau.

Ví dụ, unit test có thể chạy với số lượng worker phù hợp và không cần dịch vụ bên ngoài:

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    maxParallelForks = 2
}
~~~

Integration test có thể cần biến môi trường, system property hoặc cấu hình timeout:

~~~kotlin
tasks.named<Test>("integrationTest") {
    useJUnitPlatform()

    systemProperty("app.environment", "test")
    environment("DATABASE_NAME", "app_integration_test")

    maxParallelForks = 1
}
~~~

Ví dụ trên giả định môi trường test có database tương ứng. Không nên trỏ integration test vào database production hoặc database dùng chung mà test có thể làm thay đổi dữ liệu của người khác.

Có thể đặt cấu hình chung cho tất cả task Test:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
    }
}
~~~

Sau đó cấu hình riêng từng task nếu cần. Cách này giảm lặp lại nhưng vẫn cho phép integration test có môi trường và mức song song khác unit test.

## 7. Đưa integration test vào chuỗi build

Có ba việc cần phân biệt:

- **Đăng ký task:** Gradle biết task **integrationTest** tồn tại.
- **Đặt thứ tự:** quy định task nào chạy trước task nào nếu cả hai đã được chọn.
- **Thêm dependency vào lifecycle:** bảo đảm task được chọn khi gọi task tổng hợp như **check** hoặc **build**.

Ví dụ:

~~~kotlin
tasks.named("check") {
    dependsOn(integrationTestTask)
}
~~~

Đây là cấu hình khiến **integrationTest** được chọn khi chạy **check**.

Trong khi đó:

~~~kotlin
tasks.named<Test>("integrationTest") {
    shouldRunAfter(tasks.test)
}
~~~

chỉ yêu cầu integration test chạy sau unit test nếu cả hai đã có trong graph. **shouldRunAfter** không tự đưa **test** vào graph khi chỉ gọi **integrationTest**, và cũng không tự đưa **integrationTest** vào graph khi chỉ gọi **test**.

Có thể hình dung:

~~~text
./gradlew test
    └── test

./gradlew integrationTest
    └── integrationTest

./gradlew check
    ├── test
    └── integrationTest
        (thứ tự được ràng buộc nếu cả hai được chọn)

./gradlew build
    ├── check
    │   ├── test
    │   └── integrationTest
    └── assemble
~~~

Nếu muốn chạy tất cả kiểm thử qua một lệnh, có thể gọi:

~~~bash
./gradlew check
~~~

Nếu muốn build cả artifact:

~~~bash
./gradlew build
~~~

## 8. Khi nào nên chạy integration test?

Không phải mọi nhóm test đều cần chạy ở mọi bước phát triển.

Một chiến lược phổ biến:

| Giai đoạn | Unit test | Integration test |
|---|---|---|
| Khi lập trình cục bộ | Chạy thường xuyên | Chạy khi thay đổi liên quan |
| Pull request | Chạy đầy đủ | Chạy nhóm thiết yếu |
| CI trên nhánh chính | Chạy đầy đủ | Chạy đầy đủ theo chính sách |
| Trước phát hành | Chạy đầy đủ | Chạy đầy đủ và kiểm tra môi trường gần production |
| Kiểm tra nhanh | Chọn test liên quan | Có thể bỏ qua nếu không liên quan |

Cách tổ chức cụ thể tùy vào thời gian build và mức độ rủi ro. Nếu integration test nhanh và ổn định, có thể đưa toàn bộ vào **check**. Nếu một nhóm integration test cần môi trường đặc biệt hoặc chạy rất lâu, nhóm có thể tạo task riêng và chỉ đưa một tập test phù hợp vào pipeline thường xuyên.

Dù chọn chiến lược nào, cần bảo đảm pipeline phát hành có một bước xác minh integration test mà nhóm xem là bắt buộc. Việc một task tồn tại trong build script không có nghĩa CI tự động chạy nó.

## 9. Chạy và lọc test bằng Gradle

Chạy unit test:

~~~bash
./gradlew test
~~~

Chạy integration test:

~~~bash
./gradlew integrationTest
~~~

Chạy cả hai qua lifecycle task:

~~~bash
./gradlew check
~~~

Chạy toàn bộ build:

~~~bash
./gradlew build
~~~

Lọc theo tên class hoặc phương thức với tùy chọn **--tests**:

~~~bash
./gradlew test --tests "com.example.service.PriceCalculatorTest"
~~~

Với integration test:

~~~bash
./gradlew integrationTest --tests "com.example.integration.OrderRepositoryIntegrationTest"
~~~

Có thể bật log chi tiết hơn:

~~~bash
./gradlew integrationTest --info --console=plain
~~~

Khi chỉ muốn xem task nào được chọn mà không chạy test action:

~~~bash
./gradlew check --dry-run --console=plain
~~~

Dry run giúp xác nhận **integrationTest** có được đưa vào graph thông qua **check** hay không. Các dòng **SKIPPED** trong dry run chỉ thể hiện chế độ xem kế hoạch, không phải kết quả kiểm thử thật.

## 10. Báo cáo và kết quả test

Gradle **Test** task tạo báo cáo HTML và kết quả XML. Với task **test**, báo cáo thường nằm tại:

~~~text
build/reports/tests/test/index.html
build/test-results/test/
~~~

Với task **integrationTest**, báo cáo thường nằm tại:

~~~text
build/reports/tests/integrationTest/index.html
build/test-results/integrationTest/
~~~

Báo cáo có thể cho biết:

- Tổng số test được thực thi.
- Test thành công, thất bại hoặc bị bỏ qua.
- Thời gian chạy.
- Assertion hoặc exception gây thất bại.
- Test class và phương thức liên quan.

Trong CI, kết quả XML thường được dùng để hệ thống CI thu thập và hiển thị test report. HTML hữu ích khi lập trình viên cần điều tra một test thất bại cục bộ.

Không nên chỉ nhìn trạng thái **BUILD SUCCESSFUL** mà bỏ qua số test thực sự được chạy. Một task có thể chạy nhưng không tìm thấy test nào nếu source set, test class pattern hoặc framework configuration sai.

## 11. Quản lý dữ liệu và môi trường cho integration test

Integration test thường tương tác với tài nguyên có trạng thái. Nếu nhiều test dùng chung một database hoặc thư mục, test có thể ảnh hưởng lẫn nhau.

Một số nguyên tắc hữu ích:

### Dùng môi trường test riêng

Tạo database hoặc schema dành riêng cho test. Không dùng thông tin kết nối production trong file cấu hình test.

### Tạo dữ liệu có thể tái lập

Mỗi test nên tạo dữ liệu cần thiết hoặc dùng fixture được kiểm soát. Tránh phụ thuộc vào dữ liệu được một test khác tạo trước đó.

### Dọn dẹp sau test

Đóng connection, xóa dữ liệu test và dừng server/container sau khi test kết thúc. Dùng lifecycle hook của framework test hoặc fixture có trách nhiệm rõ ràng.

### Cô lập test chạy song song

Nếu nhiều test chạy đồng thời, hãy dùng database/schema hoặc resource name riêng cho từng test. Với hệ thống có port động, tránh hard-code một port dùng chung.

### Tránh phụ thuộc vào dịch vụ không ổn định

Nếu integration test gọi dịch vụ bên ngoài, cần có chiến lược retry hợp lý, timeout và môi trường test có thể kiểm soát. Test phụ thuộc trực tiếp vào dịch vụ công cộng có thể thất bại do mạng hoặc bảo trì ngoài dự án.

### Giữ test độc lập với thứ tự chạy

Một test không nên cần test khác chạy trước để tạo trạng thái. Gradle có thể chạy task song song và thứ tự test trong một task không nên được dùng như cơ chế quản lý dữ liệu.

## 12. Kiểm soát thời gian và độ ổn định

Integration test có thể chiếm phần lớn thời gian build. Một số cách kiểm soát:

- Chỉ khởi động các dịch vụ thực sự cần.
- Dùng fixture chung có lifecycle rõ ràng thay vì khởi động lại dịch vụ nặng cho từng test nếu điều đó an toàn.
- Chia test theo nhóm hoặc tag để CI chọn tập phù hợp.
- Dùng timeout cho thao tác network và database.
- Tránh sleep cố định; chờ điều kiện thực tế với giới hạn thời gian.
- Giữ log đủ để xác định môi trường và dữ liệu gây lỗi.
- Chạy test song song chỉ khi tài nguyên được cô lập.

Có thể cấu hình số worker của một Test task:

~~~kotlin
tasks.named<Test>("integrationTest") {
    maxParallelForks = 1
}
~~~

Giá trị này giới hạn số process test fork cho task đó. Nếu integration test dùng chung tài nguyên, bắt đầu với một fork thường dễ kiểm soát hơn. Sau khi test được cô lập đúng cách, nhóm có thể tăng mức song song để giảm thời gian.

Không nên dùng **ignoreFailures = true** để che lỗi test bắt buộc. Nếu có test tùy chọn hoặc môi trường đặc biệt, hãy thiết kế task và pipeline riêng để trạng thái được thể hiện rõ.

## 13. Phân biệt test task, source set và lifecycle task

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Source set | **main**, **test**, **integrationTest** | Xác định nhóm source, resources và classpath |
| Test task | **test**, **integrationTest** | Thực thi các test class đã biên dịch |
| Lifecycle task | **check**, **build** | Gom các task theo mục tiêu lớn hơn |

Source set không tự chạy test. Test task cần biết test class directories và runtime classpath. Lifecycle task cần phụ thuộc vào test task nếu muốn đưa nó vào chuỗi build.

Ví dụ, tạo source set **integrationTest** mà không đăng ký task sẽ chỉ tạo cấu trúc source và configuration. Tạo task **integrationTest** nhưng không nối vào **check** có nghĩa task đó chỉ chạy khi được gọi trực tiếp hoặc được task khác yêu cầu.

## 14. Ví dụ thực hành từ đầu đến cuối

Giả sử ứng dụng Java có unit test và integration test dùng JUnit 5.

**Bước 1: Tạo thư mục**

~~~text
src/
├── main/java/
├── test/java/
└── integrationTest/java/
~~~

**Bước 2: Khai báo dependency chung**

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

**Bước 3: Tạo source set integrationTest**

~~~kotlin
val integrationTestSourceSet = sourceSets.create("integrationTest") {
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}
~~~

**Bước 4: Kế thừa dependency test**

~~~kotlin
configurations.named(integrationTestSourceSet.implementationConfigurationName) {
    extendsFrom(configurations.testImplementation.get())
}

configurations.named(integrationTestSourceSet.runtimeOnlyConfigurationName) {
    extendsFrom(configurations.testRuntimeOnly.get())
}
~~~

**Bước 5: Đăng ký task chạy integration test**

~~~kotlin
val integrationTestTask = tasks.register<Test>("integrationTest") {
    group = "verification"
    description = "Runs integration tests."

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath

    dependsOn(integrationTestSourceSet.classesTaskName)
    shouldRunAfter(tasks.test)
    useJUnitPlatform()
}
~~~

**Bước 6: Nối vào check**

~~~kotlin
tasks.named("check") {
    dependsOn(integrationTestTask)
}
~~~

**Bước 7: Chạy kiểm thử**

~~~bash
./gradlew test
./gradlew integrationTest
./gradlew check
./gradlew build
~~~

**Bước 8: Xem báo cáo**

Mở báo cáo HTML của từng task trong thư mục **build/reports/tests/**. Nếu task không chạy hoặc không tìm thấy test, kiểm tra source set output, test class directories, runtime classpath và cấu hình JUnit Platform.

## 15. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **integrationTest** không được chạy khi gọi **build** | Task chưa được nối vào **check** hoặc lifecycle task khác | Thêm **dependsOn(integrationTestTask)** vào **check** |
| Không tìm thấy test class | Source set hoặc **testClassesDirs** cấu hình sai | Kiểm tra **integrationTest.output.classesDirs** và task compile |
| Không tìm thấy lớp production | Output của **main** chưa có trong compile/runtime classpath | Bổ sung **sourceSets.main.output** vào classpath integration test |
| Không tìm thấy JUnit engine | Thiếu dependency runtime của test framework | Kiểm tra **integrationTestRuntimeOnly** và cấu hình JUnit Platform |
| Unit test chạy nhưng integration test không chạy trên JUnit 5 | Chỉ cấu hình **useJUnitPlatform()** cho task **test** | Cấu hình cho mọi **Test** task hoặc riêng **integrationTest** |
| Test thất bại do port/database đã được dùng | Nhiều test chia sẻ tài nguyên hoặc chạy song song | Cô lập dữ liệu, schema, port và giảm **maxParallelForks** khi cần |
| Test chạy cục bộ nhưng thất bại trên CI | Khác biệt môi trường, biến môi trường hoặc dịch vụ phụ thuộc | Khai báo môi trường rõ ràng và kiểm tra log CI |
| Integration test chạy nhiều lần ngoài ý muốn | Task được nối vào nhiều nhánh hoặc gọi qua nhiều lifecycle task | Xem task graph và dependency để hiểu đường yêu cầu |

## 16. Những nguyên tắc cần nhớ

- Unit test kiểm tra logic trong phạm vi hẹp; integration test kiểm tra sự phối hợp giữa nhiều thành phần hoặc hệ thống bên ngoài.
- Gradle Java plugin cung cấp source set **main** và **test**; integration test thường cần source set và task riêng.
- Integration test phải có main output trên compile và runtime classpath để sử dụng mã ứng dụng.
- Có thể cho configuration integration test kế thừa dependency framework từ unit test để tránh khai báo lặp.
- **Test** task cần test class directories, runtime classpath và task biên dịch tương ứng.
- **shouldRunAfter** chỉ ràng buộc thứ tự khi cả hai task đã được chọn; **dependsOn** mới đưa task vào graph.
- Nối integration test vào **check** để **build** thực hiện nó qua lifecycle verification.
- Dùng báo cáo riêng của từng Test task để xem kết quả và điều tra lỗi.
- Cô lập database, file, port và dịch vụ test để tránh phụ thuộc thứ tự hoặc trạng thái dùng chung.
- Điều chỉnh mức song song dựa trên khả năng cô lập tài nguyên và thời gian build.
- CI cần chạy những nhóm test mà chính sách chất lượng của dự án yêu cầu; task chỉ được đăng ký không đồng nghĩa tự động được thực thi.

Tổ chức unit test và integration test thành các nhóm riêng giúp chuỗi build phản ánh rõ mục tiêu kiểm thử, thời gian và môi trường của từng nhóm. Khi các task được nối đúng vào lifecycle **check**, nhóm có thể chạy nhanh unit test trong lúc phát triển và vẫn bảo đảm integration test được thực hiện trong những bước xác minh cần thiết.

# Kiểm tra bộ test kế thừa JUnit và cấu hình test engine

Sau khi nâng cấp ứng dụng Spring Web Flow, build vẫn xanh nhưng số ca kiểm thử giảm từ hàng chục xuống vài ca. Không có lỗi transition nào được báo, vì những lớp test cũ chưa hề được engine mới chạy. Đây là một dạng mất bảo vệ hồi quy dễ bị nhầm với nâng cấp thành công.

Bài học thuộc chương **Nâng cấp ứng dụng cũ** của module **SPRING_WEB_FLOW**. Trọng tâm là nhận diện mô hình JUnit của bộ test kế thừa, cấu hình engine và build tool phù hợp, rồi chứng minh các ca kiểm tra state, event, binding, validation, scope và phục hồi vẫn được thực thi sau nâng cấp.

## 1. Phân biệt mã test, engine và công cụ chạy

Một test chạy được cần nhiều thành phần cùng khớp:

```text
Lớp/phương thức test
        ↓
Quy tắc phát hiện và bộ lọc của task/plugin
        ↓
JUnit Platform và engine tương ứng, nếu dùng Platform
        ↓
Lifecycle, fixture, assertion và báo cáo kết quả
```

Có dependency chứa annotation `@Test` chỉ giúp code biên dịch. Nó chưa chứng minh runtime có engine phù hợp hoặc build task chọn đúng lớp.

| Thành phần | Vai trò |
| --- | --- |
| JUnit 3 | Mô hình `TestCase`, phương thức `public void test...()` và `setUp()`/`tearDown()` |
| JUnit 4 | Mô hình annotation `org.junit.Test`, runner, rule và lifecycle tương ứng |
| JUnit Jupiter | Mô hình `org.junit.jupiter.api.*`, extension và Jupiter engine |
| JUnit Platform | Hạ tầng khám phá và chạy các engine |
| JUnit Vintage | Engine chạy test theo mô hình JUnit 3/4 trên Platform |
| Maven Surefire/Failsafe, Gradle `Test`, IDE | Chọn task, classpath, bộ lọc và tích hợp cơ chế chạy |

JUnit Vintage yêu cầu JUnit 4.12 trở lên trong classpath/module path; thư viện JUnit 4 chứa cả API tương thích `junit.framework` cho test kiểu JUnit 3. Tài liệu JUnit 6 còn đánh dấu Vintage là deprecated và định hướng dùng tạm thời khi chuyển đổi, không phải một lời hứa duy trì vô thời hạn. Xem [JUnit User Guide: Overview](https://docs.junit.org/6.0.2/overview).

Cần chọn dòng JUnit theo JVM và công cụ của dự án. Chẳng hạn JUnit 6 yêu cầu Java 17 trở lên; không nâng BOM lên một dòng mới chỉ để khắc phục thiếu engine mà bỏ qua nền Java hiện tại.

## 2. Vì sao test Web Flow có thể vẫn là JUnit 3?

Các lớp hỗ trợ kiểm thử flow XML quen thuộc có chuỗi kế thừa dạng:

```text
junit.framework.TestCase
    └── AbstractFlowExecutionTests
          └── AbstractExternalizedFlowExecutionTests
                └── AbstractXmlFlowExecutionTests
                      └── CheckoutFlowExecutionTests
```

`AbstractFlowExecutionTests` kế thừa `junit.framework.TestCase`; xem [API AbstractFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/execution/AbstractFlowExecutionTests.html). Vì vậy việc ứng dụng đã nâng Spring hoặc đã thêm Jupiter không tự đổi mô hình của những subclass này.

Ví dụ test cũ hợp lệ theo quy ước của lớp cơ sở:

```java
public void testStartFlow() {
    startFlow(new MockExternalContext());
    assertCurrentStateEquals("edit");
}
```

Phương thức không cần `@Test` của Jupiter để được test kiểu JUnit 3 nhận diện. Đổi tên thành `startsAtEdit()` rồi chỉ thêm annotation Jupiter là một thay đổi về mô hình thực thi, không đơn thuần là đổi phong cách đặt tên.

Chuỗi kế thừa và cách khai báo test được thể hiện tại [API AbstractXmlFlowExecutionTests](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/test/execution/AbstractXmlFlowExecutionTests.html).

## 3. Kiểm kê bộ test trước khi đổi cấu hình

Trước nâng cấp, ghi nhận tên các lớp quan trọng, số ca, task chạy chúng và kết quả. Sau nâng cấp, đối chiếu cùng phạm vi thay vì chỉ nhìn dòng `BUILD SUCCESS`.

| Dấu hiệu trong mã | Phân loại ban đầu | Điểm cần kiểm tra |
| --- | --- | --- |
| `extends TestCase` trực tiếp hoặc gián tiếp | Test kiểu JUnit 3 | Phương thức `test...`, lifecycle và engine/runner |
| `extends AbstractXmlFlowExecutionTests` | Harness Web Flow mang mô hình TestCase | Test cũ có còn được Vintage hoặc cơ chế tương ứng chạy không? |
| `import org.junit.Test` | Test annotation JUnit 4 | Runner, rule, JUnit 4 runtime và Vintage khi dùng Platform |
| `import org.junit.jupiter.api.Test` | Test Jupiter | Jupiter engine và extension |
| `@RunWith(SpringRunner.class)` | Tích hợp Spring theo JUnit 4 | Không thay máy móc bằng annotation Jupiter |
| `@ExtendWith(SpringExtension.class)` | Tích hợp Spring theo Jupiter | Có đúng context và lifecycle cần thiết không? |
| `suite()` hoặc lớp suite riêng | Cơ chế tập hợp test | Suite có bỏ sót lớp hoặc làm chạy trùng không? |

Trong dự án cần nâng cấp, có thể dùng tìm kiếm nguồn để lập danh sách, chẳng hạn:

```powershell
rg -n 'AbstractXmlFlowExecutionTests|junit\.framework\.TestCase|org\.junit\.Test|org\.junit\.jupiter\.api\.Test' src/test

rg -n 'setUp\(|tearDown\(|@RunWith|@ExtendWith|@BeforeEach|@Before|suite\(' src/test
```

Đây là lệnh minh họa cho người triển khai tại dự án của họ. Tìm kiếm chuỗi không thay thế việc đọc superclass, vì nhiều test kế thừa qua lớp cơ sở nội bộ mà không chứa các tên trên ngay trong file.

### Lập bảng sở hữu task và engine

```text
CheckoutFlowExecutionTests → task test → mô hình TestCase → Vintage trên Platform
DraftPolicyTests          → task test → Jupiter
CheckoutMvcIT             → task integrationTest/Failsafe → Jupiter + Spring
```

Tên task chỉ là quy ước dự án. Điểm quan trọng là mỗi lớp có nơi chạy rõ ràng, không bị bỏ giữa hai task và không bị thực thi hai lần ngoài chủ đích.

## 4. Nhận diện lỗi lifecycle khi trộn mô hình

Ba cách chuẩn bị fixture có hình thức gần nhau nhưng không tự thay thế nhau:

| Mô hình | Trước mỗi test | Sau mỗi test |
| --- | --- | --- |
| TestCase kiểu JUnit 3 | Override `setUp()` | Override `tearDown()` |
| JUnit 4 annotation | `@Before` | `@After` |
| Jupiter | `@BeforeEach` | `@AfterEach` |

Trong đường chạy TestCase thông thường, `setUp()` và `tearDown()` là hợp đồng lifecycle. Mã [JUnit TestCase](https://github.com/junit-team/junit4/blob/main/src/main/java/junit/framework/TestCase.java) thể hiện quá trình gọi setup, test và teardown. JUnit 4 cũng có [JUnit3Builder](https://github.com/junit-team/junit4/blob/main/src/main/java/org/junit/internal/builders/JUnit3Builder.java) nhận diện subclass TestCase để chọn runner phù hợp.

Một lỗi thường gặp:

```java
public class CheckoutFlowExecutionTests extends AbstractXmlFlowExecutionTests {
    private OrderService orderService;

    @org.junit.jupiter.api.BeforeEach
    void prepare() {
        orderService = new StubOrderService();
    }

    public void testConfirm() {
        // Khi ca này chạy theo mô hình TestCase/Vintage,
        // annotation BeforeEach của Jupiter không cung cấp setup cho nó.
    }
}
```

Kết quả có thể là dependency chưa được tạo hoặc test dùng trạng thái không đúng. Đổi `@BeforeEach` thành `@Before` cũng không phải cách sửa mặc định cho một subclass vẫn đang theo mô hình TestCase.

Nếu chọn giữ mô hình cũ, chuẩn bị fixture bằng override đúng hợp đồng:

```java
@Override
protected void setUp() throws Exception {
    super.setUp();
    orderService = new StubOrderService();
}
```

Nếu override `tearDown()`, bảo đảm gọi lifecycle lớp cha khi cần, thường qua `finally`. Cũng phải biết rằng nếu `setUp()` thất bại trước khi chạy test, không thể mặc định mọi tài nguyên đã tạo dở đều được `tearDown()` giải phóng; setup tài nguyên cần có xử lý thất bại phù hợp.

### Không gắn hai mô hình vào cùng một phương thức

Một phương thức vừa có tên `testConfirm()` vừa mang `org.junit.jupiter.api.Test` trong subclass TestCase có thể được nhiều engine nhận diện, tùy cấu hình discovery. Khi đó fixture, lifecycle hoặc tác dụng phụ có nguy cơ chạy hai lần.

Chọn một mô hình cho mỗi lớp trong giai đoạn chuyển tiếp. Việc gọi assertion Jupiter trong một test cũ không tự chuyển engine; assertion là lời gọi Java, còn discovery và lifecycle do mô hình thực thi quyết định.

## 5. Giữ test cũ chạy trên Platform bằng cấu hình có chủ đích

Một cấu hình chuyển tiếp có thể giữ cả Jupiter và Vintage:

```text
Test kiểu TestCase/JUnit 4 → Vintage
Test Jupiter              → Jupiter engine
Cùng chạy qua             → JUnit Platform
```

Mục đích là giữ bảo vệ hồi quy trong lúc nâng ứng dụng, rồi chuyển dần những nhóm test có thể chuyển. Không cần viết lại toàn bộ test flow trước khi xác minh bộ cũ vẫn chạy.

### Ví dụ Gradle Kotlin DSL

```kotlin
val junitVersion: String by project

dependencies {
    testImplementation(platform("org.junit:junit-bom:$junitVersion"))

    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("junit:junit:4.13.2")

    testRuntimeOnly("org.junit.vintage:junit-vintage-engine")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform {
        includeEngines("junit-jupiter", "junit-vintage")
    }
}
```

`junitVersion` phải được khai báo theo bộ phiên bản dự án đã chọn, chẳng hạn trong quản lý version của build. BOM đồng bộ các artifact Platform/Jupiter/Vintage thuộc dòng đó; không tự giả định số phiên bản của Platform luôn bằng Jupiter trong mọi dòng JUnit.

Nếu Spring Boot hoặc platform của tổ chức đã quản lý JUnit, hãy chọn một nguồn quyết định phiên bản thay vì nhập thêm BOM khác gây override ngoài ý muốn.

`testRuntimeOnly` phù hợp với engine/launcher không được mã test gọi trực tiếp. Nếu test dùng API launcher, cần đưa dependency đó vào compile classpath tương ứng. JUnit 4 được khai báo rõ vì test hoặc superclass sử dụng `junit.framework`/`org.junit`.

`useJUnitPlatform()` và các dependency engine/launcher được mô tả trong [Gradle: Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html).

Bộ lọc `includeEngines(...)` ở ví dụ chủ động giữ hai engine. Nếu dự án dùng thêm engine khác, cần điều chỉnh hoặc bỏ giới hạn; chỉ giữ `junit-jupiter` sẽ loại nhóm test Vintage dù JAR Vintage đã có mặt.

Nếu có task tích hợp với source set/classpath riêng, kiểm tra nó nhận được dependency cần thiết. Áp dụng `useJUnitPlatform()` cho task không tự bổ sung engine vào classpath của task đó.

### Ví dụ Maven

Đoạn cấu hình sau dùng các property phiên bản do dự án khai báo. Nó minh họa cách quản lý đồng bộ; chưa phải một POM hoàn chỉnh có thể chạy độc lập.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>junit</groupId>
        <artifactId>junit</artifactId>
        <version>4.13.2</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.vintage</groupId>
        <artifactId>junit-vintage-engine</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>${maven-surefire-plugin.version}</version>
            <configuration>
                <failIfNoTests>true</failIfNoTests>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Chọn Surefire hỗ trợ JUnit Platform và tương thích với JUnit/JDK đã chọn. Cơ chế provider thay đổi theo phiên bản plugin: tài liệu Surefire 3.6.0 trở lên mô tả việc chạy JUnit qua Platform và hỗ trợ Vintage cho JUnit 4.12 trở lên. Không áp dụng máy móc bảng chọn provider của plugin cũ cho plugin mới. Xem [Maven Surefire: Using JUnit](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit.html).

Một số plugin có thể tự hỗ trợ đưa engine thích hợp vào đường chạy; vì vậy phải kiểm tra provider/runtime thực tế, không suy từ mỗi dependency được khai báo. Cấu hình tường minh vẫn cần tránh ghi đè các engine bằng phiên bản lệch nhau.

`failIfNoTests` giúp phát hiện task không chạy ca nào trong phạm vi đã cấu hình. Nó không phát hiện trường hợp Jupiter chạy 10 ca nhưng toàn bộ 40 ca cũ bị bỏ sót. Với multi-module, chỉ áp chính sách phù hợp cho module/task thực sự phải có test.

## 6. Một lớp test Web Flow kế thừa với lifecycle rõ ràng

Giả sử ứng dụng có flow minh họa bắt đầu tại `edit` và cho hủy:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">
    <view-state id="edit" view="checkoutForm">
        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>
    <end-state id="cancelled" />
</flow>
```

Đường dẫn trong lớp test dưới là vị trí minh họa của XML thuộc ứng dụng cần kiểm thử. Khi áp dụng vào dự án, dùng định nghĩa sản phẩm thật và các phụ thuộc phù hợp.

```java
package com.example.webflow;

import org.springframework.webflow.engine.builder.support.FlowDefinitionResource;
import org.springframework.webflow.engine.builder.support.FlowDefinitionResourceFactory;
import org.springframework.webflow.test.MockExternalContext;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;

public class CheckoutFlowExecutionTests extends AbstractXmlFlowExecutionTests {
    private boolean fixtureReady;

    @Override
    protected void setUp() throws Exception {
        super.setUp();
        fixtureReady = true;
    }

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory factory) {
        return factory.createFileResource(
                "src/main/webapp/WEB-INF/flows/checkout/checkout-flow.xml");
    }

    public void testStartsAtEdit() {
        assertTrue("Fixture must be initialized", fixtureReady);

        startFlow(new MockExternalContext());

        assertCurrentStateEquals("edit");
    }

    public void testCancelEndsWithCancelled() {
        assertTrue("Fixture must be initialized", fixtureReady);
        startFlow(new MockExternalContext());

        MockExternalContext context = new MockExternalContext();
        context.setEventId("cancel");
        resumeFlow(context);

        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("cancelled");
    }

    @Override
    protected void tearDown() throws Exception {
        try {
            fixtureReady = false;
        } finally {
            super.tearDown();
        }
    }
}
```

Ví dụ không thêm annotation Jupiter. Hai phương thức `public void test...()` cùng fixture `setUp()` diễn đạt nhất quán mô hình TestCase. Assertion về `fixtureReady` chỉ minh họa việc nhận biết setup đã chạy; fixture thật thường tạo stub, dữ liệu và tài nguyên cần thiết thay cho cờ này.

Đây là test thực thi định nghĩa flow với môi trường mock. Nó chưa chứng minh JSP render, HTTP binding, CSRF hoặc session store thật hoạt động. Các ca tích hợp MVC dùng mô hình JUnit khác có thể nằm ở lớp riêng và cần engine/lifecycle riêng.

## 7. Kiểm tra tên lớp, bộ lọc và task trước khi kết luận thiếu engine

Không thấy test không đồng nghĩa luôn thiếu Vintage. Lớp có thể đã bị task loại trước khi tới engine.

### Maven Surefire và Failsafe

Surefire mặc định chọn các mẫu như:

```text
Test*.java
*Test.java
*Tests.java
*TestCase.java
```

Vì vậy tên `CheckoutFlowExecutionTests` phù hợp với mẫu `*Tests`. Các mẫu và cách tùy biến được nêu tại [Surefire: Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html).

Failsafe mặc định dùng các mẫu khác, bao gồm `IT*.java`, `*IT.java`, `*ITCase.java`; xem [Failsafe: Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html). Lớp `CheckoutMvcIT` có thể không chạy ở `mvn test` nếu dự án giao nó cho Failsafe trong lifecycle tích hợp.

Để kiểm tra task tích hợp, dự án cần cấu hình execution/goals Failsafe phù hợp và chạy tới `verify`; chỉ thêm dependency JUnit không tự cấu hình lifecycle đó. Cũng không nên đổi toàn bộ tên lớp để “chạy được” nếu việc đổi tên vô tình chuyển trách nhiệm từ task tích hợp sang task unit.

### Các bộ lọc khác

- `include`/`exclude` ở plugin hoặc Gradle task.
- `includeEngines`/`excludeEngines` trên Platform.
- Tag Jupiter hoặc Category JUnit 4 và cách ánh xạ tương ứng.
- Profile build, source set hoặc module chưa được chạy.
- Test được skip/disable hoặc bị assumption loại khỏi phần thực thi.
- Suite cũ tự liệt kê lớp, có thể thiếu lớp mới hoặc tạo đường chạy trùng.
- Cấu hình IDE khác với task của CI.

Không dùng `--tests` hoặc `-Dtest` mãi như cách chữa cấu hình toàn bộ suite. Chạy chọn một lớp giúp chẩn đoán; bộ đầy đủ vẫn phải có quy tắc discovery đúng.

## 8. Chứng minh test đã chạy bằng báo cáo và phạm vi đối chiếu

Trong dự án ứng dụng, có thể chạy chọn một lớp đại diện trước:

```powershell
.\mvnw.cmd "-Dtest=CheckoutFlowExecutionTests" test
```

Hoặc với Gradle:

```powershell
.\gradlew.bat test --tests "com.example.webflow.CheckoutFlowExecutionTests" --rerun-tasks
```

Sau đó chạy task đầy đủ theo cấu hình dự án:

```powershell
.\mvnw.cmd verify
```

Hoặc:

```powershell
.\gradlew.bat test
```

Nếu có task tích hợp riêng trong Gradle, chạy thêm task đó; `test` không mặc định bao gồm mọi source set tự tạo. Với multi-module, chọn đúng module hoặc phạm vi reactor/build đã xác định.

### Đọc báo cáo thay vì chỉ nhìn mã thoát

Các vị trí thường gặp, có thể đã được tùy biến:

```text
Maven Surefire: target/surefire-reports
Maven Failsafe: target/failsafe-reports
Gradle:        build/test-results/<task-name>
Gradle HTML:   build/reports/tests/<task-name>
```

Đối chiếu ít nhất tên lớp và tên các ca quan trọng, số executed/skipped/failure cùng task chạy. Nếu công cụ báo unique ID hoặc engine, dùng thêm thông tin đó; không giả định mọi định dạng XML đều ghi trực tiếp engine.

Ví dụ bằng chứng mong muốn:

| Nhóm | Trước nâng cấp | Sau nâng cấp | Kết luận |
| --- | --- | --- | --- |
| TestCase của flow | Có startup, confirm, cancel, recovery | Cùng các ca xuất hiện trong báo cáo | Chưa mất nhóm bảo vệ cũ |
| Jupiter của action | Có các quy tắc nghiệp vụ | Các ca tương ứng vẫn thực thi | Engine mới hoạt động |
| Tích hợp MVC | Có binding, validation, session | Task tích hợp báo đúng phạm vi | Không bỏ quên lớp nằm ngoài unit test task |

Số ca có thể thay đổi hợp lệ khi tách/ghép hoặc tham số hóa test. Không cố giữ tổng số bằng mọi giá; cần giải thích được khác biệt và chứng minh các hành vi cũ vẫn được bao phủ.

Trong quá trình xác minh cấu hình ở một nhánh làm việc kiểm soát được, có thể tạm làm sai kỳ vọng của một ca quan trọng để chứng minh task thật sự báo thất bại vì assertion đó, rồi khôi phục ngay. Không để kiểm tra âm tính này trong mã được bàn giao và không nhầm lỗi “không tìm thấy test” với việc đã chạy test và phát hiện sai hành vi.

## 9. Chẩn đoán theo triệu chứng

| Triệu chứng | Điều tra trước |
| --- | --- |
| Build xanh, không có test | Task discovery, skip flag, classpath và engine |
| Jupiter chạy, test Web Flow cũ mất | Vintage/cơ chế chạy JUnit cũ và bộ lọc engine |
| `NoClassDefFoundError: junit/framework/TestCase` | Thiếu thư viện chứa API JUnit cũ ở test runtime |
| Test được tìm thấy nhưng stub null | Lifecycle bị trộn hoặc setup không được gọi |
| Một thao tác gửi đơn được gọi hai lần | Discovery trùng engine, suite trùng hoặc task chạy lặp |
| IDE chạy được, CI bỏ test | Runner của IDE, profile/module/task và classpath CI |
| `NoSuchMethodError` thuộc JUnit Platform | Artifact Platform/Jupiter/Vintage/launcher hoặc provider bị lệch |
| Lỗi `javax.servlet`/`jakarta.servlet` sau khi test đã chạy | Tương thích Spring/Servlet/mock web stack; không phải mặc định do engine |
| Ca tích hợp không xuất hiện | Failsafe hoặc task tích hợp chưa được chạy/cấu hình |

Phân tích dependency test runtime khi có dấu hiệu lệch phiên bản:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=junit:*,org.junit:*,org.junit.platform:*,org.junit.jupiter:*,org.junit.vintage:*"
```

Hoặc:

```powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath

.\gradlew.bat dependencyInsight --dependency junit-platform --configuration testRuntimeClasspath
```

Dependency `junit-jupiter-api` không tự là bằng chứng có engine chạy Jupiter. Ngược lại, thêm Vintage không sửa được plugin quá cũ, bộ lọc loại hết lớp hoặc task chưa được gọi.

Nếu test class dùng Spring TestContext, kiểm tra cả runner/extension và context configuration. `@RunWith(SpringRunner.class)` trong lớp JUnit 4 và `@ExtendWith(SpringExtension.class)` trong Jupiter là hai hợp đồng thực thi; không đổi riêng annotation mà bỏ qua lifecycle, transaction hoặc rule còn lại.

## 10. Chuyển dần sang Jupiter mà không mất hợp đồng kiểm thử

Một trình tự chuyển đổi thực tế có thể là:

1. Giữ suite cũ chạy bằng cơ chế tương thích và lập bằng chứng phạm vi.
2. Chọn một nhóm test đơn giản, chẳng hạn test POJO action hoặc validator không phụ thuộc harness TestCase.
3. Chuyển cả annotation, lifecycle, rule/runner và assertion liên quan.
4. Chạy riêng lớp mới rồi đối chiếu hành vi với lớp cũ.
5. Loại đường thực thi cũ của nhóm đã chuyển để tránh chạy trùng.
6. Giữ test flow kế thừa cho đến khi có harness hoặc cách tổ chức thay thế đã được kiểm chứng.
7. Chỉ bỏ Vintage khi không còn nhóm test hay superclass phụ thuộc mô hình cũ.

Ví dụ lớp Jupiter mới có cấu trúc độc lập:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class QuantityPolicyTests {
    private QuantityPolicy policy;

    @BeforeEach
    void prepare() {
        policy = new QuantityPolicy();
    }

    @Test
    void rejectsZeroQuantity() {
        assertFalse(policy.accepts(0));
    }

    @Test
    void acceptsPositiveQuantity() {
        assertTrue(policy.accepts(2));
    }

    static class QuantityPolicy {
        boolean accepts(int quantity) {
            return quantity > 0;
        }
    }
}
```

`QuantityPolicy` là ví dụ về đối tượng nghiệp vụ của ứng dụng, không phải API Web Flow. Lớp này không kế thừa TestCase, nên annotation và lifecycle Jupiter diễn đạt thống nhất mô hình mới.

### Những thay đổi dễ bỏ sót khi chuyển

| Hợp đồng cũ | Khi chuyển cần xem lại |
| --- | --- |
| `@Test(expected = ...)` của JUnit 4 | Dùng `assertThrows` bao quanh đúng thao tác cần kiểm tra |
| `@Rule`/`@ClassRule` | Extension hoặc cơ chế Jupiter tương đương theo mục đích |
| `@Before`/`@After` hoặc `setUp`/`tearDown` | Lifecycle mới và lời gọi lớp cha |
| Runner Spring hoặc Mockito | Extension/cấu hình mới và thời điểm tạo mock |
| Assertion có message đầu tiên | Jupiter thường đặt message sau các giá trị so sánh |
| Timeout | Kiểm tra tác động của thread/transaction, không thay máy móc |
| Category và suite cũ | Tag/discovery/task mới phải giữ đúng phạm vi |

Hướng dẫn annotation, assertion và migration được trình bày trong [JUnit 5 User Guide](https://docs.junit.org/5.12.1/user-guide/index.html). Cần dùng tài liệu đúng dòng JUnit của dự án, đặc biệt khi thay cả major version của platform và build plugin.

Không chuyển một subclass `AbstractXmlFlowExecutionTests` sang Jupiter chỉ bằng cách bỏ tiền tố `test` và thêm annotation. Nếu thay harness, cần bảo vệ lại việc nạp XML, tạo execution, đăng ký stub, reset trạng thái và kiểm tra outcome. Một wrapper tự tạo cũng phải có lifecycle rõ ràng; gọi trực tiếp phương thức test cũ không tự gọi setup/teardown như runner.

## 11. Tiêu chí hoàn tất việc rà soát bộ test kế thừa

Việc rà soát có thể coi là đạt khi có bằng chứng cho các điểm sau:

- Mỗi nhóm test đã được phân loại theo mô hình và task chịu trách nhiệm.
- Engine/provider và dependency runtime phù hợp với mô hình đó.
- Các ca quan trọng xuất hiện trong báo cáo sau nâng cấp.
- Setup/teardown, mock, dữ liệu và transaction hoạt động đúng lifecycle.
- Không có lớp bị chạy trùng ngoài chủ đích.
- Chênh lệch số ca được giải thích bằng thay đổi có chủ đích.
- CI và cách chạy được tài liệu hóa dùng cùng phạm vi cần bảo vệ.
- Việc giữ Vintage hoặc kế hoạch loại bỏ nó phù hợp với nền JUnit đã chọn.

Các hành vi Web Flow đáng giữ trong danh sách đối chiếu gồm: startup, event hợp lệ, nhánh lỗi, quay lại, hủy, output subflow và phục hồi. Test binding, validation và session ở tầng tích hợp cũng phải tiếp tục có nơi chạy rõ ràng.

Build xanh chỉ có ý nghĩa khi đúng các ca cần thiết đã được thực thi. Với ứng dụng Spring Web Flow cũ, đọc chuỗi kế thừa JUnit, kiểm tra engine và đối chiếu báo cáo là cách giữ lại bảo vệ hồi quy trước khi tiếp tục hiện đại hóa bộ test.
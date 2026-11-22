# Chọn lớp kiểm thử, nhóm kiểm thử và tag phù hợp với từng task

## Mục tiêu

Một dự án Java có thể có nhiều lớp kiểm thử với thời gian chạy và mục đích khác nhau. Task kiểm thử nhanh có thể chỉ chạy test đơn vị; task tích hợp cần thêm test cơ sở dữ liệu hoặc dịch vụ; task phát hành có thể chạy toàn bộ bộ test.

Apache Ant cho phép chọn phạm vi kiểm thử ở nhiều mức:

1. **Lớp kiểm thử**: chọn chính xác lớp nào được đưa vào lần chạy.
2. **Phương thức kiểm thử**: giới hạn một hoặc vài method trong một lớp.
3. **Nhóm hoặc tag**: chọn test theo ý nghĩa như `smoke`, `fast`, `integration`, `database` hoặc `slow`.
4. **Điều kiện của task**: chỉ chạy phần test khi property phù hợp được bật.

Cú pháp phụ thuộc framework đang dùng. Ant có task `junit` cho JUnit 3/4, task `junitlauncher` cho JUnit Platform/JUnit 5, còn TestNG cung cấp Ant task riêng. Cần chọn đúng cơ chế của framework thay vì dùng lẫn các thuộc tính.

## 1. Chọn kiểm thử theo lớp

### 1.1. Chạy một lớp bằng junit

Task `junit` có phần tử con `test` để chạy một lớp theo tên đầy đủ:

~~~xml
<junit printsummary="yes" haltonfailure="yes">
    <classpath>
        <pathelement location="build/classes"/>
        <pathelement location="build/test-classes"/>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </classpath>
    <formatter type="plain"/>
    <test name="com.example.user.UserServiceTest"/>
</junit>
~~~

Thuộc tính `name` là tên lớp đầy đủ, bao gồm package. Cách này phù hợp khi cần chạy lại một lớp vừa thất bại, điều tra lỗi trong một module hoặc tạo target riêng cho một lớp quan trọng.

### 1.2. Chạy nhiều lớp bằng batchtest

Khi cần chọn nhiều lớp theo quy tắc tên, dùng `batchtest` cùng FileSet:

~~~xml
<junit printsummary="yes" haltonfailure="yes">
    <classpath refid="test.classpath"/>
    <formatter type="plain"/>
    <batchtest todir="build/test-reports">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
            <exclude name="**/manual/**"/>
            <exclude name="**/*AbstractTest.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

BatchTest thu thập các resource khớp pattern rồi tạo tên lớp kiểm thử từ các tệp `.java` hoặc `.class`. Trong ví dụ:

- `**/*Test.class` chọn các lớp có tên kết thúc bằng Test ở mọi package.
- `**/manual/**` loại test cần chạy thủ công.
- `**/*AbstractTest.class` loại lớp cơ sở không phải test độc lập.

Nên trỏ FileSet đến thư mục chứa test đã biên dịch nếu target chạy sau bước compile test. Nếu quét thư mục nguồn, pattern phải khớp tệp `.java` và cấu trúc package.

### 1.3. Pattern include và exclude

FileSet dùng pattern theo đường dẫn tương đối với thư mục gốc:

| Pattern | Ý nghĩa |
|---|---|
| `**/*Test.class` | Lớp có tên kết thúc bằng Test ở mọi package |
| `**/*Tests.class` | Lớp có tên kết thúc bằng Tests |
| `**/service/**` | Mọi resource dưới package/thư mục service |
| `com/example/**` | Mọi resource dưới package com.example |
| `**/Slow*Test.class` | Lớp test bắt đầu bằng Slow |
| `**/*IntegrationTest.class` | Lớp test tích hợp theo quy ước tên |

Include xác định tập ứng viên; exclude loại các resource không muốn chạy. Nếu không có include, FileSet mặc định có thể chọn tất cả resource phù hợp trong thư mục. Vì vậy, hãy đặt include rõ ràng cho test suite.

Tên lớp nhất quán như `UserServiceTest`, `PaymentIntegrationTest` hoặc `DatabaseSlowTest` giúp chọn lớp đơn giản. Tuy nhiên, tên lớp chỉ mô tả quy ước; tag hoặc group phù hợp hơn khi cần phân loại theo hành vi.

### 1.4. Bỏ qua các lớp không phải test

Task `junit` hỗ trợ thuộc tính `skipNonTests` trên `test` và `batchtest`. Khi bật, Ant cố gắng loại các lớp không chứa test JUnit hợp lệ trước khi gửi chúng cho runner:

~~~xml
<junit printsummary="yes" haltonfailure="yes">
    <classpath refid="test.classpath"/>
    <batchtest todir="build/test-reports" skipNonTests="true">
        <fileset dir="build/test-classes">
            <include name="**/*.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

Điều này hữu ích nếu thư mục có nhiều lớp tiện ích hoặc lớp hỗ trợ. Dù vậy, pattern cụ thể như `**/*Test.class` thường dễ hiểu và ít quét quá rộng hơn.

## 2. Chọn phương thức kiểm thử

### 2.1. JUnit task

Phần tử `test` của task `junit` có thuộc tính `methods` để chỉ chạy các phương thức được liệt kê:

~~~xml
<junit printsummary="yes" haltonfailure="yes">
    <classpath refid="test.classpath"/>
    <formatter type="plain"/>
    <test name="com.example.user.UserServiceTest"
          methods="createsUser, rejectsDuplicateEmail"/>
</junit>
~~~

Tên method được phân cách bằng dấu phẩy. Cách này hữu ích khi một lớp có nhiều test nhưng chỉ cần chạy lại một vài method đang được điều tra.

### 2.2. JUnitLauncher

Task `junitlauncher` cũng hỗ trợ phần tử `test` với thuộc tính `methods`:

~~~xml
<junitlauncher haltOnFailure="true" printSummary="true">
    <classpath refid="junit5.test.classpath"/>
    <test name="com.example.user.UserServiceTest"
          methods="createsUser, rejectsDuplicateEmail"/>
</junitlauncher>
~~~

Nếu muốn quét nhiều lớp theo pattern, dùng `testclasses` thay vì khai báo từng `test`.

Chọn method phù hợp khi cần tái hiện nhanh một lỗi cụ thể hoặc chạy một method dưới debugger/profiler. Chọn cả lớp khi các method thường được xem như một đơn vị và muốn giữ lifecycle chung. Tránh duy trì danh sách method dài trong buildfile nếu tag hoặc group có thể biểu đạt cùng mục đích ổn định hơn.

## 3. Nhóm kiểm thử và tag là gì?

Nhóm và tag gắn nhãn cho test theo mục đích hoặc đặc tính. Chúng cho phép chọn test theo ý nghĩa thay vì phụ thuộc hoàn toàn vào tên lớp.

| Nhãn | Ý nghĩa | Khi thường chạy |
|---|---|---|
| `smoke` | Kiểm tra nhanh chức năng cốt lõi | Sau build hoặc deploy |
| `fast` | Test đơn vị chạy nhanh | Trong quá trình phát triển và CI |
| `integration` | Kiểm tra tương tác giữa thành phần | Trên CI hoặc trước merge |
| `database` | Cần cơ sở dữ liệu | Khi môi trường DB sẵn sàng |
| `network` | Cần kết nối mạng hoặc dịch vụ ngoài | Trong môi trường tích hợp |
| `slow` | Test chạy lâu | Theo lịch hoặc trước phát hành |
| `unstable` | Test đang được theo dõi vì chưa ổn định | Theo chính sách riêng |

Một test có thể mang nhiều nhãn, chẳng hạn vừa `integration` vừa `database`.

Cần phân biệt ba tầng:

- **Pattern FileSet** chọn lớp theo tên hoặc vị trí tệp.
- **Tag/group của framework** chọn test theo metadata khai báo trong mã nguồn hoặc suite.
- **Target Ant** gom các bước build và quyết định task nào được chạy.

Ba tầng có thể phối hợp trong cùng một lần chạy.

## 4. JUnit 3/4 với task junit

### 4.1. Chọn lớp và method

Task `junit` của Ant hỗ trợ JUnit 3 và JUnit 4. Nó có thể chọn một lớp qua `<test>`, nhiều lớp qua `<batchtest>` và FileSet, hoặc một số method qua thuộc tính `methods`.

~~~xml
<target name="test-unit" depends="compile-test">
    <junit printsummary="yes" haltonfailure="yes">
        <classpath refid="test.classpath"/>
        <formatter type="plain"/>
        <batchtest todir="build/test-reports/unit">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
                <exclude name="**/*IntegrationTest.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
~~~

Task `junit` không có thuộc tính chung `includeTags` hoặc `excludeTags` như JUnit Platform. Nếu dùng JUnit 4 Categories, hãy tổ chức suite bằng runner của JUnit 4 rồi gọi suite class như một test class thông thường.

### 4.2. JUnit 4 Categories

JUnit 4 có cơ chế Categories để gắn category vào test method hoặc lớp. Đầu tiên, định nghĩa marker interface:

~~~java
public interface FastTests {}
public interface IntegrationTests {}
~~~

Gắn category cho các method:

~~~java
import org.junit.Test;
import org.junit.experimental.categories.Category;

public class UserServiceTest {
    @Test
    @Category(FastTests.class)
    public void createsUser() {
        // test logic
    }

    @Test
    @Category(IntegrationTests.class)
    public void storesUserInDatabase() {
        // test logic
    }
}
~~~

Tạo suite dùng runner `Categories` để chỉ chọn một category:

~~~java
import org.junit.experimental.categories.Categories;
import org.junit.runner.RunWith;
import org.junit.runners.Suite;

@RunWith(Categories.class)
@Categories.IncludeCategory(FastTests.class)
@Suite.SuiteClasses({
    UserServiceTest.class,
    OrderServiceTest.class
})
public class FastTestSuite {}
~~~

Ant chạy suite class như một lớp JUnit bình thường:

~~~xml
<junit printsummary="yes" haltonfailure="yes">
    <classpath refid="test.classpath"/>
    <formatter type="plain"/>
    <test name="com.example.suites.FastTestSuite"/>
</junit>
~~~

Để tạo suite tích hợp, dùng `@Categories.IncludeCategory(IntegrationTests.class)` và một suite class riêng. JUnit 4 Categories được thực thi bởi runner trong JUnit; Ant chỉ chọn suite class. Không nhầm category của JUnit 4 với tag của JUnit 5.

## 5. JUnit 5 tags với junitlauncher

### 5.1. Gắn tag trong mã nguồn

JUnit 5 dùng annotation `@Tag` để gắn nhãn cho lớp hoặc method:

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

class PaymentServiceTest {
    @Test
    @Tag("fast")
    void calculatesTotal() {
        // test logic
    }

    @Test
    @Tag("integration")
    @Tag("database")
    void savesPayment() {
        // test logic
    }
}
~~~

Tag ở cấp lớp áp dụng cho các test trong lớp; tag ở cấp method mô tả riêng test đó. Có thể gắn nhiều tag lên cùng một lớp hoặc method.

### 5.2. includeTags và excludeTags

Task `junitlauncher` hỗ trợ `includeTags` và `excludeTags` từ Apache Ant 1.10.7:

~~~xml
<junitlauncher includeTags="fast,smoke"
               excludeTags="unstable"
               haltOnFailure="true"
               printSummary="true">
    <classpath refid="junit5.test.classpath"/>
    <testclasses outputDir="build/test-reports/fast">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </testclasses>
</junitlauncher>
~~~

- `includeTags` nhận danh sách tag phân cách bằng dấu phẩy.
- `excludeTags` loại các test mang tag tương ứng.
- Nếu test mang tag bị loại, nó không chạy ngay cả khi cũng mang tag được include.

Ví dụ, test mang cả `fast` và `unstable` sẽ bị loại khi cấu hình `includeTags="fast"` và `excludeTags="unstable"`.

### 5.3. Chọn lớp trước, lọc tag sau

Hai bộ lọc hoạt động ở hai tầng:

1. FileSet trong `testclasses` chọn các tệp lớp theo tên.
2. JUnit Platform nhận những lớp đó rồi áp dụng includeTags/excludeTags để chọn test thực sự chạy.

Ví dụ, chỉ quét package service và repository, sau đó chạy test có tag integration:

~~~xml
<junitlauncher includeTags="integration"
               haltOnFailure="true"
               printSummary="true">
    <classpath refid="junit5.test.classpath"/>
    <testclasses outputDir="build/test-reports/integration">
        <fileset dir="build/test-classes">
            <include name="com/example/service/**"/>
            <include name="com/example/repository/**"/>
            <exclude name="**/*AbstractTest.class"/>
        </fileset>
    </testclasses>
</junitlauncher>
~~~

Đường dẫn trong FileSet tương đối với thư mục `build/test-classes`. Pattern phải khớp cấu trúc package thực tế.

### 5.4. Chạy một lớp hoặc một số method

~~~xml
<junitlauncher includeTags="integration" haltOnFailure="true">
    <classpath refid="junit5.test.classpath"/>
    <test name="com.example.payment.PaymentServiceTest"
          methods="savesPayment, rejectsInvalidCard"/>
</junitlauncher>
~~~

Tag và method selection cùng giới hạn phạm vi. Một method không có tag phù hợp vẫn không được chạy dù tên method đã được liệt kê.

### 5.5. Chọn test engine

JUnit Platform có thể chạy test thông qua nhiều engine, chẳng hạn:

- `junit-jupiter` chạy test JUnit Jupiter.
- `junit-vintage` hỗ trợ test JUnit 3/4 thông qua Platform.

Có thể giới hạn engine bằng `includeEngines` hoặc loại engine bằng `excludeEngines`:

~~~xml
<junitlauncher>
    <classpath refid="junit5.test.classpath"/>
    <testclasses includeEngines="junit-jupiter"
                 outputDir="build/test-reports/jupiter">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </testclasses>
</junitlauncher>
~~~

Engine filter chọn bộ thực thi framework; tag filter chọn nhóm test trong các engine đang dùng. Để chạy JUnit 4 qua Platform, cần Vintage engine và các thư viện tương ứng trên classpath.

### 5.6. Thư viện cần thiết cho junitlauncher

Task `junitlauncher` cần thư viện JUnit Platform và engine tương ứng; chúng không được đóng gói đầy đủ trong bản phân phối Ant. Cần cung cấp `ant-junitlauncher.jar` theo cách Ant yêu cầu và khai báo JUnit Platform/Jupiter/Vintage JAR trong classpath.

~~~xml
<path id="junit5.test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <fileset dir="lib/junit-platform">
        <include name="*.jar"/>
    </fileset>
    <fileset dir="lib/junit-jupiter">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Nếu thiếu engine hoặc platform launcher, task có thể không tìm thấy engine hoặc không phát hiện test. Hãy quản lý các JAR với phiên bản tương thích.

## 6. TestNG groups với Ant task

### 6.1. Gắn group trong mã nguồn

TestNG dùng annotation `@Test(groups=...)` để gán method vào một hoặc nhiều nhóm:

~~~java
import org.testng.annotations.Test;

public class CheckoutTest {
    @Test(groups = {"fast", "smoke"})
    public void calculatesSubtotal() {
        // test logic
    }

    @Test(groups = {"integration", "database"})
    public void persistsOrder() {
        // test logic
    }

    @Test(groups = {"slow"})
    public void processesLargeOrder() {
        // test logic
    }
}
~~~

TestNG có thể include hoặc exclude group khi chạy. Một method có thể thuộc nhiều group.

### 6.2. Đăng ký TestNG Ant task

Task TestNG do TestNG cung cấp, không phải task JUnit lõi của Ant. Cần khai báo taskdef và cung cấp JAR TestNG:

~~~xml
<path id="testng.classpath">
    <pathelement location="lib/testng.jar"/>
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
</path>

<taskdef name="testng"
         classname="org.testng.TestNGAntTask"
         classpathref="testng.classpath"/>
~~~

Phiên bản TestNG cần tương thích với JDK và Ant của môi trường build. Hãy dùng tài liệu Ant task tương ứng với phiên bản TestNG trong dự án.

### 6.3. Chọn lớp và group

Có thể chọn lớp bằng `classfileset`, nhóm bằng `groups` và `excludedgroups`:

~~~xml
<target name="test-smoke">
    <testng classpathref="testng.classpath"
            groups="smoke"
            excludedgroups="unstable"
            outputdir="build/test-reports/smoke"
            haltonfailure="true">
        <classfileset dir="build/test-classes">
            <include name="**/*Test.class"/>
            <exclude name="**/Abstract*Test.class"/>
        </classfileset>
    </testng>
</target>
~~~

- `classfileset` chọn các lớp ứng viên.
- `groups="smoke"` yêu cầu TestNG chạy method thuộc group smoke.
- `excludedgroups="unstable"` loại method thuộc group unstable.
- `haltonfailure="true"` làm build dừng nếu test thất bại.

Các group được phân cách bằng dấu phẩy hoặc khoảng trắng trong Ant task. Nếu cần quy tắc phức tạp hơn, định nghĩa group và suite trong `testng.xml`.

### 6.4. Tổ chức suite bằng testng.xml

~~~xml
<!DOCTYPE suite SYSTEM "https://testng.org/testng-1.0.dtd">
<suite name="ApplicationSuite">
    <test name="SmokeTests">
        <groups>
            <run>
                <include name="smoke"/>
                <exclude name="unstable"/>
            </run>
        </groups>
        <classes>
            <class name="com.example.user.UserServiceTest"/>
            <class name="com.example.order.OrderServiceTest"/>
        </classes>
    </test>
</suite>
~~~

Ant có thể chạy suite file qua `xmlfileset`:

~~~xml
<target name="test-suite">
    <testng classpathref="testng.classpath"
            outputdir="build/test-reports"
            haltonfailure="true">
        <xmlfileset dir="config/testng">
            <include name="smoke-suite.xml"/>
        </xmlfileset>
    </testng>
</target>
~~~

Suite XML tách lựa chọn lớp, method và group khỏi buildfile. Nếu đồng thời khai báo groups/excludedgroups trên task, các lựa chọn ở task có thể ảnh hưởng hoặc ghi đè cấu hình group trong suite theo quy tắc TestNG. Hãy chọn một nơi làm nguồn cấu hình chính.

### 6.5. Group lồng nhau và chọn method

TestNG cho phép định nghĩa group bao gồm các group khác. Ví dụ `all-fast` có thể gồm `smoke` và `unit`.

TestNG cũng hỗ trợ include/exclude method trong suite XML. Pattern method là regular expression, không phải wildcard FileSet:

~~~xml
<classes>
    <class name="com.example.user.UserServiceTest">
        <methods>
            <include name="creates.*"/>
            <exclude name="createsLegacyUser"/>
        </methods>
    </class>
</classes>
~~~

Không dùng cú pháp `**/*Test.class` của FileSet trong trường `<methods>`; hai cơ chế có quy tắc pattern khác nhau.

## 7. Tổ chức target cho từng loại kiểm thử

Một buildfile thường có target riêng để chạy đúng phạm vi:

| Target | Phạm vi | Mục đích |
|---|---|---|
| `test-smoke` | Test cốt lõi, rất nhanh | Kiểm tra sau build/deploy |
| `test-unit` | Test đơn vị | Chạy thường xuyên khi phát triển |
| `test-integration` | Test giữa các thành phần | Xác nhận dependency hoạt động cùng nhau |
| `test-slow` | Test lâu hoặc tốn tài nguyên | Chạy theo lịch hoặc trước release |
| `test-all` | Toàn bộ test | Kiểm tra trước phát hành |

Ví dụ với JUnit 5:

~~~xml
<target name="test-smoke" depends="compile-test">
    <junitlauncher includeTags="smoke"
                   excludeTags="unstable"
                   haltOnFailure="true"
                   printSummary="true">
        <classpath refid="junit5.test.classpath"/>
        <testclasses outputDir="build/test-reports/smoke">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </testclasses>
    </junitlauncher>
</target>

<target name="test-unit" depends="compile-test">
    <junitlauncher includeTags="fast"
                   excludeTags="integration,slow,unstable"
                   haltOnFailure="true"
                   printSummary="true">
        <classpath refid="junit5.test.classpath"/>
        <testclasses outputDir="build/test-reports/unit">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </testclasses>
    </junitlauncher>
</target>

<target name="test-integration" depends="compile-test">
    <junitlauncher includeTags="integration"
                   haltOnFailure="true"
                   printSummary="true">
        <classpath refid="junit5.test.classpath"/>
        <testclasses outputDir="build/test-reports/integration">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </testclasses>
    </junitlauncher>
</target>

<target name="test-all" depends="compile-test">
    <junitlauncher haltOnFailure="true" printSummary="true">
        <classpath refid="junit5.test.classpath"/>
        <testclasses outputDir="build/test-reports/all">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </testclasses>
    </junitlauncher>
</target>
~~~

Ví dụ giả định test class đã được compile và JUnit Platform có engine cùng thư viện cần thiết. Tag `fast`, `smoke`, `integration` phải được gắn trong mã nguồn. Nếu một test có nhiều tag, hãy thiết kế include/exclude sao cho target không bỏ qua test quan trọng.

### 7.1. Bật hoặc tắt phần test theo property

Ant hỗ trợ `if` và `unless` trên các phần tử test tương ứng. Có thể dùng property để điều khiển việc chạy testclasses:

~~~xml
<target name="test-integration" depends="compile-test">
    <junitlauncher haltOnFailure="true">
        <classpath refid="junit5.test.classpath"/>
        <testclasses if="run.integration"
                     outputDir="build/test-reports/integration">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </testclasses>
    </junitlauncher>
</target>
~~~

Gọi Ant với:

~~~text
ant -Drun.integration=true test-integration
~~~

Property điều khiển việc thực hiện phần testclasses; nó không thay thế tag filtering. Có thể dùng cả hai để chỉ chạy integration tests khi được bật.

## 8. Kết hợp các tầng lựa chọn

Khi xây dựng một task, hãy xác định theo thứ tự:

1. **Framework/engine**: JUnit 4, JUnit Platform/Jupiter hay TestNG.
2. **Lớp**: FileSet hoặc tên lớp đầy đủ.
3. **Method**: nếu cần chạy một số method cụ thể.
4. **Tag/group**: theo ý nghĩa của test.
5. **Hành vi khi thất bại**: dừng build, ghi property hoặc tiếp tục thu thập kết quả.

Ví dụ với JUnit 5:

~~~xml
<junitlauncher includeTags="integration"
               excludeTags="unstable"
               haltOnFailure="true">
    <classpath refid="junit5.test.classpath"/>
    <testclasses outputDir="build/test-reports/integration">
        <fileset dir="build/test-classes">
            <include name="com/example/payment/**"/>
            <exclude name="**/*AbstractTest.class"/>
        </fileset>
    </testclasses>
</junitlauncher>
~~~

Task chỉ gửi lớp thuộc package payment cho JUnit Platform. Platform sau đó lọc test theo tag integration và loại tag unstable.

Nếu không có lớp nào khớp FileSet hoặc không có test mang tag được include, có thể không có test nào được thực thi. Hãy xem summary và report để phát hiện trường hợp target chạy nhưng phạm vi lựa chọn quá hẹp.

## 9. Quy tắc đặt tên lớp, group và tag

### 9.1. Tên lớp

Một số quy ước phổ biến:

- `UserServiceTest`: test đơn vị cho service.
- `PaymentIntegrationTest`: test tích hợp thanh toán.
- `DatabaseRepositoryTest`: test repository liên quan DB.
- `AbstractRepositoryTest`: lớp cơ sở, không chạy trực tiếp.

Tên lớp nhất quán giúp FileSet chọn đúng nhóm bằng pattern ngắn. Không nên tạo quá nhiều hậu tố khó phân biệt.

### 9.2. Tag và group

Chọn tag/group dựa trên một chiều phân loại có ý nghĩa:

- Tốc độ: `fast`, `slow`.
- Phạm vi: `unit`, `integration`, `end-to-end`.
- Dependency: `database`, `network`, `filesystem`.
- Vai trò: `smoke`, `regression`, `acceptance`.

Không nên tạo tag cho từng test riêng lẻ nếu không có target hoặc quy trình nào cần dùng tag đó. Tag quá chi tiết làm cấu hình build khó duy trì.

Một test có thể có nhiều nhãn:

~~~java
@Test
@Tag("integration")
@Tag("database")
@Tag("slow")
void persistsOrderAndReloadsIt() {
    // test logic
}
~~~

Target `test-integration` có thể chọn tag integration, còn target chạy kiểm thử nhanh có thể loại tag slow.

### 9.3. Không nhầm tag với pattern

JUnit 5 tags là nhãn được framework so sánh theo tên. FileSet dùng wildcard theo đường dẫn. TestNG groups hỗ trợ regular expression trong cấu hình nhóm. Không thể lấy pattern FileSet rồi đặt nguyên vào includeTags hoặc TestNG groups mà kỳ vọng cùng hành vi.

## 10. Xử lý lỗi và báo cáo

### 10.1. Dừng build khi test thất bại

Với JUnit task, đặt `haltonfailure="yes"` để build thất bại khi có test fail. Với JUnitLauncher, dùng `haltOnFailure="true"`. Với TestNG Ant task, dùng `haltonfailure="true"`.

~~~xml
<junit haltonfailure="yes" printsummary="yes">
    <formatter type="plain"/>
    <batchtest todir="build/test-reports">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
~~~

Nếu muốn chạy hết các test để thu thập mọi kết quả trước khi quyết định, có thể không dừng ngay rồi kiểm tra failure property ở bước sau. Target cuối cùng vẫn cần trả build status phù hợp với CI.

### 10.2. Báo cáo riêng cho từng task

Dùng thư mục report riêng cho smoke, unit, integration và slow:

~~~text
build/test-reports/
├── smoke/
├── unit/
├── integration/
└── slow/
~~~

Với JUnit cũ, formatter như `plain`, `brief` hoặc `xml` ghi kết quả theo định dạng đã chọn. Với JUnitLauncher, dùng listener như `legacy-plain` hoặc `legacy-xml`. TestNG có `outputdir` và hỗ trợ reporter/listener.

### 10.3. Phát hiện không có test nào được chạy

Một task thành công không nhất thiết chứng minh rằng có test đã chạy. Pattern có thể không khớp, tag có thể không tồn tại hoặc engine có thể không được nạp.

Khi cấu hình lựa chọn mới:

- Xem summary số lượng test được tìm thấy, chạy, bỏ qua và thất bại.
- Kiểm tra report có được tạo trong đúng thư mục không.
- Kiểm tra FileSet có khớp class file đã compile không.
- Kiểm tra tag/group có thực sự được khai báo trong test không.
- Kiểm tra classpath có engine và framework phù hợp không.

Trong CI, trường hợp không có test chạy cần được chú ý, đặc biệt với target bắt buộc như smoke hoặc regression.

## 11. Bảng chọn task theo framework

| Framework | Task Ant | Chọn lớp | Chọn method | Nhóm/tag |
|---|---|---|---|---|
| JUnit 3/4 | `junit` | `test`, `batchtest` + FileSet | `methods` trên test | JUnit 4 Categories qua suite/runner; không có includeTags trực tiếp |
| JUnit 5 | `junitlauncher` | `test`, `testclasses` + Resource Collection | `methods` trên test | `includeTags`, `excludeTags`; từ Ant 1.10.7 |
| TestNG | Task `testng` do TestNG cung cấp | `classfileset`, `xmlfileset`, suite XML | `methods` hoặc suite XML | `groups`, `excludedgroups` |

`junitlauncher` được giới thiệu trong Ant 1.10.6; includeTags/excludeTags được hỗ trợ từ Ant 1.10.7. TestNG Ant task cần thư viện và taskdef của TestNG. Kiểm tra phiên bản Ant, JUnit, TestNG và JDK trước khi dùng các thuộc tính mới.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy test class | FileSet trỏ sai thư mục hoặc pattern sai | Trỏ đến thư mục test đã compile và kiểm tra package |
| Batchtest chạy cả lớp tiện ích | Pattern quá rộng hoặc thiếu exclude | Dùng hậu tố Test rõ ràng, cân nhắc skipNonTests |
| Chạy nhầm class từ package khác | Tên lớp hoặc pattern không giới hạn package | Dùng tên đầy đủ hoặc prefix package |
| Test method không chạy | Sai tên trong methods hoặc method không phải test hợp lệ | Kiểm tra annotation và chính tả |
| JUnit 5 không nhận tag | Đang dùng task junit cũ hoặc thiếu engine | Dùng junitlauncher và khai báo engine |
| includeTags không được nhận diện | Ant cũ hơn 1.10.7 | Nâng cấp Ant hoặc dùng lựa chọn phù hợp phiên bản |
| JUnit 4 category không lọc | Mong task junit hiểu Categories trực tiếp | Tạo suite dùng Categories runner |
| TestNG không nhận groups | Taskdef/classpath chưa đúng hoặc sai thuộc tính | Kiểm tra TestNG Ant task |
| Không có test chạy nhưng target thành công | Pattern hoặc tag không khớp | Xem summary và report |
| Report bị ghi đè | Nhiều task dùng chung thư mục/tên report | Tạo thư mục riêng cho từng nhóm |

## 13. Thực hành tốt

- Chọn lớp bằng FileSet khi muốn giới hạn theo package hoặc quy ước tên.
- Dùng tên lớp đầy đủ khi cần chạy một lớp cụ thể.
- Chọn method riêng lẻ chủ yếu để debug hoặc chạy lại lỗi.
- Dùng JUnit 4 Categories qua suite runner nếu dự án còn dùng JUnit 4.
- Dùng JUnit 5 `@Tag`, `includeTags` và `excludeTags` qua `junitlauncher`.
- Dùng TestNG groups và suite XML nếu dự án dùng TestNG.
- Tách target smoke, unit, integration, slow và all để mỗi task có mục đích rõ ràng.
- Đặt tag/group theo ý nghĩa ổn định.
- Kết hợp chọn lớp và tag để giới hạn cả package lẫn loại test.
- Đặt `haltonfailure` hoặc `haltOnFailure` phù hợp với CI.
- Dùng report directory riêng cho mỗi nhóm chạy.
- Xác nhận có test thực sự được thực thi thay vì chỉ dựa vào exit code thành công.
- Quản lý tương thích phiên bản giữa Ant, JUnit engine, TestNG và JDK.

## 14. Tự kiểm tra cấu hình lựa chọn test

Trước khi đưa target test vào CI, hãy tự trả lời:

1. Dự án dùng JUnit 3/4, JUnit 5 hay TestNG?
2. Task Ant có hỗ trợ đúng cơ chế group/tag của framework không?
3. FileSet đang quét thư mục nguồn hay thư mục class đã biên dịch?
4. Pattern có chọn đúng lớp và loại trừ lớp cơ sở hoặc lớp hỗ trợ không?
5. Có cần chạy toàn lớp hay chỉ một số method?
6. Tag/group đã được gắn trong test method hoặc class chưa?
7. Include và exclude có mâu thuẫn hoặc loại nhầm test quan trọng không?
8. JUnit engine hoặc TestNG library đã có trên classpath chưa?
9. Target có tạo report riêng và hiển thị số test thực sự chạy không?
10. Khi test fail, task có trả build status phù hợp với quy trình CI không?

Khi chọn đúng task theo framework, giới hạn lớp bằng FileSet hoặc tên đầy đủ, rồi áp dụng method, group hoặc tag ở đúng tầng, buildfile sẽ chạy đúng tập test cần thiết cho từng giai đoạn phát triển và phát hành.

## Tài liệu tham khảo

- [Apache Ant — JUnit Task](https://ant.apache.org/manual/Tasks/junit.html)
- [Apache Ant — JUnitLauncher Task](https://ant.apache.org/manual/Tasks/junitlauncher.html)
- [Apache Ant — FileSet](https://ant.apache.org/manual/Types/fileset.html)
- [TestNG — Ant Task](https://testng.org/testng-ant/)
- [TestNG — Test methods, classes and groups](https://testng.org/documentation.html)


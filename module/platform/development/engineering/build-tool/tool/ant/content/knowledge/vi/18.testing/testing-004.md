# Cấu hình thư viện launcher, test engine và classpath kiểm thử

Khi dùng Apache Ant để kiểm thử ứng dụng Java với JUnit 5, chỉ có các lớp kiểm thử đã biên dịch là chưa đủ. JUnit Platform cần một **Launcher** để khởi động quá trình kiểm thử, một **Test Engine** để nhận diện và thực thi loại kiểm thử cụ thể, cùng các thư viện API mà mã kiểm thử sử dụng.

Các thư viện này phải xuất hiện đúng classpath ở đúng giai đoạn. Nếu thiếu JUnit API, mã kiểm thử không biên dịch được. Nếu thiếu engine, launcher có thể khởi động nhưng không tìm thấy engine phù hợp để chạy test. Nếu thiếu launcher hoặc cấu hình task Ant không đúng, task `junitlauncher` không thể điều phối phiên chạy. Nếu thiếu lớp ứng dụng hoặc dependency runtime, test có thể biên dịch thành công nhưng thất bại khi thực thi.

Bài học này tập trung vào việc phân biệt ba thành phần launcher, engine và API, sau đó cấu hình classpath biên dịch và classpath chạy kiểm thử trong buildfile Ant.

Sau bài học, bạn có thể:

- Phân biệt JUnit Platform Launcher, Test Engine và JUnit API.
- Nhận biết vai trò của Jupiter Engine và Vintage Engine.
- Phân biệt thư viện tích hợp task của Ant với thư viện JUnit Platform.
- Cấu hình dependency test riêng cho compile và runtime.
- Tạo classpath kiểm thử chứa lớp ứng dụng, lớp test và các thư viện cần thiết.
- Dùng task `<junitlauncher>` để chạy kiểm thử JUnit Platform.
- Nhận biết các lỗi thường gặp khi thiếu launcher, engine hoặc dependency trong classpath.

## 1. Các thành phần trong kiến trúc JUnit Platform

JUnit 5 được tổ chức thành nhiều module có vai trò khác nhau. Khi tích hợp với Ant, cần hiểu thành phần nào cung cấp API cho mã test, thành phần nào thực thi test và thành phần nào điều phối phiên chạy.

```text
                    Ant build.xml
                         |
                         v
                  <junitlauncher>
                         |
                         v
              JUnit Platform Launcher
                         |
             discovers and selects tests
                         |
              +----------+----------+
              |                     |
              v                     v
       Jupiter Engine        Vintage Engine
              |                     |
              v                     v
        JUnit Jupiter         JUnit 3 / JUnit 4
          test classes          test classes
```

Ba vai trò chính:

- **JUnit API:** cung cấp annotation và assertion để viết test, chẳng hạn `@Test`, `@BeforeEach`, `@AfterEach`, `Assertions.assertEquals(...)`.
- **Test Engine:** hiểu một mô hình kiểm thử và thực thi các test theo mô hình đó. Jupiter Engine chạy test viết bằng JUnit Jupiter; Vintage Engine chạy test JUnit 3 và JUnit 4 trên JUnit Platform.
- **JUnit Platform Launcher:** nhận yêu cầu chạy test, tìm engine, khám phá test, chọn test cần chạy và điều phối kết quả.

Ant task `<junitlauncher>` tích hợp với JUnit Platform Launcher. Task này giúp buildfile gọi quá trình chạy test từ các target Ant.

## 2. Phân biệt Launcher, Engine và API

### 2.1. JUnit Platform Launcher

Launcher là thành phần điều phối phiên kiểm thử. Nó cung cấp API để khởi tạo một lần chạy, khám phá các test, áp dụng bộ lọc và gửi kết quả tới listener.

Trong JUnit Platform, module thường được dùng là:

```text
org.junit.platform:junit-platform-launcher
```

Launcher không tự định nghĩa cú pháp `@Test` của Jupiter và cũng không tự thực thi mọi loại test. Nó cần các Test Engine tương ứng có mặt trên classpath để xử lý test được khám phá.

Trong Ant, task `<junitlauncher>` là cầu nối để sử dụng Launcher API. Khi cấu hình task, phải bảo đảm thư viện launcher phù hợp có thể được nạp trong môi trường thực thi kiểm thử.

### 2.2. JUnit Jupiter API

JUnit Jupiter API là thư viện mà mã nguồn test import để khai báo test và các lifecycle callback.

Module:

```text
org.junit.jupiter:junit-jupiter-api
```

Ví dụ:

```java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Để biên dịch lớp `CalculatorTest`, classpath biên dịch phải có `junit-jupiter-api` cùng các dependency compile cần thiết. Chỉ có Jupiter Engine ở runtime không thay thế được API mà compiler cần khi gặp các import `org.junit.jupiter.api.*`.

### 2.3. JUnit Jupiter Engine

Jupiter Engine là engine thực thi test được viết theo mô hình JUnit Jupiter.

Module:

```text
org.junit.jupiter:junit-jupiter-engine
```

Engine này được JUnit Platform Launcher phát hiện khi chạy test. Nó đọc annotation và cấu trúc test Jupiter, sau đó thực thi các phương thức test và báo kết quả về Platform.

Thông thường, Jupiter Engine thuộc dependency runtime. Mã test cần Jupiter API để biên dịch; lúc chạy, Launcher cần Jupiter Engine để thực thi các test đó.

### 2.4. JUnit Platform Engine API

Module:

```text
org.junit.platform:junit-platform-engine
```

Module này định nghĩa các abstraction và SPI mà những Test Engine triển khai để tích hợp với JUnit Platform. Engine Jupiter và Vintage phụ thuộc vào các thành phần Platform tương ứng.

Khi dùng dependency manager, các dependency bắc cầu của Engine thường được kéo về tự động. Không nên tự tải một JAR engine đơn lẻ rồi giả định mọi dependency của nó đã có.

### 2.5. JUnit Vintage Engine

Nếu dự án còn các test JUnit 3 hoặc JUnit 4, có thể cần Vintage Engine:

```text
org.junit.vintage:junit-vintage-engine
```

Vintage Engine cho phép các test JUnit 3/4 được chạy thông qua JUnit Platform Launcher. Với test JUnit 4, mã nguồn còn cần thư viện `junit:junit` trên classpath biên dịch; Vintage Engine được đặt trên classpath runtime để thực thi chúng.

Nếu dự án chỉ có test Jupiter, không cần thêm Vintage Engine. Chỉ thêm engine cho loại test mà dự án thực sự sử dụng.

## 3. Các JAR thường gặp và vai trò của chúng

| Module | Vai trò | Giai đoạn thường cần |
|---|---|---|
| `junit-jupiter-api` | Annotation, assertion và API viết test Jupiter. | Compile test; cũng có mặt gián tiếp khi chạy. |
| `junit-jupiter-engine` | Thực thi test Jupiter. | Runtime test. |
| `junit-platform-launcher` | Khởi tạo và điều phối phiên chạy trên JUnit Platform. | Runtime test launcher. |
| `junit-platform-engine` | API/SPI chung cho Test Engine. | Dependency của engine và nền tảng. |
| `junit-platform-commons` | Các tiện ích dùng chung của Platform. | Dependency bắc cầu. |
| `junit-vintage-engine` | Chạy test JUnit 3/4 qua Platform. | Runtime nếu cần test legacy. |
| `junit` | API JUnit 4, gồm `org.junit.Test` và assertion JUnit 4. | Compile test JUnit 4; runtime nếu test sử dụng. |
| `opentest4j` | Mô hình lỗi và kết quả kiểm thử dùng trong hệ sinh thái JUnit. | Dependency bắc cầu. |
| `apiguardian-api` | Annotation về trạng thái API được dùng trong hệ sinh thái JUnit. | Dependency bắc cầu. |

Không cần tự thêm tất cả các module trong bảng nếu dependency khai báo đã kéo chúng về. Bảng giúp bạn hiểu vì sao một JAR xuất hiện trong cache hoặc classpath khi xem log và dependency report.

## 4. Phân biệt thư viện Ant task và thư viện JUnit

Có hai lớp tích hợp khác nhau thường bị nhầm:

1. **Thư viện task của Ant:** cung cấp phần triển khai task như `<junitlauncher>` cho Ant.
2. **Thư viện JUnit Platform:** cung cấp Launcher, Engine, API và các dependency để chạy test.

Với các bản Ant hỗ trợ task JUnit Platform, task `<junitlauncher>` có từ Ant 1.10.3. Bản cài Ant cần có phần thư viện task tương ứng, thường là `ant-junitlauncher.jar` trong bộ thư viện Ant. JAR này là phần tích hợp task, không phải Jupiter Engine và cũng không thay thế `junit-platform-launcher`.

Hãy phân biệt:

| Thành phần | Được cung cấp bởi | Mục đích |
|---|---|---|
| `ant-junitlauncher.jar` | Bản cài Apache Ant | Đăng ký và triển khai task Ant `<junitlauncher>`. |
| `junit-platform-launcher.jar` | JUnit Platform | API launcher điều phối test. |
| `junit-jupiter-engine.jar` | JUnit Jupiter | Engine thực thi test Jupiter. |
| `junit-jupiter-api.jar` | JUnit Jupiter | API để mã test biên dịch. |

Nếu Ant báo không nhận ra task `junitlauncher`, hãy kiểm tra phiên bản Ant và thư viện task của Ant. Nếu task đã được nhận diện nhưng không tìm thấy engine hoặc launcher, hãy kiểm tra dependency JUnit trên classpath của phiên chạy test.

Task `<junit>` truyền thống của Ant là một tích hợp khác, thường được dùng với JUnit 3/4. Không nhầm task đó với `<junitlauncher>` dành cho JUnit Platform.

## 5. Classpath kiểm thử gồm những gì?

Một dự án Ant có thể có nhiều classpath khác nhau. Đối với kiểm thử, nên phân biệt classpath biên dịch test và classpath chạy test.

### 5.1. Classpath biên dịch test

Khi biên dịch mã nguồn test, compiler cần tìm:

- Các lớp đã biên dịch của ứng dụng, thường nằm trong `build/classes`.
- JUnit API mà mã test import.
- Các dependency mà mã test hoặc lớp ứng dụng tham chiếu trong quá trình biên dịch.
- Các thư viện test hỗ trợ mà mã nguồn test sử dụng.

Ví dụ, nếu `CalculatorTest` gọi `Calculator` trong ứng dụng, thư mục chứa `Calculator.class` phải có trên classpath.

### 5.2. Classpath chạy test

Khi chạy test, runtime cần:

- Lớp ứng dụng đã biên dịch.
- Lớp kiểm thử đã biên dịch.
- JUnit Platform Launcher.
- Test Engine tương ứng, chẳng hạn Jupiter Engine.
- Các dependency runtime của ứng dụng và test.
- Tài nguyên test cần đọc lúc chạy.

Chỉ đưa `junit-jupiter-api` vào classpath không đủ để chạy test Jupiter. Launcher cần một engine có thể nhận diện và thực thi các test.

### 5.3. Classpath của Ant và classpath của test

Ngoài hai classpath trên, Ant còn có classpath riêng để nạp task và thư viện tích hợp. Đây là ba phạm vi khác nhau:

```text
Ant process classpath
  +-- ant.jar và thư viện Ant
  +-- ant-junitlauncher.jar

Test compile classpath
  +-- build/classes
  +-- junit-jupiter-api
  +-- dependency compile của ứng dụng/test

Test runtime classpath
  +-- build/classes
  +-- build/test-classes
  +-- junit-platform-launcher
  +-- junit-jupiter-engine
  +-- dependency runtime của ứng dụng/test
```

Đưa một JAR vào classpath của Ant không tự động có nghĩa JAR đó được đưa vào classpath của mã test. Tương tự, thêm Jupiter Engine vào classpath test không tự làm Ant nhận diện task `<junitlauncher>` nếu thư viện task của Ant chưa có.

## 6. Cấu hình thư viện bằng JAR có sẵn

Với dự án nhỏ hoặc môi trường học tập, có thể đặt các JAR cần thiết trong thư mục `lib` của dự án. Ví dụ:

```text
ant-junit-project/
├── build.xml
├── lib/
│   ├── junit-jupiter-api-5.x.y.jar
│   ├── junit-jupiter-engine-5.x.y.jar
│   ├── junit-platform-launcher-1.x.y.jar
│   └── ... dependency bắc cầu phù hợp ...
├── src/
│   └── main/java/
└── src/
    └── test/java/
```

Tên phiên bản `5.x.y` và `1.x.y` trong sơ đồ chỉ là ký hiệu minh họa. Khi chọn phiên bản thật, hãy dùng các bản tương thích thuộc cùng release train của JUnit Platform/Jupiter và lấy đầy đủ dependency bắc cầu.

Có thể tạo các path Ant:

```xml
<path id="main.classpath">
    <fileset dir="lib">
        <include name="*.jar" />
    </fileset>
</path>

<path id="test.compile.classpath">
    <pathelement location="build/classes" />
    <path refid="main.classpath" />
</path>

<path id="test.runtime.classpath">
    <pathelement location="build/classes" />
    <pathelement location="build/test-classes" />
    <path refid="main.classpath" />
</path>
```

Đây là ví dụ đơn giản cho dự án tự quản lý JAR. Trong dự án lớn, nên dùng dependency manager để tự giải quyết dependency bắc cầu và phiên bản thay vì tự chép từng JAR.

## 7. Cấu hình dependency test bằng Apache Ivy

Vì Ivy có thể quản lý dependency cho Ant, ta có thể khai báo API, Launcher và Engine trong `ivy.xml`, sau đó tạo các path riêng cho compile và runtime.

### 7.1. Khai báo configuration

Ví dụ `ivy.xml`:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="ant-junit-demo" />

    <configurations>
        <conf name="compile" description="Application compile dependencies" />
        <conf name="runtime" extends="compile"
              description="Application runtime dependencies" />
        <conf name="test-compile" extends="compile"
              description="Test compilation dependencies" />
        <conf name="test-runtime" extends="test-compile,runtime"
              description="Test execution dependencies" />
    </configurations>

    <dependencies>
        <dependency org="org.junit.jupiter"
                    name="junit-jupiter-api"
                    rev="5.10.2"
                    conf="test-compile->default" />

        <dependency org="org.junit.jupiter"
                    name="junit-jupiter-engine"
                    rev="5.10.2"
                    conf="test-runtime->default" />

        <dependency org="org.junit.platform"
                    name="junit-platform-launcher"
                    rev="1.10.2"
                    conf="test-runtime->default" />
    </dependencies>
</ivy-module>
```

Các revision `5.10.2` và `1.10.2` là ví dụ về một bộ phiên bản cùng release train, không phải khuyến nghị dùng phiên bản mới nhất. Khi bắt đầu dự án hoặc nâng cấp, hãy chọn một release train được hỗ trợ và đồng bộ các module Jupiter/Platform tương ứng.

Ý nghĩa các configuration:

- `compile`: dependency cần để biên dịch mã ứng dụng.
- `runtime`: dependency cần khi chạy ứng dụng; kế thừa `compile` trong ví dụ này.
- `test-compile`: dependency cần để biên dịch test; kế thừa dependency compile của ứng dụng.
- `test-runtime`: dependency cần chạy test; kế thừa test compile và runtime của ứng dụng.

`junit-jupiter-api` được đưa vào `test-compile`, vì mã test sử dụng annotation và assertion của Jupiter. `junit-jupiter-engine` và `junit-platform-launcher` được đưa vào `test-runtime`, vì chúng cần thiết khi launcher thực thi test.

### 7.2. Tạo path từ cache Ivy

Sau khi resolve, tạo hai path riêng:

```xml
<ivy:cachepath pathid="test.compile.dependencies"
               conf="test-compile" />

<ivy:cachepath pathid="test.runtime.dependencies"
               conf="test-runtime" />
```

Path `test.compile.dependencies` cung cấp dependency để biên dịch test. Path `test.runtime.dependencies` cung cấp dependency cho phiên chạy test.

Khi dùng Ivy, không cần chép các JAR ra thư mục `lib` nếu task có thể tham chiếu trực tiếp path do `cachepath` tạo.

### 7.3. Nếu còn test JUnit 4

Nếu dự án có test JUnit 4, thêm API JUnit 4 và Vintage Engine:

```xml
<dependency org="junit"
            name="junit"
            rev="4.13.2"
            conf="test-compile->default" />

<dependency org="org.junit.vintage"
            name="junit-vintage-engine"
            rev="5.10.2"
            conf="test-runtime->default" />
```

JUnit 4 API cần cho bước biên dịch những lớp sử dụng `org.junit.Test`. Vintage Engine cần khi chạy các test đó qua JUnit Platform. Nếu không có test legacy, không cần khai báo hai dependency này.

## 8. Biên dịch test bằng Ant

Sau khi resolve dependency, có thể dùng `javac` để biên dịch riêng mã nguồn test. Ví dụ:

```xml
<target name="compile-tests" depends="resolve-dependencies,compile">
    <mkdir dir="${test.classes.dir}" />

    <ivy:cachepath pathid="test.compile.dependencies"
                   conf="test-compile" />

    <javac srcdir="${test.src.dir}"
           destdir="${test.classes.dir}"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath>
            <pathelement location="${classes.dir}" />
            <path refid="test.compile.dependencies" />
        </classpath>
    </javac>
</target>
```

Classpath của task `javac` gồm:

1. `${classes.dir}` để compiler tìm các lớp ứng dụng mà test cần gọi.
2. `test.compile.dependencies` để compiler tìm JUnit API và các dependency compile khác.

Nếu test sử dụng thêm thư viện hỗ trợ như thư viện tạo dữ liệu test, thư viện đó cũng phải được khai báo trong configuration `test-compile` hoặc configuration được kế thừa.

## 9. Chạy test bằng task `<junitlauncher>`

Task `<junitlauncher>` tích hợp JUnit Platform với Ant. Task này có trong các phiên bản Ant hỗ trợ JUnit Platform, bắt đầu từ Ant 1.10.3.

Ví dụ target chạy một lớp test:

```xml
<target name="test" depends="compile-tests">
    <ivy:cachepath pathid="test.runtime.dependencies"
                   conf="test-runtime" />

    <junitlauncher printSummary="true" haltOnFailure="true">
        <classpath>
            <pathelement location="${classes.dir}" />
            <pathelement location="${test.classes.dir}" />
            <path refid="test.runtime.dependencies" />
        </classpath>

        <test name="com.example.CalculatorTest">
            <listener type="legacy-xml"
                      sendSysOut="true"
                      sendSysErr="true" />
        </test>
    </junitlauncher>
</target>
```

Trong cấu hình này:

- `printSummary="true"` yêu cầu hiển thị tóm tắt kết quả.
- `haltOnFailure="true"` làm build dừng với trạng thái thất bại khi test thất bại.
- `<classpath>` cung cấp các lớp ứng dụng, lớp test và dependency cần khi thực thi.
- `<test name="...">` chỉ định lớp test cần chạy.
- Listener `legacy-xml` yêu cầu Ant tạo báo cáo theo định dạng XML tương thích với kiểu báo cáo legacy mà task hỗ trợ.

Class path ở đây phải có `junit-platform-launcher` và ít nhất một engine phù hợp với test cần chạy. Nếu chỉ có API, launcher không có engine để thực thi test.

### 9.1. Chạy nhiều lớp test

Có thể khai báo nhiều phần tử `<test>` trong cùng task:

```xml
<junitlauncher printSummary="true" haltOnFailure="true">
    <classpath>
        <pathelement location="${classes.dir}" />
        <pathelement location="${test.classes.dir}" />
        <path refid="test.runtime.dependencies" />
    </classpath>

    <test name="com.example.CalculatorTest" />
    <test name="com.example.StringUtilsTest" />
    <test name="com.example.OrderServiceTest" />
</junitlauncher>
```

Mỗi phần tử chỉ định một lớp test. Có thể chia target theo nhóm nếu dự án muốn chạy nhanh một nhóm test trong lúc phát triển và chạy toàn bộ test trong CI.

### 9.2. Ghi báo cáo XML

Listener `legacy-xml` có thể được dùng để tạo kết quả XML mà các hệ thống CI hoặc công cụ báo cáo có thể đọc:

```xml
<junitlauncher printSummary="true" haltOnFailure="true">
    <classpath>
        <pathelement location="${classes.dir}" />
        <pathelement location="${test.classes.dir}" />
        <path refid="test.runtime.dependencies" />
    </classpath>

    <test name="com.example.CalculatorTest">
        <listener type="legacy-xml"
                  sendSysOut="true"
                  sendSysErr="true" />
    </test>
</junitlauncher>
```

Để lưu báo cáo trong thư mục riêng, cấu hình output directory theo thuộc tính mà listener của phiên bản Ant đang dùng hỗ trợ, hoặc dùng cấu hình listener tương ứng trong tài liệu task. Hãy giữ báo cáo test tách khỏi thư mục class output để CI có thể thu thập chúng độc lập.

## 10. Ví dụ hoàn chỉnh: Ant, Ivy và JUnit Jupiter

Một dự án mẫu:

```text
ant-junit-demo/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── src/main/java/com/example/Calculator.java
└── src/test/java/com/example/CalculatorTest.java
```

### 10.1. Lớp ứng dụng

`src/main/java/com/example/Calculator.java`:

```java
package com.example;

public class Calculator {
    public int add(int left, int right) {
        return left + right;
    }
}
```

### 10.2. Lớp kiểm thử

`src/test/java/com/example/CalculatorTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();
        assertEquals(5, calculator.add(2, 3));
    }
}
```

Lớp test import `org.junit.jupiter.api.Test` và assertion từ Jupiter API. Nó gọi lớp `Calculator`, vì vậy thư mục class của ứng dụng cũng phải nằm trong classpath biên dịch test.

### 10.3. `ivysettings.xml`

Ví dụ dùng repository tương thích Maven:

```xml
<ivysettings>
    <settings defaultResolver="central" />
    <resolvers>
        <ibiblio name="central" m2compatible="true" />
    </resolvers>
</ivysettings>
```

### 10.4. `ivy.xml`

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="ant-junit-demo" />

    <configurations>
        <conf name="compile" />
        <conf name="runtime" extends="compile" />
        <conf name="test-compile" extends="compile" />
        <conf name="test-runtime" extends="test-compile,runtime" />
    </configurations>

    <dependencies>
        <dependency org="org.junit.jupiter"
                    name="junit-jupiter-api"
                    rev="5.10.2"
                    conf="test-compile->default" />
        <dependency org="org.junit.jupiter"
                    name="junit-jupiter-engine"
                    rev="5.10.2"
                    conf="test-runtime->default" />
        <dependency org="org.junit.platform"
                    name="junit-platform-launcher"
                    rev="1.10.2"
                    conf="test-runtime->default" />
    </dependencies>
</ivy-module>
```

### 10.5. `build.xml`

```xml
<project name="ant-junit-demo" default="test"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src/main/java" />
    <property name="test.src.dir" location="src/test/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="test.classes.dir" location="${build.dir}/test-classes" />

    <target name="resolve-dependencies">
        <ivy:settings file="ivysettings.xml" />
        <ivy:resolve file="ivy.xml" />
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${test.classes.dir}" />
    </target>

    <target name="compile" depends="resolve-dependencies,init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="compile-tests" depends="compile">
        <ivy:cachepath pathid="test.compile.dependencies"
                       conf="test-compile" />

        <javac srcdir="${test.src.dir}"
               destdir="${test.classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <pathelement location="${classes.dir}" />
                <path refid="test.compile.dependencies" />
            </classpath>
        </javac>
    </target>

    <target name="test" depends="compile-tests">
        <ivy:cachepath pathid="test.runtime.dependencies"
                       conf="test-runtime" />

        <junitlauncher printSummary="true" haltOnFailure="true">
            <classpath>
                <pathelement location="${classes.dir}" />
                <pathelement location="${test.classes.dir}" />
                <path refid="test.runtime.dependencies" />
            </classpath>

            <test name="com.example.CalculatorTest">
                <listener type="legacy-xml"
                          sendSysOut="true"
                          sendSysErr="true" />
            </test>
        </junitlauncher>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>
</project>
```

Trong ví dụ này, Ant điều phối các target theo thứ tự phụ thuộc. Ivy resolve dependency trước, `javac` biên dịch ứng dụng, `javac` tiếp theo biên dịch test với API Jupiter, rồi `junitlauncher` sử dụng Launcher và Jupiter Engine để chạy test.

Lưu ý: bản Ant phải có task JUnit Platform `<junitlauncher>` và môi trường phải có Ivy nếu buildfile dùng các task `ivy:*`. Các revision JUnit trong ví dụ cần được thay bằng một bộ phiên bản phù hợp với JDK và chính sách dependency của dự án.

## 11. Tích hợp test JUnit 4 qua Vintage Engine

Một dự án có thể đang chuyển dần từ JUnit 4 sang JUnit Jupiter. Trong giai đoạn chuyển tiếp, có thể chạy cả hai loại test trên cùng JUnit Platform nếu thêm Vintage Engine.

Ví dụ test JUnit 4:

```java
package com.example;

import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyCalculatorTest {
    @Test
    public void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Dependency bổ sung trong `ivy.xml`:

```xml
<dependency org="junit"
            name="junit"
            rev="4.13.2"
            conf="test-compile->default" />

<dependency org="org.junit.vintage"
            name="junit-vintage-engine"
            rev="5.10.2"
            conf="test-runtime->default" />
```

Khi chạy JUnit Platform Launcher, cả Jupiter Engine và Vintage Engine có thể được phát hiện trên classpath. Launcher giao test tương ứng cho engine phù hợp.

Nếu dự án chỉ chạy JUnit 4 và chưa cần JUnit Platform, task Ant truyền thống `<junit>` có thể là lựa chọn riêng. Nếu đã dùng `<junitlauncher>`, hãy bảo đảm Vintage Engine có mặt để JUnit Platform thực thi test legacy.

## 12. Phân biệt dependency compile và runtime

Đưa toàn bộ JAR vào mọi classpath có thể khiến cấu hình khó hiểu và che giấu dependency không được khai báo đúng. Tách configuration giúp xác định rõ thư viện nào cần ở từng giai đoạn.

| Giai đoạn | Những thành phần thường cần |
|---|---|
| Biên dịch ứng dụng | Lớp ứng dụng phụ thuộc và thư viện compile của ứng dụng. |
| Biên dịch test | Lớp ứng dụng, dependency compile của ứng dụng, JUnit API và thư viện test mà mã test import. |
| Chạy test | Lớp ứng dụng, lớp test, Launcher, Engine, dependency runtime của ứng dụng và test. |
| Chạy ứng dụng đóng gói | Lớp ứng dụng và dependency runtime được phân phối theo chiến lược của sản phẩm. |

Một số dependency được dùng ở cả compile và runtime. Ví dụ, JUnit Jupiter API có thể xuất hiện trong cây dependency runtime thông qua Engine, dù mã test cần nó trực tiếp ở compile. Điều quan trọng là path của từng task có đủ các lớp cần thiết và không dựa vào classpath toàn cục ngoài ý muốn.

## 13. Các lỗi thường gặp khi cấu hình launcher, engine và classpath

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy task `junitlauncher` | Ant quá cũ hoặc thiếu thư viện task `ant-junitlauncher`. | Dùng Ant từ 1.10.3 trở lên có hỗ trợ task và kiểm tra thư viện task của Ant. |
| Không tìm thấy `org.junit.jupiter.api.Test` khi biên dịch | Thiếu `junit-jupiter-api` trong test compile classpath. | Thêm API vào configuration test compile và path của `javac` test. |
| Launcher chạy nhưng không tìm thấy TestEngine | Thiếu engine hoặc engine không tương thích với Platform. | Thêm `junit-jupiter-engine` hoặc engine phù hợp vào runtime classpath. |
| Không tìm thấy `org.junit.platform.launcher` | Thiếu `junit-platform-launcher` hoặc phiên bản không phù hợp. | Thêm launcher dependency vào test runtime và đồng bộ phiên bản. |
| Test compile thành công nhưng chạy báo `NoClassDefFoundError` | Runtime classpath thiếu thư viện mà ứng dụng hoặc test cần. | Bổ sung dependency runtime và kiểm tra path truyền cho `junitlauncher`. |
| JUnit 4 test không được phát hiện | Chưa có Vintage Engine hoặc JUnit 4 API không có trong cấu hình phù hợp. | Thêm `junit-vintage-engine` runtime và `junit:junit` compile khi cần. |
| Test Jupiter không được phát hiện | Jupiter Engine thiếu, lớp test không được chọn hoặc test không có annotation phù hợp. | Kiểm tra engine, tên lớp trong `<test>` và annotation `org.junit.jupiter.api.Test`. |
| Lỗi `NoSuchMethodError` trong JUnit | Các module JUnit/Platform không cùng release train hoặc có phiên bản trùng/xung đột. | Đồng bộ phiên bản và xem dependency report. |
| Build không tìm được lớp ứng dụng trong test | Thiếu `${classes.dir}` trong classpath biên dịch hoặc runtime. | Thêm class output của ứng dụng vào cả hai classpath cần thiết. |
| Test không tìm thấy tệp dữ liệu | Tài nguyên test không được copy hoặc thư mục làm việc khác dự kiến. | Đưa test resources vào output phù hợp và dùng đường dẫn tài nguyên ổn định. |
| Máy cá nhân chạy được nhưng CI thất bại | CI thiếu JAR, JDK/Ant khác hoặc repository không truy cập được. | Dùng dependency manager, khóa phiên bản và đồng bộ môi trường build. |

### 13.1. Khi báo thiếu engine

Nếu log cho biết không có TestEngine phù hợp, hãy kiểm tra theo thứ tự:

1. Test viết bằng Jupiter, JUnit 4 hay một framework khác?
2. Engine tương ứng đã được khai báo chưa?
3. Engine có nằm trên classpath mà `junitlauncher` sử dụng không?
4. Phiên bản Engine có tương thích với JUnit Platform Launcher không?
5. Có dependency conflict khiến một phiên bản khác được chọn không?

Chỉ có API không đủ để chạy test. Ví dụ, `junit-jupiter-api` giúp compiler hiểu `@Test`, nhưng `junit-jupiter-engine` mới là thành phần thực thi test Jupiter.

### 13.2. Khi test compile được nhưng runtime thất bại

Điều này thường cho thấy classpath biên dịch và classpath chạy không giống nhau. Hãy kiểm tra:

- Lớp ứng dụng có trong runtime path không?
- Dependency runtime của ứng dụng có được resolve không?
- Engine và Launcher có trong path của task `<junitlauncher>` không?
- Tài nguyên test có được đưa vào thư mục output không?
- Có JAR cũ hoặc trùng phiên bản được nạp trước JAR mong muốn không?

Đừng mặc định classpath của task `javac` được tự động dùng lại cho `junitlauncher`. Mỗi task cần được cấu hình rõ ràng.

## 14. Sơ đồ luồng build kiểm thử

Một target test điển hình có thể được mô tả như sau:

```text
ant test
   |
   v
resolve-dependencies
   |
   +-- resolve API, launcher, engine và thư viện ứng dụng
   |
   v
compile
   |
   +-- javac mã nguồn ứng dụng
   |
   v
compile-tests
   |
   +-- tạo test compile classpath
   +-- javac mã nguồn test
   |
   v
test
   |
   +-- tạo test runtime classpath
   +-- junitlauncher gọi JUnit Platform Launcher
   +-- Launcher phát hiện Jupiter/Vintage Engine
   +-- Engine thực thi test
   +-- listener ghi kết quả
   |
   v
Build thành công hoặc thất bại theo kết quả test
```

Sơ đồ nhấn mạnh rằng dependency phải sẵn sàng trước giai đoạn cần chúng. API phục vụ compile, Launcher và Engine phục vụ runtime, còn các lớp ứng dụng và test phải có mặt ở đúng classpath.

## 15. Bài thực hành

Tạo một dự án Ant nhỏ với JUnit Jupiter:

```text
junit-ant-lab/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── src/main/java/com/example/Calculator.java
└── src/test/java/com/example/CalculatorTest.java
```

Thực hiện các bước:

1. Kiểm tra phiên bản Ant và bảo đảm task `<junitlauncher>` có sẵn.
2. Cấu hình Ivy hoặc chuẩn bị JAR tương thích của JUnit Platform.
3. Khai báo `junit-jupiter-api` cho test compile.
4. Khai báo `junit-jupiter-engine` và `junit-platform-launcher` cho test runtime.
5. Tạo path riêng cho compile test và runtime test.
6. Biên dịch lớp ứng dụng vào `build/classes`.
7. Biên dịch lớp test vào `build/test-classes`, với classpath gồm lớp ứng dụng và Jupiter API.
8. Chạy `CalculatorTest` bằng `<junitlauncher>` với classpath gồm lớp ứng dụng, lớp test, Launcher và Engine.
9. Bật summary và listener báo cáo để xem kết quả.
10. Cố ý bỏ `junit-jupiter-engine` khỏi runtime path rồi quan sát thông báo lỗi; khôi phục dependency và chạy lại.

### Câu hỏi tự kiểm tra

1. JUnit Platform Launcher thực hiện nhiệm vụ gì?
2. Vì sao `junit-jupiter-api` không thể thay thế `junit-jupiter-engine`?
3. Khi nào cần thêm Vintage Engine?
4. `ant-junitlauncher.jar` khác `junit-platform-launcher.jar` như thế nào?
5. Vì sao lớp ứng dụng cần nằm trên classpath biên dịch test?
6. Những thư viện nào cần có trong classpath chạy test Jupiter?
7. Vì sao không nên cho rằng classpath của `javac` tự động được dùng bởi `junitlauncher`?
8. Dependency compile và runtime khác nhau ở mục đích nào?
9. Nếu test compile thành công nhưng báo thiếu engine khi chạy, bạn sẽ kiểm tra những gì?
10. Vì sao nên đồng bộ phiên bản của các module JUnit Jupiter và JUnit Platform?

### Đáp án gợi ý

- Launcher khám phá, chọn và điều phối test thông qua các Test Engine.
- API cung cấp annotation/assertion cho mã test; Engine mới thực thi test Jupiter.
- Khi cần chạy test JUnit 3 hoặc JUnit 4 qua JUnit Platform.
- `ant-junitlauncher.jar` cung cấp task tích hợp cho Ant; `junit-platform-launcher.jar` cung cấp Launcher API của JUnit Platform.
- Vì test có thể tham chiếu các lớp ứng dụng đã biên dịch.
- Tối thiểu cần lớp ứng dụng, lớp test, JUnit Platform Launcher, engine Jupiter và các dependency runtime liên quan.
- Mỗi task Ant có classpath riêng; cần cấu hình path rõ ràng cho task chạy test.
- Compile classpath phục vụ biên dịch mã nguồn; runtime classpath phục vụ nạp và thực thi lớp khi chạy.
- Kiểm tra engine tương ứng, runtime path, phiên bản engine/launcher và dependency conflict.
- Các module thuộc cùng release train được phát triển để tương thích; trộn phiên bản tùy ý có thể gây lỗi liên kết như `NoSuchMethodError`.

## Kết luận

Khi chạy kiểm thử JUnit Platform từ Ant, hãy phân biệt API, Launcher và Test Engine. JUnit API giúp biên dịch mã test; Launcher điều phối phiên chạy; Engine như Jupiter hoặc Vintage thực thi loại test tương ứng. Task Ant `<junitlauncher>` là phần tích hợp với Ant và cần thư viện task của Ant, trong khi classpath test vẫn phải có JUnit Platform Launcher, Engine, lớp ứng dụng, lớp test và các dependency runtime. Tách rõ test compile classpath và test runtime classpath giúp build dễ hiểu, phát hiện sớm dependency bị thiếu và chạy nhất quán trên máy phát triển lẫn CI.

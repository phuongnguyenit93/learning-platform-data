# Tích hợp Ivy để phân giải và chuẩn bị thư viện kiểm thử trong Apache Ant

Trong một dự án dùng **Apache Ant**, task `<javac>` có thể biên dịch mã Java mà không cần một hệ thống quản lý dependency riêng. Tuy nhiên, ngay khi thêm kiểm thử tự động, dự án thường cần các thư viện bên ngoài như JUnit, Hamcrest, Mockito hoặc framework hỗ trợ test. Nếu tải từng JAR thủ công, chép vào `lib/` rồi viết classpath cố định, người bảo trì phải tự theo dõi phiên bản, dependency bắc cầu và việc đồng bộ giữa máy cá nhân với CI.

**Apache Ivy** bổ sung khả năng **phân giải dependency (resolve)** cho Ant: mô tả thư viện cần dùng, tìm artifact từ repository được cấu hình, xử lý quan hệ phụ thuộc và chuẩn bị classpath để biên dịch/chạy test. Bài thực hành này đi từ một dự án Java nhỏ đến lệnh `ant ci-test` hoàn chỉnh, đồng thời giải thích cách tách thư viện kiểm thử khỏi sản phẩm ứng dụng.

Mục tiêu sau bài học:

- Phân biệt vai trò của Ant, Ivy, repository và các JAR kiểm thử.
- Khai báo cấu hình `test` trong `ivy.xml`, chọn repository trong `ivysettings.xml`.
- Nạp các task Ivy vào Ant, phân giải JUnit và dependency bắc cầu rồi tạo test classpath.
- Biên dịch mã chính và mã kiểm thử với hai classpath có phạm vi rõ ràng.
- Thực thi JUnit, để lỗi phân giải/biên dịch/test làm lệnh build thất bại.
- Nhận diện khác biệt giữa cache Ivy và thư mục JAR được sao chép bằng `retrieve`.
- Áp dụng các nguyên tắc về phiên bản, nguồn artifact, môi trường CI và xử lý sự cố.

## 1. Ant và Ivy chịu trách nhiệm khác nhau

Ant là công cụ tổ chức build theo **project, target, task và dependency giữa target**. Ant biết gọi `<javac>`, `<java>`, `<jar>` và các task khác; Ant không tự biết JUnit cần những thư viện gì từ một tọa độ Maven.

Ivy là thành phần mở rộng, cung cấp task và mô hình dependency riêng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `build.xml` của Ant | Điều phối thứ tự: tải thư viện, compile source, compile test, chạy test, đóng gói |
| `ivy.xml` | Mô tả module hiện tại, các configuration và dependency cần phân giải |
| `ivysettings.xml` | Chọn resolver, repository, cấu hình cache và chính sách tìm artifact |
| Repository | Chứa metadata module như POM/Ivy descriptor và file artifact JAR |
| Cache của Ivy | Lưu metadata/artifact đã tải để tránh tải lại và hỗ trợ các lần resolve sau |
| `ivy:cachepath` | Tạo một Ant path từ artifact đã resolve để dùng làm classpath |
| `ivy:retrieve` | Sao chép artifact đã resolve vào một thư mục có tên theo pattern |
| `javac` / `java` | Sử dụng classpath để biên dịch mã kiểm thử và chạy test |

Dòng dữ liệu cơ bản:

```text
             ivysettings.xml                ivy.xml
                |                              |
                | resolver                     | dependency + conf
                +--------------+---------------+
                               |
                               v
                         ivy:resolve
                               |
                               v
                  Repository (Maven/Ivy)
                               |
                               v
                    Ivy cache (JAR + metadata)
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
              ivy:cachepath           ivy:retrieve
                   |                       |
                   v                       v
              Ant path ID          Thư mục JAR vật lý
                   |
                   v
           javac test + JUnitCore
```

**Hai loại dependency không nên nhầm:**

1. **Dependency của bản thân Ivy:** Ant phải có JAR Ivy để nhận ra task `ivy:resolve`, `ivy:cachepath`. Đây là dependency của *hệ thống build*.
2. **Dependency của mã kiểm thử:** chẳng hạn `junit:junit:4.13.2`. Ivy phân giải chúng để `<javac>` và test runner có thể sử dụng. Đây là dependency của *dự án đang build*.

Không thể trông chờ Ivy tự tải JAR của chính nó bằng `ivy:resolve` khi Ant chưa nạp được task Ivy.

## 2. Chuẩn bị môi trường trước khi khai báo dependency

Cần có:

- Một JDK được cài và Ant chạy được bằng `ant -version`.
- JAR Apache Ivy phù hợp với bản Ant/JDK mà dự án sử dụng.
- Quyền đọc repository đã chọn, hoặc một cache/mirror có các artifact cần thiết.
- Hai khu vực nguồn tách biệt: `src/main/java` và `src/test/java`.

Các cách nạp Ivy thông dụng:

| Cách | Cách Ant nhìn thấy Ivy | Nên dùng khi |
| --- | --- | --- |
| Chép Ivy JAR vào `ANT_HOME/lib` | Các task có thể nạp từ classloader Ant | Máy/build image do nhóm quản lý, cấu hình Ant dùng chung |
| Chép Ivy JAR vào `~/.ant/lib` | Ant nạp các JAR của người dùng | Máy cá nhân; lưu ý mỗi người có thể dùng phiên bản khác |
| Gọi `ant -lib /path/to/ivy.jar ...` | Bổ sung Ivy JAR cho lần chạy cụ thể | CI hoặc dự án muốn chọn Ivy version tường minh |
| `<taskdef ... classpath="...">` | Nạp task từ một JAR tại đường dẫn cụ thể | Cấu hình dự án đóng gói/chỉ định đường dẫn JAR riêng |

Để dễ tái hiện, phần thực hành giả sử JAR Ivy có tên `tools/ivy-2.5.3.jar` (tên phiên bản **chỉ minh họa việc chốt phiên bản; hãy chọn bản đã kiểm tra tương thích**) và được cung cấp từ một nguồn chính thức hoặc mirror tin cậy. Có thể chạy Ant với `-lib`:

```bash
ant -lib tools/ivy-2.5.3.jar ci-test
```

Trên PowerShell:

```powershell
ant -lib 'tools/ivy-2.5.3.jar' ci-test
```

Có thể tải và lưu trữ Ivy JAR theo chính sách toolchain của tổ chức. Không nên yêu cầu một script mới nhận từ nguồn lạ tải `latest` rồi thực thi ngay mà không xác minh phiên bản và tính toàn vẹn.

**Điểm kiểm tra:** `ant -version` kiểm tra Ant, **không chứng minh Ivy đã được nạp**. Ivy sẽ được đăng ký bằng `<taskdef>` trong `build.xml`. Nếu chưa tìm được JAR Ivy, Ant sẽ báo lỗi nạp resource/task trước khi phân giải JUnit.

## 3. Cấu trúc dự án thực hành

Tạo các file:

```text
ant-ivy-test-demo/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── tools/
│   └── ivy-2.5.3.jar
├── src/
│   ├── main/
│   │   └── java/
│   │       └── example/
│   │           └── Calculator.java
│   └── test/
│       └── java/
│           └── example/
│               └── CalculatorTest.java
├── build/                   # Ant tạo khi compile/test
└── dist/                    # Ant tạo khi đóng gói
```

Hai thư mục `build/` và `dist/` là **đầu ra sinh tự động**. Không cần tạo trước; cũng không nên đưa chúng thành nguồn dependency lâu dài. Cache Ivy mặc định thường ở khu vực cache của người dùng (ví dụ `~/.ivy2/cache`), **nằm ngoài `build/`**. Vì vậy `ant clean` thông thường xóa output dự án nhưng không xóa toàn bộ cache Ivy.

**File `src/main/java/example/Calculator.java`:**

```java
package example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
```

**File `src/test/java/example/CalculatorTest.java`:**

```java
package example;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class CalculatorTest {

    @Test
    public void addsTwoIntegers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    public void handlesNegativeNumbers() {
        assertEquals(-1, Calculator.add(2, -3));
    }
}
```

Mã chính `Calculator` không phụ thuộc JUnit. Chỉ source trong `src/test/java` sử dụng `org.junit`, nên thư viện JUnit chỉ cần nằm trên **classpath biên dịch và thực thi test**, không cần thêm vào bản JAR ứng dụng.

## 4. Khai báo dependency với ivy.xml

File `ivy.xml` là mô tả dependency của module. Với ví dụ này:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="example"
          module="ant-ivy-test-demo"
          revision="1.0.0"/>

    <configurations>
        <conf name="compile" visibility="public"/>
        <conf name="test"
              visibility="public"
              extends="compile"/>
    </configurations>

    <dependencies>
        <dependency org="junit"
                    name="junit"
                    rev="4.13.2"
                    conf="test->default"
                    transitive="true"/>
    </dependencies>
</ivy-module>
```

### 4.1. Đọc các tọa độ Ivy

Một dependency được nhận diện theo các thành phần:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `org` | `junit` | Tổ chức (tương ứng `groupId` trong Maven) |
| `name` | `junit` | Tên module/artifact (tương ứng `artifactId`) |
| `rev` | `4.13.2` | Revision/phiên bản cần dùng |
| `conf` | `test->default` | Mapping configuration từ module của ta sang module phụ thuộc |
| `transitive` | `true` | Cho phép Ivy xử lý dependency bắc cầu từ metadata có sẵn |

Cặp `junit:junit:4.13.2` được phát hành lên Maven Central. POM của JUnit 4.13.2 khai báo phụ thuộc Hamcrest cho các chức năng assertion/matcher. Khi dùng resolver đọc POM và cho phép dependency bắc cầu, Ivy có thể phân giải thêm artifact phù hợp thay vì người dùng phải đoán tất cả JAR cần tải.

### 4.2. Configuration compile và test

Configuration trong Ivy là một **nhóm phụ thuộc theo mục đích**:

- `compile`: thư viện cần cho mã sản phẩm khi biên dịch.
- `test`: thư viện cần cho kiểm thử; khai báo `extends="compile"` để kế thừa dependency được phân vào `compile` khi có.

Trong ví dụ, JUnit nằm **chỉ ở configuration `test`**:

```xml
<dependency org="junit"
            name="junit"
            rev="4.13.2"
            conf="test->default"/>
```

Dấu `->` là **configuration mapping**: phía trái là configuration thuộc module đang build, phía phải là configuration của module bên ngoài. `default` thường là configuration do Ivy cung cấp hoặc diễn dịch từ metadata Maven/POM. Khi tích hợp một thư viện có mô hình configuration đặc biệt, cần xem descriptor thực tế để chọn mapping đúng, không áp dụng `default` một cách máy móc.

Một bảng mô tả ý nghĩa:

| Resolve configuration | Có JUnit trực tiếp trong ví dụ? | Dùng cho |
| --- | --- | --- |
| `compile` | Không | Biên dịch mã trong `src/main/java` |
| `test` | Có | Biên dịch và chạy `src/test/java` |

Nếu sau này sản phẩm phụ thuộc một thư viện runtime riêng, có thể khai báo dependency vào `compile` hoặc tạo thêm `runtime` phù hợp với dự án. Đừng đưa toàn bộ test dependency vào mọi configuration chỉ vì ban đầu chưa cần phân biệt.

### 4.3. Revision cố định và revision động

`rev="4.13.2"` là một revision được chỉ định cụ thể. Các cách khai báo động như `latest.release` hoặc một dải phiên bản có thể khiến cùng source resolve sang thư viện khác khi repository được cập nhật.

Với CI/release, nên chốt:

1. Phiên bản dependency trực tiếp.
2. Quy tắc phân giải dependency bắc cầu và xung đột phiên bản.
3. Repository/mirror và chính sách tính toàn vẹn.
4. Phiên bản Ivy, Ant, JDK.

**Chốt mỗi dependency trực tiếp không tự đóng băng toàn bộ cây dependency.** Nếu các thư viện bắc cầu khai báo revision động hoặc repository cho phép thay nội dung artifact, kết quả vẫn có thể khác. Dự án cần quy trình kiểm soát graph/lock hoặc danh sách version đã xác nhận tương ứng với mức tái lập yêu cầu.

## 5. Cấu hình repository trong ivysettings.xml

Ivy không thể resolve module nếu chưa biết **tìm ở đâu**. Với các artifact từ Maven Central, có thể dùng resolver `ibiblio` theo bố cục Maven:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivysettings>
    <settings defaultResolver="central"/>

    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 usepoms="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>
</ivysettings>
```

Ý nghĩa:

- `defaultResolver="central"` chọn resolver mặc định.
- `ibiblio` là resolver Ivy hỗ trợ cách tra cứu artifact kiểu repository Maven.
- `m2compatible="true"` làm tọa độ `org/name/rev` tương ứng bố cục `groupId/artifactId/version`.
- `usepoms="true"` cho phép Ivy đọc POM để biết thông tin dependency.
- `root` là địa chỉ repository. Ví dụ dùng HTTPS Maven Central.

Với môi trường doanh nghiệp, nhiều hệ thống dùng Artifactory/Nexus hoặc repository mirror nội bộ. Khi đó có thể thay `root` bằng endpoint chính thức do nhóm quản lý build cung cấp, kèm cơ chế xác thực riêng phù hợp CI.

**Không đặt token truy cập repository dưới dạng chuỗi rõ trong `ivysettings.xml` được commit.** Dùng cơ chế credential của pipeline, property an toàn hoặc hạ tầng repository; bảo đảm log không in mật khẩu. Nếu có proxy, chứng chỉ nội bộ hoặc đường truyền bị chặn, cần cấu hình mạng của JVM và repository trước khi kết luận rằng dependency không tồn tại.

### 5.1. Một nguồn resolver hay nhiều nguồn?

Một chain resolver có thể thử repository nội bộ trước rồi đến nguồn công khai. Điều này tiện nhưng làm thay đổi nguồn artifact khi mirror thiếu dữ liệu. Với build cần kiểm soát chặt, cần quy định:

- Repository nào là **nguồn chính** của từng nhóm dependency.
- Có cho phép fallback sang mạng công khai hay không.
- Khi artifact thiếu trên mirror, build **fail** hay đổi nguồn.
- Cách kiểm tra tính toàn vẹn và khả năng truy vết nguồn của artifact.

Resolver quyết định **nguồn dữ liệu và đường phân giải**, vì vậy nó là một phần của hợp đồng build, không phải chỉ là một tùy chọn hiệu năng.

## 6. Viết build.xml: nạp Ivy, resolve, tạo classpath, biên dịch và chạy test

Ví dụ dưới gọi JUnit 4 qua `org.junit.runner.JUnitCore` trong JVM con. Cách này tránh yêu cầu phải có task Ant `<junit>` thuộc bộ thư viện optional Ant trong classpath của chính Ant; thư viện JUnit chỉ cần nằm trong test classpath do Ivy cung cấp.

**File `build.xml` hoàn chỉnh:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ivy-test-demo"
         default="ci-test"
         basedir="."
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <!-- ivy-*.jar được nạp vào Ant qua tham số -lib. -->
    <taskdef resource="org/apache/ivy/ant/antlib.xml"
             uri="antlib:org.apache.ivy.ant"/>

    <property name="src.main" value="src/main/java"/>
    <property name="src.test" value="src/test/java"/>

    <property name="build.dir" value="build"/>
    <property name="classes.main"
              value="${build.dir}/classes/main"/>
    <property name="classes.test"
              value="${build.dir}/classes/test"/>
    <property name="dist.dir" value="dist"/>

    <!-- Chỉ xóa output do dự án này sinh. -->
    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.main}"/>
        <mkdir dir="${classes.test}"/>
    </target>

    <!-- Nạp settings của dự án trước mỗi resolve. -->
    <target name="resolve-test" depends="prepare">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml"
                     conf="test"
                     transitive="true"/>

        <!-- Kết quả resolve thành một Ant path.
             Chưa cần copy JAR ra thư mục lib/. -->
        <ivy:cachepath pathid="ivy.test.path"
                       conf="test"/>
    </target>

    <!-- Mã sản phẩm không cần thư viện JUnit. -->
    <target name="compile-main" depends="prepare">
        <javac srcdir="${src.main}"
               destdir="${classes.main}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false"
               failonerror="true"/>
    </target>

    <!-- Test cần thấy class sản phẩm và dependency của Ivy. -->
    <target name="compile-test"
            depends="compile-main,resolve-test">

        <javac srcdir="${src.test}"
               destdir="${classes.test}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false"
               failonerror="true">
            <classpath>
                <pathelement location="${classes.main}"/>
                <path refid="ivy.test.path"/>
            </classpath>
        </javac>
    </target>

    <!-- Chạy chính class test đã biên dịch. -->
    <target name="test" depends="compile-test">
        <java classname="org.junit.runner.JUnitCore"
              fork="true"
              failonerror="true"
              output="${build.dir}/junit-console.txt">
            <classpath>
                <pathelement location="${classes.main}"/>
                <pathelement location="${classes.test}"/>
                <path refid="ivy.test.path"/>
            </classpath>
            <arg value="example.CalculatorTest"/>
        </java>

        <echo message="JUnit đã hoàn thành; xem build/junit-console.txt"/>
    </target>

    <!-- Package chỉ lấy main classes; không đóng test classes/JUnit. -->
    <target name="package" depends="compile-main">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/calculator.jar"
             basedir="${classes.main}"
             duplicate="fail"/>
    </target>

    <!-- CI bắt đầu từ output sạch và fail nếu test fail. -->
    <target name="ci-test" depends="clean,test"/>

    <!-- Chỉ đóng gói sau khi kiểm thử thành công. -->
    <target name="release" depends="ci-test,package"/>
</project>
```

### 6.1. Ant xác định thứ tự như thế nào?

Lệnh:

```bash
ant -lib tools/ivy-2.5.3.jar ci-test
```

Đi qua đồ thị target:

```text
                   ci-test
                  /       \
               clean      test
                           |
                      compile-test
                       /        \
               compile-main   resolve-test
                     |             |
                  prepare       prepare
```

Các target có chung dependency như `prepare` chỉ được Ant thực hiện **một lần trong một invocation**. Khi gọi `ci-test`, `clean` được xử lý trước `test` theo thứ tự trong `depends`. Sau đó Ant chuẩn bị thư mục, resolve dependency, compile và chạy test.

Khi gọi `release`, dependency `ci-test` hoàn thành trước `package`; tức là **test phải đạt trước khi tạo `dist/calculator.jar`**. Về mặt chức năng, `compile-main` không thêm JUnit vào sản phẩm. Ivy chỉ tham gia classpath ở bước test.

### 6.2. Vì sao cần taskdef đầu file?

```xml
<taskdef resource="org/apache/ivy/ant/antlib.xml"
         uri="antlib:org.apache.ivy.ant"/>
```

`xmlns:ivy="antlib:org.apache.ivy.ant"` gắn tiền tố `ivy` với namespace Antlib; `taskdef` tìm định nghĩa task Ivy trong JAR đã được Ant nạp. Khi Ant chưa có Ivy JAR, các thẻ `ivy:settings`, `ivy:resolve`, `ivy:cachepath` sẽ không thể hoạt động.

Lỗi nạp Ivy khác với lỗi JUnit chưa resolve:

- Ivy chưa nạp: lỗi tại `taskdef`/namespace Antlib trước khi chạy resolve.
- Ivy đã nạp nhưng JUnit không tải được: lỗi **resolve** và có log về resolver, URL, revision hoặc metadata.
- JUnit đã resolve nhưng không có trên test classpath: lỗi compile hoặc chạy `JUnitCore`.

Tách ba nhóm giúp chẩn đoán đúng tầng.

### 6.3. Mối quan hệ giữa resolve và cachepath

`<ivy:resolve>` đọc `ivy.xml`, tìm các revision phù hợp, truy xuất metadata và artifact theo settings, rồi lưu kết quả giải quyết dependency trong Ivy.

`<ivy:cachepath pathid="ivy.test.path" conf="test"/>` tạo một **Ant Path**. Các thư viện trong path trỏ tới artifact được Ivy lưu trong cache, ví dụ JAR JUnit và JAR bắc cầu.

Nó không tự động biến JAR thành file `lib/junit.jar` trong project. Ant dùng path theo ID:

```xml
<classpath>
    <pathelement location="${classes.main}"/>
    <path refid="ivy.test.path"/>
</classpath>
```

`pathid` phải trùng tên giữa nơi tạo và nơi dùng. Cần dùng `<path refid="..."/>` trong nested classpath, không nhầm `refid` với tên file trên ổ đĩa.

### 6.4. Vì sao compile-main không resolve Ivy test?

`Calculator.java` chỉ dùng JDK API. Đưa JUnit vào classpath compile chính có thể khiến source sản phẩm vô tình phụ thuộc API kiểm thử và che lỗi phân tách module. Build mẫu chỉ đưa test JAR vào `compile-test` và `test`.

Trong dự án thực tế, nếu mã sản phẩm có thư viện ngoài riêng, cần thêm resolve/path cho configuration `compile`. Nhưng việc đó là phần mở rộng có chủ đích; không nên tái sử dụng toàn bộ test classpath để biên dịch production chỉ vì thuận tiện.

### 6.5. Vì sao dùng JUnitCore?

JUnit 4 có runner `org.junit.runner.JUnitCore`. Với test đơn giản:

```bash
java -cp "build/classes/main:build/classes/test:<junit-and-hamcrest-jars>" \
     org.junit.runner.JUnitCore example.CalculatorTest
```

Cú pháp classpath `:` ở trên minh họa Unix; Windows dùng dấu `;` và đường dẫn khác. Ant `<classpath>` giải quyết khác biệt này khi thực thi trên từng hệ điều hành.

`<java classname="org.junit.runner.JUnitCore" fork="true" failonerror="true">` chạy JUnit trong JVM con. Khi JUnit báo test thất bại với exit code khác 0, Ant dừng thay vì tiếp tục sang `package`.

Output được lưu vào `build/junit-console.txt` để CI có thể thu thập. Nếu muốn xem console ngay, có thể dùng `outputproperty` hoặc bỏ thuộc tính `output` và để output đi vào log Ant; lựa chọn tùy yêu cầu reporting.

## 7. Chạy bài thực hành từ đầu đến cuối

### 7.1. Lệnh nền tảng

Từ thư mục dự án:

```bash
java -version
ant -version
ant -lib tools/ivy-2.5.3.jar ci-test
```

Ở lần đầu, Ivy có thể kết nối Maven Central, tải POM/JAR và lưu vào cache. Lần sau, các artifact đã có có thể được tái sử dụng tùy cấu hình và thời hạn kiểm tra metadata của Ivy.

Các bước có thể quan sát được trong log:

```text
clean:
prepare:
compile-main:
resolve-test:
    [ivy:resolve] ...
    [ivy:cachepath] ...
compile-test:
test:
    [java] ...
BUILD SUCCESSFUL
```

Đây là **dạng log minh họa**, không phải stdout cố định của mọi phiên bản Ant/Ivy. Kết quả của JUnit nằm trong `build/junit-console.txt` vì file `build.xml` đã cấu hình thuộc tính `output`.

### 7.2. Xem đầu ra và chạy release

Khi test đạt:

```bash
ant -lib tools/ivy-2.5.3.jar release
```

Lệnh `release` thực hiện clean + test rồi package. Đầu ra dự kiến:

```text
build/
├── classes/
│   ├── main/example/Calculator.class
│   └── test/example/CalculatorTest.class
└── junit-console.txt

dist/
└── calculator.jar
```

Xem các entry JAR:

```bash
jar tf dist/calculator.jar
```

Bản JAR chỉ nên chứa `example/Calculator.class` cùng metadata ZIP/JAR thông thường; **không nên chứa `example/CalculatorTest.class` hoặc `org/junit/...`** bởi target `package` dùng `basedir="${classes.main}"`. Điều này minh họa tác dụng của việc tách configuration và đường dẫn output.

### 7.3. Làm test thất bại có chủ đích

Trong bản sao dùng để luyện tập, đổi một assertion:

```java
@Test
public void addsTwoIntegers() {
    assertEquals(99, Calculator.add(2, 3));
}
```

Chạy:

```bash
ant -lib tools/ivy-2.5.3.jar ci-test
```

JUnit phải trả kết quả thất bại. Vì Ant dùng `failonerror="true"`, lệnh `ci-test` phải kết thúc khác 0. Nếu gọi `release` với test lỗi, target `package` không nên chạy; `clean` đã xóa `dist/` ở đầu invocation.

Ca này xác nhận **JUnit thực sự được chạy và lỗi test chặn phát hành**, thay vì chỉ kiểm tra JUnit có mặt trên classpath.

### 7.4. Làm resolve thất bại có chủ đích

Thay revision JUnit trong một bản sao của `ivy.xml`:

```xml
<dependency org="junit"
            name="junit"
            rev="9999.0-invalid"
            conf="test->default"/>
```

Nếu repository không có revision đó, `ivy:resolve` phải báo không thể giải quyết dependency và Ant không đi tiếp tới biên dịch test. Khôi phục `4.13.2` sau khi quan sát.

Lỗi resolve do **không tồn tại revision** khác với lỗi do **mất mạng hoặc cấu hình repository sai**. Xem phần log resolver trước khi chẩn đoán.

## 8. Lúc nào dùng ivy:retrieve thay cho ivy:cachepath?

`ivy:cachepath` đủ cho nhiều dự án: JAR được dùng trực tiếp từ cache, không cần sao chép vào workspace. Nhưng có dự án cần một **thư mục vật lý chứa tất cả test JAR** để chuyển cho script ngoài, đóng gói bộ kiểm thử, tạo classpath từ một thư mục hoặc chuẩn bị môi trường không chạy Ivy ở bước sau.

Khi đó, dùng `ivy:retrieve`:

```xml
<target name="retrieve-test-libs" depends="resolve-test">
    <ivy:retrieve conf="test"
                  pattern="${build.dir}/test-libs/[artifact]-[revision].[ext]"
                  sync="true"/>
</target>
```

Sau khi resolve, Ivy chép artifact phù hợp vào đường dẫn theo pattern:

```text
build/test-libs/
├── junit-4.13.2.jar
└── hamcrest-core-1.3.jar
```

Đây là kết quả **thường gặp** của graph JUnit 4.13.2 trên Maven Central. Số lượng và tên artifact thực tế phụ thuộc metadata/cấu hình và kết quả phân giải, nên kiểm tra log Ivy khi dùng một repository khác.

Pattern:

| Token | Ý nghĩa |
| --- | --- |
| `[artifact]` | Tên artifact |
| `[revision]` | Phiên bản được resolve |
| `[ext]` | Đuôi file như `jar` |
| `[conf]` | Tên configuration khi pattern cần tách nhiều nhóm |
| `[organisation]` | Organisation của module, hữu ích khi tránh trùng tên artifact |

**Bẫy quan trọng:** Hai module khác organisation có thể cùng `[artifact]` và `[revision]`. Nếu tất cả được copy vào một thư mục chung với pattern quá ngắn, có nguy cơ đè file hoặc va chạm tên. Với dependency graph lớn, cân nhắc thêm `[organisation]` hoặc cấu trúc thư mục theo module.

`sync="true"` giúp loại bỏ artifact không còn khớp tập retrieve trong vùng pattern mà Ivy quản lý. Hãy dùng **thư mục output riêng do build sở hữu**; không hướng sync tới thư mục chứa JAR được bổ sung thủ công hoặc dữ liệu khác.

Có thể dùng thư mục đã retrieve làm classpath:

```xml
<path id="test.libs.from.dir">
    <fileset dir="${build.dir}/test-libs">
        <include name="*.jar"/>
    </fileset>
</path>
```

Nhưng không cần vừa `cachepath` vừa `retrieve` cho cùng một mục đích nếu dự án chỉ cần một đường classpath. Chọn một phương án chủ đạo:

- **`cachepath`:** ít bản sao, phù hợp Ant chạy test ngay trong project.
- **`retrieve`:** cần thư mục JAR cụ thể để một công cụ hoặc pipeline khác sử dụng.

Một số dự án giữ cả hai vì nhu cầu khác nhau; khi đó phải nêu rõ đâu là classpath dùng cho compile/test và đâu là output phân phối.

## 9. Cơ chế cache Ivy và ảnh hưởng tới CI

Cache giúp tải dependency nhanh hơn nhưng cũng có thể che việc cấu hình repository thiếu hoặc tạo sự khác biệt giữa máy mới và máy đã build nhiều lần.

### 9.1. Ba môi trường cần phân biệt

| Tình huống | Điều dễ xảy ra | Hướng kiểm soát |
| --- | --- | --- |
| Máy dev đã có cache | Resolve nhanh, đôi khi vẫn thành công khi mạng gián đoạn | Không coi cache cục bộ là bằng chứng mọi máy sẽ resolve được |
| Runner CI mới | Phải tải metadata và artifact từ repository | Đảm bảo HTTPS/proxy/chứng chỉ và version đã chốt |
| Runner CI có cache được khôi phục | Nhanh hơn, nhưng có thể chứa artifact từ run khác | Cache theo toolchain/chính sách, không cho nguồn thiếu tin cậy ghi đè |

`ant clean` trong ví dụ **không xóa cache Ivy**. Đó là hành vi mong muốn: clean build nghĩa là xóa output trung gian của project, còn cache dependency có thể được quản lý riêng. Nếu muốn chứng minh một dự án không phụ thuộc cache của máy cá nhân, hãy chạy thêm trên runner/checkout sạch với chính sách cache rõ ràng.

### 9.2. Phân giải dependency không đồng nghĩa tải artifact tùy ý đã an toàn

Dependency từ repository là **đầu vào bên ngoài**; nếu thư viện được dùng trong test, class của nó có thể chạy trong JVM của test runner. Cần cân nhắc:

- Nguồn repository và quyền cập nhật artifact.
- Phiên bản dependency trực tiếp và bắc cầu.
- Chính sách kiểm tra checksum, chữ ký hoặc proxy đáng tin.
- Việc cho phép revision động/SNAPSHOT.
- Quyền mà job test được cấp (file, mạng, secrets).

Không nên cấp credential phát hành cho một bước test dùng code/dependency chưa được phê duyệt. Nguồn Maven Central là một nguồn phân phối phổ biến, nhưng việc resolve thành công **không phải bằng chứng thư viện an toàn hoặc phù hợp chính sách của dự án**.

### 9.3. Có cần commit thư mục lib không?

Nếu dùng Ivy, thông thường **không cần commit bản sao mọi JAR do Ivy retrieve**. Có thể commit những file mô tả dependency và settings, rồi để CI tự resolve/retrieve.

Ngoại lệ có thể là dự án hoạt động trong mạng hoàn toàn offline hoặc có chính sách lưu trữ artifact nội bộ. Khi đó cần mô tả rõ **nguồn tin cậy của JAR, digest, phiên bản và cơ chế cập nhật**. Tránh vừa commit JAR thủ công vào `lib/` vừa để Ivy retrieve đè lên đó mà không có quy tắc sở hữu file.

## 10. Tăng khả năng tái lập của test build

Một bài thực hành có thể chạy thành công mà vẫn thiếu tính tái lập lâu dài. Để cùng revision chạy lại với cùng kết quả về dependency, cần kiểm soát những điểm sau.

### 10.1. Không dùng version động cho bước phát hành

Không dùng `rev="latest.integration"` hoặc một pattern tự động lấy bản mới nhất cho test của bản phát hành nếu yêu cầu chạy lại được. Khi repository được cập nhật, test có thể dùng thư viện khác mà mã nguồn không đổi.

Ưu tiên version cụ thể và quy trình nâng cấp dependency riêng. Khi nâng phiên bản, review thay đổi API, cây dependency và hành vi test.

### 10.2. Kiểm soát dependency bắc cầu

Một direct dependency có thể kéo theo nhiều thư viện khác. Ivy có cơ chế **conflict management** và các quy tắc giải quyết module trùng phiên bản; nếu hai nhánh yêu cầu hai bản khác nhau, phải xem bản nào được chọn.

Có thể thu thập report bằng task Ivy sau khi resolve:

```xml
<target name="report-dependencies" depends="resolve-test">
    <mkdir dir="${build.dir}/ivy-report"/>
    <ivy:report conf="test"
                todir="${build.dir}/ivy-report"/>
</target>
```

Report giúp xem version được chọn, dependency bắc cầu và các revision bị loại do conflict. Tùy mức tái lập mong muốn, dự án có thể dùng một danh sách version đã duyệt, quy tắc override hoặc chính sách lock/validation riêng. Ivy mô tả graph, nhưng **không nên giả định mọi cấu hình Ivy mặc nhiên cung cấp lockfile bất biến như một số công cụ build khác**.

### 10.3. Chốt resolver và toolchain

Một bộ CI đáng tin thường xác định:

```text
Git revision
  + build.xml
  + ivy.xml
  + ivysettings.xml
  + Ant version
  + Ivy version
  + JDK version
  + repository policy
  + artifact versions/checksums
  = dependency + test environment được kiểm soát
```

Thay JDK, Ivy, resolver hoặc POM được cung cấp bởi repository có thể thay cách resolve hoặc hành vi test, kể cả khi không sửa source Java. Việc lưu metadata của môi trường trong log CI giúp chẩn đoán sự khác biệt giữa các lần chạy.

### 10.4. Tách thư viện test khỏi sản phẩm

Không lấy toàn bộ test classpath đưa vào JAR ứng dụng. Trong ví dụ, `package` chỉ đóng `classes.main`. Khi packaging ứng dụng lớn hơn, cần xác định rõ:

- Dependency runtime nào bắt buộc đi cùng ứng dụng.
- Dependency chỉ dùng compile và có sẵn trong môi trường triển khai.
- Dependency chỉ dùng test và không được xuất hiện trong release.

Configuration của Ivy hỗ trợ mô hình hóa nhóm dependency; đóng gói đúng vẫn phụ thuộc vào lựa chọn `fileset`, `basedir` và cách tạo artifact trong Ant.

## 11. Các lỗi thường gặp và cách tìm nguyên nhân

### 11.1. Không nhận ra task Ivy

Ví dụ log:

```text
Problem: failed to create task or type ivy:resolve
```

Nguyên nhân thường gặp: JAR Ivy chưa nằm trên Ant classpath, `<taskdef>` không đúng resource/URI hoặc lệnh chạy Ant thiếu `-lib`.

Cách xem xét: kiểm tra đường dẫn JAR Ivy, lệnh `ant -lib ...` và đăng ký:

```xml
<taskdef resource="org/apache/ivy/ant/antlib.xml"
         uri="antlib:org.apache.ivy.ant"/>
```

Nếu dùng `~/.ant/lib`, phải nhớ một runner CI mới có thể không có file đó. Vì vậy cấu hình minh bạch qua `-lib` hoặc image đã chốt thường dễ bảo trì hơn.

### 11.2. Không resolve được JUnit

Ví dụ nội dung lỗi có thể là:

```text
unresolved dependency: junit#junit;4.13.2
```

Hướng kiểm tra:

1. Revision và tọa độ trong `ivy.xml` có đúng không?
2. `ivysettings.xml` đã dùng resolver mong muốn chưa?
3. Maven Central/mirror có truy cập được từ JVM Ant không?
4. Hệ thống có proxy, chứng chỉ TLS nội bộ hoặc chính sách chặn mạng không?
5. Repository được chọn có POM và JAR đúng đường dẫn không?

Phân biệt **artifact không tồn tại** với **không truy cập được repository**. Không xóa cache bừa bãi trước khi đọc log resolver; điều đó có thể làm triệu chứng nặng hơn mà chưa giải quyết nguồn lỗi.

### 11.3. Test compile không thấy org.junit

```text
package org.junit does not exist
```

Ivy có thể đã resolve thành công, nhưng `<javac>` dành cho test chưa tham chiếu `ivy.test.path`. Kiểm tra `<classpath>` trong `compile-test` có đủ:

```xml
<classpath>
    <pathelement location="${classes.main}"/>
    <path refid="ivy.test.path"/>
</classpath>
```

Ngoài ra, xem lại configuration đã resolve là `test` hay vô tình là `compile` vốn không chứa JUnit.

### 11.4. JUnitCore không có khi chạy test

```text
Could not find or load main class org.junit.runner.JUnitCore
```

Thường do classpath của `<java>` không chứa JAR JUnit dù compile có thể dùng classpath khác. Đừng chỉ sửa classpath compile. Cần cho JVM **đang chạy test** nhìn thấy `classes.main`, `classes.test` và `ivy.test.path`.

### 11.5. NoClassDefFoundError cho Hamcrest

Với JUnit 4, một lỗi liên quan `org/hamcrest/...` cho thấy dependency bắc cầu bị thiếu ở runtime, classpath chưa đầy đủ, cấu hình transitivity không đúng hoặc dùng JAR từ nguồn không khớp.

Xem `ivy:report` hoặc danh sách artifact thực tế của `ivy:cachepath`, kiểm tra `transitive`, configuration mapping và POM. Không giải quyết bằng cách chép ngẫu nhiên một JAR Hamcrest vào thư mục cá nhân rồi bỏ qua mô tả trong dependency graph.

### 11.6. Test chạy nhưng lỗi không làm Ant fail

Nếu dùng `<java>` mà thiếu `failonerror="true"`, Ant có thể không coi exit code khác 0 là lỗi cần dừng build. Mẫu đúng cho bước bắt buộc:

```xml
<java classname="org.junit.runner.JUnitCore"
      fork="true"
      failonerror="true">
    <!-- classpath + arg test class -->
</java>
```

Chạy một test cố ý sai assertion để chứng minh CI thật sự fail khi test fail. Đừng coi một dòng log có chữ “FAILURES” là đủ nếu process điều phối vẫn trả `0`.

### 11.7. JAR ứng dụng có chứa thư viện test

Nếu package dùng `<fileset dir=".">` hoặc copy toàn bộ `build/`, các file từ test có thể lọt vào archive. Giải pháp là chọn **gốc đóng gói chỉ chứa mã sản phẩm** và kiểm tra entry phát hành:

```bash
jar tf dist/calculator.jar
```

Tách source/test class output ngay từ đầu giúp giảm nguy cơ đưa test/JUnit vào sản phẩm.

### 11.8. Ivy retrieve gây trùng hoặc giữ JAR cũ

Nếu tên file lấy từ `[artifact]-[revision].[ext]` nhưng nhiều organisation có artifact trùng tên, xảy ra va chạm. Nếu không sync vào thư mục riêng, JAR cũ có thể còn lại và xuất hiện trong classpath.

Có thể thêm `[organisation]` vào pattern hoặc sử dụng `ivy:cachepath` để Ivy cung cấp classpath từ graph đã resolve. Khi dùng retrieve, hãy quản lý thư mục đích như output sinh tự động và quyết định rõ cơ chế dọn file cũ.

## 12. Phân biệt Ivy, Maven và việc chép JAR thủ công

| Tiêu chí | JAR copy thủ công | Ivy + Ant | Maven/Gradle |
| --- | --- | --- | --- |
| Mô tả dependency | Tên file trong lib | `ivy.xml` | POM/build script |
| Phân giải dependency bắc cầu | Người dùng tự xử lý | Ivy xử lý từ metadata | Tích hợp trong build tool |
| Điều phối target Ant tùy biến | Có, nhưng thư viện thủ công | **Giữ nguyên build.xml** | Cần mô hình build của công cụ khác |
| Repository Maven | Tải/copy riêng | Resolver Ivy như `ibiblio` | Resolver tích hợp |
| Classpath test | Tự liệt kê JAR | `ivy:cachepath` hoặc `retrieve` | Tạo theo configuration |
| Chi phí chuyển đổi dự án Ant | Thấp ban đầu, bảo trì cao dần | Bổ sung descriptor/settings | Có thể phải chuyển cấu trúc build |
| Quản trị version/transitivity | Thủ công | Chính sách Ivy | Cơ chế của từng công cụ |

Ivy phù hợp khi dự án **đã tổ chức build bằng Ant** và muốn giữ các target đang có, nhưng cần quản lý thư viện kiểm thử theo tọa độ và repository. Nếu hệ thống đã có Maven/Gradle làm nguồn dependency chính, việc thêm Ivy riêng có thể tạo **hai nguồn cấu hình dependency**, cần cân nhắc trước khi dùng.

## 13. Bài tập mở rộng

### Bài 1 — Chạy test từ một workspace mới

Tạo đúng cấu trúc dự án mẫu, cung cấp JAR Ivy đã xác minh, sau đó chạy:

```bash
ant -lib tools/ivy-2.5.3.jar ci-test
```

Quan sát target resolve, classpath test và file `build/junit-console.txt`. Trả lời: nếu xóa `build/` nhưng giữ cache Ivy, Ivy còn cần tải lại JAR JUnit không? Điều kiện nào khiến nó phải đọc lại metadata hoặc truy cập repository?

### Bài 2 — Nhận diện dependency bắc cầu

Sau khi resolve `test`, tạo report:

```bash
ant -lib tools/ivy-2.5.3.jar report-dependencies
```

Muốn lệnh này chạy, bổ sung target `report-dependencies` ở mục 10.2 vào `build.xml`. Mở report và chỉ ra JUnit trực tiếp cùng các module bắc cầu được chọn. Thay `transitive="false"` trong dependency JUnit của bản sao test, rồi giải thích vì sao test có thể thiếu class dù JUnit JAR còn đó.

### Bài 3 — Dùng retrieve thay cachepath

Thêm target `retrieve-test-libs` từ mục 8 và gọi:

```bash
ant -lib tools/ivy-2.5.3.jar retrieve-test-libs
```

Quan sát `build/test-libs`. Sửa pattern để thêm `[organisation]`, rồi giải thích tác dụng khi có hai artifact cùng tên và revision. Thảo luận ưu/nhược điểm của cachepath và retrieve trong CI.

### Bài 4 — Ca lỗi được chặn đúng lúc

Đổi `rev` JUnit thành một revision không tồn tại trong bản sao cấu hình. Chạy `ci-test` và xác nhận Ant dừng ở bước resolve trước khi chạy JUnit. Khôi phục revision đúng rồi làm một assertion sai. Hai lỗi xuất hiện ở hai tầng nào của pipeline?

### Bài 5 — Giữ JUnit ngoài JAR phát hành

Chạy:

```bash
ant -lib tools/ivy-2.5.3.jar release
jar tf dist/calculator.jar
```

Kiểm tra rằng `Calculator.class` có mặt còn `CalculatorTest.class` và thư viện `org/junit` không nằm trong JAR. Nếu muốn đóng gói dependency runtime cho ứng dụng ở tương lai, cần thiết kế thêm configuration nào và sửa bước package ra sao?

### Bài 6 — Thiết kế pipeline thực tế

Cho một dự án Ant có nhiều test class và cần chạy trên CI không có mạng công khai. Hãy thiết kế:

- Resolver tới mirror nội bộ được phê duyệt.
- Cách cung cấp và chốt JAR Ivy cho runner.
- Phiên bản dependency trực tiếp và quy tắc bắc cầu.
- Cơ chế cache hoặc retrieve phù hợp runner.
- Lệnh clean/test, cách báo lỗi khi dependency không có.
- Cách xác minh JAR phát hành không mang test dependency.

Mục tiêu không chỉ là “chạy được trên máy cá nhân”, mà là một **đường build có đầu vào và kết quả giải thích được**, có thể bảo trì khi thành viên hoặc runner thay đổi.

## Tài liệu tham khảo

- Apache Ivy — [Official documentation](https://ant.apache.org/ivy/history/latest-milestone/index.html): hướng dẫn Ivy, module descriptor, settings, resolver và Ant tasks.
- Apache Ivy — [Ivy file](https://ant.apache.org/ivy/history/latest-milestone/ivyfile.html): `info`, `configurations`, `dependencies` và configuration mapping.
- Apache Ivy — [Ivy settings](https://ant.apache.org/ivy/history/latest-milestone/settings.html): lựa chọn resolver và cấu hình phân giải.
- Apache Ivy — [resolve task](https://ant.apache.org/ivy/history/latest-milestone/use/resolve.html), [cachepath task](https://ant.apache.org/ivy/history/latest-milestone/use/cachepath.html) và [retrieve task](https://ant.apache.org/ivy/history/latest-milestone/use/retrieve.html): các thao tác trực tiếp dùng trong Ant.
- Apache Ivy — [ibiblio resolver](https://ant.apache.org/ivy/history/latest-milestone/resolver/ibiblio.html): truy cập repository theo bố cục Maven.
- Apache Ant — [Taskdef task](https://ant.apache.org/manual/Tasks/taskdef.html), [Javac task](https://ant.apache.org/manual/Tasks/javac.html), [Java task](https://ant.apache.org/manual/Tasks/java.html): nạp custom task, biên dịch và chạy JUnit trong JVM con.
- JUnit 4 — [Documentation](https://junit.org/junit4/): `@Test`, assertion và runner `JUnitCore`.

**Điểm cần nhớ:** Ivy bổ sung khả năng **mô tả và phân giải thư viện** cho build Ant hiện có. Một chuỗi kiểm thử dễ bảo trì là: **nạp Ivy → chọn resolver → resolve `test` → tạo classpath → compile main/test riêng → chạy JUnit và chặn lỗi → chỉ đóng gói mã sản phẩm sau khi test đạt**. Khi version, repository, cache và toolchain được kiểm soát, quy trình này hoạt động nhất quán hơn giữa máy phát triển và CI.


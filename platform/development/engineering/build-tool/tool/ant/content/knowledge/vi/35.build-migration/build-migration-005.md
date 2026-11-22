# Chuyển từng giai đoạn biên dịch, kiểm thử và đóng gói sang Apache Ant

## 1. Vì sao nên chuyển đổi build theo giai đoạn?

Khi một dự án Java đang dùng script thủ công, một bộ lệnh cũ, Makefile hoặc một công cụ build khác, việc thay toàn bộ pipeline bằng **Apache Ant** trong một lần thay đổi thường làm khó việc tìm nguyên nhân nếu kết quả build khác trước. Các bước biên dịch, kiểm thử và đóng gói tuy liên quan nhưng có **đầu vào, đầu ra và tiêu chí đúng riêng**.

Thay vì chỉ đổi tên các lệnh, cần chuyển từng hành vi:

1. **Biên dịch (compile):** cùng tập mã nguồn và dependency phù hợp phải tạo ra các lớp Java với cùng mức tương thích đã yêu cầu.
2. **Kiểm thử (test):** cùng bộ test quan trọng phải được thực thi; test thất bại phải làm build thất bại, không bị bỏ qua hoặc đếm thiếu.
3. **Đóng gói (package):** archive cuối cùng phải chứa đúng lớp, tài nguyên, manifest và cấu trúc phát hành mà người dùng hoặc hệ thống triển khai cần.

Mỗi bước được đối chiếu với đường chuẩn từ build cũ trước khi thay thế bước tương ứng. Khi cả ba bước đạt tiêu chí, mới chuyển pipeline CI/CD sang Ant làm đường build chính.

Ví dụ một kế hoạch chuyển đổi:

```text
Build hiện tại
  compile cũ --> test cũ --> package cũ --> deploy
       |             |             |
       v             v             v
  Ant compile    Ant test      Ant package
       |             |             |
       +---- so sánh từng giai đoạn-+
                     |
                     v
             Chấp nhận pipeline Ant
                     |
                     v
             CI phát hành từ Ant
```

**Đích đến:** có một chuỗi Ant rõ ràng, chạy được từ checkout sạch, thất bại khi bất kỳ bước bắt buộc nào lỗi, và tạo sản phẩm có thể sử dụng theo hợp đồng phát hành đã xác định.

### “Tương đương” không nhất thiết có nghĩa là cùng checksum

Trong lúc chuyển công cụ, hai file JAR có thể **khác SHA-256** do thời gian đóng gói ZIP, thứ tự entry, metadata manifest hoặc khác phiên bản compiler, dù cùng tài nguyên và hành vi. Nếu yêu cầu của dự án là **build tái lập từng byte**, phải xử lý riêng tất cả những khác biệt đó. Còn trong một lần chuyển đổi công cụ, nên kiểm tra theo mức độ:

- **Tập thành phần:** file nào nằm trong sản phẩm, đường dẫn entry, dependency, tài nguyên và manifest có đúng không.
- **Hợp đồng kỹ thuật:** Java target/release, API public, khả năng chạy và cài đặt, quy tắc lỗi, bộ test.
- **Tính tái lập:** nếu dự án đặt tiêu chí byte-identical, kiểm tra checksum của sản phẩm cuối và điều tra toàn bộ metadata biến động.

Không được coi “Ant báo BUILD SUCCESSFUL” là bằng chứng pipeline mới hoàn toàn tương đương.

## 2. Ghi nhận đường chuẩn của build hiện tại trước khi sửa

Trước khi chuyển target nào, phải biết build đang làm gì. Một script cũ có thể thêm resource, chạy generator hoặc chuẩn bị manifest mà tài liệu cũ không nhắc tới.

Tại một commit cố định, ghi nhận:

| Nhóm | Cần biết | Vì sao |
| --- | --- | --- |
| Source | Thư mục chứa Java, generated sources, resources, file loại trừ | Tránh compile thiếu hoặc lấy nhầm test/generated code. |
| Compiler | JDK, `--release`/`source`/`target`, encoding, flags, annotation processors | Đảm bảo bytecode và API tương thích. |
| Dependency | Tọa độ/phiên bản JAR, classpath compile/test/runtime, cách lấy file | Không làm chương trình chạy trên classpath sai. |
| Test | Framework, cách tìm test, profile, biến môi trường, báo cáo, exit code | Tránh tình huống pipeline xanh nhưng không chạy đủ test. |
| Package | JAR/WAR/ZIP, manifest, tên file, tài nguyên, layout, permissions | Bảo toàn hợp đồng phát hành. |
| CI | Thứ tự stage, điều kiện stop, upload artifact, cache, secret, deploy gate | Không chuyển nhầm job kiểm thử thành job phát hành. |
| Runtime | Cách khởi chạy, Java version đích, thư viện đi kèm, smoke test | Chứng minh sản phẩm thực sự sử dụng được. |

Một mẫu ghi nhận kết quả:

```text
BASELINE_COMMIT=<commit>
JDK=<java -version>
BUILD_TOOL=<phiên bản và lệnh build cũ>
SOURCE_LAYOUT=src/main/java, src/main/resources, src/test/java
COMPILE_RELEASE=17
DEPENDENCY_INPUT=<danh sách và nội dung đã khóa>
TEST_TOTAL=<số lượng test thực sự chạy>
TEST_RESULT=PASS
PACKAGE=dist/demo-app.jar
PACKAGE_ENTRIES=<tập tên entry đã lưu>
MANIFEST=<Main-Class và các thuộc tính cần thiết>
RUNTIME_SMOKE_TEST=PASS
```

Các giá trị `<...>` là thông tin cần điền từ build thực tế, không phải một bộ kết quả mặc định. Nếu chưa biết rõ một phần, hãy xác định trước khi tuyên bố đã chuyển thành công phần đó.

### Chạy trên hai vùng đầu ra riêng biệt

Trong giai đoạn so sánh, cho build cũ và build Ant ghi sản phẩm vào **hai thư mục khác nhau**, chẳng hạn:

```text
comparison/
├── legacy/
│   └── demo-app.jar
└── ant/
    └── demo-app.jar
```

Không để hai công cụ cùng ghi `dist/demo-app.jar` rồi so sánh file sau cùng: build chạy sau có thể ghi đè kết quả của build trước. Đường dẫn đầu ra nên cấu hình được trong Ant để thuận tiện cho việc đối chiếu.

## 3. Thiết kế đồ thị target Ant trước khi chuyển logic

Ant hoạt động dựa trên target và quan hệ `depends`. Một đồ thị tối thiểu:

```text
prepare
   |
   v
compile-main
   |
   v
copy-resources
   |
   v
compile-tests
   |
   v
test
   |
   v
package
   |
   v
verify-package
```

Trong đồ thị này:

- `compile-main` chỉ biên dịch ứng dụng.
- `copy-resources` đưa resource cần thiết vào classpath đầu ra.
- `compile-tests` biên dịch nguồn test.
- `test` thực sự chạy test và dừng khi thất bại.
- `package` chỉ đóng gói sau khi test đã đạt.
- `verify-package` xác minh file thành phẩm tồn tại và công bố checksum.

**Không nối `clean` làm dependency bắt buộc của mọi target.** Ant cần có thể chạy build tăng dần để phát triển nhanh, còn CI hoặc lần kiểm tra tái lập sẽ gọi tường minh `ant clean verify-package`. Nếu mọi target tự xóa sản phẩm ở đầu, việc chạy riêng một giai đoạn để điều tra sẽ khó hơn.

### Cần chú ý ý nghĩa của `depends`

Ant chạy target phụ thuộc trước, mỗi target trong một lần gọi chỉ được thực thi một lần nếu xuất hiện trong nhiều nhánh phụ thuộc. Nếu có:

```xml
<target name="test" depends="compile-tests"/>
<target name="package" depends="test"/>
```

thì `ant package` sẽ chạy cả hai bước trước đó theo quan hệ dependency. Nhưng gọi `ant compile-main` sẽ **không** tự chạy kiểm thử hoặc đóng gói, thích hợp khi đang xác minh riêng bước compile.

Quyết định cho `package` phụ thuộc `test` là **chính sách chất lượng** của ví dụ. Một số dự án cho phép tạo JAR tạm ngay cả khi chưa chạy test; lúc đó có thể thiết kế `assemble` để đóng gói và `release` phụ thuộc `test,assemble`. Điều cần giữ chắc là **đường phát hành chính thức** phải có kiểm thử bắt buộc và không phát hành khi fail.

## 4. Dự án thực hành dùng để chuyển từng bước

Giả sử dự án có cấu trúc sau:

```text
ant-migration-demo/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── example/
│   │   │       └── Greeter.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/
│           └── example/
│               └── GreeterTest.java
├── lib/
│   ├── main/                # Có thể rỗng trong ví dụ này
│   └── test/
│       ├── junit-4.13.2.jar
│       └── hamcrest-core-1.3.jar
├── build/                   # Ant sinh ra
└── dist/                    # Ant sinh ra
```

**Điều kiện chạy:** JDK 17 trở lên, Apache Ant có khả năng `<javac release="17">`, và hai JAR JUnit 4.13.2/Hamcrest Core 1.3 có nội dung đã được xác minh, đặt đúng trong `lib/test/`. Ví dụ không tải dependency tự động. Khi đưa vào CI thật, cần dùng cơ chế quản lý dependency có phiên bản/checksum thay vì tải file tùy ý hoặc commit file không rõ nguồn.

Nội dung `src/main/java/example/Greeter.java`:

```java
package example;

public final class Greeter {
    private Greeter() {}

    public static String greet(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Ant" : args[0];
        System.out.println(greet(name));
    }
}
```

Nội dung `src/test/java/example/GreeterTest.java`:

```java
package example;

import static org.junit.Assert.assertEquals;
import org.junit.Test;

public class GreeterTest {
    @Test
    public void greetIncludesName() {
        assertEquals("Xin chào, Linh", Greeter.greet("Linh"));
    }
}
```

Nội dung `src/main/resources/application.properties`:

```properties
application.name=ant-migration-demo
application.language=vi
```

Ba tệp này giúp quan sát đầy đủ: source chính có logic, source test dùng JUnit 4, và resource phải xuất hiện trong JAR. Chỉ nhìn `.class` mà không kiểm tra resource sẽ không đủ.

## 5. Viết `build.xml` theo từng giai đoạn

Đây là file Ant tự chứa các target cần thiết. Có thể dùng ngay cho cấu trúc ở phần trên.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-migration-demo"
         default="verify-package"
         basedir=".">

    <!-- 1. Input và output -->
    <property name="source.main.dir" location="src/main/java"/>
    <property name="source.test.dir" location="src/test/java"/>
    <property name="resources.dir" location="src/main/resources"/>

    <property name="lib.main.dir" location="lib/main"/>
    <property name="lib.test.dir" location="lib/test"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="test.classes.dir" location="build/test-classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="package.file" location="dist/demo-app.jar"/>

    <!-- 2. Classpath: sản phẩm chính tách khỏi test -->
    <path id="main.classpath">
        <fileset dir="${lib.main.dir}">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <path refid="main.classpath"/>
        <fileset dir="${lib.test.dir}">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <!-- 3. Dọn đầu ra, không xóa thư viện đầu vào -->
    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
    </target>

    <!-- 4. Chuyển giai đoạn biên dịch mã chính -->
    <target name="compile-main" depends="prepare">
        <javac srcdir="${source.main.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"
               debug="true">
            <classpath refid="main.classpath"/>
        </javac>
    </target>

    <!-- 5. Sao chép resource vào classpath -->
    <target name="copy-resources" depends="compile-main">
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}"/>
        </copy>
    </target>

    <!-- 6. Biên dịch test và báo lỗi khi thiếu JUnit -->
    <target name="check-test-libs">
        <available file="${lib.test.dir}/junit-4.13.2.jar"
                   property="junit.present"/>
        <available file="${lib.test.dir}/hamcrest-core-1.3.jar"
                   property="hamcrest.present"/>
        <fail unless="junit.present"
              message="Thiếu lib/test/junit-4.13.2.jar"/>
        <fail unless="hamcrest.present"
              message="Thiếu lib/test/hamcrest-core-1.3.jar"/>
    </target>

    <target name="compile-tests"
            depends="copy-resources,check-test-libs">
        <javac srcdir="${source.test.dir}"
               destdir="${test.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"
               debug="true">
            <classpath refid="test.classpath"/>
        </javac>
    </target>

    <!-- 7. Chạy test. JUnitCore trả exit code khác 0 nếu test fail -->
    <target name="test" depends="compile-tests">
        <java classname="org.junit.runner.JUnitCore"
              fork="true"
              failonerror="true">
            <classpath refid="test.classpath"/>
            <arg value="example.GreeterTest"/>
        </java>
    </target>

    <!-- 8. Chỉ package sau khi test đã thành công -->
    <target name="package" depends="test">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${package.file}"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class"
                           value="example.Greeter"/>
            </manifest>
        </jar>
    </target>

    <!-- 9. Kiểm tra file phát hành và in checksum -->
    <target name="verify-package" depends="package">
        <available file="${package.file}"
                   property="package.exists"/>
        <fail unless="package.exists"
              message="Chưa tạo được dist/demo-app.jar"/>
        <checksum file="${package.file}"
                  algorithm="SHA-256"
                  property="package.sha256"/>
        <echo message="Package SHA-256: ${package.sha256}"/>
    </target>

</project>
```

Trong Ant, `<property>` thông thường là **immutable**: khi một thuộc tính đã được định nghĩa, lần khai báo sau không thay đổi nó. Thuộc tính truyền từ command line bằng `-D...` có thể được dùng để override giá trị mặc định vì được thiết lập trước phần khai báo property trong project. Trong dự án lớn nên kiểm soát rõ các thuộc tính được phép override; không giả định mọi giá trị sẽ bị gán lại như biến shell.

> Ví dụ trên giả định các thư mục `src/main/java`, `src/main/resources`, `src/test/java`, `lib/main` và `lib/test` đã tồn tại. Thư mục `lib/main` có thể chứa một file giữ chỗ để được tạo trong checkout dù chưa dùng thư viện nào. Nếu dự án không có thư mục nào đó, cần điều chỉnh target/fileset tương ứng vì `<fileset dir="...">` có thể báo lỗi khi thư mục không tồn tại.

### Tại sao cấu hình được tách như vậy?

- `compile-main` không cần JUnit và không đưa `lib/test` vào classpath compile. Phần test chỉ có vai trò test.
- `copy-resources` phụ thuộc `compile-main` và đặt tài nguyên vào đúng lớp đầu ra sẽ được đóng gói.
- `compile-tests` dùng cả class chính và dependency test, nhưng file `.class` test nằm riêng ở `build/test-classes`.
- `test` có `fork="true"` để chạy test trong JVM riêng; `failonerror="true"` làm target thất bại nếu `JUnitCore` kết thúc với exit code khác 0.
- `package` đóng gói **chỉ** `build/classes`, nên test class và JUnit JAR không vô tình lọt vào bản phát hành.
- `verify-package` đọc file đã tạo và in SHA-256 để ghi nhận bằng chứng về sản phẩm. Hai lần build cho checksum khác nhau vẫn cần xem metadata JAR trước khi kết luận logic chương trình khác.

Ví dụ chọn **JUnit 4** và một test class cố định để giải thích cách nối giai đoạn. Với dự án thực có hàng chục/hàng nghìn test hoặc đang dùng **JUnit 5**, phải cấu hình bộ chạy tương ứng (chẳng hạn `junitlauncher` với các thư viện JUnit Platform đúng phiên bản) và cơ chế khám phá test phù hợp; không tự thay JUnit 5 bằng JUnit 4 khi di chuyển build.

## 6. Giai đoạn 1: chuyển biên dịch và đo mức tương đương

Lúc đầu, chưa cần cho Ant tạo JAR chính thức. Trước tiên thực thi:

```bash
ant -version
java -version
ant clean compile-main
```

Sau đó quan sát thư mục:

```text
build/
├── classes/
│   └── example/
│       └── Greeter.class
└── test-classes/
```

`prepare` tạo `test-classes` nhưng `compile-main` chưa biên dịch test. Đây là kết quả đúng với thứ tự target.

### 6.1. Giữ nguyên compiler contract

Khi chuyển từ build cũ, ít nhất cần đối chiếu:

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| JDK | Ant và build cũ đang dùng cùng JDK/compiler hay không? |
| Java release | Tệp `.class` có tương thích Java runtime đích không? |
| Encoding | Compiler có đọc source UTF-8 đúng như build cũ không? |
| Classpath | Có lấy đúng dependency compile, không trộn thư viện test vào production không? |
| Annotation processor | Có chạy đúng processor, đúng version và tạo đúng generated source không? |
| Source include/exclude | Có biên dịch đủ lớp, không kéo thêm file không thuộc module không? |
| Debug/lint flags | `debug` và các tham số compiler quan trọng có được giữ lại không? |
| Incremental behavior | Lượt build sạch có giống mong đợi không? Tệp .class cũ có che giấu lỗi không? |

Ở ví dụ, `release="17"` yêu cầu JDK hỗ trợ tham số `--release 17`. Khác với chỉ gán `target="17"`, tham số `--release` còn kiểm soát tập API chuẩn của Java ở phiên bản đích. Nếu ứng dụng cần Java 11, hãy kiểm tra source/dependency và thay giá trị release tương ứng thay vì mặc định giữ 17.

### 6.2. So sánh đầu ra compile đúng cách

Nếu hai build tạo các lớp tương ứng, có thể đối chiếu:

- Danh sách đường dẫn `.class` tương đối trong hai cây đầu ra.
- Phiên bản class file và chữ ký public qua `javap -verbose` hoặc API diff.
- Nội dung bytecode khi cùng compiler/flags và đã chuẩn hóa những khác biệt có thể ảnh hưởng.
- Một smoke test đơn giản gọi entry point mà ứng dụng dự kiến cung cấp.

Ví dụ:

```bash
javap -classpath build/classes -verbose example.Greeter
```

Với bản build cũ, thay `build/classes` bằng đúng thư mục compile của build đó. Các giá trị constant pool, debug path, thứ tự sinh và annotation có thể khác khi toolchain khác nhau. Vì vậy **khác checksum của `.class`** là tín hiệu để điều tra, không đồng nghĩa mọi hành vi đều sai; ngược lại, chỉ cùng tên file cũng chưa đủ.

### 6.3. Di chuyển code generation trước hay sau compile?

Nếu build cũ chạy generator (ví dụ tạo Java từ schema/OpenAPI/ANTLR) trước khi compile, đồ thị Ant phải thể hiện thứ tự:

```text
generate-sources --> compile-main --> copy-resources
```

Nguồn generate nên nằm ở thư mục riêng như `build/generated-sources`, không ghi đè source do lập trình viên quản lý. Khi chuyển, cần so sánh cả mã generate và tool/version của generator; nếu bỏ qua, Ant có thể compile từ mã cũ đã nằm sẵn trên máy.

## 7. Giai đoạn 2: chuyển kiểm thử, giữ nguyên quy tắc thất bại

Sau khi compile chính đạt tiêu chí, thêm bước:

```bash
ant clean test
```

Với ví dụ, Ant sẽ tự chạy:

```text
prepare
  -> compile-main
  -> copy-resources
  -> check-test-libs
  -> compile-tests
  -> test
```

Thông thường JUnit 4 `JUnitCore` in thông tin chạy test, ví dụ dạng:

```text
JUnit version 4.13.2
.
Time: ...
OK (1 test)
```

Đó là **ví dụ hình thức output**; thời gian và thông điệp cụ thể có thể khác theo môi trường. Quan trọng hơn là có test được chạy thực sự và exit code bằng 0 khi pass.

### 7.1. Kiểm tra trường hợp thất bại có chặn build không

Cố tình đổi expected value trong `GreeterTest` thành một giá trị không đúng, rồi chạy:

```bash
ant clean test
```

Khi `JUnitCore` trả exit code khác 0, `<java failonerror="true">` khiến target `test` thất bại. Vì `package` phụ thuộc `test`, lệnh `ant package` cũng phải thất bại trước khi đóng gói. Không nên đặt `failonerror="false"` chỉ để CI có trạng thái xanh.

Đừng xem test compile thành công là test pass. Bước `compile-tests` chỉ xác nhận test source biên dịch được; **`test` mới thực thi test** và cần có bằng chứng về số test, kết quả và lỗi.

### 7.2. Giữ đủ test suite

Ví dụ `<arg value="example.GreeterTest"/>` chạy một class cụ thể. Khi chuyển dự án thực:

- Liệt kê test suite cũ, nhóm unit/integration và quy tắc chọn test.
- Chuyển cơ chế discovery/filter phù hợp; không chỉ chạy một test class minh họa.
- Với JUnit 4, có thể cân nhắc task `<junit>` của Ant với `<batchtest>`, nhưng cần các optional Ant JUnit task/library phù hợp.
- Với JUnit 5, dùng `<junitlauncher>` hoặc bộ chạy JUnit Platform phù hợp và đúng dependency; không thay tên task tùy tiện.
- Kiểm soát biến môi trường, working directory, database test, timezone và test data.
- Giữ cơ chế test report mà CI cần (ví dụ XML JUnit report) để giao diện CI vẫn hiển thị số lượng pass/fail.
- Đảm bảo build fail khi không chạy được test bắt buộc; đặc biệt cần phát hiện “0 test được phát hiện” nếu dự án yêu cầu suite không rỗng.

**Ví dụ mở rộng JUnit 4 bằng Ant optional task** (chỉ dùng khi Ant có `ant-junit.jar` và các thư viện JUnit cần thiết):

```xml
<target name="test-batch" depends="compile-tests">
    <mkdir dir="build/test-reports"/>
    <junit fork="true"
           haltonfailure="true"
           haltonerror="true"
           printsummary="yes">
        <classpath refid="test.classpath"/>
        <formatter type="xml"/>
        <batchtest todir="build/test-reports">
            <fileset dir="${test.classes.dir}">
                <include name="**/*Test.class"/>
                <exclude name="**/*$*.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Trong code thật, bổ sung quy tắc kiểm soát test count khi suite có thể rỗng; Ant task tùy phiên bản có thể xử lý khác nhau khi không tìm thấy class test. Đây là một hướng mở rộng, **không phải** target đang được gọi bởi `package` trong `build.xml` mẫu. Nếu chuyển sang `test-batch`, cần thay dependency và loại bỏ đường chạy test không còn dùng.

### 7.3. Không gộp unit test với integration test nếu cần điều kiện khác nhau

Một dự án có test cần database hoặc dịch vụ ngoài nên tách target:

```xml
<target name="unit-test" depends="compile-tests">
    <!-- Chạy test không yêu cầu dịch vụ ngoài -->
</target>

<target name="integration-test" depends="unit-test">
    <!-- Chuẩn bị cấu hình test, chạy suite integration -->
</target>

<target name="release-gate" depends="integration-test">
    <!-- Chỉ được phát hành nếu mọi kiểm tra bắt buộc đã pass -->
</target>
```

Code trên là **đồ thị thiết kế**, các phần `<!-- ... -->` chưa phải lệnh chạy test thực. Trong quá trình chuyển đổi, phải triển khai runner thật, exit code và report rồi mới coi target là gate chất lượng. Một target Ant chỉ có `echo` vẫn có thể báo `BUILD SUCCESSFUL` dù không thực hiện kiểm thử nào.

## 8. Giai đoạn 3: chuyển đóng gói và bảo toàn hợp đồng phát hành

Khi compiler và test đã đạt đường chuẩn, chạy:

```bash
ant clean package
```

Với ví dụ, file xuất bản là `dist/demo-app.jar`. Mở nội dung:

```bash
jar tf dist/demo-app.jar
```

Danh sách entry đáng mong đợi gồm:

```text
META-INF/
META-INF/MANIFEST.MF
example/
example/Greeter.class
application.properties
```

Thứ tự hiển thị có thể khác; cần quan tâm tới **tập entry thực tế** và đường dẫn tương đối. Test class `example/GreeterTest.class` và JUnit JAR không nên xuất hiện trong JAR production.

Thử chạy:

```bash
java -jar dist/demo-app.jar
```

Kết quả của mã `Greeter` với tham số mặc định:

```text
Xin chào, Ant
```

Nếu `java -jar` báo không tìm được main class, kiểm tra `META-INF/MANIFEST.MF`, tên package, `Main-Class` và sự có mặt của class. Nếu chương trình cần dependency bên ngoài, một JAR chứa riêng class của project **không** tự mang theo tất cả thư viện runtime; phải đóng gói hoặc phân phối dependency theo đúng contract của build cũ.

### 8.1. So sánh package qua bảng hợp đồng

| Thành phần | Cách kiểm tra | Rủi ro nếu bỏ sót |
| --- | --- | --- |
| Tên và vị trí artifact | `dist/demo-app.jar` hay đường dẫn CI được công bố | Job upload/deploy lấy nhầm file hoặc không tìm thấy. |
| Main-Class | Nội dung `META-INF/MANIFEST.MF`, `java -jar` | JAR không khởi động theo cách cũ. |
| Lớp production | `jar tf` và smoke test | Thiếu lớp ở runtime. |
| Resources | Liệt kê entry và kiểm tra `getResource`/logic đọc file | Chương trình chạy nhưng thiếu cấu hình/template. |
| Test classes | Bảo đảm không nằm trong production JAR | Tăng dung lượng, lộ dữ liệu test, rối classpath. |
| Dependencies | JAR ngoài đi kèm, classpath, manifest `Class-Path` hoặc fat-JAR | `NoClassDefFoundError` khi chạy ở máy sạch. |
| File permission/script | ZIP/tar distribution khi có script khởi động | Bản cài đặt không chạy trên môi trường đích. |
| Archive metadata | Timestamp, thứ tự entry, mã hóa tên, manifest | Thay đổi checksum, ảnh hưởng yêu cầu tái lập byte. |

### 8.2. Nếu sản phẩm cũ là WAR, ZIP hoặc bộ phân phối nhiều file

Không thay mọi sản phẩm bằng `<jar>` chỉ vì Ant có task đó. Hãy chọn task tương ứng với loại sản phẩm cần bảo toàn:

- `<jar>`: đóng gói Java archive.
- `<war>`: tạo web archive với layout và `WEB-INF` cần thiết.
- `<zip>`: phân phối nhiều tệp, ví dụ scripts, config và JAR.
- `<copy>`, `<move>` hoặc mapping file: giữ layout thư mục phát hành.

Ví dụ distribution ZIP:

```xml
<target name="package-distribution" depends="package">
    <mkdir dir="${dist.dir}/bundle/lib"/>
    <copy file="${package.file}"
          todir="${dist.dir}/bundle/lib"/>
    <copy todir="${dist.dir}/bundle">
        <fileset dir="distribution">
            <include name="**/*"/>
        </fileset>
    </copy>
    <zip destfile="${dist.dir}/demo-distribution.zip"
         basedir="${dist.dir}/bundle"/>
</target>
```

Đoạn này giả định thư mục `distribution/` tồn tại và chỉ chứa các tài nguyên được phép đưa vào phát hành. Nó bổ sung một sản phẩm ZIP, không làm JAR tự chứa dependency. Nếu build cũ phân phối lib runtime ngoài JAR, cần thiết kế thêm bước copy đúng những lib đó; không copy toàn bộ thư viện test vào bundle.

### 8.3. Vì sao chỉ so sánh hash của JAR chưa đủ?

Giả sử Ant và công cụ cũ tạo JAR có cùng các file logic bên trong nhưng timestamp của entry khác nhau. Hash của hai JAR có thể khác dù nội dung sau giải nén giống nhau. Khi đối chiếu:

1. So sánh **tập đường dẫn** và loại archive.
2. So sánh kích thước và SHA-256 của toàn file archive để biết có khác byte hay không.
3. Nếu khác, giải nén hai archive vào thư mục riêng và so sánh **tên + checksum từng entry**.
4. Nếu entry có cùng byte, kiểm tra metadata ZIP/JAR và quy trình đóng gói.
5. Chạy smoke test với đúng command/runtime triển khai thực tế.

Ngược lại, checksum toàn JAR bằng nhau là bằng chứng mạnh về byte giống nhau của **JAR đó**, nhưng không chứng minh cả bộ distribution, tập dependency ngoài hoặc hành vi trong mọi môi trường đều giống.

## 9. Di chuyển CI theo từng cổng kiểm tra

Để tránh tác động tới quá trình phát hành hiện hữu, nên coi đường Ant mới là một nhánh **shadow validation** trong giai đoạn đầu: nó build và kiểm tra, nhưng **chưa phát hành** sản phẩm.

### Giai đoạn A — Chạy compile Ant cạnh build cũ

```text
CI:
  legacy build ------------> vẫn là đường chính
       |
       +-- ant clean compile-main
               |
               +-- đối chiếu file/class/compiler flags
```

Giai đoạn này nhằm tìm lỗi compiler/classpath trước khi xét tới test và package. Nếu Ant compile fail, job đối chiếu fail hoặc ghi nhận lỗi tùy chính sách thử nghiệm; vẫn giữ nguyên đường phát hành cũ.

### Giai đoạn B — Thêm test

```text
CI:
  legacy build + tests ----> đường chính
       |
       +-- ant clean test
               |
               +-- so sánh test list, số test, exit code, report
```

Chỉ chuyển test gate khi Ant chạy **đủ** test bắt buộc. Cùng tổng số test vẫn chưa chứng minh cùng bộ test; nên đối chiếu tên test/class khi có thể.

### Giai đoạn C — Thêm package

```text
CI:
  legacy package ----------> artifact được phát hành
       |
       +-- ant clean verify-package
               |
               +-- jar tf + manifest + runtime smoke test
               +-- đối chiếu distribution contents
```

Trong giai đoạn này, lưu artifact Ant với tên tách biệt (ví dụ artifact CI `ant-candidate`) và giữ artifact legacy có tên riêng. Không đưa cả hai vào một đường upload/release dùng chung nếu hệ thống triển khai không phân biệt phiên bản.

### Giai đoạn D — Chuyển Ant thành đường chính

Khi các tiêu chí đã đạt, sửa pipeline để:

1. Checkout cùng nguồn đã kiểm soát.
2. Chuẩn bị đúng JDK, Ant và dependency.
3. Gọi `ant -noinput clean verify-package`.
4. Chạy các gate kiểm thử cần thiết và smoke test.
5. Upload **chỉ sản phẩm Ant đã được xác minh** làm artifact phát hành.
6. Giữ đường rollback được mô tả rõ ràng cho đến khi đủ tự tin loại bỏ pipeline cũ.

**Tránh tình huống hai build cùng deploy.** Trong thời gian song song, chỉ một pipeline có quyền publish/deploy production. Bản Ant nên chỉ dùng trong job kiểm tra hoặc artifact review cho đến khi có quyết định chuyển chính thức.

### Một job CI mẫu

Đây là ví dụ GitHub Actions đơn giản cho dự án thực hành:

```yaml
name: Verify Ant build

on:
  push:
  pull_request:

jobs:
  ant:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Apache Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant
          ant -version
          java -version

      - name: Compile, test and package
        run: ant -noinput clean verify-package

      - name: Smoke test
        run: |
          java -jar dist/demo-app.jar
          jar tf dist/demo-app.jar

      - name: Upload candidate artifact
        uses: actions/upload-artifact@v4
        with:
          name: ant-candidate
          path: dist/demo-app.jar
          if-no-files-found: error
```

Workflow minh họa này **chưa tự chuẩn bị** hai JAR JUnit cần thiết; dự án phải có chúng qua checkout hoặc một bước resolve dependency đáng tin cậy trước khi chạy Ant. Bản cài Ant bằng `apt-get` cũng có thể thay đổi version theo kho phân phối. Khi chuyển CI production, nên quản lý phiên bản Ant/JDK/dependency chặt chẽ hơn, và bổ sung các test, report, secret/sandbox theo yêu cầu hệ thống.

Việc GitHub Actions hoặc runner khác upload được file chỉ chứng minh file tồn tại tại đường dẫn được chỉ định. Mỗi lần phát hành cần gắn artifact với commit, kết quả test và quy trình xác minh của chính build đó.

## 10. Tách cấu hình theo môi trường mà không làm sai thứ tự stage

Một build di chuyển thường có cấu hình khác nhau cho local, CI và release. Có thể truyền property qua `-D`:

```bash
ant "-Ddist.dir=out/ant-candidate" clean verify-package
```

Tuy nhiên, trong `build.xml` mẫu, `package.file` được khai báo bằng `location="dist/demo-app.jar"` độc lập với `dist.dir`. Vì vậy nếu muốn override thư mục đầu ra, cần viết lại thuộc tính để liên hệ đúng với `dist.dir`:

```xml
<property name="dist.dir" location="dist"/>
<property name="package.file"
          location="${dist.dir}/demo-app.jar"/>
```

Khi đó, nếu `dist.dir` được thiết lập từ dòng lệnh trước khi file được parse, `package.file` sẽ được tính dựa trên giá trị đã override. Cần kiểm tra cả target `clean`: nó sẽ xóa thư mục mà `dist.dir` trỏ tới. Không truyền một đường dẫn hệ thống hoặc thư mục chứa dữ liệu khác cho thuộc tính này rồi chạy `clean`.

### Đặc điểm Ant: property được mở rộng theo thời điểm sử dụng

Ant không phải hệ thống biến shell. Nhiều property có semantics “set once”; một số giá trị được mở rộng ngay khi được khai báo và không tự cập nhật nếu property khác thay đổi sau đó. Khi chuyển build, định nghĩa thứ tự property rõ ràng và tránh dựa vào phép gán lại để thay đổi môi trường trong cùng một process Ant.

Với dependency, cấu hình nhánh/module cũng cần được đưa vào classpath một cách có kiểm soát. Đừng chuyển mọi thuộc tính build cũ thành `-D...` một cách máy móc mà không xác định ai là nguồn chân lý của giá trị đó.

## 11. Kiểm soát thay đổi để tránh build “xanh giả”

Có một số lỗi có thể khiến CI báo thành công nhưng pipeline Ant chưa đạt chất lượng:

| Lỗi thiết kế | Hậu quả | Cách phát hiện/chỉnh |
| --- | --- | --- |
| `package` không phụ thuộc `test` trong đường release | Build lỗi test vẫn đóng gói | Đặt gate test trên đường phát hành, kiểm tra tình huống cố ý làm test fail. |
| Test target chỉ compile source test | Không có test nào được chạy | Có test runner thật, kiểm tra số test và exit code. |
| Test runner báo fail nhưng Ant bỏ qua | CI xanh sai | `failonerror="true"` hoặc `haltonfailure/haltonerror` phù hợp. |
| Ant lấy lại `build/classes` cũ | Source thiếu vẫn có `.class` | Chạy clean build từ checkout sạch trong CI. |
| Thư mục source test lọt vào JAR | Sản phẩm phát hành thừa nội dung | Tách classes/test-classes và kiểm tra `jar tf`. |
| Sao chép thiếu resources | Chương trình runtime thiếu config | So sánh entry và chạy smoke test đọc tài nguyên. |
| Dependency test lọt vào runtime | Tăng kích thước/lỗi license/bảo mật | Tách classpath main, test và runtime. |
| Công cụ cũ và Ant cùng ghi một thư mục | Kết quả đối chiếu bị ghi đè | Tách output, chỉ một pipeline có quyền publish. |
| Dùng phiên bản dependency động | Cùng source tạo đầu ra khác nhau | Khóa phiên bản và nội dung, kiểm tra tập resolved dependency. |
| Chỉ so sánh build success | Bỏ qua khác biệt API, manifest, bộ test | Có tiêu chí đo được cho từng giai đoạn. |
| Xóa đường build cũ quá sớm | Không thể rollback khi gặp lỗi sản xuất | Hoàn thành tiêu chí và thủ tục chuyển/rollback trước. |

Một phép kiểm tra nên thực hiện trong quá trình chuyển đổi là tạo lỗi có chủ đích ở từng stage, ví dụ lỗi cú pháp Java, một assertion fail, và cấu hình archive sai. Pipeline cần dừng đúng giai đoạn, không che lỗi bằng `onerror="continue"`, `failonerror="false"` hoặc echo thành công.

## 12. Quản lý dependency trong lúc chuyển đổi

Ant lõi không tự phân giải dependency Maven theo tọa độ `groupId:artifactId:version`. Tệp `build.xml` mẫu giả định JAR đã có trong `lib/`. Khi chuyển từ Maven hoặc Gradle, bỏ qua cơ chế resolve của công cụ cũ có thể làm build Ant dùng nhầm JAR.

Các lựa chọn phổ biến:

- **Giữ thư viện JAR đã pin:** phù hợp ví dụ nhỏ, nhưng phải quản lý checksum, license và nguồn gốc.
- **Dùng Apache Ivy:** khai báo dependency và resolver riêng, thực hiện resolve/retrieve trước compile/test.
- **Dùng artifact repository/mirror quản lý:** CI lấy dependency đã duyệt theo checksum từ nguồn tin cậy.
- **Tách migration thành giai đoạn phụ thuộc:** trước mắt chuyển compile/test/package với tập JAR cố định, sau đó mới đổi cơ chế download nếu dự án cho phép.

Khi so sánh, nên ghi nhận **toàn bộ cây dependency thực tế**, không chỉ dependency khai báo trực tiếp. Một thay đổi transitive dependency hoặc classpath order có thể làm test kết quả khác dù source giữ nguyên.

### Classpath compile, test và runtime không giống nhau

```text
compile-main:
    production dependency

compile-tests:
    production classes + test classes + test dependency

test runtime:
    production classes + test classes + test dependency

production runtime:
    production classes + runtime dependency cần thiết
```

Ví dụ dự án không dùng thư viện ngoài trong `Greeter` nên JAR có thể chạy trực tiếp bằng `java -jar`. Trong ứng dụng thật, Ant cần xử lý lib runtime theo đúng loại distribution đã chọn. **Không** lấy nguyên classpath test để làm classpath phát hành.

## 13. Đối chiếu kết quả giữa build cũ và Ant

Một ma trận chấp nhận chuyển đổi giúp nhóm xác nhận tiến độ:

| Giai đoạn | Tiêu chí chấp nhận | Bằng chứng |
| --- | --- | --- |
| **Compile** | Cùng source cần thiết, JDK/`release`/dependency phù hợp, class chính có mặt | Log compile, danh sách `.class`, thông tin compiler, smoke invocation |
| **Test** | Các test bắt buộc đã chạy, kết quả pass, build fail khi test fail | Danh sách và số test, JUnit report, exit code |
| **Package** | Đúng định dạng/tên/manifest, đủ resource/dependency, chạy được | `jar tf`, manifest, checksum, smoke test |
| **CI gate** | Clean build từ checkout mới, fail-fast, một đường publish duy nhất | Log CI, artifact id, commit và trạng thái job |
| **Rollback** | Có thể quay lại đường phát hành đã biết nếu cần | Quy trình kích hoạt lại pipeline cũ, điều kiện chuyển lại |

### Ví dụ lệnh đối chiếu sản phẩm JAR

Nếu đã có `comparison/legacy/demo-app.jar` và `comparison/ant/demo-app.jar`:

```bash
jar tf comparison/legacy/demo-app.jar > comparison/legacy-entries.txt
jar tf comparison/ant/demo-app.jar > comparison/ant-entries.txt

# Lệnh phổ biến trên Linux:
sha256sum comparison/legacy/demo-app.jar
sha256sum comparison/ant/demo-app.jar
```

Khi so sánh danh sách entry, nên chuẩn hóa **thứ tự hiển thị** (ví dụ sắp xếp) trước khi kết luận khác về tập entry. Nếu checksum khác, so sánh nội dung sau giải nén và metadata ZIP thay vì chỉ nhìn thông báo. Với artifact chứa nhiều file, cần so sánh cả bộ distribution bên ngoài JAR.

Đừng đưa tài liệu/log từ chính phép đối chiếu vào thư mục đang được đóng gói, vì chúng có thể vô tình thay đổi tập output của lượt build tiếp theo.

### Smoke test phải khớp mục tiêu deploy

Trong ví dụ nhỏ, `java -jar` đủ để kiểm tra đường chạy chính. Với service, web app hoặc CLI thật, smoke test nên kiểm tra cơ chế triển khai đã có:

- CLI: chạy với một input có kiểm soát, kiểm tra exit code và output quan trọng.
- Service: khởi động trong môi trường test, kiểm tra health endpoint và cấu hình.
- Web archive: triển khai WAR vào servlet container phù hợp, xác minh request cơ bản.
- Library: chạy consumer test biên dịch và gọi API public với JAR mới.

Một JAR tạo ra thành công không tự chứng minh mọi dependency runtime hoặc môi trường deploy vẫn tương thích.

## 14. Tổ chức thay đổi theo các commit dễ kiểm tra

Có thể chia migration thành những thay đổi nhỏ mà mỗi thay đổi có tiêu chí hoàn thành rõ:

**Thay đổi 1 — Dựng cấu trúc Ant:**

- Thêm `build.xml`, property, classpath và target `compile-main`.
- Không chuyển pipeline phát hành.
- Chứng minh có thể build từ checkout sạch, so sánh compiler contract.

**Thay đổi 2 — Chuyển test:**

- Thêm `compile-tests`, `test`, report và logic fail-fast.
- Mở rộng runner để thực thi toàn bộ suite thực tế.
- Chứng minh test thất bại chặn stage tiếp theo.

**Thay đổi 3 — Chuyển package:**

- Thêm `package`, `verify-package`, manifest/distribution cần thiết.
- So sánh tập entry, resource, dependency runtime và smoke test với build cũ.
- Lưu artifact Ant làm ứng viên, chưa tự động deploy.

**Thay đổi 4 — Chuyển CI chính:**

- Pin toolchain/dependency, bật clean Ant build/test/package.
- Đổi nguồn artifact phát hành sang Ant sau khi tiêu chí chấp nhận đều đạt.
- Theo dõi vài lần phát hành đầu và giữ đường rollback đã được xác định.

Nếu muốn tiến độ nhanh hơn, có thể gộp commit nhưng vẫn phải giữ khả năng xác minh **riêng từng giai đoạn**. Một PR thay toàn bộ build script cùng lúc sẽ khó khoanh vùng lỗi hơn nếu thiếu những điểm đối chiếu này.

## 15. Cách rollback và tránh phát hành hai kết quả khác nhau

Chuyển đổi hoàn chỉnh cần tính tới tình huống đầu ra Ant đi qua test cơ bản nhưng gặp lỗi ở hệ thống downstream. Hãy giữ một cơ chế rõ ràng để khôi phục pipeline cũ trong giai đoạn chuyển tiếp:

1. Gắn mỗi sản phẩm phát hành với commit nguồn, toolchain và pipeline tạo ra nó.
2. Chỉ một workflow hoặc job có quyền xuất bản tới môi trường chính thức.
3. Trong giai đoạn chạy song song, artifact từ Ant phải có tên hoặc nhãn rõ là **candidate**.
4. Nếu phát hiện lỗi, dừng publish đường Ant, chuyển lại artifact đã kiểm tra từ pipeline cũ theo quy trình của dự án.
5. Xác định nguyên nhân ở compile, test, package, dependency hoặc CI; cập nhật tiêu chí chấp nhận trước lần thử tiếp theo.

Rollback ở đây là thay đổi **đường build/phát hành**, không phải xóa toàn bộ lịch sử đổi mới. Không cần xóa source Ant khi rollback; giữ nó làm dữ liệu điều tra, nhưng đảm bảo build cũ không vô tình sử dụng các output do Ant đã sinh.

### Những việc không nên làm khi rollback

- Không để hai pipeline đồng thời tạo hoặc ghi đè artifact có cùng danh tính phát hành.
- Không khôi phục từ file build cũ chưa được xác minh, chỉ vì tên file trông giống.
- Không âm thầm bỏ test đang fail để kịp release.
- Không sửa manifest/cấu hình phát hành trực tiếp sau build mà không ghi lại nguồn và kết quả kiểm tra.
- Không đặt clean target xóa cả artifact bằng chứng hoặc directory đầu ra của pipeline khác.

## 16. Bài thực hành theo bốn vòng

### Vòng A — Chỉ chuyển compile

Tạo cấu trúc dự án phần 4, thêm `Greeter.java` và `build.xml`. Chạy:

```bash
ant clean compile-main
```

Kiểm tra `build/classes/example/Greeter.class` xuất hiện, còn `dist/demo-app.jar` chưa được tạo. Giải thích vì sao target compile không thực thi test.

### Vòng B — Đưa kiểm thử vào pipeline

Thêm `GreeterTest.java` và các JAR test đã xác minh. Chạy:

```bash
ant clean test
```

Sau khi test pass, sửa một expected string trong test cho sai và chạy lại. Lệnh phải kết thúc ở trạng thái lỗi. Hoàn nguyên test trước khi tiếp tục.

### Vòng C — Chuyển package

Chạy:

```bash
ant clean verify-package
jar tf dist/demo-app.jar
java -jar dist/demo-app.jar
```

Xác nhận có `Greeter.class` và `application.properties`, không có `GreeterTest.class`; ứng dụng in lời chào. Nếu kết quả khác, xác định bước gây lỗi: resource copy, classpath hoặc manifest.

### Vòng D — Đối chiếu với build cũ

Tạo hai snapshot độc lập, một từ công cụ hiện tại và một từ Ant. Lưu:

- Lệnh/compiler/JDK dùng cho mỗi phía.
- Danh sách class và resource của mỗi sản phẩm.
- Tổng số/nội dung test đã được thực thi.
- Tên artifact, entry JAR, manifest, SHA-256 và kết quả smoke test.
- Mọi khác biệt có giải thích và quyết định chấp nhận hoặc sửa.

Chỉ đánh dấu một stage **đã chuyển** khi có bằng chứng phù hợp, không dựa vào sự giống nhau của tên target.

### Câu hỏi tự kiểm tra

1. Vì sao chuyển compile, test và package trong các đợt riêng giúp xác định lỗi dễ hơn?
2. `ant compile-main` và `ant package` trong đồ thị ví dụ khác nhau ở những target nào được chạy?
3. Tại sao `compile-tests` thành công chưa đủ để kết luận test đã pass?
4. Tại sao `<java failonerror="true">` quan trọng với một test runner trả exit code khác 0 khi test lỗi?
5. Khi JAR mới khác checksum nhưng cùng nội dung entry, cần kiểm tra tiếp điều gì?
6. Vì sao thư mục output của build cũ và Ant phải độc lập khi đối chiếu?
7. Tại sao một JAR chạy tốt trên máy phát triển vẫn có thể thiếu dependency khi triển khai lên runner sạch?
8. Điều kiện nào phải đạt trước khi pipeline Ant được cấp quyền publish chính thức?

## 17. Tóm lược quy trình chuyển đổi

Chuyển build sang Apache Ant theo giai đoạn là quá trình bảo toàn **hành vi kỹ thuật**, không đơn thuần chuyển cú pháp lệnh. Bắt đầu bằng ghi nhận build hiện tại; tiếp theo chuyển riêng `compile-main`, `compile-tests/test` và `package` với đồ thị phụ thuộc rõ; cuối cùng so sánh sản phẩm và chạy thử theo đúng môi trường phát hành. Khi từng giai đoạn có bằng chứng đạt tiêu chí và CI fail đúng khi có lỗi, mới thay đường phát hành cũ bằng Ant.

Điều quan trọng nhất là mỗi lần chuyển một bước đều trả lời được: **đầu vào nào được sử dụng, đầu ra nào được tạo, điều kiện nào khiến bước thất bại và kết quả đã được đối chiếu với đường chuẩn ra sao?**

# Tạo chuỗi init, compile, test, jar và clean

Một build Ant thường được chia thành các target nhỏ, mỗi target đảm nhiệm một bước có tên rõ ràng. Với một ứng dụng Java, chuỗi cơ bản có thể gồm `init` để chuẩn bị thư mục, `compile` để biên dịch mã nguồn, `test` để chạy kiểm thử, `jar` để đóng gói và `clean` để xóa kết quả build cũ.

Mục tiêu của bài học là tạo được một `build.xml` hoàn chỉnh, hiểu thứ tự thực thi giữa các target và biết cách gọi từng bước hoặc toàn bộ quy trình từ terminal. Ví dụ sử dụng JUnit 4 để minh họa task test của Ant; phần cấu hình test có thể thay bằng runner phù hợp nếu dự án dùng JUnit 5.

## 1. Hiểu vai trò của từng target

Mỗi target nên đại diện cho một công việc dễ mô tả và có thể gọi độc lập khi cần.

| Target | Trách nhiệm | Kết quả chính |
|---|---|---|
| `init` | Tạo các thư mục đầu ra cần thiết | `build/classes`, `build/test-classes`, `build/reports`, `dist` |
| `compile` | Biên dịch mã nguồn chính | Các file `.class` trong `build/classes` |
| `compile-test` | Biên dịch mã nguồn kiểm thử | Các file `.class` trong `build/test-classes` |
| `test` | Chạy bộ kiểm thử sau khi đã compile | Kết quả test và báo cáo trong `build/reports` |
| `jar` | Đóng gói class chính thành JAR | `dist/hello-app.jar` |
| `clean` | Xóa các thư mục do build tạo ra | Output cũ được loại bỏ |

`compile-test` là target hỗ trợ để tách riêng việc biên dịch test. Nhờ vậy, target `test` tập trung vào việc thực thi kiểm thử, còn lỗi cú pháp hoặc lỗi biên dịch trong test được phát hiện ở bước trước.

Thông thường, `jar` chỉ được chạy khi test thành công. Nếu một test thất bại, Ant dừng build và không tạo artifact phát hành mới. `clean` có vai trò khác: nó xóa output và không phải điều kiện bắt buộc của mỗi lần build.

## 2. Cấu trúc dự án mẫu

Tạo một dự án nhỏ với cấu trúc sau:

```text
hello-app/
├── build.xml
├── lib/
│   ├── junit-4.13.2.jar
│   └── hamcrest-core-1.3.jar
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/example/App.java
│   └── test/
│       └── java/
│           └── com/example/AppTest.java
├── build/                 # Ant tạo khi chạy init
│   ├── classes/
│   ├── test-classes/
│   └── reports/
└── dist/                  # Ant tạo khi chạy init
```

`src/main/java` chứa mã nguồn ứng dụng. `src/test/java` chứa mã nguồn kiểm thử. `lib` chứa thư viện test được dùng trong ví dụ. Hai thư mục `build` và `dist` là output được tạo tự động, không phải nơi lưu source.

Ví dụ này dùng JUnit 4.13.2 và Hamcrest 1.3. Đặt hai JAR tương ứng trong `lib` trước khi chạy build. Task `<junit>` còn cần task library `ant-junit` có mặt trên classpath của chính Ant, thường được cài trong thư mục `ANT_HOME/lib`. Hai JAR JUnit/Hamcrest của dự án và JAR `ant-junit` của Ant có hai vai trò khác nhau.

## 3. Tạo mã nguồn và test mẫu

Tạo `src/main/java/com/example/App.java`:

```java
package com.example;

public class App {

    public int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        App app = new App();
        System.out.println("2 + 3 = " + app.add(2, 3));
    }
}
```

Tạo `src/test/java/com/example/AppTest.java`:

```java
package com.example;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class AppTest {

    @Test
    public void addsTwoNumbers() {
        App app = new App();

        assertEquals(5, app.add(2, 3));
    }
}
```

Test kiểm tra hành vi của lớp `App`. Khi thay đổi logic của `add`, bước test sẽ giúp phát hiện trường hợp kết quả không còn đúng như mong đợi.

## 4. Khai báo property và classpath

Đầu file `build.xml`, khai báo tên ứng dụng, lớp chính và các đường dẫn:

```xml
<project name="hello-app" default="build" basedir=".">
    <property name="app.name" value="hello-app"/>
    <property name="main.class" value="com.example.App"/>

    <property name="java.source" value="11"/>
    <property name="java.target" value="11"/>

    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="src.test" location="${basedir}/src/test/java"/>
    <property name="lib.dir" location="${basedir}/lib"/>

    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <!-- Các target sẽ được khai báo bên dưới. -->
</project>
```

`basedir` xác định thư mục gốc để các đường dẫn tương đối được tính nhất quán. Thuộc tính `location` dùng để khai báo đường dẫn và Ant chuẩn hóa giá trị thành đường dẫn tuyệt đối. Các property của Ant có tính bất biến: khi một property đã được đặt, lần khai báo sau thường không ghi đè được giá trị cũ. Vì vậy, hãy khai báo giá trị mặc định có chủ đích và dùng tham số dòng lệnh để truyền giá trị cần thay đổi.

Classpath của test cần chứa class ứng dụng, class test và thư viện JUnit/Hamcrest:

```xml
<path id="test.classpath">
    <pathelement location="${classes.dir}"/>
    <pathelement location="${test.classes.dir}"/>
    <fileset dir="${lib.dir}">
        <include name="junit-*.jar"/>
        <include name="hamcrest-*.jar"/>
    </fileset>
</path>
```

`path` gom nhiều phần tử classpath thành một reference có `id`. Các task có thể dùng lại reference bằng `refid`, nhờ đó cấu hình classpath được tập trung ở một chỗ. Nếu dự án có dependency riêng cho mã nguồn chính, hãy tạo thêm `main.classpath` và chỉ đưa các dependency cần thiết vào đó; ví dụ hiện tại không có thư viện runtime bên ngoài.

## 5. Tạo target init

Target `init` chuẩn bị những thư mục mà các bước sau sẽ ghi file:

```xml
<target name="init" description="Create build output directories">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${test.classes.dir}"/>
    <mkdir dir="${reports.dir}"/>
    <mkdir dir="${dist.dir}"/>
</target>
```

Task `<mkdir>` tạo thư mục nếu thư mục chưa tồn tại. Nếu thư mục đã có, task không làm hỏng output hiện tại. Vì vậy `init` có thể được gọi trước nhiều bước mà không cần tự kiểm tra thư mục bằng các câu lệnh điều kiện.

Không đặt source vào các thư mục do `init` tạo. Output được tách riêng để `clean` có thể xóa an toàn các kết quả build mà không đụng đến mã nguồn.

## 6. Tạo target compile

Target `compile` phụ thuộc `init`, nên Ant luôn chuẩn bị thư mục trước khi gọi compiler:

```xml
<target name="compile" depends="init"
        description="Compile main Java sources">
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           encoding="UTF-8"
           source="${java.source}"
           target="${java.target}"
           includeantruntime="false"/>
</target>
```

Task `<javac>` tìm các file Java trong `src.main` và ghi bytecode vào `classes.dir`. `encoding` xác định encoding của source. `source` và `target` minh họa cách đặt mức ngôn ngữ và bytecode; cần chọn giá trị phù hợp với JDK mà dự án hỗ trợ. Với JDK mới, có thể cân nhắc thuộc tính `release` nếu phiên bản Ant và compiler đang dùng hỗ trợ.

`includeantruntime="false"` ngăn thư viện nội bộ của Ant bị thêm vào classpath biên dịch một cách vô tình. Nếu ứng dụng dùng thư viện ngoài, thêm classpath của ứng dụng vào task `javac`:

```xml
<javac srcdir="${src.main}"
       destdir="${classes.dir}"
       includeantruntime="false">
    <classpath refid="main.classpath"/>
</javac>
```

Ant có thể chỉ biên dịch lại source đã thay đổi dựa trên timestamp. Tuy nhiên, nếu source bị xóa hoặc cấu trúc output thay đổi, class cũ có thể còn sót lại. Một lần build sạch giúp xác nhận kết quả không phụ thuộc vào file tồn dư.

## 7. Tạo target compile-test

Test cần class ứng dụng đã biên dịch và các thư viện test. Vì vậy `compile-test` phụ thuộc `compile`:

```xml
<target name="compile-test" depends="compile"
        description="Compile test sources">
    <javac srcdir="${src.test}"
           destdir="${test.classes.dir}"
           encoding="UTF-8"
           source="${java.source}"
           target="${java.target}"
           includeantruntime="false">
        <classpath refid="test.classpath"/>
    </javac>
</target>
```

Thứ tự thực hiện đến đây là:

```text
init
  └── compile
        └── compile-test
```

Khi gọi `ant compile-test`, Ant lần lượt thực hiện các dependency trước rồi mới chạy target được yêu cầu. Người dùng không cần gọi riêng `init` và `compile` trước.

## 8. Tạo target test

Với JUnit 4, Ant cung cấp task `<junit>` thông qua thư viện tùy chọn `ant-junit`. Target `test` có thể viết như sau:

```xml
<target name="test" depends="compile-test"
        description="Run unit tests">
    <junit printsummary="yes"
           haltonfailure="yes"
           haltonerror="yes"
           fork="true">
        <classpath refid="test.classpath"/>
        <formatter type="plain" usefile="false"/>
        <formatter type="xml"/>
        <batchtest todir="${reports.dir}">
            <fileset dir="${test.classes.dir}">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Các thuộc tính quan trọng:

- `printsummary="yes"` in tổng kết test ra log.
- `haltonfailure="yes"` làm build thất bại khi có assertion thất bại.
- `haltonerror="yes"` làm build thất bại khi test gặp lỗi thực thi.
- `fork="true"` chạy test trong JVM riêng, giúp tách biệt tiến trình test với tiến trình Ant.
- `formatter` chọn cách xuất kết quả. Formatter `plain` hiển thị trên console; formatter `xml` tạo báo cáo trong `reports.dir`.
- `batchtest` tìm các class có tên khớp `**/*Test.class` trong thư mục test đã biên dịch.

Để target này chạy được, cần có JUnit và Hamcrest trong `lib`, đồng thời task library `ant-junit` phải được Ant nạp. Nếu Ant báo không tìm thấy task `junit` hoặc class `JUnitTask`, hãy kiểm tra phần cài đặt optional task của Ant. Nếu task chạy nhưng không tìm thấy `org.junit.Test`, hãy kiểm tra classpath của dự án.

Ví dụ trên dùng JUnit 4. Với JUnit 5, cần một runner tương thích như JUnit Platform Console Launcher và gọi runner bằng task `<java>` hoặc cấu hình một integration phù hợp. Không nên giả định task `<junit>` cổ điển tự động chạy được mọi test JUnit 5.

## 9. Tạo target jar

Target `jar` phụ thuộc `test`, vì vậy artifact chỉ được tạo sau khi mã nguồn và test đều biên dịch, test chạy thành công:

```xml
<target name="jar" depends="test"
        description="Package the application JAR">
    <jar destfile="${dist.dir}/${app.name}.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Main-Class" value="${main.class}"/>
        </manifest>
    </jar>
</target>
```

Task `<jar>` đóng gói nội dung trong `classes.dir`. Các class test nằm ở `test.classes.dir`, do đó không bị đưa vào artifact ứng dụng. Manifest khai báo `Main-Class`, cho phép JVM biết lớp chứa phương thức `main` khi chạy bằng `java -jar`.

Ví dụ này không đóng gói thư viện bên ngoài vào JAR. Nếu ứng dụng có dependency runtime, cần phân phối các JAR đó cùng ứng dụng và khai báo classpath trong manifest, hoặc chọn cách đóng gói phù hợp như tạo fat JAR bằng công cụ chuyên dụng. Chỉ có `Main-Class` chưa đủ để một JAR chạy độc lập khi thiếu dependency.

## 10. Tạo target clean

Target `clean` xóa output do build tạo ra:

```xml
<target name="clean" description="Remove generated build output">
    <delete dir="${build.dir}"/>
    <delete dir="${dist.dir}"/>
</target>
```

`clean` không phụ thuộc `init`, `compile`, `test` hay `jar`. Khi chạy `ant clean`, Ant chỉ xóa các thư mục output đã khai báo. Không trỏ task `<delete>` vào `src`, `lib` hoặc thư mục gốc của dự án.

Giữ `clean` độc lập có hai lợi ích. Người dùng có thể dọn output mà không kích hoạt build lại, và có thể kết hợp `clean` với target build trong cùng một lệnh theo đúng thứ tự mong muốn.

## 11. Ghép thành build.xml hoàn chỉnh

File dưới đây kết hợp các phần đã tạo. Target mặc định là `build`, target này phụ thuộc `jar`; chuỗi dependency đảm bảo thứ tự `init` → `compile` → `compile-test` → `test` → `jar`.

```xml
<project name="hello-app" default="build" basedir=".">
    <property name="app.name" value="hello-app"/>
    <property name="main.class" value="com.example.App"/>
    <property name="java.source" value="11"/>
    <property name="java.target" value="11"/>

    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="src.test" location="${basedir}/src/test/java"/>
    <property name="lib.dir" location="${basedir}/lib"/>

    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <fileset dir="${lib.dir}">
            <include name="junit-*.jar"/>
            <include name="hamcrest-*.jar"/>
        </fileset>
    </path>

    <target name="init" description="Create build output directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init"
            description="Compile main Java sources">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               source="${java.source}"
               target="${java.target}"
               includeantruntime="false"/>
    </target>

    <target name="compile-test" depends="compile"
            description="Compile test sources">
        <javac srcdir="${src.test}"
               destdir="${test.classes.dir}"
               encoding="UTF-8"
               source="${java.source}"
               target="${java.target}"
               includeantruntime="false">
            <classpath refid="test.classpath"/>
        </javac>
    </target>

    <target name="test" depends="compile-test"
            description="Run unit tests">
        <junit printsummary="yes"
               haltonfailure="yes"
               haltonerror="yes"
               fork="true">
            <classpath refid="test.classpath"/>
            <formatter type="plain" usefile="false"/>
            <formatter type="xml"/>
            <batchtest todir="${reports.dir}">
                <fileset dir="${test.classes.dir}">
                    <include name="**/*Test.class"/>
                </fileset>
            </batchtest>
        </junit>
    </target>

    <target name="jar" depends="test"
            description="Package the application JAR">
        <jar destfile="${dist.dir}/${app.name}.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
            </manifest>
        </jar>
    </target>

    <target name="build" depends="jar"
            description="Compile, test and package the application"/>

    <target name="clean" description="Remove generated build output">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="rebuild" depends="clean,build"
            description="Clean and build from scratch"/>
</project>
```

Trong target `rebuild`, danh sách dependency `clean,build` thể hiện thứ tự: dọn output trước, sau đó chạy chuỗi build. Target `build` vẫn có thể được gọi riêng để tận dụng cơ chế biên dịch cập nhật của Ant.

## 12. Đọc đồ thị dependency và thứ tự chạy

Các quan hệ phụ thuộc của ví dụ:

```text
build
  └── jar
        └── test
              └── compile-test
                    └── compile
                          └── init

rebuild
  ├── clean
  └── build
```

Mũi tên trong sơ đồ thể hiện target phía trên phụ thuộc vào target phía dưới. Khi một target được gọi, Ant thực hiện các dependency trước rồi mới thực hiện nội dung của target đó. Trong một lần gọi build, một target chỉ được thực hiện một lần dù nó được tham chiếu từ nhiều nhánh dependency.

`clean` không nằm trong dependency của `build`, nên gọi `ant build` không tự xóa output. Nếu thêm `clean` vào dependency của `build`, mọi lần build đều bắt đầu bằng xóa toàn bộ output và mất lợi ích của compile tăng dần. Chỉ dùng `rebuild` khi cần xác minh build từ trạng thái sạch.

## 13. Chạy từng target từ terminal

Mở terminal tại thư mục chứa `build.xml`.

| Lệnh | Tác dụng |
|---|---|
| `ant -p` | Liệt kê target và mô tả |
| `ant init` | Tạo thư mục đầu ra |
| `ant compile` | Chạy `init` rồi biên dịch source chính |
| `ant compile-test` | Chạy chuỗi chuẩn bị, compile và biên dịch test |
| `ant test` | Chạy toàn bộ dependency đến compile-test rồi thực thi test |
| `ant jar` | Chạy test thành công rồi tạo JAR |
| `ant build` | Chạy target mặc định tổng hợp compile, test và package |
| `ant clean` | Xóa `build` và `dist` |
| `ant clean build` | Chạy clean trước, sau đó build |
| `ant rebuild` | Gọi target tổng hợp clean rồi build |

Nếu không ghi target, lệnh `ant` gọi target được khai báo trong thuộc tính `default` của `<project>`. Với file mẫu này, `ant` tương đương `ant build`.

Có thể truyền property khi chạy:

```bash
ant -Djava.source=17 -Djava.target=17 rebuild
```

Giá trị truyền từ dòng lệnh cho phép chọn mức Java mà không sửa `build.xml`. Chỉ dùng giá trị mà JDK và phiên bản Ant hiện tại hỗ trợ.

## 14. Quan sát output sau mỗi bước

Sau `ant init`, các thư mục output được tạo nhưng chưa có class. Sau `ant compile`, `build/classes` chứa `com/example/App.class`. Sau `ant compile-test`, `build/test-classes` có `com/example/AppTest.class`. Sau `ant test`, log thể hiện số test chạy và báo cáo XML nằm trong `build/reports`. Sau `ant jar`, file `dist/hello-app.jar` được tạo.

Có thể kiểm tra nội dung JAR bằng công cụ JDK:

```bash
jar tf dist/hello-app.jar
```

Kết quả cần có `com/example/App.class` và `META-INF/MANIFEST.MF`. Không nên có `AppTest.class` trong JAR phát hành.

Để kiểm tra manifest và chạy ứng dụng:

```bash
java -jar dist/hello-app.jar
```

Với ví dụ không dùng dependency runtime, chương trình sẽ in kết quả phép cộng. Nếu thêm dependency ngoài, cần bảo đảm các thư viện đó có mặt khi chạy JAR.

Sau `ant clean`, hai thư mục `build` và `dist` không còn. Source trong `src` và thư viện trong `lib` vẫn được giữ nguyên. Chạy `ant build` sau đó sẽ tạo lại output từ đầu.

## 15. Những lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `srcdir` không tồn tại | Cấu trúc source chưa được tạo hoặc property sai | Kiểm tra `src.main` và `src.test` |
| `package org.junit does not exist` | JUnit chưa có trong classpath biên dịch test | Kiểm tra JAR trong `lib` và `test.classpath` |
| Không tìm thấy task `junit` | Ant chưa nạp optional task library `ant-junit` | Kiểm tra cài đặt Ant và classpath của Ant |
| Không tìm thấy `JUnitTask` | Thiếu JAR chứa implementation task | Bổ sung/cấu hình `ant-junit` tương thích với phiên bản Ant |
| Test fail nhưng JAR vẫn được tạo | Target test không truyền lỗi về Ant hoặc jar không phụ thuộc test | Dùng `haltonfailure`, `haltonerror` và `depends="test"` |
| JAR thiếu class chính | `javac` chưa biên dịch source hoặc `basedir` của jar sai | Kiểm tra `classes.dir` và nội dung output |
| `java -jar` báo không tìm thấy class | Manifest sai hoặc thiếu dependency runtime | Kiểm tra `Main-Class` và classpath khi chạy |
| Output cũ vẫn xuất hiện sau khi xóa source | Class cũ còn trong thư mục build | Chạy `ant clean build` để tạo lại output sạch |

Khi debug, chạy riêng target gây lỗi và quan sát target dependency mà Ant thực hiện. Có thể tăng log bằng:

```bash
ant -verbose test
ant -debug jar
ant -diagnostics
```

`-verbose` cung cấp thêm thông tin về task và target; `-debug` hiển thị log chi tiết hơn; `-diagnostics` cung cấp thông tin môi trường Ant. Hãy kiểm tra lỗi đầu tiên trong log vì các lỗi phía sau có thể chỉ là hệ quả của bước trước thất bại.

## 16. Bài tập thực hành

1. Tạo dự án theo cấu trúc mẫu và viết `App.java` có một phương thức xử lý đơn giản.
2. Tạo target `init`, sau đó gọi `ant init` và xác nhận các thư mục output đã xuất hiện.
3. Viết target `compile` phụ thuộc `init`; gọi `ant compile` và kiểm tra file `.class`.
4. Thêm một test JUnit, tạo `compile-test` phụ thuộc `compile` và tạo target `test` phụ thuộc `compile-test`.
5. Cố tình làm assertion sai để xác nhận build thất bại và target `jar` không chạy.
6. Sửa test cho đúng, gọi `ant jar` và kiểm tra manifest cùng nội dung JAR.
7. Gọi `ant clean`, xác nhận output bị xóa nhưng source vẫn còn; cuối cùng gọi `ant rebuild`.

Khi hoàn thành, người học cần giải thích được vì sao `jar` phụ thuộc `test`, vì sao `test` phụ thuộc `compile-test`, vì sao `compile` phụ thuộc `init` và vì sao `clean` thường đứng riêng. Đây là nền tảng để mở rộng build script với resource, dependency ngoài, nhiều module và pipeline CI.

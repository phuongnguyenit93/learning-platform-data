# Tách đầu ra mã chính, mã kiểm thử và tài nguyên trong Apache Ant

Một dự án Java thường có ít nhất hai nhóm mã nguồn: mã chính tạo nên ứng dụng và mã kiểm thử dùng để xác minh ứng dụng. Ngoài file `.java`, dự án còn có tài nguyên như `.properties`, XML, JSON, template, ảnh hoặc file dữ liệu. Khi biên dịch bằng Apache Ant, nên đưa từng nhóm đầu ra vào vị trí riêng để tránh lẫn class kiểm thử vào artifact phát hành, tránh resource test ghi đè resource production và giúp classpath của từng bước thể hiện đúng mục đích.

Trong bài này, ta dùng cấu trúc đầu ra dưới `build/` như sau:

```text
project/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/             # Mã nguồn ứng dụng
│   │   └── resources/        # Tài nguyên ứng dụng
│   └── test/
│       ├── java/             # Mã nguồn kiểm thử
│       └── resources/        # Tài nguyên dành riêng cho test
├── lib/
│   ├── main/                 # Thư viện cần khi biên dịch/chạy ứng dụng
│   └── test/                 # Thư viện test, ví dụ JUnit
└── build/
    ├── classes/
    │   ├── main/             # .class của ứng dụng
    │   └── test/             # .class của kiểm thử
    ├── resources/
    │   ├── main/             # Tài nguyên ứng dụng đã copy
    │   └── test/             # Tài nguyên test đã copy
    ├── reports/              # Báo cáo test
    └── libs/                 # JAR phát hành
```

Các thư mục trong `build/` là đầu ra sinh tự động. Có thể xóa và tạo lại chúng mà không làm mất source code hoặc tài nguyên do lập trình viên quản lý.

## 1. Vì sao phải tách đầu ra?

### Mã chính và mã kiểm thử có mục đích khác nhau

Mã chính (`src/main/java`) là nội dung cần đưa vào ứng dụng. Mã kiểm thử (`src/test/java`) chỉ phục vụ quá trình kiểm tra. Nếu hai nhóm được biên dịch vào cùng một thư mục, task đóng gói có thể vô tình đưa test class, mock hoặc fixture vào JAR production.

Ví dụ, nếu cả `Main.java` và `MainTest.java` được biên dịch vào `build/classes`, task `jar` dùng toàn bộ thư mục này có nguy cơ đóng gói cả `MainTest.class`. Điều đó làm artifact phát hành chứa mã không cần thiết và có thể kéo theo dependency kiểm thử.

### Tài nguyên ứng dụng và tài nguyên test cũng khác nhau

Tài nguyên trong `src/main/resources` được ứng dụng sử dụng khi chạy. Tài nguyên trong `src/test/resources` chỉ dành cho test, chẳng hạn dữ liệu mẫu, file cấu hình test hoặc fixture. Không nên copy cả hai nhóm vào cùng thư mục production.

### Lợi ích của việc tách riêng

- JAR production chỉ chứa mã chính và tài nguyên ứng dụng.
- Test classpath có thể thêm thư viện JUnit, Mockito hoặc công cụ kiểm thử mà không làm chúng lọt vào artifact production.
- Tài nguyên test có thể dùng cùng tên tương đối với tài nguyên chính để ghi đè có chủ đích trong môi trường test.
- `clean` có thể xóa toàn bộ đầu ra sinh ra mà không ảnh hưởng source.
- Khi một bước thất bại, dễ xác định đầu ra của bước đó nằm ở đâu.
- IDE và CI có thể dùng chung một cấu trúc source/output quen thuộc.

## 2. Khai báo các thư mục đầu ra bằng property

Đặt các đường dẫn ở đầu buildfile giúp tất cả target sử dụng cùng một quy ước. Không viết rải rác các chuỗi `build/classes/main` hoặc `build/resources/test` trong nhiều task.

```xml
<property name="src.main.java" location="src/main/java"/>
<property name="src.main.resources" location="src/main/resources"/>
<property name="src.test.java" location="src/test/java"/>
<property name="src.test.resources" location="src/test/resources"/>

<property name="build.dir" location="build"/>
<property name="main.classes.dir" location="${build.dir}/classes/main"/>
<property name="test.classes.dir" location="${build.dir}/classes/test"/>
<property name="main.resources.dir" location="${build.dir}/resources/main"/>
<property name="test.resources.dir" location="${build.dir}/resources/test"/>
<property name="test.reports.dir" location="${build.dir}/reports"/>
<property name="libs.dir" location="${build.dir}/libs"/>
```

Các property này mô tả rõ nguồn và đích:

| Nhóm | Source | Build output |
|---|---|---|
| Mã chính | `src/main/java` | `build/classes/main` |
| Mã kiểm thử | `src/test/java` | `build/classes/test` |
| Tài nguyên chính | `src/main/resources` | `build/resources/main` |
| Tài nguyên test | `src/test/resources` | `build/resources/test` |
| Báo cáo test | Kết quả chạy kiểm thử | `build/reports` |
| JAR phát hành | Class và resource chính | `build/libs` |

Không bắt buộc phải dùng đúng tên thư mục này. Điều quan trọng là mã chính, mã test, resource chính và resource test có các output directory riêng, được sử dụng nhất quán trong compile, test và package.

## 3. Tạo thư mục đầu ra

Task `mkdir` tạo thư mục nếu chưa tồn tại. Có thể gom việc chuẩn bị cấu trúc vào target `init`:

```xml
<target name="init">
    <mkdir dir="${main.classes.dir}"/>
    <mkdir dir="${test.classes.dir}"/>
    <mkdir dir="${main.resources.dir}"/>
    <mkdir dir="${test.resources.dir}"/>
    <mkdir dir="${test.reports.dir}"/>
    <mkdir dir="${libs.dir}"/>
</target>
```

Ở đây, `main.resources.dir` và `test.resources.dir` là các thư mục đầu ra dưới `build/`, không phải thư mục nguồn. Vì vậy, tên property cần thể hiện rõ vai trò; trong dự án lớn, có thể đặt tên cụ thể hơn như `build.main.resources.dir` và `build.test.resources.dir` để tránh nhầm với source path.

`mkdir` có thể được gọi lặp lại. Nếu thư mục đã tồn tại, task không cần tạo lại nội dung bên trong. Các target biên dịch, copy resource và đóng gói nên phụ thuộc vào `init` hoặc một target nền tảng tương đương.

## 4. Biên dịch riêng mã chính

Task `javac` nhận `srcdir` là thư mục source và `destdir` là nơi ghi file `.class`. Với mã chính, `destdir` phải là thư mục `build/classes/main`.

```xml
<path id="main.compile.classpath">
    <fileset dir="lib/main" includes="**/*.jar"/>
</path>

<target name="compile-main" depends="init"
        description="Biên dịch mã nguồn ứng dụng">
    <javac srcdir="${src.main.java}"
           destdir="${main.classes.dir}"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath refid="main.compile.classpath"/>
    </javac>
</target>
```

`javac` chỉ ghi class vào `main.classes.dir`. Các thư viện ứng dụng được khai báo trong `main.compile.classpath`. Thuộc tính `includeantruntime="false"` tránh tự động thêm Ant runtime vào classpath biên dịch ứng dụng.

Nếu ứng dụng không có dependency ngoài, có thể bỏ nested `classpath`. Nếu có thư viện, hãy đưa đúng JAR cần thiết vào `lib/main`; không đưa JUnit hoặc thư viện chỉ dành cho test vào classpath mã chính.

## 5. Copy riêng tài nguyên chính

`javac` chỉ biên dịch Java source thành class. Nó không tự copy các file `.properties`, XML, JSON, template hoặc ảnh từ `src/main/resources`. Cần dùng task `copy` để đưa các tài nguyên này vào thư mục output tương ứng.

```xml
<target name="copy-main-resources" depends="init"
        description="Copy tài nguyên ứng dụng">
    <copy todir="${main.resources.dir}">
        <fileset dir="${src.main.resources}"/>
    </copy>
</target>
```

Ví dụ, file `src/main/resources/config/app.yml` sẽ được đặt tại `build/resources/main/config/app.yml`. Cấu trúc tương đối bên dưới source root được giữ lại.

Khi đóng gói JAR, nội dung của `main.classes.dir` và `main.resources.dir` sẽ được ghép vào cùng một archive. Điều này giúp ứng dụng tìm resource qua classpath như `ClassLoader.getResource(...)` hoặc `Class.getResource(...)`.

## 6. Biên dịch riêng mã kiểm thử

Mã test thường tham chiếu đến class chính, đồng thời sử dụng framework kiểm thử. Vì vậy test compile classpath cần chứa:

- `build/classes/main`: class đã biên dịch của ứng dụng.
- `lib/main`: dependency cần thiết để biên dịch class chính và các API mà test sử dụng.
- `lib/test`: thư viện test như JUnit và các thư viện hỗ trợ.

Khai báo classpath và target:

```xml
<path id="test.compile.classpath">
    <pathelement location="${main.classes.dir}"/>
    <path refid="main.compile.classpath"/>
    <fileset dir="lib/test" includes="**/*.jar"/>
</path>

<target name="compile-test" depends="compile-main"
        description="Biên dịch mã kiểm thử">
    <javac srcdir="${src.test.java}"
           destdir="${test.classes.dir}"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath refid="test.compile.classpath"/>
    </javac>
</target>
```

Điểm quan trọng là `destdir` của test khác `destdir` của main. `compile-test` phụ thuộc `compile-main` để class chính đã có sẵn trên classpath. Nếu test source tham chiếu đến resource lúc compile thì cần xem lại thiết kế; thông thường resource được đọc ở runtime, không phải đầu vào của javac.

## 7. Copy riêng tài nguyên kiểm thử

Test resources có thể chứa file dữ liệu mẫu, JSON request, XML fixture, file cấu hình test hoặc dữ liệu giả lập. Copy chúng vào `build/resources/test`:

```xml
<target name="copy-test-resources" depends="init"
        description="Copy tài nguyên kiểm thử">
    <copy todir="${test.resources.dir}">
        <fileset dir="${src.test.resources}"/>
    </copy>
</target>
```

Không copy test resources vào `build/resources/main`. Nếu làm vậy, resource test có thể bị đưa vào JAR production hoặc làm thay đổi cấu hình ứng dụng khi chạy ngoài môi trường test.

Khi test cần resource cùng tên với resource chính để thay thế cấu hình, hãy đặt test resource ở `build/resources/test` và sắp xếp classpath runtime để thư mục test đứng trước thư mục main. Việc ghi đè lúc này là hành vi có chủ đích trong môi trường test.

## 8. Classpath khi chạy test

Classpath biên dịch test và classpath chạy test thường gần giống nhau, nhưng cần có đủ các đầu ra và tài nguyên mà test sử dụng. Có thể khai báo riêng runtime classpath:

```xml
<path id="test.runtime.classpath">
    <pathelement location="${test.classes.dir}"/>
    <pathelement location="${test.resources.dir}"/>
    <pathelement location="${main.classes.dir}"/>
    <pathelement location="${main.resources.dir}"/>
    <path refid="main.compile.classpath"/>
    <fileset dir="lib/test" includes="**/*.jar"/>
</path>
```

Thứ tự các phần tử classpath có ý nghĩa khi có nhiều resource cùng tên. Trong ví dụ, test classes và test resources đứng trước main classes và main resources. Nếu `src/test/resources/config/app.yml` và `src/main/resources/config/app.yml` cùng có mặt, classloader tìm thấy bản test trước. Hãy dùng quy tắc này có chủ đích và tránh trùng resource không cần thiết.

Ví dụ chạy một test class bằng JUnit 4 `JUnitCore`: 

```xml
<target name="test" depends="compile-test,copy-main-resources,copy-test-resources"
        description="Chạy unit test">
    <mkdir dir="${test.reports.dir}"/>
    <java classname="org.junit.runner.JUnitCore"
          fork="true"
          failonerror="true">
        <classpath refid="test.runtime.classpath"/>
        <arg value="com.example.service.InventoryServiceTest"/>
    </java>
</target>
```

Ví dụ cần JUnit 4 và dependency hỗ trợ tương ứng trong `lib/test`. `failonerror="true"` bảo đảm tiến trình test trả mã lỗi khác 0 sẽ làm Ant build thất bại. Nếu dự án có nhiều test class, có thể tạo danh sách class hoặc tích hợp test runner phù hợp với quy ước dự án.

## 9. Đóng gói chỉ mã chính và tài nguyên chính

JAR phát hành nên được tạo từ hai đầu ra main. Không đưa `test.classes.dir` hoặc `test.resources.dir` vào task `jar`.

```xml
<target name="package" depends="compile-main,copy-main-resources"
        description="Đóng gói ứng dụng chính thành JAR">
    <jar destfile="${libs.dir}/inventory-app.jar">
        <fileset dir="${main.classes.dir}"/>
        <fileset dir="${main.resources.dir}"/>
        <manifest>
            <attribute name="Main-Class" value="com.example.Main"/>
        </manifest>
    </jar>
</target>
```

Task `jar` nhận hai FileSet: một chứa `.class`, một chứa resource main. Kết quả là class và resource cùng nằm ở root của JAR theo cấu trúc tương đối của từng FileSet. Các file test vẫn nằm ngoài artifact.

Để kiểm tra nội dung JAR, có thể dùng lệnh JDK:

```bash
jar tf build/libs/inventory-app.jar
```

Trong danh sách kết quả, nên thấy các package class ứng dụng và resource production. Không nên thấy `*Test.class`, dữ liệu fixture hoặc file cấu hình chỉ dành cho test.

## 10. Ví dụ buildfile hoàn chỉnh

Giả sử dự án có cấu trúc:

```text
project/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/Main.java
│   │   └── resources/config/app.properties
│   └── test/
│       ├── java/com/example/MainTest.java
│       └── resources/config/app.properties
└── lib/
    ├── main/
    └── test/
        ├── junit-4.13.2.jar
        └── hamcrest-core-1.3.jar
```

Buildfile:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="separated-output" default="test" basedir=".">

    <property name="src.main.java" location="src/main/java"/>
    <property name="src.main.resources" location="src/main/resources"/>
    <property name="src.test.java" location="src/test/java"/>
    <property name="src.test.resources" location="src/test/resources"/>

    <property name="build.dir" location="build"/>
    <property name="main.classes.dir" location="${build.dir}/classes/main"/>
    <property name="test.classes.dir" location="${build.dir}/classes/test"/>
    <property name="main.resources.dir" location="${build.dir}/resources/main"/>
    <property name="test.resources.dir" location="${build.dir}/resources/test"/>
    <property name="libs.dir" location="${build.dir}/libs"/>

    <path id="main.compile.classpath">
        <fileset dir="lib/main" includes="**/*.jar"/>
    </path>

    <path id="test.compile.classpath">
        <pathelement location="${main.classes.dir}"/>
        <path refid="main.compile.classpath"/>
        <fileset dir="lib/test" includes="**/*.jar"/>
    </path>

    <path id="test.runtime.classpath">
        <pathelement location="${test.classes.dir}"/>
        <pathelement location="${test.resources.dir}"/>
        <pathelement location="${main.classes.dir}"/>
        <pathelement location="${main.resources.dir}"/>
        <path refid="main.compile.classpath"/>
        <fileset dir="lib/test" includes="**/*.jar"/>
    </path>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="init">
        <mkdir dir="${main.classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${main.resources.dir}"/>
        <mkdir dir="${test.resources.dir}"/>
        <mkdir dir="${libs.dir}"/>
    </target>

    <target name="compile-main" depends="init">
        <javac srcdir="${src.main.java}"
               destdir="${main.classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="main.compile.classpath"/>
        </javac>
    </target>

    <target name="copy-main-resources" depends="init">
        <copy todir="${main.resources.dir}">
            <fileset dir="${src.main.resources}"/>
        </copy>
    </target>

    <target name="compile-test" depends="compile-main">
        <javac srcdir="${src.test.java}"
               destdir="${test.classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="test.compile.classpath"/>
        </javac>
    </target>

    <target name="copy-test-resources" depends="init">
        <copy todir="${test.resources.dir}">
            <fileset dir="${src.test.resources}"/>
        </copy>
    </target>

    <target name="test" depends="compile-test,copy-main-resources,copy-test-resources">
        <java classname="org.junit.runner.JUnitCore"
              fork="true"
              failonerror="true">
            <classpath refid="test.runtime.classpath"/>
            <arg value="com.example.MainTest"/>
        </java>
    </target>

    <target name="package" depends="compile-main,copy-main-resources">
        <jar destfile="${libs.dir}/inventory-app.jar">
            <fileset dir="${main.classes.dir}"/>
            <fileset dir="${main.resources.dir}"/>
            <manifest>
                <attribute name="Main-Class" value="com.example.Main"/>
            </manifest>
        </jar>
    </target>

</project>
```

Buildfile trên giữ bốn nhóm output độc lập. `test` chỉ cần main/test class và resource tương ứng trên runtime classpath; `package` chỉ ghép output main. Target `clean` xóa toàn bộ thư mục build để tránh class hoặc resource cũ còn sót lại.

## 11. Những lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Biên dịch main và test vào cùng `destdir` | Test class có thể lọt vào JAR production | Dùng hai output directory riêng |
| Copy cả `src/test/resources` vào output main | Fixture hoặc cấu hình test lọt vào ứng dụng | Copy test resource vào output test riêng |
| Đóng gói toàn bộ thư mục `build/` | JAR có thể chứa class test, report hoặc file tạm | Chỉ đưa main classes và main resources vào `jar` |
| Test runtime thiếu main resources | Test không tìm thấy cấu hình hoặc fixture của ứng dụng | Thêm `main.resources.dir` vào test runtime classpath |
| Test resource cùng tên không được ưu tiên | Thứ tự classpath đặt main trước test | Đặt test classes/resources trước main trong classpath test khi cần override |
| Test compile chạy trước main compile | Không tìm thấy class ứng dụng | Khai báo `compile-test` phụ thuộc `compile-main` |
| Thư viện JUnit lọt vào classpath main | Artifact production phụ thuộc test library ngoài ý muốn | Tách `lib/main` và `lib/test` |
| Build sau khi xóa source vẫn giữ class cũ | `javac` incremental không tự xóa class không còn source | Dùng `clean` khi cần build sạch hoặc quản lý output bằng target phù hợp |

## 12. Quy tắc tổ chức buildfile

- Dùng `src/main/java` và `src/test/java` làm hai source root độc lập.
- Đặt main classes, test classes, main resources và test resources ở bốn thư mục output riêng.
- Để test compile classpath chứa main classes cùng thư viện test.
- Để test runtime classpath chứa cả hai nhóm class/resource và test libraries.
- Đặt test output trước main output trong classpath nếu test cần ghi đè resource production cùng tên.
- Tạo JAR chỉ từ main classes và main resources.
- Tách dependency main và dependency test để tránh đưa thư viện test vào artifact production.
- Dùng property tập trung cho đường dẫn để các target không tự định nghĩa output khác nhau.
- Dùng `clean` để xóa output sinh tự động khi cần bảo đảm không còn file cũ.

## 13. Bài tập tự kiểm tra

**Bài 1.** Vì sao `build/classes/main` và `build/classes/test` nên tách riêng?

**Đáp án:** Vì class chính thuộc ứng dụng phát hành, còn class test chỉ phục vụ kiểm thử. Tách riêng giúp task `jar` chỉ chọn main output.

**Bài 2.** Test cần đọc file `src/test/resources/config/app.yml`. File đó nên được copy vào đâu?

**Đáp án:** Vào `build/resources/test`, sau đó thêm thư mục này vào test runtime classpath.

**Bài 3.** JAR production cần chứa những output nào?

**Đáp án:** Main classes và main resources. Không đưa test classes, test resources, test report hoặc test libraries vào JAR production.

**Bài 4.** Nếu test resource có cùng tên với main resource, làm sao để test dùng bản test?

**Đáp án:** Đặt `build/resources/test` trước `build/resources/main` trong test runtime classpath để classloader tìm thấy bản test trước.

**Bài 5.** Vì sao test compile cần phụ thuộc main compile?

**Đáp án:** Vì test source thường tham chiếu đến class ứng dụng. Main classes phải được biên dịch và có trên classpath trước khi biên dịch test.

## Kết luận

Tách đầu ra mã chính, mã kiểm thử và tài nguyên giúp Apache Ant tạo build có ranh giới rõ ràng. Mã chính và resource production được đưa vào JAR; mã test và test resource chỉ xuất hiện trong classpath kiểm thử. Khi khai báo đúng source root, `destdir`, resource copy, classpath và dependency giữa các target, buildfile dễ bảo trì hơn và giảm nguy cơ phát hành nhầm nội dung chỉ dành cho test.


# Quản lý dữ liệu kiểm thử, tài nguyên và dọn dẹp môi trường

Một quy trình kiểm thử bằng Apache Ant không chỉ có bước biên dịch và gọi test runner. Test còn cần dữ liệu đầu vào, tệp cấu hình, ảnh hoặc tài nguyên mẫu, thư mục làm việc riêng và nơi lưu báo cáo. Sau khi chạy, những dữ liệu tạm phải được dọn dẹp có kiểm soát để lần chạy tiếp theo bắt đầu từ trạng thái dự đoán được.

Nếu các lần chạy dùng chung một thư mục dữ liệu, một test có thể làm thay đổi fixture của test khác. Nếu không dọn output cũ, test có thể vô tình đọc kết quả từ lần chạy trước. Nếu xóa nhầm thư mục nguồn hoặc thư mục làm việc của người dùng, thao tác cleanup có thể gây mất dữ liệu.

Bài học này trình bày cách tổ chức dữ liệu kiểm thử, sao chép tài nguyên vào test classpath, tạo vùng làm việc riêng, điều phối setup và cleanup bằng target Ant, giữ lại báo cáo khi có lỗi và làm cho test có thể chạy lặp lại trên máy phát triển lẫn CI.

## 1. Tách mã nguồn, tài nguyên và dữ liệu kiểm thử

Một cấu trúc dự án Java thường dùng:

```text
project/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
├── test-data/
│   ├── input/
│   └── expected/
└── build/
    ├── classes/
    ├── test-classes/
    ├── test-work/
    └── test-reports/
```

Mỗi khu vực có một mục đích:

| Thư mục | Nội dung | Cách sử dụng |
|---|---|---|
| `src/main/java` | Mã nguồn ứng dụng | Biên dịch thành lớp chính |
| `src/main/resources` | Tài nguyên runtime của ứng dụng | Đưa vào output chính hoặc JAR |
| `src/test/java` | Mã nguồn kiểm thử | Biên dịch riêng với test classpath |
| `src/test/resources` | Tài nguyên cần trên test classpath | Sao chép vào thư mục test classes |
| `test-data` | Fixture đầu vào và dữ liệu mong đợi | Copy vào vùng làm việc của test khi cần |
| `build/test-work` | Tệp tạm do test tạo hoặc sửa | Xóa và tạo lại cho mỗi lần chạy |
| `build/test-reports` | Báo cáo kết quả test | Giữ lại để phân tích khi test thất bại |

Không phải dự án nào cũng cần đủ các thư mục này. Điều quan trọng là phân biệt tài nguyên thuộc ứng dụng, tài nguyên chỉ dành cho test và dữ liệu có thể bị test thay đổi.

## 2. Phân loại dữ liệu kiểm thử

Trước khi viết target, hãy xác định dữ liệu nào là nguồn cố định, dữ liệu nào được tạo ra trong lúc test và dữ liệu nào là kết quả.

### Fixture cố định

Fixture là dữ liệu mẫu được chuẩn bị trước, chẳng hạn:

- Tệp JSON hoặc XML đại diện cho một yêu cầu hợp lệ.
- Tệp CSV chứa một bộ bản ghi mẫu.
- Ảnh hoặc tài liệu nhỏ dùng để kiểm thử xử lý tệp.
- Nội dung dự kiến để so sánh với kết quả thực tế.

Fixture cố định nên được xem như dữ liệu chỉ đọc. Test có thể đọc chúng nhưng không nên sửa trực tiếp file trong repository.

Ví dụ:

```text
test-data/
├── input/
│   ├── customer-valid.json
│   └── customer-invalid.json
└── expected/
    └── customer-normalized.json
```

### Dữ liệu được tạo trong lúc test

Một số test cần tạo tệp hoặc bản ghi riêng cho từng lần chạy. Dữ liệu đó nên nằm trong thư mục làm việc tạm, ví dụ `build/test-work/`. Test có thể thay đổi hoặc xóa dữ liệu ở đây mà không làm ảnh hưởng fixture gốc.

### Dữ liệu mong đợi và báo cáo

Dữ liệu mong đợi là đầu vào để so sánh kết quả. Báo cáo test là đầu ra phục vụ chẩn đoán. Hai nhóm này có vòng đời khác nhau:

- Fixture mong đợi thường được lưu cùng source control.
- Báo cáo được tạo mới trong mỗi lần chạy và thường được giữ lại khi CI thất bại.
- Tệp tạm được dọn sau test, trừ khi cần giữ lại để điều tra lỗi.

Không nên đặt fixture gốc, dữ liệu tạm và báo cáo vào cùng một thư mục rồi xóa toàn bộ sau mỗi lần chạy.

## 3. Biên dịch mã nguồn và tài nguyên kiểm thử

Mã nguồn test cần được biên dịch riêng và thường tham chiếu các lớp ứng dụng cùng thư viện test.

Ví dụ khai báo property và classpath:

```xml
<project name="sample-tests" default="test" basedir=".">

    <property name="main.src.dir" location="src/main/java"/>
    <property name="main.resources.dir" location="src/main/resources"/>
    <property name="test.src.dir" location="src/test/java"/>
    <property name="test.resources.dir" location="src/test/resources"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>

    <path id="main.classpath">
        <pathelement location="lib/application-api.jar"/>
    </path>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <pathelement location="lib/junit.jar"/>
        <pathelement location="lib/application-api.jar"/>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${main.src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="main.classpath"/>
        </javac>

        <copy todir="${classes.dir}">
            <fileset dir="${main.resources.dir}" erroronmissingdir="false"/>
        </copy>
    </target>

    <target name="compile-test" depends="compile">
        <mkdir dir="${test.classes.dir}"/>
        <javac
            srcdir="${test.src.dir}"
            destdir="${test.classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="test.classpath"/>
        </javac>

        <copy todir="${test.classes.dir}">
            <fileset dir="${test.resources.dir}" erroronmissingdir="false"/>
        </copy>
    </target>

</project>
```

Trong ví dụ:

1. `compile` biên dịch mã nguồn chính vào `build/classes`.
2. Tài nguyên chính được copy vào cùng output để ứng dụng có thể đọc từ classpath.
3. `compile-test` phụ thuộc vào `compile`, nên lớp ứng dụng có sẵn trước khi biên dịch test.
4. Test classpath chứa output chính, output test và thư viện test.
5. Tài nguyên trong `src/test/resources` được copy vào `build/test-classes`, đúng vị trí để test đọc qua classloader.

`erroronmissingdir="false"` hữu ích khi dự án cho phép thư mục tài nguyên chưa tồn tại. Nếu thư mục là thành phần bắt buộc, hãy bỏ thuộc tính này để build báo lỗi khi thiếu.

### Đọc test resource từ Java

Nếu `src/test/resources/fixtures/customer.json` được copy vào `build/test-classes/fixtures/customer.json`, test có thể đọc qua classloader:

```java
try (var input = getClass().getClassLoader()
        .getResourceAsStream("fixtures/customer.json")) {
    if (input == null) {
        throw new IllegalStateException("Missing customer fixture");
    }
    // Parse input and assert the expected values.
}
```

Cách đọc này không phụ thuộc vào thư mục terminal đang đứng. Nó cũng hoạt động khi test resource được đóng gói trong một JAR trên classpath.

Nếu test cần sửa nội dung tệp, hãy copy fixture sang vùng làm việc trước rồi mới sửa bản sao.

## 4. Chuẩn bị dữ liệu và thư mục làm việc cho test

Một target chuẩn bị thường làm ba việc:

- Xóa dữ liệu tạm còn sót từ lần chạy trước.
- Tạo thư mục làm việc mới.
- Copy fixture vào đó.

Ví dụ:

```xml
<property name="test.data.dir" location="test-data"/>
<property name="test.work.dir" location="build/test-work"/>
<property name="test.report.dir" location="build/test-reports"/>

<target name="prepare-test-data" depends="compile-test">
    <delete dir="${test.work.dir}"/>
    <mkdir dir="${test.work.dir}/input"/>
    <mkdir dir="${test.work.dir}/output"/>

    <copy todir="${test.work.dir}/input">
        <fileset dir="${test.data.dir}/input"/>
    </copy>

    <mkdir dir="${test.report.dir}"/>
</target>
```

Target này bảo đảm test bắt đầu với một bản sao fixture mới. Nếu test ghi đè hoặc xóa tệp trong `build/test-work/input`, dữ liệu gốc trong `test-data/input` vẫn được giữ nguyên.

### Truyền đường dẫn làm việc cho test

Task test runner có thể truyền property vào JVM kiểm thử. Với task JUnit cổ điển của Ant:

```xml
<junit fork="true">
    <sysproperty
        key="test.work.dir"
        value="${test.work.dir}"/>
</junit>
```

Trong Java test, đọc bằng:

```java
String workDir = System.getProperty("test.work.dir");
```

Như vậy test không phải hard-code đường dẫn `build/test-work`. Có thể thay đổi thư mục làm việc qua property của Ant hoặc cấu hình CI.

## 5. Tạo dữ liệu test riêng cho từng lần chạy

Nếu nhiều lần chạy hoặc nhiều test cùng ghi vào một thư mục, chúng có thể ghi đè dữ liệu của nhau. Điều này đặc biệt dễ xảy ra khi bật parallel testing hoặc chạy nhiều job trên cùng workspace.

Có thể thêm mã định danh cho vùng làm việc:

```xml
<property name="test.run.id" value="local"/>
<property
    name="test.work.dir"
    location="build/test-work/${test.run.id}"/>
```

Khi chạy:

```bash
ant -Dtest.run.id=ci-1042 test
```

test sử dụng `build/test-work/ci-1042`. Một job khác có thể dùng mã khác để tránh ghi chung dữ liệu.

Nếu các test chạy song song trong cùng một JVM hoặc cùng một job, chỉ tạo thư mục riêng cho job vẫn chưa đủ. Mỗi test hoặc mỗi worker cần tên thư mục con duy nhất, hoặc test phải tự tạo file tạm bằng API phù hợp của Java/JUnit. Tránh dùng tên cố định như `output.txt` cho nhiều test đồng thời.

### Dữ liệu cơ sở dữ liệu

Với test có sử dụng database:

- Tạo schema hoặc bộ dữ liệu dành riêng cho test.
- Dùng khóa định danh riêng cho từng test hoặc từng lượt chạy.
- Đưa database về trạng thái xác định trước khi test bắt đầu.
- Dùng transaction rollback khi phù hợp với kiến trúc kiểm thử.
- Không trỏ target test thông thường vào database production.
- Xóa đúng các bản ghi do test tạo, tránh lệnh xóa rộng không có điều kiện.

Ant có thể điều phối script hoặc công cụ chuẩn bị database, nhưng quy tắc tạo và hoàn nguyên fixture nên được thiết kế rõ ràng. Không nên phụ thuộc vào việc một test chạy trước để tạo dữ liệu cho test khác.

## 6. Chạy test và lưu báo cáo

Task JUnit cổ điển của Ant có thể chạy một nhóm test và ghi báo cáo:

```xml
<target name="run-tests" depends="prepare-test-data">
    <junit
        fork="true"
        printsummary="yes"
        haltonfailure="false"
        haltonerror="false"
        failureproperty="tests.failed"
        errorproperty="tests.error">

        <classpath refid="test.classpath"/>

        <sysproperty
            key="test.work.dir"
            value="${test.work.dir}"/>

        <formatter type="plain"/>
        <formatter type="xml"/>

        <batchtest todir="${test.report.dir}">
            <fileset dir="${test.classes.dir}">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Trong ví dụ:

- `fork="true"` chạy test trong JVM riêng.
- `test.classpath` cung cấp lớp ứng dụng, lớp test và thư viện cần cho test.
- `sysproperty` truyền thư mục dữ liệu vào JVM test.
- Các formatter tạo log hoặc XML report theo cấu hình.
- `batchtest` tìm các lớp test khớp pattern.
- `failureproperty` và `errorproperty` ghi nhận trạng thái thất bại để build có thể xử lý sau khi task test kết thúc.
- `haltonfailure="false"` và `haltonerror="false"` cho phép target tiếp tục để thực hiện bước cleanup và quyết định trạng thái build sau đó.

Task `junit` thuộc nhóm task mở rộng của Ant và cần thư viện JUnit cùng dependency tương thích theo tài liệu phiên bản đang dùng. Classpath lồng trong `<junit>` là classpath của test runner và các lớp test; nó không thay thế việc cài task implementation cần thiết cho Ant.

Với JUnit Platform, Ant có task `junitlauncher` ở các phiên bản hỗ trợ. Cú pháp và cách khai báo engine khác với task `junit` cổ điển. Hãy dùng task phù hợp với phiên bản framework và Ant của dự án.

## 7. Dọn dữ liệu sau khi test

Cleanup nên được thiết kế theo phạm vi hẹp. Nếu test tạo dữ liệu dưới `build/test-work`, target dọn dẹp chỉ nên xóa thư mục đó:

```xml
<target name="clean-test-data">
    <delete dir="${test.work.dir}"/>
</target>
```

Không dùng đường dẫn quá rộng như ${basedir} hoặc thư mục cha chứa cả mã nguồn và fixture. Đặc biệt, không ghép đường dẫn cleanup từ property không được kiểm soát nếu giá trị đó có thể trỏ ra ngoài workspace dự án.

Có thể tách cleanup dữ liệu test khỏi cleanup toàn bộ build:

```xml
<target name="clean-test-data">
    <delete dir="${test.work.dir}"/>
</target>

<target name="clean-test-output">
    <delete dir="${test.classes.dir}"/>
    <delete dir="${test.report.dir}"/>
</target>

<target name="clean-test" depends="clean-test-data,clean-test-output"/>
```

Việc tách target giúp bạn chọn giữ báo cáo hay xóa toàn bộ output. Trong CI, thường nên giữ báo cáo test khi job thất bại để có thể tải artifact và phân tích nguyên nhân.

### Dọn dữ liệu sau khi test nhưng vẫn giữ báo cáo

Một quy trình có thể chạy test, xóa vùng dữ liệu tạm rồi mới làm build thất bại nếu có test lỗi:

```xml
<target name="test" depends="run-tests">
    <delete dir="${test.work.dir}"/>

    <fail
        if="tests.failed"
        message="Có test thất bại. Xem báo cáo trong ${test.report.dir}."/>

    <fail
        if="tests.error"
        message="Có lỗi khi chạy test. Xem báo cáo trong ${test.report.dir}."/>
</target>
```

Trong cấu hình này, task JUnit được yêu cầu không dừng target ngay khi test thất bại; Ant có thể tiếp tục đến lệnh `delete` và sau đó phát tín hiệu build thất bại bằng `fail`. Báo cáo nằm ngoài `test.work.dir`, nên vẫn còn để phân tích.

Đây là mẫu xử lý cho các kết quả thất bại mà task JUnit ghi nhận qua property. Nếu task ném lỗi cấu hình hoặc lỗi Ant nghiêm trọng trước khi tới bước cleanup, các target phía sau vẫn có thể không chạy. Vì vậy, test code cũng nên tự giải phóng tài nguyên trong `finally`, `@AfterEach` hoặc cơ chế teardown tương ứng của framework.

## 8. Giữ lại dữ liệu khi cần điều tra lỗi

Đôi khi dữ liệu tạm là bằng chứng quan trọng để tái hiện lỗi. Bạn có thể cho phép người gọi giữ lại vùng làm việc bằng một property:

```xml
<target name="clean-test-data" unless="keep.test.data">
    <delete dir="${test.work.dir}"/>
</target>
```

Chạy bình thường:

```bash
ant test
```

Target cleanup được thực hiện và xóa dữ liệu tạm.

Giữ dữ liệu để điều tra:

```bash
ant -Dkeep.test.data=true test
```

Target có `unless="keep.test.data"` sẽ bị bỏ qua nếu property tồn tại.

Lưu ý, thuộc tính `if` và `unless` trên target kiểm tra **sự tồn tại của property**, không đánh giá chuỗi `true` hoặc `false` như boolean. Vì vậy, nếu truyền `-Dkeep.test.data=false`, property vẫn tồn tại và cleanup vẫn bị bỏ qua. Nếu cần kiểm tra giá trị boolean thực sự, hãy tạo property điều kiện bằng task `<condition>` rồi dùng tên property kết quả.

Khi giữ dữ liệu test, hãy ghi rõ đường dẫn được giữ trong log và tránh lưu dữ liệu nhạy cảm vào artifact CI. Sau khi đã thu thập đủ thông tin, dùng target cleanup để xóa vùng làm việc.

## 9. Quản lý tài nguyên ngoài hệ thống tệp

Một test có thể sử dụng thêm tài nguyên như:

- Database hoặc schema riêng.
- Queue, bucket hoặc thư mục chia sẻ.
- Process phụ hoặc server test cục bộ.
- Socket, port hoặc kết nối mạng.
- Tài khoản test và dữ liệu xác thực.

Ant có thể gọi script chuẩn bị và dọn dẹp những tài nguyên này thông qua target hoặc task phù hợp. Tuy nhiên, cần có quy tắc sở hữu rõ ràng: tài nguyên nào do test tạo thì test hoặc quy trình teardown phải chịu trách nhiệm giải phóng.

Ví dụ quy trình ở mức target:

```xml
<target name="prepare-integration-test">
    <echo message="Preparing isolated integration-test environment"/>
    <!-- Gọi công cụ/script đã được dự án quản lý để tạo tài nguyên test -->
</target>

<target name="integration-test" depends="prepare-integration-test">
    <echo message="Run integration tests here"/>
</target>

<target name="teardown-integration-test">
    <echo message="Release integration-test resources"/>
    <!-- Gọi công cụ/script teardown tương ứng -->
</target>
```

Đây là khung điều phối. Các lệnh tạo và xóa thực tế phụ thuộc hạ tầng của dự án. Script teardown cần nhận đúng mã định danh tài nguyên đã tạo để chỉ xóa tài nguyên của lần test hiện tại.

Với process hoặc kết nối được tạo từ mã Java, hãy đóng chúng trong `finally` hoặc `try-with-resources`. Không nên chỉ trông chờ target `clean` cuối build vì test có thể bị hủy giữa chừng hoặc JVM có thể kết thúc bất thường.

## 10. Bảo đảm test có thể chạy lặp lại

Một test tốt nên cho kết quả giống nhau khi chạy độc lập, chạy lại nhiều lần hoặc chạy trên máy CI. Để đạt điều đó:

- Không sửa fixture gốc trong source control.
- Tạo lại dữ liệu đầu vào cần thay đổi ở mỗi lần chạy.
- Dùng thư mục làm việc riêng cho từng job hoặc từng test song song.
- Xóa output cũ trước khi tạo fixture mới.
- Không phụ thuộc thứ tự chạy giữa các test.
- Cố định timezone, locale và encoding nếu kết quả phụ thuộc môi trường.
- Đặt cấu hình endpoint và thông tin test qua property rõ ràng.
- Không dùng dữ liệu production trong test thông thường.
- Lưu báo cáo ở thư mục riêng để cleanup dữ liệu tạm không xóa mất báo cáo.
- Dùng teardown trong test code để giải phóng tài nguyên ngay cả khi assertion thất bại.

Ví dụ cố định timezone và encoding cho JVM test:

```xml
<junit fork="true" printsummary="yes">
    <sysproperty key="user.timezone" value="UTC"/>
    <sysproperty key="file.encoding" value="UTF-8"/>
    <sysproperty key="test.work.dir" value="${test.work.dir}"/>
    <classpath refid="test.classpath"/>
</junit>
```

`file.encoding` và cách JVM xử lý encoding mặc định có thể phụ thuộc phiên bản Java. Với tệp, tốt hơn nên chỉ định encoding trực tiếp trong API đọc/ghi thay vì chỉ dựa vào giá trị mặc định của JVM. Ví dụ, dùng `StandardCharsets.UTF_8` trong mã Java khi đọc dữ liệu UTF-8.

## 11. Ví dụ build file tổng hợp

Ví dụ sau ghép các bước compile, copy tài nguyên, chuẩn bị fixture, chạy test, cleanup và giữ báo cáo:

```xml
<project name="test-lifecycle" default="test" basedir=".">

    <property name="main.src.dir" location="src/main/java"/>
    <property name="main.resources.dir" location="src/main/resources"/>
    <property name="test.src.dir" location="src/test/java"/>
    <property name="test.resources.dir" location="src/test/resources"/>
    <property name="test.data.dir" location="test-data"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="test.work.dir" location="${build.dir}/test-work"/>
    <property name="test.report.dir" location="${build.dir}/test-reports"/>
    <property name="test.run.id" value="local"/>

    <path id="main.classpath">
        <pathelement location="lib/application-api.jar"/>
    </path>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <pathelement location="lib/application-api.jar"/>
        <pathelement location="lib/junit.jar"/>
    </path>

    <target name="clean-test-data">
        <delete dir="${test.work.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${main.src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="main.classpath"/>
        </javac>
        <copy todir="${classes.dir}">
            <fileset dir="${main.resources.dir}" erroronmissingdir="false"/>
        </copy>
    </target>

    <target name="compile-test" depends="compile">
        <mkdir dir="${test.classes.dir}"/>
        <javac
            srcdir="${test.src.dir}"
            destdir="${test.classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="test.classpath"/>
        </javac>
        <copy todir="${test.classes.dir}">
            <fileset dir="${test.resources.dir}" erroronmissingdir="false"/>
        </copy>
    </target>

    <target name="prepare-test" depends="compile-test,clean-test-data">
        <mkdir dir="${test.work.dir}/${test.run.id}/input"/>
        <mkdir dir="${test.work.dir}/${test.run.id}/output"/>
        <mkdir dir="${test.report.dir}"/>
        <copy todir="${test.work.dir}/${test.run.id}/input">
            <fileset dir="${test.data.dir}/input"/>
        </copy>
    </target>

    <target name="run-tests" depends="prepare-test">
        <junit
            fork="true"
            printsummary="yes"
            haltonfailure="false"
            haltonerror="false"
            failureproperty="tests.failed"
            errorproperty="tests.error">
            <classpath refid="test.classpath"/>
            <sysproperty
                key="test.work.dir"
                value="${test.work.dir}/${test.run.id}"/>
            <sysproperty key="user.timezone" value="UTC"/>
            <formatter type="plain"/>
            <formatter type="xml"/>
            <batchtest todir="${test.report.dir}">
                <fileset dir="${test.classes.dir}">
                    <include name="**/*Test.class"/>
                </fileset>
            </batchtest>
        </junit>
    </target>

    <target name="test" depends="run-tests">
        <delete dir="${test.work.dir}/${test.run.id}"
                quiet="true"
                failonerror="false"/>
        <fail if="tests.failed"
              message="Tests failed. See ${test.report.dir}."/>
        <fail if="tests.error"
              message="Test execution errors occurred. See ${test.report.dir}."/>
    </target>

    <target name="clean-test">
        <delete dir="${test.work.dir}"/>
        <delete dir="${test.classes.dir}"/>
        <delete dir="${test.report.dir}"/>
    </target>

</project>
```

Chạy test:

```bash
ant test
```

Chạy với mã định danh riêng:

```bash
ant -Dtest.run.id=ci-1042 test
```

Xóa toàn bộ dữ liệu test và báo cáo:

```bash
ant clean-test
```

Trong ví dụ, target `test` xóa thư mục làm việc của lượt chạy hiện tại nhưng giữ lại `test-reports`. Target `clean-test` mới xóa cả báo cáo và test classes. Hãy điều chỉnh vòng đời này theo yêu cầu CI: nếu cần giữ báo cáo khi job thất bại, đừng gọi `clean-test` ngay sau khi test.

Lưu ý: target `prepare-test` gọi `clean-test-data` để tạo trạng thái mới. Nếu chạy nhiều job song song trong cùng một workspace, cách xóa toàn bộ `test.work.dir` này không an toàn cho các job khác. Khi chạy song song, hãy dùng workspace riêng cho mỗi job hoặc chỉ xóa thư mục có mã định danh hiện tại trước khi chuẩn bị dữ liệu.

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test đọc được tài nguyên trên máy cá nhân nhưng lỗi trên CI | Tài nguyên chưa được copy vào test classpath hoặc đường dẫn phụ thuộc working directory | Copy `src/test/resources` vào test classes và đọc bằng classloader |
| Test thất bại khi chạy lần thứ hai | Dữ liệu hoặc output từ lần trước còn sót | Dọn thư mục làm việc trước khi tạo fixture |
| Fixture trong repository bị thay đổi | Test sửa trực tiếp file nguồn | Copy fixture sang vùng làm việc rồi chỉ sửa bản sao |
| Nhiều test ghi đè cùng một file | Dùng chung tên tệp hoặc thư mục khi chạy song song | Tạo vùng làm việc riêng theo test/job |
| Build báo thành công dù test thất bại | Task test được cấu hình không dừng build nhưng không kiểm tra property kết quả | Dùng `failureproperty`/`errorproperty` và `fail` sau cleanup |
| Báo cáo biến mất sau khi test lỗi | Cleanup xóa cả thư mục chứa báo cáo | Tách `test-work` và `test-reports` |
| Cleanup xóa nhầm dữ liệu | Đường dẫn xóa quá rộng hoặc property trỏ sai | Chỉ xóa thư mục con chuyên dụng, kiểm tra property và base directory |
| Tài nguyên có encoding khác nhau giữa các máy | Dựa vào encoding mặc định của JVM hoặc hệ điều hành | Chỉ định UTF-8 rõ ràng trong build và mã đọc/ghi |
| Test phụ thuộc thứ tự chạy | Một test tạo dữ liệu cho test khác | Mỗi test tự chuẩn bị fixture và teardown của mình |

## 13. Ghi nhớ

- Tách mã nguồn test, test resources, fixture gốc, dữ liệu tạm và báo cáo thành các vùng riêng.
- Không sửa trực tiếp fixture trong repository; copy sang thư mục làm việc trước khi test thay đổi dữ liệu.
- Đưa `src/test/resources` vào test classpath để test đọc bằng classloader.
- Tạo dữ liệu riêng theo lượt chạy hoặc theo test khi có khả năng chạy song song.
- Dùng target setup để chuẩn bị fixture và target cleanup để dọn đúng vùng dữ liệu tạm.
- Giữ báo cáo test ở thư mục riêng để vẫn có thể phân tích khi test thất bại.
- Kết hợp `failureproperty`, `errorproperty` và `fail` nếu cần cleanup trước khi đánh dấu build thất bại.
- Dùng teardown trong test code để đóng tài nguyên ngay cả khi assertion hoặc test runner gặp lỗi.
- Không dùng dữ liệu production cho test thông thường và không xóa thư mục ngoài phạm vi được kiểm soát.

Một quy trình test đáng tin cậy bắt đầu từ dữ liệu đầu vào xác định, chạy trong vùng làm việc riêng và kết thúc bằng cleanup có phạm vi rõ ràng. Khi fixture, tài nguyên, báo cáo và dữ liệu tạm có vòng đời riêng, test sẽ dễ chạy lại, dễ chẩn đoán và ổn định hơn trên CI.

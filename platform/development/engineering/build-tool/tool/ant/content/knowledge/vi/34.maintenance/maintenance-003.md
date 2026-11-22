# Tài liệu hóa target công khai, đầu vào, đầu ra và điều kiện chạy

Trong dự án dùng **Apache Ant**, `build.xml` là nơi khai báo các tác vụ tự động hóa, đồng thời là một giao diện để lập trình viên, CI/CD và công cụ khác gọi build. Một lệnh như `ant package` có vẻ đơn giản, nhưng người gọi cần biết: target này phụ thuộc target nào, phải có file và công cụ gì, đầu ra nằm đâu, có ghi đè dữ liệu không, điều kiện nào khiến nó chạy hoặc bỏ qua và khi thất bại phải xử lý thế nào.

Khi dự án phát triển, các target có thể được tách sang file khác, thêm `depends`, thêm thuộc tính `if`/`unless`, thay thư mục output hoặc gọi công cụ ngoài qua `<exec>`. Nếu không cập nhật tài liệu, tên target vẫn giống cũ nhưng hành vi đã khác. Điều này làm tăng chi phí bảo trì và dễ gây lỗi vận hành, đặc biệt với target có tác dụng phụ như `clean`, `publish` hoặc `deploy`.

Mục tiêu của bài này thuộc nhóm **Bảo trì** là biến các target Ant được hỗ trợ gọi trực tiếp thành **hợp đồng build rõ ràng**: mô tả lệnh công khai, đầu vào, đầu ra, điều kiện chạy, lỗi và tác dụng phụ; giữ thông tin ngắn ngay trong `build.xml` và giải thích chi tiết trong tài liệu dự án.

## 1. Target công khai là giao diện sử dụng của build

Một project có thể có hàng chục target nhưng người dùng thường chỉ cần một nhóm lệnh ổn định:

~~~bash
ant -projecthelp
ant compile
ant test
ant package
ant clean
~~~

Có thể phân biệt:

| Loại target | Vai trò | Ví dụ |
|---|---|---|
| **Công khai** | Người dùng, pipeline hoặc automation được hướng dẫn gọi trực tiếp | `help`, `compile`, `test`, `package`, `clean` |
| **Nội bộ** | Bước triển khai để target khác tái sử dụng | `internal.validate-inputs`, `internal.prepare-dirs`, `internal.resolve-classpath` |
| **Có tác dụng ngoài môi trường build** | Cần quy tắc quyền và điều kiện chạy bổ sung | `publish`, `deploy`, `db-migrate` |

Ant không áp dụng hệ thống truy cập `public/private` giống Java cho mọi target. Việc bỏ `description` chỉ giúp target không xuất hiện trong danh sách lệnh được quảng bá bởi `ant -projecthelp`; một target nội bộ có tên như `internal.prepare-dirs` vẫn có thể được gọi nếu người dùng biết tên. Vì vậy cần **quy ước về API được hỗ trợ**, không xem việc ẩn mô tả là một rào chắn bảo mật.

Một target công khai nên có tên dễ đoán, công dụng nhất quán và tài liệu phản ánh chính xác hành vi. Nếu các script bên ngoài đã gọi `ant package` thì thay đổi tên hoặc ngữ nghĩa của target có thể là thay đổi phá vỡ tương thích, ngay cả khi `build.xml` vẫn hợp lệ.

### Hợp đồng tối thiểu cần công bố

Mỗi target được hỗ trợ trực tiếp nên trả lời:

1. **Mục đích:** target giải quyết công việc gì, khi nào nên dùng?
2. **Cách gọi:** CLI, target và các tham số được hỗ trợ là gì?
3. **Đầu vào:** file, thư mục, property, biến môi trường, dependency, công cụ hoặc dịch vụ nào cần thiết?
4. **Đầu ra:** artifact, báo cáo, log hay trạng thái từ xa được tạo ở đâu?
5. **Điều kiện chạy:** target phụ thuộc vào gì; khi nào chạy, skip hoặc fail trước khi thực thi?
6. **Tác dụng phụ:** có ghi đè/xóa file, thay cache, gọi mạng, cập nhật database hay upload không?
7. **Kết quả và lỗi:** dấu hiệu thành công, lỗi có thể gặp và khả năng chạy lại thế nào?

Chỉ ghi “`package`: tạo JAR” sẽ khiến người dùng phải tự mở `build.xml` để suy luận những thông tin còn lại.

## 2. Khai báo danh sách lệnh bằng `description`

Ant có thuộc tính `description` trên `<target>`, và thuộc tính mô tả cho project. Lệnh `ant -projecthelp` (hoặc `ant -p`) giúp người mới khám phá những target được mô tả.

~~~xml
<project name="sample-app" default="help" basedir=".">
    <description>
        Ant build cua Sample App.
        Xem docs/BUILDING.md de biet input, output va cach chay.
    </description>

    <target name="help"
            description="Hien thi huong dan va tai lieu build">
        <echo message="Chay: ant -projecthelp"/>
        <echo message="Tai lieu: docs/BUILDING.md"/>
    </target>

    <target name="compile"
            description="Bien dich Java vao build/classes">
        <!-- Chi tiet bien dich duoc khai bao tai build that. -->
    </target>

    <target name="package"
            description="Tao JAR tai build/dist/sample-app.jar">
        <!-- Chi tiet dong goi duoc khai bao tai build that. -->
    </target>

    <target name="clean"
            description="Xoa output sinh ra trong build/">
        <!-- Chi tiet xoa duoc khai bao tai build that. -->
    </target>

    <target name="internal.prepare-dirs">
        <!-- Buoc phu tro, khong thuoc giao dien CLI da cam ket. -->
    </target>
</project>
~~~

Sử dụng:

~~~bash
ant -projecthelp
~~~

Các target có `description` sẽ xuất hiện trong phần trợ giúp của project theo cách trình bày của phiên bản Ant đang dùng. Nội dung `description` nên ngắn gọn: **động từ + kết quả chính + đường dẫn output**, ví dụ “Đóng gói build/dist/sample-app.jar” hữu ích hơn “Build artifact”.

Có thể đặt target mặc định là `help` để lệnh `ant` không làm thay đổi dữ liệu ngoài ý muốn. Dự án khác có thể chọn mặc định là `verify` hoặc `build` nếu đó là hợp đồng công khai được phê duyệt. Tránh chọn target tác động hệ thống bên ngoài như `publish` hoặc `deploy` làm mặc định.

### Tài liệu nằm ở đâu?

| Nơi viết | Loại thông tin | Mục đích |
|---|---|---|
| Project `<description>` | Mục tiêu build và nơi xem hướng dẫn | Giới thiệu nhanh |
| Target `description` | Tên lệnh và tác dụng ngắn | Hiển thị qua `ant -p` |
| Comment XML gần target | Vì sao có một dependency hoặc điều kiện đặc biệt | Người sửa mã build |
| `docs/BUILDING.md` / README | Hợp đồng đầy đủ, ví dụ CLI và troubleshooting | Người gọi target |
| Cấu hình CI/CD | Phiên bản công cụ, cách gọi target, đầu ra pipeline | Người vận hành automation |

Không cần nhồi hết hướng dẫn vào một thuộc tính XML. Hai lớp mô tả ngắn và tài liệu chi tiết nên liên kết rõ ràng và được cập nhật trong cùng một thay đổi.

## 3. Lập bảng tổng quan các target được hỗ trợ

Một bảng giao diện giúp người dùng chọn đúng lệnh:

| Target | Mục đích | Input chính | Output chính | Ghi chú điều kiện |
|---|---|---|---|---|
| `help` | Liệt kê lệnh | `build.xml` | Console | Không thay đổi artifact |
| `compile` | Biên dịch Java | `src/main/java`, JDK, classpath | `build/classes/` | Fail nếu thiếu source hoặc compiler lỗi |
| `unit-test` | Kiểm tra mã Java | Classes, test data, test libraries | `build/reports/tests/` | Fail nếu test thất bại theo chính sách |
| `package` | Đóng gói | Classes và resources | `build/dist/app.jar` | Depends on `compile` |
| `clean` | Dọn output | Thư mục generated của project | Xóa `build/` | Có tác dụng xóa file |
| `publish` | Phát hành artifact | Artifact, repository, credential | Artifact từ xa | Chỉ chạy khi đủ quyền và điều kiện phát hành |

Đây là bảng ví dụ: dự án thật chỉ ghi những target thực sự có trong `build.xml` và các output thực sự được tạo. Nếu `test` không tạo báo cáo XML hoặc `package` không biên dịch source, đừng sao chép nguyên bảng trên.

Một target quan trọng nên có mục riêng theo mẫu:

~~~markdown
### package

**Mục đích:** Tạo JAR từ source đã biên dịch.

**Cách gọi:** ./scripts/antw.sh package

**Đầu vào:** src/main/java/**, build.xml, build.properties,
JDK và các JAR compile dependency đã khóa.

**Phụ thuộc:** compile và các target mà compile phụ thuộc.

**Đầu ra:** build/dist/app.jar; build/classes/** là output trung gian.

**Điều kiện chạy:** Cần source Java hợp lệ và JDK được hỗ trợ.

**Tác dụng phụ:** Tạo hoặc ghi đè file bên trong build/.

**Thành công:** Biên dịch thành công, JAR được tạo.

**Thất bại:** Thiếu input, compiler trả lỗi, không thể ghi output.

**Chạy lại:** Có thể chạy lại trên cùng checkout; cần quy định
việc làm sạch output cũ khi thay cấu hình.

**Ví dụ:** ./scripts/antw.sh clean package
~~~

Mẫu giúp người bảo trì nói chính xác target làm gì mà không biến tài liệu thành bản sao của mọi dòng XML.

## 4. Mô tả đầy đủ đầu vào của target

Trong Ant, “đầu vào” không giới hạn ở source file:

| Loại đầu vào | Ví dụ | Điều cần ghi |
|---|---|---|
| Source/resource | `src/main/java/**`, `src/test/resources/**` | Đường dẫn tương đối project, bắt buộc hay tùy chọn |
| Cấu hình | `build.properties`, `settings.xml` | Ai quản lý, giá trị mặc định, khi nào phải có |
| Ant property | `java.release`, `with.integration.tests`, `artifact.name` | Kiểu giá trị, default và cách truyền `-D` |
| Biến môi trường | `JAVA_HOME`, `CI`, `HTTP_PROXY` | Có được đọc không, fallback, nền tảng được hỗ trợ |
| Công cụ | Ant, JDK, compiler, `protoc`, `node` | Phiên bản cụ thể hoặc nguồn manifest/version lock |
| Thư viện | Compile classpath, Ant task JAR, test libraries | Bản đã khóa, đường dẫn, nguồn tải |
| Dịch vụ | Database test, artifact repository | Điều kiện sẵn sàng, quyền truy cập, ảnh hưởng ngoài |
| Secret | Token, key ký, credential phát hành | Chỉ ghi tên và cách cấp phát, không ghi giá trị |

### Ghi chính sách property

Ví dụ một bảng tùy chọn:

| Property | Mặc định | Giá trị hợp lệ | Ví dụ gọi |
|---|---|---|---|
| `java.release` | `17` | Release compiler được dự án hỗ trợ | `ant -Djava.release=17 compile` |
| `with.integration.tests` | `false` | `true` hoặc `false` | `ant -Dwith.integration.tests=true integration-test` |
| `artifact.name` | `sample-app.jar` | Tên file hợp lệ theo quy tắc dự án | `ant -Dartifact.name=sample-app.jar package` |

Đây là các property mẫu; nếu `build.xml` không thực sự sử dụng một property, không nên công bố nó như API được hỗ trợ.

**Ant properties thường có ngữ nghĩa “giá trị đặt trước được giữ”**. Chẳng hạn:

~~~xml
<property file="build.properties"/>
<property name="java.release" value="17"/>
~~~

Nếu `build.properties` hoặc tham số `-Djava.release=21` đã gán giá trị, dòng thứ hai không phải cơ chế cưỡng ép phiên bản 17. Một tài liệu bảo trì cần nêu rõ nguồn property và khả năng override. Nếu có phiên bản bắt buộc cho CI, hãy thêm validation thực tế, không chỉ khai báo default.

Nên phân biệt:

- **Input do người dùng chỉnh:** source, file cấu hình được phép sửa.
- **Input do hệ thống cung cấp:** toolchain và dependency đã pin, biến môi trường CI.
- **Input được sinh từ target khác:** classes, generated sources, metadata.
- **Input nhạy cảm:** credential và secret, chỉ được cấp phát bởi môi trường phù hợp.

Khi một thư mục vừa là output của `compile` vừa là input của `package`, ghi cả hai quan hệ để tránh người dùng chỉnh sửa file generated rồi bất ngờ bị ghi đè ở lần chạy sau.

## 5. Ghi chính xác đầu ra và tác dụng phụ

Đối với mỗi target công khai, nên phân loại:

1. **Artifact chính:** thứ người gọi mong đợi, ví dụ `build/dist/sample-app.jar`.
2. **Output trung gian:** classes, generated sources, test reports, cache hoặc temporary files.
3. **Tác dụng phụ:** xóa dữ liệu, ghi đè, thay đổi database, upload artifact hoặc gọi dịch vụ từ xa.

Ví dụ:

| Target | Đọc | Tạo/ghi | Xóa/ảnh hưởng khác |
|---|---|---|---|
| `compile` | Source và compile classpath | `build/classes/**` | Có thể ghi đè classes |
| `unit-test` | Test class/data, thư viện, service test | `build/reports/tests/**` | Có thể cập nhật DB test nếu suite có side effect |
| `package` | Classes/resources | `build/dist/sample-app.jar` | Ghi đè JAR cũ |
| `clean` | Không cần class đã build | Không có artifact cuối | Xóa `build/**` |
| `publish` | JAR đã xác minh, credential | Artifact trên repository | Ghi dữ liệu ở hệ thống từ xa |

Khi path được cấu hình qua property, tài liệu phải nêu default, cách thay đổi và ảnh hưởng tới `clean`. Khi output có timestamp hoặc version trong tên, cung cấp ví dụ cụ thể và quy tắc xác định tên file.

**Một target không tạo JAR vẫn có thể gây tác dụng phụ.** Task `<exec>` có thể sửa file, đẩy dữ liệu lên server hoặc khởi chạy background process; target test có thể tạo schema/database test. Hãy mô tả *hành vi quan sát được*, không chỉ tên các task Ant bên trong.

### Tài liệu hóa phạm vi xóa của `clean`

Ví dụ target chỉ xóa output project:

~~~xml
<target name="clean"
        description="Xoa duy nhat output duoi build/">
    <delete dir="build" quiet="true"/>
</target>
~~~

Ở đây `build` được hiểu tương đối theo `basedir` của project. Nếu thay bằng `<delete dir="${build.dir}">` và `build.dir` có thể bị ghi đè bằng `-Dbuild.dir=...`, cần **kiểm tra đường dẫn trước khi xóa**. Một tham số trỏ nhầm thư mục source hoặc thư mục dùng chung có thể gây mất dữ liệu. Hợp đồng target phải chỉ rõ đường dẫn nào được phép xóa và không được quảng bá một target xóa dữ liệu là “an toàn trong mọi trường hợp” khi chưa có cơ chế giới hạn.

## 6. Điều kiện chạy của Ant: `depends`, `if`, `unless`

### Quan hệ phụ thuộc không phải điều kiện skip

Giả sử:

~~~xml
<target name="internal.prepare">
    <mkdir dir="build/classes"/>
</target>

<target name="compile" depends="internal.prepare">
    <!-- Compiler thuc te -->
</target>

<target name="package" depends="compile">
    <!-- Tao JAR -->
</target>
~~~

Gọi `ant package` khiến Ant xử lý `internal.prepare` và `compile` trước phần thân `package`. Trong lượt thực thi bình thường, Ant bảo đảm target được xử lý theo đồ thị phụ thuộc, không phải cứ một nhánh phụ thuộc gặp lại là chạy target đó lần nữa.

Điểm dễ nhầm: target `compile` được xét chạy **không có nghĩa** `<javac>` bắt buộc biên dịch lại toàn bộ source. Các task có thể tối ưu dựa trên timestamp/đầu vào. Tài liệu nên tách **target được gọi** khỏi **công việc thực tế được thực hiện bên trong**.

### `if` / `unless` kiểm tra property có tồn tại

Với cú pháp cơ bản:

- `if="flag"`: chạy phần thân khi property `flag` **đã được định nghĩa**.
- `unless="flag"`: chạy phần thân khi property `flag` **chưa được định nghĩa**.

Ant không coi chuỗi `"false"` là một property không tồn tại:

~~~xml
<property name="skip.tests" value="false"/>

<target name="test" unless="skip.tests">
    <!-- Phan than target khong chay vi skip.tests DA TON TAI. -->
</target>
~~~

Nếu người dùng muốn tùy chọn boolean, hãy tạo property điều kiện từ phép so sánh thực:

~~~xml
<property name="with.integration.tests" value="false"/>

<condition property="integration.tests.enabled">
    <equals arg1="${with.integration.tests}"
            arg2="true"
            casesensitive="false"
            trim="true"/>
</condition>

<target name="integration-test"
        if="integration.tests.enabled"
        description="Chay test tich hop neu duoc bat">
    <echo message="Integration tests enabled."/>
    <!-- Goi test runner that tai day. -->
</target>
~~~

Khi chạy:

~~~bash
ant integration-test
ant -Dwith.integration.tests=true integration-test
~~~

Lệnh đầu bỏ qua phần thân, lệnh thứ hai cho phép thực thi nếu property điều kiện không bị thiết lập theo cách khác trước đó. Đối với build production, nên validate giá trị input rõ ràng; typo như `tru` không nên im lặng khiến test bị skip.

### Dependency có thể chạy ngay cả khi target bị skip

Đây là chi tiết cần ghi trong tài liệu nếu target phụ thuộc có side effect:

~~~xml
<target name="prepare-test-service">
    <echo message="Thuc hien buoc chuan bi test service"/>
</target>

<target name="integration-test"
        depends="prepare-test-service"
        if="integration.tests.enabled">
    <echo message="Chay integration tests"/>
</target>
~~~

Ant đánh giá dependency trước khi quyết định có chạy **phần thân** của `integration-test` theo `if`/`unless` hay không. Vì vậy `prepare-test-service` có thể vẫn chạy dù test bị skip. Nếu target prepare thực sự khởi động dịch vụ hoặc thay database, cần chuyển điều kiện tới đúng bước chuẩn bị hoặc thiết kế lại đồ thị.

Điều này làm thay đổi tài liệu cần viết: không được nói “`integration-test` không đụng tới database nếu flag bằng false” khi dependency đã can thiệp database trước đó.

### Fail sớm khi thiếu điều kiện bắt buộc

Ví dụ:

~~~xml
<target name="internal.validate-inputs">
    <available file="src/main/java"
               type="dir"
               property="source.exists"/>
    <fail unless="source.exists"
          message="Missing required source directory: src/main/java"/>
</target>
~~~

Đối với file, environment hoặc tool bắt buộc, lỗi nên nói rõ **tên input và giá trị mong đợi**. Nếu cấu hình sai làm target skip hoặc tiếp tục âm thầm, người dùng có thể lấy artifact thiếu dữ liệu và tưởng build đã thành công.

## 7. Ví dụ `build.xml` tự mô tả dành cho project Java nhỏ

Đây là một cấu hình tối giản có bốn target công khai và hai target nội bộ. Nó giả định có source Java trong `src/main/java`, đã cài JDK/Ant tương thích và không có dependency ngoài JDK.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="help" basedir=".">
    <description>
        Build Java bang Apache Ant.
        Target cong khai: help, compile, package, clean.
        Hop dong chi tiet: docs/BUILDING.md.
    </description>

    <property file="build.properties"/>
    <property name="java.release" value="17"/>

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="build/dist"/>

    <target name="help"
            description="Hien thi huong dan va tai lieu build">
        <echo message="Chay: ant -projecthelp"/>
        <echo message="Tai lieu: docs/BUILDING.md"/>
    </target>

    <target name="internal.validate-inputs">
        <available file="${src.dir}"
                   type="dir"
                   property="source.dir.exists"/>
        <fail unless="source.dir.exists"
              message="Thieu thu muc source src/main/java"/>
    </target>

    <target name="internal.prepare-dirs"
            depends="internal.validate-inputs">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile"
            depends="internal.prepare-dirs"
            description="Bien dich Java vao build/classes">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package"
            depends="compile"
            description="Tao JAR build/dist/sample-app.jar">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/sample-app.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="clean"
            description="Xoa output duoi build/">
        <delete dir="build" quiet="true"/>
    </target>
</project>
~~~

Ví dụ gọi:

~~~bash
ant -projecthelp
ant compile
ant package
ant clean
ant clean package
~~~

**Hợp đồng thực tế của ví dụ:**

| Target | Đầu vào | Đầu ra | Điều kiện chạy | Tác dụng phụ |
|---|---|---|---|---|
| `help` | `build.xml` | Console | Mặc định, không phụ thuộc class | In hướng dẫn |
| `compile` | `src/main/java`, JDK, `java.release` | `build/classes/**` | Validate thư mục source; compiler hỗ trợ release | Tạo/ghi đè class |
| `package` | Inputs của compile, classes | `build/dist/sample-app.jar` | Depends on compile | Tạo/ghi đè JAR |
| `clean` | Project root | Không tạo artifact | Không depends | Xóa `build/**` |

Cấu hình trên không có test runner và không cấu hình `classpathref` cho thư viện ngoài. Dự án có thư viện hoặc test phải thêm chúng vào build và hợp đồng tài liệu. Đồng thời, nếu cho phép override các property đường dẫn `src.dir`/`classes.dir`/`dist.dir` từ CLI hoặc file cấu hình, cần cập nhật mô tả output và chính sách `clean` cho phù hợp.

Không nhất thiết coi tên target bắt đầu bằng `internal.` là private ở mức engine: đó là quy ước để người bảo trì biết không được xây automation phụ thuộc trực tiếp vào target này.

## 8. Mẫu tài liệu `docs/BUILDING.md` cho người mới

Bên cạnh `ant -p`, một tài liệu lệnh công khai nên có những câu lệnh người dùng có thể sao chép, điều kiện môi trường, output và hướng xử lý lỗi.

~~~markdown
# Build với Apache Ant

## Yêu cầu môi trường
- Apache Ant và JDK theo phiên bản đã được dự án chấp thuận.
- Chạy tại project root hoặc dùng script wrapper của repository.
- Có mã Java trong src/main/java/.

## Xem các lệnh được hỗ trợ
./scripts/antw.sh -projecthelp

## Compile
./scripts/antw.sh compile

Input: src/main/java/** và compile classpath.
Output: build/classes/.
Lỗi: thiếu source hoặc compiler thất bại.

## Package
./scripts/antw.sh clean package

Input: source, dependency, build config.
Output: build/dist/sample-app.jar.
Không upload artifact lên hệ thống ngoài.

## Clean
./scripts/antw.sh clean

Xóa: build/ trong project.
Không xóa: source, cấu hình hay dependency cache.

## Java release (nếu project hỗ trợ)
./scripts/antw.sh -Djava.release=17 package

## Khắc phục lỗi
- Không có src/main/java/: kiểm tra checkout hoặc đường dẫn project.
- Compiler không hỗ trợ release: xác minh JDK.
- Không thể ghi JAR: kiểm tra quyền ghi build/dist.
~~~

Ở dự án thật, chỉ cung cấp lệnh wrapper nếu script đó tồn tại; nêu rõ cách chạy trên Linux/macOS/Windows nếu hỗ trợ nhiều hệ điều hành. Tài liệu cũng nên phân biệt **build sạch** (`clean package`) và **build gia tăng** (`package`) khi các task tạo kết quả khác nhau do output cũ.

Khi cùng một target được CI và developer gọi với option khác nhau, ghi ví dụ riêng cho hai ngữ cảnh: phiên bản toolchain, service test, property và yêu cầu quyền có thể khác.

## 9. Công khai rõ điều kiện của các target tác động ra bên ngoài

Các target như `publish`, `deploy`, `sign`, `db-migrate` hoặc `upload-docs` cần hợp đồng chi tiết hơn vì có thể tác động repository, server, database hoặc hệ thống khác.

| Trường cần mô tả | Ví dụ |
|---|---|
| Người gọi được phép | Pipeline release hoặc vai trò vận hành đã được cấp quyền |
| Điều kiện trước | Artifact đã build/test; version/tag hợp lệ; endpoint cho phép |
| Đầu vào | File artifact, SHA-256, version, URL đích, credential |
| Đầu ra | Artifact trong repository hoặc môi trường triển khai được thay đổi |
| Side effect | Upload, ghi đè, cập nhật trạng thái từ xa, restart service |
| Lỗi và phục hồi | Quy tắc dừng, tránh publish dở dang, rollback/retry |
| Khả năng chạy lại | Có thể đẩy cùng version lần thứ hai không? |
| Bằng chứng | Commit, bản toolchain, artifact digest, log publish |

Ví dụ điều kiện tồn tại property:

~~~xml
<target name="internal.validate-publish">
    <fail unless="release.version"
          message="Thieu release.version"/>
    <fail unless="publish.repository"
          message="Thieu publish.repository"/>
</target>

<target name="publish"
        depends="internal.validate-publish,package"
        description="Phat hanh artifact khi du dieu kien">
    <!-- Goi publisher that tai day. -->
</target>
~~~

Đây chỉ là minh họa **validation sơ bộ**; `<fail unless="...">` kiểm tra property có tồn tại, chưa kiểm tra giá trị hợp lệ hay quyền publish. Credential phải được cấp phát qua cơ chế an toàn của CI hoặc môi trường, không coi một `-Dpublish.allowed=true` do người dùng tự truyền là chứng minh có quyền. Việc kiểm soát truy cập thực sự thuộc hệ thống CI và repository đích.

Trong ví dụ, thứ tự `depends="internal.validate-publish,package"` được chọn để fail về property trước khi chạy package. Nếu `package` có side effect hoặc tốn thời gian, thứ tự dependency có tác động vận hành và cần được tài liệu hóa đúng.

## 10. Trạng thái skip, up-to-date và chạy lại

Một target được Ant gọi không đồng nghĩa mọi task trong đó đã xử lý lại toàn bộ input:

- `<javac>` có thể bỏ qua source khi class tương ứng được xem là mới hơn theo cơ chế timestamp.
- `<uptodate>` có thể tạo property mô tả một output được coi là hiện hành so với các source đã khai báo.
- `if`/`unless` có thể làm target bỏ qua phần thân dù dependency trước đó đã chạy.
- `<antcall>` tạo một ngữ cảnh gọi target khác; cần hiểu vòng đời property và khả năng thực thi lại khi dùng thay cho `depends`.
- Chạy `ant package` lần thứ hai là một invocation mới, khác với việc một target bị lặp trong đồ thị dependency của cùng invocation.

Ví dụ cơ chế up-to-date:

~~~xml
<target name="internal.check-report">
    <uptodate property="report.current"
              targetfile="build/reports/summary.txt">
        <srcfiles dir="src/report-data" includes="**/*.csv"/>
    </uptodate>
</target>

<target name="generate-report"
        depends="internal.check-report"
        unless="report.current"
        description="Tao report khi input thay doi">
    <!-- Generator that cua project tao summary.txt. -->
</target>
~~~

Đoạn ví dụ giả định thư mục `src/report-data` và generator tồn tại. Cần xem xét riêng trường hợp xóa input, thay đổi phiên bản generator hoặc cấu hình ngoài danh sách source. **Timestamp không bảo đảm output có cùng bytes** khi công cụ, dependency hoặc cấu hình thay đổi.

Khi mô tả khả năng chạy lại, tài liệu nên nêu:

1. Có thể gọi target nhiều lần trên cùng checkout không?
2. Có ghi đè output hay fail khi output đã tồn tại?
3. Khi dừng giữa chừng, có để lại file tạm/đầu ra dở dang không?
4. Có cần `clean` hoặc workspace sạch trước một bản phát hành không?
5. Có phát sinh side effect từ xa không thể đảo ngược không?

Ví dụ một target `package` có thể chạy lại an toàn với đúng các đường dẫn output của nó; điều đó không tự chứng minh hai JAR có cùng SHA-256 nếu timestamp hoặc thứ tự entry thay đổi. Một target `publish` có thể cần cơ chế chống publish lại cùng version.

## 11. Ghi lỗi và bằng chứng hoàn thành cho người vận hành

Tài liệu nên giúp phân biệt bốn trạng thái:

| Trạng thái | Dấu hiệu |
|---|---|
| **Chạy thành công** | Ant kết thúc thành công, output kỳ vọng tồn tại tại path công bố |
| **Bỏ qua theo điều kiện** | Property `if`/`unless` hoặc kiểm tra up-to-date làm phần thân không chạy |
| **Thất bại trước khi chạy** | Thiếu file, tool, cấu hình, permission hoặc dịch vụ bắt buộc |
| **Thất bại khi thực thi** | Compile/test/generator/CLI lỗi hoặc không ghi được output |

Một lỗi rõ ràng nên có tên input và bối cảnh:

~~~xml
<fail unless="source.dir.exists"
      message="Thieu thu muc src/main/java (project root)."/>
~~~

Nếu target gọi executable bằng `<exec>`, cần xác định chính sách exit status, chẳng hạn `failonerror="true"` hoặc kiểm tra result property. Một build không nên tiếp tục tạo artifact phát hành từ bước CLI đã báo lỗi mà không có cơ chế xử lý lỗi rõ ràng.

Với target test, cần ghi liệu test thất bại có làm job fail, report nằm đâu và trường hợp không tìm thấy test có được coi là thành công không. Với target publish, cần nói rõ khi upload lỗi thì có thể có artifact dở dang từ xa hay không, và phải làm gì khi retry.

## 12. Dùng sơ đồ target để nhìn thấy đường đi của dữ liệu

Một sơ đồ phụ thuộc ngắn hữu ích khi target công khai gọi qua nhiều lớp:

~~~mermaid
flowchart LR
    A["package"] --> B["compile"]
    B --> C["internal.prepare-dirs"]
    C --> D["internal.validate-inputs"]
    D --> E["Kiểm tra source"]
    C --> F["Tạo build/classes"]
    B --> G["Tạo classes"]
    A --> H["Tạo build/dist/sample-app.jar"]
    X["clean"] --> Y["Xóa build/"]
    Z["help"] --> W["Hiển thị hướng dẫn"]
~~~

Mũi tên từ target tới dependency trong sơ đồ diễn đạt **yêu cầu phụ thuộc**, trong khi lúc thực thi dependency phải hoàn thành trước phần thân target phụ thuộc. Với các target có network, database hoặc xóa file, nên gắn ghi chú side effect vào đúng nút, để reviewer không hiểu nhầm một target “chỉ build” nhưng thực tế kích hoạt bước có tác động bên ngoài.

Sơ đồ có giá trị hơn khi được cập nhật cùng lúc với `depends`. Không dùng sơ đồ đẹp để thay thế hợp đồng đầu vào/output mà người dùng cần tra cứu.

## 13. Bảo trì hợp đồng khi refactor build

Những thay đổi tưởng là nội bộ có thể phá cách người khác dùng target:

- Đổi tên `jar` thành `package` làm script CI cũ không còn gọi được.
- Đổi output từ `dist/app.jar` sang `build/dist/app.jar` làm bước upload không tìm thấy file.
- Thêm `depends="prepare-db"` khiến target test có thêm side effect.
- Đổi mặc định của property hoặc từ `if` sang `unless` khiến hành vi skip khác đi.
- Thay `clean` để xóa thêm cache hoặc generated source ngoài phạm vi đã công bố.

Khi sửa một target công khai, nên cập nhật cùng một thay đổi:

1. **Người gọi:** lệnh trong README, scripts, CI/CD workflow và target phụ thuộc.
2. **Cú pháp:** tên target, property, giá trị mặc định, cách override, working directory.
3. **Điều kiện:** dependencies, `if`/`unless`, validation và hành vi skip.
4. **Đầu vào/đầu ra:** đường dẫn, tên artifact, định dạng báo cáo, side effect.
5. **Mô tả gần code:** project/target `description` và comment quan trọng.
6. **Tài liệu dài:** bảng hợp đồng, ví dụ CLI và troubleshooting.
7. **Tương thích:** có cần alias tạm cho tên target cũ không?
8. **Kiểm chứng:** build/test phù hợp và quan sát output, exit code theo phạm vi thay đổi.

Ví dụ giữ tên cũ trong giai đoạn chuyển đổi:

~~~xml
<target name="package"
        depends="compile"
        description="Tao artifact chinh">
    <!-- Logic dong goi o day. -->
</target>

<target name="jar"
        depends="package"
        description="Alias tam thoi; hay chuyen sang package">
    <echo message="Target jar se duoc thay bang package."/>
</target>
~~~

Với cấu hình này, người gọi `ant jar` vẫn thực hiện `package` trước khi nhận thông báo. Nếu dự án có thời điểm bỏ alias, ghi rõ mốc đó trong tài liệu. Đổi tên lệnh công khai nên được xem giống đổi API có người dùng bên ngoài.

Nếu build được tách thành file con qua `<import>` hoặc `<include>`, tài liệu nên mô tả tập target công khai của **project tổng thể**. Không nên bắt người dùng tự ghép nhiều danh sách target từ các file XML khác nhau.

## 14. Mẫu hợp đồng để dùng khi thêm target mới

Có thể dùng khuôn sau cho mỗi target được hỗ trợ:

~~~markdown
## <tên target>

**Mục đích:** <Hành động và kết quả người gọi nhận được>

**Người gọi:** <Developer / CI / Release operator>

**Cách gọi:** ant <tên target> [các property được hỗ trợ]

**Điều kiện trước:**
- <Ant, JDK, toolchain, file và dịch vụ bắt buộc>
- <quyền truy cập và cấu hình cần thiết>

**Properties và environment:**
| Tên | Bắt buộc | Mặc định | Giá trị hợp lệ |
|---|---|---|---|
| <property> | Có/Không | <giá trị> | <quy tắc> |

**Dependencies:** <target phụ thuộc và side effect của chúng>

**Đầu vào:** <source, cấu hình, JAR, executable và dịch vụ>

**Đầu ra:** <artifact, report, log, state từ xa>

**Điều kiện chạy/skip:** <if/unless, up-to-date, policy CI>

**Tác dụng phụ:** <tạo, ghi đè, xóa, upload, đổi DB>

**Thành công:** <dấu hiệu có thể quan sát>

**Thất bại:** <điều kiện và trạng thái output khi lỗi>

**Chạy lại:** <idempotence, clean, retry, overwrite>

**Ví dụ:** <lệnh CLI thực tế của dự án>

**Liên hệ:** <file hoặc tài liệu vận hành bổ sung>
~~~

Đây chỉ là **khuôn trình bày**, không phải hợp đồng được mặc định áp dụng cho mọi project Ant. Với target nhỏ như `help`, một đoạn ngắn có thể đủ; với `publish`, mọi điều kiện quyền, artifact và hành vi retry cần được nêu cụ thể.

## 15. Kết quả bảo trì mong muốn

Giả sử một đồng nghiệp vừa clone repository và cần “tạo JAR để thử nghiệm”. Nếu hợp đồng build được tài liệu hóa tốt, họ có thể đọc hướng dẫn toolchain, chạy `ant -projecthelp`, chọn `package`, biết source/JDK nào bắt buộc, chạy đúng câu lệnh ví dụ, lấy JAR ở đường dẫn đã nêu và hiểu rằng lệnh này chưa upload gì lên server.

Khi lệnh thất bại, họ có thể đối chiếu lỗi “thiếu source”, “compiler không hỗ trợ release” hoặc “không ghi được output” với phần troubleshooting; khi lệnh thành công, họ có thể xác nhận artifact và hiểu những file nào sẽ bị `clean` xóa ở lượt sau.

**Nguyên tắc cốt lõi:** mỗi target Ant công khai cần có một hợp đồng dễ tìm và có thể kiểm chứng về **cách gọi, đầu vào, đầu ra, điều kiện chạy, dependency, tác dụng phụ, lỗi và khả năng chạy lại**. Giữ `description` trong XML đồng bộ với tài liệu build giúp các lệnh Ant trở thành giao diện ổn định khi mã nguồn, pipeline và đội ngũ phát triển thay đổi.


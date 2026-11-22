# Resolve, retrieve và tạo classpath theo Ivy configuration

Apache Ivy là công cụ quản lý dependency có thể tích hợp trực tiếp với Apache Ant. Ivy đọc mô tả module trong `ivy.xml`, giải quyết dependency trực tiếp và bắc cầu, lưu artifact vào cache, sau đó cho phép build lấy các thư viện cần thiết theo từng configuration.

Trong quy trình này, ba thao tác cần phân biệt rõ:

- **Resolve**: phân tích dependency graph cho configuration được yêu cầu, chọn phiên bản phù hợp và tải những artifact còn thiếu vào Ivy cache.
- **Retrieve**: sao chép artifact đã resolve từ cache ra thư mục của dự án theo một mẫu đường dẫn.
- **Tạo classpath**: tạo một Ant `Path` tham chiếu trực tiếp đến các artifact trong cache để task như `<javac>` hoặc `<java>` sử dụng.

Ivy configuration quyết định nhóm dependency nào được chọn. Nhờ đó, compile, runtime và test có thể dùng những tập thư viện khác nhau mà vẫn chia sẻ cùng một mô tả dependency.

## 1. Ivy configuration là gì?

Một module Ivy có thể khai báo nhiều configuration. Mỗi configuration mô tả một góc nhìn hoặc một nhóm dependency phục vụ một mục đích cụ thể. Các tên thường gặp là `compile`, `runtime`, `test`, `provided` hoặc `default`, nhưng tên configuration do module định nghĩa và không bị giới hạn ở các tên này.

Ví dụ trong `ivy.xml`:

```xml
<ivy-module version="2.0">
    <info organisation="com.example" module="sample-app"/>

    <configurations>
        <conf name="compile" visibility="public"
              description="Libraries needed to compile application sources"/>
        <conf name="runtime" extends="compile" visibility="public"
              description="Libraries needed to run the application"/>
        <conf name="test" extends="runtime" visibility="private"
              description="Libraries needed by tests"/>
    </configurations>

    <dependencies>
        <dependency org="org.apache.commons" name="commons-lang3"
                    rev="3.14.0" conf="compile->default"/>
        <dependency org="org.slf4j" name="slf4j-api"
                    rev="2.0.12" conf="runtime->default"/>
        <dependency org="junit" name="junit"
                    rev="4.13.2" conf="test->default"/>
    </dependencies>
</ivy-module>
```

Trong ví dụ, `runtime` kế thừa `compile`, còn `test` kế thừa `runtime`. Vì vậy, configuration `test` bao gồm các dependency được khai báo cho `compile`, `runtime` và `test` theo quan hệ kế thừa. `compile` chỉ chứa dependency cần để biên dịch; `runtime` bổ sung thư viện chỉ cần khi chạy; `test` bổ sung thư viện kiểm thử.

Các configuration không phải là Ant target. Target mô tả công việc cần thực thi trong build file; configuration mô tả tập dependency mà Ivy giải quyết cho một module.

### 1.1. Ý nghĩa của `extends`

Thuộc tính `extends` khai báo configuration hiện tại kế thừa configuration khác. Ví dụ:

```xml
<configurations>
    <conf name="compile"/>
    <conf name="runtime" extends="compile"/>
    <conf name="test" extends="runtime"/>
</configurations>
```

Quan hệ này có thể hình dung:

```text
compile
   ^
   |
runtime
   ^
   |
test
```

`runtime` bao gồm nội dung dependency của `compile`; `test` bao gồm nội dung của `runtime` và do đó cả `compile`. Đây là quan hệ kế thừa một chiều: dependency chỉ khai báo cho `test` không tự động trở thành dependency của `compile`.

Chỉ tạo quan hệ kế thừa khi tập dependency thực sự có quan hệ bao hàm. Nếu cấu hình runtime không nên kéo theo một thư viện chỉ dùng để biên dịch hoặc kiểm thử, hãy thiết kế các configuration và mapping phù hợp thay vì kế thừa máy móc.

### 1.2. Ánh xạ configuration của dependency

Trong một dependency declaration, thuộc tính `conf` ánh xạ configuration của module hiện tại sang configuration của module được phụ thuộc.

Ví dụ:

```xml
<dependency org="org.apache.commons" name="commons-lang3"
            rev="3.14.0" conf="compile->default"/>
```

Phần bên trái `compile` là configuration của module hiện tại. Phần bên phải `default` là configuration được yêu cầu ở module `commons-lang3`. Khi Ivy resolve configuration `compile` của ứng dụng, dependency này được lấy theo configuration `default` của thư viện.

Một dependency có thể được ánh xạ vào nhiều configuration:

```xml
<dependency org="com.example" name="shared-api"
            rev="1.5" conf="compile->default;runtime->default"/>
```

Ở đây cùng một thư viện được dùng trong cả `compile` và `runtime`. Có thể dùng ký hiệu wildcard hoặc mapping khác khi cần, nhưng khai báo tường minh thường dễ đọc hơn khi mới xây dựng module.

## 2. Chuẩn bị Ivy để Ant nhận diện các task

Ivy cung cấp các Ant task như `ivy:settings`, `ivy:resolve`, `ivy:retrieve`, `ivy:cachepath` và `ivy:report`. Ant cần nạp JAR của Ivy để nhận diện namespace task này.

Có thể cài JAR Ivy vào `${ANT_HOME}/lib`, hoặc thêm nó vào classpath khi chạy Ant, ví dụ:

```bash
ant -lib tools/ivy/lib/ivy.jar resolve
```

Khi JAR Ivy đã có trên classpath của Ant, khai báo namespace trong project:

```xml
<project name="sample-app" default="resolve"
         xmlns:ivy="antlib:org.apache.ivy.ant">
    <!-- Các target Ivy nằm ở đây. -->
</project>
```

Namespace `antlib:org.apache.ivy.ant` cho phép gọi task bằng tiền tố `ivy:`. Nếu Ant báo không tìm thấy namespace hoặc task Ivy, hãy kiểm tra Ivy JAR có được nạp đúng vào tiến trình Ant hay chưa và phiên bản JAR có tương thích với môi trường Java/Ant đang dùng không.

## 3. Cấu hình repository bằng `ivysettings.xml`

Ivy cần biết nơi tìm metadata và artifact. Cấu hình resolver thường được đặt trong `ivysettings.xml`.

Ví dụ sử dụng Maven Central thông qua resolver tương thích Maven 2:

```xml
<ivysettings>
    <settings defaultResolver="central"/>
    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2"/>
    </resolvers>
</ivysettings>
```

`defaultResolver` chọn resolver mặc định. Resolver `ibiblio` với `m2compatible="true"` hiểu layout repository kiểu Maven. Trong môi trường doanh nghiệp, có thể thay bằng Nexus, Artifactory, repository nội bộ hoặc một chain resolver được quản trị tập trung.

Nạp cấu hình này bằng task `ivy:settings` trước khi resolve:

```xml
<target name="ivy-init">
    <ivy:settings file="${basedir}/ivysettings.xml"/>
</target>
```

Nếu dự án dùng cấu hình Ivy mặc định của máy, có thể bỏ thuộc tính `file`; tuy nhiên, một build cần tái lập trên nhiều máy nên khai báo resolver rõ ràng và quản lý tệp settings cùng dự án hoặc cung cấp qua cấu hình build chuẩn.

## 4. Resolve dependency theo configuration

Task `ivy:resolve` đọc `ivy.xml`, tính toán dependency graph cho configuration được yêu cầu, áp dụng quy tắc chọn phiên bản và tải các artifact cần thiết vào cache của Ivy.

Ví dụ resolve configuration compile:

```xml
<target name="resolve-compile" depends="ivy-init">
    <ivy:resolve file="${basedir}/ivy.xml" conf="compile"/>
</target>
```

Khi target chạy, Ivy chỉ resolve configuration `compile` cùng các dependency liên quan theo mapping và quan hệ kế thừa. Nếu dependency có dependency bắc cầu, Ivy cũng xử lý chúng theo metadata và quy tắc resolve.

Có thể resolve nhiều configuration trong một lần:

```xml
<ivy:resolve file="${basedir}/ivy.xml" conf="compile,runtime,test"/>
```

Danh sách configuration được phân tách bằng dấu phẩy. Chỉ yêu cầu những configuration mà các bước build tiếp theo cần dùng, để tránh tải và xử lý thư viện không liên quan.

### 4.1. Resolve không đồng nghĩa với retrieve

Resolve làm việc với dependency graph và cache của Ivy. Artifact được lưu trong cache theo cấu trúc do Ivy quản lý. Resolve không có nghĩa là tất cả JAR đã được sao chép vào thư mục `lib` của dự án.

Điều này quan trọng khi phân biệt hai cách sử dụng thư viện:

- Nếu task cần một classpath, có thể tạo Ant Path từ cache bằng `ivy:cachepath`.
- Nếu cần các JAR hiện diện trong thư mục của dự án để đóng gói, kiểm tra hoặc chạy bằng một công cụ khác, dùng `ivy:retrieve`.

Không cần retrieve chỉ để `<javac>` có thể nhìn thấy dependency nếu bạn đã tạo classpath bằng `ivy:cachepath`.

### 4.2. Xem báo cáo resolve

Ivy có thể tạo báo cáo dependency để xem phiên bản được chọn và quan hệ bắc cầu:

```xml
<target name="dependency-report" depends="resolve-compile">
    <ivy:report todir="${build.dir}/ivy-reports"/>
</target>
```

Báo cáo hữu ích khi một dependency có nhiều phiên bản được yêu cầu bởi các nhánh khác nhau. Ivy có thể chọn một revision theo conflict manager và cấu hình resolver. Hãy xem báo cáo khi cần hiểu vì sao một phiên bản cụ thể xuất hiện trong kết quả resolve.

## 5. Retrieve artifact ra thư mục dự án

Task `ivy:retrieve` sao chép artifact đã resolve từ cache Ivy ra một thư mục do build chỉ định. Thuộc tính quan trọng nhất là `pattern`, mô tả cấu trúc đường dẫn đích.

Ví dụ retrieve configuration runtime:

```xml
<target name="retrieve-runtime" depends="ivy-init">
    <ivy:resolve file="${basedir}/ivy.xml" conf="runtime"/>
    <ivy:retrieve conf="runtime"
                  pattern="${basedir}/lib/runtime/[artifact]-[revision].[ext]"/>
</target>
```

Với pattern trên, một artifact có thể được lưu thành đường dẫn như:

```text
lib/runtime/commons-lang3-3.14.0.jar
lib/runtime/slf4j-api-2.0.12.jar
```

Tên file thực tế phụ thuộc artifact, revision, classifier và extension của dependency. Pattern có thể dùng các token Ivy như `[organisation]`, `[module]`, `[artifact]`, `[revision]`, `[type]`, `[ext]`, `[classifier]` và `[conf]` để tổ chức thư viện.

### 5.1. Tổ chức thư mục theo configuration

Khi retrieve nhiều configuration, thêm `[conf]` vào pattern để tách các tập thư viện:

```xml
<ivy:retrieve conf="compile,runtime,test"
              pattern="${basedir}/lib/[conf]/[artifact]-[revision].[ext]"/>
```

Ví dụ cấu trúc:

```text
lib/
├── compile/
├── runtime/
└── test/
```

Lưu ý rằng configuration kế thừa có thể chứa cùng một dependency trong nhiều nhóm. Khi retrieve nhiều configuration và dùng `[conf]`, cùng một artifact có thể xuất hiện ở nhiều thư mục. Điều này có thể hữu ích nếu mỗi nhóm cần được sử dụng độc lập, nhưng cũng làm tăng dung lượng và số bản sao.

Nếu không cần tách thư viện theo configuration, hãy chọn một configuration cụ thể hoặc dùng pattern chung phù hợp. Tránh retrieve tất cả cấu hình một cách máy móc.

### 5.2. Đồng bộ thư mục retrieve bằng `sync`

Thuộc tính `sync="true"` yêu cầu Ivy đồng bộ kết quả retrieve với tập artifact hiện tại: các tệp thuộc pattern đích nhưng không còn trong kết quả retrieve có thể bị xóa.

Ví dụ:

```xml
<ivy:retrieve conf="runtime"
              pattern="${basedir}/build/ivy-runtime/[artifact]-[revision].[ext]"
              sync="true"/>
```

Chỉ bật `sync` khi thư mục đích được dành riêng cho artifact do Ivy retrieve. Không trỏ pattern vào thư mục chứa tệp thủ công hoặc dữ liệu không thuộc Ivy quản lý, vì các tệp không còn thuộc kết quả resolve nhưng khớp pattern có thể bị xóa.

Retrieve thường hữu ích khi một công cụ khác cần các JAR nằm trong thư mục dự án hoặc khi muốn kiểm tra trực tiếp nội dung dependency đã lấy về. Nếu chỉ cần classpath cho task Ant, `cachepath` thường tránh được việc sao chép không cần thiết.

## 6. Tạo Ant classpath từ Ivy cache bằng `ivy:cachepath`

Task `ivy:cachepath` tạo một Ant Path reference từ các artifact trong cache của Ivy theo configuration đã resolve. Nó không sao chép JAR ra thư mục dự án.

Ví dụ:

```xml
<target name="compile" depends="resolve-compile">
    <ivy:cachepath conf="compile" pathid="compile.classpath"/>

    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

`pathid="compile.classpath"` đặt ID cho Ant Path vừa tạo. Nested `<classpath refid="compile.classpath"/>` trong `<javac>` sử dụng đúng các JAR mà Ivy đã resolve cho configuration `compile`.

Ưu điểm của `cachepath`:

- Không cần sao chép JAR vào thư mục `lib` của dự án.
- Tận dụng Ivy cache, tránh retrieve lại cùng artifact vào thư mục làm việc.
- Classpath được tạo theo configuration, nên compile không vô tình nhận thư viện chỉ dành cho test.
- Có thể tham chiếu cùng Path ở nhiều task trong cùng build.

### 6.1. Tạo classpath runtime

Ứng dụng khi chạy thường cần configuration `runtime`:

```xml
<target name="run" depends="resolve-runtime">
    <ivy:cachepath conf="runtime" pathid="runtime.classpath"/>

    <java classname="com.example.Main" fork="true" failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
            <path refid="runtime.classpath"/>
        </classpath>
    </java>
</target>
```

Classpath của ứng dụng gồm class output của dự án và dependency runtime. `fork="true"` chạy chương trình trong JVM con; `failonerror="true"` làm build thất bại nếu chương trình kết thúc với lỗi.

Nếu task `<java>` chạy trong cùng JVM Ant, hành vi classloading và các tùy chọn JVM khác có thể khác. Hãy chọn `fork` theo nhu cầu ứng dụng và cấu hình runtime tương ứng.

### 6.2. Tạo classpath test

Configuration `test` thường kế thừa runtime và compile, đồng thời bổ sung framework kiểm thử:

```xml
<target name="test" depends="resolve-test">
    <ivy:cachepath conf="test" pathid="test.classpath"/>

    <path id="test.run.classpath">
        <pathelement location="build/classes"/>
        <pathelement location="build/test-classes"/>
        <path refid="test.classpath"/>
    </path>

    <!-- Truyền test.run.classpath cho test runner của dự án. -->
</target>
```

Task test runner thực tế có thể là JUnit task, một task khác hoặc tiến trình Java được khởi chạy bằng `<java>`. Hãy bảo đảm class output của test và application cùng có mặt trên classpath, ngoài các dependency thuộc configuration `test`.

## 7. Phân biệt `retrieve`, `cachepath` và `classpath` tự khai báo

Ba cách này liên quan đến dependency nhưng tạo ra kết quả khác nhau:

| Cơ chế | Kết quả | Khi nào dùng |
|---|---|---|
| `ivy:resolve` | Dependency graph và artifact trong Ivy cache | Bước chuẩn bị bắt buộc trước khi lấy dependency theo configuration |
| `ivy:retrieve` | Các tệp artifact được sao chép ra thư mục dự án theo pattern | Khi cần JAR trên filesystem của dự án hoặc cho công cụ ngoài Ant |
| `ivy:cachepath` | Một Ant Path reference trỏ đến artifact trong cache | Khi task Ant cần compile/runtime/test classpath |
| `<path>` tự khai báo | Path từ các đường dẫn do build file chỉ định | Khi cần thêm class output, thư viện nội bộ hoặc đường dẫn bổ sung |

`ivy:cachepath` không thay thế `ivy:resolve`; nó sử dụng kết quả resolve. `ivy:retrieve` cũng dựa trên dependency đã resolve. Nếu gọi retrieve hoặc cachepath trước khi resolve configuration cần thiết, kết quả có thể rỗng hoặc không đúng với mục tiêu của build.

## 8. Một build file sử dụng nhiều configuration

Ví dụ dưới đây kết hợp resolve, cachepath, retrieve và các classpath riêng cho compile, runtime và test.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ivy-ant-demo" default="compile"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="ivy.file" value="${basedir}/ivy.xml"/>
    <property name="ivy.settings.file" value="${basedir}/ivysettings.xml"/>
    <property name="build.dir" value="${basedir}/build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>
    <property name="test.classes.dir" value="${build.dir}/test-classes"/>
    <property name="lib.dir" value="${build.dir}/ivy-libs"/>

    <target name="ivy-init">
        <ivy:settings file="${ivy.settings.file}"/>
    </target>

    <target name="resolve-compile" depends="ivy-init">
        <ivy:resolve file="${ivy.file}" conf="compile"/>
    </target>

    <target name="resolve-runtime" depends="ivy-init">
        <ivy:resolve file="${ivy.file}" conf="runtime"/>
    </target>

    <target name="resolve-test" depends="ivy-init">
        <ivy:resolve file="${ivy.file}" conf="test"/>
    </target>

    <target name="compile" depends="resolve-compile">
        <ivy:cachepath conf="compile" pathid="compile.classpath"/>
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="retrieve-runtime" depends="resolve-runtime">
        <ivy:retrieve conf="runtime"
                      pattern="${lib.dir}/runtime/[artifact]-[revision].[ext]"
                      sync="true"/>
    </target>

    <target name="prepare-test" depends="compile,resolve-test">
        <ivy:cachepath conf="test" pathid="test.dependency.classpath"/>
        <mkdir dir="${test.classes.dir}"/>
        <javac srcdir="src/test/java"
               destdir="${test.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="test.dependency.classpath"/>
            </classpath>
        </javac>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

</project>
```

Build file giả định có cấu trúc `ivy.xml` và `ivysettings.xml` như các ví dụ trước, cùng thư mục source `src/main/java` và `src/test/java`. Để biên dịch test, dependency configuration `test` phải bao gồm framework và các API mà test sử dụng.

Mỗi target resolve configuration cần dùng trước khi gọi `cachepath` hoặc `retrieve`. Ví dụ, `compile` resolve `compile`; `retrieve-runtime` resolve `runtime`; `prepare-test` resolve `test`. Cách tổ chức này tránh sử dụng nhầm kết quả resolve của configuration khác.

Thư mục retrieve nằm dưới `build/ivy-libs/runtime`, một vùng output riêng. `sync="true"` có thể dọn các artifact cũ trong vùng này khi tập dependency thay đổi, trong khi classpath của compiler lấy trực tiếp từ Ivy cache.

## 9. Quy trình resolve và cache

Ivy lưu metadata và artifact trong cache dùng chung của người dùng. Khi resolve, Ivy kiểm tra metadata, phiên bản và artifact cần thiết. Nếu artifact đã có trong cache và vẫn hợp lệ theo chính sách resolve, Ivy có thể dùng lại mà không tải lại toàn bộ dữ liệu.

Các revision cố định như `3.14.0` giúp kết quả dễ tái lập hơn so với revision động như `latest.integration` hoặc dải revision. Revision động có thể trỏ đến phiên bản mới hơn ở lần resolve sau, tùy metadata và chính sách cache.

Khi cần làm mới metadata hoặc revision động, Ivy có các tùy chọn resolve như `refresh`. Chỉ bật refresh khi có lý do, vì nó có thể khiến Ivy truy vấn repository lại và làm build phụ thuộc vào trạng thái repository tại thời điểm chạy.

Đối với build cần tái lập:

- Khóa revision của dependency quan trọng thay vì dùng revision động tùy tiện.
- Quản lý resolver và repository rõ ràng.
- Dùng cùng một `ivy.xml` và `ivysettings.xml` trên máy phát triển và CI.
- Kiểm tra báo cáo resolve khi có xung đột phiên bản.
- Không sửa thủ công nội dung cache Ivy; hãy để Ivy quản lý cache.

## 10. Xung đột phiên bản và dependency bắc cầu

Một dependency có thể kéo theo các dependency khác. Ví dụ, thư viện A phụ thuộc B phiên bản 1, trong khi thư viện C phụ thuộc B phiên bản 2. Khi đó Ivy cần áp dụng conflict manager để quyết định revision nào được sử dụng trong dependency graph.

Ivy có thể chọn revision theo chiến lược được cấu hình, chẳng hạn `latest-revision` trong nhiều thiết lập mặc định. Kết quả còn phụ thuộc resolver, metadata và các constraint trong module. Không nên giả định chỉ cần nhìn dependency trực tiếp trong `ivy.xml` là biết toàn bộ classpath cuối cùng.

Dùng báo cáo dependency:

```xml
<target name="report-dependencies" depends="resolve-test">
    <ivy:report todir="build/ivy-reports"/>
</target>
```

Mở báo cáo để xem dependency trực tiếp, dependency bắc cầu, revision được chọn và những phiên bản bị loại. Nếu cần cố định phiên bản, có thể dùng dependency declaration, override hoặc constraint theo cú pháp Ivy phù hợp với module và chính sách của dự án.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant không nhận diện `ivy:resolve` | Ivy JAR chưa có trên classpath của Ant hoặc namespace khai báo sai | Cài Ivy JAR vào `${ANT_HOME}/lib`, dùng `-lib` hoặc kiểm tra namespace `antlib:org.apache.ivy.ant` |
| Resolve không tìm thấy dependency | Resolver sai, repository không truy cập được, revision không tồn tại hoặc metadata không khớp | Kiểm tra `ivysettings.xml`, tọa độ dependency, mạng và log resolve |
| Resolve chỉ lấy một phần dependency | Chỉ yêu cầu configuration không chứa dependency mong muốn hoặc mapping sai | Kiểm tra `conf` trong `ivy:resolve`, `extends` và mapping `conf` của dependency |
| Runtime classpath thiếu thư viện | Dùng nhầm `compile` thay vì `runtime`, hoặc runtime config chưa khai báo đúng | Resolve `runtime` và tạo `ivy:cachepath conf="runtime"` |
| Test không tìm thấy framework | Test configuration chưa khai báo dependency hoặc chưa được resolve | Khai báo dependency vào `test`, resolve `test` và tạo test classpath |
| Retrieve không tạo file ở thư mục mong muốn | Pattern sai, configuration chưa resolve hoặc đường dẫn đích khác dự kiến | Kiểm tra `pattern`, `conf`, quyền ghi và kết quả resolve |
| Tệp cũ vẫn còn trong thư mục retrieve | Không bật `sync` hoặc thư mục đích chứa dữ liệu ngoài phạm vi pattern | Dùng thư mục retrieve riêng và cân nhắc `sync="true"` |
| Một artifact xuất hiện nhiều lần ở các thư mục | Retrieve nhiều configuration kế thừa và pattern có `[conf]` | Chỉ retrieve configuration cần thiết hoặc chấp nhận tách artifact theo conf |
| `cachepath` tạo path rỗng | Chưa resolve configuration tương ứng hoặc pathid/conf sai | Đặt `ivy:resolve` trước `ivy:cachepath`, kiểm tra tên configuration |
| Phiên bản được chọn không như mong đợi | Có dependency bắc cầu hoặc conflict manager chọn revision khác | Mở Ivy report và kiểm tra graph, revision và resolver |

## 12. Thực hành lựa chọn cách lấy thư viện

Giả sử mục tiêu là biên dịch ứng dụng. Build cần các JAR trên classpath của `<javac>` nhưng không cần chúng nằm trong thư mục dự án. Dùng `resolve` rồi `cachepath`:

```xml
<ivy:resolve file="ivy.xml" conf="compile"/>
<ivy:cachepath conf="compile" pathid="compile.classpath"/>
```

Nếu một công cụ đóng gói hoặc script bên ngoài cần các JAR vật lý trong một thư mục, dùng `retrieve`:

```xml
<ivy:retrieve conf="runtime"
              pattern="build/dependencies/[artifact]-[revision].[ext]"/>
```

Nếu build vừa cần classpath compile vừa cần thư viện runtime để chạy ứng dụng, tạo hai path từ hai configuration:

```xml
<ivy:cachepath conf="compile" pathid="compile.classpath"/>
<ivy:cachepath conf="runtime" pathid="runtime.classpath"/>
```

Không cần retrieve cùng dependency chỉ để tạo hai classpath này. Hai path tham chiếu các artifact trong cache theo configuration đã resolve.

## 13. Checklist làm việc với Ivy configuration

- [ ] Đã khai báo các configuration cần dùng trong `ivy.xml`.
- [ ] Quan hệ `extends` phản ánh đúng nhóm dependency được kế thừa.
- [ ] Mapping `conf` của mỗi dependency trỏ đúng configuration của module được phụ thuộc.
- [ ] Ivy JAR được nạp vào Ant và namespace task được khai báo.
- [ ] Resolver được cấu hình rõ trong `ivysettings.xml` hoặc môi trường build đã quản lý.
- [ ] Đã gọi `ivy:resolve` cho đúng configuration trước retrieve hoặc cachepath.
- [ ] Dùng `ivy:retrieve` khi cần artifact trên filesystem và chọn pattern rõ ràng.
- [ ] Chỉ dùng `sync="true"` với thư mục retrieve dành riêng cho Ivy.
- [ ] Dùng `ivy:cachepath` để tạo compile, runtime hoặc test classpath theo nhu cầu.
- [ ] Class output của dự án được thêm riêng vào runtime/test classpath khi cần.
- [ ] Đã xem Ivy report khi dependency bắc cầu hoặc xung đột phiên bản gây bất ngờ.
- [ ] Revision và repository được quản lý để build có thể tái lập.

## 14. Tài liệu tham khảo

- [Apache Ivy — Ivy Ant Tasks](https://ant.apache.org/ivy/history/latest-milestone/use/ant.html): cách tích hợp task Ivy vào Ant, gồm resolve, retrieve, cachepath và report.
- [Apache Ivy — Configurations](https://ant.apache.org/ivy/history/latest-milestone/concept.html#configurations): khái niệm configuration và cách tổ chức dependency theo các góc nhìn của module.
- [Apache Ivy — Retrieve](https://ant.apache.org/ivy/history/latest-milestone/use/retrieve.html): pattern và hành vi sao chép artifact ra thư mục dự án.
- [Apache Ivy — Cache](https://ant.apache.org/ivy/history/latest-milestone/concept.html#cache): vai trò của cache trong quá trình resolve và sử dụng artifact.

Khi thiết kế build Ant với Ivy, hãy bắt đầu từ các configuration thể hiện đúng nhu cầu compile, runtime và test. Sau đó resolve configuration tương ứng, dùng `cachepath` để tạo classpath cho task Ant hoặc `retrieve` khi cần các JAR trên filesystem. Tách rõ ba bước này giúp dependency graph, thư mục thư viện và classpath của từng giai đoạn luôn có mục đích cụ thể.

# Giới hạn quản lý dependency của Ant lõi

Apache Ant lõi là công cụ tự động hóa build dựa trên target và task. Nó có thể biên dịch Java, chạy test, đóng gói JAR/WAR, sao chép thư viện và tạo classpath từ các thư mục hoặc tệp JAR. Tuy nhiên, Ant lõi không cung cấp một hệ thống quản lý dependency cấp module hoàn chỉnh giống Maven hoặc Gradle.

Điểm khác biệt quan trọng nằm ở việc **khai báo và sử dụng thư viện** so với **tìm kiếm, phân giải và quản lý toàn bộ đồ thị dependency**. Ant có thể đưa một JAR đã có sẵn vào classpath, nhưng tự nó không hiểu tọa độ artifact theo dạng group/module/version, không tự truy vấn repository Maven để tìm dependency bắc cầu, và không tự giải quyết xung đột phiên bản giữa các module.

Khi dự án chỉ có ít thư viện và cấu trúc ổn định, quản lý JAR thủ công có thể đủ dùng. Khi số lượng thư viện tăng, có dependency bắc cầu, nhiều phiên bản hoặc nhiều môi trường build, nhóm thường kết hợp Ant với Apache Ivy hoặc một công cụ quản lý dependency chuyên biệt.

## 1. Ant lõi làm được gì với thư viện?

Ant cung cấp các data type và task để mô tả, kết hợp và sử dụng đường dẫn thư viện. Các thành phần thường gặp:

- `<path>` và `<pathelement>` mô tả classpath gồm thư mục hoặc file.
- `<fileset>` chọn các JAR theo pattern trong một thư mục.
- `classpath` hoặc `classpathref` đưa các đường dẫn đó vào task như `<javac>`.
- `<copy>` có thể sao chép thư viện từ vị trí này sang vị trí khác.
- `<jar>` và `<war>` đóng gói nội dung theo cấu trúc artifact.
- `<get>` có thể tải một file từ URL được chỉ định.

Ví dụ, nếu thư viện đã được đặt trong thư mục `lib`, Ant có thể xây dựng compile classpath:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
~~~

Đoạn build này giả định mọi JAR cần cho compile đã được cung cấp trong `lib`. Ant chọn các file khớp `*.jar` và đưa chúng vào classpath của compiler.

Điều Ant đang làm là sử dụng một tập file đã biết. Nó không tìm hiểu JAR nào cần một JAR khác, phiên bản nào tương thích, hay thư viện nào nên được tải từ repository.

## 2. Những việc Ant lõi không tự đảm nhiệm

Quản lý dependency hiện đại thường gồm nhiều công việc liên quan:

1. Khai báo thư viện bằng tọa độ có cấu trúc, ví dụ tổ chức, tên module và phiên bản.
2. Tìm artifact trong một hoặc nhiều repository.
3. Đọc metadata để biết artifact phụ thuộc vào những module nào khác.
4. Phân giải toàn bộ dependency bắc cầu (transitive dependencies).
5. Phát hiện và xử lý khi nhiều nhánh yêu cầu các phiên bản khác nhau của cùng module.
6. Chọn dependency theo cấu hình như compile, runtime, test hoặc optional.
7. Lưu cache để tránh tải lại artifact không cần thiết.
8. Kiểm soát phiên bản và nguồn tải để build có thể tái lập.

Ant lõi không cung cấp một dependency resolver tổng quát cho các nhiệm vụ trên. Các target và task trong `build.xml` do dự án định nghĩa; Ant thực hiện những gì build file yêu cầu.

| Nhu cầu | Ant lõi | Hệ thống dependency chuyên dụng |
|---|---|---|
| Dùng một JAR đã có trên máy | Có, qua `path`/`fileset` | Có |
| Kết hợp nhiều thư viện thành classpath | Có | Có |
| Chọn file theo pattern | Có | Có |
| Tải một file từ URL đã biết | Có thể dùng `<get>` | Có |
| Khai báo module bằng tọa độ và phiên bản | Không có mô hình dependency module tích hợp | Có |
| Tự đọc metadata dependency của artifact | Không có resolver tích hợp | Có |
| Tự tìm dependency bắc cầu | Không | Có |
| Giải quyết xung đột phiên bản theo đồ thị | Không | Có, theo quy tắc của công cụ |
| Quản lý cấu hình compile/runtime/test | Phải tự tổ chức path và target | Có mô hình configuration/scope |
| Cache và tái sử dụng artifact theo tọa độ | Không có dependency cache tích hợp | Có |

Điều này không làm Ant mất khả năng build dự án Java. Nó chỉ có nghĩa trách nhiệm chuẩn bị và kiểm soát thư viện thuộc về build file, script, quy trình CI hoặc công cụ tích hợp thêm.

## 3. Dependency thủ công bằng thư mục `lib`

Cách đơn giản nhất là đưa các JAR vào repository cùng source code:

~~~text
project/
├── build.xml
├── src/
│   ├── main/java/
│   └── test/java/
├── lib/
│   ├── commons-lang3-3.14.0.jar
│   └── jackson-core-2.17.1.jar
└── lib-test/
    └── junit-4.13.2.jar
~~~

Build file tạo các path riêng:

~~~xml
<path id="main.compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <path refid="main.compile.classpath"/>
    <fileset dir="lib-test">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Target compile dùng thư viện chính:

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="main.compile.classpath"/>
    </javac>
</target>
~~~

Target test compile thêm class đã biên dịch và thư viện test:

~~~xml
<target name="test-compile" depends="compile">
    <mkdir dir="build/test-classes"/>
    <javac srcdir="src/test/java"
           destdir="build/test-classes"
           includeantruntime="false">
        <classpath refid="test.classpath"/>
    </javac>
</target>
~~~

Cách này dễ hiểu, không cần dịch vụ repository khi build và cho phép kiểm soát chính xác JAR được dùng. Tuy nhiên, nhóm phải tự tải, cập nhật, kiểm tra nguồn gốc, đổi tên, loại bỏ phiên bản cũ và giữ classpath đồng nhất giữa máy phát triển với CI.

## 4. Dependency bắc cầu là giới hạn quan trọng

Một thư viện thường phụ thuộc vào các thư viện khác. Ví dụ:

~~~text
Ứng dụng
   |
   +--> library-a.jar
   |       |
   |       +--> common-util.jar
   |       +--> logging-api.jar
   |
   +--> library-b.jar
           |
           +--> common-util.jar
           +--> json-core.jar
~~~

Nếu chỉ đặt `library-a.jar` và `library-b.jar` vào thư mục `lib`, Ant không tự đọc metadata bên trong để biết cần thêm `common-util.jar`, `logging-api.jar` và `json-core.jar`. Người xây dựng phải biết và cung cấp đầy đủ các JAR cần thiết.

Nếu thiếu một dependency bắc cầu, compiler có thể báo `package ... does not exist` hoặc `cannot find symbol`. Nếu compile classpath có đủ thư viện nhưng runtime classpath thiếu một thư viện, chương trình có thể biên dịch thành công nhưng lỗi khi chạy với `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Khi dùng JAR thủ công, cần có quy trình lập danh sách dependency đầy đủ. Có thể ghi danh sách và phiên bản trong tài liệu hoặc file cấu hình riêng, nhưng Ant lõi không tự biến danh sách đó thành một đồ thị dependency được phân giải.

## 5. Xung đột phiên bản không được Ant lõi tự giải quyết

Một tình huống khác xảy ra khi hai thư viện cần các phiên bản khác nhau của cùng dependency:

~~~text
Ứng dụng
   |
   +--> library-a --> common-util 1.8
   |
   +--> library-b --> common-util 2.2
~~~

Nếu thư mục `lib` chứa cả `common-util-1.8.jar` và `common-util-2.2.jar`, Ant có thể đưa cả hai vào classpath nếu FileSet chọn cả hai. Ant không phân tích metadata module để tự chọn phiên bản phù hợp.

Khi cùng một class xuất hiện trong nhiều JAR, kết quả có thể phụ thuộc thứ tự classpath và cách classloader tìm lớp. Đây là nguồn gây lỗi khó chẩn đoán: build có thể compile được nhưng runtime nạp phiên bản khác với phiên bản mà nhóm dự kiến.

Một số cách xử lý khi quản lý thủ công:

- Chỉ giữ một phiên bản của mỗi module trong classpath.
- Ghi rõ phiên bản được chọn và lý do chọn.
- Kiểm tra các thư viện có yêu cầu phiên bản tối thiểu hoặc tối đa hay không.
- Xóa JAR cũ khỏi thư mục được FileSet quét.
- Kiểm tra classpath compile, test và runtime có cùng quyết định phiên bản hay không.

Đây là quy trình do nhóm tự quản lý. Khi dependency graph lớn, việc làm thủ công dễ bỏ sót và nên chuyển cho công cụ resolver.

## 6. `<get>` không thay thế dependency resolver

Ant có task `<get>` để tải một tài nguyên từ URL đã biết:

~~~xml
<target name="download-library">
    <mkdir dir="lib"/>
    <get src="https://repo.example.invalid/releases/com/example/library/1.2.0/library-1.2.0.jar"
         dest="lib/library-1.2.0.jar"
         usetimestamp="true"/>
</target>
~~~

Task này có thể hữu ích cho một file có URL cụ thể. Nhưng nó không tự:

- Đọc POM hoặc Ivy metadata để phát hiện dependency bắc cầu.
- Chọn phiên bản theo quy tắc xung đột.
- Tính toán classpath compile/runtime/test.
- Kiểm soát toàn bộ repository và cache dependency.
- Bảo đảm URL luôn trỏ tới artifact bất biến.

Nếu cần tải nhiều JAR, người viết build phải tự khai báo URL, đích lưu và quan hệ giữa chúng. Một script tự tải hàng loạt vẫn là quy trình tải file do dự án quản lý; nó không có đầy đủ semantics của dependency resolver.

Không nên dùng URL động hoặc đường dẫn không cố định cho dependency quan trọng. Nếu repository cho phép ghi đè artifact cùng tọa độ, cùng một build file có thể nhận nội dung khác ở hai thời điểm. Nên dùng phiên bản bất biến, checksum hoặc chữ ký theo chính sách của tổ chức.

## 7. Tự quản lý classpath có thể trở nên khó bảo trì

Một build nhỏ có thể dùng một path chung:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Nhưng khi dự án lớn lên, có thể cần nhiều nhóm thư viện:

- Compile: cần để biên dịch source chính.
- Runtime: cần khi chạy ứng dụng nhưng không nhất thiết cần để compile.
- Test: chỉ dùng trong test, ví dụ JUnit hoặc mocking framework.
- Annotation processor: công cụ chạy trong compile để sinh mã hoặc kiểm tra source.
- Tooling: công cụ chỉ dùng cho task build, không thuộc classpath ứng dụng.

Nếu gom tất cả vào một thư mục `lib` và đưa toàn bộ vào mọi classpath, build có thể vô tình compile dựa trên thư viện chỉ nên có ở test hoặc runtime. Điều này làm che giấu dependency khai báo thiếu và tạo khác biệt giữa môi trường build với môi trường chạy.

Nên phân tách path theo vai trò:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib/compile">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib/runtime">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <path refid="compile.classpath"/>
    <fileset dir="lib/test">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Các thư mục này là quy ước của dự án, không phải cấu trúc bắt buộc của Ant. Mục tiêu là để classpath phản ánh đúng mục đích sử dụng và tránh đưa mọi JAR vào mọi bước.

## 8. Quản lý phiên bản và tính tái lập khi dùng JAR thủ công

Nếu nhóm quyết định giữ dependency trong repository, cần kiểm soát chúng như một phần của source build:

1. Ghi tên module, phiên bản, nguồn tải và license.
2. Không đổi nội dung JAR nhưng giữ nguyên tên file.
3. Dùng checksum hoặc chữ ký để kiểm tra tính toàn vẹn theo chính sách dự án.
4. Chỉ giữ các phiên bản thực sự cần thiết trong thư mục classpath.
5. Ghi nhận JDK, Ant và dependency set được dùng trong CI.
6. Cập nhật các thư viện theo một thay đổi có kiểm soát và chạy test phù hợp.
7. Tránh lấy dependency từ thư mục cá nhân hoặc vị trí không được version control quản lý.

Tên file như `commons-lang3-3.14.0.jar` giúp người đọc nhận biết phiên bản, nhưng chỉ tên file không chứng minh nội dung bên trong đúng phiên bản đó. Có thể lưu checksum trong file metadata hoặc xác minh bằng công cụ quản lý artifact.

Nếu dùng `<fileset dir="lib"><include name="*.jar"/></fileset>`, hãy bảo đảm thư mục không chứa đồng thời các phiên bản cũ và mới. Pattern rộng rất tiện nhưng có thể vô tình đưa mọi phiên bản vào classpath.

## 9. Khi nào nên bổ sung Apache Ivy?

Apache Ivy là công cụ quản lý dependency có thể tích hợp trực tiếp vào Ant. Ivy bổ sung khả năng khai báo module, phân giải dependency, tải artifact từ repository, quản lý configuration và cung cấp các file được resolve để Ant dùng trong classpath.

Mô hình làm việc:

~~~text
ivy.xml + ivysettings.xml
          |
          v
      ivy:resolve
          |
          v
  Phân giải dependency graph
          |
          v
  Chọn phiên bản và tải artifact
          |
          v
      ivy:retrieve
          |
          v
  JAR vào thư mục theo configuration
          |
          v
  Ant path / javac / test / package
~~~

Ivy không thay thế Ant. Ant vẫn điều phối target và task; Ivy đảm nhận phần dependency resolution. Build có thể gọi Ivy trước compile, sau đó tạo Path từ các JAR đã retrieve.

### 9.1. Khai báo module và dependency trong `ivy.xml`

Một ví dụ tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="com.example"
          module="sample-app"
          revision="1.0.0"/>

    <configurations>
        <conf name="compile" visibility="private"/>
        <conf name="runtime" extends="compile" visibility="private"/>
        <conf name="test" extends="runtime" visibility="private"/>
    </configurations>

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"
                    conf="compile->default"/>
        <dependency org="junit"
                    name="junit"
                    rev="4.13.2"
                    conf="test->default"/>
    </dependencies>
</ivy-module>
~~~

Trong ví dụ:

- `organisation` và `module` xác định module của dự án.
- `revision` là phiên bản module hiện tại.
- `configurations` định nghĩa nhóm dependency của dự án.
- `<dependency>` khai báo module cần dùng, phiên bản và cách ánh xạ configuration.
- `compile->default` yêu cầu configuration `compile` của dự án lấy configuration `default` của dependency.
- `test->default` đưa JUnit vào configuration test.

Cấu hình thực tế có thể cần ánh xạ khác theo metadata của thư viện. Một số module công bố nhiều configuration, artifact classifier hoặc loại artifact khác nhau; cần xem metadata Ivy/POM của dependency.

### 9.2. Cấu hình repository bằng `ivysettings.xml`

Ivy cần biết repository nào được dùng để tìm artifact. Ví dụ một resolver Maven-compatible:

~~~xml
<ivysettings>
    <settings defaultResolver="central"/>
    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>
</ivysettings>
~~~

Đây là ví dụ repository công khai. Trong doanh nghiệp, thường nên dùng repository nội bộ/proxy để kiểm soát nguồn, cache, quyền truy cập và chính sách lưu artifact. Không đặt token hoặc mật khẩu repository trực tiếp trong file được commit; dùng cơ chế credential an toàn của môi trường build.

### 9.3. Gọi Ivy từ Ant

Ivy cung cấp Ant tasks thông qua antlib. Cần cài đặt Ivy và đưa JAR Ivy vào classpath Ant để task được nhận diện. Ví dụ:

~~~xml
<project name="sample-app"
         default="compile"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="lib.dir" location="build/ivy-lib"/>
    <property name="ivy.settings.file" location="ivysettings.xml"/>

    <target name="resolve">
        <ivy:settings file="${ivy.settings.file}"/>
        <ivy:resolve file="ivy.xml"/>
        <ivy:retrieve conf="compile,runtime,test"
                     pattern="${lib.dir}/[conf]/[artifact]-[revision].[ext]"/>
    </target>

    <path id="compile.classpath">
        <fileset dir="${lib.dir}/compile">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="compile" depends="resolve">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

</project>
~~~

Trong cấu hình này, `resolve` gọi Ivy để đọc dependency graph và retrieve các artifact theo configuration. Target `compile` phụ thuộc `resolve`, nên classpath được chuẩn bị trước khi `javac` chạy.

Khi tích hợp thật, cần bảo đảm Ivy task đã được nạp vào Ant, `ivysettings.xml` trỏ tới repository phù hợp và configuration mapping trong `ivy.xml` đúng với các module đang dùng. Cần kiểm tra thư mục retrieve có được tạo và có chứa JAR dự kiến trước khi biên dịch.

### 9.4. Ivy xử lý được những gì?

So với Ant lõi, Ivy bổ sung các năng lực dependency chuyên biệt:

- Đọc dependency metadata và phân giải dependency bắc cầu.
- Truy vấn resolver/repository để tìm artifact.
- Áp dụng conflict manager và version matcher theo cấu hình.
- Chia dependency theo configuration như compile, runtime, test.
- Cache artifact đã resolve để tái sử dụng.
- Retrieve dependency vào một cấu trúc thư mục mà Ant có thể đưa vào Path.
- Publish module/artifact nếu dự án cấu hình quy trình xuất bản Ivy.

Ivy vẫn cần được cấu hình đúng. Nếu dùng dynamic revision, resolver thay đổi hoặc metadata không ổn định, kết quả resolve có thể thay đổi theo thời gian. Với build phát hành, nên ưu tiên revision cố định, repository được kiểm soát và lưu lại thông tin resolve theo chính sách dự án.

## 10. Ant kết hợp với Maven hoặc Gradle trong hệ thống lớn

Không nhất thiết phải chuyển toàn bộ dự án khỏi Ant để có dependency management. Có thể để một công cụ chuyên dụng chuẩn bị dependency rồi Ant thực hiện các target build còn lại. Tuy nhiên, cần xác định rõ công cụ nào là nguồn sự thật cho dependency graph.

Một số cách tổ chức:

- Dùng Ivy với Ant khi muốn tiếp tục viết target/task bằng Ant và bổ sung dependency resolution.
- Dùng Maven hoặc Gradle để resolve dependency, sau đó gọi Ant cho các bước build legacy hoặc tác vụ tùy biến.
- Chuyển dần module sang Maven/Gradle nếu dự án cần lifecycle và ecosystem plugin chuẩn hơn.
- Giữ Ant thuần nếu dependency ít, ổn định và nhóm có quy trình quản lý JAR thủ công đáng tin cậy.

Tránh để Ant, Ivy, Maven và script shell cùng khai báo những phiên bản khác nhau cho cùng thư viện. Khi có nhiều nguồn cấu hình, cần xác định file/module nào là nguồn chính và cách đồng bộ classpath để không tạo hai đồ thị dependency khác nhau.

## 11. Chọn cách quản lý phù hợp

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Ứng dụng nhỏ, vài JAR ổn định | Ant core + thư mục `lib` | Cấu hình đơn giản, dễ quan sát |
| Không có mạng khi build, dependency được kiểm soát nội bộ | JAR vendored hoặc repository/cache nội bộ | Build không phụ thuộc truy cập Internet trực tiếp |
| Nhiều dependency bắc cầu | Ant + Ivy hoặc công cụ resolver khác | Không phải tự lập toàn bộ đồ thị |
| Nhiều phiên bản xung đột | Dùng resolver và quy tắc conflict rõ ràng | Tránh đưa nhiều phiên bản trùng class vào classpath |
| Cần scope compile/runtime/test | Ivy/Maven/Gradle hoặc tự tách path rất chặt | Phân loại dependency theo mục đích |
| Dự án mới cần convention và hệ sinh thái plugin | Cân nhắc Maven hoặc Gradle | Có dependency management và lifecycle tích hợp hơn |
| Dự án legacy có build.xml phức tạp | Giữ Ant, bổ sung Ivy nếu cần | Có thể cải thiện dependency mà không viết lại toàn bộ build |

Không có một lựa chọn duy nhất đúng cho mọi dự án. Tiêu chí quan trọng là số lượng dependency, mức độ thay đổi, yêu cầu tái lập, chính sách repository và chi phí bảo trì classpath.

## 12. Những lỗi thường gặp khi Ant quản lý JAR thủ công

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Compile báo thiếu package/class | Thiếu JAR trực tiếp hoặc dependency bắc cầu | Xác định module cung cấp class và bổ sung đúng phiên bản |
| Compile thành công nhưng runtime lỗi `NoClassDefFoundError` | Runtime classpath thiếu thư viện | Tách và kiểm tra runtime classpath, không chỉ compile classpath |
| Có hai bản cùng module trong classpath | FileSet quét cả JAR cũ và mới | Loại bản cũ, pin một phiên bản và kiểm tra thứ tự classpath |
| Local chạy nhưng CI thiếu JAR | Thư viện nằm ngoài repository hoặc chỉ có trên máy cá nhân | Đưa dependency vào nguồn được quản lý hoặc resolve trong CI |
| Build tải JAR khác nhau giữa các lần chạy | URL động hoặc artifact có thể bị thay thế | Dùng revision bất biến, checksum và repository đáng tin cậy |
| Test dùng nhầm phiên bản thư viện | Dùng chung một classpath quá rộng | Tạo classpath riêng cho compile, test và runtime |
| Nâng một thư viện làm thư viện khác lỗi | Dependency bắc cầu không tương thích | Dùng resolver, xem dependency graph và kiểm thử tích hợp |
| Xóa JAR khỏi `lib` làm nhiều target lỗi | Nhiều target phụ thuộc ngầm vào cùng thư viện | Ghi nhận dependency theo vai trò và kiểm tra tất cả classpath |

Khi debug, hãy in classpath thực tế hoặc dùng `pathconvert` để xem các phần tử trong Path. So sánh classpath compile với runtime và test. Nếu dự án dùng Ivy, xem báo cáo resolve để biết phiên bản nào được chọn và vì sao.

## 13. Quy trình chuyển từ JAR thủ công sang Ivy

Có thể bổ sung dependency resolution theo từng bước:

1. Liệt kê toàn bộ JAR hiện có trong `lib`, `lib-test` và các thư mục công cụ.
2. Ghi tên module, phiên bản, nguồn tải và checksum nếu có.
3. Xác định JAR nào thuộc compile, runtime, test hoặc tooling.
4. Tìm metadata dependency của từng module để phát hiện dependency bắc cầu.
5. Tạo `ivy.xml` với các configuration và dependency tương ứng.
6. Cấu hình resolver trong `ivysettings.xml` trỏ tới repository được phép sử dụng.
7. Thêm target `resolve` và `retrieve` vào Ant.
8. Thay path thủ công bằng FileSet trên thư mục retrieve theo configuration.
9. So sánh classpath mới với classpath cũ và chạy compile/test.
10. Khi kết quả ổn định, bỏ các JAR trùng lặp không còn cần thiết trong thư mục cũ.

Không nên xóa toàn bộ JAR thủ công ngay khi thêm Ivy. Hãy chuyển từng nhóm, xác nhận artifact và test chạy đúng rồi mới loại bỏ nguồn cũ. Nếu cả hai cơ chế cùng hoạt động trong thời gian chuyển tiếp, phải tránh đưa cùng một dependency từ cả thư mục `lib` và thư mục Ivy retrieve.

## Kết luận

Ant lõi cung cấp công cụ để mô tả classpath, chọn JAR, tải file cụ thể và đưa thư viện vào task compile/test/runtime. Nó không tự đóng vai trò dependency resolver: không quản lý tọa độ module, không tự đọc và phân giải dependency bắc cầu, không giải quyết xung đột phiên bản và không có dependency cache/repository model tích hợp như các công cụ chuyên dụng. Với dự án nhỏ, JAR thủ công có thể phù hợp nếu được pin và kiểm soát chặt. Khi dependency graph phức tạp, Apache Ivy có thể bổ sung resolve/retrieve cho Ant; Maven hoặc Gradle cũng là lựa chọn nếu dự án cần dependency management và lifecycle tích hợp hơn.
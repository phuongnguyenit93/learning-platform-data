# Giảm quét thư mục rộng và tái sử dụng tập tệp phù hợp trong Apache Ant

Apache Ant thường xử lý tài nguyên bằng cách chọn tệp từ một cây thư mục: tìm các đường dẫn khớp mẫu, loại trừ những mục không cần thiết rồi chuyển kết quả cho task như `copy`, `zip`, `jar`, `delete` hoặc `move`. Nếu chọn thư mục quá rộng, đặc biệt là toàn bộ repository chứa source, thư viện, dữ liệu test, cache và đầu ra build, Ant có thể dành nhiều thời gian chỉ để tìm tệp. Bên cạnh đó, nhiều task dùng các cấu hình gần giống nhau khiến khó kiểm soát phạm vi quét và dễ sinh trùng lặp.

Bài học này trình bày cách **thu hẹp phạm vi tìm tệp**, **tái sử dụng định nghĩa FileSet, PatternSet khi thích hợp**, và lựa chọn loại tập tài nguyên đúng nhu cầu. Trọng tâm là hiệu năng của build Ant: giảm công việc duyệt thư mục không cần thiết trong khi giữ đúng tập đầu vào của mỗi task.

## 1. Vì sao quét thư mục rộng có thể làm build chậm?

Xét một tập tệp đơn giản:

```xml
<fileset dir="." includes="**/*"/>
```

`dir="."` chỉ tới thư mục gốc tương đối với `basedir` hiện hành; `**/*` là mẫu rất rộng, bao phủ nhiều cấp thư mục. Tùy cấu trúc project, phép chọn này có thể xem xét cả thư mục `build`, `dist`, `lib`, `node_modules`, dữ liệu lưu trữ, thư mục được tạo bởi công cụ khác, và những nhánh không phục vụ task.

Cần phân biệt ba loại thời gian:

1. **Thời gian tìm và chọn tệp:** duyệt cây thư mục, kiểm tra metadata, so khớp `includes`/`excludes` và selector.
2. **Thời gian xử lý tệp:** copy, nén, đọc nội dung, tạo JAR hoặc biên dịch; ngay cả khi tập đầu vào đã tối ưu, các bước này vẫn có chi phí thật.
3. **Thời gian thực hiện lại:** những task độc lập có thể tiếp tục duyệt hoặc xử lý cùng một cây; việc dùng chung cấu hình không mặc nhiên tạo cache dùng chung.

Chi phí duyệt còn phụ thuộc số lượng tệp, độ sâu thư mục, tốc độ ổ đĩa, ổ mạng, symbolic link, antivirus và kiểu selector. Không có công thức cố định “mỗi fileset mất bao nhiêu mili giây”; nên quan sát target thực tế trước và sau khi chỉnh cấu hình.

## 2. Cách `FileSet` chọn đường dẫn

`<fileset>` là kiểu dữ liệu Ant thường dùng để chọn các tệp trong một thư mục gốc. Các thuộc tính quan trọng:

| Thành phần | Tác dụng | Gợi ý |
| --- | --- | --- |
| `dir` | Thư mục gốc để tìm tệp | Chọn gần nhất với dữ liệu cần xử lý |
| `includes` hoặc `<include>` | Mẫu tên được chấp nhận | Chỉ rõ những loại tệp và nhánh cần thiết |
| `excludes` hoặc `<exclude>` | Mẫu phải loại bỏ | Loại nhánh tạm, dữ liệu không cần phát hành |
| `defaultexcludes` | Bật/tắt các loại trừ mặc định | Giữ giá trị mặc định nếu không có lý do cụ thể |
| `followsymlinks` | Điều khiển việc đi theo liên kết tượng trưng | Cân nhắc khi link dẫn đến cây lớn |
| `id` / `refid` | Đặt tên và tham chiếu định nghĩa | Dùng khi nhiều task cần cùng tập file |

Mẫu được hiểu **tương đối với thư mục `dir`**, không phải tương đối với đường dẫn của build script nếu hai thư mục khác nhau. `*` khớp trong một thành phần đường dẫn; `**` có thể khớp nhiều cấp thư mục.

Ví dụ một project:

```text
shop/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   │       ├── config/
│   │       ├── messages/
│   │       └── draft/
│   └── test/
│       └── resources/
├── lib/
├── build/
├── dist/
└── data/
    └── archive/
```

Nếu task chỉ cần XML cấu hình ở `src/main/resources/config`, hai cách viết sau có ý nghĩa khác nhau về phạm vi duyệt:

```xml
<!-- Quá rộng: quét từ gốc repository -->
<fileset dir="." includes="**/*.xml"/>

<!-- Hẹp: chỉ cần xét cây config -->
<fileset dir="src/main/resources/config" includes="**/*.xml"/>
```

Cách thứ hai tránh cho task phải xem xét các nhánh dữ liệu không liên quan. Nguyên tắc ưu tiên là **chọn `dir` hẹp trước, rồi dùng mẫu để chọn tệp trong phạm vi đó**. Mẫu include cụ thể giúp xác định kết quả, nhưng không nên được xem là giải pháp thay thế hoàn toàn cho việc chọn đúng gốc quét.

## 3. Hạn chế quét các thư mục nguồn, thư viện và đầu ra không cần thiết

Ví dụ một task copy tài nguyên nhưng đang lấy nguồn từ cả repository:

```xml
<target name="copy-resources">
    <copy todir="build/resources">
        <fileset dir=".">
            <include name="**/*.properties"/>
            <include name="**/*.xml"/>
        </fileset>
    </copy>
</target>
```

Nếu `build/resources` chứa file `.properties` của lần chạy trước, nó cũng có thể trở thành đầu vào theo cấu hình rộng này. Ngoài mất thời gian, cách chọn đó còn dễ trộn file cũ hoặc file từ những module khác.

Thu hẹp gốc quét và loại phần không thuộc bản phát hành:

```xml
<target name="copy-resources">
    <mkdir dir="build/resources"/>
    <copy todir="build/resources">
        <fileset dir="src/main/resources">
            <include name="**/*.properties"/>
            <include name="**/*.xml"/>
            <exclude name="draft/**"/>
        </fileset>
    </copy>
</target>
```

Bây giờ thư mục `build`, `dist`, `lib` và `data` nằm ngoài vùng chọn. Task chỉ tìm trong thư mục tài nguyên chính.

Nếu chưa thể đổi `dir` vì yêu cầu nghiệp vụ cần nhiều nhánh khác nhau, có thể dùng excludes rõ ràng:

```xml
<fileset dir="." includes="**/*.properties,**/*.xml">
    <exclude name="build/**"/>
    <exclude name="dist/**"/>
    <exclude name="data/archive/**"/>
    <exclude name="vendor/**"/>
</fileset>
```

Excludes hữu ích để bỏ bớt nhánh trong một cây lớn, nhưng cấu trúc đầu vào hẹp vẫn dễ hiểu hơn việc bổ sung liên tục các ngoại lệ cho một gốc quá rộng.

### Viết mẫu theo đúng gốc

```xml
<fileset dir="src/main/resources">
    <include name="config/**/*.xml"/>
    <include name="messages/**/*.properties"/>
    <exclude name="**/*.bak"/>
    <exclude name="**/draft/**"/>
</fileset>
```

Ở ví dụ này, không cần ghi `src/main/resources/config/**/*.xml` trong `<include>` vì phần `src/main/resources` đã là `dir`. Nhầm lẫn này có thể làm tập kết quả rỗng và gây hiểu nhầm là Ant không tìm thấy tệp.

Ant còn có danh sách loại trừ mặc định cho một số file tạm hoặc metadata quản lý phiên bản. Không nên mặc định danh sách ấy bao gồm thư mục `build`, `dist` hay cache riêng của mọi project. Nếu đặt `defaultexcludes="no"`, Ant có thể chọn thêm những file vốn bị loại; chỉ dùng khi đó là yêu cầu thật sự.

Trong cây có symbolic link trỏ đến vị trí lớn, có thể cân nhắc:

```xml
<fileset dir="src/main/resources"
         includes="**/*"
         followsymlinks="false"/>
```

Lựa chọn này thay đổi tập file được chọn nếu dữ liệu cần thiết nằm sau symlink; vì vậy phải dựa trên cấu trúc nguồn chứ không tắt theo thói quen.

## 4. Tái sử dụng `FileSet` với `id` và `refid`

Khi nhiều task cần **cùng thư mục gốc và cùng quy tắc lựa chọn**, tạo FileSet dùng chung để chỉ định một lần:

```xml
<project name="shop-resources" default="assemble" basedir=".">
    <property name="resources.dir" location="src/main/resources"/>
    <property name="stage.dir" location="build/staging"/>
    <property name="dist.dir" location="dist"/>

    <fileset id="release.resources" dir="${resources.dir}">
        <include name="**/*.properties"/>
        <include name="**/*.xml"/>
        <include name="**/*.json"/>
        <exclude name="**/draft/**"/>
        <exclude name="**/*.bak"/>
    </fileset>

    <target name="prepare">
        <mkdir dir="${stage.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="stage-resources" depends="prepare">
        <copy todir="${stage.dir}">
            <fileset refid="release.resources"/>
        </copy>
    </target>

    <target name="archive-resources" depends="prepare">
        <zip destfile="${dist.dir}/resources.zip">
            <fileset refid="release.resources"/>
        </zip>
    </target>

    <target name="assemble" depends="stage-resources,archive-resources"/>
</project>
```

Chạy:

```bash
ant -f build.xml assemble
```

Hai task sử dụng cùng tập tài nguyên phát hành. Nếu thay đổi loại file được phép đóng gói, chỉnh tại `release.resources` để cả hai task có cùng định nghĩa. Điều này giảm cấu hình lặp, tránh khác biệt giữa các bước và giúp nhận ra tập đầu vào có được chọn quá rộng hay không.

**Giới hạn cần hiểu rõ:** `refid` tái sử dụng **định nghĩa chọn file**, không bảo đảm Ant quét cây thư mục đúng một lần rồi dùng cache kết quả cho mọi task. Tùy task và thời điểm truy cập, hệ thống có thể thực hiện lại việc lấy tập file. Tối ưu hiệu năng vẫn cần giảm phạm vi `dir` và bỏ những task xử lý dư thừa.

Một tham chiếu FileSet nên dùng riêng `refid`:

```xml
<fileset refid="release.resources"/>
```

Không gắn thêm `dir`, `includes` hoặc các `<exclude>` cho chính phần tử tham chiếu. Nếu muốn một biến thể khác, khai báo FileSet riêng hoặc chia sẻ quy tắc chọn file qua PatternSet.

## 5. Tái sử dụng `PatternSet` khi các thư mục khác nhau

Một repository nhiều module có thể dùng cùng quy tắc chọn file nhưng thư mục nguồn khác nhau:

```text
shop/
├── core/src/main/java/
└── api/src/main/java/
```

Không cần tạo một FileSet gốc `."` để tìm khắp repository. Hãy định nghĩa mẫu chung rồi ghép với mỗi thư mục cụ thể:

```xml
<project name="multi-module" default="snapshot">
    <patternset id="production.java">
        <include name="**/*.java"/>
        <exclude name="**/generated/**"/>
        <exclude name="**/experimental/**"/>
    </patternset>

    <fileset id="core.java" dir="core/src/main/java">
        <patternset refid="production.java"/>
    </fileset>

    <fileset id="api.java" dir="api/src/main/java">
        <patternset refid="production.java"/>
    </fileset>

    <target name="snapshot">
        <copy todir="build/snapshot/core">
            <fileset refid="core.java"/>
        </copy>
        <copy todir="build/snapshot/api">
            <fileset refid="api.java"/>
        </copy>
    </target>
</project>
```

`PatternSet` diễn đạt **quy tắc tên**, còn `FileSet` diễn đạt **quy tắc tên áp dụng vào một gốc thư mục**. Tách hai khái niệm này giúp mỗi module quét vùng nguồn của chính nó nhưng vẫn tuân theo quy tắc chung.

| Nhu cầu | Cấu trúc nên chọn | Vì sao |
| --- | --- | --- |
| Nhiều task dùng cùng tệp trong cùng gốc | `FileSet id/refid` | Chia sẻ toàn bộ định nghĩa |
| Nhiều module dùng cùng mẫu trong gốc khác nhau | `PatternSet id/refid` + FileSet riêng | Không ép quét một thư mục gốc quá rộng |
| Chỉ cần vài tệp có tên cố định | `FileList` hoặc đường dẫn cụ thể | Không cần quét theo mẫu |
| Cần classpath chứa thư mục, JAR | `Path` với `pathelement`/FileSet JAR | Dùng đúng kiểu dữ liệu của task |

## 6. Khi nào nên dùng `FileList` hoặc đường dẫn tường minh?

Không phải lúc nào `FileSet` cũng là lựa chọn tối ưu. Nếu cần đúng một vài file cấu hình đã biết tên, mô tả trực tiếp thường đơn giản hơn:

```xml
<project name="fixed-config" default="copy-config">
    <filelist id="startup.config" dir="config"
              files="app.properties,logging.properties,features.properties"/>

    <target name="copy-config">
        <copy todir="build/config">
            <filelist refid="startup.config"/>
        </copy>
    </target>
</project>
```

`FileList` liệt kê những tên file cố định và không dựa vào glob để phát hiện file đang có trong cây. Vì tên file đã được khai báo, cần chú ý nếu một mục không tồn tại: task sử dụng tập tài nguyên phải xử lý tình huống đó theo cơ chế của nó. Nếu cần tự phát hiện file tùy theo trạng thái thư mục, `FileSet` mới là lựa chọn phù hợp.

Với một file, có thể dùng trực tiếp:

```xml
<copy file="config/app.properties"
      tofile="build/config/app.properties"/>
```

Không cần viết `<fileset dir="." includes="**/app.properties"/>` để tìm một đường dẫn mà cấu hình đã biết chắc.

## 7. Chọn đúng loại tập tệp theo task

Các task Ant không có cùng giao diện nhận đầu vào. Nhiều task như `copy` và `zip` nhận các tập tài nguyên lồng bên trong; task `javac` thường dùng `srcdir` cùng các mẫu include/exclude:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includes="**/*.java"
           excludes="**/examples/**"
           includeantruntime="false"/>
</target>
```

Cấu hình nguồn Java cụ thể giúp tránh để trình biên dịch xem những nhánh không thuộc source chính. Không nên mặc định có thể đặt một `<fileset>` ở mọi vị trí của mọi task; cần dùng đúng cú pháp task hỗ trợ.

Nếu cần nhiều JAR làm classpath, có thể định nghĩa `Path`:

```xml
<path id="compile.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib" includes="*.jar"/>
</path>

<target name="compile-with-dependencies">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

`includes="*.jar"` chỉ chọn JAR trực tiếp trong `lib`; nếu có thư mục con cần chọn, dùng mẫu phù hợp như `**/*.jar`. Với JAR luôn có đường dẫn cố định, `<pathelement location="lib/library.jar"/>` có thể rõ ràng hơn quét cả kho thư viện.

## 8. Tránh selector đắt và task quét trùng

Ant hỗ trợ selector chọn tài nguyên theo nhiều điều kiện như kích thước, thời gian sửa đổi hoặc nội dung. Một số selector chỉ cần metadata, một số phải mở tệp và kiểm tra nội dung. Với cây lớn, chi phí kiểm tra nhiều tệp có thể cao hơn việc so tên.

Ví dụ, nếu mục tiêu là chọn XML trong `config`, nên ưu tiên:

```xml
<fileset dir="src/main/resources/config"
         includes="**/*.xml"/>
```

Không nên chọn toàn bộ project rồi thêm nhiều bước kiểm tra nội dung chỉ để lọc xuống đúng thư mục. Chỉ thêm selector khi nó phản ánh yêu cầu của quy trình.

Các target khác nhau cũng có thể làm công việc lặp:

```text
src/main/resources
       |
       +--> copy-resources   --> build/resources
       |
       +--> archive-assets   --> dist/resources.zip
       |
       +--> another-copy     --> build/resources
```

Hai task đầu tạo hai dạng đầu ra khác nhau; việc cả hai đọc cùng nguồn có thể hợp lý. Task cuối copy lại đến đúng đích cũ có khả năng là công việc dư thừa. Hãy kiểm tra quan hệ `depends`, những lời gọi `antcall` hoặc việc CI gọi nhiều target liên tiếp để không lặp lại cùng bước.

Task `copy` có thể bỏ qua file đích đã đủ mới trong những cấu hình thông thường. Ví dụ:

```xml
<copy todir="build/resources" overwrite="false">
    <fileset dir="src/main/resources"
             includes="**/*.properties,**/*.xml"/>
</copy>
```

Tuy nhiên, logic bỏ qua file chưa cần copy **khác với** việc không quét để biết file nào thuộc tập nguồn. Một target “nhanh” ở lần chạy thứ hai có thể nhanh vì file đích đã mới, không nhất thiết vì các mẫu chọn file đã tối ưu.

Giữ tệp sinh ra khỏi cây nguồn cũng rất quan trọng. Nếu `build` nằm dưới thư mục nguồn đang được quét, số file ứng viên có thể tăng theo các lần build; đồng thời có nguy cơ lấy lại file đầu ra làm đầu vào ở lần sau.

## 9. Tập tệp tái sử dụng cần đúng ngữ nghĩa

Không nên tạo một FileSet thật rộng chỉ để mọi target đều tham chiếu được. Tài nguyên phục vụ test, tài nguyên phát hành và thư viện chạy ứng dụng có vai trò khác nhau:

```xml
<fileset id="release.assets" dir="src/main/resources">
    <include name="public/**"/>
    <include name="config/**"/>
    <exclude name="**/*.bak"/>
</fileset>

<fileset id="test.fixtures" dir="src/test/resources">
    <include name="fixtures/**"/>
    <include name="samples/**"/>
</fileset>
```

Task đóng gói dùng `release.assets`; task test dùng `test.fixtures`. Như vậy, mỗi task chỉ duyệt và xử lý tập dữ liệu phù hợp. Đặt `id` theo vai trò giúp nhận ra tham chiếu sai, chẳng hạn copy `test.fixtures` vào bản phát hành.

Nếu quy tắc giống một phần, có thể chia sẻ một `PatternSet` và bổ sung các include/exclude cho từng `FileSet`. Tái sử dụng có lợi khi cấu hình thực sự cùng ý nghĩa, không phải khi cố rút ngắn XML bằng mọi giá.

## 10. Ví dụ tổng hợp: tổ chức nguồn hẹp, mẫu dùng chung và tập dùng chung

Giả sử repository có cấu trúc:

```text
project/
├── build.xml
├── src/main/resources/
├── src/test/resources/
├── lib/
├── build/
└── dist/
```

Một bản cấu hình cho công việc stage và đóng gói tài nguyên:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="efficient-ant-build" default="dist" basedir=".">
    <property name="main.resources" location="src/main/resources"/>
    <property name="test.resources" location="src/test/resources"/>
    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>

    <!-- Mẫu chung, có thể áp dụng cho các thư mục khác nhau. -->
    <patternset id="text.resources">
        <include name="**/*.properties"/>
        <include name="**/*.xml"/>
        <include name="**/*.json"/>
        <exclude name="**/*.bak"/>
    </patternset>

    <!-- Tập tài nguyên phát hành được nhiều task dùng chung. -->
    <fileset id="main.text.resources" dir="${main.resources}">
        <patternset refid="text.resources"/>
        <exclude name="draft/**"/>
    </fileset>

    <!-- Tập test có gốc khác, chỉ dùng khi cần. -->
    <fileset id="test.text.resources" dir="${test.resources}">
        <patternset refid="text.resources"/>
    </fileset>

    <target name="prepare">
        <mkdir dir="${build.dir}/resources"/>
        <mkdir dir="${build.dir}/test-resources"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="stage-main" depends="prepare">
        <copy todir="${build.dir}/resources">
            <fileset refid="main.text.resources"/>
        </copy>
    </target>

    <target name="stage-test" depends="prepare">
        <copy todir="${build.dir}/test-resources">
            <fileset refid="test.text.resources"/>
        </copy>
    </target>

    <target name="archive-main" depends="prepare">
        <zip destfile="${dist.dir}/resources.zip">
            <fileset refid="main.text.resources"/>
        </zip>
    </target>

    <target name="dist" depends="stage-main,archive-main"/>
</project>
```

Gọi `ant -f build.xml dist` sẽ thực hiện công việc cho tài nguyên chính và tạo archive, còn `stage-test` có gốc riêng và không thuộc phụ thuộc của `dist`. Cả hai bước phát hành dùng chung một định nghĩa `main.text.resources`, không cần sao chép nhiều lần các mẫu chọn tệp. Tùy cấu trúc thật của dự án, có thể thay thư mục và pattern mà vẫn giữ nguyên nguyên tắc lựa chọn.

## 11. Đo lường hiệu năng có ý nghĩa

Cần đo đúng target, trong điều kiện tương đương, trước khi kết luận một cách viết `fileset` cải thiện hiệu năng.

Trên PowerShell:

```powershell
Measure-Command { ant -f build.xml stage-main }
```

Trên hệ thống có lệnh `time`:

```bash
time ant -f build.xml stage-main
```

Nếu cần điều tra những công việc được thực thi, chạy:

```bash
ant -f build.xml -verbose stage-main
```

`-verbose` cho nhiều thông tin hơn nhưng bản thân nó tăng lượng log; không nên coi một lần chạy verbose là thước đo duy nhất. Phương pháp đánh giá phù hợp là:

1. Ghi nhận target, kích thước dữ liệu, trạng thái thư mục đích và thời gian trước khi đổi cấu hình.
2. Thu hẹp `dir`, chọn mẫu phù hợp, chia riêng tài nguyên theo nhiệm vụ và loại bước xử lý lặp không cần thiết.
3. Chạy lại cùng target với dữ liệu và điều kiện tương đương; phân biệt build sạch với build tăng dần (đích đã có).
4. Đối chiếu thời gian và kiểm tra tập đầu ra thực tế; nếu không nhanh hơn, xem xét chi phí nén, copy, biên dịch, ổ mạng hoặc selector.

Một phép đo đơn lẻ có thể chịu ảnh hưởng lớn từ cache của hệ điều hành, antivirus hoặc lần đầu tạo dữ liệu. Dùng vài lượt đo trong cùng trạng thái giúp so sánh có cơ sở hơn.

## 12. Các lỗi cấu hình thường gặp

### Exclude nhiều nhưng vẫn quét rộng

```xml
<fileset dir="." includes="**/*"
         excludes="build/**,dist/**,data/**"/>
```

Nếu chỉ cần `src/main/resources/config`, hãy chuyển `dir` sang đó. Loại trừ một vài nhánh từ gốc không có nghĩa chỉ còn duyệt đúng cây cần xử lý.

### Dùng `refid` nhưng build không nhanh hơn

```xml
<fileset id="all.resources" dir="." includes="**/*"/>
```

`refid` giúp chia sẻ định nghĩa, không bảo đảm kết quả scan được cache giữa các task. Cần tạo FileSet hẹp và xét xem có task nào xử lý trùng hoặc selector nào quá đắt.

### Không tìm thấy tệp do ghi sai pattern

```xml
<fileset dir="src/main/resources"
         includes="src/main/resources/config/*.xml"/>
```

Mẫu được hiểu tương đối với `dir`, vì vậy tiền tố bị lặp. Nên dùng `includes="config/*.xml"` khi chỉ cần XML trực tiếp dưới `config`, hoặc `config/**/*.xml` khi cần cả các thư mục con.

### Bản phát hành thiếu hoặc thừa file

Khi thu hẹp `dir` hoặc thêm `excludes`, tập tài nguyên thay đổi. Nếu file nằm ngoài vùng chọn, nó sẽ không còn vào archive. Ngược lại, dùng một tập quá rộng có thể đưa fixture test hoặc file tạm vào gói phát hành. Cần đối chiếu nội dung đích với nhu cầu từng target, không chỉ nhìn vào việc `BUILD SUCCESSFUL`.

### File nguồn và file sinh ra lẫn nhau

Nếu `copy` hoặc `zip` có nguồn là `dir="."` trong khi thư mục `build`/`dist` cũng nằm dưới cùng gốc, có nguy cơ lựa chọn artifact cũ. Tách thư mục nguồn và kết quả, hoặc đặt nguồn ở một subtree cụ thể để không kéo các file sinh ra trở lại vòng build.

## 13. Kết luận thực hành

Với Ant, cách giảm chi phí quét tệp hiệu quả nhất thường bắt đầu bằng việc chọn **đúng thư mục gốc và đúng tập đầu vào**. Dùng `includes`/`excludes` rõ ràng, tránh quét cả repository khi chỉ cần một module, giữ đầu ra build ngoài vùng nguồn được xét và hạn chế công việc lặp. Khi cùng một tập file được nhiều task sử dụng, `FileSet id/refid` giúp cấu hình nhất quán; nếu nhiều thư mục dùng chung quy tắc, `PatternSet` phù hợp hơn; nếu chỉ có tên tệp cố định, dùng `FileList` hoặc đường dẫn tường minh.

Hãy nhớ rằng **tái sử dụng mô tả tập tệp không đồng nghĩa với chỉ quét một lần**. Thu hẹp cây thư mục, giảm những bước xử lý trùng và đo đúng target mới cho thấy lợi ích thực tế của thay đổi đối với hiệu năng build.

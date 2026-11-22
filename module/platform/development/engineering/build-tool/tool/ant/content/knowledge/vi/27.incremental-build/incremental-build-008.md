# Thiết kế tác vụ có thể chạy lại mà không làm sai đầu ra

Trong một dự án dùng Apache Ant, cùng một target có thể được gọi nhiều lần: lập trình viên chạy build ở máy cá nhân, CI chạy lại sau khi có commit mới, hoặc một pipeline được khởi động lại sau khi gặp lỗi. Một build file tốt cần xử lý được những lần chạy lặp này mà không tạo file trùng, nối dữ liệu ngoài ý muốn, giữ lại artifact cũ hoặc làm hỏng kết quả đã tạo.

Có hai mục tiêu liên quan nhưng khác nhau:

- **Idempotent (có tính lặp an toàn):** chạy cùng một thao tác nhiều lần với cùng trạng thái đầu vào không làm trạng thái cuối bị thay đổi ngoài ý muốn. Lần chạy sau không tạo thêm bản sao hoặc cộng dồn tác dụng phụ.
- **Incremental (tăng dần):** chỉ thực hiện lại phần công việc bị ảnh hưởng bởi thay đổi đầu vào, bỏ qua phần đã có kết quả còn hợp lệ.

Một tác vụ có thể idempotent nhưng không incremental: nó luôn ghi lại cùng một file nên kết quả giống nhau nhưng vẫn tốn thời gian. Ngược lại, một tác vụ có thể incremental nhưng không idempotent: nó chỉ chạy khi có thay đổi, nhưng nếu bị gọi lại trong cùng điều kiện thì có thể nối thêm dòng hoặc tạo bản ghi trùng. Build đáng tin cậy nên hướng tới cả hai mục tiêu.

## 1. Phân biệt idempotence, incremental và reproducibility

Ba khái niệm thường đi cùng nhau nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Idempotence | Chạy lại có làm trạng thái cuối sai lệch hoặc tích lũy tác dụng phụ không? | Ghi đè một file cấu hình bằng nội dung mong muốn thay vì nối thêm mỗi lần |
| Incremental build | Khi đầu vào không đổi, có thể bỏ qua công việc đã hoàn tất không? | Chỉ biên dịch source Java mới hơn file `.class` tương ứng |
| Reproducible build | Cùng source, dependency và cấu hình có tạo ra artifact giống nhau không? | Hai lần build tạo JAR có cùng nội dung và metadata được kiểm soát |

Ví dụ, task `<echo file="build/version.txt">2.4.0</echo>` có thể ghi cùng một nội dung ở mọi lần chạy. Về nội dung file, thao tác có tính lặp an toàn; tuy nhiên file có thể bị ghi lại và timestamp thay đổi mỗi lần, nên task chưa chắc incremental. Ngược lại, một task chỉ chạy khi source mới hơn output nhưng dùng `append="true"` có thể tạo dữ liệu trùng nếu task bị chạy lại vì output bị xóa hoặc trạng thái theo dõi bị mất.

Mục tiêu thiết kế là xác định trạng thái đích rõ ràng, tạo output theo cách có thể chạy lại, rồi dùng thông tin phụ thuộc để bỏ qua công việc không cần thiết.

## 2. Target Ant không tự động là incremental

Ant xây dựng dependency graph từ các target và thuộc tính `depends`. Trong một lần chạy Ant, target được thực hiện theo thứ tự phụ thuộc và một target thông thường chỉ được thực hiện một lần trong project đó. Tuy nhiên, khi chạy Ant lần tiếp theo, Ant không tự so sánh output của target với input để quyết định target có cần chạy hay không.

Ví dụ:

```xml
<target name="compile">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="jar" depends="compile">
    <jar destfile="build/app.jar" basedir="build/classes"/>
</target>
```

Khi gọi `ant jar` nhiều lần, target `compile` và `jar` vẫn được xét và thực thi theo dependency graph ở mỗi lần chạy. Task `<javac>` có cơ chế riêng để chỉ biên dịch source cần thiết, nhưng task `<jar>` mặc định có thể tạo lại archive. `depends` bảo đảm thứ tự; nó không phải cơ chế kiểm tra output còn mới hay không.

Có thể thêm điều kiện `if` hoặc `unless` cho target. Các điều kiện target kiểu này kiểm tra **sự tồn tại của property**, không đánh giá chuỗi `true` hoặc `false` theo nghĩa boolean. Ví dụ, nếu property `jar.current` được đặt, target có `unless="jar.current"` sẽ bị bỏ qua.

## 3. Tận dụng hành vi incremental có sẵn của task

Trước khi tự viết logic kiểm tra timestamp, hãy dùng cơ chế sẵn có của task Ant:

| Task | Hành vi hữu ích khi chạy lặp |
|---|---|
| `<mkdir>` | Nếu thư mục đã tồn tại thì không cần tạo lại |
| `<delete>` | Xóa file/thư mục được chỉ định; gọi lại khi mục tiêu đã biến mất không tạo thêm tác dụng phụ |
| `<javac>` | So sánh source và class output để biên dịch các file cần cập nhật |
| `<copy>` | Mặc định chỉ sao chép khi file đích chưa có hoặc file nguồn mới hơn; `overwrite="true"` buộc ghi đè |
| `<sync>` | Đồng bộ nội dung thư mục đích với nguồn và có thể xóa file đích không còn trong nguồn |
| `<uptodate>` | Đặt property khi output được xem là mới hơn hoặc tương ứng với input theo quy tắc kiểm tra |

Ví dụ, `mkdir` có thể xuất hiện trong mọi lần chạy mà không cần kiểm tra trước:

```xml
<target name="prepare">
    <mkdir dir="build/classes"/>
    <mkdir dir="build/reports"/>
</target>
```

Không cần dùng `<available>` để kiểm tra thư mục rồi mới gọi `<mkdir>`. Task đã xử lý trường hợp thư mục tồn tại.

Với `<copy>`, mặc định Ant không ghi đè file đích mới hơn file nguồn. Không bật `overwrite="true"` nếu mục tiêu là tránh copy lại dữ liệu không đổi:

```xml
<copy todir="build/config">
    <fileset dir="config" includes="**/*.properties"/>
</copy>
```

Khi bật `overwrite="true"`, Ant copy bất kể timestamp đích. Điều này có thể cần thiết khi muốn bảo đảm nội dung luôn được đồng bộ, nhưng làm mất lợi ích incremental và có thể thay đổi timestamp output ở mọi lần chạy.

## 4. Dùng `<uptodate>` để bỏ qua công việc đã hoàn tất

Task `<uptodate>` so sánh thời gian sửa đổi của nguồn và đích. Nếu đích đã mới hơn nguồn theo cách so sánh được cấu hình, task đặt một property. Task không tự chạy lệnh tạo output và cũng không tự bỏ qua target; nó chỉ cung cấp thông tin để build file quyết định.

Với một nguồn và một output:

```xml
<target name="check-report">
    <uptodate property="report.current"
              srcfile="data/input.csv"
              targetfile="build/report.html"/>
</target>

<target name="generate-report"
        depends="check-report"
        unless="report.current">
    <mkdir dir="build"/>
    <exec executable="report-generator" failonerror="true">
        <arg value="--input"/>
        <arg value="data/input.csv"/>
        <arg value="--output"/>
        <arg value="build/report.html"/>
    </exec>
</target>
```

Nếu `build/report.html` đã tồn tại và mới hơn `data/input.csv`, `<uptodate>` đặt property `report.current`; target `generate-report` bị bỏ qua. Nếu output chưa tồn tại hoặc source mới hơn output, property không được đặt và lệnh tạo báo cáo chạy.

Với nhiều file nguồn tạo ra một output tổng hợp, có thể dùng nested `<srcfiles>`:

```xml
<target name="check-index">
    <uptodate property="index.current"
              targetfile="build/site/index.html">
        <srcfiles dir="src/pages" includes="**/*.html"/>
        <srcfiles dir="src/templates" includes="**/*.xsl"/>
    </uptodate>
</target>

<target name="generate-index"
        depends="check-index"
        unless="index.current">
    <exec executable="site-indexer" failonerror="true">
        <arg value="--pages"/>
        <arg value="src/pages"/>
        <arg value="--templates"/>
        <arg value="src/templates"/>
        <arg value="--output"/>
        <arg value="build/site/index.html"/>
    </exec>
</target>
```

Property `index.current` chỉ được đặt khi output mới hơn tất cả file nguồn được chọn. Nếu bất kỳ nguồn nào mới hơn output, target tạo lại index.

### Kiểm tra nhiều nguồn với mapper

Khi mỗi file nguồn có một file đích tương ứng, có thể dùng mapper để ánh xạ tên nguồn sang tên output. Ví dụ, một bước biến đổi XML thành HTML có thể so sánh `src/a.xml` với `build/html/a.html`, `src/b.xml` với `build/html/b.html`. Mapper giúp kiểm tra từng cặp thay vì so tất cả nguồn với một output chung.

```xml
<uptodate property="pages.current">
    <srcfiles dir="src/pages" includes="**/*.xml"/>
    <mapper type="glob" from="*.xml" to="build/html/*.html"/>
</uptodate>
```

Khi dùng mapper, hãy chọn pattern phù hợp với cấu trúc thư mục thực tế và bảo đảm mỗi source có output tương ứng. Nếu không có mapper, không nên giả định Ant tự suy ra tên output theo ý muốn của dự án.

## 5. Dùng `<dependset>` khi một thay đổi làm mất hiệu lực cả nhóm output

Với một số quy trình, các file output phụ thuộc lẫn nhau hoặc một thay đổi ở bất kỳ nguồn nào cũng yêu cầu tạo lại toàn bộ nhóm kết quả. Task `<dependset>` có thể kiểm tra source files và target files; nếu một nguồn mới hơn một đích, task xóa toàn bộ target files để các bước sau tạo lại chúng.

```xml
<target name="invalidate-generated-classes">
    <dependset>
        <srcfileset dir="src/main/java" includes="**/*.java"/>
        <targetfileset dir="build/classes" includes="**/*.class"/>
    </dependset>
</target>

<target name="compile-all" depends="invalidate-generated-classes">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
```

`dependset` hữu ích khi không thể ánh xạ từng nguồn với một output cụ thể và muốn vô hiệu hóa cả nhóm output khi phát hiện dependency cũ. Vì task xóa các target file, hãy chọn `targetfileset` hẹp và chính xác; không trỏ nó vào thư mục chứa file không được phép xóa.

Timestamp comparison không phát hiện mọi thay đổi cấu trúc. Ví dụ, nếu một source bị xóa khỏi thư mục, file đó không còn xuất hiện trong fileset để so sánh. Một output cũ được tạo từ source đã xóa có thể vẫn tồn tại. Khi việc thêm/xóa/đổi tên file làm thay đổi kết quả, cần một cách theo dõi danh sách input hoặc đồng bộ thư mục output, không chỉ so sánh timestamp của các file còn lại.

## 6. Quản lý output thư mục và file bị xóa khỏi nguồn

Một lỗi thường gặp trong build tăng dần là output cũ còn sót lại sau khi source tương ứng bị xóa hoặc đổi tên. `<copy>` có thể cập nhật file mới nhưng không tự xóa file đích không còn trong source.

Nếu một thư mục đích chỉ dành riêng cho bản sao tài nguyên, dùng `<sync>` để phản chiếu source:

```xml
<target name="sync-resources">
    <sync todir="build/resources">
        <fileset dir="src/main/resources"/>
    </sync>
</target>
```

`<sync>` copy file mới hoặc đã thay đổi và xóa file ở `build/resources` nếu file đó không còn trong `src/main/resources`. Chỉ dùng một thư mục đích chuyên biệt cho loại tài nguyên này. Không đồng bộ resource vào thư mục đang chứa class files nếu fileset nguồn không bao gồm class files, vì các class có thể bị xóa nhầm.

Với output phức tạp được sinh từ nhiều nguồn, một cách an toàn là dựng vào staging directory riêng rồi thay thế thư mục output cũ sau khi tạo thành công:

```xml
<target name="generate-site">
    <delete dir="build/site-staging"/>
    <mkdir dir="build/site-staging"/>

    <exec executable="site-generator" failonerror="true">
        <arg value="--input"/>
        <arg value="src/site"/>
        <arg value="--output"/>
        <arg value="build/site-staging"/>
    </exec>

    <delete dir="build/site-old"/>
    <move file="build/site" tofile="build/site-old" failonerror="false"/>
    <move file="build/site-staging" tofile="build/site"/>
    <delete dir="build/site-old"/>
</target>
```

Đây là mẫu minh họa quy trình staging và thay thế; thao tác rename thư mục có thể khác nhau giữa hệ thống file, đặc biệt khi thư mục đích đang được tiến trình khác sử dụng. Với release quan trọng, hãy chọn chiến lược triển khai phù hợp hệ điều hành và bảo đảm có bước phục hồi nếu bước move cuối thất bại.

## 7. Ví dụ build Java có thể chạy lại

Ví dụ dưới đây minh họa biên dịch incremental, đồng bộ resource vào một thư mục riêng, kiểm tra freshness rồi mới đóng gói JAR. Cấu trúc output được tách để việc xóa resource cũ không ảnh hưởng class đã biên dịch.

```xml
<project name="incremental-java-build" default="jar" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="resources.src.dir" location="src/main/resources"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="resources.dir" location="${build.dir}/resources"/>
    <property name="jar.file" location="${build.dir}/libs/application.jar"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${resources.dir}"/>
        <mkdir dir="${build.dir}/libs"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               debug="true"/>
    </target>

    <target name="sync-resources" depends="prepare">
        <sync todir="${resources.dir}">
            <fileset dir="${resources.src.dir}"/>
        </sync>
    </target>

    <target name="check-jar" depends="compile,sync-resources">
        <uptodate property="jar.current" targetfile="${jar.file}">
            <srcfiles dir="${classes.dir}"/>
            <srcfiles dir="${resources.dir}"/>
        </uptodate>
    </target>

    <target name="jar" depends="check-jar" unless="jar.current">
        <jar destfile="${jar.file}">
            <fileset dir="${classes.dir}"/>
            <fileset dir="${resources.dir}"/>
        </jar>
    </target>
</project>
```

Ở mỗi lần chạy:

1. `prepare` bảo đảm các thư mục cần thiết tồn tại.
2. `compile` để `<javac>` tự biên dịch những source cần cập nhật.
3. `sync-resources` cập nhật resource và loại bỏ file đích đã bị xóa khỏi nguồn.
4. `check-jar` đặt `jar.current` nếu JAR mới hơn tất cả file class và resource hiện có.
5. Target `jar` chỉ chạy khi property `jar.current` chưa được đặt.

Khi source Java thay đổi, `<javac>` cập nhật class tương ứng và timestamp class mới hơn JAR; JAR được tạo lại. Khi resource thay đổi hoặc bị xóa, `sync` cập nhật thư mục resource và freshness check khiến JAR được tạo lại. Nếu không có thay đổi, JAR hiện có được giữ nguyên và task đóng gói bị bỏ qua.

Trong dự án thực tế, cần tính thêm các đầu vào khác có ảnh hưởng đến JAR, chẳng hạn manifest, file cấu hình đóng gói, dependency được nhúng hoặc tùy chọn compiler. Nếu một đầu vào không được đưa vào freshness check, thay đổi của nó có thể không làm JAR được tạo lại.

## 8. Timestamp và giới hạn của kiểm tra up-to-date

Các cơ chế incremental phổ biến của Ant dựa vào thời gian sửa đổi file. Cách này nhanh và phù hợp với nhiều build, nhưng có giới hạn:

- Nếu nội dung file thay đổi nhưng timestamp được giữ nguyên hoặc bị đặt lùi, task có thể không nhận ra thay đổi.
- Đồng hồ giữa các máy hoặc hệ thống file có độ phân giải timestamp khác nhau có thể làm so sánh không chính xác.
- Một số thao tác copy, checkout hoặc giải nén giữ nguyên timestamp cũ.
- Việc thêm hoặc xóa file có thể không được phản ánh bởi phép so sánh chỉ xét các file hiện có.
- Một output có timestamp mới hơn source không chứng minh nó được tạo từ đúng phiên bản dependency hoặc cấu hình hiện tại.

Khi độ chính xác quan trọng hơn tốc độ, có thể dùng checksum hoặc manifest đầu vào để theo dõi nội dung. Ví dụ, tạo một file mô tả các input và hash của chúng; chỉ bỏ qua bước build khi manifest hiện tại trùng với manifest được lưu cùng output. Cần cập nhật manifest sau khi output được tạo thành công, không cập nhật trước, nếu không một lần build lỗi có thể để lại dấu hiệu sai rằng output đã mới.

Một lựa chọn đơn giản cho release là chạy clean build trong workspace mới hoặc xóa thư mục output trước khi tạo artifact. Clean build chậm hơn incremental build nhưng giúp phát hiện các dependency bị khai báo thiếu và file cũ còn sót. CI thường có thể dùng incremental build cho vòng phản hồi nhanh và clean build ở các giai đoạn xác minh hoặc phát hành.

## 9. Thiết kế thao tác file để chạy lặp an toàn

Những thao tác ghi file nên có một trạng thái đích xác định:

### Ghi đè thay vì nối thêm khi tạo file kết quả

Nếu file là kết quả được tạo lại từ đầu, hãy ghi nội dung hoàn chỉnh thay vì append:

```xml
<echo file="build/version.txt" encoding="UTF-8">${app.version}</echo>
```

Không dùng `append="true"` cho file được tạo lại toàn bộ ở mỗi lần build, trừ khi mục tiêu thật sự là log tích lũy. Với log, có thể dùng tên file theo build number hoặc xóa log cũ trước khi bắt đầu để tránh lẫn nhiều lần chạy.

### Không dùng timestamp marker như một tác dụng phụ vô điều kiện

Task `<touch>` cập nhật timestamp file. Nếu target marker được chạm ở mọi lần chạy, các bước phụ thuộc timestamp có thể luôn bị xem là cần chạy lại. Chỉ cập nhật marker sau khi tác vụ tạo output hoàn tất thành công và chỉ khi trạng thái đầu vào thực sự thay đổi.

### Tạo file tạm rồi thay thế output cuối

Với chương trình ngoài có thể ghi file dở dang trước khi lỗi, yêu cầu chương trình ghi vào file tạm. Chỉ move file tạm sang tên cuối sau khi exit code thành công:

```xml
<target name="generate-config">
    <delete file="build/app.properties.tmp"/>

    <exec executable="config-generator" failonerror="true">
        <arg value="--output"/>
        <arg value="build/app.properties.tmp"/>
    </exec>

    <move file="build/app.properties.tmp"
          tofile="build/app.properties"
          overwrite="true"/>
</target>
```

Nếu lệnh thất bại, file output cuối vẫn giữ bản trước đó; task `<move>` không được thực hiện. Việc thay thế file có tính nguyên tử hay không còn tùy hệ điều hành và filesystem, nhưng staging giúp tránh để một file kết quả chưa hoàn chỉnh mang tên chính thức.

## 10. Tác vụ ngoài và tác dụng phụ

Task `<exec>` gọi một chương trình khác. Ant không thể tự biết chương trình đó có idempotent hay không. Ví dụ, lệnh `upload --file app.zip` có thể tạo bản phát hành mới mỗi lần chạy; lệnh `append-log` có thể nhân đôi dòng; lệnh `deploy` có thể tạo tài nguyên trùng nếu API không hỗ trợ cập nhật.

Để lệnh ngoài chạy lặp an toàn:

- Ưu tiên chế độ `replace`, `upsert`, `sync` hoặc `--overwrite` nếu công cụ hỗ trợ và semantics phù hợp.
- Dùng khóa định danh ổn định cho tài nguyên, chẳng hạn version hoặc artifact ID, để lần chạy sau cập nhật đúng đối tượng.
- Truyền output path tường minh và không phụ thuộc thư mục tạm không xác định.
- Ghi nhận exit code và chỉ đánh dấu hoàn tất sau khi chương trình kết thúc thành công.
- Nếu thao tác có thể tạo tác dụng phụ không thể đảo ngược, kiểm tra trạng thái hiện tại trước khi gọi hoặc yêu cầu công cụ hỗ trợ idempotency key.
- Tách bước tạo artifact khỏi bước publish/deploy để có thể chạy lại phần tạo mà không phát hành trùng.

Ví dụ, thay vì gọi upload ở mọi lần build, có thể kiểm tra artifact đã tồn tại ở kho phát hành bằng một công cụ chuyên dụng rồi chỉ upload khi version chưa có. Nếu kho hỗ trợ upload cùng version theo semantics ghi đè an toàn, hãy dùng cơ chế đó và xác minh digest sau upload.

## 11. Tránh output cũ và phụ thuộc bị bỏ sót

Một build có thể chạy lặp mà không lỗi nhưng vẫn tạo artifact sai nếu đầu vào của freshness check chưa đầy đủ. Ví dụ JAR phụ thuộc vào:

- class files;
- resources;
- manifest;
- file cấu hình đóng gói;
- dependency JAR được nhúng;
- tùy chọn compiler hoặc biến môi trường ảnh hưởng nội dung.

Nếu `<uptodate>` chỉ kiểm tra class files, thay đổi manifest hoặc dependency sẽ không làm property up-to-date mất hiệu lực. Cần đưa mọi đầu vào ảnh hưởng đến output vào dependency model hoặc lưu một manifest cấu hình để so sánh.

Tương tự, nếu một source bị đổi tên, class cũ có thể còn trong thư mục output. `javac` biên dịch file mới nhưng không nhất thiết xóa class tương ứng với source đã bị xóa. Có thể dùng clean compile, output directory riêng được dựng lại, hoặc cơ chế đồng bộ có ánh xạ rõ ràng để loại file stale.

Không dùng một marker duy nhất nếu output thực tế gồm nhiều file và marker có thể còn tồn tại khi một phần output bị xóa. Freshness check nên xác nhận các output cần thiết đều tồn tại và mới hơn các input liên quan.

## 12. Lỗi thường gặp và cách xử lý

1. **Nghĩ rằng `depends` bỏ qua target không thay đổi.** `depends` chỉ điều phối thứ tự và quan hệ phụ thuộc. Dùng task incremental hoặc `<uptodate>` để quyết định có cần tạo lại output.
2. **Target chạy lại làm file bị nhân đôi.** Kiểm tra task có `append`, tạo tên file ngẫu nhiên hoặc gọi API tạo mới mỗi lần hay không. Dùng output path ổn định và thao tác replace/upsert phù hợp.
3. **JAR được đóng gói lại ở mọi lần build.** Thêm freshness check trước `<jar>` hoặc dùng task có cơ chế incremental phù hợp. Đảm bảo mọi đầu vào của JAR đều được kiểm tra.
4. **File cũ vẫn xuất hiện sau khi xóa source.** `<copy>` không tự xóa file đích stale. Dùng `<sync>` với thư mục đích riêng hoặc clean/rebuild output.
5. **`<uptodate>` bỏ qua thay đổi.** Kiểm tra timestamp, độ phân giải filesystem và danh sách input. Nếu cần, dùng checksum hoặc manifest nội dung.
6. **Build bỏ sót thay đổi manifest hoặc cấu hình.** Bổ sung các file cấu hình đó vào `srcfiles` hoặc cơ chế theo dõi dependency.
7. **Output bị hỏng sau lần chạy thất bại.** Tạo file vào staging hoặc tên tạm, rồi move vào vị trí cuối chỉ sau khi lệnh thành công.
8. **Marker báo up-to-date dù một output đã mất.** Kiểm tra sự tồn tại của toàn bộ output cần thiết; không chỉ kiểm tra một file marker nếu artifact có nhiều thành phần.
9. **Dùng `<touch>` làm marker mỗi lần target chạy.** Timestamp bị thay đổi liên tục khiến các bước phụ thuộc luôn bị coi là cũ. Chỉ cập nhật marker sau khi xử lý thành công và khi cần.
10. **Build trên máy cá nhân đúng nhưng CI sai.** Kiểm tra dependency ngoài, biến môi trường, timezone/clock, filesystem timestamp và sự khác biệt giữa workspace sạch với workspace tái sử dụng.

## 13. Quy trình thiết kế tác vụ có thể chạy lại

Khi thêm một bước mới vào build file, hãy xác định:

1. Đầu vào chính xác là những file, property, dependency và biến môi trường nào.
2. Output cuối gồm những file hoặc tác dụng phụ nào, và đường dẫn có ổn định hay không.
3. Khi chạy lại với cùng đầu vào, task có ghi đè, nối thêm, tạo bản sao hay thay đổi tài nguyên ngoài không.
4. Task có cơ chế incremental sẵn có hay cần `<uptodate>`, `<dependset>` hoặc checksum.
5. Việc thêm, xóa, đổi tên input có được phản ánh vào dependency model không.
6. Nếu task thất bại giữa chừng, output cũ có còn nguyên và lần chạy sau có thể phục hồi không.
7. Có cần clean build ở một giai đoạn CI để phát hiện output stale hoặc dependency bị bỏ sót không.
8. Có thể xác minh kết quả cuối bằng cách kiểm tra file, checksum hoặc trạng thái dịch vụ hay không.

Một tác vụ được thiết kế tốt cho build tăng dần có thể chạy lại an toàn, nhận biết khi nào output đã cũ và chỉ cập nhật đúng phần bị ảnh hưởng. Điều đó làm build nhanh hơn, dễ phục hồi sau lỗi và đáng tin cậy hơn trong CI.

## Tài liệu tham khảo

- [Apache Ant Manual — UpToDate Task](https://ant.apache.org/manual/Tasks/uptodate.html): kiểm tra quan hệ thời gian giữa source và target, dùng property để điều khiển target.
- [Apache Ant Manual — DependSet Task](https://ant.apache.org/manual/Tasks/dependset.html): vô hiệu hóa nhóm output khi dependency source mới hơn.
- [Apache Ant Manual — Javac Task](https://ant.apache.org/manual/Tasks/javac.html): biên dịch Java theo trạng thái source/class output.
- [Apache Ant Manual — Copy Task](https://ant.apache.org/manual/Tasks/copy.html): sao chép file, overwrite và preserve timestamp.
- [Apache Ant Manual — Sync Task](https://ant.apache.org/manual/Tasks/sync.html): đồng bộ thư mục và xóa file đích không còn trong nguồn.
- [Apache Ant Manual — Exec Task](https://ant.apache.org/manual/Tasks/exec.html): gọi tiến trình ngoài và quản lý output của lệnh.

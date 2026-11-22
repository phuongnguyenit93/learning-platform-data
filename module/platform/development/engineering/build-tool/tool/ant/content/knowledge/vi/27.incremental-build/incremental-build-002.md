# So sánh dấu thời gian và kiểm tra up-to-date

Apache Ant thường dùng dấu thời gian sửa đổi cuối cùng (last-modified time) để quyết định một đầu ra có cần được tạo lại hay không. Nếu file nguồn mới hơn file đích, đầu ra được xem là cũ; nếu file đích tồn tại và không cũ hơn các nguồn liên quan, công việc có thể được bỏ qua.

Cơ chế này là nền tảng của build tăng dần (incremental build). Thay vì biên dịch hoặc tạo lại mọi thứ trong mỗi lần chạy, Ant chỉ xử lý những đầu vào được xác định là đã thay đổi theo quy tắc timestamp của task.

Hai cơ chế cần hiểu rõ:

- **Timestamp comparison:** so sánh thời điểm sửa đổi của file nguồn và file đích.
- **Up-to-date check:** kiểm tra đầu ra đã tồn tại và còn mới so với các đầu vào được khai báo hay chưa; nếu còn mới, build có thể bỏ qua bước tạo lại.

Ant cung cấp task `<uptodate>` để thực hiện phép kiểm tra này và nhiều task như `<javac>` tự dùng timestamp để chọn file cần xử lý. Cơ chế timestamp nhanh và đơn giản, nhưng không phải phép so sánh nội dung: nó không tự phát hiện mọi thay đổi trong dependency, compiler option hoặc nội dung file nếu timestamp không phản ánh thay đổi đó.

## 1. Timestamp của file là gì?

Hệ điều hành lưu thời điểm sửa đổi cuối cùng cho mỗi file. Ant có thể đọc thời điểm này và so sánh giữa source với output.

Ví dụ:

~~~text
src/Guide.xml           modified: 10:15
build/Guide.html        modified: 10:10
~~~

Source mới hơn output, nên trang HTML có thể đã lỗi thời và cần được tạo lại.

Trường hợp khác:

~~~text
src/Guide.xml           modified: 10:15
build/Guide.html        modified: 10:20
~~~

Output không cũ hơn source, vì vậy theo phép so sánh timestamp đơn giản, nó được xem là up-to-date.

Quy tắc so sánh thường dùng là:

| Trạng thái | Kết luận |
|---|---|
| File đích không tồn tại | Out-of-date; cần tạo output |
| Source mới hơn target | Out-of-date; cần xử lý lại |
| Target mới hơn source | Up-to-date theo timestamp |
| Source và target có timestamp bằng nhau | Không có source nào mới hơn; thường được xem là up-to-date |

Điều quan trọng là timestamp chỉ là dấu hiệu gián tiếp về thay đổi. Ant không đọc và so sánh toàn bộ byte của hai file trong phép kiểm tra up-to-date thông thường.

## 2. Build tăng dần hoạt động như thế nào?

Một build tăng dần thường có các bước:

1. Xác định source và output tương ứng.
2. Kiểm tra output có tồn tại hay không.
3. So sánh timestamp của source và output.
4. Chỉ chạy compiler hoặc generator cho phần cần cập nhật.
5. Giữ lại các output vẫn còn up-to-date.

Ví dụ với Java:

~~~text
src/main/java/com/example/App.java
                 |
                 v
build/classes/com/example/App.class
~~~

Nếu `App.java` mới hơn `App.class`, Ant đưa source đó vào lượt compile. Nếu `.class` chưa tồn tại, source cũng cần được biên dịch. Nếu `.class` mới hơn hoặc bằng source, Ant có thể bỏ qua source đó.

Lợi ích chính là giảm thời gian build khi chỉ một phần nhỏ source thay đổi. Dự án càng lớn, việc tránh biên dịch lại các module hoặc file không thay đổi càng có giá trị.

Tuy nhiên, incremental build chỉ chính xác trong phạm vi các đầu vào và quan hệ mà task biết. Nếu classpath, compiler version, compiler flags hoặc file cấu hình thay đổi mà timestamp của source không đổi, một task dựa chủ yếu vào source timestamp có thể không tự nhận ra cần build lại.

## 3. Dùng `<uptodate>` với một source và một target

Task `<uptodate>` kiểm tra một file nguồn với một file đích. Nếu target tồn tại và không cũ hơn source, task đặt property được chỉ định.

~~~xml
<uptodate property="page.current"
          srcfile="src/docs/index.xml"
          targetfile="build/docs/index.html"/>
~~~

Trong ví dụ:

- `property` là tên property được đặt khi target đã up-to-date.
- `srcfile` là file nguồn cần theo dõi.
- `targetfile` là file đầu ra cần kiểm tra.

Nếu `build/docs/index.html` không tồn tại hoặc cũ hơn `src/docs/index.xml`, property `page.current` không được đặt. Nếu target tồn tại và không cũ hơn source, Ant đặt `page.current`.

Có thể dùng property này để điều khiển target:

~~~xml
<target name="check-page">
    <uptodate property="page.current"
              srcfile="src/docs/index.xml"
              targetfile="build/docs/index.html"/>
</target>

<target name="generate-page" depends="check-page" unless="page.current">
    <mkdir dir="build/docs"/>
    <xslt in="src/docs/index.xml"
          out="build/docs/index.html"
          style="src/xsl/docs.xsl"/>
</target>
~~~

Khi `page.current` đã được đặt, target `generate-page` bị bỏ qua. Nếu property không được đặt, target chạy và tạo lại HTML.

Lưu ý: `unless` kiểm tra sự tồn tại của property, không diễn giải chuỗi giá trị `true` hoặc `false`. Vì `<uptodate>` chỉ đặt property khi up-to-date, mẫu trên hoạt động đúng. Nếu tự đặt property thành chuỗi `false`, nó vẫn được xem là tồn tại và target có `unless="page.current"` vẫn bị bỏ qua.

## 4. Kiểm tra nhiều source cùng tạo một output

Một output tổng hợp có thể phụ thuộc vào nhiều file nguồn. Ví dụ trang mục lục HTML được tạo từ nhiều tài liệu XML. Khi đó, output chỉ up-to-date nếu không có source nào mới hơn target.

~~~xml
<uptodate property="docs.index.current"
          targetfile="build/docs/index.html">
    <srcfiles dir="src/docs">
        <include name="**/*.xml"/>
        <exclude name="**/draft/**"/>
    </srcfiles>
</uptodate>
~~~

`<srcfiles>` chọn tập source cần so sánh. Trong ví dụ, Ant xét tất cả XML dưới `src/docs`, trừ nội dung trong thư mục `draft`.

Nếu bất kỳ source nào mới hơn `build/docs/index.html`, property `docs.index.current` không được đặt và trang mục lục cần được tạo lại. Nếu target tồn tại và không cũ hơn tất cả source được chọn, property được đặt.

Một pipeline hoàn chỉnh:

~~~xml
<property name="docs.src.dir" location="src/docs"/>
<property name="docs.out.dir" location="build/docs"/>

<target name="check-docs-index">
    <uptodate property="docs.index.current"
              targetfile="${docs.out.dir}/index.html">
        <srcfiles dir="${docs.src.dir}">
            <include name="**/*.xml"/>
            <exclude name="**/draft/**"/>
        </srcfiles>
    </uptodate>
</target>

<target name="generate-docs-index"
        depends="check-docs-index"
        unless="docs.index.current">
    <mkdir dir="${docs.out.dir}"/>
    <xslt basedir="${docs.src.dir}"
          destdir="${docs.out.dir}"
          includes="**/*.xml"
          excludes="**/draft/**"
          style="src/xsl/docs-index.xsl"
          extension=".html"/>
</target>
~~~

Trong ví dụ thực tế, stylesheet và cấu trúc output phải tương ứng với mục tiêu tạo index. Nếu một task tạo nhiều trang riêng biệt, hãy xác định rõ phép ánh xạ source-to-target; một target tổng hợp duy nhất chỉ phù hợp khi tất cả source cùng quyết định việc tạo một output chung.

## 5. Kiểm tra theo cặp file và ánh xạ nhiều output

Khi mỗi source tạo ra một target riêng, cần so sánh từng cặp tương ứng. Ví dụ:

~~~text
src/docs/intro.xml       -> build/docs/intro.html
src/docs/install.xml     -> build/docs/install.html
src/docs/reference.xml   -> build/docs/reference.html
~~~

Có thể dùng `<uptodate>` với tập source và một mapper để xác định tên target tương ứng:

~~~xml
<uptodate property="all.pages.current">
    <srcfiles dir="src/docs">
        <include name="**/*.xml"/>
    </srcfiles>
    <mapper type="glob" from="*.xml" to="*.html"/>
</uptodate>
~~~

Mapper chuyển tên file source thành tên file đích tương ứng. Khi dùng mapper, phải bảo đảm đường dẫn được ánh xạ trùng với cấu trúc output thực tế. Nếu output nằm trong thư mục khác, mapping phải bao gồm hoặc được cấu hình để so sánh đúng vị trí đích theo cách task hỗ trợ.

Với pipeline phức tạp, có thể chia kiểm tra theo thư mục/module hoặc dùng task generator có cơ chế incremental riêng. Tránh dùng một phép kiểm tra chung nếu các source tạo ra nhiều nhóm output với quy tắc ánh xạ khác nhau.

## 6. Target `if` và `unless` kiểm tra property theo cách nào?

Các thuộc tính `if` và `unless` của `<target>` kiểm tra property có được thiết lập hay không:

- `if="some.property"`: target chỉ chạy khi property tồn tại.
- `unless="some.property"`: target chỉ chạy khi property chưa tồn tại.

Chúng không tự parse nội dung property để hiểu boolean. Ví dụ:

~~~xml
<property name="ready" value="false"/>

<target name="publish" if="ready">
    <echo message="Publishing"/>
</target>
~~~

Target `publish` vẫn chạy vì property `ready` tồn tại, dù giá trị của nó là chuỗi `false`.

Với `<uptodate>`, mẫu phù hợp là chỉ đặt property khi up-to-date:

~~~xml
<uptodate property="artifact.current"
          srcfile="src/input.xml"
          targetfile="build/output.html"/>

<target name="generate" unless="artifact.current">
    <!-- Generate output only when it is stale. -->
</target>
~~~

Không cần đặt `artifact.current` thành `false` khi target stale. Để property chưa tồn tại là đủ cho `unless`.

## 7. Thời điểm kiểm tra điều kiện của target và thứ tự `depends`

Ant thực hiện các target phụ thuộc trước target hiện tại. Điều kiện `if`/`unless` của target được kiểm tra khi target đó đến lượt thực hiện, sau khi các dependency của nó đã chạy.

Vì vậy, nếu target `generate` phụ thuộc vào target `check`, property up-to-date cần được xác định trong `check`:

~~~xml
<target name="check-output">
    <uptodate property="output.current"
              srcfile="src/data.xml"
              targetfile="build/data.json"/>
</target>

<target name="generate-output"
        depends="check-output"
        unless="output.current">
    <java classname="com.example.GenerateJson" fork="true">
        <arg value="src/data.xml"/>
        <arg value="build/data.json"/>
    </java>
</target>
~~~

Nếu đặt task `<uptodate>` bên trong chính target có `unless`, Ant sẽ phải quyết định có chạy target hay không trước khi task bên trong target được thực hiện. Khi property chưa được thiết lập, target chạy; sau đó task mới kiểm tra timestamp, quá muộn để điều kiện `unless` ngăn các task còn lại trong cùng target.

Do đó, tách thành target kiểm tra và target thực hiện là mẫu rõ ràng. Cũng cần nhớ rằng dependency của một target vẫn chạy kể cả khi target đó bị bỏ qua bởi `if` hoặc `unless`.

## 8. `<available>` khác `<uptodate>` như thế nào?

`<available>` kiểm tra một tài nguyên có tồn tại hay không. Nó không so sánh thời điểm sửa đổi.

Ví dụ:

~~~xml
<available file="build/docs/index.html"
           type="file"
           property="index.exists"/>
~~~

Property `index.exists` được đặt nếu file tồn tại. Một file cũ từ lần build trước vẫn thỏa điều kiện này.

`<uptodate>` kiểm tra trạng thái tương đối giữa source và target:

~~~xml
<uptodate property="index.current"
          srcfile="src/docs/index.xml"
          targetfile="build/docs/index.html"/>
~~~

| Task | Câu hỏi được trả lời | Không kiểm tra |
|---|---|---|
| `<available>` | File/thư mục có tồn tại không? | File có mới hơn source không |
| `<uptodate>` | Output có tồn tại và không cũ hơn các source đã khai báo không? | Nội dung byte có giống kết quả mới không |

Có thể dùng cả hai khi logic cần phân biệt file chưa tồn tại với file tồn tại nhưng stale. Tuy nhiên, nếu chỉ cần quyết định có tạo lại output hay không, `<uptodate>` thường đã đủ.

## 9. Incremental compile của `<javac>`

Task `<javac>` của Ant có cơ chế chọn source cần biên dịch dựa trên output tương ứng trong `destdir`. Ant so sánh timestamp của source với class file đích; source mới hơn hoặc chưa có class tương ứng sẽ được đưa vào compiler.

Ví dụ:

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           encoding="UTF-8"
           includeantruntime="false"/>
</target>
~~~

Với source `src/main/java/com/example/App.java`, output tương ứng là `build/classes/com/example/App.class`. Nếu class file chưa tồn tại hoặc source mới hơn class, Ant chọn source đó để biên dịch.

### 9.1. Không phải mọi thay đổi đều làm source được biên dịch lại

Cơ chế chọn source của `<javac>` chủ yếu dựa trên timestamp và quan hệ source-to-class. Một số thay đổi quan trọng không nhất thiết làm source file mới hơn class file:

- Một JAR trên compile classpath được thay bằng phiên bản khác.
- Phiên bản JDK/compiler thay đổi.
- `source`, `target`, `release`, encoding hoặc compilerarg thay đổi.
- Annotation processor hoặc cấu hình processor thay đổi.
- Một file cấu hình được dùng để sinh source thay đổi nhưng source sinh ra giữ timestamp cũ.
- Một lớp cha hoặc API bên ngoài thay đổi mà timestamp source phụ thuộc không phản ánh.

Trong những trường hợp này, build tăng dần có thể giữ lại `.class` được biên dịch bằng cấu hình cũ. Nếu thay đổi ảnh hưởng đến bytecode hoặc tính đúng đắn của output, hãy xóa output cũ và compile lại hoặc tạo cơ chế stamp/input marker để biểu diễn các đầu vào cấu hình.

### 9.2. File source bị xóa không tự xóa class cũ

Nếu `OldService.java` bị xóa khỏi `src`, file `OldService.class` cũ trong `build/classes` có thể vẫn còn. `<javac>` không phải công cụ đồng bộ hoàn chỉnh giữa cây source và cây class output.

Một clean build xóa thư mục output trước khi biên dịch:

~~~xml
<target name="clean">
    <delete dir="build/classes"/>
</target>

<target name="compile-clean" depends="clean,compile"/>
~~~

Trong dự án thực tế, target clean nên xóa đúng các thư mục do build tạo ra. Không xóa thư mục chứa source hoặc dữ liệu người dùng.

## 10. Timestamp comparison không phải content hash

Một phép kiểm tra timestamp chỉ nhìn thời điểm sửa đổi. Nó không đọc toàn bộ nội dung để tính checksum.

Ví dụ, nếu một file source được thay đổi nhưng timestamp bị giữ nguyên hoặc được đặt về thời điểm cũ, Ant có thể coi output vẫn up-to-date. Ngược lại, chỉ chạm timestamp mà không đổi nội dung cũng có thể khiến Ant xử lý lại file.

| Thay đổi | Kết quả có thể xảy ra với timestamp check |
|---|---|
| Nội dung đổi và timestamp mới hơn | Phát hiện stale |
| Nội dung không đổi nhưng timestamp mới hơn | Có thể build lại không cần thiết |
| Nội dung đổi nhưng timestamp giữ nguyên | Có thể bỏ sót thay đổi |
| Nội dung đổi nhưng timestamp cũ hơn output | Có thể bị xem là up-to-date |
| File target bị xóa | Phát hiện target không tồn tại và cần tạo lại |

Nếu cần kiểm tra nội dung chính xác, cần cơ chế checksum/content hash hoặc build tool có input tracking sâu hơn. Ant core có thể gọi script hoặc task tùy chỉnh để tính hash, nhưng `<uptodate>` bản thân nó không phải content-based incremental engine.

## 11. Những vấn đề về độ chính xác của timestamp

Timestamp có thể gây kết quả bất ngờ trong một số môi trường:

- **Độ phân giải filesystem:** một số filesystem hoặc công cụ lưu trữ chỉ giữ timestamp với độ chính xác theo giây hoặc thấp hơn. Hai lần ghi gần nhau có thể có cùng timestamp.
- **Clock skew:** đồng hồ của máy build, máy lưu file hoặc filesystem mạng có thể lệch nhau. Source vừa được cập nhật có thể mang timestamp không lớn hơn target.
- **Copy/archive:** một số thao tác copy hoặc giải nén có thể bảo toàn timestamp gốc; nội dung được thay thế nhưng mtime không đổi.
- **Generated file:** generator có thể ghi output nhưng đặt timestamp theo nguồn hoặc theo một quy tắc riêng.
- **Timestamp tương lai:** file có mtime ở tương lai có thể khiến nó liên tục được xem là mới hơn output cho đến khi các lần build sau vượt qua mốc đó.

Ant có thuộc tính `granularity` trên một số task thao tác file như `<copy>` để tính đến độ phân giải timestamp của filesystem khi so sánh source và destination. Giá trị phù hợp phụ thuộc môi trường; đừng tự đặt một khoảng lớn nếu chưa hiểu tác động vì có thể bỏ qua thay đổi thực sự.

Để giảm rủi ro:

- Dùng filesystem và đồng hồ được đồng bộ trên CI.
- Tránh thay đổi nội dung file nhưng giữ nguyên timestamp nếu build dựa vào mtime.
- Pin cách giải nén/copy dependency và source để timestamp có ý nghĩa nhất quán.
- Dùng clean build sau khi đổi compiler, classpath hoặc cấu hình quan trọng.
- Dùng checksum khi cần xác định nội dung thay đổi chính xác.

## 12. Dùng `<copy>` với timestamp

Task `<copy>` cũng có thể bỏ qua file đích nếu file đích đã mới hơn source, thay vì ghi đè mọi lần.

Ví dụ:

~~~xml
<copy todir="build/resources">
    <fileset dir="src/main/resources">
        <include name="**/*"/>
    </fileset>
</copy>
~~~

Theo mặc định, Ant chỉ copy khi source mới hơn destination hoặc destination chưa tồn tại, trừ khi cấu hình như `overwrite` yêu cầu ghi đè. Nhờ đó, resource không thay đổi có thể được giữ nguyên.

Một số thuộc tính liên quan:

- `overwrite`: yêu cầu ghi đè file đích ngay cả khi file đích mới hơn.
- `preservelastmodified`: giữ timestamp sửa đổi của source trên file đích sau khi copy.
- `granularity`: điều chỉnh ngưỡng so sánh timestamp để phù hợp độ phân giải filesystem.

Ví dụ:

~~~xml
<copy todir="build/resources"
      preservelastmodified="true"
      granularity="1000">
    <fileset dir="src/main/resources">
        <include name="**/*"/>
    </fileset>
</copy>
~~~

`preservelastmodified="true"` hữu ích khi timestamp của file đích cần phản ánh timestamp nguồn, chẳng hạn để bước incremental tiếp theo không coi file vừa copy là mới hơn một cách giả tạo. `granularity` ở ví dụ là 1000 ms; chỉ dùng giá trị phù hợp với môi trường thực tế.

Nếu đặt `overwrite="true"`, copy có thể chạy lại dù destination mới hơn source. Điều này phù hợp khi cần đồng bộ nội dung theo một chính sách cụ thể, nhưng có thể làm mất lợi ích incremental và ghi đè file đích có nội dung mới hơn.

## 13. Tổ chức up-to-date check cho nhiều đầu ra

Một task generator có thể tạo nhiều file từ một nhóm source. Cần xác định rõ quan hệ đầu vào/đầu ra:

~~~text
src/templates/a.xml  ---> build/generated/a.java
src/templates/b.xml  ---> build/generated/b.java
src/templates/c.xml  ---> build/generated/c.java
~~~

Nếu tất cả source tạo một archive tổng hợp, có thể so sánh cả tập source với một target archive. Nếu mỗi source tạo một file riêng, nên kiểm tra từng cặp hoặc dùng mapper đúng với cấu trúc output.

Một phép kiểm tra tổng hợp có thể bỏ qua cả nhóm nếu archive mới hơn mọi source, nhưng nó không cho biết file đầu ra riêng lẻ nào bị thiếu hoặc stale. Khi một target duy nhất đại diện cho nhiều output, việc xóa một output con có thể không làm target archive trở nên cũ hơn. Vì vậy, đừng dùng một stamp file hoặc archive tổng hợp làm bằng chứng duy nhất nếu các output riêng lẻ cũng cần tồn tại.

Có thể dùng một file stamp để biểu diễn việc một bước hoàn tất, nhưng chỉ nên làm khi dependency graph và quy trình clean bảo đảm stamp luôn được xóa khi bất kỳ đầu vào quan trọng nào thay đổi. Nếu không, stamp cũ có thể che giấu output bị thiếu.

## 14. Khi nào nên chạy clean build?

Incremental build giúp tăng tốc, còn clean build giúp kiểm tra khả năng tái tạo toàn bộ output từ đầu vào hiện tại.

Nên chạy clean build khi:

- Thay đổi JDK, compiler hoặc phiên bản Ant.
- Thay đổi compiler flags, encoding hoặc `--release`.
- Nâng cấp hoặc thay thế dependency trên classpath.
- Thay đổi annotation processor hoặc code generator.
- Xóa hoặc đổi tên source/package mà output cũ có thể còn sót.
- Thay đổi quy tắc include/exclude hoặc cấu trúc output.
- Điều tra lỗi chỉ xuất hiện trên một máy hoặc sau nhiều lần build tăng dần.
- Chuẩn bị artifact phát hành quan trọng.

Có thể định nghĩa target tổng hợp:

~~~xml
<target name="clean">
    <delete dir="build"/>
    <delete dir="dist"/>
</target>

<target name="clean-build" depends="clean,package"/>
~~~

Với Ant, các target trong `depends` được xử lý theo thứ tự khai báo dependency. Đảm bảo `clean` thực sự chạy trước `package` trong target tổng hợp; nếu cần luồng phức tạp hơn, hãy tách target trung gian để thể hiện thứ tự rõ ràng.

Không nhất thiết phải clean trước mọi lần compile khi đang phát triển. Hãy dùng incremental build cho vòng lặp nhanh và clean build trong các mốc kiểm tra, CI hoặc phát hành phù hợp.

## 15. Lỗi thường gặp khi kiểm tra up-to-date

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Task bỏ qua dù nội dung source đã đổi | Timestamp source không mới hơn target | Kiểm tra mtime; dùng clean hoặc content hash nếu cần |
| Task chạy lại dù nội dung không đổi | Timestamp source mới hơn target | Xem lại copy/generator có chạm timestamp không |
| Output bị thiếu nhưng stamp vẫn up-to-date | Chỉ kiểm tra stamp tổng hợp, không kiểm tra từng output | Kiểm tra từng target hoặc tái tạo khi output con thiếu |
| `unless` không hoạt động khi property có giá trị `false` | `unless` kiểm tra property tồn tại, không kiểm tra boolean | Chỉ đặt property khi điều kiện đúng hoặc dùng condition phù hợp |
| `<uptodate>` luôn không đặt property | Target thiếu, source mới hơn hoặc sai đường dẫn | Kiểm tra `srcfile`, `targetfile`, FileSet và basedir |
| `<uptodate>` báo up-to-date nhưng output không đúng | Timestamp không phản ánh nội dung hoặc đầu vào phụ chưa được khai báo | Khai báo đủ input, dùng clean hoặc checksum |
| Javac không biên dịch lại sau khi đổi JAR dependency | Source timestamp không đổi | Xóa classes output hoặc dùng marker cho classpath/configuration |
| Class cũ vẫn tồn tại sau khi xóa source | Javac không đồng bộ xóa output | Clean output trước compile hoặc thêm bước dọn class tương ứng |
| Build khác nhau giữa filesystem | Độ phân giải timestamp/clock skew | Đồng bộ clock, cấu hình granularity phù hợp, kiểm tra clean build |
| Copy ghi đè file mới hơn | `overwrite="true"` | Bỏ overwrite hoặc xác định lại chính sách đồng bộ |

Khi điều tra, hãy in đường dẫn tuyệt đối và timestamp của source/target. Có thể dùng `<echo>` để xác nhận property path, hoặc kiểm tra file bằng công cụ hệ điều hành. Chạy riêng target check giúp xác định property up-to-date có được đặt hay không trước khi generator chạy.

## 16. Quy trình debug một up-to-date check

Một trình tự ngắn giúp xác định nguyên nhân:

1. Xác nhận source và target trỏ tới đúng file.
2. Kiểm tra target có tồn tại không.
3. So sánh thời điểm sửa đổi của từng source với target.
4. Xác nhận FileSet không chọn thừa hoặc bỏ sót file.
5. Kiểm tra mapper nếu mỗi source tạo một target riêng.
6. Kiểm tra property có bị đặt trước đó trong cùng project không.
7. Xác nhận target check chạy trước target có `if`/`unless`.
8. Xem các dependency của target có chạy dù target bị bỏ qua hay không.
9. Nếu timestamp không đủ mô tả đầu vào, thêm dependency marker hoặc chạy clean.

Có thể bật log chi tiết:

~~~bash
ant -verbose generate-docs-index
ant -debug generate-docs-index
~~~

Với một dự án lớn, có thể tạo target chẩn đoán chỉ in basedir, source path, target path và trạng thái property. Tránh thay đổi timestamp thủ công trong CI như một cách sửa lỗi lâu dài; hãy sửa nguyên nhân khiến timestamp không phản ánh đầu vào thật.

## Kết luận

Ant dùng timestamp để quyết định nhiều công việc có cần chạy lại hay không. `<uptodate>` đặt property khi target tồn tại và không cũ hơn các source được khai báo; target có thể dùng `unless` để bỏ qua bước tạo output khi property đó tồn tại. `<javac>` cũng dùng so sánh timestamp giữa source và class tương ứng để biên dịch tăng dần. Cơ chế này nhanh nhưng chỉ đáng tin trong phạm vi đầu vào được khai báo và timestamp phản ánh đúng thay đổi. Thay đổi dependency, compiler option, file bị xóa, timestamp được bảo toàn hoặc filesystem có độ phân giải thấp có thể khiến kết quả không như mong đợi. Hãy tách target kiểm tra khỏi target tạo output, kiểm soát property và dependency rõ ràng, dùng clean build ở các mốc phù hợp và cân nhắc checksum khi cần kiểm tra nội dung thay vì chỉ mtime.

## Tài liệu tham khảo

- [Apache Ant – UpToDate Task](https://ant.apache.org/manual/Tasks/uptodate.html)
- [Apache Ant – Javac Task](https://ant.apache.org/manual/Tasks/javac.html)
- [Apache Ant – Copy Task](https://ant.apache.org/manual/Tasks/copy.html)
- [Apache Ant – Targets and Buildfile Basics](https://ant.apache.org/manual/using.html)
# Thực thi công cụ trên nhiều tệp bằng apply

Trong Apache Ant, task `<exec>` dùng để chạy một chương trình bên ngoài. Khi cần gọi cùng một công cụ cho nhiều tệp, viết một `<exec>` riêng cho từng tệp sẽ làm buildfile dài và khó bảo trì. Task `<apply>` giải quyết trường hợp này: nó lấy một tập tệp từ `FileSet` hoặc ResourceCollection, tạo dòng lệnh cho công cụ và đưa tên từng tệp vào vị trí đối số đã định.

`apply` phù hợp với các công cụ dòng lệnh như formatter, linter, compiler native, bộ chuyển đổi ảnh, trình kiểm tra schema hoặc tiện ích xử lý tài liệu. Điểm quan trọng là chọn đúng chế độ chạy: một lần gọi cho mỗi tệp hay gom nhiều tệp vào một lần gọi; đồng thời kiểm soát vị trí source file, tên output, thư mục làm việc, mã thoát và thời gian chờ.

## 1. apply khác gì exec?

`exec` thực thi một chương trình với các đối số do buildfile chỉ định. `apply` cũng thực thi chương trình bên ngoài, nhưng có thêm khả năng lặp qua một tập tệp và chèn tên tệp vào dòng lệnh.

| Task | Mục đích chính | Cách đưa tệp vào lệnh |
|---|---|---|
| `exec` | Chạy một lệnh cụ thể | Khai báo các đối số tường minh bằng `<arg>` |
| `apply` | Chạy một lệnh trên một hoặc nhiều tệp được chọn | Lấy tệp từ FileSet/ResourceCollection và thêm tên tệp vào đối số |

Ví dụ dùng `exec` để chạy một công cụ với một file cố định:

```xml
<exec executable="validator" failonerror="true">
    <arg value="--strict" />
    <arg file="config/application.xml" />
</exec>
```

Nếu muốn kiểm tra mọi file XML dưới `config`, `apply` mô tả tập đầu vào trực tiếp hơn:

```xml
<apply executable="validator" relative="true" failonerror="true">
    <arg value="--strict" />
    <fileset dir="config">
        <include name="**/*.xml" />
    </fileset>
</apply>
```

Trong chế độ mặc định, Ant gọi `validator` một lần cho mỗi tệp được chọn và thêm tên tệp làm đối số nguồn. Với ba tệp XML, công cụ được gọi ba lần.

## 2. Cấu trúc cơ bản của apply

Task thường có một thuộc tính `executable`, các phần tử `<arg>` để cấu hình đối số cố định và một ResourceCollection để chọn tệp:

```xml
<target name="check-xml">
    <apply
        executable="validator"
        relative="true"
        failonerror="true">

        <arg value="--no-network" />
        <arg value="--schema" />
        <arg file="config/schema.xsd" />

        <fileset dir="config">
            <include name="**/*.xml" />
            <exclude name="**/examples/**" />
        </fileset>
    </apply>
</target>
```

Trong ví dụ:

- `executable` là chương trình cần chạy. Có thể dùng tên chương trình tìm thấy qua PATH hoặc đường dẫn tới executable.
- `<arg>` khai báo các đối số cố định được truyền cho mọi lần gọi.
- `<fileset>` xác định tập XML đầu vào.
- `failonerror="true"` yêu cầu build thất bại nếu công cụ trả mã thoát khác 0.

Nếu không khai báo vị trí chèn source file, `apply` tự thêm tên tệp nguồn vào cuối danh sách đối số theo mặc định. Vì vậy, lệnh tương đương với một tệp có dạng:

```text
validator --no-network --schema config/schema.xsd application.xml
```

Ant tự liệt kê các tệp phù hợp với mẫu. Không cần viết wildcard của shell như `config/**/*.xml` vào đối số và kỳ vọng chương trình tự mở rộng nó.

## 3. Chạy riêng từng tệp hay gom nhiều tệp?

Thuộc tính `parallel` quyết định cách Ant nhóm các tệp nguồn vào dòng lệnh:

- `parallel="false"` (mặc định): Ant gọi chương trình riêng cho từng tệp.
- `parallel="true"`: Ant có thể truyền nhiều tên tệp vào cùng một lần gọi chương trình.

Tên `parallel` dễ gây hiểu nhầm. Nó nói về việc gom danh sách tệp vào một invocation, không tự động tạo nhiều tiến trình chạy đồng thời.

### Một lần gọi cho mỗi tệp

```xml
<apply executable="image-tool" parallel="false" relative="true" failonerror="true">
    <arg value="--resize" />
    <arg value="800x600" />
    <fileset dir="src/images">
        <include name="*.png" />
        <include name="*.jpg" />
    </fileset>
</apply>
```

Với `logo.png` và `cover.jpg`, Ant tạo các lệnh riêng, về ý tưởng tương đương:

```text
image-tool --resize 800x600 logo.png
image-tool --resize 800x600 cover.jpg
```

Chế độ này phù hợp khi công cụ chỉ nhận một tệp đầu vào mỗi lần hoặc cần cách ly kết quả và mã thoát của từng tệp.

### Gom nhiều tệp vào một lần gọi

```xml
<apply executable="scanner"
       parallel="true"
       maxparallel="40"
       failonerror="true">
    <arg value="--check" />
    <fileset dir="src">
        <include name="**/*.java" />
    </fileset>
</apply>
```

Nếu công cụ `scanner` hỗ trợ nhận nhiều đường dẫn trong một lệnh, Ant có thể truyền một nhóm tối đa 40 tệp trong mỗi invocation. `maxparallel` giới hạn số tệp được gom vào một lần gọi; nó không phải số tiến trình chạy song song.

Gom tệp có thể giảm chi phí khởi động chương trình, nhưng chỉ dùng khi công cụ hỗ trợ cú pháp nhận nhiều tệp. Nếu chương trình chỉ nhận một file hoặc cách diễn giải đối số phụ thuộc vị trí, hãy giữ `parallel="false"`.

## 4. Đặt vị trí tên tệp bằng srcfile

Mặc định, `apply` tự thêm source file vào cuối danh sách đối số. Phần tử `<srcfile />` cho phép chọn vị trí chính xác của tên tệp trong dòng lệnh.

Ví dụ một công cụ yêu cầu tên tệp xuất hiện ngay sau tùy chọn `--input`:

```xml
<apply executable="document-checker" relative="true" failonerror="true">
    <arg value="--input" />
    <srcfile />
    <arg value="--format" />
    <arg value="json" />

    <fileset dir="documents">
        <include name="**/*.xml" />
    </fileset>
</apply>
```

Lệnh được tạo cho một tệp có dạng:

```text
document-checker --input report.xml --format json
```

`<srcfile />` là placeholder do Ant xử lý; nó không phải một đối số literal được truyền nguyên văn cho chương trình. Dùng placeholder này khi công cụ yêu cầu thứ tự đối số cụ thể.

Thuộc tính `addsourcefile` điều khiển việc Ant tự thêm tên tệp nguồn. Giá trị mặc định là `true`. Khi muốn tự kiểm soát toàn bộ đối số nguồn, có thể đặt `addsourcefile="false"` và đặt `<srcfile />` tại vị trí mong muốn. Không nên vừa tắt tự động thêm nguồn vừa quên placeholder, nếu không chương trình sẽ không nhận được tệp đầu vào.

## 5. Tạo tên output bằng targetfile và mapper

Một số công cụ tạo một tệp đầu ra cho mỗi tệp nguồn. Khi đó, `apply` có thể dùng `dest`, mapper và placeholder `<targetfile />` để xác định đường dẫn output tương ứng.

Ví dụ biên dịch từng tệp C thành một tệp object:

```xml
<target name="compile-native">
    <mkdir dir="build/objects" />

    <apply
        executable="cc"
        dest="build/objects"
        relative="true"
        parallel="false"
        failonerror="true">

        <arg value="-c" />
        <srcfile />
        <arg value="-o" />
        <targetfile />

        <fileset dir="src/native">
            <include name="**/*.c" />
        </fileset>

        <mapper type="glob" from="**/*.c" to="**/*.o" />
    </apply>
</target>
```

Với tệp nguồn nằm tại `src/native/math/vector.c`, mapper tạo tên đích tương đối `math/vector.o` dưới `build/objects`. Do `relative="true"`, tên nguồn được truyền tương đối với thư mục gốc của FileSet. Dòng lệnh có dạng:

```text
cc -c math/vector.c -o build/objects/math/vector.o
```

Vai trò từng phần:

- `dest` là thư mục gốc nhận các tệp đích.
- `mapper` biến đổi tên tương đối của nguồn thành tên tương đối của output.
- `<srcfile />` chèn đường dẫn tệp nguồn vào dòng lệnh.
- `<targetfile />` chèn đường dẫn đích do mapper tạo.

Mapper không thực thi công cụ và không tạo nội dung output. Nó chỉ tính tên đường dẫn đích để Ant có thể truyền cho chương trình. Công cụ bên ngoài vẫn chịu trách nhiệm tạo tệp tại đường dẫn đó.

Khi output nằm trong thư mục con, hãy bảo đảm thư mục đích tương ứng được tạo trước nếu công cụ không tự tạo thư mục. Có thể dùng một bước chuẩn bị output hoặc cấu hình công cụ để tạo thư mục cha.

## 6. Mapper và quy tắc đổi tên

Mapper dùng trong `apply` hoạt động theo cơ chế ánh xạ tên tệp của Ant. Một số kiểu thường gặp:

| Mapper | Cách ánh xạ | Ví dụ |
|---|---|---|
| `identity` | Giữ nguyên tên | `a.c` → `a.c` |
| `glob` | Thay phần khớp wildcard trong mẫu nguồn bằng mẫu đích | `a.c` → `a.o` |
| `flatten` | Bỏ các thành phần thư mục | `src/math/a.c` → `a.c` |
| `regexp` | Dùng biểu thức chính quy để đổi tên | `a.source` → `a.generated` |

Ví dụ mapper glob:

```xml
        <mapper type="glob" from="**/*.scss" to="**/*.css" />
```

Với tệp nguồn `theme.scss`, mapper tạo tên đích `theme.css`. Nếu nguồn có thư mục con, đường dẫn tương đối được xử lý theo mẫu và cấu hình mapper.

Ví dụ flatten:

```xml
<mapper type="flatten" />
```

Mapper này gom các tên về một cấp. Cần chú ý xung đột: `module-a/config.xml` và `module-b/config.xml` đều có thể trở thành `config.xml`. Khi nhiều nguồn cùng ánh xạ đến một output, một tệp có thể ghi đè hoặc làm mất kết quả của tệp khác. Hãy giữ cấu trúc thư mục hoặc tạo tên đích duy nhất.

## 7. Chọn file hoặc directory

Task `apply` có thể làm việc với tệp hoặc thư mục được cung cấp bởi ResourceCollection. Thuộc tính `type` xác định loại đối tượng cần xử lý; các giá trị thường dùng là `file` và `dir`.

Ví dụ xử lý tệp:

```xml
<apply executable="checksum-tool" type="file" failonerror="true">
    <arg value="--sha256" />
    <fileset dir="release">
        <include name="**/*" />
    </fileset>
</apply>
```

Ví dụ xử lý các thư mục con:

```xml
<apply executable="directory-audit" type="dir" failonerror="true">
    <arg value="--inspect" />
    <fileset dir="modules">
        <include name="*/" />
    </fileset>
</apply>
```

Hãy bảo đảm chương trình được gọi hiểu loại đường dẫn mà Ant truyền vào. Một công cụ chỉ đọc file sẽ không tự xử lý directory nếu task được cấu hình `type="dir"`.

## 8. Đường dẫn tuyệt đối, tương đối và dấu phân cách

Tên file được truyền cho công cụ có thể là đường dẫn tuyệt đối hoặc tương đối tùy cấu hình. Thuộc tính `relative` cho phép yêu cầu sử dụng đường dẫn tương đối so với base directory của FileSet/collection trong những trường hợp task hỗ trợ. Nếu công cụ cần đường dẫn tương đối để tạo output ổn định hoặc ghi metadata có thể tái lập, hãy cấu hình và kiểm tra rõ hành vi này.

Thuộc tính `forwardslash` có thể yêu cầu Ant dùng dấu `/` trong đường dẫn truyền cho công cụ. Điều này hữu ích với công cụ đa nền tảng chấp nhận slash trên Windows, hoặc khi đối số được lưu vào file cấu hình và cần định dạng thống nhất.

Ví dụ:

```xml
<apply
    executable="source-indexer"
    relative="true"
    forwardslash="true"
    failonerror="true">
    <arg value="--index" />
    <fileset dir="src">
        <include name="**/*.java" />
    </fileset>
</apply>
```

Đường dẫn tương đối giúp kết quả ít phụ thuộc vào vị trí checkout tuyệt đối. Tuy nhiên, nếu chương trình cần truy cập file từ một working directory khác, phải bảo đảm đường dẫn vẫn được phân giải đúng.

## 9. Thư mục làm việc và biến môi trường

Thuộc tính `dir` đặt working directory của tiến trình được gọi. Đây là thư mục mà chương trình dùng để phân giải các đường dẫn tương đối trong đối số và để tạo file nếu nó ghi theo đường dẫn tương đối.

```xml
<apply
    executable="node"
    dir="frontend"
    failonerror="true">

    <arg file="${basedir}/frontend/tools/check-one.js" />
    <srcfile />

    <fileset dir="frontend/src">
        <include name="**/*.js" />
    </fileset>
</apply>
```

Khi đặt `dir="frontend"`, đường dẫn tương đối của đối số cần được hiểu từ thư mục đó. Hãy tránh trộn lẫn đường dẫn tính từ project base directory với đường dẫn tính từ working directory của tiến trình.

Có thể truyền biến môi trường bằng phần tử `<env>`:

```xml
<apply executable="compiler-tool" dir="native" failonerror="true">
    <env key="BUILD_MODE" value="release" />
    <env key="TOOL_CONFIG" file="config/compiler.properties" />
    <arg value="--compile" />
    <fileset dir="native/src">
        <include name="**/*.c" />
    </fileset>
</apply>
```

`<env>` đặt biến môi trường cho tiến trình con. Nếu cần thay thế toàn bộ môi trường kế thừa, task hỗ trợ thuộc tính `newenvironment`; khi đó phải khai báo đầy đủ các biến mà chương trình cần. Nếu không, Ant thường giữ môi trường hiện có và bổ sung/ghi đè các biến được khai báo.

## 10. Xử lý trường hợp không có tệp đầu vào

Một FileSet có thể không khớp tệp nào vì thư mục rỗng, mẫu include sai hoặc dữ liệu chưa được tạo. Thuộc tính `skipemptyfilesets` điều khiển việc bỏ qua lần gọi khi tập đầu vào rỗng.

```xml
<apply
    executable="optional-scanner"
    skipemptyfilesets="true">
    <arg value="--scan" />
    <fileset dir="generated/reports">
        <include name="**/*.xml" />
    </fileset>
</apply>
```

Điều này phù hợp khi không có tệp là tình huống hợp lệ, chẳng hạn module không tạo báo cáo XML. Nếu ít nhất một tệp là yêu cầu bắt buộc, đừng âm thầm bỏ qua. Hãy kiểm tra sự tồn tại hoặc số lượng tài nguyên trước bằng `available`, `resourcecount`, `condition` và `fail` để thông báo rõ ràng.

Việc bỏ qua FileSet rỗng cũng không thay thế kiểm tra thư mục nguồn. Nếu đường dẫn nguồn sai, build có thể cần dừng thay vì coi đó là không có việc để làm.

## 11. Mã thoát, lỗi thực thi và timeout

`apply` chạy một chương trình bên ngoài, do đó buildfile cần quyết định phản ứng với lỗi khởi chạy và mã thoát khác 0.

Các thuộc tính thường cần quan tâm:

| Thuộc tính | Mục đích |
|---|---|
| `failonerror` | Làm task thất bại khi chương trình trả mã thoát khác 0 |
| `failifexecutionfails` | Điều khiển việc task thất bại nếu Ant không thể khởi chạy chương trình |
| `timeout` | Giới hạn thời gian chạy, tính bằng mili giây |
| `resultproperty` | Lưu mã thoát vào property để target sau xử lý |

Ví dụ đặt timeout và yêu cầu build dừng khi một tệp không hợp lệ:

```xml
<apply
    executable="schema-validator"
    timeout="60000"
    failonerror="true"
    failifexecutionfails="true">

    <arg value="--strict" />
    <fileset dir="src/config">
        <include name="**/*.xml" />
    </fileset>
</apply>
```

`timeout="60000"` giới hạn mỗi tiến trình được gọi theo cấu hình task ở mức 60 giây. Với chế độ một lần gọi cho mỗi file, mỗi invocation có giới hạn riêng. Khi gom nhiều tệp, thời gian xử lý cả nhóm cần được tính đến.

Nếu muốn ghi nhận mã thoát để tự quyết định, có thể dùng `resultproperty` trong cấu hình thực thi phù hợp:

```xml
<target name="check-generated-source">
    <apply
        executable="source-checker"
        failonerror="false"
        resultproperty="source.check.exit">
        <arg value="--check" />
        <fileset dir="generated">
            <include name="**/*.java" />
        </fileset>
    </apply>
</target>

<target name="report-check-result" depends="check-generated-source">
    <echo message="Source checker exit code: ${source.check.exit}" />
</target>
```

Khi dùng `resultproperty`, cần hiểu kết quả có ý nghĩa theo chế độ gọi của task và phiên bản Ant. Với `parallel="true"`, một lần gọi có thể xử lý nhiều tệp cùng lúc nên không thể suy ra mã thoát riêng cho từng tệp từ một property duy nhất. Nếu cần quyết định riêng theo từng file, dùng chế độ không parallel hoặc để công cụ xuất báo cáo chi tiết.

## 12. Thu thập stdout và stderr

Có thể chuyển output của công cụ vào file hoặc property để phục vụ log và bước xử lý tiếp theo. Ví dụ:

```xml
<apply
    executable="xml-validator"
    output="build/logs/xml-validator.out"
    error="build/logs/xml-validator.err"
    failonerror="true">

    <arg value="--verbose" />
    <fileset dir="config">
        <include name="**/*.xml" />
    </fileset>
</apply>
```

`output` định tuyến stdout và `error` định tuyến stderr theo cơ chế redirect của task. Nếu công cụ chạy một lần cho mỗi tệp, hãy xác định cách log được ghi nối hay thay thế theo cấu hình redirector và phiên bản Ant; tránh để nhiều invocation ghi đè một log khiến mất thông tin.

Với công cụ tạo log riêng cho từng tệp, có thể dùng một bước wrapper hoặc cấu hình redirector/mapper phù hợp để tạo tên output duy nhất. Nếu chỉ cần log chung cho cả lần chạy, có thể ghi stdout/stderr ra file build log và giữ lại mã thoát để Ant quyết định thành công.

## 13. Dùng apply để biến đổi tệp theo cặp source và target

Một use case phổ biến là chuyển từng tệp nguồn thành một tệp đầu ra tương ứng. Ví dụ gọi `sass` để đổi `.scss` thành `.css`:

```xml
<target name="compile-styles">
    <mkdir dir="build/css" />

    <apply
        executable="sass"
        dest="build/css"
        relative="true"
        parallel="false"
        failonerror="true">

        <arg value="--no-source-map" />
        <srcfile />
        <targetfile />

        <fileset dir="src/scss">
            <include name="**/*.scss" />
            <exclude name="**/_*.scss" />
        </fileset>

    <mapper type="glob" from="**/*.scss" to="**/*.css" />
    </apply>
</target>
```

Với `src/scss/theme/main.scss`, mapper tạo `build/css/theme/main.css`. Các partial có tên bắt đầu bằng `_` bị loại khỏi tập nguồn vì chúng được import bởi stylesheet khác và không cần biên dịch độc lập.

Trước khi dùng ví dụ với một công cụ thật, hãy kiểm tra cú pháp CLI của phiên bản công cụ đang cài. Một số chương trình nhận thứ tự `source output`, số khác yêu cầu cờ `-o output source`; chỉ cần thay đổi vị trí `<srcfile />` và `<targetfile />` cùng các `<arg>` để phù hợp.

## 14. Không nhầm apply với shell script

`apply` gọi executable trực tiếp và truyền các đối số theo cấu hình của Ant. Nó không mặc định chạy một shell để diễn giải `|`, `>`, `&&`, wildcard hoặc biến môi trường kiểu shell.

Ví dụ sau không tạo pipeline shell như mong đợi:

```xml
<apply executable="tool">
    <arg value="--check" />
    <arg value="|" />
    <arg value="grep" />
    <fileset dir="src" includes="**/*.txt" />
</apply>
```

Các chuỗi `|` và `grep` chỉ là đối số được truyền cho `tool`; Ant không tự tạo pipeline. Nếu thực sự cần shell, phải gọi executable shell cụ thể và truyền script theo cú pháp của hệ điều hành. Tuy nhiên, cách đó làm buildfile phụ thuộc nền tảng; nếu có thể, hãy dùng trực tiếp tùy chọn của công cụ hoặc tạo một script riêng có kiểm soát.

Với đường dẫn chứa dấu cách, dùng `<arg value="..." />`, `<arg file="..." />` hoặc placeholder `<srcfile />` để Ant truyền mỗi đường dẫn như một đối số. Tránh ghép toàn bộ lệnh thành một chuỗi `<arg line="..." />` khi các giá trị có thể chứa dấu cách hoặc ký tự đặc biệt.

## 15. Ví dụ buildfile tổng hợp

Ví dụ dưới đây có hai bước: formatter chạy riêng trên mỗi file Java; scanner gom nhiều file vào một lần gọi nếu chương trình hỗ trợ batch.

```xml
<project name="external-tools" default="check-source">

    <property name="source.dir" value="src/main/java" />

    <target name="format-source">
        <apply
            executable="java-formatter"
            parallel="false"
            failonerror="true"
            timeout="120000">

            <arg value="--write" />
            <srcfile />

            <fileset dir="${source.dir}">
                <include name="**/*.java" />
                <exclude name="**/generated/**" />
            </fileset>
        </apply>
    </target>

    <target name="check-source" depends="format-source">
        <apply
            executable="source-scanner"
            parallel="true"
            maxparallel="50"
            failonerror="true"
            timeout="180000">

            <arg value="--rules" />
            <arg file="config/source-rules.yml" />

            <fileset dir="${source.dir}">
                <include name="**/*.java" />
                <exclude name="**/generated/**" />
            </fileset>
        </apply>
    </target>

</project>
```

Ví dụ giả định `java-formatter` hỗ trợ một file nguồn mỗi invocation và tùy chọn `--write` sửa tệp tại chỗ; `source-scanner` nhận nhiều đường dẫn trong một invocation. Nếu formatter tạo một tệp output riêng thay vì sửa nguồn, hãy cấu hình `dest`, mapper và `<targetfile />` như ví dụ biên dịch native ở trên. `apply` không tự suy ra thư mục output chỉ từ tên thư mục trong buildfile.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Công cụ chạy nhưng không nhận file nguồn | `addsourcefile="false"` mà không có `<srcfile />`, hoặc FileSet rỗng | Kiểm tra placeholder và mẫu include/exclude |
| Tên file xuất hiện ở cuối lệnh thay vì vị trí cần thiết | Chưa dùng `<srcfile />` | Đặt placeholder tại vị trí CLI yêu cầu |
| Công cụ báo quá nhiều đối số | `parallel="true"` gom nhiều file trong khi tool chỉ nhận một file | Dùng `parallel="false"` |
| Công cụ chạy nhiều lần ngoài dự kiến | `parallel="false"` gọi một lần cho mỗi file | Dùng `parallel="true"` nếu tool hỗ trợ batch |
| Đường dẫn output sai | Mapper hoặc `dest` không khớp cấu trúc nguồn | Kiểm tra tên tương đối đầu vào và kết quả mapper |
| Nhiều file ghi đè cùng output | Mapper tạo tên đích trùng nhau, thường gặp với flatten | Giữ cấu trúc thư mục hoặc tạo tên output duy nhất |
| Công cụ không tìm thấy file khi có dấu cách | Đường dẫn bị ghép thành một chuỗi đối số sai | Dùng `<arg value>`, `<arg file>` và `<srcfile />` |
| Lệnh chứa `|` hoặc `>` không hoạt động | Ant gọi executable trực tiếp, không có shell mặc định | Dùng tùy chọn công cụ hoặc gọi shell tường minh khi thật sự cần |
| Build treo khi công cụ xử lý một file | Tiến trình không kết thúc hoặc chờ input | Đặt `timeout`, kiểm tra stdin và vòng đời của công cụ |
| Build vẫn thành công dù tool trả lỗi | `failonerror` không được bật | Đặt `failonerror="true"` cho bước bắt buộc |
| Không có file nhưng task vẫn gọi công cụ | Tập nguồn rỗng và chưa cấu hình bỏ qua/kiểm tra | Dùng `skipemptyfilesets` hoặc `fail` theo yêu cầu |

Khi debug, hãy xem dòng lệnh thực tế Ant tạo ra, số lần gọi, đường dẫn nguồn/đích và mã thoát. Nếu vấn đề chỉ xảy ra trên một số file, thử một FileSet nhỏ với một đường dẫn chứa dấu cách và một đường dẫn trong thư mục con để xác định lỗi thuộc argument handling hay mapper.

## 17. Quy trình thiết kế apply

Khi cần chạy một công cụ ngoài trên nhiều tệp, có thể thực hiện theo trình tự sau:

1. Xác định executable và cú pháp CLI chính xác của công cụ.
2. Chọn các tệp nguồn bằng `FileSet` hoặc ResourceCollection, với include/exclude đủ hẹp.
3. Quyết định công cụ nhận một file mỗi lần hay nhiều file trong một invocation; chọn `parallel` tương ứng.
4. Đặt `<srcfile />` ở đúng vị trí; nếu công cụ tạo output cho từng nguồn, dùng `dest`, mapper và `<targetfile />`.
5. Chọn đường dẫn tuyệt đối/tương đối, dấu phân cách, working directory và biến môi trường phù hợp.
6. Đặt timeout, chính sách mã thoát và cách thu thập stdout/stderr.
7. Xác định hành vi khi tập đầu vào rỗng: bỏ qua nếu hợp lệ hoặc dừng sớm nếu thiếu dữ liệu là lỗi.
8. Chạy thử với một tập nhỏ, xem dòng lệnh được tạo và kiểm tra output trước khi áp dụng cho toàn bộ dự án.

`apply` kết nối một tập tệp với một chương trình bên ngoài. `FileSet` quyết định tệp nào được xử lý, `parallel` quyết định cách gom tệp vào invocation, `<srcfile />` và `<targetfile />` kiểm soát vị trí đối số, còn mapper xác định tên output. Khi kết hợp các phần này với working directory, environment, timeout và chính sách lỗi rõ ràng, buildfile có thể tự động hóa công cụ dòng lệnh trên nhiều tệp một cách dễ kiểm soát.

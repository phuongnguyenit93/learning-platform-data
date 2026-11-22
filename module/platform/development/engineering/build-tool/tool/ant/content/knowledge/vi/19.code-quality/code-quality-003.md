# Phân tích tĩnh bằng PMD và SpotBugs

Phân tích tĩnh (static analysis) là việc kiểm tra mã nguồn hoặc bytecode mà không cần chạy ứng dụng theo các kịch bản thông thường. Công cụ phân tích tìm những mẫu có khả năng gây lỗi, làm mã khó bảo trì, tạo rủi ro bảo mật hoặc dẫn tới hành vi không mong muốn. Với Apache Ant, có thể tích hợp các công cụ này thành target riêng trong `build.xml`, tạo báo cáo tự động và đặt điều kiện để build dừng khi phát hiện vấn đề nghiêm trọng.

PMD và SpotBugs bổ sung cho nhau. PMD chủ yếu phân tích mã nguồn Java và cấu trúc cú pháp để tìm các vấn đề về quy tắc lập trình, thiết kế và khả năng bảo trì. SpotBugs phân tích bytecode đã biên dịch để tìm những mẫu lỗi có thể xảy ra trong luồng điều khiển, dữ liệu, xử lý null, tài nguyên, đồng bộ và các API Java. Chạy cả hai giúp nhìn mã từ hai góc độ khác nhau.

## 1. Phân tích tĩnh khác gì với biên dịch và kiểm thử?

Các bước trong quy trình chất lượng phần mềm giải quyết những câu hỏi khác nhau:

| Hoạt động | Đầu vào | Mục tiêu |
|---|---|---|
| Biên dịch | Mã nguồn | Kiểm tra cú pháp, kiểu dữ liệu và tạo bytecode |
| Kiểm thử | Chương trình đang chạy | Kiểm tra hành vi trong những tình huống cụ thể |
| Phân tích tĩnh | Mã nguồn hoặc bytecode | Phát hiện mẫu code đáng ngờ mà không cần thực thi luồng nghiệp vụ đầy đủ |
| Review thủ công | Mã nguồn, thiết kế và ngữ cảnh | Đánh giá tính đúng đắn, khả năng hiểu, kiến trúc và yêu cầu sản phẩm |

Ví dụ, compiler có thể chấp nhận một đoạn code tạo `InputStream` nhưng không đóng stream ở mọi đường thực thi. Unit test có thể không đi qua nhánh gây rò rỉ tài nguyên. Công cụ phân tích tĩnh có thể nhận diện mẫu sử dụng tài nguyên đáng ngờ và báo vị trí cần xem xét.

Kết quả phân tích tĩnh là cảnh báo dựa trên quy tắc hoặc heuristic. Một cảnh báo không tự động chứng minh ứng dụng có lỗi; người phát triển cần đọc ngữ cảnh, đánh giá mức độ ảnh hưởng và quyết định sửa hoặc loại trừ có giải thích.

## 2. PMD và SpotBugs làm việc ở lớp nào?

### PMD: phân tích mã nguồn

PMD đọc mã nguồn, phân tích cấu trúc cú pháp và áp dụng các rule. Các rule có thể tìm những vấn đề như:

- Biến hoặc trường không cần thiết, code không được sử dụng.
- Khối `catch` rỗng hoặc xử lý exception thiếu ý nghĩa.
- Câu lệnh điều kiện phức tạp, code lặp hoặc cấu trúc khó hiểu.
- Cách dùng API dễ dẫn tới lỗi hoặc hiệu năng không tốt.
- Quy ước đặt tên, tổ chức lớp và các quy tắc thiết kế.

PMD còn có CPD (Copy/Paste Detector) để tìm những đoạn mã trùng lặp. CPD là công cụ liên quan nhưng có nhiệm vụ khác với các rule PMD thông thường.

### SpotBugs: phân tích bytecode

SpotBugs đọc các lớp `.class` hoặc JAR đã biên dịch. Nó tìm những bug pattern dựa trên phân tích bytecode, luồng dữ liệu và các heuristic. Ví dụ:

- Có đường đi có thể dereference một tham chiếu null.
- Đối tượng mutable hoặc trường static được chia sẻ theo cách đáng ngờ.
- Tài nguyên hoặc stream có thể không được giải phóng.
- So sánh chuỗi hoặc đối tượng bằng toán tử không phù hợp.
- Các mẫu exception, serialization, concurrency hoặc API dễ gây lỗi.

SpotBugs cần bytecode đã biên dịch để phân tích. Nó cũng có thể cần auxiliary classpath chứa những dependency mà lớp đang phân tích tham chiếu nhưng không phải là đối tượng cần kiểm tra.

### So sánh nhanh

| Tiêu chí | PMD | SpotBugs |
|---|---|---|
| Đầu vào chính | Mã nguồn `.java` | Bytecode `.class`, thư mục lớp hoặc JAR |
| Cách phân tích | Cấu trúc cú pháp và rule trên source | Bug pattern trên bytecode, phân tích luồng dữ liệu và điều khiển |
| Trọng tâm | Chất lượng code, maintainability, một số lỗi lập trình | Những bug pattern có khả năng gây lỗi khi chạy |
| Cần biên dịch trước? | Không bắt buộc để chạy rule cơ bản; auxiliary classpath có thể tăng khả năng phân tích kiểu | Có, cần bytecode đã được biên dịch |
| Cấu hình | Ruleset XML, source selection, language version | Effort, report level, include/exclude filter, auxiliary classpath |
| Đầu ra | Text, XML, HTML và các định dạng khác tùy phiên bản | XML, HTML, text, SARIF và các định dạng được phiên bản hỗ trợ |

Không nên dùng một công cụ để thay thế hoàn toàn công cụ kia. Cả hai đều có thể phát hiện một số vấn đề tương tự, nhưng cách nhìn và tập quy tắc khác nhau.

## 3. Chuẩn bị công cụ và cấu trúc dự án

Ví dụ dưới đây giả định dự án Ant có cấu trúc:

```text
inventory-app/
├── build.xml
├── config/
│   └── pmd-ruleset.xml
├── src/
│   └── main/java/
├── lib/
│   └── third-party.jar
├── tools/
│   ├── pmd/
│   │   └── lib/
│   └── spotbugs/
│       └── lib/
│           └── spotbugs-ant.jar
└── build/
    ├── classes/
    └── reports/
```

PMD và SpotBugs có thể được cài bên ngoài repository, sau đó `build.xml` tham chiếu tới thư mục cài đặt qua property hoặc biến môi trường. Nếu tổ chức lưu công cụ trong thư mục `tools`, hãy ghi rõ phiên bản và nguồn tải để mọi máy dùng cùng một bộ công cụ.

Trước khi cấu hình Ant:

1. Chọn phiên bản PMD và SpotBugs tương thích với JDK của môi trường build.
2. Tải binary distribution từ nguồn phát hành chính thức.
3. Xác định thư mục chứa thư viện của từng công cụ.
4. Với PMD 7, bảo đảm module `pmd-ant` có trong classpath dùng để đăng ký Ant task; từ PMD 7, phần Ant task được tách thành module riêng.
5. Với SpotBugs, dùng `spotbugs-ant.jar` đi cùng đúng phiên bản SpotBugs đang cài.

Không nên ghép Ant task JAR của một phiên bản với thư viện lõi của phiên bản khác. Đặc biệt, tài liệu SpotBugs khuyến nghị dùng Ant task JAR cùng bản phát hành SpotBugs đi kèm.

## 4. Đăng ký Ant task cho PMD

Ant cần biết tên task `pmd` ánh xạ tới lớp Java nào và cần thư viện nào để tải lớp đó. Việc này được khai báo bằng `<taskdef>`.

```xml
<property name="pmd.home" location="tools/pmd"/>

<path id="pmd.classpath">
    <fileset dir="${pmd.home}/lib">
        <include name="*.jar"/>
    </fileset>
</path>

<taskdef name="pmd"
         classname="net.sourceforge.pmd.ant.PMDTask"
         classpathref="pmd.classpath"/>
```

`pmd.home` trỏ tới thư mục đã giải nén PMD. Path `pmd.classpath` lấy các JAR trong thư mục `lib` của bản phân phối. Với PMD 7, hãy bảo đảm classpath đó bao gồm module `pmd-ant` và các dependency cần thiết.

Có thể đăng ký task bằng cách chỉ định trực tiếp nested `<classpath>` trong `<taskdef>`, nhưng tạo một Path riêng sẽ thuận tiện hơn khi cần tái sử dụng hoặc chẩn đoán classpath.

## 5. Tạo ruleset cho PMD

PMD dùng ruleset XML để xác định những rule nào cần chạy. Nên lưu ruleset của dự án trong repository để mọi developer và CI sử dụng cùng chính sách.

Ví dụ `config/pmd-ruleset.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Inventory Application Rules"
         xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0
                             https://pmd.sourceforge.io/ruleset_2_0_0.xsd">
    <description>
        Rules used by the Inventory Application build.
    </description>

    <rule ref="category/java/bestpractices.xml"/>
    <rule ref="category/java/errorprone.xml"/>
    <rule ref="category/java/performance.xml"/>
</ruleset>
```

Ví dụ này tham chiếu các nhóm rule có sẵn của PMD. Trong dự án thực tế, có thể chọn một số rule cụ thể thay vì bật toàn bộ category. Bắt đầu với tập rule phù hợp, sau đó điều chỉnh dựa trên chất lượng code, phiên bản Java và mức cảnh báo mà nhóm có thể xử lý.

PMD 7 có thay đổi về rule, cấu trúc module và một số API so với PMD 6. Khi nâng cấp major version, cần đọc migration guide và kiểm tra ruleset hiện có; không nên giả định mọi rule cũ vẫn còn hoặc giữ nguyên hành vi.

## 6. Chạy PMD trong target Ant

Sau khi đăng ký task và tạo ruleset, có thể thêm target `pmd`:

```xml
<property name="src.dir" location="src/main/java"/>
<property name="reports.dir" location="build/reports"/>

<target name="pmd">
    <mkdir dir="${reports.dir}"/>

    <pmd rulesetfiles="config/pmd-ruleset.xml"
         encoding="UTF-8"
         cacheLocation="build/pmd.cache"
         failOnError="true"
         failOnRuleViolation="false">
        <sourceLanguage name="java" version="17"/>
        <formatter type="html"
                   toFile="${reports.dir}/pmd.html"/>
        <formatter type="xml"
                   toFile="${reports.dir}/pmd.xml"/>
        <fileset dir="${src.dir}">
            <include name="**/*.java"/>
            <exclude name="**/generated/**"/>
        </fileset>
    </pmd>
</target>
```

Giải thích các thuộc tính và phần tử:

- `rulesetfiles` chỉ định một hoặc nhiều ruleset. Có thể dùng nested `<ruleset>` thay thế.
- `encoding` là charset dùng để đọc mã nguồn.
- `cacheLocation` bật incremental analysis bằng cache file; lần chạy sau có thể phân tích nhanh hơn nếu nguồn không thay đổi.
- `failOnError` quyết định build có thất bại khi chính quá trình phân tích gặp lỗi hay không.
- `failOnRuleViolation` quyết định build có thất bại khi PMD tìm thấy vi phạm rule hay không.
- `sourceLanguage` khai báo phiên bản Java phù hợp với mã nguồn của dự án.
- `formatter` xác định định dạng và đường dẫn báo cáo. Có thể khai báo nhiều formatter.
- `fileset` chọn các tệp `.java` cần phân tích.

Ví dụ trên đặt `failOnRuleViolation="false"` để giai đoạn đầu chỉ thu thập báo cáo. Khi nhóm đã thống nhất rule và xử lý baseline, có thể bật `true` để dùng PMD như quality gate.

Nếu một số rule cần phân giải kiểu dữ liệu, có thể truyền `auxclasspath` chứa thư mục class đã biên dịch và dependency của dự án:

```xml
<pmd rulesetfiles="config/pmd-ruleset.xml">
    <auxclasspath>
        <pathelement location="build/classes"/>
        <path refid="compile.classpath"/>
    </auxclasspath>
    <fileset dir="src/main/java">
        <include name="**/*.java"/>
    </fileset>
</pmd>
```

Auxiliary classpath giúp PMD phân giải một số kiểu và thực hiện các rule cần thông tin đó. Nội dung của path phải phù hợp với dependency thực tế của source đang phân tích.

## 7. Đăng ký Ant task cho SpotBugs

SpotBugs cần bytecode đã biên dịch. Sau khi cài SpotBugs, đăng ký Ant task bằng resource `tasks.properties` trong JAR `spotbugs-ant.jar`:

```xml
<property name="spotbugs.home" location="tools/spotbugs"/>

<taskdef resource="edu/umd/cs/findbugs/anttask/tasks.properties"
         classpath="${spotbugs.home}/lib/spotbugs-ant.jar"/>
```

Task được đăng ký với tên `spotbugs`. JAR Ant task phải thuộc cùng bản phát hành SpotBugs mà thư mục `spotbugs.home` trỏ tới. Không nên lấy riêng một `spotbugs-ant.jar` từ phiên bản khác.

Nếu task không được tìm thấy, kiểm tra file `spotbugs-ant.jar`, đường dẫn classpath và phiên bản SpotBugs trước khi kiểm tra cấu hình target.

## 8. Chạy SpotBugs trên bytecode

Ví dụ target SpotBugs phân tích thư mục lớp `build/classes`:

```xml
<target name="spotbugs" depends="compile">
    <mkdir dir="${reports.dir}"/>

    <spotbugs home="${spotbugs.home}"
              output="html"
              outputFile="${reports.dir}/spotbugs.html"
              effort="default"
              reportLevel="medium"
              failOnError="true">
        <class location="build/classes"/>
        <auxClasspath>
            <path refid="compile.classpath"/>
        </auxClasspath>
        <sourcePath path="src/main/java"/>
    </spotbugs>
</target>
```

Các phần quan trọng:

- `home` là thư mục cài đặt SpotBugs.
- `output` chọn định dạng báo cáo; ví dụ `html`.
- `outputFile` là đường dẫn báo cáo.
- `effort` điều chỉnh mức độ phân tích, thường là `min`, `default` hoặc `max` tùy phiên bản.
- `reportLevel` đặt ngưỡng độ tin cậy/ưu tiên của bug được báo cáo.
- `<class location="..."/>` chỉ định thư mục lớp, JAR, ZIP hoặc class file cần phân tích.
- `<auxClasspath>` chứa dependency mà bytecode tham chiếu nhưng không phải đối tượng phân tích chính.
- `<sourcePath>` trỏ tới mã nguồn tương ứng để báo cáo có thể hiển thị thông tin file và dòng tốt hơn.

Target `spotbugs` phụ thuộc `compile`, do đó bytecode được tạo trước khi SpotBugs chạy. Nếu dự án có nhiều output directory hoặc nhiều module, cần khai báo các class location tương ứng.

## 9. Auxiliary classpath và source path của SpotBugs

Hai phần tử này thường bị nhầm lẫn:

| Cấu hình | Dùng để làm gì? |
|---|---|
| `<class location="..."/>` | Chỉ định bytecode cần phân tích |
| `<auxClasspath>` | Cung cấp các lớp/JAR mà bytecode cần tham chiếu nhưng không phải mục tiêu phân tích |
| `<sourcePath>` | Cung cấp mã nguồn tương ứng để báo cáo có thông tin vị trí source tốt hơn |

Ví dụ, ứng dụng có `build/classes` và phụ thuộc `lib/database-driver.jar`:

```xml
<spotbugs home="${spotbugs.home}" output="xml"
          outputFile="${reports.dir}/spotbugs.xml">
    <class location="build/classes"/>
    <auxClasspath>
        <pathelement location="lib/database-driver.jar"/>
    </auxClasspath>
    <sourcePath path="src/main/java"/>
</spotbugs>
```

Nếu auxiliary classpath thiếu dependency, SpotBugs có thể báo missing classes hoặc giảm độ chính xác của một số phân tích. Không nên tắt thông báo lỗi chỉ để làm báo cáo sạch; hãy bổ sung đúng dependency hoặc xác định rõ những lớp nào không thể được phân giải.

## 10. Kết hợp PMD và SpotBugs trong cùng buildfile

Một buildfile có thể khai báo cả hai công cụ và chạy chúng bằng một target chung:

```xml
<project name="static-analysis-demo" default="analyze" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="reports.dir" location="build/reports"/>
    <property name="pmd.home" location="tools/pmd"/>
    <property name="spotbugs.home" location="tools/spotbugs"/>

    <path id="compile.classpath">
        <fileset dir="lib" includes="*.jar"/>
    </path>

    <path id="pmd.classpath">
        <fileset dir="${pmd.home}/lib" includes="*.jar"/>
    </path>
    <taskdef name="pmd"
             classname="net.sourceforge.pmd.ant.PMDTask"
             classpathref="pmd.classpath"/>

    <taskdef resource="edu/umd/cs/findbugs/anttask/tasks.properties"
             classpath="${spotbugs.home}/lib/spotbugs-ant.jar"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="pmd" depends="compile">
        <mkdir dir="${reports.dir}"/>
        <pmd rulesetfiles="config/pmd-ruleset.xml"
             encoding="UTF-8"
             cacheLocation="build/pmd.cache"
             failOnError="true"
             failOnRuleViolation="false">
            <sourceLanguage name="java" version="17"/>
            <formatter type="html" toFile="${reports.dir}/pmd.html"/>
            <fileset dir="${src.dir}">
                <include name="**/*.java"/>
                <exclude name="**/generated/**"/>
            </fileset>
        </pmd>
    </target>

    <target name="spotbugs" depends="compile">
        <mkdir dir="${reports.dir}"/>
        <spotbugs home="${spotbugs.home}"
                  output="html"
                  outputFile="${reports.dir}/spotbugs.html"
                  effort="default"
                  reportLevel="medium"
                  failOnError="true">
            <class location="${classes.dir}"/>
            <auxClasspath>
                <path refid="compile.classpath"/>
            </auxClasspath>
            <sourcePath path="${src.dir}"/>
        </spotbugs>
    </target>

    <target name="analyze" depends="pmd,spotbugs">
        <echo message="Static analysis reports are in ${reports.dir}"/>
    </target>

</project>
```

Chạy cả hai công cụ:

```sh
ant analyze
```

Hoặc chạy riêng:

```sh
ant pmd
ant spotbugs
```

Target `analyze` phụ thuộc cả `pmd` và `spotbugs`. Hai target phân tích đều phụ thuộc `compile`, nên Ant thực hiện compile trước. Báo cáo HTML được lưu trong `build/reports`.

Đây là ví dụ cấu trúc. Đường dẫn `tools/pmd`, `tools/spotbugs`, source level, dependency và cấu hình classpath cần được thay bằng vị trí và phiên bản thực tế của dự án.

## 11. Báo cáo và cách đọc kết quả

PMD và SpotBugs có thể tạo báo cáo ở nhiều định dạng. HTML phù hợp cho người đọc trực tiếp; XML phù hợp để xử lý tự động, lưu trữ hoặc chuyển đổi; SARIF có thể tích hợp với các hệ thống hỗ trợ chuẩn trao đổi kết quả phân tích.

| Định dạng | Trường hợp sử dụng |
|---|---|
| HTML | Xem trong trình duyệt, đọc mô tả và vị trí cảnh báo |
| XML | Lưu kết quả có cấu trúc, xử lý bằng script hoặc công cụ báo cáo |
| Text | Xem nhanh trong terminal hoặc log CI |
| SARIF | Trao đổi kết quả static analysis với nền tảng hỗ trợ SARIF; cần kiểm tra phiên bản công cụ có hỗ trợ định dạng này |

Khi đọc một finding, hãy xem:

1. Tên rule hoặc bug pattern.
2. File, class, method và dòng được báo cáo.
3. Mức độ ưu tiên hoặc độ tin cậy.
4. Mô tả vì sao công cụ nghi ngờ có vấn đề.
5. Đường đi dữ liệu hoặc điều kiện dẫn tới cảnh báo, nếu báo cáo cung cấp.
6. Khả năng tái hiện và tác động thực tế trong ứng dụng.

Không nên chỉ nhìn số lượng cảnh báo. Một finding có độ tin cậy cao và ảnh hưởng tới dữ liệu hoặc tài nguyên quan trọng có thể đáng xử lý trước hàng chục cảnh báo style nhỏ.

## 12. Dùng kết quả phân tích làm quality gate

Một quality gate là điều kiện để build được phép tiếp tục. Có thể bắt đầu bằng chế độ chỉ tạo báo cáo, sau đó nâng dần mức chặn khi nhóm đã hiểu các rule và xử lý baseline hiện tại.

### PMD: chặn build khi có rule violation

Trong task PMD, có thể bật:

```xml
<pmd rulesetfiles="config/pmd-ruleset.xml"
     failOnError="true"
     failOnRuleViolation="true">
    <formatter type="xml" toFile="build/reports/pmd.xml"/>
    <fileset dir="src/main/java">
        <include name="**/*.java"/>
    </fileset>
</pmd>
```

`failOnError` kiểm soát lỗi khi chạy phân tích; `failOnRuleViolation` kiểm soát việc thất bại khi có vi phạm rule. Hai thuộc tính giải quyết hai loại tình huống khác nhau.

PMD cũng có thể giới hạn số vi phạm cho phép bằng thuộc tính `maxRuleViolations` trong các phiên bản hỗ trợ. Hãy kiểm tra tài liệu của phiên bản đang dùng nếu chọn chính sách theo số lượng.

### SpotBugs: chặn build khi có cảnh báo

SpotBugs Ant task có thể ghi property khi phát hiện warning. Ví dụ:

```xml
<spotbugs home="${spotbugs.home}"
          output="xml"
          outputFile="build/reports/spotbugs.xml"
          effort="max"
          reportLevel="medium"
          failOnError="true"
          warningsProperty="spotbugs.warnings">
    <class location="build/classes"/>
    <auxClasspath>
        <path refid="compile.classpath"/>
    </auxClasspath>
</spotbugs>

<fail if="spotbugs.warnings"
      message="SpotBugs found warnings; inspect build/reports/spotbugs.xml"/>
```

`failOnError` làm build thất bại khi chính công cụ gặp lỗi thực thi; `warningsProperty` cho biết đã tìm thấy cảnh báo. Task `<fail>` biến property đó thành quality gate. Nếu muốn chỉ chặn một nhóm bug nhất định, hãy cấu hình filter phù hợp thay vì chặn mọi cảnh báo ngay từ đầu.

### Không nên bật gate quá nghiêm ngặt ngay ngày đầu

Với codebase cũ, một ruleset rộng có thể tạo nhiều finding. Nếu bật chặn tất cả ngay lập tức, nhóm có thể phải xử lý một lượng cảnh báo lớn trước khi build hoạt động bình thường.

Một lộ trình thực tế:

1. Chạy report-only để hiểu số lượng và loại finding.
2. Xác định cảnh báo thật, false positive và các ngoại lệ hợp lệ.
3. Sửa lỗi có rủi ro cao trước.
4. Lưu baseline hoặc filter cho những finding cũ cần xử lý dần.
5. Chặn build với finding mới hoặc finding nghiêm trọng.
6. Mở rộng ruleset và quality gate theo từng giai đoạn.

Mục tiêu là ngăn vấn đề mới đi vào codebase mà không làm mất khả năng build và phát triển của nhóm.

## 13. Suppress warning có kiểm soát

Đôi khi một finding không thể sửa ngay hoặc là false positive do ngữ cảnh mà công cụ không hiểu. Có thể suppress, nhưng cần ghi rõ lý do và giới hạn phạm vi.

### PMD suppression

PMD hỗ trợ marker `NOPMD` mặc định:

```java
String raw = readLegacyValue(); // NOPMD - giữ tương thích với định dạng dữ liệu cũ
```

Có thể cấu hình marker khác trong task PMD bằng thuộc tính `suppressMarker`. Không nên thêm `NOPMD` cho cả file hoặc cả class nếu chỉ một dòng cần ngoại lệ.

### SpotBugs suppression

SpotBugs hỗ trợ annotation `@SuppressFBWarnings` từ artifact annotations tương ứng:

```java
import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

public class LegacyAdapter {

    @SuppressFBWarnings(
        value = "EI_EXPOSE_REP",
        justification = "API này giữ hành vi tương thích với client cũ."
    )
    public byte[] rawData() {
        return data;
    }
}
```

Tên bug pattern trong `value` cần khớp với mã finding của SpotBugs. Annotation chỉ nên được dùng sau khi đã đọc finding và xác định vì sao trường hợp cụ thể được chấp nhận.

SpotBugs cũng hỗ trợ include/exclude filter XML để điều khiển những bug được báo cáo. Ví dụ filter loại trừ lớp sinh tự động:

```xml
<FindBugsFilter>
    <Match>
        <Class name="com.example.generated.*"/>
    </Match>
</FindBugsFilter>
```

Sau đó tham chiếu tệp filter bằng thuộc tính `excludeFilter` của task SpotBugs. Không nên loại trừ package rộng chỉ để giảm số cảnh báo; điều đó có thể che khuất lỗi thực sự.

## 14. PMD và SpotBugs trong CI

Khi tích hợp vào CI, nên chạy phân tích trên cùng JDK và phiên bản công cụ như môi trường phát triển. Các tệp ruleset, filter, cấu hình Ant và phiên bản tool nên được quản lý trong repository hoặc được pin trong cấu hình build.

Một pipeline đơn giản có thể chạy:

```sh
ant clean compile
ant analyze
```

CI nên lưu các báo cáo ngay cả khi quality gate thất bại để nhóm có thể xem nguyên nhân. Có thể cấu hình artifact retention cho:

```text
build/reports/pmd.html
build/reports/pmd.xml
build/reports/spotbugs.html
build/reports/spotbugs.xml
```

Một số lưu ý khi chạy trong CI:

- Dùng phiên bản PMD/SpotBugs cố định, không tải `latest` không kiểm soát.
- Đảm bảo `compile` hoàn tất trước khi chạy SpotBugs.
- Cung cấp auxiliary classpath đầy đủ để giảm missing class và tăng độ chính xác.
- Giữ report khi build thất bại để có dữ liệu điều tra.
- Phân biệt lỗi cấu hình hoặc lỗi chạy công cụ với finding trong mã nguồn.
- Tránh để report hoặc cache được tạo trong thư mục source và vô tình đưa vào commit.
- Nếu có baseline, cập nhật baseline có review; không tự động thêm mọi finding mới vào danh sách bỏ qua.

## 15. Hiệu năng và incremental analysis

PMD có thể dùng cache qua `cacheLocation` để tránh phân tích lại những tệp không thay đổi. Đây là cách giảm thời gian chạy trên dự án lớn. Khi source, ruleset hoặc phiên bản PMD thay đổi, cần hiểu cách phiên bản PMD xử lý cache và xóa cache khi cần điều tra kết quả không nhất quán.

SpotBugs có thể tốn nhiều thời gian và bộ nhớ hơn khi phân tích chương trình lớn. Thuộc tính `effort` ảnh hưởng độ sâu và chi phí phân tích:

| Effort | Ý nghĩa khái quát |
|---|---|
| `min` | Giảm chi phí và một số phân tích chuyên sâu |
| `default` | Mức cân bằng thường dùng |
| `max` | Chạy thêm phân tích có thể tốn thời gian và bộ nhớ hơn |

Nếu SpotBugs chạy chậm hoặc thiếu bộ nhớ, hãy xem xét tăng heap cho tiến trình công cụ bằng cấu hình JVM phù hợp, giảm phạm vi bytecode cần phân tích hoặc điều chỉnh effort. Không nên hạ effort chỉ để làm biến mất finding mà chưa hiểu tác động tới độ bao phủ.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy task `pmd` | Chưa đăng ký `PMDTask` hoặc thiếu JAR trong classpath | Kiểm tra `taskdef`, `pmd.classpath` và module `pmd-ant` khi dùng PMD 7 |
| PMD báo lỗi ruleset hoặc không tìm thấy rule | Ruleset dùng tên rule/category không có trong phiên bản PMD đang cài | Kiểm tra đường dẫn ruleset, migration guide và rule reference của đúng phiên bản |
| PMD báo lỗi phân tích cú pháp Java | `sourceLanguage` không khớp phiên bản mã nguồn hoặc PMD chưa hỗ trợ cú pháp đó | Khai báo đúng Java version và dùng bản PMD hỗ trợ ngôn ngữ nguồn |
| PMD báo thiếu type hoặc rule phân tích không sâu | Auxiliary classpath chưa có output và compile dependency | Bổ sung thư mục lớp và dependency cần thiết vào `auxclasspath` |
| SpotBugs không có lớp để phân tích | Target compile chưa chạy hoặc `class location` sai | Đặt `depends="compile"` và kiểm tra thư mục/JAR đầu vào |
| SpotBugs báo missing classes | Auxiliary classpath thiếu dependency | Thêm JAR/thư mục chứa các lớp được tham chiếu vào `<auxClasspath>` |
| SpotBugs không hiển thị vị trí source rõ ràng | Chưa cấu hình `sourcePath` hoặc source không khớp bytecode | Trỏ `sourcePath` tới đúng thư mục mã nguồn đã biên dịch |
| Ant task SpotBugs không tải được | `spotbugs-ant.jar` không có trong classpath hoặc không cùng phiên bản | Dùng task JAR từ đúng bản SpotBugs và kiểm tra `taskdef resource` |
| Báo cáo HTML không được tạo | Thư mục báo cáo chưa tồn tại hoặc đường dẫn sai | Tạo thư mục bằng `<mkdir>` và kiểm tra `outputFile`/formatter |
| Build thất bại dù chỉ muốn tạo report | Quality gate đang bật hoặc công cụ gặp lỗi thực thi | Phân biệt `failOnRuleViolation` của PMD với `failOnError` của PMD/SpotBugs và cấu hình theo mục tiêu |
| Có quá nhiều finding | Ruleset rộng, baseline cũ hoặc phạm vi source quá lớn | Chọn rule phù hợp, phân loại finding và xử lý baseline có kiểm soát |
| SpotBugs chạy quá lâu hoặc hết bộ nhớ | Phân tích nhiều bytecode hoặc effort cao | Kiểm tra phạm vi, heap, auxiliary classpath và mức effort |

## 17. Checklist triển khai PMD và SpotBugs

- [ ] Đã chọn phiên bản PMD và SpotBugs tương thích với JDK và Ant.
- [ ] PMD Ant task và module `pmd-ant` đã có trong classpath của `taskdef`.
- [ ] SpotBugs Ant task dùng `spotbugs-ant.jar` cùng bản phân phối SpotBugs.
- [ ] Ruleset PMD được lưu trong repository và chọn rule phù hợp.
- [ ] `sourceLanguage` khớp phiên bản Java của mã nguồn.
- [ ] PMD có source fileset và auxiliary classpath khi rule cần phân giải kiểu.
- [ ] SpotBugs chạy sau compile và phân tích đúng class directory hoặc JAR.
- [ ] Auxiliary classpath và source path của SpotBugs được khai báo phù hợp.
- [ ] Báo cáo HTML/XML được lưu vào thư mục build riêng.
- [ ] Lỗi chạy công cụ được phân biệt với vi phạm rule/bug pattern.
- [ ] Suppression có phạm vi hẹp và giải thích lý do.
- [ ] Quality gate được triển khai theo baseline và mức độ rủi ro của dự án.
- [ ] CI lưu báo cáo khi phân tích thất bại và dùng phiên bản công cụ cố định.

PMD và SpotBugs giúp đưa kiểm tra chất lượng vào quy trình Ant một cách tự động. PMD tập trung vào mã nguồn và quy tắc lập trình; SpotBugs phân tích bytecode để tìm bug pattern. Khi cấu hình đúng đầu vào, classpath, ruleset, report và quality gate, nhóm có thể phát hiện vấn đề sớm và theo dõi chất lượng code qua từng lần build.

## Tài liệu tham khảo

- [PMD — Ant Task Usage](https://docs.pmd-code.org/pmd-doc-7.28.0/pmd_userdocs_tools_ant.html)
- [PMD — Installation and CLI Usage](https://docs.pmd-code.org/latest/pmd_userdocs_installation.html)
- [SpotBugs — Using the Ant Task](https://spotbugs.readthedocs.io/en/latest/ant.html)
- [SpotBugs — Command-line Options and Reports](https://spotbugs.readthedocs.io/en/latest/running.html)

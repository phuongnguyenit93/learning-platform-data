# Cấu hình classpath, classloaderref và xử lý thiếu thư viện mở rộng

Apache Ant có thể nạp task và data type do thư viện bên ngoài cung cấp. Ví dụ, một dự án có thể dùng task riêng để triển khai ứng dụng, tạo báo cáo, kiểm tra chất lượng hoặc kết nối một hệ thống nội bộ. Để Ant sử dụng được các lớp mở rộng này, buildfile phải cung cấp đúng JAR và các dependency của chúng, sau đó đăng ký lớp bằng `taskdef` hoặc `typedef`.

Việc nạp lớp mở rộng liên quan đến hai cấu hình thường bị nhầm lẫn: `classpathref` xác định các thư viện mà Ant cần tìm khi nạp lớp; `loaderref` định danh classloader để nhiều định nghĩa có thể dùng chung một classloader. Ngoài ra, buildfile cần quyết định cách xử lý khi thư viện không tồn tại hoặc không thể nạp: dừng build, bỏ qua một tính năng tùy chọn hay ghi cảnh báo.

## 1. Task mở rộng và data type mở rộng

Ant phân biệt task và data type. Task thực hiện một hành động trong target, còn data type biểu diễn một cấu hình hoặc tập dữ liệu mà task có thể sử dụng.

| Cơ chế | Dùng để đăng ký | Ví dụ |
|---|---|---|
| `taskdef` | Một task Java mới | `<deploy-app />`, `<generate-report />` |
| `typedef` | Một data type mới | Một kiểu cấu hình hoặc ResourceCollection tùy chỉnh |

Ví dụ, một lớp Java triển khai task có thể được đăng ký như sau:

```xml
<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpath="lib/company-ant-tasks.jar" />

<target name="demo">
    <hello />
</target>
```

`name` là tên task sẽ được dùng trong buildfile; `classname` là tên đầy đủ của lớp Java triển khai task; `classpath` cho Ant biết nơi tìm lớp đó. Sau khi đăng ký thành công, Ant có thể phân giải phần tử `<hello>` thành task tương ứng.

Nếu thư viện cung cấp data type thay vì task, dùng `typedef`:

```xml
<typedef
    name="company-resources"
    classname="com.example.ant.CompanyResources"
    classpath="lib/company-ant-types.jar" />
```

Task hoặc data type chỉ có thể được sử dụng sau khi định nghĩa đã được nạp. Vì vậy, target đăng ký extension phải chạy trước target chứa lời gọi task hoặc data type đó.

## 2. Classpath của extension là gì?

Classpath của extension là tập đường dẫn tới JAR hoặc thư mục chứa các lớp mà Ant cần nạp để khởi tạo task/data type. Nó có thể chứa:

- JAR chính chứa lớp task hoặc data type.
- JAR phụ thuộc mà lớp mở rộng tham chiếu khi chạy.
- Thư mục chứa các lớp đã biên dịch, nếu extension được tổ chức dưới dạng thư mục class output.

Ví dụ thư viện có cấu trúc:

```text
project/
├── build.xml
└── lib/
    └── ant-extensions/
        ├── company-ant-tasks.jar
        ├── company-api.jar
        └── json-support.jar
```

Nếu `HelloTask` trong `company-ant-tasks.jar` sử dụng lớp từ hai JAR còn lại, cả ba phải có mặt trong classpath dùng để nạp task.

```xml
<path id="company.extension.classpath">
    <pathelement location="lib/ant-extensions/company-ant-tasks.jar" />
    <pathelement location="lib/ant-extensions/company-api.jar" />
    <pathelement location="lib/ant-extensions/json-support.jar" />
</path>

<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpathref="company.extension.classpath" />
```

`path` tạo một đối tượng Path có `id`; `classpathref` tham chiếu tới Path đó. Cách này thuận tiện khi nhiều task mở rộng cùng dùng một tập thư viện.

## 3. Phân biệt classpath và classpathref

`classpath` nhận trực tiếp một path-like value, còn `classpathref` tham chiếu tới một Path đã được khai báo bằng `id`.

Khai báo trực tiếp:

```xml
<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpath="lib/company-ant-tasks.jar;lib/company-api.jar" />
```

Khai báo bằng Path và `classpathref`:

```xml
<path id="extension.classpath">
    <pathelement location="lib/company-ant-tasks.jar" />
    <pathelement location="lib/company-api.jar" />
</path>

<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpathref="extension.classpath" />
```

Trên các hệ điều hành khác nhau, ký tự phân cách trong thuộc tính path dạng chuỗi có thể khác nhau. Dùng nested `<path>` với `pathelement` thường rõ ràng và dễ di chuyển hơn.

Một cách viết khác là khai báo nested `<classpath>` ngay trong `taskdef`:

```xml
<taskdef name="hello" classname="com.example.ant.HelloTask">
    <classpath>
        <pathelement location="lib/company-ant-tasks.jar" />
        <pathelement location="lib/company-api.jar" />
    </classpath>
</taskdef>
```

`classpathref` không phải tên classloader; nó chỉ chỉ tới Path. Việc classloader nào được dùng để nạp các lớp được kiểm soát riêng bằng `loaderref`.

## 4. Tái sử dụng Path cho nhiều extension

Khi nhiều task đến từ cùng một thư viện, hãy định nghĩa classpath một lần rồi dùng lại:

```xml
<path id="company.extension.classpath">
    <pathelement location="lib/company-ant-tasks.jar" />
    <pathelement location="lib/company-api.jar" />
    <pathelement location="lib/json-support.jar" />
</path>

<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpathref="company.extension.classpath" />

<taskdef
    name="publish-report"
    classname="com.example.ant.PublishReportTask"
    classpathref="company.extension.classpath" />

<typedef
    name="company-resources"
    classname="com.example.ant.CompanyResources"
    classpathref="company.extension.classpath" />
```

Nhờ dùng chung Path, danh sách JAR được quản lý tại một vị trí. Khi extension thêm một dependency, có thể cập nhật Path thay vì sửa nhiều định nghĩa task.

Với dự án có nhiều phiên bản thư viện, nên khai báo các JAR theo phiên bản cụ thể. Dùng một `fileset` quá rộng như `lib/**/*.jar` có thể vô tình nạp hai phiên bản của cùng một dependency, dẫn tới xung đột class hoặc hành vi khó dự đoán.

## 5. Classloader và loaderref

Classpath mô tả nơi tìm bytecode; classloader là thành phần Java chịu trách nhiệm nạp định nghĩa lớp từ những vị trí đó. Ant dùng classloader để nạp task và data type mở rộng vào môi trường build.

Thuộc tính `loaderref` của `taskdef`/`typedef` cho phép đặt một định danh tham chiếu cho classloader. Khi nhiều định nghĩa dùng cùng `loaderref`, Ant có thể tái sử dụng cùng classloader thay vì tạo một classloader độc lập cho từng định nghĩa.

Ví dụ:

```xml
<path id="company.extension.classpath">
    <pathelement location="lib/company-ant-tasks.jar" />
    <pathelement location="lib/company-api.jar" />
</path>

<taskdef
    name="hello"
    classname="com.example.ant.HelloTask"
    classpathref="company.extension.classpath"
    loaderref="company.extension.loader" />

<taskdef
    name="publish-report"
    classname="com.example.ant.PublishReportTask"
    classpathref="company.extension.classpath"
    loaderref="company.extension.loader" />
```

Hai task dùng cùng định danh `company.extension.loader`, do đó có thể chia sẻ classloader và cùng nhìn thấy các lớp extension được nạp qua loader đó. Điều này hữu ích khi các task trao đổi đối tượng thuộc thư viện extension hoặc cùng dựa vào một singleton/static registry trong thư viện.

`loaderref` là một reference ID, không phải đường dẫn JAR. Nó cũng không thay thế `classpathref`: classpath xác định các vị trí chứa lớp, còn loaderref xác định việc tái sử dụng loader.

Khi dùng chung loaderref, hãy cung cấp đầy đủ classpath ngay từ định nghĩa đầu tiên tạo loader. Không nên giả định một định nghĩa sau có thể bổ sung an toàn các JAR còn thiếu vào classloader đã được tạo trước đó. Tất cả task dùng chung loader nên có bộ dependency tương thích.

## 6. Khi nào nên dùng chung loaderref?

Chia sẻ classloader có ích khi các định nghĩa extension cần dùng chung cùng một tập lớp:

- Nhiều task được cung cấp bởi một thư viện và chia sẻ API nội bộ.
- Task và data type trao đổi instance của cùng một lớp extension.
- Nhiều định nghĩa cần dùng chung một registry hoặc trạng thái static trong extension.
- Muốn tránh việc cùng một lớp bị nạp riêng trong nhiều classloader độc lập.

Không nên dùng chung loaderref giữa các extension có dependency xung đột hoặc yêu cầu phiên bản thư viện khác nhau. Trong Java, hai lớp có cùng tên đầy đủ nhưng được nạp bởi hai classloader khác nhau vẫn được xem là hai kiểu khác nhau. Điều này có thể gây lỗi `ClassCastException` khi đối tượng từ loader này được truyền sang code mong đợi lớp từ loader kia.

Ví dụ về lựa chọn:

| Tình huống | Cách cấu hình |
|---|---|
| Hai task cùng bộ JAR và cần chia sẻ class | Cùng `classpathref` và cùng `loaderref` |
| Hai extension có phiên bản dependency khác nhau | Dùng classpath và loaderref riêng |
| Một task độc lập, không cần chia sẻ lớp với task khác | Có thể bỏ `loaderref` |
| Task và typedef cần trao đổi cùng kiểu dữ liệu | Dùng chung loaderref và cùng bộ dependency |

Classloader dùng chung cũng có nghĩa trạng thái static của các lớp trong loader đó có thể được chia sẻ giữa các task. Nếu extension lưu cache hoặc cấu hình mutable ở static field, các lần gọi task có thể tác động lẫn nhau. Hãy hiểu hành vi này trước khi quyết định chia sẻ loader.

## 7. Đăng ký nhiều task qua Antlib

Nếu thư viện cung cấp nhiều task và data type, có thể đóng gói các định nghĩa vào Antlib thay vì khai báo từng `taskdef` trong mọi buildfile.

Ví dụ cấu trúc JAR:

```text
company-ant-tasks.jar
└── com/
    └── example/
        └── ant/
            ├── HelloTask.class
            ├── PublishReportTask.class
            └── antlib.xml
```

Nội dung `com/example/ant/antlib.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef name="hello" classname="com.example.ant.HelloTask" />
    <taskdef name="publish-report" classname="com.example.ant.PublishReportTask" />
</antlib>
```

Buildfile có thể nạp Antlib theo URI `antlib:`:

```xml
<project name="antlib-example"
         default="demo"
         xmlns:company="antlib:com.example.ant">

    <path id="company.extension.classpath">
        <pathelement location="lib/company-ant-tasks.jar" />
        <pathelement location="lib/company-api.jar" />
    </path>

    <taskdef
        uri="antlib:com.example.ant"
        resource="com/example/ant/antlib.xml"
        classpathref="company.extension.classpath"
        loaderref="company.extension.loader" />

    <target name="demo">
        <company:hello />
        <company:publish-report />
    </target>
</project>
```

Ở đây:

- `uri` là namespace mà các task trong Antlib được đăng ký vào.
- `resource` là đường dẫn resource của descriptor trên classpath.
- `classpathref` cung cấp JAR chứa descriptor, lớp task và dependency.
- `loaderref` cho phép định danh classloader được dùng để nạp các định nghĩa.
- `xmlns:company` ánh xạ prefix `company` tới namespace URI của Antlib.

Với URI `antlib:com.example.ant`, Ant tìm resource tương ứng theo package `com/example/ant/antlib.xml`. Đây là quy ước của Antlib; nó không có nghĩa Ant tải một tài liệu từ máy chủ HTTP.

## 8. Xử lý khi thiếu thư viện bắt buộc

Nếu extension là yêu cầu bắt buộc của build, nên kiểm tra JAR tồn tại và dừng sớm với thông báo rõ ràng. Task `available` có thể thiết lập property khi tệp tồn tại; task `fail` làm build thất bại nếu property chưa được thiết lập.

```xml
<property name="extension.jar" value="lib/company-ant-tasks.jar" />

<target name="define-company-tasks">
    <available
        file="${extension.jar}"
        type="file"
        property="company.extension.present" />

    <fail
        unless="company.extension.present"
        message="Missing required Ant extension: ${extension.jar}" />

    <taskdef
        name="hello"
        classname="com.example.ant.HelloTask"
        classpath="${extension.jar}" />
</target>

<target name="run-extension" depends="define-company-tasks">
    <hello />
</target>
```

Trình tự này bảo đảm Ant kiểm tra file trước khi đăng ký task. Nếu JAR không tồn tại, `fail` dừng target và đưa ra đường dẫn cần khắc phục. Nếu JAR tồn tại nhưng thiếu dependency bắc cầu hoặc không chứa class đã khai báo, `taskdef` vẫn có thể thất bại khi nạp lớp; kiểm tra tồn tại của JAR chính không chứng minh toàn bộ dependency graph hợp lệ.

Đối với một extension quan trọng, mặc định thất bại nhanh thường là lựa chọn đúng. Build không nên tiếp tục và tạo artifact thiếu chức năng chỉ vì một thư viện bắt buộc bị thiếu.

## 9. Xử lý extension tùy chọn

Một số extension chỉ phục vụ một tính năng phụ, ví dụ tạo báo cáo nâng cao hoặc triển khai lên một môi trường không phải lúc nào cũng được dùng. Khi đó, có thể kiểm tra sự tồn tại của JAR và chỉ đăng ký/chạy task nếu extension có mặt.

```xml
<property name="optional.extension.jar" value="lib/optional-reporting.jar" />

<available
    file="${optional.extension.jar}"
    type="file"
    property="optional.extension.present" />

<target name="define-optional-reporting" if="optional.extension.present">
    <taskdef
        name="advanced-report"
        classname="com.example.reporting.AdvancedReportTask"
        classpath="${optional.extension.jar}"
        loaderref="optional.reporting.loader" />
</target>

<target name="report-advanced"
        depends="define-optional-reporting"
        if="optional.extension.present">
    <advanced-report />
</target>

<target name="report-basic" unless="optional.extension.present">
    <echo message="Optional reporting library is absent; using basic reports." />
</target>
```

Property `optional.extension.present` được thiết lập trước khi Ant thực thi các target. Nếu JAR không có, phần thân `define-optional-reporting` bị bỏ qua; target `report-advanced` cũng bị bỏ qua vì điều kiện không thỏa mãn; `report-basic` có thể chạy để thông báo hoặc tạo báo cáo thay thế.

Lưu ý: `if` và `unless` trên target chỉ điều khiển phần thân target. Các target trong `depends` vẫn được xử lý trước. Trong ví dụ, dependency `define-optional-reporting` có điều kiện riêng nên không cố nạp task khi thư viện thiếu.

## 10. Thuộc tính onerror của taskdef và typedef

`taskdef` và `typedef` có thuộc tính `onerror` để quyết định cách Ant phản ứng khi không thể nạp định nghĩa. Các lựa chọn thường dùng là:

| Giá trị | Hành vi |
|---|---|
| `fail` | Dừng build khi định nghĩa không thể nạp; đây là lựa chọn mặc định |
| `report` | Ghi nhận/báo lỗi nạp định nghĩa nhưng không dừng build ngay |
| `ignore` | Bỏ qua lỗi nạp định nghĩa mà không báo lỗi ở mức thông thường |

Ví dụ:

```xml
<taskdef
    name="optional-report"
    classname="com.example.reporting.OptionalReportTask"
    classpath="lib/optional-reporting.jar"
    onerror="report" />
```

`onerror="report"` có thể hữu ích khi extension không bắt buộc và build có nhánh thay thế. Tuy nhiên, nếu target sau đó vẫn gọi `<optional-report>`, Ant có thể báo lỗi vì task chưa được đăng ký. Do đó, `onerror` không thay thế việc kiểm tra điều kiện trước khi sử dụng task.

Không nên dùng `onerror="ignore"` cho dependency bắt buộc. Việc che giấu lỗi nạp lớp làm build thất bại muộn hơn và thông báo thường khó hiểu hơn, chẳng hạn task không được nhận diện hoặc thiếu class khi thực thi.

Đối với extension tùy chọn, kết hợp kiểm tra `available`, điều kiện target và thông báo rõ ràng thường làm ý định của buildfile dễ đọc hơn. Dùng `onerror` như lớp xử lý bổ sung khi thật sự cần.

## 11. Phân biệt thiếu JAR, thiếu class và xung đột phiên bản

Không phải mọi lỗi nạp extension đều có nghĩa là JAR chính không tồn tại. Cần phân biệt các trường hợp:

| Lỗi hoặc hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException` | Ant không tìm thấy lớp được khai báo trong `classname` hoặc dependency được nạp động | Kiểm tra class name, classpath và vị trí JAR |
| `NoClassDefFoundError` | Một lớp cần thiết khi liên kết/chạy không có trong classpath hoặc không thể khởi tạo | Bổ sung dependency bắc cầu và kiểm tra phiên bản thư viện |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Extension được biên dịch với API khác phiên bản đang được nạp | Đồng bộ phiên bản JAR và API tương thích |
| `UnsupportedClassVersionError` | Class file được biên dịch bằng JDK mới hơn runtime đang chạy Ant hỗ trợ | Chọn JDK runtime phù hợp hoặc biên dịch extension về phiên bản tương thích |
| `ClassCastException` giữa các lớp cùng tên | Hai bản lớp được nạp bởi các classloader khác nhau hoặc có phiên bản không tương thích | Kiểm tra loaderref, classpath và cách chia sẻ API |
| Task không được nhận diện | `taskdef` chưa chạy, đăng ký thất bại hoặc tên task khác với lời gọi | Bảo đảm target đăng ký chạy trước và kiểm tra thuộc tính `name` |

Khi đọc lỗi, hãy tìm lớp đầu tiên được nêu trong stack trace và xác định nó thuộc JAR nào. Việc thêm toàn bộ thư mục `lib` vào classpath có thể làm lỗi biến mất tạm thời nhưng cũng dễ che giấu xung đột phiên bản. Tốt hơn là xác định dependency cụ thể và khai báo phiên bản có kiểm soát.

## 12. Classloader, API của Ant và dependency của extension

Task mở rộng chạy bên trong tiến trình Ant nên thường phụ thuộc vào API của Ant. Khi đóng gói extension:

- Biên dịch task với API Ant tương thích với phiên bản Ant mà dự án hỗ trợ.
- Đưa các dependency riêng của extension vào classpath nạp task.
- Không đóng gói một bản `ant.jar` tùy tiện bên trong JAR extension nếu runtime Ant đã cung cấp API đó; hai bản API có thể gây xung đột classloader.
- Tránh đưa nhiều phiên bản của cùng một thư viện vào một classpath.
- Nếu các extension cần chia sẻ kiểu dữ liệu, dùng chung classloader phù hợp và cùng phiên bản API.

Classloader là một phần của định danh lớp trong JVM. Vì vậy, hai lớp có cùng tên đầy đủ nhưng được nạp bởi hai classloader khác nhau không nhất thiết tương thích khi ép kiểu hoặc truyền qua API. Đây là lý do `loaderref` hữu ích khi nhiều định nghĩa thực sự phải chia sẻ cùng lớp, nhưng cũng là lý do không nên dùng một loaderref chung cho các extension có dependency không tương thích.

Khi thay JAR extension trong lúc Ant đang chạy, classloader đã được tạo có thể tiếp tục giữ các lớp cũ trong bộ nhớ. Để bảo đảm nạp đúng phiên bản mới, hãy chạy một invocation Ant mới sau khi cập nhật JAR, thay vì kỳ vọng classloader hiện tại tự tải lại lớp.

## 13. Tổ chức classpath theo từng nhóm extension

Một dự án có thể dùng nhiều nhóm extension với dependency khác nhau. Nên tạo Path riêng cho từng nhóm:

```xml
<path id="reporting.classpath">
    <pathelement location="lib/reporting/report-task.jar" />
    <pathelement location="lib/reporting/report-api.jar" />
</path>

<path id="deployment.classpath">
    <pathelement location="lib/deployment/deploy-task.jar" />
    <pathelement location="lib/deployment/cloud-client.jar" />
</path>

<taskdef
    name="generate-report"
    classname="com.example.reporting.GenerateReportTask"
    classpathref="reporting.classpath"
    loaderref="reporting.loader" />

<taskdef
    name="deploy-application"
    classname="com.example.deployment.DeployTask"
    classpathref="deployment.classpath"
    loaderref="deployment.loader" />
```

Hai nhóm có classpath và loaderref riêng. Điều này giúp giới hạn phạm vi dependency và giảm nguy cơ một extension vô tình sử dụng phiên bản thư viện của extension khác.

Nếu hai nhóm thực sự cần chia sẻ cùng một API hoặc object, hãy đưa các lớp chung vào một thư viện phiên bản thống nhất và thiết kế classloader dùng chung có chủ đích. Không gộp tất cả extension vào một loader chỉ để buildfile ngắn hơn.

## 14. Ví dụ buildfile hoàn chỉnh với thư viện bắt buộc và tùy chọn

Ví dụ sau đăng ký một extension bắt buộc để tạo gói và một extension tùy chọn để xuất báo cáo nâng cao. Build dừng sớm nếu thư viện bắt buộc thiếu; tính năng báo cáo nâng cao chỉ chạy khi JAR tùy chọn có mặt.

```xml
<project name="extension-loading" default="build">

    <property name="required.extension.jar" value="lib/company-ant-tasks.jar" />
    <property name="optional.extension.jar" value="lib/advanced-report.jar" />

    <target name="check-required-extension">
        <available
            file="${required.extension.jar}"
            type="file"
            property="required.extension.present" />
        <fail
            unless="required.extension.present"
            message="Required extension is missing: ${required.extension.jar}" />
    </target>

    <target name="define-required-extension" depends="check-required-extension">
        <path id="required.extension.classpath">
            <pathelement location="${required.extension.jar}" />
            <pathelement location="lib/company-api.jar" />
        </path>
        <taskdef
            name="package-application"
            classname="com.example.ant.PackageApplicationTask"
            classpathref="required.extension.classpath"
            loaderref="company.extension.loader" />
    </target>

    <target name="check-optional-extension">
        <available
            file="${optional.extension.jar}"
            type="file"
            property="optional.extension.present" />
    </target>

    <target name="define-optional-extension"
            depends="check-optional-extension"
            if="optional.extension.present">
        <path id="optional.extension.classpath">
            <pathelement location="${optional.extension.jar}" />
            <pathelement location="lib/reporting-api.jar" />
        </path>
        <taskdef
            name="advanced-report"
            classname="com.example.reporting.AdvancedReportTask"
            classpathref="optional.extension.classpath"
            loaderref="advanced.reporting.loader" />
    </target>

    <target name="build" depends="define-required-extension">
        <package-application />
    </target>

    <target name="report"
            depends="define-optional-extension"
            if="optional.extension.present">
        <advanced-report />
    </target>

    <target name="report-unavailable"
            depends="check-optional-extension"
            unless="optional.extension.present">
        <echo message="Advanced reporting is unavailable; install ${optional.extension.jar} to enable it." />
    </target>

</project>
```

Các target `check-*` kiểm tra sự tồn tại của JAR. `define-required-extension` chỉ chạy sau khi kiểm tra bắt buộc thành công; `define-optional-extension` chỉ đăng ký task khi JAR tùy chọn có mặt. `report` phụ thuộc vào bước đăng ký và có cùng điều kiện, còn `report-unavailable` thông báo khi thư viện không có.

Ví dụ giả định các dependency bắc cầu như `company-api.jar` và `reporting-api.jar` cũng được cung cấp ở đúng đường dẫn. Kiểm tra một JAR chính không bảo đảm các dependency đó tồn tại; nếu chúng cũng có thể bị thiếu, hãy kiểm tra chúng trong target tương ứng trước khi gọi `taskdef`.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant không tìm thấy lớp task | JAR chính chưa có trong classpath hoặc `classname` sai | Kiểm tra tên đầy đủ của lớp và `classpath`/`classpathref` |
| Nạp được task class nhưng lỗi khi thực thi | Thiếu dependency bắc cầu | Bổ sung các JAR mà extension tham chiếu vào classpath |
| `ClassCastException` dù hai lớp có cùng tên | Hai bản lớp được nạp bởi classloader khác nhau | Dùng loaderref chung nếu chúng phải chia sẻ cùng kiểu, hoặc tách hẳn API/dependency |
| Task không được nhận diện | Target đăng ký chưa chạy hoặc `taskdef` thất bại | Đặt target đăng ký trong `depends` trước target sử dụng |
| Extension dùng nhầm phiên bản thư viện | Classpath chứa nhiều phiên bản hoặc thứ tự dependency không rõ | Khóa phiên bản và khai báo JAR cụ thể |
| Thay JAR nhưng Ant vẫn dùng lớp cũ | Classloader đã nạp và giữ lớp trong tiến trình hiện tại | Khởi động invocation Ant mới sau khi cập nhật thư viện |
| Extension tùy chọn thiếu nhưng build vẫn lỗi | Target vẫn gọi task chưa được đăng ký | Đặt điều kiện cho cả target đăng ký và target sử dụng |
| Extension bắt buộc thiếu nhưng lỗi xuất hiện muộn | Chưa kiểm tra file trước khi đăng ký hoặc sử dụng | Dùng `available` và `fail` ở target kiểm tra đầu tiên |
| `onerror="ignore"` làm khó tìm nguyên nhân | Lỗi nạp lớp bị che giấu, task không được đăng ký | Dùng `fail` cho dependency bắt buộc; với optional, kiểm tra property và báo rõ trạng thái |
| Hai extension không chia sẻ được object | Chúng dùng các classloader khác nhau hoặc API khác phiên bản | Chuẩn hóa API chung và dùng cùng loaderref khi cần |

Khi debug, kiểm tra theo thứ tự: file JAR có tồn tại, `classname` có đúng, classpath có đủ dependency, target đăng ký có chạy trước, loaderref có được dùng nhất quán và phiên bản API có tương thích hay không. Chỉ thêm JAR vào classpath sau khi đã xác định nó là dependency cần thiết.

## 16. Quy trình cấu hình extension ổn định

Khi tích hợp một thư viện task hoặc data type vào Ant, có thể thực hiện theo trình tự sau:

1. Xác định extension cung cấp task hay data type và lấy đúng tên lớp hoặc Antlib descriptor.
2. Liệt kê JAR chính cùng dependency bắc cầu cần thiết.
3. Tạo một Path có `id` mô tả rõ nhóm extension và dùng `classpathref` để tái sử dụng.
4. Dùng `taskdef` cho task hoặc `typedef` cho data type; nếu dùng Antlib, khai báo `uri`, `resource` và namespace tương ứng.
5. Chọn `loaderref` khi nhiều định nghĩa cần chia sẻ cùng classloader và cùng bộ dependency tương thích.
6. Kiểm tra file trước khi đăng ký: dependency bắt buộc thì `fail` sớm; dependency tùy chọn thì chỉ đăng ký và gọi task khi có mặt.
7. Dùng `onerror` phù hợp, tránh che giấu lỗi của extension bắt buộc.
8. Khóa phiên bản JAR và kiểm tra tương thích giữa extension, Ant runtime và JDK.
9. Chạy target đăng ký trước target sử dụng và khởi động Ant invocation mới khi thay đổi JAR.

`classpathref` cho Ant biết nơi tìm lớp và dependency của extension; `loaderref` giúp nhiều định nghĩa chia sẻ classloader khi cần. Kết hợp hai cấu hình này với kiểm tra thư viện bắt buộc/tùy chọn và chính sách lỗi rõ ràng giúp buildfile nạp extension có kiểm soát, dễ chẩn đoán và ổn định giữa máy phát triển với CI.

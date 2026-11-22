# Kiểm tra tập tệp rỗng và tránh chọn nhầm thư mục đầu ra

Trong Apache Ant, `FileSet` dùng các mẫu `include` và `exclude` để chọn tập tệp từ một thư mục gốc. Khi viết build file, cần kiểm soát hai vấn đề: tập tệp được chọn có thực sự chứa tệp cần xử lý hay không, và các mẫu có vô tình chọn cả thư mục đầu ra do build tạo ra hay không.

Nếu tập tệp rỗng, một số task có thể không làm gì vì không có đầu vào. Điều đó đôi khi là hợp lệ, nhưng cũng có thể che giấu lỗi cấu hình như chọn sai thư mục nguồn hoặc viết sai mẫu. Nếu thư mục đầu ra bị đưa vào tập đầu vào, build có thể sao chép lại sản phẩm cũ, đóng gói cả artifact đã sinh hoặc lặp dữ liệu qua nhiều lần chạy.

## 1. FileSet chọn tệp như thế nào?

`<fileset>` là một resource collection mô tả các tệp nằm dưới một thư mục gốc. Thuộc tính `dir` xác định thư mục gốc; các phần tử `<include>` và `<exclude>` giới hạn những đường dẫn được chọn.

Ví dụ:

```xml
<fileset dir="src/main/resources">
    <include name="**/*.properties"/>
    <exclude name="**/local-*.properties"/>
</fileset>
```

Ant tìm các tệp có phần mở rộng `.properties` bên dưới `src/main/resources`, sau đó loại bỏ những tệp có tên phù hợp với mẫu `**/local-*.properties`.

### 1.1. Thư mục gốc và đường dẫn tương đối

Các mẫu trong FileSet được so khớp tương đối với thư mục `dir`, không phải với thư mục làm việc tùy ý của terminal. Ví dụ:

```xml
<fileset dir="src/main/java">
    <include name="com/example/**/*.java"/>
</fileset>
```

Mẫu bắt đầu từ `src/main/java`. Nó chọn các tệp Java nằm trong cây con `com/example` của thư mục đó.

Nếu `dir` là thư mục gốc dự án, mẫu phải bao gồm phần đường dẫn từ gốc dự án:

```xml
<fileset dir="${basedir}">
    <include name="src/main/java/**/*.java"/>
</fileset>
```

Hai cách khai báo có thể chọn cùng một tập tệp, nhưng phạm vi tìm kiếm khác nhau. Chọn thư mục gốc càng cụ thể càng dễ kiểm soát và thường giảm nguy cơ quét nhầm tài nguyên không liên quan.

### 1.2. Ý nghĩa của `*`, `?` và `**`

Ant sử dụng mẫu đường dẫn để so khớp tên tệp và thư mục:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `*` | Khớp không hoặc nhiều ký tự trong một đoạn tên, không vượt qua dấu phân cách thư mục | `*.java` chọn tệp Java ngay trong thư mục gốc của FileSet |
| `?` | Khớp một ký tự trong một đoạn tên | `Test?.java` khớp `Test1.java`, `TestA.java` |
| `**` | Khớp không hoặc nhiều cấp thư mục | `**/*.java` chọn tệp Java ở nhiều cấp bên dưới thư mục gốc |

Một số mẫu thường gặp:

```xml
<include name="*.xml"/>
<include name="**/*.java"/>
<include name="config/**/*.properties"/>
<exclude name="**/generated/**"/>
```

Các mẫu nên dùng dấu `/` để phân tách thư mục, kể cả khi build chạy trên Windows. Ant xử lý mẫu theo quy ước đường dẫn của nó và chuyển đổi phù hợp với hệ điều hành.

### 1.3. Khi không khai báo include

Nếu FileSet không có điều kiện include, mặc định mọi tệp dưới thư mục gốc đều có thể được chọn, ngoại trừ những tệp bị loại bởi exclude và default excludes. Vì vậy, đoạn sau có phạm vi rất rộng:

```xml
<fileset dir="${basedir}"/>
```

Khi dùng thư mục gốc dự án, không nên để FileSet rộng như vậy nếu task chỉ cần mã nguồn hoặc tài nguyên cụ thể. Hãy khai báo include theo loại tệp hoặc thư mục nguồn cần xử lý.

## 2. Kiểm tra tập tệp có rỗng hay không

Một FileSet có thể hợp lệ nhưng không chọn được tệp nào. Ví dụ, thư mục nguồn tồn tại nhưng chưa có file `.java`, hoặc mẫu include không khớp với tên tệp thực tế.

Ant cung cấp condition `<resourcecount>` để kiểm tra số lượng resource trong một resource collection. Có thể kết hợp nó với task `<condition>` để đặt property khi số lượng tệp lớn hơn 0.

Ví dụ:

```xml
<condition property="has.java.sources">
    <resourcecount count="0" when="greater">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
    </resourcecount>
</condition>
```

Khi FileSet chứa ít nhất một resource được chọn, điều kiện đúng và Ant đặt property `has.java.sources`. Nếu không có resource nào, property này không được đặt.

`resourcecount` là một condition, không phải task độc lập để in số lượng ra log. Nó được dùng bên trong các cấu trúc nhận condition, chẳng hạn `<condition>` hoặc `<waitfor>`.

### 2.1. Dừng build khi không có tệp đầu vào

Nếu bước biên dịch bắt buộc phải có mã nguồn, hãy kiểm tra số lượng trước và dừng build với thông báo cụ thể:

```xml
<project name="source-check" default="compile" basedir=".">

    <property name="src.dir" value="src/main/java"/>
    <property name="classes.dir" value="build/classes"/>

    <target name="check-sources">
        <condition property="has.java.sources">
            <resourcecount count="0" when="greater">
                <fileset dir="${src.dir}">
                    <include name="**/*.java"/>
                </fileset>
            </resourcecount>
        </condition>

        <fail unless="has.java.sources"
              message="No Java source files found under ${src.dir}. Check src.dir and include patterns."/>
    </target>

    <target name="compile" depends="check-sources">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includes="**/*.java"
               includeantruntime="false"/>
    </target>

</project>
```

Target `check-sources` tạo property `has.java.sources` khi tìm được ít nhất một tệp Java. Nếu không tìm thấy, task `<fail>` dừng build và hiển thị đường dẫn cùng gợi ý kiểm tra. Target `compile` phụ thuộc `check-sources`, vì vậy Ant chỉ biên dịch sau khi kiểm tra thành công.

Khi dùng cùng một logic chọn cho bước đếm và bước xử lý, hãy giữ các mẫu include/exclude nhất quán. Nếu FileSet kiểm tra một nhóm tệp nhưng task `<javac>` lại dùng mẫu khác, kết quả kiểm tra có thể không phản ánh chính xác đầu vào mà compiler nhận được.

### 2.2. Bỏ qua bước xử lý khi không có tệp

Không phải mọi trường hợp tập tệp rỗng đều là lỗi. Ví dụ, một module có thể không có tài nguyên tùy chọn hoặc không có mã nguồn kiểm thử trong một cấu hình nhất định. Khi đó, build có thể bỏ qua target tương ứng và tiếp tục.

```xml
<project name="optional-sources" default="build" basedir=".">

    <property name="src.dir" value="src/optional/java"/>

    <target name="detect-optional-sources">
        <condition property="has.optional.sources">
            <resourcecount count="0" when="greater">
                <fileset dir="${src.dir}" erroronmissingdir="false">
                    <include name="**/*.java"/>
                </fileset>
            </resourcecount>
        </condition>
    </target>

    <target name="compile-optional"
            depends="detect-optional-sources"
            if="has.optional.sources">
        <javac srcdir="${src.dir}"
               destdir="build/optional-classes"
               includes="**/*.java"
               includeantruntime="false"/>
    </target>

    <target name="skip-optional"
            depends="detect-optional-sources"
            unless="has.optional.sources">
        <echo message="No optional Java sources; skipping this step."/>
    </target>

    <target name="build" depends="compile-optional,skip-optional">
        <echo message="Build flow completed."/>
    </target>

</project>
```

Ở đây thư mục nguồn là tùy chọn, vì vậy FileSet đặt `erroronmissingdir="false"`. Nếu thư mục không tồn tại hoặc không có file `.java`, điều kiện không đặt `has.optional.sources`; target `compile-optional` được bỏ qua và `skip-optional` in thông báo.

Thuộc tính `if` và `unless` của target kiểm tra sự tồn tại của property, không đánh giá chuỗi `false` như một biểu thức boolean. Vì thế ví dụ chỉ đặt `has.optional.sources` khi condition đúng và để property không tồn tại khi condition sai.

## 3. Phân biệt tập tệp rỗng với thư mục không tồn tại

Hai trường hợp này thường bị nhầm lẫn:

- Thư mục tồn tại nhưng không có tệp nào khớp với mẫu: FileSet hợp lệ, kết quả chọn có thể rỗng.
- Thư mục gốc không tồn tại: có thể là lỗi đường dẫn hoặc một thư mục tùy chọn chưa được tạo.

FileSet có thuộc tính `erroronmissingdir`. Mặc định thuộc tính này là `true`, nghĩa là Ant báo lỗi nếu thư mục `dir` không tồn tại. Đặt `erroronmissingdir="false"` khiến thư mục bị thiếu được xem như tập rỗng.

Ví dụ yêu cầu thư mục nguồn phải tồn tại:

```xml
<fileset dir="src/main/java" erroronmissingdir="true">
    <include name="**/*.java"/>
</fileset>
```

Ví dụ thư mục tùy chọn có thể chưa được tạo:

```xml
<fileset dir="src/generated/java" erroronmissingdir="false">
    <include name="**/*.java"/>
</fileset>
```

Không nên đặt `erroronmissingdir="false"` một cách mặc định cho mọi FileSet. Nếu `src/main/java` bị gõ sai thành `src/main/jvaa`, việc coi thư mục không tồn tại như tập rỗng có thể che giấu lỗi. Hãy chỉ dùng tùy chọn này khi thiếu thư mục thực sự là một trạng thái hợp lệ.

## 4. Tránh chọn nhầm thư mục đầu ra

Thư mục đầu ra chứa các tệp được sinh ra trong quá trình build, chẳng hạn `.class`, JAR, báo cáo, tài nguyên đã xử lý hoặc mã nguồn sinh tự động. Những thư mục phổ biến gồm `build/`, `target/`, `dist/` và `out/`.

Nếu FileSet quét từ thư mục gốc dự án với mẫu quá rộng, nó có thể chọn lại chính những sản phẩm đã được tạo ra. Việc này gây ra các vấn đề như:

- Đóng gói JAR cũ vào JAR mới hoặc đưa artifact vào một gói không mong muốn.
- Sao chép thư mục đầu ra trở lại một vị trí khác, làm tăng dữ liệu qua mỗi lần chạy.
- Đưa báo cáo, class đã biên dịch hoặc tệp tạm vào bước xử lý nguồn.
- Khi đầu ra nằm bên trong phạm vi đầu vào, một task sao chép đệ quy có thể gặp dữ liệu thay đổi trong lúc đang quét.

### 4.1. Ưu tiên chọn thư mục nguồn cụ thể

Cách đơn giản và an toàn nhất là đặt thư mục nguồn và thư mục đầu ra tách biệt, sau đó đặt `dir` của FileSet đúng vào thư mục nguồn:

```text
sample-project/
├── src/
│   └── main/
│       ├── java/
│       └── resources/
├── build/
│   ├── classes/
│   └── dist/
└── build.xml
```

Chọn mã nguồn Java:

```xml
<fileset dir="src/main/java">
    <include name="**/*.java"/>
</fileset>
```

Vì FileSet chỉ quét dưới `src/main/java`, các thư mục `build/classes` và `build/dist` nằm ngoài phạm vi lựa chọn. Đây là cách tốt hơn việc quét toàn bộ dự án rồi cố loại trừ mọi thư mục không mong muốn.

### 4.2. Loại trừ thư mục đầu ra khi phải quét từ project root

Đôi khi task cần quét nhiều nhóm tệp trong project root. Khi đó, hãy khai báo include cụ thể và loại trừ những thư mục sinh ra:

```xml
<property name="build.dir" value="build"/>

<fileset dir="${basedir}">
    <include name="**/*.java"/>
    <include name="**/*.properties"/>

    <exclude name="${build.dir}/**"/>
    <exclude name="target/**"/>
    <exclude name="dist/**"/>
    <exclude name="out/**"/>
    <exclude name="**/generated/**"/>
</fileset>
```

Trong ví dụ, các mẫu exclude được tính tương đối với `${basedir}`. `build/**` loại trừ thư mục build ở gốc dự án; `target/**`, `dist/**` và `out/**` loại trừ các thư mục đầu ra tương ứng. Mẫu `**/generated/**` loại trừ thư mục `generated` ở mọi cấp.

Nếu thư mục đầu ra có tên hoặc vị trí khác, hãy bổ sung đúng mẫu. Không giả định Ant tự động bỏ qua `build`, `target`, `dist` hoặc `out`.

### 4.3. Default excludes không thay thế exclude đầu ra

FileSet bật default excludes theo mặc định. Các mẫu mặc định thường loại trừ dữ liệu quản lý phiên bản và tệp phụ trợ phổ biến như thư mục `.git`, `.svn`, `CVS` hoặc một số tệp backup.

Default excludes không có nghĩa là Ant tự loại trừ mọi thư mục build. Các thư mục `build/`, `target/`, `dist/` và `out/` thường cần được loại trừ tường minh nếu phạm vi quét có thể đi vào chúng.

Thuộc tính `defaultexcludes="false"` tắt các mẫu loại trừ mặc định. Chỉ dùng khi thật sự cần chọn những tệp đó; việc tắt default excludes không giúp tránh chọn nhầm đầu ra và có thể khiến FileSet lấy cả dữ liệu quản lý phiên bản.

## 5. Tách riêng đầu vào và đầu ra trong từng task

Đối với các task như `<copy>`, `<jar>` hoặc `<zip>`, hãy xác định rõ FileSet là đầu vào và thư mục hoặc tệp đích là đầu ra. Không để đầu ra nằm trong chính phạm vi đầu vào nếu task đang quét đệ quy.

### 5.1. Sao chép tài nguyên

Ví dụ sao chép tài nguyên từ `src/main/resources` sang `build/resources`:

```xml
<property name="resources.dir" value="src/main/resources"/>
<property name="build.dir" value="build"/>

<target name="copy-resources">
    <copy todir="${build.dir}/resources">
        <fileset dir="${resources.dir}">
            <include name="**/*"/>
            <exclude name="**/local/**"/>
        </fileset>
    </copy>
</target>
```

FileSet chỉ đọc dưới `src/main/resources`; task `<copy>` ghi vào `build/resources`. Nếu lần chạy sau quét lại `build/resources` làm nguồn, dữ liệu đã sao chép có thể bị xử lý thêm lần nữa. Hãy giữ nguồn và đích tách biệt.

Nếu cần kiểm tra có tài nguyên hay không trước khi copy, có thể dùng `<resourcecount>` trên cùng FileSet rồi đặt target copy theo property điều kiện.

### 5.2. Đóng gói JAR

Task `<jar>` thường nhận các tệp từ một thư mục class hoặc FileSet. Đầu vào nên là thư mục class đã biên dịch, còn tệp JAR phải nằm ngoài thư mục được quét:

```xml
<property name="classes.dir" value="build/classes"/>
<property name="dist.dir" value="build/dist"/>

<target name="package">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar">
        <fileset dir="${classes.dir}">
            <include name="**/*.class"/>
            <exclude name="**/test/**"/>
        </fileset>
    </jar>
</target>
```

Trong ví dụ, FileSet chỉ chọn class dưới `build/classes`, còn JAR được tạo ở `build/dist`. Nếu đặt JAR bên trong chính thư mục FileSet đang quét, build file sẽ trộn đầu ra đóng gói với đầu vào và có thể gây kết quả không mong muốn ở những lần chạy sau.

## 6. Kiểm tra số lượng tệp với `resourcecount`

`resourcecount` hỗ trợ so sánh số lượng resource với một giá trị. Thuộc tính `count` đặt số lượng cần so sánh; `when` xác định phép so sánh.

| `when` | Điều kiện |
|---|---|
| `equal` | Số lượng bằng `count` |
| `greater` | Số lượng lớn hơn `count` |
| `less` | Số lượng nhỏ hơn `count` |

Ví dụ kiểm tra FileSet có đúng 0 tệp:

```xml
<condition property="source.set.empty">
    <resourcecount count="0" when="equal">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
    </resourcecount>
</condition>
```

Nếu số lượng resource bằng 0, property `source.set.empty` được đặt. Có thể dùng điều kiện lớn hơn 0 để kiểm tra trường hợp có đầu vào:

```xml
<condition property="source.set.has-files">
    <resourcecount count="0" when="greater">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
    </resourcecount>
</condition>
```

Hai property trên là hai cách diễn đạt ngược nhau về cùng một tập hợp, nhưng trong build thực tế chỉ cần khai báo property phục vụ quyết định tiếp theo. Nếu dùng nhiều điều kiện, hãy bảo đảm chúng áp dụng cùng một FileSet và cùng quy tắc chọn.

`resourcecount` đếm resource trong collection được cung cấp. Khi mục tiêu là đếm tệp, hãy dùng FileSet với mẫu chỉ chọn tệp cần quan tâm, chẳng hạn `**/*.java`, để tránh đếm nhầm loại resource khác.

## 7. Hiểu hành vi của task khi tập tệp rỗng

Không phải task nào cũng xử lý tập rỗng theo cùng một cách. Có task đơn giản không thực hiện thao tác nào vì không có đầu vào; có task có thể tạo ra sản phẩm rỗng; có task có thể báo lỗi tùy cấu hình hoặc yêu cầu của nó.

Vì vậy, đừng dựa vào hành vi ngầm của task để kết luận rằng đầu vào đã được chọn đúng. Nếu tệp đầu vào là bắt buộc, hãy kiểm tra trước bằng `resourcecount` và dừng bằng `<fail>` khi không có tệp. Nếu đầu vào là tùy chọn, hãy dùng điều kiện để bỏ qua bước xử lý và ghi log rõ ràng.

Ví dụ với một nhóm tài nguyên tùy chọn:

```xml
<target name="detect-resources">
    <condition property="has.resources">
        <resourcecount count="0" when="greater">
            <fileset dir="src/optional/resources" erroronmissingdir="false">
                <include name="**/*"/>
            </fileset>
        </resourcecount>
    </condition>
</target>

<target name="copy-resources"
        depends="detect-resources"
        if="has.resources">
    <copy todir="build/resources">
        <fileset dir="src/optional/resources">
            <include name="**/*"/>
        </fileset>
    </copy>
</target>
```

Ở đây thư mục tài nguyên tùy chọn có thể không tồn tại. Nếu có tệp, target copy chạy; nếu không, target được bỏ qua. Nếu cần thông báo rõ ràng cho trường hợp bỏ qua, có thể thêm target `unless="has.resources"` phụ thuộc vào `detect-resources` để in thông báo.

Đối với thư mục nguồn bắt buộc, hãy giữ `erroronmissingdir="true"` và kiểm tra số lượng tệp. Điều đó phân biệt được đường dẫn nguồn sai với trường hợp thư mục hợp lệ nhưng không có tệp phù hợp.

## 8. Các lỗi chọn tệp thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| FileSet rỗng dù thư mục có tệp | Mẫu include không khớp, sai thư mục `dir` hoặc sai phần đường dẫn tương đối | Kiểm tra `dir`, tên tệp và mẫu; nhớ rằng mẫu được tính từ thư mục gốc FileSet |
| FileSet chọn quá nhiều tệp | Không có include hoặc dùng mẫu quá rộng như `**/*` | Chọn thư mục nguồn cụ thể và khai báo include theo loại tệp cần xử lý |
| Build bỏ qua lỗi do thư mục nguồn bị thiếu | Đặt `erroronmissingdir="false"` cho một thư mục vốn phải tồn tại | Dùng `erroronmissingdir="true"` cho đầu vào bắt buộc và chỉ tắt khi thư mục thực sự tùy chọn |
| JAR chứa artifact cũ hoặc tài nguyên ngoài ý muốn | FileSet quét cả thư mục đầu ra hoặc không loại trừ thư mục sinh tự động | Tách source/output và thêm exclude tương ứng |
| Tệp được copy lặp qua nhiều lần chạy | Thư mục đích nằm trong phạm vi nguồn được quét | Đặt thư mục đích ngoài thư mục nguồn hoặc giới hạn include/exclude |
| FileSet không lấy dữ liệu trong `.git` hoặc `.svn` | Default excludes đang hoạt động | Chỉ tắt `defaultexcludes` nếu thực sự cần những tệp này |
| Condition báo không có tệp dù task sau tìm thấy tệp | FileSet dùng trong `resourcecount` và mẫu của task xử lý không giống nhau | Đồng bộ include/exclude và thư mục gốc của cả hai bước |
| Tập tệp rỗng nhưng build vẫn báo thành công | Task không coi tập rỗng là lỗi | Thêm `resourcecount` và `<fail>` nếu đầu vào bắt buộc |

## 9. Ví dụ hoàn chỉnh: kiểm tra nguồn và loại trừ output

Ví dụ sau quét mã nguồn Java từ project root, loại trừ thư mục đầu ra và kiểm tra tập nguồn trước khi biên dịch:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="safe-file-selection" default="compile" basedir=".">

    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>

    <target name="check-sources">
        <condition property="has.java.sources">
            <resourcecount count="0" when="greater">
                <fileset dir="${basedir}" erroronmissingdir="true">
                    <include name="src/main/java/**/*.java"/>
                    <exclude name="${build.dir}/**"/>
                    <exclude name="target/**"/>
                    <exclude name="dist/**"/>
                    <exclude name="out/**"/>
                    <exclude name="**/generated/**"/>
                </fileset>
            </resourcecount>
        </condition>

        <fail unless="has.java.sources"
              message="No Java source files selected. Check the source path and patterns."/>
    </target>

    <target name="compile" depends="check-sources">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includes="**/*.java"
               excludes="**/generated/**"
               includeantruntime="false"/>
    </target>

</project>
```

FileSet dùng project root làm phạm vi, nhưng include chỉ chọn `src/main/java/**/*.java`. Các exclude thể hiện rõ những vùng không được chọn nếu quy tắc include sau này được mở rộng. Target `check-sources` đếm số resource; nếu không có tệp phù hợp, build dừng trước khi tạo class.

Trong ví dụ này, `<javac>` dùng `srcdir`, `includes` và `excludes` tương ứng với nhóm mã nguồn đã kiểm tra: các tệp Java trong `src/main/java`, ngoại trừ cây con `generated`. Các exclude đầu ra ở FileSet cũng đóng vai trò bảo vệ nếu phạm vi include được mở rộng về sau. Khi thay đổi cấu trúc source, hãy cập nhật cả FileSet kiểm tra và cấu hình compiler để chúng vẫn mô tả cùng tập đầu vào. Nếu có thể, ưu tiên đặt FileSet trực tiếp dưới thư mục nguồn cụ thể thay vì quét từ project root.

## 10. Checklist chọn tệp an toàn

- [ ] `dir` trỏ đến đúng thư mục nguồn và tồn tại nếu đó là đầu vào bắt buộc.
- [ ] Các mẫu include được tính tương đối với `dir` và chỉ chọn loại tệp cần xử lý.
- [ ] Đã hiểu sự khác nhau giữa `*`, `?` và `**`.
- [ ] Đã kiểm tra trường hợp FileSet không có tệp khớp.
- [ ] Đã dùng `resourcecount` nếu cần phân biệt tập rỗng với tập có dữ liệu.
- [ ] Đã dùng `<fail>` khi đầu vào rỗng là lỗi, hoặc điều kiện target khi đầu vào tùy chọn.
- [ ] Đã chọn `erroronmissingdir` phù hợp để không che giấu đường dẫn nguồn bị sai.
- [ ] Đã tách thư mục nguồn khỏi `build`, `target`, `dist` hoặc thư mục đầu ra tương ứng.
- [ ] Đã khai báo exclude cho các thư mục sinh tự động có thể nằm trong phạm vi quét.
- [ ] Đã hiểu default excludes không tự loại trừ mọi thư mục đầu ra.
- [ ] FileSet dùng để kiểm tra và task dùng để xử lý có cùng quy tắc chọn tệp.
- [ ] Không để task sao chép hoặc đóng gói đọc lại sản phẩm mà chính nó vừa tạo ra.

Kiểm tra tập tệp rỗng và kiểm soát thư mục đầu ra giúp build file Ant phát hiện sớm cấu hình nguồn sai, tránh xử lý nhầm artifact cũ và giữ cho kết quả build ổn định qua nhiều lần chạy. Hãy bắt đầu bằng một thư mục nguồn cụ thể, chọn đúng mẫu tệp, rồi bổ sung kiểm tra số lượng và exclude ở những nơi phạm vi quét có thể bao gồm dữ liệu sinh ra.

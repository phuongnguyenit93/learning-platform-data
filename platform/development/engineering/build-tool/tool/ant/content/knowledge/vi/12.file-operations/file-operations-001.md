# Tạo thư mục bằng `mkdir` và xóa đầu ra bằng `delete`

Trong một quy trình build Java, Ant thường cần tạo thư mục để chứa lớp đã biên dịch, tài nguyên được sao chép và tệp JAR. Sau khi build xong, ta cũng cần xóa các kết quả cũ để tránh tệp sinh ra từ lần chạy trước ảnh hưởng đến lần chạy hiện tại.

Ant cung cấp hai task cơ bản cho các thao tác này:

- `<mkdir>` tạo thư mục và các thư mục cha còn thiếu.
- `<delete>` xóa một tệp, một thư mục hoặc những mục được chọn thông qua FileSet.

Hai task này thường xuất hiện trong các target `init` và `clean`. Hiểu đúng cách chỉ định đường dẫn, phạm vi xóa và cách xử lý lỗi sẽ giúp buildfile dễ dùng và tránh xóa nhầm dữ liệu.

Sau bài học, bạn có thể:

- Tạo thư mục đầu ra bằng task `<mkdir>`.
- Tổ chức các đường dẫn build bằng property.
- Xóa tệp hoặc toàn bộ thư mục bằng task `<delete>`.
- Xóa có chọn lọc bằng `fileset`, `include` và `exclude`.
- Hiểu tác dụng của `includeEmptyDirs`, `failonerror`, `quiet` và `verbose`.
- Thiết kế các target `clean`, `init` và `clean-build` phù hợp.

## 1. Tạo thư mục với task `<mkdir>`

Task `<mkdir>` tạo thư mục tại đường dẫn được chỉ định bởi thuộc tính `dir`:

```xml
<mkdir dir="build" />
```

Nếu thư mục `build` chưa tồn tại, Ant tạo thư mục đó. Nếu thư mục đã tồn tại, task không cần tạo lại và thông thường không báo lỗi. Vì vậy, `<mkdir>` phù hợp với các bước chuẩn bị có thể được gọi nhiều lần.

### 1.1. Tạo thư mục con và thư mục cha

`mkdir` có thể tạo cả cây thư mục khi các thư mục cha chưa tồn tại:

```xml
<mkdir dir="build/classes/com/example" />
```

Nếu chưa có `build`, `build/classes` hoặc `build/classes/com`, Ant tạo các thư mục cần thiết để hoàn thành đường dẫn.

Ví dụ, một dự án Java có thể chuẩn bị cấu trúc đầu ra như sau:

```xml
<target name="init">
    <mkdir dir="build/classes" />
    <mkdir dir="build/resources" />
    <mkdir dir="build/reports" />
</target>
```

Sau khi target `init` chạy, cấu trúc thư mục có dạng:

```text
project/
├── build/
│   ├── classes/
│   ├── resources/
│   └── reports/
├── src/
└── build.xml
```

Không cần tạo riêng từng thư mục cha trước khi tạo thư mục con. Tuy nhiên, khai báo từng thư mục đầu ra có ý nghĩa giúp người đọc biết build cần những vị trí nào.

### 1.2. Dùng property cho đường dẫn

Trong buildfile, nên đặt các đường dẫn thường dùng vào property thay vì lặp lại chuỗi đường dẫn ở nhiều task:

```xml
<project name="file-operations" default="init" basedir=".">
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="resources.dir" location="${build.dir}/resources" />

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${resources.dir}" />
    </target>
</project>
```

Property `build.dir` xác định thư mục gốc chứa kết quả build. Các property còn lại được tạo dựa trên đường dẫn đó. Nếu muốn chuyển toàn bộ đầu ra sang thư mục khác, có thể truyền giá trị mới từ dòng lệnh:

```bash
ant -Dbuild.dir=out init
```

Với property của Ant, giá trị đã được đặt không tự thay đổi. Vì vậy, giá trị `build.dir` truyền từ dòng lệnh được giữ lại khi buildfile khai báo giá trị mặc định cùng tên.

### 1.3. Đường dẫn tương đối và tuyệt đối

Đường dẫn tương đối trong buildfile thường được phân giải theo thư mục cơ sở của project (`basedir`). Ví dụ:

```xml
<project name="demo" basedir=".">
    <target name="init">
        <mkdir dir="build/classes" />
    </target>
</project>
```

Với `basedir="."`, thư mục hiện tại của project là cơ sở để xác định `build/classes`. Có thể đặt `basedir` thành một thư mục khác nếu buildfile cần làm việc với một cây dự án cụ thể.

Đường dẫn tuyệt đối cũng có thể được dùng:

```xml
<mkdir dir="C:/temp/java-build" />
```

Tuy nhiên, đường dẫn tuyệt đối gắn buildfile với một máy hoặc hệ điều hành cụ thể. Để dự án dễ di chuyển, hãy ưu tiên đường dẫn tương đối hoặc property có thể cấu hình.

## 2. Xóa thư mục và tệp với task `<delete>`

Task `<delete>` có thể xóa một tệp hoặc một thư mục. Khi xóa thư mục bằng thuộc tính `dir`, Ant xóa cả nội dung bên trong thư mục đó theo cách đệ quy.

### 2.1. Xóa một thư mục đầu ra

Ví dụ xóa toàn bộ thư mục `build`:

```xml
<delete dir="build" />
```

Nếu `build` chứa các thư mục con và tệp đã sinh ra từ các lần build trước, chúng cũng bị xóa. Đây là cách thường dùng để tạo target `clean`:

```xml
<target name="clean" description="Remove generated build output">
    <delete dir="build" />
</target>
```

Sau khi chạy:

```bash
ant clean
```

thư mục `build` cùng nội dung của nó được loại bỏ. Các thư mục mã nguồn như `src` và tệp cấu hình như `build.xml` vẫn nằm ngoài phạm vi xóa.

### 2.2. Xóa một tệp cụ thể

Để xóa một tệp, dùng thuộc tính `file`:

```xml
<delete file="build/app.jar" />
```

Có thể xóa một số tệp đã biết trong cùng target:

```xml
<target name="clean-reports">
    <delete file="build/reports/test-report.xml" />
    <delete file="build/reports/coverage.txt" />
</target>
```

Khi chỉ muốn xóa một vài tệp cụ thể, `file` thể hiện phạm vi rõ ràng. Khi muốn xóa cả cây đầu ra, dùng `dir` sẽ đơn giản hơn.

### 2.3. Xóa thư mục con

Có thể xóa riêng một thư mục con mà vẫn giữ các thư mục khác:

```xml
<delete dir="build/reports" />
```

Trong trường hợp này, `build/classes` và `build/resources` vẫn được giữ lại nếu chúng nằm bên cạnh `reports` trong thư mục `build`.

Hãy xác định chính xác thư mục được truyền vào `dir`. Một property đường dẫn sai có thể khiến task xóa một cây thư mục rộng hơn dự định.

## 3. Xóa có chọn lọc bằng FileSet

Đôi khi không muốn xóa toàn bộ thư mục. Ví dụ, cần xóa tệp `.tmp` và `.log` nhưng vẫn giữ lại các tài nguyên khác. Có thể đặt một FileSet bên trong task `<delete>`:

```xml
<delete>
    <fileset dir="build">
        <include name="**/*.tmp" />
        <include name="**/*.log" />
    </fileset>
</delete>
```

FileSet chọn các tệp phù hợp với mẫu; task `delete` xóa những mục đã chọn. Thư mục gốc `build` không bị xóa chỉ vì các tệp bên trong được chọn.

### 3.1. Kết hợp `include` và `exclude`

Ví dụ xóa các tệp log nhưng giữ lại log có tên `important.log`:

```xml
<delete>
    <fileset dir="logs">
        <include name="**/*.log" />
        <exclude name="**/important.log" />
    </fileset>
</delete>
```

Các mẫu được tính tương đối với thư mục gốc của FileSet. `**/*.log` chọn tệp log ở các cấp thư mục bên dưới `logs`; `exclude` loại các đường dẫn khớp `important.log`.

Ví dụ khác: chỉ xóa tệp được sinh ra trong thư mục tạm:

```xml
<delete>
    <fileset dir="build/tmp">
        <include name="**/*" />
    </fileset>
</delete>
```

Ở đây, phạm vi quét đã được giới hạn vào `build/tmp`. Cách giới hạn `dir` giúp tránh vô tình áp dụng một mẫu rộng lên toàn bộ dự án.

### 3.2. Xóa các thư mục rỗng

Khi xóa tệp bằng FileSet, các thư mục con có thể trở thành thư mục rỗng. Mặc định, task `delete` không xóa các thư mục rỗng đó chỉ vì chúng không còn tệp.

Thuộc tính `includeEmptyDirs="true"` cho phép xóa cả các thư mục rỗng được chọn trong quá trình xử lý FileSet:

```xml
<delete includeEmptyDirs="true">
    <fileset dir="build/tmp">
        <include name="**/*.tmp" />
    </fileset>
</delete>
```

Nếu cần xóa toàn bộ thư mục `build/tmp`, kể cả các thư mục con và mọi nội dung còn lại, cách trực tiếp là:

```xml
<delete dir="build/tmp" />
```

Hãy phân biệt hai ý định: xóa các tệp khớp mẫu và có thể dọn thư mục con rỗng bằng FileSet; hoặc xóa toàn bộ cây thư mục bằng `dir`.

### 3.3. Mẫu loại trừ mặc định

FileSet có các mẫu loại trừ mặc định (`defaultexcludes`) để bỏ qua một số tệp phụ trợ thường gặp, ví dụ dữ liệu quản lý phiên bản hoặc tệp tạm. Có thể bật hoặc tắt bằng thuộc tính `defaultexcludes` của FileSet:

```xml
<delete>
    <fileset dir="build" defaultexcludes="yes">
        <include name="**/*.tmp" />
    </fileset>
</delete>
```

Thông thường nên giữ hành vi mặc định. Chỉ tắt các default excludes khi có lý do rõ ràng và đã xác định được những tệp sẽ bị tác động.

## 4. Các thuộc tính hữu ích của task `delete`

Task `<delete>` có một số thuộc tính giúp kiểm soát thông báo và cách xử lý khi thao tác xóa thất bại.

| Thuộc tính | Ý nghĩa | Giá trị thường dùng |
|---|---|---|
| `file` | Tệp cụ thể cần xóa. | Đường dẫn tệp. |
| `dir` | Thư mục cần xóa cùng nội dung bên trong. | Đường dẫn thư mục. |
| `includeEmptyDirs` | Cho phép xóa các thư mục rỗng được chọn khi xử lý FileSet. | `true` hoặc `false` (mặc định `false`). |
| `failonerror` | Quyết định build có thất bại khi thao tác xóa gặp lỗi hay không. | `true` (mặc định) hoặc `false`. |
| `quiet` | Giảm thông báo lỗi khi xóa thất bại; hữu ích khi kết hợp với `failonerror="false"`. | `true` hoặc `false`. |
| `verbose` | Hiển thị chi tiết hơn các mục bị xóa. | `true` hoặc `false`. |

### 4.1. `failonerror`

Mặc định, nếu Ant không xóa được mục cần xóa, task báo lỗi và build thất bại. Có thể thay đổi hành vi bằng `failonerror="false"`:

```xml
<delete dir="build/cache" failonerror="false" />
```

Khi đó, lỗi xóa không làm task buộc build thất bại. Cách này có thể phù hợp với thư mục cache tùy chọn, nhưng cần thận trọng với đầu ra bắt buộc phải được dọn sạch. Nếu xóa thất bại mà build vẫn tiếp tục, các tệp cũ có thể còn sót và ảnh hưởng kết quả.

### 4.2. `quiet`

`quiet="true"` giảm các thông báo lỗi khi xóa thất bại. Thuộc tính này hữu ích khi đã quyết định không làm build thất bại vì lỗi xóa:

```xml
<delete file="build/optional.cache"
        failonerror="false"
        quiet="true" />
```

Không nên dùng `quiet` để che giấu lỗi ở một bước dọn dẹp bắt buộc. Khi cần biết vì sao xóa thất bại, hãy giữ thông báo và kiểm tra quyền truy cập, tệp đang được sử dụng hoặc thuộc tính chỉ đọc.

### 4.3. `verbose`

Khi cần xem Ant đang xóa những mục nào, có thể bật `verbose`:

```xml
<delete dir="build" verbose="true" />
```

Thông tin chi tiết hữu ích khi điều tra vì sao một thư mục hoặc tệp vẫn còn sau target `clean`.

## 5. Thiết kế target `clean` và `init`

Trong dự án Ant, `clean` thường xóa sản phẩm được sinh ra; `init` chuẩn bị các thư mục cần thiết cho lần build mới.

Ví dụ đầy đủ:

```xml
<project name="file-operations" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="resources.out.dir" location="${build.dir}/resources" />

    <target name="clean" description="Remove generated output">
        <delete dir="${build.dir}" />
    </target>

    <target name="init" description="Create output directories">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${resources.out.dir}" />
    </target>

    <target name="compile" depends="init" description="Compile Java sources">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false" />
    </target>
</project>
```

Các lệnh thường dùng:

```bash
ant clean
ant compile
```

`ant clean` xóa thư mục đầu ra. `ant compile` tạo lại thư mục cần thiết qua target `init`, rồi biên dịch mã nguồn.

### 5.1. Target build sạch từ đầu

Nếu muốn có một target thực hiện dọn dẹp trước rồi chuẩn bị lại thư mục, có thể tạo target trung gian:

```xml
<target name="clean-build" depends="clean,init">
    <echo message="Output directories are ready" />
</target>
```

Khi chạy `ant clean-build`, Ant thực hiện `clean`, sau đó `init`, rồi mới chạy task trong `clean-build`.

Nếu muốn target `compile` luôn bắt đầu bằng việc xóa kết quả cũ, có thể tạo target riêng cho quy trình đó:

```xml
<target name="compile-clean" depends="clean,compile" />
```

Tuy nhiên, hãy cân nhắc mục đích của target. Không phải mọi lần biên dịch đều cần xóa toàn bộ đầu ra; task `javac` có cơ chế kiểm tra tệp nguồn thay đổi để tránh biên dịch lại không cần thiết. Tách target `clean` để người dùng chủ động gọi giúp quy trình linh hoạt hơn.

## 6. Giữ phạm vi xóa an toàn và dễ hiểu

`delete` có thể xóa cả một cây thư mục. Vì vậy, property đường dẫn và cấu trúc target cần được thiết kế rõ ràng.

### 6.1. Dùng property riêng cho thư mục sinh ra

Ví dụ:

```xml
<property name="build.dir" location="build" />
<property name="dist.dir" location="dist" />

<target name="clean">
    <delete dir="${build.dir}" />
    <delete dir="${dist.dir}" />
</target>
```

Ở đây, `build.dir` và `dist.dir` được dành riêng cho đầu ra có thể tái tạo. Nếu `dist` chứa tài liệu hoặc tệp do người dùng quản lý, không nên đưa toàn bộ thư mục đó vào target `clean`.

### 6.2. Tránh xóa thư mục nguồn

Không đặt một property dùng chung cho cả thư mục nguồn và thư mục đầu ra. Ví dụ, nếu `src.dir` là `src`, target `clean` không nên xóa `${src.dir}`.

Nên phân biệt rõ:

| Nhóm thư mục | Ví dụ | Xử lý trong `clean` |
|---|---|---|
| Mã nguồn | `src`, `test` | Giữ nguyên. |
| Cấu hình đầu vào | `config`, `build.xml` | Giữ nguyên. |
| Kết quả biên dịch | `build/classes` | Có thể xóa. |
| Tệp tạm | `build/tmp` | Có thể xóa. |
| Sản phẩm phát hành | `dist` | Chỉ xóa nếu dự án xác định đây là đầu ra có thể tạo lại. |

### 6.3. Kiểm tra property đường dẫn trước khi xóa

Nếu property có thể được truyền từ dòng lệnh, hãy chắc chắn giá trị của nó trỏ đến thư mục đầu ra dự kiến. Ví dụ:

```bash
ant -Dbuild.dir=build-ci clean
```

Lệnh trên chỉ nên được dùng khi `build-ci` thực sự là thư mục đầu ra cần dọn. Vì `delete dir` xóa đệ quy, một giá trị property quá rộng hoặc sai có thể gây mất dữ liệu ngoài dự kiến.

Trong môi trường phát triển, có thể bật `verbose="true"` để quan sát các mục bị xóa. Khi cần kiểm tra một FileSet, hãy thử sao chép các mục được chọn sang một thư mục kiểm tra hoặc liệt kê chúng bằng task phù hợp trước khi thay thao tác bằng `delete`.

## 7. Xử lý một số tình huống thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thư mục không xuất hiện sau `mkdir` | Property hoặc đường dẫn `dir` không đúng, hoặc task chưa được gọi. | Kiểm tra target được yêu cầu, `depends` và giá trị đường dẫn. |
| Lệnh clean báo không xóa được tệp | Tệp đang được tiến trình khác sử dụng, thiếu quyền hoặc tệp chỉ đọc. | Đóng tiến trình sử dụng tệp, kiểm tra quyền và thuộc tính tệp. |
| Tệp cũ vẫn còn sau khi dùng FileSet | Mẫu `include` không khớp hoặc thư mục gốc không đúng. | Kiểm tra `dir`, mẫu `**` và đường dẫn tương đối. |
| Thư mục con rỗng vẫn còn | FileSet chỉ xóa tệp; `includeEmptyDirs` đang tắt. | Bật `includeEmptyDirs="true"` hoặc xóa cả cây bằng `dir` nếu đó là mục tiêu. |
| Build tiếp tục dù dọn dẹp thất bại | `failonerror="false"` đã cho phép bỏ qua lỗi. | Kiểm tra log và cân nhắc để `failonerror` mặc định là `true` với đầu ra bắt buộc. |
| Target clean xóa nhầm dữ liệu | Property đầu ra trỏ sai hoặc phạm vi `dir` quá rộng. | Tách property, giới hạn đường dẫn và xem lại các giá trị được truyền từ dòng lệnh. |
| Build tạo thư mục nhưng compile không chạy | Target được yêu cầu chỉ là `init`, hoặc target compile không phụ thuộc init. | Gọi đúng target hoặc khai báo `depends` phù hợp. |

## 8. Ví dụ tổng hợp: clean, init, compile và package

Ví dụ dưới đây mô tả một quy trình build nhỏ. Các thư mục đầu ra được gom dưới `build`, target `clean` xóa kết quả cũ, `init` tạo lại cấu trúc, `compile` biên dịch mã nguồn và `package` đóng gói JAR.

```xml
<project name="mkdir-delete-demo" default="package" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="${build.dir}/dist" />

    <target name="clean" description="Remove generated files">
        <delete dir="${build.dir}" />
    </target>

    <target name="init" description="Create output folders">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="compile" depends="init" description="Compile source files">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile" description="Create application JAR">
        <jar destfile="${dist.dir}/app.jar" basedir="${classes.dir}" />
    </target>

    <target name="rebuild" depends="clean,package">
        <echo message="Clean rebuild completed" />
    </target>
</project>
```

Luồng chạy mặc định:

```text
ant
 |
 v
package
 |
 v
compile
 |
 v
init
 |
 +-- mkdir build/classes
 +-- mkdir build/dist
 |
 v
javac
 |
 v
jar
```

Chạy các lệnh:

```bash
ant clean
ant package
ant rebuild
```

- `ant clean` xóa đầu ra trong `build`.
- `ant package` tạo thư mục đầu ra nếu cần, biên dịch rồi đóng gói.
- `ant rebuild` thực hiện target `clean` trước, sau đó xử lý phụ thuộc của `package` và tạo lại sản phẩm.

Trong một lần gọi Ant, target chỉ được thực hiện tối đa một lần. Vì vậy, khi `rebuild` yêu cầu `clean` và `package`, target `clean` không bị chạy lại nếu đã được xử lý trong cùng lần gọi. Sau `clean`, `package` yêu cầu `compile`, rồi `compile` yêu cầu `init`, nên các thư mục được tạo lại trước khi biên dịch.

## 9. Bài thực hành

Tạo dự án có cấu trúc:

```text
file-lab/
├── build.xml
├── src/
│   └── Hello.java
├── resources/
│   └── app.properties
└── build/
    ├── classes/
    ├── tmp/
    └── reports/
```

Tạo lớp `src/Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
```

Hãy viết `build.xml` với các yêu cầu:

1. Khai báo property `build.dir`, `classes.dir`, `resources.out.dir` và `reports.dir`.
2. Tạo target `init` dùng `mkdir` để chuẩn bị tất cả thư mục đầu ra.
3. Tạo target `compile` phụ thuộc `init`, dùng `javac` biên dịch `Hello.java`.
4. Tạo target `copy-resources` phụ thuộc `init`, sao chép `resources/app.properties` vào thư mục tài nguyên đầu ra.
5. Tạo target `clean` dùng `delete dir` để xóa toàn bộ thư mục đầu ra.
6. Tạo target `clean-temp` dùng FileSet để chỉ xóa các tệp `.tmp` trong `build/tmp`.
7. Tạo target `clean-build` phụ thuộc `clean` và `init` để xóa rồi tạo lại cấu trúc thư mục.

Gợi ý cho target xóa có chọn lọc:

```xml
<target name="clean-temp">
    <delete>
        <fileset dir="${build.dir}/tmp">
            <include name="**/*.tmp" />
        </fileset>
    </delete>
</target>
```

Gợi ý cho target chuẩn bị thư mục:

```xml
<target name="init">
    <mkdir dir="${classes.dir}" />
    <mkdir dir="${resources.out.dir}" />
    <mkdir dir="${reports.dir}" />
    <mkdir dir="${build.dir}/tmp" />
</target>
```

Sau khi hoàn thành, chạy `ant clean-build`, kiểm tra cây thư mục, sau đó chạy `ant compile`. Tạo một vài tệp `.tmp` và `.txt` trong `build/tmp`, chạy `ant clean-temp` rồi xác nhận chỉ các tệp `.tmp` được chọn để xóa.

### Câu hỏi tự kiểm tra

1. Task `<mkdir>` nhận thuộc tính nào để xác định thư mục cần tạo?
2. Khi thư mục cha chưa tồn tại, `mkdir` có thể tạo cả cây thư mục không?
3. Khác biệt giữa `<delete file="..." />` và `<delete dir="..." />` là gì?
4. Khi xóa bằng FileSet, vì sao thư mục gốc có thể vẫn còn sau khi các tệp đã bị xóa?
5. `includeEmptyDirs="true"` có tác dụng gì?
6. `failonerror="false"` ảnh hưởng thế nào đến kết quả build khi thao tác xóa thất bại?
7. Vì sao nên dành riêng một thư mục cho đầu ra có thể xóa và giữ mã nguồn ở thư mục khác?
8. Target `clean-build` cần phụ thuộc vào những target nào để xóa trước rồi tạo lại thư mục?

### Đáp án gợi ý

- `mkdir` dùng thuộc tính `dir` để chỉ định thư mục cần tạo.
- Có. Ant tạo các thư mục cha còn thiếu để hoàn thành đường dẫn.
- `file` xóa một tệp cụ thể; `dir` xóa thư mục cùng nội dung bên trong.
- FileSet chọn các tệp; việc xóa tệp không mặc định đồng nghĩa xóa toàn bộ cây thư mục.
- Thuộc tính này cho phép xóa cả các thư mục rỗng được chọn trong khi xử lý FileSet.
- Build không bị đánh dấu thất bại chỉ vì lỗi xóa đó, nên cần xem xét nguy cơ đầu ra cũ còn sót.
- Tách nguồn và đầu ra giúp target `clean` chỉ tác động đến dữ liệu có thể tái tạo.
- `clean-build` nên phụ thuộc `clean,init` để dọn dẹp trước rồi chuẩn bị thư mục.

## Kết luận

Task `<mkdir>` tạo thư mục và các thư mục cha còn thiếu; task `<delete>` xóa tệp, thư mục hoặc các mục được chọn bằng FileSet. Dùng `dir` khi cần xóa toàn bộ cây đầu ra, dùng `file` khi chỉ xóa một tệp và dùng `include`/`exclude` khi cần xóa có chọn lọc. Các thuộc tính `includeEmptyDirs`, `failonerror`, `quiet` và `verbose` giúp kiểm soát phạm vi và cách task phản hồi khi có lỗi. Hãy gom đầu ra vào những thư mục riêng, khai báo property rõ ràng và tổ chức target `clean`/`init` để quy trình build có thể lặp lại an toàn.

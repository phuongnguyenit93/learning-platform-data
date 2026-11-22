# Gọi target cùng buildfile bằng antcall và phân biệt với depends

Trong Apache Ant, một build file thường có nhiều target như `clean`, `compile`, `test`, `package` và `release`. Các target có thể phụ thuộc vào nhau hoặc gọi một target khác để thực hiện một phần công việc. Hai cơ chế dễ bị nhầm lẫn là thuộc tính `depends` của target và task `antcall`.

Cả hai đều có thể khiến một target khác được chạy, nhưng chúng phục vụ hai cách tổ chức build khác nhau:

- `depends` khai báo quan hệ phụ thuộc trong cùng một build graph. Target phụ thuộc được chạy trước target hiện tại trong cùng project invocation.
- `antcall` gọi một target khác trong cùng build file thông qua một project context mới. Nó có thể truyền property cho lần gọi đó và phù hợp với quy trình cần chạy lại target với cấu hình riêng.

Chọn đúng cơ chế giúp build file dễ hiểu, tránh chạy lặp không cần thiết và tránh nhầm lẫn về property hoặc reference được chia sẻ giữa các target.

## 1. Target và quan hệ phụ thuộc trong Ant

Target là một đơn vị công việc có tên trong build file. Ví dụ:

```xml
<project name="sample-app" default="package">

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src" destdir="build/classes"/>
    </target>

    <target name="package">
        <jar destfile="dist/sample-app.jar" basedir="build/classes"/>
    </target>

</project>
```

Trong ví dụ này, ba target độc lập về mặt khai báo. Nếu chạy `ant package`, Ant chỉ chạy target `package`; nó không tự suy ra rằng phải chạy `clean` hoặc `compile` trước.

Để mô tả thứ tự công việc, bạn có thể khai báo quan hệ phụ thuộc bằng `depends`:

```xml
<target name="package" depends="compile">
    <mkdir dir="dist"/>
    <jar destfile="dist/sample-app.jar" basedir="build/classes"/>
</target>
```

Khi chạy `ant package`, Ant thực hiện `compile` trước rồi mới chạy nội dung của `package`.

Đây là cách thông thường để mô tả pipeline build: target nói rõ điều kiện tiên quyết của nó, còn Ant sắp xếp việc thực thi theo quan hệ phụ thuộc.

## 2. Dùng depends để khai báo prerequisite

Thuộc tính `depends` nhận danh sách tên target, phân tách bằng dấu phẩy:

```xml
<target name="compile">
    <echo message="Compile source"/>
</target>

<target name="test" depends="compile">
    <echo message="Run tests"/>
</target>

<target name="package" depends="compile,test">
    <echo message="Create archive"/>
</target>
```

Khi chạy:

```bash
ant package
```

Ant bảo đảm các prerequisite được thực hiện trước target `package`. Vì `test` cũng phụ thuộc vào `compile`, target `compile` không bị chạy lại lần thứ hai trong cùng project invocation.

Có thể biểu diễn quan hệ:

```text
package
  |
  +-- compile
  |
  +-- test
        |
        +-- compile
```

Mặc dù `compile` xuất hiện ở hai nhánh, Ant chỉ thực hiện target đó một lần trong cùng build invocation. Các target được xử lý theo thứ tự phụ thuộc; danh sách trong `depends` được viết theo thứ tự mà bạn muốn Ant xét các prerequisite.

### Đặc điểm của depends

- Quan hệ phụ thuộc được khai báo tĩnh trong thuộc tính `depends`.
- Các prerequisite chạy trước target phụ thuộc.
- Tất cả target chạy trong cùng project context.
- Property được thiết lập trong một prerequisite có thể được target chạy sau sử dụng.
- Một target chỉ được thực hiện một lần trong cùng project invocation, kể cả khi nhiều target phụ thuộc vào nó.
- `depends` không có cơ chế truyền tham số riêng cho từng lần chạy target.

Nếu mục tiêu chỉ là bảo đảm `compile` chạy trước `package`, `depends` thường là lựa chọn phù hợp nhất.

## 3. antcall là gì?

`antcall` là task dùng để gọi một target khác trong **cùng build file**. Khác với `depends`, lời gọi này được thực hiện như một lần chạy project mới, với project context riêng.

Cú pháp cơ bản:

```xml
<target name="build-all">
    <antcall target="compile"/>
</target>
```

Trong đó:

- `target` là tên target muốn gọi.
- Task `antcall` nằm trong phần thân của một target đang thực thi.
- Target được gọi vẫn thuộc build file hiện tại.
- Ant tạo project context mới cho lần gọi; các property và reference được truyền theo quy tắc của `antcall`.

Ví dụ:

```xml
<project name="antcall-demo" default="build-all">

    <target name="compile">
        <echo message="Compile in called target"/>
    </target>

    <target name="build-all">
        <echo message="Start build-all"/>
        <antcall target="compile"/>
        <echo message="Finish build-all"/>
    </target>

</project>
```

Chạy `ant build-all` sẽ thực hiện phần thân `build-all`, gọi target `compile`, rồi quay lại tiếp tục phần còn lại của `build-all`.

### antcall không phải lời gọi hàm Java

`antcall` có hình thức giống một lời gọi hàm, nhưng không có đầy đủ ngữ nghĩa của hàm:

- Không có giá trị trả về trực tiếp cho target gọi.
- Không dùng chung project context với target gọi.
- Property được tạo trong project được gọi không tự động quay về project gọi.
- Có thể truyền property vào project được gọi bằng nested `param`.
- Target được gọi có thể chạy lại trong một project invocation mới.

Hãy xem `antcall` như một lần thực thi build lồng bên trong build hiện tại, thay vì một phương thức có thể trả kết quả.

## 4. Truyền tham số cho target bằng nested param

Một điểm hữu ích của `antcall` là có thể truyền property riêng cho target được gọi thông qua nested element `<param>`.

Ví dụ:

```xml
<project name="multi-module" default="build-all" basedir=".">

    <target name="build-all">
        <antcall target="build-module">
            <param name="module.name" value="core"/>
        </antcall>

        <antcall target="build-module">
            <param name="module.name" value="web"/>
        </antcall>
    </target>

    <target name="build-module">
        <echo message="Building module: ${module.name}"/>
        <echo message="Source: modules/${module.name}/src"/>
    </target>

</project>
```

Hai lần gọi truyền giá trị khác nhau cho property `module.name`. Target `build-module` có thể sử dụng cùng một cấu hình để xử lý từng module.

Khi chạy `ant build-all`, lần gọi thứ nhất nhận `core`, lần gọi thứ hai nhận `web`. Mỗi lần gọi có project context riêng nên có thể sử dụng cùng target với bộ property đầu vào khác nhau.

### Các thuộc tính thường dùng của param

```xml
<antcall target="build-module">
    <param name="module.name" value="core"/>
    <param name="module.output" location="build/core"/>
</antcall>
```

- `name` là tên property trong project được gọi.
- `value` truyền một giá trị dạng chuỗi.
- `location` truyền một đường dẫn đã được Ant xử lý theo quy tắc location.

Hãy dùng tên property có ý nghĩa rõ ràng như `module.name`, `module.output` hoặc `release.channel` để target được gọi dễ hiểu.

### Tránh xung đột tên property

Ant property có tính bất biến: một khi đã được thiết lập trong một project, lệnh khai báo property thông thường tiếp theo không thay thế giá trị cũ.

Theo mặc định, `antcall` kế thừa các property từ project gọi. Vì vậy, nếu project cha đã có property `module.name`, truyền một `<param name="module.name" .../>` với ý định thay giá trị có thể không cho kết quả bạn mong đợi do property đã được kế thừa.

Để tránh nhầm lẫn:

- Dùng tên property riêng cho tham số của target được gọi.
- Không khai báo sẵn cùng tên trong project cha nếu muốn mỗi lần gọi nhận giá trị riêng.
- Hoặc đặt `inheritAll="false"` khi muốn hạn chế việc truyền các property thông thường của project cha, rồi truyền tường minh những giá trị target cần.

Ví dụ:

```xml
<antcall target="build-module" inheritAll="false">
    <param name="module.name" value="core"/>
    <param name="release.version" value="2.4.0"/>
</antcall>
```

Khi `inheritAll="false"`, các property thông thường của project cha không được truyền toàn bộ sang project mới; user property từ dòng lệnh vẫn được kế thừa theo cơ chế của Ant. Vì vậy, nếu target được gọi cần một property cấu hình khác, hãy truyền nó rõ ràng bằng `param` hoặc thiết lập giá trị mặc định trong build file.

## 5. Kế thừa property với inheritAll

`antcall` có thuộc tính `inheritAll` để điều khiển việc truyền property từ project gọi sang project được tạo:

| Giá trị | Hành vi |
|---|---|
| `true` | Kế thừa toàn bộ property từ project gọi; đây là mặc định |
| `false` | Không kế thừa toàn bộ property thông thường; các user property được truyền từ dòng lệnh vẫn có thể được kế thừa |

Ví dụ mặc định:

```xml
<property name="release.version" value="2.4.0"/>

<target name="show-version">
    <echo message="Version: ${release.version}"/>
</target>

<target name="release">
    <antcall target="show-version"/>
</target>
```

Vì `inheritAll` mặc định là `true`, target `show-version` có thể đọc property `release.version` từ project gọi.

Nếu thay bằng:

```xml
<target name="release">
    <antcall target="show-version" inheritAll="false"/>
</target>
```

thì property thông thường được khai báo trong project cha không còn được truyền toàn bộ. Target được gọi cần tự thiết lập giá trị mặc định hoặc nhận property qua `param`.

### Khi nào nên dùng inheritAll="false"?

Dùng khi target được gọi cần một môi trường property có giới hạn, hoặc khi bạn muốn xác định rõ những giá trị đầu vào thay vì phụ thuộc vào toàn bộ trạng thái của project gọi.

Tuy nhiên, không nên đặt `inheritAll="false"` một cách máy móc. Nếu target được gọi phụ thuộc vào nhiều property chung của build, bạn phải truyền hoặc khai báo lại các giá trị đó. Hãy chọn dựa trên mức độ độc lập mà target cần.

## 6. Reference và inheritRefs

Ngoài property, build file có thể chứa reference như path datatype, fileset hoặc đối tượng dữ liệu được đăng ký bằng `id`.

Ví dụ:

```xml
<path id="shared.classpath">
    <pathelement location="lib/application-api.jar"/>
</path>
```

Reference không được kế thừa mặc định qua `antcall`. Thuộc tính `inheritRefs` điều khiển việc truyền reference:

| Giá trị | Hành vi |
|---|---|
| `true` | Kế thừa các reference của project gọi |
| `false` | Không tự động kế thừa reference; đây là mặc định |

Có thể bật kế thừa:

```xml
<antcall target="compile-module" inheritRefs="true">
    <param name="module.name" value="core"/>
</antcall>
```

Hoặc truyền reference cụ thể bằng nested `<reference>`:

```xml
<antcall target="compile-module">
    <param name="module.name" value="core"/>
    <reference refid="shared.classpath"/>
</antcall>
```

Nested `reference` có thể dùng `torefid` nếu muốn đăng ký reference dưới một tên khác trong project được gọi:

```xml
<antcall target="compile-module">
    <reference
        refid="shared.classpath"
        torefid="module.classpath"/>
</antcall>
```

Khi truyền reference, hãy kiểm tra tài liệu Ant và datatype/task đang dùng để bảo đảm đối tượng đó có thể được chia sẻ theo cách mong muốn. Với path hoặc cấu hình đơn giản, đôi khi định nghĩa lại trong project được gọi sẽ dễ hiểu hơn việc truyền một reference phức tạp.

## 7. Dependencies của target được gọi cũng được thực hiện

Khi `antcall` gọi một target có `depends`, Ant cũng thực hiện các prerequisite của target đó trong project context mới.

Ví dụ:

```xml
<target name="prepare-module">
    <echo message="Prepare module environment"/>
</target>

<target name="compile-module" depends="prepare-module">
    <echo message="Compile module ${module.name}"/>
</target>

<target name="build-all">
    <antcall target="compile-module">
        <param name="module.name" value="core"/>
    </antcall>
</target>
```

Khi `build-all` gọi `compile-module`, Ant chạy `prepare-module` trong project được gọi trước khi chạy `compile-module`.

Nếu `build-all` gọi `compile-module` hai lần, mỗi lần là một project invocation riêng. Vì thế, prerequisite có thể được chạy lại trong từng lần gọi. Đây là khác biệt quan trọng so với `depends`, nơi một prerequisite chỉ được thực hiện một lần trong cùng project invocation.

Không nên đặt các thao tác tốn thời gian hoặc có tác động phụ lớn trong prerequisite của target được `antcall` lặp nhiều lần nếu bạn không muốn chúng chạy lại.

## 8. So sánh trực tiếp antcall và depends

| Tiêu chí | `depends` | `antcall` |
|---|---|---|
| Cách khai báo | Thuộc tính của target | Task nằm trong thân target |
| Mục đích chính | Khai báo prerequisite | Gọi target trong cùng build file |
| Project context | Dùng chung project invocation | Tạo project context mới cho lần gọi |
| Truyền tham số | Không có tham số riêng cho mỗi prerequisite | Có nested `param` để truyền property |
| Property từ target được gọi | Được thiết lập trong cùng project và có thể dùng ở target sau | Property được tạo trong project con không tự quay về project gọi |
| Reference | Dùng chung trong project | Không kế thừa mặc định; có `inheritRefs` hoặc nested `reference` |
| Chạy lặp | Một target chỉ chạy một lần trong cùng project invocation | Mỗi lần gọi có project invocation riêng, nên target có thể chạy lại |
| Dependency của target | Chạy trước target phụ thuộc | Dependency của target được gọi cũng chạy trong project con |
| Chi phí và độ phức tạp | Thường đơn giản và nhẹ hơn | Tạo project context mới, cần chú ý truyền property/reference |
| Trường hợp phù hợp | `compile` trước `test`, `test` trước `package` | Cùng một target cần chạy nhiều lần với bộ property đầu vào riêng |

### Quy tắc lựa chọn nhanh

Hãy dùng `depends` khi bạn đang mô tả thứ tự bắt buộc của quy trình:

```xml
<target name="test" depends="compile"/>
<target name="package" depends="test"/>
<target name="release" depends="package"/>
```

Hãy cân nhắc `antcall` khi bạn thực sự cần gọi lại cùng một target trong project context riêng, chẳng hạn dùng chung logic build cho nhiều module với property đầu vào khác nhau:

```xml
<target name="build-all">
    <antcall target="build-module">
        <param name="module.name" value="core"/>
    </antcall>
    <antcall target="build-module">
        <param name="module.name" value="web"/>
    </antcall>
</target>
```

Không nên dùng `antcall` chỉ để thay thế một quan hệ prerequisite đơn giản. Việc đó làm build khó theo dõi hơn và có thể khiến prerequisite bị chạy nhiều lần.

## 9. Ví dụ: cùng một target xử lý nhiều module

Giả sử repository có:

```text
workspace/
├── build.xml
├── modules/
│   ├── core/
│   │   └── src/
│   ├── web/
│   │   └── src/
│   └── cli/
│       └── src/
└── build/
```

Bạn muốn tái sử dụng một target để xử lý từng module:

```xml
<project name="multi-module" default="build-all" basedir=".">

    <property name="modules.dir" location="modules"/>
    <property name="build.dir" location="build"/>

    <target name="build-all">
        <antcall target="build-module">
            <param name="module.name" value="core"/>
        </antcall>

        <antcall target="build-module">
            <param name="module.name" value="web"/>
        </antcall>

        <antcall target="build-module">
            <param name="module.name" value="cli"/>
        </antcall>
    </target>

    <target name="build-module">
        <property
            name="module.src.dir"
            location="${modules.dir}/${module.name}/src"/>
        <property
            name="module.classes.dir"
            location="${build.dir}/${module.name}/classes"/>

        <mkdir dir="${module.classes.dir}"/>
        <javac
            srcdir="${module.src.dir}"
            destdir="${module.classes.dir}"
            includeantruntime="false"
            encoding="UTF-8"/>

        <echo message="Built module ${module.name}"/>
    </target>

</project>
```

Mỗi lần gọi `build-module` nhận một `module.name` khác nhau. Vì mỗi lần `antcall` tạo project context riêng, các property được thiết lập bên trong target có phạm vi của lần gọi đó; lần gọi tiếp theo có thể tính đường dẫn cho module khác.

Ví dụ này phù hợp khi các module có cùng quy trình cơ bản nhưng cần đầu vào riêng. Trong dự án thực tế, bạn có thể bổ sung classpath, resource copy hoặc target kiểm thử cho từng module.

### Chú ý về thư mục output

Project context mới không có nghĩa là hệ thống tệp được cô lập. Nếu hai lần gọi ghi vào cùng một thư mục output, chúng vẫn có thể ghi đè dữ liệu của nhau. Hãy tạo output directory theo module hoặc build ID, như `${build.dir}/${module.name}`, để tách kết quả.

## 10. Ví dụ: depends phù hợp hơn cho pipeline thông thường

Với một ứng dụng đơn, quy trình chuẩn thường không cần `antcall`:

```xml
<project name="single-app" default="release" basedir=".">

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac
            srcdir="src/main/java"
            destdir="build/classes"
            includeantruntime="false"
            encoding="UTF-8"/>
    </target>

    <target name="test" depends="compile">
        <echo message="Run unit tests"/>
    </target>

    <target name="package" depends="test">
        <mkdir dir="dist"/>
        <jar
            destfile="dist/single-app.jar"
            basedir="build/classes"/>
    </target>

    <target name="release" depends="package">
        <echo message="Release package is ready"/>
    </target>

</project>
```

Khi chạy `ant release`, Ant tự xử lý chuỗi prerequisite:

```text
compile -> test -> package -> release
```

Mỗi target chạy trong cùng project context. Property, path reference và trạng thái build được chia sẻ theo quy tắc thông thường của Ant. Đây là cách biểu đạt ngắn gọn, trực tiếp cho một pipeline có thứ tự cố định.

Nếu muốn `release` luôn chạy `clean` trước, có thể thêm `clean` vào dependency graph, nhưng hãy chú ý thứ tự: `clean` không được chạy sau `compile` hoặc xóa output trước khi đóng gói.

## 11. Các giới hạn và lỗi thường gặp khi dùng antcall

### Mong đợi property từ target con quay về target cha

Project được gọi là một project context riêng. Nếu target con thiết lập property:

```xml
<target name="child">
    <property name="generated.value" value="hello"/>
</target>

<target name="parent">
    <antcall target="child"/>
    <echo message="${generated.value}"/>
</target>
```

Không nên kỳ vọng `parent` nhìn thấy `generated.value` do `child` tạo ra. Property được thiết lập trong project con không tự động truyền ngược về project cha.

Nếu cần truyền kết quả giữa các giai đoạn, hãy dùng cơ chế phù hợp như ghi ra file properties rồi nạp lại, tạo artifact hoặc dùng task có cơ chế output rõ ràng. Không nên xem `antcall` như hàm trả về giá trị.

### Dùng antcall cho prerequisite đơn giản

Nếu target `package` chỉ cần `compile` chạy trước, hãy viết `depends="compile"`. Gọi `<antcall target="compile"/>` trong thân target tạo thêm project context và có thể khiến `compile` chạy lại, trong khi quan hệ prerequisite đã diễn đạt đúng ý định.

### Quên dependency của target được gọi

Target được gọi có thể có `depends` riêng. Các prerequisite đó cũng chạy trong project context mới. Nếu prerequisite xóa hoặc tạo lại thư mục, thao tác có thể lặp ở mỗi lần gọi.

### Nhầm property kế thừa với param

Mặc định `inheritAll="true"` truyền các property của project gọi. Vì property bất biến, tham số trùng tên với property đã kế thừa không phải cách an toàn để thay giá trị. Dùng tên tham số riêng hoặc cân nhắc `inheritAll="false"`.

### Giả định reference tự được truyền

Reference không tự kế thừa mặc định. Nếu target con cần path hoặc reference khác, hãy truyền bằng `inheritRefs="true"`, nested `<reference>` hoặc khai báo lại reference trong build file.

### Tạo lời gọi đệ quy không có điểm dừng

Một target có thể gọi lại chính nó trực tiếp hoặc gián tiếp thông qua target khác. Vì mỗi `antcall` tạo project context mới, cơ chế phát hiện vòng lặp dependency của một project invocation không thay thế được điều kiện dừng cho chuỗi lời gọi này. Nếu không có điều kiện kết thúc, build có thể gọi lặp vô hạn.

Hãy vẽ luồng gọi target trước khi tạo các lời gọi lồng nhau và tránh thiết kế vòng gọi không có điểm dừng rõ ràng.

### Nhiều lần gọi ghi vào cùng output

Project context riêng không tạo thư mục riêng tự động. Nếu nhiều lần gọi dùng cùng `destdir`, `dist` hoặc file đích, chúng có thể ghi đè kết quả. Hãy truyền tên module hoặc build ID và tạo output path riêng.

## 12. Khi nào nên tách sang build file khác?

`antcall` chỉ gọi target trong cùng build file. Nếu muốn chạy một build file khác, Ant có task `<ant>`; nếu muốn áp dụng một build file lên nhiều thư mục con, có thể xem xét `<subant>`.

Ví dụ gọi build file khác:

```xml
<target name="build-library">
    <ant
        antfile="modules/library/build.xml"
        target="package"
        dir="modules/library"/>
</target>
```

Ở đây `antfile` chỉ định build file cần chạy và `dir` chỉ định thư mục làm việc của build đó. Đây là trường hợp khác với `antcall`, vì target được gọi không thuộc build file hiện tại.

Hãy chọn:

- `depends` cho prerequisite trong cùng build graph.
- `antcall` cho target khác trong cùng build file, khi cần một project context mới hoặc tham số riêng.
- `ant` cho build file khác.
- `subant` khi cần điều phối cùng một target trên nhiều build file hoặc thư mục con.

## 13. Gợi ý thiết kế build file dễ bảo trì

- Ưu tiên `depends` cho quan hệ prerequisite thông thường.
- Dùng `antcall` khi có lý do cụ thể để gọi target trong project context mới.
- Giữ target được gọi có một trách nhiệm rõ ràng và đầu vào dễ nhận biết.
- Đặt tên property truyền qua `param` theo quy ước nhất quán.
- Kiểm tra `inheritAll` và `inheritRefs` thay vì dựa vào hành vi mặc định mà không hiểu phạm vi.
- Không kỳ vọng property do project con tạo ra sẽ quay về project cha.
- Tránh gọi target lồng nhau quá sâu hoặc tạo vòng gọi không có điểm dừng.
- Tách output directory theo module hoặc lần build nếu gọi target nhiều lần.
- Dùng `ant` hoặc `subant` khi cần chạy build file khác.

## 14. Ghi nhớ

- `depends` khai báo prerequisite; target phụ thuộc được chạy trước trong cùng project invocation.
- Một target chỉ chạy một lần trong cùng project invocation, kể cả khi được nhiều target phụ thuộc.
- `antcall` gọi target trong cùng build file bằng một project context mới.
- Nested `<param>` truyền property vào project được gọi; tránh trùng tên với property đã kế thừa.
- `inheritAll` mặc định là `true`; đặt `false` khi muốn hạn chế property thông thường được truyền sang.
- `inheritRefs` mặc định là `false`; có thể bật hoặc truyền reference cụ thể bằng nested `<reference>`.
- Dependencies của target được gọi cũng được thực hiện trong project context mới.
- Property được tạo trong project con không tự truyền ngược về project gọi.
- Dùng `depends` cho pipeline thông thường; chỉ dùng `antcall` khi cần hành vi gọi target riêng biệt.

Khi tổ chức nhiều target trong Ant, hãy dùng `depends` để mô tả thứ tự prerequisite và dùng `antcall` cho những lần gọi target có chủ đích với project context hoặc property đầu vào riêng. Phân biệt hai cơ chế này giúp build graph rõ ràng, hạn chế chạy lặp và tránh các lỗi do hiểu nhầm phạm vi property hoặc reference.

# Phần tử `project` với `name`, `default` và `basedir`

Trong Apache Ant, tệp `build.xml` mô tả một dự án build bằng XML. Phần tử gốc của tệp là `<project>`. Nó đặt tên cho dự án, xác định target mặc định khi người dùng không chỉ định target trên dòng lệnh và xác định thư mục cơ sở để Ant diễn giải các đường dẫn tương đối.

Ba thuộc tính `name`, `default` và `basedir` giúp người đọc hiểu một buildfile thuộc dự án nào, lệnh `ant` sẽ bắt đầu từ đâu và các thư mục như `src`, `build` hay `dist` được tính từ vị trí nào.

## 1. Cấu trúc cơ bản của phần tử `project`

Một buildfile tối thiểu có thể viết như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="help" basedir=".">

    <target name="help" description="Show project information">
        <echo message="Apache Ant project: sample-app"/>
    </target>

</project>
```

Trong cấu trúc này:

- `project` là phần tử gốc của buildfile.
- `name="sample-app"` đặt tên cho dự án Ant.
- `default="help"` chọn target `help` khi chạy Ant mà không ghi tên target.
- `basedir="."` đặt thư mục cơ sở là thư mục hiện tại của buildfile theo quy tắc phân giải đường dẫn của Ant.
- `target` khai báo một công việc có thể được gọi bằng tên.
- `echo` in thông điệp ra log để minh họa target đã được thực thi.

Phần khai báo XML `<?xml ...?>` thường được đặt ở đầu tệp. Dòng này cho biết đây là tài liệu XML và khai báo encoding; phần tử `<project>` vẫn là phần tử gốc duy nhất của tài liệu.

Các tên phần tử và thuộc tính XML phân biệt chữ hoa, chữ thường. Vì vậy, hãy viết đúng `project`, `name`, `default` và `basedir` như trong ví dụ.

## 2. Thuộc tính `name`

`name` đặt tên nhận diện cho project. Ví dụ:

```xml
<project name="customer-service-build" default="compile" basedir=".">
    <!-- Các target được khai báo bên trong project. -->
</project>
```

Tên này giúp người đọc nhận ra buildfile đang mô tả dự án nào, đặc biệt khi làm việc với nhiều buildfile hoặc xem log của nhiều lần build. Hãy chọn tên ngắn gọn, có ý nghĩa và nhất quán với dự án.

`name` không phải tên target mặc định. Trong ví dụ trên, tên project là `customer-service-build`, còn target mặc định là `compile`. Khi chạy `ant`, Ant tìm target `compile` theo thuộc tính `default`; nó không tìm target có tên trùng với `name`.

Thuộc tính `name` là tùy chọn. Tuy vậy, khai báo tên project thường giúp buildfile dễ đọc và log dễ nhận biết hơn.

## 3. Thuộc tính `default`

`default` chỉ định tên target mà Ant thực thi khi người dùng gọi lệnh `ant` mà không truyền tên target.

```xml
<project name="sample-app" default="prepare" basedir=".">

    <target name="prepare">
        <echo message="Prepare the project"/>
    </target>

    <target name="compile">
        <echo message="Compile source code"/>
    </target>

</project>
```

Với buildfile này:

```sh
ant
```

sẽ gọi target `prepare`, vì `default="prepare"`.

Nếu người dùng chỉ định target:

```sh
ant compile
```

Ant chạy target `compile` được yêu cầu, thay vì target mặc định `prepare`.

Một điểm cần nhớ: target mặc định không có nghĩa là Ant tự chạy tất cả target trong buildfile. Nó chỉ xác định điểm bắt đầu khi không có target nào được truyền trên dòng lệnh. Nếu một target cần target khác chạy trước, hãy khai báo quan hệ phụ thuộc bằng `depends`:

```xml
<project name="sample-app" default="compile" basedir=".">

    <target name="prepare">
        <mkdir dir="build"/>
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile after preparing the output directory"/>
    </target>

</project>
```

Khi chạy `ant`, Ant chọn `compile` làm target mặc định. Vì `compile` phụ thuộc `prepare`, Ant thực hiện `prepare` trước rồi mới thực hiện phần thân của `compile`.

Nếu bỏ thuộc tính `default`, Ant dùng target đầu tiên được khai báo trong buildfile làm target mặc định. Dù vậy, nên ghi rõ `default` để ý định của người viết không phụ thuộc vào thứ tự sắp xếp các target. Giá trị của `default` phải khớp với tên một target có trong buildfile; nếu không, lệnh gọi target mặc định sẽ thất bại.

## 4. Thuộc tính `basedir`

`basedir` xác định thư mục cơ sở của project. Ant dùng thư mục này để phân giải các đường dẫn tương đối trong những thuộc tính và task làm việc với tệp, thư mục.

Ví dụ:

```xml
<project name="sample-app" default="prepare" basedir=".">

    <target name="prepare">
        <mkdir dir="build"/>
        <mkdir dir="build/classes"/>
        <mkdir dir="dist"/>
    </target>

</project>
```

Nếu buildfile nằm ở thư mục gốc dự án, `basedir="."` có nghĩa thư mục cơ sở là thư mục đó. Các đường dẫn `build`, `build/classes` và `dist` vì thế được tính từ thư mục gốc dự án.

Nếu không khai báo `basedir`, Ant mặc định dùng thư mục chứa buildfile làm thư mục cơ sở. Nếu giá trị `basedir` là đường dẫn tương đối, Ant phân giải nó dựa trên thư mục chứa buildfile. Giá trị cũng có thể là đường dẫn tuyệt đối.

Ví dụ về buildfile nằm trong thư mục con:

```text
sample-app/
├── src/
├── build.xml
└── config/
    └── alternate-build.xml
```

Nếu `alternate-build.xml` cần coi `sample-app/` là thư mục gốc, có thể đặt:

```xml
<project name="sample-app" default="prepare" basedir="..">
    <target name="prepare">
        <mkdir dir="build"/>
    </target>
</project>
```

Vì `basedir=".."` được tính từ thư mục chứa `alternate-build.xml`, đường dẫn `build` sẽ trỏ tới `sample-app/build`.

## 5. Phân biệt `basedir` với thư mục làm việc của terminal

Một nhầm lẫn phổ biến là cho rằng đường dẫn tương đối luôn được tính từ thư mục terminal đang đứng. Trong Ant, các đường dẫn tương đối của project được tính từ project base directory.

Giả sử cấu trúc như sau:

```text
workspace/
└── sample-app/
    ├── build.xml
    └── src/
```

Và `build.xml` khai báo:

```xml
<project name="sample-app" default="show-path" basedir=".">
    <target name="show-path">
        <echo message="Base directory: ${basedir}"/>
        <echo message="Source directory: ${basedir}/src"/>
    </target>
</project>
```

Người dùng có thể chạy buildfile từ thư mục `workspace` bằng cách chỉ định đường dẫn:

```sh
ant -f sample-app/build.xml show-path
```

Trong trường hợp này, `basedir="."` vẫn lấy thư mục chứa buildfile làm thư mục cơ sở theo mặc định đã khai báo, nên đường dẫn nguồn là `sample-app/src`. Thư mục làm việc của terminal quyết định cách shell tìm đường dẫn `sample-app/build.xml` trong lệnh trên; nó không tự thay đổi project base directory đã được xác định trong buildfile.

Nếu muốn dùng thư mục terminal hiện tại làm cơ sở, cần cấu hình project phù hợp một cách có chủ đích. Không nên dựa vào việc người dùng luôn chạy Ant từ một thư mục nhất định nếu buildfile có thể được gọi từ nhiều vị trí.

## 6. Sử dụng property `basedir` trong buildfile

Ant cung cấp property `${basedir}` chứa đường dẫn thư mục cơ sở của project. Property này hữu ích khi khai báo các đường dẫn khác dựa trên cùng một gốc.

```xml
<project name="sample-app" default="prepare" basedir=".">

    <property name="src.dir" location="${basedir}/src"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <target name="prepare">
        <mkdir dir="${build.dir}"/>
        <mkdir dir="${dist.dir}"/>
        <echo message="Source directory: ${src.dir}"/>
    </target>

</project>
```

Trong ví dụ này:

- `src.dir` trỏ tới thư mục `src` bên dưới project base directory.
- `build.dir` trỏ tới thư mục `build`.
- `dist.dir` trỏ tới thư mục `dist`.
- `location` yêu cầu Ant diễn giải giá trị như một vị trí trên hệ thống tệp và chuẩn hóa thành đường dẫn tuyệt đối.

Khi nhiều target cùng dùng các đường dẫn này, việc tập trung chúng thành property giúp buildfile dễ bảo trì. Nếu cấu trúc đầu ra thay đổi, có thể chỉnh property tương ứng mà không phải tìm và sửa mọi task đang dùng đường dẫn.

## 7. Kết hợp cả ba thuộc tính trong một buildfile

Ví dụ dưới đây kết hợp `name`, `default` và `basedir` trong một cấu hình nhỏ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="student-management" default="build" basedir=".">

    <property name="src.dir" location="${basedir}/src"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <target name="prepare" description="Create output directories">
        <mkdir dir="${build.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="build" depends="prepare"
            description="Run the project's build entry point">
        <echo message="Project: student-management"/>
        <echo message="Sources: ${src.dir}"/>
        <echo message="Build output: ${build.dir}"/>
        <echo message="Distribution output: ${dist.dir}"/>
    </target>

</project>
```

Chạy target mặc định:

```sh
ant
```

hoặc chỉ định tường minh:

```sh
ant build
```

Hai lệnh trên đều chọn target `build`. Target `build` phụ thuộc vào `prepare`, vì vậy các thư mục đầu ra được tạo trước khi các thông điệp của target `build` được in ra.

Có thể xem danh sách target và mô tả bằng:

```sh
ant -p
```

Lệnh này hữu ích khi đọc một buildfile có nhiều target và cần tìm tên target để gọi.

## 8. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chạy `ant` nhưng target mong muốn không được gọi | `default` đang trỏ tới target khác hoặc chưa được khai báo | Kiểm tra giá trị `default` và target tương ứng |
| Ant báo không tìm thấy target mặc định | Giá trị `default` không khớp tên target hiện có | Sửa tên trong `default` hoặc khai báo target còn thiếu |
| Thay `name` nhưng hành vi build không đổi | `name` chỉ đặt tên project, không chọn target | Sửa thuộc tính `default` nếu muốn thay đổi target được gọi khi chạy `ant` |
| Thư mục `build` được tạo sai vị trí | `basedir` không trỏ tới thư mục gốc dự kiến | Kiểm tra vị trí buildfile và giá trị `basedir` |
| Chạy build từ thư mục khác tạo ra kết quả khác dự kiến | Nhầm lẫn thư mục làm việc terminal với project base directory | Dùng `basedir` rõ ràng và kiểm tra `${basedir}` trong log |
| Các target không chạy theo thứ tự mong muốn | Chưa khai báo quan hệ phụ thuộc | Dùng `depends` để mô tả target nào cần chạy trước |
| XML không được phân tích | Sai cú pháp XML hoặc sai chữ hoa/chữ thường của tên phần tử, thuộc tính | Kiểm tra thẻ mở/đóng, dấu nháy và cách viết tên thuộc tính |

Khi cần chẩn đoán, có thể thêm lệnh `echo` để hiển thị giá trị property:

```xml
<target name="show-config">
    <echo message="Project base: ${basedir}"/>
    <echo message="Build directory: ${build.dir}"/>
</target>
```

Sau đó chạy:

```sh
ant show-config
```

Quan sát log sẽ giúp xác định Ant đang sử dụng thư mục cơ sở và đường dẫn đầu ra nào.

## 9. Checklist khi khai báo phần tử `project`

- [ ] Buildfile có một phần tử gốc `<project>` hợp lệ.
- [ ] `name` mô tả đúng dự án và không bị nhầm với tên target.
- [ ] `default` trỏ tới target có thật và là điểm bắt đầu phù hợp khi chạy `ant` không kèm tên target.
- [ ] `basedir` trỏ tới thư mục gốc mong muốn; nếu bỏ trống, đã hiểu quy tắc mặc định theo vị trí buildfile.
- [ ] Các đường dẫn tương đối và property như `${basedir}`, `src.dir`, `build.dir` được tính từ đúng thư mục cơ sở.
- [ ] Các target phụ thuộc lẫn nhau được liên kết bằng `depends` để Ant thực thi đúng thứ tự.
- [ ] Đã thử cả lệnh `ant` và lệnh gọi target cụ thể.

Khai báo rõ `name`, `default` và `basedir` tạo nền tảng dễ hiểu cho phần còn lại của `build.xml`: người đọc biết buildfile thuộc dự án nào, lệnh mặc định sẽ chạy công việc gì và mọi đường dẫn tương đối bắt đầu từ đâu.

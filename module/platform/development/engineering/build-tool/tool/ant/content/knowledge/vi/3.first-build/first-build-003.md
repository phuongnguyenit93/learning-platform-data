# Chuẩn bị thư mục đầu ra bằng `mkdir`

Trong một dự án sử dụng Apache Ant, các bước biên dịch, kiểm thử và đóng gói thường tạo ra nhiều tệp trung gian. Nên gom những tệp này vào các thư mục đầu ra riêng, chẳng hạn `build/classes` để chứa bytecode, `build/reports` để chứa báo cáo và `dist` để chứa gói phát hành. Trước khi ghi tệp vào những vị trí đó, build cần bảo đảm các thư mục đã tồn tại.

Ant cung cấp task tích hợp `<mkdir>` để tạo thư mục ngay trong `build.xml`. Khi đặt task này vào một target khởi tạo, những target biên dịch hoặc đóng gói có thể phụ thuộc vào target khởi tạo đó. Nhờ vậy, việc chuẩn bị cấu trúc thư mục trở thành một phần có thể lặp lại của quy trình build.

## 1. `<mkdir>` là gì?

`<mkdir>` là một Ant task dùng để tạo thư mục được chỉ định bởi thuộc tính `dir`:

```xml
<mkdir dir="build/classes"/>
```

Task này có các đặc điểm quan trọng:

- Nếu thư mục chưa tồn tại, Ant tạo thư mục đó.
- Nếu một hoặc nhiều thư mục cha chưa tồn tại, Ant tạo cả các thư mục cha cần thiết.
- Nếu đường dẫn đã là một thư mục, task có thể chạy lại mà không báo lỗi chỉ vì thư mục đã tồn tại.
- Nếu tại đường dẫn đó đang có một tệp thông thường thay vì thư mục, Ant không thể dùng tệp ấy làm thư mục và bước build sẽ thất bại.
- Task chỉ tạo cấu trúc thư mục; nó không tự tạo tệp, không xóa nội dung cũ và không biên dịch mã nguồn.

Ví dụ, với lệnh:

```xml
<mkdir dir="build/classes/com/example"/>
```

nếu dự án chưa có thư mục `build`, Ant tạo lần lượt các cấp cần thiết để có đường dẫn `build/classes/com/example`. Không cần viết riêng một task cho từng thư mục cha.

## 2. Phân biệt Ant task với lệnh `mkdir` của hệ điều hành

Tên gọi giống nhau nhưng hai cách dùng nằm ở hai nơi khác nhau:

| Cách dùng | Viết ở đâu? | Khi nào chạy? |
|---|---|---|
| `mkdir build` | Command Prompt, PowerShell hoặc shell của hệ điều hành | Khi người dùng nhập lệnh trong terminal |
| `<mkdir dir="build"/>` | Tệp cấu hình `build.xml` | Khi Ant thực thi target chứa task đó |

Ví dụ, nếu người dùng tạo thư mục bằng terminal trước, dự án có thể chạy được trên máy đó. Nhưng một máy khác checkout mã nguồn sẽ không tự có thư mục vừa tạo. Đưa `<mkdir>` vào `build.xml` giúp Ant tự chuẩn bị thư mục trên mỗi máy khi target tương ứng được chạy.

## 3. Tạo target chuẩn bị thư mục đầu ra

Một tệp `build.xml` tối thiểu có thể khai báo target `prepare-output` như sau:

```xml
<project name="sample-ant-project" default="prepare-output" basedir=".">

    <target name="prepare-output" description="Create build output directories">
        <mkdir dir="build"/>
        <mkdir dir="build/classes"/>
        <mkdir dir="build/reports"/>
        <mkdir dir="dist"/>
    </target>

</project>
```

Trong ví dụ này:

- `<project>` khai báo dự án Ant. `default="prepare-output"` chọn target mặc định khi chạy Ant mà không chỉ rõ tên target.
- `<target>` gom các bước chuẩn bị dưới tên `prepare-output`.
- Mỗi `<mkdir>` tạo một thư mục đầu ra.
- `description` mô tả mục đích của target và giúp người đọc hiểu vai trò của nó.

Có thể lưu đoạn cấu hình trên vào tệp `build.xml` tại thư mục gốc dự án. Mở terminal ở thư mục chứa tệp rồi chạy:

```sh
ant prepare-output
```

Vì `prepare-output` cũng là target mặc định trong ví dụ, lệnh sau có kết quả tương đương:

```sh
ant
```

Sau khi chạy, cấu trúc thư mục dự kiến là:

```text
sample-ant-project/
├── build.xml
├── build/
│   ├── classes/
│   └── reports/
└── dist/
```

Tên target là do người viết `build.xml` đặt. `mkdir` là task nằm bên trong target; `prepare-output` không phải tên khác của task `mkdir`.

## 4. Dùng property để quản lý đường dẫn

Khi dự án lớn hơn, nhiều target có thể cùng sử dụng một thư mục đầu ra. Nếu viết lặp lại đường dẫn ở nhiều vị trí, việc đổi tên hoặc chuyển vị trí thư mục sẽ cần sửa nhiều dòng. Ant property giúp khai báo đường dẫn một lần rồi tái sử dụng.

Ví dụ:

```xml
<project name="sample-ant-project" default="prepare-output" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="dist.dir" location="dist"/>

    <target name="prepare-output" description="Create build output directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

</project>
```

Các biểu thức `${build.dir}`, `${classes.dir}`, `${reports.dir}` và `${dist.dir}` được Ant thay bằng giá trị property tương ứng khi thực thi. Thuộc tính `location` khai báo một vị trí trên hệ thống tệp và chuẩn hóa giá trị thành đường dẫn tuyệt đối.

Trong ví dụ trên, `build.dir` được đặt thành thư mục `build` bên dưới project base directory. Hai property `classes.dir` và `reports.dir` được xây dựng từ `build.dir`, vì vậy cả hai cùng nằm dưới một thư mục gốc. Nếu muốn chuyển toàn bộ đầu ra biên dịch sang một vị trí khác, có thể bắt đầu bằng cách đổi giá trị `build.dir`.

Ant tự cung cấp property `${basedir}` để biểu diễn thư mục cơ sở của project. Khi cần diễn đạt rõ đường dẫn gắn với thư mục gốc dự án, có thể viết:

```xml
<property name="build.dir" location="${basedir}/build"/>
```

Với cấu hình project không chỉ định `basedir`, Ant mặc định dùng thư mục chứa tệp build làm thư mục cơ sở. Nếu có khai báo `basedir` riêng, các đường dẫn tương đối được hiểu theo thư mục cơ sở đã khai báo đó.

## 5. Dùng target khởi tạo làm prerequisite cho các bước build

Thông thường, target biên dịch cần có thư mục để ghi `.class`; target đóng gói cần có nơi chứa JAR. Ta có thể khai báo quan hệ phụ thuộc bằng thuộc tính `depends` của target.

```xml
<project name="sample-ant-project" default="compile" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>

    <target name="prepare-output" description="Create output directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
    </target>

    <target name="compile" depends="prepare-output"
            description="Compile Java source files">
        <!-- Các task biên dịch được đặt ở đây. -->
    </target>

</project>
```

Khi chạy:

```sh
ant compile
```

Ant thực hiện `prepare-output` trước rồi mới chạy phần thân của target `compile`. Điều này bảo đảm các thư mục đầu ra được tạo trước khi các task tiếp theo cần dùng đến chúng.

Một target khác cũng có thể phụ thuộc vào `prepare-output`:

```xml
<target name="test" depends="prepare-output">
    <!-- Các task kiểm thử được đặt ở đây. -->
</target>

<target name="package" depends="prepare-output">
    <!-- Các task đóng gói được đặt ở đây. -->
</target>
```

Khai báo phụ thuộc giúp mỗi target có thể được gọi độc lập mà vẫn chuẩn bị được thư mục cần thiết. Nếu một target cần kết quả của target khác, có thể mô tả quan hệ phụ thuộc theo chuỗi phù hợp với quy trình build của dự án.

## 6. Chuẩn bị nhiều cấp thư mục và nhiều khu vực đầu ra

Một dự án Java có thể cần các thư mục riêng cho bytecode, tài nguyên đã sao chép, báo cáo kiểm thử và gói phát hành. Có thể tạo chúng trong cùng target:

```xml
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="resources.dir" location="${build.dir}/resources"/>
<property name="test.classes.dir" location="${build.dir}/test-classes"/>
<property name="reports.dir" location="${build.dir}/reports"/>
<property name="dist.dir" location="dist"/>

<target name="prepare-output">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${resources.dir}"/>
    <mkdir dir="${test.classes.dir}"/>
    <mkdir dir="${reports.dir}"/>
    <mkdir dir="${dist.dir}"/>
</target>
```

Sau khi target chạy, cấu trúc có thể trông như sau:

```text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       └── java/
├── build/
│   ├── classes/
│   ├── resources/
│   ├── test-classes/
│   └── reports/
└── dist/
```

Đây là cách tổ chức thường gặp, không phải cấu trúc bắt buộc của Ant. Dự án có thể chọn tên thư mục khác, miễn các task biên dịch, sao chép, kiểm thử và đóng gói cùng tham chiếu đúng các property đã khai báo.

## 7. Đường dẫn tương đối, tuyệt đối và thư mục có dấu cách

Thuộc tính `dir` nhận đường dẫn thư mục. Có thể truyền đường dẫn tương đối:

```xml
<mkdir dir="build/generated"/>
```

hoặc đường dẫn được tạo từ `basedir`:

```xml
<mkdir dir="${basedir}/build/generated"/>
```

Với property dùng `location`, có thể khai báo đường dẫn đầy đủ:

```xml
<property name="output.dir" location="D:/workspace/sample/output"/>

<target name="prepare-output">
    <mkdir dir="${output.dir}"/>
</target>
```

Trong XML, giá trị thuộc tính được đặt trong dấu nháy nên đường dẫn có dấu cách vẫn có thể được viết trực tiếp:

```xml
<mkdir dir="D:/Java Projects/sample/build/output"/>
```

Để cấu hình dễ chuyển giữa Windows, Linux và macOS, nên ưu tiên đường dẫn tương đối với project hoặc ghép từ property. Tránh gắn đường dẫn cá nhân của một máy vào `build.xml` nếu dự án cần được build trên nhiều máy.

## 8. Tính lặp lại của target chuẩn bị thư mục

Một build thường được chạy nhiều lần trong quá trình phát triển. Target chuẩn bị thư mục nên có thể chạy lại mà không cần người dùng xóa thư mục trước.

Ví dụ:

```xml
<target name="prepare-output">
    <mkdir dir="build/classes"/>
    <mkdir dir="build/reports"/>
</target>
```

Lần chạy đầu tiên, Ant tạo các thư mục còn thiếu. Ở lần chạy tiếp theo, nếu chúng vẫn là thư mục hợp lệ, task không báo lỗi chỉ vì chúng đã tồn tại. Đây là lý do có thể đặt target này làm prerequisite cho nhiều bước khác.

Hãy phân biệt việc tạo thư mục với việc làm sạch dữ liệu cũ:

- `<mkdir>` chỉ bảo đảm thư mục tồn tại.
- `<mkdir>` không xóa tệp cũ bên trong thư mục.
- Nếu quy trình cần làm sạch đầu ra cũ, đó là một yêu cầu riêng cần được thiết kế bằng target và task phù hợp. Không nên giả định rằng gọi `mkdir` sẽ làm mới toàn bộ nội dung thư mục.

Giữ hai trách nhiệm này tách bạch giúp tránh vô tình xóa kết quả build hoặc dữ liệu mà người dùng vẫn cần.

## 9. Chạy và quan sát kết quả

Đứng tại thư mục dự án có `build.xml`, chạy target:

```sh
ant prepare-output
```

Một số lệnh hữu ích khi tìm hiểu build:

```sh
ant -p
ant -verbose prepare-output
```

- `ant -p` liệt kê các target có mô tả trong project.
- `ant -verbose prepare-output` chạy target với thông tin chi tiết hơn để quan sát quá trình Ant thực thi.

Sau khi chạy, kiểm tra trực tiếp thư mục đầu ra bằng File Explorer hoặc terminal. Trên Windows có thể dùng:

```bat
dir build
dir build\classes
dir build\reports
dir dist
```

Trên Linux/macOS có thể dùng:

```sh
find build dist -type d
```

Nếu target kết thúc thành công nhưng thư mục xuất hiện ở vị trí không mong đợi, hãy kiểm tra `basedir`, các property chứa đường dẫn và thư mục làm việc của lệnh Ant.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant báo không tạo được thư mục | Tiến trình không có quyền ghi tại thư mục cha hoặc ổ đĩa không khả dụng | Kiểm tra quyền truy cập, đường dẫn và dung lượng ổ đĩa |
| Đường dẫn được tạo sai vị trí | Hiểu nhầm thư mục cơ sở hoặc property đang chứa giá trị khác dự kiến | Kiểm tra `basedir`, `location` và giá trị property được dùng trong `dir` |
| Ant báo lỗi vì đường dẫn đã tồn tại | Đường dẫn đang là một tệp, không phải thư mục | Kiểm tra đúng đường dẫn và xử lý xung đột tên tệp/thư mục trước khi chạy lại |
| Target biên dịch chạy trước khi có thư mục đầu ra | Target biên dịch chưa khai báo phụ thuộc vào target chuẩn bị | Thêm `depends="prepare-output"` vào target cần thư mục |
| Thư mục đã có nhưng tệp cũ vẫn còn | `<mkdir>` không có chức năng xóa nội dung | Xác định riêng yêu cầu làm sạch đầu ra và thiết kế bước đó có chủ đích |
| Lệnh Ant không tìm thấy `build.xml` | Terminal đang ở sai thư mục hoặc tệp build có tên/vị trí khác | Chuyển tới thư mục dự án hoặc chỉ định tệp bằng tùy chọn `-f` |

Nếu tệp build không nằm trong thư mục hiện tại, có thể chỉ định đường dẫn tệp:

```sh
ant -f path/to/build.xml prepare-output
```

Khi dùng cách này, hãy nhớ rằng đường dẫn tương đối trong project được diễn giải theo project base directory. Kiểm tra `basedir` trong tệp build nếu vị trí đầu ra khác với mong đợi.

## 11. Checklist trước khi dùng trong build

- [ ] Mỗi `<mkdir>` có thuộc tính `dir` trỏ tới đúng thư mục cần tạo.
- [ ] Các đường dẫn đầu ra được gom thành property khi nhiều target cùng sử dụng.
- [ ] Target chuẩn bị thư mục có tên và mô tả rõ mục đích.
- [ ] Target biên dịch, kiểm thử hoặc đóng gói khai báo phụ thuộc vào target chuẩn bị khi cần các thư mục đó.
- [ ] Đường dẫn tương đối được hiểu theo project base directory đã cấu hình.
- [ ] Có thể chạy lại target mà không cần tạo thủ công hoặc xóa thư mục trước.
- [ ] Đã kiểm tra vị trí thư mục thực tế sau khi chạy target.

Khi tổ chức như vậy, `<mkdir>` trở thành bước khởi tạo đơn giản và đáng tin cậy cho các target tiếp theo. Ant có thể tự tạo cấu trúc đầu ra cần thiết mỗi khi build, giúp dự án dễ chạy trên máy mới và giảm phụ thuộc vào thao tác chuẩn bị thủ công.

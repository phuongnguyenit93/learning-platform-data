# Quản lý `basedir` và đường dẫn của tệp build được nhập

Apache Ant cho phép chia buildfile thành nhiều tệp để tái sử dụng target và cấu hình chung. Ví dụ, dự án có thể đặt các target biên dịch, kiểm tra, đóng gói hoặc triển khai trong một tệp build dùng chung rồi nhập vào `build.xml` của từng ứng dụng bằng `<import>` hoặc `<include>`.

Khi một buildfile được nhập, có một điểm dễ gây nhầm lẫn: Ant xử lý các target và task của tệp được nhập trong project chính. Vì vậy, thuộc tính `basedir` của project trong tệp được nhập bị bỏ qua; các đường dẫn tương đối trong nội dung tệp đó thường được tính theo `basedir` của project chính. Nếu tệp dùng chung cần đọc file cấu hình hoặc tài nguyên nằm cạnh chính nó, hãy xác định thư mục chứa buildfile bằng property đặc biệt `ant.file.<project-name>` và task `<dirname>`.

## 1. `basedir` điều khiển đường dẫn tương đối như thế nào?

`basedir` là thư mục cơ sở mà Ant sử dụng để phân giải phần lớn đường dẫn tương đối trong một project. Nếu project khai báo:

```xml
<project name="inventory-app" default="compile" basedir=".">
    <property name="src.dir" location="src/main/java"/>
</project>
```

thì `src/main/java` được tính từ thư mục cơ sở của project `inventory-app`. Nếu bỏ thuộc tính `basedir`, Ant mặc định dùng thư mục chứa buildfile làm thư mục cơ sở. Nếu giá trị `basedir` là đường dẫn tương đối, nó được phân giải tương đối với thư mục chứa buildfile.

Ví dụ cấu trúc:

```text
workspace/
└── inventory-app/
    ├── build.xml
    └── src/
        └── main/java/
```

Với `basedir="."`, property `src.dir` trỏ tới `inventory-app/src/main/java`.

Thuộc tính `location` của task `<property>` chuyển đường dẫn thành giá trị đã chuẩn hóa, thường là đường dẫn tuyệt đối. Vì thế, khi xây dựng property từ một thư mục gốc đã xác định, `location` giúp các task dùng chung cùng một đường dẫn rõ ràng.

## 2. Nhập buildfile bằng `<import>`

`<import>` đưa các target của một buildfile khác vào project hiện tại. Nó phải được khai báo ở cấp cao nhất của `<project>`, không được đặt bên trong một `<target>`.

Ví dụ:

```text
workspace/
├── build-logic/
│   └── common-targets.xml
└── inventory-app/
    └── build.xml
```

Tệp `inventory-app/build.xml`:

```xml
<project name="inventory-app" default="build" basedir=".">

    <import file="../build-logic/common-targets.xml"/>

    <target name="build" depends="compile,package"/>

</project>
```

Tệp `common-targets.xml` có thể khai báo các target dùng chung:

```xml
<project name="common-build">

    <target name="prepare">
        <mkdir dir="build"/>
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile shared project sources here"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Package shared project output here"/>
    </target>

</project>
```

Sau khi nhập, các target `prepare`, `compile` và `package` có thể được gọi từ project chính như thể chúng được khai báo trong buildfile chính. `<import>` phù hợp khi muốn tái sử dụng target và vẫn cho phép project nhập ghi đè cách triển khai một target.

## 3. Đường dẫn của thuộc tính `file` trong `<import>`

Thuộc tính `file` của `<import>` có quy tắc phân giải riêng: nếu là đường dẫn tương đối, nó được tính tương đối với tệp build đang thực hiện thao tác import. Đây là điểm khác với phần lớn thuộc tính đường dẫn của task Ant, vốn thường được tính theo `basedir` của project.

Ví dụ:

```xml
<project name="inventory-app" basedir=".">
    <import file="../build-logic/common-targets.xml"/>
</project>
```

Nếu `build.xml` nằm trong `inventory-app/`, đường dẫn `../build-logic/common-targets.xml` được tính từ vị trí buildfile nhập. Khi cấu trúc thư mục được tổ chức rõ, cách viết tương đối này giúp project nhập tìm thấy tệp dùng chung mà không cần hard-code đường dẫn tuyệt đối của một máy.

Với các cấu trúc import nhiều tầng hoặc project có `basedir` tùy chỉnh phức tạp, việc suy luận đường dẫn có thể khó hơn. Tài liệu Ant khuyến nghị dùng tham chiếu tuyệt đối hoặc property đường dẫn đã chuẩn hóa khi cần độ ổn định cao, đặc biệt trong các buildfile dùng chung.

## 4. Vì sao `basedir` trong buildfile được nhập bị bỏ qua?

Ant xử lý buildfile được import như thể nội dung của nó (trừ thẻ `<project>` ngoài cùng) nằm trong buildfile chính. Điều này giúp target của các tệp có thể phối hợp trong cùng một project, nhưng cũng có nghĩa thuộc tính `basedir` ở `<project>` của tệp được nhập không tạo ra một thư mục cơ sở riêng.

Giả sử:

```text
workspace/
├── build-logic/
│   ├── common-targets.xml
│   └── config/
│       └── common.properties
└── inventory-app/
    ├── build.xml
    └── config/
        └── app.properties
```

Tệp `inventory-app/build.xml`:

```xml
<project name="inventory-app" default="show-config" basedir=".">
    <import file="../build-logic/common-targets.xml"/>
</project>
```

Tệp `build-logic/common-targets.xml`:

```xml
<project name="common-build" basedir=".">
    <property file="config/common.properties"/>

    <target name="show-config">
        <echo message="Shared setting: ${shared.setting}"/>
    </target>
</project>
```

Trong trường hợp này, `basedir="."` của `common-targets.xml` bị bỏ qua. Đường dẫn `config/common.properties` được phân giải theo `basedir` của project chính, tức `inventory-app/config/common.properties`, chứ không phải `build-logic/config/common.properties`.

Để buildfile dùng chung đọc tài nguyên cạnh chính nó, cần lấy thư mục chứa file build được nhập một cách tường minh.

## 5. Dùng `ant.file.<project-name>` và `<dirname>`

Với mỗi buildfile được import, Ant tạo property đặc biệt chứa đường dẫn tới buildfile đó. Tên property có dạng:

```text
ant.file.<project-name>
```

Trong đó `<project-name>` là giá trị thuộc tính `name` của phần tử `<project>` trong buildfile được nhập, không phải tên file trên đĩa.

Ví dụ, nếu `common-targets.xml` khai báo:

```xml
<project name="common-build">
    ...
</project>
```

thì có thể tham chiếu `${ant.file.common-build}` để lấy đường dẫn của `common-targets.xml`.

Task `<dirname>` lấy phần thư mục của một đường dẫn file. Kết hợp hai cơ chế:

```xml
<project name="common-build">

    <dirname property="common.basedir"
             file="${ant.file.common-build}"/>

    <property name="common.config.file"
              location="${common.basedir}/config/common.properties"/>

    <property file="${common.config.file}"/>

    <target name="show-common-config">
        <echo message="Common build directory: ${common.basedir}"/>
        <echo message="Common setting: ${shared.setting}"/>
    </target>

</project>
```

`<dirname>` đặt `common.basedir` thành thư mục chứa `common-targets.xml`. Sau đó, `common.config.file` được tạo từ thư mục đó và trỏ tới `config/common.properties` cạnh buildfile dùng chung.

Kỹ thuật này là cách tiêu chuẩn để một buildfile được import có thể tham chiếu tài nguyên theo vị trí của chính nó, bất kể project chính được gọi từ thư mục nào.

## 6. Dùng buildfile được nhập độc lập

Một lợi ích của cách dùng `ant.file.<project-name>` cùng `<dirname>` là buildfile dùng chung vẫn có thể được chạy độc lập. Khi chạy trực tiếp, Ant cũng cung cấp property xác định buildfile hiện hành; với tên project tương ứng, property đặc biệt cho phép lấy đường dẫn của file.

Ví dụ `common-targets.xml`:

```xml
<project name="common-build" default="show-common-config">

    <dirname property="common.basedir"
             file="${ant.file.common-build}"/>
    <property name="common.config.file"
              location="${common.basedir}/config/common.properties"/>
    <property file="${common.config.file}"/>

    <target name="show-common-config">
        <echo message="Build logic: ${common.basedir}"/>
        <echo message="Setting: ${shared.setting}"/>
    </target>

</project>
```

Có thể chạy trực tiếp:

```sh
ant -f build-logic/common-targets.xml show-common-config
```

Hoặc nhập vào project chính rồi gọi target từ project chính. Cùng một buildfile có thể được tái sử dụng theo cả hai cách, miễn các property và target của nó không giả định một `basedir` cụ thể do project bên ngoài cung cấp.

## 7. Đặt tên project và property riêng để tránh xung đột

Vì buildfile được import hoạt động trong cùng project với buildfile chính, các property và reference có thể dùng chung namespace. Ant property có tính bất biến: khi một property đã được đặt, lần khai báo tiếp theo cùng tên không thay đổi giá trị đã có.

Do đó, nên dùng tên project và property có tiền tố riêng:

```xml
<project name="database-build-support">
    <dirname property="database.build.basedir"
             file="${ant.file.database-build-support}"/>
    <property name="database.build.config"
              location="${database.build.basedir}/config/database.properties"/>
</project>
```

Tránh dùng các tên quá chung như `base.dir`, `config.file`, `output.dir` trong nhiều buildfile được nhập. Nếu project chính đã đặt `config.file`, property cùng tên trong buildfile nhập có thể không ghi đè được và task sẽ đọc nhầm giá trị.

Tên `project` trong mỗi file được nhập nên rõ ràng và duy nhất trong phạm vi build. Property `ant.file.<project-name>` phụ thuộc tên đó; nếu bỏ thuộc tính `name` trong project được nhập, Ant không tạo property đặc biệt tương ứng cho file ấy.

## 8. Dùng `as` để đặt prefix cho target được nhập

Thuộc tính `as` của `<import>` thay đổi prefix được dùng cho các target của buildfile nhập:

```xml
<project name="inventory-app" default="build" basedir=".">
    <import file="../build-logic/common-targets.xml" as="common"/>

    <target name="build" depends="common.prepare,common.compile"/>
</project>
```

Với `as="common"`, target nhập có thể được tham chiếu bằng tên có prefix như `common.prepare` và `common.compile`. Trong import, target nhập thường vẫn có tên không prefix và tên prefix; nếu target trùng với target ở project chính, target project chính được ưu tiên, còn target nhập có thể được gọi qua tên prefix.

Điều này hữu ích khi muốn mở rộng target dùng chung mà vẫn gọi được hành vi gốc:

```xml
<target name="compile" depends="common.compile">
    <echo message="Application-specific compile steps"/>
</target>
```

Trong ví dụ, project chính định nghĩa target `compile` riêng. Target gốc từ buildfile nhập vẫn có thể được gọi bằng `common.compile`.

## 9. Khi nào dùng `<include>` thay vì `<import>`?

`<include>` cũng đưa target từ buildfile khác vào project, nhưng quy tắc tên target và dependency khác `<import>`.

| Đặc điểm | `<import>` | `<include>` |
|---|---|---|
| Target được nhập | Có thể được gọi bằng tên thường và tên có prefix | Chỉ có tên có prefix |
| Ghi đè target bằng project chính | Có hỗ trợ | Không hỗ trợ theo cơ chế của import |
| `depends` của target nhập | Giữ tên dependency gốc | Được viết lại để dùng tên có prefix |
| Dùng lại cùng file nhiều lần với prefix khác | Không thể import cùng file nhiều lần | Có thể include cùng file nhiều lần với prefix khác |
| Mục đích | Mở rộng hoặc ghi đè target dùng chung | Bao gồm nhóm target độc lập, tự đóng gói theo prefix |

Ví dụ:

```xml
<project name="inventory-app" default="build" basedir=".">
    <include file="../build-logic/common-targets.xml" as="common"/>

    <target name="build" depends="common.compile,common.package"/>
</project>
```

Trong cả `import` và `include`, tệp được nhập được xử lý như một phần của project chính về mặt `basedir`. Nếu buildfile cần tham chiếu tài nguyên nằm cạnh nó, vẫn nên dùng `ant.file.<project-name>` và `<dirname>`.

Chọn `import` khi cần override target hoặc cần gọi target gốc qua prefix. Chọn `include` khi muốn giữ các target trong namespace riêng và không muốn project chính thay đổi dependency nội bộ của chúng.

## 10. Tệp được nhập qua URL hoặc resource

Từ Ant 1.8.0, `<import>` và `<include>` có thể nhận resource collection hoặc URL thay vì chỉ một file hệ thống. Khi nguồn là URL, property đặc biệt `ant.file.type.<project-name>` có thể cho biết nguồn là `file` hay `url`.

Ví dụ kiểm tra loại nguồn:

```xml
<condition property="common.build.is.file">
    <equals arg1="${ant.file.type.common-build}" arg2="file"/>
</condition>
```

Kỹ thuật `<dirname>` chỉ phù hợp khi `ant.file.<project-name>` đại diện cho đường dẫn file trên filesystem. Nếu buildfile được nhập từ URL, không thể coi URL như một đường dẫn thư mục cục bộ để ghép `config/common.properties`.

Với tài nguyên tương đối nằm cạnh buildfile URL, dùng task có khả năng làm việc với URL/resource, chẳng hạn `<loadproperties>` cùng nested `<url>`:

```xml
<loadproperties>
    <url baseUrl="${ant.file.common-build}"
         relativePath="config/common.properties"/>
</loadproperties>
```

Khả năng truy cập tài nguyên tương đối còn phụ thuộc URL nguồn và task tiêu thụ. Nếu không cần import qua URL, dùng file hệ thống với đường dẫn ổn định thường đơn giản hơn.

## 11. Phân biệt `<import>` với task `<ant>` gọi sub-build

`<import>` và `<include>` gộp target vào cùng project. Task `<ant>` thì chạy một buildfile khác như một project con, với target và project context riêng.

Ví dụ:

```xml
<target name="build-core-module">
    <ant antfile="build.xml"
         dir="modules/core"
         target="compile"
         inheritAll="false"/>
</target>
```

Ở đây:

- `dir` xác định thư mục dùng để tìm buildfile con và làm `basedir` cho project con theo quy tắc của task.
- `antfile` là tên buildfile con, được phân giải tương đối với `dir`.
- `target` chọn target của project con.
- `inheritAll="false"` hạn chế việc truyền các property thông thường từ project cha; user properties từ dòng lệnh vẫn có quy tắc riêng.

Từ Ant 1.8.0, task `<ant>` có thuộc tính `useNativeBasedir="true"`. Khi bật, project con sử dụng `basedir` mà nó sẽ có nếu được chạy độc lập từ buildfile của chính nó, thay vì để task cha áp đặt theo `dir` hoặc cơ chế kế thừa mặc định.

```xml
<target name="build-core-module">
    <ant antfile="build.xml"
         dir="modules/core"
         target="compile"
         inheritAll="false"
         useNativeBasedir="true"/>
</target>
```

Nếu mục tiêu là chia sẻ target trong cùng project và cho phép override, dùng `<import>`. Nếu mục tiêu là chạy một module như một build riêng với project context và `basedir` độc lập, dùng `<ant>` và cấu hình `dir`, `inheritAll`, `useNativeBasedir` có chủ đích.

## 12. Tổ chức một buildfile dùng chung có đường dẫn ổn định

Một mẫu thực tế là đặt build logic và tài nguyên cạnh nhau:

```text
workspace/
├── build-support/
│   ├── common-targets.xml
│   └── config/
│       └── common.properties
└── inventory-app/
    ├── build.xml
    └── src/
```

`build-support/common-targets.xml`:

```xml
<project name="common-build">

    <dirname property="common.build.dir"
             file="${ant.file.common-build}"/>
    <property name="common.config.file"
              location="${common.build.dir}/config/common.properties"/>
    <property file="${common.config.file}"/>

    <target name="common.prepare">
        <mkdir dir="${basedir}/build/shared"/>
        <echo message="Loaded shared settings from ${common.config.file}"/>
    </target>

</project>
```

`inventory-app/build.xml`:

```xml
<project name="inventory-app" default="prepare" basedir=".">

    <import file="../build-support/common-targets.xml" as="shared"/>

    <target name="prepare" depends="shared.common.prepare">
        <mkdir dir="${basedir}/build/app"/>
    </target>

</project>
```

Trong ví dụ này, `common.config.file` được tính từ vị trí của `common-targets.xml`, nên tìm được file cấu hình ở `build-support/config` dù project chính nằm trong `inventory-app`. Tuy nhiên, target dùng chung tạo `build/shared` từ `${basedir}` của project chính. Đây là lựa chọn có chủ đích nếu output thuộc ứng dụng gọi nó.

Nếu output cần nằm cạnh build logic dùng chung, hãy dùng `${common.build.dir}` thay cho `${basedir}`. Cần quyết định rõ tài nguyên thuộc về project nhập hay thư mục chứa build logic; đừng để cùng một property mang hai ý nghĩa.

## 13. Những nguyên tắc thiết kế đường dẫn khi tái sử dụng buildfile

1. **Dùng `ant.file.<project-name>` để xác định vị trí buildfile.** Đừng giả định `basedir` trong file nhập tạo ra một base directory riêng.
2. **Dùng `<dirname>` để lấy thư mục chứa file.** Tạo property riêng như `common.build.dir` hoặc `shared.basedir`.
3. **Dùng `location` để chuẩn hóa đường dẫn.** Khi đã có thư mục gốc tuyệt đối, xây dựng property con bằng `location` để giảm nhập nhằng.
4. **Đặt prefix cho property.** Dùng `common.*`, `database.*` hoặc `release.*` thay vì tên chung dễ xung đột.
5. **Phân biệt đường dẫn của file import với đường dẫn của tài nguyên.** Thuộc tính `file` của `<import>` được tính tương đối với buildfile nhập; nhiều thuộc tính file khác được tính theo `basedir`.
6. **Giữ đường dẫn trong cùng repository tương đối khi có thể.** Tránh hard-code đường dẫn cá nhân hoặc ổ đĩa của một máy.
7. **Dùng `<ant>` khi cần project con độc lập.** Đừng dùng import chỉ để tạo một project context riêng.
8. **Không giả định `<dirname>` xử lý được URL.** Với nguồn URL, dùng resource-aware task để tìm tài nguyên tương đối.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Tệp properties cạnh buildfile dùng chung không được tìm thấy | Đường dẫn tương đối đang được tính theo `basedir` của project chính | Dùng `ant.file.<project-name>` và `<dirname>` để tạo đường dẫn tới tài nguyên cạnh file nhập |
| Thư mục `build` được tạo ở project chính thay vì thư mục build logic | `basedir` của project nhập bị bỏ qua | Quyết định output thuộc project chính hay build logic; dùng `${basedir}` hoặc property thư mục riêng tương ứng |
| Property dùng chung có giá trị sai | Tên property trùng với property đã được project chính đặt trước | Dùng prefix riêng cho property của từng buildfile |
| `${ant.file.common}` không được thay thế | Tên property không khớp thuộc tính `name` của project được nhập hoặc project thiếu `name` | Kiểm tra `name` và dùng đúng `ant.file.<project-name>` |
| `<dirname>` báo lỗi hoặc tạo đường dẫn không hợp lệ | Buildfile được nhập từ URL/resource thay vì filesystem | Kiểm tra `ant.file.type.<project-name>` và dùng task xử lý URL/resource |
| Target nhập không được tìm thấy bằng tên dự kiến | Dùng `as` hoặc `<include>` nên target có prefix | Kiểm tra tên target đầy đủ và separator của prefix |
| Target project chính không ghi đè target nhập | Đang dùng `<include>` thay vì `<import>` | Dùng `<import>` nếu cần target overriding |
| Dependency của target include không chạy | Gọi target không có prefix hoặc viết `depends` sai | Dùng tên prefix do `as` hoặc `name` của project nhập tạo ra |
| Đường dẫn import hoạt động từ một thư mục nhưng lỗi ở nơi khác | Nhầm quy tắc phân giải `file` của import với thuộc tính file thông thường | Tính đường dẫn import theo vị trí buildfile nhập và kiểm tra cấu trúc repository |
| Sub-build dùng nhầm `basedir` của project cha | Task `<ant>` đang kế thừa `basedir` theo quy tắc mặc định | Đặt `dir` hoặc `useNativeBasedir="true"` theo mục tiêu thực tế |

## 15. Checklist khi tái sử dụng buildfile

- [ ] Đã chọn đúng cơ chế: `<import>`, `<include>` hay task `<ant>`.
- [ ] Buildfile nhập có thuộc tính `name` duy nhất và ổn định.
- [ ] Đã hiểu `basedir` của buildfile nhập bị bỏ qua khi dùng import/include.
- [ ] Các tài nguyên cạnh buildfile được tham chiếu qua `ant.file.<project-name>` và `<dirname>` khi nguồn là file hệ thống.
- [ ] Các đường dẫn được tạo bằng property có prefix để tránh xung đột.
- [ ] Thuộc tính `file` của import được phân biệt với các thuộc tính đường dẫn thông thường.
- [ ] Prefix target được dùng nhất quán khi khai báo `depends` và gọi target.
- [ ] Tài nguyên URL được xử lý bằng task hỗ trợ resource/URL, không ghép như đường dẫn filesystem.
- [ ] Nếu gọi sub-build bằng `<ant>`, `dir`, `inheritAll` và `useNativeBasedir` được cấu hình có chủ đích.
- [ ] Đã chạy thử buildfile dùng chung độc lập và thông qua project nhập nếu cả hai cách đều được hỗ trợ.

Quản lý `basedir` đúng cách giúp buildfile dùng chung hoạt động ổn định dù được nhập từ nhiều project. Hãy xem `basedir` là thư mục của project đang chạy, còn `ant.file.<project-name>` là vị trí của từng buildfile được nhập. Kết hợp property đặc biệt với `<dirname>` sẽ giúp tài nguyên nằm cạnh buildfile được tìm thấy đúng chỗ mà không phụ thuộc thư mục làm việc của người gọi.

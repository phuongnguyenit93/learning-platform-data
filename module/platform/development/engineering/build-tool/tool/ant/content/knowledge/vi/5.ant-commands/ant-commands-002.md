# Chạy target mặc định, target cụ thể và nhiều target trong Apache Ant

Apache Ant điều khiển build thông qua các target được khai báo trong build file. Khi gọi lệnh ant, bạn có thể để Ant chọn target mặc định, chỉ định một target cụ thể hoặc yêu cầu nhiều target trong cùng một lần chạy. Target cũng có thể phụ thuộc vào target khác, nên cần hiểu cả thứ tự trên dòng lệnh lẫn đồ thị dependency để dự đoán chính xác những công việc sẽ được thực hiện.

## 1. Cú pháp chung của lệnh Ant

Cú pháp tổng quát:

~~~bash
ant [options] [target [target2 [target3] ...]]
~~~

Trong đó:

- **ant** là chương trình khởi chạy Apache Ant.
- **options** là các tùy chọn điều khiển build file, property, mức log hoặc cách xử lý lỗi.
- **target** là tên target được khai báo trong build file.
- Bạn có thể ghi nhiều tên target sau các tùy chọn; Ant xử lý chúng theo thứ tự được chỉ định.

Ví dụ:

~~~bash
ant
ant compile
ant clean compile
ant clean compile test package
~~~

| Lệnh | Ý nghĩa |
|---|---|
| `ant` | Chạy target mặc định của project. |
| `ant compile` | Chạy target `compile` và các dependency của nó. |
| `ant clean compile` | Chạy `clean`, sau đó chạy `compile` cùng dependency cần thiết. |
| `ant clean compile test package` | Yêu cầu chạy lần lượt các target theo thứ tự ghi trên dòng lệnh, đồng thời xử lý dependency của từng target. |

Ant cần tìm được build file để đọc các target. Theo mặc định, Ant tìm `build.xml` trong thư mục làm việc hiện tại. Nếu file có tên khác hoặc nằm ở vị trí khác, dùng tùy chọn `-f` để chỉ rõ file.

~~~bash
ant -f build.xml compile
ant -f build/release.xml package
~~~

Trên Windows hoặc khi đường dẫn có khoảng trắng, đặt đường dẫn trong dấu nháy kép:

~~~powershell
ant -f "build scripts/release.xml" package
~~~

`-f` là dạng viết ngắn; `-file` và `-buildfile` cũng có thể dùng để chỉ định build file.

## 2. Chạy target mặc định

### 2.1. Khai báo target mặc định trong project

Target mặc định được chỉ định bằng thuộc tính `default` của phần tử `<project>`:

~~~xml
<project name="sample-app" default="package" basedir=".">

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source code"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Create application package"/>
    </target>

</project>
~~~

Trong ví dụ này:

- Project có tên `sample-app`.
- Target mặc định là `package`.
- `package` phụ thuộc vào `compile`.
- `compile` phụ thuộc vào `init`.

Khi chạy:

~~~bash
ant
~~~

Ant chọn `package` làm target được yêu cầu. Trước khi thực hiện phần thân của `package`, Ant thực hiện các dependency theo thứ tự. Luồng công việc là:

~~~text
init → compile → package
~~~

Gọi target mặc định không có nghĩa là Ant chạy tất cả target trong file. Ant chỉ chạy target mặc định cùng các target cần thiết theo dependency của nó.

### 2.2. Target mặc định là tên target, không phải một lệnh đặc biệt

Trong khai báo:

~~~xml
<project name="sample-app" default="package">
~~~

`package` vẫn là một target bình thường được đặt tên trong build file. Thuộc tính `default` chỉ cho Ant biết cần chọn target nào khi người dùng không ghi tên target trên dòng lệnh.

Hai lệnh sau thường tạo ra cùng chuỗi thực thi:

~~~bash
ant
ant package
~~~

Điều kiện là build file đang dùng có `default="package"` và không có tùy chọn hoặc cấu hình khác làm thay đổi việc chọn build file.

Nếu gọi một target khác:

~~~bash
ant compile
~~~

Ant chạy `compile` cùng dependency của nó. Target mặc định `package` không được tự động chạy sau đó.

### 2.3. Khi nào nên dùng target mặc định?

Target mặc định nên đại diện cho thao tác tổng thể mà người dùng thường muốn thực hiện, ví dụ:

- `package`: tạo artifact có thể phân phối.
- `build`: thực hiện các bước build chính.
- `test`: chạy bộ kiểm thử mặc định.
- `verify`: chạy chuỗi kiểm tra trước khi phát hành.

Tên target mặc định phụ thuộc vào quy ước của project. Ant không bắt buộc target mặc định phải tên `default`, `build` hay `package`.

Nếu muốn hỗ trợ lệnh `ant` không có đối số, project cần khai báo `default` trỏ đến một target tồn tại. Trong project có nhiều thao tác khác nhau, hãy chọn một target mặc định có hành vi dễ dự đoán.

## 3. Chạy một target cụ thể

Bạn có thể chạy trực tiếp bất kỳ target nào được khai báo trong build file bằng cách ghi tên target sau lệnh Ant.

Ví dụ:

~~~xml
<project name="sample-app" default="package">

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source code"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Package application"/>
    </target>

</project>
~~~

Một số cách gọi:

~~~bash
ant clean
ant init
ant compile
ant package
~~~

Mỗi lệnh yêu cầu Ant thực hiện target tương ứng. Nếu target có thuộc tính `depends`, Ant thực hiện các dependency trước target đó.

Với `compile depends="init"`:

~~~bash
ant compile
~~~

Ant chạy `init` rồi mới chạy `compile`.

Với `package depends="compile"` và `compile depends="init"`:

~~~bash
ant package
~~~

Ant chạy `init`, `compile`, rồi `package`.

Bạn có thể gọi một target dependency trực tiếp dù nó không phải target mặc định. Điều này hữu ích khi chỉ muốn thực hiện một giai đoạn, chẳng hạn chuẩn bị thư mục hoặc biên dịch mà chưa cần đóng gói.

### 3.1. Gọi target không đồng nghĩa chạy các target đứng trước nó trong file

Ant không tự chạy target chỉ vì target đó được viết phía trên target được gọi.

Ví dụ:

~~~xml
<project name="sample-app" default="package">

    <target name="clean">
        <echo message="Clean"/>
    </target>

    <target name="compile">
        <echo message="Compile"/>
    </target>

    <target name="package">
        <echo message="Package"/>
    </target>

</project>
~~~

Lệnh:

~~~bash
ant package
~~~

chỉ chạy `package`, bởi target này không khai báo dependency. `clean` và `compile` không tự động chạy chỉ vì chúng xuất hiện trước `package` trong XML.

Nếu muốn `package` cần `compile`, phải mô tả rõ:

~~~xml
<target name="package" depends="compile">
    <echo message="Package"/>
</target>
~~~

Cấu trúc dependency mới là căn cứ để Ant quyết định các target phải chạy trước.

## 4. Chạy nhiều target trong một lần gọi

Ant cho phép ghi nhiều target trên cùng dòng lệnh:

~~~bash
ant clean compile test package
~~~

Các target được yêu cầu theo thứ tự từ trái sang phải. Với mỗi target, Ant xử lý dependency trước khi thực hiện phần thân của target đó.

Ví dụ:

~~~xml
<project name="sample-app" default="package">

    <target name="clean">
        <echo message="1. Clean output"/>
    </target>

    <target name="init">
        <echo message="2. Prepare build"/>
    </target>

    <target name="compile" depends="init">
        <echo message="3. Compile source"/>
    </target>

    <target name="test" depends="compile">
        <echo message="4. Run tests"/>
    </target>

    <target name="package" depends="compile">
        <echo message="5. Create package"/>
    </target>

    <target name="docs">
        <echo message="6. Generate documentation"/>
    </target>

</project>
~~~

Lệnh:

~~~bash
ant clean package test docs
~~~

được xử lý theo trình tự:

~~~text
clean
  ↓
init
  ↓
compile
  ↓
package
  ↓
test
  ↓
docs
~~~

Giải thích:

1. Ant chạy `clean` trước vì đây là target đầu tiên trên dòng lệnh.
2. Ant chuyển đến `package`. Target này cần `compile`; `compile` cần `init`, nên Ant chạy `init` rồi `compile`, sau đó mới chạy `package`.
3. Ant chuyển đến `test`. `test` cũng phụ thuộc `compile`, nhưng `compile` đã chạy trong cùng lần gọi Ant nên Ant không thực hiện lại target đó. Ant chạy phần thân của `test`.
4. Ant chạy `docs` sau cùng vì đây là target tiếp theo được yêu cầu và không có dependency trong ví dụ.

Thứ tự khai báo target trên dòng lệnh có ý nghĩa. Ant không tự sắp xếp các target độc lập theo tên hoặc theo vị trí của chúng trong build file.

### 4.1. Một dependency được dùng chung chỉ chạy một lần

Giả sử hai target cùng phụ thuộc `compile`:

~~~xml
<target name="compile">
    <echo message="Compile once"/>
</target>

<target name="test" depends="compile">
    <echo message="Test"/>
</target>

<target name="package" depends="compile">
    <echo message="Package"/>
</target>
~~~

Khi gọi:

~~~bash
ant test package
~~~

Ant thực hiện `compile`, rồi `test`, rồi `package`. Target `compile` chỉ chạy một lần trong lần gọi build đó, dù nó được yêu cầu qua hai nhánh dependency.

Tương tự, nếu một target vừa là dependency vừa được ghi trực tiếp trên dòng lệnh, Ant không thực hiện lại target đó trong cùng lần gọi.

Đây là hành vi quan trọng khi thiết kế chuỗi build có nhiều target cùng sử dụng bước chuẩn bị, biên dịch hoặc tạo resource.

### 4.2. Thứ tự dependency bên trong target

Khi một target có nhiều dependency, thứ tự liệt kê trong `depends` quyết định thứ tự xử lý các dependency:

~~~xml
<target name="package" depends="compile,copy-resources,prepare-metadata">
    <echo message="Package application"/>
</target>
~~~

Ant xử lý `compile`, sau đó `copy-resources`, rồi `prepare-metadata`, trước khi chạy các task trong `package` (đồng thời vẫn tuân theo dependency riêng của từng target).

Nên liệt kê dependency theo thứ tự mà quy trình thực sự cần. Nếu các bước không phụ thuộc lẫn nhau về dữ liệu, thứ tự vẫn xác định cách Ant đi qua đồ thị target, nhưng không nên dựa vào thứ tự tình cờ để thay thế một dependency bị thiếu.

## 5. Thứ tự target trên dòng lệnh và dependency khác nhau thế nào?

Hai cơ chế này thường bị nhầm lẫn:

- Danh sách target trên dòng lệnh cho biết những target gốc mà người dùng muốn chạy và thứ tự yêu cầu chúng.
- Thuộc tính `depends` cho biết một target cần target nào hoàn thành trước khi bản thân nó chạy.

Ví dụ:

~~~xml
<target name="compile" depends="init">
    <echo message="Compile"/>
</target>

<target name="package" depends="compile">
    <echo message="Package"/>
</target>
~~~

Lệnh:

~~~bash
ant package clean
~~~

yêu cầu `package` trước rồi mới đến `clean`. Vì `package` phụ thuộc `compile`, và `compile` phụ thuộc `init`, thứ tự là:

~~~text
init → compile → package → clean
~~~

Ngược lại:

~~~bash
ant clean package
~~~

có thứ tự:

~~~text
clean → init → compile → package
~~~

Nếu `clean` xóa thư mục đầu ra, hai lệnh này có kết quả cuối cùng khác nhau: lệnh đầu tiên có thể xóa artifact vừa tạo; lệnh thứ hai dọn dẹp trước rồi mới tạo artifact.

Do đó, khi kết hợp target có tác động đối lập như `clean` và `package`, hãy đặt chúng theo thứ tự mong muốn một cách rõ ràng.

## 6. Dùng property và tùy chọn cùng target

Ngoài tên target, lệnh Ant có thể nhận property từ dòng lệnh để thay đổi cấu hình của build.

### 6.1. Truyền property bằng -D

Cú pháp:

~~~bash
ant -Dproperty.name=value target
~~~

Ví dụ build file:

~~~xml
<project name="sample-app" default="package">

    <property name="environment" value="local"/>
    <property name="app.version" value="1.0.0"/>

    <target name="package">
        <echo message="Environment: ${environment}"/>
        <echo message="Version: ${app.version}"/>
    </target>

</project>
~~~

Nếu chạy:

~~~bash
ant package
~~~

Ant sử dụng các giá trị mặc định `local` và `1.0.0`.

Nếu chạy:

~~~bash
ant -Denvironment=staging -Dapp.version=2.5.0 package
~~~

Ant sử dụng giá trị được truyền từ dòng lệnh. Property đã được đặt trước sẽ không bị khai báo mặc định thông thường trong build file ghi đè, theo nguyên tắc first definition wins của Ant.

Có thể kết hợp property với nhiều target:

~~~bash
ant -Denvironment=production clean package deploy
~~~

Trong ví dụ này, Ant nhận property `environment` cho toàn bộ lần chạy build, rồi xử lý các target theo thứ tự đã yêu cầu và dependency tương ứng.

### 6.2. Chỉ định build file bằng -f

Khi có nhiều build file hoặc bạn đang đứng ở thư mục khác với thư mục chứa build file, hãy dùng `-f`:

~~~bash
ant -f path/to/build.xml package
~~~

Có thể kết hợp `-f`, `-D` và nhiều target:

~~~bash
ant -f build/release.xml -Denvironment=production clean package deploy
~~~

Tùy chọn nên được đặt trước danh sách target để lệnh dễ đọc và dễ phân tích.

### 6.3. Xem danh sách target bằng -projecthelp

Khi chưa biết build file cung cấp những target nào, dùng:

~~~bash
ant -projecthelp
~~~

Hoặc dạng viết ngắn:

~~~bash
ant -p
~~~

Ant hiển thị thông tin trợ giúp và các target có mô tả. Để target xuất hiện với phần mô tả dễ hiểu, nên khai báo thuộc tính `description`:

~~~xml
<target name="compile" description="Compile application source">
    <echo message="Compile"/>
</target>
~~~

`-projecthelp` giúp khám phá các thao tác mà build file công bố. Nó không chạy các target build thông thường.

## 7. Điều gì xảy ra khi một target thất bại?

Theo mặc định, Ant dừng lần chạy build khi gặp lỗi làm target thất bại. Những target phụ thuộc vào kết quả của target lỗi không thể tiếp tục như bình thường.

Ví dụ:

~~~xml
<target name="compile">
    <fail message="Compilation failed"/>
</target>

<target name="test" depends="compile">
    <echo message="Test"/>
</target>

<target name="docs">
    <echo message="Generate docs"/>
</target>
~~~

Lệnh:

~~~bash
ant test docs
~~~

Nếu `compile` thất bại, target `test` không thể thực hiện vì dependency của nó không hoàn thành. Theo hành vi mặc định, Ant dừng lần chạy build khi lỗi xảy ra, nên `docs` cũng không được thực hiện trong lần chạy này.

### 7.1. Tùy chọn -keep-going

Ant cung cấp `-keep-going` (hoặc `-k`) để tiếp tục thực hiện các target không phụ thuộc vào target đã thất bại:

~~~bash
ant -keep-going test docs
~~~

Với tùy chọn này:

- Ant vẫn báo lỗi của target thất bại.
- Target phụ thuộc vào target lỗi sẽ không được thực hiện như thể dependency đã thành công.
- Những target độc lập không phụ thuộc vào nhánh lỗi có thể tiếp tục chạy.
- Kết quả cuối cùng vẫn phản ánh rằng build có lỗi.

`-keep-going` hữu ích khi một lần chạy có nhiều target độc lập và bạn muốn thu thập thêm kết quả. Nó không biến dependency thất bại thành thành công và không bảo đảm mọi target đều chạy được.

## 8. Ví dụ hoàn chỉnh về lựa chọn target

File `build.xml` sau minh họa target mặc định, target cụ thể, dependency, nhiều target và property từ dòng lệnh:

~~~xml
<project name="sample-app" default="package" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="environment" value="local"/>
    <property name="app.version" value="1.0.0"/>

    <target name="clean"
            description="Remove previous build output">
        <delete dir="${build.dir}"/>
    </target>

    <target name="init"
            description="Create build directories">
        <mkdir dir="${build.dir}/classes"/>
        <mkdir dir="${build.dir}/dist"/>
    </target>

    <target name="compile"
            depends="init"
            description="Compile application source">
        <echo message="Compile for ${environment}"/>
    </target>

    <target name="test"
            depends="compile"
            description="Run application tests">
        <echo message="Run tests"/>
    </target>

    <target name="package"
            depends="compile"
            description="Create application package">
        <echo message="Package version ${app.version}"/>
    </target>

    <target name="deploy"
            depends="package"
            description="Deploy packaged application">
        <echo message="Deploy to ${environment}"/>
    </target>

    <target name="docs"
            description="Generate project documentation">
        <echo message="Generate documentation"/>
    </target>

</project>
~~~

Các lệnh tiêu biểu:

| Mục tiêu | Lệnh |
|---|---|
| Chạy target mặc định `package`. | `ant` |
| Chạy riêng target `compile` và dependency. | `ant compile` |
| Dọn đầu ra rồi đóng gói. | `ant clean package` |
| Chạy test rồi đóng gói. | `ant test package` |
| Đóng gói rồi triển khai. | `ant deploy` |
| Chạy nhiều target độc lập theo thứ tự. | `ant docs clean` |
| Đóng gói với môi trường staging. | `ant -Denvironment=staging package` |
| Dọn, đóng gói và triển khai lên production. | `ant -Denvironment=production clean deploy` |
| Xem danh sách target. | `ant -projecthelp` |

Trong ví dụ này, task `echo` được dùng để thể hiện luồng điều khiển. Trong build thực tế, bạn có thể thay bằng `javac`, `copy`, `jar`, task kiểm thử hoặc task triển khai tương ứng. Quan hệ target và cách gọi dòng lệnh vẫn giữ nguyên.

### 8.1. Phân tích lệnh ant -Denvironment=production clean deploy

Đây là một lệnh kết hợp nhiều cơ chế:

1. `-Denvironment=production` đặt property cho lần chạy build.
2. `clean` là target đầu tiên được yêu cầu; nó xóa thư mục build.
3. `deploy` là target tiếp theo. `deploy` phụ thuộc `package`.
4. `package` phụ thuộc `compile`; `compile` phụ thuộc `init`.
5. Ant thực hiện `init`, `compile`, `package`, rồi `deploy`.
6. Các task sử dụng property `environment` sẽ nhận giá trị `production`.

Chuỗi thực thi:

~~~text
clean → init → compile → package → deploy
~~~

Target `test` không nằm trong dependency của `deploy`, nên lệnh này không tự chạy `test`. Nếu cần kiểm thử trước khi triển khai, hãy khai báo `deploy` phụ thuộc `test` hoặc ghi rõ target `test` trong lệnh gọi theo đúng quy trình của project.

## 9. Các nhầm lẫn thường gặp

### 9.1. Nghĩ rằng chạy ant sẽ chạy tất cả target

Lệnh không có tên target chỉ chạy target được chỉ định trong thuộc tính `default` của project và các dependency cần thiết. Target độc lập khác không tự động chạy.

### 9.2. Nghĩ rằng target mặc định luôn tên là default hoặc build

`default` là tên thuộc tính trên phần tử project. Giá trị của nó là tên một target thực tế, ví dụ `package`, `build` hoặc `verify`.

### 9.3. Nghĩ rằng target đứng trước trong XML sẽ chạy trước

Vị trí khai báo trong XML không khiến target độc lập tự động được thực hiện. Ant dựa vào target được gọi và dependency của chúng.

### 9.4. Nghĩ rằng nhiều target trên dòng lệnh có thể chạy theo thứ tự tùy ý

Ant xử lý các target gốc theo thứ tự được ghi trên dòng lệnh. Dependency của mỗi target được thực hiện trước target tương ứng. Vì vậy, thay đổi vị trí `clean`, `package` hoặc `deploy` có thể thay đổi kết quả cuối cùng.

### 9.5. Nghĩ rằng dependency chung sẽ bị chạy lại

Một target đã được thực hiện trong lần gọi Ant hiện tại sẽ không được thực hiện lần thứ hai chỉ vì target khác cũng phụ thuộc vào nó.

### 9.6. Nghĩ rằng -keep-going bỏ qua mọi lỗi

`-keep-going` cho phép Ant tiếp tục các nhánh không phụ thuộc vào target thất bại. Target cần kết quả từ dependency lỗi vẫn không thể chạy đúng.

### 9.7. Nghĩ rằng -D là tên target

`-Dname=value` là tùy chọn đặt property. Tên target là đối số riêng sau các tùy chọn, ví dụ `ant -Denv=staging package`.

## 10. Cách chọn lệnh phù hợp

Khi quyết định chạy lệnh Ant, hãy xác định rõ kết quả cần đạt:

1. Nếu muốn thực hiện quy trình mặc định của project, chạy `ant`.
2. Nếu chỉ cần một giai đoạn, gọi trực tiếp target đó, ví dụ `ant compile`.
3. Nếu cần dọn kết quả trước khi build, đặt `clean` trước target build, ví dụ `ant clean package`.
4. Nếu cần nhiều bước độc lập, ghi các target theo đúng thứ tự mong muốn, ví dụ `ant compile test docs`.
5. Nếu target đã mô tả đầy đủ dependency, chỉ cần gọi target cuối cùng, ví dụ `ant deploy`.
6. Nếu cần cấu hình theo môi trường, truyền property bằng `-D`, ví dụ `ant -Denvironment=staging deploy`.
7. Nếu chưa rõ target có sẵn, xem `ant -projecthelp`.
8. Nếu cần tiếp tục các nhánh độc lập sau một lỗi, cân nhắc `ant -keep-going ...` và đọc kỹ kết quả lỗi.

Trước khi chạy một lệnh có `clean`, `delete` hoặc thao tác triển khai, hãy đọc phần thân target để hiểu tác động của nó. Thứ tự target là một phần của ý nghĩa lệnh, đặc biệt khi một target xóa đầu ra mà target khác vừa tạo.

## 11. Ghi nhớ

- **`ant`** không kèm target sẽ chọn target được khai báo trong thuộc tính `default` của project.
- **`ant targetName`** chạy target cụ thể và các dependency cần thiết.
- **`ant targetA targetB`** yêu cầu nhiều target theo thứ tự từ trái sang phải; dependency được thực hiện trước target tương ứng.
- Một target chỉ được thực hiện một lần trong cùng một lần gọi Ant, kể cả khi nhiều target cùng phụ thuộc vào nó.
- **`depends`** mô tả quan hệ giữa các target; danh sách target trên dòng lệnh mô tả các thao tác người dùng muốn gọi.
- **`-f`** chọn build file; **`-D`** truyền property; **`-projecthelp`** liệt kê trợ giúp; **`-keep-going`** cho phép tiếp tục các nhánh độc lập sau lỗi.
- Đặt `clean`, `package`, `deploy` theo đúng thứ tự mong muốn vì thứ tự gọi có thể làm thay đổi kết quả cuối cùng.

Khi hiểu sự khác nhau giữa target mặc định, target được gọi trực tiếp, danh sách target trên dòng lệnh và dependency, bạn có thể điều khiển build Ant chính xác mà không cần gọi riêng từng bước đã được mô tả trong dependency của project.


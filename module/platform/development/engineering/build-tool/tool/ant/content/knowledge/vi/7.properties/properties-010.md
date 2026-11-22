# Tổ chức cấu hình mặc định, cấu hình cá nhân và cấu hình môi trường

Một build file Ant thường cần những giá trị có thể thay đổi theo máy phát triển hoặc môi trường chạy build: thư mục đầu ra, đường dẫn JDK, cờ biên dịch, địa chỉ máy chủ kiểm thử hay tên môi trường triển khai. Nếu ghi cứng tất cả giá trị vào task, mỗi lần chuyển máy hoặc chạy CI người dùng lại phải sửa XML.

Ant cung cấp **property** để tách dữ liệu cấu hình khỏi các task. Có thể tổ chức cấu hình thành nhiều lớp: giá trị mặc định của dự án, giá trị riêng của người dùng, biến môi trường của hệ điều hành và giá trị truyền từ dòng lệnh. Khi thiết kế đúng thứ tự nạp, một build file có thể dùng chung cho nhiều máy mà vẫn cho phép mỗi người hoặc pipeline điều chỉnh các giá trị cần thiết.

## 1. Property là nền tảng của cấu hình Ant

Property là một cặp tên và giá trị. Tên property được dùng trong build file bằng cú pháp `${property.name}`.

~~~xml
<project name="inventory" default="compile" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="debug" value="true"/>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               debug="${debug}"
               includeantruntime="false"/>
    </target>
</project>
~~~

Trong ví dụ:

- `src.dir` lưu đường dẫn mã nguồn.
- `build.dir` lưu thư mục đầu ra.
- `debug` lưu tùy chọn biên dịch.
- Các task tham chiếu giá trị thông qua `${...}`, vì vậy không phải lặp lại cùng một giá trị ở nhiều nơi.

Hai thuộc tính thường dùng khi khai báo property:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên property |
| `value` | Giá trị văn bản |
| `location` | Đường dẫn; Ant chuẩn hóa thành đường dẫn tuyệt đối theo ngữ cảnh base directory |
| `file` | Nạp các property từ tệp properties |
| `environment` | Nhập biến môi trường của hệ điều hành với tiền tố được chỉ định |

Property có phạm vi dùng chung trong project. Trong cách sử dụng thông thường, một khi property đã được thiết lập thì khai báo `property` tiếp theo cùng tên không ghi đè giá trị trước đó. Đây là quy tắc **first one wins** (giá trị được thiết lập trước sẽ được giữ lại). Quy tắc này là cơ sở để tổ chức thứ tự ưu tiên cấu hình.

## 2. Cấu hình mặc định của dự án

Cấu hình mặc định là những giá trị giúp build có thể chạy với ít tham số nhất. Chúng thường được đặt trong một tệp properties thuộc dự án hoặc khai báo ngay trong build file.

Ví dụ, tệp `config/build.properties`:

~~~properties
# Default project build configuration
src.dir=src/main/java
build.dir=build
classes.dir=build/classes
dist.dir=build/dist
compiler.debug=true
~~~

Build file nạp tệp này:

~~~xml
<property file="config/build.properties"/>
~~~

Tệp properties dùng cú pháp Java Properties:

- Mỗi dòng thường có dạng `name=value` hoặc `name: value`.
- Dòng bắt đầu bằng `#` hoặc `!` là chú thích.
- Không dùng cấu trúc XML hay YAML.
- Các giá trị được đọc dưới dạng chuỗi; task sử dụng chúng theo thuộc tính tương ứng.
- Ký tự đặc biệt và dấu gạch chéo ngược trong giá trị cần tuân theo quy tắc escape của Java Properties.

Nếu cần biểu diễn đường dẫn Windows trong tệp properties, có thể dùng dấu gạch chéo xuôi, ví dụ `build.dir=C:/work/inventory/build`, để tránh nhầm dấu gạch chéo ngược với ký tự escape.

Cấu hình mặc định nên chứa giá trị chung, không nhạy cảm và có thể dùng trên nhiều máy. Ví dụ phù hợp là thư mục nguồn, thư mục đầu ra tương đối, chế độ debug mặc định hoặc tên artifact. Không nên đưa mật khẩu, token hay khóa riêng vào tệp mặc định được commit vào repository.

## 3. Cấu hình cá nhân theo từng người dùng

Mỗi lập trình viên có thể cần một số giá trị riêng: thư mục build ngoài workspace, đường dẫn công cụ cục bộ hoặc tùy chọn debug cá nhân. Những giá trị này không nên buộc cả nhóm thay đổi cấu hình dự án.

Ant cung cấp property hệ thống `user.home`, đại diện cho thư mục home của tài khoản đang chạy Java. Có thể nạp một tệp cấu hình cá nhân từ vị trí đó:

~~~xml
<property file="${user.home}/.inventory-ant.properties"/>
~~~

Ví dụ tệp `~/.inventory-ant.properties` trên máy của một developer:

~~~properties
build.dir=D:/work-output/inventory
compiler.debug=true
local.report.dir=D:/reports/inventory
~~~

Trên Linux hoặc macOS, tệp có thể nằm ở:

~~~text
/home/alex/.inventory-ant.properties
~~~

hoặc:

~~~text
/Users/alex/.inventory-ant.properties
~~~

Tên và vị trí tệp là quy ước do dự án lựa chọn; Ant không tự động đọc mọi tệp có tên tùy ý trong home. Build file phải khai báo rõ `<property file="..."/>` để nạp tệp đó.

Để cấu hình cá nhân có thể ghi đè mặc định của dự án, hãy nạp tệp cá nhân trước tệp mặc định:

~~~xml
<property file="${user.home}/.inventory-ant.properties"/>
<property file="config/build.properties"/>
~~~

Vì property thông thường không ghi đè giá trị đã có, nếu cả hai tệp cùng định nghĩa `build.dir`, giá trị từ tệp cá nhân được giữ lại. Nếu người dùng không có tệp cá nhân hoặc tệp đó không khai báo một property cụ thể, Ant tiếp tục lấy giá trị từ cấu hình dự án.

Tệp cá nhân thường không được commit vào repository. Có thể cung cấp một tệp mẫu như `config/build.properties.example` để thành viên biết các tên property được hỗ trợ mà không phải chia sẻ cấu hình riêng của máy.

## 4. Lấy cấu hình từ biến môi trường của hệ điều hành

Một số giá trị do hệ điều hành hoặc môi trường chạy cung cấp, chẳng hạn `JAVA_HOME`, đường dẫn công cụ hoặc tên môi trường triển khai. Ant có thể nhập các biến môi trường bằng thuộc tính `environment`:

~~~xml
<property environment="env"/>
~~~

Khi đó, biến môi trường được đưa vào project dưới tiền tố `env.`. Ví dụ, nếu hệ điều hành có `JAVA_HOME`, build file có thể tham chiếu:

~~~xml
<echo message="JAVA_HOME = ${env.JAVA_HOME}"/>
~~~

Tên property môi trường phụ thuộc tên biến mà hệ điều hành cung cấp. Trên Windows, tên biến môi trường thường không phân biệt hoa thường; trên hệ thống Unix-like, tên biến có phân biệt hoa thường. Hãy dùng đúng cách viết được môi trường cung cấp và tránh giả định rằng mọi máy đều có cùng biến.

Việc nhập môi trường chỉ đọc các giá trị đã có trong tiến trình Ant. Nó không tạo hoặc sửa biến môi trường hệ điều hành, không thay đổi cấu hình người dùng và không tự động làm cho biến tồn tại ở những lần chạy sau.

### Chuyển một biến môi trường thành property cấu hình

Giả sử pipeline hoặc developer có biến `INVENTORY_BUILD_DIR`, nhưng task muốn sử dụng một property thống nhất là `build.dir`. Có thể ánh xạ biến đó bằng task `condition`:

~~~xml
<property environment="env"/>

<condition property="build.dir" value="${env.INVENTORY_BUILD_DIR}">
    <isset property="env.INVENTORY_BUILD_DIR"/>
</condition>

<property name="build.dir" location="build"/>
~~~

Thứ tự này có ý nghĩa:

1. Nhập các biến môi trường với tiền tố `env.`.
2. Nếu `env.INVENTORY_BUILD_DIR` tồn tại và `build.dir` chưa được thiết lập, dùng giá trị môi trường làm `build.dir`.
3. Nếu chưa có giá trị nào cho `build.dir`, dùng thư mục mặc định `build`.

Điều kiện `isset` kiểm tra property có tồn tại hay không. Nó không diễn giải chuỗi `false` thành boolean false. Vì vậy, nếu biến môi trường được định nghĩa với giá trị rỗng hoặc chuỗi không mong muốn, cần quy định và kiểm tra giá trị đầu vào phù hợp với chính sách cấu hình của dự án.

## 5. Cấu hình từ dòng lệnh

Khi chạy Ant, người dùng có thể truyền property bằng tùy chọn `-D`:

~~~bash
ant -Dbuild.dir=build-local compile
~~~

Trong ví dụ này, `build.dir` nhận giá trị `build-local` cho lượt chạy đó. Build file có thể dùng property như mọi property khác.

Property truyền bằng `-D` là **user property**. Nó được thiết lập trước khi Ant xử lý build file và có ưu tiên cao hơn các giá trị thông thường khai báo trong build file hoặc tệp properties được nạp bằng task `property`. Đây là cách tiện lợi để thay đổi cấu hình trong một lần chạy mà không phải sửa tệp.

Có thể truyền nhiều property:

~~~bash
ant -Denv=ci -Dcompiler.debug=false -Dbuild.dir=build-ci package
~~~

Trên PowerShell, cách viết lệnh cũng tương tự:

~~~powershell
ant -Denv=ci -Dcompiler.debug=false -Dbuild.dir=build-ci package
~~~

Property từ dòng lệnh không được ghi ngược trở lại tệp properties. Khi kết thúc tiến trình Ant, các giá trị này không tự lưu thành cấu hình lâu dài.

### Nạp một tệp properties từ dòng lệnh

Ant hỗ trợ tùy chọn `-propertyfile`:

~~~bash
ant -propertyfile config/ci.properties package
~~~

Ví dụ `config/ci.properties`:

~~~properties
env=ci
build.dir=build-ci
compiler.debug=false
~~~

Có thể kết hợp với `-D`:

~~~bash
ant -propertyfile config/ci.properties -Dbuild.dir=build-debug package
~~~

Giá trị truyền trực tiếp bằng `-D` có ưu tiên cao hơn property cùng tên được nạp từ `-propertyfile`. Tùy chọn `-propertyfile` phù hợp khi cần chọn một bộ cấu hình cho lượt build; `-D` phù hợp cho giá trị cần ghi đè riêng trong lần chạy đó.

## 6. Thứ tự ưu tiên giữa các lớp cấu hình

Do property thông thường không ghi đè giá trị đã thiết lập, **thứ tự nạp** quyết định lớp cấu hình nào được ưu tiên.

Một quy ước hữu ích cho dự án Ant là:

1. User properties từ dòng lệnh (`-D`) và tệp được chỉ định bằng `-propertyfile`.
2. Tệp cấu hình cá nhân trong home của người dùng.
3. Tệp cấu hình chung của dự án.
4. Giá trị lấy từ biến môi trường khi chưa có giá trị khác.
5. Giá trị mặc định khai báo trực tiếp trong build file.

Với property nạp bằng task trong build file, hãy nạp lớp có ưu tiên cao trước:

~~~xml
<property environment="env"/>

<!-- Cá nhân được ưu tiên hơn cấu hình mặc định của dự án -->
<property file="${user.home}/.inventory-ant.properties"/>

<!-- Cấu hình chung của repository -->
<property file="config/build.properties"/>

<!-- Môi trường là fallback nếu chưa có build.dir -->
<condition property="build.dir" value="${env.INVENTORY_BUILD_DIR}">
    <isset property="env.INVENTORY_BUILD_DIR"/>
</condition>

<!-- Mặc định cuối cùng -->
<property name="build.dir" location="build"/>
~~~

Ở đây, property từ `-D` hoặc `-propertyfile` đã được cung cấp trước khi build file xử lý, nên các khai báo bên trong không thay thế chúng. Tệp cá nhân được nạp trước tệp dự án để có thể ghi đè giá trị chung. Biến môi trường chỉ được dùng nếu hai lớp tệp chưa thiết lập `build.dir`. Giá trị `build` là phương án cuối cùng.

Bảng ví dụ:

| Nguồn | Giá trị `build.dir` | Kết quả khi các lớp đều định nghĩa |
|---|---|---|
| Mặc định trong XML | `build` | Ưu tiên thấp nhất |
| Biến môi trường | `build-from-env` | Dùng nếu các lớp trước chưa thiết lập |
| Tệp dự án | `build-project` | Thay thế fallback môi trường và mặc định |
| Tệp cá nhân | `build-user` | Thay thế cấu hình dự án và fallback |
| `-Dbuild.dir=build-cli` | `build-cli` | Ưu tiên cao nhất |

Điều quan trọng là không chỉ liệt kê các nguồn cấu hình mà phải xác định rõ thứ tự nạp và cách ghi đè. Nếu nạp tệp dự án trước tệp cá nhân, tệp cá nhân sẽ không ghi đè được property đã có. Nếu đặt giá trị mặc định trước các tệp, các tệp sau cũng không thay đổi được giá trị mặc định theo quy tắc thông thường.

## 7. Ví dụ build.xml hoàn chỉnh

Ví dụ sau kết hợp cấu hình dự án, cấu hình cá nhân, biến môi trường và giá trị mặc định. Nó tạo một property `build.dir` thống nhất để các target dùng chung.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="package" basedir=".">

    <!-- Nhập biến môi trường của hệ điều hành -->
    <property environment="env"/>

    <!-- Cấu hình riêng của developer -->
    <property file="${user.home}/.inventory-ant.properties"/>

    <!-- Cấu hình mặc định của repository -->
    <property file="config/build.properties"/>

    <!-- Dùng biến môi trường nếu build.dir chưa được thiết lập -->
    <condition property="build.dir" value="${env.INVENTORY_BUILD_DIR}">
        <isset property="env.INVENTORY_BUILD_DIR"/>
    </condition>

    <!-- Fallback cuối cùng -->
    <property name="build.dir" location="build"/>

    <!-- Các property phụ thuộc build.dir phải được tạo sau khi đã chọn giá trị -->
    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="compiler.debug" value="true"/>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init"
            description="Biên dịch mã nguồn Java">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               debug="${compiler.debug}"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile"
            description="Đóng gói ứng dụng thành JAR">
        <jar destfile="${dist.dir}/inventory.jar"
             basedir="${classes.dir}"/>
    </target>

</project>
~~~

Tệp cấu hình chung `config/build.properties`:

~~~properties
build.dir=build
compiler.debug=true
~~~

Một developer có thể tạo `~/.inventory-ant.properties`:

~~~properties
build.dir=D:/work-output/inventory
compiler.debug=true
~~~

Pipeline có thể cung cấp biến môi trường:

~~~text
INVENTORY_BUILD_DIR=build-ci
~~~

Khi chạy trên pipeline:

~~~bash
ant -Dcompiler.debug=false package
~~~

Ant sử dụng `build.dir` từ tệp cá nhân nếu có; nếu không có thì lấy từ tệp dự án; nếu hai tệp không định nghĩa thì mới xét biến môi trường; cuối cùng dùng `build`. Riêng `compiler.debug` được ghi đè bằng `-Dcompiler.debug=false` cho lượt chạy này.

## 8. Tổ chức cấu hình theo môi trường

Dự án có thể cần các bộ giá trị khác nhau cho local, test, staging hoặc production. Có hai cách phổ biến:

- Dùng cùng tên property nhưng cung cấp giá trị khác nhau qua `-propertyfile` hoặc `-D`.
- Ánh xạ biến môi trường vào property trong build file rồi để task sử dụng property thống nhất.

Ví dụ các tệp cấu hình riêng:

~~~text
config/
├── build.properties
├── local.properties
├── test.properties
└── ci.properties
~~~

Nạp bộ cấu hình CI từ dòng lệnh:

~~~bash
ant -propertyfile config/ci.properties package
~~~

Hoặc truyền riêng một số giá trị:

~~~bash
ant -Dbuild.dir=build-staging -Denv=staging package
~~~

Cách thứ nhất giúp gom các giá trị liên quan thành một bộ cấu hình. Cách thứ hai phù hợp khi chỉ cần thay đổi một vài property. Dù chọn cách nào, nên thống nhất tên property giữa các môi trường để target không cần biết nó đang chạy trên máy cá nhân hay pipeline.

Nếu muốn chọn tệp cấu hình bên trong build file theo property `env`, có thể đặt giá trị mặc định cho tên môi trường trước rồi nạp tệp tương ứng:

~~~xml
<property name="env" value="local"/>
<property file="config/${env}.properties"/>
~~~

Khi đó, có thể gọi:

~~~bash
ant -Denv=ci package
~~~

Do `env` từ `-D` đã được thiết lập trước, Ant nạp `config/ci.properties`. Nếu không truyền `-Denv`, build file dùng `local`. Cần đảm bảo tệp tương ứng tồn tại và chỉ cho phép những profile được dự án hỗ trợ.

## 9. Quản lý thông tin nhạy cảm

Property giúp truyền cấu hình, nhưng bản thân property không phải kho bí mật và không mã hóa giá trị. Không nên commit mật khẩu, access token, private key hoặc credential vào `build.properties`, tệp cấu hình cá nhân mẫu hay build file.

Đối với CI, hãy dùng secret store của nền tảng để cung cấp giá trị cho tiến trình build dưới dạng biến môi trường hoặc cơ chế cấp credential phù hợp. Có thể đọc biến môi trường qua `<property environment="env"/>`, sau đó chuyển giá trị cần thiết vào task. Tránh in giá trị nhạy cảm bằng `echo`, tránh bật log quá chi tiết khi không cần và hạn chế quyền đọc các tệp cấu hình chứa credential.

Tệp cá nhân nên nằm ngoài repository hoặc được thêm vào danh sách ignore. Tệp mẫu trong repository chỉ nên chứa tên property và giá trị ví dụ không nhạy cảm.

## 10. Các lỗi thường gặp khi tổ chức property

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Giá trị trong tệp cá nhân không được dùng | Tệp dự án hoặc giá trị mặc định đã nạp cùng property trước đó | Nạp nguồn ưu tiên cao trước nguồn mặc định |
| `-D` không làm thay đổi task | Task đang dùng tên property khác hoặc giá trị đã được biến đổi ở nơi khác | Kiểm tra tên property trong task và lệnh gọi |
| Property môi trường không tồn tại | Biến môi trường chưa được thiết lập hoặc dùng sai tiền tố/tên | Kiểm tra biến trên hệ điều hành và khai báo `environment` |
| Đường dẫn bị ghép sai | Dùng giá trị tương đối không đúng base directory hoặc khai báo property phụ thuộc quá sớm | Kiểm tra `basedir`, `location` và thứ tự khai báo |
| Cấu hình CI phụ thuộc máy developer | Build file đọc một tệp cá nhân bắt buộc hoặc không có fallback | Cho tệp cá nhân là tùy chọn và cung cấp mặc định dự án |
| Tệp properties không được đọc | Đường dẫn sai hoặc nội dung không đúng cú pháp Java Properties | Kiểm tra vị trí, quyền đọc và cú pháp `name=value` |
| Giá trị cũ vẫn xuất hiện sau khi khai báo lại | Property thông thường không ghi đè giá trị đã thiết lập | Xem lại thứ tự nạp hoặc truyền user property từ dòng lệnh |

Một lỗi đặc biệt phổ biến là đặt property dẫn xuất trước property gốc:

~~~xml
<!-- Không nên: build.dir chưa được chọn -->
<property name="classes.dir" location="${build.dir}/classes"/>

<property file="config/build.properties"/>
<property name="build.dir" location="build"/>
~~~

Hãy chọn `build.dir` trước, sau đó mới xây dựng các đường dẫn phụ thuộc:

~~~xml
<property file="config/build.properties"/>
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
~~~

Cách này làm cho mối quan hệ giữa cấu hình gốc và cấu hình dẫn xuất rõ ràng, đồng thời tránh giữ lại biểu thức chưa được thay thế như mong muốn.

## 11. Nguyên tắc thiết kế cấu hình dễ bảo trì

- Đặt giá trị mặc định không nhạy cảm ở cấp dự án để build có thể chạy ngay trong trường hợp đơn giản.
- Cho phép cấu hình cá nhân ghi đè giá trị chung mà không phải sửa file được chia sẻ.
- Dùng biến môi trường cho dữ liệu do hệ điều hành hoặc CI cung cấp.
- Dùng `-D` cho những điều chỉnh ngắn hạn, có chủ đích trong một lượt chạy.
- Xác định rõ thứ tự nạp vì property thông thường tuân theo quy tắc giá trị được thiết lập trước sẽ thắng.
- Nạp property gốc trước property dẫn xuất như `classes.dir`, `dist.dir` hoặc đường dẫn artifact.
- Giữ bí mật ngoài repository và không in credential trong log.
- Dùng tên property thống nhất giữa local, test, staging và CI để task không phụ thuộc vào tên môi trường cụ thể.

Khi cấu hình được chia thành các lớp rõ ràng, build file Ant có thể giữ nguyên logic task trong khi từng máy hoặc pipeline cung cấp giá trị thích hợp. Giá trị mặc định giúp dự án dễ chạy, cấu hình cá nhân hỗ trợ nhu cầu của developer, biến môi trường kết nối build với hệ điều hành và CI, còn `-D` cho phép ghi đè có chủ đích trong một lần thực thi.


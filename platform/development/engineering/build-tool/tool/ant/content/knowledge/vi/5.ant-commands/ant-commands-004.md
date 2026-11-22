# Truyền property bằng -D và -propertyfile

## 1. Property trong Apache Ant

Ant dùng property để truyền các giá trị cấu hình vào build. Một property là một cặp tên và giá trị, ví dụ:

```text
build.profile=development
app.version=1.4.0
output.dir=build/development
```

Trong build file, giá trị được tham chiếu bằng cú pháp `${name}`:

```xml
<project name="sample" default="show-config">
    <property name="build.profile" value="development"/>
    <property name="output.dir" location="build/${build.profile}"/>

    <target name="show-config">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Output: ${output.dir}"/>
    </target>
</project>
```

Khi chạy `ant show-config`, Ant thay các biểu thức property bằng giá trị tương ứng. Property thường được dùng để cấu hình thư mục đầu ra, phiên bản, tên artifact, cờ bật/tắt một bước build, đường dẫn công cụ hoặc thông tin môi trường.

Property của Ant là giá trị dạng chuỗi. Một task có thể diễn giải chuỗi đó thành số, boolean hoặc đường dẫn theo cách riêng, nhưng bản thân hệ thống property không phải một hệ thống kiểu dữ liệu mạnh.

Ant có hai đặc điểm quan trọng cần hiểu trước khi truyền property từ dòng lệnh:

- Property thông thường có tính bất biến: khi một tên đã được đặt giá trị, một lần đặt thông thường tiếp theo với cùng tên sẽ không thay đổi giá trị đó.
- Property được truyền từ dòng lệnh bằng tùy chọn của Ant là user property. Chúng được ưu tiên hơn giá trị mặc định mà build file khai báo bằng task `<property>`.

Hai tùy chọn thường dùng để truyền cấu hình vào một lần build là `-Dname=value` và `-propertyfile filename`.

## 2. Truyền một property bằng -D

Tùy chọn `-D` của Ant có dạng:

```text
-Dproperty=value
```

Ví dụ:

```bash
ant -Dbuild.profile=ci -Dapp.version=1.4.0 package
```

Trong lệnh này:

- `build.profile` có giá trị `ci`.
- `app.version` có giá trị `1.4.0`.
- `package` là target được yêu cầu chạy.

Build file có thể sử dụng trực tiếp các giá trị đó:

```xml
<project name="sample" default="package">
    <property name="build.profile" value="development"/>
    <property name="app.version" value="0.0.0-local"/>

    <target name="show-config">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Version: ${app.version}"/>
    </target>

    <target name="package" depends="show-config">
        <echo message="Packaging ${app.version} for ${build.profile}"/>
    </target>
</project>
```

Nếu chạy:

```bash
ant -Dbuild.profile=ci -Dapp.version=1.4.0 package
```

thì các giá trị mặc định trong hai task `<property>` không thay thế được giá trị truyền từ dòng lệnh. Ant dùng `ci` và `1.4.0` trong suốt lần chạy đó.

### Khi nào nên dùng -D?

`-D` phù hợp khi cần truyền một vài giá trị thay đổi theo lần chạy:

- Chọn profile như `local`, `ci` hoặc `release`.
- Đặt phiên bản phát hành.
- Bật/tắt một bước tùy chọn.
- Ghi đè một thư mục đầu ra hoặc đường dẫn công cụ.
- Truyền một tham số từ script CI vào build.

Ví dụ chỉ thay profile:

```bash
ant -Dbuild.profile=staging package
```

Ví dụ bật một bước tùy chọn:

```bash
ant -Dtests.enabled=true verify
```

Build file có thể dùng property này để quyết định cấu hình. Nếu cần rẽ nhánh theo điều kiện, có thể kết hợp với các task điều kiện của Ant thay vì viết nhiều lệnh shell bên ngoài.

## 3. Truyền nhiều property bằng -propertyfile

Khi có nhiều cấu hình, viết từng tham số `-D` trên dòng lệnh sẽ dài và khó quản lý. Tùy chọn `-propertyfile` cho phép nạp nhiều property từ một tệp theo định dạng Java Properties:

```text
ant -propertyfile config/ci.properties package
```

Ví dụ tạo tệp `config/ci.properties`:

```properties
# Configuration for CI
build.profile=ci
app.version=1.4.0
tests.enabled=true
output.dir=build/ci
```

Sau đó chạy:

```bash
ant -propertyfile config/ci.properties package
```

Các tên trong tệp trở thành property của project và có thể được tham chiếu bằng `${build.profile}`, `${app.version}`, `${tests.enabled}` và `${output.dir}` trong build file.

Một property file có thể chứa:

- Một cặp `key=value` trên mỗi dòng.
- Dòng chú thích bắt đầu bằng `#` hoặc `!`.
- Khoảng trắng quanh dấu phân cách.
- Giá trị có chứa khoảng trắng.
- Dòng nối tiếp theo cú pháp Java Properties khi một dòng kết thúc bằng dấu gạch chéo ngược.

Ví dụ:

```properties
# Application metadata
app.name=Order Service
app.description=Build for integration testing
build.profile=integration
```

Không cần bọc giá trị trong dấu nháy như YAML hoặc shell. Nếu viết `app.name="Order Service"`, dấu nháy có thể trở thành một phần của giá trị property.

### Tổ chức file theo môi trường

Có thể duy trì một file cho từng môi trường:

```text
config/
├── local.properties
├── ci.properties
└── release.properties
```

Chạy build với file tương ứng:

```bash
ant -propertyfile config/local.properties package
ant -propertyfile config/ci.properties package
ant -propertyfile config/release.properties package
```

Cách này giúp cấu hình theo môi trường nằm trong các tệp có tên rõ ràng. Đường dẫn tương đối của file property nên được xác định theo thư mục làm việc nơi gọi lệnh Ant; nếu script có thể được chạy từ nhiều thư mục khác nhau, hãy chuẩn hóa thư mục làm việc hoặc truyền đường dẫn tuyệt đối để tránh nạp nhầm file.

## 4. Kết hợp -D và -propertyfile

Hai tùy chọn có thể dùng cùng một lần chạy:

```bash
ant -propertyfile config/ci.properties -Dbuild.profile=release package
```

Quy tắc ưu tiên của Ant cho trường hợp này:

1. Property truyền trực tiếp bằng `-Dname=value` có ưu tiên cao hơn property cùng tên trong file được nạp bằng `-propertyfile`.
2. Các property được nạp từ dòng lệnh/file property có ưu tiên cao hơn giá trị mặc định mà build file đặt bằng task `<property>`.
3. Với property thông thường trong build file, lần định nghĩa hợp lệ đầu tiên giữ giá trị; một task `<property>` sau đó không ghi đè giá trị đã có.

Ví dụ file `config/ci.properties`:

```properties
build.profile=ci
app.version=1.4.0
output.dir=build/ci
```

Build file:

```xml
<project name="sample" default="show-config">
    <property name="build.profile" value="development"/>
    <property name="app.version" value="0.0.0-local"/>
    <property name="output.dir" location="build/${build.profile}"/>

    <target name="show-config">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Version: ${app.version}"/>
        <echo message="Output: ${output.dir}"/>
    </target>
</project>
```

Chạy với property file:

```bash
ant -propertyfile config/ci.properties show-config
```

Kết quả cấu hình có các giá trị:

| Property | Giá trị |
|---|---|
| `build.profile` | `ci` |
| `app.version` | `1.4.0` |
| `output.dir` | `build/ci` |

Task `<property>` trong build file không thay các giá trị đã được nạp từ file. Với `output.dir`, giá trị `build/ci` trong property file cũng được giữ lại thay vì giá trị mặc định được tính từ `build.profile`.

Nếu chạy:

```bash
ant -propertyfile config/ci.properties -Dbuild.profile=release show-config
```

thì `build.profile` có giá trị `release`, còn `app.version` vẫn là `1.4.0`. `output.dir` vẫn là `build/ci` vì property đó đã được nạp từ file; Ant không tự tính lại một property đã có chỉ vì property đầu vào khác thay đổi.

Điểm cuối rất quan trọng: property trong Ant không phải biểu thức luôn được tính lại. Nếu muốn một đường dẫn được suy ra từ profile, hãy để file cấu hình chỉ khai báo profile và để build file tạo đường dẫn mặc định; hoặc truyền cả đường dẫn cần dùng trong property file hay bằng `-D`.

## 5. Phân biệt -D của Ant với -D của JVM

Cùng ký hiệu `-Dname=value` có thể xuất hiện ở hai vị trí khác nhau, nhưng đối tượng nhận không giống nhau.

| Cách truyền | Ví dụ | Đối tượng nhận trực tiếp |
|---|---|---|
| Tùy chọn dòng lệnh Ant | `ant -Denv=ci package` | Ant user property |
| Tùy chọn JVM qua ANT_OPTS | `ANT_OPTS="-Denv=ci" ant package` | Java system property của JVM chạy Ant |

Khi dùng `ant -Denv=ci`, Ant nhận property trực tiếp từ command line. Đây là cách rõ ràng để cung cấp cấu hình cho build.

Khi dùng `-Denv=ci` trong `ANT_OPTS`, launcher đưa tham số đó vào lệnh khởi động JVM. JVM tạo system property, và Ant thường đưa system properties vào tập property của project. Cách này phù hợp khi mục đích là cấu hình JVM hoặc một thư viện Java trong tiến trình Ant.

Đối với yêu cầu truyền property cho build, nên ưu tiên tùy chọn dòng lệnh Ant `-Dname=value` hoặc `-propertyfile`. Đối với heap, garbage collector hay các tùy chọn khởi động JVM, dùng biến `ANT_OPTS`.

## 6. Truyền giá trị có khoảng trắng hoặc ký tự đặc biệt

Shell phân tích dòng lệnh trước khi Ant nhận tham số. Nếu giá trị có khoảng trắng, hãy đặt toàn bộ tham số thành một đối số bằng cách dùng dấu nháy phù hợp với shell.

Linux hoặc macOS:

```bash
ant '-Dapp.name=Order Management Service' package
```

Windows PowerShell:

```powershell
ant '-Dapp.name=Order Management Service' package
```

Windows Command Prompt:

```bat
ant "-Dapp.name=Order Management Service" package
```

Không đặt dấu cách quanh dấu bằng. Nếu giá trị chứa ký tự đặc biệt như `$`, `&` hoặc dấu nháy, cách escape phụ thuộc shell đang dùng. Hãy kiểm tra cách shell truyền đối số trước khi tìm lỗi trong build file.

Với property file, giá trị có khoảng trắng có thể viết trực tiếp:

```properties
app.name=Order Management Service
```

Định dạng Java Properties có quy tắc escape riêng cho dấu gạch chéo ngược, dấu phân cách và ký tự đặc biệt. Nếu cần lưu ký tự ngoài ASCII, hãy chú ý encoding mà cách nạp property file đang sử dụng; cách đọc kiểu Java Properties truyền thống có thể yêu cầu Unicode escape. Giữ file cấu hình theo một quy ước encoding thống nhất để tránh lỗi dấu tiếng Việt.

## 7. Dùng property trong build file

Sau khi nhận property, build file có thể sử dụng chúng trong thuộc tính của task, đường dẫn hoặc điều kiện.

Ví dụ:

```xml
<project name="sample" default="package">
    <property name="build.profile" value="local"/>
    <property name="output.dir" location="build/${build.profile}"/>

    <target name="prepare">
        <mkdir dir="${output.dir}"/>
        <echo message="Preparing ${build.profile} build"/>
    </target>

    <target name="package" depends="prepare">
        <jar destfile="${output.dir}/sample.jar"
             basedir="build/classes"/>
    </target>
</project>
```

Có thể truyền profile khác nhau mà không phải sửa build file:

```bash
ant -Dbuild.profile=ci package
ant -Dbuild.profile=release package
```

Trong ví dụ này, `output.dir` được tạo từ profile nếu chưa được định nghĩa trước. Nếu property file đã cung cấp `output.dir`, giá trị đó được giữ nguyên. Điều này cho phép build file cung cấp mặc định trong khi người chạy build có thể truyền giá trị cụ thể.

Nếu một property bắt buộc phải có, không nên âm thầm dùng giá trị mặc định giả. Có thể kiểm tra giá trị trước khi chạy các target chính, rồi báo lỗi dễ hiểu khi thiếu cấu hình. Ví dụ:

```xml
<target name="check-config">
    <fail unless="release.version"
          message="Missing required property: release.version"/>
</target>
```

Sau đó đặt target kiểm tra làm dependency của target phát hành:

```xml
<target name="release" depends="check-config">
    <echo message="Releasing version ${release.version}"/>
</target>
```

Giá trị bắt buộc có thể được cung cấp bằng `-Drelease.version=...` hoặc trong file property được nạp khi gọi Ant.

## 8. Lỗi thường gặp

### Property trong build file không đổi dù đã truyền -D

Kiểm tra tên property có khớp chính xác không, có viết đúng dạng `-Dname=value` không và tham số có nằm trước tên target không. Tên property phân biệt theo chuỗi ký tự; `build.profile` và `build_profile` là hai tên khác nhau.

Nếu property được truyền đúng bằng tùy chọn Ant, giá trị từ command line sẽ được ưu tiên hơn giá trị mặc định khai báo bằng `<property>`.

### Property trong file không được nạp

Kiểm tra đường dẫn file, thư mục làm việc hiện tại và quyền đọc. Đảm bảo đã dùng `-propertyfile` thay vì đặt đường dẫn file như một đối số target. Có thể thử dùng đường dẫn tuyệt đối để phân biệt lỗi đường dẫn với lỗi nội dung.

### Giá trị có khoảng trắng bị tách thành nhiều tham số

Đặt toàn bộ đối số `-Dname=value` trong dấu nháy phù hợp với shell. Với property file, viết giá trị trên một dòng theo định dạng Java Properties và không thêm dấu nháy bao quanh nếu không muốn dấu nháy trở thành nội dung.

### Property dẫn xuất không tự cập nhật

Ant property không tự tính lại khi property đầu vào thay đổi. Nếu `output.dir` đã được đặt, việc thay `build.profile` sau đó không tự làm `output.dir` thay đổi. Hãy thiết kế property phụ thuộc theo thứ tự hợp lý hoặc truyền trực tiếp giá trị cuối cùng.

### Nội dung tiếng Việt bị sai ký tự

Kiểm tra encoding của file và cách Ant/JDK đọc property file. Với định dạng Java Properties truyền thống dùng luồng byte, các ký tự ngoài ISO-8859-1 cần được biểu diễn bằng Unicode escape. Nếu build hỗ trợ cấu hình encoding cụ thể cho cách nạp file, hãy khai báo tường minh và dùng cùng quy ước khi tạo file.

## 9. Nguyên tắc tổ chức cấu hình

- Dùng `-D` cho một vài giá trị cần thay đổi theo lần chạy.
- Dùng `-propertyfile` khi có một nhóm cấu hình cần lưu, xem lại và tái sử dụng.
- Để build file khai báo giá trị mặc định bằng `<property>`, còn môi trường chạy cung cấp các giá trị cần ghi đè.
- Chỉ truyền các property thực sự cần thiết; tránh để nhiều nguồn cấu hình cùng đặt một tên nếu không có quy tắc ưu tiên rõ ràng.
- Đặt tên property nhất quán, có tiền tố theo phạm vi như `build.`, `app.` hoặc `release.`.
- Không lưu mật khẩu, token hoặc khóa riêng trong file property được commit vào repository hay truyền trực tiếp trên command line. Dòng lệnh có thể xuất hiện trong log và thông tin tiến trình; hãy dùng cơ chế secret của CI hoặc môi trường chạy phù hợp.
- Giữ cấu hình phát hành có thể truy vết: ghi lại tên profile và phiên bản đã dùng để tạo artifact.

`-D` và `-propertyfile` giúp cùng một build file chạy với nhiều bộ cấu hình mà không phải chỉnh sửa mã build cho từng lần chạy. `-D` tiện cho giá trị đơn lẻ cần ghi đè; `-propertyfile` phù hợp với tập cấu hình có thể lưu và tái sử dụng. Hiểu quy tắc ưu tiên và tính bất biến của property giúp tránh trường hợp một giá trị đã được nạp nhưng không thay đổi như mong đợi.


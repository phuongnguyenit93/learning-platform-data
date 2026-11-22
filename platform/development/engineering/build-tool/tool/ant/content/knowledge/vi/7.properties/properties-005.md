# Nạp biến môi trường bằng `property environment`

Trong Apache Ant, task `<property>` có thể đọc các biến môi trường của tiến trình đang chạy Ant và đưa chúng vào hệ thống property của build. Cách này cho phép `build.xml` sử dụng những thông tin đã được cấu hình bên ngoài, chẳng hạn `JAVA_HOME`, `APP_HOME`, `CI` hoặc đường dẫn đến công cụ cần thiết.

Để nạp biến môi trường, dùng thuộc tính `environment` của task `<property>` và chỉ định một prefix. Ví dụ, `<property environment="env"/>` làm cho biến môi trường `JAVA_HOME` có thể được tham chiếu trong build file bằng `${env.JAVA_HOME}`. Prefix giúp phân biệt property được nhập từ môi trường với property do build file tự khai báo.

## 1. Biến môi trường và Ant property

Biến môi trường là cặp tên và giá trị được hệ điều hành cung cấp cho một tiến trình khi tiến trình đó được khởi chạy. Ví dụ, terminal có thể cung cấp `JAVA_HOME` để các công cụ Java biết vị trí JDK.

Ant có hệ thống property riêng để lưu các giá trị được dùng trong build file. Một property có thể được khai báo bằng task `<property>`, được nhập từ tệp properties, được truyền qua dòng lệnh hoặc được nạp từ môi trường.

Hai khái niệm này có liên quan nhưng không giống nhau:

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Biến môi trường | Được hệ điều hành truyền cho tiến trình | `JAVA_HOME=C:\Java\jdk-21` |
| Ant property | Giá trị được Ant dùng khi xử lý build file | `env.JAVA_HOME` |
| Prefix | Tiền tố Ant thêm vào tên biến môi trường khi nhập | `env` trong `env.JAVA_HOME` |

Khi chạy Ant từ một terminal, tiến trình Ant kế thừa môi trường của terminal đó. Nếu `JAVA_HOME` đã được cấu hình trong môi trường mà terminal nhìn thấy, Ant có thể đọc giá trị này bằng `property environment`.

## 2. Cú pháp `property environment`

Cú pháp cơ bản:

```xml
<property environment="env"/>
```

`environment` nhận một chuỗi prefix. Ant nhập các biến môi trường mà tiến trình hiện tại nhìn thấy thành các property có dạng:

```text
<prefix>.<TEN_BIEN_MOI_TRUONG>
```

Với prefix `env`, một số ví dụ tham chiếu là:

| Biến môi trường | Ant property |
|---|---|
| `JAVA_HOME` | `${env.JAVA_HOME}` |
| `PATH` | `${env.PATH}` |
| `HOME` | `${env.HOME}` |
| `APP_HOME` | `${env.APP_HOME}` |

Tên property được tạo bằng cách nối prefix, dấu chấm và tên biến môi trường. Hãy tham chiếu đúng tên biến được cung cấp trong môi trường của hệ điều hành.

### 2.1. Đặt task nạp môi trường ở cấp project

Thông thường, đặt `<property environment="env"/>` trực tiếp bên trong `<project>` và bên ngoài các target:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="environment-demo" default="show-env" basedir=".">

    <property environment="env"/>

    <target name="show-env">
        <echo message="JAVA_HOME = ${env.JAVA_HOME}"/>
        <echo message="APP_HOME = ${env.APP_HOME}"/>
    </target>

</project>
```

Task `<property>` ở cấp project được xử lý khi Ant đọc build file. Vì vậy các target có thể sử dụng những property đã được nhập mà không cần nạp lại ở từng target.

Nếu chỉ nạp trong một target, các target khác không thể dựa vào property đó trước khi target nạp môi trường được thực thi. Đặt task ở cấp project thường làm ý định cấu hình rõ ràng hơn và giúp các target dùng chung một nguồn giá trị.

### 2.2. Chọn prefix khác

Prefix không bắt buộc phải là `env`. Bạn có thể chọn tên khác để phù hợp với cách tổ chức build file:

```xml
<property environment="system"/>

<target name="show-java-home">
    <echo message="JAVA_HOME = ${system.JAVA_HOME}"/>
</target>
```

Trong ví dụ này, Ant tạo property `system.JAVA_HOME`. Nếu chọn prefix `machine`, property tương ứng sẽ là `machine.JAVA_HOME`.

Nên chọn một prefix ngắn, dễ nhận biết và dùng thống nhất trong build file. Tránh thay đổi prefix giữa nhiều target vì người đọc sẽ khó xác định property nào đến từ môi trường.

## 3. Nạp và sử dụng biến môi trường trong build file

Ví dụ sau nạp môi trường rồi dùng `JAVA_HOME` để kiểm tra cấu hình Java:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="java-environment-check" default="check-java" basedir=".">

    <property environment="env"/>

    <target name="check-java">
        <fail unless="env.JAVA_HOME"
              message="JAVA_HOME is not set in the environment."/>

        <echo message="JAVA_HOME = ${env.JAVA_HOME}"/>
        <echo message="Java environment is available."/>
    </target>

</project>
```

Task `<fail>` dừng build nếu property `env.JAVA_HOME` chưa được thiết lập. Nếu property tồn tại, Ant tiếp tục và in đường dẫn. Cách kiểm tra này giúp thông báo lỗi gần với nơi cấu hình được sử dụng, thay vì để một task phía sau thất bại với thông báo khó hiểu.

Chạy target:

```bash
ant check-java
```

Nếu `JAVA_HOME` có trong môi trường của tiến trình Ant, build tiếp tục. Nếu không có, Ant dừng tại task `<fail>` và hiển thị thông báo đã khai báo.

### 3.1. Sử dụng biến trong đường dẫn

Property nhập từ môi trường có thể được kết hợp với các chuỗi khác để tạo đường dẫn hoặc cấu hình task:

```xml
<project name="external-tool-demo" default="show-tool" basedir=".">
    <property environment="env"/>

    <target name="show-tool">
        <fail unless="env.TOOL_HOME"
              message="Please define TOOL_HOME before running this build."/>

        <echo message="External tool directory: ${env.TOOL_HOME}"/>
        <echo message="Configuration file: ${env.TOOL_HOME}/conf/tool.properties"/>
    </target>
</project>
```

Nếu `TOOL_HOME` có giá trị `/opt/example-tool`, Ant thay `${env.TOOL_HOME}` bằng chuỗi đó trong các thuộc tính của task. Nếu đường dẫn chứa dấu cách, hãy giữ giá trị trong dấu nháy XML như ví dụ trên; không tự ghép thêm dấu nháy vào giá trị property trừ khi task cụ thể yêu cầu.

Đối với đường dẫn thực tế, nên dùng các thuộc tính như `location` hoặc `file` của task Ant tương ứng khi chúng được hỗ trợ. Ant có thể xử lý đường dẫn theo hệ điều hành, nhưng không nên giả định mọi task đều phân tích chuỗi đường dẫn theo cùng một cách.

### 3.2. Dùng biến môi trường để chọn chế độ build

Một biến môi trường có thể được dùng để nhận biết build đang chạy trong CI hoặc trong máy phát triển:

```xml
<project name="build-mode-demo" default="show-mode">
    <property environment="env"/>

    <target name="show-mode">
        <echo message="CI environment = ${env.CI}"/>
    </target>
</project>
```

Một số hệ thống CI đặt biến `CI` để nhận diện tiến trình build tự động. Tuy nhiên, không phải mọi hệ thống hoặc máy cá nhân đều có biến này. Hãy kiểm tra property trước khi dùng nó để điều khiển nhánh build.

Ví dụ dùng điều kiện của Ant để chạy hai target theo sự tồn tại của property:

```xml
<project name="ci-demo" default="build">
    <property environment="env"/>

    <target name="build" depends="ci-info,local-info"/>

    <target name="ci-info" if="env.CI">
        <echo message="Running in a CI environment"/>
    </target>

    <target name="local-info" unless="env.CI">
        <echo message="Running without the CI environment property"/>
    </target>
</project>
```

Trong Ant, thuộc tính `if` và `unless` trên target kiểm tra việc property có được thiết lập hay không. Chúng không tự đánh giá nội dung của property như một biểu thức boolean tổng quát. Ví dụ này phù hợp khi sự hiện diện của `env.CI` là quy ước mà môi trường CI của bạn sử dụng. Nếu cần kiểm tra một giá trị cụ thể như `CI=true`, hãy dùng điều kiện so sánh rõ ràng bằng các task điều kiện hoặc cấu trúc điều khiển phù hợp với phiên bản Ant đang dùng.

## 4. Cấu hình biến môi trường trước khi chạy Ant

`property environment` chỉ đọc môi trường mà tiến trình Ant nhận được lúc khởi chạy. Vì vậy, nếu biến chưa được thiết lập trong terminal, build file không thể tự suy ra giá trị cần thiết.

### 4.1. Windows PowerShell

Kiểm tra biến hiện có:

```powershell
$env:JAVA_HOME
```

Đặt biến tạm thời cho cửa sổ PowerShell hiện tại:

```powershell
$env:APP_HOME = "C:\tools\sample-app"
ant show-env
```

Lệnh `ant` được chạy từ cùng cửa sổ nên tiến trình Ant nhận giá trị `APP_HOME`. Khi đóng cửa sổ PowerShell, biến được đặt theo cách này không còn trong phiên mới.

### 4.2. Windows Command Prompt

Kiểm tra biến:

```bat
echo %JAVA_HOME%
```

Đặt biến trong cửa sổ Command Prompt hiện tại và chạy Ant:

```bat
set APP_HOME=C:\tools\sample-app
ant show-env
```

Lệnh `set` áp dụng cho cửa sổ hiện tại và các tiến trình con được khởi chạy từ đó. Nó không tự ghi cấu hình lâu dài vào hệ điều hành.

### 4.3. Linux và macOS

Kiểm tra biến:

```bash
printenv JAVA_HOME
```

Đặt biến và chạy Ant trong cùng terminal:

```bash
export APP_HOME="$HOME/tools/sample-app"
ant show-env
```

`export` đánh dấu biến để các tiến trình con, bao gồm Ant, nhận được biến đó. Nếu chỉ gán biến shell mà không export, chương trình được khởi chạy có thể không nhìn thấy biến.

### 4.4. Thay đổi cấu hình lâu dài

Nếu muốn biến môi trường có sẵn trong các terminal mới, hãy cấu hình nó ở phần quản lý Environment Variables của hệ điều hành hoặc trong tệp khởi tạo shell thích hợp. Sau khi thay đổi, mở terminal mới rồi kiểm tra lại giá trị trước khi chạy Ant.

Trên Windows, một tiến trình đã mở không tự nhận các thay đổi môi trường vừa lưu ở cấp người dùng hoặc hệ thống. Trên Linux/macOS, một terminal đã chạy cũng không tự đọc lại tệp cấu hình shell sau khi bạn chỉnh sửa; cần mở terminal mới hoặc nạp lại tệp cấu hình tương ứng.

## 5. Phạm vi và thời điểm nạp môi trường

Khi Ant khởi động, hệ điều hành cung cấp một snapshot môi trường cho tiến trình Ant. Task `<property environment="env"/>` đọc các biến từ môi trường đó và đưa vào property của build.

Điều này có ba hệ quả quan trọng:

1. Ant chỉ nhìn thấy những biến đã được truyền cho tiến trình Ant. Biến đặt trong một terminal khác không tự xuất hiện.
2. Thay đổi biến trong terminal sau khi Ant đã chạy không cập nhật property đã nạp trong build đang thực thi.
3. Property nhập từ môi trường tuân theo quy tắc property của Ant: một property đã được thiết lập thì không bị ghi đè bằng một lần khai báo `<property>` sau đó.

Nếu cần thay đổi giá trị, hãy thiết lập môi trường trước khi chạy Ant hoặc truyền giá trị điều khiển bằng cơ chế cấu hình thích hợp. Không nên kỳ vọng gọi `<property environment="env"/>` nhiều lần sẽ làm mới và ghi đè các property đã được thiết lập.

### 5.1. Property của Ant là immutable

Ant property có tính bất biến theo quy tắc first definition wins: khi một property đã được thiết lập, các lần thiết lập sau không thay đổi giá trị đó.

Ví dụ:

```xml
<project name="property-precedence" default="show">
    <property environment="env"/>

    <property name="app.home" value="${env.APP_HOME}"/>
    <property name="app.home" value="/opt/default-app"/>

    <target name="show">
        <echo message="Application home = ${app.home}"/>
    </target>
</project>
```

Nếu `env.APP_HOME` đã tồn tại khi Ant nạp môi trường, property `app.home` được thiết lập từ giá trị đó. Lần khai báo thứ hai không thay thế nó. Nếu biến môi trường không tồn tại, biểu thức tham chiếu có thể vẫn chưa được phân giải; không nên dùng cách viết trên như một cơ chế fallback tự động.

Để đặt một giá trị mặc định có thể được thay bằng dòng lệnh, hãy khai báo một property riêng với giá trị mặc định:

```xml
<project name="property-override" default="show">
    <property name="app.home" value="build/app"/>

    <target name="show">
        <echo message="Application home = ${app.home}"/>
    </target>
</project>
```

Người chạy có thể truyền giá trị khác bằng user property:

```bash
ant -Dapp.home=/opt/sample-app show
```

Giá trị truyền bằng `-D` được Ant tiếp nhận như user property và có ưu tiên cao hơn khai báo `<property>` trong build file. Nếu muốn dùng biến môi trường làm giá trị mặc định nhưng vẫn cho phép ghi đè bằng `-Dapp.home=...`, có thể dùng một điều kiện kiểm tra rõ ràng hoặc chuẩn bị biến trung gian phù hợp; cần xử lý trường hợp biến môi trường không tồn tại trước khi gán property.

### 5.2. Thứ tự khai báo

Đặt task nạp môi trường trước các cấu hình cần sử dụng giá trị được nhập:

```xml
<project name="order-demo" default="show">
    <property environment="env"/>
    <property name="app.root" value="${env.APP_HOME}"/>

    <target name="show">
        <echo message="${app.root}"/>
    </target>
</project>
```

Nếu một property khác cần tham chiếu `env.APP_HOME`, hãy bảo đảm property môi trường được nạp trước khi khai báo property đó. Cách sắp xếp này giúp người đọc hiểu nguồn dữ liệu và tránh phụ thuộc vào một giá trị chưa được nhập.

## 6. Phân biệt nạp biến môi trường với đặt biến môi trường

`<property environment="env"/>` là thao tác **đọc** môi trường vào Ant. Nó không tạo hoặc sửa biến môi trường của hệ điều hành.

Ví dụ:

```xml
<property environment="env"/>
<echo message="Current PATH = ${env.PATH}"/>
```

Đoạn build file trên chỉ đọc và in `PATH` mà tiến trình Ant nhận được. Nó không thể thêm thư mục vào `PATH` của Windows, Linux hoặc macOS.

Nếu một task cần truyền biến môi trường riêng cho tiến trình con, đó là một cấu hình khác. Chẳng hạn task `<exec>` có thể nhận phần tử lồng `<env>` để thiết lập môi trường của lệnh con:

```xml
<target name="run-tool">
    <exec executable="my-tool" failonerror="true">
        <env key="APP_MODE" value="production"/>
    </exec>
</target>
```

Ở đây `<env>` thuộc cấu hình của task `<exec>`, dùng để cung cấp biến cho tiến trình con. Nó không phải cách thay đổi môi trường của tiến trình Ant hiện tại. Đường dẫn `my-tool` cũng phải được hệ điều hành phân giải được hoặc được chỉ định bằng đường dẫn phù hợp.

## 7. Không làm lộ thông tin nhạy cảm

Môi trường của một tiến trình có thể chứa token, mật khẩu, khóa truy cập hoặc thông tin kết nối do CI/CD cung cấp. Task `<property environment="env"/>` nhập các biến môi trường vào property của Ant; bản thân thao tác này không có nghĩa tất cả giá trị sẽ được in ra log.

Chỉ tham chiếu những biến thật sự cần cho build. Tránh in toàn bộ property hoặc toàn bộ môi trường bằng các lệnh liệt kê khi log có thể được chia sẻ, lưu lâu dài hoặc hiển thị cho người không được phép xem. Không đưa giá trị bí mật vào source code, commit build file hoặc thông báo lỗi.

Ví dụ nên in trạng thái có/không thay vì in token:

```xml
<project name="secret-check" default="check">
    <property environment="env"/>

    <target name="check">
        <fail unless="env.DEPLOY_TOKEN"
              message="DEPLOY_TOKEN must be provided by the environment."/>
        <echo message="Deployment credential is configured."/>
    </target>
</project>
```

Ví dụ chỉ kiểm tra property tồn tại, không đưa giá trị token vào đầu ra. Quyền truy cập và cách cấp secret vẫn cần được quản lý bởi hệ điều hành hoặc nền tảng CI/CD.

## 8. Lỗi thường gặp khi dùng `property environment`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `${env.JAVA_HOME}` không có giá trị mong đợi | `JAVA_HOME` chưa được đặt trong môi trường của terminal chạy Ant | Kiểm tra biến trong đúng terminal, đặt biến rồi khởi chạy lại Ant |
| Property vẫn là chuỗi `${env.APP_HOME}` | Biến môi trường không tồn tại hoặc tên được tham chiếu không khớp | Kiểm tra tên biến, prefix và môi trường mà tiến trình Ant nhận được; kiểm tra tồn tại trước khi sử dụng |
| Thay đổi biến nhưng Ant vẫn dùng giá trị cũ | Ant đang chạy trong tiến trình được khởi tạo trước khi môi trường thay đổi, hoặc property đã được thiết lập trước đó | Mở tiến trình Ant mới và kiểm tra thứ tự khai báo property |
| `${JAVA_HOME}` không được thay thế | Bạn đã nhập biến với prefix `env` nhưng tham chiếu thiếu prefix | Dùng `${env.JAVA_HOME}` hoặc đổi prefix trong task nạp môi trường cho nhất quán |
| Dùng nhầm `environment` như thuộc tính của target | Đặt task hoặc thuộc tính sai phần tử | Dùng `<property environment="env"/>` như một task property ở cấp project hoặc trong target phù hợp |
| Muốn Ant thay đổi `PATH` của máy nhưng không có tác dụng | `property environment` chỉ đọc môi trường vào property | Cấu hình môi trường bên ngoài Ant; nếu chỉ cần môi trường cho tiến trình con, dùng cấu hình `env` của task thực thi tương ứng |
| Build log chứa thông tin bí mật | In toàn bộ property hoặc giá trị biến nhạy cảm | Chỉ in tên hoặc trạng thái cấu hình cần thiết; không ghi token và mật khẩu vào log |

Khi debug, có thể tạo một target chỉ in một vài biến không nhạy cảm đã biết:

```xml
<property environment="env"/>

<target name="show-environment">
    <echo message="JAVA_HOME = ${env.JAVA_HOME}"/>
    <echo message="APP_HOME = ${env.APP_HOME}"/>
</target>
```

Không nên dùng target này để in các biến có thể chứa thông tin xác thực. Nếu một property chưa có, hãy kiểm tra biến tương ứng ở terminal trước rồi mới kết luận lỗi nằm ở Ant.

## 9. Ví dụ hoàn chỉnh

Ví dụ sau dùng biến môi trường `APP_HOME` để xác định thư mục ứng dụng và kiểm tra thư mục cấu hình trước khi tiếp tục:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="environment-property-demo" default="inspect-app" basedir=".">

    <!-- Import environment variables with the env prefix. -->
    <property environment="env"/>

    <target name="inspect-app" description="Inspect the configured application home">
        <fail unless="env.APP_HOME"
              message="Please set APP_HOME before running this build."/>

        <available file="${env.APP_HOME}" type="dir"
                   property="app.home.exists"/>
        <fail unless="app.home.exists"
              message="APP_HOME does not point to an existing directory."/>

        <echo message="Application directory is configured."/>
        <echo message="Configuration path: ${env.APP_HOME}/conf"/>
    </target>

</project>
```

Thiết lập biến trong terminal trước khi chạy:

PowerShell:

```powershell
$env:APP_HOME = "C:\apps\sample"
ant inspect-app
```

Linux hoặc macOS:

```bash
export APP_HOME="$HOME/apps/sample"
ant inspect-app
```

Nếu `APP_HOME` chưa được thiết lập, task `<fail>` đầu tiên dừng build. Nếu biến tồn tại nhưng không trỏ đến thư mục hiện có, task `<available>` không đặt property `app.home.exists`, và task `<fail>` thứ hai dừng build. Khi thư mục tồn tại, target in thông báo và đường dẫn cấu hình.

Task `<available>` ở ví dụ này kiểm tra sự tồn tại của một thư mục trên máy; nó không kiểm tra nội dung bên trong thư mục `conf` và cũng không xác nhận ứng dụng đã được cài đặt hoàn chỉnh.

## 10. Checklist sử dụng property environment

- [ ] Đã xác định biến môi trường mà build thực sự cần.
- [ ] Đã cấu hình biến trong môi trường của terminal hoặc tiến trình sẽ chạy Ant.
- [ ] Đã khai báo `<property environment="env"/>` trước khi tham chiếu các biến.
- [ ] Đã dùng đúng prefix, ví dụ `${env.JAVA_HOME}`.
- [ ] Đã kiểm tra property bắt buộc tồn tại trước khi dùng nó.
- [ ] Đã hiểu property của Ant theo quy tắc first definition wins.
- [ ] Đã mở tiến trình Ant mới sau khi thay đổi môi trường bên ngoài.
- [ ] Không nhầm thao tác đọc môi trường với thao tác sửa môi trường hệ điều hành.
- [ ] Không in token, mật khẩu hoặc toàn bộ môi trường vào log build.

`property environment` là cầu nối đơn giản giữa cấu hình của hệ điều hành và build file Ant. Khi nạp biến với một prefix rõ ràng, kiểm tra các giá trị bắt buộc và hiểu quy tắc bất biến của Ant property, bạn có thể tái sử dụng cùng một build file trên nhiều máy hoặc môi trường CI/CD mà không phải ghi cứng các đường dẫn phụ thuộc vào từng máy.

# User property và độ ưu tiên của giá trị truyền từ dòng lệnh

Trong Apache Ant, **property** là một giá trị có tên được dùng để cấu hình build file, chẳng hạn thư mục mã nguồn, phiên bản Java, tên môi trường hoặc đường dẫn đến thư mục đóng gói. Bạn có thể khai báo property ngay trong build file, đọc từ tệp cấu hình hoặc truyền giá trị từ dòng lệnh.

Một loại property đặc biệt là **user property**. Đây là giá trị được người gọi build cung cấp từ bên ngoài, thường thông qua tùy chọn dòng lệnh `-Dname=value` hoặc tệp property được nạp khi khởi chạy Ant. User property có độ ưu tiên cao hơn các property thông thường trong build file. Nhờ đó, người dùng có thể thay đổi cấu hình cho một lần chạy mà không phải sửa mã build.

Bài học này giải thích cách Ant xử lý property, vì sao giá trị truyền từ dòng lệnh được ưu tiên, cách kết hợp giá trị mặc định với cấu hình môi trường và cách kiểm tra khi một property không nhận giá trị như mong đợi.

## 1. Property trong Ant là gì?

Property là một cặp tên và giá trị. Ví dụ:

```xml
<project name="sample" default="show">

    <property name="app.name" value="customer-service"/>
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo message="Application: ${app.name}"/>
        <echo message="Build directory: ${build.dir}"/>
    </target>

</project>
```

Khi chạy:

```bash
ant show
```

Ant thay các biểu thức `${app.name}` và `${build.dir}` bằng giá trị tương ứng. Kết quả:

```text
Application: customer-service
Build directory: build
```

Property thường được dùng cho:

- Tên ứng dụng và phiên bản.
- Thư mục chứa mã nguồn, bytecode, test report và JAR.
- Mức Java mục tiêu.
- Địa chỉ máy chủ hoặc tên môi trường triển khai.
- Cờ bật/tắt một phần công việc trong build.
- Đường dẫn đến công cụ và thư viện bên ngoài.

Property của Ant chủ yếu là chuỗi. Giá trị như `true`, `false`, `17` hoặc `production` vẫn được lưu dưới dạng văn bản; task hoặc điều kiện sử dụng chúng sẽ diễn giải theo quy tắc riêng.

## 2. Quy tắc quan trọng: property thông thường không thể bị ghi đè

Ant thiết kế property theo hướng **immutable** (không thay đổi sau khi đã được thiết lập). Khi một property đã có giá trị, một lần khai báo thông thường tiếp theo với cùng tên sẽ không thay thế giá trị cũ.

Ví dụ:

```xml
<project name="property-demo" default="show">

    <property name="env" value="dev"/>
    <property name="env" value="test"/>

    <target name="show">
        <echo message="Environment: ${env}"/>
    </target>

</project>
```

Chạy:

```bash
ant show
```

Kết quả vẫn là:

```text
Environment: dev
```

Lệnh khai báo thứ hai không đổi `env` thành `test` vì property đã được đặt trước đó.

Quy tắc này cũng áp dụng khi giá trị đến từ nhiều nguồn. Ví dụ, nếu build file đã nạp `env` từ tệp cấu hình, một lần `<property name="env" value="..."/>` sau đó không tự động thay thế nó.

Tính bất biến giúp build có hành vi dự đoán được: một giá trị cấu hình không bị thay đổi âm thầm ở một target khác. Khi cần chọn cấu hình khác, hãy cung cấp giá trị trước khi build bắt đầu hoặc dùng một tên property khác cho giá trị cần tính toán.

## 3. User property là gì?

User property là property do người gọi Ant cung cấp như một phần cấu hình của lần chạy. Cách thường dùng nhất là tùy chọn `-D` trên dòng lệnh:

```bash
ant -Denv=prod package
```

Trong đó:

- `-D` cho biết một property được truyền từ dòng lệnh.
- `env` là tên property.
- `prod` là giá trị của property.
- `package` là target cần chạy.

Giả sử build file có giá trị mặc định:

```xml
<project name="property-demo" default="show">

    <property name="env" value="dev"/>

    <target name="show">
        <echo message="Environment: ${env}"/>
    </target>

</project>
```

Chạy không truyền property:

```bash
ant show
```

Kết quả:

```text
Environment: dev
```

Chạy với user property:

```bash
ant -Denv=prod show
```

Kết quả:

```text
Environment: prod
```

Mặc dù build file khai báo `env=dev`, giá trị `prod` được truyền từ dòng lệnh đã có sẵn trước khi Ant xử lý build file. Lệnh `<property>` trong build file không thể thay thế user property đó.

Đây là cách phổ biến để giữ cấu hình mặc định trong build file nhưng vẫn cho phép người gọi chọn môi trường cho từng lần chạy.

## 4. Độ ưu tiên giữa user property và property trong build file

Khi cùng một tên property được cung cấp từ nhiều nơi, cần phân biệt hai tình huống:

1. **User property** được truyền từ bên ngoài, chẳng hạn bằng `-D`.
2. **Property thông thường** được khai báo trong build file hoặc được nạp bằng task `<property>`.

User property có ưu tiên cao hơn property thông thường. Quy tắc này không phụ thuộc vào việc lệnh `<property>` xuất hiện trước hay sau trong build file.

Ví dụ:

```xml
<project name="priority-demo" default="show">

    <property name="env" value="dev"/>

    <target name="show">
        <property name="env" value="test"/>
        <echo message="Environment: ${env}"/>
    </target>

</project>
```

Không truyền user property:

```bash
ant show
```

Giá trị đầu tiên được thiết lập là `dev`. Lệnh `<property>` bên trong target không thể thay thế nó, nên kết quả là:

```text
Environment: dev
```

Truyền từ dòng lệnh:

```bash
ant -Denv=prod show
```

Kết quả:

```text
Environment: prod
```

Có thể hình dung thứ tự ưu tiên trong tình huống thông dụng như sau:

```text
User property từ dòng lệnh (-D)
            |
            v
Giá trị env đã được người gọi cung cấp
            |
            v
Property thông thường trong build file
            |
            v
Giá trị mặc định do build file thiết lập
```

Sơ đồ nhấn mạnh rằng user property được bảo vệ khỏi các lần khai báo property thông thường. Còn giữa các property thông thường, quy tắc “giá trị đầu tiên thắng” vẫn áp dụng.

### Bảng so sánh

| Nguồn giá trị | Ví dụ | Hành vi |
|---|---|---|
| Dòng lệnh | `ant -Denv=prod package` | User property; ưu tiên hơn property thông thường |
| Property file nạp bằng tùy chọn dòng lệnh | `ant -propertyfile release.properties package` | Cung cấp cấu hình cho lần chạy; giá trị `-D` tường minh có thể ghi đè giá trị từ file |
| Build file | `<property name="env" value="dev"/>` | Chỉ thiết lập nếu property chưa có giá trị |
| Property file nạp bằng task `<property file="..."/>` | `<property file="build.properties"/>` | Property thông thường; chỉ thiết lập tên chưa có giá trị |
| Environment property được nạp bằng task | `<property environment="env"/>` | Tạo các property như `env.PATH`; tuân theo quy tắc property thông thường |

Khi cần bảo đảm một giá trị có thể được người gọi ghi đè, hãy để nó là user property hoặc khai báo mặc định trong build file. Không nên đặt một giá trị cố định ở nhiều vị trí rồi kỳ vọng lần khai báo sau sẽ thay thế lần trước.

## 5. Dùng property file từ dòng lệnh

Khi có nhiều cấu hình cần truyền, viết từng tùy chọn `-D` có thể làm lệnh dài. Ant hỗ trợ tùy chọn `-propertyfile` để nạp một tệp thuộc tính khi khởi chạy.

Ví dụ tệp `config/release.properties`:

```properties
env=prod
app.name=customer-service
java.version=17
output.dir=dist
```

Chạy:

```bash
ant -propertyfile config/release.properties package
```

Ant nạp các giá trị trong tệp làm cấu hình cho lần chạy. Có thể kết hợp với `-D` để chỉ ghi đè một vài giá trị:

```bash
ant -propertyfile config/release.properties -Denv=staging package
```

Trong ví dụ này, `env` được truyền rõ ràng bằng `-D` nên có giá trị `staging`; các property khác tiếp tục lấy từ tệp cấu hình nếu build file không có user property hoặc giá trị có độ ưu tiên cao hơn.

Tùy chọn `-propertyfile` hữu ích khi nhóm muốn lưu một bộ cấu hình có thể tái sử dụng, còn `-D` phù hợp với các giá trị cần thay đổi riêng cho một lần chạy.

### Phân biệt -propertyfile với task <property file="..."/>

Hai cách này đều đọc nội dung dạng property file nhưng vai trò trong quá trình build khác nhau:

```bash
ant -propertyfile config/release.properties package
```

Đây là tùy chọn của Ant launcher. Các giá trị được nạp trước khi build file được xử lý và được cung cấp như cấu hình từ bên ngoài.

Trong khi đó:

```xml
<property file="config/release.properties"/>
```

là task trong build file. Nó được thực hiện khi Ant xử lý cấu hình build và thiết lập các property thông thường nếu tên đó chưa được đặt.

Do khác nhau về thời điểm và loại property, nếu cùng một tên xuất hiện ở cả hai nơi, user property từ tùy chọn dòng lệnh sẽ giữ quyền ưu tiên.

## 6. Kết hợp giá trị mặc định với cấu hình môi trường

Một build file tốt thường cung cấp giá trị mặc định để người mới có thể chạy mà không cần nhớ quá nhiều tham số. Người gọi vẫn có thể truyền user property để thay đổi giá trị khi cần.

Ví dụ:

```xml
<project name="service-build" default="show-config">

    <property name="env" value="dev"/>
    <property name="app.name" value="customer-service"/>
    <property name="output.dir" value="build"/>
    <property name="java.version" value="17"/>

    <target name="show-config">
        <echo message="Environment: ${env}"/>
        <echo message="Application: ${app.name}"/>
        <echo message="Output: ${output.dir}"/>
        <echo message="Java target: ${java.version}"/>
    </target>

</project>
```

Chạy mặc định:

```bash
ant show-config
```

Chạy với cấu hình phát hành:

```bash
ant -Denv=prod -Doutput.dir=dist show-config
```

Chỉ hai property được truyền thay đổi; các property còn lại giữ giá trị mặc định.

Đây là cách tổ chức cấu hình dễ bảo trì:

- Giá trị dùng chung và an toàn để mặc định có thể đặt trong build file.
- Giá trị theo môi trường có thể được cung cấp qua property file.
- Giá trị cần thay đổi nhanh cho một lần chạy có thể truyền bằng `-D`.
- Các giá trị bắt buộc nên được kiểm tra trước khi chạy target có sử dụng chúng.

### Kiểm tra property bắt buộc

Không phải property nào cũng nên có giá trị mặc định. Ví dụ, build triển khai có thể yêu cầu tên máy chủ hoặc thư mục artifact cụ thể. Có thể kiểm tra trước khi thực hiện:

```xml
<project name="deployment" default="deploy">

    <target name="validate-config">
        <fail
            unless="deploy.host"
            message="Cần truyền property deploy.host, ví dụ -Ddeploy.host=server.example"/>
    </target>

    <target name="deploy" depends="validate-config">
        <echo message="Deploying to ${deploy.host}"/>
    </target>

</project>
```

Nếu người gọi không truyền `deploy.host`, build dừng ở bước kiểm tra và hiển thị thông báo. Có thể chạy:

```bash
ant -Ddeploy.host=server.example deploy
```

Việc kiểm tra sớm giúp lỗi cấu hình xuất hiện trước khi build thực hiện các thao tác tốn thời gian hoặc có tác động đến môi trường triển khai.

## 7. Property và điều kiện

Ant thường dùng property để quyết định một target hoặc một thao tác có được thực hiện hay không. Ví dụ, có thể bật chế độ kiểm thử bổ sung bằng user property:

```xml
<project name="conditional-build" default="build">

    <target name="build">
        <echo message="Build ứng dụng"/>
    </target>

    <target name="integration-test" if="integration">
        <echo message="Chạy integration test"/>
    </target>

    <target name="verify" depends="build,integration-test">
        <echo message="Hoàn tất verify"/>
    </target>

</project>
```

Gọi:

```bash
ant verify
```

Target `integration-test` được bỏ qua nếu property `integration` không được thiết lập.

Khi gọi:

```bash
ant -Dintegration=true verify
```

property được truyền từ dòng lệnh, vì vậy target `integration-test` được thực hiện.

Lưu ý: thuộc tính `if` và `unless` trên target kiểm tra sự tồn tại của property theo quy tắc của Ant; không nên mặc định rằng chuỗi `false` đồng nghĩa với “không có property”. Nếu bạn truyền `-Dintegration=false`, property vẫn tồn tại và điều kiện `if="integration"` vẫn có thể được xem là thỏa mãn. Nếu cần kiểm tra giá trị boolean, hãy dùng task `<condition>` hoặc các điều kiện phù hợp thay vì chỉ dựa vào sự tồn tại.

Ví dụ tạo property chỉ khi cờ đầu vào có giá trị mong muốn:

```xml
<condition property="run.integration">
    <equals arg1="${integration}" arg2="true"/>
</condition>

<target name="integration-test" if="run.integration">
    <echo message="Chạy integration test"/>
</target>
```

Trong ví dụ, property `run.integration` chỉ được thiết lập khi giá trị `integration` bằng `true`. Vì property là bất biến, điều kiện nên được đánh giá sau khi đầu vào đã được cung cấp và trước khi target sử dụng kết quả.

## 8. Các tình huống dễ nhầm về độ ưu tiên

### Property trong target không ghi đè property đã có

Ví dụ:

```xml
<target name="prepare">
    <property name="output.dir" value="build"/>
</target>

<target name="package" depends="prepare">
    <property name="output.dir" value="dist"/>
    <echo message="Output: ${output.dir}"/>
</target>
```

Target `package` vẫn nhìn thấy giá trị `build`. Lệnh khai báo trong target `package` không thay thế giá trị đã được thiết lập ở `prepare`.

Nếu cần hai giá trị khác nhau, hãy dùng hai tên riêng:

```xml
<property name="classes.dir" value="build/classes"/>
<property name="archive.dir" value="dist"/>
```

### Giá trị mặc định không phải là giá trị ép buộc

Khai báo:

```xml
<property name="env" value="dev"/>
```

có nghĩa là “nếu chưa có `env`, dùng `dev`”. Nó không có nghĩa là “mọi lần build phải dùng `dev`”. Người gọi vẫn có thể truyền `-Denv=prod`.

### Property file trong build file và property file trên dòng lệnh khác nhau

```xml
<property file="config/dev.properties"/>
```

được thực hiện như một phần của build file. Nếu trước đó Ant đã nhận `env` qua `-Denv=prod`, giá trị `prod` được giữ nguyên.

Trong khi đó, `-propertyfile` là cách cung cấp property ngay từ lệnh khởi chạy Ant. Hãy chọn đúng cách theo ý định: cấu hình mặc định do build tự nạp hay cấu hình được người gọi cung cấp cho lần chạy.

### Property là chuỗi, không phải biến có thể gán lại

Không nên dùng cùng một property như biến thay đổi qua nhiều giai đoạn:

```xml
<property name="status" value="compile"/>
<!-- Một khai báo khác không thể đổi status thành package -->
```

Nếu cần biểu diễn trạng thái ở các giai đoạn khác nhau, dùng tên riêng như `compile.status` và `package.status`, hoặc thiết kế lại target để truyền thông tin qua cơ chế phù hợp.

## 9. Giá trị có dấu cách và cách truyền trên shell

Nếu giá trị property chứa dấu cách, hãy đặt toàn bộ cặp `name=value` trong dấu nháy để shell truyền thành một đối số:

```bash
ant "-Drelease.label=Customer Service RC 1" package
```

Trong PowerShell cũng có thể dùng dấu nháy kép:

```powershell
ant "-Drelease.label=Customer Service RC 1" package
```

Không đặt dấu nháy thành một phần của giá trị nếu không có chủ ý. Dấu nháy ở ví dụ chỉ giúp shell giữ toàn bộ biểu thức thành một đối số.

Với giá trị có ký tự đặc biệt như dấu bằng, dấu nháy hoặc ký tự mở rộng của shell, hãy xem quy tắc quoting của terminal đang sử dụng. Ant nhận chuỗi đối số sau khi shell đã xử lý; do đó, lỗi đôi khi nằm ở cách shell tách tham số chứ không phải ở task `<property>`.

## 10. Chẩn đoán khi property không nhận giá trị mong muốn

Khi một property có giá trị khác dự kiến, hãy kiểm tra theo thứ tự:

1. Xác nhận tên property có thống nhất về chính tả giữa dòng lệnh và build file.
2. Xác nhận lệnh gọi Ant có truyền đúng cặp `-Dname=value` hay không.
3. Kiểm tra property có được nạp từ `-propertyfile` hoặc task `<property file="..."/>` hay không.
4. Tìm lần khai báo đầu tiên của property thông thường, vì các lần khai báo sau không thay thế giá trị đã có.
5. Kiểm tra shell có tách giá trị thành nhiều đối số do dấu cách hoặc ký tự đặc biệt hay không.
6. In giá trị ngay trước target sử dụng để xác định thời điểm và nơi property đã được thiết lập.

Ví dụ thêm thông báo:

```xml
<target name="show-config">
    <echo message="env=[${env}]"/>
    <echo message="output.dir=[${output.dir}]"/>
</target>
```

Dấu ngoặc vuông trong thông báo giúp nhận ra dấu cách thừa ở đầu hoặc cuối giá trị.

Có thể chạy Ant với log chi tiết:

```bash
ant -verbose -Denv=prod show-config
```

Hoặc xem thông tin chẩn đoán môi trường:

```bash
ant -diagnostics
```

Khi cần kiểm tra property file, mở chính tệp đó và xác nhận tên key, dấu phân tách và encoding. Property file thường dùng cú pháp của Java Properties; ký tự đặc biệt và Unicode cần được lưu theo encoding mà phiên bản Ant/JDK đang sử dụng hỗ trợ.

## 11. Thực hành: một build file có thể chạy ở nhiều môi trường

Tạo tệp `build.xml`:

```xml
<project name="multi-env" default="show">

    <property name="env" value="dev"/>
    <property name="app.name" value="demo-service"/>
    <property name="output.dir" value="build"/>

    <target name="validate">
        <fail unless="env" message="Thiếu cấu hình env"/>
    </target>

    <target name="show" depends="validate">
        <echo message="Application: ${app.name}"/>
        <echo message="Environment: ${env}"/>
        <echo message="Output: ${output.dir}"/>
    </target>

</project>
```

Chạy mặc định:

```bash
ant
```

Kết quả sử dụng cấu hình `dev` và `build`.

Chạy cho môi trường kiểm thử:

```bash
ant -Denv=test -Doutput.dir=build-test
```

Chạy cho môi trường phát hành:

```bash
ant -Denv=prod -Doutput.dir=dist
```

Cùng một build file có thể phục vụ nhiều môi trường. Các target và task vẫn giữ nguyên, còn người gọi quyết định cấu hình đầu vào cho mỗi lần chạy.

Trong dự án thật, hãy giới hạn các property có thể thay đổi và ghi rõ ý nghĩa của chúng. Không nên biến mọi chi tiết nội bộ thành tham số dòng lệnh, vì điều đó khiến build khó sử dụng và khó kiểm soát.

## 12. Ghi nhớ

- Property là cặp tên và giá trị dùng để cấu hình build.
- Ant property có tính bất biến: khi đã thiết lập, lần khai báo thông thường tiếp theo không thay thế nó.
- User property thường được truyền bằng `-Dname=value` và có ưu tiên cao hơn property thông thường trong build file.
- `-propertyfile` nạp một bộ property cho lần chạy; các giá trị `-D` tường minh có thể ghi đè giá trị tương ứng trong tệp.
- Task `<property file="..."/>` nạp property trong quá trình xử lý build file và tuân theo quy tắc property thông thường.
- Giá trị mặc định trong build file giúp lệnh chạy ngắn gọn; user property cho phép tùy chỉnh mà không sửa build file.
- Điều kiện `if`/`unless` trên target kiểm tra sự tồn tại của property; chuỗi `false` vẫn là một giá trị đã tồn tại.
- Nếu cần nhiều giá trị khác nhau theo từng giai đoạn, hãy dùng tên property riêng thay vì cố gắng gán lại một property.

Khi thiết kế build file, hãy xác định rõ property nào là mặc định, property nào do người gọi cung cấp và property nào bắt buộc phải có. Nắm được độ ưu tiên và tính bất biến của user property sẽ giúp cùng một build file hoạt động nhất quán trong môi trường phát triển, kiểm thử và phát hành.

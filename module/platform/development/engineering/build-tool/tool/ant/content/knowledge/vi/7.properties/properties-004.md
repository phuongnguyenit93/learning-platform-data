# Nạp cấu hình từ tệp .properties và tham số -propertyfile trong Apache Ant

Buildfile Ant thường cần những giá trị thay đổi theo dự án hoặc môi trường chạy: thư mục mã nguồn, thư mục đầu ra, phiên bản ứng dụng, URL dịch vụ, tên artifact và tùy chọn biên dịch. Nếu ghi cứng tất cả giá trị này vào build.xml, mỗi lần đổi môi trường hoặc phiên bản, người phát triển có thể phải sửa file build.

Ant hỗ trợ nạp các cặp tên–giá trị từ tệp theo định dạng Java Properties. Có hai cách thường dùng:

- Dùng task property với thuộc tính file ngay trong buildfile.
- Truyền tùy chọn -propertyfile khi gọi Ant để nạp cấu hình cho một lần chạy.

Sau khi được nạp, giá trị có thể được tham chiếu trong buildfile bằng cú pháp ${property.name}. Nhờ đó, cùng một buildfile có thể sử dụng cấu hình phát triển, kiểm thử hoặc production mà không phải chỉnh sửa nội dung build cho từng môi trường.

## 1. Tệp .properties có cấu trúc như thế nào?

Tệp .properties là tệp văn bản lưu các cặp key và value. Mỗi dòng thường chứa một khai báo theo dạng key=value hoặc key:value.

Ví dụ, tạo file config/build.properties:

~~~properties
# Application information
app.name=inventory
app.version=1.4.0

# Source and output directories
src.dir=src/main/java
build.dir=build
dist.dir=dist

# Service configuration
service.baseUrl=https://dev.example.test/api
~~~

Trong ví dụ:

- app.name là tên ứng dụng.
- app.version là phiên bản dùng để đặt tên artifact.
- src.dir xác định thư mục mã nguồn.
- build.dir và dist.dir xác định thư mục đầu ra.
- service.baseUrl là địa chỉ dịch vụ mà ứng dụng hoặc quy trình build cần tham chiếu.

Một số quy tắc cơ bản của định dạng Properties:

- Dòng bắt đầu bằng dấu # hoặc ! được xem là comment.
- Dòng trống được bỏ qua.
- Dấu = hoặc : có thể phân cách key và value.
- Key phân biệt chữ hoa và chữ thường. Ví dụ app.name và APP.NAME là hai tên khác nhau.
- Nếu giá trị cần chứa ký tự phân cách hoặc khoảng trắng ở vị trí đặc biệt, dùng quy tắc escape của Java Properties.
- Dấu gạch chéo ngược ở cuối dòng có thể dùng để nối dòng tiếp theo thành một giá trị nhiều dòng.
- Ký tự Unicode có thể biểu diễn bằng escape dạng \uXXXX khi cần tương thích với cách đọc Properties dựa trên byte stream.

Ví dụ có comment và giá trị nhiều dòng:

~~~properties
# Build label
release.label=Inventory Release

# A logical description continued on the next line
release.note=Inventory application for \
internal warehouse operations
~~~

Tệp Properties không phải XML. Không đặt các key trong thẻ và không dùng cấu trúc lồng nhau. Ant đọc từng key/value rồi đưa chúng vào hệ thống property của project.

## 2. Nạp file bằng task property trong build.xml

Cách thứ nhất là khai báo task property ở cấp project:

~~~xml
<project name="inventory" default="package" basedir=".">
    <property file="config/build.properties" />

    <target name="show-config">
        <echo message="Application: ${app.name}" />
        <echo message="Version: ${app.version}" />
        <echo message="Source: ${src.dir}" />
    </target>
</project>
~~~

Khi Ant đọc buildfile, task property nạp các giá trị trong config/build.properties. Các task phía sau có thể sử dụng chúng bằng cú pháp tham chiếu property.

Chạy:

~~~bash
ant show-config
~~~

Ant sẽ hiển thị các giá trị tương ứng nếu file đã được nạp và các key tồn tại. Nếu tham chiếu đến property chưa được khai báo, biểu thức có thể vẫn còn nguyên trong thông báo hoặc giá trị task tùy nơi sử dụng; vì vậy hãy bảo đảm những property bắt buộc đã được cung cấp.

### 2.1. Đường dẫn của file cấu hình

Với thuộc tính file của task property, đường dẫn tương đối được phân giải theo basedir của project. Nếu project khai báo basedir=".", file config/build.properties được tìm từ thư mục cơ sở của buildfile.

Có thể dùng đường dẫn tuyệt đối khi thực sự cần, nhưng đường dẫn tương đối thường giúp buildfile dễ chuyển giữa máy cá nhân và CI hơn.

Task property cũng có thể khai báo trực tiếp giá trị thay vì đọc file:

~~~xml
<property name="app.name" value="inventory" />
<property name="build.dir" location="build" />
~~~

Thuộc tính value dùng cho giá trị thông thường. Thuộc tính location phù hợp với đường dẫn vì Ant chuẩn hóa giá trị thành vị trí dựa trên project. Cả hai đều tuân theo nguyên tắc property đã được thiết lập thì không thể bị ghi đè bằng một lần khai báo property thông thường sau đó.

## 3. Dùng giá trị mặc định khi file không cung cấp key

Một cách tổ chức phổ biến là nạp file cấu hình trước, sau đó khai báo các giá trị mặc định trong buildfile:

~~~xml
<project name="inventory" default="package" basedir=".">
    <property file="config/build.properties" />

    <property name="app.name" value="inventory" />
    <property name="app.version" value="1.0.0" />
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="dist" />

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}" />
        <jar destfile="${dist.dir}/${app.name}-${app.version}.jar"
             basedir="${classes.dir}" />
    </target>
</project>
~~~

Thứ tự khai báo có ý nghĩa:

1. Task property đầu tiên nạp những key có trong file.
2. Các task property tiếp theo cung cấp giá trị mặc định cho key chưa có.
3. Nếu file đã đặt app.version=1.4.0, khai báo mặc định app.version=1.0.0 phía sau không thay thế giá trị 1.4.0.
4. Nếu file không có app.name, giá trị mặc định inventory được sử dụng.

Cách làm này cho phép dự án có một bộ mặc định hợp lý nhưng vẫn tùy chỉnh được bằng file bên ngoài. Nếu khai báo mặc định trước rồi mới nạp file, giá trị mặc định có thể đã chiếm tên property và ngăn file thay thế nó. Vì vậy, khi muốn file cung cấp giá trị ưu tiên hơn mặc định, hãy nạp file trước.

## 4. Nạp file từ dòng lệnh bằng -propertyfile

Thay vì ghi task property vào buildfile, có thể chỉ định file cấu hình khi gọi Ant:

~~~bash
ant -propertyfile config/build.properties package
~~~

Tùy chọn -propertyfile yêu cầu Ant nạp các property từ file được chỉ định cho lần chạy đó. Cách này hữu ích khi muốn giữ nguyên buildfile và chọn cấu hình theo môi trường ngay tại dòng lệnh.

Ví dụ, tổ chức các file:

~~~text
project/
├── build.xml
└── config/
    ├── dev.properties
    ├── test.properties
    └── prod.properties
~~~

Nội dung config/dev.properties:

~~~properties
app.name=inventory
app.version=1.4.0-SNAPSHOT
build.dir=build/dev
dist.dir=dist/dev
service.baseUrl=https://dev.example.test/api
~~~

Nội dung config/test.properties:

~~~properties
app.name=inventory
app.version=1.4.0-RC1
build.dir=build/test
dist.dir=dist/test
service.baseUrl=https://test.example.test/api
~~~

Nội dung config/prod.properties:

~~~properties
app.name=inventory
app.version=1.4.0
build.dir=build/prod
dist.dir=dist/prod
service.baseUrl=https://api.example.com
~~~

Cùng một buildfile có thể được gọi theo các cách:

~~~bash
ant -propertyfile config/dev.properties package
ant -propertyfile config/test.properties package
ant -propertyfile config/prod.properties package
~~~

Mỗi lệnh chọn một bộ cấu hình khác nhau. Buildfile không phải sửa mỗi khi đổi môi trường; người vận hành chỉ chọn file phù hợp với mục tiêu của lần build.

Lưu ý rằng đường dẫn config/dev.properties trong ví dụ là đường dẫn mà shell phân giải từ thư mục hiện tại khi chạy lệnh. Hãy chạy lệnh tại thư mục dự án hoặc cung cấp đường dẫn phù hợp với vị trí hiện tại.

## 5. Kết hợp -propertyfile với -D để ghi đè một giá trị

Có những lần chạy chỉ cần thay đổi một property so với file cấu hình. Ant hỗ trợ tùy chọn -Dname=value để truyền giá trị từ dòng lệnh:

~~~bash
ant -propertyfile config/prod.properties -Dapp.version=1.4.1 package
~~~

Trong ví dụ, file production cung cấp các cấu hình chung, còn -Dapp.version=1.4.1 chỉ định phiên bản artifact cho lần chạy này. Theo quy tắc của Ant, property được truyền bằng -D có ưu tiên cao hơn giá trị cùng tên được nạp bằng -propertyfile.

Điều này tiện khi phát hành bản vá hoặc build một phiên bản cụ thể mà không cần sửa file cấu hình chuẩn. Có thể truyền nhiều property:

~~~bash
ant -propertyfile config/test.properties \
    -Dapp.version=1.4.0-RC2 \
    -Dservice.baseUrl=https://test2.example.test/api \
    package
~~~

Khi viết lệnh trên một dòng, bỏ ký tự nối dòng phù hợp với shell đang sử dụng. Trong PowerShell, có thể dùng dấu backtick để nối dòng; trong Bash, dấu gạch chéo ngược ở cuối dòng thường được dùng.

Không nên lạm dụng -D để truyền một danh sách cấu hình rất dài. Nếu nhiều giá trị cùng thay đổi theo môi trường, hãy tạo file .properties riêng để dễ quản lý và tái sử dụng.

## 6. Quy tắc property bất biến và thứ tự ưu tiên

Một điểm quan trọng khi dùng property trong Ant là property có tính bất biến. Khi một tên property đã được thiết lập, một task property thông thường chạy sau không thể gán lại giá trị khác cho cùng tên đó.

Ví dụ:

~~~xml
<project name="property-order" default="show">
    <property name="app.mode" value="development" />
    <property name="app.mode" value="production" />

    <target name="show">
        <echo message="Mode: ${app.mode}" />
    </target>
</project>
~~~

Kết quả vẫn là development vì lần khai báo đầu tiên đã thiết lập property. Khai báo thứ hai không thay đổi giá trị đã có.

Khi dùng file và tham số dòng lệnh, cần nhớ các nguyên tắc sau:

| Nguồn cấu hình | Vai trò |
|---|---|
| -Dname=value | Giá trị do người gọi truyền rõ ràng; có ưu tiên hơn property cùng tên trong file được nạp bằng -propertyfile |
| -propertyfile file.properties | Nạp bộ property cho lần chạy Ant; các giá trị này có sẵn khi buildfile được xử lý và có thể ghi đè giá trị mặc định khai báo thông thường trong buildfile |
| <property file="..."/> | Nạp property tại vị trí task trong buildfile; chỉ thiết lập các key chưa có giá trị |
| <property name="..." value="..."/> | Khai báo giá trị trực tiếp; nếu property đã được thiết lập thì giá trị cũ được giữ |

Có thể áp dụng cách đọc đơn giản: giá trị người gọi truyền rõ ràng qua -D được ưu tiên, file cấu hình được chọn cho lần chạy cung cấp bộ giá trị, còn các khai báo property trong buildfile đóng vai trò mặc định nếu tên đó chưa được thiết lập.

Khi dùng task property để nạp file và muốn có mặc định, hãy đặt task nạp file trước các task khai báo mặc định. Không nên kỳ vọng một task property phía sau sẽ sửa giá trị đã được nạp.

Cũng cần lưu ý rằng property không phải biến có thể thay đổi trong suốt build. Nếu cần tính toán hoặc cập nhật trạng thái nhiều lần, hãy chọn cơ chế khác phù hợp với task và mục đích; đừng cố khai báo lại property cùng tên.

## 7. Kết hợp file cấu hình với các target

Giá trị được nạp từ file có thể dùng trong hầu hết thuộc tính task cần chuỗi, đường dẫn hoặc tham số. Ví dụ:

~~~xml
<project name="inventory" default="package" basedir=".">
    <property file="config/build.properties" />
    <property name="app.name" value="inventory" />
    <property name="app.version" value="1.0.0" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="dist" />

    <target name="prepare">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile">
        <jar destfile="${dist.dir}/${app.name}-${app.version}.jar"
             basedir="${classes.dir}" />
    </target>

    <target name="show-config">
        <echo message="Application: ${app.name}" />
        <echo message="Version: ${app.version}" />
        <echo message="Service: ${service.baseUrl}" />
    </target>
</project>
~~~

Với cấu hình phù hợp, lệnh sau tạo artifact theo phiên bản được chọn:

~~~bash
ant -propertyfile config/dev.properties package
~~~

Còn lệnh sau chỉ hiển thị một số giá trị để kiểm tra:

~~~bash
ant -propertyfile config/test.properties show-config
~~~

Target show-config hữu ích trong giai đoạn thiết lập build vì giúp phát hiện file cấu hình chưa được nạp hoặc key bị đặt sai tên. Không nên in các giá trị nhạy cảm như mật khẩu, token hay thông tin xác thực vào log CI.

## 8. Xử lý lỗi cấu hình thường gặp

### 8.1. Sai đường dẫn file

Nếu Ant không tìm thấy file được chỉ định, hãy kiểm tra:

- Lệnh được chạy từ thư mục hiện tại nào?
- Đường dẫn truyền cho -propertyfile có đúng so với thư mục đó không?
- Nếu dùng task property, đường dẫn file có đúng so với basedir của project không?
- Tên file và phần mở rộng có chính xác không?

Trên Windows, đường dẫn chứa khoảng trắng cần được đặt trong dấu ngoặc kép:

~~~powershell
ant -propertyfile "config/local development.properties" package
~~~

### 8.2. Property không được nạp

Nếu thông báo vẫn hiển thị biểu thức như ${app.version}, hãy kiểm tra key trong file có trùng chính xác tên được tham chiếu hay không. Tên property phân biệt chữ hoa và chữ thường.

Ví dụ file có:

~~~properties
app.version=1.4.0
~~~

nhưng buildfile lại tham chiếu ${app.Version}, hai tên không trùng nhau.

### 8.3. Giá trị mặc định ghi trước file

Nếu buildfile khai báo:

~~~xml
<property name="app.version" value="1.0.0" />
<property file="config/build.properties" />
~~~

và file có app.version=1.4.0, giá trị mặc định đã được thiết lập trước nên task property phía sau không thay thế nó. Hãy chuyển task nạp file lên trước các khai báo mặc định nếu muốn file cung cấp giá trị ưu tiên.

### 8.4. Dùng nhầm -propertyfile và -D

Tùy chọn -propertyfile nhận đường dẫn tới file chứa nhiều cặp key/value. Tùy chọn -D nhận một property đơn lẻ theo dạng -Dname=value. Không truyền nội dung file vào -D hoặc dùng -propertyfile như thể nó nhận trực tiếp tên property.

### 8.5. Nhầm đường dẫn tương đối với đường dẫn tuyệt đối

Một đường dẫn như build/output được hiểu tương đối theo ngữ cảnh của project/task hoặc thư mục gọi lệnh tùy vị trí khai báo. Nếu build chạy từ nhiều thư mục khác nhau, hãy quy định rõ thư mục làm việc của CI và dùng basedir/location nhất quán.

### 8.6. Chứa ký tự đặc biệt hoặc dữ liệu nhạy cảm

Tệp Properties tuân theo quy tắc escape của Java Properties. Nếu giá trị có ký tự phân cách, dấu gạch chéo ngược hoặc khoảng trắng đặc biệt, hãy kiểm tra cách escape và cách parser đọc giá trị.

Không nên commit mật khẩu, token hoặc khóa riêng vào file cấu hình nằm trong Git. Dùng secret store hoặc biến môi trường được quản lý bởi CI cho thông tin xác thực; chỉ đưa giá trị không nhạy cảm vào file cấu hình có thể chia sẻ.

## 9. Thực hành tốt khi tổ chức cấu hình

- **Tách cấu hình khỏi logic build.** Giữ task và dependency trong build.xml; đặt các giá trị thay đổi theo môi trường trong file Properties.
- **Có bộ mặc định dùng được.** Nạp file trước rồi khai báo mặc định sau để người dùng không bắt buộc phải cung cấp mọi key.
- **Đặt tên property nhất quán.** Có thể dùng nhóm tên như app.*, src.*, build.*, dist.* và service.* để dễ nhận diện.
- **Tạo file theo môi trường khi có nhiều khác biệt.** dev.properties, test.properties và prod.properties giúp lựa chọn rõ ràng khi gọi Ant.
- **Chỉ ghi đè có chủ đích.** Dùng -D cho một vài giá trị cần thay đổi trong một lần build; không biến dòng lệnh thành nơi lưu toàn bộ cấu hình.
- **Không phụ thuộc vào thứ tự ngẫu nhiên.** Vì property bất biến, thứ tự nạp file và khai báo mặc định cần được tổ chức rõ ràng.
- **Kiểm tra key bắt buộc.** Dùng target hiển thị cấu hình không nhạy cảm hoặc các điều kiện kiểm tra phù hợp để phát hiện thiếu property trước khi chạy công việc tốn thời gian.
- **Giữ bí mật ngoài repository.** Dùng cơ chế secret của môi trường chạy cho thông tin xác thực và tránh in chúng ra log.
- **Ghi rõ cách chạy.** README hoặc tài liệu vận hành nên chỉ ra file cấu hình nào dành cho từng môi trường và lệnh Ant tương ứng.

## 10. Kết luận

Ant có thể nạp cấu hình từ file .properties bằng task property với thuộc tính file, hoặc bằng tùy chọn -propertyfile khi chạy Ant. Cách thứ nhất đặt việc nạp cấu hình ngay trong buildfile; cách thứ hai cho phép người vận hành chọn file cho từng lần chạy mà không chỉnh sửa buildfile. Tham số -Dname=value phù hợp để ghi đè một vài giá trị riêng, và có ưu tiên hơn giá trị trùng tên được nạp bằng -propertyfile.

Do property của Ant bất biến, thứ tự khai báo rất quan trọng: nạp file trước rồi khai báo mặc định sau nếu muốn file có thể cung cấp giá trị. Khi tổ chức các file theo môi trường, đặt tên key rõ ràng và kiểm tra cấu hình trước khi build, cùng một buildfile có thể được sử dụng nhất quán trên máy phát triển và hệ thống CI.


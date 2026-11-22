# Đọc và ghi cấu hình bằng loadproperties, loadfile và propertyfile trong Apache Ant

Apache Ant cung cấp các task để làm việc với dữ liệu cấu hình bên ngoài build file. Ba task thường gặp là **loadproperties**, **loadfile** và **propertyfile**. Chúng có tên gần giống nhau nhưng đảm nhiệm ba hướng xử lý khác nhau:

- **loadproperties** đọc file theo định dạng Java Properties và đưa từng cặp khóa/giá trị vào hệ thống property của Ant.
- **loadfile** đọc toàn bộ nội dung của một file thành một property duy nhất.
- **propertyfile** tạo mới hoặc cập nhật các mục trong file properties để lưu cấu hình lâu dài.

Hiểu đúng vai trò của từng task giúp build file tách cấu hình khỏi logic build, đọc nội dung văn bản cần thiết và cập nhật những giá trị như số build hoặc thời điểm phát hành.

## 1. Phân biệt ba task

| Task | Hướng dữ liệu | Kết quả | Tình huống phù hợp |
|---|---|---|---|
| loadproperties | File properties → Ant | Nhiều property trong project | Nạp cấu hình môi trường, phiên bản, thư mục, endpoint. |
| loadfile | File văn bản → Ant | Một property chứa toàn bộ nội dung file | Đọc banner, ghi chú phát hành hoặc nội dung mẫu. |
| propertyfile | Ant → File properties | File được tạo hoặc cập nhật | Tăng số build, ghi phiên bản, cập nhật thời điểm chạy. |

Ví dụ, file cấu hình:

~~~properties
app.name=Inventory Service
app.version=2.4.0
app.environment=staging
~~~

Nếu muốn dùng từng giá trị trong build file, hãy dùng **loadproperties**. Nếu có file release-notes.txt chứa nhiều dòng văn bản và muốn đưa cả nội dung vào một property, hãy dùng **loadfile**. Nếu muốn ghi build.number mới vào file để lần chạy sau tiếp tục sử dụng, hãy dùng **propertyfile**.

Một điểm quan trọng: property trong Ant có nguyên tắc **first definition wins**. Task đọc file không biến property thành biến có thể gán lại. Task ghi file cũng không đồng nghĩa với việc cập nhật lại các property đã nạp trong bộ nhớ của project.

## 2. Đọc file properties bằng loadproperties

### 2.1. Mục đích và cách hoạt động

Task loadproperties đọc một file theo định dạng Java Properties. Mỗi khóa trong file trở thành tên property, còn giá trị tương ứng trở thành giá trị property.

Ví dụ file config/build.properties:

~~~properties
app.name=Inventory Service
app.version=2.4.0
app.environment=staging
build.number=15
~~~

Nạp file:

~~~xml
<loadproperties srcFile="config/build.properties"/>
~~~

Sau khi task chạy, build file có thể tham chiếu:

~~~xml
<echo message="Application: ${app.name}"/>
<echo message="Version: ${app.version}"/>
<echo message="Environment: ${app.environment}"/>
<echo message="Build: ${build.number}"/>
~~~

Như vậy, loadproperties biến nhiều dòng cấu hình thành nhiều property riêng biệt. Bạn có thể dùng chúng trong thuộc tính task, điều kiện target, đường dẫn hoặc nội dung log.

### 2.2. Cú pháp và thuộc tính thường dùng

~~~xml
<loadproperties srcFile="path/to/config.properties"/>
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| srcFile | File properties cần đọc. |
| resource | Tên resource cần nạp từ classpath. Có thể dùng thay cho srcFile. |
| classpath | Classpath để tìm resource. |
| classpathref | Tham chiếu đến một path đã khai báo bằng id để tìm resource. |
| prefix | Tiền tố được thêm vào tên các property được nạp. |
| prefixValues | Nếu bật, thêm cùng tiền tố vào tên property trong các tham chiếu ${...} nằm trong giá trị được nạp. |
| encoding | Bảng mã dùng để đọc file. |
| failonerror | Quyết định việc không đọc được nguồn có làm build thất bại hay không. |

Thông thường, bạn chọn một nguồn đọc: srcFile cho file trên hệ thống file hoặc resource cho tài nguyên có thể tìm thấy qua classpath.

### 2.3. Nạp file với prefix

Khi nhiều file cấu hình có thể chứa các khóa trùng tên, dùng prefix để phân biệt các nhóm property.

Ví dụ file:

~~~properties
name=Inventory Service
version=2.4.0
environment=staging
~~~

Nạp với prefix:

~~~xml
<loadproperties
    srcFile="config/simple.properties"
    prefix="app"/>
~~~

Các property được tạo có tên:

~~~text
app.name
app.version
app.environment
~~~

Khi sử dụng:

~~~xml
<echo message="Application: ${app.name}"/>
<echo message="Version: ${app.version}"/>
~~~

prefix chỉ thay đổi tên property khi nạp. Nó không thay đổi nội dung file nguồn.

Cách này hữu ích khi một build file cần nạp nhiều nhóm cấu hình:

~~~xml
<loadproperties srcFile="config/app.properties" prefix="app"/>
<loadproperties srcFile="config/database.properties" prefix="db"/>
<loadproperties srcFile="config/deployment.properties" prefix="deploy"/>
~~~

Cả ba file có thể chứa khóa name, nhưng chúng được phân biệt thành app.name, db.name và deploy.name.

### 2.4. Hiểu prefixValues

Giả sử file config/message.properties có nội dung:

~~~properties
name=Inventory Service
welcome=Welcome to ${name}
~~~

Nếu nạp:

~~~xml
<loadproperties
    srcFile="config/message.properties"
    prefix="app"/>
~~~

thì tên property trở thành app.name và app.welcome. Tuy nhiên, phần tham chiếu ${name} bên trong giá trị welcome vẫn giữ nguyên tên name.

Khi muốn tham chiếu bên trong giá trị cũng được thêm tiền tố, dùng prefixValues="true":

~~~xml
<loadproperties
    srcFile="config/message.properties"
    prefix="app"
    prefixValues="true"/>
~~~

Giá trị sau khi nạp có ý nghĩa tương đương:

~~~text
app.name = Inventory Service
app.welcome = Welcome to ${app.name}
~~~

Khi đó, nếu Ant mở rộng property reference trong một task sử dụng app.welcome, tham chiếu sẽ trỏ đến app.name.

Cần phân biệt hai hành vi:

- prefix đổi tên các property được nạp.
- prefixValues điều chỉnh tên property được tham chiếu trong các giá trị được nạp.

prefixValues không phải tùy chọn để mở rộng mọi biểu thức ngay lập tức; nó điều chỉnh tên trong các tham chiếu property.

### 2.5. Nạp resource từ classpath

Không phải cấu hình nào cũng nằm dưới dạng file có đường dẫn trực tiếp. Nếu file properties được đóng gói trong classpath, có thể dùng thuộc tính resource.

Ví dụ:

~~~xml
<path id="build.config.classpath">
    <pathelement location="config-resources"/>
    <pathelement location="lib/build-support.jar"/>
</path>

<loadproperties
    resource="defaults.properties"
    classpathref="build.config.classpath"
    prefix="defaults"/>
~~~

Ant tìm resource defaults.properties qua classpath đã chỉ định và nạp các property với tiền tố defaults.

Có thể khai báo classpath trực tiếp nếu không cần tái sử dụng:

~~~xml
<loadproperties resource="defaults.properties">
    <classpath>
        <pathelement location="config-resources"/>
    </classpath>
</loadproperties>
~~~

resource phù hợp với cấu hình được phân phối cùng tài nguyên của build hoặc thư viện hỗ trợ. srcFile phù hợp khi bạn muốn chỉ rõ file cấu hình nằm ở vị trí nào trên hệ thống file.

### 2.6. Định dạng file properties

File properties thường có dạng khóa và giá trị:

~~~properties
app.name=Inventory Service
app.version=2.4.0
app.environment=staging
~~~

Có thể dùng dấu bằng hoặc dấu hai chấm để phân cách khóa và giá trị:

~~~properties
app.name=Inventory Service
app.version:2.4.0
~~~

Dòng bắt đầu bằng # hoặc ! thường được xem là chú thích:

~~~properties
# Application configuration
app.name=Inventory Service
! Release version
app.version=2.4.0
~~~

Khoảng trắng đầu dòng được xử lý theo quy tắc của định dạng Java Properties. Nếu giá trị cần chứa ký tự đặc biệt, dấu phân cách hoặc xuống dòng, hãy dùng quy tắc escape của định dạng này.

Ví dụ:

~~~properties
message=Hello\=Ant
windows.path=C\:\\tools\\ant
multiline=First line\
  second line
~~~

Một số lưu ý:

- Dấu bằng hoặc dấu hai chấm trong giá trị có thể cần escape tùy vị trí.
- Dấu gạch chéo ngược có ý nghĩa đặc biệt trong file properties.
- Một dấu gạch chéo ngược ở cuối dòng có thể nối dòng tiếp theo vào cùng giá trị.
- Ký tự Unicode có thể được biểu diễn bằng escape dạng \uXXXX theo định dạng Java Properties.

Nếu cấu hình có tiếng Việt hoặc ký tự ngoài ASCII, hãy thống nhất encoding giữa công cụ tạo file và task đọc file. Có thể chỉ định encoding trên loadproperties khi phiên bản Ant đang dùng hỗ trợ thuộc tính này. Định dạng properties truyền thống của Java dùng ISO-8859-1 và escape Unicode; khi chọn encoding khác, cần bảo đảm file được ghi và đọc cùng một quy ước.

### 2.7. Nạp có điều kiện khi file cấu hình là tùy chọn

Trong một số project, file cấu hình cục bộ có thể không tồn tại ở mọi máy. Khi task hỗ trợ failonerror, có thể cho phép bỏ qua lỗi đọc nguồn tùy chọn:

~~~xml
<loadproperties
    srcFile="config/local.properties"
    prefix="local"
    failonerror="false"/>
~~~

Cách dùng này chỉ phù hợp khi file thực sự không bắt buộc. Nếu file chứa cấu hình cần thiết để build đúng, nên để lỗi đọc file làm build thất bại để tránh sử dụng cấu hình thiếu hoặc không chính xác.

## 3. Đọc toàn bộ nội dung file bằng loadfile

### 3.1. Mục đích và cách hoạt động

loadfile đọc toàn bộ nội dung của một file văn bản và lưu vào **một property duy nhất**. Task này không phân tích nội dung theo cặp khóa/giá trị như loadproperties.

Ví dụ file release-notes.txt:

~~~text
Version 2.4.0

- Add inventory search.
- Improve report export.
- Fix startup configuration.
~~~

Nạp nội dung:

~~~xml
<loadfile
    property="release.notes"
    srcFile="release-notes.txt"
    encoding="UTF-8"/>
~~~

Sau đó có thể dùng property trong task khác:

~~~xml
<echo message="${release.notes}"/>
~~~

Property release.notes chứa toàn bộ nội dung file, bao gồm các dòng và ký tự xuống dòng được đọc.

### 3.2. Cú pháp và thuộc tính thường dùng

~~~xml
<loadfile
    property="property.name"
    srcFile="path/to/file.txt"
    encoding="UTF-8"/>
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| property | Tên property nhận toàn bộ nội dung file. |
| srcFile | File văn bản cần đọc. |
| encoding | Bảng mã dùng để giải mã nội dung file. |
| failonerror | Quyết định việc không đọc được file có làm build thất bại hay không. |

property và srcFile là hai thông tin cốt lõi: Ant cần biết nội dung đi từ file nào và sẽ được đặt vào property nào.

### 3.3. Dùng loadfile để đưa nội dung vào task

Ví dụ đưa banner vào log:

~~~xml
<loadfile
    property="build.banner"
    srcFile="config/banner.txt"
    encoding="UTF-8"/>

<target name="show-banner">
    <echo message="${build.banner}"/>
</target>
~~~

Ví dụ đưa ghi chú phát hành vào file khác:

~~~xml
<loadfile
    property="release.notes"
    srcFile="release-notes.txt"
    encoding="UTF-8"/>

<target name="publish-notes">
    <echo file="build/release-notes.txt"
          message="${release.notes}"/>
</target>
~~~

Trong ví dụ thứ hai, loadfile chỉ đọc nội dung và tạo property. Task echo mới là task ghi nội dung ra file đích.

### 3.4. Biến đổi nội dung bằng filterchain

loadfile có thể kết hợp filterchain để biến đổi nội dung trong lúc đọc. Điều này hữu ích khi file chứa dòng chú thích, khoảng trắng thừa hoặc cần áp dụng một số bộ lọc trước khi lưu vào property.

Ví dụ file config/banner.txt:

~~~text
# Banner shown during build
Inventory Service
Release channel: staging
# Internal note: this line is not shown
~~~

Nạp file và loại các dòng chú thích bắt đầu bằng #:

~~~xml
<loadfile
    property="build.banner"
    srcFile="config/banner.txt"
    encoding="UTF-8">

    <filterchain>
        <striplinecomments>
            <comment value="#"/>
        </striplinecomments>
    </filterchain>

</loadfile>
~~~

Sau filterchain, property chứa nội dung đã qua bộ lọc. striplinecomments là filter reader loại các dòng chú thích theo ký hiệu được khai báo trong phần tử comment.

Có thể kết hợp nhiều filter reader theo thứ tự:

~~~xml
<loadfile
    property="release.notes"
    srcFile="release-notes.txt"
    encoding="UTF-8">

    <filterchain>
        <striplinecomments>
            <comment value="#"/>
        </striplinecomments>
        <trim/>
    </filterchain>

</loadfile>
~~~

Thứ tự filter reader có ý nghĩa vì đầu ra của bộ lọc trước trở thành đầu vào cho bộ lọc tiếp theo. Chỉ thêm filter khi bạn thực sự muốn thay đổi nội dung đọc được; nếu cần giữ nguyên file, hãy nạp trực tiếp.

### 3.5. loadfile không phải cách đọc file properties thành nhiều property

Giả sử file có nội dung:

~~~properties
app.name=Inventory Service
app.version=2.4.0
~~~

Nếu dùng:

~~~xml
<loadfile
    property="config.text"
    srcFile="config/build.properties"
    encoding="UTF-8"/>
~~~

Ant tạo một property tên config.text, chứa nguyên nội dung hai dòng. Ant không tự tạo app.name và app.version.

Muốn có từng property riêng, hãy dùng loadproperties:

~~~xml
<loadproperties srcFile="config/build.properties"/>
~~~

Đây là khác biệt quan trọng nhất giữa hai task đọc file.

### 3.6. Kích thước nội dung và cách sử dụng

Vì toàn bộ file được giữ trong một property, loadfile phù hợp với nội dung văn bản có kích thước hợp lý như banner, ghi chú phát hành, mẫu thông báo hoặc một đoạn cấu hình cần chuyển tiếp.

Không nên mặc định dùng loadfile cho file nhị phân hoặc file cực lớn. Property là dữ liệu chuỗi trong bộ nhớ build; task này không phải cơ chế truyền file nhị phân hay xử lý luồng dữ liệu dung lượng lớn.

Nếu nội dung được đưa vào log hoặc thông điệp lỗi, hãy kiểm soát dữ liệu trước khi in. File có thể chứa token, mật khẩu hoặc thông tin nội bộ mà bạn không muốn xuất hiện trong log build.

## 4. Ghi và cập nhật file properties bằng propertyfile

### 4.1. Mục đích và cách hoạt động

propertyfile tạo mới hoặc cập nhật một file theo định dạng Java Properties. Khác với loadproperties và loadfile, task này ghi dữ liệu từ build vào file để lưu lại cho những lần chạy sau.

Ví dụ file build.properties ban đầu:

~~~properties
app.version=2.4.0
build.number=15
~~~

Build file:

~~~xml
<propertyfile file="build.properties">
    <entry key="build.number"
           type="int"
           operation="+"
           value="1"/>
</propertyfile>
~~~

Sau khi task chạy, build.number được tăng lên một đơn vị. Lần chạy tiếp theo có thể đọc lại file để lấy giá trị mới.

propertyfile phù hợp với những dữ liệu cần được duy trì giữa các lần chạy, chẳng hạn:

- Số build tăng dần.
- Phiên bản hoặc mã phát hành.
- Thời điểm build gần nhất.
- Một số giá trị trạng thái do quy trình build quản lý.

### 4.2. Cú pháp và thuộc tính thường dùng

~~~xml
<propertyfile file="path/to/build.properties">
    <entry key="property.name" value="new-value"/>
</propertyfile>
~~~

Các thuộc tính thường dùng của task:

| Thuộc tính | Ý nghĩa |
|---|---|
| file | File properties cần tạo hoặc cập nhật. |
| comment | Chú thích phần đầu file được ghi ra. |
| encoding | Bảng mã dùng khi ghi file, nếu phiên bản Ant hỗ trợ thuộc tính này. |

Mỗi phần tử con entry mô tả một property cần cập nhật. Task có thể xử lý nhiều entry trong một lần chạy.

### 4.3. Cập nhật giá trị chuỗi

Với giá trị chuỗi, khai báo key và value:

~~~xml
<propertyfile file="config/build.properties"
              comment="Generated by Apache Ant">
    <entry key="app.version" value="2.5.0"/>
    <entry key="app.environment" value="production"/>
    <entry key="release.channel" value="stable"/>
</propertyfile>
~~~

Nếu khóa đã tồn tại, giá trị được cập nhật. Nếu khóa chưa tồn tại, task thêm khóa mới vào file.

Nếu file chưa tồn tại, propertyfile có thể tạo file mới và ghi các entry đã khai báo.

### 4.4. Tăng số build bằng type int

Một ứng dụng thường cần số build tăng dần sau mỗi lần chạy quy trình phát hành.

Ví dụ:

~~~properties
build.number=15
~~~

Cấu hình Ant:

~~~xml
<propertyfile file="build.properties">
    <entry key="build.number"
           type="int"
           operation="+"
           value="1"
           default="0"/>
</propertyfile>
~~~

Kết quả sau lần chạy đầu tiên với giá trị ban đầu là 15:

~~~properties
build.number=16
~~~

Các thuộc tính trong entry:

- key: tên property cần cập nhật.
- type="int": xử lý giá trị như số nguyên.
- operation="+": cộng giá trị mới vào giá trị hiện tại.
- value="1": số được cộng.
- default="0": giá trị khởi đầu nếu khóa chưa có trong file.

Các phép toán số học thường dùng gồm:

| operation | Ý nghĩa |
|---|---|
| = | Gán giá trị. |
| + | Cộng. |
| - | Trừ. |
| * | Nhân. |
| / | Chia. |
| % | Lấy phần dư. |

Các phép toán số học yêu cầu giá trị hiện tại có thể chuyển thành số hợp lệ. Nếu file chứa chuỗi không phải số trong một entry kiểu int, task có thể thất bại khi xử lý giá trị đó.

Ví dụ tăng số build:

~~~xml
<entry key="build.number"
       type="int"
       operation="+"
       value="1"
       default="0"/>
~~~

Ví dụ giảm bộ đếm:

~~~xml
<entry key="retry.remaining"
       type="int"
       operation="-"
       value="1"
       default="3"/>
~~~

Hãy chọn giá trị default phù hợp với ý nghĩa nghiệp vụ. Nếu không khai báo mặc định, giá trị mặc định phụ thuộc loại entry và quy tắc của task.

### 4.5. Ghi ngày giờ bằng type date

Có thể ghi thời điểm cập nhật bằng entry kiểu date:

~~~xml
<propertyfile file="build.properties">
    <entry key="last.build"
           type="date"
           value="now"
           pattern="yyyy-MM-dd HH:mm:ss"/>
</propertyfile>
~~~

value="now" yêu cầu task lấy thời điểm hiện tại. pattern xác định định dạng chuỗi ngày giờ theo quy tắc của Java date format.

Ví dụ giá trị được ghi:

~~~properties
last.build=2026-11-12 22:30:00
~~~

Giá trị cụ thể phụ thuộc thời điểm chạy và múi giờ của môi trường build.

Một số mẫu định dạng:

| Pattern | Dạng kết quả minh họa |
|---|---|
| yyyy-MM-dd | 2026-11-12 |
| yyyyMMdd | 20261112 |
| yyyy-MM-dd HH:mm:ss | 2026-11-12 22:30:00 |
| dd/MM/yyyy | 12/11/2026 |

Ký tự hoa và thường trong pattern có ý nghĩa khác nhau. Ví dụ MM là tháng, còn mm là phút.

### 4.6. Nhiều entry trong cùng một lần ghi

Bạn có thể cập nhật nhiều giá trị cùng lúc:

~~~xml
<propertyfile file="build.properties"
              comment="Build metadata">
    <entry key="app.version" value="2.5.0"/>
    <entry key="build.number"
           type="int"
           operation="+"
           value="1"
           default="0"/>
    <entry key="last.build"
           type="date"
           value="now"
           pattern="yyyy-MM-dd HH:mm:ss"/>
</propertyfile>
~~~

Cách này giúp một task ghi đồng bộ các metadata của lần build. Mỗi entry có kiểu và quy tắc riêng.

### 4.7. Comment và định dạng file

Thuộc tính comment đặt chú thích phần đầu cho file được ghi. Không nên xem propertyfile như trình chỉnh sửa văn bản bảo toàn nguyên vẹn từng dòng, thứ tự, khoảng trắng và chú thích ban đầu. Task đọc các property rồi ghi lại file theo cơ chế lưu trữ properties; bố cục và comment cũ có thể không được giữ nguyên như bản gốc.

Nếu file cấu hình có comment do con người biên soạn, thứ tự đặc biệt hoặc format cần bảo toàn tuyệt đối, hãy cân nhắc dùng một công cụ xử lý văn bản phù hợp thay vì dùng propertyfile để sửa file đó.

## 5. Property trong bộ nhớ và giá trị được ghi ra file

Đây là điểm cần hiểu rõ khi kết hợp ba task.

### 5.1. loadproperties và loadfile đặt property cho project

Hai task đọc file đưa dữ liệu vào hệ thống property của Ant:

~~~xml
<loadproperties srcFile="build.properties"/>
<loadfile property="release.notes" srcFile="release-notes.txt"/>
~~~

Các property đã được đặt tuân theo quy tắc bất biến thông thường của Ant. Nếu property cùng tên đã tồn tại, task đọc file không nên được xem là cách ghi đè giá trị cũ.

### 5.2. propertyfile cập nhật file, không phải phép gán property thông thường

Task propertyfile lưu giá trị vào file. Nó không phải cơ chế để gán lại một property đã được nạp trong project.

Ví dụ, nếu build file đã nạp:

~~~xml
<loadproperties srcFile="build.properties"/>
~~~

sau đó cập nhật file:

~~~xml
<propertyfile file="build.properties">
    <entry key="build.number"
           type="int"
           operation="+"
           value="1"/>
</propertyfile>
~~~

thì file trên đĩa có số build mới. Property build.number đã được nạp trước đó trong project vẫn giữ giá trị cũ trong lần chạy hiện tại.

Nếu cần đọc lại giá trị vừa ghi, có thể nạp file vào một namespace mới bằng prefix:

~~~xml
<loadproperties
    srcFile="build.properties"
    prefix="stored"/>
~~~

Sau đó dùng ${stored.build.number} để đọc giá trị vừa được lưu.

Không nên kỳ vọng nạp lại vào cùng tên property sẽ ghi đè giá trị cũ, vì nguyên tắc first definition wins vẫn áp dụng.

### 5.3. Chọn đúng task theo hướng dữ liệu

~~~text
                   File properties
                  /               \
                 /                 \
        loadproperties             propertyfile
              |                         ^
              v                         |
      Nhiều property trong Ant     Cập nhật file
                                       
       File văn bản
            |
            v
         loadfile
            |
            v
    Một property chứa nội dung
~~~

- Dữ liệu đi từ file properties vào nhiều property: loadproperties.
- Dữ liệu đi từ file văn bản vào một property: loadfile.
- Dữ liệu từ build được ghi trở lại file properties: propertyfile.

## 6. Kết hợp ba task trong một quy trình

Một build có thể vừa nạp cấu hình ứng dụng, vừa đọc ghi chú phát hành, vừa cập nhật metadata cho lần chạy.

### 6.1. Cấu trúc file đầu vào

Giả sử có các file:

~~~text
project/
├── build.xml
└── config/
    ├── build.properties
    └── release-notes.txt
~~~

config/build.properties:

~~~properties
name=Inventory Service
version=2.4.0
environment=staging
build.number=15
~~~

config/release-notes.txt:

~~~text
# Release notes
Inventory Service 2.4.0

- Add inventory search.
- Improve report export.
~~~

### 6.2. Build file kết hợp các task

~~~xml
<project name="inventory-service" default="show-config" basedir=".">

    <property name="config.dir" location="config"/>

    <!-- Nạp từng cấu hình thành property có prefix app. -->
    <loadproperties
        srcFile="config/build.properties"
        prefix="app"
        prefixValues="true"
        encoding="UTF-8"/>

    <!-- Đọc toàn bộ ghi chú, bỏ dòng comment. -->
    <loadfile
        property="release.notes"
        srcFile="config/release-notes.txt"
        encoding="UTF-8">
        <filterchain>
            <striplinecomments>
                <comment value="#"/>
            </striplinecomments>
        </filterchain>
    </loadfile>

    <target name="show-config">
        <echo message="Application: ${app.name}"/>
        <echo message="Version: ${app.version}"/>
        <echo message="Environment: ${app.environment}"/>
        <echo message="Release notes: ${release.notes}"/>
    </target>

    <target name="update-build-metadata">
        <propertyfile
            file="config/build.properties"
            comment="Updated by Apache Ant">
            <entry key="build.number"
                   type="int"
                   operation="+"
                   value="1"
                   default="0"/>
            <entry key="last.build"
                   type="date"
                   value="now"
                   pattern="yyyy-MM-dd HH:mm:ss"/>
        </propertyfile>

        <!-- Nạp lại vào namespace riêng để đọc giá trị mới. -->
        <loadproperties
            srcFile="config/build.properties"
            prefix="stored"
            encoding="UTF-8"/>

        <echo message="New build number: ${stored.build.number}"/>
    </target>

</project>
~~~

### 6.3. Theo dõi dữ liệu qua từng bước

Khi chạy:

~~~bash
ant show-config
~~~

Ant nạp các property app.*, đọc toàn bộ release notes vào release.notes, sau đó target show-config sử dụng các giá trị này.

Khi chạy:

~~~bash
ant update-build-metadata
~~~

Ant thực hiện target cập nhật file. Nếu build.number ban đầu là 15, file được cập nhật thành 16; đồng thời last.build nhận thời điểm hiện tại. Task loadproperties bên trong target nạp các giá trị vừa ghi vào namespace stored.*, nhờ đó target có thể in số build mới.

Luồng dữ liệu:

~~~text
build.properties
      |
      | loadproperties (prefix=app)
      v
  app.name, app.version, app.environment
      |
      +------> show-config

release-notes.txt
      |
      | loadfile
      v
  release.notes
      |
      +------> show-config

build.properties
      |
      | propertyfile
      v
  Cập nhật build.number và last.build
      |
      | loadproperties (prefix=stored)
      v
  stored.build.number, stored.last.build
~~~

Trong quy trình thực tế, hãy cân nhắc thời điểm nạp cấu hình và thời điểm cập nhật file. Nếu nạp app.* ở cấp project trước khi chạy target cập nhật metadata, các property đó vẫn là ảnh chụp giá trị lúc nạp. Nếu target cần giá trị mới, hãy nạp lại vào namespace riêng sau khi ghi file.

## 7. Xử lý lỗi và encoding

### 7.1. File bắt buộc và file tùy chọn

Nếu file là đầu vào bắt buộc, nên để task thất bại khi không thể đọc file. Build thiếu cấu hình quan trọng có thể tạo artifact sai hoặc dùng giá trị mặc định ngoài ý muốn.

Nếu file là tùy chọn, có thể dùng failonerror="false" ở task hỗ trợ thuộc tính này:

~~~xml
<loadproperties
    srcFile="config/local.properties"
    prefix="local"
    failonerror="false"/>
~~~

Khi dùng chế độ bỏ qua lỗi, cần có giá trị mặc định hoặc logic khác để build vẫn hoạt động đúng nếu file không tồn tại. Không nên biến lỗi đọc cấu hình bắt buộc thành cảnh báo rồi tiếp tục một cách âm thầm.

### 7.2. Chọn encoding rõ ràng

Với file văn bản có tiếng Việt, hãy thống nhất UTF-8 giữa nơi tạo file và nơi đọc file:

~~~xml
<loadfile
    property="release.notes"
    srcFile="release-notes.txt"
    encoding="UTF-8"/>
~~~

Với file properties, hãy chú ý quy tắc encoding của Java Properties và phiên bản Ant. Định dạng truyền thống sử dụng ISO-8859-1 cùng escape Unicode; nếu chọn encoding khác thông qua thuộc tính được task hỗ trợ, cần đảm bảo file được ghi và đọc theo cùng encoding.

Khi dùng propertyfile, hãy xác định encoding đầu ra phù hợp với các công cụ sẽ đọc file ở những lần chạy sau. Một file được ghi theo encoding khác với cách task đọc có thể dẫn đến giá trị tiếng Việt bị sai ký tự.

### 7.3. Giá trị chứa nội dung nhiều dòng

loadfile có thể đưa nội dung nhiều dòng vào một property. Khi chuyển tiếp giá trị này sang task khác, hãy hiểu cách task đích xử lý ký tự xuống dòng. Ví dụ, echo có thể in nội dung nhiều dòng ra log hoặc ghi vào file.

Đối với nội dung lớn hoặc dữ liệu nhị phân, nên dùng các task thao tác trực tiếp trên file thay vì đưa toàn bộ nội dung vào một property.

## 8. Những nhầm lẫn thường gặp

### 8.1. Dùng loadfile để đọc từng khóa properties

loadfile tạo một property chứa nguyên nội dung file. Muốn mỗi khóa thành một property riêng, dùng loadproperties.

### 8.2. Dùng loadproperties để đọc file văn bản bất kỳ

loadproperties mong đợi định dạng Java Properties. Một file Markdown, release notes hoặc HTML không phải file properties hợp lệ cho mục đích này. Dùng loadfile nếu cần nội dung văn bản nguyên khối.

### 8.3. Nghĩ rằng propertyfile chỉ thay đổi property trong bộ nhớ

propertyfile cập nhật file trên hệ thống file. Nó không phải phép gán lại property trong project. Nếu cần dùng giá trị vừa ghi, hãy nạp lại bằng tên property mới.

### 8.4. Nghĩ rằng loadproperties có thể ghi đè property cũ

Property của Ant tuân theo first definition wins. Nạp lại cùng tên không phải cách đáng tin cậy để thay thế giá trị đã được đặt.

### 8.5. Nhầm prefix với prefixValues

prefix đổi tên các property được nạp. prefixValues điều chỉnh tên property reference bên trong giá trị. Hai thuộc tính này giải quyết hai vấn đề khác nhau.

### 8.6. Nghĩ rằng propertyfile bảo toàn nguyên trạng file

propertyfile đọc và ghi lại dữ liệu theo định dạng properties. Comment, thứ tự và cách trình bày ban đầu có thể thay đổi. Nếu cần bảo toàn format do con người biên soạn, hãy chọn công cụ chỉnh sửa văn bản phù hợp.

### 8.7. Bỏ qua encoding

Một file UTF-8 được đọc bằng encoding khác có thể làm hỏng tiếng Việt. Với file văn bản và cấu hình, hãy thống nhất encoding và khai báo rõ khi task hỗ trợ.

## 9. Cách chọn task phù hợp

| Nhu cầu | Task nên dùng | Kết quả |
|---|---|---|
| Đọc app.version, app.name, db.url từ file cấu hình. | loadproperties | Nhiều property riêng trong Ant. |
| Đưa toàn bộ ghi chú phát hành vào một property. | loadfile | Một property chứa văn bản nhiều dòng. |
| Tăng build.number trong file sau mỗi lần build. | propertyfile | File properties được cập nhật. |
| Đọc resource properties nằm trong classpath. | loadproperties với resource | Nhiều property được nạp từ resource. |
| Lọc bỏ dòng comment khi đọc văn bản. | loadfile với filterchain | Một property chứa nội dung đã lọc. |
| Cập nhật thời điểm build gần nhất. | propertyfile với entry kiểu date | Một giá trị ngày giờ được lưu trong file. |

Một quy trình cấu hình thường có ba giai đoạn:

1. Nạp các giá trị đầu vào bằng loadproperties và loadfile.
2. Sử dụng các property trong target và task của build.
3. Ghi các metadata cần duy trì giữa các lần chạy bằng propertyfile.

Không phải build nào cũng cần cả ba task. Hãy chọn task dựa trên cấu trúc dữ liệu và hướng dữ liệu cần xử lý.

## 10. Ghi nhớ

- **loadproperties** đọc file Java Properties và tạo nhiều property riêng trong Ant.
- **loadfile** đọc toàn bộ file văn bản vào một property duy nhất; nó không phân tích từng dòng thành cặp khóa/giá trị.
- **propertyfile** tạo hoặc cập nhật file properties để lưu giá trị lâu dài.
- **prefix** thêm tiền tố vào tên property; **prefixValues** điều chỉnh các tham chiếu property nằm trong giá trị.
- **filterchain** cho phép biến đổi nội dung trong lúc đọc bằng các task hỗ trợ.
- Property đã đặt không bị ghi đè theo cách thông thường; ghi file bằng propertyfile không tự cập nhật property cũ trong bộ nhớ.
- Hãy khai báo encoding rõ ràng và nhất quán, đặc biệt khi file chứa tiếng Việt.
- Chọn loadproperties cho cấu hình dạng khóa/giá trị, loadfile cho nội dung văn bản nguyên khối và propertyfile cho cập nhật cấu hình lưu trên đĩa.

Khi nắm rõ hướng dữ liệu và phạm vi tác động của từng task, bạn có thể tổ chức cấu hình Ant thành các file dễ quản lý, đọc dữ liệu có kiểm soát và lưu lại metadata giữa các lần build.


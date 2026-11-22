# Thứ tự classpath, JAR trùng lặp và xung đột phiên bản

Một ứng dụng Java có thể biên dịch thành công nhưng vẫn chạy sai hoặc phát sinh lỗi ngay khi khởi động nếu classpath chứa nhiều phiên bản của cùng một thư viện. Nguyên nhân thường không nằm ở một dòng mã Java riêng lẻ mà ở cách các file JAR được đưa vào classpath và thứ tự mà compiler hoặc class loader tìm kiếm chúng.

Trong Apache Ant, classpath thường được mô tả bằng kiểu dữ liệu `<path>` rồi truyền vào các task như `<javac>` và `<java>`. Khi nhiều JAR có cùng tên class, thứ tự các phần tử có thể quyết định phiên bản nào được sử dụng. Vì vậy, cần hiểu ba vấn đề liên quan với nhau: classpath dùng để làm gì, thứ tự tìm kiếm ảnh hưởng ra sao và cách phát hiện JAR trùng lặp hoặc không tương thích phiên bản.

## 1. Classpath là gì?

Classpath là danh sách các vị trí mà Java dùng để tìm lớp và tài nguyên cần thiết. Một phần tử classpath có thể là:

- Thư mục chứa các file `.class` đã biên dịch.
- Một file JAR chứa bytecode và tài nguyên.
- Một số dạng archive mà công cụ Java hỗ trợ.

Ví dụ một ứng dụng có cấu trúc:

```text
hello-ant/
├── build/
│   └── classes/
├── lib/
│   ├── logging-api.jar
│   └── json-parser.jar
└── src/
    └── main/java/
```

Khi biên dịch, `javac` cần tìm các class mà mã nguồn tham chiếu trong những thư viện ngoài. Khi chạy ứng dụng, JVM cũng cần tìm các class đó để nạp và thực thi. Nếu một thư viện không có trong classpath thích hợp, compiler có thể báo không tìm thấy package hoặc class; khi chạy, JVM có thể ném `ClassNotFoundException` hoặc `NoClassDefFoundError` tùy tình huống.

Classpath có thể được dùng ở nhiều giai đoạn, nhưng các classpath này không nhất thiết giống hệt nhau:

| Loại classpath | Mục đích | Ví dụ đầu vào |
|---|---|---|
| Compile classpath | Giúp compiler tìm class và API mà mã nguồn sử dụng | JAR thư viện, class đã biên dịch của module phụ thuộc |
| Runtime classpath | Giúp JVM tìm class khi ứng dụng chạy | Thư mục class của ứng dụng và các JAR runtime cần thiết |
| Test classpath | Cung cấp class ứng dụng cùng thư viện và framework kiểm thử | `build/classes`, `build/test-classes`, JUnit và dependency test |
| Ant task classpath | Giúp chính tiến trình Ant nạp task hoặc extension bổ sung | JAR chứa custom task, thư viện mà task đó cần |

Không nên nhầm classpath của ứng dụng với classpath dùng để nạp task cho Ant. Thêm một JAR vào nested `<classpath>` của task `javac` không tự động làm cho Ant nhận diện một task tùy chỉnh nằm trong JAR đó.

## 2. Thứ tự classpath ảnh hưởng như thế nào?

Trong classpath truyền thống của Java, các phần tử được tìm kiếm theo thứ tự xuất hiện. Khi cùng một class có mặt trong nhiều phần tử, class loader hoặc compiler thường sử dụng bản tìm thấy đầu tiên theo quy tắc tìm kiếm của môi trường đó.

Ví dụ, hai thư viện đều chứa class:

```text
com/example/client/ApiClient.class
```

Classpath được sắp xếp như sau:

```text
lib/client-v1.jar
lib/client-v2.jar
```

Nếu cả hai JAR đều cung cấp `com.example.client.ApiClient`, bản trong `client-v1.jar` thường được tìm thấy trước. Đổi thứ tự:

```text
lib/client-v2.jar
lib/client-v1.jar
```

có thể khiến bản trong `client-v2.jar` được chọn. Điều này áp dụng cho việc phân giải class trong classpath thông thường; cơ chế class loader cha-con, module system hoặc class loader tùy chỉnh có thể bổ sung quy tắc tìm kiếm riêng.

### 2.1. Ví dụ xung đột API

Giả sử:

- `client-v1.jar` có phương thức `connect(String)`.
- `client-v2.jar` có phương thức `connect(String)` và bổ sung `connect(URI)`.
- Mã nguồn ứng dụng gọi `connect(URI)`.

Nếu compile classpath đặt `client-v2.jar` trước, compiler nhìn thấy API mới và biên dịch thành công. Nhưng nếu runtime classpath lại đặt `client-v1.jar` trước, JVM có thể nạp class cũ. Khi mã đã biên dịch gọi phương thức chỉ tồn tại trong v2, chương trình có thể gặp `NoSuchMethodError`.

Đây là lý do compile classpath và runtime classpath cần thống nhất phiên bản thư viện. Chỉ kiểm tra việc biên dịch thành công là chưa đủ để bảo đảm ứng dụng có thể chạy.

### 2.2. Sơ đồ minh họa

```text
Compile classpath
  1. client-v2.jar  -> tìm thấy ApiClient mới
  2. client-v1.jar
          |
          v
  javac biên dịch lời gọi connect(URI)

Runtime classpath
  1. client-v1.jar  -> JVM nạp ApiClient cũ
  2. client-v2.jar
          |
          v
  lời gọi connect(URI) không tồn tại
          |
          v
  NoSuchMethodError
```

Sơ đồ cho thấy hai giai đoạn có thể chọn hai phiên bản khác nhau nếu cấu hình classpath không nhất quán.

## 3. JAR trùng lặp và các dạng xung đột

Không phải mọi trường hợp có nhiều file JAR đều là lỗi. Một ứng dụng bình thường có thể cần hàng chục hoặc hàng trăm thư viện khác nhau. Vấn đề xuất hiện khi nhiều phần tử classpath cung cấp cùng class, hoặc khi các thư viện được biên dịch để dùng với những phiên bản API không tương thích.

### 3.1. Trùng chính cùng một JAR

Ví dụ:

```text
lib/client.jar
lib/legacy/client.jar
```

Hai đường dẫn có thể trỏ đến cùng một bản sao hoặc hai bản sao giống hệt nhau. Việc đưa cả hai vào classpath thường không mang lại lợi ích; nó làm cấu hình khó hiểu và gây khó khăn khi điều tra nguồn gốc class được nạp.

### 3.2. Hai phiên bản khác nhau của cùng thư viện

Ví dụ:

```text
lib/http-client-4.x.jar
lib/http-client-5.x.jar
```

Hai phiên bản có thể có package, class hoặc chữ ký phương thức khác nhau. Nếu cả hai cùng xuất hiện, kết quả phụ thuộc vào class nào bị trùng và thứ tự tìm kiếm. Một module có thể cần API v4 trong khi module khác đã được biên dịch với API v5.

### 3.3. Hai thư viện khác tên nhưng chứa cùng class

Tên file không đủ để xác định xung đột. Hai JAR có thể mang tên khác nhưng cùng đóng gói một class, ví dụ thư viện được shade hoặc copy class vào một archive khác.

```text
lib/vendor-client.jar
lib/application-bundle.jar
```

Cả hai có thể chứa `com/vendor/Client.class`. Vì vậy, khi điều tra class trùng, cần kiểm tra nội dung JAR chứ không chỉ so sánh tên file.

### 3.4. Xung đột dependency bắc cầu

Một thư viện có thể phụ thuộc vào thư viện khác. Ví dụ:

```text
application
├── library-A -> common-utils 1.x
└── library-B -> common-utils 2.x
```

Nếu buildfile tự đưa cả `common-utils-1.x.jar` và `common-utils-2.x.jar` vào classpath, ứng dụng có thể gặp xung đột API. Ant core không tự giải quyết toàn bộ đồ thị dependency như một dependency manager chuyên dụng; người viết build phải quản lý những JAR được đưa vào path, hoặc kết hợp Ant với công cụ quản lý dependency phù hợp.

## 4. Khai báo classpath trong Ant bằng Path

Ant cung cấp kiểu dữ liệu `<path>` để gom nhiều thư mục và JAR thành một path có thể tái sử dụng. Ta thường khai báo `id` ở cấp project, sau đó truyền `refid` cho task cần classpath.

Ví dụ:

```xml
<path id="compile.classpath">
    <pathelement location="lib/client-v2.jar"/>
    <pathelement location="lib/json-parser.jar"/>
    <pathelement location="lib/logging-api.jar"/>
</path>

<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Các phần tử `<pathelement>` được khai báo theo thứ tự mong muốn. Khi cần kiểm soát thứ tự classpath, cách liệt kê từng JAR tường minh giúp người đọc biết chính xác thư viện nào được đặt trước.

### 4.1. Dùng property để quản lý vị trí thư viện

Có thể khai báo thư mục thư viện một lần:

```xml
<property name="lib.dir" location="lib"/>

<path id="compile.classpath">
    <pathelement location="${lib.dir}/client-v2.jar"/>
    <pathelement location="${lib.dir}/json-parser.jar"/>
    <pathelement location="${lib.dir}/logging-api.jar"/>
</path>
```

Nếu thư mục `lib` thay đổi, chỉ cần sửa property `lib.dir`. Các phần tử path sẽ được xây dựng từ giá trị đó.

### 4.2. Dùng FileSet để thêm nhiều JAR

Nếu muốn đưa tất cả JAR trong một thư mục vào classpath, có thể dùng FileSet bên trong Path:

```xml
<path id="all.libs.classpath">
    <fileset dir="lib" includes="*.jar"/>
</path>
```

Cách này thuận tiện khi thư mục chứa các thư viện độc lập, không có xung đột class và không cần kiểm soát thứ tự. Tuy nhiên, không nên dựa vào thứ tự file được FileSet quét để quyết định phiên bản nào thắng khi có class trùng lặp. Thứ tự duyệt file có thể phụ thuộc cách hệ thống file và scanner trả kết quả; nếu thứ tự có ý nghĩa, hãy liệt kê JAR tường minh bằng các phần tử `pathelement`.

### 4.3. Kết hợp phần tử tường minh và FileSet

Một path có thể kết hợp các phần tử:

```xml
<path id="compile.classpath">
    <!-- Đặt API được chọn lên trước. -->
    <pathelement location="lib/client-v2.jar"/>

    <!-- Thêm các thư viện plugin không xung đột. -->
    <fileset dir="lib/plugins" includes="*.jar"/>
    <pathelement location="lib/logging-api.jar"/>
</path>
```

Các phần tử của Path được kết hợp theo thứ tự khai báo, nhưng thứ tự nội bộ của FileSet không nên được dùng để giải quyết xung đột phiên bản. Hãy tách những thư viện có xung đột ra và khai báo chúng tường minh.

## 5. Tách compile classpath và runtime classpath

Một buildfile thường nên mô tả rõ hai classpath riêng:

- Compile classpath: các thư viện mà compiler cần để kiểm tra và biên dịch mã nguồn.
- Runtime classpath: các class và thư viện cần có khi JVM thực thi ứng dụng.

Ví dụ:

```xml
<path id="compile.classpath">
    <pathelement location="lib/client-v2.jar"/>
    <pathelement location="lib/json-parser.jar"/>
</path>

<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/client-v2.jar"/>
    <pathelement location="lib/json-parser.jar"/>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>

<target name="run" depends="compile">
    <java classname="com.example.Main" fork="true">
        <classpath refid="runtime.classpath"/>
    </java>
</target>
```

Trong ví dụ, compiler dùng hai JAR thư viện; khi chạy, JVM cần thêm `build/classes` để tìm class ứng dụng. Cả hai classpath dùng cùng phiên bản `client-v2.jar` và `json-parser.jar`, tránh tình trạng compile với một phiên bản rồi chạy với phiên bản khác.

### 5.1. Vai trò của includeantruntime

Task `<javac>` của Ant có thuộc tính `includeantruntime`. Khi bật, các thư viện runtime của chính Ant có thể được đưa vào classpath biên dịch. Với ứng dụng thông thường, nên đặt:

```xml
<javac includeantruntime="false" ...>
```

Điều này tránh việc mã nguồn vô tình phụ thuộc vào class chỉ có mặt vì Ant đang chạy. Nếu ứng dụng thực sự cần một thư viện nào đó, hãy khai báo thư viện đó trong classpath của dự án một cách tường minh.

### 5.2. Test classpath cũng cần nhất quán

Nếu có target kiểm thử, test classpath thường cần:

- Class đã biên dịch của ứng dụng.
- Class đã biên dịch của test.
- Framework test và các dependency cần thiết.
- Cùng phiên bản các thư viện mà ứng dụng dùng khi chạy.

Nếu test classpath nạp phiên bản mới của thư viện nhưng runtime production lại dùng phiên bản cũ, test có thể thành công trong khi ứng dụng triển khai thất bại. Vì vậy, nên dùng chung các định nghĩa path cho dependency chính và chỉ bổ sung thư viện test ở phần riêng.

## 6. Ví dụ xung đột phiên bản và cách khắc phục

Giả sử thư mục `lib` có:

```text
lib/
├── xml-core-1.8.jar
├── xml-core-2.1.jar
└── app-support.jar
```

Hai bản `xml-core` cùng chứa class `org.example.xml.Parser`. Nếu buildfile viết:

```xml
<path id="compile.classpath">
    <fileset dir="lib" includes="*.jar"/>
</path>
```

thì cả hai phiên bản có thể xuất hiện trong classpath. Ta không nên dựa vào thứ tự scanner để quyết định bản nào được sử dụng.

Nếu ứng dụng đã được nâng cấp để dùng API của phiên bản 2.1, hãy chọn một phiên bản duy nhất:

```xml
<path id="compile.classpath">
    <pathelement location="lib/xml-core-2.1.jar"/>
    <pathelement location="lib/app-support.jar"/>
</path>
```

Đồng thời loại `xml-core-1.8.jar` khỏi path thực tế của compile, test và runtime. Nếu `app-support.jar` chỉ tương thích với phiên bản 1.8, cần chọn lại phiên bản tương thích của `app-support` hoặc nâng cấp nó; chỉ đổi thứ tự classpath có thể che lỗi trong một số tình huống nhưng không giải quyết sự không tương thích.

### 6.1. Cùng một class nhưng khác chữ ký phương thức

Giả sử mã nguồn biên dịch với API 2.1:

```java
Parser parser = new Parser();
parser.parse(input, strictMode);
```

Nếu runtime lại nạp `Parser` từ phiên bản 1.8 không có phương thức `parse` với chữ ký tương ứng, JVM có thể ném `NoSuchMethodError` khi lời gọi được thực hiện.

Điều này là lỗi tương thích nhị phân: mã bytecode đã được biên dịch dựa trên một API, nhưng runtime cung cấp class không có thành viên mà bytecode yêu cầu.

### 6.2. Class trùng trong thư viện khác tên

Nếu hai JAR khác tên cùng chứa một class, hãy xác định class nào đang được nạp và JAR nào là nguồn dự kiến. Có thể dùng `jar tf` để liệt kê nội dung từng JAR:

```bash
jar tf lib/vendor-client.jar
jar tf lib/application-bundle.jar
```

Tìm đường dẫn class, ví dụ `com/vendor/Client.class`. Nếu class xuất hiện ở cả hai archive, cần xác định liệu đó có phải bản đóng gói có chủ ý hay một bản copy không cần thiết.

## 7. Những lỗi runtime thường liên quan đến classpath

| Lỗi | Ý nghĩa thường gặp | Điều cần kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Một thao tác nạp class theo tên không tìm thấy class | Runtime classpath, tên class và class loader được dùng |
| `NoClassDefFoundError` | JVM không thể dùng một class cần thiết trong lúc liên kết hoặc thực thi; có thể class thiếu hoặc khởi tạo class trước đó thất bại | Dependency runtime, lỗi khởi tạo trước đó và log gốc |
| `NoSuchMethodError` | Class được nạp không có phương thức mà bytecode đang gọi | Phiên bản JAR runtime so với phiên bản dùng lúc compile |
| `NoSuchFieldError` | Class được nạp không có field mà bytecode yêu cầu | JAR trùng class hoặc API không tương thích |
| `AbstractMethodError` | Class thực tế không cung cấp implementation tương thích cho phương thức cần gọi | Các phiên bản interface và implementation |
| `ClassCastException` | Hai kiểu không tương thích khi ép kiểu; có thể liên quan đến cùng tên class do class loader khác nhau định nghĩa | Nguồn class, class loader và ranh giới module/plugin |
| `UnsupportedClassVersionError` | JVM hiện tại không hỗ trợ phiên bản bytecode của class | JDK dùng để chạy ứng dụng so với JDK dùng để biên dịch |

Những lỗi này không phải lúc nào cũng do thứ tự classpath. Ví dụ, `ClassNotFoundException` cũng có thể do thiếu JAR hoàn toàn; `UnsupportedClassVersionError` thường liên quan đến phiên bản bytecode. Tuy nhiên, classpath và phiên bản thư viện là những điểm cần kiểm tra sớm khi lỗi chỉ xuất hiện trên một môi trường.

## 8. Kiểm tra classpath thực tế mà Ant tạo ra

Khi buildfile có nhiều path được ghép từ property, FileSet và các file khác, classpath cuối cùng có thể khó nhìn bằng mắt. Ant có task `pathconvert` để chuyển Path thành một chuỗi có thể in ra log.

Ví dụ:

```xml
<path id="compile.classpath">
    <pathelement location="lib/client-v2.jar"/>
    <pathelement location="lib/json-parser.jar"/>
    <pathelement location="lib/logging-api.jar"/>
</path>

<pathconvert property="compile.classpath.text" refid="compile.classpath"/>

<target name="show-classpath">
    <echo message="Compile classpath: ${compile.classpath.text}"/>
</target>
```

Chạy:

```bash
ant show-classpath
```

Thông báo giúp kiểm tra các đường dẫn đã được Ant phân giải và thứ tự các phần tử trong Path. Khi classpath được tạo động, đây là cách hữu ích để xác định một JAR có thực sự được đưa vào hay không.

Có thể tăng mức log của Ant khi điều tra:

```bash
ant -verbose compile
ant -debug compile
```

Log chi tiết giúp quan sát hoạt động của task và các lệnh compiler được gọi. Tùy phiên bản Ant và compiler adapter, cách hiển thị classpath có thể khác nhau.

## 9. Tìm class thực sự được nạp từ JAR nào

Khi nghi ngờ runtime đang chọn sai JAR, cần biết class được nạp từ vị trí nào. Với Java, có thể bật log class loading.

Trên JDK 8, tùy chọn thường dùng là `-verbose:class`. Ví dụ trên Windows:

```powershell
java -verbose:class -cp "build/classes;lib/*" com.example.Main
```

Trên Linux và macOS, dùng dấu hai chấm làm ký tự phân cách classpath:

```bash
java -verbose:class -cp "build/classes:lib/*" com.example.Main
```

Trên JDK 9 trở lên, có thể dùng unified logging. Ví dụ trên Windows:

```powershell
java -Xlog:class+load=info -cp "build/classes;lib/*" com.example.Main
```

Và trên Linux/macOS:

```bash
java -Xlog:class+load=info -cp "build/classes:lib/*" com.example.Main
```

Ký tự phân cách classpath khác nhau theo hệ điều hành: Windows thường dùng dấu chấm phẩy `;`, Linux và macOS dùng dấu hai chấm `:`. Trong script Ant, nên để Ant tạo classpath từ Path thay vì tự nối chuỗi bằng dấu phân cách cố định.

Nếu chạy qua task `<java>`, có thể truyền tùy chọn JVM:

```xml
<java classname="com.example.Main" fork="true">
    <jvmarg value="-Xlog:class+load=info"/>
    <classpath refid="runtime.classpath"/>
</java>
```

Tùy chọn `-Xlog:class+load=info` dành cho các JDK hỗ trợ unified logging. Nếu ứng dụng chạy trên JDK 8, dùng tùy chọn phù hợp với phiên bản đó.

Khi xem log, tìm tên đầy đủ của class đáng ngờ và kiểm tra nguồn archive hoặc thư mục mà JVM báo đã nạp. Nếu class đến từ một JAR cũ ngoài dự kiến, hãy lần ngược cấu hình runtime classpath và class loader liên quan.

## 10. Kiểm tra nội dung và phiên bản JAR

Tên file JAR có thể chứa số phiên bản nhưng không phải lúc nào cũng đáng tin cậy. File có thể được đổi tên, copy hoặc đóng gói lại. Nên kết hợp nhiều cách kiểm tra.

### 10.1. Liệt kê class trong JAR

```bash
jar tf lib/client-v2.jar
```

Lệnh `jar tf` liệt kê nội dung archive. Có thể tìm một class cụ thể bằng công cụ lọc của shell:

```bash
# Linux/macOS
jar tf lib/client-v2.jar | grep 'com/example/ApiClient.class'
```

```powershell
# Windows PowerShell
jar tf lib/client-v2.jar | Select-String 'com/example/ApiClient.class'
```

### 10.2. Xem API mà compiler nhìn thấy

`javap` có thể hiển thị chữ ký class từ một classpath được chỉ định:

```bash
javap -classpath lib/client-v2.jar com.example.client.ApiClient
```

Kết quả cho biết những constructor, method và field mà JAR đó cung cấp. Khi có nhiều JAR trùng class, hãy kiểm tra từng JAR riêng và kiểm tra lại classpath theo đúng thứ tự thực tế.

### 10.3. Kiểm tra metadata và checksum

Một số JAR chứa metadata trong `META-INF`, manifest hoặc thư mục metadata của thư viện. Có thể xem:

```bash
jar tf lib/client-v2.jar
```

và giải nén hoặc đọc `META-INF/MANIFEST.MF` khi cần. Tuy nhiên, manifest không phải lúc nào cũng ghi phiên bản thư viện đáng tin cậy. Để xác định hai file có giống hệt nhau hay không, có thể so sánh checksum:

```bash
# Linux
sha256sum lib/client-v1.jar lib/client-v2.jar
```

```powershell
# Windows PowerShell
Get-FileHash .\lib\client-v1.jar -Algorithm SHA256
Get-FileHash .\lib\client-v2.jar -Algorithm SHA256
```

Checksum giống nhau là bằng chứng mạnh cho thấy nội dung file giống hệt; checksum khác nhau không nhất thiết chứng minh hai JAR chứa class khác nhau, vì metadata hoặc thứ tự entry cũng có thể khác.

## 11. Cách xử lý xung đột phiên bản

Khi phát hiện nhiều JAR chứa cùng class, hãy xử lý từ nguồn dependency và cấu hình path:

1. Xác định class nào bị trùng và các JAR chứa class đó.
2. Xác định phiên bản thư viện mà mã nguồn và các module thực sự cần.
3. Chọn một phiên bản tương thích làm phiên bản chuẩn.
4. Loại phiên bản cũ hoặc không cần thiết khỏi compile, test và runtime classpath.
5. Kiểm tra các thư viện phụ thuộc vào phiên bản được chọn.
6. Chạy lại build và test; sau đó chạy ứng dụng với log class loading nếu cần xác nhận nguồn class.

Không nên chỉ đảo thứ tự JAR để làm lỗi biến mất rồi dừng điều tra. Việc đảo thứ tự có thể khiến class cũ bị che đi, nhưng các thư viện khác vẫn có thể được biên dịch với API không tương thích. Cần làm cho toàn bộ đồ thị dependency dùng các phiên bản có thể làm việc cùng nhau.

### 11.1. Dùng một property để chọn phiên bản

Nếu dự án quản lý phiên bản thư viện thủ công, có thể dùng property để tránh lặp tên phiên bản:

```xml
<property name="client.version" value="2.1.0"/>
<property name="client.jar" location="lib/client-${client.version}.jar"/>

<path id="application.classpath">
    <pathelement location="${client.jar}"/>
    <pathelement location="lib/json-parser.jar"/>
</path>
```

Khi cần nâng cấp, thay `client.version` và kiểm tra các dependency liên quan. Cách này làm rõ phiên bản được chọn trong buildfile.

### 11.2. Tránh đưa toàn bộ thư mục lib vào path một cách thiếu kiểm soát

Một cấu hình tiện lợi như:

```xml
<fileset dir="lib" includes="*.jar"/>
```

có thể vô tình đưa cả bản cũ và bản mới vào classpath nếu thư mục còn lưu file từ lần nâng cấp trước. Khi thư viện có xung đột, hãy dọn cấu hình và chỉ đưa những JAR cần thiết vào path. Nếu vẫn dùng wildcard để thêm nhóm thư viện, cần bảo đảm thư mục đó chỉ chứa các phiên bản hợp lệ và không có class trùng ngoài ý muốn.

## 12. Phân biệt classpath ứng dụng và thư viện của Ant

Ant là một chương trình Java, vì vậy bản thân tiến trình Ant cũng có classpath để nạp core và các task. Classpath này khác với classpath mà buildfile truyền cho ứng dụng.

Một số cách cung cấp thư viện cho Ant:

- Đặt JAR extension hoặc task phù hợp vào thư mục thư viện của Ant theo hướng dẫn của task.
- Dùng tùy chọn `-lib` khi khởi động Ant để bổ sung thư viện cho Ant.
- Dùng `taskdef` hoặc `typedef` với classpath phù hợp để nạp task hoặc type tùy chỉnh.

Ví dụ minh họa:

```bash
ant -lib tools/ant-tasks/custom-task.jar verify
```

Tùy chọn `-lib` bổ sung thư viện vào môi trường Ant. Nó không thay thế việc khai báo dependency runtime cho ứng dụng. Nếu ứng dụng cần `custom-task.jar` khi chạy, vẫn phải đưa nó vào runtime classpath của ứng dụng theo đúng nhu cầu.

## 13. Nguyên tắc tổ chức classpath dễ bảo trì

- Khai báo Path có `id` để tái sử dụng giữa các target.
- Liệt kê tường minh những JAR có nguy cơ chứa class trùng hoặc có yêu cầu thứ tự.
- Dùng FileSet wildcard cho nhóm thư viện độc lập, không phụ thuộc vào thứ tự tìm kiếm.
- Tránh để nhiều phiên bản của cùng thư viện cùng nằm trong classpath.
- Giữ compile, test và runtime classpath nhất quán về phiên bản dependency chính.
- Đặt `includeantruntime="false"` cho `javac` nếu ứng dụng không cần classpath runtime của Ant.
- Kiểm tra classpath thực tế bằng `pathconvert`, log Ant và log class loading khi cần.
- Xác minh nội dung JAR thay vì chỉ dựa vào tên file.
- Ghi rõ lý do nếu thứ tự classpath đặc biệt là một phần có chủ ý của cấu hình.
- Không coi việc đổi thứ tự là cách sửa lâu dài cho một dependency không tương thích.

## 14. Kết luận

Classpath xác định nơi compiler và JVM tìm class, còn thứ tự các phần tử quyết định class nào có thể được chọn trước khi nhiều JAR cung cấp cùng một tên class. JAR trùng lặp, nhiều phiên bản của cùng thư viện và dependency bắc cầu không tương thích có thể khiến build biên dịch thành công nhưng ứng dụng lỗi khi chạy.

Trong Ant, hãy dùng `<path>` để mô tả classpath có thể tái sử dụng, dùng `<pathelement>` để kiểm soát thứ tự rõ ràng và tách compile classpath khỏi runtime classpath khi mục đích khác nhau. Khi phát hiện lỗi, hãy xác định nguồn class thực tế, kiểm tra nội dung JAR và thống nhất phiên bản dependency trên các giai đoạn build, test và chạy ứng dụng. Cách quản lý này giúp giảm xung đột và làm cho kết quả build nhất quán giữa máy phát triển và môi trường CI.

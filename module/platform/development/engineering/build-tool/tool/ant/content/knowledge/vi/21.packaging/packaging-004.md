# Kiểm soát trùng lặp, cập nhật và nội dung đầu vào của JAR

Apache Ant dùng task **jar** để đóng gói class đã biên dịch, tài nguyên và metadata thành một tệp JAR. Một JAR có thể lấy dữ liệu từ nhiều thư mục hoặc từ các archive khác nhau. Vì vậy, người viết build file cần kiểm soát ba việc: những resource nào được đưa vào, điều gì xảy ra khi nhiều nguồn có cùng đường dẫn bên trong JAR, và cách xử lý khi tệp JAR đích đã tồn tại.

Ba thuộc tính quan trọng của task Jar là:

- **duplicate** quyết định cách xử lý khi nhiều nguồn cùng tạo một entry có cùng tên trong archive.
- **update** quyết định cách Ant cập nhật archive đã tồn tại.
- **includes/excludes**, FileSet, ZipFileSet và các resource collection quyết định nội dung đầu vào và đường dẫn của từng entry.

Nếu không cấu hình rõ, JAR có thể chứa entry trùng lặp, còn sót class hoặc resource cũ, hoặc đưa cả tệp không cần thiết vào artifact. Bài này giải thích cách kiểm soát các trường hợp đó trong một quy trình build có thể lặp lại.

## 1. JAR là archive gồm các entry có đường dẫn

JAR dựa trên định dạng ZIP. Bên trong JAR, mỗi tệp được lưu thành một entry với đường dẫn tương đối, ví dụ:

~~~text
inventory.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       ├── App.class
│       └── service/
│           └── InventoryService.class
└── config/
    └── application.properties
~~~

Đường dẫn entry quan trọng vì Java tìm class theo tên đầy đủ của nó. Ví dụ lớp **com.example.App** cần xuất hiện trong JAR tại đường dẫn:

~~~text
com/example/App.class
~~~

Tương tự, resource có thể được đọc theo đường dẫn tương đối như **config/application.properties**.

Task **jar** tạo archive từ các tệp và thư mục đã chọn:

~~~xml
<jar destfile="build/inventory.jar"
     basedir="build/classes"/>
~~~

**destfile** là JAR đầu ra. **basedir** là thư mục gốc của dữ liệu đầu vào; đường dẫn tương đối bên dưới thư mục này được giữ làm đường dẫn entry trong JAR.

Nếu build/classes có **com/example/App.class**, entry trong JAR sẽ là **com/example/App.class**, không phải **build/classes/com/example/App.class**.

Nếu không khai báo manifest, Ant tự cung cấp một manifest đơn giản. Có thể khai báo manifest riêng để đặt Main-Class, phiên bản ứng dụng và các metadata khác.

## 2. Kiểm soát nội dung đầu vào bằng include và exclude

Khi dùng thuộc tính **basedir**, Jar tạo một FileSet ngầm định. Có thể giới hạn dữ liệu bằng **includes**, **excludes**, **includesfile**, **excludesfile** hoặc các phần tử lồng **include** và **exclude**.

Ví dụ chỉ đóng gói class của ứng dụng và bỏ qua test class:

~~~xml
<jar destfile="build/inventory.jar"
     basedir="build/classes"
     includes="**/*.class"
     excludes="**/*Test.class"/>
~~~

Một cách dễ đọc hơn khi có nhiều quy tắc:

~~~xml
<jar destfile="build/inventory.jar"
     basedir="build/classes">
    <include name="com/example/**"/>
    <exclude name="**/*Test.class"/>
    <exclude name="**/internal/debug/**"/>
</jar>
~~~

Các mẫu được so khớp với đường dẫn tương đối từ thư mục gốc. Những đường dẫn khớp include mới được chọn; các đường dẫn khớp exclude bị loại khỏi tập đầu vào.

Nếu bỏ qua include, mặc định mọi tệp phù hợp trong phạm vi FileSet đều có thể được chọn. Vì vậy, với thư mục build chứa cả class thử nghiệm, log hoặc tệp tạm, nên khai báo phạm vi đóng gói rõ ràng.

### Chọn nhiều loại đầu vào

Một ứng dụng thường cần cả class và resource. Có thể thêm nhiều FileSet vào cùng một JAR:

~~~xml
<jar destfile="build/inventory.jar">
    <fileset dir="build/classes">
        <include name="**/*.class"/>
        <exclude name="**/*Test.class"/>
    </fileset>

    <fileset dir="src/main/resources">
        <include name="**/*"/>
        <exclude name="local/**"/>
    </fileset>
</jar>
~~~

Ant giữ đường dẫn tương đối của mỗi FileSet. Ví dụ **build/classes/com/example/App.class** và **src/main/resources/config/app.properties** sẽ trở thành:

~~~text
com/example/App.class
config/app.properties
~~~

Các FileSet có thể hợp nhất nhiều cây thư mục thành một cây entry duy nhất. Vì vậy, hai FileSet khác nhau có thể tạo ra cùng một đường dẫn bên trong JAR. Trường hợp này dẫn tới vấn đề duplicate được giải thích ở phần sau.

### Default excludes

Task Jar hỗ trợ **defaultexcludes**, mặc định là **yes**. Các mẫu loại trừ mặc định giúp bỏ qua một số metadata hoặc tệp quản lý phiên bản phổ biến như thư mục CVS, .git và các tệp tạm thuộc nhóm default excludes của Ant.

Không nên dựa hoàn toàn vào default excludes để kiểm soát nội dung phát hành. Nếu dự án có tệp cấu hình cục bộ, credential, log hoặc dữ liệu test, hãy thêm exclude cụ thể theo cấu trúc repository.

## 3. Đổi đường dẫn entry bằng zipfileset

FileSet giữ đường dẫn tương đối theo thư mục gốc. Khi cần đặt resource vào một vị trí khác trong JAR, dùng **zipfileset**.

Ví dụ đưa tệp cấu hình vào thư mục **config**:

~~~xml
<jar destfile="build/inventory.jar">
    <fileset dir="build/classes"/>

    <zipfileset dir="src/main/config"
                prefix="config"/>
</jar>
~~~

Nếu thư mục nguồn có **database.properties**, entry trong JAR sẽ là **config/database.properties**.

ZipFileSet còn có thể đọc nội dung từ một archive khác thông qua thuộc tính **src**:

~~~xml
<jar destfile="build/inventory-all.jar">
    <fileset dir="build/classes"/>

    <zipfileset src="lib/shared-resources.jar"
                includes="**/*.properties"
                prefix="shared"/>
</jar>
~~~

Các tệp properties trong archive nguồn được thêm dưới tiền tố **shared/**. Đây là cách chọn một phần nội dung của archive khác thay vì giải nén thủ công trước khi đóng gói.

Thuộc tính **fullpath** của ZipFileSet có thể đặt một resource đơn vào đúng đường dẫn chỉ định trong archive. Thuộc tính **prefix** phù hợp khi muốn thêm một thư mục gốc cho nhiều resource. Không dùng fullpath cho một tập gồm nhiều tệp vì nhiều resource không thể cùng chiếm một đường dẫn duy nhất.

## 4. Gộp nội dung từ nhiều JAR

Task Jar hỗ trợ đưa nội dung từ các archive khác vào JAR mới. Có thể dùng ZipFileSet với **src** cho từng archive:

~~~xml
<jar destfile="build/application-all.jar">
    <fileset dir="build/classes"/>

    <zipfileset src="lib/common.jar"/>
    <zipfileset src="lib/validation.jar"/>
</jar>
~~~

Hoặc dùng **zipgroupfileset** để chọn nhiều archive theo FileSet:

~~~xml
<jar destfile="build/application-all.jar">
    <fileset dir="build/classes"/>

    <zipgroupfileset dir="lib">
        <include name="*.jar"/>
    </zipgroupfileset>
</jar>
~~~

Cách gộp này thường được dùng để tạo một JAR chứa class của ứng dụng cùng class của một số thư viện. Tuy nhiên, hai thư viện có thể cùng chứa một entry như **META-INF/services/...**, **com/example/Version.class** hoặc một resource có tên giống nhau.

Gộp archive không tự giải quyết xung đột nội dung. Cần quyết định chính sách duplicate, xử lý manifest và service descriptor phù hợp với loại thư viện được đưa vào.

## 5. Hiểu ba chính sách duplicate

Định dạng ZIP cho phép một archive có nhiều entry cùng tên đầy đủ. Điều này có thể gây vấn đề khi một JAR chứa hai class hoặc resource có cùng đường dẫn.

Thuộc tính **duplicate** của Jar quyết định cách xử lý khi một entry trùng tên được thêm vào:

| Giá trị | Hành vi |
|---|---|
| **add** | Thêm cả entry trùng lặp; đây là mặc định |
| **preserve** | Giữ entry đầu tiên tìm thấy và bỏ qua các bản trùng sau |
| **fail** | Dừng build khi phát hiện entry trùng lặp |

### add: giữ tất cả entry

~~~xml
<jar destfile="build/application.jar"
     duplicate="add">
    <fileset dir="build/classes"/>
    <fileset dir="src/main/resources"/>
</jar>
~~~

Với **add**, Ant giữ các entry trùng tên trong archive. Đây là hành vi mặc định, nhưng thường không phù hợp với class hoặc resource cần có một bản duy nhất.

Ví dụ, cả hai nguồn đều chứa **config/application.properties**. JAR có thể có hai entry cùng đường dẫn. Các công cụ đọc archive hoặc classloader có thể xử lý tình huống này khác nhau; không nên dựa vào việc entry nào sẽ được chọn.

### preserve: giữ bản đầu tiên

~~~xml
<jar destfile="build/application.jar"
     duplicate="preserve">
    <fileset dir="build/classes"/>
    <fileset dir="src/main/resources"/>
</jar>
~~~

Với **preserve**, entry đầu tiên được thêm vào sẽ được giữ lại. Entry trùng xuất hiện sau bị bỏ qua.

Thứ tự khai báo resource collection vì vậy trở nên quan trọng. Nếu FileSet class được khai báo trước resource, bản trong class tree có thể thắng bản trong resource tree. Tuy nhiên, đây là quyết định dựa trên thứ tự đầu vào; thay đổi thứ tự FileSet có thể làm nội dung cuối cùng thay đổi.

Dùng preserve chỉ khi thứ tự ưu tiên đã được thiết kế rõ và có lý do để chọn bản đầu tiên.

### fail: coi duplicate là lỗi đóng gói

~~~xml
<jar destfile="build/application.jar"
     duplicate="fail">
    <fileset dir="build/classes"/>
    <fileset dir="src/main/resources"/>
</jar>
~~~

Với **fail**, Ant báo lỗi và dừng build khi phát hiện entry trùng. Đây là lựa chọn hữu ích cho artifact phát hành vì xung đột được phát hiện ngay trong bước đóng gói.

Thay vì âm thầm giữ một bản hoặc đưa nhiều bản vào JAR, build buộc người phát triển xử lý nguồn xung đột: đổi tên resource, loại một bản bằng exclude, hoặc hợp nhất nội dung theo định dạng phù hợp.

### Ví dụ xung đột thực tế

Giả sử:

~~~text
build/classes/
└── com/example/
    └── Version.class

src/main/resources/
└── com/example/
    └── Version.class
~~~

Hai FileSet cùng tạo entry **com/example/Version.class**. Đây thường là lỗi tổ chức đầu vào: resource tree không nên cung cấp một class file cùng đường dẫn với class đã biên dịch. Đặt **duplicate="fail"** giúp phát hiện lỗi thay vì tạo archive khó dự đoán.

Với service descriptor tại **META-INF/services/**, nhiều thư viện đôi khi cần đóng góp các provider khác nhau cho cùng một service. Trong trường hợp đó, chỉ đặt preserve hoặc add có thể không đủ: cần hợp nhất nội dung service descriptor theo đúng định dạng, hoặc dùng phần tử **service** của task Jar để khai báo provider rõ ràng.

## 6. Cập nhật JAR đã tồn tại bằng update

Thuộc tính **update** quyết định cách task xử lý khi tệp JAR đích đã tồn tại:

~~~xml
<jar destfile="build/inventory.jar"
     basedir="build/classes"
     update="true"/>
~~~

Khi **update="true"**, Ant cập nhật archive hiện có bằng các resource đã chỉ định: entry mới được thêm, entry cũ được thay bằng phiên bản mới khi đầu vào cần cập nhật.

Khi **update="false"** (mặc định), Ant tạo lại archive thay vì cập nhật từng entry theo chế độ update. Nếu archive tồn tại, task chỉ cần ghi lại khi phát hiện resource đầu vào mới hơn entry tương ứng; nếu không có gì cần cập nhật, archive có thể được xem là up-to-date.

### So sánh update true và false

| Cấu hình | Cách xử lý archive đã tồn tại |
|---|---|
| **update="false"** | Chế độ mặc định; khi đầu vào cần cập nhật, Ant tạo lại archive từ tập resource được chọn |
| **update="true"** | Cập nhật archive hiện tại; thêm entry mới và thay entry bằng phiên bản mới khi phù hợp |

Update là kiểm tra theo timestamp của resource và entry trong archive, không phải so sánh toàn bộ nội dung byte. ZIP lưu thời gian sửa đổi với độ chính xác 2 giây; nếu tệp nguồn chỉ mới hơn entry chưa đến 2 giây, Ant có thể không xem nó là mới hơn.

Do đó, không nên dùng update như một cơ chế phát hiện mọi thay đổi nội dung. Nếu công cụ khác thay đổi byte nhưng giữ nguyên timestamp, hoặc timestamp không đủ độ phân giải, Ant có thể không nhận ra thay đổi.

### Update không tự xóa entry không còn trong đầu vào

Giả sử lần đầu JAR có:

~~~text
com/example/App.class
com/example/OldFeature.class
config/app.properties
~~~

Sau đó, tệp **OldFeature.class** bị xóa khỏi thư mục build/classes. Nếu dùng **update="true"**, Ant thêm hoặc thay các resource đầu vào đã chọn; nó không dùng danh sách đầu vào mới để tự dọn mọi entry cũ không còn nguồn tương ứng.

Kết quả có thể vẫn chứa **com/example/OldFeature.class**. Đây là điểm quan trọng khi một class hoặc resource đã bị xóa hoặc đổi tên.

Nếu cần JAR phản ánh chính xác tập đầu vào hiện tại, hãy xóa JAR cũ trước khi tạo lại hoặc dọn thư mục dist trong target clean:

~~~xml
<target name="package">
    <mkdir dir="dist"/>
    <delete file="dist/inventory.jar"/>

    <jar destfile="dist/inventory.jar"
         duplicate="fail">
        <fileset dir="build/classes"/>
        <fileset dir="src/main/resources"/>
    </jar>
</target>
~~~

Việc xóa archive trước buộc Ant tạo một JAR mới từ các resource đang tồn tại. Đây là cách dễ hiểu để loại bỏ entry đã bị xóa khỏi cây nguồn.

Ngay cả với update mặc định, nếu chỉ một tệp nguồn bị xóa mà các resource còn lại không mới hơn entry trong JAR, task có thể không có lý do timestamp để tạo lại archive. Vì vậy, nếu tính đầy đủ của danh sách entry quan trọng, hãy dọn JAR cũ trước khi đóng gói.

## 7. Chọn hành vi khi không có đầu vào

Task Jar có thuộc tính **whenmanifestonly** để xử lý trường hợp không có resource nào khớp ngoài manifest hoặc service:

| Giá trị | Hành vi |
|---|---|
| **create** | Tạo JAR chỉ có manifest/services; đây là mặc định |
| **skip** | Không tạo JAR và ghi cảnh báo |
| **fail** | Không tạo JAR và làm build thất bại |

Ví dụ, nếu JAR phải luôn chứa class ứng dụng:

~~~xml
<jar destfile="dist/inventory.jar"
     whenmanifestonly="fail"
     duplicate="fail">
    <fileset dir="build/classes">
        <include name="**/*.class"/>
    </fileset>
</jar>
~~~

Nếu không có class nào phù hợp, build thất bại thay vì tạo một JAR chỉ có manifest.

Cần phân biệt **whenmanifestonly** của Jar với **whenempty** của Zip. Jar có manifest mặc định nên tình huống “chỉ còn manifest” có ý nghĩa riêng. Dùng đúng thuộc tính theo task đang gọi.

## 8. Kiểm soát manifest và metadata

Manifest nằm tại **META-INF/MANIFEST.MF**. Nếu không chỉ định manifest, Ant tự tạo một manifest đơn giản. Với ứng dụng chạy trực tiếp bằng:

~~~bash
java -jar dist/inventory.jar
~~~

manifest cần có thuộc tính **Main-Class**:

~~~xml
<jar destfile="dist/inventory.jar"
     duplicate="fail">
    <fileset dir="build/classes"/>
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.App"/>
        <attribute name="Implementation-Title"
                   value="Inventory"/>
        <attribute name="Implementation-Version"
                   value="1.4.0"/>
    </manifest>
</jar>
~~~

Có thể dùng manifest ngoài:

~~~xml
<jar destfile="dist/inventory.jar"
     manifest="config/MANIFEST.MF">
    <fileset dir="build/classes"/>
</jar>
~~~

Nếu vừa có manifest ngoài vừa có manifest lồng trong build file, Ant sẽ hợp nhất các khai báo theo quy tắc của task Jar. Cần tránh khai báo cùng thuộc tính theo các giá trị mâu thuẫn.

### Manifest nằm trong archive nguồn

Khi gộp một JAR khác bằng ZipFileSet hoặc ZipGroupFileSet, archive nguồn có thể chứa **META-INF/MANIFEST.MF**. Thuộc tính **filesetmanifest** điều khiển việc xử lý manifest được tìm thấy trong các archive đó:

- **skip**: bỏ qua manifest của archive nguồn; đây là mặc định.
- **merge**: hợp nhất các manifest nguồn và manifest được khai báo cho JAR đích.
- **mergewithoutmain**: hợp nhất các phần manifest ngoài Main section.

Ví dụ:

~~~xml
<jar destfile="dist/application-all.jar"
     duplicate="fail"
     filesetmanifest="mergewithoutmain">
    <fileset dir="build/classes"/>
    <zipfileset src="lib/common.jar"/>
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.App"/>
    </manifest>
</jar>
~~~

Việc merge manifest cần được thiết kế có chủ đích. Nhiều thư viện có thể khai báo Class-Path hoặc thuộc tính khác nhau; merge không tự bảo đảm mọi giá trị đều có ý nghĩa trong JAR cuối cùng. Với ứng dụng đơn giản, để mặc định skip manifest từ archive nguồn thường dễ kiểm soát hơn.

### Đưa tài nguyên vào META-INF

Dùng phần tử **metainf** khi muốn thêm tệp vào thư mục META-INF:

~~~xml
<jar destfile="dist/inventory.jar">
    <fileset dir="build/classes"/>

    <metainf dir="src/main/jar-meta">
        <include name="*.SF"/>
        <include name="*.txt"/>
    </metainf>
</jar>
~~~

Các tệp trong FileSet lồng metainf được đặt dưới **META-INF/**. Nếu FileSet chứa một tệp MANIFEST.MF, task sẽ bỏ qua tệp đó và cảnh báo; hãy dùng thuộc tính hoặc phần tử manifest để cấu hình manifest chính.

## 9. Service provider và resource cần hợp nhất

Java Service Provider Interface (SPI) sử dụng các tệp dưới **META-INF/services/**. Mỗi tệp có tên là tên interface/service và nội dung liệt kê class provider.

Ví dụ một service:

~~~text
META-INF/services/com.example.PaymentProvider
~~~

Nội dung:

~~~text
com.example.card.CardPaymentProvider
~~~

Task Jar có phần tử **service** để khai báo provider:

~~~xml
<jar destfile="dist/payment-app.jar">
    <fileset dir="build/classes"/>

    <service type="com.example.PaymentProvider"
             provider="com.example.card.CardPaymentProvider"/>
</jar>
~~~

Có thể khai báo nhiều provider:

~~~xml
<service type="com.example.PaymentProvider">
    <provider classname="com.example.card.CardPaymentProvider"/>
    <provider classname="com.example.wallet.WalletPaymentProvider"/>
</service>
~~~

Cách này giúp task tạo service descriptor theo định dạng mà Java sử dụng. Nếu nhiều dependency JAR có cùng một service descriptor, không nên chỉ dựa vào duplicate="add" hoặc preserve để mong Ant tự nối danh sách provider. Hãy hợp nhất nội dung service descriptor theo quy tắc của SPI hoặc khai báo các provider bằng phần tử service.

## 10. Ví dụ build.xml hoàn chỉnh

Ví dụ sau tạo JAR ứng dụng từ class và resource, kiểm soát duplicate, loại test/local config, cung cấp manifest và yêu cầu build thất bại nếu không có class đầu vào.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="package" basedir=".">

    <property name="classes.dir" location="build/classes"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="dist.dir" location="dist"/>
    <property name="jar.file" location="dist/inventory.jar"/>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="prepare">
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="package" depends="prepare"
            description="Tạo JAR với đầu vào và duplicate được kiểm soát">

        <!-- Xóa archive cũ để không giữ entry đã bị xóa khỏi đầu vào -->
        <delete file="${jar.file}"/>

        <jar destfile="${jar.file}"
             duplicate="fail"
             whenmanifestonly="fail"
             encoding="UTF-8">

            <fileset dir="${classes.dir}">
                <include name="**/*.class"/>
                <exclude name="**/*Test.class"/>
            </fileset>

            <fileset dir="${resources.dir}">
                <include name="**/*"/>
                <exclude name="local/**"/>
                <exclude name="**/*.secret"/>
            </fileset>

            <manifest>
                <attribute name="Main-Class"
                           value="com.example.App"/>
                <attribute name="Implementation-Title"
                           value="Inventory"/>
                <attribute name="Implementation-Version"
                           value="1.4.0"/>
            </manifest>
        </jar>
    </target>

</project>
~~~

Khi chạy **ant package**:

1. Target prepare tạo thư mục dist.
2. Task delete xóa JAR cũ để loại các entry không còn trong đầu vào.
3. FileSet thứ nhất chọn class ứng dụng và bỏ test class.
4. FileSet thứ hai chọn resource, bỏ cấu hình local và tệp secret.
5. Jar hợp nhất hai cây thư mục theo đường dẫn tương đối.
6. Nếu hai nguồn cùng tạo một entry, **duplicate="fail"** làm build dừng.
7. Nếu không có class hoặc resource ngoài manifest, **whenmanifestonly="fail"** ngăn tạo artifact rỗng.
8. Manifest khai báo lớp main và phiên bản ứng dụng.

Ví dụ này dùng chế độ tạo lại archive ở mỗi lần đóng gói. Nếu cần incremental update cho một tác vụ riêng, có thể bỏ delete và đặt update="true", nhưng phải có quy tắc xử lý entry đã bị xóa khỏi nguồn.

## 11. Kiểm tra nội dung JAR sau khi đóng gói

Sau khi tạo JAR, nên kiểm tra danh sách entry để xác nhận đường dẫn và nội dung thực tế:

~~~bash
jar tf dist/inventory.jar
~~~

Có thể lọc class chính:

~~~bash
jar tf dist/inventory.jar | grep 'com/example/'
~~~

Trên PowerShell:

~~~powershell
jar tf dist/inventory.jar | Select-String 'com/example/'
~~~

Kiểm tra manifest:

~~~bash
jar xf dist/inventory.jar META-INF/MANIFEST.MF
~~~

Sau đó đọc nội dung **META-INF/MANIFEST.MF**. Với quy trình CI, có thể lưu danh sách entry làm artifact kiểm tra hoặc chạy một bước xác nhận các class/resource bắt buộc tồn tại.

Một số điểm nên xác nhận:

- Class main có mặt đúng đường dẫn.
- Không có test class hoặc dữ liệu cục bộ không mong muốn.
- Resource có đường dẫn đúng như code ứng dụng đang truy cập.
- Không có duplicate entry ngoài chủ ý.
- Manifest có Main-Class và phiên bản đúng.
- Các service descriptor đã được hợp nhất hoặc tạo đúng cách.
- JAR không còn entry cũ sau khi source bị xóa/đổi tên.

Task Jar không tự xác nhận logic ứng dụng có đọc đúng resource hay không. Danh sách entry chỉ cho biết archive chứa gì; cần kiểm thử ứng dụng hoặc kiểm tra runtime để xác nhận nội dung được sử dụng đúng.

## 12. Những lưu ý về cập nhật và tính tái lập

### Độ phân giải timestamp của ZIP

ZIP lưu thời gian sửa đổi với độ chính xác 2 giây. Khi task Jar so sánh resource nguồn với entry đã có, một tệp chỉ mới hơn chưa đến 2 giây có thể không được xem là mới hơn. Điều này ảnh hưởng tới quyết định update và kiểm tra archive có cần xây dựng lại hay không.

Trong build CI, nếu cần kết quả chắc chắn sau khi thay đổi đầu vào, có thể xóa JAR cũ trước khi tạo lại. Đây cũng là lý do không nên dùng timestamp như bằng chứng duy nhất rằng nội dung byte đã giống nhau.

### Thời gian entry và archive có thể ảnh hưởng reproducibility

Entry trong JAR chứa metadata thời gian sửa đổi. Hai lần build từ cùng nội dung nhưng thời gian nguồn khác nhau có thể tạo archive có byte khác nhau.

Task Jar hỗ trợ thuộc tính **modificationtime** từ Ant 1.10.2 để đặt cùng một thời điểm sửa đổi cho các entry được ghi vào archive:

~~~xml
<jar destfile="dist/inventory.jar"
     modificationtime="2020-01-01T00:00:00Z"
     duplicate="fail">
    <fileset dir="build/classes"/>
</jar>
~~~

Cấu hình này có thể hỗ trợ tạo archive ổn định hơn về timestamp. Để có build tái lập thực sự, còn phải kiểm soát thứ tự resource, nội dung manifest, encoding, phiên bản compiler và các metadata khác.

### JAR đã ký

Nếu một JAR đã được ký số rồi bị cập nhật hoặc thay đổi entry, chữ ký có thể không còn hợp lệ. Quy trình phù hợp là tạo JAR hoàn chỉnh trước, sau đó ký artifact cuối cùng bằng task **signjar**. Không cập nhật nội dung sau khi ký.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JAR chứa hai class/resource cùng đường dẫn | Nhiều FileSet hoặc archive đầu vào có cùng entry | Dùng **duplicate="fail"** và xử lý nguồn xung đột |
| JAR chứa class cũ sau khi xóa source | Dùng **update="true"** hoặc archive không được tạo lại | Xóa JAR cũ trước khi đóng gói lại |
| Resource không được ứng dụng tìm thấy | FileSet đặt sai thư mục gốc hoặc đường dẫn entry không đúng | Kiểm tra basedir, prefix và đường dẫn tương đối |
| Tệp local/test lọt vào JAR | Phạm vi include quá rộng hoặc thiếu exclude | Khai báo include/exclude cụ thể |
| Manifest thiếu Main-Class | Không khai báo manifest entry cho ứng dụng executable | Thêm Main-Class vào phần tử manifest |
| Manifest của dependency ghi đè hoặc xung đột | Merge manifest từ archive nguồn không có quy tắc | Giữ mặc định skip hoặc dùng mergewithoutmain khi phù hợp |
| Service provider bị thiếu | Các descriptor cùng đường dẫn bị duplicate policy bỏ qua hoặc giữ một bản | Hợp nhất nội dung SPI hoặc khai báo provider bằng service |
| Archive không được cập nhật dù tệp vừa sửa | Timestamp nguồn mới hơn chưa đủ 2 giây hoặc bị giữ nguyên | Tạo lại archive hoặc kiểm tra timestamp |
| JAR rỗng vẫn được tạo | whenmanifestonly mặc định là create | Đặt **whenmanifestonly="fail"** nếu cần nội dung bắt buộc |
| JAR đã ký không còn hợp lệ | Archive bị sửa sau khi ký | Chỉ ký sau bước đóng gói cuối cùng |

## 14. Nguyên tắc thiết kế bước đóng gói

- Chọn đầu vào rõ ràng bằng FileSet và include/exclude; giữ class, resource và metadata ở các nguồn dễ nhận biết.
- Hiểu đường dẫn tương đối của từng FileSet vì đó là đường dẫn entry bên trong JAR.
- Dùng ZipFileSet với prefix hoặc fullpath khi cần đặt resource vào vị trí khác.
- Dùng **duplicate="fail"** cho artifact phát hành để phát hiện xung đột entry sớm.
- Chỉ dùng **preserve** khi thứ tự ưu tiên nguồn đã được xác định; tránh để nội dung cuối phụ thuộc thứ tự tình cờ.
- Dùng **update="true"** khi chủ đích cập nhật archive hiện có; nhớ rằng entry không còn trong đầu vào không tự bị xóa.
- Xóa archive cũ và tạo lại khi cần JAR phản ánh chính xác tập đầu vào hiện tại.
- Đặt **whenmanifestonly="fail"** nếu JAR chỉ có manifest không được chấp nhận.
- Quản lý manifest và service descriptor riêng, không coi chúng như resource thông thường có thể bỏ qua xung đột.
- Kiểm tra danh sách entry sau khi đóng gói và ký JAR sau khi nội dung đã hoàn tất.

Task Jar không chỉ nén một thư mục thành tệp. Nó hợp nhất nhiều nguồn resource thành một không gian đường dẫn chung, quản lý manifest và quyết định cách xử lý archive đã tồn tại. Khi kiểm soát đúng nội dung đầu vào, chính sách duplicate và chế độ update, build Ant tạo được JAR có cấu trúc rõ ràng, tránh entry xung đột và không vô tình giữ lại dữ liệu cũ.

## Tài liệu tham khảo

- [Apache Ant — Jar Task](https://ant.apache.org/manual/Tasks/jar.html)
- [Apache Ant — Zip Task](https://ant.apache.org/manual/Tasks/zip.html)
- [Apache Ant — SignJar Task](https://ant.apache.org/manual/Tasks/signjar.html)


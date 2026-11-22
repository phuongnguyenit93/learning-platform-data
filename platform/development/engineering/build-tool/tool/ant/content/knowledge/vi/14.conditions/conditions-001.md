# Tạo property điều kiện bằng condition trong Apache Ant

Trong Apache Ant, nhiều quyết định của quy trình build phụ thuộc vào trạng thái môi trường hoặc sự tồn tại của tài nguyên: có file cấu hình hay chưa, phiên bản đang build có phải bản production không, thư viện tùy chọn có sẵn không, file đích đã mới hơn file nguồn chưa. Task **condition** cho phép kiểm tra những điều kiện như vậy và tạo một property biểu thị kết quả.

Property được tạo có thể được dùng trong các task tiếp theo hoặc làm điều kiện cho target thông qua thuộc tính if và unless. Nhờ đó, build file có thể mô tả các nhánh xử lý rõ ràng mà không phải viết script riêng cho từng trường hợp.

## 1. condition là gì?

Task condition đánh giá một biểu thức điều kiện lồng bên trong nó. Nếu biểu thức đúng, Ant đặt property được chỉ định. Nếu biểu thức sai, property thường không được đặt, trừ khi bạn khai báo giá trị else.

Ví dụ kiểm tra môi trường:

~~~xml
<target name="detect-environment">
    <condition property="is.production">
        <equals arg1="${environment}" arg2="production"/>
    </condition>
</target>
~~~

Nếu property environment có giá trị production, task condition đặt property is.production. Nếu giá trị khác, is.production không được tạo bởi task này.

Sau đó, target có thể sử dụng property:

~~~xml
<target name="deploy-production" if="is.production">
    <echo message="Deploying production build"/>
</target>
~~~

Đây là cách kết hợp hai cơ chế:

- **condition** đánh giá một điều kiện và tạo property.
- **if/unless** trên target kiểm tra sự tồn tại của property để quyết định target có được thực thi hay không.

Điểm cần nhớ: condition không phải là một target và cũng không phải một property có thể thay đổi liên tục. Nó là task đánh giá điều kiện tại thời điểm được thực thi.

## 2. Cú pháp cơ bản của task condition

Cấu trúc tổng quát:

~~~xml
<condition property="property.name"
           value="true-value"
           else="false-value">
    <!-- Một condition type -->
</condition>
~~~

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| property | Tên property nhận kết quả điều kiện. |
| value | Giá trị chuỗi được đặt khi điều kiện đúng. Nếu bỏ qua, giá trị mặc định là true. |
| else | Giá trị chuỗi được đặt khi điều kiện sai. Nếu bỏ qua, property không được đặt khi điều kiện sai. |

Một ví dụ đơn giản:

~~~xml
<target name="check-config">
    <condition property="config.exists">
        <available file="config/app.properties" type="file"/>
    </condition>
</target>
~~~

Nếu file config/app.properties tồn tại, property config.exists được đặt thành chuỗi true. Nếu file không tồn tại, property đó không được đặt.

Bạn cũng có thể chỉ định giá trị khác:

~~~xml
<target name="check-config">
    <condition property="config.status"
               value="found"
               else="missing">
        <available file="config/app.properties" type="file"/>
    </condition>
    <echo message="Configuration status: ${config.status}"/>
</target>
~~~

Khi điều kiện đúng, config.status nhận found. Khi điều kiện sai, nó nhận missing.

### 2.1. Điều kiện đúng và điều kiện sai

Có hai cách thường dùng để xử lý kết quả.

**Chỉ đặt property khi điều kiện đúng**

~~~xml
<condition property="has.database.config">
    <available file="config/database.properties" type="file"/>
</condition>
~~~

- File tồn tại: property has.database.config được đặt.
- File không tồn tại: property chưa được đặt.

**Đặt giá trị cho cả hai trường hợp**

~~~xml
<condition property="has.database.config"
           value="true"
           else="false">
    <available file="config/database.properties" type="file"/>
</condition>
~~~

- File tồn tại: property có giá trị chuỗi true.
- File không tồn tại: property có giá trị chuỗi false.

Hai cách này có ý nghĩa khác nhau khi kết hợp với target if/unless. Phần tiếp theo sẽ giải thích chi tiết.

### 2.2. condition phải nằm trong một target

condition là một task, vì vậy thông thường nó được đặt bên trong target:

~~~xml
<target name="detect-options">
    <condition property="feature.enabled">
        <available file="config/feature.properties" type="file"/>
    </condition>
</target>

<target name="build-feature" depends="detect-options" if="feature.enabled">
    <echo message="Building optional feature"/>
</target>
~~~

Khi gọi target build-feature, Ant thực hiện dependency detect-options trước. Sau đó, target build-feature được kiểm tra điều kiện if và chỉ chạy phần thân khi property feature.enabled đã được đặt.

Cách tổ chức này giúp tách bước phát hiện trạng thái khỏi bước thực hiện công việc dựa trên trạng thái đó.

## 3. Phân biệt condition với if và unless

Ant có hai lớp điều khiển điều kiện thường gặp:

| Cơ chế | Cách hoạt động |
|---|---|
| Task condition | Đánh giá một điều kiện thực sự, rồi đặt property theo kết quả. |
| Thuộc tính if của target | Chạy target khi property có tên được chỉ định đã tồn tại. |
| Thuộc tính unless của target | Chạy target khi property có tên được chỉ định chưa tồn tại. |

Ví dụ:

~~~xml
<target name="detect">
    <condition property="release.ready">
        <available file="build/app.jar" type="file"/>
    </condition>
</target>

<target name="publish" depends="detect" if="release.ready">
    <echo message="Publish artifact"/>
</target>

<target name="explain-missing" depends="detect" unless="release.ready">
    <echo message="Artifact is not available"/>
</target>
~~~

Nếu file build/app.jar tồn tại:

- condition đặt release.ready.
- Target publish đủ điều kiện chạy.
- Target explain-missing bị bỏ qua.

Nếu file không tồn tại:

- condition không đặt release.ready.
- Target publish bị bỏ qua.
- Target explain-missing đủ điều kiện chạy.

### 3.1. if/unless không kiểm tra nội dung true/false

Đây là nhầm lẫn rất phổ biến. Thuộc tính if và unless của target kiểm tra **property có tồn tại hay không**, không kiểm tra giá trị của property có phải chuỗi true hay false.

Ví dụ:

~~~xml
<target name="show-feature" if="feature.enabled">
    <echo message="Feature is enabled"/>
</target>
~~~

Nếu property feature.enabled được đặt thành chuỗi false:

~~~bash
ant -Dfeature.enabled=false show-feature
~~~

target show-feature vẫn đủ điều kiện chạy, vì property tồn tại.

Do đó, nếu condition sử dụng else="false", property luôn được đặt ở cả hai nhánh. Target if="feature.enabled" sẽ chạy ngay cả khi giá trị là false.

Ví dụ:

~~~xml
<condition property="feature.enabled"
           value="true"
           else="false">
    <available file="config/feature.properties" type="file"/>
</condition>
~~~

Với cấu hình này, không nên dùng trực tiếp if="feature.enabled" để biểu thị kiểm tra boolean. Hãy dùng một condition type như istrue để đánh giá nội dung giá trị:

~~~xml
<condition property="run-feature">
    <istrue value="${feature.enabled}"/>
</condition>

<target name="build-feature" if="run-feature">
    <echo message="Building feature"/>
</target>
~~~

Trong trường hợp property feature.enabled là chuỗi true, run-feature được đặt. Nếu giá trị là false, run-feature không được đặt.

### 3.2. Khi nào dùng isset, istrue và isfalse?

Ba condition type này kiểm tra ba ý nghĩa khác nhau:

| Condition | Kiểm tra |
|---|---|
| isset | Property có tồn tại hay không. |
| istrue | Giá trị được cung cấp có biểu thị true hay không. |
| isfalse | Giá trị được cung cấp có biểu thị false hay không. |

Ví dụ:

~~~xml
<target name="check-flags">
    <condition property="flag.was.provided">
        <isset property="feature.enabled"/>
    </condition>

    <condition property="feature.is.true">
        <istrue value="${feature.enabled}"/>
    </condition>

    <condition property="feature.is.false">
        <isfalse value="${feature.enabled}"/>
    </condition>
</target>
~~~

Nếu feature.enabled không tồn tại, isset trả về false. istrue và isfalse dùng để diễn giải giá trị boolean được cung cấp; chúng không thay thế việc kiểm tra property có được khai báo hay chưa.

Khi cần phân biệt rõ ba trạng thái: chưa cấu hình, bật và tắt, hãy kiểm tra sự tồn tại trước rồi mới diễn giải giá trị.

### 3.3. Dependency vẫn chạy khi target bị bỏ qua

Thuộc tính if/unless quyết định phần thân của target có được thực thi hay không. Các dependency của target được xử lý trước khi Ant đánh giá và thực hiện phần thân target đó.

Ví dụ:

~~~xml
<target name="prepare">
    <echo message="Prepare build"/>
</target>

<target name="deploy" depends="prepare" if="is.production">
    <echo message="Deploy production"/>
</target>
~~~

Nếu is.production chưa được đặt, phần thân deploy bị bỏ qua, nhưng target prepare vẫn chạy vì nó là dependency.

Điều này quan trọng khi thiết kế build: không nên đặt một thao tác tốn thời gian hoặc có tác động không cần thiết vào dependency của target có điều kiện nếu bạn muốn tránh thao tác đó khi điều kiện sai.

## 4. Các condition type thường dùng

Task condition không tự định nghĩa cách kiểm tra từng loại dữ liệu. Công việc cụ thể được mô tả bằng các condition type lồng bên trong.

### 4.1. available: kiểm tra file, thư mục hoặc class

available kiểm tra xem một tài nguyên có sẵn hay không.

Kiểm tra file:

~~~xml
<condition property="config.found">
    <available file="config/app.properties" type="file"/>
</condition>
~~~

Kiểm tra thư mục:

~~~xml
<condition property="output.dir.exists">
    <available file="build/classes" type="dir"/>
</condition>
~~~

Có thể kiểm tra một class có thể được tìm thấy qua classpath:

~~~xml
<condition property="logging.available">
    <available classname="org.example.logging.Logger">
        <classpath refid="compile.classpath"/>
    </available>
</condition>
~~~

Một số thuộc tính thường gặp của available:

- file: đường dẫn file hoặc thư mục cần kiểm tra.
- type: giới hạn loại tài nguyên, thường là file hoặc dir.
- classname: tên lớp Java cần tìm.
- resource: tên resource cần tìm.
- filepath hoặc classpath: đường dẫn tìm kiếm phù hợp với loại tài nguyên.
- classpathref: tham chiếu đến path đã khai báo bằng id.

available cũng có thể xuất hiện như một task độc lập để đặt property. Khi nằm trong condition, nó đóng vai trò condition type và cung cấp kết quả true/false cho task condition bên ngoài.

### 4.2. equals: so sánh hai giá trị

equals so sánh hai giá trị:

~~~xml
<target name="detect-environment">
    <condition property="is.production">
        <equals arg1="${environment}" arg2="production"/>
    </condition>
</target>
~~~

Nếu environment bằng production, property is.production được đặt.

Có thể bỏ qua khác biệt chữ hoa/chữ thường:

~~~xml
<condition property="is.production">
    <equals
        arg1="${environment}"
        arg2="production"
        casesensitive="false"/>
</condition>
~~~

Có thể loại bỏ khoảng trắng ở đầu và cuối trước khi so sánh bằng trim:

~~~xml
<condition property="is.staging">
    <equals
        arg1="${environment}"
        arg2="staging"
        trim="true"
        casesensitive="false"/>
</condition>
~~~

equals hữu ích khi build cần rẽ nhánh theo profile, tên môi trường, phiên bản hoặc giá trị cấu hình.

### 4.3. contains: kiểm tra chuỗi con

contains kiểm tra một chuỗi có chứa chuỗi con hay không.

~~~xml
<condition property="is.snapshot">
    <contains
        string="${app.version}"
        substring="SNAPSHOT"/>
</condition>
~~~

Nếu app.version là 2.5.0-SNAPSHOT, property is.snapshot được đặt.

Có thể dùng thuộc tính casesensitive để điều khiển việc phân biệt chữ hoa và chữ thường:

~~~xml
<condition property="has.release-label">
    <contains
        string="${release.label}"
        substring="release"
        casesensitive="false"/>
</condition>
~~~

contains phù hợp với những kiểm tra đơn giản. Nếu cần so khớp theo mẫu phức tạp, hãy dùng condition type dành cho biểu thức chính quy nếu môi trường Ant đã có bộ hỗ trợ tương ứng.

### 4.4. os: kiểm tra hệ điều hành

os kiểm tra thông tin hệ điều hành đang chạy Ant. Nó hữu ích khi cần chọn script, đường dẫn hoặc tùy chọn theo nền tảng.

Ví dụ:

~~~xml
<target name="detect-platform">
    <condition property="platform.windows">
        <os family="windows"/>
    </condition>

    <condition property="platform.unix">
        <os family="unix"/>
    </condition>
</target>
~~~

Một số thuộc tính có thể dùng với os:

| Thuộc tính | Ý nghĩa |
|---|---|
| family | Nhóm hệ điều hành, ví dụ windows hoặc unix. |
| name | Tên hệ điều hành theo thông tin runtime. |
| arch | Kiến trúc máy, ví dụ x86_64. |
| version | Phiên bản hệ điều hành. |

Có thể kiểm tra cụ thể hơn:

~~~xml
<condition property="is.windows.64bit">
    <and>
        <os family="windows"/>
        <os arch="amd64"/>
    </and>
</condition>
~~~

Tên kiến trúc thực tế phụ thuộc JVM và hệ điều hành; trước khi dựa vào một giá trị cụ thể, hãy kiểm tra thông tin runtime của môi trường build.

### 4.5. uptodate: kiểm tra file đích đã mới hơn file nguồn

uptodate kiểm tra trạng thái thời gian cập nhật giữa file nguồn và file đích.

~~~xml
<condition property="report.is.current">
    <uptodate
        srcfile="src/report.xml"
        targetfile="build/report.html"/>
</condition>
~~~

Nếu file đích tồn tại và không cũ hơn file nguồn theo quy tắc so sánh timestamp của Ant, điều kiện đúng. Nếu file đích chưa có hoặc cần được tạo lại, điều kiện sai.

Có thể dùng property để quyết định có cần tạo lại kết quả:

~~~xml
<target name="check-report">
    <condition property="report.needs.build">
        <not>
            <uptodate
                srcfile="src/report.xml"
                targetfile="build/report.html"/>
        </not>
    </condition>
</target>

<target name="generate-report" depends="check-report" if="report.needs.build">
    <echo message="Generating report"/>
</target>
~~~

Trong build thực tế, task tạo báo cáo sẽ thay echo. Cách kiểm tra này phù hợp với các bước tạo artifact từ nguồn, nhưng cần hiểu rằng timestamp không phải lúc nào cũng phản ánh đầy đủ nội dung file. Nếu file bị thay đổi mà timestamp không được cập nhật đúng, kết quả kiểm tra có thể không phản ánh nội dung thực.

## 5. Kết hợp điều kiện bằng and, or và not

Các condition type logic cho phép kết hợp nhiều điều kiện nhỏ thành một điều kiện tổng hợp.

### 5.1. and: tất cả điều kiện phải đúng

and trả về true khi mọi condition con đều đúng.

Ví dụ chỉ cho phép publish khi môi trường là production và artifact đã tồn tại:

~~~xml
<target name="detect-publish-ready">
    <condition property="publish.ready">
        <and>
            <equals arg1="${environment}" arg2="production"/>
            <available file="build/app.jar" type="file"/>
        </and>
    </condition>
</target>
~~~

Kết quả:

| environment | File JAR tồn tại | publish.ready |
|---|---|---|
| production | Có | Được đặt |
| production | Không | Không được đặt |
| staging | Có | Không được đặt |
| staging | Không | Không được đặt |

and phù hợp khi một thao tác cần nhiều điều kiện tiên quyết cùng được đáp ứng.

### 5.2. or: chỉ cần một điều kiện đúng

or trả về true nếu có ít nhất một condition con đúng.

Ví dụ cho phép build chế độ debug trên môi trường development hoặc testing:

~~~xml
<condition property="debug.allowed">
    <or>
        <equals arg1="${environment}" arg2="development"/>
        <equals arg1="${environment}" arg2="testing"/>
    </or>
</condition>
~~~

Chỉ cần một trong hai phép so sánh đúng thì debug.allowed được đặt.

### 5.3. not: đảo ngược kết quả

not đảo kết quả của condition con:

~~~xml
<condition property="config.missing">
    <not>
        <available file="config/app.properties" type="file"/>
    </not>
</condition>
~~~

Nếu file không tồn tại, available trả về false; not đảo thành true và property config.missing được đặt.

not thường chứa một condition con. Nếu cần phủ định một nhóm điều kiện, hãy đặt and hoặc or bên trong not.

### 5.4. Kết hợp nhiều tầng

Các condition logic có thể lồng nhau để mô tả điều kiện nghiệp vụ:

~~~xml
<condition property="deploy.allowed">
    <and>
        <equals arg1="${environment}" arg2="production"/>
        <available file="build/app.jar" type="file"/>
        <or>
            <equals arg1="${release.channel}" arg2="stable"/>
            <equals arg1="${release.channel}" arg2="hotfix"/>
        </or>
    </and>
</condition>
~~~

Điều kiện trên đúng khi:

1. Môi trường là production.
2. File build/app.jar tồn tại.
3. Kênh phát hành là stable hoặc hotfix.

Cách lồng điều kiện này dễ đọc hơn khi bạn tách các nhóm logic bằng and và or. Với biểu thức phức tạp, nên chia thành các property trung gian để người bảo trì dễ hiểu và kiểm tra.

## 6. Tạo property điều kiện cho nhiều tình huống

### 6.1. Kiểm tra cấu hình tùy chọn

Một project có thể có file cấu hình riêng cho từng máy phát triển. Nếu file không tồn tại, build dùng giá trị mặc định; nếu có, build nạp cấu hình đó.

~~~xml
<target name="load-local-config">
    <condition property="local.config.exists">
        <available file="config/local.properties" type="file"/>
    </condition>
</target>

<target name="use-local-config" depends="load-local-config" if="local.config.exists">
    <loadproperties srcFile="config/local.properties" prefix="local"/>
</target>

<target name="use-default-config" depends="load-local-config" unless="local.config.exists">
    <echo message="Using default configuration"/>
</target>
~~~

Ở đây condition tạo cờ local.config.exists. Hai target sau dùng cùng property để chọn nhánh.

Nếu file là bắt buộc, không nên dùng nhánh mặc định một cách âm thầm. Hãy làm build thất bại với thông điệp rõ ràng khi thiếu file.

### 6.2. Kiểm tra phiên bản phát hành

Giả sử project sử dụng property app.version:

~~~xml
<target name="detect-release-type">
    <condition property="release.is.final">
        <and>
            <not>
                <contains string="${app.version}" substring="SNAPSHOT"/>
            </not>
            <not>
                <contains string="${app.version}" substring="alpha"/>
            </not>
        </and>
    </condition>
</target>

<target name="publish-final" depends="detect-release-type" if="release.is.final">
    <echo message="Publishing final release"/>
</target>
~~~

Ví dụ này minh họa cách kết hợp điều kiện chuỗi. Với quy tắc phiên bản phức tạp, nên dùng một bộ phân tích version chuyên dụng thay vì dựa vào vài chuỗi con đơn giản.

### 6.3. Kiểm tra hệ điều hành để chọn task

Bạn có thể tạo property cho từng nền tảng:

~~~xml
<target name="detect-platform">
    <condition property="is.windows">
        <os family="windows"/>
    </condition>

    <condition property="is.unix">
        <os family="unix"/>
    </condition>
</target>

<target name="prepare-windows" depends="detect-platform" if="is.windows">
    <echo message="Prepare Windows environment"/>
</target>

<target name="prepare-unix" depends="detect-platform" if="is.unix">
    <echo message="Prepare Unix environment"/>
</target>
~~~

Trong project thực tế, hai target có thể chứa task chạy script hoặc chuẩn bị công cụ riêng cho từng hệ điều hành. Việc phát hiện hệ điều hành chỉ tạo cờ điều kiện; nó không tự cài đặt công cụ cần thiết.

### 6.4. Kiểm tra file đầu ra trước khi đóng gói

Có thể dùng available để kiểm tra artifact đã tồn tại trước khi chạy task đóng gói hoặc triển khai:

~~~xml
<target name="check-artifact">
    <condition property="artifact.exists">
        <available file="build/app.jar" type="file"/>
    </condition>
</target>

<target name="deploy" depends="check-artifact" if="artifact.exists">
    <echo message="Deploying build/app.jar"/>
</target>

<target name="missing-artifact" depends="check-artifact" unless="artifact.exists">
    <fail message="Artifact build/app.jar does not exist"/>
</target>
~~~

Cách này tạo thông báo rõ ràng nếu artifact chưa được tạo. Trong build thực tế, hãy đặt dependency biên dịch hoặc đóng gói phù hợp để artifact được tạo trước bước kiểm tra.

## 7. Thời điểm đánh giá condition và phạm vi property

### 7.1. Property được tạo khi task condition chạy

Task condition chỉ đánh giá khi Ant thực thi target chứa task đó. Vì vậy, target sử dụng property điều kiện cần phụ thuộc vào target tạo property:

~~~xml
<target name="detect">
    <condition property="has.source">
        <available file="src/Main.java" type="file"/>
    </condition>
</target>

<target name="compile-optional" depends="detect" if="has.source">
    <javac srcdir="src" destdir="build/classes"/>
</target>
~~~

Nếu bỏ depends="detect", target compile-optional có thể được kiểm tra trước khi property has.source được tạo. Hãy mô tả dependency để thứ tự xử lý rõ ràng.

### 7.2. Property là bất biến

Property Ant thông thường được đặt một lần. Nếu property đã tồn tại, task condition không thể ghi đè nó bằng kết quả mới.

Ví dụ:

~~~xml
<condition property="is.production">
    <equals arg1="${environment}" arg2="production"/>
</condition>
~~~

Nếu is.production đã được truyền từ dòng lệnh:

~~~bash
ant -Dis.production=false deploy
~~~

thì condition không thay thế giá trị false đã có. Hơn nữa, target if="is.production" vẫn kiểm tra sự tồn tại của property nên vẫn đủ điều kiện chạy.

Nếu muốn cho phép người chạy build chọn chế độ, hãy thiết kế tên property và cách kiểm tra giá trị một cách nhất quán. Có thể dùng một property đầu vào riêng, sau đó tạo một property kết quả khác bằng condition và istrue/equals.

### 7.3. Tên property điều kiện nên có ý nghĩa

Nên chọn tên thể hiện trạng thái đúng hoặc sai, ví dụ:

- is.production
- has.database.config
- artifact.exists
- report.needs.build
- deploy.allowed
- debug.enabled

Tên như flag1 hoặc check2 khiến người đọc phải lần ngược toàn bộ build file để hiểu ý nghĩa.

## 8. Ví dụ hoàn chỉnh: build có điều kiện theo môi trường

Ví dụ dưới đây kết hợp equals, available, os, and, or và các target có if/unless.

~~~xml
<project name="inventory-app" default="build" basedir=".">

    <property name="environment" value="development"/>
    <property name="build.dir" location="build"/>
    <property name="artifact.file" location="${build.dir}/inventory-app.jar"/>

    <target name="detect-environment">
        <condition property="is.production">
            <equals
                arg1="${environment}"
                arg2="production"
                casesensitive="false"
                trim="true"/>
        </condition>

        <condition property="is.development">
            <equals
                arg1="${environment}"
                arg2="development"
                casesensitive="false"
                trim="true"/>
        </condition>
    </target>

    <target name="detect-platform">
        <condition property="is.windows">
            <os family="windows"/>
        </condition>

        <condition property="is.unix">
            <os family="unix"/>
        </condition>
    </target>

    <target name="prepare">
        <mkdir dir="${build.dir}/classes"/>
        <echo message="Preparing ${environment} build"/>
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile application"/>
        <!-- Thay echo bằng task javac trong project thực tế. -->
    </target>

    <target name="package" depends="compile">
        <echo file="${artifact.file}" message="Placeholder artifact"/>
        <!-- Thay echo bằng task jar trong project thực tế. -->
    </target>

    <target name="detect-artifact" depends="package">
        <condition property="artifact.exists">
            <available file="${artifact.file}" type="file"/>
        </condition>
    </target>

    <target name="verify-production"
            depends="detect-environment,detect-artifact">
        <condition property="production.deploy.allowed">
            <and>
                <istrue value="${is.production}"/>
                <isset property="artifact.exists"/>
            </and>
        </condition>
    </target>

    <target name="deploy-production"
            depends="verify-production"
            if="production.deploy.allowed">
        <echo message="Deploying production artifact"/>
    </target>

    <target name="show-development-message"
            depends="detect-environment"
            if="is.development">
        <echo message="Development build: deployment is optional"/>
    </target>

    <target name="build" depends="package,detect-platform">
        <echo message="Build completed"/>
    </target>

</project>
~~~

Trong ví dụ, echo tạo một file placeholder có đuôi JAR để minh họa phép kiểm tra available. Đây không phải JAR hợp lệ; trong project thực tế, thay phần này bằng task jar sau khi biên dịch mã nguồn thật.

Các lệnh có thể chạy:

~~~bash
# Build theo môi trường mặc định development
ant

# Xác định môi trường production và kiểm tra điều kiện triển khai
ant -Denvironment=production deploy-production

# Chạy target hiển thị thông điệp development
ant show-development-message

# Kiểm tra target và mô tả của project
ant -projecthelp
~~~

Luồng điều kiện của deploy-production:

~~~text
detect-environment ─┐
                    ├──> verify-production ──> deploy-production
package ──> detect-artifact ┘
~~~

Target verify-production chỉ đặt production.deploy.allowed khi môi trường là production và artifact tồn tại. Target deploy-production chỉ chạy phần thân khi property này được đặt. Các dependency của deploy-production vẫn được thực hiện trước khi Ant kiểm tra điều kiện của chính target đó.

## 9. Những nhầm lẫn thường gặp

### 9.1. Nghĩ condition tạo một biến boolean có thể thay đổi

condition tạo property chuỗi theo quy tắc property của Ant. Property đã được đặt không thể ghi đè bằng khai báo thông thường.

### 9.2. Nghĩ if="flag" kiểm tra flag có giá trị true

if và unless kiểm tra sự tồn tại của property. Property có giá trị false vẫn tồn tại. Dùng istrue hoặc isfalse khi cần diễn giải nội dung boolean.

### 9.3. Quên dependency tạo property

Nếu target dùng property do condition tạo, hãy bảo đảm target đó phụ thuộc vào target chứa condition. Nếu không, property có thể chưa tồn tại khi target được kiểm tra.

### 9.4. Dùng available như phép kiểm tra nội dung file

available kiểm tra sự hiện diện và loại tài nguyên, không đọc nội dung để xác nhận giá trị bên trong. Nếu cần kiểm tra nội dung, hãy đọc file bằng task phù hợp rồi so sánh giá trị.

### 9.5. Lồng điều kiện quá phức tạp

Một biểu thức and/or nhiều tầng có thể khó bảo trì. Hãy chia thành các property trung gian có tên rõ ràng nếu nhiều target cần dùng chung một phần điều kiện.

### 9.6. Dùng else rồi lại kiểm tra bằng if

Nếu condition đặt property thành true hoặc false bằng else, target if vẫn chạy trong cả hai trường hợp vì property luôn tồn tại. Dùng condition trung gian chỉ được đặt khi biểu thức đúng, hoặc dùng istrue để kiểm tra giá trị.

## 10. Cách thiết kế điều kiện dễ bảo trì

Khi tạo property điều kiện trong build file, hãy thực hiện theo các bước:

1. Xác định chính xác trạng thái cần kiểm tra: file tồn tại, giá trị bằng một chuỗi, hệ điều hành phù hợp hay nhiều điều kiện cùng đúng.
2. Chọn condition type phù hợp như available, equals, contains, os, uptodate hoặc isset.
3. Dùng and, or và not để kết hợp những điều kiện nhỏ khi cần.
4. Đặt property kết quả với tên mô tả trạng thái, ví dụ artifact.exists hoặc deploy.allowed.
5. Đặt task condition trong một target riêng nếu nhiều target cần dùng kết quả.
6. Khai báo depends để target sử dụng property chạy sau target tạo property.
7. Dùng if/unless cho kiểm tra sự tồn tại của property; dùng istrue/isfalse khi cần kiểm tra giá trị boolean.
8. Tránh dùng cùng một tên property cho nhiều mục đích hoặc kỳ vọng property được tính lại trong cùng project.

Điều kiện nên phản ánh trạng thái có thể xác định được. Nếu một thao tác quan trọng như phát hành hoặc triển khai cần nhiều điều kiện, hãy biểu diễn từng điều kiện thành property riêng rồi kết hợp chúng trong một condition tổng hợp. Cách này làm log, dependency và quyết định chạy target dễ hiểu hơn.

## 11. Ghi nhớ

- **condition** đánh giá một condition type và tạo property theo kết quả.
- **property** là tên property nhận kết quả; **value** là giá trị khi đúng; **else** là giá trị khi sai.
- Nếu không khai báo else, property thường chỉ được đặt khi điều kiện đúng.
- **isset** kiểm tra property tồn tại; **istrue** và **isfalse** kiểm tra nội dung boolean.
- **available** kiểm tra tài nguyên; **equals** so sánh giá trị; **contains** tìm chuỗi con; **os** kiểm tra nền tảng; **uptodate** so sánh trạng thái timestamp.
- **and**, **or** và **not** cho phép kết hợp nhiều điều kiện.
- Target if/unless kiểm tra sự tồn tại của property, không kiểm tra chuỗi true/false.
- Dependency của target vẫn chạy ngay cả khi phần thân target bị bỏ qua bởi if/unless.
- Target sử dụng property điều kiện cần phụ thuộc vào target tạo property.
- Property Ant có tính bất biến; hãy chọn tên property riêng cho từng kết quả cần lưu.

Khi sử dụng condition để biến trạng thái môi trường thành property có ý nghĩa, bạn có thể xây dựng các target có điều kiện rõ ràng, tái sử dụng được và dễ hiểu trong Apache Ant.


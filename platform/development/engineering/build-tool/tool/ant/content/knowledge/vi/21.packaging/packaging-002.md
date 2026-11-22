# Cấu hình manifest với Main-Class, Class-Path và thông tin phiên bản

## Mục tiêu

Manifest là tệp metadata nằm trong JAR, thường ở đường dẫn META-INF/MANIFEST.MF. Nó mô tả cách Java launcher khởi chạy ứng dụng, các JAR phụ thuộc cần nạp và thông tin về phiên bản hoặc nhà cung cấp của thành phần được đóng gói.

Khi tạo JAR bằng Apache Ant, task jar cho phép khai báo manifest trực tiếp trong buildfile. Ba nhóm thông tin thường cần cấu hình là:

- **Main-Class**: tên lớp chứa điểm bắt đầu của ứng dụng khi chạy bằng java -jar.
- **Class-Path**: các vị trí thư viện hoặc thư mục bên ngoài mà ứng dụng cần khi chạy.
- **Thông tin phiên bản**: các thuộc tính như Implementation-Version, Specification-Version, tên sản phẩm và nhà cung cấp.

Manifest có ảnh hưởng đến cách JAR được sử dụng sau khi đóng gói. Một JAR có thể tạo thành công nhưng không chạy được nếu Main-Class sai, Class-Path trỏ sai vị trí hoặc thư viện phụ thuộc không được phân phối cùng ứng dụng.

## 1. Manifest nằm ở đâu và dùng để làm gì?

JAR là một định dạng archive dựa trên ZIP. Ngoài các lớp và tài nguyên của ứng dụng, JAR có thể chứa thư mục META-INF. Tệp manifest chuẩn nằm tại:

~~~text
META-INF/MANIFEST.MF
~~~

Một manifest đơn giản có thể trông như sau:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/logging.jar lib/json-core.jar
Implementation-Title: Sample Application
Implementation-Version: 2.4.0
Implementation-Vendor: Example Corporation

~~~

Manifest gồm các header theo dạng tên và giá trị. Các header chính nằm trong main section ở đầu tệp. Có thể có thêm section riêng cho từng package hoặc nhóm tài nguyên.

Manifest được Java runtime đọc khi JAR được sử dụng. Nó cũng là nơi lưu metadata mà các công cụ đóng gói, triển khai hoặc kiểm tra phiên bản có thể đọc.

### 1.1. Ant tạo manifest khi đóng gói JAR

Task jar của Ant tạo JAR từ các lớp và tài nguyên, đồng thời có thể thêm manifest:

~~~xml
<jar destfile="build/sample-app.jar">
    <fileset dir="build/classes"/>
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.app.Main"/>
        <attribute name="Implementation-Version"
                   value="2.4.0"/>
    </manifest>
</jar>
~~~

Phần tử manifest lồng bên trong jar chứa các thuộc tính cần ghi vào META-INF/MANIFEST.MF. Ant tạo manifest mặc định nếu buildfile không cung cấp nội dung riêng, sau đó bổ sung các thuộc tính được khai báo.

Nên khai báo manifest ngay trong task jar để cấu hình đóng gói có thể được xem và duy trì cùng một chỗ.

## 2. Main-Class: xác định điểm bắt đầu của ứng dụng

### 2.1. Giá trị Main-Class

Main-Class phải là tên đầy đủ của lớp Java, gồm package và tên lớp, nhưng không có phần mở rộng .class.

Ví dụ, với lớp:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Giá trị manifest là:

~~~text
Main-Class: com.example.app.Main
~~~

Không viết đường dẫn tệp như com/example/app/Main.class, không thêm dấu gạch chéo ở đầu và không ghi tên tệp Java Main.java.

### 2.2. Cấu hình Main-Class trong Ant

~~~xml
<jar destfile="build/sample-app.jar">
    <fileset dir="build/classes"/>
    <manifest>
        <attribute name="Main-Class"
                   value="com.example.app.Main"/>
    </manifest>
</jar>
~~~

Khi đóng gói, Ant ghi Main-Class vào main section của manifest. Sau đó có thể chạy:

~~~text
java -jar build/sample-app.jar
~~~

Java launcher đọc manifest, tìm lớp được chỉ định và gọi phương thức main.

### 2.3. Điều kiện để lớp chính chạy được

Lớp được chỉ định phải có phương thức main hợp lệ theo quy tắc Java launcher, thường là:

~~~java
public static void main(String[] args)
~~~

Lớp cũng phải có trong JAR hoặc có thể được tìm thấy qua classpath khi chạy. Nếu Main-Class sai package, sai chữ hoa/chữ thường hoặc lớp không được đóng gói, lệnh java -jar sẽ báo không tìm thấy hoặc không nạp được lớp chính.

Một JAR thư viện thường không cần Main-Class. Nếu JAR chỉ cung cấp API để ứng dụng khác sử dụng, hãy bỏ thuộc tính này thay vì đặt một lớp bất kỳ làm điểm bắt đầu.

### 2.4. Main-Class không tự thêm lớp vào JAR

Khai báo Main-Class chỉ ghi tên lớp vào manifest. Nó không biên dịch mã nguồn, không tự tìm lớp còn thiếu và cũng không đóng gói các lớp khác.

Hãy bảo đảm target compile chạy trước target jar và thư mục chứa lớp đã biên dịch được thêm vào archive:

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <jar destfile="build/sample-app.jar">
        <fileset dir="build/classes"/>
        <manifest>
            <attribute name="Main-Class"
                       value="com.example.app.Main"/>
        </manifest>
    </jar>
</target>
~~~

Dependency của target bảo đảm compile hoàn thành trước khi đóng gói.

## 3. Class-Path: khai báo thư viện cần khi chạy

### 3.1. Class-Path trong manifest khác classpath của javac

Thuộc tính Class-Path của manifest mô tả các vị trí bổ sung mà Java runtime cần tìm khi nạp JAR. Nó thường được dùng để ứng dụng chạy bằng java -jar có thể nạp các thư viện đặt bên ngoài JAR chính.

Cần phân biệt:

| Cấu hình | Thời điểm sử dụng | Mục đích |
|---|---|---|
| classpath của javac trong Ant | Khi biên dịch | Giúp compiler tìm lớp và thư viện phụ thuộc |
| Class-Path trong manifest | Khi chạy JAR | Giúp Java runtime tìm các thư viện bên ngoài |
| Thư mục hoặc JAR được đóng gói trực tiếp | Khi chạy JAR | Cung cấp lớp và tài nguyên ngay trong archive |

Việc ghi Class-Path vào manifest không thay thế classpath cần thiết cho task javac. Build vẫn phải cung cấp dependency cho compiler ở bước biên dịch.

### 3.2. Cú pháp Class-Path

Giá trị Class-Path là danh sách URL tương đối, các mục được phân cách bằng dấu cách:

~~~text
Class-Path: lib/logging.jar lib/json-core.jar
~~~

Không dùng dấu chấm phẩy trên Windows hoặc dấu hai chấm trên Unix để phân cách như chuỗi classpath của dòng lệnh. Manifest dùng dấu cách giữa các URL.

Các URL được giải quyết tương đối với vị trí của JAR chứa manifest. Ví dụ cấu trúc phân phối:

~~~text
dist/
├── sample-app.jar
└── lib/
    ├── logging.jar
    └── json-core.jar
~~~

Manifest của sample-app.jar có thể ghi:

~~~text
Class-Path: lib/logging.jar lib/json-core.jar
~~~

Khi chạy JAR chính trong thư mục dist, Java runtime tìm các thư viện trong dist/lib.

### 3.3. Khai báo Class-Path bằng Ant

~~~xml
<jar destfile="dist/sample-app.jar">
    <fileset dir="build/classes"/>

    <manifest>
        <attribute name="Main-Class"
                   value="com.example.app.Main"/>
        <attribute name="Class-Path"
                   value="lib/logging.jar lib/json-core.jar"/>
    </manifest>
</jar>
~~~

Task jar chỉ ghi tham chiếu vào manifest. Nó không tự tải hoặc sao chép các JAR phụ thuộc vào thư mục lib. Build cần có bước phân phối riêng để đặt các dependency vào đúng vị trí.

Ví dụ:

~~~xml
<target name="package" depends="compile">
    <mkdir dir="dist/lib"/>

    <copy todir="dist/lib">
        <fileset dir="lib">
            <include name="logging.jar"/>
            <include name="json-core.jar"/>
        </fileset>
    </copy>

    <jar destfile="dist/sample-app.jar">
        <fileset dir="build/classes"/>
        <manifest>
            <attribute name="Main-Class"
                       value="com.example.app.Main"/>
            <attribute name="Class-Path"
                       value="lib/logging.jar lib/json-core.jar"/>
        </manifest>
    </jar>
</target>
~~~

Kết quả là thư mục dist chứa JAR chính và các thư viện ở đúng đường dẫn được manifest tham chiếu.

### 3.4. Đường dẫn trong Class-Path là URL tương đối

Class-Path của manifest tuân theo quy tắc URL, không phải quy tắc đường dẫn hệ điều hành. Một số điểm cần nhớ:

- Dùng dấu gạch chéo xuôi / trong URL.
- Dùng dấu cách để phân cách các mục.
- Mỗi mục được giải quyết tương đối với vị trí JAR chính.
- Thư mục được tham chiếu nên có dấu / ở cuối để thể hiện đó là thư mục.
- Tên có dấu cách hoặc ký tự đặc biệt phải được mã hóa theo quy tắc URL; tốt nhất tránh tên có dấu cách trong thư mục phân phối.
- Không dùng wildcard kiểu lib/*; manifest Class-Path không tự mở rộng wildcard như tùy chọn -cp của Java launcher.

Ví dụ tham chiếu thư mục:

~~~text
Class-Path: classes/ lib/logging.jar
~~~

Nếu JAR nằm trong dist, đường dẫn classes/ được giải quyết thành thư mục dist/classes.

### 3.5. Class-Path không đóng gói dependency

Một lỗi thường gặp là ghi tên thư viện vào Class-Path nhưng quên phân phối tệp JAR đó.

Manifest có thể chứa:

~~~text
Class-Path: lib/logging.jar
~~~

nhưng nếu dist/lib/logging.jar không tồn tại, ứng dụng vẫn báo lỗi thiếu lớp khi chạy.

Hãy xem manifest như danh sách tham chiếu. Các tệp thực tế phải được copy hoặc tải về riêng, và cấu trúc thư mục phải khớp chính xác với những URL đã ghi.

### 3.6. Khi chạy java -jar

Khi dùng:

~~~text
java -jar dist/sample-app.jar
~~~

Java launcher dùng Main-Class và Class-Path trong manifest của JAR chính. Tùy chọn classpath bên ngoài như -cp không được dùng để thay thế classpath của ứng dụng trong chế độ -jar.

Nếu muốn điều khiển classpath hoàn toàn từ lệnh chạy, có thể dùng dạng:

~~~text
java -cp "dist/sample-app.jar;dist/lib/*" com.example.app.Main
~~~

Dấu phân cách trong ví dụ này là dấu chấm phẩy của Windows; trên Unix-like dùng dấu hai chấm. Đây là cơ chế dòng lệnh, khác với Class-Path trong manifest.

Với ứng dụng được phân phối dưới dạng executable JAR, nên kiểm tra bằng chính lệnh java -jar để xác nhận manifest hoạt động như dự kiến.

## 4. Thông tin phiên bản trong manifest

Manifest có thể chứa metadata mô tả phiên bản sản phẩm, phiên bản đặc tả API và nhà cung cấp.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| Implementation-Title | Tên thành phần hoặc sản phẩm được triển khai |
| Implementation-Version | Phiên bản cụ thể của bản triển khai |
| Implementation-Vendor | Tổ chức cung cấp bản triển khai |
| Specification-Title | Tên đặc tả hoặc API mà thành phần thực hiện |
| Specification-Version | Phiên bản của đặc tả hoặc API |
| Specification-Vendor | Tổ chức chịu trách nhiệm về đặc tả |
| Implementation-URL | Địa chỉ thông tin về bản triển khai |
| Specification-URL | Địa chỉ tài liệu đặc tả |

Không nên nhầm Implementation-Version với Specification-Version:

- Implementation-Version thay đổi khi bản triển khai hoặc bản phát hành của sản phẩm thay đổi.
- Specification-Version mô tả phiên bản hợp đồng/API mà thành phần tuân theo.

Ví dụ, một thư viện có thể triển khai Specification-Version 3.1 nhưng bản triển khai cụ thể đang là Implementation-Version 3.1.7.

### 4.1. Khai báo metadata phiên bản

~~~xml
<manifest>
    <attribute name="Implementation-Title"
               value="Sample Application"/>
    <attribute name="Implementation-Version"
               value="2.4.0"/>
    <attribute name="Implementation-Vendor"
               value="Example Corporation"/>

    <attribute name="Specification-Title"
               value="Sample Application API"/>
    <attribute name="Specification-Version"
               value="2.3"/>
    <attribute name="Specification-Vendor"
               value="Example Corporation"/>
</manifest>
~~~

Các giá trị được ghi vào main section của manifest. Công cụ khác có thể đọc chúng để hiển thị thông tin phiên bản hoặc kiểm tra thành phần.

### 4.2. Dùng property để quản lý phiên bản

Không nên viết cùng một số phiên bản ở nhiều nơi trong buildfile. Có thể đặt giá trị trong tệp properties:

**version.properties**

~~~properties
application.title=Sample Application
release.version=2.4.0
specification.version=2.3
vendor.name=Example Corporation
~~~

Nạp tệp trước khi đóng gói:

~~~xml
<project name="versioned-jar" default="package" basedir=".">
    <property file="version.properties"/>

    <target name="package" depends="compile">
        <jar destfile="dist/sample-app-${release.version}.jar">
            <fileset dir="build/classes"/>
            <manifest>
                <attribute name="Main-Class"
                           value="com.example.app.Main"/>
                <attribute name="Implementation-Title"
                           value="${application.title}"/>
                <attribute name="Implementation-Version"
                           value="${release.version}"/>
                <attribute name="Implementation-Vendor"
                           value="${vendor.name}"/>
                <attribute name="Specification-Version"
                           value="${specification.version}"/>
            </manifest>
        </jar>
    </target>
</project>
~~~

Lợi ích:

- Tên JAR và Implementation-Version có thể dùng cùng một nguồn giá trị.
- Có thể thay đổi phiên bản mà không sửa manifest ở nhiều nơi.
- CI có thể truyền phiên bản qua property dòng lệnh.

Ví dụ:

~~~text
ant -Drelease.version=2.4.1 package
~~~

Property được truyền từ dòng lệnh có độ ưu tiên cao hơn property được nạp từ buildfile hoặc tệp properties. Tuy nhiên, Ant property chỉ thiết lập một lần; nếu property đã được gán trước đó, khai báo sau không ghi đè nó. Hãy tổ chức thứ tự nạp giá trị mặc định và giá trị môi trường có chủ đích.

### 4.3. Thêm số build hoặc revision

Có thể thêm thuộc tính riêng để ghi build number hoặc revision:

~~~xml
<manifest>
    <attribute name="Implementation-Version"
               value="${release.version}"/>
    <attribute name="Build-Number"
               value="${build.number}"/>
    <attribute name="Build-Revision"
               value="${git.revision}"/>
</manifest>
~~~

Các header tùy chỉnh giúp công cụ nội bộ hoặc nhóm vận hành truy xuất metadata. Tên header cần tuân theo quy tắc tên header của manifest, không chứa khoảng trắng hoặc dấu phân cách tùy ý.

Chỉ ghi thông tin đã được xác định. Nếu build không biết revision, đừng tự tạo một giá trị có vẻ hợp lệ nhưng không phản ánh commit thực tế.

## 5. Section riêng cho package

Ngoài main section, manifest có thể có section áp dụng cho một package hoặc đường dẫn tài nguyên cụ thể.

Ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Version: 2.4.0

Name: com/example/security/
Sealed: true

Name: com/example/api/
Specification-Version: 2.3

~~~

Section bắt đầu bằng header Name. Các thuộc tính sau đó áp dụng cho mục được đặt tên trong section đó, cho đến section tiếp theo.

### 5.1. Khai báo section trong Ant

~~~xml
<manifest>
    <attribute name="Main-Class"
               value="com.example.app.Main"/>
    <attribute name="Implementation-Version"
               value="2.4.0"/>

    <section name="com/example/security/">
        <attribute name="Sealed" value="true"/>
    </section>

    <section name="com/example/api/">
        <attribute name="Specification-Version"
                   value="2.3"/>
    </section>
</manifest>
~~~

Thuộc tính Sealed có thể được dùng để yêu cầu các lớp trong package tương ứng chỉ được nạp từ cùng một code source theo cơ chế sealing của Java. Đây là một thiết lập ảnh hưởng đến cách class loader xử lý package; chỉ bật khi cấu trúc phân phối được thiết kế phù hợp.

Section package thường hữu ích khi các package khác nhau có thông tin đặc tả hoặc trạng thái sealing khác nhau. Không cần tạo section riêng nếu toàn bộ JAR chỉ dùng chung một bộ metadata.

## 6. Manifest hoàn chỉnh cho executable JAR

Ví dụ sau kết hợp Main-Class, Class-Path và thông tin phiên bản:

~~~xml
<project name="sample-app" default="package" basedir=".">
    <property file="version.properties"/>

    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="lib.dir" location="lib"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src"
               destdir="${classes.dir}"
               classpathref="compile.classpath"
               includeantruntime="false"/>
    </target>

    <path id="compile.classpath">
        <fileset dir="${lib.dir}">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}/lib"/>

        <copy todir="${dist.dir}/lib">
            <fileset dir="${lib.dir}">
                <include name="*.jar"/>
            </fileset>
        </copy>

        <jar destfile="${dist.dir}/sample-app-${release.version}.jar">
            <fileset dir="${classes.dir}"/>

            <manifest>
                <attribute name="Main-Class"
                           value="com.example.app.Main"/>
                <attribute name="Class-Path"
                           value="lib/logging.jar lib/json-core.jar"/>

                <attribute name="Implementation-Title"
                           value="${application.title}"/>
                <attribute name="Implementation-Version"
                           value="${release.version}"/>
                <attribute name="Implementation-Vendor"
                           value="${vendor.name}"/>

                <attribute name="Specification-Version"
                           value="${specification.version}"/>
            </manifest>
        </jar>
    </target>
</project>
~~~

Trong ví dụ này, build giả định thư mục lib chỉ chứa đúng các thư viện được tham chiếu trong Class-Path. Nếu thư mục có thêm JAR khác, cần điều chỉnh fileset copy hoặc giá trị Class-Path để tránh phân phối thừa hoặc thiếu.

Cấu trúc đầu ra:

~~~text
dist/
├── sample-app-2.4.0.jar
└── lib/
    ├── logging.jar
    └── json-core.jar
~~~

Chạy ứng dụng:

~~~text
java -jar dist/sample-app-2.4.0.jar
~~~

Main-Class xác định lớp bắt đầu; Class-Path tìm hai JAR trong dist/lib; Implementation-Version cho biết phiên bản bản triển khai.

## 7. Tách manifest ra tệp riêng

Khi manifest có nhiều thuộc tính hoặc được nhiều buildfile dùng chung, có thể lưu nội dung manifest trong một tệp riêng rồi cung cấp cho task jar bằng thuộc tính manifest của task.

Ví dụ tệp **config/MANIFEST.MF**:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Sample Application
Implementation-Version: 2.4.0

~~~

Dùng trong Ant:

~~~xml
<jar destfile="dist/sample-app.jar"
     manifest="config/MANIFEST.MF">
    <fileset dir="build/classes"/>
</jar>
~~~

Cách này hữu ích khi manifest được duy trì độc lập với buildfile. Tuy nhiên, nếu giá trị thay đổi theo phiên bản hoặc môi trường, khai báo nested manifest với property expansion có thể dễ quản lý hơn.

Không đặt cùng một thuộc tính trùng lặp trong manifest file và nested manifest nếu không có chủ đích. Khi phải hợp nhất nhiều nguồn manifest, cần hiểu quy tắc merge của task jar để tránh kết quả không như mong muốn.

## 8. Manifest trùng lặp và merge manifest từ dependency

Một số JAR đầu vào có thể chứa sẵn META-INF/MANIFEST.MF. Khi task jar đưa nội dung từ FileSet hoặc resource collection vào JAR mới, cần quyết định cách xử lý manifest nguồn.

Task jar có thuộc tính filesetmanifest với các chế độ:

| Giá trị | Ý nghĩa |
|---|---|
| skip | Bỏ qua manifest trong các FileSet đầu vào; đây là hành vi mặc định |
| merge | Hợp nhất manifest của các JAR đầu vào vào manifest của JAR đích |
| mergewithoutmain | Hợp nhất các section khác nhưng không nhập main section của manifest nguồn |

Khi tạo JAR ứng dụng thông thường, giữ chế độ mặc định skip thường phù hợp vì manifest của JAR đầu ra do buildfile kiểm soát.

Nếu đóng gói lại nhiều JAR và cần giữ metadata theo package, có thể cân nhắc merge hoặc mergewithoutmain. Hãy kiểm tra các header bị trùng và nội dung section sau khi đóng gói; không nên mặc định rằng merge sẽ tạo ra một manifest có ngữ nghĩa đúng cho mọi dependency.

Việc merge manifest không phải cơ chế thay thế đầy đủ cho fat JAR/shaded JAR. Đóng gói tất cả lớp và tài nguyên từ nhiều thư viện vào một JAR có thể cần xử lý thêm file service, chữ ký, tài nguyên trùng tên và metadata của module.

## 9. Quy tắc định dạng manifest cần nhớ

### 9.1. Main section và package section

Main section nằm ở đầu tệp. Các thuộc tính như Main-Class, Class-Path và Implementation-Version thuộc phần này.

Package section bắt đầu bằng một dòng Name và được ngăn cách với section trước bằng dòng trống. Thuộc tính trong section chỉ áp dụng cho mục được nêu trong Name.

Không đặt Main-Class hoặc Class-Path trong package section nếu mục đích là cấu hình khởi chạy toàn bộ JAR.

### 9.2. Dòng dài và ký tự đặc biệt

Manifest có quy tắc giới hạn độ dài dòng vật lý. Khi một header dài, dòng tiếp theo phải là continuation line bắt đầu bằng một dấu cách. Ant tự xử lý việc ghi và xuống dòng khi dùng phần tử manifest; không nên tự chèn ngắt dòng tùy tiện vào giá trị attribute.

Ví dụ Class-Path có nhiều dependency nên được truyền thành một giá trị duy nhất trong Ant:

~~~xml
<attribute name="Class-Path"
           value="lib/alpha.jar lib/beta.jar lib/gamma.jar"/>
~~~

Ant ghi manifest theo định dạng phù hợp. Nếu tự tạo tệp MANIFEST.MF, cần tuân thủ quy tắc continuation line và encoding của manifest.

### 9.3. Dòng trống kết thúc section

Manifest dùng dòng trống để phân tách main section và các named section. Khi tự viết manifest file, hãy giữ dòng trống ở cuối mỗi section. Khi dùng nested manifest của Ant, để task xử lý định dạng.

### 9.4. Header names và values

Tên header không được tùy ý chứa dấu cách. Dùng tên thuộc tính theo chuẩn manifest như Main-Class, Class-Path, Implementation-Version hoặc tên custom phù hợp quy tắc.

Giá trị cần được ghi dưới dạng văn bản. Nếu property mở rộng thành chuỗi rỗng hoặc chưa được thiết lập, manifest có thể thiếu metadata cần thiết. Hãy cung cấp giá trị phiên bản rõ ràng trước khi đóng gói.

## 10. Kiểm tra manifest sau khi tạo JAR

Sau khi chạy target package, hãy kiểm tra nội dung JAR và manifest thay vì chỉ dựa vào việc task kết thúc thành công.

### 10.1. Liệt kê nội dung JAR

Dùng công cụ jar của JDK:

~~~text
jar tf dist/sample-app-2.4.0.jar
~~~

Kiểm tra có META-INF/MANIFEST.MF, lớp Main và các tài nguyên cần thiết hay không.

### 10.2. Đọc manifest

Có thể giải nén riêng manifest vào thư mục tạm:

~~~text
jar xf dist/sample-app-2.4.0.jar META-INF/MANIFEST.MF
~~~

Sau đó mở tệp META-INF/MANIFEST.MF để xem Main-Class, Class-Path và các thuộc tính phiên bản.

Khi chạy lệnh jar xf, hãy thực hiện trong thư mục tạm để tránh ghi đè một tệp META-INF có sẵn trong workspace.

### 10.3. Chạy thử executable JAR

~~~text
java -jar dist/sample-app-2.4.0.jar
~~~

Nếu Main-Class đúng và các dependency được đặt đúng vị trí, ứng dụng có thể khởi chạy.

Một số lỗi thường gặp:

- No main manifest attribute: manifest không có Main-Class.
- Could not find or load main class: tên Main-Class sai hoặc lớp không có trong JAR/classpath.
- NoClassDefFoundError: thiếu thư viện hoặc Class-Path trỏ sai.
- ClassNotFoundException: runtime không tìm được lớp được yêu cầu.
- UnsupportedClassVersionError: JAR được biên dịch bằng phiên bản Java mới hơn runtime đang dùng.

Kiểm tra manifest và cấu trúc thư mục dist để xác định nguyên nhân.

## 11. Những lỗi thường gặp khi cấu hình manifest

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| java -jar báo không có main manifest attribute | Thiếu Main-Class | Thêm Main-Class vào main section |
| Không tìm thấy lớp chính | Sai package, tên lớp hoặc lớp không được đóng gói | Kiểm tra class file và tên đầy đủ |
| Ứng dụng thiếu thư viện lúc chạy | Class-Path sai hoặc JAR phụ thuộc chưa được phân phối | Đối chiếu URL tương đối với cấu trúc dist |
| Dùng dấu ; hoặc : trong Class-Path | Nhầm với classpath của dòng lệnh | Dùng dấu cách để phân cách URL |
| Thư viện có trong thư mục lib nhưng không được nạp | Class-Path không trỏ đúng vị trí tương đối | Tính đường dẫn từ thư mục chứa JAR chính |
| Thêm Class-Path nhưng javac vẫn báo thiếu package | Nhầm manifest runtime classpath với compile classpath | Khai báo classpath riêng cho javac |
| Version trong tên JAR khác manifest | Hai giá trị được viết ở nhiều nơi | Dùng chung property release.version |
| Metadata phiên bản bị rỗng | Property chưa được nạp hoặc tên property sai | Kiểm tra file properties và thứ tự khai báo |
| Manifest có header trùng | Merge nhiều nguồn manifest hoặc khai báo trùng | Kiểm tra filesetmanifest và nguồn manifest |
| JAR chạy được trên máy build nhưng lỗi ở máy khác | Class-Path tham chiếu đường dẫn cục bộ hoặc dependency không được phân phối | Dùng cấu trúc tương đối nằm trong gói phân phối |
| Manifest tự viết bị lỗi khi đọc | Sai quy tắc dòng dài, continuation hoặc section | Dùng nested manifest của Ant hoặc tuân thủ định dạng chuẩn |

## 12. Thực hành tốt

- Dùng Main-Class bằng tên đầy đủ của lớp, không kèm .class.
- Chỉ khai báo Main-Class cho JAR thực sự có thể chạy như ứng dụng.
- Giữ Class-Path tương đối với vị trí JAR chính để gói phân phối có thể di chuyển.
- Dùng dấu cách giữa các URL trong Class-Path, không dùng dấu phân cách của hệ điều hành.
- Không dùng wildcard trong Class-Path của manifest.
- Copy dependency vào đúng cấu trúc thư mục mà Class-Path tham chiếu.
- Khai báo compile classpath riêng; manifest Class-Path không phục vụ bước javac.
- Quản lý Implementation-Version và tên JAR từ cùng một property.
- Phân biệt phiên bản triển khai với phiên bản đặc tả.
- Chỉ ghi build number hoặc revision khi có dữ liệu đáng tin cậy.
- Dùng package section cho metadata áp dụng riêng cho package.
- Giữ mặc định filesetmanifest=skip trừ khi thực sự cần hợp nhất manifest nguồn.
- Kiểm tra META-INF/MANIFEST.MF sau khi tạo JAR.
- Chạy thử bằng java -jar trong cấu trúc thư mục phân phối thực tế.
- Không dùng đường dẫn tuyệt đối gắn với máy build trong manifest của artifact cần phân phối.

## 13. Tự kiểm tra trước khi phát hành JAR

Trước khi đưa artifact vào bản phát hành, hãy trả lời:

1. JAR là thư viện hay executable JAR? Có thực sự cần Main-Class không?
2. Main-Class có đúng tên đầy đủ và lớp đã được đóng gói chưa?
3. Lớp chính có phương thức main hợp lệ không?
4. Class-Path có chứa đủ dependency runtime không?
5. Các đường dẫn Class-Path có tương đối với vị trí JAR chính không?
6. Các JAR phụ thuộc có được copy vào đúng thư mục phân phối không?
7. Có nhầm manifest Class-Path với classpath của javac không?
8. Implementation-Version có khớp tên file artifact không?
9. Specification-Version có mô tả đúng phiên bản API/đặc tả không?
10. Có cần package section hoặc Sealed cho package nào không?
11. Có manifest nguồn từ dependency cần merge không, và chế độ filesetmanifest đã đúng chưa?
12. Đã đọc lại META-INF/MANIFEST.MF và chạy thử bằng java -jar chưa?

Manifest là hợp đồng metadata giữa bước đóng gói và môi trường sử dụng JAR. Main-Class xác định điểm vào, Class-Path mô tả dependency runtime bên ngoài và các thuộc tính phiên bản cho biết artifact thuộc bản triển khai hoặc đặc tả nào. Khi các giá trị này được quản lý bằng property và kiểm tra sau đóng gói, JAR sẽ dễ chạy, dễ phân phối và dễ truy vết hơn.

## Tài liệu tham khảo

- [Apache Ant — Jar Task](https://ant.apache.org/manual/Tasks/jar.html)
- [Java JAR File Specification — Manifest](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
- [Java Launcher — java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)


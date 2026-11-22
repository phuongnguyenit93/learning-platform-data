# Gộp thư viện vào JAR và xử lý tài nguyên trùng, service descriptor, chữ ký

Một ứng dụng Java có thể phụ thuộc vào nhiều thư viện JAR. Khi phát hành, đôi khi cần gom class của ứng dụng và class của các dependency vào một file duy nhất, thường gọi là **fat JAR** hoặc **uber JAR**. Người dùng khi đó có thể chạy ứng dụng bằng một artifact thay vì phải tự chuẩn bị cả thư mục thư viện.

Việc gộp JAR không chỉ là giải nén mọi dependency rồi nén lại. Các JAR có thể chứa file trùng tên, cấu hình cần hợp nhất, service descriptor cần nối nội dung, manifest riêng và metadata chữ ký. Nếu xử lý không đúng, ứng dụng có thể mất provider của `ServiceLoader`, nạp nhầm resource, không khởi động được hoặc báo lỗi chữ ký.

Apache Ant cung cấp task `<jar>`, `<zipgroupfileset>`, `<unzip>`, `<copy>` và `<concat>` để xây dựng quy trình đóng gói. Với những quy tắc đặc thù, cần bổ sung task hoặc script xử lý resource trước khi tạo archive cuối cùng.

## 1. Fat JAR hoạt động như thế nào?

Thông thường, một ứng dụng được phân phối theo cấu trúc:

```text
app/
├── app.jar
└── lib/
    ├── codec-api.jar
    ├── codec-json.jar
    └── logging.jar
```

JVM cần cả `app.jar` và các thư viện trong classpath. Với fat JAR, nội dung của những thư viện cần thiết được đưa vào cùng archive:

```text
app-all.jar
├── com/example/app/Main.class
├── com/example/codec/Codec.class
├── com/example/codec/json/JsonCodec.class
└── org/example/logging/Logger.class
```

Khi chạy bằng `java -jar app-all.jar`, JVM tìm lớp chính qua manifest và các class/dependency đều nằm trong cùng archive.

Fat JAR phù hợp với ứng dụng cần phân phối đơn giản, chạy trong container hoặc triển khai qua một bước CI/CD. Tuy nhiên, không phải thư viện nào cũng có thể ghép một cách an toàn. Một số thư viện phụ thuộc vào resource, service provider, native library, package sealing hoặc metadata riêng.

## 2. Những loại nội dung có thể xuất hiện trong dependency JAR

Một JAR không chỉ có file `.class`. Khi giải nén, có thể gặp:

| Nội dung | Ví dụ | Cách xử lý khi gộp |
|---|---|---|
| Class | `com/example/Codec.class` | Giữ class; phát hiện xung đột tên class |
| Resource | `config/defaults.properties` | Chọn bản có chủ đích hoặc hợp nhất theo định dạng |
| Service descriptor | `META-INF/services/com.example.spi.Codec` | Nối danh sách provider từ các dependency |
| Manifest | `META-INF/MANIFEST.MF` | Tạo manifest mới cho fat JAR |
| Chữ ký JAR | `META-INF/DEPENDENCY.SF`, `.RSA`, `.DSA`, `.EC` | Loại chữ ký cũ vì nội dung archive đã thay đổi; ký lại nếu cần |
| JAR index | `META-INF/INDEX.LIST` | Thường loại bỏ vì index cũ không còn đúng với archive mới |
| License/notice | `META-INF/LICENSE`, `META-INF/NOTICE` | Giữ lại; hợp nhất hoặc đổi tên khi trùng |
| Module descriptor | `module-info.class` | Xử lý riêng; fat JAR thường được dùng trên classpath |
| Multi-release entries | `META-INF/versions/9/...` | Giữ đúng cấu trúc và manifest `Multi-Release: true` nếu cần |

Trước khi gộp, nên biết dependency nào chứa resource đặc biệt. Không nên mặc định rằng tất cả file trong `META-INF` đều có thể xóa; license, notice và một số cấu hình runtime cần được giữ lại.

## 3. Cách nhanh bằng zipgroupfileset

Ant có nested element `<zipgroupfileset>` để đưa nội dung của nhiều archive vào archive đích. Ví dụ đơn giản:

```xml
<target name="fat-jar-simple">
    <jar destfile="dist/app-all.jar">
        <fileset dir="build/classes">
            <include name="**/*"/>
        </fileset>
        <zipgroupfileset dir="lib">
            <include name="*.jar"/>
        </zipgroupfileset>
        <manifest>
            <attribute name="Main-Class" value="com.example.app.Main"/>
        </manifest>
    </jar>
</target>
```

`fileset` thêm nội dung ứng dụng đã biên dịch. `zipgroupfileset` chọn các JAR trong thư mục `lib` và đưa nội dung bên trong chúng vào archive đích. `manifest` khai báo lớp chính để chạy bằng `java -jar`.

Đây là cách gọn khi các dependency đã được chuẩn bị, không có xung đột resource cần xử lý và không cần biến đổi metadata bên trong từng JAR. Nó không tự hiểu cách hợp nhất mọi resource đặc biệt. Nếu nhiều JAR cùng chứa `META-INF/services/...`, file cấu hình hoặc chữ ký, chỉ gom archive có thể tạo kết quả không mong muốn.

Khi cần loại chữ ký, lọc manifest, hợp nhất service descriptor hoặc kiểm soát xung đột, nên giải nén dependency vào các thư mục riêng trước khi đóng gói. Cách này cho phép chọn chính xác nội dung nào được đưa vào JAR cuối.

## 4. Hiểu xung đột entry trong JAR

JAR là ZIP archive. Mỗi file bên trong có một entry name, ví dụ `com/example/Codec.class` hoặc `META-INF/services/com.example.spi.Codec`. Hai dependency có thể cùng chứa một entry name.

Ví dụ:

```text
codec-json.jar
└── META-INF/services/com.example.spi.Codec

codec-xml.jar
└── META-INF/services/com.example.spi.Codec
```

Hai file có cùng đường dẫn nhưng nội dung khác nhau. Nếu chỉ gộp archive, một số công cụ có thể giữ cả hai entry, bỏ một entry hoặc báo lỗi tùy chính sách xử lý duplicate. Việc có nhiều entry cùng tên trong một ZIP không phải cách đáng tin cậy để biểu diễn dữ liệu cần hợp nhất.

Task ZIP/JAR của Ant có thuộc tính `duplicate` với các lựa chọn thường dùng:

| Giá trị | Hành vi |
|---|---|
| `add` | Thêm entry trùng vào archive; đây là hành vi mặc định của task ZIP |
| `preserve` | Giữ entry đã có và bỏ qua entry trùng tiếp theo |
| `fail` | Báo lỗi khi gặp entry trùng |

Với fat JAR, `duplicate="fail"` thường là chính sách an toàn để phát hiện xung đột chưa được giải quyết. Nó khiến build báo lỗi thay vì âm thầm tạo archive có nội dung khó đoán.

Không nên chọn `preserve` như một cách giải quyết chung. Nó chỉ chọn một bản theo thứ tự xử lý, không biết bản nào đúng theo ngữ nghĩa của ứng dụng. Cũng không nên để nhiều bản class cùng tên rồi hy vọng JVM chọn đúng.

## 5. Phân loại duplicate trước khi đóng gói

Không phải mọi entry trùng đều cần xử lý giống nhau:

1. **Class trùng tên:** thường là xung đột dependency hoặc nhiều phiên bản của cùng thư viện. Cần loại bỏ một dependency hoặc giải quyết phiên bản; không nên ghi đè class tùy tiện.
2. **Resource cấu hình:** có thể cần chọn một nguồn ưu tiên hoặc hợp nhất theo định dạng, chẳng hạn properties, YAML hay HOCON.
3. **Service descriptor:** cần hợp nhất danh sách provider thay vì chỉ giữ một file.
4. **License/notice:** cần giữ thông tin của tất cả thư viện, có thể đặt thành các file riêng hoặc tạo bản tổng hợp.
5. **Manifest, signature và index:** cần loại bỏ metadata của JAR thành phần và tạo metadata phù hợp cho archive cuối.

Đặt `duplicate="fail"` trong bước tạo archive cuối để những xung đột chưa có chính sách rõ ràng được phát hiện. Với những entry đã được xử lý, loại chúng khỏi fileset nguồn và thêm bản kết quả đã hợp nhất.

## 6. Giải nén dependency vào thư mục riêng

Giải nén mỗi dependency vào một thư mục khác nhau giúp giữ lại nguồn gốc của file và tránh ghi đè ngay trong lúc chuẩn bị:

```xml
<property name="unpack.dir" location="${basedir}/build/unpacked"/>

<target name="unpack-dependencies">
    <delete dir="${unpack.dir}"/>
    <mkdir dir="${unpack.dir}/codec-api"/>
    <mkdir dir="${unpack.dir}/codec-json"/>
    <mkdir dir="${unpack.dir}/codec-xml"/>

    <unzip src="lib/codec-api.jar" dest="${unpack.dir}/codec-api"/>
    <unzip src="lib/codec-json.jar" dest="${unpack.dir}/codec-json"/>
    <unzip src="lib/codec-xml.jar" dest="${unpack.dir}/codec-xml"/>
</target>
```

Sau target này, nội dung từng JAR nằm trong thư mục riêng:

```text
build/unpacked/
├── codec-api/
├── codec-json/
└── codec-xml/
```

Không giải nén tất cả dependency vào cùng một thư mục nếu chưa có quy tắc duplicate. Làm như vậy có thể khiến file cùng tên ghi đè lẫn nhau trước khi bước tạo JAR có cơ hội phát hiện xung đột.

## 7. Loại manifest, chữ ký và index cũ

Mỗi dependency có thể chứa manifest riêng tại `META-INF/MANIFEST.MF`. Khi gộp nhiều JAR, không nên đưa nguyên manifest của từng dependency vào archive cuối. Fat JAR cần một manifest mới do build chính quản lý.

Chữ ký của JAR thành phần cũng không còn hợp lệ sau khi các entry được lấy ra và đóng gói vào archive khác. Những file chữ ký thường nằm trong `META-INF`:

```text
META-INF/DEPENDENCY.SF
META-INF/DEPENDENCY.RSA
META-INF/DEPENDENCY.DSA
META-INF/DEPENDENCY.EC
META-INF/SIG-ABC
```

Chữ ký được tính trên nội dung entry của JAR đã ký. Khi gộp, thay đổi manifest hoặc hợp nhất resource, nội dung archive không còn khớp với chữ ký cũ. Vì vậy phải loại các file chữ ký của dependency. Nếu cần phân phối artifact có chữ ký, hãy ký lại fat JAR sau khi tạo xong.

`META-INF/INDEX.LIST` là index của archive cũ. Sau khi gộp thêm hoặc bỏ entry, index có thể không còn chính xác, vì vậy thường nên loại bỏ và để công cụ tạo archive cuối không mang index cũ.

Fileset có thể loại các entry này:

```xml
<fileset dir="build/unpacked/codec-json" casesensitive="false">
    <exclude name="META-INF/MANIFEST.MF"/>
    <exclude name="META-INF/INDEX.LIST"/>
    <exclude name="META-INF/*.SF"/>
    <exclude name="META-INF/*.RSA"/>
    <exclude name="META-INF/*.DSA"/>
    <exclude name="META-INF/*.EC"/>
    <exclude name="META-INF/SIG-*"/>
</fileset>
```

Đặt `casesensitive="false"` để quy tắc loại bỏ không phụ thuộc chữ hoa/chữ thường trong tên entry. Áp dụng cùng nhóm exclude cho từng dependency. Không loại toàn bộ `META-INF/**`, vì có thể làm mất service descriptor, license, notice hoặc cấu hình mà ứng dụng cần.

## 8. Hợp nhất service descriptor trong META-INF/services

Java Service Provider Interface (SPI) cho phép một thư viện cung cấp implementation cho interface hoặc abstract service. Provider được đăng ký bằng file văn bản có tên là binary name của service, nằm trong:

```text
META-INF/services/<fully.qualified.ServiceName>
```

Ví dụ service `com.example.spi.Codec` có hai provider:

```text
# codec-json.jar
META-INF/services/com.example.spi.Codec
```

Nội dung:

```text
com.example.codec.json.JsonCodec
```

Trong `codec-xml.jar`, cùng file có thể chứa:

```text
com.example.codec.xml.XmlCodec
```

Nếu fat JAR chỉ giữ một trong hai file, một provider sẽ biến mất khỏi danh sách đăng ký. Khi ứng dụng gọi `ServiceLoader.load(Codec.class)`, provider bị mất sẽ không được phát hiện.

### 8.1. Quy tắc hợp nhất

Đối với service descriptor dạng dòng:

- Giữ tất cả provider hợp lệ từ các dependency và từ chính ứng dụng.
- Giữ comment nếu muốn bảo toàn thông tin nguồn; dòng bắt đầu bằng `#` là comment theo định dạng provider configuration.
- Đảm bảo mỗi provider nằm trên một dòng riêng.
- Tránh tạo file rỗng nếu không có dependency nào đăng ký service đó.
- Nếu cần loại dòng trùng, thực hiện deduplicate theo tên provider trước khi đóng gói.

Task `<concat>` của Ant có thể nối các file descriptor đã giải nén thành một file duy nhất. Nó không tự hiểu cú pháp SPI và không tự loại provider trùng; việc kiểm tra hoặc deduplicate cần một bước riêng nếu dự án yêu cầu.

### 8.2. Ví dụ nối descriptor đã biết

Giả sử ba nguồn `codec-api`, `codec-json`, `codec-xml` và ứng dụng đều có thể đăng ký `com.example.spi.Codec`. Tạo thư mục chứa kết quả hợp nhất:

```xml
<property name="services.dir" location="${basedir}/build/merged-services"/>

<target name="merge-codec-service" depends="unpack-dependencies">
    <mkdir dir="${services.dir}/META-INF/services"/>

    <concat destfile="${services.dir}/META-INF/services/com.example.spi.Codec"
            encoding="UTF-8"
            outputencoding="UTF-8"
            fixlastline="true">
        <fileset dir="${unpack.dir}/codec-api/META-INF/services"
                 erroronmissingdir="false">
            <include name="com.example.spi.Codec"/>
        </fileset>
        <fileset dir="${unpack.dir}/codec-json/META-INF/services"
                 erroronmissingdir="false">
            <include name="com.example.spi.Codec"/>
        </fileset>
        <fileset dir="${unpack.dir}/codec-xml/META-INF/services"
                 erroronmissingdir="false">
            <include name="com.example.spi.Codec"/>
        </fileset>
        <fileset dir="${classes.dir}/META-INF/services"
                 erroronmissingdir="false">
            <include name="com.example.spi.Codec"/>
        </fileset>
    </concat>
</target>
```

`fixlastline="true"` giúp bảo đảm nội dung của mỗi nguồn được ngăn cách đúng khi file trước đó không kết thúc bằng ký tự xuống dòng. `erroronmissingdir="false"` cho phép một dependency không có thư mục service descriptor mà không làm bước gom file thất bại. Ví dụ giả định có ít nhất một descriptor đầu vào cho service này.

Trong archive cuối, loại các file `META-INF/services/**` gốc khỏi fileset dependency và thêm thư mục kết quả hợp nhất:

```xml
<fileset dir="${unpack.dir}/codec-json">
    <exclude name="META-INF/services/**"/>
    <!-- Các exclude metadata khác được khai báo ở bước đóng gói. -->
</fileset>

<fileset dir="${services.dir}">
    <include name="META-INF/services/**"/>
</fileset>
```

Nếu dự án có nhiều service interface, tạo một file hợp nhất cho từng tên service. Có thể dùng script hoặc custom task để tìm mọi file trong `META-INF/services`, nhóm theo tên service và nối nội dung tự động. Ant core không cung cấp một transformer tổng quát hiểu và hợp nhất mọi descriptor theo ngữ nghĩa SPI.

## 9. Xử lý tài nguyên trùng ngoài service descriptor

Service descriptor chỉ là một trường hợp. Các thư viện có thể cùng cung cấp resource với cùng đường dẫn, nhưng cách hợp nhất phụ thuộc định dạng.

| Resource | Vấn đề | Hướng xử lý |
|---|---|---|
| `application.properties` | Nhiều thư viện có thể có cùng tên nhưng ý nghĩa khác nhau | Đổi tên/đặt vào namespace riêng hoặc chọn một nguồn rõ ràng |
| `META-INF/services/*` | Danh sách provider từ nhiều JAR | Nối nội dung theo từng service |
| `META-INF/spring.factories` | Nhiều dependency đăng ký cùng loại extension | Dùng transformer tương thích với phiên bản Spring; không chỉ chọn một file |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Danh sách auto-configuration của Spring Boot | Hợp nhất các dòng từ mọi dependency |
| `META-INF/native-image/**` | Metadata native-image có thể cần kết hợp theo cấu trúc | Dùng quy tắc merge riêng cho từng loại file |
| `reference.conf` | Cấu hình HOCON có quy tắc fallback/merge | Giữ hoặc hợp nhất theo cú pháp HOCON và thứ tự ưu tiên |
| `META-INF/LICENSE`, `META-INF/NOTICE` | Nhiều thư viện có thông báo bản quyền | Giữ riêng theo thư viện hoặc tạo bản tổng hợp đầy đủ |
| Class cùng tên | Hai dependency cung cấp cùng binary name | Giải quyết dependency/version; không âm thầm ghi đè |

Không có một chính sách `duplicate` nào đúng cho mọi resource. `preserve` chọn một entry; `add` có thể tạo nhiều entry cùng tên; `fail` phát hiện xung đột. Với resource có định dạng đặc biệt, cần transformer hiểu cấu trúc của nó.

### 9.1. Chọn một resource có chủ đích

Nếu hai thư viện có cùng một file cấu hình và dự án muốn chọn bản của dependency cụ thể, loại file đó khỏi fileset còn lại rồi thêm đúng bản được chọn. Ví dụ:

```xml
<fileset dir="${unpack.dir}/codec-api">
    <exclude name="config/codec-defaults.properties"/>
    <!-- Các exclude metadata khác. -->
</fileset>

<fileset dir="${unpack.dir}/codec-json">
    <include name="config/codec-defaults.properties"/>
    <!-- Các exclude metadata khác. -->
</fileset>
```

Đây là lựa chọn có chủ đích cho một đường dẫn đã biết. Không nên áp dụng quy tắc này cho class cùng tên hoặc cho một nhóm resource chưa hiểu rõ ý nghĩa.

### 9.2. Giữ license và notice

Không loại mọi file có tên `LICENSE` hoặc `NOTICE` chỉ để tránh duplicate. Thông tin bản quyền và license của dependency cần được bảo toàn theo nghĩa vụ phân phối của dự án.

Một cách rõ ràng là đặt mỗi file vào một đường dẫn riêng, ví dụ:

```text
META-INF/licenses/codec-api-LICENSE.txt
META-INF/licenses/codec-json-LICENSE.txt
META-INF/licenses/codec-xml-LICENSE.txt
```

Có thể dùng task `<copy>` để chuẩn bị các file này vào staging directory với tên đích riêng, rồi thêm staging directory vào JAR. Nếu tạo một `NOTICE` tổng hợp, hãy đảm bảo không bỏ sót thông tin của bất kỳ dependency nào.

## 10. Đóng gói với duplicate=fail sau khi đã xử lý xung đột

Khi dependency đã được giải nén riêng, service descriptor đã hợp nhất và các metadata cần loại đã được lọc, có thể tạo JAR cuối bằng nhiều fileset. `duplicate="fail"` giúp phát hiện những entry còn trùng ngoài các trường hợp đã chủ động xử lý.

Ví dụ khung đóng gói:

```xml
<target name="fat-jar" depends="merge-codec-service">
    <mkdir dir="dist"/>

    <jar destfile="dist/app-all.jar" duplicate="fail">
        <!-- Class và resource của ứng dụng. -->
        <fileset dir="build/classes" casesensitive="false">
            <exclude name="META-INF/MANIFEST.MF"/>
            <exclude name="META-INF/INDEX.LIST"/>
            <exclude name="META-INF/services/**"/>
            <exclude name="**/module-info.class"/>
        </fileset>

        <!-- Nội dung dependency thứ nhất. -->
        <fileset dir="build/unpacked/codec-api" casesensitive="false">
            <exclude name="META-INF/MANIFEST.MF"/>
            <exclude name="META-INF/INDEX.LIST"/>
            <exclude name="META-INF/*.SF"/>
            <exclude name="META-INF/*.RSA"/>
            <exclude name="META-INF/*.DSA"/>
            <exclude name="META-INF/*.EC"/>
            <exclude name="META-INF/SIG-*"/>
            <exclude name="META-INF/services/**"/>
            <exclude name="**/module-info.class"/>
        </fileset>

        <!-- Nội dung dependency thứ hai. -->
        <fileset dir="build/unpacked/codec-json" casesensitive="false">
            <exclude name="META-INF/MANIFEST.MF"/>
            <exclude name="META-INF/INDEX.LIST"/>
            <exclude name="META-INF/*.SF"/>
            <exclude name="META-INF/*.RSA"/>
            <exclude name="META-INF/*.DSA"/>
            <exclude name="META-INF/*.EC"/>
            <exclude name="META-INF/SIG-*"/>
            <exclude name="META-INF/services/**"/>
            <exclude name="**/module-info.class"/>
        </fileset>

        <!-- Service descriptor đã được nối thành một file. -->
        <fileset dir="build/merged-services">
            <include name="META-INF/services/**"/>
        </fileset>

        <manifest>
            <attribute name="Main-Class" value="com.example.app.Main"/>
        </manifest>
    </jar>
</target>
```

Đây là ví dụ minh họa cho hai dependency; thêm fileset tương tự cho các dependency còn lại. `duplicate="fail"` khiến build dừng nếu hai nguồn vẫn cung cấp cùng một entry name, kể cả class hoặc resource mà dự án chưa có chính sách giải quyết.

Trong ví dụ, `META-INF/services/**` bị loại khỏi các nguồn ban đầu để file đã hợp nhất là nguồn duy nhất. Manifest mới chỉ khai báo `Main-Class`; nếu ứng dụng cần thuộc tính manifest khác, hãy thêm chúng một cách có chủ đích.

## 11. Ví dụ build hoàn chỉnh với hai dependency và một service

Ví dụ dưới đây kết hợp compile ứng dụng, giải nén hai thư viện, hợp nhất service descriptor đã biết và tạo fat JAR. Giả định:

- `lib/codec-api.jar` và `lib/codec-json.jar` tồn tại.
- Cả hai dependency có thể chứa descriptor `com.example.spi.Codec`.
- `build/classes` chứa class ứng dụng và resource của ứng dụng.
- Lớp chính là `com.example.app.Main`.

```xml
<project name="fat-app" default="package" basedir=".">
    <property name="lib.dir" location="${basedir}/lib"/>
    <property name="classes.dir" location="${basedir}/build/classes"/>
    <property name="unpack.dir" location="${basedir}/build/unpacked"/>
    <property name="services.dir" location="${basedir}/build/merged-services"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <fileset dir="${lib.dir}">
                    <include name="*.jar"/>
                </fileset>
            </classpath>
        </javac>
        <copy todir="${classes.dir}">
            <fileset dir="src/main/resources">
                <include name="**/*"/>
            </fileset>
        </copy>
    </target>

    <target name="unpack-dependencies" depends="compile">
        <delete dir="${unpack.dir}"/>
        <mkdir dir="${unpack.dir}/codec-api"/>
        <mkdir dir="${unpack.dir}/codec-json"/>

        <unzip src="${lib.dir}/codec-api.jar"
               dest="${unpack.dir}/codec-api"/>
        <unzip src="${lib.dir}/codec-json.jar"
               dest="${unpack.dir}/codec-json"/>
    </target>

    <target name="merge-services" depends="unpack-dependencies">
        <delete dir="${services.dir}"/>
        <mkdir dir="${services.dir}/META-INF/services"/>

        <concat destfile="${services.dir}/META-INF/services/com.example.spi.Codec"
                encoding="UTF-8"
                outputencoding="UTF-8"
                fixlastline="true">
            <fileset dir="${unpack.dir}/codec-api/META-INF/services"
                     erroronmissingdir="false">
                <include name="com.example.spi.Codec"/>
            </fileset>
            <fileset dir="${unpack.dir}/codec-json/META-INF/services"
                     erroronmissingdir="false">
                <include name="com.example.spi.Codec"/>
            </fileset>
            <fileset dir="${classes.dir}/META-INF/services"
                     erroronmissingdir="false">
                <include name="com.example.spi.Codec"/>
            </fileset>
        </concat>
    </target>

    <target name="package" depends="merge-services">
        <jar destfile="${dist.dir}/app-all.jar" duplicate="fail">
            <fileset dir="${classes.dir}" casesensitive="false">
                <exclude name="META-INF/MANIFEST.MF"/>
                <exclude name="META-INF/INDEX.LIST"/>
                <exclude name="META-INF/services/**"/>
                <exclude name="**/module-info.class"/>
            </fileset>

            <fileset dir="${unpack.dir}/codec-api" casesensitive="false">
                <exclude name="META-INF/MANIFEST.MF"/>
                <exclude name="META-INF/INDEX.LIST"/>
                <exclude name="META-INF/*.SF"/>
                <exclude name="META-INF/*.RSA"/>
                <exclude name="META-INF/*.DSA"/>
                <exclude name="META-INF/*.EC"/>
                <exclude name="META-INF/SIG-*"/>
                <exclude name="META-INF/services/**"/>
                <exclude name="**/module-info.class"/>
            </fileset>

            <fileset dir="${unpack.dir}/codec-json" casesensitive="false">
                <exclude name="META-INF/MANIFEST.MF"/>
                <exclude name="META-INF/INDEX.LIST"/>
                <exclude name="META-INF/*.SF"/>
                <exclude name="META-INF/*.RSA"/>
                <exclude name="META-INF/*.DSA"/>
                <exclude name="META-INF/*.EC"/>
                <exclude name="META-INF/SIG-*"/>
                <exclude name="META-INF/services/**"/>
                <exclude name="**/module-info.class"/>
            </fileset>

            <fileset dir="${services.dir}">
                <include name="META-INF/services/**"/>
            </fileset>

            <manifest>
                <attribute name="Main-Class" value="com.example.app.Main"/>
            </manifest>
        </jar>
    </target>

    <target name="clean">
        <delete dir="${basedir}/build"/>
        <delete dir="${dist.dir}"/>
    </target>
</project>
```

Ví dụ giả định thư mục `src/main/resources` tồn tại. Nếu không có resource, bỏ bước copy. Nếu các dependency có thêm service interface khác, tạo một lần `<concat>` riêng cho từng descriptor hoặc dùng một transformer tổng quát. Nếu descriptor không tồn tại ở bất kỳ nguồn nào, không cần tạo file rỗng tương ứng.

`<concat>` nối nội dung, không tự loại dòng provider trùng. Nếu cùng provider xuất hiện nhiều lần và dự án muốn danh sách duy nhất, hãy thêm bước chuẩn hóa/deduplicate trước khi tạo archive.

## 12. Vì sao phải loại chữ ký cũ và ký lại fat JAR?

Khi một JAR được ký, công cụ ký tạo metadata trong `META-INF` để xác minh nội dung archive. Quá trình gộp thay đổi tập entry, có thể thay manifest, đổi resource hoặc hợp nhất file. Chữ ký của JAR thành phần không còn mô tả đúng nội dung fat JAR.

Do đó quy trình đúng là:

1. Giải nén dependency.
2. Loại manifest và file chữ ký của từng dependency khỏi tập nội dung được gộp.
3. Hợp nhất resource và tạo fat JAR cuối.
4. Nếu chính sách phát hành yêu cầu chữ ký, ký fat JAR cuối cùng bằng khóa phát hành của dự án.
5. Phát hành artifact và thông tin kiểm tra tương ứng.

Không nên giữ các file `.SF`, `.RSA`, `.DSA` hoặc `.EC` từ dependency trong fat JAR. Chúng không còn xác minh được archive mới và có thể làm JVM hoặc công cụ bảo mật báo lỗi chữ ký.

Nếu ứng dụng không yêu cầu ký JAR, vẫn phải loại chữ ký cũ. Nếu cần ký, dùng công cụ như `jarsigner` sau khi gộp:

```bash
jarsigner -keystore release-keystore.p12 \
          -storetype PKCS12 \
          dist/app-all.jar release-key
```

Đây chỉ là minh họa cú pháp. Quản lý khóa và mật khẩu phải dùng cơ chế secret an toàn của môi trường phát hành; không ghi mật khẩu trực tiếp vào `build.xml`, dòng lệnh được lưu log hoặc repository.

## 13. Manifest của fat JAR

JAR chạy bằng `java -jar` cần manifest khai báo lớp chính:

```xml
<manifest>
    <attribute name="Main-Class" value="com.example.app.Main"/>
</manifest>
```

Không sao chép nguyên manifest của các dependency vào fat JAR. Manifest thành phần có thể chứa `Main-Class`, `Class-Path`, package sealing hoặc thuộc tính riêng của thư viện. Fat JAR cần manifest được tạo theo ứng dụng phát hành.

Nếu fat JAR chứa các entry từ multi-release JAR, cần giữ đúng cấu trúc `META-INF/versions/<n>/...` và đặt thuộc tính:

```xml
<attribute name="Multi-Release" value="true"/>
```

Chỉ đặt `Multi-Release: true` khi archive cuối thực sự chứa các phiên bản class/resource theo cấu trúc multi-release hợp lệ. Không đặt chỉ vì một dependency có manifest ghi thuộc tính này mà các entry tương ứng đã bị loại.

Các manifest section theo package, ví dụ `Sealed: true`, cũng cần xem xét riêng. Gộp nhiều thư viện có thể làm thay đổi ranh giới package và ảnh hưởng package sealing. Không mang nguyên các section của dependency vào manifest mới nếu chưa xác định chúng còn hợp lệ.

## 14. Module descriptor và giới hạn của fat JAR

Một thư viện modular có thể chứa `module-info.class`. Khi ghép nhiều module thành một JAR, không thể giữ đồng thời nhiều module descriptor ở cùng vị trí. Fat JAR truyền thống thường được dùng trên classpath và không đại diện cho một module JPMS hợp nhất.

Ví dụ trong fileset đóng gói loại:

```xml
<exclude name="**/module-info.class"/>
```

Mẫu này cũng loại module descriptor nằm trong cây `META-INF/versions` nếu có. Nếu cần chạy trên module path, phải thiết kế module descriptor mới cho ứng dụng hợp nhất và kiểm tra các yêu cầu encapsulation, package export, service use/provide cùng dependency. Đây là một bài toán modularization riêng, không chỉ là gộp file.

## 15. Kiểm tra fat JAR sau khi tạo

Không nên chỉ kiểm tra rằng file JAR tồn tại. Cần xác nhận archive có class ứng dụng, dependency, manifest và service descriptor cần thiết.

Liệt kê nội dung:

```bash
jar tf dist/app-all.jar
```

Kiểm tra manifest:

```bash
jar xf dist/app-all.jar META-INF/MANIFEST.MF
```

Mở `META-INF/MANIFEST.MF` và xác nhận `Main-Class` đúng. Khi chạy trong thư mục thử nghiệm, kiểm tra:

```bash
java -jar dist/app-all.jar
```

Nếu ứng dụng dùng SPI, thêm một test tích hợp gọi `ServiceLoader`:

```java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
for (Codec codec : codecs) {
    System.out.println(codec.getClass().getName());
}
```

Kết quả cần liệt kê tất cả provider dự kiến. Nếu chỉ có một provider, kiểm tra nội dung `META-INF/services/com.example.spi.Codec` trong fat JAR.

Nếu JAR được ký lại, kiểm tra chữ ký bằng:

```bash
jarsigner -verify -verbose -certs dist/app-all.jar
```

Nếu không ký artifact, không nên còn các file chữ ký cũ từ dependency. Có thể liệt kê `META-INF` trong JAR để xác nhận.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `java -jar` không tìm thấy main class | Manifest thiếu hoặc sai `Main-Class` | Tạo manifest mới cho fat JAR |
| Một provider SPI biến mất | Chỉ giữ một `META-INF/services` trùng tên | Hợp nhất descriptor từ tất cả dependency và ứng dụng |
| JVM báo lỗi chữ ký | Giữ file `.SF`, `.RSA`, `.DSA` hoặc `.EC` cũ | Loại chữ ký dependency; ký lại fat JAR nếu cần |
| Archive có nhiều entry cùng tên | Dùng chính sách `add` hoặc chưa xử lý duplicate | Dùng `duplicate="fail"` để phát hiện và xử lý từng xung đột |
| Resource cấu hình bị mất | `preserve` giữ nhầm bản hoặc một file ghi đè file khác | Xác định nguồn ưu tiên hoặc merge theo định dạng |
| Build fail do LICENSE/NOTICE trùng | Nhiều dependency dùng cùng đường dẫn metadata | Đổi tên/đặt riêng hoặc tạo notice tổng hợp, vẫn giữ nội dung cần thiết |
| JAR có `INDEX.LIST` không đúng | Mang index từ dependency vào archive mới | Loại index cũ và tạo lại nếu thực sự cần |
| Ứng dụng modular không chạy trên module path | Nhiều `module-info.class` không thể gộp nguyên trạng | Thiết kế module descriptor mới hoặc phát hành modular artifacts riêng |
| Spring/Log4j plugin không được phát hiện | Resource metadata đặc thù bị ghi đè | Dùng transformer phù hợp với framework và phiên bản |

## 17. Bài tập thực hành

1. Tạo hai thư viện JAR nhỏ, mỗi thư viện có một class và một resource cấu hình cùng đường dẫn.
2. Dùng `<unzip>` giải nén mỗi dependency vào thư mục riêng.
3. Tạo fat JAR bằng các fileset và bật `duplicate="fail"`; quan sát build phát hiện resource trùng.
4. Quyết định resource nào được giữ hoặc tạo quy tắc merge phù hợp, rồi chạy lại.
5. Tạo hai provider cho cùng một service interface và thêm descriptor `META-INF/services` vào mỗi JAR.
6. Dùng `<concat>` tạo descriptor hợp nhất, đóng gói lại và kiểm tra bằng `ServiceLoader`.
7. Thêm file chữ ký giả lập hoặc kiểm tra một dependency đã ký; bảo đảm các signature metadata không được đưa vào fat JAR.
8. Tạo manifest mới có `Main-Class` và chạy bằng `java -jar`.
9. Thêm một resource trùng khác như `META-INF/NOTICE`, sau đó lưu nội dung của cả hai thư viện theo quy tắc riêng.
10. Kiểm tra nội dung cuối bằng `jar tf`, test SPI và chạy ứng dụng trong môi trường gần với production.

## 18. Nguyên tắc thiết kế quy trình gộp JAR

Hãy giữ dependency ở các thư mục giải nén riêng cho đến khi đã quyết định cách xử lý từng loại entry. Loại manifest, signature và index cũ; tạo manifest mới cho ứng dụng. Hợp nhất service descriptor theo từng service interface. Với resource khác, chọn hoặc biến đổi theo định dạng thay vì dựa vào thứ tự ghi file. Giữ license/notice và dùng `duplicate="fail"` để phát hiện xung đột còn sót.

Fat JAR chỉ đáng tin cậy khi nội dung bên trong được hợp nhất theo đúng ngữ nghĩa của từng loại file. Một archive tạo thành công chưa chắc đã chạy đúng; cần kiểm tra manifest, SPI, resource, chữ ký và hành vi runtime trước khi phát hành.

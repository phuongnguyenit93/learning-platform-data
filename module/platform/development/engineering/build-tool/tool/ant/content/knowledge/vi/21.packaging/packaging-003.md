# Ghép hoặc cập nhật manifest bằng task `manifest`

Manifest là tệp metadata nằm bên trong gói JAR, thường có đường dẫn `META-INF/MANIFEST.MF`. Nó mô tả thông tin về JAR như phiên bản manifest, lớp khởi chạy, classpath runtime, phiên bản sản phẩm, nhà cung cấp hoặc metadata riêng của từng package. Apache Ant cung cấp task `<manifest>` để tạo, ghép hoặc cập nhật một manifest độc lập; task đóng gói như `<jar>` cũng hỗ trợ phần tử `<manifest>` lồng để ghi metadata trực tiếp vào JAR.

Khi build cần duy trì một manifest đã có, task `manifest` cho phép thêm hoặc thay đổi các thuộc tính mà không phải tự đọc rồi ghi lại toàn bộ tệp bằng script. Chế độ `update` giữ những mục hiện có và cập nhật các mục được khai báo; chế độ `replace` tạo nội dung mới từ cấu hình hiện tại. Hiểu rõ hai chế độ này giúp tránh vô tình xóa metadata đang được công cụ phát hành hoặc ứng dụng sử dụng.

## 1. Manifest trong gói JAR

Manifest là tệp văn bản theo định dạng Java Manifest. Trong một JAR, vị trí chuẩn là:

```text
META-INF/MANIFEST.MF
```

Manifest gồm các header dạng `Tên: Giá trị`, được nhóm thành phần chính (main section) và có thể có các section riêng cho từng entry trong JAR.

Ví dụ đơn giản:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Inventory Application
Implementation-Version: 2.4.0
```

Các header thường gặp:

| Header | Mục đích |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest; thường là `1.0` |
| `Main-Class` | Tên đầy đủ của lớp có phương thức `public static void main(String[] args)` để chạy JAR bằng `java -jar` |
| `Class-Path` | Danh sách URL/đường dẫn tương đối đến thư viện phụ thuộc mà launcher dùng khi chạy JAR |
| `Implementation-Title` | Tên sản phẩm hoặc thành phần được đóng gói |
| `Implementation-Version` | Phiên bản triển khai của sản phẩm |
| `Implementation-Vendor` | Nhà cung cấp hoặc tổ chức phát hành |
| `Specification-Title` | Tên đặc tả mà package hoặc sản phẩm tuân theo |
| `Specification-Version` | Phiên bản đặc tả |
| `Created-By` | Công cụ hoặc môi trường tạo manifest; Ant/JDK có thể tự bổ sung tùy cách đóng gói |

Tên header không phân biệt chữ hoa và chữ thường theo định dạng manifest, nhưng nên giữ cách viết chuẩn để dễ đọc và tương thích với công cụ khác. Giá trị được ghi sau dấu hai chấm và một dấu cách.

### 1.1. Main section và named section

Main section nằm ở đầu manifest. Các header như `Manifest-Version`, `Main-Class` và `Class-Path` thường thuộc phần này.

Sau main section, manifest có thể chứa các section riêng. Mỗi section bắt đầu bằng header `Name`, chỉ định tên entry hoặc đường dẫn trong JAR, sau đó là các header áp dụng cho entry đó.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

Name: com/example/app/
Specification-Title: Inventory API
Specification-Version: 2.0
```

Trong ví dụ, `Main-Class` thuộc main section; `Specification-Title` và `Specification-Version` thuộc section dành cho package `com/example/app/`.

Trong Ant, named section được biểu diễn bằng phần tử `<section name="...">` và các `<attribute>` lồng bên trong.

## 2. Tạo manifest bằng task `manifest`

Task `<manifest>` tạo tệp manifest tại đường dẫn được chỉ định bởi thuộc tính `file`. Các header được khai báo bằng nested `<attribute>`, còn metadata theo từng entry được khai báo bằng `<section>`.

Ví dụ tạo manifest cho ứng dụng:

```xml
<target name="create-manifest">
    <manifest file="build/MANIFEST.MF" mode="replace">
        <attribute name="Manifest-Version" value="1.0"/>
        <attribute name="Main-Class" value="com.example.app.Main"/>
        <attribute name="Implementation-Title" value="Inventory Application"/>
        <attribute name="Implementation-Version" value="2.4.0"/>
        <attribute name="Implementation-Vendor" value="Example Company"/>

        <section name="com/example/app/">
            <attribute name="Specification-Title" value="Inventory API"/>
            <attribute name="Specification-Version" value="2.0"/>
        </section>
    </manifest>
</target>
```

Khi target chạy, Ant ghi manifest vào `build/MANIFEST.MF`. Phần tử `<attribute>` ở cấp trực tiếp thuộc main section. Các attribute nằm trong `<section>` thuộc section tương ứng.

Thuộc tính `file` là đường dẫn tệp manifest được tạo hoặc cập nhật. Nên đặt tệp trung gian dưới thư mục build để có thể tái tạo từ cấu hình và xóa bằng target `clean`.

### 2.1. Thuộc tính `mode`

Task `manifest` hỗ trợ hai chế độ chính:

| `mode` | Hành vi |
|---|---|
| `update` | Ghép các header và section được khai báo với nội dung manifest hiện có; header được khai báo lại sẽ nhận giá trị cập nhật, còn các mục khác được giữ lại |
| `replace` | Thay nội dung manifest đích bằng nội dung được mô tả trong task; các mục cũ không được khai báo lại sẽ bị loại bỏ |

Nếu không chỉ định `mode`, task sử dụng chế độ cập nhật theo mặc định. Dù vậy, nên ghi `mode` tường minh trong build file khi hành vi ghi manifest ảnh hưởng đến quy trình phát hành.

Chọn `update` khi manifest được chia sẻ giữa nhiều bước và mỗi bước chỉ bổ sung một nhóm metadata. Chọn `replace` khi build muốn tạo manifest chuẩn từ một nguồn cấu hình có kiểm soát và không muốn giữ những header cũ.

### 2.2. Cập nhật một header hiện có

Giả sử manifest hiện tại có:

```text
Manifest-Version: 1.0
Main-Class: com.example.legacy.Main
Implementation-Version: 1.0.0
```

Task sau cập nhật lớp khởi chạy và phiên bản:

```xml
<manifest file="build/MANIFEST.MF" mode="update">
    <attribute name="Main-Class" value="com.example.app.Main"/>
    <attribute name="Implementation-Version" value="2.4.0"/>
</manifest>
```

Manifest sau cập nhật giữ `Manifest-Version`, thay giá trị `Main-Class` và `Implementation-Version` theo cấu hình mới. Các header khác không được task đề cập vẫn được giữ trong chế độ update.

Nếu chạy cùng cấu hình với `mode="replace"`, chỉ những mục do task tạo ra sẽ còn trong manifest mới (cùng các header mặc định mà Ant tạo theo quy tắc của nó). Vì vậy, không dùng replace chỉ để đổi một giá trị nếu cần giữ metadata khác.

### 2.3. Thêm một section mới

Có thể thêm section cho package hoặc entry cụ thể:

```xml
<manifest file="build/MANIFEST.MF" mode="update">
    <section name="com/example/model/">
        <attribute name="Specification-Title" value="Domain Model API"/>
        <attribute name="Specification-Version" value="3.1"/>
    </section>
</manifest>
```

Nếu section đã tồn tại, các header được khai báo có thể được cập nhật trong section đó; những header khác được giữ theo quy tắc merge của manifest. Nếu section chưa tồn tại, Ant thêm section mới.

Tên section cần khớp với tên entry hoặc đường dẫn mà metadata áp dụng. Với package Java, tên thường dùng dấu `/` và có dấu `/` ở cuối, ví dụ `com/example/model/`.

## 3. Ghép manifest có sẵn với metadata mới

Một dự án có thể duy trì manifest cơ sở trong source control rồi bổ sung phiên bản hoặc thông tin build ở thời điểm đóng gói. Task `manifest` cho phép chỉ định tệp hiện có bằng thuộc tính `file`, sau đó khai báo các header cần thêm hoặc cập nhật.

Ví dụ tệp cơ sở `src/main/manifest/MANIFEST.MF`:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Inventory Application
```

Target sau đọc tệp đó và cập nhật phiên bản build:

```xml
<property name="app.version" value="2.4.0"/>
<property name="build.vendor" value="Example Company"/>

<target name="prepare-manifest">
    <manifest file="build/MANIFEST.MF" mode="update">
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Implementation-Vendor" value="${build.vendor}"/>
    </manifest>
</target>
```

Để merge một manifest cơ sở vào tệp đích, dùng task `manifest` với `file` trỏ đến tệp sẽ được tạo/cập nhật và phần tử `<manifest>` có thể nhận dữ liệu từ tệp manifest có sẵn theo cấu hình task của Ant. Một cách rõ ràng, dễ kiểm soát là dùng manifest cơ sở làm tệp đích làm việc trước, sau đó cập nhật trực tiếp nó; nếu muốn giữ source manifest bất biến, hãy sao chép nó vào thư mục build trước khi gọi task.

Ví dụ giữ source manifest nguyên trạng:

```xml
<target name="prepare-manifest">
    <mkdir dir="build"/>
    <copy file="src/main/manifest/MANIFEST.MF"
          tofile="build/MANIFEST.MF"/>

    <manifest file="build/MANIFEST.MF" mode="update">
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Implementation-Vendor" value="${build.vendor}"/>
    </manifest>
</target>
```

Cách này tạo bản làm việc trong `build/`, sau đó bổ sung các header do build quản lý. Mỗi lần chạy, nếu target copy lại tệp gốc trước khi update, các giá trị từ lần build trước sẽ không bị giữ lại ngoài ý muốn.

## 4. Cập nhật manifest trực tiếp khi đóng gói JAR

Nếu chỉ cần manifest cho một JAR cụ thể, thường không cần tạo tệp manifest trung gian. Task `<jar>` hỗ trợ nested `<manifest>` để khai báo header trực tiếp:

```xml
<target name="package">
    <jar destfile="build/dist/inventory.jar"
         basedir="build/classes">
        <manifest>
            <attribute name="Main-Class" value="com.example.app.Main"/>
            <attribute name="Implementation-Title" value="Inventory Application"/>
            <attribute name="Implementation-Version" value="2.4.0"/>
        </manifest>
    </jar>
</target>
```

Ant tạo `META-INF/MANIFEST.MF` bên trong JAR và ghi các thuộc tính đã khai báo. `Manifest-Version` thường được Ant thêm nếu chưa có. Cách lồng này phù hợp khi metadata chỉ được sử dụng trong một artifact và không cần chia sẻ manifest thành tệp độc lập.

### 4.1. Dùng tệp manifest bên ngoài với task `jar`

Nếu đã tạo hoặc cập nhật manifest bằng task `manifest`, truyền tệp đó cho task `<jar>` qua thuộc tính `manifest`:

```xml
<target name="package" depends="prepare-manifest">
    <jar destfile="build/dist/inventory.jar"
         basedir="build/classes"
         manifest="build/MANIFEST.MF"/>
</target>
```

Task `<jar>` đọc manifest đã chuẩn bị và đưa nó vào vị trí chuẩn bên trong archive. Cách này hữu ích khi cùng một manifest cần được kiểm tra, tái sử dụng hoặc chuyển cho nhiều bước đóng gói.

### 4.2. Kết hợp manifest ngoài và nested manifest

Task `<jar>` có thể nhận manifest từ tệp bên ngoài và các thuộc tính bổ sung qua nested `<manifest>`. Điều này cho phép dùng tệp cơ sở, sau đó bổ sung metadata chỉ dành cho artifact hiện tại:

```xml
<jar destfile="build/dist/inventory-cli.jar"
     basedir="build/classes"
     manifest="build/MANIFEST.MF">
    <manifest>
        <attribute name="Main-Class" value="com.example.cli.Main"/>
        <attribute name="Implementation-Title" value="Inventory CLI"/>
    </manifest>
</jar>
```

Khi cùng một header xuất hiện ở nhiều nguồn, giá trị cuối cùng phụ thuộc quy tắc merge của Ant và thứ tự xử lý manifest. Để tránh cấu hình khó hiểu, hãy chỉ định mỗi header ở một nơi nếu không thật sự cần ghi đè. Khi cần xác định chính xác kết quả, tạo manifest cuối cùng bằng task `manifest` rồi truyền một tệp duy nhất vào `<jar>`.

## 5. Dùng `Main-Class` để tạo executable JAR

Header `Main-Class` cho biết lớp Java có phương thức `main` mà Java launcher cần gọi khi chạy:

```bash
java -jar build/dist/inventory.jar
```

Ví dụ build file:

```xml
<jar destfile="build/dist/inventory.jar"
     basedir="build/classes">
    <manifest>
        <attribute name="Main-Class" value="com.example.app.Main"/>
    </manifest>
</jar>
```

Giá trị `Main-Class` là tên đầy đủ của lớp, gồm package, dùng dấu chấm phân tách package và tên lớp. Không thêm phần mở rộng `.class` và không viết đường dẫn dạng `com/example/app/Main.class`.

Lớp đó phải tồn tại trong JAR hoặc trên classpath runtime mà launcher có thể tìm thấy. Nếu thiếu lớp hoặc sai tên, lệnh `java -jar` sẽ báo không tìm thấy main class hoặc không thể khởi chạy.

## 6. Khai báo thư viện runtime bằng `Class-Path`

Executable JAR có thể cần thư viện phụ thuộc nằm bên ngoài. Header `Class-Path` khai báo danh sách URL tương đối đến các thư viện đó.

Ví dụ cấu trúc phân phối:

```text
dist/
├── inventory.jar
└── lib/
    ├── commons-lang3-3.14.0.jar
    └── slf4j-api-2.0.12.jar
```

Manifest của `inventory.jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/commons-lang3-3.14.0.jar lib/slf4j-api-2.0.12.jar
```

Khai báo trong Ant:

```xml
<jar destfile="build/dist/inventory.jar"
     basedir="build/classes">
    <manifest>
        <attribute name="Main-Class" value="com.example.app.Main"/>
        <attribute name="Class-Path"
                   value="lib/commons-lang3-3.14.0.jar lib/slf4j-api-2.0.12.jar"/>
    </manifest>
</jar>
```

Các mục trong `Class-Path` được phân tách bằng khoảng trắng, không phải dấu `:` hoặc `;` như classpath trên command line. Đường dẫn được phân giải tương đối với vị trí JAR chứa manifest. Vì vậy, nếu JAR nằm trong `dist/`, `lib/example.jar` trỏ đến `dist/lib/example.jar`.

Không ghi đường dẫn tuyệt đối của máy phát triển vào `Class-Path`, vì JAR sẽ không chạy trên máy khác có cấu trúc thư mục khác. Hãy thiết kế cấu trúc phân phối và giá trị tương đối nhất quán.

### 6.1. Không nhầm `Class-Path` với classpath biên dịch

Header `Class-Path` trong manifest phục vụ việc tìm thư viện khi chạy executable JAR. Nó không thay thế nested `<classpath>` của `<javac>` trong build file.

Một build thường có hai cấu hình riêng:

- Compile classpath: thư viện cần cho compiler, được truyền qua `<javac><classpath>`.
- Runtime classpath: thư viện cần khi ứng dụng chạy, có thể được đưa vào manifest `Class-Path`, đóng gói cùng distribution hoặc cung cấp bằng script khởi chạy.

Không phải mọi thư viện compile đều cần xuất hiện trong runtime manifest. Hãy chỉ đưa các dependency cần khi chạy ứng dụng.

## 7. Cập nhật manifest theo phiên bản build

Các giá trị manifest thường thay đổi theo phiên bản, số build, commit hoặc môi trường phát hành. Hãy đưa chúng thành Ant property để không phải sửa thủ công mỗi lần phát hành.

```xml
<property name="app.name" value="inventory"/>
<property name="app.version" value="2.4.0"/>
<property name="app.vendor" value="Example Company"/>

<target name="prepare-manifest">
    <manifest file="build/MANIFEST.MF" mode="replace">
        <attribute name="Manifest-Version" value="1.0"/>
        <attribute name="Main-Class" value="com.example.app.Main"/>
        <attribute name="Implementation-Title" value="${app.name}"/>
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Implementation-Vendor" value="${app.vendor}"/>
        <attribute name="Build-Profile" value="${build.profile}"/>
    </manifest>
</target>
```

Giá trị `build.profile` cần được khai báo hoặc truyền từ dòng lệnh trước khi target chạy. Ví dụ:

```bash
ant -Dapp.version=2.4.1 -Dbuild.profile=release package
```

Ant property có quy tắc first definition wins. Nếu build file đã khai báo `app.version` trước đó, giá trị truyền bằng `-D` được ưu tiên theo cơ chế user property; nhưng một property được thiết lập sớm từ nguồn khác có thể ảnh hưởng đến giá trị được mở rộng. Hãy tổ chức các property đầu vào nhất quán và tránh khai báo lại cùng một tên với kỳ vọng nó sẽ tự ghi đè.

Không đưa password, token, private key hoặc thông tin xác thực vào manifest. Manifest nằm trong JAR và thường được phát hành công khai cùng artifact.

## 8. Thêm metadata theo package bằng section

Một manifest có thể chứa metadata theo package thay vì đặt mọi header ở main section:

```xml
<manifest file="build/MANIFEST.MF" mode="replace">
    <attribute name="Manifest-Version" value="1.0"/>
    <attribute name="Main-Class" value="com.example.app.Main"/>

    <section name="com/example/api/">
        <attribute name="Specification-Title" value="Inventory Public API"/>
        <attribute name="Specification-Version" value="2.0"/>
        <attribute name="Specification-Vendor" value="Example Company"/>
    </section>

    <section name="com/example/internal/">
        <attribute name="Implementation-Title" value="Inventory Internal Components"/>
        <attribute name="Implementation-Version" value="2.4.0"/>
    </section>
</manifest>
```

Các header trong section áp dụng cho entry được đặt tên trong header `Name` của section. Điều này hữu ích khi một JAR chứa nhiều package có metadata đặc tả hoặc triển khai khác nhau.

Không đặt `Main-Class` trong section của package nếu mục đích là khai báo lớp khởi chạy cho toàn bộ JAR. Header khởi chạy phải nằm ở main section.

## 9. Ghép manifest từ các JAR phụ thuộc

Khi tạo một JAR tổng hợp từ nhiều JAR đầu vào, mỗi JAR có thể chứa manifest riêng. Task `<jar>` có thuộc tính `filesetmanifest` để điều khiển cách xử lý manifest lấy từ các JAR trong nested fileset.

Các giá trị thường dùng:

| Giá trị | Hành vi |
|---|---|
| `skip` | Bỏ qua manifest của các JAR được đưa vào bằng fileset; đây là mặc định thông thường |
| `merge` | Ghép manifest của các JAR đầu vào vào manifest của JAR kết quả, gồm cả main attributes theo quy tắc merge |
| `mergewithoutmain` | Ghép các section của manifest đầu vào nhưng bỏ qua main section của chúng |

Ví dụ:

```xml
<jar destfile="build/dist/combined.jar"
     filesetmanifest="mergewithoutmain">
    <fileset dir="build/classes">
        <include name="**/*"/>
    </fileset>
    <zipfileset src="lib/module-a.jar"/>
    <zipfileset src="lib/module-b.jar"/>

    <manifest>
        <attribute name="Main-Class" value="com.example.app.Main"/>
        <attribute name="Implementation-Version" value="2.4.0"/>
    </manifest>
</jar>
```

Ví dụ này minh họa việc lấy nội dung từ nhiều archive. Khi merge manifest từ dependency, cần xem xét các header có thể xung đột hoặc không phù hợp với JAR tổng hợp, chẳng hạn `Main-Class`, `Class-Path`, `Signature-Version` hoặc metadata đặc thù của artifact gốc.

Đặc biệt, không nên sao chép tùy tiện các tệp chữ ký như `.SF`, `.RSA`, `.DSA` hoặc `.EC` từ JAR phụ thuộc vào một JAR đã được sửa nội dung. Chữ ký của archive gốc không còn xác nhận tính toàn vẹn của JAR tổng hợp. Nếu tạo một archive mới, cần xác định quy trình ký lại phù hợp sau khi hoàn tất đóng gói.

## 10. Quy tắc định dạng manifest cần lưu ý

Manifest không phải tệp properties thông thường. Nó có quy tắc riêng về header, section, dòng trống và xuống dòng.

### 10.1. Header và dấu phân cách

Mỗi header có dạng:

```text
Header-Name: Header value
```

Tên header không được chứa dấu hai chấm. Giá trị được đặt sau dấu hai chấm và một dấu cách. Không thêm dấu nháy quanh giá trị nếu chúng không phải một phần dữ liệu mong muốn.

### 10.2. Giới hạn độ dài dòng

Định dạng manifest quy định giới hạn độ dài dòng theo byte; dòng dài được chia thành nhiều dòng vật lý và dòng tiếp theo bắt đầu bằng một dấu cách để biểu thị phần nối tiếp. Ant tự xử lý việc ghi manifest qua task của nó, vì vậy nên khai báo giá trị đầy đủ trong `<attribute>` thay vì tự cắt dòng bằng tay.

Khi đọc manifest bằng công cụ khác, cần hiểu quy tắc continuation line để ghép lại giá trị header chính xác. Không coi dấu cách ở đầu dòng tiếp theo là một phần mới của tên header.

### 10.3. Dòng trống phân tách section

Main section và các named section được phân tách bằng dòng trống. Một section có header `Name` để chỉ entry tương ứng. Khi dùng `<section>` trong Ant, task tự tạo cấu trúc cần thiết.

### 10.4. Encoding

Manifest hiện đại sử dụng UTF-8 theo định dạng JAR. Nếu đọc tệp manifest có nguồn gốc từ công cụ cũ hoặc encoding khác, hãy kiểm tra thuộc tính encoding mà task Ant cung cấp và bảo đảm dữ liệu được chuyển đổi đúng. Tránh lưu ký tự không ASCII bằng encoding không khớp với cách công cụ đọc manifest.

## 11. Tạo JAR và cập nhật manifest trong một quy trình

Ví dụ sau cho thấy cách tạo manifest độc lập rồi dùng nó để đóng gói JAR:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="manifest-demo" default="package" basedir=".">

    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="manifest.file" location="${build.dir}/MANIFEST.MF"/>
    <property name="app.version" value="2.4.0"/>

    <target name="prepare-manifest">
        <mkdir dir="${build.dir}"/>
        <manifest file="${manifest.file}" mode="replace">
            <attribute name="Manifest-Version" value="1.0"/>
            <attribute name="Main-Class" value="com.example.app.Main"/>
            <attribute name="Implementation-Title" value="Inventory Application"/>
            <attribute name="Implementation-Version" value="${app.version}"/>
            <attribute name="Implementation-Vendor" value="Example Company"/>
            <section name="com/example/api/">
                <attribute name="Specification-Version" value="2.0"/>
            </section>
        </manifest>
    </target>

    <target name="package" depends="prepare-manifest">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/inventory.jar"
             basedir="${classes.dir}"
             manifest="${manifest.file}"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

</project>
```

Target `prepare-manifest` tạo manifest mới từ cấu hình hiện tại. Target `package` phụ thuộc vào target này, sau đó truyền tệp manifest cho `<jar>`. Thư mục `classes.dir` cần chứa các lớp đã biên dịch, bao gồm `com/example/app/Main.class`; ví dụ tập trung vào bước manifest và đóng gói nên không trình bày lại target compile.

Nếu muốn giữ một manifest cơ sở được quản lý trong source control, hãy copy tệp đó vào `${build.dir}` trước rồi gọi task `<manifest mode="update">` để bổ sung giá trị build. Nếu muốn manifest phát hành luôn được tạo hoàn toàn từ cấu hình build, dùng `mode="replace"` như ví dụ.

## 12. Kiểm tra manifest sau khi đóng gói

Sau khi tạo JAR, có thể xem nội dung manifest bằng lệnh `jar` của JDK:

```bash
jar --list --file build/dist/inventory.jar
```

Lệnh trên liệt kê các entry, trong đó cần có `META-INF/MANIFEST.MF`. Để đọc manifest, có thể dùng `unzip`:

```bash
unzip -p build/dist/inventory.jar META-INF/MANIFEST.MF
```

Hoặc dùng một công cụ JDK/ZIP phù hợp trên hệ điều hành. Kiểm tra các điểm quan trọng:

- `Main-Class` có đúng tên đầy đủ và lớp đó có trong JAR không?
- `Class-Path` có trỏ đến đúng các thư viện trong cấu trúc phân phối không?
- `Implementation-Version` có đúng phiên bản phát hành không?
- Các section có header `Name` trỏ đến entry đúng không?
- Có header cũ nào cần giữ bị mất do dùng `replace` không?
- Có metadata từ JAR phụ thuộc bị ghép vào ngoài ý muốn không?

Nếu JAR là executable, chạy thử:

```bash
java -jar build/dist/inventory.jar
```

Lệnh này xác nhận launcher tìm thấy `Main-Class` và JVM có thể khởi chạy lớp đó. Nếu ứng dụng cần tham số, truyền chúng sau tên JAR; nếu cần thư viện ngoài, kiểm tra `Class-Path` và cấu trúc thư mục phát hành.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Manifest cũ bị mất header | Dùng `mode="replace"` trong khi chỉ muốn cập nhật một vài giá trị | Dùng `mode="update"` hoặc khai báo đầy đủ mọi header cần giữ |
| Header cũ vẫn còn sau khi chạy task | Dùng `mode="update"`, vốn giữ các mục không được thay đổi | Dùng `replace` nếu muốn tạo manifest hoàn toàn mới |
| JAR không chạy bằng `java -jar` | Thiếu `Main-Class`, sai tên lớp hoặc lớp không nằm trong archive | Kiểm tra main class, package và nội dung JAR |
| Không tìm thấy thư viện runtime | `Class-Path` sai, dùng đường dẫn tuyệt đối hoặc thư viện không nằm đúng vị trí tương đối | Dùng URL/đường dẫn tương đối với JAR và giữ cấu trúc distribution nhất quán |
| Header xuất hiện hai lần hoặc giá trị không như mong đợi | Cùng header được khai báo ở manifest file, nested manifest hoặc nhiều manifest đầu vào | Chỉ định một nguồn có thẩm quyền cho từng header và kiểm tra kết quả merge |
| Metadata package không áp dụng | Tên section không khớp đường dẫn entry hoặc đặt header ở main section thay vì section | Kiểm tra `<section name="...">` và vị trí header |
| Dòng manifest bị hỏng khi tự ghi thủ công | Không tuân thủ quy tắc continuation line hoặc phân tách section | Dùng task `manifest` hoặc API manifest thay vì tự nối chuỗi văn bản |
| Manifest từ dependency làm sai JAR tổng hợp | `filesetmanifest` merge cả main attributes không phù hợp | Cân nhắc `mergewithoutmain` hoặc `skip`, rồi khai báo manifest của archive đích rõ ràng |
| JAR tổng hợp không còn chữ ký hợp lệ | Đã thay đổi nội dung nhưng giữ signature file của archive gốc | Loại bỏ chữ ký cũ và ký lại archive cuối theo quy trình phát hành |
| Thay đổi manifest nhưng JAR không đổi như mong muốn | Task đóng gói không dùng tệp manifest vừa cập nhật hoặc target dependency sai | Đặt `depends` đúng thứ tự và truyền `manifest` file cho `<jar>` |

## 14. Checklist sử dụng task manifest

- [ ] Đã xác định manifest cần tạo độc lập hay chỉ cần khai báo trong `<jar>`.
- [ ] Đã chọn `mode="update"` khi cần giữ metadata hiện có.
- [ ] Đã chọn `mode="replace"` khi muốn tạo manifest mới từ cấu hình đầy đủ.
- [ ] Header toàn JAR được đặt ở main section.
- [ ] Metadata theo package hoặc entry được đặt trong `<section>` phù hợp.
- [ ] `Main-Class` là tên đầy đủ của lớp có phương thức main và lớp đó nằm trong JAR.
- [ ] `Class-Path` chỉ chứa thư viện runtime cần thiết và dùng đường dẫn tương đối phù hợp với cấu trúc phân phối.
- [ ] Manifest file trung gian được đặt trong vùng build output và có thể tái tạo.
- [ ] Target đóng gói phụ thuộc vào target chuẩn bị manifest.
- [ ] Đã xác định rõ cách xử lý manifest từ các JAR đầu vào qua `filesetmanifest`.
- [ ] Không giữ signature file cũ sau khi thay đổi nội dung archive đã ký.
- [ ] Đã mở manifest bên trong JAR để xác nhận header và section cuối cùng.
- [ ] Không đưa secret hoặc thông tin xác thực vào manifest được phát hành.

Task `manifest` giúp quản lý metadata JAR theo cách có cấu trúc: `update` để bổ sung hoặc thay đổi một phần, `replace` để tạo lại toàn bộ, `<attribute>` để khai báo header và `<section>` để gắn metadata cho entry. Khi kết hợp với thuộc tính `manifest` hoặc nested `<manifest>` của task `<jar>`, bạn có thể tạo artifact có thông tin khởi chạy và phiên bản rõ ràng, đồng thời kiểm soát được metadata được giữ lại trong quá trình đóng gói.

Tài liệu tham khảo: [Apache Ant Manual — Manifest Task](https://ant.apache.org/manual/Tasks/manifest.html), [Apache Ant Manual — JAR Task](https://ant.apache.org/manual/Tasks/jar.html) và [JAR File Specification — Manifest](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html#the-manifest).

# Tạo JAR từ lớp biên dịch và tài nguyên

Trong Apache Ant, task `<jar>` đóng gói các tệp thành một Java Archive (JAR). Với một ứng dụng hoặc thư viện Java thông thường, đầu vào của JAR gồm các lớp đã biên dịch (`.class`), tài nguyên cần có trên classpath và metadata như manifest. Ant không biên dịch source trong lúc chạy task `<jar>`; target đóng gói phải nhận được các lớp đã được tạo bởi bước compile trước đó.

Một luồng build phổ biến:

~~~text
src/main/java              src/main/resources
      |                            |
      v                            v
    javac                      copy resources
      |                            |
      v                            v
 build/classes  <------------------+
      |
      v
    jar task  +  manifest
      |
      v
 dist/application.jar
~~~

JAR giữ cấu trúc đường dẫn tương đối bên trong archive. Ví dụ lớp `com.example.Main` phải nằm tại `com/example/Main.class`; resource `config/app.properties` phải nằm tại `config/app.properties` nếu chương trình đọc nó bằng đường dẫn classpath tương ứng.

## 1. JAR là gì và chứa những gì?

JAR là một tệp archive dựa trên định dạng ZIP, được dùng để phân phối lớp Java, tài nguyên và metadata. Một JAR thông thường có thể chứa:

- Bytecode `.class` được tạo từ mã nguồn Java.
- Resource như `.properties`, `.xml`, `.yml`, ảnh, template hoặc dữ liệu tĩnh.
- Thư mục `META-INF/`, đặc biệt là file `META-INF/MANIFEST.MF`.
- Metadata bổ sung như chữ ký, thông tin phiên bản hoặc service descriptor nếu dự án cần.

Ví dụ cấu trúc một JAR ứng dụng:

~~~text
application.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       ├── Main.class
│       └── service/
│           └── UserService.class
└── config/
    └── app.properties
~~~

JAR không bắt buộc phải chứa mã nguồn `.java`. Thông thường, source được biên dịch thành `.class` trước; resource được copy hoặc thêm trực tiếp vào archive. Nếu muốn phân phối source code, dự án thường tạo thêm một source JAR riêng.

## 2. Task `<jar>` cơ bản

Task `<jar>` tạo archive từ một thư mục hoặc một tập file. Cách đơn giản nhất là chỉ định `destfile` và `basedir`:

~~~xml
<target name="package">
    <mkdir dir="dist"/>
    <jar destfile="dist/application.jar"
         basedir="build/classes"/>
</target>
~~~

- `destfile`: đường dẫn file JAR cần tạo.
- `basedir`: thư mục gốc chứa các file sẽ được đóng gói.

Ant lấy nội dung bên dưới `build/classes` và lưu các đường dẫn tương đối của chúng vào archive. Ví dụ `build/classes/com/example/Main.class` trở thành `com/example/Main.class` trong JAR; tên thư mục `build/classes` không xuất hiện ở đầu đường dẫn bên trong archive.

Thư mục đầu ra nên được tạo trước bằng `<mkdir>`. Nếu build cần đóng gói nhiều nhóm file hoặc loại trừ một số nội dung, có thể dùng các nested fileset thay cho `basedir`.

## 3. Biên dịch lớp trước khi đóng gói

Task `<jar>` chỉ đóng gói file hiện có. Vì vậy, target package phải phụ thuộc vào target compile để bảo đảm `.class` đã được tạo.

Ví dụ khai báo property và target compile:

~~~xml
<property name="src.main" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>
<property name="dist.dir" location="dist"/>

<target name="init">
    <mkdir dir="${classes.dir}"/>
</target>

<target name="compile" depends="init">
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           encoding="UTF-8"
           includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar"
         basedir="${classes.dir}"/>
</target>
~~~

Khi chạy:

~~~bash
ant package
~~~

Ant thực hiện `init`, sau đó `compile`, rồi mới thực hiện `package`. Nếu compile thất bại, dependency graph không cho target package tiếp tục như thể đã có bytecode hợp lệ.

Quan hệ `depends` chỉ điều phối thứ tự target. Nó không bảo đảm thư mục classes không còn file cũ. Nếu source bị xóa hoặc đổi package, output cũ có thể vẫn tồn tại. Một build phát hành sạch thường có target `clean` xóa output do build tạo ra trước khi compile và package lại.

## 4. Đưa resource vào JAR

Ứng dụng thường cần tài nguyên ngoài bytecode, ví dụ file cấu hình, message bundle, template hoặc dữ liệu tĩnh. Những file này cần được đặt đúng vị trí để ứng dụng đọc được khi chạy.

Cấu trúc dự án thường gặp:

~~~text
project/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/Main.java
│       └── resources/
│           ├── app.properties
│           └── config/logging.xml
└── build/
~~~

### 4.1. Copy resource vào thư mục classes

Một cách thông dụng là copy resource vào cùng thư mục output của compiler:

~~~xml
<property name="resources.dir" location="src/main/resources"/>

<target name="process-resources" depends="init">
    <copy todir="${classes.dir}">
        <fileset dir="${resources.dir}">
            <include name="**/*"/>
        </fileset>
    </copy>
</target>

<target name="compile" depends="process-resources">
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           encoding="UTF-8"
           includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar"
         basedir="${classes.dir}"/>
</target>
~~~

`<copy todir>` giữ cấu trúc đường dẫn tương đối của resource dưới `src/main/resources`. Ví dụ:

- `src/main/resources/app.properties` được copy thành `build/classes/app.properties`.
- `src/main/resources/config/logging.xml` được copy thành `build/classes/config/logging.xml`.

Khi JAR được tạo từ `build/classes`, cả `.class` lẫn resource đều được đóng gói. Trong Java, có thể đọc resource từ classpath bằng `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream`, tùy cách đặt đường dẫn.

Ví dụ:

~~~java
try (var input = Main.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("app.properties not found");
    }
    // Load the properties from input.
}
~~~

Dấu `/` ở đầu đường dẫn của `Class.getResourceAsStream` biểu thị đường dẫn từ gốc classpath. Vì resource được đóng gói ở gốc JAR, đường dẫn `/app.properties` sẽ tìm đúng file.

### 4.2. Đóng gói resource trực tiếp bằng nested fileset

Không nhất thiết phải copy resource vào thư mục classes. Task `<jar>` có thể nhận nhiều FileSet:

~~~xml
<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar">
        <fileset dir="${classes.dir}">
            <include name="**/*.class"/>
        </fileset>
        <fileset dir="${resources.dir}">
            <include name="**/*"/>
        </fileset>
    </jar>
</target>
~~~

Mỗi FileSet đóng góp các file với đường dẫn tương đối tính từ `dir` của nó. Cách này giữ thư mục resource riêng và tránh copy resource vào output classes. Tuy nhiên, nếu hai FileSet cùng chứa một đường dẫn tương đối giống nhau, chúng có thể tạo tên entry trùng trong JAR. Hãy thiết kế đường dẫn hoặc include/exclude để tránh xung đột.

Chọn một trong hai cách theo cấu trúc build. Copy resource vào classes thuận tiện khi nhiều task cần cùng một thư mục output hoàn chỉnh; thêm trực tiếp FileSet phù hợp khi muốn phân biệt bytecode với resource trong quá trình build.

## 5. Tạo manifest cho JAR

Mỗi JAR có thể chứa manifest tại `META-INF/MANIFEST.MF`. Manifest lưu các thuộc tính mô tả archive hoặc hướng dẫn Java runtime cách xử lý JAR.

Task `<jar>` hỗ trợ nested element `<manifest>`:

~~~xml
<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Manifest-Version" value="1.0"/>
            <attribute name="Implementation-Title" value="Sample Application"/>
            <attribute name="Implementation-Version" value="1.0.0"/>
        </manifest>
    </jar>
</target>
~~~

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest; thường là `1.0` |
| `Implementation-Title` | Tên sản phẩm hoặc module được đóng gói |
| `Implementation-Version` | Phiên bản implementation |
| `Implementation-Vendor` | Nhà cung cấp hoặc tổ chức phát hành |
| `Specification-Title` | Tên specification mà thư viện triển khai |
| `Specification-Version` | Phiên bản specification |
| `Main-Class` | Lớp có phương thức `public static void main(String[] args)` để chạy JAR như ứng dụng |
| `Class-Path` | Danh sách vị trí dependency bên ngoài mà launcher có thể tìm theo quy tắc manifest |

Ant có thể tự tạo `Manifest-Version` nếu không khai báo. Khi cần metadata rõ ràng cho artifact, hãy khai báo các thuộc tính mà quy trình phát hành yêu cầu.

## 6. Tạo executable JAR bằng `Main-Class`

Một JAR có thể được chạy bằng `java -jar` nếu manifest có thuộc tính `Main-Class` trỏ tới lớp chứa điểm vào ứng dụng.

Ví dụ source:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Target đóng gói:

~~~xml
<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Main-Class" value="com.example.Main"/>
            <attribute name="Implementation-Version" value="1.0.0"/>
        </manifest>
    </jar>
</target>
~~~

Sau khi build, có thể chạy:

~~~bash
java -jar dist/application.jar
~~~

Giá trị `Main-Class` là tên lớp đầy đủ (fully qualified class name), có package nếu lớp nằm trong package. Không thêm `.class` và không dùng đường dẫn file như `com/example/Main.class`.

Ví dụ đúng là `com.example.Main`. Nếu khai báo sai tên lớp hoặc lớp không có phương thức `main` hợp lệ, Java launcher không thể khởi chạy ứng dụng.

Executable JAR chỉ có nghĩa manifest xác định điểm vào. Điều đó không tự động đưa tất cả thư viện phụ thuộc vào trong JAR.

## 7. Dependency bên ngoài và manifest `Class-Path`

Task `<jar>` cơ bản đóng gói những file được chỉ định. Nếu ứng dụng phụ thuộc vào thư viện ngoài, các JAR đó không tự được nhúng vào archive chỉ vì chúng nằm trong compile classpath.

Có thể phân phối các dependency bên cạnh application JAR:

~~~text
dist/
├── application.jar
└── lib/
    ├── commons-lang3-3.14.0.jar
    └── jackson-core-2.17.1.jar
~~~

Manifest có thể khai báo `Class-Path`:

~~~xml
<manifest>
    <attribute name="Main-Class" value="com.example.Main"/>
    <attribute name="Class-Path"
               value="lib/commons-lang3-3.14.0.jar lib/jackson-core-2.17.1.jar"/>
</manifest>
~~~

Đường dẫn trong `Class-Path` được hiểu tương đối với URL của JAR chứa manifest và tuân theo quy tắc manifest class path của Java. Với cấu trúc trên, các thư viện nằm trong thư mục `lib` cùng cấp với `application.jar`.

Khi chạy:

~~~bash
java -jar dist/application.jar
~~~

Java launcher đọc `Main-Class` và `Class-Path` từ manifest. Các dependency phải thực sự tồn tại ở những vị trí được khai báo và phải tương thích với ứng dụng.

Lưu ý:

- `Class-Path` không phải đường dẫn classpath của Ant và không tự copy dependency vào thư mục `dist`.
- Giá trị cần liệt kê các URL/đường dẫn tương đối phù hợp, cách nhau bằng dấu cách theo quy tắc manifest.
- Đường dẫn có khoảng trắng hoặc ký tự đặc biệt cần tuân thủ cú pháp URL/manifest; nên ưu tiên tên thư mục đơn giản.
- Nếu dependency bị thiếu, ứng dụng có thể khởi chạy rồi lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`.
- `java -jar` sử dụng cấu hình classpath từ manifest; không nên kỳ vọng tham số `-cp` bên ngoài bổ sung classpath theo cách chạy lớp thông thường.

Một target Ant có thể copy dependency sang `dist/lib` và tạo manifest tương ứng:

~~~xml
<target name="copy-runtime-libs">
    <mkdir dir="${dist.dir}/lib"/>
    <copy todir="${dist.dir}/lib">
        <fileset dir="lib/runtime">
            <include name="*.jar"/>
        </fileset>
    </copy>
</target>

<target name="package" depends="compile,copy-runtime-libs">
    <jar destfile="${dist.dir}/application.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Main-Class" value="com.example.Main"/>
            <attribute name="Class-Path"
                       value="lib/commons-lang3-3.14.0.jar lib/jackson-core-2.17.1.jar"/>
        </manifest>
    </jar>
</target>
~~~

Danh sách trong manifest phải khớp với những file thực tế được copy. Với dự án có nhiều dependency, không nên duy trì hai danh sách bằng tay nếu có thể tạo manifest class path từ cùng một nguồn cấu hình hoặc từ dependency resolver.

## 8. JAR thường, executable JAR và fat JAR

Các khái niệm này không đồng nghĩa:

| Loại | Nội dung | Cách sử dụng |
|---|---|---|
| JAR thư viện | Class và resource của một module | Được thêm vào classpath của ứng dụng khác |
| Executable JAR | JAR có manifest `Main-Class` | Có thể chạy bằng `java -jar` nếu runtime dependencies sẵn sàng |
| JAR có manifest `Class-Path` | JAR tham chiếu các dependency bên ngoài | Chạy cùng các JAR ở vị trí được khai báo |
| Fat JAR / uber JAR | Gộp class và resource của ứng dụng cùng dependency vào một archive | Thuận tiện phân phối một file, nhưng cần xử lý nội dung trùng và metadata đặc biệt |

Task `<jar>` với `basedir` không tự tạo fat JAR. Nó chỉ đóng gói nội dung được chọn. Muốn gộp nội dung từ các dependency archive, phải cấu hình thêm cách giải nén/ghép archive, dùng task hoặc công cụ hỗ trợ, và xử lý các entry trùng tên.

Khi tạo fat JAR, cần chú ý:

- Nhiều JAR có thể chứa `META-INF/MANIFEST.MF`; không nên gộp tất cả manifest nguyên trạng.
- Service provider descriptor trong `META-INF/services` có thể cần được hợp nhất, không phải chỉ ghi đè.
- Chữ ký của JAR dependency không còn hợp lệ nếu nội dung archive đã bị thay đổi; các signature file cần được xử lý theo chính sách phù hợp.
- License, notice và metadata của dependency có thể cần được giữ lại.
- Các file có cùng đường dẫn có thể ghi đè lẫn nhau hoặc làm task báo duplicate.
- Một số thư viện cần cấu trúc đặc biệt hoặc relocation package để tránh xung đột class.

Nếu dự án cần fat JAR, nên dùng cơ chế đóng gói đã được thiết kế cho mục tiêu đó và kiểm thử artifact cuối cùng. Không coi việc đổi phần mở rộng hoặc thêm tất cả JAR vào một FileSet là đủ để tạo một executable archive đúng.

## 9. Chọn nội dung bằng `fileset`, `include` và `exclude`

Khi chỉ muốn đóng gói một phần nội dung, dùng nested FileSet:

~~~xml
<target name="package" depends="compile">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${dist.dir}/application.jar">
        <fileset dir="${classes.dir}">
            <include name="**/*.class"/>
            <include name="**/*.properties"/>
            <exclude name="**/*Test.class"/>
            <exclude name="**/internal/debug/**"/>
        </fileset>
        <manifest>
            <attribute name="Main-Class" value="com.example.Main"/>
        </manifest>
    </jar>
</target>
~~~

- `**/*.class` chọn bytecode ở mọi package.
- `**/*.properties` chọn resource properties ở mọi cấp.
- `**/*Test.class` loại các class test.
- `**/internal/debug/**` loại các nội dung debug nội bộ.

Nếu thư mục classes chỉ chứa mã production, có thể đóng gói toàn bộ bằng `basedir`. Nếu dùng FileSet, hãy xác nhận mọi resource cần thiết đều được include và không loại nhầm class được ứng dụng sử dụng lúc chạy.

## 10. Manifest có thể được lấy từ file riêng

Khi manifest có nhiều thuộc tính hoặc được quản lý riêng, có thể chuẩn bị file manifest và đưa vào task `<jar>`:

~~~text
project/
├── build.xml
├── config/
│   └── MANIFEST.MF
└── build/classes/
~~~

Ví dụ file `config/MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Sample Application
Implementation-Version: 1.0.0
~~~

Build file:

~~~xml
<jar destfile="dist/application.jar"
     basedir="build/classes"
     manifest="config/MANIFEST.MF"/>
~~~

Task `<jar>` dùng file được chỉ định làm manifest đầu vào. Nếu cần thêm hoặc ghi đè thuộc tính, có thể dùng nested `<manifest>` theo khả năng của task và cấu hình merge phù hợp. Không nên tạo nhiều manifest khác nhau ở nhiều vị trí mà không xác định rõ nguồn chính.

Manifest có quy tắc định dạng riêng: mỗi thuộc tính là một dòng `Name: Value`, dòng trống phân tách section và dòng dài có thể được wrap theo chuẩn manifest. Dùng task Ant để tạo manifest thường an toàn hơn tự ghép chuỗi khi cần giá trị động.

## 11. Ví dụ build hoàn chỉnh: compile, resources và JAR

Ví dụ dưới đây gom các bước chính trong một `build.xml`:

~~~xml
<project name="sample-app" default="package" basedir=".">

    <property name="src.main" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="app.version" value="1.0.0"/>
    <property name="main.class" value="com.example.Main"/>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="process-resources" depends="init">
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}">
                <include name="**/*"/>
            </fileset>
        </copy>
    </target>

    <target name="compile" depends="process-resources">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${dist.dir}/application-${app.version}.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
                <attribute name="Implementation-Title" value="Sample Application"/>
                <attribute name="Implementation-Version" value="${app.version}"/>
            </manifest>
        </jar>
    </target>

    <target name="clean-package" depends="clean,package"/>

</project>
~~~

Có thể chạy:

~~~bash
ant clean-package
~~~

Target `clean-package` yêu cầu `clean` rồi `package`. `package` đi qua `compile`, `process-resources` và `init`. Vì vậy, artifact được tạo từ output sạch, bao gồm bytecode và resource đã copy.

Trong build thực tế, cần bảo đảm `src/main/resources` tồn tại hoặc điều chỉnh target nếu dự án không có thư mục resource. Cũng cần cấu hình classpath dependency cho `javac` nếu source sử dụng thư viện ngoài. Ví dụ trên tập trung vào cách ghép lớp và resource vào JAR.

## 12. Kiểm tra nội dung JAR sau khi tạo

Sau khi đóng gói, nên xác nhận artifact có đúng entry và manifest.

Liệt kê nội dung:

~~~bash
jar tf dist/application-1.0.0.jar
~~~

Có thể kiểm tra riêng:

- Có `com/example/Main.class`.
- Có các class production cần thiết.
- Có `app.properties` hoặc resource khác ở đúng đường dẫn.
- Có `META-INF/MANIFEST.MF`.
- Không có source/test class hoặc file tạm ngoài ý muốn.

Để xem manifest, có thể giải nén archive vào thư mục tạm:

~~~bash
mkdir jar-inspect
cd jar-inspect
jar xf ../dist/application-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Trên Windows PowerShell, có thể dùng `Get-Content` để đọc manifest sau khi giải nén. Nếu JAR có `Main-Class`, hãy thử chạy bằng `java -jar` trong môi trường tương thích. Một lần chạy thành công không thay thế việc kiểm tra nội dung archive, nhưng giúp xác nhận launcher và runtime dependency ở mức cơ bản.

Có thể dùng task Ant để kiểm tra file tồn tại trước khi chuyển sang bước phát hành:

~~~xml
<target name="check-package" depends="package">
    <available file="${dist.dir}/application-${app.version}.jar"
               type="file"
               property="jar.exists"/>
    <fail unless="jar.exists"
          message="JAR artifact was not created"/>
</target>
~~~

Đây chỉ là kiểm tra sự tồn tại. Việc xác minh entry, manifest, checksum và khả năng chạy cần các bước kiểm tra tương ứng.

## 13. Lỗi thường gặp khi tạo JAR

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JAR rỗng hoặc thiếu class | Compile chưa chạy, sai `basedir` hoặc output không đúng | Kiểm tra dependency target và thư mục classes |
| JAR có class nhưng thiếu resource | Resource chưa được copy hoặc chưa thêm FileSet | Kiểm tra `process-resources`, `resources.dir` và entry trong JAR |
| Resource không đọc được khi chạy | Đường dẫn trong JAR khác đường dẫn mà code yêu cầu | Kiểm tra package path và cách gọi `getResourceAsStream` |
| `no main manifest attribute` | Manifest không có `Main-Class` | Thêm thuộc tính `Main-Class` với tên lớp đầy đủ |
| `Could not find or load main class` | Sai package/class name hoặc class không có trong archive | So sánh `Main-Class` với đường dẫn `.class` trong JAR |
| `NoClassDefFoundError` khi chạy | Dependency bên ngoài không được cung cấp | Copy dependency và cấu hình manifest `Class-Path`, hoặc tạo fat JAR đúng cách |
| Có file cũ trong JAR | Thư mục classes còn output từ lần build trước | Chạy clean và tạo lại output |
| Có entry trùng tên | Nhiều FileSet đóng góp cùng đường dẫn tương đối | Điều chỉnh include/exclude hoặc tổ chức lại cây resource |
| Manifest không có giá trị mong đợi | Dùng sai property hoặc nguồn manifest khác | In property và kiểm tra cấu hình `manifest`/nested `<manifest>` |
| JAR không chạy trên runtime đích | Bytecode/API hoặc dependency không tương thích | Kiểm tra Java release, runtime và dependency versions |

Khi debug, hãy kiểm tra theo thứ tự: output classes có đúng không, resource có đúng không, target package có nhận đúng thư mục không, manifest có đúng không và dependency runtime đã được phân phối chưa.

## 14. Một số lưu ý về chất lượng artifact

Artifact phát hành nên được tạo từ đầu vào xác định và có thể kiểm tra lại. Một số nguyên tắc hữu ích:

- Chạy clean build khi cần bảo đảm không dùng output cũ.
- Gắn phiên bản vào tên JAR và manifest.
- Chỉ đóng gói nội dung cần thiết; loại file test, log, cache và secret.
- Kiểm tra resource được đặt đúng đường dẫn.
- Phân phối dependency theo một chiến lược rõ ràng: JAR bên cạnh với manifest `Class-Path`, hoặc một dạng archive gộp đã được xử lý đúng.
- Lưu checksum và metadata phát hành theo chính sách dự án.
- Kiểm tra JAR thực tế sau khi tạo trước khi upload hoặc deploy.

JAR là artifact được tạo từ bytecode và resource. Việc tạo được file không chứng minh ứng dụng có đầy đủ dependency hoặc chạy được trên môi trường đích. Vì vậy, bước kiểm tra archive và kiểm thử runtime là một phần hữu ích của quy trình đóng gói.

## Kết luận

Trong Ant, task `<jar>` đóng gói các lớp đã biên dịch và tài nguyên thành một archive bằng `basedir` hoặc nested FileSet. Target package cần phụ thuộc vào compile và bước chuẩn bị resource để bảo đảm đầu vào đã sẵn sàng. Nested `<manifest>` có thể thêm metadata và `Main-Class` để tạo executable JAR; `Class-Path` chỉ tham chiếu các dependency bên ngoài, không tự nhúng chúng vào archive. Hãy phân biệt JAR thư viện, executable JAR và fat JAR, sau đó kiểm tra nội dung, manifest, resource và runtime dependency của artifact trước khi phát hành.
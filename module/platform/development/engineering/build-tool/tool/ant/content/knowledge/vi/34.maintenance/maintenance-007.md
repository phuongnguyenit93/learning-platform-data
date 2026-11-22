# Giữ sản phẩm sinh tự động ngoài vùng mã nguồn được quản lý trong Apache Ant

## 1. Vì sao đây là một nguyên tắc bảo trì quan trọng?

Một dự án Java dùng Apache Ant thường có hai nhóm file với cách quản lý hoàn toàn khác nhau. **Mã nguồn được quản lý** là những file do con người hoặc quy trình biên soạn có chủ đích duy trì trong hệ thống quản lý phiên bản (thường là Git): Java source, cấu hình, tài nguyên, file `build.xml`, template và dữ liệu đầu vào của bộ sinh mã. **Sản phẩm sinh tự động** là những file mà Ant hoặc công cụ Ant gọi có thể tạo lại: `.class`, JAR, báo cáo kiểm thử, tài liệu Javadoc, file tạm, tài nguyên đã xử lý và source do generator tạo ra.

Nếu để cả hai nhóm chung một vùng, mỗi lần chạy build có nguy cơ làm thay đổi file đang được quản lý. Lúc đó `git status` tràn ngập thay đổi không liên quan, việc review khó hơn, công cụ dọn dẹp có thể xóa nhầm nội dung cần giữ, và build có thể vô tình sử dụng file còn sót từ lần chạy trước.

Trong Ant, cách tổ chức dễ bảo trì là **giữ đầu vào được quản lý trong `src/`, `config/`, `templates/`; đưa đầu ra sinh tự động vào một cây riêng như `.ant-out/` hoặc `build/`; chỉ khai báo đúng thư mục đầu ra ấy cho các task**.

Ví dụ về ranh giới:

| Loại file | Ví dụ | Nguồn sở hữu và cách quản lý |
|---|---|---|
| Java do lập trình viên viết | `src/main/java/demo/App.java` | Được quản lý bằng Git; Ant chỉ **đọc**. |
| Tài nguyên cấu hình được biên soạn | `src/main/resources/application.properties` | Được quản lý bằng Git; có thể copy sang đầu ra. |
| Template cho generator | `templates/client.mustache` | Được quản lý bằng Git; generator đọc để sinh file mới. |
| Bộ sinh mã và cấu hình của nó | `build.xml`, script generator | Được quản lý bằng Git; quyết định tạo file ở đâu và tạo như thế nào. |
| Java source được sinh | `.ant-out/generated-sources/java/...` | Ant/generator sở hữu; có thể xóa và tạo lại. |
| Class biên dịch | `.ant-out/classes/...` | Ant/`javac` sở hữu; không commit. |
| File phân phối | `.ant-out/dist/app.jar` | Ant/`jar` sở hữu; CI có thể giữ như artifact. |
| Báo cáo và log | `.ant-out/reports/...`, `.ant-out/logs/...` | Công cụ test/build sở hữu; không trộn với source. |

**Không phải mọi file “tạo bằng công cụ” đều bắt buộc bị bỏ khỏi Git.** Một dự án có thể chủ đích version-control API client được sinh để phân phối cho người khác, tài liệu snapshot cần review, hoặc mã nguồn bootstrap. Khi đó phải có hợp đồng rõ: ai là chủ sở hữu, file có được sửa bằng tay không, cách tái sinh và quy trình review thay đổi. Bài này áp dụng cho **đầu ra thuần tự động, có thể tạo lại từ đầu vào được quản lý**.

## 2. Những vấn đề xuất hiện khi ghi trực tiếp vào `src/`

Giả sử một generator ghi lớp `GeneratedVersion.java` vào `src/main/java/demo/generated/`, còn Ant biên dịch file `.class` ngay bên cạnh source:

```text
project/
├── src/main/java/demo/
│   ├── App.java
│   ├── App.class                     # phát sinh sau compile: không phù hợp
│   └── generated/
│       ├── GeneratedVersion.java    # generator ghi thẳng vào source
│       └── GeneratedVersion.class
└── build.xml
```

Thiết kế này tạo ra các rủi ro:

1. **Nhiễu khi review:** mỗi lần build thay timestamp hoặc thứ tự sinh mã có thể khiến hàng loạt file trong `src/` bị báo thay đổi.
2. **Lẫn nguồn sự thật:** không rõ nên sửa source đã sinh hay template/generator; lần sinh tiếp theo có thể ghi đè chỉnh sửa thủ công.
3. **File cũ không tự biến mất:** generator đổi tên hoặc xóa một lớp, nhưng lớp sinh cũ vẫn nằm trong source và có thể tiếp tục được biên dịch.
4. **Dọn dẹp khó an toàn:** `clean` phải chọn lọc những file sinh nằm xen giữa mã người viết; xóa rộng có thể mất dữ liệu.
5. **Khác biệt máy phát triển:** một người đã sinh file còn người khác thì chưa, khiến IDE và build đọc các tập source khác nhau.
6. **Rủi ro với CI:** build chạy ở workspace không sạch có thể mang theo file cũ, làm kết quả khác với clean checkout.

Việc thêm `*.class` vào `.gitignore` chỉ làm Git bớt hiển thị file mới; **nó không giải quyết việc file thực sự nằm trong cây nguồn**. Trọng tâm là cấu hình lại nơi Ant và generator **ghi file**, sau đó dùng Git ignore như biện pháp bổ sung.

## 3. Bố cục thư mục đề xuất

Với ứng dụng Java đơn giản, có thể dùng một gốc đầu ra `.ant-out/` tại cấp project:

```text
portable-ant-project/
├── .gitignore
├── build.xml
├── src/                                # nguồn được quản lý
│   └── main/
│       ├── java/demo/App.java
│       └── resources/                  # tài nguyên do người viết (tùy chọn)
├── templates/                          # template generator (nếu có)
└── .ant-out/                           # sinh tự động, Git bỏ qua
    ├── generated-sources/
    │   └── java/demo/generated/GeneratedMessage.java
    ├── generated-resources/
    │   └── build-info.properties
    ├── classes/
    │   ├── demo/App.class
    │   ├── demo/generated/GeneratedMessage.class
    │   └── build-info.properties
    ├── reports/
    ├── logs/
    ├── temp/
    └── dist/
        └── demo.jar
```

Các nguyên tắc trong cấu trúc này:

- **`src/` chỉ chứa source/tài nguyên đầu vào được quản lý**. Ant không biên dịch `.class` vào đây.
- **`generated-sources/` chỉ chứa source do công cụ tạo**. Trình biên dịch có thể đọc chúng sau khi bước generate hoàn thành.
- **`generated-resources/` chứa file tài nguyên do build tạo**. Chúng được copy vào `classes/` nếu cần đóng gói.
- **`classes/` và `dist/` là kết quả xử lý**; có thể xóa rồi tạo lại.
- **`reports/`, `logs/`, `temp/`** giúp các công cụ có chỗ ghi riêng thay vì tạo file bên cạnh mã nguồn.

Đặt đầu ra trong repository nhưng ngoài `src/` là một giải pháp đơn giản và thông dụng. “Ngoài vùng mã nguồn được quản lý” **không bắt buộc** phải là thư mục nằm ngoài toàn bộ checkout; điều quan trọng là đầu ra không trở thành file nguồn do Git quản lý và có một phạm vi rõ ràng để dọn. Với dự án nhiều module hoặc nhiều job CI dùng chung workspace, mở rộng thành `.ant-out/<module>/<run-id>/...` để tách quyền sở hữu đầu ra.

## 4. Ví dụ hoàn chỉnh: Ant sinh source rồi biên dịch ở thư mục riêng

Ví dụ dưới đây tự tạo một lớp Java đơn giản từ Ant để minh họa đường đi của file do generator tạo ra. Generator thực tế có thể là JAXB, ANTLR, OpenAPI Generator hoặc công cụ nội bộ; nguyên tắc chỉ định **thư mục đầu ra riêng** vẫn giống nhau.

Chuẩn bị mã người viết trong `src/main/java/demo/App.java`:

```java
package demo;

import demo.generated.GeneratedMessage;

public class App {
    public static void main(String[] args) {
        System.out.println(GeneratedMessage.text());
    }
}
```

File `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="clean-source-tree" default="dist" basedir=".">

    <!-- Thư mục chỉ đọc từ góc nhìn build. -->
    <property name="src.dir" location="src/main/java"/>
    <property name="authored.resources.dir"
              location="src/main/resources"/>

    <!-- Mọi đầu ra thuộc một gốc riêng. -->
    <property name="output.dir" location=".ant-out"/>
    <property name="generated.src.dir"
              location="${output.dir}/generated-sources/java"/>
    <property name="generated.resources.dir"
              location="${output.dir}/generated-resources"/>
    <property name="classes.dir" location="${output.dir}/classes"/>
    <property name="reports.dir" location="${output.dir}/reports"/>
    <property name="logs.dir" location="${output.dir}/logs"/>
    <property name="temp.dir" location="${output.dir}/temp"/>
    <property name="dist.dir" location="${output.dir}/dist"/>
    <property name="jar.file" location="${dist.dir}/demo.jar"/>

    <target name="validate">
        <available file="${src.dir}"
                   type="dir"
                   property="source.exists"/>
        <fail unless="source.exists"
              message="Không tìm thấy source: ${src.dir}"/>
    </target>

    <target name="prepare" depends="validate">
        <mkdir dir="${generated.src.dir}/demo/generated"/>
        <mkdir dir="${generated.resources.dir}"/>
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${logs.dir}"/>
        <mkdir dir="${temp.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <!-- Ví dụ công cụ sinh mã: chỉ ghi vào generated-sources. -->
    <target name="generate" depends="prepare">
        <echo file="${generated.src.dir}/demo/generated/GeneratedMessage.java"
              encoding="UTF-8"><![CDATA[
package demo.generated;

public final class GeneratedMessage {
    private GeneratedMessage() {}

    public static String text() {
        return "Hello from generated Java source";
    }
}
]]></echo>

        <!-- Sinh một resource để minh họa bước đóng gói. -->
        <echo file="${generated.resources.dir}/build-info.properties"
              encoding="UTF-8">application.name=clean-source-tree</echo>
    </target>

    <!-- javac đọc cả source do người viết và source đã sinh.
         .class chỉ được ghi vào classes.dir. -->
    <target name="compile" depends="generate">
        <javac destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false">
            <src path="${src.dir}"/>
            <src path="${generated.src.dir}"/>
        </javac>
    </target>

    <!-- Đưa resource vào classpath, không sửa thư mục src. -->
    <target name="copy-resources" depends="generate">
        <copy todir="${classes.dir}">
            <fileset dir="${authored.resources.dir}"
                     erroronmissingdir="false"/>
            <fileset dir="${generated.resources.dir}"/>
        </copy>
    </target>

    <target name="dist" depends="compile,copy-resources">
        <jar destfile="${jar.file}" basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="demo.App"/>
            </manifest>
        </jar>
        <echo message="Sản phẩm: ${jar.file}"/>
    </target>

    <!-- Clean chỉ tác động vào vùng Ant sở hữu. -->
    <target name="clean">
        <delete dir="${output.dir}"/>
    </target>
</project>
```

Yêu cầu môi trường: **Apache Ant có hỗ trợ thuộc tính `release` của `<javac>` và JDK 17 trở lên**. Ví dụ sử dụng API task chuẩn của Ant; không yêu cầu thư viện bên ngoài để sinh lớp mẫu. `src/main/resources` là thư mục tùy chọn, được xử lý bằng `erroronmissingdir="false"`.

Chạy từ gốc dự án:

```bash
# Tạo đầu ra sạch rồi sinh mã, biên dịch và đóng gói:
ant -f build.xml clean dist

# Chạy JAR đã đóng gói:
java -jar .ant-out/dist/demo.jar
```

Thông báo mong đợi từ ứng dụng:

```text
Hello from generated Java source
```

Trong quá trình chạy, Ant đọc `App.java` trong `src/main/java`, tạo `GeneratedMessage.java` dưới `.ant-out/generated-sources/java`, biên dịch cả hai tập source vào `.ant-out/classes` rồi đóng gói thành `.ant-out/dist/demo.jar`. Không có tác vụ nào ghi lại `src/main/java/demo/App.java` hoặc tạo `.class` dưới `src/`.

### 4.1. Cách luồng dữ liệu bảo vệ source

```text
  src/main/java/               templates / generator config
   (do người viết)                       |
          |                              v
          |                   .ant-out/generated-sources/
          |                              |
          +--------------+---------------+
                         |
                         v
                       javac
                         |
                         v
                .ant-out/classes/
                         ^
                         |
   src/main/resources/    +--- .ant-out/generated-resources/
          |                           |
          +---------> copy <----------+
                         |
                         v
                    jar / dist
                         |
                         v
                 .ant-out/dist/demo.jar
```

Mọi mũi tên từ `src/` hướng **ra ngoài**. Các bước generate, compile, copy và package có thể thay đổi nội dung trong `.ant-out/`, nhưng không thay đổi đầu vào do lập trình viên quản lý. Khi có lỗi, có thể xóa cả `.ant-out/` rồi tạo lại mà không cần khôi phục source.

### 4.2. Vì sao `<src>` được khai báo thành hai phần?

`<javac>` cần biết cả source viết tay và source do generator tạo. Cấu hình:

```xml
<javac destdir="${classes.dir}"
       includeantruntime="false"
       release="17">
    <src path="${src.dir}"/>
    <src path="${generated.src.dir}"/>
</javac>
```

cho phép Ant biên dịch hai cây source vào **một cây class**. Không cần chuyển source đã sinh vào `src/main/java` để compiler nhìn thấy. Việc khai báo từng đường dẫn qua `<src>` cũng tránh tự nối danh sách đường dẫn bằng dấu `:` hoặc `;` khác nhau giữa hệ điều hành.

Một số generator tự tạo JAR hoặc tài nguyên khác mà không sinh file `.java`; khi đó chỉ cần trỏ điểm ghi của công cụ về nhánh thích hợp dưới `.ant-out/`. Không cần tạo cây `generated-sources` nếu loại build đó không có generated source.

### 4.3. Làm sạch đầu ra và build lại

Target `clean` chỉ xóa `${output.dir}`, tức `.ant-out/` với cấu hình mặc định. Target `dist` tạo lại thư mục và file đầu ra. Điều này có hai lợi ích:

1. Một source đã bị xóa sẽ không để lại `.class` cũ trong JAR của lượt build sạch.
2. Generator đổi tên/loại bỏ output sẽ không làm file sinh cũ tiếp tục xuất hiện trong biên dịch.

Tuy nhiên, **`clean` không nên trở thành lệnh xóa tùy ý**. Ví dụ đặt `<delete dir="src"/>` hoặc `<delete dir="${basedir}"/>` là sai ranh giới sở hữu. Ant cho phép override property qua `-D`, nên trong CI chỉ chấp nhận giá trị đường dẫn đầu ra từ cấu hình đáng tin cậy; không truyền trực tiếp một đường dẫn xóa có thể do người dùng chưa kiểm soát cung cấp.

## 5. Dùng `.gitignore` đúng vai trò

File `.gitignore` ở gốc repository:

```gitignore
# Đầu ra của Apache Ant
/.ant-out/

# Nếu dự án còn sử dụng các thư mục output cũ, xem xét thêm:
# /build/
# /dist/
```

Với mẫu `/.ant-out/`, dấu `/` đầu tiên giới hạn quy tắc ở thư mục gốc repository. Git bỏ qua file **chưa được theo dõi** xuất hiện dưới nhánh này; các file nguồn như `src/main/java/demo/App.java` vẫn là dữ liệu quản lý bình thường.

Có thể dùng:

```bash
# Xem trạng thái working tree (file được ignore thường không hiện):
git status --short

# Kiểm tra Git có quy tắc ignore áp dụng cho file sinh không:
git check-ignore -v .ant-out/dist/demo.jar

# Kiểm tra có file nào trong output đang được Git theo dõi:
git ls-files .ant-out
```

**`.gitignore` không tự bỏ theo dõi file đã được commit từ trước.** Nếu output cũ đã bị đưa vào Git, nhóm phát triển phải quyết định chính xác file nào là đầu ra có thể tái tạo và thực hiện thao tác bỏ chúng khỏi Git index trong một thay đổi riêng. Với một file chắc chắn chỉ là đầu ra sinh:

```bash
# Ví dụ: bỏ theo dõi đúng một file, giữ bản sao trong workspace:
git rm --cached -- .ant-out/dist/demo.jar
```

Lệnh `git rm --cached` tạo thay đổi xóa file khỏi **index** để đưa vào commit sau, nhưng giữ file trong workspace; hãy review danh sách file định bỏ theo dõi trước khi commit. Không thực hiện lệnh rộng trên `src/` vì có thể loại nhầm mã nguồn thực sự cần quản lý.

`.gitignore` chỉ là một lớp bảo vệ về quản lý phiên bản. Nó **không ngăn** Ant ghi vào vị trí sai, **không xóa** file đầu ra cũ, và **không đảm bảo** một công cụ khác không lấy nhầm file đã bỏ qua. Giải pháp gốc vẫn là định nghĩa đường dẫn đầu ra đúng ngay trong task.

## 6. Di chuyển một build Ant cũ đang sinh file vào source

Giả sử `build.xml` ban đầu có:

```xml
<!-- Trạng thái cũ: generated Java nằm lẫn trong source viết tay. -->
<property name="generated.dir" location="src/main/java/demo/generated"/>

<target name="generate">
    <!-- Generator giả định dùng generated.dir làm thư mục xuất mã. -->
    <!-- ... -->
</target>
```

Không nên chỉ thêm `src/main/java/demo/generated/` vào `.gitignore`. Cần thay nơi generator ghi:

```xml
<!-- Trạng thái mới: generated source ở ngoài vùng source quản lý. -->
<property name="generated.dir"
          location=".ant-out/generated-sources/java"/>
```

Đồng thời, sửa các target tiêu thụ kết quả:

```xml
<javac destdir="${classes.dir}"
       includeantruntime="false"
       release="17">
    <src path="${src.dir}"/>
    <src path="${generated.dir}"/>
</javac>
```

Quy trình di chuyển thường cần xem xét từng khâu:

1. **Xác định nguồn tạo file:** generator, template và cấu hình là nguồn sự thật; không sửa generated Java như source chính.
2. **Thay đầu ra generator:** sử dụng thư mục riêng như `.ant-out/generated-sources/java` hoặc `build/generated-sources`.
3. **Thay các đường dẫn đầu vào của bước sau:** `javac`, Javadoc, test, copy, jar và IDE phải trỏ tới vị trí mới khi cần.
4. **Xử lý generated file cũ:** phân loại chính xác file nào thật sự sinh tự động và file nào đã được chỉnh sửa thủ công; giải quyết thay đổi có giá trị trước khi bỏ theo dõi hay dọn.
5. **Giới hạn lệnh `clean`:** chỉ xóa vùng mới mà generator sở hữu, tránh xóa thư mục nguồn.
6. **Thiết lập `.gitignore`:** loại đầu ra mới khỏi Git; chính sách cho file đã được commit trước đó cần thay đổi index có review.
7. **Cho IDE biết thư mục source sinh:** nếu IDE cần nhận diện, đăng ký `.ant-out/generated-sources/java` là generated source root theo tính năng IDE, thay vì chuyển file ngược về `src/`.

Đường dẫn đến generated source phải được thiết lập **sau khi generator chạy** nếu nó chưa tồn tại ở clean checkout. Tránh giả định developer đã chạy Ant trước khi IDE hoặc CI khởi động. Có thể thêm một target `generate` rõ ràng cho bước chuẩn bị.

## 7. Tách đúng từng loại sản phẩm sinh ra

Không phải mọi output đều đi vào một thư mục con chung. Nếu trộn generated source, JAR, XML báo cáo và file tạm, các bước dọn dẹp và kiểm tra sẽ khó phân biệt file nào còn cần thiết. Một số quy ước thực tế:

| Công việc | Ví dụ cấu hình Ant | Nơi đầu ra |
|---|---|---|
| Sinh source Java | Tham số `destdir`/`outputDirectory` của generator | `.ant-out/generated-sources/java/` |
| Biên dịch Java | `<javac destdir="${classes.dir}"/>` | `.ant-out/classes/` |
| Copy tài nguyên hoặc sinh cấu hình runtime | `<copy todir="${classes.dir}">...` | `.ant-out/classes/`, từ nguồn trong `generated-resources/` |
| Đóng gói ứng dụng | `<jar destfile="${dist.dir}/demo.jar" .../>` | `.ant-out/dist/` |
| Tạo Javadoc | `<javadoc destdir="${output.dir}/docs" .../>` | `.ant-out/docs/` |
| Lưu XML JUnit | `<batchtest todir="${reports.dir}/junit">...` | `.ant-out/reports/junit/` |
| Chuyển đổi file, sinh tài liệu, xử lý template | Thuộc tính output của tác vụ tương ứng | `.ant-out/generated-resources/` hoặc `.ant-out/docs/` |
| Log và file tạm của công cụ ngoài | Tham số output/log/temp của chính chương trình đó | `.ant-out/logs/`, `.ant-out/temp/` |

Với các task `<exec>` gọi script hoặc tool ngoài, phải kiểm tra **thư mục làm việc** và các đường dẫn mặc định của tool. Không có bảo đảm rằng mọi chương trình con tự sử dụng `.ant-out/` chỉ vì Ant có property `output.dir`; hãy truyền đường dẫn đầu ra tường minh cho từng công cụ.

### 7.1. Compiler, annotation processor và source do công cụ tạo

`<javac destdir="...">` xác định nơi compiler ghi `.class`. Nhưng một annotation processor Java có thể sinh thêm `.java` hoặc resource. Các trình biên dịch/toolchain có cách chỉ định nơi sinh source riêng (chẳng hạn tùy chọn `-s` của `javac` cho generated sources). Nếu dự án dùng annotation processing, cần cấu hình **cả** nơi sinh `.java` và nơi ghi `.class`, để chúng không vô tình nằm trong `src/main/java`.

Tránh vừa cho annotation processor sinh source tự động trong một lượt `javac` vừa đưa toàn bộ thư mục generated source cũ vào source path mà không có quy tắc rõ, vì có thể dẫn tới biên dịch trùng hoặc nạp file lỗi thời. Với build có generator phức tạp, tách thành target `generate` và target `compile`, khai báo dependencies, đầu ra, logic làm sạch và điều kiện incremental một cách minh bạch.

### 7.2. Tài nguyên do build xử lý

Một file cấu hình nguồn có thể nằm ở `src/main/resources/application.properties`, còn bản thay placeholder hoặc ghép dữ liệu từ build nên được ghi vào `.ant-out/generated-resources/` trước khi copy sang `classes/`. Không xử lý thay thế trực tiếp trên bản nguồn:

```xml
<!-- Có thể đọc file nguồn và ghi bản đã xử lý vào output riêng. -->
<copy file="src/main/resources/app-template.properties"
      tofile="${generated.resources.dir}/app.properties">
    <filterset>
        <filter token="APPLICATION_NAME" value="demo"/>
    </filterset>
</copy>
```

Khi dùng filter, chọn chính xác tài nguyên cần biến đổi; không chạy filter thay thế trên file nhị phân. Với build tái lập, các giá trị được thế vào nên đến từ cấu hình rõ ràng, không phụ thuộc âm thầm vào máy phát triển.

### 7.3. Tài liệu, báo cáo và sản phẩm phân phối

Generated Javadoc, JUnit XML, báo cáo coverage, checksum và JAR đều có thể được lưu lại dưới dạng **CI artifact** khi cần; việc đó không đòi hỏi commit vào Git. Pipeline có thể upload những nhánh như `.ant-out/reports/` và `.ant-out/dist/` sau build. Artifact CI là bản chụp của một lần chạy và có thời hạn/quyền truy cập riêng; **không phải nguồn mã được quản lý**.

## 8. Clean build, incremental build và file cũ

Việc có một vùng output riêng giúp xử lý hai cách build:

**Build sạch:**

```bash
ant -f build.xml clean dist
```

Toàn bộ output cũ bị xóa, generator tạo lại source và resource, compiler biên dịch rồi đóng gói. Cách này thích hợp để đối chiếu kết quả từ clean checkout hoặc xử lý lỗi class/file cũ.

**Build tăng dần:**

```bash
ant -f build.xml dist
```

Ant và các công cụ liên quan có thể tái sử dụng file đã có nếu mục tiêu/tác vụ hỗ trợ. Nhưng công cụ tạo source cần xử lý trường hợp input đã bị xóa hoặc đổi tên; chỉ dựa vào thời gian sửa file có thể để lại sản phẩm không còn hợp lệ. Một generator ghi đè file dù nội dung không đổi cũng làm timestamp mới khiến compiler biên dịch lại không cần thiết.

Ở ví dụ nhỏ trong mục 4, task `<echo>` ghi lại generated Java mỗi khi gọi `generate`. Đây là cách minh họa luồng đường dẫn, không phải cơ chế incremental tối ưu. Với generator thực tế, nên cân nhắc so sánh input/output, dùng checksum hoặc cơ chế up-to-date do tool hỗ trợ, và dọn các file cũ thuộc phạm vi generator khi đầu vào thay đổi.

Việc generated output nằm ngoài `src/` khiến thao tác dọn sạch dễ hơn nhưng **không tự động bảo đảm build tái lập**. Hai lần build cùng source vẫn có thể khác nhau nếu toolchain, dependency, locale, timestamp trong JAR hoặc môi trường thay đổi. Đầu ra phải nằm ở nơi rõ ràng để kiểm tra sự khác biệt, và các đầu vào quan trọng phải được cố định theo yêu cầu dự án.

## 9. Cân nhắc với Git, IDE, CI và nhiều module

### Git: giảm nhiễu nhưng không che thay đổi thật

Giữ nguồn được quản lý trong cây riêng giúp `git diff` chỉ tập trung vào chỉnh sửa cần review. Tuy nhiên, không nên bỏ qua bừa bãi các file cấu hình, test fixture hay template chỉ vì chúng nằm trong thư mục có chữ “generated”. Một thư mục có thể chứa cả file đầu vào đã được duyệt và file đầu ra; cần đổi cấu trúc trước, rồi viết quy tắc ignore đúng phạm vi.

### IDE: dùng generated source root có chủ đích

Nếu IDE cần gợi ý mã trong source do generator tạo, hãy cấu hình IDE hoặc integration build để nhận diện `.ant-out/generated-sources/java` sau khi generate. Đừng copy trở lại `src/main/java` chỉ để IDE hiển thị import; điều đó khiến cơ chế build và công cụ phát triển có hai nguồn sự thật.

### CI: giữ workspace sạch, artifact ở ngoài source

Trên CI, một clean checkout có thể chưa có `.ant-out/`. Target `prepare` và `generate` phải đủ khả năng tạo toàn bộ cây đầu ra từ đầu vào được version-control. Job upload JAR hoặc báo cáo có thể trỏ vào `.ant-out/dist/` và `.ant-out/reports/`. Nếu CI dùng cache cho dependency, tách cache khỏi artifact và không sử dụng cache như nguồn source bắt buộc.

### Multi-module: tách quyền sở hữu

Repository nhiều module có thể có `.ant-out/module-a/` và `.ant-out/module-b/`; CI nhiều lần chạy song song còn cần một nhánh `run-id` hoặc workspace riêng. Khi đó target `clean` của module A chỉ được dọn vùng module A sở hữu. Tránh lệnh `<delete dir="${basedir}/.ant-out"/>` trong một build con nếu nó có thể xóa output của các module khác đang chạy.

Ví dụ công thức đường dẫn:

```text
<repository>/.ant-out/<module-id>/<run-id>/
    generated-sources/
    generated-resources/
    classes/
    reports/
    dist/
```

Cần kiểm soát định dạng `module-id`/`run-id` để không chứa các đoạn như `../`, và không cho một giá trị chưa được tin cậy ghi đè property dùng trong `<delete>`. Hai job chạy đồng thời phải có đường dẫn sở hữu khác nhau.

## 10. Những lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Cách tổ chức tốt hơn |
|---|---|---|
| `javac` ghi `.class` vào `src/main/java` | Source tree có file nhị phân, dễ lẫn mã nguồn | Khai báo `destdir` trong `.ant-out/classes`. |
| Generator ghi thẳng `.java` vào `src/main/java` | Chỉnh sửa thủ công dễ bị ghi đè; Git diff nhiễu | Sinh vào `.ant-out/generated-sources/java` rồi thêm vào `<javac>` source path. |
| Copy resource đã biến đổi đè lên file nguồn | Mất bản cấu hình gốc hoặc khó review | Ghi bản đã xử lý vào `generated-resources` và copy sang `classes`. |
| Chỉ cấu hình `.gitignore` mà không đổi điểm ghi | File đầu ra vẫn làm bẩn cây source, dễ bị công cụ khác dùng nhầm | Sửa đường dẫn output tại từng task/generator. |
| Dùng `clean` xóa cả `src/` hoặc gốc repository | Có nguy cơ mất dữ liệu nguồn | Chỉ xóa thư mục output do build sở hữu. |
| Xóa generated code đã được người khác chỉnh tay mà không phân loại | Mất thay đổi có giá trị | Phân định ownership và xử lý việc chuyển đổi qua review. |
| Sinh file nhưng quên khai báo với `javac` hoặc IDE | Compiler không tìm thấy lớp; IDE báo lỗi import | Thêm generated source root làm đầu vào sau bước generate. |
| Reuse output giữa các module hoặc job | File bị đè, một job clean làm lỗi job khác | Tách output theo module/job/run hoặc workspace. |
| Artifact CI được commit như source | Git phình to, khó truy vết, binary stale | Đưa JAR/report vào vùng output bỏ qua bởi Git; xuất bản qua CI. |
| Coi mọi generated file đều được phép xóa | Có thể mất snapshot/tài liệu được quản lý có chủ đích | Xác định file nào thực sự có thể tái tạo và thuộc phạm vi clean. |

## 11. Bài thực hành quan sát

Với ví dụ mục 4, có thể thực hiện lần lượt:

1. Tạo `src/main/java/demo/App.java` và `build.xml`, thêm `/.ant-out/` vào `.gitignore`.
2. Chạy `ant -f build.xml clean dist`. Quan sát `GeneratedMessage.java` chỉ xuất hiện dưới `.ant-out/generated-sources/java`, còn `App.java` vẫn ở `src/main/java`.
3. Mở `.ant-out/classes` để thấy hai lớp Java đã biên dịch; mở `.ant-out/dist/demo.jar` bằng công cụ đọc ZIP/JAR và xác định tài nguyên `build-info.properties` đã được copy vào sản phẩm.
4. Chạy `git status --short`, `git check-ignore -v .ant-out/dist/demo.jar` và `git ls-files .ant-out` để phân biệt file chưa được theo dõi, file bị ignore và file thực sự có trong Git index.
5. Chạy `ant -f build.xml clean` rồi quan sát `src/main/java/demo/App.java` vẫn còn, trong khi cây `.ant-out/` đã bị xóa.
6. Chạy lại `ant -f build.xml dist` từ đầu ra trống để thấy source và resource được tạo lại không cần copy file sinh từ máy khác.

Bài thực hành này nhấn mạnh **ranh giới sở hữu đường dẫn**: nguồn được quản lý là đầu vào; source sinh tự động, class, báo cáo và JAR là đầu ra có thể tái tạo. Một script Ant dễ bảo trì làm ranh giới đó thể hiện ngay trong property, dependencies giữa target, cấu hình từng task và phạm vi `clean`. Khi ranh giới rõ ràng, việc review, reset workspace, chạy CI và mở rộng generator đều ít rủi ro hơn.

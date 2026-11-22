# Xử lý dấu cách, Unicode và phân biệt chữ hoa, chữ thường trong tên tệp khi dùng Apache Ant

## 1. Vì sao tên tệp là vấn đề của build đa nền tảng?

Một dự án Java sử dụng **Apache Ant** có thể build tốt trên máy phát triển nhưng lỗi khi chuyển sang Windows, Linux, macOS hoặc runner CI khác. Nguyên nhân đôi khi không nằm ở Java hay dependency, mà ở cách đặt tên và tham chiếu tệp:

- Đường dẫn chứa **dấu cách** như `Dự án thử nghiệm/Mã nguồn/App.java` bị tách thành nhiều đối số khi chuyển qua shell.
- Tên có **Unicode** như `Tài nguyên/Cấu hình tiếng Việt.txt` bị đọc hoặc ghi sai mã hóa, hoặc hai tên trông giống nhau thực chất gồm các mã Unicode khác nhau.
- Tên khác **chữ hoa/chữ thường** như `Config.xml` và `config.xml` có thể được xem là hai tệp riêng trên một filesystem, nhưng va chạm trên filesystem khác.

Ant hỗ trợ đường dẫn trực tiếp qua các thuộc tính XML của task, chẳng hạn `<javac>`, `<copy>`, `<fileset>`, `<jar>` và `<exec>`. Tuy nhiên, khả năng chạy đa nền tảng còn phụ thuộc vào filesystem, shell, JDK, bộ công cụ ngoài và cách dự án tổ chức tên tệp.

**Mục tiêu của bài:** xây dựng một cách làm nhất quán để Ant tham chiếu chính xác tên tệp có dấu cách/Unicode và phát hiện sớm lỗi phân biệt chữ hoa, chữ thường khi chuyển môi trường.

### Ba lớp cần phân biệt

| Lớp | Ví dụ | Quy tắc cần nhớ |
| --- | --- | --- |
| **XML và thuộc tính của Ant** | `<copy file="Tài liệu hướng dẫn.txt" .../>` | Giá trị thuộc tính XML là một chuỗi; dấu cách không tự chia thành đối số. |
| **Lệnh/đối số của tiến trình ngoài** | `ant -f "Dự án ví dụ/build.xml"`, `<exec>` | Shell có quy tắc quote; Ant `<arg value>` / `<arg file>` có thể truyền từng đối số riêng. |
| **Filesystem** | `README.md` so với `Readme.md` | Hệ thống lưu trữ quyết định có phân biệt hoa/thường và xử lý Unicode thế nào. |

Một lỗi thường gặp là cố “chữa” ở lớp XML một vấn đề thực ra phát sinh khi đi qua shell, hoặc tin rằng thay mã hóa nguồn Java có thể tự động sửa cách filesystem nhận diện tên tệp. Cần kiểm tra đúng lớp.

## 2. Quy ước đặt tên và đường dẫn để giảm lỗi

Trước khi viết task, thống nhất một số quy ước:

1. Dùng **một cách viết chính xác** cho mỗi đường dẫn trong mã nguồn, tài nguyên, script và tài liệu build. Không dựa vào việc filesystem “tự hiểu” khác biệt hoa/thường.
2. Ưu tiên tên ổn định, không tạo hai tệp chỉ khác chữ hoa/chữ thường hoặc dạng chuẩn hóa Unicode.
3. Với tên tệp do người dùng cung cấp, **chấp nhận dấu cách và Unicode** bằng API đường dẫn/đối số đúng cách; không bắt người dùng đổi tên để né lỗi.
4. Dùng dấu `/` trong đường dẫn tương đối của `build.xml` và pattern Ant, ngay cả khi chạy trên Windows. Ant/Java xử lý đường phân cách filesystem trong các task file thông thường.
5. Lấy đường dẫn từ `${basedir}` hoặc thuộc tính khai báo bằng `location`; tránh tự nối chuỗi bằng dấu `;`, `:` hoặc `\` khi công cụ đã có kiểu dữ liệu đường dẫn.
6. Giới hạn tên tệp và thư mục có thể xung đột với nền tảng cần hỗ trợ; ví dụ Windows còn có tên thiết bị dành riêng, ký tự cấm và những hạn chế riêng đối với dấu cách/dấu chấm ở cuối tên.

**Quan trọng:** Windows thường dùng filesystem không phân biệt hoa/thường, Linux thường dùng filesystem có phân biệt, macOS có nhiều tùy chọn tùy ổ đĩa. Đây là **thuộc tính của filesystem/volume**, không phải quy tắc bất biến của tên hệ điều hành. Vì vậy không kiểm tra bằng giả định “đã là Windows thì luôn không phân biệt”.

## 3. Ant xử lý dấu cách khi dùng task tích hợp

Hãy bắt đầu từ một dự án có tên thư mục, thư mục nguồn và tệp đầu ra đều chứa dấu cách hoặc ký tự tiếng Việt:

```text
Dự án Ant/
├── build.xml
├── Mã nguồn/
│   └── vn/
│       └── demo/
│           └── App.java
└── Tài nguyên/
    └── Cấu hình mặc định.txt
```

Nội dung `Mã nguồn/vn/demo/App.java`:

```java
package vn.demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Xin chào từ Apache Ant");
    }
}
```

Tạo `build.xml` và **lưu tệp ở UTF-8**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="unicode-path-demo" default="package" basedir=".">

    <!-- location: đổi đường dẫn tương đối thành đường dẫn tuyệt đối -->
    <property name="source.dir" location="Mã nguồn"/>
    <property name="resources.dir" location="Tài nguyên"/>
    <property name="classes.dir" location="build output/classes"/>
    <property name="dist.dir" location="Bản phát hành"/>

    <target name="clean">
        <delete dir="${basedir}/build output"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${source.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false"/>
    </target>

    <target name="copy-resources" depends="compile">
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}" casesensitive="true">
                <include name="**/*.txt"/>
            </fileset>
        </copy>
    </target>

    <target name="package" depends="copy-resources">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/Ứng dụng thử.jar"
             basedir="${classes.dir}"
             encoding="UTF-8">
            <manifest>
                <attribute name="Main-Class" value="vn.demo.App"/>
            </manifest>
        </jar>
    </target>

</project>
```

Đứng ở thư mục cha của dự án và chạy:

```bash
ant -f "./Dự án Ant/build.xml" clean package
java -jar "./Dự án Ant/Bản phát hành/Ứng dụng thử.jar"
```

Khi có đủ JDK (ví dụ JDK 17+) và Ant hỗ trợ thuộc tính `release` của `javac`, lệnh sẽ biên dịch lớp Java, sao chép tài nguyên và đóng gói JAR. Tên thư mục chứa dấu cách vẫn được xử lý vì `<mkdir>`, `<javac>`, `<copy>` và `<jar>` nhận đường dẫn qua **thuộc tính XML**, không thông qua việc cắt chuỗi bằng khoảng trắng như shell.

Các điểm cần hiểu trong ví dụ:

- `<property ... location="Mã nguồn"/>` diễn giải vị trí tương đối theo `basedir` của project và lưu đường dẫn tuyệt đối. `<property ... value="Mã nguồn"/>` chỉ lưu nguyên chuỗi; dùng `location` giúp ý nghĩa “đây là đường dẫn” rõ ràng.
- `<copy todir="${classes.dir}">` truyền cả tên thư mục, kể cả dấu cách và Unicode, dưới dạng một giá trị.
- `<fileset>` dùng đường dẫn tương đối bên trong thư mục gốc `dir`; pattern `**/*.txt` có dấu `/` và không cần quote riêng.
- `encoding="UTF-8"` trên `<javac>` điều khiển **mã hóa nội dung mã nguồn**, không phải cách quote tên tệp. Hai vấn đề khác nhau.
- `encoding="UTF-8"` trên `<jar>` liên quan tới mã hóa **tên entry trong ZIP/JAR**. Hệ thống đọc ZIP rất cũ hoặc công cụ giải nén không hỗ trợ đúng UTF-8 vẫn có thể hiển thị sai tên entry.
- `<delete>` sẽ xóa đúng các thư mục được chỉ định. Trong dự án khác, cần xem target `clean` trước khi chạy vì target đó có thể xóa đầu ra không thể khôi phục.

### Không tự chèn dấu nháy vào giá trị đường dẫn của Ant

Ví dụ **không nên dùng**:

```xml
<!-- Dấu nháy có thể trở thành ký tự thật trong đường dẫn -->
<property name="source.dir" value="&quot;Mã nguồn&quot;"/>
<javac srcdir="${source.dir}" destdir="build/classes"/>
```

Cách đúng:

```xml
<property name="source.dir" location="Mã nguồn"/>
<javac srcdir="${source.dir}"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false"/>
```

Dấu `"` trong cú pháp XML chỉ bao quanh **giá trị thuộc tính**; không phải dấu nháy sẽ được chuyển tiếp cho filesystem. Chỉ quote khi gọi lệnh từ shell, hoặc khi **chính định dạng dữ liệu** thực sự cần ký tự nháy.

## 4. Quote đúng khi gọi `ant` từ shell

Ngay cả khi `build.xml` viết đúng, lệnh khởi động từ terminal vẫn có thể sai vì dấu cách.

Ví dụ lỗi trong Bash:

```bash
# Shell tách đường dẫn thành nhiều token
ant -f ./Dự án Ant/build.xml clean package
```

Cách đúng trên Bash và thông thường cả PowerShell:

```bash
ant -f "./Dự án Ant/build.xml" clean package
```

Nếu truyền property qua `-D`, cần giữ **toàn bộ tham số** là một đối số:

```bash
ant -f "./Dự án Ant/build.xml" \
  "-Dinput.file=./Dữ liệu khách hàng/đơn hàng 01.csv" package
```

Đường dẫn này cần được task trong `build.xml` sử dụng và phân giải theo đúng thư mục làm việc hoặc `basedir` đã thỏa thuận. Trong PowerShell có thể đặt lệnh trên một dòng để tránh sự khác biệt cú pháp nối dòng:

```powershell
ant -f "./Dự án Ant/build.xml" "-Dinput.file=./Dữ liệu khách hàng/đơn hàng 01.csv" package
```

**Phân biệt:** dấu nháy ở lệnh terminal giúp shell giữ đối số; dấu nháy không phải một phần của tên tệp mà Ant cần tìm.

Khi viết batch file, Bash script hoặc PowerShell script gọi Ant, hãy dùng cú pháp quote phù hợp với **shell đó**. Ví dụ trên Bash, thường dùng `"$variable"` cho một đường dẫn biến, còn trong PowerShell là `"$variable"` hoặc dùng cmdlet với `-LiteralPath` khi thao tác tệp có ký tự đặc biệt. Không sao chép nguyên công thức escape của shell này sang shell khác.

## 5. Truyền tên tệp có dấu cách qua `<exec>`

Task Ant tích hợp thường đã quản lý đường dẫn giúp ta. Khi gọi chương trình ngoài bằng `<exec>`, điều quan trọng là **phân biệt từng đối số**. Ant có kiểu `<arg>` hỗ trợ việc này.

Giả sử cần chạy JAR và chuyển tên tệp dữ liệu:

```xml
<property name="input.file"
          location="Dữ liệu khách hàng/đơn hàng 01.csv"/>

<target name="run-tool" depends="package">
    <exec executable="java"
          dir="${basedir}"
          failonerror="true">
        <arg value="-jar"/>
        <arg file="${dist.dir}/Ứng dụng thử.jar"/>
        <arg value="--input"/>
        <arg file="${input.file}"/>
    </exec>
</target>
```

Ví dụ giả định chương trình đích chấp nhận tùy chọn `--input`; class `App` ở phần trên chỉ in lời chào, không xử lý tùy chọn này. Điểm cần học là Ant đưa tới tiến trình ngoài bốn đối số riêng:

```text
argv[0] = -jar
argv[1] = <đường dẫn tuyệt đối>/Bản phát hành/Ứng dụng thử.jar
argv[2] = --input
argv[3] = <đường dẫn tuyệt đối>/Dữ liệu khách hàng/đơn hàng 01.csv
```

Tên tệp trong `argv[3]` **không bị tách** tại dấu cách. Cả `<arg file="..."/>` và `<arg value="..."/>` đều tạo một đối số; thuộc tính `file` có thêm ý nghĩa chuyển đường dẫn thành tên file tuyệt đối thích hợp.

Cách dễ gây lỗi:

```xml
<!-- Tránh ghép tùy chọn và đường dẫn thành một chuỗi -->
<arg line="--input ${input.file}"/>
```

Với `line`, Ant phải phân tích một chuỗi lệnh thành các token. Khi `${input.file}` có dấu cách, quá trình phân tích có thể làm sai số đối số hoặc bắt buộc thêm quy tắc quote. Đặc biệt **không** dùng `<arg value="--input ${input.file}"/>` nếu công cụ yêu cầu hai đối số tách biệt: dạng đó là **một** đối số chứa khoảng trắng.

**Quy tắc thực hành:** mỗi tùy chọn/đường dẫn là một `<arg>` riêng. Ưu tiên `<java>` khi chạy trực tiếp một class Java hoặc JAR theo API của Ant, và chỉ dùng `<exec>` khi thật sự cần tiến trình ngoài. Tránh ghép chuỗi shell dài qua `cmd /c` hay `sh -c` trừ khi chức năng shell là yêu cầu có chủ đích; khi qua shell, lại phải xử lý thêm một lớp escape.

### Đường dẫn trong classpath: dùng `<path>`, `classpathref`

Classpath trên Windows thường nối bằng `;`, còn Unix-like là `:`. Nếu tự nối, vừa dễ sai dấu phân cách vừa dễ lỗi khi phần tử chứa dấu cách.

```xml
<path id="app.classpath">
    <pathelement location="${classes.dir}"/>
    <fileset dir="lib">
        <include name="**/*.jar"/>
    </fileset>
</path>

<target name="run-main" depends="compile">
    <java classname="vn.demo.App"
          fork="true"
          failonerror="true"
          classpathref="app.classpath"/>
</target>
```

Ví dụ này giả định thư mục `lib/` tồn tại; nếu không cần thư viện, có thể bỏ `<fileset dir="lib">`. Ant tự xây dựng classpath phù hợp cho JVM. Nếu một công cụ ngoài bắt buộc nhận classpath dưới dạng chuỗi, hãy dùng `<pathconvert>` với `targetos` phù hợp cho hệ đích thay vì nối thủ công.

## 6. Unicode trong tên tệp: phải phân biệt với mã hóa nội dung

Unicode có thể xuất hiện ở nhiều vị trí khác nhau:

| Vị trí | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Nội dung `build.xml` | `location="Tài nguyên"` | Lưu XML bằng UTF-8 và khai báo đúng `encoding="UTF-8"`. |
| **Tên** thư mục/tệp trên filesystem | `Đề kiểm tra/đầu vào.csv` | Truyền qua thuộc tính đường dẫn và API file; kiểm tra môi trường thực sự hỗ trợ tên đó. |
| Nội dung file `.java` | `System.out.println("Xin chào");` | Chỉ rõ `<javac encoding="UTF-8"/>` nếu nguồn được lưu UTF-8. |
| Nội dung tệp properties | `welcome=Xin chào` | Nạp với bộ đọc có encoding phù hợp; xem `<loadproperties>`. |
| Tên entry trong ZIP/JAR | `Cấu hình mặc định.txt` | Chỉ định UTF-8 cho ZIP/JAR và kiểm tra công cụ giải nén phía nhận. |
| Văn bản in ra từ chương trình ngoài | `Đã xử lý: ...` | Dùng mã hóa output đúng thực tế khi Ant đọc stdout/stderr; việc này độc lập với tên file. |

### Đọc UTF-8 properties đúng cách

Nếu dự án có file cấu hình dạng properties lưu UTF-8, ví dụ:

```text
config/
└── cấu hình build.properties
```

thì có thể nạp như sau:

```xml
<loadproperties srcFile="config/cấu hình build.properties"
                encoding="UTF-8"/>
```

Đây là trường hợp cần phân biệt `<loadproperties>` với việc dùng `<property file="...">` mà không xác định rõ encoding dữ liệu. Với dữ liệu tiếng Việt, nên nêu tường minh encoding và thống nhất quy ước cho nhóm phát triển.

### Đường dẫn Unicode không đồng nghĩa terminal luôn hiển thị đúng

Nếu Ant đã mở được tệp Unicode nhưng terminal in ra ký tự lạ, có thể chỉ là lỗi **mã hóa hiển thị log**; ngược lại, một dòng log nhìn đúng cũng không chứng minh filesystem đã mở đúng tệp. Khi cần phân tích:

1. Kiểm tra file tồn tại đúng tên thực tế bằng công cụ hỗ trợ Unicode.
2. Kiểm tra lệnh/đối số do script truyền.
3. Kiểm tra charset của stdout/stderr nếu công cụ ngoài sinh văn bản.
4. Chỉ thay đổi mã hóa terminal hoặc output khi đã xác định đó là nguyên nhân.

Đối với `<exec>`, thuộc tính `outputencoding` có thể được đặt theo encoding **mà tiến trình thực sự xuất ra** (ví dụ UTF-8). Nó điều khiển cách đọc output, không “sửa” tên file trên đĩa. Trên JDK và hệ điều hành khác nhau, đường chuyển Unicode tới chương trình native cũng có thể khác nhau; cách ổn định nhất vẫn là dùng task/API hỗ trợ Unicode và hạn chế bước trung gian qua shell.

## 7. Unicode normalization: hai tên nhìn như nhau có thể khác byte

Unicode cho phép một ký tự hiển thị được biểu diễn bằng nhiều chuỗi code point. Ví dụ ký tự **é** có thể là:

- **NFC**: một code point `U+00E9` (`é`).
- **NFD**: chữ `e` (`U+0065`) theo sau bởi dấu sắc kết hợp `U+0301` (`e\u0301`).

Hai tên `Café.txt` tạo bằng hai cách trên có thể trông giống hệt nhau, nhưng chuỗi Unicode không giống nhau. Một số filesystem chuẩn hóa hoặc coi chúng tương đương; filesystem khác có thể lưu thành hai tên phân biệt.

**Vì vậy, tránh tạo hai đường dẫn chỉ khác dạng Unicode normalization.** Với tên file do phần mềm tự sinh, nên quy định một dạng chuẩn hóa (thường là NFC) trước khi tạo tên; đồng thời giữ đúng tên thực tế khi truy cập tệp được cung cấp từ bên ngoài. Việc tự đổi tên hàng loạt có thể làm hỏng liên kết hoặc đường dẫn Git nếu không cập nhật tham chiếu.

Ví dụ Python ngắn giúp quan sát:

```python
import unicodedata

nfc_name = "Caf\u00e9.txt"
nfd_name = "Cafe\u0301.txt"

print(nfc_name == nfd_name)  # False
print(unicodedata.normalize("NFC", nfc_name)
      == unicodedata.normalize("NFC", nfd_name))  # True
```

Đây là kiểm tra trên **chuỗi**. Nó không nói chắc filesystem hiện tại sẽ lưu hai tên thành hai tệp, vì việc so khớp tên trên đĩa còn do filesystem quyết định. Ant không tự chuyển mọi đường dẫn bạn nhập sang một normalization form duy nhất. Một path đúng về mặt ký tự có thể không tìm thấy tệp nếu đầu vào và tên trên đĩa khác dạng và filesystem không coi chúng tương đương.

## 8. Phân biệt chữ hoa/chữ thường: quy tắc của Ant và filesystem

Giả sử repository có tham chiếu:

```xml
<copy file="config/Settings.xml"
      tofile="build output/Settings.xml"/>
```

Nhưng trên đĩa thực tế là `config/settings.xml`.

- Trên filesystem **phân biệt hoa/thường**, `Settings.xml` và `settings.xml` là hai đường dẫn khác nhau; task có thể báo không tìm thấy nguồn.
- Trên filesystem **không phân biệt hoa/thường**, tham chiếu sai kiểu chữ vẫn có thể tìm được tệp, khiến lỗi chỉ xuất hiện khi CI chạy trên volume khác.

Khi build Java, sự khác biệt này còn xuất hiện ở tên package, lớp và tài nguyên. Chẳng hạn mã gọi `getResource("/Config.json")` không nên phụ thuộc vào việc archive có chứa `config.json` với chữ `c` thường. Bên trong ZIP/JAR, tên entry là chuỗi tên riêng và việc tra cứu phân biệt hoa/thường có thể khác cách tìm file trên đĩa.

### `casesensitive` trong `<fileset>` thực sự làm gì?

Ant hỗ trợ thuộc tính `casesensitive` cho một số nhóm pattern, ví dụ:

```xml
<fileset dir="${resources.dir}" casesensitive="true">
    <include name="**/*.txt"/>
</fileset>
```

Mặc định của `<fileset>` là so khớp pattern có phân biệt hoa/thường. Với cấu hình trên, tên `hướng dẫn.txt` khớp với `*.txt`, còn `HƯỚNG DẪN.TXT` không khớp phần đuôi `.txt` theo quy tắc pattern.

Nếu đặt `casesensitive="false"`:

```xml
<fileset dir="${resources.dir}" casesensitive="false">
    <include name="**/*.txt"/>
</fileset>
```

pattern có thể chấp nhận cả `.TXT` và `.txt`. Tuy nhiên:

- Thuộc tính này **chỉ điều khiển so khớp pattern**; nó không làm filesystem chuyển thành không phân biệt hoa/thường.
- Nó **không** đảm bảo rằng `<copy file="config/Settings.xml">` sẽ tìm được `settings.xml` trên mọi máy.
- Nó **không** giải quyết tình huống hai tệp khác nhau trên Linux nhưng va chạm trong cùng một thư mục trên Windows.
- Bật `casesensitive="false"` cho mọi pattern có thể che giấu một lỗi đặt tên. Chỉ dùng khi nghiệp vụ thực sự cho phép nhiều biến thể kiểu chữ (ví dụ chấp nhận cả phần mở rộng `.jpg`/`.JPG`).

Quy tắc an toàn là sửa tham chiếu cho **khớp chính xác tên đã lưu trong Git** và cho CI kiểm tra trên filesystem có phân biệt hoa/thường.

## 9. Phát hiện xung đột tên ngay trong Git

Một dự án có thể vô tình chứa hai đường dẫn như:

```text
src/main/resources/Config.json
src/main/resources/config.json
```

hoặc hai tên chỉ khác Unicode NFC/NFD. Chúng có thể cùng tồn tại trong Git index, ngay cả khi checkout trên một số filesystem gặp khó khăn.

Để phát hiện từ sớm, có thể kiểm tra **danh sách tệp Git đang theo dõi**, thay vì chỉ quét file đã checkout. Ví dụ tạo `tools/check-portable-names.py`:

```python
#!/usr/bin/env python3
import subprocess
import sys
import unicodedata


def portable_key(path: str) -> str:
    # So sánh từng thành phần đường dẫn theo NFC + Unicode casefold.
    components = path.split("/")
    return "/".join(
        unicodedata.normalize(
            "NFC",
            unicodedata.normalize("NFC", part).casefold(),
        )
        for part in components
    )


def main() -> int:
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "-z"],
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Không đọc được Git index: {error}", file=sys.stderr)
        return 2

    seen = {}
    conflicts = 0

    try:
        paths = [
            entry.decode("utf-8")
            for entry in raw.split(b"\0")
            if entry
        ]
    except UnicodeDecodeError:
        print("Git index chứa tên tệp không giải mã được bằng UTF-8",
              file=sys.stderr)
        return 2

    for path in paths:
        key = portable_key(path)
        previous = seen.get(key)
        if previous is None:
            seen[key] = path
        elif previous != path:
            print("XUNG ĐỘT TÊN:")
            print(f"  {previous}")
            print(f"  {path}")
            conflicts += 1

    if conflicts:
        print(f"FAIL: phát hiện {conflicts} cặp đường dẫn xung đột")
        return 1

    print(f"PASS: {len(paths)} đường dẫn Git không xung đột "
          "theo NFC + casefold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Chạy ở thư mục gốc của repository:

```bash
python3 tools/check-portable-names.py
```

Windows có thể dùng `python` hoặc `py -3` tùy cách cài Python. Công cụ in `PASS` với exit code `0`, in `FAIL` và exit code `1` khi tìm thấy cặp tên xung đột, hoặc trả về `2` nếu không đọc được Git index. Vì dùng `git ls-files -z`, script xử lý được dấu cách trong tên đường dẫn và dấu xuống dòng nếu có trong tên tệp. Nó giả định đường dẫn Git được lưu theo UTF-8, phù hợp với quy ước đặt tên Unicode mà dự án lựa chọn.

**Ý nghĩa và giới hạn của bộ kiểm tra:**

- `NFC + casefold` là **quy tắc phòng ngừa bảo thủ**. Nó bắt được nhiều xung đột trên filesystem không phân biệt hoa/thường, kể cả các tên Unicode thường bị bỏ sót.
- Nó có thể chặt hơn so với phép so sánh tên thực tế của một số filesystem; vì thế mục tiêu của nó là tiêu chuẩn đặt tên **dùng chung cho dự án**, không phải mô phỏng chính xác Windows, Linux hay macOS.
- Script này chỉ xem **tệp Git đang theo dõi**. Nó không kiểm tra file đầu ra build, symlink, quyền tệp, tên thiết bị dành riêng hay mọi giới hạn tên của Windows. Nếu cần hỗ trợ chính thức nhiều filesystem, bổ sung kiểm tra riêng cho những ràng buộc đó.
- Các lỗi tham chiếu sai kiểu chữ vẫn cần kiểm tra khi build/test trên môi trường phân biệt hoa/thường; bộ phát hiện va chạm không thể tự tìm mọi đường dẫn được viết sai trong code.

Có thể cho CI chạy script trước khi gọi Ant. Nếu muốn gắn vào một target Ant, cấu hình rõ executable Python của runner:

```xml
<property name="python.command" value="python3"/>

<target name="check-filenames">
    <exec executable="${python.command}"
          dir="${basedir}"
          failonerror="true">
        <arg file="${basedir}/tools/check-portable-names.py"/>
    </exec>
</target>
```

Trên runner Windows không có lệnh `python3`, hãy chỉ định `-Dpython.command=python` (nếu `python` được cài sẵn). Ant không tự cài Python hoặc Git; kiểm tra này là **công cụ phụ trợ**, không phải một tính năng mặc định của `<javac>`.

## 10. Đổi tên tệp chỉ khác chữ hoa/chữ thường trong Git

Khi cần đổi `readme.md` thành `README.md`, chỉ đổi tên trực tiếp bằng trình quản lý tệp đôi khi không được Git ghi nhận như mong muốn trên filesystem không phân biệt hoa/thường. Một cách rõ ràng là dùng tên trung gian:

```bash
git mv docs/readme.md docs/readme.__rename__.md
git mv docs/readme.__rename__.md docs/README.md
```

Sau đó kiểm tra danh sách thay đổi được stage bằng `git status` và cập nhật mọi tham chiếu trong `build.xml`, scripts, tài liệu hoặc code đến đúng `docs/README.md`. Ví dụ giả định tệp gốc và thư mục `docs/` tồn tại; tên trung gian phải là tên chưa được sử dụng.

Không nên đặt hai tệp có cùng đường dẫn khi bỏ qua chữ hoa/thường vào cùng dự án chỉ để phục vụ hai trường hợp tên khác nhau. Trên filesystem không hỗ trợ đồng thời hai tên, việc checkout hoặc ghi một trong hai có thể thất bại hoặc che lấp dữ liệu.

## 11. Không để việc copy hoặc đóng gói che giấu tên tệp sai

Pattern Ant và các phép chuyển đổi tên có thể làm lỗi khó phát hiện:

```xml
<!-- Có thể lấy cả .txt và .TXT, nhưng tên output vẫn như trên đĩa -->
<copy todir="${dist.dir}">
    <fileset dir="${resources.dir}" casesensitive="false">
        <include name="**/*.txt"/>
    </fileset>
</copy>
```

Nếu mục tiêu là bản phát hành ổn định, cần quyết định **chính xác** tên tài nguyên nào được cho phép. Ví dụ một tên tệp `Cấu hình.txt` trong dự án nên có đúng một cách viết trong code và trong đường dẫn sử dụng lúc runtime.

Trong `<zip>`/`<jar>`, cần phân biệt:

- **Đường dẫn archive ở bên ngoài**: `Bản phát hành/Ứng dụng thử.jar`. Ant phải mở đúng đường dẫn file này trên filesystem.
- **Tên entry trong archive**: `Cấu hình mặc định.txt`. Bộ đóng gói và công cụ giải nén cần thống nhất mã hóa tên entry (ưu tiên UTF-8).
- **Nội dung entry**: byte của XML, JSON, properties, Java class hay hình ảnh. Chúng có quy tắc mã hóa riêng; không nên chuyển đổi nội dung nhị phân như văn bản.

Ví dụ dùng Ant tạo ZIP cho tài nguyên:

```xml
<zip destfile="${dist.dir}/Tài nguyên phát hành.zip"
     basedir="${resources.dir}"
     encoding="UTF-8"/>
```

Khi nghi ngờ lỗi, có thể dùng lệnh `jar tf` để xem tên entry hoặc giải nén một bản vào thư mục độc lập để kiểm tra. Việc tên được **hiển thị đúng** trong công cụ xem archive vẫn cần kiểm chứng bằng khả năng mở lại đúng entry trong hệ thống đích.

## 12. Thiết kế một build đa nền tảng dễ kiểm tra

Một quy trình hợp lý cho dự án Ant gồm bốn phần:

```text
Repository Git
    |
    +-- Tên file thống nhất (cùng kiểu chữ, Unicode chuẩn hóa)
    |
    v
Kiểm tra đường dẫn (trước build)
    |
    +-- Phát hiện xung đột NFC/casefold trong Git index
    +-- Kiểm tra các tệp đầu vào bắt buộc
    |
    v
Ant clean -> compile -> copy resources -> package
    |
    +-- Thuộc tính location, fileset, path, javac encoding
    +-- exec truyền từng arg riêng nếu cần
    |
    v
Kiểm tra đầu ra trên các môi trường đích
    |
    +-- Mở JAR/ZIP, đối chiếu danh sách entry
    +-- Chạy smoke test/truy cập đúng tài nguyên
```

### Kiểm tra tệp đầu vào bắt buộc

Ant có thể dùng `<available>` và `<fail>` để báo lỗi ngay khi thiếu tài nguyên:

```xml
<target name="check-inputs">
    <available file="${resources.dir}/Cấu hình mặc định.txt"
               property="required.config.exists"/>

    <fail unless="required.config.exists"
          message="Thiếu tài nguyên: Cấu hình mặc định.txt"/>
</target>
```

Để target này thực sự được chạy, thêm vào chuỗi dependency, ví dụ đổi `depends="compile"` của `copy-resources` thành `depends="check-inputs,compile"`.

Lưu ý: `<available>` kiểm tra việc **filesystem tìm thấy** đường dẫn, không kiểm chứng bắt buộc từng chữ hoa/chữ thường. Nó có thể PASS trên một volume không phân biệt và FAIL ở volume khác nếu tên trong XML sai kiểu chữ. Do đó cần giữ quy ước tên chuẩn và kiểm tra trên filesystem có phân biệt hoa/thường.

### Đoạn CI minh họa

Dù là Jenkins, GitHub Actions, GitLab CI hay runner tự quản lý, ý tưởng là:

```bash
# Chạy tại thư mục gốc repository, Python và Git phải có sẵn
python3 tools/check-portable-names.py

# Project Ant nằm ở thư mục có dấu cách
ant -f "./Dự án Ant/build.xml" clean package

# Kiểm tra JAR cuối cùng
jar tf "./Dự án Ant/Bản phát hành/Ứng dụng thử.jar"
```

CI phải dừng nếu lệnh phát hiện va chạm hoặc Ant trả về mã thoát lỗi. Trong CI có nhiều máy, cần thống nhất JDK, Ant và các phụ thuộc để không nhầm lỗi toolchain với lỗi tên đường dẫn. Một lượt kiểm tra trên Linux với filesystem phân biệt hoa/thường thường giúp phát hiện tham chiếu sai kiểu chữ mà môi trường khác bỏ qua; kiểm tra thêm trên Windows/macOS tùy mục tiêu triển khai.

## 13. Tình huống thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ant -f` báo không tìm thấy `build.xml` khi thư mục có dấu cách | Đường dẫn bị shell tách token | Quote toàn bộ tham số đường dẫn ở lệnh terminal. |
| `<exec>` chạy được với `data.csv` nhưng lỗi với `đơn hàng 01.csv` | Ghép tham số trong `<arg line>` hoặc thông qua `sh -c`/`cmd /c` | Dùng mỗi `<arg value>`/`<arg file>` cho một đối số; hạn chế shell trung gian. |
| `<javac>` báo ký tự nguồn không hợp lệ | Encoding nội dung `.java` không khớp compiler | Lưu nguồn theo encoding thống nhất và chỉ rõ `encoding`. |
| File properties có dấu bị lỗi nội dung | Nạp sai charset | Dùng cách nạp properties có chỉ định encoding phù hợp. |
| Log console hiển thị sai tiếng Việt | Charset của console/stdout khác dữ liệu | Kiểm tra charset của luồng output; không mặc nhiên đổi tên file. |
| Build PASS trên Windows nhưng thiếu `Config.json` trên Linux | Tên thực tế là `config.json` | Sửa tham chiếu và tên Git đúng từng ký tự; chạy CI trên filesystem phân biệt hoa/thường. |
| `<fileset includes="**/*.txt">` không lấy `README.TXT` | Pattern đang phân biệt hoa/thường | Dùng tên/đuôi chuẩn; nếu có chủ đích chấp nhận mọi kiểu chữ mới đặt `casesensitive="false"`. |
| Hai tên nhìn giống hệt nhưng một tên không tìm thấy | NFC/NFD khác nhau | Kiểm tra code point Unicode, chuẩn hóa đầu vào có kiểm soát và đổi tên nhất quán. |
| Checkout trên máy khác báo xung đột file | Hai tên khác case hoặc normalization mà filesystem không phân biệt | Phát hiện qua Git index, chọn một tên chuẩn, cập nhật reference. |
| Tên trong JAR bị hiển thị sai ở công cụ giải nén | Công cụ xử lý tên entry ZIP/JAR không cùng mã hóa | Dùng UTF-8 khi tạo archive và kiểm tra bằng công cụ đọc hỗ trợ đúng chuẩn. |
| `<copy>` hoặc `<delete>` tác động sai mục tiêu | Tự thêm dấu nháy vào property hoặc phân giải đường dẫn sai gốc | Sử dụng `location`, kiểm tra `basedir`, tránh coi dấu nháy là ký tự đường dẫn. |

## 14. Bài thực hành: kiểm chứng bằng thay đổi có kiểm soát

**Thử nghiệm A — Dấu cách:** tạo đúng cấu trúc `Dự án Ant`, chạy target `clean package` từ thư mục cha. Đổi tên thư mục thành `Dự án Ant có dấu cách` rồi lặp lại với tham số `-f` được quote đầy đủ. Đối chiếu kết quả khi cố tình bỏ dấu nháy ở shell.

**Thử nghiệm B — Unicode:** đổi tên `Cấu hình mặc định.txt` thành một tên tiếng Việt khác và sửa cả tham chiếu trong `build.xml`. Kiểm tra tên tài nguyên trong JAR bằng `jar tf`. Sau đó thay nội dung file Java bằng chuỗi Unicode và kiểm tra thông báo khi chạy `java -jar`; ghi nhớ rằng tên file và nội dung file đi qua hai cơ chế mã hóa khác nhau.

**Thử nghiệm C — Chữ hoa/chữ thường:** trên filesystem có phân biệt, đặt tệp `Tài nguyên/Config.txt` và sửa pattern/tham chiếu lần lượt thành `Config.txt` và `config.txt`. Quan sát khác biệt. Trên filesystem không phân biệt, kiểm tra bộ quét đường dẫn qua Git thay vì cố tạo hai file chỉ khác case.

**Thử nghiệm D — NFC/NFD:** dùng đoạn Python phần 7 để tạo hai chuỗi hiển thị tương tự; xác nhận so sánh chuỗi thường trả về `False` và so sánh sau chuẩn hóa NFC trả về `True`. Không cần thực sự tạo hai tệp xung đột trên filesystem của máy.

**Thử nghiệm E — Đối số tiến trình ngoài:** dùng một chương trình in từng đối số `args[]` của Java; gọi qua `<exec>` với `<arg value>`/`<arg file>` và đường dẫn `đầu vào 01.txt`. Mục tiêu là nhìn thấy **toàn bộ tên file trong một phần tử** `args[]`.

### Câu hỏi tự kiểm tra

1. Vì sao `<copy file="Tài liệu.txt">` không cần tự chèn dấu nháy, còn lệnh terminal `ant -f "./Dự án Ant/build.xml"` lại cần?
2. `<arg line="--input đường dẫn có dấu cách.csv">` khác `<arg value="--input"/>` và `<arg file="...">` như thế nào?
3. `encoding="UTF-8"` trên `<javac>` có tác động tới việc filesystem so khớp `README.txt` và `readme.txt` không?
4. Hai tên tệp Unicode trông giống nhau có thể khác mã code point ra sao? Chuẩn hóa NFC có tác dụng gì?
5. Thuộc tính `casesensitive="false"` của `<fileset>` có làm Windows và Linux dùng chung một quy tắc filesystem không?
6. Vì sao bộ phát hiện va chạm nên đọc cả Git index thay vì chỉ nhìn thư mục đã checkout?

## 15. Ghi nhớ khi triển khai

Với Apache Ant, **dấu cách** được xử lý tốt khi truyền đường dẫn trực tiếp cho task tích hợp và quote đúng khi khởi chạy từ shell. **Unicode** yêu cầu phân biệt mã hóa XML, nội dung file, tên tệp trên filesystem và tên entry trong archive; không có một thuộc tính encoding duy nhất sửa tất cả. **Chữ hoa/chữ thường** và **normalization** phụ thuộc vào quy tắc filesystem, nên cần chuẩn hóa cách đặt tên trong repository, kiểm tra xung đột và chạy build trên môi trường đích.

Một bản build thực sự đa nền tảng là bản build mà các đường dẫn được tham chiếu nhất quán, từng đối số được truyền chính xác và những khác biệt filesystem có thể được phát hiện bằng kiểm tra tự động trước khi phát hành.

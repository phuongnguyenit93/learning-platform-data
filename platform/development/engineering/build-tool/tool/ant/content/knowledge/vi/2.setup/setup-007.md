# Cấu hình JVM chạy Ant bằng ANT_OPTS

## 1. ANT_OPTS là gì?

Apache Ant là một chương trình Java. Khi chạy lệnh `ant`, script khởi chạy của Ant tìm Java executable, tạo classpath cần thiết rồi khởi động JVM để chạy lớp `org.apache.tools.ant.Main`. Vì vậy, trước khi Ant có thể đọc `build.xml` và thực hiện target, JVM đã phải được khởi động với một tập hợp tùy chọn phù hợp.

`ANT_OPTS` là biến môi trường dành cho các tùy chọn truyền vào JVM chạy Ant. Bạn có thể dùng nó để:

- Điều chỉnh bộ nhớ heap mà tiến trình Ant được phép sử dụng.
- Truyền các thuộc tính hệ thống Java bằng tùy chọn `-Dname=value`.
- Bổ sung các tùy chọn JVM như cấu hình garbage collector hoặc tùy chọn chẩn đoán.
- Cấu hình hành vi của thư viện Java được nạp bên trong tiến trình Ant.

Ví dụ, khi một dự án có nhiều task, nhiều file hoặc xử lý bytecode lớn, JVM mặc định có thể không đủ heap. Có thể đặt giới hạn heap tối đa cao hơn:

```text
ANT_OPTS=-Xms512m -Xmx2g
```

Ở đây:

- `-Xms512m`: heap ban đầu có kích thước 512 MB.
- `-Xmx2g`: heap tối đa là 2 GB.

Hai giá trị này là ví dụ để minh họa, không phải cấu hình phù hợp cho mọi máy. Hãy cân nhắc RAM, số tiến trình chạy đồng thời và lượng bộ nhớ mà các task thực sự cần.

## 2. ANT_OPTS được áp dụng ở đâu?

Luồng khởi chạy cơ bản:

```text
Terminal / CI / IDE
       |
       | gọi lệnh ant
       v
Ant launcher script (ant hoặc ant.bat)
       |
       | đọc ANT_OPTS
       | ghép JVM options vào lệnh java
       v
JVM chạy Ant
       |
       | nạp org.apache.tools.ant.Main
       v
Ant đọc build.xml và chạy target
```

Điểm quan trọng là `ANT_OPTS` cấu hình JVM đang chạy Ant. Nó không phải thuộc tính của một target và cũng không phải cú pháp riêng trong `build.xml`.

Ví dụ:

```bash
export ANT_OPTS='-Xms512m -Xmx2g -Dbuild.profile=ci'
ant package
```

Khi script Ant khởi chạy JVM, các tùy chọn trên được đưa vào tiến trình đó. `-Dbuild.profile=ci` tạo thuộc tính hệ thống Java có tên `build.profile`. Ant thường đưa system properties vào tập thuộc tính của project, nên build file có thể tham chiếu `${build.profile}`.

```xml
<target name="show-runtime">
    <echo message="Java version: ${java.version}"/>
    <echo message="Java home: ${java.home}"/>
    <echo message="Build profile: ${build.profile}"/>
</target>
```

Khi chạy `ant show-runtime`, build có thể in ra phiên bản Java, thư mục Java đang chạy và profile được truyền vào.

`ANT_OPTS` chỉ được launcher script của Ant đọc. Nếu một chương trình tự gọi Ant bằng Java API, hoặc tự chạy `org.apache.tools.ant.Main` bằng một lệnh Java riêng, chương trình đó phải tự cấu hình JVM options; không nên giả định `ANT_OPTS` sẽ tự được áp dụng.

## 3. Thiết lập ANT_OPTS theo hệ điều hành

Biến môi trường phải tồn tại trong môi trường của tiến trình gọi Ant. Thông thường, cách đơn giản nhất là đặt biến trong terminal hiện tại rồi chạy Ant ngay trong terminal đó.

### Linux và macOS (Bash hoặc shell tương thích)

Thiết lập trong phiên terminal hiện tại:

```bash
export ANT_OPTS='-Xms512m -Xmx2g -Dfile.encoding=UTF-8'
ant -version
ant package
```

Nếu chỉ muốn áp dụng cho một lệnh, có thể đặt biến ngay trước lệnh:

```bash
ANT_OPTS='-Xms512m -Xmx2g' ant package
```

Xóa biến khỏi phiên shell:

```bash
unset ANT_OPTS
```

Lệnh `export` làm cho biến được truyền tới các tiến trình con được khởi chạy từ shell đó. Một terminal khác đang mở không tự động nhận thay đổi này.

### Windows Command Prompt

Dùng `set` để đặt biến trong cửa sổ Command Prompt hiện tại:

```bat
set "ANT_OPTS=-Xms512m -Xmx2g -Dfile.encoding=UTF-8"
ant -version
ant package
```

Cú pháp `set "NAME=value"` giúp tránh vô tình đưa dấu cách ở cuối vào giá trị biến.

Xóa biến trong cửa sổ hiện tại:

```bat
set ANT_OPTS=
```

Biến đặt bằng `set` chỉ có hiệu lực trong cửa sổ Command Prompt đó và các tiến trình được khởi chạy từ nó.

### Windows PowerShell

PowerShell dùng namespace `Env:` để truy cập biến môi trường của tiến trình:

```powershell
$env:ANT_OPTS = '-Xms512m -Xmx2g -Dfile.encoding=UTF-8'
ant -version
ant package
```

Xóa biến khỏi phiên PowerShell:

```powershell
Remove-Item Env:ANT_OPTS
```

Nếu đặt biến bằng giao diện Environment Variables của Windows, hãy mở terminal hoặc IDE mới sau khi lưu thay đổi để tiến trình mới nhận được môi trường cập nhật. Những tiến trình đã chạy không tự nhận giá trị mới.

### Cấu hình trong CI

Trong pipeline CI, nên đặt `ANT_OPTS` ở phạm vi job hoặc step cần chạy Ant. Ví dụ với một cấu hình YAML có hỗ trợ `env`:

```yaml
steps:
  - name: Build with Ant
    env:
      ANT_OPTS: -Xms512m -Xmx2g
    run: ant package
```

Cú pháp khai báo `env` cụ thể tùy nền tảng CI. Hãy dùng cú pháp của hệ thống đang chạy và chỉ cấp biến cho những bước cần nó. Không nên ghi thông tin bí mật vào `ANT_OPTS`, vì tham số JVM và thuộc tính hệ thống có thể xuất hiện trong log hoặc thông tin tiến trình.

## 4. Những JVM option thường dùng

### Điều chỉnh heap

| Tùy chọn | Ý nghĩa |
|---|---|
| `-Xms512m` | Đặt heap ban đầu ở mức 512 MB |
| `-Xmx2g` | Giới hạn heap tối đa ở mức 2 GB |
| `-XX:MaxMetaspaceSize=512m` | Đặt giới hạn Metaspace ở mức 512 MB |

Heap lưu trữ phần lớn object được tạo trong JVM. Nếu Ant hoặc task chạy trong cùng JVM tạo nhiều object, heap tối đa quá thấp có thể dẫn đến `OutOfMemoryError: Java heap space`.

Metaspace lưu metadata của class. Giới hạn metaspace quá thấp có thể gây lỗi `OutOfMemoryError: Metaspace`, đặc biệt khi build nạp nhiều class hoặc dùng classloader riêng. Không nên thêm `MaxMetaspaceSize` nếu chưa có lý do rõ ràng; giới hạn không cần thiết có thể khiến tiến trình thất bại sớm.

Tăng `-Xmx` không bảo đảm build nhanh hơn. Nếu build bị giới hạn bởi I/O, compiler bên ngoài, mạng hoặc một tiến trình con khác, tăng heap cho JVM Ant có thể không giải quyết nguyên nhân.

### Truyền thuộc tính hệ thống

Tùy chọn `-Dname=value` đặt một Java system property:

```text
-Dfile.encoding=UTF-8
-Duser.timezone=UTC
-Dbuild.profile=ci
```

Mã Java có thể đọc thuộc tính bằng `System.getProperty("build.profile")`. Ant cũng thường công bố các system properties thành Ant properties, cho phép tham chiếu `${build.profile}` trong build file.

Nếu mục đích là truyền một Ant user property rõ ràng từ dòng lệnh, có thể dùng tùy chọn `-D` của chính Ant:

```bash
ant -Dbuild.profile=ci package
```

Hai cách có tầng xử lý khác nhau:

- `-Dbuild.profile=ci` nằm trong `ANT_OPTS` là tùy chọn của JVM, tạo system property.
- `ant -Dbuild.profile=ci package` là tùy chọn dòng lệnh của Ant, tạo user property cho build.

Khi một giá trị phải được truyền tường minh cho một lần build, tùy chọn của Ant thường dễ nhận biết hơn. Dùng `ANT_OPTS` khi cần cấu hình JVM hoặc muốn áp dụng cùng system property cho mọi lần chạy Ant trong môi trường đó.

### Tùy chọn JVM khác

Có thể truyền các tùy chọn JVM phù hợp với JDK đang sử dụng, chẳng hạn:

```text
-XX:+UseG1GC
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=./build/heap-dump.hprof
```

- `-XX:+UseG1GC` yêu cầu JVM dùng G1 garbage collector trên các JDK hỗ trợ tùy chọn đó.
- `-XX:+HeapDumpOnOutOfMemoryError` yêu cầu JVM tạo heap dump khi xảy ra lỗi hết bộ nhớ.
- `-XX:HeapDumpPath=...` chỉ định đường dẫn lưu heap dump.

Heap dump có thể lớn và chứa dữ liệu nhạy cảm trong bộ nhớ tiến trình. Chỉ bật việc tạo dump khi cần điều tra, đồng thời kiểm soát vị trí lưu và quyền truy cập tệp.

## 5. Phân biệt ANT_OPTS với các cách truyền tham số khác

Một số biến và tùy chọn có tên gần giống nhau nhưng phục vụ các tầng khác nhau:

| Cách cấu hình | Đối tượng nhận | Mục đích |
|---|---|---|
| `ANT_OPTS` | JVM chạy Ant, thông qua launcher script | Truyền JVM options |
| `ANT_ARGS` | Lệnh Ant | Bổ sung tham số dòng lệnh Ant |
| `ant -Dname=value` | Ant project | Đặt Ant user property cho lần chạy |
| `JAVA_TOOL_OPTIONS` | Các JVM khởi chạy trong môi trường có biến này | Bổ sung tùy chọn ở phạm vi rộng hơn Ant |
| `JAVA_OPTS` | Phụ thuộc launcher hoặc script cụ thể | Tên biến quy ước, không phải biến chuẩn mà mọi launcher Ant đều tự đọc |

Ví dụ `ANT_ARGS` có thể chứa tham số Ant như `-verbose`, trong khi `ANT_OPTS` có thể chứa `-Xmx2g`. Không đặt `-verbose` của Ant vào `ANT_OPTS`, vì JVM có thể hiểu đó là một JVM option không hợp lệ.

`JAVA_OPTS` thường được một số ứng dụng hoặc script tự định nghĩa và đọc. Không nên giả định biến này có tác dụng với launcher Ant chuẩn nếu script đang dùng không hỗ trợ nó.

`JAVA_TOOL_OPTIONS` có phạm vi rộng hơn vì JVM tự kiểm tra biến này khi khởi động. Nó có thể tác động tới những JVM khác cũng được khởi chạy trong môi trường đó. Chỉ dùng khi thực sự muốn áp dụng ở phạm vi rộng; nếu chỉ cần cấu hình JVM chạy Ant, `ANT_OPTS` thể hiện ý định rõ hơn.

## 6. Phạm vi tác động: Ant JVM và JVM con

Một nhầm lẫn thường gặp là cho rằng đặt `ANT_OPTS` sẽ cấu hình mọi chương trình Java được build gọi ra. Thực tế, `ANT_OPTS` cấu hình JVM chạy Ant. Nếu một task tạo tiến trình JVM riêng, tiến trình đó có cấu hình khởi động riêng.

Ví dụ, task `<java>` chạy trong JVM hiện tại khi `fork` không được bật. Khi bật `fork="true"`, Ant tạo một JVM con. Các tham số của JVM con nên được khai báo trực tiếp bằng `<jvmarg>`:

```xml
<target name="run-tool">
    <java classname="com.example.Tool" fork="true">
        <classpath>
            <pathelement location="build/classes"/>
        </classpath>
        <jvmarg value="-Xms128m"/>
        <jvmarg value="-Xmx512m"/>
        <arg value="--check"/>
    </java>
</target>
```

Ở ví dụ này, `ANT_OPTS` vẫn điều chỉnh JVM chạy Ant; các phần tử `<jvmarg>` điều chỉnh JVM con chạy `com.example.Tool`.

Tương tự, nếu task compiler được cấu hình chạy trong một tiến trình riêng, cần xem tài liệu task và compiler đang dùng để truyền tham số đúng cách. Không nên tăng heap của Ant rồi kết luận compiler forked cũng đã nhận cùng giới hạn.

## 7. Kiểm tra cấu hình đã có hiệu lực

### Kiểm tra Ant và Java đang được dùng

Chạy:

```bash
ant -version
ant -diagnostics
java -version
```

`ant -version` xác nhận lệnh Ant hoạt động. `ant -diagnostics` cung cấp thông tin chẩn đoán về môi trường Ant, Java và cấu hình liên quan. `java -version` cho biết Java mà lệnh `java` trên PATH đang chạy; nếu máy có nhiều JDK, thông tin này có thể khác JVM mà một launcher Ant cụ thể chọn. Khi cần xác định chính xác, đối chiếu `java.home` trong phần diagnostics của Ant.

### Kiểm tra system property từ build file

Tạm thêm một target chẩn đoán:

```xml
<target name="show-jvm-properties">
    <echo message="java.version=${java.version}"/>
    <echo message="java.home=${java.home}"/>
    <echo message="build.profile=${build.profile}"/>
</target>
```

Đặt biến rồi chạy:

```bash
export ANT_OPTS='-Dbuild.profile=ci'
ant show-jvm-properties
```

Nếu giá trị `build.profile` xuất hiện là `ci`, system property đã được truyền tới JVM Ant và được Ant đưa vào project properties.

### Kiểm tra JVM flags khi cần xác nhận bộ nhớ

Trên JDK có công cụ `jcmd`, có thể lấy PID của tiến trình Ant đang chạy rồi kiểm tra:

```bash
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
```

`VM.command_line` hiển thị lệnh khởi chạy JVM; `VM.flags` hiển thị các cờ JVM đang có hiệu lực, bao gồm những cờ liên quan tới heap. Lệnh cần chạy khi tiến trình Ant còn tồn tại và tài khoản hiện tại có quyền attach vào JVM đó. Thay `<PID>` bằng mã tiến trình thực tế.

## 8. Lỗi thường gặp và cách xử lý

### Ant không nhận thay đổi ANT_OPTS

Nguyên nhân thường là biến được đặt trong terminal khác, IDE đã mở trước khi thay đổi biến môi trường, hoặc launcher đang dùng không đọc biến đó.

Cách xử lý:

1. In giá trị biến ngay trong terminal sẽ chạy Ant (`echo $ANT_OPTS` trên shell Unix-like, `echo %ANT_OPTS%` trong CMD hoặc `$env:ANT_OPTS` trong PowerShell).
2. Chạy Ant từ chính terminal đó.
3. Nếu chạy qua IDE, cấu hình VM options trong cấu hình chạy Ant của IDE hoặc khởi động lại IDE sau khi thay đổi biến môi trường.
4. Xác nhận cách khởi chạy thực tế có dùng launcher script của Ant hay không.

### JVM báo Unrecognized VM option

Một tùy chọn có thể không được JDK hiện tại hỗ trợ, đã bị loại bỏ hoặc viết sai. Hãy kiểm tra phiên bản Java mà Ant thực sự sử dụng, sau đó tra cứu tùy chọn theo phiên bản JDK đó. Không sao chép cờ JVM từ một phiên bản Java khác mà không kiểm tra khả năng tương thích.

### JVM không thể cấp phát bộ nhớ

Thông báo như `Could not reserve enough space for object heap` có thể xuất hiện khi `-Xms` hoặc `-Xmx` vượt quá giới hạn bộ nhớ mà hệ điều hành hoặc môi trường CI cho phép. Giảm giá trị, kiểm tra RAM khả dụng và giới hạn bộ nhớ của container/runner. Nếu máy đang chạy nhiều build song song, tính tổng bộ nhớ của tất cả tiến trình.

### Tăng heap nhưng lỗi vẫn xảy ra

Xác định tiến trình gây lỗi. Nếu lỗi đến từ JVM con, compiler forked hoặc một công cụ bên ngoài, `ANT_OPTS` của JVM Ant có thể không ảnh hưởng đến tiến trình đó. Cấu hình tham số ở task hoặc launcher tạo tiến trình con tương ứng.

### Giá trị có dấu cách hoặc ký tự đặc biệt

`ANT_OPTS` là một chuỗi được launcher phân tích thành các tham số JVM. Cách xử lý dấu nháy và dấu cách phụ thuộc shell và script launcher. Hãy bắt đầu với các tùy chọn đơn giản, kiểm tra lệnh khởi chạy và tránh đặt giá trị phức tạp vào biến nếu không cần thiết. Với đường dẫn có khoảng trắng, dùng cách quoting phù hợp với hệ điều hành và launcher đang dùng.

## 9. Thực hành cấu hình ổn định

- Chỉ thêm JVM options khi có yêu cầu cụ thể như thiếu heap, cần system property hoặc cần chẩn đoán.
- Đặt `ANT_OPTS` ở phạm vi terminal, CI job hoặc cấu hình chạy Ant cần dùng; tránh đặt cờ thử nghiệm ở phạm vi toàn máy.
- Dùng cùng phiên bản JDK trên máy lập trình và CI, đồng thời ghi nhận phiên bản Ant nếu dự án phụ thuộc vào hành vi cụ thể.
- Không đặt `-Xmx` quá sát tổng RAM của máy; chừa bộ nhớ cho hệ điều hành, IDE và tiến trình build khác.
- Khi cần cấu hình JVM con, khai báo tham số ở task tạo tiến trình đó và kiểm tra riêng.
- Gỡ các cờ chẩn đoán hoặc heap dump không còn cần thiết sau khi điều tra để tránh tạo tệp lớn và làm lộ dữ liệu.
- Không dùng system properties để truyền mật khẩu hoặc token. Thông tin dòng lệnh và thuộc tính JVM có thể bị lộ qua log, báo cáo lỗi hoặc công cụ xem tiến trình.

`ANT_OPTS` là điểm cấu hình hữu ích khi cần kiểm soát JVM thực thi Ant. Hãy xác định đúng JVM cần cấu hình, đặt biến trong môi trường khởi chạy tương ứng và kiểm tra giá trị thực tế trong tiến trình. Cách làm đó giúp xử lý các vấn đề về bộ nhớ, thuộc tính hệ thống và chẩn đoán mà không nhầm cấu hình JVM của Ant với tham số của target hay JVM con.


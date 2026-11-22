# Annotation processing và quản lý mã nguồn được sinh

Annotation processing là cơ chế của Java cho phép một chương trình xử lý annotation trong lúc biên dịch. Annotation processor có thể đọc thông tin từ các lớp, phương thức, trường hoặc annotation được khai báo trong mã nguồn, sau đó tạo thêm mã Java, tài nguyên hoặc tệp phục vụ build.

Trong Apache Ant, annotation processing thường được điều khiển thông qua task `<javac>` và các tùy chọn của Java compiler như `-processorpath`, `-processor`, `-s`, `-A`, `-proc:only` và `-proc:none`. Việc quản lý thư mục mã nguồn được sinh cũng quan trọng như cấu hình processor: mã sinh ra cần có vị trí riêng, được biên dịch đúng lúc và được dọn dẹp cùng các đầu ra build tương ứng.

## 1. Annotation processing hoạt động như thế nào?

Annotation là metadata gắn với thành phần mã nguồn. Ví dụ:

```java
@GenerateMapper
public class Customer {
    private String name;
}
```

Annotation processor là một thành phần chạy trong quá trình biên dịch, nhận các annotation mà nó hỗ trợ và phân tích những phần tử Java liên quan. Processor có thể tạo tệp nguồn mới thông qua API `javax.annotation.processing` và `javax.annotation.processing.Filer`.

Luồng xử lý cơ bản:

```text
Mã nguồn Java có annotation
          |
          v
      javac bắt đầu
          |
          v
  Phát hiện annotation processor
          |
          v
  Processor phân tích phần tử
          |
          v
 Sinh Java source / resource
          |
          v
  javac xử lý các source mới
          |
          v
      Tạo class files
```

Một processor có thể chạy qua nhiều vòng (round). Nếu một processor tạo thêm mã nguồn Java, compiler có thể đưa các kiểu vừa sinh vào vòng xử lý tiếp theo. Quá trình tiếp tục cho đến khi không còn source mới được tạo hoặc quá trình xử lý kết thúc.

Annotation processing thường dùng cho các thư viện tạo mapper, dependency injection, metadata, bộ chuyển đổi hoặc mã boilerplate. Ví dụ về nhóm công cụ sử dụng cơ chế này gồm MapStruct, Dagger và nhiều processor tự viết.

## 2. Phân biệt thư viện annotation và thư viện processor

Một số thư viện tách API annotation mà mã nguồn sử dụng khỏi phần triển khai processor chạy trong compiler.

| Thành phần | Vai trò | Classpath phù hợp |
|---|---|---|
| API/annotation library | Cung cấp annotation hoặc kiểu mà mã nguồn Java tham chiếu | Compile classpath của `<javac>` |
| Annotation processor | Đọc annotation và sinh mã nguồn/tài nguyên | Processor path của javac |
| Dependency của processor | Các thư viện mà chính processor cần khi chạy | Cùng processor path |
| Generated source | Mã Java được processor tạo ra | Thư mục đầu ra mã nguồn sinh, thường nằm dưới `build/` |
| Compiled class | Bytecode được compiler tạo từ source gốc và source sinh | Thư mục `destdir` của `<javac>` |

Không nên nhầm `processorpath` với compile classpath. Processor cần có mặt trên processor path để compiler có thể nạp và chạy nó. Còn các annotation hoặc API mà source code tham chiếu cần có mặt trên compile classpath.

Ví dụ với một thư viện mapper, dự án có thể cần cả JAR API để mã nguồn sử dụng annotation và JAR processor để tạo implementation. Hai JAR có thể có tên artifact và phiên bản liên quan, nhưng chúng phục vụ hai mục đích khác nhau.

## 3. Khai báo đường dẫn cho processor trong Ant

Task `<javac>` hỗ trợ nested `<classpath>` cho các dependency biên dịch. Các tùy chọn annotation processing của javac có thể được truyền qua nested `<compilerarg>`.

Một build file thường khai báo riêng:

- `compile.classpath`: thư viện mà mã nguồn cần khi biên dịch.
- `annotation.processor.path`: processor JAR và các dependency lúc chạy processor.
- `generated.sources.dir`: thư mục chứa `.java` được sinh.
- `classes.dir`: thư mục chứa `.class` được biên dịch.

Ví dụ cấu trúc thư mục:

```text
sample-project/
├── build.xml
├── lib/
│   ├── compile/
│   │   └── mapper-api.jar
│   └── processors/
│       ├── mapper-processor.jar
│       └── processor-helper.jar
├── src/
│   └── main/java/
└── build/
    ├── classes/
    └── generated-sources/annotations/
```

Khai báo path trong Ant:

```xml
<property name="src.dir" value="src/main/java"/>
<property name="build.dir" value="build"/>
<property name="classes.dir" value="${build.dir}/classes"/>
<property name="generated.sources.dir"
          value="${build.dir}/generated-sources/annotations"/>

<path id="compile.classpath">
    <fileset dir="lib/compile">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="annotation.processor.path">
    <fileset dir="lib/processors">
        <include name="*.jar"/>
    </fileset>
</path>

<pathconvert property="annotation.processor.path.string"
             refid="annotation.processor.path"/>
```

`<pathconvert>` chuyển Path thành chuỗi phân tách theo quy ước của hệ điều hành. Chuỗi này được truyền cho tùy chọn `-processorpath` của javac. Cách này tránh tự ghép dấu `:` hoặc `;`, vốn khác nhau giữa Linux/macOS và Windows.

## 4. Cấu hình annotation processing qua `<javac>`

Ví dụ sau thực hiện annotation processing và biên dịch trong cùng một lần gọi compiler:

```xml
<target name="prepare-compile-output">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${generated.sources.dir}"/>
</target>

<target name="compile" depends="prepare-compile-output">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"
           encoding="UTF-8">

        <classpath refid="compile.classpath"/>

        <compilerarg value="-processorpath"/>
        <compilerarg value="${annotation.processor.path.string}"/>

        <compilerarg value="-processor"/>
        <compilerarg value="com.example.processor.MapperProcessor"/>

        <compilerarg value="-s"/>
        <compilerarg value="${generated.sources.dir}"/>

        <compilerarg value="-Amapper.componentModel=spring"/>
    </javac>
</target>
```

Thay `com.example.processor.MapperProcessor`, JAR và tham số `-A` bằng processor thực tế mà dự án sử dụng. Nếu processor cần nhiều class, có thể liệt kê tên các processor trong một giá trị `-processor`, phân tách bằng dấu phẩy.

Các tùy chọn có ý nghĩa:

| Tùy chọn | Công dụng |
|---|---|
| `-processorpath` | Chỉ định nơi javac tìm các annotation processor và dependency chạy cùng processor |
| `-processor` | Chỉ định tường minh class name của processor cần chạy |
| `-s` | Chỉ định thư mục ghi các Java source được sinh |
| `-Akey=value` | Truyền một tùy chọn riêng cho annotation processor |
| `destdir` của Ant `<javac>` | Chỉ định thư mục ghi class files; tương ứng với `-d` của javac |

Khi processor tạo `.java`, javac có thể tiếp tục xử lý và biên dịch các source đó trong cùng compilation. Vì vậy, trong cấu hình một lần gọi thông thường, không cần thêm thư mục generated source vào `srcdir` của chính lần compile đó.

### 4.1. Tự động phát hiện processor

Nếu không chỉ định `-processor`, javac có thể phát hiện processor qua cơ chế service provider. JAR processor thường chứa tệp:

```text
META-INF/services/javax.annotation.processing.Processor
```

Tệp này liệt kê tên đầy đủ của các lớp processor có thể được nạp. Nếu dùng `-processorpath`, javac tìm processor trên đường dẫn đó. Nếu không tách processor path, việc phát hiện có thể phụ thuộc vào classpath compiler và cấu hình JDK.

Để build dễ tái lập, nên khai báo processor path rõ ràng. Có thể dùng `-processor` để giới hạn chính xác processor cần chạy, nhất là khi thư viện chứa nhiều processor hoặc khi muốn tránh chạy processor không liên quan.

### 4.2. Tương thích với các JDK mới

Hành vi tự động dò annotation processor thay đổi ở các phiên bản JDK mới. Từ JDK 23, javac không còn mặc định quét classpath để tự kích hoạt annotation processing như các JDK trước. Build cần yêu cầu rõ việc xử lý annotation bằng cách chỉ định processor hoặc processor path, hoặc dùng tùy chọn chế độ xử lý phù hợp.

Trong cấu hình ở trên, `-processorpath` và `-processor` đã thể hiện rõ processor cần nạp. Nếu dự án dựa vào cơ chế discovery thay vì chỉ định class cụ thể, hãy cấu hình `-processorpath` rõ ràng và kiểm tra yêu cầu của JDK mục tiêu. `-proc:full` là tùy chọn tường minh để yêu cầu vừa xử lý annotation vừa biên dịch; chỉ thêm khi phiên bản javac đang dùng hỗ trợ tùy chọn này.

Không nên dựa vào việc “máy này tự tìm thấy processor” như một cấu hình build. Hãy cố định phiên bản processor, đường dẫn và cách kích hoạt trong build file hoặc trong môi trường build được quản lý.

## 5. Quản lý thư mục mã nguồn được sinh

Tùy chọn `-s` của javac xác định nơi ghi mã nguồn Java do processor tạo. Nên đặt thư mục này dưới vùng build output, ví dụ:

```text
build/generated-sources/annotations/
```

Không nên ghi mã nguồn sinh trực tiếp vào `src/main/java`. Thư mục source thường chứa mã do lập trình viên quản lý; nếu trộn source sinh vào đó, build có thể biên dịch lại các tệp đã sinh ở lần chạy sau, tạo thay đổi không mong muốn trong Git hoặc gây xung đột tên lớp.

Một cấu trúc đầu ra dễ quản lý:

```text
build/
├── classes/
│   └── com/example/...
└── generated-sources/
    └── annotations/
        └── com/example/...
```

`generated-sources/annotations` chứa `.java` do processor tạo; `classes` chứa `.class` được compiler tạo từ source gốc và source sinh. Việc tách hai vị trí giúp dễ xem mã sinh, dọn đầu ra và đóng gói class.

### 5.1. Tạo thư mục trước khi compile

Hãy tạo `destdir` và generated source directory trước khi chạy javac:

```xml
<target name="prepare-compile-output">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${generated.sources.dir}"/>
</target>
```

Sau đó target compile phụ thuộc `prepare-compile-output`. Điều này làm rõ cấu trúc đầu ra và tránh phụ thuộc vào việc compiler tự tạo thư mục.

### 5.2. Không chỉnh sửa source được sinh bằng tay

Các tệp trong generated source directory là đầu ra của processor. Nếu cần thay đổi hành vi, hãy sửa annotation, cấu hình processor hoặc mã nguồn đầu vào. Thay đổi trực tiếp tệp được sinh thường bị ghi đè ở lần build sau và không có tính bền vững.

Nếu cần kiểm tra logic được tạo, hãy mở tệp trong `build/generated-sources/annotations` để đọc hoặc debug, nhưng xem nó là artifact có thể tái tạo.

### 5.3. Tách thư mục theo module hoặc processor

Với build nhiều module, mỗi module nên có thư mục generated source riêng để tránh ghi đè hoặc trộn output:

```text
build/
├── module-a/generated-sources/annotations/
├── module-b/generated-sources/annotations/
└── module-c/generated-sources/annotations/
```

Nếu nhiều processor cùng chạy trong một compilation, chúng có thể dùng chung generated source directory của module. Nếu các giai đoạn khác nhau tạo cùng tên lớp hoặc cùng resource, hãy xem lại ranh giới output và cách cấu hình processor.

## 6. Clean generated source và tránh mã sinh cũ

Mã nguồn được sinh là output của build, vì vậy cần được dọn cùng class files khi thực hiện clean build.

```xml
<target name="clean">
    <delete dir="${build.dir}"/>
</target>
```

Nếu `build.dir` chứa cả class output và generated source output, một lần `ant clean` sẽ xóa cả hai. Target compile sau đó tạo lại các thư mục cần thiết.

Không nên làm cho target compile luôn phụ thuộc vào target clean nếu muốn giữ lợi ích incremental compilation. Thay vào đó, cung cấp target `rebuild` để người dùng chủ động yêu cầu dọn sạch rồi biên dịch lại:

```xml
<target name="rebuild" depends="clean,compile"
        description="Clean and compile all sources again"/>
```

Khi processor thay đổi, phiên bản processor thay đổi, tùy chọn `-A` thay đổi hoặc một source đã bị xóa, các generated output cũ có thể không còn phù hợp. Hãy chạy clean build để loại bỏ tệp sinh cũ trước khi tạo lại.

### 6.1. Vì sao cần xóa cả generated source và class output?

Ant `<javac>` có thể bỏ qua việc biên dịch những source không thay đổi dựa trên timestamp và các class output tương ứng. Nếu chỉ xóa generated source mà vẫn giữ class files, Ant có thể không kích hoạt compilation như bạn mong đợi. Ngược lại, nếu giữ generated source cũ, một lớp đã bị loại khỏi source gốc có thể vẫn còn trong thư mục generated.

Vì vậy, khi cần tái tạo hoàn toàn mã sinh, hãy xóa cả generated source directory và class output liên quan, thường bằng cách xóa toàn bộ `build/`. Không xóa thư mục source được lập trình viên quản lý.

## 7. Chế độ xử lý annotation của javac

Javac cung cấp các chế độ điều khiển annotation processing:

| Tùy chọn | Hành vi |
|---|---|
| `-proc:none` | Không chạy annotation processor |
| `-proc:only` | Chạy annotation processing nhưng không thực hiện biên dịch thông thường |
| `-proc:full` | Thực hiện annotation processing và biên dịch |

Trong một lần compile thông thường, không cần thêm tùy chọn chế độ nếu processor đã được phát hiện theo cách phù hợp với JDK. Có thể dùng `-proc:full` để yêu cầu rõ cả xử lý annotation và compilation trên các JDK hỗ trợ tùy chọn này.

### 7.1. Chỉ chạy processor bằng `-proc:only`

Một số build cần tách riêng bước sinh source và bước biên dịch. Khi đó có thể gọi javac với `-proc:only` và `-s` để chỉ chạy processor:

```xml
<target name="generate-sources" depends="prepare-compile-output">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
        <compilerarg value="-proc:only"/>
        <compilerarg value="-processorpath"/>
        <compilerarg value="${annotation.processor.path.string}"/>
        <compilerarg value="-processor"/>
        <compilerarg value="com.example.processor.MapperProcessor"/>
        <compilerarg value="-s"/>
        <compilerarg value="${generated.sources.dir}"/>
    </javac>
</target>
```

Target này yêu cầu javac chạy processor để tạo source trong generated directory, không biên dịch các lớp theo quy trình thông thường. Nếu cần class files, phải có một bước javac tiếp theo biên dịch source gốc cùng các source được sinh.

### 7.2. Tắt annotation processing bằng `-proc:none`

Khi build chỉ cần biên dịch source đã có và không muốn chạy processor, có thể dùng:

```xml
<javac srcdir="${src.dir}"
       destdir="${classes.dir}"
       includeantruntime="false">
    <classpath refid="compile.classpath"/>
    <compilerarg value="-proc:none"/>
</javac>
```

Nếu mã nguồn tham chiếu lớp được sinh từ một lần compile trước, các class hoặc source tương ứng vẫn cần có trong classpath/source input. `-proc:none` không tự tạo ra các lớp còn thiếu.

### 7.3. Hai giai đoạn: generate rồi compile

Quy trình hai giai đoạn có thể hữu ích khi cần xem hoặc xử lý generated source trước khi compile. Luồng tổng quát:

```text
Source gốc
    |
    v
javac -proc:only -s generated-sources
    |
    v
Generated .java
    |
    v
javac -proc:none
  (source gốc + generated source)
    |
    v
Class files
```

Trong lần compile thứ hai, đưa cả thư mục source gốc và generated source vào danh sách source của javac, đồng thời dùng `-proc:none` để tránh chạy processor lần nữa nếu mục tiêu chỉ là biên dịch output đã sinh. Với Ant, có thể khai báo nhiều source root bằng path được hỗ trợ bởi `srcdir` hoặc nested source path của task; bảo đảm đường dẫn generated directory được thêm đúng cách và không trùng với source root khác.

Chỉ chọn mô hình hai giai đoạn khi có lý do cụ thể. Với phần lớn dự án, để javac vừa chạy processor vừa compile trong một lần gọi đơn giản hơn và cho phép compiler xử lý các vòng source sinh tự động.

## 8. Truyền cấu hình cho processor bằng `-A`

Annotation processor có thể nhận các tùy chọn riêng theo dạng:

```text
-Akey=value
```

Trong Ant:

```xml
<compilerarg value="-Amapper.defaultComponentModel=spring"/>
<compilerarg value="-Amapper.suppressGeneratorTimestamp=true"/>
```

Tên key và giá trị phụ thuộc vào processor. Ví dụ trên chỉ minh họa cú pháp, không phải mọi processor đều hiểu các key này.

Hãy đặt các giá trị thay đổi theo môi trường thành Ant property để dễ quản lý:

```xml
<property name="mapper.component.model" value="default"/>

<javac srcdir="${src.dir}" destdir="${classes.dir}"
       includeantruntime="false">
    <compilerarg value="-Amapper.defaultComponentModel=${mapper.component.model}"/>
</javac>
```

Giá trị có thể được truyền từ dòng lệnh:

```bash
ant -Dmapper.component.model=spring compile
```

Ant property được mở rộng trước khi compiler nhận đối số. Không đưa token, mật khẩu hoặc thông tin xác thực vào tùy chọn processor nếu chúng có thể bị in ra log hoặc ghi vào generated source.

## 9. Chẩn đoán annotation processing

Khi processor không chạy hoặc không sinh source, hãy kiểm tra theo từng lớp cấu hình.

### 9.1. Xác nhận processor có trên processor path

Kiểm tra JAR processor có nằm trong thư mục mà `<path id="annotation.processor.path">` quét hay không. Nếu processor cần dependency khác, các JAR đó cũng phải có trên processor path.

Nếu dùng `-processor`, kiểm tra class name đầy đủ và chính tả. Nếu dựa vào discovery, kiểm tra JAR có service descriptor `META-INF/services/javax.annotation.processing.Processor` và danh sách class bên trong có đúng.

### 9.2. Kiểm tra annotation API trên compile classpath

Nếu compiler báo không tìm thấy annotation hoặc kiểu được dùng trong source, hãy kiểm tra compile classpath. Đặt processor JAR trên processor path không tự động làm cho mọi API của processor có sẵn cho mã nguồn ứng dụng.

### 9.3. In thông tin vòng xử lý

Javac có các tùy chọn chẩn đoán hữu ích:

```xml
<compilerarg value="-XprintRounds"/>
<compilerarg value="-XprintProcessorInfo"/>
```

`-XprintRounds` hiển thị thông tin các vòng annotation processing. `-XprintProcessorInfo` hiển thị processor nào được gọi và các annotation mà nó xử lý. Đây là tùy chọn chẩn đoán; hãy bỏ chúng khỏi build thông thường nếu log quá nhiều.

### 9.4. Kiểm tra generated source

Sau khi compile, xem thư mục `${generated.sources.dir}`. Nếu thư mục rỗng:

- Xác nhận source đầu vào có annotation mà processor hỗ trợ.
- Kiểm tra processor có được phát hiện và kích hoạt hay không.
- Kiểm tra `-s` có trỏ đến đúng thư mục và task đã tạo thư mục đó.
- Kiểm tra processor có điều kiện cấu hình khiến nó không sinh mã trong trường hợp này.
- Xem lỗi hoặc cảnh báo compiler trước khi kết luận processor không chạy.

Nếu source đã được sinh nhưng class không xuất hiện, kiểm tra lỗi compile của source sinh, classpath và chế độ `-proc:only`/`-proc:none`.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có processor nào được chạy | Processor không nằm trên processor path, discovery chưa được kích hoạt hoặc tên processor sai | Khai báo `-processorpath`, kiểm tra service descriptor và dùng `-processor` nếu cần |
| `ClassNotFoundException` khi nạp processor | Thiếu JAR processor hoặc dependency của processor | Bổ sung JAR vào `annotation.processor.path` |
| Không tìm thấy annotation trong source | API annotation thiếu trên compile classpath | Thêm thư viện API vào nested `<classpath>` của `<javac>` |
| Generated source không xuất hiện | Không có annotation phù hợp, processor bị tắt hoặc `-s` trỏ sai | Kiểm tra annotation, processor option, `-proc` và generated directory |
| Source sinh ra nhưng không được compile | Dùng `-proc:only` hoặc cấu hình compilation hai giai đoạn chưa đưa generated source vào source input | Thêm bước compile source gốc và generated source, hoặc dùng một lần javac thông thường |
| Lỗi duplicate class hoặc `FilerException` | Nhiều processor hoặc nhiều lần xử lý cố tạo cùng một tệp | Kiểm tra processor, tên output và việc chạy lặp trong cùng build |
| Mã sinh cũ vẫn còn sau khi xóa annotation | Generated output không được dọn hoặc compile incremental không chạy lại | Clean cả generated source và class output rồi build lại |
| Máy dùng JDK mới không tự chạy processor | Cơ chế tự động discovery thay đổi theo phiên bản javac | Khai báo rõ processor path/class hoặc chế độ xử lý phù hợp với JDK |
| Build phụ thuộc máy cá nhân | Processor chỉ có trong classpath toàn cục hoặc thư viện người dùng | Quản lý JAR processor và phiên bản trong cấu hình build |
| Build tạo source vào `src/main/java` | `-s` trỏ nhầm vào thư mục source được quản lý | Chuyển output vào thư mục riêng dưới `build/generated-sources` |

## 11. Ví dụ build file hoàn chỉnh

Ví dụ dưới đây minh họa một lần compile có annotation processing, tách API và processor path, ghi generated source vào vùng build output và cung cấp target clean riêng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="annotation-processing-demo" default="compile" basedir=".">

    <property name="src.dir" value="src/main/java"/>
    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>
    <property name="generated.sources.dir"
              value="${build.dir}/generated-sources/annotations"/>

    <path id="compile.classpath">
        <fileset dir="lib/compile">
            <include name="*.jar"/>
        </fileset>
    </path>

    <path id="annotation.processor.path">
        <fileset dir="lib/processors">
            <include name="*.jar"/>
        </fileset>
    </path>

    <pathconvert property="annotation.processor.path.string"
                 refid="annotation.processor.path"/>

    <target name="clean" description="Remove all generated build output">
        <delete dir="${build.dir}"/>
    </target>

    <target name="prepare-compile-output">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${generated.sources.dir}"/>
    </target>

    <target name="compile" depends="prepare-compile-output">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">

            <classpath refid="compile.classpath"/>

            <compilerarg value="-processorpath"/>
            <compilerarg value="${annotation.processor.path.string}"/>

            <compilerarg value="-processor"/>
            <compilerarg value="com.example.processor.MapperProcessor"/>

            <compilerarg value="-s"/>
            <compilerarg value="${generated.sources.dir}"/>

            <compilerarg value="-Amapper.componentModel=spring"/>
        </javac>
    </target>

    <target name="rebuild" depends="clean,compile"
            description="Remove old generated files and compile again"/>

</project>
```

Trong dự án thật, thay đường dẫn JAR và class name bằng processor đang dùng. Nếu processor không cần chỉ định class cụ thể, có thể bỏ `-processor` và dựa vào service discovery trên processor path, với điều kiện cơ chế đó được kích hoạt phù hợp với JDK mục tiêu.

Chạy biên dịch thông thường:

```bash
ant compile
```

Chạy clean build để tái tạo toàn bộ output:

```bash
ant rebuild
```

`compile` không tự xóa output mỗi lần chạy nên vẫn có thể tận dụng cơ chế incremental của Ant. `rebuild` xóa toàn bộ `build/`, sau đó tạo lại class và generated source.

## 12. Checklist quản lý annotation processing

- [ ] Đã xác định annotation processor và phiên bản cần dùng.
- [ ] API annotation có trên compile classpath nếu source cần tham chiếu.
- [ ] Processor JAR cùng dependency của nó có trên processor path.
- [ ] Đã chọn discovery hoặc chỉ định processor class tường minh.
- [ ] Cấu hình kích hoạt annotation processing tương thích với JDK mục tiêu.
- [ ] Các tùy chọn `-A` được khai báo rõ và có giá trị phù hợp.
- [ ] `-s` trỏ đến generated source directory riêng dưới build output.
- [ ] `destdir` trỏ đến thư mục class output riêng.
- [ ] Generated source không bị trộn vào thư mục source do lập trình viên quản lý.
- [ ] Đã phân biệt compile một giai đoạn với quy trình `-proc:only` hai giai đoạn.
- [ ] Target clean xóa cả generated source và class output liên quan.
- [ ] Khi processor, tùy chọn hoặc source set thay đổi, có cách tái tạo output sạch.
- [ ] Đã dùng thông tin chẩn đoán javac khi processor không chạy hoặc source không được sinh.

Annotation processing giúp tự động hóa việc tạo mã Java và tài nguyên trong quá trình build. Khi Ant tách rõ compile classpath, processor path, generated source directory và class output, đồng thời quản lý clean build đúng cách, mã nguồn được sinh sẽ trở thành một phần có thể tái tạo và kiểm soát được của quy trình biên dịch.

Tài liệu tham khảo: [Apache Ant Manual — Javac Task](https://ant.apache.org/manual/Tasks/javac.html) và [The Java Compiler (`javac`) — Annotation Processing](https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html).
